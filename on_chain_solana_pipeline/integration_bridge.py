"""
Integration bridge to use on-chain pipeline with existing token_labeler.py
This allows you to gradually migrate from external APIs to on-chain data.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

# Add paths for imports
current_dir = os.path.dirname(__file__)
label_dir = os.path.join(os.path.dirname(current_dir), "data_pipeline", "label")
sys.path.insert(0, current_dir)
sys.path.insert(0, label_dir)

from onchain_provider import OnChainDataProvider, PriceData, HistoricalData
from config.config_loader import load_config

logger = logging.getLogger(__name__)


class OnChainBridge:
    """
    Bridge class that can be used as a drop-in replacement for external API calls
    in the existing token_labeler.py. Provides the same interface but uses on-chain data.
    """
    
    def __init__(self, config_path: str = None):
        self.config = load_config(config_path)
        self.provider: Optional[OnChainDataProvider] = None
    
    async def __aenter__(self):
        self.provider = OnChainDataProvider(self.config)
        await self.provider.__aenter__()
        return self
    
    async def __aexit__(self, *exc):
        if self.provider:
            await self.provider.__aexit__(*exc)
    
    # Methods that match the interface expected by token_labeler.py
    
    async def get_dexscreener_token(self, mint: str) -> Optional[Dict[str, Any]]:
        """
        Replacement for DexScreener token API call.
        Returns data in the same format as the original API.
        """
        try:
            price_data = await self.provider.get_current_price(mint)
            if not price_data:
                return None
            
            # Format response to match DexScreener API structure
            return {
                "pairs": [{
                    "priceUsd": str(price_data.price),
                    "volume": {"h24": str(price_data.volume_24h)},
                    "marketCap": str(price_data.market_cap) if price_data.market_cap else None,
                    "liquidity": {"usd": "0"}  # Would need pool reserve data for this
                }]
            }
        except Exception as e:
            logger.error(f"Error getting token data for {mint}: {e}")
            return None
    
    async def get_dexscreener_chart(self, mint: str) -> Optional[List[Dict[str, Any]]]:
        """
        Replacement for DexScreener chart API call.
        Returns OHLCV data in the same format as the original API.
        """
        try:
            hist_data = await self.provider.get_historical_data(mint, days=17)
            if not hist_data or not hist_data.ohlcv:
                return None
            
            # Convert to DexScreener format
            candles = []
            for candle in hist_data.ohlcv:
                candles.append({
                    "t": candle["ts"],
                    "o": candle["o"], 
                    "h": candle["h"],
                    "l": candle["l"],
                    "c": candle["c"],
                    "v": candle["v"]
                })
            
            return candles
            
        except Exception as e:
            logger.error(f"Error getting chart data for {mint}: {e}")
            return None
    
    async def get_birdeye_price(self, mint: str) -> Optional[float]:
        """
        Replacement for Birdeye price API call.
        """
        try:
            price_data = await self.provider.get_current_price(mint)
            return price_data.price if price_data else None
        except Exception as e:
            logger.error(f"Error getting Birdeye price for {mint}: {e}")
            return None
    
    async def get_birdeye_candles(self, mint: str) -> List[Dict[str, Any]]:
        """
        Replacement for Birdeye OHLC API call.
        """
        try:
            hist_data = await self.provider.get_historical_data(mint, days=17)
            if not hist_data or not hist_data.ohlcv:
                return []
            
            # Convert to Birdeye format (similar to DexScreener)
            return hist_data.ohlcv
            
        except Exception as e:
            logger.error(f"Error getting Birdeye candles for {mint}: {e}")
            return []
    
    async def get_solscan_holders(self, mint: str) -> Optional[List]:
        """
        Replacement for SolScan holders API call.
        Returns a list with length equal to holder count (to match original interface).
        """
        try:
            holder_count = await self.provider.get_holder_count(mint)
            if holder_count is None:
                return None
            
            # Return a list with the right length (original code just checks len())
            return [{}] * holder_count
            
        except Exception as e:
            logger.error(f"Error getting holder count for {mint}: {e}")
            return None


# Monkey patch functions to replace external API calls in token_labeler.py
async def patch_token_labeler():
    """
    Function to monkey-patch the existing token_labeler.py to use on-chain data.
    Call this before running the original labeler.
    """
    try:
        import token_labeler
        
        # Create bridge instance
        bridge = OnChainBridge()
        await bridge.__aenter__()
        
        # Store original methods
        original_safe_json = token_labeler.TokenLabeler._safe_json
        
        # Create patched version
        async def patched_safe_json(self, url: str, headers=None):
            mint = None
            
            # Extract mint from URL patterns
            if "dex/tokens/" in url:
                mint = url.split("dex/tokens/")[1].split("?")[0]
                return await bridge.get_dexscreener_token(mint)
            elif "dex/chart/tokens/" in url:
                mint = url.split("dex/chart/tokens/")[1].split("?")[0]
                return await bridge.get_dexscreener_chart(mint)
            elif "birdeye.so/public/price" in url:
                mint = url.split("address=")[1].split("&")[0]
                result = await bridge.get_birdeye_price(mint)
                return {"data": {"value": result}} if result else None
            elif "birdeye.so/defi/v3/ohlc" in url:
                mint = url.split("address=")[1].split("&")[0]
                candles = await bridge.get_birdeye_candles(mint)
                return {"data": candles} if candles else None
            elif "solscan.io/token/holders" in url:
                mint = url.split("account=")[1].split("&")[0]
                return await bridge.get_solscan_holders(mint)
            else:
                # Fallback to original method for unrecognized URLs
                return await original_safe_json(self, url, headers)
        
        # Apply the patch
        token_labeler.TokenLabeler._safe_json = patched_safe_json
        
        logger.info("Successfully patched token_labeler to use on-chain data")
        return bridge
        
    except ImportError as e:
        logger.error(f"Could not import token_labeler: {e}")
        raise
    except Exception as e:
        logger.error(f"Error patching token_labeler: {e}")
        raise


async def run_patched_labeler(input_csv: str, output_csv: str, batch_size: int = 20):
    """
    Run the original token labeler with on-chain data patches applied.
    """
    bridge = await patch_token_labeler()
    
    try:
        # Import and run the original labeler
        from token_labeler import TokenLabeler
        
        async with TokenLabeler() as labeler:
            await labeler.label_tokens_from_csv(input_csv, output_csv, batch_size)
    
    finally:
        await bridge.__aexit__(None, None, None)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Run token labeler with on-chain data")
    parser.add_argument("--input", required=True, help="Input CSV file")
    parser.add_argument("--output", required=True, help="Output CSV file")
    parser.add_argument("--batch", type=int, default=20, help="Batch size")
    parser.add_argument("--config", help="Config file path")
    args = parser.parse_args()
    
    # Set config path if provided
    if args.config:
        os.environ['ONCHAIN_CONFIG_PATH'] = args.config
    
    asyncio.run(run_patched_labeler(args.input, args.output, args.batch))


if __name__ == "__main__":
    main()
