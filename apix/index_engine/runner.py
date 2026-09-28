"""
runner.py — Computes and stores index values reading from and writing to Supabase.

1. Reads route weights from public.routes (seeds if missing).
2. Reads fare_quotes from Supabase, excluding is_outlier, is_duplicate, or sold_out
   rows from the median calculation (while keeping them stored in the database).
3. Computes Törnqvist index per day, aggregates to weekly and monthly series.
4. Upserts index values into public.index_values with on_conflict on (date, granularity, route_code).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from apix.config import settings
from apix.index_engine.aggregator import aggregate_monthly, aggregate_weekly
from apix.index_engine.tornqvist import (
    IndexResult,
    RoutePriceData,
    build_route_price_data,
    compute_tornqvist,
)
from apix.index_engine.weights import load_weights

logger = logging.getLogger(__name__)


def _get_supabase_client():
    from supabase import create_client
    url = settings.supabase_url
    key = settings.supabase_service_role_key
    if not (url and key):
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment.")
    return create_client(url, key)


def _load_supabase_weights(client) -> Tuple[Dict[str, float], List[str]]:
    """Fetch route weights from Supabase routes table. Seed from CSV if empty."""
    res = client.table("routes").select("route_code, weight").execute()
    data = res.data or []

    if not data:
        logger.info("routes table in Supabase is empty. Seeding from weights file...")
        csv_weights = load_weights()
        rows = [{"route_code": r, "weight": w} for r, w in csv_weights.items()]
        client.table("routes").upsert(rows, on_conflict="route_code").execute()
        return csv_weights, list(csv_weights.keys())

    weights = {r["route_code"]: float(r["weight"]) for r in data}
    return weights, list(weights.keys())


def _fetch_supabase_fares(
    client, from_date: Optional[date] = None, to_date: Optional[date] = None
) -> Dict[date, Dict[str, List[float]]]:
    """
    Fetch all fare quotes from Supabase, excluding outlier, duplicate, and sold_out rows
    from the pricing pool.

    Returns:
        {scrape_date: {route_code: [total_fare, ...]}}
    """
    page_size = 1000
    start = 0
    all_quotes = []

    while True:
        q = client.table("fare_quotes").select(
            "route_code, total_fare, scrape_date, is_outlier, is_duplicate, sold_out"
        )
        if from_date:
            q = q.gte("scrape_date", str(from_date))
        if to_date:
            q = q.lte("scrape_date", str(to_date))

        res = q.order("id").range(start, start + page_size - 1).execute()
        batch = res.data or []
        if not batch:
            break
        all_quotes.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size

    logger.info("Retrieved %d raw fare quotes from Supabase", len(all_quotes))

    fares_by_date_route: Dict[date, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    excluded_count = 0
    valid_count = 0

    for q in all_quotes:
        # Exclude outlier, duplicate, or sold_out rows from median
        is_outlier = bool(q.get("is_outlier"))
        is_duplicate = bool(q.get("is_duplicate"))
        sold_out = bool(q.get("sold_out"))

        if is_outlier or is_duplicate or sold_out:
            excluded_count += 1
            continue

        valid_count += 1
        s_date = date.fromisoformat(str(q["scrape_date"]))
        route = str(q["route_code"]).strip().upper()
        fare = float(q["total_fare"])
        fares_by_date_route[s_date][route].append(fare)

    logger.info("Valid quotes for index: %d (excluded %d flagged outliers/duplicates/sold_out)", valid_count, excluded_count)
    return fares_by_date_route


def _upsert_index_values_supabase(client, records: List[Dict[str, Any]]) -> int:
    """Upsert calculated index records into public.index_values in chunks of 500."""
    if not records:
        return 0

    chunk_size = 500
    total_upserted = 0
    conflict_cols = "date,granularity,route_code"

    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        client.table("index_values").upsert(chunk, on_conflict=conflict_cols).execute()
        total_upserted += len(chunk)

    return total_upserted


async def compute_range_supabase(from_date: Optional[date] = None, to_date: Optional[date] = None) -> None:
    """Compute daily, weekly, and monthly Törnqvist indices and upsert to Supabase."""
    client = _get_supabase_client()
    weights, active_routes = _load_supabase_weights(client)
    fares_by_date = _fetch_supabase_fares(client, from_date, to_date)

    if not fares_by_date:
        logger.warning("No fare quotes found in Supabase to compute index.")
        print("No fare quotes found in Supabase. index_values row count: 0")
        return

    available_dates = sorted(fares_by_date.keys())
    base_date = available_dates[0]
    base_fares = {r: fares_by_date[base_date].get(r, []) for r in active_routes}
    base_data = build_route_price_data(base_fares, weights)

    daily_db_records: List[Dict[str, Any]] = []
    daily_results_for_aggregation: List[Dict[str, Any]] = []

    for d in available_dates:
        day_fares = {r: fares_by_date[d].get(r, []) for r in active_routes}
        total_fares = sum(len(f) for f in day_fares.values())
        if total_fares == 0:
            continue

        current_data = build_route_price_data(day_fares, weights)
        result: IndexResult = compute_tornqvist(base_data, current_data)

        # 1. Composite daily index
        daily_db_records.append({
            "date": str(d),
            "granularity": "daily",
            "route_code": None,
            "index_value": round(float(result.index_value), 4),
        })

        # 2. Per-route daily indices
        for route_code, val in result.route_values.items():
            if val is not None and val > 0:
                daily_db_records.append({
                    "date": str(d),
                    "granularity": "daily",
                    "route_code": route_code,
                    "index_value": round(float(val), 4),
                })

        daily_results_for_aggregation.append({
            "index_date": d,
            "index_value": float(result.index_value),
            "del_bom": float(result.route_values.get("DEL-BOM", 0)) or None,
            "del_blr": float(result.route_values.get("DEL-BLR", 0)) or None,
            "bom_blr": float(result.route_values.get("BOM-BLR", 0)) or None,
            "sample_size": result.sample_size,
        })

    # Weekly aggregates
    weekly_agg = aggregate_weekly(daily_results_for_aggregation)
    weekly_db_records: List[Dict[str, Any]] = []
    for w in weekly_agg:
        weekly_db_records.append({
            "date": str(w["week_start_date"]),
            "granularity": "weekly",
            "route_code": None,
            "index_value": round(float(w["index_value"]), 4),
        })

    # Monthly aggregates
    monthly_agg = aggregate_monthly(daily_results_for_aggregation)
    monthly_db_records: List[Dict[str, Any]] = []
    for m in monthly_agg:
        monthly_date = date(m["year"], m["month"], 1)
        monthly_db_records.append({
            "date": str(monthly_date),
            "granularity": "monthly",
            "route_code": None,
            "index_value": round(float(m["index_value"]), 4),
        })

    all_index_records = daily_db_records + weekly_db_records + monthly_db_records
    n_upserted = _upsert_index_values_supabase(client, all_index_records)

    # Fetch final counts from Supabase
    quotes_count = client.table("fare_quotes").select("*", count="exact").limit(1).execute().count
    index_count = client.table("index_values").select("*", count="exact").limit(1).execute().count

    print("\n" + "=" * 50)
    print(" INDEX ENGINE RUNNER SUMMARY")
    print(f" Daily index records:   {len(daily_db_records)}")
    print(f" Weekly index records:  {len(weekly_db_records)}")
    print(f" Monthly index records: {len(monthly_db_records)}")
    print(f" Total upserted:        {n_upserted}")
    print(f" Current fare_quotes in Supabase: {quotes_count}")
    print(f" Current index_values in Supabase: {index_count}")
    print("=" * 50 + "\n")


async def compute_range_sqlite(from_date: date, to_date: date) -> None:
    """Local SQLite fallback for unit tests."""
    from apix.pipeline.db import AsyncSessionLocal, ApixDaily, ApixMonthly, ApixWeekly, FareQuote, _is_sqlite
    from apix.index_engine.weights import get_active_routes
    from sqlalchemy import select
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    weights = load_weights()
    active_routes = get_active_routes(weights)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(FareQuote.origin, FareQuote.destination, FareQuote.total_fare, FareQuote.scrape_date)
            .where(
                FareQuote.is_censored.is_(False),
                FareQuote.is_outlier.is_(False),
                FareQuote.is_duplicate.is_(False),
            )
            .order_by(FareQuote.scrape_date)
        )
        rows = result.fetchall()

    if not rows:
        return

    by_date: dict[date, dict[str, list[float]]] = defaultdict(lambda: {r: [] for r in active_routes})
    for origin, destination, fare, sd in rows:
        key = f"{origin}-{destination}"
        if key in active_routes:
            by_date[sd][key].append(float(fare))

    first_date = min(by_date.keys())
    base_data = build_route_price_data(by_date[first_date], weights)

    daily_results = []
    current = from_date
    while current <= to_date:
        if current in by_date:
            cur_data = build_route_price_data(by_date[current], weights)
            res = compute_tornqvist(base_data, cur_data)
            rec = {
                "index_date": current,
                "index_value": float(res.index_value),
                "del_bom": float(res.route_values.get("DEL-BOM", 0)) or None,
                "del_blr": float(res.route_values.get("DEL-BLR", 0)) or None,
                "bom_blr": float(res.route_values.get("BOM-BLR", 0)) or None,
                "sample_size": res.sample_size,
            }
            stmt = sqlite_insert(ApixDaily).values([rec])
            stmt = stmt.on_conflict_do_update(
                index_elements=["index_date"],
                set_={k: stmt.excluded[k] for k in ["index_value", "del_bom", "del_blr", "bom_blr", "sample_size"]},
            )
            async with AsyncSessionLocal() as session:
                await session.execute(stmt)
                await session.commit()
            daily_results.append(rec)
        current += timedelta(days=1)

    weekly = aggregate_weekly(daily_results)
    monthly = aggregate_monthly(daily_results)

    if weekly:
        w_stmt = sqlite_insert(ApixWeekly).values(weekly)
        w_stmt = w_stmt.on_conflict_do_update(
            index_elements=["iso_year", "iso_week"],
            set_={"index_value": w_stmt.excluded.index_value},
        )
        async with AsyncSessionLocal() as session:
            await session.execute(w_stmt)
            await session.commit()

    if monthly:
        m_stmt = sqlite_insert(ApixMonthly).values(monthly)
        m_stmt = m_stmt.on_conflict_do_update(
            index_elements=["year", "month"],
            set_={"index_value": m_stmt.excluded.index_value},
        )
        async with AsyncSessionLocal() as session:
            await session.execute(m_stmt)
            await session.commit()


async def compute_today() -> None:
    """Compute index for today."""
    if os.environ.get("USE_SQLITE") == "1":
        await compute_range_sqlite(date.today(), date.today())
    else:
        await compute_range_supabase(date.today(), date.today())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="APIx Index Engine Runner (Supabase)")
    parser.add_argument("--from", dest="from_date", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", default=None, help="End date YYYY-MM-DD")
    parser.add_argument("--date", dest="single_date", default=None, help="Single date YYYY-MM-DD")
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    if os.environ.get("USE_SQLITE") == "1":
        if args.single_date:
            d = date.fromisoformat(args.single_date)
            await compute_range_sqlite(d, d)
        elif args.from_date:
            await compute_range_sqlite(date.fromisoformat(args.from_date), date.today())
        else:
            await compute_today()
        return

    # Supabase execution
    f_date = date.fromisoformat(args.from_date) if args.from_date else None
    t_date = date.fromisoformat(args.to_date) if args.to_date else None
    if args.single_date:
        d = date.fromisoformat(args.single_date)
        f_date, t_date = d, d

    await compute_range_supabase(f_date, t_date)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(main())
