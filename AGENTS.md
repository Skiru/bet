# Betting Pipeline — Project Rules

## Architecture

- Agent-driven pipeline: orchestrator calls individual scripts; `pipeline_orchestrator.py` is BANNED.
- DB-first: `betting/data/betting.db` via `from bet.db.connection import get_db`. JSON/MD are secondary.
- Model: Gemini 2.5 Flash via Google AI Studio API (free tier, 1M context, 1500 RPD).
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
