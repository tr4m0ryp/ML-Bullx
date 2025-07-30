"""
Script om ECHTE data op te halen van tokens via DexScreener API
"""

import requests
import time
import json
from datetime import datetime
import pandas as pd

def get_real_token_data(mint_address):
    """Haal echte data op van DexScreener"""
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mint_address}"
        
        response = requests.get(url)
        time.sleep(0.5)  # Rate limiting
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('pairs'):
                # Neem de pair met meeste liquiditeit
                pair = max(data['pairs'], key=lambda p: float(p.get('liquidity', {}).get('usd', 0)))
                
                return {
                    'mint_address': mint_address,
                    'found': True,
                    'current_price_usd': float(pair.get('priceUsd', 0)),
                    'price_change_5m': pair.get('priceChange', {}).get('m5'),
                    'price_change_1h': pair.get('priceChange', {}).get('h1'),
                    'price_change_6h': pair.get('priceChange', {}).get('h6'),
                    'price_change_24h': pair.get('priceChange', {}).get('h24'),
                    'volume_5m': float(pair.get('volume', {}).get('m5', 0)),
                    'volume_1h': float(pair.get('volume', {}).get('h1', 0)),
                    'volume_6h': float(pair.get('volume', {}).get('h6', 0)),
                    'volume_24h': float(pair.get('volume', {}).get('h24', 0)),
                    'liquidity_usd': float(pair.get('liquidity', {}).get('usd', 0)),
                    'market_cap': float(pair.get('marketCap', 0)),
                    'fdv': float(pair.get('fdv', 0)),
                    'pair_created_at': pair.get('pairCreatedAt'),
                    'dex_id': pair.get('dexId'),
                    'pair_address': pair.get('pairAddress')
                }
            else:
                return {
                    'mint_address': mint_address,
                    'found': False,
                    'error': 'No trading pairs found'
                }
        else:
            return {
                'mint_address': mint_address,
                'found': False,
                'error': f'HTTP {response.status_code}'
            }
            
    except Exception as e:
        return {
            'mint_address': mint_address,
            'found': False,
            'error': str(e)
        }

def analyze_first_tokens(num_tokens=20):
    """Analyseer de eerste X tokens met echte data"""
    
    # Lees de successful tokens
    with open('successful_tokens.txt', 'r') as f:
        tokens = [line.strip() for line in f.readlines()[:num_tokens]]
    
    print(f"🔍 Analyseren van {len(tokens)} tokens met ECHTE data...")
    print("=" * 60)
    
    results = []
    
    for i, token in enumerate(tokens, 1):
        print(f"📊 {i}/{len(tokens)}: {token[:20]}...")
        
        data = get_real_token_data(token)
        results.append(data)
        
        if data['found']:
            print(f"   ✅ Prijs: ${data['current_price_usd']:.8f}")
            print(f"   📈 24h: {data['price_change_24h']}%")
            print(f"   💰 Volume 24h: ${data['volume_24h']:,.0f}")
            print(f"   💧 Liquiditeit: ${data['liquidity_usd']:,.0f}")
        else:
            print(f"   ❌ Niet gevonden: {data['error']}")
        
        print("-" * 40)
    
    # Sla resultaten op
    df = pd.DataFrame(results)
    df.to_csv('real_token_analysis.csv', index=False)
    
    # Maak leesbare samenvatting
    with open('real_token_analysis.txt', 'w') as f:
        f.write("ECHTE DATA ANALYSE VAN 'SUCCESSFUL' TOKENS\n")
        f.write("=" * 50 + "\n\n")
        
        found_count = len([r for r in results if r['found']])
        not_found_count = len([r for r in results if not r['found']])
        
        f.write(f"Totaal onderzocht: {len(results)}\n")
        f.write(f"Gevonden op DEX: {found_count}\n") 
        f.write(f"Niet gevonden: {not_found_count}\n\n")
        
        if not_found_count > 0:
            f.write("⚠️  WAARSCHUWING: Veel tokens zijn niet gevonden op DexScreener!\n")
            f.write("Dit kan betekenen dat ze:\n")
            f.write("• Niet meer verhandeld worden (delisted)\n")
            f.write("• Zeer lage liquiditeit hebben\n") 
            f.write("• Mogelijk pump & dump waren\n\n")
        
        f.write("GEVONDEN TOKENS DETAILS:\n")
        f.write("=" * 30 + "\n\n")
        
        for r in results:
            if r['found']:
                f.write(f"Token: {r['mint_address']}\n")
                f.write(f"  Huidige prijs: ${r['current_price_usd']:.8f}\n")
                f.write(f"  Prijs verandering 24h: {r['price_change_24h']}%\n")
                f.write(f"  Volume 24h: ${r['volume_24h']:,.0f}\n")
                f.write(f"  Liquiditeit: ${r['liquidity_usd']:,.0f}\n")
                f.write(f"  Market cap: ${r['market_cap']:,.0f}\n")
                f.write(f"  DEX: {r['dex_id']}\n")
                f.write("\n")
        
        f.write("\nNIET GEVONDEN TOKENS:\n")
        f.write("=" * 20 + "\n\n")
        
        for r in results:
            if not r['found']:
                f.write(f"❌ {r['mint_address']} - {r['error']}\n")
    
    print(f"\n✅ Analyse voltooid!")
    print(f"📊 CSV: real_token_analysis.csv")
    print(f"📄 Tekst: real_token_analysis.txt")
    print(f"🔍 Gevonden: {found_count}/{len(results)} tokens")
    
    return results

if __name__ == "__main__":
    results = analyze_first_tokens(20)
