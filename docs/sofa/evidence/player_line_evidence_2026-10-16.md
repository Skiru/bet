# Line evidence zawodników na liniach x >= 0.90 (V1) - walk-forward 2026-10-16

**Pytanie** (operator, wariant 3 z `player_sample_gates_2026-10-16.md`): czy offset kluczy zawodników liczony tylko na liniach, które kupon mógłby wziąć (pewność krzywej x kurs >= 0.90), koryguje przeszacowanie linii zawodników na Superbecie - zanim zdecydujemy o bramkach próbki?

**Metoda.** `scripts/sofa/measure_player_line_evidence.py` (tylko odczyt). Dla każdego dnia D 10-12..10-15 evidence dopasowane na dniach stats-only przed D tak jak `fit_line_evidence.py` (wiersze arkusza football / tennis, zainstalowane krzywe), w dwóch wariantach: **V0** - dzisiejsza reguła (printable = krzywa >= 0.70), **V1** - dla kluczy `player_*` printable tylko linie z krzywa x kurs >= 0.90 (pasma, kubełki i reszta kluczy bez zmian). Każdy wyceniony wiersz zawodnika z dnia D z WIN / LOSS czytany jak w CONFIDENCE (krzywa -> `LineEvidence.read`: offset i limit pasma; próg 0.70, x >= 0.90, one-sided single z krzywej `market:` n >= 300), z bramkami próbki i bez nich. Bootstrap po meczach, dni zsumowane.

## Wynik

Bramki próbki wyłączone dla zawodników (scenariusz przełącznika), 4 dni testowe:

| | nogi | mecze | pewność | cena | zrealizowane | zreal. - pewn. | ROI |
|---|---|---|---|---|---|---|---|
| V0 drukuje | 77 | 42 | 0.785 | 0.829 | 0.753 | -3.2 pp [-13.8, +6.5] | -8.6% [-21.2, +2.9] |
| V1 drukuje | 53 | 35 | 0.758 | 0.808 | 0.755 | -0.3 [-9.2, +9.4] | -5.8% [-16.9, +6.7] |
| V1 zdejmuje (pewność V0) | 37 | 29 | 0.801 | 0.857 | 0.730 | -7.1 [-23.9, +8.5] | -15.2% [-34.5, +2.7] |
| V1 zostawia (pewność V0) | 40 | 28 | 0.770 | 0.803 | 0.775 | +0.5 [-10.3, +11.8] | -2.6% [-16.0, +11.2] |

Z bramkami (dziś): V0 drukuje 4 nogi w 4 dni, V1 - 0.

Offsety (V0 -> V1, na 10-15): `player_shots_for` OVER -0.018 -> **-0.108** (jedyny klucz z >= 50 liniami x >= 0.90 w 30 meczach); `player_tackles_for` OVER -0.045 -> -0.011 (jego linii x >= 0.90 jest za mało, spada do puli piłki - V1 **podnosi** jego pewność); reszta kluczy na puli, ~-0.01 w obu.

## Wniosek

- **Wcześniejsze -12 pp było bez line evidence.** Z offsetem i limitem pasma, które CONFIDENCE stosuje, nogi zawodników drukowane bez bramek próbki realizują się -3.2 pp [-13.8, +6.5] pod pewnością - w granicach szumu; limit pasma ceny już robi większość korekty (z 157 linii x >= 0.90 przed evidence zostaje 77).
- **V1 nie jest uzasadnione.** Nogi, które zdejmuje, wypadły trochę gorzej (-7.1 pp vs +0.5), ale przedziały się nakładają i obejmują zero; działa praktycznie tylko na `player_shots_for` (-10.8 pp), a `player_tackles_for` przez spadek do puli dostaje wyższą pewność niż dziś. Ten sam kształt co offset per przedział pewność-cena odrzucony 2026-10-12 (połowa korekty, zdjęte nogi nie gorsze). Nie włączać.
- Wyłączenie bramek próbki dla zawodników (wariant 2) przy dzisiejszym line evidence: około 19 nóg dziennie (77 / 4 dni; 10-12 i 10-13 po 4-8, 10-14 / 10-15 po 28-37), skalibrowane w granicach szumu, ROI -8.6% [-21, +3] - przy cenie, bez zmierzonej przewagi. Line evidence liczy offset ze wszystkich wierszy arkusza, więc dalsze dni dopną je same.

Zastrzeżenia: 4 dni testowe, 42 mecze; krzywe z 10-16 (nie te, którymi budowano 10-12..10-14); ceny z arkusza (nie świeże z CONFIDENCE); klasy (kobiety) pominięte; dni treningowe 10-05..10-11 mają próbki ze wszystkich występów, nie tylko startów.

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
| V0 drukuje | 77 | 42 | 0.785 | 0.829 | 0.753 | -3.2 [-13.8, +6.5] | -8.6 [-21.2, +2.9] |
| V1 drukuje | 53 | 35 | 0.758 | 0.808 | 0.755 | -0.3 [-9.2, +9.4] | -5.8 [-16.9, +6.7] |
| V1 zdejmuje (pewność V0) | 37 | 29 | 0.801 | 0.857 | 0.730 | -7.1 [-23.9, +8.5] | -15.2 [-34.5, +2.7] |
| V1 zostawia (pewność V0) | 40 | 28 | 0.770 | 0.803 | 0.775 | +0.5 [-10.3, +11.8] | -2.6 [-16.0, +11.2] |

## Dzień po dniu (bramki wyłączone)

| grupa | nogi | mecze | pewność | cena | zrealizowane | zreal. - pewn. (pp) | ROI % |
|---|---|---|---|---|---|---|---|
| 2026-10-12 V0 (bez bramek) | 4 | 3 | 0.793 | 0.845 | 1.000 | +20.7 [+17.2, +24.5] | +19.0 [+10.3, +25.0] |
| 2026-10-12 V1 (bez bramek) | 3 | 3 | 0.752 | 0.813 | 1.000 | +24.8 [+21.6, +26.7] | +23.0 [+21.0, +24.3] |
| 2026-10-13 V0 (bez bramek) | 8 | 6 | 0.786 | 0.849 | 0.875 | +8.9 [-4.2, +24.9] | +4.1 [-10.8, +23.8] |
| 2026-10-13 V1 (bez bramek) | 7 | 6 | 0.732 | 0.805 | 0.857 | +12.5 [-6.3, +27.2] | +6.4 [-16.1, +24.7] |
| 2026-10-14 V0 (bez bramek) | 28 | 13 | 0.786 | 0.834 | 0.679 | -10.8 [-23.0, +4.4] | -18.8 [-32.9, -0.7] |
| 2026-10-14 V1 (bez bramek) | 16 | 10 | 0.761 | 0.812 | 0.625 | -13.6 [-32.1, +5.1] | -22.1 [-45.3, +0.8] |
| 2026-10-15 V0 (bez bramek) | 37 | 20 | 0.783 | 0.819 | 0.757 | -2.6 [-20.9, +12.6] | -6.7 [-28.2, +11.4] |
| 2026-10-15 V1 (bez bramek) | 27 | 16 | 0.764 | 0.805 | 0.778 | +1.4 [-10.5, +14.9] | -2.6 [-18.2, +15.3] |

