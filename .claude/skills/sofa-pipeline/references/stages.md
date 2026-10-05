# The stages — what each one does, what it costs, how it fails

Source of truth: `DEFAULT_SEQUENCE` in `scripts/sofa/run_pipeline.py` (BOARD,
RESOLVE, OFFER, SAMPLES, OFFER, SHEET, COUPON - it ends at COUPON) and
`STAGE_MODULES` beside it: the sequence plus SETTLE, CS2, CS2_SETTLE, SHADOW,
SHADOW_SETTLE, FIXTURE_CHECK, SPORT_IDENTITY, SPORT_CONFIDENCE and
COUPON_ASSEMBLY, each reachable with `--only`. CONFIDENCE
(`run_confidence.py`) and the PDF (`build_coupon_pdf.py`) are scripts outside
`STAGE_MODULES`: there is no `--only CONFIDENCE`. Read them rather than
guessing.

The day after the sequence (stats-only epoch, a day >= 2026-10-05 built at or
after 07:15Z, `bet.sofa.epochs`):

```
[FIXTURE_CHECK, in a rebuild] → CONFIDENCE → 08_confidence.json            football, tennis
--only SHADOW, --only CS2 → SPORT_IDENTITY → SPORT_CONFIDENCE → 08_confidence_sports.json
COUPON_ASSEMBLY → 11_coupon.json → PDF → KUPON_<d>.pdf + 12_printed.json   the coupon
```

Every stage is runnable on its own against the artifacts already on disk.
`run_pipeline.py` only sequences them, and a stage that raises fails **that
stage** as a process (`STAGE_EXCEPTION` on stderr, exit 2 for that stage).
Since 2026-10-01 a FAILED stage **stops the stages after it**: they are
reported `SKIPPED` and leave their artifacts untouched, because each reads the
one before it (that day a locked DB stopped RESOLVE at 15 of 461 fixtures and
OFFER/SAMPLES overwrote the day with those 15). `--continue-on-failure` is
the deliberate exception. A RESOLVE that raised also leaves
`02_fixtures.json.INCOMPLETE`; OFFER, SAMPLES, SHEET, COUPON, CONFIDENCE and
the PDF refuse it (`UPSTREAM_INCOMPLETE`, exit 2) until a clean RESOLVE
clears it. The DB is in WAL mode and a busy COMMIT is retried (`bet.sofa.db`).

```
--date YYYY-MM-DD        default: today, UTC
--only STAGE             run just this one, in or out of the daily sequence
--from-stage STAGE       resume here, reusing what is on disk
--run-id ID              reuse an id instead of minting one (for resuming)
--stop-on-failure        kept for old command lines; stopping is the default
--continue-on-failure    run the stages after a FAILED one anyway
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
RESOLVE never asks again. It is **6** since 2026-10-01 (Sofascore's trailing
"Reserve(s)" folds to "(r)": "River Plate Reserve" vs "CA River Plate (R)"
scored 75.9 against the 82 gate). A **verified** entity is looked up even with
a fresh miss row and never gets a miss written: its miss meant "no event for
that one fixture yet", and checked first it stopped RESOLVE asking the known
id for seven days (2026-10-01: ~26 unstarted tennis matches, Tien-Hurkacz;
Croatia U19 / Jerash in football).

A match listed twice on the board keeps the first listing's Superbet clock,
unless that is exactly 00:00:00Z and the other listing has a real time
(`merged_superbet_kickoff`): Superbet lists some ITF matches at a midnight
placeholder, and on 2026-10-01 three of them were read as started and lost all
168 priced rungs.

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

One listing that errors (a removed event's 404) is a gap, not `FAILED`
(since 2026-10-01; before, one exception failed OFFER and the chain): counted
in `fetch_errors`, verdict `PARTIAL`. A fixture whose every listing failed
gets no entry at all, so a filtered refresh keeps the previous file's prices.

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

Since 2026-10-01 `player_assists_for`, `player_shots_on_target_for` and
`player_shots_for` are priced with a negative binomial
(`engine.NEGATIVE_BINOMIAL_METRICS`): on every settled player row of
09-24..30 the normal put +8 pp median on every OVER (assists 0.5 OVER claimed
0.243, realised 0.081, n=495); dBrier NB vs normal -0.03136 / -0.01473 /
-0.00749 (n 546 / 1317 / 2379). "Liczba strzałów w obramowanie bramki" is
woodwork, not a team, and is no longer read as a side
(`_SUBJECT_IS_NOT_A_SIDE`).

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

Football friendlies are dropped here by `uniqueTournament.id` from
`config/sofa_friendly_competitions.json`: 853 Club Friendly Games, 1794 MLS
All Star Game, and 28008 Women Club Friendly Games since 2026-09-30. SAMPLES'
`SOFA_SUMMARY` carries `friendly_competitions_excluded` (3 now). Only SAMPLES
applies it: a sheet built from samples taken before an id was added still
counts those matches (look for the id in the observations' `competition_id`),
and `/sofa-rebuild` does not fix that.

Since 2026-10-02 a club's second squad filed under the first team's id is
dropped too (`src/bet/sofa/reserve_squads.py`, gap `RESERVE_SQUAD`): two of a
side's matches in a competition 6-44 h from a match of its main competition
make the whole (side, competition) pair a second squad, and
`config/sofa_reserve_competitions.json` lists competitions where sides from
named main competitions field reserves (Brazilian state cups for Serie A/B,
Copa Santa Fe for the Liga Profesional). A fixture that is itself the second
squad's leaves the side empty. The rating moves neither side on such a match.

`GapReason` vocabulary: `NO_ENTITY_FOUND`, `AMBIGUOUS_ENTITY`,
`NO_MATCHING_EVENT`, `EVENT_NOT_FINISHED`, `NO_STATISTICS`, `NO_INCIDENTS`,
`STAT_KEY_ABSENT`, `ALL_ZERO_SAMPLE`, `OUTSIDE_MODEL_RESOLUTION`,
`INTERNAL_INCONSISTENT`, `ENTITY_CONFLICT`, `RESERVE_SQUAD`, `THIN_SAMPLE`,
`SURFACE_UNKNOWN`, `NO_PRICE`, `STALE_PRICE`, `PROVIDER_ERROR`,
`CIRCUIT_OPEN`.

`provider_fault_fixtures` in the summary (since 2026-10-01) counts fixtures
that lost metrics to a provider fault with nothing to carry over; any makes
the verdict `PARTIAL`. A cached match with NULL `incidents_json` ("never
asked", not "none") is asked `/incidents` once when a card market needs it -
a 404 is stored as `{}` and read as no incidents, and a fault on that ask
costs only the card metrics (`NO_INCIDENTS`), never the match (2026-10-01:
118 gaps over 59 events, all NULL).

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

One row per rung; see `arithmetic.md` for the chain.

In the stats-only epoch every row carries `epoch: "stats_only"`, and SHEET
keeps the price out of `p_central` (K1): no tennis ladder centre, no tennis
rating blended with `market_p`, no empirical shrink to the rung's price, no
`K_DERIVED_CENTRE` handicap centre on the ladder. The rating is written beside
it as `forecast_p` / `forecast_source` (K11; uncalibrated, never a gate).
`p_bar`, `required_odds`, `surplus` and the verdict below are still computed
and still priced - they are the old selector's numbers, not the coupon's.
CONFIDENCE refuses a sheet without the stats-only epoch, so a rebuild under
the rule starts here.

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

**The old priced VALUE-singles selector, not the coupon** (the coupon is
`11_coupon.json`, COUPON_ASSEMBLY below). It stays in the sequence and
`audit_coupon.py` still audits it. Selects singles from VALUE rows and **records every exclusion** in
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
| `READ_NO_BET` / `WATCHED` | a `reads.json` entry with verdict `NO_BET` / `WATCH` covers the row (since 2026-10-04; COUPON honours WATCH like the official profile) |
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

## FIXTURE_CHECK — `scripts/sofa/run_fixture_check.py`, `src/bet/sofa/fixture_status.py`

```
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_fixture_check.py --date <d>
```

**Bridge.** In a rebuild, after OFFER and before CONFIDENCE (K12, K14). Reads
`/event/{id}` (the cache's `sofa_event_detail` first, 60 min for an unplayed
match) for every match the coupon artifact prints (`coupon_artifact`) and
every match whose Superbet start (`superbet_kickoff_seen_utc`) moved more than
30 min (`CLOCK_GAP_MIN`) from RESOLVE's Sofascore start. Writes
`runs/sofa/<d>/fixture_status.json`: per event `status`, `start_utc`, `why`
(printed / moved clock), `checked_at_utc`.

- A `postponed` / `canceled` / `cancelled` / `abandoned` match is
  `FIXTURE_NOT_AS_SCHEDULED` in CONFIDENCE (refused; a locked leg of it stays
  and SETTLE refunds it).
- A fresh `startTimestamp` replaces RESOLVE's frozen Sofascore clock for the
  kickoff gate, the lock and `capture_closing` (the earliest clock is still
  the rule).
- No bridge: every event `UNVERIFIED` - shown, never a refusal - and exit 1.
  A 403 stops the requests at once; the rest stays `UNVERIFIED`.

## CONFIDENCE — `src/bet/sofa/confidence.py`, `scripts/sofa/run_confidence.py`

A different question from COUPON: not "is this worth its price" but "how often
does this actually happen". Offline; reads the sheet, offer, fixtures,
samples, `fixture_status.json`, `vetoes.json` and `reads.json`. Football and
tennis only (the sheet's sports); writes `08_confidence.json` / `.md` - on a
stats-only day the input of COUPON_ASSEMBLY, not the coupon.

```
--date D  [--floor F]  [--runs-dir runs/sofa]
```

Leave `--floor` out: the official floor is 0.70 (`confidence.PROFILES`
`standard`: floor 0.70, `min_ev` 0.90, `max_overround` 0.15, honours WATCH).
Passing a floor builds a different experiment under the official file name.

Every number is the **lower bound** of the measured realised rate, so a thin
bucket reads as less confident rather than more precise. The curve **tops out
at 0.9202** (`CONFIDENCE_CEILING`) - the model has run out of resolution.
There is no 98% leg.

**Stats-only epoch** (`epoch: "stats_only"` on the artifact and every leg):

- refuses (exit 2) a `05_sheet.json` not built under the rule - a rebuild
  starts at SHEET;
- `MAX_DISAGREEMENT` (`DISAGREES_WITH_PRICE`) and `UNREACHABLE_BAR` are off
  (K2); `gap_shrink_k` is 0;
- a price that moved since SHEET re-prices the leg: x, the margin and
  `ODDS_TOO_LOW` are judged at the fresh odds in `04_offer.json` instead of
  `PRICE_MOVED_SINCE_SHEET` (that refusal stays for old-epoch builds);
- K13: a thin direction bucket (`thin_by_market_direction`) caps the
  two-direction `by_market` curve too (`cap_market_by_thin`), as it caps the
  pools - the lower of the two Wilson lower bounds, recorded as
  `calibrated_on: market_thin:<market>|<direction>`;
- `FIXTURE_NOT_AS_SCHEDULED` from `fixture_status.json` (else RESOLVE's own
  status); a fresh start from it feeds the kickoff clocks;
- reads, and the automatic football `MODEL_ABOVE_OWN_SAMPLE`, apply at the
  END of the chain (K6): a leg that passed every gate and a WATCH / NO_BET
  removed goes to `removed_by_reads` (with `refusal` and `reason` = the
  author(s) or `auto`), graded on its own, never in the coupon's result;
- each leg carries `forecast_p` / `forecast_source` beside `model_p`;
- singles sort by `confidence.coupon_sort_key` (confidence, earlier start,
  match, market, line - never the price);
- Bet Builders: one leg per quantity family chosen by confidence
  (`best_leg_per_quantity(..., by_confidence=True)`), the pool and the
  builders ordered by `combined_probability`, each builder carrying
  `stakeable_rule: "x>=0.90"`; stakeable = `best_for_fixture` and
  combined_probability x `odds_after_haircut` >= 0.90 (`is_stakeable`).
  The 2-, 3- and 4-leg builders are prefixes of one pool, so
  `best_for_fixture` is nearly always the 2-leg one - not a defect.

Leg refusal vocabulary (the `refused` counter): `NO_PRICE`, `ODDS_TOO_LOW`
(below `1/0.9202 = 1.0867`), `NO_FIXTURE`, `VETOED`,
`FIXTURE_NOT_AS_SCHEDULED`, `KICKED_OFF`, `NO_FETCHED_AT`, `STALE_PRICE`,
`PRICE_MOVED_SINCE_SHEET` (old epoch), `NOT_IN_CALIBRATION_FIT`,
`UNREACHABLE_BAR` (old epoch), `CROSS_LEAGUE_UNLINKED`, `FRIENDLY_FIXTURE`,
`DERIVED_NOT_CALIBRATABLE`, `OPERATOR_REFUSED`, `PLAYER_PROP_NOT_ADMITTED`,
`TENNIS_SET_MARKET_NOT_ADMITTED`, `NOT_CALIBRATED`, `NO_CLASS_CURVE`,
`CATCH_ALL_BUCKET`, `BELOW_CONFIDENCE_FLOOR`, `DISAGREES_WITH_PRICE` (old
epoch), `NEGATIVE_LEG_EV` (x = confidence x odds below the profile's 0.90),
`LINE_BEYOND_SAMPLE`, `MODE_LOSES`, `THIN_SAMPLE_FOR_BUILDER`,
`SAMPLE_CROSSES_SEASON` (oldest observation over 180 days), `STALE_SAMPLE`
(newest over `MAX_SAMPLE_AGE_DAYS = 60` - the same constant COUPON uses),
`BUILDER_LEGS_INCOHERENT`, `READ_NO_BET`, `WATCHED`, `MODEL_ABOVE_OWN_SAMPLE`
(football, n >= 5: `model_p` more than `MAX_OWN_SAMPLE_GAP = 0.15` above the
leg's `sample_hit_rate`). A single prints only on a ladder whose margin is
<= 15% (`single_is_fairly_priced`). Every leg carries `sample_hit_rate`, and
`context_flags` (`MAKEUP_FIXTURE(...)`, `LONG_LAYOFF(...)`, `CONGESTED(...)`)
- shown, never gated.

A read for a measured-sport leg matches no sheet row, so `run_confidence.py`
prints it as `UNMATCHED_READ` on stderr - expected; COUPON_ASSEMBLY applies
it (check `removed_by_reads` / the leg's `reads` in `11_coupon.json`).

`NOT_CALIBRATED` is the honest refusal: neither the market's own curve nor the
pooled one covers that bucket, so the leg is refused rather than served the
model's own number. **A market with its own curve may not borrow the pooled
curve above the top of its own measured range** - silence above a market's
ceiling is evidence, not a gap. The sport's own pool (`pooled:tennis`) is
tried before the global one. A market in `confidence.AWAITING_OWN_CURVE`
(football player props, the new per-half / saves / throw-in / goal-kick /
tackle markets, tennis `TENNIS_PER_SET_SERVE` and `TENNIS_SERVE_POINTS`)
never borrows a pool: without its own curve it is `NOT_CALIBRATED`.

Locked legs: a rebuild reads the previous coupon artifact and, in the
stats-only epoch, `12_printed.json` (the last print) too, and carries over, unchanged, every printed single and
stakeable builder whose match has started or is inside the kickoff margin
(`bet.sofa.locked_print`); a leg a rebuild drops before its start stays
dropped.

## SPORT_IDENTITY — `scripts/sofa/run_sport_identity.py`, `src/bet/sofa/sport_identity.py`

```
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_identity.py --date <d> [--sport hockey --sport cs2]
```

**Bridge**, after fresh `--only SHADOW` and `--only CS2` snapshots (it reads
D's and D+1's snapshot files). One `team/<id>/events/next/0` request per
match (cached with the events TTL); team ids from the DB read-only. Writes
`runs/sofa/<d>/sport_fixtures.json` (one record per Superbet event:
`superbet_event_id`, `sport`, `sofascore_event_id`, `home_id`, `away_id`,
`home_is_team1`, `competition_id`, `match_method`, `name_scores`,
`start_gap_h`, `matched_at_utc`, `status` `IDENTIFIED` / `NOT_IDENTIFIED` /
`DUPLICATE_*`). An `IDENTIFIED` record is pinned and never asked again;
SETTLE grades the sport leg by that pinned id. A refusal stops the run (no
retry). Exit 0; 1 an event not identified or the bridge refused; 2 no
snapshot of any sport.

## SPORT_CONFIDENCE — `scripts/sofa/run_sport_confidence.py`, `src/bet/sofa/sport_confidence.py`

```
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_confidence.py --date <d>
```

**No bridge.** Reads `sport_fixtures.json`, the SHADOW / CS2 snapshots,
`config/sofa_sport_confidence_calibration.json` (`fit_sport_confidence.py`,
between days only) and the DB read-only; writes
`runs/sofa/<d>/08_confidence_sports.json` and nothing else. Per Superbet side
of an event starting in [D 00:00Z, D+1 00:00Z): identified, not started
(earliest clock), the newest pre-start snapshot no older than
the price-age limit (`MAX_PRICE_AGE`), an allowed market
(`sport_confidence.ALLOWED_MARKETS` / `CS2_FAMILIES`), a whole outcome group;
volleyball needs a tournament with a SETTLED event in the last 14 days.
Confidence = the `realised_lo95` of the calibrated bucket of the model's p
(`score_model` / `cs2_engine`, no price); then the coupon's price filters:
floor 0.70, odds >= 1/0.9202, margin <= 15%, x >= 0.90.

Refusals: `NOT_IDENTIFIED`, `DUPLICATE_*`, `KICKED_OFF`, `STALE_PRICE`,
`MARKET_NOT_ALLOWED`, `NOT_CALIBRATED`, `BELOW_FLOOR`, `BELOW_MIN_X`, and the
volleyball tournament rule. Exit 0; 1 when a sport is `NOT_CALIBRATED` (no
file, no section, nothing admitted) or `sport_fixtures.json` is missing - the
artifact is still written and the football / tennis coupon still built; 2 a
crash.

## COUPON_ASSEMBLY — `scripts/sofa/build_coupon.py`

```
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon.py --date <d>
```

**Offline**, after CONFIDENCE and SPORT_CONFIDENCE, before the PDF. From
`08_confidence.json` (it refuses, exit 2, a missing one, a non-standard
profile, a non-stats-only epoch, or one older than `05_sheet.json` /
`vetoes.json` / `reads.json` / the calibration file) plus
`08_confidence_sports.json` where it exists, writes `11_coupon.json` and
`11_coupon.md`:

- fresh singles inside the day's UTC window in `confidence.coupon_order` -
  one block per match (`group_key` `sofa:<id>`) at the place of its best leg,
  positions 1..N;
- legs locked from the last print first, outside the numbering (sport legs
  via `coupon_sports.locked_sport_legs`);
- printed builders numbered `B1..`, named in their match's block;
- vetoes and reads applied to the sport legs here (`coupon_sports.apply_reads`);
  `removed_by_reads` from both sources;
- `read_requests` copied from `read_requests.json`, each with the positions
  it `covers`; a request covering nothing is `UNMATCHED_READ_REQUEST` on
  stderr; an unreadable file (or an entry without `requested_by` / `at_utc`)
  is exit 2.

Exit 0; 1 when `08_confidence_sports.json` is missing (football / tennis
coupon still assembled); 2 a refusal.

## PDF — `scripts/sofa/build_coupon_pdf.py`

```
--date D  --runs-dir runs/sofa  --out PATH
```

On a stats-only day it renders `11_coupon.json` (`coupon_artifact`) and
refuses a stats-only `08_confidence.json` without it. Guards (exit 2):
`STALE_CONFIDENCE` - `08_confidence.json` older than `05_sheet.json`,
`vetoes.json`, `reads.json` or `config/sofa_confidence_calibration.json`;
`STALE_COUPON` - `11_coupon.json` older than `08_confidence.json`,
`08_confidence_sports.json` or `read_requests.json`. Then it writes
`runs/sofa/<d>/12_printed.json` (`locked_print.PRINTED_MANIFEST`: the 11
document + `pdf`, `pdf_rendered_at_utc`) - only for the day's own PDF, never
for an `--out` render. The next rebuild locks from it, so **a provisional
PDF locks legs** whose match then starts.

Every single prints; builders on their own pages B1.., referenced in the
match block; locked legs in their own section; a column "model"
(`forecast_p`) beside "pewność". Marks, never enforced: `ta sama drabina: N`,
`start przed renderem PDF`; a builder prints only `kurs po narzucie`, never
the product of its legs' prices. Rendered to a temporary file and moved into
place. Needs `reportlab`.

Retired 2026-10-05: `--profile wariant` (and `run_confidence.py --profile
wariant`) is refused for builds after 07:15Z; historical WARIANT files of
earlier days stay.

## SETTLE (E10) — `src/bet/sofa/settle.py`, `scripts/sofa/run_settle.py`

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

- A match whose Sofascore start moved more than 48 h (`VOID_AFTER`) from the
  earliest clock the pipeline held (`MOVED_BEYOND_VOID`) or with an awarded result (`AWARDED`) is a **refund**
  (0 u.) - never a loss, never a `sofa_settled_row`; recorded in
  `07_settle_skips.json` (`settle.REFUND_REASONS`).
- A player prop is graded only from the player's own squad (the side SAMPLES
  found him in); a candidate in the other squad within the matcher's margin,
  or a hit in both when no side is known, is `PLAYER_AMBIGUOUS`, never a
  guess.
- A printed leg the final sheet has no row for is graded into
  `07_settled_printed.json` (`settle.PRINTED_SETTLED_FILE`), never into
  `sofa_settled_row`.
- Measured-sport legs never reach `sofa_settled_row` or `fit_confidence`;
  they are graded from the sport's `settled.json` (SHADOW_SETTLE /
  CS2_SETTLE) against the id pinned in `sport_fixtures.json`
  (`NOT_GRADED:ID_CHANGED` otherwise). `audit_settle_identity.py` checks the
  pins after the D-1 settle.

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
Since 2026-10-01 it collapses duplicate listings (`one_listing_per_match`),
so a match listed under two ids is no longer settled against a sample holding
itself.

Since 2026-10-01 `fit_confidence.py`'s curves and `fit_constants.py`'s
K_CENTRE scoring skip the derived markets (`both_over_`, `handicap_`, `most_` - `is_derived`), which SETTLE
grades by side and the old scoring read as "actual > line" (disagreeing with
the stored outcome on 351/1243 handicap and 197/431 most rows of 09-30), and
K_CENTRE is scored on a prior that leaves the scored match out
(`leave_match_out_prior`; the written baselines keep every match). The files
in `config/` change only at the next between-days refit. Fit outputs are
written atomically.

## Audits

| script | question |
|---|---|
| `audit_coupon.py --date D` | structure, arithmetic re-derived from each row's own fields, anti-selection distributions. Exit 1 = findings. |
| `audit_settlement.py --date D` | of everything forecast, how much came in and why not. **Section 7c is the PDF coupon's real result** (on a stats-only day per sport x epoch, measured sports graded at the printed price, refunds apart); 7i the legs `removed_by_reads`; 7 and 7b are input material, not bets. |
| `audit_day_deep.py --date D` | per market: was the miss systematic or dispersion; and would today's gates still have made yesterday's bet |
| `audit_sample_bias.py --date D` | does the sample measure what the book settles |
| `audit_variants.py --date D` | C1 freshness, C2 every printed single obeys its dials, C3 every leg in `legs_requiring_read` has an analyst read, U1 the order of 11 = `coupon_order`, U2 every fresh football / tennis single is stats_only, U3 every fresh sport leg re-derived from the raw Superbet snapshot. Exit 0 / 1 findings / 2 bad file. |
| `audit_settle_identity.py --from D --to D` | the measured sports' pinned ids: `ID_USED_TWICE`, `MOVED_GRADED`, `NAME_BELOW`, `ORIENTATION_IDS`, `ID_CHANGED`, `IDENTITY_STATE`, `IDENTITY_PENDING`. Exit 0/1/2. |

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
