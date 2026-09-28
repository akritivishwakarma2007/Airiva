"""
robots_check.py — robots.txt compliance helper.

Fetches and caches the robots.txt for a given domain and checks whether
the target path is allowed for a given user agent.

If robots.txt cannot be fetched, NEVER assume permission: skip the source
for that run and log "robots.txt unconfirmed - skipped".
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger(__name__)

# Cache parsed robots.txt per domain to avoid repeated fetches per run
# Maps domain_url -> RobotFileParser (if fetched) or None (if fetch failed / unconfirmed)
_CACHE: dict[str, RobotFileParser | None] = {}
_FETCHED: set[str] = set()


def _get_parser(domain_url: str) -> RobotFileParser | None:
    """
    Fetch and parse robots.txt for a domain, with in-memory cache.
    If robots.txt cannot be fetched, returns None (never assumes permission).
    """
    if domain_url in _FETCHED:
        return _CACHE.get(domain_url)

    robots_url = f"{domain_url.rstrip('/')}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)

    try:
        resp = httpx.get(robots_url, timeout=10, follow_redirects=True)
        resp.raise_for_status()
        parser.parse(resp.text.splitlines())
        logger.info("Fetched robots.txt from %s", robots_url)
        _CACHE[domain_url] = parser
    except Exception as exc:
        logger.warning(
            "robots.txt unconfirmed - skipped: Could not fetch robots.txt from %s (%s). Never assuming permission.",
            robots_url, exc,
        )
        _CACHE[domain_url] = None

    _FETCHED.add(domain_url)
    return _CACHE.get(domain_url)


def is_allowed(url: str, user_agent: str = "*") -> tuple[bool, str]:
    """
    Check whether ``url`` may be fetched by ``user_agent`` per robots.txt.
    If robots.txt cannot be fetched, refuses permission and returns:
    (False, "robots.txt unconfirmed - skipped").
    """
    parsed = urlparse(url)
    domain_url = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path or "/"

    parser = _get_parser(domain_url)
    if parser is None:
        logger.warning("robots.txt unconfirmed - skipped for %s", url)
        return False, "robots.txt unconfirmed - skipped"

    allowed = parser.can_fetch(user_agent, url)
    if not allowed:
        reason = f"robots_txt_disallows path={path} ua={user_agent}"
        logger.warning("robots.txt blocks %s for UA '%s'", url, user_agent)
        return False, reason

    return True, "allowed"


def clear_cache() -> None:
    """Clear the in-memory robots.txt cache (useful in tests)."""
    _CACHE.clear()
    _FETCHED.clear()
