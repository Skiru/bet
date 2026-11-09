# Working agreement - `bet`

The main session's working agreement (operator + developer). It describes the
system **as it is now**: one pipeline, `sofa`, and one coupon a day. It is not
a changelog: a rule change edits its section; the story lives in
`docs/sofa/history/` and git. The sofa agents do **not** load this file
(`omitClaudeMd: true`); their contract is the `sofa-pipeline` skill.

**Before proposing or changing a model, curve, switch or refit, read
`.claude/skills/sofa-pipeline/references/model-state.md`** (every switch with
its date, measurement and evidence; installed fits; measured and declined;
open questions; ledger epoch groups). Full command catalogue:
`.claude/skills/sofa-pipeline/references/commands.md`.

## The pipeline: `sofa`

Sofascore statistics, Superbet prices, one coupon a day for every sport -
football, tennis, hockey, basketball, volleyball, CS2. The product of a day is
**`runs/sofa/<date>/KUPON_<date>.pdf`**, rendered from **`11_coupon.json`**.

```
BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON
                                          ↘ CONFIDENCE ─────────────┐
   SHADOW / CS2 → SPORT_IDENTITY → SPORT_CONFIDENCE ────────────────┤
                                   COUPON_ASSEMBLY (11_coupon.json) → PDF   ★ the product
   in a rebuild, before CONFIDENCE: FIXTURE_CHECK
   in a live rebuild, first:        LATE_RESOLVE (new fixtures only → OFFER/SAMPLES/SHEET --event-ids)
   in a rebuild, on a sample switch: SAMPLES/SHEET --event-ids for open fixtures (rebuild_plan 1c)
   deliberately separate:           SETTLE → FIT
```

Order: `DEFAULT_SEQUENCE` in `scripts/sofa/run_pipeline.py`. There is no other
pipeline and no other coupon. `DISCOVER`, `ENRICH`, `ANALYZE`,
`MARKET_CONTEXT`, `TIPSTERS` do not exist here; discovery is BOARD, and it asks
the bookmaker.

Reference (Polish): `docs/sofa/PIPELINE.md` every stage, field and gate;
`docs/sofa/RUNBOOK.md` the day's order and "what if"; `docs/sofa/AGENTIC_FLOW.md`
agents and hand-offs; `docs/sofa/CONFIG.md` config files and the refit loop.

### Artifacts of a day (`runs/sofa/<d>/`)

| file | what it is |
|---|---|
| `08_confidence.json` | football / tennis legs with confidence and gates; SETTLE's and the refit's input |
| `08_confidence_sports.json` | hockey / basketball / volleyball / CS2 legs (SPORT_CONFIDENCE) |
| `11_coupon.json` | **the coupon**; read it through `confidence.coupon_artifact()` |
| `KUPON_<d>.pdf`, `printed/<ts>.json`, `12_printed.json` | the product and its append-only print record (a rebuild locks from the first print) |
| `KUPON_<d>.html` | the same legs as a filterable page - a **view**, not a coupon (`bet.sofa.coupon_html`); every read leg carries its analysts' notes (verdict, author, merge time, context tag, reason) and, folded under it, the match's full analysis sections (`analyses.json`; the PDF: the whole reason at the leg, `read_label`, and an "A<n>" pointer to the appendix "Aneks: analizy meczów" with the newest analyst / verifier section of every printed read match), a match with no read leg is marked "nieczytany" - display only; dark, cards under 760 px for the operator's iPhone, a table on the Mac and on paper, a results render without the "nierozpoczęte" filter (never restored there), chips / sort list / filters kept per day in localStorage, 200 legs drawn at a time (filters and summaries count all); written by `build_coupon_pdf.py` after every PDF (HTML failure: PDF kept, exit 1); alone `build_coupon_html.py --date <d>` |
| iCloud `Kupony/<DD.MM.YYYY>/` | the operator's copy of KUPON pdf + html (`bet.sofa.icloud_sync`, operator 2026-10-25): every render of the day's own coupon (print, rebuild, `--with-results`; `build_coupon_html.py` too) replaces it atomically; a scratch runs dir never reaches it (`SOFA_ICLOUD_KUPONY_DIR` names a root, empty = off; tests set it empty); no iCloud Drive = SKIPPED; a failed copy = PDF stage PARTIAL (exit 1); `day_status.py` `icloud` WARNs when the copy differs from the local render. A copy, read by nothing |
| `13_results.json` | settled result of every printed position, the ledger's own grades (`bet.sofa.coupon_results`); written by `mark_coupon_results.py` (called by `record_results.py`) |
| `reads.json`, `vetoes.json`, `read_requests.json` | analysts' per-leg verdicts (each stamped `read_at_utc` by `merge_reads.py`), vetoes, the operator's extra positions |
| `analyses_slip.json` | the same for chat slips (`merge_reads.py --slip`): never the coupon's view; `build_slip.py` reads it beside `analyses.json` for `prior_analysis`, so a match read in an earlier /kupon of the day gets a delta pass |
| `analyses.json` | the analysts' and the verifier's match sections by Sofascore id, newest first (`bet.sofa.analyses`): cut from each report at its `sofa:<id>` heading (else both team names) by every coupon `merge_reads.py`; `build_analyses.py --date <d>` rebuilds it from the reports on disk. Read by the HTML / PDF and by `read_set.py` (a re-read leg's `prior_analysis` -> the analyst's delta pass) - display / process only, never a gate |
| `read_set/read_set_<sport>[_<i>].json` | C3's read set as compact legs (`read_set.py`) |
| `dossier/<sport>_<event id>.json` | the analysts' match fact sheet (`bet.sofa.dossier`, offline, written by `read_set.py` / `build_slip.py`, path on each leg's `dossier`): form with periods, rest, rebuilt table, h2h (cached meetings + `h2h.json`, each with the legs' metrics; `head_to_head_source` says what was asked and how far the cache reaches), Sofascore's pre-match lineup (`lineups`: predicted / confirmed, XI, missing / doubtful, each prop's player XI / bench / missing / not listed, each side's regulars not in the XI), venue city / local hour, referee / ranking / CS2 roster and map pool, Superbet line moves, the web checklist, football `style` (each side's last 10 competitive games with stats: corners / shots won and conceded, crosses attempted, box touches, blocked shots, xG, big chances, final-third entries, long balls, throw-ins, goal kicks, possession, corners by own possession - a bucket under 4 games marked a note; the league's rate of the legs' metrics, `style.league`; `matchup`: every count leg - side legs own k/n beside what the opponent conceded, totals both sides' games, league share - counted as SETTLE counts, `metrics.extract_metric`; a "każda z drużyn" joint (`both_over_*`, `joint: true`) as a total on min(own, rival), as SETTLE grades it; schema 3 rows carry the leg's key and `price_gap`; measured 10-29 as a suspicion, model-state.md (d), the basis of a `RYNEK:` WATCH from reports of 10-29; the same text is the KUPON html "zestawienie" tag on every printed football count leg, `dossier.matchups_for_legs`; `dossier.joint_history` is `build_slip.py --check`'s k/n of a builder's legs together; football matches from 2026-10-30 (`AWARDED_EXCLUDED`): a result awarded at the table stays in `last_games` marked `awarded`, out of the form summary, style, matchup, league rate, h2h metrics and joint k/n, its points kept in the rebuilt table) - **display only**, never a gate |
| `h2h.json` | every read match's head-to-head asked of Sofascore (`/event/{customId}/h2h/events`, `bet.sofa.h2h`) by `read_set.py` / `build_slip.py` before the dossiers (`--no-h2h` skips; operator 2026-10-21: always), the meetings' statistics into the cache; an OK answer is not re-asked that day; a failure leaves the dossier `NOT_ASKED` / `FAILED` and an h2h line on its web checklist - display only, SAMPLES never reads it |
| `lineups_prematch.json` | Sofascore's pre-match lineup (`/event/{id}/lineups`, `bet.sofa.prematch_lineups`) of every read football / hockey / basketball match not yet started, asked by `read_set.py` / `build_slip.py` before the dossiers (`--no-lineups` skips): `asked_at_utc`, status OK / NOT_PUBLISHED (404) / FAILED / NOT_ASKED (breaker), `confirmed`, formation, starters, substitutes, `missingPlayers` (missing / doubtful, reason copied); a confirmed answer is final, an unconfirmed one re-asked after 30 min, a failure keeps the earlier answer. **Never written to the cache** (`sofa_event_stats.lineups_json` is the post-match lineup player samples and SETTLE read); display only, SAMPLES / SHEET / CONFIDENCE never read it |
| `late_resolve.json` | the late RESOLVE passes (`epochs.LATE_RESOLVE_FROM_UTC`, `bet.sofa.late_resolve`): board entries the morning could not bridge re-asked while open; only new fixtures added, every old row kept |
| `fixture_status.json`, `sport_fixtures.json` | FIXTURE_CHECK's fresh starts / statuses; pinned Sofascore ids of sport games |
| `unmapped_prices/<ts>.jsonl.gz`, `unmapped_prices/<sport>_<ts>.jsonl.gz` | prices of markets OFFER does not read; from 2026-11-05 also SHADOW's (hockey / basketball / volleyball) and the CS2 snapshot's (`shadow.reads_market` / `cs2.reads_market`), one file per snapshot and sport under the event's day, from the payload already fetched, plus `sport` / `marketId`, `sofascore_event_id` null (join on `superbet_event_id`); `unmapped_prices.read(dir)` = OFFER's files only, `read(dir, sport)` a sport's - a record, read by nothing but `measure_*` (`test_unmapped_prices_sports.py`) |
| `06_coupon.json` | the priced VALUE selector - **not the coupon** |
| `runs/sofa/paper/bb_handicap/<d>.json`, `ledger.json` | a pre-registered PAPER test (operator 2026-10-31): basketball handicap where Superbet price x bet365 OPENING fair p > 1 (`bet.sofa.paper_bb_handicap`, `T-PAPER-BB-HANDICAP-B365-OPEN`); forward bet365 only from `prestart/<d>/<id>.json` captured before tip-off (`--capture --loop`, started by `shadow_daily.py`, `day_status` `loop:paper_capture`); forward from 11-01 apart from the backtest (post-match line, a look-ahead), judged once on the first 300 selections in kickoff order (later ones apart) - no stake, read by nothing the coupon reads, never a reason for a leg |

## How the coupon is built

**Confidence comes from the statistics; the price is only the condition for
the bet and may only lower a confidence.** Yardstick (operator): the statistics
must tell a good 1.20 from a bad 1.20, in every sport alike, and nothing that
could win is cut by name.

### Fixtures (RESOLVE)

A board entry becomes a fixture only when both sides agree with one Sofascore
game (name, opponent, start within the window, Superbet's side order F25,
gender, squad level - never reserves / youth for the first team). For a pair
nothing matched by name, football falls back, in order, to (all from 10-21,
each measured with 0 wrong picks against the real opponent; model-state.md
"RESOLVE ..." sections; fixture `identity: FUZZY` + `match_rule`, never cached
as a verified name): the **reserve / youth retry** with Superbet's own name
(`SQUAD_SEARCH_RETRY`, 09:20Z); the **searched anchor** - the searched side's
one game at Superbet's start, the opponent agreeing weakly, vetoed when its own
search names another team (`FOOTBALL_SEARCHED_ANCHOR`, 10:00Z); the
**squad-level alias** - U19 / U20, reserves / U19..U23, Sofascore's trailing
"2", each side on its own from 11:30Z (`FOOTBALL_SQUAD_LEVEL_ALIAS[_LOOSE]`,
10:30Z); the **short-name search** - both sides searched by their longest
words must land on the same game (`FOOTBALL_SHORT_NAME_SEARCH`, 11:00Z). An
entity miss blocks a name only on its own kickoff day
(`ENTITY_MISS_PER_DAY`, 09:20Z; the late pass re-asks a miss older than 30 min),
and a miss recorded before a rule's switch never blocks that rule.

### Confidence

- **Curves are fitted on the history** of events and statistics, replayed as of
  each match with the estimator SHEET prices with today. Our settled days are an
  audit of a curve, never its source. Curves: `config/sofa_confidence_calibration.json`
  (football / tennis) and `config/sofa_sport_confidence_calibration.json` (a
  staged `.next.json` is read from its `effective_from`, and a dated
  `.next.<YYYY-MM-DD>.json` from that day - a day reads the staged file with
  the latest `effective_from` <= it, `sport_confidence.calibration_path_for`;
  10-14..10-23 read `.next.json`, 10-24..10-27 `.next.2026-10-24.json`
  (hockey refit), from 2026-10-28 `.next.2026-10-28.json` (basketball / CS2
  curves made monotone, review 10-27), so an edit for a coming day goes into the latest staged
  file, never into the installed one or a file a built day reads). Football /
  tennis read a staged file from its `effective_from` (`confidence.calibration_path_for`:
  the undated `.next.json` or a dated `.next.<YYYY-MM-DD>.json`, the latest start the
  day and the build clock have reached, each file complete on its own): from 2026-11-06 17:30Z
  (moved by the operator from 11-07 00:00Z, "WŁĄCZ JAK NAJWIĘCEJ RZECZY OD DZISIAJ";
  11-06 mixed, ledger "11-06 mieszany") `config/sofa_confidence_calibration.next.json`, the 11-05 replay refit with the live
  rules (16 families / 25 keys + 13 score slices, every other key the
  installed file's byte for byte, `staged_change`; ledger groups "11-06 mieszany", "od 11-07";
  model-state.md). Never copy it over the installed file; a later staged day
  is a new dated file carrying 11-07's keys too. From 2026-11-07 00:00Z
  `.next.2026-11-07.json` (the season table's 4 refit curves; 11-06 after
  17:30Z still reads `.next.json`).
- **Football season table per family from 2026-11-07 00:00Z** (`FOOTBALL_FORM_TABLE`,
  coordinator 11-06, moved from 11-09 by the operator, never into 11-06; ledger "od 11-07"; report `refit_replay_2026-11-05.md` section 12): SHEET
  prices each football fixture on two rating books, without and with the goals
  form step + season table, and a row of `epochs.FOOTBALL_FORM_TABLE_FAMILIES`
  (35 `market|DIR`, selected on 10-18..10-26, confirmed on 10-27..11-04) takes
  the table run's row (`form_table_p` "table" / "no_table"); card counts,
  goals_for, goals_1h_for, most_* stay off (curve / p mismatch, a later
  refit) - `handicap_cards_points` OVER is one of the 35. A refit
  replays it with `--form-table-per-family`. The whole-sheet table and
  `result_1x2` were declined (table gate; 1X2 over-promises on printable legs
  under A -5.5 pp and on rules p -7.8 pp).
- SHEET keeps the price out of `p_central`; the rating is published beside it
  as `forecast_p` ("model", uncalibrated, never a gate). CONFIDENCE maps the
  statistics to a calibrated confidence through the curves.
- **Line evidence** (`bet.sofa.line_evidence`,
  `config/sofa_superbet_line_evidence.json`, refitted every morning by
  `refresh_line_evidence.py`, which never touches a curve; `day_status.py`
  `line_evidence` WARNs when it is fitted for an earlier day; once refitted
  mid-day - 11-06 17:34Z, for the 17:30Z switches, so 11-06's late legs read
  the new keys' own offsets): every key is also read through its own
  settled Superbet lines. From a fit for 2026-11-08 the tennis pool leaves
  out the point model's rows (they enter through its own evidence only). Confidence = the lowest of
  - the curve lowered by the key's **offset** (realised minus confidence on
    printable lines; needs `MIN_OFFSET_ROWS` 50 lines and `MIN_OFFSET_GAMES` 30
    games, else the sport's pooled offset with `MIN_SPORT_OFFSET_GAMES` 20;
    never above 0; the pooled offset excludes a key holding more than
    `CONCENTRATION_MAX` 50% of the lines - which can raise another CS2 key;
    football / tennis / hockey from 2026-10-30 08:45Z read the offset by the
    leg's d = curve - 1/odds bucket instead, `PRICE_GAP_OFFSET`: the key's
    printable lines in that bucket shrunk to the sport's, K 200, never above 0;
    printed calibration +1-2 pp out of sample, ROI unchanged - 10-30 mixed), and
  - the **price-band cap** (`PRICE_BANDS` 1.30 / 1.60 / 2.20, cell
    `MIN_CAP_CELL` 20): what the key's lines at this `p` realised in this band,
    applied only where below the confidence; a thin cell widens downward in
    its band, an empty band reads the key's lines over every band from its `p`
    down (to 0.70).

  A key without a curve reads the Wilson bound of its own lines divided by its
  p bucket's design effect (`deff`; lines of one game are not independent),
  needing `MIN_EVIDENCE_BUCKET` 50 lines and `MIN_EVIDENCE_GAMES` 15 games in
  the bucket, else `NO_LINE_EVIDENCE`. Legs carry `line_offset` /
  `price_band_cap` when lowered. A CS2 fixture with no `best_of` is not guessed
  as best-of-3.
- **Curves per line** (`bet.sofa.line_curves`): the 33 football keys of
  `config/sofa_line_curves.json` read the leg's own line bucket first (source
  `line:<market>|<DIR>@<line>`), a bucket under 400 rows the pooled curve; class
  legs (women, season_early) unchanged. A calibration fix, not an edge.
- **Wait for a measurement, not a name:** a market with no curve and no
  evidence is `NO_LINE_EVIDENCE`. Only rebuilds of days before
  `LINE_EVIDENCE_FROM_UTC` use the old by-name refusals (`refused_markets`,
  `admitted_player_markets`, `admitted_tennis_set_markets`,
  `DERIVED_NOT_CALIBRATABLE`, the sports' `admitted` keys).
- **No curve from our days alone** (`LIVE_ONLY_CURVE_REFUSED`, from 2026-10-24
  00:00Z): `fit_confidence` gives no curve to a key only live settled rows
  reached (`live_only_refused` in its output); the 50 installed tennis keys
  measured so (`config/sofa_live_only_curves.json`) read as markets without a
  curve, no pool standing in (`bet.sofa.live_only_curves`).
- **Football from 2026-10-21** (model-state.md, "Football statistics night"):
  cards / fouls centres carry the fixture **referee's** as-of shrunk rate
  (`bet.sofa.referees`; labels from `backfill_referees.py`, the fixture's
  referee from its cached `/event` - named ~48 h before kick-off, none = x1)
  and cards / shots totals a **closeness** term (`bet.sofa.closeness_stretch`);
  a footballer's shots / SOT / fouls centre is his shrunk **share** of his
  side's team centre (`bet.sofa.player_share`); SAMPLES widens thin player
  samples to the last 20 matches (`FOOTBALL_PLAYER_COVERAGE`); new markets:
  fouls drawn on a player, card points by half, side / half reds and
  penalties, both-over throw-ins / goal kicks / tackles, shots handicaps.
  Neither the referee nor the share is replayed by a refit yet.
- **Tennis rating from 2026-10-24** (`TENNIS_RATING_SCORE_WINNER`, audit P14):
  an Ended match with no `winnerCode` takes its winner from a complete set
  score (never retired / walkover); SHEET reads it by the day and the build
  clock; a match is a women's when either side says "F"; rows carry no marker;
  the installed tennis curves were fitted without it.
- **Tennis point model from 2026-11-06** (`TENNIS_POINT_MODEL_FROM_UTC`,
  operator 11-05; `bet.sofa.tennis_point_sheet`): the 20 keys of
  `epochs.TENNIS_POINT_MODEL_MARKETS` (`games_set1/2_total`; aces / double
  faults / serve points, match and set 1 / 2, `_for` / `_total`) take
  p_central / centre from the bottom-up point model (as of the start, 4,000
  seeded simulations; best of five / no ids = NOT_RATED, never the old
  estimator; row marker `tennis_point_model_rule`, rebuild_plan re-runs SHEET).
  CONFIDENCE reads those keys only from `config/sofa_tennis_point_curves.json`
  (`bet.sofa.tennis_point_curves`, fitted by `fit_tennis_point_curves.py` on
  the model's walk-forward over Sofascore history before 10-20; overlaid after
  the live-only strip, never pooled); line evidence refits these keys from the
  model's p (`data/line_evidence/tennis_point_model_p.json.gz` backfill), the
  sport pools unchanged. `games_total` / `games_won_for` keep today's
  estimator. Hold-out replay of the wired chain 10-20..11-04: see model-state.md.
- **Tennis per-set handicap from the point model, 2026-11-06 17:30Z**
  (`TENNIS_HANDICAP_POINT_MODEL_FROM_UTC`, by the build clock; moved by the
  operator from 11-07 00:00Z, 11-06 mixed; operator 11-06: "install what
  beats the current estimator"): `handicap_games_won_set1/2` join the point model's
  scope (`epochs.tennis_point_markets`; margin read by
  `bet.sofa.tennis_handicap_point`, OVER only; derived rows take p through
`run_sheet._point_model_rating_p`, none = NOT_RATED, never the joint), curves
  `config/sofa_tennis_handicap_point_curves.json` (overlaid only for a sheet
  whose tennis rows carry the marker, `tennis_point_curves.handicap_rows_marked`),
  line evidence from the backfill (11-06 rows: backfill only, from 11-07 the
  rows' own p; `data/line_evidence/tennis_handicap_point_model_p.json.gz`),
  row marker
  `tennis_handicap_point_model_rule`. Hold-out 10-20..11-05: Brier vs the
  neighbours -0.0114 [-0.0185, -0.0040], >= 0.70 after the curve -1.0 pp
  (neighbours -6.7); vs the price +0.0030 (reported). Full-match
  `handicap_games` stays on the rating (calibration -8.0 vs -6.8 pp failed the
  rule; `docs/sofa/evidence/tennis_handicap_point_model_2026-11-06.md`).
- **Football minute simulator from 2026-11-06 17:30Z** (`FOOTBALL_SIM_FROM_UTC`,
  moved by the operator into the built day, 11-06 mixed; operator 11-06; `bet.sofa.football_sim_sheet`): the path markets SHEET
  never priced - `epochs.FOOTBALL_SIM_MARKETS` (HT/FT, 1H / 2H result,
  higher-scoring half, team scores in both halves, BTTS by halves / in either
  half, 1H first goal, half goals combo; `bet.sofa.football_sim_markets`,
  mapped by OFFER, graded by SETTLE on the 90-minute and `period1` scores,
  the 1H first goal from incidents only when both sides scored, a
  contradiction refused) - take p_central from `bet.sofa.football_sim` (4,000
  sims seeded by event id on SHEET's pure rating centres; rating-only rows,
  never in a builder; marker `football_sim_rule`, rebuild_plan re-runs SHEET).
  CONFIDENCE reads them only from `config/sofa_football_sim_curves.json`
  (`bet.sofa.football_sim_curves`, walk-forward over history 06-01..10-20,
  never pooled); line evidence from the backfill
  `data/line_evidence/football_sim_lines.jsonl.gz`. Only
  `team_scores_both_halves` UNDER and `half_goals_combo` OVER reach 0.70;
  minute bands are not wired (not reliably settleable). Hold-out: model-state.md.
- **Football schedule term from 2026-11-09 11:30Z** (`SCHEDULE_TERM_FROM_UTC`,
  moved by the operator from 11-10 00:00Z into the built day; 11-09 mixed;
  `schedule_term_v1`; the one pre-registered exam of 2026-11-09, spec
  `87a5087f`, `docs/sofa/evidence/schedule_context_exam_log.md`: of goals,
  football_result, tennis_winner, tennis_games_sets only **football_result**
  passed rule (c); the rest measured and declined; ledger "11-09 mieszany",
  then "od 11-10";
  `bet.sofa.schedule_term`): the pure rating goals centres
  (`FootballForecast.centre("goals_for")`) of `epochs.SCHEDULE_TERM_MARKETS`
  (1X2, DNB, DC, score markets, first goal, the simulator's path markets
  except the four 0.60-floor keys, `SCHEDULE_TERM_FLOOR_EXCLUDED`) are
  multiplied by exp(t), t = own + opponent terms of each side's rest (days:
  R1 < 3.5, R2 3.5-5.5, R4 8.5-20.5 after an international break or not, R5
  >= 20.5 winter / other; R3 the reference), a continental game within 96 h
  before (and x R1) or after, extra time within 7 days, >= 4 games in 14
  days, as of the start (`bet.sofa.schedule_features`); frozen dev
  coefficients `config/sofa_schedule_terms.json` (never refitted on full
  history; `UNFITTED_CONSTANTS` named). Counts, game state, card points and
  samples read the uncorrected forecast; national teams / no calendar
  coverage: t = 0. Rows carry `schedule_term` and the inverted shadow
  `p_central_no_schedule_term` (carried to CONFIDENCE legs and
  `07_settled.json`; not in `sofa_settled_row` - no migration),
  `T-SCHEDULE-TERM-FORWARD` judges it (withdrawal rule frozen); marker
  `schedule_term_rule` (rebuild_plan re-runs SHEET). Their curves:
  `config/sofa_confidence_calibration.next.2026-11-09.json` (138 keys refitted
  with `--schedule-term` on a DB copy, every other key the 11-07 file's;
  `draw_no_bet|UNDER` and `result_or_over@2@5.5|OVER` removed - no curve, no
  pool: line evidence or `NO_LINE_EVIDENCE` - failing their gate with and
  without the term, operator 11-09; `staged_change.removed_keys`) and `config/sofa_football_sim_curves.next.2026-11-09.json`
  (`football_sim_curves.path_for`, dated staged files). PDF / HTML / dossier
  note "kontekst terminarza w modelu (t = ...)" - display only.
- **Sample integrity** (`IDENTITY_GATE_PER_FAMILY`, from 10-21 10:50Z): a
  past match whose payload contradicts itself loses only the metrics that read
  the contradiction (`metrics.identity_gap_for_metric`: shots identity -> shot
  metrics; goal incidents vs score -> card points / reds / penalties; home
  period sum -> goals and the incident metrics on the 90-minute score);
  tennis `gamesWon` nonsense still drops the whole match. Before it one bad
  shot count dropped the match from every sample (Roma 3-4 Real, 10-14).
  From 2026-10-24 00:00Z a football side with `ENTITY_CONFLICT` keeps its
  newest 10 matches after the newest clash instead of emptying
  (`SAMPLE_CONFLICT_CUT`; gap detail "sample cut at the clash"; fewer than 10
  after it = empty as before; two friendly tournaments excluded for it only,
  `excluded_from_sample_conflict_cut` in `config/sofa_friendly_competitions.json`).
  From 2026-10-30 00:00Z a result awarded at the table (Sofascore
  `isAwarded`: forfeits, walkovers after a withdrawal, an unplayed 3-0 / 0-0)
  leaves the samples and the football rating SHEET replays
  (`AWARDED_EXCLUDED`, `comparability.is_awarded_event`; gap "awarded";
  Maardu's 0-0s in Kalev's / Kalju U21's goal samples, 10-29); SETTLE
  refused it already. The dossier leaves it out of its counts by the same
  switch; a refit replays it with `--awarded-excluded` (an install while the
  switch is on refuses a replay without it), every football fit takes the
  flag and records it (`fitted_from.awarded_excluded`; prepare_refit warns
  on a replayed fitted file without it).
- **Confidence review 2026-10-27** (literature, every sport; report
  `docs/sofa/history/PRZEGLAD_PEWNOSCI_2026-10-27.md`, model-state.md): from
  2026-10-28 00:00Z a football joint's side with no quoted ladder gets its
  marginal row's whole centre chain (`JOINT_FILLED_SIDE_CHAIN`,
  `bet.sofa.centre_chain`, note `JOINT_SIDE_CHAIN`) and tennis per-set games
  handicap reads the rating neighbours' own set scores
  (`TENNIS_SET_HANDICAP_NEIGHBOURS`, note `SET_HANDICAP_NEIGHBOURS`). Coded and
  off (measured not better): hockey late goal in the P3 mean
  (`HK_LATE_GOAL_IN_MEAN`), CS2 decider-map posterior
  (`CS2_DECIDER_MAP_POSTERIOR`), exact NB first goal (`FIRST_GOAL_NB_EXACT`).
- What each estimator does today (ratings, dispersion, stretches, cup strength,
  opponent correction, new markets...) and when it switched on: model-state.md.

### What prints

- **A leg prints** when confidence >= 0.70, confidence x odds >= 0.90, ladder
  (group) margin <= 15% (`COUPON_PROFILE`), not ODDS_TOO_LOW, not started,
  fresh price (STALE_PRICE otherwise; a moved price re-prices the leg). Every
  passing single prints - no page limit. **Tennis `games_total` /
  `sets_total` from 2026-11-05 17:05Z** (moved into the built day by the
  operator; 11-05 mixed) pass at confidence 0.60
  (`TENNIS_TOTALS_FLOOR`, `epochs.leg_floor`; operator 11-05: "as good as the
  price, margin accepted" - hold-out calibrated and at the de-vigged price,
  ROI -4.6%): such a leg carries `floor_rule`, never joins a builder, C2
  audits its own floor; every other gate unchanged (model-state.md).
  The football simulator's keys (from 2026-11-06 17:30Z) print on the same gates:
  0.70, x >= 0.90, 15% margin on the two-sided rungs, one-sided only from
  their own curve with n >= 300; four of them pass at 0.60
  (`FOOTBALL_SIM_FLOOR`, 2026-11-06 17:30Z, operator 11-06 "TAK!":
  `team_scores_both_halves` UNDER, `half_goals_combo` OVER, `btts_any_half`
  UNDER, `btts_halves` OVER - each measured on its own 0.60-0.70 band, frozen
  rule, calibrated and at the de-vigged price, ROI -1..-10%), with
  `floor_rule`, never in a builder, C2 audits their own floor
  (`docs/sofa/evidence/football_sim_floor_2026-11-06.md`). `btts_any_half`
  UNDER and `btts_halves` "Nie/Nie" are ONE event (audit 2026-11-07): the
  floor stands on three distinct events, and the two legs print once from
  `SAME_EVENT_DEDUP` (below).
- **Refusals worth knowing** (each named on the row):
  - `CROSS_LEAGUE_UNLINKED`: a football pair is LINKED only when both sides'
    leagues are the competition they share (the hockey / basketball /
    volleyball score model reads the same book; rows carry `link_rule`);
  - `NO_CLASS_CURVE`: women's football, women's tennis and tennis team cups
    read only their class's curves;
  - `NOT_SETTLEABLE`: (competition, family) cells whose printed legs went
    ungraded for want of the statistic; from 2026-11-03 refitted every
    morning by `refresh_line_evidence.py` step 3 into
    `config/sofa_settleability.<D>.json` (a day reads the latest dated fit
    <= it, `settleability.path_for`; earlier days the 10-05 file; a refused
    cell the window cannot judge is carried - it prints nothing; `day_status`
    `settleability`);
  - K13 / K13b: a thin direction bucket caps the curve; a pooled read is capped
    by the market's nearest own bucket below;
  - `SAMPLE_CROSSES_SEASON` (180 days, `MAX_BUILDER_SAMPLE_AGE_DAYS`) - national
    teams judged by count (`NATIONAL_SAMPLE_AGE`);
  - CS2 team-rounds line outside 9.5-12.5: `LINE_OUTSIDE_FIT`;
  - `BEST_OF_FIVE_NOT_MODELLED`: tennis `sets_total` not known to be best of three;
  - `NO_LEAGUE_RATE` / `FRIENDLY_FIXTURE` for the measured sports (competition
    below 30 matches / friendly);
  - one-sided legs (football player props, OVER-only score-market rungs): no
    overround, so the 15% rule cannot judge them; such a leg prints as a single
    only when its confidence is its own market's (or slice's) history curve
    with n >= 300 (`confidence.one_sided_single`; PDF margin column "1-str.");
    every other gate applies;
  - player shape gates: a footballer row on `confidence.PLAYER_SHAPE_GATE_MARKETS`
    needs only `PLAYER_MIN_SAMPLE` (5) values (age, curve, line evidence, floor
    and x unchanged); a leg a shape gate would have refused carries
    `player_sample_rule` and never joins a builder.
- **Players** (football): sample = his starts (Superbet voids a non-starter;
  SETTLE `PLAYER_NOT_STARTED`); a name `players.match_player` misses is tried by
  whole tokens (`match_rule: "tokens"`), then surname + first-name prefix
  (`match_rule: "surname"`), then `transliteration`, `inner_surname` (10-21,
  `FOOTBALL_PLAYER_COVERAGE`), and from 2026-10-24 00:00Z last by his Sofascore
  slug (`match_rule: "slug"`, `PLAYER_SLUG_NAME`); SETTLE grades the
  `matched_name` from his own squad (a candidate in the other squad is
  PLAYER_AMBIGUOUS). From 2026-10-24 a sample still thin after the 20-match
  window is topped up with the same player id's starts for other teams (from
  cached lineups of the sample proper's opponents' own newest 20 matches, each
  admitted as the sample proper admits a match - `samples.peer_history` - one
  row per (match, peer), never asked, never by name; a `THIN_SAMPLE` gap, detail `PLAYER_HISTORY_ANY_TEAM:`,
  marks a sample that IS used; `samples.any_team_sample`). Players'
  zero offsides from a team's rebuilt 0-0 (`PLAYER_OMITTED_ZERO`) measured
  worse and off.
- **Start clock** = earliest of RESOLVE's clocks and Superbet's
  (`superbet_kickoff_seen_utc`), or - once FIXTURE_CHECK read a fresh `/event`
  start - of that start and Superbet's newest clock (it replaces RESOLVE's
  frozen ones, `locked_print.kickoff_clocks`: a match moved later is not
  gated on its dawn start); Superbet's start signal (`superbet_started_utc`;
  in-play odds dropped for every reader) counts as started. A postponed /
  cancelled printed match is FIXTURE_NOT_AS_SCHEDULED; no bridge = UNVERIFIED,
  nothing refused. A transient error on one fixture (504 / timeout / 5xx) is
  retried once, then that fixture is UNVERIFIED and the check goes on; a
  refusal (403 / 429, breaker) or two fixtures in a row given up stops it. Blind
  spot: a suspended pre-match offer with no metadata; only the clocks see it.
- **Peer choice** (annotation only): two legs of one match on different
  variables priced within `PEER_BAND` 0.06 are peers (`bet.sofa.peer_choice`);
  the surer is starred (★, `peer.preferred`). Small measured edge (53.4%); no
  sample statistic or tournament flag re-ranks peers. **Stakes**
  (`STAKES_SIX_POINTER`, `STAKES_TOP4`, `bet.sofa.stakes`) are a context flag:
  shown, never gated, never a correction.
- **Confidence above the price** (annotation only): a football / tennis leg
  whose confidence exceeds 1/odds by more than `GAP` 0.03 carries `price_gap`
  (`CONFIDENCE_ABOVE_PRICE`) and a sentence on the PDF / HTML. Such legs realise
  about at their price, below their confidence (`T-PRICE-GAP-flag` passed
  10-19: -10.0 pp on 2,111 legs) - the printed number over-promises, the money
  is alike. CS2 carries it too from `CS2_PRICE_GAP_FROM_UTC` (10-21 00:00Z;
  settled Superbet lines 09-28..10-19: -18.6 pp [-27.1, -10.1] on 238 lines,
  `measure_cs2_price_gap.py`, `T-CS2-PRICE-GAP-flag`); hockey / basketball /
  volleyball carry none.
- **Rating below the market's margin** (annotation only,
  `RATING_MARKET_GAP_FROM_UTC` 2026-11-04 00:00Z, operator "wdróż od
  dzisiaj"; `bet.sofa.rating_market_gap`, written by CONFIDENCE): a football
  leg that depends on the favourite's strength (favourite's team goals UNDER,
  underdog's team goals OVER, the underdog's result / DC / DNB / +handicap,
  underdog or draw "lub poniżej"; full match only) in a match where Superbet's
  expected goal margin for its favourite (NB fit to 1X2 / DC 12 / team and
  match totals of 04_offer) exceeds our pure rating's (SHEET's notes) by D >=
  `THRESHOLD` 1.0 carries `rating_market_gap` (`RATING_BELOW_MARKET_MARGIN`)
  and a sentence on the PDF / HTML / md. Such legs realised about at their
  price, below their confidence (printed, D >= 1 minus D -0.5..0.5, hold-out
  from 10-25: -3.4 pp [-9.3, +2.6] vs confidence, +1.8 [-4.3, +7.5] vs price;
  `docs/sofa/evidence/rating_vs_market_disagreement_2026-11-04.md`). Nothing
  moves: not a gate, not in `read_value`, never a read ground on its own; no
  ledger group. Missing either view = no entry; an error, or no view at all
  on a day of >= 20 football matches (SHEET's note wording moved), is a
  `WARN rating_market_gap` on CONFIDENCE's stderr and never stops the build
  (`rating_market_gap.safe_views`). `T-RATING-MARKET-GAP-flag`.
- **Bet Builders:** one per fixture, by best `combined_probability`; an internal
  haircut x >= 0.90 decides stakeable and is never printed. **sofa does not
  price a builder**: the PDF shows its legs with Superbet's single prices, the
  combined p and "kurs buildera: sprawdź na ekranie Superbetu". A screen price
  in `09_screen_prices.json` is shown back as the operator's note.
- **Assembly** (`build_coupon.py`): order by confidence, then earlier start,
  one match's legs together; legs locked from an earlier print first,
  unnumbered; builders B1.. on their own pages; ladders under "ta sama
  zmienna"; an exposure-per-match section. A leg printed before its start stays
  (locked); a leg removed before its start stays removed. `ladder_form` /
  `max_positions_per_match` are OFF unless `config/sofa_coupon_form.json` sets them.
- **One event, one leg** (`SAME_EVENT_DEDUP`, from 2026-11-08 00:00Z, audit
  2026-11-07, operator "TAK!"; `bet.sofa.leg_identity`): two market names of
  one outcome print once - e.g. `btts_any_half` UNDER = `btts_halves`
  "Nie/Nie", a side's goals over 0.5 = `result_or_btts` of that side, the four
  names of "not 0-0", hockey handicap +-0.5 = double chance / 1X2 (and per
  period), basketball first half / quarters 1-3 likewise (never the full
  game, the second half or the 4th quarter: overtime),
  volleyball set handicap +-2.5 = "wins a set", best-of-3 CS2 maps handicap
  +1.5 = "maps over 0.5" (CS2 legs carry `best_of`; none = no match). The
  identity is LOGIC (football: graded on every half-time / full-time path
  with SETTLE's graders), never agreement on settled rows (a DNB is not the
  double chance). A locked leg stays and its fresh twin goes; a fresh twin
  of an event a read refused (`removed_by_reads`) goes too
  (`same_event_refused`: the twin was never read); among fresh legs one
  already on a printed render stays, else the higher price, then the lower
  confidence; the rest go to `removed_as_same_event` (`same_event_as`). Before it 667 printed legs of
  10-13..11-06 were a second leg of an event already printed - the ledger
  counted those outcomes twice (ROI the same, -5.27%;
  `measure_same_event.py`). Ledger group "od 11-08".
- **Superbet's words** (`bet.sofa.superbet_names`, display only): every leg
  carries `superbet_market` / `superbet_selection` as the screen writes them
  ("3. tercja - Seattle Kraken - liczba goli" / "poniżej 1.5"); a market it does
  not know keeps its old label, nothing guessed. The PDF / HTML name legs this way.
- **Reads on request** (`READS_ON_REQUEST_FROM_UTC`, from 2026-11-02 00:00Z,
  operator 11-02): `/sofa-day` prints without the analysts; reads come only from
  `/sofa-analyze` or `/kupon`. The read set and the rules below are unchanged and a
  read that is made still removes its leg; audit C3 counts read-set legs printed
  unread as a note, a printed WATCH / NO_BET stays a defect (`audit_variants.audit_reads`).
- **Reads:** analysts read every unlocked leg of the first 20 matches by value
  (30 on a coupon built before `READ_SCOPE_FROM_UTC` 2026-10-27 00:00Z, operator 10-26; the artifact's `read_events`)
  (best unlocked leg's confidence x odds, a football / tennis or flagged CS2
  confidence capped at 1/odds + `price_gap.GAP`; `confidence.read_value`), every printed builder
  leg and `read_requests.json` (`confidence.legs_requiring_read`; audit C3; a
  rebuild moves positions, so re-read with `read_set.py --unread` until C3 is
  clean); the rest prints unread. WATCH or NO_BET in `reads.json` - or the
  automatic football `MODEL_ABOVE_OWN_SAMPLE` (model minus own-sample hit rate >
  `MAX_OWN_SAMPLE_GAP` 0.15, props excluded) - moves a leg to
  `removed_by_reads`, graded on its own, never in the coupon's result.
  `context_flags` (`MAKEUP_FIXTURE`, `LONG_LAYOFF`, `CONGESTED`) are shown,
  never gated. Every analyst reads the match's dossier first and makes a web
  context pass on every match not yet started (news, weather, morale and the
  backstage - `MORALE` tag - stakes, opinions; operator 2026-10-20); one
  domain or an opinion carries at most a WATCH, through the leg's variable.
  From reports of 2026-10-27 (operator's go 10-26) a WATCH / NO_BET reason
  names a dated fact newer than the price (`[WEB: ..., publ. ...]`) or an
  artifact defect (`DEFEKT: ...`) - h2h, form, table, a model-sample gap,
  `price_gap` never remove a leg - and a KEEP is per market family
  (`report_check`, the hook sends a report back). From reports of
  2026-10-29 (operator 2026-10-29: a market's drivers are never skipped;
  moved from 10-30 into the day by the operator after the E2E test)
  every leg's market drivers are checked per family
  (`sofa-analysis-core/references/market-drivers.md`, from the literature);
  a WATCH - never a NO_BET - may also rest on one with the dossier's numbers
  (`RYNEK: <driver>: <k/n>`, `context: "MARKET"`, ledger-graded by tag; the
  opponent-concession / both-sides share >= 0.25 below the leg's confidence,
  or an OVER side's corners below 50% own possession under the line on >= 4
  games) - **checked by the code** against the leg's own dossier row
  (`report_check.market_findings`, dossier schema >= 3: one leg with its
  line, threshold computed, the row's k/n quoted, no h2h / form / rating
  after the mark; merge_reads refuses the whole report otherwise, E2E
  2026-10-29); a veto is sourced alike (`WETO BEZ FAKTU`); every section opens
  with `**W skrócie:**`, a football count-market read carries the
  "Styl gry i zestawienie" table. The hook checks the verifier's
  `_weryfikacja` reports too (same removal rules). The concession signal
  measured 10-29 was not robust (model-state.md (d)) - the MARKET removals
  are its out-of-sample measurement. From reports of 2026-11-02 (operator
  2026-11-01, after Pereira 3-6 3-6: retired 10-25, SAMPLES drops an
  abnormally finished match) a tennis WATCH - never a NO_BET - may rest on
  `KRECZ: <gracz> <data>` (`context: "RETIREMENT"`): the dossier's
  `sides.<side>.retirement` (`dossier.recent_retirement`: a singles match
  lost Retired / Walkover <= 14 days before, none completed since, also
  first on the web checklist), **checked by the code**
  (`report_check.retirement_findings`). `sofa-analyst-sport` runs on Sonnet
  (operator 10-26: cost).

### Measured sports (hockey, basketball, volleyball, CS2)

SHADOW / CS2 snapshot Superbet -> SPORT_IDENTITY pins the Sofascore id before
the start (an event not identified by its start keeps its last pre-start
record, `frozen_at_start`) -> SPORT_CONFIDENCE reads the sport calibration
(fitted without prices) and corrects it with line evidence. SHADOW / CS2 are a
measurement of Superbet's price and feed nothing else.

- **Day window** (`SPORT_LATE_WINDOW`, from 2026-10-23 00:00Z, operator
  10-22): a measured sport's day D is [end(D-1), end(D)) with end(D) = D+1
  05:00Z (`sport_identity.day_window`; football / tennis keep the UTC day),
  so NBA / NHL games after midnight UTC are D's, not the next morning's
  KICKED_OFF. SHADOW / CS2 of D fetch them once early into D+1's file; legs
  starting on D+1 carry `window: "late"`; an event D-1's printed coupon holds
  is `ALREADY_PRINTED_PREV_DAY`. They print only through the operator's
  **manual evening rebuild** - `rebuild_day.py --date D` at ~20:00-21:00Z
  (not automated), which appends them; morning legs stay locked. The loops'
  next morning settles D+1's file up to end(D) (`--kickoff-before`); grading
  reads each leg's `source_date` file. `day_status.py` treats the sports' day
  as over at end(D).
- **Identity**: the entity map (`bet.sofa.entity_map`) learns verified names
  from SPORT_IDENTITY; opponent-only matches are candidates, conflicts are
  queued and never overwritten (`SofaCache.save_entity` in `src/bet/sofa/cache.py`
  follows the same rule). Manual decisions: `config/sofa_entity_aliases.json`
  (fuzzy matching never writes it); the queue `report_entity_queue.py`. Day
  anchor, tournament day and proven absence (`NOT_ON_SOFASCORE`) identify the
  rest; details in model-state.md. From 2026-10-24 00:00Z (coverage audit,
  model-state.md "Coverage audit 2026-10-23"): a refusal read from a cached
  team page within 3 h of the start is re-asked fresh whatever its reason,
  then the other side's page is asked too (`IDENTITY_FRESH_RECHECK_ALL`, P2;
  ~120-180 extra requests a day; a second page showing the game but refusing
  it blocks `NOT_ON_SOFASCORE`, `absence_contradicted_by_second_team`); a
  volleyball event with no resolved side is
  the query team's ONE game at Superbet's exact start, named >= 90, the
  opponent agreeing weakly and not vetoed by its own query
  (`SPORT_QUERY_ANCHOR`, P4, `match_method` QUERY_ANCHOR; backtest 0 wrong of
  2,480; never learned as a name); CS2 "prospect" = "prospects"
  (`NAME_RULES_1023`, P8).
- **Basketball league rate** (`LEAGUE_SEASON_RESTART`, from 2026-10-23
  00:00Z, operator's go 10-22): a league back after >= 45 days off reads the
  ended season's plain mean, and its level restarts from it worth 10 games
  (home share slow) - the NBA had carried its playoffs into October (218 vs
  229 points). Basketball only (hockey / volleyball measured worse); the
  installed basketball curve was fitted without it (a refit needs a go).
- **History** is kept current by `refresh_sport_history.py` (run first by
  `refresh_line_evidence.py`); `day_status.py` WARNs `sport_history` below 80%
  of D-1's pinned games.
- Every fitted key prints on the same rules as football and tennis. Volleyball
  needs a tournament with a settled event in the last 14 days. A sport without
  a usable calibration is `NOT_CALIBRATED` (exit 1, the rest still builds).
- Extended markets: `sport_confidence.EXTENDED_MARKETS` (basketball quarters,
  second half, dnb, odd/even; hockey period dnb; volleyball exact set score,
  points / set parity, set on extra points); CS2 `CS2_EXTENDED_FAMILIES` (map
  round handicap / total, team kills, player kills / deaths / assists /
  headshots) and series families from a Beta-mixed series distribution
  (`cs2_engine.SERIES_KAPPA`); round parity unpriced.
- **Basketball period curves** (`BB_PERIOD_MARKET_LINES`, from 2026-11-06
  00:00Z, operator's install go 11-05; ledger: 11-06 is "11-06 mieszany",
  then "od 11-07" - the group "od 11-06" holds no day): the h1 / h2 /
  quarter total, handicap and team-total curves are fitted on lines placed
  where the market stood - the game's Sofascore total / spread / period count,
  +-2 points (`sport_confidence.period_position_lines`), as the full-game ones
  (A7) - not at the model's own quantiles; 15 keys in
  `config/sofa_sport_confidence_calibration.next.2026-11-06.json`. Settled
  Superbet lines 10-18..11-04: >= 0.70 -14.1 -> -0.0 pp, log loss -0.021; most
  period legs stop printing (model-state.md).
- **Volleyball rally-point model** (`VB_POINT_MODEL`, from 2026-11-06
  17:30Z by the build clock - moved by the operator from 11-07 00:00Z into
  the built day, 11-06 mixed; operator 11-06: "install what beats the current
  estimator; the price need not be beaten"; ledger groups "11-06 mieszany",
  "od 11-07"): the lines of
  `epochs.VB_POINT_MODEL_MARKETS` (winner, points / set handicap, points /
  set-points totals, exact sets, set winner, points parity) take p from
  `bet.sofa.volleyball_point_model` through `bet.sofa.vb_point_pricer` (team
  rally strength as of the start, Kalman on the point share, league-mean
  prior; side-out chain, 4,000 seeded rally-by-rally matches) in
  SPORT_CONFIDENCE (`DbForecaster`, leg field `vb_point_model_rule`,
  `forecast_source: vb_point_model`); sets total, extra points, team-set and
  sets-count markets keep the score model. Their curves: the rally model's
  walk-forward in `config/sofa_volleyball_point_curves.json`, overlaid by
  `sport_confidence.with_vb_point_curves` onto the day's calibration by the
  switch's build clock (the file choice is by day only; 11-06's
  `.next.2026-11-06.json` is untouched, `.next.2026-11-07.json` carries the
  same 16 keys - a no-op there); line evidence at the rally p (`vb_point_pricer.BACKFILL`, kept by
  `backfill_vb_point_p.py`, refresh step 1b). Hold-out 10-20..11-05 vs the
  current chain: Brier better in every wired family by point estimate (points
  handicap -0.0048 [-0.0135, +0.0038] and points parity cross zero; the
  families were chosen on this hold-out - audit 2026-11-07), >= 0.70 points handicap -19.7 pp (current
  -22.6) - still over-promising; the price beats both
  (`docs/sofa/evidence/volleyball_point_model_2026-11-06.md`).
- Hockey / basketball player lines: p = player_model's pre-game number in
  SHADOW's `player_model.jsonl`; no history curve, so `NO_LINE_EVIDENCE` until a
  family's p bucket holds 50 settled pre-game lines; graded from SHADOW_SETTLE's
  own player row (football's token / surname rules, then tokens without Jr /
  Sr / II; a nickname is never guessed). From `BASKETBALL_PLAYER_V2`
  (10-23 00:00Z) SHADOW also reads the NBA's free throws made / attempted,
  field goals made / attempted, two-pointers made / attempted, threes
  attempted, personal fouls and turnovers (`shadow.PLAYER_V2_MARKETS`, one
  box key each; `player_v2_rule`); not read: first-quarter player lines,
  "N+" milestones, most / first, double / triple double.
  From 2026-10-24 00:00Z (audit P3 / P8 / P9): a hockey player's sample also
  reads the peers' games (the two teams' opponents, by side; his own sample
  only, never the pool; a name absent from both teams looked up among them;
  `player_history_rule`), basketball measured worse and off
  (`PLAYER_HISTORY_ANY_TEAM[_SPORTS]`); hockey names fold transliterations
  (Stuetzle / Stützle, Yegor / Egor; `NAME_RULES_1023`); a game seen on one
  team's `last` page only is listed for the other as kind `last_side`
  (`sport_history.list_both_sides`, written by every
  `refresh_sport_history.py`), read by the pre-game and settle numbers from
  `PLAYER_BOTH_SIDES_LISTED` (`player_lists_rule`; nothing reading `last` sees
  it; `fit_player_model.py` reads `last` only). Player constants resolve per
  day (`player_model.params_path_for`, a staged
  `config/sofa_player_model.next.<YYYY-MM-DD>.json`); none staged.
- CS2 from 2026-10-24 00:00Z: a pair whose team ids are not both rated reads
  the lineup gap through its own calibration (`CS2_LINEUP_ELO_UNRATED`, P7,
  `cs2_engine.fit_unrated`; rated pairs unchanged; such a leg carries
  `lineup_unrated_rule`); the engine finds a player's nickname as settlement
  does - the exact nickname on either roster first, then a prefix
  (`NAME_RULES_1023`); a series
  graded from its result alone carries `model_p` (`CS2_SERIES_ONLY_MODEL_P`,
  P12, by the settle clock; earlier series once through `settle_cs2.py
  --attach-series-only-model --sweep-from 2026-09-28 --sweep-to 2026-10-23`,
  the 10-24 morning before `refresh_line_evidence.py`; a settle writing
  meanwhile keeps the attached `model_p`) - line evidence only.
- A volleyball match followed by a golden set (Sofascore AET / AGS,
  `shadow.GOLDEN_SET_DESCRIPTIONS`) is FINISHED and graded on the match's own
  sets - winner by the sets, never `winnerCode` (the tie's winner on 28 of 90
  cached games); the golden set (`overtime`) counts in nothing (Regulamin
  5.D.3.a; correctness fix, live 2026-10-23). The score-model history reads
  such a match from `VB_GOLDEN_SET` (10-24 00:00Z, P13). Basketball halves
  leagues (NCAA, `score_model.BB_HALVES_COMPETITIONS`) only under
  `BB_HALVES_LEAGUES` - OFF (P11: no NCAA basketball in Superbet's offer yet,
  halves not settleable).
- SHADOW_SETTLE only (correctness fixes 2026-10-26, history readers unchanged): a
  basketball / hockey `normaltime` above the final score is a payload defect and
  the periods are read (`build_result(..., allow_final_only=True)`; Golden State -
  Memphis 10-24 was a whole-game DATA_MISMATCH); a player name is also tried with
  generational suffixes dropped and adjacent initials joined ("PJ Washington" /
  "P.J. Washington Jr.", `shadow._bare_name`). A box that does not sum to the score
  stays refused (Milwaukee - Chicago 10-23, 494 lines; `player_retry`). An NCAA
  men's game (`score_model.BB_HALVES_COMPETITIONS`) with two periods is read as two
  halves (`GameResult.halves`, `score_source: "halves"`; h1 / h2 one period each,
  quarters ungradeable; 2026-11-05: 136 NCAA DATA_MISMATCH of 10-22..11-04). NBA player
  model measurements and why no leg prints:
  `docs/sofa/evidence/nba_player_model_2026-10-26.md`.
- Basketball second half / Q4 grade on regulation periods (overtime does not
  count); full-game basketball markets include it.
- A hockey / basketball game with no periods is graded from its final score
  (`shadow.build_result(..., allow_final_only=True)`, SHADOW_SETTLE only,
  `score_source: "final_only"`): full-game markets only, never a period / half /
  quarter. A CS2 player line whose nickname Superbet extends reads the one
  roster nickname of >= 5 letters that prefixes it (`cs2.MapResult.player`).

## Settlement and the ledger

- **SETTLE refunds** (0 u., never a loss; `settle.REFUND_REASONS`): match put
  back past Superbet's deadline - **23:59 of the day after the offered start,
  local time at the venue** (`settle.void_deadline`, zone from venue /
  competition / home country, `config/sofa_country_timezones.json`, UTC when
  unknown; Regulamin 5.E.1.a) - or brought forward > 48 h (`VOID_AFTER`),
  awarded, retired (`RETIRED`), walkover (`WALKOVER`), cancelled (`CANCELED`)
  or still postponed past the deadline (`POSTPONED_BEYOND_VOID`; before it
  `POSTPONED`, pending). SHADOW_SETTLE / CS2_SETTLE read the same deadline. An
  abandoned match (5.D.5) is not graded yet.
- Football grading: decided on penalties without extra time = whole-match
  statistics (`metrics.played_extra_time`); after extra time non-goal counts
  stay `EVENT_NOT_FINISHED`; goals always `normaltime`; samples and ratings
  still skip both (changing that changes what prints). A card shown to a player
  on the bench does not count in SETTLE / regrade (`metrics.drop_bench_cards`;
  samples keep every card). A half whose `period1` contradicts the HT marker is
  refused when settling (`metrics.half_time_disagrees`; a graded row stays).
  Player props grade only from the player's own squad (PLAYER_AMBIGUOUS);
  `PLAYER_DID_NOT_PLAY`, `PLAYER_NOT_STARTED`, `PLAYER_NOT_IN_SQUAD` are listed
  in `07_settle_skips.json` `void_legs` and a printed such leg is a refund; a
  printed leg without a sheet row goes to `07_settled_printed.json`.
- Sport legs grade at the printed price against the pinned id
  (`NOT_GRADED:ID_CHANGED` otherwise); a volleyball set / CS2 map never played
  is VOID (`shadow.set_not_played`); in their own 7c table, never in
  `sofa_settled_row` or `fit_confidence`. Statistic gaps close days later:
  `resettle_sweep.py` every morning.
- **Results on the coupon**: `record_results.py` marks each graded day
  (`mark_coupon_results.py`; `--no-mark` skips): `13_results.json`, then
  `build_coupon_pdf.py --with-results` re-renders KUPON pdf / html - green won,
  red lost, yellow unknown or refund; claim beside what the market counted;
  per-sport summary. Grades are the ledger's, never a second grader; a printed
  leg the results do not hold is yellow. Only days from
  `coupon_results.RESULTS_FROM_DATE` (2026-10-13) that are over (before today,
  UTC); a refunded builder's legs are yellow; originals kept
  as `KUPON_<d>.przed_wynikami.pdf` / `.html`. A results render is a view, not a
  print: no `printed/<ts>.json`, no freshness guards, the printed files' mtime
  kept (CONFIDENCE and audit C1 read the PDF's mtime as "printed"). Only
  `--with-results` reads `13_results.json` - a normal render never shows
  results; the next mark draws them again. Display only.
- **Ledger** (`record_results.py` -> `runs/sofa/ledger/results.jsonl`, read with
  `audit_ledger.py`): the coupon's result, the read-removed legs and each sport
  side by side, never pooled. It reads `sofa_settled_row`: re-run it after any
  `regrade_settled.py`. Exit 0 with legs pending, 1 on a `MISMATCH` (two graders
  disagree - a defect), 2 on a crash.
- **Comparability:** a refit install or an epoch switch starts a new epoch; a
  switch moved into a built day makes the day mixed (its own group, summed with
  neither neighbour). Groups are never pooled. The groups:
  `audit_ledger.EPOCH_GROUPS` (`scripts/sofa/audit_ledger.py`) and model-state.md
  section (f).

## Changing the pipeline

The shape above stays; it is improved, not rebuilt.

1. **Measure first.** A change comes with a measurement on settled rows or
   history (match bootstrap, out of sample) or it is a suspicion. `measure_*.py`
   scripts are read-only evidence.
2. **Correctness fixes** (a misgrade, a wrong mapping, a crash) go live at once,
   with a test.
3. **Anything that changes what prints** gets a switch in `bet.sofa.epochs`,
   by default effective from the next day's 00:00Z. Only the operator moves it
   earlier, to an exact time (the day is then mixed and says so); never on
   your own mid-day.
4. **Refits and calibration fits** (`prepare_refit.py`, `fit_*`) run on a
   **copy** of the database (SQLite `VACUUM INTO`, then `--db-path <copy>`
   with `--without-db-backup`; scratch in `data/refit_<date>/`), never
   against live rows, so the daily loops stay up. `install` runs
   `tests/sofa` and restores on failure. Installing changes what prints, so
   it needs the operator's go - and no refit without it, mid-day included.
   **Standing go for the 2026-10-13 audit** (operator, 2026-10-13;
   `docs/sofa/history/AUDYT_RYNKOW_KONTEKST_2026-10-13.md`, "Decyzje
   operatora"): while implementing that audit a switch may be turned on by
   the implementing session when the out-of-sample measurement is better with
   an interval excluding zero, `tests/sofa` pass and a report is written; a
   refit carrying the audit's fixes may be installed without a further go,
   also into a day already built - then at an exact UTC time, the day is
   mixed and says so, printed legs stay locked, and the ledger opens a new
   epoch. Nothing else is covered by this go.
5. **Every fix ships a test** in `tests/sofa/` (offline, fast); run the gates.
6. **Update this file's section** (or model-state.md for a switch / fit /
   measurement) and the Polish doc in `docs/sofa/`; a run or a night gets a
   report in `docs/sofa/history/`.

A refit replays every rule the installed curves carry
(`fitted_from.replay_rules.flags` of `config/sofa_confidence_calibration.json`:
today the 10-16b flags plus `--goals-stretch --count-stretch --player-stretch`;
from 2026-10-30 also `--awarded-excluded`, which `install` requires while
`AWARDED_EXCLUDED` is on) and never `--tennis-serve-markets` / `--tennis-aces-opponent` (model-state.md).
Every SHEET row carries `config_sha` (`bet.sofa.sheet_config`, the fitted
files SHEET reads); a sheet priced on other constants gets a `CONFIG_CHANGED`
note but is **not** re-run - an install is undated and never goes into a built
day without a go; with one, `run_pipeline.py --only SHEET` by hand. Curves need
nothing (CONFIDENCE reads them on every rebuild). `rebuild_plan.py` re-runs SHEET
itself when a switch is on for the day and the build clock and a row of its
sport lacks the switch's marker (a sheet without that sport never re-runs).
The coverage audit's P1 / P3 / P5 / P14 carry no such marker: a 10-24
SAMPLES / SHEET built before 00:00Z stays on the old rules, and moving one of
them into a built day needs SAMPLES / SHEET re-run by hand - rebuild_plan
will not see it. Their curves are
not replayed: `prepare_refit.py` warns on install (`replay_switch_warnings`)
while P1 / P3 (football) / P5 / P14 is on, `fit_sport_confidence.py` for P7 /
P13 (`fitted_from.unreplayed_switches`); neither refuses.

Daily loops spawn each step through `run_pipeline.py` (fresh code per step);
only the loop's own orchestration is old code until it ends - a loop started
before a code change runs its old steps until it ends.

## Entry points

| you want | use |
|---|---|
| a full betting day - D-1 settled and recorded, the coupon + PDF, verification (no analysts - on request) | `/sofa-day [dzisiaj\|wczoraj\|YYYY-MM-DD]` |
| the analysts' read of an existing coupon ("dodatkowo: <pozycje>" adds to `read_requests.json`; "okno 14-17" rebuilds on fresh prices, then asks for the window's 20 best-value matches, every market - `window_reads.py`) | `/sofa-analyze` |
| coupon + PDF from artifacts on disk (`rebuild_day.py`) | `/sofa-rebuild` |
| adversarial verification of a built day | `/sofa-verify` |
| settle D-1 and decide about constants | `/sofa-settle` |
| price a slip the operator screenshotted | the `bet-slip-audit` skill |
| a chat slip (AKO) to a target price from the day's coupon (every market, a time window; each leg read, a refused leg replaced and read) - the least-loss flow (operator 2026-10-31, no flow clears zero after the 12% tax, `docs/sofa/evidence/slip_flow_backtest_2026-10-31.md`): 2 legs by default (more only when asked, each extra leg's measured cost stated), builders only when asked (measured -16.6% / -45.8%), a target the limit cannot reach said first with the closest slip, low-margin (< 0.08) legs win a near-tie; redesign 2026-10-31 (`docs/sofa/evidence/kupon_od_nowa_2026-10-31.md`: ~1,800 cells, frozen rules, one hold-out - no statistic tells a good leg from a bad one at the same price, no ranking beats random): pool = legs with the match's own sample >= 8 (`slip_builder.MIN_SAMPLE`, CS2 engine exempt, `--allow-no-sample` on request), the chosen legs re-asked just before the answer (offer / the sports' newest pre-start snapshot) and dropped when the price rose > 2% (`PRICE_RISE_DROP`) or left the offer, evidence columns (model, own sample, zestawienie, league, h2h, referee - `bet.sofa.slip_evidence`, cut at the kickoff) display only, "przewagi nad ceną nie ma" said; money line = 0.88 x 0.960^n - 1 (the pool's measured 0.960 of price, n 36,940), never a return from our confidence; the measured sports' fresh price asked of Superbet's event endpoint there and then (the loop's parser; snapshot as the fallback); a leg already in an earlier slip of the day (`runs/sofa/<d>/slips/*.json`) or its match is named under "Ekspozycja" (never a gate), `--new-matches` leaves those matches out (/kupon experiment 11-01) | `/kupon 11-13 [~4] [x2] [3 nogi] [buildery] [pewny]` (`build_slip.py` + analysts through the `bet-slip-audit` skill's loop; `pewny` = `--safest`, operator 2026-11-01: the highest measured chance at a leg price product >= the target, floor 1.14 where a win pays back about the stake after tax, read legs kept only within 1 pp of the pool's surest) |
| check the operator's own Bet Builder from a screenshot (each leg's measured chance vs 1/odds, zestawienie, the legs' joint k/n in both sides' games, the screen price) | `build_slip.py --date <d> --check "<mecz>\|<rynek>\|<wybór>" [--check ...] [--screen-odds X]` (read-only) |
| the basketball handicap paper test (sofa-day 1c; report only at n >= 300) | `paper_bb_handicap.py --date <D-1> --pending --report` |

Agents: `sofa-runner`, `sofa-analyst-football`, `sofa-analyst-tennis`,
`sofa-analyst-sport` (one instance per measured sport), `sofa-verifier`,
`sofa-settler`, `sofa-market-scout`. Preloaded skills: `sofa-pipeline`,
`sofa-analysis-core`, `football-analysis`, `tennis-analysis`, `sport-analysis`. An analyst writes
its own report (`runs/sofa/<d>/<d>_analiza_<sport>[_<part>].md`); the caller
merges it with `merge_reads.py`, never re-types it. Agent definitions and
skills load at session start: an edited one is live only in the next session.

## Commands

Python runs as `PYTHONPATH=src:. .venv/bin/python ...` (3.12; `.venv/bin/pip`
belongs to 3.14 - install with `.venv/bin/python -m pip`). Exit codes: **0 OK,
1 PARTIAL, 2 FAILED**; PARTIAL on RESOLVE / OFFER / SAMPLES is a healthy run.
Everything else (single stages, refit, backfill, measurement):
`.claude/skills/sofa-pipeline/references/commands.md`.

```bash
.venv/bin/python scripts/sofa/ensure_bridge.py                                   # always first
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d>        # the day
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <d> [--dry-run] [--skip-audits]   # THE rebuild, never stage scripts by hand
PYTHONPATH=src:. .venv/bin/python scripts/sofa/day_status.py --date <d>         # status, no network; 0 / 1 WARN / 2 broken
PYTHONPATH=src:. .venv/bin/python scripts/sofa/read_set.py --date <d> --unread  # legs still needing a read
PYTHONPATH=src:. .venv/bin/python scripts/sofa/merge_reads.py --date <d> --report <md>   # merge an analyst / verifier report
PYTHONPATH=src:. .venv/bin/python scripts/sofa/refresh_line_evidence.py --before <D>   # every morning after D-1 is recorded, before D's CONFIDENCE (sofa-day 1a)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --from <D-8> --to <D-1>   # ledger + results on the coupon
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <d> --to <d>   # the ledger by epoch group
```

The loops (`shadow_daily.py`, `cs2_daily.py`) run `ensure_bridge.py` before
every SPORT_IDENTITY (`cs2_daily.identity_steps`; 10-20 lost 10 h of
identities to a dead bridge) and start `capture_closing.py` for their date; `day_status.py` WARNs `loop:capture_closing` when it is missing. A
loop step past `cs2_daily.STEP_TIMEOUT_S` (6 h) is killed with its process
group (`STEP_FAILED TIMEOUT`). `day_status.py` also WARNs on sport identity
(any BRIDGE_ABORTED, or below hockey 85% / basketball 75% / CS2 45% /
volleyball 25% with >= 10 events).

**Gates before a commit**
```bash
.venv/bin/python -m pytest tests/sofa -q
.venv/bin/python -m ruff check src/bet/sofa scripts/sofa
.venv/bin/python -m mypy --strict --no-incremental src/bet/sofa scripts/sofa   # a stale mypy cache gives false errors
PYTHONPATH=src:. .venv/bin/python scripts/sofa/check_test_registry.py
```

## Hard rules

- **The PDF rendered from `11_coupon.json` is the coupon.** Reporting
  `06_coupon.json`, `p_bar` or `08_confidence.json` as the coupon inverts the day.
- **Never invent** a number, a fixture, a price or an availability.
- **Never print a combined / Bet Builder / parlay price**, and never present
  `odds_if_product` as one - Superbet does not price a slip as the product of
  its legs (measured markup 8.8-19.6%).
- **No stake sizing, no automated placement.** The stake is the operator's.
- **A slip assembled in chat is not a coupon and has no gates - so say no
  first.** When the operator asks for N slips, a target price or disjoint
  slips and the day supports fewer, say so in the first line ("dzień cienki -
  masz jeden kupon" / "dziś żadnego") instead of filling the request with
  weaker legs. "Supports" = legs standing on their own statistics and the
  analysts' reads: each leg's measured chance is its confidence (which carries
  its line evidence), never above its price: min(confidence, 1/odds), a leg of
  any sport (`price_gap` or not); a leg a read refuses is out. No market family is preferred or counted - the
  families' record "on the plus" was removed by the operator 2026-10-31 ("the
  pipeline exists to analyse deeply and stand on statistics"). Every table the
  operator may stake from carries that measured chance with 1/odds beside it -
  in **every** re-summary - and no "na minusie" label (operator 2026-10-15: a
  leg below its price is by design). The product of confidences is never the
  headline.
- **A leg proposed in chat is named in Superbet's words** - its
  `superbet_market: superbet_selection` from `11_coupon.json`
  (`bet.sofa.superbet_names.names` for a leg of another artifact), never a
  paraphrase like "Seattle +1.5 w 3. tercji" ("+1.5" beside "Poniżej 1.5" is a
  misclick).
- **Never read, echo or log `.env` values.**
- **Curves are fitted on the history of events and statistics** (operator:
  "nasze źródło to historia statystyk"), replayed as of each match with the
  estimator the sheet uses today. Our settled days are an audit of a curve,
  never its source; line evidence only lowers, and any number it holds is
  reported as measured on N days.
- **Never re-fit or install constants or calibrations without the operator's
  go**, and never into a day already built (except the 2026-10-13 audit's
  standing go, "Changing the pipeline" 4): a refit runs on a copy of the DB,
  installs only after `tests/sofa` pass.
- **A pooled number must say what it pooled across.** Friendlies are out of
  samples and ratings (`bet.sofa.comparability` is the one "does this past
  match count" rule). "History is thin" is not an argument before
  `backfill_listings.py` has run.
- **Never strip `UNFITTED_CONSTANTS`** from a row or a report.
- **Sofascore and Superbet only** - no other data provider in the pipeline.
  Superbet `190` (virtual football), `75` (e-football), `157` (e-hockey) and
  `70` (e-basketball) are simulations - never add them.
- A settled result is a fact about the day, **not about the decision that made
  it**. "It won" never enters the reasoning for the next one.

## The bridge (Sofascore through a real browser)

- **`MIN_INTERVAL_MS = 350` in the userscript is the safety mechanism and is
  never lowered.** It paces each connection; capacity comes from more tabs,
  never a faster tab.
- **Open the windows with `launch_bridge_browser.py`;** they may be minimised.
  Its launch flags stop Chrome clamping a hidden page's timers to >= 1000 ms
  (~1 req/s a tab). They are process-creation flags: Chrome must be fully quit
  first; the script refuses otherwise.
- **`SOFA_MAX_CONCURRENCY` is the window count - never below it.** Measured
  2026-09-22, five windows:

  | `SOFA_MAX_CONCURRENCY` | achieved | p50 | p90 |
  |---|---|---|---|
  | 3 | 0.15 req/s | 20,138 ms | 20,162 ms |
  | **5** | **11.67 req/s** | **354 ms** | **620 ms** |
  | 8 | 11.72 req/s | 668 ms | 704 ms |
  | 12 | 11.66 req/s | 1,010 ms | 1,056 ms |

  Above the window count only latency grows (queue depth -> `STALE_PRICE`);
  below it the bridge collapses. Change it together with `--windows` and
  re-run `measure_bridge_capacity.py`.
- **`SOFA_TARGET_RPS` sits above what the tabs serve** (5 x 2.86 = 14.3 req/s,
  so 20). A starved bucket idles the tabs.
- **Measure the round trip, not the wall clock around the client** - the token
  bucket is inside the client; use `p50 net` from `measure_bridge_capacity.py`.
- **Refusals happen** (403 bursts during long runs at full width). Backfills
  run short and resume; a refusal means slow down - never refresh tokens
  pre-emptively to outrun it.
- **Superbet has a breaker too:** 3 failures (403 / 429 / 5xx / timeout; a 404
  is an answer) open it (`SOFA_BREAKER_*`). OFFER keeps the unasked fixtures'
  old entries (CONFIDENCE refuses them STALE_PRICE); an all-refused SHADOW /
  CS2 snapshot is FAILED.
- `SOFA_NOW` freezes `timeutil.now()` for as-of replays only; `run_pipeline.py`
  refuses it.

## Session economy

Main sessions are the largest cost (context x turns). Keep them small:

- **Delegate** multi-file reading, measurement and verification to a subagent;
  only its conclusion comes back. Do not re-read what it read.
- **Never `cat` a big JSON or log.** Filter with `jq` or a Python one-liner,
  `head` / `tail` logs, write big outputs to a file and `grep` it; read only the
  rows of the legs in question.
- **One task per session.** Start a fresh session for the next task rather than
  carrying a long context into it.
- `.claude/settings.json` caps auto-compaction at 400k tokens
  (`autoCompactWindow`).
- **Agents do not load this file.** A rule an agent must obey goes into the
  `sofa-pipeline` skill (or the agent's own file) too.

## Working style

- **Evidence or it did not happen.** A claim about the pipeline names the file
  and line, or the artifact and field. An unmeasured statement is marked as a
  suspicion.
- **A skipped check is named.** If a run went clean, a guard was *not tested* -
  never "it works".
- **Check a subagent's numbers** when you can check them locally.
- Live runs are deliberate: hours of bridge time, visible to a third party's
  production API.

## Language and repository

Operator-facing documentation in `docs/sofa/` is **Polish** (so are the
analysts' reports). Code, tests, this file and the `.claude/` contracts are
**English**. `data/sofa.db` is the only working database. The slip calculator
is `scripts/sofa/audit_slip.py` (`bet.sofa.slip_audit`); the operator's builder
method is `docs/sofa/SUPERBET_BET_BUILDER_METHOD_v3.md`.
