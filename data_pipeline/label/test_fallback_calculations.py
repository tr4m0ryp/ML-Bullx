"""
Test fallback calculations for missing token data.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import numpy as np
from datetime import datetime, timedelta
from data_pipeline.label.fallback_calculations import FallbackCalculations


class TestFallbackCalculations:
    """Test fallback calculation methods."""

    def test_volume_24h_calculation(self):
        """Test 24h volume calculation from swaps."""
        now = datetime.now()
        
        # Create recent and old swaps
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
        """Test 24h volume with no recent data."""
        old_time = datetime.now() - timedelta(days=2)
        
        swap_data = [
            {
                'timestamp': old_time.timestamp(),
                'volume_usd': 1000.0
            }
        ]
        
        result = FallbackCalculations.calculate_volume_24h_from_swaps(swap_data)
        assert result is None

    def test_historical_avg_volume(self):
        """Test historical average volume calculation."""
        swap_data = [
            {'volume_usd': 100.0},
            {'volume_usd': 200.0},
            {'volume_usd': 300.0}
        ]
        
        result = FallbackCalculations.calculate_historical_avg_volume(swap_data)
        assert result == 200.0

    def test_historical_avg_volume_insufficient_data(self):
        """Test historical avg with insufficient data."""
        swap_data = [{'volume_usd': 100.0}]  # Only one data point
        
        result = FallbackCalculations.calculate_historical_avg_volume(swap_data)
        assert result is None

    def test_peak_volume_from_swaps(self):
        """Test peak volume calculation from swap data."""
        swap_data = [
            {'volume_usd': 100.0},
            {'volume_usd': 500.0},  # Peak
            {'volume_usd': 200.0}
        ]
        
        result = FallbackCalculations.calculate_peak_volume(swap_data)
        assert result == 500.0

    def test_peak_volume_from_ohlcv(self):
        """Test peak volume calculation from OHLCV data."""
        swap_data = []
        ohlcv_data = [
            {'v': 1000.0},
            {'v': 2000.0},  # Peak
            {'v': 800.0}
        ]
        
        result = FallbackCalculations.calculate_peak_volume(swap_data, ohlcv_data)
        assert result == 2000.0

    def test_launch_price_detection(self):
        """Test launch price detection from earliest swap."""
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
        """Test launch price detection from OHLCV data."""
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

    def test_price_points_count_swaps(self):
        """Test price points counting from swaps."""
        swap_data = [
            {'price': 0.001},
            {'price': 0.002},
            {'price': 0.0}  # Invalid, should not count
        ]
        
        result = FallbackCalculations.count_price_points(swap_data)
        assert result == 2

    def test_price_points_count_ohlcv(self):
        """Test price points counting from OHLCV data."""
        swap_data = []
        ohlcv_data = [
            {'c': 0.001},  # Valid close price
            {'c': 0.002},  # Valid close price
            {'c': 0.0}     # Invalid, should not count
        ]
        
        result = FallbackCalculations.count_price_points(swap_data, ohlcv_data)
        assert result == 2

    def test_transaction_rate_calculation(self):
        """Test daily transaction rate calculation."""
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
        """Test transaction rate with insufficient data."""
        swap_data = [{'timestamp': 1640995200}]  # Only one transaction
        
        result = FallbackCalculations.calculate_transaction_rate(swap_data)
        assert result is None

    def test_market_cap_calculation(self):
        """Test market cap calculation."""
        result = FallbackCalculations.calculate_market_cap(0.001, 1000000)
        assert result == 1000.0

    def test_market_cap_invalid_inputs(self):
        """Test market cap with invalid inputs."""
        assert FallbackCalculations.calculate_market_cap(0.0, 1000000) is None
        assert FallbackCalculations.calculate_market_cap(0.001, 0) is None
        assert FallbackCalculations.calculate_market_cap(None, 1000000) is None

    def test_extract_swap_data_from_analysis(self):
        """Test swap data extraction from analysis result."""
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

    @pytest.mark.asyncio
    async def test_get_token_supply_rpc_success(self):
        """Test successful RPC token supply retrieval."""
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
        """Test RPC token supply retrieval failure."""
        mock_rpc_client = Mock()
        mock_rpc_client.get_token_supply = AsyncMock(side_effect=Exception("RPC error"))
        
        result = await FallbackCalculations.get_token_supply_rpc(
            "test_mint", mock_rpc_client
        )
        
        assert result is None


class TestIntegratedFallbacks:
    """Test integrated fallback functionality."""

    def test_multiple_fallbacks_applied(self):
        """Test that multiple fallbacks can be applied together."""
        now = datetime.now()
        
        # Test data with various missing elements
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
        
        # Test multiple calculations work together
        volume_24h = FallbackCalculations.calculate_volume_24h_from_swaps(swap_data)
        historical_avg = FallbackCalculations.calculate_historical_avg_volume(swap_data)
        launch_price = FallbackCalculations.detect_launch_price(swap_data)
        price_points = FallbackCalculations.count_price_points(swap_data)
        
        assert volume_24h == 1300.0  # Recent swaps total
        assert historical_avg == 650.0  # Average of all volumes
        assert launch_price == 0.001  # Earliest price
        assert price_points == 2  # Two valid price points

    def test_fallback_priority_ohlcv_over_swaps(self):
        """Test that OHLCV data is preferred over individual swaps."""
        swap_data = [{'volume_usd': 100.0}]
        ohlcv_data = [{'v': 500.0}]  # Should be preferred
        
        result = FallbackCalculations.calculate_peak_volume(swap_data, ohlcv_data)
        assert result == 500.0  # OHLCV value chosen over swap value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])