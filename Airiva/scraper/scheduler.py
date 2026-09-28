"""
scheduler.py — APScheduler daily collection job.

Full basket: 30 routes × 5 sources × 5 windows = 750 requests/day.
Runs daily, spread across 20:30–23:30 UTC (2:00–5:00 AM IST) to respect
per-domain rate limits (2–8 s polite delay) without back-to-back bursts.

Architecture note (GitHub Actions runtime):
  750 requests × avg 5 s delay + Playwright overhead ≈ 70-90 min.
  GitHub Actions free-tier hard-limits jobs at 6 hours, so this fits.
  If scraping is extended further (e.g. >1500 req/day), migrate the
  scheduler to a Render background worker (always-on, no job time limit).
  Flag is set in logs: WARN 'runtime_risk=high' if estimated duration > 300 min.

Each task is run sequentially within a source to respect per-domain rate
caps. Different sources run concurrently via asyncio.gather().
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from apix.config import settings
from apix.scraper.base import CaptchaDetectedError, RobotsBlockedError
from apix.scraper.indigo import IndiGoScraper
from apix.scraper.air_india import AirIndiaScraper
from apix.scraper.makemytrip import MakeMyTripScraper
from apix.scraper.akasa import AkasaScraper
from apix.scraper.spicejet import SpiceJetScraper

logger = logging.getLogger(__name__)

# Map source names to scraper classes
_SCRAPERS = {
    "indigo": IndiGoScraper,
    "air_india": AirIndiaScraper,
    "makemytrip": MakeMyTripScraper,
    "akasa": AkasaScraper,
    "spicejet": SpiceJetScraper,
}


async def _run_source(source_name: str, advance_days: int, run_id: str | None = None) -> list[dict]:
    """
    Run one source for all routes at a given advance window.
    Routes are run sequentially within a source to respect rate caps.
    Logs each attempt to public.scrape_log.
    """
    if source_name not in settings.enabled_sources:
        logger.info("Source '%s' disabled — skipping", source_name)
        return []

    from apix.scraper.runner import execute_scrape_task
    current_run_id = run_id or f"sched_{date.today().isoformat()}"
    results = []

    for origin, destination in settings.routes:
        result = await execute_scrape_task(
            source_name, origin, destination, advance_days, run_id=current_run_id
        )
        results.append(result)

    return results


async def run_daily_collection() -> None:
    """
    Main collection job: runs all sources × windows concurrently.
    Called by APScheduler each day.
    """
    n_sources = len([s for s in _SCRAPERS if s in settings.enabled_sources])
    n_routes = len(settings.routes)
    n_windows = len(settings.advance_windows)
    total_tasks = n_sources * n_routes * n_windows
    # Conservative estimate: avg 5s delay + 15s Playwright overhead per task
    est_minutes = total_tasks * 20 / 60
    if est_minutes > 300:
        logger.warning(
            "runtime_risk=high: estimated %.0f min for %d tasks "
            "(%d sources × %d routes × %d windows). "
            "Consider migrating to Render background worker.",
            est_minutes, total_tasks, n_sources, n_routes, n_windows,
        )
    else:
        logger.info(
            "=== APIx daily collection started: %d tasks (%d sources × %d routes × %d windows), "
            "est. %.0f min ===",
            total_tasks, n_sources, n_routes, n_windows, est_minutes,
        )

    run_id = f"daily_{date.today().isoformat()}"
    tasks = []
    for source_name in _SCRAPERS:
        for advance_days in settings.advance_windows:
            tasks.append(_run_source(source_name, advance_days, run_id=run_id))

    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    total_flights = 0
    for res in all_results:
        if isinstance(res, list):
            for r in res:
                total_flights += len(r.get("flights", []))

    logger.info(
        "=== APIx daily collection complete — %d total flight records ===",
        total_flights,
    )

    # Trigger pipeline after collection
    try:
        from apix.pipeline.loader import load_raw_today
        await load_raw_today()
    except Exception as exc:
        logger.error("Pipeline loader failed: %s", exc, exc_info=True)

    # Trigger index computation
    try:
        from apix.index_engine.runner import compute_today
        await compute_today()
    except Exception as exc:
        logger.error("Index computation failed: %s", exc, exc_info=True)


def build_scheduler() -> AsyncIOScheduler:
    """Build and return a configured APScheduler instance (not yet started)."""
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Parse COLLECTION_CRON string into CronTrigger fields
    cron_parts = settings.collection_cron.split()
    if len(cron_parts) == 5:
        minute, hour, day, month, day_of_week = cron_parts
    else:
        logger.warning("Invalid COLLECTION_CRON '%s'; defaulting to 20:30 UTC", settings.collection_cron)
        minute, hour, day, month, day_of_week = "30", "20", "*", "*", "*"

    scheduler.add_job(
        run_daily_collection,
        trigger=CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
        ),
        id="daily_collection",
        name="APIx Daily Fare Collection",
        replace_existing=True,
        misfire_grace_time=3600,  # Allow up to 1hr late start
    )
    logger.info("Scheduler configured: cron='%s' UTC", settings.collection_cron)
    return scheduler
