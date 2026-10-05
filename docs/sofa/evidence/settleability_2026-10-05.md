# Rozliczalność wydrukowanych nóg (D+3)

Pomiar: `scripts/sofa/measure_settleability.py`, 2026-10-05T11:36:19+00:00. Nogi: wszystko, co wydrukował PDF kuponu (11_coupon.json / 08_confidence.json) i WARIANTU (08_confidence_wariant.json) - single i nogi builderów, piłka i tenis (sporty mierzone rozlicza sport_coupon). Ocena: `sofa_settled_row` (wiersz dnia, inaczej ten sam klucz pod inną datą), `07_settled_printed.json`. Pierwsze rozliczenie = `settled_at` albo najwcześniejsze `old_settled_at` z `runs/sofa/regrade_*.json`. Zwrot (przełożony > 48 h, walkower) i PUSH nie są winne rozliczenia - poza mianownikiem.

Dni z minionym horyzontem: 2026-09-19, 2026-09-20, 2026-09-21, 2026-09-22, 2026-09-23, 2026-09-24, 2026-09-25, 2026-09-26, 2026-09-27, 2026-09-28, 2026-09-29, 2026-09-30, 2026-10-01. Dni bez horyzontu (stan na teraz, poza wynikiem): 2026-10-02, 2026-10-03, 2026-10-04.

## Wynik

- **Nierozliczone po D+3: 240 z 2798 nóg (8.6%, dolna granica Wilsona 7.6%).** Kryterium planu F0.6: < 2% przez 7 dni - dziś niespełnione.
- z tego rozliczone później: 195 (w tym 9 z danymi w cache przed horyzontem - proces: nikt nie rozliczył dnia ponownie), nadal nierozliczone: 45 {'DATA_GAP': 5, 'IDENTITY': 3, 'NOT_PLAYED': 37}.
- zwroty / PUSH: 1 z 2799 wydrukowanych.

## Według profilu

| profil | należne | nierozl. D+3 | % | później | nadal |
|---|---|---|---|---|---|
| standard | 280 | 35 | 12.5% | 32 | 3 |
| wariant | 2662 | 232 | 8.7% | 189 | 43 |

## Według dnia

| dzień | należne | nierozl. D+3 | % | później (proces) | nadal | horyzont |
|---|---|---|---|---|---|---|
| 2026-09-19 | 83 | 3 | 3.6% | 3 (0) | 0 | minął |
| 2026-09-20 | 12 | 0 | 0.0% | 0 (0) | 0 | minął |
| 2026-09-21 | 0 | 0 | — | 0 (0) | 0 | minął |
| 2026-09-22 | 39 | 5 | 12.8% | 3 (1) | 2 | minął |
| 2026-09-23 | 32 | 0 | 0.0% | 0 (0) | 0 | minął |
| 2026-09-24 | 288 | 7 | 2.4% | 0 (0) | 7 | minął |
| 2026-09-25 | 310 | 11 | 3.5% | 2 (0) | 9 | minął |
| 2026-09-26 | 967 | 105 | 10.9% | 88 (0) | 17 | minął |
| 2026-09-27 | 613 | 52 | 8.5% | 46 (0) | 6 | minął |
| 2026-09-28 | 99 | 12 | 12.1% | 12 (5) | 0 | minął |
| 2026-09-29 | 219 | 35 | 16.0% | 31 (3) | 4 | minął |
| 2026-09-30 | 56 | 10 | 17.9% | 10 (0) | 0 | minął |
| 2026-10-01 | 80 | 0 | 0.0% | 0 (0) | 0 | minął |
| 2026-10-02 | 256 | 22 | 8.6% | 0 (0) | 22 | nie minął |
| 2026-10-03 | 895 | 87 | 9.7% | 0 (0) | 87 | nie minął |
| 2026-10-04 | 505 | 38 | 7.5% | 0 (0) | 38 | nie minął |

## Według rodziny rynku

| rodzina | należne | nierozl. D+3 | % | Wilson dolna | nadal (brak danych) |
|---|---|---|---|---|---|
| corners | 476 | 192 | 40.3% | 36.0% | 4 |
| games | 586 | 27 | 4.6% | 3.2% | 0 |
| goals | 1607 | 14 | 0.9% | 0.5% | 1 |
| shots | 79 | 4 | 5.1% | 2.0% | 0 |
| cards | 36 | 3 | 8.3% | 2.9% | 0 |
| aces | 2 | 0 | 0.0% | 0.0% | 0 |
| double_faults | 8 | 0 | 0.0% | 0.0% | 0 |
| offsides | 4 | 0 | 0.0% | 0.0% | 0 |

## Rozgrywki z największą liczbą nierozliczonych (top 25)

| rozgrywki | należne | nierozl. D+3 | % | nadal |
|---|---|---|---|---|
| National League [173] (football) | 131 | 56 | 42.8% | 0 |
| Primera B Nacional [703] (football) | 80 | 44 | 55.0% | 0 |
| Torneo DIMAYOR, Clausura [1238] (football) | 36 | 15 | 41.7% | 2 |
| MLS [242] (football) | 69 | 11 | 15.9% | 11 |
| Liga AUF Uruguaya, Clausura [278] (football) | 27 | 9 | 33.3% | 0 |
| Curitiba, Brazil [9366] (tennis) | 33 | 8 | 24.2% | 0 |
| National League North [176] (football) | 38 | 8 | 21.1% | 1 |
| Genoa 2, Italy [38037] (tennis) | 40 | 7 | 17.5% | 7 |
| Liga de Ascenso [1240] (football) | 15 | 6 | 40.0% | 0 |
| National [183] (football) | 27 | 6 | 22.2% | 1 |
| Segunda Division [1908] (football) | 26 | 6 | 23.1% | 0 |
| National League South [174] (football) | 31 | 5 | 16.1% | 0 |
| Tolentino, Italy [29389] (tennis) | 27 | 5 | 18.5% | 5 |
| Cymru Premier [254] (football) | 19 | 4 | 21.1% | 0 |
| Primera Federacion, Group 1 [17073] (football) | 26 | 4 | 15.4% | 0 |
| Brasileirão Série C, Group C [1281] (football) | 5 | 3 | 60.0% | 0 |
| Championship [206] (football) | 10 | 3 | 30.0% | 0 |
| Premiership [200] (football) | 14 | 3 | 21.4% | 0 |
| Primera Federacion, Group 2 [17073] (football) | 20 | 3 | 15.0% | 0 |
| Brasileirão Série B [390] (football) | 69 | 2 | 2.9% | 0 |
| Curitiba, Brazil, Qualifying [9366] (tennis) | 11 | 2 | 18.2% | 2 |
| Derde Divisie A [18497] (football) | 2 | 2 | 100.0% | 0 |
| EFL Trophy, Northern Group A [334] (football) | 3 | 2 | 66.7% | 2 |
| ITF M25 Santa Margherita di Pula 8 Men [29574] (tennis) | 9 | 2 | 22.2% | 2 |
| K League 1 [410] (football) | 6 | 2 | 33.3% | 0 |

## Powody nadal nierozliczonych (SETTLE, 07_settle_skips.json)

- `FINISHED_ABNORMALLY`: 17
- `POSTPONED`: 13
- `corners_total:EVENT_NOT_FINISHED`: 4
- `corners_total:STAT_KEY_ABSENT`: 4
- `SUBJECT_NOT_MATCHED`: 3
- `CANCELED`: 2
- `NO_EVENT`: 1
- `goals_1h_total:STAT_KEY_ABSENT`: 1

## Dni bez minionego horyzontu (stan na teraz)

- należne 1656, nierozliczone 147 (8.9%) - liczba jeszcze spadnie.

## Zastrzeżenia

- „Rozliczone później” ze statystyk pobranych po horyzoncie: cache trzyma tylko ostatnie pobranie, więc nie da się odróżnić, czy feed ligi zamknął się po D+3, czy nikt nie zapytał wcześniej (do 10-05 ponownie rozliczano tylko D-5). Dla bramki to górna granica braku danych.
- Dzień bez `08_confidence_wariant.json` liczy tylko kupon; dni 09-20 i 09-21 drukowały same buildery. Większość nóg to WARIANT (cały artefakt na PDF), kupon do 10-04 drukował 30 singli.
- Pewność, ROI i krzywe nie są tu mierzone - tylko to, czy noga dostała ocenę.

## Bramka rozliczalności (fit, `config/sofa_settleability.json`)

Komórka (rozgrywki, rodzina) odmawiana `NOT_SETTLEABLE`, gdy co najmniej 8 ocenionych nóg i dolna granica Wilsona (95%) udziału nierozliczonych z braku danych > 10.0%. Brak danych = nadal nierozliczona z powodem statystyki (NO_STATISTICS, STAT_KEY_ABSENT, ...) albo rozliczona po horyzoncie ze statystyk pobranych po nim. Mecz nierozegrany, gracz / strona nierozpoznani, błąd dostawcy - poza oceną (nic nie mówią o feedzie ligi).

| rozgrywki | rodzina | ocenione | brak danych | % | Wilson dolna |
|---|---|---|---|---|---|
| Torneo DIMAYOR, Clausura [1238] | corners | 15 | 15 | 100.0% | 79.6% |
| National League [173] | corners | 65 | 56 | 86.2% | 75.7% |
| National League North [176] | corners | 9 | 8 | 88.9% | 56.5% |
| Cymru Premier [254] | corners | 8 | 4 | 50.0% | 21.5% |
| Liga AUF Uruguaya, Clausura [278] | corners | 9 | 9 | 100.0% | 70.1% |
| Primera B Nacional [703] | corners | 44 | 44 | 100.0% | 92.0% |

Z bramką (w próbie - komórki dopasowane na tych samych nogach): usunięte 150 nóg, nierozliczone po D+3 104 z 2648 (3.9%).
- Poza próbą: komórki z dni <= 2026-09-26 (3) na dniach 2026-09-27..2026-10-01: bez bramki 109/1067 (10.2%), z bramką 55/1013 (5.4%), usunięte 54 nóg.
- Poza próbą: komórki z dni <= 2026-09-28 (4) na dniach 2026-09-29..2026-10-01: bez bramki 45/355 (12.7%), z bramką 12/322 (3.7%), usunięte 33 nóg.

