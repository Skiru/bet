# V4 Protocol: THINK-WHILE-WAITING Async Pattern

## Status: SHIPPED (2026-05-11)

### What Changed (17 files)

**Core protocol:**
- `agent-execution-protocol.instructions.md` → v3→v4: dual-mode (sync ≤120s, async ≥300s), THINK-WHILE-WAITING, per-agent productive work table, BAD/GOOD examples
- `copilot-instructions.md` → R17 rewritten with async pattern
- `orchestrate-betting-day.prompt.md` → 3 stale mode=sync references fixed

**All 13 specialist agents updated:**
- bet-scanner, bet-enricher, bet-statistician, bet-challenger, bet-valuator, bet-scout, bet-builder, bet-settler → scripts ≥300s changed to mode=async with agent-specific THINK-WHILE-WAITING guidance
- bet-scanner-football, bet-scanner-tennis, bet-scanner-hockey, bet-scanner-volleyball, bet-scanner-basketball → timeout tables updated with Mode column
- bet-db-analyst → no change (all queries fast ≤120s)
- bet-orchestrator → script table with Mode column, banned patterns updated

### Key Design: Per-Agent THINK-WHILE-WAITING

| Agent | Long Script(s) | What to do during wait |
|-------|----------------|------------------------|
| bet-scanner | scan_events (600s) | Query DB for source health, check fixture counts |
| bet-enricher | data_enrichment_agent (600s) | Read shortlist, check team form data in DB |
| bet-statistician | deep_stats_report (600s) | Review enrichment quality, pre-load sport protocols |
| bet-challenger | context/upset/gate (300s each) | Review deep stats, draft bear cases |
| bet-valuator | odds_evaluator (300s) | Read S3 stats, pre-load safety scores |
| bet-scout | tipster_aggregator (300s) | Read scan results, check pre-fetched HTML |
| bet-builder | coupon_builder (300s) | Review gate results, check bankroll config |
| bet-settler | settle_on_finish (300s) | Read coupon files, review Betclic history |

### Validation
- Needs a FRESH session to pick up changes (workspace-level copilot-instructions.md loaded at session start)
- First real pipeline run IS the validation
- If agents still idle → add sharper examples (per instruction-design-lessons)

---

## FUTURE: Hybrid Event Loop (NOT YET IMPLEMENTED)

User chose "Skip — v4 is enough for now" on 2026-05-11.

### Concept
Orchestrator launches Phase 1 scripts (scan + tipsters + API + odds) ALL simultaneously in async mode, monitors them in an event loop, and delegates ANALYSIS to subagents when each finishes.

### Pipeline Parallelism Map
```
PHASE 1: PARALLEL DATA COLLECTION (~20 min vs ~40 min sequential)
├── scan_events.py (10-20 min)     ─┐
├── tipster_aggregator.py (5 min)   ├── ALL launch simultaneously
├── fetch_api_stats.py (5 min)      │   Orchestrator monitors event loop
└── fetch_odds_api.py (2 min)      ─┘

PHASE 2+: Current subagent model with v4 async
```

### Platform Constraint
`runSubagent` is SYNCHRONOUS — orchestrator blocks while subagent works. To parallelize, orchestrator must own script execution and delegate only analysis.

### When to implement
After v4 is validated in real pipeline runs and if agents still show significant idle time.

---

## OBSERVED ISSUE: S3 Terminal Command Failures (2026-05-11)

Agents running complex inline Python (`python3 -c "..."`) with heavy quoting → commands get garbled → `i...` output → wasted turns.

### Fix needed
Add to protocol: "Use `read_file` for JSON inspection, use heredocs for complex Python, avoid `-c` with nested quotes."
