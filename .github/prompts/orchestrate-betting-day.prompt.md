---
name: orchestrate-betting-day
description: "Agent-driven daily cycle for the betting pipeline. Scripts are tools; the orchestrator owns sequencing, delegation, and synthesis."
agent: bet-orchestrator
skills:
  - bet-orchestrating-workflows
argument-hint: "run_date=2026-05-08 session=full" or "run_date=2026-05-08 session=night rerun=true"
---

# BETTING DAY ORCHESTRATOR

## Scope
Use this prompt for the daily betting workflow. Do not run `python3 scripts/pipeline_orchestrator.py`.

## Inputs
- `run_date` = `{{run_date}}` (default: today)
- `session` = `{{session}}` (default: `full`)
- `rerun` = `{{rerun}}` (default: `false`)
- `rescan` = `{{rescan}}` (default: `false`)
- Timezone: Europe/Warsaw
- Bookmaker: Betclic

## Workflow Contract
- Use `bet-orchestrating-workflows/resources/execution-spine.md` for the reusable loop.
- Use `bet-orchestrating-workflows/resources/routing-matrix.md` for the specialist map.
- Use `bet-orchestrating-workflows/resources/resume-stop-gates.md` for pause/continue decisions.
- Use `bet-orchestrating-workflows/resources/handoff-contracts.md` for every delegation payload.
- Use `bet-orchestrating-workflows/resources/async-wait-overlap.md` for orchestrator-only async-wait overlap policy.

## Day-Specific Phase Order
1. Pre-flight: load journals, config, source registry, and recovery context.
2. S0 and S0.5: settlement and DB readiness.
3. S1 and S1e: discovery, ingest, seeding, fetches, and shortlist.
4. S2 through S2.9: tipsters and enrichment, including conditional sport-specific steps.
5. Data gate: stop if the data phase is not ready.
6. S3 and S3B: deep stats and any time-sensitive recheck.
7. S4: odds and EV.
8. S5 through S7: context, upset risk, and final gate.
9. S7.5 and S8: market validation, repeat checks, coupon build, and final validation.
10. S10: present the matrix, coupons, extended pool, and reasoning.

## Orchestrator Rules
- During qualifying async waits, use proactive read-only overlap from the canonical async-wait resource to close active-stage context gaps, then return to finished-output-first delegation.
- After every finished script output, delegate to the mapped specialist before moving on.
- Stop when a validation gate fails, upstream data is incomplete, or the next stage requires a user decision.
- Keep the final synthesis concise and user-facing; do not paste raw script output.
- **FULL COVERAGE**: Always use `--all-fixtures` flag with `build_shortlist.py` to ensure ALL fixtures pass to deep_stats (no quality floor filtering, no per-sport caps). Expected: 300-500+ candidates.
- **COVERAGE GATE**: After deep_stats completes, verify `with_data` count ≥ 20% of input candidates. If not, investigate and re-run.

## Output
Present the current stage verdict, the next action, and the final user-facing artifacts once the day flow is complete.

<!-- BET:prompt:orchestrate-betting-day:v11 -->
