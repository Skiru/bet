# Scrapers Module — Handoff Documentation for Next Agent

> Created: 2026-05-15. Author: Senior Data Engineer agent (Phase 1–4 implementation).
> Purpose: COMPLETE specification for the next agent to integrate `bet.scrapers` into the betting pipeline and eventually replace `data_enrichment_agent.py`.
>
> **Related docs:**
> - `memories/repo/pipeline-knowledge-base.md` — consolidated pipeline architecture, bugs, enrichment flow, safety patterns
> - `memories/repo/scrapers-module-migration-guide.md` — architecture overview, table mappings, query examples
> - `memories/repo/pipeline-bugs-and-fixes.md` — post-mortem bugs with rules for all agents

---

## TABLE OF CONTENTS

1. [What Was Built](#1-what-was-built)
2. [Complete File Inventory](#2-complete-file-inventory)
3. [Database Tables — What Each Scraper Writes Where](#3-database-tables)
4. [Old System Deep Dive (data_enrichment_agent.py)](#4-old-system)
5. [New System Deep Dive (bet.scrapers)](#5-new-system)
6. [THE CRITICAL GAP — team_form Adapter](#6-the-critical-gap)
7. [Step-by-Step Integration Plan](#7-integration-plan)
8. [Exact Commands to Run](#8-commands)
9. [Known Risks and Rate Limits](#9-risks)
10. [What NOT to Break](#10-do-not-break)
11. [Testing Status — Honest Assessment](#11-testing-status)

---

## 1. What Was Built

A **modular Python scraper system** at `src/bet/scrapers/` that fetches sports data from 9 different sources across 5 sports (football, basketball, tennis, hockey, volleyball). It is SEPARATE from the existing enrichment script (`scripts/data_enrichment_agent.py`).

**Key design decisions:**
- SQLAlchemy 2.0 ORM coexisting with the existing raw `sqlite3` + `get_db()` system
- Lazy imports via `__getattr__` to avoid requiring optional dependencies at import time
- `BaseScraper` ABC pattern with shared helpers (rate limiting, UA rotation, DB find-or-create)
- CLI entry point at `scripts/run_scrapers.py` emitting `AGENT_SUMMARY:{json}` for pipeline integration
- All HTTP calls use `requests` (lightweight) — NO Playwright dependency

**What it does NOT do (yet):**
- Does NOT write to `team_form` table (the old system's output consumed by the pipeline)
- Does NOT have verbose mid-run logging (scrapers are silent during execution)
- Has NOT been tested against live APIs (all tests use mocked responses)
- Is NOT integrated into `orchestrate-betting-day` pipeline

---

## 2. Complete File Inventory

### Core Module: `src/bet/scrapers/`

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `__init__.py` | Lazy registry mapping `(sport, source)` → scraper class. Uses `importlib.import_module()` | `available_scrapers()`, `get_scraper(sport, source)` |
| `engine.py` | SQLAlchemy engine singleton. StaticPool, WAL+FK+busy_timeout pragmas. DB: `betting/data/betting.db` | `get_engine()`, `get_session_factory()`, `init_scraper_db()`, `Base` (DeclarativeBase) |
| `models.py` | ORM models for 2 new tables + reflection of 5 existing tables | `ScraperRun`, `PlayerSeasonStat`, `_reflect_existing_tables()` |
| `base.py` | Abstract base class for all scrapers. Contains ALL shared DB/HTTP helpers | `BaseScraper` (ABC), `ScraperError`, `ScraperRateLimitError` |
| `constants.py` | Configuration constants: UA strings, league mappings, rate delays, URLs | `USER_AGENTS`, `SPORT_SOURCE_MAP`, `FBREF_LEAGUES`, `DEFAULT_RATE_DELAYS` |

### Sport Scrapers (9 total):

| File | Class | Data Source | Methods Implemented |
|------|-------|-------------|---------------------|
| `football/fbref.py` | `FootballFBrefScraper` | FBref via `soccerdata` library | `team_stats` ✅, `player_stats` ✅, `player_match_stats` ✅ |
| `basketball/nba_api_scraper.py` | `BasketballNBAScraper` | NBA official API via `nba_api` | `team_stats` ✅, `player_stats` ✅, `player_match_stats` ✅ (top 50 by mins) |
| `basketball/bball_ref.py` | `BasketballBRefScraper` | Basketball-Reference HTML | `team_stats` ✅, `player_stats` ✅ |
| `tennis/sackmann.py` | `TennisSackmannScraper` | Jeff Sackmann GitHub CSVs | `team_stats` ✅ (=player aggregates), `player_stats` ✅, `player_match_stats` ✅ |
| `tennis/sofascore_tennis.py` | `TennisSofascoreScraper` | SofaScore REST API | `fixtures` ✅, `team_stats` returns 0, `player_stats` returns 0 |
| `hockey/nhl_api.py` | `HockeyNHLScraper` | NHL public API (`api-web.nhle.com`) | `team_stats` ✅, `player_stats` ✅, `fixtures` ✅ |
| `hockey/hockey_ref.py` | `HockeyRefScraper` | Hockey-Reference HTML | `team_stats` ✅, `player_stats` ✅ |
| `volleyball/volleybox.py` | `VolleyboxScraper` | Volleybox.net HTML | `team_stats` ✅, `player_stats` ✅ |
| `volleyball/sofascore_volley.py` | `VolleySofascoreScraper` | SofaScore REST API | `team_stats` ✅ (standings), `fixtures` ✅, `player_stats` returns 0 |

### CLI & Tests:

| File | Purpose |
|------|---------|
| `scripts/run_scrapers.py` | CLI entry point. Supports `--sport`, `--source`, `--season`, `--competition`, `--fixtures`, `--list`, `--verbose` |
| `tests/scrapers/conftest.py` | Pytest fixtures: `tmp_db_path`, `session_factory` (in-memory SQLite), `sample_sport_id` |
| `tests/scrapers/test_football_fbref.py` | 5 tests (mocked soccerdata) |
| `tests/scrapers/test_basketball_nba.py` | 5 tests (mocked nba_api) |
| `tests/scrapers/test_basketball_bref.py` | 5 tests (mocked HTML) |
| `tests/scrapers/test_tennis_sackmann.py` | 5 tests (mocked CSV) |
| `tests/scrapers/test_sofascore_tennis.py` | 5 tests (mocked API) |
| `tests/scrapers/test_hockey_nhl.py` | 5 tests (mocked API) |
| `tests/scrapers/test_hockey_ref.py` | 5 tests (mocked HTML) |
| `tests/scrapers/test_volleyball_volleybox.py` | 5 tests (mocked HTML) |
| `tests/scrapers/test_volleyball_sofascore.py` | 4 tests (mocked API) |
| `tests/scrapers/test_integration.py` | 5 integration tests (registry, factory, init_db, CLI) |

### DB Migrations:

| File | What it adds |
|------|-------------|
| `src/bet/db/migrations/007_scraper_tables.sql` | `scraper_runs` + `player_season_stats` table DDL |
| `src/bet/db/schema.py` | SCHEMA_VERSION bumped to 7, migration 007 registered |
| `src/bet/db/schema.sql` | DDL appended for both tables |

### Dependencies (pyproject.toml):

| Dependency | Group | Required By |
|-----------|-------|-------------|
| `sqlalchemy>=2.0.0` | Core (always installed) | `engine.py`, `models.py`, `base.py` |
| `soccerdata>=1.8.0` | `[scrapers]` optional | `football/fbref.py` |
| `pandas>=2.0.0` | `[scrapers]` optional | `football/fbref.py` |
| `nba_api` | NOT in pyproject.toml (install manually) | `basketball/nba_api_scraper.py` |
| `beautifulsoup4` | Already in core deps | `basketball/bball_ref.py`, `hockey/hockey_ref.py`, `volleyball/volleybox.py` |

> ⚠️ `nba_api` is missing from pyproject.toml. Add it to `[project.optional-dependencies].scrapers`.

---

## 3. Database Tables — What Each Scraper Writes Where

### Tables WRITTEN by scrapers:

#### `league_profiles` (existing table, new data)
Stores **league-wide averages** (mean across all teams for each stat key per competition/season).

| Column | Type | Example |
|--------|------|---------|
| `competition_id` | INTEGER FK → competitions | 42 (NHL) |
| `stat_key` | TEXT | `"wins"`, `"goals_per_game"`, `"penalty_minutes"` |
| `season` | TEXT | `"2425"` |
| `avg_value` | REAL | `41.0` (mean wins across 30 NHL teams) |
| `sample_size` | INTEGER | `30` (number of teams) |
| `updated_at` | TEXT | ISO timestamp |

**Who writes:** ALL 7 scrapers that implement `scrape_team_season_stats()` call `_upsert_league_profiles()`.

**IMPORTANT:** After code review fix C1, this stores the MEAN of all teams' values — NOT per-team data. If 30 teams have wins [52,48,45,...], it stores `avg_value = mean(all) = 41.0`. Per-team data is NOT preserved in league_profiles.

#### `player_season_stats` (NEW table)
Stores per-player season aggregates.

| Column | Type | Example |
|--------|------|---------|
| `athlete_id` | INTEGER FK → athletes | 1234 |
| `competition_id` | INTEGER FK → competitions | 42 |
| `season` | TEXT | `"2425"` |
| `games_played` | INTEGER | 82 |
| `games_started` | INTEGER | 82 |
| `minutes_played` | REAL | 2156.0 |
| `stats_json` | TEXT (JSON) | `{"pts": 28.5, "reb": 7.2, "ast": 5.1}` |
| `per_game_json` | TEXT (JSON) | `{"pts_pg": 28.5}` |
| `advanced_json` | TEXT (JSON) | `{"per": 30.2, "ts_pct": 0.62}` |
| `source` | TEXT | `"nba-api"`, `"fbref"`, `"sackmann"` |
| UNIQUE constraint | | `(athlete_id, competition_id, season, source)` |

**Who writes:** FBref, NBA API, BRef, Sackmann, NHL API, Hockey-Ref, Volleybox.

#### `player_gamelogs` (existing table, new data)
Stores per-match player stat lines.

| Column | Type | Example |
|--------|------|---------|
| `athlete_id` | INTEGER FK → athletes | 1234 |
| `game_date` | TEXT | `"2025-01-15"` |
| `stats_json` | TEXT (JSON) | `{"goals": 2, "assists": 1, "shots": 5}` |
| `source` | TEXT | `"fbref"`, `"nba-api"`, `"sackmann"` |
| UNIQUE constraint | | `(athlete_id, game_date)` |

**Who writes:** FBref (`scrape_player_match_stats`), NBA API (`scrape_player_match_stats`), Sackmann (`scrape_player_match_stats`).

#### `scraper_runs` (NEW table)
Operational tracking of scraper executions.

| Column | Type |
|--------|------|
| `scraper_name` | TEXT — e.g. `"HockeyNHLScraper"` |
| `sport` | TEXT — e.g. `"hockey"` |
| `target` | TEXT — e.g. `"NHL/2425"` |
| `status` | TEXT — `"running"`, `"success"`, `"failed"` |
| `records_scraped` / `records_inserted` / `records_updated` | INTEGER |
| `error_message` | TEXT (null on success) |
| `started_at` / `finished_at` | TEXT (ISO timestamps) |

**Who writes:** All scrapers via `_track_run()` context manager in `scrape_team_season_stats()`.

#### Lookup tables (existing, scrapers create rows as needed):

| Table | How scrapers use it |
|-------|-------------------|
| `sports` | `_find_or_create_sport(session, "hockey")` → creates if missing |
| `competitions` | `_find_or_create_competition(session, sport_id, "NHL", "USA", "2425")` |
| `teams` | `_find_or_create_team(session, sport_id, "Edmonton Oilers")` |
| `athletes` | `_find_or_create_athlete(session, ext_id, sport_id, "Connor McDavid", team_id, "C")` |
| `fixtures` | Direct INSERT (NHL API + SofaScore scrapers only) |

### Tables NOT written by scrapers (THE GAP):

| Table | Who writes it NOW | Who reads it | Why it matters |
|-------|------------------|-------------|----------------|
| **`team_form`** | `data_enrichment_agent.py` via `StatsRepo.save_team_form()` | `normalize_stats.py` (`build_safety_input_from_db()`), `deep_stats_report.py` (`load_team_form_from_db()`) | **This is the MAIN data pipeline input for safety scores, market analysis, and all S3+ steps** |
| **JSON stats cache** | `data_enrichment_agent.py` via `_save_to_cache()` | `normalize_stats.py` (`build_safety_input_from_cache()`) — fallback when DB has no data | Secondary data path, used when team_form table is empty for a team |

---

## 4. Old System Deep Dive (data_enrichment_agent.py)

**File:** `scripts/data_enrichment_agent.py` (~1000 lines)

### What it does:
1. Takes team name + sport as input (via `--team`, `--batch`, or `--date`)
2. Tries multiple sources in order:
   - **UnifiedAPIClient** (Flashscore/Scores24 via Playwright headless browser)
   - **TotalCorner** (football corners only, for TC-sourced fixtures)
   - **ESPN deep fetch** (via `_fetch_espn_deep()`)
   - **Scores24 direct** (fallback)
3. For each team, collects a dict of `{stat_key: [list of last N values]}` — e.g. `{"corners": [8, 5, 12, 7, 9, ...], "goals": [2, 1, 0, 3, ...]}`
4. Saves data to TWO destinations simultaneously:

### Save path 1: JSON cache (`_save_to_cache()`, line 673)
- File: `betting/data/stats_cache/{sport}/{team_slug}.json`
- Format:
```json
{
  "team": "FC Barcelona",
  "sport": "football",
  "sources": ["flashscore", "enrichment-agent"],
  "form": {
    "l10_avg": {"corners": 5.8, "goals": 2.1, "shots": 14.3},
    "l5_avg": {"corners": 6.2, "goals": 2.4, "shots": 15.1},
    "l10_matches": [
      {"corners": 8, "goals": 2, "shots": 16},
      {"corners": 5, "goals": 1, "shots": 12}
    ]
  },
  "enriched_at": "2026-05-15T10:00:00+00:00"
}
```

### Save path 2: `team_form` table (`_save_to_db()`, line 736)
- For each stat_key in the stats dict, creates a `TeamForm` row:
```python
TeamForm(
    id=None,
    team_id=team.id,            # resolved via TeamRepo.find_or_create()
    sport_id=sport_obj.id,      # resolved via SportRepo.get_by_name()
    stat_key="corners",         # e.g. "corners", "goals", "shots_on_target", "fouls"
    l10_values=[8, 5, 12, 7, 9, 6, 11, 4, 8, 7],  # last 10 match values
    l5_values=[8, 5, 12, 7, 9],                     # last 5 match values
    l10_avg=7.7,                # mean of l10_values
    l5_avg=8.2,                 # mean of l5_values
    h2h_values=[],              # empty for non-H2H rows
    h2h_opponent_id=None,       # null for non-H2H rows
    trend="rising",             # "rising", "falling", "stable" (l5_avg vs l10_avg, threshold ±0.3)
    updated_at="2026-05-15T10:00:00+00:00",
    source="client-enrichment"
)
```
- Saved via `StatsRepo.save_team_form(form)` which does DELETE+INSERT (SAVEPOINT-wrapped)

### What stat_keys the old system produces (per sport):

The stat keys are defined in `SPORT_STAT_KEYS` (line ~100 of data_enrichment_agent.py). Typical keys:

| Sport | Stat Keys |
|-------|-----------|
| Football | `corners`, `goals`, `shots_on_target`, `shots`, `fouls`, `yellow_cards`, `possession`, `offsides` |
| Basketball | `points`, `rebounds`, `assists`, `steals`, `blocks`, `turnovers`, `field_goal_pct` |
| Hockey | `goals`, `shots`, `power_play_pct`, `penalty_minutes`, `faceoff_pct` |
| Tennis | `aces`, `double_faults`, `first_serve_pct`, `break_points_saved` |
| Volleyball | `points`, `aces`, `blocks`, `attack_pct`, `serve_errors` |

### How downstream reads it:

`normalize_stats.py` function `build_safety_input_from_db()` (line 627):
1. Resolves `sport_id`, `team_a_id`, `team_b_id` via repositories
2. Calls `stats_repo.get_all_form_for_team(team_id, sport_id)` → gets all `team_form` rows for each team
3. Calls `conn.execute("SELECT * FROM team_form WHERE team_id = ? AND h2h_opponent_id = ?")` → H2H rows
4. Passes to `_build_markets_from_db_form()` which:
   - Groups form rows by `stat_key` and side (home/away suffix)
   - For each market definition, extracts `l10_values` (prefers `_home` variant for team_a, `_away` for team_b)
   - Falls back to `l10_avg` → synthesizes fake L10 values if only averages available
   - Returns list of market dicts for safety score calculation

**CRITICAL CHAIN:** `data_enrichment_agent.py` → `team_form` table → `normalize_stats.py` `build_safety_input_from_db()` → `deep_stats_report.py` → safety scores → gate → coupon

---

## 5. New System Deep Dive (bet.scrapers)

### Data flow per scraper type:

#### `scrape_team_season_stats(competition, season)`:
1. Fetches team-level stats from source (API or HTML scraping)
2. For each team, collects stat values into a `defaultdict(list)` accumulator
3. At the end, calls `_upsert_league_profiles(session, comp_id, season, accumulator)` which:
   - Computes `mean()` of all teams' values per stat_key
   - Upserts into `league_profiles` (competition_id, stat_key, season, avg_value, sample_size)
4. Returns count of stat keys upserted

**Example:** NHL scraper fetches 32 teams. For `"wins"` key, accumulator has `[52, 48, 45, ...]` (32 values). League profile stores `avg_value = mean = 41.0, sample_size = 32`.

#### `scrape_player_season_stats(competition, season)`:
1. Fetches per-player season aggregates from source
2. For each player: `find_or_create_athlete` → upsert `PlayerSeasonStat` row
3. `stats_json` contains sport-specific JSON blob (see section 3)
4. Returns count of player records inserted/updated

#### `scrape_player_match_stats(competition, season)`:
1. Fetches per-player per-match stat lines (gamelogs)
2. For each gamelog: INSERT OR IGNORE into `player_gamelogs`
3. `stats_json` contains match-specific stats
4. Returns count of gamelogs inserted

#### `scrape_fixtures(date)`:
1. Fetches scheduled matches for given date
2. INSERT OR IGNORE into `fixtures` table
3. Only implemented by: NHL API, SofaScore Tennis, SofaScore Volleyball

### What `stats_json` contains per sport/source:

#### Football (FBref) — player_season_stats.stats_json:
```json
{"standard_mp": 38, "standard_gls": 15, "standard_ast": 8, "standard_g+a": 23, 
 "standard_pk": 2, "standard_crdy": 5, "standard_crdr": 0, "playing_time_min": 3200}
```

#### Basketball (NBA API) — player_season_stats.stats_json:
```json
{"pts": 28.5, "reb": 7.2, "ast": 5.1, "stl": 1.3, "blk": 0.8, "tov": 3.2,
 "fgm": 10.5, "fga": 20.1, "fg_pct": 0.522, "fg3_pct": 0.385, "ft_pct": 0.88}
```

#### Hockey (NHL API) — player_season_stats.stats_json:
```json
{"goals": 64, "assists": 89, "points": 153, "plusminus": 32, 
 "penaltyminutes": 36, "shots": 350, "shootingpctg": 0.183}
```

#### Hockey (NHL API) — league_profiles stat_keys:
`wins`, `losses`, `ot_losses`, `points`, `goals_per_game`, `goals_against_per_game`, `pp_pct`, `pk_pct`, `shots_per_game`, `shots_against_per_game`

#### Tennis (Sackmann) — player_season_stats.stats_json:
```json
{"wins": 65, "losses": 8, "aces_per_match": 12.3, "df_per_match": 2.1,
 "first_serve_pct": 0.67, "bp_saved_pct": 0.72, 
 "hard_wins": 30, "hard_losses": 3, "clay_wins": 20, "clay_losses": 4}
```

#### Volleyball (Volleybox) — player_season_stats.stats_json:
```json
{"points": 512, "aces": 45, "block_points": 38, "attack_pct": 56.2}
```

---

## 6. THE CRITICAL GAP — team_form Adapter

### The Problem

The betting pipeline's S3+ steps (deep stats, safety scores, gate, coupon) read team form data via:

```
normalize_stats.py → build_safety_input_from_db() → reads team_form table
normalize_stats.py → build_safety_input_from_cache() → reads JSON stats cache files
```

The new scrapers write to DIFFERENT tables:
- `league_profiles` — league averages (not per-team)
- `player_season_stats` — per-player aggregates
- `player_gamelogs` — per-player per-match stats

**Neither `team_form` nor the JSON cache files are populated by the new scrapers.**

### What the Adapter Must Do

Build a **post-processing script** that:

1. **Reads** `player_gamelogs` for a given team (all players, last N matches)
2. **Aggregates** per-match player stats into TEAM-LEVEL stats per match
   - Football: sum all players' corners, goals, shots → team totals per match
   - Basketball: sum points, rebounds, assists → team totals per match
   - Hockey: sum goals, shots, assists → team totals per match
3. **Computes** L10 and L5 rolling averages:
   - `l10_values` = last 10 match team totals for each stat key
   - `l5_values` = last 5 match team totals
   - `l10_avg` = mean(l10_values)
   - `l5_avg` = mean(l5_values)
   - `trend` = "rising" if (l5_avg - l10_avg) > 0.3, "falling" if < -0.3, else "stable"
4. **Writes** to `team_form` table via `StatsRepo.save_team_form(TeamForm(...))` — same format the old system uses
5. **Optionally writes** JSON cache file to `betting/data/stats_cache/{sport}/{slug}.json` in the same format the old system uses

### Adapter Design Suggestion

```python
# scripts/scraper_to_team_form.py

"""Bridge: converts scraper output (player_gamelogs + player_season_stats) 
into team_form rows that downstream pipeline scripts consume."""

# For each team in a given sport:
# 1. Get all athlete_ids for the team:
#    SELECT id FROM athletes WHERE team_id = ?
#
# 2. Get last N gamelogs per athlete (ordered by game_date DESC):
#    SELECT game_date, stats_json FROM player_gamelogs 
#    WHERE athlete_id IN (...) ORDER BY game_date DESC
#
# 3. Group by game_date → aggregate to team-level per match
#    (sum/avg depending on stat type — goals=sum, fg_pct=avg)
#
# 4. From the last 10 team-level matches, extract per-stat arrays
#    l10_values = [team_corners_match1, team_corners_match2, ...]
#
# 5. Write TeamForm rows via StatsRepo.save_team_form()
```

### Mapping: player_gamelogs stats_json keys → team_form stat_keys

This is the HARDEST part. The stat_keys in `player_gamelogs.stats_json` (e.g. `"standard_gls"` from FBref) must map to the stat_keys that `normalize_stats.py` expects (e.g. `"goals"`).

**The next agent MUST read `SPORT_STAT_KEYS` from `data_enrichment_agent.py` and `SPORT_MARKETS` from `normalize_stats.py` to understand the exact key names the downstream expects.**

Approximate mapping needed:

| Sport | Pipeline stat_key | FBref player_gamelogs key | NHL API key | NBA API key |
|-------|------------------|--------------------------|-------------|-------------|
| Football | `goals` | `standard_gls` | — | — |
| Football | `corners` | ❌ NOT IN FBREF | — | — |
| Football | `shots_on_target` | `standard_sota` (if available) | — | — |
| Hockey | `goals` | — | `goals` | — |
| Hockey | `shots` | — | `shots` | — |
| Basketball | `points` | — | — | `pts` |
| Basketball | `rebounds` | — | — | `reb` |

> ⚠️ **FBref does NOT provide team-level corners, fouls, or cards in player gamelogs.** These are match-level stats. For football corners/fouls/cards, the adapter may need to aggregate from team_season_stats or use a different source. This is a DATA COVERAGE GAP — the old Flashscore scraper got these directly from match pages.

---

## 7. Step-by-Step Integration Plan

### Phase A: Live Smoke Tests (MUST DO FIRST)

Before building anything else, verify that scrapers actually work against real APIs.

1. **Install dependencies:**
   ```bash
   pip install soccerdata pandas nba_api
   ```

2. **Run safe API scrapers first** (public APIs, unlikely to 403):
   ```bash
   python3 scripts/run_scrapers.py --sport hockey --source nhl-api --season 2425 --verbose
   python3 scripts/run_scrapers.py --sport basketball --source nba-api --season 2425 --verbose
   python3 scripts/run_scrapers.py --sport tennis --source sackmann --season 2425 --verbose
   ```

3. **Run HTML scrapers cautiously** (may get 403/rate-limited):
   ```bash
   python3 scripts/run_scrapers.py --sport hockey --source hockey-reference --season 2425 --verbose
   python3 scripts/run_scrapers.py --sport volleyball --source volleybox --season 2425 --verbose
   ```

4. **Run FBref last** (most aggressive rate limiting, `soccerdata` manages this):
   ```bash
   python3 scripts/run_scrapers.py --sport football --source fbref --season 2425 --verbose
   ```

5. **After each run, verify data in DB:**
   ```sql
   -- Check scraper_runs for status
   SELECT scraper_name, status, records_inserted, error_message FROM scraper_runs ORDER BY started_at DESC LIMIT 10;
   
   -- Check league_profiles got populated
   SELECT lp.stat_key, lp.avg_value, lp.sample_size, c.name 
   FROM league_profiles lp JOIN competitions c ON c.id = lp.competition_id 
   WHERE lp.season = '2425' ORDER BY c.name, lp.stat_key;
   
   -- Check player_season_stats
   SELECT COUNT(*), source FROM player_season_stats WHERE season = '2425' GROUP BY source;
   
   -- Check player_gamelogs
   SELECT COUNT(*), source FROM player_gamelogs GROUP BY source;
   ```

### Phase B: Build team_form Adapter

1. Create `scripts/scraper_to_team_form.py`
2. Read `SPORT_STAT_KEYS` from `data_enrichment_agent.py` to know expected output keys
3. Read `SPORT_MARKETS` from `normalize_stats.py` to know what `build_safety_input` expects
4. Implement the aggregation logic described in section 6
5. Test by:
   - Running adapter for one hockey team
   - Querying `team_form` to verify rows exist
   - Running `normalize_stats.py` function `build_safety_input_from_db("hockey", "Edmonton Oilers", "Calgary Flames", "NHL")` — should return a dict with markets

### Phase C: Add Verbose Logging

Currently scrapers are SILENT during execution — no per-team, per-player progress logging. This violates R17 (LIVE SCRIPT MONITORING). Add `logging.info()` calls inside each scraper:
- After each team's data is fetched
- After each player's data is saved
- Include running totals (e.g. "Processed 15/32 NHL teams, 450 players so far")

### Phase D: Pipeline Integration

1. Add scraper step to `orchestrate-betting-day.prompt.md` (before or alongside enrichment)
2. Decide: run scrapers INSTEAD of enrichment, or AS SUPPLEMENT
3. The scraper data is SEASONAL (entire season stats), while enrichment is ROLLING (last 10 matches). Both have value.
4. Eventually: run scrapers weekly for season-level data, run enrichment daily for rolling form

### Phase E: Retire Old System (LAST — only when adapter is proven)

1. Run both old and new systems in parallel for 1-2 weeks
2. Compare `team_form` rows from old system vs adapter output
3. When confidence is high, stop calling `data_enrichment_agent.py`
4. Keep the file but rename to `_data_enrichment_agent_DEPRECATED.py`

---

## 8. Exact Commands to Run

### List all available scrapers:
```bash
python3 scripts/run_scrapers.py --list
```

### Run a single scraper:
```bash
python3 scripts/run_scrapers.py --sport hockey --source nhl-api --season 2425 --verbose
```

### Run all scrapers for one sport:
```bash
python3 scripts/run_scrapers.py --sport hockey --season 2425 --verbose
```

### Run ALL scrapers (5 sports × 9 sources):
```bash
python3 scripts/run_scrapers.py --sport all --season 2425 --verbose
```

### Scrape fixtures for a specific date:
```bash
python3 scripts/run_scrapers.py --sport hockey --source nhl-api --fixtures 2026-05-15 --verbose
```

### Run all tests:
```bash
python3 -m pytest tests/scrapers/ -v
```

### Run tests for a single sport:
```bash
python3 -m pytest tests/scrapers/test_hockey_nhl.py tests/scrapers/test_hockey_ref.py -v
```

---

## 9. Known Risks and Rate Limits

| Source | Rate Limit | Risk | Mitigation |
|--------|-----------|------|------------|
| **FBref** | ~20 req/min (enforced by `soccerdata`) | 429 errors if too fast | `soccerdata` auto-throttles; our delay is 3-6s |
| **Hockey-Reference** | ~20 req/min | 429 or temporary ban | Delay: 3-5s between requests |
| **Basketball-Reference** | ~20 req/min | 429 or temporary ban | Delay: 3-5s between requests |
| **Volleybox** | Unknown | 403 possible | Delay: 3-5s, UA rotation |
| **SofaScore** | Aggressive anti-bot | 403 very likely | Delay: 1.5-4s, UA rotation. May need Playwright fallback. |
| **NHL API** | Very generous (public) | Low risk | Delay: 1-2s out of courtesy |
| **NBA API** | Moderate | Occasional 500s | Delay: 0.6-1.5s |
| **Sackmann CSVs** | GitHub raw CDN | Effectively unlimited | Delay: 0.5-1s |

### Known Issues:

| ID | Issue | Severity | Details |
|----|-------|----------|---------|
| **M3** | `get_engine()` singleton ignores `db_path` after first call | LOW | If you create engine with default path, subsequent calls with different path are silently ignored. Fix: add path validation or accept singleton behavior. |
| **DATA GAP** | FBref doesn't provide team-level corners/fouls/cards in gamelogs | HIGH for football | Player gamelogs have individual stats (goals, assists, xG) but NOT match-level team stats (corners, fouls). The adapter will need supplementary data for football statistical markets. |
| **nba_api missing** | Not in pyproject.toml | LOW | `pip install nba_api` needed manually, or add to `[scrapers]` group |
| **SofaScore fragility** | Both tennis and volleyball SofaScore scrapers may break | MEDIUM | SofaScore frequently changes API. Monitor for 403s or schema changes. |

---

## 10. What NOT to Break

### DO NOT modify these files:
- `src/bet/db/connection.py` — `get_db()` raw sqlite3 connection, used by ALL existing scripts
- `src/bet/db/repositories.py` — `StatsRepo`, `TeamRepo`, `SportRepo` — used everywhere
- `src/bet/db/models.py` — `TeamForm` dataclass — downstream format contract
- `scripts/normalize_stats.py` — `build_safety_input()` chain — this is the safety score backbone
- `scripts/deep_stats_report.py` — consumes `build_safety_input()` output

### DO NOT change the `team_form` table schema:
The `team_form` table columns and the `TeamForm` dataclass fields are a **contract** between the enrichment system and the analysis pipeline. The adapter MUST write data in exactly the same format.

### DO NOT remove the old enrichment system until:
1. The adapter is fully working
2. It has been validated against at least 3 sports
3. The downstream `build_safety_input_from_db()` returns identical (or better) results

### SQLAlchemy coexistence:
- The scrapers use SQLAlchemy `engine.py` → `get_engine()` → `get_session_factory()`
- The rest of the codebase uses raw `sqlite3` → `get_db()` from `src/bet/db/connection.py`
- Both point to the SAME database file: `betting/data/betting.db`
- Both use WAL mode. This coexistence is tested and works.
- **DO NOT try to migrate existing code to SQLAlchemy** — only the scrapers module uses it

---

## 11. Testing Status — Honest Assessment

| What | Status | Confidence |
|------|--------|------------|
| Unit tests (49/49, all mocked) | ✅ PASSING | HIGH — tests verify data flow logic correctly |
| Code review fixes (C1, C2, M1, M2) | ✅ APPLIED | HIGH — all 4 bugs fixed and verified |
| Live API calls | ❌ NEVER TESTED | ZERO — no real HTTP request has been made |
| Rate limiting under real conditions | ❌ NEVER TESTED | LOW — delays exist but untested |
| SofaScore anti-bot | ❌ NEVER TESTED | LOW — SofaScore is the most likely to 403 |
| Production data volumes | ❌ NEVER TESTED | LOW — unknown behavior with 30+ teams × 500+ players |
| team_form adapter | ❌ NOT BUILT | — |
| JSON cache adapter | ❌ NOT BUILT | — |
| Pipeline integration | ❌ NOT DONE | — |
| `--sport all` full run | ❌ NEVER TESTED | ZERO |

### What the tests DO verify:
- Each scraper correctly parses mocked API/HTML responses
- Data is correctly written to in-memory SQLite (league_profiles, player_season_stats, player_gamelogs, scraper_runs)
- `_upsert_league_profiles()` computes correct averages (post-C1 fix)
- `_safe_json_dumps()` handles numpy/pandas types without crashing (post-C2 fix)
- `_track_run()` creates scraper_runs records with correct status transitions (post-M1 fix)
- Error handling (empty responses, 403s, missing data) returns 0 without crashing
- Registry + factory patterns work (get_scraper, available_scrapers, init_scraper_db)
- CLI argument parsing and output format

### What the tests DO NOT verify:
- Actual HTTP response parsing from real endpoints (HTML structure may differ from mocks)
- Real rate limiting behavior and retry logic
- Connection timeouts and network errors under real conditions
- Data volume handling (memory, speed, DB write performance)
- Whether the stat_keys produced by each scraper are actually USEFUL for downstream analysis

---

## SUMMARY FOR THE NEXT AGENT

**You are inheriting a COMPLETE but UNTESTED scraper module.** The code architecture is solid, tests pass, and the module is cleanly separated from the existing system.

**Your job is to:**
1. ✅ Run live smoke tests (Phase A) — this will likely reveal issues with HTML parsing, API response format changes, or rate limiting
2. ✅ Build the `team_form` adapter (Phase B) — this is the CRITICAL missing piece for pipeline integration
3. ✅ Add verbose logging (Phase C) — needed for R17 compliance
4. ✅ Integrate into the pipeline (Phase D)
5. ✅ Eventually retire the old system (Phase E)

**The single most important thing:** The pipeline reads `team_form`. The scrapers don't write to `team_form`. You must bridge this gap. Everything else is secondary.
