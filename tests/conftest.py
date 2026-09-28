"""
conftest.py — shared pytest fixtures for all test modules.
"""
from __future__ import annotations

import os

# Set test environment variables before any apix modules are loaded
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key-secret")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
os.environ.setdefault("APP_ENV", "test")

import pytest
from datetime import date, datetime, timezone
from typing import List

from apix.pipeline.schema import FareRecord


def _make_fare(
    origin="DEL", destination="BOM", carrier="6E",
    flight_number="6E-123", travel_date=None, scrape_date=None,
    advance_purchase_days=7, fare_class="ECONOMY",
    base_fare=4000.0, taxes_fees=720.0, total_fare=4720.0,
    seats_available=5, source="indigo",
    is_censored=False, is_outlier=False, is_duplicate=False,
) -> FareRecord:
    now = datetime.now(tz=timezone.utc)
    return FareRecord(
        origin=origin,
        destination=destination,
        carrier=carrier,
        flight_number=flight_number,
        travel_date=travel_date or date(2026, 10, 15),
        scrape_timestamp=now,
        scrape_date=scrape_date or now.date(),
        advance_purchase_days=advance_purchase_days,
        fare_class=fare_class,
        base_fare=base_fare,
        taxes_fees=taxes_fees,
        total_fare=total_fare,
        seats_available=seats_available,
        source=source,
        is_censored=is_censored,
        is_outlier=is_outlier,
        is_duplicate=is_duplicate,
    )


@pytest.fixture
def sample_records() -> List[FareRecord]:
    """A realistic set of fare records for testing."""
    return [
        _make_fare(flight_number="6E-101", total_fare=4500.0, source="indigo"),
        _make_fare(flight_number="6E-101", total_fare=4600.0, source="makemytrip"),  # duplicate
        _make_fare(flight_number="6E-102", total_fare=4800.0, source="indigo"),
        _make_fare(flight_number="AI-201", carrier="AI", total_fare=5200.0, source="air_india"),
        _make_fare(flight_number="6E-103", total_fare=4650.0, source="makemytrip"),
        _make_fare(flight_number="6E-104", total_fare=4750.0, source="indigo"),
        # Outlier — should be flagged
        _make_fare(flight_number="6E-999", total_fare=99000.0, source="indigo"),
    ]


@pytest.fixture
def censored_record() -> FareRecord:
    return _make_fare(
        flight_number="CENSORED", total_fare=0.0,
        is_censored=True, source="air_india",
    )


@pytest.fixture
def make_fare():
    """Factory fixture for creating custom FareRecord instances."""
    return _make_fare
