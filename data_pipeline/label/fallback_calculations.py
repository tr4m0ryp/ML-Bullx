"""
Fallback calculation methods for missing token data.
These methods attempt to calculate missing metrics from available data.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

class FallbackCalculations:
    """Provides fallback calculations for missing token data."""
    
    @staticmethod
    def calculate_volume_24h_from_swaps(swap_data: List[Dict[str, Any]]) -> Optional[float]:
        """
        Calculate 24h volume from swap data.
        
        Args:
            swap_data: List of swap dictionaries with 'timestamp' and 'volume_usd'
            
        Returns:
            24h volume in USD or None if insufficient data
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
        """
        Calculate historical average volume from all swap data.
        
        Args:
            swap_data: List of swap dictionaries with 'volume_usd'
            
        Returns:
            Average volume in USD or None if insufficient data
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
        """
        Calculate peak volume from swap data or OHLCV data.
        
        Args:
            swap_data: List of swap dictionaries with 'volume_usd'
            ohlcv_data: Optional OHLCV data with 'v' (volume) field
            
        Returns:
            Peak volume in USD or None if insufficient data
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
    
    @staticmethod
    def detect_launch_price(swap_data: List[Dict[str, Any]], ohlcv_data: List[Dict[str, Any]] = None) -> Optional[float]:
        """
        Detect launch price from earliest swap or OHLCV data.
        
        Args:
            swap_data: List of swap dictionaries with 'timestamp' and 'price'
            ohlcv_data: Optional OHLCV data with timestamps
            
        Returns:
            Launch price or None if not found
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
    
    @staticmethod  
    def count_price_points(swap_data: List[Dict[str, Any]], ohlcv_data: List[Dict[str, Any]] = None) -> int:
        """
        Count actual price data points available.
        
        Args:
            swap_data: List of swap dictionaries
            ohlcv_data: Optional OHLCV data
            
        Returns:
            Number of price data points
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
        """
        Calculate average daily transaction rate.
        
        Args:
            swap_data: List of swap dictionaries with timestamps
            total_days: Total days to calculate rate over (auto-detected if None)
            
        Returns:
            Transactions per day or None if insufficient data
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

    @staticmethod
    async def get_token_supply_rpc(mint_address: str, rpc_client) -> Optional[int]:
        """
        Get token supply using Solana RPC.
        
        Args:
            mint_address: Token mint address
            rpc_client: Solana RPC client
            
        Returns:
            Token supply or None if failed
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
    
    @staticmethod
    def calculate_market_cap(current_price: Optional[float], token_supply: Optional[int]) -> Optional[float]:
        """
        Calculate market cap from price and supply.
        
        Args:
            current_price: Current token price in USD
            token_supply: Total token supply
            
        Returns:
            Market cap in USD or None if insufficient data
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

    @staticmethod
    def extract_swap_data_from_analysis(analysis_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract swap data from enhanced analysis result.
        
        Args:
            analysis_result: Result from enhanced token analysis
            
        Returns:
            List of swap data dictionaries
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