# 🏷️ Solana Token Labeling Pipeline

This module provides an automated token classification system for Solana tokens. It analyzes on-chain data to classify tokens into four categories: **successful**, **unsuccessful**, **rugpull**, and **inactive**.

## � Quick Start

### Prerequisites
```bash
# Install dependencies
pip install -r requirements.txt

# Ensure on_chain_solana_pipeline is properly configured
```

### Basic Usage
```bash
# Label tokens from a CSV file
python run_incremental_labeling.py input_tokens.csv output_labeled.csv

# With custom batch size
python run_incremental_labeling.py input_tokens.csv output_labeled.csv --batch-size 20

# Resume interrupted processing (automatically skips completed tokens)
python run_incremental_labeling.py input_tokens.csv output_labeled.csv
```

## 📁 File Structure

```
data_pipeline/label/
├── run_incremental_labeling.py    # Main entry point - use this!
├── token_labeler.py               # Core labeling logic
├── config.py                      # Configuration settings
├── requirements.txt               # Python dependencies
├── README.md                      # This file
└── solana_tokens_labeled.csv      # Example output
```

## 📊 Classification Categories

### 🎯 **SUCCESSFUL**
- Sustained growth and community adoption
- 10x+ appreciation with 100+ holders
- Strong recovery patterns after early drops

### 📉 **UNSUCCESSFUL** 
- Limited growth, doesn't meet success criteria
- Moderate performance without clear rugpull indicators

### 🚨 **RUGPULL**
- Coordinated dumps or malicious patterns
- Multiple rapid drops without recovery
- Clear abandonment patterns

### 💤 **INACTIVE**
- Never gained meaningful traction
- Very low appreciation (<10x) AND few holders (<20)
- Dead volume (<$10)

## 🔧 Input/Output Format

### Input CSV Format
```csv
mint_address
DxuZtRqzVonQ6yFqv5fpDAUQS4pXvBxjR6x9CEvCukVd
5fr1bB2Tz6ywjoFc9K1VoX3ukGHP6xPUD5bFU4nX1Zs9
```

### Output CSV Format
```csv
mint_address,label
DxuZtRqzVonQ6yFqv5fpDAUQS4pXvBxjR6x9CEvCukVd,unsuccessful
5fr1bB2Tz6ywjoFc9K1VoX3ukGHP6xPUD5bFU4nX1Zs9,successful
```

## 🛠️ Features

- **Incremental Processing**: Resume from where you left off
- **Robust Data Fetching**: Multiple API fallbacks
- **Real-time Progress**: Detailed logging and progress tracking
- **Error Handling**: Graceful handling of API failures
- **Batch Processing**: Configurable batch sizes for optimal performance

## 📝 Logs

Processing logs are saved to `incremental_labeling.log` with detailed information about:
- Token processing progress
- API response details
- Classification decisions
- Error diagnostics

## 🔍 Algorithm Details

The algorithm analyzes:
- Historical price data from transactions
- Volume patterns and trading activity
- Holder count and distribution
- Time-based recovery patterns
- Drop frequency and severity

For detailed algorithm information, see the docstring in `token_labeler.py`.

## 🚨 Troubleshooting

### Common Issues

1. **Import Errors**: Ensure the `on_chain_solana_pipeline` is in the correct path
2. **API Rate Limits**: Reduce batch size if encountering rate limits
3. **Database Connection**: Check database configuration in config files

### Getting Help

Check the log files for detailed error information:
```bash
tail -f incremental_labeling.log
```
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
