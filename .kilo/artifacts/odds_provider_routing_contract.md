# Odds Provider Routing Contract

This contract defines the production-grade routing priorities and statuses for all available odds provider integrations.

---

## 1. Mapped Routing Status Definitions

All providers within the betting pipeline must resolve to one of the following exact routing statuses:

- **`PRIMARY_ACTIVE`**: The core, most reliable provider used first for fixtures, odds, and line discovery.
- **`SECONDARY_ACTIVE`**: A valid backup provider used for validation, cross-checking, or falling back when primary limits are reached.
- **`SHADOW_ONLY`**: An integrated provider that operates in a silent/shadow mode to gather statistics and double-check bets, but has no final say in production candidates.
- **`CONFIG_MISSING`**: Config key or credentials are empty or missing.
- **`AUTH_FAILED`**: Provider rejected authentication (e.g. HTTP 401).
- **`QUOTA_EXHAUSTED`**: Out of request credits or rate limited (e.g. HTTP 429).
- **`NOT_IMPLEMENTED`**: No adapter code or client implementation exists.
- **`PROVIDER_ZERO_RESPONSE`**: Adapter is online, but returned empty list of results.
- **`PRODUCTION_SELECTABLE_FALSE`**: The provider cannot under any circumstance be configured as an active production target.

---

## 2. Active Provider Assignments

Based on the June 2026 key audits, refresh probes, and coverage checks, the active routing layout is established as:

### A. OddsAPI.io (`odds-api-io`)
- **Routing Status:** `PRIMARY_ACTIVE`
- **Priority:** `1`
- **Production Selectable:** `True`
- **Recheck Status:** **PASS** (150 active tennis events, 63 Wimbledon events, and valid bookmaker odds fetched)
- **Role:** Primary source for all 5 core sports, esports (CS2/Dota2/Valorant), and value bets.

### B. The Odds API (`odds-api`)
- **Routing Status:** `SECONDARY_ACTIVE`
- **Priority:** `2`
- **Production Selectable:** `True`
- **Recheck Status:** **PASS** (Fresh key resolved via configuration, 10 events successfully fetched via cost-safe probe)
- **Role:** Secondary fallback for football, basketball, hockey, and tennis.

### C. OddsPapi (`odds-papi`)
- **Routing Status:** `SHADOW_ONLY`
- **Priority:** `3`
- **Production Selectable:** `False` (Blocked by `PRODUCTION_SELECTABLE_FALSE` boundary safety)
- **Recheck Status:** **PASS** (Client implementation and 23 tests fully green, shadow gate enforced)
- **Role:** Silent shadow reference validation for Superbet PL odds comparison.
