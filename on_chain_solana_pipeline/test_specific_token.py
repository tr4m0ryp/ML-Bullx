#!/usr/bin/env python3
"""
Direct test of token 5fr1bB2Tz6ywjoFc9K1VoX3ukGHP6xPUD5bFU4nX1Zs9
Using the enhanced classification algorithm.
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

TARGET_TOKEN = "5fr1bB2Tz6ywjoFc9K1VoX3ukGHP6xPUD5bFU4nX1Zs9"

# Enhanced constants
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

def classify_token(m: MockTokenMetrics) -> str:
    """Enhanced classification algorithm"""
    if is_inactive(m):
        return "inactive"
    if is_success(m):
        return "successful"
    if is_rugpull(m):
        return "rugpull"
    return "unsuccessful"

def is_inactive(m: MockTokenMetrics) -> bool:
    if m.volume_24h is not None and m.volume_24h < INACTIVE_VOLUME_THRESHOLD:
        return True
    if m.holder_count is not None and m.holder_count < INACTIVE_HOLDER_THRESHOLD:
        return True
    return False

def is_rugpull(m: MockTokenMetrics) -> bool:
    if not m.price_drops:
        return False
    
    major_drops = [d for _, d in m.price_drops if d >= RUG_THRESHOLD]
    if not major_drops:
        return False
    
    # Multiple rapid drops
    if m.rapid_drops_count >= 2:
        return True
    
    # Late phase drops without recovery
    if m.late_phase_drops:
        for _, drop_pct, recovery_ratio in m.late_phase_drops:
            if drop_pct >= RUG_THRESHOLD and recovery_ratio < SUCCESS_RECOVERY_MULTIPLIER:
                if m.days_since_last_major_drop and m.days_since_last_major_drop >= RUG_NO_RECOVERY_DAYS:
                    return True
    
    # Early drops without recovery
    if m.early_phase_drops:
        max_early_recovery = max((recovery for _, _, recovery in m.early_phase_drops), default=0)
        if max_early_recovery < 2.0 and m.days_since_last_major_drop and m.days_since_last_major_drop >= RUG_NO_RECOVERY_DAYS:
            return True
    
    # Declining trend after drops
    if m.current_trend == "declining" and m.days_since_last_major_drop and m.days_since_last_major_drop >= 7:
        return True
    
    return False

def is_success(m: MockTokenMetrics) -> bool:
    if None in (m.peak_price_72h, m.post_ath_peak_price, m.holder_count):
        return False
    
    if m.holder_count < SUCCESS_MIN_HOLDERS:
        return False
    
    # Traditional success
    if (m.post_ath_peak_price / m.peak_price_72h >= SUCCESS_APPRECIATION and 
        not m.has_sustained_drop):
        return True
    
    # Recovery-based success
    if m.has_shown_recovery and m.max_recovery_after_drop >= SUCCESS_RECOVERY_MULTIPLIER:
        if (m.current_trend in ["recovering", "stable"] and 
            m.holder_count >= SUCCESS_MIN_HOLDERS * 1.5):
            if m.days_since_last_major_drop and m.days_since_last_major_drop >= 7:
                return True
    
    # Early phase recovery success
    if m.early_phase_drops:
        best_early_recovery = max((recovery for _, _, recovery in m.early_phase_drops), default=0)
        if (best_early_recovery >= SUCCESS_RECOVERY_MULTIPLIER and 
            m.current_trend != "declining" and
            m.holder_count >= SUCCESS_MIN_HOLDERS):
            return True
    
    return False

async def test_with_onchain_data():
    """Try to get real on-chain data for the token"""
    print(f"🔍 Attempting to get real on-chain data for: {TARGET_TOKEN}")
    
    try:
        from onchain_provider import OnChainDataProvider
        from config.config_loader import load_config
        
        config = load_config()
        
        async with OnChainDataProvider(config) as provider:
            print("✅ Connected to on-chain data provider")
            
            # Gather real metrics
            metrics = MockTokenMetrics(TARGET_TOKEN)
            
            # Get current price data
            price_data = await provider.get_current_price(TARGET_TOKEN)
            if price_data:
                metrics.current_price = price_data.price
                metrics.volume_24h = price_data.volume_24h
                metrics.market_cap = price_data.market_cap
                print(f"💰 Price: ${price_data.price}")
                print(f"📊 24h Volume: ${price_data.volume_24h:,.2f}")
                print(f"💎 Market Cap: ${price_data.market_cap:,.2f}")
            
            # Get historical data
            hist_data = await provider.get_historical_data(TARGET_TOKEN)
            if hist_data:
                metrics.peak_price_72h = hist_data.peak_price_72h
                metrics.post_ath_peak_price = hist_data.post_ath_peak_price
                print(f"📈 72h Peak: ${hist_data.peak_price_72h}")
                print(f"🚀 Post-ATH Peak: ${hist_data.post_ath_peak_price}")
                
                # Analyze OHLCV data for enhanced metrics
                if hist_data.ohlcv:
                    print(f"📊 OHLCV Data Points: {len(hist_data.ohlcv)}")
                    # Here we would run the enhanced analysis
                    # For now, let's do a simple analysis
                    analyze_price_history(metrics, hist_data.ohlcv)
            
            # Get holder count
            holders = await provider.get_holder_count(TARGET_TOKEN)
            if holders:
                metrics.holder_count = holders
                print(f"👥 Holders: {holders}")
            
            # Classify the token
            label = classify_token(metrics)
            
            print(f"\n🏷️  CLASSIFICATION RESULT:")
            print(f"   Token: {TARGET_TOKEN}")
            print(f"   Label: {label.upper()}")
            
            # Log reasoning
            print(f"\n📋 CLASSIFICATION REASONING:")
            print(f"   - Current price: ${metrics.current_price}")
            print(f"   - Volume 24h: ${metrics.volume_24h:,.2f}")
            print(f"   - Holder count: {metrics.holder_count}")
            print(f"   - Early drops: {len(metrics.early_phase_drops)}")
            print(f"   - Late drops: {len(metrics.late_phase_drops)}")
            print(f"   - Max recovery: {metrics.max_recovery_after_drop}x")
            print(f"   - Current trend: {metrics.current_trend}")
            
            return label
            
    except Exception as e:
        print(f"❌ Error getting on-chain data: {e}")
        print("🔄 Falling back to simulated analysis...")
        return await test_with_simulated_data()

def analyze_price_history(metrics, ohlcv_data):
    """Analyze OHLCV data for enhanced metrics"""
    if not ohlcv_data:
        return
    
    # Simple analysis for demonstration
    max_drop = 0
    recovery_found = False
    
    for i, candle in enumerate(ohlcv_data):
        if candle.get('h', 0) > 0:
            drop = 1 - (candle.get('l', 0) / candle.get('h', 1))
            if drop > max_drop:
                max_drop = drop
                
                # Check for recovery in subsequent candles
                for j in range(i+1, min(i+10, len(ohlcv_data))):  # Check next 10 candles
                    future_candle = ohlcv_data[j]
                    if future_candle.get('h', 0) > candle.get('l', 0) * 2:  # 2x recovery
                        recovery_found = True
                        break
    
    if max_drop >= 0.7:
        metrics.price_drops = [(datetime.now() - timedelta(days=10), max_drop)]
        if recovery_found:
            metrics.has_shown_recovery = True
            metrics.max_recovery_after_drop = 3.0  # Estimated
            metrics.current_trend = "stable"
        else:
            metrics.current_trend = "declining"

async def test_with_simulated_data():
    """Test with simulated data as fallback"""
    print(f"🧪 Testing with simulated data for token: {TARGET_TOKEN}")
    
    # Create realistic test scenarios
    scenarios = [
        # Scenario 1: Token with early drop but good recovery
        MockTokenMetrics(
            mint_address=TARGET_TOKEN,
            current_price=0.05,
            volume_24h=25000,
            peak_price_72h=0.01,
            post_ath_peak_price=0.08,
            holder_count=150,
            early_phase_drops=[(datetime.now() - timedelta(days=5), 0.75, 6.0)],
            max_recovery_after_drop=6.0,
            has_shown_recovery=True,
            current_trend="stable",
            days_since_last_major_drop=20
        ),
        
        # Scenario 2: Rugpull token
        MockTokenMetrics(
            mint_address=TARGET_TOKEN,
            current_price=0.001,
            volume_24h=5000,
            holder_count=30,
            rapid_drops_count=2,
            current_trend="declining",
            days_since_last_major_drop=1
        ),
        
        # Scenario 3: Successful token
        MockTokenMetrics(
            mint_address=TARGET_TOKEN,
            current_price=1.0,
            volume_24h=100000,
            peak_price_72h=0.05,
            post_ath_peak_price=1.0,
            holder_count=250,
            current_trend="stable"
        )
    ]
    
    print(f"\n📊 Testing {len(scenarios)} possible scenarios:")
    
    for i, metrics in enumerate(scenarios, 1):
        label = classify_token(metrics)
        print(f"\n{i}. Scenario {i}:")
        print(f"   Label: {label.upper()}")
        print(f"   Price: ${metrics.current_price}, Volume: ${metrics.volume_24h:,.0f}, Holders: {metrics.holder_count}")
        
        if label == "successful" and metrics.early_phase_drops:
            print(f"   → SUCCESS despite early {len(metrics.early_phase_drops)} drop(s) due to {metrics.max_recovery_after_drop}x recovery")
        elif label == "rugpull":
            print(f"   → RUGPULL due to rapid drops: {metrics.rapid_drops_count}, trend: {metrics.current_trend}")
    
    return "simulated_test_complete"

async def main():
    print("🚀 Enhanced Token Classification Test")
    print("=" * 60)
    print(f"Target Token: {TARGET_TOKEN}")
    print("=" * 60)
    
    # Try real data first, fallback to simulation
    result = await test_with_onchain_data()
    
    print(f"\n✅ Test completed with result: {result}")
    print("\n💡 The enhanced algorithm considers:")
    print("   - Recovery patterns after major drops")
    print("   - Early vs late phase drop timing")
    print("   - Rapid vs gradual drop patterns")
    print("   - Current trend analysis")
    print("   - Holder count and volume thresholds")

if __name__ == "__main__":
    asyncio.run(main())
