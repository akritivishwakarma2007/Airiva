"""
apix/api/limiter.py — Shared slowapi Limiter instance.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# Default 60 requests/minute per client IP for public routes
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
