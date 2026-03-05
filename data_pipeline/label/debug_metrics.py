#!/usr/bin/env python3
"""
Debug Script for Token Metrics Collection.

Provides a step-by-step diagnostic tool for investigating why specific
token metrics show up as N/A or are otherwise incomplete:
- Tests individual data provider steps (price, history, holders).
- Dumps detailed metrics for a single token including all calculated
  ratios and advanced fields.
- Performs low-level transaction parsing analysis to identify swap
  detection failures.
- Logs everything at DEBUG level for full visibility.

Usage:
    python debug_metrics.py [mint_address]

Author: ML-Bullx Team
Date: 2025-08-01
"""

import asyncio
import logging
import sys
from pathlib import Path

from data_pipeline.label.token_labeler import EnhancedTokenLabeler


# =============================================================================
# Logging Setup
# =============================================================================

def setup_logging():
    """Configure detailed DEBUG-level logging to both console and file.

    Output is written to ``debug_metrics.log`` alongside the console
    for real-time observation.
    """
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("debug_metrics.log")
        ]
    )


# =============================================================================
# Transaction Parsing Debug
# =============================================================================

async def debug_transaction_parsing(mint_address: str, data_provider):
    """Analyze the first 20 transactions for a mint to diagnose parsing failures.

    For each transaction the function logs basic filter checks (error
    status, balance presence), mint involvement, and swap parsing
    results.  When parsing fails it inspects the raw balance deltas
    to pinpoint the root cause.

    Args:
        mint_address: SPL token mint address to inspect.
        data_provider: Initialized data provider instance with RPC
            access.
    """
    logger = logging.getLogger(__name__)
    logger.info("DEBUGGING TRANSACTION PARSING:")

    # Get signatures
    signatures = await data_provider._get_signatures_for_address(mint_address, get_all=False, limit=50)
    logger.info(f"Got {len(signatures)} signatures for analysis")

    # Analyze first 20 transactions in detail
    logger.info("Analyzing first 20 transactions in detail...")
    for i, sig in enumerate(signatures[:20]):
        logger.info(f"--- Transaction {i+1}: {sig} ---")

        try:
            tx = await data_provider._get_transaction_details(sig)
            if not tx:
                logger.warning(f"  [ERROR]No transaction data returned")
                continue

            # Check basic filters
            meta = tx.get("meta", {})
            has_error = meta.get("err") is not None
            has_post_balances = bool(meta.get("postTokenBalances"))

            logger.info(f"  Basic checks: error={has_error}, has_post_balances={has_post_balances}")

            if has_error:
                logger.warning(f"  [ERROR]Transaction failed with error: {meta.get('err')}")
                continue

            if not has_post_balances:
                logger.warning(f"  [ERROR]No postTokenBalances")
                continue

            # Check if our mint is involved
            pre_balances = meta.get("preTokenBalances", [])
            post_balances = meta.get("postTokenBalances", [])

            mint_involved = False
            token_change = 0

            for bal in pre_balances + post_balances:
                if bal.get('mint') == mint_address:
                    mint_involved = True
                    break

            logger.info(f"  Mint involved: {mint_involved}")

            if mint_involved:
                # Try to parse swap details
                swap_info = data_provider._parse_swap_details(tx, mint_address)
                if swap_info:
                    logger.info(f"  [OK]Valid swap: price=${swap_info['price']:.8f}, volume=${swap_info['volume_usd']:.2f}")
                else:
                    logger.warning(f"  [ERROR]Could not parse swap details")
                    # Inspect raw balance deltas for root cause
                    try:
                        pre_bal_dict = {bal['mint']: bal['uiTokenAmount']['uiAmount'] for bal in pre_balances if bal.get('uiTokenAmount')}
                        post_bal_dict = {bal['mint']: bal['uiTokenAmount']['uiAmount'] for bal in post_balances if bal.get('uiTokenAmount')}

                        token_change = abs(post_bal_dict.get(mint_address, 0) - pre_bal_dict.get(mint_address, 0))
                        logger.info(f"    Token change: {token_change}")

                        sol_change = 0
                        for j, pre_bal in enumerate(meta.get("preBalances", [])):
                            if j < len(meta.get("postBalances", [])):
                                post_bal = meta.get("postBalances", [])[j]
                                balance_change = abs(post_bal - pre_bal) / 1e9
                                if balance_change > 0.001:  # More than 0.001 SOL
                                    sol_change = balance_change
                                    logger.info(f"    SOL change: {sol_change}")
                                    break

                        if token_change == 0:
                            logger.warning(f"    [ERROR]No token change detected")
                        if sol_change == 0:
                            logger.warning(f"    [ERROR]No significant SOL change detected")

                    except Exception as e:
                        logger.error(f"    [ERROR]Error analyzing swap details: {e}")
            else:
                logger.warning(f"  [ERROR]Our mint not involved in transaction")

        except Exception as e:
            logger.error(f"  [ERROR]Error analyzing transaction: {e}")


# =============================================================================
# Single Token Debug
# =============================================================================

async def debug_single_token(mint_address: str):
    """Run a full diagnostic on a single token's data collection pipeline.

    Walks through each data provider step (current price, historical
    data, holder count, full metrics gathering) and logs intermediate
    results before performing final classification.

    Args:
        mint_address: SPL token mint address to debug.
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 80)
    logger.info(f"DEBUGGING TOKEN: {mint_address}")
    logger.info("=" * 80)

    try:
        async with EnhancedTokenLabeler() as labeler:
            logger.info("[OK] Token labeler initialized successfully")

            # Test data provider connection
            logger.info(f"Testing data provider connection...")
            logger.info(f"   - Data provider: {type(labeler.data_provider).__name__}")
            logger.info(f"   - Has RPC client: {labeler.data_provider.rpc_client is not None}")
            logger.info(f"   - Has DB pool: {labeler.data_provider.db_pool is not None}")
            logger.info(f"   - Has session: {labeler.data_provider.session is not None}")

            # Step 1: Current price data
            logger.info(f"Step 1: Getting current price data...")
            price_data = await labeler.data_provider.get_current_price(mint_address)
            if price_data:
                logger.info(f"   [OK]Price: ${price_data.price:.8f}")
                logger.info(f"   [OK]Volume 24h: ${price_data.volume_24h:,.2f}")
                logger.info(f"   [OK]Market cap: ${price_data.market_cap or 0:,.2f}")
            else:
                logger.warning(f"   [ERROR]No price data found")

            # Step 2: Historical data
            logger.info(f"Step 2: Getting historical data...")
            hist_data = await labeler.data_provider.get_historical_data(mint_address)
            if hist_data:
                logger.info(f"   [OK]OHLCV records: {len(hist_data.ohlcv or [])}")
                logger.info(f"   [OK]Launch price: ${hist_data.launch_price or 0:.8f}")
                logger.info(f"   [OK]Peak 72h: ${hist_data.peak_price_72h or 0:.8f}")
                logger.info(f"   [OK]Post ATH peak: ${hist_data.post_ath_peak_price or 0:.8f}")

                if hist_data.ohlcv and len(hist_data.ohlcv) > 0:
                    logger.info(f"   Sample OHLCV data:")
                    for i, record in enumerate(hist_data.ohlcv[:3]):
                        logger.info(f"      [{i}] ts: {record.get('ts')}, o: {record.get('o'):.8f}, h: {record.get('h'):.8f}, c: {record.get('c'):.8f}")
            else:
                logger.warning(f"   [ERROR]No historical data found")

            # Step 3: Holder count
            logger.info(f"Step 3: Getting holder count...")
            holder_count = await labeler.data_provider.get_holder_count(mint_address)
            if holder_count is not None:
                logger.info(f"   [OK]Holders: {holder_count:,}")
            else:
                logger.warning(f"   [ERROR]No holder count found")

            # Step 4: Full metrics collection
            logger.info(f"Step 4: Full metrics collection...")
            metrics = await labeler._gather_metrics(mint_address)

            logger.info("=" * 50)
            logger.info("FINAL METRICS SUMMARY:")
            logger.info("=" * 50)

            # Basic price metrics
            logger.info(f"PRICE DATA:")
            logger.info(f"   Launch price: {metrics.launch_price}")
            logger.info(f"   Current price: {metrics.current_price}")
            logger.info(f"   Peak 72h: {metrics.peak_price_72h}")
            logger.info(f"   Post ATH peak: {metrics.post_ath_peak_price}")

            # Calculated ratios
            logger.info(f"CALCULATED RATIOS:")
            logger.info(f"   Mega appreciation: {metrics.mega_appreciation}")
            logger.info(f"   Current vs ATH: {metrics.current_vs_ath_ratio}")

            # Community metrics
            logger.info(f"COMMUNITY:")
            logger.info(f"   Holder count: {metrics.holder_count}")
            logger.info(f"   Volume 24h: {metrics.volume_24h}")
            logger.info(f"   Historical avg volume: {metrics.historical_avg_volume}")

            # Advanced metrics
            logger.info(f"ADVANCED:")
            logger.info(f"   ATH before 72h: {metrics.ath_before_72h}")
            logger.info(f"   ATH after 72h: {metrics.ath_after_72h}")
            logger.info(f"   Avg price post 72h: {metrics.avg_price_post_72h}")
            logger.info(f"   Transaction count daily: {metrics.transaction_count_daily_avg}")
            logger.info(f"   Legitimacy analysis: {metrics.legitimacy_analysis is not None}")

            # Transaction-level debug
            logger.info("TRANSACTION PARSING DEBUG:")
            await debug_transaction_parsing(mint_address, labeler.data_provider)

            # Final classification
            logger.info(f"CLASSIFICATION:")
            classification = labeler._classify(metrics)
            logger.info(f"   Result: {classification.upper()}")

            # Detailed reasoning
            logger.info("DETAILED REASONING:")
            labeler._log_classification_reasoning(metrics, classification)

    except Exception as e:
        logger.error(f"[ERROR] Error during debugging: {e}", exc_info=True)


# =============================================================================
# Script Entry Point
# =============================================================================

async def main():
    """Set up logging and launch the single-token debug flow.

    Accepts an optional mint address as the first CLI argument.
    Defaults to a hard-coded test address when none is provided.
    """
    setup_logging()

    # Test with the first token from the input CSV
    test_mint = "X3qPC4HYu3DBSxGYbevftb16RJYNm3c87qV1z3tDXRj"

    if len(sys.argv) > 1:
        test_mint = sys.argv[1]

    print(f"Debugging metrics collection for: {test_mint}")
    await debug_single_token(test_mint)


if __name__ == "__main__":
    asyncio.run(main())
