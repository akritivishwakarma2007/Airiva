"""
db.py — SQLAlchemy async engine and ORM models for TimescaleDB.

Tables:
  fare_quotes   — raw/cleaned fare records (hypertable on scrape_timestamp)
  apix_daily    — daily index values
  apix_weekly   — weekly index values
  apix_monthly  — monthly index values
  scraper_runs  — scrape run audit log

The physical hypertables are created by Docker's init_db.sql script.
SQLAlchemy models are used for typed ORM access only.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Integer,
    Numeric, SmallInteger, String, Text, UniqueConstraint, Index,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from apix.config import settings


# ── Engine + session factory ──────────────────────────────────────────────────
_is_sqlite = "sqlite" in settings.database_url.lower()

if _is_sqlite:
    engine = create_async_engine(
        settings.database_url,
        echo=False,
    )
else:
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


# ── Base ──────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Create all tables if they do not exist (SQLite or PostgreSQL)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── ORM Models ────────────────────────────────────────────────────────────────

class FareQuote(Base):
    """Maps to the ``fare_quotes`` hypertable."""
    __tablename__ = "fare_quotes"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    scrape_timestamp = Column(DateTime(timezone=True), nullable=False)
    scrape_date = Column(Date, nullable=False)
    origin = Column(String(3), nullable=False)
    destination = Column(String(3), nullable=False)
    carrier = Column(String(10), nullable=False)
    flight_number = Column(String(10), nullable=False)
    travel_date = Column(Date, nullable=False)
    advance_purchase_days = Column(Integer, nullable=False)
    fare_class = Column(String(20))
    base_fare = Column(Numeric(10, 2))
    taxes_fees = Column(Numeric(10, 2))
    total_fare = Column(Numeric(10, 2), nullable=False)
    seats_available = Column(Integer)
    source = Column(String(30), nullable=False)
    is_censored = Column(Boolean, nullable=False, default=False)
    is_outlier = Column(Boolean, nullable=False, default=False)
    is_duplicate = Column(Boolean, nullable=False, default=False)
    raw_file_path = Column(Text)

    __table_args__ = (
        UniqueConstraint(
            "flight_number", "travel_date", "fare_class", "source", "scrape_date",
            name="uq_fare_dedup",
        ),
        Index("ix_fq_route", "origin", "destination", "travel_date", "advance_purchase_days"),
        # Note: primary key on (id, scrape_timestamp) is required by TimescaleDB
        # hypertable partitioning — handled in init_db.sql
        {"extend_existing": True},
    )


class ApixDaily(Base):
    """Daily composite and route-level index values."""
    __tablename__ = "apix_daily"

    index_date = Column(Date, primary_key=True)
    index_value = Column(Numeric(10, 4), nullable=False)
    del_bom = Column(Numeric(10, 4))
    del_blr = Column(Numeric(10, 4))
    bom_blr = Column(Numeric(10, 4))
    sample_size = Column(Integer)
    computed_at = Column(DateTime(timezone=True))
    # Full 30-route sub-index values stored as JSON text (portable across SQLite + PG)
    route_values_json = Column(Text, nullable=True,
                               comment="JSON {route: sub_index_value} for all active routes")


class ApixWeekly(Base):
    """Weekly rolled-up index values (ISO week)."""
    __tablename__ = "apix_weekly"

    iso_year = Column(SmallInteger, primary_key=True)
    iso_week = Column(SmallInteger, primary_key=True)
    week_start_date = Column(Date, nullable=False)
    index_value = Column(Numeric(10, 4), nullable=False)
    del_bom = Column(Numeric(10, 4))
    del_blr = Column(Numeric(10, 4))
    bom_blr = Column(Numeric(10, 4))


class ApixMonthly(Base):
    """Monthly rolled-up index values."""
    __tablename__ = "apix_monthly"

    year = Column(SmallInteger, primary_key=True)
    month = Column(SmallInteger, primary_key=True)
    index_value = Column(Numeric(10, 4), nullable=False)
    del_bom = Column(Numeric(10, 4))
    del_blr = Column(Numeric(10, 4))
    bom_blr = Column(Numeric(10, 4))


class ScraperRun(Base):
    """Audit log for each scraper task execution."""
    __tablename__ = "scraper_runs"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    run_timestamp = Column(DateTime(timezone=True), nullable=False)
    source = Column(String(30), nullable=False)
    origin = Column(String(3), nullable=False)
    destination = Column(String(3), nullable=False)
    advance_days = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False)
    records_written = Column(Integer)
    error_message = Column(Text)
    raw_file_path = Column(Text)

    __table_args__ = (
        # Indexes required to query 750 entries/day by source or route efficiently
        Index("ix_sr_source", "source"),
        Index("ix_sr_route", "origin", "destination"),
        Index("ix_sr_timestamp", "run_timestamp"),
        {"extend_existing": True},
    )


class CpiOfficial(Base):
    """Official MoSPI CPI airfare monthly series (eSankhyiki)."""
    __tablename__ = "cpi_official"

    year = Column(Integer, primary_key=True)
    month = Column(Integer, primary_key=True)
    state = Column(String(100), primary_key=True)
    sector = Column(String(20), primary_key=True)
    item_code = Column(String(30), primary_key=True, default="07.3.3.1.2.01")
    base_year = Column(Integer, default=2024)
    index_value = Column(Numeric(10, 2), nullable=False)
    inflation = Column(Numeric(10, 2), nullable=True)
    imputed = Column(Boolean, default=False)

