# Tennis market playbook — drivers, scoreline arithmetic, kill cases

Every market below is a function of match length, so first decide the match:
**format** (BO3/BO5), **surface**, **favourite strength** (book's match odds),
**hold profile** of both (web), **fatigue asymmetry**. Then read the rows.

## Scoreline arithmetic (memorise)

| Scoreline | games | winner's games | loser's games |
|---|---|---|---|
| 6-0 6-0 | 12 | 12 | 0 |
| 6-2 6-3 | 17 | 12 | 5 |
| 6-3 6-4 | 19 | 12 | 7 |
| 6-4 6-4 | 20 | 12 | 8 |
| 7-5 6-4 | 22 | 13 | 9 |
| 7-6 6-4 | 23 | 13 | 10 |
| 7-6 7-6 | 26 | 14 | 12 |
| 6-3 3-6 6-4 | 28 | 15 | 13 |
| 6-4 4-6 6-4 | 30 | 16 | 14 |
| 7-6 6-7 7-6 | 39 | 20 | 19 |

BO5 adds 12–26 games per extra set pair; 3-0 in BO5 is 36–39 games at the
tightest, 18 at 6-0 6-0 6-0.

## Total games (`total_games`)

- **Measures:** games in the match, framed as own + own from each side's
  scoped `games_won`-type history (centre) with the pooled buckets for hits.
- **Drivers:** both hold rates on this surface (high+high ⇒ 7-6s and 20+;
  high+low ⇒ 6-3 6-4 ≈ 19; low+low ⇒ breaks, possibly three sets ⇒ 28+),
  favourite strength (a 1.20 favourite ⇒ modal 6-3 6-4), competitiveness of
  the sample's opposition, format.
- **Ladder:** Superbet 12.5–36.5. The sheet's rung is one of many — read the
  whole ladder; BO3 rungs of interest are 18.5–23.5, BO5 27.5–36.5.
- **Kill cases:** an OVER on a mean of 22.5 with median 19.5 (three-setters
  carry the mean); an OVER 16.5 at 1.04–1.14 (certainty, not value); a sample
  whose 20+ matches were all against peers while tonight is a 1.15 favourite;
  fatigue asymmetry (one side played 3h yesterday) on a competitiveness OVER;
  a retirement risk (void).
- **Good read:** "hold ~84%/~78% na twardym [WEB]; faworytka 1.30 ⇒ modalny
  6-3 6-4 = 19; O18.5 przeżywa A/B/C/D, O20.5 tylko B/D; 20.5 leży na modzie
  próby (6 z 14 obserwacji 19–21)".

## Total sets (`total_sets`)

- **Measures:** 2 or 3 (BO3) / 3–5 (BO5). **Pooled centre still** (no
  per-player sets metric) — a `total_sets` row is the one tennis total not
  framed own+own; say so.
- **Drivers:** favourite strength above all; closeness of hold rates; both
  players' three-set rates on this surface (web); fatigue.
- **Rungs:** 2.5 in BO3 (`OVER` = three sets, base ~35% ATP / ~33% WTA — check
  the sample's own three-set share); 3.5/4.5 in BO5.
- **Kill cases:** UNDER 3.5 in BO3 (tautology — the format gate should have
  removed it); OVER 2.5 on a 1.15 favourite's sample of competitive matches;
  a `total_sets` row leading the sheet on `p_low` alone.

## Player games won (`games_won`)

- **Measures:** one player's own games. Conditional on nothing about the
  opponent. Per-player bucket only.
- **Drivers:** the player's hold rate vs tonight's opponent's return; whether
  the player wins (winner's games ≥ 12 in straight sets; loser's 0–12);
  three-set probability (adds 4–7).
- **Ladder:** 2.5–23.5 per player. The **underdog's** games line is the
  sharpest read in tennis: `UNDER 9.5` for a 4.00 underdog means "straight
  sets with at most 6-4 6-4 or 6-3 6-4 plus change" — write the scorelines.
- **Kill cases:** the Tagger case — mode 12 built against WTA-125 fields,
  facing a slam finalist; identical `p_low` on 7.5/8.5/9.5; sample of nine
  with one three-set outlier at 19 carrying the mean; a `games_won` row on
  the wrong player (check `team_name`).
- **Good read:** classify each sample opponent (rank band) and tonight's;
  state the modal scoreline per scenario and the player's games in it.

## Aces (`aces_total`, `aces_for`)

- **Measures:** aces; framed own+own for the total.
- **Drivers:** serve quality on **this surface** (grass ≫ hard ≫ clay), the
  opponent's return quality (aces are conceded as much as served), match
  length (more games ⇒ more aces — a three-setter can double a count), height
  and first-serve % (`first_serve_pct` in the dossier), conditions (altitude,
  balls, wind — web).
- **Kill cases:** Boulter–Muchová (grass sample on hard); Oliynykova–Eala
  (pooled 5.23 vs own+own 2.25); an OVER built on a mean the three-setters
  made; an UNDER ignoring that a long match is the modal scenario for two big
  servers; `aces_for` 0.5/1.5 UNDER at 1.1 (certainty, not value).
- **Good read:** each player's hard-court aces per match (median, not mean),
  opponent's return rank, expected games from the total_games read, then the
  rung: aces scale with games.

## Double faults (`double_faults_total`, `double_faults_for`)

- **Measures:** DFs; framed own+own for the total.
- **Drivers:** second-serve risk appetite, return pressure from the opponent
  (a punishing returner induces DFs), nerves in a tight match (DFs cluster at
  6-6 and in deciders), match length, surface (clay lengthens matches ⇒ more
  DFs per match even with fewer per game).
- **Kill cases:** Badosa–Gauff (one side scoped to zero, n=9 was one player);
  an UNDER a half-point above a one-sided sample's maximum; a player whose
  own sample is clay-only (`[4,4,6,6,6,7,9,10,12]`) priced on hard; a
  notoriously DF-prone player (some top players average 5+) on the other side.
- **Good read:** both players' on-surface DF medians, sum, compare with the
  rung; the one direct meeting's count; the returner's pressure profile.

## What is *not* on the sheet and must not be inferred

First-set games, first-set winner, set betting, tie-break yes/no, break
counts, match winner. Method §83 forbids "strong overall form ⇒ first-set
over"; the data is not collected, so any such read is invention. If the
operator asks, say the market is not priced here and why.

## Tennis Bet Builder (method §76, §91–§93, §114)

`bet_builder_draft.py` marks any two length legs `correlation_risk HIGH`
(sets, games, aces, DFs move together). By hand: a concrete scoreline that
satisfies every leg (`7-6 6-4`: 23 games, winner 13, loser 10 — does it pass
O21.5 + winner O12.5 + loser U10.5? yes; `6-3 6-4` fails the winner's 12.5),
the breadth of the common region (`ROBUST / MODERATE / FRAGILE`), the one
scenario that kills all legs (a 6-2 6-2 rout, or a retirement), and the
fragility grade. Preferred constructions (§114) pair a set/player thesis
with a games thesis that *share the modal scenario*; never
winner + unrelated prop + unrelated prop. Never a combined price.
