"""
Enhanced Token Classification Algorithm

The algorithm now distinguishes between 4 categories:
1. SUCCESSFUL: Tokens that show sustained growth and community adoption
   - Historical Success: Overrides all other factors if a token shows legendary historical performance (e.g., >1,000,000x recovery).
   - Traditional success: 10x appreciation, 100+ holders, no major drops
   - Recovery success: Strong recovery (3x+) after early drops with sustained growth

2. RUGPULL: Tokens with coordinated dumps or no recovery patterns, AND no signs of historical success.

3. INACTIVE: Tokens that never gained meaningful traction.

4. UNSUCCESSFUL: Tokens that don't meet success criteria but aren't clear rugpulls.

Key Improvements:
- A new "Historical Success" category that prioritizes massive past performance.
- Recovery-based success is now more lenient and not penalized by current price trends.
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
pipeline_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "on_chain_solana_pipeline")
sys.path.insert(0, pipeline_dir)

# Also add config subdirectory to path
config_dir = os.path.join(pipeline_dir, "config")
sys.path.insert(0, config_dir)

from onchain_provider import OnChainDataProvider
from config_loader import load_config

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
    launch_price: Optional[float] = None
    peak_price_72h: Optional[float] = None
    post_ath_peak_price: Optional[float] = None
    ath_72h_sustained: bool = False
    has_sustained_drop: bool = False
    price_drops: List[Tuple[datetime, float]] = None
    holder_count: Optional[int] = None
    
    # Enhanced metrics for better classification
    early_phase_drops: List[Tuple[datetime, float, float]] = None  # (time, drop_pct, recovery_ratio)
    late_phase_drops: List[Tuple[datetime, float, float]] = None   # (time, drop_pct, recovery_ratio)
    max_recovery_after_drop: Optional[float] = None  # Best recovery ratio after any major drop
    rapid_drops_count: int = 0  # Number of rapid (< 2h) major drops
    days_since_last_major_drop: Optional[int] = None
    has_shown_recovery: bool = False  # Has recovered significantly after any major drop
    current_trend: Optional[str] = None  # "recovering", "declining", "stable"
    
    # New mega-success metrics
    mega_appreciation: Optional[float] = None  # Total appreciation from launch to ATH
    current_vs_ath_ratio: Optional[float] = None  # Current price as % of ATH
    total_major_drops: int = 0  # Total count of major drops
    final_evaluation_score: Optional[float] = None  # Overall success score
    volume_drop_24h_after_peak: bool = False  # Volume dropped significantly after peak

    def __post_init__(self):
        if self.price_drops is None:
            self.price_drops = []
        if self.early_phase_drops is None:
            self.early_phase_drops = []
        if self.late_phase_drops is None:
            self.late_phase_drops = []

# ─────────────────────── Enhanced TokenLabeler ───────────────────────
class EnhancedTokenLabeler:
    """
    Precision Token Classification Algorithm for ML Training Data
    
    Designed to create the highest quality dataset for ML prediction based on 72h data.
    Each classification has strict, unambiguous criteria to minimize mislabeling.
    
    SUCCESSFUL: Tokens with proven sustained growth patterns
    RUGPULL: Coordinated dumps with clear malicious intent  
    INACTIVE: Tokens that never gained meaningful traction
    UNSUCCESSFUL: Everything else (failed attempts at success)
    """
    
    # === CORE SUCCESS CRITERIA ===
    # Primary success: 72h performance + sustainability
    SUCCESS_72H_MIN_GAIN = 5.0  # Minimum 5x gain from launch to 72h peak
    SUCCESS_72H_SUSTAINABILITY_DAYS = 7  # Must sustain for 1 week after 72h
    SUCCESS_72H_MIN_RETENTION = 0.40  # Must retain at least 40% of 72h gains
    SUCCESS_MIN_HOLDERS_PRIMARY = 100  # Strong community indicator
    SUCCESS_MIN_VOLUME_PRIMARY = 50000  # $50k+ volume shows real activity
    
    # Secondary success: Recovery-based patterns
    SUCCESS_RECOVERY_MIN_DROP = 0.70  # Must have dropped 70%+ to qualify for recovery
    SUCCESS_RECOVERY_MULTIPLIER = 8.0  # Must recover 8x+ from drop low
    SUCCESS_RECOVERY_SUSTAINABILITY = 14  # Recovery must be sustained 2 weeks
    SUCCESS_MIN_HOLDERS_RECOVERY = 75  # Slightly lower for recovery cases
    
    # Mega success: Exceptional historical performance
    SUCCESS_MEGA_APPRECIATION = 1000.0  # 1000x+ total appreciation
    SUCCESS_MEGA_CURRENT_RATIO = 0.001  # Must retain 0.1%+ of peak for mega
    SUCCESS_LEGENDARY_APPRECIATION = 100000.0  # 100,000x+ overrides most criteria
    
    # === RUGPULL DETECTION ===
    # Coordinated drop patterns
    RUG_DROP_THRESHOLD = 0.85  # 85%+ drop from recent peak
    RUG_RAPID_DROP_HOURS = 6  # Within 6 hours indicates coordination
    RUG_MIN_APPRECIATION_FOR_RUG = 10.0  # Must have pumped first (10x+)
    RUG_FINAL_PRICE_RATIO = 0.005  # Final price <0.5% of ATH
    RUG_VOLUME_DROP_RATIO = 0.30  # Volume drops <30% of peak volume
    RUG_MIN_DROPS_FOR_PATTERN = 3  # Multiple coordinated dumps
    RUG_NO_RECOVERY_DAYS = 30  # No meaningful recovery for 30+ days
    
    # === INACTIVE CRITERIA ===  
    INACTIVE_MAX_APPRECIATION = 3.0  # Never gained more than 3x
    INACTIVE_MAX_HOLDERS = 25  # Very few holders
    INACTIVE_MAX_VOLUME = 50  # <$50 daily volume
    INACTIVE_MAX_PEAK_RATIO = 1.5  # Peak never exceeded 1.5x launch price
    INACTIVE_MAX_DAYS_ACTIVE = 7  # No activity after first week
    
    # === ANALYSIS PARAMETERS ===
    EARLY_PHASE_DAYS = 14  # First 2 weeks are "early phase"
    RECOVERY_ANALYSIS_DAYS = 60  # Look 60 days ahead for recovery
    TREND_ANALYSIS_DAYS = 14  # Analyze trend over 2 weeks
    VOLUME_CONSISTENCY_THRESHOLD = 0.1  # Volume consistency requirement

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
        """Label tokens from CSV using on-chain data with incremental saving."""
        df = pd.read_csv(inp)
        if "mint_address" not in df.columns:
            raise ValueError("CSV must contain 'mint_address' column")
        mints = df["mint_address"].tolist()

        # Show initial processing stats
        initial_stats = self.get_processing_stats(inp, out)
        logger.info(f"Processing overview: {initial_stats}")

        # Create backup of existing output file
        if os.path.exists(out):
            backup_path = self._create_backup(out)
            if backup_path:
                logger.info(f"Backup created before processing: {backup_path}")

        # Validate existing output file
        processed_mints = set()
        if os.path.exists(out):
            if self._validate_csv_integrity(out):
                try:
                    existing_df = pd.read_csv(out)
                    if "mint_address" in existing_df.columns:
                        processed_mints = set(existing_df["mint_address"].tolist())
                        logger.info(f"Resuming from existing output: {len(processed_mints)} tokens already processed")
                except Exception as e:
                    logger.warning(f"Could not read existing output file: {e}")
            else:
                logger.warning("Existing output file failed validation, starting fresh")
                self._init_output_csv(out, overwrite=True)
                processed_mints = set()

        # Filter out already processed mints
        remaining_mints = [m for m in mints if m not in processed_mints]
        logger.info(f"Processing {len(remaining_mints)} remaining tokens (skipping {len(processed_mints)} already done)")

        # Initialize CSV file with headers if it doesn't exist
        self._init_output_csv(out)

        results: List[Tuple[str, str]] = []
        total_processed = len(processed_mints)
        failed_count = 0
        
        try:
            for i in range(0, len(remaining_mints), batch):
                chunk = remaining_mints[i:i + batch]
                logger.info("Batch %d/%d (size=%d), total processed: %d/%d, failed: %d", 
                           i // batch + 1, (len(remaining_mints) + batch - 1) // batch, 
                           len(chunk), total_processed, len(mints), failed_count)
                
                # Process tokens one by one for incremental saving
                for mint in chunk:
                    try:
                        result = await self._process(mint)
                        if result is not None:
                            results.append(result)
                            # Write immediately to CSV
                            self._append_to_csv(out, result)
                            total_processed += 1
                            logger.info(f"✓ {mint} → {result[1]} (progress: {total_processed}/{len(mints)})")
                        else:
                            logger.info(f"✗ {mint} → skipped (no data)")
                    except Exception as e:
                        failed_count += 1
                        logger.error(f"✗ {mint} → error: {e}")
                        # Continue processing other tokens even if one fails
                        continue
                
                # Validate CSV integrity periodically (every 10 batches)
                if (i // batch + 1) % 10 == 0:
                    if not self._validate_csv_integrity(out):
                        logger.error("CSV integrity check failed during processing!")
                
                if i + batch < len(remaining_mints):
                    await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("Processing interrupted by user. Progress has been saved to CSV.")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during processing: {e}")
            logger.info("Progress has been saved to CSV up to this point.")
            raise

        # Load final results from file (includes both existing and new results)
        if os.path.exists(out):
            final_df = pd.read_csv(out)
            final_stats = self.get_processing_stats(inp, out)
            logger.info(f"Completed labeling process. Final stats: {final_stats}")
            logger.info(f"Output saved to: {out}")
            return final_df
        else:
            logger.error("Output file not found after processing!")
            return pd.DataFrame(columns=["mint_address", "label"])

    def _init_output_csv(self, output_path: str, overwrite: bool = False) -> None:
        """Initialize CSV file with headers if it doesn't exist or if overwrite is True."""
        if overwrite or not os.path.exists(output_path):
            pd.DataFrame(columns=["mint_address", "label"]).to_csv(output_path, index=False)
            if overwrite:
                logger.info(f"Re-initialized (overwrote) output CSV file: {output_path}")
            else:
                logger.info(f"Initialized output CSV file: {output_path}")

    def _append_to_csv(self, output_path: str, result: Tuple[str, str]) -> None:
        """Append a single result to the CSV file."""
        try:
            # Create a DataFrame with the single result
            result_df = pd.DataFrame([result], columns=["mint_address", "label"])
            
            # Append to existing file
            result_df.to_csv(output_path, mode='a', header=False, index=False)
        except Exception as e:
            logger.error(f"Failed to append result to CSV: {e}")
            # Fall back to in-memory storage if file writing fails

    def _create_backup(self, output_path: str) -> str:
        """Create a backup of the current output file."""
        if os.path.exists(output_path):
            backup_path = f"{output_path}.backup_{int(time.time())}"
            try:
                import shutil
                shutil.copy2(output_path, backup_path)
                logger.info(f"Created backup: {backup_path}")
                return backup_path
            except Exception as e:
                logger.warning(f"Failed to create backup: {e}")
        return ""

    def _validate_csv_integrity(self, output_path: str) -> bool:
        """Validate that the CSV file is readable and has correct structure."""
        try:
            if not os.path.exists(output_path):
                return False
            
            df = pd.read_csv(output_path)
            required_columns = ["mint_address", "label"]
            
            if not all(col in df.columns for col in required_columns):
                logger.error(f"CSV missing required columns: {required_columns}")
                return False
            
            # Check for duplicate mint addresses
            duplicates = df["mint_address"].duplicated().sum()
            if duplicates > 0:
                logger.warning(f"Found {duplicates} duplicate mint addresses in CSV")
            
            logger.info(f"CSV validation passed: {len(df)} records")
            return True
            
        except Exception as e:
            logger.error(f"CSV validation failed: {e}")
            return False

    def get_processing_stats(self, input_path: str, output_path: str) -> Dict[str, int]:
        """Get statistics about processing progress."""
        stats = {"total": 0, "completed": 0, "remaining": 0, "skipped": 0}
        
        try:
            # Get total from input
            input_df = pd.read_csv(input_path)
            stats["total"] = len(input_df)
            
            # Get completed from output
            if os.path.exists(output_path):
                output_df = pd.read_csv(output_path)
                stats["completed"] = len(output_df)
                stats["remaining"] = max(0, stats["total"] - stats["completed"])
            else:
                stats["remaining"] = stats["total"]
                
        except Exception as e:
            logger.error(f"Failed to get processing stats: {e}")
            
        return stats

    # ────────── Per‑token flow ──────────
    async def _process(self, mint: str) -> Optional[Tuple[str, str]]:
        m = await self._gather_metrics(mint)
        if not self._has_any_data(m):
            logger.info("%s – skipped (no on-chain data)", mint)
            return None
        label = self._classify(m)
        self._log_classification_reasoning(m, label)  # Log the reasoning
        return mint, label

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
            t.launch_price = hist_data.launch_price
            t.peak_price_72h = hist_data.peak_price_72h
            t.post_ath_peak_price = hist_data.post_ath_peak_price
            
            # Calculate mega-success metrics with fallback strategies
            if t.launch_price and t.post_ath_peak_price and t.launch_price > 0:
                t.mega_appreciation = t.post_ath_peak_price / t.launch_price
                logger.debug(f"{mint}: mega_appreciation = {t.post_ath_peak_price} / {t.launch_price} = {t.mega_appreciation}")
            elif t.peak_price_72h and t.post_ath_peak_price and t.peak_price_72h > 0:
                # Fallback: Use 72h peak as proxy for launch if launch price missing
                fallback_appreciation = t.post_ath_peak_price / t.peak_price_72h
                logger.debug(f"{mint}: Using 72h peak as launch proxy: {t.post_ath_peak_price} / {t.peak_price_72h} = {fallback_appreciation}")
                if fallback_appreciation >= 1.0:  # Only if ATH >= 72h peak (makes sense)
                    t.mega_appreciation = fallback_appreciation
            else:
                logger.debug(f"{mint}: Cannot calculate mega_appreciation - launch_price: {t.launch_price}, post_ath_peak_price: {t.post_ath_peak_price}, peak_72h: {t.peak_price_72h}")
            
            if t.current_price and t.post_ath_peak_price and t.post_ath_peak_price > 0:
                t.current_vs_ath_ratio = t.current_price / t.post_ath_peak_price
                logger.debug(f"{mint}: current_vs_ath_ratio = {t.current_price} / {t.post_ath_peak_price} = {t.current_vs_ath_ratio}")
            else:
                logger.debug(f"{mint}: Cannot calculate current_vs_ath_ratio - current_price: {t.current_price}, post_ath_peak_price: {t.post_ath_peak_price}")
                
            # Emergency fallback calculations for critical missing data
            if not t.mega_appreciation and t.current_price and t.peak_price_72h and t.current_price > 0:
                # If we have current price and 72h peak, estimate appreciation
                estimated_appreciation = t.peak_price_72h / t.current_price
                logger.debug(f"{mint}: Emergency appreciation estimate from current price: {estimated_appreciation}")
                if estimated_appreciation > 1:  # Only if makes sense
                    t.mega_appreciation = estimated_appreciation
            
            # Analyze historical data for drops and patterns
            hist_metrics = self._historical_metrics_from_ohlcv(hist_data.ohlcv or [])
            t.has_sustained_drop = hist_metrics.get("has_sustained_drop", False)
            t.price_drops = hist_metrics.get("price_drops", [])
            t.early_phase_drops = hist_metrics.get("early_phase_drops", [])
            t.late_phase_drops = hist_metrics.get("late_phase_drops", [])
            t.max_recovery_after_drop = hist_metrics.get("max_recovery_after_drop", 0.0)
            t.rapid_drops_count = hist_metrics.get("rapid_drops_count", 0)
            t.days_since_last_major_drop = hist_metrics.get("days_since_last_major_drop")
            t.has_shown_recovery = hist_metrics.get("has_shown_recovery", False)
            t.current_trend = hist_metrics.get("current_trend", "stable")
            t.total_major_drops = len(t.price_drops)
            t.ath_72h_sustained = hist_metrics.get("ath_72h_sustained", False)
            t.volume_drop_24h_after_peak = hist_metrics.get("volume_drop_24h_after_peak", False)
            
            # Override launch price if we got a better one from OHLCV analysis
            ohlcv_launch_price = hist_metrics.get("launch_price")
            if ohlcv_launch_price and not t.launch_price:
                t.launch_price = ohlcv_launch_price
                logger.debug(f"{mint}: Using OHLCV launch price: {ohlcv_launch_price}")
                
                # Recalculate mega_appreciation if we now have launch price
                if t.post_ath_peak_price and t.launch_price > 0:
                    t.mega_appreciation = t.post_ath_peak_price / t.launch_price
                    logger.debug(f"{mint}: Recalculated mega_appreciation = {t.mega_appreciation}")
            
            # Final fallback: If still no launch price, estimate from OHLCV or use 72h peak as proxy
            if not t.launch_price and hist_metrics.get("estimated_launch_price"):
                t.launch_price = hist_metrics.get("estimated_launch_price")
                logger.debug(f"{mint}: Using estimated launch price: {t.launch_price}")
                
                # Recalculate with estimated launch price
                if t.post_ath_peak_price and t.launch_price > 0:
                    t.mega_appreciation = t.post_ath_peak_price / t.launch_price
                    logger.debug(f"{mint}: Recalculated mega_appreciation with estimated launch = {t.mega_appreciation}")
            
            # Ensure we have volume data for community adoption checks
            if not t.volume_24h and hist_metrics.get("average_volume"):
                t.volume_24h = hist_metrics.get("average_volume")
                logger.debug(f"{mint}: Using historical average volume: {t.volume_24h}")
            
            # Calculate final evaluation score (ensure it's never None)
            t.final_evaluation_score = self._calculate_success_score(t)
            if t.final_evaluation_score is None:
                logger.warning(f"Success score calculation returned None for {mint}, setting to 0.0")
                t.final_evaluation_score = 0.0
        else:
            logger.debug(f"{mint}: No historical data available")

        # 3. Holder count
        t.holder_count = await self.data_provider.get_holder_count(mint)
        
        return t

    def _historical_metrics_from_ohlcv(self, ohlcv: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Enhanced OHLCV analysis to detect sophisticated patterns including:
        - Early vs late phase drops
        - Recovery patterns after major drops
        - Rapid vs gradual drops
        - Current trend analysis
        """
        if not ohlcv:
            return {
                "has_sustained_drop": False,
                "price_drops": [],
                "early_phase_drops": [],
                "late_phase_drops": [],
                "max_recovery_after_drop": 0.0,
                "rapid_drops_count": 0,
                "days_since_last_major_drop": None,
                "has_shown_recovery": False,
                "current_trend": "stable",
                "ath_72h_sustained": False,
                "volume_drop_24h_after_peak": False
            }

        # Convert to DataFrame
        df = pd.DataFrame(ohlcv)
        df["t"] = pd.to_datetime(df["ts"], unit="s")
        df.sort_values("t", inplace=True)
        
        if df.empty:
            return {}

        launch = df["t"].iloc[0]
        now = df["t"].iloc[-1]
        early_phase_end = launch + timedelta(days=self.EARLY_PHASE_DAYS)
        ath_3d_end = launch + timedelta(seconds=THREE_DAYS_SEC)
        
        # Find 72h ATH
        ath_3d_df = df.loc[df["t"] <= ath_3d_end]
        if ath_3d_df.empty:
            return {}
        ath_3d = ath_3d_df["h"].max()
        
        # Check if ATH within 72 hours is sustained for at least one week
        ath_72h_sustained = False
        if ath_3d > 0:
            # Find the time when ATH was reached
            ath_time = ath_3d_df.loc[ath_3d_df["h"] == ath_3d, "t"].max()
            
            # Check prices for one week after ATH was set
            sustain_end = ath_time + timedelta(seconds=SUSTAIN_DAYS_SEC)
            sustain_df = df.loc[(df["t"] >= ath_time) & (df["t"] <= sustain_end)]
            
            if not sustain_df.empty:
                # Check if all prices in this period are above the 72h ATH
                if (sustain_df["l"] >= ath_3d).all():
                    ath_72h_sustained = True

        # Post-72h data
        post_df = df.loc[df["t"] > ath_3d_end]
        if post_df.empty:
            return {}
        post_peak = post_df["h"].max()

        # Initialize tracking variables
        roll: deque[Tuple[datetime, float]] = deque()
        bad, drops = False, []
        early_drops, late_drops = [], []
        rapid_drops_count = 0
        max_recovery = 0.0
        has_recovery = False
        volume_drop_24h_after_peak = False
        
        # Track drops and recoveries
        drop_low_tracker = {}  # track lowest point after each major drop
        
        for i, row in post_df.iterrows():
            ts = row["t"]
            
            # Maintain 7-day rolling window
            while roll and (ts - roll[0][0]).total_seconds() > SUSTAIN_DAYS_SEC:
                roll.popleft()
            
            roll.append((ts, row["h"]))
            window_peak = max(h for _, h in roll)
            drop_pct = 1 - row["l"] / window_peak if window_peak else 0
            
            # Track sustained drops (existing logic)
            if drop_pct >= 0.5:
                bad = True
            
            # Enhanced drop analysis - now using 85% threshold
            if drop_pct >= 0.85:  # Use class constant RUG_DROP_THRESHOLD
                is_early_phase = ts <= early_phase_end
                
                # Check if this is a rapid drop (within 6 hours of peak)
                hours_since_peak = min((ts - peak_time).total_seconds() / 3600 
                                     for peak_time, peak_val in roll if peak_val == window_peak)
                is_rapid = hours_since_peak <= 6  # Use class constant RUG_RAPID_DROP_HOURS
                
                if is_rapid:
                    rapid_drops_count += 1
                
                # Record the drop with its low point
                drop_id = f"{ts}_{drop_pct}"
                drop_low_tracker[drop_id] = {
                    'low': row["l"],
                    'time': ts,
                    'drop_pct': drop_pct,
                    'is_early': is_early_phase,
                    'is_rapid': is_rapid
                }
                
                drops.append((ts.to_pydatetime(), drop_pct))

                # Enhanced Volume Analysis for Rugpull Detection
                peak_time_for_volume = ts
                volume_at_peak = row["v"]
                
                # Get volume 24 hours after the peak
                volume_24h_after_peak_time = peak_time_for_volume + timedelta(hours=24)
                volume_24h_after_peak_df = df.loc[(df["t"] > peak_time_for_volume) & (df["t"] <= volume_24h_after_peak_time)]
                
                if not volume_24h_after_peak_df.empty and volume_at_peak > 0:
                    # Average volume in the 24 hours after the peak
                    avg_volume_24h_after = volume_24h_after_peak_df["v"].mean()
                    
                    # Check for significant volume drop (>60% reduction)
                    if avg_volume_24h_after < (volume_at_peak * 0.4):
                        volume_drop_24h_after_peak = True
                
        # Analyze recovery patterns with enhanced criteria
        for drop_id, drop_info in drop_low_tracker.items():
            drop_low = drop_info['low']
            drop_time = drop_info['time']
            
            # Look for recovery in the following 60 days (extended window)
            recovery_window = drop_time + timedelta(days=60)
            recovery_df = post_df.loc[(post_df["t"] > drop_time) & (post_df["t"] <= recovery_window)]
            
            if not recovery_df.empty:
                max_price_after = recovery_df["h"].max()
                recovery_ratio = max_price_after / drop_low if drop_low > 0 else 0
                
                # More sophisticated recovery analysis
                # Check if recovery was sustained (not just a temporary spike)
                recovery_peak_time = recovery_df.loc[recovery_df["h"] == max_price_after, "t"].iloc[0]
                
                # Check price 7 days after recovery peak
                sustain_window = recovery_peak_time + timedelta(days=7)
                sustain_df = recovery_df.loc[(recovery_df["t"] >= recovery_peak_time) & 
                                           (recovery_df["t"] <= sustain_window)]
                
                recovery_sustained = False
                if not sustain_df.empty:
                    # Recovery is sustained if price doesn't drop more than 50% from recovery peak
                    min_price_after_recovery = sustain_df["l"].min()
                    retention_ratio = min_price_after_recovery / max_price_after if max_price_after > 0 else 0
                    recovery_sustained = retention_ratio >= 0.5
                
                # Update recovery metrics
                max_recovery = max(max_recovery, recovery_ratio)
                
                # More stringent recovery requirements
                if recovery_ratio >= 8.0 and recovery_sustained:  # 8x recovery that was sustained
                    has_recovery = True
                
                # Categorize drops by phase with recovery info
                drop_entry = (drop_time.to_pydatetime(), drop_info['drop_pct'], recovery_ratio)
                if drop_info['is_early']:
                    early_drops.append(drop_entry)
                else:
                    late_drops.append(drop_entry)
        
        # Determine current trend (last 7 days)
        recent_df = df.loc[df["t"] >= (now - timedelta(days=7))]
        current_trend = "stable"
        if len(recent_df) >= 2:
            recent_start = recent_df["c"].iloc[0]
            recent_end = recent_df["c"].iloc[-1]
            change_pct = (recent_end - recent_start) / recent_start if recent_start > 0 else 0
            
            if change_pct > 0.2:
                current_trend = "recovering"
            elif change_pct < -0.2:
                current_trend = "declining"
        
        # Calculate days since last major drop
        days_since_last_drop = None
        if drops:
            last_drop_time = max(drop_time for drop_time, _ in drops)
            days_since_last_drop = (now - pd.to_datetime(last_drop_time)).days

        return {
            "has_sustained_drop": bad,
            "price_drops": drops,
            "early_phase_drops": early_drops,
            "late_phase_drops": late_drops,
            "max_recovery_after_drop": max_recovery,
            "rapid_drops_count": rapid_drops_count,
            "days_since_last_major_drop": days_since_last_drop,
            "has_shown_recovery": has_recovery,
            "current_trend": current_trend,
            "ath_72h_sustained": ath_72h_sustained,
            "launch_price": df["c"].iloc[0] if not df.empty else None,
            "volume_drop_24h_after_peak": volume_drop_24h_after_peak,
            # Additional data for fallback calculations
            "estimated_launch_price": self._estimate_launch_price(df),
            "average_volume": df["v"].mean() if not df.empty else None,
            "peak_volume": df["v"].max() if not df.empty else None,
            "recent_volume": df["v"].tail(7).mean() if len(df) >= 7 else None
        }

    # ---------- Enhanced Classification Algorithm ------------------
    def _classify(self, m: TokenMetrics) -> str:
        """
        Ultra-precise classification algorithm for ML training data.
        
        Order of precedence (most important first):
        1. Historical mega-success (overrides everything)
        2. Clear coordinated rugpulls 
        3. True inactivity (never gained traction)
        4. 72h sustained success patterns
        5. Recovery-based success patterns
        6. Everything else = unsuccessful
        """
        
        # PHASE 1: Historical mega-success check (highest priority)
        # These tokens had legendary performance and should always be successful
        if self._is_legendary_historical_success(m):
            return "successful"
        
        # PHASE 2: Clear rugpull patterns (second priority)
        # Must be identified before other classifications to avoid false negatives
        if self._is_coordinated_rugpull(m):
            return "rugpull"
        
        # PHASE 3: True inactivity check (third priority)
        # Only tokens that truly never gained any meaningful traction
        if self._is_truly_inactive(m):
            return "inactive"
        
        # PHASE 4: Primary success patterns (72h + sustainability)
        # The main success criteria - strong 72h performance that was sustained
        if self._is_72h_sustained_success(m):
            return "successful"
        
        # PHASE 5: Secondary success patterns (recovery-based)
        # Tokens that recovered strongly after major setbacks
        if self._is_recovery_based_success(m):
            return "successful"
        
        # PHASE 6: Mega appreciation without sustainability
        # High appreciation but couldn't sustain - still successful due to magnitude
        if self._is_mega_appreciation_success(m):
            return "successful"
        
        # PHASE 7: Default classification
        # Everything else that doesn't meet success, rugpull, or inactive criteria
        return "unsuccessful"

    def _is_legendary_historical_success(self, m: TokenMetrics) -> bool:
        """
        Identifies tokens with legendary historical performance that overrides all other factors.
        CRITICAL: These must have SUSTAINED value, not just extreme appreciation followed by collapse.
        """
        # NEW CRITICAL RULE: No legendary success if current price is <1% of ATH with dead volume
        # This prevents rugpulls from being classified as legendary successes
        if (m.current_vs_ath_ratio is not None and m.current_vs_ath_ratio < 0.01 and
            m.volume_24h is not None and m.volume_24h < 5000):
            logger.debug(f"Blocking legendary success: collapsed to {m.current_vs_ath_ratio:.4%} with ${m.volume_24h} volume")
            return False
        
        # Criterion 1: Extreme recovery performance (1M+ recovery from major drops)
        # BUT must still retain reasonable value
        if m.max_recovery_after_drop and m.max_recovery_after_drop >= 1_000_000:
            # Additional check: must retain at least 5% of ATH for recovery to count
            if m.current_vs_ath_ratio and m.current_vs_ath_ratio >= 0.05:
                logger.info(f"Legendary success: {m.max_recovery_after_drop:.0f}x recovery with {m.current_vs_ath_ratio:.2%} retention")
                return True
        
        # Criterion 2: Ultra-mega appreciation (100,000x+) with SIGNIFICANT retention
        if (m.mega_appreciation and m.mega_appreciation >= self.SUCCESS_LEGENDARY_APPRECIATION):
            # Much stricter retention requirements for mega appreciation
            if m.current_vs_ath_ratio is None:
                # Without retention data, require very strong community indicators
                if (m.holder_count and m.holder_count >= 500 and 
                    m.volume_24h and m.volume_24h >= 50000):
                    logger.info(f"Legendary success: {m.mega_appreciation:.0f}x appreciation with strong community")
                    return True
            elif m.current_vs_ath_ratio >= 0.1:  # Must retain at least 10% of ATH
                logger.info(f"Legendary success: {m.mega_appreciation:.0f}x appreciation with {m.current_vs_ath_ratio:.2%} retention")
                return True
        
        # Criterion 3: Combination of high appreciation + strong recovery + retention
        if (m.mega_appreciation and m.mega_appreciation >= 50000 and
            m.max_recovery_after_drop and m.max_recovery_after_drop >= 1000 and
            m.current_vs_ath_ratio and m.current_vs_ath_ratio >= 0.05):
            logger.info(f"Legendary success: {m.mega_appreciation:.0f}x appreciation + {m.max_recovery_after_drop:.0f}x recovery with {m.current_vs_ath_ratio:.2%} retention")
            return True
        
        return False

    def _is_coordinated_rugpull(self, m: TokenMetrics) -> bool:
        """
        Detects clear coordinated rugpull patterns with high precision.
        Multiple verification layers to avoid false positives.
        """
        
        # Pattern 1: Classic Mega Rugpull
        # High appreciation → Complete collapse → Dead volume
        if self._is_mega_rugpull_pattern(m):
            return True
        
        # Pattern 2: Multiple Coordinated Dumps
        # Series of rapid, coordinated sell-offs with no recovery
        if self._is_coordinated_dump_pattern(m):
            return True
        
        # Pattern 3: Volume-based Rugpull
        # Significant volume drop immediately after peak + price collapse
        if self._is_volume_based_rugpull(m):
            return True
        
        return False

    def _is_mega_rugpull_pattern(self, m: TokenMetrics) -> bool:
        """
        Detect mega rugpull: high appreciation followed by complete collapse.
        FIXED: More precise thresholds to avoid catching inactive tokens.
        """
        
        # CRITICAL FIX: Minimum appreciation threshold for rugpull classification
        # Tokens with <5x appreciation cannot be rugpulls (they're inactive)
        had_significant_appreciation = False
        
        # Method A: Direct mega appreciation check (must be meaningful)
        if m.mega_appreciation and m.mega_appreciation >= 5.0:  # Minimum 5x for rugpull consideration
            had_significant_appreciation = True
        
        # Method B: Infer from price data (peak vs current) - more conservative
        elif m.current_price and m.post_ath_peak_price and m.current_price > 0:
            implied_appreciation = m.post_ath_peak_price / m.current_price
            if implied_appreciation >= 10.0:  # Higher threshold for inferred appreciation
                had_significant_appreciation = True
                logger.debug(f"Inferred appreciation from collapse: {implied_appreciation:.1f}x")
        
        # Method C: Use 72h peak if available - most conservative
        elif m.current_price and m.peak_price_72h and m.current_price > 0:
            implied_72h_appreciation = m.peak_price_72h / m.current_price
            if implied_72h_appreciation >= 20.0:  # Even higher threshold for 72h data
                had_significant_appreciation = True
                logger.debug(f"Inferred 72h appreciation from collapse: {implied_72h_appreciation:.1f}x")
        
        if not had_significant_appreciation:
            logger.debug(f"Not rugpull: insufficient appreciation (< minimum thresholds)")
            return False
        
        # Pattern 1: Current vs ATH ratio indicates massive collapse
        massive_collapse = (m.current_vs_ath_ratio is not None and 
                          m.current_vs_ath_ratio <= 0.05)  # Less than 5% of ATH
        
        if not massive_collapse:
            logger.debug(f"Not rugpull: insufficient collapse ratio ({m.current_vs_ath_ratio})")
            return False
        
        # Pattern 2: Volume must be dead or very low (indicating abandonment)
        volume_dead = (m.volume_24h is None or m.volume_24h <= 2000)  # Raised threshold
        
        # Pattern 3: Confirmation scoring system
        confirmation_score = 0
        
        # High appreciation with extreme collapse gets base score
        if m.mega_appreciation and m.mega_appreciation >= 50:
            confirmation_score += 1
        
        # Extreme collapse gets extra points
        if m.current_vs_ath_ratio and m.current_vs_ath_ratio <= 0.01:  # <1% of ATH
            confirmation_score += 2
        elif m.current_vs_ath_ratio and m.current_vs_ath_ratio <= 0.02:  # <2% of ATH
            confirmation_score += 1
        
        # Volume death confirmation
        if volume_dead:
            confirmation_score += 1
        
        # Volume dropped significantly after peak
        if m.volume_drop_24h_after_peak:
            confirmation_score += 1
        
        # Multiple major drops with no meaningful recovery
        if m.total_major_drops >= 3 and not m.has_shown_recovery:
            confirmation_score += 1
        
        # High holder count but dead volume = trapped holders (strong indicator)
        if m.holder_count and m.holder_count >= 20 and volume_dead:
            confirmation_score += 1
        
        # Current trend is declining or no trend data (indicating death)
        if m.current_trend == "declining":
            confirmation_score += 1
        
        # RUGPULL DECISION: Need minimum appreciation + collapse + confirmations
        min_confirmations = 3  # Raised threshold for higher precision
        
        if confirmation_score >= min_confirmations:
            implied_appreciation = (m.mega_appreciation or 
                                  (m.post_ath_peak_price / m.current_price if m.current_price and m.post_ath_peak_price else 0))
            logger.info(f"Mega rugpull: {implied_appreciation:.0f}x → {m.current_vs_ath_ratio:.4%}, confirmations: {confirmation_score}")
            return True
        
        logger.debug(f"Not rugpull: insufficient confirmations ({confirmation_score}/{min_confirmations})")
        return False

    def _is_coordinated_dump_pattern(self, m: TokenMetrics) -> bool:
        """Detect pattern of multiple coordinated dumps."""
        if not m.price_drops:
            return False
        
        # Must have multiple major drops
        major_drops = [d for _, d in m.price_drops if d >= self.RUG_DROP_THRESHOLD]
        if len(major_drops) < self.RUG_MIN_DROPS_FOR_PATTERN:
            return False
        
        # Must have multiple rapid drops (coordinated)
        if m.rapid_drops_count < 2:
            return False
        
        # Must not have recovered meaningfully
        if m.has_shown_recovery and m.max_recovery_after_drop and m.max_recovery_after_drop >= 5:
            return False
        
        # Must have been a long time since last major recovery
        if (m.days_since_last_major_drop is None or 
            m.days_since_last_major_drop < self.RUG_NO_RECOVERY_DAYS):
            return False
        
        logger.info(f"Coordinated dump pattern: {len(major_drops)} major drops, {m.rapid_drops_count} rapid")
        return True

    def _is_volume_based_rugpull(self, m: TokenMetrics) -> bool:
        """Detect rugpull based on volume patterns after peak."""
        if not m.volume_drop_24h_after_peak:
            return False
        
        # Must have had some initial appreciation
        if not m.mega_appreciation or m.mega_appreciation < 5:
            return False
        
        # Current volume must be very low
        if not m.volume_24h or m.volume_24h > 500:
            return False
        
        # Current price must be significantly below ATH
        if not m.current_vs_ath_ratio or m.current_vs_ath_ratio > 0.1:
            return False
        
        logger.info(f"Volume-based rugpull: volume dried up after peak, price at {m.current_vs_ath_ratio:.4%} of ATH")
        return True

    def _is_truly_inactive(self, m: TokenMetrics) -> bool:
        """
        Identify tokens that truly never gained any meaningful traction.
        FIXED: More precise criteria to catch tokens misclassified as rugpulls.
        """
        
        # Primary indicator: Never gained significant appreciation
        appreciation_threshold = self.INACTIVE_MAX_APPRECIATION  # 3x
        
        if m.mega_appreciation and m.mega_appreciation > appreciation_threshold:
            logger.debug(f"Not inactive: had {m.mega_appreciation:.1f}x appreciation (> {appreciation_threshold}x threshold)")
            return False
        
        # If no direct appreciation data, try to infer from price patterns
        if not m.mega_appreciation:
            # Check if there's evidence of meaningful price movement
            if m.current_price and m.post_ath_peak_price and m.current_price > 0:
                inferred_appreciation = m.post_ath_peak_price / m.current_price
                if inferred_appreciation > appreciation_threshold:
                    logger.debug(f"Not inactive: inferred {inferred_appreciation:.1f}x appreciation")
                    return False
            
            # Check 72h peak vs current as another indicator
            if m.current_price and m.peak_price_72h and m.current_price > 0:
                peak_appreciation = m.peak_price_72h / m.current_price
                if peak_appreciation > appreciation_threshold:
                    logger.debug(f"Not inactive: 72h peak shows {peak_appreciation:.1f}x appreciation")
                    return False
        
        # Secondary indicators: Very limited community engagement
        very_few_holders = (m.holder_count is not None and 
                           m.holder_count <= self.INACTIVE_MAX_HOLDERS)  # 25 holders
        
        # If holder data missing, be more cautious
        if m.holder_count is None:
            logger.debug(f"Holder data missing, not classifying as inactive")
            return False
        
        # Tertiary indicator: Extremely low activity
        extremely_low_volume = (m.volume_24h is not None and 
                               m.volume_24h <= self.INACTIVE_MAX_VOLUME)  # $50
        
        # If volume data missing, check other indicators
        if m.volume_24h is None:
            # Without volume data, require stricter holder requirements
            if not very_few_holders or m.holder_count > 10:
                logger.debug(f"Volume data missing, not inactive with {m.holder_count} holders")
                return False
        
        # Additional check: Never showed any recovery ability
        never_recovered = not m.has_shown_recovery or (
            m.max_recovery_after_drop is not None and 
            m.max_recovery_after_drop < 2
        )
        
        # Check if token never exceeded launch price significantly
        never_gained_traction = True  # Default assumption
        if m.launch_price and m.peak_price_72h:
            peak_ratio = m.peak_price_72h / m.launch_price
            if peak_ratio > self.INACTIVE_MAX_PEAK_RATIO:  # 1.5x
                never_gained_traction = False
                logger.debug(f"Not inactive: peaked at {peak_ratio:.1f}x launch price")
        elif m.launch_price is None:
            # Without launch price, we can't determine if it gained traction
            # Use appreciation as proxy
            if m.mega_appreciation and m.mega_appreciation > 2:
                never_gained_traction = False
        
        # All key conditions must be true for inactive classification
        conditions = [
            never_gained_traction,
            very_few_holders,
            extremely_low_volume or m.volume_24h is None,  # Missing volume acceptable for inactive
            never_recovered
        ]
        
        inactive_score = sum(conditions)
        total_conditions = len(conditions)
        
        # Require at least 3/4 conditions for inactive classification
        if inactive_score >= 3:
            logger.info(f"Truly inactive: {inactive_score}/{total_conditions} conditions met - peak {m.peak_price_72h/m.launch_price:.1f}x launch (if available), {m.holder_count} holders, ${m.volume_24h or 0:.0f} volume")
            return True
        
        logger.debug(f"Not inactive: only {inactive_score}/{total_conditions} conditions met")
        return False

    def _is_72h_sustained_success(self, m: TokenMetrics) -> bool:
        """
        Primary success pattern: Strong 72h performance that was sustained.
        This is the gold standard for success classification.
        """
        
        # Must have strong 72h performance
        if not self._has_strong_72h_performance(m):
            return False
        
        # Must have sustained that performance
        if not self._has_sustained_performance(m):
            return False
        
        # Must have community adoption indicators
        if not self._has_community_adoption(m):
            return False
        
        # Must not have clear rugpull indicators
        if self._has_rugpull_red_flags(m):
            return False
        
        logger.info(f"72h sustained success: {self._get_72h_gain(m):.1f}x in 72h, sustained")
        return True

    def _has_strong_72h_performance(self, m: TokenMetrics) -> bool:
        """Check if token had strong performance in first 72 hours."""
        # Primary method: Direct calculation with launch price
        if m.launch_price and m.peak_price_72h and m.launch_price > 0:
            gain_72h = m.peak_price_72h / m.launch_price
            return gain_72h >= self.SUCCESS_72H_MIN_GAIN
        
        # Fallback method: Estimate from current price collapse
        # If current price is much lower than 72h peak, infer high initial appreciation
        if m.current_price and m.peak_price_72h and m.current_price > 0:
            # If we're currently far below 72h peak, there must have been significant appreciation
            current_vs_72h_peak = m.current_price / m.peak_price_72h
            if current_vs_72h_peak <= 0.1:  # Current price is <10% of 72h peak
                # Estimate potential launch price that could create this pattern
                estimated_gain = 1 / current_vs_72h_peak  # Inverse gives us the implied gain
                if estimated_gain >= self.SUCCESS_72H_MIN_GAIN:
                    logger.debug(f"Inferred strong 72h performance from collapse pattern: {estimated_gain:.1f}x estimated")
                    return True
        
        return False

    def _has_sustained_performance(self, m: TokenMetrics) -> bool:
        """Check if 72h performance was sustained for required period."""
        # Method 1: Direct ATH 72h sustained flag
        if m.ath_72h_sustained is not None:
            return m.ath_72h_sustained
        
        # Method 2: Check retention ratio
        if m.current_price and m.peak_price_72h and m.launch_price:
            current_gain = m.current_price / m.launch_price
            peak_gain = m.peak_price_72h / m.launch_price
            retention_ratio = current_gain / peak_gain if peak_gain > 0 else 0
            return retention_ratio >= self.SUCCESS_72H_MIN_RETENTION
        
        # Method 3: Check post-ATH performance
        if m.post_ath_peak_price and m.peak_price_72h:
            return m.post_ath_peak_price >= (m.peak_price_72h * self.SUCCESS_72H_MIN_RETENTION)
        
        return False

    def _has_community_adoption(self, m: TokenMetrics) -> bool:
        """Check for indicators of genuine community adoption."""
        # Holder count requirement
        min_holders = self.SUCCESS_MIN_HOLDERS_PRIMARY
        if not m.holder_count or m.holder_count < min_holders:
            return False
        
        # Volume requirement (indicates real trading activity)
        # Be more lenient with volume if we have other strong indicators
        min_volume = self.SUCCESS_MIN_VOLUME_PRIMARY
        
        # If we have very strong appreciation, be more lenient with volume requirements
        if m.mega_appreciation and m.mega_appreciation >= 100:
            min_volume = min_volume // 5  # 5x more lenient for high appreciation tokens
        
        # Accept if volume data is missing but holder count is very high
        if m.volume_24h is None:
            if m.holder_count >= min_holders * 2:  # Double the normal holder requirement
                logger.debug(f"Community adoption: No volume data but high holder count ({m.holder_count})")
                return True
            return False
        
        return m.volume_24h >= min_volume

    def _has_rugpull_red_flags(self, m: TokenMetrics) -> bool:
        """Check for red flags that would disqualify from success."""
        # Too many rapid drops indicates coordination
        if m.rapid_drops_count and m.rapid_drops_count >= 5:
            return True
        
        # Excessive total drops indicates instability
        if m.total_major_drops and m.total_major_drops >= 15:
            return True
        
        # Volume disappeared after peak
        if m.volume_drop_24h_after_peak and m.volume_24h and m.volume_24h < 1000:
            return True
        
        return False

    def _is_recovery_based_success(self, m: TokenMetrics) -> bool:
        """
        Secondary success pattern: Strong recovery after major setbacks.
        For tokens that proved resilience through adversity.
        """
        
        # Must have shown significant recovery
        if not m.has_shown_recovery or not m.max_recovery_after_drop:
            return False
        
        # Recovery must be substantial
        if m.max_recovery_after_drop < self.SUCCESS_RECOVERY_MULTIPLIER:
            return False
        
        # Must have had significant initial drop to qualify for recovery success
        major_drops = [d for _, d in m.price_drops if d >= self.SUCCESS_RECOVERY_MIN_DROP]
        if not major_drops:
            return False
        
        # Must have reasonable community (slightly lower bar for recovery cases)
        min_holders = self.SUCCESS_MIN_HOLDERS_RECOVERY
        if not m.holder_count or m.holder_count < min_holders:
            return False
        
        # Must have sustained the recovery (not just a temporary spike)
        if not self._has_sustained_recovery(m):
            return False
        
        logger.info(f"Recovery-based success: {m.max_recovery_after_drop:.1f}x recovery after {max(major_drops):.1%} drop")
        return True

    def _has_sustained_recovery(self, m: TokenMetrics) -> bool:
        """Check if recovery was sustained, not just a temporary spike."""
        # If current trend is declining, recovery wasn't sustained
        if m.current_trend == "declining":
            return False
        
        # Must not have had major drops recently (recovery should be stable)
        if (m.days_since_last_major_drop is not None and 
            m.days_since_last_major_drop < self.SUCCESS_RECOVERY_SUSTAINABILITY):
            return False
        
        # Current price should still be reasonable vs ATH
        if m.current_vs_ath_ratio is not None and m.current_vs_ath_ratio < 0.01:
            return False
        
        return True

    def _is_mega_appreciation_success(self, m: TokenMetrics) -> bool:
        """
        Success based purely on magnitude of appreciation.
        For tokens with extraordinary appreciation even without perfect sustainability.
        """
        
        if not m.mega_appreciation or m.mega_appreciation < self.SUCCESS_MEGA_APPRECIATION:
            return False
        
        # For mega appreciation, be more lenient with sustainability requirements
        # But still require some retention
        if m.current_vs_ath_ratio is not None and m.current_vs_ath_ratio < self.SUCCESS_MEGA_CURRENT_RATIO:
            return False
        
        # Must have some community adoption
        if m.holder_count is not None and m.holder_count < (self.SUCCESS_MIN_HOLDERS_PRIMARY // 2):
            return False
        
        # Must not be a clear rugpull
        if self._is_mega_rugpull_pattern(m):
            return False
        
        logger.info(f"Mega appreciation success: {m.mega_appreciation:.0f}x total appreciation")
        return True

    def _get_72h_gain(self, m: TokenMetrics) -> float:
        """Helper to get 72h gain ratio."""
        if m.launch_price and m.peak_price_72h and m.launch_price > 0:
            return m.peak_price_72h / m.launch_price
        return 0.0

    def _is_historical_success(self, m: TokenMetrics) -> bool:
        """
        Identifies tokens that had extreme historical success, even if inactive now.
        This overrides most other classifications.
        """
        # Criterion 1: Extraordinary recovery from a drop (e.g., >1,000,000x).
        if m.max_recovery_after_drop and m.max_recovery_after_drop >= 1_000_000:
            return True

        # Criterion 2: Massive appreciation combined with significant recovery.
        if (m.mega_appreciation and m.mega_appreciation >= 100 and
            m.max_recovery_after_drop and m.max_recovery_after_drop >= 100):
            return True
            
        return False

    def _is_inactive(self, m: TokenMetrics) -> bool:
        """
        Check if token is inactive - but ONLY for tokens that never showed success.
        Historically successful tokens should not be penalized for current low activity.
        """
        # Never classify tokens with any significant historical appreciation as inactive
        if m.mega_appreciation and m.mega_appreciation >= 10:  # Even 10x+ should not be inactive
            return False
        
        # Never classify tokens that showed meaningful recovery as inactive
        if m.has_shown_recovery and m.max_recovery_after_drop and m.max_recovery_after_drop >= 2:
            return False
        
        # Never classify tokens with reasonable holder base as inactive (shows community)
        if m.holder_count and m.holder_count >= 50:  # Lowered threshold for community
            return False
        
        # Only classify as inactive if the token truly never gained traction:
        # 1. Very low appreciation (< 10x)
        # 2. Very few holders (< 20)
        # 3. Extremely low current volume (< $10) indicating complete abandonment
        
        low_appreciation = not m.mega_appreciation or m.mega_appreciation < 10
        very_few_holders = m.holder_count is not None and m.holder_count < 20
        completely_dead = m.volume_24h is not None and m.volume_24h < 10
        
        # New rule: Never exceeded launch price
        never_exceeded_launch = False
        if m.launch_price is not None and m.peak_price_72h is not None:
            if m.peak_price_72h <= m.launch_price:
                never_exceeded_launch = True

        # Only mark as inactive if it never gained any meaningful traction
        return low_appreciation and very_few_holders and completely_dead and never_exceeded_launch

    def _is_mega_success(self, m: TokenMetrics) -> bool:
        """
        Detect mega-successful tokens (1000x+ appreciation).
        These are almost always successful regardless of volatility.
        """
        # Check for mega appreciation even if other metrics are None
        if m.mega_appreciation and m.mega_appreciation >= self.SUCCESS_MEGA_APPRECIATION:
            # For extremely high appreciation (>100,000x), be very lenient with current price
            if m.mega_appreciation >= 100000:
                if m.current_vs_ath_ratio is None or m.current_vs_ath_ratio >= 0.0001:  # 0.01% of ATH or None
                    return True
            # For very high appreciation (>10,000x), be moderately lenient
            elif m.mega_appreciation >= 10000:
                if m.current_vs_ath_ratio is None or m.current_vs_ath_ratio >= 0.001:  # 0.1% of ATH or None
                    return True
            # For standard mega success (>1,000x), use normal requirements but be lenient if no ATH data
            else:
                if m.current_vs_ath_ratio is None:
                    # If we don't have ATH ratio but have mega appreciation, consider other factors
                    if m.holder_count and m.holder_count >= self.SUCCESS_MIN_HOLDERS:
                        return True
                elif m.current_vs_ath_ratio >= self.SUCCESS_SUSTAINED_HIGH_RATIO:
                    return True
        
        # Use success score for borderline cases (ensuring score is not None)
        if m.final_evaluation_score is not None and m.final_evaluation_score >= 0.7:
            return True
        
        return False

    def _is_traditional_success(self, m: TokenMetrics) -> bool:
        """Traditional success criteria (10x+ with no major sustained drops)."""
        # Check required metrics - allow some to be None
        if m.holder_count is None or m.holder_count < self.SUCCESS_MIN_HOLDERS:
            return False
        
        # Check for ATH sustained requirement if available
        if m.ath_72h_sustained is not None and not m.ath_72h_sustained:
            return False
        
        # Traditional success: 10x+ appreciation without sustained drops
        # Use either peak_price_72h or post_ath_peak_price comparison
        appreciation_ratio = None
        if m.peak_price_72h and m.post_ath_peak_price and m.peak_price_72h > 0:
            appreciation_ratio = m.post_ath_peak_price / m.peak_price_72h
        elif m.launch_price and m.post_ath_peak_price and m.launch_price > 0:
            # Alternative: compare ATH to launch price
            appreciation_ratio = m.post_ath_peak_price / m.launch_price
        
        if appreciation_ratio and appreciation_ratio >= self.SUCCESS_APPRECIATION:
            # Check if there were no sustained drops (if data available)
            if m.has_sustained_drop is not None:
                return not m.has_sustained_drop
            else:
                # If we don't have drop data, consider it successful if appreciation is high enough
                return True
        
        return False

    def _is_recovery_success(self, m: TokenMetrics) -> bool:
        """
        Recovery-based success: Token that recovered well after drops.
        """
        if not m.has_shown_recovery or m.max_recovery_after_drop is None:
            return False
        
        # Strong recovery with reasonable holder count
        holder_requirement = self.SUCCESS_MIN_HOLDERS // 2  # Half the normal requirement
        if m.holder_count is None:
            # If no holder data, be more lenient with recovery requirements
            return m.max_recovery_after_drop >= self.SUCCESS_RECOVERY_MULTIPLIER * 2  # Double the recovery requirement
        
        if (m.max_recovery_after_drop >= self.SUCCESS_RECOVERY_MULTIPLIER and
            m.holder_count >= holder_requirement):
            return True
        
        return False

    def _is_clear_rugpull(self, m: TokenMetrics) -> bool:
        """
        Enhanced rugpull detection covering multiple patterns:
        1. Traditional: Multiple major drops with no recovery
        2. Mega rugpull: Massive appreciation followed by complete collapse
        """
        
        # Pattern 1: Mega Rugpull Detection
        # High appreciation followed by complete collapse (classic pump and dump)
        if (m.mega_appreciation and m.mega_appreciation >= 1000 and  # Had significant appreciation
            m.current_vs_ath_ratio is not None and m.current_vs_ath_ratio <= 0.001 and  # Current price < 0.1% of ATH
            m.volume_24h is not None and m.volume_24h < 100):  # Very low current volume
            
            # Additional confirmation: High holder count but no volume indicates trapped holders
            if m.holder_count and m.holder_count >= 50:
                return True
            
            # Or if mega appreciation is extremely high (100k+), even with fewer holders
            if m.mega_appreciation >= 100000:
                return True
        
        # Pattern 2: Traditional rugpull detection (multiple drops)
        if m.price_drops:
            # Must have drops above the higher threshold (85%)
            major_drops = [d for _, d in m.price_drops if d >= self.RUG_THRESHOLD]
            if major_drops:
                # Must have many major drops (indicating pattern, not volatility)
                if m.total_major_drops >= self.RUG_MIN_DROPS_FOR_PATTERN:
                    # Current price must be very low vs ATH (indicating no recovery)
                    if not m.current_vs_ath_ratio or m.current_vs_ath_ratio < self.RUG_FINAL_PRICE_RATIO:
                        # Multiple rapid coordinated dumps or significant volume drop after peak
                        if m.rapid_drops_count >= 3 or m.volume_drop_24h_after_peak:
                            return True
                        
                        # Many drops with very long time without recovery and declining trend
                        if (m.total_major_drops >= 10 and 
                            m.days_since_last_major_drop and m.days_since_last_major_drop >= self.RUG_NO_RECOVERY_DAYS and
                            m.current_trend == "declining"):
                            return True
        
        return False

    def _calculate_success_score(self, m: TokenMetrics) -> float:
        """
        Calculate a comprehensive success score considering all factors.
        Score ranges from 0.0 to 1.0, with >0.7 indicating strong success.
        
        Weighted scoring system:
        - Historical appreciation (40% weight)
        - Price sustainability (25% weight) 
        - Community adoption (20% weight)
        - Recovery resilience (10% weight)
        - Current momentum (5% weight)
        """
        score = 0.0
        
        # 1. Historical Appreciation Score (40% weight, max 0.4)
        appreciation_score = 0.0
        if m.mega_appreciation:
            if m.mega_appreciation >= 100000:      # 100,000x+ = perfect
                appreciation_score = 0.4
            elif m.mega_appreciation >= 50000:     # 50,000x+ = excellent  
                appreciation_score = 0.35
            elif m.mega_appreciation >= 10000:     # 10,000x+ = very good
                appreciation_score = 0.3
            elif m.mega_appreciation >= 5000:      # 5,000x+ = good
                appreciation_score = 0.25
            elif m.mega_appreciation >= 1000:      # 1,000x+ = decent
                appreciation_score = 0.2
            elif m.mega_appreciation >= 500:       # 500x+ = moderate
                appreciation_score = 0.15
            elif m.mega_appreciation >= 100:       # 100x+ = basic
                appreciation_score = 0.1
            elif m.mega_appreciation >= 50:        # 50x+ = minimal
                appreciation_score = 0.05
        score += appreciation_score
        
        # 2. Price Sustainability Score (25% weight, max 0.25)
        sustainability_score = 0.0
        if m.current_vs_ath_ratio is not None:
            if m.current_vs_ath_ratio >= 0.5:      # 50%+ of ATH = excellent sustainability
                sustainability_score = 0.25
            elif m.current_vs_ath_ratio >= 0.25:   # 25%+ of ATH = very good
                sustainability_score = 0.2
            elif m.current_vs_ath_ratio >= 0.1:    # 10%+ of ATH = good
                sustainability_score = 0.15
            elif m.current_vs_ath_ratio >= 0.05:   # 5%+ of ATH = moderate
                sustainability_score = 0.1
            elif m.current_vs_ath_ratio >= 0.01:   # 1%+ of ATH = minimal
                sustainability_score = 0.05
        
        # Bonus for sustained 72h performance
        if m.ath_72h_sustained:
            sustainability_score += 0.05
        
        score += min(0.25, sustainability_score)  # Cap at 25% weight
        
        # 3. Community Adoption Score (20% weight, max 0.2)
        community_score = 0.0
        
        # Holder count component (15% of total)
        if m.holder_count is not None:
            if m.holder_count >= 1000:             # 1000+ holders = excellent
                community_score += 0.15
            elif m.holder_count >= 500:            # 500+ holders = very good
                community_score += 0.12
            elif m.holder_count >= 250:            # 250+ holders = good
                community_score += 0.1
            elif m.holder_count >= 100:            # 100+ holders = moderate
                community_score += 0.08
            elif m.holder_count >= 50:             # 50+ holders = minimal
                community_score += 0.05
        
        # Volume component (5% of total)
        if m.volume_24h is not None:
            if m.volume_24h >= 100000:             # $100k+ volume = excellent
                community_score += 0.05
            elif m.volume_24h >= 50000:            # $50k+ volume = very good
                community_score += 0.04
            elif m.volume_24h >= 25000:            # $25k+ volume = good
                community_score += 0.03
            elif m.volume_24h >= 10000:            # $10k+ volume = moderate
                community_score += 0.02
            elif m.volume_24h >= 5000:             # $5k+ volume = minimal
                community_score += 0.01
        
        score += community_score
        
        # 4. Recovery Resilience Score (10% weight, max 0.1)
        recovery_score = 0.0
        if m.has_shown_recovery and m.max_recovery_after_drop is not None:
            if m.max_recovery_after_drop >= 1000:   # 1000x+ recovery = legendary
                recovery_score = 0.1
            elif m.max_recovery_after_drop >= 100:  # 100x+ recovery = excellent
                recovery_score = 0.08
            elif m.max_recovery_after_drop >= 50:   # 50x+ recovery = very good
                recovery_score = 0.06
            elif m.max_recovery_after_drop >= 20:   # 20x+ recovery = good
                recovery_score = 0.04
            elif m.max_recovery_after_drop >= 10:   # 10x+ recovery = moderate
                recovery_score = 0.02
            elif m.max_recovery_after_drop >= 5:    # 5x+ recovery = minimal
                recovery_score = 0.01
        score += recovery_score
        
        # 5. Current Momentum Score (5% weight, max 0.05)
        momentum_score = 0.0
        if m.current_trend == "recovering":
            momentum_score = 0.05
        elif m.current_trend == "stable":
            momentum_score = 0.03
        elif m.current_trend == "declining":
            momentum_score = 0.0
        score += momentum_score
        
        # Penalties for red flags
        penalty = 0.0
        
        # Excessive drop penalty
        if m.total_major_drops is not None:
            if m.total_major_drops >= 20:          # 20+ drops = major penalty
                penalty += 0.2
            elif m.total_major_drops >= 15:        # 15+ drops = significant penalty
                penalty += 0.15
            elif m.total_major_drops >= 10:        # 10+ drops = moderate penalty
                penalty += 0.1
            elif m.total_major_drops >= 5:         # 5+ drops = minor penalty
                penalty += 0.05
        
        # Coordinated dump penalty
        if m.rapid_drops_count is not None and m.rapid_drops_count >= 5:
            penalty += 0.1
        
        # Volume death penalty
        if (m.volume_drop_24h_after_peak and 
            m.volume_24h is not None and m.volume_24h < 1000):
            penalty += 0.1
        
        # Apply penalties
        score = max(0.0, score - penalty)
        
        # Final clamping and rounding
        final_score = max(0.0, min(1.0, score))
        
        # Enhanced Analysis for Success Score Components
        final_score_components = {
            'appreciation_score': appreciation_score,
            'sustainability_score': sustainability_score, 
            'community_score': community_score,
            'recovery_score': recovery_score,
            'momentum_score': momentum_score,
            'total_penalty': penalty
        }
        
        logger.debug(f"{m.mint_address}: Success score breakdown: {final_score_components}")
        return round(final_score, 4)  # Round to 4 decimal places for clarity

    def _log_classification_reasoning(self, m: TokenMetrics, label: str) -> None:
        """Log detailed reasoning for classification decision with enhanced metrics."""
        logger.info(f"═══ Token {m.mint_address} classified as '{label.upper()}' ═══")
        
        # Core metrics
        logger.info(f"📊 Core Metrics:")
        logger.info(f"  ├─ Current price: ${m.current_price:.8f}" if m.current_price else "  ├─ Current price: None")
        logger.info(f"  ├─ Launch price: ${m.launch_price:.8f}" if m.launch_price else "  ├─ Launch price: None")
        logger.info(f"  ├─ 72h peak: ${m.peak_price_72h:.8f}" if m.peak_price_72h else "  ├─ 72h peak: None")
        logger.info(f"  ├─ All-time high: ${m.post_ath_peak_price:.8f}" if m.post_ath_peak_price else "  ├─ All-time high: None")
        logger.info(f"  ├─ Volume 24h: ${m.volume_24h:,.0f}" if m.volume_24h else "  ├─ Volume 24h: None")
        logger.info(f"  └─ Holder count: {m.holder_count:,}" if m.holder_count else "  └─ Holder count: None")
        
        # Performance metrics
        logger.info(f"🚀 Performance Metrics:")
        if m.launch_price and m.peak_price_72h:
            gain_72h = m.peak_price_72h / m.launch_price
            logger.info(f"  ├─ 72h gain: {gain_72h:.1f}x")
        else:
            logger.info(f"  ├─ 72h gain: Cannot calculate")
        
        logger.info(f"  ├─ Total appreciation: {f'{m.mega_appreciation:.0f}x' if m.mega_appreciation else 'None'}")
        logger.info(f"  ├─ Current vs ATH: {f'{m.current_vs_ath_ratio:.4%}' if m.current_vs_ath_ratio else 'None'}")
        logger.info(f"  ├─ Max recovery: {f'{m.max_recovery_after_drop:.0f}x' if m.max_recovery_after_drop else 'None'}")
        logger.info(f"  ├─ ATH 72h sustained: {'✓' if m.ath_72h_sustained else '✗'}")
        logger.info(f"  └─ Success score: {f'{m.final_evaluation_score:.3f}' if m.final_evaluation_score else 'None'}")
        
        # Risk metrics
        logger.info(f"⚠️  Risk Metrics:")
        logger.info(f"  ├─ Total major drops: {m.total_major_drops}")
        logger.info(f"  ├─ Rapid drops: {m.rapid_drops_count}")
        logger.info(f"  ├─ Volume drop after peak: {'✓' if m.volume_drop_24h_after_peak else '✗'}")
        logger.info(f"  ├─ Days since last drop: {m.days_since_last_major_drop if m.days_since_last_major_drop else 'None'}")
        logger.info(f"  ├─ Current trend: {m.current_trend}")
        logger.info(f"  └─ Has shown recovery: {'✓' if m.has_shown_recovery else '✗'}")
        
        # Classification reasoning
        logger.info(f"🔍 Classification Reasoning:")
        
        if label == "successful":
            reasons = []
            
            # Check each success pattern
            if self._is_legendary_historical_success(m):
                reasons.append("🏆 LEGENDARY HISTORICAL SUCCESS")
                if m.max_recovery_after_drop and m.max_recovery_after_drop >= 1_000_000:
                    reasons.append(f"   └─ Extraordinary recovery: {m.max_recovery_after_drop:.0f}x")
                if m.mega_appreciation and m.mega_appreciation >= 100000:
                    reasons.append(f"   └─ Ultra-mega appreciation: {m.mega_appreciation:.0f}x")
            
            if self._is_72h_sustained_success(m):
                reasons.append("📈 72H SUSTAINED SUCCESS")
                if self._has_strong_72h_performance(m):
                    gain = self._get_72h_gain(m)
                    reasons.append(f"   ├─ Strong 72h performance: {gain:.1f}x")
                if self._has_sustained_performance(m):
                    reasons.append("   ├─ Performance sustained")
                if self._has_community_adoption(m):
                    reasons.append(f"   └─ Community adoption: {m.holder_count} holders, ${m.volume_24h:,.0f} volume")
            
            if self._is_recovery_based_success(m):
                reasons.append("💪 RECOVERY-BASED SUCCESS")
                major_drops = [d for _, d in m.price_drops if d >= 0.70]
                if major_drops:
                    reasons.append(f"   ├─ Recovered from {max(major_drops):.1%} drop")
                reasons.append(f"   └─ {m.max_recovery_after_drop:.1f}x recovery achieved")
            
            if self._is_mega_appreciation_success(m):
                reasons.append("🌟 MEGA APPRECIATION SUCCESS")
                reasons.append(f"   └─ {m.mega_appreciation:.0f}x total appreciation")
            
            for reason in reasons:
                logger.info(f"  {reason}")
                
        elif label == "rugpull":
            reasons = []
            
            if self._is_mega_rugpull_pattern(m):
                reasons.append("💀 MEGA RUGPULL PATTERN")
                reasons.append(f"   ├─ {m.mega_appreciation:.0f}x appreciation → {m.current_vs_ath_ratio:.4%} collapse")
                reasons.append(f"   └─ Dead volume: ${m.volume_24h:.0f}")
            
            if self._is_coordinated_dump_pattern(m):
                reasons.append("🔻 COORDINATED DUMP PATTERN")
                major_drops = [d for _, d in m.price_drops if d >= 0.85]
                reasons.append(f"   ├─ {len(major_drops)} major drops, {m.rapid_drops_count} rapid")
                reasons.append(f"   └─ No recovery for {m.days_since_last_major_drop} days")
            
            if self._is_volume_based_rugpull(m):
                reasons.append("📉 VOLUME-BASED RUGPULL")
                reasons.append(f"   ├─ Volume dried up after peak")
                reasons.append(f"   └─ Price collapsed to {m.current_vs_ath_ratio:.4%} of ATH")
            
            for reason in reasons:
                logger.info(f"  {reason}")
                
        elif label == "inactive":
            reasons = []
            reasons.append("😴 TRULY INACTIVE TOKEN")
            
            if m.launch_price and m.peak_price_72h:
                peak_ratio = m.peak_price_72h / m.launch_price
                reasons.append(f"   ├─ Never gained traction: {peak_ratio:.1f}x peak")
            
            if m.holder_count is not None:
                reasons.append(f"   ├─ Very few holders: {m.holder_count}")
            
            if m.volume_24h is not None:
                reasons.append(f"   └─ Extremely low volume: ${m.volume_24h:.0f}")
            
            for reason in reasons:
                logger.info(f"  {reason}")
                
        elif label == "unsuccessful":
            reasons = []
            reasons.append("❌ UNSUCCESSFUL (doesn't meet success criteria)")
            
            # Explain what's missing for success
            missing = []
            if not self._has_strong_72h_performance(m):
                missing.append("insufficient 72h gains")
            if not self._has_sustained_performance(m):
                missing.append("performance not sustained")
            if not self._has_community_adoption(m):
                missing.append("limited community adoption")
            if m.mega_appreciation is None or m.mega_appreciation < 1000:
                missing.append("insufficient total appreciation")
            
            if missing:
                reasons.append(f"   └─ Missing: {', '.join(missing)}")
            
            for reason in reasons:
                logger.info(f"  {reason}")
        
        logger.info("═" * 60)

    def _estimate_launch_price(self, df: pd.DataFrame) -> Optional[float]:
        """
        Estimate launch price when it's missing from data.
        Uses multiple heuristics to find the most likely launch price.
        """
        if df.empty:
            return None
        
        # Method 1: Use the first recorded price (most common case)
        first_price = df["c"].iloc[0]
        
        # Method 2: Look for the lowest price in first 24 hours (common launch pattern)
        if len(df) > 24:  # If we have more than 24 data points
            early_df = df.head(24)
            min_early_price = early_df["l"].min()
            
            # If the minimum early price is significantly lower than first price,
            # it might be a better launch price estimate
            if min_early_price < first_price * 0.5:  # 50% lower
                return min_early_price
        
        # Method 3: Check for price stability patterns at start
        if len(df) >= 10:
            # Look at first 10 candles for price stability
            early_prices = df["c"].head(10)
            price_std = early_prices.std()
            price_mean = early_prices.mean()
            
            # If prices are very stable (low volatility), use the mean
            if price_std < price_mean * 0.1:  # Less than 10% volatility
                return price_mean
        
        # Default: return first price
        return first_price

    # ────────── Per‑token flow with enhanced logging ──────────
