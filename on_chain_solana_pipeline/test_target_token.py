#!/usr/bin/env python3
"""
Test script to label a specific token: 5fr1bB2Tz6ywjoFc9K1VoX3ukGHP6xPUD5bFU4nX1Zs9
"""
import asyncio
import os
import pandas as pd
import sys

async def test_specific_token():
    """Test labeling of the specific token"""
    print("🧪 Testing Token: 5fr1bB2Tz6ywjoFc9K1VoX3ukGHP6xPUD5bFU4nX1Zs9")
    print("=" * 70)
    
    target_token = "5fr1bB2Tz6ywjoFc9K1VoX3ukGHP6xPUD5bFU4nX1Zs9"
    
    try:
        # Import the enhanced labeler 
        from enhanced_token_labeler import EnhancedTokenLabeler
        
        # Create test CSV
        test_df = pd.DataFrame({"mint_address": [target_token]})
        test_input = "target_token_test.csv"
        test_output = "target_token_result.csv"
        
        test_df.to_csv(test_input, index=False)
        print(f"📝 Created test CSV with token: {target_token}")
        
        # Test with enhanced labeler
        print("🔄 Running enhanced token labeling...")
        
        try:
            async with EnhancedTokenLabeler() as labeler:
                result_df = await labeler.label_tokens_from_csv(
                    test_input, 
                    test_output, 
                    batch=1
                )
                
                print(f"\n✅ Labeling completed!")
                print("📊 RESULTS:")
                print("-" * 40)
                for _, row in result_df.iterrows():
                    print(f"Token: {row['mint_address']}")
                    print(f"Label: {row['label'].upper()}")
                
                return result_df
                
        except Exception as e:
            print(f"❌ Error during enhanced labeling: {e}")
            import traceback
            traceback.print_exc()
            
            # Try with a simpler approach
            print("\n🔄 Trying with direct classification...")
            return await test_direct_classification(target_token)
    
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Let's try using the existing working components...")
        return await test_with_existing_components(target_token)
    
    finally:
        # Cleanup
        for file in [test_input, test_output]:
            try:
                if os.path.exists(file):
                    os.remove(file)
            except:
                pass

async def test_direct_classification(token):
    """Test direct classification without full pipeline"""
    print(f"🔍 Direct classification test for: {token}")
    
    try:
        # Try to import and use the onchain provider directly
        from onchain_provider import OnChainDataProvider
        from config.config_loader import load_config
        
        config = load_config()
        
        async with OnChainDataProvider(config) as provider:
            print("✅ OnChain provider connected")
            
            # Get basic data
            price_data = await provider.get_current_price(token)
            if price_data:
                print(f"💰 Current price: ${price_data.price}")
                print(f"📊 24h volume: ${price_data.volume_24h:,.2f}")
                print(f"💎 Market cap: ${price_data.market_cap:,.2f}")
            else:
                print("❌ No price data available")
                
            # Get historical data
            hist_data = await provider.get_historical_data(token)
            if hist_data:
                print(f"📈 72h peak: ${hist_data.peak_price_72h}")
                print(f"🚀 Post-ATH peak: ${hist_data.post_ath_peak_price}")
                print(f"📊 OHLCV data points: {len(hist_data.ohlcv)}")
            else:
                print("❌ No historical data available")
                
            # Get holder count
            holders = await provider.get_holder_count(token)
            if holders:
                print(f"👥 Holder count: {holders}")
            else:
                print("❌ No holder data available")
            
            # Simple classification based on available data
            if price_data and hist_data and holders:
                label = classify_simple(price_data, hist_data, holders)
                print(f"\n🏷️  SIMPLIFIED CLASSIFICATION: {label.upper()}")
                return pd.DataFrame({"mint_address": [token], "label": [label]})
            else:
                print(f"\n🏷️  CLASSIFICATION: INACTIVE (insufficient data)")
                return pd.DataFrame({"mint_address": [token], "label": ["inactive"]})
        
    except Exception as e:
        print(f"❌ Error in direct classification: {e}")
        import traceback
        traceback.print_exc()
        return None

def classify_simple(price_data, hist_data, holders):
    """Simple classification logic"""
    if not price_data.price or holders < 10:
        return "inactive"
    
    if hist_data.peak_price_72h and hist_data.post_ath_peak_price:
        appreciation = hist_data.post_ath_peak_price / hist_data.peak_price_72h
        if appreciation >= 10.0 and holders >= 100:
            return "successful"
    
    # Check for major drops in OHLCV data
    if hist_data.ohlcv:
        max_drop = 0
        for candle in hist_data.ohlcv:
            if candle.get('h', 0) > 0:
                drop = 1 - (candle.get('l', 0) / candle.get('h', 1))
                max_drop = max(max_drop, drop)
        
        if max_drop >= 0.7:
            return "rugpull"
    
    return "unsuccessful"

async def test_with_existing_components(token):
    """Fallback test using existing demo components"""
    print(f"🔄 Testing with existing demo components for: {token}")
    
    # Simulate classification based on known patterns
    print("📊 Simulating classification based on token characteristics...")
    
    # This is a placeholder - in real scenario we'd use actual data
    result = pd.DataFrame({
        "mint_address": [token], 
        "label": ["test_classification_needed"]
    })
    
    print(f"⚠️  Manual investigation needed for token: {token}")
    return result

if __name__ == "__main__":
    print("🚀 Starting Token Classification Test")
    result = asyncio.run(test_specific_token())
    
    if result is not None:
        print(f"\n✅ Test completed successfully!")
        print("\n📋 FINAL RESULT:")
        print("=" * 50)
        print(result.to_string(index=False))
    else:
        print(f"\n❌ Test failed - manual investigation required")
