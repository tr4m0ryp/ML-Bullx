#!/usr/bin/env python3
"""
Minimal CoinGecko API Validation Test.

Performs a quick smoke test against the CoinGecko coin detail API:
- Queries a small set of known Solana memecoins.
- Verifies that Solana contract addresses can be extracted.
- Writes results to a CSV file for manual inspection.

Author: ML-Bullx Team
Date: 2025-08-01
"""

# =============================================================================
# Third-Party Imports
# =============================================================================
import pandas as pd
import requests


# =============================================================================
# Test Function
# =============================================================================
def quick_solana_test():
    """Run a minimal validation against a handful of known Solana memecoins.

    Queries the CoinGecko ``/coins/{id}`` endpoint for each test coin,
    checks for a Solana entry in the ``platforms`` field, and prints
    diagnostic output.  Successful results are saved to
    ``quick_test_results.csv``.
    """

    # Known Solana memecoins with their expected addresses
    test_coins = ['bonk', 'dogwifhat', 'popcat']

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
    })

    results = []

    for coin_id in test_coins:
        print(f"Testing {coin_id}...")

        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
            response = session.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                platforms = data.get('platforms', {})

                if 'solana' in platforms:
                    address = platforms['solana']
                    if address:
                        results.append({
                            'mintaddress': address,
                            'successful': 'successful'
                        })
                        print(f"  [OK] Found: {address}")
                    else:
                        print(f"  [FAIL] No address")
                else:
                    print(f"  [FAIL] Not on Solana")
            else:
                print(f"  [FAIL] API error: {response.status_code}")

        except Exception as e:
            print(f"  [FAIL] Error: {e}")

    if results:
        df = pd.DataFrame(results)
        df.to_csv('quick_test_results.csv', index=False)
        print(f"\n=== Results ===")
        print(df.to_string(index=False))
        print(f"\nSaved {len(results)} results to quick_test_results.csv")
    else:
        print("No results found")


# =============================================================================
# Script Entry Point
# =============================================================================
if __name__ == "__main__":
    quick_solana_test()
