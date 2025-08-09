#!/usr/bin/env python3
"""
Test script for the enhanced token classification system with rugpull vs success detection.

This script demonstrates how the new legitimacy analysis works to distinguish
between successful coins with natural volatility and actual rugpulls.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta

# Add the label directory to path
sys.path.insert(0, os.path.dirname(__file__))

from rugpull_vs_success_detector import analyze_token_legitimacy
from token_labeler_copy import EnhancedTokenLabeler, TokenMetrics

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def create_sample_ohlcv_successful_coin():
    """Create sample OHLCV data for a successful coin with natural volatility."""
    base_time = 1640995200  # Jan 1, 2022
    data = []
    
    # Simulate a successful memecoin launch pattern
    # Phase 1: Initial launch (hours 0-24) - gradual increase
    for i in range(24):
        data.append({
            "ts": base_time + i * 3600,
            "o": 0.001 + i * 0.0001,
            "h": 0.001 + (i + 1) * 0.0001,
            "l": 0.001 + i * 0.0001 * 0.9,
            "c": 0.001 + (i + 0.5) * 0.0001,
            "v": 1000 + i * 200  # Growing volume
        })
    
    # Phase 2: 72h period (hours 24-96) - moderate growth with volatility
    for i in range(24, 96):
        base_price = 0.001 + (i - 24) * 0.0002
        volatility = 0.3 if i % 12 == 0 else 0.1  # Some big moves every 12 hours
        
        data.append({
            "ts": base_time + i * 3600,
            "o": base_price,
            "h": base_price * (1 + volatility),
            "l": base_price * (1 - volatility * 0.7),
            "c": base_price * (1 + volatility * 0.2),
            "v": 2000 + (i - 24) * 150 + (500 if i % 12 == 0 else 0)  # Volume spikes with volatility
        })
    
    # Phase 3: Post-72h breakthrough (hours 96-168) - significant growth
    breakthrough_multiplier = 2.0
    for i in range(96, 168):
        base_price = 0.001 + (96 - 24) * 0.0002
        breakthrough_price = base_price * breakthrough_multiplier * (1 + (i - 96) * 0.01)
        
        data.append({
            "ts": base_time + i * 3600,
            "o": breakthrough_price,
            "h": breakthrough_price * 1.15,
            "l": breakthrough_price * 0.90,
            "c": breakthrough_price * 1.05,
            "v": 5000 + (i - 96) * 200  # Higher volume during breakthrough
        })
    
    # Phase 4: Natural correction and stabilization (hours 168-336) - 1 week
    peak_price = breakthrough_price * 1.05
    for i in range(168, 336):
        # Natural decline and stabilization
        decline_factor = 0.95 - (i - 168) * 0.001  # Gradual decline
        stable_price = peak_price * max(0.6, decline_factor)  # Don't go below 60% of peak
        
        # Occasional volume spikes (organic buying)
        volume_spike = 1000 if (i - 168) % 20 == 0 else 0
        
        data.append({
            "ts": base_time + i * 3600,
            "o": stable_price,
            "h": stable_price * 1.08,
            "l": stable_price * 0.94,
            "c": stable_price * 1.02,
            "v": 1500 + volume_spike + (i - 168) * 10  # Declining but organic volume
        })
    
    return data

def create_sample_ohlcv_rugpull_coin():
    """Create sample OHLCV data for a rugpull coin."""
    base_time = 1640995200  # Jan 1, 2022
    data = []
    
    # Phase 1: Initial pump (hours 0-48) - artificial growth
    for i in range(48):
        pump_multiplier = 1 + i * 0.05  # Aggressive pumping
        base_price = 0.001 * pump_multiplier
        
        data.append({
            "ts": base_time + i * 3600,
            "o": base_price,
            "h": base_price * 1.10,
            "l": base_price * 0.98,
            "c": base_price * 1.05,
            "v": 3000 + i * 500  # High volume during pump
        })
    
    # Phase 2: Peak and immediate dump (hours 48-72) - rugpull execution
    peak_price = base_price * 1.05
    for i in range(48, 72):
        # Rapid price collapse
        collapse_factor = 1 - (i - 48) * 0.15  # 15% drop per hour
        collapsed_price = peak_price * max(0.1, collapse_factor)
        
        # Volume spikes during dump then dies
        if i <= 50:  # First few hours of dump
            volume = 8000  # Massive dump volume
        else:
            volume = 200 + (72 - i) * 50  # Rapidly declining volume
        
        data.append({
            "ts": base_time + i * 3600,
            "o": collapsed_price * 1.1,
            "h": collapsed_price * 1.15,
            "l": collapsed_price * 0.80,
            "c": collapsed_price,
            "v": volume
        })
    
    # Phase 3: Dead coin (hours 72-168) - minimal activity
    dead_price = collapsed_price
    for i in range(72, 168):
        # Minimal price movement, dead volume
        dead_price *= 0.995  # Slow decline
        
        data.append({
            "ts": base_time + i * 3600,
            "o": dead_price,
            "h": dead_price * 1.02,
            "l": dead_price * 0.98,
            "c": dead_price,
            "v": 50 + (i % 10) * 5  # Very low, sporadic volume
        })
    
    return data

def create_sample_ohlcv_successful_with_volatility():
    """Create sample OHLCV data for a successful coin that has extreme volatility (like many successful memecoins)."""
    base_time = 1640995200  # Jan 1, 2022
    data = []
    
    # This simulates a successful memecoin that has extreme volume drops and price volatility
    # but shows legitimate recovery patterns
    
    # Phase 1: Launch and initial growth (0-72h)
    for i in range(72):
        growth_factor = 1 + i * 0.02
        base_price = 0.001 * growth_factor
        
        # Add some natural volatility
        volatility = 0.2 + (0.1 if i % 8 == 0 else 0)
        
        data.append({
            "ts": base_time + i * 3600,
            "o": base_price,
            "h": base_price * (1 + volatility),
            "l": base_price * (1 - volatility * 0.8),
            "c": base_price * (1 + volatility * 0.3),
            "v": 2000 + i * 100 + (1000 if i % 8 == 0 else 0)
        })
    
    # Phase 2: Major breakthrough but with extreme volatility (72-120h)
    breakthrough_price = base_price * 3  # 3x breakthrough after 72h
    for i in range(72, 120):
        current_price = breakthrough_price * (1 + (i - 72) * 0.01)
        
        # Extreme volatility event at hour 84 (major volume drop)
        if i == 84:
            # Massive volume drop (90% reduction) but organic recovery
            volume = 500  # 90% drop from normal ~5000
            price_impact = 0.4  # 40% price drop
        elif 85 <= i <= 96:
            # Gradual organic recovery over 12 hours
            recovery_progress = (i - 85) / 11  # 0 to 1
            volume = 500 + recovery_progress * 4500  # Volume recovers gradually
            price_impact = 0.4 * (1 - recovery_progress * 0.7)  # Price recovers 70%
        else:
            volume = 4000 + i * 50
            price_impact = 0
        
        actual_price = current_price * (1 - price_impact)
        
        data.append({
            "ts": base_time + i * 3600,
            "o": actual_price,
            "h": actual_price * 1.12,
            "l": actual_price * 0.90,
            "c": actual_price * 1.06,
            "v": volume
        })
    
    # Phase 3: Continued success with stabilization (120h+)
    stable_price = actual_price * 1.06
    for i in range(120, 240):
        # Maintain high price with natural decline
        decline_factor = 0.998  # Very slow decline
        stable_price *= decline_factor
        
        # Occasional organic volume spikes
        if (i - 120) % 24 == 0:  # Daily volume spikes
            volume = 6000
        else:
            volume = 2000 + (i - 120) * 20
        
        data.append({
            "ts": base_time + i * 3600,
            "o": stable_price,
            "h": stable_price * 1.08,
            "l": stable_price * 0.94,
            "c": stable_price * 1.02,
            "v": volume
        })
    
    return data

def test_legitimacy_analysis():
    """Test the legitimacy analysis on different coin types."""
    logger.info("=" * 60)
    logger.info("TESTING RUGPULL vs SUCCESS DETECTOR")
    logger.info("=" * 60)
    
    # Test 1: Successful coin with natural volatility
    logger.info("\n🟢 TEST 1: Successful coin with natural volatility")
    logger.info("-" * 50)
    successful_data = create_sample_ohlcv_successful_coin()
    result1 = analyze_token_legitimacy(successful_data)
    
    logger.info(f"Classification hint: {result1['classification_hint']}")
    logger.info(f"Legitimacy score: {result1['overall_legitimacy_score']:.2f}")
    logger.info(f"Summary: {result1['analysis_summary']}")
    
    # Test 2: Clear rugpull
    logger.info("\n🔴 TEST 2: Clear rugpull")
    logger.info("-" * 50)
    rugpull_data = create_sample_ohlcv_rugpull_coin()
    result2 = analyze_token_legitimacy(rugpull_data)
    
    logger.info(f"Classification hint: {result2['classification_hint']}")
    logger.info(f"Legitimacy score: {result2['overall_legitimacy_score']:.2f}")
    logger.info(f"Summary: {result2['analysis_summary']}")
    
    # Test 3: Successful coin with extreme volatility (challenging case)
    logger.info("\n🟡 TEST 3: Successful coin with extreme volatility")
    logger.info("-" * 50)
    volatile_success_data = create_sample_ohlcv_successful_with_volatility()
    result3 = analyze_token_legitimacy(volatile_success_data)
    
    logger.info(f"Classification hint: {result3['classification_hint']}")
    logger.info(f"Legitimacy score: {result3['overall_legitimacy_score']:.2f}")
    logger.info(f"Summary: {result3['analysis_summary']}")
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY OF RESULTS")
    logger.info("=" * 60)
    logger.info(f"Successful coin:           {result1['classification_hint']} (score: {result1['overall_legitimacy_score']:.2f})")
    logger.info(f"Rugpull coin:              {result2['classification_hint']} (score: {result2['overall_legitimacy_score']:.2f})")
    logger.info(f"Volatile successful coin:  {result3['classification_hint']} (score: {result3['overall_legitimacy_score']:.2f})")
    
    return result1, result2, result3

if __name__ == "__main__":
    # Run the test
    test_legitimacy_analysis()
    
    logger.info("\n" + "=" * 60)
    logger.info("TEST COMPLETE")
    logger.info("=" * 60)
    logger.info("The legitimacy detector helps distinguish between:")
    logger.info("1. ✅ Successful coins with natural volume/price volatility")
    logger.info("2. ❌ Rugpulls with coordinated/artificial patterns")  
    logger.info("3. 🤔 Mixed cases requiring human judgment")
    logger.info("")
    logger.info("This analysis is now integrated into the main token labeler")
    logger.info("to prevent successful coins from being mislabeled as rugpulls.")
