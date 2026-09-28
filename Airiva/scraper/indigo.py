"""
indigo.py — IndiGo scraper.

Targets goindigo.in one-way domestic flight search.
Intercepts the availability/pricing XHR that the React SPA calls.

XHR pattern (observed 2024-2025):
  POST https://book.goindigo.in/api/...  (exact path varies; matched by keyword)
  or GET  https://prod.goindigo.in/...

Response shape (simplified):
  {
    "flightAvailability": {
      "outboundFlights": [
        {
          "flightNumber": "6E-123",
          "origin": "DEL", "destination": "BOM",
          "departureDate": "2024-10-10T06:00:00",
          "arrivalDate": "2024-10-10T08:10:00",
          "fareOptions": [
            {
              "fareClass": "SAVER",
              "baseFare": 3500.00,
              "taxes": 650.00,
              "totalFare": 4150.00,
              "seatsAvailable": 9
            }
          ]
        }
      ]
    }
  }

Note: The exact field names are normalised in the `_parse_response` method.
If IndiGo updates their API, only this file needs changing.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from apix.scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class IndiGoScraper(BaseScraper):
    BASE_URL = "https://www.goindigo.in"
    SOURCE_NAME = "indigo"

    # Keywords that identify IndiGo's fare search XHR URL
    _XHR_KEYWORDS = ["availability", "search", "fare", "flight"]

    def _search_url(self, origin: str, destination: str, travel_date: date) -> str:
        """
        Build the deep-link URL that launches IndiGo's search SPA.
        Date format: DD/MM/YYYY as required by IndiGo's URL scheme.
        """
        fmt_date = travel_date.strftime("%d/%m/%Y")
        return (
            f"https://www.goindigo.in/flight-booking.html"
            f"#origin={origin}&destination={destination}"
            f"&departDate={fmt_date}&adult=1&child=0&infant=0"
            f"&tripType=O&src=search"
        )

    def _intercept_predicate(self, url: str) -> bool:
        """
        Match IndiGo's internal pricing API calls.
        Uses keyword matching so it survives minor URL path changes.
        """
        url_lower = url.lower()
        domain_match = "goindigo.in" in url_lower or "indigo" in url_lower
        keyword_match = any(kw in url_lower for kw in self._XHR_KEYWORDS)
        is_api = "/api/" in url_lower or "search" in url_lower
        return domain_match and keyword_match and is_api

    def _parse_response(
        self,
        raw_json: Any,
        origin: str,
        destination: str,
        travel_date: date,
        advance_days: int,
    ) -> dict:
        """
        Normalise IndiGo's raw XHR response into the APIx intermediate format.

        Returns a dict with top-level keys:
          source, origin, destination, travel_date, advance_days, flights[]
        """
        flights = []

        if not raw_json:
            logger.warning("[indigo] Empty response for %s→%s on %s", origin, destination, travel_date)
            return self._empty_result(origin, destination, travel_date, advance_days)

        # Traverse known response shapes; fail gracefully on unknown structures
        try:
            outbound = (
                raw_json
                .get("flightAvailability", raw_json)
                .get("outboundFlights", raw_json.get("flights", []))
            )
            for flight in outbound:
                flight_num = flight.get("flightNumber", flight.get("flightNo", ""))
                for fare in flight.get("fareOptions", flight.get("fares", [{}])):
                    flights.append({
                        "flight_number": flight_num,
                        "carrier": "6E",
                        "departure": flight.get("departureDate", flight.get("departure", "")),
                        "arrival": flight.get("arrivalDate", flight.get("arrival", "")),
                        "fare_class": fare.get("fareClass", fare.get("class", "ECONOMY")),
                        "base_fare": fare.get("baseFare", fare.get("baseAmount", None)),
                        "taxes_fees": fare.get("taxes", fare.get("taxAmount", None)),
                        "total_fare": fare.get("totalFare", fare.get("totalAmount", None)),
                        "seats_available": fare.get("seatsAvailable", fare.get("seats", None)),
                    })
        except Exception as exc:
            logger.error("[indigo] Parse error: %s — raw keys: %s", exc, list(raw_json.keys()) if raw_json else [])

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
            "source": "indigo",
            "origin": origin,
            "destination": destination,
            "travel_date": travel_date.isoformat(),
            "advance_days": advance_days,
            "flights": [],
            "censored": True,
            "reason": "empty_response",
        }
