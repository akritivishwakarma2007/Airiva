"""
base.py — Abstract base class for all scrapers.

Each concrete scraper (IndiGo, Air India, MakeMyTrip) inherits from
BaseScraper and implements:
  - ``_search_url(origin, destination, travel_date)`` → str
  - ``_intercept_predicate(url)`` → bool   (XHR filter)
  - ``_parse_response(raw_json, origin, destination, travel_date, advance_days)`` → dict

Public interface (used by scheduler):
  scrape(origin, destination, travel_date, advance_days) → dict
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Any

from playwright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    Response,
    async_playwright,
)

from apix.config import settings
from apix.scraper.robots_check import is_allowed
from apix.scraper.user_agents import get_random_ua

logger = logging.getLogger(__name__)

# Strings that indicate a CAPTCHA/challenge page has been presented
_CAPTCHA_SIGNALS = [
    "captcha",
    "cf-challenge",
    "are you a robot",
    "unusual traffic",
    "security check",
    "verify you are human",
    "datadome",
]


class CaptchaDetectedError(RuntimeError):
    """Raised when a CAPTCHA challenge page is detected."""


class RobotsBlockedError(RuntimeError):
    """Raised when robots.txt disallows the target URL."""


class BaseScraper(ABC):
    """
    Common scaffolding for all three source scrapers.

    Subclasses must implement the three abstract methods below.
    """

    #: Override in subclass — e.g. "https://www.goindigo.in"
    BASE_URL: str = ""
    #: Human-readable source name used in file paths and DB records
    SOURCE_NAME: str = ""

    def __init__(self) -> None:
        if not self.BASE_URL or not self.SOURCE_NAME:
            raise NotImplementedError("Subclass must set BASE_URL and SOURCE_NAME")

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def _search_url(self, origin: str, destination: str, travel_date: date) -> str:
        """Return the URL that triggers the flight-search SPA page."""

    @abstractmethod
    def _intercept_predicate(self, url: str) -> bool:
        """Return True if *url* is the XHR/fetch response we want to capture."""

    @abstractmethod
    def _parse_response(
        self,
        raw_json: Any,
        origin: str,
        destination: str,
        travel_date: date,
        advance_days: int,
    ) -> dict:
        """
        Transform the raw XHR JSON into the standard storage dict.
        Return value is persisted as-is to the raw JSON dump file.
        """

    # ── Public interface ──────────────────────────────────────────────────────

    async def scrape(
        self,
        origin: str,
        destination: str,
        travel_date: date,
        advance_days: int,
        headless: bool | None = None,
    ) -> dict:
        """
        Execute a scrape for one route/window combination.

        Returns the parsed dict (also written to disk).
        Raises CaptchaDetectedError or RobotsBlockedError on failures.
        """
        search_url = self._search_url(origin, destination, travel_date)

        # ── robots.txt pre-flight ─────────────────────────────────────────────
        ua = get_random_ua()
        allowed, reason = is_allowed(search_url, user_agent="*")
        if not allowed:
            logger.warning(
                "[%s] robots.txt blocks %s → skipping (reason: %s)",
                self.SOURCE_NAME, search_url, reason,
            )
            result = {
                "censored": True,
                "reason": reason,
                "source": self.SOURCE_NAME,
                "origin": origin,
                "destination": destination,
                "travel_date": travel_date.isoformat(),
                "advance_days": advance_days,
            }
            self._write_raw(result, origin, destination, travel_date, advance_days)
            raise RobotsBlockedError(reason)

        # ── Random pre-request delay ──────────────────────────────────────────
        delay = random.uniform(
            settings.scraper_min_delay_s, settings.scraper_max_delay_s
        )
        logger.debug("[%s] Sleeping %.1fs before request", self.SOURCE_NAME, delay)
        await asyncio.sleep(delay)

        # ── Playwright browser session ────────────────────────────────────────
        is_headless = settings.playwright_headless if headless is None else headless
        async with async_playwright() as pw:
            browser_type = getattr(pw, settings.playwright_browser)
            browser = await browser_type.launch(
                headless=is_headless,
                args=[
                    "--disable-http2",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ],
            )
            context: BrowserContext = await browser.new_context(
                user_agent=ua,
                locale="en-IN",
                timezone_id="Asia/Kolkata",
                viewport={"width": 1280, "height": 800},
                extra_http_headers={
                    "Accept-Language": "en-IN,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page: Page = await context.new_page()

            # Intercept the XHR response containing fare data
            captured_json: dict | None = None

            async def handle_response(response: Response) -> None:
                nonlocal captured_json
                if self._intercept_predicate(response.url):
                    try:
                        captured_json = await response.json()
                        logger.debug(
                            "[%s] Intercepted XHR: %s", self.SOURCE_NAME, response.url
                        )
                    except Exception as exc:
                        logger.warning(
                            "[%s] Failed to parse intercepted response: %s",
                            self.SOURCE_NAME, exc,
                        )

            page.on("response", handle_response)

            try:
                logger.info(
                    "[%s] Navigating to %s", self.SOURCE_NAME, search_url
                )
                try:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
                    # Wait for network idle up to 15s
                    await page.wait_for_load_state("networkidle", timeout=15_000)
                except Exception as nav_err:
                    logger.warning(
                        "[%s] Navigation warning on %s: %s",
                        self.SOURCE_NAME, search_url, nav_err,
                    )

                # ── CAPTCHA detection ─────────────────────────────────────────
                try:
                    page_text = (await page.content()).lower()
                    if any(sig in page_text for sig in _CAPTCHA_SIGNALS):
                        logger.error(
                            "[%s] CAPTCHA detected on %s — backing off",
                            self.SOURCE_NAME, search_url,
                        )
                        raise CaptchaDetectedError(
                            f"{self.SOURCE_NAME}: CAPTCHA on {search_url}"
                        )
                except CaptchaDetectedError:
                    raise
                except Exception:
                    pass

                if captured_json is None:
                    logger.warning(
                        "[%s] No matching XHR captured for %s→%s on %s",
                        self.SOURCE_NAME, origin, destination, travel_date,
                    )
                    captured_json = {}

            finally:
                await browser.close()

        # ── Parse + persist ───────────────────────────────────────────────────
        result = self._parse_response(
            captured_json, origin, destination, travel_date, advance_days
        )
        self._write_raw(result, origin, destination, travel_date, advance_days)
        return result

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _write_raw(
        self,
        data: dict,
        origin: str,
        destination: str,
        travel_date: date,
        advance_days: int,
    ) -> Optional[str]:
        """
        Sanitize and persist raw JSON to Supabase Storage bucket 'raw-scrapes'
        at {source}/{YYYY-MM-DD}/{route}_{window}d.json using service-role client.
        Keeps local data/raw/ copy only when APP_ENV=development.
        """
        from apix.scraper.storage import upload_raw_scrape
        return upload_raw_scrape(
            data=data,
            source=self.SOURCE_NAME,
            origin=origin,
            destination=destination,
            advance_days=advance_days,
            scrape_date=date.today(),
        )

