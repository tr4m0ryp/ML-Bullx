"""
Real-time swap ingestion from Helius with multiple API key rotation.
Parses Jupiter and DEX swaps, stores tick data in TimescaleDB.
"""
import asyncio
import aiohttp
import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass

from on_chain_solana_pipeline.api_key_manager import HeliusAPIKeyManager, get_key_manager
from on_chain_solana_pipeline.config.config_loader import load_config
from on_chain_solana_pipeline.swap_parser import SwapParser

logger = logging.getLogger(__name__)


@dataclass
class SwapTick:
    mint: str
    price: float
    volume_usd: float
    timestamp: datetime
    source: str
    tx_signature: str


class HeliusSwapConsumer:
    """
    Consumes swap transactions from Helius using multiple API keys with rotation.
    """
    
    def __init__(self, config_path: str = None):
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
        
    async def start(self):
        """Start the consumer."""
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
    
    async def _consume_helius_transactions(self):
        """
        Consume transactions via Helius enhanced transactions API with key rotation.
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
    
    async def _fetch_recent_transactions(self, session: aiohttp.ClientSession, 
                                       url: str, api_key: str) -> bool:
        """Fetch recent transactions for Jupiter program."""
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
                
                if response.status == 429:  # Rate limited
                    self.key_manager.record_request_failure(api_key, is_rate_limit=True)
                    logger.warning(f"Rate limited on key {api_key[:8]}...")
                    return False
                
                if response.status != 200:
                    self.key_manager.record_request_failure(api_key)
                    logger.warning(f"HTTP {response.status} for key {api_key[:8]}...")
                    return False
                
                data = await response.json()
                
                if "result" in data and data["result"]:
                    signatures = [sig["signature"] for sig in data["result"][:10]]  # Process fewer at once
                    await self._process_transaction_batch(session, signatures, api_key)
                    return True
                else:
                    logger.debug("No recent transactions found")
                    return True
                    
        except Exception as e:
            self.key_manager.record_request_failure(api_key)
            logger.error(f"Error fetching transactions with key {api_key[:8]}...: {e}")
            return False
    
    async def _process_transaction_batch(self, session: aiohttp.ClientSession, 
                                       signatures: List[str], api_key: str):
        """Process a batch of transaction signatures."""
        url = f"{self.config.rpc.helius_url}/?api-key={api_key}"
        
        for signature in signatures:
            try:
                # Check if we still have this key available
                if not self.key_manager.get_next_available_key():
                    # Switch to a different key if current one is exhausted
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
    
    async def _poll_recent_transactions(self):
        """Fallback method using direct RPC polling."""
        logger.info("Starting RPC polling mode (fallback)")
        while True:
            try:
                # This would implement basic RPC polling as fallback
                logger.info("RPC polling not implemented - please configure Helius API keys")
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Error in RPC polling: {e}")
                await asyncio.sleep(60)
    
    async def _store_swap_ticks(self, ticks: List[SwapTick]):
        """Store swap ticks in the database."""
        if not ticks or not self.db_pool:
            return
            
        try:
            async with self.db_pool.acquire() as conn:
                # Batch insert with conflict handling
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
    
    async def _log_stats_if_needed(self):
        """Log statistics periodically."""
        current_time = time.time()
        if current_time - self.last_stats_log > 300:  # Every 5 minutes
            stats = self.key_manager.get_usage_stats()
            healthy_keys = self.key_manager.get_healthy_key_count()
            
            logger.info(f"=== API Key Stats (Total Requests: {self.request_count}) ===")
            logger.info(f"Healthy Keys: {healthy_keys}/{len(self.key_manager.api_keys)}")
            
            for masked_key, key_stats in stats.items():
                logger.info(f"Key {masked_key}: {key_stats['total_requests']} req, "
                          f"{key_stats['success_rate']:.1f}% success, "
                          f"{'RATE LIMITED' if key_stats['is_rate_limited'] else 'OK'}")
            
            self.last_stats_log = current_time


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Helius swap consumer with multi-key rotation")
    parser.add_argument("--config", help="Path to config file")
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    consumer = HeliusSwapConsumer(args.config)
    await consumer.start()


if __name__ == "__main__":
    asyncio.run(main())
