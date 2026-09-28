# Ethical Scraping Policy

## Overview

APIx scrapes publicly accessible flight-search pages on IndiGo, Air India,
and MakeMyTrip to collect Indian domestic airfare data. This document defines
the ethical and legal constraints under which all scraping is performed.

---

## 1. robots.txt Compliance (Non-Negotiable)

Every scrape run begins with a programmatic robots.txt check
(`apix/scraper/robots_check.py`). If any path is disallowed:

- The scrape **does not proceed** for that source.
- The outcome is logged as `robots_blocked` in the `scraper_runs` table.
- A censored record is emitted to the pipeline.
- No manual override or circumvention is permitted.

This check is performed at startup and cached for the duration of the run.

---

## 2. Rate Limits

| Control | Value | Location |
|---------|-------|----------|
| Minimum delay between requests | 2 seconds | `SCRAPER_MIN_DELAY_S` |
| Maximum delay between requests | 8 seconds | `SCRAPER_MAX_DELAY_S` |
| Daily collection frequency | Once per day | `COLLECTION_CRON` |
| Max tasks per domain per run | 6 (3 routes × 2 windows) | Scheduler |

Delays are randomised uniformly between min and max to avoid creating
recognisable patterns in server logs.

---

## 3. CAPTCHA Handling

The scraper detects CAPTCHA challenge pages by checking page content for
common CAPTCHA signatures (e.g. "are you a robot", "cf-challenge",
"datadome"). On detection:

- The scrape **immediately stops** for that source and window.
- The event is logged at ERROR level with the timestamp and URL.
- A backoff of at least the next daily scheduled run is applied.
- **No CAPTCHA-solving is attempted**, neither manually nor via third-party
  services.

This is defined as explicitly OUT OF SCOPE in the project brief.

---

## 4. User Agent Rotation

The scraper rotates through a pool of real, recent browser User-Agent
strings (`apix/scraper/user_agents.py`). This is done to present the
same UA fingerprint as a regular user browsing the site — not to evade
detection through deception, but to avoid server-side rejections caused
by the default `python-playwright/x.y` UA string.

---

## 5. IP Rotation and Evasion

- **No IP rotation** is implemented.
- **No proxy pool** is used.
- **No Tor or VPN** is used.

All requests originate from the same IP as the operator's machine. If the
target site bans the IP, the scraper logs the failure and stops gracefully.
Manual investigation and, if appropriate, a request to the site for data
access is the recommended remediation.

---

## 6. Terms of Service

Web scraping exists in a legal grey zone in India (no specific scraping law
as of 2026). The project operates on the following principles:

- Data collected is used for non-commercial, research/prototype purposes.
- No scraped data is redistributed or sold.
- The scraper does not impersonate authenticated users or scrape data behind
  login walls.
- If a source operator sends a cease-and-desist or requests removal, the
  source is immediately disabled.

---

## 7. Data Minimisation

The scraper collects only:
- Flight number, carrier, departure/arrival times
- Fare class, base fare, taxes, total fare, seats available

No personal data (PII), authentication tokens, session cookies, or user
account information is collected or stored.

---

## 8. Out of Scope (Hard Limits)

The following are explicitly prohibited regardless of technical feasibility:

- CAPTCHA solving (automated or manual)
- IP rotation for evasion purposes
- Scraping behind authentication
- Sub-daily / high-frequency scraping
- International routes
- Distributing scraped data to third parties

---

## Contact

For data access requests, ethical concerns, or takedown requests, contact
the project operator directly. Sources can be disabled without code changes
via the `ENABLED_SOURCES` environment variable.
