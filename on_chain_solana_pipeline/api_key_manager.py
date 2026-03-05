"""
Helius API key manager with rotation, cooldowns, and global backoff.

- Loads multiple Helius API keys from numbered environment variables
  (HELIUS_API_KEY_1, HELIUS_API_KEY_2, ...).
- Implements round-robin key selection with per-key rate-limit tracking.
- Provides a global backoff mechanism when all keys are exhausted.
- Exposes an async ``wait_for_available_key`` helper that blocks until
  a key becomes ready, suitable for use in consumer coroutines.
- Maintains per-key usage statistics (request counts, failure counts,
  cooldown state) accessible via ``get_usage_stats``.

Author: ML-Bullx Team
Date:   2025-08-01
"""

# ==============================================================================
# Standard library imports
# ==============================================================================
import asyncio
import logging
import os
import random
import time
from typing import Dict, List, Optional, Tuple

# ==============================================================================
# Third-party imports
# ==============================================================================
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


# ==============================================================================
# Data structures
# ==============================================================================
@dataclass
class APIKeyStats:
    """Per-key usage and health statistics."""

    key: str                              # The raw API key string
    total_requests: int = 0               # Lifetime request count
    failed_requests: int = 0              # Lifetime failure count
    last_used: float = 0.0                # Unix timestamp of last use
    rate_limit_reset_time: float = 0.0    # When rate-limit cooldown expires
    is_rate_limited: bool = False         # Currently in cooldown
    consecutive_failures: int = 0         # Failures since last success


# ==============================================================================
# Key manager
# ==============================================================================
class HeliusAPIKeyManager:
    """Manages multiple Helius API keys with rotation, cooldowns, and backoff.

    Implements round-robin key selection with per-key rate-limit tracking
    and a global backoff mechanism when all keys are exhausted. Consumers
    should call ``wait_for_available_key`` to block until a key is ready.

    Attributes:
        api_keys: Ordered list of available API key strings.
        rate_limit_cooldown: Seconds to wait after a 429 response.
        max_consecutive_failures: Failure count before disabling a key.
    """

    def __init__(self, load_from_env: bool = True, rate_limit_cooldown: int = 180, max_consecutive_failures: int = 5):
        """Initialise the key manager and optionally load keys from env vars.

        Args:
            load_from_env: If True, scan HELIUS_API_KEY_N env vars on init.
            rate_limit_cooldown: Seconds a key stays in cooldown after a 429.
            max_consecutive_failures: Consecutive failure count that disables
                a key until its cooldown expires.
        """
        self.api_keys: List[str] = []
        self.key_stats: Dict[str, APIKeyStats] = {}
        self.current_key_index: int = 0
        self.rate_limit_cooldown = rate_limit_cooldown
        self.max_consecutive_failures = max_consecutive_failures
        self.global_backoff_until = 0.0

        if load_from_env:
            self._load_keys_from_env()

    # ------------------------------------------------------------------
    # Key loading
    # ------------------------------------------------------------------
    def _load_keys_from_env(self) -> None:
        """Load API keys from numbered environment variables.

        Scans HELIUS_API_KEY_1, HELIUS_API_KEY_2, ... until a gap is found.
        Placeholder values (those starting with ``your_``) are skipped.
        Keys are shuffled after loading so that different process restarts
        begin with different starting keys.
        """
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
        """Manually register an API key if it is not already present.

        Args:
            api_key: The raw Helius API key string to add.
        """
        if api_key not in self.api_keys:
            self.api_keys.append(api_key)
            self.key_stats[api_key] = APIKeyStats(key=api_key)
            logger.info(f"Manually added API key. Total keys: {len(self.api_keys)}")

    # ------------------------------------------------------------------
    # Key selection
    # ------------------------------------------------------------------
    def get_next_available_key(self) -> Optional[str]:
        """Return the next available key using round-robin selection.

        Skips keys that are rate-limited or have exceeded the consecutive
        failure threshold.  If every key is unavailable, a global backoff
        is triggered and ``None`` is returned.

        Returns:
            An API key string, or None when no key is available.
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
        """Check whether the given key is ready for use.

        Handles cooldown expiry reset and consecutive-failure disabling.

        Args:
            stats: The ``APIKeyStats`` record for the key to check.

        Returns:
            True if the key can be used for a request right now.
        """
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
            # Put it on a shorter cooldown for failure-based disabling
            stats.rate_limit_reset_time = current_time + 60  # 1-minute cooldown for failures
            stats.is_rate_limited = True
            return False

        return True

    # ------------------------------------------------------------------
    # Request tracking
    # ------------------------------------------------------------------
    def record_request_success(self, api_key: str) -> None:
        """Record a successful API request and reset the failure counter.

        Args:
            api_key: The key that was used for the successful request.
        """
        if api_key in self.key_stats:
            stats = self.key_stats[api_key]
            stats.total_requests += 1
            stats.last_used = time.time()
            stats.consecutive_failures = 0
            logger.debug(f"Request success for key {api_key[:8]}...")

    def record_request_failure(self, api_key: str, is_rate_limit: bool = False) -> None:
        """Record a failed API request and optionally trigger rate-limit cooldown.

        Args:
            api_key: The key that was used for the failed request.
            is_rate_limit: If True the failure was a 429 rate-limit response,
                which triggers the full cooldown period for this key.
        """
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

    # ------------------------------------------------------------------
    # Async wait helper
    # ------------------------------------------------------------------
    async def wait_for_available_key(self, max_wait_time: float = 300) -> Optional[str]:
        """Block until an API key becomes available, using exponential backoff.

        This is the primary method consumers should use to obtain a key.
        It respects the global backoff timer and increases its own sleep
        interval between polls up to a 30-second cap.

        Args:
            max_wait_time: Maximum seconds to wait before giving up.

        Returns:
            An API key string, or None if no key became available within
            the timeout.
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
                wait_interval = min(wait_interval * 1.5, 30.0)

        logger.error(f"Could not secure an available API key within the {max_wait_time}s timeout.")
        return None

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def get_usage_stats(self) -> Dict[str, Dict[str, any]]:
        """Return a summary of usage and health statistics for every key.

        Returns:
            A dict keyed by masked key strings, each containing request
            counts, failure counts, cooldown state, and success rate.
        """
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


# ==============================================================================
# Global singleton
# ==============================================================================
_global_key_manager: Optional[HeliusAPIKeyManager] = None


def get_key_manager() -> HeliusAPIKeyManager:
    """Access the process-wide singleton ``HeliusAPIKeyManager``.

    The instance is lazily created on first call.

    Returns:
        The shared ``HeliusAPIKeyManager`` instance.
    """
    global _global_key_manager
    if _global_key_manager is None:
        _global_key_manager = HeliusAPIKeyManager()
    return _global_key_manager


# ==============================================================================
# Environment bootstrap
# ==============================================================================
def load_env_if_exists():
    """Load a ``.env`` file from the package directory if one exists.

    Requires the ``python-dotenv`` package.  If the package is not
    installed a warning is logged and execution continues.
    """
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
