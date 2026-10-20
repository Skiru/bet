<!-- PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_selection_walk_forward.py --from 2026-10-12 --to 2026-10-19 (uruchomione 2026-10-20). Źródło TIER_SHORTFALL w bet.sofa.slip_builder. Okno rejestracji T-FAMILY-SELECTION zaczyna się 2026-10-19: dni 10-12..10-18 to dane, na których regułę wymyślono, nie test. -->
# Selekcja nóg walk-forward, dni testu 2026-10-12..2026-10-19

Rodziny z dni przed każdym dniem (`family_record.window`, >= 50 nóg, jednostki > 0); ROI przy cenie wydruku, przedziały 95% z losowania (dzień, mecz).

| selekcja | nogi | mecze | trafione | 1/kurs | jednostki | ROI [95%] |
|---|---|---|---|---|---|---|
| cały kupon | 30188 | 3779 | 0.782 | 0.823 | -1500.87 | -5.0% [-5.8, -4.1] |
| x >= 1 | 6046 | 2039 | 0.740 | 0.764 | -187.90 | -3.1% [-5.3, -0.9] |
| rodzina na plusie | 4996 | 1581 | 0.799 | 0.815 | -98.90 | -2.0% [-3.9, +0.0] |
| kurs 1.40-2.00 | 1902 | 1230 | 0.661 | 0.680 | -49.77 | -2.6% [-6.4, +0.8] |
| x >= 1 i rodzina na plusie (przycisk widoku) | 1430 | 697 | 0.755 | 0.763 | -12.78 | -0.9% [-5.0, +2.9] |
| reszta kuponu (bez selekcji) | 28758 | 3743 | 0.783 | 0.826 | -1488.09 | -5.2% [-6.0, -4.4] |

**Selekcja minus reszta: +4.3 pp [+0.4, +8.1]** (pary na tych samych losowaniach). Selekcja lepsza od reszty w 8 z 8 dni; największy dzień to 72% nóg selekcji.

| dzień | okno (dni) | nogi dnia | selekcja: nogi | ROI selekcji | ROI reszty | selekcja - reszta |
|---|---|---|---|---|---|---|
| 2026-10-12 | 3 | 718 | 21 | +10.6% | -6.3% | +16.9 pp |
| 2026-10-13 | 4 | 1029 | 36 | -1.0% | -4.0% | +3.1 pp |
| 2026-10-14 | 5 | 1195 | 47 | +8.0% | -6.2% | +14.2 pp |
| 2026-10-15 | 6 | 1414 | 74 | +2.5% | -1.2% | +3.7 pp |
| 2026-10-16 | 7 | 3076 | 65 | -1.2% | -3.5% | +2.3 pp |
| 2026-10-17 | 8 | 12042 | 1024 | -1.3% | -5.0% | +3.7 pp |
| 2026-10-18 | 9 | 8829 | 129 | -4.9% | -6.7% | +1.8 pp |
| 2026-10-19 | 10 | 1885 | 34 | -0.3% | -3.8% | +3.6 pp |

Selekcja wg sportu:

| sport | nogi | mecze | trafione | 1/kurs | jednostki | ROI [95%] |
|---|---|---|---|---|---|---|
| football | 1337 | 610 | 0.757 | 0.764 | -10.49 | -0.8% [-5.0, +3.2] |
| hockey | 74 | 68 | 0.730 | 0.734 | -0.53 | -0.7% [-16.2, +13.2] |
| tennis | 19 | 19 | 0.737 | 0.797 | -1.76 | -9.3% [-35.3, +13.5] |

Rodziny na plusie w dniu testu:
- 2026-10-12: football|corners_total|OVER, hockey|period_total|UNDER, hockey|total|UNDER
- 2026-10-13: football|corners_1h_total|OVER, football|corners_for|OVER, football|corners_total|OVER, football|shots_for|OVER, hockey|period_total|UNDER, hockey|total|UNDER
- 2026-10-14: football|corners_1h_total|OVER, football|corners_total|OVER, football|shots_for|OVER, football|shots_on_target_for|OVER, football|shots_on_target_total|OVER, hockey|total|UNDER, tennis|games_set1_total|OVER
- 2026-10-15: football|corners_1h_total|OVER, football|corners_for|OVER, football|corners_total|OVER, football|shots_for|OVER, football|shots_on_target_for|OVER, football|shots_on_target_total|OVER, hockey|total|UNDER, tennis|games_set1_total|OVER, tennis|games_set2_total|OVER, tennis|games_set2_total|UNDER
- 2026-10-16: football|cards_points_total|UNDER, football|corners_for|OVER, football|corners_total|OVER, football|shots_for|OVER, football|shots_on_target_for|OVER, football|shots_on_target_total|OVER, football|shots_total|OVER, hockey|total|UNDER, tennis|games_set2_total|OVER, tennis|games_set2_total|UNDER
- 2026-10-17: football|cards_points_total|UNDER, football|corners_for|OVER, football|corners_total|OVER, football|result_or_under|OVER, football|shots_for|OVER, football|shots_on_target_for|OVER, football|shots_on_target_total|OVER, football|shots_total|OVER, hockey|total|UNDER, tennis|games_set2_total|OVER
- 2026-10-18: football|corners_1h_for|UNDER, football|corners_for|OVER, football|corners_total|OVER, football|shots_for|OVER, football|shots_on_target_total|OVER, football|shots_total|OVER, hockey|total|UNDER, tennis|games_set2_total|OVER
- 2026-10-19: football|corners_for|OVER, football|corners_total|OVER, football|draw_no_bet|OVER, football|red_cards_total|UNDER, football|shots_for|OVER, football|shots_for|UNDER, football|shots_on_target_total|OVER, football|shots_total|OVER, hockey|period_handicap|T2, hockey|player_pp_points|UNDER, hockey|total|UNDER, tennis|games_set2_total|OVER

Wszystkie nogi 2026-10-09..2026-10-19:

| sport | nogi | mecze | trafione | 1/kurs | jednostki | ROI [95%] |
|---|---|---|---|---|---|---|
| wszystkie sporty | 35842 | 5044 | 0.781 | 0.821 | -1746.20 | -4.9% [-5.6, -4.1] |
| basketball | 189 | 115 | 0.571 | 0.691 | -29.98 | -15.9% [-33.9, +2.7] |
| cs2 | 161 | 51 | 0.783 | 0.789 | -1.37 | -0.9% [-11.9, +9.6] |
| football | 30438 | 3520 | 0.780 | 0.822 | -1544.48 | -5.1% [-5.9, -4.2] |
| hockey | 2559 | 605 | 0.804 | 0.825 | -65.13 | -2.5% [-5.0, -0.3] |
| tennis | 2331 | 642 | 0.790 | 0.824 | -97.17 | -4.2% [-6.7, -1.7] |
| volleyball | 164 | 111 | 0.726 | 0.767 | -8.07 | -4.9% [-14.9, +4.2] |

Kalibracja wg sportu:

| sport | nogi | mecze | pewność | trafione | luka [95%] | ROI | jednostki |
|---|---|---|---|---|---|---|---|
| basketball | 189 | 115 | 0.745 | 0.571 | -17.3 pp [-28.2, -6.3] | -15.9% | -30.0 |
| cs2 | 161 | 51 | 0.761 | 0.783 | +2.2 pp [-6.0, +9.3] | -0.9% | -1.4 |
| football | 30438 | 3520 | 0.794 | 0.780 | -1.4 pp [-2.1, -0.8] | -5.1% | -1544.5 |
| hockey | 2559 | 605 | 0.784 | 0.804 | +2.0 pp [+0.1, +3.7] | -2.5% | -65.1 |
| tennis | 2331 | 642 | 0.788 | 0.790 | +0.2 pp [-1.8, +2.1] | -4.2% | -97.2 |
| volleyball | 164 | 111 | 0.762 | 0.726 | -3.7 pp [-11.0, +2.6] | -4.9% | -8.1 |

Rynki z największą stratą (>= 60 nóg):

| sport / rynek / kierunek | nogi | mecze | pewność | trafione | luka [95%] | ROI | jednostki |
|---|---|---|---|---|---|---|---|
| football / result_or_over / OVER | 4778 | 1675 | 0.798 | 0.784 | -1.4 pp [-2.9, +0.3] | -6.3% | -299.5 |
| football / result_or_under / OVER | 5579 | 1832 | 0.801 | 0.779 | -2.2 pp [-3.7, -0.6] | -5.4% | -298.9 |
| football / double_chance / OVER | 2356 | 1808 | 0.780 | 0.763 | -1.7 pp [-3.3, -0.2] | -6.0% | -140.9 |
| football / goals_total / UNDER | 1649 | 1337 | 0.796 | 0.768 | -2.9 pp [-5.3, -0.7] | -6.6% | -108.1 |
| football / goals_total / OVER | 1185 | 1160 | 0.792 | 0.769 | -2.4 pp [-4.7, -0.2] | -6.8% | -80.5 |
| football / goals_2h_total / OVER | 1157 | 1157 | 0.795 | 0.784 | -1.1 pp [-3.5, +1.3] | -6.1% | -70.2 |
| football / goals_2h_total / UNDER | 1209 | 1185 | 0.790 | 0.779 | -1.1 pp [-3.7, +1.3] | -5.1% | -61.8 |
| football / goals_for / UNDER | 1096 | 901 | 0.802 | 0.769 | -3.3 pp [-5.9, -0.8] | -5.6% | -61.8 |
| football / corners_total / UNDER | 1307 | 648 | 0.802 | 0.787 | -1.6 pp [-4.7, +1.4] | -4.5% | -58.8 |
| football / goals_for / OVER | 599 | 540 | 0.786 | 0.735 | -5.1 pp [-8.8, -1.8] | -9.5% | -57.0 |

## basketball: luka kalibracji i ROI wg pewność - 1/kurs (2026-10-09..2026-10-19)

| pewność - 1/kurs | nogi | luka (trafione - pewność) [95%] | ROI |
|---|---|---|---|
| -1.00..-0.05 | 38 | -19.0 pp [-35.3, -4.3] | -32.2% |
| -0.05..-0.02 | 26 | -16.1 pp [-33.9, +5.4] | -26.3% |
| +0.03..+1.00 | 95 | -15.2 pp [-32.3, -0.6] | -1.3% |

## cs2: luka kalibracji i ROI wg pewność - 1/kurs (2026-10-09..2026-10-19)

| pewność - 1/kurs | nogi | luka (trafione - pewność) [95%] | ROI |
|---|---|---|---|
| -1.00..-0.05 | 72 | +6.9 pp [-2.4, +14.8] | +0.2% |
| -0.05..-0.02 | 28 | -0.6 pp [-14.1, +13.0] | -5.5% |
| -0.02..+0.00 | 20 | -15.8 pp [-38.4, +5.1] | -22.3% |
| +0.00..+0.03 | 24 | +2.9 pp [-14.4, +18.2] | +5.2% |

## football: luka kalibracji i ROI wg pewność - 1/kurs (2026-10-09..2026-10-19)

| pewność - 1/kurs | nogi | luka (trafione - pewność) [95%] | ROI |
|---|---|---|---|
| -1.00..-0.05 | 10474 | +1.6 pp [+0.8, +2.5] | -6.0% |
| -0.05..-0.02 | 8940 | -1.3 pp [-2.3, -0.3] | -5.8% |
| -0.02..+0.00 | 4499 | -2.5 pp [-4.0, -1.1] | -4.3% |
| +0.00..+0.03 | 3764 | -3.0 pp [-4.8, -1.5] | -2.0% |
| +0.03..+1.00 | 2761 | -9.5 pp [-11.7, -7.2] | -4.5% |

## hockey: luka kalibracji i ROI wg pewność - 1/kurs (2026-10-09..2026-10-19)

| pewność - 1/kurs | nogi | luka (trafione - pewność) [95%] | ROI |
|---|---|---|---|
| -1.00..-0.05 | 1240 | +3.8 pp [+1.5, +6.2] | -3.3% |
| -0.05..-0.02 | 779 | +0.7 pp [-2.2, +3.5] | -3.8% |
| -0.02..+0.00 | 273 | +0.2 pp [-5.0, +4.8] | -1.6% |
| +0.00..+0.03 | 149 | +4.9 pp [-2.0, +11.2] | +8.2% |
| +0.03..+1.00 | 118 | -8.9 pp [-18.1, -0.3] | -2.7% |

## tennis: luka kalibracji i ROI wg pewność - 1/kurs (2026-10-09..2026-10-19)

| pewność - 1/kurs | nogi | luka (trafione - pewność) [95%] | ROI |
|---|---|---|---|
| -1.00..-0.05 | 955 | +2.3 pp [-0.3, +4.9] | -5.2% |
| -0.05..-0.02 | 793 | +1.3 pp [-2.0, +4.4] | -2.8% |
| -0.02..+0.00 | 262 | -1.0 pp [-6.0, +4.0] | -2.5% |
| +0.00..+0.03 | 165 | -5.0 pp [-12.9, +2.0] | -5.3% |
| +0.03..+1.00 | 156 | -11.2 pp [-18.6, -4.1] | -6.6% |

## volleyball: luka kalibracji i ROI wg pewność - 1/kurs (2026-10-09..2026-10-19)

| pewność - 1/kurs | nogi | luka (trafione - pewność) [95%] | ROI |
|---|---|---|---|
| -1.00..-0.05 | 31 | -5.8 pp [-23.4, +8.3] | -15.7% |
| -0.05..-0.02 | 42 | +1.5 pp [-11.5, +14.1] | -3.0% |
| -0.02..+0.00 | 26 | +1.0 pp [-17.5, +14.4] | -0.8% |
| +0.00..+0.03 | 25 | -3.3 pp [-21.2, +12.3] | -3.0% |
| +0.03..+1.00 | 40 | -10.8 pp [-28.5, +4.4] | -2.5% |

