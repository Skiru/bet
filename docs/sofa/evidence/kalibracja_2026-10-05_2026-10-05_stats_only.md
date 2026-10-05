# Kalibracja: drukowana pewność a realizacja, 2026-10-05..2026-10-05 (epoka: stats_only)

Wygenerowane 2026-10-05T11:32:46+00:00 przez `scripts/sofa/measure_calibration.py` (plan `docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md`, F2.1). Tylko odczyt: nogi ocenione dokładnie tak, jak zapisuje je ledger (`record_results.graded_confidence`: 7c / 7d / 7i, sporty przez `sport_coupon`).

- **luka = średnia pewność - realizacja** (dodatnia = pewność zawyżona);
  przedział 95% z losowania całych **meczów** (nie nóg; 2000 prób,
  ziarno 7; poniżej 20 meczów brak przedziału).
- **PASS**: n >= 300 rozliczonych, |luka| <= 2 pp i przedział zawiera 0; **FAIL**: n >= 300 i nie; **INSUFFICIENT**: n < 300.
- Liczą się tylko WIN / LOSS. Zwroty, VOID, PENDING, UNSETTLED, MISMATCH, NOT_GRADED są w tabeli „nie liczone”, nigdy jako wynik.
- Warianty (a więc epoki) **nigdy nie są sumowane**: `official` (stats_only od 2026-10-05 07:15Z), `official:pre_stats_only` (nogi zablokowane z porannego wydruku 10-05), `official` dnia sprzed 10-05 (stara reguła), `wariant` (wycofany), `removed:reads` (nogi zdjęte odczytem - nie kupon).
- Wiersze „sport” i „wariant” (krzywa `*`) sumują krzywe danego sportu / wariantu - to podsumowanie, nie werdykt o żadnej krzywej.
- Builder (`builder:combined_probability`) to jedna pozycja na kupon przy jego `combined_probability`; nie jest krzywą CONFIDENCE.

Werdykty krzywych: PASS 0 · FAIL 0 · INSUFFICIENT 37.

## Wariant (wszystkie krzywe razem)

| wariant | epoka | sport | krzywa | drukowane | rozliczone | mecze | pewność % | realizacja % | luka pp | 95% (po meczach) pp | werdykt |
|---|---|---|---|---|---|---|---|---|---|---|---|
| official | stats_only | * | `*` | 210 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| removed:reads | stats_only | * | `*` | 16 | 0 | 0 | - | - | - | - | INSUFFICIENT |

## Sport (krzywe sportu razem)

| wariant | epoka | sport | krzywa | drukowane | rozliczone | mecze | pewność % | realizacja % | luka pp | 95% (po meczach) pp | werdykt |
|---|---|---|---|---|---|---|---|---|---|---|---|
| official | stats_only | builder | `*` | 1 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `*` | 102 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | hockey | `*` | 3 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | tennis | `*` | 104 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| removed:reads | stats_only | football | `*` | 12 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| removed:reads | stats_only | hockey | `*` | 2 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| removed:reads | stats_only | tennis | `*` | 2 | 0 | 0 | - | - | - | - | INSUFFICIENT |

## Krzywa (`calibrated_on`)

| wariant | epoka | sport | krzywa | drukowane | rozliczone | mecze | pewność % | realizacja % | luka pp | 95% (po meczach) pp | werdykt |
|---|---|---|---|---|---|---|---|---|---|---|---|
| official | stats_only | builder | `builder:combined_probability` | 1 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `market:cards_points_for\|UNDER` | 1 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `market:corners_1h_total` | 1 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `market:corners_for\|OVER` | 3 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `market:corners_for\|UNDER` | 5 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `market:corners_total\|OVER` | 11 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `market:corners_total\|UNDER` | 13 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `market:goals_2h_total\|OVER` | 10 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `market:goals_2h_total\|UNDER` | 7 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `market:goals_for\|OVER` | 3 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `market:goals_for\|UNDER` | 14 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `market:goals_total\|OVER` | 14 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `market:goals_total\|UNDER` | 14 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `market:saves_for\|OVER` | 2 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `market:saves_for\|UNDER` | 1 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `market_thin:goals_1h_total\|OVER` | 1 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `market_thin:goals_2h_total\|UNDER` | 1 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | football | `pooled:football` | 1 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | hockey | `hockey:handicap\|TEAM` | 1 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | hockey | `hockey:total\|OVER` | 2 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | tennis | `market:games_total\|OVER` | 1 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | tennis | `market:games_won_for\|OVER` | 27 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | tennis | `market:games_won_for\|UNDER` | 33 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | tennis | `tennis_women:market:games_total\|OVER` | 1 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | tennis | `tennis_women:market:games_total\|UNDER` | 2 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | tennis | `tennis_women:market:games_won_for\|OVER` | 17 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| official | stats_only | tennis | `tennis_women:market:games_won_for\|UNDER` | 23 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| removed:reads | stats_only | football | `market:corners_total\|UNDER` | 1 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| removed:reads | stats_only | football | `market:goals_for\|UNDER` | 2 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| removed:reads | stats_only | football | `market:goals_total\|OVER` | 3 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| removed:reads | stats_only | football | `market:goals_total\|UNDER` | 2 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| removed:reads | stats_only | football | `market:shots_on_target_total\|OVER` | 2 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| removed:reads | stats_only | football | `market:shots_on_target_total\|UNDER` | 1 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| removed:reads | stats_only | football | `market:shots_total\|OVER` | 1 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| removed:reads | stats_only | hockey | `hockey:team_total\|OVER` | 2 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| removed:reads | stats_only | tennis | `market:games_won_for\|OVER` | 1 | 0 | 0 | - | - | - | - | INSUFFICIENT |
| removed:reads | stats_only | tennis | `market:games_won_for\|UNDER` | 1 | 0 | 0 | - | - | - | - | INSUFFICIENT |

## Nie liczone (poza WIN / LOSS)

| wariant / epoka | wyniki |
|---|---|
| official / stats_only | PENDING 210 |
| removed:reads / stats_only | PENDING 16 |

**Brak rozliczonych nóg w oknie** - każda krzywa INSUFFICIENT; zgodność pewności z realizacją nie jest zmierzona.
