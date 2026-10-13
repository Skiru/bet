# B14: waga ratingu piłki per rynek (`W_FOOTBALL_RATING`, audyt 2026-10-13)

Przełącznik: `epochs.FOOTBALL_RATING_WEIGHT_FROM_UTC` (`rating_weight_v1`),
domyślnie `None`. Wagi: `config/sofa_rating_weight.json` (pisze
`scripts/sofa/fit_rating_weight.py`, domyślnie dry-run). Moduł:
`bet.sofa.rating_weight`. Pomiar: `scripts/sofa/measure_rating_weight.py`
(tylko odczyt), rekonstrukcja centrum: `bet.sofa.centre_replay`.

## Diagnoza (sprawdzona w kodzie 2026-10-13)

- `football_rating.py:125` `W_FOOTBALL_RATING = 0.5` - jedna waga dla
  wszystkich rynków z ratingiem; `run_sheet.py:1212-1216`:
  centrum = W x rating + (1 - W) x próbka.
- W wybrano Brierem na 5 rozliczonych dniach 2026-09-18..22 (1 360 meczów),
  siatka {0; 0,25; 0,5; 0,75; 1} wspólna dla wszystkich rynków
  (komentarz `football_rating.py:113-124`). Audyt (Część 1, `goals_for`):
  rating sam lepszy w MSE (2,412 vs blend 2,485).

## Rejestracja (zapisana 2026-10-13 PRZED uruchomieniem pomiaru)

- **Hipoteza:** W per rynek, dopasowane na historii, daje lepsze centrum niż
  W = 0,5 dla wszystkich.
- **Rynki:** wszystkie rynki z ratingiem dziś: `_for` i `_total` metryk
  `football_rating.BASE_METRICS` bez `UNRATED_MARKETS` (rynki B2
  `RATED_SCOPE_MARKETS` - raportowane osobno, nie progowe, bo dziś nie mają
  ratingu).
- **Centrum:** W x rating + (1 - W) x próbka w rekonstrukcji `centre_replay`
  (próbka 10 ostatnich wartości skurczona do stawki ligi z książki, K rynku z
  `PER_MARKET_K`); wiersze bez ratingu pominięte (W ich nie dotyczy).
- **Populacja:** historia z cache'u, mecze 2025-08-01..2026-10-12.
- **Poza próbą (walk-forward):** W z siatki 0,00..1,00 co 0,05 minimalizujące
  średni log-loss NB na wierszach ściśle przed pierwszym dniem ocenianego
  miesiąca (trening od 2024-10-01).
- **Metryka główna:** log-loss NB obserwowanej liczby przy średniej = centrum,
  alfa z `config/sofa_count_dispersion.json` (rynek x rozgrywka; dla
  `shots_total`, który SHEET wycenia normalnym, też NB z tą alfą - ta sama w
  obu wariantach); różnica (W walk-forward) - (W = 0,5) na wiersz.
- **Przedział:** 95% bootstrap po meczach (2000, ziarno 0).
- **Próg (O5):** per rynek górna granica 95% < 0. Tylko takie rynki wchodzą do
  pliku; reszta zostaje przy 0,5.
- **Wtórne:** W per miesiąc, MSE centrum, połowy okna.
- **Zastrzeżenia z góry:** pomiar centrum, nie linii Superbetu ani krzywej
  (replay krzywych nie odtwarza ratingu, A6). Krzywe zainstalowane opisują
  estymator z W = 0,5: po włączeniu potrzebny refit z W per rynek w replayu.
  C1 (faza sezonu) dopasowano na centrum z W = 0,5 - przy obu włączonych
  współczynniki fazy trzeba dopasować ponownie.

## Wynik (2026-10-13, `scripts/sofa/measure_rating_weight.py`, okno 2025-08-01..2026-10-12)

Walk-forward miesięczny (W z siatki co 0,05, wybrane na wierszach przed 1. dniem
miesiąca, trening od 2024-10-01). Log-loss NB na wiersz; różnica
(W walk-forward) - (W = 0,5), 95% bootstrap po meczach (2000, ziarno 0).
Tylko wiersze z ratingiem.

Rynki z ratingiem dziś (progowe):

| rynek | wiersze / mecze | różnica [95%] | log-loss 0,5 -> W | MSE 0,5 -> W | W (zakres miesięcy; ostatni) | próg |
|---|---|---|---|---|---|---|
| `goals_for` | 759 468 / 379 734 | **-0,01054 [-0,01087; -0,01019]** | 1,62808 -> 1,61754 | 2,374 -> 2,294 | 0,95-1,00; 0,95 | tak |
| `goals_total` | 379 734 / 379 734 | -0,00000 [-0,00004; +0,00003] | 2,02877 -> 2,02877 | 4,065 -> 4,066 | 0,45 | nie |
| `goals_1h_for` | 521 230 / 260 615 | **-0,00203 [-0,00222; -0,00185]** | 1,09651 -> 1,09448 | 0,810 -> 0,805 | 0,75-0,80; 0,80 | tak |
| `goals_1h_total` | 260 615 / 260 615 | **-0,00043 [-0,00056; -0,00031]** | 1,49919 -> 1,49876 | 1,500 -> 1,499 | 0,30 | tak |
| `goals_2h_for` | 521 252 / 260 626 | **-0,00303 [-0,00324; -0,00282]** | 1,22226 -> 1,21923 | 1,015 -> 1,004 | 0,80-0,85; 0,80 | tak |
| `goals_2h_total` | 260 626 / 260 626 | **-0,00060 [-0,00074; -0,00047]** | 1,62234 -> 1,62174 | 1,827 -> 1,827 | 0,25-0,30; 0,30 | tak |
| `corners_for` | 123 072 / 61 536 | **-0,00369 [-0,00423; -0,00320]** | 2,34115 -> 2,33746 | 7,222 -> 7,169 | 0,80-0,85; 0,80 | tak |
| `cards_points_total` | 47 986 / 47 986 | +0,00012 [-0,00004; +0,00029] | 2,21966 -> 2,21978 | 5,621 -> 5,622 | 0,20-0,45; 0,45 | nie |
| `fouls_for` | 104 364 / 52 182 | **-0,00120 [-0,00149; -0,00091]** | 2,74231 -> 2,74111 | 14,879 -> 14,845 | 0,60-0,65; 0,65 | tak |
| `fouls_total` | 52 182 / 52 182 | +0,00006 [-0,00022; +0,00032] | 3,14005 -> 3,14011 | 32,711 -> 32,718 | 0,35-0,45; 0,45 | nie |
| `fouls_1h_for` | 33 318 / 16 659 | **-0,00089 [-0,00150; -0,00028]** | 2,25711 -> 2,25622 | 5,535 -> 5,525 | 0,00-0,75; 0,70 | tak |
| `fouls_1h_total` | 16 659 / 16 659 | +0,00015 [-0,00025; +0,00055] | 2,62654 -> 2,62670 | 11,402 -> 11,407 | 0,00-0,55; 0,55 | nie |
| `offsides_for` | 110 136 / 55 068 | **-0,00546 [-0,00616; -0,00474]** | 1,69430 -> 1,68885 | 2,320 -> 2,289 | 0,90-1,00; 0,90 | tak |
| `shots_for` | 89 770 / 44 885 | **-0,01321 [-0,01425; -0,01218]** | 2,92718 -> 2,91396 | 22,003 -> 21,322 | 0,85-0,90; 0,85 | tak |
| `shots_total` | 44 885 / 44 885 | -0,00007 [-0,00028; +0,00014] | 3,14723 -> 3,14716 | 32,339 -> 32,337 | 0,40-0,45; 0,45 | nie |
| `shots_1h_for` | 43 910 / 21 955 | **-0,00912 [-0,01040; -0,00787]** | 2,45115 -> 2,44203 | 8,640 -> 8,462 | 0,85-0,90; 0,90 | tak |
| `shots_1h_total` | 21 955 / 21 955 | +0,00003 [-0,00026; +0,00032] | 2,70704 -> 2,70707 | 13,508 -> 13,510 | 0,30-0,45; 0,45 | nie |
| `shots_on_target_for` | 102 902 / 51 451 | **-0,00671 [-0,00738; -0,00604]** | 2,22558 -> 2,21887 | 5,738 -> 5,652 | 0,85 | tak |
| `shots_on_target_total` | 51 451 / 51 451 | -0,00025 [-0,00052; +0,00000] | 2,56722 -> 2,56697 | 10,662 -> 10,656 | 0,30-0,40; 0,35 | nie |
| `shots_on_target_1h_for` | 43 102 / 21 551 | **-0,00221 [-0,00276; -0,00164]** | 1,74060 -> 1,73839 | 2,301 -> 2,290 | 0,65-0,75; 0,75 | tak |
| `shots_on_target_1h_total` | 21 551 / 21 551 | -0,00028 [-0,00092; +0,00037] | 2,11118 -> 2,11090 | 4,247 -> 4,244 | 0,00-0,30; 0,30 | nie |

Rynki B2 (`RATED_SCOPE_MARKETS`, dziś bez ratingu; nie progowe, za
`FOOTBALL_RATED_SCOPE_FROM_UTC`): `corners_1h_for` -0,00263 [-0,00331; -0,00198]
(W 0,70-0,80), `corners_2h_for` -0,00099 [-0,00141; -0,00057] (0,65-0,70),
`cards_points_for` -0,00047 [-0,00062; -0,00031] (0,65-0,70), `offsides_total`
+0,00007 [+0,00001; +0,00013] (0,40-0,55; gorzej).

Połowy okna: wszystkie rynki z progiem spełnionym mają ujemny punkt w obu
połowach; `fouls_1h_for` w pierwszej połowie -0,00005 [-0,00113; +0,00103]
(W skakało 0,00 -> 0,75 przy 33 tys. wierszy - najsłabszy z przyjętych).

**Próg zarejestrowany (górna granica < 0 per rynek): spełniony dla 13 z 21
rynków z ratingiem** - wszystkie rynki stron (`_for`): `goals_for`,
`goals_1h_for`, `goals_2h_for`, `corners_for`, `fouls_for`, `fouls_1h_for`,
`offsides_for`, `shots_for`, `shots_1h_for`, `shots_on_target_for`,
`shots_on_target_1h_for`, oraz `goals_1h_total`, `goals_2h_total`. Nie
spełniony: `goals_total`, `cards_points_total`, `fouls_total`,
`fouls_1h_total`, `shots_total`, `shots_1h_total`, `shots_on_target_total`,
`shots_on_target_1h_total` (zostają przy 0,5).

**Co się rusza:** rynki stron idą w stronę ratingu (W 0,65-0,95; `goals_for`
0,95, `shots_for` 0,85, `offsides_for` 0,90 - największe zyski: `shots_for`
-0,0132, `goals_for` -0,0105, `shots_1h_for` -0,0091 na stronę); sumy połów
goli w stronę próbki (W 0,30). Sumy pełnego meczu zostają przy ~0,45 bez
zysku.

Wagi w pliku (`fit_rating_weight.py --before 2026-10-13 --write`, wszystkie
wiersze 2024-10-01..2026-10-12, `config/sofa_rating_weight.json`):
`goals_for` 0,95, `goals_1h_for` 0,80, `goals_1h_total` 0,30, `goals_2h_for`
0,80, `goals_2h_total` 0,30, `corners_for` 0,80, `fouls_for` 0,65,
`fouls_1h_for` 0,70, `offsides_for` 0,90, `shots_for` 0,85, `shots_1h_for`
0,90, `shots_on_target_for` 0,85, `shots_on_target_1h_for` 0,75. Pozostałe
rynki - brak w pliku, czyli `W_FOOTBALL_RATING` 0,5.

**Przełącznik `FOOTBALL_RATING_WEIGHT_FROM_UTC` zostaje `None`** (polecenie
sesji nadrzędnej: włącza ją razem z refitem piłki).

Zastrzeżenia:
1. Próbka w rekonstrukcji to 10 ostatnich wartości z historii (bez reguły
   „te same rozgrywki” SAMPLES, prior z książki), więc W optymalne dla
   rekonstrukcji może przeceniać rating wobec prawdziwej próbki SHEET-u. To
   pomiar centrum, nie linii Superbetu ani krzywej.
2. `goals_for` 0,95 przy `goals_total` 0,5: centrum sumy przestaje być sumą
   centrów stron (już dziś nie jest: próbka sumy to sumy meczów obu drużyn).
   Rynki pochodne czytające brzegi (`DERIVED_MARGINAL_CENTRES`) dostaną nowe
   centra stron.
3. C1 (faza) dopasowano na centrum z W = 0,5; przy obu włączonych
   współczynniki fazy trzeba dopasować ponownie (i odwrotnie).
4. Krzywe pewności opisują estymator z W = 0,5 - przełącznik idzie z refitem,
   którego replay woła `rating_weight.blend`.
