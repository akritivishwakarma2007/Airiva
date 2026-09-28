"""
tests/test_api_security.py — Hardened API security and permissions test suite.

Covers:
  - Missing token -> 401
  - Analyst on admin route -> 403
  - Admin on admin route -> 200
  - Disallowed CORS origin blocked
  - Rate limiting -> 429
  - Input validation (strict schemas, forbid extra fields, email validation)
  - Generic 500 errors (no leaked paths/stack traces)
  - Security headers (nosniff, DENY, no-referrer, HSTS)
  - Health check returns {"status": "ok"} only
  - Config fails when required variables are missing
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apix.api.auth import get_supabase_service_client
from apix.api.limiter import limiter
from apix.api.main import app
from apix.config import Settings


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Reset rate limiter counts between tests."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def mock_supabase():
    """Provides a mocked Supabase client for auth and database operations."""
    mock = MagicMock()
    # Default to an admin user
    mock.auth.get_user.return_value.user.id = "mock-admin-uuid"
    mock.auth.get_user.return_value.user.email = "admin@airiva.local"
    mock.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"role": "admin"}
    ]
    mock.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value.data = []
    mock.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value.count = 0
    mock.table.return_value.insert.return_value.execute.return_value.data = [{"id": 1}]
    mock.table.return_value.upsert.return_value.execute.return_value.data = [{"id": "mock-user-id"}]
    mock.auth.admin.invite_user_by_email.return_value.user.id = "invited-user-id"

    app.dependency_overrides[get_supabase_service_client] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_supabase_service_client, None)


@pytest.fixture
def client():
    return TestClient(app)


# ── 1. Authentication & Role Tests ────────────────────────────────────────────

def test_missing_token_returns_401(client):
    """Calling protected routes without an Authorization header must return 401."""
    # Protected admin route
    r_admin = client.get("/v1/admin/scrape-log")
    assert r_admin.status_code == 401
    assert "Missing or invalid Authorization header" in r_admin.json()["detail"]

    # Protected raw-quotes route
    r_quotes = client.get("/v1/raw-quotes")
    assert r_quotes.status_code == 401


def test_invalid_token_returns_401(client, mock_supabase):
    """Calling protected routes with an invalid JWT must return 401."""
    mock_supabase.auth.get_user.side_effect = Exception("Invalid JWT signature")
    r = client.get("/v1/raw-quotes", headers={"Authorization": "Bearer bad-token"})
    assert r.status_code == 401
    assert "Invalid or expired token" in r.json()["detail"]


def test_analyst_on_admin_route_returns_403(client, mock_supabase):
    """Analyst role must be rejected with 403 Forbidden on all /v1/admin/* routes."""
    mock_supabase.auth.get_user.return_value.user.id = "mock-analyst-uuid"
    mock_supabase.auth.get_user.return_value.user.email = "analyst@airiva.local"
    # Server-side profile returns analyst role
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"role": "analyst"}
    ]

    headers = {"Authorization": "Bearer analyst-token"}

    # Admin scrape-log
    r1 = client.get("/v1/admin/scrape-log", headers=headers)
    assert r1.status_code == 403
    assert "Admin privileges required" in r1.json()["detail"]

    # Admin trigger-scrape
    r2 = client.post("/v1/admin/trigger-scrape", json={"sources": ["indigo"]}, headers=headers)
    assert r2.status_code == 403

    # Admin invite-user
    r3 = client.post("/v1/admin/invite-user", json={"email": "new@airiva.local", "role": "analyst"}, headers=headers)
    assert r3.status_code == 403


def test_admin_ok_returns_200(client, mock_supabase):
    """Admin role must successfully access /v1/admin/scrape-log."""
    mock_supabase.auth.get_user.return_value.user.id = "mock-admin-uuid"
    mock_supabase.auth.get_user.return_value.user.email = "admin@airiva.local"
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"role": "admin"}
    ]

    headers = {"Authorization": "Bearer valid-admin-token"}
    r = client.get("/v1/admin/scrape-log", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "data" in data
    assert "total" in data
    assert "page" in data


# ── 2. CORS Tests ─────────────────────────────────────────────────────────────

def test_allowed_origin_permitted(client):
    """Allowed CORS origins receive Access-Control-Allow-Origin header."""
    r = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_disallowed_origin_blocked(client):
    """Disallowed CORS origins do NOT receive Access-Control-Allow-Origin header."""
    r = client.get("/health", headers={"Origin": "https://malicious-attacker.com"})
    assert "access-control-allow-origin" not in r.headers


# ── 3. Rate Limiting Tests ───────────────────────────────────────────────────

def test_rate_limit_admin_returns_429(client, mock_supabase):
    """Exceeding 10 requests/minute on /v1/admin/* returns 429 Too Many Requests."""
    mock_supabase.auth.get_user.return_value.user.id = "mock-admin-uuid"
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"role": "admin"}
    ]

    headers = {"Authorization": "Bearer admin-token"}
    statuses = []
    for _ in range(12):
        res = client.get("/v1/admin/scrape-log", headers=headers)
        statuses.append(res.status_code)

    assert 429 in statuses, f"Expected 429 in responses, got: {statuses}"


# ── 4. Admin Endpoints Functionality ──────────────────────────────────────────

def test_trigger_scrape_refuses_disabled_sources(client, mock_supabase):
    """trigger-scrape must refuse sources that are disabled or unconfigured."""
    headers = {"Authorization": "Bearer admin-token"}
    payload = {"sources": ["unknown_scraper_airline"]}

    r = client.post("/v1/admin/trigger-scrape", json=payload, headers=headers)
    assert r.status_code == 400
    assert "Refusing disabled or unconfigured source" in r.json()["detail"]


def test_trigger_scrape_accepts_enabled_sources_and_writes_audit(client, mock_supabase):
    """trigger-scrape starts a run for enabled sources and writes audit_log."""
    headers = {"Authorization": "Bearer admin-token"}
    payload = {"sources": ["indigo", "air_india"]}

    with patch("apix.api.routers.admin._run_scraper_task"):
        r = client.post("/v1/admin/trigger-scrape", json=payload, headers=headers)
        assert r.status_code == 202
        assert r.json()["status"] == "started"

    # Verify audit_log insert was called
    mock_supabase.table.assert_any_call("audit_log")


def test_invite_user_validates_email_and_role(client, mock_supabase):
    """invite-user requires valid email, role in [analyst, admin], and rejects unknown fields."""
    headers = {"Authorization": "Bearer admin-token"}

    # Invalid email
    r_bad_email = client.post(
        "/v1/admin/invite-user",
        json={"email": "not-an-email", "role": "analyst"},
        headers=headers,
    )
    assert r_bad_email.status_code == 422

    # Invalid role
    r_bad_role = client.post(
        "/v1/admin/invite-user",
        json={"email": "valid@example.com", "role": "superadmin"},
        headers=headers,
    )
    assert r_bad_role.status_code == 422

    # Unknown field rejected (ConfigDict extra="forbid")
    r_extra = client.post(
        "/v1/admin/invite-user",
        json={"email": "valid@example.com", "role": "analyst", "is_admin": True},
        headers=headers,
    )
    assert r_extra.status_code == 422

    # Valid invite
    r_ok = client.post(
        "/v1/admin/invite-user",
        json={"email": "valid@example.com", "role": "analyst"},
        headers=headers,
    )
    assert r_ok.status_code == 201
    assert r_ok.json()["status"] == "ok"
    mock_supabase.auth.admin.invite_user_by_email.assert_called_once()
    mock_supabase.table.assert_any_call("audit_log")


# ── 5. Health Check ───────────────────────────────────────────────────────────

def test_health_check_returns_only_status_ok(client):
    """Health check must return exactly {"status": "ok"} with no leaked paths, versions, or DB details."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ── 6. Security Headers ───────────────────────────────────────────────────────

def test_security_headers_present(client):
    """Verify nosniff, DENY, no-referrer, and X-Request-ID are present."""
    r = client.get("/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "no-referrer"
    assert "x-request-id" in r.headers


# ── 7. Generic Error Handling (No Leaks) ──────────────────────────────────────

def test_generic_exception_handler_masks_internals():
    """Unhandled exceptions must return generic 500 with request_id and no stack trace."""
    no_raise_client = TestClient(app, raise_server_exceptions=False)
    from apix.api.routers import index
    with patch.object(index, "AsyncSessionLocal", side_effect=RuntimeError("Database Connection Failed: SELECT * FROM keys")):
        r = no_raise_client.get("/v1/index/daily")
        assert r.status_code == 500
        body = r.json()
        assert body["detail"] == "Internal server error"
        assert "request_id" in body
        assert "Database" not in body["detail"]
        assert "SELECT" not in body["detail"]


# ── 8. Config Validation ──────────────────────────────────────────────────────

def test_config_fails_when_required_variable_missing():
    """Config must raise ValidationError / fail when required environment variables are absent."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        errors = [e["loc"][0] for e in exc_info.value.errors()]
        assert "supabase_url" in errors
        assert "supabase_service_role_key" in errors
        assert "allowed_origins" in errors
        assert "app_env" in errors


def test_config_never_logs_secrets():
    """Settings string representation must mask secrets."""
    s = Settings(
        supabase_url="https://ref.supabase.co",
        supabase_service_role_key="super-secret-service-key-12345",
        allowed_origins="http://localhost:3000",
        app_env="production",
    )
    rep = repr(s)
    assert "super-secret-service-key-12345" not in rep
    assert "[REDACTED]" in rep
