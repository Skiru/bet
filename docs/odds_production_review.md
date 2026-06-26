# Odds Production Review — Superbet First, Betclic Second

Review timestamp: 2026-06-26, Europe/Warsaw context.

## Decision

Current repository odds integration is not production-complete for the target betting workflow until these changes are applied and live-certified:

1. Add OddsPapi as the primary Superbet PL integration.
2. Add a Betclic-focused The Odds API path using bookmaker key `betclic_fr`.
3. Patch the source registry and bookmaker priority so Superbet precedes Betclic.
4. Replace/route merge logic through a market-safe merge that does not discard same-bookmaker markets.
5. Run local unit tests and, only with real keys, single-flight live probes that write evidence artifacts without exposing secrets.

## Public evidence used by the review

- The repo README targets disciplined small-bankroll betting on Betclic and covers Football, Volleyball, Basketball, Tennis, Hockey, CS2, Dota 2, and Valorant.
- Existing odds sources visible in public GitHub are `the-odds-api`, `odds-api-io`, and `api-football-odds`.
- Existing preferred bookmakers do not put Superbet first.
- Existing source registry does not include OddsPapi or a Betclic-specific The Odds API adapter.
- OddsPapi documents `Superbet PL` with bookmaker slug `superbet.pl`, JSON REST access, v4 host, 250 requests/month free tier, and WebSocket support.
- The Odds API documents Betclic as `betclic_fr` in EU and FR bookmaker lists and supports `bookmakers`, `regions`, `markets`, decimal odds, and ISO date format.
- odds-api.io has an official Python SDK and covers 250+ bookmakers, but the current repo client defaults to `Betclic PL,Bet365`, not Superbet-first.

## What this bundle implements

### New files

- `src/bet/api_clients/oddspapi.py`
  - `ODDSPAPI_API_KEY` required at runtime.
  - Default bookmaker: `superbet.pl`.
  - Uses `sportId=10` for football/soccer, per public OddsPapi example.
  - Adds timeout, bounded retry, `Retry-After`, JSON validation, env overrides.
  - Normalizes generic provider payloads and documented `bookmakerOdds -> markets -> outcomes -> players` payloads.

- `scripts/odds_sources/oddspapi.py`
  - Existing scanner-compatible source adapter.
  - Accepts current `fetch_odds(sport, date_from, date_to)` style.

- `src/bet/api_clients/the_odds_api_betclic.py`
  - `THE_ODDS_API_KEY` required at runtime.
  - Default bookmaker: `betclic_fr`.
  - Default region: `eu`.
  - Default markets: `h2h,spreads,totals`.
  - Adds timeout, bounded retry, `Retry-After`, JSON validation, date window params.

- `scripts/odds_sources/the_odds_api_betclic.py`
  - Existing scanner-compatible source adapter.
  - Accepts current `fetch_odds(sport, date_from, date_to)` style.

- `src/bet/odds_merge.py`
  - Market-safe merge by bookmaker + market + outcome + point.
  - Preserves same-bookmaker additional markets instead of dropping them.
  - Adds source provenance and bookmaker priority sort.

- Tests:
  - `tests/test_oddspapi_client.py`
  - `tests/test_the_odds_api_betclic_client.py`
  - `tests/test_odds_merge.py`
  - `tests/test_odds_source_adapters.py`

## Verification performed on this bundle

```text
cd /mnt/data/bet_odds_production_patch
PYTHONPATH=src:. pytest -q
9 passed

PYTHONPATH=src:. python -m compileall -q src scripts tests
PASS
```

## Important limitation

This bundle is unit/integration-boundary tested with fake transports. It is not live-certified against real OddsPapi/The Odds API keys in this environment. The agent must run live probes only in the local repo when keys are available and must redact all secrets from logs and artifacts.

## Required repository edits after copying files

Patch `scripts/odds_sources/__init__.py`:

```python
PREFERRED_BOOKMAKERS = [
    "superbet.pl", "superbet", "superbet_pl", "superbet-pl",
    "betclic_fr", "betclic", "betclic_pl",
    "bet365", "pinnacle", "unibet", "betfair",
]

SPORT_SOURCE_PRIORITY = {
    "football": ["oddspapi", "the-odds-api-betclic", "odds-api-io", "the-odds-api", "api-football-odds"],
    "tennis": ["oddspapi", "the-odds-api-betclic", "odds-api-io", "the-odds-api"],
    "basketball": ["oddspapi", "the-odds-api-betclic", "odds-api-io", "the-odds-api"],
    "hockey": ["oddspapi", "the-odds-api-betclic", "odds-api-io", "the-odds-api"],
    "volleyball": ["oddspapi", "odds-api-io"],
    "cs2": ["oddspapi", "odds-api-io"],
    "dota2": ["oddspapi", "odds-api-io"],
    "valorant": ["oddspapi", "odds-api-io"],
}
```

Patch `scripts/fetch_odds_multi.py` source registry:

```python
_SOURCE_MODULES = {
    "oddspapi": ("odds_sources.oddspapi", "SOURCE"),
    "the-odds-api-betclic": ("odds_sources.the_odds_api_betclic", "SOURCE"),
    "the-odds-api": ("odds_sources.the_odds_api", "SOURCE"),
    "odds-api-io": ("odds_sources.odds_api_io_source", "SOURCE"),
    "api-football-odds": ("odds_sources.api_football_odds", "SOURCE"),
}
```

Then replace calls/imports of legacy `merge_event_odds` if needed with `bet.odds_merge.merge_event_odds`, or port the improved logic into `scripts/odds_sources/__init__.py` with tests.

## Environment variables

```fish
set -x ODDSPAPI_API_KEY "..."
set -x ODDSPAPI_BOOKMAKERS "superbet.pl"
set -x ODDSPAPI_MARKETS "h2h,totals,spreads"

set -x THE_ODDS_API_KEY "..."
set -x THE_ODDS_API_BOOKMAKERS "betclic_fr"
set -x THE_ODDS_API_REGIONS "eu"
set -x THE_ODDS_API_MARKETS "h2h,spreads,totals"
```

## Live certification commands for agent

Use only after keys are configured:

```fish
cd /Users/mkoziol/projects/bet
set -x PYTHONPATH src:scripts
.venv/bin/python3 -m pytest -q tests/test_oddspapi_client.py tests/test_the_odds_api_betclic_client.py tests/test_odds_merge.py tests/test_odds_source_adapters.py
.venv/bin/python3 -m compileall src/bet/api_clients scripts/odds_sources tests

# Single-flight smoke, narrow window, no secret logging.
.venv/bin/python3 - <<'PY'
from scripts.odds_sources.oddspapi import SOURCE as superbet
from scripts.odds_sources.the_odds_api_betclic import SOURCE as betclic
for name, source in [("oddspapi", superbet), ("the-odds-api-betclic", betclic)]:
    try:
        events = source.fetch_odds("football", "2026-06-26", "2026-06-28")
        print({"source": name, "events": len(events), "sample_has_bookmakers": bool(events and events[0].get("bookmakers"))})
    except Exception as exc:
        print({"source": name, "error_type": type(exc).__name__, "message": str(exc)[:160]})
PY
```

## Next architecture step

After live certification, store provider evidence per run:

- request window, provider name, sport, event count, bookmaker count;
- no API key, no full raw payload if it contains betslip/deep-link sensitive data;
- normalized event sample hashes;
- provider quota headers if available;
- explicit status: `LIVE_CERTIFIED`, `NO_EVENTS`, `AUTH_FAILED`, `SCHEMA_DRIFT`, or `RATE_LIMITED`.
