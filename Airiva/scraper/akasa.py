"""
akasa.py — Akasa Air scraper.

Targets akasaair.com one-way domestic flight search.
Carrier code: QP.
Intercepts availability and pricing XHR/Fetch calls.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from apix.scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class AkasaScraper(BaseScraper):
    BASE_URL = "https://www.akasaair.com"
    SOURCE_NAME = "akasa"

    _XHR_KEYWORDS = ["availability", "search", "fare", "flight", "booking", "lowfare"]

    def _search_url(self, origin: str, destination: str, travel_date: date) -> str:
        """
        Build one-way search deep-link for Akasa Air.
        Format: YYYY-MM-DD
        """
        fmt_date = travel_date.isoformat()
        return (
            f"https://www.akasaair.com/fly/flight-search?"
            f"tripType=OW&origin={origin}&destination={destination}"
            f"&departDate={fmt_date}&adults=1&children=0&infants=0"
        )

    def _intercept_predicate(self, url: str) -> bool:
        url_lower = url.lower()
        domain_match = "akasaair.com" in url_lower or "akasa" in url_lower
        keyword_match = any(kw in url_lower for kw in self._XHR_KEYWORDS)
        is_api = "/api/" in url_lower or "search" in url_lower or "v1" in url_lower or "v2" in url_lower
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
            logger.warning("[akasa] Empty response for %s→%s on %s", origin, destination, travel_date)
            return self._empty_result(origin, destination, travel_date, advance_days)

        try:
            items = (
                raw_json.get("flights")
                or raw_json.get("outboundFlights")
                or raw_json.get("trips", [{}])[0].get("flights", [])
                if isinstance(raw_json.get("trips"), list) and raw_json.get("trips")
                else []
            )
            for flight in items:
                flight_num = flight.get("flightNumber") or flight.get("flightNo") or flight.get("identifier", "")
                if not flight_num.startswith("QP-") and not flight_num.startswith("QP"):
                    flight_num = f"QP-{flight_num.lstrip('QP-')}"
                fares = flight.get("fareOptions") or flight.get("fares") or flight.get("bundles") or [{}]
                for fare in fares:
                    flights.append({
                        "flight_number": flight_num,
                        "carrier": "QP",
                        "departure": flight.get("departureDate") or flight.get("departureTime") or flight.get("departure", ""),
                        "arrival": flight.get("arrivalDate") or flight.get("arrivalTime") or flight.get("arrival", ""),
                        "fare_class": fare.get("fareClass") or fare.get("brandName") or fare.get("fareType", "SAVER"),
                        "base_fare": fare.get("baseFare") or fare.get("baseAmount", None),
                        "taxes_fees": fare.get("taxes") or fare.get("taxAmount", None),
                        "total_fare": fare.get("totalFare") or fare.get("totalAmount", None),
                        "seats_available": fare.get("seatsAvailable") or fare.get("seats", None),
                    })
        except Exception as exc:
            logger.error("[akasa] Parse error: %s", exc)

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
            "source": "akasa",
            "origin": origin,
            "destination": destination,
            "travel_date": travel_date.isoformat(),
            "advance_days": advance_days,
            "flights": [],
            "censored": True,
            "reason": "empty_response",
        }
