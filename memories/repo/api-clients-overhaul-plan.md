# API Client Layer Overhaul — Context & Delegation Guide

## Created: 2026-05-13
## Plan: `betting/plans/api-clients-overhaul.plan.md` (1000 lines, 10 phases)

## What This Is
A comprehensive overhaul of `src/bet/api_clients/` to:
1. Extract shared Playwright boilerplate into `PlaywrightBaseClient`
2. Fix `unified.py` — add sport-aware routing with graceful degradation
3. Create 5 NEW clients for missing data sources
4. Clean up 3 dead legacy clients
5. Update registry + rate limiter + source-registry.md

## Architecture After Overhaul
```
BaseAPIClient (ABC) — base_client.py
├── APISportsClient (HTTP + x-apisports-key) — EXISTING, NO CHANGES
│   ├── APIFootballClient, APIBasketballClient, APIHockeyClient, APIVolleyballClient
├── ESPNClient (HTTP, no key) — EXISTING, NO CHANGES
├── BetExplorerClient (HTTP-first + BeautifulSoup) ← NEW Phase 3
├── SoccerwayClient (HTTP-first + BeautifulSoup) ← NEW Phase 7
├── PlaywrightBaseClient (stealth + circuit breaker) ← NEW Phase 1
│   ├── FlashscoreClient (REFACTORED to extend PlaywrightBaseClient)
│   ├── OddsPortalClient ← NEW Phase 4
│   ├── TotalCornerClient ← NEW Phase 5
│   └── Scores24Client ← NEW Phase 6
└── UnifiedAPIClient (composite router) — FIXED Phase 2
```

## Key Files
- `src/bet/api_clients/flashscore.py` (834 lines) — REFERENCE implementation for Playwright patterns
- `src/bet/api_clients/base_client.py` (255 lines) — ABC with retry, cache, rate limiting
- `src/bet/api_clients/unified.py` (107 lines) — currently brittle, only Flashscore→ESPN
- `src/bet/api_clients/rate_limiter.py` — already has betexplorer-scraper (50), oddsportal-scraper (50)
- `src/bet/api_clients/__init__.py` — CLIENT_REGISTRY + get_client() factory
- `scripts/stealth_utils.py` — shared UA rotation, block detection helpers

## Patterns From flashscore.py (Reference for ALL Playwright Clients)
- **Stealth**: `from playwright_stealth import Stealth; Stealth().apply_stealth_sync(page)`
- **Cookie dismiss**: `page.click(selector, timeout=2500)` with try/except
- **Cloudflare**: check `page.inner_text('body')` for "Just a moment"
- **Block detection**: body text < 500 chars = blocked
- **Circuit breaker**: class-level `_failures` counter, opens after 3, 300s cooldown, `type(self)._failures` for per-subclass isolation
- **JS extraction**: `page.evaluate(js_code)` with structured JS constants
- **Page loading**: `page.goto(url, wait_until="domcontentloaded", timeout=30000)` + wait_for_timeout
- **Cleanup**: `close()` + `__enter__/__exit__/__del__`
- **NEVER**: use `page.content()` for text extraction (use `inner_text('body')` instead)

## Dead Legacy Clients (Phase 8 cleanup)
- `scripts/api_clients/balldontlie.py` — _HOST_BROKEN=True, v1 API deprecated
- `scripts/api_clients/thesportsdb.py` — _HOST_BROKEN=True, 97.8% fail rate
- `scripts/api_clients/api_tennis.py` — _HOST_BROKEN=True, NXDOMAIN
- `scripts/adapters/` — directory NO LONGER EXISTS (deleted in previous refactors)

## Execution Waves
| Wave | Agent | Phases | Scope |
|------|-------|--------|-------|
| Wave 1A | tsh-software-engineer | Phase 1+2 | PlaywrightBaseClient + unified.py |
| Wave 1B | tsh-software-engineer | Phase 8 | Dead client cleanup |
| Wave 2A | tsh-software-engineer | Phase 3+7 | HTTP clients: BetExplorer + Soccerway |
| Wave 2B | tsh-software-engineer | Phase 4 | OddsPortal (Playwright SPA) |
| Wave 2C | tsh-software-engineer | Phase 5+6 | TotalCorner + Scores24 (Playwright) |
| Wave 3 | tsh-software-engineer | Phase 9+10 | Registry + verification |
| Wave 4 | tsh-code-reviewer | All | Code review |

## Critical Rules
- SKIP Flashscore and Sofascore (already implemented)
- Debug DOM FIRST → implement SECOND (for Playwright clients)
- All clients return `APIFixture` / `APIMatchStats` dataclasses
- All clients use `RateLimiter` from `src/bet/api_clients/rate_limiter.py`
- HTTP-first when possible (BetExplorer, Soccerway) — Playwright only for JS SPAs
- Circuit breaker per-subclass: `type(self)._failures` not `cls._failures`
- Fish shell — no inline Python, no bash loops in terminal
- playwright-stealth v2: `Stealth().apply_stealth_sync(page)` NOT `stealth_sync(page)`
