"""
Configuration file for token labeling algorithm
Contains all criteria and thresholds for classification
"""

# Labeling criteria based on claude.md specifications

RUGPULL_CRITERIA = {
    # Liquidity removal criteria
    'liquidity_drop_threshold': 0.70,  # >70% liquidity removal
    'liquidity_timeframe_hours': 1,    # within 1 hour
    
    # Developer dump criteria  
    'dev_dump_threshold': 0.50,        # >50% of holdings dumped
    'dev_dump_timeframe_hours': 24,    # within 24 hours
    
    # Smart contract red flags
    'unlimited_minting': True,          # Check for unlimited mint functions
    'liquidity_extraction': True,       # Check for liquidity extraction functions
    'honeypot_indicators': True         # Check for honeypot patterns
}

SUCCESS_CRITERIA = {
    # Price appreciation criteria
    'price_appreciation_multiplier': 10.0,  # >1000% (10x) increase
    'price_timeframe_hours': 72,            # within first 72 hours
    
    # Volume criteria
    'min_daily_volume': 100000,             # >$100K daily volume
    'volume_sustain_days': 7,               # sustained for at least 7 days
    
    # Community growth criteria
    'min_holders_week1': 500,               # >500 unique holders
    'holder_timeframe_days': 7,             # within first week
    
    # Additional success indicators
    'min_market_cap': 1000000,              # >$1M market cap
    'social_engagement_threshold': 1000     # Social media engagement score
}

UNSUCCESSFUL_CRITERIA = {
    # Price stagnation criteria
    'price_range_threshold': 0.50,     # within ±50% of launch price
    'price_timeframe_hours': 72,       # after 72 hours
    
    # Low volume criteria
    'max_daily_volume': 10000,         # <$10K daily average
    'volume_timeframe_days': 7,        # in first week
    
    # Low adoption criteria
    'max_holders': 100,                # <100 unique holders
    'holder_timeframe_days': 7,        # after 7 days
    
    # Low engagement
    'max_social_engagement': 100       # Minimal social media activity
}

# API Configuration
API_CONFIG = {
    'solana_rpc_endpoints': [
        "https://api.mainnet-beta.solana.com",
        "https://rpc.ankr.com/solana",
        "https://solana-api.projectserum.com"
    ],
    
    'dex_apis': {
        'jupiter': "https://quote-api.jup.ag/v6",
        'raydium': "https://api.raydium.io/v2",
        'orca': "https://api.orca.so/v1"
    },
    
    'rate_limits': {
        'requests_per_second': 10,
        'batch_size': 50,
        'retry_attempts': 3,
        'retry_delay': 1
    }
}

# Data sources for different metrics
DATA_SOURCES = {
    'price_data': ['jupiter', 'raydium', 'orca', 'coingecko'],
    'volume_data': ['jupiter', 'raydium', 'dexscreener'],
    'holder_data': ['solana_rpc', 'solscan'],
    'liquidity_data': ['raydium', 'orca', 'serum'],
    'social_data': ['twitter_api', 'telegram_api', 'discord_api']
}

# Feature weights for classification
FEATURE_WEIGHTS = {
    'price_movement': 0.25,
    'volume_pattern': 0.20,
    'liquidity_stability': 0.25,
    'holder_growth': 0.15,
    'developer_behavior': 0.10,
    'social_engagement': 0.05
}

# Confidence thresholds
CONFIDENCE_THRESHOLDS = {
    'high_confidence': 0.85,
    'medium_confidence': 0.65,
    'low_confidence': 0.45
}

# Logging configuration
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': 'token_labeling.log',
    'max_file_size': '10MB',
    'backup_count': 5
}
