# Architecture

What runs, where it lives, and what is kept only as a record.

## 1. One pipeline is in service

**`sofa`** — Sofascore statistics, Superbet prices, one coupon PDF per day
for every sport on it: football and tennis, and since 2026-10-05 08:30Z
hockey, basketball, volleyball and CS2. It imports **nothing** from the older trees; that was a decision,
not an accident: the knowledge transferred, the code did not.

| | in service | retired |
|---|---|---|
| library | `src/bet/sofa/` | `src/bet/simple_stats/`, `src/bet/tipsters/`, `src/bet/enrichment/`, `src/bet/discovery/`, `legacy/` |
| entry points | `scripts/sofa/` | `scripts/simple/`, `legacy/pipeline_steps/` |
| stages | BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON (+ CONFIDENCE, SPORT_IDENTITY, SPORT_CONFIDENCE, COUPON_ASSEMBLY, PDF, and FIXTURE_CHECK in a rebuild; SETTLE and FIT outside the sequence) | DISCOVER → SUPERBET → ENRICH → MARKET_CONTEXT → TIPSTERS → ANALYZE; S0–S10 |
| stats sources | Sofascore only | bzzoiro, ESPN, highlightly, OddsPapi, api-football, sportdb |
| fixture key | `sofascore_event_id` (int) | `event_id` (64-char hash) |
| ranking quantity | legs by measured `confidence` (statistics only since 2026-10-05; the price only as the betting condition); `p_central` → `p_bar` for the priced VALUE selector | `p_low`, tiers CALL/LEAN/WEAK/DROP |
| product | `runs/sofa/<date>/KUPON_<date>.pdf` | `runs/<date>/<date>_kupony.md` |
| tests | `tests/sofa/` (699, offline) | `tests/simple_stats/`, `tests/tipsters/`, … |
| agentic config | `.claude/agents`, `.claude/commands`, `.claude/skills` | `.claude/legacy/`, `.kilo/legacy/` |
| docs | `docs/sofa/` | `docs/legacy/` |

The retired code is not deleted because the artifacts and the database rows it
produced are still on disk and still read. `legacy/` does not even import — 16
files there carry unresolved merge markers. Nothing in this document below the
line above describes it further; see `docs/legacy/README.md`.

## 2. Modules of `src/bet/sofa/`

| module | responsibility |
|---|---|
| `board.py` | the day's fixtures off Superbet's board; sport, doubles and tournament filters |
| `resolve.py` | board fixture → `sofascore_event_id`; name/gender/orientation matching, both clocks |
| `offer.py` | which rungs Superbet actually prices, with `fetched_at_utc` per rung |
| `market_mapper.py` | Superbet's market names → our metric vocabulary; records `unmapped_markets` |
| `samples.py` | last N finished matches per side per metric; scoping, gaps, readiness |
| `metrics.py` | what a metric *is* in a Sofascore payload (30 football, 22 tennis) |
| `engine.py` | the pricing chain: prior → centre → `p_central` → `p_bar` → verdict |
| `derived.py`, `joint.py` | markets about both sides at once, via a Gaussian copula over measured correlations |
| `coupon.py` | VALUE-singles selection and every exclusion, with a reason |
| `confidence.py` | legs ranked by measured realised rate; Bet Builders; `is_stakeable`; `coupon_order`, `coupon_artifact`, `legs_requiring_read` |
| `epochs.py` | `STATS_ONLY_FROM_UTC` (2026-10-05 07:15Z) and `SPORTS_ON_COUPON_FROM_UTC` (08:30Z) — which rule a build is under |
| `sport_identity.py` | SPORT_IDENTITY: pre-match Sofascore id of a hockey / basketball / volleyball / CS2 event, pinned in `sport_fixtures.json` |
| `sport_confidence.py`, `score_model.py`, `cs2_engine.py` | SPORT_CONFIDENCE: the score model / CS2 engine probability read through `config/sofa_sport_confidence_calibration.json` |
| `coupon_sports.py`, `locked_print.py` | the measured sports' legs on the one coupon (reads, locks, grading by the pinned id); legs locked from the last print (`12_printed.json`) |
| `fixture_status.py` | FIXTURE_CHECK: a printed match postponed / cancelled / abandoned, and its fresh start |
| `shadow.py`, `cs2.py` | the SHADOW / CS2 price measurement and its settlement; their snapshots feed SPORT_CONFIDENCE |
| `settle.py` | grade a finished day against Sofascore, with the price |
| `veto.py` | matching and unmatched-veto reporting for `vetoes.json` |
| `coverage.py` | run-over-run coverage floor (weekday-blind — see the runbook) |
| `client.py`, `bridge_transport.py`, `cache.py`, `stage.py`, `errors.py` | transport, the browser bridge, caching with TTLs, stage-scoped logging, circuit breaker |
| `superbet.py` | Superbet client and `SPORT_IDS` |
| `contracts.py` | every artifact's Pydantic model — the actual interface between stages |
| `config.py` | `SofaConfig` and its environment variables |
| `db.py` | `data/sofa.db` — settled rows, cache, run log |
| `names.py`, `timeutil.py`, `canonical`-helpers | name folding/aliases, UTC handling |

## 3. Data flow and state

```
Superbet ─► 01_board.json ─► (bridge) 02_fixtures.json ─┐
Superbet ─► 04_offer.json ──────────────────────────────┼─► 05_sheet.json ─┬─► 06_coupon.* + 06_dropped.json
             (bridge) 03_samples.json ──────────────────┘     ▲            └─► 08_confidence.* ──┐
                                                 config/sofa_*.json                            ├─► 11_coupon.json ─► KUPON_<date>.pdf + 12_printed.json
Superbet ─► SHADOW / CS2 snapshots ─► (bridge) sport_fixtures.json ─► 08_confidence_sports.json ┘
                                                              ▲
         D-1: 05_sheet + results ─► 07_settled.json ─► data/sofa.db ─► fit_constants.py
```

**`data/sofa.db` plus `config/sofa_*.json` are the only state carried between
days.** Everything else is a per-day directory that can be deleted and rebuilt
from the artifacts above it. That is why a stale config file is both silent and
expensive, and why re-fitting mid-day is an error rather than a wasted minute.

## 4. Constraints that shape the design

- **Sofascore answers 403 to every non-browser client** (since 2026-09-17). The
  pipeline talks to `scripts/sofa/bridge_server.py`, a real browser tab polls
  it through `userscripts/sofascore-bridge.user.js`, and the answers come back.
  Rate: 2 req/s configured, ~0.5–2 observed. Raising it is how the API was
  closed in the first place.
- **Superbet is the only price that matters** — it is where the bet is placed.
  Any other book is a reference, never a price.
- **Nothing may vanish silently.** Every dropped row carries a reason, every
  sample gap a `GapReason`, every unfitted constant a note on every row that
  used it. `scripts/sofa/audit_coupon.py` enforces the first of those
  mechanically.
- **A constant with no data is `null` with a status**, never a borrowed
  default. `K_PRICE` is `NOT_FITTED` because its Brier curve has no interior
  optimum: the model loses to the price, and saying so is information.
- **Two products, and they disagree.** `06_coupon.json` (VALUE singles,
  measured −20.4% on 2026-09-20) and the PDF (Bet Builders, +8.2% the same
  day). Only the PDF is staked; since 2026-10-05 it renders `11_coupon.json`,
  the one coupon artifact. The operator's variant (WARIANT), WARIANT
  WSZYSTKIE and the separate per-sport coupons were retired 2026-10-05
  (historical: their files up to that morning stay and are graded as
  before).

## 5. Where to read further

| | |
|---|---|
| the flow, in full detail | [`docs/sofa/PIPELINE.md`](docs/sofa/PIPELINE.md) |
| running a day | [`docs/sofa/RUNBOOK.md`](docs/sofa/RUNBOOK.md) |
| agents and handoffs | [`docs/sofa/AGENTIC_FLOW.md`](docs/sofa/AGENTIC_FLOW.md) |
| constants and calibration | [`docs/sofa/CONFIG.md`](docs/sofa/CONFIG.md) |
| the Sofascore API itself | [`docs/sofa/REFERENCE.md`](docs/sofa/REFERENCE.md) |
