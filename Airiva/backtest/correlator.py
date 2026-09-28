"""
correlator.py — Correlate APIx monthly index against DGCA published avg fares.

Steps:
  1. Load monthly APIx from apix_monthly DB table
  2. Load DGCA monthly avg fares from dgca_parser output
  3. Join on (year, month, route)
  4. Compute Pearson r and Spearman ρ for composite and per-route
  5. Return a correlation summary dict + merged DataFrame
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import pandas as pd
from scipy import stats
from sqlalchemy import select

from apix.pipeline.db import AsyncSessionLocal, ApixMonthly

logger = logging.getLogger(__name__)


async def _load_apix_monthly() -> pd.DataFrame:
    """Load all apix_monthly records into a DataFrame."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ApixMonthly)
        )
        rows = result.scalars().all()

    if not rows:
        return pd.DataFrame(columns=["year", "month", "index_value", "del_bom", "del_blr", "bom_blr"])

    return pd.DataFrame([
        {
            "year": r.year,
            "month": r.month,
            "index_value": float(r.index_value),
            "del_bom": float(r.del_bom) if r.del_bom else None,
            "del_blr": float(r.del_blr) if r.del_blr else None,
            "bom_blr": float(r.bom_blr) if r.bom_blr else None,
        }
        for r in rows
    ])


def compute_correlation(
    apix_monthly: pd.DataFrame,
    dgca_monthly: pd.DataFrame,
) -> dict:
    """
    Join APIx monthly index against DGCA avg fares and compute correlation.

    Parameters
    ----------
    apix_monthly : columns [year, month, index_value, del_bom, del_blr, bom_blr]
    dgca_monthly : columns [year, month, route, avg_fare_inr]

    Returns
    -------
    dict with keys:
        merged_df       : joined DataFrame
        pearson_r       : float (composite index vs DGCA composite avg)
        pearson_p       : float (p-value)
        spearman_rho    : float
        spearman_p      : float
        route_correlations : dict per route
    """
    if apix_monthly.empty or dgca_monthly.empty:
        logger.warning("correlator: empty data — cannot compute correlations")
        return {
            "merged_df": pd.DataFrame(),
            "pearson_r": None,
            "pearson_p": None,
            "spearman_rho": None,
            "spearman_p": None,
            "route_correlations": {},
        }

    # Pivot DGCA data: (year, month) × route
    dgca_pivot = dgca_monthly.pivot_table(
        index=["year", "month"],
        columns="route",
        values="avg_fare_inr",
        aggfunc="mean",
    ).reset_index()
    dgca_pivot.columns.name = None

    # DGCA composite avg: weighted mean across routes (equal weight for now)
    route_cols = [c for c in dgca_pivot.columns if c in ["DEL-BOM", "DEL-BLR", "BOM-BLR"]]
    if route_cols:
        dgca_pivot["dgca_composite"] = dgca_pivot[route_cols].mean(axis=1)

    # Merge
    merged = apix_monthly.merge(dgca_pivot, on=["year", "month"], how="inner")

    if merged.empty or "dgca_composite" not in merged.columns:
        logger.warning("correlator: no overlapping data after join")
        return {
            "merged_df": merged,
            "pearson_r": None,
            "pearson_p": None,
            "spearman_rho": None,
            "spearman_p": None,
            "route_correlations": {},
        }

    valid = merged.dropna(subset=["index_value", "dgca_composite"])
    if len(valid) < 3:
        logger.warning("correlator: only %d overlapping months — need >= 3", len(valid))
        return {
            "merged_df": merged,
            "pearson_r": None,
            "pearson_p": None,
            "spearman_rho": None,
            "spearman_p": None,
            "route_correlations": {},
        }

    # Composite correlations
    pearson_r, pearson_p = stats.pearsonr(valid["index_value"], valid["dgca_composite"])
    spearman_rho, spearman_p = stats.spearmanr(valid["index_value"], valid["dgca_composite"])

    # Per-route correlations
    route_corrs = {}
    route_apix_map = {"DEL-BOM": "del_bom", "DEL-BLR": "del_blr", "BOM-BLR": "bom_blr"}
    for route, apix_col in route_apix_map.items():
        if route not in merged.columns or apix_col not in merged.columns:
            continue
        v = merged.dropna(subset=[apix_col, route])
        if len(v) < 3:
            continue
        r, p = stats.pearsonr(v[apix_col], v[route])
        rho, rp = stats.spearmanr(v[apix_col], v[route])
        route_corrs[route] = {"pearson_r": r, "pearson_p": p, "spearman_rho": rho, "spearman_p": rp}

    logger.info(
        "correlator: Pearson r=%.4f (p=%.4f), Spearman ρ=%.4f (p=%.4f) [n=%d months]",
        pearson_r, pearson_p, spearman_rho, spearman_p, len(valid),
    )

    return {
        "merged_df": merged,
        "pearson_r": pearson_r,
        "pearson_p": pearson_p,
        "spearman_rho": spearman_rho,
        "spearman_p": spearman_p,
        "route_correlations": route_corrs,
    }


async def run_correlation(dgca_monthly: pd.DataFrame) -> dict:
    """Async wrapper: load APIx monthly from DB and correlate with DGCA data."""
    apix_monthly = await _load_apix_monthly()
    return compute_correlation(apix_monthly, dgca_monthly)
