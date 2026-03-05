"""
Real-time swap ingestion consumer for Helius with multi-key rotation.

- Continuously polls the Helius enhanced transactions API for recent
  Jupiter v6 swap transactions on Solana.
- Rotates through multiple API keys automatically using the shared
  ``HeliusAPIKeyManager``, handling 429 rate-limit responses and
  per-key cooldowns transparently.
- Parses raw transactions via ``SwapParser`` and stores the resulting
  ``SwapTick`` records into TimescaleDB with conflict-safe upserts.
- Falls back to basic RPC polling when no Helius keys are configured.
- Logs per-key usage statistics every five minutes for observability.

Author: ML-Bullx Team
Date:   2025-08-01
"""

# ==============================================================================
# Standard library imports
# ==============================================================================
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

# ==============================================================================
# Third-party imports
# ==============================================================================
import aiohttp
from dataclasses import dataclass

# ==============================================================================
# Local imports
# ==============================================================================
from on_chain_solana_pipeline.api_key_manager import HeliusAPIKeyManager, get_key_manager
from on_chain_solana_pipeline.config.config_loader import load_config
from on_chain_solana_pipeline.swap_parser import SwapParser

logger = logging.getLogger(__name__)


# ==============================================================================
# Data structures
# ==============================================================================
@dataclass
class SwapTick:
    """A single swap event extracted from a Solana transaction."""

    mint: str                             # SPL token mint address
    price: float                          # Swap price in USD
    volume_usd: float                     # Trade volume in USD
    timestamp: datetime                   # Block timestamp of the swap
    source: str                           # DEX source (e.g. "jupiter", "raydium")
    tx_signature: str                     # On-chain transaction signature


# ==============================================================================
# Consumer class
# ==============================================================================
class HeliusSwapConsumer:
    """Consumes swap transactions from Helius with automatic key rotation.

    Connects to the Helius RPC gateway, fetches recent Jupiter v6
    transaction signatures, retrieves full transaction details, parses
    swap data, and stores results in TimescaleDB.

    Attributes:
        config: Pipeline configuration.
        key_manager: Shared Helius API key manager.
        swap_parser: Parser that extracts swap ticks from raw transactions.
        request_count: Running total of HTTP requests made.
    """

    def __init__(self, config_path: str = None):
        """Initialise the consumer, loading configuration and registering keys.

        Args:
            config_path: Optional path to a YAML config file.  When
                None the default config location is used.
        """
        self.config = load_config(config_path)
        self.db_pool = None
        self.swap_parser = SwapParser(self.config)
        self.key_manager = get_key_manager()

        # Add keys from config to manager
        for key in self.config.rpc.helius_keys:
            self.key_manager.add_key(key)

        # Request tracking
        self.request_count = 0
        self.last_stats_log = time.time()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self):
        """Start the consumer loop.

        Creates a database connection pool and enters the main
        consumption loop.  Falls back to RPC polling if no Helius
        keys are available.
        """
        try:
            import asyncpg
            self.db_pool = await asyncpg.create_pool(self.config.database.dsn)
        except ImportError:
            logger.error("asyncpg not installed. Install with: pip install asyncpg")
            return

        logger.info(f"Starting Helius consumer with {len(self.config.rpc.helius_keys)} API keys")

        if self.config.rpc.helius_keys:
            await self._consume_helius_transactions()
        else:
            logger.warning("No Helius keys configured, using RPC polling instead")
            await self._poll_recent_transactions()

    # ------------------------------------------------------------------
    # Main consumption loop
    # ------------------------------------------------------------------
    async def _consume_helius_transactions(self):
        """Poll Helius for recent swap transactions with key rotation.

        Runs indefinitely, rotating API keys on each iteration and
        backing off on failures.
        """
        session_timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(timeout=session_timeout) as session:
            while True:
                try:
                    # Get next available API key
                    api_key = await self.key_manager.wait_for_available_key(max_wait_time=60)
                    if not api_key:
                        logger.error("No API keys available, sleeping for 60 seconds")
                        await asyncio.sleep(60)
                        continue

                    # Build URL with current API key
                    url = f"{self.config.rpc.helius_url}/?api-key={api_key}"

                    # Get recent transactions for Jupiter V6
                    success = await self._fetch_recent_transactions(session, url, api_key)

                    if success:
                        self.key_manager.record_request_success(api_key)
                        await asyncio.sleep(1)  # Rate limiting
                    else:
                        await asyncio.sleep(5)  # Back off on failure

                    # Log stats periodically
                    await self._log_stats_if_needed()

                except Exception as e:
                    logger.error(f"Error in transaction consumption: {e}")
                    await asyncio.sleep(30)

    # ------------------------------------------------------------------
    # Transaction fetching
    # ------------------------------------------------------------------
    async def _fetch_recent_transactions(self, session: aiohttp.ClientSession,
                                       url: str, api_key: str) -> bool:
        """Fetch recent Jupiter v6 transaction signatures and process them.

        Args:
            session: The ``aiohttp`` client session.
            url: Helius RPC URL with API key appended.
            api_key: The raw API key (for failure recording).

        Returns:
            True if the request succeeded (even if no transactions were
            found), False on HTTP or network errors.
        """
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [
                    self.config.programs.jupiter_v6,
                    {"limit": 50}  # Smaller batch for better rotation
                ]
            }

            async with session.post(url, json=payload) as response:
                self.request_count += 1

                if response.status == 429:
                    self.key_manager.record_request_failure(api_key, is_rate_limit=True)
                    logger.warning(f"Rate limited on key {api_key[:8]}...")
                    return False

                if response.status != 200:
                    self.key_manager.record_request_failure(api_key)
                    logger.warning(f"HTTP {response.status} for key {api_key[:8]}...")
                    return False

                data = await response.json()

                if "result" in data and data["result"]:
                    signatures = [sig["signature"] for sig in data["result"][:10]]
                    await self._process_transaction_batch(session, signatures, api_key)
                    return True
                else:
                    logger.debug("No recent transactions found")
                    return True

        except Exception as e:
            self.key_manager.record_request_failure(api_key)
            logger.error(f"Error fetching transactions with key {api_key[:8]}...: {e}")
            return False

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------
    async def _process_transaction_batch(self, session: aiohttp.ClientSession,
                                       signatures: List[str], api_key: str):
        """Retrieve and parse a batch of transactions by signature.

        Switches to a fresh API key mid-batch if the current one
        becomes unavailable.

        Args:
            session: The ``aiohttp`` client session.
            signatures: Transaction signatures to process.
            api_key: The currently active API key.
        """
        url = f"{self.config.rpc.helius_url}/?api-key={api_key}"

        for signature in signatures:
            try:
                # Check if we still have this key available
                if not self.key_manager.get_next_available_key():
                    new_key = await self.key_manager.wait_for_available_key(max_wait_time=10)
                    if new_key and new_key != api_key:
                        url = f"{self.config.rpc.helius_url}/?api-key={new_key}"
                        api_key = new_key

                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTransaction",
                    "params": [
                        signature,
                        {
                            "encoding": "jsonParsed",
                            "maxSupportedTransactionVersion": 0
                        }
                    ]
                }

                async with session.post(url, json=payload) as response:
                    self.request_count += 1

                    if response.status == 429:
                        self.key_manager.record_request_failure(api_key, is_rate_limit=True)
                        break  # Stop processing this batch

                    if response.status == 200:
                        tx_data = await response.json()
                        self.key_manager.record_request_success(api_key)

                        if "result" in tx_data and tx_data["result"]:
                            swap_ticks = await self.swap_parser.parse_transaction(tx_data["result"])
                            if swap_ticks:
                                await self._store_swap_ticks(swap_ticks)
                    else:
                        self.key_manager.record_request_failure(api_key)
                        logger.debug(f"HTTP {response.status} for transaction {signature}")

                # Small delay between transaction requests
                await asyncio.sleep(0.1)

            except Exception as e:
                self.key_manager.record_request_failure(api_key)
                logger.error(f"Error processing transaction {signature}: {e}")
                continue

    # ------------------------------------------------------------------
    # Fallback polling
    # ------------------------------------------------------------------
    async def _poll_recent_transactions(self):
        """Fallback polling loop using the public Solana RPC endpoint.

        Runs when no Helius API keys are configured.  Currently a
        placeholder that logs a reminder to configure keys.
        """
        logger.info("Starting RPC polling mode (fallback)")
        while True:
            try:
                logger.info("RPC polling not implemented - please configure Helius API keys")
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Error in RPC polling: {e}")
                await asyncio.sleep(60)

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------
    async def _store_swap_ticks(self, ticks: List[SwapTick]):
        """Batch-insert swap ticks into TimescaleDB.

        Uses ``ON CONFLICT DO NOTHING`` to silently skip duplicate
        entries identified by the ``(tx_signature, mint)`` unique
        constraint.

        Args:
            ticks: The swap tick records to persist.
        """
        if not ticks or not self.db_pool:
            return

        try:
            async with self.db_pool.acquire() as conn:
                values = [
                    (tick.timestamp, tick.mint, tick.price, tick.volume_usd,
                     tick.source, tick.tx_signature)
                    for tick in ticks
                ]

                await conn.executemany("""
                    INSERT INTO swap_ticks (ts, mint, price, volume_usd, source, tx_signature)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (tx_signature, mint) DO NOTHING
                """, values)

                logger.info(f"Stored {len(values)} swap ticks")

        except Exception as e:
            logger.error(f"Error storing swap ticks: {e}")

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    async def _log_stats_if_needed(self):
        """Log API key usage statistics every five minutes."""
        current_time = time.time()
        if current_time - self.last_stats_log > 300:
            stats = self.key_manager.get_usage_stats()
            healthy_keys = self.key_manager.get_healthy_key_count()

            logger.info(f"=== API Key Stats (Total Requests: {self.request_count}) ===")
            logger.info(f"Healthy Keys: {healthy_keys}/{len(self.key_manager.api_keys)}")

            for masked_key, key_stats in stats.items():
                logger.info(f"Key {masked_key}: {key_stats['total_requests']} req, "
                          f"{key_stats['success_rate']:.1f}% success, "
                          f"{'RATE LIMITED' if key_stats['is_rate_limited'] else 'OK'}")

            self.last_stats_log = current_time


# ==============================================================================
# CLI entry point
# ==============================================================================
async def main():
    """Parse command-line arguments, configure logging, and start the consumer."""
    import argparse

    parser = argparse.ArgumentParser(description="Helius swap consumer with multi-key rotation")
    parser.add_argument("--config", help="Path to config file")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    consumer = HeliusSwapConsumer(args.config)
    await consumer.start()


if __name__ == "__main__":
    asyncio.run(main())
