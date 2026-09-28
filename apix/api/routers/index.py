"""
routers/index.py — Index value endpoints.

GET /index/daily             → last 30 days of composite daily index
GET /index/daily?days=N      → last N days
GET /index/weekly            → all weekly index records
GET /index/monthly           → all monthly index records
GET /index/route/{pair}      → route-specific series (daily by default)
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from apix.api.limiter import limiter
from apix.api.schemas import (
    DailyIndexPoint, MonthlyIndexPoint, RouteIndexResponse, WeeklyIndexPoint,
)
from apix.pipeline.db import AsyncSessionLocal, ApixDaily, ApixMonthly, ApixWeekly

router = APIRouter(prefix="/index", tags=["Index"])

VALID_ROUTES = {"DEL-BOM", "DEL-BLR", "BOM-BLR"}
ROUTE_COL_MAP = {"DEL-BOM": "del_bom", "DEL-BLR": "del_blr", "BOM-BLR": "bom_blr"}


@router.get("/daily", response_model=list[DailyIndexPoint])
@limiter.limit("60/minute")
async def get_daily_index(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
):
    """Return last `days` days of composite daily index values."""
    cutoff = date.today() - timedelta(days=days)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ApixDaily)
            .where(ApixDaily.index_date >= cutoff)
            .order_by(ApixDaily.index_date.asc())
        )
        rows = result.scalars().all()

    return [
        DailyIndexPoint(
            index_date=r.index_date,
            index_value=float(r.index_value),
            del_bom=float(r.del_bom) if r.del_bom else None,
            del_blr=float(r.del_blr) if r.del_blr else None,
            bom_blr=float(r.bom_blr) if r.bom_blr else None,
            sample_size=r.sample_size,
            computed_at=r.computed_at,
        )
        for r in rows
    ]


@router.get("/weekly", response_model=list[WeeklyIndexPoint])
@limiter.limit("60/minute")
async def get_weekly_index(request: Request):
    """Return all weekly index records."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ApixWeekly).order_by(ApixWeekly.iso_year.asc(), ApixWeekly.iso_week.asc())
        )
        rows = result.scalars().all()

    return [
        WeeklyIndexPoint(
            iso_year=r.iso_year, iso_week=r.iso_week,
            week_start_date=r.week_start_date,
            index_value=float(r.index_value),
            del_bom=float(r.del_bom) if r.del_bom else None,
            del_blr=float(r.del_blr) if r.del_blr else None,
            bom_blr=float(r.bom_blr) if r.bom_blr else None,
        )
        for r in rows
    ]


@router.get("/monthly", response_model=list[MonthlyIndexPoint])
@limiter.limit("60/minute")
async def get_monthly_index(request: Request):
    """Return all monthly index records."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ApixMonthly).order_by(ApixMonthly.year.asc(), ApixMonthly.month.asc())
        )
        rows = result.scalars().all()

    return [
        MonthlyIndexPoint(
            year=r.year, month=r.month,
            index_value=float(r.index_value),
            del_bom=float(r.del_bom) if r.del_bom else None,
            del_blr=float(r.del_blr) if r.del_blr else None,
            bom_blr=float(r.bom_blr) if r.bom_blr else None,
        )
        for r in rows
    ]


@router.get("/route/{pair}", response_model=RouteIndexResponse)
@limiter.limit("60/minute")
async def get_route_index(
    request: Request,
    pair: str,
    period: Literal["daily", "weekly", "monthly"] = Query(default="daily"),
    days: int = Query(default=60, ge=1, le=365),
):
    """
    Return index series for a specific route pair.

    pair must be one of: DEL-BOM, DEL-BLR, BOM-BLR
    """
    pair = pair.upper().replace("_", "-")
    if pair not in VALID_ROUTES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid route '{pair}'. Must be one of: {sorted(VALID_ROUTES)}",
        )

    col_name = ROUTE_COL_MAP[pair]
    data = []

    if period == "daily":
        cutoff = date.today() - timedelta(days=days)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ApixDaily)
                .where(ApixDaily.index_date >= cutoff)
                .order_by(ApixDaily.index_date.asc())
            )
            rows = result.scalars().all()
        data = [
            {"date": str(r.index_date), "index_value": float(getattr(r, col_name)) if getattr(r, col_name) else None}
            for r in rows
        ]

    elif period == "weekly":
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ApixWeekly).order_by(ApixWeekly.iso_year, ApixWeekly.iso_week)
            )
            rows = result.scalars().all()
        data = [
            {"week_start": str(r.week_start_date), "iso_week": r.iso_week, "index_value": float(getattr(r, col_name)) if getattr(r, col_name) else None}
            for r in rows
        ]

    elif period == "monthly":
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ApixMonthly).order_by(ApixMonthly.year, ApixMonthly.month)
            )
            rows = result.scalars().all()
        data = [
            {"year": r.year, "month": r.month, "index_value": float(getattr(r, col_name)) if getattr(r, col_name) else None}
            for r in rows
        ]

    return RouteIndexResponse(route=pair, period=period, data=data)
