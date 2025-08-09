#!/usr/bin/env python3
"""
Enhanced Token Classification Algorithm - Complete Version

The algorithm distinguishes between 4 categories:
1. SUCCESSFUL: Tokens that show sustained growth and community adoption
2. RUGPULL: Tokens with coordinated dumps or no recovery patterns
3. INACTIVE: Tokens that never gained meaningful traction
4. UNSUCCESSFUL: Tokens that don't meet success criteria but aren't clear rugpulls

Usage:
    python token_labeler_complete.py <input_csv> <output_csv> [--batch-size N] [--reset]

Examples:
    # Resume from existing progress
    python token_labeler_complete.py input.csv output.csv --batch-size 10
    
    # Reset and start from beginning
    python token_labeler_complete.py input.csv output.csv --batch-size 10 --reset
"""

from __future__ import annotations

import asyncio
import argparse
import logging
import os
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
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
    transaction_count: Optional[int] = None
    
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
    """
    
    # === CORE SUCCESS CRITERIA ===
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
    INACTIVE_MAX_TRANSACTIONS = 380  # Hard rule: <380 transactions = always inactive
    
    # === ANALYSIS PARAMETERS ===
    EARLY_PHASE_DAYS = 14  # First 2 weeks are "early phase"
    RECOVERY_ANALYSIS_DAYS = 60  # Look 60 days ahead for recovery
    TREND_ANALYSIS_DAYS = 14  # Analyze trend over 2 weeks

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
    async def label_tokens_from_csv(self, inp: str, out: str, batch: int = 20, reset_progress: bool = False) -> pd.DataFrame:
        """Label tokens from CSV using on-chain data with incremental saving."""
        df = pd.read_csv(inp)
        if "mint_address" not in df.columns:
            raise ValueError("CSV must contain 'mint_address' column")
        mints = df["mint_address"].tolist()

        # Show initial processing stats
        initial_stats = self.get_processing_stats(inp, out)
        logger.info(f"Processing overview: {initial_stats}")

        # Handle reset option
        if reset_progress:
            logger.info("🔄 RESET MODE: Starting fresh, ignoring existing progress")
            if os.path.exists(out):
                backup_path = self._create_backup(out)
                if backup_path:
                    logger.info(f"Backup created before reset: {backup_path}")
            # Force overwrite the output file
            self._init_output_csv(out, overwrite=True)
            processed_mints = set()
            remaining_mints = mints
            logger.info(f"Processing all {len(remaining_mints)} tokens from the beginning")
        else:
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
        batch_results = []  # Store results for current batch
        
        try:
            for i in range(0, len(remaining_mints), batch):
                chunk = remaining_mints[i:i + batch]
                batch_number = i // batch + 1
                total_batches = (len(remaining_mints) + batch - 1) // batch
                
                logger.info("=" * 60)
                logger.info(f"🚀 STARTING BATCH {batch_number}/{total_batches}")
                logger.info(f"   Batch size: {len(chunk)} tokens")
                logger.info(f"   Total processed so far: {total_processed}/{len(mints)}")
                logger.info(f"   Failed tokens so far: {failed_count}")
                logger.info("=" * 60)
                
                batch_results = []  # Reset batch results
                batch_start_time = time.time()
                
                # Process tokens one by one for incremental saving
                for token_idx, mint in enumerate(chunk, 1):
                    try:
                        logger.info(f"🔄 Processing token {token_idx}/{len(chunk)} in batch {batch_number}: {mint}")
                        result = await self._process(mint)
                        if result is not None:
                            results.append(result)
                            batch_results.append(result)
                            # Write immediately to CSV
                            self._append_to_csv(out, result)
                            total_processed += 1
                            logger.info(f"✅ {mint} → {result[1]} (progress: {total_processed}/{len(mints)})")
                        else:
                            logger.info(f"⚠️ {mint} → skipped (no data)")
                    except Exception as e:
                        failed_count += 1
                        logger.error(f"❌ {mint} → error: {e}")
                        # Continue processing other tokens even if one fails
                        continue
                
                # Batch completion summary
                batch_duration = time.time() - batch_start_time
                successful_in_batch = len(batch_results)
                
                logger.info("=" * 60)
                logger.info(f"✅ BATCH {batch_number}/{total_batches} COMPLETED")
                logger.info(f"   Duration: {batch_duration:.1f} seconds")
                logger.info(f"   Successful: {successful_in_batch}/{len(chunk)} tokens")
                logger.info(f"   Failed in batch: {len(chunk) - successful_in_batch}")
                logger.info(f"   Cumulative progress: {total_processed}/{len(mints)} ({total_processed/len(mints)*100:.1f}%)")
                logger.info(f"   Results saved to: {out}")
                logger.info("=" * 60)
                
                # Validate CSV integrity periodically (every 5 batches)
                if batch_number % 5 == 0:
                    logger.info(f"🔍 Performing integrity check after batch {batch_number}...")
                    if not self._validate_csv_integrity(out):
                        logger.error("❌ CSV integrity check failed during processing!")
                    else:
                        logger.info("✅ CSV integrity check passed")
                
                # Sleep between batches (except for the last one)
                if i + batch < len(remaining_mints):
                    logger.info(f"⏸️ Waiting 1 second before next batch...")
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
            df = pd.read_csv(output_path)
            if "mint_address" not in df.columns or "label" not in df.columns:
                return False
            return True
        except Exception as e:
            logger.warning(f"CSV validation failed: {e}")
            return False

    def get_processing_stats(self, input_path: str, output_path: str) -> Dict[str, int]:
        """Get statistics about processing progress."""
        stats = {"total": 0, "completed": 0, "remaining": 0, "skipped": 0}
        
        try:
            input_df = pd.read_csv(input_path)
            stats["total"] = len(input_df)
            
            if os.path.exists(output_path):
                output_df = pd.read_csv(output_path)
                stats["completed"] = len(output_df)
            
            stats["remaining"] = stats["total"] - stats["completed"]
                
        except Exception as e:
            logger.warning(f"Could not calculate stats: {e}")
            
        return stats

    # ────────── Per‑token flow ──────────
    async def _process(self, mint: str) -> Optional[Tuple[str, str]]:
        m = await self._gather_metrics(mint)
        if not self._has_any_data(m):
            return None
        label = self._classify(m)
        self._log_classification_reasoning(m, label)
        return (mint, label)

    # --- helpers ----------------------------------------------------------
    @staticmethod
    def _has_any_data(m: TokenMetrics) -> bool:
        return any([
            m.current_price is not None,
            m.volume_24h is not None,
            m.holder_count is not None,
            m.launch_price is not None,
            m.mega_appreciation is not None
        ])

    async def _gather_metrics(self, mint: str) -> TokenMetrics:
        """Gather metrics using on-chain data provider."""
        t = TokenMetrics(mint)

        # 1. Current price and volume
        price_data = await self.data_provider.get_current_price(mint)
        if price_data:
            if hasattr(price_data, 'price'):
                t.current_price = price_data.price
                t.volume_24h = getattr(price_data, 'volume_24h', None)
                t.market_cap = getattr(price_data, 'market_cap', None)
            elif isinstance(price_data, dict):
                t.current_price = price_data.get("price")
                t.volume_24h = price_data.get("volume_24h")
                t.market_cap = price_data.get("market_cap")

        # 2. Historical metrics
        hist_data = await self.data_provider.get_historical_data(mint)
        if hist_data:
            hist_metrics = self._historical_metrics_from_ohlcv(hist_data)
            for key, value in hist_metrics.items():
                setattr(t, key, value)
        else:
            # Set some fallback values
            t.mega_appreciation = None
            t.current_vs_ath_ratio = None

        # 3. Holder count
        t.holder_count = await self.data_provider.get_holder_count(mint)
        
        # 4. Try to get transaction count
        try:
            t.transaction_count = await self.data_provider.get_transaction_count(mint)
        except:
            t.transaction_count = None
        
        return t

    def _historical_metrics_from_ohlcv(self, ohlcv: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Enhanced OHLCV analysis to detect sophisticated patterns."""
        if not ohlcv:
            return {}

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
            ath_time = ath_3d_df.loc[ath_3d_df["h"] == ath_3d, "t"].max()
            sustain_end = ath_time + timedelta(seconds=SUSTAIN_DAYS_SEC)
            sustain_df = df.loc[(df["t"] >= ath_time) & (df["t"] <= sustain_end)]
            
            if not sustain_df.empty:
                sustained_above_threshold = (sustain_df["l"] >= ath_3d * 0.4).all()
                ath_72h_sustained = sustained_above_threshold

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
        drop_low_tracker = {}
        drop_counter = 0
        
        for i, row in post_df.iterrows():
            ts = row["t"]
            
            # Maintain 7-day rolling window
            while roll and (ts - roll[0][0]).total_seconds() > SUSTAIN_DAYS_SEC:
                roll.popleft()
            
            roll.append((ts, row["h"]))
            window_peak = max(h for _, h in roll)
            drop_pct = 1 - row["l"] / window_peak if window_peak else 0
            
            # Track sustained drops
            if drop_pct >= 0.5:
                bad = True
            
            # Enhanced drop analysis
            if drop_pct >= 0.85:
                drop_counter += 1
                drop_time = ts
                drops.append((drop_time, drop_pct))
                
                # Track lowest point after this drop for recovery analysis
                drop_low_tracker[drop_counter] = {
                    'time': drop_time,
                    'low': row["l"],
                    'drop_pct': drop_pct
                }
                
                # Check if it's a rapid drop
                if len(roll) >= 2:
                    time_diff = (ts - roll[0][0]).total_seconds()
                    if time_diff <= self.RUG_RAPID_DROP_HOURS * 3600:
                        rapid_drops_count += 1
                
                # Categorize as early or late phase drop
                if ts <= early_phase_end:
                    early_drops.append((drop_time, drop_pct, 0.0))  # Recovery ratio filled later
                else:
                    late_drops.append((drop_time, drop_pct, 0.0))
        
        # Analyze recovery patterns
        for drop_id, drop_info in drop_low_tracker.items():
            drop_low = drop_info['low']
            drop_time = drop_info['time']
            
            # Look for recovery in the following 60 days
            recovery_window = drop_time + timedelta(days=60)
            recovery_df = post_df.loc[(post_df["t"] > drop_time) & (post_df["t"] <= recovery_window)]
            
            if not recovery_df.empty:
                recovery_peak = recovery_df["h"].max()
                if drop_low > 0:
                    recovery_ratio = recovery_peak / drop_low
                    max_recovery = max(max_recovery, recovery_ratio)
                    
                    if recovery_ratio >= 3.0:  # 3x+ recovery
                        has_recovery = True
        
        # Determine current trend
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

        # Calculate mega appreciation
        launch_price = df["c"].iloc[0] if not df.empty else None
        all_time_high = df["h"].max() if not df.empty else None
        mega_appreciation = None
        current_vs_ath_ratio = None
        
        if launch_price and all_time_high and launch_price > 0:
            mega_appreciation = all_time_high / launch_price
        
        if df["c"].iloc[-1] and all_time_high and all_time_high > 0:
            current_vs_ath_ratio = df["c"].iloc[-1] / all_time_high

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
            "launch_price": launch_price,
            "peak_price_72h": ath_3d,
            "post_ath_peak_price": post_peak,
            "volume_drop_24h_after_peak": volume_drop_24h_after_peak,
            "mega_appreciation": mega_appreciation,
            "current_vs_ath_ratio": current_vs_ath_ratio,
            "total_major_drops": len(drops)
        }

    # ---------- Enhanced Classification Algorithm ------------------
    def _classify(self, m: TokenMetrics) -> str:
        """
        Revised classification algorithm for ML training data.
        
        Order of precedence:
        1. HARD RULE: <380 transactions = always inactive
        2. HARD RULE: Liquidity removal = always rugpull
        3. ALL rugpull patterns (with double verification for recovery)
        4. HARD RULE: ATH within 72h = never successful (hype-only tokens)
        5. True inactivity (minimal transactions/holders)
        6. Sustained growth success (ATH after 72h + stability)
        7. Recovery-based success (survived crashes and recovered)
        8. Historical success (consistent with sustained patterns)
        9. Everything else = unsuccessful
        """
        
        # HARD RULE #1: Transaction count check (highest priority)
        if m.transaction_count is not None and m.transaction_count < self.INACTIVE_MAX_TRANSACTIONS:
            logger.debug(f"HARD RULE: <{self.INACTIVE_MAX_TRANSACTIONS} transactions ({m.transaction_count}) - immediately classified as inactive")
            return "inactive"
        
        # HARD RULE #2: Liquidity removal = ALWAYS rugpull
        if self._is_hard_liquidity_removal_rugpull(m):
            logger.debug(f"HARD RULE: Liquidity removal detected - immediately classified as rugpull")
            return "rugpull"
        
        # PHASE 1: ALL rugpull patterns (including early rugpulls)
        if self._is_coordinated_rugpull_non_liquidity(m):
            # DOUBLE VERIFICATION: Check if this might actually be a successful token
            if self._has_successful_recovery_patterns(m):
                logger.info(f"Rugpull patterns detected BUT successful recovery patterns override → checking for success")
                # Don't return rugpull immediately, let it flow through success checks
            else:
                return "rugpull"
        
        # HARD RULE #3: If ATH was reached within first 72h, token can NEVER be successful
        if self._ath_was_within_72h(m):
            logger.debug(f"ATH within 72h - disqualified from success classification")
            # Only check for inactive vs unsuccessful
            if self._is_truly_inactive(m):
                return "inactive"
            else:
                return "unsuccessful"
        
        # PHASE 2: True inactivity check 
        if self._is_truly_inactive(m):
            return "inactive"
        
        # PHASE 3: Sustained growth success (primary success pattern)
        if self._is_sustained_growth_success(m):
            return "successful"
        
        # PHASE 4: Recovery-based success (tokens that survived crashes and recovered)
        if self._is_recovery_based_success(m):
            return "successful"
        
        # PHASE 5: Historical success with stability indicators
        if self._is_historical_stable_success(m):
            return "successful"
        
        # PHASE 6: Default classification
        return "unsuccessful"

    def _is_hard_liquidity_removal_rugpull(self, m: TokenMetrics) -> bool:
        """Hard rule: Detect clear liquidity removal patterns."""
        if not m.mega_appreciation or m.mega_appreciation < self.RUG_MIN_APPRECIATION_FOR_RUG:
            return False
        
        # Must have extreme price collapse AND volume death
        price_collapsed = (m.current_vs_ath_ratio is not None and 
                          m.current_vs_ath_ratio <= 0.1)  # <10% of ATH
        
        volume_dead = (m.volume_24h is not None and m.volume_24h <= 1000)  # <$1000 volume
        
        return price_collapsed and volume_dead

    def _is_coordinated_rugpull_non_liquidity(self, m: TokenMetrics) -> bool:
        """Detect coordinated rugpull patterns (excluding liquidity removal)."""
        return self._is_mega_rugpull_pattern(m) or self._is_coordinated_dump_pattern(m)

    def _is_mega_rugpull_pattern(self, m: TokenMetrics) -> bool:
        """Detect mega rugpull: high appreciation followed by complete collapse."""
        if not m.mega_appreciation or m.mega_appreciation < 5.0:
            return False
        
        # Pattern 1: Current vs ATH ratio indicates massive collapse
        massive_collapse = (m.current_vs_ath_ratio is not None and 
                          m.current_vs_ath_ratio <= 0.05)  # Less than 5% of ATH
        
        if not massive_collapse:
            return False
        
        # Pattern 2: Volume must be dead or very low
        volume_dead = (m.volume_24h is None or m.volume_24h <= 2000)
        
        # Confirmation scoring system
        confirmation_score = 0
        
        if m.mega_appreciation >= 50:
            confirmation_score += 1
        
        if m.current_vs_ath_ratio and m.current_vs_ath_ratio <= 0.01:
            confirmation_score += 2
        elif m.current_vs_ath_ratio and m.current_vs_ath_ratio <= 0.02:
            confirmation_score += 1
        
        if volume_dead:
            confirmation_score += 1
        
        if m.total_major_drops >= 3 and not m.has_shown_recovery:
            confirmation_score += 1
        
        if m.holder_count and m.holder_count >= 20 and volume_dead:
            confirmation_score += 1
        
        if m.current_trend == "declining":
            confirmation_score += 1
        
        return confirmation_score >= 3

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
        
        return True

    def _ath_was_within_72h(self, m: TokenMetrics) -> bool:
        """Check if all-time high was reached within first 72 hours."""
        if not m.peak_price_72h or not m.post_ath_peak_price:
            return False
        
        # If 72h peak is same as or higher than post-ATH peak, then ATH was within 72h
        return m.peak_price_72h >= m.post_ath_peak_price * 0.95  # 95% threshold for floating point comparison

    def _has_successful_recovery_patterns(self, m: TokenMetrics) -> bool:
        """Check if token has patterns indicating successful recovery despite rugpull indicators."""
        if not m.has_shown_recovery or not m.max_recovery_after_drop:
            return False
        
        # Must have substantial recovery (50x+ from major drop)
        if m.max_recovery_after_drop < 50:
            return False
        
        # Must have sustained the recovery
        if m.current_trend == "declining":
            return False
        
        # Must have reasonable current price vs ATH
        if m.current_vs_ath_ratio is not None and m.current_vs_ath_ratio < 0.01:
            return False
        
        return True

    def _is_truly_inactive(self, m: TokenMetrics) -> bool:
        """Identify tokens that truly never gained any meaningful traction."""
        # Primary indicator: Never gained significant appreciation
        if m.mega_appreciation and m.mega_appreciation > self.INACTIVE_MAX_APPRECIATION:
            return False
        
        # Secondary indicators: Very limited community engagement
        very_few_holders = (m.holder_count is not None and 
                           m.holder_count <= self.INACTIVE_MAX_HOLDERS)
        
        if m.holder_count is None:
            return False  # Without holder data, be cautious
        
        # Tertiary indicator: Extremely low activity
        extremely_low_volume = (m.volume_24h is not None and 
                               m.volume_24h <= self.INACTIVE_MAX_VOLUME)
        
        # Additional check: Never showed any recovery ability
        never_recovered = not m.has_shown_recovery or (
            m.max_recovery_after_drop is not None and 
            m.max_recovery_after_drop < 2
        )
        
        # All conditions must be true for inactive classification
        conditions = [
            very_few_holders,
            extremely_low_volume or m.volume_24h is None,
            never_recovered
        ]
        
        return all(conditions)

    def _is_sustained_growth_success(self, m: TokenMetrics) -> bool:
        """Primary success pattern: Strong sustained growth after 72h."""
        # Must have reached ATH after 72h
        if not self._reached_ath_after_72h(m):
            return False
        
        # Must have sustained growth pattern
        if not self._has_sustained_growth_pattern(m):
            return False
        
        # Must have reasonable community
        if not self._has_reasonable_community(m):
            return False
        
        # Must not have clear rugpull characteristics
        if self._has_rugpull_characteristics(m):
            return False
        
        return True

    def _reached_ath_after_72h(self, m: TokenMetrics) -> bool:
        """Check if ATH was reached after 72h period."""
        if not m.peak_price_72h or not m.post_ath_peak_price:
            return False
        
        # Post-ATH peak should be significantly higher than 72h peak
        return m.post_ath_peak_price > m.peak_price_72h * 1.1  # 10% higher

    def _has_sustained_growth_pattern(self, m: TokenMetrics) -> bool:
        """Check for sustained growth patterns."""
        if not m.mega_appreciation or m.mega_appreciation < 10:
            return False
        
        # Should have sustained performance
        if m.ath_72h_sustained is not None:
            return m.ath_72h_sustained
        
        return True

    def _has_reasonable_community(self, m: TokenMetrics) -> bool:
        """Check for reasonable community adoption."""
        min_holders = self.SUCCESS_MIN_HOLDERS_PRIMARY
        if not m.holder_count or m.holder_count < min_holders:
            return False
        
        # Volume requirement
        min_volume = self.SUCCESS_MIN_VOLUME_PRIMARY
        if m.mega_appreciation and m.mega_appreciation >= 100:
            min_volume = min_volume // 5  # More lenient for high appreciation
        
        if m.volume_24h is None:
            if m.holder_count >= min_holders * 2:
                return True
            return False
        
        return m.volume_24h >= min_volume

    def _has_rugpull_characteristics(self, m: TokenMetrics) -> bool:
        """Check for rugpull red flags."""
        if m.rapid_drops_count and m.rapid_drops_count >= 5:
            return True
        
        if m.total_major_drops and m.total_major_drops >= 15:
            return True
        
        return False

    def _is_recovery_based_success(self, m: TokenMetrics) -> bool:
        """Secondary success pattern: Strong recovery after major setbacks."""
        if not m.has_shown_recovery or not m.max_recovery_after_drop:
            return False
        
        # Recovery must be substantial
        if m.max_recovery_after_drop < self.SUCCESS_RECOVERY_MULTIPLIER:
            return False
        
        # Must have had significant initial drop
        major_drops = [d for _, d in m.price_drops if d >= self.SUCCESS_RECOVERY_MIN_DROP]
        if not major_drops:
            return False
        
        # Must have reasonable community
        min_holders = self.SUCCESS_MIN_HOLDERS_RECOVERY
        if not m.holder_count or m.holder_count < min_holders:
            return False
        
        # Must have sustained the recovery
        return self._has_sustained_recovery(m)

    def _has_sustained_recovery(self, m: TokenMetrics) -> bool:
        """Check if recovery was sustained."""
        if m.current_trend == "declining":
            return False
        
        if (m.days_since_last_major_drop is not None and 
            m.days_since_last_major_drop < self.SUCCESS_RECOVERY_SUSTAINABILITY):
            return False
        
        if m.current_vs_ath_ratio is not None and m.current_vs_ath_ratio < 0.01:
            return False
        
        return True

    def _is_historical_stable_success(self, m: TokenMetrics) -> bool:
        """Success based on historical performance with stability."""
        if not m.mega_appreciation or m.mega_appreciation < self.SUCCESS_MEGA_APPRECIATION:
            return False
        
        if m.current_vs_ath_ratio is not None and m.current_vs_ath_ratio < self.SUCCESS_MEGA_CURRENT_RATIO:
            return False
        
        if m.holder_count is not None and m.holder_count < (self.SUCCESS_MIN_HOLDERS_PRIMARY // 2):
            return False
        
        return True

    def _log_classification_reasoning(self, m: TokenMetrics, label: str) -> None:
        """Log detailed reasoning for classification decision."""
        logger.info(f"═══ Token {m.mint_address} classified as '{label.upper()}' ═══")
        
        # Core metrics
        logger.info(f"📊 Core Metrics:")
        logger.info(f"  ├─ Current price: ${m.current_price:.8f}" if m.current_price else "  ├─ Current price: None")
        logger.info(f"  ├─ Launch price: ${m.launch_price:.8f}" if m.launch_price else "  ├─ Launch price: None")
        logger.info(f"  ├─ 72h peak: ${m.peak_price_72h:.8f}" if m.peak_price_72h else "  ├─ 72h peak: None")
        logger.info(f"  ├─ All-time high: ${m.post_ath_peak_price:.8f}" if m.post_ath_peak_price else "  ├─ All-time high: None")
        logger.info(f"  ├─ Volume 24h: ${m.volume_24h:,.0f}" if m.volume_24h else "  ├─ Volume 24h: None")
        logger.info(f"  ├─ Holder count: {m.holder_count:,}" if m.holder_count else "  ├─ Holder count: None")
        logger.info(f"  └─ Transaction count: {m.transaction_count:,}" if m.transaction_count else "  └─ Transaction count: None")
        
        # Performance metrics
        logger.info(f"🚀 Performance Metrics:")
        logger.info(f"  ├─ Total appreciation: {f'{m.mega_appreciation:.0f}x' if m.mega_appreciation else 'None'}")
        logger.info(f"  ├─ Current vs ATH: {f'{m.current_vs_ath_ratio:.4%}' if m.current_vs_ath_ratio else 'None'}")
        logger.info(f"  ├─ Max recovery: {f'{m.max_recovery_after_drop:.0f}x' if m.max_recovery_after_drop else 'None'}")
        logger.info(f"  └─ ATH 72h sustained: {'✓' if m.ath_72h_sustained else '✗'}")
        
        # Risk metrics
        logger.info(f"⚠️  Risk Metrics:")
        logger.info(f"  ├─ Total major drops: {m.total_major_drops}")
        logger.info(f"  ├─ Rapid drops: {m.rapid_drops_count}")
        logger.info(f"  ├─ Days since last drop: {m.days_since_last_major_drop if m.days_since_last_major_drop else 'None'}")
        logger.info(f"  ├─ Current trend: {m.current_trend}")
        logger.info(f"  └─ Has shown recovery: {'✓' if m.has_shown_recovery else '✗'}")
        
        logger.info("═" * 60)


def setup_logging():
    """Setup logging with both file and console output."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("incremental_labeling.log"),
            logging.StreamHandler()
        ]
    )


async def main():
    """Main function to run incremental token labeling."""
    parser = argparse.ArgumentParser(description="Enhanced Token Labeling - Complete Version")
    parser.add_argument("input_csv", help="Input CSV file with mint addresses")
    parser.add_argument("output_csv", help="Output CSV file for labeled tokens")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for processing (default: 10)")
    parser.add_argument("--config", help="Path to config file (optional)")
    parser.add_argument("--reset", action="store_true", help="Reset progress and start from the beginning (ignores existing output)")
    
    args = parser.parse_args()
    
    # Validate input file exists
    if not Path(args.input_csv).exists():
        print(f"Error: Input file '{args.input_csv}' not found")
        sys.exit(1)
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info("🚀 ENHANCED TOKEN LABELING - COMPLETE VERSION")
    logger.info("=" * 80)
    logger.info(f"📁 Input: {args.input_csv}")
    logger.info(f"📁 Output: {args.output_csv}")
    logger.info(f"📦 Batch size: {args.batch_size}")
    if args.reset:
        logger.info("🔄 RESET MODE: Will start from the beginning, ignoring existing progress")
    else:
        logger.info("📝 RESUME MODE: Will continue from existing progress if available")
    logger.info("=" * 80)
    
    try:
        # Initialize the enhanced token labeler
        async with EnhancedTokenLabeler(config_path=args.config) as labeler:
            # Get initial stats (before reset if applicable)
            if not args.reset:
                stats = labeler.get_processing_stats(args.input_csv, args.output_csv)
                logger.info(f"📊 Initial processing stats: {stats}")
                
                if stats["remaining"] == 0:
                    logger.info("✅ All tokens have already been processed!")
                    return
            
            # Run the labeling process with incremental saving
            await labeler.label_tokens_from_csv(
                inp=args.input_csv,
                out=args.output_csv,
                batch=args.batch_size,
                reset_progress=args.reset
            )
            
            # Load the final results from the CSV for the report
            if os.path.exists(args.output_csv):
                try:
                    result_df = pd.read_csv(args.output_csv)
                except pd.errors.EmptyDataError:
                    result_df = pd.DataFrame(columns=['mint_address', 'label'])
            else:
                result_df = pd.DataFrame(columns=['mint_address', 'label'])
            
            # Final summary
            final_stats = labeler.get_processing_stats(args.input_csv, args.output_csv)
            logger.info("=" * 80)
            logger.info("🎉 PROCESSING COMPLETED!")
            logger.info("=" * 80)
            logger.info(f"📊 Final stats: {final_stats}")
            logger.info(f"💾 Results saved to: {args.output_csv}")
            
            # Show distribution of labels
            if not result_df.empty:
                logger.info("📈 Label distribution:")
                label_counts = result_df["label"].value_counts()
                for label, count in label_counts.items():
                    percentage = (count / len(result_df)) * 100
                    logger.info(f"   {label}: {count} ({percentage:.1f}%)")
            logger.info("=" * 80)
    
    except KeyboardInterrupt:
        logger.info("⚠️ Process interrupted by user. Progress has been saved.")
        logger.info(f"🔄 To resume, run the same command again: {' '.join(sys.argv)}")
    except Exception as e:
        logger.error(f"❌ Error during processing: {e}")
        logger.info("📝 Check the log file for detailed error information.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
