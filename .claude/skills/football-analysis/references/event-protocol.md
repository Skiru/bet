# Football event protocol - the steps, and the section they produce

Steps follow the evidence hierarchy: a hard fail early ends the analysis; no
later step reopens it. Every match of your read-set file gets the full
protocol; a match you intend to veto too. Anything else: one line under
*Pozostałe mecze*, or nothing.

## The steps

| # | step | where the answer is | what you write |
|---|---|---|---|
| I1 | identity and clocks | `02_fixtures.json` (`identity`, `kickoff_utc`, `superbet_kickoff_utc`, `kickoff_disagreement_h`); `fixture_status.json`; `04_offer.json` `superbet_started_utc` / `superbet_kickoff_seen_utc` | "Liga X, kolejka N; start 20:00Z (Superbet 20:00Z); CONFIRMED; nierozpoczęty o 07:40Z". Started -> dropped |
| I2 | stakes and round | `round_name`, `cup_round_type`, `previous_leg_event_id`, the leg's `stakes`; table and aggregate from the web | round, second leg and the first leg's score, table position, dead rubber |
| I2b | schedule | `03_samples.json` `schedule`; the legs' `context_flags` | make-up (and *why*, from the web), rest days, matches in 7 / 14 days |
| I3 | the sample, per side | `metrics[<metric>].side_a / side_b / h2h` | n per bucket, date range, opponents, venues; anything that makes the mean |
| I4 | shrinkage share and the rating | `w_c = n/(n+K)` (`k_rule`); the `FOOTBALL_RATING` note (`W=`, rating centre, attack / defence ratios, `link_rule`) | "n=10, K=15 -> próbka 40% centrum próbkowego; rating W=0.95 daje 2.22 przy próbce 2.00" - or "rynek bez ratingu" |
| I5 | distribution | the observations | min, max, median, **mode**, where the line sits; flag a line on the mode or beyond the extreme |
| I6 | venue and opponent class | observation `venue`, `opponent`, `competition_id` | the sample's home / away mix vs tonight; the opponents' class vs tonight's |
| I7 | estimand check | `X_for(A) + X_for(B)` vs `X_total`; the metric's definition | "cards_points to punkty kartkowe, nie kartki"; "totalShotsOnGoal liczy każdy strzał, nie celne" |
| I8 | referee (cards / fouls) | `RefereeRecord` | `games`, yellow and red rate - or "brak sędziego" and what that costs |
| I9 | absences and lineup | the web, two domains | per side: count, the names that matter, how you checked |
| I10 | game script A-D | Superbet's ladders in `04_offer.json` (`goals_for`, `double_chance`, `result_1x2`, `handicap_corners`, `most_*`) | which scenario is modal and whether the leg survives it; "nieważone" when no ladder |
| I11 | the ladder | every rung in `04_offer.json` + sheet rows + coupon legs | rung table: pewność, próbka k/n, model, kurs, x; why this rung |
| I12 | correlation | the mechanism, for a builder leg | the one scenario that kills every leg - **never multiply** |
| I13 | price, only the filter | `offered_odds`, x, the rung's `fetched_at_utc` | "x 1.03 >= 0.90, cena z 09:05Z" - a condition the code applied |
| I14 | buy / kill | | strongest fact for, strongest against, which wins |
| I15 | verdict | | KEEP / WATCH / NO_BET per leg + the veto entry |

## The match section, in Polish

```markdown
### <Gospodarz> – <Gość> — <rozgrywki>, <runda>
**Start:** 2026-09-21 20:00Z (Superbet 20:00Z; rozjazd 0.0 h) · **identity:** CONFIRMED
**Status:** nierozpoczęty o 09:12Z (najwcześniejszy zegar: 20:00Z)

**Stawka.** <runda, dwumecz + wynik 1. meczu, miejsce w tabeli - albo „brak">

**Próbka.** corners_total: side_a n=10 (2026-07-14 … 2026-09-14), side_b n=10,
h2h n=3. Wartości side_a: 6 8 8 9 9 10 11 11 12 15 (mediana 9, moda 8/9/11,
zakres 6–15). Trzy najwyższe przeciw <rywale>.
**Udział próbki w centrum:** n=10, K=15 -> 40%; rating: <W, centrum ratingu> albo „rynek bez ratingu".

**Rozkład.** <moda, ogony, gdzie leży linia>

**Kontekst.** Sędzia: <nazwisko>, <games> meczów, <żółte>/mecz - albo „brak".
Braki kadrowe: <…> `[WEB: domena, publ. …, fetched …]`. Scenariusz modalny: <A/B/C/D>.

**Drabina.**
| poz. | rynek (Superbet) | pewność | próbka k/n | model | kurs | x | uwagi |
|---|---|---|---|---|---|---|---|

**Cena (tylko warunek).** <kurs, x = pewność x kurs >= 0.90, fetched_at>

**Za:** FAKT → RACHUNEK → IMPLIKACJA → RYZYKO
**Przeciw:** FAKT → RACHUNEK → IMPLIKACJA → RYZYKO

**Werdykt:** KEEP / WATCH / NO_BET — <jedno zdanie>
```

## Rules for the section

- Every non-artifact statement carries a source tag and a fetch time.
- Never present a `FUZZY` identity as confirmed.
- Never quote a combined price.
- Do not repeat a gate the code applied as your finding: "kod już to odrzucił
  jako `MODE_LOSES`".
- What you could not check goes in **NIE PODANO**, never silently omitted.
