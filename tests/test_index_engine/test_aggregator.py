"""
test_aggregator.py — Tests for apix.index_engine.aggregator
"""
from __future__ import annotations

import math
import pytest
from datetime import date

from apix.index_engine.aggregator import (
    aggregate_weekly,
    aggregate_monthly,
    geometric_mean,
)


def _daily(index_date: str, index_value: float, del_bom=None, del_blr=None, bom_blr=None) -> dict:
    return {
        "index_date": date.fromisoformat(index_date),
        "index_value": index_value,
        "del_bom": del_bom,
        "del_blr": del_blr,
        "bom_blr": bom_blr,
    }


class TestGeometricMean:
    def test_known_values(self):
        # geo mean of (100, 121) = sqrt(100*121) = 110
        assert abs(geometric_mean([100.0, 121.0]) - 110.0) < 1e-6

    def test_single_value(self):
        assert geometric_mean([105.0]) == pytest.approx(105.0)

    def test_empty_list(self):
        assert geometric_mean([]) == 100.0

    def test_equal_values(self):
        assert geometric_mean([110.0, 110.0, 110.0]) == pytest.approx(110.0)


class TestAggregateWeekly:
    def test_groups_into_correct_week_count(self):
        # 14 days spanning 2 ISO weeks → 2 weekly records
        records = [_daily(f"2026-09-{7+i:02d}", 100.0 + i) for i in range(14)]
        weekly = aggregate_weekly(records)
        assert len(weekly) >= 2

    def test_geometric_mean_applied(self):
        # Single week with values 100 and 121 → geo mean = 110
        records = [
            _daily("2026-09-07", 100.0),  # Mon
            _daily("2026-09-08", 121.0),  # Tue
        ]
        weekly = aggregate_weekly(records)
        assert len(weekly) == 1
        assert abs(weekly[0]["index_value"] - 110.0) < 0.01

    def test_week_start_is_monday(self):
        records = [_daily("2026-09-09", 105.0)]  # Wednesday
        weekly = aggregate_weekly(records)
        assert weekly[0]["week_start_date"].weekday() == 0  # Monday

    def test_output_keys_present(self):
        records = [_daily("2026-09-07", 102.0, del_bom=101.0, del_blr=103.0, bom_blr=99.0)]
        weekly = aggregate_weekly(records)
        row = weekly[0]
        assert "iso_year" in row
        assert "iso_week" in row
        assert "week_start_date" in row
        assert "index_value" in row

    def test_empty_input(self):
        assert aggregate_weekly([]) == []


class TestAggregateMonthly:
    def test_two_months_produce_two_records(self):
        records = (
            [_daily(f"2026-08-{i+1:02d}", 100.0 + i) for i in range(5)] +
            [_daily(f"2026-09-{i+1:02d}", 110.0 + i) for i in range(5)]
        )
        monthly = aggregate_monthly(records)
        assert len(monthly) == 2

    def test_month_index_geometric_mean(self):
        # September with only 2 values: 100 and 121 → geo = 110
        records = [_daily("2026-09-01", 100.0), _daily("2026-09-02", 121.0)]
        monthly = aggregate_monthly(records)
        assert len(monthly) == 1
        assert abs(monthly[0]["index_value"] - 110.0) < 0.01

    def test_output_keys_present(self):
        records = [_daily("2026-09-01", 105.0, del_bom=104.0)]
        monthly = aggregate_monthly(records)
        assert "year" in monthly[0]
        assert "month" in monthly[0]
        assert "index_value" in monthly[0]

    def test_year_month_correct(self):
        records = [_daily("2026-08-15", 102.5)]
        monthly = aggregate_monthly(records)
        assert monthly[0]["year"] == 2026
        assert monthly[0]["month"] == 8

    def test_empty_input(self):
        assert aggregate_monthly([]) == []

    def test_single_year_ordered(self):
        records = (
            [_daily("2026-09-01", 100.0)] +
            [_daily("2026-08-01", 98.0)] +
            [_daily("2026-10-01", 103.0)]
        )
        monthly = aggregate_monthly(records)
        months = [r["month"] for r in monthly]
        assert months == sorted(months), "Monthly records should be in chronological order"
