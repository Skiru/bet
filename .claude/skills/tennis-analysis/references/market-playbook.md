# Tennis market playbook — drivers, scoreline arithmetic, kill cases

> **Since 2026-10-07 10:55Z (`epochs.LINE_EVIDENCE_FROM_UTC`)** the refusals BY NAME below (`DERIVED_NOT_CALIBRATABLE`, `OPERATOR_REFUSED` / `refused_markets`, `PLAYER_PROP_NOT_ADMITTED`, `TENNIS_SET_MARKET_NOT_ADMITTED`, a sport key outside `admitted`) describe the old epoch only: every market is now read through its own settled Superbet lines (`bet.sofa.line_evidence`), and one with no measurement is `NO_LINE_EVIDENCE`. See `.claude/skills/sofa-pipeline/SKILL.md`, "The 2026-10-07 rules".

Every market here is a function of **match length**. That is the single
mechanism, and it is why a tennis slip of two UNDERs is one bet charged twice
— `confidence.py` puts `games_*`, `sets_*` and `handicap_games` in one quantity
family for exactly that reason.

## `games_total` — total games in the match

- **Drivers:** both players' hold percentage (two big servers produce long
  close sets *and* fast ones — the variance is the point), return strength,
  surface speed, format.
- **Arithmetic:** `6-3 6-4` = 19. `6-4 6-4` = 20. `6-4 7-5` = 22.
  `7-6 6-4` = 23. `7-6 6-7 7-6` = 39. A best-of-three straight-sets match is
  typically 17–23; a third set adds **12–15**.
- **The tail is one-sided and enormous.** The distance from the modal
  straight-sets outcome to a three-set outcome is bigger than anything else in
  the sample, so an OVER's upside and an UNDER's downside are not symmetric.
- **Priced by** (from 2026-10-07 14:05Z) 0.5 x the rating's 600 neighbours +
  0.5 x the NB count model on the sample; `forecast_p` is the rating alone, so
  `p_central` sits between the sample's NB and `forecast_p`.
- **Kill cases:** a sample mixing surfaces (a generic "Hard" label matches
  indoor and outdoor); a sample of a player who has since changed level; an
  UNDER whose modal scoreline lands exactly on the line; a match decided by a
  10-point match tiebreak (code: one game, Superbet's count unverified).

## `games_won_for` — one player's games

**Read `data-inventory.md` on this market before grading one.** It is the
largest tennis family on the board (3,014 of 17,744 tennis rows on the
2026-10-07 sheet; 333 of the 391 tennis singles of that day's coupon) and the
one whose estimator changed on 2026-10-07 14:05Z.

- **Bimodal by construction.** A straight-sets winner has ≥ 12 games; a loser
  is spread over 0–11. One day's 570 observations: 10:17, 11:10, **12:159**,
  13:84.
- **Superbet's line is 11.5 — in the trough**, between the loser mode and the
  wall.
- Priced, from 2026-10-07 14:05Z, by the **rating's neighbours alone** (the
  600 historical best-of-three matches nearest in match-win probability;
  no price, no sample): `p_central == forecast_p`. The player's own record is
  the independent number - próbka k/n. Where the rating does not read the
  fixture (best-of-five; a player with under 10 rated matches) the sample's
  empirical frequency around the shrunk centre prices it and `forecast_p` is
  null. Older rows: the sample, and before 2026-10-05 pulled onto the price
  (`TENNIS_RATING` 0.25·rating + 0.75·`market_p`; `P_SHRUNK_TO_PRICE`
  w·hits/n + (1−w)·`market_p`, w = n/(n+30)).
- **Trust it least on a confident row.** The old frequency estimator claimed
  0.95 and realised 0.728 (9,286 settled rows, 2026-09-21); the current curve
  (history replay of the rating, refit 2026-10-07) reaches the 0.950-1.010
  bucket, but the 2026-10-05/06 Superbet lines realised 0.17 (OVER) / 0.12
  (UNDER) below confidence on printable legs under the older estimator, and
  no settled line yet belongs to the rating-priced one.
- **Arithmetic:** in `6-2 6-3` the loser has 5 games. In `6-4 6-4`, 8. In
  `7-6 6-7 7-6`, 19. With a 10-point match tiebreak (`6-4 3-6 10-7`) the
  winner has 10 games by the code's convention (one game for the tiebreak),
  9 if Superbet counts none - an open operator question.
- **Kill case:** a mode of 12 built against much weaker fields, priced against
  a far stronger opponent tonight.

## `sets_total`

- **Bounded:** 2 or 3 on a best-of-three, 3/4/5 on a best-of-five. Priced by
  the sample's empirical frequency (no price) because a bell curve over two
  bars is the wrong model (error +16.0 pp → +4.0 pp when the floor was
  removed); `forecast_p` is the rating's and is a separate estimator here. The
  rating only reads best-of-three.
- **`default_period_count` decides everything.** A BO3 sample priced against a
  BO5 event is a tautology sold at 2.40, and a null here means the format scope
  did not run.
- `UNDER 3.5` on a best-of-three is a tautology. Never lead with one.
- Thin: the 2026-10-07 curve has `by_market.sets_total` buckets only up to
  0.600-0.700 (2,919 replayed rows) and a UNDER-only thin curve; a high
  `p_central` here reads the key's own Superbet lines or `NO_LINE_EVIDENCE`.

## `aces_total` / `aces_for`, `double_faults_total` / `double_faults_for`

- **Drivers:** serve speed and placement, surface and ball, altitude, the
  returner's court position, and above all **match length** — more service
  games is more of everything.
- **Aces ≠ tie-breaks, and a big serve does not mean over games.** A dominant
  server holds quickly, which shortens the match.
- Double faults rise with pressure and with second-serve aggression; they are
  the noisier of the two.
- **Kill cases:** a grass sample on a hard court (medians 9.0/11.0 against
  6.0/5.0) where `ground_type` was null; a total whose split shows one side at
  zero after scoping — that is one player's history, not a total.
- Ladders for `aces_*` were **0% checkable** (2026-09 measurement), so
  `NO_LADDER_CHECK` on these rows is the norm, not a passed test.

## `serve_points_*`

Almost purely a length market wearing a serve name: more games is more serve
points. Grade it as `games_total` with extra variance, and never treat it as an
independent second leg alongside a games market. Its own curve is thin and
September's measurement was bad (`serve_points_for` 15/31 realised against
0.78 claimed); it goes through line evidence like the rest.

## Per-set markets — `*_set1_*`, `*_set2_*`

Set 1 and set 2 only. Thin, and a `set2` market does not exist if the match
ends in straight sets in a way the book voids — **check the settlement rule
before grading one**. Small counts of rows on any board.

## `games_won_set{1,2,3}_for` — one player's games in ONE set

New 2026-09-22 (F54), and the biggest per-player family on the tennis board:
**827 priced markets across 166 fixtures** in one day, all of which used to
land in `unmapped_markets`. Superbet writes it
`"1. set - Kenta Kawada liczba gemów"` and quotes it **two-sided**, so unlike
football's player props it devigs, clears the ladder gate and can be staked.

The value comes off the **set score in the listing**, not `/statistics`, so a
row exists wherever the match history does.

What to check, in this order:

- **The line is almost always 5.5, and 5.5 is a cliff.** Measured over 80,149
  cached matches, a player's games in a set run 4 → 10.8%, **5 → 4.4%**,
  **6 → 45.6%**. Five is only reachable as the loser of a 7-5. So `p_central`
  here moves in big steps and a one-observation change in a ten-match sample
  moves it 10 points. Treat 0.6 and 0.7 as the same claim.
- **Set 3 is conditional and the sample is short.** A `set3` row only settles
  if the match reaches a third set — the book voids it otherwise — and the
  sample is only the player's three-set matches, typically 4-5 observations
  against 10 for set 1. Check `sample_size` before anything else.
- **Set 1 and set 2 are not independent of the match total.** They share the
  `games` quantity family, so a builder takes one of them, not both, and not
  alongside `games_total` or `games_won_for`.
- **A set line is a scoreline claim.** "Over 5.5 games in set 1" is "wins the
  set, or loses it 7-5 / 6-7" — run the scoreline arithmetic the way you would
  for `games_won_for`, but over one set.

## `tiebreaks_total`

Collected as a **non-count** (`NORMAL_NON_COUNT_METRICS`: a normal CDF
without a Poisson floor). CONFIDENCE no longer refuses it by name
(`NOT_IN_CALIBRATION_FIT` was the pre-2026-09-23 rule); it has a thin
`by_market_direction` curve (OVER only) and goes through line evidence. The
rating reads it off the neighbours but SHEET does not price it with them (the
rating was worse on 52 settled rows, 2026-09). It sits in the `games`
quantity family.

## Derived — `most_aces`, `most_games`, `most_serve_points`, `handicap_games`

- Functions of two sides (`config/sofa_side_correlations.json`), **not
  sampled** (`derived.py`). Where the per-side ladders are not quoted a row
  may carry `ONE_SIDED_LADDER` / `NO_MARKET_MARGINAL` (not every row does).
- **From 2026-10-07 14:05Z `handicap_games` and `most_games` (not the draw)
  are priced by the rating's neighbours alone** (`rating_p` in `derived.py`):
  the side's margin over the 600 nearest best-of-three matches. They carry no
  `forecast_p` (verified on the 2026-10-07 sheet: none of 1,674 rows).
  Where the rating does not read the fixture, the joint of the two samples
  prices them. `most_aces`, `most_serve_points` stay on the joint.
- CONFIDENCE: before 2026-10-07 10:55Z these were refused
  `DERIVED_NOT_CALIBRATABLE`. Now a derived market reads **only its own
  Superbet lines** (no history curve: `derived_curves` is off), so it is
  `NO_LINE_EVIDENCE` until a key has enough lines (`min_evidence_games`); the
  2026-10-07 coupon holds no `handicap_games` or `most_*` single.
- `handicap_games` is in the `games` quantity family, so it competes with
  `games_total` and `games_won_for` for the one slot a builder allows.

## Tennis Bet Builders

Two legs on one tennis match are almost always **one bet**: sets, games, aces,
double faults and serve points all resolve through match length, and a short
match settles every UNDER at once. `confidence.py`'s quantity families stop the
worst of it, but `aces` and `double_faults` are separate families from `games`
and will combine. Say plainly when they share the mechanism anyway.

Tennis length markets were measured overconfident by ~25 pp on 2026-09-06
under the old estimator; the curves were refitted on 2026-10-07 and line
evidence lowers what the settled lines still show below confidence. Carry
that into every tennis read.
