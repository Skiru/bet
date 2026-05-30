---
applyTo: ".github/agents/bet-*.agent.md"
---

# Agent Execution Protocol v11

## Terminal: Fish Shell

No inline Python (`python3 -c "..."`), no bash syntax, no `export`. Use `set -x VAR value` for env vars.
Always use `.venv/bin/python3` — never bare `python3`.

---

## MCP Tools

| Tool | When |
|------|------|
| `sequentialthinking_sequentialthinking` | Complex decisions (≥3 factors), when stuck |
| `sqlite_read_query` | DB stats, row counts, verification |
| `sqlite_write_query` | DB fixes (DELETE orphans, UPDATE flags) |
| `brave-search_brave_web_search` | Live context when DB lacks data |

- DB operations → use sqlite MCP tools (NOT inline `python3 -c`)
- Complex fixes → write `/tmp/fix.py`, then run it
- NEVER use `python3 -c "..."` — quoting breaks in fish
- DB → scraper files → brave-search (fallback order)
- NEVER return "insufficient data" without trying all three

---

## THE ONE RULE

> Your response MUST contain ORIGINAL ANALYSIS with specific metrics — not paraphrased script output.

---

## NARRATE (visibility for user)

- FIRST thing in every response: 1-line status of what you found/what you're doing next.
- MAX 3 tool calls per turn. If you need more, respond with partial findings first, then continue.
- NEVER go silent for >60 seconds. If a query takes time, narrate BEFORE calling it.
- Every response MUST have user-visible text (even if it's just "Querying L10 values for 12 teams...").

---

## IF STUCK

1. Call `sequentialthinking_sequentialthinking`: "What am I trying to do? What failed? 3 options?"
2. Pick simplest action. Never repeat same failed approach.

---

## Execution Pattern

1. Verify inputs exist (sqlite or ls)
2. Run script: `.venv/bin/python3 scripts/{name}.py`
3. Extract `AGENT_SUMMARY:{json}` metrics from output
4. Verify outputs were written
5. Return verdict with metrics

---

## Verdict Format (subagents)

```
verdict: APPROVED | FLAGGED | REJECTED
Metrics: (≥3 specific numbers from output)
Analysis: (what numbers MEAN, 2-3 sentences)
Impact: (what downstream step needs to know)
```

---

## BAD vs GOOD

❌ `"Script completed. 57 candidates. APPROVED."`
✅ `"Yield 73% (42/57). Football 86% strong. Hockey 44% WARNING — off-season gap."`

<!-- BET:instruction:agent-execution-protocol:v11 -->
