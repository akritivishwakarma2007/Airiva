# APIx Backtest Data Directory
================================================================================
Place DGCA monthly route-wise fare / traffic reports here for backtest correlation.

1. What goes in this folder:
   - DGCA Monthly City-Pair Fare Reports (PDF or CSV).
   - These reports must contain Route / City-Pair data (DEL-BOM, DEL-BLR, BOM-BLR)
     with Average Fare (INR) and/or Route Passenger Counts.

2. Source on dgca.gov.in:
   dgca.gov.in -> Data & Reports -> Civil Aviation Statistics Handbook
               -> Domestic Air Transport -> Monthly Statistics
               -> Statement showing Route-wise traffic and average fares

3. Recommended naming convention:
   - PDF format:  dgca_monthly_YYYY_MM.pdf   (e.g., dgca_monthly_2024_03.pdf)
   - CSV format:  dgca_fares_YYYY_MM.csv    (e.g., dgca_fares_2024_03.csv)

4. Note on Airline Form A Statistics (e.g. indigo26.xlsx, Air India26.xlsx):
   - Carrier-level Form A statistics (total monthly passengers, load factors)
     are placed in `data/dgca_traffic_2026/`.
   - Backtesting specifically looks for City-Pair average fares (INR).
================================================================================
