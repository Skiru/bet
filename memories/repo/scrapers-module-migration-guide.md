# Modular Scrapers System — Migration Guide

> Created: 2026-05-14. For the agent replacing `data_enrichment_agent.py` with `bet.scrapers`.

## Architecture Overview

New module: `src/bet/scrapers/` — 9 scrapers across 5 sports, SQLAlchemy 2.0 ORM, coexists with existing raw sqlite3.

```
src/bet/scrapers/
├── __init__.py          # Lazy registry: get_scraper(sport, source) → class
├── engine.py            # SQLAlchemy engine + session factory (WAL, FK, busy_timeout)
├── models.py            # ORM: ScraperRun, PlayerSeasonStat + reflected existing tables
├── base.py              # BaseScraper ABC: rate limiting, UA rotation, DB helpers
├── constants.py         # SPORT_SOURCE_MAP, FBREF_LEAGUES, rate delays, URLs
├── football/fbref.py    # soccerdata library (FBref)
├── basketball/nba_api_scraper.py  # nba_api library
├── basketball/bball_ref.py        # HTML scraping (requests + BeautifulSoup)
├── tennis/sackmann.py             # CSV from GitHub (Jeff Sackmann datasets)
├── tennis/sofascore_tennis.py     # SofaScore REST API
├── hockey/nhl_api.py              # NHL public API (api-web.nhle.com)
├── hockey/hockey_ref.py           # HTML scraping (Hockey-Reference)
├── volleyball/volleybox.py        # HTML scraping (Volleybox.net)
└── volleyball/sofascore_volley.py # SofaScore REST API
```

CLI: `scripts/run_scrapers.py` — `--sport all`, `--sport hockey --source nhl-api`, `--list`, `--fixtures YYYY-MM-DD`

## Database Tables Written By Scrapers

### Existing tables (reflected, NOT created by scrapers):
| Table | What scrapers write | Key columns |
|-------|-------------------|-------------|
| `sports` | find_or_create sport rows | `id`, `name` |
| `competitions` | find_or_create competition rows | `id`, `sport_id`, `name`, `country`, `season` |
| `teams` | find_or_create team rows | `id`, `sport_id`, `name`, `country` |
| `athletes` | find_or_create athlete rows | `id`, `external_id`, `sport_id`, `team_id`, `name`, `position` |
| `fixtures` | Scheduled matches (NHL, SofaScore) | `external_id`, `sport_id`, `competition_id`, `home_team_id`, `away_team_id`, `kickoff`, `status` |
| `league_profiles` | **LEAGUE AVERAGES** (mean across all teams) | `competition_id`, `stat_key`, `season`, `avg_value`, `sample_size` |
| `player_gamelogs` | Per-match player stats (FBref, Sackmann, NBA) | `athlete_id`, `game_date`, `stats_json`, `source` |

### New tables (created by scrapers via SQLAlchemy):
| Table | Purpose | Key columns |
|-------|---------|-------------|
| `scraper_runs` | Run tracking: when, what, status, record counts | `scraper_name`, `sport`, `target`, `status`, `records_inserted`, `records_updated`, `error_message` |
| `player_season_stats` | Player season aggregates | `athlete_id`, `competition_id`, `season`, `games_played`, `stats_json`, `source` |

### CRITICAL: league_profiles stores AVERAGES, not per-team data
After code review fix (C1), `league_profiles` stores the **mean** of all teams' values for each stat key. Example: if 30 NHL teams have wins [52, 48, 45, ...], `league_profiles` stores `avg_value = mean(all_wins) = 41.0, sample_size = 30`. This is LEAGUE-LEVEL context, not per-team standings.

**Per-team data is NOT in league_profiles.** Per-team player data is in `player_season_stats`.

## How to Query Scraper Data (for downstream agents)

### Get league averages for a competition:
```sql
SELECT stat_key, avg_value, sample_size
FROM league_profiles
WHERE competition_id = (SELECT id FROM competitions WHERE name = 'NHL' AND season = '2425')
ORDER BY stat_key;
```

### Get player season stats for a team:
```sql
SELECT a.name, ps.games_played, ps.stats_json, ps.source
FROM player_season_stats ps
JOIN athletes a ON a.id = ps.athlete_id
JOIN teams t ON a.team_id = t.id
WHERE t.name = 'Edmonton Oilers' AND ps.season = '2425'
ORDER BY ps.games_played DESC;
```

### Get scraper run history:
```sql
SELECT scraper_name, sport, target, status, records_inserted, records_updated, 
       started_at, error_message
FROM scraper_runs
ORDER BY started_at DESC LIMIT 20;
```

## Difference from Old System (data_enrichment_agent.py)

| Aspect | Old (`data_enrichment_agent.py`) | New (`bet.scrapers`) |
|--------|--------------------------------|---------------------|
| **Data source** | Flashscore via Playwright (headless browser) | Direct APIs + HTML scraping (requests) |
| **DB layer** | Raw sqlite3 via `get_db()` + `StatsRepo.save_team_form()` | SQLAlchemy 2.0 ORM + parameterized `text()` queries |
| **What it writes** | `team_form` table (L10/L5 values per stat key) | `league_profiles`, `player_season_stats`, `player_gamelogs`, `athletes` |
| **Granularity** | Team-level form only | Team averages + individual player stats + match-level gamelogs |
| **Player data** | None | Full player season stats with games, goals, assists, etc. |
| **Rate limiting** | Playwright page delays | Configurable per-source sleep (0.5s–6s) |
| **Concurrency** | ThreadPoolExecutor (caused Playwright crashes) | Sequential per-source (safe) |
| **Dependencies** | Playwright (heavy, fragile) | requests, beautifulsoup4, soccerdata, nba_api (lightweight) |

### What the old system wrote to `team_form`:
```python
TeamForm(team_id, sport_id, stat_key, l10_values, l5_values, l10_avg, l5_avg, h2h_values, trend, source)
```

### What the new system writes:
- `league_profiles`: league-wide averages per stat (replaces part of team_form context)
- `player_season_stats`: individual player aggregates (NEW — old system didn't have this)
- `player_gamelogs`: per-match player stats (NEW)
- `scraper_runs`: operational tracking (NEW)

## ⚠️ MIGRATION GAP: team_form NOT written by scrapers

The new scrapers do NOT write to `team_form`. The old enrichment agent populates `team_form` with L10/L5 rolling averages per team — this is what `deep_stats_report.py` and `normalize_stats.py` consume via `build_safety_input()`.

**To fully replace the old system, you need to either:**
1. Add a post-processing step that reads `player_season_stats` + `player_gamelogs` and computes L10/L5 rolling form → writes to `team_form`
2. Or modify downstream consumers (`normalize_stats.py`, `deep_stats_report.py`) to read directly from `player_season_stats` and `league_profiles`

## What stats_json Contains (per sport)

### Football (FBref):
```json
{"standard_mp": 38, "standard_gls": 15, "standard_ast": 8, "standard_g+a": 23, 
 "standard_pk": 2, "standard_crdy": 5, "standard_crdr": 0, "playing_time_min": 3200}
```

### Basketball (NBA API):
```json
{"pts": 28.5, "reb": 7.2, "ast": 5.1, "stl": 1.3, "blk": 0.8, "tov": 3.2,
 "fgm": 10.5, "fga": 20.1, "fg_pct": 0.522, "fg3_pct": 0.385, "ft_pct": 0.88}
```

### Hockey (NHL API / Hockey-Ref):
```json
{"goals": 64, "assists": 89, "points": 153, "plusminus": 32, 
 "penaltyminutes": 36, "shots": 350, "shootingpctg": 0.183}
```

### Tennis (Sackmann):
```json
{"wins": 65, "losses": 8, "aces_per_match": 12.3, "df_per_match": 2.1,
 "first_serve_pct": 0.67, "bp_saved_pct": 0.72, 
 "hard_wins": 30, "hard_losses": 3, "clay_wins": 20, "clay_losses": 4}
```

### Volleyball (Volleybox):
```json
{"points": 512, "aces": 45, "block_points": 38, "attack_pct": 56.2}
```

## Testing Status — HONEST ASSESSMENT

| What | Status | Details |
|------|--------|---------|
| Unit tests (mocked) | ✅ 49/49 pass | All HTTP calls mocked. Tests verify DB writes, data flow, error handling |
| Live API calls | ❌ NOT TESTED | Never hit real NHL API, Hockey-Ref, Volleybox, SofaScore, etc. |
| Rate limiting | ❌ NOT TESTED | Delays implemented but untested against real endpoints |
| Production data volume | ❌ NOT TESTED | Unknown behavior with 30 NHL teams × 200+ stats or 500+ players |
| CLI `--sport all` | ❌ NOT TESTED | Only `--list` was tested |
| Integration with pipeline | ❌ NOT TESTED | Scrapers write to DB correctly in tests, but no downstream script has consumed this data yet |
| Old system compatibility | ❌ GAP | Does NOT write to `team_form` — downstream scripts won't see scraper data without adapter |

## What Needs to Happen for Full Integration

1. **Live smoke test**: Run `scripts/run_scrapers.py --sport hockey --source nhl-api --season 2425 --verbose` against real NHL API
2. **Adapter layer**: Bridge scraper output → `team_form` table (or modify consumers)
3. **Pipeline integration**: Call `run_scrapers.py` from `orchestrate-betting-day` before/alongside enrichment
4. **Verbose enhancement**: Add per-team/per-player progress logging inside scraper methods (currently silent during scrape)
5. **AGENT_SUMMARY format**: The CLI prints `AGENT_SUMMARY:{json}` at the end, but individual scrapers don't emit progress — an orchestrator agent monitoring a long scrape won't see mid-run progress
