# The arithmetic - and what can and cannot be re-derived

Read this when you re-derive a number on a row or a leg. Which model packages
and switches are on for a day (centre corrections, stretches, per-line curves,
dispersion, tennis rating prices, ...) is in `references/model-state.md`;
this file is the arithmetic they plug into.

Two chains produce two different numbers. Do not conflate them.

- **Chain 1 - SHEET -> COUPON** asks *is this worth its price* and ranks by
  `surplus`. `p_bar`, `required_odds`, `surplus`, `edge`, VALUE: still
  computed, still audited by `audit_coupon.py`, **never the coupon's**.
  Measured: the model loses that argument to the price (Brier 0.2067 vs 0.1845).
- **Chain 2 - CONFIDENCE / SPORT_CONFIDENCE -> COUPON_ASSEMBLY -> PDF** asks
  *how often does this happen* and is the coupon's.

## Switch rule (`src/bet/sofa/epochs.py`)

A switch acts on a build when the DAY built is >= its date AND the build
clock (`timeutil.now()`, `SOFA_NOW` in a replay) is >= its `*_FROM_UTC`, so a
rebuild of an earlier day keeps the rule it printed under. `None` = off.
Exceptions that read the wall clock: `link_shared_league` (when the caller
gives no clock) and `model_fixes_enabled`. Every switch, with its date,
is listed in `references/model-state.md`.

## Chain 1 - the sheet (`src/bet/sofa/engine.py`, `scripts/sofa/run_sheet.py`)

```
prior   = league baseline, else global baseline        config/sofa_league_baselines.json
w_c     = n / (n + K_CENTRE)                           K_CENTRE football 15, tennis 8 (config/sofa_engine_constants.json by_sport);
                                                        by_market football: cards_points_for 25, fouls_total 2, shots_for 8, shots_total 5
centre  = w_c * sample_mean + (1 - w_c) * prior         (= sample_mean when no baseline)
centre  = W * rating + (1 - W) * centre                 football rows with a rating (W_FOOTBALL_RATING 0.5, per market from
                                                        config/sofa_rating_weight.json); then the centre switches (model-state.md)

p_central (no price in it on a stats-only row):
    football counts      -> negative binomial around `centre` (dispersion from config/sofa_count_dispersion.json)
    football joints      -> from the marginal rows' centres (both_over_ / most_ / handicap_)
    tennis rated markets -> the rating's neighbours (games_total: W_GAMES_TOTAL_RATING 0.5 rating + 0.5 NB;
                            best-of-five not rated)
    result / score / incident markets -> NB goals grid on the pure rating centres
    other empirical      -> frequency around the shifted centre
    everything else      -> normal, support floored at -0.5

old priced bar (Chain 1 only):
p       = max(0.01, p_central - max(0, calibration_correction))
w       = n / (n + K_PRICE)                            K_PRICE = 10.0, status NOT_FITTED
p_bar   = w * p + (1 - w) * market_p                   market_p = power-devigged Superbet price (proportional devig mis-states tails by ~7 pp)
required_odds = 1.10 / p_bar ; surplus = offered_odds - required_odds ; edge = p_central - market_p
verdict = VALUE when offered_odds > required_odds
```

`config/sofa_engine_constants.json` carries each constant with a `status`; a
constant with no data is `null` / `NOT_FITTED` and the row says
`UNFITTED_CONSTANTS` (`K_PRICE`, `MAX_LADDER_SIGMA`). **Never strip that
note.** `K_PRICE` is honestly unfitted: Brier improves monotonically all the
way to `w = 0` (the price), so there is no interior optimum to name.

### Re-deriving a row

`audit_coupon.py` re-derives Chain 1 from the row's own fields:

```
required_odds == 1.10 / p_bar
surplus       == offered_odds - required_odds
edge          == p_central - market_p
p_bar         == w * (p_central - calibration_correction) + (1 - w) * market_p,  w = n / (n + 10)
```

`p_central` itself is only approximately reproducible (`pred_sd` is not on
the row; 5 of 63 rows fell outside 0.024). Check it against **the sample's own
hit rate** in `03_samples.json` instead. On a stats-only row `p_central` must
not move with `market_p` at all. An old-epoch tennis row was blended with the
price (`TENNIS_RATING`, `P_SHRUNK_TO_PRICE` notes) - re-derive from the row's
`epoch` and notes.

### Three things that look wrong and are not

1. `centre` != `sample_mean`: shrinkage. At football K 15 a sample of n = 8
   is 35% of its centre - compute `n / (n + K)` before trusting a
   `*_1h_*` / `*_2h_*` row and say how much is the league prior.
2. `ladder_centre` / `ladder_sigma` describe the bookmaker's ladder;
   `ladder_sigma` ~0.003 is normal.
3. A football `p_central` differs from the sample's hit rate; above ~15 pp the
   prior or the rating, not the team's sample, is doing the work (football
   `MODEL_ABOVE_OWN_SAMPLE`, gap > `MAX_OWN_SAMPLE_GAP` 0.15, n >= 5, removes
   the leg automatically; football non-prop rows only - player props are
   excluded, `confidence.py` `is_player_metric`).

## Chain 2 - confidence (`src/bet/sofa/confidence.py`, `src/bet/sofa/line_evidence.py`)

```
curve      = Calibration.realised(market, p_central, sport, direction, klass, line) -> realised_lo95
confidence = min( curve + offset(key),  price_band_cap(key, p, odds) )       offset <= 0
             key with no curve at p: Wilson lower bound of the key's own settled Superbet lines in p's bucket
             / the design effect (>= MIN_EVIDENCE_BUCKET 50 lines, MIN_EVIDENCE_GAMES 15 games), else NO_LINE_EVIDENCE
x          = confidence * offered_odds          prints at >= 0.90 (else NEGATIVE_LEG_EV)
condition  : confidence >= 0.70, ladder margin <= 15% (single_is_fairly_priced), odds >= MIN_ODDS_FOR_CEILING 1.0867,
             not started (MIN_MINUTES_TO_KICKOFF 15 before the start clock, SKILL.md), price <= 45 min old
order      = confidence desc, kickoff asc, match, market, line   (confidence.coupon_order / coupon_sort_key) - no price, no EV
```

`COUPON_PROFILE` = floor 0.70, `min_ev` 0.90, `max_overround` 0.15, no page
limit. A price that moved since SHEET is judged at the fresh odds.

**Curve lookup order** (`Calibration.realised`): the leg's own line bucket
(`line:<market>|<DIR>@<line>`, men's football keys of
`config/sofa_line_curves.json`) -> a class leg (women, season_early, tennis
team cup) reads only its class's curves (`<class>:...`; none = `NO_CLASS_CURVE`)
-> the market x direction curve -> a player prop stops here -> the market's
two-direction curve (`market:<m>`, K13-capped) -> a derived joint, a
rating-only market, a curve slice (`market@subject@line`), an
`AWAITING_OWN_CURVE` market with no curve and a tennis per-set market stop
here -> no borrowing above the market's own measured ceiling -> the sport's
pool (`pooled:<sport>`) -> the global pool, both K13 / K13b-capped. Nothing
found: the line-evidence stand-in, else `NO_LINE_EVIDENCE` / `NOT_CALIBRATED`.
Silence above a market's measured range is evidence, not a gap; the curve
tops out at `CONFIDENCE_CEILING` 0.9202 - there is no 98% leg.

**K13** (`cap_market_by_thin`): a thin direction bucket
(`thin_by_market_direction`) caps the two-direction curve and the pools -
the lower of the two Wilson bounds, `calibrated_on:
market_thin:<market>|<direction>`. **K13b** (`cap_pool_by_neighbour`,
`epochs.POOL_NEIGHBOUR_CAP_FROM_UTC`): a pool read of a hole in a market's own
curve is capped by that market's nearest own bucket below.

**Line evidence** (`config/sofa_superbet_line_evidence.json`, refitted every
morning by `refresh_line_evidence.py`; `fitted_from.before` must be the day
built). Key = `market|DIRECTION`, `<class>:`-prefixed for a class.
- offset: the key's realised-minus-confidence on printable lines; needs
  `MIN_OFFSET_ROWS` 50 lines and `MIN_OFFSET_GAMES` 30 games, else the
  sport's pooled offset (`MIN_SPORT_OFFSET_GAMES` 20; measured without a key
  holding more than `CONCENTRATION_MAX` 50% of the lines - the one way a
  CS2 key can come out higher); never above 0.
- price-band cap: `PRICE_BANDS` 1.30 / 1.60 / 2.20, cell `MIN_CAP_CELL` 20;
  applied only where the cell measured below the confidence; a thin cell
  widens downward inside its band, else the key's lines over every band from
  p down to 0.70.
- a leg lowered carries `line_offset` / `price_band_cap`; `calibrated_on`
  reads `<curve><offset>sb`, `...|cap:<cell>` or `sb:<sport>:<key>`; the
  line-evidence constants join `unfitted_constants`
  (`line_evidence.UNFITTED_CONSTANTS`).

## Chain 3 - the measured sports (`src/bet/sofa/sport_confidence.py`)

```
p_model    = score_model (hockey, basketball, volleyball) / cs2_engine (CS2) / player_model.jsonl (player lines) - no price
curve      = realised_lo95 of p_model's bucket in the file sport_confidence.calibration_path_for(date) returns
             (the staged file with the latest effective_from <= date; from 2026-10-28 .next.2026-10-28.json);
             a bucket with n < MIN_BUCKET 200 is unused
confidence = the same min(curve + offset, band cap) / stand-in as Chain 2
print      : confidence >= 0.70, odds >= 1.0867, group margin <= 15%, x >= 0.90, price <= 3 h old (sport_day.MAX_PRICE_AGE)
```

`forecast_p` = `p_model`; `sample_k / sample_n` shown, never a gate.

## Builders (`confidence.py`)

`odds_product`, `odds_after_haircut`, `ev_after_haircut`, `odds_if_product`,
`ev_if_product_priced` are internal - **never printed, never reported as a
price**. One exception (operator, 2026-10-26): a chat slip
(`build_slip.py --builders`) shows a builder as "<product> iloczyn" (the
product of its legs' single prices) and counts the slip's target on it -
never called "kurs", never our price; `build_slip.py --check` prints no
product at all.

```
legs        : one per quantity family (goals, corners, fouls, cards, shots, offsides, games, aces, double_faults;
              an unmapped market is its own family), chosen by confidence (best_leg_per_quantity)
product_p   = prod(confidence_i)
combined_p  = min(product_p, empirical_joint)        the joint may demote, never promote
odds_after_haircut = prod(offered_odds_i) * (1 - BUILDER_CORRELATION_HAIRCUT)   (a recorded screen price wins)
stakeable   = best_for_fixture and combined_p * odds_after_haircut >= 0.90       (stakeable_rule "x>=0.90"; is_stakeable)
```

A team's goals and the match total are one quantity counted twice; legs that
disagree on tempo (goals UNDER + corners OVER) make the product overstate.
The 2-, 3- and 4-leg builders are prefixes of one pool - `best_for_fixture`
is nearly always the 2-leg one; staking all three stakes one opinion three
times. The 12% haircut is the middle of Superbet's measured markup
(8.8-19.6% on three screen prices); the single legs were priced faithfully.

## Constants (checked in code 2026-10-19; `tests/sofa/test_agentic_config.py` guards the starred ones)

| constant | value | module | role |
|---|---|---|---|
| `MIN_ODDS_FLOOR` * | 1.25 | `bet.sofa.coupon` | old selector's odds floor (06 only) |
| `MAX_SAMPLE_AGE_DAYS` * | 60 | `bet.sofa.coupon` | `STALE_SAMPLE`: newest observation older than this (06 and CONFIDENCE) |
| `MAX_PER_FIXTURE` * | 3 | `bet.sofa.coupon` | old selector's cap per fixture |
| `MAX_PER_MECHANISM_FAMILY_PER_FIXTURE` * | 1 | `bet.sofa.coupon` | old selector's `FAMILY_SLOT_TAKEN` |
| `MAX_DISAGREEMENT` * | 0.10 | `bet.sofa.confidence` | `DISAGREES_WITH_PRICE` - off since the stats-only epoch (old days only) |
| `BUILDER_CORRELATION_HAIRCUT` * | 0.12 | `bet.sofa.confidence` | builder haircut (internal) |
| `MIN_BUILDER_SAMPLE` * | 10 | `bet.sofa.confidence` | observations a builder leg needs (`THIN_SAMPLE_FOR_BUILDER`) |
| `MIN_BUILDER_LEGS` / `MAX_BUILDER_LEGS` * | 2 / 4 | `bet.sofa.confidence` | builder size |
| `MAX_BUILDER_SAMPLE_AGE_DAYS` * | 180 | `bet.sofa.confidence` | `SAMPLE_CROSSES_SEASON` (national teams judged by count) |
| `CONFIDENCE_CEILING` * | 0.9202 | `bet.sofa.confidence` | top of the curves; `MIN_ODDS_FOR_CEILING` = 1/0.9202 = 1.0867 |
| `K_PRICE` * | 10.0 | `bet.sofa.engine` | old bar's blend weight, NOT_FITTED |
| `MAX_OWN_SAMPLE_GAP` | 0.15 | `bet.sofa.confidence` | `MODEL_ABOVE_OWN_SAMPLE` |
| `READ_REQUIRED_EVENTS` / `READ_REQUIRED_SINGLES` | 20 from 2026-10-27 (`read_events` on the artifact); 30 / 30 before | `bet.sofa.confidence` | the read set (matches / positions on older days) |
| `MIN_MINUTES_TO_KICKOFF` | 15 | `bet.sofa.confidence` | kickoff margin (sports: `sport_day.KICKOFF_MARGIN`) |
| `price_max_age_min` | 45 | `bet.sofa.config` | football / tennis `STALE_PRICE` |
| `MAX_PRICE_AGE` | 3 h | `bet.sofa.sport_day` | measured sports' `STALE_PRICE` |
| `PLAYER_MIN_SAMPLE` | 5 | `bet.sofa.epochs` | a footballer's shape-gate floor (`PLAYER_SHAPE_GATE_MARKETS`) |
| `GAP` | 0.03 | `bet.sofa.price_gap` | `price_gap` flag; `read_value` cap |
| `PEER_BAND` | 0.06 | `bet.sofa.peer_choice` | peers priced within this |
| `MIN_BUCKET` | 200 | `bet.sofa.sport_confidence` | sport curve bucket floor |
| `CLOCK_GAP_MIN` | 30 | `bet.sofa.fixture_status` | FIXTURE_CHECK asks a match whose Superbet start moved more |
| `VOID_AFTER` | 48 h | `bet.sofa.settle` | start brought forward beyond this = refund |
