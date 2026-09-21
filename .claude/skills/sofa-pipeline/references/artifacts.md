# The artifacts — every file, every field

All under `runs/sofa/<date>/`. Types come from `src/bet/sofa/contracts.py`,
which is `strict=True, extra="forbid"` throughout — a field not listed here
does not exist, and a typo is a validation error rather than a silent `None`.

The day is **UTC**. Datetimes in these files are UTC ISO with `Z`.

---

## `01_board.json` — `BoardFixture[]`

| field | type | note |
|---|---|---|
| `superbet_event_id` | str | Superbet's own id; a Sofascore match may have **several** |
| `sport` | `"football" \| "tennis"` | nothing else exists in `sofa` |
| `match_name`, `side_a`, `side_b` | str | as Superbet names them |
| `kickoff_utc` | datetime | Superbet's clock |
| `tournament_id`, `category_id` | int \| null | Superbet sends **no competition name**. These are the only handle on "which competition" before RESOLVE, and what BOARD excludes by. |

## `02_fixtures.json` — `Fixture[]`

| field | type | note |
|---|---|---|
| `sofascore_event_id` | int | the key everything downstream joins on |
| `superbet_event_ids` | str[] | plural: duplicate listings are merged here |
| `kickoff_utc` | datetime | **Sofascore's** clock |
| `superbet_kickoff_utc` | datetime \| null | **Superbet's** clock |
| `kickoff_disagreement_h` | float \| null | up to 11 h on ITF. COUPON takes the **earlier** of the two. |
| `home_name` / `away_name`, `home_entity_id` / `away_entity_id` | | the side a `subject` must resolve to |
| `competition_name`, `competition_id`, `season_id`, `category_name` | | first place a competition is named at all |
| `identity` | `CONFIRMED \| FUZZY` | |
| `round_number`, `round_name`, `cup_round_type`, `previous_leg_event_id` | | cup context; `previous_leg_event_id` is how a second leg is visible |
| `venue_name`, `referee` | `RefereeRecord \| null` | referee is filled for ~9% of fixtures — announced late |
| `ground_type` | str \| null | tennis surface |
| `default_period_count` | int \| null | tennis: the real best-of (3 or 5). Football: the number of halves, which is why it is not called `best_of`. |

`RefereeRecord`: `name`, `games`, `yellow_cards`, `red_cards`,
`yellow_red_cards`.

## `03_samples.json` — `FixtureSamples[]`

```
sofascore_event_id, readiness: READY|PARTIAL|BLOCKED,
metrics: { "<metric>": MetricSample }, gaps: GapEntry[]
```

`MetricSample`: `metric`, `side_a[]`, `side_b[]`, `h2h[]` — each an
`Observation`:

| field | note |
|---|---|
| `sofascore_event_id` | the past match this number came from. **This is what a builder's empirical joint intersects on.** |
| `match_date_utc` | drives `sample_newest_days` and the builder's age guard |
| `opponent` | who the sample was collected against — the quality question |
| `value` | float |
| `competition_id`, `season_id`, `venue` (`home`/`away`/null) | |

`GapEntry`: `reason` (a `GapReason`), `metric`, `detail`. **Every gap has a
named reason.** Nothing disappears in silence; if you cannot find why a metric
is absent, you are reading the wrong file, not looking at a silent drop.

## `04_offer.json` — `FixtureOffer[]`

```
sofascore_event_id, status: PRICED|NO_PRICE|null,
rungs: PricedRung[], unmapped_markets: str[], price_collisions: str[]
```

`PricedRung`: `market`, `subject`, `line`, `over_odds`, `under_odds`,
`fetched_at_utc`. A rung with one side `null` is **one-sided** — no devig is
possible, so `market_p` is `null` and the sheet says `NO_MARKET_MARGINAL`.

`fetched_at_utc` is per rung and is what the 45-minute staleness gates read.

## `05_sheet.json` — `SheetRow[]`

| field | note |
|---|---|
| `sofascore_event_id`, `sport`, `market`, `subject`, `line`, `direction` | the row's identity. `subject` is `""` for a match-level market. |
| `sample_size`, `sample_mean`, `sample_sd` | the sample, before shrinkage |
| `centre` | the mean **after** shrinkage toward the league prior |
| `p_central` | the model's probability |
| `calibration_correction` | subtracted from `p_central` before the price blend. On the row since 2026-09-21 — without it `p_bar` cannot be re-derived from the row's own fields. |
| `market_p` | Superbet's price, power-devigged. `null` when one-sided. |
| `ladder_centre`, `ladder_sigma` | describe **the bookmaker's ladder**, not our distribution |
| `p_bar` | the blend the bar is computed from |
| `bar_reason` | `none \| laplace_cap \| p_low_cap` |
| `sample_newest_days` | age of the **newest** observation. `null` = no usable date, which is kept: unknown is not stale. |
| `required_odds`, `offered_odds`, `edge`, `surplus` | `edge = p_central − market_p`; `surplus = offered − required` |
| `verdict` | `VALUE \| LEAN \| BELOW_BAR \| NO_PRICE \| BLOCKED` |
| `notes[]` | see `stages.md` § SHEET |

## `06_coupon.json` — `Coupon` — **not the coupon**

`created_at_utc` + `singles: CouponRow[]`. A `CouponRow` carries the row's own
arithmetic — `sample_size`, `centre`, `p_central`, `calibration_correction`,
`market_p`, `p_bar`, `offered_odds`, `required_odds`, `edge`, `surplus`,
`sample_newest_days` — plus `match_name` and `kickoff_utc`, so it can be
checked without opening the sheet.

## `06_dropped.json`

One entry per VALUE row that did not make it: row identity, `surplus`,
`reason`, `detail`. **This file is the reason nothing vanishes in silence.**
Read it before concluding a row was never generated. Reason vocabulary in
`stages.md` § COUPON.

## `07_settled.json` (D-1) + `07_settle_skips.json`

Graded rows, also written to `data/sofa.db` (`sofa_settled_row`). The skips
file says which rows could not be graded and why — a blind row counted as a
loss understates the model exactly as much as counting it a win overstates it.

## `08_confidence.json`

```
created_at_utc, confidence_floor, vetoes_applied, vetoes_unmatched,
legs: [...], builders: [...]
```

A **leg**: identity + `model_p` (what the model claimed), `confidence` (the
measured lower bound — this is the number), `calibrated_on`
(`market:<name>` or `pooled`), `calibration_n`, `sample_size`,
`sample_observations`, `sample_oldest_days`, `sample_min`/`sample_max`,
`offered_odds`, `implied_p`, `shading` (`confidence − 1/odds`), `leg_ev`
(`confidence·odds − 1`), `market_p`.

A **builder**: `legs[]`, `n_legs`, `combined_probability` (the **lower** of
the product and the empirical joint), `product_probability`,
`empirical_joint_hits` / `_n` (how often every leg held in the *same* past
match — often 0), `fair_odds`, `odds_if_product`, `ev_if_product_priced`,
`haircut` (0.12), `odds_after_haircut`, `ev_after_haircut`,
`best_for_fixture`.

Two traps in this object:

- `ev_if_product_priced` being positive **means nothing on its own**. Superbet
  does not price a slip as the product of its legs; the measured markup is
  8.8–19.6%. Select on `ev_after_haircut`.
- A fixture emits a 2-, 3- and 4-leg builder off the same ranked pool, so the
  smaller ones are **subsets** of the larger. Staking all three is staking one
  opinion three times. `best_for_fixture` marks the one.

## `KUPON_<date>.pdf`

The product. Only `is_stakeable` slips — `best_for_fixture` **and**
`ev_after_haircut > 0`.

## `vetoes.json` — `Veto[]`

`sofascore_event_id` (int, required), `market`, `subject`, `line`,
`direction` (all nullable, `null` = all), `reason_class`
(`SAMPLE_UNINFORMATIVE | CONTEXT | PRICE | OTHER`), `reason` (free text, and
the operator reads it).

Read by **COUPON and CONFIDENCE both**. Write it after SHEET and before either.

## The log

`runs/sofa/run.log.jsonl` — one JSON row per request, carrying `run_id` and the
stage that declared it (`src/bet/sofa/stage.py`). The stage is a context
variable set once at the top of each `run_*.py`, not a literal per client
method: `entity_events` is called by RESOLVE *and* SAMPLES, and when it was a
literal, 8.2% of SAMPLES' cost was filed under RESOLVE. A request with no
declared stage logs as `CLIENT`, deliberately not a real stage name, so it is
visible rather than misfiled.
