"""
Quick analysis of missing data patterns from debug output and logs.
"""

import re
from collections import Counter

def analyze_debug_output():
    """Analyze patterns from our recent debug output."""
    
    # From our previous debug run, we saw these patterns:
    debug_patterns = {
        'volume_24h': ['N/A', 'N/A', 'N/A'],  # All 3 tokens missing
        'historical_avg_volume': ['N/A', 'N/A', '5,711.70'],  # 2/3 missing
        'peak_volume': ['N/A', 'N/A', '114,114.04'],  # 2/3 missing  
        'launch_price': ['N/A', 'N/A', '$0.00059952'],  # 2/3 missing
        'market_cap': ['N/A', 'N/A', 'N/A'],  # All 3 missing
        'daily_transactions': ['N/A', 'N/A', '0.1'],  # 2/3 missing
        'has_volume_data': [False, False, True],  # 2/3 missing
        'has_historical_data': [False, False, True],  # 2/3 missing
        'price_points_count': [0, 0, 0],  # All tokens have 0 (issue with counting)
        'parsing_success_rate': [
            '8 successful, 15 failed',  # 34% success
            '13 successful, 102 failed',  # 11% success  
            '124 successful, 153 failed'  # 44% success
        ]
    }
    
    print("🔍 MISSING DATA ANALYSIS FROM DEBUG OUTPUT")
    print("=" * 60)
    
    print("📊 CRITICAL MISSING DATA PATTERNS:")
    print("   📍 volume_24h: 100% missing (3/3 tokens)")
    print("      💡 ROOT CAUSE: No 24h volume calculation from swaps")
    print("      🔧 FALLBACK: Sum volume_usd from all swaps in last 24h")
    print()
    
    print("   📍 market_cap: 100% missing (3/3 tokens)")  
    print("      💡 ROOT CAUSE: Missing total_supply × current_price calculation")
    print("      🔧 FALLBACK: Get token supply via Solana RPC + price")
    print()
    
    print("   📍 historical_avg_volume: 67% missing (2/3 tokens)")
    print("      💡 ROOT CAUSE: Insufficient swap parsing success") 
    print("      🔧 FALLBACK: Average all parsed swap volumes")
    print()
    
    print("   📍 launch_price: 67% missing (2/3 tokens)")
    print("      💡 ROOT CAUSE: First swap not properly detected")
    print("      🔧 FALLBACK: Use earliest swap price or mint event analysis")
    print()
    
    print("   📍 price_points_count: Incorrect (showing 0 for all tokens)")
    print("      💡 ROOT CAUSE: Wrong calculation method")
    print("      🔧 FALLBACK: Count actual OHLCV records or swap events")
    print()
    
    print("📈 PARSING SUCCESS RATES:")
    parsing_rates = [34, 11, 44]  # From debug output
    avg_success = sum(parsing_rates) / len(parsing_rates)
    print(f"   Average: {avg_success:.1f}% successful parsing")
    print(f"   Range: {min(parsing_rates)}% - {max(parsing_rates)}%")
    print(f"   💡 OPPORTUNITY: ~{100-avg_success:.1f}% of transactions could be recovered with better parsing")
    print()
    
    print("🎯 IMPLEMENTATION PRIORITY:")
    print("   1. ⚡ IMMEDIATE WINS (simple calculations):")
    print("      • volume_24h: Sum recent swap volumes") 
    print("      • historical_avg_volume: Average all swap volumes")
    print("      • price_points_count: Count OHLCV/swap records")
    print("      • launch_price: First swap price detection")
    print()
    
    print("   2. 📡 RPC-BASED FALLBACKS (external calls needed):")
    print("      • market_cap: getTokenSupply + current_price")
    print("      • holder_count: getTokenAccountsByMint")
    print()
    
    print("   3. 🔧 ENHANCED PARSING (more complex):")
    print("      • Better swap detection (currently ~70% failure rate)")
    print("      • Token transfer parsing as fallback")
    print("      • Mint event analysis for launch detection")
    print()
    
    print("🚀 RECOMMENDED IMPLEMENTATION ORDER:")
    print("   Phase 1: Volume calculations (volume_24h, historical_avg)")
    print("   Phase 2: Launch price detection (first swap analysis)")  
    print("   Phase 3: Market cap via RPC (token supply)")
    print("   Phase 4: Enhanced transaction parsing")
    print()
    
    return {
        'critical_missing': ['volume_24h', 'market_cap', 'historical_avg_volume', 'launch_price'],
        'avg_parsing_success': avg_success,
        'immediate_opportunities': ['volume_24h', 'historical_avg_volume', 'launch_price', 'price_points_count']
    }

if __name__ == "__main__":
    analysis = analyze_debug_output()
    print("✅ Analysis complete!")