# 🏷️ Solana Token Labeling Algorithm

This module implements an automated labeling algorithm for Solana tokens based on the criteria specified in `claude.md`. The algorithm classifies tokens into three categories: **rugpull**, **successful**, and **unsuccessful**.

## 📋 Classification Criteria

### 🚨 Rugpull
A token is labeled as a rugpull if it meets any of the following criteria:
- **Liquidity removal**: >70% liquidity removed within 1 hour
- **Developer dump**: >50% of developer holdings dumped within 24 hours
- **Smart contract risks**: Unlimited minting or liquidity extraction functions

### 🚀 Successful
A token is labeled as successful if it meets ALL of the following criteria:
- **Price appreciation**: >1000% (10x) increase within first 72 hours
- **Sustained volume**: >$100K daily trading volume for at least 7 days
- **Community growth**: >500 unique holders within first week
- **Market presence**: Active trading and engagement

### 📉 Unsuccessful
A token is labeled as unsuccessful if it meets the following criteria:
- **Price stagnation**: Remains within ±50% of launch price after 72 hours
- **Low volume**: <$10K daily average trading volume in first week
- **Low adoption**: <100 unique holders after 7 days
- **Minimal engagement**: Low social media and community activity

## 🏗️ Architecture

```
label/
├── token_labeler.py      # Main labeling algorithm
├── data_fetcher.py       # Real-time data collection from APIs
├── config.py            # Configuration and criteria settings
├── requirements.txt     # Python dependencies
├── run_labeling.sh      # Execution script
└── README.md           # This file
```

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run with Default Settings
```bash
./run_labeling.sh
```

### 3. Run with Custom Parameters
```bash
./run_labeling.sh --input ../mint_addr/my_tokens.csv --output my_labels.csv --sample 1000
```

### 4. Test Mode (100 sample tokens)
```bash
./run_labeling.sh --test
```

## 📊 Input/Output Format

### Input CSV Format
The input CSV must contain at minimum:
```csv
mint_address,collected_at,index
85FCjfVZdnojztL1FvdJzdd5HvoP1bAVogxyYjv9pump,2025-07-29T12:29:48.083669,0
9VYPrJqeDo7gJU7J6tus7cuUM3wkezMzUJ685hpYpump,2025-07-29T12:29:48.083669,1
```

### Output CSV Format
The output CSV will contain:
```csv
mint_address,label,labeled_at,total_tokens
85FCjfVZdnojztL1FvdJzdd5HvoP1bAVogxyYjv9pump,successful,2025-07-29T15:30:00.000000,287871
9VYPrJqeDo7gJU7J6tus7cuUM3wkezMzUJ685hpYpump,rugpull,2025-07-29T15:30:00.000000,287871
```

## 🔧 Command Line Options

```bash
./run_labeling.sh [options]

Options:
  --input FILE       Input CSV file path
  --output FILE      Output CSV file path  
  --sample N         Process only first N tokens (for testing)
  --batch-size N     Batch size for processing (default: 50)
  --install-deps     Install required Python packages
  --test             Run in test mode with 100 sample tokens
  --help             Show help message
```

## 🔌 Data Sources

The algorithm fetches data from multiple sources:

### Blockchain Data
- **Solana RPC**: Token metadata, transaction history, holder counts
- **Jupiter API**: Price data and trading information
- **Raydium API**: Liquidity pool data
- **Orca API**: Additional DEX data

### Market Data
- **DexScreener**: Comprehensive price, volume, and market data
- **CoinGecko**: Backup price feeds and market information

### Social Data (Future Enhancement)
- **Twitter API**: Social media engagement metrics
- **Telegram API**: Community activity data
- **Discord API**: Developer and community interaction

## ⚙️ Configuration

Modify `config.py` to adjust:
- Classification thresholds
- API endpoints and rate limits
- Feature weights
- Confidence thresholds

Example configuration change:
```python
# Make rugpull detection more sensitive
RUGPULL_CRITERIA['liquidity_drop_threshold'] = 0.60  # 60% instead of 70%
```

## 🔬 Development Mode

For development and testing:

### 1. Run with Sample Data
```bash
python token_labeler.py --sample 10 --output test_labels.csv
```

### 2. Test Data Fetcher
```bash
python data_fetcher.py
```

### 3. Modify Classification Logic
Edit the classification methods in `token_labeler.py`:
- `_is_rugpull()`
- `_is_successful()`
- `_is_unsuccessful()`

## 📈 Performance & Scaling

### Current Limitations
- **Rate Limits**: Respects API rate limits (10 requests/second)
- **Sample Processing**: Can process ~50 tokens per batch
- **Mock Data**: Currently uses simulated data for development

### Production Enhancements
- **Parallel Processing**: Multiple worker processes
- **Caching**: Redis for frequently accessed data
- **Real APIs**: Full integration with production APIs
- **Database Storage**: PostgreSQL for historical data

## 🐛 Troubleshooting

### Common Issues

**1. Import Errors**
```bash
# Install missing dependencies
pip install -r requirements.txt
```

**2. API Rate Limiting**
```bash
# Reduce batch size
./run_labeling.sh --batch-size 25
```

**3. No Output File**
```bash
# Check logs for errors
tail -f token_labeling.log
```

**4. Memory Issues with Large Files**
```bash
# Process in smaller samples
./run_labeling.sh --sample 1000
```

### Debug Mode
Enable detailed logging by modifying `config.py`:
```python
LOGGING_CONFIG['level'] = 'DEBUG'
```

## 🔮 Future Enhancements

### Phase 1: Data Enhancement
- [ ] Real-time API integration
- [ ] Social media sentiment analysis
- [ ] Smart contract analysis
- [ ] Historical price pattern analysis

### Phase 2: ML Integration
- [ ] Feature engineering pipeline
- [ ] Machine learning model training
- [ ] Confidence scoring
- [ ] Ensemble methods

### Phase 3: Production Features
- [ ] Real-time streaming
- [ ] Web dashboard
- [ ] API endpoints
- [ ] Monitoring and alerting

## 📝 Example Usage

### Basic Labeling
```bash
# Label all tokens from the main CSV
./run_labeling.sh

# Label with custom input/output
./run_labeling.sh --input my_tokens.csv --output my_labels.csv
```

### Development Testing
```bash
# Quick test with 100 tokens
./run_labeling.sh --test

# Custom sample size
./run_labeling.sh --sample 500 --output test_500.csv
```

### Programmatic Usage
```python
import asyncio
from token_labeler import TokenLabeler

async def label_tokens():
    async with TokenLabeler() as labeler:
        await labeler.label_tokens_from_csv(
            input_csv_path="input.csv",
            output_csv_path="output.csv"
        )

asyncio.run(label_tokens())
```

## 📊 Expected Results

After running the labeling algorithm on your dataset of ~287K tokens, you can expect:

- **Rugpull**: ~5-10% of tokens (high-risk indicators)
- **Successful**: ~1-3% of tokens (exceptional performers)
- **Unsuccessful**: ~87-94% of tokens (majority of tokens)

The actual distribution will depend on:
- Market conditions during the token creation period
- Quality of the dataset
- API data availability
- Classification threshold sensitivity

## 🤝 Contributing

To contribute to the labeling algorithm:

1. **Fork the repository**
2. **Create feature branch**: `git checkout -b feature/enhancement`
3. **Add tests** for new functionality
4. **Update documentation**
5. **Submit pull request**

### Code Style
- Follow PEP 8 for Python code
- Add type hints for all functions
- Include docstrings for public methods
- Add logging for important operations

---

## 📞 Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the logs in `token_labeling.log`
3. Open an issue with detailed error information
4. Include sample data and configuration used

---

**Last Updated**: July 29, 2025  
**Version**: 1.0.0  
**Status**: Development Ready
