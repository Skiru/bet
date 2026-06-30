# Hydration Runtime Enforcement Review

Reviewed files:
- `src/bet/pipeline/analyzability_prefilter.py`
- `src/bet/pipeline/market_probability_inputs.py`
- `src/bet/pipeline/analytical_candidate_bridge.py`
- `src/bet/pipeline/bet_builder_analytical.py`
- `scripts/pipeline_steps/s8_build_coupons.py`
- `tests/test_football_data_hydration.py`
- `tests/test_analyzability_prefilter.py`
- `tests/test_pipeline_s4_valuation_output_handoff.py`

## Runtime Answers

- Does runtime check `hydration_status == HYDRATED` before `ANALYZABLE`?
  Yes. `validate_market_probability_input()` rejects any non-`HYDRATED` input before allowing `promotion_status == ANALYZABLE`, and `evaluate_candidate_analyzability()` only returns `ANALYZABLE` after validation passes.

- Does runtime block `PARTIAL_HYDRATION` from `ANALYZABLE`?
  Yes. `build_market_probability_input()` maps partial hydration to `REVIEW_ONLY_PARTIAL_DATA`; `validate_market_probability_input()` rejects `hydration_status != HYDRATED`; `analytical_candidate_bridge` keeps `ready_for_manual_operator_quote_review = False`.

- Does runtime block `MINIMAL_HYDRATION` from `ANALYZABLE`?
  Yes. `build_market_probability_input()` maps minimal hydration to `RESEARCH_GAP_MINIMAL_HYDRATION`; validation rejects it before analyzable promotion.

- Does runtime block partial/minimal from fair odds and min acceptable odds?
  Yes. The bridge nulls `model_probability` for all non-analytical candidates, so downstream manual-session logic cannot derive `fair_odds` or `min_acceptable_operator_odds`.

- Does runtime block partial/minimal from manual operator quote review?
  Yes. The bridge marks those candidates `ready_for_manual_operator_quote_review = False`, `s8_build_coupons.py` filters quote-ready selections to `HYDRATED + ANALYZABLE + promotion_safe_model_probability`, and downstream session/package reports re-check the same provenance.

- Does runtime require `source_provider`, `source_artifact_path`, `stats_as_of`/`as_of_utc`?
  Yes. `validate_market_probability_input()` hard-fails on missing provider, artifact path, or unknown/missing timestamp.

- Does runtime reject `UNKNOWN` `as_of`?
  Yes. `_has_known_as_of()` treats empty/`UNKNOWN` values as invalid, and validation returns `STATS_AS_OF_MISSING_OR_UNKNOWN`.

- Does market series matching require exact family + direction + line?
  Yes for line-required families. `derive_l10_series_for_market_family()` now matches by extracted market semantics, artifact path, exact family, compatible direction, and line tolerance.

- Is there any fallback to last/first market when no exact match?
  No. The market-series resolver now returns `MARKET_SERIES_NOT_FOUND_FOR_FAMILY_LINE` when no exact compatible match exists and `AMBIGUOUS_MARKET_SERIES_MATCH` when multiple matches remain unresolved.

- Are real artifacts/logs scanned for raw API key values?
  Yes. `tests/_secret_artifact_scan.py` loads raw local secret values only in test runtime and `test_secret_values_not_present_in_real_artifacts` scans `.kilo/artifacts`, `reports`, and `/tmp` logs/artifacts for raw secret leakage.

## Classification

- `RUNTIME_CONTRACT_ENFORCEMENT`: `RUNTIME_CONTRACT_ENFORCED`
- `PARTIAL_PROMOTION`: `PARTIAL_PROMOTION_RUNTIME_BLOCKED`
- `MINIMAL_PROMOTION`: `MINIMAL_PROMOTION_RUNTIME_BLOCKED`
- `MARKET_SERIES_MATCHING`: `MARKET_MISMATCH_RUNTIME_BUG_RESOLVED`
- `SOURCE_AS_OF`: `SOURCE_AS_OF_RUNTIME_GAP_RESOLVED`
- `SECRET_SCAN`: `SECRET_ARTIFACT_SCAN_GAP_RESOLVED`

## Proof Points

- `tests/test_football_data_hydration.py::test_runtime_requires_hydrated_status_for_analyzable`
- `tests/test_football_data_hydration.py::test_runtime_blocks_partial_hydration_from_analyzable`
- `tests/test_football_data_hydration.py::test_runtime_blocks_minimal_hydration_from_analyzable`
- `tests/test_football_data_hydration.py::test_market_probability_input_requires_source_provider_source_artifact_and_as_of`
- `tests/test_football_data_hydration.py::test_market_probability_input_rejects_unknown_as_of`
- `tests/test_football_data_hydration.py::test_market_series_no_exact_match_returns_gap_not_fallback`
- `tests/test_football_data_hydration.py::test_market_series_ambiguous_match_blocks`
- `tests/test_pipeline_s4_valuation_output_handoff.py::test_s8_review_only_package_not_quote_ready`
- `tests/test_football_data_hydration.py::test_secret_values_not_present_in_real_artifacts`
