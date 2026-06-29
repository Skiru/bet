# Analytical Candidate Identity Contract

## Required S4 to S5 Fields

Every candidate handed from shortlist or `S4` into `S5` must carry:

- `candidate_id`
- `event_id` or `fixture_id`
- `sport`
- `competition`
- `participants`
- `start_time`
- `market_family`
- `market_type`
- `pick`
- `line` when the market is totals or handicap shaped
- `odds_decimal` when provider odds exist
- `odds_source` and `odds_as_of` when provider odds exist
- `source_artifact_path`

## Runtime Rules

- If `sport` exists upstream in `S3` or shortlist and is missing in `S4`, classify `SPORT_PROPAGATION_BUG`.
- If `sport` never exists upstream, classify `UPSTREAM_IDENTITY_INCOMPLETE`.
- If `competition` exists upstream and disappears in `S4`, classify `COMPETITION_PROPAGATION_BUG`.
- `S4` must never emit anonymous valuation rows. The replayed `S4` output now keeps `candidate_id`, `event_id`, `sport`, `competition`, and `participants`.
- `S5` must never emit a bare rejection code without traceability. Rejected rows now include `rejection_source_artifact_path` and `rejection_field_path` in `2026-06-29_pre_s7_universe_report.json`.

## Enforcement Points

- `scripts/deep_stats_report.py`
  Seeds `candidate_id`, `participants`, `stats_gap_reason`, and `probability_*` fields into the canonical `S3` JSON.
- `scripts/odds_evaluator.py`
  Preserves `sport`, `competition`, `participants`, `event_id`, `candidate_id`, and explicit probability-gap metadata into `S4` valuation rows.
- `src/bet/pipeline/live_session_universe.py`
  Adds artifact-path and field-path diagnostics on rejected `S4` rows.
- `scripts/pipeline_steps/s5_gate.py`
  Writes `analytical_candidate_handoff.json` and records handoff counts in `S7` evidence.

## Replay Outcome

- Failed smoke symptom: `REJECTED_MISSING_SPORT=8` with no field-path diagnosis.
- Replayed outcome after repair: `S7` reads `S4`, not `S3`; no candidate is rejected solely because `sport` vanished; the single remaining identity issue is an unsupported exact-odds market-family match for `Germany vs Paraguay`.
