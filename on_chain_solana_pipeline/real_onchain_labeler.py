#!/usr/bin/env python3
"""
Real on-chain token labeler using actual Helius API calls.

- Provides ``RealOnChainProvider``, a data provider that fetches token
  holder counts, transaction signatures, and full transaction details
  directly from the Helius RPC gateway with circuit-breaker protection
  and concurrency-limited request handling.
- Provides ``RealOnChainTokenLabeler``, a classification engine that
  labels SPL tokens as "successful", "unsuccessful", "rugpull", or
  "inactive" based on on-chain price history, holder counts, and
  sophisticated pattern detection (recovery analysis, rapid-dump
  detection, mega-success recognition).
- Supports batch CSV processing with per-token timeouts and rate-limit
  delays between tokens.
- All API calls are routed through the shared ``HeliusAPIKeyManager``
  for automatic key rotation and cooldown handling.

Author: ML-Bullx Team
Date:   2025-08-01
"""

# ==============================================================================
# Standard library imports
# ==============================================================================
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# ==============================================================================
# Third-party imports
# ==============================================================================
import aiohttp
import pandas as pd
from dotenv import load_dotenv

# ==============================================================================
# Local imports
# ==============================================================================
from shared.models import TokenMetrics
from shared.constants import ONE_HOUR, THREE_DAYS_SEC, SUSTAIN_DAYS_SEC, HELIUS_BASE_URL
from on_chain_solana_pipeline.api_key_manager import get_key_manager

load_dotenv()

logger = logging.getLogger(__name__)


# ==============================================================================
# Real on-chain data provider
# ==============================================================================
class RealOnChainProvider:
    """Data provider that makes actual Helius API calls for token analysis.

    Wraps all RPC interactions behind a circuit breaker that halts
    outgoing requests after a configurable number of consecutive
    failures.  A semaphore limits concurrency to avoid overwhelming
    the API.

    Attributes:
        session: The ``aiohttp`` client session (created on context entry).
        key_manager: Shared Helius API key manager instance.
        rate_limit_semaphore: Limits concurrent outgoing API calls.
        circuit_breaker_failures: Running count of consecutive failures.
        circuit_breaker_threshold: Failure count that trips the breaker.
        circuit_breaker_reset_time: Seconds before the breaker auto-resets.
    """

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
        """Create the HTTP session with conservative timeouts."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15, connect=5)
        )
        return self

    async def __aexit__(self, *exc):
        """Close the HTTP session."""
        if self.session:
            await self.session.close()

    # ------------------------------------------------------------------
    # Core RPC helper
    # ------------------------------------------------------------------
    async def _make_helius_request(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send a JSON-RPC request to Helius with circuit breaker and retries.

        The circuit breaker trips after ``circuit_breaker_threshold``
        consecutive failures and auto-resets after
        ``circuit_breaker_reset_time`` seconds.  Each call is gated by
        ``rate_limit_semaphore`` to cap concurrency.

        Args:
            payload: The JSON-RPC request body.

        Returns:
            The parsed JSON response dict, or None on failure.
        """
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
            max_retries = 2

            for attempt in range(max_retries):
                # First try to get an immediately available key
                api_key = self.key_manager.get_next_available_key()

                # If no key is available, wait for one to become available
                if not api_key:
                    logger.warning("No Helius API keys immediately available, waiting...")
                    api_key = await self.key_manager.wait_for_available_key(max_wait_time=30)
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
                            self.circuit_breaker_failures = 0
                            result = await response.json()
                            return result
                        elif response.status == 429:
                            logger.warning(f"Rate limited on key {api_key[:8]}... (attempt {attempt + 1})")
                            self.key_manager.record_request_failure(api_key, is_rate_limit=True)
                            self.circuit_breaker_failures += 1
                            await asyncio.sleep(2 ** attempt)
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

    # ------------------------------------------------------------------
    # Token accounts (holder count proxy)
    # ------------------------------------------------------------------
    async def get_token_accounts(self, mint: str) -> Optional[int]:
        """Get token account count as a holder count proxy.

        Args:
            mint: The SPL token mint address.

        Returns:
            The number of token accounts found (up to the 1000-account
            sample limit), or None on failure.
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccounts",
            "params": [
                {
                    "mint": mint,
                    "limit": 1000
                }
            ]
        }

        result = await self._make_helius_request(payload)
        if result and "result" in result:
            token_accounts = result["result"].get("token_accounts", [])
            return len(token_accounts)
        return None

    # ------------------------------------------------------------------
    # Signature collection (with pagination)
    # ------------------------------------------------------------------
    async def get_signatures_for_address(self, mint: str, limit: int = 1000, get_all: bool = True) -> List[str]:
        """Get transaction signatures for a token with optional full pagination.

        When ``get_all`` is True the method paginates through all
        available signatures (up to a 10 000 safety cap).  Consecutive
        API failures are tracked and the loop aborts after five in a
        row.

        Args:
            mint: The Solana address to query.
            limit: Maximum signatures per RPC call (capped at 1000).
            get_all: When True, paginate until all signatures are collected.

        Returns:
            A list of transaction signature strings.
        """
        all_signatures = []

        if not get_all:
            return await self._get_signatures_batch(mint, limit)

        # Get all signatures using pagination
        before = None
        total_fetched = 0
        max_total = 10000
        consecutive_failures = 0
        max_consecutive_failures = 5

        logger.info(f"Starting paginated signature collection for {mint}")

        while total_fetched < max_total and consecutive_failures < max_consecutive_failures:
            params = [
                mint,
                {
                    "limit": min(limit, 1000),
                    "commitment": "finalized",
                    "searchTransactionHistory": True
                }
            ]

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

            # Delay to respect rate limits
            await asyncio.sleep(1.0)

        logger.info(f"Total signatures collected for {mint}: {len(all_signatures)}")
        return all_signatures

    async def _get_signatures_batch(self, mint: str, limit: int) -> List[str]:
        """Get a single batch of signatures (non-paginated legacy helper).

        Args:
            mint: The Solana address to query.
            limit: Maximum number of signatures to return.

        Returns:
            A list of transaction signature strings.
        """
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

    # ------------------------------------------------------------------
    # Transaction details
    # ------------------------------------------------------------------
    async def get_transaction(self, signature: str) -> Optional[Dict[str, Any]]:
        """Get full transaction details with finalized commitment.

        Args:
            signature: The base-58 transaction signature.

        Returns:
            The ``result`` field of the JSON-RPC response, or None.
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {
                    "encoding": "json",
                    "maxSupportedTransactionVersion": 0,
                    "commitment": "finalized",
                    "searchTransactionHistory": True
                }
            ]
        }

        result = await self._make_helius_request(payload)
        if result and "result" in result:
            return result["result"]
        return None

    # ------------------------------------------------------------------
    # Token activity analysis
    # ------------------------------------------------------------------
    async def analyze_token_activity(self, mint: str) -> Dict[str, Any]:
        """Analyse token transaction activity to derive pricing metrics.

        Fetches all signatures, samples a subset for detailed analysis,
        and extracts swap-like transactions to build a price history.

        Args:
            mint: The SPL token mint address.

        Returns:
            A dict of calculated metrics (estimated price, volume,
            transaction count), or an empty dict on failure.
        """
        try:
            signatures = await self.get_signatures_for_address(mint, get_all=True)
            if not signatures:
                logger.info(f"No signatures found for {mint}")
                return {}

            logger.info(f"Found {len(signatures)} signatures for {mint}")

            # Smart sampling: analyse fewer transactions to avoid rate limits
            max_to_analyze = min(len(signatures), 20)

            if len(signatures) <= max_to_analyze:
                signatures_to_analyze = signatures
            else:
                # Sample strategically: more from early period, some recent
                early_count = min(20, len(signatures) // 4)
                recent_count = min(10, len(signatures) // 10)
                middle_count = max_to_analyze - early_count - recent_count

                middle_start = early_count
                middle_end = len(signatures) - recent_count
                step = max(1, (middle_end - middle_start) // middle_count) if middle_count > 0 else 1

                signatures_to_analyze = (
                    list(signatures[:early_count]) +
                    list(signatures[middle_start:middle_end:step][:middle_count]) +
                    list(signatures[-recent_count:])
                )

                # Remove duplicates while preserving order
                seen = set()
                signatures_to_analyze = [x for x in signatures_to_analyze if not (x in seen or seen.add(x))]

            logger.info(f"Analyzing {len(signatures_to_analyze)} sampled transactions from {len(signatures)} total for {mint}")

            # Analyse transactions with very conservative rate limiting
            swap_data = []
            batch_size = 1

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
                            if self._looks_like_swap(tx):
                                swap_info = self._extract_swap_info(tx, mint)
                                if swap_info:
                                    swap_data.append(swap_info)

                        await asyncio.sleep(1.0)

                    except Exception as e:
                        logger.warning(f"Error analyzing transaction {sig}: {e}")
                        await asyncio.sleep(2.0)
                        continue

                # Pause between batches to respect rate limits
                if i + batch_size < len(signatures_to_analyze):
                    logger.info(f"Pausing 5 seconds between batches to respect rate limits...")
                    await asyncio.sleep(5.0)

            if swap_data:
                logger.info(f"Found {len(swap_data)} swap transactions for {mint}")
                return self._calculate_metrics_from_swaps(swap_data)
            else:
                logger.info(f"No swap data found for {mint}")
                return {}

        except Exception as e:
            logger.error(f"Error analyzing token activity for {mint}: {e}")
            return {}

    # ------------------------------------------------------------------
    # Swap detection helpers
    # ------------------------------------------------------------------
    def _looks_like_swap(self, tx: Dict[str, Any]) -> bool:
        """Heuristically check if a transaction looks like a swap.

        Args:
            tx: Parsed transaction dict.

        Returns:
            True when token balances changed between pre and post state.
        """
        if not tx.get("meta") or not tx["meta"].get("postTokenBalances"):
            return False

        pre_balances = tx["meta"].get("preTokenBalances", [])
        post_balances = tx["meta"].get("postTokenBalances", [])

        return len(pre_balances) != len(post_balances) or \
               any(pre.get("uiTokenAmount", {}).get("uiAmount") != post.get("uiTokenAmount", {}).get("uiAmount")
                   for pre, post in zip(pre_balances, post_balances))

    def _extract_swap_info(self, tx: Dict[str, Any], mint: str) -> Optional[Dict[str, Any]]:
        """Extract swap price and volume from a transaction.

        Computes price as SOL change / token change, using a rough
        SOL/USD estimate of $150.

        Args:
            tx: Parsed transaction dict.
            mint: The SPL token mint to track.

        Returns:
            A dict with ``slot``, ``timestamp``, ``amount``, ``price``,
            ``volume_usd``, and ``signature`` keys, or None.
        """
        try:
            slot = tx.get("slot", 0)
            timestamp = tx.get("blockTime", 0)

            pre_balances = tx["meta"].get("preTokenBalances", [])
            post_balances = tx["meta"].get("postTokenBalances", [])

            pre_sol_balances = tx["meta"].get("preBalances", [])
            post_sol_balances = tx["meta"].get("postBalances", [])

            # Find token amount changes
            token_change = 0
            sol_change = 0

            for pre, post in zip(pre_balances, post_balances):
                if pre.get("mint") == mint and post.get("mint") == mint:
                    pre_amount = pre.get("uiTokenAmount", {}).get("uiAmount", 0) or 0
                    post_amount = post.get("uiTokenAmount", {}).get("uiAmount", 0) or 0
                    token_change = abs(post_amount - pre_amount)
                    break

            # Calculate SOL balance change (convert lamports to SOL)
            if pre_sol_balances and post_sol_balances:
                for i, (pre_sol, post_sol) in enumerate(zip(pre_sol_balances, post_sol_balances)):
                    sol_delta = abs(post_sol - pre_sol) / 1e9
                    if sol_delta > 0.001:  # Minimum meaningful SOL change
                        sol_change = sol_delta
                        break

            # Calculate price if we have both token and SOL changes
            if token_change > 0 and sol_change > 0:
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
        """Calculate basic metrics from collected swap data.

        Args:
            swap_data: List of swap info dicts as returned by
                ``_extract_swap_info``.

        Returns:
            A dict with ``estimated_price``, ``volume_24h``,
            ``transaction_count``, and ``latest_activity`` keys.
        """
        if not swap_data:
            return {}

        swap_data.sort(key=lambda x: x.get("timestamp", 0))

        amounts = [s["amount"] for s in swap_data if s.get("amount")]
        if not amounts:
            return {}

        recent_amount = amounts[-1] if amounts else 0
        total_volume = sum(amounts)

        return {
            "estimated_price": recent_amount * 0.001,
            "volume_24h": total_volume * 0.001,
            "transaction_count": len(swap_data),
            "latest_activity": swap_data[-1]["timestamp"] if swap_data else 0
        }


# ==============================================================================
# Token labeler
# ==============================================================================
class RealOnChainTokenLabeler:
    """Classifies SPL tokens using on-chain data and pattern analysis.

    Applies a multi-tier classification strategy:
      1. Inactive detection (tokens that never gained traction).
      2. Mega-success recognition (1000x+ appreciation).
      3. Recovery-based success (strong bounce after major drops).
      4. Traditional success (10x+ with stable holder base).
      5. Conservative rugpull detection (coordinated dumps only).
      6. Default: unsuccessful.

    Class-level constants control thresholds for each tier.
    """

    # -- Rugpull detection thresholds (very conservative) --
    RUG_THRESHOLD = 0.85                  # Minimum drop % to count as major
    RUG_MIN_DROPS_FOR_PATTERN = 5         # Minimum major drops for pattern
    RUG_RAPID_DROP_HOURS = 2              # Window for coordinated dump detection
    RUG_NO_RECOVERY_DAYS = 14             # Days without recovery before rugpull
    RUG_FINAL_PRICE_RATIO = 0.01          # Final price must be <1% of ATH

    # -- Success criteria --
    SUCCESS_APPRECIATION = 10.0           # Minimum appreciation for traditional success
    SUCCESS_MIN_HOLDERS = 100             # Minimum holder count for success
    SUCCESS_RECOVERY_MULTIPLIER = 5.0     # Required recovery ratio (5x from low)
    SUCCESS_MEGA_APPRECIATION = 1000.0    # Threshold for mega-success (1000x+)
    SUCCESS_SUSTAINED_HIGH_RATIO = 0.1    # Must maintain 10%+ of ATH

    # -- Activity thresholds --
    MIN_ACTIVITY_TRANSACTIONS = 15        # Minimum transactions for active status
    INACTIVE_VOLUME_THRESHOLD = 1000      # Volume below this is considered dead
    INACTIVE_HOLDER_THRESHOLD = 10        # Holders below this is considered dead

    # -- Analysis parameters --
    EARLY_PHASE_DAYS = 14                 # Duration of the "early phase" window
    RECOVERY_ANALYSIS_DAYS = 60           # Window to look for recovery after drops
    MAX_TRANSACTIONS = 2000               # Maximum transactions to analyse

    def __init__(self):
        self.provider: Optional[RealOnChainProvider] = None

    async def __aenter__(self):
        """Create and enter the underlying ``RealOnChainProvider``."""
        self.provider = RealOnChainProvider()
        await self.provider.__aenter__()
        return self

    async def __aexit__(self, *exc):
        """Tear down the provider."""
        if self.provider:
            await self.provider.__aexit__(*exc)

    # ------------------------------------------------------------------
    # CSV batch processing
    # ------------------------------------------------------------------
    async def label_tokens_from_csv(self, inp: str, out: str, batch: int = 10) -> pd.DataFrame:
        """Read mint addresses from a CSV, label each, and write results.

        Args:
            inp: Path to the input CSV (must have a ``mint_address`` column).
            out: Path where the labelled output CSV will be written.
            batch: Number of tokens per processing batch.

        Returns:
            A DataFrame with ``mint_address`` and ``label`` columns.

        Raises:
            ValueError: If the input CSV lacks a ``mint_address`` column.
        """
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
                await asyncio.sleep(2)

            logger.info(f"Completed batch {i // batch + 1}, processed {len(results)} tokens so far")

        out_df = pd.DataFrame(results, columns=["mint_address", "label"])
        out_df.to_csv(out, index=False)
        logger.info("Saved %d labeled tokens -> %s", len(out_df), out)
        return out_df

    # ------------------------------------------------------------------
    # Single-token processing
    # ------------------------------------------------------------------
    async def _process(self, mint: str) -> Optional[Tuple[str, str]]:
        """Process a single token with comprehensive error handling.

        Args:
            mint: The SPL token mint address.

        Returns:
            A ``(mint_address, label)`` tuple, or ``(mint, "inactive")``
            on timeout / error.
        """
        try:
            logger.info(f"Processing token: {mint}")

            m = await asyncio.wait_for(self._gather_metrics(mint), timeout=60)

            if not self._has_any_data(m):
                logger.info(f"{mint} -- skipped (no on-chain data)")
                return mint, "inactive"

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
        """Return True if the metrics contain any usable data.

        Args:
            m: The gathered token metrics.

        Returns:
            True when at least one of current_price, holder_count,
            or transaction_count is populated.
        """
        return (m.current_price is not None or
                m.holder_count is not None or
                m.transaction_count > 0)

    # ------------------------------------------------------------------
    # Metrics gathering
    # ------------------------------------------------------------------
    async def _gather_metrics(self, mint: str) -> TokenMetrics:
        """Gather comprehensive on-chain metrics for a token.

        Collects holder count, transaction signatures, swap data, and
        builds a full price history for pattern analysis.

        Args:
            mint: The SPL token mint address.

        Returns:
            A populated ``TokenMetrics`` instance.
        """
        t = TokenMetrics(mint)

        try:
            # 1. Get holder count from token accounts
            holder_count = await self.provider.get_token_accounts(mint)
            if holder_count:
                t.holder_count = holder_count
                logger.info(f"{mint}: Found {holder_count} token accounts")

            # 2. Get comprehensive transaction history
            signatures = await self.provider.get_signatures_for_address(mint, get_all=True)
            logger.info(f"Found {len(signatures)} signatures for {mint}")

            if signatures:
                all_swaps = []
                price_history = []

                # Process transactions in batches for swap extraction
                batch_size = 20
                max_transactions = min(len(signatures), 500)

                for i in range(0, max_transactions, batch_size):
                    batch_signatures = signatures[i:i + batch_size]

                    tasks = [self.provider.get_transaction(sig) for sig in batch_signatures]
                    transactions = await asyncio.gather(*tasks, return_exceptions=True)

                    for tx in transactions:
                        if isinstance(tx, dict) and tx:
                            if self.provider._looks_like_swap(tx):
                                swap_info = self.provider._extract_swap_info(tx, mint)
                                if swap_info:
                                    all_swaps.append(swap_info)

                                    if 'timestamp' in swap_info and 'price' in swap_info:
                                        price_history.append({
                                            'timestamp': swap_info['timestamp'],
                                            'price': swap_info['price'],
                                            'volume': swap_info.get('volume_usd', 0)
                                        })

                    await asyncio.sleep(0.3)

                logger.info(f"Found {len(all_swaps)} swap transactions for {mint}")

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

                    # 4. Enhanced price history analysis
                    historical_analysis = await self._analyze_comprehensive_price_history(price_history, mint)
                    if historical_analysis:
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

    # ------------------------------------------------------------------
    # Comprehensive price history analysis
    # ------------------------------------------------------------------
    async def _analyze_comprehensive_price_history(self, price_history: List[Dict], mint: str) -> Dict[str, Any]:
        """Perform enhanced price analysis with pattern detection.

        Analyses the full price history to identify major drops,
        recovery patterns, rapid coordinated dumps, and current trend
        direction.  Uses a 24-hour rolling window for drop detection
        and categorises drops into early-phase and late-phase buckets.

        Args:
            price_history: List of dicts with ``timestamp`` and
                ``price`` keys.
            mint: The SPL token mint (for logging).

        Returns:
            A dict containing peak prices, drop lists, recovery
            metrics, trend direction, and other analysis results.
            Returns an empty dict on insufficient data or error.
        """
        if not price_history or len(price_history) < 2:
            return {}

        try:
            sorted_history = sorted(price_history, key=lambda x: x['timestamp'])

            df = pd.DataFrame(sorted_history)
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')

            # Key time boundaries
            launch_time = df['datetime'].min()
            current_time = df['datetime'].max()
            early_phase_end = launch_time + timedelta(days=self.EARLY_PHASE_DAYS)
            hours_72_cutoff = launch_time + timedelta(hours=72)

            # Split into early (first 72h) and post periods
            early_df = df[df['datetime'] <= hours_72_cutoff]
            if early_df.empty:
                early_df = df.head(min(10, len(df)))

            post_df = df[df['datetime'] > hours_72_cutoff]

            # Key price points
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

            # 24-hour rolling window for drop detection
            window_hours = 24
            drop_low_tracker = {}

            for i in range(len(df)):
                current_row = df.iloc[i]
                current_ts = current_row['datetime']
                current_px = current_row['price']

                lookback_start = current_ts - timedelta(hours=window_hours)
                window_df = df[(df['datetime'] >= lookback_start) & (df['datetime'] <= current_ts)]

                if len(window_df) > 1:
                    window_peak = window_df['price'].max()

                    if window_peak > 0:
                        drop_pct = (window_peak - current_px) / window_peak

                        # Detect major drops
                        if drop_pct >= 0.5:
                            has_sustained_drop = True

                        if drop_pct >= 0.85:
                            is_early_phase = current_ts <= early_phase_end

                            peak_rows = window_df[window_df['price'] == window_peak]
                            if not peak_rows.empty:
                                peak_time = peak_rows['datetime'].iloc[0]
                                hours_since_peak = (current_ts - peak_time).total_seconds() / 3600
                                is_rapid = hours_since_peak <= self.RUG_RAPID_DROP_HOURS

                                if is_rapid:
                                    rapid_drops_count += 1

                                drop_id = f"{current_ts}_{drop_pct:.3f}"
                                drop_low_tracker[drop_id] = {
                                    'low': current_px,
                                    'time': current_ts,
                                    'drop_pct': drop_pct,
                                    'is_early': is_early_phase,
                                    'is_rapid': is_rapid
                                }

                                price_drops.append((current_ts.to_pydatetime(), drop_pct))

            # Analyse recovery patterns after each drop
            for drop_id, drop_info in drop_low_tracker.items():
                drop_low = drop_info['low']
                drop_time = drop_info['time']

                recovery_end = drop_time + timedelta(days=self.RECOVERY_ANALYSIS_DAYS)
                recovery_df = df[(df['datetime'] > drop_time) & (df['datetime'] <= recovery_end)]

                if not recovery_df.empty:
                    max_price_after = recovery_df['price'].max()
                    recovery_ratio = max_price_after / drop_low if drop_low > 0 else 0

                    max_recovery = max(max_recovery, recovery_ratio)
                    if recovery_ratio >= self.SUCCESS_RECOVERY_MULTIPLIER:
                        has_recovery = True

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

            # Days since last major drop
            days_since_last_drop = None
            if price_drops:
                last_drop_time = max(drop_time for drop_time, _ in price_drops)
                days_since_last_drop = (current_time - pd.to_datetime(last_drop_time)).days

            appreciation_ratio = (post_ath_peak_price / peak_price_72h) if peak_price_72h > 0 else 0

            result = {
                'peak_price_72h': float(peak_price_72h) if peak_price_72h else None,
                'post_ath_peak_price': float(post_ath_peak_price) if post_ath_peak_price else None,
                'current_price': float(current_price) if current_price else None,
                'has_sustained_drop': has_sustained_drop,
                'price_drops': price_drops,
                'appreciation_ratio': appreciation_ratio,
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

    # ------------------------------------------------------------------
    # Classification engine
    # ------------------------------------------------------------------
    def _classify(self, m: TokenMetrics) -> str:
        """Classify a token based on its gathered metrics.

        Priority order:
          1. Inactive detection.
          2. Massive historical appreciation override (10 000x+).
          3. Mega-success (1000x+).
          4. Massive recovery patterns.
          5. Traditional success (10x+ with holders).
          6. Recovery-based success.
          7. Conservative rugpull detection.
          8. Default: unsuccessful.

        Args:
            m: Populated ``TokenMetrics`` for the token.

        Returns:
            One of ``"inactive"``, ``"successful"``, ``"rugpull"``, or
            ``"unsuccessful"``.
        """
        # Check for inactive tokens first
        if self._is_inactive(m):
            return "inactive"

        # Calculate enhanced derived metrics
        self._calculate_enhanced_metrics(m)

        # PRIORITY 1: Tokens with massive historical appreciation (10,000x+)
        if (m.mega_appreciation and m.mega_appreciation >= 10000):
            if (m.current_vs_ath_ratio and m.current_vs_ath_ratio < 0.0001 and
                m.days_since_last_major_drop and m.days_since_last_major_drop < 7 and
                m.current_trend == "declining"):
                pass  # Possible temporary pullback -- fall through
            else:
                self._log_classification_reasoning(m, "successful")
                return "successful"

        # PRIORITY 2: Mega-success (1000x+ with reasonable current price)
        if self._is_mega_success(m):
            self._log_classification_reasoning(m, "successful")
            return "successful"

        # PRIORITY 3: Massive recovery patterns
        if (m.max_recovery_after_drop and m.max_recovery_after_drop >= 1000000 and
            m.mega_appreciation and m.mega_appreciation >= 1000):
            self._log_classification_reasoning(m, "successful")
            return "successful"

        # Traditional success check
        if self._is_traditional_success(m):
            self._log_classification_reasoning(m, "successful")
            return "successful"

        # Recovery-based success check
        if self._is_recovery_success(m):
            self._log_classification_reasoning(m, "successful")
            return "successful"

        # Conservative rugpull detection (skip for high-appreciation tokens)
        if (not m.mega_appreciation or m.mega_appreciation < 100) and self._is_clear_rugpull(m):
            self._log_classification_reasoning(m, "rugpull")
            return "rugpull"

        # Default
        self._log_classification_reasoning(m, "unsuccessful")
        return "unsuccessful"

    # ------------------------------------------------------------------
    # Classification sub-checks
    # ------------------------------------------------------------------
    def _is_inactive(self, m: TokenMetrics) -> bool:
        """Check if token is inactive (never gained meaningful traction).

        Historically successful tokens are never classified as inactive,
        regardless of their current activity level.

        Args:
            m: Token metrics.

        Returns:
            True if the token should be labelled inactive.
        """
        # Never classify tokens with significant historical appreciation
        if m.mega_appreciation and m.mega_appreciation >= 10:
            return False

        if m.has_shown_recovery and m.max_recovery_after_drop and m.max_recovery_after_drop >= 2:
            return False

        if m.holder_count and m.holder_count >= 50:
            return False

        low_appreciation = not m.mega_appreciation or m.mega_appreciation < 10
        very_few_holders = m.holder_count is not None and m.holder_count < 20
        completely_dead = m.volume_24h is not None and m.volume_24h < 10

        return low_appreciation and very_few_holders and completely_dead

    def _is_mega_success(self, m: TokenMetrics) -> bool:
        """Detect mega-successful tokens (1000x+ appreciation).

        Tiered thresholds allow increasingly lenient current-price
        requirements as the appreciation magnitude grows.

        Args:
            m: Token metrics.

        Returns:
            True if the token qualifies as mega-successful.
        """
        if not m.mega_appreciation:
            return False

        # Ultra mega success (100,000x+)
        if m.mega_appreciation >= 100000:
            if not m.current_vs_ath_ratio or m.current_vs_ath_ratio >= 0.00001:
                return True

        # Super mega success (10,000x+)
        if m.mega_appreciation >= 10000:
            if not m.current_vs_ath_ratio or m.current_vs_ath_ratio >= 0.0001:
                return True

        # Regular mega success (1000x+)
        if (m.mega_appreciation >= self.SUCCESS_MEGA_APPRECIATION and
            m.current_vs_ath_ratio and m.current_vs_ath_ratio >= self.SUCCESS_SUSTAINED_HIGH_RATIO):
            return True

        # Borderline cases with high appreciation and good success score
        if (m.mega_appreciation >= 500 and
            m.final_evaluation_score and m.final_evaluation_score >= 0.6):
            return True

        return False

    def _is_traditional_success(self, m: TokenMetrics) -> bool:
        """Check for traditional success: 10x+ appreciation with no major drops.

        Args:
            m: Token metrics.

        Returns:
            True if the token meets traditional success criteria.
        """
        if None in (m.peak_price_72h, m.post_ath_peak_price, m.holder_count):
            return False

        if m.holder_count < self.SUCCESS_MIN_HOLDERS:
            return False

        if (m.post_ath_peak_price / m.peak_price_72h >= self.SUCCESS_APPRECIATION and
            not m.has_sustained_drop):
            return True

        return False

    def _is_recovery_success(self, m: TokenMetrics) -> bool:
        """Check for recovery-based success after major drops.

        More lenient than traditional success -- requires only half
        the normal holder threshold.

        Args:
            m: Token metrics.

        Returns:
            True if the token recovered strongly enough to qualify.
        """
        if not m.has_shown_recovery or not m.max_recovery_after_drop:
            return False

        if (m.max_recovery_after_drop >= self.SUCCESS_RECOVERY_MULTIPLIER and
            m.holder_count and m.holder_count >= self.SUCCESS_MIN_HOLDERS // 2):

            if m.current_trend != "declining":
                return True

        return False

    def _is_clear_rugpull(self, m: TokenMetrics) -> bool:
        """Detect clear coordinated rugpulls with high confidence.

        Requires multiple 85%+ drops, very low current price vs ATH,
        and either rapid coordinated dumps or an extended declining
        pattern with no recovery.

        Args:
            m: Token metrics.

        Returns:
            True only for high-confidence rugpull classifications.
        """
        if not m.price_drops:
            return False

        major_drops = [d for _, d in m.price_drops if d >= self.RUG_THRESHOLD]
        if not major_drops:
            return False

        if m.total_major_drops < self.RUG_MIN_DROPS_FOR_PATTERN:
            return False

        if m.current_vs_ath_ratio and m.current_vs_ath_ratio >= self.RUG_FINAL_PRICE_RATIO:
            return False

        # Multiple rapid coordinated dumps
        if m.rapid_drops_count >= 3:
            return True

        # Many drops with extended non-recovery and declining trend
        if (m.total_major_drops >= 10 and
            m.days_since_last_major_drop and m.days_since_last_major_drop >= self.RUG_NO_RECOVERY_DAYS and
            m.current_trend == "declining"):
            return True

        return False

    # ------------------------------------------------------------------
    # Derived metric calculation
    # ------------------------------------------------------------------
    def _calculate_enhanced_metrics(self, m: TokenMetrics) -> None:
        """Compute derived metrics needed by the classification engine.

        Populates ``mega_appreciation``, ``current_vs_ath_ratio``,
        ``total_major_drops``, and ``final_evaluation_score`` on the
        metrics object.

        Args:
            m: Token metrics to augment in place.
        """
        if m.peak_price_72h and m.post_ath_peak_price and m.peak_price_72h > 0:
            m.mega_appreciation = m.post_ath_peak_price / m.peak_price_72h

        if m.current_price and m.post_ath_peak_price and m.post_ath_peak_price > 0:
            m.current_vs_ath_ratio = m.current_price / m.post_ath_peak_price

        m.total_major_drops = len([d for _, d in m.price_drops if d >= self.RUG_THRESHOLD])

        m.final_evaluation_score = self._calculate_success_score(m)

    def _calculate_success_score(self, m: TokenMetrics) -> float:
        """Calculate a composite success score from multiple factors.

        The score ranges from 0.0 to 1.0 and combines bonuses for
        appreciation, price sustainability, recovery strength, and
        holder count with penalties for excessive drops and declining
        trends.  Penalties are scaled down for tokens with very high
        historical appreciation.

        Args:
            m: Token metrics.

        Returns:
            A float between 0.0 and 1.0.
        """
        score = 0.0

        # Mega appreciation bonus (most important factor)
        if m.mega_appreciation:
            if m.mega_appreciation >= 1000000:
                score += 0.7
            elif m.mega_appreciation >= 100000:
                score += 0.6
            elif m.mega_appreciation >= 10000:
                score += 0.5
            elif m.mega_appreciation >= 1000:
                score += 0.4
            elif m.mega_appreciation >= 100:
                score += 0.3
            elif m.mega_appreciation >= 10:
                score += 0.2

        # Current price vs ATH (sustainability factor)
        if m.current_vs_ath_ratio:
            if m.current_vs_ath_ratio >= 0.5:
                score += 0.2
            elif m.current_vs_ath_ratio >= 0.1:
                score += 0.15
            elif m.current_vs_ath_ratio >= 0.01:
                score += 0.1
            elif m.current_vs_ath_ratio >= 0.001:
                score += 0.05

        # Recovery pattern bonus
        if m.has_shown_recovery and m.max_recovery_after_drop:
            if m.max_recovery_after_drop >= 1000000:
                score += 0.2
            elif m.max_recovery_after_drop >= 100000:
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

        # Penalty for excessive drops (scaled by appreciation)
        if m.total_major_drops and m.mega_appreciation:
            penalty_scale = 1.0
            if m.mega_appreciation >= 10000:
                penalty_scale = 0.1
            elif m.mega_appreciation >= 1000:
                penalty_scale = 0.3
            elif m.mega_appreciation >= 100:
                penalty_scale = 0.6

            if m.total_major_drops >= 20:
                score -= 0.2 * penalty_scale
            elif m.total_major_drops >= 10:
                score -= 0.1 * penalty_scale
            elif m.total_major_drops >= 5:
                score -= 0.05 * penalty_scale

        # Current trend bonus / penalty
        if m.current_trend == "recovering":
            score += 0.05
        elif m.current_trend == "declining":
            penalty = 0.1
            if m.mega_appreciation and m.mega_appreciation >= 1000:
                penalty = 0.02
            score -= penalty

        return max(0.0, min(1.0, score))

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    def _log_classification_reasoning(self, m: TokenMetrics, label: str) -> None:
        """Log detailed reasoning behind a classification decision.

        Args:
            m: The token metrics used for classification.
            label: The assigned label string.
        """
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
            logger.info(f"  -> SUCCESS due to: {', '.join(reasons) if reasons else 'traditional criteria'}")

        elif label == "rugpull":
            reasons = []
            if m.rapid_drops_count >= 3:
                reasons.append(f"multiple coordinated dumps ({m.rapid_drops_count})")
            if m.total_major_drops >= 10:
                reasons.append(f"excessive drops ({m.total_major_drops})")
            if m.current_vs_ath_ratio and m.current_vs_ath_ratio < 0.01:
                reasons.append(f"collapsed price ({m.current_vs_ath_ratio:.4%} of ATH)")
            logger.info(f"  -> RUGPULL due to: {', '.join(reasons)}")

        elif label == "unsuccessful":
            logger.info(f"  -> UNSUCCESSFUL: Doesn't meet success criteria but not clear rugpull")

    # ...existing code...

# ==============================================================================
# CLI entry point
# ==============================================================================
def main() -> None:
    """Parse arguments and run the real on-chain token labeler."""
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
