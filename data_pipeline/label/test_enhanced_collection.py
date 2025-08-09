#!/usr/bin/env python3
"""
Test script for the enhanced data collection system.
This will test both the original and enhanced parsing to compare results.
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "on_chain_solana_pipeline"))
sys.path.insert(0, str(Path(__file__).parent))

from token_labeler_copy import EnhancedTokenLabeler

def setup_logging():
    """Setup detailed logging."""
    logging.basicConfig(
        level=logging.INFO,  # Changed to INFO to reduce noise
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("enhanced_test.log")
        ]
    )

async def test_enhanced_collection(mint_address: str):
    """Test the enhanced data collection system."""
    logger = logging.getLogger(__name__)
    logger.info("=" * 80)
    logger.info(f"🧪 TESTING ENHANCED DATA COLLECTION: {mint_address}")
    logger.info("=" * 80)
    
    try:
        async with EnhancedTokenLabeler() as labeler:
            logger.info("✅ Enhanced token labeler initialized")
            
            # Test the enhanced data collection
            logger.info("🔍 Testing enhanced metrics collection...")
            metrics = await labeler._gather_metrics(mint_address)
            
            logger.info("=" * 50)
            logger.info("📊 ENHANCED METRICS RESULTS:")
            logger.info("=" * 50)
            
            # Quick summary
            has_data = {
                'price_data': bool(metrics.current_price or metrics.launch_price),
                'volume_data': bool(metrics.volume_24h or metrics.historical_avg_volume),
                'holder_data': bool(metrics.holder_count),
                'historical_data': bool(metrics.ath_before_72h or metrics.ath_after_72h),
                'advanced_metrics': bool(metrics.legitimacy_analysis)
            }
            
            logger.info("📋 DATA AVAILABILITY SUMMARY:")
            for data_type, available in has_data.items():
                status = "✅" if available else "❌"
                logger.info(f"   {status} {data_type.replace('_', ' ').title()}: {available}")
            
            # Key metrics
            logger.info("💰 KEY METRICS:")
            logger.info(f"   Launch price: ${metrics.launch_price:.8f}" if metrics.launch_price else "   Launch price: N/A")
            logger.info(f"   Current price: ${metrics.current_price:.8f}" if metrics.current_price else "   Current price: N/A")
            logger.info(f"   Mega appreciation: {metrics.mega_appreciation:.0f}x" if metrics.mega_appreciation else "   Mega appreciation: N/A")
            logger.info(f"   Holder count: {metrics.holder_count:,}" if metrics.holder_count else "   Holder count: N/A")
            logger.info(f"   Volume 24h: ${metrics.volume_24h:,.0f}" if metrics.volume_24h else "   Volume 24h: N/A")
            
            # Classification test
            logger.info("🏷️ CLASSIFICATION TEST:")
            classification = labeler._classify(metrics)
            logger.info(f"   Result: {classification.upper()}")
            
            # Detailed reasoning
            logger.info("📝 CLASSIFICATION REASONING:")
            labeler._log_classification_reasoning(metrics, classification)
            
            # Count non-null metrics
            non_null_count = 0
            total_count = 0
            
            for attr in dir(metrics):
                if not attr.startswith('_') and hasattr(metrics, attr):
                    value = getattr(metrics, attr)
                    total_count += 1
                    if value is not None:
                        non_null_count += 1
            
            completeness_ratio = non_null_count / total_count if total_count > 0 else 0
            logger.info(f"📊 DATA COMPLETENESS: {non_null_count}/{total_count} ({completeness_ratio:.1%}) metrics populated")
            
            if completeness_ratio < 0.5:
                logger.warning("⚠️ Low data completeness - many metrics are missing")
                logger.info("💡 Possible causes:")
                logger.info("   - Token has very few transactions")
                logger.info("   - API rate limiting preventing full analysis")
                logger.info("   - Transaction parsing issues")
                logger.info("   - Database connectivity problems")
            else:
                logger.info("✅ Good data completeness - most metrics are available")
    
    except Exception as e:
        logger.error(f"❌ Error during enhanced testing: {e}", exc_info=True)

async def main():
    """Main test function."""
    setup_logging()
    
    # Test with a few different tokens
    test_mints = [
        "X3qPC4HYu3DBSxGYbevftb16RJYNm3c87qV1z3tDXRj",  # From input CSV
        "4ZTzLk9dsmzLFSmT1tcFeLUyfKhuGPpWQPakkY8Hpump",  # Second from input CSV
        "9Nj2NN9z1JxmSPDtJ7b2VWn3m8RgeZx2jAeGWTp2pump",  # Third from input CSV
    ]
    
    if len(sys.argv) > 1:
        test_mints = [sys.argv[1]]
    
    for i, mint in enumerate(test_mints, 1):
        print(f"🧪 Testing token {i}/{len(test_mints)}: {mint}")
        await test_enhanced_collection(mint)
        
        if i < len(test_mints):
            print("\n" + "="*80 + "\n")
            await asyncio.sleep(2)  # Brief pause between tests

if __name__ == "__main__":
    asyncio.run(main())
