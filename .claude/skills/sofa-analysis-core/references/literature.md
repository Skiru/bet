# What the literature says a remove-only analyst can do

Distilled 2026-10-26 from a review of ~45 sources (academic papers, working
papers, practitioner work; abstracts and secondary descriptions, no full texts
re-derived). Full review with links and the source checks:
`docs/sofa/history/analitycy_2026-10-26/lit_review.md`. Grades: **S** solid
(peer-reviewed / replicated), **M** one study, **W** weak (blog, thesis,
preprint, small sample), **F** folklore (no evidence found).

Read this when you are unsure whether a finding may carry a removal. The
rules it produced are in `context-pass.md`; this is their why.

## 1. The market is the best public forecast

| finding | grade | source |
|---|---|---|
| Consensus / closing odds are the best public forecast; tipsters and experts do not beat them net of the margin (a majority consensus of tipsters returned ~+1.3% in one study, Brown & Reade 2019 - not a source here); picking "good" tipsters does not help | S | Forrest, Goddard & Simmons 2005; Forrest & Simmons 2000; Spann & Skiera 2009; Štrumbelj 2014; Brown & Reade 2019 |
| Exchange prices absorb a goal within seconds | S | Croxson & Reade 2014 |
| LLMs betting against the market lost in every model of a 2026 World Cup benchmark; LLM ensembles lean to "yes" | W (preprint) / M | 2026 benchmark preprint; Schoenegger et al. 2024 |
| Favourite-longshot bias: longshots carry the most margin; strongest between low-ranked tennis players (insiders) | S | Forrest & McHale 2007; Lahvička 2014; Whelan 2024 |
| A named beat reporter's post leads the price briefly; diffuse opinion does not | M | Brown, Rambaccussing, Reade & Rossi 2018 |
| Line moves on public signals are noise; streaks / hot hand are not information | M | Camerer 1989 (not verified); Gandar et al. 2005 |

Our own measurement agrees: disagreement with the price is an anti-signal
(88k rows), and reads 10-13..10-25 removed legs that realised like the kept
ones (removed minus KEEP ROI -0.9 pp [-5.9, +4.2], 1,104 removed legs;
`docs/sofa/history/analitycy_2026-10-26/analyst_measurement.md`).
**So the analyst's value is not opinion about the match; it is (a) a defect
of the leg as printed and (b) a fact the model and the price may not hold
yet.**

## 2. Which facts move outcomes, and whether the price already holds them

| factor | effect | priced? | grade | consequence for a read |
|---|---|---|---|---|
| Confirmed XI / starting goalie / CS2 stand-in contradicting the leg's premise | mechanical | only after release | S (mechanism) | the strongest removal there is |
| Injuries of key players | real, size by player | mostly, if public > 1 day | M | a fresh absence (< 24 h, named source) through the leg's variable |
| Referee card rate | real, stable between referees | the model carries it (`REFEREE`) | S | only a referee **change** is new |
| Crowd / closed doors: away yellows ↑ with fans (~+⅓ card) | real | priced except for novel shocks | S | a fan ban / closed doors is new information for cards |
| Home advantage | real, shrinking | priced, in the model | S | never a reason |
| Altitude (~0.5 goal of home goal difference per 1,000 m; Denver ~66% vs equal) | real | priced | M | only a big gap (> ~2,000 m) on away-output legs |
| Travel east / west, time zones; NBA back-to-back (~2.3 pts); goalie on 1 day's rest (sv% .905 → .897) | real | partly | M | a note (rest is in no model; the price probably holds it); a WATCH only through who rests, announced since the price |
| Tennis: a long previous match | real (Elo-adjusted, 61% after < 1 h 30 vs 32% after > 4 h 30, men's Slams) | partly | W-M | WATCH legs needing the tired player to win games |
| New coach: "bounce" is regression to the mean; odds may under-price the team in its first 1-4 games | S / M | — | may carry a WATCH on a leg **against** that team, through its variable; no reason for a leg on it |
| Motivation / dead rubber | through lineups only | priced by the close | M | WATCH only when it makes rotation likely and the leg needs starters |
| Derby: no effect on goals or results; fouls / cards mixed | S null / W | — | never a reason for goals / results |
| Weather: heat lowers passes and counter-attack shots; rain / wind on goals, corners, shots unmeasured | M / F | — | extreme only (waterlogged, gale, snow, WBGT heat rule) |
| VAR present vs absent: fouls, offsides, yellows ↓ | M | in the league's samples | not a per-match reason |
| CS2 LAN vs online; a first LAN | W | partly | WATCH close-game legs (OT, narrow totals) |
| Novel shocks (first games behind closed doors, a new format, a debut coach, an unprecedented schedule) | real | mispriced for weeks | M | may carry a WATCH through the leg's variable |

## 3. How to reason (debiasing)

| rule | grade | source |
|---|---|---|
| More information raises confidence faster than accuracy - fix what would flip the leg **before** searching | S | Tsai, Klayman & Hastie 2008; Andersson et al. 2005 |
| Start from the base rate (the leg's printed confidence) - the outside view; a story without a fact moves nothing | S | Kahneman & Lovallo 1993 |
| Premortem: "this leg lost - the three likeliest reasons", then check each as a fact | M | Klein 2007 |
| Weigh sources, not volume; one official / named source beats any number of aggregators | M | Brown et al. 2018 |

## 4. What nothing measured (do not cite as evidence)

NHL goalie confirmation timing, football lineup-release studies, NBA load
management, player-prop efficiency, volleyball anything, CS2 stand-in / map-
pool effects, rain / wind on football counts, wind on aces, dressing-room
stories, ranking points to defend. They may still be **facts** (a stand-in is
a fact); their **size** is unknown - at most a WATCH through the leg's own
variable, unless the fact breaks the leg's premise (a prop on a player who
does not start, a format the line does not assume).

## 5. The prediction to test

The literature predicts the per-tag grade (audit_settlement 7e / 7i) will rank
ABSENCES / ROTATION >= SCHEDULE > CONDITIONS > MOTIVATION ≈ MORALE ≈ DERBY ≈ 0.
A tag that stays at zero after ~200 removed legs is a note, not a removal -
that is the operator's call, on the measurement.
