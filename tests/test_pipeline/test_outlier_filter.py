"""
test_outlier_filter.py — Tests for apix.pipeline.outlier_filter
"""
from __future__ import annotations

import pytest
from typing import List

from apix.pipeline.outlier_filter import apply_iqr_filter, _MIN_GROUP_SIZE
from apix.pipeline.schema import FareRecord


class TestIQRFilter:
    def test_extreme_high_fare_flagged(self, make_fare):
        """A fare 10× the median should be flagged as an outlier."""
        records = [make_fare(flight_number=f"6E-{i:03d}", total_fare=4500.0 + i*50) for i in range(6)]
        records.append(make_fare(flight_number="6E-999", total_fare=90000.0))

        result = apply_iqr_filter(records)
        flagged = [r for r in result if r.is_outlier]
        assert len(flagged) == 1
        assert flagged[0].flight_number == "6E-999"

    def test_extreme_low_fare_flagged(self, make_fare):
        """A suspiciously low fare (below Q1 - 1.5×IQR) should be flagged."""
        records = [make_fare(flight_number=f"6E-{i:03d}", total_fare=4500.0 + i*100) for i in range(6)]
        records.append(make_fare(flight_number="6E-001", total_fare=10.0))

        result = apply_iqr_filter(records)
        flagged = [r for r in result if r.is_outlier]
        assert any(r.total_fare == 10.0 for r in flagged)

    def test_normal_fares_not_flagged(self, make_fare):
        """All fares within normal range should NOT be flagged."""
        records = [make_fare(flight_number=f"6E-{i:03d}", total_fare=4400.0 + i*100) for i in range(8)]
        result = apply_iqr_filter(records)
        flagged = [r for r in result if r.is_outlier]
        assert len(flagged) == 0

    def test_records_never_dropped(self, make_fare):
        """Total record count must not change after filtering."""
        records = [make_fare(flight_number=f"6E-{i:03d}", total_fare=4500.0 + i*50) for i in range(6)]
        records.append(make_fare(flight_number="6E-999", total_fare=99000.0))
        result = apply_iqr_filter(records)
        assert len(result) == len(records)

    def test_small_group_skipped(self, make_fare):
        """Groups below MIN_GROUP_SIZE should not have IQR computed — no flags."""
        small_group = [
            make_fare(flight_number=f"6E-{i:03d}", total_fare=4500.0 + i*200)
            for i in range(_MIN_GROUP_SIZE - 1)
        ]
        result = apply_iqr_filter(small_group)
        assert all(not r.is_outlier for r in result)

    def test_groups_are_per_route_not_global(self, make_fare):
        """
        A high fare for one route should NOT flag records on another route
        (IQR must be computed per group, not globally).
        """
        # BOM-BLR fares are naturally lower; DEL-BOM fares are higher
        del_bom = [make_fare(origin="DEL", destination="BOM", flight_number=f"6E-D{i}", total_fare=5000+i*100) for i in range(5)]
        bom_blr = [make_fare(origin="BOM", destination="BLR", flight_number=f"6E-B{i}", total_fare=3500+i*100) for i in range(5)]

        result = apply_iqr_filter(del_bom + bom_blr)
        flagged = [r for r in result if r.is_outlier]
        assert len(flagged) == 0, "No outliers expected when groups are evaluated independently"

    def test_censored_excluded_from_iqr(self, make_fare):
        """Censored records (total_fare=0) must NOT skew the IQR lower."""
        records = [make_fare(flight_number=f"6E-{i:03d}", total_fare=4500.0 + i*80) for i in range(6)]
        censored = make_fare(flight_number="CENSORED", total_fare=0.0, is_censored=True)
        all_records = records + [censored]

        result = apply_iqr_filter(all_records)
        # Normal records should remain clean
        valid_flagged = [r for r in result if r.is_outlier and not r.is_censored]
        assert len(valid_flagged) == 0, "Censored records must not pull IQR fences down"

    def test_censored_not_flagged_as_outlier(self, censored_record, make_fare):
        """A censored record itself should never be marked is_outlier=True."""
        records = [make_fare(flight_number=f"6E-{i:03d}", total_fare=4500.0 + i*80) for i in range(6)]
        result = apply_iqr_filter(records + [censored_record])
        censored_out = [r for r in result if r.is_censored]
        assert all(not r.is_outlier for r in censored_out)

    def test_uniform_fares_no_outliers(self, make_fare):
        """When all fares are identical, IQR=0 → no outliers."""
        records = [make_fare(flight_number=f"6E-{i:03d}", total_fare=5000.0) for i in range(8)]
        result = apply_iqr_filter(records)
        assert all(not r.is_outlier for r in result)
