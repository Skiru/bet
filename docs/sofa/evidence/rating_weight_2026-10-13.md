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

## Wynik

(uzupełniane po pomiarze)
