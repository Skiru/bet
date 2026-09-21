# Tennis market playbook — drivers, scoreline arithmetic, kill cases

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
- **Kill cases:** a sample mixing surfaces because `ground_type` was null; a
  sample of a player who has since changed level; an UNDER whose modal
  scoreline lands exactly on the line.

## `games_won_for` — one player's games

**Read `data-inventory.md` on this market before grading one.** It is 1,084 of
3,026 tennis rows on a Monday board and it is the most dangerous market here.

- **Bimodal by construction.** A straight-sets winner has ≥ 12 games; a loser
  is spread over 0–11. One day's 570 observations: 10:17, 11:10, **12:159**,
  13:84.
- **Superbet's line is 11.5 — in the trough**, between the loser mode and the
  wall.
- Priced by the **sample's own frequency**, so `p_central` equals the hit rate.
- **The frequency is overconfident at the top:** a claimed 0.95 realises 0.728
  over 9,286 settled rows, and the market has no measured bucket above 0.825.
  A confident `games_won_for` row is the number to trust least on the sheet.
- **Arithmetic:** in `6-2 6-3` the loser has 5 games. In `6-4 6-4`, 8. In
  `7-6 6-7 7-6`, 19.
- **Kill case:** a mode of 12 built against much weaker fields, priced against
  a far stronger opponent tonight.

## `sets_total`

- **Bounded:** 2 or 3 on a best-of-three, 3/4/5 on a best-of-five. Priced by
  empirical frequency because a bell curve over two bars is the wrong model
  (error +16.0 pp → +4.0 pp when the floor was removed).
- **`default_period_count` decides everything.** A BO3 sample priced against a
  BO5 event is a tautology sold at 2.40, and a null here means the format scope
  did not run.
- `UNDER 3.5` on a best-of-three is a tautology. Never lead with one.
- Only **202** settled rows, so it has no market curve of its own and falls to
  the tennis pool.

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
- Ladders for `aces_*` were **0% checkable**, so `NO_LADDER_CHECK` on these
  rows is the norm, not a passed test.

## `serve_points_*`

Almost purely a length market wearing a serve name: more games is more serve
points. Grade it as `games_total` with extra variance, and never treat it as an
independent second leg alongside a games market.

## Per-set markets — `*_set1_*`, `*_set2_*`

Set 1 and set 2 only. Thin, and a `set2` market does not exist if the match
ends in straight sets in a way the book voids — **check the settlement rule
before grading one**. Small counts of rows on any board.

## `tiebreaks_total`

Collected and classified **non-count**, so CONFIDENCE refuses it
(`NOT_IN_CALIBRATION_FIT`). It can never be a builder leg. Treat it as
reporting only.

## Derived — `most_aces`, `most_games`, `most_serve_points`, `handicap_games`

- Functions of two sides, computed from `config/sofa_side_correlations.json`,
  **not sampled**. Every such row carries `ONE_SIDED_LADDER` and
  `NO_MARKET_MARGINAL`.
- `most_*` are refused by CONFIDENCE (`DERIVED_NOT_CALIBRATABLE`) and can never
  be a leg.
- `handicap_games` is **not** in the derived-prefix ban but **is** in the
  `games` quantity family, so it competes with `games_total` and
  `games_won_for` for the one slot a builder allows. It was 581 rows on a
  Monday board — a large, weakly-checked part of the tennis sheet.

## Tennis Bet Builders

Two legs on one tennis match are almost always **one bet**: sets, games, aces,
double faults and serve points all resolve through match length, and a short
match settles every UNDER at once. `confidence.py`'s quantity families stop the
worst of it, but `aces` and `double_faults` are separate families from `games`
and will combine. Say plainly when they share the mechanism anyway.

Tennis length markets were measured overconfident by ~25 pp on 2026-09-06 and
deliberately left uncorrected, because the fix risked overfitting. Carry that
into every tennis read.
