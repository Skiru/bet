# Beast Mode Architecture Migration — Implementation Plan

**Created:** 2026-05-12
**Status:** Draft
**Goal:** Fix all broken imports after deleting 18 HTML adapters, `fetch_with_playwright.py`, and rewriting `scan_events.py` to pure Sofascore API.

---

## Technical Context

### Old Architecture (pre-Beast Mode)
```
scan_events.py (551 lines) → Playwright + 18 HTML adapters → parse HTML → normalize → DB (scan_results + fixtures)
                            → scanners/base_scanner.py → per-sport scanners → fetch + parse + write DB
data_enrichment_agent.py   → Playwright fetch → Flashscore/Sofascore HTML → regex parse → stats_cache
odds_sources/*_scraper.py  → Playwright fetch → adapter.parse() → odds data
```

### New Architecture (Beast Mode)
```
scan_events.py (84 lines)  → Sofascore REST API → JSON → global_events_api.json
_deep_enrich_sofascore.py  → Sofascore REST API → odds, H2H, form → enriched JSON
beast_mode_pipeline.py     → Sofascore REST API → football-only enriched pipeline
```

### What Was Deleted
- `scripts/adapters/` — entire directory (18 adapter files + `__init__.py`)
- `scripts/fetch_with_playwright.py` — Playwright-based HTML fetcher

### Critical Data Flow Gap
The new `scan_events.py` writes **only** to `betting/data/global_events_api.json`.
The downstream pipeline (`build_shortlist.py`) reads from DB via `db_data_loader.load_fixtures_from_db()` → `FixtureRepo`.
**Without DB writing, the entire downstream pipeline gets zero fixtures.**

---

## Dependency Map (All Broken Imports)

| File | Broken Import | Type | Severity |
|------|--------------|------|----------|
| `scripts/data_enrichment_agent.py:29` | `from fetch_with_playwright import fetch` | top-level, hard crash | **P0** |
| `scripts/scan_events.py` | no DB write (data flow gap) | missing integration | **P0** |
| `scripts/fetch_betclic_bets.py:22` | `from fetch_with_playwright import USER_AGENTS, STORAGE_DIR, load_selectors` | top-level, hard crash | **P0** |
| `scripts/verify_betclic_odds.py:28` | `from fetch_with_playwright import load_selectors, USER_AGENTS, STORAGE_DIR` | top-level, hard crash | **P0** |
| `scripts/betclic_login.py:20` | `from fetch_with_playwright import USER_AGENTS, STORAGE_DIR` | top-level, hard crash | **P0** |
| `scripts/tipster_aggregator.py:40` | `from fetch_with_playwright import fetch` | try/except, graceful fallback | **P1** |
| `scripts/web_research_agent.py:168` | `from fetch_with_playwright import fetch` | lazy import, has urllib fallback | **P1** |
| `scripts/scanners/base_scanner.py:27,30,39` | `from adapters import normalize_adapter_output`, `fetch`, `get_adapter` | top-level | **P1** |
| `scripts/odds_sources/betexplorer_scraper.py:48-49` | `fetch_with_playwright.fetch`, `adapters.betexplorer_adapter.parse` | lazy import, try/except | **P1** |
| `scripts/odds_sources/betclic_scraper.py:60-71` | `adapters.betclic_adapter.parse`, `fetch_with_playwright.fetch` | lazy import, try/except | **P1** |
| `scripts/odds_sources/oddsportal_scraper.py:48-49` | `fetch_with_playwright.fetch`, `adapters.oddsportal_adapter.parse` | lazy import, try/except | **P1** |
| `scripts/fetch_tennis_elo.py:25` | `from adapters.tennisabstract_adapter import parse` | top-level, hard crash | **P2** |
| `scripts/_live_test_adapters.py` | `from adapters import ADAPTERS, normalize_adapter_output` | test script | **P3** |
| `scripts/_live_test_ingest_pipeline.py` | `from adapters import ADAPTERS, normalize_adapter_output` | test script | **P3** |
| `scripts/_live_test_basketball.py` | `from adapters.basketball_reference_adapter import parse` | test script | **P3** |
| `scripts/_live_test_football_adapters.py` | likely adapter imports | test script | **P3** |
| `scripts/_live_test_tennis_adapters.py` | likely adapter imports | test script | **P3** |
| `scripts/_test_volleyball_deep.py` | `adapters.sofascore_adapter`, `flashscore_adapter`, etc. | test script | **P3** |
| `scripts/_verify_db_pipeline.py` | `from adapters import normalize_adapter_output` | test script | **P3** |
| `scripts/_verify_methodology_flow.py` | `adapters.tennisexplorer_adapter`, `tennisabstract_adapter`, `normalize_batch` | test script | **P3** |

---

## Phase 0: Critical Data Flow — scan_events.py DB Integration

**Why:** Without this, `build_shortlist.py` reads zero fixtures from DB. The entire pipeline is dead.

### Task 0.1 — [MODIFY] `scripts/scan_events.py`: Add DB writing alongside JSON output

**Current state:** Writes only to `betting/data/global_events_api.json` (84 lines, pure Sofascore API).

**Required changes:**
1. Import `bet.db.connection.get_db`, `bet.db.models.ScanResult`, `bet.db.repositories.ScanResultRepo`
2. After normalization loop, create `ScanResult` objects from the normalized events:
   - `betting_date` = `args.date`
   - `sport` = event `sport` field
   - `source_domain` = `"api.sofascore.com"`
   - `event_key` = `f"{home_team}|{away_team}|{start_time}".lower()`
   - `home_team` = event `home_team`
   - `away_team` = event `away_team`
   - `competition` = event `tournament`
   - `kickoff` = event `start_time`
   - `raw_data` = full normalized dict (include Sofascore `id` for enrichment)
   - `scan_timestamp` = `datetime.now(timezone.utc).isoformat()`
3. Call `ScanResultRepo.bulk_insert()` to write to DB
4. Log count of DB records inserted

**Also consider:** The `db_data_loader.load_fixtures_from_db()` reads from the `fixtures` table via `FixtureRepo`, NOT from `scan_results`. Need to check if there's an ingest step that moves scan_results → fixtures, or if scan_events.py should write directly to fixtures. Review `ingest_scan_stats.py` — it reads from `scan_summary.json` and writes to `stats_cache`, NOT to fixtures table. The fixtures table is populated separately. 

**Investigation needed before implementation:** Trace exactly how the OLD pipeline populated the `fixtures` table. Was it `scan_events.py → scan_results table → some ingest step → fixtures table`? Or did something else populate fixtures? The answer determines whether we write to `scan_results` (and rely on existing ingest) or directly to `fixtures`.

**Definition of done:**
- [ ] `scan_events.py` writes normalized events to DB (scan_results and/or fixtures table)
- [ ] `build_shortlist.py --date YYYY-MM-DD` finds fixtures for a date that was scanned with the new `scan_events.py`
- [ ] JSON output to `global_events_api.json` still works (dual-write)

---

## Phase 1: Betclic Playwright Helpers Extraction

**Why:** 3 Betclic-specific scripts (`fetch_betclic_bets.py`, `verify_betclic_odds.py`, `betclic_login.py`) need Playwright for Betclic scraping. They don't need the full `fetch_with_playwright.py` — only the constants `USER_AGENTS`, `STORAGE_DIR`, and `load_selectors()`.

### Task 1.1 — [CREATE] `scripts/betclic_helpers.py`: Minimal Playwright constants for Betclic scripts

**Contents to extract (define inline — the original file is deleted):**
```python
"""Minimal Playwright helpers for Betclic-specific scripts.

Extracted from the deleted fetch_with_playwright.py. Only contains
constants and utilities needed by betclic_login.py, fetch_betclic_bets.py,
and verify_betclic_odds.py.
"""
from pathlib import Path

STORAGE_DIR = Path(__file__).resolve().parent / "playwright_storage"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

def load_selectors() -> dict:
    """Load CSS selectors for Betclic page scraping."""
    # ... (reproduce the selectors dict from deleted file or keep inline)
```

**Note:** Check git history for the exact `USER_AGENTS` list and `load_selectors()` implementation from the deleted `fetch_with_playwright.py`. These must match what the Betclic scripts expect.

**Definition of done:**
- [ ] `scripts/betclic_helpers.py` exists with `USER_AGENTS`, `STORAGE_DIR`, `load_selectors()` 
- [ ] `python3 -c "from betclic_helpers import USER_AGENTS, STORAGE_DIR, load_selectors"` succeeds (run from scripts/)

### Task 1.2 — [MODIFY] `scripts/fetch_betclic_bets.py`: Update import

**Change:**
```python
# OLD:
from fetch_with_playwright import USER_AGENTS, STORAGE_DIR, load_selectors
# NEW:
from betclic_helpers import USER_AGENTS, STORAGE_DIR, load_selectors
```

**Definition of done:**
- [ ] No `ImportError` when running `python3 scripts/fetch_betclic_bets.py --help`

### Task 1.3 — [MODIFY] `scripts/verify_betclic_odds.py`: Update import

**Change:**
```python
# OLD:
from fetch_with_playwright import load_selectors, USER_AGENTS, STORAGE_DIR
# NEW:
from betclic_helpers import load_selectors, USER_AGENTS, STORAGE_DIR
```

**Definition of done:**
- [ ] No `ImportError` when running `python3 scripts/verify_betclic_odds.py --help`

### Task 1.4 — [MODIFY] `scripts/betclic_login.py`: Update import

**Change:**
```python
# OLD:
from fetch_with_playwright import USER_AGENTS, STORAGE_DIR
# NEW:
from betclic_helpers import USER_AGENTS, STORAGE_DIR
```

**Definition of done:**
- [ ] No `ImportError` when running `python3 scripts/betclic_login.py --help`

---

## Phase 2: Core Pipeline Import Fixes

**Why:** These scripts are part of the daily betting pipeline and crash on import.

### Task 2.1 — [MODIFY] `scripts/data_enrichment_agent.py`: Replace Playwright fetch with requests fallback

**Current state:** Line 29 has a top-level hard import:
```python
from fetch_with_playwright import fetch  # noqa: E402
```
The script uses `fetch(url)` to get HTML from Flashscore/Sofascore/scores24. All 3 sources are HTML-based. The script is 400+ lines of regex-based HTML parsing.

**Option A (minimal fix):** Replace with a requests-based `fetch` fallback:
```python
import requests

def fetch(url: str) -> str:
    """Simple HTTP fetch — replaces deleted Playwright fetcher."""
    resp = requests.get(url, timeout=30, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })
    resp.raise_for_status()
    return resp.text
```
This preserves all existing HTML parsing logic. Flashscore/Sofascore HTML pages may return less data without JS rendering, but the script already handles partial data gracefully.

**Option B (full rewrite):** Rewrite to use Sofascore API (like `_deep_enrich_sofascore.py`). This is better long-term but much more work — defer to a separate task.

**Recommended:** Option A now (unblock pipeline), Option B as future improvement.

**Definition of done:**
- [ ] `python3 scripts/data_enrichment_agent.py --help` runs without `ImportError`
- [ ] The `fetch()` function is defined locally with requests-based implementation

### Task 2.2 — [MODIFY] `scripts/tipster_aggregator.py`: Clean up fetch import (already works)

**Current state:** Lines 40-51 have a try/except with requests fallback. This already works but prints a warning. No change strictly needed — just cosmetic.

**Optional change:** Remove the try/except and keep only the requests fallback since `fetch_with_playwright` no longer exists:
```python
import requests

def fetch(url: str) -> str:
    resp = requests.get(url, timeout=30, headers={...})
    resp.raise_for_status()
    return resp.text
```

**Definition of done:**
- [ ] `python3 scripts/tipster_aggregator.py --help` runs without warnings about missing Playwright
- [ ] Tipster fetching still works via HTTP requests

### Task 2.3 — [MODIFY] `scripts/web_research_agent.py`: Clean up Playwright reference (already works)

**Current state:** Line 168 has a lazy import inside `_fetch_via_playwright()` function with urllib fallback at line 176. Already works — falls through to urllib.

**Optional change:** Remove the Playwright import attempt from `_fetch_via_playwright()` and rename to `_fetch_via_requests()` or simplify to just use urllib directly:
```python
def _fetch_via_playwright(url: str) -> str | None:
    """Fetch URL via HTTP requests (Playwright removed in Beast Mode)."""
    return _fetch_via_urllib(url)
```

**Definition of done:**
- [ ] `python3 scripts/web_research_agent.py --help` runs without errors
- [ ] Web research still works via urllib fallback

---

## Phase 3: Odds Sources — Disable HTML Scrapers

**Why:** 3 odds source scrapers import deleted adapters. They fail gracefully (lazy imports with try/except), but should be explicitly disabled.

### Task 3.1 — [MODIFY] `scripts/odds_sources/betexplorer_scraper.py`: Disable scraper

**Current state:** `fetch_odds()` method (line 48-49) lazy-imports `fetch_with_playwright.fetch` and `adapters.betexplorer_adapter.parse`. Both are deleted. The try/except catches `ImportError` and returns `[]`.

**Change:** Add early return with deprecation notice at top of `fetch_odds()`:
```python
def fetch_odds(self, sport: str, date_from: str, date_to: str) -> list[dict]:
    # DEPRECATED: BetExplorer HTML scraping removed in Beast Mode migration.
    # Adapter and Playwright fetcher no longer exist. Use API-based odds sources.
    return []
```

**Definition of done:**
- [ ] `BetExplorerSource().fetch_odds("football", "2026-05-12", "2026-05-12")` returns `[]` without errors

### Task 3.2 — [MODIFY] `scripts/odds_sources/oddsportal_scraper.py`: Disable scraper

Same pattern as Task 3.1. Add early return with deprecation comment.

**Definition of done:**
- [ ] `OddsPortalSource().fetch_odds(...)` returns `[]` without errors

### Task 3.3 — [MODIFY] `scripts/odds_sources/betclic_scraper.py`: Disable scraper

Same pattern. The Betclic scraper was already getting 403s anyway.

**Definition of done:**
- [ ] `BetclicSource().fetch_odds(...)` returns `[]` without errors

---

## Phase 4: Scanners Framework Deprecation

**Why:** The `scanners/` framework is the old Playwright+adapters scanning system. It's replaced by the new `scan_events.py` (Sofascore API). It imports from deleted `adapters` package and `fetch_with_playwright`.

### Task 4.1 — [MODIFY] `scripts/scanners/base_scanner.py`: Guard all broken imports

**Current broken imports:**
- Line 27: `from adapters import normalize_adapter_output` — hard crash
- Line 30: `from fetch_with_playwright import fetch` — try/except, has requests fallback
- Line 39: `from adapters import get_adapter` — hard crash

**Change:** Wrap the adapter imports in try/except with stubs that raise `RuntimeError` explaining the framework is deprecated:
```python
try:
    from adapters import normalize_adapter_output
except ImportError:
    def normalize_adapter_output(event, source_type=""):
        raise RuntimeError("Scanners framework deprecated — use scan_events.py (Beast Mode)")

try:
    from adapters import get_adapter
except ImportError:
    def get_adapter(domain):
        raise RuntimeError("Scanners framework deprecated — use scan_events.py (Beast Mode)")
```

This prevents import-time crashes while making it clear at runtime that the framework shouldn't be used.

**Definition of done:**
- [ ] `from scanners.base_scanner import BaseSportScanner` doesn't crash on import
- [ ] Calling `BaseSportScanner.scan()` raises a clear deprecation error

### Task 4.2 — [CREATE] `scripts/scanners/DEPRECATED.md`: Document deprecation

**Contents:**
```markdown
# Scanners Framework — DEPRECATED

This framework was replaced by `scripts/scan_events.py` (Beast Mode) on 2026-05-12.

The old system used Playwright + HTML adapters to scrape event data.
The new system uses Sofascore REST API directly.

Do not add new scanners to this framework. Use `scan_events.py` instead.
```

**Definition of done:**
- [ ] File exists and communicates deprecation clearly

---

## Phase 5: fetch_tennis_elo.py Fix

**Why:** This script imports `adapters.tennisabstract_adapter.parse` which no longer exists. Unlike test scripts, this is a real pipeline utility for tennis Elo ratings.

### Task 5.1 — [MODIFY] `scripts/fetch_tennis_elo.py`: Inline TennisAbstract parsing

**Current state:** Uses `tennisabstract_parse(html, url)` to parse Elo ratings HTML from tennisabstract.com.

**Required change:** The `tennisabstract_adapter.parse()` function was a simple HTML table parser. Inline the parsing logic directly in `fetch_tennis_elo.py`:

1. Check git history for the deleted `adapters/tennisabstract_adapter.py` to understand the `parse()` function
2. The function likely parses an HTML table of Elo ratings into a list of dicts with player names, Elo values, etc.
3. Inline a `_parse_elo_html(html, url)` function that does the same parsing using `re` and/or `BeautifulSoup`
4. Replace the import with the local function

**Alternative:** Use Sofascore API for player ratings if available (likely not — Elo is specific to TennisAbstract).

**Definition of done:**
- [ ] `python3 scripts/fetch_tennis_elo.py --help` runs without `ImportError`
- [ ] `python3 scripts/fetch_tennis_elo.py --tour atp --verbose` fetches and parses ATP Elo ratings

---

## Phase 6: Test Script Cleanup

**Why:** 8 test/verification scripts (prefixed with `_`) test deleted adapters and will never work again. They are dead code.

### Task 6.1 — [DELETE] Adapter test scripts

**Files to delete:**
1. `scripts/_live_test_adapters.py` — tests all 18 deleted adapters
2. `scripts/_live_test_football_adapters.py` — tests deleted football adapters
3. `scripts/_live_test_tennis_adapters.py` — tests deleted tennis adapters
4. `scripts/_live_test_basketball.py` — tests deleted basketball_reference_adapter
5. `scripts/_live_test_ingest_pipeline.py` — tests adapter → ingest pipeline
6. `scripts/_test_volleyball_deep.py` — tests sofascore/flashscore/betexplorer/scores24 adapters

### Task 6.2 — [DELETE] Methodology verification scripts

**Files to delete:**
1. `scripts/_verify_db_pipeline.py` — uses `normalize_adapter_output` + references deleted adapters
2. `scripts/_verify_methodology_flow.py` — imports `tennisexplorer_adapter`, `tennisabstract_adapter`, `normalize_batch`

**Definition of done:**
- [ ] All 8 files are deleted
- [ ] No remaining `scripts/_*` files that import from `adapters` or `fetch_with_playwright`

---

## Phase 7: Final Verification

### Task 7.1 — Full import check

Run a comprehensive import check across all remaining scripts to ensure zero broken imports:

```bash
# Check each core pipeline script can be imported
python3 -c "import sys; sys.path.insert(0, 'scripts'); import scan_events"
python3 -c "import sys; sys.path.insert(0, 'scripts'); import build_shortlist"
python3 -c "import sys; sys.path.insert(0, 'scripts'); import data_enrichment_agent"
python3 -c "import sys; sys.path.insert(0, 'scripts'); import tipster_aggregator"
python3 -c "import sys; sys.path.insert(0, 'scripts'); import web_research_agent"
python3 -c "import sys; sys.path.insert(0, 'scripts'); import fetch_odds_multi"
python3 -c "import sys; sys.path.insert(0, 'scripts'); import fetch_tennis_elo"
python3 -c "import sys; sys.path.insert(0, 'scripts'); import betclic_login"
python3 -c "import sys; sys.path.insert(0, 'scripts'); import verify_betclic_odds"
python3 -c "import sys; sys.path.insert(0, 'scripts'); import fetch_betclic_bets"
```

**Definition of done:**
- [ ] Zero `ImportError` or `ModuleNotFoundError` across all non-`_` prefixed scripts
- [ ] `grep -r "from fetch_with_playwright" scripts/ --include="*.py"` returns zero matches in active (non-`_` prefixed) scripts
- [ ] `grep -r "from adapters" scripts/ --include="*.py"` returns zero matches in active (non-`_` prefixed) scripts (except scanners/ which has guarded imports)

---

## Implementation Order Summary

| Order | Phase | Priority | Est. Tasks | Risk |
|-------|-------|----------|-----------|------|
| 1 | Phase 0: scan_events.py DB integration | **P0** | 1 (complex) | HIGH — data flow |
| 2 | Phase 1: Betclic helpers extraction | **P0** | 4 | LOW — straightforward |
| 3 | Phase 2: Core pipeline import fixes | **P0** | 3 | LOW — fallback patterns |
| 4 | Phase 3: Odds sources deprecation | **P1** | 3 | LOW — early return |
| 5 | Phase 4: Scanners deprecation | **P1** | 2 | LOW — guard imports |
| 6 | Phase 5: fetch_tennis_elo.py | **P2** | 1 | MEDIUM — need adapter logic |
| 7 | Phase 6: Test script cleanup | **P3** | 2 | NONE — pure deletion |
| 8 | Phase 7: Final verification | — | 1 | — |

**Total: 17 tasks across 8 phases.**

---

## Open Questions

1. **DB write target for scan_events.py:** Should it write to `scan_results` table (and rely on existing ingest pipeline to populate `fixtures`) or directly to `fixtures` table? Need to trace how the old pipeline populated `fixtures`.

2. **fetch_with_playwright.py git recovery:** The exact contents of `USER_AGENTS`, `STORAGE_DIR`, and `load_selectors()` need to be recovered from git history to create `betclic_helpers.py`.

3. **tennisabstract_adapter.parse() recovery:** The Elo HTML parsing logic needs to be recovered from git history to inline in `fetch_tennis_elo.py`.

4. **data_enrichment_agent.py long-term:** Should it be fully rewritten to Sofascore API (like `_deep_enrich_sofascore.py`) or is the requests-based HTML fallback sufficient? The HTML approach will degrade without JS rendering (Flashscore needs JS).

5. **scanners/ full removal:** Should `scanners/` be deleted entirely in a future cleanup, or kept as deprecated for reference?
