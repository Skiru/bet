# bet — `sofa` betting pipeline

One pipeline is in service: **`sofa`**. Statistics come from **Sofascore**,
prices from **Superbet**, and the product of a day is a single file:

```
runs/sofa/<date>/KUPON_<date>.pdf
```

Football and tennis only (`SPORT_IDS = {"football": 5, "tennis": 2}`).
Everything else in this repository is retired and is kept only because its
artifacts and database rows are still on disk.

## The day, in one line

```bash
.venv/bin/python scripts/sofa/check_bridge.py                                   # 1. the browser bridge
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <YYYY-MM-DD>
```

or, from Claude Code, **`/sofa-day`** — which also settles D-1, runs the two
sport analysts, merges their vetoes, rebuilds and verifies.

**Start here: [`docs/sofa/RUNBOOK.md`](docs/sofa/RUNBOOK.md)** — the operator's
sequence, the timings and what to do when a stage complains.

## Stages

```
BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON
                                          ↘ CONFIDENCE → PDF   ★ the product
                    deliberately separate:  SETTLE → FIT
```

`BOARD` is discovery, and it asks the **bookmaker** what is bettable today.
`OFFER` runs twice on purpose. `SETTLE` and `FIT` are not in the daily
sequence. The source of truth for the order is `DEFAULT_SEQUENCE` in
`scripts/sofa/run_pipeline.py`.

**There is no `DISCOVER`, `ENRICH`, `ANALYZE`, `MARKET_CONTEXT` or `TIPSTERS`
stage.** Those belong to the retired `simple` pipeline; the two share no code
and no vocabulary, and there is no mapping between them.

## Documentation

| | |
|---|---|
| [`docs/sofa/`](docs/sofa/) | the current pipeline — runbook, full flow, agentic orchestration, verification protocol, config |
| [`docs/legacy/`](docs/legacy/) | the retired `simple` / S0–S10 / tipster / multisport work. Historical record; describes no running code |
| [`CLAUDE.md`](CLAUDE.md) · [`ARCHITECTURE.md`](ARCHITECTURE.md) | working agreement for agents, and where the code lives |

## Layout

```
src/bet/sofa/          the pipeline (26 modules, no imports from the old tree)
scripts/sofa/          CLI entry points: run_pipeline.py, run_*.py, audit_*.py, fit_*.py
config/sofa_*.json     fitted constants, league baselines, calibration curves
userscripts/           the browser userscript that makes Sofascore answerable
tests/sofa/            699 tests, offline
data/sofa.db           settled rows — the only state carried between days
runs/sofa/<date>/      one directory per betting day
.claude/               agents, commands and skills for the current pipeline
```

Retired and not in service: `src/bet/simple_stats/`, `scripts/simple/`,
`src/bet/tipsters/`, `legacy/`, `.claude/legacy/`, `.kilo/legacy/`.

## Three things that have cost money

1. **`06_coupon.json` is not the coupon — the PDF is.** The VALUE-singles
   selector returned −20.4% on 2026-09-20; the PDF's Bet Builders returned
   +8.2% the same day.
2. **`PARTIAL` is the normal shape of a healthy run.** Only `FAILED` stops you
   (exit codes: 0 OK, 1 PARTIAL, 2 FAILED).
3. **Sofascore answers 403 to every non-browser client.** Everything except
   BOARD, OFFER and the offline stages goes through a real browser tab, and
   `SOFA_TARGET_RPS` must never be raised.

## Development

```bash
.venv/bin/python -m pytest tests/sofa -q
.venv/bin/python -m ruff check src/bet/sofa scripts/sofa
.venv/bin/python -m mypy --strict src/bet/sofa scripts/sofa
```

`.venv/bin/python` is 3.12 and runs the pipeline; `.venv/bin/pip` belongs to
3.14 — install with `.venv/bin/python -m pip`. `ruff` and `mypy` carry a
pre-existing backlog outside `sofa`; judge a run by whether it points at a line
you wrote.
