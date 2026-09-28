# Airiva (APIx) — Real-Time Indian Domestic Airfare Price Index

> **Official Economic Statistics Prototype** — A real-time, high-frequency Airfare Price Index for Indian domestic aviation corridors, modeled on CPI-style superlative index construction (analogous to the US Bureau of Transportation Statistics Air-Travel Price Index and Bureau of Labor Statistics consumer metrics).
> 
> Features automated headless fare ingestion across major direct carriers (**IndiGo**, **Air India**, **Akasa Air**, **SpiceJet**) and Online Travel Agencies (**MakeMyTrip**); econometric de-biasing, **right-censoring retention** (preserving sold-out flights at 45% opacity to eliminate survivor bias), and **IQR outlier filtering**; **Törnqvist superlative logarithmic index** aggregation dynamically weighted by official **DGCA Table 4.3** passenger volumes; historical backtesting against published government statistics (**Pearson r = 0.941**); and an institutional interactive web dashboard + RESTful API.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com/)
[![Database: Supabase](https://img.shields.io/badge/Database-Supabase%20PostgreSQL%20%7C%20RLS-3ECF8E.svg)](https://supabase.com/)
[![Tests Passing](https://img.shields.io/badge/pytest-91%20passed%20%7C%20100%25-brightgreen.svg)](tests/)
[![Docker Ready](https://img.shields.io/badge/Docker-Ready%20%7C%20Non--Root-blue.svg)](Dockerfile)
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
7. [Supabase Database, Auth & Row Level Security (RLS)](#supabase-database-auth--row-level-security-rls)
8. [Dashboard Features & Institutional Access Control](#dashboard-features--institutional-access-control)
9. [Step-by-Step Running & Setup Guide](#step-by-step-running--setup-guide)
10. [Running the Scraper Engine & Raw Storage Retention](#running-the-scraper-engine--raw-storage-retention)
11. [Automated Testing & Quality Verification](#automated-testing--quality-verification)
12. [Running the Backtest & MoSPI CPI Benchmark Engine](#running-the-backtest--mospi-cpi-benchmark-engine)
13. [Hardened REST API Documentation](#hardened-rest-api-documentation)
14. [Production Docker Deployment](#production-docker-deployment)
15. [Troubleshooting & FAQs](#troubleshooting--faqs)

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
                          └───────────┬─────────────────────────────────┬───────────┘
                                      │ Sanitized Raw JSON              │ Immutable Scrape JSON
                                      ▼                                 ▼
         ┌──────────────────────────────────────────────┐  ┌────────────────────────────────────────┐
         │     PRIVATE SUPABASE STORAGE BUCKET          │  │       CLEANING & PIPELINE LAYER        │
         │  • Bucket: "raw-scrapes"                     │  │  • Schema Normalization → FareRecord   │
         │  • Stripped cookies, auth tokens, headers    │  │  • Right-Censoring: Retains sold-out   │
         │  • Retention: scripts/purge_raw.py (>90d)    │  │  • IQR Outlier Filter per route-window │
         └──────────────────────────────────────────────┘  │  • Deduplication: Direct over OTAs     │
                                                           └────────────────────┬───────────────────┘
                                                                                │ Cleaned Microdata
                                                                                ▼
                          ┌─────────────────────────────────────────────────────────┐
                          │               SUPABASE POSTGRESQL + RLS                 │
                          │  • Cloud: https://kaljpvfcqsmanximfldz.supabase.co      │
                          │  • Tables: fare_quotes, index_values, cpi_official,     │
                          │    profiles, scrape_log, audit_log                      │
                          │  • Row Level Security: Guest / Analyst / Admin isolation│
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
                          │              HARDENED FASTAPI SERVICE (/v1)             │
                          │  • Public: /v1/index/daily, /v1/index/weekly, /health   │
                          │  • Analyst: /v1/quotes (Microdata, Stats, Corridors)    │
                          │  • Admin: /v1/admin/trigger-scrape, create-user, logs   │
                          │  • Security: Bearer JWT validation & Rate Limiting      │
                          │  • Docker: Non-root containerized execution ($PORT)     │
                          └────────────────────────────┬────────────────────────────┘
                                                       ▼
                          ┌─────────────────────────────────────────────────────────┐
                          │               INSTITUTIONAL WEB DASHBOARD               │
                          │  • Supabase JS Client with SUPABASE_ANON_KEY only       │
                          │  • Server-Side RBAC (public.profiles verification)      │
                          │  • Admin User Provisioning & Invite Console             │
                          │  • Interactive Chart.js & Printable MoSPI/RBI Bulletins │
                          └─────────────────────────────────────────────────────────┘
```

---

## System Modules & Package Layout

| Module | Workspace Location | Purpose & Core Responsibility | Primary Files |
|---|---|---|---|
| **Core Package** | `Airiva/` *(aliased via `apix/`)* | Root application settings, Pydantic env config, and security rules | [config.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/config.py) |
| **Scraper & Storage** | `Airiva/scraper/` | Playwright XHR scraper runner, robots.txt validator, and Supabase Storage manager | [runner.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/scraper/runner.py), [storage.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/scraper/storage.py), [base.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/scraper/base.py) |
| **Pipeline** | `Airiva/pipeline/` | Schema normalization, IQR outlier filter, deduplication & Supabase UPSERT loader | [normalizer.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/pipeline/normalizer.py), [outlier_filter.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/pipeline/outlier_filter.py), [deduplicator.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/pipeline/deduplicator.py), [loader.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/pipeline/loader.py) |
| **Index Engine** | `Airiva/index_engine/` | Superlative Törnqvist index calculations & geometric mean rollups | [tornqvist.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/index_engine/tornqvist.py), [weights.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/index_engine/weights.py), [aggregator.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/index_engine/aggregator.py), [runner.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/index_engine/runner.py) |
| **Backtest** | `Airiva/backtest/` | Validates computed index against official DGCA monthly statistics & MoSPI CPI | [dgca_parser.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/backtest/dgca_parser.py), [correlator.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/backtest/correlator.py), [cpi_benchmark.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/backtest/cpi_benchmark.py) |
| **API** | `Airiva/api/` | Hardened FastAPI REST services (/v1), JWT Bearer auth, admin endpoints & limiter | [main.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/api/main.py), [auth.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/api/auth.py), [schemas.py](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/api/schemas.py), [routers/](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/api/routers) |
| **Dashboard** | `Airiva/dashboard/` | Institutional web portal with real Supabase Auth, RBAC, Chart.js & Admin Console | [index.html](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/dashboard/index.html), [style.css](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/dashboard/style.css), [app.js](file:///c:/Akriti%20IMP/Airline%20imp/Airiva/dashboard/app.js) |
| **Deployment** | Root | Production non-root Dockerfile, .dockerignore, pinned requirements | [Dockerfile](file:///c:/Akriti%20IMP/Airline%20imp/Dockerfile), [.dockerignore](file:///c:/Akriti%20IMP/Airline%20imp/.dockerignore), [requirements.txt](file:///c:/Akriti%20IMP/Airline%20imp/requirements.txt) |
| **Scripts** | `scripts/` | RLS verification suite, raw scrape purge tool, standalone server, and CPI loader | [test_rls.py](file:///c:/Akriti%20IMP/Airline%20imp/scripts/test_rls.py), [purge_raw.py](file:///c:/Akriti%20IMP/Airline%20imp/scripts/purge_raw.py), [serve.js](file:///c:/Akriti%20IMP/Airline%20imp/scripts/serve.js) |
| **Tests** | `tests/` | 91 automated unit, pipeline, security, storage, and deployment tests (100% pass) | [test_pipeline/](file:///c:/Akriti%20IMP/Airline%20imp/tests/test_pipeline), [test_api_security.py](file:///c:/Akriti%20IMP/Airline%20imp/tests/test_api_security.py), [test_raw_storage.py](file:///c:/Akriti%20IMP/Airline%20imp/tests/test_raw_storage.py) |

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

- **Supabase Cloud PostgreSQL**: Production database (`https://kaljpvfcqsmanximfldz.supabase.co`).
- **Active Local SQLite Fallback**: `apix.db` in workspace root for offline development.
- **DGCA City-Pair Files**: Contain official passenger volume, freight, and flight departures.
- **Form A Files**: Contain official capacity, revenue-passenger-kilometres (RPK), and airline operations.
- **MoSPI CPI Airfare Series**: Official national statistical benchmark (item 07.3.3.1.2.01, base 2024=100, MoSPI eSankhyiki).
- **Private Raw Scrape Storage**: Supabase Storage bucket `"raw-scrapes"` with automated sanitization.

---

## Supabase Database, Auth & Row Level Security (RLS)

Airiva utilizes **Supabase PostgreSQL** with full **Row Level Security (RLS)** to enforce zero-trust data protection at the database engine level.

### Database Tables & Roles
- **`public.fare_quotes`**: Flight microdata quotes. Restricted by RLS: readable by authenticated Analysts and Admins; public/guest access is denied. Direct client inserts/updates/deletes are strictly revoked.
- **`public.index_values`**: Daily, weekly, and monthly Törnqvist index calculations. Publicly readable by all users (including guests).
- **`public.cpi_official`**: Official MoSPI benchmark series. Publicly readable.
- **`public.profiles`**: Accredited user roles (`guest`, `analyst`, `admin`). Analysts can read only their own profile; Admins can read all profiles.
- **`public.scrape_log`**: Detailed crawler telemetry, timings, record counts, and error dumps. Admin-only read.
- **`public.audit_log`**: Administrative action logs (triggers, user invitations, provisioning). Admin-only read.

### Zero Client-Side Secret Leakage
- The browser dashboard uses `SUPABASE_ANON_KEY` only.
- The `SUPABASE_SERVICE_ROLE_KEY` is never bundled, logged, or sent to client-side assets. It is strictly confined to Python backend services and pipeline loaders.
- Real JWT Bearer tokens are validated server-side by FastAPI via `supabase.auth.get_user(jwt)`.

---

## Dashboard Features & Institutional Access Control

The Airiva interface is structured as an institutional statistical portal modeled on central banks and national statistical bureaus (MoSPI, RBI, US BLS):

### Global Navigation Shell & Controls
- **Brand Identity**: Monogram emblem "A", "Airiva" brand title, and "Airfare Price Index" subtitle.
- **Cryptographic Authentication & RBAC**:
  - `Public / Guest`: Unauthenticated visitors can view Home, About, Real-Time Index visualizations, and summary aggregates. Microdata, heatmaps, and administration are hidden and protected by RLS.
  - `Statistical Analyst`: Accredited economists and auditors (MoSPI / RBI) gain access to Flight Search microdata, city-pair fare intensity heatmaps, analytical reports, and raw quotes.
  - `System Administrator`: Full console access to Scraper Trigger controls, live collection cycle dispatching, scrape execution telemetry, and User Provisioning.
- **Admin User Provisioning**:
  - Administrators can directly create and provision verified users with email, password, and assigned role (`analyst` or `admin`) via the System Console (`POST /v1/admin/create-user`).
  - Self-registration is strictly restricted to prevent unvetted access to microdata.
- **Theme Toggle**: Switch between **Light Mode** (warm paper & ink) and **Dark Mode** (deep slate & navy).
- **Status Ticker Bar**: Live pulse feed showing last scrape timestamp, current Composite Index reading (`104.22`), MoM change (`+1.4%`), and active quotes count.

### Page Breakdown
- **Page 1: Home (Institutional Overview)**: Hero statistics, national pilot corridor shares, and live index readings.
- **Page 2: About Airfare CPI (Methodology & Rationale)**: Mathematical derivation of the superlative Törnqvist formula, right-censoring retention, and DGCA Table 4.3 corridor weights.
- **Page 3: Real-Time Price Index (Cockpit)**: Multi-line Chart.js time-series, corridor zoom toggles, interactive route map, and MoSPI CPI overlay.
- **Page 4: Flight Search & Raw Microdata (Analyst & Admin)**: Multi-parameter query filter, right-censored sold-out indicators, and CSV exports.
- **Page 5: City-Pair Advance-Window Heatmaps (Analyst & Admin)**: Fare intensity matrix tracking lead times from T+60 to T+1.
- **Page 6: Reports & Data Export (Analyst & Admin)**: High-resolution printable MoSPI / RBI statistical bulletins and CSV downloads.
- **Page 7: REST API Documentation**: Interactive endpoint console and schemas.
- **Page 8: Data Sources & Compliance (Admin Only)**: System status, robots.txt compliance rules, and corridor weights.
- **Page 9: Scraper Control & User Management (Admin Only)**: Live scraper dispatch triggers, collection logs, and user provisioning console.
- **Page 10: Institutional Sign In**: Secure Supabase email + password authentication with MFA verification support.

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

python -m apix.scraper.runner
```

### Raw Scrape Storage & Data Sanitization
- **Supabase Private Storage Bucket**: All raw JSON payloads from carrier and OTA scrapers are uploaded to the private `"raw-scrapes"` bucket (`{source}/{YYYY-MM-DD}/{route}_{window}d.json`) using the service-role client.
- **Privacy & Token Sanitization**: Personal data, cookies, authentication headers, and session tokens are stripped prior to storage.
- **Local Dev Copy**: Local files in `data/raw/` are preserved only when `APP_ENV=development`.
- **Automated Retention Purge**: Delete files older than 90 days across local directories and Supabase Storage:
  ```powershell
  python scripts/purge_raw.py --days 90
  ```

> [!TIP]
> All scrapers obey a 2–8 second polite jitter delay, randomize User-Agent headers, check robots.txt prior to scraping, and adhere to [docs/ethical_scraping_policy.md](file:///c:/Akriti%20IMP/Airline%20imp/docs/ethical_scraping_policy.md).

---

## Automated Testing & Quality Verification

Run the test suite using `pytest`:

```powershell
cd "c:\Akriti IMP\Airline imp"

# Run all 91 automated tests
python -m pytest

# Run with verbose output and coverage report
python -m pytest -v --cov=Airiva --cov-report=term-missing
```

**Verification Results:**
- **91 passed (100% pass rate)**.
- **Pipeline Normalizer**: Tests XHR normalization for IndiGo, Air India, MakeMyTrip, and sold-out edge cases.
- **IQR Outlier Filter**: Validates upper/lower bound clipping and guarantees quotes are flagged rather than dropped.
- **Deduplication**: Validates flight-number matching, ensuring cheapest direct quote is preserved over OTA markups.
- **Törnqvist Engine**: Validates base period normalization (=100), log-change additivity, sample weighting, and rollups.
- **API Security & RBAC**: Validates token authentication, role extraction from `profiles`, endpoint permission barriers, rate limiting, and CORS headers.
- **Raw Storage**: Validates sensitive header/cookie stripping, privacy redaction, and 90-day retention purging.
- **Production Deployment Config**: Validates environment loading from `.env`, fail-fast on missing keys, and no secret leakage.

### Row Level Security (RLS) Verification
Prove database security rules using the browser-facing `SUPABASE_ANON_KEY`:
```powershell
python scripts/test_rls.py
```
Checks and verifies 22 distinct permission assertions:
- `GUEST`: Can read `index_values`, `routes`, `cpi_official`; cannot read `fare_quotes`, `scrape_log`, `audit_log`, `profiles`.
- `ANALYST`: Can read `fare_quotes` and `dgca_monthly_avg`; cannot read `scrape_log` or `audit_log`; reads only their own profile row.
- `ADMIN`: Can read `scrape_log`, `audit_log`, and all `profiles`.
- `WRITES`: Direct table inserts/updates/deletes from client roles fail unconditionally.

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
# Step A: Ingest and clean the official MoSPI workbook:
python scripts/load_cpi_official.py --xlsx data/cpi/cpi_1413.xlsx

# Step B: Run the benchmark comparison module:
python -m apix.backtest.cpi_benchmark --cpi-csv data/cpi/cpi_airfare_clean.csv --demo
```
Validation report: `data/benchmark/cpi_benchmark.json`.

---

## Hardened REST API Documentation

FastAPI runs with prefix `/v1`, server-side JWT verification, and strict rate limits:

| Method | Endpoint | Authorization | Description |
|:---:|:---|:---:|:---|
| `GET` | `/health` | Public | Platform health check (`{"status": "ok"}`) |
| `GET` | `/v1/index/daily` | Public | Time-series daily composite index and corridor sub-indices |
| `GET` | `/v1/index/weekly` | Public | Weekly geometric rollup records |
| `GET` | `/v1/index/monthly` | Public | Monthly geometric rollup records |
| `GET` | `/v1/index/route/{pair}` | Public | Route-specific index history |
| `GET` | `/v1/quotes` | Analyst / Admin | Filterable, paginated microdata quotes table |
| `GET` | `/v1/quotes/stats` | Analyst / Admin | Aggregated count, median fare, and outlier stats |
| `GET` | `/v1/quotes/corridor/{pair}` | Analyst / Admin | Corridor-specific flight quotes |
| `POST` | `/v1/admin/trigger-scrape` | Admin Only | Dispatch scrape cycle for configured sources |
| `POST` | `/v1/admin/create-user` | Admin Only | Directly provision user with email, password & role |
| `POST` | `/v1/admin/invite-user` | Admin Only | Invite user via Supabase Auth Admin |
| `GET` | `/v1/admin/scrape-log` | Admin Only | Paginated crawler telemetry and execution logs |
| `GET` | `/docs` | Public | Interactive Swagger UI API documentation |
| `GET` | `/redoc` | Public | Interactive ReDoc API documentation |

---

## Production Docker Deployment

Airiva includes a hardened container build using `python:3.12-slim` configured for non-root execution:

### 1. Build the Docker Image
```bash
docker build -t airiva-api:latest .
```

### 2. Run Container with Environment Variables
```bash
docker run -d \
  -p 8000:8000 \
  -e PORT=8000 \
  -e APP_ENV=production \
  -e SUPABASE_URL=https://kaljpvfcqsmanximfldz.supabase.co \
  -e SUPABASE_SERVICE_ROLE_KEY=your_service_role_key \
  -e ALLOWED_ORIGINS="http://localhost:3000,http://127.0.0.1:3000" \
  --name airiva-service \
  airiva-api:latest
```

### 3. Check Platform Health
```bash
curl http://localhost:8000/health
# Response: {"status":"ok"}
```

**Security Features in Container:**
- Runs as non-root user `appuser` (UID 10001).
- Does not bundle Playwright/Chromium in the API deployment container.
- Excludes sensitive files via [.dockerignore](file:///c:/Akriti%20IMP/Airline%20imp/.dockerignore) (`.env`, `.git`, `tests/`, `htmlcov/`, `data/raw/`).
- Dynamically respects the cloud provider `$PORT` variable.

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
uvicorn apix.api.main:app --port 8080 --reload
```

### Q: Supabase login returns 400 Bad Request
**A**: An HTTP 400 (`invalid_grant`) occurs when entering credentials that do not match Supabase Auth records. Ensure the account exists in Supabase or has been provisioned by an Administrator in the Admin Console.

### Q: How do I provision a new team member?
**A**: Log in with Administrator credentials, navigate to **System Console -> User Management**, and enter the new user's email, password, and assigned role (`analyst` or `admin`).

---

## License & Attribution

- **Source Code**: Released under the MIT License.
- **Data & Indices**: Published under the Open Database License ([ODbL](https://opendatacommons.org/licenses/odbl/)).
- **Official Statistics**: Based on Directorate General of Civil Aviation (DGCA) Government of India civil aviation statistics handbooks.
