# The stages — what each one does, what it costs, how it fails

Source of truth: `DEFAULT_SEQUENCE` in `scripts/sofa/run_pipeline.py`. Fifty
lines; read them rather than guessing.

Every stage is runnable on its own against the artifacts already on disk.
`run_pipeline.py` only sequences them, and a stage that raises fails **that
stage**, not the run (`STAGE_EXCEPTION` on stderr, exit 2 for that stage) —
unless `--stop-on-failure` was asked for.

```
--date YYYY-MM-DD        default: today, UTC
--only STAGE             run just this one, in or out of the daily sequence
--from-stage STAGE       resume here, reusing what is on disk
--run-id ID              reuse an id instead of minting one (for resuming)
--stop-on-failure        abort at the first FAILED stage
```

`SOFA_RUN_ID` is minted **before** the stages run and exported, so every log
row of a run carries it. Resuming without `--run-id` splits one day into two
runs in `runs/sofa/run.log.jsonl`.

---

## BOARD (E3) — `src/bet/sofa/board.py`, `scripts/sofa/run_board.py`

The day off Superbet's board. **One** HTTP request, no Sofascore, no bridge,
under a second. This is what `simple` called discovery.

Filters out: sports outside `SPORT_IDS` (`football: 5`, `tennis: 2` — nothing
else exists here), tennis doubles (a `/` in the match name), kickoffs outside
the day, and tournaments listed in `config/sofa_board_exclusions.json`.

Superbet sends **no competition name at all**, only `tournament_id` /
`category_id`. "Which competition is this" is not answerable until RESOLVE.

*Trap:* board size swings with the weekday, hard. 2026-09-20 (Sunday) put
**1040** football fixtures up; 2026-09-21 (Monday) put **102**. That is the
calendar, not a fault. Verify against Superbet's raw response before reporting
a problem.

Because BOARD touches only Superbet, it can run while SETTLE is still using
the bridge.

## RESOLVE (E4) — `src/bet/sofa/resolve.py`

Attaches `sofascore_event_id` to each board fixture. **Through the bridge**,
~8 requests per fixture — the second most expensive stage.

Emits `identity: CONFIRMED | FUZZY`, and gaps `NO_MATCHING_EVENT`,
`AMBIGUOUS_ENTITY`, `NO_ENTITY_FOUND`. **A healthy match rate is 72–90%.**
That number, not the coverage floor, is how you tell a broken matcher from a
quiet day.

Writes **both clocks** — `kickoff_utc` (Sofascore) and `superbet_kickoff_utc` —
plus `kickoff_disagreement_h`. Not redundancy: for ITF tournaments Sofascore
appears to publish the tournament's *local* time as though it were UTC, and the
gap reaches **11 h**. The error runs the wrong way — a finished match looks
upcoming. Superbet's clock is the one that decides whether a market is open,
because Superbet is who accepts the bet.

RESOLVE is **additive**: re-running it late in the day adds fixtures rather
than replacing the set. It was not, once, and a 21:30 re-run turned 491
fixtures into 408.

A negative cache remembers "we looked and found nothing", stamped with
`MATCH_LOGIC_VERSION`. Bump that constant whenever matching logic changes in a
way that could turn a miss into a hit — otherwise a fix is invisible, because
RESOLVE never asks again.

## OFFER (E5) — `src/bet/sofa/offer.py`

Superbet, public, unmetered, quick. **Runs twice per day, by design.**

```
--min-minutes-to-kickoff N    only price fixtures at least N minutes out
```

Use it on a late refresh. Without it the stage re-prices the whole board
including matches already played: on 2026-09-20 that was 890 finished fixtures
paid for to reach the 185 still open, at ~90 minutes for a full pass.

Per fixture: `status: PRICED | NO_PRICE`, `rungs[]` each with
`fetched_at_utc`, and `unmapped_markets[]`. That last list is routinely
enormous — **21,290 on 2026-09-21**. We read roughly a tenth of Superbet's
screen and that is a known state, not a fault.

`price_collisions[]` records where two Superbet listings of the same match
quoted one rung differently. Empty is normal; non-empty means the price used
was *chosen*, not inherited from whichever listing came last.

**Three classifiers, tried in this order** (`market_mapper.py`), because the
three families put the subject in different places:

1. `classify_market` — the subject is in the **market name**
   (`"Criciúma - liczba goli"`, `"1. set - Kenta Kawada liczba gemów"`), the
   line in `specialBetValue`, the direction in the selection.
2. `classify_derived_market` — both-teams / comparative / handicap. The
   subject and the line are on the **selection**.
3. `classify_player_market` (F54) — football player counts. One market name
   (`"Zawodnik - liczba strzałów"`) covers the whole squad; the player, the
   line and the direction are all on the selection, and `specialBetValue`
   reads `sr:player:<sportradar id>-<Name>-<line>`. The line is parsed from
   the **end** so a hyphenated surname cannot be read as the separator. That
   Sportradar id maps to nothing we hold — the player is identified by name
   (`players.match_player`, threshold 85 with a margin of 5).

Player market names are matched **exactly**, never by prefix. Superbet prices
eight body-part and location variants of the same quantity
(`"liczba strzałów lewą nogą"`, `"liczba celnych strzałów spoza pola karnego"`)
and Sofascore's `/lineups` reports none of them; a prefix rule would price a
left-footed shot line off a total-shots sample.

**Football player markets are quoted on ONE side only** — 437 "powyżej" and
**0** "poniżej" across the whole 2026-09-22 board. So the rung carries
`over_odds` and no `under_odds`, nothing devigs, `market_p` is `None`, and
SHEET stops the row at `LEAN` with `NO_PRICE_ANCHOR`. **No football player
prop can reach the coupon today, and that is deliberate** — it is the family
the settled record calls unchecked, not a gate to tune away. Tennis's
per-player set games *are* two-sided and can reach it.

## SAMPLES (E6) — `src/bet/sofa/samples.py`

Each side's last N matches per metric. **Through the bridge, ~12 requests per
fixture — this is most of the run's wall clock.** At 0.5 req/s, well over an
hour.

Reads `04_offer.json` and samples only metrics somebody prices; it falls back
to a live Superbet call only for a fixture the artifact does not cover. Before
that fix the pre-sample OFFER had no reader at all — it wrote the artifact,
nothing opened it, the second pass overwrote it, and its only effects were ~600
requests a day and the ability to fail the run.

Per fixture: `readiness: READY | PARTIAL | BLOCKED`, `metrics{}` and `gaps[]`.
Observations carry `sofascore_event_id`, `match_date_utc`, `opponent`, `value`,
`competition_id`, `season_id`, `venue`.

`GapReason` vocabulary: `NO_ENTITY_FOUND`, `AMBIGUOUS_ENTITY`,
`NO_MATCHING_EVENT`, `EVENT_NOT_FINISHED`, `NO_STATISTICS`, `NO_INCIDENTS`,
`STAT_KEY_ABSENT`, `ALL_ZERO_SAMPLE`, `OUTSIDE_MODEL_RESOLUTION`,
`INTERNAL_INCONSISTENT`, `THIN_SAMPLE`, `SURFACE_UNKNOWN`, `NO_PRICE`,
`STALE_PRICE`, `PROVIDER_ERROR`, `CIRCUIT_OPEN`.

`SURFACE_UNKNOWN` is the tennis one and it is the honest version of a silent
failure: the surface scope compares `event.groundType` against
`fixture.ground_type`, and when the fixture's is null the comparison cannot
match and the sample was never scoped at all. Named rather than passed over.

*Trap — the coverage floor is weekday-blind.* `src/bet/sofa/coverage.py`
compares a **share** against the median of the last 10 runs, per sport, and
calls a drop of more than 40% a matching regression. Its median is built from
whatever days happen to be recent, so a Monday against three weekends trips it
every time. **Check the RESOLVE rate first** — 72–90% is healthy — before
believing it.

Know what the share is a share *of*: the denominator is `02_fixtures.json`,
which is **RESOLVE's own output**, not `01_board.json`. So it measures
sampling, not name-matching — deliberately, because RESOLVE reports recall
separately and conflating the two hides both. The cost of that choice is that
a name-matching regression shrinks numerator and denominator together and this
floor stays flat through it. **`coverage_floor` is not a matching alarm; the
RESOLVE rate is.**

Sample pages are read **descending**; they were read ascending once, which made
"the last ten matches" mean the ten oldest and put sample freshness at 154 days
instead of 5.

## SHEET (E8) — `scripts/sofa/run_sheet.py`, `src/bet/sofa/engine.py`

The pricing. One row per rung; see `arithmetic.md` for the chain.

`notes[]` vocabulary actually observed on a day (2026-09-21, 5,674 rows):

| note | rows | meaning |
|---|---|---|
| `UNFITTED_CONSTANTS` | all | `K_PRICE` / `MAX_LADDER_SIGMA` are not fitted. **Never strip this** — it is the row saying it has no calibration. |
| `PRICE_GAP` | 1404 | our `p_central` and the devigged price disagree materially |
| `DERIVED` | 1024 | a joint/comparative market (`both_over_*`, `handicap_*`, `most_*`) |
| `UNREACHABLE_BAR` | 654 | no price on the ladder could clear the bar — structural, not a judgement |
| `NO_MARKET_MARGINAL` / `_CHECK` | 154/155 | the other side was not quoted, so no devig was possible |
| `ONE_SIDED_LADDER` | 72 | ditto, at ladder level |
| `NO_LADDER_CHECK` | 81 | the ladder could not be measured. Only **52.4%** of ladders can be; `sets_total` and `aces_*` were **0%**. |
| `LADDER_SPREAD_DISAGREES` / `LADDER_DISAGREES` | 36/8 | our centre sits away from the book's whole ladder |
| `NO_PRICE_ANCHOR` | 17 | nothing to anchor against |

`bar_reason` ∈ `none | laplace_cap | p_low_cap` — which cap, if any, held
`p_central` back.

Verdicts: `VALUE | LEAN | BELOW_BAR | NO_PRICE | BLOCKED`.

## COUPON (E9) — `src/bet/sofa/coupon.py`, `scripts/sofa/run_coupon.py`

Selects singles from VALUE rows and **records every exclusion** in
`06_dropped.json`. Nothing here recomputes a probability.

```
--max-singles N     cap the day's rows. Default: no cap.
```

A cap that binds does not trim the worst rows, it trims whichever sort last —
on 2026-09-18 it dropped 738 of 920 VALUE rows across 131 fixtures the sheet
had already passed.

Gates, in order, each with its own `06_dropped.json` reason:

| reason | gate |
|---|---|
| `NO_FIXTURE` | the row's event id is not in `02_fixtures.json` |
| `KICKOFF_TOO_SOON` | `min(kickoff_utc, superbet_kickoff_utc)` is not more than 15 min out. **The earlier of the two clocks**, deliberately — see RESOLVE. |
| `ODDS_TOO_LOW` | below `MIN_ODDS_FLOOR = 1.25` |
| `VETOED` | matched an entry in `vetoes.json` |
| `STALE_PRICE` | no `fetched_at`, or older than `price_max_age_min` (45) |
| `DISAGREES_WITH_PRICE` | `p_central − market_p > MAX_DISAGREEMENT = 0.10`. **Measured, not cautious**: past +0.10 the realised rate falls BELOW a coin flip while the claim keeps climbing (+0.30 and up: claims 0.800, realises 0.451 over 328 rows). Until 2026-09-21 this gate existed only on the staked path, so the singles file was the *more permissive* of the two products. It is now routinely the largest single reason a day's coupon is empty — 84 of 118 VALUE rows on 2026-09-21. |
| `ABOVE_MEASURED_CEILING` | `p_central` is at or above the top of this market's **own measured** calibration range. Only markets that *have* a curve are gated — one with no curve is unmeasured rather than contradicted. `games_won_for` has 9,286 settled rows and no bucket above 0.825, yet seven coupon rows one day claimed 0.900: not an optimistic estimate, a claim about a region the data refuses to describe. |
| `STALE_SAMPLE` | newest observation older than `MAX_SAMPLE_AGE_DAYS = 60` |
| `MAX_SINGLES` / `MAX_PER_FIXTURE` (3) | caps |
| `FAMILY_SLOT_TAKEN` | this fixture already has `MAX_PER_MECHANISM_FAMILY_PER_FIXTURE` (1) row of this mechanism family, with more surplus |
| `NO_ODDS` / `NO_SURPLUS` | a VALUE row carrying neither |

`ABOVE_MEASURED_CEILING` is the same rule CONFIDENCE applies, deliberately
shared: the two paths disagreeing about one measured fact is how a market ends
up banned from the builder and dominant in the singles.

`UNMATCHED_VETO` goes to stderr for any veto that matched nothing.

## CONFIDENCE — `src/bet/sofa/confidence.py`, `scripts/sofa/run_confidence.py`

A different question from COUPON: not "is this worth its price" but "how often
does this actually happen". Offline; reads the sheet, offer, fixtures, samples
and `vetoes.json`.

```
--date D  --floor 0.80  --runs-dir runs/sofa
```

Every number is the **lower bound** of the measured realised rate, fitted on
1,868,474 settled rows, so a thin bucket reads as less confident rather than
more precise. The curve **tops out at 0.9202** — the 0.900–0.925 and
0.925–0.950 buckets both realise 0.9083, which is the model saying it has run
out of resolution. There is no 98% leg.

Leg refusal vocabulary (the `refused` counter in the stage summary):
`NO_PRICE`, `ODDS_TOO_LOW` (below `1/0.9202 = 1.0867` — below that a leg
cannot have positive EV under this curve, whatever the fixture), `NO_FIXTURE`,
`VETOED`, `KICKED_OFF`, `NO_FETCHED_AT`, `STALE_PRICE`,
`NOT_IN_CALIBRATION_FIT`, `DERIVED_NOT_CALIBRATABLE`, `NOT_CALIBRATED`,
`BELOW_CONFIDENCE_FLOOR`, `DISAGREES_WITH_PRICE`, `NEGATIVE_LEG_EV`,
`LINE_BEYOND_SAMPLE`, `MODE_LOSES`, `THIN_SAMPLE_FOR_BUILDER`,
`SAMPLE_CROSSES_SEASON` (oldest observation over 180 days), `STALE_SAMPLE`
(newest over `MAX_SAMPLE_AGE_DAYS = 60` — **the same constant COUPON uses**,
shared since 2026-09-21 so the staked path can never again be the more
permissive one), `BUILDER_LEGS_INCOHERENT`.

`NOT_CALIBRATED` is the big one and it is the honest refusal: neither the
market's own curve nor the pooled one covers that bucket, so the leg is
refused rather than served the model's own number. **A market with its own
curve may not borrow the pooled curve above the top of its own measured
range** — silence above a market's ceiling is evidence, not a gap. The sport's
own pool (`pooled:tennis`) is tried before the global one, because the global
pool is almost entirely football counts.

Empirical-frequency metrics (`sets_total`, `games_won_for`,
`games_won_set{1,2,3}_for`) are **no longer
banned** from the fit: they carry measured curves, capped at their own ceiling.
They were banned once, and the ban deleted tennis from the good path while
`games_won_for` — 1,084 of a Monday sheet's 3,026 tennis rows — remained the
largest component of the VALUE path, whose measured ROI is negative.

Builders: same fixture, **one leg per quantity family** (a team's goals and
the match total are one quantity counted twice — measured lambda 2.165), 2–4
legs, ranked by **leg EV** not by confidence — **at both levels**: the family's
representative (`best_leg_per_quantity`) and the ordering of the pool. Ranking
by confidence is ranking by shortness of price, and that was the root of the
2026-09-20 defect. Fixing only the pool ordering left it alive one level down:
replayed over 2026-09-19's 5,334 legs, choosing the representative by
confidence put a **negative**-EV leg into 530 family slots that had a better
one available.

A slip is stakeable when `is_stakeable(b)` — `best_for_fixture` **and**
`ev_after_haircut > 0`. Report `stakeable_builders`, not `builders`; both are
in the summary since 2026-09-21 precisely because they disagree.

## PDF — `scripts/sofa/build_coupon_pdf.py`

```
--date D  --runs-dir runs/sofa  --out PATH
```

Renders only slips passing `is_stakeable`. **`picks: 0` is a legitimate and
frequent answer.** Needs `reportlab`, which is in `dependencies`.

## SETTLE (E10) — `src/bet/sofa/settle.py`

Grades a **finished** day. Running it against today finds every fixture
unfinished. It is the only writer that puts a Superbet price next to an
outcome, and therefore the only source `fit_k_price` and `MAX_LADDER_SIGMA`
can ever fit from.

```
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only SETTLE

# --include-unpriced belongs to run_settle.py, not to run_pipeline.py, so it is
# only reachable by invoking the stage script directly:
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_settle.py --date <D-1> --include-unpriced
#     also grades rows Superbet never quoted
```

`PARTIAL` is the normal verdict — unfinished matches and provider stat gaps.

## FIT (E11) — `scripts/sofa/fit_constants.py`

**Not in `DEFAULT_SEQUENCE`.** A deliberate, separate step. Re-fitting mid-day
breaks comparability with yesterday's run.

```
--db-path data/sofa.db  --config-dir config
```

Writes `config/sofa_engine_constants.json`, `sofa_league_baselines.json`,
`sofa_market_reliability.json`. A constant with no data is written `null` with
`status: NOT_FITTED`, never a borrowed default. Always check the
`fitted_from` metadata and `half_match_coherence` — a stale baselines file
shipped a corners prior 24–32% too high for two days before anyone noticed.

`calibrate_from_cache.py` inserts replayed rows; it does **not** own
`sofa_market_reliability.json` (`--out` writes an ungated curve for inspection
only). Two writers on one file meant whichever ran last won, and the first time
that happened an empty file overwrote a measured one and reported success.

## Audits

| script | question |
|---|---|
| `audit_coupon.py --date D` | structure, arithmetic re-derived from each row's own fields, anti-selection distributions. Exit 1 = findings. |
| `audit_settlement.py --date D` | of everything forecast, how much came in and why not. **Section 7c is the PDF coupon's real result**; 7 and 7b are input material, not bets. |
| `audit_day_deep.py --date D` | per market: was the miss systematic or dispersion; and would today's gates still have made yesterday's bet |
| `audit_sample_bias.py --date D` | does the sample measure what the book settles |

## Pre-commit gates

```bash
.venv/bin/python -m pytest tests/sofa -q
.venv/bin/python -m ruff check src/bet/sofa scripts/sofa
.venv/bin/python -m mypy --strict src/bet/sofa scripts/sofa
```

`ruff` and `mypy` carry a standing backlog (~100 and 129 in 10 files). Do not
compare the count against zero or against HEAD — the tree often holds someone
else's uncommitted work. Check whether the error points at a line you wrote.
`ruff` does **not** catch a duplicate in an enum; after touching one, import it.
