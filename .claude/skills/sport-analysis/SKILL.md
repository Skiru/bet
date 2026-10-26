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
| `references/event-protocol.md` | you write a match section (the Polish template) |
| `.claude/skills/sofa-analysis-core/references/sources-<sport>.md` | the context pass: mandatory checks, checklist, sources and what each may carry |

## What priced the leg

A sport leg has no sheet row; its numbers are on the leg (`calibrated_on`,
`model_p`, `forecast_p`, `sample_k` / `sample_n`, `line_offset`,
`price_band_cap`). What produced `model_p`:

| sport / family | the number | what it sees | what it cannot see |
|---|---|---|---|
| hockey / basketball / volleyball game lines (winner, total, handicap, team totals, periods / quarters / sets) | `bet.sofa.score_model` - team ratings and the league's rate from the cached history (no price) | form, home / away, league scoring level (basketball season restart) | tonight's goalie, injuries, rest, rotation |
| hockey / basketball player lines | `player_model` (SHADOW's pre-game number) - the player's own appearances (hockey also the peers' games) | his rate per game | whether he dresses, his line / PP unit / minutes |
| CS2 maps / rounds / series | `cs2_engine` - team / lineup ratings, map pool terms, the round race | the five as listed, map strengths | a stand-in announced late, the veto, LAN vs online |
| CS2 player kills / deaths / assists / headshots | the exposure (rounds x per-round rate x share over 40 maps) | his share in the lineup | whether he plays, a role change |
| any key without a curve (`sb:<sport>:<key>`) | the Wilson bound of the key's own settled Superbet lines | the history of those lines | anything about tonight |

Every confidence is then lowered (never raised) by line evidence. So the
statistics already hold form, ratings, home advantage and the league's
level; **your job is the half they do not hold**: who plays, rest, format,
and whether the market Superbet settles is the one the code priced.

## The order - per match

1. **Identity** (agent step 2) - a wrong pin is the one defect that makes
   every leg of the match a different bet. `QUERY_ANCHOR`, a reserve /
   women's / academy name, a CS2 org with two rosters: compare both names.
2. **Scope** - does `superbet_market` settle what the code priced? Hockey
   winner incl. OT / shoot-out, total / handicap / 1X2 regulation;
   basketball full-game incl. OT, halves / quarters regulation only;
   volleyball golden set counts in nothing, fifth set to 15; CS2 map rounds
   incl. OT, series families on the leg's `best_of`.
3. **Expectation in the market's units** from the dossier, before any price:
   "oczekuję ~5.9 goli (Kraken 3.1 / Ducks 2.8 śr. z 10), linia 5.5";
   "~226 pkt (śr. 229 / 221, tempo ...)"; "3:1 modalne (sety 3:0 4×, 3:1
   3×)"; "mapa Nuke: Vitality 14-3 w 90 dni, rywal 5-6".
4. **Kill facts before the search** - one line: which fact would break these
   legs (a backup goalie under an UNDER, a star Out under a team-total OVER,
   a stand-in under a handicap, a rested setter under -1.5 sets).
5. **The context pass** - the sport's mandatory checks first
   (`sources-<sport>.md`), then what the dossier raises (a moved line, a new
   roster name, a back-to-back).
6. **Verdict per leg** through the leg's own variable.

## The sport's decisive facts

- **Hockey**: the starting goalie is the single biggest pre-match fact for
  totals, team totals, handicaps and the winner (sv% on one day's rest .905
  -> .897); a backup confirmed on two domains under a goalie-dependent leg is
  a NO_BET, an expected-not-confirmed backup a WATCH. Back-to-back acts mostly
  through the goalie. A player prop: dressed? which line, which PP unit? An
  empty-net late goal is in the regulation total - not a reason.
- **Basketball**: the injury report and minutes restrictions. A team total
  or handicap whose side lost a starter since the price: WATCH; a player
  prop on a player Out: NO_BET on two domains (the
  official report + one), else WATCH; Questionable / GTD: WATCH on his OVER. Second
  night of a back-to-back ~2.3 points. A star resting in a lopsided game
  (garbage time) cuts starters' props. Quarters / halves never include OT.
- **Volleyball**: the six is not published before the serve - an announced
  injury or rest of the opposite / setter / main outside hitter is the only
  pre-match fact that moves a set handicap or 3:0. A CEV double week is when
  rest happens. Points per set lines: the fifth set is to 15.
- **CS2**: the five first (`roster_new_vs_previous`, then news) - a player
  line on a player not in the five is a NO_BET on two domains, else a WATCH; a stand-in under a
  winner / handicap / roster-priced (`lineup_unrated_rule`) leg a WATCH, a
  NO_BET when confirmed on two domains. Then the map: a map line on a map one
  side has barely played in 90 days, or a map new to Active Duty, is a WATCH
  question. LAN vs online moves close-game legs. Two legs that are one bet
  (Bo3 `team_maps` OVER 0.5 and `maps_handicap` +1.5) are an exposure line,
  never a removal.

## Never a reason

A league's tendency ("this league goes under"), a winning run, yesterday's
result, a family's past hit rate, the model number or `forecast_p` far from
the confidence, a line move by itself, a preview's pick - all measured as
anti-selection or noise (`sofa-analysis-core` `references/literature.md`).
A single-source claim is WATCH at most.
