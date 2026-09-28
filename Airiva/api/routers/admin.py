"""
apix/api/routers/admin.py — Administrative endpoints (Admin only).

Endpoints:
  POST /v1/admin/trigger-scrape — trigger a scrape run for enabled sources
  POST /v1/admin/invite-user    — invite a new user via Supabase Auth Admin
  GET  /v1/admin/scrape-log     — paginated scrape logs
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from supabase import Client

from apix.api.auth import get_supabase_service_client, require_admin
from apix.api.limiter import limiter
from apix.api.schemas import (
    CreateUserRequest,
    InviteUserRequest,
    ScrapeLogItem,
    ScrapeLogPage,
    TriggerScrapeRequest,
)
from apix.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


async def _run_scraper_task(sources: List[str]) -> None:
    """Background task to run scrapers safely."""
    try:
        from apix.scraper.runner import run_collection_cycle
        logger.info("Executing background scraper task for sources: %s", sources)
        await run_collection_cycle(sources=sources)
    except Exception as exc:
        logger.error("Scraper execution background task failed: %s", exc)


@router.post("/trigger-scrape", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute")
async def trigger_scrape(
    request: Request,
    payload: TriggerScrapeRequest,
    background_tasks: BackgroundTasks,
    admin: Dict[str, Any] = Depends(require_admin),
    client: Client = Depends(get_supabase_service_client),
) -> Dict[str, Any]:
    """
    Trigger a scrape run for sources that are ENABLED in config only.
    Refuses any disabled or unconfigured source and logs to audit_log.
    """
    enabled_set = set(settings.enabled_sources)

    if payload.sources:
        for src in payload.sources:
            if src not in enabled_set:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Refusing disabled or unconfigured source: '{src}'. Allowed sources: {sorted(enabled_set)}",
                )
        sources_to_run = payload.sources
    else:
        sources_to_run = list(settings.enabled_sources)

    # Record action in audit_log
    try:
        audit_entry = {
            "actor_id": admin["id"],
            "action": "trigger_scrape",
            "detail": {
                "sources": sources_to_run,
                "actor_email": admin.get("email"),
            },
        }
        client.table("audit_log").insert(audit_entry).execute()
    except Exception as exc:
        logger.error("Failed to write to audit_log for trigger-scrape: %s", exc)

    # Dispatch scrape in background
    background_tasks.add_task(_run_scraper_task, sources_to_run)

    return {
        "status": "started",
        "sources": sources_to_run,
        "message": f"Scrape run initiated for {len(sources_to_run)} source(s)",
    }


@router.post("/invite-user", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def invite_user(
    request: Request,
    body: InviteUserRequest,
    admin: Dict[str, Any] = Depends(require_admin),
    client: Client = Depends(get_supabase_service_client),
) -> Dict[str, Any]:
    """
    Invite a new user with role 'analyst' or 'admin'.
    Uses supabase.auth.admin.invite_user_by_email and logs to audit_log.
    """
    try:
        invite_res = client.auth.admin.invite_user_by_email(
            email=body.email,
            options={"data": {"role": body.role}},
        )
    except Exception as exc:
        logger.error("Supabase user invitation failed for %s: %s", body.email, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to send user invitation. Please check the email and try again.",
        ) from None

    # Upsert profile with assigned role
    try:
        if invite_res and getattr(invite_res, "user", None):
            user_id = invite_res.user.id
            client.table("profiles").upsert({
                "id": user_id,
                "email": body.email,
                "role": body.role,
            }).execute()
    except Exception as exc:
        logger.warning("Failed to initialize profile for invited user %s: %s", body.email, exc)

    # Write audit log entry
    try:
        audit_entry = {
            "actor_id": admin["id"],
            "action": "invite_user",
            "detail": {
                "invited_email": body.email,
                "role": body.role,
                "invited_by": admin.get("email"),
            },
        }
        client.table("audit_log").insert(audit_entry).execute()
    except Exception as exc:
        logger.error("Failed to write to audit_log for invite-user: %s", exc)

    return {
        "status": "ok",
        "message": f"Invitation sent to {body.email}",
        "role": body.role,
    }


@router.post("/create-user", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_user(
    request: Request,
    body: CreateUserRequest,
    admin: Dict[str, Any] = Depends(require_admin),
    client: Client = Depends(get_supabase_service_client),
) -> Dict[str, Any]:
    """
    Directly create a user with email and password and assign role.
    Only callable by an Administrator.
    Sets email_confirm=True so the user can immediately log in without email confirmation.
    """
    try:
        user_res = client.auth.admin.create_user({
            "email": body.email,
            "password": body.password,
            "email_confirm": True,
            "user_metadata": {"role": body.role},
        })
    except Exception as exc:
        logger.error("Supabase user creation failed for %s: %s", body.email, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create user: {str(exc)}",
        ) from None

    user_id = getattr(getattr(user_res, "user", None), "id", None)
    if not user_id and isinstance(user_res, dict):
        user_id = user_res.get("user", {}).get("id")

    if user_id:
        try:
            client.table("profiles").upsert({
                "id": str(user_id),
                "email": body.email,
                "role": body.role,
            }).execute()
        except Exception as exc:
            logger.warning("Failed to initialize profile for created user %s: %s", body.email, exc)

    # Write audit log entry
    try:
        audit_entry = {
            "actor_id": admin["id"],
            "action": "create_user",
            "detail": {
                "created_email": body.email,
                "role": body.role,
                "created_by": admin.get("email"),
            },
        }
        client.table("audit_log").insert(audit_entry).execute()
    except Exception as exc:
        logger.error("Failed to write to audit_log for create-user: %s", exc)

    return {
        "status": "ok",
        "message": f"User {body.email} created with role '{body.role}'",
        "user_id": str(user_id) if user_id else None,
        "role": body.role,
    }


@router.get("/scrape-log", response_model=ScrapeLogPage)
@limiter.limit("10/minute")
async def get_scrape_log(
    request: Request,
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=50, ge=1, le=200, description="Items per page (max 200)"),
    admin: Dict[str, Any] = Depends(require_admin),
    client: Client = Depends(get_supabase_service_client),
) -> ScrapeLogPage:
    """
    Return paginated scrape run logs. (Admin only)
    """
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size - 1

    try:
        res = (
            client.table("scrape_log")
            .select("*", count="exact")
            .order("id", desc=True)
            .range(start_idx, end_idx)
            .execute()
        )
        total = res.count if res.count is not None else len(res.data or [])
        items = [ScrapeLogItem(**row) for row in (res.data or [])]
        return ScrapeLogPage(
            total=total,
            page=page,
            page_size=page_size,
            data=items,
        )
    except Exception as exc:
        logger.error("Failed to fetch scrape_log from Supabase: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve scrape logs",
        ) from None
