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

## Wynik

(wpisywany po pomiarze)
