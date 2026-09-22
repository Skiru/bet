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
- **`MIN_INTERVAL_MS = 350` in the userscript is the safety mechanism, and it
  is never lowered.** It paces each *connection*, which is what keeps a tab
  looking like a person. Capacity comes from opening more tabs, never from
  making one tab faster. The 2026-09-17 incident was one `curl_cffi` client
  with 100 workers peaking at 550 req/s and no browser in the path; the bridge
  cannot produce that shape.
- **Open the windows with `launch_bridge_browser.py`, and they do NOT have to
  be visible.** Chrome clamps `setTimeout` in a hidden page to >=1000 ms, and
  the userscript's `pace()` waits on exactly that to hold `MIN_INTERVAL_MS`.
  So a background tab silently ran at ~1 req/s instead of 2.86, and the only
  symptom was a run that took four times as long. Three launch flags remove
  it; with five **minimised** windows the round trip p90 went from 9,436 ms to
  224 ms. They are process-creation flags, so Chrome must be fully quit first
  — the script refuses to launch rather than open a window whose flags were
  silently dropped. The old "tabs must be visible, three non-overlapping
  windows" rule was a workaround for this bug and is retired.
- **`SOFA_MAX_CONCURRENCY` is the window count — not a tuning knob, and never
  below it.** Measured 2026-09-22, five windows, 60 requests a step, zero
  non-200:

  | `SOFA_MAX_CONCURRENCY` | achieved | p50 | p90 |
  |---|---|---|---|
  | 3 | 0.15 req/s | 20,138 ms | 20,162 ms |
  | **5** | **11.67 req/s** | **354 ms** | **620 ms** |
  | 8 | 11.72 req/s | 668 ms | 704 ms |
  | 12 | 11.66 req/s | 1,010 ms | 1,056 ms |

  Throughput saturates at the window count and never moves again; only latency
  grows, which is queue depth and costs `STALE_PRICE`. Below it the failure is
  not gradual — two idle tabs fall back into a 20 s `/pull` and the bridge
  collapses 78x. `p50 = 354 ms` at five *is* `MIN_INTERVAL_MS`: the tab is
  pacing itself and nothing else is the limit. Change it together with
  `--windows`, and re-run `measure_bridge_capacity.py`.
- **`SOFA_TARGET_RPS` must sit above what the tabs can serve.** Five windows
  at 350 ms is 5 x 2.86 = 14.3 req/s, so the bucket is 20. Starving it is
  worse than opening it: if the bucket is the limiter the tabs idle between
  jobs and pay the same poll cycle. Defaults are 20 and 5.
- **The browser is the binding limit, not Sofascore.** Nothing measured across
  2026-09-22 was ever refused by Sofascore — every collapse that day was our
  own configuration or our own measurement.
- **Measure the round trip, not the wall clock around the client.** The token
  bucket sits *inside* `client.event_statistics()`, so timing that call
  reports our own rate limiting as if it were browser latency — it read a flat
  ~2,050 ms while the bridge was answering in 216 ms, and sent a whole
  diagnosis the wrong way. `measure_bridge_capacity.py` now reports `p50 net`
  from the request log, and gives every ramp its own `run_id`.
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
