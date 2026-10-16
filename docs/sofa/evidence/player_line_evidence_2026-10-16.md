# Line evidence zawodników na liniach x >= 0.90 (V1) - walk-forward 2026-10-16

**Pytanie** (operator, wariant 3 z `player_sample_gates_2026-10-16.md`): czy offset kluczy zawodników liczony tylko na liniach, które kupon mógłby wziąć (pewność krzywej x kurs >= 0.90), koryguje przeszacowanie linii zawodników na Superbecie - zanim zdecydujemy o bramkach próbki?

**Metoda.** `scripts/sofa/measure_player_line_evidence.py` (tylko odczyt). Dla każdego dnia D 10-12..10-15 evidence dopasowane na dniach stats-only przed D tak jak `fit_line_evidence.py` (wiersze arkusza football / tennis, zainstalowane krzywe), w dwóch wariantach: **V0** - dzisiejsza reguła (printable = krzywa >= 0.70), **V1** - dla kluczy `player_*` printable tylko linie z krzywa x kurs >= 0.90. Każdy wyceniony wiersz zawodnika z rynku `/lineups` (zakres przełącznika, `confidence.player_shape_gate_scope`; bez strzałów wg nogi / głowy / spoza pola) z dnia D z WIN / LOSS czytany jak w CONFIDENCE (krzywa -> `LineEvidence.read`: offset i limit pasma; próg 0.70, x >= 0.90, one-sided single z krzywej `market:` n >= 300), z bramkami próbki i bez nich. Bootstrap po meczach, dni zsumowane.

**Walk-forward tylko dla line evidence:** krzywa to zainstalowana (refit 2026-10-16b, którego replay zawiera mecze dni testowych) - liczby są in-sample dla krzywej. Pominięte (przybliżenie tego, co by się wydrukowało): klasy meczów (kobiety czytają krzywą mężczyzn), świeża cena (tu cena z arkusza), `SAMPLE_CROSSES_SEASON`, `STALE_SAMPLE`, `NOT_SETTLEABLE`.

## Wynik

Bramki próbki wyłączone dla zawodników (scenariusz przełącznika), 4 dni testowe:

| | nogi | mecze | pewność | cena | zrealizowane | zreal. - pewn. | ROI |
|---|---|---|---|---|---|---|---|
| V0 drukuje | 55 | 37 | 0.787 | 0.826 | 0.727 | -5.9 pp [-15.9, +4.5] | -11.7% [-23.8, +1.2] |
| V1 drukuje | 36 | 27 | 0.758 | 0.808 | 0.722 | -3.6 [-15.0, +8.7] | -10.2% [-24.5, +5.0] |
| V1 zdejmuje (pewność V0) | 32 | 26 | 0.792 | 0.843 | 0.719 | -7.3 [-22.2, +7.3] | -15.1% [-32.2, +2.0] |
| V1 zostawia (pewność V0) | 23 | 20 | 0.780 | 0.801 | 0.739 | -4.1 [-19.2, +12.4] | -7.0% [-25.6, +13.5] |

Z bramkami (dziś): V0 drukuje 4 nogi w 4 dni, V1 - 0. Dzień po dniu (V0 bez bramek): 10-12 3 nogi +23.1 pp, 10-13 7 nóg +8.4, 10-14 18 nóg -18.2 [-32.9, -3.7], 10-15 27 nóg -4.7.

Offsety (V0 -> V1, na 10-15): `player_shots_for` OVER -0.018 -> **-0.108** (jedyny klucz z >= 50 liniami x >= 0.90 w 30 meczach); `player_tackles_for` OVER -0.045 -> -0.011 (jego linii x >= 0.90 jest za mało, spada do puli piłki - V1 **podnosi** jego pewność); reszta kluczy na puli, ~-0.01 w obu.

(Pierwsza wersja tego pomiaru liczyła też strzały wg nogi - 77 nóg, -3.2 pp [-13.8, +6.5]; przełącznik ich nie obejmuje. Druga - bez progu kursu 1.0867 - 60 nóg, -6.0 pp [-18.4, +5.1].)

## Wniosek

- Pierwszy odczyt -12 pp był bez line evidence; z offsetem i limitem pasma nogi zawodników drukowane bez bramek realizowały -5.9 pp [-15.9, +4.5] pod pewnością - przedział obejmuje zero, punkt jest ujemny, jeden dzień (10-14) wyraźnie słaby.
- **V1 nie jest uzasadnione.** Nogi, które zdejmuje, nie wypadły mierzalnie gorzej od tych, które zostawia (-7.3 vs -4.1 pp, przedziały się nakładają); działa praktycznie tylko na `player_shots_for`, a `player_tackles_for` przez spadek do puli dostaje wyższą pewność niż dziś. Ten sam kształt co offset per przedział pewność-cena odrzucony 2026-10-12. Nie włączać.
- Wyłączenie bramek (operator: od 2026-10-17): ~14 nóg dziennie (55 / 4 dni; 10-14 / 10-15 po 18-27), ROI -11.7% [-23.8, +1.2] przy cenie, bez zmierzonej przewagi; line evidence liczy offset ze wszystkich wierszy arkusza, więc kolejne dni go dopną. Sprawdzian: `T-PLAYER-SAMPLE-GATES`.

---

## Pełny raport skryptu

## Offset kluczy zawodników (V0 -> V1) na każdy dzień

| dzień | klucz | V0 | V1 |
|---|---|---|---|
| 2026-10-12 | player_assists_for OVER | -0.0031 | -0.0032 |
| 2026-10-12 | player_fouls_for OVER | -0.0162 | -0.0032 |
| 2026-10-12 | player_offsides_for OVER | -0.0031 | -0.0032 |
| 2026-10-12 | player_shots_for OVER | -0.0181 | -0.0994 |
| 2026-10-12 | player_shots_on_target_for OVER | -0.0031 | -0.0032 |
| 2026-10-12 | player_tackles_for OVER | -0.0329 | -0.0032 |
| 2026-10-13 | player_assists_for OVER | -0.0055 | -0.0057 |
| 2026-10-13 | player_fouls_for OVER | -0.0088 | -0.0057 |
| 2026-10-13 | player_offsides_for OVER | -0.0055 | -0.0057 |
| 2026-10-13 | player_shots_for OVER | -0.0124 | -0.0790 |
| 2026-10-13 | player_shots_on_target_for OVER | -0.0055 | -0.0057 |
| 2026-10-13 | player_tackles_for OVER | -0.0263 | -0.0057 |
| 2026-10-14 | player_assists_for OVER | -0.0085 | -0.0088 |
| 2026-10-14 | player_fouls_for OVER | +0.0000 | -0.0088 |
| 2026-10-14 | player_offsides_for OVER | -0.0085 | -0.0088 |
| 2026-10-14 | player_shots_for OVER | -0.0115 | -0.0965 |
| 2026-10-14 | player_shots_on_target_for OVER | -0.0085 | -0.0088 |
| 2026-10-14 | player_tackles_for OVER | -0.0382 | -0.0088 |
| 2026-10-15 | player_assists_for OVER | -0.0104 | -0.0106 |
| 2026-10-15 | player_fouls_for OVER | -0.0109 | -0.0106 |
| 2026-10-15 | player_headed_shots_for OVER | -0.0104 | -0.0106 |
| 2026-10-15 | player_left_foot_shots_for OVER | -0.0104 | -0.0106 |
| 2026-10-15 | player_offsides_for OVER | -0.0104 | -0.0106 |
| 2026-10-15 | player_right_foot_shots_for OVER | -0.0104 | -0.0106 |
| 2026-10-15 | player_shots_for OVER | -0.0183 | -0.1075 |
| 2026-10-15 | player_shots_on_target_for OVER | -0.0104 | -0.0106 |
| 2026-10-15 | player_shots_outside_box_for OVER | -0.0104 | -0.0106 |
| 2026-10-15 | player_sot_headed_for OVER | -0.0104 | -0.0106 |
| 2026-10-15 | player_sot_left_foot_for OVER | -0.0104 | -0.0106 |
| 2026-10-15 | player_sot_outside_box_for OVER | -0.0104 | -0.0106 |
| 2026-10-15 | player_sot_right_foot_for OVER | -0.0104 | -0.0106 |
| 2026-10-15 | player_tackles_for OVER | -0.0449 | -0.0106 |

## bramki próbki WŁĄCZONE (dziś)

| grupa | nogi | mecze | pewność | cena | zrealizowane | zreal. - pewn. (pp) | ROI % |
|---|---|---|---|---|---|---|---|
| V0 drukuje | 4 | 4 | 0.792 | 0.859 | 0.750 | -4.2 [-58.0, +23.9] | -11.8 [-70.5, +19.5] |
| V1 drukuje | 0 | | | | | | |
| V1 zdejmuje (pewność V0) | 4 | 4 | 0.792 | 0.859 | 0.750 | -4.2 [-58.0, +23.9] | -11.8 [-70.5, +19.5] |
| V1 zostawia (pewność V0) | 0 | | | | | | |

## bramki próbki WYŁĄCZONE dla zawodników

| grupa | nogi | mecze | pewność | cena | zrealizowane | zreal. - pewn. (pp) | ROI % |
|---|---|---|---|---|---|---|---|
| V0 drukuje | 55 | 37 | 0.787 | 0.826 | 0.727 | -5.9 [-15.9, +4.5] | -11.7 [-23.8, +1.2] |
| V1 drukuje | 36 | 27 | 0.758 | 0.808 | 0.722 | -3.6 [-15.0, +8.7] | -10.2 [-24.5, +5.0] |
| V1 zdejmuje (pewność V0) | 32 | 26 | 0.792 | 0.843 | 0.719 | -7.3 [-22.2, +7.3] | -15.1 [-32.2, +2.0] |
| V1 zostawia (pewność V0) | 23 | 20 | 0.780 | 0.801 | 0.739 | -4.1 [-19.2, +12.4] | -7.0 [-25.6, +13.5] |

## Dzień po dniu (bramki wyłączone)

| grupa | nogi | mecze | pewność | cena | zrealizowane | zreal. - pewn. (pp) | ROI % |
|---|---|---|---|---|---|---|---|
| 2026-10-12 V0 (bez bramek) | 3 | 2 | 0.769 | 0.809 | 1.000 | +23.1 [+22.3, +24.5] | +23.7 [+21.0, +25.0] |
| 2026-10-12 V1 (bez bramek) | 3 | 3 | 0.752 | 0.813 | 1.000 | +24.8 [+21.6, +26.7] | +23.0 [+21.0, +24.3] |
| 2026-10-13 V0 (bez bramek) | 7 | 5 | 0.774 | 0.836 | 0.857 | +8.4 [-5.8, +26.4] | +3.7 [-12.4, +24.8] |
| 2026-10-13 V1 (bez bramek) | 7 | 6 | 0.732 | 0.805 | 0.857 | +12.5 [-6.3, +27.2] | +6.4 [-16.1, +24.7] |
| 2026-10-14 V0 (bez bramek) | 18 | 11 | 0.793 | 0.836 | 0.611 | -18.2 [-32.9, -3.7] | -27.9 [-44.7, -9.6] |
| 2026-10-14 V1 (bez bramek) | 7 | 6 | 0.759 | 0.804 | 0.429 | -33.0 [-61.0, -3.8] | -46.4 [-81.2, -10.4] |
| 2026-10-15 V0 (bez bramek) | 27 | 19 | 0.787 | 0.818 | 0.741 | -4.7 [-21.0, +14.0] | -8.9 [-28.6, +13.0] |
| 2026-10-15 V1 (bez bramek) | 19 | 12 | 0.769 | 0.810 | 0.737 | -3.2 [-16.6, +11.4] | -8.2 [-25.8, +11.5] |

