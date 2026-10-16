# Bramki próbki zawodników (THIN_SAMPLE / LINE_BEYOND_SAMPLE / MODE_LOSES) - pomiar 2026-10-16

**Pytanie.** Na 10-15 z 19 018 wierszy zawodników (piłka) wydrukowało się 5. Z 57, które przeszły krzywą, line evidence i x >= 0.90, 54 odcięły bramki kształtu próbki CONFIDENCE (`MIN_BUILDER_SAMPLE` 10, `line_is_beyond_sample`, `mode_loses`). Próbka zawodnika to od 10-12 jego starty w 10 ostatnich meczach drużyny (5-10 wartości), więc `THIN_SAMPLE_FOR_BUILDER` przepuszcza tylko zawodnika z 10/10 startów. Krzywe zawodników z `/lineups` są fitowane na replayu z próbką od 5 startów i bez bramek kształtu (`calibrate_from_cache.player_rows_for_event`, `min_sample` 5). Czy wydrukowana pewność odcinanych nóg jest przeszacowana?

**Metoda.** `scripts/sofa/measure_player_sample_gates.py` (tylko odczyt):
1. historia - replay wierszy zawodników (starty) z `data/refit_2026-10-16b/sofa_replay.db` tym samym kodem, z zapamiętaną próbką każdego wiersza; pewność = zainstalowana krzywa (przed line evidence); wiersze z pewnością >= 0.70 pogrupowane wg bramki, która by je odcięła (`confidence.shape_gate_refusal`), i wg liczby startów; „vs PASS" = względem wierszy przepuszczanych **tego samego kierunku** (i rynku w tabeli rynków); bootstrap po meczach. Krzywa była fitowana na tych wierszach (łączna luka ~0 z konstrukcji). Replay ma tylko rynki z `/lineups` (strzały, celne, faule, odbiory, asysty, spalone) - rynki strzałów wg nogi / głowy / spoza pola (`/shotmap`, osobny estymator `shot_detail`) nie są tu mierzone i nie są objęte przełącznikiem;
2. linie Superbetu 10-12..10-15 - wycenione wiersze rynków z `/lineups` z `05_sheet.json`, próbka z `03_samples.json`, wynik z `07_settled.json`, tylko te, które przechodzą x >= 0.90; pewność **przed** line evidence (z line evidence: `player_line_evidence_2026-10-16.md`).

## Wynik

**Historia (OVER, strona, którą Superbet wystawia: 102 735 wierszy; UNDER 856 921 - w tabeli pełnej).** Grupy odcinane realizują się na swojej krzywej, ale ~1 pp słabiej niż przepuszczane:

| OVER | n | mecze | zreal. - pewn. | vs OVER PASS |
|---|---|---|---|---|
| PASS | 9 108 | 4 110 | +1.4 [+0.5, +2.2] | - |
| THIN_SAMPLE_FOR_BUILDER | 51 530 | 9 771 | +1.2 [+0.8, +1.6] | -0.2 [-1.1, +0.7] |
| LINE_BEYOND_SAMPLE | 34 766 | 9 436 | +0.5 [+0.0, +0.9] | -0.9 [-1.8, +0.1] |
| MODE_LOSES | 7 331 | 5 040 | +1.5 [+0.6, +2.6] | +0.2 [-1.1, +1.4] |
| n = 5 startów | 15 644 | 6 360 | -0.5 [-1.1, +0.2] | **-1.9 [-2.9, -0.8]** |
| n = 6 | 17 244 | 6 640 | +0.8 [+0.1, +1.4] | -0.6 [-1.7, +0.5] |
| n = 10 | 12 613 | 4 549 | +1.7 [+1.0, +2.5] | +0.3 [-0.1, +0.8] |

Per rynek OVER (vs PASS tego rynku): strzały THIN -0.9 [-2.3, +0.7], LINE_BEYOND -1.2 [-2.8, +0.3]; faule i odbiory w granicach ±1 pp.

**Linie Superbetu (134 linie rynków `/lineups`, 4 dni, pewność przed line evidence):** strzały OVER odcinane przez THIN / LINE_BEYOND realizowały -17 / -16 pp pod krzywą (po ~40 linii), PASS ma 7 linii - porównania nie da się zrobić. Z line evidence (offset + limit pasma) cała populacja bez bramek: -6.0 pp [-18.4, +5.1] (`player_line_evidence_2026-10-16.md`).

## Wniosek

- Bramki nie są ochroną przed przeszacowaniem: odcinane nogi zawodników realizują się na krzywej, z której bierze się ich wydrukowana pewność (w historii -0.5..+1.5 pp).
- Bramki lekko **wybierają** lepsze nogi: przepuszczane realizują ~1 pp powyżej odcinanych, najwyraźniej przy próbce 5 startów (-1.9 pp [-2.9, -0.8]). Zdjęcie bramek dodaje więc nogi średnio nieco słabsze od dzisiejszych, ale skalibrowane na swojej krzywej.
- Na liniach Superbetu (4 dni) nogi odcinane były wyraźnie słabsze od krzywej przed line evidence; line evidence koryguje większość tej różnicy, przedział obejmuje zero. Decyzja operatora (2026-10-16): włączone od 2026-10-17, z testem na nowych danych `T-PLAYER-SAMPLE-GATES`.

Zastrzeżenia: krzywa in-sample na historii; historia bez cen (nie da się zastosować x >= 0.90); linie Superbetu z 4 dni, krzywe z 10-16.

---

## Pełny raport skryptu

## 1. Historia (replay data/refit_2026-10-16b/sofa_replay.db)

### wg bramki (kolejność run_confidence; vs PASS tego kierunku)

| grupa | n | mecze | pewność | zrealizowane | zreal. - pewn. (pp) | vs PASS (pp) |
|---|---|---|---|---|---|---|
| OVER LINE_BEYOND_SAMPLE | 34766 | 9436 | 0.798 | 0.803 | +0.5 [+0.0, +0.9] | -0.9 [-1.8, +0.1] |
| OVER MODE_LOSES | 7331 | 5040 | 0.742 | 0.758 | +1.5 [+0.6, +2.6] | +0.2 [-1.1, +1.4] |
| OVER PASS | 9108 | 4110 | 0.770 | 0.783 | +1.4 [+0.5, +2.2] | - |
| OVER THIN_SAMPLE_FOR_BUILDER | 51530 | 9771 | 0.762 | 0.774 | +1.2 [+0.8, +1.6] | -0.2 [-1.1, +0.7] |
| UNDER LINE_BEYOND_SAMPLE | 225654 | 10288 | 0.913 | 0.915 | +0.2 [+0.1, +0.3] | +0.1 [-0.3, +0.4] |
| UNDER MODE_LOSES | 16042 | 7497 | 0.766 | 0.796 | +3.0 [+2.4, +3.6] | +2.8 [+2.1, +3.5] |
| UNDER PASS | 89221 | 5746 | 0.853 | 0.854 | +0.1 [-0.1, +0.4] | - |
| UNDER THIN_SAMPLE_FOR_BUILDER | 526004 | 10307 | 0.840 | 0.846 | +0.6 [+0.5, +0.7] | +0.4 [+0.1, +0.8] |

### OVER wg liczby startów w próbce (vs OVER PASS)

| grupa | n | mecze | pewność | zrealizowane | zreal. - pewn. (pp) | vs PASS (pp) |
|---|---|---|---|---|---|---|
| OVER n=05 | 15644 | 6360 | 0.772 | 0.767 | -0.5 [-1.1, +0.2] | -1.9 [-2.9, -0.8] |
| OVER n=06 | 17244 | 6640 | 0.769 | 0.777 | +0.8 [+0.1, +1.4] | -0.6 [-1.7, +0.5] |
| OVER n=07 | 18224 | 6785 | 0.774 | 0.779 | +0.5 [-0.2, +1.1] | -0.9 [-1.9, +0.1] |
| OVER n=08 | 20077 | 6842 | 0.772 | 0.789 | +1.8 [+1.2, +2.3] | +0.4 [-0.6, +1.4] |
| OVER n=09 | 18933 | 6315 | 0.776 | 0.793 | +1.7 [+1.0, +2.2] | +0.3 [-0.7, +1.3] |
| OVER n=10 | 12613 | 4549 | 0.777 | 0.794 | +1.7 [+1.0, +2.5] | +0.3 [-0.1, +0.8] |

### tylko próbki 10/10 - LINE_BEYOND / MODE vs PASS tego kierunku

| grupa | n | mecze | pewność | zrealizowane | zreal. - pewn. (pp) | vs PASS (pp) |
|---|---|---|---|---|---|---|
| OVER LINE_BEYOND_SAMPLE | 2626 | 1951 | 0.814 | 0.836 | +2.2 [+0.8, +3.6] | +0.8 [-0.8, +2.4] |
| OVER MODE_LOSES | 879 | 781 | 0.742 | 0.779 | +3.7 [+0.9, +6.5] | +2.3 [-0.6, +5.3] |
| OVER PASS | 9108 | 4110 | 0.770 | 0.783 | +1.4 [+0.5, +2.2] | - |
| UNDER LINE_BEYOND_SAMPLE | 15789 | 4766 | 0.921 | 0.914 | -0.8 [-1.2, -0.3] | -0.9 [-1.4, -0.4] |
| UNDER MODE_LOSES | 1383 | 1110 | 0.764 | 0.776 | +1.2 [-0.9, +3.5] | +1.1 [-1.2, +3.2] |
| UNDER PASS | 89221 | 5746 | 0.853 | 0.854 | +0.1 [-0.1, +0.4] | - |

### wg rynku i bramki (vs PASS tego rynku i kierunku)

| grupa | n | mecze | pewność | zrealizowane | zreal. - pewn. (pp) | vs PASS (pp) |
|---|---|---|---|---|---|---|
| player_assists_for UNDER / LINE_BEYOND_SAMPLE | 5179 | 3962 | 0.965 | 0.984 | +1.9 [+1.6, +2.3] | +2.5 [+1.8, +3.2] |
| player_assists_for UNDER / MODE_LOSES | 673 | 646 | 0.765 | 0.782 | +1.7 [-1.4, +5.0] | +2.3 [-0.9, +5.5] |
| player_assists_for UNDER / PASS | 8835 | 4188 | 0.906 | 0.900 | -0.6 [-1.2, +0.1] | - |
| player_assists_for UNDER / THIN_SAMPLE_FOR_BUILDER | 45092 | 9804 | 0.893 | 0.901 | +0.8 [+0.6, +1.1] | +1.4 [+0.7, +2.1] |
| player_fouls_for OVER / LINE_BEYOND_SAMPLE | 7500 | 5072 | 0.748 | 0.756 | +0.8 [-0.3, +1.8] | -0.4 [-2.7, +2.1] |
| player_fouls_for OVER / MODE_LOSES | 1870 | 1674 | 0.714 | 0.720 | +0.6 [-1.5, +2.6] | -0.7 [-3.7, +2.3] |
| player_fouls_for OVER / PASS | 1639 | 1421 | 0.725 | 0.737 | +1.2 [-0.9, +3.3] | - |
| player_fouls_for OVER / THIN_SAMPLE_FOR_BUILDER | 12730 | 6933 | 0.726 | 0.741 | +1.5 [+0.8, +2.2] | +0.2 [-2.0, +2.6] |
| player_fouls_for UNDER / LINE_BEYOND_SAMPLE | 52882 | 9989 | 0.907 | 0.905 | -0.2 [-0.4, +0.1] | +0.0 [-0.6, +0.7] |
| player_fouls_for UNDER / MODE_LOSES | 4202 | 3370 | 0.771 | 0.809 | +3.8 [+2.7, +4.9] | +4.0 [+2.7, +5.3] |
| player_fouls_for UNDER / PASS | 17835 | 5170 | 0.848 | 0.846 | -0.2 [-0.8, +0.4] | - |
| player_fouls_for UNDER / THIN_SAMPLE_FOR_BUILDER | 105781 | 10113 | 0.834 | 0.842 | +0.8 [+0.5, +1.0] | +1.0 [+0.4, +1.6] |
| player_offsides_for UNDER / LINE_BEYOND_SAMPLE | 5613 | 4265 | 0.935 | 0.945 | +1.0 [+0.5, +1.6] | +1.5 [+0.4, +2.6] |
| player_offsides_for UNDER / MODE_LOSES | 132 | 132 | 0.830 | 0.818 | -1.1 [-8.5, +5.0] | -0.7 [-7.3, +6.0] |
| player_offsides_for UNDER / PASS | 4418 | 2536 | 0.896 | 0.891 | -0.5 [-1.5, +0.4] | - |
| player_offsides_for UNDER / THIN_SAMPLE_FOR_BUILDER | 37819 | 9089 | 0.882 | 0.892 | +0.9 [+0.6, +1.2] | +1.4 [+0.5, +2.4] |
| player_shots_for OVER / LINE_BEYOND_SAMPLE | 12970 | 7070 | 0.825 | 0.833 | +0.8 [+0.2, +1.5] | -1.2 [-2.8, +0.3] |
| player_shots_for OVER / MODE_LOSES | 976 | 920 | 0.761 | 0.777 | +1.5 [-1.0, +4.4] | -0.5 [-3.5, +2.3] |
| player_shots_for OVER / PASS | 3185 | 2238 | 0.792 | 0.812 | +2.1 [+0.5, +3.5] | - |
| player_shots_for OVER / THIN_SAMPLE_FOR_BUILDER | 15235 | 7686 | 0.783 | 0.795 | +1.2 [+0.6, +1.8] | -0.9 [-2.3, +0.7] |
| player_shots_for UNDER / LINE_BEYOND_SAMPLE | 74595 | 10212 | 0.914 | 0.918 | +0.4 [+0.1, +0.6] | +0.1 [-0.5, +0.7] |
| player_shots_for UNDER / MODE_LOSES | 3985 | 3059 | 0.749 | 0.800 | +5.1 [+3.9, +6.5] | +4.8 [+3.5, +6.2] |
| player_shots_for UNDER / PASS | 22907 | 5397 | 0.837 | 0.839 | +0.3 [-0.3, +0.8] | - |
| player_shots_for UNDER / THIN_SAMPLE_FOR_BUILDER | 126098 | 10232 | 0.824 | 0.828 | +0.3 [+0.1, +0.6] | +0.1 [-0.6, +0.7] |
| player_shots_on_target_for UNDER / LINE_BEYOND_SAMPLE | 33618 | 9643 | 0.925 | 0.940 | +1.5 [+1.3, +1.8] | +1.9 [+1.2, +2.7] |
| player_shots_on_target_for UNDER / MODE_LOSES | 649 | 614 | 0.754 | 0.837 | +8.3 [+5.5, +10.9] | +8.7 [+5.6, +11.5] |
| player_shots_on_target_for UNDER / PASS | 12692 | 4796 | 0.853 | 0.849 | -0.4 [-1.1, +0.2] | - |
| player_shots_on_target_for UNDER / THIN_SAMPLE_FOR_BUILDER | 82968 | 10157 | 0.838 | 0.840 | +0.2 [-0.0, +0.5] | +0.6 [-0.1, +1.4] |
| player_tackles_for OVER / LINE_BEYOND_SAMPLE | 14296 | 7166 | 0.800 | 0.800 | -0.0 [-0.7, +0.7] | -0.9 [-2.4, +0.4] |
| player_tackles_for OVER / MODE_LOSES | 4485 | 3552 | 0.750 | 0.769 | +1.9 [+0.7, +3.1] | +1.0 [-0.8, +2.7] |
| player_tackles_for OVER / PASS | 4284 | 2807 | 0.770 | 0.780 | +0.9 [-0.3, +2.2] | - |
| player_tackles_for OVER / THIN_SAMPLE_FOR_BUILDER | 23565 | 8343 | 0.768 | 0.779 | +1.1 [+0.6, +1.7] | +0.2 [-1.1, +1.5] |
| player_tackles_for UNDER / LINE_BEYOND_SAMPLE | 53767 | 9724 | 0.903 | 0.896 | -0.7 [-1.0, -0.4] | -1.8 [-2.4, -1.2] |
| player_tackles_for UNDER / MODE_LOSES | 6401 | 4358 | 0.773 | 0.781 | +0.8 [-0.2, +1.9] | -0.3 [-1.4, +0.9] |
| player_tackles_for UNDER / PASS | 22534 | 5285 | 0.844 | 0.854 | +1.1 [+0.5, +1.6] | - |
| player_tackles_for UNDER / THIN_SAMPLE_FOR_BUILDER | 128246 | 10124 | 0.832 | 0.840 | +0.8 [+0.5, +1.0] | -0.3 [-0.9, +0.3] |

## 2. Linie Superbetu 2026-10-12..2026-10-15

### wg bramki (kolejność run_confidence; vs PASS tego kierunku)

| grupa | n | mecze | pewność | zrealizowane | zreal. - pewn. (pp) | vs PASS (pp) | ROI % |
|---|---|---|---|---|---|---|---|
| OVER LINE_BEYOND_SAMPLE | 57 | 40 | 0.821 | 0.702 | -11.9 [-23.6, -0.1] | -14.5 [-42.1, +18.2] | -16.7 [-31.3, -2.8] |
| OVER MODE_LOSES | 4 | 4 | 0.747 | 0.000 | -74.7 [-76.1, -73.2] | -77.3 [-98.8, -49.7] | -100.0 [-100.0, -100.0] |
| OVER PASS | 10 | 8 | 0.774 | 0.800 | +2.6 [-23.4, +23.7] | - | +2.9 [-27.9, +33.1] |
| OVER THIN_SAMPLE_FOR_BUILDER | 63 | 42 | 0.771 | 0.635 | -13.6 [-26.7, -1.4] | -16.2 [-43.8, +16.0] | -17.3 [-34.7, -0.9] |

### OVER wg liczby startów w próbce (vs OVER PASS)

| grupa | n | mecze | pewność | zrealizowane | zreal. - pewn. (pp) | vs PASS (pp) | ROI % |
|---|---|---|---|---|---|---|---|
| OVER n=05 | 28 | 19 | 0.786 | 0.500 | -28.6 [-48.1, -9.2] | -31.1 [-62.9, +4.4] | -38.5 [-62.4, -15.0] |
| OVER n=06 | 25 | 18 | 0.799 | 0.560 | -23.9 [-49.5, +5.7] | -26.5 [-62.2, +14.3] | -29.4 [-61.4, +7.9] |
| OVER n=07 | 19 | 15 | 0.787 | 0.684 | -10.2 [-33.2, +11.0] | -12.8 [-45.7, +19.9] | -13.5 [-45.4, +15.8] |
| OVER n=08 | 25 | 17 | 0.791 | 0.680 | -11.1 [-31.7, +5.4] | -13.7 [-42.4, +19.1] | -16.6 [-42.4, +4.2] |
| OVER n=09 | 27 | 18 | 0.803 | 0.815 | +1.1 [-14.9, +15.4] | -1.4 [-31.2, +30.8] | +1.4 [-20.7, +19.0] |
| OVER n=10 | 10 | 8 | 0.774 | 0.800 | +2.6 [-23.4, +23.7] | - | +2.9 [-27.9, +33.1] |

### tylko próbki 10/10 - LINE_BEYOND / MODE vs PASS tego kierunku

| grupa | n | mecze | pewność | zrealizowane | zreal. - pewn. (pp) | vs PASS (pp) | ROI % |
|---|---|---|---|---|---|---|---|
| OVER PASS | 10 | 8 | 0.774 | 0.800 | +2.6 [-23.4, +23.7] | - | +2.9 [-27.9, +33.1] |

### wg rynku i bramki (vs PASS tego rynku i kierunku)

| grupa | n | mecze | pewność | zrealizowane | zreal. - pewn. (pp) | vs PASS (pp) | ROI % |
|---|---|---|---|---|---|---|---|
| player_fouls_for OVER / LINE_BEYOND_SAMPLE | 6 | 6 | 0.759 | 0.833 | +7.5 [-25.9, +25.0] | +27.6 [-40.0, +94.6] | +0.3 [-40.0, +22.2] |
| player_fouls_for OVER / PASS | 2 | 2 | 0.701 | 0.500 | -20.1 [-70.1, +29.9] | - | -32.0 [-100.0, +36.0] |
| player_fouls_for OVER / THIN_SAMPLE_FOR_BUILDER | 13 | 13 | 0.739 | 0.692 | -4.7 [-29.3, +19.2] | +15.4 [-54.0, +81.0] | -8.8 [-41.4, +22.8] |
| player_shots_for OVER / LINE_BEYOND_SAMPLE | 43 | 30 | 0.831 | 0.674 | -15.7 [-30.9, -0.4] | -21.7 [-48.1, +22.3] | -19.8 [-38.3, -1.5] |
| player_shots_for OVER / MODE_LOSES | 2 | 2 | 0.748 | 0.000 | -74.8 [-74.8, -74.8] | -80.9 [-97.8, -43.3] | -100.0 [-100.0, -100.0] |
| player_shots_for OVER / PASS | 7 | 6 | 0.796 | 0.857 | +6.1 [-32.4, +22.9] | - | +9.0 [-35.4, +35.8] |
| player_shots_for OVER / THIN_SAMPLE_FOR_BUILDER | 41 | 29 | 0.784 | 0.610 | -17.4 [-33.5, -2.1] | -23.5 [-52.5, +23.3] | -20.2 [-41.5, +0.9] |
| player_tackles_for OVER / LINE_BEYOND_SAMPLE | 8 | 8 | 0.816 | 0.750 | -6.6 [-41.7, +19.1] | -30.1 [-63.6, -3.9] | -13.0 [-53.2, +18.0] |
| player_tackles_for OVER / MODE_LOSES | 2 | 2 | 0.746 | 0.000 | -74.6 [-76.5, -72.6] | -98.1 [-100.0, -96.1] | -100.0 [-100.0, -100.0] |
| player_tackles_for OVER / PASS | 1 | 1 | 0.765 | 1.000 | +23.5 [+23.5, +23.5] | - | +30.0 [+30.0, +30.0] |
| player_tackles_for OVER / THIN_SAMPLE_FOR_BUILDER | 9 | 7 | 0.760 | 0.667 | -9.3 [-42.2, +13.6] | -32.8 [-65.8, -0.4] | -16.2 [-58.2, +13.0] |

