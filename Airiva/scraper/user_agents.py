"""
user_agents.py — Rotating user-agent pool.

Maintains a curated list of real browser UA strings to rotate through
during scraping. Rotation is random per request to reduce fingerprinting.
"""
from __future__ import annotations

import random

# Curated pool of recent, real browser User-Agent strings (Chrome/Firefox, desktop)
_UA_POOL: list[str] = [
    # Chrome 126 / Windows 11
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    # Chrome 127 / Windows 11
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    # Chrome 126 / macOS Sonoma
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.6478.127 Safari/537.36",
    # Chrome 127 / macOS Sequoia
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    # Firefox 128 / Windows 11
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
    "Gecko/20100101 Firefox/128.0",
    # Firefox 127 / Ubuntu
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:127.0) "
    "Gecko/20100101 Firefox/127.0",
    # Edge 126 / Windows 11
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
    # Safari 17 / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]


def get_random_ua() -> str:
    """Return a randomly selected user-agent string from the pool."""
    return random.choice(_UA_POOL)


def get_ua_pool() -> list[str]:
    """Return the full UA pool (read-only copy)."""
    return list(_UA_POOL)
