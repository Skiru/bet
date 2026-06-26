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

## Public Branch Remediation A Certification

- Branch: `feat/odds-superbet-betclic-production-v1`
- Previous public commit: `91fb722c7db390e2468dee115398bed608b8c0b6`
- Worktree: `/Users/mkoziol/projects/bet/.kilo/worktrees/plume-homburg`
- `config/api_keys.json` is local-only and must never be committed.
- Pytest command: `.venv/bin/python -m pytest -q tests/test_oddspapi_client.py tests/test_the_odds_api_betclic_client.py tests/test_odds_merge.py tests/test_odds_source_adapters.py`
- Pytest result: `10 passed in 0.54s`.
- Broader odds pytest command: `.venv/bin/python -m pytest -q tests/test_fetch_odds_multi.py tests/test_odds_evaluator.py tests/test_odds_merge.py tests/test_odds_source_adapters.py tests/test_oddspapi_client.py tests/test_the_odds_api_betclic_client.py`
- Broader odds pytest result: `37 passed in 0.56s`.
- Compileall command: `.venv/bin/python -m compileall src/bet/api_clients src/bet/odds_merge.py scripts/odds_sources scripts/odds_live_probe_superbet_betclic.py tests`
- Compileall result: `PASS`.
- Live probe command: `.venv/bin/python scripts/odds_live_probe_superbet_betclic.py`
- Live probe status: exit `0`; OddsPapi `FAIL_AUTH_OR_PLAN`, The Odds API Betclic `NOT_RUN_MISSING_KEYS`.
- Evidence file: `reports/odds_provider_live_probe_superbet_betclic_v1.json`
- OddsPapi key source: `config/api_keys.json`.
- The Odds API key source/status: `missing` / `NOT_RUN_MISSING_KEYS`.
- Live certified: `false`.
- Live certification reason: `OddsPapi` returned `HTTP 403`, classified as `FAIL_AUTH_OR_PLAN`; this preserved live evidence but did not satisfy live certification.

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

## Remediation B2 Absolute Credential Path Verification

- Branch: `feat/odds-superbet-betclic-production-v1`
- Base commit before remediation: `be1f223908c2b151de54567e40f0d4b276dc8974`
- Absolute credential path used by the live probe: `/Users/mkoziol/projects/bet/.kilo/worktrees/plume-homburg/config/api_keys.json`
- Secret handling: the key value was never printed, committed, or written to evidence; the probe records only `key_source`, `key_file_path_used`, and `key_present`.
- OddsPapi key source result: `absolute_config_api_keys_json`
- Env-before-import guard: `scripts/odds_live_probe_superbet_betclic.py` now sets `ODDSPAPI_API_KEY` before dynamically importing `scripts.odds_sources.oddspapi`, because the adapter `SOURCE` path can read env-backed config at import time.
- Account endpoint diagnostic: `/v4/account` returned HTTP `200` with a successful redacted account probe.
- Billable calls attempted after the account probe: `1`
- Live probe outcome: the credential path is proven, but the follow-up OddsPapi odds request returned HTTP `403`, so the remaining blocker is provider access/plan scope rather than local credential discovery.
- The Odds API Betclic status during this remediation: `NOT_RUN_MISSING_KEYS`
- Evidence file: `reports/odds_provider_live_probe_superbet_betclic_v1.json`
- Targeted pytest: `.venv/bin/python -m pytest -q tests/test_oddspapi_client.py tests/test_the_odds_api_betclic_client.py tests/test_odds_merge.py tests/test_odds_source_adapters.py tests/test_fetch_odds_multi.py tests/test_odds_live_probe_credentials.py` -> `30 passed`
- Broader odds pytest: `.venv/bin/python -m pytest -q tests/test_odds_live_probe_credentials.py tests/test_fetch_odds_multi.py tests/test_odds_source_adapters.py tests/test_oddspapi_client.py tests/test_odds_merge.py tests/test_the_odds_api_betclic_client.py tests/test_odds_evaluator.py` -> `41 passed`
- Compileall: `.venv/bin/python -m compileall src/bet/api_clients src/bet/odds_merge.py scripts/odds_sources scripts/odds_live_probe_superbet_betclic.py tests` -> `PASS`

## Remediation C Provider Contract Diagnostics

- Branch: `feat/odds-superbet-betclic-production-v1`
- Base commit: `fc5e7188b9f016f891a24346f1dce9c6ab73b455`
- Public merge export fixed: `scripts/odds_sources/__init__.py` now routes `merge_event_odds` through `bet.odds_merge.merge_event_odds` when available and keeps a market-safe fallback that merges by bookmaker -> market -> outcome + point.
- Official OddsPapi flow implemented: `src/bet/api_clients/oddspapi.py` now follows `account -> fixtures -> odds?fixtureId=...`, keeps query-parameter auth, and gates the undocumented sport-level `/v4/odds` shortcut behind `ODDSPAPI_ENABLE_LEGACY_SPORT_ODDS=1`.
- Targeted pytest: `env PYTHONPATH=src:scripts:. .venv/bin/python -m pytest -q tests/test_oddspapi_client.py tests/test_the_odds_api_betclic_client.py tests/test_odds_merge.py tests/test_odds_source_adapters.py tests/test_fetch_odds_multi.py tests/test_odds_live_probe_credentials.py` -> `40 passed in 0.17s`.
- Broader odds pytest: `env PYTHONPATH=src:scripts:. .venv/bin/python -m pytest -q tests/test_odds_live_probe_credentials.py tests/test_odds_source_adapters.py tests/test_oddspapi_client.py tests/test_fetch_odds_multi.py tests/test_odds_merge.py tests/test_the_odds_api_betclic_client.py tests/test_odds_evaluator.py` -> `51 passed in 0.18s`.
- Compileall: `env PYTHONPATH=src:scripts:. .venv/bin/python -m compileall src/bet/api_clients src/bet/odds_merge.py scripts/odds_sources scripts/odds_live_probe_superbet_betclic.py tests` -> `PASS`.
- Account diagnostic result: `/v4/account` returned `HTTP 200`, `current_subscription_active=true`, `request_count=12`, `request_limit=250`, with a redacted summary only.
- Billable calls attempted: `1`.
- Final OddsPapi status: `FAIL_ACCESS_FIXTURES`.
- The Odds API Betclic status: `NOT_RUN_MISSING_KEYS`.
- Live certified: `false` because the documented `fixtures` discovery step is forbidden even after a successful account diagnostic, so the provider remains access-gated.
- Evidence file: `reports/odds_provider_live_probe_superbet_betclic_v1.json`.
- Deployment posture: branch is safe only as `shadow/disabled` provider wiring until a plan/key with documented Superbet fixtures access is available.
- Secret handling: `config/api_keys.json` remains local-only and untracked.
