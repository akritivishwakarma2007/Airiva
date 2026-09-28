# Setup Instructions

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | Tested on 3.11 and 3.12 |
| Docker Desktop | 4.x+ | For TimescaleDB |
| Docker Compose | v2+ | Bundled with Docker Desktop |
| Ghostscript | Any | Required by camelot-py for PDF parsing |

---

## Step-by-Step Setup

### 1. Configure environment

```powershell
cd "c:\Airline imp"
copy .env.example .env
```

Edit `.env` as needed — defaults work for local development with Docker.

---

### 2. Start TimescaleDB

```powershell
docker-compose up -d timescaledb
```

Wait for the container to become healthy:

```powershell
docker-compose ps
# STATUS should show "healthy" for timescaledb
```

The `scripts/init_db.sql` file is run automatically on first start and
creates all hypertables, indices, and tables.

Optional — start PgAdmin for a DB browser:

```powershell
docker-compose --profile tools up -d pgadmin
# Access at http://localhost:5050
# Email: admin@apix.local  Password: admin (from .env)
```

---

### 3. Install Python dependencies

```powershell
pip install -r requirements.txt
```

Install Playwright Chromium browser:

```powershell
playwright install chromium
```

Install Ghostscript (for camelot PDF parsing):
- Windows: https://www.ghostscript.com/releases/gsdnld.html
- Install and ensure `gswin64c.exe` is on PATH

---

### 4. Verify installation

```powershell
# Check DB connectivity
python -c "
import asyncio
from apix.pipeline.db import AsyncSessionLocal
from sqlalchemy import text
async def check():
    async with AsyncSessionLocal() as s:
        r = await s.execute(text('SELECT version()'))
        print('DB OK:', r.scalar())
asyncio.run(check())
"
```

---

### 5. Load seed data (dev mode — no scraping)

```powershell
python -c "
import asyncio
from apix.pipeline.loader import load_csv
from pathlib import Path
asyncio.run(load_csv(Path('data/seed/synthetic_fares.csv')))
"
```

---

### 6. Compute the index

```powershell
python -m apix.index_engine.runner
```

---

### 7. Start the API + Dashboard

```powershell
uvicorn apix.api.main:app --host 0.0.0.0 --port 8000 --reload
```

| URL | Description |
|-----|-------------|
| http://localhost:8000/ | API root |
| http://localhost:8000/dashboard | Live dashboard |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/health | Health check |

---

### 8. Run the scraper (optional — requires live internet)

Check robots.txt compliance before any live scraping:

```powershell
python -m apix.scraper.runner --dry-run
```

Run a single immediate collection:

```powershell
python -m apix.scraper.runner --single-run
```

Start the daily scheduler (runs at 2am IST = 20:30 UTC):

```powershell
python -m apix.scraper.runner
```

---

### 9. Run the backtest

1. Download DGCA monthly statistics PDFs from:
   - https://www.dgca.gov.in → Data & Reports → Civil Aviation Statistics Handbook
   - Place downloaded PDFs in `apix/backtest/data/`

2. Run the report:

```powershell
python -m apix.backtest.report
# Chart saved to: data/backtest_report.png
```

Without real PDFs (uses synthetic reference data):

```powershell
python -m apix.backtest.report --use-synthetic
```

---

### 10. Run tests

```powershell
pytest tests/ -v
# With coverage:
pytest tests/ --cov=apix --cov-report=html
# Open htmlcov/index.html in a browser to view coverage
```

---

## Troubleshooting

### `asyncpg.exceptions.ConnectionRefusedError`
TimescaleDB container is not running or not yet healthy.
```powershell
docker-compose ps      # check status
docker-compose logs timescaledb  # check startup logs
```

### `playwright._impl._errors.Error: Executable doesn't exist`
```powershell
playwright install chromium
```

### Scraper gets no data / empty JSON
The target site's XHR pattern may have changed. Enable debug logging:
```powershell
# In .env:
LOG_LEVEL=DEBUG
```
Then check the logged intercepted URLs against the `_intercept_predicate()`
method in the relevant scraper class.

### camelot fails with Ghostscript error
Ensure Ghostscript is installed and `gswin64c` is on your system PATH.
Alternatively, the DGCA parser falls back to pdfplumber automatically.

---

## Stopping / Cleanup

```powershell
# Stop API
Ctrl+C

# Stop DB container (data preserved in Docker volume)
docker-compose down

# Full cleanup (removes DB data):
docker-compose down -v
```
