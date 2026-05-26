# Repo Workflow Notes

## Workflow Facts
- Copilot is the orchestrator and delegates analysis to specialist agents.
- Scripts produce data; agents interpret finished output.
- The agent-driven pipeline uses the stage scripts, not `pipeline_orchestrator.py`.
- DB-first storage is the default across the pipeline; JSON is the fallback/debug layer.

## Active Surface
- Discovery, stats, odds, gate, and coupon steps all live in the existing `scripts/` and `src/bet/` structure.
- `betting/data/agent_reviews/` stores per-step review inputs and outputs.
- Statistical markets remain the preferred analysis lane across sports.
