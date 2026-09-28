"""
schema.py — Canonical Pydantic model for a single fare quote.

All 13 specification fields + 3 quality flags (censored, outlier, duplicate).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FareRecord(BaseModel):
    """One fare quote, post-normalisation."""

    # ── Identification ────────────────────────────────────────────────────────
    origin: str = Field(..., min_length=3, max_length=3, description="IATA airport code")
    destination: str = Field(..., min_length=3, max_length=3, description="IATA airport code")
    carrier: str = Field(..., description="Airline IATA code, e.g. '6E', 'AI'")
    flight_number: str = Field(..., description="Full flight number, e.g. '6E-123'")

    # ── Dates ─────────────────────────────────────────────────────────────────
    travel_date: date = Field(..., description="Date of travel (flight departure date)")
    scrape_timestamp: datetime = Field(..., description="UTC timestamp when data was collected")
    scrape_date: date = Field(..., description="Date portion of scrape_timestamp (partition key)")
    advance_purchase_days: int = Field(..., ge=0, description="Days between scrape_date and travel_date")

    # ── Fare breakdown ────────────────────────────────────────────────────────
    fare_class: Optional[str] = Field(None, description="Booking/fare class code")
    base_fare: Optional[float] = Field(None, ge=0, description="Base fare in INR, excl. taxes")
    taxes_fees: Optional[float] = Field(None, ge=0, description="Taxes and fees in INR")
    total_fare: float = Field(..., ge=0, description="Total fare in INR (base + taxes)")
    seats_available: Optional[int] = Field(None, ge=0)

    # ── Provenance ────────────────────────────────────────────────────────────
    source: str = Field(..., description="Scraper source: indigo | air_india | makemytrip")
    raw_file_path: Optional[str] = Field(None, description="Path to raw JSON dump")

    # ── Quality flags ─────────────────────────────────────────────────────────
    is_censored: bool = Field(
        default=False,
        description="True when flight sold out or scrape was blocked (robots/CAPTCHA). "
                    "Never dropped — retained as a missing-data signal.",
    )
    is_outlier: bool = Field(
        default=False,
        description="True when fare lies outside IQR fence for this (route, date, window) group. "
                    "Record is retained; index engine excludes outliers.",
    )
    is_duplicate: bool = Field(
        default=False,
        description="True when a cheaper quote for the same (flight, date, class) already exists. "
                    "Suppressed record is retained for audit.",
    )

    @field_validator("origin", "destination", mode="before")
    @classmethod
    def upper_iata(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("carrier", mode="before")
    @classmethod
    def upper_carrier(cls, v: str) -> str:
        return v.strip().upper()

    model_config = ConfigDict(populate_by_name=True)
