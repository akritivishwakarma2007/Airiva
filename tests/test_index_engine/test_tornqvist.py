"""
test_tornqvist.py — Tests for apix.index_engine.tornqvist
"""
from __future__ import annotations

import math
import pytest

from apix.index_engine.tornqvist import (
    RoutePriceData,
    IndexResult,
    compute_tornqvist,
    build_route_price_data,
)

WEIGHTS = {"DEL-BOM": 0.370, "DEL-BLR": 0.355, "BOM-BLR": 0.275}


def _make_price_data(route_fares: dict[str, float]) -> dict[str, RoutePriceData]:
    return {
        route: RoutePriceData(
            route=route,
            median_fare=fare,
            weight=WEIGHTS[route],
            sample_size=10,
        )
        for route, fare in route_fares.items()
    }


class TestTornqvistFormula:
    def test_base_period_equals_100(self):
        """When base and current period are identical, index must equal 100."""
        base_fares    = {"DEL-BOM": 5000.0, "DEL-BLR": 4800.0, "BOM-BLR": 4500.0}
        base_data     = _make_price_data(base_fares)
        current_data  = _make_price_data(base_fares)  # same as base

        result = compute_tornqvist(base_data, current_data)
        assert abs(result.index_value - 100.0) < 1e-6, \
            f"Expected 100.0, got {result.index_value}"

    def test_uniform_10pct_increase(self):
        """When all fares rise by 10%, composite index should ≈ 110."""
        base_fares    = {"DEL-BOM": 5000.0, "DEL-BLR": 4800.0, "BOM-BLR": 4500.0}
        curr_fares    = {k: v * 1.10 for k, v in base_fares.items()}
        result = compute_tornqvist(
            _make_price_data(base_fares),
            _make_price_data(curr_fares),
        )
        assert abs(result.index_value - 110.0) < 0.01, \
            f"Expected ~110.0, got {result.index_value}"

    def test_uniform_20pct_decrease(self):
        """When all fares fall by 20%, composite index should ≈ 80."""
        base_fares    = {"DEL-BOM": 5000.0, "DEL-BLR": 4800.0, "BOM-BLR": 4500.0}
        curr_fares    = {k: v * 0.80 for k, v in base_fares.items()}
        result = compute_tornqvist(
            _make_price_data(base_fares),
            _make_price_data(curr_fares),
        )
        assert abs(result.index_value - 80.0) < 0.01

    def test_log_change_additivity(self):
        """
        Törnqvist log changes must sum to the composite log change.
        This verifies the additive decomposition property.
        """
        base_fares = {"DEL-BOM": 5000.0, "DEL-BLR": 4800.0, "BOM-BLR": 4500.0}
        curr_fares = {"DEL-BOM": 5500.0, "DEL-BLR": 4600.0, "BOM-BLR": 4700.0}
        result = compute_tornqvist(
            _make_price_data(base_fares),
            _make_price_data(curr_fares),
        )
        expected_log = math.log(result.index_value / 100.0)
        assert abs(result.composite_log_change - expected_log) < 1e-9

    def test_per_route_sub_indices(self):
        """Each route sub-index should reflect that route's price change."""
        base_fares = {"DEL-BOM": 5000.0, "DEL-BLR": 4800.0, "BOM-BLR": 4500.0}
        curr_fares = {"DEL-BOM": 6000.0, "DEL-BLR": 4800.0, "BOM-BLR": 4500.0}
        result = compute_tornqvist(
            _make_price_data(base_fares),
            _make_price_data(curr_fares),
        )
        # DEL-BOM rose 20% → sub-index ≈ 120
        assert abs(result.route_values["DEL-BOM"] - 120.0) < 0.01
        # DEL-BLR unchanged → sub-index ≈ 100
        assert abs(result.route_values["DEL-BLR"] - 100.0) < 0.01

    def test_missing_route_handled(self):
        """When a route is missing from current data, result is still valid."""
        base_fares = {"DEL-BOM": 5000.0, "DEL-BLR": 4800.0, "BOM-BLR": 4500.0}
        curr_fares = {"DEL-BOM": 5500.0, "DEL-BLR": 4900.0}  # BOM-BLR missing
        result = compute_tornqvist(
            _make_price_data(base_fares),
            _make_price_data(curr_fares),
        )
        assert "BOM-BLR" in result.missing_routes
        assert result.index_value > 0  # still computes with remaining routes

    def test_no_data_returns_100(self):
        """When no routes have valid data in both periods, returns 100."""
        base_data = _make_price_data({"DEL-BOM": 5000.0})
        curr_data = {}  # nothing
        result = compute_tornqvist(base_data, curr_data)
        assert result.index_value == 100.0

    def test_sample_size_summed(self):
        """sample_size must equal sum of sample sizes in current_data."""
        base_fares = {"DEL-BOM": 5000.0, "DEL-BLR": 4800.0, "BOM-BLR": 4500.0}
        result = compute_tornqvist(
            _make_price_data(base_fares),
            _make_price_data(base_fares),
        )
        assert result.sample_size == 30  # 3 routes × 10 each


class TestBuildRoutePriceData:
    def test_median_computed_correctly(self):
        fares_by_route = {
            "DEL-BOM": [4000.0, 5000.0, 6000.0],  # median = 5000
            "DEL-BLR": [4500.0, 4500.0],           # median = 4500
        }
        result = build_route_price_data(fares_by_route, WEIGHTS)
        assert result["DEL-BOM"].median_fare == 5000.0
        assert result["DEL-BLR"].median_fare == 4500.0

    def test_empty_route_excluded(self):
        fares = {"DEL-BOM": [5000.0], "DEL-BLR": []}
        result = build_route_price_data(fares, WEIGHTS)
        assert "DEL-BOM" in result
        assert "DEL-BLR" not in result

    def test_weights_assigned(self):
        fares = {"DEL-BOM": [5000.0], "BOM-BLR": [4500.0]}
        result = build_route_price_data(fares, WEIGHTS)
        assert result["DEL-BOM"].weight == WEIGHTS["DEL-BOM"]
