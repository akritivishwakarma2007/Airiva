"""
scripts/load_cpi_official.py — Load the MoSPI eSankhyiki CPI airfare workbook (cpi_1413.xlsx).

Usage:
  python scripts/load_cpi_official.py --xlsx data/cpi/cpi_1413.xlsx --dry-run
  python scripts/load_cpi_official.py --xlsx data/cpi/cpi_1413.xlsx                 # cleans and saves CSV + upserts SQLite/Supabase
  python scripts/load_cpi_official.py --xlsx data/cpi/cpi_1413.xlsx --sqlite       # upsert into local apix.db SQLite

Always writes a cleaned CSV (data/cpi/cpi_airfare_clean.csv) that the benchmark module reads.
Supabase upsert runs only if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set.
SQLite upsert runs into apix.db if available.

Source to cite everywhere it appears:
  Ministry of Statistics & Programme Implementation (MoSPI), eSankhyiki.
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path
import pandas as pd

MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}
EXPECTED = {"base_year", "series", "year", "month", "state", "sector", "item", "code",
            "index", "inflation", "imputation"}


def load_clean(xlsx: Path) -> pd.DataFrame:
    df = pd.read_excel(xlsx)
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = EXPECTED - set(df.columns)
    if missing:
        sys.exit(f"Workbook is missing expected columns: {sorted(missing)}")

    df = df[df["item"].astype(str).str.strip().str.lower() == "airfare"].copy()
    df["month"] = df["month"].astype(str).str.strip().map(MONTHS)
    bad = df["month"].isna().sum()
    if bad:
        print(f"WARNING: dropping {bad} rows with unrecognised month names")
        df = df.dropna(subset=["month"])

    out = pd.DataFrame({
        "year": df["year"].astype(int),
        "month": df["month"].astype(int),
        "state": df["state"].astype(str).str.strip(),
        "sector": df["sector"].astype(str).str.strip().str.title(),
        "item_code": df["code"].astype(str).str.strip(),
        "base_year": df["base_year"].astype(int),
        "index_value": pd.to_numeric(df["index"], errors="coerce"),
        "inflation": pd.to_numeric(df["inflation"], errors="coerce"),
        "imputed": df["imputation"].astype(str).str.upper().eq("Y"),
    })
    dropped = out["index_value"].isna().sum()
    if dropped:
        print(f"WARNING: dropping {dropped} rows with non-numeric index")
        out = out.dropna(subset=["index_value"])
    out = out.drop_duplicates(["year", "month", "state", "sector", "item_code"])
    return out.sort_values(["state", "sector", "year", "month"]).reset_index(drop=True)


def upsert_sqlite(df: pd.DataFrame, db_path: Path) -> None:
    if not db_path.exists():
        print(f"SQLite DB {db_path} not found - skipping SQLite upsert.")
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cpi_official (
      year        INTEGER NOT NULL,
      month       INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
      state       TEXT NOT NULL,
      sector      TEXT NOT NULL CHECK (sector IN ('Rural','Urban','Combined')),
      item_code   TEXT NOT NULL DEFAULT '07.3.3.1.2.01',
      base_year   INTEGER NOT NULL DEFAULT 2024,
      index_value REAL NOT NULL,
      inflation   REAL,
      imputed     BOOLEAN NOT NULL DEFAULT 0,
      PRIMARY KEY (year, month, state, sector, item_code)
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cpi_lookup ON cpi_official (state, sector, year, month)")
    
    records = []
    for _, r in df.iterrows():
        records.append((
            int(r["year"]), int(r["month"]), str(r["state"]), str(r["sector"]),
            str(r["item_code"]), int(r["base_year"]), float(r["index_value"]),
            float(r["inflation"]) if pd.notna(r["inflation"]) else None,
            1 if r["imputed"] else 0
        ))
    cur.executemany("""
    INSERT INTO cpi_official (year, month, state, sector, item_code, base_year, index_value, inflation, imputed)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(year, month, state, sector, item_code) DO UPDATE SET
      index_value=excluded.index_value,
      inflation=excluded.inflation,
      imputed=excluded.imputed
    """, records)
    conn.commit()
    conn.close()
    print(f"Upserted {len(records)} rows into SQLite table 'cpi_official' in {db_path}.")


def upsert_supabase(df: pd.DataFrame, chunk: int = 500) -> None:
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not (url and key):
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set - skipping Supabase upsert.")
        return
    try:
        from supabase import create_client          # pip install supabase
        client = create_client(url, key)
        rows = df.astype(object).where(df.notna(), None).to_dict("records")
        for i in range(0, len(rows), chunk):
            client.table("cpi_official").upsert(
                rows[i:i + chunk], on_conflict="year,month,state,sector,item_code").execute()
        print(f"Upserted {len(rows)} rows into Supabase table 'cpi_official'.")
    except Exception as e:
        print(f"Supabase upsert skipped or encountered error: {e}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/cpi/cpi_airfare_clean.csv"))
    ap.add_argument("--dry-run", action="store_true", help="clean + write CSV only")
    ap.add_argument("--sqlite", action="store_true", help="upsert to local SQLite apix.db")
    ap.add_argument("--db-path", type=Path, default=Path("apix.db"))
    a = ap.parse_args()

    clean = load_clean(a.xlsx)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    clean.to_csv(a.out, index=False)
    ai = clean[(clean.state == "All India") & (clean.sector == "Combined")]
    print(f"Rows: {len(clean)} | states: {clean.state.nunique()} | "
          f"months: {ai.shape[0]} ({ai.year.min()}-{ai.month.iloc[0]:02d} .. "
          f"{ai.year.max()}-{ai.month.iloc[-1]:02d}) | imputed rows: {int(clean.imputed.sum())}")
    print(f"Wrote {a.out}")
    
    if not a.dry_run:
        # Upsert to SQLite if requested or if apix.db exists
        if a.sqlite or a.db_path.exists():
            upsert_sqlite(clean, a.db_path)
        upsert_supabase(clean)
