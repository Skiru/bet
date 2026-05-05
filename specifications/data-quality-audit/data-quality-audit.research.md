# Data Quality Audit — Betting Pipeline Deep Audit

**Date:** 2026-05-05
**Scope:** All adapters, API clients, stats cache, database schema, and consumer scripts
**Method:** Field-level code read of every file listed in the audit scope

---

## 1. Executive Summary

| Dimension | Status | Notes |
|-----------|--------|-------|
| **Fixture discovery** | 🟢 GREEN | 18 HTML adapters + 16 API clients cover 14 sports, 232 URLs |
| **Team-level L10/L5 stats** | 🟢 GREEN | ESPN-enriched cache has 20-30+ stat keys per sport for Tier 1 sports |
| **H2H data** | 🟡 AMBER | Present for API-sourced teams; empty for most niche sports |
| **Odds collection** | 🟡 AMBER | the-odds-api + odds-api.io + API-Football odds cover ~5.6% of fixtures; most events have no API odds |
| **Injury/suspension data** | 🔴 RED | Pipeline checks for `injuries`/`suspensions` keys in cache but NO adapter or API client populates them |
| **Player-level stats** | 🔴 RED | No player-level data collected; all stats are team-aggregated |
| **Coach/manager data** | 🔴 RED | `deep_stats_report.py` checks for `coach`/`manager` in cache but no source writes it |
| **Venue/stadium data** | 🟡 AMBER | Weather script has hardcoded coordinates for ~50 cities; Sofascore API doesn't extract venue; Scores24 extracts venue from detail pages |
| **League standings/position** | 🟡 AMBER | Football-Data.org provides standings for 10 EU leagues; no other sport has standings API |
| **Motivation context** | 🔴 RED | No automated motivation scoring; mentioned in pipeline_orchestrator S5 but no data source |
| **Referee data** | 🔴 RED | Pipeline_orchestrator S5 mentions "referee" but no source collects it |
| **Probability modeling** | 🟢 GREEN | Poisson-based probability_engine.py with bootstrap CI, recency weighting (40% L5, 35% L10, 25% H2H) |
| **Database schema** | 🟢 GREEN | 12 tables, normalized with proper FK/indexes; dual-write to JSON cache + SQLite |

---

## 2. Adapter Audit Table

| # | Adapter | Fields Extracted | Depth | Sport Coverage | Extracts Odds? | Extracts Stats? | Missing Data |
|---|---------|-----------------|-------|---------------|----------------|-----------------|--------------|
| 1 | `flashscore_adapter.py` | home, away, time, source_url, league | Shallow | All 14 sports | ❌ | ❌ | No odds, no stats, no scores — Flashscore is JS-heavy, HTML fallback only |
| 2 | `betexplorer_adapter.py` | home, away, time, source_url, odds[] | Medium | EU sports | ✅ 1X2 odds (list of floats) | ❌ | No structured odds keys (just positional list), no stats |
| 3 | `oddsportal_adapter.py` | home, away, odds[], market_type, odds_structured{home_win, draw, away_win} | Medium | All sports | ✅ Named h2h odds, 2-way/3-way auto-detect | ❌ | React SPA — often returns empty; no totals/handicap markets |
| 4 | `scores24_adapter.py` | **Listing:** home, away, time, date, sport, detail_url. **Detail:** match_info{venue, surface, tournament, round}, odds{W1/X/W2, handicap, totals}, h2h[], form_home[], form_away[], trends[] | **Deep** | 20 sport slugs | ✅ Multi-bookmaker odds on detail pages | ✅ H2H, form, trends | Detail page parsing requires Playwright for full JS rendering |
| 5 | `forebet_adapter.py` | home, away, time, date, detail_url, forebet_probs{home/draw/away %}, forebet_prediction, forebet_score, forebet_avg | Medium | Football, tennis, basketball, hockey, etc. | ❌ (probabilities, not odds) | Prediction probabilities only | No actual bookmaker odds; probabilities are Forebet's model output |
| 6 | `sofascore_adapter.py` | home, away, time, source_url, sport, league (country-league), sofascore_id | Medium | 14 sports via REST API | ❌ | ❌ | Uses Sofascore public API directly (bypasses HTML); no odds, no stats, no venue |
| 7 | `soccerway_adapter.py` | home, away, time, league, sport="football" | Shallow | Football only | ❌ | ❌ | Football fixture listing only — no stats, no odds |
| 8 | `totalcorner_adapter.py` | home, away, time, league, score, corner_handicap, corner_count, total_goals_line | **Medium-Deep** | Football only | ❌ (lines, not decimal odds) | ✅ Corner counts, handicap lines, total goals lines | Unique source for live corner data; no decimal odds |
| 9 | `basketball_reference_adapter.py` | home_team, away_team, kickoff, competition="NBA", sport="basketball" | Shallow | Basketball (NBA/WNBA) | ❌ | ❌ | Schedule/fixture only — no box scores from HTML parsing |
| 10 | `hockey_reference_adapter.py` | home_team, away_team, kickoff, competition="NHL", sport="hockey" | Shallow | Hockey (NHL) | ❌ | ❌ | Schedule/fixture only — no game stats from HTML parsing |
| 11 | `whoscored_adapter.py` | home_team, away_team, kickoff, competition, sport="football", stats{possession, shots, shots_on_target, passes, corners} | Medium | Football | ❌ | ✅ Regex-extracted stats from HTML | JS-heavy SPA — stats extraction is best-effort regex on page text |
| 12 | `covers_adapter.py` | home_team, away_team, kickoff, sport, consensus{spread, total, moneyline} | Medium | NFL, NBA, MLB, NHL, NCAA | ✅ Spread/total/moneyline | ❌ | US sports only; consensus = public betting %s |
| 13 | `betclic_adapter.py` | home, away, time, odds[], competition, match_url | Medium | All Betclic sports | ✅ Decimal odds from btn_label elements | ❌ | Angular SPA — odds extraction works when page renders; no stats |
| 14 | `hltv_adapter.py` | home_team, away_team, kickoff, competition, sport="esports", format (BO1/3/5), maps[] | Medium | CS2 (esports) | ❌ | Map names only | No team stats, no odds; format detection is useful |
| 15 | `tennisexplorer_adapter.py` | home, away, time, league, sport="tennis", surface | Medium | Tennis (ATP/WTA/ITF/Challenger) | ❌ | Surface detection only | No player stats, no odds; surface is valuable metadata |
| 16 | `tennisabstract_adapter.py` | player name, elo_rank, elo_rating, hard_elo, clay_elo, grass_elo, peak_elo, official_rank, tour, player_age | **Deep (ratings)** | Tennis | ❌ | ✅ Elo ratings (overall + per-surface) | Not a fixture source — player database. No match-level stats |
| 17 | `soccerstats_adapter.py` | home, away, time, league, sport="football", stats{corners_home/away, cards_home/away, fouls_home/away}, team_stats (league averages) | Medium-Deep | Football | ❌ | ✅ Corner/card/foul averages per team | Key statistical source for football corners/cards/fouls |
| 18 | `raw_adapter.py` | home, away, time, source_url | **Shallow** | Generic fallback | ❌ | ❌ | Regex-based "Team A vs Team B" extraction; high noise, low signal |

### Key Adapter Findings

- **Only 4 adapters extract odds:** BetExplorer, OddsPortal, Betclic, Covers
- **Only 4 adapters extract stats:** Scores24 (detail pages), WhoScored, TotalCorner, SoccerStats
- **TennisAbstract is unique:** Only source providing Elo ratings per surface — critical for tennis analysis
- **Scores24 is the deepest adapter:** Extracts match info, odds, H2H, form, and trends from detail pages
- **13 out of 18 adapters produce shallow data:** Just fixture listings (team names + time)

---

## 3. API Client Audit Table

| # | Client | Sport(s) | Endpoints | Data Depth | Rate Limit | Injuries? | Player Stats? | H2H? | Key Stats |
|---|--------|----------|-----------|------------|------------|-----------|---------------|------|-----------|
| 1 | `api_football.py` (APIFootballClient) | Football | `/fixtures`, `/fixtures/statistics`, `/fixtures/headtohead` | **Deep** | 100/day (shared API-Sports key) | ❌ | ❌ Team-level | ✅ | corners, fouls, yellow_cards, red_cards, shots, shots_on_target, possession, offsides, saves |
| 2 | `api_football_odds.py` (APIFootballOddsClient) | Football | `/odds?date=` (paginated) | **Medium** (odds only) | Shares football quota | ❌ | ❌ | ❌ | h2h odds, totals, totals_corners, totals_cards, totals_fouls from multiple bookmakers |
| 3 | `api_basketball.py` (APIBasketballClient) | Basketball | `/games`, `/statistics`, `/games?h2h=` | **Deep** | 100/day (shared key) | ❌ | ❌ Team-level | ✅ | points, rebounds, assists, steals, blocks, turnovers, fg_pct, three_pct, ft_pct |
| 4 | `api_tennis.py` (APITennisClient) | Tennis | `/games`, `/games/statistics`, `/games/h2h` | Medium | 100/day (shared key) | ❌ | ❌ | ✅ | aces, double_faults, first_serve_pct, break_points_won, games_won, sets_won, total_games |
| 5 | `api_volleyball.py` (APIVolleyballClient) | Volleyball | `/games`, `/games/statistics`, `/games?h2h=` | Medium | 100/day (shared key) | ❌ | ❌ | ✅ | points, total_points, aces, blocks, attack_pct, sets_won, errors |
| 6 | `api_handball.py` (APIHandballClient) | Handball | `/games`, `/games/statistics`, `/games?h2h=` | Medium | 100/day (shared key) | ❌ | ❌ | ✅ | goals, saves, turnovers, penalties, suspensions, total_goals |
| 7 | `api_hockey.py` (APIHockeyClient) | Hockey | `/games`, `/games/statistics`, `/games?h2h=` | **Deep** | 100/day (shared key) | ❌ | ❌ | ✅ | goals, shots, powerplay_goals, pim, hits, blocks, faceoff_pct |
| 8 | `api_baseball.py` (APIBaseballClient) | Baseball | `/games`, `/games/statistics`, `/games?h2h=` | Medium | 100/day (shared key) | ❌ | ❌ | ✅ | runs, total_runs, hits, errors, strikeouts, walks, home_runs |
| 9 | `espn_adapter.py` (ESPNMultiLeagueClient) | Football (36 leagues), Basketball (NBA/WNBA), Hockey (NHL), Baseball (MLB), Tennis (ATP/WTA), MMA (UFC) | Multi-league fixture discovery + per-game stats | **Deep** | **FREE, unlimited, no key** | ❌ | ❌ Team-level | ✅ (H2H via competitors lookup) | **28+ stats per football game** (see stats_cache samples): corners, fouls, cards, shots, shots_on_target, possession, passes, crosses, tackles, interceptions, clearances, blocked_shots, long_balls, accurate_passes, etc. |
| 10 | `nba_api_client.py` (NBAAPIClient) | Basketball (NBA) | LeagueGameFinder, TeamGameLog, BoxScoreTraditionalV2, LeagueStandings | **Deep** | ~1 req/sec, free | ❌ | ❌ Team-aggregated box scores | ❌ (not in free tier) | PTS, REB, AST, STL, BLK, TOV, FG_PCT, FG3_PCT, FT_PCT |
| 11 | `understat_client.py` (UnderstatClient) | Football (6 EU leagues: EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL) | Team results with xG | **Deep (xG)** | Free, no key | ❌ | ❌ | ❌ | xG (expected goals) home/away, goals, shots — unique advanced metric |
| 12 | `thesportsdb.py` (TheSportsDBClient) | All sports | `/eventsday.php`, `/searchteams.php`, `/lookupevent.php` | **Shallow** | 100/day (free key "3") | ❌ | ❌ | ❌ (free tier) | Fixture listings only — NO per-game stats, NO H2H on free tier |
| 13 | `football_data_org.py` (FootballDataOrgClient) | Football (10 EU leagues) | `/matches`, `/teams/{id}/matches`, `/competitions/{code}/standings` | Medium (fixtures + standings) | 10 req/min, key required | ❌ | ❌ | ❌ | Fixtures with scores + **standings** (unique data point), NO per-match stat detail |
| 14 | `balldontlie.py` (NBAStatsClient) | Basketball (NBA) | `/games`, `/stats` | **Deep** (player box scores → team aggregation) | Free, key optional | ❌ | ✅ Player box scores aggregated | ✅ (via nba_api fallback) | points, rebounds, assists, steals, blocks, turnovers from player-level aggregation |
| 15 | `serpapi_client.py` (SerpAPIClient) | All sports (generic Google search) | SerpAPI Google search `/search.json` | **Variable** | 250/month (~8/day) | ❌ | ❌ | ❌ | Knowledge graph attributes (coach, venue, record, standing, rank), sports_results — unstructured supplement |
| 16 | `odds_api_io.py` (OddsAPIioClient) | 34 sports | `/events`, `/odds`, `/odds/multi`, `/value-bets`, `/participants` | Medium (odds) | 5000 req/hour, capped 200/day | ❌ | ❌ | ❌ | Multi-bookmaker odds comparison; **value-bets endpoint** (pre-calculated EV); 265 bookmakers |

### Key API Client Findings

- **ALL 7 API-Sports clients share a single API key** with 100 req/day total — contention across football, basketball, hockey, tennis, volleyball, handball, baseball
- **ESPN is the primary workhorse**: Free, unlimited, covers 6 sports with 28+ stat keys per football game
- **NO client collects injury data** despite gate_checker.py checking for it
- **NO client collects player-level data** — all stats are team-aggregated (except BallDontLie which aggregates player box scores internally)
- **7 sports have ZERO dedicated API**: snooker, darts, table_tennis, esports, mma, padel, speedway — rely on TheSportsDB (fixture-only) and SerpAPI (unstructured)
- **Understat is unique**: Only source of xG (expected goals) data, but limited to 6 EU leagues

---

## 4. Stats Cache Field Map (Actual JSON Keys Found)

### 4.1 Football (`stats_cache/football/arsenal.json`)

**Cache structure:** `{team, sport, slug, last_updated, ttl_hours, form{l10_matches[], l10_avg{}, l5_avg{}}, h2h{}, sources[], api_source}`

**Per-match stats (28+ keys from ESPN enrichment):**
| Stat Key | Format | Notes |
|----------|--------|-------|
| `corners` | `{home: N, away: N}` | ✅ Core stat for betting |
| `fouls` | `{home: N, away: N}` | ✅ Core stat for betting |
| `yellow_cards` | `{home: N, away: N}` | ✅ Core stat for betting |
| `red_cards` | `{home: N, away: N}` | Rare events |
| `shots` | `{home: N, away: N}` | ✅ Core stat |
| `shots_on_target` | `{home: N, away: N}` | ✅ Core stat |
| `possession` | `{home: %, away: %}` | Percentage stat |
| `offsides` | `{home: N, away: N}` | |
| `saves` | `{home: N, away: N}` | |
| `shot_accuracy` | `{home: ratio, away: ratio}` | Derived from ESPN |
| `penalty_goals` | `{home: N, away: N}` | |
| `penalty_attempts` | `{home: N, away: N}` | |
| `accurate_passes` | `{home: N, away: N}` | ESPN-exclusive deep stat |
| `total_passes` | `{home: N, away: N}` | ESPN-exclusive |
| `pass_accuracy` | `{home: ratio, away: ratio}` | |
| `accurate_crosses` | `{home: N, away: N}` | ESPN-exclusive |
| `crosses` | `{home: N, away: N}` | |
| `cross_accuracy` | `{home: ratio, away: ratio}` | |
| `long_balls` | `{home: N, away: N}` | |
| `accurate_long_balls` | `{home: N, away: N}` | |
| `long_ball_accuracy` | `{home: ratio, away: ratio}` | |
| `blocked_shots` | `{home: N, away: N}` | |
| `tackles_won` | `{home: N, away: N}` | |
| `tackles` | `{home: N, away: N}` | |
| `tackle_accuracy` | `{home: ratio, away: ratio}` | |
| `interceptions` | `{home: N, away: N}` | |
| `clearances` | `{home: N, away: N}` | |

**L10/L5 averages** use `{stat_key}_home` / `{stat_key}_away` split format.

**H2H section:** `h2h: {opponent_slug: {matches: [...], avg: {}}}`
**Sources tracked:** `["espn-football"]` typical, can be multi-source.

### 4.2 Tennis (`stats_cache/tennis/a-kalinina.json`)

**Per-match stats (limited — tennis API stats sparse):**
| Stat Key | Format | Notes |
|----------|--------|-------|
| `sets_won` | `{home: N, away: N}` | |
| `games_won` | `{home: N, away: N}` | ✅ Core stat for betting |
| `total_sets` | `{home: N, away: N}` | Always = number of sets played (both sides same) |

**Missing keys defined in normalize_stats.py but NOT found in cache:**
- `aces` ❌ (not from ESPN tennis)
- `double_faults` ❌
- `first_serve_pct` ❌
- `break_points_won` ❌

**Implication:** Tennis safety score calculations for aces, double_faults, first_serve, break_points markets will return empty/zero — only `games_won`, `sets_won`, `total_sets` markets are calculable.

### 4.3 Basketball (`stats_cache/basketball/cleveland.json`)

**Per-match stats (ESPN-enriched, ~20 keys):**
| Stat Key | Format | Notes |
|----------|--------|-------|
| `fg_pct` | `{home: %, away: %}` | Field goal percentage |
| `three_pct` | `{home: %, away: %}` | |
| `ft_pct` | `{home: %, away: %}` | |
| `rebounds` | `{home: N, away: N}` | ✅ Core stat |
| `offensive_rebounds` | `{home: N, away: N}` | ESPN extra |
| `defensive_rebounds` | `{home: N, away: N}` | ESPN extra |
| `assists` | `{home: N, away: N}` | ✅ Core stat |
| `steals` | `{home: N, away: N}` | |
| `blocks` | `{home: N, away: N}` | |
| `turnovers` | `{home: N, away: N}` | |
| `technical_fouls` | `{home: N, away: N}` | ESPN extra |
| `flagrant_fouls` | `{home: N, away: N}` | ESPN extra |
| `turnover_points` | `{home: N, away: N}` | ESPN extra |
| `fast_break_points` | `{home: N, away: N}` | ESPN extra |
| `points_in_paint` | `{home: N, away: N}` | ESPN extra |
| `fouls` | `{home: N, away: N}` | |
| `largest_lead` | `{home: N, away: N}` | ESPN extra |

**Missing:** `points` (total team score) is not broken out as a stat_key — it may come from `score_home`/`score_away` on the fixture level.

### 4.4 Hockey (`stats_cache/hockey/minnesota-wild.json`)

**Per-match stats (ESPN-enriched, ~15 keys):**
| Stat Key | Format | Notes |
|----------|--------|-------|
| `blocks` | `{home: N, away: N}` | ✅ |
| `hits` | `{home: N, away: N}` | ✅ |
| `takeaways` | `{home: N, away: N}` | ESPN extra |
| `shots` | `{home: N, away: N}` | ✅ Core |
| `powerplay_goals` | `{home: N, away: N}` | |
| `power_play_opportunities` | `{home: N, away: N}` | |
| `power_play_pct` | `{home: %, away: %}` | |
| `shorthanded_goals` | `{home: N, away: N}` | |
| `shootout_goals` | `{home: N, away: N}` | |
| `faceoffs_won` | `{home: N, away: N}` | |
| `faceoff_pct` | `{home: %, away: %}` | |
| `giveaways` | `{home: N, away: N}` | |
| `penalties` | `{home: N, away: N}` | |
| `pim` | `{home: N, away: N}` | ✅ Core (penalty minutes) |
| `goals` | `{home: N, away: N}` | |

### 4.5 Baseball (`stats_cache/baseball/los-angeles-dodgers.json`)

**Per-match stats (ESPN-enriched, ~12 keys):**
| Stat Key | Format | Notes |
|----------|--------|-------|
| `hit_by_pitch` | `{home: N, away: N}` | ESPN extra |
| `ground_balls` | `{home: N, away: N}` | ESPN extra |
| `strikeouts_batting` | `{home: N, away: N}` | |
| `rbis` | `{home: N, away: N}` | |
| `hits` | `{home: N, away: N}` | ✅ Core |
| `stolen_bases` | `{home: N, away: N}` | |
| `walks` | `{home: N, away: N}` | ✅ Core |
| `runs` | `{home: N, away: N}` | ✅ Core |
| `home_runs` | `{home: N, away: N}` | ✅ Core |
| `saves` | `{home: N, away: N}` | Pitching |
| `strikeouts_pitching` | `{home: N, away: N}` | |
| `losses` | `{home: N, away: N}` | |

### 4.6 Volleyball

**Stats cache directory:** `betting/data/stats_cache/volleyball/` — contains only `fixtures/` and `h2h/` subdirectories. **No team cache files found.** Volleyball team stats are completely empty in the cache.

### 4.7 Handball

**Stats cache directory:** `betting/data/stats_cache/handball/` — contains only `fixtures/` and `h2h/` subdirectories. **No team cache files found.** Handball team stats are completely empty.

### 4.8 Coverage Summary

| Sport | Cache Files Found | L10 Stats? | H2H Data? | Notes |
|-------|-------------------|------------|-----------|-------|
| Football | ~400+ files | ✅ 28+ keys | ✅ | Best coverage by far |
| Tennis | ~500+ files | ✅ 3 keys only | ❌ (empty `h2h: {}`) | Only games_won/sets_won/total_sets from ESPN |
| Basketball | ~25 files | ✅ 17+ keys | ✅ (via h2h/ dir) | NBA-focused |
| Hockey | ~16 files | ✅ 15+ keys | ✅ (via h2h/ dir) | NHL-focused |
| Baseball | ~28 files | ✅ 12+ keys | ✅ (via h2h/ dir) | MLB-focused |
| Volleyball | 0 team files | ❌ | ❌ | Only fixture/h2h directories exist |
| Handball | 0 team files | ❌ | ❌ | Only fixture/h2h directories exist |
| Snooker | Not checked | Likely ❌ | ❌ | TheSportsDB only = no stats |
| Darts | Not checked | Likely ❌ | ❌ | TheSportsDB only = no stats |
| Table Tennis | Not checked | Likely ❌ | ❌ | TheSportsDB only = no stats |
| Esports | Not checked | Likely ❌ | ❌ | TheSportsDB only = no stats |
| MMA | Not checked | Likely ❌ | ❌ | ESPN MMA exists but unclear |
| Padel | Not checked | Likely ❌ | ❌ | No API coverage |
| Speedway | Not checked | Likely ❌ | ❌ | No API coverage |

---

## 5. Database Schema

### Tables (12 total + 1 meta)

| Table | Columns | Purpose |
|-------|---------|---------|
| `sports` | id, name, tier, stat_keys (JSON array) | 14 sports with per-sport stat key definitions |
| `competitions` | id, sport_id (FK), name, country, importance, season | League/tournament registry |
| `teams` | id, sport_id (FK), name, aliases (JSON), country, venue, style_tags (JSON) | Team registry with aliases for name matching |
| `fixtures` | id, external_id, sport_id (FK), competition_id (FK), home_team_id (FK), away_team_id (FK), kickoff, status, score_home, score_away, source, fetched_at | Central fixture table — UNIQUE(sport, home, away, kickoff) |
| `match_stats` | id, fixture_id (FK), team_id (FK), stat_key, stat_value (REAL), source, fetched_at | Per-team per-stat values — UNIQUE(fixture, team, stat_key, source) |
| `team_form` | id, team_id (FK), sport_id (FK), stat_key, l10_values (JSON), l5_values (JSON), l10_avg, l5_avg, h2h_values (JSON), h2h_opponent_id (FK), trend, updated_at, source | Pre-computed form data with H2H per opponent |
| `odds_history` | id, fixture_id (FK), bookmaker, market, selection, odds (REAL), line (REAL), fetched_at, is_closing | Historical odds snapshots — indexed for drift detection |
| `coupons` | id, coupon_id (UNIQUE), coupon_type, total_odds, stake_pln, status, pnl_pln, placed_at, settled_at, betclic_ref, version, created_at | Coupon tracking with versioning |
| `bets` | id, coupon_id (FK), fixture_id (FK), sport, event_name, market, selection, odds, min_odds, safety_score, hit_rate, status, pnl_pln, settled_at, market_pl, navigation_hint, stats_detail | Individual bet records per coupon |
| `pipeline_runs` | id, date, step, status, started_at, completed_at, error_message, stats | Pipeline execution tracking |
| `source_health` | id, source_name (UNIQUE), last_success, last_failure, consecutive_failures, total_requests, total_failures, avg_response_ms | API source health monitoring |
| `league_profiles` | id, competition_id (FK), stat_key, season, avg_value, median_value, std_dev, sample_size, updated_at | League-wide stat averages for contextual comparison |

### Schema Observations

- **Dual-write pattern:** All scripts write to both JSON cache (`stats_cache/`) and SQLite DB. JSON is the primary read path; DB is a structured backup.
- **`teams.venue` column exists** but is never populated by any API client or adapter.
- **`teams.style_tags` column exists** (for "pressing", "defensive", etc.) but is never populated.
- **No `injuries` table** — the schema has no provision for injury/suspension tracking.
- **No `referees` table** — no data model for referee assignments.
- **No `coaches` table** — no data model for coaching staff.
- **`league_profiles`** is defined and has a builder script (`build_league_profiles.py`) — provides competition-level statistical context.

---

## 6. Consumer Requirements vs Supply

### What `deep_stats_report.py` (S3 Analysis) Needs

| Section | Data Required | Supplied By | Gap |
|---------|---------------|-------------|-----|
| §S3.1 H2H Analysis | Per-stat H2H meeting history | `stats_cache/{sport}/{team}.json → h2h → {opponent}` | ✅ Football/Basketball/Hockey have it; ❌ Tennis/Volleyball/Handball/niche sports don't |
| §S3.2 Form & Stats Table | L10 and L5 averages per stat key | `stats_cache/{sport}/{team}.json → form → l10_avg/l5_avg` | ✅ Tier 1 sports; ❌ Volleyball/Handball cache files completely empty |
| §S3.3 Market Ranking (§3.0) | L10 per-match values, H2H values, lines | `compute_safety_scores.py` consuming JSON input | ✅ Works when cache data exists; ❌ Fails silently for missing data |
| §S3.4 Three-Way Cross-Check | L10 avg, H2H avg, L5 trend — all must support direction | `compute_safety_scores.py` | ✅ When all 3 sources have data; 🟡 Degrades when H2H missing (penalty applied) |
| §S3.5 Coach/Roster Stability | `cache.coach`, `cache.manager`, `cache.formations` | **NOT POPULATED** by any pipeline component | 🔴 Always shows "No coach/formation data available — verify manually" |
| §S3.6 Injury/Suspension Check | `cache.injuries`, `cache.suspensions`, `cache.unavailable` | **NOT POPULATED** by any pipeline component | 🔴 Always shows "No injury data in cache — verify on Flashscore/Sofascore" |
| Probability Engine | L5 values (40% weight), L10 values (35%), H2H values (25%) | Stats cache per-match arrays | ✅ When data exists; Poisson model + bootstrap CI |

### What `compute_safety_scores.py` Needs

| Input Field | Required? | Source | Gap |
|-------------|-----------|--------|-----|
| `sport` | Required | Event metadata | ✅ |
| `team_a`, `team_b` | Required | Event metadata | ✅ |
| `markets[].name` | Required | `normalize_stats.py` market definitions | ✅ |
| `markets[].line` | Required | Odds sources or standard lines | 🟡 Often missing for niche sports — falls back to standard lines |
| `markets[].team_a_l10` | Required | Stats cache → l10_matches per-match extraction | ✅ For football/basketball/hockey; ❌ for volleyball/handball |
| `markets[].team_b_l10` | Required | Stats cache | Same as above |
| `markets[].h2h_values` | Optional (penalized if missing) | Stats cache → h2h section | 🟡 Missing for most tennis, all niche sports |
| `markets[].team_a_l5` | Optional | Stats cache → recent 5 matches | ✅ Derived from L10 |

### What `gate_checker.py` Checks (17-Point Approval Gate)

| Gate # | Check | Data Source | Status |
|--------|-------|-------------|--------|
| 1 | Stats verified (L10 exists) | Stats cache | ✅ Works for Tier 1 |
| 2 | Multi-market calculation done | Safety score output | ✅ |
| 3 | H2H checked | Stats cache h2h section | 🟡 Often auto-passes because gate is lenient |
| 4 | **Injuries/suspensions checked** | `candidate.injuries` or `candidate.injury_data` | 🔴 **Never passes from data — always needs manual check flag or data_quality="FULL" override** |
| 5-17 | Various statistical checks | Safety scores, EV, cross-checks | ✅ |

---

## 7. Data Gap Analysis

### 🔴 RED — Completely Missing

| Gap | Impact | Where Expected | Current State |
|-----|--------|---------------|---------------|
| **Injury/Suspension data** | HIGH — Gate #4 never auto-passes; user must manually verify every pick | `gate_checker.py:100-109`, `deep_stats_report.py:465-481` | Code checks for `injuries`, `suspensions`, `unavailable` keys in cache — **no adapter, API client, or script populates these keys** |
| **Player-level statistics** | MEDIUM — Cannot identify key player contributions, form, or absences | All stats are team-aggregated | BallDontLie has player box scores but aggregates to team totals before caching; no per-player cache |
| **Coach/Manager data** | MEDIUM — §S3.5 always shows "verify manually" | `deep_stats_report.py:428-459` | Code checks for `coach`/`manager`/`formations` in cache — **never populated**. SerpAPI knowledge_graph sometimes has `coach` attribute but it's unstructured and not written to cache |
| **Referee data** | LOW-MEDIUM — Referee tendencies affect card/foul markets | `pipeline_orchestrator.py:971` mentions "referee" | **No data source, no schema table, no API endpoint** for referee data |
| **Motivation/Context scoring** | MEDIUM — No automated relegation/title/elimination context | `pipeline_orchestrator.py:218` mentions "model motivation effects" | **No implementation exists** — pipeline_orchestrator S5 logs it as a check item but has no data source |

### 🟡 AMBER — Exists But Shallow/Inconsistent

| Gap | Impact | Current State |
|-----|--------|---------------|
| **Volleyball stats** | HIGH for Tier 1 sport — 0 cache files | API-Volleyball client exists and has `get_fixture_stats()` but stats cache directory is empty. Volleyball fixtures exist in `fixtures/` but no enrichment has run. |
| **Handball stats** | MEDIUM — 0 cache files | Same as volleyball — API-Handball client exists but cache directory has only `fixtures/` and `h2h/` dirs. |
| **Tennis detailed stats** | HIGH — Only 3 stat keys vs 7 defined | ESPN tennis returns only sets_won/games_won/total_sets. The 4 other keys (aces, double_faults, first_serve_pct, break_points_won) are never populated. API-Tennis should provide them but the shared 100/day limit is likely the bottleneck. |
| **Odds coverage** | HIGH — ~5.6% of fixtures have API odds | `the-odds-api` (16/day), `odds-api-io` (200/day), `API-Football /odds` cover EU football + US sports. 7 sports have ZERO API odds. STATS-FIRST mode mitigates but doesn't solve. |
| **Venue/Stadium data** | LOW — `teams.venue` exists in DB but is never written | Weather script uses hardcoded coordinates (~50 cities). Scores24 extracts venue from detail pages. Sofascore API doesn't return venue. |
| **League standings** | MEDIUM — Only Football-Data.org for 10 EU leagues | `football_data_org.py` provides `get_standings()` for PL, La Liga, Bundesliga, Serie A, Ligue 1, Eredivisie, Primeira Liga, Championship, Brasileirão, Copa Libertadores. No standings for any other sport. |
| **xG (Expected Goals)** | LOW — Only 6 EU leagues via Understat | Understat covers EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL. No xG for other football leagues (MLS, Liga MX, J.League, etc.) |
| **H2H depth for tennis** | HIGH — `h2h: {}` is empty in all sampled tennis cache files | ESPN tennis doesn't provide H2H data. API-Tennis has `/games/h2h` but the 100/day shared limit means most players never get H2H enriched. |
| **Niche sport stats (snooker, darts, table_tennis, esports, padel, speedway)** | MEDIUM — No API provides stats | TheSportsDB = fixture-only on free tier. SerpAPI provides unstructured Google results. These 6 sports have defined stat_keys in `normalize_stats.py` but **zero actual data** to compute safety scores. |

### 🟢 GREEN — Well-Covered

| Dimension | Notes |
|-----------|-------|
| **Football L10/L5 stats** | ESPN provides 28+ stat keys per match. Best-in-class data quality. |
| **Basketball L10/L5 stats** | ESPN + BallDontLie + nba_api provide deep box score data. |
| **Hockey L10/L5 stats** | ESPN provides 15+ stat keys per NHL game. |
| **Baseball L10/L5 stats** | ESPN provides 12+ stat keys per MLB game. |
| **Fixture discovery** | 18 adapters + 16 API clients + multi-source deduplication. Comprehensive. |
| **Safety score calculation** | Deterministic formula: min(hit_rate_L10, hit_rate_H2H) with H2H missing penalty. Well-tested. |
| **Probability engine** | Poisson-based with recency weighting, bootstrap CI, overdispersion detection. Academically grounded. |
| **Rate limiting** | File-based daily counters, per-API locks, thread-safe. Production-quality. |
| **Caching** | 24h TTL for form, 7d for H2H, atomic writes, dual JSON+DB write. |
| **Database schema** | Normalized, indexed, FK-enforced, with migration support (currently v3). |

---

## 8. Data Flow Map

### Source → Analysis Pipeline

```
SCAN (run_full_scan_and_prepare.sh)
├── Playwright fetches 232 URLs
│   └── Each URL → site-specific adapter.parse(html, url)
│       └── Returns List[Dict] with {home, away, time, source_url, [odds], [league], [stats]}
│       └── Fields that SURVIVE: home, away, time, league, source_url
│       └── Fields that DON'T survive: adapter-specific fields (forebet_probs, corner_count, etc.)
│           are preserved in scan_summary.json but NOT used downstream
│
├── discover_fixtures.py → API fixture discovery (ESPN, API-Sports, TheSportsDB)
│   └── Returns NormalizedFixture{fixture_id, source, sport, competition, home_team, away_team, kickoff, status}
│   └── Merged with HTML scan results → deduplicated fixture list
│
├── fetch_api_stats.py → Stats enrichment
│   └── For each discovered team:
│       └── Try FALLBACK_CHAINS[sport] in order (ESPN first, SerpAPI last)
│       └── Resolve team_id → get_team_last_fixtures(10) → get_fixture_stats(each)
│       └── Returns NormalizedMatchStats{fixture_id, source, sport, home_team, away_team, date, stats{}}
│       └── Written to: stats_cache/{sport}/{team_slug}.json + SQLite team_form table
│   └── MISSING: No injury, coach, referee data is fetched in this step
│
├── fetch_odds_multi.py → Multi-source odds
│   └── Queries: the-odds-api, odds-api-io, API-Football /odds, OddsPortal scrape
│   └── Returns: odds_api_snapshot.json with bookmaker odds per market per event
│   └── Written to: odds_history table + JSON
│   └── Coverage: ~5.6% of fixtures get API odds
│
├── fetch_weather.py → Weather data
│   └── Open-Meteo free API → temperature, wind, rain probability
│   └── Only for outdoor sports with known venue coordinates
│
└── build_stats_cache.py → Cache persistence + DB dual-write

ANALYSIS (deep_stats_report.py + pipeline_orchestrator.py)
├── S3: deep_stats_report.py
│   └── READS: stats_cache/{sport}/{team}.json
│   └── NEEDS: l10_avg, l5_avg, l10_matches (per-match stats), h2h
│   └── ALSO CHECKS (but never finds): injuries, suspensions, coach, formations
│   └── COMPUTES: safety scores via compute_safety_scores.py
│   └── COMPUTES: probabilities via probability_engine.py
│
├── S5: pipeline_orchestrator.py contextual checks
│   └── READS: weather data, injury data (from ESPN — but ESPN doesn't provide injuries)
│   └── FLAGS: weather impacts, venue concerns, roster changes
│   └── NEVER HAS: referee data, motivation scoring, coach changes
│
├── S7: gate_checker.py (17-point approval)
│   └── Gate #4 (injuries) ALWAYS FAILS unless data_quality flag manually set
│   └── All statistical gates work correctly when cache data exists
│
└── S8: coupon_builder.py → Final coupon output
```

### Key Data Loss Points

1. **Adapter-specific rich fields are underutilized:** Forebet probabilities, TotalCorner corner_counts, Scores24 trends/H2H/odds — all extracted but not integrated into the safety score pipeline.
2. **No pipeline step populates injury/coach/referee data:** The code checks for these fields but no upstream step writes them.
3. **Stats enrichment depends on API quotas:** The shared 100/day API-Sports limit across 7 sport APIs means most fixtures in low-priority sports never get enriched.
4. **Tennis Elo ratings from TennisAbstract are not integrated** into the safety score or probability engine despite being collected.

---

## 9. Recommendations (Prioritized)

> **NOTE: These are observations only — no solutions or implementation details proposed.**

| Priority | Gap | Severity | Affected Sports |
|----------|-----|----------|-----------------|
| **P0** | Volleyball stats cache is completely empty despite being a Tier 1 sport | Critical | Volleyball |
| **P0** | Tennis stats limited to 3/7 defined keys (aces, double_faults, first_serve, break_points missing) | Critical | Tennis |
| **P1** | No injury/suspension data populated anywhere in the pipeline | High | All 14 sports |
| **P1** | Handball stats cache completely empty | High | Handball |
| **P1** | TennisAbstract Elo ratings not fed into safety score or probability calculations | High | Tennis |
| **P2** | Coach/manager data never populated despite code reading it | Medium | All team sports |
| **P2** | Forebet probabilities, TotalCorner data, Scores24 trends not integrated into safety scores | Medium | Football primarily |
| **P2** | H2H data empty for all tennis players | Medium | Tennis |
| **P3** | 6 niche sports (snooker, darts, table_tennis, esports, padel, speedway) have zero stat data | Medium | Niche sports |
| **P3** | `teams.venue` and `teams.style_tags` DB columns never populated | Low | All sports |
| **P3** | Referee assignment data not collected | Low | Football primarily |
| **P3** | Motivation/context scoring not implemented | Low | All sports |
| **P4** | Standings data only for 10 EU football leagues | Low | All sports except top-tier football |
| **P4** | xG data only for 6 EU leagues via Understat | Low | Football |

---

*End of audit. All findings based on direct code reading as of 2026-05-05.*
