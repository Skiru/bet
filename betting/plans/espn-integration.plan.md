# ESPN Hidden API Integration Plan

## Overview
Integrate ESPN's free hidden API as the PRIMARY stat source for football (soccer), basketball (NBA), hockey (NHL), and baseball (MLB). ESPN provides per-game statistics with NO API key and NO rate limits, completely bypassing the API-Sports 100/day shared quota limitation.

## ESPN API Reference

### Base URL
```
http://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/
```

### Endpoints
| Endpoint | Purpose | Returns |
|----------|---------|---------|
| `/scoreboard?dates=YYYYMMDD` | Get fixtures for a date | Events with scores, status, competitors |
| `/summary?event={id}` | Full match detail | 28 soccer stats, 25 NBA stats, 14 NHL stats, boxscore, H2H, odds, commentary |
| `/teams` | All teams in league | Team IDs, names, logos |
| `/teams/{id}` | Team detail | Record (W-D-L), home/away splits, next event, standing |
| `/teams/{id}/schedule` | Team's season schedule | All season events with IDs, dates, scores |
| `/injuries` | Team injury reports | Player name, status (Out/Day-To-Day), injury type |
| `/standings` | League standings | GP, W, D, L, PTS, GD |

### Sport/League Codes
```python
ESPN_SPORT_MAP = {
    "football": "soccer",   # ESPN calls it "soccer"
    "basketball": "basketball",
    "hockey": "hockey",
    "baseball": "baseball",
}

ESPN_LEAGUES = {
    "football": [
        "eng.1", "esp.1", "ger.1", "ita.1", "fra.1",  # Top 5
        "bra.1", "arg.1", "mex.1", "usa.1", "col.1",  # Americas
        "por.1", "ned.1", "bel.1", "tur.1", "sco.1",  # Europe 2
        "pol.1", "cze.1", "aut.1", "gre.1", "den.1",  # Europe 3
        "nor.1", "swe.1", "sui.1", "aus.1", "jpn.1",  # Europe 4 + Asia/Oceania
        "idn.1", "tha.1", "ven.1", "per.1", "bol.1",  # More
        "par.1", "ecu.1", "uru.1",
    ],
    "basketball": ["nba", "wnba"],
    "hockey": ["nhl"],
    "baseball": ["mlb"],
}
```

### Stat Name Mappings (ESPN → Our Normalized Keys)

**Soccer (28 stats)**:
```python
SOCCER_STAT_MAP = {
    "wonCorners": "corners",
    "foulsCommitted": "fouls",
    "yellowCards": "yellow_cards",
    "redCards": "red_cards",
    "totalShots": "shots",
    "shotsOnTarget": "shots_on_target",
    "possessionPct": "possession",
    "offsides": "offsides",
    "saves": "saves",
    "totalPasses": "total_passes",
    "accuratePasses": "accurate_passes",
    "passPct": "pass_accuracy",
    "totalCrosses": "crosses",
    "accurateCrosses": "accurate_crosses",
    "totalLongBalls": "long_balls",
    "accurateLongBalls": "accurate_long_balls",
    "blockedShots": "blocked_shots",
    "effectiveTackles": "tackles_won",
    "totalTackles": "tackles",
    "tacklePct": "tackle_accuracy",
    "interceptions": "interceptions",
    "effectiveClearance": "clearances",
    "totalClearance": "total_clearances",
    "penaltyKickGoals": "penalty_goals",
    "penaltyKickShots": "penalty_attempts",
    "shotPct": "shot_accuracy",
    "crossPct": "cross_accuracy",
    "longballPct": "long_ball_accuracy",
}
```

**NBA (25 stats)**:
```python
NBA_STAT_MAP = {
    "totalRebounds": "rebounds",
    "offensiveRebounds": "offensive_rebounds",
    "defensiveRebounds": "defensive_rebounds",
    "assists": "assists",
    "steals": "steals",
    "blocks": "blocks",
    "turnovers": "turnovers",
    "fouls": "fouls",
    "technicalFouls": "technical_fouls",
    "flagrantFouls": "flagrant_fouls",
    "turnoverPoints": "turnover_points",
    "fastBreakPoints": "fast_break_points",
    "pointsInPaint": "points_in_paint",
    "largestLead": "largest_lead",
    "fieldGoalPct": "fg_pct",
    "threePointFieldGoalPct": "three_pt_pct",
    "freeThrowPct": "ft_pct",
}
```

**NHL (14 per-game stats)**:
```python
NHL_STAT_MAP = {
    "blockedShots": "blocked_shots",
    "hits": "hits",
    "takeaways": "takeaways",
    "shotsTotal": "shots",
    "powerPlayGoals": "power_play_goals",
    "powerPlayOpportunities": "power_play_opportunities",
    "powerPlayPct": "power_play_pct",
    "shortHandedGoals": "shorthanded_goals",
    "faceoffsWon": "faceoffs_won",
    "faceoffPercent": "faceoff_pct",
    "giveaways": "giveaways",
    "penalties": "penalties",
    "penaltyMinutes": "penalty_minutes",
    "shootoutGoals": "shootout_goals",
}
```

**MLB** (nested batting/pitching/fielding):
```python
MLB_BATTING_MAP = {
    "hits": "hits",
    "runs": "runs",
    "RBIs": "rbis",
    "homeRuns": "home_runs",
    "strikeouts": "strikeouts_batting",
    "walks": "walks",
    "stolenBases": "stolen_bases",
    "hitByPitch": "hit_by_pitch",
    "groundBalls": "ground_balls",
}
MLB_PITCHING_MAP = {
    "strikeouts": "strikeouts_pitching",
    "earnedRuns": "earned_runs",
    "hits": "hits_allowed",
    "walks": "walks_allowed",
    "saves": "saves",
    "losses": "losses",
}
```

### Key API Behaviors
- **No API key required** — just plain GET requests
- **No observed rate limits** — tested 20 req/s, 100% success
- **Status values**: Soccer uses `STATUS_FULL_TIME`, NBA/NHL use `STATUS_FINAL`, MLB uses `STATUS_FINAL`
- **Team schedule**: Returns season events. Status field is EMPTY for some completed games — use presence of scores and date < today as completion indicator
- **H2H**: Available in summary endpoint as `headToHeadGames[]`
- **Odds**: DraftKings + Bet365 moneylines, spreads, O/U in summary
- **Injuries**: Available per-league for NBA/NHL (empty for soccer currently)
- **Player stats**: Available per-game in boxscore.players[] (individual performance)

## Implementation Tasks

### Phase 1: ESPN Client [CREATE]
- [x] **T1.1**: Create `src/bet/api_clients/espn.py`
  - Class `ESPNClient` extending `BaseAPIClient`
  - Override `_load_api_key()` → return `"espn-no-key"` (so `is_available()` returns True)
  - Override `_build_headers()` → only `Accept: application/json` (no API key header)
  - Override `_request()` → skip `rate_limiter.can_request()` check, skip `rate_limiter.record_request()`
  - Constructor takes `sport` (our name: football/basketball/hockey/baseball) and `league` (ESPN code)
  - Store `ESPN_SPORT_MAP`, `ESPN_LEAGUES`, all `*_STAT_MAP` dicts as module-level constants

- [x] **T1.2**: Implement `ESPNClient.get_fixtures(date)` 
  - Call `/scoreboard?dates=YYYYMMDD`
  - Return list of `APIFixture` objects (reuse from api_football.py)
  - Map ESPN competitor names to home/away based on `homeAway` field

- [x] **T1.3**: Implement `ESPNClient.get_fixture_stats(fixture_id)`
  - Call `/summary?event={fixture_id}`
  - Extract `boxscore.teams[].statistics[]`
  - Map ESPN stat names to normalized keys using sport-specific `*_STAT_MAP`
  - For MLB: stats are nested as `statistics[].stats[]` — handle differently
  - Return list of `APIMatchStats` objects
  - Use 168h file cache (same as API-Sports)

- [x] **T1.4**: Implement `ESPNClient.resolve_team_id(team_name)`
  - Call `/teams` for the league
  - Fuzzy match team name (case-insensitive, handle abbreviations)
  - Cache team list per league with 7-day TTL
  - Return ESPN team ID as string

- [x] **T1.5**: Implement `ESPNClient.get_team_last_fixtures(team_id, last_n=10)`
  - Call `/teams/{team_id}/schedule`
  - Filter to completed games (status `STATUS_FULL_TIME`/`STATUS_FINAL` OR date < today with non-empty scores)
  - Sort by date descending, return last N
  - Return list of dicts with `id`, `date`, `home_team`, `away_team`, `score`

- [x] **T1.6**: Implement `ESPNClient.get_h2h(team1_id, team2_id, last_n=10)`
  - For a specific fixture: use summary endpoint's `headToHeadGames[]`
  - For general H2H: use schedule endpoint filtered by opponent
  - Return list of dicts

- [x] **T1.7**: Implement `ESPNClient.get_injuries()`
  - Call `/injuries` for the league
  - Return list of injury dicts per team
  - Mainly useful for NBA/NHL

- [x] **T1.8**: Implement factory functions
  - `ESPNSoccerClient(league)` — creates ESPNClient for soccer with specific league
  - `ESPNBasketballClient()` — creates ESPNClient for basketball/nba
  - `ESPNHockeyClient()` — creates ESPNClient for hockey/nhl
  - `ESPNBaseballClient()` — creates ESPNClient for baseball/mlb
  - Or: single `ESPNClient` with sport+league params, and register multiple instances

### Phase 2: Registration & Enrichment Integration [MODIFY]
- [x] **T2.1**: Update `src/bet/api_clients/__init__.py`
  - Import and register ESPN clients in CLIENT_REGISTRY
  - Use names: `"espn-football"`, `"espn-basketball"`, `"espn-hockey"`, `"espn-baseball"`

- [x] **T2.2**: Update `src/bet/scanner/discovery.py`
  - Add `API_ESPN` mapping alongside `API_SPORTS`:
    ```python
    API_ESPN = {
        "football": "espn-football",
        "basketball": "espn-basketball",
        "hockey": "espn-hockey",
        "baseball": "espn-baseball",
    }
    ```

- [x] **T2.3**: Update `src/bet/stats/enrichment.py` — `_try_api_fetch()`
  - Try ESPN client FIRST (unlimited, free)
  - Only fall back to API-Sports if ESPN fails or doesn't cover the sport/league
  - ESPN covers: football (36+ leagues), basketball (NBA), hockey (NHL), baseball (MLB)
  - API-Sports covers: football (minor leagues), basketball (non-NBA), hockey (non-NHL), volleyball (ESPN has NO volleyball)

- [x] **T2.4**: Update `enrichment.py` — handle ESPN league detection
  - For football: need to determine which ESPN league code a fixture belongs to
  - Use competition_name from the fixture to map to ESPN league code
  - If no match → fall back to API-Sports

### Phase 3: Bug Fixes [MODIFY]
- [x] **T3.1**: Fix basketball AOT status in `src/bet/api_clients/api_basketball.py`
  - Change `short == "FT"` to `short in ("FT", "AOT")` in `get_team_last_fixtures()`
  - AOT = After Over Time — needed for ~30% of NBA games

### Phase 4: Tests [CREATE]
- [x] **T4.1**: Create `tests/test_espn_client.py`
  - Test ESPNClient initialization (no API key needed)
  - Test stat mapping for all 4 sports
  - Test fixture filtering (completed games only)
  - Test team ID resolution with mocked API responses
  - Mock all HTTP requests (don't hit real ESPN API in tests)

- [x] **T4.2**: Create `tests/test_espn_enrichment.py`
  - Test that ESPN is tried before API-Sports in `_try_api_fetch()`
  - Test fallback to API-Sports when ESPN fails
  - Test that volleyball still uses API-Sports (no ESPN coverage)

## Acceptance Criteria
- [x] ESPN client successfully fetches per-game stats for soccer, NBA, NHL, MLB
- [x] Stats are correctly normalized to our stat key format
- [x] Team resolution works across all supported leagues
- [x] Enrichment pipeline uses ESPN as primary source
- [x] API-Sports remains as fallback for unsupported leagues/sports
- [x] Basketball AOT bug is fixed
- [x] All existing tests still pass
- [x] New tests cover ESPN client and integration

## Architecture Decision: ESPN as Primary Source
- **ESPN** (PRIMARY): Free, unlimited, covers major leagues with deep per-game stats
  - Soccer: 36+ leagues, 28 stats per game
  - Basketball: NBA/WNBA, 25 stats per game + player stats
  - Hockey: NHL, 14 stats per game
  - Baseball: MLB, full batting/pitching/fielding
- **API-Sports** (FALLBACK): 100/day shared quota, covers minor leagues + volleyball
  - Volleyball (ESPN has none)
  - Soccer minor leagues not in ESPN
  - International competitions

## Changelog
- 2026-05-03: Full implementation complete (Phases 1-4). 382 tests passing.
