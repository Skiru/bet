# Measured base rates

Two samples, both from bzzoiro, both reproducible. Use them as the prior when
the odds feed carries no line for a market — never as a substitute for the
consensus when it does.

## Goals and halves — 7,516 matches

Every finished fixture with both a full-time and a half-time score,
2026-05-01 … 2026-08-31, across all covered leagues.

Mean first-half goals **1.339**, mean full-time **2.996** → **first halves carry
44.7% of the goals**. This is the `FIRST_HALF_GOAL_SHARE` constant. An even
split misprices every first-half market, always in the direction of making the
first half look livelier than it is.

| Outcome | rate | fair odds |
|---|---|---|
| 1H = 0 goals | 27.8% | 3.60 |
| 1H = 1 or 2 goals | 57.2% | 1.75 |
| 1H ≥ 3 goals | 15.1% | 6.64 |
| 2H = 0 goals | 20.1% | 4.97 |
| both halves ≥ 1 goal | 58.6% | 1.71 |
| **goals 1-3 in each half** | **48.6%** | **2.06** |
| goals 1-3 in each half AND total 2-5 | 47.2% | 2.12 |
| goals 1-3 in each half AND total 2-6 | **48.6%** | 2.06 |
| **1H 1-2 goals AND 2H ≥ 1** | **46.1%** | **2.17** |
| total 2-5 | 68.8% | 1.45 |
| total 2-6 | 73.3% | 1.36 |
| over 1.5 | 77.6% | 1.29 |
| over 2.5 | 55.4% | 1.80 |

Note the two identical rows: `1-3 in each half` and `1-3 in each half AND total
2-6` are **the same 48.6%**, because the first forces the second. A slip pairing
them has one event in it.

### Ceilings

Derived by maximising the Poisson expression over every match rate, not read off
the table above:

| Structure | peak | at match rate | price floor |
|---|---|---|---|
| goals 1-3 in each half | **52.0%** | 3.63 goals | **1.92** |
| 1H over 0.5 + 1H under 2.5 + 2H over 0.5 | **50.5%** | 3.91 goals | **1.98** |

Both fall away on *both* sides of the peak. No real fixture sits on it, so leave
room: in practice do not take the first below 2.10 or the second below 2.15.

## Corners, shots and fouls — 700 matches

70 matches from each of ten leagues, 2026-01-01 … 2026-08-31, restricted to
fixtures with a published `/events/{id}/stats/`.

| League | corners | >7.5 | >8.5 | >9.5 | each team >3.5 | SOT | >6.5 | fouls | >20.5 |
|---|---|---|---|---|---|---|---|---|---|
| Premier League | 10.0 | 79% | 66% | 57% | 43% | 8.1 | 70% | 20.9 | 54% |
| La Liga | 9.3 | 69% | 60% | 51% | 34% | 8.8 | 70% | 25.5 | 83% |
| Serie A | 8.8 | 66% | 51% | 39% | 29% | 8.2 | 71% | 25.2 | 80% |
| Bundesliga | 9.4 | 71% | 61% | 47% | 34% | 9.7 | 90% | 20.7 | 47% |
| Ligue 1 | 8.9 | 64% | 53% | 40% | 34% | 8.3 | 73% | 24.3 | 77% |
| Süper Lig | 9.5 | 66% | 54% | 44% | 33% | 8.3 | 69% | 27.9 | 96% |
| Ekstraklasa | 9.7 | 76% | 66% | 54% | 34% | 8.5 | 67% | 25.8 | 80% |
| Allsvenskan | 9.9 | 74% | 67% | 49% | 43% | 9.4 | 79% | 25.3 | 81% |
| Danish Superliga | 10.3 | 76% | 67% | 57% | 47% | 9.4 | 76% | 24.0 | 69% |
| Veikkausliiga | 9.7 | 73% | 64% | 47% | 36% | 8.4 | 70% | 23.7 | 79% |
| **all** | **9.5** | **71%** | **61%** | **49%** | **37%** | **8.7** | **73%** | **24.3** | **75%** |

Per team, pooling both sides:

| | mean | rate |
|---|---|---|
| corners | 4.77 | >3.5 in **64%**, >4.5 in **48%** |
| shots on target | 4.35 | >2.5 in **77%** |
| fouls | 12.17 | >12.5 in **45%** |

Those three numbers are why a 1.40–1.45 price on a per-team counting line is
almost always below fair. It is asking for ~70% from a market that is closer to
a coin flip.

## Correlation

Measured on the same 700 matches. This is the part that contradicts the usual
assumption.

| pair | r |
|---|---|
| goals ↔ shots on target | **+0.55** |
| corners ↔ shots on target | +0.16 |
| **goals ↔ corners** | **+0.04** |
| corners ↔ fouls | −0.12 |
| goals ↔ fouls | −0.13 |

Mean corners in decided matches: **winner 4.70, loser 4.78.** The trailing side
takes marginally *more* corners — chasing a game produces corners, and so does
controlling one.

Consequences:

- **Do not multiply shots-and-goals legs.** The Napoli–Como three-leg slip lands
  46.1% of the time against a 41.1% product: +5pp of correlation lift the
  product throws away.
- **Do multiply corners legs.** Monaco's corners-plus-BTTS structure lands 20.7%
  against a 21.1% product — independent within noise.
- Fouls run mildly *against* goals. A slip pairing "lots of fouls" with "lots of
  goals" is not a coherent story about a chaotic match; it is two legs pulling in
  opposite directions.

**Cards were not sampled** — `/events/{id}/stats/` carries `yellow_cards` but
the 700-match pull did not retain it, so nothing here speaks to the
"foul-heavy match is a card-heavy match" claim in `bet_builder_draft.py`. What
this sample does say is that the *corners* and *fouls* halves of that same
sentence do not hold against goals. Re-pull with `yellow_cards` before treating
the card claim as either confirmed or broken.

## Reproducing all of this

The sampling scripts are not committed — they are three short loops over
`/events/`, `/events/{id}/stats/` and `/teams/{id}/fixtures/` using the client
in `src/bet/api_clients/bzzoiro.py`. Pagination is `limit`/`offset`, **not**
`page`: a `page` parameter is silently ignored and you will get one page back
with a `count` that says otherwise, which is how a 153-match day first read as
100 matches.
