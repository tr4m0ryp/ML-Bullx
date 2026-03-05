"""
Missing Data Pattern Analyzer for Token Labeling.

Runs a set of test tokens through the metrics-gathering pipeline and
reports which fields are most frequently missing:
- Per-token breakdown of present vs. missing fields.
- Aggregate missing-data frequency table.
- OHLCV data-quality distribution (none / minimal / insufficient / good).
- Parsing failure type counts.
- Prioritized list of fallback implementation opportunities.

Author: ML-Bullx Team
Date: 2025-08-01
"""

import asyncio
import sys
from collections import Counter, defaultdict

from data_pipeline.label.token_labeler import EnhancedTokenLabeler


# =============================================================================
# Missing Data Analysis
# =============================================================================

async def analyze_missing_data_patterns():
    """Analyze which metrics are most commonly missing across a set of test tokens.

    Iterates over a hard-coded list of representative token mint
    addresses, gathers metrics for each via the labeling pipeline,
    and tallies which fields come back empty.  Prints a comprehensive
    report including per-field miss rates, OHLCV quality buckets,
    parsing error types, and recommended implementation priorities.
    """

    test_tokens = [
        "5YPpdaFU3AfDAT3gb4DjYmjcfu9huuGaLJBxB8Sapump",
        "Bn4nBhQa2JAFGhSbjqgC9dCYMyAF3CGEaAzshbaapump",
        "FPCiQD3FQv4TzinaXfphopSNDMMxmEeNELtSYEPVavHJ",
        "X3qPC4HYu3DBSxGYbevftb16RJYNm3c87qV1z3tDXRj",
        "4ZTzLk9dsmzLFSmT1tcFeLUyfKhuGPpWQPakkY8Hpump"
    ]

    missing_data_stats = {
        'volume_24h': 0,
        'historical_avg_volume': 0,
        'peak_volume': 0,
        'launch_price': 0,
        'peak_price_72h': 0,
        'holder_count': 0,
        'market_cap': 0,
        'ath_before_72h': 0,
        'ath_after_72h': 0,
        'avg_price_post_72h': 0,
        'transaction_count_daily_avg': 0,
        'legitimacy_analysis': 0
    }

    parsing_failure_reasons = Counter()
    ohlcv_stats = {
        'no_ohlcv': 0,
        'minimal_ohlcv': 0,       # <5 points
        'insufficient_ohlcv': 0,  # 5-20 points
        'good_ohlcv': 0           # >20 points
    }

    print("MISSING DATA ANALYSIS")
    print("=" * 60)

    async with EnhancedTokenLabeler() as labeler:
        labeler.debug_mode = True

        for i, mint in enumerate(test_tokens, 1):
            print(f"\nAnalyzing token {i}/{len(test_tokens)}: {mint[:20]}...")

            try:
                metrics = await labeler._gather_metrics(mint)

                # Check missing data patterns
                if not metrics.volume_24h:
                    missing_data_stats['volume_24h'] += 1
                if not metrics.historical_avg_volume:
                    missing_data_stats['historical_avg_volume'] += 1
                if not metrics.peak_volume:
                    missing_data_stats['peak_volume'] += 1
                if not metrics.launch_price:
                    missing_data_stats['launch_price'] += 1
                if not metrics.peak_price_72h:
                    missing_data_stats['peak_price_72h'] += 1
                if not metrics.holder_count:
                    missing_data_stats['holder_count'] += 1
                if not metrics.market_cap:
                    missing_data_stats['market_cap'] += 1
                if not metrics.ath_before_72h:
                    missing_data_stats['ath_before_72h'] += 1
                if not metrics.ath_after_72h:
                    missing_data_stats['ath_after_72h'] += 1
                if not metrics.avg_price_post_72h:
                    missing_data_stats['avg_price_post_72h'] += 1
                if not metrics.transaction_count_daily_avg:
                    missing_data_stats['transaction_count_daily_avg'] += 1
                if not metrics.legitimacy_analysis:
                    missing_data_stats['legitimacy_analysis'] += 1

                # Check OHLCV availability
                if metrics.legitimacy_analysis and 'ohlcv' in str(metrics.legitimacy_analysis):
                    volume_drops = metrics.legitimacy_analysis.get('volume_drop_events', []) if metrics.legitimacy_analysis else []
                    ohlcv_points = len(volume_drops)

                    if ohlcv_points == 0:
                        ohlcv_stats['no_ohlcv'] += 1
                    elif ohlcv_points < 5:
                        ohlcv_stats['minimal_ohlcv'] += 1
                    elif ohlcv_points < 20:
                        ohlcv_stats['insufficient_ohlcv'] += 1
                    else:
                        ohlcv_stats['good_ohlcv'] += 1
                else:
                    ohlcv_stats['no_ohlcv'] += 1

                # Show specific details for this token
                print(f"   Price data: {'[OK]' if metrics.current_price else '[MISSING]'}")
                print(f"   Volume 24h: {'[OK]' if metrics.volume_24h else '[MISSING]'}")
                print(f"   Historical volume: {'[OK]' if metrics.historical_avg_volume else '[MISSING]'}")
                print(f"   Launch price: {'[OK]' if metrics.launch_price else '[MISSING]'}")
                print(f"   Holder count: {'[OK]' if metrics.holder_count else '[MISSING]'}")
                print(f"   Legitimacy analysis: {'[OK]' if metrics.legitimacy_analysis else '[MISSING]'}")

            except Exception as e:
                print(f"   [ERROR] Error analyzing {mint[:20]}: {e}")
                parsing_failure_reasons[str(type(e).__name__)] += 1

    # -------------------------------------------------------------------------
    # Summary Report
    # -------------------------------------------------------------------------

    print("\n\nMISSING DATA SUMMARY")
    print("=" * 60)
    total_tokens = len(test_tokens)

    print(f"Missing data frequency (out of {total_tokens} tokens):")
    for field, count in sorted(missing_data_stats.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_tokens) * 100
        print(f"   {field:25}: {count}/{total_tokens} ({percentage:5.1f}%)")

    print(f"\nOHLCV Data Quality:")
    for category, count in ohlcv_stats.items():
        percentage = (count / total_tokens) * 100
        print(f"   {category:20}: {count}/{total_tokens} ({percentage:5.1f}%)")

    if parsing_failure_reasons:
        print(f"\n[ERROR] Parsing Failure Types:")
        for error_type, count in parsing_failure_reasons.most_common():
            print(f"   {error_type}: {count}")

    # -------------------------------------------------------------------------
    # Fallback Opportunities
    # -------------------------------------------------------------------------

    print(f"\nFALLBACK OPPORTUNITIES IDENTIFIED:")

    critical_missing = [(k, v) for k, v in missing_data_stats.items() if v >= total_tokens * 0.4]

    for field, count in critical_missing:
        percentage = (count / total_tokens) * 100
        print(f"   -> {field} ({percentage:.1f}% missing) - HIGH PRIORITY for fallback")

        if field == 'volume_24h':
            print(f"      Fallback: Calculate from recent transactions (sum last 24h swaps)")
        elif field == 'historical_avg_volume':
            print(f"      Fallback: Average all transaction volumes over token lifetime")
        elif field == 'launch_price':
            print(f"      Fallback: Use first swap price or mint transaction details")
        elif field == 'holder_count':
            print(f"      Fallback: Use Solana RPC getTokenAccountsByMint")
        elif field == 'peak_volume':
            print(f"      Fallback: Max volume from all parsed transactions")
        elif field == 'market_cap':
            print(f"      Fallback: current_price * total_supply (from token metadata)")

    print(f"\nRECOMMENDED IMPLEMENTATION PRIORITY:")
    print(f"   1. Volume calculations (volume_24h, historical_avg_volume, peak_volume)")
    print(f"   2. Launch price detection (first swap or mint analysis)")
    print(f"   3. Holder count via RPC (getTokenAccountsByMint)")
    print(f"   4. Market cap calculation (price * supply)")
    print(f"   5. Enhanced OHLCV aggregation (more transaction parsing)")


if __name__ == "__main__":
    asyncio.run(analyze_missing_data_patterns())
