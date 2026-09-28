"""
air_india.py — Air India scraper.

Targets airindia.com one-way domestic flight search.
Intercepts the availability/pricing XHR (Amadeus GDS-backed in 2025).

IMPORTANT: Air India's robots.txt has broad Disallow rules.
BaseScraper.scrape() performs a robots.txt check before any navigation.
If disallowed, RobotsBlockedError is raised and the run is logged — no
scraping attempt is made.

XHR pattern (observed 2024-2025, Air India's Amadeus-powered booking engine):
  POST https://www.airindia.com/api/flights/availability
  or   https://booking.airindia.com/...

Response shape (simplified):
  {
    "itineraries": [
      {
        "segments": [
          {
            "flightNumber": "AI-101",
            "marketingCarrier": "AI",
            "origin": "DEL", "destination": "BOM",
            "departureDateTime": "2024-10-10T06:00:00",
            "arrivalDateTime": "2024-10-10T08:15:00"
          }
        ],
        "fareOptions": [
          {
            "cabinClass": "ECONOMY",
            "bookingClass": "S",
            "baseAmount": 4200.00,
            "taxAmount": 780.00,
            "totalAmount": 4980.00,
            "seatsLeft": 7
          }
        ]
      }
    ]
  }
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from apix.scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class AirIndiaScraper(BaseScraper):
    BASE_URL = "https://www.airindia.com"
    SOURCE_NAME = "air_india"

    _XHR_KEYWORDS = ["availability", "flight", "search", "itinerary"]

    def _search_url(self, origin: str, destination: str, travel_date: date) -> str:
        """
        Build the Air India deep-link search URL.
        Date format: YYYY-MM-DD.
        """
        fmt_date = travel_date.strftime("%Y-%m-%d")
        return (
            f"https://www.airindia.com/in/en/book/flight-search.html"
            f"?origin={origin}&destination={destination}"
            f"&departDate={fmt_date}&paxType=ADT&paxCount=1&tripType=O"
        )

    def _intercept_predicate(self, url: str) -> bool:
        """Match Air India's booking engine API calls."""
        url_lower = url.lower()
        domain_match = "airindia.com" in url_lower
        keyword_match = any(kw in url_lower for kw in self._XHR_KEYWORDS)
        is_api = "/api/" in url_lower or "booking" in url_lower
        return domain_match and keyword_match and is_api

    def _parse_response(
        self,
        raw_json: Any,
        origin: str,
        destination: str,
        travel_date: date,
        advance_days: int,
    ) -> dict:
        """Normalise Air India's XHR response."""
        flights = []

        if not raw_json:
            logger.warning("[air_india] Empty response for %s→%s on %s", origin, destination, travel_date)
            return self._empty_result(origin, destination, travel_date, advance_days)

        try:
            itineraries = raw_json.get("itineraries", raw_json.get("flights", []))
            for itin in itineraries:
                segments = itin.get("segments", [itin])
                if not segments:
                    continue
                seg = segments[0]  # first (and only) segment for non-stop
                flight_num = seg.get("flightNumber", seg.get("flightNo", ""))
                carrier = seg.get("marketingCarrier", "AI")

                for fare in itin.get("fareOptions", itin.get("fares", [{}])):
                    flights.append({
                        "flight_number": flight_num,
                        "carrier": carrier,
                        "departure": seg.get("departureDateTime", seg.get("departure", "")),
                        "arrival": seg.get("arrivalDateTime", seg.get("arrival", "")),
                        "fare_class": fare.get("bookingClass", fare.get("cabinClass", "ECONOMY")),
                        "base_fare": fare.get("baseAmount", fare.get("baseFare", None)),
                        "taxes_fees": fare.get("taxAmount", fare.get("taxes", None)),
                        "total_fare": fare.get("totalAmount", fare.get("totalFare", None)),
                        "seats_available": fare.get("seatsLeft", fare.get("seatsAvailable", None)),
                    })
        except Exception as exc:
            logger.error("[air_india] Parse error: %s — raw keys: %s", exc, list(raw_json.keys()) if raw_json else [])

        return {
            "source": self.SOURCE_NAME,
            "origin": origin,
            "destination": destination,
            "travel_date": travel_date.isoformat(),
            "advance_days": advance_days,
            "flights": flights,
        }

    @staticmethod
    def _empty_result(origin: str, destination: str, travel_date: date, advance_days: int) -> dict:
        return {
            "source": "air_india",
            "origin": origin,
            "destination": destination,
            "travel_date": travel_date.isoformat(),
            "advance_days": advance_days,
            "flights": [],
            "censored": True,
            "reason": "empty_response",
        }
