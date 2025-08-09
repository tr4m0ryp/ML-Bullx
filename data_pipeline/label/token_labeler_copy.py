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

# Import the rugpull vs success detector
from rugpull_vs_success_detector import analyze_token_legitimacy, RugpullVsSuccessDetector

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
    
    # New metrics for improved classification
    ath_before_72h: Optional[float] = None  # All-time high before 72h
    ath_after_72h: Optional[float] = None   # All-time high after 72h
    avg_price_post_72h: Optional[float] = None  # Average price after 72h for 30 days
    historical_avg_volume: Optional[float] = None  # Historical average volume
    peak_volume: Optional[float] = None  # Peak volume ever recorded
    max_volume_drop_ratio: Optional[float] = None  # Maximum volume drop ratio (0.0 to 1.0)
    liquidity_removal_detected: bool = False  # 60%+ volume drop detected
    pre_removal_ath: Optional[float] = None  # ATH before liquidity removal
    post_removal_peak: Optional[float] = None  # Highest price after removal
    transaction_count_daily_avg: Optional[float] = None  # Average daily transactions
    
    # Legitimacy analysis from rugpull vs success detector
    legitimacy_analysis: Optional[Dict[str, Any]] = None  # Results from rugpull detector
    
    # Final evaluation metrics
    final_evaluation_score: Optional[float] = None  # Overall success score (0.0 to 1.0)
    mega_appreciation: Optional[float] = None  # Historical max appreciation

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
    # Primary success: 72h breakthrough + sustainable growth
    SUCCESS_MIN_HOLDERS_PRIMARY = 50  # Minimum community size
    SUCCESS_MIN_VOLUME_AVG = 10000  # $10k+ average historical volume
    SUCCESS_MIN_POST_72H_AVG_RATIO = 1.5  # Average price after 72h must be 1.5x+ launch
    SUCCESS_SUSTAINED_GROWTH_DAYS = 30  # Must show sustained growth for 30 days
    
    # Secondary success: Recovery-based patterns  
    SUCCESS_RECOVERY_MIN_DROP = 0.70  # Must have dropped 70%+ to qualify for recovery
    SUCCESS_RECOVERY_MULTIPLIER = 5.0  # Must recover 5x+ from drop low
    SUCCESS_RECOVERY_SUSTAINABILITY = 21  # Recovery must be sustained 3 weeks
    SUCCESS_MIN_HOLDERS_RECOVERY = 30  # Lower bar for recovery cases
    
    # Historical success recognition (NOT override, just recognition factor)
    SUCCESS_HISTORICAL_APPRECIATION = 1000.0  # 1000x+ total appreciation (recognition)
    SUCCESS_HISTORICAL_RECOVERY = 100.0  # 100x+ recovery from major drop (recognition)
    SUCCESS_HISTORICAL_WEIGHT = 0.3  # Historical success contributes 30% to final score
    SUCCESS_LEGENDARY_APPRECIATION = 100000.0  # 100,000x+ appreciation for legendary status
    
    # === RUGPULL DETECTION ===
    # Liquidity removal patterns (primary indicator)
    RUG_LIQUIDITY_REMOVAL_THRESHOLD = 0.60  # 60%+ volume drop indicates liquidity removal
    RUG_POST_REMOVAL_ATH_RATIO = 0.20  # Post-removal peak <20% of pre-removal ATH
    RUG_MIN_APPRECIATION_FOR_RUG = 5.0  # Must have pumped first (5x+ minimum)
    RUG_FINAL_PRICE_RATIO = 0.10  # Final price <10% of pre-removal peak
    RUG_NO_RECOVERY_DAYS = 21  # No meaningful recovery for 21+ days
    
    # Secondary rugpull indicators
    RUG_DROP_THRESHOLD = 0.70  # 70%+ drop from peak
    RUG_RAPID_DROP_HOURS = 4  # Within 4 hours indicates coordination
    RUG_MIN_DROPS_FOR_PATTERN = 2  # Multiple coordinated dumps
    
    # === INACTIVE CRITERIA ===  
    INACTIVE_MAX_APPRECIATION = 2.0  # Never gained more than 2x
    INACTIVE_MAX_HOLDERS = 15  # Very few holders
    INACTIVE_MAX_TRANSACTIONS_PER_DAY = 5  # <5 transactions per day on average
    INACTIVE_MAX_PEAK_RATIO = 1.2  # Peak never exceeded 1.2x launch price
    INACTIVE_MAX_DAYS_ACTIVE = 7  # No meaningful activity after first week
    
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
        
        # Apply enhanced data collection patches if available
        if ENHANCED_DATA_COLLECTION_AVAILABLE:
            try:
                monkey_patch_data_provider(self.data_provider)
                logger.info("✅ Enhanced data collection patches applied")
            except Exception as e:
                logger.warning(f"Failed to apply enhanced data collection patches: {e}")
        
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
        """
        Check if we have any data to make a classification decision.
        
        Even tokens without current on-chain activity can be classified as:
        - INACTIVE if they never had significant activity
        - SUCCESSFUL if they have historical evidence of success
        """
        # Accept tokens that have any of these data points
        return (
            m.current_price is not None or 
            m.holder_count is not None or
            m.volume_24h is not None or
            m.launch_price is not None or
            # Accept all tokens - we can always make some classification
            # even if it's just INACTIVE for lack of data
            True
        )

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
            # Apply new 72h breakthrough metrics
            t.ath_before_72h = hist_metrics.get("ath_before_72h")
            t.ath_after_72h = hist_metrics.get("ath_after_72h")  
            t.avg_price_post_72h = hist_metrics.get("avg_price_post_72h")
            
            # Apply volume and liquidity metrics
            t.historical_avg_volume = hist_metrics.get("historical_avg_volume")
            t.peak_volume = hist_metrics.get("peak_volume")
            t.max_volume_drop_ratio = hist_metrics.get("max_volume_drop_ratio")
            t.liquidity_removal_detected = hist_metrics.get("liquidity_removal_detected", False)
            t.pre_removal_ath = hist_metrics.get("pre_removal_ath")
            t.post_removal_peak = hist_metrics.get("post_removal_peak")
            
            # Apply activity metrics
            t.transaction_count_daily_avg = hist_metrics.get("transaction_count_daily_avg")
            
            # Apply legitimacy analysis
            t.legitimacy_analysis = hist_metrics.get("legitimacy_analysis")
            
            # Legacy metrics (keep for compatibility)
            t.ath_72h_sustained = hist_metrics.get("ath_breakthrough", False)  # Use breakthrough as proxy
            t.volume_drop_24h_after_peak = hist_metrics.get("liquidity_removal_detected", False)  # Use liquidity removal as proxy
            
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
        
        # Find ATH BEFORE 72h
        ath_before_72h_df = df.loc[df["t"] <= ath_3d_end]
        if ath_before_72h_df.empty:
            return {}
        ath_before_72h = ath_before_72h_df["h"].max()
        
        # Find ATH AFTER 72h 
        ath_after_72h_df = df.loc[df["t"] > ath_3d_end]
        ath_after_72h = ath_after_72h_df["h"].max() if not ath_after_72h_df.empty else 0
        
        # Check if ATH after 72h exceeds ATH before 72h (key success indicator)
        ath_breakthrough = ath_after_72h > ath_before_72h if ath_before_72h > 0 else False
        
        # Calculate average price in 30 days after 72h for sustainability check
        post_72h_30d_end = ath_3d_end + timedelta(days=30)
        avg_price_post_72h_df = df.loc[(df["t"] > ath_3d_end) & (df["t"] <= post_72h_30d_end)]
        avg_price_post_72h = avg_price_post_72h_df["c"].mean() if not avg_price_post_72h_df.empty else None
        
        # Calculate historical volume metrics
        historical_avg_volume = df["v"].mean() if not df.empty else None
        peak_volume = df["v"].max() if not df.empty else None
        
        # Calculate maximum volume drop ratio
        max_volume_drop_ratio = None
        if peak_volume and peak_volume > 0:
            min_volume = df["v"].min()
            if min_volume is not None:
                max_volume_drop_ratio = 1.0 - (min_volume / peak_volume)

        # Post-72h data
        post_df = df.loc[df["t"] > ath_3d_end]
        if post_df.empty:
            return {}

        # Detect liquidity removal patterns (key rugpull indicator)
        liquidity_removal_detected = False
        pre_removal_ath = None
        post_removal_peak = None
        
        # Look for significant volume drops (60%+ reduction)
        if historical_avg_volume and peak_volume:
            volume_reduction_threshold = peak_volume * (1 - self.RUG_LIQUIDITY_REMOVAL_THRESHOLD)
            
            # Find periods where volume dropped significantly
            low_volume_periods = df.loc[df["v"] <= volume_reduction_threshold]
            if not low_volume_periods.empty:
                # Check if this coincided with price collapse
                removal_start = low_volume_periods["t"].iloc[0]
                pre_removal_df = df.loc[df["t"] < removal_start]
                post_removal_df = df.loc[df["t"] >= removal_start]
                
                if not pre_removal_df.empty and not post_removal_df.empty:
                    pre_removal_ath = pre_removal_df["h"].max()
                    post_removal_peak = post_removal_df["h"].max()
                    
                    # If post-removal peak is <20% of pre-removal ATH, it's likely liquidity removal
                    if pre_removal_ath > 0 and post_removal_peak < (pre_removal_ath * self.RUG_POST_REMOVAL_ATH_RATIO):
                        liquidity_removal_detected = True

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

        # Calculate average daily transaction count (if available)
        if len(df) > 0:
            total_days = (now - launch).days or 1
            transaction_count_daily_avg = len(df) / total_days
        else:
            transaction_count_daily_avg = 0

        # NEW: Perform legitimacy analysis using the rugpull vs success detector
        legitimacy_analysis = analyze_token_legitimacy(ohlcv)
        logger.debug(f"Legitimacy analysis result: {legitimacy_analysis.get('classification_hint', 'unknown')} "
                    f"(score: {legitimacy_analysis.get('overall_legitimacy_score', 0.0):.2f})")

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
            "launch_price": df["c"].iloc[0] if not df.empty else None,
            # New 72h breakthrough metrics
            "ath_before_72h": ath_before_72h,
            "ath_after_72h": ath_after_72h,
            "ath_breakthrough": ath_breakthrough,  # Key success indicator
            "avg_price_post_72h": avg_price_post_72h,
            # New volume and liquidity metrics  
            "historical_avg_volume": historical_avg_volume,
            "peak_volume": peak_volume,
            "max_volume_drop_ratio": max_volume_drop_ratio,
            "liquidity_removal_detected": liquidity_removal_detected,
            "pre_removal_ath": pre_removal_ath,
            "post_removal_peak": post_removal_peak,
            # Activity metrics
            "transaction_count_daily_avg": transaction_count_daily_avg,
            # Legitimacy analysis
            "legitimacy_analysis": legitimacy_analysis,
            # Legacy metrics for backward compatibility
            "estimated_launch_price": self._estimate_launch_price(df),
            "recent_volume": df["v"].tail(7).mean() if len(df) >= 7 else None
        }

    # ---------- Enhanced Classification Algorithm ------------------
    def _classify(self, m: TokenMetrics) -> str:
        """
        Improved classification algorithm with legitimacy analysis:
        
        1. SUCCESSFUL: Tokens with historical stable growth + breakthrough pattern + legitimacy
           - ATH after 72h exceeds ATH before 72h (breakthrough pattern)
           - Average price after 72h > 1.5x launch price (sustainable growth)
           - Reasonable community (50+ holders, $10k+ avg volume)
           - Historical success is recognition factor (30% weight), not override
           - HIGH LEGITIMACY: Legitimacy analysis indicates organic volume patterns
        
        2. RUGPULL: Tokens with clear liquidity removal patterns + low legitimacy
           - 60%+ volume drop with price collapse
           - Post-removal peak <20% of pre-removal ATH
           - No meaningful recovery for 21+ days
           - LOW LEGITIMACY: Legitimacy analysis indicates artificial/coordinated patterns
        
        3. INACTIVE: Tokens with very few/no transactions
           - <5 transactions per day average
           - <15 holders
           - Never exceeded 1.2x launch price
           - No meaningful activity after first week
        
        4. UNSUCCESSFUL: Everything else (active but not successful enough)
           - Has some transactions/activity but doesn't meet success criteria
           - Not a clear rugpull or inactive
        """
        
        # Get legitimacy analysis hint if available
        legitimacy_hint = None
        legitimacy_score = 0.5  # Default neutral score
        if m.legitimacy_analysis:
            legitimacy_hint = m.legitimacy_analysis.get("classification_hint", "unclear")
            legitimacy_score = m.legitimacy_analysis.get("overall_legitimacy_score", 0.5)
        
        # STEP 1: Check for clear rugpull patterns with legitimacy verification
        if self._is_coordinated_rugpull_with_legitimacy(m, legitimacy_hint, legitimacy_score):
            return "rugpull"
        
        # STEP 2: Check for true inactivity 
        if self._is_truly_inactive_new(m):
            return "inactive"
        
        # STEP 3: Check for success with historical recognition and legitimacy verification
        if self._is_breakthrough_success_with_legitimacy(m, legitimacy_hint, legitimacy_score):
            return "successful"
        
        # STEP 4: Everything else is unsuccessful but active
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

    def _is_coordinated_rugpull_with_legitimacy(self, m: TokenMetrics, 
                                                legitimacy_hint: Optional[str], 
                                                legitimacy_score: float) -> bool:
        """
        Enhanced rugpull detection that uses legitimacy analysis to distinguish
        between actual rugpulls and successful coins with natural volatility.
        """
        
        # If legitimacy analysis strongly suggests rugpull, trust it
        if legitimacy_hint == "rugpull_likely" or legitimacy_score <= 0.3:
            logger.debug(f"Legitimacy analysis suggests rugpull: {legitimacy_hint}, score: {legitimacy_score:.2f}")
            
            # Still need some basic rugpull indicators to confirm
            if m.liquidity_removal_detected or self._is_liquidity_removal_rugpull(m):
                logger.info(f"Confirmed rugpull: legitimacy analysis + liquidity removal detected")
                return True
                
            # Alternative confirmation: old rugpull detection methods
            if (self._is_mega_rugpull_pattern(m) or 
                self._is_coordinated_dump_pattern(m) or 
                self._is_volume_based_rugpull(m)):
                logger.info(f"Confirmed rugpull: legitimacy analysis + traditional indicators")
                return True
        
        # If legitimacy analysis suggests success, be more lenient with rugpull detection
        elif legitimacy_hint == "success_likely" or legitimacy_score >= 0.7:
            logger.debug(f"Legitimacy analysis suggests success: {legitimacy_hint}, score: {legitimacy_score:.2f}")
            
            # Only classify as rugpull if we have very strong evidence
            # (This prevents successful coins from being mislabeled due to natural volatility)
            if (m.liquidity_removal_detected and 
                m.pre_removal_ath and m.post_removal_peak and
                m.post_removal_peak < (m.pre_removal_ath * 0.1)):  # Less than 10% recovery
                
                logger.info(f"Rugpull despite legitimacy: extreme liquidity removal with <10% recovery")
                return True
        
        # For unclear cases, use traditional detection with higher thresholds
        else:
            logger.debug(f"Unclear legitimacy: {legitimacy_hint}, score: {legitimacy_score:.2f}, using traditional detection")
            
            # Use traditional methods but with higher confidence thresholds
            traditional_rugpull = (
                self._is_liquidity_removal_rugpull(m) or
                (self._is_mega_rugpull_pattern(m) and m.current_vs_ath_ratio and m.current_vs_ath_ratio < 0.01) or
                (self._is_coordinated_dump_pattern(m) and m.rapid_drops_count >= 3)
            )
            
            if traditional_rugpull:
                logger.info(f"Traditional rugpull detection with higher confidence")
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

    def _is_liquidity_removal_rugpull(self, m: TokenMetrics) -> bool:
        """
        Detect rugpulls based on liquidity removal patterns.
        Key indicator: 60%+ volume drop with price collapse and no recovery.
        """
        
        # Must have detected liquidity removal
        if not m.liquidity_removal_detected:
            return False
        
        # Must have had some initial appreciation to qualify as rugpull
        if m.launch_price and m.pre_removal_ath:
            initial_appreciation = m.pre_removal_ath / m.launch_price
            if initial_appreciation < self.RUG_MIN_APPRECIATION_FOR_RUG:
                return False
        
        # Post-removal performance must be very poor
        if m.pre_removal_ath and m.post_removal_peak:
            post_removal_ratio = m.post_removal_peak / m.pre_removal_ath
            if post_removal_ratio >= self.RUG_POST_REMOVAL_ATH_RATIO:
                return False
        
        # Current price should be significantly below pre-removal ATH
        if m.current_price and m.pre_removal_ath:
            current_ratio = m.current_price / m.pre_removal_ath
            if current_ratio >= self.RUG_FINAL_PRICE_RATIO:
                return False
        
        # Should not have recovered meaningfully in recent days
        if (m.days_since_last_major_drop is not None and 
            m.days_since_last_major_drop < self.RUG_NO_RECOVERY_DAYS and
            m.has_shown_recovery):
            return False
        
        logger.info(f"Liquidity removal rugpull: {initial_appreciation:.1f}x pump → liquidity removed → {post_removal_ratio:.2%} recovery")
        return True

    def _is_truly_inactive_new(self, m: TokenMetrics) -> bool:
        """
        Identify tokens that are truly inactive with very few/no transactions.
        Based on clearer activity metrics rather than price appreciation.
        """
        
        # Primary indicator: Very low transaction activity
        if m.transaction_count_daily_avg is not None:
            if m.transaction_count_daily_avg > self.INACTIVE_MAX_TRANSACTIONS_PER_DAY:
                return False
        
        # Secondary indicator: Very few holders (shows lack of community)
        if m.holder_count is not None:
            if m.holder_count > self.INACTIVE_MAX_HOLDERS:
                return False
        
        # Tertiary indicator: Never gained meaningful traction from launch
        peak_ratio = 1.0  # Default ratio
        if m.launch_price and m.peak_price_72h:
            peak_ratio = m.peak_price_72h / m.launch_price
            if peak_ratio > self.INACTIVE_MAX_PEAK_RATIO:
                return False
        
        # If we got here, all activity indicators suggest true inactivity
        tx_rate = m.transaction_count_daily_avg or 0
        holders = m.holder_count or 0
        logger.info(f"Truly inactive: {tx_rate:.1f} tx/day, {holders} holders, peak {peak_ratio:.1f}x launch")
        return True

    def _is_breakthrough_success(self, m: TokenMetrics) -> bool:
        """
        Check for success based on 72h breakthrough + sustainable growth pattern.
        Historical success is a recognition factor (30% weight), not override.
        """
        
        # Core requirement 1: 72h breakthrough pattern  
        # ATH after 72h must exceed ATH before 72h
        if not self._has_72h_breakthrough(m):
            return False
        
        # Core requirement 2: Sustainable growth
        # Average price after 72h must be 1.5x+ launch price
        if not self._has_sustainable_growth(m):
            return False
        
        # Core requirement 3: Community adoption
        # Minimum holders and average volume
        if not self._has_community_adoption_new(m):
            return False
        
        # Enhancement: Historical success recognition (30% bonus weight)
        historical_success_bonus = self._get_historical_success_score(m) * self.SUCCESS_HISTORICAL_WEIGHT
        
        # Base success score (70% weight) + historical bonus (30% weight)
        base_score = 0.7  # Met all core requirements
        total_score = base_score + historical_success_bonus
        
        logger.info(f"Breakthrough success: 72h breakthrough + sustainable growth + community (score: {total_score:.2f})")
        return total_score >= 0.7  # Still need to meet minimum threshold

    def _is_breakthrough_success_with_legitimacy(self, m: TokenMetrics, 
                                                 legitimacy_hint: Optional[str], 
                                                 legitimacy_score: float) -> bool:
        """
        Enhanced breakthrough success detection that uses legitimacy analysis to distinguish
        between actual success and artificial pump patterns.
        """
        
        # If legitimacy analysis strongly suggests success, be more lenient with requirements
        if legitimacy_hint == "success_likely" or legitimacy_score >= 0.7:
            logger.debug(f"Legitimacy analysis suggests success: {legitimacy_hint}, score: {legitimacy_score:.2f}")
            
            # Relaxed requirements for tokens with high legitimacy scores
            # Check if we have any growth indicators at all
            has_any_growth = (
                (m.current_price and m.launch_price and m.current_price >= m.launch_price * 2) or  # 2x+ current appreciation
                (m.peak_price_72h and m.launch_price and m.peak_price_72h >= m.launch_price * 5) or  # 5x+ peak
                (m.holder_count and m.holder_count >= 30) or  # Decent community
                (m.volume_24h and m.volume_24h >= 5000)  # Reasonable activity
            )
            
            if has_any_growth:
                logger.info(f"Success via legitimacy: high legitimacy score with basic growth indicators")
                return True
        
        # If legitimacy analysis suggests rugpull, be more strict
        elif legitimacy_hint == "rugpull_likely" or legitimacy_score <= 0.3:
            logger.debug(f"Legitimacy analysis suggests rugpull: {legitimacy_hint}, score: {legitimacy_score:.2f}")
            
            # Use much stricter requirements
            if not self._has_72h_breakthrough(m):
                return False
                
            if not self._has_sustainable_growth(m):
                return False
                
            # Require higher community adoption
            if not m.holder_count or m.holder_count < self.SUCCESS_MIN_HOLDERS_PRIMARY * 2:  # 2x holder requirement
                return False
                
            volume_to_check = m.historical_avg_volume or m.volume_24h
            if not volume_to_check or volume_to_check < self.SUCCESS_MIN_VOLUME_AVG * 2:  # 2x volume requirement
                return False
                
            logger.info(f"Success despite legitimacy concerns: met all strict requirements")
            return True
        
        # For unclear cases, use traditional breakthrough success detection
        else:
            logger.debug(f"Unclear legitimacy: {legitimacy_hint}, score: {legitimacy_score:.2f}, using traditional detection")
            return self._is_breakthrough_success(m)

    def _has_72h_breakthrough(self, m: TokenMetrics) -> bool:
        """Check if ATH after 72h exceeds ATH before 72h."""
        if not m.ath_before_72h or not m.ath_after_72h:
            return False
        
        breakthrough = m.ath_after_72h > m.ath_before_72h
        if breakthrough:
            breakthrough_ratio = m.ath_after_72h / m.ath_before_72h
            logger.debug(f"72h breakthrough: {breakthrough_ratio:.1f}x ({m.ath_after_72h} > {m.ath_before_72h})")
        return breakthrough

    def _has_sustainable_growth(self, m: TokenMetrics) -> bool:
        """Check if average price after 72h is 1.5x+ launch price."""
        if not m.launch_price or not m.avg_price_post_72h:
            return False
        
        sustainability_ratio = m.avg_price_post_72h / m.launch_price
        is_sustainable = sustainability_ratio >= self.SUCCESS_MIN_POST_72H_AVG_RATIO
        
        if is_sustainable:
            logger.debug(f"Sustainable growth: avg post-72h price {sustainability_ratio:.1f}x launch")
        return is_sustainable

    def _has_community_adoption_new(self, m: TokenMetrics) -> bool:
        """Check for community adoption using new thresholds."""
        # Holder requirement
        if not m.holder_count or m.holder_count < self.SUCCESS_MIN_HOLDERS_PRIMARY:
            return False
        
        # Volume requirement - use historical average, not current 24h
        volume_to_check = m.historical_avg_volume or m.volume_24h
        if not volume_to_check or volume_to_check < self.SUCCESS_MIN_VOLUME_AVG:
            return False
        
        logger.debug(f"Community adoption: {m.holder_count} holders, ${volume_to_check:,.0f} avg volume")
        return True

    def _has_strong_72h_performance(self, m: TokenMetrics) -> bool:
        """Check if token had strong performance in first 72h."""
        gain = self._get_72h_gain(m)
        if gain is None or gain < 2.0:  # Less than 2x gain is not strong
            return False
        
        logger.debug(f"Strong 72h performance: {gain:.1f}x gain")
        return True

    def _get_72h_gain(self, m: TokenMetrics) -> Optional[float]:
        """Calculate the 72h gain ratio (peak_72h / launch_price)."""
        if not m.launch_price or m.launch_price <= 0:
            return None
        
        # Use peak_price_72h if available, otherwise ath_after_72h
        peak_72h = m.peak_price_72h or m.ath_after_72h
        if not peak_72h or peak_72h <= 0:
            return None
        
        return peak_72h / m.launch_price

    def _get_historical_success_score(self, m: TokenMetrics) -> float:
        """
        Calculate historical success recognition score (0.0 to 1.0).
        This is NOT an override but a component in the overall success evaluation.
        """
        score = 0.0
        
        # Historical appreciation factor (0.0 to 0.5)
        if m.mega_appreciation:
            if m.mega_appreciation >= self.SUCCESS_LEGENDARY_APPRECIATION:
                score += 0.5  # Maximum historical appreciation score
            elif m.mega_appreciation >= self.SUCCESS_HISTORICAL_APPRECIATION:
                # Scale between normal historical threshold and legendary
                ratio = min(m.mega_appreciation / self.SUCCESS_LEGENDARY_APPRECIATION, 1.0)
                score += 0.3 + (0.2 * ratio)  # 0.3 to 0.5 range
            elif m.mega_appreciation >= 100:
                # Scale between 100x and historical threshold (1000x)
                ratio = min((m.mega_appreciation - 100) / (self.SUCCESS_HISTORICAL_APPRECIATION - 100), 1.0)
                score += 0.1 + (0.2 * ratio)  # 0.1 to 0.3 range
        
        # Historical recovery factor (0.0 to 0.3)
        if m.max_recovery_after_drop:
            if m.max_recovery_after_drop >= 1000000:  # 1M+ recovery
                score += 0.3  # Maximum recovery score
            elif m.max_recovery_after_drop >= self.SUCCESS_HISTORICAL_RECOVERY:
                # Scale between normal recovery threshold and extreme
                ratio = min(m.max_recovery_after_drop / 1000000, 1.0)
                score += 0.2 + (0.1 * ratio)  # 0.2 to 0.3 range
            elif m.max_recovery_after_drop >= 10:
                # Scale between 10x and historical threshold (100x)
                ratio = min((m.max_recovery_after_drop - 10) / (self.SUCCESS_HISTORICAL_RECOVERY - 10), 1.0)
                score += 0.1 * ratio  # 0.0 to 0.1 range
        
        # Current retention bonus (0.0 to 0.2)
        # Rewards tokens that still retain value from their peaks
        if hasattr(m, 'current_vs_ath_ratio') and m.current_vs_ath_ratio:
            if m.current_vs_ath_ratio >= 0.5:  # Still at 50%+ of ATH
                score += 0.2
            elif m.current_vs_ath_ratio >= 0.1:  # Still at 10%+ of ATH
                ratio = (m.current_vs_ath_ratio - 0.1) / 0.4  # Scale 0.1-0.5 to 0.0-1.0
                score += 0.1 + (0.1 * ratio)  # 0.1 to 0.2 range
        
        # Cap at 1.0 and return
        return min(score, 1.0)

    def _has_sustained_performance(self, m: TokenMetrics) -> bool:
        """Check if performance was sustained after 72h period."""
        # Check if average price post-72h is well above launch price
        if m.avg_price_post_72h and m.launch_price and m.launch_price > 0:
            sustained_ratio = m.avg_price_post_72h / m.launch_price
            if sustained_ratio >= self.SUCCESS_MIN_POST_72H_AVG_RATIO:
                logger.debug(f"Sustained performance: {sustained_ratio:.1f}x launch price maintained")
                return True
        
        # Alternative: Check if current price is reasonable compared to peaks
        # Use post_ath_peak_price (which is the main ATH) for comparison
        if m.current_price and m.post_ath_peak_price and m.post_ath_peak_price > 0:
            price_retention = m.current_price / m.post_ath_peak_price
            if price_retention >= 0.1:  # Still holding 10%+ of ATH
                logger.debug(f"Sustained performance: {price_retention:.1%} of ATH retained")
                return True
        
        return False

    def _calculate_success_score(self, m: TokenMetrics) -> float:
        """Calculate a comprehensive success score for the token (0.0 to 1.0)."""
        score = 0.0
        max_score = 0.0
        
        # 72h performance (0.3 weight)
        if self._has_strong_72h_performance(m):
            score += 0.3
        max_score += 0.3
        
        # Sustained performance (0.25 weight)
        if self._has_sustained_performance(m):
            score += 0.25
        max_score += 0.25
        
        # Community adoption (0.2 weight)
        if self._has_community_adoption_new(m):
            score += 0.2
        max_score += 0.2
        
        # Historical success recognition (0.15 weight)
        historical_score = self._get_historical_success_score(m)
        score += 0.15 * historical_score
        max_score += 0.15
        
        # Legitimacy analysis (0.1 weight)
        if m.legitimacy_analysis and m.legitimacy_analysis.get('legitimacy_score'):
            legitimacy_normalized = min(m.legitimacy_analysis['legitimacy_score'] / 10.0, 1.0)
            score += 0.1 * legitimacy_normalized
        max_score += 0.1
        
        # Normalize to 0.0-1.0 range
        if max_score > 0:
            return score / max_score
        return 0.0

    def _estimate_launch_price(self, df) -> Optional[float]:
        """Estimate launch price from historical data DataFrame."""
        if df is None or df.empty:
            return None
        
        # Try to get the earliest price from the dataframe
        if 'c' in df.columns:  # Close price
            earliest_prices = df['c'].head(5)  # Look at first 5 data points
            valid_prices = earliest_prices[earliest_prices > 0]
            if not valid_prices.empty:
                return valid_prices.iloc[0]
        
        # Fallback to 'o' (open) or 'l' (low)
        for col in ['o', 'l']:
            if col in df.columns:
                earliest_prices = df[col].head(5)
                valid_prices = earliest_prices[earliest_prices > 0]
                if not valid_prices.empty:
                    return valid_prices.iloc[0]
        
        return None

    def _log_classification_reasoning(self, m: TokenMetrics, label: str):
        """Log detailed reasoning for why a token received its classification with comprehensive variable details."""
        logger.info(f"Classification result: {label.upper()}")
        
        # First, log ALL scraped/calculated variables for transparency
        self._log_comprehensive_token_metrics(m)
        
        # Then log classification-specific reasoning
        if label == "inactive":
            reasons = []
            reasons.append("💤 INACTIVE (no meaningful on-chain activity)")
            
            # Explain inactivity reasons with thresholds
            if not m.holder_count or m.holder_count == 0:
                reasons.append(f"   ├─ Zero holders detected (threshold: >{self.INACTIVE_MAX_HOLDERS})")
            if not m.historical_avg_volume or m.historical_avg_volume < 1000:
                avg_vol = m.historical_avg_volume or 0
                reasons.append(f"   ├─ Minimal volume: ${avg_vol:,.0f} average (threshold: >$1000)")
            if not m.post_ath_peak_price or m.post_ath_peak_price <= (m.launch_price or 0):
                peak_ratio = (m.post_ath_peak_price or 0) / (m.launch_price or 1)
                reasons.append(f"   ├─ No price appreciation: {peak_ratio:.1f}x peak/launch (threshold: >{self.INACTIVE_MAX_PEAK_RATIO}x)")
            if m.transaction_count_daily_avg and m.transaction_count_daily_avg <= self.INACTIVE_MAX_TRANSACTIONS_PER_DAY:
                reasons.append(f"   └─ Low transaction activity: {m.transaction_count_daily_avg:.1f}/day (threshold: >{self.INACTIVE_MAX_TRANSACTIONS_PER_DAY}/day)")
            
            for reason in reasons:
                logger.info(f"  {reason}")
                
        elif label == "rugpull":
            reasons = []
            reasons.append("🚨 RUGPULL (coordinated malicious dump detected)")
            
            # Detailed rugpull analysis
            if m.liquidity_removal_detected:
                reasons.append(f"   ├─ 🔴 LIQUIDITY REMOVAL DETECTED")
                if m.max_volume_drop_ratio:
                    reasons.append(f"   │   ├─ Volume drop: {m.max_volume_drop_ratio:.1%} (threshold: >{self.RUG_LIQUIDITY_REMOVAL_THRESHOLD:.0%})")
                if m.pre_removal_ath and m.post_removal_peak:
                    recovery_ratio = m.post_removal_peak / m.pre_removal_ath
                    reasons.append(f"   │   └─ Post-removal recovery: {recovery_ratio:.1%} of pre-removal ATH (threshold: <{self.RUG_POST_REMOVAL_ATH_RATIO:.0%})")
            
            # Legitimacy analysis details
            if m.legitimacy_analysis:
                legit = m.legitimacy_analysis
                reasons.append(f"   ├─ 📊 LEGITIMACY ANALYSIS:")
                if 'legitimacy_score' in legit:
                    reasons.append(f"   │   ├─ Overall legitimacy: {legit['legitimacy_score']:.1f}/10")
                if 'volume_drop_recovery' in legit:
                    reasons.append(f"   │   ├─ Volume recovery: {legit.get('volume_drop_recovery', 0):.1%}")
                if 'transaction_pattern_score' in legit:
                    reasons.append(f"   │   ├─ Transaction pattern: {legit.get('transaction_pattern_score', 0):.1f}/10")
                if 'classification_hint' in legit:
                    reasons.append(f"   │   └─ AI hint: {legit['classification_hint']}")
            
            # Price collapse metrics
            if m.mega_appreciation and m.current_vs_ath_ratio:
                reasons.append(f"   ├─ 📉 PRICE COLLAPSE:")
                reasons.append(f"   │   ├─ Peak appreciation: {m.mega_appreciation:.0f}x (threshold: >{self.RUG_MIN_APPRECIATION_FOR_RUG:.0f}x)")
                reasons.append(f"   │   ├─ Current vs ATH: {m.current_vs_ath_ratio:.4%}")
                reasons.append(f"   │   └─ Collapse ratio: {1/m.current_vs_ath_ratio:.0f}x drop from peak")
            
            # Drop pattern analysis
            if m.rapid_drops_count or m.price_drops:
                reasons.append(f"   ├─ 🏃 DROP PATTERNS:")
                if m.rapid_drops_count:
                    reasons.append(f"   │   ├─ Rapid drops: {m.rapid_drops_count} (threshold: <{self.RUG_RAPID_DROP_HOURS}h)")
                if m.max_recovery_after_drop:
                    reasons.append(f"   │   ├─ Max recovery: {m.max_recovery_after_drop:.1f}x")
                if m.days_since_last_major_drop:
                    reasons.append(f"   │   └─ Days since last drop: {m.days_since_last_major_drop} (threshold: >{self.RUG_NO_RECOVERY_DAYS})")
            
            # Volume death indicators
            if m.volume_24h is not None or m.historical_avg_volume:
                vol_24h = m.volume_24h or 0
                vol_avg = m.historical_avg_volume or 0
                reasons.append(f"   └─ 💀 VOLUME DEATH:")
                reasons.append(f"       ├─ Current 24h volume: ${vol_24h:,.0f}")
                reasons.append(f"       └─ Historical avg volume: ${vol_avg:,.0f}")
            
            for reason in reasons:
                logger.info(f"  {reason}")
                
        elif label == "successful":
            reasons = []
            reasons.append("🚀 SUCCESSFUL (meets all success criteria)")
            
            # 72H Breakthrough Analysis
            if self._has_72h_breakthrough(m):
                reasons.append("📈 72H BREAKTHROUGH DETECTED")
                if m.ath_before_72h and m.ath_after_72h:
                    breakthrough_ratio = m.ath_after_72h / m.ath_before_72h
                    reasons.append(f"   ├─ ATH breakthrough: {breakthrough_ratio:.1f}x")
                    reasons.append(f"   ├─ Pre-72h ATH: ${m.ath_before_72h:.8f}")
                    reasons.append(f"   └─ Post-72h ATH: ${m.ath_after_72h:.8f}")
            
            # Sustainable Growth Analysis
            if self._has_sustainable_growth(m):
                reasons.append("📊 SUSTAINABLE GROWTH CONFIRMED")
                if m.avg_price_post_72h and m.launch_price:
                    sustainability_ratio = m.avg_price_post_72h / m.launch_price
                    reasons.append(f"   ├─ Sustained {sustainability_ratio:.1f}x launch price (threshold: >{self.SUCCESS_MIN_POST_72H_AVG_RATIO:.1f}x)")
                    reasons.append(f"   ├─ Launch price: ${m.launch_price:.8f}")
                    reasons.append(f"   ├─ Avg post-72h price: ${m.avg_price_post_72h:.8f}")
                    reasons.append(f"   └─ Sustained for {self.SUCCESS_SUSTAINED_GROWTH_DAYS} days")
            
            # Community Adoption Analysis
            if self._has_community_adoption_new(m):
                reasons.append("👥 COMMUNITY ADOPTION VERIFIED")
                reasons.append(f"   ├─ Holders: {m.holder_count or 0} (threshold: >{self.SUCCESS_MIN_HOLDERS_PRIMARY})")
                vol_display = m.historical_avg_volume or m.volume_24h or 0
                reasons.append(f"   ├─ Avg volume: ${vol_display:,.0f} (threshold: >${self.SUCCESS_MIN_VOLUME_AVG:,.0f})")
                if m.transaction_count_daily_avg:
                    reasons.append(f"   └─ Daily transactions: {m.transaction_count_daily_avg:.1f}")
            
            # Historical Achievements
            if m.mega_appreciation and m.mega_appreciation >= self.SUCCESS_HISTORICAL_APPRECIATION:
                reasons.append(f"🏆 MEGA APPRECIATION: {m.mega_appreciation:.0f}x total gains")
                reasons.append(f"   └─ Exceeds historical threshold: {self.SUCCESS_HISTORICAL_APPRECIATION:.0f}x")
            
            if m.max_recovery_after_drop and m.max_recovery_after_drop >= self.SUCCESS_HISTORICAL_RECOVERY:
                reasons.append(f"💪 RECOVERY CHAMPION: {m.max_recovery_after_drop:.0f}x recovery")
                reasons.append(f"   └─ Exceeds recovery threshold: {self.SUCCESS_HISTORICAL_RECOVERY:.0f}x")
            
            # Legitimacy Verification
            if m.legitimacy_analysis and m.legitimacy_analysis.get('legitimacy_score', 0) >= 7:
                legit_score = m.legitimacy_analysis.get('legitimacy_score', 0)
                reasons.append(f"✅ HIGH LEGITIMACY: {legit_score:.1f}/10 score")
                if 'classification_hint' in m.legitimacy_analysis:
                    reasons.append(f"   └─ AI classification hint: {m.legitimacy_analysis['classification_hint']}")
            
            for reason in reasons:
                logger.info(f"  {reason}")
                
        elif label == "unsuccessful":
            reasons = []
            reasons.append("❌ UNSUCCESSFUL (doesn't meet success criteria)")
            
            # Detailed analysis of what's missing
            reasons.append("🔍 CRITERIA ANALYSIS:")
            
            # 72h performance check
            gain_72h = self._get_72h_gain(m)
            has_72h_perf = self._has_strong_72h_performance(m)
            reasons.append(f"   ├─ 72h performance: {'✅' if has_72h_perf else '❌'}")
            if gain_72h:
                reasons.append(f"   │   └─ Actual gain: {gain_72h:.1f}x")
            
            # Sustained performance check
            has_sustained = self._has_sustained_performance(m)
            reasons.append(f"   ├─ Sustained performance: {'✅' if has_sustained else '❌'}")
            if m.avg_price_post_72h and m.launch_price:
                sustained_ratio = m.avg_price_post_72h / m.launch_price
                reasons.append(f"   │   └─ Sustainability ratio: {sustained_ratio:.1f}x (need >{self.SUCCESS_MIN_POST_72H_AVG_RATIO:.1f}x)")
            
            # Community adoption check
            has_community = self._has_community_adoption_new(m)
            reasons.append(f"   ├─ Community adoption: {'✅' if has_community else '❌'}")
            reasons.append(f"   │   ├─ Holders: {m.holder_count or 0} (need >{self.SUCCESS_MIN_HOLDERS_PRIMARY})")
            vol_display = m.historical_avg_volume or m.volume_24h or 0
            reasons.append(f"   │   └─ Avg volume: ${vol_display:,.0f} (need >${self.SUCCESS_MIN_VOLUME_AVG:,.0f})")
            
            # Total appreciation check
            reasons.append(f"   └─ Total appreciation: {'✅' if (m.mega_appreciation and m.mega_appreciation >= 1000) else '❌'}")
            if m.mega_appreciation:
                reasons.append(f"       └─ Actual: {m.mega_appreciation:.0f}x (need >1000x for historical recognition)")
            
            # Show what it did achieve
            achievements = []
            if gain_72h and gain_72h >= 1.5:
                achievements.append(f"{gain_72h:.1f}x in 72h")
            if m.holder_count and m.holder_count >= 10:
                achievements.append(f"{m.holder_count} holders")
            if m.mega_appreciation and m.mega_appreciation >= 100:
                achievements.append(f"{m.mega_appreciation:.0f}x total gains")
            
            if achievements:
                reasons.append(f"🎯 POSITIVE ASPECTS: {', '.join(achievements)}")
            
            for reason in reasons:
                logger.info(f"  {reason}")

    def _log_comprehensive_token_metrics(self, m: TokenMetrics):
        """Log all scraped and calculated variables for complete transparency."""
        logger.info("📊 COMPREHENSIVE TOKEN METRICS:")
        logger.info("═" * 60)
        
        # Helper function to format values safely
        def safe_format_price(value, default="N/A"):
            if value is None:
                return default
            try:
                return f"${value:.8f}" if isinstance(value, (int, float)) else default
            except:
                return default
        
        def safe_format_number(value, decimals=0, default="N/A"):
            if value is None:
                return default
            try:
                if decimals == 0:
                    return f"{value:,}" if isinstance(value, (int, float)) else default
                else:
                    return f"{value:,.{decimals}f}" if isinstance(value, (int, float)) else default
            except:
                return default
        
        def safe_format_percentage(value, default="N/A"):
            if value is None:
                return default
            try:
                return f"{value:.4%}" if isinstance(value, (int, float)) else default
            except:
                return default
        
        def safe_format_ratio(value, default="N/A"):
            if value is None:
                return default
            try:
                return f"{value:.1f}x" if isinstance(value, (int, float)) else default
            except:
                return default
        
        # Basic Price Data
        logger.info("💰 PRICE METRICS:")
        logger.info(f"   ├─ Launch price: {safe_format_price(m.launch_price)}")
        logger.info(f"   ├─ Current price: {safe_format_price(m.current_price)}")
        logger.info(f"   ├─ Peak 72h: {safe_format_price(m.peak_price_72h)}")
        logger.info(f"   ├─ Post-ATH peak: {safe_format_price(m.post_ath_peak_price)}")
        logger.info(f"   ├─ ATH before 72h: {safe_format_price(m.ath_before_72h)}")
        logger.info(f"   └─ ATH after 72h: {safe_format_price(m.ath_after_72h)}")
        
        # Volume Metrics
        logger.info("📈 VOLUME METRICS:")
        logger.info(f"   ├─ Volume 24h: {safe_format_number(m.volume_24h, 0) if m.volume_24h else 'N/A'}")
        logger.info(f"   ├─ Historical avg: {safe_format_number(m.historical_avg_volume, 0) if m.historical_avg_volume else 'N/A'}")
        logger.info(f"   ├─ Peak volume: {safe_format_number(m.peak_volume, 0) if m.peak_volume else 'N/A'}")
        logger.info(f"   └─ Max drop ratio: {safe_format_percentage(m.max_volume_drop_ratio) if m.max_volume_drop_ratio else 'N/A'}")
        
        # Community Metrics  
        logger.info("👥 COMMUNITY METRICS:")
        logger.info(f"   ├─ Holder count: {safe_format_number(m.holder_count, 0) if m.holder_count else 'N/A'}")
        logger.info(f"   ├─ Market cap: {safe_format_number(m.market_cap, 0) if m.market_cap else 'N/A'}")
        logger.info(f"   └─ Daily transactions: {safe_format_number(m.transaction_count_daily_avg, 1) if m.transaction_count_daily_avg else 'N/A'}")
        
        # Performance Ratios
        logger.info("📊 PERFORMANCE RATIOS:")
        if m.current_price and m.launch_price and m.launch_price > 0:
            current_launch_ratio = m.current_price / m.launch_price
            logger.info(f"   ├─ Current/Launch: {safe_format_ratio(current_launch_ratio)}")
        else:
            logger.info(f"   ├─ Current/Launch: N/A")
        logger.info(f"   ├─ Current vs ATH: {safe_format_percentage(m.current_vs_ath_ratio) if m.current_vs_ath_ratio else 'N/A'}")
        logger.info(f"   ├─ Mega appreciation: {safe_format_ratio(m.mega_appreciation) if m.mega_appreciation else 'N/A'}")
        logger.info(f"   └─ Max recovery: {safe_format_ratio(m.max_recovery_after_drop) if m.max_recovery_after_drop else 'N/A'}")
        
        # Drop Analysis
        logger.info("📉 DROP ANALYSIS:")
        logger.info(f"   ├─ Rapid drops: {m.rapid_drops_count or 0}")
        logger.info(f"   ├─ Has sustained drop: {m.has_sustained_drop}")
        logger.info(f"   ├─ Days since last drop: {safe_format_number(m.days_since_last_major_drop, 0) if m.days_since_last_major_drop else 'N/A'}")
        logger.info(f"   └─ Has shown recovery: {m.has_shown_recovery}")
        
        # Liquidity Analysis
        logger.info("💧 LIQUIDITY ANALYSIS:")
        logger.info(f"   ├─ Removal detected: {m.liquidity_removal_detected}")
        logger.info(f"   ├─ Pre-removal ATH: {safe_format_price(m.pre_removal_ath)}")
        logger.info(f"   └─ Post-removal peak: {safe_format_price(m.post_removal_peak)}")
        
        # Trend Analysis
        logger.info("📈 TREND ANALYSIS:")
        logger.info(f"   ├─ Current trend: {m.current_trend or 'N/A'}")
        logger.info(f"   ├─ ATH 72h sustained: {m.ath_72h_sustained}")
        logger.info(f"   └─ Avg post-72h price: {safe_format_price(m.avg_price_post_72h)}")
        
        # Legitimacy Analysis Summary
        if m.legitimacy_analysis:
            logger.info("🔍 LEGITIMACY ANALYSIS:")
            legit = m.legitimacy_analysis
            legitimacy_score = legit.get('legitimacy_score', 'N/A')
            if legitimacy_score != 'N/A' and isinstance(legitimacy_score, (int, float)):
                logger.info(f"   ├─ Overall score: {legitimacy_score:.1f}/10")
            else:
                logger.info(f"   ├─ Overall score: N/A")
            logger.info(f"   ├─ Classification hint: {legit.get('classification_hint', 'N/A')}")
            
            volume_recovery = legit.get('volume_drop_recovery', 'N/A')
            if volume_recovery != 'N/A' and isinstance(volume_recovery, (int, float)):
                logger.info(f"   ├─ Volume recovery: {volume_recovery:.1%}")
            else:
                logger.info(f"   ├─ Volume recovery: N/A")
            
            tx_pattern_score = legit.get('transaction_pattern_score', 'N/A')
            if tx_pattern_score != 'N/A' and isinstance(tx_pattern_score, (int, float)):
                logger.info(f"   └─ Transaction pattern: {tx_pattern_score:.1f}/10")
            else:
                logger.info(f"   └─ Transaction pattern: N/A")
        else:
            logger.info("🔍 LEGITIMACY ANALYSIS: Not performed")
        
        # Additional diagnostic info
        logger.info("🔧 DIAGNOSTIC INFO:")
        has_price_data = bool(m.current_price or m.launch_price or m.peak_price_72h)
        has_volume_data = bool(m.volume_24h or m.historical_avg_volume)
        has_holder_data = bool(m.holder_count)
        has_historical_data = bool(m.ath_before_72h or m.ath_after_72h)
        
        logger.info(f"   ├─ Has price data: {has_price_data}")
        logger.info(f"   ├─ Has volume data: {has_volume_data}")
        logger.info(f"   ├─ Has holder data: {has_holder_data}")
        logger.info(f"   └─ Has historical data: {has_historical_data}")
        
        logger.info("═" * 60)

# Enhanced data collection patches
try:
    from enhanced_data_collection import monkey_patch_data_provider
    ENHANCED_DATA_COLLECTION_AVAILABLE = True
except ImportError:
    ENHANCED_DATA_COLLECTION_AVAILABLE = False
    logger.warning("Enhanced data collection not available - using original methods")
