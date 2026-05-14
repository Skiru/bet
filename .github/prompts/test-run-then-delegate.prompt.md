---
mode: bet-orchestrator
description: "Test Run-Then-Delegate (Model A) on the enrichment step"
---

## Test: Run-Then-Delegate (Model A) — Enrichment Step

Run the enrichment pipeline step (S2.5) for 2026-05-14 using the NEW Model A execution protocol.

### Instructions

1. **YOU (orchestrator) run the script:**
   ```
   PYTHONPATH=src .venv/bin/python3 scripts/data_enrichment_agent.py --date 2026-05-14 --news --verbose
   ```
   Use `mode=async`. While it runs, use `sequentialthinking` to analyze the existing shortlist quality from `betting/data/2026-05-14_s2_shortlist.json`.

2. **Monitor with `get_terminal_output`** — react immediately to 404/403/timeout errors. Extract the `AGENT_SUMMARY:{json}` block when done.

3. **Delegate ANALYSIS ONLY to bet-enricher subagent** — pass the AGENT_SUMMARY + relevant log excerpts. The subagent must NOT run any script. It returns a Model A verdict with `execution_model: analysis-only`.

4. **Apply 5-question quality gate** on the subagent's verdict, then present results.

### What This Tests

- Orchestrator runs the script (not the subagent) — the core Model A change
- `sequentialthinking` during async wait (THINK-WHILE-WAITING)
- Error monitoring via `get_terminal_output`
- Subagent receives finished output only — returns `execution_model: analysis-only` verdict
- 5-question quality gate enforcement

Follow R1, R17, R18 from `agent-execution-protocol.instructions.md` strictly.
