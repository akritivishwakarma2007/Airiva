"""
main.py — Hardened FastAPI application for APIx.

All API endpoints mounted under prefix /v1:
  /v1/admin/*      → Administrative endpoints (Admin only)
  /v1/index/*      → Public read-only index endpoints
  /v1/raw-quotes/* → Raw quotes endpoints (Analyst / Admin only)
  /health          → Minimal system status {"status": "ok"}
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from apix.api.limiter import limiter
from apix.api.routers import admin as admin_router
from apix.api.routers import index as index_router
from apix.api.routers import quotes as quotes_router
from apix.api.schemas import HealthResponse
from apix.config import settings

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("apix.api")


# ── Security Headers & Request ID Middleware ─────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Applies security headers to every response:
      - X-Content-Type-Options: nosniff
      - X-Frame-Options: DENY
      - Referrer-Policy: no-referrer
      - Strict-Transport-Security (when APP_ENV=production)
      - X-Request-ID: unique request tracking identifier
    """
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        response: Response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Request-ID"] = request_id

        if settings.app_env.lower() == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


app = FastAPI(
    title="APIx — Indian Domestic Airfare Price Index API",
    description="Hardened, secure FastAPI service for APIx index calculation and fare analytics.",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── SlowAPI Rate Limiter ──────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── Security Headers ──────────────────────────────────────────────────────────
app.add_middleware(SecurityHeadersMiddleware)

# ── CORS Middleware (Whitelisted Origins Only, No Wildcard) ───────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With", "X-Request-ID"],
)


# ── Generic Error Handler (No Leaked Stack Traces, SQL, or Paths) ─────────────
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.exception("Unhandled server exception [request_id=%s]: %s", request_id, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )


# ── API Routers Under Prefix /v1 ──────────────────────────────────────────────
app.include_router(admin_router.router, prefix="/v1")
app.include_router(index_router.router, prefix="/v1")
app.include_router(quotes_router.router, prefix="/v1")


# ── Health Check (Returns {"status": "ok"} only) ──────────────────────────────
@app.get("/health", response_model=HealthResponse, tags=["System"])
@app.get("/v1/health", response_model=HealthResponse, tags=["System"])
@limiter.limit("60/minute")
async def health_check(request: Request) -> HealthResponse:
    """
    Minimal health check.
    Returns status "ok" only. Never reveals versions, paths, or database internals.
    """
    return HealthResponse(status="ok")


# ── Dashboard & Static Assets ─────────────────────────────────────────────────
_dashboard_dir = Path(__file__).parent.parent / "dashboard"
if _dashboard_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=str(_dashboard_dir), html=True), name="dashboard")
    logger.info("Dashboard static files mounted at /dashboard")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    fav_path = _dashboard_dir / "favicon.ico"
    if fav_path.exists():
        return FileResponse(fav_path, media_type="image/x-icon")
    return Response(status_code=204)


@app.get("/image.png", include_in_schema=False)
async def image():
    img_path = _dashboard_dir / "image.png"
    if img_path.exists():
        return FileResponse(img_path, media_type="image/png")
    return Response(status_code=404)


@app.get("/image-bg.png", include_in_schema=False)
@app.get("/image copy.png", include_in_schema=False)
@app.get("/image%20copy.png", include_in_schema=False)
async def image_bg():
    img_path = _dashboard_dir / "image-bg.png"
    if img_path.exists():
        return FileResponse(img_path, media_type="image/png")
    return Response(status_code=404)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/dashboard")
