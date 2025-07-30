-- TimescaleDB continuous aggregate for 5m OHLCV
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_5m
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('5 minutes', ts) AS bucket,
  mint,
  first(price, ts) AS open,
  max(price) AS high,
  min(price) AS low,
  last(price, ts) AS close,
  sum(volume_usd) AS volume_usd,
  count(*) AS trade_count
FROM swap_ticks
GROUP BY bucket, mint
WITH NO DATA;

-- Refresh policy to keep the view updated
SELECT add_continuous_aggregate_policy('ohlcv_5m',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE);

-- 1-hour OHLCV view
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_1h
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 hour', ts) AS bucket,
  mint,
  first(price, ts) AS open,
  max(price) AS high,
  min(price) AS low,
  last(price, ts) AS close,
  sum(volume_usd) AS volume_usd,
  count(*) AS trade_count
FROM swap_ticks
GROUP BY bucket, mint
WITH NO DATA;

SELECT add_continuous_aggregate_policy('ohlcv_1h',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);

-- Daily OHLCV view
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_1d
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 day', ts) AS bucket,
  mint,
  first(price, ts) AS open,
  max(price) AS high,
  min(price) AS low,
  last(price, ts) AS close,
  sum(volume_usd) AS volume_usd,
  count(*) AS trade_count
FROM swap_ticks
GROUP BY bucket, mint
WITH NO DATA;

SELECT add_continuous_aggregate_policy('ohlcv_1d',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 day', 
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);
