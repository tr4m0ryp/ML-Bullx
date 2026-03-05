#!/usr/bin/env python3
"""
CoinGecko Memecoin Scraper Runner.

Command-line entry point for selecting and executing a scraper variant:
- Supports API-based, HTML-based, and Selenium-based scrapers.
- Provides configurable coin limits, output paths, and headless mode.
- Handles import errors gracefully with dependency guidance.

Author: ML-Bullx Team
Date: 2025-08-01
"""

# =============================================================================
# Standard Library Imports
# =============================================================================
import argparse
import os
import sys
from pathlib import Path


# =============================================================================
# Main Entry Point
# =============================================================================
def main():
    """Parse command-line arguments and dispatch to the selected scraper.

    Supports three scraper backends:
        - ``api``      -- CoinGecko REST API with HTML fallback.
        - ``basic``    -- Pure HTML scraping via BeautifulSoup.
        - ``selenium`` -- Browser-based scraping via Selenium WebDriver.

    Exits with code 1 on import errors, keyboard interrupts, or unhandled
    exceptions.
    """
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


# =============================================================================
# Script Entry Point
# =============================================================================
if __name__ == "__main__":
    main()
