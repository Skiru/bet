# Esports Integration — Implementation Plan

**Date:** 2026-05-24  
**Status:** Ready for Implementation  
**Research:** [esports-integration.research.md](esports-integration.research.md)  
**Target Games:** Counter-Strike 2 (CS2), Dota 2, Valorant

---

## Solution Architecture

### Key Design Decision: Three Distinct Internal Sports

Rather than using a single `sport="esports"` with a `sub_sport` field, the integration treats **cs2**, **dota2**, and **valorant** as three independent internal sports. This is the cleanest approach because:

1. **Every downstream script** already dispatches on `sport` field — no changes needed
2. **Market definitions**, stat keys, value ranges, safety scores are all per-sport — natural fit
3. **The adapter** fetches once from odds-api.io slug `"esports"`, then splits events by parsing league name prefix
4. **Dedup** works automatically — sport mismatch prevents cross-game false merges
5. **Coupon builder** max-same-sport rules apply correctly per game

### Data Flow

```
odds-api.io (slug: "esports")
    │
    ▼ 194 raw events
OddsAPIioAdapter._fetch_esports()
    │ Parse league name prefix:
    │   "Counter-Strike - X" → sport="cs2"
    │   "Dota - X"           → sport="dota2"
    │   "Valorant - X"       → sport="valorant"
    ▼
DiscoveredEvent(sport="cs2", competition="Thunderpick World Championship", ...)
    │
    ▼
DeduplicationEngine.merge()  ← sport must match exactly
    │
    ▼
DB: fixtures(sport="cs2"), teams(sport_id=...), ...
    │
    ▼
build_shortlist.py → deep_stats_report.py → gate_checker.py → coupon_builder.py
                         │
                         ├── cs2    → HLTVScraper
                         ├── dota2  → OpenDotaClient
                         └── valorant → VLRScraper
```

### Source Hierarchy (Live-Tested)

| Role | CS2 | Dota 2 | Valorant |
|------|-----|--------|----------|
| **Discovery + Odds** | odds-api.io (PRIMARY) | odds-api.io (PRIMARY) | odds-api.io (PRIMARY) |
| **Deep Stats** | HLTV (Playwright) → bo3.gg (fallback) | OpenDota API (FREE) | VLR.gg (HTTP) |
| **H2H** | HLTV match history | OpenDota team matches | VLR.gg match history |
| **Tipster/Consensus** | GosuGamers + HLTV polls | GosuGamers | GosuGamers + VLR predictions |
| **Context/Roster** | Liquipedia | Liquipedia | Liquipedia |
| **Settlement** | HLTV results | OpenDota proMatches | VLR.gg results |

---

## Phase 1: Pipeline Discovery + Odds (QUICK WIN)

**Goal:** Esports events appear in discovery pipeline with odds from Betclic PL.  
**Prerequisite:** None  
**Delivers:** Fixtures in DB, odds in `odds_history`, events in shortlist

### Task 1.1 — Add esports sports to `betting_config.json`

**File:** `config/betting_config.json`  
**Change:** Add `"cs2"`, `"dota2"`, `"valorant"` to the `sports` array  
**Complexity:** Trivial

```json
"sports": [
  "football", "volleyball", "basketball", "tennis", "hockey",
  "cs2", "dota2", "valorant"
]
```

**Definition of Done:** Config loads with 8 sports, no JSON parse errors.

---

### Task 1.2 — Add esports slug mapping to `OddsAPIioClient`

**File:** `src/bet/api_clients/odds_api_io.py`  
**Change:** Extend `SPORT_SLUG_MAP` with three entries pointing to the same API slug

```python
SPORT_SLUG_MAP = {
    "football": "football",
    "basketball": "basketball",
    "tennis": "tennis",
    "hockey": "ice-hockey",
    "volleyball": "volleyball",
    "cs2": "esports",
    "dota2": "esports",
    "valorant": "esports",
}
```

**Complexity:** Trivial  
**Definition of Done:** `SPORT_SLUG_MAP["cs2"]` returns `"esports"`.

---

### Task 1.3 — Add esports support to `OddsAPIioAdapter`

**File:** `src/bet/discovery/sources/odds_api_io.py`  
**Change:** 
1. Add `"cs2"`, `"dota2"`, `"valorant"` to `supported_sports`
2. Override `_fetch_events_impl` behavior for esports sports: since all three map to the same slug, fetch once and cache. When sport is cs2/dota2/valorant, filter from the cached esports response by parsing `league.name` prefix.

**New logic (inside adapter class):**

```python
# League name prefix → internal sport mapping
ESPORTS_LEAGUE_PREFIX = {
    "Counter-Strike": "cs2",
    "CS2": "cs2",
    "CS:GO": "cs2",
    "Dota": "dota2",
    "Dota 2": "dota2",
    "Valorant": "valorant",
}

supported_sports = [
    "football", "volleyball", "basketball", "tennis", "hockey",
    "cs2", "dota2", "valorant",
]

def _parse_esports_sport(self, league_name: str) -> str | None:
    """Parse sub-game from odds-api.io league name like 'Counter-Strike - BLAST Premier'."""
    for prefix, sport in self.ESPORTS_LEAGUE_PREFIX.items():
        if league_name.startswith(prefix):
            return sport
    return None

def _fetch_events_impl(self, date: str, sport: str) -> list[DiscoveredEvent]:
    slug = SPORT_SLUG_MAP.get(sport, sport)
    
    # Esports: all 3 games share one slug — fetch all, filter by league prefix
    if slug == "esports":
        return self._fetch_esports_filtered(date, sport)
    
    # ... existing logic for traditional sports ...

def _fetch_esports_filtered(self, date: str, target_sport: str) -> list[DiscoveredEvent]:
    """Fetch all esports events, return only those matching target_sport."""
    from_dt = f"{date}T00:00:00Z"
    to_dt = f"{date}T23:59:59Z"
    
    raw_events = self._client.get_events("esports", status="pending", from_dt=from_dt, to_dt=to_dt)
    
    events = []
    for ev in raw_events:
        league_name = ""
        league = ev.get("league")
        if isinstance(league, dict):
            league_name = league.get("name", "")
        elif isinstance(league, str):
            league_name = league
        
        parsed_sport = self._parse_esports_sport(league_name)
        if parsed_sport != target_sport:
            continue
        
        # Strip game prefix from competition name for cleaner display
        competition = self._clean_esports_competition(league_name)
        
        # ... build DiscoveredEvent with sport=target_sport, competition=competition ...
    
    return events

def _clean_esports_competition(self, league_name: str) -> str:
    """'Counter-Strike - BLAST Premier Spring' → 'BLAST Premier Spring'"""
    for prefix in self.ESPORTS_LEAGUE_PREFIX:
        if league_name.startswith(prefix):
            remainder = league_name[len(prefix):].lstrip(" -–—")
            return remainder if remainder else league_name
    return league_name
```

**Complexity:** Medium  
**Caching consideration:** The coordinator calls `_fetch_events_impl` for each sport sequentially. For esports, the same API call would be made 3 times (cs2, dota2, valorant). Add a simple per-date cache:

```python
_esports_cache: dict[str, list[dict]] = {}  # date → raw events

def _get_esports_raw(self, date: str) -> list[dict]:
    if date not in self._esports_cache:
        from_dt = f"{date}T00:00:00Z"
        to_dt = f"{date}T23:59:59Z"
        self._esports_cache[date] = self._client.get_events(
            "esports", status="pending", from_dt=from_dt, to_dt=to_dt
        ) or []
    return self._esports_cache[date]
```

**Definition of Done:**
- `discover_events.py --date YYYY-MM-DD --sports cs2` returns CS2 fixtures
- Events have `sport="cs2"`, clean competition names (no "Counter-Strike -" prefix)
- Single API call serves all three esports sports (not 3 redundant calls)

---

### Task 1.4 — Add esports to coordinator SPORTS constant

**File:** `src/bet/discovery/coordinator.py`  
**Change:** Add three esports to the SPORTS list

```python
SPORTS = ["football", "volleyball", "basketball", "tennis", "hockey", "cs2", "dota2", "valorant"]
```

**Complexity:** Trivial  
**Definition of Done:** `discover_events.py --date YYYY-MM-DD` (no --sports filter) includes esports.

---

### Task 1.5 — Create esports sport rows in DB

**File:** `src/bet/discovery/coordinator.py` (already handles sport creation in `_persist`)  
**Change:** No code change needed — the coordinator already does:
```python
self.session.execute(
    text("INSERT OR IGNORE INTO sports (name, tier) VALUES (:name, 1)"),
    {"name": mf.sport},
)
```

This auto-creates sport rows for cs2, dota2, valorant on first discovery run.

**Definition of Done:** After first run, `SELECT * FROM sports` shows cs2, dota2, valorant rows.

---

### Task 1.6 — Esports-aware team name normalization

**File:** `src/bet/utils.py`  
**Change:** Add esports-specific suffix stripping to `normalize_team_name`:

```python
# After existing club suffix removal, add esports org suffixes:
s = re.sub(
    r"\b(Gaming|Esports|eSports|e-Sports|Team|Clan|Organization|Org)\b",
    "", s, flags=re.IGNORECASE,
)
```

**Complexity:** Low  
**Risk:** Must ensure this doesn't break existing sport matching. "Gaming" and "Esports" are not traditional sport team names, so safe to remove universally.

**Definition of Done:** `normalize_team_name("FaZe Clan")` == `normalize_team_name("FaZe")`.

---

### Phase 1 Checklist

- [ ] 1.1 — Add cs2/dota2/valorant to betting_config.json sports
- [ ] 1.2 — Add cs2/dota2/valorant → "esports" in SPORT_SLUG_MAP
- [ ] 1.3 — Implement _fetch_esports_filtered in OddsAPIioAdapter with league prefix parsing + caching
- [ ] 1.4 — Add esports to coordinator SPORTS list
- [ ] 1.5 — Verify auto-creation of sport rows (no code change, integration test)
- [ ] 1.6 — Add esports org suffixes to normalize_team_name

---

## Phase 2: Stats Infrastructure

**Goal:** Deep statistical data per game for safety score calculation.  
**Prerequisite:** Phase 1 complete (fixtures in DB)  
**Delivers:** L10 form, H2H data, team stats for all three games

### Task 2.1 — OpenDota API Client (Dota 2)

**File:** `src/bet/api_clients/opendota.py` (NEW)  
**Base class:** Inherit from `BaseAPIClient`  
**Auth:** None (60 req/min free), optional API key for 1200 req/min  
**Rate limit key:** `"opendota"` in RateLimiter

**Interface:**

```python
class OpenDotaClient(BaseAPIClient):
    """OpenDota API client for Dota 2 professional match statistics."""
    
    TIMEOUT = 15
    BASE_URL = "https://api.opendota.com/api"
    
    def get_pro_matches(self, limit: int = 100) -> list[dict]:
        """GET /proMatches — recent professional matches."""
        
    def get_team(self, team_id: int) -> dict | None:
        """GET /teams/{id} — team info + W/L record."""
    
    def get_team_matches(self, team_id: int, limit: int = 20) -> list[dict]:
        """GET /teams/{id}/matches — recent team matches with scores."""
    
    def get_team_heroes(self, team_id: int) -> list[dict]:
        """GET /teams/{id}/heroes — hero pool + win rates."""
    
    def get_match(self, match_id: int) -> dict | None:
        """GET /matches/{id} — full match detail (kills, duration, draft)."""
    
    def search_teams(self, name: str) -> list[dict]:
        """GET /search?q=name — find team by name, return team_id."""
    
    def get_team_stats(self, team_name: str, n_matches: int = 10) -> dict:
        """High-level: resolve team → fetch last N matches → compute averages.
        
        Returns: {
            "kills_avg": float,
            "deaths_avg": float, 
            "duration_avg_min": float,
            "first_blood_rate": float,
            "win_rate_l10": float,
            "hero_pool_size": int,
            "matches_found": int,
        }
        """
    
    def get_h2h(self, team_a: str, team_b: str) -> dict:
        """Find mutual matches between two teams.
        
        Returns: {
            "matches_found": int,
            "team_a_wins": int,
            "team_b_wins": int,
            "avg_total_kills": float,
            "avg_duration_min": float,
        }
        """
```

**Data persistence:** Write to `team_form` table (existing) with stat keys from `SPORT_STAT_KEYS["dota2"]`.

**Complexity:** Medium (3-4 hours)  
**Definition of Done:**
- `OpenDotaClient().get_team_stats("Team Spirit")` returns valid stats dict
- Results cached in `stats_cache/` with 4h TTL
- Rate limiter enforced (60 req/min bucket)
- Team name → team_id resolution works via `/search`

---

### Task 2.2 — HLTV Scraper (CS2)

**File:** `src/bet/scrapers/hltv.py` (NEW)  
**Access:** Playwright stealth mode (Cloudflare)  
**Base class:** Use `PlaywrightBase` from `src/bet/api_clients/playwright_base.py`

**Interface:**

```python
class HLTVScraper:
    """HLTV.org scraper for CS2 team and match statistics."""
    
    RATE_LIMIT_SECONDS = 4  # Conservative: 1 req per 4s
    
    def get_team_stats(self, team_name: str, months: int = 3) -> dict:
        """Scrape team stats page.
        
        Returns: {
            "maps_played": int,
            "maps_won": int,
            "map_win_rate": float,
            "rounds_played": int,
            "round_win_rate_ct": float,
            "round_win_rate_t": float,
            "avg_rounds_per_map": float,
            "rating_2": float,
            "ranking": int | None,
        }
        """
    
    def get_team_map_pool(self, team_name: str) -> dict:
        """Scrape map-specific stats.
        
        Returns: {
            "map_name": {"played": int, "won": int, "win_rate": float, "avg_rounds": float},
            ...
        }
        """
    
    def get_h2h(self, team_a: str, team_b: str) -> dict:
        """Scrape head-to-head match history.
        
        Returns: {
            "matches_found": int,
            "team_a_wins": int,
            "team_b_wins": int,
            "avg_rounds_per_map": float,
            "maps_played": int,
            "recent_matches": [{date, score, event}, ...],
        }
        """
    
    def get_upcoming_matches(self) -> list[dict]:
        """Scrape upcoming matches page for fixture verification."""
    
    def search_team(self, name: str) -> int | None:
        """Resolve team name → HLTV team ID."""
```

**Fallback:** If HLTV is 403 (Cloudflare escalation), fall through to bo3.gg HTTP scraping.

**Complexity:** High (4-6 hours — Playwright stealth + HTML parsing)  
**Definition of Done:**
- `HLTVScraper().get_team_stats("Natus Vincere")` returns valid stats
- Playwright uses stealth mode (no Cloudflare detection)
- 4s rate limiting between requests
- Graceful fallback on 403 (returns None, logs warning)

---

### Task 2.3 — VLR.gg Scraper (Valorant)

**File:** `src/bet/scrapers/vlr.py` (NEW)  
**Access:** Standard HTTP + BeautifulSoup (confirmed working without Playwright)

**Interface:**

```python
class VLRScraper:
    """VLR.gg scraper for Valorant team and match statistics."""
    
    RATE_LIMIT_SECONDS = 3
    BASE_URL = "https://www.vlr.gg"
    
    def get_team_stats(self, team_name: str) -> dict:
        """Scrape team profile + recent matches.
        
        Returns: {
            "maps_played": int,
            "maps_won": int,
            "map_win_rate": float,
            "avg_rounds_per_map": float,
            "acs_avg": float,  # Average Combat Score
            "win_rate_l10": float,
            "ranking": int | None,
        }
        """
    
    def get_team_map_pool(self, team_name: str) -> dict:
        """Scrape map-specific stats.
        
        Returns: {
            "map_name": {"played": int, "won": int, "win_rate": float, "avg_rounds": float},
            ...
        }
        """
    
    def get_h2h(self, team_a: str, team_b: str) -> dict:
        """Find head-to-head matches.
        
        Returns: {
            "matches_found": int,
            "team_a_wins": int,
            "team_b_wins": int,
            "avg_rounds_per_map": float,
        }
        """
    
    def search_team(self, name: str) -> str | None:
        """Resolve team name → VLR team URL slug."""
```

**Complexity:** Medium (4-6 hours)  
**Definition of Done:**
- `VLRScraper().get_team_stats("Sentinels")` returns valid stats
- HTTP-only (no Playwright dependency)
- 3s rate limiting
- BeautifulSoup parsing handles VLR HTML structure

---

### Task 2.4 — bo3.gg Scraper (CS2 Fallback)

**File:** `src/bet/scrapers/bo3gg.py` (NEW)  
**Access:** Standard HTTP (confirmed working)

**Interface:**

```python
class Bo3ggScraper:
    """bo3.gg scraper — CS2 fallback when HLTV is blocked."""
    
    def get_team_stats(self, team_name: str) -> dict:
        """Basic team stats from bo3.gg."""
    
    def get_h2h(self, team_a: str, team_b: str) -> dict:
        """H2H from bo3.gg."""
```

**Complexity:** Low-Medium (2-3 hours)  
**Definition of Done:** Returns usable L10 stats when HLTV is unavailable.

---

### Task 2.5 — Stats Router for Esports in `deep_stats_report.py`

**File:** `scripts/deep_stats_report.py`  
**Change:** Add routing logic for cs2/dota2/valorant in the stats-fetching section.

Currently the script uses `SPORT_STAT_KEYS.get(sport)` and calls enrichment functions. Add:

```python
ESPORTS_STATS_CLIENTS = {
    "cs2": ("hltv", "bo3gg"),       # primary, fallback
    "dota2": ("opendota",),          # single source (free, reliable)
    "valorant": ("vlr",),            # single source
}

def _fetch_esports_stats(sport: str, team_a: str, team_b: str) -> tuple[dict, dict, dict]:
    """Fetch L10 stats + H2H for esports candidates.
    
    Returns: (stats_a, stats_b, h2h)
    """
    clients = ESPORTS_STATS_CLIENTS.get(sport, ())
    for client_name in clients:
        try:
            client = _get_esports_client(client_name)
            stats_a = client.get_team_stats(team_a)
            stats_b = client.get_team_stats(team_b)
            h2h = client.get_h2h(team_a, team_b)
            if stats_a and stats_b:
                return stats_a, stats_b, h2h
        except Exception as e:
            logger.warning("Esports client %s failed: %s", client_name, e)
            continue
    return {}, {}, {}
```

**Complexity:** Medium  
**Definition of Done:**
- `deep_stats_report.py` successfully processes cs2/dota2/valorant candidates
- Falls back through client chain on failure
- Results written to team_form DB table

---

### Phase 2 Checklist

- [ ] 2.1 — Build OpenDota API client with team stats, H2H, team search
- [ ] 2.2 — Build HLTV Playwright scraper with team stats, map pool, H2H
- [ ] 2.3 — Build VLR.gg HTTP scraper with team stats, map pool, H2H
- [ ] 2.4 — Build bo3.gg HTTP scraper as CS2 fallback
- [ ] 2.5 — Add esports stats routing in deep_stats_report.py

---

## Phase 3: Safety Scores + Market Definitions

**Goal:** Esports candidates get proper safety score ranking with game-specific markets.  
**Prerequisite:** Phase 2 complete (stats available)  
**Delivers:** Ranked market tables per esports candidate

### Task 3.1 — Add esports stat keys to `SPORT_STAT_KEYS`

**File:** `src/bet/stats/market_ranking.py`  
**Change:** Add three new entries:

```python
SPORT_STAT_KEYS["cs2"] = [
    "maps_won", "map_win_rate", "avg_rounds_per_map",
    "round_win_rate_ct", "round_win_rate_t", "rating_2", "ranking",
]

SPORT_STAT_KEYS["dota2"] = [
    "kills_avg", "deaths_avg", "duration_avg_min",
    "first_blood_rate", "win_rate_l10", "hero_pool_size",
]

SPORT_STAT_KEYS["valorant"] = [
    "maps_won", "map_win_rate", "avg_rounds_per_map",
    "acs_avg", "win_rate_l10", "ranking",
]
```

**Definition of Done:** `SPORT_STAT_KEYS["cs2"]` returns correct keys.

---

### Task 3.2 — Add esports market definitions to `SPORT_MARKETS`

**File:** `src/bet/stats/market_ranking.py`  
**Change:** Add market tables for each game:

```python
CS2_MARKETS = [
    {"name": "Total Maps O/U", "stat_a": "maps_won", "stat_b": "maps_won", "is_combined": True},
    {"name": "Map Handicap", "stat_a": "map_win_rate", "stat_b": "map_win_rate", "is_combined": False},
    {"name": "Total Rounds (Map) O/U", "stat_a": "avg_rounds_per_map", "stat_b": "avg_rounds_per_map", "is_combined": True},
]

DOTA2_MARKETS = [
    {"name": "Total Maps O/U", "stat_a": "maps_won", "stat_b": "maps_won", "is_combined": True},
    {"name": "Total Kills O/U", "stat_a": "kills_avg", "stat_b": "kills_avg", "is_combined": True},
    {"name": "Game Duration O/U", "stat_a": "duration_avg_min", "stat_b": "duration_avg_min", "is_combined": True},
]

VALORANT_MARKETS = [
    {"name": "Total Maps O/U", "stat_a": "maps_won", "stat_b": "maps_won", "is_combined": True},
    {"name": "Map Handicap", "stat_a": "map_win_rate", "stat_b": "map_win_rate", "is_combined": False},
    {"name": "Total Rounds (Map) O/U", "stat_a": "avg_rounds_per_map", "stat_b": "avg_rounds_per_map", "is_combined": True},
]

SPORT_MARKETS["cs2"] = CS2_MARKETS
SPORT_MARKETS["dota2"] = DOTA2_MARKETS
SPORT_MARKETS["valorant"] = VALORANT_MARKETS
```

**Definition of Done:** `SPORT_MARKETS["cs2"]` returns market list.

---

### Task 3.3 — Add esports standard market lines

**File:** `src/bet/stats/market_ranking.py`  
**Change:**

```python
STANDARD_MARKET_LINES["cs2"] = [
    {"market": "Total Maps", "lines": [2.5], "stat": "maps_won", "is_combined": True},
    {"market": "Map Handicap", "lines": [-1.5, 1.5], "stat": "map_win_rate", "is_combined": False},
    {"market": "Total Rounds (Map)", "lines": [24.5, 25.5, 26.5], "stat": "avg_rounds_per_map", "is_combined": True},
]

STANDARD_MARKET_LINES["dota2"] = [
    {"market": "Total Maps", "lines": [2.5], "stat": "maps_won", "is_combined": True},
    {"market": "Total Kills", "lines": [42.5, 45.5, 48.5], "stat": "kills_avg", "is_combined": True},
    {"market": "Game Duration", "lines": [32.5, 35.5, 38.5], "stat": "duration_avg_min", "is_combined": True},
]

STANDARD_MARKET_LINES["valorant"] = [
    {"market": "Total Maps", "lines": [2.5], "stat": "maps_won", "is_combined": True},
    {"market": "Map Handicap", "lines": [-1.5, 1.5], "stat": "map_win_rate", "is_combined": False},
    {"market": "Total Rounds (Map)", "lines": [22.5, 23.5, 24.5], "stat": "avg_rounds_per_map", "is_combined": True},
]
```

**Definition of Done:** Lines match Betclic's commonly offered esports lines.

---

### Task 3.4 — Add esports value ranges

**File:** `src/bet/stats/value_ranges.py`  
**Change:**

```python
SPORT_VALUE_RANGES["cs2"] = {
    "maps_won": (0, 3), "map_win_rate": (0, 100),
    "avg_rounds_per_map": (16, 30), "round_win_rate_ct": (20, 80),
    "round_win_rate_t": (20, 80), "rating_2": (0.70, 1.50),
    "ranking": (1, 200),
}

SPORT_VALUE_RANGES["dota2"] = {
    "kills_avg": (15, 60), "deaths_avg": (15, 60),
    "duration_avg_min": (20, 70), "first_blood_rate": (0, 100),
    "win_rate_l10": (0, 100), "hero_pool_size": (5, 40),
}

SPORT_VALUE_RANGES["valorant"] = {
    "maps_won": (0, 3), "map_win_rate": (0, 100),
    "avg_rounds_per_map": (20, 26), "acs_avg": (100, 300),
    "win_rate_l10": (0, 100), "ranking": (1, 200),
}
```

**Definition of Done:** `SPORT_VALUE_RANGES["cs2"]["avg_rounds_per_map"]` returns `(16, 30)`.

---

### Task 3.5 — Add esports volatility caps

**File:** `scripts/compute_safety_scores.py`  
**Change:** Add to `SPORT_VOLATILITY_CAPS`:

```python
SPORT_VOLATILITY_CAPS["cs2"] = {
    "avg_rounds_per_map": 0.75,  # Rounds are relatively stable
}
SPORT_VOLATILITY_CAPS["dota2"] = {
    "kills_avg": 0.60,           # Kill variance is high
    "duration_avg_min": 0.65,    # Duration variance moderate
}
SPORT_VOLATILITY_CAPS["valorant"] = {
    "avg_rounds_per_map": 0.75,  # Similar to CS2
}
```

**Definition of Done:** Safety scores apply correct volatility caps for esports stats.

---

### Task 3.6 — Add esports H2H penalty config

**File:** `scripts/compute_safety_scores.py`  
**Change:** Add to `MIN_MARKETS` and `H2H_MISSING_PENALTY`:

```python
MIN_MARKETS["cs2"] = 2
MIN_MARKETS["dota2"] = 2
MIN_MARKETS["valorant"] = 2

H2H_MISSING_PENALTY["cs2"] = 0.80       # 20% penalty — H2H less common in esports
H2H_MISSING_PENALTY["dota2"] = 0.80     # 20% penalty
H2H_MISSING_PENALTY["valorant"] = 0.80  # 20% penalty
```

**Definition of Done:** Esports candidates aren't over-penalized for missing H2H data.

---

### Task 3.7 — Add Polish translations for esports markets

**File:** `src/bet/stats/market_ranking.py`  
**Change:** Add to `MARKET_PL`:

```python
MARKET_PL["Total Maps O/U"] = "Mapy łącznie"
MARKET_PL["Map Handicap"] = "Handicap mapowy"
MARKET_PL["Total Rounds (Map) O/U"] = "Rundy na mapie łącznie"
MARKET_PL["Total Kills O/U"] = "Zabójstwa łącznie"
MARKET_PL["Game Duration O/U"] = "Czas gry"
```

**Definition of Done:** Coupon output uses Polish market names for esports.

---

### Phase 3 Checklist

- [ ] 3.1 — Add SPORT_STAT_KEYS for cs2, dota2, valorant
- [ ] 3.2 — Add SPORT_MARKETS for cs2, dota2, valorant
- [ ] 3.3 — Add STANDARD_MARKET_LINES for cs2, dota2, valorant
- [ ] 3.4 — Add SPORT_VALUE_RANGES for cs2, dota2, valorant
- [ ] 3.5 — Add SPORT_VOLATILITY_CAPS for cs2, dota2, valorant
- [ ] 3.6 — Add MIN_MARKETS and H2H_MISSING_PENALTY for esports
- [ ] 3.7 — Add Polish translations for esports markets

---

## Phase 4: Tipster + Context

**Goal:** Community consensus signals + upset risk factors for esports.  
**Prerequisite:** Phase 1 complete (fixtures discoverable)  
**Delivers:** Tipster picks in DB, roster/patch context for upset risk

### Task 4.1 — GosuGamers Parser in Tipster Aggregator

**File:** `scripts/tipster_aggregator.py`  
**Change:** Add new tipster source class for GosuGamers esports predictions.

```python
class GosuGamersScraper:
    """GosuGamers community predictions for CS2/Dota2/Valorant."""
    
    URLS = {
        "cs2": "https://www.gosugamers.net/counterstrike/matches",
        "dota2": "https://www.gosugamers.net/dota2/matches",
        "valorant": "https://www.gosugamers.net/valorant/matches",
    }
    
    def fetch_predictions(self, sport: str, date: str) -> list[dict]:
        """Scrape community poll percentages.
        
        Returns: [{
            "home_team": str,
            "away_team": str,
            "home_pct": float,  # e.g., 72.0
            "away_pct": float,  # e.g., 28.0
            "total_votes": int,
        }, ...]
        """
```

**Integration:** Register in tipster_aggregator's source list for esports sports.

**Complexity:** Medium (3 hours)  
**Definition of Done:** GosuGamers predictions appear in `tipster_picks` DB table for esports fixtures.

---

### Task 4.2 — HLTV Poll Extraction (CS2)

**File:** `scripts/tipster_aggregator.py` (extend) or new `src/bet/scrapers/hltv_polls.py`  
**Change:** Extract community win% polls from HLTV match pages.

**Complexity:** Medium (2 hours — Playwright required, same as HLTV stats)  
**Definition of Done:** CS2 match polls (e.g., "68% NaVi / 32% FaZe") stored as tipster consensus.

---

### Task 4.3 — Liquipedia Roster Change Detection

**File:** `src/bet/api_clients/liquipedia.py` (NEW)  
**Access:** MediaWiki Cargo API (1 req/s)

**Interface:**

```python
class LiquipediaClient:
    """Liquipedia MediaWiki API for roster changes and tournament context."""
    
    GAME_WIKIS = {
        "cs2": "counterstrike",
        "dota2": "dota2", 
        "valorant": "valorant",
    }
    
    def get_recent_roster_changes(self, game: str, team: str, days: int = 14) -> list[dict]:
        """Query Cargo tables for recent transfers.
        
        Returns: [{
            "player": str,
            "type": "join" | "leave" | "standin",
            "date": str,
            "from_team": str | None,
        }, ...]
        """
    
    def get_latest_patch(self, game: str) -> dict:
        """Get most recent game patch info.
        
        Returns: {"version": str, "date": str, "days_since": int}
        """
```

**Used by:** `upset_risk_scorer.py` for stand-in detection + patch recency factors.

**Complexity:** Medium (3 hours)  
**Definition of Done:**
- Stand-in detection: if roster change <7 days → upset_risk += 1
- Patch recency: if new patch <14 days → upset_risk += 1

---

### Task 4.4 — Upset Risk Factors for Esports

**File:** `scripts/upset_risk_scorer.py` (or wherever upset risk is calculated)  
**Change:** Add esports-specific upset risk factors:

| Factor | Condition | Points |
|--------|-----------|--------|
| Stand-in player | Roster change < 7 days (Liquipedia) | +1 |
| New patch | Game patch < 14 days | +1 |
| Online vs LAN | Different format context | +1 |
| BO1 format | Single map (high variance) | +1 |
| Map pool disadvantage | Opponent has >20% higher win rate on likely maps | +1 |

**Threshold:** ≥2 factors = elevated upset risk (same as traditional sports)

**Definition of Done:** Esports candidates receive upset_risk scores based on esports-specific factors.

---

### Phase 4 Checklist

- [ ] 4.1 — Build GosuGamers esports parser in tipster_aggregator
- [ ] 4.2 — Add HLTV poll extraction for CS2 consensus
- [ ] 4.3 — Build Liquipedia client for roster changes + patch dates
- [ ] 4.4 — Add esports upset risk factors to upset_risk_scorer

---

## Phase 5: Fuzzy Name Matching (Cross-Cutting)

**Goal:** Reliable team name matching across sources with different naming conventions.  
**Prerequisite:** Phase 1 (needed for dedup), improves Phase 2+ accuracy  
**Delivers:** Higher dedup quality, better tipster-to-fixture matching

### Problem Statement

Esports teams have many aliases:
- "Natus Vincere" / "NaVi" / "NAVI" / "Na'Vi" / "Natus Vincere CS2"
- "FaZe Clan" / "FaZe" / "faze"
- "G2 Esports" / "G2" / "G2.iG"
- "Team Liquid" / "Liquid" / "TL"
- "Cloud9" / "C9" / "Cloud 9"

Current `normalize_team_name` + rapidfuzz (threshold 85) handles traditional sports well but fails for:
- Short names (FaZe vs G2 = low ratio even though both correct)
- Acronym vs full name (NaVi vs Natus Vincere = very low ratio)

### Task 5.1 — Esports Team Alias Registry

**File:** `src/bet/discovery/esports_aliases.py` (NEW)

```python
"""Canonical esports team aliases for cross-source name resolution.

Used by dedup engine and stats routing to match names across
odds-api.io, HLTV, VLR, OpenDota, GosuGamers, etc.
"""

# canonical_name → set of known aliases (all lowercase)
ESPORTS_ALIASES: dict[str, set[str]] = {
    "natus vincere": {"navi", "na'vi", "na`vi", "natus vincere cs2"},
    "faze clan": {"faze", "faze cs2"},
    "g2 esports": {"g2", "g2.ig"},
    "team liquid": {"liquid", "tl", "team liquid cs2"},
    "cloud9": {"c9", "cloud 9", "cloud9 cs2"},
    "team vitality": {"vitality", "vit"},
    "virtus.pro": {"vp", "virtus pro"},
    "ninjas in pyjamas": {"nip", "ninjas in pajamas"},
    "heroic": set(),
    "mouz": {"mousesports", "mouz nxt"},
    "fnatic": {"fnc"},
    "team spirit": {"spirit", "ts"},
    "9pandas": {"9p", "9 pandas"},
    "sentinels": {"sen"},
    "loud": set(),
    "drx": set(),
    "paper rex": {"prx"},
    "evil geniuses": {"eg"},
    "og": {"og esports"},
    "tundra esports": {"tundra"},
    "gaimin gladiators": {"gg", "gaimin"},
    "beastcoast": {"bc"},
}

def resolve_alias(name: str) -> str:
    """Resolve an alias to its canonical name.
    
    Returns the canonical name if found, otherwise the original (lowered).
    """
    lower = name.lower().strip()
    # Direct canonical match
    if lower in ESPORTS_ALIASES:
        return lower
    # Check all alias sets
    for canonical, aliases in ESPORTS_ALIASES.items():
        if lower in aliases:
            return canonical
    return lower
```

**Complexity:** Low (1-2 hours, mostly data entry)  
**Maintenance:** New teams/aliases added as encountered during pipeline runs.  
**Definition of Done:** `resolve_alias("NaVi")` → `"natus vincere"`.

---

### Task 5.2 — Integrate Alias Resolution into Dedup Engine

**File:** `src/bet/discovery/dedup.py`  
**Change:** Before fuzzy matching, try alias resolution:

```python
from .esports_aliases import resolve_alias

def _match_key(self, event: DiscoveredEvent) -> str:
    norm_home = normalize_team_name(event.home_team)
    norm_away = normalize_team_name(event.away_team)
    
    # For esports, also try alias resolution
    if event.sport in ("cs2", "dota2", "valorant"):
        norm_home = resolve_alias(norm_home)
        norm_away = resolve_alias(norm_away)
    
    kickoff_date = event.kickoff.strftime("%Y-%m-%d")
    return f"{event.sport}|{norm_home}|{norm_away}|{kickoff_date}"
```

Also apply in `_fuzzy_match`:

```python
def _fuzzy_match(self, event, candidates):
    ev_home = normalize_team_name(event.home_team)
    ev_away = normalize_team_name(event.away_team)
    
    if event.sport in ("cs2", "dota2", "valorant"):
        ev_home = resolve_alias(ev_home)
        ev_away = resolve_alias(ev_away)
    
    # ... rest of fuzzy matching with these resolved names ...
```

**Complexity:** Low  
**Definition of Done:** Event from odds-api.io with "NAVI" deduplicates with HLTV event showing "Natus Vincere".

---

### Task 5.3 — Alias Resolution in Stats Clients

**File:** Each stats client (opendota.py, hltv.py, vlr.py)  
**Change:** Before searching for a team by name, resolve aliases to the form used by that source.

For example, HLTV uses full names ("Natus Vincere"), while odds-api.io might use "NAVI". The alias registry maps both to canonical form, and each client can have a reverse mapping:

```python
# In HLTVScraper:
HLTV_NAMES = {
    "natus vincere": "Natus Vincere",
    "faze clan": "FaZe",
    # ...
}

def _resolve_for_hltv(self, canonical: str) -> str:
    return self.HLTV_NAMES.get(canonical, canonical.title())
```

**Complexity:** Medium (per-source name mappings)  
**Definition of Done:** Stats lookup succeeds regardless of which name form the fixture uses.

---

### Phase 5 Checklist

- [ ] 5.1 — Create esports_aliases.py with initial alias registry (50+ teams)
- [ ] 5.2 — Integrate alias resolution into dedup engine
- [ ] 5.3 — Add per-source name resolution in stats clients

---

## Security Considerations

1. **API Keys:** OpenDota free tier needs no key. If registering PandaScore later, store key in `config/api_keys.json` (gitignored) following existing pattern.
2. **Scraping:** HLTV/VLR scraping uses Playwright stealth — respect rate limits (4s HLTV, 3s VLR). No credential scraping.
3. **Input validation:** Team names from external APIs are sanitized through `normalize_team_name` before DB insertion (prevents SQL injection via parameterized queries in SQLAlchemy).
4. **Rate limiting:** All new clients must register with `RateLimiter` to prevent quota exhaustion.

---

## Test Plan

### Unit Tests

| Test | File | Validates |
|------|------|-----------|
| `test_esports_league_parsing` | `tests/test_discovery_esports.py` | League prefix → sport mapping |
| `test_esports_competition_cleaning` | `tests/test_discovery_esports.py` | "Counter-Strike - X" → "X" |
| `test_esports_alias_resolution` | `tests/test_esports_aliases.py` | Alias → canonical mapping |
| `test_esports_dedup_with_aliases` | `tests/test_dedup_esports.py` | NaVi == Natus Vincere in dedup |
| `test_normalize_team_name_esports` | `tests/test_utils.py` | "FaZe Clan" → "faze" |
| `test_esports_value_ranges` | `tests/test_value_ranges.py` | Ranges are sane |
| `test_esports_safety_scores` | `tests/test_safety_scores.py` | Safety score computation |

### Integration Tests

| Test | Validates |
|------|-----------|
| `test_opendota_live` | OpenDota API returns pro matches (skip if offline) |
| `test_odds_api_io_esports` | odds-api.io slug "esports" returns events |
| `test_discovery_esports_e2e` | Full discovery → DB persistence for cs2 fixtures |
| `test_deep_stats_cs2` | Stats routing → HLTV → safety score for CS2 candidate |

### Validation Criteria

- Phase 1 passes when: `discover_events.py --date YYYY-MM-DD --sports cs2,dota2,valorant` produces fixtures in DB with correct sport values
- Phase 2 passes when: `deep_stats_report.py` produces per-candidate reports with esports stats
- Phase 3 passes when: safety scores compute correctly for esports candidates
- Phase 4 passes when: GosuGamers consensus appears in tipster_picks for esports fixtures

---

## Quality Assurance

- All new code follows existing patterns (BaseAPIClient inheritance, RateLimiter, get_db(), AGENT_SUMMARY output)
- New scrapers include `--verbose` output for R17 compliance
- New DB writes use `from bet.db.connection import get_db` (R2)
- No auto-rejection of esports candidates based on data quality alone (R3)
- Stats-first: statistical markets (rounds, kills) evaluated before ML (R4)
- Self-healing: if HLTV fails → bo3.gg fallback (R6)

---

## Implementation Order & Dependencies

```
Phase 1 (no deps) ────────────────────────────────► Esports in discovery + odds
    │
    ├── Phase 2 (needs fixtures) ──────────────────► Stats per game
    │       │
    │       └── Phase 3 (needs stats) ─────────────► Safety scores + markets
    │
    ├── Phase 4 (needs fixtures) ──────────────────► Tipster + context
    │
    └── Phase 5 (improves all phases) ─────────────► Fuzzy matching
```

**Recommended execution:** Phase 1 → Phase 5 → Phase 2 → Phase 3 → Phase 4

Phase 5 (fuzzy matching) should come early because it directly improves the quality of Phase 2+ results. Phase 4 can be parallelized with Phase 3.
