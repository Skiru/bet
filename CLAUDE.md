# Working agreement — `bet`

## The only pipeline in service is `sofa`

Sofascore statistics, Superbet prices, football and tennis. The product of a
day is **`runs/sofa/<date>/KUPON_<date>.pdf`**.

```
BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON
                                          ↘ CONFIDENCE → PDF   ★ the product
                    deliberately separate:  SETTLE → FIT
```

**There is no `DISCOVER`, `ENRICH`, `ANALYZE`, `MARKET_CONTEXT` or `TIPSTERS`
stage.** Those are the retired `simple` pipeline's vocabulary. The two share no
code and no stage names, and there is no mapping between them. Reaching for the
old words is the most common way to start a session wrong — it cost fifteen
minutes on 2026-09-21. `sofa`'s discovery stage is **BOARD**, and it asks the
bookmaker, not a stats provider.

Source of truth for the order: `DEFAULT_SEQUENCE` in
`scripts/sofa/run_pipeline.py`.

## Entry points

| you want | use |
|---|---|
| a full betting day | `/sofa-day [dzisiaj\|wczoraj\|YYYY-MM-DD]` |
| the per-sport read over an existing sheet | `/sofa-analyze` |
| coupon + PDF from artifacts on disk | `/sofa-rebuild` |
| adversarial verification of a built day | `/sofa-verify` |
| settle D-1 and decide about constants | `/sofa-settle` |
| price a slip the operator screenshotted | the `bet-slip-audit` skill |

Agents: `sofa-runner`, `sofa-analyst-football`, `sofa-analyst-tennis`,
`sofa-verifier`, `sofa-settler`, `sofa-market-scout`. Skills preloaded into
them: `sofa-pipeline`, `sofa-analysis-core`, `football-analysis`,
`tennis-analysis`.

Full orchestration contract: `docs/sofa/AGENTIC_FLOW.md`.

## Commands

```bash
.venv/bin/python scripts/sofa/check_bridge.py                                    # always first
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --from-stage RESOLVE --run-id <id>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <d>

.venv/bin/python -m pytest tests/sofa -q
.venv/bin/python -m ruff check src/bet/sofa scripts/sofa
.venv/bin/python -m mypy --strict src/bet/sofa scripts/sofa
```

`.venv/bin/python` is 3.12 and runs the pipeline. `.venv/bin/pip` belongs to
3.14 — install with `.venv/bin/python -m pip`, or the import still fails after
a successful-looking install.

Exit codes: **0 OK, 1 PARTIAL, 2 FAILED**. `PARTIAL` on RESOLVE / OFFER /
SAMPLES is the normal shape of a healthy run; only `FAILED` stops you.

## Hard rules

- **`06_coupon.json` is not the coupon. The PDF is.** The VALUE-singles
  selector returned −20.4% on 2026-09-20 while the PDF returned +8.2% the same
  day. Reporting the wrong file inverts the day.
- **Never invent** a number, a fixture, a price or an availability.
- **Never print a combined / Bet Builder / parlay price** outside what
  `confidence.py` computed, and never present `odds_if_product` as a price —
  Superbet does not price a slip as the product of its legs (measured markup
  8.8–19.6%).
- **No stake sizing, no automated placement.** The stake decision is the
  operator's.
- **Never read, echo or log `.env` values.**
- **Never re-fit constants mid-day.** `fit_constants.py` is outside the
  sequence on purpose; re-fitting breaks comparability with yesterday.
- **Never strip `UNFITTED_CONSTANTS`** from a row or a report to make it read
  better.
- **Set `SOFA_TARGET_RPS` from a measurement, never above it.** The old rule
  here was "never raise", written after a burst peaking at 550 req/s coincided
  with Sofascore closing `/api/v1/` on 2026-09-17. That burst was **one**
  `curl_cffi` client with 100 workers and no browser. It is not the shape the
  bridge produces, so the rule is now the measurement:
  `scripts/sofa/measure_bridge_capacity.py` ramps the rate and reports the
  plateau. Measured 2026-09-22 with three tabs: **3.9 req/s**, reached already
  at a target of 4, with zero non-200 in 360 requests. Asking for 14 delivered
  the same 3.9 and took the bridge round trip from 605 ms to 5,603 ms — above
  the plateau you buy queue, not speed, and queue costs `STALE_PRICE`.
- **Never lower `MIN_INTERVAL_MS`** in `userscripts/sofascore-bridge.user.js`.
  That is the *per-connection* pace, and it is the one number that makes a tab
  look like a person. Capacity comes from opening more tabs, not from making
  one tab faster.
- **The browser, not Sofascore, is the binding limit.** Three tabs served
  3.9 req/s, not the 8.6 the 350 ms floor allows, because Chrome throttles
  hidden tabs; a throttled tab takes ~40 s to claim one job and answers the
  same routes in ~2,000 ms instead of ~175 ms. `check_bridge.py` warns above
  600 ms. Keep the tabs visible before touching any rate.
- A settled result is a fact about the day, **not about the decision that made
  it**. "It won" never enters the reasoning for the next one.

## Working style in this repo

- **Evidence or it did not happen.** A claim about the pipeline names the file
  and the line, or the artifact and the field. An unmeasured statement is
  marked as a suspicion, not stated as a fact.
- **Every fix ships a test.** `tests/sofa/` is offline and fast; there is no
  reason to skip it.
- **A skipped check is named.** Silence about a check reads as a passed check.
  If a run went clean, say a guard was *not tested* — never that it works.
- **Check a subagent's numbers** when you can check them locally. One
  adversarial pass over a single agent file once found eighteen errors, two of
  which inverted the argument.
- **Agent definitions and skills load at session start.** A rewritten agent
  cannot be exercised in the session that wrote it; say so rather than claiming
  the fix is live.
- Live runs are deliberate: they cost hours of bridge time and they are visible
  to a third party's production API.

## Language

Operator-facing documentation in `docs/sofa/` is **Polish** (so are the
analysts' reports). Code, tests and the `.claude/` contracts are **English**.
Keep that boundary.

## What is retired

`src/bet/simple_stats/`, `scripts/simple/`, `src/bet/tipsters/`, `legacy/`,
`.claude/legacy/`, `.kilo/legacy/`, `docs/legacy/`. They are kept because their
artifacts and database rows are still on disk. Do not take stage names,
quantities (`p_low`, CALL/LEAN/WEAK/DROP) or artifact names from them, and do
not "restore" one without reading `docs/legacy/README.md` first.
