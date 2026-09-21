# Betting Agent Anti-Loop and Step Budget Contract

## Core Rules

- Every betting agent starts with a checklist of at most 5 items.
- No more than 3 read-only inspections before the first action unless the task is explicitly audit-only.
- No more than 2 attempts per failing operation.
- After repeated failure, the agent must change strategy or escalate.
- If a required tool is unavailable, the agent stops with a blocker instead of improvising.
- If max-step risk appears, the agent writes a checkpoint and returns a resume-ready next action.
- No agent may review forever.
- No recursive subagent delegation is allowed.
- No final PASS from a partial phase.
- No phase PASS without all required artifacts.
- Long sessions must be checkpointed.
- Outputs must stay concise and schema-bound.

## Enforcement Targets

- Prompts must include retry limits, hard stops, continuation rules, and exact final response schemas.
- Audits and tests must fail when omission gates, continuation gates, or artifact gates are missing.
