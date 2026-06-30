# PRE_S7_TO_S7 E2E Wiring Audit

## Classification

`METRIC_CONTEXT_MIXED`

Reason: the previously reported `PRE_S7_VALID_COUNT=427` and `S7_INPUT_COUNT=2` do not come from the same artifact root.

- `427` comes from the repo-local expanded-retry S1 artifact:
  `reports/pipeline_runs/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/pipeline_runs/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/artifacts/S1.json`
- `2` comes from the bad-session replay S7 artifact:
  `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/pipeline_runs/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/artifacts/S7.json`

The new clean smoke root below shows same-root pre-S7 and S7 traceability via persisted `pre_s7_universe_report_path`, `pre_s7_valid_count`, `s7_input_count`, and explicit `s7_selection_policy`.

## Trace Table

| Context | run_id | artifact_root | S1 raw discovery artifact + count | market matrix artifact + count | shortlist artifact + count | S3 stats artifact + count | S4 valuation artifact + count | pre-S7 universe report + valid_count | S7 input path + candidate_count | S7 output path + approved_count |
|---|---|---|---|---|---|---|---|---|---|---|
| `BAD_SESSION_REPLAY` | `TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A` | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A` | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/pipeline_runs/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/artifacts/S1.json` -> raw discovery count unavailable in this artifact revision | `/private/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/market_matrix_2026-06-28.json` -> `2` | `/private/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/2026-06-28_s2_shortlist.json` -> `2` | `/private/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/2026-06-28_s3_deep_stats.json` -> `2` | `/private/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/2026-06-28_s4_valuation_candidates.json` -> `2` | not emitted in this older run root | `/private/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/2026-06-28_s4_valuation_candidates.json` -> `2` | `/private/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/2026-06-28_s7_gate_results.json` -> `0` |
| `EXPANDED_RETRY` | `TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A` | `reports/pipeline_runs/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A` | `reports/pipeline_runs/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/pipeline_runs/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/artifacts/S1.json` -> `427` | path empty in `S1.json` payload -> `0` | not produced | not produced | not produced | not produced | not produced | not produced |
| `E2E_S7` | `PRE_S7_TO_S7_E2E_WIRING_SMOKE_A` | `/tmp/pre_s7_to_s7_e2e_wiring_smoke/2026-06-28/PRE_S7_TO_S7_E2E_WIRING_SMOKE_A` | `/tmp/pre_s7_to_s7_e2e_wiring_smoke/2026-06-28/PRE_S7_TO_S7_E2E_WIRING_SMOKE_A/pipeline_runs/2026-06-28/PRE_S7_TO_S7_E2E_WIRING_SMOKE_A/artifacts/S1.json` -> `427` | `/tmp/pre_s7_to_s7_e2e_wiring_smoke/2026-06-28/PRE_S7_TO_S7_E2E_WIRING_SMOKE_A/data/market_matrix_2026-06-28.json` -> `339` | `/tmp/pre_s7_to_s7_e2e_wiring_smoke/2026-06-28/PRE_S7_TO_S7_E2E_WIRING_SMOKE_A/data/2026-06-28_s2_shortlist.json` -> `122` | `/tmp/pre_s7_to_s7_e2e_wiring_smoke/2026-06-28/PRE_S7_TO_S7_E2E_WIRING_SMOKE_A/data/2026-06-28_s3_deep_stats.json` -> `122` | `/tmp/pre_s7_to_s7_e2e_wiring_smoke/2026-06-28/PRE_S7_TO_S7_E2E_WIRING_SMOKE_A/data/2026-06-28_s4_valuation_candidates.json` -> `122` | `/tmp/pre_s7_to_s7_e2e_wiring_smoke/2026-06-28/PRE_S7_TO_S7_E2E_WIRING_SMOKE_A/data/2026-06-28_pre_s7_universe_report.json` -> `0` | `/private/tmp/pre_s7_to_s7_e2e_wiring_smoke/2026-06-28/PRE_S7_TO_S7_E2E_WIRING_SMOKE_A/data/2026-06-28_s4_valuation_candidates.json` -> `0` | `/tmp/pre_s7_to_s7_e2e_wiring_smoke/2026-06-28/PRE_S7_TO_S7_E2E_WIRING_SMOKE_A/data/2026-06-28_s7_gate_results.json` not created because universe blocked before gate checker -> `0` |

## Verdict

- Mixed report root cause confirmed: expanded-retry discovery metrics were compared against bad-session replay S7 metrics.
- Same-root traceability is now persisted in S7 evidence.
- Clean smoke verdict shape is `C`:
  - `UNIVERSE_VERDICT=BLOCKED_INSUFFICIENT_CANDIDATE_UNIVERSE`
  - `S7_NOT_RUN_REASON=universe_not_ready`
  - `E2E_WIRING_VERDICT=PASS`
