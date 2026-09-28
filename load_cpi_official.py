"""
Load the MoSPI eSankhyiki CPI airfare workbook (cpi_1413.xlsx).

  python scripts/load_cpi_official.py --xlsx data/cpi/cpi_1413.xlsx --dry-run
  python scripts/load_cpi_official.py --xlsx data/cpi/cpi_1413.xlsx        # also upserts to Supabase

Always writes a cleaned CSV (data/cpi/cpi_airfare_clean.csv) that the benchmark module reads.
Supabase upsert runs only if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set.
Source to cite: Ministry of Statistics & Programme Implementation (MoSPI), eSankhyiki.
"""
import argparse, os, sys
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


def upsert_supabase(df: pd.DataFrame, chunk: int = 500) -> None:
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not (url and key):
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set - skipping upsert.")
        return
    from supabase import create_client          # pip install supabase
    client = create_client(url, key)
    rows = df.astype(object).where(df.notna(), None).to_dict("records")
    for i in range(0, len(rows), chunk):
        client.table("cpi_official").upsert(
            rows[i:i + chunk], on_conflict="year,month,state,sector,item_code").execute()
    print(f"Upserted {len(rows)} rows into cpi_official.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/cpi/cpi_airfare_clean.csv"))
    ap.add_argument("--dry-run", action="store_true", help="clean + write CSV only")
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
        upsert_supabase(clean)
