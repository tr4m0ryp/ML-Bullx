#!/bin/bash
# Setup script for on-chain Solana pipeline

echo "Setting up on-chain Solana pipeline..."

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Database setup (assumes PostgreSQL with TimescaleDB is already installed)
echo "Setting up database schema..."
echo "Please ensure PostgreSQL with TimescaleDB extension is running."
echo "Create database: CREATE DATABASE solana_pipeline;"
echo "Then run the SQL files:"
echo "  psql -d solana_pipeline -f db/schema.sql"
echo "  psql -d solana_pipeline -f db/timescale_ohlcv_view.sql"

# Configuration
echo "Configuration setup:"
echo "1. Copy config/config.yaml and update with your settings"
echo "2. Set database connection details"
echo "3. Add RPC endpoint (Helius recommended for best results)"
echo "4. Configure program IDs if needed"

echo "Setup complete! See README.md for usage instructions."
