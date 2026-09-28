"""
tests/test_raw_storage.py — Tests for Supabase Storage raw scrapes, sanitization, and purging.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apix.config import settings
from apix.scraper.storage import (
    BUCKET_NAME,
    is_sensitive_key,
    sanitize_raw_data,
    upload_raw_scrape,
)
from scripts.purge_raw import (
    parse_date_from_string,
    purge_local_directory,
    purge_supabase_storage,
)


class TestSanitizeRawData:
    def test_strip_sensitive_headers_and_cookies(self):
        payload = {
            "source": "indigo",
            "origin": "DEL",
            "destination": "BOM",
            "travel_date": "2026-10-01",
            "advance_days": 7,
            "headers": {"User-Agent": "Playwright", "Authorization": "Bearer secret_jwt_token"},
            "request_headers": {"Accept": "application/json"},
            "cookies": [{"name": "session_id", "value": "xyz123"}],
            "request_cookies": "sid=12345; auth=token",
            "access_token": "secret_abc",
            "flights": [
                {
                    "flight_number": "6E-101",
                    "base_fare": 4500.0,
                    "taxes_fees": 810.0,
                    "total_fare": 5310.0,
                    "passenger_name": "John Doe",
                    "user_email": "john@example.com",
                    "fare_class": "SAVER",
                }
            ],
        }

        cleaned = sanitize_raw_data(payload)

        # Sensitive keys must be stripped
        assert "headers" not in cleaned
        assert "request_headers" not in cleaned
        assert "cookies" not in cleaned
        assert "request_cookies" not in cleaned
        assert "access_token" not in cleaned

        # Flight data must be preserved without personal data
        assert "flights" in cleaned
        flight = cleaned["flights"][0]
        assert flight["flight_number"] == "6E-101"
        assert flight["base_fare"] == 4500.0
        assert flight["taxes_fees"] == 810.0
        assert flight["total_fare"] == 5310.0
        assert flight["fare_class"] == "SAVER"
        assert "passenger_name" not in flight
        assert "user_email" not in flight

        # Core scrape metadata must be preserved
        assert cleaned["source"] == "indigo"
        assert cleaned["origin"] == "DEL"
        assert cleaned["destination"] == "BOM"
        assert cleaned["travel_date"] == "2026-10-01"
        assert cleaned["advance_days"] == 7

    def test_redact_sensitive_strings(self):
        assert sanitize_raw_data("Bearer eyJhbGciOi...") == "[REDACTED]"
        assert sanitize_raw_data("Set-Cookie: session=xyz") == "[REDACTED]"
        assert sanitize_raw_data("6E-101") == "6E-101"

    def test_is_sensitive_key(self):
        assert is_sensitive_key("authorization") is True
        assert is_sensitive_key("Authorization") is True
        assert is_sensitive_key("request-headers") is True
        assert is_sensitive_key("Set-Cookie") is True
        assert is_sensitive_key("pnr_number") is True
        assert is_sensitive_key("flight_number") is False
        assert is_sensitive_key("total_fare") is False


class TestUploadRawScrape:
    @pytest.fixture(autouse=True)
    def setup_tmp_raw_dir(self, tmp_path):
        self.tmp_dir = tmp_path / "raw"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        with patch.object(settings, "raw_data_dir", self.tmp_dir):
            yield

    def test_upload_app_env_development_keeps_local_copy(self):
        payload = {
            "source": "indigo",
            "origin": "DEL",
            "destination": "BOM",
            "advance_days": 7,
            "headers": {"Secret": "strip_me"},
            "flights": [{"flight_number": "6E-101", "total_fare": 5000.0}],
        }

        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_client.storage.from_.return_value = mock_bucket

        with patch("apix.scraper.storage.get_storage_client", return_value=mock_client), \
             patch.object(settings, "app_env", "development"):
            path = upload_raw_scrape(
                data=payload,
                source="indigo",
                origin="DEL",
                destination="BOM",
                advance_days=7,
                scrape_date=date(2026, 9, 28),
            )

        # 1. Verify storage path format
        assert path == "indigo/2026-09-28/DEL-BOM_7d.json"

        # 2. Verify Supabase Storage upload called
        mock_client.storage.from_.assert_called_with(BUCKET_NAME)
        mock_bucket.upload.assert_called_once()
        call_kwargs = mock_bucket.upload.call_args[1]
        assert call_kwargs["path"] == "indigo/2026-09-28/DEL-BOM_7d.json"

        # Content must be sanitized bytes
        uploaded_bytes = call_kwargs["file"]
        uploaded_dict = json.loads(uploaded_bytes.decode("utf-8"))
        assert "headers" not in uploaded_dict
        assert uploaded_dict["flights"][0]["flight_number"] == "6E-101"

        # 3. Local copy MUST exist when APP_ENV=development
        local_file = self.tmp_dir / "indigo" / "2026-09-28" / "DEL-BOM_7d.json"
        assert local_file.exists()
        with local_file.open("r", encoding="utf-8") as fh:
            local_dict = json.load(fh)
        assert "headers" not in local_dict

    def test_upload_app_env_production_skips_local_copy(self):
        payload = {
            "source": "air_india",
            "origin": "BOM",
            "destination": "BLR",
            "advance_days": 30,
            "cookies": ["cookie=secret"],
            "flights": [{"flight_number": "AI-401", "total_fare": 6000.0}],
        }

        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_client.storage.from_.return_value = mock_bucket

        with patch("apix.scraper.storage.get_storage_client", return_value=mock_client), \
             patch.object(settings, "app_env", "production"):
            path = upload_raw_scrape(
                data=payload,
                source="air_india",
                origin="BOM",
                destination="BLR",
                advance_days=30,
                scrape_date=date(2026, 9, 28),
            )

        assert path == "air_india/2026-09-28/BOM-BLR_30d.json"
        mock_bucket.upload.assert_called_once()

        # Local copy MUST NOT exist when APP_ENV=production
        local_file = self.tmp_dir / "air_india" / "2026-09-28" / "BOM-BLR_30d.json"
        assert not local_file.exists()


class TestPurgeRawScrapes:
    def test_parse_date_from_string(self):
        assert parse_date_from_string("2026-05-15") == date(2026, 5, 15)
        assert parse_date_from_string("not-a-date") is None
        assert parse_date_from_string("DEL-BOM_7d.json") is None

    def test_purge_local_directory(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir(parents=True)

        old_dir = raw_dir / "indigo" / "2026-01-10"
        old_dir.mkdir(parents=True)
        old_file = old_dir / "DEL-BOM_7d.json"
        old_file.write_text('{"test": "old"}')

        new_dir = raw_dir / "indigo" / "2026-09-28"
        new_dir.mkdir(parents=True)
        new_file = new_dir / "DEL-BOM_7d.json"
        new_file.write_text('{"test": "new"}')

        cutoff = date(2026, 6, 30)

        with patch.object(settings, "raw_data_dir", raw_dir):
            count, removed = purge_local_directory(cutoff, dry_run=False)

        assert count == 1
        assert not old_file.exists()
        assert not old_dir.exists()  # Empty directory cleaned up
        assert new_file.exists()  # Recent file preserved

    def test_purge_supabase_storage(self):
        cutoff = date(2026, 6, 30)

        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_client.storage.from_.return_value = mock_bucket

        # Mock listing
        # Root level: sources
        mock_bucket.list.side_effect = [
            [{"name": "indigo"}],  # root
            [{"name": "2026-05-01"}, {"name": "2026-09-28"}],  # indigo dates
            [{"name": "DEL-BOM_7d.json"}],  # indigo/2026-05-01 (older than cutoff)
        ]

        with patch("scripts.purge_raw.get_storage_client", return_value=mock_client):
            count, removed = purge_supabase_storage(cutoff, dry_run=False)

        assert count == 1
        assert removed == ["indigo/2026-05-01/DEL-BOM_7d.json"]
        mock_bucket.remove.assert_called_once_with(["indigo/2026-05-01/DEL-BOM_7d.json"])
