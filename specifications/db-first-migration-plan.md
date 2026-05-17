# DB-First Pipeline Migration — Implementation Plan

**Version:** 1.0  
**Date:** 2026-05-17  
**Status:** Ready for implementation  
**Scope:** Fix SQLite lock data loss, migrate pipeline reads to DB-first

---

## Executive Summary

The betting pipeline has two interconnected problems:

1. **Critical Bug:** `data_enrichment_agent.py` runs 4 worker threads that each open separate SQLite connections and call `save_team_form()` (SAVEPOINT: DELETE+INSERT). With `busy_timeout=5000ms`, lock contention causes `OperationalError` which is silently swallowed by a bare `except Exception` — resulting in **data loss**.

2. **Architecture Debt:** Several pipeline scripts read JSON files as primary data source with DB as fallback (or no DB at all), despite the DB containing the canonical data. This creates fragile inter-script coupling through filesystem intermediaries.

The fix is 4 phases, each independently deployable and testable.

---

## Architecture Decision: Why Not SQLAlchemy

The pipeline uses a custom `sqlite3` + dataclass repository pattern (`src/bet/db/repositories.py` with 25+ repo classes). The discovery module uses SQLAlchemy separately. Per project constraints, we keep the custom repo pattern — no ORM migration.

## Architecture Decision: Dual-Write Preserved

All scripts continue writing to **both** DB and JSON. JSON files are kept for:
- Human readability and debugging
- Backward compatibility with scripts not yet migrated
- Fallback when DB is unavailable or corrupt

The change is **read order only**: DB-first, JSON-fallback.

---

## Phase 0: SQLite Lock Fix (Critical — Deploy First)

**Goal:** Stop data loss from concurrent SQLite writes in enrichment.  
**Risk:** Low — changes are additive, backward-compatible.  
**Dependencies:** None.

### Task 0.1: Increase busy_timeout

`[MODIFY]` **`src/bet/db/connection.py`**

Change `PRAGMA busy_timeout` from `5000` to `30000` (30 seconds) in both `_configure_connection()` and `get_async_db()`.

**Rationale:** 5 seconds is insufficient when 4 threads compete for write locks on the same table. WAL mode allows concurrent readers but serializes writers. The SAVEPOINT pattern (DELETE+INSERT) holds locks longer than a simple upsert. 30s gives ample time for all queued writes to complete.

**Definition of Done:**
- [ ] `busy_timeout = 30000` in `_configure_connection()` (line 21)
- [ ] `busy_timeout = 30000` in `get_async_db()` (line 53)
- [ ] Existing tests pass (`pytest tests/test_db_repositories.py`)

---

### Task 0.2: Add retry-on-lock utility

`[MODIFY]` **`src/bet/db/connection.py`**

Add a `retry_on_lock` context manager / decorator for defense-in-depth against cross-process lock contention:

```python
import time
import sqlite3
from contextlib import contextmanager

@contextmanager
def retry_on_lock(conn: sqlite3.Connection, max_retries: int = 3, base_delay: float = 0.5):
    """Retry a block of DB operations on SQLITE_BUSY/locked errors.
    
    Usage:
        with get_db() as conn:
            with retry_on_lock(conn):
                repo.save_team_form(form)
                conn.commit()
    """
    for attempt in range(max_retries + 1):
        try:
            yield
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"DB locked (attempt {attempt+1}/{max_retries}), retrying in {delay:.1f}s")
                time.sleep(delay)
                continue
            raise
```

**Note:** This is a **generator-based context manager** that retries the entire block. An alternative (simpler) approach is a wrapper function:

```python
def retry_on_lock(fn, *args, max_retries=3, base_delay=0.5, **kwargs):
    """Call fn(*args, **kwargs) with retry on sqlite3.OperationalError (locked)."""
    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)
                continue
            raise
```

**Recommendation:** Use the function wrapper (second form) — simpler, no generator complexity, composable with existing `get_db()` context manager.

**Definition of Done:**
- [ ] `retry_on_lock()` function added to `connection.py`
- [ ] Function handles `sqlite3.OperationalError` with "locked" in message
- [ ] Exponential backoff: 0.5s → 1s → 2s (3 retries default)
- [ ] Re-raises after max retries exhausted
- [ ] Re-raises non-lock OperationalErrors immediately
- [ ] Unit test added (see Phase 3)

---

### Task 0.3: Serialize enrichment DB writes with threading.Lock

`[MODIFY]` **`scripts/data_enrichment_agent.py`**

Add a module-level `_db_write_lock = threading.Lock()` (pattern already established — see `_unified_client_lock` at line 236). Wrap DB write operations in both `_save_to_db()` and `_save_h2h_to_db()`.

**Current code** (`_save_to_db`, line 761):
```python
def _save_to_db(team_name: str, sport: str, stats: dict, source: str) -> None:
    try:
        with get_db() as conn:
            # ... multiple save_team_form() calls ...
            conn.commit()
    except Exception as exc:
        logger.error("DB save failed for %s: %s", team_name, exc)
```

**Target code:**
```python
_db_write_lock = threading.Lock()  # Serialize all DB writes across worker threads

def _save_to_db(team_name: str, sport: str, stats: dict, source: str) -> None:
    with _db_write_lock:
        try:
            with get_db() as conn:
                # ... multiple save_team_form() calls ...
                conn.commit()
        except sqlite3.OperationalError as exc:
            logger.critical("DB LOCK ERROR saving %s: %s — DATA LOST", team_name, exc)
            raise
        except Exception as exc:
            logger.error("DB save failed for %s: %s", team_name, exc)
```

Same pattern for `_save_h2h_to_db()` (line 1318):
```python
def _save_h2h_to_db(team_a, team_b, sport, stats) -> None:
    with _db_write_lock:
        try:
            with get_db() as conn:
                # ... save_team_form() calls ...
        except sqlite3.OperationalError as exc:
            logger.critical("DB LOCK ERROR saving H2H %s vs %s: %s", team_a, team_b, exc)
            raise
        except Exception as exc:
            logger.error("H2H DB save failed: %s", exc)
```

**Why `threading.Lock` and not `retry_on_lock`:** The lock is stronger — it prevents contention entirely within the process. `retry_on_lock` is for cross-process scenarios. Using both together (lock + retry inside) is acceptable but unnecessary here since the pipeline runs enrichment as a single process.

**Definition of Done:**
- [ ] `_db_write_lock = threading.Lock()` declared at module level (near `_unified_client_lock`)
- [ ] `_save_to_db()` body wrapped with `with _db_write_lock:`
- [ ] `_save_h2h_to_db()` body wrapped with `with _db_write_lock:`
- [ ] `sqlite3.OperationalError` caught separately in both functions, logged as CRITICAL, re-raised
- [ ] `import sqlite3` added to imports if not already present
- [ ] Existing tests pass, batch_enrich still works with --workers 4

---

## Phase 1: DB-First Read Order

**Goal:** Pipeline scripts read from DB as primary source, JSON as fallback.  
**Risk:** Low — all DB loaders already exist in `db_data_loader.py`.  
**Dependencies:** Phase 0 (lock fix ensures DB data is complete).

### Task 1.1: Flip coupon_builder.py to DB-first

`[MODIFY]` **`scripts/coupon_builder.py`** (lines 2025–2080)

**Current order** (lines 2027–2070):
1. Try explicit `--input` path → OK, keep as-is
2. Try JSON `{date}_s7_gate_results.json` → **primary** (line 2038)
3. If JSON missing → try DB via `load_gate_results_from_db` → **fallback** (line 2051)

**Target order:**
1. Try explicit `--input` path → keep as-is
2. Try DB via `load_gate_results_from_db` → **primary**
3. If DB empty → try JSON `{date}_s7_gate_results.json` → **fallback**

**Key concern:** The existing code comment says "Prefer JSON (has full best_market data incl. combined_avg, opponent_blocker)". These fields ARE stored in the DB in `gate_details_json` column, and `load_gate_results_from_db()` already reconstructs them into the `gate_details` key. The coupon builder accesses `best_market.name`, `best_market.safety_score`, `ev`, `risk_tier` — all present in DB loader output.

**Verification step:** After flipping, run coupon_builder with both DB and JSON present, compare output. If DB output is missing fields that JSON has, add those fields to `load_gate_results_from_db()` in db_data_loader.py.

**Definition of Done:**
- [ ] DB loading attempted before JSON loading (when no `--input` flag)
- [ ] JSON becomes explicit fallback (logged as such)
- [ ] `--verbose` output clearly indicates data source ("DB: loaded X" vs "JSON fallback: loaded X")
- [ ] Coupon output is identical whether loaded from DB or JSON (manual verification with one day's data)

---

### Task 1.2: Add DB-first to context_checks.py

`[MODIFY]` **`scripts/context_checks.py`** (lines 33–40)

**Current code:**
```python
s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
candidates = []
if s3_path.exists():
    s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
    candidates = s3_data.get("analyses", [])
```

**Target code:**
```python
# DB-first (R2)
candidates = []
try:
    from db_data_loader import load_analysis_results_from_db
    db_results = load_analysis_results_from_db(date)
    if db_results:
        candidates = db_results
except Exception:
    pass

# JSON fallback
if not candidates:
    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    if s3_path.exists():
        s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
        candidates = s3_data.get("analyses", [])
```

**Definition of Done:**
- [ ] DB loading attempted first via `load_analysis_results_from_db()`
- [ ] JSON file is fallback only
- [ ] Script behavior unchanged when both DB and JSON have same data
- [ ] Script still works when DB is empty (JSON fallback activates)

---

### Task 1.3: Add DB-first to upset_risk.py

`[MODIFY]` **`scripts/upset_risk.py`** (lines 26–43)

**Current code:**
```python
s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
if not s3_path.exists():
    return True, "S6: No S3 data — skipping upset risk scoring"
# ...
s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
analyses = s3_data.get("analyses", [])
```

**Target code:**
```python
# DB-first (R2)
analyses = []
try:
    from db_data_loader import load_analysis_results_from_db
    db_results = load_analysis_results_from_db(date)
    if db_results:
        analyses = db_results
except Exception:
    pass

# JSON fallback
if not analyses:
    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    if not s3_path.exists():
        return True, "S6: No S3 data — skipping upset risk scoring"
    s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
    analyses = s3_data.get("analyses", [])
```

**Definition of Done:**
- [ ] DB loading attempted first
- [ ] JSON fallback preserved
- [ ] Upset risk scoring logic unchanged (reads same fields: `ranking`, `safety_score`, `sport`)
- [ ] Works correctly when DB is empty

---

### Task 1.4: Add DB-first shortlist loading to data_enrichment_agent.py

`[MODIFY]` **`scripts/data_enrichment_agent.py`** (around line 1457)

The `--date` mode currently loads shortlist from JSON. Add DB-first via `load_fixtures_from_db()`.

**Current code** (line ~1457):
```python
shortlist_path = DATA_DIR / f"{date_str}_s2_shortlist.json"
if not shortlist_path.exists():
    shortlist_path = DATA_DIR / f"{date_str.replace('-', '')}_s2_shortlist.json"
```

**Target:** Try `load_fixtures_from_db(date_str)` first, construct team list from fixtures. Fall back to JSON shortlist.

**Definition of Done:**
- [ ] DB fixtures loaded first when using `--date` mode
- [ ] JSON shortlist is fallback
- [ ] Team extraction logic produces same format for batch_enrich input
- [ ] Works when DB has fixtures but no shortlist JSON exists

---

### Task 1.5 (Optional): Enrich gate_results DB loader with best_market subfields

`[MODIFY]` **`scripts/db_data_loader.py`** — `load_gate_results_from_db()` (line 620)

If Task 1.1 verification reveals missing fields, enrich the DB loader to extract `combined_avg`, `opponent_blocker`, and other nested fields from `gate_details_json` into the `best_market` dict.

**Current output shape:**
```python
"best_market": {
    "name": gr.best_market_name,
    "line": gr.best_market_line,
    "direction": gr.best_market_direction,
    "safety_score": gr.best_safety_score,
}
```

**Target (if needed):**
```python
best_market = {
    "name": gr.best_market_name,
    "line": gr.best_market_line,
    "direction": gr.best_market_direction,
    "safety_score": gr.best_safety_score,
}
# Merge extended fields from gate_details_json
if details := gr.gate_details_json:
    for key in ("combined_avg", "opponent_blocker", "hit_rate", "trend"):
        if key in details:
            best_market[key] = details[key]
```

**Definition of Done:**
- [ ] Coupon builder produces identical output from DB and JSON sources
- [ ] No KeyError exceptions in coupon builder when reading from DB

---

## Phase 2: Scripts Not Migrated (Documented Exclusions)

These scripts are **intentionally excluded** from DB-first migration:

| Script | Reason |
|--------|--------|
| `build_shortlist.py` | Reads `market_matrix_{date}.json` — a computed intermediate format with scoring data. Would require a new DB table (`market_matrix`) to migrate. Not worth the schema change for a file that's only read by one script. |
| `compute_safety_scores.py` | Standalone CLI tool. Takes explicit `--input` file path. Not in pipeline data flow chain. |
| `discover_events.py` | Entry point — writes TO DB/JSON, doesn't read pipeline intermediaries. Already DB-aware. |
| `tipster_aggregator.py` | Reads shortlist JSON for matching. Already writes to DB (R2). Shortlist matching is name-based fuzzy matching that works better with the denormalized JSON format. |
| `tipster_xref.py` | Reads tipster JSON + shortlist JSON. The cross-referencing logic is tightly coupled to the JSON structure with tipster-specific fields. Low ROI to migrate. |

---

## Phase 3: Tests

**Goal:** Verify lock fix and DB-first reads work correctly.  
**Dependencies:** Phases 0–1.

### Task 3.1: Test retry_on_lock utility

`[CREATE]` **`tests/test_db_connection.py`**

```python
def test_retry_on_lock_succeeds_after_retries():
    """retry_on_lock retries on OperationalError('database is locked')."""
    
def test_retry_on_lock_raises_after_max_retries():
    """retry_on_lock re-raises after exhausting retries."""

def test_retry_on_lock_no_retry_on_other_errors():
    """retry_on_lock does not retry on non-lock OperationalErrors."""
```

**Definition of Done:**
- [ ] 3 test cases covering: success-after-retry, exhaustion, non-lock errors
- [ ] Tests use mocking (no real DB contention needed)
- [ ] All pass with `pytest tests/test_db_connection.py`

---

### Task 3.2: Test enrichment DB write serialization

`[MODIFY]` **`tests/test_enrichment.py`** (or create `tests/test_enrichment_thread_safety.py`)

Test that `_save_to_db` with `_db_write_lock` correctly serializes concurrent writes:

```python
def test_save_to_db_concurrent_no_data_loss():
    """Multiple threads calling _save_to_db don't lose data."""
    # Setup: in-memory DB with schema
    # Run: 4 threads each saving different teams
    # Assert: all teams present in DB after completion

def test_save_to_db_lock_error_is_raised():
    """sqlite3.OperationalError from save_to_db is re-raised, not swallowed."""
```

**Definition of Done:**
- [ ] Concurrent write test with ≥4 threads, all data preserved
- [ ] OperationalError propagation test (mock to force lock error)
- [ ] Tests pass with `pytest tests/test_enrichment_thread_safety.py`

---

### Task 3.3: Test coupon_builder DB-first loading

`[MODIFY]` **`tests/test_pipeline_integration.py`** (or new file)

```python
def test_coupon_builder_loads_from_db_when_json_absent():
    """coupon_builder falls through to DB when JSON file doesn't exist."""

def test_coupon_builder_prefers_db_over_json():
    """coupon_builder reads DB first even when JSON exists."""
```

**Definition of Done:**
- [ ] Verify DB is attempted before JSON
- [ ] Verify fallback works when DB is empty
- [ ] Tests pass

---

## Implementation Order & Dependencies

```
Phase 0 (Critical Fix):
  Task 0.1 (busy_timeout)     ──→ no deps
  Task 0.2 (retry_on_lock)    ──→ no deps  
  Task 0.3 (threading.Lock)   ──→ no deps (but deploy with 0.1)

Phase 1 (DB-First Reads):
  Task 1.1 (coupon_builder)   ──→ depends on Phase 0 (ensures DB data is complete)
  Task 1.2 (context_checks)   ──→ depends on Phase 0
  Task 1.3 (upset_risk)       ──→ depends on Phase 0
  Task 1.4 (enrichment)       ──→ depends on Phase 0
  Task 1.5 (db_data_loader)   ──→ only if Task 1.1 verification fails

Phase 3 (Tests):
  Task 3.1 (retry_on_lock)    ──→ depends on Task 0.2
  Task 3.2 (thread safety)    ──→ depends on Task 0.3
  Task 3.3 (coupon DB-first)  ──→ depends on Task 1.1
```

**Recommended deployment order:**
1. Ship Phase 0 immediately (stops data loss)
2. Ship Phase 1 tasks independently (each is self-contained)
3. Ship Phase 3 alongside or after the task they test

---

## Security Considerations

1. **SQL Injection:** All existing repository code uses parameterized queries (`?` placeholders). No changes to query construction are proposed. Verified in `repositories.py` — no string interpolation in SQL.

2. **Race Conditions:** The `_db_write_lock` serializes writes within a single process. Cross-process writes (rare — pipeline steps are sequential) are handled by WAL mode + increased busy_timeout + retry_on_lock.

3. **Data Integrity:** The SAVEPOINT pattern in `save_team_form()` ensures atomic DELETE+INSERT. The lock prevents concurrent SAVEPOINTs from interleaving.

4. **Error Handling:** Silent exception swallowing is replaced with discriminated catching — lock errors are CRITICAL (re-raised), other errors remain logged. No data loss from silent failures.

---

## Quality Assurance

### Automated Test Strategy

| Change | Test | How to verify |
|--------|------|---------------|
| busy_timeout increase | Existing `test_db_repositories.py` | Passes — no behavioral change |
| retry_on_lock | New `test_db_connection.py` | Mock OperationalError, verify retry count |
| threading.Lock | New `test_enrichment_thread_safety.py` | 4 threads write, assert all data present |
| DB-first reads | Modified integration tests | DB populated → script reads from DB, not JSON |
| Exception discrimination | New test | Force lock error, verify it propagates (not swallowed) |

### Manual Verification (One-Time)

After deploying Phase 1, run one full pipeline day and compare:
- `coupon_builder.py` output with JSON vs DB source — should be identical
- Check logs for "DB:" vs "JSON fallback:" messages to confirm read order

### Regression Safety

- All changes are **additive** — no existing behavior is removed
- JSON files continue to be written (dual-write preserved)
- `--input` CLI flags continue to work (explicit path overrides)
- Each Phase 1 task has a `try/except` around DB loading — if DB read fails, JSON fallback activates silently

---

## Files Changed Summary

| File | Phase | Change Type |
|------|-------|-------------|
| `src/bet/db/connection.py` | 0 | Increase busy_timeout, add retry_on_lock |
| `scripts/data_enrichment_agent.py` | 0, 1 | Add _db_write_lock, fix exception handling, DB-first shortlist |
| `scripts/coupon_builder.py` | 1 | Flip to DB-first read order |
| `scripts/context_checks.py` | 1 | Add DB-first S3 loading |
| `scripts/upset_risk.py` | 1 | Add DB-first S3 loading |
| `scripts/db_data_loader.py` | 1 | (Optional) Enrich gate_results loader |
| `tests/test_db_connection.py` | 3 | New — retry_on_lock tests |
| `tests/test_enrichment_thread_safety.py` | 3 | New — concurrent write tests |
| `tests/test_pipeline_integration.py` | 3 | Modified — DB-first loading tests |

**Total files modified:** 6 (+ 2 new test files)
