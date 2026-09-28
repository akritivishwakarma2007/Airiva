-- TimescaleDB initialization script
-- Run automatically by Docker on first start

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Hypertable: raw fare quotes (partitioned by scrape_timestamp)
CREATE TABLE IF NOT EXISTS fare_quotes (
    id              BIGSERIAL,
    scrape_timestamp TIMESTAMPTZ NOT NULL,
    scrape_date     DATE        NOT NULL,
    origin          CHAR(3)     NOT NULL,
    destination     CHAR(3)     NOT NULL,
    carrier         VARCHAR(10) NOT NULL,
    flight_number   VARCHAR(10) NOT NULL,
    travel_date     DATE        NOT NULL,
    advance_purchase_days INTEGER NOT NULL,
    fare_class      VARCHAR(20),
    base_fare       NUMERIC(10,2),
    taxes_fees      NUMERIC(10,2),
    total_fare      NUMERIC(10,2) NOT NULL,
    seats_available INTEGER,
    source          VARCHAR(30) NOT NULL,
    is_censored     BOOLEAN     NOT NULL DEFAULT FALSE,
    is_outlier      BOOLEAN     NOT NULL DEFAULT FALSE,
    is_duplicate    BOOLEAN     NOT NULL DEFAULT FALSE,
    raw_file_path   TEXT,
    CONSTRAINT fare_quotes_pkey PRIMARY KEY (id, scrape_timestamp)
);

SELECT create_hypertable(
    'fare_quotes',
    'scrape_timestamp',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '7 days'
);

CREATE INDEX IF NOT EXISTS idx_fq_route
    ON fare_quotes (origin, destination, travel_date, advance_purchase_days);

CREATE UNIQUE INDEX IF NOT EXISTS idx_fq_dedup
    ON fare_quotes (flight_number, travel_date, fare_class, source, scrape_date);

-- Daily index values
CREATE TABLE IF NOT EXISTS apix_daily (
    index_date      DATE        NOT NULL PRIMARY KEY,
    index_value     NUMERIC(10,4) NOT NULL,
    del_bom         NUMERIC(10,4),
    del_blr         NUMERIC(10,4),
    bom_blr         NUMERIC(10,4),
    sample_size     INTEGER,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Weekly index values
CREATE TABLE IF NOT EXISTS apix_weekly (
    iso_year        INTEGER     NOT NULL,
    iso_week        INTEGER     NOT NULL,
    week_start_date DATE        NOT NULL,
    index_value     NUMERIC(10,4) NOT NULL,
    del_bom         NUMERIC(10,4),
    del_blr         NUMERIC(10,4),
    bom_blr         NUMERIC(10,4),
    PRIMARY KEY (iso_year, iso_week)
);

-- Monthly index values
CREATE TABLE IF NOT EXISTS apix_monthly (
    year            INTEGER     NOT NULL,
    month           INTEGER     NOT NULL,
    index_value     NUMERIC(10,4) NOT NULL,
    del_bom         NUMERIC(10,4),
    del_blr         NUMERIC(10,4),
    bom_blr         NUMERIC(10,4),
    PRIMARY KEY (year, month)
);

-- Scraper run log
CREATE TABLE IF NOT EXISTS scraper_runs (
    id              BIGSERIAL   PRIMARY KEY,
    run_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source          VARCHAR(30) NOT NULL,
    origin          CHAR(3)     NOT NULL,
    destination     CHAR(3)     NOT NULL,
    advance_days    INTEGER     NOT NULL,
    status          VARCHAR(20) NOT NULL,  -- success | captcha | robots_blocked | error
    records_written INTEGER,
    error_message   TEXT,
    raw_file_path   TEXT
);

-- Official MoSPI CPI "Airfare" series (eSankhyiki)
CREATE TABLE IF NOT EXISTS cpi_official (
    year        INTEGER     NOT NULL,
    month       INTEGER     NOT NULL CHECK (month BETWEEN 1 AND 12),
    state       TEXT        NOT NULL,
    sector      VARCHAR(20) NOT NULL CHECK (sector IN ('Rural','Urban','Combined')),
    item_code   VARCHAR(30) NOT NULL DEFAULT '07.3.3.1.2.01',
    base_year   INTEGER     NOT NULL DEFAULT 2024,
    index_value NUMERIC(10,2) NOT NULL,
    inflation   NUMERIC(10,2),
    imputed     BOOLEAN     NOT NULL DEFAULT FALSE,
    PRIMARY KEY (year, month, state, sector, item_code)
);

CREATE INDEX IF NOT EXISTS idx_cpi_lookup ON cpi_official (state, sector, year, month);

