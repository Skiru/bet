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

## Wynik (2026-10-13, `data/audit_2026-10-13/b15_history.json`, `b15_gates.json`)

### Test H (historia): `lc_all` po kalibracji, ramię - dziś, x 10^-3 na linię

Trening 757 077 wierszy (2025-10-12..2026-06-08), ewaluacja 355 264 wiersze /
22 946 meczów (2026-06-09..2026-10-12); bootstrap po meczach 2000, ziarno 0.
Sprawdzenie zgodności szybkiej sumy NB z `engine.sheet_count_p_raw`: 300
wierszy, różnica < 1e-5. Ujemne = lepiej. „mecze” = mecze ewaluacji z
wierszem rynku; `T lc` = poziom dzisiejszy.

| rynek | wiersze | mecze | T lc | **C - T** [95%] | próg | O - T | D - T |
|---|---|---|---|---|---|---|---|
| corners_for | 39 210 | 20 719 | 0.4740 | **-0.44 [-0.58; -0.31]** | tak | -0.22 | -0.22 |
| corners_total | 18 491 | 18 491 | 0.5415 | **-0.42 [-0.70; -0.14]** | tak | -0.34 | -0.07 |
| corners_1h_for | 12 149 | 6 323 | 0.3403 | **-1.08 [-1.47; -0.73]** | tak | -0.42 | -0.65 |
| corners_1h_total | 5 826 | 5 826 | 0.4191 | -0.35 [-0.85; +0.11] | nie | -0.30 | -0.23 |
| corners_2h_for | 12 148 | 6 322 | 0.3753 | **-0.50 [-0.82; -0.20]** | tak | -0.13 | -0.25 |
| corners_2h_total | 5 826 | 5 826 | 0.4425 | **-0.52 [-0.94; -0.13]** | tak | -0.49 | +0.04 |
| shots_for | 25 768 | 13 340 | 0.6074 | **-1.96 [-2.38; -1.56]** | tak | -1.10 | -0.89 |
| shots_total | 12 428 | 12 428 | 0.6360 | +0.01 [-0.46; +0.49] | nie | -0.06 | +0.05 |
| shots_1h_for | 12 162 | 6 329 | 0.5093 | **-1.07 [-1.43; -0.72]** | tak | -0.59 | -0.51 |
| shots_1h_total | 5 833 | 5 833 | 0.5708 | +0.03 [-0.34; +0.41] | nie | -0.15 | +0.11 |
| shots_on_target_for | 32 553 | 16 992 | 0.4421 | **-0.73 [-0.89; -0.55]** | tak | -0.38 | -0.27 |
| shots_on_target_total | 15 561 | 15 561 | 0.5328 | **-0.44 [-0.66; -0.23]** | tak | -0.42 | -0.03 |
| shots_on_target_1h_for | 11 845 | 6 169 | 0.3003 | **-0.51 [-0.77; -0.25]** | tak | -0.20 | -0.25 |
| shots_on_target_1h_total | 5 676 | 5 676 | 0.4010 | -0.13 [-0.42; +0.16] | nie | -0.18 | +0.06 |
| fouls_for | 29 960 | 15 529 | 0.5669 | -0.07 [-0.23; +0.10] | nie | -0.12 | +0.03 |
| fouls_total | 14 431 | 14 431 | 0.6302 | -0.29 [-0.73; +0.09] | nie | -0.30 | -0.01 |
| fouls_1h_for | 11 883 | 6 240 | 0.4421 | **-0.42 [-0.69; -0.13]** | tak | -0.53 | +0.11 |
| fouls_1h_total | 5 643 | 5 643 | 0.5463 | **-0.49 [-0.88; -0.08]** | tak | -0.51 | +0.04 |
| cards_points_for | 19 807 | 10 390 | 0.2903 | -0.16 [-0.26; -0.05] | (bez progu) | -0.06 | -0.09 |
| cards_points_total | 9 418 | 9 418 | 0.4214 | -0.14 [-0.25; -0.03] | (bez progu) | -0.19 | +0.01 |
| offsides_for | 32 957 | 17 270 | 0.2870 | -0.15 [-0.29; -0.02] | (bez progu) | -0.21 | +0.00 |
| offsides_total | 15 689 | 15 689 | 0.4009 | -0.91 [-1.23; -0.58] | (bez progu) | -0.96 | +0.03 |

**Próg: 12 z 18 rynków corners_* / shots_* / fouls_* spełnia** (górna granica
< 0). Nie spełniają: `corners_1h_total`, `shots_total`, `shots_1h_total`,
`shots_on_target_1h_total`, `fouls_for`, `fouls_total` - żaden nie jest
gorszy z przedziałem wykluczającym zero (najgorszy punktowo `shots_1h_total`
+0.03). Wszystkie cztery rynki raportowane bez progu też lepsze.

Podgrupa W4 (dzisiejsza para `LINKED_BY_STRENGTH`, wzorzec Aktobe) - zysk
kilkukrotnie większy i niesiony przez domenę (D): `corners_for` -1.26
[-1.78; -0.75] (7 783 wierszy), `corners_1h_for` -4.06 [-5.69; -2.52],
`corners_2h_for` -2.89 [-4.33; -1.54], `shots_for` -5.98 [-7.73; -4.46],
`shots_1h_for` -4.20 [-5.75; -2.63], `shots_on_target_for` -2.17
[-2.81; -1.53], `corners_total` -0.93 [-1.68; -0.16]; sumy strzałów i fauli
w tej podgrupie nierozstrzygnięte. Pierwszy pomiar Aktobe (`corners_for`
+1.65 przy n = 13) dostaje tu potwierdzenie na 3 973 meczach.

Skala zysku: `lc_all` dzisiejszego `shots_for` 0.6074 - korekta zabiera 0.32%
log-lossu; `corners_for` 0.09%. Mały, ale spójny efekt, wszędzie tego samego
znaku na rynkach „za” (strona).

### Test G (bramki, A5), dni 2026-10-09..2026-10-12

Odtworzenie SHEET-a: 81 637 wierszy złączonych z `sofa_settled_row`,
mediana |p - p_central| = 0, 91.1% w granicy 0.005 (reszta: oferta
odświeżona po wyliczeniu wiersza, historia z pickla 10-13). Wiersze ze
skorygowaną próbką: 33 033 (gole poza korektą). Nogi „do druku” w
przybliżeniu (krzywa bez line evidence) - dużo więcej niż kupon drukuje;
liczby opisują skutek bramek, nie kupon.

| ramię | do druku | zdjęte | LINE_BEYOND | MODE_LOSES | MODEL_ABOVE_OWN | pozostałe: realizacja - pewność, ROI |
|---|---|---|---|---|---|---|
| surowa próbka (dziś) | 12 422 | 2 617 | 1 451 | 897 | 269 | -1.7 pp [-2.8; -0.6], -4.5% [-5.9; -3.1] |
| skorygowana | 12 362 | 2 665 | 1 506 | 887 | 272 | -1.7 pp [-2.8; -0.5], -4.5% [-5.9; -3.1] |

Zdjęte przez `MODEL_ABOVE_OWN_SAMPLE`: surowe -3.5 pp [-9.1; +1.9], ROI
-6.5% [-13.6; +0.3] (269 nóg / 189 meczów); na skorygowanej -6.1 pp
[-12.0; -0.4], ROI -8.8% [-16.2; -1.4] (272 / 189). Zmiana zestawu:
357 nóg dziś zostających byłoby zdjętych (-3.6 pp [-8.7; +1.2], ROI -5.1%),
290 dziś zdjętych zostałoby (-5.9 pp [-11.5; -0.5], ROI -8.4%
[-15.7; -1.3]) - te drugie realizowały gorzej, co przy 4 dniach jest
ostrzeżeniem, nie wnioskiem.

**A5 wprost:** gdyby korekta środka działała, a bramki czytały surową
próbkę, `MODEL_ABOVE_OWN_SAMPLE` zdejmowałby nogi tylko dlatego, że środek
odszedł od surowej próbki. Pod przełącznikiem bramki czytają skorygowane
wartości i liczba zdjęć zostaje praktycznie ta sama (2 617 -> 2 665).

### Dwie rzeczy znalezione w trakcie (po rejestracji, jawnie)

1. **Moda na wartościach ciągłych.** Pierwsze uruchomienie Testu G
   (`b15_gates_mode_unrounded.json`) dało `MODE_LOSES` 896 -> 2 403:
   skorygowane wartości są ciągłe, każda inna, więc `statistics.mode`
   zwracał pierwszą obserwację. Poprawka: `opponent_correction.mode_values`
   - skorygowana próbka zaokrąglana do liczby całkowitej przed modą (surowa
   bez zmian). To naprawa wejścia bramki, nie zmiana progu.
2. **Gole poza korektą.** Test H nie mierzył goli (zarejestrowane), a
   pierwsza wersja kodu korygowała je także (`b15_gates_with_goals.json`).
   Kod ograniczony do zmierzonych metryk (`CORRECTED_METRICS`).

## Decyzja

**Przełącznik `SAMPLE_OPPONENT_CORRECTION_FROM_UTC` zostaje `None`.**
Próg spełniony na 12 z 18 rynków progu (i lepszy punktowo na 16), więc
pomiar na historii wspiera korektę, ale jej włączenie zmienia `p_central`
estymatora, na którym dopasowano krzywe piłki: wymaga tej samej korekty w
replayu (`calibrate_from_cache.py` - dziś go nie ma) i refitu krzywych
(etap 4 audytu). Bez refitu krzywa czytałaby p innego estymatora. Kod jest
gotowy za przełącznikiem; bramki A5 czytają skorygowaną próbkę pod tym samym
przełącznikiem. Do decyzji przy reficie: włączać tylko rynki spełniające
próg czy całość (żaden nie jest gorszy).

Zastrzeżenia: prior z księgi zamiast `sofa_league_baselines.json` (te same
w obu ramionach); def rywala z księgi as-of meczu prognozowanego, nie as-of
meczu próbki (tak jak na żywo); bez h2h spoza okien; Test G bez line
evidence i reguł druku poza pewnością i x >= 0,90; 4 dni.
