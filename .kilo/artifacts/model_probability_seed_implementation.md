# Model Probability Seed Implementation Document

## 1. Allowed Probability Methods

To ensure all analytical calculations are rooted strictly in factual historical statistics rather than heuristics or bookmaker bias, our Probability Engine supports exactly three methodologies:

* **`S3_TEAM_FORM_CONTEXTUAL_PROXY` (Primary Model):**
  * Computes the joint Poisson Probability Mass Function (PMF) and Cumulative Distribution Function (CDF) using Team A and Team B's historical averages over the last 10 games.
  * Used for team-level statistical markets (Goals, Corners, Cards, Shots) and Match Winner (RESULT) joint goals distribution matrix.
* **`S3_HIT_RATE_PROXY` (Fallback Model):**
  * Proxies probability from the actual observed historical hit rates over the L10 matches and H2H matches: `(hit_rate_l10 + hit_rate_h2h) / 2`.
* **`S3_MARKET_FAMILY_BASELINE` (Alternative Model):**
  * Uses baseline statistical distributions for markets with limited sample sizes or higher variances.

---

## 2. Forbidden Operations

* **NO Bookmaker Implied Probability:** Implied probability (derived from bookmaker odds) must **never** be used as the model probability. It can only be kept as a reference-only value (`BOOKMAKER_IMPLIED_REFERENCE_ONLY`).
* **NO Hardcoded Probabilities:** A static or arbitrary percentage is strictly forbidden.
* **NO Fake Probabilities for Testing:** Test cases must use deterministic mock stats inputs to compute mock probabilities organically rather than hardcoding fake final values.

---

## 3. Output Fields

| Field Name | Type | Description |
|---|---|---|
| `model_probability` | `Decimal \| None` | The calculated model probability, or `None` if stats are missing. |
| `probability_method` | `str` | The method used: `S3_TEAM_FORM_CONTEXTUAL_PROXY` or `S3_HIT_RATE_PROXY`. |
| `probability_sources` | `list[str]` | The specific historical sources (e.g., `["stats_db"]`). |
| `probability_as_of` | `str` | ISO 8601 timestamp of calculation. |
| `probability_confidence` | `str` | Confidence tier: `FULL`, `PARTIAL`, or `MINIMAL`. |
| `probability_missing_reason` | `str \| None` | Exact missing reason: `NO_STATS_DATA_FOR_MODEL_PROBABILITY`. |

---

## 4. No Stats / Missing Behavior

If either `stats_a` or `stats_b` has `has_data = False`, the engine must output:
* `model_probability = null`
* `probability_missing_reason = "NO_STATS_DATA_FOR_MODEL_PROBABILITY"`
