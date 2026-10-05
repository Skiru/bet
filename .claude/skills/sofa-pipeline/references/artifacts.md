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
| `superbet_kickoff_utc` | datetime \| null | **Superbet's** clock. A match listed twice keeps the first listing's clock, unless it is exactly 00:00:00Z and the other is a real time (`resolve.merged_superbet_kickoff`, since 2026-10-01: three ITF matches held a midnight placeholder beside 11:08Z and lost all 168 priced rungs as "started") |
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
metrics: { "<metric>": MetricSample }, gaps: GapEntry[],
players: { "<metric>|<player>": PlayerSample }
```

`MetricSample`: `metric`, `side_a[]`, `side_b[]`, `h2h[]` — each an
`Observation`:

| field | note |
|---|---|
| `sofascore_event_id` | the past match this number came from. **This is what a builder's empirical joint intersects on.** |
| `match_date_utc` | drives `sample_newest_days` and the builder's age guard |
| `opponent` | who the sample was collected against — the quality question |
| `value` | float |
| `minutes` | float or null. Set **only** on a per-player observation (F54); null for every team and tennis metric, where it has no meaning. |
| `competition_id`, `season_id`, `venue` (`home`/`away`/null) | |

`PlayerSample` (F54) is the third axis, alongside `_total` and `_for`. Its
subject is neither side — it is one footballer — so it cannot live in
`metrics`, whose two buckets *are* the two sides. Keyed
`"<metric>|<player as Superbet writes him>"`, which is exactly the
`(market, subject)` pair a rung carries, so SHEET and CONFIDENCE look it up
without re-running the name match (`players.player_sample_key`).

| field | note |
|---|---|
| `metric` | `player_shots_for`, `player_shots_on_target_for`, `player_assists_for`, `player_fouls_for`, `player_tackles_for`, `player_interceptions_for`, `player_offsides_for` (the last four: zero only when the team sum closes) |
| `player` | the name Superbet wrote, e.g. `"Tolo, Nouhou"` |
| `matched_name` | the normalised Sofascore squad name it was matched to |
| `side` | `side_a` / `side_b` — which squad he was found in, more often |
| `squad_matches` | how many of that side's sampled matches carried a squad list at all. The honest denominator: without it a six-match sample from a ten-match history is indistinguishable from one from a six-match history. |
| `observations` | `Observation[]`, newest first, **appearances only** |

An appearance is `minutesPlayed` being present. A squad member who did not
take the pitch carries `totalShots: 0` and no minutes, and that zero is not an
observation — Superbet *voids* a player market when the player does not play,
it does not settle it at zero.

`GapEntry`: `reason` (a `GapReason`), `metric`, `detail`. **Every gap has a
named reason.** Nothing disappears in silence; if you cannot find why a metric
is absent, you are reading the wrong file, not looking at a silent drop.

The SAMPLES summary counts `provider_fault_fixtures` (since 2026-10-01):
fixtures that lost metrics to a provider fault with nothing to carry over.
Any of them makes the verdict `PARTIAL` (`samples_verdict`); before, a breaker
opening mid-SAMPLES thinned the day under an `OK`. A cached match whose
`incidents_json` is NULL ("never asked", not "none") is asked `/incidents`
once when a card market needs it; a 404 is stored as `{}` and read as no
incidents. A fault on that ask costs the card metrics (`NO_INCIDENTS`), never
the match (2026-10-01: 118 gaps over 59 events were all NULL).

## `04_offer.json` — `FixtureOffer[]`

```
sofascore_event_id, status: PRICED|NO_PRICE|null,
rungs: PricedRung[], unmapped_markets: str[], price_collisions: str[]
```

`PricedRung`: `market`, `subject`, `line`, `over_odds`, `under_odds`,
`fetched_at_utc`. A rung with one side `null` is **one-sided** — no devig is
possible, so `market_p` is `null` and the sheet says `NO_MARKET_MARGINAL`.

`fetched_at_utc` is per rung and is what the 45-minute staleness gates read.

One Superbet listing that errors (a removed event answers 404) is a gap, not
`FAILED` (since 2026-10-01): it is counted in the summary's `fetch_errors`
(the first 20 on stderr as `OFFER_FETCH_ERROR`) and the verdict is `PARTIAL`.
A fixture whose every listing failed gets **no entry** - not an empty one -
so a filtered refresh's merge keeps the prices the previous file holds.

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

**Locked legs (since 2026-10-05, operator: "a leg printed before its match
started counts").** A rebuild of CONFIDENCE reads the previous artifact of the
same profile and carries over, unchanged, every printed single and printed
stakeable builder whose match has started or is inside the kickoff margin
(`bet.sofa.locked_print`; the same `kicked_off` predicate that refuses fresh
rows). They carry `locked: true`, `printed_at_utc` (the build that printed
them) and `printed_under` (that build's floor / min_ev / max_overround), come
first in `singles` / `builders` / `legs`, and fresh singles fill the remaining
`pdf_max_singles`. The artifact then carries `locked_from_utc`,
`locked_singles`, `locked_builders` and `locked_late_refusals` (a veto or a
NO_BET / WATCH read now covering a locked leg - shown, never acted on); an
artifact with nothing locked has none of these keys. A leg a rebuild drops
BEFORE its start (veto, read, moved price) stays dropped. The PDF marks a
locked leg `w grze - wydrukowane przed startem (wydruk HH:MMZ)`;
audit_variants checks it against `printed_at_utc` / `printed_under`.

## `KUPON_<date>.pdf`

The product. Only `is_stakeable` slips — `best_for_fixture` **and**
`ev_after_haircut > 0`.

Since 2026-10-01 the page marks (shown, never enforced): `ta sama drabina: N`
on a single when N singles stand on one ladder (`confidence.ladder_key`:
fixture, market, subject), with a line above the list counting such ladders
(09-30's coupon printed corners_total 12.5 UNDER, 11.5 UNDER and 7.5 OVER on
one match; 10-01's WARIANT ten such ladders, 22 rows); `start przed renderem
PDF` on a leg already inside CONFIDENCE's kickoff margin when the PDF is
rendered (kept - the JSON is what is graded - and a `WARNING` on stderr). A
builder line prints only `kurs po narzucie` (`odds_after_haircut`), never the
product of the legs' prices. The PDF is rendered to a temporary sibling and
moved into place, so a crash never leaves a truncated `KUPON_*.pdf`.

Every stage artifact, PDF and `config/` fit is written atomically since
2026-10-01 (`src/bet/sofa/atomic.py`: `<name>.<pid>.<thread>.tmp` beside the
target, then `os.replace`).

## `10_boosts.json` / `10_boosts.md` — `Boost[]` — **not the coupon**

Written by `scripts/sofa/run_boosts.py --date <d>`, outside `DEFAULT_SEQUENCE`
(like `fit_constants.py`); re-runs merge by `odd_uuid` and append to
`observations`. One record per Superbet odd tagged `price_boost`:
`boosted_price`, `original_price` (from `extra.originalPrice`), `combo`, and
`legs[]` - each leg classified by `offer.classify_odd`, so it keys onto the
same sheet row SETTLE graded. `leg_price_product` is a yardstick for
Superbet's markup and **never a price**. Graded by `audit_boosts.py --from
--to` and `audit_settlement` section 7f; a boost whose fixture is not on the
day's board is `NOT_ON_BOARD`, not a loss. Superbet's offer API carries no
results, so nothing off the board can be graded.

## `runs/sofa/cs2/<date>/` — CS2 shadow measurement — **not the coupon**

Beside the day, never inside it; no coupon stage reads it. Two stages outside
`DEFAULT_SEQUENCE`, registered in `run_pipeline.STAGE_MODULES`:

- **CS2** (`scripts/sofa/run_cs2.py`, Superbet only, run several times a day)
  appends `snapshots.jsonl`: one record per not-yet-started CS2 series (sportId
  55) with every complete outcome group - two-way lines and, since
  2026-09-30, the exact maps score (`exact_maps`, "2:1" = team1 first) and a
  map's round parity, each devigged over its whole group (`cs2.group_fair`) -
  `family`, `map_nr` (0 = series), `subject` (player/team), `line` (a total,
  or **team1's** handicap: Superbet quotes both outcomes under team1's
  `hcp`), `side`, `odds`. Boosted prices, combos, AWP kills, round-N and
  pistol-round markets are not parsed.
- **CS2_SETTLE** (`scripts/sofa/settle_cs2.py`, Sofascore via the bridge, D-1)
  writes `settled.json`: per series a `state` - `SETTLED` (with `maps`, as
  `[team1, team2]` rounds, and `graded[]`: `actual`, `outcome`, `fair_p` by
  the pipeline's power devig), `PENDING`, `NOT_ON_SOFASCORE`, `AMBIGUOUS`,
  `DATA_MISMATCH` (the maps do not reproduce Sofascore's series score, so
  nothing is graded), `UNUSUAL` (finished but not "Ended", e.g. a walkover),
  `VOID` (cancelled, or still ungraded 48 h after the start - Superbet's own
  rule), `GAVE_UP` (ours, after `GIVE_UP_AFTER` = 7 days). VOID/UNUSUAL/
  GAVE_UP are never asked again; a `SETTLED` series is asked again while it
  carries `pending_sides` > 0 (`pending_reason` `SERIES_ONLY` or
  `STATS_PENDING`, `settle_cs2.is_waiting`), and a failed retry never
  replaces the grades it already has (`last_retry_state`; past
  `GIVE_UP_AFTER` the count moves to `gave_up_pending`). Since 2026-10-01 a
  series whose player rows are missing (`STATS_GRACE` 72 h) is no longer held
  whole: only the player / team-kill sides on a map without player rows wait
  (`stats_pending`), the series, map and round lines are graded now. A series
  with no round scores grades its series lines and counts the rest
  (`series_only_skipped` - on 09-30 114 of 154 were dropped uncounted).
  `sofascore_start_utc` is written since 2026-10-01, so the sport coupon's
  `IN_PLAY_PRICE` guard can fire for CS2. `settled.json` is a locked
  read-modify-write (`<file>.lock`): a concurrent settle keeps the series
  this one did not touch.
- `settle_cs2.py --sweep-from <d> --sweep-to <d>`: settles every date in the
  range whose `settled.json` is missing or still holds a waiting series
  (decided offline from the files; `CS2_SETTLE_SWEEP` summary lists
  `waiting_dates`).
- `cs2_daily.py`: one loop per date (`daily_<d>.pid`, `daily_<d>.done`; a
  second loop refuses, exit 2). Snapshots to 23:30Z; `--chain` then starts
  D+1's loop, so D+1's night series are priced. Its 05:00Z morning settles D
  and D-1 (the night series of D-1's coupon sit in D's file), sweeps D-7..D-2
  (`settle_cs2.py --sweep-from/--sweep-to`: without it a series still waiting
  on D-2 was never asked again and never reached `GIVE_UP_AFTER`, audit
  2026-10-01), then grades the CS2 coupons and records the ledger for
  D-7..D. A loop reads this plan when it starts.

**History and engine.** `scripts/sofa/backfill_cs2.py` (stage name
CS2_BACKFILL, not in STAGE_MODULES - it takes `--days/--hops/--max-minutes`)
fills `cs2_series` / `cs2_map` / `cs2_player_map` in `data/sofa.db` from
Sofascore, Sofascore's home/away kept as is; CS2_SETTLE also writes each
series it grades. Results only - Superbet's offer API has no history. Each
graded side then carries `model_p` / `model_n` / `model` /
`unfitted_constants` from `src/bet/sofa/cs2_engine.py`: map Elo calibrated
by a logistic fit with a home term on its own pre-cut walk-forward
predictions, plus an exact best-of series distribution, for map_winner and
match_winner only; a negative binomial (`engine.nb_survival`, or a
continuity-corrected normal when under-dispersed) for player stats and team
kills; the history base rate for map_rounds_total and a base-rate-shrunk
frequency for map_team_rounds. maps_total / maps_handicap / team_maps get
`null`: the constant-p series overpredicted three-map series. P(side | no
push) on integer lines. History cut at the earlier of the two kickoffs, the
graded series excluded by id. A backfill that meets a 403/429 stops and
writes `runs/sofa/cs2/backfill_cooldown.json` (12 h; `--force`).

`audit_cs2.py --from --to` reports coverage and price-against-outcome per
family. It is a measurement of Superbet's price: CS2 has no calibration curve,
so CONFIDENCE would refuse every CS2 row (`NOT_CALIBRATED`) even if one
reached a sheet - which none does.

## `runs/sofa/shadow/<sport>/<date>/` — hockey / basketball / volleyball shadow — **not the coupon**

CS2's design for three team sports (`src/bet/sofa/shadow.py`), sport one of
`hockey` (Superbet 3, Sofascore `ice-hockey`), `basketball` (4), `volleyball`
(1). Stages SHADOW (`run_shadow.py`, Superbet only) and SHADOW_SETTLE
(`settle_shadow.py`, bridge, D-1), both outside `DEFAULT_SEQUENCE`;
`shadow_daily.py` runs a day unattended, `audit_shadow.py --from --to` reports.

- `snapshots.jsonl`: per not-yet-started game every complete outcome group -
  two-way lines and, since 2026-09-30, the 1X2s (three sides; a 1X2 missing
  its draw is no price), odd/even, yes/no (volleyball's "set on extra
  points") and volleyball's exact set score, each devigged over its whole
  group -
  `market_id` (the table key; one id per market type across events),
  `family`, `period` (0 = none; period / quarter / set otherwise), `subject`
  (`T1`/`T2` for a team total), `line` (a total, or **team1's** handicap),
  `side` (OVER/UNDER/T1/T2, or the group's outcome: T1/DRAW/T2 for a 1X2,
  ODD/EVEN, YES/NO, "3:1" = team1 first for an exact score), `odds`.
- `settled.json`: per game a `state` - `SETTLED` (with `t1_periods`,
  `t2_periods`, `t1_full`, `t2_full`, `overtime`, `graded[]` with `actual`,
  `outcome`, `fair_p`, `overtime`), `PENDING`, `NOT_ON_SOFASCORE`,
  `AMBIGUOUS`, `DATA_MISMATCH` (the periods do not add
  up to Sofascore's own totals), `UNUSUAL` (finished but not Ended/AET/AP),
  `VOID` (cancelled / not started 48 h on), `GAVE_UP` (ours, after 7 days),
  `NO_PRE_START_PRICE` (Sofascore's start was earlier than Superbet's and
  no snapshot predates it - every price held was in play; final).
  The pre-match clock is the EARLIER of Superbet's kickoff and Sofascore's
  `startTimestamp` (football's rule); a game that began early carries
  `sofascore_start_utc`, `started_before_superbet_min`,
  `priced_sides_superbet_clock` and `priced_sides`, and is graded at the last
  snapshot before it; `minutes_before_kickoff` runs to that earlier clock.
  NO_PRE_START_PRICE is only decided for a finished game. An empty `/event`
  is `ERROR` (retried), never the listing's score.
  A game whose orientation cannot be told is SETTLED with
  `orientation_unclear: true` and only its totals graded. Every graded row
  carries `minutes_before_kickoff` (audit section 5 splits on it).
- SHADOW also records the next day's games that start within its horizon,
  into that day's file, so late North American games are priced.
- Player lines (since 2026-09-29, hockey + basketball, two-sided only):
  `family` `player_*`, `subject` = Superbet's player name, graded from a
  fresh `/event/{id}/lineups`; `player_box` on the game record is `ok`,
  `missing` or why the box does not add up to the score (then no player line
  of the game is graded, `player_no_box`); a player who did not play is
  `player_dnp` (void), an unmatched name `player_unmatched`. Since 2026-10-01
  the `/lineups` answer of a finished game is saved to the cache
  (`sofa_event_stats.lineups_json` had been empty for all 3,052 graded player
  sides), so a player grade can be audited against its box; an empty answer
  is not saved.
- A `NOT_ON_SOFASCORE` game carries `miss` (`team1` / `team2`): the first gate
  that emptied each side's lookup (`shadow.miss_reason`: `CACHED_MISS`,
  `NO_SEARCH_RESULT`, `NO_CANDIDATE` with `search_teams`, `NO_LISTING`,
  `NO_GAME_IN_WINDOW` with `nearest_gap_h`, `GENDER_REFUSED` /
  `OPPONENT_REFUSED` with `in_window`, `UNEXPLAINED`), read from the search
  already paid for and the cache, never a new request (30 of 50 volleyball
  games of 09-29..30 ended NOT_ON_SOFASCORE with nothing saying why).
- `shadow_daily.py`: one loop per date (`daily_<d>.pid`, deleted on exit; a
  second loop refuses, exit 2). Its 05:15Z morning settles D, D-1 and D-2
  (each that has snapshots; D-2's settle is 53-77 h after its games, the
  first late enough for a postponed game to read VOID - `VOID_AFTER` 48 h -
  rather than end GAVE_UP), grades those days' sport coupons
  (`settle_sport_coupon.py`) and records them (`record_results.py --from
  <earliest> --to D`). `--chain` starts D+1's loop after
  D's 05:15Z settle and audit - without it D+1's games after ~07:30Z are priced only
  once someone starts D+1's loop.
- A market without "(z dogrywką)" counts regulation time; Sofascore puts an
  overtime goal in `current` and in no period. Hockey's overtime-inclusive
  families (613 / 617 / 621 / 653) are not mapped, and the NHL is posted ONLY
  with them, so no NHL total is measured at all (review 2026-10-01). Basketball Q4 and second-half
  lines are ungradeable after overtime (the name does not say whether it is
  appended).
- `audit_shadow.py` (and `audit_cs2.py` section 2) keep ONE side per line
  (`cs2.one_side_per_line`): pooled, the sides of a line read mean fair p =
  hit rate by construction (0.500 for a two-way line). Section 2 is the
  favourite side, 2b a fixed side (OVER / ODD / YES, else T1; an exact-score
  group keeps its first stored score, which says nothing).
  Every shadow row carries `SE pp` (clustered by game) and `read`: `too few`
  (< 30 games), `noise` (gap inside 2 SE), `lead only` (outside, < 7 days of
  data), `signal`. Quote `read`, never a bare gap.

## `sport_coupon.json` (+ `.md`, `KUPON_<d>_{CS2,HOKEJ,KOSZYKOWKA,SIATKOWKA}.pdf`) — **not the coupon**

In the measurement's own directory (`runs/sofa/cs2/<d>/`,
`runs/sofa/shadow/<sport>/<d>/`), written by `run_sport_coupon.py`. Price-only:
no model. Top level: `kind` = `SPORT_COUPON_EXPERIMENT`, `not_the_coupon`,
`sport`, `date`, `created_at_utc`, `window_start_utc` / `window_end_utc` (the
previous day's and this day's 06:00 Warsaw, D+1), `probability` (what fair_p
is), `rule` (floor, max_overround, min_odds, max_legs, kickoff margin, max
price age, day end, rank), `UNFITTED_CONSTANTS`, `snapshots` /
`snapshot_lines` / `unreadable_snapshot_lines` (what the build read, so
`audit_variants` replays exactly it), `vetoes_applied`, `counts` (drop reasons),
`candidates`, `vetoes_file`, `vetoes_unmatched`, `vetoed`, `locked`,
`replaced_legs` (legs an earlier build printed and this one does not, with
why), `refused_events` (CS2: Superbet event id -> `unseen_team`, a side the
`cs2_series` store has never seen, computed once per build so `audit_variants`
replays exactly it; an empty store refuses nothing), `previous_build_utc`, `rule_history` (the rule replayed on the settled
days at the last pre-start price - not a printed price), `pdf_sha256` (the PDF
it was printed as) and `legs[]`.

A leg: the snapshot line (`superbet_event_id`, `market_id` (shadow),
`family`, `period` / `map_nr`, `subject`, `line`, `side`, `odds`),
`group_odds` (the whole outcome group), `fair_p`, `overround`,
`fair_p_x_odds`, `match_name`, `team1`, `team2`, `tournament`, `kickoff_utc`,
`source_date` (the snapshot file the event is in: D, or D+1 for a night game),
`price_fetched_at_utc`, `price_age_min`, `label` (Polish), and optionally
`locked` (started before a rebuild: kept as printed) and `tie_at_cut`.

`sport_coupon_builds.jsonl`: every build appended (`created_at_utc`, `legs`,
`vetoed`). Legs of earlier builds and `replaced_legs` are **recorded, never
graded** - only the final build's `legs` are the coupon's result.

`sport_coupon_settled.json` (`settle_sport_coupon.py`, and every
`record_results.py` run): `sport`, `date`, `not_the_coupon`, `graded_at` =
"printed price", `legs[]` = each leg with its `outcome`: `WIN` / `LOSS` /
`VOID` (a push, a period never played, or SETTLE voided the event),
`UNGRADEABLE`, `IN_PLAY_PRICE` (printed after Sofascore's real start, never
counted), `NOT_GRADED:<state>`, `PENDING` / `PENDING:<state>`, `MISMATCH`
(the measurement graded the same side the other way: a grader defect,
neither result counted, exit 1). A CS2 leg on a partly graded series
(`pending_sides` in `settled.json`) is `PENDING:<pending_reason>`, not
`UNGRADEABLE`, until the record is final or the leg passes 7 days.

Build-time refusals that keep an ungradeable leg off a sport coupon (in
`counts`): `friendly_tournament`; `unsettleable_tournament` - over the last
14 settled days before D, at least half of >= 2 events `NOT_ON_SOFASCORE`, or
(since 2026-10-01, `UNSETTLEABLE_ALL_MIN_EVENTS`) every seen event (>= 1)
`NOT_ON_SOFASCORE` (10-01's volleyball coupon printed two legs of "Brazylia -
Paulista U19" and one of "Szwecja - Puchar Ligi", each 1/1 not found); an
unseen tournament passes. CS2 only, since 2026-10-01: `unseen_team` (above)
and `no_tournament` (Superbet's struct fetch failed, so neither gate can read
the event).

## `runs/sofa/multi/<d>/` — WARIANT WSZYSTKIE — **not the coupon**

`multi_coupon.json` (`run_multi_coupon.py`): `kind` = `MULTI_SPORT_VARIANT`,
`not_the_coupon`, `date`, `created_at_utc`, `counts` (`singles`, `builders`,
`sections_ok`, `sections_excluded`), `pdf_sha256`, and `sections` -
`official` and one per sport, each `status` `OK` or `EXCLUDED` with `reason`
(`MISSING`, `STALE`, `STALE_CONFIDENCE`, `PDF_OLDER_THAN_ARTIFACT`, ...).
A position: `section`, `sport`, `match`, `competition`, `kickoff_utc`,
`odds`, `probability` (confidence for official, fair_p for a sport),
`probability_kind`, `p_x_odds`, `started`, `source` (the source row
verbatim); official `builders[]` likewise.

`multi_coupon_settled.json` (`settle_multi_coupon.py`): per section
`singles` / `builders` summaries (`positions`, `settled`, `won`, `lost`,
`not_counted`, `units`, `roi`) and `rows` (each position with `outcome`),
and `variant_total` - the variant's own total, never added to 7c / 7d.

## `runs/sofa/ledger/results.jsonl` — the ledger

One JSON row per (`date`, `variant`), written by `record_results.py` (a
re-run replaces the date's rows), read by `audit_ledger.py` - per variant,
never pooled. Variants: `official` (7c), `wariant` (7d), `sport:<sport>`,
`multi`, `rule:<sport>`, `measure:<sport>`.

- official / wariant: `singles`, `builders`, `total` (the summary above),
  `pending`, `settled_rows_in_db`, `outcomes` (count per grade),
  `estimated_builders` (builders graded at `odds_if_product` x haircut because
  no screen price was recorded - 7c's "(szac.)"; not a price Superbet
  printed) and `by_match`.
- `sport:<sport>`: `total`, `by_family`, `pending`, `outcomes`, `by_match`.
- `by_match` (since 2026-10-01): `{match: [units, settled]}` (`sofa:<id>` /
  `sb:<id>`) - the cluster `audit_ledger` resamples. Its ROI interval is a
  bootstrap **by match** (legs of one match share its game script), `-` under
  20 matches (`clv.MIN_CLUSTERS`) and `- (no per-match record)` when a day
  with settled positions predates the field. `audit_clv` uses the same
  cluster rule.
- `multi`: `total` (= `variant_total`), `sections` (a summary, or
  `{"excluded": reason}`), `pending`, `outcomes`, `estimated_builders`,
  `by_match`.
- `rule:<sport>`: the price-only rule replayed on the day (one side per
  event, chosen before the outcome, at the last pre-start price) - `total`,
  `by_family`, `graded_at`. Its record even on a day without a coupon.
- `measure:<sport>`: `events` (count per SETTLE state), `favourite_side`
  (TWO-WAY lines only, so comparable across the 09-30 cutover: `events`,
  `sides`, `mean_fair_p`, `hit`, `gap_pp`, `brier`, `roi`, `median_margin`),
  `by_shape` (two / three / exact), `by_family`, `players` (player lines,
  never in `favourite_side`), `retryable`.

Exit of `record_results.py`: 0 recorded (pending shown, not failed), 1 a
`MISMATCH` or an unreadable file, 2 a crash or a missing database (nothing
written). A run that read no data at all never replaces a graded row (`KEPT`
on stderr); any run that read data does, also when a regrade removed a result.

## `vetoes.json` — `Veto[]`

`sofascore_event_id` (int, required), `market`, `subject`, `line`,
`direction` (all nullable, `null` = all), `reason_class`
(`SAMPLE_UNINFORMATIVE | CONTEXT | PRICE | OTHER`), `reason` (free text, and
the operator reads it), `context` (optional; only with `CONTEXT`:
`MOTIVATION | ROTATION | ABSENCES | DERBY | SCHEDULE | CONDITIONS`).

Every vetoed row is still settled; `audit_settlement` section 7e and
`scripts/sofa/audit_vetoes.py --from --to` grade what the vetoes removed, per
class and tag, against the rest of the board at the same price bands.

Read by **COUPON and CONFIDENCE both**. Write it after SHEET and before either.

## `reads.json` — `LegRead[]` (since 2026-10-04)

`sofascore_event_id` (int), `market`, `subject`, `line`, `direction` (all
nullable, matched like a veto), `verdict` (`KEEP | WATCH | NO_BET`),
`author` (`analyst | verifier`), `reason` (non-empty), `context` (optional,
the veto's tags). Strict, `extra="forbid"`: one bad entry fails the file and
COUPON / CONFIDENCE with it. `NO_BET` refuses the row in every profile
(`READ_NO_BET`), `WATCH` only where the profile honours it - COUPON and the
official CONFIDENCE (`WATCHED`); the WARIANT keeps the leg and writes the
covering reads on it as `reads: [{verdict, author, reason}]`. CONFIDENCE's
summary carries `reads_applied`, `reads_unmatched`, `read_rungs`; each
unmatched read is `UNMATCHED_READ` on stderr. Appended to, never edited:
the analysts' reads after a provisional CONFIDENCE, the verifier's after
verification. `audit_variants` C1 counts it in freshness, C3 (days from
2026-10-05) requires an analyst's read on the best 30 printed official
singles and every printed builder leg (`confidence.legs_requiring_read`).

## The log

`runs/sofa/run.log.jsonl` — one JSON row per request, carrying `run_id` and the
stage that declared it (`src/bet/sofa/stage.py`). The stage is a context
variable set once at the top of each `run_*.py`, not a literal per client
method: `entity_events` is called by RESOLVE *and* SAMPLES, and when it was a
literal, 8.2% of SAMPLES' cost was filed under RESOLVE. A request with no
declared stage logs as `CLIENT`, deliberately not a real stage name, so it is
visible rather than misfiled.
