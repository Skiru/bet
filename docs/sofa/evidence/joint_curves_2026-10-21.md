# Krzywe historii łącznych rynków piłkarskich (2026-10-21)

Operator (2026-10-21): każdy rynek Superbetu ma móc się wydrukować; liczenie
rynku, który nigdy się nie drukuje, nie ma sensu. Łączne rynki baz spoza
`DERIVED_MARGINAL_CENTRES_METRICS` (`both_over_` / `handicap_` / `most_` goli
i rożnych połów, obron, fauli, strzałów, spalonych, autów, wybić, odbiorów)
SHEET wycenia z surowych próbek stron (`derived.price_derived_rungs`), ale nie
miały krzywej historii.

## Metoda

`scripts/sofa/fit_joint_curves.py` na bazie replayu
`data/refit_2026-10-17/sofa_replay.db` (tylko do odczytu, `load_cache(...,
read_only=True)`; 968 402 mecze piłkarskie, 80 815 kobiet):

- próbka strony jak w replayu (`recent_for`: SAMPLE_N 10, MIN_SAMPLE 8,
  reguła tej samej rozgrywki dla goli połów), mecz nigdy we własnej próbce,
  towarzyski poza historią, rozgrywki towarzyskie poza dopasowaniem;
- p = `calibrate_from_cache.football_joint_rows` bez środków brzegowych - ta
  sama ścieżka co SHEET dla tych baz; korelacja stron z
  `config/sofa_side_correlations.json` (brak = 0, jak SHEET dziś). Korelacje
  rezydualne zmierzone na oknie treningowym (goals_1h -0,035, goals_2h
  -0,061, saves -0,072, saves_1h -0,059) **nie** zostały użyte: zmiana
  pliku zmieniłaby p SHEET; zapisane w `correlations.json` grupy;
- dopasowanie przed 2026-09-01, holdout 09-01..10-13, krzywa końcowa przed
  2026-10-17; bramka jednostronna `new_market_gate` (krzywa >= 0,70, n >= 300,
  realizacja - krzywa >= -2 pp) + `require_final`.

**Krzywa wspólna linii nie nadaje się**: na holdoucie linie jednego klucza
różnią się o 5-10 pp, np. `both_over_goals_1h|UNDER` 0,5 -2,88 pp
[-3,36, -2,34] obok 1,5 +8,88 pp; `handicap_saves|OVER` 0,5 -9,85 pp obok 4,5
+7,10 pp. Dlatego dla nóg mężczyzn stawiamy krzywe **per linia**
(`by_market_direction_line`, czytane pierwsze przez
`Calibration.realised(line=)`, `epochs.LINE_CURVES`), każda dopasowana i
bramkowana na wierszach swojej linii; krzywej wspólnej nie instalujemy (linia
bez własnej krzywej nie ma krzywej). Klasa `women` (noga kobiet nie czyta
krzywych linii): krzywa wspólna klasy, odrzucona gdy wycinek linii z
n >= 300 zawyża o > 2 pp.

## Wynik - grupa 1 (gole połów, obrony)

Przeszły (holdout n przy krzywej >= 0,70; luka realizacja - krzywa, 95% CI
bootstrap meczów):

| klucz@linia | n | luka pp |
|---|---|---|
| both_over_goals_1h UNDER@0.5 | 21 846 | -1,13 [-1,61, -0,61] |
| both_over_goals_1h UNDER@1.5 | 4 262 | -0,16 [-0,73, +0,29] |
| both_over_goals_2h UNDER@0.5 | 18 535 | -1,73 [-2,45, -1,13] |
| both_over_goals_2h UNDER@1.5 | 9 367 | -0,29 [-0,72, +0,14] |
| both_over_goals_2h UNDER@2.5 | 562 | +0,23 [-0,49, +0,93] |
| both_over_saves OVER@0.5 | 5 268 | +2,39 [+1,47, +3,25] |
| both_over_saves UNDER@2.5 / 3.5 / 4.5 / 5.5 | 2 799 / 4 818 / 2 142 / 325 | -1,86 / -1,40 / -0,56 / +2,24 |
| both_over_saves_1h UNDER@1.5 / 2.5 | 2 405 / 503 | -0,89 / +0,87 |
| handicap_saves OVER@1.5..4.5, handicap_saves_1h OVER@1.5..3.5 | | (gate_report.md) |
| handicap_goals_1h / _2h OVER@0.5..4.5 | | (Superbet ich nie oferuje) |

`both_over_goals_1h|OVER`, `_2h|OVER`, `most_goals_1h/_2h`, `most_saves(_1h)`:
żadna prognoza holdoutu nie sięga krzywej 0,70 - nie drukują się.

Kobiety (`women:`): przeszły `both_over_saves|UNDER`, `handicap_saves_1h|OVER`;
z zainstalowanego replayu (`--stored-rows`, wiersze `cache-calibration`
refitu 10-17): `both_over_corners` OVER / UNDER, `both_over_goals|UNDER`
(n 3 585, -0,80 [-1,97, +0,36]), `both_over_shots_on_target|UNDER`,
`handicap_cards_points`, `handicap_corners`, `handicap_goals`,
`handicap_shots_on_target`. Nie przeszły: `women:most_corners` (żadna
prognoza >= 0,70), `women:most_goals` (-3,41 pp), `women:both_over_goals_1h /
_2h|UNDER` (wycinek 0,5 zawyża).

## E2E (kopia 2026-10-20, ramię „on” audytu 10-21, SOFA_NOW 06:45Z)

`DERIVED_CURVES` wymuszony w obu ramionach; A = konfiguracja zainstalowana,
B = + krzywe grupy 1 i kobiet (`stage1`). Nogi łączne w `08_confidence.json`:
**A 1, B 1** - każda noga łączna odpada na `THIN_SAMPLE_FOR_BUILDER`
(`side_observations` czyta próbkę pod nazwą rynku łącznego, której
`03_samples.json` nie ma). Z bramkami kształtu zdjętymi dla wiersza bez
obserwacji (tylko symulacja): A 151, B 283 nóg łącznych (+81
`both_over_goals_1h` UNDER, +73 `both_over_goals_2h` UNDER - wcześniej 20 i 4
z ewidencji linii -, +2 `both_over_saves` OVER), źródło
`line:<klucz>@0.5` obniżone offsetem sportu.

Pliki: `data/refit_joint_curves_2026-10-21/` (`g1/`, `women_installed/`,
`stage1/joint_curves/curves.json` do instalacji).
