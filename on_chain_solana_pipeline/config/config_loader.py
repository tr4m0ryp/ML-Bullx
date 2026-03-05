"""
Configuration loader for the on-chain Solana pipeline.
"""
import os
try:
    import yaml
except ImportError:
    yaml = None
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class DatabaseConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    
    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class RPCConfig:
    url: str
    helius_url: str = ""
    helius_keys: List[str] = None  # Multiple API keys
    
    def __post_init__(self):
        if self.helius_keys is None:
            self.helius_keys = []


@dataclass
class ProgramConfig:
    jupiter_v6: str
    raydium_amm: str
    orca_whirlpools: str
    token_program: str


@dataclass
class CacheConfig:
    price_cache_ttl: int
    holder_cache_ttl: int


@dataclass
class PipelineConfig:
    database: DatabaseConfig
    rpc: RPCConfig
    programs: ProgramConfig
    cache: CacheConfig


def load_env_variables() -> Dict[str, Any]:
    """Load environment variables, including from .env file."""
    env_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if load_dotenv is not None:
        load_dotenv(env_file_path, override=False)

    # Collect Helius API keys
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
    
    # Also check single key format
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


def load_config(config_path: str = None) -> PipelineConfig:
    """Load configuration from YAML file and environment variables."""
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
