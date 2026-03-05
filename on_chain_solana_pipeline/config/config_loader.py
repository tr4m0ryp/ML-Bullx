"""
Configuration loader for the on-chain Solana pipeline.

- Defines typed dataclasses for database, RPC, program-address, and
  cache configuration sections.
- Loads a YAML configuration file (with sensible defaults when the
  ``pyyaml`` package or the file itself is absent).
- Overlays environment variables (DB_HOST, HELIUS_API_KEY_N, etc.)
  on top of the YAML values so that secrets never need to live in
  version-controlled files.
- Collects multiple Helius API keys from both numbered env vars
  (HELIUS_API_KEY_1 ...) and the single HELIUS_API_KEY var.

Author: ML-Bullx Team
Date:   2025-08-01
"""

# ==============================================================================
# Standard library imports
# ==============================================================================
import os
from typing import Any, Dict, List

# ==============================================================================
# Third-party imports (optional dependencies)
# ==============================================================================
try:
    import yaml
except ImportError:
    yaml = None

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# ==============================================================================
# Standard library imports (continued)
# ==============================================================================
from dataclasses import dataclass


# ==============================================================================
# Configuration dataclasses
# ==============================================================================
@dataclass
class DatabaseConfig:
    """PostgreSQL / TimescaleDB connection parameters."""

    host: str                             # Database hostname or IP
    port: int                             # Database TCP port
    database: str                         # Database name
    user: str                             # Database user
    password: str                         # Database password

    @property
    def dsn(self) -> str:
        """Build a PostgreSQL DSN string from the stored fields.

        Returns:
            A ``postgresql://`` connection URI.
        """
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class RPCConfig:
    """Solana RPC and Helius endpoint configuration.

    Attributes:
        url: Public or private Solana RPC endpoint.
        helius_url: Base URL for the Helius RPC gateway.
        helius_keys: List of Helius API keys for rotation.
    """

    url: str                              # Primary Solana RPC URL
    helius_url: str = ""                  # Helius RPC base URL
    helius_keys: List[str] = None         # Multiple API keys for rotation

    def __post_init__(self):
        """Default ``helius_keys`` to an empty list when not provided."""
        if self.helius_keys is None:
            self.helius_keys = []


@dataclass
class ProgramConfig:
    """Well-known Solana program addresses used by the pipeline."""

    jupiter_v6: str                       # Jupiter v6 aggregator program ID
    raydium_amm: str                      # Raydium AMM program ID
    orca_whirlpools: str                  # Orca Whirlpools program ID
    token_program: str                    # SPL Token program ID


@dataclass
class CacheConfig:
    """TTL values (in seconds) for in-memory caches."""

    price_cache_ttl: int                  # Seconds before a cached price expires
    holder_cache_ttl: int                 # Seconds before a cached holder count expires


@dataclass
class PipelineConfig:
    """Top-level configuration container aggregating all sub-configs.

    Attributes:
        database: Database connection parameters.
        rpc: RPC endpoint and API key settings.
        programs: Well-known program addresses.
        cache: Cache TTL values.
    """

    database: DatabaseConfig
    rpc: RPCConfig
    programs: ProgramConfig
    cache: CacheConfig


# ==============================================================================
# Environment variable helpers
# ==============================================================================
def load_env_variables() -> Dict[str, Any]:
    """Load environment variables, including from a ``.env`` file.

    Scans numbered ``HELIUS_API_KEY_N`` variables as well as a single
    ``HELIUS_API_KEY`` variable.  Placeholder values (those starting
    with ``your_``) are ignored.

    Returns:
        A dict with keys ``helius_keys``, ``db_host``, ``db_port``,
        ``db_name``, ``db_user``, ``db_password``, ``solana_rpc_url``,
        and ``helius_base_url``.
    """
    env_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if load_dotenv is not None:
        load_dotenv(env_file_path, override=False)

    # Collect Helius API keys from numbered env vars
    helius_keys = []
    i = 1
    while True:
        key = os.getenv(f"HELIUS_API_KEY_{i}")
        if not key:
            break
        # Skip placeholder keys
        if not key.startswith("your_") and key != "your_api_key_here":
            helius_keys.append(key)
        i += 1

    # Also check the single-key format
    single_key = os.getenv("HELIUS_API_KEY")
    if single_key and single_key not in helius_keys and not single_key.startswith("your_"):
        helius_keys.append(single_key)

    return {
        "helius_keys": helius_keys,
        "db_host": os.getenv("DB_HOST"),
        "db_port": os.getenv("DB_PORT"),
        "db_name": os.getenv("DB_NAME"),
        "db_user": os.getenv("DB_USER"),
        "db_password": os.getenv("DB_PASSWORD"),
        "solana_rpc_url": os.getenv("SOLANA_RPC_URL"),
        "helius_base_url": os.getenv("HELIUS_BASE_URL")
    }


# ==============================================================================
# Config loader
# ==============================================================================
def load_config(config_path: str = None) -> PipelineConfig:
    """Load pipeline configuration from a YAML file and environment variables.

    The YAML file provides default values.  Environment variables, when
    set, override the corresponding YAML values.  If the YAML file or
    the ``pyyaml`` package is missing, built-in defaults are used.

    Args:
        config_path: Path to the YAML config file.  Defaults to
            ``config/config.yaml`` relative to this module.

    Returns:
        A fully populated ``PipelineConfig`` instance.
    """
    # Load environment variables first
    env_vars = load_env_variables()

    # Default config path
    if config_path is None:
        current_dir = os.path.dirname(__file__)
        config_path = os.path.join(current_dir, "config.yaml")

    # Load YAML config
    if yaml and os.path.exists(config_path):
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
    else:
        # Fallback config if YAML not available or file missing
        data = {
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "solana_pipeline",
                "user": "postgres",
                "password": "password"
            },
            "rpc": {
                "url": "https://api.mainnet-beta.solana.com",
                "helius_url": "https://rpc.helius.xyz"
            },
            "programs": {
                "jupiter_v6": "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
                "raydium_amm": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
                "orca_whirlpools": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
                "token_program": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
            },
            "cache": {
                "price_cache_ttl": 60,
                "holder_cache_ttl": 300
            }
        }

    # Override with environment variables if available
    if env_vars["db_host"]:
        data["database"]["host"] = env_vars["db_host"]
    if env_vars["db_port"]:
        data["database"]["port"] = int(env_vars["db_port"])
    if env_vars["db_name"]:
        data["database"]["database"] = env_vars["db_name"]
    if env_vars["db_user"]:
        data["database"]["user"] = env_vars["db_user"]
    if env_vars["db_password"]:
        data["database"]["password"] = env_vars["db_password"]
    if env_vars["solana_rpc_url"]:
        data["rpc"]["url"] = env_vars["solana_rpc_url"]
    if env_vars["helius_base_url"]:
        data["rpc"]["helius_url"] = env_vars["helius_base_url"]

    # Create RPC config with multiple keys
    rpc_config = RPCConfig(
        url=data["rpc"]["url"],
        helius_url=data["rpc"]["helius_url"],
        helius_keys=env_vars["helius_keys"]
    )

    return PipelineConfig(
        database=DatabaseConfig(**data['database']),
        rpc=rpc_config,
        programs=ProgramConfig(**data['programs']),
        cache=CacheConfig(**data['cache'])
    )
