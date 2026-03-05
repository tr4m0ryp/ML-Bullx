"""
On-chain Solana data provider with multiple API key support.
"""
from __future__ import annotations

import asyncio
import aiohttp
import logging
import time
import sys
import os
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import json
import base58
import pandas as pd

from on_chain_solana_pipeline.api_key_manager import get_key_manager
from on_chain_solana_pipeline.config.config_loader import load_config, PipelineConfig

logger = logging.getLogger(__name__)


@dataclass
class PriceData:
    price: float
    volume_24h: float
    market_cap: Optional[float] = None
    timestamp: datetime = None


@dataclass 
class HistoricalData:
    ohlcv: List[Dict[str, Any]]  # List of {ts, o, h, l, c, v}
    launch_price: Optional[float] = None
    peak_price_72h: Optional[float] = None
    post_ath_peak_price: Optional[float] = None


class OnChainDataProvider:
    """
    Provides token data directly from Solana blockchain and local TimescaleDB.
    Now supports multiple Helius API keys with automatic rotation and direct
    on-chain transaction analysis.
    """
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.rpc_client = None
        self.db_pool = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.key_manager = get_key_manager()
        
        for key in config.rpc.helius_keys:
            self.key_manager.add_key(key)
        
        self._price_cache: Dict[str, Tuple[PriceData, float]] = {}
        self._holder_cache: Dict[str, Tuple[int, float]] = {}
        self._activity_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}

    async def __aenter__(self):
        try:
            from solana.rpc.async_api import AsyncClient
            helius_key = self.key_manager.get_next_available_key()
            if helius_key:
                helius_url = f"{self.config.rpc.helius_url}/?api-key={helius_key}"
                self.rpc_client = AsyncClient(helius_url)
                logger.info("Using Helius RPC endpoint for enhanced queries")
            else:
                self.rpc_client = AsyncClient(self.config.rpc.url)
                logger.warning("No Helius keys available, using public RPC")
        except ImportError:
            logger.warning("solana package not installed. RPC features will be limited.")
        
        self.db_pool = None
        try:
            import asyncpg
            logger.info("Attempting to create database pool...")
            self.db_pool = await asyncpg.create_pool(self.config.database.dsn)
            logger.info("Database pool created successfully")
        except ImportError:
            logger.warning("asyncpg not installed. Database features will not work.")
        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            self.db_pool = None
        
        logger.info("Creating HTTP session...")
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        logger.info("OnChainDataProvider initialization complete")
        return self
    
    async def __aexit__(self, *exc):
        if self.rpc_client:
            await self.rpc_client.close()
        if self.db_pool:
            await self.db_pool.close()
        if self.session:
            await self.session.close()
    
    async def _make_helius_request(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        api_key = await self.key_manager.wait_for_available_key(max_wait_time=30)
        if not api_key:
            logger.error("No Helius API keys available")
            return None
        
        url = f"{self.config.rpc.helius_url}/?api-key={api_key}"
        
        try:
            async with self.session.post(url, json=payload) as response:
                if response.status == 429:
                    self.key_manager.record_request_failure(api_key, is_rate_limit=True)
                    logger.warning(f"Helius API key rate limited: {api_key[:8]}...")
                    return None
                
                if response.status == 200:
                    self.key_manager.record_request_success(api_key)
                    return await response.json()
                else:
                    self.key_manager.record_request_failure(api_key)
                    logger.warning(f"Helius API error {response.status}")
                    return None
                    
        except Exception as e:
            self.key_manager.record_request_failure(api_key)
            logger.error(f"Error making Helius request: {e}")
            return None

    async def get_current_price(self, mint: str) -> Optional[PriceData]:
        logger.info(f"Getting current price for {mint}")
        
        cache_key = f"price_{mint}"
        if cache_key in self._price_cache:
            data, cached_at = self._price_cache[cache_key]
            if time.time() - cached_at < self.config.cache.price_cache_ttl:
                logger.info(f"Returning cached price for {mint}")
                return data
        
        if self.db_pool:
            async with self.db_pool.acquire() as conn:
                latest_tick = await conn.fetchrow("SELECT price, volume_usd, ts FROM swap_ticks WHERE mint = $1 ORDER BY ts DESC LIMIT 1", mint)
                if latest_tick:
                    volume_24h_result = await conn.fetchval("SELECT COALESCE(SUM(volume_usd), 0) FROM swap_ticks WHERE mint = $1 AND ts >= NOW() - INTERVAL '24 hours'", mint)
                    price_data = PriceData(price=float(latest_tick['price']), volume_24h=float(volume_24h_result or 0), timestamp=latest_tick['ts'])
                    self._price_cache[cache_key] = (price_data, time.time())
                    logger.info(f"Found database price for {mint}: ${price_data.price}")
                    return price_data
        
        logger.info(f"No database price for {mint}, analyzing transactions directly.")
        activity_data = await self._analyze_token_activity(mint)
        if activity_data and activity_data.get('current_price'):
            price_data = PriceData(
                price=activity_data['current_price'],
                volume_24h=activity_data.get('volume_24h', 0.0),
                timestamp=datetime.now()
            )
            self._price_cache[cache_key] = (price_data, time.time())
            return price_data

        logger.info(f"No price from transactions, trying external APIs for {mint}")
        price_data = await self._get_external_price_data(mint)
        if price_data:
            self._price_cache[cache_key] = (price_data, time.time())
            return price_data
        
        logger.warning(f"No price data found for {mint}")
        return None

    async def get_historical_data(self, mint: str, days: int = 17) -> Optional[HistoricalData]:
        if self.db_pool:
            async with self.db_pool.acquire() as conn:
                ohlcv_data = await conn.fetch(f"""
                    SELECT EXTRACT(epoch FROM bucket) as ts, open, high, low, close, volume_usd as volume
                    FROM ohlcv_5m WHERE mint = $1 AND bucket >= NOW() - INTERVAL '{days} days'
                    ORDER BY bucket ASC
                """, mint)
                if ohlcv_data:
                    # ... (code to process DB ohlcv data)
                    pass # Placeholder for original logic

        logger.info(f"No database history for {mint}, analyzing transactions directly.")
        activity_data = await self._analyze_token_activity(mint)
        if activity_data and activity_data.get('ohlcv'):
            return HistoricalData(
                ohlcv=activity_data['ohlcv'],
                peak_price_72h=activity_data.get('peak_price_72h'),
                post_ath_peak_price=activity_data.get('post_ath_peak_price')
            )
        
        logger.warning(f"Could not build historical data for {mint}")
        return None

    async def get_holder_count(self, mint: str) -> Optional[int]:
        cache_key = f"holders_{mint}"
        if cache_key in self._holder_cache:
            count, cached_at = self._holder_cache[cache_key]
            if time.time() - cached_at < self.config.cache.holder_cache_ttl:
                return count
        
        if self.db_pool:
            async with self.db_pool.acquire() as conn:
                recent_snapshot = await conn.fetchval("SELECT holder_count FROM holder_snapshots WHERE mint = $1 ORDER BY snapshot_time DESC LIMIT 1", mint)
                if recent_snapshot:
                    self._holder_cache[cache_key] = (recent_snapshot, time.time())
                    return recent_snapshot
        
        holder_count = await self._get_holders_via_program_accounts(mint)
        if holder_count is not None:
            self._holder_cache[cache_key] = (holder_count, time.time())
            if self.db_pool:
                try:
                    async with self.db_pool.acquire() as conn:
                        await conn.execute("INSERT INTO holder_snapshots (mint, snapshot_time, holder_count) VALUES ($1, NOW(), $2) ON CONFLICT (mint, snapshot_time) DO UPDATE SET holder_count = $2", mint, holder_count)
                except Exception as e:
                    logger.debug(f"Failed to store holder snapshot for {mint}: {e}")
        return holder_count

    async def get_transaction_count(self, mint: str) -> Optional[int]:
        """Get transaction count for a token using getSignaturesForAddress API."""
        cache_key = f"tx_count_{mint}"
        if cache_key in self._holder_cache:  # Reuse holder cache for tx counts
            count, cached_at = self._holder_cache[cache_key]
            if time.time() - cached_at < self.config.cache.holder_cache_ttl:
                return count
        
        logger.info(f"Getting transaction count for: {mint}")
        try:
            # Get all signatures for this mint address
            signatures = await self._get_signatures_for_address(mint, get_all=True)
            if signatures is None:
                logger.warning(f"Could not get signatures for {mint}")
                return None
            
            transaction_count = len(signatures)
            logger.info(f"Found {transaction_count} transactions for {mint}")
            
            # Cache the result
            self._holder_cache[cache_key] = (transaction_count, time.time())
            return transaction_count
            
        except Exception as e:
            logger.error(f"Error getting transaction count for {mint}: {e}")
            return None

    async def _get_holders_via_program_accounts(self, mint: str) -> Optional[int]:
        logger.info(f"Attempting to get holder count for: {mint} via getProgramAccounts")
        try:
            payload = {
                "jsonrpc": "2.0", "id": "program-accounts", "method": "getProgramAccounts",
                "params": [
                    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                    {"encoding": "jsonParsed", "filters": [{"dataSize": 165}, {"memcmp": {"offset": 0, "bytes": mint}}]}
                ]
            }
            response = await self._make_helius_request(payload)
            if response and "result" in response:
                unique_holders = set()
                for acc in response["result"]:
                    try:
                        info = acc["account"]["data"]["parsed"]["info"]
                        if float(info["tokenAmount"]["amount"]) > 0:
                            unique_holders.add(info["owner"])
                    except Exception: continue
                logger.info(f"Found {len(unique_holders)} holders for {mint} via getProgramAccounts")
                return len(unique_holders)
            logger.warning(f"Could not determine holder count for {mint}")
            return None
        except Exception as e:
            logger.error(f"Error in getProgramAccounts for {mint}: {e}")
            return None

    async def _analyze_token_activity(self, mint: str) -> Optional[Dict[str, Any]]:
        cache_key = f"activity_{mint}"
        if cache_key in self._activity_cache:
            data, cached_at = self._activity_cache[cache_key]
            if time.time() - cached_at < self.config.cache.price_cache_ttl:
                logger.info(f"Returning cached activity for {mint}")
                return data

        logger.info(f"Performing full on-chain activity analysis for {mint}")
        signatures = await self._get_signatures_for_address(mint, get_all=True)
        if not signatures:
            logger.info(f"No signatures found for {mint}")
            return None
        
        all_swaps = []
        price_history = []
        batch_size = 20
        max_tx = min(len(signatures), 500)

        logger.info(f"Analyzing {max_tx} transactions for {mint} in batches of {batch_size}")
        for i in range(0, max_tx, batch_size):
            batch_sigs = signatures[i:i + batch_size]
            tasks = [self._get_transaction_details(sig) for sig in batch_sigs]
            transactions = await asyncio.gather(*tasks, return_exceptions=True)
            
            for tx in transactions:
                if isinstance(tx, dict) and tx and self._is_swap_transaction(tx):
                    swap_info = self._parse_swap_details(tx, mint)
                    if swap_info:
                        all_swaps.append(swap_info)
                        if 'timestamp' in swap_info and 'price' in swap_info:
                            price_history.append({'timestamp': swap_info['timestamp'], 'price': swap_info['price'], 'volume': swap_info.get('volume_usd', 0)})
            await asyncio.sleep(0.3)
        
        logger.info(f"Collected {len(all_swaps)} swaps and {len(price_history)} price points for {mint}")
        if not price_history:
            logger.warning(f"No price history could be built from swaps for {mint}")
            return None

        analysis = self._build_history_from_swaps(price_history, mint)
        logger.info(f"Built historical analysis for {mint}: {analysis.keys()}")
        self._activity_cache[cache_key] = (analysis, time.time())
        return analysis

    async def _get_signatures_for_address(self, mint: str, limit: int = 1000, get_all: bool = True) -> List[str]:
        all_signatures = []
        before = None
        max_total = 10000
        
        while len(all_signatures) < max_total:
            params = [mint, {"limit": min(limit, 1000), "commitment": "finalized", "searchTransactionHistory": True}]
            if before:
                params[1]["before"] = before
            
            payload = {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": params}
            result = await self._make_helius_request(payload)
            
            if not result or "result" not in result or not result["result"]:
                break
            
            batch_signatures = [sig["signature"] for sig in result["result"]]
            if not batch_signatures:
                break
            
            all_signatures.extend(batch_signatures)
            before = batch_signatures[-1]
            
            if not batch_signatures or (not get_all and len(batch_signatures) < min(limit, 1000)):
                break
            await asyncio.sleep(0.5)
        
        logger.info(f"Collected {len(all_signatures)} signatures for {mint}")
        return all_signatures

    async def _get_transaction_details(self, signature: str) -> Optional[Dict[str, Any]]:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]}
        result = await self._make_helius_request(payload)
        return result.get("result") if result else None

    def _is_swap_transaction(self, tx: Dict[str, Any]) -> bool:
        if not tx.get("meta") or tx["meta"].get("err") or not tx["meta"].get("postTokenBalances"):
            return False
        return True

    def _parse_swap_details(self, tx: Dict[str, Any], mint: str) -> Optional[Dict[str, Any]]:
        try:
            meta = tx.get("meta", {})
            pre_balances = {bal['mint']: bal['uiTokenAmount']['uiAmount'] for bal in meta.get("preTokenBalances", []) if bal.get('uiTokenAmount')}
            post_balances = {bal['mint']: bal['uiTokenAmount']['uiAmount'] for bal in meta.get("postTokenBalances", []) if bal.get('uiTokenAmount')}
            
            token_change = abs(post_balances.get(mint, 0) - pre_balances.get(mint, 0))
            if token_change == 0: return None

            sol_change = 0
            for i, pre_bal in enumerate(meta.get("preBalances", [])):
                post_bal = meta.get("postBalances", [])[i]
                if abs(post_bal - pre_bal) > 1000: # Ignore small fee changes
                    sol_change = abs(post_bal - pre_bal) / 1e9
                    break
            
            if sol_change > 0:
                price = sol_change / token_change
                # Simple SOL price estimate
                sol_price_usd = 150
                return {"timestamp": tx.get("blockTime"), "price": price * sol_price_usd, "volume_usd": sol_change * sol_price_usd}
            return None
        except Exception:
            return None

    def _build_history_from_swaps(self, price_history: List[Dict[str, Any]], mint: str) -> Dict[str, Any]:
        logger.debug(f"_build_history_from_swaps for {mint}: Received {len(price_history)} price points.")
        if not price_history:
            logger.debug(f"_build_history_from_swaps for {mint}: price_history is empty.")
            return {}
        
        df = pd.DataFrame(price_history)
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
        df.sort_values('datetime', inplace=True)
        logger.debug(f"_build_history_from_swaps for {mint}: DataFrame head:\n{df.head()}")
        
        # Resample to 5-minute OHLCV
        ohlcv = df.set_index('datetime')['price'].resample('5min').ohlc().dropna()
        volume = df.set_index('datetime')['volume'].resample('5min').sum().dropna()
        ohlcv = ohlcv.join(volume).rename(columns={'volume': 'v', 'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c'})
        ohlcv['ts'] = ohlcv.index.astype(int) // 10**9
        logger.debug(f"_build_history_from_swaps for {mint}: OHLCV head:\n{ohlcv.head()}")
        
        launch_time = df['datetime'].min()
        hours_72_cutoff = launch_time + timedelta(hours=72)
        
        early_df = df[df['datetime'] <= hours_72_cutoff]
        post_df = df[df['datetime'] > hours_72_cutoff]
        logger.debug(f"_build_history_from_swaps for {mint}: early_df empty: {early_df.empty}, post_df empty: {post_df.empty}")
        
        # Calculate all-time high (ATH) from entire dataset
        all_time_high = df['price'].max() if not df.empty else None
        
        # Peak price within 72h of launch
        peak_price_72h = early_df['price'].max() if not early_df.empty else None
        
        # For post_ath_peak_price, use the all-time high from the entire dataset
        # This represents the highest price the token ever reached
        post_ath_peak_price = all_time_high
        
        result = {
            'ohlcv': ohlcv.reset_index().to_dict('records'),
            'launch_price': df['price'].iloc[0] if not df.empty else None,
            'peak_price_72h': peak_price_72h,
            'post_ath_peak_price': post_ath_peak_price,
            'current_price': df['price'].iloc[-1] if not df.empty else None,
            'volume_24h': df[df['datetime'] >= datetime.now() - timedelta(hours=24)]['volume'].sum()
        }
        logger.debug(f"_build_history_from_swaps for {mint}: Returning result: {result.keys()}")
        return result

    async def _get_external_price_data(self, mint: str) -> Optional[PriceData]:
        # This method remains as a final fallback
        try:
            jupiter_url = f"https://price.jup.ag/v4/price?ids={mint}"
            async with self.session.get(jupiter_url) as response:
                if response.status == 200:
                    data = await response.json()
                    if "data" in data and mint in data["data"] and data["data"][mint].get("price"):
                        price = float(data["data"][mint]["price"])
                        logger.info(f"Found Jupiter API price for {mint}: ${price}")
                        return PriceData(price=price, volume_24h=0.0, timestamp=datetime.now())
        except Exception as e:
            logger.debug(f"Error with Jupiter API for {mint}: {e}")
        
        logger.debug(f"No external price data found for {mint}")
        return None