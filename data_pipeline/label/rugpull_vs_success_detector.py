"""
Rugpull vs Success Detector

This module provides sophisticated algorithms to distinguish between:
1. Legitimate successful coins that experienced natural volume/price drops
2. Actual rugpulls with coordinated malicious intent

The key insight is that successful coins often have extreme volatility and volume drops,
but they exhibit different recovery patterns compared to rugpulls.

Key Differentiators:
- Volume recovery patterns (organic vs artificial)
- Recovery timing and sustainability
- Transaction patterns during recovery
- Community behavior during drops
- Price action legitimacy

Author: Enhanced Token Classification System
Date: August 2025
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class VolumeDropEvent:
    """Represents a significant volume drop event."""
    timestamp: datetime
    pre_drop_volume: float  # Average volume before drop
    drop_volume: float      # Lowest volume during drop
    post_drop_volume: Optional[float] = None  # Volume after recovery attempt
    drop_percentage: float = 0.0  # % volume reduction
    recovery_time_hours: Optional[float] = None  # Hours to recover
    recovery_strength: float = 0.0  # Recovery volume vs pre-drop
    transaction_pattern_score: float = 0.0  # Legitimacy score of transactions
    price_correlation: float = 0.0  # How volume correlates with price action

@dataclass
class RecoveryPattern:
    """Analysis of recovery behavior after major drops."""
    recovery_start_time: datetime
    recovery_duration_hours: float
    volume_recovery_ratio: float  # Post-recovery volume vs pre-drop
    price_recovery_ratio: float   # Post-recovery price vs pre-drop
    transaction_count: int        # Number of transactions during recovery
    unique_addresses: Optional[int] = None  # Unique addresses involved
    avg_transaction_size: Optional[float] = None
    time_between_transactions: float = 0.0  # Average time between txs (minutes)
    recovery_legitimacy_score: float = 0.0  # Overall legitimacy score

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
    ORGANIC_RECOVERY_MIN_HOURS = 6    # Organic recovery takes at least 6 hours
    ORGANIC_RECOVERY_MAX_HOURS = 168  # Organic recovery within 1 week
    ARTIFICIAL_RECOVERY_MAX_HOURS = 2 # Artificial recovery is very fast (<2h)
    
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
                volume_drop_events, recovery_patterns, legitimacy_score
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
        """Identify significant volume drop events."""
        events = []
        
        for i in range(24, len(df)):  # Start after 24h for rolling average
            current_volume = df.iloc[i]["v"]
            pre_drop_volume = df.iloc[i-24:i]["v"].mean()  # 24h average before
            
            if pre_drop_volume > 0:
                drop_percentage = 1 - (current_volume / pre_drop_volume)
                
                if drop_percentage >= self.SIGNIFICANT_VOLUME_DROP:
                    event = VolumeDropEvent(
                        timestamp=df.iloc[i]["t"],
                        pre_drop_volume=pre_drop_volume,
                        drop_volume=current_volume,
                        drop_percentage=drop_percentage
                    )
                    
                    # Calculate price correlation
                    price_before = df.iloc[i-24:i]["c"].mean()
                    price_at_drop = df.iloc[i]["c"]
                    price_drop = 1 - (price_at_drop / price_before) if price_before > 0 else 0
                    event.price_correlation = price_drop  # How much price dropped with volume
                    
                    events.append(event)
        
        # Remove duplicate events (too close in time)
        events = self._deduplicate_events(events)
        
        logger.debug(f"Identified {len(events)} significant volume drop events")
        return events
    
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
        
        return RecoveryPattern(
            recovery_start_time=recovery_start,
            recovery_duration_hours=recovery_duration,
            volume_recovery_ratio=volume_recovery_ratio,
            price_recovery_ratio=price_recovery_ratio,
            transaction_count=transaction_count,
            time_between_transactions=avg_time_between_txs,
            recovery_legitimacy_score=legitimacy_score
        )
    
    def _score_recovery_legitimacy(self, duration_hours: float, volume_ratio: float, 
                                   tx_count: int, avg_tx_interval: float) -> float:
        """Score the legitimacy of a recovery pattern (0.0 = rugpull, 1.0 = legitimate)."""
        score = 0.0
        
        # Duration scoring (organic recovery takes time)
        if duration_hours >= self.ORGANIC_RECOVERY_MIN_HOURS:
            if duration_hours <= self.ORGANIC_RECOVERY_MAX_HOURS:
                score += 0.3  # Good timing
            else:
                score += 0.1  # Too slow, might be natural decay
        else:
            score -= 0.2  # Too fast, suspicious
        
        # Volume recovery strength
        if volume_ratio >= 0.8:  # Strong recovery
            score += 0.3
        elif volume_ratio >= 0.5:  # Moderate recovery
            score += 0.2
        else:  # Weak recovery
            score += 0.1
        
        # Transaction count (legitimate recovery has multiple transactions)
        if tx_count >= self.MIN_RECOVERY_TRANSACTIONS:
            score += 0.2
        elif tx_count >= 5:
            score += 0.1
        else:
            score -= 0.1  # Too few transactions
        
        # Transaction timing (organic transactions have varied intervals)
        if avg_tx_interval >= self.ORGANIC_TX_INTERVAL_MINUTES:
            score += 0.2  # Natural timing
        elif avg_tx_interval >= 5:
            score += 0.1  # Somewhat natural
        elif avg_tx_interval <= self.SUSPICIOUS_TX_INTERVAL_MINUTES:
            score -= 0.2  # Highly suspicious (bot-like)
        
        return max(0.0, min(1.0, score))  # Clamp between 0 and 1
    
    def _calculate_overall_legitimacy_score(self, volume_drops: List[VolumeDropEvent], 
                                            recoveries: List[RecoveryPattern], df: pd.DataFrame) -> float:
        """Calculate overall legitimacy score for the token."""
        if not volume_drops:
            return 0.8  # No major volume drops = likely legitimate
        
        total_score = 0.0
        weight_sum = 0.0
        
        # Score based on recovery patterns
        for i, drop in enumerate(volume_drops):
            # Weight by severity of drop (more severe drops get more weight)
            weight = drop.drop_percentage
            
            if i < len(recoveries) and recoveries[i]:
                recovery_score = recoveries[i].recovery_legitimacy_score
            else:
                recovery_score = 0.1  # No recovery = likely rugpull
            
            total_score += recovery_score * weight
            weight_sum += weight
        
        base_legitimacy = total_score / weight_sum if weight_sum > 0 else 0.0
        
        # Additional factors
        
        # Factor 1: Overall volume trend (declining volume over time is suspicious)
        if len(df) > 48:  # At least 48 hours of data
            early_volume = df.head(24)["v"].mean()
            late_volume = df.tail(24)["v"].mean()
            volume_trend = late_volume / early_volume if early_volume > 0 else 0
            
            if volume_trend > 0.5:  # Volume maintained relatively well
                base_legitimacy += 0.1
            elif volume_trend < 0.1:  # Volume collapsed permanently
                base_legitimacy -= 0.2
        
        # Factor 2: Number of extreme drops (too many is suspicious)
        extreme_drops = sum(1 for drop in volume_drops if drop.drop_percentage >= self.EXTREME_VOLUME_DROP)
        if extreme_drops > 3:
            base_legitimacy -= 0.1 * (extreme_drops - 3)
        
        # Factor 3: Price-volume correlation (should be somewhat correlated)
        avg_price_correlation = np.mean([drop.price_correlation for drop in volume_drops])
        if 0.3 <= avg_price_correlation <= 0.8:  # Reasonable correlation
            base_legitimacy += 0.1
        elif avg_price_correlation < 0.1:  # Volume drops without price drops (suspicious)
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
                                   legitimacy_score: float) -> str:
        """Generate a human-readable summary of the analysis."""
        if not volume_drops:
            return f"No significant volume drops detected. Legitimacy score: {legitimacy_score:.2f}"
        
        summary_parts = []
        summary_parts.append(f"Detected {len(volume_drops)} significant volume drop events")
        
        if recoveries:
            strong_recoveries = sum(1 for r in recoveries if r.volume_recovery_ratio >= 0.7)
            weak_recoveries = sum(1 for r in recoveries if r.volume_recovery_ratio < 0.3)
            
            summary_parts.append(f"Recovery analysis: {strong_recoveries} strong recoveries, {weak_recoveries} weak recoveries")
            
            # Average recovery time
            avg_recovery_time = np.mean([r.recovery_duration_hours for r in recoveries])
            summary_parts.append(f"Average recovery time: {avg_recovery_time:.1f} hours")
        
        # Drop severity analysis
        extreme_drops = sum(1 for drop in volume_drops if drop.drop_percentage >= self.EXTREME_VOLUME_DROP)
        if extreme_drops > 0:
            summary_parts.append(f"{extreme_drops} extreme volume drops (80%+)")
        
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


def analyze_token_legitimacy(ohlcv_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convenience function to analyze token legitimacy.
    
    Args:
        ohlcv_data: List of OHLCV data dictionaries
        
    Returns:
        Analysis results dictionary
    """
    detector = RugpullVsSuccessDetector()
    return detector.analyze_volume_drops_and_recoveries(ohlcv_data)


# Example usage and testing functions
if __name__ == "__main__":
    # This section can be used for testing the detector
    logging.basicConfig(level=logging.DEBUG)
    
    # Example OHLCV data (would be replaced with real data)
    sample_data = [
        {"ts": 1627776000, "o": 1.0, "h": 1.2, "l": 0.9, "c": 1.1, "v": 10000},
        {"ts": 1627779600, "o": 1.1, "h": 1.3, "l": 1.0, "c": 1.2, "v": 15000},
        # ... more data points
    ]
    
    result = analyze_token_legitimacy(sample_data)
    print(f"Analysis result: {result}")
