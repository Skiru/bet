# bet — `sofa` betting pipeline

One pipeline is in service: **`sofa`**. Statistics come from **Sofascore**,
prices from **Superbet**, and the product of a day is a single file:

```
runs/sofa/<date>/KUPON_<date>.pdf
```

One coupon for every sport on it: football and tennis
(`SPORT_IDS = {"football": 5, "tennis": 2}` on the board), and since
2026-10-05 08:30Z hockey, basketball, volleyball and CS2 (from the SHADOW /
CS2 snapshots). Confidence comes from the statistics alone; the price is only
the betting condition.

## The day, in one line

```bash
.venv/bin/python scripts/sofa/check_bridge.py                                   # 1. the browser bridge
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <YYYY-MM-DD>
```

or, from Claude Code, **`/sofa-day`** — which also settles D-1 and records the
ledger, builds the measured sports' legs (SPORT_IDENTITY, SPORT_CONFIDENCE),
assembles the one coupon (COUPON_ASSEMBLY → `11_coupon.json`), runs the
analysts (football, tennis, one per measured sport) on the best 30 positions
and every printed builder leg, merges their vetoes and reads, rebuilds and
verifies.

**Start here: [`docs/sofa/RUNBOOK.md`](docs/sofa/RUNBOOK.md)** — the operator's
sequence, the timings and what to do when a stage complains.

## Stages

```
BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON
                                          ↘ CONFIDENCE ─────────────┐
   SHADOW / CS2 → SPORT_IDENTITY → SPORT_CONFIDENCE ────────────────┤
                                   COUPON_ASSEMBLY (11_coupon.json) → PDF   ★ the product
   in a rebuild, before CONFIDENCE:  FIXTURE_CHECK
                    deliberately separate:  SETTLE → FIT
```

`BOARD` is discovery, and it asks the **bookmaker** what is bettable today.
`OFFER` runs twice on purpose. `DEFAULT_SEQUENCE` ends at COUPON; CONFIDENCE
and the PDF are scripts, and FIXTURE_CHECK, SPORT_IDENTITY, SPORT_CONFIDENCE
and COUPON_ASSEMBLY are stage modules outside the sequence. `SETTLE` and `FIT`
are not in the daily sequence. The source of truth for the order is `DEFAULT_SEQUENCE` in
`scripts/sofa/run_pipeline.py`.

**There is no `DISCOVER`, `ENRICH`, `ANALYZE`, `MARKET_CONTEXT` or `TIPSTERS`
stage.** Those belong to the retired `simple` pipeline; the two share no code
and no vocabulary, and there is no mapping between them.

## Documentation

| | |
|---|---|
| [`docs/sofa/`](docs/sofa/) | the current pipeline — runbook, full flow, agentic orchestration, verification protocol, config |
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

Only `sofa` lives here: the retired `simple` pipeline and everything else was
deleted 2026-10-05 (in git history; every branch in `data/archive/branches_2026-10-05.bundle`).

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
