# Betting Agent Anti-Loop And Step Budget Contract Artifact

- Checklist cap: 5 items.
- Inspection cap before first action: 3 unless audit-only.
- Failure retry cap: 2 attempts.
- After repeated failure: change strategy or escalate.
- Tool unavailable: stop with blocker.
- Step-budget risk: write checkpoint and resume-ready next action.
- No review forever.
- No recursive delegation.
- No false PASS from partial phase.
- No phase PASS without required artifacts.
- Long sessions require checkpoints.
- Outputs stay concise and schema-bound.
