# Deep Statistical Analysis Engine — Implementation Plan

## Task Details

| Field            | Value                                                      |
| ---------------- | ---------------------------------------------------------- |
| Jira ID          | N/A (internal initiative)                                  |
| Title            | Transform betting workflow into deep statistical analysis engine with multi-API integration |
| Description      | Build a multi-API data fetching layer, unified stats normalization pipeline, and deep analysis pool engine that produces 20+ deeply analyzed statistical events per day across all 14 sports |
| Priority         | High                                                       |
| Related Research | User request — terminal session exploring API-Sports endpoints |

## Proposed Solution

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR LAYER                           │
│  run_full_scan_and_prepare.sh  /  fetch_api_stats.py           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────┐    ┌──────────────────────────────┐  │
│  │  FIXTURE DISCOVERY    │    │  EXISTING PLAYWRIGHT SCAN     │  │
│  │  discover_fixtures.py │    │  scan_events.py + adapters/   │  │
│  │  (API-based)          │    │  (HTML scraping — unchanged)  │  │
│  └──────────┬───────────┘    └──────────┬───────────────────┘  │
│             │                            │                      │
│             ▼                            ▼                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              MERGED FIXTURE LIST                          │  │
│  │         (deduplicated by teams + date)                     │  │
│  └──────────────────────┬───────────────────────────────────┘  │
│                          │                                      │
│                          ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           API STATS ENRICHMENT                            │  │
│  │  Per fixture: fetch L10, L5, H2H stats via APIs           │  │
│  │                                                           │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐ │  │
│  │  │ API-Football │ │ API-Basket  │ │ API-Hockey          │ │  │
│  │  │ (100/day)    │ │ (100/day)   │ │ (100/day)           │ │  │
│  │  └──────┬──────┘ └──────┬──────┘ └──────┬──────────────┘ │  │
│  │         │               │               │                 │  │
│  │  ┌──────┴──────┐ ┌──────┴──────┐ ┌──────┴──────┐        │  │
│  │  │Football-Data│ │ BallDontLie │ │ (no fallback│        │  │
│  │  │ (fallback)  │ │ / nba_api   │ │  — scraping)│        │  │
│  │  └──────┬──────┘ │ (fallbacks) │ └─────────────┘        │  │
│  │         │        └─────────────┘                          │  │
│  │  ┌──────┴──────┐                                          │  │
│  │  │  Understat  │                                          │  │
│  │  │  (xG data)  │                                          │  │
│  │  └─────────────┘                                          │  │
│  └──────────────────────┬───────────────────────────────────┘  │
│                          │                                      │
│                          ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           STATS NORMALIZER (normalize_stats.py)           │  │
│  │  API response → NormalizedMatchStats → per-match arrays   │  │
│  └──────────────────────┬───────────────────────────────────┘  │
│                          │                                      │
│                          ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           STATS CACHE (build_stats_cache.py)              │  │
│  │  TTL: 24h form, 7d H2H — extended with source tracking   │  │
│  └──────────────────────┬───────────────────────────────────┘  │
│                          │                                      │
│                          ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │        SAFETY SCORE CALCULATOR (compute_safety_scores.py) │  │
│  │  Input: JSON {team_a_l10: [...], h2h_values: [...], ...}  │  │
│  │  Output: ranked markets with safety scores                 │  │
│  └──────────────────────┬───────────────────────────────────┘  │
│                          │                                      │
│                          ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │        ANALYSIS POOL (deep_analysis_pool.py)              │  │
│  │  Output: analysis_pool_YYYY-MM-DD.json + .md              │  │
│  │  20+ events × all stat markets × ranked by safety score   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │        ODDS CROSS-VALIDATION (fetch_odds_api.py)          │  │
│  │  (existing — enriches pool with odds + EV)                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  RATE LIMITER         │  File-based daily counters per API      │
│  rate_limiter.py      │  Auto-fallback when quota exhausted     │
└─────────────────────────────────────────────────────────────────┘
```

### Free API Inventory

| API | Sport Coverage | Free Tier | Key Endpoints | Stats Available |
|-----|---------------|-----------|---------------|-----------------|
| **API-Football v3** (api-sports.io) | Football: 1000+ leagues globally | 100 req/day | `/fixtures`, `/fixtures/statistics`, `/fixtures/headtohead`, `/teams/statistics`, `/leagues`, `/injuries`, `/predictions` | Corners, shots, SOT, fouls, cards, possession, passes, saves, offsides — PER MATCH |
| **API-Basketball v1** (api-sports.io) | Basketball: NBA, Euroleague, ACB, NBL, LNB, all major+minor | 100 req/day | `/games`, `/games/statistics`, `/standings` | Points, rebounds, assists, steals, blocks, turnovers, FG%, 3P%, FT% |
| **API-Hockey v1** (api-sports.io) | Hockey: NHL, KHL, SHL, DEL, Liiga, Czech, Swiss | 100 req/day | `/games`, `/games/statistics` | Goals, shots, PP, PK, hits, blocks, faceoffs, PIM |
| **Football-Data.org** | EU football: 12 leagues (EPL, LaLiga, Bundesliga, Serie A, Ligue 1, Eredivisie, Primeira, Championship, Brasileirão, SA, BL2, Serie B) | 10 req/min (~1000/day) | `/matches`, `/teams/{id}/matches`, `/competitions` | Scores, results, standings, team form (not per-match corner/foul stats) |
| **BallDontLie v2** | NBA only | Free (no key) | `/games`, `/stats`, `/season_averages`, `/players` | All NBA box score stats: pts, reb, ast, stl, blk, turnover, FG/3P/FT |
| **nba_api** (Python) | NBA only (stats.nba.com) | Free (no key, rate ~30/min) | `leaguegamefinder`, `teamgamelog`, `teamvsplayer`, `boxscoretraditionalv2` | Full NBA stats: pts, reb, ast, stl, blk, TO, +/-, pace, ORtg, DRtg |
| **TheSportsDB** | All sports (basic) | Free tier | `/eventsday.php`, `/lookupevent.php`, `/lookupteam.php`, `/searchteams.php` | Fixtures, results, team info, venue — NO per-match statistical breakdown |
| **Understat** (Python) | Football: EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL | Free (scraping) | Python package: `understat.get_league_results`, `get_team_stats` | xG, xGA, xPTS, npxG, npxGA, PPDA — per match |
| **The Odds API** (existing) | 70+ sports/leagues | 500 credits/month | `/sports/{key}/odds`, `/sports/{key}/scores` | Odds only (h2h, totals, spreads) — no match stats |

### Daily API Request Budget

| API | Daily Limit | Allocated | Reserve | Use Case |
|-----|-------------|-----------|---------|----------|
| API-Football v3 | 100 | 70 | 30 | 1 fixture list + ~25 fixture stats + ~20 H2H/team stats + ~24 reserves |
| API-Basketball v1 | 100 | 60 | 40 | 1 game list + ~25 game stats + ~15 standings + ~19 reserves |
| API-Hockey v1 | 100 | 50 | 50 | 1 game list + ~15 game stats + ~10 team stats + ~24 reserves |
| Football-Data.org | ~1000 | 200 | 800 | Team match history, standings, competition fixtures |
| BallDontLie | ~1000 | 100 | 900 | NBA game stats, season averages |
| nba_api | ~1800/hr | 200 | 1600 | NBA detailed box scores, team game logs |
| TheSportsDB | ~100 | 30 | 70 | Fixture discovery, team metadata |
| Understat | unlimited (scraping) | 50 | — | xG data for top 6 EU leagues |
| The Odds API | ~16/day (500/mo) | 16 | 0 | Odds cross-validation (existing) |
| **TOTAL** | | **~776** | | |

### Key Data Flow: API → Safety Score Input

```
API-Football /fixtures/statistics?fixture=12345
  → Response: {"statistics": [{"team": {"id": 1}, "statistics": [{"type": "Corner Kicks", "value": 7}, ...]}]}
  
normalize_stats.py
  → NormalizedMatchStats: {"corners_home": 7, "corners_away": 4, "fouls_home": 12, ...}

For team's L10: fetch last 10 fixtures → get stats for each → extract per-match values
  → team_a_l10_corners = [7, 5, 8, 6, 9, 4, 7, 6, 8, 5]

compute_safety_scores.py input:
  → {"team_a_l10": [7,5,8,6,9,4,7,6,8,5], "team_b_l10": [4,6,3,5,7,3,5,4,6,3], "h2h_values": [11,9,12,10,13], "line": 9.5, ...}
```

### Normalized Stats Schema (per-match)

```python
# Football stats keys
FOOTBALL_STATS = [
    "corners_home", "corners_away",          # Corner Kicks
    "fouls_home", "fouls_away",              # Fouls
    "yellow_cards_home", "yellow_cards_away", # Yellow Cards
    "red_cards_home", "red_cards_away",       # Red Cards
    "shots_home", "shots_away",              # Total Shots
    "shots_on_target_home", "shots_on_target_away",
    "possession_home", "possession_away",
    "goals_home", "goals_away",
    "offsides_home", "offsides_away",
    "saves_home", "saves_away",
]

# Basketball stats keys
BASKETBALL_STATS = [
    "points_home", "points_away",
    "rebounds_home", "rebounds_away",
    "assists_home", "assists_away",
    "steals_home", "steals_away",
    "blocks_home", "blocks_away",
    "turnovers_home", "turnovers_away",
    "fg_pct_home", "fg_pct_away",
    "three_pct_home", "three_pct_away",
    "ft_pct_home", "ft_pct_away",
]

# Hockey stats keys
HOCKEY_STATS = [
    "goals_home", "goals_away",
    "shots_home", "shots_away",
    "powerplay_goals_home", "powerplay_goals_away",
    "pim_home", "pim_away",
    "hits_home", "hits_away",
    "blocks_home", "blocks_away",
    "faceoff_pct_home", "faceoff_pct_away",
]
```

---

## Current Implementation Analysis

### Already Implemented

- `scripts/fetch_odds_api.py` — API integration pattern with key loading, rate tracking (via headers), response parsing, and `betting/data/` output. Provides the template for new API clients.
- `scripts/build_stats_cache.py` — TTL-based cache (24h form, 7d H2H) at `betting/data/stats_cache/{sport}/{team_slug}.json`. Functions: `read_cache()`, `update_cache()`, `is_cache_valid()`, `slugify()`.
- `scripts/compute_safety_scores.py` — Safety score calculator accepting JSON input with `team_a_l10`, `team_b_l10`, `h2h_values`, `team_a_l5`, `team_b_l5` arrays. Computes hit rates, three-way cross-check, generates markdown tables.
- `scripts/scan_events.py` — Playwright-based event scanner with domain-specific adapters.
- `scripts/adapters/__init__.py` — Adapter registry with `get_adapter(domain)` pattern.
- `scripts/aggregate_and_select.py` — Scan output aggregation with team name normalization.
- `scripts/run_full_scan_and_prepare.sh` — Bash orchestrator (venv setup → pip install → Playwright → smoke test → scan → aggregate).
- `config/betting_config.json` — Full sport/market/threshold configuration.
- `betting/sources/source-registry.md` — Source hierarchy documentation.

### To Be Modified

- `scripts/build_stats_cache.py` — Add `"api_source"` field to cache entries, add `update_from_api()` function that accepts normalized API data and stores per-match stat arrays (not just aggregates).
- `scripts/run_full_scan_and_prepare.sh` — Add new pipeline steps: API fixture discovery → API stats enrichment → analysis pool generation (after existing scan, before aggregation).
- `scripts/requirements.txt` — Add `understat`, `nba_api`, `httpx` (async HTTP for API clients).
- `config/betting_config.json` — Add `"api_config"` section with per-API rate limits, priorities, and sport mappings.
- `betting/sources/source-registry.md` — Add all new API sources to Tier A documentation.

### To Be Created

- `scripts/api_clients/__init__.py` — Package init with client registry and factory function.
- `scripts/api_clients/rate_limiter.py` — File-based daily request counter per API with auto-reset at midnight UTC.
- `scripts/api_clients/base_client.py` — Abstract base class: rate limiting, caching integration, error handling, retry logic.
- `scripts/api_clients/api_football.py` — API-Football v3 client: fixtures, fixture stats, H2H, team season stats, injuries.
- `scripts/api_clients/api_basketball.py` — API-Basketball v1 client: games, game stats, standings.
- `scripts/api_clients/api_hockey.py` — API-Hockey v1 client: games, game stats.
- `scripts/api_clients/football_data_org.py` — Football-Data.org client: matches, team matches, competitions.
- `scripts/api_clients/balldontlie.py` — BallDontLie v2 + nba_api wrapper: NBA game stats, season averages.
- `scripts/api_clients/understat_client.py` — Understat Python package wrapper: xG per match for top 6 EU leagues.
- `scripts/api_clients/thesportsdb.py` — TheSportsDB client: fixture discovery, team metadata.
- `scripts/normalize_stats.py` — Converts diverse API responses to unified per-match stat arrays compatible with `compute_safety_scores.py` input.
- `scripts/discover_fixtures.py` — Multi-API fixture discovery: finds ALL matches on a date, deduplicates, merges with Playwright scan results.
- `scripts/fetch_api_stats.py` — Main orchestrator: for a list of fixtures, fetches stats from best available API, populates cache, handles fallbacks.
- `scripts/deep_analysis_pool.py` — Generates the 20+ event analysis pool: iterates fixtures, computes all statistical markets, ranks by safety score, outputs JSON + markdown.
- `config/api_keys.json` — API keys for all services (gitignored).
- `config/api_keys.example.json` — Template showing required keys (committed).
- `tests/test_rate_limiter.py` — Unit tests for rate limiter.
- `tests/test_normalize_stats.py` — Unit tests for stats normalizer.
- `tests/test_api_football.py` — Unit tests for API-Football client (with mocked responses).
- `tests/test_deep_analysis_pool.py` — Integration tests for the analysis pool pipeline.

---

## Open Questions

| #   | Question | Answer | Status |
| --- | -------- | ------ | ------ |
| 1 | Should API keys use a single JSON file or separate files per API (like `odds_api_key.txt`)? | Single `config/api_keys.json` for all API keys, with `config/api_keys.example.json` as template. Consistent pattern. Also support env vars as override (e.g., `API_FOOTBALL_KEY`). | ✅ Resolved |
| 2 | Should API clients use `requests` (sync) or `httpx` (async)? | Use `requests` (sync) to match existing codebase pattern (`fetch_odds_api.py` uses `requests`). Async adds complexity without clear benefit since API rate limits prevent meaningful parallelism. Add `httpx` only if performance becomes an issue later. | ✅ Resolved |
| 3 | How to handle API-Sports.io team ID resolution (APIs use numeric IDs, not team names)? | Build a team name → API ID mapping cache. First call searches by name, caches the ID. Subsequent calls use cached ID. Store in `betting/data/stats_cache/_team_ids/{api_name}.json`. | ✅ Resolved |
| 4 | How deep should per-fixture stats go before rate limit concerns? | Tiered approach: Tier 1 = all fixtures (1 req), Tier 2 = team season stats for shortlisted fixtures (~2 req/fixture), Tier 3 = H2H for top candidates (~1 req/fixture), Tier 4 = per-match detailed stats for top 3-5 only (~10 req/fixture). This keeps football within ~70 req/day. | ✅ Resolved |
| 5 | Should the analysis pool replace or supplement the existing coupon system? | Supplement. The analysis pool is the PRIMARY output. Existing coupon system continues to work and can draw picks FROM the pool. The pool is upstream of coupons. | ✅ Resolved |

---

## Implementation Plan

### Phase 1: Foundation — API Client Framework & Rate Limiter

#### Task 1.1 — [CREATE] Rate Limiter Module

**Description**: Create a file-based daily request counter that tracks API usage per service. Each API gets a separate counter file at `betting/data/.api_usage/{api_name}_{YYYY-MM-DD}.json`. The limiter checks remaining quota before each request and blocks when exhausted.

**File**: `scripts/api_clients/rate_limiter.py`

**Key interfaces**:
```python
class RateLimiter:
    def __init__(self, usage_dir: Path = Path("betting/data/.api_usage"))
    def can_request(self, api_name: str, cost: int = 1) -> bool
    def record_request(self, api_name: str, endpoint: str, cost: int = 1) -> None
    def get_remaining(self, api_name: str) -> int
    def get_usage_summary(self) -> dict[str, dict]

# Daily limits config
API_DAILY_LIMITS = {
    "api-football": 100,
    "api-basketball": 100,
    "api-hockey": 100,
    "football-data-org": 1000,
    "balldontlie": 1000,
    "thesportsdb": 100,
    "odds-api": 16,  # 500/month ÷ 30
}
```

**Definition of Done**:
- [ ] `RateLimiter` class created with `can_request()`, `record_request()`, `get_remaining()`, `get_usage_summary()` methods
- [ ] Usage files stored at `betting/data/.api_usage/{api_name}_{YYYY-MM-DD}.json`
- [ ] Counter automatically resets when date changes (new file per day)
- [ ] `get_usage_summary()` returns all APIs with used/remaining/limit
- [ ] Path traversal prevented — `api_name` validated (alphanumeric + hyphens only)
- [ ] Thread-safe file writes (use file locking or atomic writes)

#### Task 1.2 — [CREATE] Base API Client Abstract Class

**Description**: Create an abstract base class that all API clients inherit from. Provides: rate limit checking (via `RateLimiter`), cache integration (via `build_stats_cache`), retry with exponential backoff, consistent error handling, and API key loading.

**File**: `scripts/api_clients/base_client.py`

**Key interfaces**:
```python
class BaseAPIClient(ABC):
    def __init__(self, api_name: str, base_url: str, rate_limiter: RateLimiter)
    
    # Template method — subclasses override
    @abstractmethod
    def get_fixtures(self, date: str) -> list[dict]: ...
    @abstractmethod
    def get_team_stats(self, team_id: str, season: str) -> dict: ...
    @abstractmethod
    def get_fixture_stats(self, fixture_id: str) -> dict: ...
    @abstractmethod
    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]: ...
    
    # Shared infrastructure
    def _request(self, endpoint: str, params: dict, cost: int = 1) -> dict
    def _load_api_key(self) -> str
    def _check_cache(self, cache_key: str, ttl_hours: int) -> dict | None
    def _save_cache(self, cache_key: str, data: dict) -> None
```

**Definition of Done**:
- [ ] `BaseAPIClient` abstract class with `_request()` method that integrates rate limiting, retry (3 attempts, exponential backoff), and timeout (15s)
- [ ] API key loading from `config/api_keys.json` with env var override (`{API_NAME}_KEY`)
- [ ] Cache check/save methods that use `betting/data/stats_cache/` structure
- [ ] Consistent error handling: `APIRateLimitError`, `APIError`, `APINotFoundError` exceptions
- [ ] Logging: each request logged with endpoint, cost, remaining quota
- [ ] `_request()` returns parsed JSON; raises typed exceptions on failure

#### Task 1.3 — [CREATE] API Keys Configuration

**Description**: Create the API keys configuration file (gitignored) and a committed example template. Support loading keys from file or environment variables.

**Files**: `config/api_keys.json` (gitignored), `config/api_keys.example.json` (committed)

**Definition of Done**:
- [ ] `config/api_keys.example.json` created with all required keys as placeholders and registration URLs
- [ ] `config/api_keys.json` structure documented: `{"api-football": "xxx", "api-basketball": "xxx", ...}`
- [ ] `config/api_keys.json` added to `.gitignore`
- [ ] `BaseAPIClient._load_api_key()` checks env var first (`API_FOOTBALL_KEY`), then `config/api_keys.json`, then `config/odds_api_key.txt` (for backward compatibility with existing Odds API key)

#### Task 1.4 — [CREATE] Stats Normalizer Framework

**Description**: Create a module that converts diverse API response formats into a unified per-match stats structure compatible with `compute_safety_scores.py` input format. Each sport defines its stat keys. The normalizer produces arrays of per-match values suitable for L10/L5/H2H computation.

**File**: `scripts/normalize_stats.py`

**Key interfaces**:
```python
# Per-sport stat key definitions
SPORT_STAT_KEYS: dict[str, list[str]]  # e.g., football → ["corners", "fouls", "cards", ...]

@dataclass
class NormalizedFixture:
    fixture_id: str
    source: str           # "api-football", "football-data-org", etc.
    sport: str
    competition: str
    home_team: str
    away_team: str
    home_team_id: str     # API-specific team ID
    away_team_id: str
    kickoff: str          # ISO 8601
    status: str           # "scheduled", "live", "finished"

@dataclass  
class NormalizedMatchStats:
    fixture_id: str
    source: str
    sport: str
    home_team: str
    away_team: str
    date: str
    stats: dict[str, float]  # flat dict: "corners_home": 7, "corners_away": 4, ...

def normalize_api_football_fixture(raw: dict) -> NormalizedFixture
def normalize_api_football_stats(raw: dict) -> NormalizedMatchStats
def normalize_api_basketball_stats(raw: dict) -> NormalizedMatchStats
def normalize_api_hockey_stats(raw: dict) -> NormalizedMatchStats
def normalize_football_data_org_match(raw: dict) -> NormalizedFixture

def build_safety_score_input(
    sport: str,
    team_a: str,
    team_b: str,
    competition: str,
    team_a_matches: list[NormalizedMatchStats],  # L10 for team A
    team_b_matches: list[NormalizedMatchStats],  # L10 for team B
    h2h_matches: list[NormalizedMatchStats],     # H2H history
    market_definitions: list[dict],               # which stats → which markets
) -> dict  # compute_safety_scores.py input format
```

**Definition of Done**:
- [ ] `NormalizedFixture` and `NormalizedMatchStats` dataclasses defined
- [ ] Per-API normalizer functions created: `normalize_api_football_fixture()`, `normalize_api_football_stats()`, `normalize_api_basketball_stats()`, `normalize_api_hockey_stats()`, `normalize_football_data_org_match()`
- [ ] `SPORT_STAT_KEYS` dictionary defines all tracked stats per sport
- [ ] `build_safety_score_input()` transforms normalized match arrays into the exact JSON format expected by `compute_safety_scores.py` (with `team_a_l10`, `team_b_l10`, `h2h_values`, `team_a_l5`, `team_b_l5`, `line`, `is_combined`, `name` per market)
- [ ] Market definitions per sport: maps stat keys to betting market names (e.g., `corners_home + corners_away` → `"Corners Total O/U"`)

#### Task 1.5 — [CREATE] Unit Tests for Foundation

**Description**: Create unit tests for the rate limiter, base client, and stats normalizer. Use `unittest` (matches existing Python stdlib-only approach in the codebase).

**Files**: `tests/test_rate_limiter.py`, `tests/test_normalize_stats.py`

**Definition of Done**:
- [ ] Rate limiter tests: counter increment, daily reset, quota exhaustion blocking, usage summary
- [ ] Normalizer tests: API-Football response → `NormalizedMatchStats`, `build_safety_score_input()` produces valid `compute_safety_scores.py` input (verifiable by calling `validate_input()` from `compute_safety_scores.py`)
- [ ] Tests use sample/fixture data (no real API calls)
- [ ] All tests pass: `python3 -m pytest tests/`

#### Task 1.6 — [MODIFY] Update Requirements

**Description**: Add new Python dependencies required by the API clients.

**File**: `scripts/requirements.txt`

**Definition of Done**:
- [ ] `understat` added (Understat xG data)
- [ ] `nba_api` added (NBA stats from stats.nba.com)
- [ ] No other new dependencies needed — `requests` already present; dataclasses built-in Python 3.7+
- [ ] `pip install -r scripts/requirements.txt` succeeds in existing `.venv`

---

### Phase 2: Football API Integration

#### Task 2.1 — [CREATE] API-Football v3 Client

**Description**: Implement the primary football statistics API client. This is the highest-value integration — it provides per-match statistical breakdowns (corners, fouls, cards, shots, possession) across 1000+ leagues globally, including all exotic leagues the system tracks.

**File**: `scripts/api_clients/api_football.py`

**Key endpoints to implement**:
| Endpoint | Use | Cost |
|----------|-----|------|
| `GET /fixtures?date=YYYY-MM-DD` | All fixtures on a date | 1 req |
| `GET /fixtures/statistics?fixture={id}` | Per-match stats (corners, shots, fouls, cards, possession) | 1 req |
| `GET /fixtures/headtohead?h2h={id1}-{id2}&last=10` | H2H fixture history | 1 req |
| `GET /teams/statistics?team={id}&league={id}&season={year}` | Team season aggregates | 1 req |
| `GET /leagues?current=true` | Active leagues (for fixture filtering) | 1 req |
| `GET /injuries?fixture={id}` | Injury/suspension list | 1 req |
| `GET /teams?search={name}` | Team name → ID resolution | 1 req |

**Request budget strategy (70 req/day allocation)**:
- 1 req: all fixtures for the date
- ~15 req: team ID lookups (cached after first use)
- ~20 req: fixture statistics for shortlisted matches
- ~15 req: H2H data for top candidates
- ~10 req: team season stats for context
- ~9 req: reserve

**Definition of Done**:
- [ ] `APIFootballClient` class extends `BaseAPIClient`
- [ ] `get_fixtures(date)` returns all fixtures for a date as `list[NormalizedFixture]`
- [ ] `get_fixture_stats(fixture_id)` returns `NormalizedMatchStats` with corners, fouls, cards, shots, SOT, possession, offsides, saves
- [ ] `get_h2h(team1_id, team2_id, last_n=10)` returns list of historical fixtures with basic stats
- [ ] `get_team_stats(team_id, league_id, season)` returns team season aggregates
- [ ] `resolve_team_id(team_name)` with persistent ID cache at `betting/data/stats_cache/_team_ids/api-football.json`
- [ ] All methods respect rate limiter; raise `APIRateLimitError` when quota exhausted
- [ ] Fixture stats API response correctly mapped to normalized stat keys (API returns `"Corner Kicks"` → normalized `"corners_home"`)

#### Task 2.2 — [CREATE] Fixture Discovery Engine

**Description**: Create a multi-source fixture discovery script that finds ALL matches on a given date across all sports and leagues. Combines API-based discovery with existing Playwright scan results. Deduplicates by matching team names + date.

**File**: `scripts/discover_fixtures.py`

**Key interfaces**:
```python
def discover_all_fixtures(
    date: str,                          # YYYY-MM-DD
    sports: list[str] | None = None,    # filter to specific sports
    include_playwright: bool = True,     # merge with existing scan_summary.json
) -> list[NormalizedFixture]

def merge_fixtures(
    api_fixtures: list[NormalizedFixture],
    scan_fixtures: list[dict],           # from scan_summary.json
) -> list[NormalizedFixture]

def deduplicate_fixtures(
    fixtures: list[NormalizedFixture]
) -> list[NormalizedFixture]
```

**Definition of Done**:
- [ ] `discover_all_fixtures()` queries API-Football (football), API-Basketball (basketball), API-Hockey (hockey) for all matches on the date
- [ ] Merges API-discovered fixtures with existing `scan_summary.json` results from Playwright
- [ ] Deduplication uses fuzzy team name matching (leverage existing `normalize()` from `aggregate_and_select.py`)
- [ ] Returns unified fixture list with source provenance (`"source": "api-football"` or `"source": "flashscore.com"`)
- [ ] Sports without API coverage (volleyball, tennis, handball, etc.) retain Playwright-only fixtures
- [ ] CLI: `python3 scripts/discover_fixtures.py --date 2026-04-28 [--sports football,basketball]`
- [ ] Output saved to `betting/data/fixtures_{YYYY-MM-DD}.json`

#### Task 2.3 — [CREATE] L10/L5/H2H Stats Extraction Pipeline

**Description**: For a given fixture, fetch the detailed per-match statistical history needed for safety score computation. Uses tiered fetching: season averages first (cheap), then per-match details for top candidates (expensive). This is the core value-add of the API integration.

**Integrated into**: `scripts/fetch_api_stats.py` (main orchestrator, created in Phase 4 Task 4.1; the extraction logic lives in the API client methods and normalizer)

**Logic flow**:
```
For each fixture on the shortlist:
  1. Resolve team IDs (cached)
  2. Fetch team A last 10 fixtures → for each, fetch fixture stats → extract per-match stat values
  3. Fetch team B last 10 fixtures → same
  4. Fetch H2H last 10 meetings → for each, fetch fixture stats → extract combined stat values
  5. Normalize all into compute_safety_scores.py input format
  6. Store in stats cache
```

**Definition of Done**:
- [ ] `APIFootballClient.get_team_last_fixtures(team_id, last_n=10)` returns list of fixture IDs
- [ ] For each fixture ID, `get_fixture_stats()` retrieves per-match corners, fouls, cards, shots, etc.
- [ ] `get_h2h()` returns historical meetings with stats (if API provides them inline) or fixture IDs for subsequent stats fetching
- [ ] L5 derived from L10 (last 5 entries of the L10 array)
- [ ] All extracted data stored in stats cache via `build_stats_cache.py` with `"api_source": "api-football"`
- [ ] Request cost tracked: typical fixture enrichment = 3-5 API calls (team A fixtures + team B fixtures + H2H), up to ~25 calls if fetching per-match stats for each

#### Task 2.4 — [CREATE] Football-Data.org Client (EU Fallback)

**Description**: Implement a fallback client for European football when API-Football quota is exhausted. Covers 12 major leagues. Provides fixtures, results, standings, and team form — but NOT per-match corner/foul stats (only scores). Use for fixture discovery and form validation.

**File**: `scripts/api_clients/football_data_org.py`

**Key endpoints**:
| Endpoint | Use | Auth |
|----------|-----|------|
| `GET /v4/matches?dateFrom=X&dateTo=X` | All matches in date range | API key header |
| `GET /v4/teams/{id}/matches?status=FINISHED&limit=10` | Team's last 10 matches | API key header |
| `GET /v4/competitions/{code}/standings` | League standings | API key header |
| `GET /v4/competitions` | Available competitions | API key header |

**Definition of Done**:
- [ ] `FootballDataOrgClient` class extends `BaseAPIClient`
- [ ] `get_fixtures(date)` returns all matches for the date across covered competitions
- [ ] `get_team_matches(team_id, last_n=10)` returns recent match results (scores, not detailed stats)
- [ ] Competition codes mapped: `PL` (EPL), `BL1` (Bundesliga), `SA` (Serie A), `PD` (La Liga), `FL1` (Ligue 1), `DED` (Eredivisie), `PPL` (Primeira), `ELC` (Championship), `BSA` (Brasileirão), `CLI` (Copa Libertadores)
- [ ] Rate limiting: 10 req/min enforced via `RateLimiter` with per-minute tracking (or simple `time.sleep(6)` between requests)
- [ ] Used as fallback when API-Football quota exhausted for EU leagues

#### Task 2.5 — [CREATE] Understat xG Client

**Description**: Wrap the `understat` Python package to fetch expected goals (xG) data for matches in the top 6 European leagues. Provides xG, xGA, npxG, PPDA per match — valuable for football analysis depth.

**File**: `scripts/api_clients/understat_client.py`

**Covered leagues**: EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL (Russian Premier League)

**Definition of Done**:
- [ ] `UnderstatClient` class wraps `understat` Python package (async internally, exposed as sync)
- [ ] `get_team_matches(team_name, league, season)` returns list of matches with xG, xGA, npxG, npxGA, PPDA, deep stats
- [ ] `get_match_stats(match_id)` returns per-match xG breakdown (home/away xG, shot maps if available)
- [ ] Results normalized to `NormalizedMatchStats` with stat keys: `xg_home`, `xg_away`, `npxg_home`, `npxg_away`, `ppda_home`, `ppda_away`
- [ ] No API key required — package scrapes understat.com
- [ ] Results cached in stats cache with `"api_source": "understat"`

---

### Phase 3: Basketball & Hockey API Integration

#### Task 3.1 — [CREATE] API-Basketball v1 Client

**Description**: Implement the API-Basketball client for NBA, Euroleague, and other basketball leagues. Provides per-game team statistics needed for basketball market analysis (totals, spreads).

**File**: `scripts/api_clients/api_basketball.py`

**Key endpoints**:
| Endpoint | Use | Cost |
|----------|-----|------|
| `GET /games?date=YYYY-MM-DD` | All games on a date | 1 req |
| `GET /statistics?id={game_id}` | Team stats for a game (pts, reb, ast, etc.) | 1 req |
| `GET /standings?league={id}&season={year}` | Standings with PF/PA | 1 req |
| `GET /teams?search={name}` | Team name → ID | 1 req |
| `GET /games?team={id}&season={year}&last=10` | Team's last 10 games | 1 req |

**Definition of Done**:
- [ ] `APIBasketballClient` class extends `BaseAPIClient`
- [ ] `get_fixtures(date)` returns all games for the date
- [ ] `get_fixture_stats(game_id)` returns `NormalizedMatchStats` with points, rebounds, assists, steals, blocks, turnovers, FG%, 3P%, FT%
- [ ] `get_h2h(team1_id, team2_id, last_n=10)` returns historical meetings
- [ ] `resolve_team_id(team_name)` with persistent cache
- [ ] League coverage: NBA (12), Euroleague (138), ACB, LNB, BSL, NBL, and other available leagues
- [ ] All methods respect 100 req/day rate limit

#### Task 3.2 — [CREATE] API-Hockey v1 Client

**Description**: Implement the API-Hockey client for NHL, KHL, and European hockey leagues. Provides per-game team statistics for hockey market analysis.

**File**: `scripts/api_clients/api_hockey.py`

**Key endpoints**:
| Endpoint | Use | Cost |
|----------|-----|------|
| `GET /games?date=YYYY-MM-DD` | All games on a date | 1 req |
| `GET /games/statistics?id={game_id}` | Team stats for a game | 1 req |
| `GET /teams?search={name}` | Team name → ID | 1 req |
| `GET /games?team={id}&season={year}&last=10` | Team's last 10 games | 1 req |

**Definition of Done**:
- [ ] `APIHockeyClient` class extends `BaseAPIClient`
- [ ] `get_fixtures(date)` returns all games for the date
- [ ] `get_fixture_stats(game_id)` returns `NormalizedMatchStats` with goals, shots, PP goals, PIM, hits, blocks, faceoff %
- [ ] `get_h2h(team1_id, team2_id, last_n=10)` returns historical meetings
- [ ] `resolve_team_id(team_name)` with persistent cache
- [ ] League coverage: NHL, KHL, SHL, DEL, Liiga, Czech Extraliga, Swiss NL
- [ ] All methods respect 100 req/day rate limit

#### Task 3.3 — [CREATE] BallDontLie + nba_api Client

**Description**: Implement a combined NBA stats client that uses BallDontLie API (simple, no auth) as primary and `nba_api` package as deep-dive fallback for advanced NBA statistics. These provide the most detailed NBA data available for free.

**File**: `scripts/api_clients/balldontlie.py`

**BallDontLie endpoints** (free, no key):
| Endpoint | Use |
|----------|-----|
| `GET /games?dates[]={YYYY-MM-DD}` | Games on a date |
| `GET /stats?game_ids[]={id}` | Player box scores for a game |
| `GET /season_averages?season={year}&player_ids[]={id}` | Season averages |

**nba_api functions** (deep dive, rate limited ~30/min):
| Function | Use |
|----------|-----|
| `TeamGameLog(team_id, season)` | Full game log for a team |
| `LeagueGameFinder(date_from, date_to)` | Find games in date range |
| `BoxScoreTraditionalV2(game_id)` | Detailed team box score |

**Definition of Done**:
- [ ] `NBAStatsClient` class extends `BaseAPIClient`
- [ ] Uses BallDontLie for basic game discovery and stats
- [ ] Falls back to `nba_api` for detailed stats (pace, ORtg, DRtg, advanced) when BallDontLie insufficient
- [ ] `get_fixtures(date)` returns NBA games for the date
- [ ] `get_fixture_stats(game_id)` returns team totals: points, rebounds, assists, steals, blocks, turnovers, FG%, 3P%, FT%
- [ ] `get_team_game_log(team_id, last_n=10)` returns last N games with full stats
- [ ] Rate limiting: `time.sleep(2)` between `nba_api` calls (respects stats.nba.com rate limits)

---

### Phase 4: Multi-API Orchestration & Stats Pipeline

#### Task 4.1 — [CREATE] API Stats Fetcher Orchestrator

**Description**: Create the main script that orchestrates multi-API stats fetching for a list of fixtures. For each fixture, determines the best API to use (based on sport, league, remaining quota), fetches L10/L5/H2H stats, normalizes them, and stores in cache. Implements the fallback chain.

**File**: `scripts/fetch_api_stats.py`

**Fallback chains**:
```
Football: API-Football → Football-Data.org → Understat (xG only) → Playwright (existing)
Basketball: API-Basketball → BallDontLie → nba_api (NBA only) → Playwright (existing)
Hockey: API-Hockey → Playwright (existing)
Tennis/Volleyball/Other: Playwright (existing) — no API coverage
```

**CLI**:
```bash
# Fetch stats for all fixtures on a date
python3 scripts/fetch_api_stats.py --date 2026-04-28

# Fetch stats for specific fixtures (from fixtures file)
python3 scripts/fetch_api_stats.py --fixtures betting/data/fixtures_2026-04-28.json

# Fetch stats for specific sports only
python3 scripts/fetch_api_stats.py --date 2026-04-28 --sports football,basketball

# Show API usage summary
python3 scripts/fetch_api_stats.py --usage
```

**Definition of Done**:
- [ ] Main `fetch_stats_for_fixtures(fixtures, sports_filter)` function iterates fixtures, selects best API client per sport, fetches stats
- [ ] Fallback logic: if primary API returns `APIRateLimitError`, tries next in chain
- [ ] For each fixture with stats, produces `compute_safety_scores.py`-compatible input JSON via `normalize_stats.build_safety_score_input()`
- [ ] Stores enriched data in stats cache (`build_stats_cache.update_cache()`)
- [ ] Summary output: `betting/data/api_stats_summary_{YYYY-MM-DD}.json` with per-fixture enrichment status, API usage, errors
- [ ] CLI with `--date`, `--fixtures`, `--sports`, `--usage` flags
- [ ] Request budget tracking: prints remaining quota per API after completion

#### Task 4.2 — [MODIFY] Extend Stats Cache for API Data

**Description**: Modify `build_stats_cache.py` to store richer API-sourced data, including per-match stat arrays (not just aggregates) and source provenance. The cache must support the L10/L5 arrays that `compute_safety_scores.py` needs.

**File**: `scripts/build_stats_cache.py`

**Changes**:
```python
# Extended cache entry format
{
    "team": "Liverpool",
    "sport": "football",
    "slug": "liverpool",
    "last_updated": "2026-04-28T10:00:00Z",
    "ttl_hours": 24,
    "api_source": "api-football",           # NEW: which API provided data
    "form": {
        "l10_matches": [                     # NEW: per-match raw stats
            {"date": "2026-04-20", "opponent": "Arsenal", "stats": {"corners": 7, "fouls": 12, ...}},
            ...
        ],
        "l10_avg": {"corners": 6.2, "fouls": 11.4, ...},
        "l5_avg": {"corners": 6.8, "fouls": 10.2, ...},
    },
    "h2h": {
        "arsenal": {
            "last_updated": "2026-04-28T10:00:00Z",
            "matches": [                     # NEW: per-match H2H stats
                {"date": "2025-12-15", "stats": {"corners_total": 11, "fouls_total": 24, ...}},
                ...
            ],
            "avg": {"corners_total": 10.8, "fouls_total": 22.1, ...},
        }
    },
    "sources": ["api-football", "flashscore.com"],
}
```

**Definition of Done**:
- [ ] `create_team_cache_entry()` extended with `api_source` field and `l10_matches` array in `form`
- [ ] New function `update_from_api(sport, team, normalized_matches, api_source)` that takes a list of `NormalizedMatchStats` and stores per-match arrays + computed averages
- [ ] H2H cache entries extended with `matches` array (per-match stats, not just aggregate)
- [ ] Backward compatible — existing cache entries without new fields still work
- [ ] Cache read functions return per-match arrays when available (for `compute_safety_scores.py` input)

#### Task 4.3 — [CREATE] Safety Score Pipeline Bridge

**Description**: Create the bridge function that reads enriched stats cache entries and produces the exact JSON input format for `compute_safety_scores.py`. This automates what was previously done manually by the analysis agent — reading stats and constructing the input.

**Integrated into**: `scripts/normalize_stats.py` (extends Task 1.4)

**Key function**:
```python
def build_safety_input_from_cache(
    sport: str,
    team_a: str,
    team_b: str,
    competition: str,
) -> dict | None:
    """
    Read stats cache for both teams, extract per-match arrays,
    and produce compute_safety_scores.py input JSON.
    
    Returns None if insufficient cache data.
    """
```

**Market definitions per sport**:
```python
FOOTBALL_MARKETS = [
    {"name": "Corners Total O/U", "stat_a": "corners", "stat_b": "corners", "is_combined": True},
    {"name": "Fouls Total O/U", "stat_a": "fouls", "stat_b": "fouls", "is_combined": True},
    {"name": "Cards Total O/U", "stat_a": "yellow_cards", "stat_b": "yellow_cards", "is_combined": True},
    {"name": "Shots Total O/U", "stat_a": "shots", "stat_b": "shots", "is_combined": True},
    {"name": "Shots on Target Total O/U", "stat_a": "shots_on_target", "stat_b": "shots_on_target", "is_combined": True},
    {"name": "Team A Corners O/U", "stat_a": "corners", "stat_b": None, "is_combined": False},
    {"name": "Team B Corners O/U", "stat_a": None, "stat_b": "corners", "is_combined": False},
    {"name": "Goals Total O/U", "stat_a": "goals", "stat_b": "goals", "is_combined": True},
]

BASKETBALL_MARKETS = [
    {"name": "Total Points O/U", "stat_a": "points", "stat_b": "points", "is_combined": True},
    {"name": "Total Rebounds O/U", "stat_a": "rebounds", "stat_b": "rebounds", "is_combined": True},
    {"name": "Total Assists O/U", "stat_a": "assists", "stat_b": "assists", "is_combined": True},
    {"name": "Team A Points O/U", "stat_a": "points", "stat_b": None, "is_combined": False},
    {"name": "Team B Points O/U", "stat_a": None, "stat_b": "points", "is_combined": False},
]

HOCKEY_MARKETS = [
    {"name": "Total Goals O/U", "stat_a": "goals", "stat_b": "goals", "is_combined": True},
    {"name": "Total Shots O/U", "stat_a": "shots", "stat_b": "shots", "is_combined": True},
    {"name": "Total PIM O/U", "stat_a": "pim", "stat_b": "pim", "is_combined": True},
]
```

**Definition of Done**:
- [ ] `build_safety_input_from_cache()` reads cache for both teams, extracts per-match stat arrays, constructs all applicable market entries
- [ ] Market definitions for football (8+ markets), basketball (5+ markets), hockey (3+ markets)
- [ ] Lines auto-determined from averages (e.g., L10 avg corners = 10.2 → line = 9.5 or 10.5 depending on half-integer rounding)
- [ ] Common Betclic lines used when available (from `betting_config.json` or known standard lines)
- [ ] Returns `None` when insufficient data (< 5 matches for either team)
- [ ] Output directly passable to `compute_safety_scores.rank_markets()`

#### Task 4.4 — [CREATE] Pipeline Integration Tests

**Description**: Create integration tests that verify the full pipeline: API response → normalizer → cache → safety score input → safety score output. Use sample/mock API responses.

**Files**: `tests/test_api_football.py`, `tests/test_deep_analysis_pool.py`

**Definition of Done**:
- [ ] `test_api_football.py`: mock API-Football responses, verify fixture and stats normalization
- [ ] `test_deep_analysis_pool.py`: mock cached data for 3 fixtures, verify analysis pool generation produces valid output with ranked markets
- [ ] Full pipeline test: sample API response → `normalize_api_football_stats()` → `build_safety_score_input()` → `rank_markets()` → verify output has safety scores and ranking
- [ ] All tests pass: `python3 -m pytest tests/`

---

### Phase 5: Deep Analysis Pool Engine

#### Task 5.1 — [CREATE] Analysis Pool Generator

**Description**: Create the core analysis engine that produces a pool of 20+ deeply analyzed statistical events. For each fixture with sufficient stats data, it computes safety scores across ALL available statistical markets and ranks them. This is the PRIMARY output of the system.

**File**: `scripts/deep_analysis_pool.py`

**CLI**:
```bash
# Generate analysis pool for today
python3 scripts/deep_analysis_pool.py --date 2026-04-28

# Generate with minimum event count
python3 scripts/deep_analysis_pool.py --date 2026-04-28 --min-events 20

# Generate for specific sports
python3 scripts/deep_analysis_pool.py --date 2026-04-28 --sports football,basketball,hockey

# Use pre-fetched fixtures and stats (skip API calls)
python3 scripts/deep_analysis_pool.py --date 2026-04-28 --cache-only
```

**Process**:
```
1. Load fixtures (from fixtures_{date}.json or discover)
2. For each fixture with cached stats:
   a. Build safety score input (all markets for the sport)
   b. Run compute_safety_scores.rank_markets()
   c. Attach odds from fetch_odds_api snapshot (if available)
   d. Compute EV for each market (where odds available)
3. Rank all events by best market safety score
4. Output: analysis_pool_{date}.json + analysis_pool_{date}.md
```

**Definition of Done**:
- [ ] `generate_analysis_pool(date, sports, min_events, cache_only)` function processes all fixtures
- [ ] For each fixture, computes safety scores for ALL applicable statistical markets
- [ ] Each event in the pool includes: fixture info, ALL markets ranked by safety score, best market recommendation, L10/H2H/L5 averages, hit rates, three-way check
- [ ] Pool ranked by best market safety score (descending)
- [ ] Integrates with `fetch_odds_api.py` output to attach odds and EV when available
- [ ] `--cache-only` mode uses only cached stats (no new API calls) — useful for re-analysis
- [ ] Output: JSON pool file + human-readable markdown
- [ ] Handles insufficient data gracefully: events with < 5 matches per team are flagged but included with lower confidence

#### Task 5.2 — [CREATE] Pool Output Formats

**Description**: Define and implement the JSON and markdown output formats for the analysis pool. The markdown format must be scannable by the user to quickly identify best picks.

**Integrated into**: `scripts/deep_analysis_pool.py`

**JSON output format** (`betting/data/analysis_pool_{YYYY-MM-DD}.json`):
```json
{
    "date": "2026-04-28",
    "generated_at": "2026-04-28T10:00:00Z",
    "api_usage": {
        "api-football": {"used": 65, "remaining": 35},
        "api-basketball": {"used": 42, "remaining": 58}
    },
    "total_fixtures_discovered": 120,
    "total_fixtures_enriched": 45,
    "total_events_in_pool": 28,
    "events": [
        {
            "rank": 1,
            "fixture_id": "api-football-12345",
            "sport": "football",
            "competition": "Premier League",
            "home_team": "Liverpool",
            "away_team": "Arsenal",
            "kickoff": "2026-04-28T15:00:00Z",
            "data_quality": "FULL",
            "sources": ["api-football", "understat"],
            "best_market": {
                "name": "Corners Total O/U 9.5",
                "direction": "OVER",
                "safety_score": 0.85,
                "l10_avg": 11.2,
                "h2h_avg": 10.8,
                "l5_avg": 12.1,
                "hit_rate_l10": "8/10",
                "hit_rate_h2h": "6/7",
                "three_way": "3/3 SUPPORT",
                "margin": 1.179
            },
            "odds": {
                "betclic": null,
                "market_best": 1.72,
                "market_best_bookmaker": "Pinnacle"
            },
            "ev": 0.08,
            "all_markets": [
                {"rank": 1, "name": "Corners Total O/U 9.5", "direction": "OVER", "safety": 0.85, "l10_avg": 11.2, "h2h_avg": 10.8, "l5_avg": 12.1, "hit_l10": "8/10", "hit_h2h": "6/7"},
                {"rank": 2, "name": "Fouls Total O/U 22.5", "direction": "OVER", "safety": 0.78, "l10_avg": 24.1, "h2h_avg": 23.5, "l5_avg": 25.0, "hit_l10": "7/10", "hit_h2h": "5/6"},
                {"rank": 3, "name": "Shots Total O/U 24.5", "direction": "OVER", "safety": 0.70, "l10_avg": 26.3, "h2h_avg": 25.0, "l5_avg": 27.1, "hit_l10": "7/10", "hit_h2h": "5/7"}
            ]
        }
    ]
}
```

**Markdown output** (`betting/data/analysis_pool_{YYYY-MM-DD}.md`):
```markdown
# Analysis Pool — 2026-04-28
Generated: 2026-04-28 10:00 UTC | Fixtures: 120 discovered, 45 enriched, 28 in pool

## API Usage
| API | Used | Remaining | Limit |
|-----|------|-----------|-------|
| API-Football | 65 | 35 | 100 |
| API-Basketball | 42 | 58 | 100 |

---

## #1 — Liverpool vs Arsenal | Premier League | 15:00 UTC
**BEST: Corners Total O/U 9.5 OVER** | Safety: 0.85 | EV: +8%

| # | Market | L10 avg | H2H avg | L5 avg | Hit L10 | Hit H2H | Safety | 3-Way |
|---|--------|---------|---------|--------|---------|---------|--------|-------|
| 1 | Corners O/U 9.5 | 11.2 | 10.8 | 12.1 | 8/10 | 6/7 | 0.85 | 3/3 ✅ |
| 2 | Fouls O/U 22.5 | 24.1 | 23.5 | 25.0 | 7/10 | 5/6 | 0.78 | 3/3 ✅ |
| 3 | Shots O/U 24.5 | 26.3 | 25.0 | 27.1 | 7/10 | 5/7 | 0.70 | 2/3 ⚠️ |
```

**Definition of Done**:
- [ ] JSON output schema matches the format above, all fields populated
- [ ] Markdown output is human-scannable with ranked events and market tables
- [ ] Each event shows ALL available statistical markets ranked by safety score
- [ ] Odds attached when available from `odds_api_snapshot.json`
- [ ] EV computed when odds available: `EV = (safety_score × odds) - 1` (simplified)
- [ ] Data quality flags: `FULL` (API stats + H2H + odds), `PARTIAL` (API stats, limited H2H), `THIN` (limited data)

#### Task 5.3 — [MODIFY] Update Orchestrator Script

**Description**: Modify `run_full_scan_and_prepare.sh` to include the new API-based pipeline steps. The API steps run AFTER Playwright scanning (to benefit from fixture discovery) and BEFORE aggregation/selection.

**File**: `scripts/run_full_scan_and_prepare.sh`

**New steps inserted**:
```bash
# Existing steps 1-4 unchanged

# [5/9] API-based fixture discovery
echo "[5/9] Discovering fixtures via APIs..."
python3 "${SCRIPT_DIR}/discover_fixtures.py" --date "$(date '+%Y-%m-%d')"

# [6/9] Fetch API stats for discovered fixtures
echo "[6/9] Fetching statistics from APIs..."
python3 "${SCRIPT_DIR}/fetch_api_stats.py" --date "$(date '+%Y-%m-%d')"

# [7/9] Generate deep analysis pool
echo "[7/9] Generating analysis pool..."
python3 "${SCRIPT_DIR}/deep_analysis_pool.py" --date "$(date '+%Y-%m-%d')"

# Existing steps (aggregate, select) renumbered
```

**Definition of Done**:
- [ ] Three new steps added to `run_full_scan_and_prepare.sh` after Playwright scan and before aggregation
- [ ] Steps execute in order: discover_fixtures → fetch_api_stats → deep_analysis_pool
- [ ] Each step has error handling: if API script fails, print warning and continue (don't block Playwright pipeline)
- [ ] API usage summary printed at end
- [ ] Step numbering updated (was 7 steps, now 9-10 steps)

#### Task 5.4 — [CREATE] TheSportsDB Client

**Description**: Implement TheSportsDB client for supplementary fixture discovery and team metadata. This API covers ALL sports (including volleyball, tennis, handball) but provides only basic fixture/result data — no per-match statistical breakdowns. Useful for fixture discovery where other APIs lack coverage.

**File**: `scripts/api_clients/thesportsdb.py`

**Key endpoints** (free, no key for basic endpoints):
| Endpoint | Use |
|----------|-----|
| `GET /eventsday.php?d={YYYY-MM-DD}` | Events on a date |
| `GET /lookupevent.php?id={id}` | Event details |
| `GET /searchteams.php?t={team}` | Team search |
| `GET /lookupteam.php?id={id}` | Team details |

**Definition of Done**:
- [ ] `TheSportsDBClient` class extends `BaseAPIClient`
- [ ] `get_fixtures(date)` returns events for the date (useful for sports without API-Sports.io coverage: volleyball, tennis, handball, etc.)
- [ ] `get_team_info(team_name)` returns team metadata (venue, league, badge)
- [ ] Results normalized to `NormalizedFixture` format
- [ ] Used primarily for fixture discovery gap-filling — does NOT provide match stats
- [ ] Rate limiting respected (free tier ~100 req/day)

---

### Phase 6: Configuration & Documentation

#### Task 6.1 — [MODIFY] Update Betting Config

**Description**: Add API configuration section to `config/betting_config.json` with per-API rate limits, sport mappings, request budget allocations, and enrichment priorities.

**File**: `config/betting_config.json`

**New section**:
```json
{
    "api_config": {
        "enabled": true,
        "daily_limits": {
            "api-football": 100,
            "api-basketball": 100,
            "api-hockey": 100,
            "football-data-org": 1000,
            "balldontlie": 1000,
            "thesportsdb": 100,
            "odds-api": 16
        },
        "budget_allocation": {
            "api-football": {"discovery": 5, "team_stats": 25, "fixture_stats": 20, "h2h": 15, "reserve": 35},
            "api-basketball": {"discovery": 5, "team_stats": 20, "fixture_stats": 20, "h2h": 10, "reserve": 45},
            "api-hockey": {"discovery": 5, "team_stats": 15, "fixture_stats": 15, "h2h": 10, "reserve": 55}
        },
        "sport_api_mapping": {
            "football": ["api-football", "football-data-org", "understat"],
            "basketball": ["api-basketball", "balldontlie", "nba_api"],
            "hockey": ["api-hockey"],
            "tennis": ["thesportsdb"],
            "volleyball": ["thesportsdb"],
            "handball": ["thesportsdb"],
            "baseball": [],
            "esports": [],
            "snooker": [],
            "table_tennis": [],
            "darts": [],
            "mma": [],
            "padel": [],
            "speedway": []
        },
        "enrichment_priority": {
            "note": "Order in which fixtures are enriched when quota is limited. KEY sports first, then by league importance.",
            "order": ["football", "basketball", "hockey", "tennis", "volleyball", "handball", "baseball"]
        },
        "analysis_pool": {
            "min_events": 20,
            "min_safety_score": 0.50,
            "min_matches_per_team": 5,
            "include_thin_data": true
        }
    }
}
```

**Definition of Done**:
- [ ] `api_config` section added with `daily_limits`, `budget_allocation`, `sport_api_mapping`, `enrichment_priority`, `analysis_pool` sub-sections
- [ ] All API client scripts read limits from config (not hardcoded)
- [ ] `analysis_pool` settings control `deep_analysis_pool.py` behavior
- [ ] Existing config sections unchanged — backward compatible

#### Task 6.2 — [CREATE] End-to-End Smoke Test

**Description**: Create a smoke test script that verifies the full pipeline works end-to-end without real API calls. Uses mock/cached data to validate: config loading → fixture discovery → stats fetching → normalization → safety score → analysis pool output.

**File**: `tests/test_e2e_pipeline.py`

**Definition of Done**:
- [ ] Smoke test creates sample fixtures, mock API responses, runs full pipeline
- [ ] Verifies analysis pool JSON output is valid and contains expected fields
- [ ] Verifies markdown output is generated
- [ ] Verifies rate limiter files are created and incremented
- [ ] Test is runnable standalone: `python3 -m pytest tests/test_e2e_pipeline.py`
- [ ] Uses `tmp_path` fixture to avoid polluting real data directories

#### Task 6.3 — [MODIFY] Update Source Registry

**Description**: Add all new API sources to `betting/sources/source-registry.md` with proper Tier A classification, coverage details, rate limits, and integration notes.

**File**: `betting/sources/source-registry.md`

**New entries**:
```markdown
## Tier A Core Stats — API Sources (Programmatic)

- API-Football v3 (api-sports.io)
  Role: comprehensive football statistics API — per-match corners, fouls, cards, shots, possession, xG across 1000+ leagues globally.
  Use for: L10/L5/H2H statistical data for ALL football markets. Primary source for safety score computation.
  Access: free tier (100 req/day). API key in config/api_keys.json or API_FOOTBALL_KEY env var.
  Coverage: 1000+ leagues, 120+ countries. All exotic leagues (E1-E3) covered.
  Stats per match: corners, shots, SOT, fouls, cards, possession, passes, saves, offsides.
  Script: `python3 scripts/fetch_api_stats.py --sports football`
  Added: 2026-04-28.

- API-Basketball v1 (api-sports.io)
  Role: basketball statistics API — per-game points, rebounds, assists, steals, blocks across NBA, Euroleague, and 50+ leagues.
  Use for: L10/L5/H2H statistical data for basketball totals, spreads, and team prop markets.
  Access: free tier (100 req/day). API key in config/api_keys.json or API_BASKETBALL_KEY env var.
  Coverage: NBA, Euroleague, ACB, NBL, BSL, LNB, and all major+minor leagues.
  Script: `python3 scripts/fetch_api_stats.py --sports basketball`
  Added: 2026-04-28.

- API-Hockey v1 (api-sports.io)
  Role: hockey statistics API — per-game goals, shots, PP, PIM, hits, blocks, faceoffs across NHL, KHL, and European leagues.
  Use for: L10/L5/H2H statistical data for hockey totals and period markets.
  Access: free tier (100 req/day). API key in config/api_keys.json or API_HOCKEY_KEY env var.
  Coverage: NHL, KHL, SHL, DEL, Liiga, Czech Extraliga, Swiss NL.
  Script: `python3 scripts/fetch_api_stats.py --sports hockey`
  Added: 2026-04-28.

- Football-Data.org
  Role: EU football fixtures, results, standings — fallback when API-Football quota exhausted.
  Use for: fixture discovery and form validation for 12 major EU leagues. Does NOT provide per-match corner/foul stats.
  Access: free tier (10 req/min). API key in config/api_keys.json or FOOTBALL_DATA_ORG_KEY env var.
  Coverage: EPL, Bundesliga, Serie A, La Liga, Ligue 1, Eredivisie, Primeira, Championship, Brasileirão + more.
  Added: 2026-04-28.

- BallDontLie API
  Role: free NBA stats API — game results, player box scores, season averages.
  Use for: NBA statistical analysis when API-Basketball quota exhausted.
  Access: free (no key required).
  Coverage: NBA only.
  Added: 2026-04-28.

- nba_api (Python package)
  Role: unofficial NBA stats from stats.nba.com — most detailed free NBA data source.
  Use for: advanced NBA stats (pace, ORtg, DRtg), team game logs, detailed box scores.
  Access: free (no key, rate ~30 req/min). Rate-sensitive — add delays between calls.
  Coverage: NBA only (current + historical seasons).
  Added: 2026-04-28.

- Understat
  Role: expected goals (xG) data for top 6 European football leagues.
  Use for: xG, xGA, npxG, PPDA per match — enriches football analysis depth.
  Access: free Python package (scrapes understat.com).
  Coverage: EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL.
  Added: 2026-04-28.

- TheSportsDB
  Role: universal sports fixture database — covers ALL sports with basic fixture/result data.
  Use for: fixture discovery for sports without API-Sports.io coverage (volleyball, tennis, handball, etc.). No per-match stats.
  Access: free tier (~100 req/day).
  Coverage: All sports globally — but basic data only (fixtures, results, team info).
  Added: 2026-04-28.
```

**Definition of Done**:
- [ ] All 8 new API sources added to source-registry.md under a new "Tier A Core Stats — API Sources (Programmatic)" section
- [ ] Each entry includes: role, use for, access details, coverage, and script command
- [ ] Fallback chains documented (API-Football → Football-Data.org → Understat → Playwright)

---

### Phase 7: Code Review

#### Task 7.1 — [REUSE] Code Review by `tsh-code-reviewer`

**Description**: Run `tsh-code-reviewer` agent via `tsh-review.prompt.md` to review all new and modified files. Include running the E2E test suite (`python3 -m pytest tests/`) as part of the review.

**Scope**:
- All files in `scripts/api_clients/`
- `scripts/normalize_stats.py`
- `scripts/discover_fixtures.py`
- `scripts/fetch_api_stats.py`
- `scripts/deep_analysis_pool.py`
- Modified: `scripts/build_stats_cache.py`, `scripts/run_full_scan_and_prepare.sh`, `scripts/requirements.txt`
- Config: `config/betting_config.json`, `config/api_keys.example.json`
- Tests: `tests/test_rate_limiter.py`, `tests/test_normalize_stats.py`, `tests/test_api_football.py`, `tests/test_deep_analysis_pool.py`, `tests/test_e2e_pipeline.py`

**Definition of Done**:
- [ ] Code review passes or issues resolved after max 3 iterations
- [ ] All tests pass: `python3 -m pytest tests/ -v`
- [ ] No security issues (API keys not hardcoded, path traversal prevented, input validated)
- [ ] Review report documented in Changelog

---

## Security Considerations

- **API Key Storage**: Keys stored in `config/api_keys.json` (gitignored). Env var override supported. Never logged in console output — use `key[:8]...` masking.
- **Path Traversal Prevention**: `validate_sport()` and `slugify()` already exist in `build_stats_cache.py`. Apply same validation to all file paths derived from API data (team names, league names).
- **Input Validation**: All API responses validated before processing. Unexpected response shapes logged and skipped, not crash.
- **Rate Limit Respect**: Never exceed free tier limits. Rate limiter is a hard gate, not advisory.
- **No Secrets in Logs**: API responses may contain subscription info — strip before logging.
- **HTTPS Only**: All API calls over HTTPS (enforced in base URLs).
- **Dependency Security**: `understat` and `nba_api` are well-maintained open-source packages. Pin versions in `requirements.txt`.

## Quality Assurance

Acceptance criteria checklist to verify the implementation meets the defined requirements:

- [ ] Rate limiter correctly tracks and enforces daily limits for all 7 APIs
- [ ] API-Football client fetches per-match stats (corners, fouls, cards, shots) for football fixtures
- [ ] API-Basketball client fetches per-game stats (points, rebounds, assists) for basketball games
- [ ] API-Hockey client fetches per-game stats (goals, shots, PIM) for hockey games
- [ ] Stats normalizer converts all API responses to unified `NormalizedMatchStats` format
- [ ] `build_safety_score_input()` produces valid input for `compute_safety_scores.py` (passes `validate_input()`)
- [ ] Analysis pool generates 20+ events when sufficient data is available
- [ ] Analysis pool markdown output is human-readable with ranked markets per event
- [ ] Existing Playwright-based scanning pipeline continues to work unmodified
- [ ] `run_full_scan_and_prepare.sh` executes new API steps without blocking on errors
- [ ] All unit and integration tests pass
- [ ] Daily API budget stays within free tier limits across typical usage
- [ ] Fallback chains activate when primary API is exhausted

## Improvements (Out of Scope)

Potential improvements identified during planning that are not part of the current task:

- **Async API Fetching**: Migrate from `requests` to `httpx` async for parallel API calls across different APIs. Would improve throughput but adds complexity.
- **Machine Learning Model**: Train a model on historical stats + outcomes to predict statistical markets. Requires significant data collection first.
- **Real-time Odds Integration**: Stream live odds from The Odds API and trigger re-analysis when lines move significantly.
- **Database Backend**: Replace JSON file cache with SQLite or PostgreSQL for better querying of historical stats across seasons.
- **Dashboard UI**: Build a web dashboard (Streamlit or similar) to visualize the analysis pool interactively.
- **Tennis/Volleyball API**: Find or build API integrations for tennis and volleyball stats (currently no free APIs with per-match stats for these sports).
- **Automated Betclic Odds Verification**: Cross-reference analysis pool picks with actual Betclic app odds automatically.
- **Historical Backtesting**: Run the safety score analysis on historical data to validate prediction accuracy before live use.

## Changelog

| Date       | Change Description   |
| ---------- | -------------------- |
| 2026-04-28 | Initial plan created |
