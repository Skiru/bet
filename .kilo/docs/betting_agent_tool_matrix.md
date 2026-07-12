# Betting Agent and Tool Execution Matrix

This matrix governs the division of labor between the canonical shell-capable primary executor and its six partner power agents.

## Key Rules

1. **Script Executor for Script Steps:** `bet-executor` is canonical. Code/General with Bash is only an engineering repair path or emergency fallback.
2. **Seven Power Agents:** `bet-executor`, `bet-researcher`, `bet-modeler`, `bet-risk-gatekeeper`, `bet-builder`, `bet-auditor`, and `bet-settler-postevent` are the complete active set.
3. **Shell Boundary:** Business specialists deny Bash. `bet-auditor` allows Bash only for read-only verification and denies mutation.
4. **Human Execution:** S9 is human-only. No automated bookmaker placement is permitted.
5. **Odds and Quotes:** A Superbet manual quote is required before any candidate is bettable.

---

## Agent Permission Matrix

These capability cells mirror the agent YAML. All seven agents set `question: deny`, deny repository mutation (`edit`, `write`, `apply_patch`), and inherit the parent model without an override.

| Agent | Bash | DB read | Public web | Artifact write | Task |
|---|---|---|---|---|---|
| `bet-executor` | allow | deny | deny | allow | exactly six partner agents; wildcard deny |
| `bet-researcher` | deny | allow | allow | allow | deny |
| `bet-modeler` | deny | allow | deny | allow | deny |
| `bet-risk-gatekeeper` | deny | allow | allow | allow | deny |
| `bet-builder` | deny | deny | deny | allow | deny |
| `bet-auditor` | allow (verification only) | allow | deny | allow | deny |
| `bet-settler-postevent` | deny | allow | deny | allow | deny |

---

## Tool and Execution Matrix

| Pipeline Step | Manifest Agent | Execution Mode | Canonical Wrapper | Script Executor | Domain Specialist | Allowed Tools | Forbidden Tools | Required Output | Hard Stop |
|---|---|---|---|---|---|---|---|---|---|
| **S0** (Settler) | `bet-settler-postevent` | script | `scripts/pipeline_steps/s0_settler.py` | `bet-executor` | `bet-settler-postevent` | `bet_sqlite_query`, `bet_artifact_write`, `read` | `bash`, `edit`, `write`, `apply_patch` | `historical_pnl` | Settlement or learning mismatch |
| **S1** (Discover) | `bet-researcher` | script | `scripts/pipeline_steps/s1_discover.py` | `bet-executor` | `bet-researcher` | `bet_sqlite_query`, `bet_artifact_write`, `read`, `webfetch`, `brave-search_*` | `bash`, `edit`, `write`, `apply_patch` | `fixtures_shortlist` | Event lacks explicit status/reason |
| **S1e** (Events) | `bet-researcher` | state_only | None | `bet-executor` | `bet-researcher` | `bet_sqlite_query`, `bet_artifact_write`, `read` | `bash` | `discovered_events` | Silent event omission |
| **S2** (Tipsters) | `bet-researcher` | script | `scripts/pipeline_steps/s2_tipsters.py` | `bet-executor` | `bet-researcher` | `bet_sqlite_query`, `bet_artifact_write`, `read`, `webfetch`, `brave-search_*` | `bash`, `edit`, `write`, `apply_patch` | `tipster_consensus` | Unlabeled tipster absence |
| **S2.3** (Gap Det) | `bet-researcher` | agent_artifact | None | None (Artifact only) | `bet-researcher` | `bet_sqlite_query`, `bet_artifact_write`, `read` | `bash` | `s2_3_enrichment_gaps` | Empty gap inventory |
| **S2.5** (Enrichment)| `bet-researcher` | agent_artifact | None | None (Artifact only) | `bet-researcher` | `bet_sqlite_query`, `bet_artifact_write`, `read`, `webfetch`, `brave-search_*` | `bash` | `s2_5_provider_observations` | Unverified provider claims |
| **S2.7** (Reconcile) | `bet-researcher` | agent_artifact | None | None (Artifact only) | `bet-researcher` | `bet_sqlite_query`, `bet_artifact_write`, `read` | `bash` | `s2_7_reconciled_facts` | Unresolved contradictions |
| **S2.9** (Readiness) | `bet-researcher` | agent_artifact | None | None (Artifact only) | `bet-researcher` | `bet_sqlite_query`, `bet_artifact_write`, `read` | `bash` | `s2_9_data_readiness` | Quality grading below threshold |
| **S3** (Stats) | `bet-modeler` | script | `scripts/pipeline_steps/s3_stats.py` | `bet-executor` | `bet-modeler` | `bet_sqlite_query`, `bet_artifact_write`, `read` | `bash`, web tools | `calibrated_probabilities` | Unsupported market family |
| **S4** (Valuator) | `bet-modeler` | script | `scripts/pipeline_steps/s4_valuator.py` | `bet-executor` | `bet-modeler` | `bet_sqlite_query`, `bet_artifact_write`, `read` | `bash`, web tools | `expected_value_estimates` | EV/stake attempted without real odds |
| **S5** (Motivation) | `bet-risk-gatekeeper` | agent_artifact | None | None (Artifact only) | `bet-risk-gatekeeper` | `bet_sqlite_query`, `bet_artifact_write`, `read`, `webfetch`, `brave-search_*` | `bash`, mutation | `s5_context_motivation_risk` | Blocker detected |
| **S6** (Repeat Guard) | `bet-risk-gatekeeper` | script | `scripts/pipeline_steps/s6_repeats.py` | `bet-executor` | `bet-risk-gatekeeper` | `bet_sqlite_query`, `bet_artifact_write`, `read`, `webfetch`, `brave-search_*` | `bash`, mutation | `s6_portfolio_repeat_guard` | Unchecked repeats or loss-chasing |
| **S7** (Gate) | `bet-risk-gatekeeper` | script | `scripts/pipeline_steps/s5_gate.py` | `bet-executor` | `bet-risk-gatekeeper` | `bet_sqlite_query`, `bet_artifact_write`, `read`, `webfetch`, `brave-search_*` | `bash`, mutation | `approved_picks` | Weak approval; zero is valid NO_ACTION_TERMINAL |
| **S7b** (Validation) | `bet-auditor` | script | `scripts/pipeline_steps/s7_validate.py` | `bet-executor` | `bet-auditor` | `bash`, `bet_sqlite_query`, `bet_artifact_write`, `read` | `edit`, `write`, `apply_patch` | `verified_market_availability` | Missing quote is MANUAL_QUOTE_REQUIRED |
| **S8** (Builder) | `bet-builder` | script | `scripts/pipeline_steps/s8_build_coupons.py` | `bet-executor` | `bet-builder` | `bet_artifact_write`, `read` | `bash`, `bet_sqlite_query`, web tools | `manual_quote_cards` | Executable coupon attempted before S9 |
| **S9** (Human Gate) | `bet-risk-gatekeeper` | human_gate | None | None | None (Human only) | None | All (Human must do the job) | `executed_bets_journal` | Missing Superbet manual quote |
| **S10** (Post-event) | `bet-settler-postevent` | state_only | None | None | `bet-settler-postevent` | `bet_sqlite_query`, `bet_artifact_write`, `read` | `bash` | `s10_settlement_handoff` | Partial settlement or empty outcome |
