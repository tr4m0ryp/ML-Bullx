#!/usr/bin/env python3
"""
Simple runner script for CoinGecko memecoin scrapers
"""

import argparse
import sys
import os
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Run CoinGecko memecoin scraper")
    parser.add_argument(
        "--scraper", 
        choices=["api", "basic", "selenium"],
        default="api",
        help="Which scraper to use (default: api)"
    )
    parser.add_argument(
        "--max-coins",
        type=int,
        default=50,
        help="Maximum number of coins to process (default: 50)"
    )
    parser.add_argument(
        "--output",
        default="solana_memecoins.csv",
        help="Output filename (default: solana_memecoins.csv)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless mode (for selenium scraper)"
    )
    
    args = parser.parse_args()
    
    print(f"Starting {args.scraper} scraper...")
    print(f"Max coins: {args.max_coins}")
    print(f"Output file: {args.output}")
    
    try:
        if args.scraper == "api":
            from api_scraper import CoinGeckoAPIBasedScraper
            scraper = CoinGeckoAPIBasedScraper()
            results = scraper.run_full_scrape(max_coins=args.max_coins)
            
        elif args.scraper == "basic":
            from memecoin_scraper import CoinGeckoMemecoinScraper
            scraper = CoinGeckoMemecoinScraper()
            scraper.run_full_scrape()
            results = []
            
        elif args.scraper == "selenium":
            from selenium_scraper import SeleniumCoinGeckoScraper
            scraper = SeleniumCoinGeckoScraper(headless=args.headless)
            scraper.run_full_scrape(max_pages=5, max_coins=args.max_coins)
            results = []
        
        print(f"\nScraping completed successfully!")
        if results:
            print(f"Found {len(results)} Solana memecoins.")
        print(f"Check {args.output} for results.")
        
    except ImportError as e:
        print(f"Error importing scraper modules: {e}")
        print("Make sure you have installed all dependencies:")
        print("pip install -r requirements.txt")
        sys.exit(1)
        
    except KeyboardInterrupt:
        print("\nScraping interrupted by user")
        sys.exit(1)
        
    except Exception as e:
        print(f"Scraping failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
