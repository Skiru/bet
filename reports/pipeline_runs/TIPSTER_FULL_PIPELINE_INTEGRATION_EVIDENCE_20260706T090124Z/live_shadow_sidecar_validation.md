# Live Shadow Sidecar Smoke Validation Report

- **Status**: PASS
- **Total Picks Extracted (Zawodtyper)**: 26
- **Consensus File Path**: `reports/pipeline_runs/TIPSTER_FULL_PIPELINE_INTEGRATION_EVIDENCE_20260706T090124Z/live_shadow_sidecar_smoke/tipsters_shadow.json`
- **Handoff File Path**: `reports/pipeline_runs/TIPSTER_FULL_PIPELINE_INTEGRATION_EVIDENCE_20260706T090124Z/live_shadow_sidecar_smoke/tipsters_handoff.json`
- **Sandbox SQLite DB Path**: `/tmp/tipsters_shadow_sidecar.sqlite`

## Verification Checklist:
1. **Zero Production DB Mutations**: Verified sandbox database used (`/tmp/tipsters_shadow_sidecar.sqlite`), preventing any repository-local SQLite mutations.
2. **Schema Compliance**: Hand-off schema strictly validated as `tipster_evidence_handoff_v1`.
3. **Allowed Consumers Enforced**: Hand-off consumers restricted to `S3`, `S4`, and `manual Superbet quote review` only.
4. **Forbidden Actions Stripped**: Guaranteed zero exposure of `EV`, `stake`, `coupon`, `final bet`, or `Superbet combined odds` fields.
5. **Agent Readiness Records Present**: Verified that each pick contains dynamic `agent_use_decision` and order-insensitive `normalized_event_key` mapping.

## Validation Errors:


---
*Verified automatically by Kilo on 2026-07-06*
