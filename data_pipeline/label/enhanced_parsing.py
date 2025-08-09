"""
Enhanced transaction parsing functions to improve data collection.
This file contains improved logic for parsing Solana transactions to extract swap data.
"""

from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

def enhanced_is_swap_transaction(tx: Dict[str, Any]) -> bool:
    """
    Enhanced swap transaction detection with multiple criteria.
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

def enhanced_parse_swap_details(tx: Dict[str, Any], target_mint: str) -> Optional[Dict[str, Any]]:
    """
    Enhanced swap detail parsing with better price calculation.
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
            return None
        
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
        return None

def estimate_sol_price_usd(timestamp: int) -> float:
    """
    Estimate SOL price in USD based on timestamp.
    This is a rough estimate - in production, you'd want to use actual price data.
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
    
    import datetime
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

def get_all_token_mints_from_transaction(tx: Dict[str, Any]) -> List[str]:
    """
    Extract all token mints involved in a transaction.
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
