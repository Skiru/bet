# The stages - what each one does, what it costs, how it fails

Read this when you run, debug or explain one stage. Which switches and model
packages a day's stages run under: `references/model-state.md`. Command
lines beyond the ones here: `references/commands.md`.

Source of truth: `DEFAULT_SEQUENCE` in `scripts/sofa/run_pipeline.py` (BOARD,
RESOLVE, OFFER, SAMPLES, OFFER, SHEET, COUPON) and `STAGE_MODULES` beside it
(the sequence plus SETTLE, CS2, CS2_SETTLE, SHADOW, SHADOW_SETTLE,
FIXTURE_CHECK, SPORT_IDENTITY, SPORT_CONFIDENCE, COUPON_ASSEMBLY - each
reachable with `--only`). CONFIDENCE (`run_confidence.py`) and the PDF
(`build_coupon_pdf.py`) are scripts outside `STAGE_MODULES`: there is no
`--only CONFIDENCE`.

```
--date YYYY-MM-DD        default: today, UTC
--only STAGE             just this one
--from-stage STAGE       resume here, reusing what is on disk
--run-id ID              reuse an id (resume without it splits one day into two runs in runs/sofa/run.log.jsonl)
--continue-on-failure    run the stages after a FAILED one anyway (--stop-on-failure is the default, kept for old lines)
```

A stage that raises fails that stage (`STAGE_EXCEPTION`, exit 2) and the
stages after it are `SKIPPED`, artifacts untouched. A RESOLVE that raised
leaves `02_fixtures.json.INCOMPLETE`; the stages after it refuse it
(`UPSTREAM_INCOMPLETE`, exit 2) until a clean RESOLVE. `run_pipeline.py`
refuses `SOFA_NOW` (replays only). Every artifact is written atomically
(`src/bet/sofa/atomic.py`).

## BOARD - `scripts/sofa/run_board.py`, `src/bet/sofa/board.py`

One Superbet request, no bridge, < 1 s - this is discovery. Keeps football
(Superbet sport 5) and tennis (2); drops tennis doubles, kickoffs outside the
day and tournaments in `config/sofa_board_exclusions.json`. Superbet sends no
competition name, only `tournament_id` / `category_id`. Board size is the
calendar (1,040 on a Sunday, 102 on a Monday).

## RESOLVE - `scripts/sofa/run_resolve.py`, `src/bet/sofa/resolve.py`

Attaches `sofascore_event_id` to each board fixture through the bridge
(~8 requests a fixture). `identity: CONFIRMED | FUZZY`; gaps
`NO_MATCHING_EVENT`, `AMBIGUOUS_ENTITY`, `NO_ENTITY_FOUND`. **A healthy match
rate is 72-90%** - that, not the coverage floor, tells a broken matcher from a
quiet day. Writes both clocks (`kickoff_utc` Sofascore, `superbet_kickoff_utc`)
and `kickoff_disagreement_h`. Additive: a late re-run adds fixtures, never
replaces the set. A negative cache is stamped with `MATCH_LOGIC_VERSION` (7,
`bet.sofa.config`) - bump it when matching logic changes or a fix stays
invisible. A verified entity is looked up even with a fresh miss row. A match
listed twice keeps the first listing's clock unless it is a 00:00:00Z
placeholder (`run_resolve.merged_superbet_kickoff`). A verified side's only
football game within 1 h of Superbet's start is taken by the football day
anchor (`resolve.football_day_anchor_event`).

## OFFER - `scripts/sofa/run_offer.py`, `src/bet/sofa/offer.py`

Superbet, no bridge. Runs twice: before SAMPLES (so nothing unpriced is
sampled) and after (a fresh price). `--min-minutes-to-kickoff N` skips
fixtures starting sooner (rebuilds use 20). Every reader builds its fetcher
from `offer.day_flags(date)`, so the day's market switches apply alike.

Per fixture `status: PRICED | NO_PRICE`, `rungs[]` with `fetched_at_utc`,
`unmapped_markets[]` (~21-28k a day: we read about a tenth of the screen),
`price_collisions[]` (two listings quoting one rung differently - the price
was chosen). A listing that errors is a gap (`fetch_errors`, `PARTIAL`); a
fixture whose every listing failed gets no entry, so a filtered refresh keeps
the earlier prices. Every run also writes the unread markets' prices to
`unmapped_prices/<ts>.jsonl.gz` (read by nothing).

Classifiers in order (`market_mapper.py`): `classify_market` (subject in the
market name), `classify_derived_market` (both-teams / comparative / handicap:
subject and line on the selection), `classify_player_market` (football
player counts: player, line and direction on the selection; the player found
by name - `players.match_player`, then whole tokens, then surname + first-name
prefix). Player market names match exactly, never by prefix (Superbet prices
body-part and location variants Sofascore's `/lineups` does not report).
**Football player markets are quoted OVER only**: no devig, `market_p` null;
such a leg prints as a one-sided single when its own curve has n >= 300
(`confidence.one_sided_single`, `one_sided_market: true`).

## SAMPLES - `scripts/sofa/run_samples.py`, `src/bet/sofa/samples.py`

Each side's last N matches per priced metric, through the bridge (~12
requests a fixture) - most of the run's wall clock. Reads `04_offer.json`;
falls back to a live Superbet call only for a fixture it does not cover. Per
fixture `readiness: READY | PARTIAL | BLOCKED`, `metrics{}`, `players{}`,
`gaps[]`. Friendlies are dropped by `uniqueTournament.id`
(`config/sofa_friendly_competitions.json`, SAMPLES only - an older sample
still holds them); a club's second squad filed under the first team's id is
dropped (`src/bet/sofa/reserve_squads.py`, `config/sofa_reserve_competitions.json`,
gap `RESERVE_SQUAD`). A footballer's sample is his starts.

`GapReason`: `NO_ENTITY_FOUND`, `AMBIGUOUS_ENTITY`, `NO_MATCHING_EVENT`,
`EVENT_NOT_FINISHED`, `NO_STATISTICS`, `NO_INCIDENTS`, `STAT_KEY_ABSENT`,
`ALL_ZERO_SAMPLE`, `OUTSIDE_MODEL_RESOLUTION`, `INTERNAL_INCONSISTENT`,
`ENTITY_CONFLICT`, `RESERVE_SQUAD`, `ZERO_NOT_RECORDED`, `CARDS_NOT_RECORDED`,
`THIN_SAMPLE`, `SURFACE_UNKNOWN` (tennis fixture with no surface - the sample
was never surface-scoped), `NO_PRICE`, `STALE_PRICE`, `PROVIDER_ERROR`,
`CIRCUIT_OPEN`. `provider_fault_fixtures` > 0 makes the verdict `PARTIAL`.
The coverage floor (`src/bet/sofa/coverage.py`) is weekday-blind and its
denominator is RESOLVE's output - it is not a matching alarm.

## SHEET - `scripts/sofa/run_sheet.py`, `src/bet/sofa/engine.py`

One row per rung; the chain is in `arithmetic.md`. Parses the whole football
history (~10 min when listings changed, ~30 s from the pickle in
`data/cache/`) - a quiet SHEET is parsing; do not kill it. Every row carries
`epoch: "stats_only"`, `p_central` without the price, `forecast_p` /
`forecast_source`, `config_sha` (the fitted files it read) and a marker per
rule it priced under (`link_rule`, `dispersion_rule`, `k_rule`, ... -
`references/model-state.md`). CONFIDENCE refuses (exit 2) a sheet not built
under the stats-only rule (`epochs.sheet_epoch`). `rebuild_day.py` re-runs
SHEET when a marker of a switch on for the day is missing; a sheet priced on
other fitted constants gets `CONFIG_CHANGED` and is **not** re-run.

`notes[]`: `UNFITTED_CONSTANTS` (every row - never strip), `PRICE_GAP`,
`DERIVED`, `UNREACHABLE_BAR`, `NO_MARKET_MARGINAL` / `_CHECK`,
`ONE_SIDED_LADDER`, `NO_LADDER_CHECK` (the ladder could not be measured -
passed without the test), `LADDER_SPREAD_DISAGREES` / `LADDER_DISAGREES`,
`NO_PRICE_ANCHOR`, and rule notes (`PLAYER_STARTS_ONLY`, `PLAYER_NAME_TOKENS`,
`PLAYER_NAME_SURNAME`, `PRIOR_MEN_FRIENDLY`, ...). `bar_reason` ∈ `none |
laplace_cap | p_low_cap`. Verdicts (old selector): `VALUE | LEAN | BELOW_BAR |
NO_PRICE | BLOCKED`. A refusal by format: `BEST_OF_FIVE_NOT_MODELLED`
(`sets_total` on a fixture not known to be best of three).

## COUPON - `scripts/sofa/run_coupon.py`, `src/bet/sofa/coupon.py`

**The old priced VALUE-singles selector, not the coupon.** Stays in the
sequence; `audit_coupon.py` audits it. Selects from VALUE rows and records
every exclusion in `06_dropped.json`. `--max-singles N` caps the day (a binding
cap trims whatever sorts last, not the worst). Reasons, in order:
`NO_FIXTURE`, `KICKOFF_TOO_SOON` (earlier clock, 15 min), `ODDS_TOO_LOW`
(`MIN_ODDS_FLOOR` 1.25), `VETOED`, `READ_NO_BET` / `WATCHED`, `STALE_PRICE`
(45 min), `DISAGREES_WITH_PRICE` (`MAX_DISAGREEMENT` 0.10 - past it realised
fell below a coin flip), `ABOVE_MEASURED_CEILING` (p at or above the market's
own measured range - the rule CONFIDENCE shares), `STALE_SAMPLE`
(`MAX_SAMPLE_AGE_DAYS` 60), `MAX_SINGLES` / `MAX_PER_FIXTURE` (3),
`FAMILY_SLOT_TAKEN` (`MAX_PER_MECHANISM_FAMILY_PER_FIXTURE` 1),
`NO_ODDS` / `NO_SURPLUS`. `UNMATCHED_VETO` on stderr.

## FIXTURE_CHECK - `scripts/sofa/run_fixture_check.py`, `src/bet/sofa/fixture_status.py`

Bridge; in a rebuild after OFFER, before CONFIDENCE. Reads `/event/{id}` (the
cached `sofa_event_detail` first, 60 min for an unplayed match) for every
printed match, every match whose Superbet start moved more than
`CLOCK_GAP_MIN` 30 min, and candidates not yet printed (`--max-candidates N`).
Writes `fixture_status.json`. Postponed / canceled / cancelled / abandoned /
interrupted / suspended / willcontinue = `FIXTURE_NOT_AS_SCHEDULED` in
CONFIDENCE (a locked leg stays; SETTLE refunds it). A fresh start replaces
RESOLVE's clock for the kickoff gate, the lock and `capture_closing`. A
transient error (504 / timeout / 5xx) is retried once, then that fixture alone
is `UNVERIFIED`; a refusal (403 / 429, breaker) or two fixtures in a row given
up on stops the check. No bridge: every event `UNVERIFIED` (shown, never a
refusal), exit 1.

## CONFIDENCE - `scripts/sofa/run_confidence.py`, `src/bet/sofa/confidence.py`

```
--date D  [--runs-dir runs/sofa]  [--calibration PATH]
```

Offline; football and tennis only. Reads the sheet, offer, fixtures, samples,
`fixture_status.json`, `vetoes.json`, `reads.json`, the curves and the line
evidence; writes `08_confidence.json` / `.md`. No `--floor`: the floor is
`COUPON_PROFILE`'s 0.70. `--calibration` writes the same artifact names - pair
it with a scratch `--runs-dir` or it overwrites the day's real 08.
`LINE_EVIDENCE_NOT_FITTED` on stderr = no evidence file.

- a moved price re-prices the leg at the fresh odds;
- reads and the automatic football `MODEL_ABOVE_OWN_SAMPLE` apply at the END
  of the chain: a leg that passed every gate goes to `removed_by_reads`
  (`refusal`, `reason` = authors or `auto`);
- singles sort by `confidence.coupon_sort_key`; builders as in `arithmetic.md`;
- annotations: `price_gap`, `peer`, stakes, `context_flags`, `sample_hit_rate`.

Refusals (the `refused` counter): `NO_PRICE`, `ODDS_TOO_LOW` (< 1.0867),
`NO_FIXTURE`, `VETOED`, `FIXTURE_NOT_AS_SCHEDULED`, `KICKED_OFF`,
`NO_FETCHED_AT`, `STALE_PRICE`, `NOT_IN_CALIBRATION_FIT`,
`CROSS_LEAGUE_UNLINKED`, `FRIENDLY_FIXTURE`, `NOT_SETTLEABLE`,
`NO_LINE_EVIDENCE`, `NOT_CALIBRATED`, `NO_CLASS_CURVE`, `CATCH_ALL_BUCKET`,
`BELOW_CONFIDENCE_FLOOR`, `NEGATIVE_LEG_EV` (x < 0.90), `LINE_BEYOND_SAMPLE`,
`MODE_LOSES`, `THIN_SAMPLE_FOR_BUILDER`, `SAMPLE_CROSSES_SEASON` (oldest > 180
days, national teams by count), `STALE_SAMPLE` (newest > 60 days),
`BUILDER_LEGS_INCOHERENT`, `READ_NO_BET`, `WATCHED`, `MODEL_ABOVE_OWN_SAMPLE`;
`CURVE_FAILED_CALIBRATION` is wired but off. A single prints only on a ladder
with margin <= 15% (`single_is_fairly_priced`). A football player row on
`confidence.PLAYER_SHAPE_GATE_MARKETS` needs only `PLAYER_MIN_SAMPLE` (5)
starts; a leg a shape gate would have refused carries `player_sample_rule`
and never joins a builder. Rebuilds of days before 2026-10-07 10:55Z also
show the retired by-name refusals (`PRICE_MOVED_SINCE_SHEET`,
`UNREACHABLE_BAR`, `DISAGREES_WITH_PRICE`, `DERIVED_NOT_CALIBRATABLE`,
`OPERATOR_REFUSED`, `PLAYER_PROP_NOT_ADMITTED`,
`TENNIS_SET_MARKET_NOT_ADMITTED`) - a printed leg of a once-refused market
today is not a defect.

A measured-sport read matches no sheet row: CONFIDENCE counts it as
`reads_sport` (`run_confidence.py`), never `UNMATCHED_READ`, and COUPON_ASSEMBLY
applies it. An `UNMATCHED_READ` is always a read that covers nothing.

Locked legs come from the previous artifact and the print history
(`bet.sofa.locked_print`): every printed single and stakeable builder whose
match has started or is inside the kickoff margin, unchanged.

## SHADOW / CS2 - `scripts/sofa/run_shadow.py`, `scripts/sofa/run_cs2.py`

Superbet snapshots of hockey (3), basketball (4), volleyball (1) and CS2 (55)
into `runs/sofa/shadow/<sport>/<d>/snapshots.jsonl` /
`runs/sofa/cs2/<d>/snapshots.jsonl`, several times a day by the daily loops
(`shadow_daily.py`, `cs2_daily.py`). Only complete outcome groups, each
devigged over its group. SHADOW also writes `player_model.jsonl` (pre-game p of
hockey / basketball player lines) and records D+1's games inside its horizon.
They are a measurement of the price and feed SPORT_IDENTITY /
SPORT_CONFIDENCE only.

## SPORT_IDENTITY - `scripts/sofa/run_sport_identity.py`, `src/bet/sofa/sport_identity.py`

```
--date D [--sport hockey --sport cs2] [--if-snapshot]
```

Bridge, after fresh snapshots (reads D's and D+1's). Pins the Sofascore event
of every hockey / basketball / volleyball / CS2 Superbet event before it
starts into `sport_fixtures.json` (`status` `IDENTIFIED` / `NOT_IDENTIFIED` /
`DUPLICATE_*`, `match_method`, `name_scores`, ...). An `IDENTIFIED` record is
never re-asked; an event not identified by its start keeps its last pre-start
record (`frozen_at_start`). SETTLE grades a sport leg by the pinned id. Also
teaches the entity map. A refusal stops the run. Exit 0; 1 an event not
identified or the bridge refused; 2 no snapshot (with `--if-snapshot`:
`NOTHING_TO_DO`, exit 0).

## SPORT_CONFIDENCE - `scripts/sofa/run_sport_confidence.py`, `src/bet/sofa/sport_confidence.py`

No bridge. Reads `sport_fixtures.json`, the snapshots, the day's sport
calibration (`sport_confidence.calibration_path_for`), the line evidence and
the DB read-only; writes `08_confidence_sports.json` only. Per side of an
event starting in [D 00:00Z, D+1 00:00Z): identified, not started, newest
pre-start snapshot <= 3 h old, an allowed market, a whole outcome group.
Refusals (`sports.<s>.refused`): `NOT_IDENTIFIED`, `DUPLICATE_*`,
`FIXTURE_NOT_AS_SCHEDULED`, `KICKED_OFF`, `STALE_PRICE`, `MARKET_NOT_ALLOWED`,
`TOURNAMENT_NEVER_SETTLED` (volleyball: no settled event in 14 days),
`INCOMPLETE_GROUP`, `NO_MODEL_P`, `FRIENDLY_FIXTURE`, `NO_LEAGUE_RATE`,
`LINE_OUTSIDE_FIT`, `NOT_CALIBRATED`, `NO_LINE_EVIDENCE`,
`CURVE_FAILED_CALIBRATION` (off), `BELOW_FLOOR`, `ODDS_TOO_LOW`,
`MARGIN_TOO_HIGH`, `NEGATIVE_MARGIN`, `BELOW_MIN_X`. Exit 0; 1 a sport
`NOT_CALIBRATED` or `sport_fixtures.json` missing (artifact still written,
football / tennis still built); 2 a crash.

## COUPON_ASSEMBLY - `scripts/sofa/build_coupon.py`

Offline, after CONFIDENCE and SPORT_CONFIDENCE. Refuses (exit 2) a missing,
non-standard-profile, non-stats-only or stale `08_confidence.json` (older than
the sheet, vetoes, reads or the curves). Writes `11_coupon.json` / `.md`:
locked legs first (unnumbered), fresh singles inside the day's UTC window in
`coupon_order` as one block per match (`group_key` `sofa:<id>`), positions
1..N; printed builders `B1..`; vetoes and reads applied to sport legs here
(`coupon_sports.apply_reads`); `removed_by_reads` from both sources;
`read_requests` with the positions each `covers` (`UNMATCHED_READ_REQUEST` on
stderr; an entry without `requested_by` / `at_utc` = exit 2); structure
annotations (`coupon_structure`); Superbet's names on every leg. Exit 1 when
`08_confidence_sports.json` is missing.

## PDF - `scripts/sofa/build_coupon_pdf.py`

```
--date D  [--runs-dir runs/sofa]  [--out PATH]  [--with-results]
```

Renders `11_coupon.json`. Guards (exit 2): `STALE_CONFIDENCE` (08 older than
the sheet, vetoes, reads or the football / tennis calibration file),
`STALE_COUPON` (11 older than 08, 08_sports, `read_requests.json`,
`09_screen_prices.json` or `config/sofa_coupon_form.json`). Writes
`12_printed.json` and `printed/<ts>.json` (only the day's own render, never
`--out`), then `KUPON_<d>.html` (an HTML failure keeps the PDF, exit 1).
Columns "pewność" and "model" (`forecast_p`); "rynek" in Superbet's words;
marks shown, never enforced (`ta sama drabina: N`, `start przed renderem PDF`,
`price_gap` sentence, ★ peer). A builder page: legs at Superbet's single
prices, the combined p, "kurs buildera: sprawdź na ekranie Superbetu" - never
our price. `--with-results` renders a finished day coloured from
`13_results.json` (a view, not a print: no print record, mtime kept).

## SETTLE - `scripts/sofa/run_settle.py`, `src/bet/sofa/settle.py`

D-1 only (today finds every fixture unfinished). `--only SETTLE` through
`run_pipeline.py`; `run_settle.py --include-unpriced` also grades rows
Superbet never quoted, `--refetch-stat-gaps` re-asks missing statistics.
`PARTIAL` is normal.

- **Refunds** (0 u., never a loss, never a `sofa_settled_row`;
  `settle.REFUND_REASONS`): `MOVED_BEYOND_VOID` (put back past
  `settle.void_deadline` - 23:59 of the day after the offered start, local
  time at the venue - or brought forward > `VOID_AFTER` 48 h), `AWARDED`,
  `RETIRED` (Sofascore code 92), `WALKOVER`, `CANCELED`,
  `POSTPONED_BEYOND_VOID` (before the deadline: `POSTPONED`, pending).
- A player who did not play / start / make the squad (`PLAYER_DID_NOT_PLAY`,
  `PLAYER_NOT_STARTED`, `PLAYER_NOT_IN_SQUAD`) is a refunded leg
  (`07_settle_skips.json` `void_legs`). A prop grades only from the player's
  own squad (`PLAYER_AMBIGUOUS` otherwise).
- Cards of a player on the bench do not count; football goals are always the
  90 minutes; after extra time non-goal counts stay `EVENT_NOT_FINISHED`.
- A printed leg the final sheet has no row for goes to
  `07_settled_printed.json`, never the DB table.
- Measured-sport legs are graded from SHADOW_SETTLE / CS2_SETTLE's
  `settled.json` at the printed price against the pinned id
  (`NOT_GRADED:ID_CHANGED` otherwise; a set / map never played is VOID),
  never in `sofa_settled_row` or `fit_confidence`. `audit_settle_identity.py`
  checks the pins. SHADOW_SETTLE reads an awarded / walkover / retired /
  forfeit game as `AWARDED` (`shadow.is_no_result`): never graded, never
  retried.
- Statistic gaps close days later: `resettle_sweep.py` every morning.
  `record_results.py` then writes the ledger and marks the day's KUPON with
  its results (`mark_coupon_results.py`).

## FIT - outside any day's run

`fit_constants.py` (`--db-path`, `--config-dir`), `fit_confidence.py`,
`fit_sport_confidence.py`, orchestrated by `prepare_refit.py` on a
`VACUUM INTO` copy of the DB; `install` runs `tests/sofa` and restores on
failure, and only on the operator's go. Curves are fitted on the history
replayed with SHEET's own estimator (`calibrate_from_cache.py`). A constant
with no data is written `null` / `NOT_FITTED`. Check `fitted_from` and
`half_match_coherence` before trusting a sheet. The line evidence has its own
morning refit (`refresh_line_evidence.py` -> `fit_line_evidence.py`) and never
touches a curve. Commands: `references/commands.md`.

## Audits

| script | question |
|---|---|
| `audit_coupon.py --date D` | Chain 1 arithmetic from each row's own fields, structure, anti-selection distributions. Exit 1 = findings |
| `audit_variants.py --date D` | C1 freshness, C2 every printed single obeys its dials (and printed-started legs are locked), C3 every leg of `legs_requiring_read` has an analyst read and no printed leg is WATCH / NO_BET, U1 order = `coupon_order`, U2 fresh football / tennis singles stats_only, U3 sport legs re-derived from the raw snapshot. 0 / 1 findings / 2 bad file |
| `audit_settlement.py --date D` | what came in and why not. **7c = the coupon's real result** per sport x epoch (refunds apart); 7i = `removed_by_reads`; 7e vetoes; 7 / 7b are input material, not bets |
| `audit_day_deep.py --date D` | per market: systematic miss or dispersion; would today's gates have made yesterday's bet |
| `audit_sample_bias.py --date D` | does the sample count what the book settles |
| `audit_vetoes.py --from D --to D` | what the vetoes removed, against the board at the same price bands |
| `audit_settle_identity.py --from D --to D` | the sports' pinned ids (`ID_USED_TWICE`, `MOVED_GRADED`, `NAME_BELOW`, `ORIENTATION_IDS`, `ID_CHANGED`, `IDENTITY_STATE`, `IDENTITY_PENDING`). 0 / 1 / 2 |
| `audit_ledger.py --from D --to D` | the ledger per variant and epoch group, never pooled |
| `day_status.py --date D` | one status: snapshot ages, loops alive, ledger MISMATCH, CLV coverage, UNVERIFIED, sport history, identity. 0 / 1 WARN / 2 broken |
