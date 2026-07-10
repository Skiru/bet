# Betting Agent and Tool Execution Matrix

This matrix governs the division of labor between the shell-capable primary executors and the consolidated power subagents.

## Key Rules

1. **Script Executor for Script Steps:** Must be `bet-executor` or built-in `Code`/`General` with Bash capability.
2. **No legacy orchestrator:** The legacy `bet-orchestrator` has been removed. Active primary-mode Code/General with Bash handles all script orchestration.
3. **Consolidated Power Agents:** Micro-agents have been consolidated into 5 high-performing power agents: `bet-researcher`, `bet-modeler`, `bet-risk-gatekeeper`, `bet-auditor`, and `bet-settler-postevent`.
4. **Human Execution:** S9 is human-only. No automated bookmaker placement is permitted.
5. **Odds and Quotes:** A Superbet manual quote is required before any candidate is bettable.

---

## Tool and Execution Matrix

| Pipeline Step | Manifest Agent | Execution Mode | Canonical Wrapper | Script Executor | Domain Specialist | Allowed Tools | Forbidden Tools | Required Output | Hard Stop |
|---|---|---|---|---|---|---|---|---|---|
| **S0** (Settler) | `bet-settler-postevent` | script | `scripts/pipeline_steps/s0_settler.py` | `bet-executor` / Code / General | `bet-settler-postevent` | `bet_sqlite_query`, `bet_artifact_write`, `read` | `bash`, `edit`, `write`, `apply_patch` | `historical_pnl` | Settlement or learning mismatch |
| **S1** (Discover) | `bet-researcher` | script | `scripts/pipeline_steps/s1_discover.py` | `bet-executor` / Code / General | `bet-researcher` | `bet_sqlite_query`, `bet_artifact_write`, `read`, `webfetch`, `brave-search_*` | `bash`, `edit`, `write`, `apply_patch` | `fixtures_shortlist` | Out-of-window event discover |
| **S1e** (Events) | `bet-researcher` | state_only | None | `bet-executor` / Code / General | `bet-researcher` | `bet_sqlite_query`, `bet_artifact_write`, `read` | `bash` | `discovered_events` | Empty discovered universe |
| **S2** (Tipsters) | `bet-researcher` | script | `scripts/pipeline_steps/s2_tipsters.py` | `bet-executor` / Code / General | `bet-researcher` | `bet_sqlite_query`, `bet_artifact_write`, `read`, `webfetch`, `brave-search_*` | `bash`, `edit`, `write`, `apply_patch` | `tipster_consensus` | Zero valid tips |
| **S2.3** (Gap Det) | `bet-researcher` | agent_artifact | None | None (Artifact only) | `bet-researcher` | `bet_sqlite_query`, `bet_artifact_write`, `read` | `bash` | `s2_3_enrichment_gaps` | Empty gap inventory |
| **S2.5** (Enrichment)| `bet-researcher` | agent_artifact | None | None (Artifact only) | `bet-researcher` | `bet_sqlite_query`, `bet_artifact_write`, `read`, `webfetch`, `brave-search_*` | `bash` | `s2_5_provider_observations` | Unverified provider claims |
| **S2.7** (Reconcile) | `bet-researcher` | agent_artifact | None | None (Artifact only) | `bet-researcher` | `bet_sqlite_query`, `bet_artifact_write`, `read` | `bash` | `s2_7_reconciled_facts` | Unresolved contradictions |
| **S2.9** (Readiness) | `bet-researcher` | agent_artifact | None | None (Artifact only) | `bet-researcher` | `bet_sqlite_query`, `bet_artifact_write`, `read` | `bash` | `s2_9_data_readiness` | Quality grading below threshold |
| **S3** (Stats) | `bet-modeler` | script | `scripts/pipeline_steps/s3_stats.py` | `bet-executor` / Code / General | `bet-modeler` | `bet_sqlite_query`, `bet_artifact_write`, `read` | `bash` | `calibrated_probabilities` | Unsupported market family |
| **S4** (Valuator) | `bet-modeler` | script | `scripts/pipeline_steps/s4_valuator.py` | `bet-executor` / Code / General | `bet-modeler` | `bet_sqlite_query`, `bet_artifact_write`, `read`, `webfetch` | `bash` | `expected_value_estimates` | Missing fair price or probability |
| **S5** (Motivation) | `bet-risk-gatekeeper` | agent_artifact | None | None (Artifact only) | `bet-risk-gatekeeper` | `bet_artifact_write`, `read` | `bash`, `bet_sqlite_query` | `s5_context_motivation_risk` | Blocker detected |
| **S6** (Repeat Guard) | `bet-risk-gatekeeper` | script | `scripts/pipeline_steps/s6_repeats.py` | `bet-executor` / Code / General | `bet-risk-gatekeeper` | `bet_artifact_write`, `read` | `bash`, `bet_sqlite_query` | `s6_portfolio_repeat_guard` | Unchecked repeats or loss-chasing |
| **S7** (Gate) | `bet-risk-gatekeeper` | script | `scripts/pipeline_steps/s5_gate.py` | `bet-executor` / Code / General | `bet-risk-gatekeeper` | `bet_artifact_write`, `read` | `bash`, `bet_sqlite_query` | `approved_picks` | Empty selection |
| **S7b** (Validation) | `bet-auditor` | script | `scripts/pipeline_steps/s7_validate.py` | `bet-executor` / Code / General | `bet-auditor` | `bash`, `bet_sqlite_query`, `bet_artifact_write`, `read` | `edit`, `write`, `apply_patch` (Verification only) | `verified_market_availability` | Validation FAIL |
| **S8** (Builder) | `bet-builder` | script | `scripts/pipeline_steps/s8_build_coupons.py` | `bet-executor` / Code / General | `bet-builder` | `bet_artifact_write`, `read` | `bash`, `bet_sqlite_query` | `final_coupons` | Correlation mismatch |
| **S9** (Human Gate) | `bet-risk-gatekeeper` | human_gate | None | None | None (Human only) | None | All (Human must do the job) | `executed_bets_journal` | Missing Superbet manual quote |
| **S10** (Post-event) | `bet-settler-postevent` | state_only | None | None | `bet-settler-postevent` | `bet_sqlite_query`, `bet_artifact_write`, `read` | `bash` | `s10_settlement_handoff` | Partial settlement or empty outcome |
