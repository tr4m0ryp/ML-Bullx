"""
CoinGecko HTML-Based Memecoin Scraper.

Discovers Solana memecoins by scraping the CoinGecko website directly:
- Crawls paginated memecoin category pages using BeautifulSoup.
- Extracts individual coin URLs and navigates to each detail page.
- Identifies Solana contract addresses via multiple HTML parsing strategies.
- Supports parallel processing of coin detail pages.
- Exports filtered Solana-only results to CSV.

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
from typing import Dict, List, Optional, Tuple

# =============================================================================
# Third-Party Imports
# =============================================================================
import pandas as pd
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

# =============================================================================
# Logging Configuration
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('memecoin_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# CoinGeckoMemecoinScraper
# =============================================================================
class CoinGeckoMemecoinScraper:
    """HTML scraper for extracting Solana memecoin data from CoinGecko.

    Navigates the CoinGecko meme-token category pages, follows links to
    individual coin pages, and applies multiple heuristics to locate Solana
    contract addresses in the rendered HTML.

    Responsibilities:
        - Discover all pagination URLs for the memecoin category.
        - Parse coin links from category table rows.
        - Extract contract addresses from individual coin detail pages.
        - Filter results to Solana-only deployments.
        - Persist results to CSV.
    """

    def __init__(self):
        """Initialize the scraper with a configured HTTP session."""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        self.base_url = "https://www.coingecko.com"
        self.memecoin_url = "https://www.coingecko.com/en/categories/meme-token"

    # =========================================================================
    # HTTP Helpers
    # =========================================================================
    def get_page_content(self, url: str, retries: int = 3) -> Optional[BeautifulSoup]:
        """Fetch a page and return its parsed HTML tree.

        Applies rate limiting and exponential backoff between retries.

        Args:
            url: Target URL to fetch.
            retries: Maximum number of attempts before giving up.

        Returns:
            A ``BeautifulSoup`` object for the page, or None if all attempts
            failed.
        """
        for attempt in range(retries):
            try:
                time.sleep(1)  # Rate limiting
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return BeautifulSoup(response.content, 'html.parser')
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {str(e)}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"All attempts failed for {url}")
                    return None

    # =========================================================================
    # Category Page Parsing
    # =========================================================================
    def extract_coin_links_from_page(self, page_url: str) -> List[Dict[str, str]]:
        """Extract coin links from a memecoin category page.

        Parses table rows for anchor tags pointing to ``/en/coins/`` paths,
        deduplicating by coin ID.

        Args:
            page_url: Full URL of the category page to scrape.

        Returns:
            A deduplicated list of dictionaries with ``name``, ``coin_id``,
            and ``url`` keys.
        """
        soup = self.get_page_content(page_url)
        if not soup:
            return []

        coin_links = []

        # Look for table rows containing coin information
        rows = soup.find_all('tr')

        for row in rows:
            # Look for coin links within each row
            coin_link_tags = row.find_all('a', href=lambda x: x and '/en/coins/' in x)

            for link_tag in coin_link_tags:
                href = link_tag.get('href')
                if href and '/en/coins/' in href and not href.endswith('/historical_data'):
                    coin_name = link_tag.get_text(strip=True)
                    coin_url = urljoin(self.base_url, href)

                    # Extract coin ID from URL
                    coin_id = href.split('/en/coins/')[-1].split('#')[0].split('?')[0]

                    if coin_name and coin_id:
                        coin_links.append({
                            'name': coin_name,
                            'coin_id': coin_id,
                            'url': coin_url
                        })

        # Remove duplicates based on coin_id
        unique_coins = {}
        for coin in coin_links:
            if coin['coin_id'] not in unique_coins:
                unique_coins[coin['coin_id']] = coin

        logger.info(f"Found {len(unique_coins)} unique coins on page {page_url}")
        return list(unique_coins.values())

    def get_all_memecoin_pages(self) -> List[str]:
        """Discover all pagination URLs for the memecoin category.

        Parses the first category page for pagination links and infers
        additional page URLs from the highest page number found.

        Returns:
            A sorted list of unique category page URLs.
        """
        soup = self.get_page_content(self.memecoin_url)
        if not soup:
            return [self.memecoin_url]

        pages = [self.memecoin_url]

        # Look for pagination links
        pagination_links = soup.find_all('a', href=lambda x: x and 'meme-token?page=' in x)

        for link in pagination_links:
            href = link.get('href')
            if href:
                page_url = urljoin(self.base_url, href)
                if page_url not in pages:
                    pages.append(page_url)

        # Also try to find the last page number from text
        page_numbers = []
        for link in soup.find_all('a', href=lambda x: x and 'meme-token?page=' in x):
            text = link.get_text(strip=True)
            if text.isdigit():
                page_numbers.append(int(text))

        if page_numbers:
            max_page = max(page_numbers)
            for i in range(2, min(max_page + 1, 51)):  # Limit to 50 pages for safety
                page_url = f"{self.memecoin_url}?page={i}"
                if page_url not in pages:
                    pages.append(page_url)

        logger.info(f"Found {len(pages)} pages to scrape")
        return sorted(set(pages))

    # =========================================================================
    # Coin Detail Extraction
    # =========================================================================
    def extract_coin_details(self, coin_info: Dict[str, str]) -> Optional[Dict[str, str]]:
        """Extract Solana contract information from an individual coin page.

        Applies three progressively broader strategies to locate a Solana
        contract address:
            1. Dedicated contract sections with Solana platform images.
            2. Full-page text search for the word "solana" plus base58 patterns.
            3. Raw base58 pattern matching across the entire page text.

        Args:
            coin_info: Dictionary with ``name``, ``coin_id``, and ``url`` keys.

        Returns:
            A dictionary with coin metadata and contract address, or None on
            failure.
        """
        try:
            soup = self.get_page_content(coin_info['url'])
            if not soup:
                return None

            result = {
                'name': coin_info['name'],
                'coin_id': coin_info['coin_id'],
                'url': coin_info['url'],
                'platform': None,
                'contract_address': None,
                'is_solana': False,
                'successful': 'successful'
            }

            # Method 1: Look for contract section
            contract_sections = soup.find_all(['div', 'section'], class_=lambda x: x and 'contract' in x.lower() if x else False)

            for section in contract_sections:
                # Look for Solana platform indicator
                platform_img = section.find('img', alt=lambda x: x and 'solana' in x.lower() if x else False)
                if platform_img:
                    result['platform'] = 'Solana'
                    result['is_solana'] = True

                    # Look for contract address
                    contract_text = section.get_text()
                    # Solana addresses are typically 32-44 characters of base58
                    solana_address_match = re.search(r'[1-9A-HJ-NP-Za-km-z]{32,44}', contract_text)
                    if solana_address_match:
                        result['contract_address'] = solana_address_match.group()
                        break

            # Method 2: Look for platform information in the page
            if not result['platform']:
                page_text = soup.get_text().lower()
                if 'solana' in page_text:
                    result['platform'] = 'Solana'
                    result['is_solana'] = True

                    # Try to find contract address in the full text
                    full_text = soup.get_text()
                    solana_address_match = re.search(r'[1-9A-HJ-NP-Za-km-z]{32,44}', full_text)
                    if solana_address_match:
                        result['contract_address'] = solana_address_match.group()

            # Method 3: Look for specific contract address patterns in the HTML
            if not result['contract_address'] and result['is_solana']:
                all_text = soup.get_text()
                potential_addresses = re.findall(r'[1-9A-HJ-NP-Za-km-z]{32,44}', all_text)

                # Filter out obvious non-addresses (like very long strings)
                for addr in potential_addresses:
                    if 32 <= len(addr) <= 44:
                        result['contract_address'] = addr
                        break

            logger.info(f"Processed {coin_info['name']}: Solana={result['is_solana']}, Address={result['contract_address']}")
            return result

        except Exception as e:
            logger.error(f"Error processing {coin_info['name']}: {str(e)}")
            return None

    # =========================================================================
    # Parallel Scraping Pipeline
    # =========================================================================
    def scrape_all_memecoins(self, max_workers: int = 5) -> List[Dict[str, str]]:
        """Scrape all memecoins using parallel page processing.

        Collects coin links from category pages sequentially, then processes
        individual coin detail pages concurrently using a thread pool.

        Args:
            max_workers: Maximum number of concurrent threads for detail
                page scraping.

        Returns:
            A list of coin detail dictionaries for all successfully
            processed coins.
        """
        logger.info("Starting memecoin scraping process...")

        # Get all pagination pages
        all_pages = self.get_all_memecoin_pages()

        # Extract coin links from all pages
        all_coins = []
        for page_url in all_pages[:10]:  # Limit to first 10 pages for safety
            logger.info(f"Scraping page: {page_url}")
            coins_on_page = self.extract_coin_links_from_page(page_url)
            all_coins.extend(coins_on_page)
            time.sleep(2)  # Rate limiting between pages

        logger.info(f"Found {len(all_coins)} total coins to process")

        # Process individual coin pages with threading
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_coin = {
                executor.submit(self.extract_coin_details, coin): coin
                for coin in all_coins[:100]  # Limit for testing
            }

            # Process completed tasks
            for future in as_completed(future_to_coin):
                result = future.result()
                if result:
                    results.append(result)

                # Progress logging
                if len(results) % 10 == 0:
                    logger.info(f"Processed {len(results)}/{len(all_coins)} coins")

        logger.info(f"Successfully processed {len(results)} coins")
        return results

    # =========================================================================
    # Filtering
    # =========================================================================
    def filter_solana_coins(self, coins: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Filter a list of coins to include only Solana deployments.

        Args:
            coins: List of coin detail dictionaries.

        Returns:
            A filtered list containing only coins where ``is_solana`` is True.
        """
        solana_coins = [coin for coin in coins if coin.get('is_solana', False)]
        logger.info(f"Filtered {len(solana_coins)} Solana coins from {len(coins)} total coins")
        return solana_coins

    # =========================================================================
    # CSV Output
    # =========================================================================
    def save_to_csv(self, coins: List[Dict[str, str]], filename: str = 'solana_memecoins.csv'):
        """Write Solana memecoin results to a CSV file.

        Only coins with a non-empty contract address are included.

        Args:
            coins: List of Solana coin dictionaries to persist.
            filename: Output CSV file path.
        """
        if not coins:
            logger.warning("No coins to save")
            return

        # Prepare data for CSV (only mint address and successful tag as requested)
        csv_data = []
        for coin in coins:
            if coin.get('contract_address'):
                csv_data.append({
                    'mintaddress': coin['contract_address'],
                    'successful': coin['successful']
                })

        if csv_data:
            df = pd.DataFrame(csv_data)
            df.to_csv(filename, index=False)
            logger.info(f"Saved {len(csv_data)} Solana memecoins to {filename}")
        else:
            logger.warning("No valid Solana memecoins with contract addresses found")

    # =========================================================================
    # Entry Point
    # =========================================================================
    def run_full_scrape(self) -> None:
        """Execute the complete scraping pipeline.

        Scrapes category pages, extracts coin details in parallel, filters
        for Solana, and saves results to CSV.
        """
        try:
            logger.info("Starting CoinGecko memecoin scraper...")

            # Scrape all memecoins
            all_coins = self.scrape_all_memecoins()

            # Filter for Solana only
            solana_coins = self.filter_solana_coins(all_coins)

            # Save to CSV
            self.save_to_csv(solana_coins)

            logger.info("Scraping completed successfully!")

        except Exception as e:
            logger.error(f"Scraping failed: {str(e)}")
            raise


# =============================================================================
# Script Entry Point
# =============================================================================
if __name__ == "__main__":
    scraper = CoinGeckoMemecoinScraper()
    scraper.run_full_scrape()
