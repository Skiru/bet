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
| I11 | the ladder | every rung in `04_offer.json` + sheet rows + coupon legs | why this rung (the line against the distribution) - no rung table, the page shows the numbers |
| I12 | correlation | the mechanism, for a builder leg | the one scenario that kills every leg - **never multiply** |
| I13 | price, only the filter | `offered_odds`, x, the rung's `fetched_at_utc` | "x 1.03 >= 0.90, cena z 09:05Z" - a condition the code applied |
| I14 | buy / kill | | strongest fact for, strongest against, which wins |
| I15 | verdict | | KEEP / WATCH / NO_BET per leg + the veto entry |

## The match section, in Polish

Dense: the operator reads it folded under the leg (HTML) and in the PDF's
appendix. Facts and arithmetic, no artifact tables copied - the page shows
each leg's pewność, kurs, x, próbka. At most ~4,000 characters; a quiet match needs less.

```markdown
### <Gospodarz> – <Gość> — <rozgrywki>, <runda> · sofa:<sofascore_event_id>
**Start:** 2026-09-21 20:00Z (Superbet 20:00Z) · **identity:** CONFIRMED · nierozpoczęty o 09:12Z
**Punkt wyjścia:** pewność nóg 0.78-0.86; oczekuję <liczba w jednostkach rynku> (<skąd>).
**Fakty zabójcze (przed siecią):** <co złamałoby te nogi - 1 linia>

**Dossier.** <stawka / tabela / dwumecz; forma; odpoczynek; h2h na metryce nóg; skład (przewidywany / potwierdzony, braki); sędzia - 3-6 punktów>
**Próbka.** <n per strona, zakres dat, rozkład wokół linii: mediana, moda, ogon; udział próbki w centrum i rating - 2-4 zdania; integralność: puchary, luki>
**Kontekst (web).** <zapytania i wynik, każde z [WEB: domena, publ., fetched]; co robi której nodze, albo „nic istotnego dla tych nóg”>
**Scenariusz.** <modalny A-D z drabin Superbetu; który zabija nogi>

**Nogi.**
- <superbet_market: superbet_selection> — KEEP / WATCH / NO_BET: <jedno zdanie: oczekiwanie vs linia, fakt>
- …

**Za / Przeciw:** FAKT → RACHUNEK → IMPLIKACJA → RYZYKO (najmocniejszy argument każdej strony)
```

A buy / kill that reaches no leg is not written. A match with a prior
section today (`prior_analysis`) gets the same heading, **Dossier** /
**Próbka** as "[wcześniej: <report>]" plus what changed, and a **Kontekst
(web)** of the delta pass.

## Rules for the section

- Every non-artifact statement carries a source tag and a fetch time.
- Never present a `FUZZY` identity as confirmed.
- Never quote a combined price.
- Do not repeat a gate the code applied as your finding: "kod już to odrzucił
  jako `MODE_LOSES`".
- What you could not check goes in **NIE PODANO**, never silently omitted.
