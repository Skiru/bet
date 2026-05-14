# Agent Protocol & Configuration — Current State

## Protocol Version: v6 (2026-05-13)

### 6-Step Cycle (per pipeline step)
1. **INSPECT**: Use `pylanceRunCodeSnippet` to verify input data BEFORE running script
2. **RUN**: Always `mode=async` for scripts >120s, `mode=sync` for <120s
3. **THINK**: `sequentialthinking` while script runs (analyze previous step data)
4. **ANALYZE**: Parse `AGENT_SUMMARY:{json}` line, extract metrics
5. **VALIDATE**: Use `pylanceRunCodeSnippet` to verify output data
6. **VERDICT**: Cite specific numbers, provide original insight

### Tool Selection
- `pylanceRunCodeSnippet` = PRIMARY for data inspection (DB queries, JSON reads)
- `run_in_terminal mode=sync` = scripts <120s
- `run_in_terminal mode=async` = scripts >120s → THINK-WHILE-WAITING

### Per-Agent THINK-WHILE-WAITING Work
| Agent | Long Script | What to do during wait |
|-------|-------------|----------------------|
| bet-scanner | scan_events (600s) | Query DB for source health, check fixture counts |
| bet-enricher | data_enrichment_agent (600s) | Read shortlist, check team form data |
| bet-statistician | deep_stats_report (600s) | Review enrichment quality, pre-load sport protocols |
| bet-challenger | context/upset/gate (300s each) | Review deep stats, draft bear cases |
| bet-valuator | odds_evaluator (300s) | Read S3 stats, pre-load safety scores |
| bet-scout | tipster_aggregator (300s) | Read scan results, check pre-fetched HTML |
| bet-builder | coupon_builder (300s) | Review gate results, check bankroll config |
| bet-settler | settle_on_finish (300s) | Read coupon files, review Betclic history |

## Python Tool IDs for Agents
All 10 agents include:
- `ms-python.python/configurePythonEnvironment`
- `ms-python.python/getPythonExecutableCommand`
- `ms-python.python/getPythonEnvironmentInfo`
- `ms-python.python/installPythonPackage`

## MCP Sequential Thinking
All agents have `sequential-thinking/sequentialthinking` (canonical ID with hyphen).

## AI Config Audit Summary (2026-05-13)
- 27 tasks across 5 phases, ~30 files modified
- All `.venv/bin/python` → `python3` (39 occurrences)
- Removed broken skill references, phantom agent references
- Standardized PYTHONPATH handling
- Added `playwright/*` MCP tools to challenger, valuator, scanner
- Removed duplicate `sequentialthinking` from 9 agent tool arrays
- All verified via `scripts/_verify_ai_audit.py` (14 checks passing)

## Structured Script Output Protocol
15 scripts support `--verbose` + `AGENT_SUMMARY:{json}`:
`scan_events.py`, `html_deep_parser.py`, `ingest_scan_stats.py`, `tipster_aggregator.py`, `tipster_xref.py`, `data_enrichment_agent.py`, `deep_stats_report.py`, `gate_checker.py`, `coupon_builder.py`, `build_shortlist.py`, `odds_evaluator.py`, `context_checks.py`, `upset_risk.py`, `fetch_odds_multi.py`, `validate_coupons.py`

Exit codes: 0=success, 1=partial/degraded, 2=critical failure.

## Key Design Lesson
When agents fail to follow instructions: make instructions SHORTER, add CONCRETE EXAMPLES, reduce DUPLICATION. Don't add more rules or bold text. Per-agent "YOUR VALUE" statements explain WHY the agent exists.
