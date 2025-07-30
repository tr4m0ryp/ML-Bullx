"""
On-Chain Solana Token Labeling Algorithm
========================================

This version uses our own on-chain data pipeline instead of external APIs
like Birdeye and DexScreener. It queries price data, historical candles,
and holder counts directly from our TimescaleDB and Solana RPC.

The classification logic remains the same as the original labeler.
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

# Add the pipeline directory to path so we can import modules
pipeline_dir = os.path.dirname(__file__)
sys.path.insert(0, pipeline_dir)

from onchain_provider import OnChainDataProvider, PriceData, HistoricalData
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

# ─────────────────────── OnChainTokenLabeler ───────────────────────
class OnChainTokenLabeler:
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
        """
        Process tokens from CSV file and output labeled results.
        Using smaller default batch size since on-chain queries can be slower.
        """
        df = pd.read_csv(inp)
        if "mint_address" not in df.columns:
            raise ValueError("CSV must contain 'mint_address' column")
        mints = df["mint_address"].tolist()

        results: List[Tuple[str, str]] = []
        
        for i in range(0, len(mints), batch):
            chunk = mints[i:i + batch]
            logger.info("Processing batch %d/%d (size=%d)", 
                       i // batch + 1, (len(mints) + batch - 1) // batch, len(chunk))
            
            # Process chunk concurrently but with limited concurrency
            chunk_results = await asyncio.gather(*[self._process(m) for m in chunk])
            results.extend([r for r in chunk_results if r is not None])
            
            # Small delay between batches to be nice to the RPC
            if i + batch < len(mints):
                await asyncio.sleep(2)

        out_df = pd.DataFrame(results, columns=["mint_address", "label"])
        out_df.to_csv(out, index=False)
        logger.info("Saved %d labeled tokens → %s", len(out_df), out)
        return out_df

    # ────────── Per‑token flow ──────────
    async def _process(self, mint: str) -> Optional[Tuple[str, str]]:
        """Process a single token and return (mint, label) or None if skipped."""
        try:
            metrics = await self._gather_metrics(mint)
            if not self._has_any_data(metrics):
                logger.info("%s – skipped (no on-chain data available)", mint)
                return None
            
            label = self._classify(metrics)
            logger.debug("%s → %s", mint, label)
            return mint, label
            
        except Exception as e:
            logger.error("Error processing %s: %s", mint, e)
            return None

    # --- helpers ----------------------------------------------------------
    @staticmethod
    def _has_any_data(m: TokenMetrics) -> bool:
        """Check if we have any meaningful data for this token."""
        return (m.current_price is not None) or (m.holder_count is not None)

    async def _gather_metrics(self, mint: str) -> TokenMetrics:
        """Gather all metrics for a token from on-chain sources."""
        metrics = TokenMetrics(mint)

        # 1. Current price and volume
        price_data = await self.data_provider.get_current_price(mint)
        if price_data:
            metrics.current_price = price_data.price
            metrics.volume_24h = price_data.volume_24h
            metrics.market_cap = price_data.market_cap

        # 2. Historical data for peak analysis
        hist_data = await self.data_provider.get_historical_data(mint, days=17)
        if hist_data:
            metrics.peak_price_72h = hist_data.peak_price_72h
            metrics.post_ath_peak_price = hist_data.post_ath_peak_price
            
            # Analyze price drops from historical data
            drop_analysis = self._analyze_price_drops(hist_data.ohlcv)
            metrics.has_sustained_drop = drop_analysis['has_sustained_drop']
            metrics.price_drops = drop_analysis['price_drops']

        # 3. Holder count
        metrics.holder_count = await self.data_provider.get_holder_count(mint)

        return metrics

    def _analyze_price_drops(self, ohlcv: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze historical OHLCV data to detect sustained drops and rug patterns.
        This replicates the logic from the original labeler.
        """
        if not ohlcv:
            return {'has_sustained_drop': False, 'price_drops': []}

        # Convert timestamps and sort
        candles = []
        for candle in ohlcv:
            candles.append({
                'ts': datetime.fromtimestamp(candle['ts']),
                'h': candle['h'],
                'l': candle['l'],
                'o': candle['o'],
                'c': candle['c']
            })
        
        candles.sort(key=lambda x: x['ts'])
        
        if len(candles) < 2:
            return {'has_sustained_drop': False, 'price_drops': []}

        # Find the cutoff point (3 days after launch)
        launch_time = candles[0]['ts']
        cutoff_time = launch_time + timedelta(seconds=THREE_DAYS_SEC)
        
        # Split into 72h and post-72h periods
        post_cutoff_candles = [c for c in candles if c['ts'] > cutoff_time]
        
        if not post_cutoff_candles:
            return {'has_sustained_drop': False, 'price_drops': []}

        # Rolling window analysis for sustained drops
        rolling_window: deque[Tuple[datetime, float]] = deque()
        has_sustained_drop = False
        price_drops = []

        for candle in post_cutoff_candles:
            ts = candle['ts']
            
            # Maintain 7-day rolling window
            while rolling_window and (ts - rolling_window[0][0]).total_seconds() > SUSTAIN_DAYS_SEC:
                rolling_window.popleft()
            
            rolling_window.append((ts, candle['h']))
            
            # Find peak in current window
            if rolling_window:
                peak_price = max(price for _, price in rolling_window)
                
                # Calculate drop percentage
                drop_pct = 1 - candle['l'] / peak_price if peak_price > 0 else 0
                
                # Check for sustained drop (50%+ drop maintained)
                if drop_pct >= 0.5:
                    has_sustained_drop = True
                
                # Check for rug pull pattern (70%+ drop within 1 hour)
                if drop_pct >= 0.7:
                    # Check if this drop happened quickly (within 1 hour of peak)
                    peak_time = max(rolling_window, key=lambda x: x[1])[0]
                    if (ts - peak_time).total_seconds() <= ONE_HOUR:
                        price_drops.append((ts, drop_pct))

        return {
            'has_sustained_drop': has_sustained_drop,
            'price_drops': price_drops
        }

    # ---------- classification ------------------
    def _classify(self, metrics: TokenMetrics) -> str:
        """Classify token based on gathered metrics."""
        # If no price data, mark as unsuccessful
        if metrics.current_price is None:
            return "unsuccessful"
        
        # Check for rug pull pattern
        if any(drop_pct >= self.RUG_THRESHOLD for _, drop_pct in metrics.price_drops):
            return "rugpull"
        
        # Check for success criteria
        if self._is_success(metrics):
            return "successful"
        
        return "unsuccessful"

    def _is_success(self, metrics: TokenMetrics) -> bool:
        """Determine if a token meets success criteria."""
        # Need all key metrics to evaluate success
        required_fields = [
            metrics.peak_price_72h,
            metrics.post_ath_peak_price,
            metrics.holder_count
        ]
        
        if any(field is None for field in required_fields):
            return False
        
        # Minimum holder count requirement
        if metrics.holder_count < self.SUCCESS_MIN_HOLDERS:
            return False
        
        # Price appreciation requirement (10x from 72h peak to post-peak)
        price_appreciation = metrics.post_ath_peak_price / metrics.peak_price_72h
        if price_appreciation < self.SUCCESS_APPRECIATION:
            return False
        
        # Must not have sustained drops
        if metrics.has_sustained_drop:
            return False
        
        return True


# ───────────────────────── CLI wrapper ─────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Label Solana tokens using on-chain data")
    parser.add_argument("--input", required=True, help="CSV with 'mint_address' column")
    parser.add_argument("--output", required=True, help="Output CSV path")
    parser.add_argument("--batch", type=int, default=20, help="Batch size (default 20)")
    parser.add_argument("--config", help="Path to config YAML file")
    args = parser.parse_args()

    async def runner():
        async with OnChainTokenLabeler(args.config) as labeler:
            await labeler.label_tokens_from_csv(args.input, args.output, args.batch)

    asyncio.run(runner())


if __name__ == "__main__":
    main()
