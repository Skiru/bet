# Football market playbook — drivers, base rates, kill cases

> **Since 2026-10-07 10:55Z (`epochs.LINE_EVIDENCE_FROM_UTC`)** the refusals BY NAME below (`DERIVED_NOT_CALIBRATABLE`, `OPERATOR_REFUSED` / `refused_markets`, `PLAYER_PROP_NOT_ADMITTED`, `TENNIS_SET_MARKET_NOT_ADMITTED`, a sport key outside `admitted`) describe the old epoch only: every market is now read through its own settled Superbet lines (`bet.sofa.line_evidence`), and one with no measurement is `NO_LINE_EVIDENCE`. See `.claude/skills/sofa-pipeline/SKILL.md`, "Line evidence and the 2026-10-07 changes".

For each market: what `sofa` measures, what moves it, the base rate, the kill
cases, and what a good read says. Base rates are the global means of `config/sofa_league_baselines.json`
(Sofascore settled rows, fit 2026-10-07 17:13Z, 7,255 competitions): **orders
of magnitude, not priors you may substitute for `centre`** - a competition's
own baseline is what the sheet shrinks toward, and leagues differ more than
most teams do. A base rate that only an earlier provider's sample gave is
dropped rather than quoted.

Which markets `sofa` actually prices is decided by Superbet's screen. On
2026-10-07 (`05_sheet.json`, football rows: 7,184, 56 distinct markets)
`goals_total` (946 rows), `goals_for` (606), the player props (1,516 between
them), `corners_total` (390), the goals halves and `corners_for` (278) dominate,
and `fouls_total` produced 30, `shots_total` 90. Saves, throw-ins, goal kicks
and tackles are priced as well (`saves_total` is on the coupon).

---

## Corners — `corners_total`, `corners_for`, `corners_1h_*`, `corners_2h_*`

- **Measures:** corners awarded, from `/statistics`, per period.
- **Drivers:** attacking volume and *width* (crosses, full-back involvement);
  the opponent's block depth — a deep block blocks shots, and blocked shots
  are corners; game state (a trailing side wins corners without winning);
  wind argues down. **Goals ↔ corners ≈ 0**: a goal-heavy match is not a
  corner-heavy one.
- **Base:** 9.48 per match (n = 62,476), per team 4.76. Not rated:
  `corners_total` and every corners half row take the sample's centre alone
  (`football_rating.UNRATED_MARKETS`); `corners_for` is rated and priced by a
  negative binomial, `corners_total` by a normal CDF.
- **Kill cases:** a team-corner OVER stacked with a total-corner UNDER without
  a tail test (Porto–Arouca 12–2 — one side can destroy the total alone); a
  sample mean far from the book's ladder centre (2.80 against 5.76 means the
  sample described a different team-state — look for `LADDER_DISAGREES`); one
  side's ten matches in a different competition class; a 1.40 price on a
  per-team 4.5, which asks 70% of a coin-flip market.
- **Half-match warning.** The `corners_2h_total` global baseline rests on
  **102** observations (`corners_1h_total`: 721), and a stale baselines file once
  gave corners priors 24–32% too high for two days (September 2026). At n=8 the
  row is 65% league prior (before any rating). Compute `n/(n+15)` and say it.

## Cards — `cards_points_total`, `cards_points_for`

- **Measures:** **booking points, not cards.** From `/incidents/`: yellow 1,
  straight red 2, second yellow 3 — the way Superbet settles *Liczba kartek*.
  A yellow-only count reads 7/7/4 on a match whose real figure is 10/9/4.
  Rescinded cards are handled.
- **Drivers, in order:** the **referee** (a third of a line between officials
  in one league; what looks like home bias in cards is referee behaviour),
  fouls volume, stakes (derby, knockout, relegation), game state (0-0 late in
  a knockout), each side's discipline profile, and red-card propensity, which
  adds 2–3 points at once.
- **Base:** booking points 4.50 per match (n = 52,247), per team 2.25
  (global baselines, 2026-10-07). Staff cards (a card shown to the bench or the
  coaching staff, `manager` with no `player` in the incident) are not counted,
  as Superbet's rules say; a card to an unused substitute is.
  `cards_points_for` is unrated: the centre is the sample's alone, so the
  sample's own `venue` field is all there is for home / away.
- **`sofa` does not blend the referee into the centre.** The old pipeline did;
  this one does not, and the referee is present on ~9% of fixtures. So the
  referee is entirely your contribution here — and its absence is the normal
  state, not a defect to chase.
- **Kill cases:** no referee in a high-spread league on a tight line; a line on
  the mode (7.5 with five 7s and two 8s in twenty); a red in a derby second leg
  (+2/+3 at once); an official with 3–4 matches behind the rate; an UNDER in a
  tie that can go to extra time — 30 more minutes settle into the market.

## Fouls — `fouls_total`, `fouls_for`, `fouls_1h_*`

- **Measures:** fouls committed, from `/statistics`.
- **Rarely priced.** 30 `fouls_total` rows (60 `fouls_for`) among 7,184
  football rows on 2026-10-07. Check the offer before spending analysis on it.
  The fouls rows are priced by a normal CDF, not a negative binomial.
- **Drivers:** the referee's foul tolerance, the league (the per-competition
  means in `config/sofa_league_baselines.json` differ by more than most teams
  do), pressing and duel intensity, derby or knockout, and game state: a side
  protecting a lead fouls to stop transitions. Fouls run mildly **against**
  goals (an earlier sample: r ≈ −0.13).
- **Base:** 24.67 per match (n = 54,208), per team 12.37 (global baselines).
- **Estimand check:** `fouls_for(A) + fouls_for(B) ≈ fouls_total` mean. A large
  gap means the pooled and per-team samples describe different match sets.
- **Kill case:** the misses are the h2h — a pairing running 43/39/33 against a
  pooled 27.

## Shots and shots on target — `shots_*`, `shots_on_target_*`

- **Measures:** from `/statistics`. The raw field `totalShotsOnGoal` is **all
  shots** despite its name.
- **Many of our rungs have no price**: on 2026-10-07 `shots_total` had 90 and
  `shots_on_target_total` 118 rows among 7,184 football rows. Both are priced by
  a normal CDF; the rating centres them (shots and shots on target are rated).
- **Drivers:** attacking volume, opponent block, game state (a trailing side
  shoots more and worse), finishing regression, tempo. **SOT ↔ goals strongly positive** (an earlier
  sample: +0.55) — a SOT OVER and a goals OVER are one thesis, not two, and `confidence.py`
  enforces that by putting `shots` and `goals` in different quantity families
  but refusing builders whose legs disagree about tempo.
- **Base:** SOT 8.64 per match, per team 4.35; shots 24.72 per match, per team
  12.39 (global baselines, 2026-10-07).
- **Kill cases:** a mean pulled by outliers against weak opposition (41–50 shots
  four times — the median still describes the fixture, so this is a caveat, not
  automatically a veto); a favourite that scores early and manages, which kills
  SOT-for in the second half.

## Goals — `goals_total`, `goals_for`, `goals_1h_*`, `goals_2h_*`

- **Measures:** off the score, so `n` runs ahead of every other market — every
  finished match has a score, far fewer have full statistics. Halves from the
  half-time score.
- **Extra time.** `EXTRA_TIME_STATUS_CODES = {110, 120}`: a goal count of such
  a match is read at 90 minutes (`normaltime`), every other counting metric
  of it is refused (`EVENT_NOT_FINISHED`). Superbet's "(z dogrywką)" markets
  and its 90-minute markets are different questions; check which one the
  rung is.
- **Halves:** first halves carry ~45% of goals, not 50%. The half-match
  baselines are measured on a smaller population (2,448 against 598,987
  observations for goals, fit 2026-10-07; `half_match_coherence` `OK`, it had
  reported −13% / −17% for the goals halves earlier). Say so on any
  `goals_1h_*` / `goals_2h_*` row.
- **Sample:** for a league fixture `goals_total` / `goals_for` / the halves'
  `_for` read the side's last ten REGULAR matches of the same competition
  (five or more), a knockout fixture the usual newest ten.
- **Kill cases:** a 0.5 OVER or 5.5 UNDER at 1.01–1.05 topping a sheet by hit
  rate — certainty for free is not a bet, and CONFIDENCE refuses any price under
  1.0867 for exactly that reason; a second leg whose aggregate changes who must
  score; a past-frequency streak read as an edge (the pewność is the claim,
  not the streak).

## Offsides — `offsides_total`, `offsides_for`

Driven by the high line of *one* side and the runners of the other. Thin
samples, high variance, and Superbet's ladder starts at 2.5. 30 `offsides_total`
and 60 `offsides_for` rows on 2026-10-07 (full-match offsides use a negative
binomial; `offsides_total` is unrated). WATCH unless the matchup argument is
specific.

## Saves, throw-ins, goal kicks, tackles — `saves_*`, `throw_ins_*`, `goal_kicks_*`, `tackles_*`

Collected and priced, unrated (no rating centre), normal CDF; they sit in the
shots family for the builder (saves, goal kicks) or their own. Their zeros are
often the provider not counting (see the data inventory): look at the sample
for a gap before trusting a low mean. Goalkeeper saves follow the opponent's
shots on target and the keeper in goal tonight, which nothing in the artifacts
names (a changed keeper is a `CONTEXT` veto). `saves_total` and `saves_for` legs
were on the 2026-10-07 coupon.

## xG — `xg_total`, `xg_for`

Collected, absent for most competitions, and **not priced by Superbet**. Use it
as a regression argument against a shots or goals lean built on results. Do not
read an absent xG as zero.

## Derived markets — `both_over_*`, `most_*`, `handicap_*`

- **Not sampled.** They are functions of two sides, priced from the two sides'
  marginals and `config/sofa_side_correlations.json`; since 2026-10-07 14:05Z
  the goals, corners, shots-on-target and cards joints use the marginal rows'
  centres (K_CENTRE shrink + rating, variance scaled with the centre), the
  fouls, shots and offsides joints the raw sample mean and variance. Notes
  that say how far the market checked the row: `NO_MARKET_MARGINAL`,
  `ONE_SIDED_LADDER`, `MARGINAL_DISAGREEMENT`, `NO_LADDER_CHECK` (these also
  decide the old VALUE selector's verdict, not the coupon's confidence).
- **No history curve** (`epochs.DERIVED_CURVES_FROM_UTC` is off).
  `DERIVED_NOT_CALIBRATABLE` is gone; a derived row's confidence is the Wilson
  bound of its own settled Superbet lines, else `NO_LINE_EVIDENCE`. As coded,
  such a row has no observations for the sample gates, and neither the
  2026-10-06 nor the 2026-10-07 coupon holds a football derived leg, single or
  builder.
- The residual correlation between the two teams' corners is **r = −0.145**
  (raw −0.198), goals −0.012 (config, `_min_pairs` 200). "Both over"
  intuition assumes a positive sign for corners.
- On 2026-10-07 these were 702 of 7,184 football sheet rows (`DERIVED` note).
  If one is in your read set, report the two `*_for` rows and refuse the
  multiplication.

## Per-team markets in general — `*_for`

- Tonight's venue against the sample's own mix: eight away matches ahead of a
  home fixture is a thinner sample than `n=8` looks.
- **`h2h` never reaches a `*_for` row** — by design. A head-to-head is a fact
  about a pairing; `*_for` is a claim about one side.
- **No `*_against` observation exists.** Use the opponent's `*_for` and label
  it a proxy; the rating's defence ratio (`FOOTBALL_RATING` note, rated markets
  only) is the one built-in opponent adjustment.

## Player props — `player_shots_for`, `player_shots_on_target_for`, `player_assists_for`, and since 2026-09-29 `player_fouls_for`, `player_tackles_for`, `player_interceptions_for`, `player_offsides_for`

The four newer ones are omitted by Sofascore on a zero; a zero is taken only
in a match where the appearing players sum to the team's `/statistics` value
(closes in ~98% of team-games), otherwise the match is a gap for that player.
Fouls SUFFERED ("fauli na zawodniku") is not mapped - no identity proves it.

New 2026-09-22 (F54). Three metrics, read per player out of
`/event/{id}/lineups`, living on their own axis in `03_samples.json`
(`players`, keyed `"<metric>|<player as Superbet writes him>"`) rather than in
`metrics`. Everything else Superbet prices on a footballer — "strzeli gola",
"otrzyma kartkę", and the eight body-part and location variants of shots —
stays in `unmapped_markets`, because Sofascore reports none of those splits
and a yes/no proposition is not a rung on a ladder. Do not grade one of those.

**Do not argue for a player prop.** Superbet quotes these on ONE side only —
437 "powyżej" and 0 "poniżej" on the whole 2026-09-22 board (dated) — so
`market_p` is `None`, `NO_PRICE_ANCHOR` fires and the old VALUE selector stops
at `LEAN`. On the coupon the same missing under-price leaves the rung with no
ladder margin, and a single prints only with a margin <= 15%: a one-sided prop
cannot be a single. It could in principle be a builder leg if it clears a curve
and its own Superbet lines (`player_*|OVER` keys exist in the line evidence;
`admitted_player_markets` no longer gates); no player leg is on the
2026-10-06 or 2026-10-07 coupon. That is the row being selected by our model
with no price checking it, the population the settled record called the worst
one on the sheet. Read these as forecasts.

Since 2026-10-01 shots, shots on target and assists are priced with a
negative binomial (`engine.NEGATIVE_BINOMIAL_METRICS`), not the normal: on
the settled player rows of 09-24..30 the normal put a median +8 pp on every
OVER (assists 0.5 OVER claimed 0.243, realised 0.081, n=495, dated). A sheet
built before that change carries the inflated OVER; do not compare a pre- and
post-change `p_central` as if the player moved. Fouls, tackles, interceptions
and offsides props still use the normal.

What to check when one is on the sheet:

- **`PLAYER_MINUTES`.** Every player row carries it: median minutes, how many
  appearances of 60'+, and how many of the side's sampled matches he played
  at all. A sample made of substitute cameos and a sample made of starts are
  not the same quantity, and the row's mean does not distinguish them. "6 of
  10 sampled matches, median 22'" is a veto-worthy sample for a line priced
  as though he starts.
- **Is he starting at all?** The sample is his past *appearances*; the bet is
  about this one. A rotation risk, a suspension or an injury doubt is
  exactly the `CONTEXT` veto this family needs most, and nothing in the code
  can see it.
- **The sample is his club's last ten matches, not his own.** A player who
  transferred in during the window has a short sample with no note saying
  why; compare `sample_size` against `squad_matches`.
- **Do not pair one with his team's line.** A player's shots and the team's
  shots are one quantity counted twice, and an assist belongs to the goals
  family; `confidence.py` enforces this (`quantity_family`) but say so if you
  see it proposed.

## Bet Builders

`scripts/sofa/run_confidence.py` builds them (one per fixture, the best
`combined_probability`, at most one leg per quantity family) and you do not. What you contribute per candidate
slip:

- a concrete scoreline or stat line that satisfies **every** leg at once, and
  whether that region is broad or an edge case;
- the shared mechanism, and the one scenario that kills every leg together;
- whether the legs really are different quantities (a team's goals and the
  match total are the same quantity — measured lambda 2.165);
- the price is NOT yours to state: since 2026-10-05 the operator reads a
  builder's price off Superbet's screen himself ("nie wyceniaj mi ich, sam
  będę widział") - never quote `fair_odds` / `odds_after_haircut` / an EV of a
  builder in a report.

**Never print a combined price of your own.** Prefer mechanism 1 + mechanism 2
over the same market three times.
