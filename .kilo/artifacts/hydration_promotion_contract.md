# Hydration Promotion Contract

This contract defines the strict state transitions and rules for promoting hydrated football statistical data into the `ANALYZABLE` promotion status. It guarantees that any candidate marked as `ANALYZABLE` is built only from the exact matching market semantics and sufficiently trusted hydrated stats, preventing partial/minimal data from silently propagating into production.

---

## 1. Hydration & Promotion Statuses

### HydrationStatus
* **`HYDRATED`**: Both teams have complete statistical data, fully matched, with sufficient sample size.
* **`PARTIAL_HYDRATION`**: Some statistical data is available but sample size is limited or one team has incomplete records.
* **`MINIMAL_HYDRATION`**: Bare minimum statistical references are available.
* **`HYDRATION_FAILED`**: Stat collection run completed but failed to produce any useable results.
* **`DATA_UNAVAILABLE`**: No data was found or provider client timed out.

### PromotionStatus
* **`ANALYZABLE`**: Promotion-safe status. Fully hydrated, validated, exact market semantics match, and eligible for fair odds, min acceptable operator odds, and manual quote review.
* **`REVIEW_ONLY_PARTIAL_DATA`**: High-risk partial data. Kept in review/research sections only.
* **`RESEARCH_GAP_PARTIAL_HYDRATION`**: Research gap state for partially hydrated candidates.
* **`RESEARCH_GAP_MINIMAL_HYDRATION`**: Research gap state for minimally hydrated candidates.
* **`BLOCKED_HYDRATION_FAILED`**: Blocked from downstream processing due to hydration failure or missing vital fields.

---

## 2. Core Transition & Promotion Rules

### Promotion to `ANALYZABLE`
A candidate with `hydration_status="HYDRATED"` may be promoted to `PromotionStatus="ANALYZABLE"` if and only if all of the following conditions are met:
1. **Exact Market Semantics Match**: No fallback-derived or ambiguous markets are allowed.
2. **Line & Direction Valid**: Line and direction must be present where required.
3. **L10 Series Valid**: L10 series contains valid numeric entries for both teams.
4. **Sample Size Valid**: Minimum sample size of 5 matches per team.
5. **Stat Semantics Status Known**: Statistical semantics (split policy, aggregation keys) must be fully mapped and valid.
6. **Traceability Fields Present**:
   * `source_provider` must be present.
   * `source_artifact_path` must be present.
   * `stats_as_of` / `as_of_utc` must be present and not equal to `"UNKNOWN"`.
7. **Probability Confidence Safe**:
   * Must **not** be in `{"BLOCKED", "LOW", "MINIMAL", "PARTIAL", "LOW_CONFIDENCE"}`.

### High-Risk Transitions
* Any candidate with `hydration_status="PARTIAL_HYDRATION"` may become **only** `REVIEW_ONLY_PARTIAL_DATA`.
* Any candidate with `hydration_status="MINIMAL_HYDRATION"` may become **only** `RESEARCH_GAP_MINIMAL_HYDRATION`.
* Any other hydration status or unknown status must fail closed and map to `BLOCKED_HYDRATION_FAILED`.

### Downstream Restraints for `PARTIAL` and `MINIMAL`
Candidates with `PARTIAL_HYDRATION` or `MINIMAL_HYDRATION` are strictly prevented from:
* Generating `fair_odds` or `min_acceptable_operator_odds` (they must remain null/unset).
* Being marked as `READY_FOR_MANUAL_OPERATOR_QUOTE_REVIEW = true`.
* Contributing to `ANALYTICAL_SUGGESTION_COUNT > 0`.
* Being selected as `BETTABLE_MANUAL_ONLY`.

---

## 3. Failure Behavior
If any required contract field (`source_provider`, `source_artifact_path`, `stats_as_of`) is missing or invalid, the candidate must fail closed, downgrading to a blocked/research status.
