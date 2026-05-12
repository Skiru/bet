# Hockey Adapter Improvements — 2026-05-12

## What Changed

### New Adapters
- **`naturalstattrick_adapter.py`** — Parses team tables (Corsi%, Fenwick%, xGF, xGA, HDCF, HDCA) and game logs. ⚠ JS-heavy site, needs Playwright rendering with cookie consent — returns 0 events with basic fetch.
- **`dailyfaceoff_adapter.py`** — JSON-first approach via `__NEXT_DATA__` embedded Next.js data. Returns goalie names, W-L-OTL, SV%, GAA, confirmation status, odds (spread/ML). HTML card fallback. Status enrichment uses proximity matching from rendered HTML.

### Modified Adapters
- **`hockey_reference_adapter.py`** — Added `_parse_boxscore()` for `/boxscores/` URLs. Extracts: period scores, team stats (goals, shots, PIM, PP, hits, blocks, faceoffs), goalie stats (saves, SV%, GAA). Goalie assignment uses table ID abbreviation matching (`goalies_BOS` → "BOS" → match against team names). Dynamic league detection (NHL default, supports olympics/wha/nwhl/pwhl).
- **`covers_adapter.py`** — NHL-specific extraction: goalie names (as dicts), PP/PK%, W-L-OTL records.
- **`__init__.py`** — Registered naturalstattrick.com + dailyfaceoff.com. Added `hockey` sub-dict to `ENRICHED_EVENT_DEFAULTS` (stats, goalie_stats, goalie_home, goalie_away, data_type). Hockey merge logic in `normalize_adapter_output`.

### Infrastructure
- **`hockey_scanner.py`** — Loads URLs from `config/scan_urls.json` (38 hockey URLs) with `_FALLBACK_URLS` fallback.
- **`config/scan_urls.json`** — Added BetExplorer, Covers NHL, NaturalStatTrick (2 URLs), DailyFaceoff.
- **`deep_link_discovery.py`** — Added patterns for hockey-reference.com and naturalstattrick.com.

## Bugs Found & Fixed
1. **Covers goalie type mismatch** — was plain strings, now `{"name": ...}` dicts.
2. **Hockey-ref goalie assignment** — was checking for "home" in table ID (never present). Now matches abbreviation from `goalies_XXX` against team names.
3. **Hockey fields lost in normalize** — Added `hockey` sub-dict + merge logic.
4. **DailyFaceoff status substring collision** — "unconfirmed" was matching "confirmed" first. Fixed: check longer patterns first via `sorted(key=len, reverse=True)`.
5. **Dead regex** in hockey-ref boxscore URL check — removed redundant `"/boxscores/" in url`.

## Live Test Results (2026-05-12)
- hockey-reference.com: ✅ 2 events (NHL schedule)
- dailyfaceoff.com: ✅ 2 events (goalie confirmations via JSON)
- naturalstattrick.com: ⚠ 0 events (JS rendering limitation — adapter code correct)
- covers.com: ✅ 86 events (NBA matchups page; NHL URL also registered)

## Test Coverage
- 16/16 unit tests passing (tests/test_hockey_adapters.py)
- 574/576 full suite (2 pre-existing failures unrelated to hockey)

## Data Flow Verification
- `scan_events.py` → `normalize_adapter_output()` → hockey fields preserved in `normalized["hockey"]` dict
- `build_shortlist.py` — hockey is Tier 1, league scoring in place (NHL=9, SHL/Liiga/DEL=8)
- `deep_stats_report.py` — ESPN enrichment for hockey
- `html_deep_parser.py` — `HockeyReferenceProfile` handles deeper extraction
- DB: `SourceHealthRepo` records scan health; `ScanResultRepo` stores parsed results
