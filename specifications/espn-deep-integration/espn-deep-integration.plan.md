# ESPN API Deep Integration — Implementation Plan

**Created:** 2026-05-07  
**Status:** Draft  
**Scope:** Enhance `src/bet/api_clients/espn.py` with 14 new endpoint families across 3 ESPN API domains

---

## Architecture Overview

### Current State

```
src/bet/api_clients/espn.py          ← ESPNClient class (~1260 lines)
  └─ Base URL: site.api.espn.com/apis/site/v2/sports/{sport}/{league}/
  └─ Methods: get_fixtures, get_fixture_stats, get_h2h, resolve_team_id, get_team_last_fixtures, get_injuries
  └─ Stat Maps: SOCCER_STAT_MAP (28), NBA_STAT_MAP (17), NHL_STAT_MAP (14), MLB_BATTING/PITCHING_MAP

scripts/api_clients/espn_adapter.py  ← ESPNMultiLeagueClient (pipeline adapter)
scripts/fetch_api_stats.py           ← Orchestrator with fallback chains
scripts/normalize_stats.py           ← NormalizedFixture, NormalizedMatchStats
```

### Target State

```
src/bet/api_clients/espn.py          ← Extended ESPNClient (+ odds, ATS, standings, gamelogs, etc.)
src/bet/api_clients/espn_odds.py     ← NEW: ESPNOddsClient (core API domain, odds-specific)
src/bet/api_clients/espn_stats.py    ← NEW: ESPNStatsClient (web API domain, player stats)
scripts/api_clients/espn_adapter.py  ← Extended adapter (wires new methods into pipeline)
scripts/normalize_stats.py           ← Extended with NormalizedOdds, NormalizedPlayerStats, NormalizedStandings
scripts/fetch_espn_odds.py           ← NEW: Standalone odds fetcher (alternative to the-odds-api)
scripts/fetch_api_stats.py           ← Extended orchestrator (uses new endpoints)
```

### ESPN API Domains

| Domain | Base URL | Auth | Purpose |
|--------|----------|------|---------|
| Site API (current) | `site.api.espn.com/apis/site/v2/sports` | None | Scoreboard, summary, teams, schedule, injuries |
| Core API (new) | `sports.core.api.espn.com/v2/sports` | None | Odds, ATS, O/U records, probabilities, power index, predictor |
| Web API (new) | `site.web.api.espn.com/apis/common/v3/sports` | None | Player gamelogs, splits, statistical leaders |
| Standings API (new) | `site.api.espn.com/apis/v2/sports` | None | Enriched standings with form |

---

## Phase 1 — ESPN Odds & ATS/O/U Records (CRITICAL)

**Goal:** Replace paid the-odds-api.com credits with ESPN's free multi-provider odds.  
**Impact:** Directly feeds EV calculation, line movement detection, ATS cover rate analysis.  
**Dependencies:** None — standalone addition.

### Task 1.1: ESPN Odds Client [CREATE]

**File:** `src/bet/api_clients/espn_odds.py`

Create dedicated client for the ESPN Core API odds domain.

**Endpoints to implement:**
```
GET sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{eventId}/competitions/{compId}/odds
GET sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{eventId}/competitions/{compId}/odds/{providerId}
```

**Provider IDs (known):**
- 1001 = Caesars
- 1002 = FanDuel  
- 1003 = DraftKings
- 1004 = ESPN BET
- 45 = Bet365 (international)

**Class structure:**
```python
class ESPNOddsClient:
    CORE_BASE = "https://sports.core.api.espn.com/v2/sports"
    
    def get_event_odds(self, sport, league, event_id, comp_id) -> list[NormalizedOdds]
    def get_provider_odds(self, sport, league, event_id, comp_id, provider_id) -> NormalizedOdds | None
    def get_all_events_odds(self, sport, league, date) -> dict[str, list[NormalizedOdds]]
```

**Response parsing — extract:**
- `spread` (point spread / handicap)
- `overUnder` (total line)
- `moneyLine` (home/away)
- `details` (opening line for movement detection)
- `provider.name` (bookmaker identification)
- `awayTeamOdds.moneyLine`, `homeTeamOdds.moneyLine` (American odds)
- `awayTeamOdds.spreadOdds`, `homeTeamOdds.spreadOdds`

**Caching:** 6-hour TTL for live odds, 7-day for historical.

**Definition of Done:**
- [ ] `ESPNOddsClient` class created with all 3 methods
- [ ] American odds converted to decimal using existing formula: `+X → 1 + X/100; −X → 1 + 100/|X|`
- [ ] Caching follows `_check_cache`/`_save_cache` pattern from `BaseAPIClient`
- [ ] All ESPN provider odds mapped to a standardized `NormalizedOdds` dataclass
- [ ] Unit tests pass with mocked ESPN responses

---

### Task 1.2: Normalized Odds Dataclass [MODIFY]

**File:** `scripts/normalize_stats.py`

Add `NormalizedOdds` dataclass after existing `NormalizedMatchStats`:

```python
@dataclass
class NormalizedOdds:
    """Normalized odds from any source (ESPN, the-odds-api, etc.)."""
    event_id: str
    source: str  # "espn-odds", "the-odds-api"
    sport: str
    home_team: str
    away_team: str
    bookmaker: str  # provider name
    timestamp: str  # ISO datetime
    markets: dict = field(default_factory=dict)
    # markets keys: "moneyline", "spread", "totals"
    # Each contains: {"home": decimal_odds, "away": decimal_odds, "line": float | None}
```

**Definition of Done:**
- [ ] `NormalizedOdds` dataclass added to `normalize_stats.py`
- [ ] Existing code unaffected (backward-compatible addition)
- [ ] Dataclass serializable via `dataclasses.asdict()`

---

### Task 1.3: ATS & Over/Under Records [CREATE]

**File:** `src/bet/api_clients/espn_odds.py` (extend from Task 1.1)

**Endpoints:**
```
GET sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/seasons/{year}/types/{type}/teams/{teamId}/ats
GET sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/seasons/{year}/types/{type}/teams/{teamId}/odds-records
```

**Methods to add:**
```python
def get_team_ats(self, sport, league, team_id, season_year, season_type=2) -> dict
def get_team_odds_records(self, sport, league, team_id, season_year, season_type=2) -> dict
```

**Returns:**
- ATS record: wins/losses/pushes against the spread
- O/U record: overs/unders (critical for totals betting)
- Home/Away splits of ATS/O/U

**Sports coverage:** NBA, NFL, NHL, MLB, NCAAF, NCAAB (NOT soccer).

**Caching:** 24-hour TTL (changes daily during season).

**Definition of Done:**
- [ ] `get_team_ats()` returns structured ATS record
- [ ] `get_team_odds_records()` returns O/U record with splits
- [ ] Results include home/away breakdown
- [ ] Graceful fallback (empty dict) for sports without ATS data (soccer)
- [ ] Unit tests with mocked responses

---

### Task 1.4: Standalone Odds Fetcher Script [CREATE]

**File:** `scripts/fetch_espn_odds.py`

CLI script to fetch ESPN odds for a given date, integrating with the pipeline.

```bash
python3 scripts/fetch_espn_odds.py --date 2026-05-07 --sports football,basketball,hockey
python3 scripts/fetch_espn_odds.py --date 2026-05-07 --event-id 401234567
```

**Output:** `betting/data/espn_odds_snapshot_{date}.json`

**Format:** Compatible with existing `odds_api_snapshot.json` so downstream scripts (`generate_market_matrix.py`) can consume either source.

**Definition of Done:**
- [ ] Script fetches odds for all events on a date across specified sports
- [ ] Output JSON matches the structure expected by `generate_market_matrix.py`
- [ ] Includes line movement data (current vs opening) where available
- [ ] Can be used as a zero-cost replacement for `fetch_odds_api.py`
- [ ] Logs provider coverage per event

---

### Task 1.5: Wire Odds into Market Matrix [MODIFY]

**File:** `scripts/generate_market_matrix.py`

Add ESPN odds as a primary odds source, with the-odds-api as fallback.

**Changes:**
- Add `--espn-odds` flag (default ON in stats-first mode)
- Load `espn_odds_snapshot_{date}.json` before `odds_api_snapshot.json`
- Merge odds from both sources (ESPN odds overwrite if newer)
- Add `odds_source` field to matrix output ("espn" or "odds-api")

**Definition of Done:**
- [ ] Market matrix uses ESPN odds when available
- [ ] Falls back to the-odds-api when ESPN odds missing
- [ ] No regression in existing matrix output format
- [ ] Decision matrix shows odds source per event

---

### Task 1.6: Expand Football League Coverage [MODIFY]

**File:** `src/bet/api_clients/espn.py`

Expand `ESPN_LEAGUES["football"]` and `COMPETITION_TO_ESPN_LEAGUE` to cover all ESPN-available soccer leagues.

**Additions (sample — full list ~260 leagues):**
```python
# Second divisions
"eng.2", "esp.2", "ger.2", "ita.2", "fra.2",
# European cups
"uefa.champions", "uefa.europa", "uefa.conference",
# International
"fifa.world", "uefa.euro", "conmebol.libertadores", "conmebol.sudamericana",
# More first divisions
"rou.1", "ukr.1", "ser.1", "cro.1", "hun.1", "bul.1", "svk.1",
"fin.1", "isr.1", "cyp.1", "geo.1", "kaz.1", "uzb.1",
# African
"rsa.1", "egy.1", "mor.1", "tun.1", "nga.1",
# Asian
"chn.1", "ind.1", "sau.1", "uae.1", "qat.1",
```

Also extend `COMPETITION_TO_ESPN_LEAGUE` with these mappings (fuzzy name → league code).

**Definition of Done:**
- [ ] `ESPN_LEAGUES["football"]` contains 60+ league codes (up from 33)
- [ ] `COMPETITION_TO_ESPN_LEAGUE` has mappings for all added leagues
- [ ] UEFA/FIFA/CONMEBOL tournament codes added
- [ ] No regression in existing league resolution
- [ ] Unit test verifies new mappings resolve correctly

---

## Phase 2 — Player Stats & Form Data (HIGH VALUE)

**Goal:** Add player-level gamelogs, splits, H2H athlete data, and league-wide statistical leaders.  
**Impact:** Enables prop bet analysis, player form tracking, and league context.  
**Dependencies:** Phase 1 not required (independent domain).

### Task 2.1: ESPN Player Stats Client [CREATE]

**File:** `src/bet/api_clients/espn_stats.py`

Dedicated client for the ESPN Web API domain (player-level data).

**Endpoints:**
```
GET site.web.api.espn.com/apis/common/v3/sports/{sport}/{league}/athletes/{id}/gamelog
GET site.web.api.espn.com/apis/common/v3/sports/{sport}/{league}/athletes/{id}/splits
GET site.web.api.espn.com/apis/common/v3/sports/{sport}/{league}/athletes/{id}/vsathlete/{opponentId}
GET site.web.api.espn.com/apis/common/v3/sports/{sport}/{league}/statistics/byathlete
```

**Class structure:**
```python
class ESPNStatsClient:
    WEB_BASE = "https://site.web.api.espn.com/apis/common/v3/sports"
    
    def get_player_gamelog(self, sport, league, athlete_id, season=None) -> list[dict]
    def get_player_splits(self, sport, league, athlete_id) -> dict
    def get_h2h_athlete(self, sport, league, athlete_id, opponent_id) -> dict
    def get_league_leaders(self, sport, league, stat_category=None) -> list[dict]
```

**Sports with gamelog support:** NBA, MLB, NHL (NOT soccer — confirmed unavailable).

**Caching:**
- Gamelogs: 24-hour TTL (updates daily during season)
- Splits: 12-hour TTL
- League leaders: 6-hour TTL

**Definition of Done:**
- [ ] `ESPNStatsClient` class with all 4 methods
- [ ] Gamelog parsing handles NBA/MLB/NHL stat structures
- [ ] Splits parsing extracts home/away/conference performance
- [ ] H2H athlete provides historical matchup stats
- [ ] League leaders sortable by stat category
- [ ] Unit tests with mocked responses per sport

---

### Task 2.2: Normalized Player Stats Dataclass [MODIFY]

**File:** `scripts/normalize_stats.py`

```python
@dataclass
class NormalizedPlayerStats:
    """Normalized player performance data."""
    athlete_id: str
    athlete_name: str
    source: str
    sport: str
    team: str
    season: str
    games: list[dict] = field(default_factory=list)  # gamelog entries
    splits: dict = field(default_factory=dict)  # home/away/conference
    # splits keys: "home", "away", "last5", "last10"
    # Each contains stat averages

@dataclass
class NormalizedStandings:
    """Normalized league standings with form data."""
    sport: str
    league: str
    season: str
    source: str
    teams: list[dict] = field(default_factory=list)
    # Each team: {name, rank, wins, draws, losses, gf, ga, gd, points, form, home_record, away_record}
```

**Definition of Done:**
- [ ] Both dataclasses added, serializable
- [ ] No impact on existing `NormalizedMatchStats` consumers

---

### Task 2.3: Integrate Gamelogs into Safety Score Pipeline [MODIFY]

**File:** `scripts/fetch_api_stats.py`

Enhance `fetch_team_stats()` to pull player gamelogs for key players (top scorers, starting pitchers) as supplementary data.

**Changes:**
- After fetching team-level L10, optionally fetch top 3 player gamelogs
- Store player data in stats cache under `{sport}/{team}/players/{player_slug}.json`
- Player data used for prop bet suggestions in market matrix

**Constraint:** Only for NBA/MLB/NHL (no soccer gamelogs).

**Definition of Done:**
- [ ] Player gamelogs fetched for top performers per team
- [ ] Data stored in cache following existing `_check_cache`/`_save_cache` pattern
- [ ] No performance regression (parallel fetching, budget-aware)
- [ ] Falls back gracefully if player endpoint returns 404/500

---

### Task 2.4: League Statistical Leaders [MODIFY]

**File:** `scripts/fetch_api_stats.py`

Add `fetch_league_leaders()` function to retrieve league-wide stat rankings.

**Purpose:** Context for safety score — "Is this team's corner average high relative to league?" helps calibrate standard lines.

**Changes:**
- New function `fetch_league_leaders(sport, league)` → stores in `betting/data/stats_cache/espn/{sport}/{league}/leaders.json`
- Called once per league per day (6-hour cache)
- Exposes percentile rank for each stat key

**Definition of Done:**
- [ ] League leaders fetched for football (corners, fouls, cards leaders), NBA (points, rebounds, assists), NHL (goals, assists, saves)
- [ ] Percentile computation working
- [ ] Cache prevents redundant fetches within same pipeline run

---

### Task 2.5: Enriched Standings with Form [CREATE]

**File:** `scripts/fetch_espn_standings.py`

**Endpoint:**
```
GET site.api.espn.com/apis/v2/sports/soccer/{league}/standings
GET site.api.espn.com/apis/v2/sports/basketball/nba/standings
GET site.api.espn.com/apis/v2/sports/hockey/nhl/standings
```

**Output:** `betting/data/stats_cache/espn/{sport}/{league}/standings.json`

**Extracts:**
- Full table: rank, W/D/L, GF/GA/GD, points, form string
- Home/Away splits: separate W/D/L for home and away
- Points per game, goals per game
- Conference/division splits (NBA, NHL)

**Definition of Done:**
- [ ] Standings fetched for all configured leagues
- [ ] Form data (last 5 results) extracted
- [ ] Home/Away record split available
- [ ] NormalizedStandings dataclass populated correctly
- [ ] 24-hour cache TTL

---

## Phase 3 — Advanced Endpoints & New Sports

**Goal:** Power Index, roster depth, predictor, win probabilities, and volleyball/rugby/cricket coverage.  
**Impact:** Provides ESPN's proprietary models + squad stability data.  
**Dependencies:** Phases 1 & 2 (uses same client infrastructure).

### Task 3.1: Win Probabilities & Predictor [MODIFY]

**File:** `src/bet/api_clients/espn_odds.py`

**Endpoints:**
```
GET sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{id}/competitions/{id}/probabilities
GET sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{id}/competitions/{id}/predictor
```

**Methods:**
```python
def get_win_probabilities(self, sport, league, event_id, comp_id) -> dict
def get_predictor(self, sport, league, event_id, comp_id) -> dict
```

**Returns:**
- `homeWinPercentage` / `awayWinPercentage` / `tiePercentage`
- Predictor factors (strength of schedule, efficiency ratings)

**Use case:** Cross-validate our safety score implied probability against ESPN's model.

**Definition of Done:**
- [ ] Both methods return structured probability data
- [ ] Probabilities expressed as 0.0-1.0 floats
- [ ] Graceful handling when predictor unavailable (some sports/events)
- [ ] Unit tests

---

### Task 3.2: Power Index (BPI/FPI) [MODIFY]

**File:** `src/bet/api_clients/espn_odds.py`

**Endpoint:**
```
GET sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/seasons/{year}/powerindex
```

**Method:**
```python
def get_power_index(self, sport, league, season_year) -> list[dict]
```

**Returns:** Team power ratings (BPI for basketball, FPI for football).

**Caching:** 24-hour TTL.

**Definition of Done:**
- [ ] Power index fetched for NBA, NCAAB, NFL, NCAAF
- [ ] Rankings include offensive/defensive ratings where available
- [ ] Data stored in `stats_cache/espn/{sport}/{league}/power_index.json`

---

### Task 3.3: Roster & Depth Charts [MODIFY]

**File:** `src/bet/api_clients/espn.py` (extend existing client)

**Endpoints:**
```
GET site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{id}/roster
GET site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{id}/depthcharts
```

**Methods:**
```python
def get_team_roster(self, team_id) -> list[dict]
def get_depth_chart(self, team_id) -> dict
```

**Purpose:** Coach/roster stability analysis (referenced in sport-analysis-protocols §3.0).

**Definition of Done:**
- [ ] Roster returns player list with position, status, jersey number
- [ ] Depth chart returns positional hierarchy
- [ ] 24-hour cache TTL
- [ ] Works for all team sports (soccer, NBA, NHL, MLB)

---

### Task 3.4: Transactions [MODIFY]

**File:** `src/bet/api_clients/espn.py`

**Endpoint:**
```
GET site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{id}/transactions
```

**Method:**
```python
def get_team_transactions(self, team_id, limit=25) -> list[dict]
```

**Purpose:** Detect recent roster moves that impact team strength.

**Definition of Done:**
- [ ] Transactions fetched with date, type, player, description
- [ ] 12-hour cache TTL
- [ ] Parseable for "trade", "waive", "sign", "call-up" categories

---

### Task 3.5: Coaches [MODIFY]

**File:** `src/bet/api_clients/espn.py`

**Endpoint:**
```
GET sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/seasons/{year}/coaches
```

**Method:**
```python
def get_league_coaches(self, season_year=None) -> list[dict]
```

**Purpose:** Coach stability analysis — new coach = unpredictable form.

**Definition of Done:**
- [ ] Coach list with name, team, tenure (years)
- [ ] 7-day cache TTL (rarely changes)
- [ ] Supports NBA, NHL, MLB

---

### Task 3.6: Volleyball (FIVB) Support [MODIFY]

**File:** `src/bet/api_clients/espn.py`

Add volleyball to `ESPN_SPORT_MAP` and `ESPN_LEAGUES`:
```python
ESPN_SPORT_MAP["volleyball"] = "volleyball"
ESPN_LEAGUES["volleyball"] = ["fivb.m", "fivb.w", "ncaa.w"]
```

**Endpoints:** Standard scoreboard + summary work for volleyball.

**Constraint:** Only FIVB + NCAA — domestic leagues (PlusLiga, Serie A1) NOT covered by ESPN.

**Definition of Done:**
- [ ] Volleyball fixtures discoverable via ESPN scoreboard
- [ ] Volleyball match stats parsed (sets, points, aces, blocks)
- [ ] Stat map created: `VOLLEYBALL_STAT_MAP`
- [ ] ESPN adapter handles volleyball sport
- [ ] Integration test with FIVB fixtures

---

### Task 3.7: Pipeline Adapter Update [MODIFY]

**File:** `scripts/api_clients/espn_adapter.py`

Wire all new ESPN capabilities into the pipeline adapter:

**Changes:**
- Import and expose `ESPNOddsClient` via `get_event_odds()`, `get_team_ats()`
- Import and expose `ESPNStatsClient` via `get_player_gamelog()`, `get_league_leaders()`
- Add `get_standings()` method
- Add volleyball to multi-league iteration
- Add convenience method `get_enriched_fixture_data()` that bundles: stats + odds + standings context

**Definition of Done:**
- [ ] Adapter exposes all P1/P2/P3 methods
- [ ] Existing `get_fixtures()`, `get_fixture_stats()` unchanged
- [ ] New methods accessible from `fetch_api_stats.py`
- [ ] No breaking changes to existing pipeline

---

## Test Strategy

### Unit Tests

| File | Tests |
|------|-------|
| `tests/test_espn_odds.py` [CREATE] | Mock ESPN Core API responses, verify odds parsing, ATS extraction, probability parsing |
| `tests/test_espn_stats.py` [CREATE] | Mock ESPN Web API responses, verify gamelog/splits/leaders parsing |
| `tests/test_espn_client.py` [MODIFY] | Add tests for new methods (roster, depth chart, transactions, coaches, volleyball) |
| `tests/test_normalize_stats.py` [MODIFY] | Test NormalizedOdds, NormalizedPlayerStats, NormalizedStandings serialization |
| `tests/test_fetch_espn_odds.py` [CREATE] | Test CLI script argument parsing, output format |

### Integration Tests

| Scope | Approach |
|-------|----------|
| ESPN Odds vs the-odds-api | Compare odds for same event from both sources — verify format compatibility |
| Standings accuracy | Fetch real standings for EPL, verify against known table |
| Gamelog completeness | Fetch NBA player gamelog, verify game count matches season |

### Regression Tests

- Run existing `test_espn_client.py` suite — must pass unchanged
- Run existing `test_fetch_api_stats.py` — must pass unchanged
- Run `test_compute_safety_scores.py` — safety input format unchanged

---

## Dependency Graph

```
Phase 1:
  Task 1.2 (NormalizedOdds) ──┐
  Task 1.1 (OddsClient)   ────┼─→ Task 1.4 (Fetcher Script) ─→ Task 1.5 (Market Matrix)
  Task 1.3 (ATS/O/U)      ────┘
  Task 1.6 (League expansion) — independent

Phase 2:
  Task 2.2 (Dataclasses) ─────┐
  Task 2.1 (StatsClient) ─────┼─→ Task 2.3 (Safety Pipeline) ─→ Task 2.4 (League Leaders)
                               └─→ Task 2.5 (Standings)

Phase 3:
  Task 3.1-3.5 — independent of each other, depend on P1 client infrastructure
  Task 3.6 (Volleyball) — independent
  Task 3.7 (Adapter) — depends on ALL previous tasks
```

---

## Caching Strategy

| Data Type | TTL | Rationale |
|-----------|-----|-----------|
| Live odds | 6 hours | Changes frequently during game day |
| Historical match stats | 7 days (168h) | Final scores don't change |
| Team schedule | 12 hours | New games scheduled |
| ATS/O/U records | 24 hours | Updates after each game |
| Standings | 24 hours | Updates after matchday |
| Player gamelogs | 24 hours | New game logs added daily |
| Player splits | 12 hours | Accumulative — changes gradually |
| League leaders | 6 hours | Stat rankings shift frequently |
| Roster/depth chart | 24 hours | Roster moves rare |
| Coaches | 7 days | Coaching changes very rare |
| Power index | 24 hours | ESPN model updates daily |

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| ESPN changes API structure without notice | Robust error handling; all new methods return `None`/empty on failure; version-check in response parsing |
| Core API domain unavailable | Fall through to existing the-odds-api.com for odds; player stats degrade gracefully |
| Rate limiting (unlikely but possible) | Aggressive caching; sequential per-league fetching; exponential backoff already in `_request()` |
| Large league list slows fixture discovery | Cache fixture lists per league; parallel fetching with ThreadPoolExecutor |
| Player gamelog endpoints return 500 for some sports | Sport-specific allowlist (NBA/MLB/NHL only); skip on 500 |
| ATS not available for soccer | Sport-guard: only query ATS for US sports (NBA/NHL/MLB/NFL) |

---

## File Summary

| Action | File Path | Phase |
|--------|-----------|-------|
| [CREATE] | `src/bet/api_clients/espn_odds.py` | P1 |
| [CREATE] | `src/bet/api_clients/espn_stats.py` | P2 |
| [CREATE] | `scripts/fetch_espn_odds.py` | P1 |
| [CREATE] | `scripts/fetch_espn_standings.py` | P2 |
| [CREATE] | `tests/test_espn_odds.py` | P1 |
| [CREATE] | `tests/test_espn_stats.py` | P2 |
| [CREATE] | `tests/test_fetch_espn_odds.py` | P1 |
| [MODIFY] | `src/bet/api_clients/espn.py` | P1 (leagues), P3 (roster/transactions/coaches/volleyball) |
| [MODIFY] | `scripts/normalize_stats.py` | P1 (NormalizedOdds), P2 (NormalizedPlayerStats, NormalizedStandings) |
| [MODIFY] | `scripts/api_clients/espn_adapter.py` | P3 (wire everything) |
| [MODIFY] | `scripts/fetch_api_stats.py` | P2 (gamelogs, leaders) |
| [MODIFY] | `scripts/generate_market_matrix.py` | P1 (ESPN odds integration) |
| [MODIFY] | `tests/test_espn_client.py` | P3 (new method tests) |
| [MODIFY] | `tests/test_normalize_stats.py` | P1+P2 (new dataclass tests) |

---

## Implementation Notes

1. **American odds conversion** — reuse existing formula from `config/` docs: `+X → 1 + X/100; −X → 1 + 100/|X|`
2. **ESPN event IDs** — the same `event.id` from scoreboard works across all API domains (Core, Web, Site)
3. **Competition ID** — typically same as event ID for single-competition events; for multi-competition events (MMA cards), use `competitions[0].id`
4. **Season types** — ESPN uses: 1=preseason, 2=regular, 3=postseason, 4=offseason
5. **No soccer gamelogs** — confirmed limitation; don't attempt `get_player_gamelog` for football sport
6. **Volleyball stat map** — ESPN uses: `kills`, `aces`, `blocks`, `digs`, `assists`, `errors`, `hittingPercentage`
7. **The-odds-api remains** — ESPN odds supplement but don't fully replace (ESPN lacks some European bookmakers); both sources merged in matrix
