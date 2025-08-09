import requests
import time
import re
import csv
from typing import List, Dict, Optional
import logging
import json
import pandas as pd
from urllib.parse import urljoin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('coingecko_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class CoinGeckoAPIBasedScraper:
    """
    A more reliable scraper that uses CoinGecko's API where possible
    and falls back to web scraping for detailed contract information
    """
    
    def __init__(self):
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
        
    def get_with_retry(self, url: str, retries: int = 3, **kwargs) -> Optional[requests.Response]:
        """Make HTTP request with retries"""
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
    
    def get_coins_by_category(self, category_id: str = "meme-token") -> List[Dict]:
        """Get coins by category using CoinGecko API"""
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
        """Get detailed coin information including contract addresses"""
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
    
    def extract_solana_info(self, coin_data: Dict) -> Optional[Dict[str, str]]:
        """Extract Solana contract information from coin data"""
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
    
    def scrape_memecoin_page_html(self, page: int = 1) -> List[Dict[str, str]]:
        """Fallback method: scrape memecoin page HTML for coin IDs"""
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
    
    def process_all_memecoins(self, max_coins: int = 100) -> List[Dict[str, str]]:
        """Process memecoins to find Solana ones"""
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
        """Get additional known Solana memecoins that might be missed"""
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
    
    def save_to_csv(self, coins: List[Dict[str, str]], filename: str = 'solana_memecoins.csv'):
        """Save results to CSV file"""
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
    
    def run_full_scrape(self, max_coins: int = 50):
        """Run the complete scraping process"""
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

if __name__ == "__main__":
    scraper = CoinGeckoAPIBasedScraper()
    try:
        results = scraper.run_full_scrape(max_coins=30)  # Start small for testing
        print(f"\nScraping completed! Found {len(results)} Solana memecoins.")
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
    except Exception as e:
        logger.error(f"Scraping failed: {str(e)}")
