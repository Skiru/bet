# DB-First Migration — Full Implementation Plan

**Date:** 2026-05-05  
**Author:** Architect  
**Status:** Draft  
**Scope:** Migrate ALL pipeline JSON reads to DB-first with JSON fallback across 31 read points, 14 scripts, and 8 agent/instruction files

---

## 1. Solution Architecture

### Problem

The betting pipeline passes data between steps via JSON files (`scan_summary.json`, `odds_api_snapshot.json`, `market_matrix_{date}.json`, `shortlist.json`, `s3_deep_stats.json`, `s7_gate_results.json`, etc.). This creates:

- Fragile file-based coupling between pipeline steps
- No transactional integrity between writes
- Difficulty querying historical data across runs
- Duplicate data (same fixture/odds stored in 3+ JSON files)

### Target Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          SQLite DB (betting.db)                        │
│                                                                        │
│  EXISTING TABLES              NEW TABLES                               │
│  ─────────────                ──────────                               │
│  sports                       analysis_results  ← S3 output           │
│  competitions                 gate_results      ← S7 output           │
│  teams                                                                 │
│  fixtures                                                              │
│  match_stats                                                           │
│  team_form                                                             │
│  odds_history                                                          │
│  coupons + bets                                                        │
│  pipeline_runs                                                         │
│  source_health                                                         │
│  league_profiles                                                       │
└──────────┬──────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│  db_data_loader.py (gateway)         │
│                                      │
│  EXISTING LOADERS        NEW LOADERS │
│  ────────────────        ─────────── │
│  load_fixtures_from_db   load_analysis_results_from_db  │
│  load_odds_from_db       save_analysis_results_to_db    │
│  load_team_form_from_db  load_gate_results_from_db      │
│  load_h2h_from_db        save_gate_results_to_db        │
│  load_pipeline_state     load_shortlist_from_db         │
│  load_scan_summary       load_betclic_history_from_db   │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│  Pipeline Scripts                    │
│  ────────────────                    │
│  1. Call db_data_loader (DB-first)   │
│  2. If DB empty → JSON fallback      │
│  3. On output → dual-write DB+JSON  │
└──────────────────────────────────────┘
```

### Data Flow After Migration

```
S1a  scan_events.py ─────→ DB(fixtures)              [ALREADY DONE via ingest]
S1b  fetch_odds_*.py ────→ DB(odds_history) + JSON    [Phase 2: dual-write]
S1c  generate_market_matrix.py ←── DB(fixtures+odds)  [Phase 2: read from DB]
S1d  build_shortlist.py ←── DB(fixtures+odds+form)    [Phase 2: read from DB]
S2   build_stats_cache.py ──→ DB(team_form) + JSON    [ALREADY dual-writes]
S3   deep_stats_report.py ←── DB(shortlist+form)      [Phase 2: read from DB]
     deep_stats_report.py ──→ DB(analysis_results)    [Phase 2: write to DB]
S7   gate_checker.py ←── DB(analysis_results)         [Phase 2: read from DB]
     gate_checker.py ──→ DB(gate_results)             [Phase 2: write to DB]
S8   coupon_builder.py ←── DB(gate_results)           [Phase 2: read from DB]
     coupon_builder.py ──→ DB(coupons+bets) + JSON    [ALREADY dual-writes]
```

### Design Principles

1. **DB-first, JSON fallback** — Every reader tries DB first. If empty/error, reads JSON. Backward-compatible.
2. **Dual-write on output** — Scripts write to BOTH DB and JSON. JSON = human-readable debug.
3. **Lazy imports** — All DB imports inside function bodies. No import errors if DB unavailable.
4. **No migration tool** — `CREATE TABLE IF NOT EXISTS` in schema.sql + run `init_database.py`.
5. **Transaction safety** — `with get_db() as conn:` for all DB operations. Auto-commit/rollback.

---

## 2. Implementation Plan

### Phase 1: Schema, Models, and Repositories (Foundation)

#### Task 1.1 — Add `analysis_results` table to schema

- **Type:** [MODIFY]
- **File:** `src/bet/db/schema.sql`
- **Change:** Append `CREATE TABLE IF NOT EXISTS analysis_results` DDL (see spec below)
- **SQL:**
```sql
CREATE TABLE IF NOT EXISTS analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    betting_date TEXT NOT NULL,
    has_data INTEGER NOT NULL DEFAULT 0,
    best_market_name TEXT,
    best_market_line REAL,
    best_market_direction TEXT,
    best_safety_score REAL,
    markets_evaluated INTEGER NOT NULL DEFAULT 0,
    ranking_json TEXT NOT NULL DEFAULT '[]',
    three_way_check_json TEXT,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    stats_summary_json TEXT,
    source TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(fixture_id, betting_date)
);

CREATE INDEX IF NOT EXISTS idx_analysis_results_date ON analysis_results(betting_date);
CREATE INDEX IF NOT EXISTS idx_analysis_results_fixture ON analysis_results(fixture_id);
```
- **Definition of Done:**
  - [x] DDL appended to schema.sql
  - [x] `python3 scripts/init_database.py` runs without error and creates the table
  - [x] `SELECT name FROM sqlite_master WHERE name='analysis_results'` returns 1 row

---

#### Task 1.2 — Add `gate_results` table to schema

- **Type:** [MODIFY]
- **File:** `src/bet/db/schema.sql`
- **Change:** Append `CREATE TABLE IF NOT EXISTS gate_results` DDL
- **SQL:**
```sql
CREATE TABLE IF NOT EXISTS gate_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    betting_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    gate_score INTEGER NOT NULL DEFAULT 0,
    gate_details_json TEXT NOT NULL DEFAULT '{}',
    best_market_name TEXT,
    best_market_line REAL,
    best_market_direction TEXT,
    best_safety_score REAL,
    ev REAL,
    risk_tier TEXT,
    rejection_reasons_json TEXT NOT NULL DEFAULT '[]',
    source TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(fixture_id, betting_date)
);

CREATE INDEX IF NOT EXISTS idx_gate_results_date ON gate_results(betting_date);
CREATE INDEX IF NOT EXISTS idx_gate_results_status ON gate_results(status);
```
- **Definition of Done:**
  - [x] DDL appended to schema.sql
  - [x] `python3 scripts/init_database.py` runs without error and creates the table
  - [x] Table shows in `sqlite_master`

---

#### Task 1.3 — Add `AnalysisResult` and `GateResult` dataclasses

- **Type:** [MODIFY]
- **File:** `src/bet/db/models.py`
- **Change:** Add two new dataclasses after existing models
- **Signatures:**
```python
@dataclass
class AnalysisResult:
    id: int | None
    fixture_id: int
    betting_date: str
    has_data: bool = False
    best_market_name: str = ""
    best_market_line: float | None = None
    best_market_direction: str = ""
    best_safety_score: float | None = None
    markets_evaluated: int = 0
    ranking_json: list = field(default_factory=list)
    three_way_check_json: dict | None = None
    warnings_json: list = field(default_factory=list)
    stats_summary_json: dict | None = None
    source: str = ""
    created_at: str = ""

@dataclass
class GateResult:
    id: int | None
    fixture_id: int
    betting_date: str
    status: str = "pending"
    gate_score: int = 0
    gate_details_json: dict = field(default_factory=dict)
    best_market_name: str = ""
    best_market_line: float | None = None
    best_market_direction: str = ""
    best_safety_score: float | None = None
    ev: float | None = None
    risk_tier: str = ""
    rejection_reasons_json: list = field(default_factory=list)
    source: str = ""
    created_at: str = ""
```
- **Definition of Done:**
  - [x] Both dataclasses added to `models.py`
  - [x] Importing `from bet.db.models import AnalysisResult, GateResult` succeeds
  - [x] No lint errors in models.py

---

#### Task 1.4 — Add `AnalysisResultRepo` class

- **Type:** [MODIFY]
- **File:** `src/bet/db/repositories.py`
- **Change:** Add new repo class after `LeagueProfileRepo`
- **Methods:**
```python
class AnalysisResultRepo:
    def __init__(self, conn: sqlite3.Connection): ...

    def upsert(self, result: AnalysisResult) -> int:
        """INSERT OR REPLACE analysis result. Returns row ID."""

    def get_by_date(self, betting_date: str) -> list[AnalysisResult]:
        """All analysis results for a betting date."""

    def get_by_fixture(self, fixture_id: int, betting_date: str) -> AnalysisResult | None:
        """Single result for fixture+date."""

    def get_approved_candidates(self, betting_date: str) -> list[dict]:
        """JOIN analysis_results + fixtures + teams for candidates with has_data=1.
        Returns dicts compatible with shortlist/pool format."""

    @staticmethod
    def _row_to_analysis_result(row: sqlite3.Row) -> AnalysisResult: ...
```
- **SQL patterns:**
  - `upsert`: Use `INSERT ... ON CONFLICT(fixture_id, betting_date) DO UPDATE SET ...`
  - `get_approved_candidates`: JOIN `analysis_results ar`, `fixtures f`, `teams ht`, `teams at`, `sports s`, optionally `competitions c`
- **Definition of Done:**
  - [x] `AnalysisResultRepo` class added to repositories.py
  - [x] Import `AnalysisResult` from models
  - [x] All methods use parameterized queries (`?` placeholders)
  - [x] JSON columns serialized/deserialized with `json.dumps()`/`json.loads()`
  - [x] Unit test covers upsert + get_by_date round-trip

---

#### Task 1.5 — Add `GateResultRepo` class

- **Type:** [MODIFY]
- **File:** `src/bet/db/repositories.py`
- **Change:** Add new repo class after `AnalysisResultRepo`
- **Methods:**
```python
class GateResultRepo:
    def __init__(self, conn: sqlite3.Connection): ...

    def upsert(self, result: GateResult) -> int:
        """INSERT OR REPLACE gate result. Returns row ID."""

    def get_by_date(self, betting_date: str) -> list[GateResult]:
        """All gate results for a betting date."""

    def get_approved(self, betting_date: str) -> list[dict]:
        """Gate results with status='approved', JOINed with fixtures+teams.
        Returns dicts compatible with coupon_builder input format."""

    def get_extended(self, betting_date: str) -> list[dict]:
        """Gate results with status='extended'."""

    def get_all_with_details(self, betting_date: str) -> list[dict]:
        """All gate results JOINed with fixture/team info."""

    @staticmethod
    def _row_to_gate_result(row: sqlite3.Row) -> GateResult: ...
```
- **SQL patterns:**
  - `get_approved`: JOIN `gate_results gr`, `fixtures f`, `teams ht`, `teams at`, `sports s` WHERE `gr.status = 'approved'`
  - Include `best_market_name`, `ev`, `risk_tier`, `safety_score` in output dicts
- **Definition of Done:**
  - [x] `GateResultRepo` class added to repositories.py
  - [x] Import `GateResult` from models
  - [x] All methods use parameterized queries
  - [x] Unit test covers upsert + get_approved round-trip

---

#### Task 1.6 — Run `init_database.py` to apply schema changes

- **Type:** [REUSE]
- **File:** `scripts/init_database.py`
- **Change:** None — existing script runs `schema.sql` which now has new tables
- **Definition of Done:**
  - [x] `python3 scripts/init_database.py` completes successfully
  - [x] Both `analysis_results` and `gate_results` tables exist in `betting.db`

---

### Phase 2: DB Data Loader + Pipeline Scripts

#### Task 2.1 — Add `save_analysis_results_to_db()` to db_data_loader

- **Type:** [MODIFY]
- **File:** `scripts/db_data_loader.py`
- **Signature:**
```python
def save_analysis_results_to_db(betting_date: str, analyses: list[dict]) -> int:
    """Write S3 analysis results to analysis_results table.

    Args:
        betting_date: YYYY-MM-DD
        analyses: list of dicts with keys: fixture_id, has_data, best_market,
                  ranking, three_way_check, warnings, stats_summary, source

    Returns: number of rows written
    """
```
- **Repos used:** `AnalysisResultRepo`
- **Table:** `analysis_results`
- **Logic:**
  1. `from bet.db.connection import get_db` (lazy import)
  2. `from bet.db.repositories import AnalysisResultRepo`
  3. `with get_db() as conn:` → construct `AnalysisResultRepo(conn)`
  4. For each analysis dict, create `AnalysisResult` model and call `repo.upsert()`
  5. Map `best_market` sub-dict → `best_market_name`, `best_market_line`, `best_market_direction`, `best_safety_score`
  6. Return count of rows written
- **Definition of Done:**
  - [x] Function added to db_data_loader.py
  - [x] Handles empty list gracefully (returns 0)
  - [x] On DB error, prints warning and returns 0 (does not raise)
  - [ ] Test round-trips: save then load returns same data

---

#### Task 2.2 — Add `load_analysis_results_from_db()` to db_data_loader

- **Type:** [MODIFY]
- **File:** `scripts/db_data_loader.py`
- **Signature:**
```python
def load_analysis_results_from_db(betting_date: str) -> list[dict]:
    """Load S3 analysis results from DB, fallback to s3_deep_stats_{date}.json.

    Returns list of dicts in the same format as deep_stats_report.py output:
    [{fixture_id, sport, home_team, away_team, competition, has_data,
      best_market: {name, line, direction, safety_score},
      ranking: [...], warnings: [...], ...}]
    """
```
- **Repos used:** `AnalysisResultRepo` (specifically `get_approved_candidates()`)
- **Table:** `analysis_results` JOIN `fixtures` + `teams` + `sports`
- **Fallback:** `DATA_DIR / f"s3_deep_stats_{date}.json"`
- **Definition of Done:**
  - [x] DB-first read with JSON fallback
  - [x] Output format matches existing `s3_deep_stats_{date}.json` structure
  - [x] Returns empty list (not None) when neither source has data

---

#### Task 2.3 — Add `save_gate_results_to_db()` to db_data_loader

- **Type:** [MODIFY]
- **File:** `scripts/db_data_loader.py`
- **Signature:**
```python
def save_gate_results_to_db(betting_date: str, results: list[dict]) -> int:
    """Write S7 gate results to gate_results table.

    Args:
        betting_date: YYYY-MM-DD
        results: list of dicts with keys: fixture_id, status, gate_score,
                 gate_details, best_market, ev, risk_tier, rejection_reasons, source

    Returns: number of rows written
    """
```
- **Repos used:** `GateResultRepo`
- **Table:** `gate_results`
- **Definition of Done:**
  - [x] Function added to db_data_loader.py
  - [x] Maps `best_market` sub-dict correctly
  - [x] Handles missing fixture_id gracefully (skips with warning)

---

#### Task 2.4 — Add `load_gate_results_from_db()` to db_data_loader

- **Type:** [MODIFY]
- **File:** `scripts/db_data_loader.py`
- **Signature:**
```python
def load_gate_results_from_db(betting_date: str, status: str | None = None) -> list[dict]:
    """Load S7 gate results from DB, fallback to s7_gate_results_{date}.json.

    Args:
        betting_date: YYYY-MM-DD
        status: Optional filter — 'approved', 'extended', 'rejected', or None for all

    Returns list of dicts compatible with coupon_builder input.
    """
```
- **Repos used:** `GateResultRepo` (`get_approved`, `get_all_with_details`)
- **Fallback:** `DATA_DIR / f"s7_gate_results_{date}.json"`
- **Definition of Done:**
  - [x] DB-first read with JSON fallback
  - [x] Status filter works (None = all results)
  - [x] Output format matches existing gate_checker.py JSON output

---

#### Task 2.5 — Add `load_shortlist_from_db()` to db_data_loader

- **Type:** [MODIFY]
- **File:** `scripts/db_data_loader.py`
- **Signature:**
```python
def load_shortlist_from_db(betting_date: str, top: int = 100) -> list[dict]:
    """Load ranked shortlist from DB (fixtures + odds + team_form), fallback to shortlist JSON.

    Queries fixtures for the date, JOINs with odds_history and team_form
    to produce the same format as build_shortlist.py output.

    Returns list of dicts: [{fixture_id, sport, home_team, away_team,
    competition, kickoff, has_odds, has_stats, score, ...}]
    """
```
- **Repos used:** `FixtureRepo`, `OddsRepo`, `StatsRepo`
- **Tables:** `fixtures` JOIN `teams`, `sports`, `competitions`, LEFT JOIN `odds_history`, LEFT JOIN `team_form`
- **Fallback:** `DATA_DIR / f"{date.replace('-','')}_s2_shortlist.json"`
- **Definition of Done:**
  - [ ] DB-first with JSON fallback
  - [ ] `top` parameter limits result count
  - [ ] Output format compatible with deep_stats_report.py input

> **Note:** `load_shortlist_from_db` is in a separate task scope (not Phase 2a).

---

#### Task 2.6 — Add `load_betclic_history_from_db()` to db_data_loader

- **Type:** [MODIFY]
- **File:** `scripts/db_data_loader.py`
- **Signature:**
```python
def load_betclic_history_from_db() -> list[dict]:
    """Load bet history from bets+coupons tables, fallback to betclic_bets_history.json.

    Returns list of dicts in the same format as betclic_bets_history.json:
    [{sport, event, market, selection, odds, stake, status, settled_date, ...}]
    """
```
- **Repos used:** `CouponRepo` (`get_pending_bets_with_details` pattern, extended for all statuses)
- **Tables:** `bets` JOIN `coupons` JOIN `fixtures` JOIN `teams` JOIN `sports`
- **Fallback:** `DATA_DIR / "betclic_bets_history.json"`
- **Definition of Done:**
  - [x] DB-first with JSON fallback
  - [x] Output format matches `betclic_bets_history.json` structure
  - [x] Includes all bet statuses (not just pending)

---

#### Task 2.7 — Modify `fetch_odds_api.py` for dual-write

- **Type:** [MODIFY]
- **File:** `scripts/fetch_odds_api.py`
- **JSON write points:** Lines 362, 541
- **Change:** After writing `odds_api_snapshot.json`, also write odds to `odds_history` table
- **Logic:**
  1. After `output_file.write_text(...)` (L362), add DB write block
  2. Lazy import `get_db`, `OddsRepo`, `FixtureRepo`, `SportRepo`, `TeamRepo`
  3. For each event in snapshot: resolve fixture_id via `FixtureRepo.get_by_teams_and_date()`
  4. If fixture found: write each bookmaker's odds via `OddsRepo.upsert()`
  5. If fixture NOT found: skip (fixture may not be in DB yet — scan runs first)
  6. Wrap in try/except — DB write failure must not break the script
- **Definition of Done:**
  - [ ] Odds from API snapshot are written to `odds_history` table
  - [ ] JSON file still written (dual-write)
  - [ ] DB write failures logged but do not stop script execution
  - [ ] No duplicate odds rows (upsert via unique index)

---

#### Task 2.8 — Modify `fetch_odds_multi.py` for dual-write

- **Type:** [MODIFY]
- **File:** `scripts/fetch_odds_multi.py`
- **JSON write points:** Lines 319, 379
- **Change:** Same pattern as Task 2.7 — after JSON write, also write to `odds_history`
- **Definition of Done:**
  - [ ] Multi-source odds written to `odds_history` table
  - [ ] JSON file still written
  - [ ] DB write failures do not break script

---

#### Task 2.9 — Modify `generate_market_matrix.py` to read from DB

- **Type:** [MODIFY]
- **File:** `scripts/generate_market_matrix.py`
- **Current JSON reads:**
  - L120: reads `odds_multi_snapshot_{date}.json`
  - L190: reads `scan_summary.json`
  - L208: reads `odds_api_snapshot.json`
  - L226: reads ESPN odds data
- **Change:**
  - The script already imports and uses `load_fixtures_from_db()` and `load_odds_from_db()`
  - Replace remaining direct JSON reads of `odds_multi_snapshot` with `load_odds_from_db(date)` (which already has JSON fallback)
  - For `scan_summary.json`: use existing `load_scan_summary_from_db()` (already has JSON fallback)
  - For ESPN data: keep as JSON-only (ESPN enrichment is auxiliary, not in DB schema)
- **Definition of Done:**
  - [x] Primary data (fixtures, odds) loaded via `db_data_loader` functions
  - [x] Supplementary data (ESPN, scan_summary) still read from JSON (acceptable)
  - [x] Market matrix output still written as JSON + MD (unchanged)
  - [x] Existing `--stats-first` flag still works

---

#### Task 2.10 — Modify `build_shortlist.py` to read from DB

- **Type:** [MODIFY]
- **File:** `scripts/build_shortlist.py`
- **Current JSON reads:**
  - L357: reads `market_matrix_{date}.json`
- **Change:**
  - Add DB-first path: try loading fixtures + odds + team_form via `load_shortlist_from_db(date)` before falling back to market_matrix JSON
  - If DB returns sufficient data, use it directly
  - If DB empty, fall back to existing `market_matrix_{date}.json` read
  - Keep writing shortlist JSON as output (dual-write: also save shortlist metadata to DB via `save_analysis_candidates_to_db()` — or simply let downstream read from DB fixtures)
- **Definition of Done:**
  - [ ] DB-first read attempted before JSON
  - [ ] JSON fallback preserved
  - [ ] Shortlist JSON output still written
  - [ ] Scoring logic unchanged

---

#### Task 2.11 — Modify `deep_stats_report.py` to read shortlist from DB and write analysis_results to DB

- **Type:** [MODIFY]
- **File:** `scripts/deep_stats_report.py`
- **Current JSON reads:**
  - L736: reads `deep_analysis_pool_{date}.json`
  - L759: reads shortlist JSON
  - `extract_team_stats()` already reads from DB (team_form) with JSON fallback ✓
- **Current JSON writes:**
  - Writes `s3_deep_stats_{date}.json`
- **Change (READ):**
  - In `generate_deep_stats()`, add DB-first path for shortlist loading:
    ```python
    from db_data_loader import load_shortlist_from_db
    candidates = load_shortlist_from_db(date, top=top)
    if not candidates:
        candidates = _load_candidates_from_shortlist(shortlist_path)
    ```
- **Change (WRITE):**
  - After writing `s3_deep_stats_{date}.json`, call `save_analysis_results_to_db(date, results)`
  - Map each analyzed candidate to the `analysis_results` table format
- **Definition of Done:**
  - [ ] Shortlist loading is DB-first with JSON fallback
  - [x] Analysis results dual-written to DB + JSON
  - [x] `extract_team_stats()` continues using existing DB-first path (unchanged)
  - [x] Output format unchanged for downstream consumers

---

#### Task 2.12 — Modify `gate_checker.py` to read from DB and write gate_results to DB

- **Type:** [MODIFY]
- **File:** `scripts/gate_checker.py`
- **Current JSON reads:**
  - L1015: reads S3 deep stats JSON (input to gate)
- **Current JSON writes:**
  - Writes `s7_gate_results_{date}.json` and `s7_gate_results_{date}.md`
- **Change (READ):**
  - In main entry point, try `load_analysis_results_from_db(date)` before JSON
  - If DB returns data, use it; else fall back to JSON file
- **Change (WRITE):**
  - After writing JSON + MD, call `save_gate_results_to_db(date, results)`
  - Map each gate result dict to `gate_results` table format
  - Include `fixture_id` resolution (from fixtures table via team names + date)
- **Definition of Done:**
  - [x] S3 input loaded DB-first with JSON fallback
  - [x] Gate results dual-written to DB + JSON + MD
  - [x] All 17 gate labels preserved in `gate_details_json`
  - [x] Status correctly set: 'approved', 'extended', 'rejected'

---

#### Task 2.13 — Modify `coupon_builder.py` to read gate_results from DB

- **Type:** [MODIFY]
- **File:** `scripts/coupon_builder.py`
- **Current JSON reads:**
  - L117: reads config JSON (keep as-is — config is not DB data)
  - L1489: reads `s7_gate_results_{date}.json`
- **Change:**
  - Replace gate_results JSON read with `load_gate_results_from_db(date, status='approved')`
  - Fall back to JSON if DB empty
  - Coupon output already dual-writes to DB + JSON (no change needed for writes)
- **Definition of Done:**
  - [x] Gate results loaded DB-first with JSON fallback
  - [x] Config loading unchanged (stays JSON)
  - [x] Coupon output dual-write unchanged
  - [x] `build_coupons()` function signature unchanged

---

#### Task 2.14 — Modify `pipeline_orchestrator.py` to read from DB

- **Type:** [MODIFY]
- **File:** `scripts/pipeline_orchestrator.py`
- **Current JSON reads (17 total):**
  - L273: config JSON (keep as-is)
  - L322: pipeline state JSON (already has `load_pipeline_state()` in db_data_loader)
  - L440: scan summary JSON
  - L651: odds_api_snapshot.json
  - L717: odds_api_io_snapshot.json
  - L759: espn_odds.json
  - L870: tipster data JSON
  - L899: shortlist JSON
  - L940, L983, L1024, L1092, L1337, L1361, L1419: S3 deep stats JSON
  - L1481: gate results JSON
- **Change — prioritized reads to replace:**
  1. **Pipeline state (L322):** Replace with `load_pipeline_state(date)` — already exists
  2. **Odds snapshot (L651, L717):** Replace with `load_odds_from_db(date)` — already exists
  3. **Shortlist (L899):** Replace with `load_shortlist_from_db(date)`
  4. **S3 deep stats (L940+):** Replace with `load_analysis_results_from_db(date)`
  5. **Gate results (L1481):** Replace with `load_gate_results_from_db(date)`
  6. **Config (L273):** Keep as JSON (not pipeline data)
  7. **Scan summary (L440):** Use `load_scan_summary_from_db()` — already exists
  8. **ESPN/tipster data (L759, L870):** Keep as JSON (auxiliary enrichment, not in DB schema)
- **Definition of Done:**
  - [x] 5+ JSON reads replaced with db_data_loader calls
  - [x] Config + ESP + tipster reads unchanged (appropriate for JSON)
  - [ ] Pipeline still runs end-to-end
  - [ ] `--resume` flag still works correctly

---

#### Task 2.15 — Modify `aggregate_and_select.py` to read from DB

- **Type:** [MODIFY]
- **File:** `scripts/aggregate_and_select.py`
- **Current JSON reads:**
  - L61: config JSON (keep)
  - L91: `odds_api_snapshot.json`
  - L136: `scan_summary.json`
- **Change:**
  - Replace L91 odds read with `load_odds_from_db(date)` where date is available
  - Replace L136 scan_summary read with `load_scan_summary_from_db()`
  - Add date parameter to main function if not already present
- **Definition of Done:**
  - [ ] Odds and scan_summary loaded DB-first with JSON fallback
  - [ ] Config stays JSON
  - [ ] Output (`picks_suggested.json`) still written as JSON

---

#### Task 2.16 — Modify `deep_analysis_pool.py` to read from DB

- **Type:** [MODIFY]
- **File:** `scripts/deep_analysis_pool.py`
- **Current JSON reads:**
  - L52: `odds_api_snapshot.json` (in `load_odds_snapshot()`)
  - L117: `scan_summary.json`
  - Already uses `load_fixtures_from_db()` ✓
  - Already uses `load_odds_from_db()` partially ✓
- **Change:**
  - In `load_odds_snapshot()`: already uses `load_odds_from_db(date)` when date is provided. Ensure all callers pass date.
  - Replace L117 direct JSON read of scan_summary with `load_scan_summary_from_db()`
- **Definition of Done:**
  - [ ] All primary data reads go through db_data_loader
  - [ ] JSON fallback still works
  - [ ] Pool output still written as JSON

---

### Phase 3: Supporting Scripts

#### Task 3.1 — Modify `settle_on_finish.py` to read odds from DB

- **Type:** [MODIFY]
- **File:** `scripts/settle_on_finish.py`
- **Current JSON reads:**
  - L87-91: `search_odds_api_snapshot()` reads `odds_api_scores.json` and `odds_api_snapshot.json`
- **Change:**
  - In `search_odds_api_snapshot()`, try DB first via `load_odds_from_db(date)` where date is the betting day
  - If DB returns data, search there for final scores
  - Fall back to existing JSON file reads
- **Definition of Done:**
  - [x] Odds/scores looked up in DB first
  - [x] JSON fallback preserved for backward compatibility
  - [x] Settlement logic unchanged
  - [x] `--betting-day` parameter still works

---

#### Task 3.2 — Modify `analyze_betclic_learning.py` to read from DB

- **Type:** [MODIFY]
- **File:** `scripts/analyze_betclic_learning.py`
- **Current JSON reads:**
  - L131: reads `betclic_bets_history.json`
- **Change:**
  - Try `load_betclic_history_from_db()` first
  - If DB returns data, use it for analysis
  - Fall back to `betclic_bets_history.json`
  - NOTE: `betclic_bets_history.json` remains the source of truth for imported Betclic bets. DB may have subset (only pipeline-placed bets). Merge if needed.
- **Definition of Done:**
  - [x] DB-first with JSON fallback
  - [x] All 10 analysis sections still produce output
  - [x] Output identical regardless of source (DB vs JSON)

---

#### Task 3.3 — Modify `historical_learning.py` to read from DB

- **Type:** [MODIFY]
- **File:** `scripts/historical_learning.py`
- **Current reads:**
  - CSV: `picks-ledger.csv` and `coupons-ledger.csv`
- **Change:**
  - Try DB first: query `bets` and `coupons` tables for settled results
  - Fall back to CSV reads
  - NOTE: CSV remains primary ledger format. DB may have subset. This is a low-priority migration — CSV is fine for now.
- **Priority:** LOW — CSV ledgers are human-editable and predate DB. Consider keeping CSV as primary.
- **Definition of Done:**
  - [x] DB read attempted first
  - [x] CSV fallback preserved
  - [x] Analysis output unchanged

---

#### Task 3.4 — Verify `probability_engine.py` DB reads (already implemented)

- **Type:** [REUSE]
- **File:** `scripts/probability_engine.py`
- **Current state:** `load_league_profiles()` (L431-462) already reads from `league_profiles` table with JSON fallback ✓
- **Change:** None — already DB-first
- **Definition of Done:**
  - [ ] Verify `load_league_profiles()` works correctly with current schema
  - [ ] No code changes needed

---

#### Task 3.5 — Modify `fetch_api_stats.py` to read fixtures from DB

- **Type:** [MODIFY]
- **File:** `scripts/fetch_api_stats.py`
- **Current JSON reads:**
  - L409-413: reads `fixtures_{date}.json`
  - Already has `_HAS_DB` flag and imports DB modules ✓
- **Change:**
  - Replace fixtures JSON read with `load_fixtures_from_db(date)` call
  - Already has DB infrastructure (`_HAS_DB`, `get_db`, repos imported at top)
  - Just need to use `load_fixtures_from_db()` instead of direct JSON read
- **Definition of Done:**
  - [x] Fixtures loaded via `load_fixtures_from_db(date)` with JSON fallback
  - [x] Existing DB dual-write for stats cache unchanged
  - [x] `--fixtures` CLI argument still works (explicit JSON path override)

---

#### Task 3.6 — Modify `fetch_weather.py` to read fixtures from DB

- **Type:** [MODIFY]
- **File:** `scripts/fetch_weather.py`
- **Current JSON reads:**
  - L261-263: reads `fixtures_{date}.json`
- **Change:**
  - Add `load_fixtures_from_db(date)` call before JSON fallback
  - When `--fixtures` argument is provided, still use explicit path (override)
- **Definition of Done:**
  - [x] Fixtures loaded DB-first when using `--date` flag
  - [x] `--fixtures` flag still loads from explicit JSON path
  - [x] Weather output unchanged

---

### Phase 4: Agent and Instruction File Updates

#### Task 4.1 — Update agent files for DB-first workflow

- **Type:** [MODIFY]
- **Files:**
  - `.github/agents/bet-scanner.agent.md`
  - `.github/agents/bet-statistician.agent.md`
  - `.github/agents/bet-scout.agent.md`
  - `.github/agents/bet-orchestrator.agent.md`
  - `.github/agents/bet-settler.agent.md`
  - `.github/agents/bet-valuator.agent.md`
- **Change:** In each agent file:
  - Replace instructions that reference "read from JSON" with "read from DB (JSON fallback)"
  - Update data flow descriptions to mention DB tables
  - Add note about `db_data_loader.py` as the gateway module
  - Add new tables (`analysis_results`, `gate_results`) to schema references
- **Definition of Done:**
  - [x] All 6 agent files mention DB-first reads
  - [x] No agents instruct reading JSON files directly for pipeline data
  - [x] New tables referenced in relevant agents (bet-statistician, bet-orchestrator)

---

#### Task 4.2 — Update `analysis-methodology.instructions.md`

- **Type:** [MODIFY]
- **File:** `.github/instructions/analysis-methodology.instructions.md`
- **Change:**
  - Update step descriptions (S1–S8) to mention DB reads/writes
  - Add note that `db_data_loader.py` functions are the standard way to load data
  - Reference new tables for S3 (analysis_results) and S7 (gate_results)
- **Definition of Done:**
  - [x] Methodology steps reference DB tables where applicable
  - [x] JSON files described as "debug/fallback output"

---

#### Task 4.3 — Update `betting-artifacts.instructions.md`

- **Type:** [MODIFY]
- **File:** `.github/instructions/betting-artifacts.instructions.md`
- **Change:**
  - Add DB artifact descriptions (analysis_results table format, gate_results table format)
  - Note that JSON artifacts are still produced for human readability
  - Add `db_data_loader.py` function reference table
- **Definition of Done:**
  - [x] New DB artifacts documented
  - [x] Dual-write policy documented
  - [x] Function reference table for db_data_loader complete

---

### Phase 5: Testing

#### Task 5.1 — Unit tests for `AnalysisResultRepo`

- **Type:** [CREATE]
- **File:** `tests/test_db_analysis_results.py`
- **Tests:**
  1. `test_upsert_and_get_by_date` — round-trip write + read
  2. `test_upsert_conflict_updates` — second upsert for same fixture+date overwrites
  3. `test_get_by_fixture` — single result lookup
  4. `test_get_approved_candidates` — JOIN query returns fixture+team info
  5. `test_empty_date_returns_empty_list` — no results for unknown date
- **Fixtures:** Use in-memory SQLite DB with schema applied
- **Definition of Done:**
  - [ ] All 5 tests pass
  - [ ] Tests use `:memory:` DB (no file I/O)
  - [ ] JSON columns correctly serialized/deserialized

---

#### Task 5.2 — Unit tests for `GateResultRepo`

- **Type:** [CREATE]
- **File:** `tests/test_db_gate_results.py`
- **Tests:**
  1. `test_upsert_and_get_by_date` — round-trip
  2. `test_get_approved_filters_correctly` — only status='approved' returned
  3. `test_get_extended` — only status='extended' returned
  4. `test_get_all_with_details` — JOIN query includes team names
  5. `test_upsert_conflict_updates` — overwrite on same fixture+date
- **Definition of Done:**
  - [ ] All 5 tests pass
  - [ ] Tests use `:memory:` DB

---

#### Task 5.3 — Integration tests for db_data_loader new functions

- **Type:** [CREATE]
- **File:** `tests/test_db_data_loader_new.py`
- **Tests:**
  1. `test_save_and_load_analysis_results` — round-trip through db_data_loader
  2. `test_save_and_load_gate_results` — round-trip
  3. `test_load_analysis_results_json_fallback` — DB empty, reads from JSON
  4. `test_load_gate_results_json_fallback` — DB empty, reads from JSON
  5. `test_load_shortlist_from_db` — fixtures + odds + form combined
  6. `test_load_betclic_history_from_db` — bets + coupons joined
  7. `test_load_betclic_history_json_fallback` — DB empty, reads betclic_bets_history.json
- **Definition of Done:**
  - [ ] All 7 tests pass
  - [ ] JSON fallback tests use tmp_path for fixture files
  - [ ] DB tests use `:memory:` or tmp_path DB

---

#### Task 5.4 — Integration tests for dual-write scripts

- **Type:** [CREATE]
- **File:** `tests/test_dual_write_integration.py`
- **Tests:**
  1. `test_deep_stats_report_writes_to_db` — run `generate_deep_stats()` and verify `analysis_results` table populated
  2. `test_gate_checker_writes_to_db` — run `run_gate()` and verify `gate_results` table populated
  3. `test_coupon_builder_reads_from_db` — populate `gate_results` in DB, run `build_coupons()`, verify it reads from DB
- **Definition of Done:**
  - [ ] All 3 tests pass
  - [ ] Tests verify both DB and JSON outputs exist
  - [ ] Tests use isolated DB (`:memory:` or tmp_path)

---

## 3. Security Considerations

1. **SQL Injection Prevention:** All queries use `?` parameterized placeholders (never string interpolation). Enforced by existing `repositories.py` pattern. Code review must verify no `f"..."` SQL strings.
2. **JSON Deserialization:** Use `json.loads()` only on data read from DB/files. No `eval()` or `pickle`. Already enforced.
3. **File Path Traversal:** All JSON fallback paths use `Path` with hardcoded base directories (`DATA_DIR`, `CACHE_DIR`). No user-controlled path components.
4. **DB File Permissions:** `betting.db` is in `betting/data/` which should be `.gitignore`d (already is).

---

## 4. Quality Assurance

1. **Automated Tests:** Phases 5.1–5.4 cover all new repos, db_data_loader functions, and dual-write integration.
2. **Backward Compatibility:** Every DB-first function has JSON fallback. Deleting `betting.db` should not break the pipeline (graceful degradation).
3. **Idempotency:** Schema uses `CREATE TABLE IF NOT EXISTS`. Repos use `INSERT OR REPLACE` / `ON CONFLICT DO UPDATE`. Safe to re-run.
4. **Test Coverage Targets:**
   - `AnalysisResultRepo`: 5 tests covering CRUD + JOINs
   - `GateResultRepo`: 5 tests covering CRUD + status filters
   - `db_data_loader` new functions: 7 tests covering round-trips + fallbacks
   - Dual-write integration: 3 tests covering end-to-end
   - **Total: 20 new tests**
5. **CI Verification:** All tests must pass with `PYTHONPATH=src:scripts python3 -m pytest tests/ -v`

---

## 5. Dependency Summary

| Phase | Depends On | Can Parallelize With |
|-------|-----------|---------------------|
| 1.1–1.2 (Schema) | — | Each other |
| 1.3 (Models) | — | 1.1–1.2 |
| 1.4–1.5 (Repos) | 1.3 | Each other |
| 1.6 (Init DB) | 1.1, 1.2 | — |
| 2.1–2.6 (Loaders) | 1.4, 1.5 | Each other |
| 2.7–2.8 (Odds write) | 1.6 | Each other |
| 2.9–2.16 (Script reads) | 2.1–2.6 | Each other |
| 3.1–3.6 (Supporting) | 2.1–2.6 | Each other |
| 4.1–4.3 (Docs) | 2.9–2.16 | Each other |
| 5.1–5.4 (Tests) | Phase 1 + 2 | Each other |

---

## 6. File Change Summary

| File | Type | Phase | Changes |
|------|------|-------|---------|
| `src/bet/db/schema.sql` | MODIFY | 1 | +2 tables, +4 indexes |
| `src/bet/db/models.py` | MODIFY | 1 | +2 dataclasses |
| `src/bet/db/repositories.py` | MODIFY | 1 | +2 repo classes (~120 lines each) |
| `scripts/db_data_loader.py` | MODIFY | 2 | +6 new functions (~200 lines) |
| `scripts/fetch_odds_api.py` | MODIFY | 2 | +DB dual-write block (~30 lines) |
| `scripts/fetch_odds_multi.py` | MODIFY | 2 | +DB dual-write block (~30 lines) |
| `scripts/generate_market_matrix.py` | MODIFY | 2 | Replace ~3 JSON reads with DB calls |
| `scripts/build_shortlist.py` | MODIFY | 2 | +DB-first read path (~15 lines) |
| `scripts/deep_stats_report.py` | MODIFY | 2 | +DB read for shortlist, +DB write for results |
| `scripts/gate_checker.py` | MODIFY | 2 | +DB read for S3, +DB write for gate results |
| `scripts/coupon_builder.py` | MODIFY | 2 | +DB read for gate results |
| `scripts/pipeline_orchestrator.py` | MODIFY | 2 | Replace ~5 JSON reads with DB calls |
| `scripts/aggregate_and_select.py` | MODIFY | 2 | Replace ~2 JSON reads with DB calls |
| `scripts/deep_analysis_pool.py` | MODIFY | 2 | Replace ~2 JSON reads with DB calls |
| `scripts/settle_on_finish.py` | MODIFY | 3 | +DB-first odds lookup |
| `scripts/analyze_betclic_learning.py` | MODIFY | 3 | +DB-first history read |
| `scripts/historical_learning.py` | MODIFY | 3 | +DB-first with CSV fallback |
| `scripts/fetch_api_stats.py` | MODIFY | 3 | Replace fixtures JSON read |
| `scripts/fetch_weather.py` | MODIFY | 3 | +DB-first fixtures read |
| `scripts/probability_engine.py` | REUSE | 3 | Already DB-first ✓ |
| `.github/agents/bet-scanner.agent.md` | MODIFY | 4 | Update data flow references |
| `.github/agents/bet-statistician.agent.md` | MODIFY | 4 | Update data flow references |
| `.github/agents/bet-scout.agent.md` | MODIFY | 4 | Update data flow references |
| `.github/agents/bet-orchestrator.agent.md` | MODIFY | 4 | Update data flow references |
| `.github/agents/bet-settler.agent.md` | MODIFY | 4 | Update data flow references |
| `.github/agents/bet-valuator.agent.md` | MODIFY | 4 | Update data flow references |
| `.github/instructions/analysis-methodology.instructions.md` | MODIFY | 4 | Update step descriptions |
| `.github/instructions/betting-artifacts.instructions.md` | MODIFY | 4 | Add DB artifact docs |
| `tests/test_db_analysis_results.py` | CREATE | 5 | 5 tests |
| `tests/test_db_gate_results.py` | CREATE | 5 | 5 tests |
| `tests/test_db_data_loader_new.py` | CREATE | 5 | 7 tests |
| `tests/test_dual_write_integration.py` | CREATE | 5 | 3 tests |

**Total: 32 files changed/created, 20 new tests**
