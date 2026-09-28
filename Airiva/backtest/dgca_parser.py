"""
dgca_parser.py — Extract monthly average-fare data from DGCA PDF reports.

Source: dgca.gov.in → Data & Reports → Civil Aviation Statistics Handbook
        → Domestic Air Transport → Monthly Statistics

The relevant tables typically appear as "Statement showing Route-wise
traffic carried by Domestic Airlines" — with columns for Route, PAX,
and Average Fare (in INR).

Strategy:
  1. Try pdfplumber (primary) — good for text-based PDFs with complex layouts
  2. Fall back to camelot (lattice mode) — better for grid-line tables
  3. Clean and normalise extracted data into a standard DataFrame

Usage:
  df = parse_dgca_pdfs("apix/backtest/data/")
  # Returns DataFrame with: year, month, route, avg_fare_inr, pax_count
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Routes we care about — matched against extracted text
_ROUTE_PATTERNS = {
    "DEL-BOM": re.compile(r"(del.?bom|delhi.?mumbai|new\s*delhi.?bombay)", re.IGNORECASE),
    "DEL-BLR": re.compile(r"(del.?blr|delhi.?bangalore|new\s*delhi.?bengaluru)", re.IGNORECASE),
    "BOM-BLR": re.compile(r"(bom.?blr|mumbai.?bangalore|bombay.?bengaluru)", re.IGNORECASE),
}

# Regex for INR amounts (e.g. "4,523" or "4523" or "4523.00")
_FARE_RE = re.compile(r"\b(\d{1,2},\d{3}(?:\.\d{1,2})?|\d{3,6}(?:\.\d{1,2})?)\b")

# Month name → number
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _extract_year_month_from_filename(path: Path) -> tuple[Optional[int], Optional[int]]:
    """Infer year/month from common DGCA filename patterns."""
    name = path.stem.lower()
    # Patterns: "monthly_stats_2024_03", "domestic_jan_2024", "2024-04"
    year_match = re.search(r"(20\d{2})", name)
    month_match = re.search(
        r"(january|february|march|april|may|june|july|august|september|october|november|december"
        r"|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec|_0?(\d{1,2})_)",
        name,
    )
    year = int(year_match.group(1)) if year_match else None
    month = None
    if month_match:
        grp = month_match.group(1).lower()
        month = _MONTHS.get(grp) or (int(month_match.group(2)) if month_match.group(2) else None)
    return year, month


def _extract_fare_from_row(row_text: str) -> Optional[float]:
    """Extract the first plausible INR fare amount from a table row string."""
    matches = _FARE_RE.findall(row_text)
    fares = []
    for m in matches:
        try:
            val = float(m.replace(",", ""))
            if 500 <= val <= 50000:  # plausible domestic fare range
                fares.append(val)
        except ValueError:
            continue
    return fares[-1] if fares else None  # last numeric = typically avg fare column


def _parse_with_pdfplumber(pdf_path: Path, year: Optional[int], month: Optional[int]) -> list[dict]:
    """Primary extraction using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not installed — skipping")
        return []

    records = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row:
                            continue
                        row_str = " ".join(str(c) for c in row if c)
                        for route_key, pattern in _ROUTE_PATTERNS.items():
                            if pattern.search(row_str):
                                fare = _extract_fare_from_row(row_str)
                                if fare:
                                    records.append({
                                        "year": year,
                                        "month": month,
                                        "route": route_key,
                                        "avg_fare_inr": fare,
                                        "source": "pdfplumber",
                                        "file": pdf_path.name,
                                    })
    except Exception as exc:
        logger.error("pdfplumber failed on %s: %s", pdf_path, exc)
    return records


def _parse_with_camelot(pdf_path: Path, year: Optional[int], month: Optional[int]) -> list[dict]:
    """Fallback extraction using camelot (lattice mode for grid-line tables)."""
    try:
        import camelot
    except ImportError:
        logger.warning("camelot-py not installed — skipping")
        return []

    records = []
    try:
        tables = camelot.read_pdf(str(pdf_path), pages="all", flavor="lattice")
        for table in tables:
            df = table.df
            for _, row in df.iterrows():
                row_str = " ".join(str(v) for v in row.values)
                for route_key, pattern in _ROUTE_PATTERNS.items():
                    if pattern.search(row_str):
                        fare = _extract_fare_from_row(row_str)
                        if fare:
                            records.append({
                                "year": year,
                                "month": month,
                                "route": route_key,
                                "avg_fare_inr": fare,
                                "source": "camelot",
                                "file": pdf_path.name,
                            })
    except Exception as exc:
        logger.error("camelot failed on %s: %s", pdf_path, exc)
    return records


def parse_pdf(pdf_path: Path) -> list[dict]:
    """Parse one DGCA PDF and return route-fare records."""
    year, month = _extract_year_month_from_filename(pdf_path)
    logger.info("Parsing %s (inferred: year=%s month=%s)", pdf_path.name, year, month)

    records = _parse_with_pdfplumber(pdf_path, year, month)
    if not records:
        logger.info("pdfplumber found nothing in %s — trying camelot", pdf_path.name)
        records = _parse_with_camelot(pdf_path, year, month)

    return records


def parse_dgca_pdfs(pdf_dir: str | Path) -> pd.DataFrame:
    """
    Parse all PDF files in a directory and return a consolidated DataFrame.

    Returns columns: year, month, route, avg_fare_inr, source, file
    Drops rows with null year/month/fare.
    """
    pdf_dir = Path(pdf_dir)
    if not pdf_dir.exists():
        logger.warning("DGCA PDF directory not found: %s", pdf_dir)
        return pd.DataFrame(columns=["year", "month", "route", "avg_fare_inr"])

    all_records = []
    pdf_files = list(pdf_dir.glob("*.pdf")) + list(pdf_dir.glob("*.PDF"))

    if not pdf_files:
        logger.warning("No PDF files found in %s", pdf_dir)
        return pd.DataFrame(columns=["year", "month", "route", "avg_fare_inr"])

    for pdf_path in sorted(pdf_files):
        records = parse_pdf(pdf_path)
        all_records.extend(records)
        logger.info("Extracted %d records from %s", len(records), pdf_path.name)

    if not all_records:
        return pd.DataFrame(columns=["year", "month", "route", "avg_fare_inr"])

    df = pd.DataFrame(all_records)
    df = df.dropna(subset=["year", "month", "avg_fare_inr"])
    df["year"] = df["year"].astype(int)
    df["month"] = df["month"].astype(int)

    # De-duplicate: if multiple rows for same (year, month, route), take mean
    df = (
        df.groupby(["year", "month", "route"], as_index=False)["avg_fare_inr"]
        .mean()
    )

    logger.info("parse_dgca_pdfs: %d total records from %d files", len(df), len(pdf_files))
    return df
