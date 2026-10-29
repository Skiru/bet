---
name: sport-analysis
description: How to read one hockey, basketball, volleyball or CS2 match's coupon legs in sofa - what priced the leg (score model, CS2 engine, player model, line evidence), identity and scope first, the expectation in the market's units, the sport's decisive pre-match facts (starting goalie, injury report and back-to-back, the six, the five and the map pool), the match section. Preloaded into sofa-analyst-sport.
user-invocable: false
---

# Measured sports - the method, mapped to what `sofa` holds

`sofa-pipeline` and `sofa-analysis-core` are preloaded: they hold the input,
the numbers, the verdicts and the output contract; the agent file holds the
procedure (identity, price, context). This skill answers the question in
between: *given what priced this leg, which fact could make it wrong
tonight?*

| reference | read it when |
|---|---|
| `.claude/skills/sofa-analysis-core/references/market-drivers.md` | **before the first match**, only your sport's section (`sed` by heading, agent step 5): the drivers per family, written with their values in **Czynniki rynku** |
| `references/event-protocol.md` | you write a match section (the Polish template) |
| `.claude/skills/sofa-analysis-core/references/sources-<sport>.md` | the context pass: mandatory checks, checklist, sources and what each may carry |

## What priced the leg

A sport leg has no sheet row and no `model_p`. Its numbers: `forecast_p`
(the score-model / engine number, `forecast_source` names which),
`calibrated_on`, `line_offset`, `price_band_cap`; the read set carries
`sample_size` / `sample_hit_rate`, the coupon leg (`11_coupon.json`, the
core's lookup) `sample_k` / `sample_n`.

| sport / family | the number | what it sees | what it cannot see |
|---|---|---|---|
| hockey / basketball / volleyball game lines (winner, total, handicap, team totals, periods / quarters / sets) | `bet.sofa.score_model` - team ratings and the league's rate from the cached history (no price) | form, home / away, league scoring level (basketball season restart) | tonight's goalie, injuries, rotation, and rest: the model holds no rest term (`b2b_delta` unset) |
| hockey / basketball player lines (`player_*`) | `player_model` (SHADOW's pre-game number) - the player's own appearances (hockey also the peers' games); on days before 2026-10-30 `forecast_source` says `score_model` on these legs - the price is still player_model's | his rate per game | whether he dresses, his line / PP unit / minutes |
| CS2 maps / rounds / series | `cs2_engine` - team / lineup ratings, map pool terms, the round race | the five as listed, map strengths | a stand-in announced late, the veto, LAN vs online |
| CS2 player kills / deaths / assists / headshots | the exposure (rounds x per-round rate x share over 40 maps) | his share in the lineup | whether he plays, a role change |
| any key without a curve (`sb:<sport>:<key>`) | the Wilson bound of the key's own settled Superbet lines | the history of those lines | anything about tonight |

Every confidence is then lowered (never raised) by line evidence. So the
statistics already hold form, ratings, home advantage and the league's
level; **your job is the half they do not hold**: who plays, format, and
whether the market Superbet settles is the one the code priced. Rest and
travel are not in the number, but they are correct values known before the
price: a note, never a `DEFEKT:`.

## The order - per match

1. **Identity** (agent step 2) - a wrong pin is the one defect that makes
   every leg of the match a different bet. `QUERY_ANCHOR`, a reserve /
   women's / academy name, a CS2 org with two rosters: compare both names
   (`QUERY_ANCHOR` = one side identified by its query alone at the exact
   start). A CS2 leg with `lineup_unrated_rule` (coupon leg) is
   priced from the lineups' rating - check the announced five against it.
2. **Scope** (`shadow.MARKETS`) - does `superbet_market` settle what the
   code priced? Hockey winner incl. OT / shoot-out, total / team totals /
   handicap / 1X2 regulation, period markets their period; basketball
   winner, total, handicap, team totals, odd / even full game incl. OT, 1X2
   regulation, halves / quarters regulation only; volleyball winner by the
   sets (never `winnerCode`), a golden set (AET / AGS) counts in nothing,
   fifth set to 15; CS2 map rounds incl. OT, series families (`maps_total`,
   `maps_handicap`, `team_maps`, `exact_maps`) on the leg's `best_of`. Raise
   a scope only where `superbet_market` says otherwise.
3. **Market drivers and the expectation in the market's units**, from the
   dossier, before any price: per family the drivers of your sport's
   section of `market-drivers.md` with their values (a note), then "oczekuję ok. 5.9 goli (Kraken średnio 3.1,
   Ducks 2.8 w ostatnich 10), linia 5.5". The dossier `header` may hold only
   identity and clocks and `table` may be absent - a check you could not
   make, listed in **Czego zabrakło**.
4. **Kill facts before the search** - one line: which fact would break these
   legs (a backup goalie under an UNDER, a star Out under a team-total OVER,
   a stand-in under a handicap, a rested setter under -1.5 sets).
5. **The context pass** - the sport's mandatory checks first
   (`sources-<sport>.md`), then what the dossier raises (a moved line, a new
   roster name).
6. **Verdict per leg** through the leg's own variable, by the agent file's
   removal table: a dated `[WEB: domena, publ. <data>, fetched <czas>]` fact
   newer than the price or a real `DEFEKT:`; everything else is a note.

## The sport's decisive facts

- **Hockey**: the starting goalie is the single biggest pre-match fact for
  totals, team totals, handicaps and the winner. The dossier's
  `lineups.*.starters` is the dressed roster with both goalies - never the
  starting goalie; that comes from the web (DailyFaceoff / Rotowire, with
  status and time). A backup confirmed since the price on two domains under
  a goalie-dependent leg is a NO_BET, expected-not-confirmed a WATCH. A
  back-to-back acts through the goalie: it is a note, a WATCH only when it
  produced a dated goalie announcement. A player prop: dressed? which line,
  which PP unit? An empty-net late goal is in the regulation total - not a
  reason.
- **Basketball**: the injury report and minutes restrictions. A team total
  or handicap whose side lost a starter since the price: WATCH; a player
  prop on a player Out: NO_BET on two domains (the official report + one),
  else WATCH; Questionable / GTD since the price: WATCH on his OVER. The
  second night of a back-to-back and an expected blowout (garbage time) are
  notes - a WATCH only through a rest / minutes announcement dated after the
  price. Quarters / halves never include OT.
- **Volleyball**: the six is not published before the serve - an announced
  injury or rest of the opposite / setter / main outside hitter is the only
  pre-match fact that moves a set handicap or 3:0. Points per set lines: the
  fifth set is to 15.
- **CS2**: the five first (`roster_new_vs_previous`, then news) - a player
  line on a player not in the five is a NO_BET on two domains, else a WATCH;
  a stand-in announced since the price under a winner / handicap /
  roster-priced (`lineup_unrated_rule`) leg a WATCH, a NO_BET when confirmed
  on two domains. The map: `DEFEKT: dossier cs2.map_pool_90d, <map> n=0 ...`
  only for a map with n=0 for both sides or new to Active Duty; a thin pool
  for one side, LAN / online and stage stakes are notes. Two legs that are one
  bet (Bo3 `team_maps` OVER 0.5 and `maps_handicap` +1.5) are an exposure
  line, never a removal.

## Never a reason

A league's tendency, a winning run, yesterday's result, a family's past hit
rate, `forecast_p` far from the confidence, a line move, a preview's pick, a
schedule fact known before the price - measured as anti-selection or noise
(`sofa-analysis-core` `references/literature.md`): notes, by the agent
file's removal table.
