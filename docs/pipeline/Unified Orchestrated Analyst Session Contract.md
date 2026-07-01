# Unified Orchestrated Analyst Session Contract

This contract establishes the formal specification, agent responsibilities, execution phases, required artifacts, quality gates, and schema requirements for the production-grade, orchestrator-led betting session.

## 1. Executive Summary & Flow Philosophy
The session follows a single unified live analyst flow led entirely by the `bet-orchestrator`. Subagents are invoked sequentially to perform isolated analysis, and the orchestrator never performs specialist analysis itself.
Odds, HYDRATED statuses, and model probabilities are treated as **optional** reference points. Missing elements do not block recommendations; they lower confidence levels, place items on a watchlist, or affect EV calculations.

---

## 2. Required Subagents & Roles
- **bet-orchestrator (Primary/Leader):** Sequentially plans and invokes required subagents, creates the subagent manifest and omission ledger, enforces hard stop gates, and prevents any silent omissions.
- **bet-scanner:** Fixture and event universe discovery covering football, tennis, basketball, volleyball, hockey (if available), CS2, Dota2, and Valorant. Drops unsupported sports/events with explicit reasons.
- **bet-scout:** Tipster and opinion aggregation layer. Classifies source types, affiliate bias, documents consensus/disagreements, and scores argument quality. Tipster is never the primary truth.
- **bet-enricher:** Context enrichment layer. Collects and logs key match factors: injuries, lineups, referee, weather, venue, travel, surface, and round. Unfilled gaps are marked as `UNKNOWN`.
- **bet-statistician:** Statistical market analysis. Computes corners, cards, goals, shots, and shots on target (SOT) for football; tennis games, handicap, tiebreaks, and aces (only if evidence exists).
- **bet-valuator:** Valuation-reference layer. Standardizes reference odds. The absence of odds lowers EV confidence but never blocks analyst recommendations. Implies no bookmaker odds as model probabilities.
- **bet-challenger:** Adversarial challenger. Audits all top/secondary recommendations, rejects generic placeholders, challenges tipster bias, and evaluates the KEEP_TOP gate.
- **bet-builder:** Package constructor. Aggregates findings into the structured analyst package.
- **bet-test-engineer:** Independent test and quality gate validator. Performs PASS/FAIL verification across all logs, routing, and quality rules.

---

## 3. Required Session Artifacts

The session is only complete and verified when all of the following artifacts exist and conform to their schemas:

1. `orchestrator_session_plan.md`
2. `orchestrator_subagent_manifest.json`
3. `model_routing_matrix.json`
4. `active_model_runtime_proof.md`
5. `scanner_event_universe.md` / `scanner_event_universe.json`
6. `scout_tipster_opinion_layer.md` / `scout_tipster_opinion_layer.json`
7. `enricher_context_layer.md` / `enricher_context_layer.json`
8. `statistician_market_analysis.md` / `statistician_market_analysis.json`
9. `valuator_reference_odds_layer.md` / `valuator_reference_odds_layer.json`
10. `challenger_adversarial_review.md` / `challenger_adversarial_review.json`
11. `builder_package.md` / `builder_package.json`
12. `omission_ledger.md` / `omission_ledger.json`
13. `package_quality_review.md`
14. `status_safety_review.md`

---

## 4. Omission Ledger and No-Silent-Omission Gate
To satisfy the no-silent-omission contract, any sport, league, event, or data gap that is discovered but not recommended must be accounted for in the `omission_ledger.json` with a valid category:
- `OMITTED`: Sport/competition explicitly excluded with a valid reason.
- `WATCHLIST`: Put on watchlist due to missing data (e.g., missing HYDRATED status or lineups).
- `REJECTED`: Discovered but rejected by a subagent or the adversarial challenger.

---

## 5. Model Routing Specifications
Every active required agent must route to the high-reasoning Gemini 3.5 Flash Flex model.
- **Provider:** `google-vertex`
- **Model:** `gemini-3.5-flash`
- **Alias:** `gemini-3.5-flash-flex-high`
- **Tier:** `flex`
- **Thinking Level:** `HIGH`

No routing to local Qwen, GPT, or Anthropic models is permitted for the active betting analyst session.

---

## 6. Quality Gates and Final Safety Policies
1. **Zero Valid Tips Gate:** If Phase C (`bet-scout`) identifies 0 valid tips, a hard stop is triggered (`NO_DATA`).
2. **Adversarial Gate:** `bet-challenger` must issue a `KEEP_TOP` verdict for any top recommendation to remain in the final list.
3. **Validation Gate:** `bet-test-engineer` must run independent tests and format checks and issue a `PASS`.
4. **Human Superbet Quote Safety:** No final coupon or combined Bet Builder odds may be computed or combined automatically. Final manual coupons strictly require a real, manually-entered Superbet operator quote.
5. **No Automated Placement:** Auto-betting, scraping of Betclic/Superbet APIs, and browser automation are strictly forbidden.

---

## 7. Phased Execution & Checkpoint-Continuation Protocol

To prevent step-exhaustion failures in monolithic multi-agent sessions, the orchestrator must adhere to the **Orchestrated Session Continuation Protocol** (`docs/pipeline/Orchestrated Session Continuation Protocol.md`).

### 7.1. Phased Division & Artifact Budgets
Execution is divided into the following sequential phases, each having a specific required subagent and artifact budget:
- **Phase J1: Discovery & Opinion Compilation**
  - Subagents: `bet-scanner`, `bet-scout`
  - Required Artifacts: `scanner_event_universe.json`, `scout_tipster_opinion_layer.json`
- **Phase J2: Context & Statistical Analysis**
  - Subagents: `bet-enricher`, `bet-statistician`
  - Required Artifacts: `enricher_context_layer.json`, `statistician_market_analysis.json`
- **Phase J3: Valuation, Challenge, & Build**
  - Subagents: `bet-valuator`, `bet-challenger`, `bet-builder`
  - Required Artifacts: `valuator_reference_odds_layer.json`, `challenger_adversarial_review.json`, `builder_package.json`
- **Phase J4: QA, Verification, & Final Report**
  - Subagents: `bet-test-engineer`
  - Required Artifacts: `package_quality_review.md`, `status_safety_review.md`, `omission_ledger.json`

### 7.2. Max Steps Protection & Checkpoint Rules
- The orchestrator has a hard limit of 24 steps. If step budget risk appears (approaching 16-18 steps), or if completing the current phase, the orchestrator must serialize its state and halt early.
- In such cases, the orchestrator must return a status of `PASS_CONTINUATION_REQUIRED` with a structured `next_resume_prompt` pointing to the next execution phase.

### 7.3. Cumulative Manifest Rule
- The subagent manifest (`orchestrator_subagent_manifest.json`) must be updated cumulatively. Each phase must append its newly executed subagents and output artifacts, ensuring that the manifest is a cumulative and accurate ledger of the entire multi-phase run.

### 7.4. No False PASS Prevention
- To prevent a false `PASS` (where only precheck or planning steps are executed, but no subagents are run), the orchestrator is strictly forbidden from returning `PASS_FINAL` without confirming that ALL 8 subagents have completed and ALL required artifacts from J1 through J4 successfully exist on disk.
- Any completion statement issued without these verifications must be rejected by quality-gate audits.

### 7.5. Resume-Token Schema
Every non-final phase must persist a resume token inside `session_state.json` containing:
- `task_id`
- `run_id`
- `status`
- `current_phase`
- `completed_phases`
- `pending_phases`
- `required_subagents`
- `completed_subagents`
- `artifact_manifest`
- `omission_ledger_path`
- `model_routing_status`
- `next_resume_prompt`
- `next_phase`
- `final_verdict_allowed`

### 7.6. Phase Checkpoint Schema
Each phase checkpoint must record:
- `TASK_ID=<task_id>`
- `RUN_ID=<run_id>`
- `STATUS=<status>`
- `CURRENT_PHASE=<phase>`
- `COMPLETED_PHASES=<json array>`
- `PENDING_PHASES=<json array>`
- `COMPLETED_SUBAGENTS=<json array>`
- `REQUIRED_ARTIFACTS=<json array>`
- `MISSING_ARTIFACTS=<json array>`
- `NEXT_PHASE=<phase or FINAL>`
- `NEXT_RESUME_PROMPT_PATH=<path or NONE>`
- `FINAL_VERDICT_ALLOWED=true|false`
