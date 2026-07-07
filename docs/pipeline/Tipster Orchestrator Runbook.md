# Tipster Orchestrator Runbook

## 1. Overview
The S2 Tipster Scraper v2 runs under a strict, compliance-first orchestrator setup.
By default, only safe sources that allow live fetching via robots.txt are processed.
Polish-specific sentiment sources (like ZawodTyper and Typersi) are classified as **Certified Shadow Sources** and require an explicit command-line opt-in.
Uncertified sources may run under the **Operator-Risk Public Read Discovery** mode only if explicitly ack-approved by the operator via a local configuration file.

---

## 2. Certified vs Operator-Risk Boundary
1. **Certified Shadow:** Fully compliant sources matching robots.txt (or having a legal ToS exception), having a repo-local ToS review, and integrated as trustworthy evidence.
2. **Operator-Risk:** Sources that the operator manually designates for public-read discovery despite robots.txt or other blocks. 
   - Strict Separation: All operator-risk picks must have `compliance_tier="operator_risk_public_read"`, `evidence_use="manual_review_only_or_low_trust_context"`, and `promotion_allowed=false`. They must never influence final betting actions or EV, nor mix with certified shadow without combined flags.

---

## 3. Command Reference

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

### Command 4: Operator-Risk Public-Read Discovery Run (ProTipster)
To run a source under operator-risk discovery mode:
```fish
.venv-tipster-v2/bin/python scripts/pipeline_steps/s2_tipsters_v2_live_dry_run.py \
  --date YYYY-MM-DD \
  --terms-reviewed-json docs/pipeline/tipster_terms_review.local.json \
  --operator-risk-json docs/pipeline/tipster_operator_risk.local.json \
  --allow-operator-risk-public-read \
  --source protipster \
  --max-pages-per-source 6 \
  --handoff-out /tmp/protipster_operator_risk_handoff.json
```

### Command 5: Combined Run (Certified Shadow + Operator Risk)
To combine certified shadow and operator-risk sources into a single mixed handoff:
```fish
.venv-tipster-v2/bin/python scripts/pipeline_steps/s2_tipsters_v2_live_dry_run.py \
  --date YYYY-MM-DD \
  --terms-reviewed-json docs/pipeline/tipster_terms_review.local.json \
  --operator-risk-json docs/pipeline/tipster_operator_risk.local.json \
  --allow-operator-risk-public-read \
  --combine-certified-and-risk \
  --source zawodtyper \
  --source typersi \
  --source protipster \
  --max-pages-per-source 6 \
  --handoff-out /tmp/combined_handoff.json
```

---

## 4. Storage Sinks & Sandbox Paths
- **JSON Consensus:** Written to `$BET_PIPELINE_DATA_DIR/<date>_tipster_consensus_shadow.json`.
- **Handoff Artifact:** Serialized to `$BET_PIPELINE_ARTIFACT_DIR/<date>_tipster_handoff.json`.
- **SQLite Database:** Saved under `$BET_PIPELINE_DATA_DIR/tipsters_shadow_sidecar.sqlite`.

---

## 5. Downstream S3/S4 Consumption
Downstream stages (S3 and S4) consume the handoff sidecar file *optionally*:
- S3/S4 are allowed consumers only.
- The handoff represents **contextual evidence**, not primary shortlist input or Kelly valuation inputs.
- Missing handoff **does not block** S3/S4 execution unless explicitly required by environment variables.
- Downstream stages use it strictly for market sanity checks and qualitative team-specific context.

---

## 6. Monitoring & Warnings
Inspect log outputs for the following signals:
1. **`total_picks=0`:** Normal state on off-days, but should be monitored for persistent empty runs.
2. **Schema Drift:** High rate of `verdict=empty` on previously functional pages indicates HTML structure updates.
3. **High Rejection Rate:** High number of `REJECT_LOW_QUALITY` or `REJECT_GARBAGE` labels indicates poor page density.
4. **Accidental Operator-Risk Mix:** Verify that `source_risk_mix` is `certified_only` unless the explicit `--combine-certified-and-risk` option was passed.
5. **Bookmaker Redirect Violation:** Inspect detail parser failures or fetch blockages to ensure the robot never follows non-same-origin paths like `/r/` or `/betting-sites/go/`.
6. **Coupon/AKO Leakage:** Verify that all multi-event combo cards are successfully rejected.
7. **Bonus/Casino Leakage:** Verify that all bonus and advertising frames are discarded.

---

## 7. Rollback Procedure
If a certified shadow source experiences compliance, drift, or accuracy issues:
1. **Remove Source:** Edit `src/bet/tipsters/source_registry.py` and remove the target from `CERTIFIED_SHADOW_SOURCE_IDS`.
2. **Revert Status:** Demote the source status to candidate or operator-risk-only.
3. **Leave Parser Tests:** Keep all parser and coverage tests to prevent regressions during offline repair.
