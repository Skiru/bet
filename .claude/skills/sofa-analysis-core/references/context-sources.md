# Where the context lives - sources for a CONTEXT veto or a read

Superbet prices off the same statistics we sample. Neither of us holds the
context: what the match is worth, who plays, what the fixture list did to the
squad. This file says where to look, so a fact is found, not re-derived.

**None of these sources is measured.** Whether a context read removes losers
is what the settlement audit answers per `context` tag (7e for vetoes, 7i for
removed legs). A source earns trust from that table, not its reputation.

The rules of SKILL.md bind every lookup: decision point first, one web pass
per match and only when a fact could change a verdict, queries that cannot
return a scoreline, two independent domains, every claim tagged with domain
and publication time, a leak declared.

## Derive it before you search for it

The cheapest context is on disk and cannot leak a result:

| signal | where | `context` |
|---|---|---|
| second leg | `02_fixtures.json` `previous_leg_event_id` (the first leg's score is not there - follow the id) | `MOTIVATION` |
| knockout vs league, which round | `round_name`, `cup_round_type` | `MOTIVATION` |
| make-up fixture, rest, matches in 7 / 14 days | `03_samples.json` `schedule` (`makeup_of`, `makeup_postponed_utc`, per side `last_match_utc`, `rest_days`, `matches_7d`, `matches_14d`); the legs' `context_flags` | `SCHEDULE`, `ROTATION` |
| table stakes (football) | the leg's `stakes` (`STAKES_SIX_POINTER` / `STAKES_TOP4`, `effect` `za` / `przeciw`) | `MOTIVATION` |
| a cup tie a few days either side | the sample's own `match_date_utc` / `competition_id` | `ROTATION`, `SCHEDULE` |

Table position and what is left to play are one standings page away: a fact,
not an opinion.

## Football

| what | where | notes |
|---|---|---|
| predicted XI, rotation, absences | Sports Mole previews; Sportsgambler lineups; Rotowire soccer lineups; Fantasy Football Scout (Premier League) | predicted, not confirmed - say "przewidywany" |
| confirmed XI | the club's or league's own channel, ~1 h before kickoff | the only confirmed source |
| manager's words on rotation | local press: Marca / AS, Gazzetta dello Sport, Kicker, L'Équipe, BBC Sport | the quote, the date, the domain |
| stakes and narrative | The Analyst (Opta), WhoScored previews (missing players too) | |
| Polish football | Meczyki.pl, Weszło, Przegląd Sportowy | |
| derby | the same previews; a derby is a fact, "revenge" is a journalist's word - say which | |

## Tennis

| what | where | notes |
|---|---|---|
| order of play, round, court | the tournament's official site, then a second domain | qualifying is best of three even at a slam |
| ranking points to defend | live-tennis.eu | `MOTIVATION` |
| surface Elo, form, hold / break % | Tennis Abstract | a rating, not an observation of tonight |
| withdrawals, retirements, previous match length | Tennis Explorer; the tournament's site and social accounts | `SCHEDULE` / `ABSENCES` |
| ITF / UTR | almost nothing is published | say so; do not manufacture a source |

## Hockey, basketball, volleyball, CS2

| what | where | notes |
|---|---|---|
| CS2 roster, stand-ins, best-of, postponement | HLTV, Liquipedia | a stand-in matters for winner / handicap / map lines |
| hockey / basketball / volleyball schedule, postponement, format | the league's or federation's site, then a second domain | a friendly with a fixed number of periods or sets is a format the line may not assume |
| overtime / shoot-out scope | Superbet's market text on the leg (`superbet_market`) and its rules - not a preview | not a `context` tag; leave `context` out |

## Tipsters

A tipster's reasoning ("rotating before the derby") is a lead to verify on a
second domain; a tipster's pick is evidence of nothing.

## Never a source

- bzzoiro or any provider other than Sofascore and Superbet, as a number;
- another bookmaker's or an aggregator's price;
- anything published after the decision point;
- a pick without its reasoning.
