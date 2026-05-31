# Bet Project — Key Facts

## Architecture
- Agent-driven pipeline: orchestrator calls scripts one at a time; `pipeline_orchestrator.py` banned.
- Database-first: `betting/data/betting.db` via `get_db()` from `src/bet/db/connection.py`.
- Discovery: `src/bet/discovery/` — API-first (Odds-API.io + The-Odds-API + API-Football).
- Enrichment: per-sport scripts in `scripts/enrich_*.py` with fallback chains.
- Analysis: `scripts/deep_stats_report.py` (S3), `scripts/gate_checker.py` (S7), `scripts/coupon_builder.py` (S8).

## Core Paths
- Output: `betting/data/`, `betting/coupons/`, `betting/reports/`, `betting/journal/`
- Scripts: `scripts/` (pipeline steps) + `src/bet/` (library code)
- Config: `config/betting_config.json`, `config/api_keys.json`
- Stats cache: `betting/data/stats_cache/`

## Key DB Tables
- `fixtures` — all events for the betting day
- `odds_history` — odds from all sources
- `team_form` — L10/L5/H2H statistics per team
- `analysis_results` — S3 deep stats output
- `gate_results` — S7 gate check output
- `coupons` + `bets` — placed bets and coupon history
- `athletes`, `player_gamelogs`, `player_splits` — player data
- `standings`, `power_index`, `espn_predictions` — team context

## Pipeline Steps (S0-S10) — see execution-spine.md for canonical order
S0: Settlement → S1: Scan/Discovery → S1b: Odds+Tipster fetch → S1e: Build shortlist →
S2: Tipster cross-reference → S2.3-S2.9: Enrichment → S3: Deep stats →
S4: Odds/EV → S5+S6: Context+Upset → S7: Gate/Challenge → S8: Coupons → S9: Validation → S10: Artifacts
