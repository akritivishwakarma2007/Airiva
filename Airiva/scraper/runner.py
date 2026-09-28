"""
runner.py — CLI entrypoint and execution engine for flight fare scrapers.

Writes one scrape_log row per (source, route, window) attempt in Supabase,
covering both successes and failures, tracking status, records_collected, and errors.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from apix.config import settings
from apix.scraper.base import CaptchaDetectedError, RobotsBlockedError
from apix.scraper.robots_check import is_allowed

# Scraper implementations
from apix.scraper.indigo import IndiGoScraper
from apix.scraper.air_india import AirIndiaScraper
from apix.scraper.makemytrip import MakeMyTripScraper
from apix.scraper.akasa import AkasaScraper
from apix.scraper.spicejet import SpiceJetScraper

# Configure UTF-8 encoding on Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

SCRAPER_MAP = {
    "indigo": IndiGoScraper,
    "air_india": AirIndiaScraper,
    "makemytrip": MakeMyTripScraper,
    "akasa": AkasaScraper,
    "spicejet": SpiceJetScraper,
}


def _get_supabase_client():
    from supabase import create_client
    url = settings.supabase_url
    key = settings.supabase_service_role_key
    if not (url and key):
        return None
    return create_client(url, key)


def write_scrape_log(
    run_id: str,
    source: str,
    route: str,
    window: int | str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    records_collected: int = 0,
    error: Optional[str] = None,
) -> None:
    """Write an audit entry to public.scrape_log in Supabase."""
    client = _get_supabase_client()
    if client is None:
        return

    log_entry = {
        "run_id": run_id,
        "source": source,
        "route_code": route,
        "advance_window": f"T+{window}" if isinstance(window, int) else str(window),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "status": status,
        "records_collected": records_collected,
        "error": error[:950] if error else None,
    }

    try:
        client.table("scrape_log").insert(log_entry).execute()
    except Exception as exc:
        logger.error("Failed to write scrape_log entry: %s", exc)


async def execute_scrape_task(
    source_name: str,
    origin: str,
    destination: str,
    advance_days: int,
    run_id: str,
    headless: bool = True,
) -> Dict[str, Any]:
    """
    Execute a single scraper task for (source, route, window).
    Respects robots.txt, logs to scrape_log for both successes and failures.
    """
    route = f"{origin}-{destination}"
    scraper_cls = SCRAPER_MAP.get(source_name)
    started_at = datetime.now(tz=timezone.utc)

    # 1. Config check: refuse disabled sources
    if source_name not in settings.enabled_sources:
        finished_at = datetime.now(tz=timezone.utc)
        reason = f"Source '{source_name}' is disabled in settings"
        logger.info(reason)
        write_scrape_log(run_id, source_name, route, advance_days, started_at, finished_at, "disabled", 0, reason)
        return {"flights": [], "status": "disabled", "error": reason}

    if scraper_cls is None:
        finished_at = datetime.now(tz=timezone.utc)
        reason = f"Unknown scraper source: {source_name}"
        logger.error(reason)
        write_scrape_log(run_id, source_name, route, advance_days, started_at, finished_at, "error", 0, reason)
        return {"flights": [], "status": "error", "error": reason}

    scraper = scraper_cls()
    travel_date = date.today() + timedelta(days=advance_days)
    search_url = scraper._search_url(origin, destination, travel_date)

    # 2. robots.txt compliance check (never assume permission)
    allowed, robot_reason = is_allowed(search_url)
    if not allowed:
        finished_at = datetime.now(tz=timezone.utc)
        logger.warning("[%s] Skipping %s T+%d: %s", source_name, route, advance_days, robot_reason)
        write_scrape_log(run_id, source_name, route, advance_days, started_at, finished_at, "skipped", 0, robot_reason)
        return {"flights": [], "status": "skipped", "error": robot_reason}

    # 3. Perform scrape
    try:
        result = await scraper.scrape(origin, destination, travel_date, advance_days, headless=headless)
        flights = result.get("flights", [])
        finished_at = datetime.now(tz=timezone.utc)
        write_scrape_log(run_id, source_name, route, advance_days, started_at, finished_at, "success", len(flights), None)
        return result
    except (CaptchaDetectedError, RobotsBlockedError) as exc:
        finished_at = datetime.now(tz=timezone.utc)
        err_msg = str(exc)
        logger.warning("[%s] Scrape blocked for %s T+%d: %s", source_name, route, advance_days, err_msg)
        write_scrape_log(run_id, source_name, route, advance_days, started_at, finished_at, "blocked", 0, err_msg)
        return {"flights": [], "status": "blocked", "error": err_msg}
    except Exception as exc:
        finished_at = datetime.now(tz=timezone.utc)
        err_msg = str(exc)
        logger.error("[%s] Scrape failed for %s T+%d: %s", source_name, route, advance_days, err_msg, exc_info=True)
        write_scrape_log(run_id, source_name, route, advance_days, started_at, finished_at, "failed", 0, err_msg)
        return {"flights": [], "status": "failed", "error": err_msg}


async def run_collection_cycle(sources: Optional[List[str]] = None, headless: bool = True) -> int:
    """
    Run collection cycle for active sources, writing scrape_log for each attempt.
    """
    run_id = f"run_{date.today().isoformat()}_{uuid.uuid4().hex[:8]}"
    enabled = set(settings.enabled_sources)
    target_sources = [s for s in (sources or list(SCRAPER_MAP.keys())) if s in enabled]

    total_records = 0
    for source_name in target_sources:
        for origin, destination in settings.routes:
            for advance_days in settings.advance_windows:
                res = await execute_scrape_task(
                    source_name, origin, destination, advance_days, run_id=run_id, headless=headless
                )
                total_records += len(res.get("flights", []))

    return total_records


async def _dry_run() -> None:
    """Print robots.txt compliance status for all targets."""
    print("\n=== APIx Dry Run — robots.txt compliance check ===\n")
    travel_date = date.today() + timedelta(days=7)

    for source_name, scraper_cls in SCRAPER_MAP.items():
        if source_name not in settings.enabled_sources:
            print(f"  [{source_name}] DISABLED in settings\n")
            continue
        scraper = scraper_cls()
        for origin, destination in settings.routes:
            url = scraper._search_url(origin, destination, travel_date)
            allowed, reason = is_allowed(url)
            status = "✓ ALLOWED" if allowed else "✗ BLOCKED/UNCONFIRMED"
            print(f"  [{source_name}] {origin}→{destination}: {status}")
            print(f"    URL: {url}")
            print(f"    Reason: {reason}\n")

    print("=== Dry run complete — no data was fetched ===\n")


async def _single_run(args: argparse.Namespace) -> None:
    """Run one collection cycle or single task."""
    headless = not args.headed
    run_id = f"single_{uuid.uuid4().hex[:8]}"

    if args.source and args.route and args.window:
        origin, destination = args.route.split("-")
        advance_days = args.window
        print(f"Scraping {args.source} for {args.route} T+{advance_days} (headless={headless})...")
        res = await execute_scrape_task(args.source, origin, destination, advance_days, run_id=run_id, headless=headless)
        flights = res.get("flights", [])
        status = res.get("status", "unknown")
        print(f"✓ Task finished ({status}): Captured {len(flights)} flight quotes.")
    else:
        sources = [args.source] if args.source else None
        total = await run_collection_cycle(sources=sources, headless=headless)
        print(f"✓ Collection cycle completed: {total} total records captured.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="APIx Scraper Runner")
    parser.add_argument("--single-run", action="store_true", help="Run once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Check robots.txt only, no scraping")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser window")
    parser.add_argument("--source", default=None, help="Specific source: indigo | air_india | makemytrip | akasa | spicejet")
    parser.add_argument("--route", default=None, help="Specific route: e.g. DEL-BOM")
    parser.add_argument("--window", type=int, default=None, help="Advance window days: 1, 7, 15, 30, 45")
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    if args.dry_run:
        await _dry_run()
    elif args.single_run or (args.source and args.route and args.window):
        await _single_run(args)
    else:
        from apix.scraper.scheduler import build_scheduler
        scheduler = build_scheduler()
        scheduler.start()
        logger.info("Scheduler started. Press Ctrl+C to exit.")
        try:
            while True:
                await asyncio.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()
            logger.info("Scheduler stopped.")


if __name__ == "__main__":
    asyncio.run(main())
