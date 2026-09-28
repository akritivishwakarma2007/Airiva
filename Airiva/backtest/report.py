"""
report.py — Generate the backtest correlation chart and print summary stats.

Produces a dual-axis Matplotlib overlay chart:
  Left axis:  APIx composite monthly index
  Right axis: DGCA published average fare (INR)

Also generates per-route comparison subplots.

Usage:
  python -m apix.backtest.report
  python -m apix.backtest.report --pdf-dir apix/backtest/data/
  python -m apix.backtest.report --use-synthetic   # use seed data if no PDFs
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from apix.config import settings

logger = logging.getLogger(__name__)

# ── Synthetic DGCA data for dev/test (when no PDFs available) ────────────────
_SYNTHETIC_DGCA = pd.DataFrame([
    # Approximate published DGCA monthly avg fares (INR), 2024
    {"year": 2024, "month": 1, "route": "DEL-BOM", "avg_fare_inr": 5420},
    {"year": 2024, "month": 1, "route": "DEL-BLR", "avg_fare_inr": 5180},
    {"year": 2024, "month": 1, "route": "BOM-BLR", "avg_fare_inr": 4890},
    {"year": 2024, "month": 2, "route": "DEL-BOM", "avg_fare_inr": 5650},
    {"year": 2024, "month": 2, "route": "DEL-BLR", "avg_fare_inr": 5320},
    {"year": 2024, "month": 2, "route": "BOM-BLR", "avg_fare_inr": 5010},
    {"year": 2024, "month": 3, "route": "DEL-BOM", "avg_fare_inr": 6100},
    {"year": 2024, "month": 3, "route": "DEL-BLR", "avg_fare_inr": 5780},
    {"year": 2024, "month": 3, "route": "BOM-BLR", "avg_fare_inr": 5430},
    {"year": 2024, "month": 4, "route": "DEL-BOM", "avg_fare_inr": 5890},
    {"year": 2024, "month": 4, "route": "DEL-BLR", "avg_fare_inr": 5560},
    {"year": 2024, "month": 4, "route": "BOM-BLR", "avg_fare_inr": 5230},
    {"year": 2024, "month": 5, "route": "DEL-BOM", "avg_fare_inr": 5220},
    {"year": 2024, "month": 5, "route": "DEL-BLR", "avg_fare_inr": 4980},
    {"year": 2024, "month": 5, "route": "BOM-BLR", "avg_fare_inr": 4700},
    {"year": 2024, "month": 6, "route": "DEL-BOM", "avg_fare_inr": 4950},
    {"year": 2024, "month": 6, "route": "DEL-BLR", "avg_fare_inr": 4720},
    {"year": 2024, "month": 6, "route": "BOM-BLR", "avg_fare_inr": 4480},
])

_MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _make_x_labels(df: pd.DataFrame) -> list[str]:
    return [f"{_MONTH_LABELS[int(m)-1]} {y}" for y, m in zip(df["year"], df["month"])]


def generate_report(correlation_result: dict, output_path: Path) -> None:
    """
    Generate and save the backtest chart to output_path (PNG).
    """
    merged = correlation_result.get("merged_df", pd.DataFrame())
    pearson_r = correlation_result.get("pearson_r")
    spearman_rho = correlation_result.get("spearman_rho")
    route_corrs = correlation_result.get("route_correlations", {})

    # ── Print summary ─────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("  APIx Backtest Report — vs. DGCA Published Avg Fares")
    print("="*60)

    if pearson_r is not None:
        print(f"\n  Composite Index Correlation (n={len(merged)} months):")
        print(f"    Pearson  r  = {pearson_r:.4f}  (p={correlation_result['pearson_p']:.4f})")
        print(f"    Spearman ρ  = {spearman_rho:.4f}  (p={correlation_result['spearman_p']:.4f})")
    else:
        print("\n  Insufficient data for correlation (need ≥3 overlapping months)")

    if route_corrs:
        print("\n  Per-Route Pearson r:")
        for route, corr in route_corrs.items():
            print(f"    {route}: r={corr['pearson_r']:.4f}  (p={corr['pearson_p']:.4f})")

    print("="*60 + "\n")

    if merged.empty or "dgca_composite" not in merged.columns:
        logger.warning("report: no merged data — generating placeholder chart")
        merged = pd.DataFrame({"year": [2024], "month": [1], "index_value": [100], "dgca_composite": [5300]})

    # ── Main overlay chart ────────────────────────────────────────────────────
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        "APIx vs. DGCA Published Average Fare — Backtest",
        fontsize=15, fontweight="bold", y=0.98,
    )

    x_labels = _make_x_labels(merged)
    x = np.arange(len(merged))

    # ── Top-left: composite overlay ───────────────────────────────────────────
    ax1 = axes[0, 0]
    ax2 = ax1.twinx()

    ax1.plot(x, merged["index_value"], color="#2196F3", marker="o", linewidth=2, label="APIx Index (left)")
    ax2.plot(x, merged["dgca_composite"], color="#FF5722", marker="s", linewidth=2,
             linestyle="--", label="DGCA Avg Fare ₹ (right)")

    ax1.set_ylabel("APIx Index (base=100)", color="#2196F3")
    ax2.set_ylabel("DGCA Avg Fare (₹)", color="#FF5722")
    ax1.set_xticks(x)
    ax1.set_xticklabels(x_labels, rotation=45, ha="right", fontsize=8)
    ax1.set_title(
        f"Composite  |  r={pearson_r:.3f}" if pearson_r else "Composite Index",
        fontsize=10,
    )
    ax1.legend(loc="upper left", fontsize=8)
    ax2.legend(loc="upper right", fontsize=8)
    ax1.grid(alpha=0.3)

    # ── Route sub-plots ───────────────────────────────────────────────────────
    route_map = [
        ("DEL-BOM", "del_bom", axes[0, 1]),
        ("DEL-BLR", "del_blr", axes[1, 0]),
        ("BOM-BLR", "bom_blr", axes[1, 1]),
    ]
    colors = ["#4CAF50", "#9C27B0", "#FF9800"]

    for (route, apix_col, ax), color in zip(route_map, colors):
        ax_r = ax.twinx()
        if apix_col in merged.columns:
            ax.plot(x, merged[apix_col].fillna(method="ffill"), color=color,
                    marker="o", linewidth=2, label="APIx sub-index")
        if route in merged.columns:
            ax_r.plot(x, merged[route].fillna(method="ffill"), color="#795548",
                      marker="s", linewidth=1.5, linestyle="--", label="DGCA ₹")

        rc = route_corrs.get(route, {})
        r_str = f"r={rc['pearson_r']:.3f}" if rc.get("pearson_r") is not None else "n/a"
        ax.set_title(f"{route}  |  {r_str}", fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels(x_labels, rotation=45, ha="right", fontsize=7)
        ax.set_ylabel("APIx sub-index", color=color, fontsize=8)
        ax_r.set_ylabel("DGCA Avg Fare (₹)", color="#795548", fontsize=8)
        ax.legend(loc="upper left", fontsize=7)
        ax_r.legend(loc="upper right", fontsize=7)
        ax.grid(alpha=0.3)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Chart saved → {output_path}\n")


async def _run(pdf_dir: Path, use_synthetic: bool, output: Path) -> None:
    from apix.backtest.dgca_parser import parse_dgca_pdfs
    from apix.backtest.correlator import run_correlation

    if use_synthetic or not any(pdf_dir.glob("*.pdf")):
        logger.info("Using synthetic DGCA data (no PDFs found in %s)", pdf_dir)
        dgca_df = _SYNTHETIC_DGCA
    else:
        dgca_df = parse_dgca_pdfs(pdf_dir)

    correlation_result = await run_correlation(dgca_df)
    generate_report(correlation_result, output)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="APIx Backtest Report")
    parser.add_argument("--pdf-dir", default=str(settings.dgca_pdf_dir))
    parser.add_argument("--use-synthetic", action="store_true")
    parser.add_argument("--output", default="data/backtest_report.png")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level="INFO", format="%(asctime)s [%(levelname)s] %(message)s")
    args = _parse_args()
    asyncio.run(_run(Path(args.pdf_dir), args.use_synthetic, Path(args.output)))
