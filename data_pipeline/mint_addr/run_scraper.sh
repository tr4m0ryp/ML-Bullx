#!/bin/bash

# Solana Mint Address Scraper Runner
# This script sets up and runs the mint address scraper

set -e  # Exit on any error

echo "Solana Mint Address Scraper"
echo "==============================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is required but not installed."
    exit 1
fi

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "[ERROR] pip3 is required but not installed."
    exit 1
fi

echo "[OK] Python 3 found: $(python3 --version)"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo "Installing dependencies..."
pip install -r requirements.txt

# Check if checkpoint exists
if [ -f "mint_addresses_checkpoint_simple.json" ]; then
    echo "Found checkpoint file. Resuming from previous run..."
else
    echo "Starting fresh scraping process..."
fi

# Run the scraper
echo "Starting mint address scraper..."
echo "Target: 100,000 unique mint addresses"
echo "Age filter: Tokens between 3 months and 1 year old"
echo ""

python3 scrape_mint_simple.py

# Check if successful
if [ $? -eq 0 ]; then
    echo ""
    echo "[OK] Scraping completed successfully!"

    # Show output files
    if [ -f "solana_mint_addresses_3months_to_1year.csv" ]; then
        num_addresses=$(tail -n +2 solana_mint_addresses_3months_to_1year.csv | wc -l)
        echo "Output file: solana_mint_addresses_3months_to_1year.csv"
        echo "Addresses collected: $num_addresses"
        echo "Text file: solana_mint_addresses_3months_to_1year.txt"
    elif [ -f "solana_mint_addresses_3months_old.csv" ]; then
        num_addresses=$(tail -n +2 solana_mint_addresses_3months_old.csv | wc -l)
        echo "Output file: solana_mint_addresses_3months_old.csv"
        echo "Addresses collected: $num_addresses"
        echo "Text file: solana_mint_addresses_3months_old.txt"
    fi

    if [ -f "mint_scraper_simple.log" ]; then
        echo "Log file: mint_scraper_simple.log"
    fi

    echo ""
    echo "All done! You can now use these mint addresses for your ML project."
else
    echo ""
    echo "[ERROR] Scraping failed. Check the logs for details."
    if [ -f "mint_scraper_simple.log" ]; then
        echo "Check log file: mint_scraper_simple.log"
        echo ""
        echo "Last few log entries:"
        tail -10 mint_scraper_simple.log
    fi
fi

# Deactivate virtual environment
deactivate
