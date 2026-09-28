"""
Centralised configuration via pydantic-settings.
All values are read strictly from environment variables.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, List, Optional, Union

from pydantic import Field, field_validator, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
    )

    # ── Required FastAPI / Security Settings ──────────────────────────────────
    supabase_url: str = Field(
        ...,
        description="Supabase project URL (e.g. https://<ref>.supabase.co)",
    )
    supabase_service_role_key: str = Field(
        ...,
        description="Supabase service role secret key for administrative access",
    )
    allowed_origins: Union[List[str], str] = Field(
        ...,
        description="Allowed CORS origins (comma-separated string or list)",
    )
    app_env: str = Field(
        ...,
        description="Application environment (e.g. development, staging, production, test)",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///apix.db",
        description="Async SQLAlchemy connection string (sqlite+aiosqlite:///apix.db or postgresql+asyncpg://…)",
    )

    # ── Data directories ──────────────────────────────────────────────────────
    raw_data_dir: Path = Field(default=Path("data/raw"))
    weights_file: Path = Field(default=Path("data/weights/dgca_route_weights.csv"))
    dgca_pdf_dir: Path = Field(default=Path("apix/backtest/data"))
    seed_file: Path = Field(default=Path("data/seed/synthetic_fares.csv"))

    # ── Scraper ───────────────────────────────────────────────────────────────
    collection_cron: str = Field(
        default="30 20 * * *",
        description="APScheduler cron for daily run (UTC). Default = 2am IST.",
    )
    scraper_min_delay_s: float = Field(default=2.0)
    scraper_max_delay_s: float = Field(default=8.0)
    playwright_browser: str = Field(default="chromium")
    playwright_headless: bool = Field(
        default=True,
        description="Whether to run Playwright in headless mode (set False for visible testing).",
    )
    enabled_sources: Union[List[str], str] = Field(
        default=["indigo", "air_india", "makemytrip", "akasa", "spicejet"],
        description="List of sources to enable (accepts comma-separated string or list).",
    )
    redis_url: Optional[str] = Field(
        default=None,
        description="Redis connection URL for distributed scraper queue (e.g. Upstash redis://...)",
    )

    # ── Routes & windows ──────────────────────────────────────────────────────
    routes: List[tuple[str, str]] = Field(
        default=[
            ("DEL", "BOM"), ("DEL", "BLR"), ("BOM", "BLR"), ("DEL", "HYD"),
            ("DEL", "PNQ"), ("DEL", "CCU"), ("BOM", "GOI"), ("DEL", "AMD"),
            ("DEL", "GOI"), ("BLR", "HYD"), ("DEL", "MAA"), ("BOM", "CCU"),
            ("BOM", "HYD"), ("BOM", "MAA"), ("BLR", "CCU"), ("BOM", "AMD"),
            ("BLR", "PNQ"), ("DEL", "SXR"), ("DEL", "PAT"), ("DEL", "GAU"),
            ("BLR", "GOI"), ("BLR", "MAA"), ("HYD", "MAA"), ("BLR", "COK"),
            ("DEL", "LKO"), ("HYD", "GOI"), ("BOM", "COK"), ("DEL", "BBI"),
            ("DEL", "IXB"), ("BLR", "AMD"),
        ],
        description="30 DGCA-weighted domestic corridors",
    )
    advance_windows: Union[List[int], str] = Field(
        default=[1, 7, 15, 30, 45],
        description="Advance-purchase days to collect (full 5-window basket).",
    )

    # ── Validators ────────────────────────────────────────────────────────────
    @field_validator("supabase_url", mode="before")
    @classmethod
    def _normalize_supabase_url(cls, v: Any) -> str:
        if isinstance(v, str):
            v = v.strip().rstrip("/")
            if v.endswith("/rest/v1"):
                v = v[:-8]
            return v.rstrip("/")
        return str(v)

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("["):
                import json
                return json.loads(v)
            return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, (list, tuple, set)):
            return [str(s).strip() for s in v if str(s).strip()]
        return v

    @field_validator("enabled_sources", mode="before")
    @classmethod
    def _parse_enabled_sources(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json
                return json.loads(v)
            return [s.strip() for s in v.split(",") if s.strip()]
        return list(v)

    @field_validator("advance_windows", mode="before")
    @classmethod
    def _parse_advance_windows(cls, v: Any) -> list[int]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json
                return json.loads(v)
            return [int(s.strip()) for s in v.split(",") if s.strip()]
        return list(v)

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")

    def __repr__(self) -> str:
        """Never leak secret values when printing or inspecting settings."""
        items = []
        for k, v in self.__dict__.items():
            k_lower = k.lower()
            if any(s in k_lower for s in ("key", "secret", "password", "token")):
                items.append(f"{k}='[REDACTED]'")
            else:
                items.append(f"{k}={v!r}")
        return f"Settings({', '.join(items)})"

    def __str__(self) -> str:
        return self.__repr__()


def _load_settings() -> Settings:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    try:
        return Settings()
    except (ValidationError, Exception) as exc:
        missing = []
        if isinstance(exc, ValidationError):
            for err in exc.errors():
                if err.get("type") in ("missing", "value_error.missing"):
                    loc = "_".join(str(l) for l in err.get("loc", [])).upper()
                    missing.append(loc)
        # Check required fields directly if pydantic didn't give missing list
        reqs = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "ALLOWED_ORIGINS", "APP_ENV"]
        for r in reqs:
            if not os.environ.get(r) and r not in missing:
                missing.append(r)

        if missing:
            msg = (
                f"FastAPI Startup Failed: Missing required environment variable(s): {', '.join(missing)}. "
                "Please define SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ALLOWED_ORIGINS, and APP_ENV."
            )
        else:
            msg = f"FastAPI Startup Failed: Configuration validation error: {exc}"
        sys.stderr.write(f"\n[CONFIG ERROR] {msg}\n\n")
        raise SystemExit(msg) from None


# Singleton instance loaded on import
settings = _load_settings()
