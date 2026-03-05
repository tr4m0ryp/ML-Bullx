"""
Enhanced data collection patches for the token labeler.
This module provides fixes for the data collection issues in the original system.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import pandas as pd
import asyncio
from data_pipeline.label.enhanced_parsing import enhanced_is_swap_transaction, enhanced_parse_swap_details, retry_with_exponential_backoff, log_parsing_failure
from data_pipeline.label.fallback_calculations import FallbackCalculations

logger = logging.getLogger(__name__)

class EnhancedDataCollection:
    """Enhanced data collection methods to patch the original OnChainDataProvider."""
    
    @staticmethod
    async def enhanced_analyze_token_activity(data_provider, mint: str) -> Optional[Dict[str, Any]]:
        """
        Enhanced version of _analyze_token_activity with better transaction parsing.
        """
        cache_key = f"activity_{mint}"
        if cache_key in data_provider._activity_cache:
            data, cached_at = data_provider._activity_cache[cache_key]
            if data_provider.config and hasattr(data_provider.config, 'cache') and hasattr(data_provider.config.cache, 'price_cache_ttl'):
                ttl = data_provider.config.cache.price_cache_ttl
            else:
                ttl = 60  # Default TTL
            
            if hasattr(data_provider, '_activity_cache') and data_provider._activity_cache:
                import time
                if time.time() - cached_at < ttl:
                    logger.info(f"Returning cached activity for {mint}")
                    return data

        logger.info(f"Performing ENHANCED on-chain activity analysis for {mint}")
        signatures = await data_provider._get_signatures_for_address(mint, get_all=True)
        if not signatures:
            logger.info(f"No signatures found for {mint}")
            return None
        
        all_swaps = []
        price_history = []
        batch_size = 20
        
        # Analyze more transactions for better data
        max_tx = min(len(signatures), 1000)  # Increased from 500
        
        logger.info(f"Analyzing {max_tx} transactions for {mint} in batches of {batch_size}")
        successful_parses = 0
        failed_parses = 0
        rate_limited = 0
        
        for i in range(0, max_tx, batch_size):
            batch_sigs = signatures[i:i + batch_size]
            
            # Use retry logic for transaction fetching
            async def fetch_batch():
                tasks = [data_provider._get_transaction_details(sig) for sig in batch_sigs]
                return await asyncio.gather(*tasks, return_exceptions=True)
            
            transactions = await retry_with_exponential_backoff(fetch_batch)
            
            for j, tx in enumerate(transactions):
                if isinstance(tx, dict) and tx:
                    # Use enhanced swap detection
                    if enhanced_is_swap_transaction(tx):
                        # Use enhanced swap parsing
                        swap_info = enhanced_parse_swap_details(tx, mint)
                        if swap_info:
                            all_swaps.append(swap_info)
                            if 'timestamp' in swap_info and 'price' in swap_info:
                                price_history.append({
                                    'timestamp': swap_info['timestamp'], 
                                    'price': swap_info['price'], 
                                    'volume': swap_info.get('volume_usd', 0)
                                })
                            successful_parses += 1
                        else:
                            failed_parses += 1
                            # Log parsing failure for debugging
                            if j < len(batch_sigs):
                                log_parsing_failure(mint, batch_sigs[j], "swap_parsing_failed")
                    else:
                        failed_parses += 1
                        # Log parsing failure for debugging
                        if j < len(batch_sigs):
                            log_parsing_failure(mint, batch_sigs[j], "not_swap_transaction")
                elif isinstance(tx, Exception):
                    logger.debug(f"Transaction fetch failed: {tx}")
                    rate_limited += 1
                    # Log API failure
                    if j < len(batch_sigs):
                        log_parsing_failure(mint, batch_sigs[j], f"api_error:{str(tx)}")
                else:
                    failed_parses += 1
                    # Log unknown failure
                    if j < len(batch_sigs):
                        log_parsing_failure(mint, batch_sigs[j], "unknown_failure")
            
            # Shorter delay to reduce rate limiting impact
            await asyncio.sleep(0.2)
        
        logger.info(f"Enhanced parsing results for {mint}: {successful_parses} successful, {failed_parses} failed, {rate_limited} rate-limited")
        logger.info(f"Collected {len(all_swaps)} swaps and {len(price_history)} price points for {mint}")
        
        if not price_history:
            logger.warning(f"No price history could be built from swaps for {mint}")
            return None

        # Use enhanced history building
        analysis = EnhancedDataCollection.enhanced_build_history_from_swaps(price_history, mint)
        logger.info(f"Built enhanced historical analysis for {mint}: {list(analysis.keys())}")
        
        # Cache the result
        if hasattr(data_provider, '_activity_cache'):
            import time
            data_provider._activity_cache[cache_key] = (analysis, time.time())
        
        return analysis
    
    @staticmethod
    def enhanced_build_history_from_swaps(price_history: List[Dict[str, Any]], mint: str) -> Dict[str, Any]:
        """
        Enhanced version of _build_history_from_swaps with better data handling.
        """
        logger.debug(f"Enhanced _build_history_from_swaps for {mint}: Received {len(price_history)} price points.")
        if not price_history:
            logger.debug(f"Enhanced _build_history_from_swaps for {mint}: price_history is empty.")
            return {}
        
        df = pd.DataFrame(price_history)
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
        df.sort_values('datetime', inplace=True)
        logger.debug(f"Enhanced _build_history_from_swaps for {mint}: DataFrame shape: {df.shape}")
        
        # Remove obvious outliers (prices that are 100x different from median)
        if len(df) > 3:
            median_price = df['price'].median()
            df = df[df['price'] <= median_price * 100]  # Remove extreme outliers
            df = df[df['price'] >= median_price / 100]  # Remove extreme low prices
            logger.debug(f"After outlier removal: {len(df)} price points remain")
        
        # Enhanced OHLCV resampling with multiple timeframes
        # Start with 1-minute, then 5-minute for sparse data
        ohlcv_1min = df.set_index('datetime')['price'].resample('1min').ohlc().dropna()
        volume_1min = df.set_index('datetime')['volume'].resample('1min').sum().dropna()
        
        if len(ohlcv_1min) < 10:  # If very sparse, use 5-minute
            ohlcv = df.set_index('datetime')['price'].resample('5min').ohlc().dropna()
            volume = df.set_index('datetime')['volume'].resample('5min').sum().dropna()
            logger.debug(f"Using 5-minute OHLCV due to sparse data: {len(ohlcv)} records")
        else:
            ohlcv = ohlcv_1min
            volume = volume_1min
            logger.debug(f"Using 1-minute OHLCV: {len(ohlcv)} records")
        
        if ohlcv.empty:
            logger.warning(f"No OHLCV data after resampling for {mint}")
            return {}
        
        ohlcv = ohlcv.join(volume, how='left').fillna(0)
        ohlcv.rename(columns={'volume': 'v', 'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c'}, inplace=True)
        ohlcv['ts'] = ohlcv.index.astype(int) // 10**9
        
        logger.debug(f"Enhanced _build_history_from_swaps for {mint}: Final OHLCV shape: {ohlcv.shape}")
        
        launch_time = df['datetime'].min()
        hours_72_cutoff = launch_time + timedelta(hours=72)
        
        early_df = df[df['datetime'] <= hours_72_cutoff]
        post_df = df[df['datetime'] > hours_72_cutoff]
        logger.debug(f"Enhanced _build_history_from_swaps for {mint}: early_df: {len(early_df)}, post_df: {len(post_df)}")
        
        # Enhanced price calculations
        all_time_high = df['price'].max() if not df.empty else None
        all_time_low = df['price'].min() if not df.empty else None
        
        # More accurate launch price (use first few transactions average)
        launch_price = df['price'].head(5).mean() if len(df) >= 5 else df['price'].iloc[0] if not df.empty else None
        
        # Peak price within 72h of launch
        peak_price_72h = early_df['price'].max() if not early_df.empty else None
        
        # Current price (last transaction)
        current_price = df['price'].iloc[-1] if not df.empty else None
        
        # Enhanced volume calculations
        total_volume = df['volume'].sum()
        volume_24h = df[df['datetime'] >= datetime.now() - timedelta(hours=24)]['volume'].sum()
        avg_daily_volume = total_volume / max((df['datetime'].max() - df['datetime'].min()).days, 1) if len(df) > 1 else total_volume
        
        result = {
            'ohlcv': ohlcv.reset_index().to_dict('records'),
            'launch_price': launch_price,
            'peak_price_72h': peak_price_72h,
            'post_ath_peak_price': all_time_high,  # This is the true ATH
            'current_price': current_price,
            'volume_24h': volume_24h,
            'total_volume': total_volume,
            'avg_daily_volume': avg_daily_volume,
            'all_time_high': all_time_high,
            'all_time_low': all_time_low,
            'total_transactions': len(df),
            'price_range_ratio': (all_time_high / all_time_low) if all_time_low and all_time_low > 0 else None,
            'days_active': (df['datetime'].max() - df['datetime'].min()).days if len(df) > 1 else 0
        }
        
        # Apply fallback calculations for missing data
        swap_data = []
        for _, row in df.iterrows():
            swap_data.append({
                'timestamp': row['datetime'].timestamp(),
                'price': row['price'],
                'volume_usd': row.get('volume', 0)
            })
        
        # Fallback calculations for critical missing metrics
        if not result.get('volume_24h'):
            fallback_24h = FallbackCalculations.calculate_volume_24h_from_swaps(swap_data)
            if fallback_24h:
                result['volume_24h'] = fallback_24h
                logger.info(f"Applied fallback 24h volume: ${fallback_24h:.2f}")
        
        if not result.get('launch_price'):
            fallback_launch = FallbackCalculations.detect_launch_price(swap_data, ohlcv.to_dict('records'))
            if fallback_launch:
                result['launch_price'] = fallback_launch
                logger.info(f"Applied fallback launch price: ${fallback_launch:.8f}")
        
        # Add accurate price points count
        price_points_count = FallbackCalculations.count_price_points(swap_data, ohlcv.to_dict('records'))
        result['price_points_count'] = price_points_count
        logger.debug(f"Counted {price_points_count} price data points")
        
        # Enhanced historical average volume calculation
        if not result.get('avg_daily_volume') or result.get('avg_daily_volume', 0) == 0:
            fallback_historical_avg = FallbackCalculations.calculate_historical_avg_volume(swap_data)
            if fallback_historical_avg:
                result['historical_avg_volume'] = fallback_historical_avg
                logger.info(f"Applied fallback historical avg volume: ${fallback_historical_avg:.2f}")
        
        # Enhanced peak volume calculation  
        if not result.get('peak_volume'):
            fallback_peak_vol = FallbackCalculations.calculate_peak_volume(swap_data, ohlcv.to_dict('records'))
            if fallback_peak_vol:
                result['peak_volume'] = fallback_peak_vol
                logger.info(f"Applied fallback peak volume: ${fallback_peak_vol:.2f}")
        
        # Transaction rate calculation
        fallback_tx_rate = FallbackCalculations.calculate_transaction_rate(swap_data)
        if fallback_tx_rate:
            result['transaction_rate_daily'] = fallback_tx_rate
            logger.debug(f"Calculated transaction rate: {fallback_tx_rate:.2f} tx/day")
        
        logger.debug(f"Enhanced _build_history_from_swaps for {mint}: Returning enhanced result with {len(result)} fields")
        return result

def monkey_patch_data_provider(data_provider):
    """
    Apply monkey patches to enhance data collection.
    """
    logger.info("Applying enhanced data collection patches...")
    
    # Store original method for fallback
    data_provider._original_analyze_token_activity = data_provider._analyze_token_activity
    
    # Replace with enhanced version
    async def patched_analyze_token_activity(mint: str) -> Optional[Dict[str, Any]]:
        try:
            result = await EnhancedDataCollection.enhanced_analyze_token_activity(data_provider, mint)
            if result and len(result.get('ohlcv', [])) > 0:
                logger.info(f"Enhanced analysis successful for {mint}: {len(result.get('ohlcv', []))} OHLCV records")
                return result
            else:
                logger.warning(f"Enhanced analysis failed for {mint}, trying original method")
                return await data_provider._original_analyze_token_activity(mint)
        except Exception as e:
            logger.error(f"Enhanced analysis error for {mint}: {e}, falling back to original")
            return await data_provider._original_analyze_token_activity(mint)
    
    data_provider._analyze_token_activity = patched_analyze_token_activity
    logger.info("Enhanced data collection patches applied successfully")
