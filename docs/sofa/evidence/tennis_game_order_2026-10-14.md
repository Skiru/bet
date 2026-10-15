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

## Rozliczenie kursów Superbetu 10-14 / 10-15 (2026-10-15 10:17Z)

`scripts/sofa/measure_tennis_draw_after_two.py` (tylko odczyt, nic nie jest
podłączone): „1. set - będzie prowadzić po 2 gemach”, selekcja „po 2 - Remis”
z `runs/sofa/<d>/unmapped_prices/`. Na mecz ostatnia cena pobrana **przed**
najwcześniejszym zegarem startu (02_fixtures `kickoff_utc` /
`superbet_kickoff_utc`, 04_offer `superbet_started_utc` /
`superbet_kickoff_seen_utc`, fixture_status, `/event startTimestamp`); kurs w
stanie live (`offerStateId` 2) nigdy. Parowanie Superbet → Sofascore to
parowanie RESOLVE zapisane w rekordzie. Wynik z `/point-by-point`: wygrana,
gdy po 2. gemie seta 1 jest 1:1 - **oba gemy utrzymane LUB oba przełamane**.
Prognoza: model serwisu z tego skryptu as-of meczu, P(1:1) = hA·hB +
(1-hA)(1-hB). Uwaga: wiersz „remis po 2 gemach” w sekcjach wyżej to hA·hB
(oba utrzymane) - to nie jest zdarzenie, które rozlicza Superbet (1:1 po
dwóch przełamaniach też wygrywa); kandydat „prognoza >= 0,80” dotyczył hA·hB.

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_draw_after_two.py \
    --date 2026-10-14 --date 2026-10-15 --fetch --max-minutes 5 \
    --json-out <f> --md-out <f>
```

(`--fetch`: `/event` i `/point-by-point` przez most tylko dla tych meczów;
`backfill_event_extra.py` nie nadaje się - bierze tylko mecze z `/statistics`
i starsze niż 72 h. 10:09-10:17Z: 185 zapytań `/event` i 115 `/point-by-point`, 0 odmów.)

| grupa | n | trafione | trafność | śr. P(1:1) | śr. hA·hB | śr. 1/kurs | ROI [95% bootstrap po meczach, 2000] |
|---|---|---|---|---|---|---|---|
| razem | 93 | 56 | 0,602 | 0,558 | 0,437 | 0,589 | +1,6% [-15,1, +19,2] |
| 10-14 | 79 | 48 | 0,608 | 0,560 | 0,440 | 0,592 | +1,7% [-16,1, +20,3] |
| 10-15 (zakończone do 10:16Z) | 14 | 8 | 0,571 | 0,545 | 0,420 | 0,568 | +1,3% [-41,0, +45,5] |
| P(1:1) >= 0,80 lub hA·hB >= 0,80 | 0 | | | | | | |

Kurs: 1,40-1,97, mediana 1,67. Najwyższa prognoza P(1:1) 0,69 (hA·hB 0,65) -
tablica 10-14/15 to głównie ITF, więc grupa „>= 0,80” jest pusta.

Poza pieniędzmi (na dzień, 10-14 / 10-15): mecze z ceną 104 / 162, z ceną
przed startem 92 / 161 (12 / 1 meczów miało tylko ceny po zaplanowanym
starcie - odrzucone, 82 / 12 rekordów); rozliczone 79 / 14; zwrot (krecz)
2 / 2, z tego 1 krecz już po 2. gemie seta 1 (Superbet mógłby taki rynek
rozliczyć - liczony jako zwrot, jak SETTLE); brak point-by-point 2 / 3;
point-by-point niezgodne z wynikiem seta 1 (np. gemy do 6:3 przy 6:4) 3 / 0 -
wykluczone; nierozstrzygnięte 6 / 142 (10-14: mecze przerwane / przeniesione
w Edmond i Lexington). 24 z 186 stron nie miało żadnego wcześniejszego meczu
ze statystykami serwisu (prognoza = średnia puli).

Werdykt: **jeden-dwa dni to za mało na jakąkolwiek decyzję** - przedział ROI
ma szerokość ~34 pp (od -15% do +19%), trafność 0,602 przy cenie 0,589 mieści
się w szumie, a próg z historii (>= 0,80) nie wystąpił ani razu. Post hoc i
bez znaczenia statystycznego: P(1:1) >= 0,60 - 22 mecze, 15 trafień, ROI
+9,8%. Pomiar do powtórzenia, gdy rozliczonych linii będzie kilkaset (ceny
zapisywane codziennie od 10-14).

### Aktualizacja 2026-10-15 ~22:00Z: 10-15 dokończone

Ta sama komenda z `--fetch` (most: 150 zapytań, 125 zakończonych meczów z
point-by-point, 0 odmów):

| grupa | n | trafienia | realizacja | P(1:1) | 1/kurs | ROI [95% bootstrap meczów] |
|---|---|---|---|---|---|---|
| razem | 211 | 124 | 0,588 | 0,563 | 0,595 | -1,9% [-13,3; +9,1] |
| 10-14 | 82 | 50 | 0,610 | 0,562 | 0,594 | +1,8% [-15,6; +19,8] |
| 10-15 | 129 | 74 | 0,574 | 0,564 | 0,596 | -4,3% [-18,2; +10,0] |
| P(1:1) >= 0,80 | 0 | | | | | |

10-15: rozliczone 129, krecz 2 + 4 po 2. gemie (zwrot), nierozstrzygnięte
22, nie znalezione 6. Werdykt bez zmian: dwa dni to za mało; trafność ~ cena;
próg >= 0,80 z historii na tablicy Superbetu nie występuje (ITF) - do
powtórzenia po kilkuset liniach.
