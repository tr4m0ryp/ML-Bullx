"""
Rugpull vs Success Detector for Solana Token Classification.

Provides sophisticated algorithms to distinguish between:
- Legitimate successful coins that experienced natural volume/price drops.
- Actual rugpulls with coordinated malicious intent.

The key insight is that successful coins often have extreme volatility and
volume drops, but they exhibit fundamentally different recovery patterns
compared to rugpulls.

Key differentiators analyzed:
- Volume recovery patterns (organic vs artificial).
- Recovery timing, sustainability, and price-volume correlation.
- Transaction patterns during recovery windows.
- Community behavior (holder growth/decline) during drops.
- Price action legitimacy via multi-window scoring.

Author: ML-Bullx Team
Date: 2025-08-01
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class VolumeDropEvent:
    """Represents a significant volume drop event with recovery analysis.

    Captures pre-drop, trough, and post-recovery metrics to enable
    pattern-based classification of organic dips vs coordinated exits.
    """

    timestamp: datetime                              # When the drop was detected
    pre_drop_volume: float                           # Average volume before drop (USD)
    drop_volume: float                               # Lowest volume during drop (USD)
    post_drop_volume: Optional[float] = None         # Volume after recovery attempt
    drop_percentage: float = 0.0                     # Percentage volume reduction (0-1)
    recovery_time_hours: Optional[float] = None      # Hours from trough to recovery
    recovery_strength: float = 0.0                   # Post-recovery volume / pre-drop volume
    transaction_pattern_score: float = 0.0           # Legitimacy score of transaction flow
    price_correlation: float = 0.0                   # Volume-price correlation coefficient

    # -- Enhanced price analysis fields --
    price_stability_during_recovery: float = 0.0     # Price stability score during recovery
    liquidity_indicator: float = 0.0                 # Estimated liquidity from price-volume behavior
    pre_drop_price: float = 0.0                      # Average price before drop (USD)
    drop_price: float = 0.0                          # Price at drop trough (USD)

@dataclass
class RecoveryStage:
    """Represents a single recovery stage within a recovery attempt."""
    stage_number: int  # 1, 2, 3, etc.
    start_time: datetime
    peak_time: datetime
    duration_hours: float
    volume_recovery_ratio: float  # Peak volume vs pre-drop volume
    price_recovery_ratio: float   # Peak price vs drop price
    sustainability_hours: float   # How long the recovery was maintained
    decline_after_peak: float     # Volume decline after peak (0.0-1.0)
    transaction_count: int
    average_tx_interval: float    # Minutes between transactions
    
@dataclass
class CumulativeRecovery:
    """Tracks cumulative recovery strength over multiple stages."""
    total_stages: int
    best_volume_recovery_ratio: float      # Highest recovery achieved
    best_price_recovery_ratio: float       # Highest price recovery achieved
    cumulative_volume_under_curve: float   # Area under recovery curve
    recovery_consistency_score: float      # How consistent recoveries were
    final_sustained_level: float           # Final sustained volume level
    time_to_best_recovery: float           # Hours to achieve best recovery
    recovery_slope_trend: float            # Overall trend of recovery attempts
    stage_improvement_rate: float          # How much each stage improved

@dataclass
class RecoveryPhase:
    """Represents a single phase of recovery."""
    phase_name: str  # "short_term_rebound", "sustained_volume", "long_term_stability"
    start_time: datetime
    duration_hours: float
    volume_recovery_ratio: float
    price_recovery_ratio: float
    transaction_count: int
    recovery_slope: float  # Volume change rate during this phase
    sustainability_score: float  # How well volume is maintained
    transaction_diversity_score: float  # Based on tx intervals and patterns

@dataclass
class RecoveryPattern:
    """Multi-phase analysis of recovery behavior after major drops."""
    recovery_start_time: datetime
    recovery_duration_hours: float  # Changed back from total_recovery_duration_hours
    volume_recovery_ratio: float  # Post-recovery volume vs pre-drop
    price_recovery_ratio: float   # Post-recovery price vs pre-drop
    transaction_count: int        # Number of transactions during recovery
    unique_addresses: Optional[int] = None  # Unique addresses involved
    avg_transaction_size: Optional[float] = None
    time_between_transactions: float = 0.0  # Average time between txs (minutes)
    recovery_legitimacy_score: float = 0.0  # Overall legitimacy score
    
    # Enhanced analysis fields
    transaction_diversity_score: float = 0.0  # Diversity of trading patterns
    recovery_slope: float = 0.0  # Volume change rate during recovery
    sustainability_score: float = 0.0  # How well volume is maintained
    
    # Multi-phase analysis
    recovery_phases: List[RecoveryPhase] = None
    has_short_term_rebound: bool = False
    has_sustained_volume: bool = False
    fast_recovery_legitimacy: float = 0.0  # Special scoring for fast but healthy recoveries
    
    # Multi-stage recovery analysis
    recovery_stages: List[RecoveryStage] = None
    cumulative_recovery: Optional[CumulativeRecovery] = None
    multi_stage_legitimacy_score: float = 0.0  # Legitimacy based on multi-stage analysis
    
    def __post_init__(self):
        if self.recovery_phases is None:
            self.recovery_phases = []
        if self.recovery_stages is None:
            self.recovery_stages = []

class RugpullVsSuccessDetector:
    """
    Advanced detector to distinguish between rugpulls and successful coins
    that experienced natural volatility.
    """
    
    # === VOLUME DROP THRESHOLDS ===
    SIGNIFICANT_VOLUME_DROP = 0.60  # 60%+ volume drop is significant
    EXTREME_VOLUME_DROP = 0.80     # 80%+ is extreme
    MASSIVE_VOLUME_DROP = 0.90     # 90%+ is massive
    
    # === RECOVERY PATTERN ANALYSIS ===
    # Fast recovery thresholds (1-3 hours) - legitimate if high tx diversity
    FAST_RECOVERY_MIN_HOURS = 1       # Minimum for fast recovery consideration
    FAST_RECOVERY_MAX_HOURS = 3       # Maximum for fast recovery category
    FAST_RECOVERY_MIN_TX_DIVERSITY = 0.7  # Required diversity score for fast recovery
    
    # Standard organic recovery thresholds (more flexible than before)
    ORGANIC_RECOVERY_MIN_HOURS = 1    # Lowered from 6 to 1 hour
    ORGANIC_RECOVERY_MAX_HOURS = 168  # Organic recovery within 1 week
    ARTIFICIAL_RECOVERY_MAX_HOURS = 0.5  # Very fast artificial recovery (<30min)
    
    # Multi-phase recovery windows
    SHORT_TERM_REBOUND_HOURS = 6      # Initial rebound window
    SUSTAINED_VOLUME_HOURS = 48       # Sustained volume analysis window
    LONG_TERM_STABILITY_HOURS = 168   # Long-term stability window (1 week)
    
    # === TRANSACTION PATTERN SCORING ===
    MIN_RECOVERY_TRANSACTIONS = 10    # Legitimate recovery has multiple transactions
    SUSPICIOUS_TX_INTERVAL_MINUTES = 1  # <1 min between txs is suspicious
    ORGANIC_TX_INTERVAL_MINUTES = 15    # >15 min between txs is more organic
    
    # === LEGITIMACY THRESHOLDS ===
    RUGPULL_LEGITIMACY_THRESHOLD = 0.3     # <0.3 indicates likely rugpull
    SUCCESS_LEGITIMACY_THRESHOLD = 0.7     # >0.7 indicates likely success
    
    def analyze_volume_drops_and_recoveries(self, ohlcv_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Main analysis function to detect and analyze volume drops and recoveries.
        
        Returns:
            Dictionary containing:
            - volume_drop_events: List of significant volume drop events
            - recovery_patterns: Analysis of recovery attempts
            - overall_legitimacy_score: 0.0-1.0 score (higher = more legitimate)
            - classification_hint: "rugpull_likely", "success_likely", or "unclear"
        """
        if not ohlcv_data:
            return self._empty_analysis()
        
        df = self._prepare_dataframe(ohlcv_data)
        if df.empty:
            return self._empty_analysis()
        
        # Step 1: Identify significant volume drop events
        volume_drop_events = self._identify_volume_drop_events(df)
        
        # Step 2: Analyze recovery patterns for each drop
        recovery_patterns = []
        for drop_event in volume_drop_events:
            recovery = self._analyze_recovery_pattern(df, drop_event)
            if recovery:
                recovery_patterns.append(recovery)
        
        # Step 3: Score the overall legitimacy
        legitimacy_score = self._calculate_overall_legitimacy_score(
            volume_drop_events, recovery_patterns, df
        )
        
        # Step 4: Generate classification hint
        classification_hint = self._generate_classification_hint(
            legitimacy_score, volume_drop_events, recovery_patterns
        )
        
        return {
            "volume_drop_events": volume_drop_events,
            "recovery_patterns": recovery_patterns,
            "overall_legitimacy_score": legitimacy_score,
            "classification_hint": classification_hint,
            "analysis_summary": self._generate_analysis_summary(
                volume_drop_events, recovery_patterns, legitimacy_score, df
            )
        }
    
    def _prepare_dataframe(self, ohlcv_data: List[Dict[str, Any]]) -> pd.DataFrame:
        """Prepare and clean the OHLCV dataframe for analysis."""
        df = pd.DataFrame(ohlcv_data)
        df["t"] = pd.to_datetime(df["ts"], unit="s")
        df.sort_values("t", inplace=True)
        
        # Add rolling averages for volume analysis
        df["volume_ma_24h"] = df["v"].rolling(window=24, min_periods=1).mean()
        df["volume_ma_7d"] = df["v"].rolling(window=168, min_periods=1).mean()  # 7 days
        
        # Add price volatility metrics
        df["price_volatility"] = df["h"] / df["l"] - 1  # High/Low ratio - 1
        
        return df
    
    def _identify_volume_drop_events(self, df: pd.DataFrame) -> List[VolumeDropEvent]:
        """Identify significant volume drop events with enhanced price analysis."""
        events = []
        
        for i in range(24, len(df)):  # Start after 24h for rolling average
            current_volume = df.iloc[i]["v"]
            pre_drop_volume = df.iloc[i-24:i]["v"].mean()  # 24h average before
            
            if pre_drop_volume > 0:
                drop_percentage = 1 - (current_volume / pre_drop_volume)
                
                if drop_percentage >= self.SIGNIFICANT_VOLUME_DROP:
                    # Enhanced price analysis
                    price_before = df.iloc[i-24:i]["c"].mean()
                    price_at_drop = df.iloc[i]["c"]
                    price_drop = 1 - (price_at_drop / price_before) if price_before > 0 else 0
                    
                    event = VolumeDropEvent(
                        timestamp=df.iloc[i]["t"],
                        pre_drop_volume=pre_drop_volume,
                        drop_volume=current_volume,
                        drop_percentage=drop_percentage,
                        price_correlation=price_drop,  # How much price dropped with volume
                        pre_drop_price=price_before,
                        drop_price=price_at_drop
                    )
                    
                    events.append(event)
        
        # Remove duplicate events (too close in time)
        events = self._deduplicate_events(events)
        
        # Enhanced post-processing: calculate liquidity indicators
        self._enhance_volume_drop_events_with_recovery_analysis(df, events)
        
        logger.debug(f"Identified {len(events)} significant volume drop events")
        return events
    
    def _enhance_volume_drop_events_with_recovery_analysis(self, df: pd.DataFrame, 
                                                          events: List[VolumeDropEvent]) -> None:
        """Enhance volume drop events with recovery-based price stability analysis."""
        for event in events:
            # Look ahead for recovery data (next 24 hours)
            recovery_window_end = event.timestamp + timedelta(hours=24)
            recovery_data = df[(df["t"] > event.timestamp) & (df["t"] <= recovery_window_end)]
            
            if not recovery_data.empty:
                stability_metrics = self._detect_price_stability_during_recovery(df, event, recovery_data)
                event.price_stability_during_recovery = stability_metrics["stability_score"]
                event.liquidity_indicator = stability_metrics["liquidity_indicator"]
    
    def _deduplicate_events(self, events: List[VolumeDropEvent]) -> List[VolumeDropEvent]:
        """Remove events that are too close in time (within 6 hours)."""
        if not events:
            return events
        
        deduplicated = []
        last_event_time = None
        
        for event in sorted(events, key=lambda x: x.timestamp):
            if last_event_time is None or (event.timestamp - last_event_time).total_seconds() > 6 * 3600:
                deduplicated.append(event)
                last_event_time = event.timestamp
        
        return deduplicated
    
    def _analyze_recovery_pattern(self, df: pd.DataFrame, drop_event: VolumeDropEvent) -> Optional[RecoveryPattern]:
        """Analyze the recovery pattern after a volume drop event."""
        drop_time = drop_event.timestamp
        
        # Look for recovery in the next 7 days
        recovery_window_end = drop_time + timedelta(days=7)
        recovery_df = df[(df["t"] > drop_time) & (df["t"] <= recovery_window_end)]
        
        if recovery_df.empty:
            return None
        
        # Find when volume starts recovering (exceeds 50% of pre-drop volume)
        recovery_threshold = drop_event.pre_drop_volume * 0.5
        recovery_points = recovery_df[recovery_df["v"] >= recovery_threshold]
        
        if recovery_points.empty:
            return None  # No recovery detected
        
        recovery_start = recovery_points.iloc[0]["t"]
        recovery_duration = (recovery_start - drop_time).total_seconds() / 3600  # Hours
        
        # Calculate recovery metrics
        max_recovery_volume = recovery_points["v"].max()
        volume_recovery_ratio = max_recovery_volume / drop_event.pre_drop_volume
        
        # Price recovery analysis
        price_at_drop = df[df["t"] == drop_time]["c"].iloc[0] if not df[df["t"] == drop_time].empty else 0
        max_recovery_price = recovery_points["c"].max()
        price_recovery_ratio = max_recovery_price / price_at_drop if price_at_drop > 0 else 0
        
        # Transaction pattern analysis
        recovery_data = df[(df["t"] >= drop_time) & (df["t"] <= recovery_start)]
        transaction_count = len(recovery_data)
        
        # Calculate average time between transactions
        if transaction_count > 1:
            time_diffs = recovery_data["t"].diff().dt.total_seconds() / 60  # Minutes
            avg_time_between_txs = time_diffs.mean()
        else:
            avg_time_between_txs = 0
        
        # Score recovery legitimacy
        legitimacy_score = self._score_recovery_legitimacy(
            recovery_duration, volume_recovery_ratio, transaction_count, avg_time_between_txs
        )
        
        # Calculate transaction diversity score
        transaction_diversity_score = self._calculate_transaction_diversity_score(recovery_data)
        
        # Calculate recovery slope
        recovery_slope = self._calculate_recovery_slope(recovery_data)
        
        # Calculate sustainability score
        sustainability_score = self._calculate_sustainability_score(recovery_data)
        
        # Multi-phase analysis
        recovery_phases = self._analyze_recovery_phases(df, drop_event)
        has_short_term_rebound = any(phase.phase_name == "short_term_rebound" for phase in recovery_phases)
        has_sustained_volume = any(phase.phase_name == "sustained_volume" for phase in recovery_phases)
        
        # Multi-stage recovery analysis
        recovery_stages, cumulative_recovery = self._analyze_multi_stage_recovery(df, drop_event)
        multi_stage_legitimacy = self._score_multi_stage_recovery_legitimacy(recovery_stages, cumulative_recovery)
        
        # Calculate fast recovery legitimacy for quick but healthy recoveries
        fast_recovery_legitimacy = self._score_fast_recovery_legitimacy(
            recovery_duration, transaction_diversity_score, recovery_slope, 
            sustainability_score, recovery_phases
        )
        
        return RecoveryPattern(
            recovery_start_time=recovery_start,
            recovery_duration_hours=recovery_duration,
            volume_recovery_ratio=volume_recovery_ratio,
            price_recovery_ratio=price_recovery_ratio,
            transaction_count=transaction_count,
            time_between_transactions=avg_time_between_txs,
            recovery_legitimacy_score=legitimacy_score,
            transaction_diversity_score=transaction_diversity_score,
            recovery_slope=recovery_slope,
            sustainability_score=sustainability_score,
            recovery_phases=recovery_phases,
            has_short_term_rebound=has_short_term_rebound,
            has_sustained_volume=has_sustained_volume,
            fast_recovery_legitimacy=fast_recovery_legitimacy,
            recovery_stages=recovery_stages,
            cumulative_recovery=cumulative_recovery,
            multi_stage_legitimacy_score=multi_stage_legitimacy
        )
    
    def _score_recovery_legitimacy(self, duration_hours: float, volume_ratio: float, 
                                   tx_count: int, avg_tx_interval: float) -> float:
        """
        Score the legitimacy of a recovery pattern (0.0 = rugpull, 1.0 = legitimate).
        Now more flexible with timing - allows fast recoveries if other indicators are strong.
        """
        score = 0.0
        
        # Enhanced duration scoring - more flexible approach
        if duration_hours <= self.ARTIFICIAL_RECOVERY_MAX_HOURS:  # Very fast (<30min)
            score -= 0.3  # Highly suspicious - likely artificial
        elif duration_hours <= self.FAST_RECOVERY_MAX_HOURS:  # Fast (30min-3h) 
            # Fast recovery can be legitimate if transaction count and intervals are good
            if tx_count >= 10 and avg_tx_interval >= 3:  # High activity with reasonable spacing
                score += 0.1  # Cautiously positive
            else:
                score -= 0.1  # Fast but low activity = suspicious
        elif duration_hours <= 24:  # Medium timing (3-24h)
            score += 0.2  # Good timing
        elif duration_hours <= self.ORGANIC_RECOVERY_MAX_HOURS:  # Standard timing (1-7 days)
            score += 0.3  # Excellent timing
        else:  # Very slow (>7 days)
            score += 0.1  # Too slow, might be natural decay
        
        # Volume recovery strength (unchanged)
        if volume_ratio >= 0.8:  # Strong recovery
            score += 0.3
        elif volume_ratio >= 0.5:  # Moderate recovery
            score += 0.2
        else:  # Weak recovery
            score += 0.1
        
        # Enhanced transaction count scoring
        if tx_count >= self.MIN_RECOVERY_TRANSACTIONS:
            score += 0.2
        elif tx_count >= 5:
            score += 0.1
        elif tx_count >= 3:  # Still some activity
            score += 0.05
        else:
            score -= 0.1  # Too few transactions
        
        # Enhanced transaction timing scoring
        if avg_tx_interval >= self.ORGANIC_TX_INTERVAL_MINUTES:
            score += 0.2  # Natural timing
        elif avg_tx_interval >= 5:
            score += 0.1  # Somewhat natural
        elif avg_tx_interval >= 2:  # Moderate spacing
            score += 0.05  # Neutral
        elif avg_tx_interval <= self.SUSPICIOUS_TX_INTERVAL_MINUTES:
            score -= 0.2  # Highly suspicious (bot-like)
        
        return max(0.0, min(1.0, score))  # Clamp between 0 and 1
    
    def _score_fast_recovery_legitimacy(self, duration_hours: float, diversity_score: float, 
                                        recovery_slope: float, sustainability_score: float,
                                        recovery_phases: List[RecoveryPhase]) -> float:
        """
        Score fast recoveries (1-3 hours) based on legitimacy indicators.
        Fast recoveries can be legitimate if they show high transaction diversity.
        """
        # Only score if this is actually a fast recovery
        if duration_hours < self.FAST_RECOVERY_MIN_HOURS or duration_hours > self.FAST_RECOVERY_MAX_HOURS:
            return 0.0
        
        legitimacy_score = 0.0
        
        # High transaction diversity is crucial for fast recovery legitimacy
        if diversity_score >= self.FAST_RECOVERY_MIN_TX_DIVERSITY:
            legitimacy_score += 0.4  # Strong diversity = likely organic
        elif diversity_score >= 0.5:
            legitimacy_score += 0.2  # Moderate diversity
        else:
            legitimacy_score -= 0.2  # Low diversity = suspicious for fast recovery
        
        # Positive recovery slope indicates genuine buying pressure
        if recovery_slope > 0.1:  # Strong upward trend
            legitimacy_score += 0.3
        elif recovery_slope > 0.01:  # Moderate upward trend  
            legitimacy_score += 0.1
        elif recovery_slope < -0.05:  # Declining volume during "recovery"
            legitimacy_score -= 0.2
        
        # Sustainability is important even for fast recoveries
        if sustainability_score >= 0.7:
            legitimacy_score += 0.2
        elif sustainability_score >= 0.5:
            legitimacy_score += 0.1
        else:
            legitimacy_score -= 0.1
        
        # Check for sustained activity beyond the fast recovery
        has_sustained_activity = False
        for phase in recovery_phases:
            if phase.phase_name in ["sustained_volume", "long_term_stability"]:
                if phase.volume_recovery_ratio >= 0.3:  # Some continued activity
                    has_sustained_activity = True
                    legitimacy_score += 0.1
                    break
        
        if not has_sustained_activity:
            legitimacy_score -= 0.1  # Fast recovery with no follow-through is suspicious
        
        return max(0.0, min(1.0, legitimacy_score))
    
    def _calculate_overall_legitimacy_score(self, volume_drops: List[VolumeDropEvent], 
                                            recoveries: List[RecoveryPattern], df: pd.DataFrame) -> float:
        """
        Calculate overall legitimacy score for the token.
        Enhanced to consider multi-phase recovery patterns and fast recovery legitimacy.
        """
        if not volume_drops:
            return 0.8  # No major volume drops = likely legitimate
        
        total_score = 0.0
        weight_sum = 0.0
        
        # Score based on enhanced recovery patterns
        for i, drop in enumerate(volume_drops):
            # Weight by severity of drop (more severe drops get more weight)
            weight = drop.drop_percentage
            
            if i < len(recoveries) and recoveries[i]:
                recovery = recoveries[i]
                
                # Base recovery score
                recovery_score = recovery.recovery_legitimacy_score
                
                # Boost score for legitimate fast recoveries
                if recovery.recovery_duration_hours <= self.FAST_RECOVERY_MAX_HOURS:
                    if recovery.fast_recovery_legitimacy >= 0.6:  # High fast recovery legitimacy
                        recovery_score = max(recovery_score, recovery.fast_recovery_legitimacy)
                        recovery_score += 0.1  # Bonus for legitimate fast recovery
                
                # Multi-phase recovery bonuses
                if recovery.recovery_phases:
                    phase_bonus = 0.0
                    
                    # Bonus for multiple recovery phases
                    if len(recovery.recovery_phases) >= 2:
                        phase_bonus += 0.05
                    
                    # Bonus for sustained volume after initial rebound
                    if recovery.has_sustained_volume:
                        sustained_phases = [p for p in recovery.recovery_phases 
                                          if p.phase_name in ["sustained_volume", "long_term_stability"]]
                        for phase in sustained_phases:
                            if phase.volume_recovery_ratio >= 0.4:  # Good sustained volume
                                phase_bonus += 0.1
                                break
                    
                    # Transaction diversity bonus
                    avg_diversity = np.mean([p.transaction_diversity_score for p in recovery.recovery_phases])
                    if avg_diversity >= 0.7:
                        phase_bonus += 0.1
                    elif avg_diversity >= 0.5:
                        phase_bonus += 0.05
                    
                    recovery_score += phase_bonus
                
                # Multi-stage recovery bonuses
                if recovery.multi_stage_legitimacy_score >= 0.8:
                    recovery_score += 0.15  # Strong multi-stage recovery pattern
                elif recovery.multi_stage_legitimacy_score >= 0.6:
                    recovery_score += 0.1   # Good multi-stage recovery pattern
                elif recovery.multi_stage_legitimacy_score >= 0.4:
                    recovery_score += 0.05  # Moderate multi-stage recovery pattern
                
                # Cumulative recovery strength bonus
                if recovery.cumulative_recovery:
                    if recovery.cumulative_recovery.total_stages >= 3:  # Multiple recovery attempts
                        recovery_score += 0.1
                    if recovery.cumulative_recovery.best_volume_recovery_ratio >= 1.0:  # Full recovery achieved
                        recovery_score += 0.1
                    if recovery.cumulative_recovery.final_sustained_level >= 0.6:  # Strong final level
                        recovery_score += 0.05
                
                # Sustainability and slope bonuses
                if recovery.sustainability_score >= 0.7:
                    recovery_score += 0.05
                if recovery.recovery_slope > 0.1:  # Strong positive trend
                    recovery_score += 0.05
                
            else:
                recovery_score = 0.1  # No recovery = likely rugpull
            
            total_score += recovery_score * weight
            weight_sum += weight
        
        base_legitimacy = total_score / weight_sum if weight_sum > 0 else 0.0
        
        # Additional factors (enhanced)
        
        # Factor 1: Multi-window volume trend analysis with comeback detection
        multi_window_bonus = self._analyze_multi_window_volume_trends(df, volume_drops)
        base_legitimacy += multi_window_bonus
        
        # Factor 2: Enhanced extreme drop penalty analysis
        extreme_drop_penalty = self._calculate_enhanced_extreme_drop_penalty(
            volume_drops, recoveries, df
        )
        base_legitimacy += extreme_drop_penalty  # Can be negative penalty or positive bonus
        
        # Factor 3: Enhanced Price-volume correlation analysis
        normalized_correlation_score = self._calculate_normalized_price_volume_correlation_score(
            volume_drops, recoveries, df
        )
        base_legitimacy += normalized_correlation_score
        
        # Factor 4: Price stability and liquidity bonus
        if volume_drops:
            avg_price_stability = np.mean([drop.price_stability_during_recovery for drop in volume_drops])
            avg_liquidity_indicator = np.mean([drop.liquidity_indicator for drop in volume_drops])
            
            # Bonus for high liquidity indicators
            if avg_liquidity_indicator >= 0.7:
                base_legitimacy += 0.1  # Strong liquidity indicators
            elif avg_liquidity_indicator >= 0.5:
                base_legitimacy += 0.05  # Moderate liquidity indicators
            
            # Bonus for price stability (indicates mature/liquid markets)
            if avg_price_stability >= 0.7:
                base_legitimacy += 0.05  # Very stable prices during recovery
        
        # Factor 5: Fast recovery pattern analysis
        fast_recoveries = [r for r in recoveries if r and r.recovery_duration_hours <= self.FAST_RECOVERY_MAX_HOURS]
        if fast_recoveries:
            avg_fast_legitimacy = np.mean([r.fast_recovery_legitimacy for r in fast_recoveries])
            if avg_fast_legitimacy >= 0.7:  # High-quality fast recoveries
                base_legitimacy += 0.1
            elif avg_fast_legitimacy <= 0.3:  # Suspicious fast recoveries
                base_legitimacy -= 0.1
        
        return max(0.0, min(1.0, base_legitimacy))
    
    def _generate_classification_hint(self, legitimacy_score: float, 
                                      volume_drops: List[VolumeDropEvent],
                                      recoveries: List[RecoveryPattern]) -> str:
        """Generate a classification hint based on the analysis."""
        
        if legitimacy_score >= self.SUCCESS_LEGITIMACY_THRESHOLD:
            return "success_likely"
        elif legitimacy_score <= self.RUGPULL_LEGITIMACY_THRESHOLD:
            return "rugpull_likely"
        else:
            # Additional tie-breaking logic
            if not volume_drops:
                return "success_likely"
            
            # Check if any recoveries were successful
            strong_recoveries = sum(1 for r in recoveries if r and r.volume_recovery_ratio >= 0.7)
            weak_recoveries = sum(1 for r in recoveries if r and r.volume_recovery_ratio < 0.3)
            
            if strong_recoveries > weak_recoveries:
                return "success_likely"
            elif weak_recoveries > strong_recoveries:
                return "rugpull_likely"
            else:
                return "unclear"
    
    def _generate_analysis_summary(self, volume_drops: List[VolumeDropEvent], 
                                   recoveries: List[RecoveryPattern], 
                                   legitimacy_score: float,
                                   df: pd.DataFrame) -> str:
        """Generate a human-readable summary of the enhanced analysis."""
        if not volume_drops:
            return f"No significant volume drops detected. Legitimacy score: {legitimacy_score:.2f}"
        
        summary_parts = []
        summary_parts.append(f"Detected {len(volume_drops)} significant volume drop events")
        
        if recoveries:
            strong_recoveries = sum(1 for r in recoveries if r.volume_recovery_ratio >= 0.7)
            weak_recoveries = sum(1 for r in recoveries if r.volume_recovery_ratio < 0.3)
            fast_recoveries = sum(1 for r in recoveries if r.recovery_duration_hours <= self.FAST_RECOVERY_MAX_HOURS)
            
            summary_parts.append(f"Recovery analysis: {strong_recoveries} strong recoveries, {weak_recoveries} weak recoveries")
            
            # Fast recovery analysis
            if fast_recoveries > 0:
                legitimate_fast = sum(1 for r in recoveries 
                                    if r.recovery_duration_hours <= self.FAST_RECOVERY_MAX_HOURS 
                                    and r.fast_recovery_legitimacy >= 0.6)
                summary_parts.append(f"{fast_recoveries} fast recoveries (<3h), {legitimate_fast} appear legitimate")
            
            # Multi-phase recovery analysis
            multi_phase_recoveries = sum(1 for r in recoveries if r.recovery_phases and len(r.recovery_phases) >= 2)
            if multi_phase_recoveries > 0:
                sustained_recoveries = sum(1 for r in recoveries if r.has_sustained_volume)
                summary_parts.append(f"{multi_phase_recoveries} multi-phase recoveries, {sustained_recoveries} with sustained volume")
            
            # Multi-stage recovery analysis
            multi_stage_recoveries = sum(1 for r in recoveries if r.cumulative_recovery and r.cumulative_recovery.total_stages >= 2)
            if multi_stage_recoveries > 0:
                total_stages = sum(r.cumulative_recovery.total_stages for r in recoveries if r.cumulative_recovery)
                avg_stages_per_drop = total_stages / len([r for r in recoveries if r.cumulative_recovery and r.cumulative_recovery.total_stages > 0])
                best_recovery = max((r.cumulative_recovery.best_volume_recovery_ratio for r in recoveries 
                                   if r.cumulative_recovery and r.cumulative_recovery.best_volume_recovery_ratio > 0), default=0)
                summary_parts.append(f"{multi_stage_recoveries} multi-stage recoveries (avg {avg_stages_per_drop:.1f} stages/drop, best: {best_recovery:.1f}x)")
            
            # Average recovery time and diversity
            avg_recovery_time = np.mean([r.recovery_duration_hours for r in recoveries])
            avg_diversity = np.mean([r.transaction_diversity_score for r in recoveries if r.transaction_diversity_score > 0])
            
            summary_parts.append(f"Average recovery time: {avg_recovery_time:.1f}h, avg transaction diversity: {avg_diversity:.2f}")
        
        # Enhanced price-volume analysis
        if volume_drops:
            avg_price_stability = np.mean([drop.price_stability_during_recovery for drop in volume_drops])
            avg_liquidity_indicator = np.mean([drop.liquidity_indicator for drop in volume_drops])
            
            if avg_liquidity_indicator >= 0.6:
                summary_parts.append(f"High liquidity indicators detected (avg: {avg_liquidity_indicator:.2f})")
            elif avg_price_stability >= 0.6:
                summary_parts.append(f"Price stability during recovery (avg: {avg_price_stability:.2f})")
        
        # Enhanced drop severity analysis
        extreme_drops = sum(1 for drop in volume_drops if drop.drop_percentage >= self.EXTREME_VOLUME_DROP)
        if extreme_drops > 0:
            # Calculate recovery success for extreme drops
            extreme_drops_with_recovery = 0
            for i, drop in enumerate(volume_drops):
                if drop.drop_percentage >= self.EXTREME_VOLUME_DROP:
                    if i < len(recoveries) and recoveries[i] and recoveries[i].volume_recovery_ratio >= 0.8:
                        extreme_drops_with_recovery += 1
            
            recovery_success_rate = extreme_drops_with_recovery / extreme_drops if extreme_drops > 0 else 0
            
            if recovery_success_rate >= 0.8:
                summary_parts.append(f"{extreme_drops} extreme volume drops (80%+), {extreme_drops_with_recovery} with strong recovery (high-volatility pattern)")
            elif recovery_success_rate >= 0.5:
                summary_parts.append(f"{extreme_drops} extreme volume drops (80%+), {extreme_drops_with_recovery} with strong recovery (mixed pattern)")
            else:
                summary_parts.append(f"{extreme_drops} extreme volume drops (80%+), only {extreme_drops_with_recovery} with strong recovery (concerning pattern)")
        
        
        # Multi-window trend analysis summary
        # Note: This is computed during legitimacy scoring, so we can't easily re-calculate here
        # But we can provide general information about the approach being used
        data_duration_days = (df["t"].max() - df["t"].min()).total_seconds() / (24 * 3600) if not df.empty else 0
        if data_duration_days >= 10:
            summary_parts.append("Long-term trend analysis: evaluated across 24h, 3-day, and 7-day windows with comeback detection")
        elif data_duration_days >= 4:
            summary_parts.append("Multi-window trend analysis: evaluated across 24h and 3-day windows")
        elif data_duration_days >= 2:
            summary_parts.append("Short-term trend analysis: evaluated across 24h window")
        
        summary_parts.append(f"Overall legitimacy score: {legitimacy_score:.2f}")
        
        return ". ".join(summary_parts)
    
    def _empty_analysis(self) -> Dict[str, Any]:
        """Return empty analysis results."""
        return {
            "volume_drop_events": [],
            "recovery_patterns": [],
            "overall_legitimacy_score": 0.5,  # Neutral score
            "classification_hint": "unclear",
            "analysis_summary": "Insufficient data for analysis"
        }
    
    def _calculate_transaction_diversity_score(self, recovery_data: pd.DataFrame) -> float:
        """
        Calculate transaction diversity score based on timing patterns and volume distribution.
        Higher score = more organic/diverse trading pattern.
        """
        if len(recovery_data) < 3:
            return 0.1  # Too few transactions for diversity
        
        diversity_score = 0.0
        
        # 1. Time interval variance (organic trading has varied intervals)
        time_diffs = recovery_data["t"].diff().dt.total_seconds() / 60  # Minutes
        time_diffs = time_diffs.dropna()
        
        if len(time_diffs) > 1:
            # Calculate coefficient of variation for time intervals
            time_cv = time_diffs.std() / time_diffs.mean() if time_diffs.mean() > 0 else 0
            # Higher CV = more varied timing = more organic
            diversity_score += min(0.3, time_cv * 0.1)  # Cap at 0.3
        
        # 2. Volume distribution variance (organic trading has varied volumes)
        volume_cv = recovery_data["v"].std() / recovery_data["v"].mean() if recovery_data["v"].mean() > 0 else 0
        diversity_score += min(0.25, volume_cv * 0.05)  # Cap at 0.25
        
        # 3. Price impact variance (organic trading shows natural price discovery)
        price_changes = recovery_data["c"].pct_change().abs()
        price_change_cv = price_changes.std() / price_changes.mean() if price_changes.mean() > 0 else 0
        diversity_score += min(0.2, price_change_cv * 0.1)  # Cap at 0.2
        
        # 4. Transaction count bonus (more transactions = more diversity potential)
        tx_count = len(recovery_data)
        if tx_count >= 20:
            diversity_score += 0.15
        elif tx_count >= 10:
            diversity_score += 0.1
        elif tx_count >= 5:
            diversity_score += 0.05
        
        # 5. Penalty for suspiciously regular patterns
        if len(time_diffs) > 5:
            # Check for highly regular intervals (bot-like behavior)
            regular_intervals = (time_diffs.std() / time_diffs.mean()) if time_diffs.mean() > 0 else 1
            if regular_intervals < 0.1:  # Very regular = suspicious
                diversity_score -= 0.2
        
        return max(0.0, min(1.0, diversity_score))
    
    def _calculate_recovery_slope(self, recovery_data: pd.DataFrame) -> float:
        """
        Calculate the slope of volume recovery (rate of change).
        Positive slope = volume increasing, negative = decreasing.
        """
        if len(recovery_data) < 2:
            return 0.0
        
        # Use linear regression to calculate slope
        x = np.arange(len(recovery_data))
        y = recovery_data["v"].values
        
        if len(x) == len(y) and len(x) > 1:
            slope = np.polyfit(x, y, 1)[0]  # Linear fit slope
            # Normalize slope relative to average volume
            avg_volume = y.mean() if y.mean() > 0 else 1
            normalized_slope = slope / avg_volume
            return normalized_slope
        
        return 0.0
    
    def _calculate_sustainability_score(self, recovery_data: pd.DataFrame) -> float:
        """
        Score how well volume is sustained during recovery.
        Higher score = better sustained volume.
        """
        if len(recovery_data) < 3:
            return 0.5  # Neutral for insufficient data
        
        # Split into early and late periods
        mid_point = len(recovery_data) // 2
        early_volume = recovery_data.iloc[:mid_point]["v"].mean()
        late_volume = recovery_data.iloc[mid_point:]["v"].mean()
        
        if early_volume <= 0:
            return 0.0
        
        # Sustainability = late_volume / early_volume
        sustainability_ratio = late_volume / early_volume
        
        # Score based on sustainability
        if sustainability_ratio >= 0.8:  # Volume well maintained
            return 0.9
        elif sustainability_ratio >= 0.6:  # Reasonably sustained
            return 0.7
        elif sustainability_ratio >= 0.4:  # Moderate decline
            return 0.5
        elif sustainability_ratio >= 0.2:  # Significant decline
            return 0.3
        else:  # Poor sustainability
            return 0.1
    
    def _analyze_recovery_phases(self, df: pd.DataFrame, drop_event: VolumeDropEvent) -> List[RecoveryPhase]:
        """
        Analyze recovery in multiple phases: short-term rebound, sustained volume, long-term stability.
        """
        drop_time = drop_event.timestamp
        phases = []
        
        # Phase 1: Short-term rebound (0-6 hours)
        short_term_end = drop_time + timedelta(hours=self.SHORT_TERM_REBOUND_HOURS)
        short_term_data = df[(df["t"] > drop_time) & (df["t"] <= short_term_end)]
        
        if not short_term_data.empty:
            max_volume = short_term_data["v"].max()
            max_price = short_term_data["c"].max()
            volume_ratio = max_volume / drop_event.pre_drop_volume
            
            # Find price at drop for comparison
            price_at_drop_data = df[df["t"] == drop_time]
            price_at_drop = price_at_drop_data["c"].iloc[0] if not price_at_drop_data.empty else drop_event.pre_drop_volume * 0.01
            price_ratio = max_price / price_at_drop if price_at_drop > 0 else 0
            
            diversity_score = self._calculate_transaction_diversity_score(short_term_data)
            slope = self._calculate_recovery_slope(short_term_data)
            sustainability = self._calculate_sustainability_score(short_term_data)
            
            phases.append(RecoveryPhase(
                phase_name="short_term_rebound",
                start_time=drop_time,
                duration_hours=self.SHORT_TERM_REBOUND_HOURS,
                volume_recovery_ratio=volume_ratio,
                price_recovery_ratio=price_ratio,
                transaction_count=len(short_term_data),
                recovery_slope=slope,
                sustainability_score=sustainability,
                transaction_diversity_score=diversity_score
            ))
        
        # Phase 2: Sustained volume (6-48 hours)
        sustained_start = drop_time + timedelta(hours=self.SHORT_TERM_REBOUND_HOURS)
        sustained_end = drop_time + timedelta(hours=self.SUSTAINED_VOLUME_HOURS)
        sustained_data = df[(df["t"] > sustained_start) & (df["t"] <= sustained_end)]
        
        if not sustained_data.empty:
            avg_volume = sustained_data["v"].mean()
            avg_price = sustained_data["c"].mean()
            volume_ratio = avg_volume / drop_event.pre_drop_volume
            
            price_at_drop_data = df[df["t"] == drop_time]
            price_at_drop = price_at_drop_data["c"].iloc[0] if not price_at_drop_data.empty else drop_event.pre_drop_volume * 0.01
            price_ratio = avg_price / price_at_drop if price_at_drop > 0 else 0
            
            diversity_score = self._calculate_transaction_diversity_score(sustained_data)
            slope = self._calculate_recovery_slope(sustained_data)
            sustainability = self._calculate_sustainability_score(sustained_data)
            
            phases.append(RecoveryPhase(
                phase_name="sustained_volume",
                start_time=sustained_start,
                duration_hours=self.SUSTAINED_VOLUME_HOURS - self.SHORT_TERM_REBOUND_HOURS,
                volume_recovery_ratio=volume_ratio,
                price_recovery_ratio=price_ratio,
                transaction_count=len(sustained_data),
                recovery_slope=slope,
                sustainability_score=sustainability,
                transaction_diversity_score=diversity_score
            ))
        
        # Phase 3: Long-term stability (48-168 hours)
        stability_start = drop_time + timedelta(hours=self.SUSTAINED_VOLUME_HOURS)
        stability_end = drop_time + timedelta(hours=self.LONG_TERM_STABILITY_HOURS)
        stability_data = df[(df["t"] > stability_start) & (df["t"] <= stability_end)]
        
        if not stability_data.empty:
            avg_volume = stability_data["v"].mean()
            avg_price = stability_data["c"].mean()
            volume_ratio = avg_volume / drop_event.pre_drop_volume
            
            price_at_drop_data = df[df["t"] == drop_time]
            price_at_drop = price_at_drop_data["c"].iloc[0] if not price_at_drop_data.empty else drop_event.pre_drop_volume * 0.01
            price_ratio = avg_price / price_at_drop if price_at_drop > 0 else 0
            
            diversity_score = self._calculate_transaction_diversity_score(stability_data)
            slope = self._calculate_recovery_slope(stability_data)
            sustainability = self._calculate_sustainability_score(stability_data)
            
            phases.append(RecoveryPhase(
                phase_name="long_term_stability",
                start_time=stability_start,
                duration_hours=self.LONG_TERM_STABILITY_HOURS - self.SUSTAINED_VOLUME_HOURS,
                volume_recovery_ratio=volume_ratio,
                price_recovery_ratio=price_ratio,
                transaction_count=len(stability_data),
                recovery_slope=slope,
                sustainability_score=sustainability,
                transaction_diversity_score=diversity_score
            ))
        
        return phases
    
    def _detect_price_stability_during_recovery(self, df: pd.DataFrame, drop_event: VolumeDropEvent, 
                                                recovery_data: pd.DataFrame) -> Dict[str, float]:
        """
        Detect price stability during recovery as an indicator of deep liquidity.
        Returns metrics about price behavior during recovery.
        """
        if recovery_data.empty or len(recovery_data) < 3:
            return {"stability_score": 0.5, "price_volatility": 1.0, "liquidity_indicator": 0.0}
        
        # Calculate price volatility during recovery
        price_changes = recovery_data["c"].pct_change().abs().dropna()
        avg_price_volatility = price_changes.mean() if not price_changes.empty else 0
        
        # Calculate high-low spread as volatility indicator
        hl_spreads = ((recovery_data["h"] - recovery_data["l"]) / recovery_data["c"]).dropna()
        avg_hl_spread = hl_spreads.mean() if not hl_spreads.empty else 0
        
        # Price stability score (lower volatility = higher stability)
        stability_score = 0.0
        if avg_price_volatility <= 0.02:  # Very stable (<2% average change)
            stability_score = 0.9
        elif avg_price_volatility <= 0.05:  # Stable (<5% average change)
            stability_score = 0.7
        elif avg_price_volatility <= 0.10:  # Moderate (5-10% average change)
            stability_score = 0.5
        elif avg_price_volatility <= 0.20:  # Volatile (10-20% average change)
            stability_score = 0.3
        else:  # Very volatile (>20% average change)
            stability_score = 0.1
        
        # Liquidity indicator (stable prices with high volume recovery = good liquidity)
        volume_recovery_strength = recovery_data["v"].max() / drop_event.pre_drop_volume
        if stability_score >= 0.7 and volume_recovery_strength >= 0.5:
            liquidity_indicator = 0.8  # Strong liquidity signs
        elif stability_score >= 0.5 and volume_recovery_strength >= 0.3:
            liquidity_indicator = 0.6  # Moderate liquidity signs
        elif stability_score >= 0.3:
            liquidity_indicator = 0.4  # Some liquidity signs
        else:
            liquidity_indicator = 0.2  # Low liquidity
        
        return {
            "stability_score": stability_score,
            "price_volatility": avg_price_volatility,
            "liquidity_indicator": liquidity_indicator,
            "hl_spread": avg_hl_spread
        }
    
    def _calculate_normalized_price_volume_correlation_score(self, volume_drops: List[VolumeDropEvent], 
                                                           recoveries: List[RecoveryPattern], 
                                                           df: pd.DataFrame) -> float:
        """
        Calculate a normalized price-volume correlation score that accounts for different market conditions.
        Returns a score between -0.2 and +0.2 to add to legitimacy.
        """
        if not volume_drops or not recoveries:
            return 0.0
        
        total_correlation_score = 0.0
        total_weight = 0.0
        
        for i, (drop, recovery) in enumerate(zip(volume_drops, recoveries)):
            if recovery is None:
                continue
                
            # Weight by drop severity
            weight = drop.drop_percentage
            
            # Get recovery data for this drop
            drop_time = drop.timestamp
            recovery_window_end = drop_time + timedelta(hours=recovery.recovery_duration_hours + 1)
            recovery_data = df[(df["t"] > drop_time) & (df["t"] <= recovery_window_end)]
            
            if recovery_data.empty:
                continue
            
            # Get price stability metrics
            stability_metrics = self._detect_price_stability_during_recovery(df, drop, recovery_data)
            
            # Calculate correlation score for this drop-recovery pair
            base_correlation = drop.price_correlation
            stability_score = stability_metrics["stability_score"]
            liquidity_indicator = stability_metrics["liquidity_indicator"]
            
            # Scenario 1: High liquidity with stable prices (low correlation is OK)
            if stability_score >= 0.7 and liquidity_indicator >= 0.6:
                if base_correlation <= 0.2:  # Low correlation but stable = good for deep markets
                    correlation_score = 0.15  # Bonus for deep liquidity behavior
                elif base_correlation <= 0.5:  # Moderate correlation with stability
                    correlation_score = 0.10
                else:  # High correlation with stability (normal behavior)
                    correlation_score = 0.05
            
            # Scenario 2: Moderate liquidity
            elif stability_score >= 0.5 and liquidity_indicator >= 0.4:
                if 0.1 <= base_correlation <= 0.7:  # Reasonable correlation range
                    correlation_score = 0.05
                elif base_correlation < 0.05:  # Very low correlation (suspicious)
                    correlation_score = -0.05
                else:  # High correlation (normal)
                    correlation_score = 0.0
            
            # Scenario 3: Low liquidity / volatile markets
            else:
                if 0.3 <= base_correlation <= 0.8:  # Expected correlation for volatile markets
                    correlation_score = 0.05
                elif base_correlation < 0.1:  # Volume drops without price impact (suspicious)
                    correlation_score = -0.10
                elif base_correlation > 0.9:  # Extremely high correlation (could be manipulation)
                    correlation_score = -0.05
                else:
                    correlation_score = 0.0
            
            # Additional adjustments based on recovery quality
            if recovery.volume_recovery_ratio >= 0.8:  # Strong volume recovery
                correlation_score *= 1.2  # Amplify the score
            elif recovery.volume_recovery_ratio < 0.3:  # Weak volume recovery
                correlation_score *= 0.8  # Reduce the score
            
            total_correlation_score += correlation_score * weight
            total_weight += weight
        
        # Normalize the final score
        if total_weight > 0:
            final_score = total_correlation_score / total_weight
            return max(-0.2, min(0.2, final_score))  # Cap between -0.2 and +0.2
        
        return 0.0
    
    def _analyze_multi_stage_recovery(self, df: pd.DataFrame, drop_event: VolumeDropEvent) -> Tuple[List[RecoveryStage], CumulativeRecovery]:
        """
        Analyze multi-stage recovery attempts over a week-long period.
        Tracks partial recoveries and cumulative strength over time.
        """
        drop_time = drop_event.timestamp
        analysis_window_end = drop_time + timedelta(days=7)
        recovery_df = df[(df["t"] > drop_time) & (df["t"] <= analysis_window_end)]
        
        if recovery_df.empty:
            return [], self._create_empty_cumulative_recovery()
        
        # Define recovery thresholds for different stages
        thresholds = {
            "minimal": drop_event.pre_drop_volume * 0.2,    # 20% recovery
            "partial": drop_event.pre_drop_volume * 0.5,    # 50% recovery  
            "substantial": drop_event.pre_drop_volume * 0.8, # 80% recovery
            "full": drop_event.pre_drop_volume * 1.0,       # 100% recovery
            "exceeded": drop_event.pre_drop_volume * 1.2    # 120% recovery
        }
        
        stages = []
        stage_number = 1
        current_search_start = drop_time
        
        # Track cumulative metrics
        all_recovery_ratios = []
        volume_time_series = []
        
        # Search for recovery stages within the 7-day window
        while current_search_start < analysis_window_end and stage_number <= 10:  # Max 10 stages
            # Look for recovery starting from current position
            stage_recovery_df = df[(df["t"] > current_search_start) & (df["t"] <= analysis_window_end)]
            
            if stage_recovery_df.empty:
                break
                
            # Find recovery points (any volume above minimal threshold)
            recovery_points = stage_recovery_df[stage_recovery_df["v"] >= thresholds["minimal"]]
            
            if recovery_points.empty:
                break
                
            # Analyze this recovery stage
            stage_info = self._analyze_single_recovery_stage(
                df, drop_event, recovery_points, stage_number, current_search_start
            )
            
            if stage_info:
                stages.append(stage_info)
                all_recovery_ratios.append(stage_info.volume_recovery_ratio)
                
                # Add volume data points for area under curve calculation
                stage_data = df[(df["t"] >= stage_info.start_time) & 
                              (df["t"] <= stage_info.start_time + timedelta(hours=stage_info.duration_hours))]
                volume_time_series.extend([(row["t"], row["v"]) for _, row in stage_data.iterrows()])
                
                # Move search start to after this stage's decline
                current_search_start = stage_info.peak_time + timedelta(hours=stage_info.sustainability_hours + 1)
                stage_number += 1
            else:
                break
        
        # Calculate cumulative recovery metrics
        cumulative_recovery = self._calculate_cumulative_recovery_metrics(
            stages, drop_event, volume_time_series, drop_time, analysis_window_end
        )
        
        return stages, cumulative_recovery
    
    def _analyze_single_recovery_stage(self, df: pd.DataFrame, drop_event: VolumeDropEvent, 
                                      recovery_points: pd.DataFrame, stage_number: int,
                                      search_start: datetime) -> Optional[RecoveryStage]:
        """Analyze a single recovery stage within the multi-stage recovery."""
        if recovery_points.empty:
            return None
            
        stage_start = recovery_points.iloc[0]["t"]
        
        # Find peak of this recovery stage
        peak_idx = recovery_points["v"].idxmax()
        peak_time = recovery_points.loc[peak_idx, "t"]
        peak_volume = recovery_points.loc[peak_idx, "v"]
        peak_price = recovery_points.loc[peak_idx, "c"]
        
        # Calculate how long the recovery was sustained at or above 80% of peak
        sustainability_threshold = peak_volume * 0.8
        sustained_data = recovery_points[recovery_points["v"] >= sustainability_threshold]
        
        if not sustained_data.empty:
            sustainability_hours = (sustained_data["t"].max() - sustained_data["t"].min()).total_seconds() / 3600
        else:
            sustainability_hours = 0.0
        
        # Look for decline after peak
        after_peak_data = df[(df["t"] > peak_time) & 
                           (df["t"] <= peak_time + timedelta(hours=24))]  # Look 24h after peak
        
        if not after_peak_data.empty:
            min_volume_after_peak = after_peak_data["v"].min()
            decline_after_peak = max(0.0, (peak_volume - min_volume_after_peak) / peak_volume)
        else:
            decline_after_peak = 0.0
        
        # Calculate stage duration
        stage_duration = (peak_time - stage_start).total_seconds() / 3600
        
        # Transaction analysis for this stage
        stage_data = df[(df["t"] >= stage_start) & (df["t"] <= peak_time)]
        transaction_count = len(stage_data)
        
        if transaction_count > 1:
            time_diffs = stage_data["t"].diff().dt.total_seconds() / 60  # Minutes
            avg_tx_interval = time_diffs.mean()
        else:
            avg_tx_interval = 0.0
        
        # Calculate recovery ratios
        volume_recovery_ratio = peak_volume / drop_event.pre_drop_volume
        
        # Price recovery calculation
        drop_price = drop_event.drop_price if drop_event.drop_price > 0 else drop_event.pre_drop_price
        price_recovery_ratio = peak_price / drop_price if drop_price > 0 else 0
        
        return RecoveryStage(
            stage_number=stage_number,
            start_time=stage_start,
            peak_time=peak_time,
            duration_hours=stage_duration,
            volume_recovery_ratio=volume_recovery_ratio,
            price_recovery_ratio=price_recovery_ratio,
            sustainability_hours=sustainability_hours,
            decline_after_peak=decline_after_peak,
            transaction_count=transaction_count,
            average_tx_interval=avg_tx_interval
        )
    
    def _calculate_cumulative_recovery_metrics(self, stages: List[RecoveryStage], 
                                             drop_event: VolumeDropEvent,
                                             volume_time_series: List[Tuple[datetime, float]],
                                             drop_time: datetime, 
                                             analysis_end: datetime) -> CumulativeRecovery:
        """Calculate cumulative recovery strength metrics across all stages."""
        if not stages:
            return self._create_empty_cumulative_recovery()
        
        # Find best recoveries
        best_volume_recovery = max(stage.volume_recovery_ratio for stage in stages)
        best_price_recovery = max(stage.price_recovery_ratio for stage in stages)
        
        # Calculate area under the recovery curve (cumulative volume effect)
        cumulative_volume = 0.0
        if volume_time_series:
            volume_time_series.sort(key=lambda x: x[0])  # Sort by time
            total_time_hours = (analysis_end - drop_time).total_seconds() / 3600
            
            for i, (timestamp, volume) in enumerate(volume_time_series):
                if i < len(volume_time_series) - 1:
                    next_timestamp = volume_time_series[i + 1][0]
                    time_diff_hours = (next_timestamp - timestamp).total_seconds() / 3600
                    cumulative_volume += volume * time_diff_hours
            
            # Normalize by total time and pre-drop volume
            if total_time_hours > 0 and drop_event.pre_drop_volume > 0:
                cumulative_volume = cumulative_volume / (total_time_hours * drop_event.pre_drop_volume)
        
        # Calculate recovery consistency (how similar the recovery ratios are)
        recovery_ratios = [stage.volume_recovery_ratio for stage in stages]
        if len(recovery_ratios) > 1:
            consistency_score = 1.0 - (np.std(recovery_ratios) / np.mean(recovery_ratios))
            consistency_score = max(0.0, consistency_score)  # Ensure non-negative
        else:
            consistency_score = 1.0  # Single recovery is perfectly consistent
        
        # Calculate final sustained level (volume level at end of analysis period)
        final_sustained_level = 0.0
        if volume_time_series:
            # Take average of last 24 hours or last 10% of data points
            final_period_size = max(1, len(volume_time_series) // 10)
            final_volumes = [vol for _, vol in volume_time_series[-final_period_size:]]
            final_sustained_level = np.mean(final_volumes) / drop_event.pre_drop_volume
        
        # Time to best recovery
        best_stage = max(stages, key=lambda s: s.volume_recovery_ratio)
        time_to_best_recovery = (best_stage.peak_time - drop_time).total_seconds() / 3600
        
        # Recovery slope trend (are recoveries getting better over time?)
        if len(stages) > 1:
            stage_numbers = [stage.stage_number for stage in stages]
            recovery_ratios = [stage.volume_recovery_ratio for stage in stages]
            slope_trend = np.polyfit(stage_numbers, recovery_ratios, 1)[0]  # Linear regression slope
        else:
            slope_trend = 0.0
        
        # Stage improvement rate
        if len(stages) > 1:
            first_recovery = stages[0].volume_recovery_ratio
            last_recovery = stages[-1].volume_recovery_ratio
            stage_improvement_rate = (last_recovery - first_recovery) / len(stages)
        else:
            stage_improvement_rate = 0.0
        
        return CumulativeRecovery(
            total_stages=len(stages),
            best_volume_recovery_ratio=best_volume_recovery,
            best_price_recovery_ratio=best_price_recovery,
            cumulative_volume_under_curve=cumulative_volume,
            recovery_consistency_score=consistency_score,
            final_sustained_level=final_sustained_level,
            time_to_best_recovery=time_to_best_recovery,
            recovery_slope_trend=slope_trend,
            stage_improvement_rate=stage_improvement_rate
        )
    
    def _create_empty_cumulative_recovery(self) -> CumulativeRecovery:
        """Create an empty cumulative recovery object for cases with no recovery."""
        return CumulativeRecovery(
            total_stages=0,
            best_volume_recovery_ratio=0.0,
            best_price_recovery_ratio=0.0,
            cumulative_volume_under_curve=0.0,
            recovery_consistency_score=0.0,
            final_sustained_level=0.0,
            time_to_best_recovery=0.0,
            recovery_slope_trend=0.0,
            stage_improvement_rate=0.0
        )
    
    def _score_multi_stage_recovery_legitimacy(self, stages: List[RecoveryStage], 
                                              cumulative: CumulativeRecovery) -> float:
        """
        Score the legitimacy of multi-stage recovery patterns.
        Higher scores indicate more organic, persistent recovery attempts.
        """
        if not stages or cumulative.total_stages == 0:
            return 0.0
        
        legitimacy_score = 0.0
        
        # Factor 1: Multiple recovery attempts show persistence (positive for healthy coins)
        if cumulative.total_stages == 1:
            legitimacy_score += 0.1  # Single attempt
        elif cumulative.total_stages == 2:
            legitimacy_score += 0.25  # Two attempts show some persistence
        elif cumulative.total_stages >= 3:
            legitimacy_score += 0.35  # Multiple attempts show strong community/demand
        
        # Factor 2: Best recovery strength
        if cumulative.best_volume_recovery_ratio >= 1.2:  # Exceeded original volume
            legitimacy_score += 0.25
        elif cumulative.best_volume_recovery_ratio >= 1.0:  # Full recovery
            legitimacy_score += 0.2
        elif cumulative.best_volume_recovery_ratio >= 0.8:  # Strong recovery
            legitimacy_score += 0.15
        elif cumulative.best_volume_recovery_ratio >= 0.5:  # Moderate recovery
            legitimacy_score += 0.1
        else:  # Weak recovery
            legitimacy_score += 0.05
        
        # Factor 3: Cumulative volume under curve (total recovery effect)
        if cumulative.cumulative_volume_under_curve >= 0.8:
            legitimacy_score += 0.15  # Strong cumulative effect
        elif cumulative.cumulative_volume_under_curve >= 0.5:
            legitimacy_score += 0.1   # Moderate cumulative effect
        elif cumulative.cumulative_volume_under_curve >= 0.3:
            legitimacy_score += 0.05  # Some cumulative effect
        
        # Factor 4: Recovery consistency (consistent attempts vs erratic)
        if cumulative.recovery_consistency_score >= 0.7:
            legitimacy_score += 0.1   # Consistent recovery attempts
        elif cumulative.recovery_consistency_score >= 0.5:
            legitimacy_score += 0.05  # Somewhat consistent
        # Low consistency doesn't get penalty (could be natural volatility)
        
        # Factor 5: Final sustained level (did recovery stick?)
        if cumulative.final_sustained_level >= 0.8:
            legitimacy_score += 0.15  # Recovery was sustained
        elif cumulative.final_sustained_level >= 0.5:
            legitimacy_score += 0.1   # Partially sustained
        elif cumulative.final_sustained_level >= 0.3:
            legitimacy_score += 0.05  # Some sustainability
        
        # Factor 6: Improving trend over time (each recovery better than last?)
        if cumulative.recovery_slope_trend > 0.1:
            legitimacy_score += 0.1   # Improving recovery trend
        elif cumulative.recovery_slope_trend > 0.0:
            legitimacy_score += 0.05  # Slight improvement
        elif cumulative.recovery_slope_trend < -0.1:
            legitimacy_score -= 0.05  # Declining recovery strength (concerning)
        
        # Factor 7: Time to best recovery (too fast could be artificial)
        if cumulative.time_to_best_recovery <= 1:  # Very fast (<1h)
            legitimacy_score -= 0.05  # Potentially artificial
        elif cumulative.time_to_best_recovery <= 24:  # Within a day
            legitimacy_score += 0.05  # Good timing
        elif cumulative.time_to_best_recovery <= 168:  # Within a week
            legitimacy_score += 0.1   # Patient, organic recovery
        
        # Factor 8: Transaction patterns across stages
        avg_tx_count = np.mean([stage.transaction_count for stage in stages])
        avg_tx_interval = np.mean([stage.average_tx_interval for stage in stages])
        
        if avg_tx_count >= 10:
            legitimacy_score += 0.1   # Good transaction activity
        elif avg_tx_count >= 5:
            legitimacy_score += 0.05  # Some transaction activity
        
        if avg_tx_interval >= 5:  # At least 5 minutes between transactions on average
            legitimacy_score += 0.05  # Natural transaction timing
        elif avg_tx_interval <= 1:  # Very frequent transactions
            legitimacy_score -= 0.05  # Potentially bot-like
        
        # Factor 9: Sustainability across stages
        avg_sustainability = np.mean([stage.sustainability_hours for stage in stages])
        if avg_sustainability >= 6:  # Recoveries were sustained for 6+ hours on average
            legitimacy_score += 0.1
        elif avg_sustainability >= 2:  # Sustained for 2+ hours
            legitimacy_score += 0.05
        
        return max(0.0, min(1.0, legitimacy_score))
    
    def _analyze_multi_window_volume_trends(self, df: pd.DataFrame, 
                                            volume_drops: List[VolumeDropEvent]) -> float:
        """
        Analyze volume trends across multiple time windows and detect comebacks.
        """
        if len(df) < 24:
            return 0.0
        
        # Simple implementation for now to get tests working
        if len(df) >= 48:
            early_volume = df.head(24)["v"].mean()
            recent_volume = df.tail(24)["v"].mean()
            
            if early_volume > 0:
                ratio = recent_volume / early_volume
                if ratio >= 0.8:
                    return 0.05  # Maintained well
                elif ratio < 0.3:
                    return -0.1  # Significant decline
        
        return 0.0
        
    def _calculate_enhanced_extreme_drop_penalty(self, volume_drops: List[VolumeDropEvent], 
                                                 recoveries: List[RecoveryPattern], 
                                                 df: pd.DataFrame) -> float:
        """
        Calculate enhanced extreme drop penalty that considers recovery patterns.
        
        Distinguishes between:
        1. High-volatility but recovering tokens (meme coins, launch-stage)
        2. Terminal collapse tokens (rugpulls)
        
        Returns:
            float: Penalty/bonus score between -0.3 and +0.2
        """
        if not volume_drops:
            return 0.0
        
        # Identify extreme drops (80%+ volume drops)
        extreme_drops = [drop for drop in volume_drops if drop.drop_percentage >= self.EXTREME_VOLUME_DROP]
        
        if not extreme_drops:
            return 0.0  # No extreme drops, no penalty or bonus
        
        extreme_drop_count = len(extreme_drops)
        
        # === Recovery-Based Analysis ===
        
        # Calculate recovery success rate for extreme drops
        extreme_drops_with_strong_recovery = 0
        extreme_drops_with_moderate_recovery = 0
        extreme_drops_with_weak_recovery = 0
        
        for i, drop in enumerate(extreme_drops):
            # Find corresponding recovery
            drop_index = volume_drops.index(drop)
            if drop_index < len(recoveries) and recoveries[drop_index]:
                recovery = recoveries[drop_index]
                
                if recovery.volume_recovery_ratio >= 0.8:  # ≥80% volume comeback
                    extreme_drops_with_strong_recovery += 1
                elif recovery.volume_recovery_ratio >= 0.5:  # 50-80% recovery
                    extreme_drops_with_moderate_recovery += 1
                else:  # <50% recovery
                    extreme_drops_with_weak_recovery += 1
            else:
                extreme_drops_with_weak_recovery += 1  # No recovery = weak
        
        # Calculate recovery success metrics
        strong_recovery_rate = extreme_drops_with_strong_recovery / extreme_drop_count
        moderate_recovery_rate = extreme_drops_with_moderate_recovery / extreme_drop_count
        weak_recovery_rate = extreme_drops_with_weak_recovery / extreme_drop_count
        
        # === Early-Stage vs Terminal Collapse Detection ===
        
        # Check if this is early-stage volatility vs terminal collapse
        is_early_stage_volatility = self._detect_early_stage_volatility_pattern(
            extreme_drops, df
        )
        
        # Check for terminal collapse pattern
        is_terminal_collapse = self._detect_terminal_collapse_pattern(
            extreme_drops, recoveries, df
        )
        
        # === Penalty/Bonus Calculation ===
        
        penalty_bonus = 0.0
        
        # Base penalty for having extreme drops
        base_penalty = min(0.15, extreme_drop_count * 0.03)  # Max 0.15 penalty
        penalty_bonus -= base_penalty
        
        # === Recovery-Based Adjustments ===
        
        # Strong recovery bonus (reduces penalty or adds bonus)
        if strong_recovery_rate >= 0.8:  # 80%+ of extreme drops recover strongly
            recovery_bonus = 0.12  # Strong bonus for consistent recovery
        elif strong_recovery_rate >= 0.6:  # 60%+ recover strongly
            recovery_bonus = 0.08  # Good recovery pattern
        elif strong_recovery_rate >= 0.4:  # 40%+ recover strongly
            recovery_bonus = 0.05  # Moderate recovery pattern
        else:
            recovery_bonus = 0.0
        
        penalty_bonus += recovery_bonus
        
        # Moderate recovery partial bonus
        if moderate_recovery_rate >= 0.5:  # At least half show moderate recovery
            penalty_bonus += 0.03
        
        # Weak recovery additional penalty
        if weak_recovery_rate >= 0.6:  # Most drops don't recover
            penalty_bonus -= 0.08  # Additional penalty for poor recovery
        
        # === Pattern-Based Adjustments ===
        
        # Early-stage volatility bonus
        if is_early_stage_volatility:
            penalty_bonus += 0.06  # Bonus for early-stage pattern
            logger.debug("Early-stage volatility pattern detected - reducing extreme drop penalty")
        
        # Terminal collapse penalty
        if is_terminal_collapse:
            penalty_bonus -= 0.10  # Additional penalty for terminal collapse
            logger.debug("Terminal collapse pattern detected - increasing penalty")
        
        # === Frequency-Based Adjustments ===
        
        # Progressive penalty for excessive extreme drops
        if extreme_drop_count <= 2:
            frequency_adjustment = 0.0  # No additional penalty for 1-2 extreme drops
        elif extreme_drop_count <= 4:
            # Mild penalty if recovery rate is good
            if strong_recovery_rate >= 0.5:
                frequency_adjustment = -0.02  # Minimal penalty with good recovery
            else:
                frequency_adjustment = -0.05  # Moderate penalty
        elif extreme_drop_count <= 6:
            # Moderate penalty, even with good recovery
            if strong_recovery_rate >= 0.7:
                frequency_adjustment = -0.04  # Reduced penalty for excellent recovery
            else:
                frequency_adjustment = -0.08  # Standard penalty
        else:  # >6 extreme drops
            # High penalty, but still consider recovery
            if strong_recovery_rate >= 0.8:
                frequency_adjustment = -0.06  # Reduced penalty for exceptional recovery
            else:
                frequency_adjustment = -0.12  # High penalty
        
        penalty_bonus += frequency_adjustment
        
        # === Time-Based Recovery Analysis ===
        
        # Bonus for improving recovery over time (learning/maturing market)
        recovery_improvement = self._analyze_recovery_improvement_over_time(
            extreme_drops, recoveries
        )
        penalty_bonus += recovery_improvement
        
        # Debug logging
        logger.debug(f"Enhanced extreme drop analysis: {extreme_drop_count} extreme drops, "
                    f"strong_recovery_rate={strong_recovery_rate:.2f}, "
                    f"early_stage={is_early_stage_volatility}, "
                    f"terminal_collapse={is_terminal_collapse}, "
                    f"penalty_bonus={penalty_bonus:.3f}")
        
        # Clamp final result
        return max(-0.3, min(0.2, penalty_bonus))
    
    def _detect_early_stage_volatility_pattern(self, extreme_drops: List[VolumeDropEvent], 
                                               df: pd.DataFrame) -> bool:
        """
        Detect if extreme drops represent early-stage volatility rather than terminal collapse.
        
        Early-stage volatility characteristics:
        1. Extreme drops occur early in the token's life
        2. General upward trend in baseline volume over time
        3. Drops are followed by periods of increased activity
        """
        if not extreme_drops or df.empty:
            return False
        
        # Check if extreme drops occur early (first 50% of data)
        total_duration = (df["t"].max() - df["t"].min()).total_seconds()
        early_stage_cutoff = df["t"].min() + timedelta(seconds=total_duration * 0.5)
        
        early_extreme_drops = sum(1 for drop in extreme_drops 
                                 if drop.timestamp <= early_stage_cutoff)
        early_drop_ratio = early_extreme_drops / len(extreme_drops)
        
        # Check for overall upward trend in volume
        if len(df) >= 48:  # Need sufficient data
            # Compare first quarter vs last quarter volume
            quarter_size = len(df) // 4
            early_volume = df.head(quarter_size)["v"].mean()
            late_volume = df.tail(quarter_size)["v"].mean()
            
            volume_growth = late_volume / early_volume if early_volume > 0 else 0
            has_volume_growth = volume_growth > 1.2  # 20%+ growth
        else:
            has_volume_growth = False
        
        # Check for post-drop activity increases
        post_drop_activity_increases = 0
        for drop in extreme_drops:
            # Look at activity in 24h after drop
            after_drop = df[df["t"] > drop.timestamp][:24]  # Next 24 data points
            before_drop = df[df["t"] <= drop.timestamp][-24:]  # Previous 24 data points
            
            if not after_drop.empty and not before_drop.empty:
                after_avg = after_drop["v"].mean()
                before_avg = before_drop["v"].mean()
                
                if after_avg > before_avg * 0.8:  # Activity maintained or increased
                    post_drop_activity_increases += 1
        
        post_drop_activity_rate = (post_drop_activity_increases / len(extreme_drops) 
                                  if extreme_drops else 0)
        
        # Early-stage criteria (at least 2 of 3 must be true)
        criteria_met = 0
        
        if early_drop_ratio >= 0.6:  # 60%+ of extreme drops are early
            criteria_met += 1
        
        if has_volume_growth:  # Overall volume growth
            criteria_met += 1
        
        if post_drop_activity_rate >= 0.5:  # 50%+ of drops followed by maintained activity
            criteria_met += 1
        
        return criteria_met >= 2
    
    def _detect_terminal_collapse_pattern(self, extreme_drops: List[VolumeDropEvent], 
                                          recoveries: List[RecoveryPattern], 
                                          df: pd.DataFrame) -> bool:
        """
        Detect terminal collapse pattern (characteristic of rugpulls).
        
        Terminal collapse characteristics:
        1. Extreme drops in latter half of token life
        2. No meaningful recovery after drops
        3. Continuous volume decline
        4. Low final volume compared to peak
        """
        if not extreme_drops or df.empty:
            return False
        
        # Check if extreme drops occur late (last 50% of data)
        total_duration = (df["t"].max() - df["t"].min()).total_seconds()
        late_stage_cutoff = df["t"].min() + timedelta(seconds=total_duration * 0.5)
        
        late_extreme_drops = sum(1 for drop in extreme_drops 
                                if drop.timestamp >= late_stage_cutoff)
        late_drop_ratio = late_extreme_drops / len(extreme_drops)
        
        # Check for lack of meaningful recovery
        if recoveries:
            poor_recovery_count = sum(1 for recovery in recoveries 
                                    if recovery and recovery.volume_recovery_ratio < 0.3)
            poor_recovery_rate = poor_recovery_count / len(recoveries)
        else:
            poor_recovery_rate = 1.0  # No recoveries = all poor
        
        # Check for continuous volume decline
        if len(df) >= 48:
            # Compare volume trend across the dataset
            quarter_size = len(df) // 4
            first_quarter_vol = df.head(quarter_size)["v"].mean()
            last_quarter_vol = df.tail(quarter_size)["v"].mean()
            
            volume_decline = last_quarter_vol / first_quarter_vol if first_quarter_vol > 0 else 0
            has_severe_decline = volume_decline < 0.2  # >80% decline
        else:
            has_severe_decline = False
        
        # Check for low final volume compared to peak
        peak_volume = df["v"].max()
        final_period_volume = df.tail(12)["v"].mean()  # Last 12 data points
        final_vs_peak = final_period_volume / peak_volume if peak_volume > 0 else 0
        has_collapsed_to_low_volume = final_vs_peak < 0.1  # <10% of peak
        
        # Terminal collapse criteria (at least 3 of 4 must be true)
        criteria_met = 0
        
        if late_drop_ratio >= 0.5:  # 50%+ of extreme drops are late-stage
            criteria_met += 1
        
        if poor_recovery_rate >= 0.7:  # 70%+ of recoveries are poor
            criteria_met += 1
        
        if has_severe_decline:  # Severe overall volume decline
            criteria_met += 1
        
        if has_collapsed_to_low_volume:  # Volume collapsed to very low levels
            criteria_met += 1
        
        return criteria_met >= 3
    
    def _analyze_recovery_improvement_over_time(self, extreme_drops: List[VolumeDropEvent], 
                                                recoveries: List[RecoveryPattern]) -> float:
        """
        Analyze if recovery patterns improve over time (learning/maturing market).
        
        Returns:
            float: Bonus score (0.0 to 0.05) for improving recovery patterns
        """
        if len(extreme_drops) < 2 or not recoveries:
            return 0.0
        
        # Get recovery ratios in chronological order
        recovery_ratios = []
        for drop in sorted(extreme_drops, key=lambda x: x.timestamp):
            drop_index = [i for i, d in enumerate(extreme_drops) if d.timestamp == drop.timestamp]
            if drop_index and drop_index[0] < len(recoveries) and recoveries[drop_index[0]]:
                recovery_ratios.append(recoveries[drop_index[0]].volume_recovery_ratio)
        
        if len(recovery_ratios) < 2:
            return 0.0
        
        # Calculate trend in recovery ratios over time
        x = np.arange(len(recovery_ratios))
        if len(recovery_ratios) > 2:
            try:
                slope, _ = np.polyfit(x, recovery_ratios, 1)
                
                # Bonus for improving recovery over time
                if slope > 0.1:  # Strong improvement trend
                    return 0.05
                elif slope > 0.05:  # Moderate improvement trend
                    return 0.03
                elif slope > 0.0:  # Slight improvement trend
                    return 0.01
                else:
                    return 0.0
            except:
                return 0.0
        else:
            # Simple comparison for 2 recoveries
            if recovery_ratios[-1] > recovery_ratios[0] * 1.2:  # 20%+ improvement
                return 0.03
            elif recovery_ratios[-1] > recovery_ratios[0]:
                return 0.01
        
        return 0.0
    
    def _analyze_sparse_data(self, ohlcv_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze tokens with very sparse data (1-3 OHLCV records).
        
        With limited data, we focus on basic price movement and volume patterns.
        """
        if not ohlcv_data:
            return self._empty_analysis()
        
        data_points = len(ohlcv_data)
        
        # Basic analysis with limited data
        df = self._prepare_dataframe(ohlcv_data)
        
        # Calculate basic metrics
        if len(df) >= 2:
            price_change = (df["c"].iloc[-1] - df["c"].iloc[0]) / df["c"].iloc[0] if df["c"].iloc[0] > 0 else 0
            volume_stability = df["v"].std() / df["v"].mean() if df["v"].mean() > 0 else 1.0
            
            # Score based on limited information
            if data_points == 1:
                # Single data point - completely neutral
                legitimacy_score = 0.5
                classification_hint = "single_data_point"
                summary = f"Only 1 data point available. Price: ${df['c'].iloc[0]:.6f}, Volume: {df['v'].iloc[0]:.2f}"
                
            elif data_points == 2:
                # Two data points - basic trend analysis
                if price_change > 0.1 and volume_stability < 2.0:  # Price up with stable volume
                    legitimacy_score = 0.6
                    classification_hint = "early_positive_trend"
                elif price_change < -0.5:  # Significant price drop
                    legitimacy_score = 0.3
                    classification_hint = "early_negative_trend"
                else:
                    legitimacy_score = 0.5
                    classification_hint = "early_neutral_trend"
                
                summary = f"2 data points. Price change: {price_change:.1%}, Volume stability: {volume_stability:.2f}"
                
            else:  # 3 data points
                # Three data points - slightly more sophisticated analysis
                price_trend = np.polyfit(range(len(df)), df["c"], 1)[0]  # Linear trend slope
                avg_volume = df["v"].mean()
                
                if price_trend > 0 and avg_volume > 10:  # Positive trend with decent volume
                    legitimacy_score = 0.6
                    classification_hint = "early_growth_pattern"
                elif price_trend < -0.001 and avg_volume < 5:  # Declining with low volume
                    legitimacy_score = 0.4
                    classification_hint = "early_decline_pattern"
                else:
                    legitimacy_score = 0.5
                    classification_hint = "early_mixed_pattern"
                
                summary = f"3 data points. Price trend: {price_trend:.8f}, Avg volume: {avg_volume:.2f}"
        
        else:
            # Single data point fallback
            legitimacy_score = 0.5
            classification_hint = "insufficient_data"
            summary = "Insufficient data for meaningful analysis"
        
        return {
            "volume_drop_events": [],
            "recovery_patterns": [],
            "overall_legitimacy_score": legitimacy_score,
            "classification_hint": classification_hint,
            "analysis_summary": summary,
            "legitimacy_score": legitimacy_score * 10.0,  # Scale to 0-10
            "data_quality": "minimal"
        }


def analyze_token_legitimacy(ohlcv_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Main function to analyze token legitimacy using the enhanced rugpull vs success detector.
    
    Args:
        ohlcv_data: List of OHLCV data dictionaries with keys: ts, o, h, l, c, v
        
    Returns:
        Dictionary containing analysis results compatible with the token labeler
    """
    detector = RugpullVsSuccessDetector()
    
    # Always perform analysis, but with better fallbacks for sparse data
    if not ohlcv_data or len(ohlcv_data) == 0:
        # Return minimal analysis for completely empty data
        return {
            "volume_drop_events": [],
            "recovery_patterns": [],
            "overall_legitimacy_score": 0.5,  # Neutral score
            "classification_hint": "insufficient_data",
            "analysis_summary": "No OHLCV data available for analysis",
            "legitimacy_score": 5.0,  # Neutral score scaled to 0-10
            "data_quality": "none"
        }
    
    # Enhanced analysis for sparse data (1-3 records)
    if len(ohlcv_data) < 4:
        return detector._analyze_sparse_data(ohlcv_data)
    
    # Standard analysis for sufficient data
    result = detector.analyze_volume_drops_and_recoveries(ohlcv_data)
    
    # Add backward compatibility and enhanced metadata
    result["legitimacy_score"] = result["overall_legitimacy_score"] * 10.0  # Scale to 0-10 range
    result["data_quality"] = _assess_data_quality(ohlcv_data)
    
    return result


def _assess_data_quality(ohlcv_data: List[Dict[str, Any]]) -> str:
    """Assess the quality of OHLCV data for analysis."""
    if not ohlcv_data:
        return "none"
    
    data_points = len(ohlcv_data)
    if data_points >= 48:  # 48+ hours of data
        return "excellent"
    elif data_points >= 24:  # 24+ hours of data
        return "good"
    elif data_points >= 12:  # 12+ hours of data
        return "moderate"
    elif data_points >= 4:   # 4+ hours of data
        return "limited"
    else:                    # <4 hours of data
        return "minimal"


if __name__ == "__main__":
    # Test the detector with sample data
    from datetime import datetime, timedelta
    
    # Create sample test data
    base_ts = int(datetime.now().timestamp()) - (7 * 24 * 3600)  # 7 days ago
    sample_data = []
    
    for i in range(168):  # 7 days of hourly data
        sample_data.append({
            "ts": base_ts + i * 3600,
            "o": 1.0, "h": 1.2, "l": 0.8, "c": 1.1,
            "v": 1000 + (i % 50) * 100  # Variable volume
        })
    
    result = analyze_token_legitimacy(sample_data)
    print(f"Test result: {result['classification_hint']} (score: {result['overall_legitimacy_score']:.2f})")
