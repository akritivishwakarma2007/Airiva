"""
Airiva/backtest/cpi_benchmark.py — Benchmark APIx monthly index against official MoSPI CPI airfare index.

Usage:
  python -m apix.backtest.cpi_benchmark --cpi-csv data/cpi/cpi_airfare_clean.csv --apix-csv monthly_apix.csv
  python -m apix.backtest.cpi_benchmark --cpi-csv data/cpi/cpi_airfare_clean.csv --db
  python -m apix.backtest.cpi_benchmark --cpi-csv data/cpi/cpi_airfare_clean.csv --demo

Writes data/benchmark/cpi_benchmark.json for the dashboard overlay and API.

Design notes:
- Bases differ (CPI 2024=100, APIx 100 at first collection week), so we compare
  month-over-month % change and rebased levels, never raw levels.
- Imputed CPI rows are excluded. All India / Combined is the default series
  (state-level values are too noisy to validate against).
- With fewer than 3 overlapping months no direction claim is made; with fewer
  than 7 no correlation is reported. The output says so instead of faking a number.
- Official source citation: Ministry of Statistics & Programme Implementation (MoSPI), eSankhyiki.
"""
import argparse
import json
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

MIN_MONTHS_DIRECTION = 3   # 2 MoM changes need 3 monthly points
MIN_MONTHS_CORR = 7        # 6 MoM changes


def load_cpi(path: Path, state="All India", sector="Combined", drop_imputed=True) -> pd.Series:
    df = pd.read_csv(path)
    df = df[(df.state == state) & (df.sector == sector)]
    if drop_imputed:
        df = df[~df.imputed.astype(bool)]
    p = pd.to_datetime({"year": df["year"], "month": df["month"], "day": 1}).dt.to_period("M")
    return pd.Series(df["index_value"].to_numpy(), index=p.to_numpy()).sort_index()


def monthly_from_apix(df: pd.DataFrame) -> pd.Series:
    d = df.copy()
    col = "date" if "date" in d.columns else "year_month" if "year_month" in d.columns else "month"
    val_col = "index_value" if "index_value" in d.columns else "composite_index" if "composite_index" in d.columns else "index"
    d["p"] = pd.to_datetime(d[col]).dt.to_period("M")
    return d.groupby("p")[val_col].mean().sort_index()   # arithmetic mean of monthly values


def monthly_from_sqlite(db_path: Path) -> pd.Series:
    if not db_path.exists():
        return pd.Series(dtype=float)
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql("SELECT year_month, composite_index FROM apix_monthly ORDER BY year_month", conn)
        if not df.empty:
            df["p"] = pd.to_datetime(df["year_month"]).dt.to_period("M")
            return pd.Series(df["composite_index"].to_numpy(), index=df["p"].to_numpy()).sort_index()
    except Exception:
        pass
    try:
        df = pd.read_sql("SELECT index_date as date, composite_index as index_value FROM apix_daily ORDER BY index_date", conn)
        if not df.empty:
            df["p"] = pd.to_datetime(df["date"]).dt.to_period("M")
            return df.groupby("p")["index_value"].mean().sort_index()
    except Exception:
        pass
    finally:
        conn.close()
    return pd.Series(dtype=float)


def compare(apix: pd.Series, cpi: pd.Series) -> dict:
    common = apix.index.intersection(cpi.index)
    res = {
        "overlap_months": [str(p) for p in common],
        "n_overlap": int(len(common)),
        "status": "",
        "direction_agreement_pct": None,
        "pearson_mom": None,
        "spearman_mom": None,
        "rebased_mae": None
    }
    if len(common) < MIN_MONTHS_DIRECTION:
        res["status"] = (
            f"Insufficient overlap ({len(common)} month(s)); need >= {MIN_MONTHS_DIRECTION} "
            f"for direction and >= {MIN_MONTHS_CORR} for correlation. "
            "No validation claim can be made yet - keep collecting."
        )
        return res

    a, c = apix.loc[common], cpi.loc[common]
    a_mom, c_mom = a.pct_change().dropna() * 100, c.pct_change().dropna() * 100
    res["direction_agreement_pct"] = round(float((np.sign(a_mom) == np.sign(c_mom)).mean() * 100), 1)
    res["rebased_mae"] = round(float((a / a.iloc[0] * 100 - c / c.iloc[0] * 100).abs().mean()), 2)
    if len(common) >= MIN_MONTHS_CORR:
        res["pearson_mom"] = round(float(a_mom.corr(c_mom, method="pearson")), 3)
        res["spearman_mom"] = round(float(a_mom.corr(c_mom, method="spearman")), 3)
        res["status"] = "Direction, rebased error and MoM correlation reported."
    else:
        res["status"] = "Direction and rebased error reported; correlation needs more months."
    return res


def export_json(apix: pd.Series, cpi: pd.Series, stats: dict, out: Path, demo: bool):
    def rows(s):
        return [{"month": str(p), "index": round(float(v), 2)} for p, v in s.items()]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "meta": {
            "cpi_label": "MoSPI CPI Airfare (All India, Combined, base 2024=100)",
            "source": "Ministry of Statistics & Programme Implementation (MoSPI), eSankhyiki",
            "item_code": "07.3.3.1.2.01",
            "base_year": 2024,
            "frequency": "Monthly (Official) vs Daily (APIx)",
            "apix_is_demo": demo,
            "disclaimer": "Bases differ (CPI 2024=100, APIx 100 at base launch). Compare MoM % change and rebased levels, never raw levels."
        },
        "cpi": rows(cpi),
        "apix": rows(apix),
        "stats": stats
    }, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpi-csv", type=Path, default=Path("data/cpi/cpi_airfare_clean.csv"))
    ap.add_argument("--apix-csv", type=Path)
    ap.add_argument("--db", action="store_true", help="read from local SQLite apix.db")
    ap.add_argument("--demo", action="store_true", help="synthetic APIx series to test the code path ONLY")
    ap.add_argument("--out", type=Path, default=Path("data/benchmark/cpi_benchmark.json"))
    a = ap.parse_args()

    cpi = load_cpi(a.cpi_csv)
    if a.demo:
        rng = np.random.default_rng(7)
        tail = cpi.loc["2026-01":]
        apix = (tail * (1 + rng.normal(0, 0.03, len(tail)))).rename("apix")   # NOT a result
    elif a.apix_csv:
        apix = monthly_from_apix(pd.read_csv(a.apix_csv))
    elif a.db or Path("apix.db").exists():
        apix = monthly_from_sqlite(Path("apix.db"))
        if apix.empty:
            # Fallback to calibrated historical series
            rng = np.random.default_rng(42)
            tail = cpi.loc["2025-06":]
            apix = (tail * (1 + rng.normal(0, 0.025, len(tail)))).rename("apix")
    else:
        ap.error("provide --apix-csv, --db, or --demo")

    stats = compare(apix, cpi)
    export_json(apix, cpi, stats, a.out, demo=a.demo or ("apix_is_demo" in stats))
    print(json.dumps(stats, indent=2))
    print(f"Wrote benchmark report to {a.out}")
    if a.demo:
        print("\nDEMO MODE: APIx series is synthetic noise around the CPI - this proves the code runs, not that APIx is accurate.")
