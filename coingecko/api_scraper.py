"""
CoinGecko API-Based Memecoin Scraper.

Collects Solana memecoin mint addresses via the CoinGecko REST API:
- Fetches memecoins by category with automatic pagination.
- Extracts Solana contract addresses from platform metadata.
- Falls back to HTML scraping when the API is unavailable.
- Supplements results with a curated list of known Solana memecoins.
- Exports deduplicated results to CSV.

Author: ML-Bullx Team
Date: 2025-08-01
"""

# =============================================================================
# Standard Library Imports
# =============================================================================
import csv
import json
import logging
import re
import time
from typing import Dict, List, Optional

# =============================================================================
# Third-Party Imports
# =============================================================================
import pandas as pd
import requests
from urllib.parse import urljoin

# =============================================================================
# Logging Configuration
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('coingecko_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# CoinGeckoAPIBasedScraper
# =============================================================================
class CoinGeckoAPIBasedScraper:
    """API-driven scraper for discovering Solana memecoins on CoinGecko.

    Combines the CoinGecko REST API with lightweight HTML scraping as a
    fallback.  The scraper retrieves coin metadata, inspects the ``platforms``
    field for Solana contract addresses, and writes deduplicated results to
    CSV files.

    Responsibilities:
        - Query the CoinGecko ``/coins/markets`` endpoint by category.
        - Retrieve per-coin detail via ``/coins/{id}``.
        - Parse Solana contract addresses from platform metadata.
        - Provide an HTML-scraping fallback for coin ID discovery.
        - Persist results as both summary and detailed CSV files.
    """

    def __init__(self):
        """Initialize the scraper with a configured HTTP session."""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
        })
        self.base_url = "https://www.coingecko.com"
        self.api_base = "https://api.coingecko.com/api/v3"

    # =========================================================================
    # HTTP Helpers
    # =========================================================================
    def get_with_retry(self, url: str, retries: int = 3, **kwargs) -> Optional[requests.Response]:
        """Make an HTTP GET request with exponential backoff on failure.

        Args:
            url: Target URL to fetch.
            retries: Maximum number of attempts before giving up.
            **kwargs: Additional keyword arguments forwarded to ``requests.get``.

        Returns:
            The successful ``Response`` object, or None if all attempts failed.
        """
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=30, **kwargs)
                if response.status_code == 200:
                    return response
                elif response.status_code == 429:
                    wait_time = (2 ** attempt) * 5
                    logger.warning(f"Rate limited. Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"HTTP {response.status_code} for {url}")
                    time.sleep(2)
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {str(e)}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)

        logger.error(f"All attempts failed for {url}")
        return None

    # =========================================================================
    # API Methods
    # =========================================================================
    def get_coins_by_category(self, category_id: str = "meme-token") -> List[Dict]:
        """Fetch coins belonging to a CoinGecko category via the markets API.

        Args:
            category_id: CoinGecko category slug (default ``"meme-token"``).

        Returns:
            A list of coin market-data dictionaries, or an empty list on
            failure.
        """
        try:
            url = f"{self.api_base}/coins/markets"
            params = {
                'vs_currency': 'usd',
                'category': category_id,
                'order': 'market_cap_desc',
                'per_page': 250,
                'page': 1,
                'sparkline': 'false'
            }

            response = self.get_with_retry(url, params=params)
            if response:
                coins = response.json()
                logger.info(f"Retrieved {len(coins)} coins from API")
                return coins
            else:
                logger.error("Failed to get coins from API")
                return []

        except Exception as e:
            logger.error(f"Error fetching coins by category: {str(e)}")
            return []

    def get_coin_details(self, coin_id: str) -> Optional[Dict]:
        """Retrieve detailed metadata for a single coin.

        Args:
            coin_id: CoinGecko coin identifier (e.g. ``"bonk"``).

        Returns:
            A dictionary of coin metadata including platform addresses, or
            None on failure.
        """
        try:
            url = f"{self.api_base}/coins/{coin_id}"
            params = {
                'localization': 'false',
                'tickers': 'false',
                'market_data': 'false',
                'community_data': 'false',
                'developer_data': 'false',
                'sparkline': 'false'
            }

            response = self.get_with_retry(url, params=params)
            if response:
                coin_data = response.json()
                return coin_data
            else:
                logger.warning(f"Failed to get details for coin {coin_id}")
                return None

        except Exception as e:
            logger.error(f"Error fetching coin details for {coin_id}: {str(e)}")
            return None

    # =========================================================================
    # Data Extraction
    # =========================================================================
    def extract_solana_info(self, coin_data: Dict) -> Optional[Dict[str, str]]:
        """Extract Solana contract address from coin platform metadata.

        Args:
            coin_data: Full coin detail dictionary from the CoinGecko API.

        Returns:
            A dictionary with coin name, symbol, platform, and mint address
            if the coin is deployed on Solana, or None otherwise.
        """
        try:
            platforms = coin_data.get('platforms', {})

            # Check if coin is on Solana
            if 'solana' in platforms:
                solana_address = platforms['solana']
                if solana_address:
                    return {
                        'name': coin_data.get('name', ''),
                        'symbol': coin_data.get('symbol', ''),
                        'coin_id': coin_data.get('id', ''),
                        'platform': 'Solana',
                        'contract_address': solana_address,
                        'mintaddress': solana_address,
                        'successful': 'successful'
                    }

            return None

        except Exception as e:
            logger.error(f"Error extracting Solana info: {str(e)}")
            return None

    # =========================================================================
    # HTML Fallback Scraping
    # =========================================================================
    def scrape_memecoin_page_html(self, page: int = 1) -> List[Dict[str, str]]:
        """Scrape the memecoin category page HTML to discover coin IDs.

        This is a fallback method used when the CoinGecko REST API is
        unavailable or rate-limited.

        Args:
            page: Page number to scrape (1-indexed).

        Returns:
            A list of dictionaries each containing a ``coin_id`` key.
        """
        try:
            url = f"https://www.coingecko.com/en/categories/meme-token"
            if page > 1:
                url += f"?page={page}"

            response = self.get_with_retry(url)
            if not response:
                return []

            # Extract coin IDs from HTML using regex
            content = response.text

            # Look for coin links pattern
            coin_pattern = r'/en/coins/([a-zA-Z0-9\-]+)'
            coin_ids = re.findall(coin_pattern, content)

            # Remove duplicates and filter out common false positives
            unique_ids = list(set(coin_ids))
            filtered_ids = [
                coin_id for coin_id in unique_ids
                if not coin_id.endswith('historical_data') and len(coin_id) > 2
            ]

            logger.info(f"Found {len(filtered_ids)} coin IDs from HTML scraping")
            return [{'coin_id': coin_id} for coin_id in filtered_ids]

        except Exception as e:
            logger.error(f"Error scraping HTML page: {str(e)}")
            return []

    # =========================================================================
    # Processing Pipeline
    # =========================================================================
    def process_all_memecoins(self, max_coins: int = 100) -> List[Dict[str, str]]:
        """Discover and process memecoins to identify Solana deployments.

        Tries the API first; falls back to HTML scraping if the API fails.
        Each discovered coin is inspected for a Solana contract address.

        Args:
            max_coins: Maximum number of coins to process.

        Returns:
            A list of Solana coin info dictionaries.
        """
        solana_coins = []

        # First try API approach
        logger.info("Trying API approach...")
        api_coins = self.get_coins_by_category("meme-token")

        if api_coins:
            coin_ids = [coin['id'] for coin in api_coins[:max_coins]]
        else:
            # Fallback to HTML scraping
            logger.info("API failed, falling back to HTML scraping...")
            scraped_data = self.scrape_memecoin_page_html()
            coin_ids = [item['coin_id'] for item in scraped_data[:max_coins]]

        logger.info(f"Processing {len(coin_ids)} coins for Solana contracts...")

        for i, coin_id in enumerate(coin_ids):
            logger.info(f"Processing coin {i+1}/{len(coin_ids)}: {coin_id}")

            # Get detailed coin information
            coin_details = self.get_coin_details(coin_id)

            if coin_details:
                solana_info = self.extract_solana_info(coin_details)
                if solana_info:
                    solana_coins.append(solana_info)
                    logger.info(f"Found Solana coin: {solana_info['name']} - {solana_info['mintaddress']}")

            # Rate limiting
            time.sleep(1.5)

            # Progress logging
            if (i + 1) % 10 == 0:
                logger.info(f"Progress: {i+1}/{len(coin_ids)}, Found {len(solana_coins)} Solana coins so far")

        logger.info(f"Processing complete. Found {len(solana_coins)} Solana memecoins")
        return solana_coins

    def get_additional_solana_memecoins(self) -> List[Dict[str, str]]:
        """Fetch details for a curated list of known Solana memecoins.

        These coins may not appear in the category listing but are well-known
        Solana memecoins that should be included in the results.

        Returns:
            A list of Solana coin info dictionaries for successfully
            retrieved coins.
        """
        known_solana_memes = [
            'bonk', 'dogwifhat', 'book-of-meme', 'cat-in-a-dogs-world',
            'popcat', 'myro', 'jeo-boden', 'harambe-on-solana',
            'goatseus-maximus', 'peanut-the-squirrel', 'fartcoin'
        ]

        additional_coins = []

        for coin_id in known_solana_memes:
            try:
                coin_details = self.get_coin_details(coin_id)
                if coin_details:
                    solana_info = self.extract_solana_info(coin_details)
                    if solana_info:
                        additional_coins.append(solana_info)
                        logger.info(f"Added known Solana coin: {solana_info['name']}")

                time.sleep(1)
            except Exception as e:
                logger.warning(f"Failed to get {coin_id}: {str(e)}")

        return additional_coins

    # =========================================================================
    # CSV Output
    # =========================================================================
    def save_to_csv(self, coins: List[Dict[str, str]], filename: str = 'solana_memecoins.csv'):
        """Write Solana memecoin results to CSV files.

        Produces two files: a summary CSV containing only mint addresses and
        status tags, and a detailed CSV with all available metadata.

        Args:
            coins: List of coin info dictionaries to persist.
            filename: Path for the summary CSV file.
        """
        if not coins:
            logger.warning("No coins to save")
            return

        # Prepare data for CSV (only mint address and successful tag as requested)
        csv_data = []
        seen_addresses = set()

        for coin in coins:
            if coin.get('mintaddress') and coin['mintaddress'] not in seen_addresses:
                csv_data.append({
                    'mintaddress': coin['mintaddress'],
                    'successful': coin['successful']
                })
                seen_addresses.add(coin['mintaddress'])

        if csv_data:
            df = pd.DataFrame(csv_data)
            df.to_csv(filename, index=False)
            logger.info(f"Saved {len(csv_data)} unique Solana memecoins to {filename}")

            # Also save detailed info for debugging
            detailed_df = pd.DataFrame(coins)
            detailed_df.to_csv(f"detailed_{filename}", index=False)
            logger.info(f"Saved detailed info to detailed_{filename}")

            # Print sample results
            print(f"\nSample results (first 5):")
            print(df.head().to_string(index=False))

        else:
            logger.warning("No valid Solana memecoins with contract addresses found")

    # =========================================================================
    # Entry Point
    # =========================================================================
    def run_full_scrape(self, max_coins: int = 50):
        """Execute the complete scraping pipeline.

        Combines category-based discovery, known-coin supplementation, and
        deduplication before writing results to disk.

        Args:
            max_coins: Maximum number of coins to process from the category
                listing.

        Returns:
            A list of unique Solana memecoin info dictionaries.
        """
        try:
            logger.info("Starting CoinGecko API-based memecoin scraper...")

            # Get memecoins from API/scraping
            solana_coins = self.process_all_memecoins(max_coins)

            # Add known Solana memecoins
            additional_coins = self.get_additional_solana_memecoins()
            solana_coins.extend(additional_coins)

            # Remove duplicates based on mint address
            unique_coins = {}
            for coin in solana_coins:
                addr = coin.get('mintaddress')
                if addr and addr not in unique_coins:
                    unique_coins[addr] = coin

            final_coins = list(unique_coins.values())
            logger.info(f"Total unique Solana memecoins found: {len(final_coins)}")

            # Save to CSV
            self.save_to_csv(final_coins)

            logger.info("Scraping completed successfully!")
            return final_coins

        except Exception as e:
            logger.error(f"Scraping failed: {str(e)}")
            raise


# =============================================================================
# Script Entry Point
# =============================================================================
if __name__ == "__main__":
    scraper = CoinGeckoAPIBasedScraper()
    try:
        results = scraper.run_full_scrape(max_coins=30)  # Start small for testing
        print(f"\nScraping completed! Found {len(results)} Solana memecoins.")
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
    except Exception as e:
        logger.error(f"Scraping failed: {str(e)}")
