# Bet Project — Key Facts

## Architecture
- **Agent-driven pipeline**: Orchestrator agent calls individual scripts one at a time (S0→S10). ⛔ NEVER use `pipeline_orchestrator.py`. See `orchestrate-betting-day.prompt.md`
- **Database**: `betting/data/betting.db` (SQLite, WAL mode). Connection: `from bet.db.connection import get_db` (busy_timeout=30000, retry_on_lock()). 30-table schema across 7 domains (Core, Stats, Analysis, Betting, Pipeline, ESPN, Tipster)
- **Discovery (S1)**: `src/bet/discovery/` module — API-first event discovery via SofaScore + Odds API + API-Football. ~30s, 1700+ events. CLI: `PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date YYYY-MM-DD --verbose`. DB: `fixtures`, `scan_results`, `fixture_sources`
- **Discovery module only**: No legacy scanning fallback. All event discovery goes through `src/bet/discovery/`
- Config: `config/betting_config.json` — all thresholds and limits
- Adapters: `scripts/adapters/` — domain-specific HTML parsers, fallback to raw_adapter
- Settlement: `scripts/settle_on_finish.py --betting-day YYYY-MM-DD [--match "..."] [--no-poll]`
- Deep stats: `scripts/deep_stats_report.py` — per-candidate S3 analysis with Poisson/NegBin probability enrichment
- Gate checker: `scripts/gate_checker.py` — 18-point S7 approval gate (`check_18_point_gate()`)
- Coupon builder: `scripts/coupon_builder.py` — S8 portfolio + combo construction
- Safety input: `scripts/normalize_stats.py` — `build_safety_input()` (DB-first, JSON cache fallback)
- DB gateway: `scripts/db_data_loader.py` — all DB read/write functions

## Key DB Tables
- `fixtures`, `team_form` (43K+), `match_stats`, `odds_history` (97K+), `analysis_results`, `gate_results`
- `scan_results`, `scan_run_stats`, `source_health`, `fixture_sources` (new, schema v8 — cross-source tracking via SA ORM)
- `athletes` (538+), `player_gamelogs` (11.5K+), `standings`, `team_ats_records`, `team_ou_records`, `power_index`, `espn_predictions`
- `tipster_picks`, `tipster_consensus` (schema v9 — via `TipsterRepo` in `repositories.py`)
- `bets`, `coupons`, `league_profiles`, `pipeline_runs`

## Extracted Pipeline Modules
- `scripts/odds_evaluator.py` — S4 odds evaluation
- `scripts/context_checks.py` — S5 context verification
- `scripts/upset_risk.py` — S6 upset risk scoring
- `scripts/tipster_xref.py` — S2 tipster cross-reference
- S10 summary built by orchestrator agent from collected verdicts (no dedicated script)
- `scripts/agent_protocol.py` — agent JSON I/O for agent reviews
- `scripts/data_rotation.py` — artifact cleanup

## Agent Architecture
- `bet-orchestrator` → routes to 8 specialist agents via `runSubagent`
- 11 per-sport scanner agents: `bet-scanner-{football,tennis,basketball,...}`
- Agent reviews: `betting/data/agent_reviews/{date}/{step}_input.json` → `{step}_review.json`

## Outputs
- DB tables (primary) + JSON/MD dual-write (human-readable fallback)
- `betting/data/{date}_s2_shortlist.json/md` — ranked shortlist (YYYY-MM-DD format)
- `betting/data/market_matrix_{date}.json/md` — full event × market matrix
- `betting/coupons/{date}*.md` — final coupon artifacts

## Conventions
- Timezone: Europe/Warsaw, betting day 06:00–05:59
- IDs: PK-YYYYMMDD-##, CP-YYYYMMDD-LR/HR
- CSV pipe-separated multi-values
- All amounts in PLN with dot decimals
- Date format for files: YYYY-MM-DD (not YYYYMMDD)
