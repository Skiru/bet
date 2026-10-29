---
name: tennis-analysis
description: How to read one tennis match's coupon legs in sofa - games, a player's games, sets, per-set games, winner and set markets, aces, double faults, serve points - format and surface first, which estimator priced the row, opponent class, serve / return, scoreline arithmetic per rung, schedule, fatigue. Preloaded into sofa-analyst-tennis.
---

# Tennis analysis - the method, mapped to what `sofa` holds

`sofa-pipeline` and `sofa-analysis-core` are preloaded: they hold the input,
the numbers, the verdicts and the output contract. This skill is the tennis
method.

| reference | read it when |
|---|---|
| `.claude/skills/sofa-analysis-core/references/market-drivers.md` | **before the first match**, only §2 Tennis: `sed -n '/^## 2. Tennis/,/^## 3\./p' <file>` - the drivers per family, written with their values in **Czynniki rynku** |
| `references/data-inventory.md` | what is measured, how the sample is scoped, which estimator prices which market, what is absent |
| `references/market-playbook.md` | grading a specific market: drivers, scoreline arithmetic, kill cases, serve markets, `set_score_not`, builders |
| `references/methodology.md` | the model behind a claim: point hierarchy, serve / return, surface and format, H2H decay, fatigue |
| `references/event-protocol.md` | writing a match section (the Polish template) |

The operator's method, `docs/sofa/SUPERBET_BET_BUILDER_METHOD_v3.md`, predates
`sofa`: cite sections, take no pipeline behaviour from it.

## What makes tennis different

1. **No source of record.** Sofascore and Superbet only; verification is the
   web, two domains, tagged. ITF game-level statistics are not free -
   `UNVERIFIED` is often the honest answer. Say it once in the header.
2. **The clocks disagree structurally.** On ITF Superbet posts a nominal
   "not before" and Sofascore's time can be hours off; gaps reach 11 h and a
   finished match can look upcoming. Take the earlier clock; report the gap.
3. **Every market is a function of match length.** A short match settles
   every UNDER at once: two tennis legs of one match are usually one bet.
4. **Two estimators** price the rows (below); know which one before you
   compare numbers.
5. **The scope rests on two fields.** `samples.py` keeps a past match only
   if `settle.surfaces_comparable(event.groundType, fixture.ground_type)`
   (equal, or a generic "Hard" / "Clay" against any member of its family)
   and `metrics.infer_best_of(event) == fixture.default_period_count`. A null
   `ground_type` empties the sample (`SURFACE_UNKNOWN`); a null
   `default_period_count` skips the format scope silently, and the rating
   reads the match as best of three. A retirement never enters a sample.
   **Check both fields on every match.**

## Which estimator priced the row

The rating (`src/bet/sofa/tennis_rating.py`): a surface-blended Elo
calibrated per tier gives the match-win probability; the 600 historical
best-of-three matches nearest to it (`NEIGHBOURS`, from the tier x gender
cell) are the score distribution, read empirically. It needs best of three
(or a null format) and both players with >= 10 rated matches (`MIN_RATED`);
best of five is not modelled.

| market | `p_central` (= `model_p` on the leg) | `forecast_p` |
|---|---|---|
| `games_won_for`, per-set games (`games_set1/2_total`, `games_won_set1/2/3_for`), `sets_total`, `match_won_for`, `set1/2_won_for`, `set_score`, `set_score_not` | the neighbours alone - no sample, no price | **equal to `p_central`** |
| `handicap_games`, `most_games` (not the draw) | the neighbours alone | none |
| per-set games handicap `handicap_games_won_set1/2` | from 2026-10-28 the neighbours' own set-N margin (note `SET_HANDICAP_NEIGHBOURS`); earlier the rho-0 joint of the two players' set games | none |
| `games_total` | 0.5 x neighbours + 0.5 x the NB count model on the sample | the rating alone |
| aces, double faults, serve points (match, per set, totals), `tiebreaks_total`, `most_aces`, `most_serve_points` | the sample's estimator around a shrunk centre (`K_CENTRE` tennis 8: at n=10 the sample owns 56%) | none |
| any rating-priced family the rating cannot read | the sample's estimator; the rating-only markets (`match_won_for`, `set1/2_won_for`, `set_score`, `set_score_not`) get no row | none |

Rating-only legs (`match_won_for`, `set1/2_won_for`, `set_score`, `set_score_not`) carry
`sample_size` 0 - there is no próbka. An independent check can be rebuilt from the players'
per-set games in `03_samples.json` (`games_won_set1_for`, `games_won_set2_for`,
`games_set1_total`, `games_set2_total`, `sets_total`) - context only, never a removal rule on its own.

The tier prior (`tennis_prior.TIER_PRIOR_METRICS`: aces, double faults,
`games_total`, `sets_total`) shrinks a sample centre only on best of three or
a null format (`scripts/sofa/run_sheet.py`).

Consequences:

- On the rating-priced families **model is not a second opinion** - it is
  the same number. The independent evidence on the leg is **próbka k/n**:
  the player's own scoped record. A próbka far from `p_central` is the rating
  and the player's record disagreeing - say which scorelines each leans on.
  The code's `MODEL_ABOVE_OWN_SAMPLE` removal is football-only: in tennis
  the disagreement is a note in the section, never a removal by itself.
- The neighbours know the match-win probability, tier and gender - not the
  surface, this player's serve, nor the sample's opposition. Your
  decomposition is what the number lacks.
- On a rating-priced row `p_central` moves in steps of 1/600 set by the
  neighbours; identical `p_central` across rungs of a sample-priced row means
  no observation falls between them.
- SHEET refuses `sets_total` on a match not known to be best of three -
  best of five or a null format (`BEST_OF_FIVE_NOT_MODELLED`).
- **Serve markets:** aces / double faults are priced from the server's own
  sample; the returner never enters the number. Read such a leg against the
  returner (return points won, aces his opponents serve).

`games_won_for` is **bimodal**: a straight-sets winner has >= 12 games, a
loser spreads over 0-11; Superbet's line is usually 11.5, **in the trough**.
Say where the line sits against the wall at 12.

**Match tiebreaks (open operator question).** A 10-point match tiebreak
(ITF, UTR, team cups) counts as **one game** to its winner in every sample,
neighbour and settlement (`tennis_score.set_games`); Superbet's count is
unverified. Name it on any leg such a tiebreak could decide; do not decide it.

**Retirement and walkover are refunds** (0 u.): a void risk, not a loss risk.

## The protocol - format and surface first, the price only as the filter

Template and step table: `references/event-protocol.md`.

1. **Format, surface, identity, clocks.** `02_fixtures.json`
   `default_period_count` (the real best-of; the dossier has none), `ground_type` (or "nieznana"), `identity` (`FUZZY` on a tennis
   name is a real risk - names collide), both clocks; then the tournament's
   order of play, tagged. Qualifying is best of three even at a slam.
2. **Sample integrity, per side.** Scoped n per side, dates, opponents, the
   `side_a` / `side_b` split of a total. A thin side is the code's job (it
   needs >= 5 per side) - never a veto by count. A veto only when the
   observations do not measure this match (another surface, format or class,
   placeholders): reason `DEFEKT: 03_samples.json <metric> <side> …`.
3. **Which estimator** (table above), and the shrinkage share of a
   sample-priced row.
4. **Opponent class of the sample.** Each observation carries `opponent` and
   `opponent_id`, no ranking: classify the sample's opposition against
   tonight's opponent.
5. **Serve / return.** `aces_for`, `double_faults_for`, `serve_points_for`
   plus the web's hold % and return points won on this surface. High-hold
   competitive OVER, breaks-and-three-sets OVER, or one-sided UNDER? Aces are
   not tie-breaks; a big serve often shortens a match.
6. **Distribution and scoreline arithmetic.** min, max, median, mode; the
   concrete scorelines settling each rung (`6-3 6-4` = 19, `7-6 6-7 7-6` =
   39, a player's games in `6-2 6-3` = 5). Which rung does the modal
   scoreline land on?
7. **Schedule and fatigue.** `schedule` (`last_match_utc`, `rest_days`,
   `matches_7d`, `matches_14d`) and `context_flags`; the previous match's
   length from the web; back-to-back days, a qualifier's extra rounds, a
   recent retirement. Known before the price, all of it - and points to
   defend - is a note, never a veto or a removal by itself; a WATCH only
   through a dated consequence since the price (an MTO, a withdrawal doubt).
8. **H2H with decay** - a supporting prior, never the primary signal; `h2h`
   never reaches a `*_for` row, and a `*_total` pools h2h with no age rule.
9. **Scenario matrix.** Favourite pulls away / underdog holds / both first
   serves work / tie-break or deciding set. The favourite's strength without a
   price: the rating's `forecast_p` on the `match_won_for` sheet row. A
   price is never evidence.
10. **Market drivers, ladder and tail.** Per family the drivers of
    `market-drivers.md` §2 Tennis with their values (**Czynniki rynku**, a
    note - never a removal in tennis); then rung by
    rung in prose, only the rungs of the legs read - no rung table; a third
    set adds 12-15 games - the tail is huge and one-sided.
11. **Buy case / kill case -> verdict.** The price is the filter the code
    applied; a one-sided rung has `market_p` null - say so.

## Kill cases this repo has paid for

- **One side scoped to zero** - a `double_faults_total` of n=9, all one
  player: a total that is one player's history. Check the `side_a` /
  `side_b` split on every total.
- **The wrong surface** - aces 5.5 OVER built on grass for a hard court
  (medians 9.0 / 11.0 vs 6.0 / 5.0). A generic "Hard" label can sample
  outdoor matches for an indoor fixture.
- **Opponent class not conditioned** - a `games_won_for` mode of 12 built
  against much weaker fields, tonight against a far stronger opponent.
- **A format the rating does not read** - best of five gets no `forecast_p`;
  a null format on a men's slam is the failure to look for.
- **Best-of-three tautologies** - `sets_total UNDER 3.5` on a best of three
  is a tautology; never lead with one.
- **A match tiebreak decides the leg** - Superbet's count unverified.
- **Two UNDERs of one match** - one bet charged twice; `games_*`, `sets_*`,
  `tiebreaks_*`, `handicap_games` share one builder family, aces and double
  faults do not.
- **Classes** - women's events, Davis / BJK Cup and exhibitions read only
  their class curves.

## Removals

| reason | verdict |
|---|---|
| a fact newer than the price, `[WEB: domena, publ. <data>, fetched <czas>]`, one domain | WATCH at most |
| the same fact on two domains | NO_BET |
| withdrawal / walkover / postponement confirmed on two domains | NO_BET with both `[WEB:]` tags (the next FIXTURE_CHECK removes it too) |
| `DEFEKT: <artifact> <field> ...` - a value **wrong for tonight**: identity, format (`default_period_count`), surface (`ground_type`), a sample of another surface / format / class | NO_BET or a `SAMPLE_UNINFORMATIVE` veto |
| everything else - rest, a long previous match, travel, points to defend, form, h2h, ranking, the rating, `forecast_p` vs próbka, a market driver's numbers, a family's past record, retirement risk, a line move | a note in **Za / Przeciw**, never a removal |

A correct value the model does not use is a note, never a `DEFEKT:`. There
is no `RYNEK:` removal in tennis.

## Tennis output requirements

Per match, in the section of `references/event-protocol.md`, with these
labels: heading with `sofa:<id>`, **W skrócie:**, **Fakty zabójcze (przed
siecią):**, **Kluczowe przed meczem:**, **Czynniki rynku.**, **Kontekst
(web).**, **Nogi.**, **Za / Przeciw:**, **Szczegóły techniczne:**. Content:
format from `02_fixtures.json` `default_period_count`; surface from `ground_type` or
explicitly unknown; round and start as verified, both clocks and the gap;
each side's scoped n and the class of its opposition; which estimator priced
each leg; the scorelines that settle each rung; the previous match where you
found it.
