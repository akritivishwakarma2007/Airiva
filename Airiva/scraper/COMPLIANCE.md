# APIx Scraper Compliance Audit & Ethical Scraping Matrix

Last updated: September 2026
Standard: RFC 9309 (Robots Exclusion Protocol) & Indian Civil Aviation Fair-Use Research Framework

## Overview
Before onboarding any airline carrier or Online Travel Agent (OTA) data source into APIx, a strict two-tier compliance verification is conducted:
1. **`robots.txt` Compliance (Non-negotiable)**: Target search URLs and backend API paths must be permitted for automated user agents (`*` or designated research agents). If a route or query path is disallowed, scraping is strictly prohibited.
2. **Terms of Service (ToS) Review**: Terms are evaluated for commercial extraction, reselling restrictions, and acceptable research/price index prototype utilization under polite rate limits without authentication bypass or CAPTCHA circumvention.

---

## Source Evaluation Matrix

| Source | Category | Target Domain | `robots.txt` Analysis | Terms of Service (ToS) Restriction | Verdict | Current Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **IndiGo** | Direct Carrier | `goindigo.in` | Disallows `/search.html`, administrative assets; flight search SPA endpoints permitted for general agents. | Non-commercial research acceptable; strict rate limits observed. | **PASS** | Active Pilot Source |
| **Air India** | Direct Carrier | `airindia.com` | Disallows `/bin/`, `/content/dam/*`, loyalty redemption; search engine booking paths permitted. | Non-commercial research acceptable; rate limited. | **PASS** | Active Pilot Source |
| **MakeMyTrip** | OTA | `makemytrip.com` | Disallows hotel booking funnel, account portals; flight search endpoints permitted under `User-agent: *`. | Prohibits commercial resale and data redistribution; non-commercial statistical aggregation. | **PASS** | Active Pilot Source |
| **Akasa Air** | Direct Carrier | `akasaair.com` | `User-Agent: *` with no `Disallow` directives (fully open search endpoints). | Prohibits commercial exploitation and abusive bot traffic; research index with polite delays is permitted. | **PASS** | **Cleared for Full Basket** |
| **SpiceJet** | Direct Carrier | `spicejet.com` | `User-agent: *` with `Disallow:` (empty string, completely unrestricted). | Prohibits commercial automated scraping and reselling; public fare observation within polite limits permitted. | **PASS** | **Cleared for Full Basket** |
| **Air India Express** | Direct Carrier | `airindiaexpress.com` | **Disallows `/flight-availability`** explicitly for all user agents. | Prohibits automated access to flight availability engine. | **RESTRICTED** | **Evaluated, Restricted** (Not Scraped) |
| **Cleartrip** | OTA | `cleartrip.com` | **Disallows `/flights/search*`** and `/m/flights/search*` explicitly. | Prohibits automated crawling of flight search results. | **RESTRICTED** | **Evaluated, Restricted** (Not Scraped) |
| **Ixigo** | OTA | `ixigo.com` | **Disallows `/flights/search`**, `/search/result/`, and `/api/` explicitly. | Prohibits automated bots and data extraction. | **RESTRICTED** | **Evaluated, Restricted** (Not Scraped) |
| **EaseMyTrip** | OTA | `easemytrip.com` | **Disallows `/flight-search/listing*`** and `/cheap-flights/`. | Explicit prohibition of automated screen scraping. | **RESTRICTED** | **Evaluated, Restricted** (Not Scraped) |
| **Goibibo** | OTA | `goibibo.com` | **Disallows `/flights/*?*`**, `/flight/searchticket/`, and `/api/`. | Prohibits automated scraping and querying. | **RESTRICTED** | **Evaluated, Restricted** (Not Scraped) |
| **Yatra** | OTA | `yatra.com` | Active WAF/Akamai edge resets automated connections (`ERR_CONNECTION_RESET`/`ERR_HTTP2_PROTOCOL_ERROR`); blocks programmatic access. | Master User Agreement restricts automated copying, reproduction, and non-personal use. | **RESTRICTED** | **Evaluated, Restricted** (Not Scraped) |

---

## Approved Sources for 5-Source Basket

Per the compliance audit above, exactly 5 sources clear compliance:
1. `indigo` (IndiGo) — Direct Carrier
2. `air_india` (Air India) — Direct Carrier
3. `makemytrip` (MakeMyTrip) — OTA
4. `akasa` (Akasa Air) — Direct Carrier
5. `spicejet` (SpiceJet) — Direct Carrier

All other evaluated candidates (`airindiaexpress`, `cleartrip`, `ixigo`, `easemytrip`, `goibibo`) fail the mandatory `robots.txt` compliance test and are documented as **evaluated, restricted**. In accordance with the ethical scraping charter, they will NOT be scraped under any circumstances.
