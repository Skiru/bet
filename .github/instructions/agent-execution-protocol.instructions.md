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
| `sequentialthinking_sequentialthinking` | **FIRST call of EVERY turn** — classify request, plan queries |
| `sqlite_read_query` | DB stats, row counts, verification — MAX 2 per turn without narrating |
| `sqlite_write_query` | DB fixes (DELETE orphans, UPDATE flags) |
| `brave-search_brave_web_search` | Live context when DB lacks data |

- **MANDATORY SEQUENCE: think → query (1-2 max) → narrate → (continue if needed)**
- **TOOL BUDGET: 1 sequentialthinking + 2 data tools = 3 total per turn.** After 3 → STOP, narrate, continue next turn.
- NEVER open a turn with `sqlite_read_query` or `sqlite_list_tables` — think FIRST
- DB operations → use sqlite MCP tools (NOT inline `python3 -c`)
- Complex fixes → write `/tmp/fix.py`, then run it
- NEVER use `python3 -c "..."` — quoting breaks in fish
- DB → scraper files → brave-search (fallback order)
- NEVER return "insufficient data" without trying all three
- **ERROR RECOVERY**: If a tool call returns error → DO NOT retry blindly. Call `sequentialthinking` to diagnose: "Why did it fail? Wrong table? Bad SQL? Simplify."

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

---

## STOP SIGNAL (subagents — MANDATORY)

When you've produced your verdict template → **STOP GENERATING.** Do not:
- Explain what you did (the verdict shows it)
- Offer "next steps" or "recommendations for the orchestrator"
- Repeat the template in different words
- Add filler like "Let me know if you need anything else"

Fill your Verdict Template → final sentence of analysis → **END.**

---

## SUBAGENT SCOPE

Subagents do NOT have `task` or `todowrite` tools. Ignore any references to them.
Your only tools: `sequentialthinking`, `sqlite_*`, `brave-search_*`, `read`, `write`, `edit`, `bash`, `glob`, `grep`.

<!-- BET:instruction:agent-execution-protocol:v12 -->
