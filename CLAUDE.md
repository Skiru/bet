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
| `KUPON_<d>.html` | the same legs as a filterable page - a **view**, not a coupon (`bet.sofa.coupon_html`); every read leg carries its analysts' notes (verdict, author, reason; the PDF: verdict + first 140 chars, `read_label`), a match with no read leg is marked "nieczytany" - display only; written by `build_coupon_pdf.py` after every PDF (HTML failure: PDF kept, exit 1); alone `build_coupon_html.py --date <d>` |
| `family_record.json` | each (sport, market, direction) family's record on the printed legs of the 14 days before; "on the plus" = >= 50 legs and units > 0 (`bet.sofa.family_record`); the HTML's selection aid, **never a gate** - advantage not yet shown (`T-FAMILY-SELECTION`) |
| `13_results.json` | settled result of every printed position, the ledger's own grades (`bet.sofa.coupon_results`); written by `mark_coupon_results.py` (called by `record_results.py`) |
| `reads.json`, `vetoes.json`, `read_requests.json` | analysts' per-leg verdicts, vetoes, the operator's extra positions |
| `read_set/read_set_<sport>[_<i>].json` | C3's read set as compact legs (`read_set.py`) |
| `dossier/<sport>_<event id>.json` | the analysts' match fact sheet (`bet.sofa.dossier`, offline, written by `read_set.py` / `build_slip.py`, path on each leg's `dossier`): form with periods, rest, rebuilt table, h2h (cached meetings + `h2h.json`, each with the legs' metrics; `head_to_head_source` says what was asked and how far the cache reaches), venue city / local hour, referee / ranking / CS2 roster and map pool, Superbet line moves, the web checklist - **display only**, never a gate |
| `h2h.json` | every read match's head-to-head asked of Sofascore (`/event/{customId}/h2h/events`, `bet.sofa.h2h`) by `read_set.py` / `build_slip.py` before the dossiers (`--no-h2h` skips; operator 2026-10-21: always), the meetings' statistics into the cache; an OK answer is not re-asked that day; a failure leaves the dossier `NOT_ASKED` / `FAILED` and an h2h line on its web checklist - display only, SAMPLES never reads it |
| `late_resolve.json` | the late RESOLVE passes (`epochs.LATE_RESOLVE_FROM_UTC`, `bet.sofa.late_resolve`): board entries the morning could not bridge re-asked while open; only new fixtures added, every old row kept |
| `fixture_status.json`, `sport_fixtures.json` | FIXTURE_CHECK's fresh starts / statuses; pinned Sofascore ids of sport games |
| `unmapped_prices/<ts>.jsonl.gz` | prices of markets OFFER does not read - a record, read by nothing |
| `06_coupon.json` | the priced VALUE selector - **not the coupon** |

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
  staged `.next.json` is read from its `effective_from`,
  `sport_confidence.calibration_path_for` - from 2026-10-14 every sport reads
  the `.next.json`, so an edit goes there, not into the installed file).
- SHEET keeps the price out of `p_central`; the rating is published beside it
  as `forecast_p` ("model", uncalibrated, never a gate). CONFIDENCE maps the
  statistics to a calibrated confidence through the curves.
- **Line evidence** (`bet.sofa.line_evidence`,
  `config/sofa_superbet_line_evidence.json`, refitted every morning by
  `refresh_line_evidence.py`, which never touches a curve): every key is also
  read through its own settled Superbet lines. Confidence = the lowest of
  - the curve lowered by the key's **offset** (realised minus confidence on
    printable lines; needs `MIN_OFFSET_ROWS` 50 lines and `MIN_OFFSET_GAMES` 30
    games, else the sport's pooled offset with `MIN_SPORT_OFFSET_GAMES` 20;
    never above 0; the pooled offset excludes a key holding more than
    `CONCENTRATION_MAX` 50% of the lines - which can raise another CS2 key), and
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
- **Sample integrity** (`IDENTITY_GATE_PER_FAMILY`, from 10-21 10:50Z): a
  past match whose payload contradicts itself loses only the metrics that read
  the contradiction (`metrics.identity_gap_for_metric`: shots identity -> shot
  metrics; goal incidents vs score -> card points / reds / penalties; home
  period sum -> goals and the incident metrics on the 90-minute score);
  tennis `gamesWon` nonsense still drops the whole match. Before it one bad
  shot count dropped the match from every sample (Roma 3-4 Real, 10-14).
- What each estimator does today (ratings, dispersion, stretches, cup strength,
  opponent correction, new markets...) and when it switched on: model-state.md.

### What prints

- **A leg prints** when confidence >= 0.70, confidence x odds >= 0.90, ladder
  (group) margin <= 15% (`COUPON_PROFILE`), not ODDS_TOO_LOW, not started,
  fresh price (STALE_PRICE otherwise; a moved price re-prices the leg). Every
  passing single prints - no page limit.
- **Refusals worth knowing** (each named on the row):
  - `CROSS_LEAGUE_UNLINKED`: a football pair is LINKED only when both sides'
    leagues are the competition they share (the hockey / basketball /
    volleyball score model reads the same book; rows carry `link_rule`);
  - `NO_CLASS_CURVE`: women's football, women's tennis and tennis team cups
    read only their class's curves;
  - `NOT_SETTLEABLE`: (competition, family) cells in `config/sofa_settleability.json`;
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
  (`match_rule: "surname"`); SETTLE grades the `matched_name` from his own squad
  (a candidate in the other squad is PLAYER_AMBIGUOUS).
- **Start clock** = earliest of RESOLVE's clock, Superbet's start signal
  (`superbet_started_utc`, `superbet_kickoff_seen_utc`; in-play odds dropped for
  every reader) and FIXTURE_CHECK's fresh `/event` start. A postponed /
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
- **Superbet's words** (`bet.sofa.superbet_names`, display only): every leg
  carries `superbet_market` / `superbet_selection` as the screen writes them
  ("3. tercja - Seattle Kraken - liczba goli" / "poniżej 1.5"); a market it does
  not know keeps its old label, nothing guessed. The PDF / HTML name legs this way.
- **Reads:** analysts read every unlocked leg of the first 30 matches by value
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

### Measured sports (hockey, basketball, volleyball, CS2)

SHADOW / CS2 snapshot Superbet -> SPORT_IDENTITY pins the Sofascore id before
the start (an event not identified by its start keeps its last pre-start
record, `frozen_at_start`) -> SPORT_CONFIDENCE reads the sport calibration
(fitted without prices) and corrects it with line evidence. SHADOW / CS2 are a
measurement of Superbet's price and feed nothing else.

- **Identity**: the entity map (`bet.sofa.entity_map`) learns verified names
  from SPORT_IDENTITY; opponent-only matches are candidates, conflicts are
  queued and never overwritten (`SofaCache.save_entity` in `src/bet/sofa/cache.py`
  follows the same rule). Manual decisions: `config/sofa_entity_aliases.json`
  (fuzzy matching never writes it); the queue `report_entity_queue.py`. Day
  anchor, tournament day and proven absence (`NOT_ON_SOFASCORE`) identify the
  rest; details in model-state.md.
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
- Hockey / basketball player lines: p = player_model's pre-game number in
  SHADOW's `player_model.jsonl`; no history curve, so `NO_LINE_EVIDENCE` until a
  family's p bucket holds 50 settled pre-game lines; graded from SHADOW_SETTLE's
  own player row (football's token / surname rules, then tokens without Jr /
  Sr / II; a nickname is never guessed).
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
today the 10-16b flags plus `--goals-stretch --count-stretch --player-stretch`)
and never `--tennis-serve-markets` / `--tennis-aces-opponent` (model-state.md).
Every SHEET row carries `config_sha` (`bet.sofa.sheet_config`, the fitted
files SHEET reads); a sheet priced on other constants gets a `CONFIG_CHANGED`
note but is **not** re-run - an install is undated and never goes into a built
day without a go; with one, `run_pipeline.py --only SHEET` by hand. Curves need
nothing (CONFIDENCE reads them on every rebuild). `rebuild_plan.py` re-runs SHEET
itself when a switch is on for the day and the build clock and a row of its
sport lacks the switch's marker (a sheet without that sport never re-runs).

Daily loops spawn each step through `run_pipeline.py` (fresh code per step);
only the loop's own orchestration is old code until it ends - a loop started
before a code change runs its old steps until it ends.

## Entry points

| you want | use |
|---|---|
| a full betting day - D-1 settled and recorded, the coupon + PDF, reads, verification | `/sofa-day [dzisiaj\|wczoraj\|YYYY-MM-DD]` |
| the analysts' read of an existing coupon ("dodatkowo: <pozycje>" adds to `read_requests.json`) | `/sofa-analyze` |
| coupon + PDF from artifacts on disk (`rebuild_day.py`) | `/sofa-rebuild` |
| adversarial verification of a built day | `/sofa-verify` |
| settle D-1 and decide about constants | `/sofa-settle` |
| price a slip the operator screenshotted | the `bet-slip-audit` skill |
| a chat slip (AKO) to a target price from the day's coupon (every market, a time window; each leg read, a refused leg replaced and read) | `/kupon 11-13 [~4] [x2]` (`build_slip.py` + analysts through the `bet-slip-audit` skill's loop) |

Agents: `sofa-runner`, `sofa-analyst-football`, `sofa-analyst-tennis`,
`sofa-analyst-sport` (one instance per measured sport), `sofa-verifier`,
`sofa-settler`, `sofa-market-scout`. Preloaded skills: `sofa-pipeline`,
`sofa-analysis-core`, `football-analysis`, `tennis-analysis`. An analyst writes
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
  weaker legs. "Supports" is measured: first scan the whole window for legs of
  the market families whose printed legs realised at or above their price on
  the latest settled days (name the days and N; match bootstrap; one family in
  twenty clearing zero is what chance gives - say so), and inside a match
  prefer such a leg. Every table the operator may stake from carries that
  measured chance (a `price_gap` leg at its price, never its confidence) with
  1/odds beside it - in **every** re-summary - and no "na minusie" label
  (operator 2026-10-15: a leg below its price is by design). The product of
  confidences is never the headline.
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
