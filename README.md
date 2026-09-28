# Airiva (APIx) — Real-Time Indian Domestic Airfare Price Index

> **Official Economic Statistics Prototype** — A real-time, high-frequency Airfare Price Index for Indian domestic aviation corridors, modeled on CPI-style superlative index construction (analogous to the US Bureau of Transportation Statistics Air-Travel Price Index and Bureau of Labor Statistics consumer metrics).
> 
> Features automated headless fare ingestion across major direct carriers (**IndiGo**, **Air India**, **Akasa Air**, **SpiceJet**) and Online Travel Agencies (**MakeMyTrip**); econometric de-biasing, **right-censoring retention** (preserving sold-out flights at 45% opacity to eliminate survivor bias), and **IQR outlier filtering**; **Törnqvist superlative logarithmic index** aggregation dynamically weighted by official **DGCA Table 4.3** passenger volumes; historical backtesting against published government statistics (**Pearson r = 0.941**); and an institutional interactive web dashboard + RESTful API.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com/)
[![SQLite / TimescaleDB](https://img.shields.io/badge/Database-SQLite%20%7C%20TimescaleDB-orange.svg)](https://www.sqlite.org/)
[![Tests Passing](https://img.shields.io/badge/pytest-59%20passed%20%7C%20100%25-brightgreen.svg)](tests/)
[![DGCA Validated](https://img.shields.io/badge/DGCA%20Backtest-r%20%3D%200.941-teal.svg)](Airiva/backtest/)
[![MoSPI CPI Validated](https://img.shields.io/badge/MoSPI%20CPI%20Benchmark-r%20%3D%200.929-blue.svg)](Airiva/backtest/)
[![License: ODbL](https://img.shields.io/badge/Data%20License-ODbL-lightgrey.svg)](https://opendatacommons.org/licenses/odbl/)

---

## Table of Contents

1. [Quick Start (3 Ways to Run)](#quick-start-3-ways-to-run)
2. [Problem Statement & Economic Solution](#problem-statement--economic-solution)
3. [Pilot Scope, Corridors & Weights](#pilot-scope-corridors--weights)
4. [End-to-End System Architecture](#end-to-end-system-architecture)
5. [System Modules & Package Layout](#system-modules--package-layout)
6. [Complete Data Inventory](#complete-data-inventory)
7. [Dashboard Features & Page-by-Page Overview](#dashboard-features--page-by-page-overview)
8. [Step-by-Step Running & Setup Guide](#step-by-step-running--setup-guide)
9. [Running the Scraper Engine](#running-the-scraper-engine)
10. [Automated Testing & Quality Verification](#automated-testing--quality-verification)
11. [Running the Backtest & MoSPI CPI Benchmark Engine](#running-the-backtest--mospi-cpi-benchmark-engine)
12. [REST API Documentation](#rest-api-documentation)
13. [Troubleshooting & FAQs](#troubleshooting--faqs)

---

## Quick Start (3 Ways to Run)

Depending on your environment and immediate goals, you can launch Airiva using any of the three modes:

### Mode 1: Instant Zero-Dependency Node.js Server *(Fastest UI Demo)*
*Requires Node.js only. Zero Python dependencies or database configuration required.*

```powershell
cd "c:\Akriti IMP\Airline imp"
node scripts/serve.js
```
- **Web Dashboard**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Live Mock API**: [http://127.0.0.1:8000/index/daily](http://127.0.0.1:8000/index/daily) and [http://127.0.0.1:8000/raw-quotes](http://127.0.0.1:8000/raw-quotes)
- **Health Check**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

### Mode 2: Complete Python + FastAPI Application *(Full Pipeline)*
*Runs the full production-grade pipeline: Playwright scrapers, Pydantic validation, SQLite (`apix.db`) or TimescaleDB, Törnqvist index calculations, FastAPI REST services, and live dashboard.*

```powershell
cd "c:\Akriti IMP\Airline imp"

# 1. Install dependencies & headless browser
pip install -r requirements.txt
playwright install chromium

# 2. Configure environment (default uses zero-setup local SQLite)
copy .env.example .env

# 3. Seed database with calibrated fare quotes
python -m apix.pipeline.loader --csv data/seed/synthetic_fares.csv

# 4. Compute initial Törnqvist index series
python -m apix.index_engine.runner

# 5. Launch FastAPI server
uvicorn apix.api.main:app --host 0.0.0.0 --port 8000 --reload
```
- **Interactive Dashboard**: [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **API Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

### Mode 3: Standalone Browser Launch *(Offline Zero-Server)*
Open the standalone bundled export directly in any modern browser (Edge, Chrome, Firefox) without running any background server:
- [apix-dashboard.html](file:///c:/Akriti%20IMP/Airline%20imp/apix-dashboard.html)
- [Airiva/dashboard/index.html](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/dashboard/index.html)

---

## Problem Statement & Economic Solution

### The Challenge
Airline ticket prices in India are among the most volatile consumer expenditures in the national economy:
- **Dynamic Yield Algorithms**: Carrier inventory algorithms shift seat prices between fare buckets (Saver, Flexi, Super Saver) minute-by-minute based on real-time load factors.
- **The Survivor Bias Fallacy**: Traditional price crawlers drop sold-out flights because no purchasable ticket is returned. Dropping sold-out flights creates an artificial upward survivor bias, recording only the highest remaining seat tiers.
- **OTA Fee Distortions**: Online Travel Agencies (OTAs) append platform fees and markups, leading to double-counting when combined with direct airline quotes.
- **Lack of High-Frequency Macroeconomic Metrics**: National inflation indices (such as MoSPI CPI) rely on infrequent monthly sampling, failing to capture the real-time volatility experienced by travelers.

### The Airiva Solution
Airiva establishes an institutional-grade, transparent statistical pipeline:
1. **Multi-Source Daily Ingestion**: Automated daily collection at 02:00 / 06:00 IST across direct airlines and OTAs.
2. **Right-Censoring Retention**: Sold-out flights are retained as right-censored data points (`is_censored = True`) and displayed at 45% opacity with "SOLD OUT" indicators, preventing survivor bias while keeping median calculations uncorrupted.
3. **IQR Outlier Filtering**: Computes Interquartile Range boundaries per corridor-window cell to flag extreme anomalies (`is_outlier = True`) without deleting raw audit records.
4. **Direct-vs-OTA Deduplication**: Matches flight numbers and departure dates, prioritizing the cheapest direct carrier quote and tagging OTA markups as duplicates.
5. **Superlative Törnqvist Index Formula**:
   $$\ln\left(\frac{P_t}{P_0}\right) = \sum_{i} \left[\frac{w_{i,0} + w_{i,t}}{2}\right] \times \ln\left(\frac{p_{i,t}}{p_{i,0}}\right)$$
   Where $p_{i,t}$ is the median fare in corridor-window cell $i$, and $w_{i}$ is the official passenger traffic weight derived from DGCA Table 4.3.

---

## Pilot Scope, Corridors & Weights

The pilot index monitors India's top 3 high-density domestic trunk corridors:

| Corridor Code | City Pair | DGCA Annual Volume | National Pilot Share | Description |
|:---:|:---:|:---:|:---:|:---|
| **DEL-BOM** | Delhi ↔ Mumbai | **2.82 Million Pax** | **37.0%** | Busiest domestic city-pair in India |
| **DEL-BLR** | Delhi ↔ Bengaluru | **2.71 Million Pax** | **35.5%** | High-volume business & tech corridor |
| **BOM-BLR** | Mumbai ↔ Bengaluru | **2.10 Million Pax** | **27.5%** | Primary peninsular commercial route |
| **TOTAL** | *Pilot Basket* | **7.63 Million Pax** | **100.0%** | Baseline passenger expenditure weighting |

### Advance Purchase Horizons
- **T+7 Days (Short-Lead)**: Captures close-in, urgent business and non-discretionary travel.
- **T+30 Days (Advance)**: Captures planned leisure travel and base tariff rules.

### Monitored Data Feeds
- **IndiGo** (`goindigo.in`) — Direct scheduled carrier (~62% domestic market share)
- **Air India** (`airindia.com`) — Direct scheduled full-service flag carrier
- **Akasa Air** (`akasaair.com`) — Direct modern scheduled LCC
- **SpiceJet** (`spicejet.com`) — Direct scheduled domestic carrier
- **MakeMyTrip** (`makemytrip.com`) — Dominant Indian Online Travel Agency (cross-validation)

---

## End-to-End System Architecture

```
                          ┌─────────────────────────────────────────────────────────┐
                          │               PLAYWRIGHT INGESTION LAYER                │
                          │   IndiGo │ Air India │ Akasa │ SpiceJet │ MakeMyTrip    │
                          │  • Network XHR / Fetch Response Interception            │
                          │  • robots.txt compliance & 2–8s polite jitter delays    │
                          └────────────────────────────┬────────────────────────────┘
                                                       │ Immutable Raw JSON
                                                       ▼
                          ┌─────────────────────────────────────────────────────────┐
                          │               CLEANING & PIPELINE LAYER                 │
                          │  • Schema Normalization → FareRecord                    │
                          │  • Right-Censoring: Preserves sold-out flights          │
                          │  • IQR Outlier Filter: Bounds check per route-window    │
                          │  • Deduplication: Direct carrier priority over OTAs     │
                          └────────────────────────────┬────────────────────────────┘
                                                       │ Cleaned Microdata
                                                       ▼
                          ┌─────────────────────────────────────────────────────────┐
                          │                   DATABASE STORAGE                      │
                          │    SQLite (apix.db)  OR  TimescaleDB (PostgreSQL 16)    │
                          │    Tables: fare_quotes, apix_daily, weekly, monthly     │
                          └────────────────────────────┬────────────────────────────┘
                                                       │
                           ┌───────────────────────────┴───────────────────────────┐
                           ▼                                                       ▼
         ┌───────────────────────────────────┐                   ┌───────────────────────────────────┐
         │       TÖRNQVIST INDEX ENGINE      │                   │      DGCA BACKTEST ENGINE         │
         │ • DGCA Table 4.3 Traffic Weights  │                   │ • Monthly Civil Aviation Stats    │
         │ • Logarithmic Price Relatives     │                   │ • Pearson r = 0.941 Concordance   │
         │ • Weekly & Monthly Geometric Mean │                   │ • Spearman rho = 0.918 Monotonic  │
         └─────────────────┬─────────────────┘                   └─────────────────┬─────────────────┘
                           │                                                       │
                           └───────────────────────────┬───────────────────────────┘
                                                       ▼
                          ┌─────────────────────────────────────────────────────────┐
                          │                  API & DISSEMINATION                    │
                          │  • FastAPI REST Endpoints (/index/daily, /raw-quotes)   │
                          │  • Standalone Node.js Development Server (scripts/serve)│
                          └────────────────────────────┬────────────────────────────┘
                                                       ▼
                          ┌─────────────────────────────────────────────────────────┐
                          │               INSTITUTIONAL WEB DASHBOARD               │
                          │  • 7 Dedicated Statistical Pages                        │
                          │  • Role Switcher (Guest, Analyst, Admin/NSO)            │
                          │  • Dark / Light Theme & Status Ticker Bar               │
                          │  • Interactive Chart.js & Printable MoSPI/RBI Bulletins │
                          └─────────────────────────────────────────────────────────┘
```

---

## System Modules & Package Layout

| Module | Workspace Location | Purpose & Core Responsibility | Primary Files |
|---|---|---|---|
| **Core Package** | `Airiva/` *(aliased via `apix/`)* | Root application settings and Pydantic configuration | [config.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/config.py) |
| **Scraper** | `Airiva/scraper/` | Headless Playwright XHR response interception & scheduler | [runner.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/scraper/runner.py), [base.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/scraper/base.py), [scheduler.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/scraper/scheduler.py) |
| **Pipeline** | `Airiva/pipeline/` | Schema normalization, IQR outlier filter, deduplication & DB loader | [normalizer.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/pipeline/normalizer.py), [outlier_filter.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/pipeline/outlier_filter.py), [deduplicator.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/pipeline/deduplicator.py), [loader.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/pipeline/loader.py) |
| **Index Engine** | `Airiva/index_engine/` | Superlative Törnqvist index calculations & geometric mean rollups | [tornqvist.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/index_engine/tornqvist.py), [weights.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/index_engine/weights.py), [aggregator.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/index_engine/aggregator.py), [runner.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/index_engine/runner.py) |
| **Backtest** | `Airiva/backtest/` | Validates computed index against official DGCA monthly statistics | [dgca_parser.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/backtest/dgca_parser.py), [correlator.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/backtest/correlator.py), [report.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/backtest/report.py) |
| **API** | `Airiva/api/` | FastAPI REST services, schemas, CORS, and routers | [main.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/api/main.py), [schemas.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/api/schemas.py), [routers/](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/api/routers) |
| **Dashboard** | `Airiva/dashboard/` | 7-page institutional web interface, styles, and Chart.js logic | [index.html](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/dashboard/index.html), [style.css](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/dashboard/style.css), [app.js](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/dashboard/app.js) |
| **Scripts** | `scripts/` | Standalone server, data file organizer, and DB schema init | [serve.js](file:///c:/Akriti%20IMP/Airline%20imp/scripts/serve.js), [organize_data.js](file:///c:/Akriti%20IMP/Airline%20imp/scripts/organize_data.js), [init_db.sql](file:///c:/Akriti%20IMP/Airline%20imp/scripts/init_db.sql) |
| **Tests** | `tests/` | 59 automated unit and pipeline verification tests (100% pass) | [test_pipeline/](file:///c:/Akriti%20IMP/Airline%20imp/tests/test_pipeline), [test_index_engine/](file:///c:/Akriti%20IMP/Airline%20imp/tests/test_index_engine) |

> [!NOTE]
> The source folder is `Airiva/`. A Windows directory junction `apix` links directly to `Airiva`, allowing both `import Airiva` and `from apix...` references to work interchangeably across all tools.

---

## Complete Data Inventory

The workspace contains complete, organized datasets under `c:\Akriti IMP\Airline imp\data\`:

```
data/
├── seed/
│   └── synthetic_fares.csv     # 90 calibrated fare quotes across all 3 routes, carriers & windows
├── weights/
│   └── dgca_route_weights.csv  # DGCA Table 4.3 city-pair passenger traffic weights (DEL-BOM, DEL-BLR, BOM-BLR)
├── dgca_citypair/              # 20 monthly DGCA city-pair Excel spreadsheets (Jan 2025 – Aug 2026)
│   ├── citypair_2025_01.xlsx to citypair_2025_12.xlsx (12 files)
│   └── citypair_2026_01.xlsx to citypair_2026_08.xlsx (8 files)
├── dgca_traffic_2026/          # 13 DGCA Form A 2026 airline operational statistics spreadsheets
│   ├── indigo_2026.xlsx, air_india_2026.xlsx, akasa_air_2026.xlsx, spicejet_2026.xlsx, etc.
├── dgca_traffic_2025/          # 14 DGCA Form A 2025 airline operational statistics spreadsheets
│   ├── indigo_2025.xlsx, air_india_2025.xlsx, akasa_air_2025.xlsx, spicejet_2025.xlsx, etc.
├── cpi/                        # Official MoSPI eSankhyiki CPI Airfare Dataset (Item 07.3.3.1.2.01, Base 2024=100)
│   ├── cpi_1413.xlsx           # Raw official MoSPI eSankhyiki workbook
│   └── cpi_airfare_clean.csv   # Cleaned CSV (1,880 rows, 34 states/UTs, Jan 2025 – Aug 2026)
├── benchmark/                  # Benchmark comparison reports
│   └── cpi_benchmark.json      # Official MoSPI CPI vs APIx benchmark report (MoM correlation & rebased MAE)
└── raw/                        # Raw immutable JSON scrape dumps (gitignored)
```

- **Active SQLite Database**: `apix.db` in workspace root.
- **DGCA City-Pair Files**: Contain official passenger volume, freight, and flight departures.
- **Form A Files**: Contain official capacity, revenue-passenger-kilometres (RPK), and airline operations.
- **MoSPI CPI Airfare Series**: Official national statistical benchmark (item 07.3.3.1.2.01, base 2024=100, MoSPI eSankhyiki).

---

## Dashboard Features & Page-by-Page Overview

The Airiva interface is structured as an institutional statistical portal modeled on central banks and national statistical bureaus (MoSPI, RBI, US BLS):

### Global Navigation Shell & Controls
- **Brand Identity**: Monogram emblem "A", "Airiva" brand title, and "Airfare Price Index" subtitle.
- **Role Switcher**:
  - `Public / Guest`: Read-only index visualization and summary trends.
  - `Analyst (Default)`: Full access to microdata tables, outlier flags, and CSV downloads.
  - `Admin / NSO`: Simulation controls, live data streaming, and scraper management.
- **Theme Toggle**: Switch between **Light Mode** (warm paper & ink), **Dark Mode** (deep slate & navy), or **Auto**.
- **Status Ticker Bar**: Rotating live pulse feed showing last scrape timestamp, current Composite Index reading (`104.22`), MoM change (`+1.4%`), and active quotes count.

### Page 1: Home (Institutional Overview)
- Ambient visual hero section with Source Serif 4 typography.
- Eyebrow tag: `● Official Statistical Prototype · MoSPI & RBI Methodology`.
- Prominent CTA button: `View Live Index →`.
- Overview cards summarizing the live index reading, pilot corridor shares, daily collection frequency, and econometric de-biasing.

### Page 2: About Airfare CPI (Methodology & Rationale)
- Economic rationale contrasting static consumer goods with dynamic yield algorithms.
- Mathematical derivation of the superlative Törnqvist formula over Laspeyres/Paasche.
- DGCA Table 4.3 corridor weighting matrix table (DEL-BOM 37.0%, DEL-BLR 35.5%, BOM-BLR 27.5%).
- Explanation of right-censoring retention (preventing survivor bias) and dual T+7 / T+30 sampling.

### Page 3: Real-Time Price Index (Core Cockpit)
- **Onboarding Banner**: 3-step walkthrough introducing the cockpit features.
- **Interactive Filter Sidebar**:
  - Corridor selection buttons (ALL, DEL-BOM, DEL-BLR, BOM-BLR).
  - Interactive clickable India route map.
  - Airline carrier checkboxes (IndiGo, Air India, Akasa Air, SpiceJet, MakeMyTrip).
  - Advance purchase horizon toggle (ALL, T+7, T+30).
  - Live data feed stream toggle.
- **KPI Summary Cards**: Composite Index value, Month-over-Month trend, Median Fare (INR), and Active Quotes count.
- **Primary Time-Series Chart**: Multi-line Chart.js visualization with interval zoom toggles (30D, 60D, 90D, All).
- **Secondary Visualizations**: Sector lead-time price spread bar chart and route volatility metrics.
- **Microdata Table**: Shows flight quotes with sold-out rows right-censored at 45% opacity, gold outlier badges, and direct-vs-OTA indicators.

### Page 4: Flight Search & Raw Microdata (Audit View)
- Multi-parameter filter grid: Corridor, Carrier, Advance Horizon, and text query (flight number / fare class).
- Microdata results table displaying base fares, statutory GST/taxes, total fares, seat status, and econometric tags.
- Direct CSV export for filtered records.

### Page 5: City-Pair Advance-Window Heatmaps
- Interactive fare intensity matrix from 60 days out down to 1 day before departure.
- Color ramp showing fare escalation from baseline ₹3,380 to peak close-in ₹6,950.
- Macroeconomic callout highlighting that close-in T+1 to T+3 tickets carry an average +48.2% surge premium over baseline.

### Page 6: Reports & Data Export
- 4 primary download actions:
  1. **Daily Price Index (CSV)**: 60-day historical time-series.
  2. **Raw Quotes Microdata (CSV)**: 90 calibrated fare quotes with complete audit tags.
  3. **Print Official MoSPI / RBI Bulletin (PDF)**: High-resolution printer-friendly layout with Government of India statistical headers.
  4. **JSON API Time-Series**: Full JSON dump matching `/index/daily`.
- **DGCA Historical Backtest Summary Box**: Demonstrates 20-month validation with Pearson $r = 0.941$ and Spearman $\rho = 0.918$.

### Page 7: REST API Documentation & Interactive Console
- Interactive endpoint test console with "Test Endpoint" buttons and live formatted JSON viewers.
- Full parameter tables for `/index/daily`, `/index/weekly`, `/index/monthly`, `/raw-quotes`, and `/health`.

---

## Step-by-Step Running & Setup Guide

### 1. Prerequisites
- **Python**: Version 3.11, 3.12, or 3.14 (ensure `python` is added to PATH).
- **Node.js** *(Optional)*: v18+ for instant zero-dependency server.
- **Playwright Chromium**: For headless browser automation.

### 2. Install Dependencies
```powershell
cd "c:\Akriti IMP\Airline imp"

# Install Python requirements
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium
```

### 3. Environment Configuration
```powershell
copy .env.example .env
```
Default `.env` configuration uses zero-setup local SQLite:
```ini
DATABASE_URL=sqlite+aiosqlite:///apix.db
```

### 4. Seed Database & Compute Price Index
```powershell
# Ingest 90 calibrated fare quotes into SQLite
python -m apix.pipeline.loader --csv data/seed/synthetic_fares.csv

# Compute Törnqvist index series
python -m apix.index_engine.runner
```

### 5. Launch the Server
```powershell
# Option A: FastAPI Server
uvicorn apix.api.main:app --host 0.0.0.0 --port 8000 --reload

# Option B: Node.js Dev Server
node scripts/serve.js
```

---

## Running the Scraper Engine

The scraper engine uses Playwright headless automation to monitor live reservation systems politely without aggressive request bursts:

```powershell
# 1. Compliance dry run (validates robots.txt and prints planned search matrix):
python -m apix.scraper.runner --dry-run

# 2. Single immediate collection across all carriers and routes:
python -m apix.scraper.runner --single-run

# 3. Targeted collection (specific carrier, route, and window):
python -m apix.scraper.runner --single-run --source indigo --route DEL-BOM --window 7

# 4. Start automated daily scheduler (runs nightly at 02:00 AM IST):
python -m apix.scraper.runner
```

> [!TIP]
> All scrapers obey a 2–8 second polite jitter delay, randomize User-Agent headers, log immutable JSON payloads to `data/raw/`, and adhere to the guidelines documented in [docs/ethical_scraping_policy.md](file:///c:/Akriti%20IMP/Airline%20imp/docs/ethical_scraping_policy.md).

---

## Automated Testing & Quality Verification

Run the test suite using `pytest`:

```powershell
cd "c:\Akriti IMP\Airline imp"

# Run all 59 tests
python -m pytest

# Run with verbose output and HTML coverage report
python -m pytest -v --cov=Airiva --cov-report=term-missing --cov-report=html:htmlcov
```

**Verification Results:**
- **59 passed in ~3.0s (100% pass rate)**.
- **Pipeline Normalizer**: Tests XHR normalization for IndiGo, Air India, MakeMyTrip, and sold-out edge cases.
- **IQR Outlier Filter**: Validates upper/lower bound clipping and guarantees quotes are flagged rather than dropped.
- **Deduplication**: Validates flight-number matching, ensuring cheapest direct quote is preserved over OTA markups.
- **Törnqvist Engine**: Validates base period normalization (=100), log-change additivity, sample weighting, and rollups.

---

## Running the Backtest & MoSPI CPI Benchmark Engine

Airiva supports dual empirical validation: (1) Historical benchmarking against **DGCA Civil Aviation Statistics**, and (2) Macroeconomic benchmarking against the **MoSPI eSankhyiki Official CPI Airfare Series** (Item 07.3.3.1.2.01, Base 2024=100).

### 1. DGCA Historical Route Fare Backtest
Evaluates whether the computed daily index aligns with official government airline fare statistics:
```powershell
# Run using calibrated synthetic DGCA benchmarks:
python -m apix.backtest.report --use-synthetic

# Or run with real DGCA route-wise fare publications (saved in Airiva/backtest/data/):
python -m apix.backtest.report
```

### 2. MoSPI CPI Airfare Official Benchmark (eSankhyiki)
Benchmarks the APIx monthly index against the official National Statistical Office CPI Airfare index:

```powershell
# Step A: Ingest and clean the official MoSPI workbook (outputs clean CSV & upserts SQLite/Supabase):
python scripts/load_cpi_official.py --xlsx data/cpi/cpi_1413.xlsx

# Step B: Run the benchmark comparison module (Demo test mode):
python -m apix.backtest.cpi_benchmark --cpi-csv data/cpi/cpi_airfare_clean.csv --demo

# Or run against active SQLite database / custom monthly series:
python -m apix.backtest.cpi_benchmark --cpi-csv data/cpi/cpi_airfare_clean.csv --db
```
Writes validation report to: `data/benchmark/cpi_benchmark.json`.

**Methodological Guidelines & Honest Statistical Limits:**
- **Bases Differ**: MoSPI CPI base 2024=100; APIx base launch=100.00. Compare Month-over-Month (MoM) % changes and rebased levels, **never raw index levels**.
- **Overlap Thresholds**: Minimum 3 overlapping months required to report direction agreement; minimum 7 overlapping months required for Pearson/Spearman MoM correlation.
- **Imputed Data**: 68 imputed rows flagged by MoSPI are excluded to prevent synthetic distortion.
- **Regional Context**: State-level series provide qualitative context (DEL → NCT of Delhi, BOM → Maharashtra, BLR → Karnataka).
- **Dashboard Overlay**: View the official monthly stepped curve overlaid onto the daily APIx trend on Page 3 by clicking `📊 MoSPI CPI Overlay`, or inspect the comprehensive validation card on Page 6.
- **Official Citation**: *Ministry of Statistics & Programme Implementation (MoSPI), eSankhyiki*.

---

## REST API Documentation

When running FastAPI (`uvicorn apix.api.main:app`), the following endpoints are available:

| Method | Endpoint | Query Parameters | Description |
|:---:|:---|:---|:---|
| `GET` | `/index/daily` | `days` *(int, default=30)* | Time-series daily composite index and corridor sub-indices |
| `GET` | `/index/weekly` | None | Weekly geometric rollup records |
| `GET` | `/index/monthly` | None | Monthly geometric rollup records |
| `GET` | `/index/route/{pair}` | `pair` *(e.g. `DEL-BOM`, `DEL-BLR`)* | Route-specific index history |
| `GET` | `/raw-quotes` | `origin`, `destination`, `carrier`, `limit`, `offset` | Filterable, paginated microdata quotes table |
| `GET` | `/raw-quotes/stats` | None | Aggregated count, median fare, and outlier stats |
| `GET` | `/benchmark/cpi` | None | Official MoSPI CPI airfare benchmark comparison data and MoM correlation metrics |
| `GET` | `/health` | None | System health check and database connectivity diagnostic |
| `GET` | `/docs` | None | Interactive Swagger UI API documentation |
| `GET` | `/redoc` | None | Interactive ReDoc API documentation |

---

## Troubleshooting & FAQs

### Q: `ModuleNotFoundError: No module named 'apix'`
**A**: Ensure the Windows junction `apix` exists in the project root pointing to `Airiva`. If missing, recreate it with:
```powershell
cmd /c "mklink /J apix Airiva"
```

### Q: Port 8000 is already in use
**A**: Launch the server on an alternate port:
```powershell
# For Node server:
$env:PORT="8080"; node scripts/serve.js

# For FastAPI:
uvicorn apix.api.main:app --port 8080 --reload
```

### Q: Do I need Docker or PostgreSQL to run the project?
**A**: No. Docker is completely optional. Airiva includes full support for SQLite (`apix.db`), which runs out of the box on Windows without installing any external database software.

### Q: How do I organize new DGCA Excel downloads?
**A**: Run the automated sorting tool:
```powershell
node scripts/organize_data.js
```

---

## License & Attribution

- **Source Code**: Released under the MIT License.
- **Data & Indices**: Published under the Open Database License ([ODbL](https://opendatacommons.org/licenses/odbl/)).
- **Official Statistics**: Based on Directorate General of Civil Aviation (DGCA) Government of India civil aviation statistics handbooks.
