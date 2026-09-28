#!/usr/bin/env python3
"""
scripts/purge_raw.py — Purge raw scrape files older than 90 days.

Deletes files older than 90 days from the private Supabase Storage bucket "raw-scrapes"
(and from local data/raw/ if present) and logs how many were removed.

Usage:
    python scripts/purge_raw.py
    python scripts/purge_raw.py --days 90
    python scripts/purge_raw.py --dry-run
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Tuple

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apix.config import settings


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("purge_raw")

BUCKET_NAME = "raw-scrapes"


def get_storage_client():
    """Obtain Supabase client using service-role key for Storage administration."""
    from supabase import create_client
    url = settings.supabase_url
    key = settings.supabase_service_role_key
    if not (url and key):
        logger.error("Supabase URL or service-role key not configured in environment.")
        return None
    key_str = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key)
    return create_client(url, key_str)


def parse_date_from_string(val: str) -> date | None:
    """Attempt to parse YYYY-MM-DD date from folder or string."""
    try:
        parts = val.strip().split("-")
        if len(parts) == 3 and len(parts[0]) == 4:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:
        pass
    return None


def purge_supabase_storage(
    cutoff_date: date,
    dry_run: bool = False,
) -> Tuple[int, List[str]]:
    """
    Traverse 'raw-scrapes' bucket and delete files older than cutoff_date.
    Returns (count_deleted, list_of_paths).
    """
    client = get_storage_client()
    if client is None:
        logger.warning("Supabase Storage client unavailable; skipping remote purge.")
        return 0, []

    bucket = client.storage.from_(BUCKET_NAME)
    to_delete: List[str] = []

    try:
        # 1. List root items (sources like indigo, air_india, makemytrip)
        root_items = bucket.list("", {"limit": 100}) or []
        for src_item in root_items:
            source_name = src_item.get("name")
            if not source_name:
                continue

            # 2. List date directories under this source
            date_items = bucket.list(source_name, {"limit": 200}) or []
            for dt_item in date_items:
                dir_name = dt_item.get("name")
                if not dir_name:
                    continue

                folder_date = parse_date_from_string(dir_name)
                folder_path = f"{source_name}/{dir_name}"

                if folder_date is not None:
                    # Date-based folder matching
                    if folder_date < cutoff_date:
                        # Entire folder is older than cutoff
                        files_in_dir = bucket.list(folder_path, {"limit": 500}) or []
                        for f in files_in_dir:
                            fname = f.get("name")
                            if fname:
                                to_delete.append(f"{folder_path}/{fname}")
                else:
                    # Item could be an individual file or non-standard directory
                    created_at_str = dt_item.get("created_at") or dt_item.get("updated_at")
                    if created_at_str:
                        try:
                            item_date = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")).date()
                            if item_date < cutoff_date:
                                to_delete.append(folder_path)
                        except Exception:
                            pass

    except Exception as exc:
        logger.error("Failed while traversing Supabase Storage bucket '%s': %s", BUCKET_NAME, exc)

    if not to_delete:
        logger.info("Supabase Storage '%s': No files found older than %s.", BUCKET_NAME, cutoff_date.isoformat())
        return 0, []

    logger.info(
        "Supabase Storage '%s': Found %d file(s) older than %s (%s).",
        BUCKET_NAME,
        len(to_delete),
        cutoff_date.isoformat(),
        "[DRY RUN - will not delete]" if dry_run else "Deleting...",
    )

    if dry_run:
        for p in to_delete:
            logger.info("  [DRY RUN] Would delete: %s", p)
        return len(to_delete), to_delete

    # Perform batch deletion in chunks of 100
    deleted_count = 0
    chunk_size = 100
    for i in range(0, len(to_delete), chunk_size):
        chunk = to_delete[i : i + chunk_size]
        try:
            bucket.remove(chunk)
            deleted_count += len(chunk)
            for p in chunk:
                logger.info("  Deleted from Storage: %s", p)
        except Exception as exc:
            logger.error("Failed to delete chunk of %d files from Storage: %s", len(chunk), exc)

    logger.info("Supabase Storage: Successfully removed %d file(s) older than %s.", deleted_count, cutoff_date.isoformat())
    return deleted_count, to_delete


def purge_local_directory(
    cutoff_date: date,
    dry_run: bool = False,
) -> Tuple[int, List[Path]]:
    """
    Traverse local raw_data_dir (data/raw/) and remove files older than cutoff_date.
    Returns (count_deleted, list_of_paths).
    """
    raw_dir = Path(settings.raw_data_dir)
    if not raw_dir.exists():
        logger.debug("Local raw directory '%s' does not exist; skipping local purge.", raw_dir)
        return 0, []

    to_delete: List[Path] = []

    for path in raw_dir.glob("**/*.json"):
        if not path.is_file():
            continue

        file_date: date | None = None
        # Try parent folder name (e.g. data/raw/indigo/2026-05-01/...)
        parent_name = path.parent.name
        file_date = parse_date_from_string(parent_name)

        if file_date is None:
            # Fallback to mtime
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date()
            file_date = mtime

        if file_date < cutoff_date:
            to_delete.append(path)

    if not to_delete:
        logger.info("Local '%s': No files found older than %s.", raw_dir, cutoff_date.isoformat())
        return 0, []

    logger.info(
        "Local '%s': Found %d file(s) older than %s (%s).",
        raw_dir,
        len(to_delete),
        cutoff_date.isoformat(),
        "[DRY RUN]" if dry_run else "Deleting...",
    )

    if dry_run:
        for p in to_delete:
            logger.info("  [DRY RUN] Would delete local: %s", p)
        return len(to_delete), to_delete

    deleted_count = 0
    for p in to_delete:
        try:
            p.unlink()
            deleted_count += 1
            logger.info("  Deleted local: %s", p)
        except Exception as exc:
            logger.error("Failed to delete local file %s: %s", p, exc)

    # Clean up empty parent directories
    for p in to_delete:
        try:
            parent = p.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        except Exception:
            pass

    logger.info("Local directory: Successfully removed %d file(s) older than %s.", deleted_count, cutoff_date.isoformat())
    return deleted_count, to_delete


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Purge raw scrape JSON files older than 90 days from Supabase Storage and local disk."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Age threshold in days (default: 90). Files older than this will be purged.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview files that would be removed without actually deleting them.",
    )

    args = parser.parse_args()
    cutoff_date = date.today() - timedelta(days=args.days)

    print("=" * 60)
    print(" AIRIVA RAW SCRAPE PURGE ORCHESTRATOR")
    print(f" Cutoff: Older than {args.days} days (< {cutoff_date.isoformat()})")
    print(f" Mode:   {'DRY RUN (Preview)' if args.dry_run else 'LIVE PURGE'}")
    print("=" * 60)

    # 1. Purge from private Supabase Storage bucket 'raw-scrapes'
    storage_count, _ = purge_supabase_storage(cutoff_date, dry_run=args.dry_run)

    # 2. Purge from local data/raw/ directory
    local_count, _ = purge_local_directory(cutoff_date, dry_run=args.dry_run)

    total_removed = storage_count + local_count
    print("\n" + "=" * 60)
    print(" PURGE EXECUTION SUMMARY")
    print(f" Supabase Storage ('{BUCKET_NAME}'): {storage_count} file(s) removed")
    print(f" Local Disk ('{settings.raw_data_dir}'):     {local_count} file(s) removed")
    print(f" Total Removed:                     {total_removed} file(s)")
    print("=" * 60 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
