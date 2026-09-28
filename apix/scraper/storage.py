"""
Airiva/scraper/storage.py — Private Supabase Storage & Sanitization for raw scrape JSON payloads.

Stores raw scrape JSON in the private Supabase Storage bucket "raw-scrapes":
- Target key format: {source}/{YYYY-MM-DD}/{route}_{window}d.json
- Strips request headers, cookies, tokens, and personal data before saving.
- Only keeps local data/raw/ copy when APP_ENV=development.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from apix.config import settings

logger = logging.getLogger(__name__)

BUCKET_NAME = "raw-scrapes"

# Keywords representing sensitive, personal, header, or credential fields (case-insensitive)
STRIP_KEY_PATTERNS = {
    # Request & response headers
    "header", "headers", "request_headers", "requestheaders", "request-headers",
    "response_headers", "responseheaders", "response-headers",
    # Cookies & session identifiers
    "cookie", "cookies", "request_cookies", "requestcookies", "response_cookies",
    "set-cookie", "setcookie", "session", "session_id", "sessionid", "session_token",
    # Tokens & authentication credentials
    "token", "tokens", "access_token", "accesstoken", "id_token", "refresh_token",
    "auth", "authorization", "bearer", "secret", "api_key", "apikey",
    # Personal & passenger identifiable data
    "user", "user_id", "userid", "email", "phone", "telephone", "mobile",
    "passenger", "passengers", "passenger_name", "pnr", "ip", "client_ip",
    "ip_address", "personal_data"
}


SENSITIVE_SUBSTRINGS = (
    "cookie", "header", "token", "auth", "secret", "pnr",
    "email", "user", "passenger", "phone", "mobile", "session",
    "password", "bearer"
)


def is_sensitive_key(key: str) -> bool:
    """Check if a dictionary key represents sensitive/private information."""
    k = key.lower().replace("-", "_").strip()
    if k in STRIP_KEY_PATTERNS:
        return True
    return any(pattern in k for pattern in SENSITIVE_SUBSTRINGS)



def sanitize_raw_data(data: Any) -> Any:
    """
    Recursively sanitize raw scraper data:
    Strips request headers, response headers, cookies, tokens, and personal data.
    Preserves all flight pricing, inventory, schedule, and route attributes.
    """
    if isinstance(data, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in data.items():
            if is_sensitive_key(str(k)):
                continue
            cleaned[k] = sanitize_raw_data(v)
        return cleaned
    elif isinstance(data, list):
        return [sanitize_raw_data(item) for item in data]
    elif isinstance(data, str):
        # Redact token-like or cookie-like strings
        lower = data.lower().strip()
        if lower.startswith("bearer ") or lower.startswith("set-cookie:") or "sessionid=" in lower:
            return "[REDACTED]"
        return data
    else:
        return data


def get_storage_client():
    """Create Supabase client using service-role key for Storage administration."""
    from supabase import create_client
    url = settings.supabase_url
    key = settings.supabase_service_role_key
    if not (url and key):
        logger.warning("Supabase credentials not set; skipping Supabase Storage upload")
        return None
    key_str = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key)
    return create_client(url, key_str)


def upload_raw_scrape(
    data: dict,
    source: str,
    origin: str,
    destination: str,
    advance_days: int,
    scrape_date: Optional[str | date] = None,
) -> Optional[str]:
    """
    Sanitize and upload raw scrape JSON to private Supabase Storage bucket 'raw-scrapes':
    - Target key: {source}/{YYYY-MM-DD}/{route}_{window}d.json
    - Upload using service-role client.
    - Keep local data/raw/ copy ONLY when APP_ENV=development.
    """
    # 1. Strip request headers, cookies, tokens, and personal data
    clean_data = sanitize_raw_data(data)

    if isinstance(scrape_date, date):
        date_str = scrape_date.isoformat()
    elif isinstance(scrape_date, str) and scrape_date:
        date_str = scrape_date[:10]
    else:
        date_str = date.today().isoformat()

    route = f"{origin.upper()}-{destination.upper()}"
    filename = f"{route}_{advance_days}d.json"
    storage_path = f"{source}/{date_str}/{filename}"

    raw_bytes = json.dumps(clean_data, indent=2, default=str).encode("utf-8")

    # 2. Upload to Supabase Storage private bucket 'raw-scrapes'
    client = get_storage_client()
    if client:
        try:
            client.storage.from_(BUCKET_NAME).upload(
                path=storage_path,
                file=raw_bytes,
                file_options={"content-type": "application/json", "upsert": "true"},
            )
            logger.info("[%s] Uploaded raw scrape to Supabase Storage: %s/%s", source, BUCKET_NAME, storage_path)
        except Exception as exc:
            logger.error("[%s] Failed to upload raw scrape to Supabase Storage (%s): %s", source, storage_path, exc)
    else:
        logger.warning("[%s] Service-role client unavailable for Storage upload", source)

    # 3. Local copy: Keep local data/raw/ copy ONLY when APP_ENV=development
    is_development = settings.app_env.lower() == "development"
    if is_development:
        try:
            local_dir = Path(settings.raw_data_dir) / source / date_str
            local_dir.mkdir(parents=True, exist_ok=True)
            local_path = local_dir / filename
            with local_path.open("w", encoding="utf-8") as fh:
                json.dump(clean_data, fh, indent=2, default=str)
            logger.info("[%s] Local copy saved (APP_ENV=development): %s", source, local_path)
        except Exception as exc:
            logger.warning("[%s] Failed to write local raw copy %s: %s", source, filename, exc)
    else:
        logger.debug("[%s] APP_ENV=%s: Skipping local data/raw/ file write", source, settings.app_env)

    return storage_path
