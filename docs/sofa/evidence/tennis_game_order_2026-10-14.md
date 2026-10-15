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

## Ponowny pomiar na pełnym roku (2026-10-14 23:15Z)

Pobieranie `/point-by-point` za rok (`backfill_event_extra.py`, 2026-10-14
15:30-23:12Z, ~1,7 tys. celów zostało, prawie same puste - starsze turnieje
bez point-by-point): 91 187 meczów z point-by-point, 70 275 ze statystykami
serwisu; ten sam skrypt (`measure_tennis_game_order.py`, K domyślne),
walk-forward.

| rynek | n | log-loss względem średniej | prognoza >= 0,70: prognoza → zrealizowane (n, Wilson dolna) |
|---|---|---|---|
| remis po 2 gemach | 45 689 | -0,0313 | 0,724 → 0,695 (1 453, 0,671); 0,773 → 0,717 (911, 0,687); 0,822 → 0,745 (486, 0,704); 0,871 → 0,783 (304, 0,733); 0,907 → 0,730 (37) |
| 2:2 po 4 gemach | 45 618 | -0,0097 | 0,724 → 0,615 (275); 0,773 → 0,625 (224); 0,818 → 0,705 (78) |
| prowadzenie po 2 gemach | 45 689 | -0,0149 | nic >= 0,60 |
| wynik po 2 / 3 punktach gemu serwisowego | 91 400 | -0,0007 .. -0,0078 | nic >= 0,50 |

Werdykt: obraz z 60 dni potwierdzony na ~6x większej próbie - surowa
prognoza **zawyża o 3-9 pp** na górze. Jedyny kandydat to **remis po 2
gemach**: kubełek prognozy 0,80-0,85 realizuje 0,745 (n 486, dolna 0,704), czyli
krzywa z historii (ona mapuje prognozę na zrealizowane, więc zawyżenie
modelu nie przechodzi do pewności) dałaby pewność ~0,72-0,75 przy prognozie
>= 0,80. Kurs Superbetu na „1. set - po 2 - Remis” 10-14: mediana 1,675
(1,40-1,97, 104 mecze, ostatnia cena przed startem). **Nie podpięte**: to
nowy rynek (OFFER, SHEET, SETTLE z point-by-point, przełącznik, krzywa z
bramką jednostronną na holdoucie) - osobny etap, zgodnie z planem nocy. Czy
Superbet nie wycenia niżej właśnie meczów o wysokiej prognozie (dwóch
mocnych serwujących), nie wiadomo bez rozliczonych linii: zapis cen
(`unmapped_prices`) jest od 2026-10-14, a wynik po 2 gemach daje
point-by-point, więc te linie da się rozliczyć wstecz od 10-14.
