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

## Ponowne dopasowanie na centrum z regułami na żywo (2026-10-13 wieczór)

Powód: beta w `config/sofa_game_state.json` (11:39Z) dopasowano na centrum
0,5 x rating + 0,5 x próbka poza `UNRATED_MARKETS` i samej próbce dla
`cards_points_for`. SHEET od 2026-10-13 18:10Z liczy centrum inaczej: B2
(`FOOTBALL_RATED_SCOPE`) wycenia ratingiem `RATED_SCOPE_MARKETS` (w tym
`cards_points_for`), a B14 (`FOOTBALL_RATING_WEIGHT`) daje każdemu rynkowi
własne W z `config/sofa_rating_weight.json` (`corners_for` 0,80,
`shots_for` 0,85, `fouls_for` 0,65; `cards_points_for` nie ma wpisu, więc
0,5). Beta opisywały więc inne centrum (zastrzeżenie 3 powyżej).

Kod: `measure_game_state.CentreRules` / `rules_as_of` / `live_centre(row,
rules)` - ta sama funkcja `rating_weight.blend`, którą woła SHEET; opcje
`--rated-scope`, `--rating-weight [PLIK]`, `--live-rules` (reguły z
`epochs` dla ostatniego dnia okna, na 00:00Z dnia następnego) w
`measure_game_state.py` i `fit_game_state.py`; `--compare-betas [PLIK]`
w pomiarze (stałe beta, domyślnie zainstalowane). Bez opcji centrum jest
dokładnie takie jak wcześniej (test `tests/sofa/test_game_state_centre_rules.py`).

Dane: kopia bazy `data/refit_2026-10-13/sofa_replay.db` (tylko odczyt,
`SOFA_DB_PATH`), historia z cache'u. Okno pomiaru 2025-08-01..2026-10-13,
trening od 2024-10-01; liczba stron jest identyczna jak w pomiarze z rana,
więc kopia nie zawiera meczów z 10-13 ze statystykami - faktycznie okno
kończy się 2026-10-12. Reguły: `--live-rules` = RATED_SCOPE + W per rynek.

Polecenia:

    SOFA_DB_PATH=data/refit_2026-10-13/sofa_replay.db PYTHONPATH=src:. \
      .venv/bin/python scripts/sofa/measure_game_state.py --to 2026-10-13 \
      --live-rules --compare-betas --json-out <plik>
    SOFA_DB_PATH=data/refit_2026-10-13/sofa_replay.db PYTHONPATH=src:. \
      .venv/bin/python scripts/sofa/fit_game_state.py --before 2026-10-14 \
      --live-rules --write --out data/refit_2026-10-14/sofa_game_state.json

### Nowe beta (wszystkie strony 2024-10-01..2026-10-13, centrum z regułami na żywo)

Zapisane WYŁĄCZNIE do `data/refit_2026-10-14/sofa_game_state.json`
(`fitted_from.centre_rules` w pliku); `config/` nietknięty.

| rynek | beta zainstalowane (stare centrum) | beta nowe (centrum na żywo) | strony |
|---|---|---|---|
| `corners_for` | +0,12897 | **+0,098622** | 144 894 |
| `shots_for` | +0,09738 | **+0,050643** | 108 302 |
| `cards_points_for` | -0,084481 | **-0,066437** | 119 552 |
| `fouls_for` | -0,010133 | **-0,009383** | 124 448 |

Wszystkie cztery beta są mniejsze co do modułu: przy większym W ratingu
(i ratingu dla kartek) centrum samo niesie już część różnicy sił, termin
stanu meczu ma mniej do poprawienia. Najmocniej spada `shots_for` (W 0,85).

### Poza próbą (walk-forward miesięczny, centrum na żywo)

Log-loss NB na stronę; różnica, 95% bootstrap po meczach (2000, ziarno 0).
(a) beta walk-forward vs brak terminu; (b) beta walk-forward vs
zainstalowane beta trzymane stałe na całym oknie. Uwaga do (b): zainstalowane
beta dopasowano na danych do 2026-10-12, więc w oknie są **w próbie**
(widzą przyszłość) - porównanie jest stronnicze na ich korzyść.

| rynek | strony / mecze | log-loss bez terminu / zainst. / nowe | (a) nowe - bez terminu [95%] | (b) nowe - zainstalowane [95%] | beta (zakres miesięcy) |
|---|---|---|---|---|---|
| `corners_for` | 123 130 / 61 565 | 2,33747 / 2,32954 / 2,32879 | **-0,00868 [-0,00955; -0,00783]** | **-0,00075 [-0,00091; -0,00059]** | +0,099..+0,116 |
| `shots_for` | 89 792 / 44 896 | 2,91393 / 2,91419 / 2,91025 | **-0,00368 [-0,00445; -0,00292]** | **-0,00393 [-0,00438; -0,00348]** | +0,050..+0,073 |
| `cards_points_for` | 96 012 / 48 006 | 1,77054 / 1,76807 / 1,76787 | **-0,00267 [-0,00309; -0,00227]** | **-0,00020 [-0,00028; -0,00012]** | -0,074..-0,067 |
| `fouls_for` | 104 410 / 52 205 | 2,74109 / 2,74090 / 2,74093 | -0,00016 [-0,00032; -0,000003] | +0,000031 [+0,000002; +0,000060] | -0,017..-0,009 |

Połowy okna, (a):

| rynek | 2025-08..2026-02 | 2026-03..2026-10 |
|---|---|---|
| `corners_for` | -0,01114 [-0,01246; -0,00988] | -0,00676 [-0,00791; -0,00554] |
| `shots_for` | -0,00605 [-0,00734; -0,00477] | -0,00193 [-0,00285; -0,00104] |
| `cards_points_for` | -0,00304 [-0,00367; -0,00249] | -0,00230 [-0,00290; -0,00172] |
| `fouls_for` | -0,00021 [-0,00048; +0,00003] | -0,00012 [-0,00032; +0,00007] |

Bias centrum - wynik według roli, bez terminu -> nowe (walk-forward):
`corners_for` faworyt -0,466 -> +0,154, outsider +0,424 -> +0,003;
`shots_for` -0,632 -> +0,295 / +0,543 -> -0,056; `cards_points_for`
+0,226 -> +0,081 / -0,079 -> +0,087; `fouls_for` +0,248 -> +0,112 /
+0,033 -> +0,173.

**Wnioski:**
- Termin nadal pomaga na centrum na żywo na wszystkich czterech rynkach
  (górna granica < 0; `fouls_for` ledwo, -0,000003, w obu połowach
  przedział obejmuje zero - jak rano).
- **Nowe beta biją zainstalowane poza próbą** na `corners_for`,
  `shots_for` i `cards_points_for` (przedziały wykluczają zero), mimo że
  zainstalowane widzą okno. Na `fouls_for` nowe są nieznacznie gorsze
  (+0,00003, przedział wyklucza zero) - to efekt wczesnych miesięcy
  walk-forward (beta -0,017), nie pełnego dopasowania: nowe pełne beta
  -0,00938 różni się od zainstalowanego -0,01013 o 0,0008, różnica
  praktycznie bez znaczenia.
- **Zainstalowane beta `shots_for` (+0,097) na centrum na żywo są gorsze
  niż brak terminu** (log-loss 2,91419 vs 2,91393, punktowo +0,00026;
  przedziału dla tej pary nie liczono): przy W = 0,85 stare beta
  przekorygowuje. To argument za podmianą pliku przed nocnym replayem.
- Instalacja nowych beta zmienia to, co drukuje - decyzja należy do sesji
  nadrzędnej / operatora (stały go audytu 2026-10-13 obejmuje ten refit,
  jeśli zostanie zainstalowany zgodnie z regułą 4 CLAUDE.md).
