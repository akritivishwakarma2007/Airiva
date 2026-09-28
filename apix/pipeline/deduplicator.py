"""
deduplicator.py — De-duplication of fare quotes across sources.

Problem: The same flight (e.g. 6E-123 on 2024-10-10, Economy Saver)
appears both in IndiGo's direct data and in MakeMyTrip's OTA listing.
Storing both inflates count-based statistics and can bias the index.

Strategy:
  - Group by (flight_number, travel_date, fare_class).
  - When multiple records share the same key, retain the one with the
    LOWEST total_fare (OTAs sometimes add convenience fees — airline-
    direct is usually cheaper, but not always).
  - All other records in the group are marked is_duplicate=True.
  - Records marked is_censored are excluded from dedup groups (we don't
    want a censored record to "win" over a valid one).

The full record set (including duplicates) is always written to the DB
for audit purposes. Only non-duplicate, non-censored records are used
in index computation.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import List

from apix.pipeline.schema import FareRecord

logger = logging.getLogger(__name__)


def deduplicate(records: List[FareRecord]) -> List[FareRecord]:
    """
    Mark duplicate fare quotes with is_duplicate=True.

    Dedup key: (flight_number, travel_date, fare_class).
    Winner: lowest total_fare in the group.

    Returns the same records with is_duplicate fields updated.
    """
    # Separate valid from censored
    valid_indices = [i for i, r in enumerate(records) if not r.is_censored]
    censored_indices = [i for i, r in enumerate(records) if r.is_censored]

    # Build groups from valid records only
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i in valid_indices:
        rec = records[i]
        key = (
            rec.flight_number.upper().replace(" ", ""),
            rec.travel_date,
            (rec.fare_class or "").upper(),
        )
        groups[key].append(i)

    duplicate_indices: set[int] = set()

    for key, indices in groups.items():
        if len(indices) <= 1:
            continue  # no duplicate to resolve

        # Find the winner (lowest total_fare)
        winner_idx = min(indices, key=lambda i: records[i].total_fare)
        losers = [i for i in indices if i != winner_idx]

        for idx in losers:
            duplicate_indices.add(idx)
            logger.debug(
                "dedup: key=%s — suppressing %s (%.2f INR) in favour of %s (%.2f INR)",
                key,
                records[idx].source, records[idx].total_fare,
                records[winner_idx].source, records[winner_idx].total_fare,
            )

    logger.info(
        "dedup: %d/%d valid records marked as duplicates",
        len(duplicate_indices), len(valid_indices),
    )

    result = []
    for i, rec in enumerate(records):
        if i in duplicate_indices:
            result.append(rec.model_copy(update={"is_duplicate": True}))
        else:
            result.append(rec)

    return result
