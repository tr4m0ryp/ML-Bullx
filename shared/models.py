"""Shared data models used across pipeline modules.

TokenMetrics is the single source of truth -- all labelers import from here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TokenMetrics:
    """Aggregated metrics for a single token, used by all classification paths."""

    mint_address: str

    # Core price/volume metrics
    current_price: Optional[float] = None
    volume_24h: Optional[float] = None
    market_cap: Optional[float] = None
    launch_price: Optional[float] = None
    peak_price_72h: Optional[float] = None
    post_ath_peak_price: Optional[float] = None

    # Boolean flags
    ath_72h_sustained: bool = False
    has_sustained_drop: bool = False
    liquidity_removal_detected: bool = False

    # Drop tracking
    price_drops: List[Tuple[datetime, float]] = field(default_factory=list)
    early_phase_drops: List[Tuple[datetime, float, float]] = field(
        default_factory=list
    )
    late_phase_drops: List[Tuple[datetime, float, float]] = field(
        default_factory=list
    )

    # Holder and transaction counts
    holder_count: Optional[int] = None
    transaction_count: int = 0

    # Recovery metrics
    max_recovery_after_drop: Optional[float] = None
    rapid_drops_count: int = 0
    days_since_last_major_drop: Optional[int] = None
    has_shown_recovery: bool = False
    current_trend: Optional[str] = None

    # Extended price analytics
    ath_before_72h: Optional[float] = None
    ath_after_72h: Optional[float] = None
    avg_price_post_72h: Optional[float] = None
    pre_removal_ath: Optional[float] = None
    post_removal_peak: Optional[float] = None

    # Volume analytics
    historical_avg_volume: Optional[float] = None
    peak_volume: Optional[float] = None
    max_volume_drop_ratio: Optional[float] = None
    transaction_count_daily_avg: Optional[float] = None

    # Mega-success metrics
    mega_appreciation: Optional[float] = None
    current_vs_ath_ratio: Optional[float] = None
    total_major_drops: int = 0

    # Legitimacy and scoring
    legitimacy_analysis: Optional[Dict[str, Any]] = None
    final_evaluation_score: Optional[float] = None
