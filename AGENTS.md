# Betting Pipeline — Project Rules

## Architecture

- Agent-driven pipeline: orchestrator calls individual scripts; `pipeline_orchestrator.py` is BANNED.
- DB-first: `betting/data/betting.db` via `from bet.db.connection import get_db`. JSON/MD are secondary.
- Model: Qwen3.6-35B-A3B MoE 4-bit (local via Rapid-MLX, 131K context, MoE 35B total/3B active, hybrid attention/Mamba, thinking mode ALWAYS ON). All 10 agents.
- MCP servers: `sequentialthinking`, `sqlite` (betting.db), `brave-search`.
- Terminal: Fish shell. No bash syntax, no `export`, no heredocs. Use `set -x VAR value`.

## Constraints

- Bookmaker: Betclic. All picks CONDITIONAL until user verifies in the app. Never scrape Betclic.
- Timezone: Europe/Warsaw. Betting day: 06:00–05:59.
- Always settle previous day BEFORE generating new picks.
- NEVER invent odds, lineups, injuries, results, source conclusions, or statistical values.
- Coverage: Football, Volleyball, Basketball, Tennis, Hockey, CS2, Dota 2, Valorant.
- Coupon model: core portfolio + combination menu + extended pool. Unique events per core coupon.
- No auto-rejection based on hit rates or safety scores. User decides. Only invalid fixtures, wrong dates, and negative-EV may be auto-removed.
- Statistical markets BEFORE outcome markets. Missing odds do not cancel analysis.
- Reruns create new versions. Preserve history — never overwrite pending artifacts.

## The ONE RULE (All Agents)

> If your response could be produced by piping terminal output to a file, you have FAILED.
> Your response MUST contain ORIGINAL ANALYSIS — insights, patterns, anomalies that NO script can produce.

## Delegation Protocol (CRITICAL — orchestrator MUST follow)

The orchestrator uses the `task` tool to delegate to specialist agents after EVERY script run.
Pattern: `RUN script → CHECK output → DELEGATE via task tool → RECEIVE verdict → PROCEED`

**Skipping delegation = FAILED SESSION.** The user pays for ANALYTICAL VALUE, not script execution.

### Mandatory Delegations (orchestrator cannot skip these):
- After S1e → delegate to `bet-scanner` (coverage verdict)
- After S2 → delegate to `bet-scout` (tipster argument analysis) — **NEVER SKIP S2**
- After S3 → delegate to `bet-statistician` (edge validation)
- After S7 → delegate to `bet-challenger` (bear cases)
- After S8 → delegate to `bet-builder` (coupon validation)

### S2 (Tipster Cross-Reference) is NEVER OPTIONAL
- Source fusion (tipsters + stats + web search) is the CORE VALUE of this pipeline
- Without tipster data → coupons are pure math → NO argumentative reasoning → WORTHLESS
- If tipster_xref.py returns 0 tips → use `websearch` tool to check tipster sites manually
- NEVER proceed past S2 without a tipster_consensus file

### Never Run Scripts With --help
- The orchestrator prompt has the EXACT command for every step (Execution Spine table)
- Running `--help` wastes tokens and time
- Use `.venv/bin/python3` for ALL scripts (never bare python3)

## Agent State Preservation (Anti-Hallucination)

To prevent context loss and hallucination in long pipeline sessions:
1. After EVERY major step: write a 3-line summary to `.kilocode/memory/session-state.md`
2. Before EVERY analysis: re-read `.kilocode/memory/session-state.md` to restore context
3. Use `sequentialthinking` MCP tool for complex decisions (replaces internal chain-of-thought)
4. Cite specific numbers from DB/files — never approximate from memory
5. When in doubt about a stat: query SQLite directly, don't guess

## Routing Table

| Step | Script | Delegate To | Expected Output |
|------|--------|-------------|-----------------|
| S0 | settle_on_finish.py | bet-settler | PnL verdict + learning signals |
| S0-SCAN | scan_coupon.py + learn_from_coupons.py | bet-settler | Coupon scan learning: calibration, model failures, undervalued edges |
| S0.5 | (DB audit) | bet-db-analyst | Table readiness + blockers |
| S1 | discover_events.py | bet-scanner | Coverage verdict + shortlist quality |
| S1e | build_shortlist.py | bet-scanner | Shortlist composition verdict |
| S2 | tipster_xref.py | bet-scout | Consensus + contrarian signals |
| S2.3–S2.9 | scrapers + enrichment | bet-enricher | Data quality verdict per sport |
| S3 | deep_stats_report.py | bet-statistician | Market ranking + safety scores |
| S4 | odds_evaluator.py | bet-valuator | EV analysis + drift flags |
| S5+S6 | context + upset_risk | bet-challenger | Bear cases + upset risk |
| S7 | gate_checker.py | bet-challenger | Gate verdict + approved list |
| S8 | coupon_builder.py | bet-builder | Portfolio + coupons + artifacts |

## Data Flow Verification (R18)

Before running script B after script A: verify output format of A matches input expectations of B. Read code, check JSON keys and DB tables. NEVER assume scripts "just work."

## Memory Boundary

- Files under `.kilocode/memory/` are persistent notes — agents read/write them as regular files via edit/command permissions.
- Write SHORT notes (max 5 lines) after discovering new patterns.
- Read session-state.md at start of every delegation to restore context.
