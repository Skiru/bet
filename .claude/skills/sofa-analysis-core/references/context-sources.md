# Where the context lives - the index

Superbet prices off the same statistics we sample. Neither of us holds all of
the context: who plays tonight, what the fixture list did to the squad, what
changed since the price was taken. This file is the index; **read only your
sport's file**:

| sport | file |
|---|---|
| football | `sources-football.md` |
| tennis | `sources-tennis.md` |
| hockey | `sources-hockey.md` |
| basketball | `sources-basketball.md` |
| volleyball | `sources-volleyball.md` |
| CS2 | `sources-cs2.md` |

Each holds: the **mandatory checks** (made on every match, in that order),
the full checklist of what can change an outcome (the variable it moves, the
direction, the evidence grade and the most it may carry), and the sources -
**checked for reachability on 2026-10-26** (OK / JS-only / blocked), with when
each publishes relative to the start. Research behind them (links, grades):
`docs/sofa/history/analitycy_2026-10-26/sources_football_tennis.md`,
`docs/sofa/history/analitycy_2026-10-26/sources_measured_sports.md`.

**None of these sources is measured as a removal signal.** Whether a context
read removes losers is what the settlement audit answers per `context` tag
(7e for vetoes, 7i for removed legs). A source earns trust from that table,
not its reputation. The rules of the core skill bind every lookup (decision
point, kill facts before the search, two domains for a NO_BET, tags, leaks):
`context-pass.md`.

## Derive it before you search for it (every sport)

The cheapest context is on disk and cannot leak a result:

| signal | where | `context` |
|---|---|---|
| second leg | `02_fixtures.json` `previous_leg_event_id`; dossier `header.first_leg` | `MOTIVATION` |
| knockout vs league, which round | `round_name`, `cup_round_type`; dossier `header` | `MOTIVATION` |
| make-up fixture, rest, matches in 7 / 14 days | `03_samples.json` `schedule`; dossier `sides.*.summary` (`rest_days`, `games_7d`); the legs' `context_flags` | `SCHEDULE`, `ROTATION` |
| table stakes | the leg's `stakes`; dossier `table` (rebuilt, not official) | `MOTIVATION` |
| who plays (football / hockey / basketball) | dossier `lineups` (Sofascore pre-match: predicted or confirmed, missing / doubtful, `regulars_not_in_xi`, each prop's player status) | `ABSENCES`, `ROTATION` |
| CS2 roster change | dossier `cs2.roster_new_vs_previous` | `ABSENCES` |
| referee (football) | dossier `header` referee + games / cards; the sheet's `REFEREE` note | - (already in the model) |
| line moves | dossier `market` | a question for the web, never a verdict |
| venue, city, local hour, coordinates | dossier `header` | the weather hour |

## Every sport - the soft half

| what | where | `context` | carries |
|---|---|---|---|
| weather at the venue (outdoor only) | `https://api.open-meteo.com/v1/forecast?latitude=<lat>&longitude=<lon>&hourly=precipitation,wind_speed_10m,wind_gusts_10m,temperature_2m` (JSON, no key; the dossier's coordinates) + yr.no / meteoblue as the second domain | `CONDITIONS` | extreme only (waterlogged pitch, gale, snow, heat-rule temperatures); ordinary rain / wind is unmeasured on any count |
| dressing room, conflict, unpaid wages, a sacked coach, a boycott, fan protest | local press in the club's language, the club's and players' own channels; fan sites = `opinia` | `MORALE` | a note; a WATCH only through a lineup (players refusing to play, a youth XI) |
| managers' / players' words | press-conference reports, club channels | the tag the words are about | a fact when it names a lineup ("X nie zagra"), else `opinia` |
| previews, journalists | any preview with reasoning | `opinia` | a lead to verify, never a removal by itself |

## Tipsters

A tipster's reasoning ("rotating before the derby") is a lead to verify on a
second domain; unverified it is an `opinia`. A tipster's pick is evidence of
nothing (Forrest & Simmons 2000; Spann & Skiera 2009 - `literature.md`).

## Never a source

- bzzoiro or any provider other than Sofascore and Superbet, as a number;
- another bookmaker's or an aggregator's price (odds sites included);
- anything published after the decision point;
- a pick without its reasoning;
- Sofascore itself through the web (Cloudflare): its data reaches you through
  the pipeline's bridge - the dossier, `lineups_prematch.json`, `h2h.json`.
