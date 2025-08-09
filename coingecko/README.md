# CoinGecko Memecoin Scraper

This directory contains tools for scraping successful memecoins from CoinGecko and filtering them to get only Solana-based memecoins with their mint addresses.

## Features

- Scrapes CoinGecko's successful memecoin category page
- Extracts coin names and identifies Solana-based memecoins
- Retrieves mint addresses (contract addresses) for Solana tokens
- Filters out non-Solana memecoins
- Saves results in CSV format with `mintaddress` and `successful` columns
- Multiple scraping approaches for reliability

## Files

- `api_scraper.py` - **Recommended**: Uses CoinGecko API for reliable data extraction
- `memecoin_scraper.py` - Basic web scraper using requests and BeautifulSoup
- `selenium_scraper.py` - Advanced scraper using Selenium for JavaScript-heavy pages
- `requirements.txt` - Python dependencies
- `run_scraper.py` - Simple runner script with configuration options

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. For Selenium scraper (optional), install ChromeDriver:
```bash
# On Ubuntu/Debian
sudo apt-get install chromium-chromedriver

# Or use webdriver-manager (included in requirements)
```

## Usage

### Quick Start (Recommended)
```bash
python api_scraper.py
```

### With Custom Options
```bash
python run_scraper.py --max-coins 100 --output solana_memecoins.csv
```

### Individual Scrapers
```bash
# API-based (most reliable)
python api_scraper.py

# Basic web scraper
python memecoin_scraper.py

# Selenium-based (for complex pages)
python selenium_scraper.py
```

## Output

The scraper creates two files:

1. `solana_memecoins.csv` - Main output with columns:
   - `mintaddress`: Solana token mint address
   - `successful`: Tag marking these as successful memecoins

2. `detailed_solana_memecoins.csv` - Detailed version with additional info:
   - `name`: Token name
   - `symbol`: Token symbol
   - `coin_id`: CoinGecko coin ID
   - `platform`: Platform (Solana)
   - `contract_address`: Contract address
   - `mintaddress`: Mint address
   - `successful`: Success tag

## Configuration

Key parameters you can adjust:

- `max_coins`: Maximum number of coins to process (default: 50)
- `max_pages`: Maximum pages to scrape (for web scrapers)
- Rate limiting delays between requests
- Output filename

## API Rate Limits

The scraper includes built-in rate limiting to respect CoinGecko's limits:
- 1.5 second delay between API calls
- Exponential backoff on rate limit errors
- Request retry logic

## Known Limitations

1. CoinGecko may not have contract addresses for all tokens
2. Some memecoins might be listed on multiple platforms
3. API rate limits may slow down large-scale scraping
4. Web scraping approaches may break if CoinGecko changes their layout

## Troubleshooting

### Common Issues

1. **Import errors**: Make sure all dependencies are installed
   ```bash
   pip install -r requirements.txt
   ```

2. **Rate limiting**: Increase delays between requests if you get 429 errors

3. **Empty results**: Try the API scraper first, it's most reliable

4. **Selenium issues**: Make sure ChromeDriver is installed and compatible

### Debugging

Check the log files created by each scraper:
- `coingecko_scraper.log` (API scraper)
- `memecoin_scraper.log` (Basic scraper)
- `selenium_scraper.log` (Selenium scraper)

## Example Output

```csv
mintaddress,successful
DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263,successful
EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm,successful
EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v,successful
```

This represents BONK, WIF, and other popular Solana memecoins.

## Future Improvements

- Add support for other blockchain platforms
- Implement database storage
- Add real-time monitoring capabilities
- Include market cap and volume data
- Add data validation and cleanup
