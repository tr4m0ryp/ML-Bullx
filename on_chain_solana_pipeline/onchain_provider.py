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

# Add current directory to path
pipeline_dir = os.path.dirname(__file__)
sys.path.insert(0, pipeline_dir)

from api_key_manager import get_key_manager
from config.config_loader import load_config, PipelineConfig

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
    peak_price_72h: Optional[float] = None
    post_ath_peak_price: Optional[float] = None


class OnChainDataProvider:
    """
    Provides token data directly from Solana blockchain and local TimescaleDB.
    Now supports multiple Helius API keys with automatic rotation.
    """
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.rpc_client = None
        self.db_pool = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.key_manager = get_key_manager()
        
        # Add configured keys to manager
        for key in config.rpc.helius_keys:
            self.key_manager.add_key(key)
        
        # Simple in-memory cache
        self._price_cache: Dict[str, Tuple[PriceData, float]] = {}
        self._holder_cache: Dict[str, Tuple[int, float]] = {}
    
    async def __aenter__(self):
        """Async context manager entry."""
        try:
            from solana.rpc.async_api import AsyncClient
            self.rpc_client = AsyncClient(self.config.rpc.url)
        except ImportError:
            logger.warning("solana package not installed. RPC features will be limited.")
        
        try:
            import asyncpg
            self.db_pool = await asyncpg.create_pool(self.config.database.dsn)
        except ImportError:
            logger.error("asyncpg not installed. Database features will not work.")
        
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *exc):
        """Async context manager exit."""
        if self.rpc_client:
            await self.rpc_client.close()
        if self.db_pool:
            await self.db_pool.close()
        if self.session:
            await self.session.close()
    
    async def _make_helius_request(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Make a request to Helius with automatic key rotation."""
        if not self.config.rpc.helius_keys:
            logger.warning("No Helius API keys configured")
            return None
        
        # Get next available API key
        api_key = await self.key_manager.wait_for_available_key(max_wait_time=30)
        if not api_key:
            logger.error("No Helius API keys available")
            return None
        
        url = f"{self.config.rpc.helius_url}/?api-key={api_key}"
        
        try:
            async with self.session.post(url, json=payload) as response:
                if response.status == 429:  # Rate limited
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
        """Get current price for a token mint with enhanced API support."""
        # Check cache first
        cache_key = f"price_{mint}"
        if cache_key in self._price_cache:
            data, cached_at = self._price_cache[cache_key]
            if time.time() - cached_at < self.config.cache.price_cache_ttl:
                return data
        
        try:
            # Try database first for recent data
            if self.db_pool:
                async with self.db_pool.acquire() as conn:
                    latest_tick = await conn.fetchrow("""
                        SELECT price, volume_usd, ts
                        FROM swap_ticks 
                        WHERE mint = $1 
                        ORDER BY ts DESC 
                        LIMIT 1
                    """, mint)
                    
                    if latest_tick:
                        # Get 24h volume
                        volume_24h_result = await conn.fetchval("""
                            SELECT COALESCE(SUM(volume_usd), 0)
                            FROM swap_ticks 
                            WHERE mint = $1 
                            AND ts >= NOW() - INTERVAL '24 hours'
                        """, mint)
                        
                        price_data = PriceData(
                            price=float(latest_tick['price']),
                            volume_24h=float(volume_24h_result or 0),
                            timestamp=latest_tick['ts']
                        )
                        
                        # Cache the result
                        self._price_cache[cache_key] = (price_data, time.time())
                        return price_data
            
            # Fallback to RPC-derived price if no database data
            return await self._get_pool_derived_price(mint)
                
        except Exception as e:
            logger.error(f"Error getting price for {mint}: {e}")
            return None
    
    async def _get_pool_derived_price(self, mint: str) -> Optional[PriceData]:
        """
        Derive price from pool reserves when no recent swaps exist.
        This would query pool accounts directly.
        """
        try:
            # This is a stub - in practice you'd query specific pool accounts
            # and calculate price from reserves based on AMM type (XYK, CLAMM, etc)
            logger.debug(f"No swap data for {mint}, would derive from pool reserves")
            return None
        except Exception as e:
            logger.error(f"Error deriving pool price for {mint}: {e}")
            return None
    
    async def get_historical_data(self, mint: str, days: int = 17) -> Optional[HistoricalData]:
        """Get historical OHLCV data for a token."""
        if not self.db_pool:
            logger.warning("No database connection available for historical data")
            return None
            
        try:
            async with self.db_pool.acquire() as conn:
                # Get 5-minute OHLCV data
                ohlcv_data = await conn.fetch("""
                    SELECT 
                        EXTRACT(epoch FROM bucket) as ts,
                        open, high, low, close, volume_usd as volume
                    FROM ohlcv_5m 
                    WHERE mint = $1 
                    AND bucket >= NOW() - INTERVAL '%s days'
                    ORDER BY bucket ASC
                """ % days, mint)
                
                if not ohlcv_data:
                    return None
                
                # Convert to list of dicts
                ohlcv = []
                for row in ohlcv_data:
                    ohlcv.append({
                        'ts': int(row['ts']),
                        'o': float(row['open']),
                        'h': float(row['high']),
                        'l': float(row['low']),
                        'c': float(row['close']),
                        'v': float(row['volume'])
                    })
                
                # Calculate peaks
                three_days_ago = time.time() - (3 * 24 * 60 * 60)
                peak_72h = None
                post_ath_peak = None
                
                for candle in ohlcv:
                    if candle['ts'] <= three_days_ago:
                        # Within first 72 hours
                        if peak_72h is None or candle['h'] > peak_72h:
                            peak_72h = candle['h']
                    else:
                        # After 72 hours
                        if post_ath_peak is None or candle['h'] > post_ath_peak:
                            post_ath_peak = candle['h']
                
                return HistoricalData(
                    ohlcv=ohlcv,
                    peak_price_72h=peak_72h,
                    post_ath_peak_price=post_ath_peak
                )
                
        except Exception as e:
            logger.error(f"Error getting historical data for {mint}: {e}")
            return None
    
    async def get_holder_count(self, mint: str) -> Optional[int]:
        """Get current holder count for a token."""
        # Check cache first
        cache_key = f"holders_{mint}"
        if cache_key in self._holder_cache:
            count, cached_at = self._holder_cache[cache_key]
            if time.time() - cached_at < self.config.cache.holder_cache_ttl:
                return count
        
        try:
            # First try to get from recent snapshot
            if self.db_pool:
                async with self.db_pool.acquire() as conn:
                    recent_snapshot = await conn.fetchval("""
                        SELECT holder_count 
                        FROM holder_snapshots 
                        WHERE mint = $1 
                        ORDER BY snapshot_time DESC 
                        LIMIT 1
                    """, mint)
                    
                    if recent_snapshot:
                        # Cache the result
                        self._holder_cache[cache_key] = (recent_snapshot, time.time())
                        return recent_snapshot
            
            # If no recent snapshot, query RPC directly (expensive)
            return await self._query_holders_from_rpc(mint)
            
        except Exception as e:
            logger.error(f"Error getting holder count for {mint}: {e}")
            return None
    
    async def _query_holders_from_rpc(self, mint: str) -> Optional[int]:
        """Query holder count directly from RPC (expensive operation)."""
        if not self.rpc_client:
            logger.warning("No RPC client available for holder queries")
            return None
            
        try:
            from solana.publickey import PublicKey
            mint_pubkey = PublicKey(mint)
            
            # Get all token accounts for this mint
            response = await self.rpc_client.get_program_accounts(
                PublicKey(self.config.programs.token_program),
                encoding="jsonParsed",
                filters=[
                    {"dataSize": 165},  # Token account size
                    {"memcmp": {"offset": 0, "bytes": str(mint_pubkey)}}  # Filter by mint
                ]
            )
            
            if response.value is None:
                return 0
            
            # Count unique owners with non-zero balances
            unique_holders = set()
            for account in response.value:
                try:
                    parsed = account.account.data.parsed
                    if parsed['type'] == 'account':
                        info = parsed['info']
                        balance = float(info['tokenAmount']['amount'])
                        if balance > 0:
                            unique_holders.add(info['owner'])
                except Exception:
                    continue
            
            holder_count = len(unique_holders)
            
            # Cache the result
            self._holder_cache[f"holders_{mint}"] = (holder_count, time.time())
            
            # Also store in database for future use
            if self.db_pool:
                async with self.db_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO holder_snapshots (mint, snapshot_time, holder_count)
                        VALUES ($1, NOW(), $2)
                        ON CONFLICT (mint, snapshot_time) DO UPDATE SET holder_count = $2
                    """, mint, holder_count)
            
            return holder_count
            
        except Exception as e:
            logger.error(f"Error querying holders from RPC for {mint}: {e}")
            return None
    
    async def get_token_metadata(self, mint: str) -> Optional[Dict[str, Any]]:
        """Get token metadata (name, symbol, decimals)."""
        if not self.db_pool:
            return None
            
        try:
            async with self.db_pool.acquire() as conn:
                metadata = await conn.fetchrow("""
                    SELECT name, symbol, decimals, supply
                    FROM token_metadata 
                    WHERE mint = $1
                """, mint)
                
                if metadata:
                    return dict(metadata)
                
                # If not in cache, could query from chain (Metaplex metadata)
                # For now, return None
                return None
                
        except Exception as e:
            logger.error(f"Error getting metadata for {mint}: {e}")
            return None
