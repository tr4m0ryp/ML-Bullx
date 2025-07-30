"""
API Key Manager for systematic rotation of multiple Helius API keys.
Handles rate limiting, failover, and balanced usage across keys.
"""
import os
import asyncio
import time
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import random

logger = logging.getLogger(__name__)


@dataclass
class APIKeyStats:
    """Statistics for tracking API key usage."""
    key: str
    total_requests: int = 0
    failed_requests: int = 0
    last_used: float = 0
    rate_limit_reset: float = 0
    is_rate_limited: bool = False
    consecutive_failures: int = 0


class HeliusAPIKeyManager:
    """
    Manages multiple Helius API keys with systematic rotation and rate limiting.
    
    Features:
    - Round-robin key rotation
    - Rate limit detection and backoff
    - Automatic failover on key exhaustion
    - Usage statistics and health monitoring
    """
    
    def __init__(self, load_from_env: bool = True):
        self.api_keys: List[str] = []
        self.key_stats: Dict[str, APIKeyStats] = {}
        self.current_key_index: int = 0  # Will be adjusted after loading keys
        self.requests_per_key_per_second = 0.3  # Reduced to 0.3 (3.3 seconds between requests)
        self.max_consecutive_failures = 3
        self.rate_limit_cooldown = 180  # Increased to 180 seconds (3 minutes)
        self.global_backoff = 0  # Global backoff timer
        
        if load_from_env:
            self._load_keys_from_env()
    
    def _load_keys_from_env(self) -> None:
        """Load API keys from environment variables."""
        # Load keys from .env file pattern
        i = 1
        while True:
            key_var = f"HELIUS_API_KEY_{i}"
            key = os.getenv(key_var)
            if not key:
                break
            # Skip placeholder keys and clean up values
            key = key.split(' ---')[0].strip()  # Remove "--- IGNORE" comments
            if not key.startswith("your_") and key != "your_api_key_here":
                self.api_keys.append(key)
                self.key_stats[key] = APIKeyStats(key=key)
            i += 1
        
        # Also check for single key format
        single_key = os.getenv("HELIUS_API_KEY")
        if single_key and single_key not in self.api_keys and not single_key.startswith("your_"):
            single_key = single_key.split(' ---')[0].strip()
            self.api_keys.append(single_key)
            self.key_stats[single_key] = APIKeyStats(key=single_key)
        
        if not self.api_keys:
            logger.warning("No Helius API keys found in environment variables")
        else:
            logger.info(f"Loaded {len(self.api_keys)} Helius API keys")
            # Adjust starting index to use api_2 if available
            if len(self.api_keys) >= 2:
                self.current_key_index = 1  # Start with the second key (api_2)
            else:
                self.current_key_index = 0  # Fall back to first key if only one available
    
    def add_key(self, api_key: str) -> None:
        """Manually add an API key."""
        if api_key not in self.api_keys:
            self.api_keys.append(api_key)
            self.key_stats[api_key] = APIKeyStats(key=api_key)
    
    def get_next_available_key(self) -> Optional[str]:
        """
        Get the next available API key using round-robin with health checks.
        Returns None if all keys are rate limited or failed.
        """
        if not self.api_keys:
            return None
        
        current_time = time.time()
        
        # Check global backoff
        if current_time < self.global_backoff:
            logger.debug(f"Global backoff active for {self.global_backoff - current_time:.1f} seconds")
            return None
        
        attempts = 0
        
        # Try each key in rotation
        while attempts < len(self.api_keys):
            key = self.api_keys[self.current_key_index]
            stats = self.key_stats[key]
            
            # Check if key is healthy and not rate limited
            if self._is_key_available(stats, current_time):
                # Move to next key for next request (round-robin)
                self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
                return key
            
            # Try next key
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            attempts += 1
        
        # All keys are unavailable - set global backoff with increasing duration
        current_backoff_time = self.global_backoff - current_time if current_time < self.global_backoff else 0
        new_backoff = max(30, current_backoff_time * 1.5) if current_backoff_time > 0 else 30
        new_backoff = min(new_backoff, 300)  # Cap at 5 minutes
        
        self.global_backoff = current_time + new_backoff
        logger.warning(f"All API keys are currently unavailable - setting {new_backoff:.0f}s global backoff")
        return None
    
    def _is_key_available(self, stats: APIKeyStats, current_time: float) -> bool:
        """Check if an API key is available for use."""
        # Check if rate limit cooldown has expired
        if stats.is_rate_limited and current_time > stats.rate_limit_reset:
            stats.is_rate_limited = False
            stats.consecutive_failures = 0
            logger.info(f"API key rate limit reset: {stats.key[:8]}...")
        
        # Check if key is currently rate limited
        if stats.is_rate_limited:
            return False
        
        # Check if key has too many consecutive failures
        if stats.consecutive_failures >= self.max_consecutive_failures:
            return False
        
        # Check rate limiting (simple time-based)
        time_since_last_use = current_time - stats.last_used
        if time_since_last_use < (1.0 / self.requests_per_key_per_second):
            return False
        
        return True
    
    def record_request_success(self, api_key: str) -> None:
        """Record a successful request for the given API key."""
        if api_key in self.key_stats:
            stats = self.key_stats[api_key]
            stats.total_requests += 1
            stats.last_used = time.time()
            stats.consecutive_failures = 0
            logger.debug(f"Request success for key {api_key[:8]}... (total: {stats.total_requests})")
    
    def record_request_failure(self, api_key: str, is_rate_limit: bool = False) -> None:
        """Record a failed request for the given API key."""
        if api_key in self.key_stats:
            stats = self.key_stats[api_key]
            stats.failed_requests += 1
            stats.consecutive_failures += 1
            
            if is_rate_limit:
                stats.is_rate_limited = True
                stats.rate_limit_reset = time.time() + self.rate_limit_cooldown
                logger.warning(f"API key rate limited: {api_key[:8]}... (cooldown: {self.rate_limit_cooldown}s)")
            else:
                logger.warning(f"Request failed for key {api_key[:8]}... (consecutive failures: {stats.consecutive_failures})")
    
    async def wait_for_available_key(self, max_wait_time: float = 300) -> Optional[str]:
        """
        Wait for an available API key, with exponential backoff.
        Returns None if no key becomes available within max_wait_time.
        """
        start_time = time.time()
        wait_time = 1.0  # Start with 1 second
        
        while time.time() - start_time < max_wait_time:
            key = self.get_next_available_key()
            if key:
                return key
            
            logger.info(f"No API keys available, waiting {wait_time:.1f}s...")
            await asyncio.sleep(wait_time)
            
            # Exponential backoff, cap at 30 seconds
            wait_time = min(wait_time * 1.5, 30.0)
        
        logger.error(f"No API keys became available within {max_wait_time}s")
        return None
    
    def get_usage_stats(self) -> Dict[str, Dict[str, any]]:
        """Get usage statistics for all API keys."""
        stats = {}
        for key, key_stats in self.key_stats.items():
            masked_key = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else f"{key[:4]}..."
            stats[masked_key] = {
                "total_requests": key_stats.total_requests,
                "failed_requests": key_stats.failed_requests,
                "consecutive_failures": key_stats.consecutive_failures,
                "is_rate_limited": key_stats.is_rate_limited,
                "success_rate": (
                    (key_stats.total_requests - key_stats.failed_requests) / key_stats.total_requests * 100
                    if key_stats.total_requests > 0 else 0
                )
            }
        return stats
    
    def get_healthy_key_count(self) -> int:
        """Get the number of currently healthy (available) API keys."""
        current_time = time.time()
        healthy_count = 0
        
        for stats in self.key_stats.values():
            if self._is_key_available(stats, current_time):
                healthy_count += 1
        
        return healthy_count
    
    def reset_key_failures(self, api_key: str) -> None:
        """Reset failure count for a specific key (manual recovery)."""
        if api_key in self.key_stats:
            stats = self.key_stats[api_key]
            stats.consecutive_failures = 0
            stats.is_rate_limited = False
            logger.info(f"Reset failures for API key: {api_key[:8]}...")


# Global instance for easy access
_global_key_manager: Optional[HeliusAPIKeyManager] = None


def get_key_manager() -> HeliusAPIKeyManager:
    """Get the global API key manager instance."""
    global _global_key_manager
    if _global_key_manager is None:
        _global_key_manager = HeliusAPIKeyManager()
    return _global_key_manager


def load_env_file(env_path: str = ".env") -> None:
    """Load environment variables from .env file."""
    try:
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Remove quotes if present
                    value = value.strip('\'"')
                    os.environ[key] = value
        logger.info(f"Loaded environment variables from {env_path}")
    except FileNotFoundError:
        logger.warning(f"Environment file {env_path} not found")
    except Exception as e:
        logger.error(f"Error loading environment file {env_path}: {e}")


# Initialize environment on import
env_file_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_file_path):
    load_env_file(env_file_path)
