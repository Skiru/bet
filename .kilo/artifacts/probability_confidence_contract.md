# Probability Confidence Contract

## Confidence Levels

| Confidence Level | Definition & Requirements |
|---|---|
| **HIGH** | Complete line, market-specific series of length ≥ 8, no missing fields, valid H2H context, and fresh sources. |
| **MEDIUM** | Complete line, series length ≥ 5, but missing optional H2H/counter-context or older sources. |
| **LOW** | Minimal sample size (length ≥ 5 but sparse) but still valid for modeling. |
| **BLOCKED** | Insufficient sample size (length < 5) or required fields (line/direction) missing. |

## Promotion Guard

- No candidate with **BLOCKED** probability confidence may become analytical-ready.
- Every candidate promoted to **ANALYTICAL_READY** must have confidence of **HIGH**, **MEDIUM**, or **LOW** with a non-null `model_probability` and compliant `supporting_stats`.
