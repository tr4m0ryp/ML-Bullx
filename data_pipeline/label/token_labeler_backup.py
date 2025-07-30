"""
Modified version of the original token_labeler.py that uses the on-chain pipeline.
This is a direct adaptation that replaces the external API calls.
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

# Add pipeline path for imports
pipeline_dir = os.path.dirname(__file__)
sys.path.insert(0, pipeline_dir)

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

# ─────────────────────── Enhanced TokenLabeler ───────────────────────
class EnhancedTokenLabeler:
    """
    Enhanced version of TokenLabeler that uses on-chain data instead of external APIs.
    Drop-in replacement with the same interface and logic.
    """
    RUG_THRESHOLD = 0.70
    SUCCESS_APPRECIATION = 10.0
    SUCCESS_MIN_HOLDERS = 100

    def __init__(self, config_path: str = None):
        self.config = load_config(config_path)
        self.data_provider: Optional[OnChainDataProvider] = None

    # ── async context ──
    async def __aenter__(self):
        self.data_provider = OnChainDataProvider(self.config)
        await self.data_provider.__aenter__()
        return self

    async def __aexit__(self, *exc):
        if self.data_provider:
            await self.data_provider.__aexit__(*exc)

    # ────────── CSV driver ──────────
    async def label_tokens_from_csv(self, inp: str, out: str, batch: int = 20) -> pd.DataFrame:
        """Label tokens from CSV using on-chain data."""
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
            logger.info("%s – skipped (no on-chain data)", mint)
            return None
        return mint, self._classify(m)

    # --- helpers ----------------------------------------------------------
    @staticmethod
    def _has_any_data(m: TokenMetrics) -> bool:
        return (m.current_price is not None) or (m.holder_count is not None)

    async def _gather_metrics(self, mint: str) -> TokenMetrics:
        """Gather metrics using on-chain data provider."""
        t = TokenMetrics(mint)

        # 1. Current price and volume
        price_data = await self.data_provider.get_current_price(mint)
        if price_data:
            t.current_price = price_data.price
            t.volume_24h = price_data.volume_24h
            t.market_cap = price_data.market_cap

        # 2. Historical metrics
        hist_data = await self.data_provider.get_historical_data(mint)
        if hist_data:
            t.peak_price_72h = hist_data.peak_price_72h
            t.post_ath_peak_price = hist_data.post_ath_peak_price
            
            # Analyze historical data for drops
            hist_metrics = self._historical_metrics_from_ohlcv(hist_data.ohlcv)
            t.has_sustained_drop = hist_metrics.get("has_sustained_drop", False)
            t.price_drops = hist_metrics.get("price_drops", [])

        # 3. Holder count
        t.holder_count = await self.data_provider.get_holder_count(mint)
        
        return t

    def _historical_metrics_from_ohlcv(self, ohlcv: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process OHLCV data to detect sustained drops and rug patterns.
        Replicates the logic from the original _historical_metrics method.
        """
        if not ohlcv:
            return {}

        # Convert to DataFrame format similar to original
        df = pd.DataFrame(ohlcv)
        df["t"] = pd.to_datetime(df["ts"], unit="s")
        df.sort_values("t", inplace=True)
        
        if df.empty:
            return {}

        launch = df["t"].iloc[0]
        cut = launch + timedelta(seconds=THREE_DAYS_SEC)
        
        # Find 72h ATH
        ath_3d_df = df.loc[df["t"] <= cut]
        if ath_3d_df.empty:
            return {}
        ath_3d = ath_3d_df["h"].max()
        
        # Post-72h data
        post_df = df.loc[df["t"] > cut]
        if post_df.empty:
            return {}
        post_peak = post_df["h"].max()

        # Rolling window analysis for drops
        roll: deque[Tuple[datetime, float]] = deque()
        bad, drops = False, []
        
        for _, row in post_df.iterrows():
            ts = row["t"]
            
            # Maintain 7-day window
            while roll and (ts - roll[0][0]).total_seconds() > SUSTAIN_DAYS_SEC:
                roll.popleft()
            
            roll.append((ts, row["h"]))
            peak = max(h for _, h in roll)
            drop_pct = 1 - row["l"] / peak if peak else 0
            
            if drop_pct >= 0.5:
                bad = True
            if drop_pct >= 0.7 and (ts - roll[-1][0]).total_seconds() <= ONE_HOUR:
                drops.append((ts.to_pydatetime(), drop_pct))

        return {
            "has_sustained_drop": bad,
            "price_drops": drops,
        }

    # ---------- classification (unchanged from original) ------------------
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
    parser.add_argument("--batch", type=int, default=20, help="batch size (default 20)")
    parser.add_argument("--config", help="config file path")
    args = parser.parse_args()

    async def runner():
        async with EnhancedTokenLabeler(args.config) as tl:
            await tl.label_tokens_from_csv(args.input, args.output, args.batch)

    asyncio.run(runner())


if __name__ == "__main__":
    main()
