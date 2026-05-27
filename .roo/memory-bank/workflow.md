# Workflow Notes

## Pipeline Operation
- Roo Code orchestrator (bet-orchestrator mode) delegates to specialist modes via Boomerang.
- Scripts produce data; modes interpret output and return structured verdicts.
- DB-first storage is default. JSON is fallback/debug layer.
- Each mode gets a fresh context window (Boomerang sub-tasks).

## Active Surface
- Discovery, stats, odds, gate, and coupon steps in `scripts/` and `src/bet/`.
- `betting/data/agent_reviews/` stores per-step review inputs and outputs.
- Statistical markets are the preferred analysis lane across all sports.

## Session Pattern
- Settlement → Scan → Enrich → Analyze → Gate → Build → Validate → Present
- Each step: run script → delegate to specialist mode → receive verdict → proceed
