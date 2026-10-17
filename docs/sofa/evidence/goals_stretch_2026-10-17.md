# Rozciągnięcie goli w piłce (faworyt / outsider w centrum goli), 2026-10-17

Przełącznik: `epochs.FOOTBALL_GOALS_STRETCH_FROM_UTC` (`goals_stretch_v1`).
Współczynniki: `config/sofa_goals_stretch.json` (pisze
`scripts/sofa/fit_goals_stretch.py`, domyślnie dry-run). Moduł:
`bet.sofa.goals_stretch`. Replay: `calibrate_from_cache.py --goals-stretch`
(`prepare_refit.py rebuild-cache-rows --goals-stretch`). Znacznik wiersza:
`goals_stretch_rule`. Skrypty pomiaru (tylko odczyt) i wyniki:
`/private/tmp/.../scratchpad/goals_ft/` sesji 2026-10-17 (`hist_analyse.out`,
`hist_curve.out`, `stretch_params.json`); liczby poniżej są z tych plików.

## Pytanie operatora

„Rynki goli często się mylą, nie uwzględniamy siły rywala, pada więcej
bramek, niż zakładamy, w każdym sporcie.” Zmierzone osobno dla piłki i tenisa
oraz dla hokeja / kosza / siatki / CS2.

## Diagnoza (piłka)

Siła rywala jest w centrum goli (rating: stawka ligi x e^gap x
(atak x obrona rywala)^k, waga ratingu goals_for 0,95), ale jest **za mało
rozciągnięta**: w meczach nierównych faworyt strzela więcej, outsider mniej,
niż centrum mówi. Sam rating ma to samo nachylenie, więc to nie jest wina
próbki.

Replay historii (centrum odtwarzane mecz po meczu, okno testu
2025-08..2026-10-16, ~383 tys. meczów), faktyczne minus centrum dla
goals_for wg oczekiwanej różnicy goli strony s:

| s | faktyczne - centrum | faktyczne - sam rating |
|---|---|---|
| < -1 | -0,128 | -0,099 |
| -0,5..0,5 | +0,02..+0,04 | |
| 0,5..1 | +0,065 | |
| > 1 | +0,259 [+0,245, +0,273] | +0,221 |

Połowy tak samo (1. połowa -0,128 / +0,303, 2. połowa -0,126 / +0,279 na
krańcach). goals_total przy |s| >= 1,5: +0,357 [+0,334, +0,380] gola (~8%).

Krzywe tego nie zdejmują (są per rynek x linia x kierunek, nie widzą s).
Krzywa kubełkowa dopasowana przed 2026, test na 2026, realizacja minus
pewność >= 0,70: goals_total UNDER przy |s| >= 1,5 -6,6 pp [-7,6, -5,7];
goals_for UNDER faworyta (s > 1) -6,8 pp; goals_for OVER outsidera (s < -1)
-6,1 pp; goals_1h_for UNDER faworyta -8,9 pp; goals_2h_for UNDER faworyta
-10,5 pp.

Żywe dni 2026-10-09..10-16 (2 209 meczów): goals_for faworyta (s >= +0,6)
+0,174 [+0,035, +0,309], outsidera -0,001 [-0,107, +0,107]. Ogólny poziom
(+0,12 gola na mecz) to w dużej części tydzień bramkowy - linia Superbetu
pomyliła się o dwa razy więcej (+0,25).

## Poprawka

Strona: centrum x exp(beta_m x s); suma: centrum x exp(g1_m x |s| + g2_m x
s^2), s = przewaga gospodarza; po GAME_STATE, przed SEASON_PHASE; ta sama
postać co B1. Nie mierzone wcześniej (Dixon-Coles / dwuwymiarowy Poisson
2026-10-08 to inne modele; GAME_STATE wyłączał gole; B15 nie testował goli).

Walk-forward, refit co miesiąc, log-loss NB nowe - stare: goals_for
-0,0010 [-0,0012, -0,0008] (beta 0,063-0,085, stabilne przez 15 miesięcy),
goals_1h_for -0,0074 [-0,0078, -0,0070], goals_2h_for -0,0048 [-0,0052,
-0,0045]. Sumy (fit przed 2026, test 2026, kwadratowa): goals_total -0,0020
[-0,0023, -0,0017] (lepsza od liniowej o -0,00037 [-0,00052, -0,00020]),
goals_1h_total -0,0027, goals_2h_total -0,0019. Po krzywej kubełkowej każdy
rynek lepszy, każdy przedział poniżej zera. Najgorsze typy nóg: goals_total
UNDER |s| >= 1,5 -6,6 -> -5,0 pp; goals_for UNDER faworyta -6,8 -> -3,6;
goals_for OVER outsidera -6,1 -> -3,1; goals_1h_for UNDER faworyta -8,9 ->
-3,9 - mniej więcej połowa błędu.

Fit do instalacji (`fit_goals_stretch.py --before 2026-10-17 --live-rules
--season-phase`, kopia bazy `data/refit_2026-10-17/sofa_replay.db`):
goals_for 0,0620 (1,20 mln stron), goals_1h_for 0,1670, goals_2h_for 0,1276;
goals_total (g1, g2) = (-0,0153, 0,0230), goals_1h_total (-0,0157, 0,0368),
goals_2h_total (-0,0105, 0,0290).

Zastrzeżenia: replay pomiaru przybliża centrum SHEET (bez fazy sezonu, siły
pucharów, GAME_STATE w pomiarze); sprawdzenie po krzywej użyło własnej krzywej
kubełkowej, nie zainstalowanej. Luka par międzyligowych na żywo (+0,17 na
stronę) zostaje po rozciągnięciu (+0,15) - niewyjaśniona, osobny pomiar.
`CROSS_RATIO_POWER` 0,8 vs 0,6: bez znaczenia (-0,0001), 1,0 gorsze.

## Inne sporty (bez poprawki)

- **Tenis:** brak spójnego błędu (games_total, games_won_for, sety, gemy w
  secie skalibrowane w przedziałach). Trop: gemy jednego gracza w 2. secie
  (faworyt +6-7 pp, 8 dni, niesprawdzone na historii).
- **Hokej:** model oczekuje WIĘCEJ goli (-0,147 [-0,185, -0,108] na
  historii) - podwójnie liczone gole do pustej bramki (`score_model.py:520`);
  krzywa to pochłania, nogi >= 0,70 skalibrowane. Poprawka F1 nie lepsza.
- **Koszykówka:** brak błędu poziomu; składnik drużynowy sumy za szeroki
  (nachylenie 0,877); F2 (zwężenie do sumy ligi) lepsze na sumach
  (-0,00084 [-0,00160, -0,00014] historia, -0,00374 Superbet), ale luka
  drukowalna zostaje (-16..-18 pp) - nie wdrażane, wymaga refitu A7.
- **Siatkówka:** punkty +0,80 [+0,19, +1,43] (znane B9, odrzucone).
- **CS2:** skalibrowane albo za mało danych.

## Faza sezonu (`goals_stretch_v2`, 2026-10-17)

Nachylenie goals_for zależy od fazy (fit przed 2026; skrypt
`goals_ft/phase_stretch.py`, wyniki `phase_stretch.out`, `phase_params.json`):
early 0,018, mid 0,056, late 0,064, final 0,063, bez fazy 0,082 (jeden zestaw
0,071). Własny zestaw meczów bez fazy był gorszy od pojedynczego (surowy NB
per faza minus pojedynczy +0,00018 [+0,00011, +0,00025]) - mecz bez fazy
czyta zestaw pojedynczy. Połowy: różni się tylko early (goals_1h_for 0,145 vs 0,167,
goals_2h_for 0,100 vs 0,128). Sumy na fazę nie lepsze od jednego zestawu
(late / final gorsze: goals_2h_total per faza - jeden zestaw +0,00070
[+0,00027, +0,00111] late, +0,00157 final) - zostają pojedyncze.

Plik może więc dać rynkowi zestaw na fazę (`by_phase`; etykiety
`season_phase`, mecz bez fazy = `none`); faza, której plik nie ma, czyta
pojedynczy zestaw rynku, a bez niego centrum zostaje bez zmian. SHEET czyta
fazę z tego samego indeksu co SEASON_PHASE (budowany także przy samym
włączonym rozciągnięciu), replay z `phases_by_event`. Fit:
`fit_goals_stretch.py --per-phase goals_for:early,mid,late,final
goals_1h_for:early goals_2h_for:early` (zawsze także zestaw pojedynczy; faza
poniżej `--min-phase-rows`, domyślnie 500 wierszy, nie dostaje zestawu).
Domyślnie offset niesie zainstalowany mnożnik fazy sezonu (jak pomiar v2;
`--no-season-phase` wyłącza), a księga ratingu siłę lig z pucharów
(`--no-cup-strength` wyłącza).
