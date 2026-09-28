"""
loader.py — Reads raw fare data (JSON/CSV), runs the pipeline, and upserts into Supabase.

Pipeline chain:
  raw data → normalize() → apply_iqr_filter() → deduplicate() → Supabase upsert (batch 500)

Entry points:
  load_raw_today()    — process all raw files from today's scrape run
  load_raw_file(path) — process a single raw JSON file (useful for backfill)
  load_csv(path)      — load from synthetic CSV (dev/test/seed)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from apix.config import settings
from apix.index_engine.weights import load_weights
from apix.pipeline.deduplicator import deduplicate
from apix.pipeline.normalizer import normalize
from apix.pipeline.outlier_filter import apply_iqr_filter
from apix.pipeline.schema import FareRecord

logger = logging.getLogger(__name__)

# Unique conflict key constraint for fare_quotes
CONFLICT_COLUMNS = "source,flight_number,travel_date,fare_class,advance_purchase_days,scrape_date"


def _get_supabase_client():
    """Create Supabase client using service role key from environment."""
    from supabase import create_client
    url = settings.supabase_url
    key = settings.supabase_service_role_key
    if not (url and key):
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment.")
    return create_client(url, key)


def _ensure_routes(client, route_codes: set[str]) -> None:
    """Ensure foreign key target routes exist in public.routes table."""
    if not route_codes:
        return
    weights = load_weights()
    routes_to_upsert = [
        {
            "route_code": r,
            "weight": weights.get(r, 1.0 / max(len(route_codes), 1)),
        }
        for r in route_codes
    ]
    try:
        client.table("routes").upsert(routes_to_upsert, on_conflict="route_code").execute()
    except Exception as exc:
        logger.warning("Could not pre-populate routes table: %s", exc)


async def _upsert_records_sqlite(records: List[FareRecord]) -> Tuple[int, int]:
    """Fallback local SQLite upsert for local unit testing only."""
    from apix.pipeline.db import AsyncSessionLocal, FareQuote, init_db
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    if not records:
        return 0, 0

    await init_db()
    rows = [
        {
            "scrape_timestamp": r.scrape_timestamp,
            "scrape_date": r.scrape_date,
            "origin": r.origin,
            "destination": r.destination,
            "carrier": r.carrier,
            "flight_number": r.flight_number,
            "travel_date": r.travel_date,
            "advance_purchase_days": r.advance_purchase_days,
            "fare_class": r.fare_class,
            "base_fare": r.base_fare,
            "taxes_fees": r.taxes_fees,
            "total_fare": r.total_fare,
            "seats_available": r.seats_available,
            "source": r.source,
            "is_censored": r.is_censored,
            "is_outlier": r.is_outlier,
            "is_duplicate": r.is_duplicate,
            "raw_file_path": r.raw_file_path,
        }
        for r in records
    ]

    conflict_cols = ["flight_number", "travel_date", "fare_class", "source", "scrape_date"]
    update_cols = [
        "total_fare", "base_fare", "taxes_fees", "seats_available",
        "is_censored", "is_outlier", "is_duplicate", "scrape_timestamp",
    ]
    stmt = sqlite_insert(FareQuote).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=conflict_cols,
        set_={k: stmt.excluded[k] for k in update_cols},
    )

    async with AsyncSessionLocal() as session:
        await session.execute(stmt)
        await session.commit()

    return len(rows), 0


def _upsert_records_supabase(records: List[FareRecord]) -> Tuple[int, int]:
    """
    Upsert cleaned FareRecord list into public.fare_quotes in Supabase.
    Batches in chunks of 500 rows.
    Returns (loaded_count, rejected_count).
    """
    if not records:
        return 0, 0

    client = _get_supabase_client()

    # Pre-populate routes to satisfy foreign key constraint
    distinct_routes = {f"{r.origin.upper()}-{r.destination.upper()}" for r in records}
    _ensure_routes(client, distinct_routes)

    rows: List[Dict[str, Any]] = []
    rejected_count = 0

    for r in records:
        try:
            route_code = f"{r.origin.upper()}-{r.destination.upper()}"
            row = {
                "route_code": route_code,
                "source": str(r.source).strip().lower(),
                "carrier": str(r.carrier).strip().upper() if r.carrier else None,
                "flight_number": str(r.flight_number).strip().upper(),
                "travel_date": str(r.travel_date),
                "scrape_date": str(r.scrape_date),
                "scrape_timestamp": r.scrape_timestamp.isoformat(),
                "advance_purchase_days": int(r.advance_purchase_days),
                "fare_class": str(r.fare_class).strip().upper() if r.fare_class else "SAVER",
                "base_fare": float(r.base_fare) if r.base_fare is not None else None,
                "taxes_fees": float(r.taxes_fees) if r.taxes_fees is not None else None,
                "total_fare": float(r.total_fare),
                "seats_available": int(r.seats_available) if r.seats_available is not None else None,
                "sold_out": bool(r.is_censored),
                "is_outlier": bool(r.is_outlier),
                "is_duplicate": bool(r.is_duplicate),
            }
            rows.append(row)
        except Exception as exc:
            rejected_count += 1
            logger.warning("Rejected row during serialization: %s — Reason: %s", r, exc)

    chunk_size = 500
    loaded_count = 0

    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        try:
            client.table("fare_quotes").upsert(chunk, on_conflict=CONFLICT_COLUMNS).execute()
            loaded_count += len(chunk)
        except Exception as exc:
            logger.warning("Batch upsert failed for chunk %d..%d: %s. Falling back to row-by-row.", i, i + len(chunk), exc)
            for item in chunk:
                try:
                    client.table("fare_quotes").upsert([item], on_conflict=CONFLICT_COLUMNS).execute()
                    loaded_count += 1
                except Exception as item_exc:
                    rejected_count += 1
                    logger.warning(
                        "Rejected row during database upsert: flight=%s, date=%s — Reason: %s",
                        item.get("flight_number"), item.get("travel_date"), item_exc,
                    )

    return loaded_count, rejected_count


async def _upsert_records(records: List[FareRecord]) -> Tuple[int, int]:
    """
    Entrypoint for upserting records.
    Uses Supabase by default; falls back to SQLite only if USE_SQLITE=1 is set.
    """
    if os.environ.get("USE_SQLITE") == "1":
        return await _upsert_records_sqlite(records)
    return _upsert_records_supabase(records)


def _run_pipeline(raw: dict) -> Tuple[List[FareRecord], int]:
    """Full pipeline: normalize → IQR filter → dedup."""
    records = normalize(raw)
    records = apply_iqr_filter(records)
    records = deduplicate(records)
    return records, 0


async def load_raw_file(path: Path) -> int:
    """Load a single raw JSON file through the pipeline and upsert to Supabase."""
    logger.info("Loading raw file: %s", path)
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    raw_str = str(path)
    records, prep_rejected = _run_pipeline(raw)
    read_count = len(records) + prep_rejected
    for r in records:
        r.__dict__["raw_file_path"] = raw_str

    loaded, upsert_rejected = await _upsert_records(records)
    total_rejected = prep_rejected + upsert_rejected

    print("\n" + "=" * 50)
    print(" PIPELINE LOADER SUMMARY")
    print(f" Read:     {read_count}")
    print(f" Loaded:   {loaded}")
    print(f" Rejected: {total_rejected}")
    print("=" * 50 + "\n")

    return loaded


async def load_raw_today() -> int:
    """Process all raw JSON files written today (by all sources)."""
    today = date.today().isoformat()
    raw_dir = Path(settings.raw_data_dir)
    total = 0

    if not raw_dir.exists():
        logger.info("Raw data directory does not exist: %s", raw_dir)
        return 0

    for source_dir in raw_dir.iterdir():
        if not source_dir.is_dir():
            continue
        date_dir = source_dir / today
        if not date_dir.is_dir():
            continue
        for json_file in date_dir.glob("*.json"):
            try:
                total += await load_raw_file(json_file)
            except Exception as exc:
                logger.error("Failed to load %s: %s", json_file, exc, exc_info=True)

    logger.info("load_raw_today: %d total records loaded", total)
    return total


async def load_csv(path: Path) -> int:
    """
    Load synthetic/seed CSV into the pipeline and upsert to Supabase.
    Logs warning for every rejected row and prints a final read / loaded / rejected summary.
    """
    logger.info("Loading CSV seed data: %s", path)
    df = pd.read_csv(path)
    read_count = len(df)

    records: List[FareRecord] = []
    rejected_count = 0

    now = datetime.now(tz=timezone.utc)

    for idx, row in df.iterrows():
        try:
            t_date = pd.to_datetime(row["travel_date"]).date()
            adv = int(row["advance_purchase_days"])
            if "scrape_date" in row and pd.notna(row["scrape_date"]):
                s_date = pd.to_datetime(row["scrape_date"]).date()
            else:
                s_date = t_date - timedelta(days=adv)

            rec = FareRecord(
                origin=str(row["origin"]).strip().upper(),
                destination=str(row["destination"]).strip().upper(),
                carrier=str(row["carrier"]).strip().upper(),
                flight_number=str(row["flight_number"]).strip().upper(),
                travel_date=t_date,
                scrape_timestamp=datetime(s_date.year, s_date.month, s_date.day, 2, 0, 0, tzinfo=timezone.utc),
                scrape_date=s_date,
                advance_purchase_days=adv,
                fare_class=str(row["fare_class"]).strip().upper() if pd.notna(row.get("fare_class")) else "SAVER",
                base_fare=float(row["base_fare"]) if pd.notna(row.get("base_fare")) else None,
                taxes_fees=float(row["taxes_fees"]) if pd.notna(row.get("taxes_fees")) else None,
                total_fare=float(row["total_fare"]),
                seats_available=int(row["seats_available"]) if pd.notna(row.get("seats_available")) else None,
                source=str(row["source"]).strip().lower(),
            )
            records.append(rec)
        except Exception as exc:
            rejected_count += 1
            logger.warning("Rejected row in CSV (row #%d): %s — Reason: %s", idx, dict(row), exc)

    records = apply_iqr_filter(records)
    records = deduplicate(records)

    loaded, upsert_rejected = await _upsert_records(records)
    total_rejected = rejected_count + upsert_rejected

    print("\n" + "=" * 50)
    print(" PIPELINE LOADER SUMMARY")
    print(f" Read:     {read_count}")
    print(f" Loaded:   {loaded}")
    print(f" Rejected: {total_rejected}")
    print("=" * 50 + "\n")

    return loaded


if __name__ == "__main__":
    import argparse
    import asyncio

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="APIx Pipeline Loader (Supabase)")
    parser.add_argument("--csv", default="data/seed/synthetic_fares.csv", help="Path to seed CSV")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"Error: file not found: {csv_path}")
        exit(1)

    loaded_rows = asyncio.run(load_csv(csv_path))
