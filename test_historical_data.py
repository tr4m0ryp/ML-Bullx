#!/usr/bin/env python3
"""
Test script to verify HistoricalData class is working correctly
"""
import sys
import os

# Add pipeline path for imports
pipeline_dir = os.path.join(os.path.dirname(__file__), "on_chain_solana_pipeline")
sys.path.insert(0, pipeline_dir)

from onchain_provider import HistoricalData

# Test 1: Create HistoricalData with correct parameters
print("Test 1: Creating HistoricalData with correct parameters...")
try:
    data = HistoricalData(
        ohlcv=[{'ts': 1234567890, 'o': 1.0, 'h': 1.1, 'l': 0.9, 'c': 1.05, 'v': 1000}],
        peak_price_72h=1.1,
        post_ath_peak_price=1.2
    )
    print("✓ SUCCESS: HistoricalData created successfully")
    print(f"  OHLCV length: {len(data.ohlcv)}")
    print(f"  Peak 72h: {data.peak_price_72h}")
    print(f"  Post ATH peak: {data.post_ath_peak_price}")
except Exception as e:
    print(f"✗ FAILED: {e}")

# Test 2: Try to create HistoricalData with 'mint' parameter (should fail)
print("\nTest 2: Creating HistoricalData with invalid 'mint' parameter...")
try:
    data = HistoricalData(
        ohlcv=[{'ts': 1234567890, 'o': 1.0, 'h': 1.1, 'l': 0.9, 'c': 1.05, 'v': 1000}],
        peak_price_72h=1.1,
        post_ath_peak_price=1.2,
        mint="test_mint_address"  # This should cause the error
    )
    print("✗ UNEXPECTED: HistoricalData created with mint parameter (should have failed)")
except Exception as e:
    print(f"✓ EXPECTED FAILURE: {e}")

print(f"\nImported HistoricalData from: {HistoricalData.__module__}")
