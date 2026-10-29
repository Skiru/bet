# Football event protocol - the steps, and the section they produce

Steps follow the evidence hierarchy: a hard fail early ends the analysis; no
later step reopens it. Every match of your read-set file gets the full
protocol; a match you intend to veto too. A match dropped at the decision
point (started) gets one line in the report's header, no section.

## The steps

| # | step | where the answer is | what you write |
|---|---|---|---|
| I1 | identity and clocks | `02_fixtures.json` (`identity`, `kickoff_utc`, `superbet_kickoff_utc`, `kickoff_disagreement_h`); `fixture_status.json` (absent before the day's first rebuild - then only the two clocks; say so); `04_offer.json` `superbet_started_utc` / `superbet_kickoff_seen_utc` | "Liga X, kolejka N; start 20:00Z (Superbet 20:00Z); CONFIRMED; nierozpoczęty o 07:40Z". Started -> dropped |
| I2 | stakes and round | `round_name`, `cup_round_type`, `previous_leg_event_id`, the leg's `stakes`; dossier `table` (rebuilt) and `header.first_leg`; the web for what changed since | round, second leg and the first leg's score, table position, dead rubber |
| I2b | schedule | `03_samples.json` `schedule`; the legs' `context_flags` | make-up (and *why*, from the web), rest days, matches in 7 / 14 days |
| I3 | the sample, per side | `metrics[<metric>].side_a / side_b / h2h` | n per bucket, date range, opponents, venues; anything that makes the mean |
| I4 | shrinkage share and the rating | `w_c = n/(n+K)` (`k_rule`); the `FOOTBALL_RATING` note (`W=`, rating centre, attack / defence ratios, a "cross-league: domains .. log strength gap" text) | once per market family, in **Szczegóły techniczne**: "gole Ajaksu: n=10, K=15 -> w_c 0.40; W=0.95" - or "rynek bez ratingu" |
| I5 | distribution | the observations | min, max, median, **mode**, where the line sits; flag a line on the mode or beyond the extreme |
| I6 | venue and opponent class | observation `venue`, `opponent`, `competition_id` | the sample's home / away mix vs tonight; the opponents' class vs tonight's |
| I6b | market drivers (mandatory, every leg) | `.claude/skills/sofa-analysis-core/references/market-drivers.md` per family; dossier `style`, `style.matchup`, `style.league` (the `jq` of core `references/dossier.md`) | per family: the drivers checked and their values; the **Styl gry i zestawienie** paragraph and leg table (below) |
| I7 | estimand check | `X_for(A) + X_for(B)` vs `X_total`; the metric's definition | "cards_points to punkty kartkowe, nie kartki"; "totalShotsOnGoal liczy każdy strzał, nie celne" |
| I8 | referee (cards / fouls) | dossier `header` referee, the row's `referee_rule`; the federation's appointment | the named referee's shrunk rate is in the centre since 2026-10-21 - say whether the row carries it; only a **change** of referee is new |
| I9 | absences and lineup | the web, two domains | per side: count, the names that matter, how you checked |
| I10 | game script A-D | Superbet's ladders in `04_offer.json` (`goals_for`, `double_chance`, `result_1x2`, `handicap_corners`, `most_*`) | which scenario is modal and whether the leg survives it; "nieważone" when no ladder |
| I11 | the ladder | every rung in `04_offer.json` + sheet rows + coupon legs | why this rung (the line against the distribution) - no rung table, the page shows the numbers |
| I12 | correlation | the mechanism, for a builder leg | the one scenario that kills every leg - **never multiply** |
| I13 | price, only the filter | `offered_odds`, x, the rung's `fetched_at_utc` | "x 1.03 >= 0.90, cena z 09:05Z" - a condition the code applied |
| I14 | buy / kill | | strongest fact for, strongest against, which wins |
| I15 | verdict | | KEEP / WATCH / NO_BET per leg + the veto entry |

## The match section, in Polish

The operator reads it on a phone, folded under the leg, and picks Bet Builder
legs from it. Write it **to be read**, not to be dense:

- full Polish sentences; a team by its name, never "A" / "B" / "gosp.";
- every number with its unit and what it means ("Aris oddaje rywalom ≥ 4
  rożne w 3 z 10 meczów"), never a bare chain like "0.30/0.45 vs 2.50/2.85";
- technical internals (`w_c`, `W`, rating ratios, `k_rule`, gaps) only in the
  closing **Szczegóły techniczne** line, once per market family;
  FAKT → RACHUNEK → IMPLIKACJA → RYZYKO only in the **Za / Przeciw** line;
- one table only: the leg table of **Styl gry i zestawienie**, built from
  the dossier's `style.matchup` (k/n copied) plus your `ocena`;
- ~4,000 characters a match, the table excluded, is the target; a builder
  match or a removal may run longer, a quiet match needs less.

Headings exactly as below (`report_check` reads them):

```markdown
### <Gospodarz> – <Gość> — <rozgrywki>, <runda> · sofa:<sofascore_event_id>
**W skrócie:** <2-3 zdania prostym językiem: kto faworytem i czemu, jak mecz się prawdopodobnie ułoży (kto będzie miał piłkę), co decyduje o nogach>
**Start:** 2026-09-21 20:00Z (Superbet 20:00Z) · **identity:** CONFIRMED · nierozpoczęty o 09:12Z
**Fakty zabójcze (przed siecią):** <co złamałoby te nogi - 1 linia>

**Styl gry i zestawienie.** <czynniki rynku z `market-drivers.md`, wartości z bloku `style`: posiadanie obu stron, dośrodkowania, kontakty i strzały w polu karnym (gra skrzydłami czy środkiem), strzały zablokowane, co rywal oddaje, stopa ligi; kto dziś będzie przy piłce (posiadanie, drabiny Superbetu); rożne strony bez piłki przy jej posiadaniu < 50% - 2-5 zdań, jedno zdanie na rodzinę rynku>

| noga (Superbet) | pewność | 1/kurs | własne / mecze gospodarza | rywal pozwolił / mecze gościa | liga % | ocena |
|---|---|---|---|---|---|---|
| Panathinaikos - liczba rzutów rożnych: powyżej 3.5 | 0.794 | 0.840 | 9/10 | Aris 3/10 | 51% | ZESTAWIENIE PRZECIW |
| Liczba rzutów rożnych: poniżej 10.5 (price_gap: realizuje po cenie) | 0.81 | 0.74 | 7/10 | 8/10 | 68% | zgodne |
Poza zestawem: <noga z `style.matchup` spoza pliku - jedna linia, bez odczytu>

**Dossier.** <stawka / tabela / dwumecz; forma; odpoczynek; h2h na metryce nóg; skład (przewidywany / potwierdzony, braki); sędzia - 3-6 punktów, pełnymi zdaniami>
**Próbka.** <n per strona, zakres dat, rozkład wokół linii: mediana, moda, ogon; integralność: puchary, luki - 2-4 zdania; próbka SAMPLES obok „własnych” z zestawienia, gdy się różnią>
**Kontekst (web).** <zapytania i wynik, każde z [WEB: domena, publ., fetched]; co robi której nodze, albo „nic istotnego dla tych nóg”>
**Scenariusz.** <modalny A-D z drabin Superbetu; który zabija nogi>

**Nogi.**
- <rynek, podmiot jak w nodze, kierunek> — KEEP: <oczekiwanie vs linie rodziny, fakt>
- <superbet_market: superbet_selection> — WATCH: RYNEK: … / DEFEKT: … / [WEB: …]

**Za / Przeciw:** FAKT → RACHUNEK → IMPLIKACJA → RYZYKO (najmocniejszy argument każdej strony)
**Szczegóły techniczne:** <per rodzina: w_c, W, rating, k_rule, luki - jedna linia>
```

### The leg table

- **Scope:** every read-set leg that the dossier's `style.matchup` lists -
  goals, corners, cards points (halves too), fouls, shots, shots on target,
  offsides, saves, throw-ins, goal kicks, `tackles_for`, `penalties_for`,
  red cards, `both_over_*` (one row per team), **totals included**. One row
  per family (market, subject, direction) at the read rung; every
  `ZESTAWIENIE PRZECIW` rung its own row; the family's other rungs in one
  cell ("także 4.5: 6/10"). `most_*` / `handicap_*` have no matchup row
  ("bez zestawienia", style means in the paragraph). A match with no listed
  leg writes the paragraph without the table.
- **Columns:** a side leg - `własne` = `style.matchup` `own`, `rywal
  pozwolił` = `opponent_conceded`; a total - `mecze gospodarza` / `mecze
  gościa` = each side's `games`; `liga %` = `league.share`. Every k/n counts
  **in the leg's direction** (an UNDER leg's "rywal pozwolił 7/10" = its
  opponents stayed under 7 times). A `price_gap` leg carries "(price_gap:
  realizuje po cenie)" in its `noga` cell and compares with 1/odds + 0.03.
- **Two "own" numbers:** `own` is the last 10 competitive games, all
  competitions; the leg's próbka is SAMPLES' selection - quote both when
  they differ; pewność rests on the próbka.
- **ocena** = `ZESTAWIENIE PRZECIW` at core's threshold (a) or (b) ("What a
  removal's reason must name"; a cup tie between levels reads who has the
  ball from the ladder alone); `zgodne` when the match-up supports the leg;
  `bez danych` when the cell is missing - for a dossier with `schema` < 2,
  "dossier sprzed bloku stylu" (core `references/dossier.md`), never a
  `RYNEK:`.
- **Verdict:** a `ZESTAWIENIE PRZECIW` rung gets its own leg-level read (its
  `line`): a WATCH `RYNEK: <driver>: <k/n>` (`context: "MARKET"`) with one
  mechanism sentence citing a `style` value, or a KEEP naming a fact that
  changes who has the ball tonight (Superbet's 1x2 / handicap ladder, a
  confirmed XI). `zgodne` / `bez danych` removes nothing.
- Legs of `style.matchup` not in your read set: one line under the table
  ("Poza zestawem"), no read.

### Nogi and the reads

"Nogi" lists one line per family (market, subject as the leg writes it,
direction) plus every WATCH / NO_BET; per-leg reasons live in the reads
JSON. A buy / kill that reaches no leg is not written.

### A delta section

A match with a prior section today (`prior_analysis`) gets the same heading;
its first body line is `**W skrócie:**`, its second `[wcześniej: <report>,
<recorded_at_utc>]`. It needs no table, but updates the rows that changed;
**Dossier** / **Próbka** say only what changed; it keeps a **Kontekst
(web).** line - the delta pass, or "delta: pełny przegląd <czas>, nic
nowego".

## Rules for the section

- Every non-artifact statement carries a source tag and a fetch time.
- Never present a `FUZZY` identity as confirmed.
- Never quote a combined price.
- Do not repeat a gate the code applied as your finding: "kod już to odrzucił
  jako `MODE_LOSES`".
- What you could not check goes in **Czego zabrakło**, never silently omitted.
