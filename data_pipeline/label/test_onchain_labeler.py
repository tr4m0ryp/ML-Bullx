#!/usr/bin/env python3
"""
Test script for the on-chain token labeler
"""
import asyncio
import os
import sys
import pandas as pd

# Add the on-chain pipeline to the path
current_dir = os.path.dirname(__file__)
pipeline_path = os.path.join(os.path.dirname(os.path.dirname(current_dir)), "on_chain_solana_pipeline")
sys.path.insert(0, pipeline_path)

# Now we can import our on-chain labeler
from token_labeler_onchain import OnChainTokenLabeler

async def test_onchain_labeler():
    """Test the on-chain token labeler with some sample tokens"""
    print("🧪 Testing On-Chain Token Labeler")
    
    # Test tokens (well-known Solana addresses)
    test_tokens = [
        "So11111111111111111111111111111111111111112",  # Wrapped SOL
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    ]
    
    # Create a temporary CSV file with test tokens
    test_df = pd.DataFrame({"mint_address": test_tokens})
    test_input = "test_tokens.csv"
    test_output = "test_results.csv"
    
    test_df.to_csv(test_input, index=False)
    print(f"📝 Created test input CSV with {len(test_tokens)} tokens")
    
    # Test the labeler
    try:
        async with OnChainTokenLabeler() as labeler:
            print("🔄 Running token labeling...")
            result_df = await labeler.label_tokens_from_csv(
                test_input, 
                test_output, 
                batch=1  # Small batch for testing
            )
            
            print(f"✅ Labeling completed! Results:")
            print(result_df)
            
    except Exception as e:
        print(f"❌ Error during labeling: {e}")
        import traceback
        traceback.print_exc()
    
    # Cleanup
    try:
        os.remove(test_input)
        if os.path.exists(test_output):
            os.remove(test_output)
    except:
        pass

def test_imports():
    """Test that all imports work correctly"""
    print("🧪 Testing imports...")
    
    try:
        from token_labeler_onchain import OnChainTokenLabeler, TokenMetrics
        print("✅ OnChainTokenLabeler imported successfully")
        
        # Test that we can create an instance
        labeler = OnChainTokenLabeler()
        print("✅ OnChainTokenLabeler instance created")
        
        # Test TokenMetrics dataclass
        metrics = TokenMetrics("test_mint")
        print("✅ TokenMetrics dataclass works")
        
        return True
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting On-Chain Token Labeler Tests")
    print("=" * 50)
    
    # Test imports first
    if test_imports():
        print("\n🔄 Running full integration test...")
        asyncio.run(test_onchain_labeler())
    else:
        print("❌ Import tests failed, skipping integration test")
    
    print("\n✅ Test completed!")
