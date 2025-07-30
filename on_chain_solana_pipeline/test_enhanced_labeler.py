#!/usr/bin/env python3
"""
Simple test for the on-chain token labeler
"""
import asyncio
import os
import pandas as pd

async def test_enhanced_labeler():
    """Test the enhanced token labeler from our pipeline"""
    print("🧪 Testing Enhanced Token Labeler from Pipeline")
    
    try:
        # Import and test the enhanced labeler
        from enhanced_token_labeler import EnhancedTokenLabeler
        
        # Test tokens (well-known Solana addresses)  
        test_tokens = [
            "So11111111111111111111111111111111111111112",  # Wrapped SOL
        ]
        
        # Create a temporary CSV file with test tokens
        test_df = pd.DataFrame({"mint_address": test_tokens})
        test_input = "test_tokens.csv"
        test_output = "test_results.csv"
        
        test_df.to_csv(test_input, index=False)
        print(f"📝 Created test input CSV with {len(test_tokens)} tokens")
        
        # Test the labeler
        try:
            async with EnhancedTokenLabeler() as labeler:
                print("🔄 Running enhanced token labeling...")
                result_df = await labeler.label_tokens_from_csv(
                    test_input, 
                    test_output, 
                    batch=1
                )
                
                print(f"✅ Enhanced labeling completed! Results:")
                print(result_df)
                
        except Exception as e:
            print(f"❌ Error during enhanced labeling: {e}")
            import traceback
            traceback.print_exc()
        
        # Cleanup
        try:
            os.remove(test_input)
            if os.path.exists(test_output):
                print(f"📁 Results saved to: {test_output}")
        except:
            pass
            
    except Exception as e:
        print(f"❌ Import error: {e}")
        import traceback
        traceback.print_exc()

async def test_basic_functionality():
    """Test basic functionality that should work without external dependencies"""
    print("🧪 Testing Basic Functionality")
    
    try:
        from enhanced_token_labeler import EnhancedTokenLabeler, TokenMetrics
        
        # Test creating metrics object
        metrics = TokenMetrics("test_mint_address")
        print(f"✅ TokenMetrics created: {metrics.mint_address}")
        
        # Test labeler instantiation
        labeler = EnhancedTokenLabeler()
        print("✅ EnhancedTokenLabeler created")
        
        # Test classification logic without external data
        metrics.current_price = 1.0
        metrics.holder_count = 150
        metrics.peak_price_72h = 0.5
        metrics.post_ath_peak_price = 10.0
        metrics.has_sustained_drop = False
        metrics.price_drops = []
        
        result = labeler._classify(metrics)
        print(f"✅ Classification test: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ Basic functionality error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting Enhanced Token Labeler Tests")
    print("=" * 50)
    
    async def run_all_tests():
        # Test basic functionality first
        if await test_basic_functionality():
            print("\n🔄 Running full enhanced labeler test...")
            await test_enhanced_labeler()
        else:
            print("❌ Basic tests failed")
    
    asyncio.run(run_all_tests())
    print("\n✅ Test completed!")
