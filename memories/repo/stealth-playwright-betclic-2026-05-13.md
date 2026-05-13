# Stealth Playwright + Betclic HTML Analysis — 2026-05-13

## What Was Done

### 1. Stealth Infrastructure (`scripts/stealth_utils.py`) — NEW
- Shared module: `USER_AGENTS` (6 Chrome 134-136 UAs), `BROWSER_ARGS`, `is_actually_blocked()`, `random_delay_sync/async()`, `create_context_sync/async()`
- **Key insight:** `is_actually_blocked()` uses size-aware detection — real blocks are HTTP 403/429 + <15KB pages; large 400KB+ pages containing "datadome" in JS bundles are FALSE POSITIVES

### 2. Stealth Fixes Applied to 8 Files
- `stealth_fetcher.py` — retry loop (3 attempts, context rotation per attempt), stealth_utils imports
- `daily_odds_warmup.py` — hockey URL added, context rotation every 2 pages, retry with backoff, stealth_utils imports
- `verify_betclic_odds.py` — context rotation every 3 picks, backoff retries on match pages, Cloudflare challenge wait
- `data_enrichment_agent.py` — stealth Playwright fallback in `fetch()` and `_fetch_stealth()`, retry with context rotation
- `sofascore.py` — retry loop (2 attempts), context rotation, `is_actually_blocked()`, stealth_utils imports
- `flashscore.py` — retry loop (2 attempts), use `inner_text('body')` not `page.content()` for feed text, proper error re-raising
- `_test_betclic_stealth.py` — NEW comprehensive test across 5 sports + match detail + fingerprint check

### 3. Betclic HTML Deep Analysis
- Cached 4 listing pages (football, tennis, basketball, hockey) + 3 match detail pages (football, basketball, tennis)
- Volleyball: 0 events at time of analysis (off-season/late hours)
- Analysis scripts: `_analyze_betclic_html.py` (listings), `_analyze_betclic_match.py` (match detail), `_fetch_betclic_match.py` (fetcher)

### 4. DOM Selector Specification (`specifications/betclic-dom-selectors.md`) — NEW
- Complete selector map for listing + match detail pages
- URL patterns: sport listing, league, match (with ID patterns)
- Market tabs per sport (Football: 8 tabs discovered — MyCombi, Top, Wynik, Strzelcy, Gole, Metoda gola, Wynik/Handicap, Statystyki)
- Full standard market catalog for all 5 sports (Polish → English mapping)
- Parser implementation notes (pagination, tab rendering, odds parsing, Angular SPA caveats)

### 5. Parser Prompt (`specifications/betclic-parser-prompt.txt`) — NEW
- Ready for new chat session to build `scripts/parse_betclic_html.py`

## Key Technical Findings

### playwright-stealth v2 API
```python
from playwright_stealth import Stealth
await Stealth().apply_stealth_async(page)  # async
Stealth().apply_stealth_sync(page)          # sync
```

### Block Detection (Size-Aware)
- Real block: HTTP 403 + 3-5KB HTML with "zablokowany"/"access denied"
- False positive: HTTP 200 + 400KB+ page with "datadome" in bundled JS
- Solution: Only flag as blocked if content < 15KB for 403/429, or < 10KB for keyword matches

### Betclic Angular SPA
- All content client-rendered — needs `wait_for_timeout(3000-4000)` after navigation
- Only active tab renders odds in DOM (default: "Top" tab)
- Max ~20 events per listing page; per-league pages needed for full coverage
- Match IDs: 15-16 digit pattern in URLs (`-m1112013945405440`)
- Team names split: `span.ellipsis` + `span.clip` (use `get_text()` to merge)

## Files Changed/Created
- **NEW:** `scripts/stealth_utils.py`, `scripts/_test_betclic_stealth.py`, `scripts/_analyze_betclic_html.py`, `scripts/_analyze_betclic_match.py`, `scripts/_fetch_betclic_match.py`
- **NEW:** `specifications/betclic-dom-selectors.md`, `specifications/betclic-parser-prompt.txt`
- **NEW (test helpers):** `scripts/_check_stealth_api.py`, `scripts/_check_stealth_api2.py`, `scripts/_test_stealth_quick.py`, `scripts/_test_sofa_json.py`, `scripts/_test_enrich_stealth.py`, `scripts/test_stealth_api.py`, `scripts/test_sofascore_api.py`
- **MODIFIED:** `scripts/stealth_fetcher.py`, `scripts/daily_odds_warmup.py`, `scripts/verify_betclic_odds.py`, `scripts/data_enrichment_agent.py`, `src/bet/api_clients/sofascore.py`, `src/bet/api_clients/flashscore.py`
