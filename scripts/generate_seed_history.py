"""
generate_seed_history.py — Generate 60 days of calibrated daily flight fare quotes.

Covers the full 30-route × 5-source × 5-window APIx basket:
- Routes: All 30 DGCA high-density corridors
- Airlines: IndiGo (6E), Air India (AI), MakeMyTrip (OTA), Akasa Air (QP), SpiceJet (SG)
- Windows: T+1, T+7, T+15, T+30, T+45
- Realistic dynamic pricing dynamics:
  - T+1 emergency surge vs T+45 early bird discounts
  - Weekend departure surcharge (Fri/Sun)
  - Seasonal inflation drift
  - Airline tariff bands
"""
import random
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

random.seed(42)

ROUTES = [
    ("DEL", "BOM", 5400.0), ("DEL", "BLR", 5100.0), ("BOM", "BLR", 4700.0),
    ("DEL", "HYD", 4900.0), ("DEL", "PNQ", 4750.0), ("DEL", "CCU", 4820.0),
    ("BOM", "GOI", 3900.0), ("DEL", "AMD", 4350.0), ("DEL", "GOI", 4500.0),
    ("BLR", "HYD", 3600.0), ("DEL", "MAA", 4950.0), ("BOM", "CCU", 4650.0),
    ("BOM", "HYD", 4150.0), ("BOM", "MAA", 4050.0), ("BLR", "CCU", 4580.0),
    ("BOM", "AMD", 3450.0), ("BLR", "PNQ", 3520.0), ("DEL", "SXR", 5650.0),
    ("DEL", "PAT", 4420.0), ("DEL", "GAU", 4650.0), ("BLR", "GOI", 3750.0),
    ("BLR", "MAA", 3380.0), ("HYD", "MAA", 3230.0), ("BLR", "COK", 3450.0),
    ("DEL", "LKO", 3900.0), ("HYD", "GOI", 3670.0), ("BOM", "COK", 3970.0),
    ("DEL", "BBI", 4360.0), ("DEL", "IXB", 4280.0), ("BLR", "AMD", 3820.0),
]

CARRIERS = [
    ("6E", "indigo", ["SAVER", "FLEX", "SUPER_SAVER"]),
    ("AI", "air_india", ["ECONOMY", "FLEX_ECONOMY"]),
    ("6E", "makemytrip", ["SAVER", "SPECIAL"]),
    ("QP", "akasa", ["SAVER", "FLEXI"]),
    ("SG", "spicejet", ["SPICESAVER", "SPICEMAX"]),
]

WINDOWS = [1, 7, 15, 30, 45]

WIN_MULTS = {
    1: 1.42,
    7: 1.15,
    15: 1.02,
    30: 0.90,
    45: 0.82,
}

CARRIER_MULTS = {
    "AI": 1.05,
    "6E": 0.99,
    "QP": 0.95,
    "SG": 0.96,
}


def generate_quotes(days_back: int = 60) -> pd.DataFrame:
    records = []
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)

    # Market trend random walk
    market_trend = 1.0

    current = start_date
    while current <= end_date:
        # Market level drifts slightly per day (+-0.4%)
        market_trend += random.uniform(-0.005, 0.006)
        market_trend = max(0.92, min(1.15, market_trend))

        for orig, dest, base_route_fare in ROUTES:
            for carrier, source, fare_classes in CARRIERS:
                f_num = f"{carrier}-{random.randint(100, 999)}"
                for win in WINDOWS:
                    travel_date = current + timedelta(days=win)
                    is_weekend = travel_date.weekday() in (4, 6)

                    win_mult = WIN_MULTS.get(win, 1.0)
                    weekend_mult = 1.07 if is_weekend else 1.0
                    carrier_mult = CARRIER_MULTS.get(carrier, 1.0)

                    price_noise = random.uniform(0.97, 1.03)
                    total = round(base_route_fare * market_trend * win_mult * weekend_mult * carrier_mult * price_noise, 2)
                    base = round(total * 0.82, 2)
                    tax = round(total - base, 2)

                    records.append({
                        "origin": orig,
                        "destination": dest,
                        "carrier": carrier,
                        "flight_number": f_num,
                        "scrape_date": current.isoformat(),
                        "travel_date": travel_date.isoformat(),
                        "advance_purchase_days": win,
                        "fare_class": random.choice(fare_classes),
                        "base_fare": base,
                        "taxes_fees": tax,
                        "total_fare": total,
                        "seats_available": random.randint(1, 9),
                        "source": source,
                    })
        current += timedelta(days=1)

    return pd.DataFrame(records)


if __name__ == "__main__":
    out_csv = Path("data/seed/synthetic_fares.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df = generate_quotes(60)
    df.to_csv(out_csv, index=False)
    print(f"Generated {len(df)} historical fare records spanning {df['scrape_date'].min()} to {df['scrape_date'].max()} -> {out_csv}")
