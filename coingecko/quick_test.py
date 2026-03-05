#!/usr/bin/env python3
"""
CoinGecko API Scraper Integration Test.

Validates the CoinGeckoAPIBasedScraper class with two targeted tests:
- Test 1: Retrieves BONK coin details and extracts its Solana address.
- Test 2: Fetches the memecoin category listing and processes a small
  sample for Solana contract addresses.

Author: ML-Bullx Team
Date: 2025-08-01
"""

# =============================================================================
# Standard Library Imports
# =============================================================================
import os
import sys
import time

# =============================================================================
# Local Imports
# =============================================================================
# Add the current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api_scraper import CoinGeckoAPIBasedScraper


# =============================================================================
# Test Function
# =============================================================================
def quick_test():
    """Run integration tests against the CoinGeckoAPIBasedScraper.

    Executes two tests:
        1. Single-coin lookup for BONK to verify detail retrieval and
           Solana address extraction.
        2. Category listing fetch followed by a small sample of detail
           lookups to confirm end-to-end functionality.

    Results from Test 2 are saved to ``test_results.csv`` when Solana
    coins are found.
    """
    print("=== CoinGecko API Scraper Quick Test ===")

    scraper = CoinGeckoAPIBasedScraper()

    # -------------------------------------------------------------------------
    # Test 1: Single coin detail retrieval
    # -------------------------------------------------------------------------
    print("\nTest 1: Getting BONK details...")
    try:
        bonk_details = scraper.get_coin_details('bonk')
        if bonk_details:
            solana_info = scraper.extract_solana_info(bonk_details)
            if solana_info:
                print(f"[OK] Found BONK: {solana_info['mintaddress']}")
            else:
                print("[FAIL] Failed to extract Solana info from BONK")
        else:
            print("[FAIL] Failed to get BONK details")
    except Exception as e:
        print(f"[FAIL] Error testing BONK: {e}")

    # -------------------------------------------------------------------------
    # Test 2: Category listing and sample processing
    # -------------------------------------------------------------------------
    print("\nTest 2: Getting memecoin category...")
    try:
        memecoins = scraper.get_coins_by_category("meme-token")
        print(f"[OK] Found {len(memecoins)} memecoins from API")

        # Test first 5 coins for Solana addresses
        solana_found = []
        for coin in memecoins[:5]:
            try:
                details = scraper.get_coin_details(coin['id'])
                if details:
                    solana_info = scraper.extract_solana_info(details)
                    if solana_info:
                        solana_found.append(solana_info)
                        print(f"  [OK] Solana coin: {solana_info['name']} - {solana_info['mintaddress']}")
                time.sleep(1)  # Rate limiting
            except Exception as e:
                print(f"  [FAIL] Error with {coin['id']}: {e}")

        print(f"\n[OK] Found {len(solana_found)} Solana memecoins in test sample")

        # Save test results
        if solana_found:
            scraper.save_to_csv(solana_found, 'test_results.csv')
            print("[OK] Saved test results to test_results.csv")

    except Exception as e:
        print(f"[FAIL] Error getting memecoins: {e}")

    print("\n=== Test Complete ===")


# =============================================================================
# Script Entry Point
# =============================================================================
if __name__ == "__main__":
    quick_test()
