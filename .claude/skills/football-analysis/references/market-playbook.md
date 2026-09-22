# Football market playbook — drivers, base rates, kill cases

For each market: what `sofa` measures, what moves it, the base rate, the kill
cases, and what a good read says. Base rates are in-repo measurements unless
stated; they were measured on a different pipeline's sample and are **orders of
magnitude, not priors you may substitute for `centre`**.

Which markets `sofa` actually prices is decided by Superbet's screen. On a
Monday board (5,674 rows, 2026-09-21) football produced 37 distinct markets;
`goals_total` (534 rows), `goals_for` (362), `corners_total` (210) and the
goals halves dominate, and `fouls_total` produced **4**.

---

## Corners — `corners_total`, `corners_for`, `corners_1h_*`, `corners_2h_*`

- **Measures:** corners awarded, from `/statistics`, per period.
- **Drivers:** attacking volume and *width* (crosses, full-back involvement);
  the opponent's block depth — a deep block blocks shots, and blocked shots
  are corners; game state (a trailing side wins corners without winning);
  wind argues down. **Goals ↔ corners ≈ 0**: a goal-heavy match is not a
  corner-heavy one.
- **Base:** 9.5 per match; over 8.5 in 61%, over 9.5 in 49%. Per team 4.77,
  over 4.5 in 48%.
- **Kill cases:** a team-corner OVER stacked with a total-corner UNDER without
  a tail test (Porto–Arouca 12–2 — one side can destroy the total alone); a
  sample mean far from the book's ladder centre (2.80 against 5.76 means the
  sample described a different team-state — look for `LADDER_DISAGREES`); one
  side's ten matches in a different competition class; a 1.40 price on a
  per-team 4.5, which asks 70% of a coin-flip market.
- **Half-match warning.** `corners_2h_*` has **62 matches** in the entire
  settled history, and its league baselines were 24–32% too high for two days.
  At n=8 the row is 76% league prior. Compute `n/(n+25)` and say it.

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
- **Base:** booking points ~4.38 per match; yellow-only 3.72 over 1,326
  observations. Per team yellow 1.86 (home 1.60 / away 2.11).
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
- **Rarely priced.** Four `fouls_total` rows on a 102-fixture board. Check the
  offer before spending analysis on it.
- **Drivers:** the referee's foul tolerance, the league (Süper Lig 27.9 against
  Bundesliga 20.7 — a league difference larger than most team differences),
  pressing and duel intensity, derby or knockout, and game state: a side
  protecting a lead fouls to stop transitions. Fouls run **against** goals
  (r ≈ −0.13).
- **Base:** 24.3 per match, over 20.5 in 75%. Per team 12.17, over 12.5 in 45%.
- **Estimand check:** `fouls_for(A) + fouls_for(B) ≈ fouls_total` mean. A large
  gap means the pooled and per-team samples describe different match sets.
- **Kill case:** the misses are the h2h — a pairing running 43/39/33 against a
  pooled 27.

## Shots and shots on target — `shots_*`, `shots_on_target_*`

- **Measures:** from `/statistics`. The raw field `totalShotsOnGoal` is **all
  shots** despite its name.
- **Superbet's ladders start high** (SOT from ~7.5, shots from ~24.5), so many
  of our rungs simply have no price.
- **Drivers:** attacking volume, opponent block, game state (a trailing side
  shoots more and worse), finishing regression, tempo. **SOT ↔ goals +0.55** —
  a SOT OVER and a goals OVER are one thesis, not two, and `confidence.py`
  enforces that by putting `shots` and `goals` in different quantity families
  but refusing builders whose legs disagree about tempo.
- **Base:** SOT 8.7 per match (over 6.5 in 73%); per team 4.35 (over 2.5 in 77%).
- **Kill cases:** a mean pulled by outliers against weak opposition (41–50 shots
  four times — the median still describes the fixture, so this is a caveat, not
  automatically a veto); a favourite that scores early and manages, which kills
  SOT-for in the second half.

## Goals — `goals_total`, `goals_for`, `goals_1h_*`, `goals_2h_*`

- **Measures:** off the score, so `n` runs ahead of every other market — every
  finished match has a score, far fewer have full statistics. Halves from the
  half-time score.
- **Extra time.** `EXTRA_TIME_STATUS_CODES = {110, 120}`. Superbet's
  "(z dogrywką)" markets and its 90-minute markets are different questions;
  check which one the rung is.
- **Halves:** first halves carry ~45% of goals, not 50%. `sofa`'s own
  half-versus-full coherence check reports goals halves inconsistent by −13%
  and −17%, because the half-match baselines are measured on a smaller
  population. Say so on any `goals_1h_*` / `goals_2h_*` row.
- **Kill cases:** a 0.5 OVER or 5.5 UNDER at 1.01–1.05 topping a sheet by hit
  rate — certainty for free is not a bet, and CONFIDENCE refuses anything under
  1.0867 for exactly that reason; a second leg whose aggregate changes who must
  score; a past-frequency streak read as an edge (devig the price first).

## Offsides — `offsides_total`, `offsides_for`

Driven by the high line of *one* side and the runners of the other. Thin
samples, high variance, and Superbet's ladder starts at 2.5. Four rows on the
Monday board. WATCH unless the matchup argument is specific.

## xG — `xg_total`, `xg_for`

Collected, absent for most competitions, and **not priced by Superbet**. Use it
as a regression argument against a shots or goals lean built on results. Do not
read an absent xG as zero.

## Derived markets — `both_over_*`, `most_*`, `handicap_*`

- **Not sampled.** They are functions of two sides, computed from
  `config/sofa_side_correlations.json`. Every such row carries
  `ONE_SIDED_LADDER` and `NO_MARKET_MARGINAL`.
- **Not calibratable.** 2–252 settled rows each; CONFIDENCE refuses them
  (`DERIVED_NOT_CALIBRATABLE`) so they can never be a builder leg.
- The measured correlation between the two teams' corners is **r = −0.279**.
  "Both over" intuition assumes the opposite sign.
- On the Monday board these were 1,024 of 5,674 rows (`DERIVED` note) —
  a fifth of the sheet, none of it stakeable as a leg. Report the two `*_for`
  rows and refuse the multiplication.

## Per-team markets in general — `*_for`

- Tonight's venue against the sample's own mix: eight away matches ahead of a
  home fixture is a thinner sample than `n=8` looks.
- **`h2h` never reaches a `*_for` row** — by design. A head-to-head is a fact
  about a pairing; `*_for` is a claim about one side.
- **No `*_against` metric exists.** Use the opponent's `*_for` and label it a
  proxy.

## Player props — `player_shots_for`, `player_shots_on_target_for`, `player_assists_for`

New 2026-09-22 (F54). Three metrics, read per player out of
`/event/{id}/lineups`, living on their own axis in `03_samples.json`
(`players`, keyed `"<metric>|<player as Superbet writes him>"`) rather than in
`metrics`. Everything else Superbet prices on a footballer — "strzeli gola",
"otrzyma kartkę", and the eight body-part and location variants of shots —
stays in `unmapped_markets`, because Sofascore reports none of those splits
and a yes/no proposition is not a rung on a ladder. Do not grade one of those.

**A player prop cannot reach the coupon, and you should not argue for one.**
Superbet quotes these on ONE side only — 437 "powyżej" and 0 "poniżej" on the
whole 2026-09-22 board — so `market_p` is `None`, `NO_PRICE_ANCHOR` fires and
the row stops at `LEAN`. That is the row being selected by our model with no
price checking it, which is the population the settled record calls the worst
one on the sheet. Read these as forecasts.

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
  shots are one quantity counted twice; `confidence.py` enforces this
  (`quantity_family`) but say so if you see it proposed.

## Bet Builders

`confidence.py` builds them and you do not. What you contribute per candidate
slip:

- a concrete scoreline or stat line that satisfies **every** leg at once, and
  whether that region is broad or an edge case;
- the shared mechanism, and the one scenario that kills every leg together;
- whether the legs really are different quantities (a team's goals and the
  match total are the same quantity — measured lambda 2.165);
- whether the price the operator can see on the screen beats
  `odds_after_haircut`. If he has the screen price, it wins outright over the
  12% estimate.

**Never print a combined price of your own.** Prefer mechanism 1 + mechanism 2
over the same market three times.
