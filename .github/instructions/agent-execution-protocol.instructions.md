---
applyTo: ".github/agents/bet-*.agent.md"
---

# Agent Execution Protocol v9

## Terminal: Fish Shell

No inline Python (`python3 -c "..."`), no bash loops, no heredocs, no `export`. Use `pylanceRunCodeSnippet` for data checks, `run_in_terminal` for scripts, `set -x VAR value` for env vars.

---

## THE ONE RULE

> If your response could be produced by piping terminal output to a file, you have FAILED.
> Your response MUST contain ORIGINAL ANALYSIS — insights, patterns, anomalies that NO script can produce.

---

## BOOT SEQUENCE (first action)

`sequentialthinking` answering:
1. What are MY 3 critical rules? (from agent.md)
2. What is my analytical value — what can I produce that a script cannot?
3. What lessons from pipeline-errors journal apply today?
4. Read `betting-mistakes-rules.instructions.md` — apply HARD REJECT rules to EVERY candidate.

## SELF-AUDIT (last action)

`sequentialthinking` verifying:
1. Did I follow my 3 rules? Evidence for each.
2. Does my output contain ≥3 specific metrics?
3. Does my output contain ORIGINAL ANALYSIS?

---

## Execution Pattern

```
INSPECT → RUN → THINK → EXTRACT → VALIDATE → RETURN
```

1. `pylanceRunCodeSnippet` — verify inputs exist
2. `run_in_terminal --verbose` — run script (async if >120s)
3. `sequentialthinking` — what does output MEAN?
4. Parse `AGENT_SUMMARY:{json}` or extract key metrics
5. `pylanceRunCodeSnippet` — verify outputs exist
6. Return structured verdict

Python env: `configurePythonEnvironment` + `getPythonExecutableCommand` before first script.

---

## Structured Verdict Template

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
| (≥3 rows with REAL numbers) |

### Anomalies
- (specific anomaly + root cause, or `None`)

### Analysis
(3-5 sentences — what numbers MEAN, not what they ARE)

### Impact
- (what downstream step should know)

### Issues
- (actionable items, or `None`)

### User Summary
(2-3 plain-language sentences)

### Data For Orchestrator
- next_step_ready: (required)
- quality_flags: (required)
- focus_points: (required)
````

---

## BAD vs GOOD Output

❌ BAD: `"The enrichment script completed successfully. 57 candidates. Pipeline can proceed. APPROVED."`

✅ GOOD:
```
Metrics: Yield 73% (42/57). Football 24/28 (86%) Strong. Hockey 4/9 (44%) WARNING.
Analysis: Hockey weakness is structural (off-season), not a bug. 15 PARTIAL
candidates need conservative safety scoring. Football keeps core strong at 86%.
Data: next_step_ready: 42 FULL + 15 PARTIAL. quality_flags: hockey=PARTIAL.
```

---

## Data Flow Verification (R18)

Before running script B after script A: verify output format of A matches input expectations of B. Read code, check JSON keys and DB tables.

---

## Anti-Patterns (ANY = failure)

1. Return without reading full output
2. Paste terminal output as "analysis"
3. Skip `sequentialthinking`
4. APPROVED without citing metrics
5. Ignore errors (404, 403, 0 results)
6. `python3 -c "..."` in terminal
7. Run without `--verbose`
8. Skip INSPECT/VALIDATE steps
9. "Looks good" without delegation

<!-- BET:instruction:agent-execution-protocol:v9 -->
