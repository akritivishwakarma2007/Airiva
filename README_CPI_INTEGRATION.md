# Using the MoSPI CPI Airfare dataset in APIx

Source to cite everywhere it appears: **MoSPI, eSankhyiki** (check the portal's data-use notice before publishing).

## What the dataset is (and isn't)
| Has | Doesn't have |
|---|---|
| Official airfare CPI, item 07.3.3.1.2.01, base 2024=100 | Route, airline, or advance-purchase detail |
| Monthly, Jan 2025 - Aug 2026; All India + 34 states/UTs; Rural/Urban/Combined | Item weights |
| YoY inflation (from Jan 2026), imputation flag (68 of 1,880 rows) | Daily data |

So it is a **benchmark and context layer**. It does not replace scraping or the DGCA traffic weights.

## Where it plugs in
1. **Backtest benchmark** (main use): APIx monthly index vs All India / Combined, non-imputed rows.
2. **Dashboard overlay**: official monthly line next to the daily APIx line.
3. **Demo realism**: calibrate seed data to the official series (about +20% YoY drift, +-10% monthly swings).
4. **Regional context** (optional): official state index for NCT of Delhi / Maharashtra / Karnataka. Context only, state values are too noisy to validate against.
5. **Data-quality practice**: mirror MoSPI's imputation flag in the APIx pipeline.

## Implementation steps
1. Put `cpi_1413.xlsx` in `data/cpi/`.
2. `python scripts/load_cpi_official.py --xlsx data/cpi/cpi_1413.xlsx --dry-run` writes `data/cpi/cpi_airfare_clean.csv`.
3. **[Manual]** Run `supabase/migrations/002_cpi_official.sql` in Supabase SQL Editor.
4. Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`, run the loader again without `--dry-run` to upsert.
5. Export APIx monthly composite values (`date, index_value`) and run
   `python -m apix.backtest.cpi_benchmark --cpi-csv data/cpi/cpi_airfare_clean.csv --apix-csv monthly_apix.csv`
   It writes `data/benchmark/cpi_benchmark.json`.
   Use `--demo` first to check the code path (synthetic series, not a result).
6. Add the overlay to the dashboard (below), serve the JSON as a static file or from a FastAPI route.
7. Backtest page and docs: report `status`, direction agreement, rebased error, and correlation only when the module returns one.

## Honest limits to state in the submission
- Bases differ, so compare month-over-month change and rebased levels, never raw levels.
- Fewer than 3 overlapping months: no direction claim. Fewer than 7: no correlation. The module says so instead of printing a number.
- About 30 days of scraping yields one monthly point. Keep collecting monthly to build the comparison.
- The official series is itself noisy month to month, which supports the case for a daily index.

## Dashboard overlay (Chart.js, second axis)
```js
const b = await (await fetch('/data/benchmark/cpi_benchmark.json')).json();
trendChart.data.datasets.push({
  label: b.meta.cpi_label,
  data: b.cpi.map(r => ({ x: r.month + '-15', y: r.index })),
  yAxisID: 'yCpi', borderColor: '#5B6B85', borderDash: [6, 4],
  pointRadius: 3, stepped: true
});
trendChart.options.scales.yCpi = {
  position: 'right', grid: { drawOnChartArea: false },
  title: { display: true, text: 'MoSPI CPI (2024=100)' }
};
trendChart.update();
```
(Use a time x-axis, e.g. the Chart.js date adapter, or map months to your existing labels.)
Show a small caption under the chart: "Official series is monthly; APIx is daily."

## Route-to-state map for the regional view
DEL -> NCT of Delhi, BOM/PNQ -> Maharashtra, BLR -> Karnataka, CCU -> West Bengal, MAA -> Tamil Nadu, HYD -> Telangana, AMD -> Gujarat, GOI -> Goa, COK -> Kerala.
