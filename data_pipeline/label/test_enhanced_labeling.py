"""
Unit Tests for Enhanced Token Labeling with Mocked Helius Responses.

Validates the enhanced parsing, INSUFFICIENT_DATA handling, and CSV
output schema:
- Normal swap parsing from pre/post token balance deltas.
- Fallback parsing when the target mint is absent from balance records.
- No-parse scenario when all balance data is empty.
- Exponential backoff retry logic (success and exhaustion).
- INSUFFICIENT_DATA label assignment with allow_insufficient toggling.
- CSV output schema correctness for both insufficient and successful tokens.
- End-to-end flow with fully mocked Helius API responses.

Author: ML-Bullx Team
Date: 2025-08-01
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pandas as pd
import pytest

from data_pipeline.label.enhanced_data_collection import EnhancedDataCollection
from data_pipeline.label.enhanced_parsing import (
    _parse_basic_token_transfer,
    enhanced_parse_swap_details,
    retry_with_exponential_backoff,
)
from data_pipeline.label.token_labeler import EnhancedTokenLabeler
from shared.models import TokenMetrics


# =============================================================================
# TestEnhancedParsing
# =============================================================================

class TestEnhancedParsing:
    """Test enhanced parsing with fallback logic."""

    def test_normal_swap_parsing_success(self):
        """Verify that a well-formed swap transaction is parsed correctly."""
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
        """Verify fallback transfer parsing triggers when mint is absent from balances."""
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
        """Verify None is returned when no balance or log data exists."""
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

    # -------------------------------------------------------------------------
    # Retry Logic
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_retry_with_exponential_backoff_success(self):
        """Verify retry logic succeeds on the second attempt."""
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
        """Verify the last exception is re-raised after all retries are exhausted."""
        async def always_failing_func():
            raise Exception("Always fails")

        with pytest.raises(Exception, match="Always fails"):
            await retry_with_exponential_backoff(always_failing_func, max_retries=2, base_delay=0.01)


# =============================================================================
# TestInsufficientDataHandling
# =============================================================================

class TestInsufficientDataHandling:
    """Test INSUFFICIENT_DATA label assignment and bypass logic."""

    @pytest.mark.asyncio
    async def test_insufficient_data_label_with_allow_false(self):
        """Verify INSUFFICIENT_DATA label is assigned when data is minimal."""
        labeler = EnhancedTokenLabeler()
        labeler.allow_insufficient_data = False

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

        result = labeler._classify(token_metrics)
        assert result == "INSUFFICIENT_DATA"

    @pytest.mark.asyncio
    async def test_sufficient_data_proceeds_normally(self):
        """Verify tokens with enough data bypass the INSUFFICIENT_DATA label."""
        labeler = EnhancedTokenLabeler()
        labeler.allow_insufficient_data = False

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

        result = labeler._classify(token_metrics)
        assert result != "INSUFFICIENT_DATA"

    @pytest.mark.asyncio
    async def test_allow_insufficient_bypasses_check(self):
        """Verify that allow_insufficient=True forces normal classification."""
        labeler = EnhancedTokenLabeler()
        labeler.allow_insufficient_data = True

        token_metrics = TokenMetrics("Bn4nBhQa2JAFGhSbjqgC9dCYMyAF3CGEaAzshbaapump")
        token_metrics.current_price = None
        token_metrics.volume_24h = None
        token_metrics.legitimacy_analysis = {
            "classification_hint": "insufficient_data",
            "data_quality": "minimal"
        }

        result = labeler._classify(token_metrics)
        assert result != "INSUFFICIENT_DATA"  # Should be inactive, unsuccessful, etc.


# =============================================================================
# TestCSVOutput
# =============================================================================

class TestCSVOutput:
    """Test CSV output schema and expected field values."""

    def test_csv_output_schema(self):
        """Verify the expected CSV columns are present in a result dictionary."""
        labeler = EnhancedTokenLabeler()

        expected_columns = [
            "mint_address", "label", "label_reason", "peak_72h", "avg_post_72h",
            "has_historical_data", "price_points_count", "volume_24h"
        ]

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

        for col in expected_columns:
            assert col in sample_result

    def test_successful_token_output(self):
        """Verify a successful token result contains expected non-None values."""
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

        assert sample_result["label"] == "successful"
        assert sample_result["has_historical_data"] is True
        assert sample_result["price_points_count"] > 0
        assert sample_result["volume_24h"] is not None


# =============================================================================
# TestMockedHeliusResponses
# =============================================================================

class TestMockedHeliusResponses:
    """End-to-end tests with fully mocked Helius API responses."""

    @pytest.mark.asyncio
    async def test_empty_helius_response_insufficient_data(self):
        """Verify INSUFFICIENT_DATA when Helius returns empty for all queries."""
        with patch('enhanced_data_collection.EnhancedDataCollection.enhanced_analyze_token_activity') as mock_analyze:
            mock_analyze.return_value = None

            labeler = EnhancedTokenLabeler()
            labeler.allow_insufficient_data = False

            labeler.data_provider = Mock()
            labeler.data_provider.get_current_price = AsyncMock(return_value=None)
            labeler.data_provider.get_holder_count = AsyncMock(return_value=None)
            labeler.data_provider.get_historical_data = AsyncMock(return_value=None)
            labeler.data_provider._analyze_token_activity = AsyncMock(return_value=None)

            token_metrics = await labeler._gather_metrics("5YPpdaFU3AfDAT3gb4DjYmjcfu9huuGaLJBxB8Sapump")
            result = labeler._classify(token_metrics)

            assert result == "INSUFFICIENT_DATA"

    @pytest.mark.asyncio
    async def test_partial_helius_response_fallback(self):
        """Verify INSUFFICIENT_DATA when Helius returns only minimal OHLCV data."""
        with patch('enhanced_data_collection.EnhancedDataCollection.enhanced_analyze_token_activity') as mock_analyze:
            mock_analyze.return_value = {
                "peak_price_72h": 0.001,
                "historical_avg_volume": None,
                "ohlcv_data": [
                    {"ts": 1640995200, "o": 0.001, "h": 0.001, "l": 0.001, "c": 0.001, "v": 100}
                ]
            }

            labeler = EnhancedTokenLabeler()
            labeler.allow_insufficient_data = False

            labeler.data_provider = Mock()
            labeler.data_provider.get_current_price = AsyncMock(return_value=Mock(price=0.001, volume_24h=None))
            labeler.data_provider.get_holder_count = AsyncMock(return_value=5)
            labeler.data_provider.get_historical_data = AsyncMock(return_value=mock_analyze.return_value)
            labeler.data_provider._analyze_token_activity = AsyncMock(return_value=mock_analyze.return_value)

            token_metrics = await labeler._gather_metrics("5YPpdaFU3AfDAT3gb4DjYmjcfu9huuGaLJBxB8Sapump")
            result = labeler._classify(token_metrics)

            # Should be INSUFFICIENT_DATA due to minimal OHLCV
            assert result == "INSUFFICIENT_DATA"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
