# The artifacts - every file, every field

Read this when you read or check a field. All under `runs/sofa/<date>/`
unless named otherwise. Types come from `src/bet/sofa/contracts.py`
(`strict=True, extra="forbid"`: a field not listed there does not exist, a
typo is a validation error). The day is **UTC**; datetimes are UTC ISO with
`Z`. Read big files with a filter (`jq`, a Python one-liner) - never `cat`.

**Artifact shapes** (checked on runs/sofa/2026-10-19):
- JSON lists, one entry per fixture: `02_fixtures.json`, `03_samples.json`, `04_offer.json`
  (`jq '.[]|select(.sofascore_event_id==<id>)'`); `05_sheet.json` is a list of sheet rows.
- Objects: `08_confidence.json`, `11_coupon.json` (legs in `singles`, `builders`,
  `removed_by_reads`), `fixture_status.json` (`events` keyed by event id),
  `sport_fixtures.json` (`fixtures`, a list).

| file | written by | what |
|---|---|---|
| `01_board.json` | BOARD | `BoardFixture[]` |
| `02_fixtures.json` | RESOLVE | `Fixture[]` |
| `03_samples.json` | SAMPLES | `FixtureSamples[]` |
| `04_offer.json` | OFFER | `FixtureOffer[]` |
| `05_sheet.json` | SHEET | `SheetRow[]` |
| `06_coupon.json` / `.md`, `06_dropped.json` | COUPON | the old VALUE selector and its exclusions - **not the coupon** |
| `fixture_status.json` | FIXTURE_CHECK | fresh status / start per event |
| `08_confidence.json` / `.md` | CONFIDENCE | football / tennis legs + builders - input of 11 |
| `sport_fixtures.json` | SPORT_IDENTITY | pinned Sofascore ids of the sports' events |
| `08_confidence_sports.json` | SPORT_CONFIDENCE | hockey / basketball / volleyball / CS2 legs |
| `11_coupon.json` / `.md` | COUPON_ASSEMBLY | **the coupon** |
| `KUPON_<d>.pdf`, `KUPON_<d>.html` | PDF | **the product**; the HTML is a filterable view of the same legs |
| `12_printed.json`, `printed/<ts>.json` | PDF | the print record |
| `vetoes.json`, `reads.json`, `read_requests.json` | analysts / verifier / operator | the channels (SKILL.md) |
| `analyses.json` | `merge_reads.py` (`bet.sofa.analyses`) | the analysts' and the verifier's match sections by match, newest first - display / `prior_analysis` |
| `dossier/<sport>_<event id>.json` | `read_set.py` / `build_slip.py` (`bet.sofa.dossier`) | the analysts' match fact sheet (form, rest, table, h2h, lineups, football `style` block with `style.matchup`, referee, line moves, web checklist); path on each leg's `dossier` - display only |
| `h2h.json` | `read_set.py` / `build_slip.py` (`bet.sofa.h2h`) | Sofascore head-to-head of every read match (`--no-h2h` skips); display only |
| `lineups_prematch.json` | `read_set.py` / `build_slip.py` (`bet.sofa.prematch_lineups`) | Sofascore pre-match lineup per read football / hockey / basketball match (OK / NOT_PUBLISHED / FAILED / NOT_ASKED); never cached; display only |
| `late_resolve.json` | LATE_RESOLVE in a live rebuild (`bet.sofa.late_resolve`) | board entries re-asked while open; only new fixtures added |
| `read_set/read_set_<sport>[_<i>].json` | `read_set.py` | the legs an analyst instance reads |
| `<d>_analiza_<sport>[_<part>][_r<n>].md`, `<d>_weryfikacja[_r<n>].md` | analysts / verifier | their reports, merged by `merge_reads.py` |
| `07_settled.json`, `07_settle_skips.json`, `07_settled_printed.json` | SETTLE (D-1) | grades, skips / refunds, printed legs without a sheet row |
| `13_results.json`, `13_results_rendered.json` | `mark_coupon_results.py` | result of every printed position; hashes of the last results render |
| `KUPON_<d>.przed_wynikami.pdf` / `.html` | `mark_coupon_results.py` | the files as printed, before the results render |
| `family_record.json` | `build_family_record.py` | 14-day record per (sport, market, direction) family - the HTML's selection aid, never a gate |
| `09_screen_prices.json` | operator | builder prices read off Superbet's screen - shown as his note, never a sofa price |
| `10_boosts.json` / `.md` | `run_boosts.py` | Superbet price boosts - not the coupon |
| `closing.jsonl` | `capture_closing.py` | closing price of every printed leg |
| `unmapped_prices/<ts>.jsonl.gz` | OFFER | prices of markets OFFER does not read - read by nothing |
| `entity_queue.md` | `report_entity_queue.py` | sport-identity alias queue for the operator |
| `reads_slip.json`, `vetoes_slip.json`, `slips/<HHMM>[_check].md`, `read_set_slip/read_set_slip_<sport>.json`, `<d>_analiza_<sport>_kupon_<hhmm>_<round>.md` | `merge_reads.py --slip` / `build_slip.py` / analysts | chat slip only (`/kupon`, `--check`); the coupon never reads them (`analyses.json` skips `_kupon_` reports) |

## `01_board.json` - `BoardFixture[]`

`superbet_event_id` (str; a Sofascore match may have several), `sport`
(`football | tennis`), `match_name`, `side_a`, `side_b`, `kickoff_utc`
(Superbet's clock), `tournament_id`, `category_id` (no competition name from
Superbet).

## `02_fixtures.json` - `Fixture[]`

| field | note |
|---|---|
| `sofascore_event_id` | the key everything downstream joins on |
| `superbet_event_ids` | plural: duplicate listings merged |
| `kickoff_utc` / `superbet_kickoff_utc` / `kickoff_disagreement_h` | Sofascore's / Superbet's clock and their gap (ITF up to 11 h; the earlier wins) |
| `home_name`, `away_name`, `home_entity_id`, `away_entity_id` | the side a `subject` must resolve to |
| `competition_name`, `competition_id`, `season_id`, `category_name` | the first place a competition is named |
| `identity` | `CONFIRMED \| FUZZY` |
| `round_number`, `round_name`, `cup_round_type`, `previous_leg_event_id` | cup context; a second leg shows here |
| `venue_name`, `referee` | `RefereeRecord` (`name`, `games`, `yellow_cards`, `red_cards`, `yellow_red_cards`), filled for ~9% |
| `ground_type`, `default_period_count` | tennis surface; tennis best-of (3 / 5), football halves |
| `sofascore_status` | Sofascore's `status.type` when RESOLVE read `/event/{id}` |
| `national_teams` | both sides national teams - sample judged by count, not age |

## `03_samples.json` - `FixtureSamples[]`

`sofascore_event_id`, `readiness` (`READY | PARTIAL | BLOCKED`), `metrics`
(`{metric: MetricSample}`: `side_a[]`, `side_b[]`, `h2h[]` of `Observation`),
`players` (`{"<metric>|<player as Superbet writes him>": PlayerSample}`,
`players.player_sample_key`), `gaps[]` (`GapEntry`: `reason`, `metric`,
`detail` - every gap is named; nothing disappears in silence), `schedule`
(make-up fixture, rest, congestion).

`Observation`: `sofascore_event_id` (the past match - a builder's empirical
joint intersects on it), `match_date_utc`, `opponent`, `opponent_id`,
`against`, `value`, `minutes` (player observations only), `competition_id`,
`season_id`, `venue` (`home | away | null`).

`PlayerSample`: `metric`, `player`, `matched_name`, `side`, `squad_matches`
(how many of the side's sampled matches had a squad list - the honest
denominator), `observations` (newest first), `match_rule` (`fuzzy | tokens |
surname | transliteration | inner_surname | slug`), `appearances` (`all | starts`; Superbet voids a footballer's market
unless he starts), `position`. A squad member who did not play is not an
observation.

## `04_offer.json` - `FixtureOffer[]`

`sofascore_event_id`, `status` (`PRICED | NO_PRICE | null`), `rungs[]`
(`PricedRung`: `market`, `subject`, `line`, `over_odds`, `under_odds`,
`fetched_at_utc` - per rung, what the 45-minute staleness gate reads; one side
`null` = one-sided, no devig), `unmapped_markets[]`, `price_collisions[]`,
`superbet_started_utc`, `superbet_kickoff_seen_utc` (start signals). Start clock = earliest of RESOLVE's clocks and Superbet's
(`superbet_kickoff_seen_utc`), or - once FIXTURE_CHECK read a fresh `/event`
start - of that start and Superbet's newest clock (it replaces RESOLVE's
frozen ones, `locked_print.kickoff_clocks`: a match moved later is not gated
on its dawn start); Superbet's start signal (`superbet_started_utc`) counts
as started.

## `05_sheet.json` - `SheetRow[]`

| field | note |
|---|---|
| `sofascore_event_id`, `sport`, `market`, `subject`, `line`, `direction` | identity; `subject` `""` for a match-level market |
| `sample_size`, `sample_mean`, `sample_sd`, `sample_newest_days` | the sample before shrinkage; newest observation age (`null` = unknown, not stale) |
| `centre` | mean after shrinkage (and the centre switches) |
| `p_central` | the model's probability, no price in it |
| `forecast_p`, `forecast_source` | the rating's own number ("model"; `football_rating` / `tennis_rating` / null) - never a gate |
| `epoch` | `stats_only`; CONFIDENCE refuses a sheet without it on a stats-only day |
| rule markers | `link_rule`, `dispersion_rule`, `k_rule`, `tennis_table_rule`, `game_state_rule`, ... one per switch the row was priced under (`references/model-state.md`); a rebuild re-runs SHEET when one due for the day is missing |
| `config_sha` | fingerprint of the fitted files SHEET read (`bet.sofa.sheet_config`) |
| `sample_frequency`, `calibration_correction`, `market_p`, `ladder_centre`, `ladder_sigma`, `p_bar`, `bar_reason`, `required_odds`, `offered_odds`, `edge`, `surplus`, `verdict` | Chain 1 (the old selector, `arithmetic.md`) |
| `notes[]` | `stages.md` - SHEET |

## `06_coupon.json` / `06_dropped.json` - not the coupon

`Coupon`: `created_at_utc`, `singles: CouponRow[]` (the row's own Chain 1
arithmetic plus `match_name`, `kickoff_utc`). `06_dropped.json`: one entry per
VALUE row that did not make it - identity, `surplus`, `reason`, `detail`
(reasons in `stages.md` - COUPON). Read it before concluding a row was never
generated.

## `07_settled.json`, `07_settle_skips.json`, `07_settled_printed.json`

Graded rows, also in `data/sofa.db` (`sofa_settled_row`). The skips file says
why a row was not graded; refunds (`settle.REFUND_REASONS`, `stages.md` -
SETTLE) are 0 u., never a loss; `void_legs` lists player legs voided for a
non-starter. `07_settled_printed.json` (`settle.PRINTED_SETTLED_FILE`):
printed legs the final sheet had no row for. Sport legs are graded from their
sport's `settled.json`, never into the DB table.

## `08_confidence.json`

Top level: `created_at_utc`, `profile`, `epoch`, `confidence_floor`,
`min_ev`, `max_overround`, `pdf_max_singles`, `prints_builders`,
`stakeable_rule`, `vetoes_applied` / `_unmatched`, `reads_applied` /
`_unmatched`, `fixture_status_checked` / `_unverified` /
`_unverified_reasons` / `_not_asked`, `fixtures_not_as_scheduled`,
`pool_neighbour_cap`, `removed_by_reads`, `legs`, `singles`, `builders`, and
the lock keys below.

A **leg**: identity + `sport`, `match`, `competition`, `kickoff_utc` (the
start clock, `04_offer.json` above), `model_p` (= `p_central`), **`confidence`** (the number),
`calibrated_on` (`market:<m>`, `line:<m>|<DIR>@<line>`,
`market_thin:<m>|<DIR>`, `pooled:<sport>`, `<class>:...`, `...<offset>sb`,
`...|cap:<cell>`, `sb:<sport>:<key>`), `calibration_n`, `sample_size`,
`sample_observations`, `sample_hit_rate`, `sample_oldest_days`,
`sample_newest_days`, `sample_min` / `sample_max`, `offered_odds`, `sheet_odds`
(the sheet's price when it moved), `implied_p`, `shading` (confidence -
1/odds), `leg_ev` (confidence x odds - 1), `market_p`, `overround`,
`unfitted_constants`, `context_flags`, `reads`, `epoch`, `forecast_p`,
`forecast_source`; when present: `line_offset`, `price_band_cap`,
`one_sided_market`, `player_sample_rule`, `price_gap`, `peer`, stakes flags.

A **builder**: `legs[]`, `n_legs`, `combined_probability` (the lower of the
product and the empirical joint), `product_probability`,
`empirical_joint_hits` / `_n` (often 0), `best_for_fixture`, `stakeable_rule`,
and the internal, never-printed `fair_odds`, `odds_if_product`,
`ev_if_product_priced`, `haircut`, `odds_after_haircut`, `ev_after_haircut`.
The 2-, 3- and 4-leg builders of a fixture are subsets of each other.

`removed_by_reads`: legs that passed every gate and a WATCH / NO_BET read or
the automatic `MODEL_ABOVE_OWN_SAMPLE` removed - the full leg plus `refusal`
(`WATCHED` / `READ_NO_BET` / `MODEL_ABOVE_OWN_SAMPLE`) and `reason` (`analyst`
/ `verifier` / `auto`). Graded apart (`audit_settlement` 7i, ledger
`removed:reads`).

**Locks**: a locked leg carries `locked: true`, `printed_at_utc`,
`printed_in` (its render file) and `printed_under` (that build's floor /
min_ev / max_overround / epoch) and comes first. The artifact carries
`locked_from_utc`, `locked_singles`, `locked_builders`, `locked_late_refusals`
(a veto or read now covering a locked leg - shown, never acted on).

## `fixture_status.json` (FIXTURE_CHECK)

`checked_at_utc`, `events: {"<id>": {status, status_code,
status_description, start_utc, [real_start_utc, real_start_basis], why,
checked_at_utc, [reason]}}`. `status` = Sofascore's `status.type` or
`UNVERIFIED` with `reason` (`NOT_FOUND`, `PROVIDER_REFUSED`,
`PROVIDER_ERROR`, `BAD_PAYLOAD`, `NO_BRIDGE`, `CIRCUIT_OPEN`, `NOT_ASKED`).
`why`: `printed`, `clock_gap` or `candidate`. Tennis `real_start_utc` (first
point; `first_set` exact, `derived` an upper bound) decides "printed before
its start" ahead of `start_utc`.

## `sport_fixtures.json` (SPORT_IDENTITY)

`created_at_utc`, `date`, `day_window_utc`, `sports` (per sport `events`,
`identified`, `refused`), `sports_run`, `aborted`, `fixtures[]`:
`superbet_event_id`, `sport`, `sofascore_event_id`, `home_id`, `away_id`,
`home_is_team1`, `competition_id`, `match_method` (incl. `DAY_ANCHOR`; `QUERY_ANCHOR` volleyball from
2026-10-24),
`name_scores`, `start_gap_h`, `matched_at_utc`, `status` (`IDENTIFIED` /
`NOT_IDENTIFIED` / `DUPLICATE_*`), `reason` (e.g. `NOT_ON_SOFASCORE`,
`NO_GAME_WITHIN_1H` with `nearest_game_h`), `frozen_at_start`, `match_name`,
`team1`, `team2`, `team1_id`, `team2_id`, `tournament`, `kickoff_utc`,
`source_date`, `queried_team_id`, `listing_from_cache`; CS2 rows also
`sofascore_match`, `sofascore_tournament`, `best_of`. `kickoff_utc` is the
start at pinning (frozen); the fresh start is `fixture_status.json`. `IDENTIFIED` is pinned
and is the id SETTLE grades by.

## `08_confidence_sports.json` (SPORT_CONFIDENCE)

`created_at_utc`, `date`, `rule` (`floor` 0.7, `min_x` 0.9, `max_overround`
0.15, `min_odds` 1.0867, `kickoff_margin_min` 15, `max_price_age_min` 180,
`day_window_utc`), `calibration_file`, `calibration_fitted_from`,
`line_evidence_fitted_from`, `sports` (per sport `status` `OK` /
`NOT_CALIBRATED`, `refused`, `legs`, `fixtures_not_as_scheduled`), `legs[]`:
`sport`, `group_key`, `sofascore_event_id`, `superbet_event_id`, `market_id`,
`family`, `period`, `subject`, `line`, `side`, `confidence`, `calibrated_on`,
`calibration_n`, `sample_hit_rate`, `sample_k`, `sample_n`, `forecast_p`,
`forecast_source`, `odds`, `x`, `overround`, `kickoff_utc`, `source_date`,
`price_fetched_at_utc`, `match`, `competition`, `unfitted_constants`;
`line_offset` / `price_band_cap` when lowered; CS2 map legs `team1`, `team2`,
`map_nr`; `dc_pair_rule` on a basketball double-chance pair;
`derived_rule` (`sport_derived_v1`) on a score-model derived market (hockey /
basketball double chance, volleyball team sets / sets count);
`lineup_unrated_rule` (`cs2_lineup_unrated_1023`, from 2026-10-24) on a CS2
leg priced through the unrated pairs' lineup calibration (P7: without it the
side has no number, or another one).

## `11_coupon.json` / `.md` (COUPON_ASSEMBLY) - the coupon

A superset of the 08 format, so `confidence.printed_singles` /
`printed_builders`, the lock, SETTLE and the ledger read it as they read 08.
Added or rebuilt:

- `coupon` (`"11_coupon.json"`), `epoch`, `built_from` (the 08 files'
  `created_at_utc`), `pdf_max_singles: null`, `prints_builders: true`;
- `singles[]`: locked legs first (no `position`), then fresh legs in
  `coupon_order` with `position` (1..N), `block`, `group_key`, optional
  `makeup_of`, and on every leg `superbet_market` / `superbet_selection` (the
  screen's words) and `display_market`; a sport leg keeps its 08_sports fields;
- `positions`, `locked_singles`, `blocks[]` (`block`, `group_key`, `match`,
  `sport`, `kickoff_utc`, `positions`, `builders`);
- `builders[]` (printed ones numbered `builder_no` `B1..`), `builders_refused`,
  `builder_screen_prices`;
- annotations: `ladders[]` (`ladder_no`), `relations[]`, `exposure`,
  `coupon_form` / `removed_by_coupon_form` (OFF unless
  `config/sofa_coupon_form.json` sets it), `peer_choice`, `price_gap`;
- `legs[]` (all candidates), `removed_by_reads`, `reads_sport`,
  `read_requests` (each with the positions it `covers`), `read_unit`
  (`event`) and `read_order` (`value`) - the read-set rule,
  `outside_day_window`, `sports`.

Positions shift after a rebuild: refer to a leg by `group_key` + rung.

## `12_printed.json` and `printed/`

`12_printed.json` (`locked_print.PRINTED_MANIFEST`) = the 11 document the last
render printed + `pdf`, `pdf_rendered_at_utc`. Every render also writes
`printed/<YYYYMMDDTHHMMSS.ffffffZ>.json`, never overwritten. CONFIDENCE /
COUPON_ASSEMBLY / FIXTURE_CHECK read the whole history (`print_history`,
`first_prints`): a printed leg whose match has started is locked as FIRST
printed, decided by the last render before its real start; a later render that
left it out does not remove it. Written only by the day's own render, never
`--out` or `--with-results`.

## `13_results.json`

`schema`, `date`, `computed_at_utc`, `graded_by`, `legs` (key = JSON of
`[sofascore_event_id, market, subject, line, direction]`; a sport leg's key
adds the market id and CS2 map) -> `{outcome, status (won / lost / refund /
unknown), actual, score, sport, confidence, odds}`, `builders`. The ledger's
own grades, never a second grader; days from 2026-10-13 that are over.

## `read_requests.json`

A JSON list; each entry has `requested_by`, `at_utc` and either
`{"position": n}` or `{"group_key": "sofa:<id>", "market"?, "line"?,
"direction"?}` (an omitted field covers every value). An entry missing
`requested_by` / `at_utc` fails COUPON_ASSEMBLY; a request covering nothing is
`UNMATCHED_READ_REQUEST`; 11 older than it is `STALE_COUPON`.

## `vetoes.json` - `Veto[]`

`sofascore_event_id` (int, required), `market`, `subject`, `line`,
`direction` (nullable; `null` = all), `reason_class` (`SAMPLE_UNINFORMATIVE |
CONTEXT | PRICE | OTHER`), `reason` (Polish, the operator reads it),
`context` (with `CONTEXT` only: `MOTIVATION | ROTATION | ABSENCES | DERBY |
SCHEDULE | CONDITIONS`). Read by COUPON, CONFIDENCE and COUPON_ASSEMBLY.
Every vetoed row is still settled and graded (`audit_settlement` 7e,
`audit_vetoes.py`).

## `reads.json` - `LegRead[]`

`sofascore_event_id`, `market`, `subject`, `line`, `direction`, `period`
(nullable, matched like a veto), `verdict` (`KEEP | WATCH | NO_BET`),
`author` (`analyst | verifier`), `reason` (non-empty, Polish), `context`
(optional, the veto tags). Sport leg: `market` = family, `direction` = side
(`contracts.READ_SIDES`: OVER, UNDER, T1, T2, DRAW, ODD, EVEN, YES, NO, 1X,
X2, 12, or an exact score "3:1"), `period` = period / quarter / set / CS2 map.
One bad entry fails the file and every stage reading it - merge only through
`merge_reads.py`. Append-only; WATCH / NO_BET win over KEEP whoever wrote
them. The covering reads are written on the leg as `reads: [{verdict, author,
reason}]` plus `read_at_utc` / `context` when set; `merge_reads.py` stamps
`read_at_utc` on every read it merges (a re-merge keeps the first stamp).

## `analyses.json` - the analysts' match sections

`{"version": 1, "events": {"<sofascore_event_id>": [entry, ...]}}`, newest
first; entry: `author` (analyst / verifier), `report` (file name),
`recorded_at_utc`, `heading`, `markdown` (the whole section), `web_tags`
(`[WEB:` count), `context_pass` (a "Kontekst (web)" block), `verdict_line`.
Written by every coupon `merge_reads.py` (`bet.sofa.analyses`: a section is
a `##`-`####` heading carrying `sofa:<id>`, else naming both teams of a
coupon match); `build_analyses.py --date <d>` rebuilds it from the day's
reports. Read by the HTML view (folded under each leg), the PDF appendix and
`read_set.py` (`prior_analysis` on a leg of a match analysed earlier today).
Display / process only.

## `runs/sofa/shadow/<sport>/<d>/` and `runs/sofa/cs2/<d>/` - the measured sports

- `snapshots.jsonl` (SHADOW / CS2): per not-yet-started event every complete
  outcome group, devigged over the group (`cs2.group_fair`): `market_id`,
  `family`, `period` (0 = none; CS2 `map_nr`, 0 = series), `subject` (`T1` /
  `T2` for a team total, a player name), `line` (a total, or **team1's**
  handicap), `side` (OVER / UNDER / T1 / T2 / DRAW / ODD / EVEN / YES / NO /
  "3:1" team1 first), `odds`.
- `player_model.jsonl` (SHADOW): pre-game p of hockey / basketball player lines.
- `settled.json` (SHADOW_SETTLE / CS2_SETTLE): per game / series a `state` -
  `SETTLED` (periods or maps, `graded[]` with `actual`, `outcome`, `fair_p`),
  `PENDING`, `NOT_ON_SOFASCORE` (with `miss` per side), `AMBIGUOUS`,
  `DATA_MISMATCH` (periods / maps do not add up - nothing graded), `UNUSUAL`,
  `VOID`, `GAVE_UP` (after 7 days), `NO_PRE_START_PRICE`. A period-less
  basketball / hockey game is graded from its final score
  (`score_source: "final_only"`, full-game markets only).
  `orientation_unclear: true` grades totals only. A CS2 series waiting for
  player stats carries `pending_sides`. Locked read-modify-write.
- Grading scope: a market without "(z dogrywką)" counts regulation time.
  **Basketball second half and Q4 grade on the regulation periods - overtime
  does not count**; full-game basketball markets include it. Hockey's
  overtime-inclusive families (613 / 617 / 621 / 653) are not mapped, and the
  NHL is posted only with them.
- `audit_shadow.py` / `audit_cs2.py` keep one side per line
  (`cs2.one_side_per_line`) and print `read`: `too few` (< 30 games),
  `noise`, `lead only`, `signal` - quote `read`, never a bare gap.

## `runs/sofa/ledger/results.jsonl` - the ledger

One row per (`date`, `variant`), written by `record_results.py` (a re-run
replaces the date's rows), read by `audit_ledger.py` per variant and epoch
group (`audit_ledger.EPOCH_GROUPS`), never pooled. Variants: `official` (7c),
`official:pre_stats_only`, `removed:reads` (7i), `measure:<sport>`. Rows
named `wariant` / `multi` / `sport:<sport>` / `rule:<sport>` are retired
variants of days up to 2026-10-05: read, never pooled. `by_match` (`{match:
[units, settled]}`) is the cluster the match bootstrap resamples (no interval
under 20 matches, `clv.MIN_CLUSTERS`). Exit of `record_results.py`: 0
recorded (pending shown), 1 a `MISMATCH` (two graders disagree - a defect) or
an unreadable file, 2 a crash.

## The log

`runs/sofa/run.log.jsonl`: one JSON row per request with `run_id` and the
stage (`src/bet/sofa/stage.py`; a request with no declared stage logs as
`CLIENT`). Pipeline log timestamps in `runs/sofa/<d>/*.log` are local time.
