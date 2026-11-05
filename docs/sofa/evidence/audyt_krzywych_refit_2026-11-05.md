# Audyt gotowości do refitu: zainstalowane krzywe i dopasowania (2026-11-05)

Pytanie operatora (2026-11-05): czy rynki, które już mamy, i ich modele można dziś zrobić lepiej, skoro mamy wiele więcej rozliczonych dni i dokończone backfille historii? Miara: co najmniej tak dobrze jak cena Superbetu bez marży, z marżą zaakceptowaną, oraz uczciwa (skalibrowana) pewność.

**W skrócie:**
- Historia urosła mocno w sportach mierzonych (koszykówka +103%, siatkówka +206% gier przed datą dopasowania), a w piłce i tenisie umiarkowanie (+15,9% / +8,1% zdarzeń względem bazy, z której są krzywe 10-17).
- Dopasowanie sportów bierze jednak co najwyżej `max_games` 4000 gier z okna rocznego, przerzedzając je równym krokiem. Więcej historii nie daje więc więcej wierszy w dopasowaniu, tylko rzadsze próbkowanie. Dzisiejszy dry-run tego samego dopasowania (poranny `refresh_line_evidence.py`) wypada **gorzej** niż krzywe zainstalowane w hokeju, koszykówce i CS2, a w siatkówce wychodzi remis (T4). Refitu sportów obecnym narzędziem nie rekomenduję.
- Krzywe piłki i tenisa z 10-17 na liniach Superbetu od 10-18 lekko obiecują za dużo: piłka >= 0.70 −0,6 pp [−0,9, −0,3], tenis >= 0.70 −1,7 pp [−2,3, −1,0], tenis 0.60–0.70 −3,0 pp. W tym samym przedziale pewności wynik wypada poniżej ceny bez marży o 1,5 pp (piłka) i 1,6 pp (tenis). Refit z 10-22 na pełniejszej historii nie ruszył tego dryfu (luka po bramkach <= 0,17 pp, model-state (d)). Dryf leży tam, gdzie działają przełączniki, których refit **nie odtwarza** (sędzia, udział zawodnika, P1/P3/P5/P14). Sama nowa historia go nie usunie.
- Dysk: wolne 19,6 GB, a refit potrzebuje ~68 GB (kopia + nowe wiersze replayu). Na dysku leżą cztery pełne kopie robocze bazy (208,5 GB) oraz baza replayu 10-17 (64 GB, „keep”). Plan jest w sekcji 4. Niczego nie usuwałem.

Źródło każdej liczby: `scripts/sofa/measure_refit_readiness.py` (tylko odczyt, `mode=ro`, bez sieci, bez zapisu konfiguracji, nie czyta zapisu wycenionych wierszy). Wyniki: `data/refit_readiness_2026-11-05/{growth,drift,sizes}.json`. Tabele poniżej to dosłowny wynik `... tables` (`tables.md`).

## 1. Na czym dopasowano, a co jest dziś

| dopasowanie | data | źródło (`fitted_from`) |
|---|---|---|
| krzywe piłki / tenisa (97 by_market, 246 by_market_direction, 13 by_class) | 2026-10-17 18:44Z | `data/refit_2026-10-17/sofa_replay.db`, 119 040 225 wierszy, rozliczone do 10-16, 21 flag replayu |
| krzywe per linia (76 kluczy) | 2026-10-18 11:58Z | ta sama baza |
| `match_won_for` | 2026-10-13 | 49 791 wierszy, okno 04-01..10-13 |
| stałe silnika, bazy lig, wiarygodność rynków | 2026-10-17 17:28Z | ta sama baza, 119 137 664 wierszy, 10 544 rozgrywek |
| sporty (`.next.2026-10-28.json`, plik czytany dziś) | hokej before 10-23, koszykówka 10-14, siatkówka 10-07, CS2 10-13 | okno roczne, max 4000 gier (CS2 bez limitu) |
| model zawodników (hokej / koszykówka) | 2026-10-02 | cięcie 07-01; koszykówka 12 877 gier treningu, hokej 1 341 |
| bazy tenisowe wg poziomu | 2026-10-03 | cache |

### T1. Dopasowanie a historia dziś

| sport | zdarzenia w bazie dopasowania | dziś | wzrost % |
|---|---:|---:|---:|
| football | 1016901 | 1178603 | 15.9 |
| tennis | 342997 | 370740 | 8.1 |
| hockey | 32653 | 63086 | 93.2 |
| basketball | 59206 | 134517 | 127.2 |
| volleyball | 25149 | 67534 | 168.5 |
| cs2 | 24340 | 25646 | 5.4 |

| sport (krzywe) | before | gry historii przed | dziś (dry-run) | wzrost % | gry w dopasowaniu | dziś | max_games |
|---|---|---:|---:|---:|---:|---:|---:|
| hockey | 2026-10-23 | 57556 | 59065 | 2.6 | 4095 | 4134 | 4000 |
| basketball | 2026-10-14 | 51168 | 104061 | 103.4 | 5712 | 8515 | 4000 |
| volleyball | 2026-10-07 | 20691 | 63406 | 206.4 | 3968 | 3736 | 4000 |
| cs2 | 2026-10-13 | 15035 | 14876 | -1.1 | 9989 | 9900 | None |

Uwagi do T1: piłka i tenis to wszystkie zdarzenia z listingu `sofa_listed_event` (także niezakończone i bez `/statistics`). Liczba meczów ze statystykami, które replay faktycznie czyta, **nie jest zmierzona**: wymagałaby pełnego skanu `sofa_event_stats` w obu bazach. Dziś `sofa_event_stats` ma ~879 tys. komórek (T6). Wiersz CS2 to cs2_series zakończone: 17 289 przed 10-13, dziś 18 442 (+6,7%). Sporty: „gry historii przed” to `history_games_before` dopasowania zainstalowanego i dzisiejszego dry-runu. „Gry w dopasowaniu” pokazują, że limit 4000 trzyma objętość dopasowania praktycznie bez zmian.

## 2. Dryf na rozliczonych liniach Superbetu od instalacji (audyt, nigdy źródło)

Pewność to tutaj sama krzywa (jej `realised_lo95`). Offset dowodu linii i cap pasma są dopasowane na tych samych liniach (w próbie), więc nie wchodzą do audytu. Przedziały to 1000 bootstrapów po meczach. Znak minus oznacza obietnicę ponad wynik.

### T2. Piłka / tenis: krzywa 10-17 na liniach Superbetu 2026-10-18..2026-11-04

| komórka | n | mecze | pewność | trafione | trafione - pewność, pp [95%] |
|---|---:|---:|---:|---:|---|
| football 0.60-0.70 | 102,577 | 6,977 | 0.651 | 0.648 | -0.3 [-0.6, -0.0] |
| football >=0.70 | 216,427 | 7,007 | 0.817 | 0.811 | -0.6 [-0.9, -0.3] |
| tennis 0.60-0.70 | 23,640 | 2,326 | 0.648 | 0.618 | -3.0 [-3.8, -2.2] |
| tennis >=0.70 | 44,673 | 2,472 | 0.820 | 0.804 | -1.7 [-2.3, -1.0] |

Te same wiersze (dwustronne linie) wobec ceny bez marży (trafione - cena):

| komórka | n | mecze | cena | trafione | trafione - cena, pp [95%] |
|---|---:|---:|---:|---:|---|
| football 0.60-0.70 | 68,883 | 6,822 | 0.650 | 0.645 | -0.4 [-0.8, -0.1] |
| football >=0.70 | 139,672 | 7,004 | 0.821 | 0.806 | -1.5 [-1.8, -1.1] |
| tennis 0.60-0.70 | 23,335 | 2,283 | 0.625 | 0.618 | -0.7 [-1.5, +0.2] |
| tennis >=0.70 | 44,541 | 2,472 | 0.820 | 0.804 | -1.6 [-2.2, -1.0] |

### T3a. Piłka / tenis: rodziny z przedziałem bez zera (n >= 300): 42

| komórka | n | mecze | pewność | trafione | trafione - pewność, pp [95%] |
|---|---:|---:|---:|---:|---|
| football handicap_corners 0.60-0.70 | 402 | 341 | 0.651 | 0.517 | -13.3 [-18.1, -8.0] |
| football throw_ins 0.60-0.70 | 321 | 158 | 0.648 | 0.530 | -11.9 [-18.7, -5.4] |
| tennis handicap_games 0.60-0.70 | 1,305 | 819 | 0.647 | 0.554 | -9.3 [-12.5, -6.2] |
| tennis set1_won 0.60-0.70 | 384 | 384 | 0.650 | 0.565 | -8.5 [-13.7, -3.2] |
| football fouls 0.60-0.70 | 608 | 289 | 0.648 | 0.572 | -7.6 [-12.2, -3.0] |
| tennis handicap_games >=0.70 | 812 | 469 | 0.765 | 0.691 | -7.4 [-11.5, -3.6] |
| football dc_and_over >=0.70 | 447 | 379 | 0.768 | 0.696 | -7.2 [-12.6, -2.5] |
| tennis tennis_women:games_won_set2 0.60-0.70 | 1,301 | 781 | 0.657 | 0.602 | -5.5 [-8.2, -2.9] |
| tennis match_won 0.60-0.70 | 369 | 369 | 0.646 | 0.594 | -5.2 [-9.8, -0.4] |
| tennis games_won_set2 0.60-0.70 | 1,970 | 1,154 | 0.662 | 0.621 | -4.1 [-6.3, -1.9] |
| football first_goal 0.60-0.70 | 734 | 734 | 0.641 | 0.601 | -4.0 [-7.7, -0.5] |
| tennis games_won 0.60-0.70 | 2,763 | 1,232 | 0.650 | 0.610 | -4.0 [-5.8, -2.2] |
| tennis tennis_women:games_won 0.60-0.70 | 1,859 | 836 | 0.644 | 0.606 | -3.8 [-6.0, -1.4] |
| tennis games 0.60-0.70 | 1,595 | 973 | 0.636 | 0.601 | -3.5 [-6.2, -1.0] |
| football shots >=0.70 | 2,836 | 487 | 0.760 | 0.725 | -3.5 [-6.0, -0.9] |
| football both_over_cards_points >=0.70 | 705 | 431 | 0.803 | 0.769 | -3.4 [-6.3, -0.5] |
| tennis games_won >=0.70 | 3,981 | 1,284 | 0.773 | 0.740 | -3.4 [-5.0, -1.9] |
| football player_fouls_drawn >=0.70 | 791 | 289 | 0.759 | 0.726 | -3.3 [-6.3, -0.2] |
| tennis tennis_women:games_won_set2 >=0.70 | 2,791 | 867 | 0.844 | 0.811 | -3.3 [-5.1, -1.5] |
| football both_over_goals 0.60-0.70 | 2,114 | 1,904 | 0.637 | 0.606 | -3.1 [-5.2, -1.1] |
| tennis games_won_set1 0.60-0.70 | 1,898 | 1,141 | 0.664 | 0.633 | -3.1 [-5.4, -1.1] |
| football dc_and_over 0.60-0.70 | 1,502 | 1,479 | 0.667 | 0.636 | -3.1 [-5.5, -0.6] |
| football cards_points 0.60-0.70 | 3,086 | 1,012 | 0.652 | 0.624 | -2.7 [-4.4, -1.2] |
| tennis tennis_women:games_won >=0.70 | 2,444 | 870 | 0.781 | 0.754 | -2.7 [-4.7, -0.7] |
| football result_or_clean_sheet 0.60-0.70 | 2,469 | 1,164 | 0.647 | 0.622 | -2.5 [-4.7, -0.4] |
| tennis games_won_set1 >=0.70 | 5,408 | 1,288 | 0.841 | 0.820 | -2.1 [-3.1, -1.1] |
| football cards_points >=0.70 | 4,026 | 858 | 0.803 | 0.782 | -2.1 [-3.9, -0.5] |
| football shots 0.60-0.70 | 3,885 | 563 | 0.652 | 0.632 | -1.9 [-3.7, -0.2] |
| tennis games_won_set2 >=0.70 | 5,286 | 1,278 | 0.842 | 0.824 | -1.9 [-3.0, -0.8] |
| football shots_on_target 0.60-0.70 | 2,738 | 608 | 0.649 | 0.631 | -1.7 [-3.3, -0.0] |
| football result_handicap >=0.70 | 5,598 | 2,947 | 0.836 | 0.819 | -1.7 [-2.8, -0.6] |
| football double_chance >=0.70 | 9,987 | 6,361 | 0.784 | 0.770 | -1.4 [-2.2, -0.7] |
| football both_over_goals >=0.70 | 6,945 | 3,121 | 0.779 | 0.767 | -1.2 [-2.4, -0.1] |
| football result_or_under >=0.70 | 41,246 | 6,411 | 0.823 | 0.815 | -0.8 [-1.4, -0.2] |
| football goals >=0.70 | 47,815 | 6,336 | 0.823 | 0.817 | -0.6 [-1.1, -0.1] |
| football result_or_over 0.60-0.70 | 12,707 | 6,203 | 0.669 | 0.680 | +1.1 [+0.1, +2.0] |
| football result_or_btts >=0.70 | 1,415 | 1,087 | 0.790 | 0.821 | +3.1 [+1.1, +5.0] |
| football both_over_corners >=0.70 | 1,359 | 930 | 0.839 | 0.880 | +4.1 [+2.2, +6.1] |
| tennis tennis_women:set1_won >=0.70 | 359 | 359 | 0.764 | 0.811 | +4.6 [+0.5, +8.3] |
| tennis tennis_women:set_score_not 0.60-0.70 | 339 | 228 | 0.632 | 0.678 | +4.7 [+0.8, +9.1] |
| football player_left_foot_shots 0.60-0.70 | 427 | 301 | 0.627 | 0.674 | +4.7 [+0.2, +9.0] |
| football result_handicap 0.60-0.70 | 1,123 | 1,123 | 0.652 | 0.720 | +6.9 [+4.5, +9.4] |

### T3b. Piłka / tenis: klucze z przedziałem bez zera (n >= 300): 58

| komórka | n | mecze | pewność | trafione | trafione - pewność, pp [95%] |
|---|---:|---:|---:|---:|---|
| football handicap_corners OVER 0.60-0.70 | 347 | 332 | 0.651 | 0.522 | -12.9 [-18.5, -7.8] |
| tennis handicap_games OVER 0.60-0.70 | 1,305 | 819 | 0.647 | 0.554 | -9.3 [-12.5, -6.2] |
| tennis games_won_set1_for UNDER 0.60-0.70 | 347 | 311 | 0.626 | 0.542 | -8.4 [-13.9, -2.9] |
| tennis handicap_games OVER >=0.70 | 812 | 469 | 0.765 | 0.691 | -7.4 [-11.5, -3.6] |
| football dc_and_over OVER >=0.70 | 447 | 379 | 0.768 | 0.696 | -7.2 [-12.6, -2.5] |
| football both_over_goals UNDER 0.60-0.70 | 729 | 729 | 0.615 | 0.543 | -7.2 [-10.9, -3.7] |
| tennis games_total UNDER 0.60-0.70 | 864 | 648 | 0.651 | 0.581 | -7.0 [-11.0, -3.2] |
| tennis match_won_for OVER >=0.70 | 301 | 301 | 0.797 | 0.728 | -7.0 [-12.0, -2.0] |
| tennis tennis_women:games_won_set2_for OVER 0.60-0.70 | 958 | 618 | 0.670 | 0.603 | -6.7 [-9.7, -3.3] |
| tennis games_set2_total UNDER 0.60-0.70 | 328 | 328 | 0.635 | 0.573 | -6.2 [-11.3, -0.7] |
| tennis games_won_set2_for UNDER 0.60-0.70 | 397 | 336 | 0.621 | 0.562 | -5.9 [-11.8, -0.3] |
| football both_over_cards_points UNDER >=0.70 | 439 | 379 | 0.821 | 0.765 | -5.5 [-10.0, -1.8] |
| football draw_no_bet UNDER >=0.70 | 357 | 357 | 0.800 | 0.748 | -5.2 [-9.8, -0.8] |
| football shots_for OVER >=0.70 | 819 | 380 | 0.781 | 0.733 | -4.9 [-9.4, -0.7] |
| football cards_points_total UNDER 0.60-0.70 | 619 | 619 | 0.651 | 0.603 | -4.8 [-8.4, -1.1] |
| tennis tennis_women:games_won_for OVER 0.60-0.70 | 716 | 435 | 0.664 | 0.616 | -4.8 [-8.7, -1.1] |
| tennis games_won_for UNDER 0.60-0.70 | 1,619 | 1,086 | 0.641 | 0.594 | -4.7 [-7.5, -2.0] |
| football shots_for UNDER >=0.70 | 816 | 358 | 0.758 | 0.712 | -4.6 [-8.2, -0.3] |
| tennis tennis_women:games_won_set2_for OVER >=0.70 | 1,522 | 623 | 0.804 | 0.758 | -4.6 [-7.3, -1.7] |
| football cards_points_for UNDER 0.60-0.70 | 668 | 545 | 0.657 | 0.611 | -4.6 [-8.3, -1.0] |
| football cards_points_for UNDER >=0.70 | 821 | 486 | 0.795 | 0.750 | -4.5 [-8.0, -1.1] |
| football cards_points_total UNDER >=0.70 | 1,221 | 687 | 0.814 | 0.773 | -4.1 [-7.3, -1.1] |
| football first_goal OVER 0.60-0.70 | 734 | 734 | 0.641 | 0.601 | -4.0 [-7.7, -0.5] |
| football shots_on_target_for OVER 0.60-0.70 | 586 | 434 | 0.655 | 0.618 | -3.7 [-7.5, -0.1] |
| tennis games_won_set2_for OVER 0.60-0.70 | 1,573 | 936 | 0.672 | 0.636 | -3.6 [-6.1, -1.2] |
| tennis games_won_for UNDER >=0.70 | 2,460 | 1,254 | 0.758 | 0.723 | -3.5 [-5.9, -1.1] |
| football both_over_goals UNDER >=0.70 | 1,584 | 1,584 | 0.841 | 0.807 | -3.4 [-5.3, -1.4] |
| football player_fouls_drawn_for OVER >=0.70 | 791 | 289 | 0.759 | 0.726 | -3.3 [-6.3, -0.2] |
| tennis games_won_for OVER >=0.70 | 1,521 | 979 | 0.798 | 0.767 | -3.1 [-5.6, -0.6] |
| football dc_and_over OVER 0.60-0.70 | 1,502 | 1,479 | 0.667 | 0.636 | -3.1 [-5.5, -0.6] |
| tennis games_won_set1_for UNDER >=0.70 | 2,100 | 1,281 | 0.871 | 0.842 | -2.9 [-4.4, -1.3] |
| tennis tennis_women:games_won_set1_for UNDER >=0.70 | 1,300 | 857 | 0.885 | 0.859 | -2.6 [-4.7, -0.9] |
| football corners_1h_total UNDER >=0.70 | 1,819 | 1,076 | 0.798 | 0.772 | -2.6 [-5.1, -0.2] |
| football result_or_clean_sheet OVER 0.60-0.70 | 2,469 | 1,164 | 0.647 | 0.622 | -2.5 [-4.7, -0.4] |
| football goals_1h_for UNDER 0.60-0.70 | 2,713 | 2,333 | 0.623 | 0.598 | -2.5 [-4.5, -0.7] |
| tennis games_set1_total UNDER >=0.70 | 2,283 | 1,172 | 0.808 | 0.784 | -2.4 [-4.6, -0.2] |
| football corners_total UNDER 0.60-0.70 | 2,000 | 1,985 | 0.637 | 0.615 | -2.2 [-4.3, -0.1] |
| tennis games_won_set2_for OVER >=0.70 | 3,193 | 1,005 | 0.817 | 0.797 | -2.0 [-3.7, -0.0] |
| football corners_total UNDER >=0.70 | 4,416 | 1,574 | 0.811 | 0.793 | -1.8 [-3.6, -0.0] |
| tennis games_won_set2_for UNDER >=0.70 | 2,093 | 1,269 | 0.881 | 0.863 | -1.7 [-3.1, -0.3] |
| football result_handicap OVER >=0.70 | 5,598 | 2,947 | 0.836 | 0.819 | -1.7 [-2.8, -0.6] |
| tennis games_won_set1_for OVER >=0.70 | 3,308 | 1,045 | 0.823 | 0.806 | -1.7 [-3.4, -0.1] |
| football goals_total UNDER >=0.70 | 8,047 | 5,016 | 0.816 | 0.801 | -1.5 [-2.5, -0.5] |
| football double_chance OVER >=0.70 | 9,987 | 6,361 | 0.784 | 0.770 | -1.4 [-2.2, -0.7] |
| football goals_2h_for UNDER >=0.70 | 3,217 | 1,444 | 0.846 | 0.832 | -1.3 [-2.7, -0.0] |
| football goals_for UNDER >=0.70 | 7,853 | 3,505 | 0.837 | 0.828 | -0.9 [-1.8, -0.0] |
| football result_or_under OVER >=0.70 | 41,246 | 6,411 | 0.823 | 0.815 | -0.8 [-1.4, -0.2] |
| football result_or_over OVER 0.60-0.70 | 12,707 | 6,203 | 0.669 | 0.680 | +1.1 [+0.1, +2.0] |
| tennis games_set2_total OVER >=0.70 | 1,952 | 1,164 | 0.835 | 0.854 | +1.9 [+0.1, +3.7] |
| tennis games_set1_total OVER >=0.70 | 1,956 | 1,167 | 0.828 | 0.852 | +2.3 [+0.5, +4.2] |
| football result_or_btts OVER >=0.70 | 1,415 | 1,087 | 0.790 | 0.821 | +3.1 [+1.1, +5.0] |
| tennis tennis_women:games_set1_total OVER >=0.70 | 1,381 | 796 | 0.850 | 0.881 | +3.1 [+1.1, +5.0] |
| football corners_2h_total OVER >=0.70 | 518 | 250 | 0.825 | 0.865 | +4.0 [+0.1, +7.8] |
| football both_over_corners OVER >=0.70 | 1,359 | 930 | 0.839 | 0.880 | +4.1 [+2.2, +6.1] |
| football goals_1h_total OVER 0.60-0.70 | 1,530 | 1,530 | 0.662 | 0.706 | +4.4 [+2.1, +6.8] |
| tennis tennis_women:set_score_not OVER 0.60-0.70 | 339 | 228 | 0.632 | 0.678 | +4.7 [+0.8, +9.1] |
| football player_left_foot_shots_for OVER 0.60-0.70 | 427 | 301 | 0.627 | 0.674 | +4.7 [+0.2, +9.0] |
| football result_handicap OVER 0.60-0.70 | 1,123 | 1,123 | 0.652 | 0.720 | +6.9 [+4.5, +9.4] |

Wielokrotność porównań: na poziomie kluczy (n >= 300) testowano 188 komórek piłki i tenisa. 58 ma przedział bez zera (47 obietnic ponad wynik, 11 pod), a losowo przy 5% spodziewałbym się ~9. Większość sygnału jest więc prawdziwa, ale pojedynczą komórkę z |luką| < 2 pp trzeba czytać ostrożnie.

Odczyt: piłka jako całość trzyma się blisko krzywej (−0,6 pp). Dryf skupia się w kartkach (`cards_points` −2,1 / −2,7 pp, `both_over_cards_points` UNDER −5,5 pp) i strzałach (`shots` −3,5 pp). To dokładnie rodziny, w których od 10-21 SHEET czyta stawkę sędziego i składnik bliskości, a zawodnik ma udział w centrum drużyny, przy czym krzywa była dopasowana bez nich (CLAUDE.md: „Neither the referee nor the share is replayed by a refit yet”). Dochodzą krzywe wycinków rynków wyniku (`dc_and_over` −7,2 pp, `draw_no_bet` UNDER −5,2 pp), dopasowane bez replayu (model-state (c), score-market slice curves). Tenis jest przesunięty szerzej: `games_won` −3,4 pp, `handicap_games` −7,4 / −9,3 pp, `match_won_for` −7,0 pp. Tenisowe krzywe dopasowano bez P14 (`TENNIS_RATING_SCORE_WINNER`), a od 10-28 `handicap_games` per set czyta sąsiadów ratingu (R2) bez własnego klucza krzywej.

Miara operatora: w przedziale druku (>= 0.70) linie wypadają **poniżej ceny bez marży** o 1,5 pp w piłce i 1,6 pp w tenisie (T2). Brier p modelu wobec ceny dla każdego sportu policzono dziś w `data/refit_2026-11-05_coverage/yardstick.json` (10-22..11-04, użyty bez przeliczania). We wszystkich sportach cena jest lepsza: piłka +0,00498 [+0,00431, +0,00577], tenis +0,00853, hokej drużyny +0,00462, zawodnicy +0,00254, koszykówka drużyny +0,01144, zawodnicy +0,00442, siatkówka +0,00876, CS2 drużyny +0,00361, zawodnicy +0,00273. Nawet po kalibracji Platta w próbie (górna granica dla każdej krzywej na tych wierszach) cena zostaje lepsza wszędzie poza zawodnikami koszykówki (+0,00092 [−0,00028, +0,00206]) i CS2 (+0,00081 [−0,00025, +0,00169]). **Żaden refit krzywej nie przeniesie modelu ponad cenę.** Krzywa poprawia tylko uczciwość pewności.

### T4. Sporty mierzone: krzywa zainstalowana i dzisiejszy dry-run

| sport | ramię | pasmo | n | mecze | pewność | trafione | trafione - pewność, pp [95%] |
|---|---|---|---:|---:|---:|---:|---|
| hockey | installed | 0.60-0.70 | 7,931 | 1,126 | 0.639 | 0.646 | +0.7 [-0.5, +1.8] |
| hockey | installed | >=0.70 | 6,801 | 1,004 | 0.781 | 0.786 | +0.5 [-0.8, +1.7] |
| hockey | installed_on_dry_oos | 0.60-0.70 | 7,931 | 1,126 | 0.639 | 0.646 | +0.7 [-0.5, +1.8] |
| hockey | installed_on_dry_oos | >=0.70 | 6,801 | 1,004 | 0.781 | 0.786 | +0.5 [-0.8, +1.7] |
| hockey | dry_run | 0.60-0.70 | 6,344 | 1,084 | 0.643 | 0.643 | +0.1 [-1.1, +1.3] |
| hockey | dry_run | >=0.70 | 5,901 | 909 | 0.789 | 0.791 | +0.2 [-1.0, +1.6] |
| basketball | installed | 0.60-0.70 | 15,511 | 2,030 | 0.644 | 0.561 | -8.4 [-9.8, -7.0] |
| basketball | installed | >=0.70 | 3,898 | 1,071 | 0.749 | 0.616 | -13.4 [-16.7, -9.9] |
| basketball | installed_on_dry_oos | 0.60-0.70 | 14,087 | 1,846 | 0.644 | 0.559 | -8.6 [-10.1, -7.1] |
| basketball | installed_on_dry_oos | >=0.70 | 3,646 | 971 | 0.750 | 0.616 | -13.4 [-16.9, -10.1] |
| basketball | dry_run | 0.60-0.70 | 13,693 | 1,915 | 0.642 | 0.560 | -8.2 [-9.7, -6.7] |
| basketball | dry_run | >=0.70 | 3,168 | 723 | 0.753 | 0.595 | -15.8 [-19.7, -12.1] |
| volleyball | installed | 0.60-0.70 | 3,173 | 1,193 | 0.640 | 0.580 | -6.0 [-8.0, -4.0] |
| volleyball | installed | >=0.70 | 3,750 | 1,102 | 0.806 | 0.768 | -3.8 [-5.6, -2.0] |
| volleyball | installed_on_dry_oos | 0.60-0.70 | 2,695 | 978 | 0.640 | 0.579 | -6.0 [-8.2, -3.8] |
| volleyball | installed_on_dry_oos | >=0.70 | 3,265 | 905 | 0.807 | 0.779 | -2.8 [-4.7, -0.9] |
| volleyball | dry_run | 0.60-0.70 | 2,119 | 938 | 0.645 | 0.563 | -8.2 [-11.1, -5.5] |
| volleyball | dry_run | >=0.70 | 2,173 | 883 | 0.784 | 0.736 | -4.8 [-7.5, -2.4] |
| cs2 | installed | 0.60-0.70 | 2,400 | 450 | 0.643 | 0.654 | +1.1 [-1.8, +4.2] |
| cs2 | installed | >=0.70 | 1,072 | 264 | 0.752 | 0.759 | +0.8 [-3.8, +5.3] |
| cs2 | installed_on_dry_oos | 0.60-0.70 | 2,400 | 450 | 0.643 | 0.654 | +1.1 [-1.8, +4.2] |
| cs2 | installed_on_dry_oos | >=0.70 | 1,072 | 264 | 0.752 | 0.759 | +0.8 [-3.8, +5.3] |
| cs2 | dry_run | 0.60-0.70 | 2,323 | 417 | 0.640 | 0.647 | +0.7 [-2.2, +3.6] |
| cs2 | dry_run | >=0.70 | 1,171 | 294 | 0.750 | 0.761 | +1.1 [-3.3, +5.8] |

| sport | zainstalowana od | linie | dry-run - zainstalowana, Brier [95%] | n | klucze lepsze / gorsze |
|---|---|---:|---|---:|---|
| hockey | 2026-10-23 | 50,055 | +0.00047 [+0.00039, +0.00056] | 43,478 | 1 / 9 z 16 |
| basketball | 2026-10-14 | 217,008 | +0.00060 [+0.00055, +0.00065] | 186,134 | 3 / 21 z 36 |
| volleyball | 2026-10-07 | 48,235 | -0.00015 [-0.00033, +0.00003] | 30,667 | 4 / 4 z 16 |
| cs2 | 2026-10-13 | 61,934 | +0.00007 [+0.00000, +0.00014] | 16,033 | 0 / 1 z 16 |

### T5. Sporty: klucze krzywej zainstalowanej z przedziałem bez zera (n >= 300): 25

| komórka | n | mecze | pewność | trafione | trafione - pewność, pp [95%] |
|---|---:|---:|---:|---:|---|
| volleyball points_handicap TEAM >=0.70 | 440 | 282 | 0.802 | 0.554 | -24.8 [-31.9, -18.3] |
| basketball h1_handicap TEAM >=0.70 | 453 | 279 | 0.766 | 0.536 | -22.9 [-29.8, -16.2] |
| basketball h1_total OVER >=0.70 | 304 | 144 | 0.754 | 0.576 | -17.9 [-27.1, -9.2] |
| volleyball points_total UNDER 0.60-0.70 | 545 | 364 | 0.623 | 0.470 | -15.3 [-20.7, -8.9] |
| basketball h1_handicap TEAM 0.60-0.70 | 1,639 | 921 | 0.648 | 0.512 | -13.5 [-16.9, -10.1] |
| basketball h2_team_total UNDER 0.60-0.70 | 578 | 243 | 0.667 | 0.536 | -13.1 [-19.3, -7.6] |
| basketball quarter_handicap TEAM >=0.70 | 413 | 234 | 0.744 | 0.613 | -13.1 [-19.9, -6.1] |
| volleyball points_handicap TEAM 0.60-0.70 | 622 | 422 | 0.667 | 0.540 | -12.7 [-17.5, -7.4] |
| basketball h2_total UNDER 0.60-0.70 | 364 | 169 | 0.655 | 0.530 | -12.5 [-20.5, -4.3] |
| basketball h1_team_total UNDER 0.60-0.70 | 913 | 503 | 0.669 | 0.546 | -12.2 [-16.4, -8.2] |
| basketball h2_team_total OVER 0.60-0.70 | 370 | 182 | 0.616 | 0.500 | -11.6 [-18.1, -5.1] |
| basketball h2_handicap TEAM 0.60-0.70 | 648 | 260 | 0.645 | 0.529 | -11.6 [-17.2, -6.3] |
| basketball quarter_team_total UNDER 0.60-0.70 | 653 | 311 | 0.681 | 0.571 | -10.9 [-15.3, -6.4] |
| basketball h1_total OVER 0.60-0.70 | 924 | 530 | 0.624 | 0.519 | -10.4 [-15.0, -6.0] |
| basketball quarter_handicap TEAM 0.60-0.70 | 1,439 | 715 | 0.646 | 0.544 | -10.2 [-13.2, -7.6] |
| basketball quarter_total UNDER 0.60-0.70 | 610 | 307 | 0.674 | 0.585 | -8.9 [-14.0, -3.7] |
| basketball quarter_team_total OVER 0.60-0.70 | 685 | 373 | 0.630 | 0.542 | -8.8 [-12.8, -5.1] |
| basketball h1_team_total OVER 0.60-0.70 | 1,020 | 538 | 0.620 | 0.536 | -8.3 [-12.4, -4.6] |
| basketball h1_total UNDER 0.60-0.70 | 699 | 407 | 0.653 | 0.581 | -7.2 [-12.2, -2.3] |
| basketball quarter_total OVER 0.60-0.70 | 643 | 380 | 0.620 | 0.558 | -6.1 [-10.9, -1.8] |
| basketball quarter_dnb TEAM 0.60-0.70 | 456 | 218 | 0.631 | 0.575 | -5.7 [-10.8, -1.2] |
| basketball quarter_1x2 TEAM 0.60-0.70 | 519 | 335 | 0.626 | 0.582 | -4.4 [-8.6, -0.1] |
| volleyball set_handicap TEAM >=0.70 | 1,043 | 581 | 0.809 | 0.768 | -4.1 [-6.9, -1.5] |
| volleyball team_sets_exact NO >=0.70 | 688 | 175 | 0.842 | 0.866 | +2.4 [+0.7, +4.2] |
| hockey period_total OVER >=0.70 | 627 | 547 | 0.809 | 0.844 | +3.5 [+0.7, +6.4] |

Odczyt sportów: hokej i CS2 są skalibrowane (przedziały obejmują zero). Koszykówka obiecuje za dużo o 13,4 pp przy >= 0.70 i 8,4 pp przy 0.60–0.70, siatkówka o 3,8 / 6,0 pp, i to w obu ramionach. Dry-run jest w koszykówce gorszy (−15,8 pp). Rodziny połówek i kwart koszykówki oraz punkty siatkówki (T5) to znana kwestia z model-state (e): rozrzut okresów w lidze, „Volleyball overstates ~16 pp”. Odświeżenie okna jej nie naprawia. Dziś łapie to dowód linii (offset + cap), dopasowany co rano.

## 3. Czy refit na dzisiejszej historii pomoże? Kandydaci od najbardziej obiecującego

Bez refitu, z dryfu, przyrostu i historii poprzednich prób:

1. **Tenis: krzywe z replayem P14 (+ R2 dla per-setowego handicapu).** Największy dryf w przedziale druku (−1,7 pp przy >= 0.70, −3,0 pp przy 0.60–0.70; `games_won`, `handicap_games`, `match_won_for`). Replay P14 nie istnieje: `prepare_refit.UNREPLAYED_AUDIT_SWITCHES` tylko ostrzega. Najpierw trzeba dopisać `score_winner` do `RatingReplay.from_db` i zmierzyć populację gier tenisowych bez `/statistics` (model-state (e) „Before the next refit”). Spodziewany efekt: kalibracja o 1–3 pp w tenisie, ROI bez zmian. Model punktowy tenisa buduje inny agent; to nie jest tutaj dublowane.
2. **Piłka: kartki i strzały z replayem sędziego i udziału zawodnika.** Dryf −2..−5 pp w `cards_points*`, `shots*`, `player_fouls_drawn`. Flagi replayu dla sędziego i udziału nie istnieją (sprawdzone: brak `--referee` / `--player-share` w `calibrate_from_cache.py` i `prepare_refit.py`), a rekord sędziów pokrywa ~połowę meczów (model-state (e)). Zysk, czyli zbicie luki do ~0, możliwy tylko po zbudowaniu tych replayów. Sam refit na +15,9% zdarzeń powtórzyłby wynik z 10-22 (ruchy <= 0,17 pp).
3. **Krzywe wycinków rynków wyniku** (`dc_and_over`, `draw_no_bet`, `double_chance` −1,4 pp): `fit_score_market_curves.py` na świeżych wierszach 1X2/DNB. Tanie, bez pełnego replayu, ale trzeba je zmierzyć.
4. **Sporty: hybrydy kluczy z dry-runu.** Lepsze na liniach od 10-17 są: koszykówka `h1_handicap` −0,00154 i `quarter_handicap` −0,00112 Briera, hokej `handicap` −0,00030, siatkówka `set_handicap` −0,00052 i `points_handicap` −0,00017. Wybrane **po wyniku** (wybór po fakcie), więc najwyżej jako test zarejestrowany z góry na danych od 11-06. Siatkówki `set_winner` (−0,0025) nie wolno: to rodzina dopasowana z naszych rozliczonych dni (twarda reguła). Cały refit sportów: nie (T4).
5. **Model zawodników** (10-02, cięcie 07-01): NBA 2026-27 ma zaplanowany ponowny pomiar przy ~200 meczach (koniec listopada, model-state (d)). Teraz nic.

**Flagi, które każdy refit piłki / tenisa musi nieść:** 21 flag z `fitted_from.replay_rules.flags` (`halves, derived=cards_points,goals,corners,shots_on_target, tennis_rating, count_dispersion, cards_correlation, per_market_k, tennis_scoped_table, football_rating, rated_scope, venue_prior, game_state, rating_weight, season_phase, opponent_correction, tennis_set_ratings, cup_strength, sample_cup_strength, tennis_sample_scope, goals_stretch, count_stretch, player_stretch`), do tego `--awarded-excluded` (install wymaga go przy włączonym `AWARDED_EXCLUDED`) oraz `--closeness-stretch --player-coverage` (przełączniki z 10-21 mają już replay, tak jak użył ich kandydat z 10-22). **Nigdy** `--tennis-serve-markets` / `--tennis-aces-opponent`. Bez replayu (tylko ostrzeżenie): referee, player share, P1 `SAMPLE_CONFLICT_CUT`, P3 football `PLAYER_HISTORY_ANY_TEAM`, P5 `PLAYER_SLUG_NAME`, P14. Sporty: P7 (CS2), P13 (siatkówka) w `fitted_from.unreplayed_switches`. Utwardzenie z (e): `fit_confidence` czyta też żywe wiersze `sofa_settled_row`, więc klucze żywe trzeba zamrozić albo wykluczyć.

## 4. Dysk: plan bezpieczny (nic nie usunięte, nic nie przeniesione)

### T6. data/sofa.db: tabele i indeksy (dbstat)

| obiekt | typ | tabela | GB | komórki |
|---|---|---|---:|---:|
| sofa_entity_events | table | sofa_entity_events | 17.05 | 260,343 |
| sofa_event_stats | table | sofa_event_stats | 10.56 | 879,096 |
| sofa_listed_event | table | sofa_listed_event | 9.80 | 2,470,022 |
| sofa_settled_row | table | sofa_settled_row | 9.78 | 62,519,900 |
| sqlite_autoindex_sofa_settled_row_1 | index | sofa_settled_row | 3.37 | 60,139,782 |
| sofa_event_extra | table | sofa_event_extra | 2.45 | 208,378 |
| sofa_settled_row_run_date | index | sofa_settled_row | 1.84 | 60,139,782 |
| sofa_event_detail | table | sofa_event_detail | 0.44 | 93,835 |
| sofa_listing_event | table | sofa_listing_event | 0.20 | 3,362,487 |
| sofa_listed_event_sport | index | sofa_listed_event | 0.17 | 1,840,126 |

Strony: 13,644,476 x 4096 B, wolne 8; wiersze sofa_settled_row: cache-calibration 58,175,184, live 1,964,598; dysk wolny 19.6 GB.

| plik bazy > 1 GB | GB | zmieniony |
|---|---:|---|
| data/kupon_redesign_2026-10-31/sofa_copy.db | 54.3 | 2026-10-31 |
| data/refit_2026-10-17/sofa_replay.db | 64.0 | 2026-10-17 |
| data/refit_2026-10-20_cs2pk/sofa_copy.db | 47.5 | 2026-10-20 |
| data/refit_2026-10-22/comp_spread/bb.db | 3.6 | 2026-10-22 |
| data/refit_2026-10-23_allin/live/sofa.db | 53.4 | 2026-10-23 |
| data/refit_2026-10-23_allin/sofa_copy.db | 53.3 | 2026-10-23 |
| data/refit_card_halves_2026-10-21/football_incidents/incidents.db | 2.8 | 2026-10-20 |
| data/refit_card_halves_terms_2026-10-21/football_incidents/incidents.db | 2.8 | 2026-10-21 |
| data/ruch_kursu_2026-11-01/settled.db | 5.8 | 2026-11-01 |
| data/sofa.db | 55.9 | 2026-11-05 |

Rachunek z T6:
- `sofa_settled_row` z indeksami zajmuje 9,78 + 3,37 + 1,84 = 15,0 GB, z czego 58 175 184 / 60 139 782 wierszy (97%) to stare wiersze `cache-calibration`. Replay i tak je kasuje i pisze od nowa (`calibrate_from_cache.py`, DELETE + INSERT). W produkcji nikt ich nie potrzebuje: CONFIDENCE czyta krzywe, a nie te wiersze.
- Tabele, które replay czyta (z kodu): `sofa_event_stats`, `sofa_listed_event`, `sofa_event_detail`, `sofa_entity_events` (ratingi, historia sportów), `sofa_listing_event` (+ `sofa_listing_index_progress`), `cs2_*`, `sofa_event_referee` (na przyszły replay sędziego), żywe wiersze `sofa_settled_row`, a do tego `sofa_entity` / `sofa_tournament_map` (małe). Nie czyta: `sofa_event_extra` (2,45 GB), `sofa_day_listing`, kolejek encji, `sofa_listing_miss`, `sofa_referee_page`.
- **Chuda kopia** (wszystkie tabele poza `sofa_event_extra` i wierszami `cache-calibration`): ~55,9 − 14,5 − 2,45 ≈ **39 GB**. Replay dopisuje ~120 mln wierszy, czyli ~29 GB w skali 15 GB / 60 mln (baza replayu 10-17 urosła do 64 GB). Razem **~68 GB**. Przy wolnych 19,6 GB nie mieści się ani pełna kopia, ani chuda.
- Na dysku leżą cztery pełne kopie robocze (żadna nie jest otwarta, sprawdzone `lsof`): `data/refit_2026-10-23_allin/sofa_copy.db` 53,3 GB, `data/refit_2026-10-23_allin/live/sofa.db` 53,4 GB, `data/kupon_redesign_2026-10-31/sofa_copy.db` 54,3 GB, `data/refit_2026-10-20_cs2pk/sofa_copy.db` 47,5 GB. Razem **208,5 GB**. Do tego `data/refit_2026-10-17/sofa_replay.db` 64,0 GB (model-state (c): „keep”, baza krzywych 10-17) oraz `data/line_evidence/rows_before_*` ~39 GB (19 katalogów po 1,7–2,3 GB, a model-state mówi o dwóch najnowszych).

Plan (każdy krok wymaga zgody operatora, bo żaden nie jest odwracalny przez nas):
1. Operator przenosi na dysk zewnętrzny (albo usuwa, jeśli uzna, że ich cel się skończył) cztery kopie robocze: **+208 GB**. `refit_2026-10-23_allin/live/sofa.db` ma w nazwie „live”, więc trzeba najpierw potwierdzić, że to kopia z 10-23, a nie kopia zapasowa, której ktoś potrzebuje.
2. Opcjonalnie stare `data/line_evidence/rows_before_<d>` poza dwoma najnowszymi: **~35 GB**. Dowód linii czyta tylko dzień bieżący.
3. Bazę replayu 10-17 zostawić do czasu instalacji nowego refitu (to punkt odniesienia `fitted_from.db_path`), potem przenieść.
4. Refit dopiero po kroku 1. Kopia przez `VACUUM INTO` (pełna, ~56 GB) albo chuda: nowa baza + `ATTACH` + `INSERT ... SELECT` tabela po tabeli bez `cache-calibration`, schemat z `sqlite_master`. Chuda kopia wymaga skryptu i testu, że replay na niej daje te same wiersze co na pełnej (próba na jednym dniu). Prościej i bezpieczniej jest robić pełne `VACUUM INTO` po zwolnieniu miejsca.
5. W żywej bazie **nie** kasować wierszy `cache-calibration` bez decyzji operatora (14,5 GB). Pomogłoby to dopiero po `VACUUM` (wolna lista ma dziś 8 stron), które wymaga drugiego tyle miejsca i zatrzymania pętli.

## Czego nie sprawdzono

- Liczby meczów ze statystykami (populacji replayu) w bazie 10-17 i dziś. Porównanie listingów to tylko jej przybliżenie.
- Efektu refitu piłki / tenisa (wymaga replayu, a ten nie mieści się na dysku). Kierunek wnioskuję z próby 10-22.
- Modelu zawodników, baz tenisowych wg poziomu i stałych CS2 nie audytowano na liniach. Podałem tylko daty i źródła.
