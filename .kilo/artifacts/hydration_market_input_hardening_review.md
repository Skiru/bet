# Football Hydration, Market Input & Analyzability Hardening Review

**Author**: Kilo (gemini-3.5-flash)  
**Date**: 2026-06-30  
**Task**: HYDRATION_PROMOTION_AND_MARKET_INPUT_HARDENING_A

---

## 1. Questions & Answers

### Q: Which confidence/hydration statuses can become ANALYZABLE?
**A**: Currently, any `probability_confidence` other than `{"BLOCKED", "LOW", "LOW_CONFIDENCE"}` can be promoted to `ANALYZABLE` if statistical averages (length >= 5) are present. This includes `MINIMAL` and `PARTIAL`.
Furthermore, `hydration_status` is not checked or validated within `evaluate_candidate_analyzability()` at all; only the raw presence and length of L10 arrays are checked.

### Q: Can MINIMAL become ANALYZABLE?
**A**: Yes. Under the current `tests/test_football_data_hydration.py` (specifically `test_hydrated_l10_series_unblocks_analyzability`), a candidate with `probability_confidence="MINIMAL"` is explicitly allowed and expected to be unblocked to `ANALYZABLE` if stats are present.

### Q: Can PARTIAL become ANALYZABLE?
**A**: Yes, a candidate with `probability_confidence="PARTIAL"` or `hydration_status="PARTIAL_HYDRATION"` can become `ANALYZABLE` because `"PARTIAL"` is not part of the blocked set `{"BLOCKED", "LOW", "LOW_CONFIDENCE"}` in `evaluate_candidate_analyzability()`, and hydration status is not enforced.

### Q: Can MINIMAL/PARTIAL produce fair_odds/min_acceptable_operator_odds?
**A**: Yes. Once promoted to `ANALYZABLE` and included in the `analytical_ready` list in `build_analytical_candidate_handoff()`, these candidates will have `model_probability` propagated downstream, allowing `fair_odds` and `min_acceptable_operator_odds` to be calculated during daily manual session generation.

### Q: Can MINIMAL/PARTIAL enter manual operator quote review?
**A**: Yes. Since they are promoted to `ANALYZABLE` and placed in the `analytical_ready` candidate pool, they satisfy the conditions to set `ready_for_manual_operator_quote_review=True` in `DailyManualSessionReport`.

### Q: Can a wrong `safety_input.markets` entry be selected when family/line does not match?
**A**: Yes, in `derive_l10_series_for_market_family()`, if no exact line match is found for the specified market family, the function falls back to returning the first market it looped over (`if matching_market is None: matching_market = m`). This results in a mismatch fallback bug where the wrong market series is chosen.

### Q: Are source_provider/source_artifact_path/as_of required before probability input is promotion-safe?
**A**: No. The current validator `validate_market_probability_input()` does not check or enforce the presence of `source_provider`, `source_artifact_path`, `stats_as_of`, or check that they are populated and valid.

### Q: Are real artifacts/logs scanned for secret leakage?
**A**: No. The test `test_api_football_probe_redacts_secret()` currently only asserts that a local helper function `redact_key()` correctly replaces a dummy secret string. It does not scan actual `.kilo/artifacts/*` files, `api_keys.json`, or stdout/stderr log outputs.

---

## 2. Classification of Findings

| ID | Finding Code | Severity | Status / Description |
|---|---|---|---|
| 1 | **P0_PARTIAL_OR_MINIMAL_PROMOTION_BUG** | CRITICAL | **Active**. Candidates with `MINIMAL`/`PARTIAL` confidence or partial hydration can promote to `ANALYZABLE` and enter quote review. |
| 2 | **P0_MARKET_MISMATCH_FALLBACK_BUG** | CRITICAL | **Active**. `derive_l10_series_for_market_family()` falls back to the last iterated market from `safety_input.markets` when family/line match is missing. |
| 3 | **P1_SOURCE_AS_OF_VALIDATION_GAP** | HIGH | **Active**. `validate_market_probability_input()` has no validation checks for `source_provider`, `source_artifact_path`, `as_of`, or hydration statuses. |
| 4 | **P1_SECRET_REDACTION_TEST_GAP** | HIGH | **Active**. Redaction test relies on mock inputs/local helper, missing verification of real generated artifact/log file scanning. |
| 5 | **P2_BACKLOG** | LOW | **None**. No other outstanding items outside the core scope. |
| 6 | **NO_ISSUE** | - | **None**. |
