"""
spicejet.py — SpiceJet scraper.

Targets spicejet.com one-way domestic flight search.
Carrier code: SG.
Intercepts availability and pricing XHR/Fetch calls.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from apix.scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class SpiceJetScraper(BaseScraper):
    BASE_URL = "https://www.spicejet.com"
    SOURCE_NAME = "spicejet"

    _XHR_KEYWORDS = ["availability", "search", "fare", "flight", "booking", "lowfare"]

    def _search_url(self, origin: str, destination: str, travel_date: date) -> str:
        """
        Build one-way search deep-link for SpiceJet.
        Format: YYYY-MM-DD
        """
        fmt_date = travel_date.isoformat()
        return (
            f"https://www.spicejet.com/search?"
            f"from={origin}&to={destination}&tripType=1"
            f"&departure={fmt_date}&adult=1&child=0&infant=0"
        )

    def _intercept_predicate(self, url: str) -> bool:
        url_lower = url.lower()
        domain_match = "spicejet.com" in url_lower or "spicejet" in url_lower
        keyword_match = any(kw in url_lower for kw in self._XHR_KEYWORDS)
        is_api = "/api/" in url_lower or "search" in url_lower or "availability" in url_lower
        return domain_match and keyword_match and is_api

    def _parse_response(
        self,
        raw_json: Any,
        origin: str,
        destination: str,
        travel_date: date,
        advance_days: int,
    ) -> dict:
        flights = []
        if not raw_json:
            logger.warning("[spicejet] Empty response for %s→%s on %s", origin, destination, travel_date)
            return self._empty_result(origin, destination, travel_date, advance_days)

        try:
            items = (
                raw_json.get("flights")
                or raw_json.get("trips", [{}])[0].get("flightDetails", [])
                if isinstance(raw_json.get("trips"), list) and raw_json.get("trips")
                else raw_json.get("data", {}).get("flights", [])
            )
            for flight in items:
                flight_num = flight.get("flightNumber") or flight.get("flightNo", "")
                if not flight_num.startswith("SG-") and not flight_num.startswith("SG"):
                    flight_num = f"SG-{flight_num.lstrip('SG-')}"
                fares = flight.get("fareOptions") or flight.get("fares") or flight.get("fareTypes") or [{}]
                for fare in fares:
                    flights.append({
                        "flight_number": flight_num,
                        "carrier": "SG",
                        "departure": flight.get("departureDate") or flight.get("departureTime") or flight.get("departure", ""),
                        "arrival": flight.get("arrivalDate") or flight.get("arrivalTime") or flight.get("arrival", ""),
                        "fare_class": fare.get("fareClass") or fare.get("fareType", "SPICESAVER"),
                        "base_fare": fare.get("baseFare") or fare.get("baseAmount", None),
                        "taxes_fees": fare.get("taxes") or fare.get("taxAmount", None),
                        "total_fare": fare.get("totalFare") or fare.get("totalAmount", None),
                        "seats_available": fare.get("seatsAvailable") or fare.get("seats", None),
                    })
        except Exception as exc:
            logger.error("[spicejet] Parse error: %s", exc)

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
            "source": "spicejet",
            "origin": origin,
            "destination": destination,
            "travel_date": travel_date.isoformat(),
            "advance_days": advance_days,
            "flights": [],
            "censored": True,
            "reason": "empty_response",
        }
