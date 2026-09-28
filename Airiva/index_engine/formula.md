# Index Formula: Törnqvist Price Index

## Why Törnqvist over Fisher Ideal?

The APIx uses the **Törnqvist price index** rather than the Fisher Ideal index.
Both are "superlative" indices that correct for substitution bias inherent in
fixed-basket (Laspeyres) approaches, but Törnqvist is preferred here for three
specific reasons:

---

### 1. Sparse daily samples make Paasche estimation unreliable

The Fisher Ideal index is defined as:

```
P_Fisher = sqrt(P_Laspeyres × P_Paasche)
```

The **Paasche** sub-index requires current-period *quantity* (or expenditure)
weights. In our pilot — 3 routes × 2 windows × ≤3 sources = at most ~18 records
per day — the current-period expenditure shares estimated from a single day's
sample are noisy. Averaging base- and current-period shares (as Törnqvist does)
dampens this day-to-day noise without requiring reliable quantity data for each
individual period.

### 2. Log-change form is additively decomposable

The Törnqvist formula in discrete log-change form:

```
ln(P_t / P_0) = Σ_i [ (s_i,0 + s_i,t) / 2  ×  ln(p_i,t / p_i,0) ]
```

is directly additive: each route contributes a weighted log price change.
This makes it trivial to:
- Decompose the composite index into route-level contributions
- Chain periods together without accumulating rounding error
- Compute weekly/monthly values as geometric means of daily log changes

The Fisher index does not have this clean additive decomposition.

### 3. Methodological precedent — BLS Air Travel Price Index

The US Bureau of Labor Statistics (BLS) uses a **Modified Laspeyres** approach
for its CPI but explicitly recommends Törnqvist for transaction-based travel
price indices where expenditure data (not quantity counts) are available.
The BTS Air Travel Price Index (ATPI), which this project is modelled on,
uses a Laspeyres framework at the quarterly level; Törnqvist has been shown
to produce numerically very similar results while requiring less assumption
about quantity stability.

---

## Formula Implementation

```python
# Period t vs. base period 0
ln_ratio = sum(
    ((s_i_base + s_i_curr) / 2) * math.log(p_i_curr / p_i_base)
    for i in common_routes
)
index_value = math.exp(ln_ratio) * 100   # base period = 100
```

Where:
- `p_i` = **median** of `total_fare` for route `i` on that day
  (median is robust to the residual fat tail after IQR filtering)
- `s_i` = route expenditure share = `w_i × p_i / Σ_j(w_j × p_j)`
- `w_i` = DGCA passenger traffic weight for route `i`

---

## Base Period

The base period is the **first complete collection week** (7 calendar days
after the first successful scrape run). During the base week, `index_value = 100`
by definition.

---

## References

- Diewert, W.E. (1976). "Exact and Superlative Index Numbers." *Journal of
  Econometrics*, 4(2), 115–145.
- BLS Handbook of Methods, Chapter 17: "The Consumer Price Index."
- Bratu, M. (2012). "Comparative Study of Alternative Methods for Price
  Indices Calculation." *Economic Computation and Economic Cybernetics
  Studies and Research*, 46(3).
- BTS Air Travel Price Index (ATPI) methodology note, 2003.
