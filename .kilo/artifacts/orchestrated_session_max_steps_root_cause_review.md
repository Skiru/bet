# Root-Cause Review: Orchestrated Session Max Steps Failure

## 1. Classification
- **MONOLITHIC_PROMPT_TOO_LARGE**: The unified session execution flow attempted to plan and execute all 8 subagents sequentially in a single session without boundary definitions.
- **PHASE_BUDGET_MISSING**: There was no budget constraint per-agent-turn, causing the orchestrator to consume steps on frontloaded planning and multi-stage reviews.
- **RESUME_TOKEN_MISSING**: The agent lacked a checkpoint/resume mechanism to serialize session state and pick up execution in a subsequent session.
- **SUBAGENT_HANDOFF_TOO_LATE**: Subagent execution happened sequentially within a single turn-loop, compounding the step count before completing a phase.
- **REVIEW_OVER_EXECUTION**: The orchestrator spent steps on extensive pre-flight checks and analysis review, hitting limits before actual execution phases.
- **MAX_STEPS_CONFIG_RISK**: The orchestrator is configured with `steps: 24`, whereas sequentially invoking 8 agents plus verification takes at least 32-40 steps.

---

## 2. Diagnostics Questions & Answers

### Question 1: Why did the agent spend steps on review instead of execution?
The agent frontloaded massive analytical reviews, checks, and planning steps. Since the prompt did not define strict phase boundaries or checkpoint milestones, the orchestrator performed verbose, monolithic planning loops and dry-runs, depleting its step limit before invoking critical downstream execution subagents.

### Question 2: Which phases are too large for one agent run?
The entire multi-sport live analyst session (spanning 8 distinct subagents across scanner, scout, enricher, statistician, valuator, challenger, builder, and test-engineer) is too large for a single agent session of 24 steps. Specifically, executing more than 2-3 complex subagents along with validation is the limit for any single session.

### Question 3: Which work must be delegated to subagents?
All domain-specific analysis must be strictly delegated to subagents:
- Event and fixture discovery -> `bet-scanner`
- Tipster and opinion aggregation -> `bet-scout`
- Context factor collection (lineups, injuries, venue, weather, etc.) -> `bet-enricher`
- Statistical market computation (goals, corners, cards, shots, tiebreaks, etc.) -> `bet-statistician`
- Standardized reference odds and implied margin analysis -> `bet-valuator`
- Adversarial challenge and recommendation auditing -> `bet-challenger`
- Analyst package construction -> `bet-builder`
- Final code, schema, and gate verification -> `bet-test-engineer`
The orchestrator must only direct, sequence, and verify these subagents, never perform the analysis itself.

### Question 4: Which work must be checkpointed and resumed?
The execution of the session must be chunked into specific phases, with each phase checkpointing its completed subagents, logs, and artifacts, and saving a structured `SessionState` and a `next_resume_prompt` so the next phase can be resumed in a new session.

### Question 5: Which artifact proves each phase is complete?
- **Phase J1 (Scanner + Scout)**: `scanner_event_universe.json` and `scout_tipster_opinion_layer.json`.
- **Phase J2 (Enricher + Statistician)**: `enricher_context_layer.json` and `statistician_market_analysis.json`.
- **Phase J3 (Valuator + Challenger + Builder)**: `valuator_reference_odds_layer.json`, `challenger_adversarial_review.json`, and `builder_package.json`.
- **Phase J4 (Test-Engineer + Final Report)**: `package_quality_review.md`, `status_safety_review.md`, and test-engineer verified `PASS`.

### Question 6: What exact continuation token should be returned after each phase?
The orchestrator must return a persisted continuation token in both `session_state.json` and the controller response. The minimum contract is:

```json
{
  "task_id": "ORCHESTRATED_SESSION_CONTINUATION_PROTOCOL_J0",
  "run_id": "<run_id>",
  "status": "PASS_CONTINUATION_REQUIRED",
  "current_phase": "J1",
  "completed_phases": ["J0", "J1"],
  "pending_phases": ["J2", "J3", "J4"],
  "completed_subagents": ["bet-scanner", "bet-scout"],
  "next_phase": "J2",
  "next_resume_prompt_path": "reports/pipeline_runs/<run_id>/resume_prompt_next.md",
  "final_verdict_allowed": false
}
```

The response body must also contain the exact `next_resume_prompt` text to start the next bounded run.

### Question 7: How do we avoid false PASS when only review was done?
We enforce a strict quality rule:
- A phase may only return `PASS_CONTINUATION_REQUIRED` if its specific phase artifacts have been successfully produced and verified on disk.
- A final session may only return `PASS_FINAL` if ALL subagent artifacts from J1 through J4 exist, the complete omission ledger exists, and the quality gate passes.
- Any execution that finishes without writing these verified artifacts must return a failing or blocked status (e.g., `BLOCKED_MISSING_ARTIFACT`).
