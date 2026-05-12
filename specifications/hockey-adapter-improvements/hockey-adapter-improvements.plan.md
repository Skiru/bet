# Hockey Adapter Improvements — Implementation Plan

**Created:** 2026-05-12  
**Status:** Draft  
**Agent:** tsh-software-engineer (all tasks)

---

## Executive Summary

Improve hockey data coverage by: (1) syncing the scanner with config URLs, (2) enhancing hockey-reference with box score parsing, (3) adding NaturalStatTrick adapter (advanced analytics), (4) adding DailyFaceoff adapter (goalie confirmations), (5) enhancing Covers for NHL, and (6) updating tests and documentation.

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| NaturalStatTrick rendering | Playwright (via `fetch_with_playwright`) | Table-driven query pages, consent selector already in `site_selectors.json` |
| DailyFaceoff rendering | Playwright | JS-rendered goalie table, consent selector already in `site_selectors.json` |
| Hockey-Reference box scores | requests (no Playwright) | SSR HTML tables, already in `API_ADAPTERS` set in `_live_test_adapters.py` |
| Scanner URL source | Load from `scan_urls.json` at runtime | Keeps config as single source of truth, matches existing 33 URLs including BetExplorer |
| New adapter registration | Domain-key in `scripts/adapters/__init__.py` ADAPTERS dict | Consistent with all 16 existing adapters |
| Deep link patterns | Add to `DOMAIN_PATTERNS` in `deep_link_discovery.py` | Consistent with existing flashscore/betexplorer/oddsportal hockey patterns |

## Dependency Graph

```
Phase 1 (Scanner URL Sync)
    │
    ├── Phase 2 (Hockey-Reference Detail Pages) ← independent
    ├── Phase 3 (NaturalStatTrick Adapter)      ← independent  
    ├── Phase 4 (DailyFaceoff Adapter)           ← independent
    └── Phase 5 (Covers NHL Enhancement)         ← independent
          │
          └── Phase 6 (Tests + Docs) ← depends on all above
```

Phases 2–5 are independent of each other and can be implemented in parallel. Phase 6 must come last.

---

## Phase 1: Hockey Scanner URL Sync

**Goal:** Align `hockey_scanner.py` with `scan_urls.json` (33 URLs) and add missing BetExplorer hockey URLs.

### Task 1.1 — Load URLs from scan_urls.json `[MODIFY]`

**File:** `scripts/scanners/hockey_scanner.py`

**Changes:**
- Replace the hardcoded 11-URL `urls` property with runtime loading from `config/scan_urls.json` → `sports.hockey.urls`
- Keep current hardcoded list as fallback if JSON loading fails
- Add BetExplorer hockey URL (`https://www.betexplorer.com/hockey/`) to `scan_urls.json` if not present

**Reference pattern:** Check if other scanners (e.g., `football_scanner.py`) already load from JSON. If not, this is the first — keep it simple: read JSON in `__init__` or in the `urls` property with a cached result.

**Definition of Done:**
- [ ] `urls` property returns ≥30 URLs (currently 11)
- [ ] URLs include all FlashScore league pages from `scan_urls.json` (22 FlashScore hockey URLs)
- [ ] URLs include sofascore.com/ice-hockey
- [ ] URLs include BetExplorer hockey
- [ ] Fallback to hardcoded list if JSON file not found or parse error
- [ ] Unit test: mock `scan_urls.json`, verify URL count and key domains present
- [ ] Existing `register_scanner("hockey", HockeyScanner)` call unchanged

### Task 1.2 — Add BetExplorer hockey URL to scan_urls.json `[MODIFY]`

**File:** `config/scan_urls.json`

**Changes:**
- Add `https://www.betexplorer.com/hockey/` to the `sports.hockey.urls` array (BetExplorer already has a dedicated adapter and deep link patterns for hockey)

**Definition of Done:**
- [ ] `scan_urls.json` hockey section contains BetExplorer hockey URL
- [ ] JSON remains valid (parseable)

---

## Phase 2: Hockey-Reference Detail Page Parsing

**Goal:** Extend `hockey_reference_adapter.py` to parse box score pages (`/boxscores/YYYYMMDD0XXX.html`) extracting per-period scores, shots, PIM, PP goals, hits, blocks, and faceoff %.

### Task 2.1 — Add box score page detection and parsing `[MODIFY]`

**File:** `scripts/adapters/hockey_reference_adapter.py`

**Changes:**
- Add URL detection: if URL matches `/boxscores/\d{9}\w+\.html` pattern, route to new `_parse_boxscore()` function
- Implement `_parse_boxscore(soup, url)` that extracts:
  - Teams (from scorebox or game header)
  - Final score and period scores (from scoring summary table)
  - Team stats: shots, PIM, PP goals, PP opportunities, hits, blocks, faceoff wins/losses (from team stats table, `data-stat` attributes)
  - Goalie stats: saves, save %, GAA (from goalie stats table)
- Return standard dict format with `source_type: "hockey_reference"`, `sport: "hockey"`
- Map stats into the normalized schema fields: `shots`, `period_scores`, plus a `stats` dict for advanced data

**HTML structure reference (Hockey-Reference box scores):**
- Table `id="scoring"` — period-by-period scoring
- Table with `data-stat` attributes: `visitor_team_name`, `home_team_name`, `goals`, `assists`, `shots`, `pim`, `pp`, `ppoa`, `hits`, `blocks`, `fow`, `fol`
- Goalie table with `data-stat`: `saves`, `save_pct`, `goals_against_avg`

**Definition of Done:**
- [ ] Box score URLs (`/boxscores/...`) return a dict with: home, away, score_home, score_away, period_scores, stats (shots, pim, pp_goals, pp_opportunities, hits, blocks, faceoff_wins, faceoff_losses, saves, save_pct)
- [ ] Schedule page parsing unchanged (no regression)
- [ ] Fallback to `raw_parse` if box score tables not found
- [ ] Unit test with sample box score HTML fixture asserting all stat fields populated

### Task 2.2 — Dynamic league detection `[MODIFY]`

**File:** `scripts/adapters/hockey_reference_adapter.py`

**Changes:**
- Replace hardcoded `"league": "NHL"` with detection from URL path or page content
- If URL contains `/nhl/` or is `hockey-reference.com` root → `"NHL"`
- If URL contains a recognizable league slug → map it
- Fallback: `"NHL"` (Hockey-Reference is primarily NHL)

**Definition of Done:**
- [ ] League field is dynamically determined from URL
- [ ] Default remains `"NHL"` for ambiguous URLs
- [ ] No regression on existing schedule page parsing

### Task 2.3 — Add hockey-reference deep link patterns `[MODIFY]`

**File:** `scripts/deep_link_discovery.py`

**Changes:**
- Add `"hockey-reference.com"` entry to `DOMAIN_PATTERNS` dict with:
  - Include: `/boxscores/\d{9}\w+\.html` (individual game box scores), `/teams/\w+/\d{4}_games\.html` (team game logs)
  - Exclude: `/players/`, `/awards/`, `/about/`, `/blog/`

**Definition of Done:**
- [ ] `discover_deep_links()` returns box score URLs when given a hockey-reference schedule page
- [ ] Excluded URLs (players, awards) are filtered out
- [ ] Unit test: sample HTML with box score links → correct links discovered

---

## Phase 3: NaturalStatTrick Adapter

**Goal:** Create a new adapter for `naturalstattrick.com` to extract NHL advanced analytics: Corsi%, Fenwick%, xGF, xGA, high-danger chances, special teams splits.

### Task 3.1 — Create naturalstattrick_adapter.py `[CREATE]`

**File:** `scripts/adapters/naturalstattrick_adapter.py`

**Changes:**
- Implement `parse(html: str, url: str) -> List[Dict]` following the standard adapter pattern
- Detect page type from URL:
  - **Team table** (`/teamtable.php?...`): Parse HTML table with team-level season stats. Extract per-team row: team name, GP, CF%, FF%, xGF, xGA, xGF%, HDCF, HDCA, shots_for, shots_against, SV%, SH%
  - **Game-level** (`/games.php?...`): Parse game-by-game stats table. Extract per-game row: date, teams, CF%, FF%, xGF, xGA, HDCF, HDCA, score
  - **Player page** (future, optional): Skip for now, return `raw_parse` fallback
- Return dicts with:
  - `source_type: "naturalstattrick"`
  - `sport: "hockey"`
  - `stats: { corsi_pct, fenwick_pct, xgf, xga, xg_pct, hdcf, hdca, shots_for, shots_against, sv_pct, sh_pct }`
- Use BeautifulSoup, match table headers to locate correct columns (NaturalStatTrick uses standard `<table>` elements with `<th>` headers)

**NaturalStatTrick URL patterns:**
- Team stats: `naturalstattrick.com/teamtable.php?fromseason=20252026&thession=20252026&stype=2&sit=5v5&score=all&rate=n&team=all&loc=B&gpf=410&fd=&td=`
- Game log: `naturalstattrick.com/games.php?fromseason=20252026&thession=20252026&stype=2&sit=5v5&loc=B&team=all&rate=n`

**Definition of Done:**
- [ ] `parse()` handles team table pages → returns list of team stat dicts (≥30 teams for NHL)
- [ ] `parse()` handles game log pages → returns list of game stat dicts
- [ ] Each dict contains: `source_type`, `sport`, `league`, and `stats` sub-dict with at minimum `corsi_pct`, `fenwick_pct`, `xgf`, `xga`
- [ ] Unrecognized pages fall back to `raw_parse`
- [ ] Unit test with sample HTML fixture covering team table and game log formats

### Task 3.2 — Register NaturalStatTrick adapter `[MODIFY]`

**File:** `scripts/adapters/__init__.py`

**Changes:**
- Add import: `from .naturalstattrick_adapter import parse as naturalstattrick_parse`
- Add to ADAPTERS dict: `"naturalstattrick.com": naturalstattrick_parse`

**Definition of Done:**
- [ ] `get_adapter("naturalstattrick.com")` returns the NaturalStatTrick parse function
- [ ] No import errors

### Task 3.3 — Add NaturalStatTrick URLs to config and scanner `[MODIFY]`

**Files:** `config/scan_urls.json`, `scripts/scanners/hockey_scanner.py`

**Changes:**
- Add to `scan_urls.json` hockey URLs:
  - `https://www.naturalstattrick.com/teamtable.php?fromseason=20252026&thession=20252026&stype=2&sit=5v5&score=all&rate=n&team=all&loc=B&gpf=410&fd=&td=`
  - `https://www.naturalstattrick.com/games.php?fromseason=20252026&thession=20252026&stype=2&sit=5v5&loc=B&team=all&rate=n`
- If Phase 1 is complete (dynamic URL loading), no scanner change needed. Otherwise, add to hardcoded fallback list.

**Definition of Done:**
- [ ] NaturalStatTrick URLs present in `scan_urls.json` hockey section
- [ ] Scanner includes these URLs in its scan cycle
- [ ] JSON remains valid

### Task 3.4 — Add NaturalStatTrick deep link patterns `[MODIFY]`

**File:** `scripts/deep_link_discovery.py`

**Changes:**
- Add `"naturalstattrick.com"` to `DOMAIN_PATTERNS`:
  - Include: `/teamtable\.php`, `/games\.php`, `/playerteams\.php`
  - Exclude: `/login`, `/register`, `/faq`

**Definition of Done:**
- [ ] Deep link discovery finds team and game pages from NaturalStatTrick landing pages
- [ ] Non-data pages excluded

---

## Phase 4: DailyFaceoff Adapter

**Goal:** Create a new adapter for `dailyfaceoff.com` to extract starting goalie confirmations — the #1 variable for hockey totals betting.

### Task 4.1 — Create dailyfaceoff_adapter.py `[CREATE]`

**File:** `scripts/adapters/dailyfaceoff_adapter.py`

**Changes:**
- Implement `parse(html: str, url: str) -> List[Dict]`
- Detect page type from URL:
  - **Starting goalies** (`/starting-goalies/`): Parse the goalie grid/table. Extract per-game: home team, away team, home goalie name, away goalie name, confirmation status (Confirmed/Expected/Unconfirmed), game time
  - **Line combinations** (`/teams/.../line-combinations/`): Parse forward lines and defensive pairings (future enhancement, skip for v1)
- Return dicts with:
  - `source_type: "dailyfaceoff"`
  - `sport: "hockey"`
  - `league: "NHL"`
  - `home`, `away`, `time`
  - `goalie_home: { name, status }` where status ∈ {"confirmed", "expected", "unconfirmed"}
  - `goalie_away: { name, status }`
- Use BeautifulSoup. DailyFaceoff starting goalies page uses card-style layout with team logos, goalie names, and confirmation badges.

**DailyFaceoff URL patterns:**
- Starting goalies: `dailyfaceoff.com/starting-goalies/`
- Team lines: `dailyfaceoff.com/teams/{team}/line-combinations/`

**Definition of Done:**
- [ ] `parse()` handles starting goalies page → returns list of game dicts with goalie confirmation data
- [ ] Each dict contains: `home`, `away`, `goalie_home`, `goalie_away` with name and status
- [ ] Confirmation status correctly classified as "confirmed", "expected", or "unconfirmed"
- [ ] Unrecognized pages fall back to `raw_parse`
- [ ] Unit test with sample HTML fixture asserting goalie names and confirmation statuses

### Task 4.2 — Register DailyFaceoff adapter `[MODIFY]`

**File:** `scripts/adapters/__init__.py`

**Changes:**
- Add import: `from .dailyfaceoff_adapter import parse as dailyfaceoff_parse`
- Add to ADAPTERS dict: `"dailyfaceoff.com": dailyfaceoff_parse`

**Definition of Done:**
- [ ] `get_adapter("dailyfaceoff.com")` returns the DailyFaceoff parse function
- [ ] No import errors

### Task 4.3 — Add DailyFaceoff URLs to config and scanner `[MODIFY]`

**Files:** `config/scan_urls.json`, `scripts/scanners/hockey_scanner.py`

**Changes:**
- Add to `scan_urls.json` hockey URLs:
  - `https://www.dailyfaceoff.com/starting-goalies/`
- Add `"dailyfaceoff.com"` to hockey section's `dedicated_sources` array

**Definition of Done:**
- [ ] DailyFaceoff URL present in `scan_urls.json` hockey section
- [ ] Scanner includes this URL in its scan cycle
- [ ] JSON remains valid

---

## Phase 5: Covers NHL Enhancement

**Goal:** Improve `covers_adapter.py` for NHL-specific pages with period scores, PP/PK data, and goalie matchup extraction.

### Task 5.1 — Add NHL-specific URL detection and data extraction `[MODIFY]`

**File:** `scripts/adapters/covers_adapter.py`

**Changes:**
- Add NHL-specific URL patterns to recognize:
  - `/nhl/matchups` — matchup page with game previews
  - `/nhl/odds` — odds comparison page  
  - `/nhl/standings` — standings context
- In `_parse_matchup_cards()`: when sport is `"hockey"`, look for additional NHL-specific elements:
  - Goalie matchup names (if present in card markup)
  - Period score breakdown (if available)
  - PP/PK percentages (if shown in matchup preview)
- Add these as optional fields in the returned dict: `goalie_home`, `goalie_away`, `pp_pct_home`, `pp_pct_away`, `pk_pct_home`, `pk_pct_away`

**Definition of Done:**
- [ ] NHL matchup URLs (`/nhl/matchups`, `/nhl/odds`) are correctly detected as `sport: "hockey"`
- [ ] NHL-specific fields extracted when present (goalie names, PP/PK %)
- [ ] No regression on non-NHL pages (NBA, NFL, NCAA)
- [ ] Unit test: sample NHL matchup card HTML → hockey sport detection + optional fields

### Task 5.2 — Add Covers NHL URLs to scan_urls.json `[MODIFY]`

**File:** `config/scan_urls.json`

**Changes:**
- Add to hockey URLs:
  - `https://www.covers.com/nhl/matchups`
  - `https://www.covers.com/nhl/odds`

**Definition of Done:**
- [ ] Covers NHL URLs present in `scan_urls.json` hockey section
- [ ] JSON remains valid

---

## Phase 6: Test Coverage + Documentation

**Goal:** Add live test URLs, unit tests, and update the hockey scanning skill doc.

### Task 6.1 — Add hockey test URLs and expected fields `[MODIFY]`

**File:** `scripts/_live_test_adapters.py`

**Changes:**
- Update `hockey-reference.com` expected fields from `["source_type"]` to `["source_type", "sport", "league"]`
- Add test entries:
  - `"naturalstattrick.com"`: URL = team table page, expected fields = `["source_type", "sport", "stats"]`
  - `"dailyfaceoff.com"`: URL = starting goalies page, expected fields = `["source_type", "sport", "goalie_home", "goalie_away"]`
- Add NaturalStatTrick and DailyFaceoff to `PLAYWRIGHT_ADAPTERS` set (they need browser rendering)

**Definition of Done:**
- [ ] All 3 hockey adapters have test URLs and non-trivial expected fields
- [ ] NaturalStatTrick and DailyFaceoff in PLAYWRIGHT_ADAPTERS set
- [ ] Running `_live_test_adapters.py --adapter hockey-reference.com` tests enriched fields

### Task 6.2 — Add unit tests for new adapters `[CREATE]`

**Files:**
- `tests/test_hockey_reference_boxscore.py`
- `tests/test_naturalstattrick_adapter.py`
- `tests/test_dailyfaceoff_adapter.py`

**Changes:**
- Each test file contains:
  - Sample HTML fixture (inline string or fixture file) representing a realistic page
  - Test that `parse()` returns non-empty list
  - Test that returned dicts contain all expected keys with correct types
  - Test that fallback to `raw_parse` works for unrecognized pages
- For hockey-reference boxscore: test period scores parsing, stat extraction
- For NaturalStatTrick: test team table parsing with ≥30 rows, stat key presence
- For DailyFaceoff: test goalie confirmation status classification

**Definition of Done:**
- [ ] All 3 test files pass with `pytest tests/test_hockey_reference_boxscore.py tests/test_naturalstattrick_adapter.py tests/test_dailyfaceoff_adapter.py`
- [ ] Tests cover happy path, empty page, and malformed HTML
- [ ] No external network calls (all HTML is inline fixtures)

### Task 6.3 — Add scanner URL sync unit test `[CREATE]`

**File:** `tests/test_scanners/test_hockey_scanner.py`

**Changes:**
- Test that HockeyScanner.urls returns ≥30 URLs
- Test that key domains are present: flashscore.com, hockey-reference.com, naturalstattrick.com, dailyfaceoff.com, scores24.live, forebet.com, oddsportal.com, betexplorer.com, covers.com
- Test fallback behavior when `scan_urls.json` is missing

**Definition of Done:**
- [ ] Test passes with `pytest tests/test_scanners/test_hockey_scanner.py`
- [ ] Validates URL count and domain coverage
- [ ] Tests fallback path

### Task 6.4 — Update hockey scanning skill doc `[MODIFY]`

**File:** `.github/skills/bet-scanning-hockey/SKILL.md`

**Changes:**
- **Source URLs table:** Add NaturalStatTrick, DailyFaceoff, BetExplorer, Covers NHL rows
- **Adapter Mapping table:** Add `naturalstattrick.com → naturalstattrick_adapter`, `dailyfaceoff.com → dailyfaceoff_adapter`, update `hockey-reference.com` description from "shallow" to "schedule + box scores"
- **Fallback Chains / Statistical data:** Update chain to: `NaturalStatTrick → Hockey-Reference (box scores) → MoneyPuck → API-Hockey → ESPN`
- **Known Issues:** Remove "No NaturalStatTrick adapter" and "No DailyFaceoff adapter" entries. Update Hockey-Reference entry to note box score support. Add note about NaturalStatTrick being NHL-only.
- **Timeout Configuration:** Add NaturalStatTrick (30s, Playwright) and DailyFaceoff (20s, Playwright)

**Definition of Done:**
- [ ] All 4 sections updated accurately
- [ ] No stale "no adapter" references for implemented adapters
- [ ] Fallback chain reflects actual implementation

### Task 6.5 — Update source-registry.md `[MODIFY]`

**File:** `betting/sources/source-registry.md`

**Changes:**
- Update NaturalStatTrick entry: add "Adapter: `naturalstattrick_adapter.py`" and "Status: ACTIVE"
- Update DailyFaceoff entry: add "Adapter: `dailyfaceoff_adapter.py`" and "Status: ACTIVE"
- Update Hockey-Reference entry: note box score parsing capability

**Definition of Done:**
- [ ] Source registry accurately reflects adapter availability
- [ ] No stale status information

---

## Files Affected Summary

| File | Phase | Action |
|------|-------|--------|
| `scripts/scanners/hockey_scanner.py` | 1 | MODIFY — dynamic URL loading |
| `config/scan_urls.json` | 1, 3, 4, 5 | MODIFY — add BetExplorer, NaturalStatTrick, DailyFaceoff, Covers NHL URLs |
| `scripts/adapters/hockey_reference_adapter.py` | 2 | MODIFY — add box score parsing + dynamic league detection |
| `scripts/deep_link_discovery.py` | 2, 3 | MODIFY — add hockey-reference + NaturalStatTrick patterns |
| `scripts/adapters/naturalstattrick_adapter.py` | 3 | CREATE — new adapter |
| `scripts/adapters/__init__.py` | 3, 4 | MODIFY — register 2 new adapters |
| `scripts/adapters/dailyfaceoff_adapter.py` | 4 | CREATE — new adapter |
| `scripts/adapters/covers_adapter.py` | 5 | MODIFY — NHL-specific enhancements |
| `scripts/_live_test_adapters.py` | 6 | MODIFY — add test URLs + expected fields |
| `tests/test_hockey_reference_boxscore.py` | 6 | CREATE — unit tests |
| `tests/test_naturalstattrick_adapter.py` | 6 | CREATE — unit tests |
| `tests/test_dailyfaceoff_adapter.py` | 6 | CREATE — unit tests |
| `tests/test_scanners/test_hockey_scanner.py` | 6 | CREATE — scanner URL sync test |
| `.github/skills/bet-scanning-hockey/SKILL.md` | 6 | MODIFY — update docs |
| `betting/sources/source-registry.md` | 6 | MODIFY — update source status |

**Total: 15 files (4 CREATE, 11 MODIFY)**

---

## Implementation Order

```
1. Phase 1 (Task 1.2 → 1.1) — Config first, then scanner
2. Phase 2 (Task 2.1 → 2.2 → 2.3) — Box scores, league detection, deep links
3. Phase 3 (Task 3.1 → 3.2 → 3.3 → 3.4) — NaturalStatTrick adapter → register → config → deep links
4. Phase 4 (Task 4.1 → 4.2 → 4.3) — DailyFaceoff adapter → register → config
5. Phase 5 (Task 5.1 → 5.2) — Covers NHL enhancement → config
6. Phase 6 (Tasks 6.1–6.5) — Tests and documentation
```

Phases 2–5 have no inter-dependencies and can be parallelized across branches if desired.

---

## Security Considerations

- **No credentials in adapters:** All adapters parse public HTML. No API keys or auth tokens involved.
- **Input sanitization:** Adapter `parse()` functions receive untrusted HTML. BeautifulSoup handles HTML parsing safely. No `eval()` or dynamic code execution on scraped content.
- **URL validation:** Deep link discovery already filters to same-domain links and excludes non-event pages. New patterns follow the same approach.
- **Rate limiting:** NaturalStatTrick and DailyFaceoff are added to `site_selectors.json` consent selectors (already present). Scanner respects `timeout_per_page` and domain semaphore from `BaseSportScanner`.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| NaturalStatTrick HTML structure changes | Medium | High — breaks xG/Corsi extraction | Unit tests with fixture HTML catch regressions; fallback to raw_parse |
| DailyFaceoff goalie page JS-heavy rendering | Medium | Medium — empty parse results | Playwright rendering with consent selector; test with real page before release |
| Hockey-Reference box score format varies by season | Low | Low — older games may not parse | Focus on current season format; older seasons are not scanned |
| Covers NHL pages empty (known issue in skill doc) | Medium | Low — graceful fallback to raw_parse | Not a primary data source; enhancement is opportunistic |
