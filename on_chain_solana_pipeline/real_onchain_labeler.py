#!/usr/bin/env python3
"""
Real On-Chain Token Labeler - Uses actual Helius API calls
"""
from __future__ import annotations

import asyncio
import aiohttp
import logging
import os
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the current directory to the path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from api_key_manager import get_key_manager

# ───────────────────────── Logging ──────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("real_onchain_labeling.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ──────────────────────── Constants ─────────────────────────
ONE_HOUR = 60 * 60
THREE_DAYS_SEC = 3 * 24 * 60 * 60
SUSTAIN_DAYS_SEC = 7 * 24 * 60 * 60
HELIUS_BASE_URL = "https://rpc.helius.xyz"

# ─────────────────── Dataclass per token ────────────────────
@dataclass
class TokenMetrics:
    mint_address: str
    current_price: Optional[float] = None
    volume_24h: Optional[float] = None
    market_cap: Optional[float] = None
    peak_price_72h: Optional[float] = None
    post_ath_peak_price: Optional[float] = None
    has_sustained_drop: bool = False
    price_drops: List[Tuple[datetime, float]] = None
    holder_count: Optional[int] = None
    transaction_count: int = 0  # Track number of swap transactions
    
    # Enhanced metrics for sophisticated classification
    early_phase_drops: List[Tuple[datetime, float, float]] = None  # (time, drop_pct, recovery_ratio)
    late_phase_drops: List[Tuple[datetime, float, float]] = None   # (time, drop_pct, recovery_ratio)
    max_recovery_after_drop: Optional[float] = None  # Best recovery ratio after any major drop
    rapid_drops_count: int = 0  # Number of rapid (< 2h) major drops
    days_since_last_major_drop: Optional[int] = None
    has_shown_recovery: bool = False  # Has recovered significantly after any major drop
    current_trend: Optional[str] = None  # "recovering", "declining", "stable"
    
    # Mega-success metrics for tokens with massive appreciation
    mega_appreciation: Optional[float] = None  # Total appreciation from launch to ATH
    current_vs_ath_ratio: Optional[float] = None  # Current price as % of ATH
    total_major_drops: int = 0  # Total count of major drops
    final_evaluation_score: Optional[float] = None  # Overall success score

    def __post_init__(self):
        if self.price_drops is None:
            self.price_drops = []
        if self.early_phase_drops is None:
            self.early_phase_drops = []
        if self.late_phase_drops is None:
            self.late_phase_drops = []

# ─────────────────────── Real OnChain Data Provider ───────────────────────
class RealOnChainProvider:
    """Real implementation that makes actual Helius API calls"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.key_manager = get_key_manager()
        # Rate limiting and circuit breaker controls
        self.rate_limit_semaphore = asyncio.Semaphore(2)  # Max 2 concurrent API calls
        self.circuit_breaker_failures = 0
        self.circuit_breaker_threshold = 15  # Stop after 15 consecutive failures
        self.circuit_breaker_reset_time = 300  # Reset after 5 minutes
        self.last_circuit_break = 0
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15, connect=5)  # Reduced timeout
        )
        return self
        
    async def __aexit__(self, *exc):
        if self.session:
            await self.session.close()
    
    async def _make_helius_request(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Make a request to Helius with automatic key rotation and better error handling."""
        # Check circuit breaker
        current_time = time.time()
        if (self.circuit_breaker_failures >= self.circuit_breaker_threshold and 
            current_time - self.last_circuit_break < self.circuit_breaker_reset_time):
            logger.warning(f"Circuit breaker active ({self.circuit_breaker_failures} failures), skipping API call")
            return None
        
        # Reset circuit breaker if enough time has passed
        if current_time - self.last_circuit_break >= self.circuit_breaker_reset_time:
            if self.circuit_breaker_failures > 0:
                logger.info("Circuit breaker reset - resuming API calls")
                self.circuit_breaker_failures = 0
        
        # Use semaphore to limit concurrent requests
        async with self.rate_limit_semaphore:
            max_retries = 2  # Reduced from 3 to 2
            
            for attempt in range(max_retries):
                # First try to get an immediately available key
                api_key = self.key_manager.get_next_available_key()
                
                # If no key is available, wait for one to become available
                if not api_key:
                    logger.warning("No Helius API keys immediately available, waiting...")
                    api_key = await self.key_manager.wait_for_available_key(max_wait_time=30)  # Reduced from 60
                    if not api_key:
                        logger.error("No Helius API keys available after waiting")
                        self.circuit_breaker_failures += 1
                        self.last_circuit_break = current_time
                        return None
                
                url = f"{HELIUS_BASE_URL}/?api-key={api_key}"
                
                try:
                    logger.debug(f"Making Helius request (attempt {attempt + 1}/{max_retries})")
                    async with self.session.post(url, json=payload) as response:
                        if response.status == 200:
                            self.key_manager.record_request_success(api_key)
                            # Reset circuit breaker on success
                            self.circuit_breaker_failures = 0
                            result = await response.json()
                            return result
                        elif response.status == 429:
                            logger.warning(f"Rate limited on key {api_key[:8]}... (attempt {attempt + 1})")
                            self.key_manager.record_request_failure(api_key, is_rate_limit=True)
                            self.circuit_breaker_failures += 1
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        else:
                            error_text = await response.text()
                            logger.warning(f"Helius API error {response.status}: {error_text[:200]}")
                            self.key_manager.record_request_failure(api_key, is_rate_limit=False)
                            self.circuit_breaker_failures += 1
                            if attempt < max_retries - 1:
                                await asyncio.sleep(1)
                                continue
                            self.last_circuit_break = current_time
                            return None
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout on Helius request (attempt {attempt + 1})")
                    self.key_manager.record_request_failure(api_key, is_rate_limit=False)
                    self.circuit_breaker_failures += 1
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    self.last_circuit_break = current_time
                    return None
                except Exception as e:
                    logger.error(f"Error making Helius request: {e}")
                    self.key_manager.record_request_failure(api_key, is_rate_limit=False)
                    self.circuit_breaker_failures += 1
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        continue
                    self.last_circuit_break = current_time
                    return None
            
            logger.error(f"Failed to make Helius request after {max_retries} attempts")
            self.last_circuit_break = current_time
            return None
    
    async def get_token_accounts(self, mint: str) -> Optional[int]:
        """Get token account count (holder count proxy)"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccounts",
            "params": [
                {
                    "mint": mint,
                    "limit": 1000  # Get sample to estimate total
                }
            ]
        }
        
        result = await self._make_helius_request(payload)
        if result and "result" in result:
            # Return rough estimate - in production you'd paginate through all
            token_accounts = result["result"].get("token_accounts", [])
            return len(token_accounts)
        return None
    
    async def get_signatures_for_address(self, mint: str, limit: int = 1000, get_all: bool = True) -> List[str]:
        """Get transaction signatures for a token with optional pagination to get ALL transactions"""
        all_signatures = []
        
        if not get_all:
            # Single request for backwards compatibility
            return await self._get_signatures_batch(mint, limit)
        
        # Get all signatures using pagination
        before = None
        total_fetched = 0
        max_total = 10000  # Safety limit to prevent infinite loops
        consecutive_failures = 0
        max_consecutive_failures = 5  # Max failed API calls before giving up
        
        logger.info(f"Starting paginated signature collection for {mint}")
        
        while total_fetched < max_total and consecutive_failures < max_consecutive_failures:
            # Build request parameters
            params = [
                mint, 
                {
                    "limit": min(limit, 1000),  # Respect API limit
                    "commitment": "finalized",
                    "searchTransactionHistory": True
                }
            ]
            
            # Add 'before' parameter for pagination
            if before:
                params[1]["before"] = before
            
            payload = {
                "jsonrpc": "2.0",
                "id": 1, 
                "method": "getSignaturesForAddress",
                "params": params
            }
            
            logger.info(f"Fetching batch for {mint}, before={before}, fetched so far: {total_fetched}")
            result = await self._make_helius_request(payload)
            
            if not result or "result" not in result or not result["result"]:
                logger.warning(f"Failed to fetch signatures for {mint} (API call failed or no results)")
                # If API call failed, wait longer before retrying
                if not result:
                    consecutive_failures += 1
                    logger.warning(f"API call failed for {mint} (failure {consecutive_failures}/{max_consecutive_failures})")
                    if consecutive_failures >= max_consecutive_failures:
                        logger.error(f"Too many consecutive API failures for {mint}, giving up")
                        break
                    logger.info("API call failed, waiting 15 seconds before retrying...")
                    await asyncio.sleep(15)
                    continue
                else:
                    logger.info(f"No more signatures found for {mint}, stopping pagination")
                    break
            
            # Reset failure counter on successful API call
            consecutive_failures = 0
            
            batch_signatures = []
            for sig_info in result["result"]:
                batch_signatures.append(sig_info["signature"])
            
            if not batch_signatures:
                logger.info(f"Empty batch returned for {mint}, stopping pagination")
                break
            
            all_signatures.extend(batch_signatures)
            total_fetched += len(batch_signatures)
            
            # Update 'before' for next batch (use last signature from this batch)
            before = batch_signatures[-1]
            
            logger.info(f"Fetched {len(batch_signatures)} signatures for {mint}, total: {total_fetched}")
            
            # If we got fewer than the limit, we've reached the end
            if len(batch_signatures) < min(limit, 1000):
                logger.info(f"Reached end of signatures for {mint} (got {len(batch_signatures)} < {min(limit, 1000)})")
                break
            
            # Longer delay to respect rate limits and prevent cascade failures
            await asyncio.sleep(1.0)  # Increased from 0.2 to 1.0 seconds
        
        logger.info(f"Total signatures collected for {mint}: {len(all_signatures)}")
        return all_signatures

    async def _get_signatures_batch(self, mint: str, limit: int) -> List[str]:
        """Get a single batch of signatures (legacy method)"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1, 
            "method": "getSignaturesForAddress",
            "params": [
                mint, 
                {
                    "limit": min(limit, 1000),
                    "commitment": "finalized",
                    "searchTransactionHistory": True
                }
            ]
        }
        
        result = await self._make_helius_request(payload)
        
        if result and "result" in result:
            signatures = []
            for sig_info in result["result"]:
                signatures.append(sig_info["signature"])
            return signatures
        
        return []
    
    async def get_transaction(self, signature: str) -> Optional[Dict[str, Any]]:
        """Get transaction details with full search capabilities"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction", 
            "params": [
                signature,
                {
                    "encoding": "json",
                    "maxSupportedTransactionVersion": 0,
                    "commitment": "finalized",  # Use finalized commitment
                    "searchTransactionHistory": True  # Search full transaction history
                }
            ]
        }
        
        result = await self._make_helius_request(payload)
        if result and "result" in result:
            return result["result"]
        return None
    
    async def analyze_token_activity(self, mint: str) -> Dict[str, Any]:
        """Analyze token transaction activity for pricing data"""
        try:
            # Get ALL transaction signatures using pagination
            signatures = await self.get_signatures_for_address(mint, get_all=True)
            if not signatures:
                logger.info(f"No signatures found for {mint}")
                return {}
            
            logger.info(f"Found {len(signatures)} signatures for {mint}")
            
            # Smart sampling: analyze fewer transactions to avoid rate limits
            # Focus on key time periods for comprehensive but efficient analysis
            max_to_analyze = min(len(signatures), 20)  # Reduced from 50 to 20 to minimize API calls
            
            if len(signatures) <= max_to_analyze:
                # Analyze all if we have few signatures
                signatures_to_analyze = signatures
            else:
                # Sample strategically: more from early period, some recent
                early_count = min(20, len(signatures) // 4)  # First 25% or 20, whichever is smaller
                recent_count = min(10, len(signatures) // 10)  # Last 10% or 10, whichever is smaller
                middle_count = max_to_analyze - early_count - recent_count
                
                # Calculate step for middle sampling
                middle_start = early_count
                middle_end = len(signatures) - recent_count
                step = max(1, (middle_end - middle_start) // middle_count) if middle_count > 0 else 1
                
                signatures_to_analyze = (
                    list(signatures[:early_count]) +  # Early transactions
                    list(signatures[middle_start:middle_end:step][:middle_count]) +  # Middle sampling
                    list(signatures[-recent_count:])  # Recent transactions
                )
                
                # Remove duplicates while preserving order
                seen = set()
                signatures_to_analyze = [x for x in signatures_to_analyze if not (x in seen or seen.add(x))]
            
            logger.info(f"Analyzing {len(signatures_to_analyze)} sampled transactions from {len(signatures)} total for {mint}")
            
            # Analyze transactions for swap data with very conservative rate limiting
            swap_data = []
            batch_size = 1  # Process one transaction at a time to minimize rate limit issues
            
            for i in range(0, len(signatures_to_analyze), batch_size):
                # Check circuit breaker before processing each batch
                if (self.circuit_breaker_failures >= self.circuit_breaker_threshold):
                    logger.warning(f"Circuit breaker active - stopping transaction analysis for {mint}")
                    break
                    
                batch = signatures_to_analyze[i:i + batch_size]
                logger.info(f"Processing transaction batch {i//batch_size + 1}/{(len(signatures_to_analyze) + batch_size - 1)//batch_size} for {mint}")
                
                for j, sig in enumerate(batch):
                    try:
                        tx = await self.get_transaction(sig)
                        if tx and tx.get("meta") and not tx["meta"].get("err"):
                            # Look for swap-like activity in transaction
                            if self._looks_like_swap(tx):
                                swap_info = self._extract_swap_info(tx, mint)
                                if swap_info:
                                    swap_data.append(swap_info)
                        
                        # Increased delay to be very conservative with rate limits
                        await asyncio.sleep(1.0)  # 1 second between each transaction request
                        
                    except Exception as e:
                        logger.warning(f"Error analyzing transaction {sig}: {e}")
                        # On error, wait longer to avoid compounding rate limit issues
                        await asyncio.sleep(2.0)  # Increased to 2 seconds on error
                        continue
                
                # Longer pause between batches to respect rate limits
                if i + batch_size < len(signatures_to_analyze):
                    logger.info(f"Pausing 5 seconds between batches to respect rate limits...")
                    await asyncio.sleep(5.0)  # Increased from 3 to 5 seconds
            
            if swap_data:
                logger.info(f"Found {len(swap_data)} swap transactions for {mint}")
                return self._calculate_metrics_from_swaps(swap_data)
            else:
                logger.info(f"No swap data found for {mint}")
                return {}
                
        except Exception as e:
            logger.error(f"Error analyzing token activity for {mint}: {e}")
            return {}
    
    def _looks_like_swap(self, tx: Dict[str, Any]) -> bool:
        """Check if transaction looks like a swap"""
        # Simple heuristic - look for token balance changes
        if not tx.get("meta") or not tx["meta"].get("postTokenBalances"):
            return False
        
        pre_balances = tx["meta"].get("preTokenBalances", [])
        post_balances = tx["meta"].get("postTokenBalances", [])
        
        # If token balances changed, likely a swap
        return len(pre_balances) != len(post_balances) or \
               any(pre.get("uiTokenAmount", {}).get("uiAmount") != post.get("uiTokenAmount", {}).get("uiAmount") 
                   for pre, post in zip(pre_balances, post_balances))
    
    def _extract_swap_info(self, tx: Dict[str, Any], mint: str) -> Optional[Dict[str, Any]]:
        """Extract swap information with price calculation from transaction"""
        try:
            slot = tx.get("slot", 0)
            timestamp = tx.get("blockTime", 0)
            
            # Look for SOL and token balance changes to calculate price
            pre_balances = tx["meta"].get("preTokenBalances", [])
            post_balances = tx["meta"].get("postTokenBalances", [])
            
            # Also check SOL balance changes (lamport changes)
            pre_sol_balances = tx["meta"].get("preBalances", [])
            post_sol_balances = tx["meta"].get("postBalances", [])
            
            # Find token amount changes
            token_change = 0
            sol_change = 0
            
            # Calculate token balance change
            for pre, post in zip(pre_balances, post_balances):
                if pre.get("mint") == mint and post.get("mint") == mint:
                    pre_amount = pre.get("uiTokenAmount", {}).get("uiAmount", 0) or 0
                    post_amount = post.get("uiTokenAmount", {}).get("uiAmount", 0) or 0
                    token_change = abs(post_amount - pre_amount)
                    break
            
            # Calculate SOL balance change (convert lamports to SOL)
            if pre_sol_balances and post_sol_balances:
                for i, (pre_sol, post_sol) in enumerate(zip(pre_sol_balances, post_sol_balances)):
                    sol_delta = abs(post_sol - pre_sol) / 1e9  # Convert lamports to SOL
                    if sol_delta > 0.001:  # Minimum meaningful SOL change
                        sol_change = sol_delta
                        break
            
            # Calculate price if we have both token and SOL changes
            if token_change > 0 and sol_change > 0:
                # Price = SOL spent / tokens received (or vice versa)
                price = sol_change / token_change
                
                return {
                    "slot": slot,
                    "timestamp": timestamp,
                    "amount": float(token_change),
                    "price": float(price),
                    "volume_usd": float(sol_change * 150),  # Rough SOL price estimate
                    "signature": tx.get("transaction", {}).get("signatures", [""])[0]
                }
            
            # Fallback: basic token amount tracking without price
            for balance in post_balances:
                if balance.get("mint") == mint:
                    amount = balance.get("uiTokenAmount", {}).get("uiAmount", 0)
                    if amount and amount > 0:
                        return {
                            "slot": slot,
                            "timestamp": timestamp,
                            "amount": float(amount),
                            "price": 0.001,  # Fallback price estimate
                            "volume_usd": 0,
                            "signature": tx.get("transaction", {}).get("signatures", [""])[0]
                        }
            
            return None
        except Exception as e:
            logger.warning(f"Error extracting swap info: {e}")
            return None
    
    def _calculate_metrics_from_swaps(self, swap_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate basic metrics from swap data"""
        if not swap_data:
            return {}
        
        # Sort by timestamp
        swap_data.sort(key=lambda x: x.get("timestamp", 0))
        
        # Calculate basic stats
        amounts = [s["amount"] for s in swap_data if s.get("amount")]
        if not amounts:
            return {}
        
        recent_amount = amounts[-1] if amounts else 0
        total_volume = sum(amounts)
        
        return {
            "estimated_price": recent_amount * 0.001,  # Rough estimate
            "volume_24h": total_volume * 0.001,  # Rough estimate
            "transaction_count": len(swap_data),
            "latest_activity": swap_data[-1]["timestamp"] if swap_data else 0
        }

# ─────────────────────── Real OnChain Token Labeler ───────────────────────
class RealOnChainTokenLabeler:
    # Much more conservative rugpull detection
    RUG_THRESHOLD = 0.85  # Raised from 70% to 85%
    RUG_MIN_DROPS_FOR_PATTERN = 5  # Need at least 5 major drops to indicate pattern
    RUG_RAPID_DROP_HOURS = 2  # Coordinated dumps happen within 2 hours
    RUG_NO_RECOVERY_DAYS = 14  # Must wait 14 days without recovery
    RUG_FINAL_PRICE_RATIO = 0.01  # Final price must be <1% of ATH for rugpull
    
    # Success criteria with mega-success detection
    SUCCESS_APPRECIATION = 10.0
    SUCCESS_MIN_HOLDERS = 100
    SUCCESS_RECOVERY_MULTIPLIER = 5.0  # Must recover to 5x the drop low
    SUCCESS_MEGA_APPRECIATION = 1000.0  # 1000x+ is mega-success
    SUCCESS_SUSTAINED_HIGH_RATIO = 0.1  # Must maintain 10%+ of ATH
    
    # Activity thresholds
    MIN_ACTIVITY_TRANSACTIONS = 15
    INACTIVE_VOLUME_THRESHOLD = 1000
    INACTIVE_HOLDER_THRESHOLD = 10
    
    # Analysis parameters
    EARLY_PHASE_DAYS = 14  # Extended early phase to 14 days
    RECOVERY_ANALYSIS_DAYS = 60  # Look for recovery within 60 days
    MAX_TRANSACTIONS = 2000  # Increased from 1000 to capture more history

    def __init__(self):
        self.provider: Optional[RealOnChainProvider] = None

    async def __aenter__(self):
        self.provider = RealOnChainProvider()
        await self.provider.__aenter__()
        return self

    async def __aexit__(self, *exc):
        if self.provider:
            await self.provider.__aexit__(*exc)

    async def label_tokens_from_csv(self, inp: str, out: str, batch: int = 10) -> pd.DataFrame:
        df = pd.read_csv(inp)
        if "mint_address" not in df.columns:
            raise ValueError("CSV must contain 'mint_address' column")
        mints = df["mint_address"].tolist()

        results: List[Tuple[str, str]] = []
        for i in range(0, len(mints), batch):
            chunk = mints[i:i + batch]
            logger.info("Batch %d/%d (size=%d)", i // batch + 1, (len(mints) + batch - 1) // batch, len(chunk))
            
            # Process tokens one by one to avoid rate limits
            for mint in chunk:
                result = await self._process(mint)
                if result:
                    results.append(result)
                
                # Rate limiting between tokens
                await asyncio.sleep(2)  # 2 second delay to respect rate limits
            
            logger.info(f"Completed batch {i // batch + 1}, processed {len(results)} tokens so far")

        out_df = pd.DataFrame(results, columns=["mint_address", "label"])
        out_df.to_csv(out, index=False)
        logger.info("Saved %d labeled tokens → %s", len(out_df), out)
        return out_df

    async def _process(self, mint: str) -> Optional[Tuple[str, str]]:
        """Process a single token with comprehensive error handling."""
        try:
            logger.info(f"Processing token: {mint}")
            
            # Gather all metrics with timeout
            m = await asyncio.wait_for(self._gather_metrics(mint), timeout=60)
            
            if not self._has_any_data(m):
                logger.info(f"{mint} – skipped (no on-chain data)")
                return mint, "inactive"
            
            # Classify the token
            label = self._classify(m)
            logger.info(f"{mint} classified as: {label}")
            
            return mint, label
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout processing token {mint}")
            return mint, "inactive"
        except Exception as e:
            logger.error(f"Error processing token {mint}: {e}")
            return mint, "inactive"

    @staticmethod
    def _has_any_data(m: TokenMetrics) -> bool:
        return (m.current_price is not None or 
                m.holder_count is not None or 
                m.transaction_count > 0)

    async def _gather_metrics(self, mint: str) -> TokenMetrics:
        """Gather comprehensive metrics for proper token classification"""
        t = TokenMetrics(mint)

        try:
            # 1. Get holder count from token accounts (actual number of holders)
            holder_count = await self.provider.get_token_accounts(mint)
            if holder_count:
                t.holder_count = holder_count
                logger.info(f"{mint}: Found {holder_count} token accounts")

            # 2. Get comprehensive transaction history for price analysis
            # Get ALL transaction signatures using pagination
            signatures = await self.provider.get_signatures_for_address(mint, get_all=True)
            logger.info(f"Found {len(signatures)} signatures for {mint}")
            
            if signatures:
                # Get detailed transaction data for comprehensive analysis
                all_swaps = []
                price_history = []
                
                # Process more transactions for better historical data
                batch_size = 20
                max_transactions = min(len(signatures), 500)  # Increased for better data
                
                for i in range(0, max_transactions, batch_size):
                    batch_signatures = signatures[i:i + batch_size]
                    
                    # Get transactions in parallel
                    tasks = [self.provider.get_transaction(sig) for sig in batch_signatures]
                    transactions = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for tx in transactions:
                        if isinstance(tx, dict) and tx:
                            if self.provider._looks_like_swap(tx):
                                swap_info = self.provider._extract_swap_info(tx, mint)
                                if swap_info:
                                    all_swaps.append(swap_info)
                                    
                                    # Build price history for temporal analysis
                                    if 'timestamp' in swap_info and 'price' in swap_info:
                                        price_history.append({
                                            'timestamp': swap_info['timestamp'],
                                            'price': swap_info['price'],
                                            'volume': swap_info.get('volume_usd', 0)
                                        })
                    
                    # Rate limiting between batches
                    await asyncio.sleep(0.3)
                
                logger.info(f"Found {len(all_swaps)} swap transactions for {mint}")
                
                # Set transaction count for inactive detection
                t.transaction_count = len(all_swaps)
                
                if all_swaps and price_history:
                    # 3. Calculate current price from recent swaps
                    recent_swaps = sorted(all_swaps, key=lambda x: x.get('timestamp', 0), reverse=True)[:10]
                    if recent_swaps:
                        prices = [swap.get('price', 0) for swap in recent_swaps if swap.get('price')]
                        volumes = [swap.get('volume_usd', 0) for swap in recent_swaps]
                        
                        if prices:
                            t.current_price = sum(prices) / len(prices)
                            t.volume_24h = sum(volumes)
                    
                    # 4. CRITICAL: Analyze price history with enhanced pattern detection
                    historical_analysis = await self._analyze_comprehensive_price_history(price_history, mint)
                    if historical_analysis:
                        # Basic metrics
                        t.peak_price_72h = historical_analysis.get('peak_price_72h')
                        t.post_ath_peak_price = historical_analysis.get('post_ath_peak_price')
                        t.has_sustained_drop = historical_analysis.get('has_sustained_drop', False)
                        t.price_drops = historical_analysis.get('price_drops', [])
                        
                        # Enhanced pattern metrics
                        t.early_phase_drops = historical_analysis.get('early_phase_drops', [])
                        t.late_phase_drops = historical_analysis.get('late_phase_drops', [])
                        t.max_recovery_after_drop = historical_analysis.get('max_recovery_after_drop', 0.0)
                        t.rapid_drops_count = historical_analysis.get('rapid_drops_count', 0)
                        t.days_since_last_major_drop = historical_analysis.get('days_since_last_major_drop')
                        t.has_shown_recovery = historical_analysis.get('has_shown_recovery', False)
                        t.current_trend = historical_analysis.get('current_trend', 'stable')
                        
                        # Update current price from analysis if available
                        if historical_analysis.get('current_price'):
                            t.current_price = historical_analysis.get('current_price')
                    
                    logger.info(f"{mint}: Price ~${t.current_price}, Volume ~${t.volume_24h}")
                    if t.peak_price_72h and t.post_ath_peak_price:
                        appreciation = (t.post_ath_peak_price / t.peak_price_72h) if t.peak_price_72h > 0 else 0
                        logger.info(f"{mint}: 72h Peak ~${t.peak_price_72h:.6f}, Post-ATH Peak ~${t.post_ath_peak_price:.6f} ({appreciation:.1f}x appreciation)")
                    
                    if t.price_drops:
                        max_drop = max(drop[1] for drop in t.price_drops) if t.price_drops else 0
                        logger.info(f"{mint}: Max price drop detected: {max_drop:.1%}")
            
        except Exception as e:
            logger.warning("Error gathering comprehensive metrics for %s: %s", mint, e)

        return t

    async def _analyze_comprehensive_price_history(self, price_history: List[Dict], mint: str) -> Dict[str, Any]:
        """Enhanced comprehensive analysis with sophisticated pattern detection"""
        if not price_history or len(price_history) < 2:
            return {}
        
        try:
            # Sort by timestamp
            sorted_history = sorted(price_history, key=lambda x: x['timestamp'])
            
            # Convert to DataFrame for analysis
            df = pd.DataFrame(sorted_history)
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
            
            # Find token launch time and key periods
            launch_time = df['datetime'].min()
            current_time = df['datetime'].max()
            early_phase_end = launch_time + timedelta(days=self.EARLY_PHASE_DAYS)
            hours_72_cutoff = launch_time + timedelta(hours=72)
            
            # Get price data for first 72 hours
            early_df = df[df['datetime'] <= hours_72_cutoff]
            if early_df.empty:
                early_df = df.head(min(10, len(df)))
            
            # Get post-72h data
            post_df = df[df['datetime'] > hours_72_cutoff]
            
            # Calculate key price points
            peak_price_72h = early_df['price'].max() if not early_df.empty else 0
            post_ath_peak_price = post_df['price'].max() if not post_df.empty else 0
            current_price = df['price'].iloc[-1] if not df.empty else 0
            
            # Enhanced drop analysis with pattern recognition
            has_sustained_drop = False
            price_drops = []
            early_drops = []
            late_drops = []
            rapid_drops_count = 0
            max_recovery = 0.0
            has_recovery = False
            
            # Analyze drops with rolling window
            window_hours = 24  # 24-hour rolling window for drop detection
            drop_low_tracker = {}  # Track recovery after drops
            
            for i in range(len(df)):
                current_row = df.iloc[i]
                current_ts = current_row['datetime']
                current_px = current_row['price']
                
                # Look back for peak in rolling window
                lookback_start = current_ts - timedelta(hours=window_hours)
                window_df = df[(df['datetime'] >= lookback_start) & (df['datetime'] <= current_ts)]
                
                if len(window_df) > 1:
                    window_peak = window_df['price'].max()
                    
                    if window_peak > 0:
                        drop_pct = (window_peak - current_px) / window_peak
                        
                        # Detect major drops (50%+ sustained, 85%+ for rugpull consideration)
                        if drop_pct >= 0.5:
                            has_sustained_drop = True
                        
                        if drop_pct >= 0.85:  # Higher threshold for rugpull detection
                            is_early_phase = current_ts <= early_phase_end
                            
                            # Check if this is a rapid drop
                            peak_rows = window_df[window_df['price'] == window_peak]
                            if not peak_rows.empty:
                                peak_time = peak_rows['datetime'].iloc[0]
                                hours_since_peak = (current_ts - peak_time).total_seconds() / 3600
                                is_rapid = hours_since_peak <= self.RUG_RAPID_DROP_HOURS
                                
                                if is_rapid:
                                    rapid_drops_count += 1
                                
                                # Record drop for recovery analysis
                                drop_id = f"{current_ts}_{drop_pct:.3f}"
                                drop_low_tracker[drop_id] = {
                                    'low': current_px,
                                    'time': current_ts,
                                    'drop_pct': drop_pct,
                                    'is_early': is_early_phase,
                                    'is_rapid': is_rapid
                                }
                                
                                price_drops.append((current_ts.to_pydatetime(), drop_pct))
            
            # Analyze recovery patterns
            for drop_id, drop_info in drop_low_tracker.items():
                drop_low = drop_info['low']
                drop_time = drop_info['time']
                
                # Look for recovery in the following recovery window
                recovery_end = drop_time + timedelta(days=self.RECOVERY_ANALYSIS_DAYS)
                recovery_df = df[(df['datetime'] > drop_time) & (df['datetime'] <= recovery_end)]
                
                if not recovery_df.empty:
                    max_price_after = recovery_df['price'].max()
                    recovery_ratio = max_price_after / drop_low if drop_low > 0 else 0
                    
                    # Update recovery metrics
                    max_recovery = max(max_recovery, recovery_ratio)
                    if recovery_ratio >= self.SUCCESS_RECOVERY_MULTIPLIER:
                        has_recovery = True
                    
                    # Categorize drops by phase
                    drop_entry = (drop_time.to_pydatetime(), drop_info['drop_pct'], recovery_ratio)
                    if drop_info['is_early']:
                        early_drops.append(drop_entry)
                    else:
                        late_drops.append(drop_entry)
            
            # Determine current trend (last 7 days)
            recent_start = current_time - timedelta(days=7)
            recent_df = df[df['datetime'] >= recent_start]
            current_trend = "stable"
            
            if len(recent_df) >= 2:
                recent_start_price = recent_df['price'].iloc[0]
                recent_end_price = recent_df['price'].iloc[-1]
                change_pct = (recent_end_price - recent_start_price) / recent_start_price if recent_start_price > 0 else 0
                
                if change_pct > 0.2:
                    current_trend = "recovering"
                elif change_pct < -0.2:
                    current_trend = "declining"
            
            # Calculate days since last major drop
            days_since_last_drop = None
            if price_drops:
                last_drop_time = max(drop_time for drop_time, _ in price_drops)
                days_since_last_drop = (current_time - pd.to_datetime(last_drop_time)).days
            
            # Calculate enhanced metrics
            appreciation_ratio = (post_ath_peak_price / peak_price_72h) if peak_price_72h > 0 else 0
            
            result = {
                'peak_price_72h': float(peak_price_72h) if peak_price_72h else None,
                'post_ath_peak_price': float(post_ath_peak_price) if post_ath_peak_price else None,
                'current_price': float(current_price) if current_price else None,
                'has_sustained_drop': has_sustained_drop,
                'price_drops': price_drops,
                'appreciation_ratio': appreciation_ratio,
                
                # Enhanced metrics
                'early_phase_drops': early_drops,
                'late_phase_drops': late_drops,
                'max_recovery_after_drop': max_recovery,
                'rapid_drops_count': rapid_drops_count,
                'days_since_last_major_drop': days_since_last_drop,
                'has_shown_recovery': has_recovery,
                'current_trend': current_trend,
            }
            
            logger.info(f"{mint}: Enhanced analysis complete")
            logger.info(f"  - Appreciation: {appreciation_ratio:.1f}x")
            logger.info(f"  - Major drops: {len(price_drops)} (Rapid: {rapid_drops_count})")
            logger.info(f"  - Max recovery: {max_recovery:.1f}x")
            logger.info(f"  - Current trend: {current_trend}")
            logger.info(f"  - Days since last drop: {days_since_last_drop}")
            
            return result
        except Exception as e:
            logger.error(f"Error in enhanced price analysis for {mint}: {e}")
            return {}

    def _classify(self, m: TokenMetrics) -> str:
        """
        Enhanced classification with sophisticated rugpull detection and mega-success recognition.
        """
        # Check for inactive tokens first
        if self._is_inactive(m):
            return "inactive"
        
        # Calculate comprehensive metrics for classification
        self._calculate_enhanced_metrics(m)
        
        # PRIORITY 1: Tokens with massive historical appreciation (10,000x+) are almost always successful
        # These should override any other classification unless it's clear fraud
        if (m.mega_appreciation and m.mega_appreciation >= 10000):
            # Only deny success if there's clear evidence of total abandonment/scam
            if (m.current_vs_ath_ratio and m.current_vs_ath_ratio < 0.0001 and  # < 0.01% of ATH 
                m.days_since_last_major_drop and m.days_since_last_major_drop < 7 and  # Recent drops
                m.current_trend == "declining"):
                # Still be generous - this is likely a temporary pullback
                pass
            else:
                self._log_classification_reasoning(m, "successful")
                return "successful"
        
        # PRIORITY 2: Tokens with good appreciation (1000x+) and reasonable current price
        if self._is_mega_success(m):
            self._log_classification_reasoning(m, "successful")
            return "successful"
        
        # PRIORITY 3: Tokens with massive recovery patterns (even if volatile)
        if (m.max_recovery_after_drop and m.max_recovery_after_drop >= 1000000 and  # Million-x recovery
            m.mega_appreciation and m.mega_appreciation >= 1000):  # Plus good appreciation
            self._log_classification_reasoning(m, "successful")
            return "successful"
        
        # Check for traditional success
        if self._is_traditional_success(m):
            self._log_classification_reasoning(m, "successful")
            return "successful"
        
        # Check for recovery-based success (tokens that recovered well after drops)
        if self._is_recovery_success(m):
            self._log_classification_reasoning(m, "successful")
            return "successful"
        
        # Very conservative rugpull detection - only clear coordinated dumps
        # BUT: Never classify tokens with massive historical appreciation as rugpulls
        if (not m.mega_appreciation or m.mega_appreciation < 100) and self._is_clear_rugpull(m):
            self._log_classification_reasoning(m, "rugpull")
            return "rugpull"
        
        # Default to unsuccessful
        self._log_classification_reasoning(m, "unsuccessful")
        return "unsuccessful"

    def _is_inactive(self, m: TokenMetrics) -> bool:
        """
        Check if token is inactive - but ONLY for tokens that never showed success.
        Historically successful tokens should not be penalized for current low activity.
        """
        # Never classify tokens with any significant historical appreciation as inactive
        if m.mega_appreciation and m.mega_appreciation >= 10:  # Even 10x+ should not be inactive
            return False
        
        # Never classify tokens that showed meaningful recovery as inactive
        if m.has_shown_recovery and m.max_recovery_after_drop and m.max_recovery_after_drop >= 2:
            return False
        
        # Never classify tokens with reasonable holder base as inactive (shows community)
        if m.holder_count and m.holder_count >= 50:  # Lowered threshold for community
            return False
        
        # Only classify as inactive if the token truly never gained traction:
        # 1. Very low appreciation (< 10x)
        # 2. Very few holders (< 20)
        # 3. Extremely low current volume (< $10) indicating complete abandonment
        
        low_appreciation = not m.mega_appreciation or m.mega_appreciation < 10
        very_few_holders = m.holder_count is not None and m.holder_count < 20
        completely_dead = m.volume_24h is not None and m.volume_24h < 10
        
        # Only mark as inactive if it never gained any meaningful traction
        return low_appreciation and very_few_holders and completely_dead

    def _is_mega_success(self, m: TokenMetrics) -> bool:
        """
        Detect mega-successful tokens (1000x+ appreciation).
        These are almost always successful regardless of volatility.
        """
        if not m.mega_appreciation:
            return False
        
        # Ultra mega success (100,000x+) - almost always successful with very lenient current price requirement
        if m.mega_appreciation >= 100000:
            # Only need to be above 0.001% of ATH (extremely lenient)
            if not m.current_vs_ath_ratio or m.current_vs_ath_ratio >= 0.00001:
                return True
        
        # Super mega success (10,000x+) - very lenient current price requirement
        if m.mega_appreciation >= 10000:
            # Only need to be above 0.01% of ATH
            if not m.current_vs_ath_ratio or m.current_vs_ath_ratio >= 0.0001:
                return True
        
        # Regular mega success (1000x+) - standard requirement
        if (m.mega_appreciation >= self.SUCCESS_MEGA_APPRECIATION and 
            m.current_vs_ath_ratio and m.current_vs_ath_ratio >= self.SUCCESS_SUSTAINED_HIGH_RATIO):
            return True
        
        # Use success score for borderline cases with high appreciation
        if (m.mega_appreciation >= 500 and  # Even 500x+ gets consideration
            m.final_evaluation_score and m.final_evaluation_score >= 0.6):  # Slightly lower threshold
            return True
        
        return False

    def _is_traditional_success(self, m: TokenMetrics) -> bool:
        """Traditional success criteria (10x+ with no major sustained drops)."""
        if None in (m.peak_price_72h, m.post_ath_peak_price, m.holder_count):
            return False
        
        if m.holder_count < self.SUCCESS_MIN_HOLDERS:
            return False
        
        # Traditional success: 10x+ appreciation without sustained drops
        if (m.post_ath_peak_price / m.peak_price_72h >= self.SUCCESS_APPRECIATION and 
            not m.has_sustained_drop):
            return True
        
        return False

    def _is_recovery_success(self, m: TokenMetrics) -> bool:
        """
        Recovery-based success: Token that recovered well after drops.
        More lenient than original algorithm.
        """
        if not m.has_shown_recovery or not m.max_recovery_after_drop:
            return False
        
        # Strong recovery with reasonable holder count
        if (m.max_recovery_after_drop >= self.SUCCESS_RECOVERY_MULTIPLIER and
            m.holder_count and m.holder_count >= self.SUCCESS_MIN_HOLDERS // 2):  # Half the normal requirement
            
            # Current trend should not be strongly declining
            if m.current_trend != "declining":
                return True
        
        return False

    def _is_clear_rugpull(self, m: TokenMetrics) -> bool:
        """
        Very conservative rugpull detection - only flag clear coordinated dumps.
        Much higher threshold to prevent false positives.
        """
        if not m.price_drops:
            return False
        
        # Must have drops above the higher threshold (85%)
        major_drops = [d for _, d in m.price_drops if d >= self.RUG_THRESHOLD]
        if not major_drops:
            return False
        
        # Must have many major drops (indicating pattern, not volatility)
        if m.total_major_drops < self.RUG_MIN_DROPS_FOR_PATTERN:
            return False
        
        # Current price must be very low vs ATH (indicating no recovery)
        if m.current_vs_ath_ratio and m.current_vs_ath_ratio >= self.RUG_FINAL_PRICE_RATIO:
            return False  # Price is still reasonable vs ATH
        
        # Multiple rapid coordinated dumps
        if m.rapid_drops_count >= 3:  # Increased threshold
            return True
        
        # Many drops with very long time without recovery and declining trend
        if (m.total_major_drops >= 10 and 
            m.days_since_last_major_drop and m.days_since_last_major_drop >= self.RUG_NO_RECOVERY_DAYS and
            m.current_trend == "declining"):
            return True
        
        return False

    def _calculate_enhanced_metrics(self, m: TokenMetrics) -> None:
        """Calculate enhanced metrics for classification."""
        # Calculate mega appreciation if we have the data
        if m.peak_price_72h and m.post_ath_peak_price and m.peak_price_72h > 0:
            m.mega_appreciation = m.post_ath_peak_price / m.peak_price_72h
        
        # Calculate current vs ATH ratio
        if m.current_price and m.post_ath_peak_price and m.post_ath_peak_price > 0:
            m.current_vs_ath_ratio = m.current_price / m.post_ath_peak_price
        
        # Calculate total major drops
        m.total_major_drops = len([d for _, d in m.price_drops if d >= self.RUG_THRESHOLD])
        
        # Calculate final evaluation score
        m.final_evaluation_score = self._calculate_success_score(m)

    def _calculate_success_score(self, m: TokenMetrics) -> float:
        """Calculate a comprehensive success score considering all factors."""
        score = 0.0
        
        # Mega appreciation bonus (most important factor) - More generous scoring
        if m.mega_appreciation:
            if m.mega_appreciation >= 1000000:   # 1,000,000x+
                score += 0.7
            elif m.mega_appreciation >= 100000:  # 100,000x+
                score += 0.6
            elif m.mega_appreciation >= 10000:   # 10,000x+
                score += 0.5
            elif m.mega_appreciation >= 1000:    # 1,000x+
                score += 0.4
            elif m.mega_appreciation >= 100:     # 100x+
                score += 0.3
            elif m.mega_appreciation >= 10:      # 10x+
                score += 0.2
        
        # Current price vs ATH (sustainability factor) - More lenient
        if m.current_vs_ath_ratio:
            if m.current_vs_ath_ratio >= 0.5:    # Still 50%+ of ATH
                score += 0.2
            elif m.current_vs_ath_ratio >= 0.1:  # Still 10%+ of ATH
                score += 0.15
            elif m.current_vs_ath_ratio >= 0.01: # Still 1%+ of ATH
                score += 0.1
            elif m.current_vs_ath_ratio >= 0.001: # Still 0.1%+ of ATH (added)
                score += 0.05
        
        # Recovery pattern bonus - More generous for massive recoveries
        if m.has_shown_recovery and m.max_recovery_after_drop:
            if m.max_recovery_after_drop >= 1000000:  # Million-x recovery
                score += 0.2
            elif m.max_recovery_after_drop >= 100000:  # 100,000x recovery
                score += 0.15
            elif m.max_recovery_after_drop >= 10:
                score += 0.1
            elif m.max_recovery_after_drop >= 5:
                score += 0.05
        
        # Holder count bonus
        if m.holder_count:
            if m.holder_count >= 500:
                score += 0.1
            elif m.holder_count >= 100:
                score += 0.05
        
        # Penalty for excessive drops - but much more lenient for high appreciation tokens
        if m.total_major_drops and m.mega_appreciation:
            # Scale penalty based on appreciation - mega successful tokens get much less penalty
            penalty_scale = 1.0
            if m.mega_appreciation >= 10000:
                penalty_scale = 0.1  # Only 10% penalty for 10,000x+ tokens
            elif m.mega_appreciation >= 1000:
                penalty_scale = 0.3  # Only 30% penalty for 1,000x+ tokens
            elif m.mega_appreciation >= 100:
                penalty_scale = 0.6  # 60% penalty for 100x+ tokens
            
            if m.total_major_drops >= 20:
                score -= 0.2 * penalty_scale
            elif m.total_major_drops >= 10:
                score -= 0.1 * penalty_scale
            elif m.total_major_drops >= 5:
                score -= 0.05 * penalty_scale
        
        # Current trend bonus/penalty
        if m.current_trend == "recovering":
            score += 0.05
        elif m.current_trend == "declining":
            # Much less penalty for declining if historically successful
            penalty = 0.1
            if m.mega_appreciation and m.mega_appreciation >= 1000:
                penalty = 0.02  # Minimal penalty for mega successful tokens
            score -= penalty
        
        return max(0.0, min(1.0, score))  # Clamp between 0 and 1

    def _log_classification_reasoning(self, m: TokenMetrics, label: str) -> None:
        """Log detailed reasoning for classification decision."""
        logger.info(f"Token {m.mint_address} classification details:")
        logger.info(f"  - Current price: {m.current_price}")
        logger.info(f"  - Volume 24h: {m.volume_24h}")
        logger.info(f"  - Holder count: {m.holder_count}")
        logger.info(f"  - Transaction count: {m.transaction_count}")
        logger.info(f"  - Mega appreciation: {m.mega_appreciation}x" if m.mega_appreciation else "  - Mega appreciation: None")
        logger.info(f"  - Current vs ATH ratio: {m.current_vs_ath_ratio:.4f}" if m.current_vs_ath_ratio else "  - Current vs ATH ratio: None")
        logger.info(f"  - Total major drops: {m.total_major_drops}")
        logger.info(f"  - Rapid drops: {m.rapid_drops_count}")
        logger.info(f"  - Max recovery: {m.max_recovery_after_drop}x" if m.max_recovery_after_drop else "  - Max recovery: None")
        logger.info(f"  - Success score: {m.final_evaluation_score:.3f}" if m.final_evaluation_score else "  - Success score: None")
        logger.info(f"  - Current trend: {m.current_trend}")
        
        if label == "successful":
            reasons = []
            if m.mega_appreciation and m.mega_appreciation >= 1000:
                reasons.append(f"mega appreciation ({m.mega_appreciation:.0f}x)")
            if m.current_vs_ath_ratio and m.current_vs_ath_ratio >= 0.01:
                reasons.append(f"sustained price ({m.current_vs_ath_ratio:.2%} of ATH)")
            if m.final_evaluation_score and m.final_evaluation_score >= 0.7:
                reasons.append(f"high success score ({m.final_evaluation_score:.3f})")
            logger.info(f"  → SUCCESS due to: {', '.join(reasons) if reasons else 'traditional criteria'}")
            
        elif label == "rugpull":
            reasons = []
            if m.rapid_drops_count >= 3:
                reasons.append(f"multiple coordinated dumps ({m.rapid_drops_count})")
            if m.total_major_drops >= 10:
                reasons.append(f"excessive drops ({m.total_major_drops})")
            if m.current_vs_ath_ratio and m.current_vs_ath_ratio < 0.01:
                reasons.append(f"collapsed price ({m.current_vs_ath_ratio:.4%} of ATH)")
            logger.info(f"  → RUGPULL due to: {', '.join(reasons)}")
        
        elif label == "unsuccessful":
            logger.info(f"  → UNSUCCESSFUL: Doesn't meet success criteria but not clear rugpull")

    # ...existing code...
# ───────────────────────── CLI wrapper ─────────────────────────
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Label Solana tokens using REAL on-chain data")
    parser.add_argument("--input", required=True, help="CSV with 'mint_address' column")
    parser.add_argument("--output", required=True, help="output CSV path")
    parser.add_argument("--batch", type=int, default=5, help="batch size (default 5 for rate limiting)")
    args = parser.parse_args()

    async def runner():
        async with RealOnChainTokenLabeler() as tl:
            await tl.label_tokens_from_csv(args.input, args.output, args.batch)

    asyncio.run(runner())

if __name__ == "__main__":
    main()
