# Live Handoff Smoke Test Report

## 1. Summary
The live dry-run of the certified shadow source `zawodtyper` was executed successfully on **2026-07-06** using:
- **Command:** `scripts/pipeline_steps/s2_tipsters_v2_live_dry_run.py --source zawodtyper`
- **Reviewed JSON:** `docs/pipeline/tipster_terms_review.local.json`

## 2. Key Metrics
- **Total Picks Extracted:** 25
- **Consensus Groups Created:** 20
- **SQLite Database Path:** `/tmp/zawodtyper_orchestrator_handoff.sqlite`
- **Picks Persisted in SQLite:** 25
- **Consensus Persisted in SQLite:** 20
- **Handoff File Location:** `reports/pipeline_runs/TIPSTER_ORCHESTRATOR_HANDOFF_AND_SOURCE_RESCUE_20260706T072647Z/live_handoff_smoke/zawodtyper_handoff.json`

## 3. Schema & Validation Checks
- **`agent_readiness` presence:** Yes (all 25 picks have a fully populated `agent_readiness` field).
- **`agent_readiness_summary` presence:** Yes (every consensus row has aggregated counts and a list of decisions).
- **Handoff Artifact Schema:** Valid (matches `tipster_evidence_handoff_v1` specification).
- **Allowed Consumers:** Restrictive (limited exclusively to `S3 contextual cross-check`, `S4 market sanity`, and `manual Superbet quote review`).
- **Forbidden Actions Enforcement:** PASS (no picks or handoff events contain any keys corresponding to `EV`, `stake`, `coupon`, `final bet`, or `Superbet combined odds`).
- **Secret/Payload leaks:** None (all session IDs, WordPress nonce, or cookies have been cleanly redacted from the committed files).
