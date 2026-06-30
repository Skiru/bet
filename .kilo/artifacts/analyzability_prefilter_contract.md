# Analyzability Prefilter Contract

This contract defines the schema, rules, and statuses for evaluating the analyzability of S4 valuation candidates before prioritizing them for analytical smoke selection.

## AnalyzabilityReport Schema

An `AnalyzabilityReport` contains the following fields:

* **candidate_id**: Unique string identifier for the candidate.
* **sport**: Sport name (e.g. `football`).
* **market_family**: Mapped market family (e.g. `RESULT`, `GOALS_TOTALS`, `CORNERS`, `CARDS`, `SHOTS`, `SHOTS_ON_TARGET`).
* **market_type**: Original provider/operator market type.
* **line**: Numeric line for totals/handicaps, or `None`.
* **direction**: Pick direction (e.g. `OVER`, `UNDER`, `home`, `away`, `draw`, or empty).
* **stats_seed_status**: Freshness and completeness status of team/h2h stats seed (`true` or `false`).
* **l10_series_status**: Freshness and completeness status of L10 historical form series (`true` or `false`).
* **stat_semantics_status**: Mapped split/aggregation semantic status (`true` or `false`).
* **market_probability_input_status**: Status of deriving the market-specific probability input (`true` or `false`).
* **analyzability_score**: Computed priority score (0.0 to 1.0) based on metrics readiness.
* **analyzability_status**: String status indicating eligibility or exact type of research gap/blocker.
* **blocker_reasons**: List of exact blocker codes (e.g., `UNSUPPORTED_SPORT`, `STATS_SEED_MISSING`, `LINE_MISSING`, `DIRECTION_MISSING`, `L10_SERIES_MISSING`, `UNKNOWN_SPLIT_STAT_SEMANTICS`).
* **source_artifact_path**: File system path to the source JSON artifact.
* **field_path**: Internal dot-notation path inside the source JSON artifact.

---

## Status Definitions

The `analyzability_status` of any candidate must be one of the following:

* **ANALYZABLE**: Fully eligible for analytical evaluation and model probability computation.
* **RESEARCH_GAP_STATS_MISSING**: Blocked because team/h2h stats seed is missing from DB and cache.
* **RESEARCH_GAP_L10_MISSING**: Blocked because historical form matches (L10 series) are missing or insufficient.
* **RESEARCH_GAP_UNKNOWN_STAT_SEMANTICS**: Blocked because split/aggregation keys have unknown stats semantics.
* **RESEARCH_GAP_MARKET_INPUT_NOT_BUILT**: Blocked because the market probability input builder failed to construct an input.
* **UNSUPPORTED_MARKET_FAMILY**: Blocked because the market family is unsupported by the analytical engine (e.g., player props).
* **IDENTITY_GAP**: Blocked because team names cannot be canonicalized or resolved.
* **LINE_OR_DIRECTION_GAP**: Blocked because a line or direction is required but missing or malformed.

---

## Rules of Execution

1. **Analytical Smoke Selection Rule**: Only candidates with `analyzability_status = "ANALYZABLE"` can be prioritized for analytical smoke selection.
2. **Honest Gaps Permitted**: Gaps are honest representations of data incompleteness. Under no circumstances may fake or dummy statistics, probabilities, or coordinates be generated to force a candidate to become `ANALYZABLE`.
3. **Traceability Rule**: Every generated analyzability record must preserve the `source_artifact_path` and `field_path` of its inputs for end-to-end debugging and auditing.
4. **Unsupported Markets Block Rule**: Unsupported markets (e.g., player props) must remain strictly blocked and must never be promoted to `ANALYZABLE`.
