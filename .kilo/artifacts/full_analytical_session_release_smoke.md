# Full Analytical Session Release Smoke

- task_id: `PRE_MERGE_MODEL_PROBABILITY_CODE_REVIEW_AND_SMOKE_A`
- betting_day: `2026-06-29`
- runtime_mode: `LIVE_SHADOW`
- sandbox: `/private/tmp/premerge_probability_release_smoke_a`
- result: `RESEARCH_GAP_PACKAGE`

## Summary

- `S1` PASS with real live-shadow discovery.
- `S3` PASS technically, but only `2/29` shortlist entries had stats-ready data.
- `S4` PASS technically, but `28/29` valuation rows still had `ev_missing_reason=MISSING_PROBABILITY`.
- `S7` BLOCK with `BLOCKED_INSUFFICIENT_CANDIDATE_UNIVERSE`.
- `S8` PASS fail-closed by emitting `RESEARCH_GAP_PACKAGE`, not a false-ready analytical package.

## Required Counts

- `S1 discovery count`: `89`
- `market matrix count`: `80`
- `shortlist count`: `29`
- `stats ready count`: `2`
- `market probability input ready count`: `0`
- `model probability ready count`: `1`
- `analytical suggestion count`: `0`
- `package type`: `RESEARCH_GAP_PACKAGE`

## Exact Drop Reasons

- market-probability-input stage: `29` dropped with `MARKET_SPECIFIC_INPUT_NOT_BUILT`
- analytical handoff probability stage: `11` dropped with `NO_STATS_DATA_FOR_MODEL_PROBABILITY`
- analytical handoff identity stage: `18` dropped with `MISSING_MARKET_FAMILY`
- pre-S7 priced universe: `28` rejected as `REJECTED_MISSING_MARKET`, `1` rejected as `REJECTED_MISSING_TIMESTAMP`

## Acceptance Check

- `ANALYTICAL_ONLY` package with operator quote checklist: `not produced`
- `RESEARCH_GAP_PACKAGE` with exact non-fake reasons: `produced`
- unclear `NO_BET_PACKAGE` despite upstream candidates: `not produced`

## Evidence Paths

- `S1`: `/private/tmp/premerge_probability_release_smoke_a/pipeline_runs/2026-06-29/PRE_MERGE_MODEL_PROBABILITY_CODE_REVIEW_AND_SMOKE_A/artifacts/S1.json`
- `S3`: `/private/tmp/premerge_probability_release_smoke_a/artifacts/S3.json`
- `S4`: `/private/tmp/premerge_probability_release_smoke_a/artifacts/S4.json`
- `S7`: `/private/tmp/premerge_probability_release_smoke_a/artifacts/S7.json`
- `S8`: `/private/tmp/premerge_probability_release_smoke_a/artifacts/S8.json`
- `handoff`: `/private/tmp/premerge_probability_release_smoke_a/data/analytical_candidate_handoff.json`
- `package`: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s8_coupon_drafts.json`
