# Football market playbook - drivers, base rates, kill cases

Per market: what `sofa` measures, what moves it, an order-of-magnitude base
rate (global means of `config/sofa_league_baselines.json` at the 2026-10-07
fit - never a prior you may substitute for `centre`; leagues differ more than
most teams), the kill cases, and what a good read says. The count of every
market is priced by a negative binomial with a fitted dispersion
(`shots_total`: a normal); which centre terms apply is on the row.

## Corners - `corners_total`, `corners_for`, `corners_1h_*`, `corners_2h_*`

- **Drivers:** attacking volume and width (crosses, full-backs); the
  opponent's block depth (blocked shots become corners); game state (a
  trailing side wins corners without winning); wind down. Goals and corners
  are ~uncorrelated.
- **Base:** ~9.5 per match, ~4.8 per team. `corners_total` and the half
  totals are unrated (sample centre only); the side markets are rated.
- **Kill cases:** a team-corner OVER with a total-corner UNDER without a tail
  test (12-2); a sample mean far from the book's ladder centre (2.80 vs 5.76,
  `LADDER_DISAGREES`); one side's ten matches in another competition class.
- Half rows: state `w_c` - half baselines rest on small populations.

## Cards - `cards_points_total`, `cards_points_for`

- **Measures:** booking points (yellow 1, red 2, second yellow 3), not cards.
- **Drivers, in order:** the referee (a third of a line between officials of
  one league; apparent home bias in cards is referee behaviour), fouls
  volume, stakes (derby, knockout, relegation), game state (0-0 late in a
  knockout), each side's discipline, red-card propensity (+2 / +3 at once).
- **Base:** ~4.5 points per match, ~2.25 per team. K = 25 for
  `cards_points_for` (the sample owns little of a thin row).
- The referee is not in the centre and is usually absent: it is entirely
  your contribution, and its absence is normal, not a defect.
- **Kill cases:** no referee in a high-spread league on a tight line; a line
  on the mode; a red in a derby second leg; an official with 3-4 matches
  behind his rate; an UNDER in a tie that can go to extra time.

## Fouls - `fouls_total`, `fouls_for`, `fouls_1h_*`

- **Drivers:** the referee's tolerance, the league (league means differ more
  than teams), pressing and duel intensity, derby or knockout, game state (a
  side protecting a lead fouls to stop transitions). Fouls run mildly against
  goals.
- **Base:** ~24.7 per match, ~12.4 per team. K = 2 for `fouls_total` (almost
  all league prior).
- **Estimand check:** `fouls_for(A) + fouls_for(B)` vs `fouls_total`'s mean -
  a gap means two different match sets.
- **Kill case:** the misses are the h2h (a pairing at 43 / 39 / 33 against a
  pooled 27).

## Shots and shots on target - `shots_*`, `shots_on_target_*`

- The raw field `totalShotsOnGoal` is all shots.
- **Drivers:** attacking volume, opponent block, game state (a trailing side
  shoots more and worse), tempo, finishing regression. SOT and goals are
  strongly positive: a SOT OVER and a goals OVER are one thesis.
- **Base:** SOT ~8.6 per match (~4.4 per team); shots ~24.7 (~12.4).
- **Kill cases:** a mean pulled by outliers against weak opposition (a
  caveat, not automatically a veto); a favourite that scores early and
  manages, killing its second-half SOT.

## Goals - `goals_total`, `goals_for`, `goals_1h_*`, `goals_2h_*`

- Off the score, so `n` runs ahead of every other market. Settled at 90
  minutes; Superbet's "(z dogrywką)" markets are a different question.
- First halves carry ~45% of goals. For a league fixture the sample is the
  side's REGULAR matches of the same competition (five or more).
- **Kill cases:** a 0.5 OVER / 5.5 UNDER at 1.01-1.05 topping a list by hit
  rate; a second leg whose aggregate changes who must score; a streak read
  as an edge; a placeholder 0-0 (forfeit) in the sample.

## Offsides - `offsides_total`, `offsides_for`

Driven by one side's high line and the other's runners. Thin samples, high
variance - a note in the section; a removal needs what any removal needs
(a dated fact or a `DEFEKT:`, core).

## Saves, throw-ins, goal kicks, tackles

Unrated, zeros often untracked (data inventory): check the sample for gaps
before trusting a low mean. Saves follow the opponent's shots on target and
the keeper in goal tonight, which nothing on disk names (a changed keeper is
a CONTEXT veto).

## xG

Not priced by Superbet; absent for most competitions. Use it only as a
regression argument against a shots or goals lean built on results.

## Score markets and rating-only markets

Priced from the pure rating's goals centres on the double chance's NB grid
(`bet.sofa.football_score_markets`): no sample, no próbka, no
`MODEL_ABOVE_OWN_SAMPLE`. OVER = Superbet's "Tak" / the selection as written;
subject `1` home, `X` draw, `2` away; the line is the goals line (0.5 for
yes / no). Settled on the 90-minute score.

| market (subject, line) | Superbet | wins when |
|---|---|---|
| `result_or_over` (S, L) | "Mecz lub liczba goli (L)" "<S> lub powyżej L"; "<S> wygra lub powyżej X goli w meczu" Tak | S, or more than L goals |
| `result_or_under` (S, L) | "... lub poniżej L" | S, or fewer than L goals |
| `btts_or_over` (-, L) | "Obie drużyny strzelą gola lub powyżej L gola" Tak | both score, or more than L goals |
| `result_or_btts` (S, 0.5) | "<S> wygra lub obie drużyny strzelą gola" Tak | S, or both score |
| `result_or_clean_sheet` (S, 0.5) | "... lub którakolwiek drużyna zachowa czyste konto" Tak | S, or either side scores none |
| `result_handicap` (side, L) | "Handicap" "<team> (L)", +1.5 / +2.5 / +3.5 | that side's goals + L beat the other's |
| `dc_and_over` ("12", L) / `dc_and_under` ("1X", L) | "Podwójna szansa & liczba goli (L)" | no draw and over L / home not losing and under L |
| `double_chance`, `draw_no_bet`, `result_1x2` | "Podwójna szansa", "Zakład bez remisu", "Mecz" | DNB: a draw is a refund |
| `first_goal` | "1. gol" | that side scores first |
| `red_cards_total`, `penalties_total` | "Liczba czerwonych kartek", "Liczba przyznanych rzutów karnych" | regular-time incidents |

The game script decides them: a 0-0 / 1-0 grind kills `result_or_over` X, a
rout kills the underdog's `result_handicap`. Several rungs of one match are
not grouped as a ladder on the PDF - one script kills them together; say so.
An early-phase men's match reads `season_early:` curves. A rung quoted OVER
only prints as a one-sided single.

## Player props - `player_*_for`

Shots, shots on target, fouls, tackles, assists, offsides (lineup
statistics), plus the shot-detail markets (outside the box, headed, left /
right foot) counted from `/shotmap`. Subject = the player as Superbet writes
him; the sample sits in `03_samples.json` `players["<market>|<subject>"]`.

- **The bet voids unless he starts** (a non-start is a refund). So "will he
  start?" is not the risk; what happens once he starts is: an early
  substitution (a return from injury on a minutes limit, a booked defender
  taken off at half-time, a planned change in a congested week), a changed
  role or position, a red card.
- **The sample is his starts** (`appearances: "starts"`, note
  `PLAYER_STARTS_ONLY`) in his team's recent matches. Read `PLAYER_MINUTES`
  (median minutes, starts of 60'+, matches played of those sampled): 90'
  starts and 60' starts are different quantities. A short sample of a new
  signing has no note saying why - compare `sample_size` with
  `squad_matches`. From 2026-10-24 a `THIN_SAMPLE` gap whose detail starts
  `PLAYER_HISTORY_ANY_TEAM` means the sample also holds his starts for other
  teams (by player id): their opponent / venue are the other team's and
  `squad_matches` counts only his current side - read the gap's N first.
- **Identity** is a name match: `match_rule` `tokens` (`PLAYER_NAME_TOKENS`,
  Superbet's full registered name matched by whole tokens) `surname`
  (`PLAYER_NAME_SURNAME`), `transliteration`, `inner_surname` or, from
  2026-10-24, `slug` (his Sofascore slug holds exactly Superbet's name tokens). Check that `matched_name` is the same person (club,
  position) and say how you know. Sofascore spells names with their own
  letters ("Wålemark", "Khlan" for Chłań) - search both spellings.
- **Per leg check:** the expected lineup (club / league page within ~1 h of
  kickoff, else two domains); role and position vs the sample; penalties and
  set pieces (shots); the opponent's style (a low block concedes shots, a
  possession side concedes few tackles); the referee (fouls); a manager
  change inside the sample; minutes limits after injury.
- **Verdicts:** an expected early substitution or a role change the sample
  does not contain (on a dated source), or an identity you cannot confirm
  (`DEFEKT:`), is WATCH. A doubtful
  start alone is not a reason. "Props never pay" is not a read.
- **On the coupon** a player leg prints as a one-sided single (no UNDER
  side, so no margin; `one_sided_market`, "1-str." on the PDF) when its
  confidence is its own market's curve with n >= 300. A leg carrying
  `player_sample_rule` printed on 5-9 starts or an always-over sample (a
  lifted shape gate) and is never in a builder - its shape is yours to read.
- Never pair a player's shots with his team's shots (one quantity counted
  twice); an assist belongs to the goals family.

## Derived joints - `both_over_*`, `most_*`, `handicap_*`

Functions of two sides' marginals and a measured side correlation
(`config/sofa_side_correlations.json`; corners residual r = -0.145, goals
~0), not sampled; no history curve (derived curves are off), so confidence
is the Wilson bound of the key's own settled Superbet lines, else
`NO_LINE_EVIDENCE`. The sheet notes say how far the market checked the row
(`NO_MARKET_MARGINAL`, `ONE_SIDED_LADDER`, `MARGINAL_DISAGREEMENT`). If one
is in your file, report the two `*_for` rows and refuse the multiplication.

## Per-team markets in general - `*_for`

- Tonight's venue vs the sample's mix: eight away matches ahead of a home
  fixture is a thinner sample than n=8 looks.
- `h2h` never reaches a `*_for` row. What the opponent concedes is its own
  observations' `against`; the rating's defence ratio and the opponent
  correction (`opponent_rule`) are the built-in adjustments.

## Bet Builders

`run_confidence.py` builds them (one per fixture, the best
`combined_probability`, at most one leg per quantity family, legs coherent in
tempo). Your contribution per builder: a concrete scoreline or stat line that
satisfies every leg at once and whether that region is broad; the shared
mechanism and the one scenario that kills every leg; whether the legs are
really different quantities. The price is not yours: the operator reads it
off Superbet's screen - never quote `fair_odds`, `odds_after_haircut` or an EV.
