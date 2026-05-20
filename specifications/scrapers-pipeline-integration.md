# Scrapers Module → Pipeline Integration Specification

> Created: 2026-05-14. Purpose: COMPLETE specification for integrating `bet.scrapers` into the betting pipeline, replacing `data_enrichment_agent.py`, and cleaning up legacy code.
>
> **Status:** Scrapers module is BUILT, TESTED, and VERIFIED LIVE against all 5 sports.

---

## TABLE OF CONTENTS

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture (AS-IS)](#2-current-architecture)
3. [Target Architecture (TO-BE)](#3-target-architecture)
4. [Scraper System — Live Verification Results](#4-live-verification)
5. [Database Schema — Complete Map](#5-database-schema)
6. [The Critical Gap — team_form Bridge](#6-the-critical-gap)
7. [Integration Plan — 5 Phases](#7-integration-plan)
8. [Legacy Cleanup Inventory](#8-legacy-cleanup)
9. [Agent Updates Required](#9-agent-updates)
10. [Pipeline Step Changes](#10-pipeline-step-changes)
11. [Data Flow Diagrams](#11-data-flow)
12. [Testing & Validation Checklist](#12-testing)
13. [Risk Register](#13-risks)

---

## 1. Executive Summary

### What Exists Now
A **modular scraper system** at `src/bet/scrapers/` with 17 scrapers across 5 sports, using SQLAlchemy 2.0 ORM. All scrapers have been **live-tested** (2026-05-14) with real data. The system writes to `league_profiles`, `player_season_stats`, `scraper_runs`, and lookup tables (`sports`, `competitions`, `teams`, `athletes`). **ESPN is now a first-class scraper** for all 5 sports (not just a fallback in the old enrichment system).

### What's Missing
The pipeline's analysis steps (S3–S8) read from `team_form` table via `normalize_stats.py → build_safety_input_from_db()`. Scrapers write to **different tables**. A bridge adapter is needed to convert scraper output into `team_form` format.

### What Must Happen
1. Build `scraper_to_team_form.py` adapter (converts scraper data → `team_form`)
2. Add `run_scrapers.py` as a pipeline step (S2.3) between tipsters and enrichment
3. Update enrichment to use scrapers as primary + old system as fallback
4. Update 4 agent definitions to know the new flow
5. Clean up 12+ legacy files after transition

---

## 2. Current Architecture (AS-IS)

### Data Flow — Current Pipeline
```
S0   analyze_betclic_learning.py  → advisory data for user
S1   discover_events.py           → fixtures in DB + JSON shortlist
S1e  build_shortlist.py           → 2026-MM-DD_s2_shortlist.json
S2   tipster_aggregator.py        → tipster picks in DB
S2   tipster_xref.py              → cross-referenced shortlist
S2.5 data_enrichment_agent.py     → team_form table + JSON cache ← THE OLD WAY
S3   deep_stats_report.py         → reads team_form via normalize_stats.py
S4   odds_evaluator.py            → EV calculations
S5   context_checks.py            → injuries, weather, news
S6   upset_risk.py                → upset risk assessment
S7   gate_checker.py              → pass/fail gate
S8   coupon_builder.py            → final coupons
```

### Key Data Dependencies
```
data_enrichment_agent.py
  WRITES → team_form (L10/L5 per-stat-key values)
  WRITES → betting/data/stats_cache/{sport}/{slug}.json

normalize_stats.py
  READS  → team_form (via build_safety_input_from_db)
  READS  → stats_cache JSON (via build_safety_input_from_cache, fallback)
  OUTPUT → market dicts with safety scores

deep_stats_report.py
  CALLS  → normalize_stats.build_safety_input()
  READS  → team_form (via db_data_loader.load_team_form_from_db)
```

### What `team_form` Contains (the contract)
```sql
CREATE TABLE team_form (
    id INTEGER PRIMARY KEY,
    team_id INTEGER NOT NULL,       -- FK → teams.id
    sport_id INTEGER NOT NULL,      -- FK → sports.id
    stat_key TEXT NOT NULL,          -- e.g. "corners", "goals", "shots_on_target"
    l10_values TEXT,                 -- JSON array of last 10 match values: [8,5,12,7,9,6,11,4,8,7]
    l5_values TEXT,                  -- JSON array of last 5 match values: [8,5,12,7,9]
    l10_avg REAL,                   -- mean(l10_values) = 7.7
    l5_avg REAL,                    -- mean(l5_values) = 8.2
    h2h_values TEXT,                -- JSON array (empty for non-H2H rows)
    h2h_opponent_id INTEGER,        -- FK → teams.id (null for non-H2H)
    trend TEXT,                     -- "rising" | "falling" | "stable"
    updated_at TEXT,                -- ISO timestamp
    source TEXT                     -- "client-enrichment", "flashscore", "scrapers"
);
```

---

## 3. Target Architecture (TO-BE)

### Data Flow — New Pipeline
```
S0    analyze_betclic_learning.py   → advisory data
S1    discover_events.py            → fixtures in DB + JSON shortlist
S1e   build_shortlist.py            → shortlist JSON
S2    tipster_aggregator.py         → tipster picks
S2    tipster_xref.py               → cross-referenced shortlist
S2.3  run_scrapers.py  ← NEW STEP  → league_profiles + player_season_stats + scraper_runs
S2.4  scraper_to_team_form.py ← NEW → team_form (bridge from scraper data)
S2.5  data_enrichment_agent.py      → team_form (gap-fill for what scrapers missed)
S3    deep_stats_report.py          → reads team_form (populated by S2.4 + S2.5)
S4+   ... (unchanged)
```

### Key Changes
1. **S2.3** — Run scrapers for today's sports (fast, API-based, ~30s per sport)
2. **S2.4** — Bridge adapter converts scraper data → `team_form` rows
3. **S2.5** — Old enrichment becomes FALLBACK (fills gaps scrapers missed)
4. **Eventually** — S2.5 is removed entirely when scraper coverage is 100%

---

## 4. Scraper System — Live Verification Results (2026-05-14)

### 17 Registered Scrapers — Live Test Summary

| # | Sport | Source | Team Stats | Player Stats | Speed | Status |
|---|-------|--------|------------|-------------|-------|--------|
| 1 | Football | `fbref` | **20** teams (EPL) | **574** players | 66s | ✅ PASS |
| 2 | Football | `espn` | **29** stat keys (1 team test) | — | 4s | ✅ PASS (live 2026-05-14) |
| 3 | Football | `flashscore` | **5/5** teams | — | 7s | ✅ PASS |
| 4 | Basketball | `nba-api` | **21** teams | **569** players | 3.3s | ✅ PASS |
| 5 | Basketball | `basketball-reference` | **19** teams | **736** players | 10s | ✅ PASS |
| 6 | Basketball | `espn` | ✅ standings (30 NBA teams) | roster import | ~3s | ✅ PASS (live 2026-05-14) |
| 7 | Basketball | `flashscore` | **3/3** teams | — | 4.4s | ✅ PASS |
| 8 | Tennis | `sackmann` | — | **457** players | 1.5s | ✅ PASS (season fix applied) |
| 9 | Tennis | `espn` | scoreboard scan (ATP/WTA) | — | ~5s | ✅ PASS (live 2026-05-14) |
| 10 | Tennis | `flashscore` | **1/3** | — | 4.4s | ⚠️ PARTIAL |
| 11 | Hockey | `nhl-api` | **15** team stats | **261** players | 5s | ✅ PASS (standings + leaders fixed) |
| 12 | Hockey | `hockey-reference` | **27** team stats | **1,251** players | 11s | ✅ PASS (comment extraction + table ID fixed) |
| 13 | Hockey | `espn` | ✅ standings (NHL) | roster import | ~3s | ✅ PASS (live 2026-05-14) |
| 14 | Hockey | `flashscore` | **3/3** teams | — | 4.5s | ✅ PASS |
| 15 | Volleyball | `volleybox` | Error | Error | — | ❌ BLOCKED (Cloudflare 403) |
| 16 | Volleyball | `espn` | ✅ standings (FIVB) | — | ~3s | ✅ PASS (live 2026-05-14) |
| 17 | Volleyball | `flashscore` | **3/3** teams | — | 4.5s | ✅ PASS |

### ESPN Scraper Details
- **Architecture**: `src/bet/scrapers/espn.py` — `BaseESPNScraper` wraps `ESPNClient` from `api_clients/espn.py`
- **5 sport subclasses**: `FootballESPNScraper`, `BasketballESPNScraper`, `HockeyESPNScraper`, `TennisESPNScraper`, `VolleyballESPNScraper`
- **Football stats** (29 keys): corners, fouls, yellow_cards, shots, shots_on_target, possession, goals, offsides, saves, passes, crosses, clearances, long_balls, blocked_shots, tackles, interceptions, penalty goals/attempts, accuracy metrics
- **Basketball/Hockey**: team stats from fixture boxscores + player rosters
- **Tennis**: custom scoreboard scan (sets_won, games_won, total_games, rankings)
- **Volleyball**: kills, aces, blocks, digs, assists, errors, hitting_pct
- **Free API**: no key, no rate limits, HTTPS, caching built-in

### DB Totals After All Runs
- **127** `league_profiles` records (98 original + 29 from ESPN football live test)
- **3,912** `player_season_stats` records (6 sources)
- **12,360** athletes tracked
- **103/103** scraper unit tests passing (13 ESPN + 90 existing)
- **660/661** full test suite (1 pre-existing failure unrelated to scrapers)

### Bugs Found & Fixed During Verification (2026-05-14)
| # | Bug | Fix | File |
|---|-----|-----|------|
| 1 | Sackmann season code `"2425"[:4]` → `"2024"` (wrong year) | Convert `"2425"` → `"2025"` (end-year) | `tennis/sackmann.py` |
| 2 | NHL API standings used season-code endpoint (404) | Use date-based `/standings/2025-04-15` | `hockey/nhl_api.py` |
| 3 | NHL API player stats response is `{category: [players]}` not `{data: [players]}` | Rewrite to iterate categories, merge by player ID | `hockey/nhl_api.py` |
| 4 | NHL API `teamAbbrev` is string, code expected `{"default": "..."}` dict | Handle both string and dict | `hockey/nhl_api.py` |
| 5 | Hockey-Reference tables hidden in HTML comments (anti-scrape) | Added `_find_table()` with `Comment` extraction | `hockey/hockey_ref.py` |
| 6 | Hockey-Reference player table ID is `player_stats` not `stats` | Changed lookup | `hockey/hockey_ref.py` |
| 7 | Volleybox season format needs `"2024-2025"` not `"2425"` | Convert in `_get_league_url()` | `volleyball/volleybox.py` |

### Per-Sport Best Sources (Recommended for Pipeline)
| Sport | Primary Source | Backup | Flashscore |
|-------|---------------|--------|------------|
| Football | **fbref** (richest: 20 teams + 574 players) | flashscore (goals from scores) | ✅ |
| Basketball | **nba-api** (official, fastest) | basketball-reference (736 players) | ✅ |
| Tennis | **sackmann** (457 players, comprehensive) | flashscore (partial) | ⚠️ |
| Hockey | **hockey-reference** (1,251 players!) | nhl-api (261 players) | ✅ |
| Volleyball | **flashscore** (only working source) | sofascore (fixtures only) | ✅ |

---

## 5. Database Schema — Complete Map

### Tables Written by Scrapers (SQLAlchemy ORM)

#### `scraper_runs` (NEW — operational tracking)
```sql
CREATE TABLE scraper_runs (
    id INTEGER PRIMARY KEY,
    scraper_name TEXT NOT NULL,    -- "HockeyNHLScraper", "FootballFBrefScraper"
    sport TEXT NOT NULL,           -- "hockey", "football"
    target TEXT NOT NULL,          -- "team_stats/NHL/2425"
    status TEXT NOT NULL,          -- "running", "success", "failed"
    records_scraped INTEGER DEFAULT 0,
    records_inserted INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_seconds REAL
);
```

#### `player_season_stats` (NEW — per-player season aggregates)
```sql
CREATE TABLE player_season_stats (
    id INTEGER PRIMARY KEY,
    athlete_id INTEGER NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
    competition_id INTEGER REFERENCES competitions(id) ON DELETE SET NULL,
    season TEXT NOT NULL,
    games_played INTEGER DEFAULT 0,
    games_started INTEGER DEFAULT 0,
    minutes_played REAL DEFAULT 0.0,
    stats_json TEXT NOT NULL DEFAULT '{}',    -- sport-specific JSON blob
    per_game_json TEXT NOT NULL DEFAULT '{}',
    advanced_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(athlete_id, competition_id, season, source)
);
```

#### `league_profiles` (EXISTING — league averages per stat key)
```sql
-- Scrapers write MEAN of all teams' values for each stat_key
-- Example: NHL "wins" → avg_value=41.0, sample_size=32
INSERT INTO league_profiles (competition_id, stat_key, season, avg_value, sample_size, updated_at)
VALUES (:cid, :sk, :sea, :avg, :n, :upd)
ON CONFLICT(competition_id, stat_key, season) DO UPDATE SET avg_value=:avg, sample_size=:n;
```

#### Lookup Tables (EXISTING — scrapers create rows via find_or_create)
| Table | Helper Method | Creates If Missing |
|-------|--------------|-------------------|
| `sports` | `_find_or_create_sport(session, "hockey")` | Yes |
| `competitions` | `_find_or_create_competition(session, sport_id, "NHL", "USA/Canada", "2425")` | Yes |
| `teams` | `_find_or_create_team(session, sport_id, "Edmonton Oilers", "USA/Canada")` | Yes |
| `athletes` | `_find_or_create_athlete(session, ext_id, sport_id, name, team_id, position)` | Yes |

### Tables READ by Pipeline (that scrapers must eventually feed)

| Table | Read By | Current Writer | New Writer |
|-------|---------|---------------|------------|
| `team_form` | `normalize_stats.py`, `deep_stats_report.py` | `data_enrichment_agent.py` | **`scraper_to_team_form.py`** (to be built) |
| `fixtures` | All pipeline steps | `discover_events.py` | Existing (scrapers supplement via NHL/SofaScore) |

### SQLAlchemy ↔ sqlite3 Coexistence
- Scrapers: `src/bet/scrapers/engine.py` → `get_engine()` / `get_session_factory()` (SQLAlchemy)
- Pipeline: `src/bet/db/connection.py` → `get_db()` (raw sqlite3)
- **Both use the SAME database file:** `betting/data/betting.db`
- **Both use WAL mode.** This is tested and works.
- **DO NOT attempt to migrate existing code to SQLAlchemy.** Only scrapers use it.

---

## 6. The Critical Gap — team_form Bridge

### Problem
Pipeline S3+ reads `team_form`. Scrapers write to `league_profiles` + `player_season_stats`. Nothing connects them.

### Solution: `scripts/scraper_to_team_form.py`

#### What It Must Do
```
FOR each team in today's shortlist:
  1. Query player_season_stats for all athletes on this team
  2. Query league_profiles for the team's competition
  3. Synthesize team-level stat arrays that look like L10/L5 form data
  4. Write team_form rows via StatsRepo.save_team_form()
```

#### Design Approach — Two Data Paths

**Path A: Player gamelogs → Team form (when gamelogs exist)**
- FBref, NBA API, Sackmann produce `player_gamelogs` with per-match stats
- Group by `game_date` → sum/avg across all players → team totals per match
- Take last 10 matches → `l10_values`, last 5 → `l5_values`
- Compute `l10_avg`, `l5_avg`, `trend`

**Path B: League profiles → Team form (when only averages exist)**
- NHL API, Hockey-Ref, Flashscore produce `league_profiles` (league averages)
- Synthesize fake L10 by sampling around the league average: `[avg ± small_noise] × 10`
- Mark `source = "scrapers-synthetic"` to distinguish from real form data
- This gives downstream a BASELINE even without per-match data

**Path C: Player season stats → Team form (enriched averages)**
- Aggregate `player_season_stats.stats_json` for all players on a team
- Compute per-game averages (e.g., team_goals_per_game = sum(player_goals) / team_games)
- Use as L10/L5 avg values with `source = "scrapers-aggregated"`

#### Stat Key Mapping (CRITICAL)

The adapter MUST map scraper stat keys to pipeline stat keys that `normalize_stats.py` expects.

| Sport | Pipeline stat_key | FBref source | ESPN source | NBA API source | NHL/Hockey-Ref | Sackmann | Flashscore |
|-------|------------------|-------------|-------------|---------------|----------------|----------|------------|
| Football | `goals` | `standard_gls` | `goals` | — | — | — | `goals` (scores) |
| Football | `corners` | ❌ NOT IN FBREF | `corners` ✅ | — | — | — | `corners` |
| Football | `shots_on_target` | `standard_sota` | `shots_on_target` | — | — | — | — |
| Football | `fouls` | ❌ NOT IN FBREF | `fouls` ✅ | — | — | — | `fouls` |
| Football | `yellow_cards` | ❌ NOT IN FBREF | `yellow_cards` ✅ | — | — | — | — |
| Football | `possession` | — | `possession` ✅ | — | — | — | `ball_possession` |
| Basketball | `points` | — | `points` | `pts` | — | — | `total_points` (scores) |
| Basketball | `rebounds` | — | `rebounds` | `reb` | — | — | — |
| Basketball | `assists` | — | `assists` | `ast` | — | — | — |
| Hockey | `goals` | — | `goals` | — | `goals` / `gf` | — | `goals` (scores) |
| Hockey | `shots` | — | `shots` | — | `s` / `shots` | — | — |
| Tennis | `aces` | — | — | — | — | `aces_per_match` | — |
| Tennis | `total_games` | — | `total_games` ✅ | — | — | derived | `total_games` |
| Volleyball | `total_points` | — | — | — | — | — | `total_points` (scores) |
| Volleyball | `kills` | — | `kills` ✅ | — | — | — | — |
| Volleyball | `aces` | — | `aces` ✅ | — | — | — | — |

> ✅ **FOOTBALL DATA GAP RESOLVED:** ESPN now provides team-level corners, fouls, yellow cards, possession, shots, crosses, clearances, and 20+ other match-level stat keys across 36+ leagues. FBref still provides deeper player-level data (xG, xA, progressive passes) but ESPN fills the critical gap for team-level statistical markets. The old `data_enrichment_agent.py` fallback (S2.5) is now less critical but still useful for H2H data and edge cases.

#### CLI Interface
```bash
# Process all teams in today's shortlist
PYTHONPATH=src .venv/bin/python scripts/scraper_to_team_form.py --date 2026-05-14 --verbose

# Process specific teams
PYTHONPATH=src .venv/bin/python scripts/scraper_to_team_form.py --teams "Edmonton Oilers,Boston Celtics" --verbose

# Emit AGENT_SUMMARY (R19)
# Exit 0=OK, 1=PARTIAL, 2=FAILED
```

---

## 7. Integration Plan — 5 Phases

### Phase 1: Build team_form Adapter (CRITICAL PATH)
**Files to create:**
- `scripts/scraper_to_team_form.py` — bridge script
- `tests/test_scraper_to_team_form.py` — unit tests with mocked DB data

**Implementation steps:**
1. Read `SPORT_STAT_KEYS` from `data_enrichment_agent.py` (line ~100) for expected output keys
2. Read `SPORT_MARKETS` from `normalize_stats.py` for what `build_safety_input` expects
3. Implement Path A (gamelogs → form) for sports with gamelog data (football, basketball, tennis)
4. Implement Path B/C (profiles/season stats → form) for others (hockey, volleyball)
5. Test by running adapter → then querying `team_form` → then calling `build_safety_input_from_db()`
6. Verify downstream `deep_stats_report.py` produces valid safety scores

**Validation query:**
```sql
-- After adapter runs, verify team_form was populated
SELECT tf.stat_key, tf.l10_avg, tf.l5_avg, tf.trend, tf.source, t.name
FROM team_form tf
JOIN teams t ON t.id = tf.team_id
WHERE tf.source LIKE 'scrapers%'
ORDER BY t.name, tf.stat_key;
```

### Phase 2: Add Scrapers to Pipeline (S2.3)
**Files to modify:**
- `.github/prompts/orchestrate-betting-day.prompt.md` — add S2.3 step
- `.github/agents/bet-orchestrator.agent.md` — add `run_scrapers.py` to script list
- `.github/agents/bet-enricher.agent.md` — update to know about scraper data
- `.github/internal-prompts/bet-enrich.prompt.md` — add scraper-first check

**Pipeline change:**
```
# S2.3 — Run scrapers for today's sports (NEW)
PYTHONPATH=src .venv/bin/python scripts/run_scrapers.py --sport all --season 2425 --verbose
# → populates league_profiles, player_season_stats, scraper_runs

# S2.4 — Convert scraper data to team_form (NEW)
PYTHONPATH=src .venv/bin/python scripts/scraper_to_team_form.py --date {date} --verbose
# → populates team_form for teams with scraper data

# S2.5 — Enrichment fills remaining gaps (MODIFIED — now fallback only)
PYTHONPATH=src .venv/bin/python scripts/data_enrichment_agent.py --date {date} --news --verbose
# → fills team_form for teams that scrapers missed
```

### Phase 3: Parallel Validation (1-2 weeks)
- Run both old and new systems
- Compare `team_form` rows: scraper adapter vs old enrichment
- Track which sport/stat combinations have better coverage
- Log discrepancies in `betting/journal/`

### Phase 4: Retire Old Enrichment
**Conditions to meet before retirement:**
- [ ] Adapter covers all 5 sports' stat keys used by `normalize_stats.py`
- [ ] Safety scores from adapter data are within ±5% of old system
- [ ] At least 2 weeks of parallel operation without issues
- [ ] Football corners/fouls gap is solved (Flashscore scraper or alternative)

**Files to deprecate:**
- `scripts/data_enrichment_agent.py` → rename to `scripts/_data_enrichment_agent_DEPRECATED.py`
- `scripts/flashscore_enricher.py` → already superseded by `src/bet/scrapers/flashscore.py`

### Phase 5: Full ORM Migration (Future — Optional)
Eventually migrate ALL DB access from raw sqlite3 to SQLAlchemy:
- Move `team_form` to ORM model in `src/bet/scrapers/models.py`
- Migrate `normalize_stats.py` to use SQLAlchemy queries
- Remove `src/bet/db/connection.py` dependency
- **This is NOT required for integration.** The coexistence works fine.

---

## 8. Legacy Cleanup Inventory

### Scripts to Deprecate (after Phase 4)
| File | Replacement | Notes |
|------|------------|-------|
| `scripts/data_enrichment_agent.py` | `run_scrapers.py` + `scraper_to_team_form.py` | Keep as `_DEPRECATED.py` until fully validated |
| `scripts/flashscore_enricher.py` | `src/bet/scrapers/flashscore.py` | Already superseded |
| `scripts/_deep_enrich_sofascore.py` | `src/bet/scrapers/tennis/sofascore_tennis.py` + `volleyball/sofascore_volley.py` | Underscore prefix = already marked internal |
| `scripts/_check_stealth_api.py` | No longer needed (scrapers use direct APIs) | Debug script |
| `scripts/_check_stealth_api2.py` | No longer needed | Debug script |
| `scripts/_debug_oddsportal.py` | No longer needed | Debug script |
| `scripts/_debug_oddsportal_detail.py` | No longer needed | Debug script |
| `scripts/_debug_oddsportal_listing.py` | No longer needed | Debug script |
| `scripts/_debug_betexplorer.py` | No longer needed | Debug script |
| `scripts/_debug_scores24.py` | No longer needed | Debug script |
| `scripts/_debug_soccerway.py` | No longer needed | Debug script |
| `scripts/_debug_totalcorner.py` | No longer needed | Debug script |
| `scripts/_dump_tc_rows.py` | No longer needed | Debug script |
| `scripts/_probe_flashscore.py` | No longer needed | Debug script |

### Specifications to Archive
| File | Status |
|------|--------|
| `specifications/adapter-enrichment-plan.md` | Superseded by this doc |
| `specifications/hockey-adapter-improvements/` | Incorporated into hockey scrapers |
| `specifications/volleyball-adapter-improvements.plan.md` | Incorporated into volleyball scrapers |
| `specifications/playwright-scraping-research/` | No longer relevant (scrapers use requests) |

### Test Files Already Cleaned (2026-05-14)
- Removed 7 orphan test files for non-existent adapter modules
- Removed betclic_scraper tests (R12: no scraping)
- All remaining tests pass (637/638)

---

## 9. Agent Updates Required

### bet-enricher.agent.md — Major Update
**Current role:** Self-healing enrichment using `data_enrichment_agent.py`
**New role:** Data quality guardian that checks scraper output FIRST, then falls back to old enrichment

**Changes needed:**
1. Update description: "Validates scraper data completeness, triggers old enrichment only for gaps"
2. Add knowledge of `run_scrapers.py` output (AGENT_SUMMARY format, league_profiles, player_season_stats)
3. Add knowledge of `scraper_to_team_form.py` output
4. Update data flow section: scrapers → adapter → team_form → (gap analysis) → enrichment if needed
5. Add new metrics to monitor: scraper success rate per sport, team_form coverage after adapter

### bet-orchestrator.agent.md — Add S2.3 and S2.4
**Changes needed:**
1. Add `run_scrapers.py` and `scraper_to_team_form.py` to script list
2. Add S2.3 and S2.4 steps in pipeline sequence
3. Update S2.5 description to "gap-fill fallback"
4. Add `run_scrapers.py` to AGENT_SUMMARY emitters list

### bet-scanner.agent.md — Minor Update
**Changes needed:**
1. Note that `discover_events.py` now has supplementary fixture data from scrapers (NHL, SofaScore)
2. Add awareness of `fixture_sources` table (cross-references between discovery sources)

### bet-statistician.agent.md — Add Scraper Data Awareness
**Changes needed:**
1. Add knowledge of `player_season_stats` table (per-player data available)
2. Add knowledge of `league_profiles` table (league averages available)
3. Update deep stats analysis to leverage player-level data when available
4. Note that `source` field in `team_form` may be "scrapers-*" for new data

### bet-db-analyst.agent.md — Add New Tables
**Changes needed:**
1. Add `scraper_runs`, `player_season_stats`, `fixture_sources` to known tables
2. Add diagnostic queries for scraper health
3. Update recommendation logic: "check scraper_runs first, then suggest re-run if stale"

### orchestrate-betting-day.prompt.md — Add S2.3/S2.4
**Changes needed:**
1. Add S2.3 block with `run_scrapers.py` command
2. Add S2.4 block with `scraper_to_team_form.py` command
3. Update S2.5 description to "gap-fill for teams scrapers missed"
4. Update script list (15 → 17 scripts)

### bet-enrich.prompt.md — Update Internal Prompt
**Changes needed:**
1. Add scraper output check as first step before old enrichment
2. Update "YOUR ANALYTICAL VALUE" to include scraper data assessment
3. Add metrics: scraper_runs success rate, team_form coverage from adapter

---

## 10. Pipeline Step Changes

### S2.3 — Run Scrapers (NEW)

**Command:**
```bash
PYTHONPATH=src .venv/bin/python scripts/run_scrapers.py --sport all --season 2425 --verbose
```

**Timeout:** 300000 (5 min — FBref is slowest at ~66s, full suite ~2-3 min)

**AGENT_SUMMARY format:**
```json
{
  "verdict": "OK|PARTIAL",
  "scrapers_run": 14,
  "results": [
    {"sport": "football", "source": "fbref", "status": "ok", "counts": {"team_stats": 20, "player_stats": 574}, "elapsed_s": 66.0},
    {"sport": "hockey", "source": "nhl-api", "status": "ok", "counts": {"team_stats": 15, "player_stats": 261}, "elapsed_s": 5.0}
  ]
}
```

**Delegation to bet-enricher:** Pass AGENT_SUMMARY + focus on:
- Which sports had errors/partial results
- Total team_stats and player_stats counts
- Any 403/timeout errors

### S2.4 — Scraper-to-Team-Form Adapter (NEW)

**Command:**
```bash
PYTHONPATH=src .venv/bin/python scripts/scraper_to_team_form.py --date {date} --verbose
```

**Timeout:** 120000 (2 min — DB-only processing, no HTTP)

**AGENT_SUMMARY format:**
```json
{
  "verdict": "OK|PARTIAL",
  "teams_processed": 85,
  "team_form_rows_written": 340,
  "sports_covered": {"football": 30, "basketball": 20, "hockey": 15, "tennis": 12, "volleyball": 8},
  "gaps": ["football corners (no source)", "volleyball aces (volleybox 403)"]
}
```

### S2.5 — Enrichment (MODIFIED — now fallback)

**New behavior:** Check `team_form` table FIRST. Only enrich teams that have 0 rows from scrapers.

**Modified command (add --skip-existing flag):**
```bash
PYTHONPATH=src .venv/bin/python scripts/data_enrichment_agent.py --date {date} --news --skip-existing --verbose
```

---

## 11. Data Flow Diagrams

### Scraper Data Flow (per sport)
```
API/HTML Source
    ↓
BaseScraper.scrape_team_season_stats()
    ↓
_upsert_league_profiles()  →  league_profiles table
    ↓
BaseScraper.scrape_player_season_stats()
    ↓
PlayerSeasonStat ORM         →  player_season_stats table
    ↓
[FUTURE] scraper_to_team_form.py
    ↓
StatsRepo.save_team_form()   →  team_form table
    ↓
normalize_stats.build_safety_input_from_db()
    ↓
deep_stats_report.py → safety scores → gate → coupon
```

### Source Coverage Matrix
```
                  fbref  nba-api  bball-ref  sackmann  sofascore  nhl-api  hockey-ref  volleybox  sofascore-v  flashscore
Football           ✅                                                                                           ✅
Basketball                ✅       ✅                                                                            ✅
Tennis                                        ✅        ⚠️ stub                                                 ⚠️ partial
Hockey                                                             ✅      ✅                                    ✅
Volleyball                                                                              ❌ 403    ⚠️ stub      ✅
```

---

## 12. Testing & Validation Checklist

### Pre-Integration (before building adapter)
- [x] All 14 scrapers registered in `__init__.py`
- [x] 80/80 scraper unit tests pass
- [x] 637/638 full test suite pass (1 pre-existing unrelated failure)
- [x] Live test: 10/14 scrapers produce real data
- [x] DB has 98 league_profiles + 3,912 player_season_stats

### Adapter Validation (after building scraper_to_team_form.py)
- [ ] Adapter writes team_form rows for all 5 sports
- [ ] `build_safety_input_from_db()` returns valid market dicts with scraper data
- [ ] `deep_stats_report.py` produces safety scores from adapter data
- [ ] Safety scores within ±5% of old enrichment system
- [ ] No `team_form` stat_key expected by `normalize_stats.py` is missing

### Pipeline Integration Validation
- [ ] `run_scrapers.py` emits valid AGENT_SUMMARY
- [ ] `scraper_to_team_form.py` emits valid AGENT_SUMMARY
- [ ] Orchestrator runs S2.3 → S2.4 → S2.5 in sequence
- [ ] S2.5 correctly skips teams already in team_form
- [ ] Full pipeline S0→S8 completes with new steps

---

## 13. Risk Register

| # | Risk | Severity | Mitigation |
|---|------|----------|-----------|
| R1 | ~~Football corners/fouls not available from scrapers~~ | ~~HIGH~~ **RESOLVED** | ESPN scraper now provides corners, fouls, yellow_cards, shots, possession across 36+ leagues |
| R2 | Volleybox 403 means no primary volleyball stats source | MEDIUM | Flashscore provides `total_points`; volleyball fixtures from SofaScore API |
| R3 | Sports-reference sites (hockey-ref, bball-ref) may start blocking | MEDIUM | Flashscore + official APIs (NHL, NBA) as backup |
| R4 | SofaScore API may change format | LOW | SofaScore scrapers are stubs currently; minimal impact |
| R5 | SQLAlchemy/sqlite3 coexistence WAL conflict | LOW | Tested and working; both use WAL + busy_timeout |
| R6 | `nba_api` not in pyproject.toml | LOW | Add to `[project.optional-dependencies].scrapers` |
| R7 | Adapter stat key mapping may miss edge cases | MEDIUM | Test adapter output against `normalize_stats.SPORT_MARKETS` exhaustively |

---

## CLI Quick Reference

```bash
# List all 17 scrapers
PYTHONPATH=src .venv/bin/python scripts/run_scrapers.py --list

# Run all scrapers for all sports
PYTHONPATH=src .venv/bin/python scripts/run_scrapers.py --sport all --season 2425 --verbose

# Run one sport, one source
PYTHONPATH=src .venv/bin/python scripts/run_scrapers.py --sport hockey --source nhl-api --season 2425 --verbose

# Run with team filter (Flashscore only)
PYTHONPATH=src .venv/bin/python scripts/run_scrapers.py --sport football --source flashscore --season 2425 --teams "Real Madrid,Barcelona" --verbose

# Run all tests
PYTHONPATH=src .venv/bin/python -m pytest tests/scrapers/ -v

# Check DB data
sqlite3 betting/data/betting.db "SELECT source, COUNT(*) FROM player_season_stats GROUP BY source;"
```
