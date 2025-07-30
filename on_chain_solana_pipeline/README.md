# On-Chain Solana Data Pipeline

This module provides a fully on-chain data pipeline for Solana token analytics, replacing external API dependencies like Birdeye and DexScreener with direct blockchain data access.

## Features

- **Real-time swap ingestion** from Jupiter, Raydium, Orca, and other AMMs
- **Price/tick extraction** and OHLCV aggregation using TimescaleDB
- **Holder count snapshots** via direct RPC queries  
- **Token labeling** using the same success/rug detection logic as the original labeler
- **Caching and optimization** to minimize RPC calls

## Architecture

```
Solana Blockchain → Helius/RPC → Swap Parser → TimescaleDB → Token Labeler
```

## Quick Start

### 1. Prerequisites

- PostgreSQL with TimescaleDB extension
- Python 3.8+ with dependencies from `requirements.txt`
- Solana RPC access (Helius recommended)

### 2. Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Setup database
createdb solana_pipeline
psql -d solana_pipeline -f db/schema.sql
psql -d solana_pipeline -f db/timescale_ohlcv_view.sql

# Configure
cp config/config.yaml config/my_config.yaml
# Edit my_config.yaml with your database and RPC settings
```

### 3. Run Components

```bash
# Start swap data ingestion (background process)
python helius_consumer.py --config config/my_config.yaml

# Run holder snapshots (periodic job)
python jobs/holder_snapshot.py --config config/my_config.yaml --from-db

# Label tokens using on-chain data
python onchain_token_labeler.py --input tokens.csv --output labeled_tokens.csv --config config/my_config.yaml
```

## Components

- **`onchain_provider.py`**: Core data provider replacing external APIs
- **`onchain_token_labeler.py`**: Token labeler using on-chain data  
- **`helius_consumer.py`**: Real-time swap data ingestion
- **`swap_parser.py`**: Parse AMM transactions into price ticks
- **`jobs/holder_snapshot.py`**: Periodic holder count updates
- **`config/`**: Configuration management

## Migration from External APIs

The `onchain_token_labeler.py` is a drop-in replacement for your existing token labeler that:

1. **Replaces Birdeye price API** → Direct swap tick queries from TimescaleDB
2. **Replaces DexScreener charts** → OHLCV views from our continuous aggregates
3. **Replaces SolScan holders** → Direct RPC queries with caching

Same classification logic, same CLI interface, but fully on-chain data sources.

## Configuration

### Environment Variables (.env file)

Create a `.env` file in the pipeline directory with your API keys:

```bash
# Multiple Helius API Keys (for rate limit distribution)
HELIUS_API_KEY_1=your_first_helius_api_key
HELIUS_API_KEY_2=your_second_helius_api_key  
HELIUS_API_KEY_3=your_third_helius_api_key
HELIUS_API_KEY_4=your_fourth_helius_api_key
HELIUS_API_KEY_5=your_fifth_helius_api_key

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=solana_pipeline
DB_USER=postgres
DB_PASSWORD=password

# RPC Configuration  
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
HELIUS_BASE_URL=https://rpc.helius.xyz
```

### YAML Configuration (config.yaml)

The system automatically loads API keys from `.env` and merges with `config.yaml`:

```yaml
database:
  host: "localhost"  # Can be overridden by DB_HOST
  database: "solana_pipeline"  # Can be overridden by DB_NAME
  # ... other settings

rpc:
  url: "https://api.mainnet-beta.solana.com"
  helius_url: "https://rpc.helius.xyz"
  # helius_keys loaded automatically from .env
```

## API Key Management

The system includes intelligent API key rotation with:

- **Round-robin distribution** across all configured keys
- **Automatic rate limit detection** and key failover  
- **Health monitoring** and failure tracking
- **Exponential backoff** when all keys are rate limited
- **Usage statistics** for monitoring key performance

### Testing Your API Keys

```bash
# Test API key rotation and configuration
python test_api_keys.py
```

This will show:
- How many keys were loaded
- Key rotation in action
- Rate limit handling simulation
- Usage statistics per key

## Performance Notes

- **RPC rate limits**: Uses caching and batching to minimize calls
- **Database optimization**: TimescaleDB handles time-series data efficiently  
- **Batch processing**: Default batch size of 20 tokens (adjustable)
- **Background ingestion**: Swap data collected continuously in background

## Data Flow

1. **Ingestion**: `helius_consumer.py` monitors blockchain for swaps
2. **Processing**: `swap_parser.py` extracts price/volume from transactions
3. **Storage**: Raw ticks → TimescaleDB → Continuous aggregates (OHLCV)
4. **Analysis**: `onchain_token_labeler.py` queries local data for classification

## Next Steps

1. Set up the database and run `setup.sh`
2. Configure your RPC endpoints in `config.yaml`
3. Start the swap ingestion process
4. Run periodic holder snapshots
5. Replace your existing labeler with `onchain_token_labeler.py`

This gives you complete control over your data pipeline with no external dependencies or rate limits!
