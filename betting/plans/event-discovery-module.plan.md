# Sports Event Discovery Module — Implementation Plan

> **Version:** 1.0  
> **Date:** 2026-05-14  
> **Status:** Draft  
> **Replaces:** `scan_events.py` → `UnifiedAPIClient` → scraper-based discovery  

---

## 1. Architecture Overview

### 1.1 Module Purpose

Replace the scraping-based event discovery (`UnifiedAPIClient` routing to Flashscore/BetExplorer/Soccerway/ESPN`) with a clean, API-first module using 3 structured sources:

| Priority | Source | Coverage | Auth | Limit |
|----------|--------|----------|------|-------|
| Primary | SofaScore API | All 5 sports, all leagues, worldwide | None (anti-bot risk, Playwright fallback) | Unlimited (rate-limited) |
| Secondary | The Odds API | Football, Basketball, Hockey, Tennis (no volleyball) | API key (`config/api_keys.json`) | 500 req/month |
| Tertiary | API-Football | Football only | api-sports.io key | 100 req/day |

### 1.2 Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                    EventDiscoveryCoordinator                         │
│                                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐              │
│  │ SofaScore    │  │ Odds API     │  │ API-Football  │              │
│  │ Adapter      │  │ Adapter      │  │ Adapter       │              │
│  │ (all sports) │  │ (4 sports    │  │ (football     │              │
│  │              │  │  + odds)     │  │  only)        │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬────────┘              │
│         │                  │                  │                       │
│         ▼                  ▼                  ▼                       │
│  ┌─────────────────────────────────────────────────────┐            │
│  │              DeduplicationEngine                     │            │
│  │  normalize_team_name() → exact match                 │            │
│  │  rapidfuzz fallback → fuzzy match (>85 score)        │            │
│  │  kickoff window ±2h → temporal match                 │            │
│  └──────────────────────┬──────────────────────────────┘            │
│                          │                                           │
│                          ▼                                           │
│  ┌─────────────────────────────────────────────────────┐            │
│  │              List[MergedFixture]                      │            │
│  │  Each fixture has 1-3 source cross-references        │            │
│  └──────────────────────┬──────────────────────────────┘            │
│                          │                                           │
└──────────────────────────┼───────────────────────────────────────────┘
                           │
                           ▼
          ┌────────────────────────────────┐
          │         Persistence Layer       │
          │                                │
          │  TeamRepo.find_or_create()     │
          │  CompetitionRepo.find_or_create│
          │  FixtureRepo.upsert()          │
          │  FixtureSourceRepo.upsert()    │  ← NEW
          │  ScanResultRepo.bulk_insert()  │
          │                                │
          │  → betting.db (R2 compliant)   │
          │  → {date}_s1_events.json       │
          └────────────────────────────────┘
```

### 1.3 Module Structure

```
src/bet/discovery/
├── __init__.py              # Public API: discover_events()
├── coordinator.py           # EventDiscoveryCoordinator — orchestrates sources + merge + persist
├── dedup.py                 # DeduplicationEngine — normalize + fuzzy + temporal matching
├── models.py                # Pydantic v2 schemas + SQLAlchemy declarative model
├── repository.py            # FixtureSourceRepo (sqlite3, R2 compliant)
└── sources/
    ├── __init__.py          # SourceAdapter Protocol definition
    ├── base.py              # AbstractSourceAdapter with shared logic
    ├── sofascore.py         # Wraps existing SofascoreClient
    ├── odds_api.py          # Wraps existing Odds API patterns from fetch_odds_api.py
    └── api_football.py      # Wraps existing APIFootballClient
```

### 1.4 Key Design Decisions

**ORM strategy — Pydantic for validation, sqlite3 for persistence:**
- SQLAlchemy is in `pyproject.toml` but the **entire pipeline** uses raw `sqlite3` + the repository pattern via `get_db()` (R2). Introducing full ORM sessions would create a split-brain architecture.
- **Decision:** Pydantic v2 models validate all API responses at the system boundary. SQLAlchemy declarative model documents the `fixture_sources` schema. Actual DB writes use the sqlite3 repository pattern (new `FixtureSourceRepo`). This keeps R2 compliance and avoids transaction conflicts.

**Dedup strategy — normalize first, fuzz second:**
- Primary: `normalize_team_name()` from `scripts/utils.py` (strips diacritics, suffixes like FC/SC/United, parentheticals)
- Secondary: `rapidfuzz.fuzz.token_sort_ratio()` for cases normalization doesn't catch (e.g., "Dynamo Kyiv" vs "Dynamo Kiev")
- Temporal: kickoff times within ±2 hours treated as same match (timezone interpretation differences)
- Compound dedup key: `{sport}|{norm_home}|{norm_away}|{kickoff_date}`

**Source orchestration — concurrent fetch, sequential merge:**
- All 3 sources fetch concurrently (ThreadPoolExecutor, one thread per source)
- Results merge sequentially in priority order: SofaScore first (primary identity), then Odds API matches are attached, then API-Football matches
- SofaScore fixture ID becomes the `fixtures.external_id` (primary); other IDs go to `fixture_sources`

**Backward compatibility:**
- Produces identical DB output to `scan_events.py`: fixtures, teams, competitions, scan_results
- Produces identical JSON at `betting/data/{date}_s1_events.json`
- `build_shortlist.py` and downstream scripts require zero changes

---

## 2. Database Changes

### 2.1 New Table: `fixture_sources`

```sql
-- Schema v8: Multi-source fixture identity tracking
CREATE TABLE IF NOT EXISTS fixture_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
    source TEXT NOT NULL,           -- 'sofascore', 'odds-api', 'api-football'
    external_id TEXT NOT NULL,      -- source-specific event/fixture ID
    confidence REAL NOT NULL DEFAULT 1.0,  -- match confidence: 1.0=exact, <1.0=fuzzy
    raw_data TEXT,                  -- optional JSON: source-specific metadata
    fetched_at TEXT NOT NULL,
    UNIQUE(fixture_id, source)
);

CREATE INDEX IF NOT EXISTS idx_fixture_sources_fixture ON fixture_sources(fixture_id);
CREATE INDEX IF NOT EXISTS idx_fixture_sources_source_ext ON fixture_sources(source, external_id);
```

**Column rationale:**
- `confidence`: Tracks dedup quality. `1.0` = exact normalized match. `0.85-0.99` = fuzzy matched. Allows downstream filtering.
- `raw_data`: Source-specific metadata (e.g., Odds API sport_key, SofaScore tournament object). JSON blob, nullable.
- `UNIQUE(fixture_id, source)`: One entry per source per fixture. ON CONFLICT → update.

### 2.2 Migration: v7 → v8

In `src/bet/db/schema.py`, add migration block:

```python
if from_version < 8:
    # v8: Multi-source fixture identity
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fixture_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id INTEGER NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
            source TEXT NOT NULL,
            external_id TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            raw_data TEXT,
            fetched_at TEXT NOT NULL,
            UNIQUE(fixture_id, source)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fixture_sources_fixture ON fixture_sources(fixture_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fixture_sources_source_ext ON fixture_sources(source, external_id)")
    # Backfill from existing fixtures.external_id
    conn.execute("""
        INSERT OR IGNORE INTO fixture_sources (fixture_id, source, external_id, confidence, fetched_at)
        SELECT id, source, external_id, 1.0, fetched_at
        FROM fixtures
        WHERE external_id IS NOT NULL AND external_id != '' AND source IS NOT NULL AND source != ''
    """)
```

### 2.3 Existing Tables (no schema changes, usage unchanged)

| Table | Role in Discovery |
|-------|-------------------|
| `sports` | Resolved via `SportRepo.get_by_name()` |
| `teams` | Created/resolved via `TeamRepo.find_or_create()` |
| `competitions` | Created/resolved via `CompetitionRepo.find_or_create()` |
| `fixtures` | Upserted via `FixtureRepo.upsert()`. `external_id` set to primary source ID, `source` set to primary source name |
| `scan_results` | Written via `ScanResultRepo.bulk_insert()` for per-source tracking |

---

## 3. Module Specifications

### 3.1 Pydantic Models (`src/bet/discovery/models.py`)

```python
from datetime import datetime
from pydantic import BaseModel, Field

class DiscoveredEvent(BaseModel):
    """A single event as returned by one source adapter."""
    source: str                          # 'sofascore', 'odds-api', 'api-football'
    external_id: str                     # Source-specific event ID
    sport: str                           # 'football', 'basketball', etc.
    competition: str                     # League/tournament name
    country: str = ""                    # Country of competition
    home_team: str                       # Home team name (source-native)
    away_team: str                       # Away team name (source-native)
    kickoff: datetime                    # UTC kickoff time
    status: str = "scheduled"            # Event status
    odds: dict | None = None             # Pre-match odds (from Odds API)
    raw_data: dict | None = None         # Source-specific extra data

class SourceRef(BaseModel):
    """Cross-reference to a source for a merged fixture."""
    source: str
    external_id: str
    confidence: float = 1.0              # Dedup match confidence
    raw_data: dict | None = None

class MergedFixture(BaseModel):
    """A fixture after dedup + merge from multiple sources."""
    sport: str
    competition: str
    country: str = ""
    home_team: str                       # Canonical name (from primary source)
    away_team: str
    kickoff: datetime
    status: str = "scheduled"
    sources: list[SourceRef]             # 1-3 source cross-references
    primary_source: str                  # Which source "owns" canonical names
    primary_external_id: str             # External ID from primary source
    odds: dict | None = None             # Best available odds data
    
    @property
    def source_count(self) -> int:
        return len(self.sources)

class DiscoveryResult(BaseModel):
    """Result of a full discovery run."""
    date: str
    fixtures: list[MergedFixture]
    total_discovered: int                # Raw events before dedup
    total_after_dedup: int               # After merge
    by_sport: dict[str, int]             # Count per sport after dedup
    source_stats: dict[str, SourceRunStats]
    issues: list[str] = Field(default_factory=list)
    verdict: str = "OK"                  # OK, PARTIAL, FAILED

class SourceRunStats(BaseModel):
    """Per-source statistics for a discovery run."""
    source: str
    events_fetched: int = 0
    sports_covered: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    available: bool = True
```

### 3.2 SQLAlchemy Declarative Model (schema documentation)

In the same `models.py`, for schema documentation and potential future ORM migration:

```python
from sqlalchemy import Column, Integer, Text, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class FixtureSourceModel(Base):
    """SQLAlchemy model for fixture_sources — schema documentation only.
    Actual writes use FixtureSourceRepo (sqlite3, R2 compliant).
    """
    __tablename__ = "fixture_sources"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False)
    source = Column(Text, nullable=False)
    external_id = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False, default=1.0)
    raw_data = Column(Text, nullable=True)
    fetched_at = Column(Text, nullable=False)
    
    __table_args__ = (
        UniqueConstraint("fixture_id", "source", name="uq_fixture_source"),
    )
```

### 3.3 Source Adapter Protocol (`src/bet/discovery/sources/__init__.py`)

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class SourceAdapter(Protocol):
    """Protocol for event discovery source adapters."""
    name: str
    priority: int          # 1=primary, 2=secondary, 3=tertiary
    supported_sports: list[str]
    
    def fetch_events(self, date: str, sport: str) -> list[DiscoveredEvent]:
        """Fetch events for a single sport on a date. Returns empty list on failure."""
        ...
    
    def is_available(self) -> bool:
        """Check if this source can make requests (API key present, etc.)."""
        ...
```

### 3.4 Source Adapters

**SofaScore Adapter** (`sources/sofascore.py`):
- Wraps existing `SofascoreClient` from `src/bet/api_clients/sofascore.py`
- Maps sport names to SofaScore slugs: `{"football": "football", "basketball": "basketball", "tennis": "tennis", "hockey": "ice-hockey", "volleyball": "volleyball"}`
- Calls `SofascoreClient.get_fixtures(date, sport_slug)` → converts `APIFixture` → `DiscoveredEvent`
- Handles 403 gracefully (SofascoreClient already has Playwright fallback + circuit breaker)
- No API key needed — `is_available()` always returns `True`

**Odds API Adapter** (`sources/odds_api.py`):
- Wraps patterns from `scripts/fetch_odds_api.py` (does NOT import it — creates clean adapter)
- Uses `SPORT_KEY_MAP` to resolve our sport names → Odds API sport keys
- Calls `discover_active_sport_keys()` pattern to get seasonal keys (tennis)
- Fetches odds via `GET /v4/sports/{key}/odds`
- Each odds event → `DiscoveredEvent` with `odds` field populated
- `is_available()` checks API key from `config/api_keys.json` (key: `"odds-api"`)
- No volleyball coverage — `supported_sports` excludes it

**API-Football Adapter** (`sources/api_football.py`):
- Wraps existing `APIFootballClient` from `src/bet/api_clients/api_football.py`
- Calls `APIFootballClient.get_fixtures(date)` → converts `APIFixture` → `DiscoveredEvent`
- Football only — `supported_sports = ["football"]`
- `is_available()` checks API key + daily quota via `RateLimiter`

### 3.5 Deduplication Engine (`src/bet/discovery/dedup.py`)

```python
class DeduplicationEngine:
    """Merge events from multiple sources into unified fixtures."""
    
    FUZZY_THRESHOLD = 85          # rapidfuzz score threshold
    KICKOFF_WINDOW_HOURS = 2      # ±2h for temporal matching
    
    def __init__(self, fuzzy_threshold: int = 85):
        self.fuzzy_threshold = fuzzy_threshold
    
    def merge(self, events_by_source: dict[str, list[DiscoveredEvent]]) -> list[MergedFixture]:
        """Merge events from all sources.
        
        Args:
            events_by_source: {"sofascore": [...], "odds-api": [...], "api-football": [...]}
        
        Algorithm:
            1. Group all events by sport
            2. For primary source (sofascore): create initial MergedFixture list
            3. For each secondary/tertiary event: find matching primary fixture
               a. Exact match: normalized team names + kickoff date
               b. Fuzzy match: rapidfuzz.fuzz.token_sort_ratio > threshold + kickoff ±2h
            4. Unmatched secondary/tertiary events become new MergedFixtures
        """
        ...
    
    def _match_key(self, event: DiscoveredEvent) -> str:
        """Exact dedup key: sport|norm_home|norm_away|kickoff_date."""
        ...
    
    def _fuzzy_match(self, event: DiscoveredEvent, candidates: list[MergedFixture]) -> tuple[MergedFixture | None, float]:
        """Find best fuzzy match among candidates. Returns (match, confidence)."""
        ...
    
    def _kickoff_within_window(self, t1: datetime, t2: datetime) -> bool:
        """Check if two kickoff times are within ±KICKOFF_WINDOW_HOURS."""
        ...
```

### 3.6 Coordinator (`src/bet/discovery/coordinator.py`)

```python
class EventDiscoveryCoordinator:
    """Orchestrates event discovery from multiple sources."""
    
    SPORTS = ["football", "volleyball", "basketball", "tennis", "hockey"]
    
    def __init__(
        self,
        sources: list[SourceAdapter] | None = None,
        dedup_engine: DeduplicationEngine | None = None,
    ):
        """Injectable sources + dedup for testability."""
        ...
    
    def discover(self, date: str, sports: list[str] | None = None, verbose: bool = False) -> DiscoveryResult:
        """Run full discovery pipeline.
        
        Steps:
            1. Fetch events from all sources (concurrent)
            2. Deduplicate + merge
            3. Persist to DB
            4. Write backward-compatible JSON
            5. Return result with stats
        """
        ...
    
    def _fetch_all_sources(self, date: str, sports: list[str]) -> dict[str, list[DiscoveredEvent]]:
        """Fetch from all sources concurrently using ThreadPoolExecutor."""
        ...
    
    def _persist(self, date: str, fixtures: list[MergedFixture], conn: sqlite3.Connection) -> int:
        """Write merged fixtures to DB using existing repos. Returns count written."""
        ...
    
    def _write_json(self, date: str, fixtures: list[MergedFixture]) -> Path:
        """Write backward-compatible {date}_s1_events.json."""
        ...
```

### 3.7 Repository (`src/bet/discovery/repository.py`)

```python
class FixtureSourceRepo:
    """Repository for fixture_sources junction table (R2 compliant, sqlite3)."""
    
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
    
    def upsert(self, fixture_id: int, source: str, external_id: str,
               confidence: float = 1.0, raw_data: dict | None = None) -> int:
        """Insert or update a fixture-source mapping. Returns row ID."""
        ...
    
    def get_by_fixture(self, fixture_id: int) -> list[dict]:
        """Get all source references for a fixture."""
        ...
    
    def get_by_source_id(self, source: str, external_id: str) -> dict | None:
        """Look up fixture by source-specific external ID."""
        ...
    
    def bulk_upsert(self, records: list[tuple]) -> int:
        """Batch upsert source references. Returns count written."""
        ...
```

---

## 4. Implementation Tasks

### Phase 1: Foundation — Models, Schema, Repository

- [x] **Task 1.1** [CREATE] `src/bet/discovery/__init__.py`
  - Package init with public API function `discover_events()`
  - Re-exports key types: `DiscoveredEvent`, `MergedFixture`, `DiscoveryResult`
  - **Definition of done:** Module importable as `from bet.discovery import discover_events`

- [x] **Task 1.2** [CREATE] `src/bet/discovery/models.py`
  - Pydantic v2 models: `DiscoveredEvent`, `SourceRef`, `MergedFixture`, `DiscoveryResult`, `SourceRunStats`
  - SQLAlchemy declarative model: `FixtureSourceModel` (schema documentation)
  - **Definition of done:** All models validate sample data; SA model reflects `fixture_sources` DDL

- [x] **Task 1.3** [MODIFY] `src/bet/db/schema.sql`
  - Add `fixture_sources` table + indexes after existing tables
  - Update schema version comment to v8
  - **Definition of done:** `schema.sql` contains `fixture_sources` CREATE TABLE with correct FKs and indexes

- [x] **Task 1.4** [MODIFY] `src/bet/db/schema.py`
  - Increment `SCHEMA_VERSION` to 8
  - Add `if from_version < 8:` migration block with CREATE TABLE + backfill
  - **Definition of done:** Calling `init_db()` on a v7 database creates `fixture_sources` and backfills existing data

- [x] **Task 1.5** [MODIFY] `src/bet/db/models.py`
  - Add `FixtureSource` dataclass matching the new table
  - **Definition of done:** `FixtureSource` dataclass has fields: `id, fixture_id, source, external_id, confidence, raw_data, fetched_at`

- [x] **Task 1.6** [CREATE] `src/bet/discovery/repository.py`
  - `FixtureSourceRepo` class with `upsert`, `get_by_fixture`, `get_by_source_id`, `bulk_upsert`
  - Uses parameterized queries (no string interpolation)
  - **Definition of done:** All CRUD operations work against an in-memory SQLite DB in tests

- [x] **Task 1.7** [CREATE] `tests/discovery/test_repository.py`
  - Test `FixtureSourceRepo`: upsert, conflict handling, get_by_fixture, get_by_source_id, bulk_upsert
  - Uses in-memory SQLite with schema applied
  - **Definition of done:** All repo operations tested, including edge cases (duplicate inserts, missing fixture FK)

**Phase 1 depends on:** Nothing (foundation)

---

### Phase 2: Deduplication Engine

- [ ] **Task 2.1** [MODIFY] `pyproject.toml`
  - Add `rapidfuzz>=3.0.0` to dependencies
  - **Definition of done:** `pip install -e .` succeeds with rapidfuzz available

- [ ] **Task 2.2** [CREATE] `src/bet/discovery/dedup.py`
  - `DeduplicationEngine` class
  - `merge()`: groups by sport → exact match → fuzzy fallback → temporal check
  - `_match_key()`: `{sport}|{norm_home}|{norm_away}|{kickoff_date}`
  - `_fuzzy_match()`: uses `rapidfuzz.fuzz.token_sort_ratio` with configurable threshold
  - `_kickoff_within_window()`: ±2h check using UTC-aware datetimes
  - Imports `normalize_team_name` from `scripts/utils.py` (move to `src/bet/` or copy the function)
  - **Definition of done:** Engine correctly merges test fixtures from 3 sources with exact + fuzzy matches

- [ ] **Task 2.3** [MODIFY or CREATE] Move `normalize_team_name` to `src/bet/utils.py`
  - Currently in `scripts/utils.py` — inaccessible from `src/bet/` without sys.path hacks
  - Create `src/bet/utils.py` with `normalize_team_name()` and `normalize_kickoff()`
  - Keep `scripts/utils.py` as a thin re-export to avoid breaking existing scripts
  - **Definition of done:** `from bet.utils import normalize_team_name` works; existing scripts still work

- [ ] **Task 2.4** [CREATE] `tests/discovery/test_dedup.py`
  - Exact match: same teams, same sport, same kickoff → merge
  - Fuzzy match: "FC Barcelona" vs "Barcelona" → merge with confidence < 1.0
  - Cross-source: SofaScore + Odds API + API-Football events for same match → single MergedFixture with 3 sources
  - Temporal: events 1h apart → merge; events 3h apart → separate
  - No false positive: "Real Madrid" vs "Real Sociedad" → NOT merged
  - Sport isolation: same team name in different sports → NOT merged
  - **Definition of done:** All edge cases pass; no false positives in test suite

**Phase 2 depends on:** Phase 1 (models)

---

### Phase 3: Source Adapters

- [ ] **Task 3.1** [CREATE] `src/bet/discovery/sources/__init__.py`
  - Define `SourceAdapter` Protocol
  - Export protocol + adapter factory function
  - **Definition of done:** `SourceAdapter` is a runtime-checkable Protocol

- [ ] **Task 3.2** [CREATE] `src/bet/discovery/sources/base.py`
  - `AbstractSourceAdapter` base class
  - Shared logic: logging, timing, error wrapping, sport filtering
  - `_wrap_errors()`: catches API exceptions → returns empty list + logs
  - **Definition of done:** Base class provides `fetch_events_safe()` that wraps `_fetch_events_impl()` with error handling

- [ ] **Task 3.3** [CREATE] `src/bet/discovery/sources/sofascore.py`
  - `SofaScoreAdapter(AbstractSourceAdapter)`
  - `name = "sofascore"`, `priority = 1`, `supported_sports = ["football", "volleyball", "basketball", "tennis", "hockey"]`
  - Sport slug mapping: `{"hockey": "ice-hockey"}` (all others map 1:1)
  - Creates `SofascoreClient` internally (reuses `src/bet/api_clients/sofascore.py`)
  - Converts `APIFixture` → `DiscoveredEvent`
  - **Definition of done:** Adapter fetches events via mocked SofascoreClient; produces valid DiscoveredEvent list

- [ ] **Task 3.4** [CREATE] `src/bet/discovery/sources/odds_api.py`
  - `OddsAPIAdapter(AbstractSourceAdapter)`
  - `name = "odds-api"`, `priority = 2`, `supported_sports = ["football", "basketball", "hockey", "tennis"]`
  - Implements sport key resolution from `SPORT_KEY_MAP` + `discover_active_sport_keys()` pattern
  - Calls `GET /v4/sports/{key}/odds` per sport key (extracted from `fetch_odds_api.py`)
  - Populates `DiscoveredEvent.odds` with structured odds data
  - Loads API key via `BaseAPIClient._load_api_key()` pattern
  - **Definition of done:** Adapter fetches and converts Odds API responses with odds attached; handles quota tracking

- [ ] **Task 3.5** [CREATE] `src/bet/discovery/sources/api_football.py`
  - `APIFootballAdapter(AbstractSourceAdapter)`
  - `name = "api-football"`, `priority = 3`, `supported_sports = ["football"]`
  - Creates `APIFootballClient` internally (reuses `src/bet/api_clients/api_football.py`)
  - Converts `APIFixture` → `DiscoveredEvent`
  - `is_available()` checks API key AND daily quota remaining
  - **Definition of done:** Adapter fetches events via mocked APIFootballClient; respects availability check

- [ ] **Task 3.6** [CREATE] `tests/discovery/test_sources.py`
  - Per-adapter tests with mocked HTTP responses (JSON fixtures from real API responses)
  - Test `is_available()` with/without API keys
  - Test sport filtering (API-Football rejects basketball)
  - Test error handling (403, 429, network timeout → empty list + error logged)
  - Test Odds API multi-key resolution (multiple soccer_* keys per "football")
  - **Definition of done:** Each adapter tested with realistic mock data; error paths covered

**Phase 3 depends on:** Phase 1 (models), Phase 2 (normalize_team_name move)

---

### Phase 4: Coordinator + Integration

- [ ] **Task 4.1** [CREATE] `src/bet/discovery/coordinator.py`
  - `EventDiscoveryCoordinator` class
  - Constructor: injectable `sources` list + `dedup_engine` for testability
  - Default sources: `[SofaScoreAdapter(), OddsAPIAdapter(), APIFootballAdapter()]`
  - `discover(date, sports, verbose)`:
    1. Fetch from all sources concurrently (`ThreadPoolExecutor(max_workers=3)`)
    2. Deduplicate via `DeduplicationEngine.merge()`
    3. Persist to DB via existing repos (`get_db()` context, R2)
    4. Write `{date}_s1_events.json` (backward compat)
    5. Build + return `DiscoveryResult`
  - `_persist()`: for each MergedFixture — resolve sport, teams, competition, upsert fixture, upsert sources
  - `_write_json()`: same format as current `scan_events.py` output
  - **Definition of done:** Full discovery pipeline runs with mocked sources; DB contains correct fixtures + sources; JSON output matches expected format

- [ ] **Task 4.2** [UPDATE] `src/bet/discovery/__init__.py`
  - Wire `discover_events()` to `EventDiscoveryCoordinator.discover()`
  - Convenience function: creates coordinator with default sources, calls discover
  - **Definition of done:** `from bet.discovery import discover_events; result = discover_events("2026-05-14")` works end-to-end

- [ ] **Task 4.3** [CREATE] `tests/discovery/test_coordinator.py`
  - Integration test: 3 mock sources → coordinator → verify DB writes
  - Test concurrent fetch (mock sources with `time.sleep` to verify concurrency)
  - Test partial failure: SofaScore fails → falls back to Odds API + API-Football
  - Test total failure: all sources fail → verdict="FAILED"
  - Test JSON output format matches `scan_events.py` output structure
  - Test dedup across sources: same match from 3 sources → 1 fixture + 3 fixture_sources
  - **Definition of done:** All integration scenarios pass with in-memory SQLite

**Phase 4 depends on:** Phases 1, 2, 3

---

### Phase 5: CLI Script + Migration

- [ ] **Task 5.1** [CREATE] `scripts/discover_events.py`
  - CLI arguments: `--date`, `--sport`, `--verbose`, `--stats-first`, `--skip-deep` (same as `scan_events.py`)
  - Calls `discover_events(date, sports, verbose)` from the discovery module
  - Emits `AGENT_SUMMARY:{json}` on stdout (R19 structured output)
  - Exit codes: 0=OK, 1=PARTIAL, 2=FAILED
  - `--verbose`: prints JSON-line progress events
  - **Definition of done:** Script runs from CLI; produces AGENT_SUMMARY; writes DB + JSON; exit code reflects result

- [ ] **Task 5.2** [VERIFY] Backward compatibility with `build_shortlist.py`
  - Run `build_shortlist.py` against DB populated by new discovery module
  - Verify it reads fixtures correctly from DB and/or JSON
  - No code changes expected — just verification
  - **Definition of done:** `build_shortlist.py --date {date}` produces valid shortlist from discovery module output

- [ ] **Task 5.3** [MODIFY] `src/bet/db/repositories.py`
  - Add `FixtureSourceRepo` import in the existing imports block
  - Alternatively, keep it in `src/bet/discovery/repository.py` (preferred — module encapsulation)
  - **Definition of done:** FixtureSourceRepo is importable from the discovery module

**Phase 5 depends on:** Phase 4

---

## 5. Testing Strategy

### 5.1 Unit Tests

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `tests/discovery/test_models.py` | Pydantic model validation | Valid/invalid DiscoveredEvent, MergedFixture serialization, SourceRef defaults |
| `tests/discovery/test_repository.py` | FixtureSourceRepo CRUD | Upsert, conflict, FK constraint, bulk ops |
| `tests/discovery/test_dedup.py` | DeduplicationEngine | Exact match, fuzzy match, temporal window, false positive prevention, sport isolation |
| `tests/discovery/test_sources.py` | Source adapters | Mocked HTTP for each source, error handling, sport filtering, availability checks |

### 5.2 Integration Tests

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `tests/discovery/test_coordinator.py` | Full pipeline | 3-source merge → DB persist → JSON output; partial failures; empty results |
| `tests/discovery/test_migration.py` | Schema migration | v7→v8 migration; backfill correctness; idempotency |

### 5.3 Mock Data

Create `tests/discovery/fixtures/` with:
- `sofascore_football.json` — sample SofaScore scheduled-events response
- `sofascore_tennis.json` — sample with tournament data
- `odds_api_soccer_epl.json` — sample Odds API response with odds
- `api_football_fixtures.json` — sample API-Football fixtures response

These are captured from real API responses (sanitized) to ensure realistic testing.

### 5.4 Test Infrastructure

```python
# tests/discovery/conftest.py
@pytest.fixture
def memory_db():
    """In-memory SQLite with full schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()

@pytest.fixture
def mock_sofascore_adapter():
    """SofaScore adapter with mocked HTTP client."""
    ...

@pytest.fixture  
def mock_coordinator(memory_db, mock_sofascore_adapter, ...):
    """Full coordinator with mocked sources and in-memory DB."""
    ...
```

---

## 6. Security Considerations

| Concern | Mitigation |
|---------|------------|
| SQL injection | All queries use parameterized `?` placeholders (existing pattern enforced) |
| API key exposure | Keys loaded from `config/api_keys.json` (gitignored) via `_load_api_key()` pattern; never logged |
| Rate limiting | Each source respects existing `RateLimiter`; Odds API tracks credits via response headers |
| Input validation | Pydantic v2 validates all API responses at system boundary; invalid events are logged + skipped |
| Dependency security | rapidfuzz is a well-maintained package (MIT license, no known CVEs) |

---

## 7. Migration Path

### 7.1 Parallel Running (Week 1)

1. Deploy new module alongside `scan_events.py`
2. Run both: `scan_events.py` writes to DB as before; `discover_events.py` writes to same DB (upsert = safe)
3. Compare outputs: fixture count, sport coverage, team name quality
4. Fix any dedup issues found in comparison

### 7.2 Switch (Week 2)

1. Update `orchestrate-betting-day.prompt.md`: replace `scan_events.py` command with `discover_events.py`
2. Update `copilot-instructions.md` scripted workflow section
3. Keep `scan_events.py` as fallback (renamed to `_legacy_scan_events.py`)

### 7.3 Cleanup (Week 3+)

1. Remove scraper-based source clients no longer needed for discovery (Flashscore, BetExplorer, Soccerway still needed for enrichment — DO NOT remove)
2. Remove `UnifiedAPIClient.get_fixtures()` method (keep `get_deep_data()` for enrichment)
3. Update `source_health` tracking for new sources

### 7.4 What NOT to Change

- `UnifiedAPIClient` stays for **enrichment** (deep data, stats, H2H) — only discovery changes
- `build_shortlist.py` — no changes needed (reads DB + JSON, format unchanged)
- `deep_stats_report.py` — no changes needed
- `data_enrichment_agent.py` — no changes needed
- All downstream scripts (gate_checker, coupon_builder, etc.) — no changes needed

---

## 8. Dependencies Summary

### New Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `rapidfuzz` | `>=3.0.0` | Fuzzy team name matching in dedup engine |

### Existing Dependencies (reused)

| Package | Usage |
|---------|-------|
| `pydantic` | API response validation (DiscoveredEvent, MergedFixture) |
| `sqlalchemy` | Declarative model for fixture_sources (schema documentation) |
| `requests` | HTTP calls in source adapters (via existing clients) |
| `aiosqlite` | Available for future async support |
| `playwright` | SofaScore stealth fallback (existing) |

### Existing Code Reused

| Component | Location | Used By |
|-----------|----------|---------|
| `SofascoreClient` | `src/bet/api_clients/sofascore.py` | SofaScore adapter |
| `APIFootballClient` | `src/bet/api_clients/api_football.py` | API-Football adapter |
| `BaseAPIClient` | `src/bet/api_clients/base_client.py` | Key loading, retry logic |
| `RateLimiter` | `src/bet/api_clients/rate_limiter.py` | All adapters |
| `normalize_team_name()` | `scripts/utils.py` → `src/bet/utils.py` | Dedup engine |
| `get_db()` | `src/bet/db/connection.py` | Coordinator persistence |
| `FixtureRepo`, `TeamRepo`, `CompetitionRepo`, `SportRepo`, `ScanResultRepo` | `src/bet/db/repositories.py` | Coordinator persistence |
| `Fixture`, `Team`, `Competition`, `Sport` dataclasses | `src/bet/db/models.py` | Coordinator persistence |
| `APIFixture` dataclass | `src/bet/api_clients/api_football.py` | Adapter conversion |

---

## 9. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| SofaScore blocks API + Playwright | Medium | High (primary source) | Odds API + API-Football provide fallback; coordinator handles gracefully |
| Odds API quota exceeded mid-month | Low | Medium | Track remaining credits; skip if <10 remaining; discovery still works with SofaScore alone |
| Fuzzy dedup false positives | Low | Medium | Conservative threshold (85); kickoff window constraint; sport isolation |
| Fuzzy dedup false negatives | Medium | Low | Unmatched events become separate fixtures; downstream dedup in build_shortlist catches some |
| API-Football daily limit | Medium | Low | Tertiary source; football also covered by SofaScore + Odds API |
| Team name normalization gaps | Medium | Medium | Existing `normalize_team_name()` covers most cases; rapidfuzz catches remainder; DB aliases provide long-term learning |

---

## 10. Open Questions for Review

1. **Deep enrichment in discovery vs. separate step?** Current `scan_events.py` does deep enrichment inline. The new module should focus on discovery only (fixtures + dedup). Deep enrichment stays in `data_enrichment_agent.py`. Confirm this separation is acceptable.

2. **SofaScore sport slug for hockey:** Currently mapped as `"ice-hockey"` in `scan_events.py` SPORT_MAP and in `SofascoreClient.get_fixtures()`. Verify this is correct for the SofaScore API.

3. **Odds API credit budget per run:** Each sport_key + market + region = 1 credit. Football alone has ~47 keys. Should we limit to top leagues (reduces from 47 to ~10 keys, saving 37 credits per run)?

4. **normalize_team_name relocation:** Moving to `src/bet/utils.py` is clean but creates a dual-location period. Alternative: import from scripts/utils.py with proper sys.path. Recommendation: move + re-export.
