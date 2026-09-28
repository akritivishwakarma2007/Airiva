"""
makemytrip.py — MakeMyTrip (OTA) scraper.

Targets makemytrip.com one-way domestic flight search.
Intercepts the flight search XHR (MMT's internal flights API).

MMT response shape (simplified, 2024-2025 observed structure):
  {
    "data": {
      "tripInfos": {
        "ONWARD": [
          {
            "sI": [
              {
                "fD": {
                  "aI": {"code": "6E", "name": "IndiGo"},
                  "fN": "123",
                  "eT": "E",        // equipment type
                },
                "da": {"code": "DEL", "name": "Indira Gandhi Intl"},
                "aa": {"code": "BOM", "name": "Chhatrapati Shivaji"},
                "dt": "2024-10-10T06:00:00",
                "at": "2024-10-10T08:10:00",
                "duration": 130
              }
            ],
            "totalPriceList": [
              {
                "fd": {
                  "ADULT": {
                    "fC": {
                      "BF": 3200,   // base fare
                      "TAF": 580,   // taxes and fees
                      "TF": 3780    // total fare
                    },
                    "cc": "SUPER SAVER",
                    "fB": "SAVER",
                    "sB": 4         // seats available
                  }
                }
              }
            ]
          }
        ]
      }
    }
  }
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from apix.scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class MakeMyTripScraper(BaseScraper):
    BASE_URL = "https://www.makemytrip.com"
    SOURCE_NAME = "makemytrip"

    _XHR_KEYWORDS = ["flights", "search", "fare", "intl", "domestic"]

    def _search_url(self, origin: str, destination: str, travel_date: date) -> str:
        """
        Build the MMT one-way flight search deep link.
        itinerary format: ORIGIN-DESTINATION-DDMMYYYY
        """
        fmt_date = travel_date.strftime("%d%m%Y")
        itinerary = f"{origin}-{destination}-{fmt_date}"
        return (
            f"https://www.makemytrip.com/flights/domestic/results"
            f"?itinerary={itinerary}&tripType=O&paxType=A-1_C-0_I-0"
            f"&intl=false&cabinClass=E&ccde=IN&lang=eng"
        )

    def _intercept_predicate(self, url: str) -> bool:
        """Match MMT's internal flight search API."""
        url_lower = url.lower()
        domain_match = "makemytrip.com" in url_lower
        keyword_match = any(kw in url_lower for kw in self._XHR_KEYWORDS)
        is_api = "/api/" in url_lower or "search" in url_lower or "results" in url_lower
        return domain_match and keyword_match and is_api

    def _parse_response(
        self,
        raw_json: Any,
        origin: str,
        destination: str,
        travel_date: date,
        advance_days: int,
    ) -> dict:
        """Normalise MMT's nested tripInfos XHR response."""
        flights = []

        if not raw_json:
            logger.warning("[makemytrip] Empty response for %s→%s on %s", origin, destination, travel_date)
            return self._empty_result(origin, destination, travel_date, advance_days)

        try:
            onward_list = (
                raw_json
                .get("data", raw_json)
                .get("tripInfos", {})
                .get("ONWARD", [])
            )

            for itinerary in onward_list:
                segments = itinerary.get("sI", [])
                if not segments:
                    continue
                seg = segments[0]

                carrier_code = seg.get("fD", {}).get("aI", {}).get("code", "")
                flight_num = seg.get("fD", {}).get("fN", "")
                full_flight = f"{carrier_code}-{flight_num}" if carrier_code else flight_num
                departure = seg.get("dt", "")
                arrival = seg.get("at", "")

                for price_entry in itinerary.get("totalPriceList", []):
                    adult_fare = (
                        price_entry.get("fd", {})
                        .get("ADULT", price_entry.get("fd", {}))
                    )
                    fare_costs = adult_fare.get("fC", {})
                    flights.append({
                        "flight_number": full_flight,
                        "carrier": carrier_code,
                        "departure": departure,
                        "arrival": arrival,
                        "fare_class": adult_fare.get("fB", adult_fare.get("cc", "ECONOMY")),
                        "base_fare": fare_costs.get("BF", None),
                        "taxes_fees": fare_costs.get("TAF", None),
                        "total_fare": fare_costs.get("TF", None),
                        "seats_available": adult_fare.get("sB", None),
                    })
        except Exception as exc:
            logger.error(
                "[makemytrip] Parse error: %s — raw keys: %s",
                exc, list(raw_json.keys()) if isinstance(raw_json, dict) else type(raw_json),
            )

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
            "source": "makemytrip",
            "origin": origin,
            "destination": destination,
            "travel_date": travel_date.isoformat(),
            "advance_days": advance_days,
            "flights": [],
            "censored": True,
            "reason": "empty_response",
        }
