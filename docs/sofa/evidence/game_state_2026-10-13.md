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

## Wynik (2026-10-13, `scripts/sofa/measure_game_state.py`, okno 2025-08-01..2026-10-12)

Walk-forward miesięczny (beta z meczów przed 1. dniem miesiąca, trening od
2024-10-01). Log-loss NB na stronę; różnica nowa - stara, 95% bootstrap po
meczach (2000, ziarno 0).

| rynek | strony / mecze | log-loss stara -> nowa | różnica [95%] | MSE stara -> nowa | beta (zakres miesięcy) |
|---|---|---|---|---|---|
| `corners_for` | 123 130 / 61 565 | 2,3412 -> 2,3263 | **-0,01490 [-0,01600; -0,01383]** | 7,223 -> 7,011 | +0,129..+0,145 |
| `shots_for` | 89 792 / 44 896 | 2,9272 -> 2,9122 | **-0,01504 [-0,01638; -0,01374]** | 22,005 -> 21,204 | +0,097..+0,117 |
| `cards_points_for` | 96 012 / 48 006 | 1,7756 -> 1,7713 | **-0,00425 [-0,00479; -0,00372]** | 2,430 -> 2,412 | -0,097..-0,085 |
| `fouls_for` | 104 410 / 52 205 | 2,7423 -> 2,7421 | **-0,00020 [-0,00037; -0,00003]** | 14,879 -> 14,874 | -0,018..-0,010 |

Połowy okna (ta sama metryka):

| rynek | 2025-08..2026-02 | 2026-03..2026-10 |
|---|---|---|
| `corners_for` | -0,01710 [-0,01875; -0,01550] | -0,01318 [-0,01466; -0,01163] |
| `shots_for` | -0,01776 [-0,01989; -0,01569] | -0,01304 [-0,01472; -0,01142] |
| `cards_points_for` | -0,00472 [-0,00552; -0,00401] | -0,00379 [-0,00455; -0,00304] |
| `fouls_for` | -0,00025 [-0,00054; +0,00001] | -0,00015 [-0,00036; +0,00006] |

Bias centrum - wynik według roli (faworyt s > +0,5, outsider s < -0,5),
stara -> nowa:

| rynek | faworyt | wyrównane | outsider |
|---|---|---|---|
| `corners_for` | -0,628 -> +0,141 (29 342) | +0,012 -> +0,020 (64 446) | +0,569 -> +0,027 (29 342) |
| `shots_for` | -1,292 -> +0,276 (20 945) | -0,012 -> +0,005 (47 902) | +1,075 -> +0,003 (20 945) |
| `cards_points_for` | +0,266 -> +0,080 (23 398) | -0,036 -> -0,035 (49 216) | -0,125 -> +0,086 (23 398) |
| `fouls_for` | +0,258 -> +0,112 (24 512) | -0,070 -> -0,070 (55 386) | +0,021 -> +0,170 (24 512) |

**Próg zarejestrowany (górna granica < 0 per rynek): spełniony dla wszystkich
czterech rynków.** `fouls_for` spełnia go ledwo (górna -0,00003), w obu
połowach przedział obejmuje zero, a jedno beta poprawia faworyta kosztem
outsidera (bias +0,021 -> +0,170) - efekt dla fauli nie jest log-liniowy w s.

Kierunek: faworyt ma więcej rożnych i strzałów, niż mówi centrum (beta > 0,
zgodnie z biasem z audytu), mniej kartek i fauli (beta < 0, zgodnie z
Buraimo i in. 2010).

Beta do pliku (`fit_game_state.py --before 2026-10-13 --write`, wszystkie
strony 2024-10-01..2026-10-12): `corners_for` +0,12897 (144 894 strony),
`shots_for` +0,09738 (108 302), `cards_points_for` -0,084481 (119 552),
`fouls_for` -0,010133 (124 448) - `config/sofa_game_state.json`.

**Przełącznik `GAME_STATE_FROM_UTC` zostaje `None`** (polecenie sesji
nadrzędnej: nie włączać; decyzja według O5 należy do niej / operatora).

Zastrzeżenia:
1. To pomiar centrum, nie linii Superbetu ani krzywej pewności: replay
   (`calibrate_from_cache.py`) nie odtwarza ratingu piłki (A6). Krzywe
   `market:<rynek>|DIR` i offsety line evidence dopasowano na p bez tego
   terminu; skutek dla druku (liczba nóg, kalibracja) niezmierzony.
2. Część zysku to korekta próbki, nie ratingu: próbka outsidera była
   zarobiona przeciw słabszym rywalom niż dzisiejszy faworyt (audyt: bias
   próbki ±0,8, ratingu ±0,3). Termin poprawia oba naraz; B15 (korekta
   próbki o rywala) by się z nim nakładała - po B15 beta trzeba dopasować
   ponownie.
3. Beta `cards_points_for` dopasowano na centrum z samej próbki
   (`UNRATED_MARKETS`). Gdy włączony jest też B2 (`FOOTBALL_RATED_SCOPE`,
   który obejmuje `cards_points_for`), beta trzeba dopasować ponownie na
   centrum z ratingiem.
4. Centrum bazowe to przybliżenie SHEET-u (prior z książki, nie z
   `config`; próbka z historii, nie z SAMPLES). Alfa dyspersji dopasowana na
   historii obejmującej okno - ta sama w obu wariantach.
5. `MAX_SUPREMACY` = 3,0 wybrane, nie dopasowane (`UNFITTED_CONSTANTS` na
   wierszu).
