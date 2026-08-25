# legacy/ — the S0–S10 stack

Reference material, not an execution path. Nothing here runs, and nothing in
`src/bet/simple_stats/**` imports it.

The live pipeline is `scripts/simple/run_pipeline.py` (DISCOVER → ENRICH → ANALYZE).
See [docs/MORNING.md](../docs/MORNING.md).

## Why it is here

The S0–S10 stack stopped being runnable before this move: `orchestrator.py`,
`run_daily_pipeline.py` and 13 other files carry unresolved `<<<<<<< HEAD` merge
markers committed to `main` and raise `SyntaxError` on import. Moving them out of
`src/` and `scripts/` makes that state visible instead of implied, and stops the
default `pytest` run from tripping over them.

It is kept rather than deleted because the design work in it is real: the market
model, the risk gates, the tipster parsers and the provider integrations are
worth reading before rebuilding any equivalent.

## What is where

| Path | Was | Contains |
|---|---|---|
| `pipeline_steps/` | `scripts/pipeline_steps/` | S0–S10 runners, `run_daily_pipeline.py`, the sharding runner |
| `bet_pipeline/` | `src/bet/pipeline/` | orchestrator, readiness contracts, agent work orders, market probability inputs |
| `bet_builder/` | `src/bet/builder/` | Same-event Bet Builder engine and models |
| `scripts/` | `scripts/` | V5 delivery, certification and audit scripts |
| `tests/` | `tests/` | 57 test files that only cover the above (flattened names: `tests/security/x.py` → `security__x.py`) |

`pytest` is configured with `testpaths = ["tests"]`, so `legacy/tests/` is out of
the default run. To run them anyway (they will fail — that is the point):

```bash
python3 -m pytest legacy/tests -q --continue-on-collection-errors
```

## What did NOT move, and why

**Provider clients are live.** `src/bet/api_clients/**` is shared: the simple
pipeline uses ESPN, Highlightly, SportDB, api-football, tennis-abstract and the
rest through exactly those modules. If you came here looking for provider code,
it is in `src/bet/api_clients/`, not here.

Also still live and shared:

- `src/bet/pipeline/contracts/`, `sharding/`, `sports/`, `state.py`,
  `structured_output.py` — these parse, and other code depends on them
- `src/bet/models/`, `src/bet/db/`, `src/bet/discovery/`, `src/bet/stats/`

`src/bet/pipeline/` therefore still exists. Only its six broken modules moved.

## Coupling that was cut during the move

`bet.models` imported `StrictBaseModel` and `hash_canonical_json` from
`bet.pipeline.contracts`, and every provider client imports `bet.models`. So
importing *any* provider loaded `bet/pipeline/__init__.py` — including the S0–S10
manifest validator, which raises when the manifest's script paths do not exist.
Moving `pipeline_steps/` made the live pipeline fail to start.

Both classes moved to neutral ground:

- `src/bet/strict_model.py` — `StrictBaseModel`
- `src/bet/canonical_json.py` — the JSON canonicaliser

`bet.pipeline.contracts.base` and `bet.pipeline.contracts.canonical_json` now
re-export them, so existing imports still work. `src/bet/simple_stats/**` now
imports zero `bet.pipeline` modules, verified by import trace.

## Still broken, still in `tests/`

Eight test files under `tests/` carry `<<<<<<< HEAD` markers *inside the test
file itself* and fail to parse. They were left in place: two of them
(`test_c2_sharding_and_acquisition.py`, `test_t2_sharding_lifecycle.py`) cover
`bet.pipeline.sharding`, which is live and shared, so moving them to `legacy/`
would hide tests of running code. They need the conflict resolved, not relocating.

```bash
grep -rl '^<<<<<<< ' tests/
```

## Running anything in here

Don't, without resolving the merge markers first:

```bash
grep -rl '^<<<<<<< ' legacy/ src/
```

`config/pipeline_manifest.json` still describes this stack and now points at
`legacy/pipeline_steps/...`.
