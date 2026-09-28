"""
test_deduplicator.py — Tests for apix.pipeline.deduplicator
"""
from __future__ import annotations

import pytest

from apix.pipeline.deduplicator import deduplicate
from apix.pipeline.schema import FareRecord


class TestDeduplicate:
    def test_cheaper_airline_direct_wins(self, make_fare):
        """
        When airline-direct is cheaper, the OTA (makemytrip) record
        should be marked as_duplicate=True.
        """
        direct = make_fare(flight_number="6E-123", total_fare=4500.0, source="indigo")
        ota    = make_fare(flight_number="6E-123", total_fare=4700.0, source="makemytrip")
        result = deduplicate([direct, ota])

        winners  = [r for r in result if not r.is_duplicate]
        losers   = [r for r in result if r.is_duplicate]
        assert len(winners) == 1
        assert len(losers)  == 1
        assert winners[0].total_fare == 4500.0
        assert losers[0].source == "makemytrip"

    def test_cheaper_ota_wins(self, make_fare):
        """
        When OTA is cheaper (e.g. sale price), the OTA record should win.
        """
        direct = make_fare(flight_number="6E-123", total_fare=5000.0, source="indigo")
        ota    = make_fare(flight_number="6E-123", total_fare=4600.0, source="makemytrip")
        result = deduplicate([direct, ota])

        winners = [r for r in result if not r.is_duplicate]
        assert winners[0].source == "makemytrip"
        assert winners[0].total_fare == 4600.0

    def test_no_duplicate_when_different_flights(self, make_fare):
        """Different flight numbers are not duplicates."""
        r1 = make_fare(flight_number="6E-123", total_fare=4500.0, source="indigo")
        r2 = make_fare(flight_number="6E-456", total_fare=4800.0, source="makemytrip")
        result = deduplicate([r1, r2])
        assert all(not r.is_duplicate for r in result)

    def test_different_fare_class_not_duplicate(self, make_fare):
        """Same flight but different fare class = not a duplicate."""
        r1 = make_fare(flight_number="6E-123", fare_class="SAVER",  total_fare=4000.0)
        r2 = make_fare(flight_number="6E-123", fare_class="FLEX",   total_fare=5500.0)
        result = deduplicate([r1, r2])
        assert all(not r.is_duplicate for r in result)

    def test_records_count_unchanged(self, sample_records):
        """Total records must not be dropped by deduplication."""
        result = deduplicate(sample_records)
        assert len(result) == len(sample_records)

    def test_censored_not_deduplicated(self, make_fare):
        """
        Censored records must be excluded from dedup groups.
        A censored record should never suppress a valid record.
        """
        censored = make_fare(flight_number="6E-123", total_fare=0.0, is_censored=True)
        valid    = make_fare(flight_number="6E-123", total_fare=4500.0, source="indigo")
        result   = deduplicate([censored, valid])

        valid_result = [r for r in result if not r.is_censored]
        assert all(not r.is_duplicate for r in valid_result), \
            "Valid record must not be marked duplicate by a censored record"

    def test_three_way_duplicate_one_winner(self, make_fare):
        """
        Three sources with the same flight/date/class → only the cheapest survives.
        """
        r1 = make_fare(flight_number="6E-123", total_fare=4700.0, source="indigo")
        r2 = make_fare(flight_number="6E-123", total_fare=4500.0, source="makemytrip")  # cheapest
        r3 = make_fare(flight_number="6E-123", total_fare=4900.0, source="air_india")
        result = deduplicate([r1, r2, r3])

        winners = [r for r in result if not r.is_duplicate]
        assert len(winners) == 1
        assert winners[0].total_fare == 4500.0

    def test_flight_number_normalised(self, make_fare):
        """Flight numbers with different whitespace/case should still dedup."""
        r1 = make_fare(flight_number="6E-123",  total_fare=4500.0, source="indigo")
        r2 = make_fare(flight_number="6E- 123", total_fare=4700.0, source="makemytrip")
        result = deduplicate([r1, r2])
        losers = [r for r in result if r.is_duplicate]
        assert len(losers) >= 1
