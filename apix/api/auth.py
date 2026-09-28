"""
apix/api/auth.py — Authentication and authorization dependencies for FastAPI.

Validates Supabase JWTs server-side via supabase.auth.get_user(jwt) and retrieves
user roles directly from the server-side `profiles` table using the service-role client.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, create_client

from apix.config import settings

logger = logging.getLogger(__name__)

# Security scheme for Swagger UI and header extraction
security_scheme = HTTPBearer(auto_error=False)

_service_client: Optional[Client] = None


def get_supabase_service_client() -> Client:
    """Singleton getter for Supabase service role client."""
    global _service_client
    if _service_client is None:
        _service_client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return _service_client


async def require_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
    client: Client = Depends(get_supabase_service_client),
) -> Dict[str, Any]:
    """
    Verify the Bearer token with Supabase Auth and fetch role server-side.

    Returns:
        dict: {"id": uuid, "email": email, "role": role}

    Raises:
        HTTPException(401): If token is missing, invalid, or expired.
        HTTPException(403): If role is not allowed (not 'analyst' or 'admin').
    """
    # 1. Read Authorization header
    token: Optional[str] = None
    if credentials is not None and credentials.credentials:
        token = credentials.credentials.strip()
    else:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Verify token with Supabase (supabase.auth.get_user(jwt))
    try:
        user_res = client.auth.get_user(token)
        if not user_res or not user_res.user:
            raise ValueError("Invalid user response from auth provider")
        user = user_res.user
    except Exception as exc:
        logger.warning("Supabase token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    # 3. Look up the role from the profiles table SERVER-SIDE with the service client
    try:
        res = client.table("profiles").select("role").eq("id", user.id).limit(1).execute()
        if not res.data:
            logger.warning("No profile found for authenticated user %s", user.id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: User profile not found",
            )
        role = res.data[0].get("role")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to query profile for user %s: %s", user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Unable to verify user role",
        ) from None

    if role not in ("analyst", "admin"):
        logger.warning("User %s has unauthorized role: %s", user.id, role)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Role '{role}' is not permitted",
        )

    return {
        "id": user.id,
        "email": user.email,
        "role": role,
    }


async def require_admin(
    user: Dict[str, Any] = Depends(require_user),
) -> Dict[str, Any]:
    """
    Ensure the authenticated user has the 'admin' role.

    Raises:
        HTTPException(403): If the user is not an admin.
    """
    if user.get("role") != "admin":
        logger.warning("Admin access denied for user %s with role %s", user.get("id"), user.get("role"))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Admin privileges required",
        )
    return user
