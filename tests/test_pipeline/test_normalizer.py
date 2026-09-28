"""
test_normalizer.py — Tests for apix.pipeline.normalizer
"""
from __future__ import annotations

import pytest
from datetime import date

from apix.pipeline.normalizer import normalize
from apix.pipeline.schema import FareRecord


# ── Fixture payloads (anonymised / not real API data) ─────────────────────────

INDIGO_RAW = {
    "source": "indigo",
    "origin": "DEL",
    "destination": "BOM",
    "travel_date": "2026-10-15",
    "advance_days": 7,
    "flights": [
        {
            "flight_number": "6E-345",
            "carrier": "6E",
            "departure": "2026-10-15T06:00:00",
            "arrival": "2026-10-15T08:10:00",
            "fare_class": "SAVER",
            "base_fare": 4200.0,
            "taxes_fees": 756.0,
            "total_fare": 4956.0,
            "seats_available": 5,
        },
        {
            "flight_number": "6E-346",
            "carrier": "6E",
            "departure": "2026-10-15T10:00:00",
            "arrival": "2026-10-15T12:15:00",
            "fare_class": "FLEX",
            "base_fare": 5100.0,
            "taxes_fees": 918.0,
            "total_fare": 6018.0,
            "seats_available": 3,
        },
    ],
}

AIR_INDIA_RAW = {
    "source": "air_india",
    "origin": "DEL",
    "destination": "BLR",
    "travel_date": "2026-10-22",
    "advance_days": 30,
    "flights": [
        {
            "flight_number": "AI-501",
            "carrier": "AI",
            "departure": "2026-10-22T07:30:00",
            "arrival": "2026-10-22T10:05:00",
            "fare_class": "ECONOMY",
            "base_fare": 3800.0,
            "taxes_fees": 684.0,
            "total_fare": 4484.0,
            "seats_available": 9,
        },
    ],
}

MMT_RAW = {
    "source": "makemytrip",
    "origin": "BOM",
    "destination": "BLR",
    "travel_date": "2026-10-15",
    "advance_days": 7,
    "flights": [
        {
            "flight_number": "6E-720",
            "carrier": "6E",
            "departure": "2026-10-15T08:00:00",
            "arrival": "2026-10-15T09:45:00",
            "fare_class": "SUPER_SAVER",
            "base_fare": 3600.0,
            "taxes_fees": 648.0,
            "total_fare": 4248.0,
            "seats_available": 7,
        },
    ],
}

CENSORED_RAW = {
    "source": "indigo",
    "origin": "DEL",
    "destination": "BOM",
    "travel_date": "2026-10-15",
    "advance_days": 7,
    "censored": True,
    "reason": "robots_txt_disallows",
}


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestNormalizeIndigo:
    def test_returns_correct_count(self):
        records = normalize(INDIGO_RAW)
        assert len(records) == 2

    def test_all_are_fare_records(self):
        records = normalize(INDIGO_RAW)
        for r in records:
            assert isinstance(r, FareRecord)

    def test_canonical_fields_populated(self):
        records = normalize(INDIGO_RAW)
        r = records[0]
        assert r.origin == "DEL"
        assert r.destination == "BOM"
        assert r.carrier == "6E"
        assert r.flight_number == "6E-345"
        assert r.total_fare == 4956.0
        assert r.fare_class == "SAVER"
        assert r.advance_purchase_days == 7
        assert r.source == "indigo"
        assert r.scrape_timestamp is not None
        assert not r.is_censored

    def test_second_flight_parsed(self):
        records = normalize(INDIGO_RAW)
        r = records[1]
        assert r.flight_number == "6E-346"
        assert r.fare_class == "FLEX"
        assert r.total_fare == 6018.0

    def test_travel_date_from_departure(self):
        records = normalize(INDIGO_RAW)
        assert records[0].travel_date == date(2026, 10, 15)


class TestNormalizeAirIndia:
    def test_returns_one_record(self):
        records = normalize(AIR_INDIA_RAW)
        assert len(records) == 1

    def test_source_correct(self):
        records = normalize(AIR_INDIA_RAW)
        assert records[0].source == "air_india"
        assert records[0].carrier == "AI"

    def test_advance_days_preserved(self):
        records = normalize(AIR_INDIA_RAW)
        assert records[0].advance_purchase_days == 30


class TestNormalizeMakeMyTrip:
    def test_returns_one_record(self):
        records = normalize(MMT_RAW)
        assert len(records) == 1

    def test_source_and_route(self):
        r = normalize(MMT_RAW)[0]
        assert r.source == "makemytrip"
        assert r.origin == "BOM"
        assert r.destination == "BLR"
        assert r.total_fare == 4248.0


class TestNormalizeCensored:
    def test_censored_emits_one_record(self):
        records = normalize(CENSORED_RAW)
        assert len(records) == 1

    def test_censored_flag_set(self):
        r = normalize(CENSORED_RAW)[0]
        assert r.is_censored is True
        assert r.total_fare == 0.0
        assert r.flight_number == "CENSORED"


class TestNormalizeEdgeCases:
    def test_unknown_source_returns_empty(self):
        records = normalize({"source": "unknown_ota", "flights": []})
        assert records == []

    def test_empty_flights_list(self):
        raw = {**INDIGO_RAW, "flights": []}
        records = normalize(raw)
        assert records == []

    def test_missing_total_fare_skipped(self):
        raw = {**INDIGO_RAW, "flights": [{"flight_number": "6E-999", "carrier": "6E"}]}
        records = normalize(raw)
        assert records == []

    def test_iata_codes_uppercased(self):
        raw = {**INDIGO_RAW, "origin": "del", "destination": "bom"}
        records = normalize(raw)
        for r in records:
            assert r.origin == "DEL"
            assert r.destination == "BOM"
