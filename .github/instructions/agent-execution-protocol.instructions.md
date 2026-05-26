---
applyTo: ".github/agents/bet-*.agent.md"
---

# Agent Execution Protocol v9

## ⛔ FISH SHELL — TERMINAL RULES

This project uses **fish shell**. The following are FORBIDDEN:

| ❌ NEVER | ✅ INSTEAD |
|----------|-----------|
| `python3 -c "..."` (ANY inline Python) | `pylanceRunCodeSnippet` |
| `for f in ...; do ...; done` | One command at a time |
| `$(command)` | Explicit values (e.g., `2026-05-11`) |
| Heredocs `<< EOF` | Write a temp .py file or use pylanceRunCodeSnippet |
| `export VAR=value` | `set -x VAR value` (fish syntax) |

---

## THE ONE RULE

> **If your response could be produced by piping terminal output to a file, you have FAILED.**
> Your response MUST contain YOUR ORIGINAL ANALYSIS — insights, patterns, anomalies that NO script can produce.

---

## BOOT SEQUENCE (first action every session)

Your FIRST action: `sequentialthinking` answering:
1. What are my 3 critical rules from the active agent or prompt?
2. What is my analytical value — what can I produce that a script cannot?
3. Which execution or data-flow lessons from past failures apply today?
4. **MANDATORY:** load `betting-mistakes-rules.instructions.md` when the current task involves S3, S5, S7, or S8 decisions.

---

## SELF-AUDIT (last action before returning)

Your LAST action: `sequentialthinking` verifying:
1. Did I follow my 3 rules? Evidence for each.
2. Does my output contain ≥3 specific metrics from the finished output or DB read?
3. Does my output contain ORIGINAL ANALYSIS (not restated numbers)?

---

## Python Environment

Before FIRST script: use `ms-python.python/configurePythonEnvironment` + `ms-python.python/getPythonExecutableCommand`. Cache and reuse.

---

## Tool Selection

| Need | Tool |
|------|------|
| Check JSON, read data, count records, query DB | `pylanceRunCodeSnippet` |
| Run ANY pipeline script | `run_in_terminal` with --verbose |
| NEVER | `python3 -c "..."` in terminal |

---

## Execution Pattern

Every analytical step follows this pattern:

```
1. INSPECT: use the cheapest available read to verify inputs exist and formats match.
2. RUN: if the active role is a direct operator, use `run_in_terminal` with `--verbose`; if the role is analysis-only, the orchestrator will supply finished output.
3. THINK: `sequentialthinking` → what does the output MEAN?
4. EXTRACT: parse `AGENT_SUMMARY:{json}` or key metrics from stdout.
5. VALIDATE: verify outputs exist and match the expected shape.
6. RETURN: structured verdict (see template below).
```

For scripts >120s: use `mode=async`. While waiting: sequentialthinking + pylanceRunCodeSnippet (review data, plan next step). Then `get_terminal_output`.

---

## Structured Verdict Template

ALL agents return this format. The orchestrator REJECTS responses without this structure.

````markdown
## Verdict: {script_name}

```subagent_verdict
verdict: APPROVED | FLAGGED | REJECTED
quality_score: 1-10
script: {script_name}
exit_code: {0|1|2}
execution_model: analysis-only
```

### Metrics
| Metric | Value | Assessment |
|--------|-------|------------|
| (≥3 rows with REAL numbers from output) |

### Anomalies
- (specific anomaly + root cause, or `None`)

### Analysis
(3-5 sentences — explain what numbers MEAN, not what they ARE)

### Impact
- (what downstream step should know)

### Issues
- (actionable items, or `None`)

### User Summary
(2-3 plain-language sentences for user presentation)

### Data For Orchestrator
- next_step_ready: (required)
- quality_flags: (required)
- focus_points: (required)
````

**Facts-only sections:** subagent_verdict, Metrics, Anomalies, Issues, Data For Orchestrator
**Reasoning sections:** Analysis, Impact, User Summary

---

## ⛔ BAD vs GOOD Output

### ❌ BAD (script runner):
```
The enrichment script completed successfully. 57 candidates were processed.
Data was enriched from multiple sources. The pipeline can proceed.
Verdict: APPROVED
```

### ✅ GOOD (analyst):
```
## Verdict: data_enrichment_agent.py

Metrics:
| Yield | 73% (42/57) | OK |
| Football | 24/28 (86%) | Strong |
| Hockey | 4/9 (44%) | WARNING — below threshold |

Analysis: Overall yield healthy at 73%. Hockey weakness is structural
(off-season), not a bug. 15 candidates with gaps will enter S3 as PARTIAL
and need conservative safety scoring. Football at 86% keeps core sport strong.

Data For Orchestrator:
- next_step_ready: 42 FULL + 15 PARTIAL
- quality_flags: hockey=PARTIAL, football=FULL
- focus_points: hockey caution in S3, preserve all candidates
```

**The difference:** GOOD separates facts from reasoning. BAD is vague prose.

---

## Anti-Patterns (ANY = failure)

| # | Pattern | Fix |
|---|---------|-----|
| 1 | Run script → return without reading output | Read FULL output. Cite ≥3 numbers. |
| 2 | Paste terminal output as "analysis" | Extract metrics. Write YOUR conclusions. |
| 3 | "Script completed successfully" | Say WHAT, HOW MUCH, WHAT QUALITY. |
| 4 | Skip sequentialthinking | MANDATORY before every verdict. |
| 5 | APPROVED without reasons | Cite specific metrics that justify it. |
| 6 | Ignore errors in output (404, 403, 0 results) | Triage EVERY error. |
| 7 | Run without `--verbose` | Always --verbose. |
| 8 | `python3 -c "..."` in terminal | Use pylanceRunCodeSnippet. Always. |
| 9 | Skip INSPECT (run without checking inputs) | pylanceRunCodeSnippet before EVERY script. |
| 10 | Skip VALIDATE (return without checking outputs) | pylanceRunCodeSnippet after EVERY script. |
| 11 | Summarize script's own summary as YOUR analysis | Add ORIGINAL INSIGHT the script didn't produce. |
| 12 | "Looks good, moving on" without delegation | ALWAYS delegate. See orchestrator R20. |

---

## Data Flow Verification (R18)

Before running script B after script A:
1. READ script A's output format (JSON keys, DB tables).
2. READ script B's input expectations.
3. VERIFY they match.
4. If mismatch → FIX before running B.

**Real failure:** `tipster_aggregator.py` saved under `"all_picks"` → `tipster_xref.py` read `"tips"` → 0 matches. Pipeline ran for DAYS broken because nobody READ THE CODE.

---

## AGENT_SUMMARY Parsing

After EVERY script, scan output for `AGENT_SUMMARY:{json}` line:
- If found: parse as authoritative metrics
- If not found: extract key numbers from verbose stdout (counts, rates, errors)

Exit codes: 0=OK, 1=partial, 2=critical.

---

## MCP Tools Available

- `brave-search/*` — Web search (2000 queries/month, ~60/day)
- `sqlite/*` — Direct DB queries (READ only — use scripts for writes)
- `pylanceRunCodeSnippet` — Run Python code (data inspection, format checks)
- `browser/*`, `playwright/*` — Web page interaction
- `sequential-thinking/*` — Structured reasoning

## Scope Boundary

This protocol owns always-on execution behavior only. It does not own:
- workflow phase order
- script inventories
- prompt routing matrices
- delegated handoff contracts
- domain methodology summaries
- project constitution or memory policy

Those concerns belong to prompts, the workflow skill, domain instructions, or the root constitution.

---

## Adapter Reference (2026-05-12 overhaul)

| Sport | Primary Stats Source | Notes |
|-------|---------------------|-------|
| Hockey | MoneyPuck (xG%, Corsi%, Fenwick%) | NaturalStatTrick BLOCKED (403) |
| Tennis | TennisAbstract Elo + ATP Tour | Paired-row parser overhauled |
| Basketball | Basketball-Reference | BallDontLie DISABLED |
| Volleyball | Flashscore volleyball adapter | Deep stats enrichment improved |
| Football | Soccerway + SoccerStats + WhoScored + Covers + Forebet | 5 adapters enhanced |

**Disabled:** TheSportsDB, BallDontLie, API-Tennis.
**New:** BetExplorerClient, OddsPortalClient, TotalCornerClient, Scores24Client, SoccerwayClient.

<!-- BET:instruction:agent-execution-protocol:v8 -->
