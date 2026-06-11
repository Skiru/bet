# Execution Core — Subagent Protocol

## Core Pattern (8 steps)

**THINK → ACT → REASON → ACT → SYNTHESIZE (draft) → VALIDATE → DELTA → FINALIZE**

1. **THINK**: What do I need? What's my hypothesis?
2. **ACT**: Gather data with READONLY tools (`sqlite_read_query` first for internal facts, then `webfetch` / brave for external confirmation, then `read` for local artifacts).
3. **REASON**: Interpret data using `sequentialthinking_sequentialthinking` for complex deductions BEFORE drafting any verdict.
4. **ACT**: Gather additional data if needed.
5. **SYNTHESIZE (draft)**: Write preliminary verdict per this agent's template.
6. **VALIDATE** (MANDATORY for agents with ≥1 validation round):
   - Call `sequentialthinking_sequentialthinking`: "Given this verdict, identify 3 specific reasons it could be wrong."
   - For each reason, call `sqlite_read_query` or `brave-search_brave_web_search` to verify or refute.
   - Follow the Tool Output Protocol (tool-names.md) for every tool result.
7. **DELTA**: Produce revision summary — what changed after validation, what stayed, what remains unresolved.
8. **FINALIZE**: Emit final verdict with `confidence` score.

## 3-Phase Structure (all analysis agents)

| Phase | Action | MCP Tools | Output |
|-------|--------|-----------|--------|
| **GATHER** | Collect raw data from DB/web | `sqlite_read_query`, `webfetch`, `brave-search_*`, `read` | Raw metrics |
| **ANALYZE** | Interpret data, form hypothesis | `sequentialthinking_sequentialthinking`, `sqlite_read_query`, `webfetch` | Draft verdict |
| **VALIDATE** | Cross-check own output | `sequentialthinking_sequentialthinking`, `sqlite_read_query`, `webfetch`, `brave-search_*` | Delta + Final verdict |

Each phase = its own THINK→ACT→REASON sub-cycle within the 8-step pattern.

## Recursion Budget (per agent)

| Agent | Gather | Analyze | Validate | Max Total |
|-------|--------|---------|----------|-----------|
| bet-statistician | 2 | 3 | 2 | 7 |
| bet-challenger | 2 | 3 | 2 | 7 |
| bet-valuator | 2 | 2 | 1 | 5 |
| bet-scout | 2 | 1 | 2 | 5 |
| bet-builder | 2 | 2 | 2 | 6 |
| bet-scanner | 2 | 2 | 0 | 4 |
| bet-enricher | 2 | 2 | 0 | 4 |
| bet-settler | 2 | 1 | 0 | 3 |
| bet-engineer | 2 | 3 | 0 | 5 |
| bet-db-analyst | 2 | 1 | 0 | 3 |
| bet-orchestrator | 3 | 3 | 0 | 6 |

Validation rounds: if validation finds ≥2 confirmed weaknesses in round 1, proceed to round 2. Otherwise finalize after round 1. Each round = 1 sequentialthinking call + 1-2 verification queries.

## Per-Agent Tool Map

| Agent | GATHER tools | ANALYZE tools | VALIDATE tools |
|-------|-------------|---------------|----------------|
| bet-statistician | `sqlite_read_query`, `webfetch`, `brave-search_brave_web_search` | `sequentialthinking_sequentialthinking`, `sqlite_read_query` | `sequentialthinking_sequentialthinking`, `sqlite_read_query`, `webfetch` |
| bet-challenger | `sqlite_read_query`, `brave-search_brave_web_search`, `webfetch` | `sequentialthinking_sequentialthinking` | `sequentialthinking_sequentialthinking`, `sqlite_read_query`, `webfetch`, `brave-search_brave_news_search` |
| bet-valuator | `sqlite_read_query`, `webfetch`, `brave-search_brave_web_search` | `sequentialthinking_sequentialthinking`, `sqlite_read_query` | `sequentialthinking_sequentialthinking`, `webfetch`, `brave-search_brave_news_search` |
| bet-scout | `sqlite_read_query`, `brave-search_brave_web_search` | — | `sqlite_read_query` |
| bet-builder | `sqlite_read_query`, `read`, `webfetch` | `sequentialthinking_sequentialthinking`, `sqlite_read_query` | `sequentialthinking_sequentialthinking`, `sqlite_read_query`, `webfetch` |
| bet-scanner | `sqlite_read_query`, `brave-search_brave_web_search` | — | — |
| bet-enricher | `sqlite_read_query` | `sequentialthinking_sequentialthinking` | — |
| bet-settler | `sqlite_read_query`, `webfetch`, `brave-search_brave_web_search` | `sequentialthinking_sequentialthinking` | `sequentialthinking_sequentialthinking`, `sqlite_read_query` |
| bet-engineer | `read`, `bash` | `sequentialthinking_sequentialthinking` | `bash` (re-run) |
| bet-db-analyst | `sqlite_read_query` | — | — |
| bet-reconciler | `sqlite_read_query` | `sequentialthinking_sequentialthinking` | — |
| bet-orchestrator | `read`, `sqlite_read_query`, `webfetch`, `bash` | `sequentialthinking_sequentialthinking` | `sequentialthinking_sequentialthinking`, `sqlite_read_query` |

## Tool Output Protocol

Every tool call result MUST be processed per the Tool Output Protocol in tool-names.md:
- SUCCESS → extract numbers, cite source
- EMPTY → treat as ZERO, not ERROR
- FAILURE → try 1 alternative, then mark UNVERIFIED
- CONFIRMED/CONTRADICTED → update confidence accordingly

## ❌ No data dumps
- Never fire >2 tools without `<think>` between.
- "Get all data first" = drift. Stay hypothesis-driven.
- Every stat needs a query behind it this session.
- Can't say WHY you need next query → STOP, go to ANALYZE.
- Output: verdict with ≥3 numbers from actual queries + confidence.

## Behavioral Guardrails
- Find MECHANISMS: "Safety=0.72" is data. "L5 fouls drop 30% in dead rubbers" is insight.
- Source fusion: ≥2 of {DB stats, web context, tipster} per STRONG verdict.
- Cite-or-Delete: every number without a DB/file query = hallucination.
- **EMPTY RESULT protocol**: If a GATHER query returns 0 rows → treat as ZERO data (not an error). Flag the candidate/sport/table with `[NO_DATA: query]` and evaluate whether downstream agents can still work. If ALL candidates in scope return 0 rows → STOP, mark verdict INCOMPLETE, report back to orchestrator. NEVER fabricate defaults.

## State Ownership
- **Orchestrator** owns the pipeline checkpoint (current step, step status, delegation results).
- **Each subagent** returns an independent verdict — orchestrator merges.
- After every step, orchestrator writes to `.kilocode/memory/session-state.md`:
  1. Current step + status
  2. Key metrics from script output
  3. Agent verdict summaries
- Before any decision, orchestrator reads session-state.md for context.

## Domain Boundary Exceptions
- **bet-db-analyst**: May query ALL tables (cross-table integrity checker). All other agents query only their assigned tables.
- **bet-reconciler**: May query ANY table that could resolve a domain conflict. All other agents stay within domain boundaries.
