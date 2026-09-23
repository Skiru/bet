# Where the context lives — sources for a `CONTEXT` veto

Superbet prices off the same statistics we sample. What neither of us holds is
the context: what the match is worth, who plays, what the fixture list did to
the squad. Other people write that up every day; this file says where, so the
read is found rather than re-derived.

**None of these sources is measured.** Whether a context veto removes losers
is exactly what `audit_vetoes.py` exists to answer, per `context` tag, and it
had one `CONTEXT` fixture to go on when this file was written (2026-09-23). A
source earns trust from that table, not from its reputation.

The rules from `SKILL.md` still bind every read below: decision point first,
never research a fixture that has started, queries that cannot return a
scoreline, two independent domains, every claim tagged with domain and
publication time, a leak declared.

## Derive it before you search for it

The cheapest context is already in the artifacts and cannot leak a result:

| signal | where | `context` |
|---|---|---|
| second leg, first-leg score | `02_fixtures.json` `previous_leg_event_id` | `MOTIVATION` |
| knockout vs league, which round | `round_name`, `cup_round_type` | `MOTIVATION` |
| a cup or European tie a few days either side | the sample's own `match_date_utc` / competitions in `03_samples.json` | `ROTATION`, `SCHEDULE` |
| yesterday's match, its length | tennis sample, newest observation | `SCHEDULE` |

Table position and what is left to play are not in the artifacts; they are one
standings page away and are a fact, not an opinion.

## Football

| what | where to look | notes |
|---|---|---|
| predicted XI, rotation, absences | Sports Mole previews; Sportsgambler lineups; Rotowire soccer lineups; Fantasy Football Scout (Premier League) | predicted, not confirmed. Name it "predicted". |
| confirmed XI | the club's or the league's own channel, ~1 h before kickoff | the only confirmed source |
| manager's words on rotation | press-conference reports in the local press: Marca / AS (ES), Gazzetta dello Sport (IT), Kicker (DE), L'Équipe (FR), BBC Sport (EN) | the quote, the date, the domain |
| stakes and narrative | The Analyst (Opta) previews; WhoScored previews (also lists missing players) | |
| Polish football | Meczyki.pl, Weszło, Przegląd Sportowy | |
| derby / grudge | the same previews; a derby is a fact, "revenge" is a journalist's word — say which | |

## Tennis

| what | where to look | notes |
|---|---|---|
| ranking points to defend, race position | live-tennis.eu | `MOTIVATION`: a player defending a title's points |
| surface Elo, form | Tennis Abstract | a rating, not an observation of tonight |
| withdrawals, retirements, schedule | Tennis Explorer; the tournament's official site and social accounts | a retirement in the last month is `SCHEDULE`/`ABSENCES` material |
| ITF / UTR | almost nothing is published | say so; do not manufacture a source |

## Tipsters

Tipsters pick 1X2, winners and BTTS; `sofa` stakes counting markets. On
2026-09-01 the retired pipeline's tipster step took 86 picks from zawodtyper
and typersi and could use **one** of them across 217 fixtures
(`docs/legacy/AUDYT_TIPSTERZY_2026-09-01.md`). A tipster's *reasoning*
("rotating before the derby") is a context lead to verify on a second domain;
a tipster's *pick* is not evidence of anything. Only sources with a complete,
timestamped public record (Blogabet, Tipstrr, OLBG, BettingExpert) are worth
reading at all, and the retired step's certification left OLBG and
BettingExpert to manual reading on terms-of-use grounds — no scraper.

## What is never a source

- bzzoiro, or any provider other than Sofascore and Superbet, as a number.
- Anything published after the decision point.
- A pick without its reasoning.
