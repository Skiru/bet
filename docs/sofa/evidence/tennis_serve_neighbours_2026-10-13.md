# B6: tenis - siła serwisu jako druga współrzędna doboru sąsiadów (audyt 2026-10-13)

Test zarejestrowany (decyzja operatora O4). Skrypt:
`scripts/sofa/measure_tennis_serve_neighbours.py` (tylko odczyt).
Źródło: `docs/sofa/history/AUDYT_RYNKOW_KONTEKST_2026-10-13.md`, wiersz B6,
Część 3 (`games_won_for` „Rozwiązanie (i)”, „Braki wspólne” 1), dziennik V3-6.

## Diagnoza (sprawdzona w kodzie 2026-10-13, commit 3993281f)

- `src/bet/sofa/tennis_rating.py:621` `_window`: 600 wierszy tabeli o
  najbliższym p zwycięstwa - jedyna współrzędna to p.
- `:716` `TennisRatingModel.forecast`: komórka tier × płeć (albo tier, albo
  pula), potem `_window(cell.rows, cell.keys, p_home)`; ani powierzchnia, ani
  serwis / return graczy nie wpływa na dobór sąsiadów.
- `:941` `AsOfRating._add`: wiersz tabeli ma tylko p meczu (i tier / płeć);
  żadnej miary serwisu. Dane są w `sofa_event_stats.statistics_json`
  (punkty serwisowe i returnowe, `measure_tennis_calibration.parse_serve_points`).

## Co jest nowe wobec odrzuconego modelu serwis/return (2026-10-08)

Odrzucony 2026-10-08 (`docs/sofa/evidence/tennis_calibration_2026-10-08.md`,
„Rozkład serwis/return”) był **zastępstwem rozkładu**: model punktowy
Klaassen-Magnus (punkt → gem → set → mecz, sety niezależne) wyliczał rozkład
gemów zamiast tabeli sąsiadów (gorszy o 0,01-0,07 nat), albo był z nią
mieszany 50/50 / 25% (zysk = kasowanie obciążenia tabeli; 25% INCONCLUSIVE).
Tutaj **nie ma modelu iid ani mieszanki**: rozkład zostaje empiryczny (te same
wiersze historii, ten sam `read`), zmienia się tylko **który** 600 meczów
historii jest sąsiadami - bliskie nie tylko w p zwycięstwa, ale i w indeksie
dominacji serwisu meczu D. Cel: zmierzona reszta (korelacja suma s−r z resztą
gemów ponad p Elo 0,11, n = 10 830, 10-08), której jednowymiarowy klucz nie
widzi. To nowa oś w rozumieniu O4.

## Rejestracja (zapisana 2026-10-13 PRZED uruchomieniem pomiaru)

**Indeks D.** Oceny serwisu s_i i returnu r_i online (SGD na punktach
serwisowych z `/statistics`, P(punkt | i serwuje do j) = σ(μ + s_i − r_j),
μ per płeć × powierzchnia 3-kl.), parametry **z 10-08, bez strojenia**:
m0 = 8, floor 0,06 (krok max(floor, 1/(m + m0)), delta obcięta do ±2).
D meczu = (s_A − r_B) + (s_B − r_A), liczony **przed** meczem (z meczów sprzed
dnia dla meczu testowego; dla wiersza tabeli - sprzed tego meczu). D znane,
gdy obaj gracze mają >= 6 meczów ze statystyką (jak test 10-08).

**Metryka odległości (jedna, z góry).** W komórce, którą wybiera produkcja
(tier × płeć / tier / pula, `SCOPED_MIN_TABLE`), kandydaci = wiersze z
znanym D; odległość (Δp/σ_p)² + (ΔD/σ_D)², σ = odchylenie standardowe p i D
kandydatów komórki w danym dniu; sąsiedzi = 600 najbliższych (dokładnie: pasmo
po p poszerzane, aż 600. odległość 2D jest mniejsza niż brzeg pasma). Jedna
waga (1:1), żadnego strojenia. Gdy D meczu nieznane albo kandydatów < 600 -
sąsiedzi produkcyjni (1D), czyli wariant = baza.

**Estymator bazowy.** Produkcyjny odczyt sąsiadów (1D, `AsOfRating`, tabela
tier × płeć, V5), ten sam p meczu w obu wariantach.

**Rodziny i linie.** Siatki stałe z drabin Superbetu w `05_sheet.json`
2026-10-09..10-12 (policzone przed pomiarem):
`games_won_for` 9,5..14,5 (i osobno 12,5-14,5, gdzie drukujemy UNDER);
`games_total` 17,5..25,5; `handicap_games` −6,5..+6,5 (strona, jak
`read`); `tiebreaks_total` 0,5 / 1,5; `sets_total` 2,5; `games_set1_total`,
`games_set2_total` 6,5..12,5; `games_won_set1_for` 2,5..6,5. Oba kierunki
(handicap: OVER), obie strony dla rynków gracza.

**Okno i podział.** Jak B5 (`tennis_set_markets_2026-10-13.md`): W1 =
2026-03-01..06-14, W2 = 2026-06-15..10-12, walk-forward, współczynniki i
`tier_start` dopasowane przed początkiem okna, tabela i oceny serwisu tylko z
meczów sprzed dnia meczu.

**Populacja.** Jak B5; główny wynik na meczach z **znanym D** (tam, gdzie
wariant różni się od bazy); udział takich meczów raportowany per tier.

**Metryka.** Średni log-loss wiersza (p obcięte do [0,01; 0,99] - odczyt z
600 sąsiadów może dać 0), różnica wariant − baza, 95% przedział z bootstrapu
po meczach (2000, ziarno 0).

**Próg (z audytu, z góry).** Per rodzina: górna granica 95% < 0 **w obu
oknach** oraz **po rekalibracji koszykowej** (krzywa koszykowa `EDGES` per
rodzina i kierunek, dopasowana osobno dla każdego wariantu na wierszach W1,
oceniona na W2: górna granica < 0). Tylko wtedy wdrożenie za przełącznikiem
`epochs.TENNIS_SERVE_NEIGHBOURS_FROM_UTC`.

**Bramki kształtu.** Jak B5: wiersze z p wariantu >= 0,70, ile odrzuciłyby
`LINE_BEYOND_SAMPLE` / `MODE_LOSES` na własnej próbce (ostatnie 10 meczów,
ta sama rodzina nawierzchni, best-of-3) - dla rodzin z próbką (`games_won_for`,
`games_total`, `tiebreaks_total`, `sets_total`, gemy w secie); handicap to
wiersz pochodny bez próbki jednego rynku - nie liczony.

**Zastrzeżenia z góry.** Statystyki serwisu są głównie dla TOUR / CH; w ITF
D będzie zwykle nieznane, więc wariant tam = baza. Wdrożenie wymagałoby
wczytania `sofa_event_stats` do historii ratingu w SHEET i w replayu
(`calibrate_from_cache.py`) oraz refitu krzywych tenisa.

## Wynik (2026-10-13, `data/audit_2026-10-13/b6/` w worktree, 795 s)

Statystyki serwisu: 72 382 mecze z `sofa_event_stats`. Mecze z prognozą
ratingu i znanym D (W1 / W2): TOUR 2 158 z 2 242 / 2 512 z 2 624 (96%),
CH 3 689 z 4 294 / 4 371 z 5 008 (86-87%), ITF 6 082 z 19 096 / 7 820 z
23 545 (32-33%). Razem 26 632 mecze w populacji głównej; poza nią wariant =
baza.

Log-loss, sąsiedzi 2D − sąsiedzi 1D, 1e-4 nat na wiersz, 95% przedział z
bootstrapu po meczach (2000):

| rodzina | wiersze | W1+W2 | W1 | W2 | W2 po rekalibracji | próg |
|---|---|---|---|---|---|---|
| `games_won_for` | 639 168 | +8,1 [+1,5; +14,3] | +14,5 [+4,4; +24,5] | +2,9 [−6,1; +11,7] | +9,6 [+2,5; +16,4] | nie (gorzej) |
| `games_total` | 479 376 | −7,7 [−17,8; +1,9] | −2,5 [−16,4; +11,7] | −11,9 [−25,1; +0,9] | −4,5 [−13,1; +3,7] | nie |
| `handicap_games` | 745 696 | +17,7 [+10,5; +25,2] | +30,2 [+18,9; +41,4] | +7,6 [−2,0; +17,5] | +9,6 [+2,6; +16,6] | nie (gorzej) |
| `tiebreaks_total` | 106 528 | −32,6 [−41,5; −23,8] | −40,1 [−53,2; −26,9] | −26,6 [−39,2; −14,8] | −12,5 [−18,8; −6,4] | **tak** |
| `sets_total` | 53 264 | +15,2 [+5,9; +24,8] | +17,7 [+2,3; +32,2] | +13,2 [+0,2; +25,8] | +6,6 [−0,1; +13,1] | nie (gorzej) |
| `games_set1_total` | 319 584 | −7,9 [−14,6; −1,4] | −6,0 [−16,4; +3,9] | −9,4 [−17,9; −0,9] | −12,9 [−21,6; −4,5] | nie (W1) |
| `games_set2_total` | 319 584 | −10,8 [−17,5; −4,0] | −10,7 [−21,4; −0,4] | −10,9 [−20,0; −1,9] | −11,2 [−20,7; −2,5] | **tak** |
| `games_won_set1_for` | 532 640 | +7,0 [+1,3; +12,5] | +10,4 [+1,3; +19,2] | +4,2 [−3,3; +12,0] | +4,2 [−2,2; +10,7] | nie (gorzej) |

`games_won_for` na liniach 12,5-14,5 (tam drukujemy UNDER): −2,2 [−9,2; +4,6]
- bez zysku.

Kalibracja strefy p >= 0,70 (wiersze, średnie p → zrealizowane): baza i
wariant są skalibrowane podobnie (np. `games_won_for` 0,815 → 0,811 vs
0,807 → 0,814; `sets_total` 0,755 → 0,738 vs 0,748 → 0,751).

Bramki kształtu przy p wariantu >= 0,70 (na własnej próbce; w nawiasie baza):
`games_won_for` LINE_BEYOND 22 248 (22 201), MODE_LOSES 19 587 (22 593);
`games_total` 700 (744) / 11 811 (12 798); `tiebreaks_total` 16 101 (16 101) /
59 (108); `sets_total` 23 (23) / 199 (339); `games_set1_total` 13 580
(13 577) / 7 404 (7 686); `games_set2_total` 12 639 (12 634) / 7 032 (7 313);
`games_won_set1_for` 33 862 (33 679) / 9 728 (11 713); `handicap_games` -
wiersz pochodny, bez próbki. Wariant zmienia liczbę odrzuceń o kilka procent,
nie strukturę.

### Decyzja

Próg (z góry: oba okna i po rekalibracji) spełniony w **2 z 8 rodzin**
(`tiebreaks_total`, `games_set2_total`), **nie** w rodzinach, w które celował
audyt: `games_won_for` i `handicap_games` są **gorsze** (W1+W2 przedział nad
zerem), `sets_total` gorszy, `games_total` bez rozstrzygnięcia. Przy 8
rodzinach i jednej mierze 2 przejścia nie składają się na spójny sygnał (dwie
rodziny gemów w secie dzielą tę samą informację, a `games_set1_total` nie
przeszedł W1). **Nie wdrożono przełącznika** (`TENNIS_SERVE_NEIGHBOURS_FROM_UTC`
nie istnieje): wdrożenie nie jest tanie (oceny serwisu z `sofa_event_stats`
w historii ratingu w SHEET i w replayu `calibrate_from_cache.py`, potem refit
krzywych tenisa), a rodzina, dla której zysk jest największy
(`tiebreaks_total`), nie jest dziś w ogóle wyceniana z sąsiadów (p z próbki,
rating tylko jako `forecast_p` poza `RATED_MARKETS`). Wniosek: druga
współrzędna doboru sąsiadów w tej postaci (waga 1:1, D z ocen punktowych) nie
poprawia rozkładu gemów meczu; zgodna z 10-08 korelacja 0,11 nie przekłada
się na lepszy odczyt sąsiadów. Kandydat do osobnego testu (nowa rejestracja,
nowe dane): D wyłącznie dla `tiebreaks_total`.

### Zastrzeżenia

- σ_p, σ_D liczone na kandydatach komórki w danym dniu; jedna waga, bez
  strojenia - inna waga nie była sprawdzana (z rejestracji).
- W ITF D znane w ~1/3 meczów; populacja główna to głównie TOUR / CH i
  gracze ITF ze statystykami.
- Kandydaci 2D to tylko wiersze tabeli ze znanym D (mniejsza pula niż 1D).
- Rekalibracja: krzywa koszykowa (`measure_tennis_calibration.BucketCurve`,
  min. 400 wierszy w koszyku) per rodzina i kierunek, dopasowana na W1.
