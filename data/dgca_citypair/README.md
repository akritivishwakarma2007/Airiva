# DGCA Domestic City-Pair Traffic Statistics (2025 – 2026)

This directory contains monthly city-pair domestic traffic statistics published by the Directorate General of Civil Aviation (DGCA), Government of India.

## Files

### Year 2025 (Full Year: 12 Months)
- `citypair_2025_01.xlsx` — January 2025
- `citypair_2025_02.xlsx` — February 2025
- `citypair_2025_03.xlsx` — March 2025
- `citypair_2025_04.xlsx` — April 2025
- `citypair_2025_05.xlsx` — May 2025
- `citypair_2025_06.xlsx` — June 2025
- `citypair_2025_07.xlsx` — July 2025
- `citypair_2025_08.xlsx` — August 2025
- `citypair_2025_09.xlsx` — September 2025
- `citypair_2025_10.xlsx` — October 2025
- `citypair_2025_11.xlsx` — November 2025
- `citypair_2025_12.xlsx` — December 2025

### Year 2026 (8 Months to Date)
- `citypair_2026_01.xlsx` — January 2026
- `citypair_2026_02.xlsx` — February 2026
- `citypair_2026_03.xlsx` — March 2026
- `citypair_2026_04.xlsx` — April 2026
- `citypair_2026_05.xlsx` — May 2026
- `citypair_2026_06.xlsx` — June 2026
- `citypair_2026_07.xlsx` — July 2026
- `citypair_2026_08.xlsx` — August 2026

## Columns in Each File
- `CITY 1`: Origin city (e.g. Delhi, Mumbai, Bengaluru)
- `CITY 2`: Destination city (e.g. Mumbai, Bengaluru)
- `Passengers (In Number)`: Total passengers transported on that corridor
- `Freight (In Tonne)`: Air cargo volume
- `Mail (In Tonne)`: Air mail volume

## How APIx Uses This Data
These files provide the empirical passenger counts for:
- `DEL-BOM` (Delhi ↔ Mumbai)
- `DEL-BLR` (Delhi ↔ Bengaluru)
- `BOM-BLR` (Mumbai ↔ Bengaluru)

They allow computing dynamic, empirical route traffic shares across seasons instead of static weights.
