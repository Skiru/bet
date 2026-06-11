# Betting Pipeline — Production Agent Rules

## Runtime contract

- Inference: **Rapid-MLX 0.7.0**, `qwen3.6-35b-4bit`, `http://127.0.0.1:8000/v1`.
- Kilo model budget: **28,672 total / 24,576 input / 4,096 output**.
- Hardware target: Apple M4 Pro with 48 GB unified memory.
- Text only. Do not enable vision, DFlash, MTP or experimental speculative decoding in the production profile.
- Bash launcher scripts are valid because they have a Bash shebang; they may be invoked from Fish.

## Phase-bounded orchestration

Run one phase group per Kilo session:

| Phase | Pipeline scope | Mandatory exit artifact |
|---|---|---|
| A | S0 settlement and historical learning | `.kilo/state/phase-A-handoff.md` |
| B | S1–S1e discovery and shortlist | `.kilo/state/phase-B-handoff.md` |
| C | S2 tipster aggregation | `.kilo/state/phase-C-handoff.md` |
| D | S2.3–S7 enrichment, analysis and gates | `.kilo/state/phase-D-handoff.md` |
| E | S8–S10 construction and final validation | `.kilo/state/phase-E-handoff.md` |

Do not run A→E inside one raw chat history. Start the next phase in a new session with only the latest handoff and exact artifacts required by that phase.

## Mandatory delegation

- S0: `bet-settler` and `bet-db-analyst`.
- S1e: `bet-scanner`.
- S2: `bet-scout`; zero valid tips is a hard stop.
- S3–S5: `bet-statistician` and `bet-valuator`.
- S7: `bet-challenger`.
- S8: `bet-builder`.
- Script failure after two bounded attempts: `bet-engineer`.
- Conflicting evidence: `bet-reconciler`.
- Before phase completion: `bet-test-engineer`.

Never run multiple LLM subagents concurrently against the single local 35B server.

## Context safety

- Do not request or expose private chain-of-thought, `<think>` blocks or sequential-thinking tool traces.
- Return concise evidence, calculations, decisions and uncertainty instead.
- Do not use the sequential-thinking MCP server.
- A tool result must be at most 12 KiB in the chat history. Store larger output under `.kilo/artifacts/` and return a compact summary plus path.
- Terminal commands must redirect verbose output to an artifact and show only the relevant tail or filtered lines.
- A subagent handoff must be under 1,200 tokens and contain: status, evidence paths, decisions, unresolved risks and next action.
- After every phase, update `.kilo/state/CURRENT_HANDOFF.md` and the phase-specific handoff.
- Run `/compact` before a major transition inside a phase; never wait for overflow.

## Data and safety

- Use only the project custom tool `bet_sqlite_query` for direct database reads. It is read-only and bounded. Mutations go through reviewed repository scripts and tests.
- Every factual betting claim must be traceable to DB rows, generated artifacts or current external sources.
- Never invent odds, injuries, fixtures, lineups or statistics.
- All picks remain conditional until the user verifies market and odds in Betclic.
- Never store credentials in scripts, prompts, logs or artifacts.
- Maximum two retries for the same failing operation; then change strategy or delegate.
