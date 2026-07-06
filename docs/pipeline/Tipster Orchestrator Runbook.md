# Tipster Orchestrator Runbook

## 1. Overview
The S2 Tipster Scraper v2 runs under a strict, compliance-first orchestrator setup.
By default, only safe sources that allow live fetching via robots.txt are processed.
Polish-specific sentiment sources (like ZawodTyper) are classified as **Certified Shadow Sources** and require an explicit command-line opt-in.

---

## 2. Command Reference

### Command 1: Legacy Canonical S2 Run
This command executes the original canonical tipster aggregation pipeline steps.
```fish
.venv-tipster-v2/bin/python scripts/pipeline_steps/s2_tipsters.py --date YYYY-MM-DD --runtime-mode DRY_RUN
```

### Command 2: Shadow Evidence Sidecar Run
This command launches the compliance-first shadow evidence collector sidecar wrapper (Model B).
```fish
.venv-tipster-v2/bin/python scripts/pipeline_steps/s2_tipsters_shadow_evidence.py \
  --date YYYY-MM-DD \
  --runtime-mode LIVE_SHADOW \
  --allow-live-network \
  --terms-reviewed-json docs/pipeline/tipster_terms_review.local.json \
  --include-certified-shadow
```

### Command 3: Direct Source Smoke Run (ZawodTyper)
To test a single certified shadow source directly and construct the evidence handoff:
```fish
.venv-tipster-v2/bin/python scripts/pipeline_steps/s2_tipsters_v2_live_dry_run.py \
  --date YYYY-MM-DD \
  --terms-reviewed-json docs/pipeline/tipster_terms_review.local.json \
  --source zawodtyper \
  --handoff-out /tmp/zawodtyper_handoff.json
```

---

## 3. Storage Sinks & Sandbox Paths
- **JSON Consensus:** Written to `$BET_PIPELINE_DATA_DIR/<date>_tipster_consensus_shadow.json`.
- **Handoff Artifact:** Serialized to `$BET_PIPELINE_ARTIFACT_DIR/<date>_tipster_handoff.json`.
- **SQLite Database:** Saved under `$BET_PIPELINE_DATA_DIR/tipsters_shadow_sidecar.sqlite`.

---

## 4. Downstream S3/S4 Consumption
Downstream stages (S3 and S4) consume the handoff sidecar file *optionally*:
- S3/S4 are allowed consumers only.
- The handoff represents **contextual evidence**, not primary shortlist input or Kelly valuation inputs.
- Missing handoff **does not block** S3/S4 execution unless explicitly required by environment variables.
- Downstream stages use it strictly for market sanity checks and qualitative team-specific context.

---

## 5. Required Environment Acknowledgments
- **`BET_PIPELINE_LIVE_ACK=I_UNDERSTAND_LIVE_PROVIDER_CALLS`**: Required for live shadow runs.
- **`BET_PIPELINE_WRITE_ACK=I_UNDERSTAND_PRODUCTION_WRITE`**: Required for writing to any production database.
- **No Production Write Unless Acknowledged:** By default, non-production modes fail-closed and do not write to production data sinks.

---

## 6. Failure Modes & Incident Resolution

| Failure Mode | Root Cause | Operator Mitigation |
|--------------|------------|---------------------|
| `BLOCKED_TERMS_REVIEW_FILE_MISSING` | `--terms-reviewed-json` was not passed. | Provide the path to the approved terms review JSON file. |
| `INVALID_REVIEW_ATTESTATION` | Reviewer name or date contains placeholders. | Complete the operator review and sign off with a valid name/date. |
| `total_picks=0` | No active picks published. | Normal state on off-days; downstream pipeline continues using stats. |
| `BLOCK_ROBOTS` | robots.txt disallows scraping. | Revert to offline fixture mode or verify if terms review allows shadow. |
| `Event Ambiguity` | Fixture split is non-standard. | Set `needs_match_resolution=true` and route to manual review. |
| `Low Extraction Quality` | Extractor scored below 0.45. | Mark pick as `REJECT_LOW_QUALITY`. |
| `Schema Drift` | Upstream HTML structure changed. | Fail-closed automatically; parser update required. |
