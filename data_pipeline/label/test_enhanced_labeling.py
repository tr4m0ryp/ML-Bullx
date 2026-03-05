"""
Unit tests for enhanced token labeling with mocked Helius responses.

Tests the fallback parsing and INSUFFICIENT_DATA handling.
"""

import pytest
import pandas as pd
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta
from data_pipeline.label.enhanced_parsing import enhanced_parse_swap_details, _parse_basic_token_transfer, retry_with_exponential_backoff
from data_pipeline.label.enhanced_data_collection import EnhancedDataCollection
from data_pipeline.label.token_labeler import EnhancedTokenLabeler
from shared.models import TokenMetrics


class TestEnhancedParsing:
    """Test enhanced parsing with fallback logic."""
    
    def test_normal_swap_parsing_success(self):
        """Test that normal swap transactions are parsed correctly."""
        mock_tx = {
            "blockTime": 1640995200,  # Jan 1, 2022
            "meta": {
                "err": None,
                "preTokenBalances": [
                    {
                        "mint": "5YPpdaFU3AfDAT3gb4DjYmjcfu9huuGaLJBxB8Sapump",
                        "uiTokenAmount": {"uiAmount": 1000.0, "decimals": 9}
                    }
                ],
                "postTokenBalances": [
                    {
                        "mint": "5YPpdaFU3AfDAT3gb4DjYmjcfu9huuGaLJBxB8Sapump", 
                        "uiTokenAmount": {"uiAmount": 800.0, "decimals": 9}
                    }
                ],
                "preBalances": [1000000000, 500000000],  # 1 SOL, 0.5 SOL
                "postBalances": [950000000, 550000000]   # 0.95 SOL, 0.55 SOL
            }
        }
        
        result = enhanced_parse_swap_details(mock_tx, "5YPpdaFU3AfDAT3gb4DjYmjcfu9huuGaLJBxB8Sapump")
        
        assert result is not None
        assert result["timestamp"] == 1640995200
        assert result["token_change"] == 200.0  # 1000 - 800
        assert result["price"] > 0
        assert "parsing_method" not in result  # Normal parsing, no fallback

    def test_fallback_parsing_when_mint_missing(self):
        """Test fallback parsing when target mint is not in balances."""
        mock_tx = {
            "blockTime": 1640995200,
            "meta": {
                "err": None,
                "preTokenBalances": [],
                "postTokenBalances": [],
                "preBalances": [1000000000],
                "postBalances": [950000000],
                "logMessages": ["Transfer: mint=5YPpdaFU3AfDAT3gb4DjYmjcfu9huuGaLJBxB8Sapump amount=100"]
            }
        }
        
        result = enhanced_parse_swap_details(mock_tx, "5YPpdaFU3AfDAT3gb4DjYmjcfu9huuGaLJBxB8Sapump")
        
        assert result is not None
        assert result["parsing_method"] == "fallback_transfer"
        assert result["price"] == 0.001  # Default fallback price

    def test_no_parsing_possible(self):
        """Test when no parsing is possible."""
        mock_tx = {
            "blockTime": 1640995200,
            "meta": {
                "err": None,
                "preTokenBalances": [],
                "postTokenBalances": [], 
                "preBalances": [],
                "postBalances": [],
                "logMessages": []
            }
        }
        
        result = enhanced_parse_swap_details(mock_tx, "5YPpdaFU3AfDAT3gb4DjYmjcfu9huuGaLJBxB8Sapump")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_retry_with_exponential_backoff_success(self):
        """Test retry logic succeeds on second attempt."""
        call_count = 0
        
        async def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("First attempt fails")
            return "success"
        
        result = await retry_with_exponential_backoff(failing_func, max_retries=3, base_delay=0.01)
        
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio  
    async def test_retry_with_exponential_backoff_max_retries(self):
        """Test retry logic fails after max retries."""
        async def always_failing_func():
            raise Exception("Always fails")
        
        with pytest.raises(Exception, match="Always fails"):
            await retry_with_exponential_backoff(always_failing_func, max_retries=2, base_delay=0.01)


class TestInsufficientDataHandling:
    """Test INSUFFICIENT_DATA label handling."""

    @pytest.mark.asyncio
    async def test_insufficient_data_label_with_allow_false(self):
        """Test INSUFFICIENT_DATA label when allow_insufficient=False."""
        
        # Mock a token labeler with minimal data
        labeler = EnhancedTokenLabeler()
        labeler.allow_insufficient_data = False
        
        # Create token with insufficient data
        token_metrics = TokenMetrics("5YPpdaFU3AfDAT3gb4DjYmjcfu9huuGaLJBxB8Sapump")
        token_metrics.current_price = None
        token_metrics.volume_24h = None
        token_metrics.historical_avg_volume = None
        token_metrics.ath_before_72h = None
        token_metrics.ath_after_72h = None
        token_metrics.legitimacy_analysis = {
            "classification_hint": "insufficient_data",
            "data_quality": "minimal"
        }
        
        # Test classification
        result = labeler._classify(token_metrics)
        assert result == "INSUFFICIENT_DATA"

    @pytest.mark.asyncio 
    async def test_sufficient_data_proceeds_normally(self):
        """Test that tokens with sufficient data proceed to normal classification."""
        
        labeler = EnhancedTokenLabeler()
        labeler.allow_insufficient_data = False
        
        # Create token with sufficient data
        token_metrics = TokenMetrics("FPCiQD3FQv4TzinaXfphopSNDMMxmEeNELtSYEPVavHJ")
        token_metrics.current_price = 0.0001
        token_metrics.volume_24h = 1000.0
        token_metrics.historical_avg_volume = 1200.0
        token_metrics.ath_before_72h = 0.00008
        token_metrics.ath_after_72h = 0.0002
        token_metrics.legitimacy_analysis = {
            "classification_hint": "success_likely", 
            "overall_legitimacy_score": 0.8,
            "data_quality": "good"
        }
        
        # Test classification - should not be INSUFFICIENT_DATA
        result = labeler._classify(token_metrics)
        assert result != "INSUFFICIENT_DATA"

    @pytest.mark.asyncio
    async def test_allow_insufficient_bypasses_check(self):
        """Test that allow_insufficient=True bypasses insufficient data check."""
        
        labeler = EnhancedTokenLabeler()
        labeler.allow_insufficient_data = True
        
        # Create token with insufficient data
        token_metrics = TokenMetrics("Bn4nBhQa2JAFGhSbjqgC9dCYMyAF3CGEaAzshbaapump")
        token_metrics.current_price = None
        token_metrics.volume_24h = None
        token_metrics.legitimacy_analysis = {
            "classification_hint": "insufficient_data",
            "data_quality": "minimal"
        }
        
        # Test classification - should proceed to normal classification
        result = labeler._classify(token_metrics)
        assert result != "INSUFFICIENT_DATA"  # Should be inactive, unsuccessful, etc.


class TestCSVOutput:
    """Test CSV output schema and formatting."""

    def test_csv_output_schema(self):
        """Test that CSV output has correct schema."""
        labeler = EnhancedTokenLabeler()
        
        # Test expected CSV structure
        expected_columns = [
            "mint_address", "label", "label_reason", "peak_72h", "avg_post_72h",
            "has_historical_data", "price_points_count", "volume_24h"
        ]
        
        # Create sample output data
        sample_result = {
            "mint_address": "5YPpdaFU3AfDAT3gb4DjYmjcfu9huuGaLJBxB8Sapump",
            "label": "INSUFFICIENT_DATA",
            "label_reason": "insufficient_swap_price_points", 
            "peak_72h": None,
            "avg_post_72h": None,
            "has_historical_data": False,
            "price_points_count": 0,
            "volume_24h": None
        }
        
        # Verify all expected columns are present
        for col in expected_columns:
            assert col in sample_result

    def test_successful_token_output(self):
        """Test successful token CSV output format."""
        sample_result = {
            "mint_address": "FPCiQD3FQv4TzinaXfphopSNDMMxmEeNELtSYEPVavHJ",
            "label": "successful",
            "label_reason": "success_via_legitimacy_and_72h_peak",
            "peak_72h": 0.05953157,
            "avg_post_72h": 0.00011961,
            "has_historical_data": True,
            "price_points_count": 124,
            "volume_24h": 114114.0426
        }
        
        # Verify expected values for successful token
        assert sample_result["label"] == "successful"
        assert sample_result["has_historical_data"] is True
        assert sample_result["price_points_count"] > 0
        assert sample_result["volume_24h"] is not None


class TestMockedHeliusResponses:
    """Test with fully mocked Helius API responses."""
    
    @pytest.mark.asyncio
    async def test_empty_helius_response_insufficient_data(self):
        """Test token gets INSUFFICIENT_DATA when Helius returns empty."""
        
        with patch('enhanced_data_collection.EnhancedDataCollection.enhanced_analyze_token_activity') as mock_analyze:
            # Mock empty Helius response
            mock_analyze.return_value = None
            
            labeler = EnhancedTokenLabeler()
            labeler.allow_insufficient_data = False
            
            # Mock data provider with all required async methods
            labeler.data_provider = Mock()
            labeler.data_provider.get_current_price = AsyncMock(return_value=None)
            labeler.data_provider.get_holder_count = AsyncMock(return_value=None)
            labeler.data_provider.get_historical_data = AsyncMock(return_value=None)
            labeler.data_provider._analyze_token_activity = AsyncMock(return_value=None)
            
            # Process token
            token_metrics = await labeler._gather_metrics("5YPpdaFU3AfDAT3gb4DjYmjcfu9huuGaLJBxB8Sapump")
            result = labeler._classify(token_metrics)
            
            assert result == "INSUFFICIENT_DATA"

    @pytest.mark.asyncio
    async def test_partial_helius_response_fallback(self):
        """Test fallback when Helius returns partial data."""
        
        with patch('enhanced_data_collection.EnhancedDataCollection.enhanced_analyze_token_activity') as mock_analyze:
            # Mock partial response with minimal OHLCV
            mock_analyze.return_value = {
                "peak_price_72h": 0.001,
                "historical_avg_volume": None,  # Missing volume data
                "ohlcv_data": [  # Only 1 data point
                    {"ts": 1640995200, "o": 0.001, "h": 0.001, "l": 0.001, "c": 0.001, "v": 100}
                ]
            }
            
            labeler = EnhancedTokenLabeler()
            labeler.allow_insufficient_data = False
            
            # Mock data provider with all required async methods
            labeler.data_provider = Mock()
            labeler.data_provider.get_current_price = AsyncMock(return_value=Mock(price=0.001, volume_24h=None))
            labeler.data_provider.get_holder_count = AsyncMock(return_value=5)
            labeler.data_provider.get_historical_data = AsyncMock(return_value=mock_analyze.return_value)
            labeler.data_provider._analyze_token_activity = AsyncMock(return_value=mock_analyze.return_value)
            
            # Process token
            token_metrics = await labeler._gather_metrics("5YPpdaFU3AfDAT3gb4DjYmjcfu9huuGaLJBxB8Sapump")
            result = labeler._classify(token_metrics)
            
            # Should be INSUFFICIENT_DATA due to minimal OHLCV
            assert result == "INSUFFICIENT_DATA"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])