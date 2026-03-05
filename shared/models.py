"""
Shared Data Models for the ML-Bullx Token Classification Pipeline.

Defines the canonical data structures used across all pipeline modules:
- TokenMetrics: Aggregated metrics for a single Solana token

All labelers and data providers import from here to ensure consistency.

Author: ML-Bullx Team
Date: 2025-08-01
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# Token Metrics
# =============================================================================

@dataclass
class TokenMetrics:
    """Aggregated metrics for a single token, used by all classification paths.

    Fields are grouped by domain:
    - Core price/volume: Current and historical price snapshots.
    - Boolean flags: Binary indicators derived from price action analysis.
    - Drop tracking: Timestamped records of significant price declines.
    - Holder/transaction: Community adoption indicators.
    - Recovery metrics: Post-drop recovery behavior signals.
    - Extended price analytics: ATH comparisons across time windows.
    - Volume analytics: Volume distribution and trends.
    - Mega-success metrics: Extreme appreciation and relative performance.
    - Legitimacy and scoring: Final evaluation outputs.
    """

    mint_address: str

    # -- Core price/volume metrics --
    current_price: Optional[float] = None          # Latest observed price in USD
    volume_24h: Optional[float] = None             # Rolling 24-hour trading volume (USD)
    market_cap: Optional[float] = None             # Estimated market cap (price * supply)
    launch_price: Optional[float] = None           # Price at token launch / first swap
    peak_price_72h: Optional[float] = None         # Highest price within first 72 hours
    post_ath_peak_price: Optional[float] = None    # Highest price observed after 72h window

    # -- Boolean flags --
    ath_72h_sustained: bool = False                 # True if ATH was reached and held within 72h
    has_sustained_drop: bool = False                # True if a prolonged decline was detected
    liquidity_removal_detected: bool = False        # True if sudden liquidity exit occurred

    # -- Drop tracking --
    price_drops: List[Tuple[datetime, float]] = field(default_factory=list)
    early_phase_drops: List[Tuple[datetime, float, float]] = field(
        default_factory=list
    )  # (timestamp, price_before, price_after) within first 7 days
    late_phase_drops: List[Tuple[datetime, float, float]] = field(
        default_factory=list
    )  # (timestamp, price_before, price_after) after 7 days

    # -- Holder and transaction counts --
    holder_count: Optional[int] = None             # Unique token-account owners with balance > 0
    transaction_count: int = 0                     # Total observed swap transactions

    # -- Recovery metrics --
    max_recovery_after_drop: Optional[float] = None    # Best recovery ratio after a major drop
    rapid_drops_count: int = 0                         # Number of drops > threshold within short window
    days_since_last_major_drop: Optional[int] = None   # Calendar days since most recent large drop
    has_shown_recovery: bool = False                    # True if meaningful bounce detected
    current_trend: Optional[str] = None                # "up", "down", "sideways", or None

    # -- Extended price analytics --
    ath_before_72h: Optional[float] = None         # All-time high before 72-hour mark
    ath_after_72h: Optional[float] = None          # All-time high after 72-hour mark
    avg_price_post_72h: Optional[float] = None     # Average price in the post-72h window
    pre_removal_ath: Optional[float] = None        # ATH before a detected liquidity removal
    post_removal_peak: Optional[float] = None      # Peak price after liquidity removal event

    # -- Volume analytics --
    historical_avg_volume: Optional[float] = None      # Mean daily volume over token lifetime
    peak_volume: Optional[float] = None                # Highest single-period volume observed
    max_volume_drop_ratio: Optional[float] = None      # Largest volume decline ratio
    transaction_count_daily_avg: Optional[float] = None  # Average transactions per day

    # -- Mega-success metrics --
    mega_appreciation: Optional[float] = None          # Total appreciation from launch to ATH
    current_vs_ath_ratio: Optional[float] = None       # Current price / ATH ratio
    total_major_drops: int = 0                         # Count of drops exceeding threshold

    # -- Legitimacy and scoring --
    legitimacy_analysis: Optional[Dict[str, Any]] = None   # Output from RugpullVsSuccessDetector
    final_evaluation_score: Optional[float] = None         # Composite classification confidence
