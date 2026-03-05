"""
Shared Constants for the ML-Bullx Token Classification Pipeline.

Central registry for time-based constants, external service URLs, and regex
patterns used across all pipeline modules. Add new constants here rather than
scattering magic values across source files.

Author: ML-Bullx Team
Date: 2025-08-01
"""

# =============================================================================
# Time Constants (seconds)
# =============================================================================

ONE_HOUR = 60 * 60                       # 3 600 seconds
THREE_DAYS_SEC = 3 * 24 * 60 * 60       # 259 200 seconds
SUSTAIN_DAYS_SEC = 7 * 24 * 60 * 60     # 604 800 seconds

# =============================================================================
# External Service URLs
# =============================================================================

HELIUS_BASE_URL = "https://rpc.helius.xyz"

# =============================================================================
# Regex Patterns
# =============================================================================

# Base58 Solana address: 32-44 characters, no 0/O/I/l
SOLANA_ADDRESS_PATTERN = r"[1-9A-HJ-NP-Za-km-z]{32,44}"
