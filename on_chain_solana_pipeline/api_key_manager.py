"""
API Key Manager for systematic rotation of multiple Helius API keys.
Handles rate limiting, failover, and balanced usage across keys.
"""
import os
import asyncio
import time
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import random

logger = logging.getLogger(__name__)


@dataclass
class APIKeyStats:
    """Statistics for tracking API key usage."""
    key: str
    total_requests: int = 0
    failed_requests: int = 0
    last_used: float = 0.0
    rate_limit_reset_time: float = 0.0
    is_rate_limited: bool = False
    consecutive_failures: int = 0


class HeliusAPIKeyManager:
    """
    Manages multiple Helius API keys with systematic rotation, cooldowns, and global backoff.
    """
    
    def __init__(self, load_from_env: bool = True, rate_limit_cooldown: int = 180, max_consecutive_failures: int = 5):
        self.api_keys: List[str] = []
        self.key_stats: Dict[str, APIKeyStats] = {}
        self.current_key_index: int = 0
        self.rate_limit_cooldown = rate_limit_cooldown
        self.max_consecutive_failures = max_consecutive_failures
        self.global_backoff_until = 0.0
        
        if load_from_env:
            self._load_keys_from_env()
    
    def _load_keys_from_env(self) -> None:
        """Load API keys from environment variables (HELIUS_API_KEY_1, HELIUS_API_KEY_2, etc.)."""
        self.api_keys = []
        self.key_stats = {}
        
        i = 1
        while True:
            key_var = f"HELIUS_API_KEY_{i}"
            key = os.getenv(key_var)
            if not key:
                break
            
            key = key.strip()
            if key and not key.startswith("your_"):
                if key not in self.api_keys:
                    self.api_keys.append(key)
                    self.key_stats[key] = APIKeyStats(key=key)
            i += 1
        
        if not self.api_keys:
            logger.warning("No Helius API keys found in environment variables (e.g., HELIUS_API_KEY_1).")
        else:
            logger.info(f"Loaded {len(self.api_keys)} Helius API keys.")
            # Shuffle keys to ensure different start points on different runs
            random.shuffle(self.api_keys)

    def add_key(self, api_key: str) -> None:
        """Manually add an API key if it's not already present."""
        if api_key not in self.api_keys:
            self.api_keys.append(api_key)
            self.key_stats[api_key] = APIKeyStats(key=api_key)
            logger.info(f"Manually added API key. Total keys: {len(self.api_keys)}")

    def get_next_available_key(self) -> Optional[str]:
        """
        Get the next available (not rate-limited, not failed) API key using round-robin.
        Returns None if all keys are currently unavailable.
        """
        if not self.api_keys:
            return None

        # Check for global backoff first
        current_time = time.time()
        if current_time < self.global_backoff_until:
            logger.warning(f"Global backoff is active. Waiting for {self.global_backoff_until - current_time:.1f}s.")
            return None

        num_keys = len(self.api_keys)
        for _ in range(num_keys):
            key = self.api_keys[self.current_key_index]
            stats = self.key_stats[key]
            
            # Move to the next key for the subsequent call
            self.current_key_index = (self.current_key_index + 1) % num_keys

            if self._is_key_available(stats):
                return key
        
        # If we loop through all keys and none are available, trigger global backoff
        logger.error(f"All {num_keys} API keys are unavailable. Initiating global backoff for {self.rate_limit_cooldown} seconds.")
        self.global_backoff_until = time.time() + self.rate_limit_cooldown
        return None

    def _is_key_available(self, stats: APIKeyStats) -> bool:
        """Check if a specific API key is ready for use."""
        current_time = time.time()
        
        # Check if the key's rate limit cooldown has expired
        if stats.is_rate_limited and current_time < stats.rate_limit_reset_time:
            return False
        elif stats.is_rate_limited:
            # Cooldown has passed, reset the key's status
            logger.info(f"API key {stats.key[:8]}... is now available after cooldown.")
            stats.is_rate_limited = False
            stats.consecutive_failures = 0

        # Check for consecutive failures
        if stats.consecutive_failures >= self.max_consecutive_failures:
            logger.warning(f"API key {stats.key[:8]}... is temporarily disabled due to {stats.consecutive_failures} consecutive failures.")
            # Optionally, put it on a shorter cooldown
            stats.rate_limit_reset_time = current_time + 60  # 1-minute cooldown for failures
            stats.is_rate_limited = True # Mark as rate-limited to enforce cooldown
            return False
            
        return True

    def record_request_success(self, api_key: str) -> None:
        """Record a successful API request."""
        if api_key in self.key_stats:
            stats = self.key_stats[api_key]
            stats.total_requests += 1
            stats.last_used = time.time()
            stats.consecutive_failures = 0 # Reset failure count on success
            logger.debug(f"Request success for key {api_key[:8]}...")

    def record_request_failure(self, api_key: str, is_rate_limit: bool = False) -> None:
        """Record a failed API request and handle cooldowns."""
        if api_key in self.key_stats:
            stats = self.key_stats[api_key]
            stats.failed_requests += 1
            stats.consecutive_failures += 1
            
            if is_rate_limit:
                stats.is_rate_limited = True
                stats.rate_limit_reset_time = time.time() + self.rate_limit_cooldown
                logger.warning(f"API key {api_key[:8]}... hit a rate limit. Cooldown for {self.rate_limit_cooldown}s.")
            else:
                logger.warning(f"Request failed for key {api_key[:8]}... (Consecutive failures: {stats.consecutive_failures})")

    async def wait_for_available_key(self, max_wait_time: float = 300) -> Optional[str]:
        """
        Wait until an API key becomes available, with exponential backoff.
        This is the primary method consumers should use to ensure they get a key.
        """
        start_time = time.time()
        wait_interval = 1.0
        
        while time.time() - start_time < max_wait_time:
            key = self.get_next_available_key()
            if key:
                return key
            
            # If no key is available, it's likely due to global backoff
            current_time = time.time()
            sleep_duration = self.global_backoff_until - current_time
            
            if sleep_duration > 0:
                logger.info(f"Waiting for global backoff: {sleep_duration:.1f}s")
                await asyncio.sleep(sleep_duration)
            else:
                # If not in global backoff, wait with exponential backoff
                logger.info(f"No keys available, waiting {wait_interval:.1f}s...")
                await asyncio.sleep(wait_interval)
                wait_interval = min(wait_interval * 1.5, 30.0) # Cap wait time
        
        logger.error(f"Could not secure an available API key within the {max_wait_time}s timeout.")
        return None

    def get_usage_stats(self) -> Dict[str, Dict[str, any]]:
        """Get usage and health statistics for all API keys."""
        stats_summary = {}
        for key, s in self.key_stats.items():
            masked_key = f"{key[:8]}...{key[-4:]}"
            success_rate = ((s.total_requests - s.failed_requests) / s.total_requests * 100) if s.total_requests > 0 else 100
            stats_summary[masked_key] = {
                "total_requests": s.total_requests,
                "failed_requests": s.failed_requests,
                "consecutive_failures": s.consecutive_failures,
                "is_rate_limited": s.is_rate_limited,
                "cooldown_ends_in_sec": max(0, s.rate_limit_reset_time - time.time()),
                "success_rate": f"{success_rate:.2f}%"
            }
        return stats_summary

# --- Global Instance ---
_global_key_manager: Optional[HeliusAPIKeyManager] = None

def get_key_manager() -> HeliusAPIKeyManager:
    """Access the global instance of the API key manager."""
    global _global_key_manager
    if _global_key_manager is None:
        _global_key_manager = HeliusAPIKeyManager()
    return _global_key_manager

# --- Environment Loading ---
def load_env_if_exists():
    """Load .env file from the script's directory if it exists."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=env_path)
            logger.info(f"Loaded environment variables from {env_path}")
        except ImportError:
            logger.warning("`python-dotenv` not installed. Cannot load .env file.")
        except Exception as e:
            logger.error(f"Error loading .env file: {e}")

# Initialize environment and global manager on import
load_env_if_exists()