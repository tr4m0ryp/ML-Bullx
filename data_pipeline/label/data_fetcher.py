"""
Real-time data fetcher for Solana tokens
Integrates with actual APIs to fetch token metrics
"""

import asyncio
import aiohttp
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
import time
from solana.rpc.async_api import AsyncClient
from solana.publickey import PublicKey
import pandas as pd

from config import API_CONFIG, DATA_SOURCES

logger = logging.getLogger(__name__)

@dataclass
class PricePoint:
    """Single price data point"""
    timestamp: datetime
    price: float
    volume: float
    market_cap: Optional[float] = None

@dataclass
class TokenData:
    """Complete token data structure"""
    mint_address: str
    symbol: Optional[str] = None
    name: Optional[str] = None
    decimals: int = 9
    total_supply: Optional[float] = None
    
    # Price data
    current_price: Optional[float] = None
    launch_price: Optional[float] = None
    price_history: List[PricePoint] = None
    
    # Volume data
    volume_24h: Optional[float] = None
    volume_7d: Optional[float] = None
    volume_history: List[Tuple[datetime, float]] = None
    
    # Liquidity data
    total_liquidity: Optional[float] = None
    liquidity_history: List[Tuple[datetime, float]] = None
    
    # Holder data
    holder_count: Optional[int] = None
    holder_history: List[Tuple[datetime, int]] = None
    
    # Developer data
    developer_wallets: List[str] = None
    dev_transactions: List[Dict] = None
    
    # Market data
    market_cap: Optional[float] = None
    fdv: Optional[float] = None
    age_days: Optional[int] = None
    
    def __post_init__(self):
        if self.price_history is None:
            self.price_history = []
        if self.volume_history is None:
            self.volume_history = []
        if self.liquidity_history is None:
            self.liquidity_history = []
        if self.holder_history is None:
            self.holder_history = []
        if self.developer_wallets is None:
            self.developer_wallets = []
        if self.dev_transactions is None:
            self.dev_transactions = []

class SolanaDataFetcher:
    """Fetches real-time data from Solana and DEX APIs"""
    
    def __init__(self, rpc_endpoint: str = None):
        self.rpc_endpoint = rpc_endpoint or API_CONFIG['solana_rpc_endpoints'][0]
        self.session: Optional[aiohttp.ClientSession] = None
        self.solana_client: Optional[AsyncClient] = None
        self.rate_limiter = {}
        
    async def __aenter__(self):
        """Async context manager entry"""
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        self.solana_client = AsyncClient(self.rpc_endpoint)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
        if self.solana_client:
            await self.solana_client.close()
    
    async def _rate_limit(self, endpoint: str):
        """Simple rate limiting"""
        now = time.time()
        if endpoint in self.rate_limiter:
            last_request = self.rate_limiter[endpoint]
            time_diff = now - last_request
            min_interval = 1.0 / API_CONFIG['rate_limits']['requests_per_second']
            if time_diff < min_interval:
                await asyncio.sleep(min_interval - time_diff)
        self.rate_limiter[endpoint] = time.time()
    
    async def get_token_metadata(self, mint_address: str) -> Dict:
        """Fetch basic token metadata from Solana"""
        try:
            await self._rate_limit('solana_rpc')
            
            mint_pubkey = PublicKey(mint_address)
            account_info = await self.solana_client.get_account_info(mint_pubkey)
            
            if account_info.value is None:
                logger.warning(f"No account info found for {mint_address}")
                return {}
            
            # Parse mint account data (simplified)
            # In production, use proper SPL token parsing
            return {
                'mint_address': mint_address,
                'owner': str(account_info.value.owner),
                'lamports': account_info.value.lamports,
                'executable': account_info.value.executable,
                'rent_epoch': account_info.value.rent_epoch
            }
            
        except Exception as e:
            logger.error(f"Error fetching metadata for {mint_address}: {e}")
            return {}
    
    async def get_jupiter_price_data(self, mint_address: str) -> Dict:
        """Fetch price data from Jupiter API"""
        try:
            await self._rate_limit('jupiter')
            
            url = f"{API_CONFIG['dex_apis']['jupiter']}/price"
            params = {
                'ids': mint_address,
                'vsToken': 'So11111111111111111111111111111111111111112'  # SOL
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if mint_address in data.get('data', {}):
                        price_info = data['data'][mint_address]
                        return {
                            'price': float(price_info.get('price', 0)),
                            'timestamp': datetime.now(),
                            'source': 'jupiter'
                        }
                else:
                    logger.warning(f"Jupiter API returned status {response.status} for {mint_address}")
                    
        except Exception as e:
            logger.error(f"Error fetching Jupiter price for {mint_address}: {e}")
        
        return {}
    
    async def get_dexscreener_data(self, mint_address: str) -> Dict:
        """Fetch comprehensive data from DexScreener"""
        try:
            await self._rate_limit('dexscreener')
            
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint_address}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get('pairs'):
                        # Get the most liquid pair
                        pair = max(data['pairs'], key=lambda p: float(p.get('liquidity', {}).get('usd', 0)))
                        
                        return {
                            'price_usd': float(pair.get('priceUsd', 0)),
                            'price_change_24h': float(pair.get('priceChange', {}).get('h24', 0)),
                            'volume_24h': float(pair.get('volume', {}).get('h24', 0)),
                            'volume_6h': float(pair.get('volume', {}).get('h6', 0)),
                            'volume_1h': float(pair.get('volume', {}).get('h1', 0)),
                            'liquidity_usd': float(pair.get('liquidity', {}).get('usd', 0)),
                            'market_cap': float(pair.get('marketCap', 0)),
                            'fdv': float(pair.get('fdv', 0)),
                            'pair_created_at': pair.get('pairCreatedAt'),
                            'dex_id': pair.get('dexId'),
                            'source': 'dexscreener'
                        }
                else:
                    logger.warning(f"DexScreener API returned status {response.status} for {mint_address}")
                    
        except Exception as e:
            logger.error(f"Error fetching DexScreener data for {mint_address}: {e}")
        
        return {}
    
    async def get_holder_count(self, mint_address: str) -> int:
        """Get holder count from Solana RPC (simplified)"""
        try:
            await self._rate_limit('solana_rpc')
            
            # This is a simplified implementation
            # In production, you'd need to:
            # 1. Find all token accounts for this mint
            # 2. Count unique owners
            # 3. Filter out zero balances
            
            mint_pubkey = PublicKey(mint_address)
            
            # Get token accounts by mint
            response = await self.solana_client.get_token_accounts_by_mint(mint_pubkey)
            
            if response.value:
                # Count unique owners (simplified)
                unique_owners = set()
                for account in response.value:
                    if account.account.owner:
                        unique_owners.add(str(account.account.owner))
                
                return len(unique_owners)
            
        except Exception as e:
            logger.error(f"Error getting holder count for {mint_address}: {e}")
        
        return 0
    
    async def get_transaction_history(self, mint_address: str, limit: int = 1000) -> List[Dict]:
        """Get recent transaction history for analysis"""
        try:
            await self._rate_limit('solana_rpc')
            
            mint_pubkey = PublicKey(mint_address)
            
            # Get recent signatures
            signatures = await self.solana_client.get_signatures_for_address(
                mint_pubkey, 
                limit=limit
            )
            
            transactions = []
            for sig_info in signatures.value[:50]:  # Limit to avoid rate limits
                sig = sig_info.signature
                tx = await self.solana_client.get_transaction(sig)
                
                if tx.value:
                    transactions.append({
                        'signature': sig,
                        'slot': tx.value.slot,
                        'block_time': tx.value.block_time,
                        'meta': tx.value.transaction.meta,
                        'transaction': tx.value.transaction.transaction
                    })
                
                # Small delay to avoid overwhelming the RPC
                await asyncio.sleep(0.1)
            
            return transactions
            
        except Exception as e:
            logger.error(f"Error getting transaction history for {mint_address}: {e}")
            return []
    
    async def fetch_complete_token_data(self, mint_address: str) -> TokenData:
        """Fetch all available data for a token"""
        logger.info(f"Fetching complete data for {mint_address}")
        
        # Fetch data from multiple sources concurrently
        tasks = [
            self.get_token_metadata(mint_address),
            self.get_jupiter_price_data(mint_address),
            self.get_dexscreener_data(mint_address),
            self.get_holder_count(mint_address),
            self.get_transaction_history(mint_address)
        ]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            metadata, jupiter_data, dexscreener_data, holder_count, transactions = results
            
            # Handle exceptions in results
            if isinstance(metadata, Exception):
                logger.error(f"Metadata fetch failed: {metadata}")
                metadata = {}
            if isinstance(jupiter_data, Exception):
                logger.error(f"Jupiter data fetch failed: {jupiter_data}")
                jupiter_data = {}
            if isinstance(dexscreener_data, Exception):
                logger.error(f"DexScreener data fetch failed: {dexscreener_data}")
                dexscreener_data = {}
            if isinstance(holder_count, Exception):
                logger.error(f"Holder count fetch failed: {holder_count}")
                holder_count = 0
            if isinstance(transactions, Exception):
                logger.error(f"Transaction history fetch failed: {transactions}")
                transactions = []
            
            # Combine data into TokenData object
            token_data = TokenData(mint_address=mint_address)
            
            # Set price data (prefer DexScreener, fallback to Jupiter)
            if dexscreener_data.get('price_usd'):
                token_data.current_price = dexscreener_data['price_usd']
                token_data.volume_24h = dexscreener_data.get('volume_24h')
                token_data.total_liquidity = dexscreener_data.get('liquidity_usd')
                token_data.market_cap = dexscreener_data.get('market_cap')
                token_data.fdv = dexscreener_data.get('fdv')
            elif jupiter_data.get('price'):
                token_data.current_price = jupiter_data['price']
            
            # Set holder data
            token_data.holder_count = holder_count
            
            # Calculate age if we have creation date
            if dexscreener_data.get('pair_created_at'):
                try:
                    created_at = datetime.fromtimestamp(dexscreener_data['pair_created_at'] / 1000)
                    token_data.age_days = (datetime.now() - created_at).days
                except:
                    pass
            
            # Analyze transactions for developer behavior
            if transactions:
                token_data.dev_transactions = transactions[:10]  # Store sample
            
            logger.info(f"Successfully fetched data for {mint_address}")
            return token_data
            
        except Exception as e:
            logger.error(f"Error in fetch_complete_token_data for {mint_address}: {e}")
            return TokenData(mint_address=mint_address)

async def test_data_fetcher():
    """Test function for the data fetcher"""
    test_tokens = [
        "85FCjfVZdnojztL1FvdJzdd5HvoP1bAVogxyYjv9pump",  # From your CSV
        "So11111111111111111111111111111111111111112",   # SOL
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"   # USDC
    ]
    
    async with SolanaDataFetcher() as fetcher:
        for token in test_tokens:
            try:
                data = await fetcher.fetch_complete_token_data(token)
                print(f"\nToken: {token}")
                print(f"Price: ${data.current_price}")
                print(f"Volume 24h: ${data.volume_24h}")
                print(f"Holders: {data.holder_count}")
                print(f"Market Cap: ${data.market_cap}")
                print(f"Age: {data.age_days} days")
            except Exception as e:
                print(f"Error processing {token}: {e}")

if __name__ == "__main__":
    asyncio.run(test_data_fetcher())
