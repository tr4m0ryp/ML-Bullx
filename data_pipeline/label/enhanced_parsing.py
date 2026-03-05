"""
Enhanced Transaction Parsing for Solana Swap Data.

Provides improved parsing logic for Solana on-chain transactions:
- Multi-criteria swap detection covering Jupiter, Raydium, Orca, and Serum.
- Enhanced price calculation from token balance deltas and SOL changes.
- Fallback parsing for basic token transfers when swap parsing fails.
- Exponential backoff retry wrapper for async RPC calls.
- Debug logging of parsing failures per mint address.
- Rough SOL-to-USD price estimation by historical time period.

Author: ML-Bullx Team
Date: 2025-08-01
"""

import asyncio
import datetime
import logging
import os
import random
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Swap Detection
# =============================================================================

def enhanced_is_swap_transaction(tx: Dict[str, Any]) -> bool:
    """Determine whether a Solana transaction represents a token swap.

    Applies multiple heuristics in order: error check, token balance
    presence, significant SOL balance change, and known DEX program ID
    matching.  Defaults to ``True`` when balance changes exist but no
    known DEX program is matched.

    Args:
        tx: Raw Solana transaction dictionary as returned by the RPC.

    Returns:
        True if the transaction is likely a swap, False otherwise.
    """
    if not tx or not isinstance(tx, dict):
        return False

    meta = tx.get("meta", {})

    # Skip failed transactions
    if meta.get("err"):
        return False

    # Must have token balance changes
    pre_token_balances = meta.get("preTokenBalances", [])
    post_token_balances = meta.get("postTokenBalances", [])

    if not pre_token_balances and not post_token_balances:
        return False

    # Must have some SOL balance changes (indicating payment/fee)
    pre_balances = meta.get("preBalances", [])
    post_balances = meta.get("postBalances", [])

    if len(pre_balances) != len(post_balances):
        return False

    # Check for significant balance changes
    has_significant_change = False
    for i, (pre, post) in enumerate(zip(pre_balances, post_balances)):
        if abs(post - pre) > 100000:  # More than 0.0001 SOL change
            has_significant_change = True
            break

    if not has_significant_change:
        return False

    # Check transaction instructions for known DEX program calls
    transaction = tx.get("transaction", {})
    if transaction:
        instructions = transaction.get("message", {}).get("instructions", [])
        for instruction in instructions:
            program_id = instruction.get("programId", "")
            # Common DEX program IDs
            dex_programs = [
                "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",  # Jupiter V6
                "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  # Raydium AMM
                "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",  # Orca Whirlpools
                "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP",  # Orca Aquafarm
                "DjVE6JNiYqPL2QXyCUUh8rNjHrbz9hXHNYt99MQ59qw1",  # Orca
                "22Y43yTVxuUkoRKdm9thyRhQ3SdgQS7c7kB6UNCiaczD",  # Serum DEX
                "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin",  # Serum DEX V3
            ]
            if program_id in dex_programs:
                return True

    return True  # Default to true if we have balance changes


# =============================================================================
# Swap Detail Parsing
# =============================================================================

def enhanced_parse_swap_details(tx: Dict[str, Any], target_mint: str) -> Optional[Dict[str, Any]]:
    """Parse swap details from a transaction, extracting price and volume.

    Calculates the token amount change and the corresponding SOL change
    to derive price-in-SOL, then converts to USD using a rough historical
    SOL price estimate.  Falls back to ``_parse_basic_token_transfer``
    when the target mint is absent from balance records or an error occurs.

    Args:
        tx: Raw Solana transaction dictionary.
        target_mint: The SPL token mint address to track.

    Returns:
        Dictionary with ``timestamp``, ``price``, ``volume_usd``,
        ``price_in_sol``, ``token_change``, and ``sol_change`` keys,
        or None if parsing fails entirely.
    """
    try:
        meta = tx.get("meta", {})

        # Parse token balance changes
        pre_token_balances = {
            bal['mint']: {
                'amount': bal.get('uiTokenAmount', {}).get('uiAmount', 0) or 0,
                'decimals': bal.get('uiTokenAmount', {}).get('decimals', 0)
            }
            for bal in meta.get("preTokenBalances", [])
            if bal.get('mint') and bal.get('uiTokenAmount')
        }

        post_token_balances = {
            bal['mint']: {
                'amount': bal.get('uiTokenAmount', {}).get('uiAmount', 0) or 0,
                'decimals': bal.get('uiTokenAmount', {}).get('decimals', 0)
            }
            for bal in meta.get("postTokenBalances", [])
            if bal.get('mint') and bal.get('uiTokenAmount')
        }

        # Check if target mint is involved
        if target_mint not in pre_token_balances and target_mint not in post_token_balances:
            # Fallback: try to parse as basic token transfer
            return _parse_basic_token_transfer(tx, target_mint)

        # Calculate token change for target mint
        pre_amount = pre_token_balances.get(target_mint, {}).get('amount', 0) or 0
        post_amount = post_token_balances.get(target_mint, {}).get('amount', 0) or 0
        token_change = abs(post_amount - pre_amount)

        if token_change == 0:
            return None

        # Calculate SOL changes (more sophisticated approach)
        pre_balances = meta.get("preBalances", [])
        post_balances = meta.get("postBalances", [])

        sol_changes = []
        for i, (pre_bal, post_bal) in enumerate(zip(pre_balances, post_balances)):
            change = abs(post_bal - pre_bal) / 1e9  # Convert lamports to SOL
            if change > 0.0001:  # Ignore dust/fees
                sol_changes.append(change)

        # Use the largest SOL change (likely the swap amount)
        if not sol_changes:
            return None

        sol_change = max(sol_changes)

        # Calculate price
        price_in_sol = sol_change / token_change if token_change > 0 else 0

        # Estimate SOL price based on transaction time
        timestamp = tx.get("blockTime", 0)
        sol_price_usd = estimate_sol_price_usd(timestamp)

        price_usd = price_in_sol * sol_price_usd
        volume_usd = sol_change * sol_price_usd

        return {
            "timestamp": timestamp,
            "price": price_usd,
            "volume_usd": volume_usd,
            "price_in_sol": price_in_sol,
            "token_change": token_change,
            "sol_change": sol_change
        }

    except Exception as e:
        logger.debug(f"Error parsing swap details: {e}")
        # Final fallback: try basic transfer parsing
        return _parse_basic_token_transfer(tx, target_mint)


# =============================================================================
# Fallback Token Transfer Parsing
# =============================================================================

def _parse_basic_token_transfer(tx: Dict[str, Any], target_mint: str) -> Optional[Dict[str, Any]]:
    """Attempt to extract price estimates from a basic token transfer.

    This is a last-resort heuristic used when full swap parsing fails.
    It scans transaction log messages for references to the target mint
    combined with transfer or mint keywords.

    Args:
        tx: Raw Solana transaction dictionary.
        target_mint: The SPL token mint address to look for in logs.

    Returns:
        Dictionary with default price/volume estimates and a
        ``parsing_method`` of ``"fallback_transfer"``, or None if
        the target mint is not found in any log message.
    """
    try:
        meta = tx.get("meta", {})

        # Look for token transfers in logs or instructions
        log_messages = meta.get("logMessages", [])
        for log in log_messages:
            if target_mint in log and ("transfer" in log.lower() or "mint" in log.lower()):
                # This is a basic heuristic - could be improved
                timestamp = tx.get("blockTime", 0)
                return {
                    "timestamp": timestamp,
                    "price": 0.001,  # Default estimate for failed parsing
                    "volume_usd": 100.0,  # Default volume estimate
                    "price_in_sol": 0.00001,
                    "token_change": 1000.0,
                    "sol_change": 0.01,
                    "parsing_method": "fallback_transfer"
                }

        return None

    except Exception as e:
        logger.debug(f"Fallback transfer parsing failed: {e}")
        return None


# =============================================================================
# Retry Logic
# =============================================================================

async def retry_with_exponential_backoff(func, max_retries=3, base_delay=1.0, max_delay=60.0):
    """Retry an async callable with exponential backoff and jitter.

    Args:
        func: Async callable (zero-argument) to invoke.
        max_retries: Maximum number of attempts before re-raising.
        base_delay: Initial delay in seconds before the first retry.
        max_delay: Upper bound on the computed delay.

    Returns:
        The return value of ``func`` on success.

    Raises:
        Exception: Re-raises the last exception after all retries
            are exhausted.
    """
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise e

            # Calculate delay with exponential backoff and jitter
            delay = min(base_delay * (2 ** attempt), max_delay)
            jitter = random.uniform(0.0, delay * 0.1)
            total_delay = delay + jitter

            logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {total_delay:.2f}s")
            await asyncio.sleep(total_delay)

    return None


# =============================================================================
# Debug Logging
# =============================================================================

def log_parsing_failure(mint: str, tx_signature: str, error: str):
    """Persist a parsing failure record to a per-mint debug log file.

    Creates a ``debug_failures/`` directory if it does not exist and
    appends a CSV-style line containing the current timestamp, the
    transaction signature, and the error description.  At most 10
    failure entries are retained per mint to avoid unbounded growth.

    Args:
        mint: Token mint address used as the log file name.
        tx_signature: Solana transaction signature that failed parsing.
        error: Short description of the failure reason.
    """
    try:
        debug_dir = "debug_failures"
        os.makedirs(debug_dir, exist_ok=True)

        debug_file = os.path.join(debug_dir, f"{mint}.log")

        # Only keep first 10 failures per mint
        if os.path.exists(debug_file):
            with open(debug_file, 'r') as f:
                lines = f.readlines()
            if len(lines) >= 10:
                return  # Skip if already have 10 failures

        with open(debug_file, 'a') as f:
            f.write(f"{time.time()},{tx_signature},{error}\n")

    except Exception as e:
        logger.debug(f"Failed to log parsing failure: {e}")


# =============================================================================
# SOL Price Estimation
# =============================================================================

def estimate_sol_price_usd(timestamp: int) -> float:
    """Return a rough SOL/USD price estimate based on a Unix timestamp.

    Uses hard-coded monthly averages for 2024.  In production this
    should be replaced with an actual historical price feed.

    Args:
        timestamp: Unix epoch seconds of the transaction.

    Returns:
        Estimated SOL price in USD.
    """
    if timestamp == 0:
        return 100.0  # Default fallback

    # Rough SOL price estimates by time period
    # January 2024: ~$100
    # February 2024: ~$110
    # March 2024: ~$200
    # April-May 2024: ~$140
    # June-July 2024: ~$130
    # August 2024: ~$150

    dt = datetime.datetime.fromtimestamp(timestamp)

    if dt.year < 2024:
        return 50.0
    elif dt.year == 2024:
        if dt.month <= 1:
            return 100.0
        elif dt.month == 2:
            return 110.0
        elif dt.month == 3:
            return 200.0
        elif dt.month in [4, 5]:
            return 140.0
        elif dt.month in [6, 7]:
            return 130.0
        else:
            return 150.0
    else:
        return 150.0  # 2025+


# =============================================================================
# Token Mint Extraction
# =============================================================================

def get_all_token_mints_from_transaction(tx: Dict[str, Any]) -> List[str]:
    """Extract all unique token mint addresses involved in a transaction.

    Scans both ``preTokenBalances`` and ``postTokenBalances`` from the
    transaction metadata.

    Args:
        tx: Raw Solana transaction dictionary.

    Returns:
        List of unique mint address strings found in the transaction.
    """
    mints = set()

    meta = tx.get("meta", {})

    for bal in meta.get("preTokenBalances", []):
        if bal.get('mint'):
            mints.add(bal['mint'])

    for bal in meta.get("postTokenBalances", []):
        if bal.get('mint'):
            mints.add(bal['mint'])

    return list(mints)
