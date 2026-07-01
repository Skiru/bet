# Orchestrated Session Continuation Protocol Contract

This artifact is the repo-owned operational summary of the continuation contract.

## SessionState Required Keys

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

## Allowed Statuses

- `PASS_PHASE_COMPLETE`
- `PASS_CONTINUATION_REQUIRED`
- `PASS_FINAL`
- `BLOCKED_MODEL_ROUTING`
- `BLOCKED_SUBAGENT_NOT_RUN`
- `BLOCKED_MISSING_ARTIFACT`
- `BLOCKED_MAX_STEPS_RISK`
- `BLOCKED_CODE_BUG`

## Phase Budgets

- `J0`: protocol repair and dry-run proof only
- `J1`: scanner + scout only
- `J2`: enricher + statistician only
- `J3`: valuator + challenger + builder only
- `J4`: test-engineer + final report only

## Final Pass Gate

`PASS_FINAL` is forbidden unless all required subagents ran, all required artifacts exist, the omission ledger exists, the cumulative subagent manifest exists, and test-engineer verification exists.

## Continuation Gate

When phases remain pending, the run must return `PASS_CONTINUATION_REQUIRED` and write `resume_prompt_next.md` containing the exact next-phase instructions.
