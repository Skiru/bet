# Tennis market playbook - drivers, scoreline arithmetic, kill cases

Every market here is a function of **match length** - the one mechanism,
and why two UNDERs of one match are one bet charged twice. Which estimator
prices each market: SKILL.md and `data-inventory.md`.

## `games_total`

- **Drivers:** both players' hold % (two big servers give long close sets
  *and* fast ones), return strength, surface speed, format.
- **Arithmetic:** `6-3 6-4` = 19, `6-4 6-4` = 20, `6-4 7-5` = 22, `7-6 6-4` =
  23, `7-6 6-7 7-6` = 39. A best-of-three straight-sets match runs 17-23; a
  third set adds **12-15**: the tail is one-sided and enormous.
- **Priced by** half the rating's neighbours, half the NB on the sample;
  `forecast_p` is the rating alone, so `p_central` sits between them.
- **Kill cases:** a sample mixing surfaces; a player who has changed level;
  an UNDER whose modal scoreline lands on the line; a match tiebreak deciding
  the count (code one game, Superbet unverified).

## `games_won_for` - one player's games

- **Bimodal by construction:** a straight-sets winner has >= 12, a loser
  0-11; the line is usually 11.5, in the trough.
- Priced by the neighbours alone (`p_central == forecast_p`); the player's own
  record is the independent number (próbka).
- **Arithmetic:** the loser of `6-2 6-3` has 5; of `6-4 6-4`, 8; of
  `7-6 6-7 7-6`, 19. With `6-4 3-6 10-7` the winner has 10 by the code's
  convention, 9 if Superbet counts none.
- **Kill case:** a mode of 12 built against much weaker fields, tonight
  against a far stronger opponent.

## Per-set games - `games_set1/2_total`, `games_won_set1/2/3_for`

- Priced by the neighbours (set three from the neighbours that played one:
  Superbet voids the market when the set is not played).
- **The line is usually 5.5, and 5.5 is a cliff:** a player's games in a set
  run 4 -> 10.8%, **5 -> 4.4%**, **6 -> 45.6%** (80,149 cached matches). Five is
  reachable only as the loser of a 7-5. A set line is a scoreline claim:
  "over 5.5 in set 1" = wins the set, or loses it 7-5 / 6-7.
- They share the games builder family with every other games market.
- Per-player set games OVER realised below confidence on the printed legs of
  10-09..10-16 (-7.1 / -6.6 pp, intervals touching zero; open check
  `T-TENNIS-SET-GAMES-OVER`) - a note, never a WATCH.

## `sets_total`

Bounded: 2 or 3 on a best of three. Priced by the neighbours; SHEET refuses
it on a match not known to be best of three. `UNDER 3.5` on a best of three is
a tautology - never lead with one.

## `match_won_for`, `set1_won_for`, `set2_won_for`, `set_score`

The rating alone ("Zwycięzca", "X. set - zwycięzca", "Dokładny wynik"), no
sample. Judge the match: form, fitness, surface, a retirement-prone player
(a retirement is a refund for the winner market too).

## `set_score_not` - "he wins at least a set"

Subject "<player> 0:2", OVER = that player does NOT lose 0:2 - Superbet's
"<player> wygra seta" Tak, "Handicap setowy" "<player> (1.5)", "<player>
liczba setów" powyżej 0.5, "<other> wygra bez straty seta" Nie (one rung).
Priced as 1 - the 0:2 share of the neighbours (best of three only); women
read the `tennis_women:` curve. The risk
is a one-sided match: a big rating gap, an out-of-form or retirement-prone
underdog, a surface that kills his serve. Its legs realised below confidence
on 10-14..10-15 (27 legs, interval through zero; open check
`T-SCORE-MARKETS-superbet`) - a note, never a WATCH.

## Aces, double faults - `aces_*`, `double_faults_*`

- **Drivers:** serve speed and placement, surface and ball, altitude, the
  returner's position, and above all **match length** - more service games
  is more of everything. A dominant server holds quickly, which shortens the
  match. Double faults rise with pressure and second-serve aggression, and
  are the noisier of the two.
- Priced from the server's own scoped sample toward the tier prior; **the
  returner never enters the number** (a returner correction was measured and
  kept off). On Superbet's lines the history curve at >= 0.70 overstated
  (-22.6 pp, 140 lines / 43 matches, 10-06..10-16); line evidence holds most
  back, so what prints is short prices. Read such a leg against the returner
  (return points won, how many aces his opponents serve).
- Per-set aces / double faults and aces + double faults (`serve_points*`):
  their installed curves hold only a 0.000-0.600 bucket (no 0.70), so they
  do not print until their own lines settle.
- **Kill cases:** a grass sample on a hard court (medians 9.0 / 11.0 vs
  6.0 / 5.0); a total whose split shows one side at zero after scoping.
  `NO_LADDER_CHECK` on these rows is the norm, not a passed test.

## `serve_points_*`

A length market wearing a serve name: grade it as `games_total` with extra
variance, never as an independent second leg beside a games market.

## `tiebreaks_total`

A non-count (normal CDF without a Poisson floor), on the sample; a thin curve
of its own, read through line evidence. In the games builder family.
Tie-break probability is a function of both hold rates on this surface, not
of ace counts.

## Derived - `most_*`, `handicap_*`

Functions of two sides (`config/sofa_side_correlations.json`), not sampled.
`handicap_games` and `most_games` (not the draw) are priced by the
neighbours, and from 2026-10-28 so is the per-set games handicap
(`handicap_games_won_set1/2`, the neighbours' own set-N margin, note
`SET_HANDICAP_NEIGHBOURS`; earlier a rho-0 joint that put ~0.26 on a level
set margin that never happens); `most_aces`, `most_serve_points`, `handicap_aces` by the joint of
the two samples. With no history curve a derived key reads its own Superbet
lines or is `NO_LINE_EVIDENCE`. `handicap_games` competes with `games_total`
and `games_won_for` for the one games slot a builder allows.

## Tennis Bet Builders

Two legs of one match are almost always one bet: sets, games, aces, double
faults and serve points all resolve through match length, and a short match
settles every UNDER at once. The quantity families stop the worst of it, but
aces and double faults are separate families from games and will combine -
say plainly when they share the mechanism anyway. Never state a builder price.
