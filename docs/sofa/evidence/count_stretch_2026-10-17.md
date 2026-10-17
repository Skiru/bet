# Rozciągnięcie liczników w piłce (faworyt / outsider poza GAME_STATE), 2026-10-17

Przełącznik: `epochs.FOOTBALL_COUNT_STRETCH_FROM_UTC` (`count_stretch_v1`,
`None` = wyłączony). Współczynniki: `config/sofa_count_stretch.json` (pisze
`scripts/sofa/fit_count_stretch.py`, domyślnie dry-run). Moduł:
`bet.sofa.count_stretch` (arytmetyka wspólna z rozciągnięciem goli,
`bet.sofa.supremacy_stretch`). Replay: `calibrate_from_cache.py
--count-stretch` (`prepare_refit.py rebuild-cache-rows --count-stretch`).
Znacznik wiersza: `count_stretch_rule` (każdy wiersz piłkarski). Skrypty
pomiaru (tylko odczyt) i wyniki: `/private/tmp/.../scratchpad/sup_ftcount/`
sesji 2026-10-17 (`a_extend.py`, `b_walk.py`, `d_analyse.py`, `h_phase.py`,
`params.json`); liczby poniżej są z `params.json`.

## Poprawka

Strona: centrum x exp(beta x s [+ beta2 x s^2]); suma: centrum x exp(g1 x |s|
+ g2 x s^2), s = oczekiwana różnica goli strony (suma: gospodarza) z księgi
goli ratingu, przycięta do +-3 (`MAX_SUPREMACY`, niedopasowane). Po
GAME_STATE i venue prior, na centrum zblendowanym albo z samej próbki. Rynki
GAME_STATE (rożne, strzały, kartki, faule strony) nie są ruszane.

## Pomiar

Replay centrum liczników SHEET mecz po meczu (ostatnie 10 wartości, korekta
rywala B15, K rynku, stawka ligi, blend z ratingiem gdzie rynek jest
oceniany; zasady na żywo z 2026-10-16). Log-loss NB nowe - stare (x1e-4,
bootstrap meczów): walk-forward od 2025-08; po krzywej kubełkowej: fit przed
2026 / test 2026 oraz fit 2026-H1 / test od 2026-07. Współczynniki: fit
2026-01-01..2026-10-16 (dojrzała księga ratingu).

| rynek | postać | wsp. | walk-forward NB | krzywa, <2026 -> 2026 | krzywa, H1 -> 07.. | mecze |
|---|---|---|---|---|---|---|
| corners_1h_for | s | +0,1390 | -108,9 [-123,8, -94,8] | -59,3 [-68,6, -50,1] | -55,9 [-69,1, -43,3] | 23 932 |
| corners_2h_for | s | +0,1202 | -85,0 [-99,0, -70,9] | -50,3 [-58,9, -41,5] | -47,4 [-58,3, -36,4] | 23 932 |
| shots_1h_for | s | +0,0425 | -30,9 [-42,1, -19,7] | -25,4 [-33,2, -17,2] | -20,5 [-28,6, -12,8] | 23 905 |
| shots_2h_for | s | +0,1609 | -316,0 [-341,2, -289,7] | -195,8 [-216,4, -175,6] | -203,3 [-233,4, -171,2] | 23 905 |
| shots_on_target_for | s | +0,0518 | -33,6 [-40,0, -27,6] | -32,2 [-36,2, -28,4] | -24,3 [-28,3, -20,0] | 54 441 |
| shots_on_target_1h_for | s | +0,0795 | -44,2 [-54,7, -33,3] | -28,7 [-34,5, -22,9] | -24,5 [-32,6, -17,1] | 23 473 |
| shots_on_target_2h_for | s | +0,1873 | -220,3 [-240,6, -199,1] | -120,2 [-131,8, -108,9] | -124,5 [-143,8, -106,1] | 23 473 |
| offsides_for | s | +0,0262 | -3,4 [-5,1, -1,4] | -3,0 [-4,5, -1,4] | -2,3 [-4,3, -0,3] | 58 165 |
| saves_for | s | -0,1693 | -213,5 [-227,9, -198,7] | -108,0 [-116,5, -100,4] | -107,6 [-119,6, -94,8] | 47 350 |
| saves_1h_for | s | -0,1859 | -122,1 [-137,4, -107,9] | -72,0 [-82,3, -61,9] | -71,2 [-87,8, -56,1] | 23 206 |
| throw_ins_for | s + s^2 | +0,0457, -0,0171 | -92,8 [-101,4, -84,5] | -52,8 [-59,7, -45,6] | -52,8 [-64,3, -42,0] | 48 952 |
| goal_kicks_for | s | -0,1360 | -308,7 [-327,0, -290,8] | -183,6 [-195,7, -170,4] | -178,6 [-199,0, -157,4] | 48 632 |
| shots_on_target_total | \|s\| | +0,0204 | -9,1 [-12,5, -5,3] | -5,0 [-7,3, -2,5] | -5,5 [-9,1, -1,6] | 54 441 |
| saves_total | \|s\| | +0,0212 | -7,7 [-10,4, -4,9] | -6,5 [-8,9, -4,0] | -4,8 [-7,8, -1,9] | 47 350 |
| saves_1h_total | \|s\| | +0,0250 | -4,6 [-8,0, -1,0] | -3,8 [-6,4, -1,1] | -5,9 [-10,8, -0,7] | 23 206 |
| throw_ins_total | \|s\| + s^2 | +0,0069, -0,0190 | -35,6 [-44,2, -26,6] | -18,2 [-25,3, -11,5] | -15,9 [-26,7, -5,0] | 48 952 |

Walk-forward NB i oba sprawdzenia po krzywej poniżej zera na wszystkich 16
rynkach. Surowy NB stałego fitu nie jest istotny dla shots_1h_for (fit przed
2026: -0,0 [-14,2, +14,1]) i offsides_for (fit 2026-H1: -2,4 [-5,2, +0,3]).
offsides_1h_for odpadł, bo nie przeszedł sprawdzenia po krzywej 2026-H1
(-3,2 [-7,4, +1,1]).

Faza sezonu: nachylenia liczników nie zależą od fazy (`h_phase.py`), osobne
współczynniki na fazę nigdy nie były lepsze - jeden zestaw na rynek.

Bez poprawki (zmierzone): rożne / strzały strony (beta GAME_STATE wystarcza),
faule (zysk przed 2026 nie utrzymał się od 2026-07), kartki (wymagałyby
zastąpienia bety GAME_STATE - poza zakresem), odbiory, sumy rożnych /
strzałów / spalonych (krzywa kubełkowa to wchłania). Połowy wrzutów / wybić
od bramki nie były w replayu pomiaru.

## Zastrzeżenia

Centrum fitu (`fit_count_stretch.walk`, odtworzenie `b_walk.py`; na
`ext_history.pkl` pomiaru daje wszystkie 16 współczynników co do 5. miejsca
po przecinku) różni się od centrum SHEET i replayu dla 8 metryk bez ratingu
(shots_2h, shots_on_target_2h, saves, saves_1h, throw_ins, goal_kicks i ich
sumy): stawka ligi to tu bieżąca średnia ligi (albo płci), a w SHEET
`resolve_prior` / baseline'y z configu; venue prior nie jest odtwarzany.
Znane przybliżenie, nie zmieniane - do sprawdzenia po replayu z
`--count-stretch` (reszty faktyczne - centrum wg s na wierszach replayu).
Domyślnie fit czyta księgę ratingu z siłą lig z pucharów (jak SHEET od
2026-10-16; pomiar czytał zwykłą księgę - `--no-cup-strength` go odtwarza).

Replay pomiaru nie odtwarza venue prior (dotyczy tylko centrum z samej
próbki; połowy rożnych są na żywo oceniane ratingiem, RATED_SCOPE) ani siły
pucharów. Krzywe piłkarskie trzeba przeliczyć na replayu z
`--count-stretch` przed włączeniem. Czy nogi przebiją cenę Superbetu - nie
mierzone.
