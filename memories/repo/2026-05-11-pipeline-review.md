# Pipeline Review & Fixes — 2026-05-11

## Critical Bugs Found & Fixed

### 1. Goal Line Validation Missing (normalize_stats.py)
**Root cause:** When `_find_closest_standard_line()` returns `None` (standard line too far from avg), the fallback `_round_to_half(combined_avg)` has NO upper bound check. Football matches with corrupt L10 stats (avg goals ~9.0) produce absurd lines like "Goals Total O/U 9.0".

**Fix:** Added `_MAX_REASONABLE_LINE` dict with sport/stat-specific caps (e.g., football goals = 5.5). Two guard points:
1. In `_find_closest_standard_line()` — rejects absurdly high averages before lookup
2. After line computation — `continue` (skip market) if line > max reasonable

**Impact:** 25 gate-approved candidates had goal lines of 8.0-9.0. All would now be correctly rejected.

**Files:** `scripts/normalize_stats.py` — `_MAX_REASONABLE_LINE` dict + 2 guard clauses

### 2. Shortlist Garbage Filtering Incomplete (build_shortlist.py)
**Root cause:** Garbage filter regex missed:
- Soccerway adapter scraping HTML structure as team names ("Division 3", "Primera Division", "display matches (1)")
- Tennis adapter scraping bookmaker names ("1xBet vs bet365", "bet365 vs Unibet")
- Short/empty team names, all-digit team names

**Fix:** Extended `_garbage_re` with soccerway structural HTML patterns and bookmaker name patterns. Added `_bookmaker_vs_re` for fullmatch detection. Added min length check (< 2 chars) and all-digit rejection.

**Impact:** 686 garbage entries in scan_results (5.6%), 135 survived into shortlist.

**Files:** `scripts/build_shortlist.py` — extended regex + 3 new checks

### 3. SQL Injection in _diag_quality.py
**Root cause:** f-string interpolation in SQL query (`f"WHERE betting_date='{TODAY}'"`)
**Fix:** Parameterized queries (`conn.execute("... WHERE betting_date=?", (TODAY,))`)

### 4. db_report.py Fixtures Query Crash
**Root cause:** `report_scan()` queried `fixtures` table with `WHERE sport=?` but `fixtures` uses `sport_id INTEGER FK → sports(id)`, not text. 
**Fix:** JOIN with sports table: `SELECT s.name, COUNT(*) FROM fixtures f JOIN sports s ON f.sport_id = s.id`

### 5. Bare except / broad exceptions
- `_diag_quality.py`: `except:` → `except (json.JSONDecodeError, TypeError):`
- `night_session_filter.py`: `except Exception:` → `except (ValueError, TypeError):`
- Division-by-zero guard: `if t == 0: return` before percentage calculations

## Data Quality Issues Discovered (NOT YET FIXED — adapter-level)

### Soccerway Adapter Broken
- 255 entries scraping HTML structural elements as team names
- Examples: "Division 3", "Primera Division", nav text "display matches (1)", entire table rows
- **Needs:** Adapter-level fix in soccerway scraping code

### Tennis Adapter Scraping Bookmaker Names  
- 30+ entries like "1xBet vs bet365", duplicated 8-11x each
- **Needs:** Adapter-level fix in tennis scraping code

### Missing Data Fields
- 3,584 events (29.5%) with no competition field
- 2,278 events (18.7%) with no kickoff time
- 1,016 duplicate rows across sources

### Missing DB Tables
- `shortlist`, `deep_stats`, `safety_scores`, `enrichment_cache`, `odds_snapshots` — data only in JSON files
- Pipeline uses JSON fallback instead of DB-first (violates R2)

## Coupon-Level Issues Found & Fixed
- Phantom fixtures: 4 teams appearing in 2 matches same day → upgraded to KRYTYCZNE blocking warnings
- Goals O9.0 picks: marked as ⛔ BŁĄD DANYCH (DATA ERROR)
- Budget violation: 28% bankroll → recommended Option A (17.5%)
- NIGHT-MS2 coupon: 2 phantom-risk teams (max 1) → marked ZABLOKOWANY

## Key Lessons

1. **Always validate computed lines against sport-reasonable ranges.** STANDARD_MARKET_LINES defines correct lines (e.g., [1.5, 2.5, 3.5] for football goals), but the fallback path `_round_to_half()` has no bounds.

2. **Garbage filtering must be maintained as adapters change.** New scraping sources = new garbage patterns. Review scan_results quality regularly.

3. **DB schema matters for queries.** `fixtures.sport_id` is FK to `sports.id`, NOT a text field. Always check schema before writing queries.

4. **Never use f-strings in SQL.** Always parameterized queries, even for "safe" constants like dates.

5. **Test with real data.** The O9.0 goal line bug only manifests with corrupt L10 stats — unit tests with clean data would miss it.
