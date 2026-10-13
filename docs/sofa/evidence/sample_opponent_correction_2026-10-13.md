# B15 (z A5): próbka skorygowana o rywala i siłę ligi (audyt 2026-10-13)

Pozycje: B15 i A5 z `docs/sofa/history/AUDYT_RYNKOW_KONTEKST_2026-10-13.md`
(Część 6 W1, W4, W7). Wymaga B13 (`Observation.opponent_id`, `against`).
Przełącznik: `epochs.SAMPLE_OPPONENT_CORRECTION_FROM_UTC`
(`sample_opponent_v1`). Skrypt: `scripts/sofa/measure_sample_opponent_correction.py`
(tylko odczyt).

## Rejestracja (zapisana 2026-10-13 przed uruchomieniem pomiaru)

### Diagnoza (sprawdzona w kodzie)

- `scripts/sofa/run_sheet.py` `process_fixture`: próbka strony (`obs`) idzie
  wprost do `values = [o.value for o in obs]` (średnia, wariancja, trafienia);
  dla sumy przez `deduplicate_observations([side_a, side_b, h2h])`. Nic nie
  czyta rywala obserwacji ani siły ligi, w której ją zarobiono. Rating
  (`football_rating.RatingBook`, `FootballForecast.centre`) koryguje tylko
  swoją połowę środka (`W_FOOTBALL_RATING` 0,5), a na `UNRATED_MARKETS`
  (`corners_total`, `corners_1h_*`, `corners_2h_*`, `cards_points_for`,
  `offsides_total`) środek to cała surowa próbka.
- `scripts/sofa/run_confidence.py` `side_observations` / `sample_values`
  czyta surowe wartości z `03_samples.json`; z nich `line_is_beyond_sample`,
  `mode_loses` (`confidence.py` ~950-982) i `model_above_own_sample`
  (`confidence.py` ~623-655, piłka, bez propsów). Każda korekta środka, która
  odsunie p od surowej próbki o > 0,15 w górę, zostaje zdjęta jako
  `MODEL_ABOVE_OWN_SAMPLE` (A5 / W7).

### Transformacja (Maher 1982; Wheatcroft 2020; jak `RatingBook.expected`)

Obserwacja strony A z meczu k przeciw rywalowi O_k, metryka bazowa m
(`football_rating.base_metric` rynku), księga ratingu as-of budowy
(ta sama, którą SHEET ma na żywo - stan sprzed meczu prognozowanego, nic z
przyszłości):

- `c_k` = `CROSS_RATIO_POWER` (0,6), gdy para (A, O_k) nie jest `LINKED`,
  inaczej 1 - jak w `RatingBook.expected(cross=...)`;
- `lf(X, Y)` = log-luka siły domen z `RatingBook.link(X, Y, m)` (0 dla
  `LINKED` i `UNLINKED`), czynnik na stawkę X; `g_k = lf(A, B) - lf(A, O_k)`,
  B = dzisiejszy rywal (k = 1, skala ratingu - żadnej nowej stałej);
- wartość „za” (`*_for`): `x' = x / def(O_k)^c_k * exp(g_k)`;
- suma (`*_total`): `for' + against'`, `against' = against / att(O_k)^c_k *
  exp(-g_k)` (rozbicie z próbki `*_for` tej samej strony i meczu, B13);
- bez korekty (wartość surowa), gdy rywal nieznany (`opponent_id` None),
  ma < `MIN_TEAM_MATCHES` (5) meczów w ratingu metryki, rynek nie ma metryki
  bazowej ratingu, rynek zawodnika, albo dla sumy brak rozbicia „za/przeciw”.

Średnia skorygowanej próbki to siła własna strony wobec przeciętnego rywala
w domenie dzisiejszego meczu; dalej środek liczony jak dziś (K, prior,
rating, rozrzut). Bramki A5 pod przełącznikiem czytają te same skorygowane
wartości (W7). To nie jest strojenie progów („gate tuning” odrzucone):
progi (`MAX_OWN_SAMPLE_GAP` 0,15, moda, ekstremum) zostają, zmienia się tylko
wejście bramki - na tę samą próbkę, z której liczony jest środek.

### Test H (historia, B15; W1 / W4)

- Dane: `football_rating.load_history` (pickle SHEET-a; `parse_event` czyta
  `metrics.extract_metric`, tę samą funkcję co SAMPLES), sparingi poza
  historią. Księga `RatingBook` (reguła linku z 10-07) aktualizowana
  sekwencyjnie: mecz oceniany księgą wszystkich meczów ściśle wcześniejszych.
- Próbka (jak R0 w `measure_sample_composition.py`, czyli to, co robi
  SAMPLES): 10 ostatnich wcześniejszych meczów strony z daną statystyką, bez
  meczów, w których strona grała drugim składem; n >= 5 na stronę. Suma: pula
  obu stron, mecz raz (bez h2h spoza okien). Gole poza testem (SAMPLES bierze
  dla goli ligowych regułę tej samej rozgrywki; rating dominuje).
- Mecze z linkiem `UNLINKED` (gole) pominięte - CONFIDENCE je odrzuca.
- Środek: `(n x średnia + K x prior) / (n + K)`, K z
  `K_CENTRE.by_market.football` (inaczej 15), prior = przyczynowa średnia
  ligi z księgi (`league_rates`, >= 30 meczów, inaczej globalna); rynek
  oceniany (`FootballForecast.centre` nie None) 0,5 x rating + 0,5 x to.
  Prior i rating identyczne w obu ramionach. Przybliżenie SHEET-a: prior z
  księgi, nie z `sofa_league_baselines.json` / priora dnia.
- Rozrzut i rodzina: `engine.sheet_predictive_sd` / `sheet_count_p_raw` z
  zainstalowaną tabelą dyspersji (`count_dispersion`), dla rynków spoza
  tabeli wariancja próbki ramienia.
- Rynki: `{corners, corners_1h, corners_2h, shots, shots_1h, shots_on_target,
  shots_on_target_1h, fouls, fouls_1h}` x `{_for, _total}` (próg) oraz
  `cards_points_for`, `offsides_for/_total` (raportowane, bez progu).
- Drabina: `calibrate_from_cache.lines_for(środek dzisiejszy)`, 9 linii,
  P(OVER) przycięte do [0,02; 0,98]; te same linie w obu ramionach.
- Okno: mecze 2025-10-12..2026-06-08 = trening mapy kalibracji, 2026-06-09..
  2026-10-12 = ewaluacja (cięcie 2026-06-09).
- Metryka: `lc_all` jak w `measure_pooling.py` (`calibrated_losses`: mapa 40
  koszy wygładzona 30 pseudo-liniami, per rynek i ramię, dopasowana na
  treningu, czytana na ewaluacji), suma log-loss / liczba linii; różnica
  ramię - dziś, 95% przedział z bootstrapu po meczach, 2000 losowań, ziarno 0.
- Ramiona: **T** dziś; **C** rywal + domena (główne); diagnostycznie **O**
  sam rywal, **D** sama domena.
- Próg (zapisany z góry): rynek spełnia, gdy górna granica 95% (C - T) < 0.
  Raportowany per rynek; osobno podgrupa meczów, w których dzisiejsza para
  jest `LINKED_BY_STRENGTH` (W4: Aktobe).

### Test G (bramki, A5; W7)

- Populacja: wiersze piłki 2026-10-09..2026-10-12 (bez propsów, bez rynków
  pochodnych), dla których SHEET jest odtworzony w procesie: te same
  artefakty dnia (`02/03/04`), ta sama funkcja `run_sheet.process_fixture`,
  księga as-of północy dnia, dwa razy - przełącznik wyłączony i włączony.
  Próbki tych dni nie mają `opponent_id` (B13 od 10-13): uzupełniane z
  historii po `sofascore_event_id` (rywal = druga strona meczu).
  Sprawdzenie odtworzenia: p wyłączonego ramienia wobec `p_central` z
  `sofa_settled_row`.
- „Do druku” (przybliżenie CONFIDENCE): pewność = krzywa
  (`Calibration.realised`, plik dnia `calibration_path_for`) >= 0,70 i pewność
  x kurs >= 0,90, kurs i wynik z `sofa_settled_row` (WIN/LOSS). Bez line
  evidence, marży drabiny, świeżości ceny - te same w obu ramionach.
- Bramki: `LINE_BEYOND_SAMPLE`, `MODE_LOSES`, `MODEL_ABOVE_OWN_SAMPLE` -
  ramię wyłączone na surowej próbce, ramię włączone na skorygowanej.
- Raport: liczba nóg do druku, zdjętych przez każdą bramkę, pozostałych;
  realizacja - pewność i ROI po kursie Superbetu dla zdjętych i
  pozostałych, 95% bootstrap po meczach (2000, ziarno 0). Bez progu (4 dni) -
  opis skutku dla decyzji, nie decyzja.

### Co zostaje poza tym pomiarem

Włączenie wymagałoby tej samej korekty w replayu (`calibrate_from_cache.py`)
i refitu krzywych piłki - krzywe są dopasowane do estymatora bez korekty.
Tu nie ma refitu ani instalacji.

## Wynik

(uzupełniane po pomiarze)
