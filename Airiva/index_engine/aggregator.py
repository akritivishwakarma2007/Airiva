"""
aggregator.py — Daily → Weekly → Monthly index rollup.

Daily index values are computed by tornqvist.py and stored in apix_daily.
Weekly and monthly values are geometric means of daily index values within
the respective period.

Geometric mean is used (not arithmetic) because the Törnqvist index itself
is defined in log-change space — aggregating by geometric mean preserves
the log-additive property.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)


def geometric_mean(values: list[float]) -> float:
    """Compute the geometric mean of a list of positive values."""
    if not values:
        return 100.0
    log_sum = sum(math.log(v) for v in values if v > 0)
    return math.exp(log_sum / len(values))


def aggregate_weekly(
    daily_records: list[dict],
) -> list[dict]:
    """
    Aggregate daily index records to ISO weeks.

    Parameters
    ----------
    daily_records : list of dicts with keys:
        index_date (date), index_value (float), del_bom, del_blr, bom_blr

    Returns list of weekly records with keys:
        iso_year, iso_week, week_start_date, index_value, del_bom, del_blr, bom_blr
    """
    groups: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for rec in daily_records:
        d = rec["index_date"]
        if isinstance(d, str):
            d = date.fromisoformat(d)
        iso_cal = d.isocalendar()
        groups[(iso_cal.year, iso_cal.week)].append(rec)

    weekly = []
    for (iso_year, iso_week), recs in sorted(groups.items()):
        # Week start = Monday of that ISO week
        week_start = date.fromisocalendar(iso_year, iso_week, 1)
        weekly.append({
            "iso_year": iso_year,
            "iso_week": iso_week,
            "week_start_date": week_start,
            "index_value": geometric_mean([r["index_value"] for r in recs]),
            "del_bom": geometric_mean([r["del_bom"] for r in recs if r.get("del_bom")]),
            "del_blr": geometric_mean([r["del_blr"] for r in recs if r.get("del_blr")]),
            "bom_blr": geometric_mean([r["bom_blr"] for r in recs if r.get("bom_blr")]),
        })

    logger.info("aggregator: %d daily → %d weekly records", len(daily_records), len(weekly))
    return weekly


def aggregate_monthly(
    daily_records: list[dict],
) -> list[dict]:
    """
    Aggregate daily index records to calendar months.

    Returns list of monthly records with keys:
        year, month, index_value, del_bom, del_blr, bom_blr
    """
    groups: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for rec in daily_records:
        d = rec["index_date"]
        if isinstance(d, str):
            d = date.fromisoformat(d)
        groups[(d.year, d.month)].append(rec)

    monthly = []
    for (year, month), recs in sorted(groups.items()):
        monthly.append({
            "year": year,
            "month": month,
            "index_value": geometric_mean([r["index_value"] for r in recs]),
            "del_bom": geometric_mean([r["del_bom"] for r in recs if r.get("del_bom")]),
            "del_blr": geometric_mean([r["del_blr"] for r in recs if r.get("del_blr")]),
            "bom_blr": geometric_mean([r["bom_blr"] for r in recs if r.get("bom_blr")]),
        })

    logger.info("aggregator: %d daily → %d monthly records", len(daily_records), len(monthly))
    return monthly


def daily_records_from_df(df: pd.DataFrame) -> list[dict]:
    """Convert a pandas DataFrame with apix_daily columns to list of dicts."""
    return df.to_dict("records")
