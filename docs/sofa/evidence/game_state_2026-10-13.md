# B1: rola faworyt / outsider (stan meczu) w centrum rynków stron (audyt 2026-10-13)

Przełącznik: `epochs.GAME_STATE_FROM_UTC` (`game_state_v1`), domyślnie `None`.
Współczynniki: `config/sofa_game_state.json` (pisze `scripts/sofa/fit_game_state.py`,
domyślnie dry-run). Pomiar: `scripts/sofa/measure_game_state.py` (tylko odczyt),
wspólna rekonstrukcja centrum: `bet.sofa.centre_replay`.

## Diagnoza (sprawdzona w kodzie 2026-10-13)

- `run_sheet.py:1197-1223`: centrum strony = 0,5 x rating (Maher: stawka ligi x
  atak x obrona rywala, `FootballForecast.centre`, `football_rating.py:975`)
  + 0,5 x próbka skurczona do priora; `cards_points_for` jest w
  `UNRATED_MARKETS` (`football_rating.py:126-136`), więc tam centrum to sama próbka.
- Ani rating, ani próbka nie mają terminu „różnica sił -> styl gry”: faworyt,
  który prowadzi, oddaje piłkę i rożne; outsider goni wynik (Buraimo, Forrest,
  Simmons 2010 - kartki; Wheatcroft 2020 - strzały i rożne w ratingu).
  Audyt zmierzył kierunek (Część 1, `corners_for` 1., V1-13): outsider +0,53,
  faworyt -0,60 w blendzie - bez przedziałów.

## Rejestracja (zapisana 2026-10-13 PRZED uruchomieniem pomiaru)

- **Hipoteza:** centrum_strony x exp(beta_m x s), gdzie s = oczekiwane gole
  strony minus oczekiwane gole rywala z ratingu goli tej samej książki
  (`FootballForecast.centre("goals_for", side)`, ta sama reguła LINKED /
  siła ligi, as-of meczu), dla rynku m w {`corners_for`, `shots_for`,
  `cards_points_for`, `fouls_for`}; rywal dostaje -s (ten sam beta).
  Kierunek z audytu (bias centrum - wynik, `corners_for`: faworyt -0,30 w
  ratingu, -0,60 w blendzie; outsider +0,29 / +0,53) daje beta > 0 dla
  rożnych; dla kartek i fauli literatura (outsider fauluje więcej) daje
  beta < 0. Znak nie jest progiem i nie jest narzucany w dopasowaniu.
- **Centrum bazowe (A, przybliżenie SHEET-u, one step ahead):** próbka = 10
  ostatnich wartości strony w historii (bez sparingów), skurczona
  w = n / (n + K) do priora; K jak w druku (`PER_MARKET_K`: `cards_points_for`
  25, `shots_for` 8, reszta 15); prior = średnia na stronę rozgrywki meczu z
  książki as-of (`league_rates`, przy cienkiej lidze stawka globalna). Dla
  rynków z ratingiem: 0,5 x rating + 0,5 x próbka (gdy strona ma rating),
  dla `cards_points_for` sama próbka - jak w SHEET. To nie jest SHEET bajt w
  bajt (prior SHEET-u to dopasowany baseline z `config`, nie bieżąca średnia
  książki) - te same A w obu wariantach.
- **Populacja:** historia z cache'u (`football_rating.load_history`), mecze
  2025-08-01..2026-10-12 (UTC), strony z >= 5 meczami w ratingu goli obu
  drużyn (żeby s istniało) i >= 5 wartościami metryki w ostatnich 10.
- **Poza próbą (walk-forward):** beta_m dopasowane metodą pseudo-największej
  wiarygodności Poissona (log-link, offset log A) na stronach z meczów
  ściśle przed pierwszym dniem ocenianego miesiąca (od 2024-10, początek
  statystyk w cache'u); ocena miesiąc po miesiącu.
- **Metryka główna:** log-loss NB obserwowanej liczby przy średniej =
  centrum i alfie z zainstalowanej tabeli dyspersji
  (`config/sofa_count_dispersion.json`, rynek x rozgrywka - ta, którą SHEET
  czyta od 10-09); różnica nowa - stara na stronę.
  Alfa dopasowana na historii obejmującej okno - ta sama w obu wariantach.
- **Przedział:** 95% bootstrap po meczach (2000 losowań, ziarno 0), suma po
  stronach meczu.
- **Próg (O5):** per rynek górna granica 95% różnicy log-loss < 0. Rynek, który
  go nie spełnia, nie wchodzi do tabeli przełącznika.
- **Wtórne (raportowane, nie progowe):** MSE centrum; bias (centrum - wynik)
  w tercylach roli (faworyt s > +0,5, wyrównane, outsider s < -0,5) przed i po;
  wynik w podoknach.
- **Zastrzeżenie zapisane z góry:** replay historii
  (`calibrate_from_cache.py`) nie odtwarza ratingu piłki (audyt A6), więc to
  pomiar jakości centrum, nie log-lossu linii Superbetu ani krzywej pewności.
  Krzywe zainstalowane dopasowano bez tego terminu; przełącznik zmienia p,
  które czytają.

## Wynik

(wpisywany po pomiarze)
