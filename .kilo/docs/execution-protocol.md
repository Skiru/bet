# Agent Execution Protocol

## Universal Rules (ALL agents)
- Fish shell ONLY. `.venv/bin/python3` always.
- ALL scripts → `> /tmp/sN.txt 2>&1` then `tail -20`
- NEVER output raw terminal. Synthesize: "✅ S1 — 547 events, 5 sports"

## Turn Structure
1. `<think>` → "What do I need? Which 1 query?"
2. 1 data tool call (sqlite / bash / brave)
3. `<think>` → "What did I learn?"
4. 0-1 more tool calls max
5. SYNTHESIZE draft verdict per this agent's template
6. **VALIDATE** (MANDATORY for agents with ≥1 validation round — see execution-core.md budget):
   - Call `sequentialthinking_sequentialthinking`: "Given this draft, identify 3 specific weaknesses. For each, what MCP query would verify or refute it?"
   - Execute those queries (sqlite / brave)
   - Process output per Tool Output Protocol (tool-names.md)
   - If weaknesses confirmed → revise draft
7. **DELTA**: Summarize what changed during validation
8. **FINALIZE**: Emit final verdict with confidence score

## Verdict Template (all agents include confidence)
```
verdict: APPROVED | FLAGGED | REJECTED
confidence: HIGH | MEDIUM | LOW
validation_rounds: N
weaknesses_checked: [list]
delta: [what changed during validation]
metrics: [≥3 numbers from actual queries — each with source tag]
analysis: [2-3 sentences — what numbers MEAN]
```

## Domain Boundaries
- I query MY assigned tables. I do NOT query another agent's primary tables.
- **Exceptions**: bet-db-analyst queries ALL tables (cross-table integrity). bet-reconciler queries ANY table that resolves a domain conflict.
- If I need cross-domain data → ask the orchestrator to route a query.
- If data is missing → report it as FLAGGED. Never fabricate defaults.
- I do NOT recalculate another agent's metrics.

## Tool Output Protocol (CRITICAL)
Every tool call returns data. YOU MUST process it:
1. **SUCCESS**: Extract specific numbers, cite `[source: tool_name]` in verdict
2. **EMPTY** (0 rows, empty string): This is VALID data. Write "0" not "missing"
3. **FAILURE** (timeout, error): Note `[FAILED: tool, reason]`, try 1 alternative, then mark UNVERIFIED
4. **CONFIRMED**: Strengthen confidence, cite `[CONFIRMED: tool]`
5. **CONTRADICTED**: Downgrade confidence, revise hypothesis, cite `[CONTRADICTED: tool, delta]`
6. **UNEXPECTED FORMAT**: Parse what you can, flag as PARTIAL. Never hallucinate.

## Forbidden
- `python3 -c "..."`, `--help`, bare `python3` (no venv)
- List all items → AGGREGATE: "147 events in 5 sports"
- Continue past `S2=0 matched tips` without user confirmation
- Skip delegation after running a script
- Fabricate tool output data
