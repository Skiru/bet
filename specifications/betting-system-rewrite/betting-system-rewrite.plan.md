# Betting System Rewrite — Implementation Plan

| Field | Value |
|---|---|
| Created | 2026-05-03 |
| Status | Draft |
| Phases | 8 |
| Estimated Tasks | 42 |
| Tech Stack | Python 3.11+, SQLite (WAL mode), asyncio, aiosqlite, Playwright, pytest |

---

## Architecture Overview

### New Package Structure

```
bet/
├── pyproject.toml                          [CREATE]
├── src/
│   └── bet/
│       ├── __init__.py                     [CREATE]
│       ├── cli.py                          [CREATE]  — CLI entry point
│       ├── config.py                       [CREATE]  — Simplified config loader
│       ├── db/
│       │   ├── __init__.py                 [CREATE]
│       │   ├── connection.py               [CREATE]  — DB connection + WAL mode
│       │   ├── schema.sql                  [CREATE]  — DDL statements
│       │   ├── schema.py                   [CREATE]  — Schema init + migrations
│       │   ├── models.py                   [CREATE]  — Dataclass row models
│       │   └── repositories.py             [CREATE]  — CRUD per entity
│       ├── scanner/
│       │   ├── __init__.py                 [CREATE]
│       │   ├── discovery.py                [CREATE]  — Parallel fixture discovery
│       │   ├── odds_fetcher.py             [CREATE]  — Odds from APIs + scrapers
│       │   └── playwright_pool.py          [CREATE]  — Managed browser pool
│       ├── stats/
│       │   ├── __init__.py                 [CREATE]
│       │   ├── enrichment.py               [CREATE]  — Incremental stat fetching
│       │   ├── safety_scores.py            [CREATE]  — Core safety score algorithm
│       │   └── market_ranking.py           [CREATE]  — Rank markets per fixture
│       ├── coupon/
│       │   ├── __init__.py                 [CREATE]
│       │   ├── builder.py                  [CREATE]  — Max 3-leg coupon builder
│       │   ├── translations.py             [CREATE]  — Polish market names
│       │   └── shopping_list.py            [CREATE]  — Betclic shopping list output
│       ├── pipeline/
│       │   ├── __init__.py                 [CREATE]
│       │   ├── orchestrator.py             [CREATE]  — 5-step pipeline + resume
│       │   └── progress.py                 [CREATE]  — Progress reporting
│       ├── settlement/
│       │   ├── __init__.py                 [CREATE]
│       │   ├── settler.py                  [CREATE]  — DB-based settlement
│       │   └── learning.py                 [CREATE]  — Betclic learning analysis
│       ├── api_clients/
│       │   ├── __init__.py                 [CREATE]  — Client registry/factory
│       │   ├── base_client.py              [REUSE]   — from scripts/api_clients/
│       │   ├── rate_limiter.py             [REUSE]   — from scripts/api_clients/
│       │   ├── api_football.py             [MODIFY]  — adapt to write to DB
│       │   ├── api_basketball.py           [MODIFY]  — adapt to write to DB
│       │   ├── api_hockey.py               [MODIFY]  — adapt to write to DB
│       │   ├── api_volleyball.py           [MODIFY]  — adapt to write to DB
│       │   └── the_odds_api.py             [MODIFY]  — from scripts/fetch_odds_api.py
│       ├── adapters/
│       │   ├── __init__.py                 [CREATE]
│       │   ├── flashscore.py               [MODIFY]  — from scripts/adapters/flashscore_adapter.py
│       │   ├── betexplorer.py              [MODIFY]  — from scripts/adapters/betexplorer_adapter.py
│       │   └── scores24.py                 [MODIFY]  — from scripts/adapters/scores24_adapter.py
│       └── utils/
│           ├── __init__.py                 [CREATE]
│           ├── team_names.py               [REUSE]   — from scripts/utils.py
│           └── odds.py                     [CREATE]  — EV, Kelly, odds conversion
├── tests/
│   ├── conftest.py                         [CREATE]  — pytest fixtures, in-memory DB
│   ├── test_db.py                          [CREATE]
│   ├── test_safety_scores.py              [CREATE]
│   ├── test_coupon_builder.py             [CREATE]
│   ├── test_enrichment.py                 [CREATE]
│   ├── test_pipeline.py                   [CREATE]
│   └── test_settlement.py                [CREATE]
├── scripts/
│   └── migrate_data.py                    [CREATE]  — One-time JSON/CSV → SQLite import
├── config/
│   └── betting_config.json                [MODIFY]  — Simplified to 7 sports
└── betting/
    └── data/
        └── betting.db                     [CREATE]  — SQLite database (generated)
```

### Data Flow

```
CLI (cli.py)
  │
  ▼
Orchestrator (pipeline/orchestrator.py)
  │
  ├─ STEP 1: DISCOVER ──────────────────────────────────────────┐
  │   ├─ scanner/discovery.py  →  API clients (async, parallel) │
  │   ├─ scanner/playwright_pool.py  →  Flashscore scraping     │
  │   ├─ scanner/odds_fetcher.py  →  The-Odds-API + others      │
  │   └─ db/repositories.py  →  SQLite (upsert fixtures, odds)  │
  │                                                              │
  ├─ STEP 2: ENRICH ────────────────────────────────────────────┐
  │   ├─ stats/enrichment.py  →  Check DB TTL, fetch stale only │
  │   ├─ api_clients/*  →  L10/L5 stats per team                │
  │   └─ db/repositories.py  →  SQLite (upsert team_form)       │
  │                                                              │
  ├─ STEP 3: ANALYZE ───────────────────────────────────────────┐
  │   ├─ stats/safety_scores.py  →  Compute per-market scores   │
  │   ├─ stats/market_ranking.py  →  Rank all candidates        │
  │   └─ settlement/learning.py  →  Betclic hit rates (advisory)│
  │                                                              │
  ├─ STEP 4: BUILD ─────────────────────────────────────────────┐
  │   ├─ coupon/builder.py  →  Select top picks, 2-3 leg combos │
  │   ├─ coupon/translations.py  →  Polish market names          │
  │   └─ coupon/shopping_list.py  →  Markdown output for user    │
  │                                                              │
  └─ STEP 5: SETTLE (on demand) ────────────────────────────────┐
      ├─ settlement/settler.py  →  Fetch results, update DB      │
      └─ settlement/learning.py  →  Refresh analysis             │
```

### Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Database | SQLite + WAL mode | Zero infra, single user, stdlib `sqlite3` + `aiosqlite` for async |
| Async DB | `aiosqlite` | sqlite3 is sync — `aiosqlite` wraps in thread pool, enables async pipeline |
| Parallelism | `asyncio.gather()` per sport group | API calls + scraping run concurrently; DB writes are sequential |
| Package layout | `src/bet/` with `pyproject.toml` | Proper Python packaging, clean imports (`from bet.db import ...`) |
| Testing | pytest + in-memory SQLite | Fast tests, no file cleanup, fixtures for common data |
| Config | Single JSON + env vars for API keys | Existing pattern preserved, simplified |
| State/Resume | `pipeline_runs` table in SQLite | No separate state JSON files; query pipeline history |
| Betclic learning | Advisory only — NEVER auto-reject | Per user's permanent rule (memory) |

---

## Phase 1: Database Foundation

**Goal**: Create SQLite schema, connection management, and one-time migration from existing JSON/CSV data.

### Task 1.1: Project Setup & pyproject.toml

**Tag**: `[CREATE]`
**Files**: `pyproject.toml`, `src/bet/__init__.py`

Create the Python package configuration:

```toml
# pyproject.toml
[project]
name = "bet"
version = "2.0.0"
requires-python = ">=3.11"
dependencies = [
    "aiosqlite>=0.20.0",
    "requests>=2.31.0",
    "beautifulsoup4>=4.12.0",
    "playwright>=1.40.0",
    "lxml>=5.0.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23.0"]

[project.scripts]
bet = "bet.cli:main"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Definition of Done**:
- [x] `pyproject.toml` exists with all dependencies listed
- [x] `pip install -e .` succeeds
- [x] `python -c "import bet"` succeeds
- [x] `src/bet/__init__.py` exists (can be empty)

---

### Task 1.2: SQLite Schema Definition

**Tag**: `[CREATE]`
**Files**: `src/bet/db/schema.sql`, `src/bet/db/schema.py`

The schema from the research document, implemented as SQL DDL:

```sql
-- src/bet/db/schema.sql

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,          -- 'football', 'basketball', etc.
    tier INTEGER NOT NULL DEFAULT 1,    -- 1=key, 2=support
    stat_keys TEXT NOT NULL DEFAULT '[]' -- JSON array of stat key names
);

CREATE TABLE IF NOT EXISTS competitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id INTEGER NOT NULL REFERENCES sports(id),
    name TEXT NOT NULL,
    country TEXT,
    importance INTEGER NOT NULL DEFAULT 3, -- 1(highest)..5(lowest)
    season TEXT,
    UNIQUE(sport_id, name, season)
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id INTEGER NOT NULL REFERENCES sports(id),
    name TEXT NOT NULL,                 -- canonical name
    aliases TEXT NOT NULL DEFAULT '[]', -- JSON array of known name variants
    country TEXT,
    venue TEXT,
    style_tags TEXT NOT NULL DEFAULT '[]', -- JSON array: ["pressing","defensive",...]
    UNIQUE(sport_id, name)
);

CREATE TABLE IF NOT EXISTS fixtures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT,                   -- source-specific ID (e.g., API-Football fixture ID)
    sport_id INTEGER NOT NULL REFERENCES sports(id),
    competition_id INTEGER REFERENCES competitions(id),
    home_team_id INTEGER NOT NULL REFERENCES teams(id),
    away_team_id INTEGER NOT NULL REFERENCES teams(id),
    kickoff TEXT NOT NULL,              -- ISO 8601 datetime
    status TEXT NOT NULL DEFAULT 'scheduled', -- scheduled|live|finished|postponed|cancelled
    score_home INTEGER,
    score_away INTEGER,
    source TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(sport_id, home_team_id, away_team_id, kickoff)
);

CREATE TABLE IF NOT EXISTS match_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    stat_key TEXT NOT NULL,             -- 'corners', 'fouls', 'shots', etc.
    stat_value REAL NOT NULL,
    source TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(fixture_id, team_id, stat_key, source)
);

CREATE TABLE IF NOT EXISTS team_form (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    sport_id INTEGER NOT NULL REFERENCES sports(id),
    stat_key TEXT NOT NULL,
    l10_values TEXT NOT NULL DEFAULT '[]',   -- JSON: last 10 values
    l5_values TEXT NOT NULL DEFAULT '[]',    -- JSON: last 5 values
    l10_avg REAL,
    l5_avg REAL,
    h2h_values TEXT NOT NULL DEFAULT '[]',   -- JSON: H2H values (vs opponent stored separately)
    h2h_opponent_id INTEGER REFERENCES teams(id),
    trend TEXT,                              -- 'up', 'down', 'stable'
    updated_at TEXT NOT NULL,
    source TEXT,
    UNIQUE(team_id, stat_key, h2h_opponent_id)
);

CREATE TABLE IF NOT EXISTS odds_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    bookmaker TEXT NOT NULL,
    market TEXT NOT NULL,                -- 'corners_total_ou', 'match_winner', etc.
    selection TEXT NOT NULL,             -- 'over_9.5', 'home', etc.
    odds REAL NOT NULL,
    line REAL,                          -- e.g., 9.5 for O/U 9.5
    fetched_at TEXT NOT NULL,
    is_closing INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_id TEXT NOT NULL UNIQUE,      -- e.g., 'AKO-2026-05-03-001'
    coupon_type TEXT NOT NULL DEFAULT 'AKO', -- AKO|SINGLE
    total_odds REAL,
    stake_pln REAL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending|won|lost|void|partial
    pnl_pln REAL,
    placed_at TEXT,
    settled_at TEXT,
    betclic_ref TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_id INTEGER NOT NULL REFERENCES coupons(id),
    fixture_id INTEGER REFERENCES fixtures(id),
    sport TEXT NOT NULL,
    event_name TEXT NOT NULL,           -- 'Liverpool vs Arsenal'
    market TEXT NOT NULL,               -- 'Corners Total O/U'
    selection TEXT NOT NULL,            -- 'OVER 9.5'
    odds REAL NOT NULL,
    min_odds REAL,                      -- minimum acceptable odds
    safety_score REAL,
    hit_rate REAL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending|won|lost|void|push
    pnl_pln REAL,
    settled_at TEXT,
    market_pl TEXT,                     -- Polish market name for Betclic
    navigation_hint TEXT               -- Betclic app navigation path
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,                 -- betting day YYYY-MM-DD
    step TEXT NOT NULL,                 -- 'discover', 'enrich', 'analyze', 'build', 'settle'
    status TEXT NOT NULL DEFAULT 'pending', -- pending|running|completed|failed
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    stats TEXT,                         -- JSON: step-specific metrics
    UNIQUE(date, step)
);

CREATE TABLE IF NOT EXISTS source_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    last_success TEXT,
    last_failure TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    total_requests INTEGER NOT NULL DEFAULT 0,
    total_failures INTEGER NOT NULL DEFAULT 0,
    avg_response_ms REAL,
    UNIQUE(source_name)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_fixtures_kickoff ON fixtures(kickoff);
CREATE INDEX IF NOT EXISTS idx_fixtures_sport_status ON fixtures(sport_id, status);
CREATE INDEX IF NOT EXISTS idx_match_stats_team_key ON match_stats(team_id, stat_key);
CREATE INDEX IF NOT EXISTS idx_match_stats_fixture ON match_stats(fixture_id);
CREATE INDEX IF NOT EXISTS idx_team_form_team_stat ON team_form(team_id, stat_key);
CREATE INDEX IF NOT EXISTS idx_odds_history_fixture ON odds_history(fixture_id);
CREATE INDEX IF NOT EXISTS idx_bets_coupon ON bets(coupon_id);
CREATE INDEX IF NOT EXISTS idx_bets_status ON bets(status);
CREATE INDEX IF NOT EXISTS idx_teams_sport ON teams(sport_id);
CREATE INDEX IF NOT EXISTS idx_teams_aliases ON teams(aliases);
```

`schema.py` provides initialization:

```python
# src/bet/db/schema.py

SCHEMA_VERSION = 1

def init_db(conn: sqlite3.Connection) -> None:
    """Execute schema.sql against the connection. Idempotent (IF NOT EXISTS)."""

def get_schema_version(conn: sqlite3.Connection) -> int:
    """Read current schema version from a metadata table."""

def migrate(conn: sqlite3.Connection, from_version: int, to_version: int) -> None:
    """Run incremental migrations. For v1, this is a no-op."""
```

**Definition of Done**:
- [x] `schema.sql` contains all 11 tables with proper FK constraints and indexes
- [x] `schema.py` can initialize a fresh database from `schema.sql`
- [x] `PRAGMA foreign_keys = ON` is enforced
- [x] `PRAGMA journal_mode = WAL` is set
- [x] Running `init_db` twice is idempotent (no errors)
- [x] Test: `test_db.py::test_schema_init` creates all tables in in-memory DB

---

### Task 1.3: Database Connection Management

**Tag**: `[CREATE]`
**Files**: `src/bet/db/connection.py`

```python
# src/bet/db/connection.py

import sqlite3
from pathlib import Path
from contextlib import contextmanager

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent.parent / "betting" / "data" / "betting.db"

@contextmanager
def get_db(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Context manager for SQLite connections.

    - Enables WAL mode and foreign keys
    - Sets row_factory to sqlite3.Row for dict-like access
    - Commits on clean exit, rolls back on exception
    """

def get_async_db(db_path: Path | str = DEFAULT_DB_PATH):
    """Async context manager using aiosqlite. Same pragmas as get_db."""
```

**Definition of Done**:
- [x] `get_db()` returns a connection with WAL mode and FK enforcement
- [x] Connection auto-commits on clean exit from context manager
- [x] Connection rolls back on exception
- [x] `get_async_db()` provides an async-compatible connection via `aiosqlite`
- [x] Test: `test_db.py::test_connection_commit_rollback`

---

### Task 1.4: Row Models (Dataclasses)

**Tag**: `[CREATE]`
**Files**: `src/bet/db/models.py`

Dataclasses representing database rows. These replace `NormalizedFixture` and `NormalizedMatchStats` from `scripts/normalize_stats.py` but preserve the key field names.

```python
# src/bet/db/models.py
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Sport:
    id: int | None
    name: str
    tier: int
    stat_keys: list[str] = field(default_factory=list)

@dataclass
class Team:
    id: int | None
    sport_id: int
    name: str
    aliases: list[str] = field(default_factory=list)
    country: str = ""
    venue: str = ""
    style_tags: list[str] = field(default_factory=list)

@dataclass
class Fixture:
    id: int | None
    sport_id: int
    competition_id: int | None
    home_team_id: int
    away_team_id: int
    kickoff: str
    status: str = "scheduled"
    score_home: int | None = None
    score_away: int | None = None
    external_id: str = ""
    source: str = ""
    fetched_at: str = ""

@dataclass
class MatchStat:
    id: int | None
    fixture_id: int
    team_id: int
    stat_key: str
    stat_value: float
    source: str = ""
    fetched_at: str = ""

@dataclass
class TeamForm:
    id: int | None
    team_id: int
    sport_id: int
    stat_key: str
    l10_values: list[float] = field(default_factory=list)
    l5_values: list[float] = field(default_factory=list)
    l10_avg: float | None = None
    l5_avg: float | None = None
    h2h_values: list[float] = field(default_factory=list)
    h2h_opponent_id: int | None = None
    trend: str = ""
    updated_at: str = ""
    source: str = ""

@dataclass
class OddsRecord:
    id: int | None
    fixture_id: int
    bookmaker: str
    market: str
    selection: str
    odds: float
    line: float | None = None
    fetched_at: str = ""
    is_closing: bool = False

@dataclass
class Coupon:
    id: int | None
    coupon_id: str
    coupon_type: str = "AKO"
    total_odds: float | None = None
    stake_pln: float | None = None
    status: str = "pending"
    pnl_pln: float | None = None
    placed_at: str = ""
    settled_at: str = ""
    betclic_ref: str = ""
    version: int = 1
    created_at: str = ""

@dataclass
class Bet:
    id: int | None
    coupon_id: int
    fixture_id: int | None
    sport: str
    event_name: str
    market: str
    selection: str
    odds: float
    min_odds: float | None = None
    safety_score: float | None = None
    hit_rate: float | None = None
    status: str = "pending"
    pnl_pln: float | None = None
    settled_at: str = ""
    market_pl: str = ""
    navigation_hint: str = ""

@dataclass
class MarketCandidate:
    """A scored market candidate for coupon building. Not persisted — computed."""
    fixture: Fixture
    home_team: Team
    away_team: Team
    sport_name: str
    competition_name: str
    market_name: str
    direction: str       # 'OVER' or 'UNDER'
    line: float
    safety_score: float
    hit_rate_l10: float
    hit_rate_h2h: float | None
    hit_rate_l5: float
    three_way_aligned: bool
    min_odds: float      # 1 / hit_rate
    best_odds: float | None
    ev: float | None     # (hit_rate * odds) - 1
    betclic_hit_rate: float | None  # from Betclic history (advisory)
```

**Definition of Done**:
- [x] All 9 persistent dataclasses match the SQL schema column-for-column
- [x] `MarketCandidate` contains all fields needed for coupon building and shopping list output
- [x] JSON-typed columns (`aliases`, `l10_values`, etc.) are typed as `list` (serialization handled in repositories)
- [x] Imports work: `from bet.db.models import Fixture, Team, Bet`

---

### Task 1.5: Repositories (CRUD Layer)

**Tag**: `[CREATE]`
**Files**: `src/bet/db/repositories.py`

Repository pattern for all database operations. All SQL uses parameterized queries (no f-strings).

```python
# src/bet/db/repositories.py

class SportRepo:
    def __init__(self, conn): ...
    def seed_defaults(self) -> None:
        """Insert the 7 sports with stat_keys from SPORT_STAT_KEYS."""
    def get_by_name(self, name: str) -> Sport | None: ...
    def get_all(self) -> list[Sport]: ...

class TeamRepo:
    def __init__(self, conn): ...
    def find_or_create(self, name: str, sport_id: int, aliases: list[str] | None = None) -> Team:
        """Find team by name or any alias. Create if not found."""
    def resolve(self, name: str, sport_id: int) -> Team | None:
        """Resolve a name (possibly variant) to a canonical Team."""
    def update_aliases(self, team_id: int, new_aliases: list[str]) -> None: ...

class CompetitionRepo:
    def __init__(self, conn): ...
    def find_or_create(self, name: str, sport_id: int, country: str = "", importance: int = 3) -> int:
        """Return competition ID, creating if needed."""

class FixtureRepo:
    def __init__(self, conn): ...
    def upsert(self, fixture: Fixture) -> int:
        """Insert or update fixture. Returns row ID."""
    def get_by_date(self, date: str, sport_id: int | None = None) -> list[Fixture]: ...
    def get_by_id(self, fixture_id: int) -> Fixture | None: ...
    def get_pending_settlement(self, date: str) -> list[Fixture]: ...
    def update_result(self, fixture_id: int, score_home: int, score_away: int, status: str = "finished") -> None: ...

class StatsRepo:
    def __init__(self, conn): ...
    def save_match_stats(self, fixture_id: int, team_id: int, stats: dict[str, float], source: str) -> None:
        """Batch insert match stats (one row per stat_key)."""
    def get_form(self, team_id: int, stat_key: str, n: int = 10) -> list[float]:
        """Get last N values for a stat from finished fixtures, most recent first."""
    def get_h2h_stats(self, team_a_id: int, team_b_id: int, stat_key: str, n: int = 10) -> list[float]:
        """Get stat values from H2H meetings between two teams."""
    def is_stale(self, team_id: int, stat_key: str, max_age_hours: int = 12) -> bool:
        """Check if team_form data is older than max_age_hours."""
    def save_team_form(self, form: TeamForm) -> None:
        """Upsert team_form row (denormalized cache)."""

class OddsRepo:
    def __init__(self, conn): ...
    def save_odds(self, record: OddsRecord) -> None: ...
    def get_best_odds(self, fixture_id: int, market: str, selection: str) -> float | None: ...
    def get_odds_history(self, fixture_id: int, market: str) -> list[OddsRecord]: ...

class CouponRepo:
    def __init__(self, conn): ...
    def create_coupon(self, coupon: Coupon) -> int: ...
    def add_bet(self, bet: Bet) -> int: ...
    def get_pending(self) -> list[Coupon]: ...
    def settle_coupon(self, coupon_id: int, status: str, pnl: float) -> None: ...
    def settle_bet(self, bet_id: int, status: str, pnl: float) -> None: ...
    def get_coupon_with_bets(self, coupon_id: int) -> tuple[Coupon, list[Bet]]: ...

class PipelineRepo:
    def __init__(self, conn): ...
    def start_step(self, date: str, step: str) -> None: ...
    def complete_step(self, date: str, step: str, stats: dict | None = None) -> None: ...
    def fail_step(self, date: str, step: str, error: str) -> None: ...
    def get_completed_steps(self, date: str) -> list[str]: ...
    def get_run_status(self, date: str) -> list[dict]: ...

class SourceHealthRepo:
    def __init__(self, conn): ...
    def record_success(self, source: str, response_ms: float) -> None: ...
    def record_failure(self, source: str) -> None: ...
    def get_health(self, source: str) -> dict | None: ...
    def get_all_health(self) -> list[dict]: ...
```

**Key implementation rules**:
- All queries use `?` parameter placeholders — NEVER string interpolation
- JSON columns (`aliases`, `l10_values`, etc.) are serialized with `json.dumps()` on write, `json.loads()` on read
- `TeamRepo.resolve()` searches both `name` and `aliases` JSON array using `LIKE` or `json_each()`

**Definition of Done**:
- [x] All 9 repository classes implemented with methods listed above
- [x] Zero string-interpolated SQL — all use parameterized queries
- [x] `TeamRepo.resolve()` finds teams by alias (e.g., "Barca" resolves to "FC Barcelona")
- [x] `StatsRepo.get_form()` returns values ordered most-recent-first from `match_stats` + `fixtures` join
- [x] `FixtureRepo.upsert()` uses `INSERT ... ON CONFLICT ... DO UPDATE`
- [ ] Tests: `test_db.py::test_team_resolve_by_alias`, `test_fixture_upsert_dedup`, `test_stats_get_form`

---

### Task 1.6: Data Migration Script

**Tag**: `[CREATE]`
**Files**: `scripts/migrate_data.py`

One-time migration importing existing data into SQLite:

```python
# scripts/migrate_data.py
"""One-time migration: JSON/CSV → SQLite.

Imports:
1. betting/data/betclic_bets_history.json → coupons + bets tables
2. betting/journal/picks-ledger.csv → bets table (supplement)
3. betting/journal/coupons-ledger.csv → coupons table (supplement)
4. betting/data/stats_cache/*.json → team_form table (if available)

Usage:
    python -m scripts.migrate_data
    python -m scripts.migrate_data --dry-run
"""

def migrate_betclic_history(conn, history_path: Path) -> dict:
    """Import betclic_bets_history.json into coupons + bets.
    Returns: {"coupons_imported": N, "bets_imported": M}
    """

def migrate_picks_ledger(conn, ledger_path: Path) -> dict:
    """Import picks-ledger.csv rows as supplemental bet data."""

def migrate_coupons_ledger(conn, ledger_path: Path) -> dict:
    """Import coupons-ledger.csv rows."""

def main(): ...
```

**Definition of Done**:
- [x] Imports all 153 coupons and 489 legs from `betclic_bets_history.json`
- [x] Imports picks from `picks-ledger.csv` (deduplicates against already-imported Betclic data)
- [x] Creates teams and sports entries as needed during import
- [x] `--dry-run` flag shows what would be imported without writing
- [x] After migration, `SELECT COUNT(*) FROM bets` ≥ 489
- [x] After migration, `SELECT COUNT(*) FROM coupons` ≥ 153

---

### Task 1.7: Simplified Configuration

**Tag**: `[MODIFY]`
**Files**: `config/betting_config.json`, `src/bet/config.py`

Simplify config to 7 sports and remove unused fields:

```python
# src/bet/config.py

from dataclasses import dataclass
from pathlib import Path
import json

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "betting_config.json"

@dataclass
class BettingConfig:
    bankroll_pln: float
    daily_exposure_range: tuple[float, float]
    max_stake_pln: float
    max_legs_per_coupon: int          # Hard cap: 3
    min_coupons_per_day: int
    preferred_odds_range: tuple[float, float]
    min_safety_score: float           # Default: 0.60
    timezone: str
    sports: list[str]                 # 7 sports only
    db_path: str

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "BettingConfig": ...
```

New simplified `betting_config.json`:

```json
{
    "bankroll_pln": 47.03,
    "daily_exposure_range": [5.0, 15.0],
    "max_stake_pln": 2.0,
    "max_legs_per_coupon": 3,
    "min_coupons_per_day": 3,
    "preferred_odds_range": [1.30, 3.50],
    "min_safety_score": 0.60,
    "timezone": "Europe/Warsaw",
    "sports": ["football", "volleyball", "basketball", "hockey", "tennis", "snooker", "speedway"],
    "db_path": "betting/data/betting.db"
}
```

**Definition of Done**:
- [x] `BettingConfig.load()` reads and validates the JSON file
- [x] `max_legs_per_coupon` is enforced as 3 (hard cap)
- [x] Only 7 sports are configured (old 14-sport list removed)
- [x] `BettingConfig` is the single source of truth for all configuration values
- [ ] Test: `test_config_loads_defaults`

---

## Phase 2: Utilities & Shared Code

**Goal**: Port reusable utilities and establish shared helpers used across all pipeline steps.

### Task 2.1: Team Name Normalization

**Tag**: `[REUSE]`
**Files**: `src/bet/utils/team_names.py`
**Source**: `scripts/utils.py::normalize_team_name()`

Copy the existing `normalize_team_name()` function. Add a DB-aware wrapper:

```python
# src/bet/utils/team_names.py

def normalize_team_name(name: str) -> str:
    """Normalize for fuzzy matching. Copied from scripts/utils.py."""

def resolve_team(conn, name: str, sport_id: int) -> int:
    """Resolve a team name to a DB team ID, creating if needed.
    Uses normalize_team_name() for alias matching.
    Returns team.id.
    """
```

**Definition of Done**:
- [x] `normalize_team_name()` is identical to the existing implementation in `scripts/utils.py`
- [x] `resolve_team()` finds existing teams by normalized alias match before creating new ones
- [ ] Test: `test_normalize_team_name` with known edge cases (diacritics, FC suffix, parenthetical)

---

### Task 2.2: Odds & EV Calculation Utilities

**Tag**: `[CREATE]`
**Files**: `src/bet/utils/odds.py`

```python
# src/bet/utils/odds.py

def implied_probability(decimal_odds: float) -> float:
    """Convert decimal odds to implied probability. E.g., 2.0 → 0.50"""

def decimal_to_american(decimal_odds: float) -> str:
    """Convert decimal odds to American format."""

def american_to_decimal(american: str) -> float:
    """Convert American odds string to decimal. +150 → 2.50, -200 → 1.50"""

def expected_value(probability: float, odds: float) -> float:
    """EV = (probability * odds) - 1. Positive = +EV."""

def min_acceptable_odds(hit_rate: float) -> float:
    """Minimum odds for +EV: 1 / hit_rate."""

def kelly_fraction(probability: float, odds: float, fraction: float = 0.25) -> float:
    """Fractional Kelly criterion. Returns fraction of bankroll to stake."""

def flat_stake(bankroll: float, max_stake: float = 2.0) -> float:
    """Flat staking: min(max_stake, bankroll * 0.05)."""
```

**Definition of Done**:
- [x] All conversion functions handle edge cases (odds = 1.0, probability = 0, etc.)
- [x] `kelly_fraction` returns 0 when EV ≤ 0
- [x] `flat_stake` never exceeds 5% of bankroll
- [ ] Tests: `test_ev_calculation`, `test_kelly_negative_ev_returns_zero`, `test_american_conversion`

---

### Task 2.3: Polish Market Translations

**Tag**: `[REUSE]`
**Files**: `src/bet/coupon/translations.py`
**Source**: `scripts/coupon_builder.py` (`MARKET_PL`, `DIRECTION_PL`, `SPORT_EMOJI`)

Extract the translation dictionaries from the existing coupon builder:

```python
# src/bet/coupon/translations.py

MARKET_PL: dict[str, str] = { ... }    # from coupon_builder.py
DIRECTION_PL: dict[str, str] = { ... } # from coupon_builder.py
SPORT_EMOJI: dict[str, str] = { ... }  # from coupon_builder.py

def translate_market(market_name: str, direction: str, line: float, team_name: str = "") -> str:
    """Build Polish market description for Betclic.
    E.g., 'Rzuty rożne łącznie Powyżej 9.5'
    """

def betclic_navigation(sport: str, competition: str, home: str, away: str, market_category: str) -> str:
    """Generate Betclic app navigation hint.
    E.g., 'Piłka nożna → Premier League → Liverpool-Arsenal → Statystyki → Rzuty rożne'
    """
```

**Definition of Done**:
- [x] All entries from existing `MARKET_PL` and `DIRECTION_PL` are preserved
- [x] `translate_market()` produces correct Polish strings for all 7 sports
- [x] `betclic_navigation()` generates Betclic app path hints
- [ ] Test: `test_translate_corners_over`

---

### Task 2.4: Market Definitions per Sport

**Tag**: `[REUSE]`
**Files**: `src/bet/stats/market_ranking.py` (partial — market constants)
**Source**: `scripts/normalize_stats.py` (`FOOTBALL_MARKETS`, `BASKETBALL_MARKETS`, etc.)

Port the market definition arrays for the 7 focus sports. Remove markets for discarded sports (baseball, esports, darts, table_tennis, handball, mma, padel).

```python
# Constants in src/bet/stats/market_ranking.py

SPORT_MARKETS = {
    "football": FOOTBALL_MARKETS,    # 16 markets
    "basketball": BASKETBALL_MARKETS, # 11 markets
    "hockey": HOCKEY_MARKETS,        # 7 markets
    "tennis": TENNIS_MARKETS,        # 9 markets
    "volleyball": VOLLEYBALL_MARKETS, # 7 markets
    "snooker": SNOOKER_MARKETS,      # 5 markets
    "speedway": SPEEDWAY_MARKETS,    # 3 markets (new)
}

SPORT_STAT_KEYS = { ... }  # from normalize_stats.py, filtered to 7 sports
```

Also create `SPEEDWAY_MARKETS` (new — not in the current codebase):

```python
SPEEDWAY_MARKETS = [
    {"name": "Total Points O/U", "stat_a": "total_points", "stat_b": "total_points", "is_combined": True},
    {"name": "Team A Points O/U", "stat_a": "heat_points", "stat_b": None, "is_combined": False},
    {"name": "Team B Points O/U", "stat_a": None, "stat_b": "heat_points", "is_combined": False},
]
```

**Definition of Done**:
- [x] Market definitions for all 7 sports are present
- [x] `SPEEDWAY_MARKETS` is defined (new addition)
- [x] Only 7 sports in `SPORT_MARKETS` and `SPORT_STAT_KEYS` (discarded sports removed)
- [x] Stat key lists match the DB `sports.stat_keys` seeded in Task 1.5

---

## Phase 3: Scanner Rewrite

**Goal**: Replace sequential 200-URL scanning with parallel API-first fixture discovery + Playwright pool for scraping gaps.

### Task 3.1: Playwright Browser Pool

**Tag**: `[CREATE]`
**Files**: `src/bet/scanner/playwright_pool.py`

Managed pool of Playwright browser contexts for concurrent scraping:

```python
# src/bet/scanner/playwright_pool.py

import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext

class PlaywrightPool:
    """Pool of Playwright browser contexts for concurrent scraping.

    Usage:
        async with PlaywrightPool(max_contexts=4) as pool:
            page = await pool.acquire()
            try:
                await page.goto(url)
                html = await page.content()
            finally:
                await pool.release(page)
    """
    def __init__(self, max_contexts: int = 4): ...
    async def __aenter__(self): ...
    async def __aexit__(self, *args): ...
    async def acquire(self) -> BrowserContext:
        """Acquire a browser context from the pool. Blocks if all in use."""
    async def release(self, ctx: BrowserContext) -> None:
        """Return a browser context to the pool."""
    async def scrape_page(self, url: str, wait_selector: str | None = None, timeout_ms: int = 15000) -> str:
        """Convenience: acquire context, navigate, return HTML, release."""
```

**Definition of Done**:
- [x] Pool manages N browser contexts (configurable, default 4)
- [x] `acquire()` blocks (via asyncio.Semaphore) when all contexts are in use
- [x] `scrape_page()` is a high-level convenience method
- [x] All contexts are closed on `__aexit__`
- [x] Timeout on navigation (default 15s) prevents hanging
- [ ] Test: `test_pool_concurrent_limit` (mock Playwright — verify semaphore behavior)

---

### Task 3.2: API-First Fixture Discovery

**Tag**: `[CREATE]`
**Files**: `src/bet/scanner/discovery.py`

Parallel fixture discovery using API clients first, Flashscore scraping for gaps:

```python
# src/bet/scanner/discovery.py

import asyncio
from datetime import date

async def discover_fixtures(
    target_date: date,
    sports: list[str],
    db_conn,
    playwright_pool: PlaywrightPool | None = None,
) -> dict[str, int]:
    """Discover fixtures for all sports in parallel.

    Strategy:
    1. API calls (asyncio.gather) for sports with API coverage
    2. Flashscore scraping (Playwright pool) for gaps
    3. Upsert all into DB, deduplicating by (sport, home, away, kickoff)

    Returns: {"football": 45, "basketball": 12, ...} — fixture counts per sport
    """

async def _discover_api(sport: str, target_date: date, db_conn) -> list[Fixture]:
    """Fetch fixtures from sport-specific API client."""

async def _discover_flashscore(sport: str, target_date: date, pool: PlaywrightPool, db_conn) -> list[Fixture]:
    """Scrape Flashscore for fixtures not found via API."""

async def _deduplicate_fixtures(fixtures: list[Fixture], db_conn) -> list[Fixture]:
    """Remove fixtures already in DB (by sport + teams + kickoff)."""
```

**Definition of Done**:
- [x] All 7 sports are discovered in parallel via `asyncio.gather()`
- [x] API clients are tried first; Flashscore fills gaps
- [x] Fixtures are upserted into `fixtures` table with deduplication
- [x] Teams are resolved/created via `TeamRepo.find_or_create()`
- [x] Returns per-sport fixture counts
- [x] Source health is recorded via `SourceHealthRepo`
- [ ] Test: `test_discover_deduplication` (mock API responses, verify no duplicates in DB)

---

### Task 3.3: Odds Fetcher

**Tag**: `[CREATE]`
**Files**: `src/bet/scanner/odds_fetcher.py`
**Source**: Adapted from `scripts/fetch_odds_api.py` and `scripts/fetch_odds_multi.py`

```python
# src/bet/scanner/odds_fetcher.py

async def fetch_odds(
    target_date: date,
    sports: list[str],
    db_conn,
) -> dict[str, int]:
    """Fetch odds from The-Odds-API and store in odds_history.

    Returns: {"football": 120, ...} — odds records saved per sport
    """

async def _fetch_odds_api(sport: str, target_date: date, db_conn) -> int:
    """Fetch from The-Odds-API. Reuses SPORT_KEY_MAP from fetch_odds_api.py."""

def match_odds_to_fixtures(odds_events: list[dict], fixtures: list[Fixture], db_conn) -> int:
    """Match API odds events to DB fixtures by team name similarity.
    Returns number of matched odds records.
    """
```

**Definition of Done**:
- [x] The-Odds-API integration works for football, basketball, hockey, tennis
- [x] Odds are stored in `odds_history` table with `fixture_id` FK
- [x] Event-to-fixture matching uses `normalize_team_name()` for fuzzy matching
- [x] API credit usage is tracked via `RateLimiter`
- [x] Sports without API coverage (volleyball, snooker, speedway) are skipped gracefully
- [ ] Test: `test_odds_match_to_fixture` (verify fuzzy matching)

---

### Task 3.4: Adapt API Clients for DB Writes

**Tag**: `[MODIFY]`
**Files**: `src/bet/api_clients/*.py`
**Source**: Copy from `scripts/api_clients/`, adapt return types

The existing API clients return raw dicts/lists. Adapt them to:
1. Return `Fixture` and `MatchStat` model objects
2. Accept DB connection for direct persistence (optional)
3. Keep `base_client.py` and `rate_limiter.py` as-is

Changes per client:
- `api_football.py`: `get_fixtures()` → returns `list[Fixture]`; `get_fixture_stats()` → returns `list[MatchStat]`
- `api_basketball.py`: Same pattern
- `api_hockey.py`: Same pattern
- `api_volleyball.py`: Same pattern

**Definition of Done**:
- [x] `base_client.py` and `rate_limiter.py` copied without changes
- [x] Each client's `get_fixtures()` returns `list[Fixture]` (model objects, not raw dicts)
- [x] Each client's `get_fixture_stats()` returns `list[MatchStat]`
- [x] Existing retry + rate limiting behavior preserved
- [ ] Test: `test_api_football_returns_fixture_model` (mock HTTP response)

---

### Task 3.5: Essential Adapters (Flashscore, BetExplorer, Scores24)

**Tag**: `[MODIFY]`
**Files**: `src/bet/adapters/flashscore.py`, `src/bet/adapters/betexplorer.py`, `src/bet/adapters/scores24.py`
**Source**: `scripts/adapters/flashscore_adapter.py`, `scripts/adapters/betexplorer_adapter.py`, `scripts/adapters/scores24_adapter.py`

Simplify to extract only what's needed:
- **Flashscore**: fixture list + scores + H2H for all 7 sports
- **BetExplorer**: odds comparison + results
- **Scores24**: H2H, form, trends

All adapters accept HTML (from PlaywrightPool) and return model objects.

```python
# src/bet/adapters/flashscore.py

class FlashscoreAdapter:
    SPORT_URLS = {
        "football": "https://www.flashscore.com/football/",
        "basketball": "https://www.flashscore.com/basketball/",
        # ... all 7 sports
    }

    def parse_fixtures(self, html: str, sport: str) -> list[Fixture]: ...
    def parse_match_detail(self, html: str, sport: str) -> list[MatchStat]: ...
    def parse_h2h(self, html: str) -> list[dict]: ...
```

**Definition of Done**:
- [x] 3 adapters ported (all others discarded: forebet, oddsportal, soccerstats, etc.)
- [x] Each adapter returns model objects (`Fixture`, `MatchStat`)
- [x] Adapters are pure parsers (receive HTML, return data — no I/O)
- [x] Flashscore URL map covers all 7 sports
- [ ] Test: `test_flashscore_parse_fixtures` with sample HTML fixture

---

## Phase 4: Statistics Engine

**Goal**: Incremental stat enrichment from DB, safety score computation, and market ranking.

### Task 4.1: Incremental Stats Enrichment

**Tag**: `[CREATE]`
**Files**: `src/bet/stats/enrichment.py`

```python
# src/bet/stats/enrichment.py

import asyncio

async def enrich_fixtures(
    fixtures: list[Fixture],
    db_conn,
    playwright_pool: PlaywrightPool | None = None,
    max_age_hours: int = 12,
) -> dict[str, int]:
    """Enrich fixtures with team stats. Only fetches stale/missing data.

    For each fixture:
    1. Check if team_form exists and is fresh (< max_age_hours old)
    2. If stale: fetch L10 stats from API → save to match_stats + team_form
    3. If no API: scrape from Flashscore/Scores24
    4. Compute L10/L5 averages, detect trend

    Returns: {"fetched": 45, "cached": 120, "failed": 3}
    """

async def _enrich_team(team: Team, sport: str, stat_keys: list[str], db_conn, pool) -> bool:
    """Fetch and store stats for a single team. Returns True if data was fetched."""

def compute_form(values: list[float], n: int = 10) -> dict:
    """Compute L10/L5 avg and trend from raw values.
    Returns: {"l10_avg": float, "l5_avg": float, "trend": "up"|"down"|"stable"}
    """
```

**Definition of Done**:
- [x] Only fetches data when `StatsRepo.is_stale()` returns True
- [x] API clients are used first; scraping is the fallback
- [x] `team_form` table is updated with computed L10/L5 averages
- [x] Trend is "up" if L5 > L10 by ≥5%, "down" if L5 < L10 by ≥5%, else "stable"
- [x] Source health is tracked for each data fetch
- [ ] Test: `test_enrich_skips_fresh_data`, `test_enrich_fetches_stale_data`

---

### Task 4.2: Safety Score Computation

**Tag**: `[REUSE]` + `[CREATE]`
**Files**: `src/bet/stats/safety_scores.py`
**Source**: Core algorithm from `scripts/compute_safety_scores.py`

Port the deterministic safety score algorithm. Adapt inputs from DB queries instead of JSON files:

```python
# src/bet/stats/safety_scores.py

def compute_safety_score(
    l10_values: list[float],
    h2h_values: list[float] | None,
    l5_values: list[float],
    line: float,
    direction: str,  # "OVER" or "UNDER"
) -> dict:
    """Compute safety score for a single market+line.

    Returns:
    {
        "hit_rate_l10": float,
        "hit_rate_h2h": float | None,
        "hit_rate_l5": float,
        "safety_score": float,  # min(l10, h2h) or l10 if no H2H
        "three_way_aligned": bool,
        "trend": "up" | "down" | "stable",
    }
    """

def compute_all_markets(
    fixture: Fixture,
    home_form: dict[str, TeamForm],
    away_form: dict[str, TeamForm],
    h2h_form: dict[str, list[float]],
    sport: str,
) -> list[MarketCandidate]:
    """Compute safety scores for ALL available markets on a fixture.

    For each market definition (from SPORT_MARKETS):
    1. Get L10/L5 values for relevant stat keys
    2. Try multiple standard lines (e.g., O8.5, O9.5, O10.5 for corners)
    3. Compute safety score for each line
    4. Return ranked list of MarketCandidates

    Standard lines per market are defined in STANDARD_LINES dict.
    """

STANDARD_LINES = {
    "corners": [7.5, 8.5, 9.5, 10.5, 11.5],
    "fouls": [20.5, 21.5, 22.5, 23.5, 24.5],
    "yellow_cards": [2.5, 3.5, 4.5, 5.5],
    "shots": [20.5, 22.5, 24.5, 26.5],
    "shots_on_target": [8.5, 9.5, 10.5, 11.5],
    "goals": [1.5, 2.5, 3.5],
    "points": [195.5, 205.5, 215.5, 225.5],  # basketball
    "total_games": [20.5, 21.5, 22.5, 23.5],  # tennis
    "total_frames": [7.5, 8.5, 9.5],          # snooker
    "total_points": [140.5, 150.5, 160.5, 170.5],  # volleyball
    # ... etc.
}
```

**Definition of Done**:
- [x] Core `compute_safety_score()` produces identical results to `scripts/compute_safety_scores.py` for same inputs
- [x] `compute_all_markets()` evaluates ALL market definitions for a sport, across multiple lines
- [x] Three-way cross-check (L10 + H2H + L5 all supporting direction) is computed
- [x] `MarketCandidate` objects include `min_odds` calculated as `1 / hit_rate`
- [ ] Test: `test_safety_score_corners_example` (known input → known output, matching existing script)
- [ ] Test: `test_three_way_alignment`

---

### Task 4.3: Market Ranking & Candidate Selection

**Tag**: `[CREATE]`
**Files**: `src/bet/stats/market_ranking.py` (analysis functions, in addition to market constants from Task 2.4)

```python
# src/bet/stats/market_ranking.py (analysis functions)

def rank_candidates(
    candidates: list[MarketCandidate],
    betclic_history: dict[str, float] | None = None,
    config: BettingConfig | None = None,
) -> list[MarketCandidate]:
    """Rank all market candidates across all fixtures.

    Ranking criteria (in order):
    1. Safety score (descending)
    2. Three-way alignment (aligned first)
    3. UNDER direction preference (UNDER before OVER at same safety)
    4. EV if odds available (descending)

    Betclic history hit rates are attached as advisory data (NEVER used for rejection).
    """

def quality_checks(candidate: MarketCandidate, db_conn) -> list[str]:
    """Run 5 quality checks on a candidate. Returns list of failed check names.

    Checks:
    1. data_completeness: L10 has ≥ 8 values
    2. positive_ev: EV > 0 (if odds available) OR min_odds < 3.50 (if no odds)
    3. no_48h_repeat: Same team+market not bet in last 48h
    4. min_safety: safety_score ≥ config.min_safety_score
    5. three_way_check: three_way_aligned is True
    """

def attach_betclic_history(candidates: list[MarketCandidate], db_conn) -> None:
    """Attach betclic_hit_rate to each candidate from historical bets (advisory only)."""
```

**Definition of Done**:
- [x] `rank_candidates()` returns candidates sorted by safety → alignment → direction → EV
- [x] Betclic history is ADVISORY ONLY — never filters/rejects candidates
- [x] `quality_checks()` returns failed check names (empty list = all passed)
- [x] 48h repeat check queries `bets` table for recent same-team+market bets
- [ ] Test: `test_rank_candidates_order`, `test_quality_checks_48h_repeat`

---

## Phase 5: Coupon Builder

**Goal**: Simplified coupon builder producing max 3-leg coupons with Polish shopping list output.

### Task 5.1: Coupon Builder (Max 3 Legs)

**Tag**: `[CREATE]`
**Files**: `src/bet/coupon/builder.py`

```python
# src/bet/coupon/builder.py

from bet.db.models import MarketCandidate, Coupon, Bet

def build_coupons(
    candidates: list[MarketCandidate],
    config: BettingConfig,
    max_coupons: int = 5,
) -> list[tuple[Coupon, list[Bet]]]:
    """Build coupons from ranked candidates.

    Rules:
    1. Max 3 legs per coupon (HARD CAP — 5+ legs = 0% win rate)
    2. Each coupon has legs from DIFFERENT events
    3. Max 2 legs from the same sport per coupon
    4. Prefer sport diversity across coupons
    5. Flat staking: config.max_stake_pln per coupon
    6. Total daily exposure ≤ config.daily_exposure_range[1]

    Algorithm:
    - Take top N candidates (by rank)
    - Greedily build coupons: pick best available candidate, add to current coupon
      if independence rules allow, else start new coupon
    - Stop when max_coupons reached or candidates exhausted

    Returns: list of (Coupon, [Bet, ...]) tuples
    """

def _are_independent(existing_bets: list[Bet], new_candidate: MarketCandidate) -> bool:
    """Check if adding candidate maintains coupon independence.
    - Different event (different fixture_id)
    - Max 2 legs from same sport
    """

def _generate_coupon_id(date: str, index: int) -> str:
    """Generate coupon ID. E.g., 'AKO-2026-05-03-001'"""
```

**Definition of Done**:
- [x] No coupon has more than 3 legs
- [x] No coupon has 2 legs from the same fixture
- [x] No coupon has more than 2 legs from the same sport
- [x] Flat staking is applied (config.max_stake_pln)
- [x] Total daily exposure does not exceed config upper bound
- [x] Coupon IDs follow `AKO-YYYY-MM-DD-NNN` pattern
- [ ] Test: `test_max_3_legs_enforced`, `test_no_same_fixture_in_coupon`, `test_sport_diversity`

---

### Task 5.2: Shopping List Output

**Tag**: `[CREATE]`
**Files**: `src/bet/coupon/shopping_list.py`

```python
# src/bet/coupon/shopping_list.py

def format_shopping_list(
    coupons: list[tuple[Coupon, list[Bet]]],
    config: BettingConfig,
) -> str:
    """Format coupons as a Polish-language shopping list for Betclic.

    Output format per coupon:
    ```
    ## 🎫 AKO-2026-05-03-001 | Kurs: 2.85 | Stawka: 2.00 PLN

    1. ⚽ Liverpool vs Arsenal — Rzuty rożne łącznie Powyżej 9.5
       Min kurs: 1.25 | Bezpieczeństwo: 0.80 | Trafialność: 80%
       → Betclic: Piłka nożna → Premier League → Liverpool-Arsenal → Statystyki → Rzuty rożne

    2. 🏐 Jastrzębski vs Resovia — Sety łącznie Powyżej 3.5
       Min kurs: 1.30 | Bezpieczeństwo: 0.77 | Trafialność: 77%
       → Betclic: Siatkówka → PlusLiga → Jastrzębski-Resovia → Sety

    3. 🎱 O'Sullivan vs Selby — Frejmy łącznie Powyżej 8.5
       Min kurs: 1.18 | Bezpieczeństwo: 0.85 | Trafialność: 85%
       → Betclic: Snooker → World Championship → O'Sullivan-Selby → Frejmy
    ```
    """

def format_summary(
    coupons: list[tuple[Coupon, list[Bet]]],
    total_candidates: int,
    config: BettingConfig,
) -> str:
    """Format summary statistics.

    Includes:
    - Number of coupons, total legs
    - Sport distribution
    - Average safety score
    - Total stake
    - Bankroll % at risk
    """

def write_shopping_list(
    coupons: list[tuple[Coupon, list[Bet]]],
    config: BettingConfig,
    output_path: Path,
) -> Path:
    """Write shopping list + summary to markdown file. Returns output path."""
```

**Definition of Done**:
- [x] Output is in Polish with correct market translations
- [x] Each bet has Betclic navigation hint (app path)
- [x] Min odds and safety scores are displayed per bet
- [x] Summary shows bankroll exposure percentage
- [x] Output is a single markdown file saved to `betting/coupons/`
- [ ] Test: `test_shopping_list_format` (verify Polish text, structure)

---

## Phase 6: Pipeline Orchestrator

**Goal**: 5-step pipeline with resume capability, progress reporting, and CLI entry point.

### Task 6.1: Pipeline Orchestrator

**Tag**: `[CREATE]`
**Files**: `src/bet/pipeline/orchestrator.py`

```python
# src/bet/pipeline/orchestrator.py

import asyncio
from datetime import date

PIPELINE_STEPS = ["discover", "enrich", "analyze", "build", "settle"]

async def run_pipeline(
    target_date: date,
    config: BettingConfig,
    db_path: str | None = None,
    resume: bool = False,
    skip_settle: bool = False,
) -> dict:
    """Run the 5-step pipeline.

    If resume=True, skip steps already completed for target_date (from pipeline_runs table).

    Steps:
    1. DISCOVER: discover_fixtures() + fetch_odds()
    2. ENRICH: enrich_fixtures() — incremental, DB-aware
    3. ANALYZE: compute_all_markets() + rank_candidates() + quality_checks()
    4. BUILD: build_coupons() + write_shopping_list()
    5. SETTLE: settle_day() (only if not skip_settle, settles PREVIOUS day)

    Returns: {"steps_completed": [...], "coupons_built": N, "total_fixtures": M}
    """

async def _run_step(step: str, target_date: date, config: BettingConfig, db_conn) -> dict:
    """Execute a single pipeline step. Records status in pipeline_runs table."""

def get_pipeline_status(target_date: date, db_conn) -> list[dict]:
    """Query pipeline_runs for the given date. Returns step statuses."""
```

**Definition of Done**:
- [x] Pipeline executes 5 steps in sequence (discover → enrich → analyze → build → settle)
- [x] Resume mode skips completed steps (queries `pipeline_runs` table)
- [x] Each step records start/complete/fail status in `pipeline_runs`
- [x] Failed step stores error message; pipeline can resume from failure point
- [x] Settlement runs for the previous day (not the target date)
- [ ] Test: `test_pipeline_resume_skips_completed`, `test_pipeline_records_failure`

---

### Task 6.2: Progress Reporting

**Tag**: `[CREATE]`
**Files**: `src/bet/pipeline/progress.py`

```python
# src/bet/pipeline/progress.py

import sys
from datetime import datetime

class PipelineProgress:
    """Progress reporter for pipeline steps. Prints to stderr."""

    def __init__(self, total_steps: int = 5): ...

    def start_step(self, step: str, description: str) -> None:
        """Print step start. E.g., '[1/5] DISCOVER — Scanning fixtures...'"""

    def update(self, message: str) -> None:
        """Print progress within a step. E.g., '  ⚽ Football: 45 fixtures found'"""

    def complete_step(self, step: str, stats: dict) -> None:
        """Print step completion with stats."""

    def error(self, step: str, error: str) -> None:
        """Print step failure."""

    def final_summary(self, results: dict) -> None:
        """Print pipeline completion summary."""
```

**Definition of Done**:
- [x] Progress prints to stderr (not stdout — stdout reserved for shopping list output)
- [x] Each step shows step number and description
- [x] Per-sport fixture counts are shown during DISCOVER
- [x] Final summary shows total runtime, fixtures, coupons built
- [x] No emoji in progress output (keep it machine-parseable); emoji only in shopping list

---

### Task 6.3: CLI Entry Point

**Tag**: `[CREATE]`
**Files**: `src/bet/cli.py`

```python
# src/bet/cli.py

import argparse
import asyncio
from datetime import date

def main():
    """CLI entry point.

    Commands:
        bet run [--date YYYY-MM-DD] [--resume]    — Run full pipeline
        bet settle [--date YYYY-MM-DD]             — Settle a specific day
        bet status [--date YYYY-MM-DD]             — Show pipeline status
        bet history                                — Show bet/coupon history summary
        bet health                                 — Show source health status
        bet migrate                                — Run data migration (one-time)
    """

def cmd_run(args): ...
def cmd_settle(args): ...
def cmd_status(args): ...
def cmd_history(args): ...
def cmd_health(args): ...
def cmd_migrate(args): ...
```

**Definition of Done**:
- [x] `bet run` runs the full 5-step pipeline
- [x] `bet run --resume` skips completed steps
- [x] `bet settle --date 2026-05-02` settles a specific day
- [x] `bet status` shows pipeline_runs for today (or --date)
- [x] `bet history` shows summary from bets/coupons tables
- [x] `bet health` shows source_health table
- [x] `bet migrate` runs the migration script from Task 1.6
- [x] Default date is today (Europe/Warsaw timezone, 06:00 boundary)
- [ ] Test: `test_cli_run_invokes_pipeline` (mock pipeline, verify correct date passed)

---

## Phase 7: Settlement Adaptation

**Goal**: DB-based settlement engine and Betclic learning analysis.

### Task 7.1: DB-Based Settlement

**Tag**: `[CREATE]`
**Files**: `src/bet/settlement/settler.py`
**Source**: Logic adapted from `scripts/settle_on_finish.py`

```python
# src/bet/settlement/settler.py

async def settle_day(target_date: date, db_conn) -> dict:
    """Settle all pending bets for a given day.

    1. Find pending bets from `bets` table where fixture kickoff matches target_date
    2. For each pending bet:
       a. Fetch result from APIs / DB (fixture.score_home, fixture.score_away)
       b. If fixture not finished: try The-Odds-API scores endpoint
       c. If still not finished: skip (will retry next run)
       d. Auto-settle standard markets: totals O/U, BTTS, 1X2, DC
       e. Mark manual markets: corners, cards, fouls (need Betclic app verification)
    3. Update coupon status based on leg outcomes
    4. Update bankroll

    Returns: {"settled": N, "still_pending": M, "pnl": X.XX}
    """

def settle_bet(bet: Bet, fixture: Fixture, match_stats: dict | None) -> str:
    """Determine bet outcome.
    Returns: "won" | "lost" | "void" | "push" | "pending" (if result unknown)
    """

def settle_totals(selection: str, line: float, actual_value: float) -> str:
    """Settle O/U market. 'OVER 9.5' with actual=10 → 'won'"""

def update_bankroll(db_conn, pnl: float, config: BettingConfig) -> float:
    """Update bankroll in config. Returns new bankroll."""
```

**Definition of Done**:
- [x] Settles totals (O/U), BTTS, 1X2, Double Chance automatically
- [x] Corner/card/foul markets are flagged as "manual" (need Betclic verification)
- [x] Coupon is "won" only if ALL legs won; "lost" if ANY leg lost
- [x] PnL is calculated correctly: won = stake × (total_odds - 1), lost = -stake
- [x] Bankroll is updated in config after settlement
- [x] Fixtures without final scores are skipped (retried next run)
- [ ] Test: `test_settle_totals_over_won`, `test_settle_coupon_one_leg_lost`

---

### Task 7.2: Betclic Learning Analysis

**Tag**: `[MODIFY]`
**Files**: `src/bet/settlement/learning.py`
**Source**: Adapted from `scripts/analyze_betclic_learning.py`

```python
# src/bet/settlement/learning.py

def analyze_history(db_conn) -> dict:
    """Analyze all historical bets from DB.

    Produces:
    1. Market-level hit rates (corners: 87%, frame_totals: 100%, etc.)
    2. Sport-level hit rates
    3. Direction bias (OVER vs UNDER)
    4. Coupon size analysis (2-leg vs 3-leg win rates)
    5. Coupon-killer analysis (which market type kills coupons most)
    6. ROI by sport
    7. Statistical vs outcome market comparison

    All data is ADVISORY ONLY — displayed to user, never used for auto-rejection.
    """

def get_market_hit_rates(db_conn) -> dict[str, float]:
    """Return hit rates per market category. Used by market_ranking for advisory display."""

MARKET_CATEGORIES: dict[str, str] = { ... }  # from analyze_betclic_learning.py
```

Key reuse:
- `MARKET_CATEGORIES` dict (Polish → English market mapping) from existing script
- `categorize_market()`, `is_statistical_market()`, `is_over_under()` functions
- All analysis logic, but reading from `bets` + `coupons` tables instead of JSON

**Definition of Done**:
- [x] `analyze_history()` produces all 7 analysis sections
- [x] Data reads from SQLite `bets` and `coupons` tables (not JSON file)
- [x] `MARKET_CATEGORIES` mapping is complete (all Betclic Polish market names)
- [x] Results are ADVISORY ONLY — function never modifies candidate rankings
- [x] `get_market_hit_rates()` returns dict that can be attached to `MarketCandidate.betclic_hit_rate`
- [ ] Test: `test_analyze_history_with_seeded_data`

---

## Phase 8: Testing, Configuration & Cleanup

**Goal**: Comprehensive test suite, cleanup of old code, and final integration.

### Task 8.1: Test Fixtures & conftest.py

**Tag**: `[CREATE]`
**Files**: `tests/conftest.py`

```python
# tests/conftest.py

import pytest
import sqlite3
from bet.db.schema import init_db
from bet.db.repositories import SportRepo

@pytest.fixture
def db():
    """In-memory SQLite database with schema initialized."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()

@pytest.fixture
def db_with_sports(db):
    """DB with 7 sports seeded."""
    SportRepo(db).seed_defaults()
    return db

@pytest.fixture
def db_with_sample_data(db_with_sports):
    """DB with sample fixtures, teams, stats for testing."""
    # Insert sample teams, fixtures, stats, bets
    ...
    return db_with_sports

@pytest.fixture
def sample_candidates():
    """List of MarketCandidate objects for coupon builder tests."""
    ...

@pytest.fixture
def config():
    """BettingConfig with test defaults."""
    return BettingConfig(
        bankroll_pln=50.0,
        daily_exposure_range=(5.0, 15.0),
        max_stake_pln=2.0,
        max_legs_per_coupon=3,
        min_coupons_per_day=3,
        preferred_odds_range=(1.3, 3.5),
        min_safety_score=0.60,
        timezone="Europe/Warsaw",
        sports=["football", "volleyball", "basketball", "hockey", "tennis", "snooker", "speedway"],
        db_path=":memory:",
    )
```

**Definition of Done**:
- [x] `db` fixture provides clean in-memory database per test
- [x] `db_with_sports` seeds all 7 sports
- [x] `db_with_sample_data` has realistic sample data for integration tests
- [x] `config` fixture provides test configuration
- [x] All fixtures are function-scoped (fresh per test)

---

### Task 8.2: Unit Tests

**Tag**: `[CREATE]`
**Files**: `tests/test_db.py`, `tests/test_safety_scores.py`, `tests/test_coupon_builder.py`, `tests/test_enrichment.py`, `tests/test_settlement.py`

Test coverage targets:

| Module | Test File | Key Tests |
|---|---|---|
| `db.schema` | `test_db.py` | Schema init, idempotency, FK enforcement |
| `db.repositories` | `test_db.py` | CRUD for all repos, team alias resolution, fixture upsert dedup |
| `stats.safety_scores` | `test_safety_scores.py` | Known-input/known-output, three-way alignment, edge cases |
| `coupon.builder` | `test_coupon_builder.py` | Max 3 legs, independence, sport diversity, stake limits |
| `stats.enrichment` | `test_enrichment.py` | TTL check, stale fetch, cached skip |
| `settlement.settler` | `test_settlement.py` | Totals settlement, coupon win/loss, bankroll update |
| `utils.odds` | `test_safety_scores.py` | EV calculation, Kelly, odds conversion |
| `pipeline.orchestrator` | `test_pipeline.py` | Resume, step recording, failure handling |

**Definition of Done**:
- [x] `pytest` passes with 0 failures
- [x] All repository methods have at least one test
- [x] Safety score computation has known-input/known-output tests matching existing `compute_safety_scores.py`
- [x] Coupon builder enforces max 3 legs in tests
- [x] Settlement tests cover won, lost, void, push outcomes
- [x] No network calls in tests (all API calls mocked)

---

### Task 8.3: Integration Test — Full Pipeline

**Tag**: `[CREATE]`
**Files**: `tests/test_pipeline.py`

End-to-end test with mocked external services:

```python
# tests/test_pipeline.py

@pytest.mark.asyncio
async def test_full_pipeline_with_mocked_apis(db, config, monkeypatch):
    """Run full pipeline against mocked API responses.

    Verifies:
    1. Fixtures are discovered and stored in DB
    2. Stats are enriched
    3. Safety scores are computed
    4. Coupons are built with ≤ 3 legs
    5. Shopping list is generated in Polish
    6. Pipeline state is recorded in pipeline_runs
    """
```

**Definition of Done**:
- [x] Full pipeline runs with mocked APIs (no real network calls)
- [x] DB contains fixtures, stats, coupons, bets after pipeline
- [x] Shopping list output file exists with Polish content
- [x] Pipeline_runs table has all 5 steps as "completed"
- [x] No coupon has more than 3 legs

---

### Task 8.4: Simplified Configuration Deployment

**Tag**: `[MODIFY]`
**Files**: `config/betting_config.json`

Replace the current 14-sport config with the simplified 7-sport version from Task 1.7. Remove all unused fields (`use_smart_allocation`, `coupon_count_rule`, `sports_key`, `sports_support`, `market_types` sub-dicts, etc.).

**Definition of Done**:
- [x] Config file has exactly the fields defined in `BettingConfig` dataclass
- [x] Only 7 sports listed
- [x] `max_legs_per_coupon: 3` is set
- [x] Existing `betting_config.json` is backed up before overwriting

---

### Task 8.5: Old Code Archival & README Update

**Tag**: `[MODIFY]`
**Files**: `README.md`, `.gitignore`

- Update README with new CLI usage instructions
- Add `betting/data/betting.db` to `.gitignore`
- Document migration steps for existing users
- Old `scripts/` directory is NOT deleted — marked as deprecated in README

**Definition of Done**:
- [x] README documents: installation, `bet run`, `bet settle`, `bet status`, `bet history`
- [x] README includes migration instructions (`bet migrate`)
- [x] `betting.db` is in `.gitignore`
- [x] README notes that `scripts/` is deprecated (kept for reference)

---

## Dependency Graph

```
Phase 1 (DB Foundation)
  ├─ Task 1.1: pyproject.toml
  ├─ Task 1.2: Schema SQL
  ├─ Task 1.3: Connection management
  ├─ Task 1.4: Row models
  ├─ Task 1.5: Repositories ← depends on 1.2, 1.3, 1.4
  ├─ Task 1.6: Migration script ← depends on 1.5
  └─ Task 1.7: Config ← independent

Phase 2 (Utilities) ← depends on Phase 1
  ├─ Task 2.1: Team names ← depends on 1.5
  ├─ Task 2.2: Odds utilities ← independent
  ├─ Task 2.3: Polish translations ← independent
  └─ Task 2.4: Market definitions ← independent

Phase 3 (Scanner) ← depends on Phase 1, 2
  ├─ Task 3.1: Playwright pool ← independent
  ├─ Task 3.2: Fixture discovery ← depends on 1.5, 2.1, 3.1
  ├─ Task 3.3: Odds fetcher ← depends on 1.5, 2.1
  ├─ Task 3.4: API client adaptation ← depends on 1.4
  └─ Task 3.5: Essential adapters ← depends on 1.4, 3.1

Phase 4 (Stats Engine) ← depends on Phase 3
  ├─ Task 4.1: Enrichment ← depends on 1.5, 3.4
  ├─ Task 4.2: Safety scores ← depends on 1.4, 2.4
  └─ Task 4.3: Market ranking ← depends on 4.2, 2.4

Phase 5 (Coupon Builder) ← depends on Phase 4
  ├─ Task 5.1: Builder ← depends on 4.3, 2.2
  └─ Task 5.2: Shopping list ← depends on 5.1, 2.3

Phase 6 (Pipeline) ← depends on Phase 3, 4, 5
  ├─ Task 6.1: Orchestrator ← depends on 3.2, 4.1, 4.3, 5.1, 5.2
  ├─ Task 6.2: Progress ← independent
  └─ Task 6.3: CLI ← depends on 6.1

Phase 7 (Settlement) ← depends on Phase 1
  ├─ Task 7.1: Settler ← depends on 1.5
  └─ Task 7.2: Learning ← depends on 1.5

Phase 8 (Testing & Cleanup) ← depends on ALL
  ├─ Task 8.1: Test fixtures ← depends on 1.2
  ├─ Task 8.2: Unit tests ← depends on all modules
  ├─ Task 8.3: Integration test ← depends on 6.1
  ├─ Task 8.4: Config deployment ← depends on 1.7
  └─ Task 8.5: README ← depends on 6.3
```

## Parallelization Opportunities

Tasks that can be worked on in parallel (by different engineers or in parallel sessions):

| Stream A | Stream B | Stream C |
|---|---|---|
| Phase 1 (1.1–1.5) | | |
| Task 1.6 (migration) | Task 1.7 (config) | |
| Task 2.1 (team names) | Task 2.2 (odds utils) | Task 2.3 + 2.4 (translations + markets) |
| Task 3.1 (Playwright pool) | Task 3.4 (API clients) | Task 3.5 (adapters) |
| Task 3.2 (discovery) | Task 3.3 (odds fetcher) | |
| Task 4.1 (enrichment) | Task 4.2 (safety scores) | Task 7.1 + 7.2 (settlement) |
| Task 4.3 (ranking) | | |
| Task 5.1 + 5.2 (coupon) | Task 6.2 (progress) | |
| Task 6.1 (orchestrator) | | |
| Task 6.3 (CLI) | | |
| Phase 8 (testing + cleanup) | | |

---

## Security Considerations

| Area | Requirement |
|---|---|
| SQL Injection | All queries use parameterized `?` placeholders — no string interpolation |
| API Keys | Loaded from env vars or `config/api_keys.json` (gitignored) — never hardcoded |
| File Paths | Validate api_name in RateLimiter to prevent path traversal (existing check preserved) |
| DB File | `betting.db` in `.gitignore` — no accidental commit of personal data |
| Scraping | Respect robots.txt, use polite rate limits, identify via User-Agent |
| Input Validation | Team names sanitized via `normalize_team_name()` before DB insertion |

## Quality Assurance

| Check | Implementation |
|---|---|
| Unit Tests | pytest with in-memory SQLite, mocked APIs |
| Integration Test | Full pipeline with mocked external services |
| Type Safety | Dataclass models enforce field types; `mypy` optional |
| Code Style | Existing project conventions (no linter enforced — follow existing style) |
| Safety Score Parity | Test that new `compute_safety_score()` matches old script for same inputs |
| Coupon Integrity | Test that max 3 legs, independence, sport diversity are enforced |
| Settlement Accuracy | Test all outcome types: won, lost, void, push |
| No Auto-Rejection | Test that Betclic history data never filters candidates |

---

## Files Reuse Summary

### Files to REUSE (copy with minimal changes)
| Source File | Destination | What to Keep |
|---|---|---|
| `scripts/api_clients/base_client.py` | `src/bet/api_clients/base_client.py` | Retry logic, rate limiting, key loading |
| `scripts/api_clients/rate_limiter.py` | `src/bet/api_clients/rate_limiter.py` | Daily counter, atomic writes, thread safety |
| `scripts/utils.py` | `src/bet/utils/team_names.py` | `normalize_team_name()` function |
| `scripts/coupon_builder.py` | `src/bet/coupon/translations.py` | `MARKET_PL`, `DIRECTION_PL`, `SPORT_EMOJI` dicts |
| `scripts/normalize_stats.py` | `src/bet/stats/market_ranking.py` | `SPORT_STAT_KEYS`, `*_MARKETS` definitions |
| `scripts/compute_safety_scores.py` | `src/bet/stats/safety_scores.py` | Core safety score algorithm |
| `scripts/analyze_betclic_learning.py` | `src/bet/settlement/learning.py` | `MARKET_CATEGORIES`, analysis functions |

### Files to DISCARD (not ported)
| File | Reason |
|---|---|
| `scripts/run_full_scan_and_prepare.sh` | Replaced by Python async orchestrator |
| `scripts/gate_checker.py` | 17-point gate → 5-point quality check inline |
| `scripts/deep_link_discovery.py` | Replaced by API-first fixture discovery |
| `scripts/generate_market_matrix.py` | Inlined into analysis step |
| `scripts/build_shortlist.py` | Replaced by SQL query on ranked candidates |
| `scripts/validate_coupons.py` | Simplified validation inline in coupon builder |
| `scripts/fetch_weather.py` | Removed from critical path |
| `scripts/scan_events.py` | Replaced by scanner/discovery.py |
| `scripts/deep_analysis_pool.py` | Replaced by stats/enrichment.py |
| `scripts/deep_stats_report.py` | Replaced by stats/market_ranking.py |
| `scripts/aggregate_and_select.py` | Replaced by SQL queries |
| `scripts/adapters/forebet_adapter.py` | Not essential — discarded |
| `scripts/adapters/oddsportal_adapter.py` | Not essential — discarded |
| `scripts/adapters/soccerstats_adapter.py` | Not essential — discarded |
| `scripts/adapters/soccerway_adapter.py` | Not essential — discarded |
| `scripts/adapters/sofascore_adapter.py` | Not essential — discarded |
| `scripts/adapters/tennisabstract_adapter.py` | Not essential — discarded |
| `scripts/adapters/tennisexplorer_adapter.py` | Not essential — discarded |
| `scripts/adapters/totalcorner_adapter.py` | Not essential — discarded |
| `scripts/adapters/betclic_adapter.py` | Betclic blocks scraping (403) |
| `scripts/adapters/raw_adapter.py` | Generic — not needed |

---

## Code Review Findings

**Reviewed**: 2026-05-03
**Reviewer**: GitHub Copilot (tsh-code-reviewer)
**Scope**: All files under `src/bet/`, `tests/`, `pyproject.toml`, `config/betting_config.json`
**Tests**: 311/311 passing (11.31s)
**Import check**: All imports OK
**Package**: `pip install -e .` + `python -m bet.cli --help` — working

### Review Summary

| Category | Status | Details |
|---|---|---|
| SQL Injection | ✅ PASS | 100% parameterized queries, zero f-string/format SQL |
| API Key Handling | ✅ PASS | Env vars → JSON file → None fallback, never hardcoded |
| Path Traversal | ✅ PASS | RateLimiter validates api_name with `^[a-zA-Z0-9-]+$` |
| 3-Leg Cap | ✅ PASS | Enforced in config (`min(..., 3)`), builder (`MAX_LEGS=3`), and tests |
| ADVISORY ONLY | ✅ PASS | Betclic history attached as data only, never auto-rejects |
| Safety Score | ✅ PASS | `min(L10, H2H)` or `L10 * 0.7` — correct, tested |
| EV / Kelly / PnL | ✅ PASS | Formulas match spec, tested with known values |
| Polish Output | ✅ PASS | Comprehensive translations, Betclic navigation hints |
| Pipeline Resume | ✅ PASS | Tracks completed steps in pipeline_runs, skips on resume |
| DB Schema | ✅ PASS | 11 tables, FKs, WAL mode, proper indexes |
| Async Safety | ⚠️ WARN | Potential concurrent DB access if enrichment code completed |
| Settlement Logic | ❌ ISSUE | Non-goals O/U markets settled incorrectly |
| Code Completeness | ⚠️ WARN | `_try_api_fetch` doesn't save fetched stats |

### Critical Findings

#### C1: Settlement logic bug for non-goals O/U markets

**File**: `src/bet/settlement/settler.py` line ~180
**Severity**: Critical

`settle_bet()` uses `fixture.score_home + fixture.score_away` as the actual value for ALL `*Total O/U` markets. This is only correct for goals/points markets where the fixture score represents the market value:

- ✅ **Football** "Goals Total O/U": score_home=2, score_away=1 → total=3. Correct.
- ✅ **Basketball** "Total Points O/U": score_home=110, score_away=105 → total=215. Correct.
- ❌ **Tennis** "Total Games O/U": score_home=2, score_away=1 (sets). Total games played could be 32, not 3.
- ❌ **Snooker** "Total Frames O/U": score_home=6, score_away=4 (frames won). Total frames = 10, but score_home + score_away = 10 only if no walkovers. Actually this might be correct if score represents frames won.
- ❌ **Tennis** "Total Aces O/U": Cannot be settled from score alone — needs stat data.

**Impact**: Tennis and snooker coupons could be settled incorrectly. Currently mitigated because stat-based markets (corners, fouls, cards, shots, aces) are in `MANUAL_MARKETS` and flagged for manual verification. However, "Total Games O/U" and "Total Frames O/U" are NOT in `MANUAL_MARKETS` but ARE in `AUTO_SETTLE_MARKETS`, so they would auto-settle incorrectly.

**Recommendation**: Add "Total Games O/U", "Total Frames O/U", "Total Aces O/U", "Total Double Faults O/U", "Break Points Total O/U", "Total Centuries O/U", "Total 50+ Breaks O/U", "Total Heat Wins O/U" to `MANUAL_MARKETS` set, or implement sport-specific settlement using `match_stats` data.

### Major Findings

#### M1: Incomplete `_try_api_fetch` in enrichment.py

**File**: `src/bet/stats/enrichment.py` lines ~140-185
**Severity**: Major

The function fetches stats from API clients but never saves them to the `match_stats` table. The loop at lines ~172-181 iterates through fixture stats but only reads values without writing. Comment says: "Note: we'd need fixture_id here for match_stats; for now, team_form is computed from existing data."

This means:
1. API calls consume quota (rate-limited to 100/day) without storing data
2. `compute_form()` can only compute from pre-existing `match_stats`, not freshly fetched data
3. The enrichment pipeline step won't actually enrich anything for new teams

**Recommendation**: Either complete the save logic (requires fixture resolution to get fixture_id) or remove the API call to avoid wasting quota.

#### M2: Concurrent DB access risk in enrichment

**File**: `src/bet/stats/enrichment.py`
**Severity**: Major (latent — only manifests if M1 is fixed)

`enrich_fixtures()` uses `asyncio.gather()` to run `_enrich_team()` coroutines in parallel. Each coroutine calls `_try_api_fetch()` via `run_in_executor()`, passing the shared `db_conn`. If M1 is fixed to save data, multiple executor threads would write to the same `sqlite3.Connection` simultaneously, which is not thread-safe.

**Recommendation**: When fixing M1, either serialize DB writes back to the main thread (return data from executor, write in coroutine) or use a separate connection per thread.

### Minor Findings

#### m1: Duplicated `_sport_id_to_name` helper

**Files**: `src/bet/pipeline/orchestrator.py` and `src/bet/stats/enrichment.py`
**Impact**: DRY violation, maintenance burden
**Fix**: Move to `SportRepo` as a method, or to a shared utility.

#### m2: Import inside nested loop

**File**: `src/bet/pipeline/orchestrator.py`, `_step_analyze()` function
**Impact**: `import statistics as stats_mod` appears inside a double-nested for loop. Python caches imports so there's no performance hit, but it's unconventional.
**Fix**: Move to file-level imports.

#### m3: Useless index on JSON text column

**File**: `src/bet/db/schema.sql` line 158
**Impact**: `idx_teams_aliases` indexes the raw JSON text of the `aliases` column. The actual alias lookup uses `json_each()` which doesn't benefit from this index.
**Fix**: Remove the index, or use a generated column + index for alias search.

#### m4: Missing composite index for `get_best_odds()`

**File**: `src/bet/db/schema.sql`
**Impact**: `OddsRepo.get_best_odds()` queries by `(fixture_id, market, selection)` but only `fixture_id` is indexed. At current data volumes this is negligible.
**Fix**: Add `CREATE INDEX idx_odds_best ON odds_history(fixture_id, market, selection)`.

#### m5: No config validation

**File**: `src/bet/config.py`
**Impact**: `BettingConfig.load()` doesn't validate that `bankroll_pln > 0`, `max_stake_pln > 0`, or `daily_exposure_range[0] < daily_exposure_range[1]`. Invalid config would cause silent math errors.
**Fix**: Add validation in `load()` or `__post_init__`.

#### m6: No CLI command tests

**Impact**: 6 CLI commands (`run`, `settle`, `status`, `history`, `health`, `migrate`) have no test coverage.
**Fix**: Add integration tests using `subprocess.run()` or by calling `cmd_*()` functions directly.

#### m7: No `settle_day()` integration test

**Impact**: The async `settle_day()` function has complex iteration logic (coupons → bets → fixtures → settlement → coupon status update) that's only tested at the unit level (`settle_bet`, `settle_totals`, manual coupon assembly in tests).
**Fix**: Add an async test with a pre-populated DB.

### Positive Observations

1. **Clean architecture** — Repository pattern, dataclass models, pure parsers, single-responsibility modules.
2. **Excellent security posture** — Zero SQL injection surface, API key isolation, path traversal protection.
3. **Business rules correctly enforced** — 3-leg cap at 3 levels, ADVISORY ONLY at 4 verification points, all formulas match spec.
4. **Comprehensive test data** — conftest.py fixtures provide realistic multi-sport test scenarios.
5. **Graceful degradation** — Odds fetch failure doesn't block pipeline, API unavailability falls back to scraping.
6. **Idempotent schema** — `IF NOT EXISTS` on all DDL, `ON CONFLICT` upserts prevent duplicates.
7. **Rate limiter** — Thread-safe with per-API locks, atomic writes, daily auto-reset, path traversal protection.
