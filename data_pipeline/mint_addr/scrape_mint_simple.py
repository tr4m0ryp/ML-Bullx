#!/usr/bin/env python3
"""
Simplified Solana Mint Address Scraper via Multiple APIs.

Collects Solana token mint addresses using API-based data sources for
improved reliability over direct blockchain scanning:
- Jupiter aggregator token list (broad coverage of known tokens).
- CoinGecko market data with Solana ecosystem filtering.
- Solscan public API for token listings by market cap.
- DexScreener search API with creation date filtering.
- Orca whirlpool and Raydium liquidity pool token extraction.
- Serum DEX market token discovery.
- Additional sources: Birdeye, Solflare token list, Jupiter strict list.
- Incremental checkpointing with configurable save intervals.

Target: 10,000,000 unique mint addresses aged 3-12 months.

Author: ML-Bullx Team
Date: 2025-08-01
"""

# ============================================================================
# Standard Library Imports
# ============================================================================
import asyncio
import csv
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

# ============================================================================
# Third-Party Imports
# ============================================================================
import aiohttp
import pandas as pd

# ============================================================================
# Local Imports
# ============================================================================
# Try to import config loader, fall back to defaults if not available
try:
    from config_loader import load_config, get_age_cutoffs
    CONFIG = load_config()
    USE_CONFIG = True
except ImportError:
    CONFIG = None
    USE_CONFIG = False

# ============================================================================
# Logging Configuration
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mint_scraper_simple.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================================================
# Simplified Scraper Class
# ============================================================================

class SimpleMintScraper:
    """API-based Solana mint address scraper for reliable bulk collection.

    Uses multiple public APIs (Jupiter, CoinGecko, Solscan, DexScreener,
    Orca, Raydium, Serum, and others) to gather token mint addresses.
    Supports configurable age-range filtering, incremental checkpointing,
    and automatic CSV/TXT export at configurable intervals. Designed as
    an async context manager for proper HTTP session lifecycle management.
    """

    def __init__(self, target_count: int = 10000000, save_interval: int = 1000):
        """Initialize the simplified scraper.

        Args:
            target_count: Total number of unique mint addresses to collect.
            save_interval: Number of new addresses between automatic saves.
        """
        if USE_CONFIG and CONFIG:
            self.target_count = CONFIG.get('target_mint_count', target_count)
            # Calculate age cutoffs from config
            min_months = CONFIG.get('min_months_ago', 3)
            max_months = CONFIG.get('max_months_ago', 12)
            self.min_cutoff_date = datetime.now() - timedelta(days=max_months * 30)
            self.max_cutoff_date = datetime.now() - timedelta(days=min_months * 30)
        else:
            self.target_count = target_count
            # Default: 3 months to 1 year old
            self.min_cutoff_date = datetime.now() - timedelta(days=365)  # 1 year ago (oldest)
            self.max_cutoff_date = datetime.now() - timedelta(days=90)   # 3 months ago (newest)

        self.mint_addresses: Set[str] = set()
        self.session: Optional[aiohttp.ClientSession] = None
        self.save_interval = save_interval  # Save progress every N addresses
        self.last_save_count = 0  # Track when we last saved

    async def __aenter__(self):
        """Set up the aiohttp client session on context entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={'User-Agent': 'Solana-Mint-Scraper/1.0'}
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the aiohttp client session on context exit."""
        if self.session:
            await self.session.close()

    # ========================================================================
    # Jupiter Source
    # ========================================================================

    async def fetch_from_jupiter(self) -> Set[str]:
        """Fetch token addresses from the Jupiter aggregator token list.

        Retrieves the full Jupiter token list and collects all addresses
        except native SOL. Logs progress every 1,000 addresses.

        Returns:
            A set of mint address strings from Jupiter.
        """
        logger.info("Fetching from Jupiter API...")
        mint_addresses = set()

        try:
            url = "https://token.jup.ag/all"
            async with self.session.get(url) as response:
                if response.status == 200:
                    tokens = await response.json()

                    for token in tokens:
                        address = token.get('address')
                        if address and address not in ['So11111111111111111111111111111111111111112']:  # Exclude SOL
                            mint_addresses.add(address)

                            if len(mint_addresses) % 1000 == 0:
                                logger.info(f"Jupiter: Processed {len(mint_addresses)} addresses so far")

                    logger.info(f"Jupiter: Found {len(mint_addresses)} token addresses")
                else:
                    logger.error(f"Jupiter API error: {response.status}")

        except Exception as e:
            logger.error(f"Error fetching from Jupiter: {e}")

        return mint_addresses

    # ========================================================================
    # CoinGecko Source
    # ========================================================================

    async def fetch_from_coingecko(self) -> Set[str]:
        """Fetch Solana token addresses from the CoinGecko markets API.

        Queries the Solana ecosystem category across multiple pages. Falls
        back to an alternative bulk coin list approach if the primary
        method yields fewer than 100 results.

        Returns:
            A set of mint address strings from CoinGecko.
        """
        logger.info("Fetching from CoinGecko API...")
        mint_addresses = set()

        try:
            # Method 1: Get Solana ecosystem tokens
            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                'vs_currency': 'usd',
                'category': 'solana-ecosystem',
                'order': 'market_cap_desc',
                'per_page': 250,
                'page': 1,
                'sparkline': 'false'
            }

            for page in range(1, 21):  # Reduce pages to avoid rate limits
                params['page'] = page

                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        coins = await response.json()

                        if not coins:
                            break

                        for coin in coins:
                            platforms = coin.get('platforms', {})
                            solana_address = platforms.get('solana')

                            if solana_address and len(solana_address) > 32:  # Valid Solana address
                                mint_addresses.add(solana_address)

                        logger.info(f"CoinGecko page {page}: {len(coins)} coins processed, total addresses: {len(mint_addresses)}")

                        await asyncio.sleep(2)  # More conservative rate limiting
                    elif response.status == 429:
                        logger.info("Rate limited, waiting longer...")
                        await asyncio.sleep(20)
                        consecutive_failures = getattr(self, 'coingecko_failures', 0) + 1
                        setattr(self, 'coingecko_failures', consecutive_failures)
                        if consecutive_failures > 3:  # Reduce failure threshold
                            logger.warning("CoinGecko: Too many rate limit failures, trying alternative approach")
                            break
                        continue
                    else:
                        logger.error(f"CoinGecko API error: {response.status}")
                        break

            # Method 2: Try alternative approach if primary yielded few results
            if len(mint_addresses) < 100:
                logger.info("Trying alternative CoinGecko approach...")
                await self.fetch_coingecko_alternative(mint_addresses)

        except Exception as e:
            logger.error(f"Error fetching from CoinGecko: {e}")

        logger.info(f"CoinGecko: Found {len(mint_addresses)} token addresses")
        return mint_addresses

    async def fetch_coingecko_alternative(self, existing_addresses: Set[str]) -> None:
        """Fetch Solana addresses using the CoinGecko bulk coin list endpoint.

        Retrieves the complete coin list with platform information and
        filters for entries that have a Solana address. Results are added
        directly to the provided set.

        Args:
            existing_addresses: Mutable set to which discovered addresses
                are added in-place.
        """
        try:
            url = "https://api.coingecko.com/api/v3/coins/list"
            params = {'include_platform': 'true'}

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    coins = await response.json()

                    for coin in coins:
                        platforms = coin.get('platforms', {})
                        solana_address = platforms.get('solana')

                        if solana_address and len(solana_address) > 32:
                            existing_addresses.add(solana_address)

                    logger.info(f"CoinGecko alternative: Added {len(existing_addresses)} total addresses")
                else:
                    logger.warning(f"CoinGecko alternative API error: {response.status}")

        except Exception as e:
            logger.debug(f"Error in CoinGecko alternative: {e}")

    # ========================================================================
    # Solscan Source
    # ========================================================================

    async def fetch_from_solscan(self) -> Set[str]:
        """Fetch token addresses from the Solscan public API.

        Paginates through the Solscan token list endpoint sorted by market
        cap. Falls back to an alternative keyword-search approach if the
        primary endpoint returns a 404.

        Returns:
            A set of mint address strings from Solscan.
        """
        logger.info("Fetching from Solscan API...")
        mint_addresses = set()

        try:
            base_url = "https://public-api.solscan.io/token/list"

            for offset in range(0, 100000, 100):  # Get up to 100k tokens
                params = {
                    'offset': offset,
                    'limit': 100,
                    'sortBy': 'market_cap',
                    'direction': 'desc'
                }

                async with self.session.get(base_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Check if data has the expected structure
                        tokens = data.get('data', []) if isinstance(data, dict) else data

                        if not tokens:
                            logger.info(f"Solscan: No more tokens at offset {offset}")
                            break

                        for token in tokens:
                            # Handle different possible response structures
                            address = None
                            if isinstance(token, dict):
                                address = token.get('address') or token.get('tokenAddress') or token.get('mint')
                            elif isinstance(token, str):
                                address = token

                            if address and len(address) > 32:  # Valid Solana address length check
                                mint_addresses.add(address)

                        if offset % 1000 == 0:
                            logger.info(f"Solscan: Processed {offset + len(tokens)} tokens, total addresses: {len(mint_addresses)}")

                        # If we got fewer than requested, we've reached the end
                        if len(tokens) < 100:
                            logger.info(f"Solscan: Reached end of available tokens at offset {offset}")
                            break

                        await asyncio.sleep(0.8)  # More conservative rate limiting
                    elif response.status == 404:
                        logger.warning("Solscan endpoint not found, trying alternative approach...")
                        await self.fetch_from_solscan_alternative()
                        break
                    else:
                        logger.error(f"Solscan API error: {response.status}")
                        if response.status == 429:  # Rate limited
                            await asyncio.sleep(10)
                            continue
                        break

        except Exception as e:
            logger.error(f"Error fetching from Solscan: {e}")

        logger.info(f"Solscan: Found {len(mint_addresses)} token addresses")
        return mint_addresses

    async def fetch_from_solscan_alternative(self) -> Set[str]:
        """Fetch addresses from Solscan using keyword search as a fallback.

        Searches for tokens matching a predefined list of popular token
        symbols when the primary list endpoint is unavailable.

        Returns:
            A set of mint address strings discovered via search.
        """
        logger.info("Trying alternative Solscan approach...")
        mint_addresses = set()

        try:
            search_terms = ['USDC', 'SOL', 'BONK', 'RAY', 'JUP', 'ORCA', 'SRM', 'MNGO', 'FIDA', 'KIN']

            for term in search_terms:
                try:
                    url = f"https://public-api.solscan.io/token/search?keyword={term}"

                    async with self.session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()

                            tokens = data.get('data', []) if isinstance(data, dict) else []
                            for token in tokens:
                                address = token.get('address') or token.get('tokenAddress')
                                if address:
                                    mint_addresses.add(address)

                            await asyncio.sleep(1)
                        else:
                            logger.debug(f"Solscan search failed for {term}: {response.status}")

                except Exception as e:
                    logger.debug(f"Error in Solscan alternative search for {term}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error in Solscan alternative method: {e}")

        return mint_addresses

    # ========================================================================
    # DexScreener Source
    # ========================================================================

    async def fetch_from_dexscreener(self) -> Set[str]:
        """Fetch token addresses from DexScreener search and trending APIs.

        Performs keyword-based searches across an expanded list of terms,
        filtering Solana pairs by creation date when available. Also
        fetches trending Solana pairs for additional coverage.

        Returns:
            A set of mint address strings from DexScreener.
        """
        logger.info("Fetching from DexScreener API...")
        mint_addresses = set()

        try:
            base_url = "https://api.dexscreener.com/latest/dex/search/"

            # Expanded search terms to get more variety
            search_terms = [
                'sol', 'usdc', 'bonk', 'ray', 'jup', 'pyth', 'serum', 'mango', 'orca', 'fida',
                'step', 'cope', 'rope', 'samo', 'ninja', 'atlas', 'polis', 'media', 'like',
                'basis', 'sunny', 'saber', 'sonar', 'star', 'slnd', 'srm', 'ftt', 'msol'
            ]

            for term in search_terms:
                try:
                    search_url = f"{base_url}?q={term}"

                    async with self.session.get(search_url) as response:
                        if response.status == 200:
                            data = await response.json()

                            for pair in data.get('pairs', []):
                                if pair.get('chainId') == 'solana':
                                    created_at = pair.get('pairCreatedAt')
                                    if created_at:
                                        created_date = datetime.fromtimestamp(created_at / 1000)
                                        # Only include pairs created in the target timeframe
                                        if self.min_cutoff_date <= created_date <= self.max_cutoff_date:
                                            base_token = pair.get('baseToken', {})
                                            quote_token = pair.get('quoteToken', {})

                                            if base_token.get('address'):
                                                mint_addresses.add(base_token['address'])
                                            if quote_token.get('address'):
                                                mint_addresses.add(quote_token['address'])
                                    else:
                                        # If no creation date, include conservatively
                                        base_token = pair.get('baseToken', {})
                                        quote_token = pair.get('quoteToken', {})

                                        if base_token.get('address'):
                                            mint_addresses.add(base_token['address'])
                                        if quote_token.get('address'):
                                            mint_addresses.add(quote_token['address'])

                            logger.info(f"DexScreener '{term}': Found {len(data.get('pairs', []))} pairs, total addresses: {len(mint_addresses)}")
                            await asyncio.sleep(1.5)  # More conservative rate limiting
                        else:
                            logger.error(f"DexScreener API error for '{term}': {response.status}")
                            if response.status == 429:
                                await asyncio.sleep(5)
                                continue

                except Exception as e:
                    logger.error(f"Error searching DexScreener for '{term}': {e}")
                    continue

            # Also try to get trending pairs
            try:
                trending_url = "https://api.dexscreener.com/latest/dex/pairs/solana"
                async with self.session.get(trending_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        for pair in data.get('pairs', []):
                            base_token = pair.get('baseToken', {})
                            quote_token = pair.get('quoteToken', {})

                            if base_token.get('address'):
                                mint_addresses.add(base_token['address'])
                            if quote_token.get('address'):
                                mint_addresses.add(quote_token['address'])

                        logger.info(f"DexScreener trending: Found {len(data.get('pairs', []))} pairs")
            except Exception as e:
                logger.debug(f"Error fetching trending pairs: {e}")

        except Exception as e:
            logger.error(f"Error fetching from DexScreener: {e}")

        logger.info(f"DexScreener: Found {len(mint_addresses)} token addresses")
        return mint_addresses

    # ========================================================================
    # Orca Source
    # ========================================================================

    async def fetch_from_orca(self) -> Set[str]:
        """Fetch token addresses from Orca whirlpool listings.

        Queries the Orca API for all whirlpool (concentrated liquidity)
        pools and extracts the token mint addresses from each side of
        every pool.

        Returns:
            A set of mint address strings from Orca pools.
        """
        logger.info("Fetching from Orca API...")
        mint_addresses = set()

        try:
            url = "https://api.orca.so/v1/whirlpool/list"

            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    for pool in data.get('whirlpools', []):
                        token_a = pool.get('tokenA', {})
                        token_b = pool.get('tokenB', {})

                        if token_a.get('mint'):
                            mint_addresses.add(token_a['mint'])
                        if token_b.get('mint'):
                            mint_addresses.add(token_b['mint'])

                else:
                    logger.warning(f"Orca API error: {response.status}")

        except Exception as e:
            logger.error(f"Error fetching from Orca: {e}")

        logger.info(f"Orca: Found {len(mint_addresses)} token addresses")
        return mint_addresses

    # ========================================================================
    # Raydium Source
    # ========================================================================

    async def fetch_from_raydium(self) -> Set[str]:
        """Fetch token addresses from Raydium liquidity pools.

        Queries the Raydium SDK API for both official and unofficial
        liquidity pools, extracting base and quote mint addresses from
        each pool definition.

        Returns:
            A set of mint address strings from Raydium pools.
        """
        logger.info("Fetching from Raydium API...")
        mint_addresses = set()

        try:
            url = "https://api.raydium.io/v2/sdk/liquidity/mainnet.json"

            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    # Handle both official and unofficial pools
                    all_pools = []
                    if 'official' in data:
                        all_pools.extend(data['official'])
                    if 'unOfficial' in data:
                        all_pools.extend(data['unOfficial'])

                    for pool in all_pools:
                        base_mint = pool.get('baseMint')
                        quote_mint = pool.get('quoteMint')

                        if base_mint:
                            mint_addresses.add(base_mint)
                        if quote_mint:
                            mint_addresses.add(quote_mint)

                else:
                    logger.warning(f"Raydium API error: {response.status}")

        except Exception as e:
            logger.error(f"Error fetching from Raydium: {e}")

        logger.info(f"Raydium: Found {len(mint_addresses)} token addresses")
        return mint_addresses

    # ========================================================================
    # Serum Source
    # ========================================================================

    async def fetch_from_serum_markets(self) -> Set[str]:
        """Fetch token addresses from Serum DEX market listings.

        Attempts multiple Serum data endpoints in order, extracting base
        and quote mint addresses from the first endpoint that responds
        successfully.

        Returns:
            A set of mint address strings from Serum markets.
        """
        logger.info("Fetching from Serum markets...")
        mint_addresses = set()

        try:
            urls = [
                "https://raw.githubusercontent.com/project-serum/serum-ts/master/packages/serum/src/markets.json",
                "https://api.serum-academy.com/markets",
                "https://serum-api.bonfida.com/markets"
            ]

            for url in urls:
                try:
                    async with self.session.get(url) as response:
                        if response.status == 200:
                            # Handle different content types
                            content_type = response.headers.get('content-type', '')
                            if 'application/json' in content_type or 'json' in content_type:
                                markets = await response.json()
                            else:
                                text = await response.text()
                                markets = json.loads(text)

                            if isinstance(markets, list):
                                for market in markets:
                                    base_mint = market.get('baseMintAddress') or market.get('baseMint')
                                    quote_mint = market.get('quoteMintAddress') or market.get('quoteMint')

                                    if base_mint:
                                        mint_addresses.add(base_mint)
                                    if quote_mint:
                                        mint_addresses.add(quote_mint)

                            logger.info(f"Serum: Successfully fetched from {url}")
                            break  # Success, don't try other URLs

                except Exception as e:
                    logger.debug(f"Failed to fetch from {url}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error fetching from Serum markets: {e}")

        logger.info(f"Serum: Found {len(mint_addresses)} token addresses")
        return mint_addresses

    # ========================================================================
    # Comprehensive Multi-Source Fetching
    # ========================================================================

    async def fetch_token_addresses_comprehensive(self) -> Set[str]:
        """Collect addresses from all available data sources sequentially.

        Iterates through Jupiter, CoinGecko, Solscan, DexScreener, Orca,
        Raydium, and Serum, accumulating unique addresses and saving
        progress after each source completes.

        Returns:
            The combined set of all unique mint addresses discovered.
        """
        logger.info("Starting comprehensive token address collection...")
        all_addresses = set()

        sources = [
            ("Jupiter", self.fetch_from_jupiter()),
            ("CoinGecko", self.fetch_from_coingecko()),
            ("Solscan", self.fetch_from_solscan()),
            ("DexScreener", self.fetch_from_dexscreener()),
            ("Orca", self.fetch_from_orca()),
            ("Raydium", self.fetch_from_raydium()),
            ("Serum", self.fetch_from_serum_markets())
        ]

        for source_name, source_coro in sources:
            try:
                logger.info(f"Fetching from {source_name}...")
                addresses = await source_coro
                new_addresses = addresses - all_addresses
                all_addresses.update(new_addresses)

                logger.info(f"{source_name}: Added {len(new_addresses)} new addresses")
                logger.info(f"Total unique addresses so far: {len(all_addresses)}")

                # Save progress after each source
                self.mint_addresses = all_addresses
                self.check_and_save_progress()

                logger.info(f"Current progress: {len(all_addresses)} / {self.target_count} addresses")

            except Exception as e:
                logger.error(f"Error processing {source_name}: {e}")
                continue

        return all_addresses

    # ========================================================================
    # Metadata and Age Filtering
    # ========================================================================

    async def fetch_token_metadata_batch(self, addresses: List[str]) -> Dict[str, Dict]:
        """Fetch creation-time metadata for a batch of token addresses.

        Queries the Solscan token metadata endpoint for each address to
        determine creation timestamps for subsequent age filtering.

        Args:
            addresses: List of mint address strings to look up.

        Returns:
            A dictionary mapping mint addresses to their metadata
            (creation_time, symbol, name, supply).
        """
        logger.info(f"Fetching metadata for {len(addresses)} tokens...")
        metadata = {}

        try:
            for i in range(0, len(addresses), 10):  # Process in batches of 10
                batch = addresses[i:i+10]

                for address in batch:
                    try:
                        url = f"https://public-api.solscan.io/token/meta?tokenAddress={address}"

                        async with self.session.get(url) as response:
                            if response.status == 200:
                                data = await response.json()

                                creation_time = None
                                if 'createdTime' in data:
                                    creation_time = datetime.fromtimestamp(data['createdTime'])

                                metadata[address] = {
                                    'creation_time': creation_time,
                                    'symbol': data.get('symbol', ''),
                                    'name': data.get('name', ''),
                                    'supply': data.get('supply', 0)
                                }

                            await asyncio.sleep(0.2)  # Rate limiting

                    except Exception as e:
                        logger.debug(f"Error fetching metadata for {address}: {e}")
                        continue

                if i % 100 == 0:
                    logger.info(f"Processed metadata for {i + len(batch)} tokens")

        except Exception as e:
            logger.error(f"Error in batch metadata fetch: {e}")

        return metadata

    def filter_old_tokens(self, addresses: Set[str], metadata: Dict[str, Dict]) -> Set[str]:
        """Filter tokens to retain only those within the target age range.

        Tokens with a known creation time outside the 3-month to 1-year
        window are excluded. Tokens without creation time data are kept
        conservatively.

        Args:
            addresses: Set of candidate mint address strings.
            metadata: Dictionary of address-to-metadata mappings as returned
                by fetch_token_metadata_batch.

        Returns:
            A filtered set of mint addresses within the target age range.
        """
        age_filtered_tokens = set()

        for address in addresses:
            token_meta = metadata.get(address, {})
            creation_time = token_meta.get('creation_time')

            if creation_time:
                # Check if token is in our target age range (3 months to 1 year old)
                if self.min_cutoff_date <= creation_time <= self.max_cutoff_date:
                    age_filtered_tokens.add(address)
            else:
                # If we can't determine age, include it (conservative approach)
                age_filtered_tokens.add(address)

        logger.info(f"Filtered to {len(age_filtered_tokens)} tokens between 3 months and 1 year old")
        return age_filtered_tokens

    # ========================================================================
    # Orchestration
    # ========================================================================

    async def run_scraping(self) -> None:
        """Run the complete multi-source scraping and filtering pipeline.

        Collects from all primary and additional sources with per-source
        timeouts. If the target is not met, attempts extended collection.
        If the target is exceeded, applies metadata-based age filtering
        to trim the result set.
        """
        logger.info(f"Starting simplified scraping. Target: {self.target_count} addresses")
        logger.info(f"Age range: {self.min_cutoff_date.strftime('%Y-%m-%d')} to {self.max_cutoff_date.strftime('%Y-%m-%d')}")
        logger.info(f"Collecting tokens between 3 months and 1 year old")

        all_addresses = set()

        # Collect from all sources
        sources = [
            ("Jupiter", self.fetch_from_jupiter()),
            ("CoinGecko", self.fetch_from_coingecko()),
            ("Solscan", self.fetch_from_solscan()),
            ("DexScreener", self.fetch_from_dexscreener()),
            ("Orca", self.fetch_from_orca()),
            ("Raydium", self.fetch_from_raydium()),
            ("Serum", self.fetch_from_serum_markets()),
            ("Additional", self.fetch_from_additional_sources())
        ]

        for source_name, source_coro in sources:
            try:
                logger.info(f"Starting collection from {source_name}...")
                # Add timeout to prevent getting stuck on one source
                addresses = await asyncio.wait_for(source_coro, timeout=900)  # 15 minute timeout per source
                new_addresses = addresses - all_addresses
                all_addresses.update(new_addresses)

                logger.info(f"{source_name}: Added {len(new_addresses)} new addresses")
                logger.info(f"Total unique addresses so far: {len(all_addresses)}")

                # Save progress after each source
                self.mint_addresses = all_addresses
                self.check_and_save_progress()

                logger.info(f"Current progress: {len(all_addresses)} / {self.target_count} addresses")

            except asyncio.TimeoutError:
                logger.warning(f"Timeout waiting for {source_name}, skipping to next source")
                continue
            except Exception as e:
                logger.error(f"Error processing {source_name}: {e}")
                continue

        # After collecting from all primary sources, try extended collection
        if len(all_addresses) < self.target_count:
            logger.info(f"Collected {len(all_addresses)} addresses from primary sources")
            logger.info(f"Attempting extended collection to reach target of {self.target_count}")
            all_addresses = await self.generate_additional_addresses_if_needed(all_addresses)

        # Filter by age if we have too many addresses
        if len(all_addresses) > self.target_count:
            logger.info("Filtering addresses by age...")

            sample_size = min(len(all_addresses), self.target_count * 2)
            address_list = list(all_addresses)[:sample_size]

            metadata = await self.fetch_token_metadata_batch(address_list)
            old_addresses = self.filter_old_tokens(set(address_list), metadata)

            # Take up to target_count old addresses
            self.mint_addresses = set(list(old_addresses)[:self.target_count])
        else:
            self.mint_addresses = all_addresses

        # Final save
        self.check_and_save_progress(force_save=True)

        logger.info(f"Final count: {len(self.mint_addresses)} mint addresses")

    # ========================================================================
    # Checkpoint and Export
    # ========================================================================

    def save_checkpoint(self) -> None:
        """Save current collection state to a JSON checkpoint file.

        Persists the full address set, count, timestamp, age range
        metadata, and save interval configuration.
        """
        try:
            checkpoint_data = {
                'mint_addresses': list(self.mint_addresses),
                'count': len(self.mint_addresses),
                'timestamp': datetime.now().isoformat(),
                'min_cutoff_date': self.min_cutoff_date.isoformat(),
                'max_cutoff_date': self.max_cutoff_date.isoformat(),
                'age_range': '3_months_to_1_year',
                'save_interval': self.save_interval,
                'last_save_count': self.last_save_count
            }

            with open('mint_addresses_checkpoint_simple.json', 'w') as f:
                json.dump(checkpoint_data, f, indent=2)

        except Exception as e:
            logger.error(f"Error saving checkpoint: {e}")

    def load_checkpoint(self) -> bool:
        """Load collection state from a previous checkpoint file.

        Returns:
            True if a checkpoint was successfully loaded, False otherwise.
        """
        try:
            if os.path.exists('mint_addresses_checkpoint_simple.json'):
                with open('mint_addresses_checkpoint_simple.json', 'r') as f:
                    data = json.load(f)

                self.mint_addresses = set(data.get('mint_addresses', []))
                self.last_save_count = len(self.mint_addresses)  # Reset save counter
                logger.info(f"Loaded {len(self.mint_addresses)} addresses from checkpoint")
                return True

        except Exception as e:
            logger.error(f"Error loading checkpoint: {e}")

        return False

    def export_to_csv(self, filename: str = None) -> None:
        """Export collected addresses to CSV and plain text files.

        Uses the configured output filename if available, otherwise falls
        back to the provided filename or a default.

        Args:
            filename: Optional override for the output CSV filename. When
                None, uses the config value or a built-in default.
        """
        try:
            if not filename:
                if USE_CONFIG and CONFIG:
                    filename = CONFIG.get('output', {}).get('csv_filename', 'solana_mint_addresses_3months_to_1year.csv')
                else:
                    filename = 'solana_mint_addresses_3months_to_1year.csv'

            address_list = list(self.mint_addresses)

            df = pd.DataFrame({
                'mint_address': address_list,
                'collected_at': datetime.now().isoformat(),
                'index': range(len(address_list))
            })

            # Save to CSV
            df.to_csv(filename, index=False)
            logger.info(f"Exported {len(address_list)} addresses to {filename}")

            # Also save as txt
            txt_filename = filename.replace('.csv', '.txt')
            with open(txt_filename, 'w') as f:
                for addr in address_list:
                    f.write(f"{addr}\n")

            logger.info(f"Also saved to {txt_filename}")

        except Exception as e:
            logger.error(f"Error exporting: {e}")

    def check_and_save_progress(self, force_save: bool = False) -> None:
        """Conditionally save progress based on the configured interval.

        Triggers a checkpoint save and CSV export when the number of newly
        collected addresses since the last save exceeds the save interval,
        or when explicitly forced.

        Args:
            force_save: If True, save regardless of the interval threshold.
        """
        current_count = len(self.mint_addresses)

        # Save if we've collected enough new addresses or if forced
        if force_save or (current_count - self.last_save_count) >= self.save_interval:
            self.save_checkpoint()
            self.export_to_csv()  # Also export current data
            self.last_save_count = current_count
            logger.info(f"Progress saved at {current_count} addresses")

    # ========================================================================
    # Additional and Extended Sources
    # ========================================================================

    async def fetch_from_additional_sources(self) -> Set[str]:
        """Fetch from supplementary token sources for broader coverage.

        Queries Birdeye, Solflare token list CDN, and Jupiter strict list
        to supplement the primary data sources.

        Returns:
            A set of mint address strings from additional sources.
        """
        logger.info("Fetching from additional sources...")
        mint_addresses = set()

        try:
            # Source 1: Birdeye API
            try:
                url = "https://public-api.birdeye.so/public/tokenlist"
                params = {'sort_by': 'v24hUSD', 'sort_type': 'desc', 'offset': 0, 'limit': 1000}

                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        tokens = data.get('data', {}).get('tokens', [])
                        for token in tokens:
                            address = token.get('address')
                            if address and len(address) > 32:
                                mint_addresses.add(address)
                        logger.info(f"Birdeye: Found {len(tokens)} tokens")
            except Exception as e:
                logger.debug(f"Birdeye error: {e}")

            # Source 2: Solflare token list
            try:
                url = "https://cdn.jsdelivr.net/gh/solflare-wallet/token-list/solana-tokenlist.json"
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        tokens = data.get('tokens', [])
                        for token in tokens:
                            address = token.get('address')
                            if address and len(address) > 32:
                                mint_addresses.add(address)
                        logger.info(f"Solflare: Found {len(tokens)} tokens")
            except Exception as e:
                logger.debug(f"Solflare error: {e}")

            # Source 3: Jupiter strict list
            try:
                url = "https://token.jup.ag/strict"
                async with self.session.get(url) as response:
                    if response.status == 200:
                        tokens = await response.json()
                        for token in tokens:
                            address = token.get('address')
                            if address and address not in ['So11111111111111111111111111111111111111112']:
                                mint_addresses.add(address)
                        logger.info(f"Jupiter Strict: Found {len(tokens)} tokens")
            except Exception as e:
                logger.debug(f"Jupiter strict error: {e}")

        except Exception as e:
            logger.error(f"Error in additional sources: {e}")

        logger.info(f"Additional Sources: Found {len(mint_addresses)} token addresses")
        return mint_addresses

    async def generate_additional_addresses_if_needed(self, current_addresses: Set[str]) -> Set[str]:
        """Attempt extended DexScreener searches to approach the target.

        Uses a broader set of generic search terms when the primary
        collection yielded fewer than 10% of the target.

        Args:
            current_addresses: The current set of collected addresses,
                modified in-place with any new discoveries.

        Returns:
            The updated set of addresses after extended collection.
        """
        if len(current_addresses) >= self.target_count * 0.1:  # If we have at least 10% of target
            return current_addresses

        logger.info(f"Attempting to reach closer to target through additional collection methods...")

        additional_search_terms = [
            'token', 'coin', 'defi', 'nft', 'dao', 'meme', 'gaming', 'meta', 'ai', 'social',
            'music', 'art', 'sports', 'finance', 'trade', 'swap', 'farm', 'pool', 'yield',
            'stake', 'governance', 'bridge', 'oracle', 'lending', 'borrow', 'mint', 'burn'
        ]

        try:
            base_url = "https://api.dexscreener.com/latest/dex/search/"

            for term in additional_search_terms:
                try:
                    search_url = f"{base_url}?q={term}"
                    async with self.session.get(search_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            for pair in data.get('pairs', []):
                                if pair.get('chainId') == 'solana':
                                    for token_key in ['baseToken', 'quoteToken']:
                                        token = pair.get(token_key, {})
                                        address = token.get('address')
                                        if address and address not in current_addresses:
                                            current_addresses.add(address)

                    await asyncio.sleep(2)  # Rate limiting

                    if len(current_addresses) % 10000 == 0:
                        logger.info(f"Extended search progress: {len(current_addresses)} addresses")

                except Exception as e:
                    logger.debug(f"Error in extended search for {term}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error in extended collection: {e}")

        return current_addresses


# ============================================================================
# Script Entry Point
# ============================================================================

async def main():
    """Run the simplified multi-source scraping pipeline.

    Initializes the scraper with a 10M target, loads any existing checkpoint,
    runs the collection process, and exports results. Handles keyboard
    interrupts by saving partial progress.
    """
    scraper = SimpleMintScraper(target_count=10000000)  # Updated to 10M

    # Load checkpoint if exists
    scraper.load_checkpoint()

    try:
        async with scraper:
            if len(scraper.mint_addresses) < scraper.target_count:
                await scraper.run_scraping()

            # Export results
            scraper.export_to_csv()

            logger.info("Scraping completed successfully!")
            logger.info(f"Total addresses collected: {len(scraper.mint_addresses)}")

    except KeyboardInterrupt:
        logger.info("Scraping interrupted")
        scraper.save_checkpoint()
        scraper.export_to_csv("solana_mint_addresses_partial.csv")


if __name__ == "__main__":
    asyncio.run(main())
