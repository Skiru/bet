# L1C1 Live-Validation Wrapper and Artifact Correction Review

**Phase ID:** `FOOTBALL_DATA_FOUNDATION_L1C1_LIVE_VALIDATION_WRAPPER_AND_ARTIFACT_CORRECTION`  
**Audit Date:** 2026-06-20  

This review documents the structural and semantic defects found in the initial live-validation run of the L1 Football Data Foundation layer.

## Source Files Physical Metrics (Pre-Correction)

- **`src/bet/enrichment/football_data_foundation/live_validation.py`**
  - Physical Lines: 820
  - Line Endings: 820 LF, 0 CR
  - Maximum Line Length: 213 (exceeds the 140 character limit)
  - Verdict: Minification/formatting defects (long line lengths)

- **`src/bet/enrichment/football_data_foundation/cli.py`**
  - Physical Lines: 378
  - Line Endings: 378 LF, 0 CR
  - Maximum Line Length: 130
  - Verdict: Structuring and modularity concerns

- **`tests/enrichment/football_data_foundation/test_live_validation.py`**
  - Physical Lines: 44
  - Line Endings: 44 LF, 0 CR
  - Maximum Line Length: 133
  - Verdict: Minified test file (only 44 lines; does not meet the minimum required 120 lines or provide comprehensive coverage)

## Audited Defects

1. **`live_validation.py` is physically minified / not reviewable:**
   - Lines exceed 140 chars. Needs to be properly structured with explicit line lengths and clean, normal formatting.
2. **`cli.py` was modified into a non-reviewable file:**
   - Requires cleaner formatting and normal structure without collapsing existing code.
3. **`test_live_validation.py` is physically minified / not reviewable:**
   - Exceedingly brief (44 lines). Needs a complete set of robust unit tests verifying policy decisions, drift handling, provider mapping, etc., reaching at least 120 lines.
4. **`freshness_results.json` hardcodes `FRESH_FROM_LIVE_PROVIDER`:**
   - Overrides the actual `evaluate_freshness` engine output, masking real stale reasons or live status drift conditions.
5. **`validation_summary.md` hardcodes `STATUS_SCHEDULED`:**
   - Does not query the actual normalized event status_state/status_name, leading to false reporting for non-scheduled matches.
6. **`provider_event_id` derived from `scanner_event_id` string parsing:**
   - Uses `split("-")[-1]` string extraction. A robust, production-grade system must maintain an explicit mapping of `scanner_event_id` -> `provider_event_id` from the candidate creation point onwards.
7. **`provider_scoreboard_snapshot.json` stores `raw_payload_structure`:**
   - Contains raw payload dumps. This must be replaced with an explicit `normalized_provider_event` shape with strictly allowlisted fields.
8. **`validation_manifest.json` does not hash itself or use a sidecar:**
   - Self-hash handling is undocumented. A dedicated sidecar file `validation_manifest.sha256` must be generated to store the manifest's final SHA-256 hash.
