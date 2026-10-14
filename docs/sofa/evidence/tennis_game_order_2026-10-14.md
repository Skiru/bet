# Tenis: rynki „po N gemach / po N punktach” (`/point-by-point`), 2026-10-14

Superbet wystawia dziś ~3 800 takich rynków (`market_coverage` tn.game_order,
tn.points_in_game), głównie trzy wzorce: „1. set - będzie prowadzić po 2 / 4
gemach” (z remisem), „1. set - dokładny wynik po 4 gemach”, „Dokładny wynik -
wynik po N punktach w 1. gemie serwisowym X”. Były oznaczone „brak źródła”;
Sofascore `/event/{id}/point-by-point` podaje każdy gem (kto serwował, kto
wygrał, wynik w gemach po nim) i bieżący wynik punktowy - źródło jest.

## Dane

- `sofa_event_extra` (kind `point_by_point`), `backfill_event_extra.py
  --kind point_by_point --sport tennis`: mecze z zapisanymi `/statistics`,
  ostatnie 60 dni (pobieranie reszty roku trwa).
- `bet.sofa.point_by_point`: gemy w kolejności gry; test na Gulin - Agamenone
  10-13 zgodny z wynikiem setów ze szczegółów meczu Sofascore (7-5, 6-2);
  suma utrzymanych gemów zgodna z `serviceGamesWon` statystyk.

## Model (tylko dane sprzed meczu)

`scripts/sofa/measure_tennis_game_order.py`: utrzymanie serwisu gracza =
utrzymane / rozegrane gemy serwisowe z jego wcześniejszych meczów ściągnięte
do średniej (K pseudo-gemów), poprawione o odsetek przełamań rywala (logit);
punkt serwisowy tak samo z `servicePointsScored`. Pierwsze 4 gemy seta
niezależne przy tych prawdopodobieństwach (remis i 2:2 nie zależą od tego, kto
serwuje pierwszy).

## Wynik (~7 800 meczów z point-by-point i historią)

| rynek | log-loss względem średniej | górne kubełki: prognoza → zrealizowane (n) |
|---|---|---|
| remis po 2 gemach (K=40) | -0,0332 | 0,72 → 0,688 (234); 0,77 → 0,681 (141); 0,82 → 0,768 (82); 0,87 → 0,824 (51) |
| wynik 2:2 po 4 gemach | -0,0095 | 0,73 → 0,725 (51); 0,77 → 0,657 (35) |
| prowadzenie po 2 gemach | -0,0162 | nic >= 0,65 |
| wynik po 2 / 3 punktach w 1. gemie serwisowym | -0,0002 .. -0,0103 | nic >= 0,60 |

K pseudo-gemów 20 / 40 / 80: ten sam obraz (remis po 2 gemach: -0,0324 /
-0,0332 / -0,0336).

## Werdykt

Model coś wie (remis po 2 gemach -0,033 log-loss), ale **na górze
przeszacowuje o 3-9 pp** i żaden kubełek >= 0,70 nie ma dolnej granicy
>= 0,70 ani 400 prognoz, których wymaga krzywa (`fit_confidence`). Dziś te
rynki nie dałyby ani jednej nogi. Jedyny kandydat: remis po 2 gemach przy
prognozie >= 0,80 (zrealizowane 0,77-0,82) - do ponownego pomiaru na pełnym
roku point-by-point (~5x więcej meczów). Ceny Superbetu tych rynków są
zapisywane od 2026-10-14 (`bet.sofa.unmapped_prices`); bez rozliczonych linii
nie wiadomo, czy nawet trafny model bije kurs (np. remis po 2 gemach @1,61).
Nic nie jest podłączone do kuponu.
