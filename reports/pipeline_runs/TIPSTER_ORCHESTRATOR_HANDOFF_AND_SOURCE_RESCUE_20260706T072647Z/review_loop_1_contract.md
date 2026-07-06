# Loop 1 — Contract & Schema Review

## 1. JSON Artifact Schema Check
- **Schema version:** `tipster_consensus_v2.3`
- **Verification:** All keys (`schema_version`, `contract`, `sources`, `total_picks`, `sources_with_picks`, `all_picks`, `consensus`, `blocked_sources`, `skipped_sources`, `pipeline_consumers`, `fail_closed`) are fully populated.
- **Verdict:** PASS

## 2. All Picks Schema Check
- **Injected fields:** Added `"agent_readiness": analyze_pick_readiness(p)` to each pick.
- **Fields preserved:** `"decision_boundary": "evidence_only_not_a_bet"` and `"pipeline_use"` are preserved intact.
- **Verdict:** PASS

## 3. Consensus Schema Check
- **Injected fields:** Added `agent_readiness_summary` to each consensus row.
- **Structure:**
  ```json
  "agent_readiness_summary": {
    "all_evidence_only": true,
    "allowed_pipeline_stages": ["S3 contextual cross-check", "S4 market sanity", "manual Superbet quote review"],
    "forbidden_actions": ["EV", "stake", "coupon", "final bet", "Superbet combined odds"],
    "needs_match_resolution_count": 0,
    "needs_manual_review_count": 0,
    "reject_low_quality_count": 0,
    "reject_garbage_count": 0,
    "usable_context_count": 1,
    "decisions": ["USE_AS_CONTEXT"]
  }
  ```
- **Verdict:** PASS

## 4. Handoff Schema Check
- **Schema version:** `tipster_evidence_handoff_v1`
- **Forbidden fields check:** Cleanly deletes and prevents any key matching `EV`, `stake`, `coupon`, `final bet`, or `Superbet combined odds`.
- **Verdict:** PASS

## 5. Source Rescue Matrix Check
- **Structure:** JSON schema includes `source_id`, `current_registry_status`, `candidate_path`, `why_not_rejected`, `classification`, `next_certification_steps`, `allowed_probe_type`, `disallowed_methods`, `priority`, and `recommended_next_pass`.
- **Verdict:** PASS
