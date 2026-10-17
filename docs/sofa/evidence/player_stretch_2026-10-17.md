# Rozciągnięcie strzałów zawodnika (siła drużyny w meczu), 2026-10-17

Przełącznik: `epochs.FOOTBALL_PLAYER_STRETCH_FROM_UTC` (`player_stretch_v1`,
`None` = wyłączony). Współczynniki: `config/sofa_player_stretch.json` (pisze
`scripts/sofa/fit_player_stretch.py`, domyślnie dry-run). Moduł:
`bet.sofa.player_stretch` (arytmetyka wspólna, `bet.sofa.supremacy_stretch`).
Replay: `calibrate_from_cache.py --player-stretch` (`prepare_refit.py
rebuild-cache-rows --player-stretch`). Znacznik wiersza: `player_stretch_rule`
(każdy wiersz piłkarski). Skrypty pomiaru (tylko odczyt) i wyniki:
`/private/tmp/.../scratchpad/sup_ftres/` sesji 2026-10-17
(`player_replay.py`, `player_eval.py`, `player_eval.json`, `params.json`).

## Poprawka

Centrum zawodnika (średnia jego wyjściowych składów) x exp(beta x s), s =
oczekiwana różnica goli JEGO drużyny dziś (`FootballForecast.supremacy` strony
próbki), przycięta do +-3. Tylko `player_shots_for` i
`player_shots_on_target_for`; nie rynki szczegółu strzałów (własny estymator),
nie faule / odbiory / spalone / asysty (bez zysku albo krzywa OVER nieistotna).

## Pomiar

Wiersze zawodników z replayu (tylko wyjściowe składy, jak
`calibrate_from_cache.build_player_rows`), fit przed 2026, test 2026, log-loss
na liniach drabinki (x1e-4, bootstrap meczów):

| rynek | beta | surowo | po krzywej OVER | po krzywej UNDER | linie / mecze testu |
|---|---|---|---|---|---|
| player_shots_for | 0,126 | -19,1 [-22,6, -15,4] | -28,7 [-33,6, -24,2] | -13,5 [-17,1, -9,3] | 460 879 / 8 539 |
| player_shots_on_target_for | 0,117 | -6,5 [-9,3, -4,0] | -12,8 [-17,3, -8,9] | -11,1 [-13,9, -8,1] | 232 821 / 8 495 |

Wariant względny (s dziś minus średnie s meczów próbki) mierzył większą betę
(0,186 / 0,182), ale wymaga przeszłych s próbki, których SHEET nie ma - nie
wdrażany. Pomiar zostawił wiersze z >= 3 ocenionymi meczami próbki (dla
porównania wariantów); skrypt fitu bierze każdą próbkę z s dziś, bo SHEET
stosuje poprawkę do każdego wiersza zawodnika z s dziś. Fit czyta księgę
ratingu z siłą lig z pucharów (domyślnie, `--no-cup-strength` wyłącza) i
reguły księgi z epok na dzień `--before`.

## Zastrzeżenia

Krzywe zawodników trzeba przeliczyć na replayu z `--player-stretch` przed
włączeniem. Przy cenach Superbetu na rekwizyty zawodników nie było mierzonej
przewagi (`football_props_2026-10-15.md`) - poprawka dotyczy kalibracji, nie
zysku.
