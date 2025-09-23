-- Table: trades
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(16) NOT NULL,
    direction VARCHAR(8) NOT NULL, -- 'long' or 'short'
    entry_time TIMESTAMP NOT NULL,
    entry_price NUMERIC(12,4) NOT NULL,
    entry_vwap NUMERIC(12,4),
    shares INTEGER NOT NULL,
    risk NUMERIC(12,4) NOT NULL, -- $ risked on the trade
    exit_time TIMESTAMP,
    exit_price NUMERIC(12,4),
    exit_reason VARCHAR(16), -- 'target', 'stop', 'manual', etc.
    realized_pnl NUMERIC(14,4),
    commission NUMERIC(10,4),
    max_favorable NUMERIC(14,4),
    max_adverse NUMERIC(14,4),
    partials JSONB, -- e.g. [{"qty": 30, "price": 101.2, "time": "...", "commission": 0.5}]
    notes TEXT,
    -- Optional: add these for deeper analysis
    stop_price NUMERIC(12,4), -- initial stop price
    account_equity NUMERIC(14,4), -- account size at entry
    strategy_tag VARCHAR(32), -- e.g. 'ORB', 'Breakout', etc.
    timeframe VARCHAR(8) -- e.g. '1m', '5m', 'D'
);
