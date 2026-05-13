# Repo Workflow Notes

## Agent-Driven Pipeline (NOT script runner)
- Copilot IS the orchestrator — delegates to specialist agents via `runSubagent`
- Scripts are DATA PRODUCERS, agents are ANALYSTS
- ⛔ NEVER run `pipeline_orchestrator.py` — call individual scripts one at a time
- Between EVERY script: `sequentialthinking` + `runSubagent` to specialist agent
- Agent reviews: `betting/data/agent_reviews/{date}/{step}_input.json`

## Scanning Architecture
- Parallel per-sport scanning: `python3 scripts/scan_events.py --parallel-sport --urls-file config/scan_urls.json --deep`
- 5 scanner groups, 5 core sports (football, volleyball, basketball, tennis, hockey). Independent timeouts (football 15min, others 2-5min)
- DB-first storage: `scan_results` + `scan_run_stats` tables, `ScanResultRepo`
- Config: `config/scan_urls.json` (sport-grouped URL source of truth)

## DB-First Architecture
- All scripts read from `betting/data/betting.db` (SQLite, WAL) first, JSON fallback
- Gateway: `scripts/db_data_loader.py` — all DB read/write functions
- Safety input: `scripts/normalize_stats.py` — `build_safety_input()` (DB-first, cache fallback)
- Connection: `from bet.db.connection import get_db` (context manager — never raw sqlite3)
- Pipeline dual-writes: JSON first (human-readable), then DB (primary source)

## Tier A stats sources by sport
- Football: Flashscore, SoccerStats, scores24
- Tennis: Flashscore, TennisAbstract
- Basketball/Hockey: ESPN (auto-loaded: gamelogs, standings, ATS/OU, power index)

## Market diversity
- Statistical markets ALWAYS preferred: corners, fouls, cards, shots, games, sets, points
- `config/betting_config.json` has a `market_types` dict per sport
- §3.0 Statistical Market Ranking via `compute_safety_scores.py`

## Betclic sport URLs
- Football: betclic.pl/pilka-nozna-s1
- Tennis: betclic.pl/tenis-s2
- Basketball: betclic.pl/koszykowka-s4
- Hockey: betclic.pl/hokej-na-lodzie-s13
- Baseball: betclic.pl/baseball-s14
