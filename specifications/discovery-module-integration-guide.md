# Discovery Module — Deep Integration Guide

> **Version:** 1.0 | **Created:** 2026-05-14 | **Status:** PRODUCTION  
> **Module:** `src/bet/discovery/` | **CLI:** `scripts/discover_events.py`  
> **Replaces:** `scan_events.py` (deleted), `beast_mode_pipeline.py` (deleted)

---

## TABLE OF CONTENTS

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Module Structure](#3-module-structure)
4. [Source Adapters — Deep Dive](#4-source-adapters)
5. [Deduplication Engine](#5-deduplication-engine)
6. [Database Schema & Writes](#6-database-schema)
7. [JSON Output Format](#7-json-output-format)
8. [CLI Interface](#8-cli-interface)
9. [Data Flow: Discovery → Pipeline](#9-data-flow)
10. [Integration Point: Ingest (S1 → S1e)](#10-ingest-integration)
11. [Integration Point: Shortlist (S1e → S2)](#11-shortlist-integration)
12. [Integration Point: Enrichment & Scrapers (S2.3 → S2.5)](#12-enrichment-integration)
13. [Integration Point: Deep Stats (S3)](#13-deep-stats-integration)
14. [Adding a New Source Adapter](#14-adding-sources)
15. [Adding a New Sport](#15-adding-sports)
16. [Testing Strategy](#16-testing)
17. [Performance Characteristics](#17-performance)
18. [Troubleshooting](#18-troubleshooting)
19. [Key Files Reference](#19-key-files)

---

## 1. Executive Summary

The Discovery Module is an **API-first event discovery system** that fetches sports fixtures from 3 API sources concurrently, deduplicates them via fuzzy matching, persists to SQLite (via SQLAlchemy ORM), and writes a JSON output file consumed by the rest of the pipeline.

**Key numbers (live production):**
- **~1700 events** discovered per day across 5 sports
- **~29 seconds** total runtime (concurrent source fetching)
- **3 sources:** SofaScore (primary), The Odds API (secondary), API-Football (tertiary)
- **5 sports:** Football, Volleyball, Basketball, Tennis, Hockey

**What it produces:**
- **JSON file:** `betting/data/{YYYY-MM-DD}_s1_events.json` — array of merged fixtures
- **DB tables:** `fixtures`, `fixture_sources`, `scan_results`, `teams`, `competitions`, `sports`

**What consumes its output:**
- `ingest_scan_stats.py` — transforms events into `stats_cache/` JSON and DB `team_form`
- `build_shortlist.py` — scores and ranks events into shortlist
- Pipeline agents (bet-scanner, bet-enricher, bet-statistician) — read DB tables

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                   EventDiscoveryCoordinator                      │
│  coordinator.py                                                  │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐         │
│  │  SofaScore   │  │  Odds API    │  │  API-Football  │         │
│  │  Adapter     │  │  Adapter     │  │  Adapter       │         │
│  │  priority=1  │  │  priority=2  │  │  priority=3    │         │
│  │  5 sports    │  │  4 sports    │  │  football only │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬─────────┘         │
│         │                 │                  │                    │
│         └────────┬────────┴──────────────────┘                   │
│       ThreadPoolExecutor (max_workers=3)                         │
│                  │                                               │
│                  ▼                                               │
│  ┌───────────────────────────────┐                               │
│  │    DeduplicationEngine        │                               │
│  │  • Exact key matching         │                               │
│  │  • RapidFuzz fuzzy (≥85)      │                               │
│  │  • ±2h kickoff window         │                               │
│  └──────────────┬────────────────┘                               │
│                 │                                                 │
│        ┌────────┴────────┐                                       │
│        ▼                 ▼                                        │
│   ┌─────────┐     ┌──────────┐                                   │
│   │  SQLite │     │  JSON    │                                   │
│   │  (ORM)  │     │  output  │                                   │
│   └─────────┘     └──────────┘                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Module Structure

```
src/bet/discovery/
├── __init__.py          # Public API: discover_events() + model exports
├── coordinator.py       # EventDiscoveryCoordinator — orchestrates everything
├── dedup.py             # DeduplicationEngine — merges multi-source events
├── models.py            # Pydantic models + SQLAlchemy ORM model
├── repository.py        # FixtureSourceRepo — ORM CRUD for fixture_sources
└── sources/
    ├── __init__.py      # SourceAdapter Protocol definition
    ├── base.py          # AbstractSourceAdapter — shared error handling
    ├── sofascore.py     # SofaScore adapter (wraps SofascoreClient)
    ├── odds_api.py      # The Odds API adapter (REST + credit tracking)
    └── api_football.py  # API-Football adapter (wraps APIFootballClient)
```

### Import Graph

```
discover_events() ← __init__.py
    ↓ creates SQLAlchemy session
    ↓ instantiates EventDiscoveryCoordinator
        ↓ uses: DeduplicationEngine, FixtureSourceRepo
        ↓ uses: SofaScoreAdapter, OddsAPIAdapter, APIFootballAdapter
            ↓ wraps: bet.api_clients.sofascore.SofascoreClient
            ↓ wraps: bet.api_clients.api_football.APIFootballClient
            ↓ uses: bet.api_clients.rate_limiter.RateLimiter
            ↓ uses: bet.utils.normalize_team_name (for dedup)
```

---

## 4. Source Adapters — Deep Dive

All source adapters implement the `SourceAdapter` Protocol:

```python
class SourceAdapter(Protocol):
    name: str                           # 'sofascore', 'odds-api', 'api-football'
    priority: int                       # 1=primary, 2=secondary, 3=tertiary
    supported_sports: list[str]

    def fetch_events(self, date: str, sport: str) -> list[DiscoveredEvent]: ...
    def is_available(self) -> bool: ...
```

The `AbstractSourceAdapter` base class adds:
- Automatic timing of fetch calls
- Try/except wrapping with logging
- Per-source logger (`bet.discovery.sources.{name}`)

### 4.1 SofaScore (Primary — Priority 1)

| Property | Value |
|----------|-------|
| **Name** | `sofascore` |
| **Sports** | football, volleyball, basketball, tennis, hockey |
| **Auth** | None (public API) |
| **Rate limiting** | `RateLimiter` instance shared across calls |
| **Typical yield** | ~1200-1500 events/day |
| **Coverage** | Global — all leagues, tournaments, friendlies |

**How it works:**
1. Wraps `bet.api_clients.sofascore.SofascoreClient`
2. Maps our sport names to SofaScore slugs: `hockey → ice-hockey`
3. Calls `client.get_fixtures(date, sport=slug)` for each sport
4. Converts `SofascoreFixture` → `DiscoveredEvent`
5. Ensures UTC timezone on all kickoff times

**Why primary:** Broadest coverage (only source covering volleyball), no API key needed, fast response times.

### 4.2 The Odds API (Secondary — Priority 2)

| Property | Value |
|----------|-------|
| **Name** | `odds-api` |
| **Sports** | football, basketball, hockey, tennis |
| **Auth** | API key in `config/api_keys.json` → `odds_api.api_key` |
| **Rate limiting** | 500 requests/month free tier |
| **Typical yield** | ~200-400 events/day |
| **Coverage** | Major leagues only (configured sport keys) |
| **Unique value** | Returns H2H and totals odds per event |

**Configured sport keys:**
- **Football:** EPL, Bundesliga, La Liga, Serie A, Ligue 1, MLS, Brasileirão, UCL, UEL, Ekstraklasa (10 leagues)
- **Basketball:** NBA, Euroleague
- **Hockey:** NHL, SHL
- **Tennis:** Auto-discovered from active tournaments

**Credit management:**
- Each sport-key fetch costs 1 credit
- `x-requests-remaining` header tracked in logs
- Tennis keys auto-discovered via `/v4/sports` endpoint (avoids wasting credits on inactive tournaments)

**Odds data format returned per event:**
```json
{
  "h2h": {"home": 1.85, "draw": 3.40, "away": 4.20},
  "totals": {"over_2.5": 1.95, "under_2.5": 1.85, "line": 2.5}
}
```

### 4.3 API-Football (Tertiary — Priority 3)

| Property | Value |
|----------|-------|
| **Name** | `api-football` |
| **Sports** | football only |
| **Auth** | API key in `config/api_keys.json` → `api_football.api_key` |
| **Rate limiting** | 100 requests/day free tier |
| **Typical yield** | ~300-500 football events/day |
| **Coverage** | Comprehensive football worldwide |
| **Unique value** | Detailed fixture metadata (venue, referee, league round) |

**How it works:**
1. Wraps `bet.api_clients.api_football.APIFootballClient`
2. Calls `client.get_fixtures(date)` — returns all football fixtures
3. Converts to `DiscoveredEvent` with `sport="football"`

**Why tertiary:** Football-only overlap with SofaScore, limited daily quota. Primarily adds cross-reference IDs for enrichment.

### Source Priority & Canonical Names

During deduplication, **SofaScore names are canonical** because it has priority 1. When a football match appears in all 3 sources:

```
SofaScore:    "Manchester United" vs "Liverpool"      (canonical)
Odds API:     "Manchester Utd" vs "Liverpool FC"      (attached as source ref)
API-Football: "Man United" vs "Liverpool"              (attached as source ref)
```

The merged fixture keeps SofaScore's team names. All other source IDs are stored as `SourceRef` entries for cross-referencing during enrichment.

---

## 5. Deduplication Engine

**File:** `src/bet/discovery/dedup.py` | **Class:** `DeduplicationEngine`

The dedup engine merges events from multiple sources into unique `MergedFixture` objects using a 3-layer matching strategy:

### 5.1 Layer 1: Exact Key Matching

Generates a match key per event:
```
{sport}|{normalized_home}|{normalized_away}|{kickoff_date}
```

Team names are normalized via `bet.utils.normalize_team_name()`:
- Lowercase, strip accents
- Remove common suffixes (FC, SC, CF, etc.)
- Collapse whitespace

### 5.2 Layer 2: Fuzzy Matching (RapidFuzz)

When exact key doesn't match, tests against all existing merged fixtures:

1. **Sport filter:** Must match exactly
2. **Kickoff window:** ±2 hours tolerance
3. **Name similarity:** `fuzz.token_sort_ratio()` on normalized home AND away names
4. **Threshold:** Both home AND away scores must be ≥ 85 (configurable)
5. **Best match wins:** Highest combined score selected

Confidence stored on the `SourceRef`:
```python
# Exact match → confidence = 1.0
# Fuzzy match → confidence = best_score / 100.0 (e.g., 0.92)
```

### 5.3 Layer 3: New Fixture Creation

Events that match nothing create a new `MergedFixture` with the event's source as primary.

### 5.4 Source Attachment Rules

- Each source appears at most once per fixture (dedup on source name)
- First source's odds are used if no better odds available
- Odds from later sources fill in gaps (e.g., SofaScore has no odds, Odds API does)

---

## 6. Database Schema

The discovery module writes to 6 tables. All operations use SQLAlchemy ORM (not raw sqlite3).

### 6.1 `fixtures` — Core fixture table

```sql
CREATE TABLE fixtures (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id        INTEGER NOT NULL REFERENCES sports(id),
    competition_id  INTEGER REFERENCES competitions(id),
    home_team_id    INTEGER NOT NULL REFERENCES teams(id),
    away_team_id    INTEGER NOT NULL REFERENCES teams(id),
    kickoff         TEXT NOT NULL,    -- ISO 8601 UTC
    status          TEXT DEFAULT 'scheduled',
    external_id     TEXT,             -- Primary source's external ID
    source          TEXT,             -- Primary source name
    fetched_at      TEXT              -- ISO 8601 timestamp
);
```

**Upsert logic:** Match on `(sport_id, home_team_id, away_team_id, kickoff)`. If exists → reuse. If not → INSERT.

### 6.2 `fixture_sources` — Source cross-reference (ORM-managed)

```sql
CREATE TABLE fixture_sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id  INTEGER NOT NULL REFERENCES fixtures(id),
    source      TEXT NOT NULL,        -- 'sofascore', 'odds-api', 'api-football'
    external_id TEXT NOT NULL,        -- Source-specific event ID
    confidence  REAL NOT NULL DEFAULT 1.0,
    raw_data    TEXT,                 -- JSON blob of source-specific metadata
    fetched_at  TEXT NOT NULL,        -- ISO 8601 timestamp
    UNIQUE(fixture_id, source)
);
```

**This is the key table for downstream integration.** When enrichment or scrapers need to fetch detailed data for a fixture, they look up the `external_id` for their target source:

```python
# Example: Get SofaScore event ID for fixture #42
repo = FixtureSourceRepo(session)
sources = repo.get_by_fixture(42)
sofa_ref = next((s for s in sources if s.source == "sofascore"), None)
sofa_event_id = sofa_ref.external_id  # e.g., "12345678"

# Or reverse lookup: Find fixture from a known Odds API ID
fixture_src = repo.get_by_source_id("odds-api", "abc123def456")
fixture_id = fixture_src.fixture_id
```

### 6.3 `scan_results` — Scan audit trail

```sql
CREATE TABLE scan_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    betting_date    TEXT NOT NULL,     -- YYYY-MM-DD
    sport           TEXT NOT NULL,
    source_domain   TEXT NOT NULL,     -- Primary source name
    event_key       TEXT NOT NULL,     -- "Home vs Away"
    home_team       TEXT NOT NULL,
    away_team       TEXT NOT NULL,
    competition     TEXT,
    kickoff         TEXT,              -- ISO 8601 UTC
    scan_timestamp  TEXT NOT NULL      -- When discovered
);
```

### 6.4 `teams` — Team registry

```sql
CREATE TABLE teams (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id  INTEGER NOT NULL REFERENCES sports(id),
    name      TEXT NOT NULL,
    UNIQUE(sport_id, name)
);
```

### 6.5 `competitions` — Competition registry

```sql
CREATE TABLE competitions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id  INTEGER NOT NULL REFERENCES sports(id),
    name      TEXT NOT NULL,
    country   TEXT DEFAULT '',
    season    TEXT DEFAULT '',
    UNIQUE(sport_id, name, season)
);
```

### 6.6 `sports` — Sport lookup

```sql
CREATE TABLE sports (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE,
    tier  INTEGER DEFAULT 1
);
```

### Entity Relationship

```
sports (1) ──→ (N) teams
sports (1) ──→ (N) competitions
sports (1) ──→ (N) fixtures
competitions (1) ──→ (N) fixtures
teams (1) ──→ (N) fixtures [as home_team_id]
teams (1) ──→ (N) fixtures [as away_team_id]
fixtures (1) ──→ (N) fixture_sources
```

---

## 7. JSON Output Format

**File:** `betting/data/{YYYY-MM-DD}_s1_events.json`

The output is a **flat JSON array** of merged fixture objects. Example:

```json
[
  {
    "sport": "football",
    "competition": "Premier League",
    "country": "England",
    "home_team": "Manchester United",
    "away_team": "Liverpool",
    "kickoff": "2026-05-14T15:00:00+00:00",
    "status": "scheduled",
    "source": "sofascore",
    "external_id": "12345678",
    "source_count": 3,
    "sources": [
      {"source": "sofascore", "external_id": "12345678", "confidence": 1.0},
      {"source": "odds-api", "external_id": "abc123", "confidence": 0.95},
      {"source": "api-football", "external_id": "98765", "confidence": 1.0}
    ]
  },
  {
    "sport": "tennis",
    "competition": "Roland Garros",
    "country": "France",
    "home_team": "Novak Djokovic",
    "away_team": "Carlos Alcaraz",
    "kickoff": "2026-05-14T13:00:00+00:00",
    "status": "scheduled",
    "source": "sofascore",
    "external_id": "87654321",
    "source_count": 2,
    "sources": [
      {"source": "sofascore", "external_id": "87654321", "confidence": 1.0},
      {"source": "odds-api", "external_id": "xyz789", "confidence": 0.91}
    ]
  }
]
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `sport` | string | One of: `football`, `volleyball`, `basketball`, `tennis`, `hockey` |
| `competition` | string | League or tournament name |
| `country` | string | Country of competition (may be empty) |
| `home_team` | string | Full team/player name (canonical from primary source) |
| `away_team` | string | Full team/player name |
| `kickoff` | string | ISO 8601 datetime with timezone (UTC) |
| `status` | string | `scheduled`, `in_progress`, `finished`, etc. |
| `source` | string | Primary source name (`sofascore` in most cases) |
| `external_id` | string | Primary source's event ID |
| `source_count` | int | Number of sources that confirmed this fixture |
| `sources` | array | All source references with confidence scores |

### Source Confidence Values

| Value | Meaning |
|-------|---------|
| `1.0` | Exact match (normalized names + same date) |
| `0.85–0.99` | Fuzzy match (slightly different names across sources) |

---

## 8. CLI Interface

```bash
# Full discovery — all 5 sports
PYTHONPATH=src .venv/bin/python scripts/discover_events.py \
  --date 2026-05-14 --verbose

# Filtered to specific sports
PYTHONPATH=src .venv/bin/python scripts/discover_events.py \
  --date 2026-05-14 --sports football,tennis --verbose

# Custom DB path (for testing)
PYTHONPATH=src .venv/bin/python scripts/discover_events.py \
  --date 2026-05-14 --db-path /tmp/test.db --verbose
```

### CLI Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--date` | Yes | — | Target date (YYYY-MM-DD) |
| `--sports` | No | All 5 | Comma-separated sport list |
| `--verbose` | No | False | Enable detailed logging |
| `--stats-first` | No | False | Stats-first mode (R10) |
| `--db-path` | No | `betting/data/betting.db` | Custom DB path |

### AGENT_SUMMARY Output (R19)

The script emits structured JSON on stdout:

```json
AGENT_SUMMARY:{
  "verdict": "OK",
  "total_discovered": 1847,
  "total_after_dedup": 1734,
  "by_sport": {"football": 892, "basketball": 312, "tennis": 245, "hockey": 156, "volleyball": 129},
  "sources": {
    "sofascore": {"events": 1523, "available": true, "errors": 0, "duration_s": 18.2},
    "odds-api": {"events": 287, "available": true, "errors": 0, "duration_s": 12.5},
    "api-football": {"events": 37, "available": true, "errors": 0, "duration_s": 8.1}
  },
  "issues_count": 0
}
```

### Exit Codes

| Code | Verdict | Meaning |
|------|---------|---------|
| 0 | `OK` | All sources fetched successfully |
| 1 | `PARTIAL` | ≥1 source unavailable or errored |
| 2 | `FAILED` | Zero events discovered |

---

## 9. Data Flow: Discovery → Pipeline

```
                  discover_events.py (S1)
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
    {date}_s1_events.json      DB: fixtures, fixture_sources,
    (betting/data/)            scan_results, teams, competitions
              │                     │
              ▼                     │
    ingest_scan_stats.py (S1-ingest)│
              │                     │
              ▼                     │
    stats_cache/{sport}/{team}.json │
    DB: team_form                   │
              │                     │
              ▼                     │
    build_shortlist.py (S1e)        │
              │                     │
              ▼                     │
    {date}_s2_shortlist.json        │
              │                     │
     ┌────────┼──────────────┐      │
     ▼        ▼              ▼      │
  tipster   enrichment    scrapers  │
  (S2)      (S2.5)        (S2.3)   │
     │        │              │      │
     └────────┼──────────────┘      │
              ▼                     ▼
    deep_stats_report.py (S3)  ←── reads fixture_sources
              │                    for cross-reference IDs
              ▼
    gate_checker.py (S4)
              │
              ▼
    coupon_builder.py (S5-S8)
```

---

## 10. Integration Point: Ingest (S1 → S1e)

**Script:** `scripts/ingest_scan_stats.py`  
**Input:** `betting/data/{date}_s1_events.json`  
**Output:** `stats_cache/{sport}/{team}.json` + DB `team_form` rows

### What It Does

1. Reads the JSON array from discovery output
2. For each event, creates/updates a stats cache entry per team
3. Parses odds from event data (if present)
4. Writes to both JSON cache and DB `team_form` table
5. Groups events by sport for batch processing

### How It Reads Discovery Output

```python
# Auto-detection: finds {date}_s1_events.json
discovery_path = DISCOVERY_DATA_DIR / f"{args.date}_s1_events.json"
with open(discovery_path) as f:
    events = json.load(f)  # list[dict]

# Each event dict has the schema from §7 (JSON Output Format)
for ev in events:
    sport = ev["sport"]
    home = ev["home_team"]
    away = ev["away_team"]
    competition = ev.get("competition", "")
    kickoff = ev.get("kickoff", "")
    source = ev.get("source", "sofascore")
    # ... normalize and write to cache
```

### Key Field Mapping

| Discovery JSON Field | Ingest Target | Notes |
|---------------------|---------------|-------|
| `sport` | stats_cache directory | e.g., `stats_cache/football/` |
| `home_team` / `away_team` | cache entry key | Slugified for filename |
| `competition` | `team_form.league` | Used in analysis |
| `kickoff` | `team_form.kickoff` | UTC ISO string |
| `source` | `team_form.source` | Default: `sofascore` |
| `sources[].confidence` | Not used in ingest | Used in analysis for data quality scoring |

### Integration Contract

To integrate with ingest, your output **MUST** include these fields per event:
- `sport` — lowercase string matching one of the 5 core sports
- `home_team` / `away_team` — full team names (not abbreviated)
- `kickoff` — ISO 8601 datetime string
- `competition` — league/tournament name
- `source` — source identifier string

---

## 11. Integration Point: Shortlist (S1e → S2)

**Script:** `scripts/build_shortlist.py`  
**Input:** `betting/data/{date}_s1_events.json` + DB `fixtures`  
**Output:** `betting/data/{date}_s2_shortlist.json`

### What It Does

1. Loads all discovered events
2. Scores each event on: data quality, competition importance, odds attractiveness, sport diversity
3. Ranks and selects top N candidates (default: 100)
4. Applies fixture verification (§1.8) — cross-checks against Odds API snapshot

### How It Uses Discovery Data

```python
# Loads fixtures from DB first (DB-first principle, R2)
db_fixtures = load_fixtures_from_db(date)

# Falls back to JSON if DB empty
events_path = DATA_DIR / f"{date}_s1_events.json"
with open(events_path) as f:
    events = json.load(f)
```

### What It Values From Discovery

| Discovery Field | Shortlist Usage |
|----------------|-----------------|
| `source_count` | Higher source_count → higher data quality score |
| `competition` | Matched against `MAJOR_COMPETITIONS` → importance boost |
| `country` | Used for minor league value identification (R8) |
| `sources[].confidence` | Low confidence → lower trust |

---

## 12. Integration Point: Enrichment & Scrapers (S2.3 → S2.5)

### 12.1 Scrapers (S2.3) — Deep Data Collection

**Script:** `scripts/run_scrapers.py`  
**Input:** `betting/data/{date}_s2_shortlist.json` + DB `fixture_sources`

Scrapers use `fixture_sources` to get external IDs for targeted fetching:

```python
# Example: Scraping detailed stats for a football match
from bet.discovery.repository import FixtureSourceRepo

repo = FixtureSourceRepo(session)
sources = repo.get_by_fixture(fixture_id)

# Use SofaScore ID for detailed match page scraping
sofa_ref = next((s for s in sources if s.source == "sofascore"), None)
if sofa_ref:
    match_details = fetch_sofascore_match_detail(sofa_ref.external_id)
```

### 12.2 Enrichment (S2.5) — Form & H2H Data

**Script:** `scripts/data_enrichment_agent.py`  
**Input:** Shortlist candidates + DB `team_form` (from ingest step)

Enrichment reads `team_form` entries created by the ingest step and fills gaps:
- ESPN standings and gamelogs for US sports
- Flashscore web pages for H2H data
- Weather data for outdoor sports

### How to Add Scraper Integration for a New Source

When building a scraper that needs discovery cross-references:

1. **Query `fixture_sources`** to find the external ID:
   ```python
   from bet.discovery.repository import FixtureSourceRepo
   
   repo = FixtureSourceRepo(session)
   src = repo.get_by_source_id("your-source", external_id)
   if src:
       fixture_id = src.fixture_id
   ```

2. **Or query by fixture to get all source IDs:**
   ```python
   sources = repo.get_by_fixture(fixture_id)
   for src in sources:
       print(f"{src.source}: {src.external_id}")
   ```

3. **Write results back to DB** using appropriate tables (`team_form`, `match_stats`, `league_profiles`, etc.)

---

## 13. Integration Point: Deep Stats (S3)

**Script:** `scripts/deep_stats_report.py`  
**Input:** Shortlist + DB `team_form` + DB `fixture_sources`

Deep stats uses `fixture_sources` for cross-referencing when fetching detailed match statistics:

```python
# For each candidate match, get all known IDs
fixture_id = candidate["fixture_id"]
all_sources = fixture_source_repo.get_by_fixture(fixture_id)

# Use appropriate ID for each stats provider
sofascore_id = next((s.external_id for s in all_sources if s.source == "sofascore"), None)
odds_api_id = next((s.external_id for s in all_sources if s.source == "odds-api"), None)
```

---

## 14. Adding a New Source Adapter

To add a new data source to discovery:

### Step 1: Create the Adapter

Create `src/bet/discovery/sources/your_source.py`:

```python
from datetime import datetime, timezone
from ..models import DiscoveredEvent
from .base import AbstractSourceAdapter


class YourSourceAdapter(AbstractSourceAdapter):
    name = "your-source"          # Must be unique
    priority = 4                   # Lower = higher priority
    supported_sports = ["football", "basketball"]

    def __init__(self):
        super().__init__()

    def is_available(self) -> bool:
        return True  # Check API key, etc.

    def _fetch_events_impl(self, date: str, sport: str) -> list[DiscoveredEvent]:
        # Fetch from your API
        raw_events = your_api.get_events(date, sport)
        
        events = []
        for ev in raw_events:
            events.append(DiscoveredEvent(
                source=self.name,
                external_id=str(ev["id"]),
                sport=sport,
                competition=ev["league"],
                country=ev.get("country", ""),
                home_team=ev["home"],
                away_team=ev["away"],
                kickoff=datetime.fromisoformat(ev["time"]),
                status="scheduled",
                odds=ev.get("odds"),      # Optional
                raw_data=ev,              # Optional — stored in fixture_sources
            ))
        return events
```

### Step 2: Register in Coordinator

Edit `src/bet/discovery/coordinator.py`:

```python
from .sources.your_source import YourSourceAdapter

@staticmethod
def _default_sources() -> list[SourceAdapter]:
    return [
        SofaScoreAdapter(),
        OddsAPIAdapter(),
        APIFootballAdapter(),
        YourSourceAdapter(),     # Add here
    ]
```

### Step 3: Update ThreadPoolExecutor

If adding a 4th source, consider bumping `max_workers=4` in `_fetch_all_sources()`.

### Step 4: Add Tests

Create `tests/test_discovery_your_source.py` following patterns in existing test files.

---

## 15. Adding a New Sport

To add a 6th sport (e.g., `cricket`):

### Step 1: Update Coordinator

In `coordinator.py`:
```python
SPORTS = ["football", "volleyball", "basketball", "tennis", "hockey", "cricket"]
```

### Step 2: Update Source Adapters

Add sport to each adapter's `supported_sports` that covers it, plus any slug mappings.

### Step 3: Update Dedup

No changes needed — dedup is sport-agnostic (it just checks `event.sport` match).

### Step 4: Update Downstream

- `ingest_scan_stats.py` — add sport to validation list
- `build_shortlist.py` — add sport scoring if needed
- `config/betting_config.json` — add sport configuration
- Agent files — update sport lists

---

## 16. Testing Strategy

### Unit Tests

| File | Tests | Coverage |
|------|-------|----------|
| `tests/test_discovery.py` | Coordinator, dedup, models | Core logic |
| `tests/test_ingest_scan_stats.py` | Ingest normalization, parsing | Data transformation |

### Integration Tests

Run discovery with `--db-path /tmp/test.db` and verify:
1. Correct number of DB rows in `fixtures`, `fixture_sources`
2. JSON output matches DB state
3. `source_count` ≥ 1 for all fixtures
4. No duplicate fixtures (same sport + teams + kickoff)

### Live Validation

```bash
# Run discovery
PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date $(date +%Y-%m-%d) --verbose

# Verify JSON output
cat betting/data/$(date +%Y-%m-%d)_s1_events.json | python3 -m json.tool | head -50

# Verify DB writes
sqlite3 betting/data/betting.db "
  SELECT sport, COUNT(*) FROM scan_results 
  WHERE betting_date = '$(date +%Y-%m-%d)' 
  GROUP BY sport;
"

# Verify fixture sources
sqlite3 betting/data/betting.db "
  SELECT source, COUNT(*) FROM fixture_sources 
  GROUP BY source;
"
```

---

## 17. Performance Characteristics

| Metric | Value |
|--------|-------|
| **Total runtime** | ~29s (typical) |
| **SofaScore fetch** | ~18s (5 sports, sequential per sport) |
| **Odds API fetch** | ~12s (parallel per sport key) |
| **API-Football fetch** | ~8s (1 sport) |
| **Dedup phase** | <1s (in-memory, O(n×m) with early exit) |
| **DB persistence** | ~2s (savepoints per fixture) |
| **JSON write** | <0.1s |
| **Memory usage** | ~50MB peak (all events in memory during dedup) |

### Concurrency Model

Sources run in `ThreadPoolExecutor(max_workers=3)` — one thread per source. Within each source, sports are fetched **sequentially** (to respect rate limits). The 3 sources run **in parallel**.

```
Thread 1 (SofaScore):   football → volleyball → basketball → tennis → hockey
Thread 2 (Odds API):    football → basketball → hockey → tennis
Thread 3 (API-Football): football
```

---

## 18. Troubleshooting

### Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `verdict: PARTIAL` | One source unavailable (API key missing/expired) | Check `config/api_keys.json`, verify credits |
| `verdict: FAILED` | All sources failed (network/API issues) | Check internet, verify SofaScore is accessible |
| Missing volleyball events | Odds API and API-Football don't cover volleyball | Expected — only SofaScore covers volleyball |
| Low football count | API-Football quota exhausted | Expected — SofaScore still has them |
| Duplicate fixtures in DB | Race condition or re-run | Safe — upsert logic handles duplicates |
| `fixture_sources` empty | Old DB without table | Run discovery again — `Base.metadata.create_all()` creates it |

### Diagnostic Queries

```sql
-- Check discovery coverage by date
SELECT betting_date, sport, COUNT(*) 
FROM scan_results 
GROUP BY betting_date, sport 
ORDER BY betting_date DESC;

-- Check source diversity per fixture
SELECT f.id, f.source, COUNT(fs.source) as source_count
FROM fixtures f
LEFT JOIN fixture_sources fs ON fs.fixture_id = f.id
GROUP BY f.id
ORDER BY source_count DESC;

-- Find fixtures with cross-references (most useful for enrichment)
SELECT f.id, t1.name as home, t2.name as away, 
       GROUP_CONCAT(fs.source || ':' || fs.external_id) as refs
FROM fixtures f
JOIN teams t1 ON t1.id = f.home_team_id
JOIN teams t2 ON t2.id = f.away_team_id
JOIN fixture_sources fs ON fs.fixture_id = f.id
GROUP BY f.id
LIMIT 10;
```

---

## 19. Key Files Reference

### Discovery Module

| File | Purpose |
|------|---------|
| `src/bet/discovery/__init__.py` | Public API: `discover_events()` |
| `src/bet/discovery/coordinator.py` | `EventDiscoveryCoordinator` — orchestrates sources, dedup, persistence |
| `src/bet/discovery/dedup.py` | `DeduplicationEngine` — fuzzy matching + merging |
| `src/bet/discovery/models.py` | Pydantic models (`DiscoveredEvent`, `MergedFixture`, `DiscoveryResult`) + SQLAlchemy ORM (`FixtureSourceModel`) |
| `src/bet/discovery/repository.py` | `FixtureSourceRepo` — CRUD for `fixture_sources` table |
| `src/bet/discovery/sources/base.py` | `AbstractSourceAdapter` — shared error handling |
| `src/bet/discovery/sources/sofascore.py` | SofaScore adapter (priority 1, 5 sports) |
| `src/bet/discovery/sources/odds_api.py` | Odds API adapter (priority 2, 4 sports, has odds) |
| `src/bet/discovery/sources/api_football.py` | API-Football adapter (priority 3, football only) |

### API Clients (wrapped by adapters)

| File | Purpose |
|------|---------|
| `src/bet/api_clients/sofascore.py` | SofaScore HTTP client |
| `src/bet/api_clients/api_football.py` | API-Football HTTP client |
| `src/bet/api_clients/rate_limiter.py` | Shared rate limiter |

### Pipeline Scripts (consumers)

| File | Reads | Writes |
|------|-------|--------|
| `scripts/discover_events.py` | — | `{date}_s1_events.json`, DB tables |
| `scripts/ingest_scan_stats.py` | `{date}_s1_events.json` | `stats_cache/`, DB `team_form` |
| `scripts/build_shortlist.py` | `{date}_s1_events.json`, DB `fixtures` | `{date}_s2_shortlist.json` |
| `scripts/data_enrichment_agent.py` | Shortlist, DB `team_form` | DB `team_form` (enriched) |
| `scripts/run_scrapers.py` | Shortlist, DB `fixture_sources` | DB `league_profiles`, `player_season_stats` |
| `scripts/deep_stats_report.py` | Shortlist, DB `team_form`, DB `fixture_sources` | Analysis JSON |

### Configuration

| File | Purpose |
|------|---------|
| `config/api_keys.json` | API keys for Odds API, API-Football |
| `config/betting_config.json` | Bankroll, sports, thresholds |
| `config/scan_urls.json` | Legacy — no longer used by discovery |
