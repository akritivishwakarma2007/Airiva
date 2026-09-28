"""
weights.py — Load and normalise DGCA route traffic weights.

Source: DGCA Domestic City-Pair Traffic Statistics 2025-2026 (monthly xlsx files).
File: data/weights/dgca_route_weights.csv

Expected CSV columns:
  route       — e.g. "DEL-BOM"
  pax_share   — fractional passenger share (0..1), or raw pax count

All routes in the weights file are loaded and normalised to sum to 1.0.
If raw pax counts are provided instead of shares, they are converted automatically.

Fallback: if the weights file is missing, top-3 DGCA pilot shares are used
as static defaults for backward-compat (3-route mode).

Full basket: 30 DGCA-weighted domestic corridors (Jan 2025 – Aug 2026 data).
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from apix.config import settings

logger = logging.getLogger(__name__)

# DGCA 2022-23 approximate domestic passenger shares for 3 original pilot routes.
# Used as static fallback if weights CSV is missing.
_STATIC_FALLBACK: dict[str, float] = {
    "DEL-BOM": 0.370,
    "DEL-BLR": 0.355,
    "BOM-BLR": 0.275,
}

# Legacy constant retained for backward-compat with tests that import it
PILOT_ROUTES = ["DEL-BOM", "DEL-BLR", "BOM-BLR"]

# Full 30-route basket (used for filtering when routes list is needed)
ALL_BASKET_ROUTES = [
    "DEL-BOM", "DEL-BLR", "BOM-BLR", "DEL-HYD", "DEL-PNQ", "DEL-CCU",
    "BOM-GOI", "DEL-AMD", "DEL-GOI", "BLR-HYD", "DEL-MAA", "BOM-CCU",
    "BOM-HYD", "BOM-MAA", "BLR-CCU", "BOM-AMD", "BLR-PNQ", "DEL-SXR",
    "DEL-PAT", "DEL-GAU", "BLR-GOI", "BLR-MAA", "HYD-MAA", "BLR-COK",
    "DEL-LKO", "HYD-GOI", "BOM-COK", "DEL-BBI", "DEL-IXB", "BLR-AMD",
]


def load_weights(weights_file: Path | None = None) -> dict[str, float]:
    """
    Load route weights from CSV, normalised to sum to 1.0.

    Returns a dict mapping route codes (e.g. "DEL-BOM") → float weight.
    Loads ALL routes present in the CSV (not limited to pilot routes).
    """
    path = weights_file or Path(settings.weights_file)

    if not path.exists():
        logger.warning(
            "weights.py: %s not found — using static DGCA 3-route fallback weights",
            path,
        )
        return _normalize(_STATIC_FALLBACK)

    try:
        df = pd.read_csv(path, comment="#")
        df.columns = [c.strip().lower() for c in df.columns]

        # Flexible column detection
        route_col = next((c for c in df.columns if "route" in c), None)
        share_col = next(
            (c for c in df.columns if any(k in c for k in ("share", "pax", "passenger", "weight"))),
            None,
        )

        if route_col is None or share_col is None:
            raise ValueError(f"Cannot find route/share columns in {path}. Columns: {list(df.columns)}")

        df = df[[route_col, share_col]].rename(columns={route_col: "route", share_col: "pax_share"})
        df["route"] = df["route"].str.strip().str.upper().str.replace(" ", "")
        df = df.dropna(subset=["route", "pax_share"])
        df = df[df["route"].str.match(r"^[A-Z]{3}-[A-Z]{3}$")]  # Valid IATA-IATA only

        if df.empty:
            raise ValueError("No valid IATA routes found in weights file")

        weights = dict(zip(df["route"], df["pax_share"].astype(float)))
        logger.info("weights.py: Loaded %d routes from %s", len(weights), path)

        return _normalize(weights)

    except Exception as exc:
        logger.error("weights.py: failed to load %s (%s) — using static fallback", path, exc)
        return _normalize(_STATIC_FALLBACK)


def get_active_routes(weights: dict[str, float] | None = None) -> list[str]:
    """
    Return ordered list of active routes (intersection of config routes and weights).
    Falls back to weights keys if no config routes specified.
    """
    if weights is None:
        weights = load_weights()
    config_routes = [f"{o}-{d}" for o, d in settings.routes]
    active = [r for r in config_routes if r in weights]
    if not active:
        active = list(weights.keys())
    return active


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    """Ensure weights sum to 1.0."""
    total = sum(weights.values())
    if total == 0:
        raise ValueError("Route weights sum to zero")
    return {k: v / total for k, v in weights.items()}
