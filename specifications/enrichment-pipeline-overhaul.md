# Technical Specification: Enrichment Pipeline Overhaul

**Date:** 2026-05-18  
**Status:** Draft  
**Scope:** `scripts/data_enrichment_agent.py`, `scripts/flashscore_enricher.py`, new helpers

---

## 1. Solution Architecture

### Current State (Broken)

```
enrich_team(team, sport)
  ├── _try_client_enrichment()     → needs DB fixtures with matching external_id (rarely available)
  ├── TotalCorner                  → football-only, needs TC-sourced fixtures (niche)
  ├── Scores24 trends              → needs scores24-sourced fixtures (niche)
  ├── _try_flashscore()            → fetches HTML results page → regex parse → ZERO DATA (JS SPA)
  ├── _try_scores24()              → fetches scores24 HTML → same regex parser → ZERO DATA
  └── web_research_agent           → L7 last resort (expensive)
```

**Root causes of failure:**
1. `_parse_flashscore_stats()` uses regex on shell HTML — Flashscore is a JS SPA, stats load via XHR
2. `_fetch_espn_deep()` maps football to `("soccer", "")` — empty league → 404  
3. `_try_scores24()` reuses the same broken regex parser
4. The UnifiedAPIClient path only works when DB already has fixtures with matching `external_id`

### Target State

```
enrich_team(team, sport)
  ├── [PRIMARY] ESPN API             → ESPNClient (all 5 sports, free, unlimited, JSON)
  │     └── Iterates leagues, finds team, gets last 10 fixture stats
  ├── [FOOTBALL] API-Football        → APIFootballClient (1000+ leagues, rich stats, key exists)
  │     └── Team search → last fixtures → per-fixture stats
  ├── [FALLBACK] Flashscore Data API → d.flashscore.com/x/feed/ endpoints (curl_cffi)
  │     └── Entity resolution (works) → team results feed → match stat feeds
  └── [REMOVED] Dead code paths
```

### Data Flow

```
                  ┌─────────────────────┐
                  │  enrich_team(team)   │
                  └────────┬────────────┘
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
     ┌─────────────┐ ┌──────────┐ ┌────────────────┐
     │ ESPN Client  │ │ API-Ftbl │ │ Flashscore Feed│
     │ (all sports)│ │ (footb.) │ │ (all sports)   │
     └──────┬──────┘ └────┬─────┘ └───────┬────────┘
            │              │               │
            ▼              ▼               ▼
     ┌──────────────────────────────────────────────┐
     │          stats: {stat_key: [v1,v2,...v10]}    │
     └──────────────────────────────┬───────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼                               ▼
           ┌──────────────┐                ┌──────────────┐
           │  _save_to_db │                │_save_to_cache│
           │  (team_form) │                │  (JSON file) │
           └──────────────┘                └──────────────┘
```

---

## 2. Implementation Plan

### Phase 1: Fix ESPN as Primary Source [MODIFY]

**Target:** `scripts/data_enrichment_agent.py`  
**Impact:** All 5 sports get working enrichment immediately

The existing `_fetch_espn_deep()` function uses raw `urllib` with a broken sport mapping that gives empty league for football. The proper `ESPNClient` in `src/bet/api_clients/espn.py` already handles multi-league iteration, stat mapping, and JSON parsing.

#### Task 1.1: Rewrite `_fetch_espn_deep()` to use ESPNClient

Replace the ~80-line raw urllib implementation with a proper call through the existing ESPN infrastructure.

**Changes:**
```python
def _fetch_espn_stats(team_name: str, sport: str, competition: str = "") -> dict[str, list[float]]:
    """Fetch L10 per-match stats from ESPN API using the proper ESPNClient.
    
    Returns: {stat_key: [val_match1, val_match2, ...]} (up to 10 matches)
    """
    from bet.api_clients.espn import ESPNClient, ESPN_LEAGUES, get_espn_league_for_competition
    from bet.api_clients.rate_limiter import RateLimiter
    
    rate_limiter = RateLimiter()
    stats_accumulator: dict[str, list[float]] = {}
    
    # Determine leagues to search
    leagues = ESPN_LEAGUES.get(sport, [])
    if not leagues:
        return {}
    
    # If competition is known, prioritize that league
    if competition:
        target_league = get_espn_league_for_competition(competition)
        if target_league:
            leagues = [target_league] + [l for l in leagues if l != target_league]
    
    # Search for team across leagues (stop at first hit)
    team_id = None
    found_league = None
    for league in leagues[:10]:  # Cap to avoid 60+ league iteration
        client = ESPNClient(sport=sport, league=league, rate_limiter=rate_limiter)
        team_id = client.resolve_team_id(team_name)
        if team_id:
            found_league = league
            break
    
    if not team_id or not found_league:
        return {}
    
    # Get recent fixtures for this team
    client = ESPNClient(sport=sport, league=found_league, rate_limiter=rate_limiter)
    # ... fetch scoreboard for recent dates, find team's fixtures, get stats per fixture
```

**Key design decisions:**
- Use `ESPNClient.resolve_team_id()` (already fuzzy-matches team names)
- Use `ESPNClient.get_fixture_stats()` per fixture for deep stats
- Leverage `ESPN_LEAGUES` mapping (60+ football leagues already defined)
- Use `get_espn_league_for_competition()` for fast league resolution when competition name is known
- Cap league search at first 10 if no competition hint (avoid 60-league scan)

#### Task 1.2: Add team fixture history lookup via ESPN scoreboard

ESPN doesn't have a direct "team recent games" endpoint that returns fixture IDs reliably without a date range. Strategy:

- Use ESPN scoreboard endpoint with date range (last 30 days)
- OR use the `/teams/{team_id}/schedule` endpoint (which `_fetch_espn_deep` already uses, but incorrectly)
- Extract fixture IDs of completed games → call `get_fixture_stats()` for each

```python
# ESPN team schedule endpoint works: 
# GET /apis/site/v2/sports/{sport}/{league}/teams/{team_id}/schedule
# Returns: {events: [{id, date, competitions: [...]}]}
```

#### Task 1.3: Convert ESPN stats to enrichment format

ESPN `get_fixture_stats()` returns:
```python
APIMatchStats(stats={"corners": {"home": 7, "away": 3}, "fouls": {"home": 12, "away": 15}})
```

Enrichment needs:
```python
{"corners": [7, 5, 8, 6, 9, ...], "fouls": [12, 18, 14, ...]}  # per-match values for our team
```

Transform by determining which side (home/away) our team was on, per match.

**Definition of Done:**
- [ ] `_fetch_espn_stats()` implemented using proper ESPNClient
- [ ] Returns `dict[str, list[float]]` with per-match stat values (up to 10 games)
- [ ] Works for all 5 sports: football, basketball, hockey, tennis, volleyball
- [ ] Football correctly resolves league from competition name
- [ ] Unit test: mock ESPN responses, verify stat extraction for football + basketball

---

### Phase 2: Flashscore Data API [MODIFY]

**Target:** `scripts/flashscore_enricher.py`  
**Impact:** Provides structured JSON data for all 5 sports as fallback

#### Task 2.1: Implement Flashscore team results feed

The Flashscore internal API serves data at `d.flashscore.com/x/feed/` endpoints. Based on community reverse-engineering:

**Team last results:**
```
GET https://d.flashscore.com/x/feed/f_2_{entity_id}
Headers: x-fsign: SW9D1eZo
```

Returns a proprietary format with recent match results including event IDs.

**Implementation:**
```python
def _fetch_flashscore_team_results(entity_id: str, sport: str) -> list[dict]:
    """Fetch team's recent results from Flashscore data feed.
    
    Returns list of match dicts: [{event_id, home, away, score_home, score_away, date}, ...]
    """
    url = f"https://d.flashscore.com/x/feed/f_2_{entity_id}"
    headers = {"x-fsign": "SW9D1eZo", **_FS_HEADERS}
    
    resp = c_requests.get(url, impersonate=_FS_IMPERSONATE, headers=headers, timeout=10)
    if resp.status_code != 200:
        return []
    
    return _parse_flashscore_feed(resp.text, sport)
```

#### Task 2.2: Implement Flashscore match statistics feed

**Per-match statistics:**
```
GET https://d.flashscore.com/x/feed/d_st_{event_id}
Headers: x-fsign: SW9D1eZo
```

Returns match statistics (corners, fouls, shots, etc.) in proprietary format.

**Implementation:**
```python
def _fetch_flashscore_match_stats(event_id: str, sport: str) -> dict[str, dict[str, float]]:
    """Fetch per-match stats from Flashscore data feed.
    
    Returns: {"corners": {"home": 7, "away": 3}, "fouls": {"home": 12, "away": 15}}
    """
    url = f"https://d.flashscore.com/x/feed/d_st_{event_id}"
    headers = {"x-fsign": "SW9D1eZo", **_FS_HEADERS}
    
    resp = c_requests.get(url, impersonate=_FS_IMPERSONATE, headers=headers, timeout=10)
    if resp.status_code != 200:
        return {}
    
    return _parse_flashscore_stats_feed(resp.text, sport)
```

#### Task 2.3: Implement feed parser

Flashscore feeds use a proprietary text format (pipe-delimited with specific field codes). Requires empirical testing to determine exact format. The implementation must:

1. Fetch a real feed response
2. Analyze the format structure
3. Build a parser

**CRITICAL NOTE:** This phase requires live testing to validate the endpoint format. The exact URL patterns and response formats need empirical verification. If `d.flashscore.com/x/feed/` endpoints have changed or require additional auth, this phase becomes secondary to Phase 1 (ESPN) which is guaranteed to work.

#### Task 2.4: Rewrite `_try_flashscore()` to use data feed

Replace the current flow:
```
entity_resolution → fetch results HTML page → regex parse (broken)
```

With:
```
entity_resolution → team results feed (JSON) → per-match stats feed (JSON) → structured data
```

**Definition of Done:**
- [ ] `_fetch_flashscore_team_results()` fetches team's recent match IDs
- [ ] `_fetch_flashscore_match_stats()` fetches per-match stats  
- [ ] `_try_flashscore()` returns real structured data
- [ ] Feed parser handles the Flashscore proprietary format
- [ ] Tested with 3+ known teams across 2+ sports
- [ ] Falls back gracefully if feed endpoints return errors

---

### Phase 3: Wire API-Football for Football Enrichment [MODIFY]

**Target:** `scripts/data_enrichment_agent.py`  
**Impact:** Rich stats for all football leagues (corners, fouls, cards, shots)

#### Task 3.1: Add API-Football enrichment path

```python
def _fetch_api_football_stats(team_name: str, competition: str = "") -> dict[str, list[float]]:
    """Fetch L10 stats from API-Football (football only).
    
    Uses APIFootballClient from scripts/api_clients/api_football.py.
    API key available in config/api_keys.json.
    """
    from api_clients.api_football import APIFootballClient
    from api_clients.rate_limiter import RateLimiter
    
    client = APIFootballClient(rate_limiter=RateLimiter())
    if not client.is_available():
        return {}
    
    # Search team → get team_id
    # Get last fixtures for team → get fixture stats for each
    # Accumulate per-match stat values
```

The `APIFootballClient` already implements:
- `get_fixtures(date)` → list of fixtures
- `get_fixture_stats(fixture_id)` → NormalizedMatchStats with corners, fouls, cards, etc.
- `get_h2h(team1_id, team2_id)` → head-to-head data

Need to add team search (API-Football has `/teams?search={name}` endpoint).

#### Task 3.2: Add team search to APIFootballClient

```python
def search_team(self, team_name: str) -> str | None:
    """GET /teams?search={name} → team ID or None."""
    data = self._request("/teams", params={"search": team_name})
    results = data.get("response", [])
    if results:
        return str(results[0].get("team", {}).get("id", ""))
    return None

def get_team_fixtures(self, team_id: str, last_n: int = 10) -> list[str]:
    """GET /fixtures?team={id}&last={n} → list of fixture IDs (finished only)."""
    data = self._request("/fixtures", params={"team": team_id, "last": last_n, "status": "FT"})
    return [str(f["fixture"]["id"]) for f in data.get("response", []) if f.get("fixture")]
```

#### Task 3.3: Integrate into enrichment chain

In `enrich_team()`, add API-Football as second source for football:

```python
# After ESPN attempt for football:
if sport == "football" and not stats:
    stats = _fetch_api_football_stats(team_name, competition)
    if stats:
        source = "api-football"
```

**Definition of Done:**
- [ ] `search_team()` and `get_team_fixtures()` added to APIFootballClient
- [ ] `_fetch_api_football_stats()` function in data_enrichment_agent.py
- [ ] Returns per-match stats (corners, fouls, yellow_cards, shots, shots_on_target, possession)
- [ ] Respects API-Football rate limits (10 req/min on free tier)
- [ ] Tested with 3+ football teams from different leagues

---

### Phase 4: Clean Up Dead Code [MODIFY]

**Target:** Both `flashscore_enricher.py` and `data_enrichment_agent.py`

#### Task 4.1: Remove broken regex parsers from `flashscore_enricher.py`

**Remove:**
- `_parse_flashscore_stats()` — regex on SPA HTML (never works)
- `_parse_flashscore_deep()` — regex on SPA HTML (never works)
- `_extract_stat_values()` — helper for broken parser
- `_extract_match_scores()` — helper for broken parser
- `_build_flashscore_url()` — builds URL for HTML page fetch (no longer needed)
- All regex label maps (200+ lines of dead mapping code)

**Keep:**
- `SPORT_IDS_FS` — used by entity resolution
- `SPORT_STAT_KEYS` — used for validation
- `SPORT_VALUE_RANGES` — used for range validation
- `_get_flashscore_entity()` — entity resolution (WORKS)
- `_rate_limit()` — still needed
- `_slugify()` — general utility

#### Task 4.2: Remove broken fallbacks from `data_enrichment_agent.py`

**Remove:**
- `_try_scores24()` — uses broken regex parser on scores24 SPA HTML
- `_build_scores24_url()` — resolves scores24 URLs (only used by broken _try_scores24)
- Scores24 circuit breaker logic
- TotalCorner special case (niche, rarely has matching fixtures)
- The web_research_agent L7 fallback (not needed when primary sources work)

**Keep:**
- `_try_client_enrichment()` — keep as potential future path (when DB has external_ids)
- All `_save_*` functions
- `_compute_enrichment_quality()`
- `batch_enrich()` and `main()`

#### Task 4.3: Simplify `enrich_team()` fallback chain

New chain (clear, ordered, each source actually works):

```python
def enrich_team(team_name: str, sport: str, competition: str = "") -> dict:
    # 1. ESPN (all 5 sports, free, unlimited)
    stats = _fetch_espn_stats(team_name, sport, competition)
    if stats:
        _save_to_cache(team_name, sport, stats, "espn")
        _save_to_db(team_name, sport, stats, "espn")
        return _build_result(team_name, sport, stats, "espn")
    
    # 2. API-Football (football only, 1000+ leagues)
    if sport == "football":
        stats = _fetch_api_football_stats(team_name, competition)
        if stats:
            _save_to_cache(team_name, sport, stats, "api-football")
            _save_to_db(team_name, sport, stats, "api-football")
            return _build_result(team_name, sport, stats, "api-football")
    
    # 3. Flashscore Data API (all 5 sports, fallback)
    stats = _try_flashscore_data_api(team_name, sport)
    if stats:
        _save_to_cache(team_name, sport, stats, "flashscore")
        _save_to_db(team_name, sport, stats, "flashscore")
        return _build_result(team_name, sport, stats, "flashscore")
    
    # Failed
    return _build_failed_result(team_name, sport, errors)
```

**Definition of Done:**
- [ ] All dead regex parser code removed from flashscore_enricher.py  
- [ ] Broken fallbacks removed from data_enrichment_agent.py
- [ ] `enrich_team()` uses clean 3-source chain
- [ ] No imports of removed functions remain
- [ ] File still passes basic syntax check (python -c "import data_enrichment_agent")

---

### Phase 5: Live Testing Protocol

#### Task 5.1: ESPN validation script

```bash
PYTHONPATH=src .venv/bin/python3 -c "
from bet.api_clients.espn import ESPNClient, ESPN_LEAGUES
from bet.api_clients.rate_limiter import RateLimiter
# Test football
c = ESPNClient('football', 'eng.1', RateLimiter())
tid = c.resolve_team_id('Arsenal')
print(f'Arsenal team_id: {tid}')
# ... get fixtures, stats
"
```

Test matrix:
| Sport | Team | Expected Stats |
|-------|------|---------------|
| football | Arsenal | corners, fouls, shots, yellow_cards |
| basketball | Lakers | points, rebounds, assists |
| hockey | Boston Bruins | shots, pim, hits |
| tennis | Djokovic | aces, double_faults |
| volleyball | Brazil | aces, blocks, errors |

#### Task 5.2: API-Football validation

```bash
PYTHONPATH=src .venv/bin/python3 scripts/data_enrichment_agent.py --team "Arsenal" --sport football --verbose
```

Verify output shows:
- Source: espn or api-football (not flashscore/scores24)
- stats_found includes sport-appropriate keys
- Status: enriched or partial (not failed)

#### Task 5.3: Full batch test

```bash
PYTHONPATH=src .venv/bin/python3 scripts/data_enrichment_agent.py --date 2026-05-18 --verbose
```

Verify:
- Enrichment rate > 60% (vs current ~0%)
- Sources used: espn, api-football (not flashscore HTML parsers)
- DB writes succeed (check team_form table)

**Definition of Done:**
- [ ] ESPN returns stats for ≥1 team per sport
- [ ] API-Football returns stats for ≥3 football teams
- [ ] Full date-based enrichment shows >60% success rate
- [ ] DB team_form table populated with new data

---

## 3. Test Plan

### Unit Tests

| Test | File | What it validates |
|------|------|-------------------|
| test_espn_stats_extraction | tests/test_enrichment.py | ESPN stat response → per-match values |
| test_api_football_search | tests/test_enrichment.py | Team search → fixture → stats |
| test_flashscore_feed_parse | tests/test_enrichment.py | Feed parser handles real response format |
| test_enrich_team_chain | tests/test_enrichment.py | Fallback chain progresses correctly |
| test_stat_validation | tests/test_enrichment.py | Range filtering works per sport |

### Integration Tests (Live)

Run against real APIs with known teams:
```bash
PYTHONPATH=src .venv/bin/python3 -m pytest tests/test_enrichment_live.py -v --timeout=60
```

Tests:
- `test_espn_football_arsenal` — verifies corners/fouls/shots returned
- `test_espn_basketball_lakers` — verifies points/rebounds/assists
- `test_api_football_barcelona` — verifies rich football stats
- `test_full_enrich_team` — end-to-end: team in, DB populated out

---

## 4. Security Considerations

- **API Keys:** `api-football` key read from `config/api_keys.json` (gitignored). Never logged.
- **Rate Limiting:** ESPN (no limit), API-Football (10 req/min free), Flashscore (1.5s gap enforced)
- **No credential exposure:** curl_cffi impersonation uses standard browser headers, not credentials
- **Input validation:** Team names sanitized via `_slugify()` before URL construction (prevents injection)
- **Flashscore x-fsign:** Static token (publicly documented), not a secret

---

## 5. Quality Assurance

### Automated Verification
- `python -c "import data_enrichment_agent"` — syntax/import check
- `PYTHONPATH=src .venv/bin/python3 -m pytest tests/ -k enrichment` — unit tests pass
- `--verbose` flag shows which source provided data (traceability)
- `AGENT_SUMMARY` JSON output includes source breakdown metrics

### Code Review Checklist
- [ ] No regex HTML parsing remains for JS SPA pages
- [ ] ESPN football uses proper league resolution (not empty string)
- [ ] All API calls have timeouts and error handling
- [ ] Rate limits enforced per source
- [ ] DB writes use existing `_save_to_db()` with range validation
- [ ] No Playwright imports/usage for Flashscore (curl_cffi only, per repo rules)
- [ ] Thread safety maintained (no global mutable state without locks)

---

## 6. Files Affected Summary

| File | Action | Description |
|------|--------|-------------|
| `scripts/data_enrichment_agent.py` | MODIFY | Rewrite `_fetch_espn_deep()`, add `_fetch_espn_stats()`, add `_fetch_api_football_stats()`, simplify `enrich_team()`, remove dead fallbacks |
| `scripts/flashscore_enricher.py` | MODIFY | Remove regex parsers, add data feed functions, keep entity resolution |
| `scripts/api_clients/api_football.py` | MODIFY | Add `search_team()`, `get_team_fixtures()` methods |
| `tests/test_enrichment.py` | CREATE | Unit tests for new enrichment functions |
| `tests/test_enrichment_live.py` | CREATE | Integration tests against real APIs |

---

## 7. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Flashscore feed endpoints changed/blocked | Medium | Low | ESPN is primary; Flashscore is fallback only |
| API-Football rate limit hit | Low | Low | 10 req/min is generous for enrichment; caching reduces calls |
| ESPN doesn't cover minor leagues | Medium | Medium | API-Football covers 1000+ leagues as fallback |
| Flashscore feed format undocumented | High | Medium | Phase 2 is experimental — if feeds don't work, ESPN+API-Football cover 90%+ of cases |

---

## 8. Implementation Order (Recommended)

1. **Phase 1** (ESPN fix) — Highest impact, lowest risk. Single function rewrite gives working enrichment for ALL sports immediately.
2. **Phase 4** (Dead code cleanup) — Removes noise, makes codebase readable for Phase 2/3.
3. **Phase 3** (API-Football) — Adds rich football stats. Small, contained change.
4. **Phase 2** (Flashscore data API) — Experimental. Requires live testing of undocumented endpoints. Do AFTER the guaranteed wins.
5. **Phase 5** (Testing) — Run after each phase to validate incrementally.

**Estimated effort:** Phase 1 is the critical fix that unblocks everything. Phases 3 and 4 are straightforward. Phase 2 has uncertainty (feed format may require iteration).
