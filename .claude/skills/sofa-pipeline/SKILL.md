---
name: sofa-pipeline
description: The shared contract for the `sofa` betting pipeline (Sofascore stats + Superbet prices) - its seven stages and their real names, every artifact and field, the arithmetic that turns a sample into a price bar, which file is the coupon and which only looks like one, and the traps that have cost money. Preloaded into every sofa agent. Use whenever running, auditing, analysing or repairing a sofa day, or when a stage name like DISCOVER or ENRICH is about to be used - those belong to the retired `simple` pipeline and there is no mapping between the two.
user-invocable: false
---

# The `sofa` pipeline — the contract

Two pipelines exist in this repository and they share no code.

| | `simple` (retired) | `sofa` (current) |
|---|---|---|
| code | `scripts/simple/`, `src/bet/simple_stats/` | `scripts/sofa/`, `src/bet/sofa/` |
| stats | bzzoiro, ESPN, highlightly | **Sofascore only** |
| prices | Superbet | Superbet |
| stages | DISCOVER → SUPERBET → ENRICH → MARKET_CONTEXT → TIPSTERS → ANALYZE | **BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON** |
| ranking number | `p_low` | `p_central` → `p_bar` |
| fixture key | `event_id`, a 64-char hash | `sofascore_event_id`, an integer |
| sports | football, tennis, baseball | football, tennis (`SPORT_IDS = {"football": 5, "tennis": 2}`) |
| product | `<date>_kupony.md` | **`KUPON_<date>.pdf`** |
| agentic config | `.claude/legacy/` | `.claude/agents/sofa-*` |

**There is no DISCOVER, no ENRICH, no ANALYZE, no TIPSTERS.** Reaching for
`simple`'s vocabulary is the single most common way to start a `sofa` session
wrong — it cost fifteen minutes on 2026-09-21 and is why this skill exists.
The source of truth is `DEFAULT_SEQUENCE` in `scripts/sofa/run_pipeline.py`.

## The stages, in one table

| # | stage | what it is | cost | artifact |
|---|---|---|---|---|
| E3 | **BOARD** | the day's fixtures, off Superbet's board. This is "discovery". | 1 HTTP request, < 1 s, no bridge | `01_board.json` |
| E4 | **RESOLVE** | attach a Sofascore event id to each board fixture | bridge, ~8 req/fixture | `02_fixtures.json` |
| E5 | **OFFER** (1st) | which markets carry a price at all | Superbet, fast | `04_offer.json` |
| E6 | **SAMPLES** | each side's last N matches per metric | bridge, ~12 req/fixture — **most of the run** | `03_samples.json` |
| E5 | **OFFER** (2nd) | refresh, so the bar meets a fresh price | Superbet | `04_offer.json` |
| E8 | **SHEET** | every rung priced: `p_central`, `p_bar`, verdict | offline | `05_sheet.json` |
| E9 | **COUPON** | VALUE singles + every exclusion, honouring `vetoes.json` | offline | `06_coupon.*`, `06_dropped.json` |
| — | **CONFIDENCE** | Bet Builders ranked by measured reliability, honouring `vetoes.json` | offline | `08_confidence.*` |
| — | **PDF** | **the coupon the operator stakes** | offline | `KUPON_<date>.pdf` |
| E10 | **SETTLE** | grade a finished day — D-1, never today | bridge | `07_settled.json` → `data/sofa.db` |
| E11 | **FIT** | re-fit constants from the settled table | offline | `config/sofa_*.json` |

OFFER runs **twice on purpose**: once before SAMPLES so sampling is not paid
for metrics nobody prices, once after so the bar is measured against a fresh
price. SETTLE and FIT are **not** in `DEFAULT_SEQUENCE`; both are deliberate,
separate steps.

Full per-stage detail, arguments and failure shapes: `references/stages.md`.

## The three things that get this wrong most often

### 1. `06_coupon.json` is not the coupon. The PDF is.

`06_coupon.json` holds VALUE singles, selected on price advantage. That selector's
measured record is bad — **−20.4% on 2026-09-20**, the same day the PDF's Bet
Builders returned **+8.2%**. Reporting `06_coupon` as "the coupon" inverts the
day. Three files on disk call themselves a coupon; only `KUPON_<date>.pdf` is
staked.

### 2. Selection is anti-selective against error in `p`.

`coupon.py` ranks on `surplus / required_odds` — the **relative** price
advantage, not the raw `surplus = offered − 1.10/p_bar`, which carries a `1/p`
term and ranked the day as a longshot scanner (F36) — and then breadth-first,
so each fixture's best row competes before any fixture's second. Every measure
of surplus still grows as `p` is overstated, so the rows most likely to be
wrong are the rows most likely to be picked. This is a property of the
mechanism, not a hypothesis about a particular day. **A surplus above +0.40 is
suspect by definition** — on a liquid market there is no free 40%. Take every
one apart by hand.

### 3. A stage saying `PARTIAL` is the normal shape of a healthy run.

`PARTIAL` on RESOLVE / OFFER / SAMPLES means some fixtures had gaps, which is
every day. Only `FAILED` stops you. Exit codes: `0 = OK`, `1 = PARTIAL`,
`2 = FAILED`.

## The arithmetic — the chain every row must be able to reproduce

```
prior   = league baseline, else global baseline          (config/sofa_league_baselines.json)
w_c     = n / (n + K_CENTRE)                             football 25, tennis 2
centre  = w_c·sample_mean + (1 − w_c)·prior              (or sample_mean when no baseline)

p_central:
    tennis + empirical metrics  -> p_empirical_raw(hits, n)   == the sample's own hit rate
    football counts             -> negative binomial around `centre`
    everything else             -> normal with a support floor at −0.5

p       = max(0.01, p_central − max(0, calibration_correction))
w       = n / (n + K_PRICE)                              K_PRICE = 10.0, status NOT_FITTED
p_bar   = w·p + (1 − w)·market_p                         market_p = power-devigged Superbet price
required_odds = 1.10 / p_bar                             1.10 is the LEAN margin
verdict = VALUE when offered_odds > required_odds
```

Three things that look like defects and are not:

1. `centre` is the mean **after shrinkage**. Comparing it to the raw sample
   mean always shows a "gap"; that gap is `K_CENTRE` doing its job.
2. `ladder_centre` / `ladder_sigma` describe **the bookmaker's ladder**, not
   our distribution. `ladder_sigma` around 0.003 is normal.
3. Tennis uses the empirical frequency, so `p_central` **equals** the sample's
   hit rate. Football does not, and should not — a gap above ~15 pp means the
   league prior, not the team, is doing the work.

Derivation rules, the confidence chain and what cannot be re-derived:
`references/arithmetic.md`.

## Artifacts

```
runs/sofa/<date>/
  01_board.json        BoardFixture[]    superbet_event_id, sport, side_a/b, kickoff_utc
  02_fixtures.json     Fixture[]         sofascore_event_id, identity, BOTH clocks, referee, round
  03_samples.json      FixtureSamples[]  per metric: side_a / side_b / h2h observations, gaps;
                                         players: per-footballer samples (F54)
  04_offer.json        FixtureOffer[]    priced rungs + fetched_at_utc, unmapped_markets
  05_sheet.json        SheetRow[]        every rung priced, with verdict and notes
  06_coupon.json/.md   Coupon            VALUE singles — NOT the coupon
  06_dropped.json                        every VALUE row that did not make it, with a reason
  07_settled.json      D-1 only          graded rows; also written to data/sofa.db
  08_confidence.json/.md                 legs + Bet Builders
  KUPON_<date>.pdf                       ★ the product
  08_confidence_wariant.json/.md         the operator's variant (--profile wariant): floor 0.65, x >= 0.90
  KUPON_<date>_WARIANT.pdf               the variant's PDF — NOT the coupon; settled beside it (7d)
  vetoes.json          Veto[]            the analyst's only channel. `[]` on most days.
```

Every field with its type and meaning: `references/artifacts.md`.

## `vetoes.json` — the analyst's only channel

A veto **removes** a row. Nothing in this pipeline can promote one. It is read
by **COUPON and CONFIDENCE both** (the second since 2026-09-21 — before that a
veto reached the singles file and left the identical rung standing as a leg of
the Bet Builder the PDF stakes). Write it **after SHEET, before COUPON**.

```json
[{"sofascore_event_id": 15275920, "market": "corners_total", "subject": null,
  "line": 9.5, "direction": "OVER",
  "reason_class": "SAMPLE_UNINFORMATIVE",
  "reason": "seven of ten observations predate the manager change on 12 Aug"}]
```

`market`/`subject`/`line`/`direction` are all nullable and `null` means **all
of them** — the normal shape, because a sample that does not describe the
fixture is broken at every rung. `reason_class` ∈ `SAMPLE_UNINFORMATIVE |
CONTEXT | PRICE | OTHER`. A veto that matches no row is printed as
`UNMATCHED_VETO` by both stages and counted in their summaries; it is never
swallowed.

## Running it

```bash
# the interpreter matters: .venv has two. `python` is 3.12 and runs the
# pipeline, `pip` belongs to 3.14 and installs where nothing can import.
.venv/bin/python -m pip install <pkg>          # correct
.venv/bin/pip install <pkg>                    # silently useless

.venv/bin/python scripts/sofa/check_bridge.py                                   # first, always
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only BOARD --run-id <id>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --from-stage RESOLVE --run-id <id>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <d>
# the operator's variant (0.65 / price up to 10% below fair), beside the coupon, never instead of it
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <d> --profile wariant
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <d> --profile wariant
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <d>
```

Sofascore answers **403 to every non-browser client**. Everything except BOARD
and the offline stages goes through a real browser tab (`check_bridge.py`).
`ok: true` alone is not enough — a dead tab still reports ok; read the poll
age. **Set `SOFA_TARGET_RPS` from `measure_bridge_capacity.py`, never above
its plateau** — 3.9 req/s on three tabs (2026-09-22); above it you buy queue,
not speed. **Never lower `MIN_INTERVAL_MS`**: that is the per-connection pace.
The binding limit is the browser, not Sofascore — a hidden, throttled tab drops
a run to ~0.5 req/s and `check_bridge.py` now names it.

## Hard rules

- Never invent a number, a fixture, a price or an availability.
- Never print a combined / Bet Builder / parlay price outside what
  `confidence.py` computed, and never present `odds_if_product` as a price —
  Superbet does not price a slip as the product of its legs; the measured
  markup is 8.8–19.6%.
- No stake sizing, no automated placement.
- Never read, echo or log `.env` values.
- Never re-fit constants mid-day. `fit_constants.py` is outside the sequence
  on purpose: re-fitting breaks comparability with yesterday.
- A settled result is a fact about the day, not about the decision that made
  it. Never let "it won" into the reasoning for the next one.

The traps that have actually cost something: `references/traps.md`.

## Deeper documentation in the repository

This skill is the contract. The repository carries the long form, and it is
kept in step with the code:

| | |
|---|---|
| `docs/sofa/PIPELINE.md` | every stage, field, gate and constant, with the file each lives in |
| `docs/sofa/RUNBOOK.md` | the operator's sequence, timings, and "what to do when…" |
| `docs/sofa/AGENTIC_FLOW.md` | commands, agents, skills, handoffs and the veto contract |
| `docs/sofa/VERIFY_PROTOCOL.md` | the adversarial verification protocol |
| `docs/sofa/CONFIG.md` | config files, fitted constants, the settle→fit loop |
| `docs/sofa/REFERENCE.md` | the Sofascore API and why the bridge exists |
| `docs/sofa/history/` | dated run reports and findings — historical, may be stale |

Those documents are Polish, this configuration is English, and that boundary
is deliberate. `docs/legacy/` describes the retired `simple` pipeline: take no
stage name, quantity or artifact name from it.
