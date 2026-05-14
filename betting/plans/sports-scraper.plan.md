# Sports Data Scraping System — Implementation Plan

**Version:** 1.0  
**Date:** 2026-05-14  
**Status:** Draft  
**Author:** Architect Agent

---

## 1. Solution Architecture

### 1.1 High-Level Overview

A new `src/bet/scrapers/` module that scrapes player-level and team-level stats from free data sources across 5 sports. It writes to the **existing** `betting/data/betting.db` via SQLAlchemy ORM, coexisting with the raw `sqlite3` + `get_db()` pipeline.

```
┌─────────────────────────────────────────────────────┐
│                  Scraper Module                      │
│  src/bet/scrapers/                                   │
│                                                      │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │ BaseScraper│  │ engine.py │  │ models.py (ORM) │  │
│  └─────┬─────┘  └─────┬─────┘  └────────┬────────┘  │
│        │               │                 │           │
│  ┌─────▼──────────────▼─────────────────▼────────┐  │
│  │  football/ basketball/ tennis/ hockey/ volley/ │  │
│  │  (sport-specific scraper implementations)      │  │
│  └────────────────────┬──────────────────────────┘  │
│                       │                              │
└───────────────────────┼──────────────────────────────┘
                        │ SQLAlchemy Session
                        ▼
              ┌─────────────────┐
              │  betting.db     │  ← WAL mode (shared)
              │  (SQLite)       │
              └────────┬────────┘
                       │ raw sqlite3
                       ▼
              ┌─────────────────┐
              │  Existing        │
              │  Pipeline        │
              │  (get_db())     │
              └─────────────────┘
```

### 1.2 Integration Architecture: SQLAlchemy ↔ raw sqlite3

**Approach: Hybrid reflection + declaration.**

| Concern | Decision |
|---------|----------|
| Existing tables | Reflected at runtime via `Table("name", metadata, autoload_with=engine)` — zero drift risk |
| New tables | Declared via `DeclarativeBase` models — `metadata.create_all(checkfirst=True)` |
| Engine pooling | `StaticPool` (single-connection reuse, safe for single-threaded scrapers) |
| WAL coexistence | Both sides set `PRAGMA journal_mode=WAL` + `busy_timeout=5000` — concurrent reads, serialized writes |
| Schema source of truth | `schema.sql` remains authoritative; new tables also added there via migration `007` |

**Why this works:** SQLite WAL allows unlimited concurrent readers. The existing pipeline opens short-lived connections via `get_db()` (commit-then-close). The scraper opens a SQLAlchemy session, writes, commits, closes. `busy_timeout=5000ms` on both sides serializes any write contention.

**Why NOT `automap_base()`:** Automap reflects ALL tables including ones the scraper doesn't need (28+ tables). Selective `Table()` reflection maps only the ~8 tables the scraper reads/writes, keeping the model surface small.

---

## 2. Database Schema

### 2.1 Existing Tables Used (read/write via reflection)

These 10 tables are reflected at runtime — the scraper module defines no DDL for them:

| Table | Scraper Access | Purpose |
|-------|---------------|---------|
| `sports` | READ | Resolve sport_id for "football", etc. |
| `competitions` | READ/WRITE | Find or create league entries |
| `teams` | READ/WRITE | Find or create team entries |
| `fixtures` | READ/WRITE | Find or create match entries |
| `match_stats` | WRITE | Store team-level match stats |
| `athletes` | READ/WRITE | Find or create player entries |
| `player_gamelogs` | WRITE | Store per-game player stat lines |
| `player_splits` | WRITE | Store home/away/L5/L10 player splits |
| `league_profiles` | WRITE | Store league stat averages |
| `source_health` | WRITE | Track source reliability |

### 2.2 New Tables (declared via SQLAlchemy + added to migration 007)

#### `scraper_runs` — Run tracking

```sql
CREATE TABLE IF NOT EXISTS scraper_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scraper_name TEXT NOT NULL,        -- "fbref", "basketball-reference", "nhl-api", etc.
    sport TEXT NOT NULL,               -- "football", "basketball", etc.
    target TEXT NOT NULL,              -- what was scraped: league/season/date/team
    status TEXT NOT NULL DEFAULT 'running', -- running, completed, failed, partial
    records_scraped INTEGER DEFAULT 0,
    records_inserted INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_seconds REAL,
    UNIQUE(scraper_name, sport, target, started_at)
);

CREATE INDEX IF NOT EXISTS idx_scraper_runs_name ON scraper_runs(scraper_name);
CREATE INDEX IF NOT EXISTS idx_scraper_runs_sport ON scraper_runs(sport);
CREATE INDEX IF NOT EXISTS idx_scraper_runs_status ON scraper_runs(status);
```

#### `player_season_stats` — Aggregated per-season player statistics

```sql
CREATE TABLE IF NOT EXISTS player_season_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    athlete_id INTEGER NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
    competition_id INTEGER REFERENCES competitions(id) ON DELETE SET NULL,
    season TEXT NOT NULL,              -- "2025-2026", "2025", etc.
    games_played INTEGER DEFAULT 0,
    games_started INTEGER DEFAULT 0,
    minutes_played REAL DEFAULT 0,
    stats_json TEXT NOT NULL DEFAULT '{}',     -- full season totals (sport-specific)
    per_game_json TEXT NOT NULL DEFAULT '{}',  -- per-game averages
    advanced_json TEXT NOT NULL DEFAULT '{}',  -- advanced/derived metrics
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(athlete_id, competition_id, season, source)
);

CREATE INDEX IF NOT EXISTS idx_player_season_stats_athlete ON player_season_stats(athlete_id);
CREATE INDEX IF NOT EXISTS idx_player_season_stats_competition ON player_season_stats(competition_id);
CREATE INDEX IF NOT EXISTS idx_player_season_stats_season ON player_season_stats(season);
```

### 2.3 JSON Blob Conventions

Player stats vary by sport. JSON blobs use sport-specific keys:

**Football** (`stats_json` example):
```json
{"goals": 12, "assists": 8, "shots": 67, "shots_on_target": 31, "xG": 10.4, "xA": 7.1, "passes_completed": 1456, "tackles": 42, "interceptions": 18, "yellow_cards": 3}
```

**Basketball** (`stats_json` example):
```json
{"points": 512, "rebounds": 198, "assists": 156, "steals": 34, "blocks": 12, "turnovers": 67, "fg_made": 189, "fg_attempted": 421, "three_made": 67, "three_attempted": 198, "ft_made": 67, "ft_attempted": 78}
```

**Tennis** (`stats_json` example):
```json
{"matches_won": 34, "matches_lost": 8, "sets_won": 78, "sets_lost": 23, "aces": 312, "double_faults": 45, "first_serve_pct": 0.67, "break_points_saved_pct": 0.72}
```

**Hockey** (`stats_json` example):
```json
{"goals": 22, "assists": 34, "points": 56, "plus_minus": 12, "pim": 28, "shots": 156, "shooting_pct": 0.141, "powerplay_goals": 6, "shorthanded_goals": 1}
```

**Volleyball** (`stats_json` example):
```json
{"points": 245, "kills": 198, "attack_pct": 0.312, "aces": 34, "blocks": 67, "digs": 123, "assists": 12, "errors": 45}
```

---

## 3. Folder Structure

```
src/bet/scrapers/
├── __init__.py              # Public API: get_scraper(), scrape_sport()
├── base.py                  # BaseScraper ABC + common utilities
├── engine.py                # SQLAlchemy engine, session factory, DB setup
├── models.py                # ORM models (reflected existing + declared new)
├── constants.py             # UA pool, sport→source mappings, league configs
├── football/
│   ├── __init__.py
│   ├── fbref.py             # FBref via soccerdata lib
│   └── sofascore_fc.py      # SofaScore via ScraperFC lib (Phase 2)
├── basketball/
│   ├── __init__.py
│   ├── bball_ref.py         # Basketball-Reference HTML scraping
│   └── nba_api_scraper.py   # NBA API via nba_api lib
├── tennis/
│   ├── __init__.py
│   ├── sackmann.py          # Jeff Sackmann GitHub CSVs
│   └── sofascore_tennis.py  # SofaScore tennis API
├── hockey/
│   ├── __init__.py
│   ├── hockey_ref.py        # Hockey-Reference HTML scraping
│   └── nhl_api.py           # NHL public API
└── volleyball/
    ├── __init__.py
    ├── volleybox.py          # Volleybox HTML scraping
    └── sofascore_volley.py   # SofaScore volleyball API
```

**Total: 20 files** (7 infrastructure + 5 sport dirs × ~2-3 files each)

---

## 4. Class Hierarchy

### 4.1 BaseScraper

```python
# src/bet/scrapers/base.py

from abc import ABC, abstractmethod
from sqlalchemy.orm import Session, sessionmaker
import random, time, logging

class ScraperError(Exception):
    """Base exception for scraper errors."""
    pass

class ScraperRateLimitError(ScraperError):
    """Rate limited by source."""
    pass

class BaseScraper(ABC):
    """Abstract base for all sport data scrapers.
    
    Provides: rate limiting (sleep-based), UA rotation, 
    run logging, error handling, SQLAlchemy session management.
    """
    
    sport: str                          # e.g., "football"
    source_name: str                    # e.g., "fbref"
    _request_delay: tuple[float, float] = (1.0, 3.0)  # random sleep range
    
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory
        self.logger = logging.getLogger(f"scraper.{self.source_name}")
    
    # --- Abstract interface (each scraper implements what it can) ---
    
    @abstractmethod
    def scrape_team_season_stats(
        self, competition: str, season: str
    ) -> int:
        """Scrape team-level season stats. Returns records written."""
        ...
    
    @abstractmethod
    def scrape_player_season_stats(
        self, competition: str, season: str
    ) -> int:
        """Scrape player-level season stats. Returns records written."""
        ...
    
    def scrape_player_match_stats(
        self, competition: str, season: str
    ) -> int:
        """Scrape per-match player stats (gamelogs). Optional."""
        raise NotImplementedError(
            f"{self.source_name} does not support match-level player stats"
        )
    
    def scrape_fixtures(self, date: str) -> int:
        """Scrape fixtures for a date. Optional."""
        raise NotImplementedError(
            f"{self.source_name} does not support fixture scraping"
        )
    
    # --- Utilities ---
    
    def _rate_limit(self) -> None:
        delay = random.uniform(*self._request_delay)
        time.sleep(delay)
    
    def _get_headers(self) -> dict[str, str]:
        from .constants import USER_AGENTS
        return {"User-Agent": random.choice(USER_AGENTS)}
    
    def _get_session(self) -> Session:
        return self.session_factory()
    
    def _log_run(
        self, session: Session, target: str,
        status: str, records: int, error: str | None = None,
        started_at: str = "", duration: float = 0.0,
        inserted: int = 0, updated: int = 0,
    ) -> None:
        """Insert a record into scraper_runs."""
        from .models import ScraperRun
        run = ScraperRun(
            scraper_name=self.source_name,
            sport=self.sport,
            target=target,
            status=status,
            records_scraped=records,
            records_inserted=inserted,
            records_updated=updated,
            error_message=error,
            started_at=started_at,
            duration_seconds=duration,
        )
        session.add(run)
```

### 4.2 Concrete Scraper Example (Football FBref)

```python
# src/bet/scrapers/football/fbref.py

import soccerdata as sd
from ..base import BaseScraper

class FootballFBrefScraper(BaseScraper):
    sport = "football"
    source_name = "fbref"
    _request_delay = (3.0, 6.0)  # FBref requires respectful scraping
    
    LEAGUE_MAP = {
        "ENG-Premier League": ("England", "Premier League"),
        "ESP-La Liga": ("Spain", "La Liga"),
        "GER-Bundesliga": ("Germany", "Bundesliga"),
        "ITA-Serie A": ("Italy", "Serie A"),
        "FRA-Ligue 1": ("France", "Ligue 1"),
        # ... more leagues
    }
    
    def scrape_team_season_stats(self, competition: str, season: str) -> int:
        fbref = sd.FBref(leagues=competition, seasons=season)
        df = fbref.read_team_season_stats(stat_type="standard")
        # ... map DataFrame rows → match_stats / league_profiles
        return len(df)
    
    def scrape_player_season_stats(self, competition: str, season: str) -> int:
        fbref = sd.FBref(leagues=competition, seasons=season)
        df = fbref.read_player_season_stats(stat_type="standard")
        # ... map DataFrame rows → player_season_stats
        return len(df)
    
    def scrape_player_match_stats(self, competition: str, season: str) -> int:
        fbref = sd.FBref(leagues=competition, seasons=season)
        df = fbref.read_player_match_stats(stat_type="summary")
        # ... map DataFrame rows → player_gamelogs
        return len(df)
```

### 4.3 Full Scraper Class Map

| Class | Module | Sport | Source | Methods |
|-------|--------|-------|--------|---------|
| `FootballFBrefScraper` | `football/fbref.py` | football | FBref | team_season, player_season, player_match |
| `FootballSofascoreScraper` | `football/sofascore_fc.py` | football | SofaScore | fixtures, team_season, player_match |
| `BasketballBRefScraper` | `basketball/bball_ref.py` | basketball | Basketball-Ref | player_season, team_season |
| `BasketballNBAScraper` | `basketball/nba_api_scraper.py` | basketball | NBA API | player_match, player_season, fixtures |
| `TennisSackmannScraper` | `tennis/sackmann.py` | tennis | Sackmann CSVs | player_season, player_match |
| `TennisSofascoreScraper` | `tennis/sofascore_tennis.py` | tennis | SofaScore | fixtures, player_match |
| `HockeyRefScraper` | `hockey/hockey_ref.py` | hockey | Hockey-Ref | player_season, team_season |
| `HockeyNHLScraper` | `hockey/nhl_api.py` | hockey | NHL API | player_match, player_season, fixtures |
| `VolleyboxScraper` | `volleyball/volleybox.py` | volleyball | Volleybox | player_season, team_season |
| `VolleySofascoreScraper` | `volleyball/sofascore_volley.py` | volleyball | SofaScore | fixtures, player_match |

---

## 5. SQLAlchemy Engine & Session Setup

```python
# src/bet/scrapers/engine.py

from pathlib import Path
from sqlalchemy import create_engine, event, Table, MetaData
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from sqlalchemy.pool import StaticPool

DEFAULT_DB_PATH = (
    Path(__file__).parent.parent.parent.parent / "betting" / "data" / "betting.db"
)

class Base(DeclarativeBase):
    pass

_engine = None
_SessionFactory = None

def get_engine(db_path: Path | str = DEFAULT_DB_PATH):
    """Create or return cached SQLAlchemy engine with WAL + FK pragmas."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"timeout": 5},
            poolclass=StaticPool,
            echo=False,
        )
        
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
    
    return _engine

def get_session_factory(db_path: Path | str = DEFAULT_DB_PATH) -> sessionmaker:
    """Return a sessionmaker bound to the engine."""
    global _SessionFactory
    if _SessionFactory is None:
        engine = get_engine(db_path)
        _SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    return _SessionFactory

def setup_db(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """Create only NEW tables (scraper_runs, player_season_stats).
    Existing tables are untouched (checkfirst=True is the default).
    """
    from .models import ScraperRun, PlayerSeasonStat  # noqa: F811
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
```

---

## 6. ORM Models

```python
# src/bet/scrapers/models.py

from datetime import datetime, timezone
from sqlalchemy import (
    Integer, String, Text, Float, ForeignKey, Table, Column,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .engine import Base, get_engine

# ────────────────────────────────────────────────
# Existing tables — reflected at runtime (read-only mapping)
# ────────────────────────────────────────────────

def _reflect_existing_tables():
    """Reflect existing tables into Base.metadata.
    Call once after engine is available.
    """
    engine = get_engine()
    for table_name in [
        "sports", "competitions", "teams", "fixtures",
        "match_stats", "athletes", "player_gamelogs",
        "player_splits", "league_profiles", "source_health",
    ]:
        if table_name not in Base.metadata.tables:
            Table(table_name, Base.metadata, autoload_with=engine)


# ────────────────────────────────────────────────
# New tables — declared via ORM
# ────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

class ScraperRun(Base):
    __tablename__ = "scraper_runs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scraper_name: Mapped[str] = mapped_column(String, nullable=False)
    sport: Mapped[str] = mapped_column(String, nullable=False)
    target: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    records_scraped: Mapped[int] = mapped_column(Integer, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[str] = mapped_column(String, nullable=False, default=_now)
    finished_at: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    __table_args__ = (
        UniqueConstraint("scraper_name", "sport", "target", "started_at"),
        Index("idx_scraper_runs_name", "scraper_name"),
        Index("idx_scraper_runs_sport", "sport"),
        Index("idx_scraper_runs_status", "status"),
    )


class PlayerSeasonStat(Base):
    __tablename__ = "player_season_stats"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False
    )
    competition_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("competitions.id", ondelete="SET NULL"), nullable=True
    )
    season: Mapped[str] = mapped_column(String, nullable=False)
    games_played: Mapped[int] = mapped_column(Integer, default=0)
    games_started: Mapped[int] = mapped_column(Integer, default=0)
    minutes_played: Mapped[float] = mapped_column(Float, default=0.0)
    stats_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    per_game_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    advanced_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    source: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=_now)
    
    __table_args__ = (
        UniqueConstraint("athlete_id", "competition_id", "season", "source"),
        Index("idx_player_season_stats_athlete", "athlete_id"),
        Index("idx_player_season_stats_competition", "competition_id"),
        Index("idx_player_season_stats_season", "season"),
    )
```

---

## 7. Dependencies

Add to `pyproject.toml`:

```toml
[project]
dependencies = [
    # ... existing deps ...
    "sqlalchemy>=2.0.0",
]

[project.optional-dependencies]
scrapers = [
    "soccerdata>=1.8.0",          # FBref + SofaScore football data
    "nba_api>=1.4.0",              # NBA stats API
    "pandas>=2.0.0",               # Required by soccerdata, nba_api
    "ScraperFC>=3.0.0",            # SofaScore football (Phase 2)
    "sportsipy>=0.6.0",            # Basketball/Hockey Reference (Phase 3)
]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23.0"]
```

**Phase 1 install:** `pip install -e ".[scrapers]"` or just `pip install sqlalchemy soccerdata`

---

## 8. Data Flow: Scraper → DB → Pipeline

```
FBref HTML  ──→  soccerdata  ──→  DataFrame  ──→  FootballFBrefScraper
                                                          │
                                                          ▼
                                                   map rows to:
                                                   ├── athletes table (find_or_create)
                                                   ├── player_season_stats table (upsert)
                                                   ├── player_gamelogs table (upsert)
                                                   ├── match_stats table (upsert team-level)
                                                   └── scraper_runs table (log)
                                                          │
                                                          ▼
                                                   SQLAlchemy session.commit()
                                                          │
                                                          ▼
                                                   betting.db (WAL mode)
                                                          │
                                                          ▼
                                                   Existing pipeline reads via:
                                                   ├── get_db() + raw SQL
                                                   ├── FixtureRepo, TeamRepo, etc.
                                                   └── deep_stats_report.py, gate_checker.py
```

**Key mapping rules:**
1. Team names from FBref → resolved via `TeamRepo.resolve()` (alias matching) before insert
2. Player names → `athletes` table via `external_id` (FBref player URL slug) + `sport_id`
3. Competition names → `competitions` table via `(sport_id, name, season)` unique key
4. Stats are stored as JSON blobs in `stats_json` — keeps the schema sport-agnostic
5. Universal columns (`games_played`, `minutes_played`) are extracted into typed columns for fast queries

---

## 9. Security Considerations

| Concern | Mitigation |
|---------|------------|
| SQL injection | SQLAlchemy ORM uses parameterized queries exclusively |
| Credential exposure | No API keys in code; existing `config/api_keys.json` + env vars pattern |
| Source abuse / IP ban | `_rate_limit()` with configurable per-source delays; FBref gets 3-6s delay |
| Malicious scraped data | Team name validation (existing `TeamRepo._is_valid_team_name`); stat value range checks before insert |
| DB corruption | WAL mode + `busy_timeout` on both SQLAlchemy and raw sqlite3 sides; `StaticPool` prevents connection leaks |
| Dependency supply chain | Pin minimum versions in pyproject.toml; only well-known packages (sqlalchemy, soccerdata, nba_api) |

---

## 10. Test Plan

| Test Type | What | How |
|-----------|------|-----|
| Unit: BaseScraper | Rate limiting, UA rotation, run logging | Concrete mock scraper; assert sleep called, headers rotated |
| Unit: ORM models | Model creation, constraints, defaults | In-memory SQLite; create tables; insert/query/violate unique |
| Unit: engine.py | Engine creation, WAL pragma, session factory | Create engine with `:memory:`; verify PRAGMA values |
| Unit: FBref scraper | DataFrame → DB mapping | Mock `soccerdata.FBref` methods to return known DataFrames; verify DB rows |
| Integration: coexistence | SQLAlchemy + raw sqlite3 on same DB | Write via SQLAlchemy session → read via `get_db()` raw query → assert same data |
| Integration: migration | New tables created alongside existing | Run `init_db()` then `setup_db()`; verify all tables exist |
| Integration: upsert | Duplicate scraper runs update correctly | Insert same player_season_stats twice → assert UNIQUE constraint handled |

**Test files:**
```
tests/scrapers/
├── __init__.py
├── test_base_scraper.py
├── test_engine.py
├── test_models.py
├── test_coexistence.py
├── conftest.py             # shared fixtures: tmp DB, session factory, mock data
└── football/
    ├── __init__.py
    └── test_fbref.py
```

---

## 11. Phased Implementation

### Phase 1: Foundation + Football (FBref) — 11 tasks

Build the scraper infrastructure and first sport implementation. This phase proves the architecture works end-to-end: scrape → ORM → DB → readable by existing pipeline.

- [ ] **P1-T01** [CREATE] `src/bet/scrapers/__init__.py` — Package init with public API (`get_scraper`, `available_scrapers`)
  - **DoD:** Importing `from bet.scrapers import get_scraper` works; returns scraper instance by name

- [ ] **P1-T02** [CREATE] `src/bet/scrapers/constants.py` — UA pool (10+ agents), sport→league mappings, FBref league codes
  - **DoD:** `USER_AGENTS` list has ≥10 entries; `FBREF_LEAGUES` maps league codes to (country, name) tuples

- [ ] **P1-T03** [CREATE] `src/bet/scrapers/engine.py` — SQLAlchemy engine, session factory, `setup_db()`
  - **DoD:** `get_engine()` returns engine with WAL+FK pragmas verified; `get_session_factory()` returns working sessionmaker; `setup_db()` creates only new tables (existing untouched)

- [ ] **P1-T04** [CREATE] `src/bet/scrapers/models.py` — ORM models: `ScraperRun`, `PlayerSeasonStat`, + reflection helper
  - **DoD:** Both models can be instantiated and persisted to test DB; `_reflect_existing_tables()` successfully reflects the 10 existing tables; unique constraints enforced

- [ ] **P1-T05** [CREATE] `src/bet/scrapers/base.py` — `BaseScraper` ABC with rate limiting, UA rotation, run logging, error handling
  - **DoD:** A concrete mock subclass can be instantiated; `_rate_limit()` sleeps within configured range; `_log_run()` inserts into `scraper_runs`; `_get_headers()` returns rotating UA

- [ ] **P1-T06** [CREATE] `src/bet/scrapers/football/__init__.py` — Football package with scraper registry
  - **DoD:** `from bet.scrapers.football import FootballFBrefScraper` works

- [ ] **P1-T07** [CREATE] `src/bet/scrapers/football/fbref.py` — `FootballFBrefScraper` implementation
  - **DoD:** `scrape_player_season_stats("ENG-Premier League", "2025")` fetches data via soccerdata, maps to `player_season_stats` + `athletes` rows, logs run to `scraper_runs`; `scrape_team_season_stats` writes to `match_stats`/`league_profiles`; `scrape_player_match_stats` writes to `player_gamelogs`

- [ ] **P1-T08** [CREATE] `src/bet/db/migrations/007_scraper_tables.sql` — DDL for `scraper_runs` + `player_season_stats`
  - **DoD:** Migration SQL is valid; running it on existing DB creates both tables with indexes

- [ ] **P1-T09** [MODIFY] `src/bet/db/schema.sql` — Append new table DDL (for fresh DB creation)
  - **DoD:** `CREATE TABLE IF NOT EXISTS scraper_runs ...` and `player_season_stats ...` appended; `init_db()` on a fresh DB creates both tables

- [ ] **P1-T10** [MODIFY] `src/bet/db/schema.py` — Bump `SCHEMA_VERSION` to 7; add migration 007 call
  - **DoD:** `SCHEMA_VERSION = 7`; `migrate()` handles `from_version < 7` by running `007_scraper_tables.sql`

- [ ] **P1-T11** [MODIFY] `pyproject.toml` — Add `sqlalchemy>=2.0.0` to dependencies; add `[project.optional-dependencies].scrapers`
  - **DoD:** `pip install -e .` installs sqlalchemy; `pip install -e ".[scrapers]"` also installs soccerdata + pandas

### Phase 1 Tests — 4 tasks

- [ ] **P1-T12** [CREATE] `tests/scrapers/conftest.py` — Shared fixtures: temp DB with schema, session factory, sample data
  - **DoD:** `tmp_db` fixture creates in-memory DB with full schema + migration 007; `session_factory` fixture provides sessionmaker

- [ ] **P1-T13** [CREATE] `tests/scrapers/test_engine.py` — Engine creation, pragma verification, coexistence with `get_db()`
  - **DoD:** Tests verify WAL mode, FK pragma, busy_timeout; test writes via SQLAlchemy session then reads via raw `get_db()` — same data returned

- [ ] **P1-T14** [CREATE] `tests/scrapers/test_models.py` — Model CRUD, unique constraints, defaults
  - **DoD:** Insert ScraperRun and PlayerSeasonStat; verify defaults; violate UNIQUE → IntegrityError

- [ ] **P1-T15** [CREATE] `tests/scrapers/football/test_fbref.py` — FBref scraper with mocked soccerdata
  - **DoD:** Mock `sd.FBref` to return known DataFrames; run `scrape_player_season_stats`; verify correct rows in `player_season_stats` + `athletes` + `scraper_runs`

---

### Phase 2: Football (SofaScore) + Basketball — 6 tasks

- [ ] **P2-T01** [CREATE] `src/bet/scrapers/football/sofascore_fc.py` — SofaScore via ScraperFC
- [ ] **P2-T02** [CREATE] `src/bet/scrapers/basketball/__init__.py`
- [ ] **P2-T03** [CREATE] `src/bet/scrapers/basketball/nba_api_scraper.py` — NBA API via nba_api
- [ ] **P2-T04** [CREATE] `src/bet/scrapers/basketball/bball_ref.py` — Basketball-Reference HTML
- [ ] **P2-T05** [CREATE] `tests/scrapers/basketball/test_nba_api.py`
- [ ] **P2-T06** [CREATE] `tests/scrapers/football/test_sofascore_fc.py`

### Phase 3: Tennis + Hockey — 6 tasks

- [ ] **P3-T01** [CREATE] `src/bet/scrapers/tennis/__init__.py`
- [ ] **P3-T02** [CREATE] `src/bet/scrapers/tennis/sackmann.py` — Jeff Sackmann CSVs
- [ ] **P3-T03** [CREATE] `src/bet/scrapers/tennis/sofascore_tennis.py`
- [ ] **P3-T04** [CREATE] `src/bet/scrapers/hockey/__init__.py`
- [ ] **P3-T05** [CREATE] `src/bet/scrapers/hockey/nhl_api.py` — NHL public API
- [ ] **P3-T06** [CREATE] `src/bet/scrapers/hockey/hockey_ref.py`

### Phase 4: Volleyball + CLI — 4 tasks

- [ ] **P4-T01** [CREATE] `src/bet/scrapers/volleyball/__init__.py`
- [ ] **P4-T02** [CREATE] `src/bet/scrapers/volleyball/volleybox.py` — HTML scraping
- [ ] **P4-T03** [CREATE] `src/bet/scrapers/volleyball/sofascore_volley.py`
- [ ] **P4-T04** [CREATE] `scripts/run_scrapers.py` — CLI entry point: `python scripts/run_scrapers.py --sport football --source fbref --competition "ENG-Premier League" --season 2025`

---

## 12. Quality Assurance

| Check | Automated Via |
|-------|--------------|
| Type correctness | `mypy --strict src/bet/scrapers/` (add to CI) |
| Code style | `ruff check src/bet/scrapers/` (existing ruff config) |
| Unit tests pass | `pytest tests/scrapers/ -v` |
| Coexistence safe | `test_coexistence.py` — SQLAlchemy writes readable by raw sqlite3 |
| No existing test regressions | `pytest tests/ -v` — full suite still passes |
| UNIQUE constraints | `test_models.py` — duplicate inserts raise IntegrityError |
| Migration idempotent | `test_engine.py` — running `setup_db()` twice is safe |

---

## Appendix A: Data Source Details

### A1. Football

| Source | Library | Data Available | Rate Limit | Notes |
|--------|---------|---------------|------------|-------|
| FBref | `soccerdata` | Team season stats, player season stats, player match stats, lineups, shot events | ~4s between requests (soccerdata built-in) | Opta-derived data; 50+ leagues |
| SofaScore | `ScraperFC` | Live fixtures, match stats, player ratings, H2H | Moderate (3s delay) | JSON API; may need stealth for some endpoints |

### A2. Basketball

| Source | Library | Data Available | Rate Limit |
|--------|---------|---------------|------------|
| NBA API | `nba_api` | Player gamelogs, season stats, team stats, box scores | ~0.6s/request (built-in) |
| Basketball-Ref | `requests`+`bs4` | Historical player/team stats, advanced metrics | 3s delay (robots.txt) |

### A3. Tennis

| Source | Library | Data Available | Rate Limit |
|--------|---------|---------------|------------|
| Sackmann CSVs | `pandas` | ATP/WTA match results, player stats since 1968 | None (static files on GitHub) |
| SofaScore | `requests` | Live scores, H2H, player form | 3s delay |

### A4. Hockey

| Source | Library | Data Available | Rate Limit |
|--------|---------|---------------|------------|
| NHL API | `requests` | Schedules, box scores, player stats, standings | Low (public API, ~1s) |
| Hockey-Ref | `requests`+`bs4` | Historical stats, advanced metrics | 3s delay |

### A5. Volleyball

| Source | Library | Data Available | Rate Limit |
|--------|---------|---------------|------------|
| Volleybox | `requests`+`bs4` | Player stats, team rosters, match results | 3s delay |
| SofaScore | `requests` | Live scores, match stats | 3s delay |
