# Live Session Candidate Universe — Runbook
Date: 2026-06-28

## Purpose
The Live Session Candidate Universe Gate serves as a pre-S7 quality control step in the automated betting pipeline. It ensures that the candidate pool delivered to the Hard Approval Gate (S7) is fresh, complete, sufficiently populated, and has valid metadata. This stops garbage inputs or stale data from causing silent session failures (e.g. false `NO_BET` outcomes when there are simply no viable current matches).

## Key Components

### 1. Module location
`src/bet/pipeline/live_session_universe.py`

### 2. Core Class Definitions
- `LiveSessionUniverseConfig`: Holds runtime validation parameters such as `min_candidates`, `stale_threshold_seconds`, and `provider_universe_exhausted`.
- `CandidateInput` / `CandidateUniverseInput`: Models individual candidate selections.
- `SourceGap`: Represents a missing upstream analytical data vector (e.g. tipsters, injuries, H2H).
- `UniverseQualityReport` / `CandidateUniverseReport`: Synthesizes validation outcomes.

### 3. Core Function API
- `classify_candidate_quality(candidate, config)`: Evaluates a candidate against quality and freshness checks.
- `build_pre_s7_universe(raw_candidates, config)`: Validates the entire candidate pool.
- `validate_candidate_sufficiency(valid_count, config)`: Applies the sufficiency/exhaustion check.

## Operational Scenarios & Troubleshooting

### Scenario A: `BLOCKED_INSUFFICIENT_CANDIDATE_UNIVERSE`
- **Symptom**: Pipeline blocks with status `BLOCKED_INSUFFICIENT_CANDIDATE_UNIVERSE` (fewer than 8 valid pre-S7 candidates resolved).
- **Reason**: The upstream discovery steps failed, fell back to stale/completed cache entries, or simply returned too few events.
- **Remediation**:
  1. Inspect the S1 discovery logs under `reports/pipeline_runs/<date>/<run_id>/logs/S1_stdout.log` to check if a crawler/scraper crashed.
  2. If a database migration or connection error occurred, run `pytest tests/test_db_data_loader.py` to diagnose.
  3. Re-run with broader discovery options or update the fixtures database.

### Scenario B: `BLOCKED_PROVIDER_UNIVERSE_EXHAUSTED`
- **Symptom**: Fewer than 8 valid pre-S7 candidates, but the `provider_universe_exhausted` option is set to true.
- **Reason**: All available providers have been scraped, but the current daily fixture landscape is naturally sparse.
- **Remediation**: This is a valid, clean block. No human action is required; the system safely halts without placing un-analyzed bets.

## Standard Verification Commands
To compile and test the module:
```fish
.venv/bin/python3 -m compileall src/bet/pipeline/live_session_universe.py scripts/pipeline_live_session_universe.py tests/test_pipeline_live_session_universe.py
.venv/bin/python3 -m pytest -v tests/test_pipeline_live_session_universe.py
```
