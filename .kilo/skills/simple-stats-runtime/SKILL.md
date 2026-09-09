---
name: simple-stats-runtime
description: Runtime contract and operational execution rules for the simple_stats betting pipeline (DISCOVER -> SUPERBET -> ENRICH -> MARKET_CONTEXT -> TIPSTERS -> ANALYZE) and the bet-simple agent.
---

# Simple Stats Runtime Skill Contract

This skill defines the runtime boundaries, execution sequence, and contract verification rules for the `simple_stats` daily pipeline in Kilo.

## Execution Sequence

The pipeline executes through a unified entrypoint with one deterministic `run_id`:

```bash
python3 scripts/simple/run_pipeline.py --preflight
python3 scripts/simple/run_pipeline.py --date <YYYY-MM-DD> -v
```

1. **DISCOVER**: Sources raw fixtures across active sports (football: bzzoiro; tennis: espn/tennis-abstract).
2. **SUPERBET**: Reads Superbet operator screen to establish active slate gating and available markets.
3. **ENRICH**: Enriches gated fixtures with historical samples and head-to-head statistics.
4. **MARKET_CONTEXT**: Evaluates market pricing and model context (football-only).
5. **TIPSTERS**: Ingests and normalizes tipster opinions without arbitrary weighting.
6. **ANALYZE**: Generates the statistical candidate sheet (`<date>_event_dossiers_stats_sheet.json`).
7. **FORECAST / COMPARISON**: Re-reads sheet and dossiers deterministically via `build_forecast.py`.

## Core Constraints

- **Single Source of Truth**: All artifacts reside under `runs/<date>/`.
- **Zero Hallucination**: No synthetic odds, no invented fixtures, no fake consensus.
- **Fail-Closed Verification**: Check `--preflight` first; never run uncorroborated pipelines if quota is zero.
- **Human Gate S9**: The final output is an analytical sheet for the operator; the agent does not place bets or execute coupons directly.
