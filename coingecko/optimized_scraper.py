#!/usr/bin/env python3
"""
Optimized CoinGecko Memecoin Scraper.

A streamlined scraper focused on known Solana memecoins with robust rate
limit handling:
- Queries the CoinGecko coin detail API for a curated list of coins.
- Extracts Solana contract addresses from platform metadata.
- Applies exponential backoff on HTTP 429 rate-limit responses.
- Exports deduplicated results to both summary and detailed CSV files.

Author: ML-Bullx Team
Date: 2025-08-01
"""

# =============================================================================
# Standard Library Imports
# =============================================================================
import json
import logging
import time

# =============================================================================
# Third-Party Imports
# =============================================================================
import pandas as pd
import requests

# =============================================================================
# Logging Configuration
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# OptimizedCoinGeckoScraper
# =============================================================================
class OptimizedCoinGeckoScraper:
    """Rate-limit-aware scraper for known Solana memecoins on CoinGecko.

    Instead of crawling the entire memecoin category, this scraper works
    from a curated list of known Solana memecoins and retrieves their
    contract addresses via the CoinGecko detail API.

    Responsibilities:
        - Maintain a curated list of known Solana memecoin IDs.
        - Query coin details with exponential backoff on rate limits.
        - Extract Solana contract addresses from platform metadata.
        - Persist deduplicated results to CSV.
    """

    def __init__(self):
        """Initialize the scraper with a configured HTTP session and coin list."""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        })
        self.api_base = "https://api.coingecko.com/api/v3"
        self.known_solana_memecoins = [
            'bonk', 'dogwifhat', 'book-of-meme', 'cat-in-a-dogs-world',
            'popcat', 'myro', 'goatseus-maximus', 'peanut-the-squirrel',
            'fartcoin', 'moo-deng', 'neiro', 'ponke', 'pudgy-penguins'
        ]

    # =========================================================================
    # API Methods
    # =========================================================================
    def get_coin_details_safe(self, coin_id: str, retries: int = 3):
        """Fetch coin details from the CoinGecko API with retry logic.

        Handles HTTP 429 rate-limit responses with exponential backoff.

        Args:
            coin_id: CoinGecko coin identifier (e.g. ``"bonk"``).
            retries: Maximum number of attempts before giving up.

        Returns:
            A dictionary of coin metadata, or None on failure.
        """
        url = f"{self.api_base}/coins/{coin_id}"
        params = {
            'localization': 'false',
            'tickers': 'false',
            'market_data': 'false',
            'community_data': 'false',
            'developer_data': 'false'
        }

        for attempt in range(retries):
            try:
                response = self.session.get(url, params=params, timeout=10)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    wait_time = (2 ** attempt) * 3
                    logger.warning(f"Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"HTTP {response.status_code} for {coin_id}")
                    return None

            except Exception as e:
                logger.warning(f"Error fetching {coin_id}: {e}")
                time.sleep(2)

        return None

    # =========================================================================
    # Data Extraction
    # =========================================================================
    def extract_solana_contract(self, coin_data):
        """Extract the Solana contract address from coin platform metadata.

        Args:
            coin_data: Full coin detail dictionary from the CoinGecko API.

        Returns:
            A dictionary with coin name, symbol, and mint address if the
            coin is deployed on Solana, or None otherwise.
        """
        try:
            platforms = coin_data.get('platforms', {})

            if 'solana' in platforms:
                address = platforms['solana']
                if address and len(address) >= 32:
                    return {
                        'name': coin_data.get('name', ''),
                        'symbol': coin_data.get('symbol', ''),
                        'coin_id': coin_data.get('id', ''),
                        'mintaddress': address,
                        'successful': 'successful'
                    }
        except Exception as e:
            logger.error(f"Error extracting contract: {e}")

        return None

    # =========================================================================
    # Scraping Pipeline
    # =========================================================================
    def scrape_known_coins(self):
        """Iterate through the known Solana memecoin list and collect addresses.

        Returns:
            A list of dictionaries for coins with valid Solana contract
            addresses.
        """
        results = []

        logger.info(f"Processing {len(self.known_solana_memecoins)} known Solana memecoins...")

        for i, coin_id in enumerate(self.known_solana_memecoins):
            logger.info(f"Processing {i+1}/{len(self.known_solana_memecoins)}: {coin_id}")

            coin_data = self.get_coin_details_safe(coin_id)

            if coin_data:
                solana_info = self.extract_solana_contract(coin_data)
                if solana_info:
                    results.append(solana_info)
                    logger.info(f"[OK] {solana_info['name']}: {solana_info['mintaddress']}")
                else:
                    logger.info(f"[FAIL] {coin_id}: No Solana address found")
            else:
                logger.warning(f"[FAIL] Failed to fetch {coin_id}")

            # Rate limiting
            time.sleep(2)

        return results

    # =========================================================================
    # CSV Output
    # =========================================================================
    def save_results(self, coins, filename='solana_memecoins.csv'):
        """Write results to summary and detailed CSV files.

        Deduplicates by mint address before writing.

        Args:
            coins: List of coin info dictionaries to persist.
            filename: Path for the summary CSV file.

        Returns:
            A ``pandas.DataFrame`` of the deduplicated summary data, or None
            if no coins were provided.
        """
        if not coins:
            logger.warning("No coins to save")
            return

        # Create DataFrame with required columns
        df = pd.DataFrame([{
            'mintaddress': coin['mintaddress'],
            'successful': coin['successful']
        } for coin in coins])

        # Remove duplicates
        df = df.drop_duplicates(subset=['mintaddress'])

        # Save to CSV
        df.to_csv(filename, index=False)
        logger.info(f"Saved {len(df)} unique Solana memecoins to {filename}")

        # Also save detailed version
        detailed_df = pd.DataFrame(coins)
        detailed_df.to_csv(f"detailed_{filename}", index=False)

        # Print sample results
        print(f"\n=== Results ===")
        print(df.to_string(index=False))
        print(f"\nTotal: {len(df)} Solana memecoins")

        return df

    # =========================================================================
    # Entry Point
    # =========================================================================
    def run(self):
        """Execute the optimized scraping pipeline.

        Returns:
            A list of Solana memecoin info dictionaries, or an empty list if
            no results were found.
        """
        try:
            logger.info("Starting optimized CoinGecko scraper...")

            results = self.scrape_known_coins()

            if results:
                self.save_results(results)
                logger.info("Scraping completed successfully!")
                return results
            else:
                logger.warning("No results found")
                return []

        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            raise


# =============================================================================
# Script Entry Point
# =============================================================================
if __name__ == "__main__":
    scraper = OptimizedCoinGeckoScraper()
    try:
        results = scraper.run()
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
    except Exception as e:
        logger.error(f"Error: {e}")
