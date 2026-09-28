"""
normalizer.py — Converts raw scraper JSON dicts into validated FareRecord lists.

One normalizer function per source. Each handles its own response shape
(documented in the corresponding scraper file). All return List[FareRecord].

Usage:
    records = normalize(raw_dict)   # auto-dispatches by source field
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from apix.pipeline.schema import FareRecord

logger = logging.getLogger(__name__)


def _parse_date(val: Any) -> date | None:
    """Parse ISO date or datetime string to date; return None on failure."""
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    s = str(val).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d%m%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


# ── IndiGo normalizer ─────────────────────────────────────────────────────────

def _normalize_indigo(raw: dict) -> list[FareRecord]:
    records: list[FareRecord] = []
    scrape_ts = _now_utc()
    scrape_date = scrape_ts.date()

    travel_date = _parse_date(raw.get("travel_date"))
    advance_days = int(raw.get("advance_days", 0))
    origin = raw.get("origin", "")
    destination = raw.get("destination", "")

    if raw.get("censored"):
        # Sold-out / robots-blocked — emit one censored record
        try:
            records.append(FareRecord(
                origin=origin,
                destination=destination,
                carrier="6E",
                flight_number="CENSORED",
                travel_date=travel_date or scrape_date,
                scrape_timestamp=scrape_ts,
                scrape_date=scrape_date,
                advance_purchase_days=advance_days,
                total_fare=0.0,
                source="indigo",
                is_censored=True,
            ))
        except Exception as exc:
            logger.warning("[normalizer:indigo] censored record error: %s", exc)
        return records

    for flight in raw.get("flights", []):
        total = flight.get("total_fare")
        if total is None:
            continue
        try:
            records.append(FareRecord(
                origin=origin,
                destination=destination,
                carrier=flight.get("carrier", "6E"),
                flight_number=flight.get("flight_number", ""),
                travel_date=_parse_date(flight.get("departure")) or travel_date or scrape_date,
                scrape_timestamp=scrape_ts,
                scrape_date=scrape_date,
                advance_purchase_days=advance_days,
                fare_class=flight.get("fare_class"),
                base_fare=flight.get("base_fare"),
                taxes_fees=flight.get("taxes_fees"),
                total_fare=float(total),
                seats_available=flight.get("seats_available"),
                source="indigo",
            ))
        except Exception as exc:
            logger.debug("[normalizer:indigo] Skipping record: %s — %s", flight, exc)

    return records


# ── Air India normalizer ──────────────────────────────────────────────────────

def _normalize_air_india(raw: dict) -> list[FareRecord]:
    records: list[FareRecord] = []
    scrape_ts = _now_utc()
    scrape_date = scrape_ts.date()

    travel_date = _parse_date(raw.get("travel_date"))
    advance_days = int(raw.get("advance_days", 0))
    origin = raw.get("origin", "")
    destination = raw.get("destination", "")

    if raw.get("censored"):
        try:
            records.append(FareRecord(
                origin=origin, destination=destination,
                carrier="AI", flight_number="CENSORED",
                travel_date=travel_date or scrape_date,
                scrape_timestamp=scrape_ts, scrape_date=scrape_date,
                advance_purchase_days=advance_days,
                total_fare=0.0, source="air_india", is_censored=True,
            ))
        except Exception as exc:
            logger.warning("[normalizer:air_india] censored record error: %s", exc)
        return records

    for flight in raw.get("flights", []):
        total = flight.get("total_fare")
        if total is None:
            continue
        try:
            records.append(FareRecord(
                origin=origin, destination=destination,
                carrier=flight.get("carrier", "AI"),
                flight_number=flight.get("flight_number", ""),
                travel_date=_parse_date(flight.get("departure")) or travel_date or scrape_date,
                scrape_timestamp=scrape_ts, scrape_date=scrape_date,
                advance_purchase_days=advance_days,
                fare_class=flight.get("fare_class"),
                base_fare=flight.get("base_fare"),
                taxes_fees=flight.get("taxes_fees"),
                total_fare=float(total),
                seats_available=flight.get("seats_available"),
                source="air_india",
            ))
        except Exception as exc:
            logger.debug("[normalizer:air_india] Skipping record: %s — %s", flight, exc)

    return records


# ── MakeMyTrip normalizer ─────────────────────────────────────────────────────

def _normalize_makemytrip(raw: dict) -> list[FareRecord]:
    records: list[FareRecord] = []
    scrape_ts = _now_utc()
    scrape_date = scrape_ts.date()

    travel_date = _parse_date(raw.get("travel_date"))
    advance_days = int(raw.get("advance_days", 0))
    origin = raw.get("origin", "")
    destination = raw.get("destination", "")

    if raw.get("censored"):
        try:
            records.append(FareRecord(
                origin=origin, destination=destination,
                carrier="MMT", flight_number="CENSORED",
                travel_date=travel_date or scrape_date,
                scrape_timestamp=scrape_ts, scrape_date=scrape_date,
                advance_purchase_days=advance_days,
                total_fare=0.0, source="makemytrip", is_censored=True,
            ))
        except Exception as exc:
            logger.warning("[normalizer:makemytrip] censored record error: %s", exc)
        return records

    for flight in raw.get("flights", []):
        total = flight.get("total_fare")
        if total is None:
            continue
        try:
            records.append(FareRecord(
                origin=origin, destination=destination,
                carrier=flight.get("carrier", ""),
                flight_number=flight.get("flight_number", ""),
                travel_date=_parse_date(flight.get("departure")) or travel_date or scrape_date,
                scrape_timestamp=scrape_ts, scrape_date=scrape_date,
                advance_purchase_days=advance_days,
                fare_class=flight.get("fare_class"),
                base_fare=flight.get("base_fare"),
                taxes_fees=flight.get("taxes_fees"),
                total_fare=float(total),
                seats_available=flight.get("seats_available"),
                source="makemytrip",
            ))
        except Exception as exc:
            logger.debug("[normalizer:makemytrip] Skipping record: %s — %s", flight, exc)

    return records


# ── Akasa Air normalizer ──────────────────────────────────────────────────────

def _normalize_akasa(raw: dict) -> list[FareRecord]:
    records: list[FareRecord] = []
    scrape_ts = _now_utc()
    scrape_date = scrape_ts.date()

    travel_date = _parse_date(raw.get("travel_date"))
    advance_days = int(raw.get("advance_days", 0))
    origin = raw.get("origin", "")
    destination = raw.get("destination", "")

    if raw.get("censored"):
        try:
            records.append(FareRecord(
                origin=origin, destination=destination,
                carrier="QP", flight_number="CENSORED",
                travel_date=travel_date or scrape_date,
                scrape_timestamp=scrape_ts, scrape_date=scrape_date,
                advance_purchase_days=advance_days,
                total_fare=0.0, source="akasa", is_censored=True,
            ))
        except Exception as exc:
            logger.warning("[normalizer:akasa] censored record error: %s", exc)
        return records

    for flight in raw.get("flights", []):
        total = flight.get("total_fare")
        if total is None:
            continue
        try:
            records.append(FareRecord(
                origin=origin, destination=destination,
                carrier=flight.get("carrier", "QP"),
                flight_number=flight.get("flight_number", ""),
                travel_date=_parse_date(flight.get("departure")) or travel_date or scrape_date,
                scrape_timestamp=scrape_ts, scrape_date=scrape_date,
                advance_purchase_days=advance_days,
                fare_class=flight.get("fare_class"),
                base_fare=flight.get("base_fare"),
                taxes_fees=flight.get("taxes_fees"),
                total_fare=float(total),
                seats_available=flight.get("seats_available"),
                source="akasa",
            ))
        except Exception as exc:
            logger.debug("[normalizer:akasa] Skipping record: %s — %s", flight, exc)

    return records


# ── SpiceJet normalizer ───────────────────────────────────────────────────────

def _normalize_spicejet(raw: dict) -> list[FareRecord]:
    records: list[FareRecord] = []
    scrape_ts = _now_utc()
    scrape_date = scrape_ts.date()

    travel_date = _parse_date(raw.get("travel_date"))
    advance_days = int(raw.get("advance_days", 0))
    origin = raw.get("origin", "")
    destination = raw.get("destination", "")

    if raw.get("censored"):
        try:
            records.append(FareRecord(
                origin=origin, destination=destination,
                carrier="SG", flight_number="CENSORED",
                travel_date=travel_date or scrape_date,
                scrape_timestamp=scrape_ts, scrape_date=scrape_date,
                advance_purchase_days=advance_days,
                total_fare=0.0, source="spicejet", is_censored=True,
            ))
        except Exception as exc:
            logger.warning("[normalizer:spicejet] censored record error: %s", exc)
        return records

    for flight in raw.get("flights", []):
        total = flight.get("total_fare")
        if total is None:
            continue
        try:
            records.append(FareRecord(
                origin=origin, destination=destination,
                carrier=flight.get("carrier", "SG"),
                flight_number=flight.get("flight_number", ""),
                travel_date=_parse_date(flight.get("departure")) or travel_date or scrape_date,
                scrape_timestamp=scrape_ts, scrape_date=scrape_date,
                advance_purchase_days=advance_days,
                fare_class=flight.get("fare_class"),
                base_fare=flight.get("base_fare"),
                taxes_fees=flight.get("taxes_fees"),
                total_fare=float(total),
                seats_available=flight.get("seats_available"),
                source="spicejet",
            ))
        except Exception as exc:
            logger.debug("[normalizer:spicejet] Skipping record: %s — %s", flight, exc)

    return records


# ── Dispatch ──────────────────────────────────────────────────────────────────

_NORMALIZERS = {
    "indigo": _normalize_indigo,
    "air_india": _normalize_air_india,
    "makemytrip": _normalize_makemytrip,
    "akasa": _normalize_akasa,
    "spicejet": _normalize_spicejet,
}


def normalize(raw: dict) -> list[FareRecord]:
    """
    Dispatch raw scraper dict to the appropriate normalizer.

    Detects source from raw["source"] field.
    Returns an empty list (with a warning) if source is unknown.
    """
    source = raw.get("source", "")
    fn = _NORMALIZERS.get(source)
    if fn is None:
        logger.warning("normalize(): unknown source '%s' — skipping batch", source)
        return []

    records = fn(raw)
    logger.debug("normalize(): %s → %d records", source, len(records))
    return records
