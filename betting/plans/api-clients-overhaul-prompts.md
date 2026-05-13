# API Client Layer Overhaul — Agent Prompts

## How To Use
Each section below is a **standalone prompt** to paste into a **fresh Copilot chat session** (use `tsh-software-engineer` mode).
Run waves in order. Wave 1A and 1B can run in parallel. Wave 2A/2B/2C can run in parallel (after Wave 1A).

---

## WAVE 1A — PlaywrightBaseClient + unified.py fix (Phases 1+2)

```
Implement Phases 1 and 2 from the plan at `betting/plans/api-clients-overhaul.plan.md`.

READ the full plan first (lines 1-200 for Phase 1, 150-210 for Phase 2).
READ the memory file `memories/repo/api-clients-overhaul-plan.md` for context.

### Phase 1: Create PlaywrightBaseClient

CREATE `src/bet/api_clients/playwright_base.py`:
- Extract shared Playwright boilerplate from `src/bet/api_clients/flashscore.py` (lines 100-245)
- Methods to extract VERBATIM: _ensure_browser, _new_page, _dismiss_cookies, _handle_cloudflare, _load_page, close, __enter__, __exit__, __del__
- Make _COOKIE_SELECTOR a class attribute (override in subclasses)
- Circuit breaker uses `type(self)._failures` for per-subclass isolation
- Add `_evaluate_js(page, js_code)` wrapper with error handling
- Add `is_available() -> bool` → always True

THEN MODIFY `src/bet/api_clients/flashscore.py`:
- Change `class FlashscoreClient(BaseAPIClient)` → `class FlashscoreClient(PlaywrightBaseClient)`
- Remove all methods that moved to PlaywrightBaseClient (no duplication)
- Keep: JS extraction constants, get_fixtures, get_fixture_stats, get_h2h, get_match_preview, get_team_last_fixtures, _parse_stats_text, SPORT_SLUGS, STAT_NAME_MAP
- Verify `isinstance(client, BaseAPIClient)` still True via inheritance

### Phase 2: Fix unified.py

MODIFY `src/bet/api_clients/unified.py`:
- Add sport-aware SOURCE_PRIORITY routing table
- Lazy-init clients (only create when first needed via _client_cache dict)
- get_fixtures(): iterate SOURCE_PRIORITY[sport], try each, merge + dedup
- Guard all Playwright client calls with try/except
- Context manager cleans up ALL child clients
- Import guards for clients not yet created (BetExplorer etc.)

### Verification
After implementing, run:
```
PYTHONPATH=src .venv/bin/python -c "from bet.api_clients.playwright_base import PlaywrightBaseClient; print('OK')"
PYTHONPATH=src .venv/bin/python -c "from bet.api_clients.flashscore import FlashscoreClient; from bet.api_clients.base_client import BaseAPIClient; c = FlashscoreClient.__mro__; print([x.__name__ for x in c])"
```

CRITICAL RULES:
- playwright-stealth v2: `from playwright_stealth import Stealth; Stealth().apply_stealth_sync(page)` (NOT stealth_sync)
- Use `page.inner_text('body')` NOT `page.content()` for text extraction
- Fish shell — no inline Python in terminal, create temp test scripts instead
- Read flashscore.py FULLY before extracting (834 lines)
```

---

## WAVE 1B — Dead Client Cleanup (Phase 8)

```
Implement Phase 8 from the plan at `betting/plans/api-clients-overhaul.plan.md` (lines 700-770).

READ the memory file `memories/repo/api-clients-overhaul-plan.md` for context.

### Tasks

1. MODIFY `scripts/api_clients/balldontlie.py`:
   - Add deprecation header: `# DEPRECATED 2026-05-13 — v1 API deprecated, 100% failure rate. DO NOT USE.`
   - Ensure `_HOST_BROKEN = True` is set
   - Override `get_fixtures()` to return `[]` immediately with warning log

2. MODIFY `scripts/api_clients/thesportsdb.py`:
   - Add deprecation header: `# DEPRECATED 2026-05-13 — 97.8% failure rate. DO NOT USE.`
   - Ensure `_HOST_BROKEN = True` is set
   - Override `get_fixtures()` to return `[]` immediately with warning log

3. MODIFY `scripts/api_clients/api_tennis.py`:
   - Add deprecation header: `# DEPRECATED 2026-05-13 — NXDOMAIN. Host does not resolve. DO NOT USE.`
   - Ensure `_HOST_BROKEN = True` is set
   - Override `get_fixtures()` to return `[]` immediately with warning log

4. MODIFY `scripts/api_clients/__init__.py`:
   - Remove broken clients from CLIENT_REGISTRY (if registered)
   - Add comment explaining why excluded

5. MODIFY `betting/sources/source-registry.md`:
   - Move BallDontLie, TheSportsDB, API-Tennis to a new "## Deprecated / Broken Sources" section
   - Add deprecation dates and reasons
   - Remove them from any active fallback chains

This is a cleanup phase — keep changes minimal and focused.
```

---

## WAVE 2A — BetExplorer + Soccerway HTTP Clients (Phases 3+7)

```
Implement Phases 3 and 7 from the plan at `betting/plans/api-clients-overhaul.plan.md`.

READ the full plan (lines 210-320 for Phase 3, lines 580-680 for Phase 7).
READ the memory file `memories/repo/api-clients-overhaul-plan.md` for context.
READ `src/bet/api_clients/base_client.py` (255 lines) — your clients extend BaseAPIClient.
READ `src/bet/api_clients/rate_limiter.py` — betexplorer-scraper (50/day) already exists.

### Phase 3: BetExplorer Client (HTTP-first)

STEP 1 — Debug script FIRST:
CREATE `scripts/_debug_betexplorer.py`:
- Load https://www.betexplorer.com/football/ with requests (HTTP)
- Parse with BeautifulSoup4
- Dump: table structure, row classes, team name selectors, odds cells
- Test with all 5 sports: /football/, /tennis/, /basketball/, /hockey/, /volleyball/
- Run it: `PYTHONPATH=src .venv/bin/python scripts/_debug_betexplorer.py`
- Study the output to discover REAL selectors

STEP 2 — Client implementation:
CREATE `src/bet/api_clients/betexplorer.py`:
- class BetExplorerClient(BaseAPIClient) — HTTP-first, requests + BeautifulSoup
- SPORT_PATHS: football, tennis, basketball, hockey, volleyball
- Methods: get_fixtures(date, sport), get_odds(match_url), get_results(date, sport), get_fixture_stats(fixture_id), get_h2h(team1_id, team2_id)
- All return APIFixture / list[dict] types
- Rate limiter: "betexplorer-scraper" (already in rate_limiter.py)
- Cache: betting/data/stats_cache/betexplorer/
- HTTP session headers: Accept, Referer, User-Agent rotation

### Phase 7: Soccerway Client (HTTP-first)

STEP 1 — Debug script:
CREATE `scripts/_debug_soccerway.py`:
- Load https://www.soccerway.com/matches/2026/05/13/ with requests
- Parse with BeautifulSoup4
- Dump: match table structure (team-a, team-b, score-time), league headers (group-head)
- Run it and study selectors

STEP 2 — Client implementation:
CREATE `src/bet/api_clients/soccerway.py`:
- class SoccerwayClient(BaseAPIClient) — HTTP-first, football only
- Methods: get_fixtures(date, sport), get_standings(competition_url), get_match_detail(match_url), get_fixture_stats(fixture_id), get_h2h(team1_id, team2_id)
- Rate limiter: add "soccerway-scraper": 100 to API_DAILY_LIMITS in rate_limiter.py
- Cache: betting/data/stats_cache/soccerway/

CRITICAL RULES:
- DEBUG FIRST, implement second — NEVER guess CSS selectors
- Use requests + BeautifulSoup, NOT Playwright (these sites work with HTTP)
- All methods return APIFixture dataclass (from api_football.py): `from .api_football import APIFixture`
- Fish shell — no inline Python in terminal
- Run debug scripts with `PYTHONPATH=src .venv/bin/python scripts/_debug_X.py`
```

---

## WAVE 2B — OddsPortal Playwright Client (Phase 4)

```
Implement Phase 4 from the plan at `betting/plans/api-clients-overhaul.plan.md` (lines 320-420).

READ the memory file `memories/repo/api-clients-overhaul-plan.md` for context.
READ `src/bet/api_clients/playwright_base.py` — your client extends PlaywrightBaseClient.
READ `src/bet/api_clients/flashscore.py` — reference implementation for Playwright patterns.

### OddsPortal Client (Playwright SPA — 0 matches via HTTP)

STEP 1 — Debug DOM FIRST:
CREATE `scripts/_debug_oddsportal.py`:
- Launch stealth Playwright (from playwright_stealth import Stealth; Stealth().apply_stealth_sync(page))
- Navigate to https://www.oddsportal.com/matches/football/
- Wait for SPA render (networkidle or specific selector)
- Dump: container hierarchy (first 100 elements), match row structure, odds cell format
- Navigate to a match detail page
- Dump: odds table with bookmaker names, odds values, market tabs
- Test GDPR/cookie banner dismissal
- Test with: football, tennis, basketball, hockey
- Run it: `PYTHONPATH=src .venv/bin/python scripts/_debug_oddsportal.py`
- Study output to discover REAL selectors — DO NOT GUESS

STEP 2 — Client implementation:
CREATE `src/bet/api_clients/oddsportal.py`:
- class OddsPortalClient(PlaywrightBaseClient) — extends the base you created in Phase 1
- _COOKIE_SELECTOR: discovered from debug script
- SPORT_PATHS: /matches/football/, /matches/tennis/, etc.
- Methods: get_fixtures(date, sport), get_odds(match_url), get_dropping_odds(sport), get_fixture_stats(fixture_id), get_h2h(team1_id, team2_id)
- JS extraction functions (like flashscore.py's _JS_EXTRACT_FIXTURES pattern)
- Rate limiter: "oddsportal-scraper" (already in rate_limiter.py at 50/day)
- Handle SPA pagination
- Parse decimal odds (EU locale)

CRITICAL RULES:
- PlaywrightBaseClient handles: _ensure_browser, _new_page, _dismiss_cookies, _handle_cloudflare, _load_page, close, circuit breaker
- You only implement: sport-specific JS extraction, URL construction, data parsing
- NEVER use page.content() for text — use page.inner_text('body')
- playwright-stealth v2: `Stealth().apply_stealth_sync(page)` — already handled by PlaywrightBaseClient
- Fish shell — no inline Python in terminal
```

---

## WAVE 2C — TotalCorner + Scores24 Playwright Clients (Phases 5+6)

```
Implement Phases 5 and 6 from the plan at `betting/plans/api-clients-overhaul.plan.md`.

READ the full plan (lines 420-500 for Phase 5, lines 500-580 for Phase 6).
READ the memory file `memories/repo/api-clients-overhaul-plan.md` for context.
READ `src/bet/api_clients/playwright_base.py` — your clients extend PlaywrightBaseClient.
READ `src/bet/api_clients/flashscore.py` — reference for Playwright JS extraction patterns.

### Phase 5: TotalCorner Client (football corners only)

STEP 1 — Debug DOM:
CREATE `scripts/_debug_totalcorner.py`:
- Stealth Playwright → https://www.totalcorner.com/match/today
- Wait for JS render, dump: match table, corner prediction cells, dangerous attack columns
- Navigate to detail: /match/{id}/corner/ — dump corner stats
- Run and study output

STEP 2 — Implement:
CREATE `src/bet/api_clients/totalcorner.py`:
- class TotalCornerClient(PlaywrightBaseClient) — football ONLY
- Methods: get_fixtures(date), get_corner_predictions(match_url), get_fixture_stats(fixture_id) [wraps corner_predictions], get_h2h() [returns empty — not supported]
- Corner data output: home_corner_avg, away_corner_avg, total_corner_avg, corner_handicap, over_under_line, dangerous_attacks_home/away, ht_corner_avg
- Rate limiter: add "totalcorner-scraper": 50 to API_DAILY_LIMITS in rate_limiter.py

### Phase 6: Scores24 Client (multi-sport deep data + trends)

STEP 1 — Debug DOM:
CREATE `scripts/_debug_scores24.py`:
- Stealth Playwright → https://scores24.live/en/soccer
- Wait for SPA render, dump: match listing, link format, date/time
- Navigate to detail: /en/soccer/m-{slug} → dump H2H, form, odds, trends
- Navigate to trends tab: dump trend categories, hit_count/sample_size
- Test with: soccer, tennis, basketball, ice-hockey, volleyball
- Run and study output

STEP 2 — Implement:
CREATE `src/bet/api_clients/scores24.py`:
- class Scores24Client(PlaywrightBaseClient) — multi-sport
- SPORT_PATHS: football→/en/soccer, tennis→/en/tennis, basketball→/en/basketball, hockey→/en/ice-hockey, volleyball→/en/volleyball
- Methods: get_fixtures(date, sport), get_match_detail(url), get_trends(url), get_fixture_stats(fixture_id), get_h2h(team1_id, team2_id)
- Trends are the UNIQUE VALUE — structured hit rates with hit_count/sample_size
- Rate limiter: add "scores24-scraper": 100 to API_DAILY_LIMITS in rate_limiter.py
- Cache: betting/data/stats_cache/scores24/{sport}/{slug}.json

CRITICAL RULES:
- DEBUG FIRST, implement second — discover selectors from real DOM
- PlaywrightBaseClient handles all browser lifecycle
- Use JS extraction pattern from flashscore.py (_JS_EXTRACT_* constants)
- NEVER use page.content() — use page.inner_text('body')
- Fish shell — no inline Python in terminal
```

---

## WAVE 3 — Registry + Rate Limiter + Verification (Phases 9+10)

```
Implement Phases 9 and 10 from the plan at `betting/plans/api-clients-overhaul.plan.md` (lines 770-900).

READ the memory file `memories/repo/api-clients-overhaul-plan.md` for context.

### Phase 9: Registry Updates

1. MODIFY `src/bet/api_clients/__init__.py`:
   Add registrations for 5 new clients with lazy import + try/except guards:
   - betexplorer → BetExplorerClient
   - oddsportal → OddsPortalClient
   - totalcorner → TotalCornerClient
   - scores24 → Scores24Client
   - soccerway → SoccerwayClient

2. MODIFY `src/bet/api_clients/rate_limiter.py`:
   Add to API_DAILY_LIMITS:
   - "totalcorner-scraper": 50
   - "scores24-scraper": 100
   - "soccerway-scraper": 100
   (betexplorer-scraper and oddsportal-scraper already exist)

3. MODIFY `src/bet/api_clients/unified.py`:
   Update SOURCE_PRIORITY to include all new clients:
   - football: flashscore → betexplorer → soccerway → espn
   - tennis: flashscore → scores24 → espn
   - basketball/hockey/volleyball: flashscore → betexplorer → scores24 → espn
   Add ODDS_PRIORITY: oddsportal → betexplorer (all sports)
   Add STATS_PRIORITY: football → totalcorner → flashscore

4. MODIFY `betting/sources/source-registry.md`:
   Update fallback chains to reflect new clients.

### Phase 10: Verify Debug Scripts

Run each debug script and verify it works:
- `PYTHONPATH=src .venv/bin/python scripts/_debug_betexplorer.py`
- `PYTHONPATH=src .venv/bin/python scripts/_debug_oddsportal.py`
- `PYTHONPATH=src .venv/bin/python scripts/_debug_totalcorner.py`
- `PYTHONPATH=src .venv/bin/python scripts/_debug_scores24.py`
- `PYTHONPATH=src .venv/bin/python scripts/_debug_soccerway.py`

Each must produce:
- Body text length > 500 (not blocked)
- Match rows identifiable
- Team names extractable

Then verify full registry:
```
PYTHONPATH=src .venv/bin/python -c "from bet.api_clients import CLIENT_REGISTRY; print(sorted(CLIENT_REGISTRY.keys()))"
```

CRITICAL: Fish shell — no inline Python in terminal, use temp .py scripts instead.
```

---

## WAVE 4 — Code Review

```
@tsh-code-reviewer Review ALL files changed/created in the API client layer overhaul.

Focus areas:
1. PlaywrightBaseClient (src/bet/api_clients/playwright_base.py) — correct extraction from flashscore.py, circuit breaker per-subclass isolation
2. FlashscoreClient refactor — no duplicated Playwright code, inheritance chain correct
3. unified.py — sport-aware routing, graceful degradation, lazy client init
4. 5 new clients — correct base class, proper selectors (not guessed), rate limiter integration
5. Dead client cleanup — _HOST_BROKEN flag, deprecation headers
6. Registry — all clients registered, import guards
7. Security — no path traversal in cache keys, no arbitrary URLs in page.goto(), proper resource cleanup

Files to review:
- src/bet/api_clients/playwright_base.py (NEW)
- src/bet/api_clients/flashscore.py (MODIFIED)
- src/bet/api_clients/unified.py (MODIFIED)
- src/bet/api_clients/betexplorer.py (NEW)
- src/bet/api_clients/oddsportal.py (NEW)
- src/bet/api_clients/totalcorner.py (NEW)
- src/bet/api_clients/scores24.py (NEW)
- src/bet/api_clients/soccerway.py (NEW)
- src/bet/api_clients/__init__.py (MODIFIED)
- src/bet/api_clients/rate_limiter.py (MODIFIED)
- scripts/api_clients/balldontlie.py (MODIFIED)
- scripts/api_clients/thesportsdb.py (MODIFIED)
- scripts/api_clients/api_tennis.py (MODIFIED)
- betting/sources/source-registry.md (MODIFIED)
```
