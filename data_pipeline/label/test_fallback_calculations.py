"""
Unit Tests for Fallback Calculation Methods.

Validates every static method in ``FallbackCalculations`` with both
normal and edge-case inputs:
- Volume 24-hour aggregation with recent and stale data.
- Historical average volume with sufficient and insufficient records.
- Peak volume detection from swaps and OHLCV data.
- Launch price detection from swaps and OHLCV candles.
- Price point counting from swaps and OHLCV data.
- Transaction rate calculation and edge cases.
- Market cap computation with valid and invalid inputs.
- Swap data extraction from analysis result dictionaries.
- Async RPC token supply retrieval (success and failure).
- Integrated multi-fallback scenarios.

Author: ML-Bullx Team
Date: 2025-08-01
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest

from data_pipeline.label.fallback_calculations import FallbackCalculations


# =============================================================================
# TestFallbackCalculations
# =============================================================================

class TestFallbackCalculations:
    """Test individual fallback calculation methods."""

    # -------------------------------------------------------------------------
    # 24-Hour Volume
    # -------------------------------------------------------------------------

    def test_volume_24h_calculation(self):
        """Verify that only swaps within the last 24 hours are summed."""
        now = datetime.now()

        swap_data = [
            {
                'timestamp': (now - timedelta(hours=1)).timestamp(),
                'volume_usd': 1000.0
            },
            {
                'timestamp': (now - timedelta(hours=12)).timestamp(),
                'volume_usd': 2000.0
            },
            {
                'timestamp': (now - timedelta(hours=30)).timestamp(),  # Too old
                'volume_usd': 5000.0
            }
        ]

        result = FallbackCalculations.calculate_volume_24h_from_swaps(swap_data)

        assert result == 3000.0  # Only recent swaps

    def test_volume_24h_no_recent_data(self):
        """Verify None is returned when all swaps are older than 24 hours."""
        old_time = datetime.now() - timedelta(days=2)

        swap_data = [
            {
                'timestamp': old_time.timestamp(),
                'volume_usd': 1000.0
            }
        ]

        result = FallbackCalculations.calculate_volume_24h_from_swaps(swap_data)
        assert result is None

    # -------------------------------------------------------------------------
    # Historical Average Volume
    # -------------------------------------------------------------------------

    def test_historical_avg_volume(self):
        """Verify correct arithmetic mean across three swap volumes."""
        swap_data = [
            {'volume_usd': 100.0},
            {'volume_usd': 200.0},
            {'volume_usd': 300.0}
        ]

        result = FallbackCalculations.calculate_historical_avg_volume(swap_data)
        assert result == 200.0

    def test_historical_avg_volume_insufficient_data(self):
        """Verify None is returned when fewer than two data points exist."""
        swap_data = [{'volume_usd': 100.0}]  # Only one data point

        result = FallbackCalculations.calculate_historical_avg_volume(swap_data)
        assert result is None

    # -------------------------------------------------------------------------
    # Peak Volume
    # -------------------------------------------------------------------------

    def test_peak_volume_from_swaps(self):
        """Verify peak volume is the maximum across individual swaps."""
        swap_data = [
            {'volume_usd': 100.0},
            {'volume_usd': 500.0},  # Peak
            {'volume_usd': 200.0}
        ]

        result = FallbackCalculations.calculate_peak_volume(swap_data)
        assert result == 500.0

    def test_peak_volume_from_ohlcv(self):
        """Verify OHLCV volume data takes precedence over empty swaps."""
        swap_data = []
        ohlcv_data = [
            {'v': 1000.0},
            {'v': 2000.0},  # Peak
            {'v': 800.0}
        ]

        result = FallbackCalculations.calculate_peak_volume(swap_data, ohlcv_data)
        assert result == 2000.0

    # -------------------------------------------------------------------------
    # Launch Price Detection
    # -------------------------------------------------------------------------

    def test_launch_price_detection(self):
        """Verify that the price with the earliest timestamp is selected."""
        base_time = 1640995200  # Jan 1, 2022

        swap_data = [
            {
                'timestamp': base_time + 3600,  # 1 hour later
                'price': 0.002
            },
            {
                'timestamp': base_time,  # Earliest
                'price': 0.001
            },
            {
                'timestamp': base_time + 7200,  # 2 hours later
                'price': 0.003
            }
        ]

        result = FallbackCalculations.detect_launch_price(swap_data)
        assert result == 0.001  # Earliest price

    def test_launch_price_from_ohlcv(self):
        """Verify launch price detection from OHLCV open prices."""
        base_time = 1640995200

        swap_data = []
        ohlcv_data = [
            {
                'timestamp': base_time + 3600,
                'o': 0.002  # Open price 1 hour later
            },
            {
                'timestamp': base_time,  # Earliest
                'o': 0.001  # Launch price
            }
        ]

        result = FallbackCalculations.detect_launch_price(swap_data, ohlcv_data)
        assert result == 0.001

    # -------------------------------------------------------------------------
    # Price Point Counting
    # -------------------------------------------------------------------------

    def test_price_points_count_swaps(self):
        """Verify that only positive swap prices are counted."""
        swap_data = [
            {'price': 0.001},
            {'price': 0.002},
            {'price': 0.0}  # Invalid, should not count
        ]

        result = FallbackCalculations.count_price_points(swap_data)
        assert result == 2

    def test_price_points_count_ohlcv(self):
        """Verify that OHLCV close prices are preferred over swaps."""
        swap_data = []
        ohlcv_data = [
            {'c': 0.001},  # Valid close price
            {'c': 0.002},  # Valid close price
            {'c': 0.0}     # Invalid, should not count
        ]

        result = FallbackCalculations.count_price_points(swap_data, ohlcv_data)
        assert result == 2

    # -------------------------------------------------------------------------
    # Transaction Rate
    # -------------------------------------------------------------------------

    def test_transaction_rate_calculation(self):
        """Verify daily transaction rate over a 24-hour span."""
        base_time = 1640995200

        swap_data = [
            {'timestamp': base_time},
            {'timestamp': base_time + 43200},  # 12 hours later
            {'timestamp': base_time + 86400}   # 24 hours later (3 total swaps)
        ]

        result = FallbackCalculations.calculate_transaction_rate(swap_data)

        # 3 transactions over 1 day = 3 tx/day
        assert result == 3.0

    def test_transaction_rate_insufficient_data(self):
        """Verify None is returned with only one transaction."""
        swap_data = [{'timestamp': 1640995200}]  # Only one transaction

        result = FallbackCalculations.calculate_transaction_rate(swap_data)
        assert result is None

    # -------------------------------------------------------------------------
    # Market Cap
    # -------------------------------------------------------------------------

    def test_market_cap_calculation(self):
        """Verify market cap equals price times supply."""
        result = FallbackCalculations.calculate_market_cap(0.001, 1000000)
        assert result == 1000.0

    def test_market_cap_invalid_inputs(self):
        """Verify None is returned for zero, negative, or missing inputs."""
        assert FallbackCalculations.calculate_market_cap(0.0, 1000000) is None
        assert FallbackCalculations.calculate_market_cap(0.001, 0) is None
        assert FallbackCalculations.calculate_market_cap(None, 1000000) is None

    # -------------------------------------------------------------------------
    # Swap Data Extraction
    # -------------------------------------------------------------------------

    def test_extract_swap_data_from_analysis(self):
        """Verify OHLCV candles are normalized into swap dictionaries."""
        analysis_result = {
            'ohlcv': [
                {'ts': 1640995200, 'c': 0.001, 'v': 1000.0, 'h': 0.0012, 'l': 0.0009},
                {'ts': 1640995260, 'c': 0.002, 'v': 2000.0, 'h': 0.0022, 'l': 0.0018}
            ]
        }

        result = FallbackCalculations.extract_swap_data_from_analysis(analysis_result)

        assert len(result) == 2
        assert result[0]['timestamp'] == 1640995200
        assert result[0]['price'] == 0.001
        assert result[0]['volume_usd'] == 1000.0

    # -------------------------------------------------------------------------
    # Async RPC Token Supply
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_token_supply_rpc_success(self):
        """Verify successful RPC token supply retrieval."""
        mock_rpc_client = Mock()
        mock_response = Mock()
        mock_response.value.ui_amount = 1000000.0
        mock_rpc_client.get_token_supply = AsyncMock(return_value=mock_response)

        result = await FallbackCalculations.get_token_supply_rpc(
            "test_mint", mock_rpc_client
        )

        assert result == 1000000

    @pytest.mark.asyncio
    async def test_get_token_supply_rpc_failure(self):
        """Verify None is returned when the RPC call raises an exception."""
        mock_rpc_client = Mock()
        mock_rpc_client.get_token_supply = AsyncMock(side_effect=Exception("RPC error"))

        result = await FallbackCalculations.get_token_supply_rpc(
            "test_mint", mock_rpc_client
        )

        assert result is None


# =============================================================================
# TestIntegratedFallbacks
# =============================================================================

class TestIntegratedFallbacks:
    """Test that multiple fallback calculations compose correctly."""

    def test_multiple_fallbacks_applied(self):
        """Verify several fallback methods produce consistent results together."""
        now = datetime.now()

        swap_data = [
            {
                'timestamp': (now - timedelta(hours=2)).timestamp(),
                'price': 0.001,
                'volume_usd': 500.0
            },
            {
                'timestamp': (now - timedelta(hours=1)).timestamp(),
                'price': 0.002,
                'volume_usd': 800.0
            }
        ]

        volume_24h = FallbackCalculations.calculate_volume_24h_from_swaps(swap_data)
        historical_avg = FallbackCalculations.calculate_historical_avg_volume(swap_data)
        launch_price = FallbackCalculations.detect_launch_price(swap_data)
        price_points = FallbackCalculations.count_price_points(swap_data)

        assert volume_24h == 1300.0  # Recent swaps total
        assert historical_avg == 650.0  # Average of all volumes
        assert launch_price == 0.001  # Earliest price
        assert price_points == 2  # Two valid price points

    def test_fallback_priority_ohlcv_over_swaps(self):
        """Verify that OHLCV data is preferred over individual swap records."""
        swap_data = [{'volume_usd': 100.0}]
        ohlcv_data = [{'v': 500.0}]  # Should be preferred

        result = FallbackCalculations.calculate_peak_volume(swap_data, ohlcv_data)
        assert result == 500.0  # OHLCV value chosen over swap value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
