# Solana Mint Address Scraper

This directory contains scripts to scrape mint addresses of Solana tokens that are between 3 months and 1 year old. The goal is to collect 100,000 unique mint addresses for training data.

## Age Requirements

- **Minimum Age:** 3 months old (ensures sufficient data for classification)
- **Maximum Age:** 1 year old (ensures relevance to current market conditions)
- **Target Range:** Tokens created between 3 months and 1 year ago

## Files

- `scrape_mint_addresses.py` - Advanced scraper using direct blockchain access
- `scrape_mint_simple.py` - Simplified scraper using API endpoints (recommended)
- `requirements.txt` - Python dependencies
- `config.yaml` - Configuration file
- `README.md` - This file

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Simple Scraper (Recommended)

```bash
python scrape_mint_simple.py
```

This script uses multiple API sources and is more reliable:
- Jupiter Token List
- CoinGecko API
- Solscan API  
- DexScreener API

### 3. Alternative: Advanced Scraper

```bash
python scrape_mint_addresses.py
```

This script directly queries the Solana blockchain but requires RPC access and is more complex.

## Output Files

After running, you'll get:
- `solana_mint_addresses_3months_old.csv` - Main output with mint addresses
- `solana_mint_addresses_3months_old.txt` - Simple text file with addresses
- `mint_addresses_checkpoint_simple.json` - Progress checkpoint
- `mint_scraper_simple.log` - Execution logs

## Auto-Save Feature

The scraper automatically saves progress to prevent data loss:

- **Save Interval**: Every 1000 addresses collected
- **Checkpoint File**: `mint_addresses_checkpoint_simple.json`
- **CSV Export**: Updated after each save interval
- **Resume Capability**: Automatically resumes from last checkpoint

### Files Created During Scraping:
- `mint_addresses_checkpoint_simple.json` - Progress checkpoint
- `solana_mint_addresses_3months_to_1year.csv` - Incremental CSV export
- `solana_mint_addresses_3months_to_1year.txt` - Incremental text export
- `mint_scraper_simple.log` - Execution logs

## Configuration

You can modify `config.yaml` to:
- Change target number of addresses
- Add more RPC endpoints
- Adjust rate limiting
- Configure output files

## Data Sources

### Simple Scraper (API-based):
1. **Jupiter** - Token aggregator with comprehensive token list
2. **CoinGecko** - Market data with Solana ecosystem tokens
3. **Solscan** - Solana blockchain explorer API
4. **DexScreener** - DEX aggregator with trading pairs

### Advanced Scraper (Blockchain-based):
1. **Solana RPC** - Direct blockchain queries
2. **Token Program** - Token creation transactions
3. **DexScreener API** - Supplemental data
4. **Jupiter API** - Additional token addresses

## Features

- **Age Filtering**: Only collects tokens between 3 months and 1 year old
- **Deduplication**: Ensures all addresses are unique
- **Auto-Save**: Automatically saves progress every 1000 addresses collected
- **Progress Saving**: Checkpoint system to resume interrupted runs
- **Rate Limiting**: Respects API limits to avoid blocking
- **Multiple Sources**: Combines data from various reliable sources
- **Error Handling**: Robust error handling and logging
- **Export Options**: CSV and TXT output formats

## Expected Results

The scraper should collect:
- 100,000 unique mint addresses
- Tokens created between 3 months and 1 year ago
- Mix of successful, failed, and rug-pulled tokens
- Comprehensive coverage of Solana ecosystem
- Optimal age range for classification training

## Rate Limits

The scripts implement rate limiting to respect API limits:
- Solana RPC: 10 requests/second
- Public APIs: 1-5 requests/second
- Batch delays between operations

## Troubleshooting

### Common Issues:

1. **Rate Limited**: 
   - Increase delays in the script
   - Use multiple RPC endpoints
   - Run during off-peak hours

2. **Incomplete Results**:
   - Check the checkpoint file
   - Resume from checkpoint
   - Combine multiple runs

3. **API Errors**:
   - Check internet connection
   - Verify API endpoints are working
   - Check logs for specific errors

### Performance Tips:

1. **Use Simple Scraper**: More reliable than blockchain scraper
2. **Add RPC Endpoints**: Better performance with multiple endpoints
3. **Run in Batches**: Can stop and resume anytime
4. **Monitor Logs**: Check progress and catch issues early
5. **Auto-Save Feature**: Data is automatically saved every 1000 addresses
6. **Resume from Checkpoint**: Restart from where you left off if interrupted

## Data Quality

The collected addresses will include:
- Various token types (memecoins, DeFi tokens, etc.)
- Different market caps and volumes
- Tokens from different time periods (3+ months old)
- Mix of active and inactive tokens

## Next Steps

After collecting mint addresses:
1. Use addresses to collect training data (price, volume, metadata)
2. Label tokens based on success criteria
3. Extract features for ML model training
4. Build classification model

## License

This scraper is for educational and research purposes. Please respect API terms of service and rate limits.
