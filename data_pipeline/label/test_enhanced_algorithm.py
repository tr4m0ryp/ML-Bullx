#!/usr/bin/env python3
"""
Test script to demonstrate the enhanced token classification algorithm.
This shows how tokens with early drops can still be classified as successful.
"""

import sys
import os
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Tuple, Optional

# Add the current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

# We'll simulate the TokenMetrics and classification logic for testing
@dataclass
class MockTokenMetrics:
    mint_address: str
    current_price: Optional[float] = None
    volume_24h: Optional[float] = None
    market_cap: Optional[float] = None
    peak_price_72h: Optional[float] = None
    post_ath_peak_price: Optional[float] = None
    has_sustained_drop: bool = False
    price_drops: List[Tuple[datetime, float]] = None
    holder_count: Optional[int] = None
    
    # Enhanced metrics
    early_phase_drops: List[Tuple[datetime, float, float]] = None
    late_phase_drops: List[Tuple[datetime, float, float]] = None
    max_recovery_after_drop: Optional[float] = None
    rapid_drops_count: int = 0
    days_since_last_major_drop: Optional[int] = None
    has_shown_recovery: bool = False
    current_trend: Optional[str] = None

    def __post_init__(self):
        if self.price_drops is None:
            self.price_drops = []
        if self.early_phase_drops is None:
            self.early_phase_drops = []
        if self.late_phase_drops is None:
            self.late_phase_drops = []

class MockEnhancedClassifier:
    """Mock classifier that implements the same logic as EnhancedTokenLabeler"""
    
    # Constants from the main class
    RUG_THRESHOLD = 0.70
    RUG_RAPID_DROP_HOURS = 6
    RUG_NO_RECOVERY_DAYS = 14
    SUCCESS_APPRECIATION = 10.0
    SUCCESS_MIN_HOLDERS = 100
    SUCCESS_RECOVERY_MULTIPLIER = 5.0
    INACTIVE_VOLUME_THRESHOLD = 1000
    INACTIVE_HOLDER_THRESHOLD = 10
    EARLY_PHASE_DAYS = 7
    RECOVERY_ANALYSIS_DAYS = 30

    def classify(self, m: MockTokenMetrics) -> str:
        """Enhanced classification logic"""
        if self._is_inactive(m):
            return "inactive"
        if self._is_success(m):
            return "successful"
        if self._is_rugpull(m):
            return "rugpull"
        return "unsuccessful"

    def _is_inactive(self, m: MockTokenMetrics) -> bool:
        if m.volume_24h is not None and m.volume_24h < self.INACTIVE_VOLUME_THRESHOLD:
            return True
        if m.holder_count is not None and m.holder_count < self.INACTIVE_HOLDER_THRESHOLD:
            return True
        return False

    def _is_rugpull(self, m: MockTokenMetrics) -> bool:
        if not m.price_drops:
            return False
        
        major_drops = [d for _, d in m.price_drops if d >= self.RUG_THRESHOLD]
        if not major_drops:
            return False
        
        # Multiple rapid drops
        if m.rapid_drops_count >= 2:
            return True
        
        # Late phase drops without recovery
        if m.late_phase_drops:
            for _, drop_pct, recovery_ratio in m.late_phase_drops:
                if drop_pct >= self.RUG_THRESHOLD and recovery_ratio < self.SUCCESS_RECOVERY_MULTIPLIER:
                    if m.days_since_last_major_drop and m.days_since_last_major_drop >= self.RUG_NO_RECOVERY_DAYS:
                        return True
        
        # Early drops without ANY recovery
        if m.early_phase_drops:
            max_early_recovery = max((recovery for _, _, recovery in m.early_phase_drops), default=0)
            if max_early_recovery < 2.0 and m.days_since_last_major_drop and m.days_since_last_major_drop >= self.RUG_NO_RECOVERY_DAYS:
                return True
        
        # Declining trend after drops
        if m.current_trend == "declining" and m.days_since_last_major_drop and m.days_since_last_major_drop >= 7:
            return True
        
        return False

    def _is_success(self, m: MockTokenMetrics) -> bool:
        if None in (m.peak_price_72h, m.post_ath_peak_price, m.holder_count):
            return False
        
        if m.holder_count < self.SUCCESS_MIN_HOLDERS:
            return False
        
        # Traditional success
        if (m.post_ath_peak_price / m.peak_price_72h >= self.SUCCESS_APPRECIATION and 
            not m.has_sustained_drop):
            return True
        
        # Recovery-based success
        if m.has_shown_recovery and m.max_recovery_after_drop >= self.SUCCESS_RECOVERY_MULTIPLIER:
            if (m.current_trend in ["recovering", "stable"] and 
                m.holder_count >= self.SUCCESS_MIN_HOLDERS * 1.5):
                if m.days_since_last_major_drop and m.days_since_last_major_drop >= 7:
                    return True
        
        # Early phase recovery success
        if m.early_phase_drops:
            best_early_recovery = max((recovery for _, _, recovery in m.early_phase_drops), default=0)
            if (best_early_recovery >= self.SUCCESS_RECOVERY_MULTIPLIER and 
                m.current_trend != "declining" and
                m.holder_count >= self.SUCCESS_MIN_HOLDERS):
                return True
        
        return False

def create_test_scenarios():
    """Create test scenarios to demonstrate the enhanced algorithm"""
    
    now = datetime.now()
    early_drop_time = now - timedelta(days=5)  # Early phase drop
    late_drop_time = now - timedelta(days=20)  # Late phase drop
    
    scenarios = []
    
    # Scenario 1: Traditional successful token (no major drops)
    scenarios.append({
        "name": "Traditional Success",
        "token": MockTokenMetrics(
            mint_address="TRADITIONAL_SUCCESS",
            current_price=1.0,
            volume_24h=50000,
            peak_price_72h=0.1,
            post_ath_peak_price=1.0,
            holder_count=200,
            has_sustained_drop=False,
            price_drops=[],
            current_trend="stable"
        ),
        "expected": "successful"
    })
    
    # Scenario 2: Early drop with strong recovery (should be successful)
    scenarios.append({
        "name": "Early Drop + Recovery Success",
        "token": MockTokenMetrics(
            mint_address="EARLY_DROP_RECOVERY",
            current_price=1.0,
            volume_24h=30000,
            peak_price_72h=0.1,
            post_ath_peak_price=1.0,
            holder_count=150,
            has_sustained_drop=True,
            price_drops=[(early_drop_time, 0.75)],  # 75% drop in early phase
            early_phase_drops=[(early_drop_time, 0.75, 8.0)],  # But 8x recovery!
            max_recovery_after_drop=8.0,
            has_shown_recovery=True,
            days_since_last_major_drop=25,
            current_trend="stable"
        ),
        "expected": "successful"
    })
    
    # Scenario 3: Multiple rapid drops (clear rugpull)
    scenarios.append({
        "name": "Multiple Rapid Drops Rugpull",
        "token": MockTokenMetrics(
            mint_address="RAPID_DUMPS",
            current_price=0.01,
            volume_24h=5000,
            peak_price_72h=1.0,
            post_ath_peak_price=0.5,
            holder_count=50,
            has_sustained_drop=True,
            price_drops=[(now - timedelta(hours=2), 0.8), (now - timedelta(hours=1), 0.7)],
            rapid_drops_count=2,
            max_recovery_after_drop=1.2,
            days_since_last_major_drop=0,
            current_trend="declining"
        ),
        "expected": "rugpull"
    })
    
    # Scenario 4: Late phase drop without recovery (rugpull)
    scenarios.append({
        "name": "Late Phase Drop No Recovery",
        "token": MockTokenMetrics(
            mint_address="LATE_DUMP",
            current_price=0.05,
            volume_24h=8000,
            peak_price_72h=0.1,
            post_ath_peak_price=1.0,
            holder_count=80,
            has_sustained_drop=True,
            price_drops=[(late_drop_time, 0.8)],
            late_phase_drops=[(late_drop_time, 0.8, 1.1)],  # Only 1.1x recovery
            max_recovery_after_drop=1.1,
            days_since_last_major_drop=20,
            current_trend="declining"
        ),
        "expected": "rugpull"
    })
    
    # Scenario 5: Inactive token
    scenarios.append({
        "name": "Inactive Token",
        "token": MockTokenMetrics(
            mint_address="INACTIVE",
            current_price=0.001,
            volume_24h=100,  # Very low volume
            holder_count=5,   # Very few holders
            current_trend="stable"
        ),
        "expected": "inactive"
    })
    
    # Scenario 6: Regular unsuccessful token
    scenarios.append({
        "name": "Regular Unsuccessful",
        "token": MockTokenMetrics(
            mint_address="UNSUCCESSFUL",
            current_price=0.05,
            volume_24h=15000,
            peak_price_72h=0.1,
            post_ath_peak_price=0.2,  # Only 2x appreciation
            holder_count=80,
            has_sustained_drop=True,
            max_recovery_after_drop=2.0,
            current_trend="stable"
        ),
        "expected": "unsuccessful"
    })
    
    return scenarios

def run_tests():
    """Run test scenarios and display results"""
    classifier = MockEnhancedClassifier()
    scenarios = create_test_scenarios()
    
    print("=" * 80)
    print("ENHANCED TOKEN CLASSIFICATION ALGORITHM TEST")
    print("=" * 80)
    print()
    
    for i, scenario in enumerate(scenarios, 1):
        token = scenario["token"]
        expected = scenario["expected"]
        actual = classifier.classify(token)
        
        status = "✓ PASS" if actual == expected else "✗ FAIL"
        
        print(f"{i}. {scenario['name']}")
        print(f"   Token: {token.mint_address}")
        print(f"   Expected: {expected} | Actual: {actual} | {status}")
        
        # Show key metrics
        print(f"   Metrics:")
        print(f"     - Price: {token.current_price}, Volume: {token.volume_24h}, Holders: {token.holder_count}")
        print(f"     - Early drops: {len(token.early_phase_drops)}, Late drops: {len(token.late_phase_drops)}")
        print(f"     - Max recovery: {token.max_recovery_after_drop}x, Trend: {token.current_trend}")
        print(f"     - Rapid drops: {token.rapid_drops_count}, Days since drop: {token.days_since_last_major_drop}")
        print()
    
    print("=" * 80)
    print("KEY IMPROVEMENTS:")
    print("- Early phase drops (first 7 days) are treated more leniently")
    print("- Strong recovery patterns can override drop-based classification")
    print("- Multiple rapid drops indicate coordinated rugpulls") 
    print("- Late phase drops require longer recovery periods")
    print("- Inactive tokens are identified by low volume/holders")
    print("=" * 80)

if __name__ == "__main__":
    run_tests()
