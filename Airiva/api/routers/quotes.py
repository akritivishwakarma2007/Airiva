"""
routers/quotes.py — Raw fare quote endpoints.

GET /v1/raw-quotes — cursor-paginated list of fare quotes (Analyst or Admin only, max page size 200).
GET /v1/raw-quotes/stats — summary statistics per route/window.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from apix.api.auth import require_user
from apix.api.limiter import limiter
from apix.api.schemas import FareQuoteResponse, RawQuotesCursorPage
from apix.pipeline.db import AsyncSessionLocal, FareQuote

router = APIRouter(prefix="/raw-quotes", tags=["Quotes"])


@router.get("", response_model=RawQuotesCursorPage)
@limiter.limit("60/minute")
async def get_raw_quotes(
    request: Request,
    origin: Optional[str] = Query(default=None, max_length=10),
    destination: Optional[str] = Query(default=None, max_length=10),
    source: Optional[str] = Query(default=None, max_length=50),
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    advance_days: Optional[int] = None,
    include_censored: bool = False,
    include_outliers: bool = False,
    include_duplicates: bool = False,
    cursor: Optional[int] = Query(default=None, ge=1, description="Exclusive ID cursor for keyset pagination"),
    limit: int = Query(default=50, ge=1, le=200, description="Page size (max 200)"),
    user: Dict[str, Any] = Depends(require_user),
) -> RawQuotesCursorPage:
    """
    Return cursor-paginated raw fare quotes with optional filters.
    Requires Analyst or Admin role. Maximum page size is 200.
    """
    async with AsyncSessionLocal() as session:
        q = select(FareQuote)

        if origin:
            q = q.where(FareQuote.origin == origin.strip().upper())
        if destination:
            q = q.where(FareQuote.destination == destination.strip().upper())
        if source:
            q = q.where(FareQuote.source == source.strip().lower())
        if from_date:
            q = q.where(FareQuote.scrape_date >= from_date)
        if to_date:
            q = q.where(FareQuote.scrape_date <= to_date)
        if advance_days is not None:
            q = q.where(FareQuote.advance_purchase_days == advance_days)
        if not include_censored:
            q = q.where(FareQuote.is_censored.is_(False))
        if not include_outliers:
            q = q.where(FareQuote.is_outlier.is_(False))
        if not include_duplicates:
            q = q.where(FareQuote.is_duplicate.is_(False))

        # Cursor keyset pagination (fetch limit + 1 to determine if next page exists)
        if cursor is not None:
            q = q.where(FareQuote.id < cursor)

        q = q.order_by(FareQuote.id.desc()).limit(limit + 1)
        rows = (await session.execute(q)).scalars().all()

    has_more = len(rows) > limit
    page_rows = rows[:limit] if has_more else rows
    next_cursor = page_rows[-1].id if (has_more and page_rows) else None

    data = [
        FareQuoteResponse(
            id=r.id,
            scrape_date=r.scrape_date,
            origin=r.origin,
            destination=r.destination,
            carrier=r.carrier,
            flight_number=r.flight_number,
            travel_date=r.travel_date,
            advance_purchase_days=r.advance_purchase_days,
            fare_class=r.fare_class,
            base_fare=float(r.base_fare) if r.base_fare else None,
            taxes_fees=float(r.taxes_fees) if r.taxes_fees else None,
            total_fare=float(r.total_fare),
            seats_available=r.seats_available,
            source=r.source,
            is_censored=bool(r.is_censored),
            is_outlier=bool(r.is_outlier),
            is_duplicate=bool(r.is_duplicate),
        )
        for r in page_rows
    ]

    return RawQuotesCursorPage(
        data=data,
        next_cursor=next_cursor,
        has_more=has_more,
        count=len(data),
    )


@router.get("/stats")
@limiter.limit("60/minute")
async def get_quote_stats(
    request: Request,
    user: Dict[str, Any] = Depends(require_user),
):
    """
    Return summary statistics per (route, advance_days, source).
    Requires Analyst or Admin role.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                FareQuote.origin,
                FareQuote.destination,
                FareQuote.advance_purchase_days,
                FareQuote.source,
                func.count(FareQuote.id).label("count"),
                func.avg(FareQuote.total_fare).label("avg_fare"),
                func.min(FareQuote.total_fare).label("min_fare"),
                func.max(FareQuote.total_fare).label("max_fare"),
            )
            .where(
                FareQuote.is_censored.is_(False),
                FareQuote.is_outlier.is_(False),
                FareQuote.is_duplicate.is_(False),
            )
            .group_by(
                FareQuote.origin,
                FareQuote.destination,
                FareQuote.advance_purchase_days,
                FareQuote.source,
            )
            .order_by(FareQuote.origin, FareQuote.destination, FareQuote.advance_purchase_days)
        )
        rows = result.all()

    return [
        {
            "route": f"{r.origin}-{r.destination}",
            "advance_days": r.advance_purchase_days,
            "source": r.source,
            "count": r.count,
            "avg_fare": round(float(r.avg_fare), 2) if r.avg_fare else None,
            "min_fare": round(float(r.min_fare), 2) if r.min_fare else None,
            "max_fare": round(float(r.max_fare), 2) if r.max_fare else None,
        }
        for r in rows
    ]
