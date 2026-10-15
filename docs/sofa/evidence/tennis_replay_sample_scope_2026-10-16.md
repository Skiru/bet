# Tenis w replayu: próbka gemów bez filtra formatu i nawierzchni (2026-10-16, noc)

Pozycja z listy „Before the next refit” w CLAUDE.md: „measure the
best-of-five games_total / games_won_for samples of the replay (not
format-scoped) before a fix”.

## Problem

Żywy SAMPLES bierze do próbki tenisa tylko mecze w formacie meczu wycenianego
(`samples.py`: `infer_best_of(event) != fixture.default_period_count` ->
odrzucony) i na porównywalnej nawierzchni (`settle.surfaces_comparable`).
Replay (`calibrate_from_cache.recent_for`) brał ostatnie 10 meczów z gemami
bez żadnego z tych filtrów - komentarz w kodzie mówił to wprost („SAMPLES'
scoping of tennis (surface / best-of) is not replayed”). Krzywe
`games_total` / `games_won_for` są więc dopasowane na wierszach, w których p
liczono z innej próbki niż ta, z której SHEET wycenia.

## Pomiar

`scripts/sofa/measure_tennis_bo5_samples.py --db
data/refit_2026-10-16/sofa_replay.db` (tylko odczyt; mecze best-of-three od
2025-01-01, historia od 2024-07-01; środek = średnia próbki, log-loss przy
linii floor(średnia S)+0,5 z rozkładu normalnego z rozrzutem próbki - wspólna
miarka, nie NB SHEET-u; bootstrap meczów 95%, 2 000 powtórzeń). R = próbka
replayu, S = sam filtr formatu, FS = format i nawierzchnia (reguła SAMPLES).
Oceniane tylko mecze, w których próbki się różnią.

32 385 meczów best-of-three z próbką obu zawodników. Próbka sumy z meczem
best-of-five: **4 264 (13%)** - ATP 2 658 z 4 695 (**57%**), Challenger 1 446
z 11 167, Puchar Davisa 120 z 179; WTA / UTR / WTA 125: 0.

| rynek | wiersze | przesunięcie środka R - x | obciążenie R | obciążenie x | SE R - x | log-loss R - x |
|---|---|---|---|---|---|---|
| suma gemów, x = S | 4 264 | +1,97 [+1,91; +2,02] | +1,83 [+1,64; +2,01] | -0,14 [-0,32; +0,04] | +5,17 [+4,15; +6,12] | +0,0445 [+0,0377; +0,0509] |
| gemy zawodnika, x = S | 5 702 | +1,26 [+1,22; +1,30] | +1,26 [+1,14; +1,37] | -0,00 [-0,11; +0,11] | +3,01 [+2,62; +3,40] | +0,0171 [+0,0094; +0,0248] |
| suma gemów, x = FS | 21 876 | +0,36 [+0,34; +0,38] | +0,17 [+0,09; +0,24] | -0,20 [-0,28; -0,12] | +0,48 [+0,24; +0,74] | +0,0087 [+0,0062; +0,0112] |
| gemy zawodnika, x = FS | 23 700 | +0,11 [+0,10; +0,13] | +0,27 [+0,22; +0,32] | +0,16 [+0,10; +0,21] | +0,37 [+0,22; +0,50] | -0,0014 [-0,0045; +0,0016] |

## Wniosek

- Mecz z Wielkiego Szlema w próbce zawyża środek replayu o ~2 gemy (sumy) i
  ~1,3 (gemy zawodnika); filtr formatu usuwa obciążenie prawie do zera.
- Filtr nawierzchni dokłada poprawę na sumie (log-loss -0,0087 dla FS), na
  gemach zawodnika jest neutralny.
- Poprawka poprawności: `calibrate_from_cache.py --tennis-sample-scope`
  (`prepare_refit.py rebuild-cache-rows --tennis-sample-scope`) - próbka
  tenisa jak w SAMPLES (format meczu, porównywalna nawierzchnia, nieznana
  nawierzchnia meczu = brak próbki). Zmienia tylko replay, czyli krzywe przy
  następnym refitcie; SHEET już tak wycenia. `replay_rules` zapisuje flagę.
