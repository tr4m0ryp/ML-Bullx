#!/usr/bin/env python3
"""
Quick test of the CoinGecko API scraper
"""

import sys
import os

# Add the current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api_scraper import CoinGeckoAPIBasedScraper
import time

def quick_test():
    """Quick test with just a few known coins"""
    print("=== CoinGecko API Scraper Quick Test ===")
    
    scraper = CoinGeckoAPIBasedScraper()
    
    # Test 1: Try to get a specific coin's details
    print("\nTest 1: Getting BONK details...")
    try:
        bonk_details = scraper.get_coin_details('bonk')
        if bonk_details:
            solana_info = scraper.extract_solana_info(bonk_details)
            if solana_info:
                print(f"✓ Found BONK: {solana_info['mintaddress']}")
            else:
                print("✗ Failed to extract Solana info from BONK")
        else:
            print("✗ Failed to get BONK details")
    except Exception as e:
        print(f"✗ Error testing BONK: {e}")
    
    # Test 2: Get a few memecoins from API
    print("\nTest 2: Getting memecoin category...")
    try:
        memecoins = scraper.get_coins_by_category("meme-token")
        print(f"✓ Found {len(memecoins)} memecoins from API")
        
        # Test first 3 coins for Solana addresses
        solana_found = []
        for coin in memecoins[:5]:
            try:
                details = scraper.get_coin_details(coin['id'])
                if details:
                    solana_info = scraper.extract_solana_info(details)
                    if solana_info:
                        solana_found.append(solana_info)
                        print(f"  ✓ Solana coin: {solana_info['name']} - {solana_info['mintaddress']}")
                time.sleep(1)  # Rate limiting
            except Exception as e:
                print(f"  ✗ Error with {coin['id']}: {e}")
        
        print(f"\n✓ Found {len(solana_found)} Solana memecoins in test sample")
        
        # Save test results
        if solana_found:
            scraper.save_to_csv(solana_found, 'test_results.csv')
            print("✓ Saved test results to test_results.csv")
        
    except Exception as e:
        print(f"✗ Error getting memecoins: {e}")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    quick_test()
