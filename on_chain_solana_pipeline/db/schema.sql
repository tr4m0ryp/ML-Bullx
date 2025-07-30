-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Table for raw swap ticks
CREATE TABLE IF NOT EXISTS swap_ticks (
    id SERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    mint TEXT NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    volume_usd DOUBLE PRECISION NOT NULL,
    source TEXT NOT NULL, -- 'jupiter', 'raydium', 'orca', etc
    tx_signature TEXT,
    INDEX (ts DESC, mint)
);

-- Convert to hypertable for time-series optimization
SELECT create_hypertable('swap_ticks', 'ts', if_not_exists => TRUE);

-- Table for token metadata
CREATE TABLE IF NOT EXISTS token_metadata (
    mint TEXT PRIMARY KEY,
    name TEXT,
    symbol TEXT,
    decimals INTEGER,
    supply BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table for holder snapshots
CREATE TABLE IF NOT EXISTS holder_snapshots (
    mint TEXT,
    snapshot_time TIMESTAMPTZ,
    holder_count INTEGER,
    PRIMARY KEY (mint, snapshot_time)
);

-- Convert to hypertable
SELECT create_hypertable('holder_snapshots', 'snapshot_time', if_not_exists => TRUE);

-- Table for liquidity snapshots
CREATE TABLE IF NOT EXISTS liquidity_snapshots (
    mint TEXT,
    snapshot_time TIMESTAMPTZ,
    total_liquidity_usd DOUBLE PRECISION,
    source TEXT,
    PRIMARY KEY (mint, snapshot_time, source)
);

SELECT create_hypertable('liquidity_snapshots', 'snapshot_time', if_not_exists => TRUE);

-- Indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_swap_ticks_mint_ts ON swap_ticks (mint, ts DESC);
CREATE INDEX IF NOT EXISTS idx_holder_snapshots_mint ON holder_snapshots (mint, snapshot_time DESC);
CREATE INDEX IF NOT EXISTS idx_liquidity_snapshots_mint ON liquidity_snapshots (mint, snapshot_time DESC);
