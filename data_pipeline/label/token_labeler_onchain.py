"""
Solana Token Labeling Algorithm – On-Chain Pipeline Edition
=========================================================

Fully on-chain data pipeline for token labeling using our own Helius-based
infrastructure. Replaces all external APIs (DexScreener, Birdeye, SolScan)
with direct blockchain data access through multiple Helius API keys.

How the on-chain lookup works
----------------------------
1. **Live price / liquidity**
   * Direct swap data analysis from Jupiter/Raydium programs
   * Real-time transaction monitoring for current pricing
2. **Historical pricing (≈17 days)**
   * Parse historical swap transactions 
   * Build OHLCV data from on-chain swap events
3. **Holder count**
   * Direct token account analysis from on-chain data
4. **Market metrics**
   * Liquidity analysis from DEX programs
   * Volume calculation from swap transactions

On-chain data source
-------------------
Uses our multi-key Helius API setup with automatic rotation and failover.
No external API dependencies - fully blockchain-based data.

All classification logic and CLI flags remain unchanged.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# Add the on-chain pipeline to the path
pipeline_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "on_chain_solana_pipeline")
sys.path.insert(0, pipeline_path)

from onchain_provider import OnChainDataProvider
from config.config_loader import load_config

# ───────────────────────── Logging ──────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("onchain_token_labeling.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ──────────────────────── Constants ─────────────────────────
ONE_HOUR = 60 * 60
THREE_DAYS_SEC = 3 * 24 * 60 * 60
SUSTAIN_DAYS_SEC = 7 * 24 * 60 * 60
CANDLE_INTERVAL = "5m"

# ─────────────────── Dataclass per token ────────────────────
@dataclass
class TokenMetrics:
    mint_address: str
    current_price: Optional[float] = None
    volume_24h: Optional[float] = None
    market_cap: Optional[float] = None
    peak_price_72h: Optional[float] = None
    post_ath_peak_price: Optional[float] = None
    has_sustained_drop: bool = False
    price_drops: List[Tuple[datetime, float]] = None
    holder_count: Optional[int] = None

    def __post_init__(self):
        if self.price_drops is None:
            self.price_drops = []

# ─────────────────────── TokenLabeler ───────────────────────
class OnChainTokenLabeler:
    RUG_THRESHOLD = 0.70
    SUCCESS_APPRECIATION = 10.0
    SUCCESS_MIN_HOLDERS = 100

    def __init__(self):
        # Load config and initialize provider properly
        self.provider: Optional[OnChainDataProvider] = None
        self.config = None

    # ── async context ──
    async def __aenter__(self):
        # Import config loader here to avoid path issues
        from config.config_loader import load_config
        self.config = load_config()
        self.provider = OnChainDataProvider(self.config)
        await self.provider.__aenter__()
        return self

    async def __aexit__(self, *exc):
        if self.provider:
            await self.provider.__aexit__(*exc)

    # ────────── CSV driver ──────────
    async def label_tokens_from_csv(self, inp: str, out: str, batch: int = 50) -> pd.DataFrame:
        df = pd.read_csv(inp)
        if "mint_address" not in df.columns:
            raise ValueError("CSV must contain 'mint_address' column")
        mints = df["mint_address"].tolist()

        results: List[Tuple[str, str]] = []
        for i in range(0, len(mints), batch):
            chunk = mints[i:i + batch]
            logger.info("Batch %d/%d (size=%d)", i // batch + 1, (len(mints) + batch - 1) // batch, len(chunk))
            out_chunk = await asyncio.gather(*[self._process(m) for m in chunk])
            results.extend([r for r in out_chunk if r is not None])
            if i + batch < len(mints):
                await asyncio.sleep(1)

        out_df = pd.DataFrame(results, columns=["mint_address", "label"])
        out_df.to_csv(out, index=False)
        logger.info("Saved %d labeled tokens → %s", len(out_df), out)
        return out_df

    # ────────── Per‑token flow ──────────
    async def _process(self, mint: str) -> Optional[Tuple[str, str]]:
        m = await self._gather_metrics(mint)
        if not self._has_any_data(m):
            logger.info("%s – skipped (no on-chain data found)", mint)
            return None
        return mint, self._classify(m)

    # --- helpers ----------------------------------------------------------
    @staticmethod
    def _has_any_data(m: TokenMetrics) -> bool:
        return (m.current_price is not None) or (m.holder_count is not None)

    async def _gather_metrics(self, mint: str) -> TokenMetrics:
        t = TokenMetrics(mint)

        try:
            # 1. Current price and volume from on-chain data
            price_data = await self.provider.get_current_price(mint)
            if price_data:
                t.current_price = price_data.get('price')
                t.volume_24h = price_data.get('volume_24h')
                t.market_cap = price_data.get('market_cap')

            # 2. Historical metrics from on-chain swap data
            hist = await self._historical_metrics(mint)
            t.__dict__.update(hist)

            # 3. Holder count from on-chain token accounts
            holder_data = await self.provider.get_holder_count(mint)
            if holder_data:
                t.holder_count = holder_data.get('count')

        except Exception as e:
            logger.warning("Error gathering metrics for %s: %s", mint, e)

        return t

    # Historical metrics from on-chain data
    async def _historical_metrics(self, mint: str) -> Dict[str, Any]:
        try:
            # Get historical OHLCV data from our on-chain pipeline
            candles = await self.provider.get_historical_ohlcv(mint, days=17)
            if not candles:
                return {}

            df = pd.DataFrame(candles)
            if df.empty:
                return {}

            # Ensure we have the right columns
            if 'timestamp' not in df.columns:
                return {}

            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df.sort_values("timestamp", inplace=True)
            
            launch = df["timestamp"].iloc[0]
            cut = launch + timedelta(seconds=THREE_DAYS_SEC)
            
            # Find ATH in first 3 days
            early_df = df.loc[df["timestamp"] <= cut]
            if early_df.empty:
                return {}
            
            ath_3d = early_df["high"].max()
            if pd.isna(ath_3d):
                return {}
            
            # Find post-ATH peak
            post_df = df.loc[df["timestamp"] > cut]
            if post_df.empty:
                return {}
            
            post_peak = post_df["high"].max()

            # Analyze for sustained drops and rug patterns
            roll: deque[Tuple[datetime, float]] = deque()
            bad, drops = False, []
            
            for _, row in post_df.iterrows():
                ts = row["timestamp"]
                while roll and (ts - roll[0][0]).total_seconds() > SUSTAIN_DAYS_SEC:
                    roll.popleft()
                roll.append((ts, row["high"]))
                peak = max(h for _, h in roll)
                drop_pct = 1 - row["low"] / peak if peak else 0
                
                if drop_pct >= 0.5:
                    bad = True
                if drop_pct >= 0.7 and (ts - roll[-1][0]).total_seconds() <= ONE_HOUR:
                    drops.append((ts.to_pydatetime(), drop_pct))

            return {
                "peak_price_72h": float(ath_3d),
                "post_ath_peak_price": float(post_peak),
                "has_sustained_drop": bad,
                "price_drops": drops,
            }

        except Exception as e:
            logger.warning("Error getting historical metrics for %s: %s", mint, e)
            return {}

    # ---------- classification ------------------
    def _classify(self, m: TokenMetrics) -> str:
        if m.current_price is None:
            return "unsuccessful"
        if any(d >= self.RUG_THRESHOLD for _, d in m.price_drops):
            return "rugpull"
        if self._is_success(m):
            return "successful"
        return "unsuccessful"

    def _is_success(self, m: TokenMetrics) -> bool:
        if None in (m.peak_price_72h, m.post_ath_peak_price, m.holder_count):
            return False
        if m.holder_count < self.SUCCESS_MIN_HOLDERS:
            return False
        if m.post_ath_peak_price / m.peak_price_72h < self.SUCCESS_APPRECIATION:
            return False
        if m.has_sustained_drop:
            return False
        return True

# ───────────────────────── CLI wrapper ─────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Label Solana tokens using on-chain data")
    parser.add_argument("--input", required=True, help="CSV with 'mint_address' column")
    parser.add_argument("--output", required=True, help="output CSV path")
    parser.add_argument("--batch", type=int, default=50, help="batch size (default 50)")
    args = parser.parse_args()

    async def runner():
        async with OnChainTokenLabeler() as tl:
            await tl.label_tokens_from_csv(args.input, args.output, args.batch)

    asyncio.run(runner())


if __name__ == "__main__":
    main()
