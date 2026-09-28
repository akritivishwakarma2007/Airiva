"""
outlier_filter.py — IQR-based outlier detection for fare quotes.

Groups records by (origin, destination, travel_date, advance_purchase_days).
Within each group, marks records outside [Q1 - 1.5×IQR, Q3 + 1.5×IQR] as
is_outlier=True.

Design decisions:
  - IQR is computed PER GROUP, never globally. Fares are heavy-tailed and
    route-specific; a global threshold would incorrectly flag premium routes.
  - Records are flagged, NEVER dropped. The index engine excludes flagged
    records; the raw data is preserved for audit.
  - Lower fence: applied (negative fares are invalid; extremely low fares
    are suspicious promotionals that distort the index).
  - Upper fence: applied (fare caps above typical 3× median are data errors
    or accidental business-class inclusions).
  - Groups with fewer than 4 records: IQR cannot be reliably computed;
    all records in that group are left unflagged.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import List

import numpy as np

from apix.pipeline.schema import FareRecord

logger = logging.getLogger(__name__)

_MIN_GROUP_SIZE = 4  # below this, skip outlier detection


def apply_iqr_filter(records: List[FareRecord]) -> List[FareRecord]:
    """
    Compute IQR per (origin, destination, travel_date, advance_purchase_days)
    group and set is_outlier=True on extreme values.

    Censored records (total_fare == 0) are always excluded from IQR
    calculation but are never themselves flagged as outliers.

    Returns the same list with is_outlier fields updated (new FareRecord
    objects since Pydantic models are immutable by default).
    """
    # Group indices by key
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, rec in enumerate(records):
        if rec.is_censored:
            continue  # exclude censored from IQR groups
        key = (rec.origin, rec.destination, rec.travel_date, rec.advance_purchase_days)
        groups[key].append(i)

    flagged_indices: set[int] = set()

    for key, indices in groups.items():
        if len(indices) < _MIN_GROUP_SIZE:
            logger.debug(
                "outlier_filter: group %s has %d records (< %d) — skipping IQR",
                key, len(indices), _MIN_GROUP_SIZE,
            )
            continue

        fares = np.array([records[i].total_fare for i in indices], dtype=float)
        q1, q3 = np.percentile(fares, [25, 75])
        iqr = q3 - q1

        if iqr == 0:
            # All fares identical — no spread to detect outliers from
            continue

        lower_fence = q1 - 1.5 * iqr
        upper_fence = q3 + 1.5 * iqr

        for i in indices:
            fare = records[i].total_fare
            if fare < lower_fence or fare > upper_fence:
                flagged_indices.add(i)
                logger.debug(
                    "outlier_filter: flagged idx=%d fare=%.2f (fence=[%.2f, %.2f]) key=%s",
                    i, fare, lower_fence, upper_fence, key,
                )

    logger.info(
        "outlier_filter: %d/%d records flagged as outliers",
        len(flagged_indices), len(records),
    )

    # Return new list with is_outlier updated (Pydantic model_copy)
    result = []
    for i, rec in enumerate(records):
        if i in flagged_indices:
            result.append(rec.model_copy(update={"is_outlier": True}))
        else:
            result.append(rec)

    return result
