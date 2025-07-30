#!/usr/bin/env python3
"""
Test script for the on-chain token labeler - run from pipeline directory
"""
import asyncio
import os
import pandas as pd
from datetime import datetime

# Import our on-chain components
from onchain_provider import OnChainDataProvider

async def test_onchain_provider():
    """Test the on-chain data provider directly"""
    print("🧪 Testing OnChain Data Provider")
    
    # Test tokens (well-known Solana addresses)
    test_tokens = [
        "So11111111111111111111111111111111111111112",  # Wrapped SOL
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    ]
    
    try:
        # Load config first
        from config.config_loader import load_config
        config = load_config()
        
        async with OnChainDataProvider(config) as provider:
            print("✅ OnChainDataProvider initialized successfully")
            
            for token in test_tokens:
                print(f"\n🔍 Testing token: {token}")
                
                # Test current price
                try:
                    price_data = await provider.get_current_price(token)
                    if price_data:
                        print(f"  💰 Price: ${price_data.get('price', 'N/A')}")
                        print(f"  📊 Volume 24h: ${price_data.get('volume_24h', 'N/A')}")
                    else:
                        print("  ⚠️  No price data found")
                except Exception as e:
                    print(f"  ❌ Price error: {e}")
                
                # Test holder count
                try:
                    holder_data = await provider.get_holder_count(token)
                    if holder_data:
                        print(f"  👥 Holders: {holder_data.get('count', 'N/A')}")
                    else:
                        print("  ⚠️  No holder data found")
                except Exception as e:
                    print(f"  ❌ Holder error: {e}")
                
                # Test historical data
                try:
                    historical_data = await provider.get_historical_ohlcv(token, days=7)
                    if historical_data:
                        print(f"  📈 Historical data points: {len(historical_data)}")
                    else:
                        print("  ⚠️  No historical data found")
                except Exception as e:
                    print(f"  ❌ Historical error: {e}")
                
                # Small delay between tokens
                await asyncio.sleep(1)
                
    except Exception as e:
        print(f"❌ Provider error: {e}")
        import traceback
        traceback.print_exc()

def test_basic_imports():
    """Test that basic imports work"""
    print("🧪 Testing basic imports...")
    
    try:
        from api_key_manager import get_key_manager
        print("✅ API key manager imported")
        
        from config.config_loader import load_config
        print("✅ Config loader imported")
        
        from onchain_provider import OnChainDataProvider
        print("✅ OnChain provider imported")
        
        return True
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_api_keys():
    """Test that API keys are working"""
    print("🧪 Testing API keys...")
    
    try:
        from api_key_manager import get_key_manager
        
        key_manager = get_key_manager()
        current_key = key_manager.get_next_available_key()
        if current_key:
            print(f"✅ Current API key: {current_key[:8]}...{current_key[-8:]}")
        else:
            print("❌ No API keys available")
            return False
        
        # Test key rotation
        next_key = key_manager.get_next_available_key()
        if next_key:
            print(f"✅ Next API key: {next_key[:8]}...{next_key[-8:]}")
        
        # Show stats
        stats = key_manager.get_usage_stats()
        print(f"✅ Total keys loaded: {len(stats)}")
        
        return True
        
    except Exception as e:
        print(f"❌ API key error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting On-Chain Data Pipeline Tests")
    print("=" * 50)
    
    # Test imports first
    if test_basic_imports():
        print("\n🔑 Testing API key management...")
        asyncio.run(test_api_keys())
        
        print("\n🔄 Running data provider test...")
        asyncio.run(test_onchain_provider())
    else:
        print("❌ Import tests failed")
    
    print("\n✅ Test completed!")
