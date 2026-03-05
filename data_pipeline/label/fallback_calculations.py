"""
Fallback Calculation Methods for Missing Token Metrics.

Provides a library of static methods that attempt to derive missing
on-chain metrics from whatever partial data is available:
- Rolling 24-hour volume aggregation from individual swap records.
- Historical average volume across all parsed swaps.
- Peak volume detection from OHLCV candles or raw swaps.
- Launch price detection from the earliest available data point.
- Price data-point counting for data-quality assessment.
- Daily transaction rate estimation.
- Token supply retrieval via Solana RPC.
- Market capitalization calculation from price and supply.
- Swap data extraction from analysis result dictionaries.

Author: ML-Bullx Team
Date: 2025-08-01
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# FallbackCalculations
# =============================================================================

class FallbackCalculations:
    """Static utility class providing fallback calculations for missing token data.

    Each method is designed to gracefully handle missing or malformed input
    and return None when a reliable result cannot be produced.  Methods
    prefer OHLCV data over raw swap records when both are available.
    """

    # -------------------------------------------------------------------------
    # Volume Calculations
    # -------------------------------------------------------------------------

    @staticmethod
    def calculate_volume_24h_from_swaps(swap_data: List[Dict[str, Any]]) -> Optional[float]:
        """Calculate rolling 24-hour volume from individual swap records.

        Args:
            swap_data: List of swap dictionaries, each containing
                ``timestamp`` (Unix epoch or ISO string) and
                ``volume_usd`` (float).

        Returns:
            Aggregated volume in USD for the last 24 hours, or None
            if no recent swaps are available.
        """
        if not swap_data:
            return None

        try:
            now = datetime.now()
            cutoff_time = now - timedelta(hours=24)

            recent_volume = 0.0
            recent_swaps = 0

            for swap in swap_data:
                # Handle timestamp in different formats
                timestamp = swap.get('timestamp', 0)
                if isinstance(timestamp, (int, float)):
                    swap_time = datetime.fromtimestamp(timestamp)
                elif isinstance(timestamp, str):
                    swap_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                else:
                    continue

                if swap_time >= cutoff_time:
                    volume_usd = swap.get('volume_usd', 0)
                    if isinstance(volume_usd, (int, float)) and volume_usd > 0:
                        recent_volume += volume_usd
                        recent_swaps += 1

            if recent_swaps > 0:
                logger.debug(f"Calculated 24h volume: ${recent_volume:.2f} from {recent_swaps} swaps")
                return recent_volume
            else:
                logger.debug("No recent swaps found for 24h volume calculation")
                return None

        except Exception as e:
            logger.debug(f"Error calculating 24h volume: {e}")
            return None

    @staticmethod
    def calculate_historical_avg_volume(swap_data: List[Dict[str, Any]]) -> Optional[float]:
        """Calculate historical average volume across all swap records.

        Requires at least two valid data points to produce a meaningful
        average.

        Args:
            swap_data: List of swap dictionaries with ``volume_usd``.

        Returns:
            Mean volume in USD, or None if fewer than two valid
            records exist.
        """
        if not swap_data:
            return None

        try:
            valid_volumes = []

            for swap in swap_data:
                volume_usd = swap.get('volume_usd', 0)
                if isinstance(volume_usd, (int, float)) and volume_usd > 0:
                    valid_volumes.append(volume_usd)

            if len(valid_volumes) >= 2:  # Need at least 2 data points
                avg_volume = np.mean(valid_volumes)
                logger.debug(f"Calculated historical avg volume: ${avg_volume:.2f} from {len(valid_volumes)} swaps")
                return float(avg_volume)
            else:
                logger.debug(f"Insufficient volume data: only {len(valid_volumes)} valid swaps")
                return None

        except Exception as e:
            logger.debug(f"Error calculating historical avg volume: {e}")
            return None

    @staticmethod
    def calculate_peak_volume(swap_data: List[Dict[str, Any]], ohlcv_data: List[Dict[str, Any]] = None) -> Optional[float]:
        """Determine the single highest volume value from available data.

        Checks OHLCV candle volumes first (more reliable aggregation),
        then falls back to individual swap volumes.

        Args:
            swap_data: List of swap dictionaries with ``volume_usd``.
            ohlcv_data: Optional list of OHLCV candle dictionaries
                with a ``v`` (volume) field.

        Returns:
            Peak volume in USD, or None if no positive volume is found.
        """
        peak_volume = 0.0

        try:
            # Check OHLCV data first (more reliable for volume aggregation)
            if ohlcv_data:
                for candle in ohlcv_data:
                    volume = candle.get('v', 0)
                    if isinstance(volume, (int, float)) and volume > peak_volume:
                        peak_volume = volume

            # Fallback to individual swap volumes
            if peak_volume == 0.0 and swap_data:
                for swap in swap_data:
                    volume_usd = swap.get('volume_usd', 0)
                    if isinstance(volume_usd, (int, float)) and volume_usd > peak_volume:
                        peak_volume = volume_usd

            if peak_volume > 0:
                logger.debug(f"Calculated peak volume: ${peak_volume:.2f}")
                return peak_volume
            else:
                return None

        except Exception as e:
            logger.debug(f"Error calculating peak volume: {e}")
            return None

    # -------------------------------------------------------------------------
    # Price Detection
    # -------------------------------------------------------------------------

    @staticmethod
    def detect_launch_price(swap_data: List[Dict[str, Any]], ohlcv_data: List[Dict[str, Any]] = None) -> Optional[float]:
        """Detect the launch price from the earliest available data point.

        Scans both swap records and OHLCV candles, selecting the price
        associated with the smallest timestamp.

        Args:
            swap_data: List of swap dictionaries with ``timestamp``
                and ``price``.
            ohlcv_data: Optional OHLCV candle list with ``ts`` or
                ``timestamp`` and ``o`` (open price).

        Returns:
            Earliest recorded price as a float, or None if no valid
            price data is found.
        """
        if not swap_data and not ohlcv_data:
            return None

        try:
            earliest_price = None
            earliest_time = None

            # Check swap data for earliest price
            if swap_data:
                for swap in swap_data:
                    timestamp = swap.get('timestamp', 0)
                    price = swap.get('price', 0)

                    if isinstance(timestamp, (int, float)) and isinstance(price, (int, float)) and price > 0:
                        if earliest_time is None or timestamp < earliest_time:
                            earliest_time = timestamp
                            earliest_price = price

            # Check OHLCV data for earliest price
            if ohlcv_data:
                for candle in ohlcv_data:
                    timestamp = candle.get('ts', candle.get('timestamp', 0))
                    open_price = candle.get('o', 0)

                    if isinstance(timestamp, (int, float)) and isinstance(open_price, (int, float)) and open_price > 0:
                        if earliest_time is None or timestamp < earliest_time:
                            earliest_time = timestamp
                            earliest_price = open_price

            if earliest_price and earliest_price > 0:
                logger.debug(f"Detected launch price: ${earliest_price:.8f} at timestamp {earliest_time}")
                return float(earliest_price)
            else:
                return None

        except Exception as e:
            logger.debug(f"Error detecting launch price: {e}")
            return None

    # -------------------------------------------------------------------------
    # Data Quality Metrics
    # -------------------------------------------------------------------------

    @staticmethod
    def count_price_points(swap_data: List[Dict[str, Any]], ohlcv_data: List[Dict[str, Any]] = None) -> int:
        """Count the number of valid price data points available.

        Prefers OHLCV close prices when available; otherwise counts
        individual swap prices.

        Args:
            swap_data: List of swap dictionaries with ``price``.
            ohlcv_data: Optional OHLCV candle list with ``c``
                (close price).

        Returns:
            Number of data points with a positive price value.
        """
        try:
            point_count = 0

            # Count OHLCV candles (preferred)
            if ohlcv_data:
                point_count += len([c for c in ohlcv_data if c.get('c', 0) > 0])

            # Count individual swap prices if no OHLCV
            elif swap_data:
                point_count += len([s for s in swap_data if s.get('price', 0) > 0])

            logger.debug(f"Counted {point_count} price data points")
            return point_count

        except Exception as e:
            logger.debug(f"Error counting price points: {e}")
            return 0

    @staticmethod
    def calculate_transaction_rate(swap_data: List[Dict[str, Any]], total_days: float = None) -> Optional[float]:
        """Calculate the average daily transaction rate.

        Automatically detects the time span from timestamps when
        ``total_days`` is not provided.  Enforces a minimum period
        of 0.1 days (~2.4 hours) to avoid inflated rates.

        Args:
            swap_data: List of swap dictionaries with ``timestamp``.
            total_days: Explicit number of days over which to compute
                the rate.  Auto-detected from data if None.

        Returns:
            Transactions per day as a float, or None if fewer than
            two data points exist.
        """
        if not swap_data or len(swap_data) < 2:
            return None

        try:
            # Get time span if not provided
            if total_days is None:
                timestamps = []
                for swap in swap_data:
                    timestamp = swap.get('timestamp', 0)
                    if isinstance(timestamp, (int, float)) and timestamp > 0:
                        timestamps.append(timestamp)

                if len(timestamps) < 2:
                    return None

                time_span_seconds = max(timestamps) - min(timestamps)
                total_days = time_span_seconds / (24 * 3600)

                if total_days < 0.1:  # Less than ~2.4 hours
                    total_days = 0.1  # Minimum rate calculation period

            transaction_count = len(swap_data)
            daily_rate = transaction_count / total_days

            logger.debug(f"Calculated transaction rate: {daily_rate:.2f} tx/day over {total_days:.1f} days")
            return float(daily_rate)

        except Exception as e:
            logger.debug(f"Error calculating transaction rate: {e}")
            return None

    # -------------------------------------------------------------------------
    # RPC-Based Lookups
    # -------------------------------------------------------------------------

    @staticmethod
    async def get_token_supply_rpc(mint_address: str, rpc_client) -> Optional[int]:
        """Retrieve total token supply via Solana RPC.

        Args:
            mint_address: SPL token mint address string.
            rpc_client: Async Solana RPC client instance exposing
                ``get_token_supply``.

        Returns:
            Total token supply as an integer, or None on failure.
        """
        try:
            if hasattr(rpc_client, 'get_token_supply'):
                response = await rpc_client.get_token_supply(mint_address)
                if hasattr(response, 'value') and hasattr(response.value, 'ui_amount'):
                    supply = response.value.ui_amount
                    if isinstance(supply, (int, float)) and supply > 0:
                        logger.debug(f"Got token supply via RPC: {supply:,.0f}")
                        return int(supply)

            return None

        except Exception as e:
            logger.debug(f"Error getting token supply via RPC: {e}")
            return None

    # -------------------------------------------------------------------------
    # Derived Calculations
    # -------------------------------------------------------------------------

    @staticmethod
    def calculate_market_cap(current_price: Optional[float], token_supply: Optional[int]) -> Optional[float]:
        """Calculate market capitalization from price and total supply.

        Args:
            current_price: Current token price in USD.
            token_supply: Total circulating or total token supply.

        Returns:
            Market cap in USD, or None if either input is missing
            or non-positive.
        """
        if not current_price or not token_supply or current_price <= 0 or token_supply <= 0:
            return None

        try:
            market_cap = current_price * token_supply
            logger.debug(f"Calculated market cap: ${market_cap:,.2f}")
            return float(market_cap)

        except Exception as e:
            logger.debug(f"Error calculating market cap: {e}")
            return None

    # -------------------------------------------------------------------------
    # Data Extraction
    # -------------------------------------------------------------------------

    @staticmethod
    def extract_swap_data_from_analysis(analysis_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract normalized swap data from an analysis result dictionary.

        Looks for OHLCV candle arrays first, then falls back to direct
        swap data lists stored under ``swaps`` or ``swap_data`` keys.

        Args:
            analysis_result: Dictionary returned by the enhanced
                token analysis pipeline.

        Returns:
            List of swap dictionaries with ``timestamp``, ``price``,
            and ``volume_usd`` keys.  Returns an empty list on error.
        """
        swap_data = []

        try:
            # Try to extract from various possible locations in the analysis
            if isinstance(analysis_result, dict):
                # Check for OHLCV data
                ohlcv = analysis_result.get('ohlcv', [])
                if ohlcv:
                    for candle in ohlcv:
                        if isinstance(candle, dict):
                            swap_data.append({
                                'timestamp': candle.get('ts', candle.get('timestamp', 0)),
                                'price': candle.get('c', 0),  # Close price
                                'volume_usd': candle.get('v', 0),  # Volume
                                'high': candle.get('h', 0),
                                'low': candle.get('l', 0)
                            })

                # Check for direct swap data
                swaps = analysis_result.get('swaps', analysis_result.get('swap_data', []))
                if swaps:
                    swap_data.extend(swaps)

            logger.debug(f"Extracted {len(swap_data)} swap data points from analysis")
            return swap_data

        except Exception as e:
            logger.debug(f"Error extracting swap data: {e}")
            return []
