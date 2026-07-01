# Orchestrated Session Continuation Protocol

This document defines the checkpoint, resume, and final-verdict contract for orchestrated analyst sessions so a full multi-agent run cannot fail after review-only work because the orchestrator reached its maximum step budget.

## 1. Purpose

The orchestrator is limited to `steps: 24` and must not attempt a full scanner-through-builder-through-test-engineer run in one session. The session must be split into bounded phases, each phase must write its own artifacts, and the orchestrator must stop with `PASS_CONTINUATION_REQUIRED` before step exhaustion.

## 2. SessionState Schema

Every run must persist `session_state.json` with the following required keys:

```json
{
  "task_id": "string",
  "run_id": "string",
  "status": "PASS_PHASE_COMPLETE | PASS_CONTINUATION_REQUIRED | PASS_FINAL | BLOCKED_MODEL_ROUTING | BLOCKED_SUBAGENT_NOT_RUN | BLOCKED_MISSING_ARTIFACT | BLOCKED_MAX_STEPS_RISK | BLOCKED_CODE_BUG",
  "current_phase": "J0 | J1 | J2 | J3 | J4",
  "completed_phases": ["J0"],
  "pending_phases": ["J1", "J2", "J3", "J4"],
  "required_subagents": ["bet-scanner", "bet-scout", "bet-enricher", "bet-statistician", "bet-valuator", "bet-challenger", "bet-builder", "bet-test-engineer"],
  "completed_subagents": [],
  "artifact_manifest": {
    "phase_checkpoint": "reports/pipeline_runs/<run_id>/phase_checkpoint.md"
  },
  "omission_ledger_path": "reports/pipeline_runs/<run_id>/omission_ledger.json",
  "model_routing_status": "PASS | FAIL | UNVERIFIED",
  "next_resume_prompt": "string",
  "next_phase": "J1 | J2 | J3 | J4 | FINAL",
  "final_verdict_allowed": false
}
```

## 3. Allowed Statuses

- `PASS_PHASE_COMPLETE`
- `PASS_CONTINUATION_REQUIRED`
- `PASS_FINAL`
- `BLOCKED_MODEL_ROUTING`
- `BLOCKED_SUBAGENT_NOT_RUN`
- `BLOCKED_MISSING_ARTIFACT`
- `BLOCKED_MAX_STEPS_RISK`
- `BLOCKED_CODE_BUG`

## 4. Phase Budget Contract

The orchestrator must execute only the subagents listed for the active phase.

| Phase | Scope | Required Subagents | Required Phase Artifacts | Budget Rule |
| --- | --- | --- | --- | --- |
| `J0` | protocol repair and dry-run proof only | none | `orchestrated_session_max_steps_root_cause_review.md`, `orchestrated_session_continuation_protocol.md`, `orchestrated_session_continuation_protocol.json`, `session_state.json`, `phase_checkpoint.md`, `resume_prompt_next.md`, `artifact_manifest.json` | never run sports analysts |
| `J1` | scanner + scout only | `bet-scanner`, `bet-scout` | `scanner_event_universe.json`, `scout_tipster_opinion_layer.json`, updated manifest, checkpoint, resume prompt | must stop after J1 |
| `J2` | enricher + statistician only | `bet-enricher`, `bet-statistician` | `enricher_context_layer.json`, `statistician_market_analysis.json`, updated manifest, checkpoint, resume prompt | must stop after J2 |
| `J3` | valuator + challenger + builder only | `bet-valuator`, `bet-challenger`, `bet-builder` | `valuator_reference_odds_layer.json`, `challenger_adversarial_review.json`, `builder_package.json`, updated manifest, checkpoint, resume prompt | must stop after J3 |
| `J4` | test-engineer + final report only | `bet-test-engineer` | `package_quality_review.md`, `status_safety_review.md`, `omission_ledger.json`, final manifest, final checkpoint | only phase allowed to return `PASS_FINAL` |

## 5. Continuation Token

After J0, J1, J2, or J3, the orchestrator must return an exact continuation token in `session_state.json` and in the controller response. The minimum token is:

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
  "next_resume_prompt": "Resume phase J2 only. Read session_state.json, phase_checkpoint.md, artifact_manifest.json, and J1 artifacts. Run bet-enricher then bet-statistician. Do not run scanner, scout, valuator, challenger, builder, or test-engineer in this phase. If J2 artifacts are complete, write a new checkpoint and stop with PASS_CONTINUATION_REQUIRED.",
  "final_verdict_allowed": false
}
```

## 6. Resume Prompt Contract

When `pending_phases` is non-empty, `next_resume_prompt` is mandatory. The prompt must:

1. Name the exact next phase.
2. Name the exact files to read first.
3. Name the exact subagents allowed in that phase.
4. State which subagents are forbidden in that phase.
5. State the required output artifacts.
6. State the required terminal status.

## 7. Step-Exhaustion Guard

The orchestrator must not use remaining steps for extra review once the phase budget or artifact budget is at risk. If the session approaches its remaining budget before the phase is safely finalizable, it must write the checkpoint artifacts and stop with `PASS_CONTINUATION_REQUIRED` or `BLOCKED_MAX_STEPS_RISK`.

## 8. False PASS Prevention

Review-only or planning-only work must never return `PASS_FINAL`. A final pass is forbidden unless all conditions are true:

1. All required subagents ran.
2. All required artifacts for J1-J4 exist.
3. The omission ledger exists.
4. The cumulative subagent manifest covers all phases.
5. The quality gate passes.
6. `bet-test-engineer` verification exists.

If any condition is false, the run must return a blocked status instead of a final pass.

## 9. Phase Report Schema

Each phase must write a compact checkpoint report containing:

```text
TASK_ID=<task_id>
RUN_ID=<run_id>
STATUS=<status>
CURRENT_PHASE=<phase>
COMPLETED_PHASES=<json array>
PENDING_PHASES=<json array>
COMPLETED_SUBAGENTS=<json array>
REQUIRED_ARTIFACTS=<json array>
MISSING_ARTIFACTS=<json array>
NEXT_PHASE=<phase or FINAL>
NEXT_RESUME_PROMPT_PATH=<path or NONE>
FINAL_VERDICT_ALLOWED=true|false
```

## 10. Cumulative Manifest Rule

`orchestrator_subagent_manifest.json` is cumulative across phases. Each phase must append the subagents executed in that phase and preserve the earlier manifest entries rather than replacing them.
