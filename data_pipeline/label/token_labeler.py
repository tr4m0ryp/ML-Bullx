"""
Enhanced Token Classification Algorithm

The algorithm now distinguishes between 4 categories:
1. SUCCESSFUL: Tokens that show sustained growth and community adoption
   - Traditional success: 10x appreciation, 100+ holders, no major drops
   - Recovery success: Strong recovery (5x+) after early drops with sustained growth

2. RUGPULL: Tokens with coordinated dumps or no recovery patterns
   - Multiple rapid drops (within 6 hours) indicating coordinated selling
   - Major late-phase drops without recovery over 14+ days
   - Sustained declining trend after major drops

3. INACTIVE: Tokens that never gained meaningful traction
   - Very low historical appreciation (< 10x) AND very few holders (< 20) AND completely dead volume (< $10)
   - Note: Historically successful tokens are NEVER classified as inactive regardless of current activity

4. UNSUCCESSFUL: Tokens that don't meet success criteria but aren't clear rugpulls
   - Limited growth, moderate drops, or insufficient recovery

Key Improvements:
- Early-phase drops (first 7 days) are treated more leniently
- Recovery patterns are analyzed over 30-day windows  
- Current trend analysis helps distinguish declining vs recovering tokens
- Rapid vs gradual drops are differentiated
- Multiple time-based criteria prevent false rugpull classifications
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
    Enhanced version of TokenLabeler that uses on-chain data instead of external APIs.
    Drop-in replacement with the same interface and logic.
    """
    # Enhanced rugpull detection thresholds - much more specialized
    RUG_THRESHOLD = 0.85  # Increased from 70% to 85% to reduce false positives
    RUG_RAPID_DROP_HOURS = 2  # Reduced to 2 hours for true coordinated dumps
    RUG_NO_RECOVERY_DAYS = 30  # Increased to 30 days to allow more recovery time
    RUG_MIN_DROPS_FOR_PATTERN = 5  # Need at least 5 major drops to consider rugpull pattern
    RUG_FINAL_PRICE_RATIO = 0.01  # Final price must be <1% of ATH for rugpull classification
    
    # Success criteria - more comprehensive
    SUCCESS_APPRECIATION = 10.0
    SUCCESS_MIN_HOLDERS = 100
    SUCCESS_RECOVERY_MULTIPLIER = 3.0  # Reduced from 5x to 3x for more realistic recovery
    SUCCESS_MEGA_APPRECIATION = 1000.0  # 1000x+ appreciation overrides drop concerns
    SUCCESS_SUSTAINED_HIGH_RATIO = 0.10  # Current price should be >10% of ATH for mega success
    
    # Volume and activity thresholds
    INACTIVE_VOLUME_THRESHOLD = 1000  # USD volume in 24h
    INACTIVE_HOLDER_THRESHOLD = 10
    
    # Time windows for analysis
    EARLY_PHASE_DAYS = 14  # Extended to 2 weeks for more lenient early phase
    RECOVERY_ANALYSIS_DAYS = 60  # Extended to 60 days for longer recovery analysis
    MEGA_SUCCESS_DAYS = 90  # Look at 90-day performance for mega successes

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
            t.peak_price_72h = hist_data.peak_price_72h
            t.post_ath_peak_price = hist_data.post_ath_peak_price
            
            # Calculate mega-success metrics
            if t.peak_price_72h and t.post_ath_peak_price:
                t.mega_appreciation = t.post_ath_peak_price / t.peak_price_72h
            
            if t.current_price and t.post_ath_peak_price:
                t.current_vs_ath_ratio = t.current_price / t.post_ath_peak_price
            
            # Analyze historical data for drops and patterns
            hist_metrics = self._historical_metrics_from_ohlcv(hist_data.ohlcv)
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
            
            # Calculate final evaluation score
            t.final_evaluation_score = self._calculate_success_score(t)

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
            if drop_pct >= self.RUG_THRESHOLD:  # 85% instead of 70%
                is_early_phase = ts <= early_phase_end
                
                # Check if this is a rapid drop (within 2 hours of peak)
                hours_since_peak = min((ts - peak_time).total_seconds() / 3600 
                                     for peak_time, peak_val in roll if peak_val == window_peak)
                is_rapid = hours_since_peak <= self.RUG_RAPID_DROP_HOURS
                
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
                
        # Analyze recovery patterns
        for drop_id, drop_info in drop_low_tracker.items():
            drop_low = drop_info['low']
            drop_time = drop_info['time']
            
            # Look for recovery in the following 30 days
            recovery_window = drop_time + timedelta(days=self.RECOVERY_ANALYSIS_DAYS)
            recovery_df = post_df.loc[(post_df["t"] > drop_time) & (post_df["t"] <= recovery_window)]
            
            if not recovery_df.empty:
                max_price_after = recovery_df["h"].max()
                recovery_ratio = max_price_after / drop_low if drop_low > 0 else 0
                
                # Update recovery metrics
                max_recovery = max(max_recovery, recovery_ratio)
                if recovery_ratio >= self.SUCCESS_RECOVERY_MULTIPLIER:
                    has_recovery = True
                
                # Categorize drops by phase
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
        }

    # ---------- Enhanced Classification Algorithm ------------------
    def _classify(self, m: TokenMetrics) -> str:
        """
        Specialized classification that prioritizes mega-success patterns
        and is much more conservative about rugpull classification.
        """
        # Check for inactive tokens first
        if self._is_inactive(m):
            return "inactive"
        
        # Priority 1: Check for mega-successful tokens (overrides everything else)
        if self._is_mega_success(m):
            return "successful"
        
        # Priority 2: Check for traditional successful tokens
        if self._is_traditional_success(m):
            return "successful"
        
        # Priority 3: Check for recovery-based success
        if self._is_recovery_success(m):
            return "successful"
        
        # Priority 4: Very conservative rugpull detection (only clear cases)
        if self._is_clear_rugpull(m):
            return "rugpull"
        
        # Default to unsuccessful
        return "unsuccessful"

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
        
        # Only mark as inactive if it never gained any meaningful traction
        return low_appreciation and very_few_holders and completely_dead

    def _is_mega_success(self, m: TokenMetrics) -> bool:
        """
        Detect mega-successful tokens (1000x+ appreciation).
        These are almost always successful regardless of volatility.
        """
        if not m.mega_appreciation or not m.current_vs_ath_ratio:
            return False
        
        # 1000x+ appreciation with current price still reasonable vs ATH
        if (m.mega_appreciation >= self.SUCCESS_MEGA_APPRECIATION and 
            m.current_vs_ath_ratio >= self.SUCCESS_SUSTAINED_HIGH_RATIO):
            return True
        
        # Super mega success (100,000x+) - almost always successful
        if m.mega_appreciation >= 100000 and m.current_vs_ath_ratio >= 0.001:  # 0.1% of ATH
            return True
        
        # Use success score for borderline cases
        if m.final_evaluation_score and m.final_evaluation_score >= 0.7:
            return True
        
        return False

    def _is_traditional_success(self, m: TokenMetrics) -> bool:
        """Traditional success criteria (10x+ with no major sustained drops)."""
        if None in (m.peak_price_72h, m.post_ath_peak_price, m.holder_count):
            return False
        
        if m.holder_count < self.SUCCESS_MIN_HOLDERS:
            return False
        
        # Traditional success: 10x+ appreciation without sustained drops
        if (m.post_ath_peak_price / m.peak_price_72h >= self.SUCCESS_APPRECIATION and 
            not m.has_sustained_drop):
            return True
        
        return False

    def _is_recovery_success(self, m: TokenMetrics) -> bool:
        """
        Recovery-based success: Token that recovered well after drops.
        More lenient than original algorithm.
        """
        if not m.has_shown_recovery or not m.max_recovery_after_drop:
            return False
        
        # Strong recovery with reasonable holder count
        if (m.max_recovery_after_drop >= self.SUCCESS_RECOVERY_MULTIPLIER and
            m.holder_count and m.holder_count >= self.SUCCESS_MIN_HOLDERS // 2):  # Half the normal requirement
            
            # Current trend should not be strongly declining
            if m.current_trend != "declining":
                return True
        
        return False

    def _is_clear_rugpull(self, m: TokenMetrics) -> bool:
        """
        Very conservative rugpull detection - only flag clear coordinated dumps.
        Much higher threshold to prevent false positives.
        """
        if not m.price_drops:
            return False
        
        # Must have drops above the higher threshold (85%)
        major_drops = [d for _, d in m.price_drops if d >= self.RUG_THRESHOLD]
        if not major_drops:
            return False
        
        # Must have many major drops (indicating pattern, not volatility)
        if m.total_major_drops < self.RUG_MIN_DROPS_FOR_PATTERN:
            return False
        
        # Current price must be very low vs ATH (indicating no recovery)
        if m.current_vs_ath_ratio and m.current_vs_ath_ratio >= self.RUG_FINAL_PRICE_RATIO:
            return False  # Price is still reasonable vs ATH
        
        # Multiple rapid coordinated dumps
        if m.rapid_drops_count >= 3:  # Increased threshold
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
        Higher score = more successful. Score >0.7 indicates strong success.
        """
        score = 0.0
        
        # Mega appreciation bonus (most important factor)
        if m.mega_appreciation:
            if m.mega_appreciation >= 100000:  # 100,000x+
                score += 0.5
            elif m.mega_appreciation >= 10000:  # 10,000x+
                score += 0.4
            elif m.mega_appreciation >= 1000:   # 1,000x+
                score += 0.3
            elif m.mega_appreciation >= 100:    # 100x+
                score += 0.2
            elif m.mega_appreciation >= 10:     # 10x+
                score += 0.1
        
        # Current price vs ATH (sustainability factor)
        if m.current_vs_ath_ratio:
            if m.current_vs_ath_ratio >= 0.5:    # Still 50%+ of ATH
                score += 0.2
            elif m.current_vs_ath_ratio >= 0.1:  # Still 10%+ of ATH
                score += 0.15
            elif m.current_vs_ath_ratio >= 0.01: # Still 1%+ of ATH
                score += 0.1
        
        # Recovery pattern bonus
        if m.has_shown_recovery and m.max_recovery_after_drop:
            if m.max_recovery_after_drop >= 10:
                score += 0.1
            elif m.max_recovery_after_drop >= 5:
                score += 0.05
        
        # Holder count bonus
        if m.holder_count:
            if m.holder_count >= 500:
                score += 0.1
            elif m.holder_count >= 100:
                score += 0.05
        
        # Penalty for excessive drops
        if m.total_major_drops:
            if m.total_major_drops >= 20:
                score -= 0.2
            elif m.total_major_drops >= 10:
                score -= 0.1
            elif m.total_major_drops >= 5:
                score -= 0.05
        
        # Current trend bonus/penalty
        if m.current_trend == "recovering":
            score += 0.05
        elif m.current_trend == "declining":
            score -= 0.1
        
        return max(0.0, min(1.0, score))  # Clamp between 0 and 1

    def _log_classification_reasoning(self, m: TokenMetrics, label: str) -> None:
        """Log detailed reasoning for classification decision."""
        logger.info(f"Token {m.mint_address} classified as '{label}'")
        logger.info(f"  - Current price: {m.current_price}")
        logger.info(f"  - Volume 24h: {m.volume_24h}")
        logger.info(f"  - Holder count: {m.holder_count}")
        logger.info(f"  - Mega appreciation: {m.mega_appreciation}x")
        logger.info(f"  - Current vs ATH ratio: {m.current_vs_ath_ratio:.4f}")
        logger.info(f"  - Total major drops: {m.total_major_drops}")
        logger.info(f"  - Rapid drops: {m.rapid_drops_count}")
        logger.info(f"  - Max recovery: {m.max_recovery_after_drop}x")
        logger.info(f"  - Success score: {m.final_evaluation_score:.3f}")
        logger.info(f"  - Current trend: {m.current_trend}")
        
        if label == "successful":
            reasons = []
            if m.mega_appreciation and m.mega_appreciation >= 1000:
                reasons.append(f"mega appreciation ({m.mega_appreciation:.0f}x)")
            if m.current_vs_ath_ratio and m.current_vs_ath_ratio >= 0.01:
                reasons.append(f"sustained price ({m.current_vs_ath_ratio:.2%} of ATH)")
            if m.final_evaluation_score and m.final_evaluation_score >= 0.7:
                reasons.append(f"high success score ({m.final_evaluation_score:.3f})")
            logger.info(f"  → SUCCESS due to: {', '.join(reasons) if reasons else 'traditional criteria'}")
            
        elif label == "rugpull":
            reasons = []
            if m.rapid_drops_count >= 3:
                reasons.append(f"multiple coordinated dumps ({m.rapid_drops_count})")
            if m.total_major_drops >= 10:
                reasons.append(f"excessive drops ({m.total_major_drops})")
            if m.current_vs_ath_ratio and m.current_vs_ath_ratio < 0.01:
                reasons.append(f"collapsed price ({m.current_vs_ath_ratio:.4%} of ATH)")
            logger.info(f"  → RUGPULL due to: {', '.join(reasons)}")
        
        elif label == "unsuccessful":
            logger.info(f"  → UNSUCCESSFUL: Doesn't meet success criteria but not clear rugpull")

    # ────────── Per‑token flow with enhanced logging ──────────
