"""
Integration bridge between the on-chain pipeline and token_labeler.py.

- Provides ``OnChainBridge``, a drop-in replacement for the external
  API calls (DexScreener, Birdeye, SolScan) used by the legacy
  ``token_labeler.py`` module.
- Translates ``OnChainDataProvider`` results into the response
  formats expected by each external API consumer.
- Includes a monkey-patching utility (``patch_token_labeler``) that
  intercepts ``_safe_json`` calls and redirects them through the
  bridge without modifying the original labeler source.
- Offers a convenience ``run_patched_labeler`` coroutine and CLI
  entry point for running the labeler end-to-end with on-chain data.

Author: ML-Bullx Team
Date:   2025-08-01
"""

# ==============================================================================
# Standard library imports
# ==============================================================================
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ==============================================================================
# Local imports
# ==============================================================================
from on_chain_solana_pipeline.onchain_provider import OnChainDataProvider, PriceData, HistoricalData
from on_chain_solana_pipeline.config.config_loader import load_config

logger = logging.getLogger(__name__)


# ==============================================================================
# Bridge class
# ==============================================================================
class OnChainBridge:
    """Drop-in replacement for external API calls in token_labeler.py.

    Wraps ``OnChainDataProvider`` and exposes methods that mirror the
    DexScreener, Birdeye, and SolScan APIs.  Each method returns data
    formatted identically to the original external response so that the
    calling code requires no changes.

    Attributes:
        config: Pipeline configuration loaded from YAML / env.
        provider: The underlying on-chain data provider (set after
            entering the async context manager).
    """

    def __init__(self, config_path: str = None):
        """Initialise the bridge with optional configuration path.

        Args:
            config_path: Path to a YAML config file.  When None the
                default config location is used.
        """
        self.config = load_config(config_path)
        self.provider: Optional[OnChainDataProvider] = None

    async def __aenter__(self):
        """Create and enter the underlying ``OnChainDataProvider``."""
        self.provider = OnChainDataProvider(self.config)
        await self.provider.__aenter__()
        return self

    async def __aexit__(self, *exc):
        """Tear down the underlying provider."""
        if self.provider:
            await self.provider.__aexit__(*exc)

    # ------------------------------------------------------------------
    # DexScreener-compatible endpoints
    # ------------------------------------------------------------------
    async def get_dexscreener_token(self, mint: str) -> Optional[Dict[str, Any]]:
        """Replacement for the DexScreener token API call.

        Args:
            mint: The SPL token mint address.

        Returns:
            A dict matching the DexScreener ``/dex/tokens/`` response
            structure, or None when no data is available.
        """
        try:
            price_data = await self.provider.get_current_price(mint)
            if not price_data:
                return None

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
        """Replacement for the DexScreener chart API call.

        Args:
            mint: The SPL token mint address.

        Returns:
            A list of OHLCV candle dicts in DexScreener format, or
            None when no history is available.
        """
        try:
            hist_data = await self.provider.get_historical_data(mint, days=17)
            if not hist_data or not hist_data.ohlcv:
                return None

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

    # ------------------------------------------------------------------
    # Birdeye-compatible endpoints
    # ------------------------------------------------------------------
    async def get_birdeye_price(self, mint: str) -> Optional[float]:
        """Replacement for the Birdeye price API call.

        Args:
            mint: The SPL token mint address.

        Returns:
            The current price as a float, or None.
        """
        try:
            price_data = await self.provider.get_current_price(mint)
            return price_data.price if price_data else None
        except Exception as e:
            logger.error(f"Error getting Birdeye price for {mint}: {e}")
            return None

    async def get_birdeye_candles(self, mint: str) -> List[Dict[str, Any]]:
        """Replacement for the Birdeye OHLC API call.

        Args:
            mint: The SPL token mint address.

        Returns:
            A list of OHLCV candle dicts, or an empty list.
        """
        try:
            hist_data = await self.provider.get_historical_data(mint, days=17)
            if not hist_data or not hist_data.ohlcv:
                return []

            return hist_data.ohlcv

        except Exception as e:
            logger.error(f"Error getting Birdeye candles for {mint}: {e}")
            return []

    # ------------------------------------------------------------------
    # SolScan-compatible endpoints
    # ------------------------------------------------------------------
    async def get_solscan_holders(self, mint: str) -> Optional[List]:
        """Replacement for the SolScan holders API call.

        The original consumer checks ``len(result)`` to obtain the
        holder count, so this method returns a list of empty dicts
        whose length equals the holder count.

        Args:
            mint: The SPL token mint address.

        Returns:
            A list of placeholder dicts with length equal to the
            holder count, or None on failure.
        """
        try:
            holder_count = await self.provider.get_holder_count(mint)
            if holder_count is None:
                return None

            return [{}] * holder_count

        except Exception as e:
            logger.error(f"Error getting holder count for {mint}: {e}")
            return None


# ==============================================================================
# Monkey-patching utilities
# ==============================================================================
async def patch_token_labeler():
    """Monkey-patch token_labeler.py to route API calls through the bridge.

    Replaces ``TokenLabeler._safe_json`` with a version that intercepts
    known URL patterns and delegates to ``OnChainBridge`` methods.
    Unrecognised URLs fall through to the original implementation.

    Returns:
        The ``OnChainBridge`` instance (caller is responsible for
        calling ``__aexit__`` when finished).

    Raises:
        ImportError: If ``token_labeler`` cannot be imported.
        Exception: On any other patching error.
    """
    try:
        import token_labeler

        bridge = OnChainBridge()
        await bridge.__aenter__()

        # Store original method
        original_safe_json = token_labeler.TokenLabeler._safe_json

        async def patched_safe_json(self, url: str, headers=None):
            """Intercept API URLs and redirect through the on-chain bridge."""
            mint = None

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
    """Run the original token labeler with on-chain data patches applied.

    Args:
        input_csv: Path to the input CSV file containing mint addresses.
        output_csv: Path where the labelled output CSV will be written.
        batch_size: Number of tokens to process per batch.
    """
    bridge = await patch_token_labeler()

    try:
        from token_labeler import TokenLabeler

        async with TokenLabeler() as labeler:
            await labeler.label_tokens_from_csv(input_csv, output_csv, batch_size)

    finally:
        await bridge.__aexit__(None, None, None)


# ==============================================================================
# CLI entry point
# ==============================================================================
def main():
    """Parse arguments and run the patched token labeler."""
    import argparse

    parser = argparse.ArgumentParser(description="Run token labeler with on-chain data")
    parser.add_argument("--input", required=True, help="Input CSV file")
    parser.add_argument("--output", required=True, help="Output CSV file")
    parser.add_argument("--batch", type=int, default=20, help="Batch size")
    parser.add_argument("--config", help="Config file path")
    args = parser.parse_args()

    if args.config:
        os.environ['ONCHAIN_CONFIG_PATH'] = args.config

    asyncio.run(run_patched_labeler(args.input, args.output, args.batch))


if __name__ == "__main__":
    main()
