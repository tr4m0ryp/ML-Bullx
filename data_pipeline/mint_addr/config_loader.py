#!/usr/bin/env python3
"""
Configuration loader for the Solana mint address scraper.
"""

import yaml
import os
from datetime import datetime, timedelta
from typing import Dict, Any

def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        Configuration dictionary
    """
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config
        else:
            # Return default configuration if file doesn't exist
            return get_default_config()
    except Exception as e:
        print(f"Error loading config: {e}")
        return get_default_config()

def get_default_config() -> Dict[str, Any]:
    """Get default configuration."""
    return {
        'target_mint_count': 100000,
        'min_months_ago': 3,
        'max_months_ago': 12,
        'batch_size': 1000,
        'rpc_endpoints': [
            "https://api.mainnet-beta.solana.com",
            "https://solana-api.projectserum.com",
            "https://api.solana.fm"
        ],
        'api_sources': {
            'dexscreener': {
                'url': "https://api.dexscreener.com/latest/dex/tokens/solana",
                'enabled': True
            },
            'jupiter': {
                'url': "https://token.jup.ag/all",
                'enabled': True
            }
        },
        'rate_limits': {
            'rpc_requests_per_second': 10,
            'api_requests_per_second': 5,
            'batch_delay_seconds': 1
        },
        'output': {
            'csv_filename': "solana_mint_addresses_3months_to_1year.csv",
            'txt_filename': "solana_mint_addresses_3months_to_1year.txt",
            'checkpoint_filename': "mint_addresses_checkpoint.json",
            'log_filename': "mint_scraper.log"
        },
        'logging': {
            'level': 'INFO',
            'format': '%(asctime)s - %(levelname)s - %(message)s'
        }
    }

def get_age_cutoffs(config: Dict[str, Any]) -> tuple:
    """
    Calculate age cutoff dates from configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Tuple of (min_cutoff_date, max_cutoff_date)
    """
    min_months = config.get('min_months_ago', 3)
    max_months = config.get('max_months_ago', 12)
    
    min_cutoff_date = datetime.now() - timedelta(days=max_months * 30)  # Oldest allowed
    max_cutoff_date = datetime.now() - timedelta(days=min_months * 30)  # Newest allowed
    
    return min_cutoff_date, max_cutoff_date

if __name__ == "__main__":
    # Test the configuration loader
    config = load_config()
    min_date, max_date = get_age_cutoffs(config)
    
    print("Configuration loaded successfully!")
    print(f"Target count: {config['target_mint_count']}")
    print(f"Age range: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}")
    print(f"RPC endpoints: {len(config['rpc_endpoints'])}")
