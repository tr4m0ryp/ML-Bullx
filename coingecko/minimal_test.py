#!/usr/bin/env python3
"""
Minimal test scraper to quickly validate the approach
"""

import requests
import pandas as pd

def quick_solana_test():
    """Quick test with just a few coins"""
    
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
                        print(f"  ✓ Found: {address}")
                    else:
                        print(f"  ✗ No address")
                else:
                    print(f"  ✗ Not on Solana")
            else:
                print(f"  ✗ API error: {response.status_code}")
                
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    if results:
        df = pd.DataFrame(results)
        df.to_csv('quick_test_results.csv', index=False)
        print(f"\n=== Results ===")
        print(df.to_string(index=False))
        print(f"\nSaved {len(results)} results to quick_test_results.csv")
    else:
        print("No results found")

if __name__ == "__main__":
    quick_solana_test()
