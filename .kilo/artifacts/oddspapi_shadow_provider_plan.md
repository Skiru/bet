# OddsPapi Shadow Provider Integration Plan

**Plan Date:** 2026-06-29  
**Auditor:** Kilo (gemini-3.5-flash)  
**ODDSPAPI_CODE_STATUS:** `SHADOW_CLIENT_ONLY`  
**ODDSPAPI_SHADOW_READY:** `true`  
**ODDSPAPI_PRODUCTION_SELECTABLE:** `false`  

---

## 1. Inventory & Codebase Analysis

Our scan and testing confirm the following components exist and are fully verified:
- **OddsPapi Client:** Implemented in `src/bet/api_clients/oddspapi.py` with built-in retry backoffs, JSON safety guards, and HTTP transport injection.
- **OddsPapi Adapter:** Implemented in `scripts/odds_sources/oddspapi.py` exporting the standard scanner `SOURCE` interface.
- **Config / Key Loader:** Integrated in `OddspapiConfig` and the live probe script.
- **Precedence / Access Gates:** Guarded in `src/bet/odds_provider_access.py` and `tests/test_odds_provider_access.py`.
- **Merge Logic:** Merges and prioritizes `oddspapi` data in `src/bet/odds_merge.py`.
- **Tests:** A suite of 23 pytest specifications (including schema validations, credential checks, and adapter tests) are **100% green**.

---

## 2. Official Docs API Plan

### A. Endpoints Mapping
- **Sports Endpoint:** Mapped via `SPORT_SLUG_MAP` to fetch active sports. Matches `sportId=10` for Football.
- **Bookmakers Endpoint:** Controlled via `bookmaker_filter` (default `superbet.pl`).
- **Tournaments Endpoint:** Optional filter within `fetch_fixtures` or passed as `league` parameter.
- **Odds Endpoint:** Mapped via `fetch_fixture_odds` using `/odds` endpoint with parameters `fixtureId` and `verbosity=3`.

### B. Normalization Strategy
- **Fixture / Tournament ID Normalization:** Mapping logic maps string event and competition titles into unified `NormalizedFixture` objects.
- **Bookmaker Odds Shape:** Adapts nested structures of the documented format:
  `bookmakerOdds -> markets -> outcomes -> players`
- **Fields Mapped:**
  - `price` (decimal odds format, e.g. `1.95`)
  - `line` or `point` (handicap handicap lines, over/under threshold totals, e.g. `-0.5`, `2.5`)
  - `changedAt` / `updatedAt` (parsed to UTC timestamps)
  - `bookmaker` (mapped to `superbet_pl`)
- **Market ID Normalization:**
  - `101` $\rightarrow$ `h2h`
  - Over/Under $\rightarrow$ `totals`
  - Handicaps / Spreads $\rightarrow$ `spreads`
- **Sport ID Mapping:**
  - `football` / `soccer` $\rightarrow$ `"10"` (soccer id in OddsPapi public docs)
  - Other sports dynamically mapped or configured via environment variables.

### C. Request and Quota Safety
- Built-in max-retry bounds ($N=2$, configurable up to 5).
- Bounded time window constraint (`_validate_fixtures_window` limits fixture requests to a max of 48 hours unless explicitly bypassed).
- Backoff jitter to prevent burst requests.

---

## 3. Shadow Integration Path & Verification

OddsPapi is configured as **`SHADOW_ONLY`** inside `src/bet/odds_provider_access.py`.
- To enable Shadow Mode, the developer sets the environment variable `ODDSPAPI_ENABLE_SHADOW=1`.
- Production activation requires **Explicit Adapter Certification** (`ODDSPAPI_LIVE_CERTIFIED=1` and `ODDSPAPI_ENABLE_LIVE=1`), which is currently locked off.
- This ensures OddsPapi acts as a quiet reference layer to double-check and validate main line selections without injecting risk or silent failures into active automated placement.
