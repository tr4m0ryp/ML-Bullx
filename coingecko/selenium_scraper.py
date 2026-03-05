"""
Selenium-Based CoinGecko Memecoin Scraper.

Uses a headless Chrome browser to scrape JavaScript-rendered CoinGecko pages:
- Navigates paginated memecoin category tables via Selenium WebDriver.
- Extracts coin links and follows each to its detail page.
- Applies multiple DOM inspection strategies to locate Solana contract addresses.
- Exports deduplicated results to both summary and detailed CSV files.

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
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# =============================================================================
# Logging Configuration
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('selenium_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# SeleniumCoinGeckoScraper
# =============================================================================
class SeleniumCoinGeckoScraper:
    """Browser-driven scraper for extracting Solana memecoin data from CoinGecko.

    Launches a Chrome WebDriver instance to handle JavaScript-heavy pages
    that cannot be scraped reliably with plain HTTP requests.  Navigates
    category tables, follows coin links, and applies multiple DOM inspection
    strategies to locate Solana contract addresses.

    Responsibilities:
        - Manage the Chrome WebDriver lifecycle.
        - Paginate through the memecoin category table.
        - Extract coin links from rendered table rows.
        - Inspect individual coin pages for Solana contract info.
        - Persist results to CSV files.
    """

    def __init__(self, headless: bool = True):
        """Initialize the scraper and launch the WebDriver.

        Args:
            headless: If True, run Chrome without a visible window.
        """
        self.setup_driver(headless)
        self.base_url = "https://www.coingecko.com"
        self.memecoin_url = "https://www.coingecko.com/en/categories/meme-token"

    # =========================================================================
    # WebDriver Setup
    # =========================================================================
    def setup_driver(self, headless: bool = True):
        """Configure and launch the Chrome WebDriver.

        Args:
            headless: If True, run Chrome in headless mode.

        Raises:
            Exception: If the WebDriver cannot be initialized.
        """
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.wait = WebDriverWait(self.driver, 10)
            logger.info("WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {str(e)}")
            raise

    # =========================================================================
    # Navigation Helpers
    # =========================================================================
    def get_page_safely(self, url: str, retries: int = 3) -> bool:
        """Navigate to a URL with retry logic.

        Args:
            url: Target URL to load in the browser.
            retries: Maximum number of navigation attempts.

        Returns:
            True if the page loaded successfully, False otherwise.
        """
        for attempt in range(retries):
            try:
                self.driver.get(url)
                time.sleep(3)  # Wait for page load
                return True
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {str(e)}")
                if attempt < retries - 1:
                    time.sleep(5)
                else:
                    logger.error(f"All attempts failed for {url}")
                    return False
        return False

    # =========================================================================
    # Category Table Parsing
    # =========================================================================
    def extract_coins_from_table(self) -> List[Dict[str, str]]:
        """Extract coin information from the currently loaded category table.

        Waits for table rows to render, then scans each row for coin links
        matching the ``/en/coins/`` URL pattern.

        Returns:
            A deduplicated list of dictionaries with ``name``, ``coin_id``,
            and ``url`` keys.
        """
        coins = []
        try:
            # Wait for table to load
            table_rows = self.wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "tr"))
            )

            for row in table_rows:
                try:
                    # Look for coin links in the row
                    coin_links = row.find_elements(By.CSS_SELECTOR, "a[href*='/en/coins/']")

                    for link in coin_links:
                        href = link.get_attribute('href')
                        if href and '/en/coins/' in href and not href.endswith('/historical_data'):
                            coin_name = link.text.strip()
                            coin_id = href.split('/en/coins/')[-1].split('#')[0].split('?')[0]

                            if coin_name and coin_id and len(coin_name) > 1:
                                coins.append({
                                    'name': coin_name,
                                    'coin_id': coin_id,
                                    'url': href
                                })
                                break  # Only get the first valid coin link per row

                except Exception as e:
                    continue  # Skip problematic rows

            # Remove duplicates
            unique_coins = {}
            for coin in coins:
                if coin['coin_id'] not in unique_coins:
                    unique_coins[coin['coin_id']] = coin

            logger.info(f"Extracted {len(unique_coins)} coins from current page")
            return list(unique_coins.values())

        except TimeoutException:
            logger.error("Timeout waiting for table to load")
            return []

    def get_next_page_url(self) -> Optional[str]:
        """Determine the URL of the next category page, if one exists.

        Inspects pagination links on the current page and returns the first
        link whose page number exceeds the current page number.

        Returns:
            The next page URL as a string, or None if no further pages exist.
        """
        try:
            next_buttons = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='meme-token?page=']")
            current_url = self.driver.current_url

            for button in next_buttons:
                href = button.get_attribute('href')
                if href and href != current_url:
                    # Check if this is actually a next page (higher page number)
                    if 'page=' in href:
                        current_page = 1
                        if 'page=' in current_url:
                            current_page = int(current_url.split('page=')[1].split('&')[0])

                        next_page = int(href.split('page=')[1].split('&')[0])
                        if next_page > current_page:
                            return href

            return None
        except Exception as e:
            logger.error(f"Error getting next page URL: {str(e)}")
            return None

    # =========================================================================
    # Coin Detail Extraction
    # =========================================================================
    def extract_coin_contract_info(self, coin_url: str) -> Optional[Dict[str, str]]:
        """Extract Solana contract information from an individual coin page.

        Applies four progressively broader strategies:
            1. DOM elements with ``Contract`` text or ``contract`` CSS class.
            2. Image elements with Solana alt-text or source URLs.
            3. Full page-source regex scan for base58 addresses.
            4. Broad page-text search for the word "solana".

        Args:
            coin_url: Full URL of the coin detail page.

        Returns:
            A dictionary with ``platform``, ``contract_address``, and
            ``is_solana`` keys, or None on failure.
        """
        try:
            if not self.get_page_safely(coin_url):
                return None

            result = {
                'platform': None,
                'contract_address': None,
                'is_solana': False
            }

            # Method 1: Look for contract section
            try:
                contract_elements = self.driver.find_elements(
                    By.XPATH,
                    "//*[contains(text(), 'Contract') or contains(@class, 'contract')]"
                )

                for element in contract_elements:
                    parent = element.find_element(By.XPATH, "./..")
                    contract_text = parent.text

                    # Look for Solana indicator
                    if 'solana' in contract_text.lower():
                        result['platform'] = 'Solana'
                        result['is_solana'] = True

                        # Extract Solana address pattern
                        solana_match = re.search(r'[1-9A-HJ-NP-Za-km-z]{32,44}', contract_text)
                        if solana_match:
                            result['contract_address'] = solana_match.group()
                            break
            except:
                pass

            # Method 2: Look for platform images/icons
            if not result['is_solana']:
                try:
                    solana_images = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        "img[alt*='solana' i], img[src*='solana' i]"
                    )

                    if solana_images:
                        result['platform'] = 'Solana'
                        result['is_solana'] = True

                        # Look for contract address near the image
                        for img in solana_images:
                            parent = img.find_element(By.XPATH, "./../../..")
                            parent_text = parent.text
                            solana_match = re.search(r'[1-9A-HJ-NP-Za-km-z]{32,44}', parent_text)
                            if solana_match:
                                result['contract_address'] = solana_match.group()
                                break
                except:
                    pass

            # Method 3: Search page source for Solana addresses
            if result['is_solana'] and not result['contract_address']:
                try:
                    page_source = self.driver.page_source
                    solana_addresses = re.findall(r'[1-9A-HJ-NP-Za-km-z]{32,44}', page_source)

                    # Filter for likely contract addresses (avoid very long strings)
                    for addr in solana_addresses:
                        if 32 <= len(addr) <= 44 and not addr.isdigit():
                            result['contract_address'] = addr
                            break
                except:
                    pass

            # Method 4: Look for any mention of Solana in page text
            if not result['is_solana']:
                try:
                    page_text = self.driver.page_source.lower()
                    if 'solana' in page_text:
                        result['platform'] = 'Solana'
                        result['is_solana'] = True

                        # Try to extract address from full page
                        addresses = re.findall(r'[1-9A-HJ-NP-Za-km-z]{32,44}', self.driver.page_source)
                        for addr in addresses:
                            if 32 <= len(addr) <= 44:
                                result['contract_address'] = addr
                                break
                except:
                    pass

            return result

        except Exception as e:
            logger.error(f"Error extracting contract info from {coin_url}: {str(e)}")
            return None

    # =========================================================================
    # Multi-Page Scraping
    # =========================================================================
    def scrape_memecoin_pages(self, max_pages: int = 10) -> List[Dict[str, str]]:
        """Scrape multiple pages of the memecoin category table.

        Navigates through pagination links until ``max_pages`` is reached or
        no further pages are available.

        Args:
            max_pages: Maximum number of category pages to scrape.

        Returns:
            A combined list of coin dictionaries from all scraped pages.
        """
        all_coins = []
        page_count = 0

        # Start with first page
        if not self.get_page_safely(self.memecoin_url):
            return []

        while page_count < max_pages:
            logger.info(f"Scraping page {page_count + 1}")

            # Extract coins from current page
            coins_on_page = self.extract_coins_from_table()
            all_coins.extend(coins_on_page)

            page_count += 1

            # Try to go to next page
            next_url = self.get_next_page_url()
            if not next_url:
                logger.info("No more pages found")
                break

            if not self.get_page_safely(next_url):
                logger.error("Failed to load next page")
                break

            time.sleep(3)  # Rate limiting

        logger.info(f"Scraped {len(all_coins)} coins from {page_count} pages")
        return all_coins

    # =========================================================================
    # Coin Processing
    # =========================================================================
    def process_coins_for_solana(self, coins: List[Dict[str, str]], max_coins: int = 50) -> List[Dict[str, str]]:
        """Visit individual coin pages and collect Solana contract info.

        Args:
            coins: List of coin dictionaries with ``name``, ``coin_id``, and
                ``url`` keys.
            max_coins: Maximum number of coins to process.

        Returns:
            A list of enriched dictionaries for coins deployed on Solana.
        """
        solana_coins = []

        for i, coin in enumerate(coins[:max_coins]):
            logger.info(f"Processing coin {i+1}/{min(len(coins), max_coins)}: {coin['name']}")

            contract_info = self.extract_coin_contract_info(coin['url'])

            if contract_info and contract_info['is_solana']:
                result = {
                    'name': coin['name'],
                    'coin_id': coin['coin_id'],
                    'url': coin['url'],
                    'platform': contract_info['platform'],
                    'contract_address': contract_info['contract_address'],
                    'mintaddress': contract_info['contract_address'],
                    'successful': 'successful'
                }
                solana_coins.append(result)
                logger.info(f"Found Solana coin: {coin['name']} - {contract_info['contract_address']}")

            time.sleep(2)  # Rate limiting

        logger.info(f"Found {len(solana_coins)} Solana coins")
        return solana_coins

    # =========================================================================
    # CSV Output
    # =========================================================================
    def save_to_csv(self, coins: List[Dict[str, str]], filename: str = 'solana_memecoins.csv'):
        """Write Solana memecoin results to CSV files.

        Produces two files: a summary CSV with mint addresses and status tags,
        and a detailed CSV with all available metadata.

        Args:
            coins: List of Solana coin dictionaries to persist.
            filename: Path for the summary CSV file.
        """
        if not coins:
            logger.warning("No coins to save")
            return

        # Prepare data for CSV (only mint address and successful tag as requested)
        csv_data = []
        for coin in coins:
            if coin.get('mintaddress'):
                csv_data.append({
                    'mintaddress': coin['mintaddress'],
                    'successful': coin['successful']
                })

        if csv_data:
            df = pd.DataFrame(csv_data)
            df.to_csv(filename, index=False)
            logger.info(f"Saved {len(csv_data)} Solana memecoins to {filename}")

            # Also save detailed info for debugging
            detailed_df = pd.DataFrame(coins)
            detailed_df.to_csv(f"detailed_{filename}", index=False)
            logger.info(f"Saved detailed info to detailed_{filename}")
        else:
            logger.warning("No valid Solana memecoins with contract addresses found")

    # =========================================================================
    # Entry Point
    # =========================================================================
    def run_full_scrape(self, max_pages: int = 5, max_coins: int = 30):
        """Execute the complete Selenium-based scraping pipeline.

        Scrapes category pages, processes individual coins for Solana
        contracts, and saves results to CSV.

        Args:
            max_pages: Maximum number of category pages to scrape.
            max_coins: Maximum number of individual coins to inspect.
        """
        try:
            logger.info("Starting Selenium-based CoinGecko memecoin scraper...")

            # Scrape coin list from pages
            all_coins = self.scrape_memecoin_pages(max_pages)

            if not all_coins:
                logger.error("No coins found to process")
                return

            # Process individual coins for Solana contracts
            solana_coins = self.process_coins_for_solana(all_coins, max_coins)

            # Save to CSV
            self.save_to_csv(solana_coins)

            logger.info("Scraping completed successfully!")

        except Exception as e:
            logger.error(f"Scraping failed: {str(e)}")
            raise
        finally:
            self.close()

    # =========================================================================
    # Resource Cleanup
    # =========================================================================
    def close(self):
        """Shut down the WebDriver and release browser resources."""
        try:
            self.driver.quit()
            logger.info("WebDriver closed")
        except:
            pass


# =============================================================================
# Script Entry Point
# =============================================================================
if __name__ == "__main__":
    scraper = SeleniumCoinGeckoScraper(headless=True)
    try:
        scraper.run_full_scrape(max_pages=3, max_coins=20)  # Start with small numbers for testing
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        scraper.close()
    except Exception as e:
        logger.error(f"Scraping failed: {str(e)}")
        scraper.close()
