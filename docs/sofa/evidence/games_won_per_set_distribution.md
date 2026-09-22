# `games_won_set{1,2,3}_for` is bimodal — measured 2026-09-22

Source: every tennis event cached in `sofa_entity_events` with
`status.type == "finished"` and `status.code == 100` (80,149 events), both
players counted, games taken from `homeScore.periodN` / `awayScore.periodN`.

Reproduce: `scripts/sofa/measure_set_games_distribution.py`

| games | set 1 | set 2 | set 3 |
|---|---|---|---|
| 0 | 2.8% | 3.2% | 2.3% |
| 1 | 6.4% | 6.9% | 5.0% |
| 2 | 8.9% | 9.5% | 6.4% |
| 3 | 11.0% | 10.6% | 8.6% |
| 4 | 10.8% | 10.5% | 8.8% |
| **5** | **4.4%** | **4.1%** | **5.3%** |
| **6** | **45.6%** | **45.8%** | **33.1%** |
| 7 | 10.3% | 9.4% | 9.9% |
| 8+ | 0.0% | 0.0% | 4.0% |

n = 159,664 (set 1), 159,554 (set 2), 49,442 (set 3).

A trough at five and a wall at six, for the same structural reason
`games_won_for` has a trough at eleven and a wall at twelve (F49): the set
winner takes at least six games, the loser at most five, and 5-all resolves to
7-5 or 6-6 rather than staying at five.

Superbet posts this ladder at 3.5, 4.5, **5.5** and 6.5. The 5.5 rung sits
exactly on the cliff — a normal CDF puts smooth density across a 4.4% trough
and a 45.6% wall, and it does so in one direction at every rung near the
centre.

So these three metrics join `EMPIRICAL_FREQUENCY_METRICS` when they ship,
rather than after a settled day says so. This is the F49 measurement repeated
on the new quantity, not an extrapolation from it.
