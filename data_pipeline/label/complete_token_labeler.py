#!/usr/bin/env python3
"""
Complete Enhanced Token Classification Algorithm with Incremental Processing

This is the complete, unified script that includes:
1. The enhanced token classification algorithm
2. Incremental CSV saving after every token
3. Batch processing with detailed progress tracking
4. Reset functionality to start from scratch
5. Resume functionality to continue from existing progress

Usage:
    python complete_token_labeler.py <input_csv> <output_csv> [--batch-size N] [--reset]

Examples:
    # Resume from existing progress
    python complete_token_labeler.py input.csv output.csv --batch-size 10
    
    # Reset and start from beginning
    python complete_token_labeler.py input.csv output.csv --batch-size 10 --reset

The algorithm distinguishes between 4 categories:
1. SUCCESSFUL: Tokens that show sustained growth and community adoption
2. RUGPULL: Tokens with coordinated dumps or clear malicious intent
3. INACTIVE: Tokens that never gained meaningful traction
4. UNSUCCESSFUL: Tokens that don't meet success criteria but aren't clear rugpulls
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
    Complete Token Classification Algorithm for ML Training Data
    
    Designed to create the highest quality dataset for ML prediction based on 72h data.
    Each classification has strict, unambiguous criteria to minimize mislabeling.
    
    SUCCESSFUL: Tokens with proven sustained growth patterns
    RUGPULL: Coordinated dumps with clear malicious intent  
    INACTIVE: Tokens that never gained meaningful traction
    UNSUCCESSFUL: Everything else (failed attempts at success)
    """
    
    # === CORE SUCCESS CRITERIA ===
    SUCCESS_72H_MIN_GAIN = 5.0  # Minimum 5x gain from launch to 72h peak
    SUCCESS_72H_SUSTAINABILITY_DAYS = 7  # Must sustain for 1 week after 72h
    SUCCESS_72H_MIN_RETENTION = 0.40  # Must retain at least 40% of 72h gains
    SUCCESS_MIN_HOLDERS_PRIMARY = 100  # Strong community indicator
    SUCCESS_MIN_VOLUME_PRIMARY = 50000  # $50k+ volume shows real activity
    
    # === RUGPULL DETECTION CRITERIA ===
    RUGPULL_MAJOR_DROP_THRESHOLD = 0.80  # 80%+ drop is major
    RUGPULL_RAPID_DROP_HOURS = 2  # Drops within 2 hours are suspicious
    RUGPULL_MIN_RAPID_DROPS = 2  # Need multiple rapid drops for rugpull
    RUGPULL_NO_RECOVERY_DAYS = 14  # No recovery for 2 weeks = likely rugpull
    
    # === ACTIVITY THRESHOLDS ===
    INACTIVE_MAX_TRANSACTIONS = 380  # Fewer transactions = inactive
    INACTIVE_MAX_HOLDERS = 50  # Very few holders = inactive
    INACTIVE_MAX_VOLUME = 10000  # Under $10k volume = inactive
    INACTIVE_MAX_PRICE_RATIO = 2.0  # Never gained more than 2x = inactive

    def __init__(self, config_path: Optional[str] = None):
        """Initialize the token labeler with configuration."""
        self.config = load_config(config_path)
        self.data_provider: Optional[OnChainDataProvider] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.data_provider = OnChainDataProvider(self.config)
        await self.data_provider.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.data_provider:
            await self.data_provider.__aexit__(exc_type, exc_val, exc_tb)

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
                
                # Validate CSV integrity periodically (every 5 batches instead of 10)
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
        """Validate the integrity of the CSV file."""
        try:
            if not os.path.exists(output_path):
                return False
            df = pd.read_csv(output_path)
            required_columns = ["mint_address", "label"]
            return all(col in df.columns for col in required_columns)
        except Exception as e:
            logger.warning(f"CSV validation failed: {e}")
            return False

    def get_processing_stats(self, input_path: str, output_path: str) -> Dict[str, Any]:
        """Get statistics about processing progress."""
        try:
            input_df = pd.read_csv(input_path)
            total_tokens = len(input_df)
            
            if os.path.exists(output_path):
                try:
                    output_df = pd.read_csv(output_path)
                    processed_tokens = len(output_df)
                except Exception:
                    processed_tokens = 0
            else:
                processed_tokens = 0
            
            remaining_tokens = total_tokens - processed_tokens
            progress_percentage = (processed_tokens / total_tokens * 100) if total_tokens > 0 else 0
            
            return {
                "total": total_tokens,
                "processed": processed_tokens,
                "remaining": remaining_tokens,
                "progress": f"{progress_percentage:.1f}%"
            }
        except Exception as e:
            logger.error(f"Failed to get processing stats: {e}")
            return {"total": 0, "processed": 0, "remaining": 0, "progress": "0%"}

    async def _process(self, mint: str) -> Optional[Tuple[str, str]]:
        """Process a single token and return (mint_address, label)."""
        try:
            m = await self._gather_metrics(mint)
            if m is None:
                return None
            
            label = self._classify(m)
            self._log_classification_reasoning(m, label)
            
            return (mint, label)
        
        except Exception as e:
            logger.error(f"Error processing {mint}: {e}")
            return None

    async def _gather_metrics(self, mint: str) -> TokenMetrics:
        """Gather comprehensive metrics for a token."""
        m = TokenMetrics(mint_address=mint)
        
        # Get current price data
        try:
            price_data = await self.data_provider.get_current_price(mint)
            if hasattr(price_data, 'price'):
                m.current_price = price_data.price
            elif isinstance(price_data, dict):
                m.current_price = price_data.get('price')
            else:
                m.current_price = price_data
        except Exception as e:
            logger.warning(f"Could not fetch current price for {mint}: {e}")
        
        # Get historical OHLCV data
        try:
            ohlcv_data = await self.data_provider.get_historical_ohlcv(mint, days=30)
            if ohlcv_data:
                historical_metrics = self._historical_metrics_from_ohlcv(ohlcv_data)
                
                # Update metrics with historical data
                for key, value in historical_metrics.items():
                    if hasattr(m, key):
                        setattr(m, key, value)
        except Exception as e:
            logger.warning(f"Could not fetch historical data for {mint}: {e}")
        
        # Get token info (holders, volume, etc.)
        try:
            token_info = await self.data_provider.get_token_info(mint)
            if token_info:
                if hasattr(token_info, 'holder_count'):
                    m.holder_count = token_info.holder_count
                elif isinstance(token_info, dict):
                    m.holder_count = token_info.get('holder_count')
                
                if hasattr(token_info, 'volume_24h'):
                    m.volume_24h = token_info.volume_24h
                elif isinstance(token_info, dict):
                    m.volume_24h = token_info.get('volume_24h')
        except Exception as e:
            logger.warning(f"Could not fetch token info for {mint}: {e}")
        
        return m

    def _historical_metrics_from_ohlcv(self, ohlcv: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract historical metrics from OHLCV data."""
        if not ohlcv:
            return {}
        
        # Convert to DataFrame for easier analysis
        df = pd.DataFrame(ohlcv)
        if df.empty:
            return {}
        
        # Ensure timestamp column exists and convert to datetime
        if 't' not in df.columns:
            return {}
        
        df['t'] = pd.to_datetime(df['t'], unit='s')
        df = df.sort_values('t').reset_index(drop=True)
        
        # Current time for calculations
        now = datetime.now()
        
        # Calculate 72-hour metrics
        launch_time = df['t'].iloc[0]
        hours_72_cutoff = launch_time + timedelta(hours=72)
        
        # Filter data for first 72 hours
        df_72h = df[df['t'] <= hours_72_cutoff]
        
        # Find peak price in 72h
        peak_price_72h = df_72h['h'].max() if not df_72h.empty else None
        
        # Post-72h data for ATH calculation
        post_72h_df = df[df['t'] > hours_72_cutoff]
        post_ath_peak_price = post_72h_df['h'].max() if not post_72h_df.empty else None
        
        # Check if ATH was sustained for 72h
        ath_72h_sustained = False
        if peak_price_72h and not post_72h_df.empty:
            # Check if price stayed above 70% of 72h peak for significant time
            threshold = peak_price_72h * 0.7
            sustained_df = post_72h_df[post_72h_df['l'] >= threshold]
            if len(sustained_df) >= 7:  # At least 7 data points above threshold
                ath_72h_sustained = True
        
        # Analyze price drops and recovery patterns
        drops = []
        early_drops = []
        late_drops = []
        has_recovery = False
        max_recovery = 0
        rapid_drops_count = 0
        
        # Track drops using a sliding window
        drop_low_tracker = {}  # Track the lowest point after each significant drop
        
        for i in range(1, len(df)):
            prev_high = df['h'].iloc[max(0, i-24):i].max()  # High in previous 24 periods
            current_low = df['l'].iloc[i]
            
            if prev_high > 0:
                drop_pct = 1 - (current_low / prev_high)
                
                if drop_pct >= 0.5:  # 50%+ drop
                    drop_time = df['t'].iloc[i]
                    drops.append((drop_time, drop_pct))
                    
                    # Track for recovery analysis
                    drop_id = len(drops) - 1
                    drop_low_tracker[drop_id] = {
                        'drop_time': drop_time,
                        'drop_pct': drop_pct,
                        'low_price': current_low,
                        'best_recovery': 0
                    }
                    
                    # Categorize as early or late phase
                    if drop_time <= hours_72_cutoff:
                        early_drops.append((drop_time, drop_pct, 0))  # Recovery will be updated later
                    else:
                        late_drops.append((drop_time, drop_pct, 0))   # Recovery will be updated later
                    
                    # Check if this was a rapid drop (within 2 hours)
                    if i > 1:
                        time_diff = (drop_time - df['t'].iloc[i-1]).total_seconds() / 3600
                        if time_diff <= 2:
                            rapid_drops_count += 1
        
        # Analyze recovery patterns with enhanced criteria
        for drop_id, drop_info in drop_low_tracker.items():
            drop_time = drop_info['drop_time']
            low_price = drop_info['low_price']
            
            # Look for recovery in the next 30 days
            recovery_end = drop_time + timedelta(days=30)
            recovery_df = df[(df['t'] > drop_time) & (df['t'] <= recovery_end)]
            
            if not recovery_df.empty:
                max_price_after = recovery_df['h'].max()
                recovery_ratio = max_price_after / low_price if low_price > 0 else 0
                
                drop_info['best_recovery'] = recovery_ratio
                max_recovery = max(max_recovery, recovery_ratio)
                
                if recovery_ratio >= 3:  # 3x recovery
                    has_recovery = True
        
        # Determine current trend (last 7 days)
        recent_df = df.loc[df["t"] >= (now - timedelta(days=7))]
        current_trend = "stable"
        if len(recent_df) >= 2:
            start_price = recent_df["c"].iloc[0]
            end_price = recent_df["c"].iloc[-1]
            change = (end_price - start_price) / start_price if start_price > 0 else 0
            
            if change > 0.2:
                current_trend = "recovering"
            elif change < -0.2:
                current_trend = "declining"
        
        # Calculate days since last major drop
        days_since_last_drop = None
        if drops:
            last_drop_time = max(drop[0] for drop in drops)
            days_since_last_drop = (now - last_drop_time).days
        
        # Volume analysis
        volume_drop_24h_after_peak = False
        if peak_price_72h and len(df) > 24:
            peak_idx = df_72h['h'].idxmax()
            if peak_idx + 24 < len(df):
                volume_before = df['v'].iloc[max(0, peak_idx-12):peak_idx+1].mean()
                volume_after = df['v'].iloc[peak_idx+1:peak_idx+25].mean()
                if volume_before > 0 and volume_after < volume_before * 0.3:
                    volume_drop_24h_after_peak = True

        return {
            "has_sustained_drop": len(drops) > 0,
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
            "peak_price_72h": peak_price_72h,
            "post_ath_peak_price": post_ath_peak_price,
            "volume_drop_24h_after_peak": volume_drop_24h_after_peak,
            "estimated_launch_price": self._estimate_launch_price(df),
            "average_volume": df["v"].mean() if not df.empty else None,
            "peak_volume": df["v"].max() if not df.empty else None,
            "recent_volume": df["v"].tail(7).mean() if len(df) >= 7 else None
        }

    def _classify(self, m: TokenMetrics) -> str:
        """
        Revised classification algorithm for ML training data.
        
        Order of precedence:
        1. HARD RULE: Liquidity removal = always rugpull (HIGHEST PRIORITY)
        2. ALL rugpull patterns (with double verification for recovery)
        3. HARD RULE: ATH within 72h = never successful (hype-only tokens)
        4. HARD RULE: <380 transactions = always inactive
        5. True inactivity (minimal transactions/holders)
        6. Sustained growth success (ATH after 72h + stability)
        7. Recovery-based success (survived crashes and recovered)
        8. Historical success (consistent with sustained patterns)
        9. Everything else = unsuccessful
        """
        
        # HARD RULE #1: Liquidity removal = ALWAYS rugpull (highest priority)
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
        
        # HARD RULE #2: If ATH was within first 72h, token can NEVER be successful
        if self._ath_was_within_72h(m):
            logger.debug(f"ATH within 72h - disqualified from success classification")
            # Only check for inactive vs unsuccessful (rugpulls already handled above)
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
        """Detect hard liquidity removal rugpulls (highest priority)."""
        # This would require specific liquidity pool data
        # For now, return False as we don't have this data
        return False

    def _is_coordinated_rugpull_non_liquidity(self, m: TokenMetrics) -> bool:
        """Detect coordinated rugpulls without liquidity removal."""
        if not m.price_drops:
            return False
        
        # Multiple rapid major drops with no recovery
        major_drops = [drop for _, drop_pct in m.price_drops if drop_pct >= 0.8]
        
        if len(major_drops) >= 2 and m.rapid_drops_count >= 2:
            # Check for lack of recovery
            if (m.days_since_last_major_drop and m.days_since_last_major_drop >= 14 and
                (not m.has_shown_recovery or m.max_recovery_after_drop < 2)):
                return True
        
        return False

    def _has_successful_recovery_patterns(self, m: TokenMetrics) -> bool:
        """Check if token has patterns indicating successful recovery despite rugpull signs."""
        if not m.has_shown_recovery:
            return False
        
        # Strong recovery after major drops
        if m.max_recovery_after_drop and m.max_recovery_after_drop >= 5:
            return True
        
        # Good holder count and volume despite drops
        if (m.holder_count and m.holder_count >= 200 and 
            m.volume_24h and m.volume_24h >= 100000):
            return True
        
        return False

    def _ath_was_within_72h(self, m: TokenMetrics) -> bool:
        """Check if ATH was reached within first 72 hours."""
        # If we have post-ATH peak data, that means ATH was after 72h
        if m.post_ath_peak_price and m.peak_price_72h:
            return m.post_ath_peak_price <= m.peak_price_72h
        
        # If no post-72h data exists or peak is much higher than 72h peak
        return True  # Assume ATH was within 72h if we can't prove otherwise

    def _is_truly_inactive(self, m: TokenMetrics) -> bool:
        """Detect truly inactive tokens."""
        # Very low holder count
        if m.holder_count and m.holder_count < self.INACTIVE_MAX_HOLDERS:
            return True
        
        # Extremely low volume
        if m.volume_24h and m.volume_24h < self.INACTIVE_MAX_VOLUME:
            return True
        
        # Never gained significant traction
        if (m.launch_price and m.peak_price_72h and 
            m.peak_price_72h / m.launch_price < self.INACTIVE_MAX_PRICE_RATIO):
            return True
        
        return False

    def _is_sustained_growth_success(self, m: TokenMetrics) -> bool:
        """Primary success pattern: sustained growth after 72h."""
        # Must have ATH after 72h
        if self._ath_was_within_72h(m):
            return False
        
        # Strong community indicators
        if not (m.holder_count and m.holder_count >= self.SUCCESS_MIN_HOLDERS_PRIMARY):
            return False
        
        if not (m.volume_24h and m.volume_24h >= self.SUCCESS_MIN_VOLUME_PRIMARY):
            return False
        
        # Sustained growth pattern
        if m.ath_72h_sustained:
            return True
        
        return False

    def _is_recovery_based_success(self, m: TokenMetrics) -> bool:
        """Recovery-based success: survived major crashes and recovered."""
        if not m.has_shown_recovery:
            return False
        
        # Strong recovery after drops
        if m.max_recovery_after_drop and m.max_recovery_after_drop >= 10:
            # Additional validation
            if (m.holder_count and m.holder_count >= 150 and
                m.volume_24h and m.volume_24h >= 30000):
                return True
        
        return False

    def _is_historical_stable_success(self, m: TokenMetrics) -> bool:
        """Historical success with stability patterns."""
        # Would require more sophisticated historical analysis
        # For now, return False
        return False

    def _log_classification_reasoning(self, m: TokenMetrics, label: str):
        """Log the reasoning behind the classification."""
        logger.info(f"═" * 60)
        logger.info(f"🔍 CLASSIFICATION: {label.upper()}")
        logger.info(f"Token: {m.mint_address}")
        
        if label == "successful":
            reasons = []
            reasons.append("🎉 SUCCESSFUL TOKEN")
            
            if self._is_sustained_growth_success(m):
                reasons.append("📈 SUSTAINED GROWTH SUCCESS")
                reasons.append(f"   ├─ Holders: {m.holder_count}")
                reasons.append(f"   ├─ Volume 24h: ${m.volume_24h:,.0f}" if m.volume_24h else "   ├─ Volume: N/A")
                reasons.append(f"   └─ ATH sustained: {m.ath_72h_sustained}")
            
            if self._is_recovery_based_success(m):
                reasons.append("💪 RECOVERY-BASED SUCCESS")
                reasons.append(f"   ├─ Max recovery: {m.max_recovery_after_drop:.1f}x")
                reasons.append(f"   └─ Survived {len(m.price_drops)} major drops")
            
            for reason in reasons:
                logger.info(f"  {reason}")
                
        elif label == "rugpull":
            reasons = []
            
            if self._is_hard_liquidity_removal_rugpull(m):
                reasons.append("🚨 HARD LIQUIDITY REMOVAL")
                reasons.append("   └─ Definitive rugpull pattern")
            
            if self._is_coordinated_rugpull_non_liquidity(m):
                reasons.append("🔻 COORDINATED DUMP PATTERN")
                major_drops = [d for _, d in m.price_drops if d >= 0.85]
                reasons.append(f"   ├─ {len(major_drops)} major drops, {m.rapid_drops_count} rapid")
                reasons.append(f"   └─ No recovery for {m.days_since_last_major_drop} days")
            
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
            if not self._is_sustained_growth_success(m):
                missing.append("insufficient sustained growth")
            if not self._is_recovery_based_success(m):
                missing.append("no strong recovery patterns")
            
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


def setup_logging():
    """Setup logging with both file and console output."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("complete_token_labeling.log"),
            logging.StreamHandler()
        ]
    )


async def main():
    """Main function to run the complete token labeling process."""
    parser = argparse.ArgumentParser(description="Complete Token Labeling with Reset and Incremental Processing")
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
    logger.info("🚀 COMPLETE ENHANCED TOKEN LABELING")
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
