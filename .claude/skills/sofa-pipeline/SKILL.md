---
name: sofa-pipeline
description: The shared contract for the `sofa` betting pipeline (Sofascore stats + Superbet prices) - the seven-stage DEFAULT_SEQUENCE (BOARD..COUPON) and the stages outside it (CONFIDENCE, FIXTURE_CHECK, SPORT_IDENTITY, SPORT_CONFIDENCE, COUPON_ASSEMBLY, PDF, SETTLE, FIT, CS2 / SHADOW), every artifact and field, the arithmetic (confidence from the statistics alone since 2026-10-05; the price only as the betting condition and, since 2026-10-07 10:55Z, only able to lower a confidence; line evidence; the 2026-10-07 epochs and the refit), which file is the coupon (11_coupon.json -> KUPON_<d>.pdf) and which only looks like one, and the traps that have cost money. Preloaded into every sofa agent. Use whenever running, auditing, analysing or repairing a sofa day, or when a stage name like DISCOVER or ENRICH is about to be used - those belong to the retired `simple` pipeline and there is no mapping between the two.
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
| ranking number | `p_low` | `confidence` (the measured lower bound of the history curve, lowered by line evidence); `p_bar` only in the old priced selector |
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

deliberately separate:  SETTLE (D-1) → FIT (on a DB copy, operator's go)
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
| E11 | **FIT** | re-fit constants and curves (since 2026-10-07 the curves from the replayed history; `prepare_refit.py`) | offline | `config/sofa_*.json` |
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
is the calibration curve's lower bound of that number, then lowered by line
evidence (section "The 2026-10-07 rules"). The rating is printed beside it as
`forecast_p` ("model", `forecast_source` `football_rating` / `tennis_rating` /
`score_model` / `cs2_engine` / null) - uncalibrated, never a gate, never a
sort key. `model_p` (= `p_central`) is unchanged. (Since 14:05Z on 2026-10-07
some tennis families are priced BY the rating's neighbours, so there
`p_central` is the rating's own number - still no price in it.)

The price is **only the betting condition**: x = confidence × odds >= 0.90,
ladder margin <= 15%, odds >= 1/0.9202 (`ODDS_TOO_LOW`), not started
(`KICKED_OFF`, earliest clock), fresh price (`STALE_PRICE`); and, from
10:55Z on 2026-10-07, the price band may LOWER a confidence (price-band cap),
never raise one. `MAX_DISAGREEMENT` and `UNREACHABLE_BAR` are off; a moved
price re-prices the leg (x at the fresh odds) instead of
`PRICE_MOVED_SINCE_SHEET`. Floor 0.70; a WATCH or NO_BET read removes the leg.
Bet Builders are chosen and ordered by `combined_probability`, stakeable at
combined p × odds after haircut >= 0.90 (`stakeable_rule: "x>=0.90"`; the
haircut is internal and no builder price is ever printed). The coupon is
ordered by confidence, then the earlier start, legs of one match together
(`confidence.coupon_order`) - no price and no EV in the key. CONFIDENCE
refuses (exit 2) a SHEET not built under the epoch (`epochs.sheet_epoch`), so
a rule rebuild starts at SHEET (see trap "a rebuild does not re-run SHEET").

**K13 / K13b:** where a market x direction bucket is too thin for its own
curve (`thin_by_market_direction`), it caps the two-direction `by_market`
curve and the pools too - the lower of the two Wilson lower bounds; where a
market's own curve has a hole at p, a pool read is capped by the market's
nearest own bucket below (`cap_pool_by_neighbour`, `epochs.POOL_NEIGHBOUR_CAP`).

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

## The 2026-10-07 rules (the single statement - the references point here)

This section is the one place that states the rules in force after the stats-only
epoch. Where `references/*.md` describe an older behaviour (a by-name refusal,
a price in `p_central`, a stale constant) they are history, marked as such, and
this section wins. Several of the switches below start in the middle of 2026-10-07
(a mixed day): a print before the moment is the old rule, a rebuild after it the
new one, and a leg locked before stays as printed.

**Operator's yardstick:** the statistics must tell a good 1.20 from a bad 1.20,
every sport alike; nothing that could win is cut by name; a market that does not
discriminate stays and is measured. Honest confidence is still required: a
curve that overstates is corrected, not removed.

### The switches (`src/bet/sofa/epochs.py`)

A switch acts on a build when the DAY built is >= its `*_DATE` AND the build
clock (`timeutil.now()`, `SOFA_NOW` in a replay) is >= its `*_FROM_UTC`, so a
rebuild of an earlier day keeps the rule it printed under. Exceptions that read
the wall clock: `link_shared_league` (when the caller gives no clock) and
`model_fixes_enabled`.

| switch (`*_FROM_UTC`) | from (UTC) | what it changes |
|---|---|---|
| `STATS_ONLY` | 2026-10-05 07:15 | price out of `p_central`; confidence from the statistics; reads at the end of the chain |
| `SPORTS_ON_COUPON` | 2026-10-05 08:30 | hockey / basketball / volleyball / CS2 print on the one coupon |
| `COUPON_STRUCTURE` | 2026-10-06 00:00 | the coupon-form dials (`ladder_form`, `max_positions_per_match`) may act; both OFF unless `config/sofa_coupon_form.json` sets them |
| `SETTLEABILITY` | 2026-10-06 00:00 | `NOT_SETTLEABLE` cells of `config/sofa_settleability.json` refuse |
| `AMPERSAND_SUBJECTS` | 2026-10-06 00:00 | a club with "&" in its name is a subject of its own markets |
| `POOL_NEIGHBOUR_CAP` | 2026-10-06 00:00 | K13b: a pool read of a hole is capped by the market's nearest own bucket below |
| `NATIONAL_SAMPLE_AGE` | 2026-10-06 00:00 | national-team samples judged by count, not age (`SAMPLE_CROSSES_SEASON` skipped) |
| `LINK_SHARED_LEAGUE` | 2026-10-07 06:45 | a football / score-model pair is LINKED only through a league both domains share (sheet rows carry `link_rule`) |
| `LINE_EVIDENCE` | 2026-10-07 10:55 | no refusal by name; every key read through its own settled Superbet lines |
| `LINE_EVIDENCE_V2` | 2026-10-07 13:42 | second rules of line evidence (below) |
| `TENNIS_RATING_PRICES` | 2026-10-07 14:05 | tennis `games_won_for` / `handicap_games` / `most_games` (not its draw) priced by the rating's neighbours alone; `games_total` = 0.5 x rating + 0.5 x NB (`tennis_rating.W_GAMES_TOTAL_RATING`); best-of-five not rated (`run_sheet.tennis_forecast`) |
| `DERIVED_MARGINAL_CENTRES` | 2026-10-07 14:05 | football goals / corners / shots-on-target / cards joints (`both_over_`, `most_`, `handicap_`) built from the marginal rows' centres (`DERIVED_MARGINAL_CENTRES_METRICS`) |
| `BB_FRESHNESS` | 2026-10-07 14:05 | basketball simulation noise x1.085 when the thinner side has <= 2 games in the last 120 days, x1.026 for 3..9 (`SimParams.bb_fresh_mult`) - live forecaster and history replay |
| OFF (`None`) | - | `CURVE_STATUS` (a failing curve stops printing), `MODEL_FIXES` (tennis NB dispersion), `BUILDER_SCREEN_PRICE` (switched off 2026-10-05: sofa never prices a builder), `DERIVED_CURVES` (derived joints read a history curve; date 2026-10-09) |

A refit install is also a comparability epoch but NOT an `epochs` switch: it is
the content of `config/` (see "Between days"). The refit installed
2026-10-07 17:51Z (`data/refit_2026-10-08/install_manifest.json`) fitted the
football / tennis curves on the HISTORY replayed with the estimator SHEET
prices with (operator, 2026-10-07: our own settled days are an audit of a
curve, never its source). It did not replay football goals joints (no football
rating in the replayed centre; `--derived` off), so derived joints have no
curve and read their own Superbet lines only. Hockey / volleyball / CS2 curves
are the morning's staged `.next.json`; its basketball section was refitted
with `--bb-freshness on`.

### Confidence from 2026-10-07 10:55Z (`bet.sofa.line_evidence`)

`config/sofa_superbet_line_evidence.json`, refitted every morning
(`refresh_line_evidence.py`; `fitted_from.before` must read the day built). The
confidence of a leg is the LOWEST of:

1. the key's history curve at p, lowered by the key's **offset** - its measured
   realised-minus-confidence on printable settled lines (confidence >= 0.70),
   needing `MIN_OFFSET_ROWS` 50 lines and `MIN_OFFSET_GAMES` 30 games; fewer,
   the sport's pooled offset (`MIN_SPORT_OFFSET_GAMES` 20); never above 0;
2. with no curve at p (a derived joint, a hole, a market never fitted), the
   **stand-in**: the Wilson lower bound of the key's own settled lines in p's
   bucket (`MIN_EVIDENCE_BUCKET` 50 lines), else **`NO_LINE_EVIDENCE`** (not
   measured yet - not a defect, never guessed);
3. the **price-band cap**: what lines of the key at this p realised in this band
   of Superbet's price (`PRICE_BANDS` 1.30 / 1.60 / 2.20; `MIN_CAP_CELL` 20
   lines), applied only where the cell's Wilson UPPER bound is under the
   confidence, and then to the cell's realised rate. A thin cell widens (key's
   lines in the band from p up; the sport's; with none, the key's lines over
   every band from p down to 0.70).

The price only chooses the band and only ever lowers; inside a band the
statistics rank the legs. The only way another key can come out HIGHER is the
CS2 pooled offset measured without its dominant key (operator's choice).
Legs carry `line_offset` / `price_band_cap` when lowered, `calibrated_on` names
the source (`...-0.0570sb`, `|cap:<cell>`, `sb:<sport>:<key>`) and
`unfitted_constants` includes the line-evidence constants (`line_evidence.UNFITTED_CONSTANTS`).

**Second rules (`LINE_EVIDENCE_V2`, `LineEvidence.v2`)**: a band cell widens
downward INSIDE its band first; a key with no curve needs `MIN_EVIDENCE_GAMES`
15 games in the bucket and reads the Wilson bound of lines divided by the
sport's `design_effect` (computed from EVERY line with p >= 0.70 of the sport,
not only the curve keys' printable ones); a sport's pooled offset leaves out a key
holding more than `CONCENTRATION_MAX` 50% of the printable lines
(`sport_printable.<s>.without`; that key keeps the full pool); a CS2 fixture
with no `best_of` gives no model p (`NO_MODEL_P`). An evidence file without
`games` reads nothing for a key without a curve until the morning refresh.
Audit: `docs/sofa/history/AUDYT_MODELI_2026-10-07.md`; evidence for the
rule: `docs/sofa/evidence/discrimination_within_price_2026-10-07.md`.

### What is still refused (and what no longer is)

No refusal BY NAME exists from `LINE_EVIDENCE` on: `refused_markets`,
`admitted_player_markets`, `admitted_tennis_set_markets`,
`DERIVED_NOT_CALIBRATABLE`, `PLAYER_PROP_NOT_ADMITTED`,
`TENNIS_SET_MARKET_NOT_ADMITTED`, `OPERATOR_REFUSED` and a sport key outside
`admitted` refuse nothing (the lists stay in the calibration files and are
carried by refits; they apply only to a rebuild of a day before the epoch).
`goals_1h_total|UNDER`, shots / fouls UNDER, tennis per-set markets, basketball
and CS2 print again; a printed leg of a formerly refused market is **not** a
defect. What remains, each named on the row: `CROSS_LEAGUE_UNLINKED`,
`NO_CLASS_CURVE` (women's football / tennis, tennis team cups read only their
class's curves), `NOT_SETTLEABLE`, K13 / K13b (caps, not refusals),
`SAMPLE_CROSSES_SEASON` (180 days, national teams excepted),
`STALE_SAMPLE` (60 days), `LINE_OUTSIDE_FIT` (CS2 `map_team_rounds` outside
9.5-12.5), `NO_LINE_EVIDENCE`, `NOT_CALIBRATED` (no usable curve at all),
`FIXTURE_NOT_AS_SCHEDULED`, `FRIENDLY_FIXTURE`, the price conditions, and a
sport's own `NOT_IDENTIFIED` / `TOURNAMENT_NEVER_SETTLED` (volleyball needs a
tournament with a settled event in the last 14 days) / `NO_MODEL_P` /
`INCOMPLETE_GROUP`. `CURVE_FAILED_CALIBRATION` is wired but off.

### Measured sports

Every fitted key of the four is read, corrected by its Superbet lines;
`sport_confidence.EXTENDED_MARKETS` (basketball quarters, second half, dnb,
odd/even; hockey period dnb), volleyball exact set score / parity / extra
points, `CS2_EXTENDED_FAMILIES` and the series families
(`cs2_engine.SERIES_KAPPA`); hockey / basketball player lines take p from
SHADOW's pre-game `player_model.jsonl` (no history curve: `NO_LINE_EVIDENCE`
until a p bucket holds 50 settled lines). A day reads
`sport_confidence.calibration_path_for(date)`: the staged
`sofa_sport_confidence_calibration.next.json` from its `effective_from`
(2026-10-07), else the main file. **Basketball second half and Q4 grade on the
REGULATION periods; overtime does not count** (operator, 2026-10-07;
`shadow._pair`); the full-game basketball markets include overtime.
`OT_RULE_UNKNOWN` no longer exists in the code. Still unpriced: CS2 series
rounds and round parity.

### Settle rules (operator, 2026-10-07)

`settle.REFUND_REASONS` = `MOVED_BEYOND_VOID` (start moved > 48 h from the
earliest clock held), `AWARDED`, `RETIRED` (Sofascore code 92) and `WALKOVER`:
a refund (0 u.), never a loss, never a `sofa_settled_row`; listed in
`07_settle_skips.json`. The measured sports' SHADOW_SETTLE reads awarded /
walkover / retired / forfeit descriptions as `AWARDED` (`shadow.is_no_result`:
never graded, never retried) and `VOID` after 48 h.

### Between days

```bash
# every morning, after D-1 is settled and recorded (SETTLE, SHADOW_SETTLE, CS2_SETTLE, record_results) and before D's build; ~15-20 min, no bridge
PYTHONPATH=src:. .venv/bin/python scripts/sofa/refresh_line_evidence.py --before <D> [--dry-run] [--skip-sport-rows]
# exit 0 written; 1 a sport's row fit failed and that sport reuses the earlier rows (name it); 2 a crash (the file is unchanged);
# four sport row fits with fit_sport_confidence.py --dry-run --rows-out data/line_evidence/rows_before_<D>, then fit_line_evidence.py; it never touches a curve
```

A **curve refit** follows a change of the estimator or a materially grown
history - never a bad day. It runs on a COPY of the database while the daily
loops stay up (they spawn each step through `run_pipeline.py`, so a new step
runs fresh code; only a loop's own orchestration is old until it ends):

```bash
mkdir -p data/refit_<d> && sqlite3 data/sofa.db "VACUUM INTO 'data/refit_<d>/sofa_replay.db'"   # the copy (needs the free space; the target must not exist); <d> = the day the new curves first serve
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date <d> backup                       # config/ -> config/backup_<d>/ with sha256
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date <d> --db-path data/refit_<d>/sofa_replay.db rebuild-cache-rows --dry-run
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date <d> --db-path data/refit_<d>/sofa_replay.db rebuild-cache-rows --confirm --without-db-backup [--derived goals,...] [--no-tennis-rating]   # LONG
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date <d> --db-path data/refit_<d>/sofa_replay.db fit
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date <d> --db-path data/refit_<d>/sofa_replay.db compare --days <d1> <d2>
# read data/refit_<d>/compare_report.md; install only on the operator's go:
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date <d> install --confirm        # runs tests/sofa, restores the backup on failure
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_sport_confidence.py --sport <s> --before <d> [--bb-freshness on] ...   # a sport's section, staged in .next.json
PYTHONPATH=src:. .venv/bin/python scripts/sofa/refresh_line_evidence.py --before <d>               # after EVERY curve refit
```

`rebuild-cache-rows` replays the tennis rating (`tennis_rating.AsOfRating`;
best-of-five skipped via `metrics.infer_best_of`) unless `--no-tennis-rating`,
and football joints only with `--derived`. Read `prepare_refit.py --help` and
`docs/sofa/CONFIG.md` section 7 before composing a command: the global
options (`--date`, `--db-path`) come BEFORE the subcommand.

### Open operator questions (never decide them)

Band-cap strictness; Superbet's game count of a match tiebreak (tennis).

### Not modelled yet

Football / tennis outcome markets (1X2, double chance, dnb, BTTS, goals
parity, HT/FT, exact score; tennis match / set winner, set score, games
parity - OFFER's `unmapped_markets`), CS2 series rounds and round parity;
derived football / tennis joints and women's tennis per-set markets above
their measured range wait for 50 settled lines a bucket.

## The arithmetic — the chain every row must be able to reproduce

```
prior   = league baseline, else global baseline          (config/sofa_league_baselines.json)
w_c     = n / (n + K_CENTRE)                             football 15, tennis 5 (fitted 2026-10-03; unchanged by the 2026-10-07 refit)
centre  = w_c·sample_mean + (1 − w_c)·prior              (or sample_mean when no baseline)
centre  = 0.5·rating + 0.5·centre                        football rows with a FOOTBALL_RATING note (W_FOOTBALL_RATING, not the price)

p_central (stats-only epoch):
    football counts             -> negative binomial around `centre`
    football derived joints     -> from the marginal rows' centres (DERIVED_MARGINAL_CENTRES, from 10-07 14:05Z)
    tennis games_won_for / handicap_games / most_games -> the rating's neighbours alone (TENNIS_RATING_PRICES, 10-07 14:05Z; best-of-five not rated)
    tennis games_total          -> 0.5·rating + 0.5·NB (same switch)
    tennis other rated / empirical -> the sample's own estimator, no price (the rating goes to forecast_p)
    basketball                  -> score model, simulation noise x1.085 / x1.026 for a thin side (BB_FRESHNESS)
    everything else             -> normal with a support floor at −0.5

confidence (football / tennis) = min( curve.realised_lo95(market, p_central, sport, direction, klass) [K13 / K13b caps] + offset(key),
                                      price-band cap(key, p, Superbet's odds) )          offset <= 0; a key with no curve: Wilson bound of its own settled lines / design effect, else NO_LINE_EVIDENCE
x          = confidence × offered_odds   >= 0.90 to print; margin <= 15%
builder    stakeable when combined_probability × odds_after_haircut >= 0.90
sport leg  confidence = the same chain from the calibrated bucket of the model p
           (sport_confidence.calibration_path_for(date): main or staged .next.json) and the sport's line evidence

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
  07_settle_skips.json                   why a row was not graded; refunds (MOVED_BEYOND_VOID, AWARDED, RETIRED, WALKOVER)
  09_screen_prices.json                  the operator's Superbet screen prices of builders - shown back as his note, never a sofa price
  10_boosts.json/.md                     run_boosts.py: Superbet price boosts - not the coupon
  printed/<ts>.json                      every PDF render, append-only; a rebuild locks from the first print
  closing.jsonl                          capture_closing.py: closing price of every printed leg

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
of `11_coupon.json` (`READ_REQUIRED_SINGLES`; a rebuild moves positions, so
re-read until C3 is clean), every printed builder leg, and
whatever `read_requests.json` asks for (`{"position": n}` or `{"group_key":
"sofa:<id>", "market"?, "line"?, "direction"?}`, each with `requested_by` and
`at_utc`; prefer `group_key` — positions shift after a rebuild).
`audit_variants` C3 requires an analyst read on that set. The PDF's
`STALE_CONFIDENCE` guard looks at `reads.json` (and `05_sheet.json`,
`vetoes.json`, the football / tennis calibration file), `STALE_COUPON` at
`read_requests.json` (and `08_confidence*.json`, `09_screen_prices.json`,
`config/sofa_coupon_form.json`): after a reads change re-run CONFIDENCE, then
COUPON_ASSEMBLY, then the PDF - or just `rebuild_day.py`.

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
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_fixture_check.py --date <d> [--max-candidates N]   # in a rebuild, after OFFER, before CONFIDENCE (bridge)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <d> [--dry-run] [--skip-audits]   # THE rebuild: stale OFFER / SHADOW (horizon) / CS2 first, SHEET only if its epoch or link rule is stale (NOT after a model-package or refit change - trap), then FIXTURE_CHECK .. PDF + audits; never the stages by hand
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <d>             # no --floor: the official floor is COUPON_PROFILE's 0.70; --calibration <path> reads a scratch file
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only SHADOW
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only CS2
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_identity.py --date <d>       # bridge; after the fresh snapshots
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_confidence.py --date <d>     # no bridge
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon.py --date <d>             # COUPON_ASSEMBLY -> 11_coupon.json
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <d>         # KUPON_<d>.pdf + 12_printed.json
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <d>             # the priced 05/06 arithmetic
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <d>           # C1-C3, U1-U3 on 11
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settle_identity.py --from <d> --to <d> [--sport all]   # after the D-1 settle
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
- Never print a combined / Bet Builder / parlay price, and never present
  `odds_if_product` as one — Superbet does not price a slip as the product of
  its legs (measured markup 8.8–19.6%). sofa does not price a builder: the PDF
  shows its legs, the combined p and "kurs buildera: sprawdź na ekranie
  Superbetu"; a screen price the operator recorded in `09_screen_prices.json`
  is shown back as his note. `odds_after_haircut` is internal (stakeable test).
- No stake sizing, no automated placement.
- Never read, echo or log `.env` values.
- **Sofascore and Superbet only.** No other data provider enters the pipeline,
  its analysts' reads or this skill's arithmetic (bzzoiro included; the
  `bet-slip-audit` skill takes any outside number only as an operator-typed
  input and says so). Superbet `190` (virtual football), `75` (e-football),
  `157` (e-hockey) and `70` (e-basketball) are simulations - never add them.
- Never re-fit or install constants from a day's run (`fit_constants.py`,
  `fit_confidence.py`, `fit_sport_confidence.py` are separate steps; `fit_line_evidence.py`
  runs every morning through `refresh_line_evidence.py`):
  re-fitting breaks comparability with yesterday. A refit runs on a copy of
  the database and installs only on the operator's go.
- Never strip `UNFITTED_CONSTANTS` from a row or a report (line-evidence
  constants are on the leg too).
- Epochs are never pooled: the official coupon before and after 07:15Z on
  2026-10-05 is not one experiment (ledger `official` vs
  `official:pre_stats_only`); the current rules apply from 2026-10-06, and a
  refit install or an `epochs` switch starts another epoch (10-07 is a mixed
  day, locked legs keep the rule they were printed under).
- **Gates before a commit:** `.venv/bin/python -m pytest tests/sofa -q`,
  `.venv/bin/python -m ruff check src/bet/sofa scripts/sofa`,
  `.venv/bin/python -m mypy --strict --no-incremental src/bet/sofa scripts/sofa`
  (a stale mypy cache gives false errors - always `--no-incremental`), and
  `scripts/sofa/check_test_registry.py`. Measured 2026-10-07: ruff and mypy
  clean (172 source files).
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
