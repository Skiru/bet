# Bramki próbki zawodników (THIN_SAMPLE / LINE_BEYOND_SAMPLE / MODE_LOSES) - pomiar 2026-10-16

**Pytanie.** Na 10-15 z 19 018 wierszy zawodników (piłka) wydrukowało się 5. Z 57, które przeszły krzywą, line evidence i x >= 0.90, 54 odcięły bramki kształtu próbki CONFIDENCE (`MIN_BUILDER_SAMPLE` 10, `line_is_beyond_sample`, `mode_loses`). Próbka zawodnika to od 10-12 jego starty w 10 ostatnich meczach drużyny (5-10 wartości), więc `THIN_SAMPLE` przepuszcza tylko zawodnika z 10/10 startów. Krzywe zawodników są fitowane na replayu z próbką od 5 startów i bez bramek kształtu (`calibrate_from_cache.player_rows_for_event`, `min_sample` 5). Czy bramki chronią nogę przed przeszacowaniem?

**Metoda.** `scripts/sofa/measure_player_sample_gates.py` (tylko odczyt):
1. historia - replay wierszy zawodników (starty) z `data/refit_2026-10-16b/sofa_replay.db` tym samym kodem, z zapamiętaną próbką każdego wiersza; pewność = zainstalowana krzywa (przed line evidence); wiersze z pewnością >= 0.70 pogrupowane wg bramki, która by je odcięła (kolejność `run_confidence`), i wg liczby startów; bootstrap po meczach. Krzywa była fitowana na tych wierszach (łączna luka ~0 z konstrukcji) - miarą jest różnica grupy odciętej względem PASS przy tej samej krzywej;
2. linie Superbetu 10-12..10-15 - wycenione wiersze zawodników z `05_sheet.json`, próbka z `03_samples.json`, wynik z `07_settled.json`, tylko te, które przechodzą x >= 0.90.

## Wynik

**Historia (959 656 wierszy, ~10 tys. meczów): bramki nie chronią.** Grupy odcięte realizują się na swojej krzywej albo trochę powyżej - nie gorzej niż PASS:

| OVER (strona, którą wystawia Superbet) | n | mecze | zreal. - pewn. | vs PASS |
|---|---|---|---|---|
| PASS | 9 108 | 4 110 | +1.4 [+0.5, +2.2] | - |
| THIN_SAMPLE | 51 530 | 9 771 | +1.2 [+0.8, +1.6] | +0.9 [+0.5, +1.4] |
| LINE_BEYOND_SAMPLE | 34 766 | 9 436 | +0.5 [+0.0, +0.9] | +0.2 [-0.3, +0.7] |
| MODE_LOSES | 7 331 | 5 040 | +1.5 [+0.6, +2.6] | +1.3 [+0.2, +2.3] |

Wg liczby startów (obie strony): n=5 +0.7 pp [+0.5, +0.9], n=10 +0.2 [-0.0, +0.4]; żadna liczba startów nie przeszacowuje. Jedyny zauważalny minus: LINE_BEYOND_SAMPLE w próbkach 10/10 -0.6 pp [-1.1, -0.1] względem PASS (głównie UNDER, którego Superbet nie wystawia).

**Linie Superbetu (157 linii / 60 meczów, 4 dni): linie zawodników przy x >= 0.90 przeszacowują, bez względu na bramkę:**

| grupa | n | mecze | pewność | cena | zrealizowane | zreal. - pewn. | ROI |
|---|---|---|---|---|---|---|---|
| wszystkie | 157 | 60 | 0.788 | 0.793 | 0.669 | -11.9 [-19.8, -4.1] | -16.4% [-26.6, -6.3] |
| price_gap, odcięte | 35 | 20 | 0.787 | 0.669 | 0.457 | -33.0 [-50.3, -13.1] | -33.7% |
| bez price_gap, odcięte | 112 | 55 | 0.790 | 0.833 | 0.723 | -6.6 [-15.1, +1.6] | -12.7% [-23.1, -3.0] |
| PASS | 10 | 8 | 0.774 | - | 0.800 | +2.6 [-23.4, +23.7] | +2.9% |

PASS ma 10 linii - porównania odcięte vs PASS na liniach Superbetu nie da się zrobić (vs PASS: THIN -15.0 [-41.7, +15.6]).

## Wniosek

> **Korekta (ten sam dzień, `player_line_evidence_2026-10-16.md`):** liczby z linii Superbetu poniżej są pewnością krzywej PRZED line evidence. Z offsetem i limitem pasma, które CONFIDENCE stosuje, nogi zawodników bez bramek próbki realizowały się -3.2 pp [-13.8, +6.5] pod pewnością (77 nóg / 42 mecze, walk-forward 10-12..10-15), nie ~-12 pp.

- Na historii bramki próbki u zawodników nie wybierają lepszych nóg: zdejmują nogi, które krzywa opisuje poprawnie. Ich wyłączenie dla `player_*` jest uzasadnione pomiarem (przedział wyklucza gorszy wynik grup odciętych dla OVER THIN / MODE).
- Na liniach Superbetu cała populacja nóg zawodników, które przechodzą x >= 0.90, jest dziś przeszacowana o ~12 pp, najmocniej tam, gdzie pewność przekracza cenę (`price_gap`). To jest pytanie o krzywą / line evidence zawodników na liniach Superbetu (offset `player_shots_for` OVER tylko -0.007), nie o bramki.
- Wyłączenie bramek bez korekty dla linii Superbetu dodałoby ~50 nóg dziennie z populacji, która na 4 dniach realizowała się ~12 pp poniżej pewności. Decyzja operatora.

Zastrzeżenia: historia nie ma cen (nie da się zastosować x >= 0.90); krzywa in-sample na historii; linie Superbetu z 4 dni, curves z 10-16 (nie te, którymi budowano 10-12..10-14); pewność bez line evidence.

---

## Pełny raport skryptu

## 1. Historia (replay data/refit_2026-10-16b/sofa_replay.db)

### wg bramki (kolejność run_confidence)

| grupa | n | mecze | pewność | zrealizowane | zreal. - pewn. (pp) | vs PASS (pp) |
|---|---|---|---|---|---|---|
| OVER LINE_BEYOND_SAMPLE | 34766 | 9436 | 0.798 | 0.803 | +0.5 [+0.0, +0.9] | +0.2 [-0.3, +0.7] |
| OVER MODE_LOSES | 7331 | 5040 | 0.742 | 0.758 | +1.5 [+0.6, +2.6] | +1.3 [+0.2, +2.3] |
| OVER PASS | 9108 | 4110 | 0.770 | 0.783 | +1.4 [+0.5, +2.2] | - |
| OVER THIN_SAMPLE | 51530 | 9771 | 0.762 | 0.774 | +1.2 [+0.8, +1.6] | +0.9 [+0.5, +1.4] |
| UNDER LINE_BEYOND_SAMPLE | 225654 | 10288 | 0.913 | 0.915 | +0.2 [+0.1, +0.3] | -0.1 [-0.3, +0.2] |
| UNDER MODE_LOSES | 16042 | 7497 | 0.766 | 0.796 | +3.0 [+2.4, +3.6] | +2.7 [+2.0, +3.3] |
| UNDER PASS | 89221 | 5746 | 0.853 | 0.854 | +0.1 [-0.1, +0.4] | - |
| UNDER THIN_SAMPLE | 526004 | 10307 | 0.840 | 0.846 | +0.6 [+0.5, +0.7] | +0.3 [+0.0, +0.6] |

### wg liczby startów w próbce

| grupa | n | mecze | pewność | zrealizowane | zreal. - pewn. (pp) | vs PASS (pp) |
|---|---|---|---|---|---|---|
| n=05 | 148828 | 8624 | 0.850 | 0.858 | +0.7 [+0.5, +0.9] | +0.4 [+0.1, +0.8] |
| n=06 | 154646 | 8548 | 0.848 | 0.856 | +0.9 [+0.6, +1.1] | +0.6 [+0.2, +0.9] |
| n=07 | 172581 | 8576 | 0.849 | 0.854 | +0.5 [+0.3, +0.7] | +0.2 [-0.1, +0.5] |
| n=08 | 184908 | 8373 | 0.848 | 0.854 | +0.6 [+0.4, +0.8] | +0.3 [+0.0, +0.7] |
| n=09 | 179687 | 7616 | 0.853 | 0.857 | +0.4 [+0.2, +0.5] | +0.1 [-0.2, +0.4] |
| n=10 | 119006 | 5748 | 0.853 | 0.855 | +0.2 [-0.0, +0.4] | -0.1 [-0.1, +0.0] |

### tylko próbki 10/10 - LINE_BEYOND / MODE vs PASS

| grupa | n | mecze | pewność | zrealizowane | zreal. - pewn. (pp) | vs PASS (pp) |
|---|---|---|---|---|---|---|
| LINE_BEYOND_SAMPLE | 18415 | 4850 | 0.906 | 0.903 | -0.3 [-0.8, +0.1] | -0.6 [-1.1, -0.1] |
| MODE_LOSES | 2262 | 1702 | 0.755 | 0.777 | +2.2 [+0.5, +3.8] | +1.9 [+0.1, +3.6] |
| PASS | 98329 | 5746 | 0.845 | 0.848 | +0.3 [+0.0, +0.5] | - |

### wg rynku i bramki

| grupa | n | mecze | pewność | zrealizowane | zreal. - pewn. (pp) | vs PASS (pp) |
|---|---|---|---|---|---|---|
| player_assists_for UNDER / LINE_BEYOND_SAMPLE | 5179 | 3962 | 0.965 | 0.984 | +1.9 [+1.6, +2.3] | +1.6 [+1.2, +2.1] |
| player_assists_for UNDER / MODE_LOSES | 673 | 646 | 0.765 | 0.782 | +1.7 [-1.4, +5.0] | +1.4 [-1.8, +4.5] |
| player_assists_for UNDER / PASS | 8835 | 4188 | 0.906 | 0.900 | -0.6 [-1.2, +0.1] | - |
| player_assists_for UNDER / THIN_SAMPLE | 45092 | 9804 | 0.893 | 0.901 | +0.8 [+0.6, +1.1] | +0.6 [+0.2, +0.9] |
| player_fouls_for OVER / LINE_BEYOND_SAMPLE | 7500 | 5072 | 0.748 | 0.756 | +0.8 [-0.3, +1.8] | +0.5 [-0.4, +1.6] |
| player_fouls_for OVER / MODE_LOSES | 1870 | 1674 | 0.714 | 0.720 | +0.6 [-1.5, +2.6] | +0.3 [-1.9, +2.3] |
| player_fouls_for OVER / PASS | 1639 | 1421 | 0.725 | 0.737 | +1.2 [-0.9, +3.3] | - |
| player_fouls_for OVER / THIN_SAMPLE | 12730 | 6933 | 0.726 | 0.741 | +1.5 [+0.8, +2.2] | +1.2 [+0.4, +1.9] |
| player_fouls_for UNDER / LINE_BEYOND_SAMPLE | 52882 | 9989 | 0.907 | 0.905 | -0.2 [-0.4, +0.1] | -0.4 [-0.8, -0.1] |
| player_fouls_for UNDER / MODE_LOSES | 4202 | 3370 | 0.771 | 0.809 | +3.8 [+2.7, +4.9] | +3.5 [+2.3, +4.7] |
| player_fouls_for UNDER / PASS | 17835 | 5170 | 0.848 | 0.846 | -0.2 [-0.8, +0.4] | - |
| player_fouls_for UNDER / THIN_SAMPLE | 105781 | 10113 | 0.834 | 0.842 | +0.8 [+0.5, +1.0] | +0.5 [+0.2, +0.8] |
| player_offsides_for UNDER / LINE_BEYOND_SAMPLE | 5613 | 4265 | 0.935 | 0.945 | +1.0 [+0.5, +1.6] | +0.7 [+0.0, +1.4] |
| player_offsides_for UNDER / MODE_LOSES | 132 | 132 | 0.830 | 0.818 | -1.1 [-8.5, +5.0] | -1.4 [-8.0, +5.1] |
| player_offsides_for UNDER / PASS | 4418 | 2536 | 0.896 | 0.891 | -0.5 [-1.5, +0.4] | - |
| player_offsides_for UNDER / THIN_SAMPLE | 37819 | 9089 | 0.882 | 0.892 | +0.9 [+0.6, +1.2] | +0.7 [+0.3, +1.1] |
| player_shots_for OVER / LINE_BEYOND_SAMPLE | 12970 | 7070 | 0.825 | 0.833 | +0.8 [+0.2, +1.5] | +0.5 [-0.1, +1.3] |
| player_shots_for OVER / MODE_LOSES | 976 | 920 | 0.761 | 0.777 | +1.5 [-1.0, +4.4] | +1.3 [-1.5, +3.7] |
| player_shots_for OVER / PASS | 3185 | 2238 | 0.792 | 0.812 | +2.1 [+0.5, +3.5] | - |
| player_shots_for OVER / THIN_SAMPLE | 15235 | 7686 | 0.783 | 0.795 | +1.2 [+0.6, +1.8] | +0.9 [+0.2, +1.6] |
| player_shots_for UNDER / LINE_BEYOND_SAMPLE | 74595 | 10212 | 0.914 | 0.918 | +0.4 [+0.1, +0.6] | +0.1 [-0.2, +0.4] |
| player_shots_for UNDER / MODE_LOSES | 3985 | 3059 | 0.749 | 0.800 | +5.1 [+3.9, +6.5] | +4.8 [+3.5, +6.1] |
| player_shots_for UNDER / PASS | 22907 | 5397 | 0.837 | 0.839 | +0.3 [-0.3, +0.8] | - |
| player_shots_for UNDER / THIN_SAMPLE | 126098 | 10232 | 0.824 | 0.828 | +0.3 [+0.1, +0.6] | +0.1 [-0.3, +0.4] |
| player_shots_on_target_for UNDER / LINE_BEYOND_SAMPLE | 33618 | 9643 | 0.925 | 0.940 | +1.5 [+1.3, +1.8] | +1.3 [+0.9, +1.6] |
| player_shots_on_target_for UNDER / MODE_LOSES | 649 | 614 | 0.754 | 0.837 | +8.3 [+5.5, +10.9] | +8.0 [+5.0, +10.8] |
| player_shots_on_target_for UNDER / PASS | 12692 | 4796 | 0.853 | 0.849 | -0.4 [-1.1, +0.2] | - |
| player_shots_on_target_for UNDER / THIN_SAMPLE | 82968 | 10157 | 0.838 | 0.840 | +0.2 [-0.0, +0.5] | -0.1 [-0.4, +0.3] |
| player_tackles_for OVER / LINE_BEYOND_SAMPLE | 14296 | 7166 | 0.800 | 0.800 | -0.0 [-0.7, +0.7] | -0.3 [-1.0, +0.4] |
| player_tackles_for OVER / MODE_LOSES | 4485 | 3552 | 0.750 | 0.769 | +1.9 [+0.7, +3.1] | +1.7 [+0.4, +3.0] |
| player_tackles_for OVER / PASS | 4284 | 2807 | 0.770 | 0.780 | +0.9 [-0.3, +2.2] | - |
| player_tackles_for OVER / THIN_SAMPLE | 23565 | 8343 | 0.768 | 0.779 | +1.1 [+0.6, +1.7] | +0.8 [+0.2, +1.4] |
| player_tackles_for UNDER / LINE_BEYOND_SAMPLE | 53767 | 9724 | 0.903 | 0.896 | -0.7 [-1.0, -0.4] | -1.0 [-1.3, -0.6] |
| player_tackles_for UNDER / MODE_LOSES | 6401 | 4358 | 0.773 | 0.781 | +0.8 [-0.2, +1.9] | +0.5 [-0.5, +1.6] |
| player_tackles_for UNDER / PASS | 22534 | 5285 | 0.844 | 0.854 | +1.1 [+0.5, +1.6] | - |
| player_tackles_for UNDER / THIN_SAMPLE | 128246 | 10124 | 0.832 | 0.840 | +0.8 [+0.5, +1.0] | +0.5 [+0.2, +0.9] |

## 2. Linie Superbetu 2026-10-12..2026-10-15

### wg bramki (kolejność run_confidence)

| grupa | n | mecze | pewność | zrealizowane | zreal. - pewn. (pp) | vs PASS (pp) | ROI % |
|---|---|---|---|---|---|---|---|
| OVER LINE_BEYOND_SAMPLE | 66 | 40 | 0.812 | 0.712 | -10.0 [-20.3, +1.0] | -12.6 [-38.9, +19.8] | -14.8 [-28.3, -1.5] |
| OVER MODE_LOSES | 7 | 7 | 0.739 | 0.286 | -45.4 [-75.5, -1.1] | -47.9 [-87.3, -1.3] | -60.4 [-100.0, -2.1] |
| OVER PASS | 10 | 8 | 0.774 | 0.800 | +2.6 [-23.4, +23.7] | - | +2.9 [-27.9, +33.1] |
| OVER THIN_SAMPLE | 74 | 44 | 0.773 | 0.649 | -12.4 [-24.8, -0.9] | -15.0 [-41.7, +15.6] | -16.2 [-32.0, -0.2] |

### wg liczby startów w próbce

| grupa | n | mecze | pewność | zrealizowane | zreal. - pewn. (pp) | vs PASS (pp) | ROI % |
|---|---|---|---|---|---|---|---|
| n=05 | 36 | 21 | 0.778 | 0.528 | -25.1 [-42.3, -4.6] | -27.6 [-56.2, +5.5] | -33.9 [-55.2, -9.9] |
| n=06 | 31 | 21 | 0.792 | 0.613 | -17.9 [-40.9, +6.6] | -20.5 [-53.7, +17.9] | -22.9 [-51.4, +8.2] |
| n=07 | 19 | 15 | 0.787 | 0.684 | -10.2 [-33.2, +11.0] | -12.8 [-45.7, +19.9] | -13.5 [-45.4, +15.8] |
| n=08 | 27 | 17 | 0.791 | 0.667 | -12.4 [-33.7, +2.6] | -15.0 [-43.0, +16.8] | -18.4 [-44.6, +0.2] |
| n=09 | 34 | 19 | 0.797 | 0.824 | +2.6 [-13.9, +15.3] | +0.1 [-29.5, +31.6] | +2.5 [-18.1, +20.1] |
| n=10 | 10 | 8 | 0.774 | 0.800 | +2.6 [-23.4, +23.7] | - | +2.9 [-27.9, +33.1] |

### tylko próbki 10/10 - LINE_BEYOND / MODE vs PASS

| grupa | n | mecze | pewność | zrealizowane | zreal. - pewn. (pp) | vs PASS (pp) | ROI % |
|---|---|---|---|---|---|---|---|
| PASS | 10 | 8 | 0.774 | 0.800 | +2.6 [-23.4, +23.7] | - | +2.9 [-27.9, +33.1] |

### wg rynku i bramki

| grupa | n | mecze | pewność | zrealizowane | zreal. - pewn. (pp) | vs PASS (pp) | ROI % |
|---|---|---|---|---|---|---|---|
| player_fouls_for OVER / LINE_BEYOND_SAMPLE | 6 | 6 | 0.759 | 0.833 | +7.5 [-25.9, +25.0] | +4.9 [-38.7, +42.2] | +0.3 [-40.0, +22.2] |
| player_fouls_for OVER / PASS | 2 | 2 | 0.701 | 0.500 | -20.1 [-70.1, +29.9] | - | -32.0 [-100.0, +36.0] |
| player_fouls_for OVER / THIN_SAMPLE | 13 | 13 | 0.739 | 0.692 | -4.7 [-29.3, +19.2] | -7.2 [-42.3, +29.0] | -8.8 [-41.4, +22.8] |
| player_left_foot_shots_for OVER / LINE_BEYOND_SAMPLE | 2 | 2 | 0.780 | 1.000 | +22.0 [+18.3, +25.7] | +19.4 [-3.1, +44.9] | +25.5 [+14.0, +37.0] |
| player_left_foot_shots_for OVER / THIN_SAMPLE | 6 | 6 | 0.800 | 0.500 | -30.0 [-65.0, +6.3] | -32.5 [-84.1, +20.7] | -40.2 [-80.7, +2.0] |
| player_right_foot_shots_for OVER / LINE_BEYOND_SAMPLE | 7 | 6 | 0.746 | 0.714 | -3.2 [-31.8, +27.1] | -5.8 [-45.6, +35.9] | -11.0 [-48.0, +28.0] |
| player_right_foot_shots_for OVER / MODE_LOSES | 3 | 3 | 0.729 | 0.667 | -6.2 [-41.2, +28.7] | -8.8 [-85.0, +42.8] | -7.7 [-54.7, +41.0] |
| player_right_foot_shots_for OVER / THIN_SAMPLE | 5 | 5 | 0.765 | 1.000 | +23.5 [+23.0, +23.8] | +21.0 [-0.3, +46.5] | +26.8 [+23.0, +29.4] |
| player_shots_for OVER / LINE_BEYOND_SAMPLE | 43 | 30 | 0.831 | 0.674 | -15.7 [-30.9, -0.4] | -18.2 [-45.2, +11.4] | -19.8 [-38.3, -1.5] |
| player_shots_for OVER / MODE_LOSES | 2 | 2 | 0.748 | 0.000 | -74.8 [-74.8, -74.8] | -77.4 [-98.8, -53.0] | -100.0 [-100.0, -100.0] |
| player_shots_for OVER / PASS | 7 | 6 | 0.796 | 0.857 | +6.1 [-32.4, +22.9] | - | +9.0 [-35.4, +35.8] |
| player_shots_for OVER / THIN_SAMPLE | 41 | 29 | 0.784 | 0.610 | -17.4 [-33.5, -2.1] | -20.0 [-48.4, +12.3] | -20.2 [-41.5, +0.9] |
| player_tackles_for OVER / LINE_BEYOND_SAMPLE | 8 | 8 | 0.816 | 0.750 | -6.6 [-41.7, +19.1] | -9.2 [-48.8, +28.0] | -13.0 [-53.2, +18.0] |
| player_tackles_for OVER / MODE_LOSES | 2 | 2 | 0.746 | 0.000 | -74.6 [-76.5, -72.6] | -77.1 [-99.0, -51.2] | -100.0 [-100.0, -100.0] |
| player_tackles_for OVER / PASS | 1 | 1 | 0.765 | 1.000 | +23.5 [+23.5, +23.5] | - | +30.0 [+30.0, +30.0] |
| player_tackles_for OVER / THIN_SAMPLE | 9 | 7 | 0.760 | 0.667 | -9.3 [-42.2, +13.6] | -11.9 [-52.9, +23.1] | -16.2 [-58.2, +13.0] |

