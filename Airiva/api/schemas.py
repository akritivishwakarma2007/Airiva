"""
schemas.py — Pydantic request and response models for the API.
Enforces strict validation, caps string lengths, and rejects unknown fields.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class StrictBaseModel(BaseModel):
    """Base model that forbids unexpected fields."""
    model_config = ConfigDict(extra="forbid")


# ── System / Health ───────────────────────────────────────────────────────────
class HealthResponse(StrictBaseModel):
    """Minimal health response. Never exposes versions, paths, or DB details."""
    status: Literal["ok"] = "ok"


# ── Admin Requests & Responses ────────────────────────────────────────────────
class TriggerScrapeRequest(StrictBaseModel):
    """Request payload to manually trigger a scraper run."""
    sources: Optional[List[str]] = Field(
        default=None,
        description="Optional list of enabled sources to trigger (e.g. ['indigo', 'air_india'])",
    )

    @field_validator("sources")
    @classmethod
    def _validate_sources(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        cleaned = []
        for s in v:
            if not isinstance(s, str):
                raise ValueError("Source name must be a string")
            s = s.strip().lower()
            if not s or len(s) > 50:
                raise ValueError("Source name must be between 1 and 50 characters")
            cleaned.append(s)
        return cleaned


class InviteUserRequest(StrictBaseModel):
    """Request payload to invite a new user with an initial role."""
    email: EmailStr = Field(
        ...,
        max_length=254,
        description="Valid email address of the user to invite",
    )
    role: Literal["analyst", "admin"] = Field(
        ...,
        description="Initial role to assign to the user ('analyst' or 'admin')",
    )


class CreateUserRequest(StrictBaseModel):
    """Request payload for an admin to directly create and provision a user with a password."""
    email: EmailStr = Field(
        ...,
        max_length=254,
        description="Valid email address of the user to create",
    )
    password: str = Field(
        ...,
        min_length=6,
        max_length=128,
        description="Initial password for the user (minimum 6 characters)",
    )
    role: Literal["analyst", "admin"] = Field(
        ...,
        description="Initial role to assign to the user ('analyst' or 'admin')",
    )


class ScrapeLogItem(StrictBaseModel):
    """Single scrape log entry."""
    id: int
    run_id: Optional[str] = Field(default=None, max_length=100)
    source: Optional[str] = Field(default=None, max_length=50)
    route_code: Optional[str] = Field(default=None, max_length=20)
    advance_window: Optional[str] = Field(default=None, max_length=50)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    status: Optional[str] = Field(default=None, max_length=50)
    records_collected: Optional[int] = None
    error: Optional[str] = Field(default=None, max_length=1000)


class ScrapeLogPage(StrictBaseModel):
    """Paginated scrape log list."""
    total: int
    page: int
    page_size: int
    data: List[ScrapeLogItem]


# ── Index Value Schemas ───────────────────────────────────────────────────────
class DailyIndexPoint(StrictBaseModel):
    index_date: date
    index_value: float
    del_bom: Optional[float] = None
    del_blr: Optional[float] = None
    bom_blr: Optional[float] = None
    sample_size: Optional[int] = None
    computed_at: Optional[datetime] = None


class WeeklyIndexPoint(StrictBaseModel):
    iso_year: int
    iso_week: int
    week_start_date: date
    index_value: float
    del_bom: Optional[float] = None
    del_blr: Optional[float] = None
    bom_blr: Optional[float] = None


class MonthlyIndexPoint(StrictBaseModel):
    year: int
    month: int
    index_value: float
    del_bom: Optional[float] = None
    del_blr: Optional[float] = None
    bom_blr: Optional[float] = None


class RouteIndexResponse(StrictBaseModel):
    route: str = Field(..., max_length=20)
    period: Literal["daily", "weekly", "monthly"]
    data: List[Dict[str, Any]]


# ── Fare Quotes Schemas ───────────────────────────────────────────────────────
class FareQuoteResponse(StrictBaseModel):
    id: int
    scrape_date: date
    origin: str = Field(..., max_length=10)
    destination: str = Field(..., max_length=10)
    carrier: Optional[str] = Field(default=None, max_length=20)
    flight_number: Optional[str] = Field(default=None, max_length=20)
    travel_date: date
    advance_purchase_days: int
    fare_class: Optional[str] = Field(default=None, max_length=50)
    base_fare: Optional[float] = None
    taxes_fees: Optional[float] = None
    total_fare: float
    seats_available: Optional[int] = None
    source: str = Field(..., max_length=50)
    is_censored: bool = False
    is_outlier: bool = False
    is_duplicate: bool = False


class RawQuotesCursorPage(StrictBaseModel):
    """Cursor-paginated raw quotes response."""
    data: List[FareQuoteResponse]
    next_cursor: Optional[int] = None
    has_more: bool = False
    count: int
