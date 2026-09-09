---
name: football-analysis
description: How to analyse one football fixture's counting markets (corners, cards as booking points, fouls, shots, shots on target, goals and halves, offsides, per-team lines, player props) from this pipeline's artifacts the way the literature and the operator's method say it should be done - stakes and round, second legs, derbies, referee, absences, season xG, venue, game script, distribution over mean, ladder choice, price last. Use when reading a football stats sheet, grading VALUE rows, writing analyst vetoes, or judging a Bet Builder draft. Preloaded into bet-analyst-football.
---

# Football analysis — the method, mapped to what this pipeline actually holds

Read `bet-analysis-core` first (it is preloaded with you). This skill answers
one question the core does not: *given these rows, how does a competent
football analyst decide whether the sample describes tonight's match?*

Reference files — open them at the step that needs them, not all at once:

| File | Open when |
|---|---|
| `references/data-inventory.md` | you need to know exactly what is measured, at which lines, what is context, what is missing |
| `references/methodology.md` | you need the model behind a claim (Poisson/Dixon–Coles, overdispersion, referee bias, game state, congestion, two-legged ties, shrinkage) |
| `references/market-playbook.md` | you are grading a specific market — drivers, kill cases, base rates, what settles it |
| `references/event-protocol.md` | you are writing a fixture section — the 15-step protocol and the report template |

The operator's method: `docs/SUPERBET_BET_BUILDER_METHOD_v3.md`. Open the
sections you use in this run — §15–§17, §22–§25, §32, §37–§44, §49, §64,
§69–§70, §76–§78, §88–§93, §99–§101, §108 — and say in the report that you did.
Do not restate its rules; cite the section.

## What a football analyst here is *for*

The code already: scopes the sample (drops friendlies, last season, stale h2h),
collapses duplicates, prices `p_low`/`p_central`, shrinks toward a market prior
with a venue split, blends the referee into card totals, flags derby /
second-leg / missing-referee / xG gap / ≥4 unavailable / wind, chooses the rung,
prices against Superbet, and gates by ladder σ. **It cannot** read a cup round,
an aggregate score, a table position, a manager change, a suspension announced
this morning, an opponent's style, or whether the four matches that make a mean
of 29 shots were all against Bolivian sides. That is the whole job: the
fixture-specific read the code cannot make, expressed as `KEEP / WATCH / NO
BET` per market and as vetoes the coupon can act on.

## The protocol, in the order the evidence hierarchy demands

For every fixture with a `VALUE` row in `<date>_superbet_comparison.json`, and
for any fixture whose rows you intend to veto (full template:
`references/event-protocol.md`):

1. **Identity & clock.** `get_match_detail(match_id=source_ids.bzzoiro)` →
   `status`, `event_date`, `round_name`, `previous_leg_event_id`, referee,
   venue. Anything but `notstarted` at the artifact's time → VETO (all lines).
2. **Stakes.** League round or cup? Which round? Second leg — read the first
   leg (`get_match_detail` on `previous_leg_event_id`; aggregate; whether extra
   time applies in this competition — it changes what "90 minutes" means for
   every UNDER). Table: `get_standings` — title/relegation/dead rubber.
   Derby: `is_local_derby` **or** `travel_distance_km < 25`. Congestion:
   `get_team_fixtures` — third match in seven days, continental tie midweek.
3. **Sample integrity** (core §"Sample integrity"): a/b/h2h split from the
   dossier, `sample_excluded`, `observation_flags`, `DISAGREE` on the line,
   h2h observations that are the *misses*, one side ≤3 retained. Then the
   estimand: does `fouls_for A + fouls_for B ≈ fouls_total mean`? Does the
   cards row use `cards_points_*`? Is a `*_for` row on the side you mean?
4. **Distribution.** Q25–Q75, mode, min, max, `mean` vs `median`; where the
   rung sits relative to the mode and to the sample's extreme; which
   observations make a skew and against whom.
5. **Opponent & venue.** Tonight's venue (`row.venue`) vs the sample's mix;
   opponent's own `*_for` / `goals_against` profile (we hold no `*_against`
   except goals — say so rather than invent an "allowed" number); style clash
   (a low block generates corners for the attacker and shots-against for
   itself).
6. **Season form.** `season_form.xgf/xga` with `xg_games`; the gap between
   goals and xG is the regression argument against a shots/goals lean built on
   results. Position and `form` string.
7. **Referee** (cards, fouls): `matches` first; `avg_yellow_per_match` vs the
   line; `avg_red_per_match`; `centre_note` tells you whether code already
   blended him in. Null referee on a card row = `MISSING_REFEREE` (code has
   capped the tier; you decide whether the league's spread makes it a
   DOWNGRADE).
8. **Squads & lineups.** `squad_availability` both sides (count, who,
   `availability_unknown_count`); `get_match_lineups` if within ~1h; props on a
   `predicted` XI stay `LEAN`; method §21 expected minutes < 70 forbids HIGH.
9. **Game script A–D** (method §24) weighted by the fixture's 1X2 from
   `market_context` / `compare_odds`: favourite ahead, underdog ahead, 0-0 to
   60', level. Say which scenario is modal and whether the market survives it.
10. **Ladder & tail.** All rungs Superbet posts, `p_low`/`p_central`/price per
    rung, `RUNG_SEPARATED_BY_MODEL`, the rung a half-point beyond the sample's
    extreme, tail both ways (method §16, §37, §88).
11. **Correlation** for anything the operator may combine: mechanism, direction,
    the one scenario that kills every leg (method §39–§42, §91–§93). Never a
    product.
12. **Price** — last. `min_acceptable_odds` vs `superbet.price` from the
    comparison; probability quality and value quality separately (§38); for
    goals markets also the devigged consensus via `audit_slip.py`.
13. **Buy case / kill case** (method §69): the strongest fact for, the strongest
    fact against, and which wins. `BUY ≈ KILL` → WATCH at most.
14. **Regression-test library** (method §108 + `references/market-playbook.md`
    kill cases): does this read resemble a known failure class?
15. **Fresh eyes → verdict** `KEEP / WATCH / NO BET`, the §32 grade, and the
    veto entry with the right `reason_class`.

## Kill cases this repo has already paid for (check each read against them)

- **Team-corner OVER + total-corner UNDER without a tail test** (Porto–Arouca
  12–2). One side can destroy the total alone.
- **The misses are the h2h.** Grenal fouls: 19/21 pooled, 1/3 conditional on
  the fixture. `SAMPLE_NOT_REPRESENTATIVE`, line null.
- **Line on the mode.** Grenal cards 7.5 with five 7s and two 8s in twenty;
  8.5 was the rung. `LINE_ON_MODE`, that line only.
- **DISAGREE on the line.** Náutico cards 6.5: 6 vs 8 on one match decided
  20/21 vs 19/21 and the bar. `DATA_CONFLICT`.
- **No referee on a card row in a high-spread league.** América–Alianza;
  `MISSING_REFEREE`, line null — a specific line let 7.5 through last time.
- **Mean pulled by four outliers against a different class of opponent.**
  Grêmio shots 29.6 mean / 26 median from Bolívar ×2, Chapecoense, Bragantino.
- **Sample centre far from the book's ladder centre.** Sheffield United
  corners mean 2.80 vs ladder median 5.76 — the sample described a different
  team-state; code now demotes at 1.25σ, you name why.
- **Past frequency read as an edge.** Brommapojkarna scored in 12 straight;
  the devigged consensus said 64% against a price asking 70%. Compare, then
  speak.
- **A short-priced 0.5 UNDER / 5.5 goals UNDER at 1.01–1.05** on top of the
  sheet by `p_low`. Certainty for free is not a bet; do not lead with it.
- **`both_teams_over`** has no sample; `min(p_A, p_B)` is a ceiling, not a
  floor. Report two `*_for` rows and forbid the multiplication.
- **Extra time / penalties in a cup second leg.** Check the competition's rule
  before trusting any counting UNDER; Copa do Brasil goes straight to
  penalties from R16, UEFA ties play 30 minutes.
- **Predicted XI props on a morning run.** All `LEAN`; substitutes' box scores
  with minutes are in the sample, unused subs are not; rotation makes `n`
  small for a reason.
- **`possession` is 100.0 in every observation** — a constant, not data.

## Output additions specific to football

Per fixture, always state (even when the answer is "none"): round/stakes and
where you read them, referee with `matches`, absences per side with the
unknown count, `season_form` xG with `xg_games`, derby/neutral/travel/weather
only when they weigh, the modal game-script scenario, and which rows the code
already stepped down (`context_flags`, `lean_ceiling_reasons`) so you do not
double-count them in a DOWNGRADE.
