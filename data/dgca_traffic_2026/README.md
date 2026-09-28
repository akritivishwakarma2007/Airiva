# DGCA Airline Operating & Traffic Statistics (2026)

This directory contains official DGCA (Directorate General of Civil Aviation) **Monthly Traffic and Operating Statistics (Form A)** for Indian domestic and international carriers for the year 2026.

## Files

| File | Airline / Carrier | Sector |
|------|-------------------|--------|
| `indigo_2026.xlsx` | InterGlobe Aviation (IndiGo) | Scheduled Domestic & International |
| `air_india_2026.xlsx` | Air India | Scheduled Domestic & International |
| `air_india_express_2026.xlsx` | Air India Express | Scheduled Domestic & International |
| `akasa_air_2026.xlsx` | SNV Aviation (Akasa Air) | Scheduled Domestic |
| `spicejet_2026.xlsx` | SpiceJet | Scheduled Domestic & International |
| `alliance_air_2026.xlsx` | Alliance Air | Regional / Scheduled Domestic |
| `fly91_2026.xlsx` | Just Udo Aviation (Fly91) | Regional Scheduled Domestic |
| `india_one_air_2026.xlsx` | IndiaOne Air | Regional Scheduled Domestic |
| `bluedart_cargo_2026.xlsx` | Blue Dart Aviation | Cargo Scheduled Domestic |
| `quikjet_cargo_2026.xlsx` | Quikjet Cargo | Cargo Scheduled Domestic |
| `star_air_2026.xlsx` | Ghodawat Enterprises (Star Air) | Regional Scheduled Domestic |
| `total_dom_2026.xlsx` | All Domestic Carriers Combined | Total Scheduled Domestic Services |
| `total_int_2026.xlsx` | All International Operations Combined | Total Scheduled International Services |

## What Data These Files Contain
Each file contains monthly sheets reporting:
- **Passengers Carried (PAX)**: Total monthly domestic and international passengers.
- **Aircraft Flown / Hours / Kilometres**: Fleet utilisation metrics.
- **Available Seat Kilometres (ASK) & Passenger Kilometres Performed (RPK)**.
- **Passenger Load Factor (PLF %)**: Efficiency and occupancy rates.

## How APIx Uses This Data
- **Carrier Weighting**: Verifying airline passenger market share (e.g. IndiGo ~60%, Air India ~27%, Akasa ~5%, SpiceJet ~4%) to validate sampling proportions.
- **Capacity & Demand Trends**: Explaining price spikes correlated with passenger load factors (PLF) and capacity fluctuations.
