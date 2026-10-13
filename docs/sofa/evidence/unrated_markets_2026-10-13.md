# B2: rynki bez ratingu (`UNRATED_MARKETS`) - rating z siłą ligi i gospodarz jako mnożnik ligi (audyt 2026-10-13)

Przełączniki: `epochs.FOOTBALL_RATED_SCOPE_FROM_UTC` (`rated_scope_v1`) i
`epochs.FOOTBALL_VENUE_PRIOR_FROM_UTC` (`venue_prior_v1`), domyślnie `None`.
Pomiar: `scripts/sofa/measure_unrated_markets.py` (tylko odczyt), wspólna
rekonstrukcja centrum: `bet.sofa.centre_replay`.

## Diagnoza (sprawdzona w kodzie 2026-10-13)

- `football_rating.py:126-136` `UNRATED_MARKETS` = `corners_total`,
  `corners_1h_total`, `corners_1h_for`, `corners_2h_total`, `corners_2h_for`,
  `cards_points_for`, `offsides_total`. `FootballForecast.centre`
  (`football_rating.py:975-979`) zwraca dla nich `None`, więc SHEET
  (`run_sheet.py:1197-1223`) zostawia centrum z samej próbki: bez ratingu,
  bez korekty siły ligi i rywali.
- Wykluczenia wybrano Brierem na 5 dniach 2026-09-18..22, na tych samych
  dniach, na których mierzono W (komentarz `football_rating.py:113-124`).
- Gospodarz: `Observation.venue` jest zapisywane (`samples.py:927`), SHEET go
  nie czyta (grep `venue` w `run_sheet.py`: brak). Rynki bez ratingu nie mają
  przewagi gospodarza wcale.

## Co jest nowe wobec „Measured and declined” (O4)

Nie mierzę per-market K (K=40 dla `corners_total` zmierzone 10-08 bez
rozstrzygnięcia, `k_under_dispersion_2026-10-08.md:33`). Nie dzielę próbki
na dom / wyjazd („venue is a prior, not a split”). Osie nowe:
1. rating ataku x obrony z siłą ligi (ten sam, który już wycenia pozostałe
   rynki) w centrum rynków `UNRATED_MARKETS`, mierzony na **pełnej historii**
   one step ahead (dotąd: 5 dni, Brier, wybór w próbie);
2. gospodarz jako **mnożnik ligi na centrum** (stawka dom / wyjazd rozgrywki
   meczu as-of względem mieszanki dom / wyjazd próbki), bez podziału próbki.

## Rejestracja (zapisana 2026-10-13 PRZED uruchomieniem pomiaru)

- **Populacja:** historia z cache'u, mecze 2025-08-01..2026-10-12 (UTC), bez
  sparingów, książka ratingu one step ahead (ta sama reguła LINKED co druk:
  `link_shared_league` na dziś = włączone).
- **Centrum A (dziś, przybliżenie SHEET-u):** `_for` - 10 ostatnich wartości
  strony skurczone w = n / (n + K) do średniej na stronę rozgrywki meczu
  (książka as-of, przy cienkiej lidze stawka globalna), K jak w druku
  (`cards_points_for` 25, reszta 15); `_total` - suma meczu z 10 ostatnich
  meczów każdej strony (mecz wspólny raz, jak `deduplicate_observations`),
  K = 15 do sumy stawek dom + wyjazd rozgrywki. Wymagane >= 5 wartości
  na stronę.
- **Wariant R (rating):** 0,5 x rating + 0,5 x A, rating = `RatingBook.expected`
  z linkiem i siłą ligi jak w `FootballForecast.centre` (dla `_total` suma
  stron); tylko gdy obie drużyny mają >= 5 meczów w ratingu metryki (inaczej
  wiersz jest poza porównaniem R, jak w druku zostałby z A).
- **Wariant V (gospodarz, tylko `_for`):** A x r_dzis / średnia_k r_{venue_k},
  r_home / r_away = stawki dom / wyjazd rozgrywki meczu as-of, venue_k =
  dom / wyjazd każdej obserwacji próbki. Dla `_total` mnożnik ligi jest
  tożsamościowo 1 (dom + wyjazd to ta sama suma) - nie mierzone.
- **Metryka główna:** log-loss NB obserwowanej liczby przy średniej = centrum i
  alfie z `config/sofa_count_dispersion.json` (rynek x rozgrywka); różnica
  wariant - A na wiersz (strona albo mecz). Alfa ta sama w obu wariantach.
- **Poza próbą:** brak współczynników dopasowywanych w tym teście; rating
  aktualizowany chronologicznie, odczyt przed meczem. Stałe ratingu
  (`ALPHA_BY_METRIC`) wybrano MSE na 2026-06-01..09-16 - dlatego wynik
  raportowany też w podoknach 2025-08-01..2026-05-31 i 2026-09-17..10-12
  (poza oknem wyboru stałych).
- **Przedział:** 95% bootstrap po meczach (2000 losowań, ziarno 0).
- **Próg (O5):** per rynek górna granica 95% różnicy < 0 w całym oknie **i**
  w obu podoknach poza oknem wyboru stałych ma ten sam znak punktu. Rynek,
  który spełnia, trafia do zakresu przełącznika.
- **Wtórne:** MSE centrum; sam rating (W = 1) dla porównania z MSE z Części 1.
- **Zastrzeżenie:** replay historii nie odtwarza ratingu piłki (A6) - pomiar
  jakości centrum, nie linii Superbetu ani krzywej pewności.

## Wynik (2026-10-13, `scripts/sofa/measure_unrated_markets.py`, okno 2025-08-01..2026-10-12)

Log-loss NB na wiersz, wariant - A, 95% bootstrap po meczach (2000, ziarno 0).
„pre” = 2025-08-01..2026-05-31, „post” = 2026-09-17..2026-10-12 (oba poza
oknem wyboru `ALPHA_BY_METRIC`), „choice” = 2026-06-01..09-16.

### R: 0,5 x rating (z siłą ligi) + 0,5 x próbka

| rynek | wiersze / mecze | całe okno [95%] | pre | choice | post | MSE A -> R | próg |
|---|---|---|---|---|---|---|---|
| `cards_points_for` | 95 972 / 47 986 | **-0,00503 [-0,00547; -0,00459]** | -0,00499 | -0,00524 | -0,00505 | 2,431 -> 2,405 | **tak** |
| `corners_1h_for` | 43 970 / 21 985 | **-0,01632 [-0,01754; -0,01512]** | -0,01594 | -0,01740 | -0,01723 | 3,099 -> 2,996 | **tak** |
| `corners_2h_for` | 43 970 / 21 985 | **-0,01099 [-0,01211; -0,00989]** | -0,01002 | -0,01389 | -0,01278 | 3,806 -> 3,723 | **tak** |
| `offsides_total` | 55 068 / 55 068 | **-0,00503 [-0,00582; -0,00420]** | -0,00482 | -0,00521 | -0,00665 | 4,619 -> 4,574 | **tak** |
| `corners_total` | 61 536 / 61 536 | +0,00092 [+0,00034; +0,00153] | +0,00094 | +0,00056 | +0,00179 | 11,485 -> 11,505 | nie (gorzej) |
| `corners_1h_total` | 21 985 / 21 985 | +0,00014 [-0,00071; +0,00101] | +0,00026 | -0,00061 | +0,00140 | 5,025 -> 5,026 | nie |
| `corners_2h_total` | 21 985 / 21 985 | +0,00078 [-0,00005; +0,00162] | +0,00087 | +0,00104 | -0,00134 | 5,803 -> 5,812 | nie |

Przedziały podokien (R, rynki spełniające próg): `cards_points_for` post
[-0,00705; -0,00315], `corners_1h_for` post [-0,02289; -0,01171],
`corners_2h_for` post [-0,01776; -0,00757], `offsides_total` post
[-0,00995; -0,00327]; pre - wszystkie z górną granicą < 0.

Sam rating (W = 1, wtórne): `corners_total` +0,00754 [+0,00638; +0,00877]
(MSE 11,485 -> 11,657 - ten sam kierunek co MSE Części 1, 11,76 vs 11,56),
`corners_1h_total` +0,00429, `corners_2h_total` +0,00542 (gorzej);
`offsides_total` -0,00057 [-0,00219; +0,00111]; `cards_points_for`
-0,00461, `corners_1h_for` -0,01774, `corners_2h_for` -0,00978 (lepiej).

### V: gospodarz jako mnożnik ligi (tylko `_for`)

| rynek | wiersze / mecze | całe okno [95%] | pre | choice | post | MSE A -> V | próg |
|---|---|---|---|---|---|---|---|
| `corners_1h_for` | 43 992 / 21 996 | **-0,00639 [-0,00804; -0,00466]** | -0,00637 | -0,00669 | -0,00549 | 3,099 -> 3,060 | **tak** |
| `corners_2h_for` | 43 992 / 21 996 | **-0,00308 [-0,00463; -0,00157]** | -0,00252 | -0,00491 | -0,00345 | 3,806 -> 3,785 | **tak** |
| `cards_points_for` | 96 012 / 48 006 | -0,00119 [-0,00182; -0,00056] | -0,00101 | -0,00273 | +0,00009 | 2,430 -> 2,424 | nie (post ma znak +) |

### Wniosek

- **Rating: próg spełniony dla `cards_points_for`, `corners_1h_for`,
  `corners_2h_for`, `offsides_total`** -
  `football_rating.RATED_SCOPE_MARKETS`. Sumy rożnych (`corners_total`,
  połowy) - rating nie pomaga, `corners_total` szkodzi: wykluczenie z 09-22
  potwierdzone na pełnej historii dla nich, obalone dla pozostałych czterech.
- **Gospodarz: próg spełniony dla `corners_1h_for`, `corners_2h_for`** -
  `football_rating.VENUE_PRIOR_MARKETS`. Działa tylko na wierszu bez centrum
  ratingu (przy włączonym `FOOTBALL_RATED_SCOPE` - drużyna bez 5 meczów w
  ratingu albo bez stawki ligi); rating ma własny stosunek dom / wyjazd.
- **Przełączniki `FOOTBALL_RATED_SCOPE_FROM_UTC` i
  `FOOTBALL_VENUE_PRIOR_FROM_UTC` zostają `None`** (polecenie sesji
  nadrzędnej: nie włączać).

Zastrzeżenia:
1. Pomiar centrum, nie linii Superbetu ani krzywej pewności (A6: replay nie
   odtwarza ratingu). Krzywe `market:corners_1h_for|DIR` itd. dopasowano na
   centrum bez ratingu; skutek dla druku niezmierzony.
2. Centrum A to przybliżenie SHEET-u (prior z książki as-of, próbka z
   historii); alfa dyspersji dopasowana na historii obejmującej okno - ta sama
   w obu wariantach. K zgodne z drukiem (`cards_points_for` 25, reszta 15).
3. Stałe ratingu (`ALPHA_BY_METRIC`, siła ligi) wybrano MSE na
   2026-06-01..09-16; dlatego próg wymaga znaku w pre i post - spełnione.
4. B1 i B2 nakładają się na `cards_points_for`: beta B1 dopasowano na
   centrum z samej próbki; przy obu przełącznikach włączonych beta trzeba
   dopasować ponownie.
