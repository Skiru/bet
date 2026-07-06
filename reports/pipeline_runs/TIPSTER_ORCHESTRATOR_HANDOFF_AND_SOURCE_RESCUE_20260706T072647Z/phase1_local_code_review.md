# Phase 1: Local Code Review Report

## Core Findings & Answers

### 1. Is ZawodTyper agent_readiness actually written into main JSON artifact?
**No.** Currently, `pipeline_adapter.to_legacy_pick` does not invoke `analyze_pick_readiness` and does not include the `agent_readiness` dictionary in the serialized output for each pick.

### 2. Is agent_readiness persisted or represented in SQLite/consensus/handoff?
**No.** The SQLite tables (`tipster_picks_v2` and `tipster_consensus_v2`) and the consensus grouping structure have no schema fields or aggregated representation for `agent_readiness` or `agent_readiness_summary`. No handoff mechanism exists yet.

### 3. Does pipeline_adapter call analyze_pick_readiness?
**No.** `pipeline_adapter.py` never imports or references `analyze_pick_readiness`.

### 4. Does storage preserve readiness metadata?
**No.** Since `pipeline_adapter` doesn't provide the metadata, the storage layer is completely unaware of it, neither in JSON serialization nor SQLite insertion.

### 5. Is there a handoff artifact for S3/S4/manual review?
**No.** There is no handoff module or structured file output representing tipster evidence handoff for downstream consumption.

### 6. Is ZawodTyper included in source orchestration safely?
**Yes and No.** It is implemented in `zawodtyper.py` using a highly secure public XHR transport without sessions or private APIs, but it is currently categorized under `LEGACY_SOURCE_IDS` in `source_registry.py` and is omitted from the default core orchestration unless `--source zawodtyper` is explicitly passed.

### 7. Is ZawodTyper only evidence-only?
**Yes.** It is explicitly marked with `decision_boundary="evidence_only_not_a_bet"` and its notes state it is for shadow cross-check context only.

### 8. Are forbidden betting fields structurally impossible?
**Yes.** The output schema does not contain fields like `stake`, `coupon`, `final bet`, or `Superbet combined odds`. However, we will reinforce this structurally at the handoff level with explicit schema restrictions.

### 9. Are other sources incorrectly buried as manual/legacy without rescue path?
**Yes.** Multiple valuable tipster websites (e.g., `sportsgambler`, `windrawwin`, `typersi`) are buried under conservative production statuses without a clear automated certification and rescue path.

### 10. What exact gaps must be fixed?
- **Gap A (Readiness in Pick):** `to_legacy_pick` must include `"agent_readiness": analyze_pick_readiness(p)`.
- **Gap B (Readiness in Consensus):** Each consensus group must contain an `agent_readiness_summary` object aggregating decisions, allowed/forbidden lists, and counts of decisions.
- **Gap C (Handoff Artifact):** A new `handoff.py` module must be implemented to compile a clean, validated `tipster_evidence_handoff_v1` artifact.
- **Gap D (Orchestrator CLI):** Both `s2_tipsters_v2_live_dry_run.py` and `s2_tipsters_v2.py` must support the `--include-certified-shadow` option and `--handoff-out` parameter.
- **Gap E (Rescue Matrix):** Implement `source_certification.py` and generate a robust `source_rescue_matrix.json` for robots.txt auditing.

## Selected Strategy & Clean Plan
1. **Apply Patch to `pipeline_adapter.py`** to integrate `analyze_pick_readiness` into picks and consensus groups.
2. **Implement `handoff.py`** to construct and write the `tipster_evidence_handoff_v1` payload with strict validation of forbidden betting fields.
3. **Update `source_registry.py`** to define `CERTIFIED_SHADOW_SOURCE_IDS = ("zawodtyper",)`.
4. **Update Runners (`s2_tipsters_v2_live_dry_run.py` and `s2_tipsters_v2.py`)** to support `--include-certified-shadow` and `--handoff-out`.
5. **Implement `source_certification.py`** with automated `robots.txt` compliance checks using Python's `urllib.robotparser`.
6. **Generate the Source Rescue Matrix** JSON and Markdown reports.
7. **Create comprehensive docs and E2E tests** in `tests/tipsters/`.
8. **Run validation, compile checks, and live smoke test** to prove stability.
