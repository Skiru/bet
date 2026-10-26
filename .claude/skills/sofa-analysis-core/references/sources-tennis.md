# Tennis - context checklist and sources

Checked 2026-10-26 (`docs/sofa/history/analitycy_2026-10-26/sources_football_tennis.md`).
Access: **OK** / **JS** / **CF** as in `sources-football.md`. Evidence:
**E+** measured, **E~** mixed / small, **F** folklore.

## Mandatory - every match, in this order

1. **Is it on, when, which format** - order of play (tournament site), the
   round, best of three or five, the final-set rule; a withdrawal or a lucky
   loser in the draw.
2. **Condition** - each player's previous match: when it ended, how long, a
   medical time-out, a retirement (tennisexplorer's match list and its
   injury / retirement table).
3. **Surface and conditions** - indoor / outdoor (tennisexplorer's
   tournament page says "Indoors"), altitude; heat only near the ATP heat
   rule.

ITF / low Challengers: these three are usually all that exists. A missing
preview there is normal, never a reason to remove a leg - write
`UNVERIFIED` for the rest.

## Checklist

| item | moves | evidence | carries |
|---|---|---|---|
| **Withdrawal / walkover / retirement** | refund (WALKOVER / RETIRED settle at 0) - still not a bet | rule | NO_BET when announced on two domains |
| **Injury or illness reported, MTO in the last match** | the injured player's games ↓, handicaps blow out; retirement risk | E~ | WATCH legs needing that player to win games / sets |
| **Long previous match** (> ~4 h 30, or a late finish the night before) | next-match win rate, Elo-adjusted, 61% after a match under 1 h 30 vs 32% after one over 4 h 30 (men's Slams) | E~ (Tennis Abstract) | WATCH legs needing the tired player to win games |
| **Travel / surface switch in week one** | upset risk; opponent's travel strengthens home advantage | E~ | note |
| **Home player** | +2-3% wins vs ranking expectation | E+ (Koning; Gucciardi & Ruberti 2025) | note (priced) |
| **Fast surface / indoor / altitude** (Bogotá, Quito, Gstaad, Kitzbühel, São Paulo) | aces ↑, holds ↑ → games, tie-breaks ↑ | E+ (surface speed, altitude) / E~ (indoor) | WATCH on aces / games UNDER only when the sample is from a different speed class |
| **Heat** | retirement risk, long matches; ATP heat rule from 2026: WBGT ≥ 30.1 °C → 10-min break after set 2 (Bo3), > 32.2 °C suspension | rule / F | note; a suspension risk is a fact |
| **Wind** | first-serve %, aces ↓ - unmeasured | F | note |
| **Format** | Bo5 at men's Slams (code: `BEST_OF_FIVE_NOT_MODELLED`); 10-point tie-break at 6-6 in Slam final sets; team cups (Davis / BJK / United Cup) | rule | NO_BET when the line assumes another format |
| **Qualifier / lucky loser** | acclimatised but tired | F | note |
| **Ranking points to defend, small-event motivation, tanking** | effort | F | note |
| **Low-ranked pair, our confidence far above 1/odds** | favourite-longshot bias and insiders are strongest there (Lahvička 2014) | S | the gap is a warning, never value (`price_gap` is already on the leg) |

## Sources

| need | source | access | when |
|---|---|---|---|
| matches, surface, indoor, results ATP → ITF, **injury / retirement table** per player | tennisexplorer.com | OK - the best single source | daily |
| order of play | the tournament's own site (OOP PDF); flashscore.com/tennis, tennis24.com (times) | OK / partly JS | evening before |
| WTA | wtatennis.com (tournaments, players; OOP is JS) | OK / JS | |
| ATP news (heat rule, withdrawals) | atptour.com news via WebFetch (the site is CF to curl) | partly | |
| other | tennislive.net, tennisstats.com, coretennis.net, ultimatetennisstatistics.com | OK (depth unchecked) | facts only, never their numbers (Sofascore + Superbet only) |

**Blocked / empty**: itftennis.com (JS-only), live-tennis.eu (CF - ranking
points dropping is unreachable), matchstat, tennistemple, tennistonic,
tennisworldusa (CF), protennislive (down).
