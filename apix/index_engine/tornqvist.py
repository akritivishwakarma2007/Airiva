"""
tornqvist.py — Törnqvist price index computation.

Formula (discrete log-change form):
  ln(P_t / P_0) = Σ_i [ (s_i,0 + s_i,t) / 2 × ln(p_i,t / p_i,0) ]

Where:
  i         = route index (DEL-BOM, DEL-BLR, BOM-BLR)
  s_i,0     = route expenditure share in the base period
  s_i,t     = route expenditure share in period t
  p_i,0     = median total_fare for route i in the base period
  p_i,t     = median total_fare for route i in period t
  P_t/P_0   = composite index ratio
  Index     = exp(ln ratio) × 100  (base period = 100)

Expenditure share for a route on a given day:
  s_i,t = w_i × p_i,t / Σ_j (w_j × p_j,t)
where w_i is the DGCA traffic weight (constant across periods).

Only non-censored, non-outlier, non-duplicate records enter price calculation.
If a route has no valid records on a given day, it is excluded from that
day's index and its weight is redistributed proportionally.

See also: apix/index_engine/formula.md
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class RoutePriceData:
    """Price data for one route on one day."""
    route: str
    median_fare: float          # median of valid total_fare records
    weight: float               # DGCA traffic weight (constant)
    sample_size: int            # number of valid records used


@dataclass
class IndexResult:
    """Output of one Törnqvist index computation."""
    index_value: float          # composite index (base = 100)
    route_values: Dict[str, float]  # per-route sub-index values
    composite_log_change: float
    sample_size: int
    missing_routes: list[str]


def compute_tornqvist(
    base_data: Dict[str, RoutePriceData],
    current_data: Dict[str, RoutePriceData],
) -> IndexResult:
    """
    Compute the Törnqvist index for one period relative to the base period.

    Parameters
    ----------
    base_data    : {route_key: RoutePriceData} for the base period
    current_data : {route_key: RoutePriceData} for the current period

    Returns IndexResult with composite index (base=100) and per-route values.
    """
    routes = list(base_data.keys())
    missing: list[str] = []

    # Compute expenditure shares for base and current periods
    def expenditure_shares(data: Dict[str, RoutePriceData]) -> Dict[str, float]:
        total_expenditure = sum(d.weight * d.median_fare for d in data.values())
        if total_expenditure == 0:
            return {r: 1.0 / len(data) for r in data}
        return {
            r: (d.weight * d.median_fare) / total_expenditure
            for r, d in data.items()
        }

    # Only include routes with valid data in BOTH periods
    common_routes = [
        r for r in routes
        if r in current_data
        and base_data[r].median_fare > 0
        and current_data[r].median_fare > 0
    ]
    missing = [r for r in routes if r not in common_routes]

    if not common_routes:
        logger.warning("tornqvist: no common routes with valid data — returning index=100")
        return IndexResult(
            index_value=100.0,
            route_values={},
            composite_log_change=0.0,
            sample_size=0,
            missing_routes=missing,
        )

    base_sub = {r: base_data[r] for r in common_routes}
    curr_sub = {r: current_data[r] for r in common_routes}

    s0 = expenditure_shares(base_sub)
    st = expenditure_shares(curr_sub)

    # Törnqvist composite log change
    composite_log = 0.0
    route_values: Dict[str, float] = {}

    for r in common_routes:
        p0 = base_data[r].median_fare
        pt = current_data[r].median_fare
        avg_share = (s0[r] + st[r]) / 2.0

        if p0 <= 0 or pt <= 0:
            logger.warning("tornqvist: zero fare for route %s — skipping", r)
            continue

        log_change = math.log(pt / p0)
        composite_log += avg_share * log_change

        # Per-route sub-index (relative to base on this specific route)
        route_values[r] = math.exp(log_change) * 100.0

        logger.debug(
            "tornqvist: route=%s p0=%.2f pt=%.2f avg_share=%.4f log_change=%.4f",
            r, p0, pt, avg_share, log_change,
        )

    if missing:
        logger.warning("tornqvist: missing routes %s — weights redistributed", missing)

    index_value = math.exp(composite_log) * 100.0
    total_samples = sum(d.sample_size for d in curr_sub.values())

    logger.info(
        "tornqvist: index=%.4f log_change=%.4f routes=%s missing=%s",
        index_value, composite_log, common_routes, missing,
    )

    return IndexResult(
        index_value=index_value,
        route_values=route_values,
        composite_log_change=composite_log,
        sample_size=total_samples,
        missing_routes=missing,
    )


def build_route_price_data(
    fares_by_route: Dict[str, list[float]],
    weights: Dict[str, float],
) -> Dict[str, RoutePriceData]:
    """
    Helper: build RoutePriceData dicts from raw fare lists per route.

    Parameters
    ----------
    fares_by_route : {route_key: [total_fare, …]} — valid fares only
    weights        : {route_key: float} — DGCA traffic weights

    Returns dict suitable for passing to compute_tornqvist().
    """
    import statistics

    result: Dict[str, RoutePriceData] = {}
    for route, fares in fares_by_route.items():
        if not fares:
            continue
        result[route] = RoutePriceData(
            route=route,
            median_fare=statistics.median(fares),
            weight=weights.get(route, 0.0),
            sample_size=len(fares),
        )
    return result
