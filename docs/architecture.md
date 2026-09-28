# Architecture — APIx Data Flow

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        COLLECTION LAYER                         │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  IndiGo      │  │  Air India   │  │  MakeMyTrip (OTA)    │  │
│  │  Scraper     │  │  Scraper     │  │  Scraper             │  │
│  │  (Playwright)│  │  (Playwright)│  │  (Playwright)        │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │                 │                      │              │
│         └─────────────────┴──────────────────────┘              │
│                           ↓                                     │
│            data/raw/{source}/{date}/{route}_{window}d.json      │
└─────────────────────────────────────────────────────────────────┘
                            ↓ (triggered after collection)
┌─────────────────────────────────────────────────────────────────┐
│                      CLEANING PIPELINE                          │
│                                                                 │
│   normalize() → apply_iqr_filter() → deduplicate() → upsert()  │
│                                                                 │
│   Flags: is_censored | is_outlier | is_duplicate               │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│              TimescaleDB (PostgreSQL + extension)               │
│                                                                 │
│   fare_quotes (hypertable, partitioned by scrape_timestamp)    │
│   apix_daily | apix_weekly | apix_monthly                      │
│   scraper_runs (audit log)                                     │
└─────────────────────────────────────────────────────────────────┘
                     ↑               ↓
┌────────────────────┐   ┌───────────────────────────────────────┐
│   INDEX ENGINE     │   │              BACKTEST                  │
│                    │   │                                       │
│  Törnqvist formula │   │  DGCA PDF Parser (pdfplumber/camelot) │
│  Route weights     │   │  Monthly APIx vs DGCA avg fare        │
│  from DGCA/Vonter  │   │  Pearson r + Spearman ρ + chart       │
└────────────────────┘   └───────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                     API + DASHBOARD LAYER                       │
│                                                                 │
│  FastAPI                    │  Dashboard (vanilla JS + Chart.js)│
│  /index/daily               │  Time-series line chart           │
│  /index/route/{pair}        │  Sector heatmap (route × week)    │
│  /raw-quotes                │  Lead-time elasticity scatter     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Module Interaction Diagram

```
APScheduler (daily cron, 2am IST)
    │
    ├── BaseScraper.scrape() × 18 tasks (3 routes × 2 windows × 3 sources)
    │       ├── robots_check.is_allowed()
    │       ├── Playwright browser → XHR intercept
    │       ├── CAPTCHA detection → CaptchaDetectedError (no solve)
    │       └── _write_raw() → JSON file
    │
    ├── loader.load_raw_today()
    │       ├── normalizer.normalize()     (raw JSON → FareRecord list)
    │       ├── outlier_filter.apply_iqr_filter()
    │       ├── deduplicator.deduplicate()
    │       └── _upsert_records()  → fare_quotes (TimescaleDB)
    │
    └── index_engine.runner.compute_today()
            ├── weights.load_weights()    (DGCA CSV)
            ├── tornqvist.compute_tornqvist()
            ├── aggregator.aggregate_weekly()
            ├── aggregator.aggregate_monthly()
            └── upsert → apix_daily / apix_weekly / apix_monthly
```

---

## Key Design Decisions

### Why Playwright over Scrapy?
All three target sites are JavaScript-rendered SPAs. DOM scraping would require
waiting for React/Vue rendering and is brittle to class-name changes.
XHR interception via `page.on("response", …)` captures the raw JSON that the
SPA's own frontend parses — it's structurally stable and format-verifiable.

### Why TimescaleDB over plain PostgreSQL?
Fare quotes are time-series data with a natural time column (`scrape_timestamp`).
TimescaleDB hypertables provide:
- Automatic chunk-based partitioning (7-day chunks)
- Compressed cold storage for older chunks
- Native `time_bucket()` SQL functions for aggregation
- Drop-in PostgreSQL compatibility (all SQLAlchemy ORM works unchanged)

### Why Törnqvist over Fisher Ideal?
See [apix/index_engine/formula.md](../apix/index_engine/formula.md).

### Why median fare (not mean)?
After IQR filtering there are still residual fat tails from promotional fares
and error records. Median is more robust than mean in this regime.

---

## Schema — fare_quotes Hypertable

| Column | Type | Description |
|--------|------|-------------|
| scrape_timestamp | TIMESTAMPTZ | Partition key (TimescaleDB) |
| scrape_date | DATE | Date portion of scrape_timestamp |
| origin, destination | CHAR(3) | IATA airport codes |
| carrier | VARCHAR(10) | Airline code (6E, AI, …) |
| flight_number | VARCHAR(10) | e.g. "6E-345" |
| travel_date | DATE | Date of the flight |
| advance_purchase_days | INTEGER | 7 or 30 |
| fare_class | VARCHAR(20) | SAVER, FLEX, ECONOMY, … |
| base_fare | NUMERIC(10,2) | Pre-tax fare in INR |
| taxes_fees | NUMERIC(10,2) | Taxes + fees in INR |
| total_fare | NUMERIC(10,2) | total_fare = base + taxes |
| seats_available | INTEGER | Seats left (nullable) |
| source | VARCHAR(30) | indigo / air_india / makemytrip |
| is_censored | BOOLEAN | True = blocked/sold-out |
| is_outlier | BOOLEAN | True = outside IQR fence |
| is_duplicate | BOOLEAN | True = cheaper quote exists |
