---
name: sofa-pipeline
description: The shared contract for the `sofa` betting pipeline (Sofascore stats + Superbet prices) - the seven-stage DEFAULT_SEQUENCE (BOARD..COUPON) and the stages outside it (CONFIDENCE, FIXTURE_CHECK, SPORT_IDENTITY, SPORT_CONFIDENCE, COUPON_ASSEMBLY, PDF, SETTLE, FIT, CS2 / SHADOW), every artifact and field, the arithmetic (confidence from the statistics alone since 2026-10-05; the price only as the betting condition), which file is the coupon (11_coupon.json -> KUPON_<d>.pdf) and which only looks like one, and the traps that have cost money. Preloaded into every sofa agent. Use whenever running, auditing, analysing or repairing a sofa day, or when a stage name like DISCOVER or ENRICH is about to be used - those belong to the retired `simple` pipeline and there is no mapping between the two.
user-invocable: false
---

# The `sofa` pipeline — the contract

Two pipelines exist in this repository and they share no code.

| | `simple` (retired) | `sofa` (current) |
|---|---|---|
| code | deleted 2026-10-05 (git history) | `scripts/sofa/`, `src/bet/sofa/` |
| stats | bzzoiro, ESPN, highlightly | **Sofascore only** |
| prices | Superbet | Superbet |
| stages | DISCOVER → SUPERBET → ENRICH → MARKET_CONTEXT → TIPSTERS → ANALYZE | **BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON**, then the stages outside the sequence (below) |
| ranking number | `p_low` | `confidence` (the measured lower bound); `p_bar` only in the old priced selector |
| fixture key | `event_id`, a 64-char hash | `sofascore_event_id`, an integer; a coupon block is `group_key` = `sofa:<sofascore_event_id>` |
| sports | football, tennis, baseball | football, tennis from the board and the sheet (`SPORT_IDS = {"football": 5, "tennis": 2}`); hockey / basketball / volleyball / CS2 on the same coupon since 2026-10-05 08:30Z (`epochs.SPORTS_ON_COUPON_FROM_UTC`) through SPORT_CONFIDENCE |
| product | `<date>_kupony.md` | **`KUPON_<date>.pdf`**, rendered from `11_coupon.json` |
| agentic config | deleted 2026-10-05 | `.claude/agents/sofa-*` |

**There is no DISCOVER, no ENRICH, no ANALYZE, no TIPSTERS.** Reaching for
`simple`'s vocabulary is the single most common way to start a `sofa` session
wrong — it cost fifteen minutes on 2026-09-21 and is why this skill exists.
The source of truth is `DEFAULT_SEQUENCE` in `scripts/sofa/run_pipeline.py`
(seven entries, ending at COUPON) and `STAGE_MODULES` beside it (what
`--only` can reach).

## The flow

```
DEFAULT_SEQUENCE (run_pipeline.py):
  BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON (06_coupon.json: the old priced selector, not the coupon)

after it, football + tennis:
  [FIXTURE_CHECK, in a rebuild] → CONFIDENCE (run_confidence.py) → 08_confidence.json
the measured sports:
  --only SHADOW, --only CS2 (fresh snapshots) → SPORT_IDENTITY → SPORT_CONFIDENCE → 08_confidence_sports.json
the coupon:
  COUPON_ASSEMBLY (build_coupon.py) → 11_coupon.json → PDF (build_coupon_pdf.py) → KUPON_<d>.pdf ★ + 12_printed.json

deliberately separate:  SETTLE (D-1) → FIT (between days, never mid-day)
```

## The stages, in one table

| # | stage | what it is | cost | artifact |
|---|---|---|---|---|
| E3 | **BOARD** | the day's fixtures, off Superbet's board. This is "discovery". | 1 HTTP request, < 1 s, no bridge | `01_board.json` |
| E4 | **RESOLVE** | attach a Sofascore event id to each board fixture | bridge, ~8 req/fixture | `02_fixtures.json` |
| E5 | **OFFER** (1st) | which markets carry a price at all | Superbet, fast | `04_offer.json` |
| E6 | **SAMPLES** | each side's last N matches per metric | bridge, ~12 req/fixture — **most of the run** | `03_samples.json` |
| E5 | **OFFER** (2nd) | refresh, so the price is fresh | Superbet | `04_offer.json` |
| E8 | **SHEET** | every rung: `p_central` (stats-only: no price in it), `forecast_p`, and the old priced bar `p_bar` / verdict | offline | `05_sheet.json` |
| E9 | **COUPON** | the old VALUE-singles selector (priced) + every exclusion — **not the coupon** | offline | `06_coupon.*`, `06_dropped.json` |
| — | **FIXTURE_CHECK** | in a rebuild, before CONFIDENCE: `/event/{id}` for printed matches and moved clocks | bridge (UNVERIFIED without it) | `fixture_status.json` |
| — | **CONFIDENCE** | football / tennis legs + Bet Builders by measured reliability, honouring `vetoes.json` and `reads.json` | offline | `08_confidence.*` |
| — | **SPORT_IDENTITY** | pins the Sofascore event of every hockey / basketball / volleyball / CS2 Superbet event before it starts | bridge, 1 req/match | `sport_fixtures.json` |
| — | **SPORT_CONFIDENCE** | the measured sports' legs, confidence from the calibrated model | offline | `08_confidence_sports.json` |
| — | **COUPON_ASSEMBLY** | the one coupon: order, blocks, positions, locks, builders B1.., `removed_by_reads` | offline | `11_coupon.json` / `.md` |
| — | **PDF** | **the coupon the operator stakes** | offline | `KUPON_<date>.pdf`, `12_printed.json` |
| E10 | **SETTLE** | grade a finished day — D-1, never today | bridge | `07_settled.json` → `data/sofa.db`, `07_settled_printed.json`, `07_settle_skips.json` |
| E11 | **FIT** | re-fit constants from the settled table | offline | `config/sofa_*.json` |
| — | **CS2** / **CS2_SETTLE** | CS2 price snapshot / grade D-1 against Sofascore — the measurement | Superbet / bridge | `runs/sofa/cs2/<date>/` |
| — | **SHADOW** / **SHADOW_SETTLE** | hockey, basketball, volleyball: the same | Superbet / bridge | `runs/sofa/shadow/<sport>/<date>/` |

`STAGE_MODULES` holds the sequence plus SETTLE, CS2, CS2_SETTLE, SHADOW,
SHADOW_SETTLE, FIXTURE_CHECK, SPORT_IDENTITY, SPORT_CONFIDENCE and
COUPON_ASSEMBLY (all reachable with `--only`). **CONFIDENCE and PDF are not in
it** — they are run as `run_confidence.py` / `build_coupon_pdf.py`; never
write `--only CONFIDENCE`. The CS2 / SHADOW snapshots are inputs to
SPORT_IDENTITY / SPORT_CONFIDENCE; their own settled files stay a measurement
and grade the sport legs against the pinned id.

OFFER runs **twice on purpose**: once before SAMPLES so sampling is not paid
for metrics nobody prices, once after so the coupon meets a fresh price.

Full per-stage detail, arguments, exit codes and failure shapes:
`references/stages.md`.

## The things that get this wrong most often

### 1. The coupon is `11_coupon.json` → `KUPON_<date>.pdf`. Nothing else.

On a stats-only day (a day >= 2026-10-05 built at or after 07:15Z,
`bet.sofa.epochs.STATS_ONLY_FROM_UTC`) the coupon artifact is
`runs/sofa/<d>/11_coupon.json`, and the PDF refuses to render without it.
`08_confidence.json` is then the football / tennis **input** to it (and the
input of SETTLE and the refit), not the coupon — it lacks the sport legs, the
positions and the locks. Every reader of "what was printed" goes through
`confidence.coupon_artifact(run_dir)`: 11 where it exists, else 08 (older
days). `12_printed.json` is what the PDF actually printed.

`06_coupon.json` is not the coupon either, on any day. It holds VALUE singles
selected on price advantage — **−20.4% on 2026-09-20**, the same day the
PDF's Bet Builders returned **+8.2%**. Reporting it as "the coupon" inverts
the day.

### 2. Confidence comes without the price.

In the stats-only epoch SHEET keeps the price out of `p_central` (no tennis
ladder centre, no rating blended with the price, no empirical shrink to the
rung's price, no handicap centre on the ladder), and the leg's `confidence`
is the calibration curve's lower bound of that number. The rating is printed
beside it as `forecast_p` ("model", `forecast_source` `football_rating` /
`tennis_rating` / `score_model` / `cs2_engine` / null) — uncalibrated, never a
gate, never a sort key. `model_p` (= `p_central`) is unchanged.

The price is **only the betting condition**: x = confidence × odds >= 0.90,
ladder margin <= 15%, odds >= 1/0.9202 (`ODDS_TOO_LOW`), not started
(`KICKED_OFF`, earliest clock), fresh price (`STALE_PRICE`).
`MAX_DISAGREEMENT` and `UNREACHABLE_BAR` are off; a moved price re-prices the
leg (x at the fresh odds) instead of `PRICE_MOVED_SINCE_SHEET`. Floor 0.70; a
WATCH or NO_BET read removes the leg. Bet Builders are chosen and ordered by
`combined_probability`, stakeable at combined p × odds after haircut >= 0.90
(`stakeable_rule: "x>=0.90"`). The coupon is ordered by confidence, then the
earlier start, legs of one match together (`confidence.coupon_order`) — no
price and no EV in the key. CONFIDENCE refuses (exit 2) a SHEET not built
under the rule, so a rule rebuild starts at SHEET.

**K13:** where a market × direction bucket is too thin for its own curve
(`thin_by_market_direction`), it now caps the two-direction `by_market` curve
too — the result is the lower of the two Wilson lower bounds.

### 3. The priced numbers are still on the sheet — and still mean the old thing.

`p_bar`, `required_odds`, `surplus`, `edge` and the VALUE verdict are still
computed in SHEET and COUPON, and `audit_coupon.py` still audits their
arithmetic. They are the old priced selector's numbers: they never enter the
coupon, its order or its confidence. That selector is anti-selective by
construction — `coupon.py` ranks on `surplus / required_odds`, and every
measure of surplus grows as `p` is overstated. **A surplus above +0.40 is
suspect by definition.**

### 4. A stage saying `PARTIAL` is the normal shape of a healthy run.

`PARTIAL` on RESOLVE / OFFER / SAMPLES means some fixtures had gaps, which is
every day; on SPORT_CONFIDENCE / COUPON_ASSEMBLY it can mean a sport is
`NOT_CALIBRATED` or unidentified (football / tennis still built). Only
`FAILED` stops you. Exit codes: `0 = OK`, `1 = PARTIAL`, `2 = FAILED`.

## The arithmetic — the chain every row must be able to reproduce

```
prior   = league baseline, else global baseline          (config/sofa_league_baselines.json)
w_c     = n / (n + K_CENTRE)                             football 15, tennis 5 (refit 2026-10-03)
centre  = w_c·sample_mean + (1 − w_c)·prior              (or sample_mean when no baseline)
centre  = 0.5·rating + 0.5·centre                        football rows with a FOOTBALL_RATING note (W_FOOTBALL_RATING, not the price)

p_central (stats-only epoch):
    football counts             -> negative binomial around `centre`
    tennis rated / empirical    -> the sample's own estimator, no price (the rating goes to forecast_p)
    everything else             -> normal with a support floor at −0.5

confidence = Calibration.realised(market, p_central, sport, direction, klass) -> its realised_lo95   (K13 cap: min with the thin direction bucket)
x          = confidence × offered_odds   >= 0.90 to print; margin <= 15%
builder    stakeable when combined_probability × odds_after_haircut >= 0.90
sport leg  confidence = realised_lo95 of the calibrated bucket of the model p (config/sofa_sport_confidence_calibration.json)

the old priced selector (SHEET / COUPON only, not the coupon):
p       = max(0.01, p_central − max(0, calibration_correction))
w       = n / (n + K_PRICE)                              K_PRICE = 10.0, status NOT_FITTED
p_bar   = w·p + (1 − w)·market_p                         market_p = power-devigged Superbet price
required_odds = 1.10 / p_bar ; verdict = VALUE when offered_odds > required_odds
```

Three things that look like defects and are not:

1. `centre` is the mean **after shrinkage**. Comparing it to the raw sample
   mean always shows a "gap"; that gap is `K_CENTRE` doing its job.
2. `ladder_centre` / `ladder_sigma` describe **the bookmaker's ladder**, not
   our distribution. `ladder_sigma` around 0.003 is normal.
3. A football `p_central` does not equal its sample's hit rate, and should
   not — a gap above ~15 pp means the league prior, not the team, is doing
   the work (football `MODEL_ABOVE_OWN_SAMPLE`, gap > 0.15, is an automatic
   WATCH). On rows built before the stats-only epoch a priced tennis
   `p_central` was pulled onto the price (`TENNIS_RATING`,
   `P_SHRUNK_TO_PRICE`); re-derive an old row from its own notes.

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
  05_sheet.json        SheetRow[]        every rung, with epoch, forecast_p, the old priced verdict and notes
  06_coupon.json/.md   Coupon            old VALUE singles (priced) — NOT the coupon
  06_dropped.json                        every VALUE row that did not make it, with a reason
  fixture_status.json                    FIXTURE_CHECK: per event status + fresh start (K12/K14)
  08_confidence.json/.md                 football / tennis legs + Bet Builders — input to 11 on a stats-only day
  sport_fixtures.json                    SPORT_IDENTITY: pinned Sofascore ids of the measured sports' events
  08_confidence_sports.json              SPORT_CONFIDENCE: hockey / basketball / volleyball / CS2 legs
  11_coupon.json/.md                     ★ the coupon artifact (COUPON_ASSEMBLY)
  KUPON_<date>.pdf                       ★ the product
  12_printed.json                        what the PDF printed; the next rebuild locks from it
  read_requests.json                     the operator's extra positions / legs to read
  vetoes.json          Veto[]            a broken sample / context: removes everywhere. `[]` on most days.
  reads.json           LegRead[]         one KEEP / WATCH / NO_BET per read leg (analyst, verifier)
  07_settled.json      D-1 only          graded rows; also written to data/sofa.db
  07_settled_printed.json                printed legs with no sheet row, graded here, never in the DB
  07_settle_skips.json                   why a row was not graded; refunds (MOVED_BEYOND_VOID, AWARDED)

runs/sofa/cs2/<date>/, runs/sofa/shadow/<sport>/<date>/     the measurement, beside the day
  snapshots.jsonl, settled.json          CS2 / SHADOW, CS2_SETTLE / SHADOW_SETTLE

runs/sofa/ledger/results.jsonl           one row per (date, variant), record_results.py; read with audit_ledger.py
```

Every field with its type and meaning: `references/artifacts.md`.

## `vetoes.json`, `reads.json`, `read_requests.json` — the only channels into the product

A veto **removes** a row. Nothing in this pipeline can promote one. It is read
by **COUPON and CONFIDENCE both**, and by COUPON_ASSEMBLY for the sport legs.
Write it **after SHEET, before COUPON**.

```json
[{"sofascore_event_id": 15275920, "market": "corners_total", "subject": null,
  "line": 9.5, "direction": "OVER",
  "reason_class": "SAMPLE_UNINFORMATIVE",
  "reason": "seven of ten observations predate the manager change on 12 Aug"}]
```

`market`/`subject`/`line`/`direction` are all nullable and `null` means **all
of them**. `reason_class` ∈ `SAMPLE_UNINFORMATIVE | CONTEXT | PRICE | OTHER`;
a `CONTEXT` veto also carries `context`, graded in `audit_settlement` section
7e. A veto's `direction` is only OVER / UNDER, so for one side of a sport leg
write a NO_BET read instead. A veto that matches no row is `UNMATCHED_VETO`;
it is never swallowed.

`reads.json` (`LegRead` in `src/bet/sofa/contracts.py`, strict,
`extra="forbid"`): `{sofascore_event_id, market, subject, line, direction,
verdict, author, reason, context, period}`, `verdict` ∈ `KEEP | WATCH |
NO_BET`, `author` ∈ `analyst | verifier`. For a sport leg `market` is the
family, `direction` is the side (`T1|T2|DRAW|ODD|EVEN|YES|NO` or an exact
score "3:1") and `period` the period / quarter / set / CS2 map (None = all).
In the stats-only epoch NO_BET and WATCH (and the automatic football
`MODEL_ABOVE_OWN_SAMPLE`) are applied **at the end of the chain**: a leg that
passed every gate and a read removed goes to `removed_by_reads` in
`11_coupon.json`, graded on its own (`audit_settlement` 7i, ledger
`removed:reads`), never in the coupon's result. KEEP removes nothing.

Who reads: `confidence.legs_requiring_read` — the first 30 unlocked positions
of `11_coupon.json` (`READ_REQUIRED_SINGLES`), every printed builder leg, and
whatever `read_requests.json` asks for (`{"position": n}` or `{"group_key":
"sofa:<id>", "market"?, "line"?, "direction"?}`, each with `requested_by` and
`at_utc`; prefer `group_key` — positions shift after a rebuild).
`audit_variants` C3 requires an analyst read on that set. The PDF's
`STALE_CONFIDENCE` guard does look at `reads.json`, and `STALE_COUPON` at
`read_requests.json`: after a reads change re-run CONFIDENCE, then
COUPON_ASSEMBLY, then the PDF.

## Running it

```bash
# the interpreter matters: .venv has two. `python` is 3.12 and runs the
# pipeline, `pip` belongs to 3.14 and installs where nothing can import.
.venv/bin/python -m pip install <pkg>          # correct
.venv/bin/pip install <pkg>                    # silently useless

.venv/bin/python scripts/sofa/ensure_bridge.py                                  # first, always: brings the bridge up, then check_bridge
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only BOARD --run-id <id>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --from-stage RESOLVE --run-id <id>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_fixture_check.py --date <d>        # in a rebuild, after OFFER, before CONFIDENCE (bridge)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <d> [--dry-run]   # THE rebuild: stale OFFER / SHADOW (horizon) / CS2 first, SHEET only if its epoch is refused, then FIXTURE_CHECK .. PDF + audits; never the stages by hand
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only SHADOW
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only CS2
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_identity.py --date <d>       # bridge; after the fresh snapshots
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_confidence.py --date <d>     # no bridge
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon.py --date <d>             # COUPON_ASSEMBLY -> 11_coupon.json
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <d>         # KUPON_<d>.pdf + 12_printed.json
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <d>             # the priced 05/06 arithmetic
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <d>           # C1-C3, U1-U3 on 11
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settle_identity.py --from <d> --to <d>   # after the D-1 settle
PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --from <D-8> --to <D-1>      # the ledger, after every settle; exit 0 even with legs pending, 1 = MISMATCH / unreadable file
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <d> --to <d>             # one table per variant and epoch, never pooled
```

Sofascore answers **403 to every non-browser client**. Everything except BOARD
and the offline stages goes through a real browser tab (`ensure_bridge.py`,
then `check_bridge.py`). `ok: true` alone is not enough — a dead tab still
reports ok; read the poll age. **`SOFA_TARGET_RPS` (20) must sit ABOVE what
the tabs can serve** (5 windows x 2.86 = 14.3 req/s) — starving it is worse
than opening it; **`SOFA_MAX_CONCURRENCY` (5) equals the window count and is
never below it.** **Never lower `MIN_INTERVAL_MS`**: that is the
per-connection pace. Open the windows with `launch_bridge_browser.py` (or
`ensure_bridge.py`); they need not be visible. The binding limit is the
browser, not Sofascore. A 403 stops FIXTURE_CHECK and SPORT_IDENTITY at once
(no retry).

## Hard rules

- Never invent a number, a fixture, a price or an availability.
- Never print a combined / Bet Builder / parlay price outside what
  `confidence.py` computed, and never present `odds_if_product` as a price —
  Superbet does not price a slip as the product of its legs; the measured
  markup is 8.8–19.6%.
- No stake sizing, no automated placement.
- Never read, echo or log `.env` values.
- Never re-fit constants mid-day (`fit_constants.py`, `fit_confidence.py`,
  `fit_sport_confidence.py` are between-days steps): re-fitting breaks
  comparability with yesterday.
- Epochs are never pooled: the official coupon before and after 07:15Z on
  2026-10-05 is not one experiment (ledger `official` vs
  `official:pre_stats_only`).
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
| `docs/sofa/history/PLAN_2026-10-05_SETTLE_I_KUPON.md` | the stats-only coupon (K0-K14) and the measured sports on it (F1-F8) |
| `docs/sofa/history/` | dated run reports and findings — historical, may be stale |

Those documents are Polish, this configuration is English, and that boundary
is deliberate. The retired `simple` pipeline was deleted on 2026-10-05: take no
stage name, quantity or artifact name from its vocabulary.
