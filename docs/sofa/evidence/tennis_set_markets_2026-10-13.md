# B5: tenis - gemy w setach i liczba setów z sąsiadów ratingu (audyt 2026-10-13)

Przełącznik: `epochs.TENNIS_SET_RATING_PRICES_FROM_UTC` (domyślnie `None`).
Skrypt: `scripts/sofa/measure_tennis_set_markets.py` (tylko odczyt).
Źródło: `docs/sofa/history/AUDYT_RYNKOW_KONTEKST_2026-10-13.md`, wiersz B5,
Część 3 (`games_set1_total`, `games_set2_total`, `games_won_set1/2/3_for`,
`sets_total`, „Braki wspólne” 2), dziennik V3-1.

## Diagnoza (sprawdzona w kodzie 2026-10-13, commit 3993281f)

- `src/bet/sofa/engine.py:42` `EMPIRICAL_FREQUENCY_METRICS`: `sets_total`,
  `games_won_set1/2/3_for`, `games_set1/2_total` liczone częstością własnej
  próbki (`p_empirical_centred_raw`), środek ściągany do priora z K = 5
  (`config/sofa_engine_constants.json` `K_CENTRE.by_sport.tennis`).
- Prior: `sets_total` - tier × płeć × powierzchnia (`tennis_prior.py:65`
  `TIER_PRIOR_METRICS`); gemy w secie - globalna średnia z
  `config/sofa_league_baselines.json` (9,4134 / 9,3744 / 4,7396 / 4,7071);
  `games_won_set3_for` - brak priora.
- `src/bet/sofa/tennis_rating.py:130` `_READABLE_MARKETS` zawiera
  `games_set1/2_total`, `games_won_set1/2_for` (`read`, `:540-604`), ale
  `:140` `RATING_PRICED_MARKETS` = {`games_won_for`, `handicap_games`,
  `most_games`}; `MatchForecast.probability` (`:532`) przepuszcza tylko
  `RATED_MARKETS`, więc w SHEET (`scripts/sofa/run_sheet.py:1270-1297`) p
  ratingu dla gemów w secie w ogóle nie powstaje, a dla `sets_total` jest tylko
  `forecast_p` (p_central z próbki).
- `games_won_set3_for`: `Outcome` (`tennis_rating.py:476`) nie ma seta 3;
  `read` go nie zna. W arkuszach 10-09..10-12 nie ma ani jednego wiersza tego
  rynku (oferta Superbetu go nie zawierała / próbka cienka) - stąd linie
  pożyczone z drabiny setów 1-2 (niżej).

## Rejestracja (zapisana 2026-10-13 PRZED uruchomieniem pomiaru)

**Hipoteza.** Odczyt z sąsiadów ratingu (ten sam estymator, który 10-07
zastąpił próbkę dla `games_won_for`: −0,0716 log-loss) jest lepszy od obecnego
estymatora próbkowego dla każdego z rynków B5.

**Estymator nowy.** `MatchForecast.read(market, side, line, direction)`:
udział 600 sąsiadów (o najbliższym p zwycięstwa) po wygranej stronie linii;
tabela zawężona tier × płeć (reguła produkcyjna od 10-09,
`TENNIS_SCOPED_TABLE`), cecha V5 (`lp_t`). `games_won_set3_for`: tylko
sąsiedzi z rozegranym pełnym trzecim setem (mecz rozstrzygnięty
super-tiebreakiem nie ma gemów seta 3 - tak jak `extract_metric`), czyli
P(linia | trzeci set rozegrany); nierozegrany = zwrot, wiersz nie istnieje.

**Estymator obecny (odtworzony).** Ścieżka stats-only SHEET: próbka =
ostatnie 10 ukończonych meczów best-of-3 gracza na tej samej rodzinie
nawierzchni przed dniem meczu (`samples.py:341-386`; przybliżenie: rodzina
nawierzchni `surface_family`, nie dokładne `groundType`); `_total` = pula obu
graczy bez duplikatów, obie strony >= 5 wartości (`config.min_sample`);
`_for` = gracz, >= 5 wartości; centrum = n/(n+5)·średnia + 5/(n+5)·prior
(prior jak wyżej; dla wszystkich wierszy gemów w secie globalny - na żywo 99% /
78% wierszy, reszta inny prior lub żaden: przybliżenie); p =
`p_empirical_centred_raw` (przechylenie wykładnicze, ta sama arytmetyka).
Odmowy F35 jak w SHEET: częstość próbki albo p poza [0,05; 0,95] - brak
wiersza.

**Linie (styl Superbetu).** Linie, które Superbet wystawił w arkuszach
2026-10-09..10-12 (`05_sheet.json`, policzone przed pomiarem):
- `games_set1_total`, `games_set2_total`: 6,5 / 7,5 / 8,5 / 9,5 / 10,5 /
  12,5 (każda wystawiona w 250-307 meczach na ~310 - pełna drabina);
- `games_won_set1_for`, `games_won_set2_for`: 2,5 / 3,5 / 4,5 / 5,5 / 6,5
  (1,5 i 0,5 rzadko - pominięte);
- `games_won_set3_for`: Superbet nie wystawił w tym oknie - te same 2,5..6,5;
- `sets_total`: 2,5.
Każda linia, oba kierunki, każdy mecz (rynki `_for`: obie strony).

**Okno i podział.** Historia singli `tennis_rating.load_history` (live DB,
tylko odczyt). Walk-forward, dwa okna: W1 = mecze 2026-03-01..2026-06-14,
W2 = 2026-06-15..2026-10-12. Rating i tabela sąsiadów jak w SHEET:
`AsOfRating.model_at(dzień meczu 00:00Z)` - tylko mecze sprzed dnia.
Współczynniki i `tier_start` dopasowane **przed początkiem okna** (wariant
„clean” z `measure_tennis_outcome_model.clean_config`), więc bez podglądania
przyszłości. Próbka obecnego estymatora - także tylko z meczów sprzed dnia.

**Populacja.** Ukończone single best-of-3, obaj gracze z >= `MIN_RATED`
meczami (jest prognoza), bez pucharów drużynowych i egzybicji. Porównanie na
**części wspólnej**: wiersze, które dają oba estymatory (osobno raportowane
wiersze, które dodaje / zabiera reguła).

**Metryka.** Średni log-loss p na wiersz (mecz × linia × kierunek × strona),
różnica nowy − obecny; 95% przedział z bootstrapu po meczach (2000 losowań,
ziarno 0); per rynek, łącznie W1+W2 i osobno per okno.

**Próg (O5, per rynek).** Spełniony, gdy górna granica 95% przedziału różnicy
(W1+W2) < 0. Raportowane dodatkowo: znak w każdym oknie, kalibracja wierszy
z p >= 0,70 (zrealizowane − średnie p, przedział po meczach).

**Bramki kształtu (wymóg operatora dla modeli matchupu).** Dla wierszy z
nowym p >= 0,70 (przybliżenie „do druku”: brak historycznych cen Superbetu i
krzywej dla nowego p, więc bez warunku pewność × kurs) liczba wierszy, które
odrzuciłyby `LINE_BEYOND_SAMPLE` i `MODE_LOSES` (`confidence.py:950`, `:970`,
na własnej próbce wiersza, jak `run_confidence.py:788-796`), i ich realizacja;
to samo dla obecnego p >= 0,70.

**Zastrzeżenia zapisane z góry.**
- Krzywe tych rynków (`config/sofa_confidence_calibration.json`,
  `by_market_direction`) są dopasowane na p obecnego estymatora; replay
  `calibrate_from_cache.py` nie produkuje dziś wierszy setowych ani
  `sets_total` (bazy `games`, `aces`, `double_faults`) - włączenie wymaga
  refitu z replayem tych rynków z odczytem sąsiadów.
- Pomiar jest na historii, nie na liniach z ceną: nie mówi nic o ROI.

## Wynik (2026-10-13, `data/audit_2026-10-13/b5/` w worktree, 751 s)

Historia: 246 293 singli. Pominięte mecze testowe (W1 / W2): bez prognozy
ratingu 8 327 / 8 323, nie ukończone best-of-3 1 337 / 1 781, puchary
drużynowe 148 / 118. K = 5, priory jak w rejestracji.

Log-loss, nowy (sąsiedzi) − obecny (próbka), 1e-4 nat na wiersz, część
wspólna, 95% przedział z bootstrapu po meczach (2000):

| rynek | wiersze | mecze (W1 / W2) | LL obecny | LL nowy | W1+W2 [95%] | W1 | W2 | próg |
|---|---|---|---|---|---|---|---|---|
| `games_set1_total` | 540 480 | 53 850 (24 063 / 29 787) | 0,5406 | 0,5220 | −186,5 [−198,3; −174,1] | −175,6 | −195,3 | **tak** |
| `games_set2_total` | 554 514 | 53 850 | 0,5311 | 0,5139 | −171,9 [−183,4; −160,6] | −178,5 | −166,6 | **tak** |
| `games_won_set1_for` | 919 342 | 56 291 (25 352 / 30 939) | 0,5956 | 0,5305 | −651,7 [−670,0; −632,7] | −639,5 | −661,6 | **tak** |
| `games_won_set2_for` | 919 062 | 56 292 | 0,6039 | 0,5359 | −679,8 [−699,7; −661,0] | −685,6 | −675,1 | **tak** |
| `games_won_set3_for` | 29 778 | 3 678 (1 669 / 2 009) | 0,6458 | 0,5582 | −875,3 [−975,5; −773,4] | −942,7 | −820,3 | **tak** |
| `sets_total` | 107 376 | 53 688 (23 982 / 29 706) | 0,6203 | 0,5986 | −216,4 [−237,9; −196,0] | −210,7 | −221,1 | **tak** |

W każdym oknie przedział też wyklucza zero (`results.json`). Rząd wielkości
jak przy `games_won_for` 10-07 (−716e-4): największy zysk tam, gdzie rynek
jest funkcją różnicy sił (gemy gracza w secie), mniejszy przy sumach seta.

Kalibracja strefy p >= 0,70 (zrealizowane − średnie p, pp [95%], każdy
estymator na swoich wierszach):

| rynek | obecny | nowy |
|---|---|---|
| `games_set1_total` | −0,8 [−1,0; −0,6] (185 749 w.) | −0,1 [−0,3; +0,1] (205 694) |
| `games_set2_total` | −0,7 [−0,9; −0,5] | −0,1 [−0,2; +0,1] |
| `games_won_set1_for` | −2,4 [−2,6; −2,3] (245 999) | +0,4 [+0,2; +0,5] (340 955) |
| `games_won_set2_for` | −2,9 [−3,1; −2,8] | +0,2 [+0,0; +0,4] |
| `games_won_set3_for` | −8,5 [−9,9; −7,2] (7 581) | −0,2 [−0,5; +0,1] (80 506) |
| `sets_total` | −5,4 [−5,9; −4,9] (31 663) | −0,3 [−0,8; +0,2] (25 513) |

Zawyżenie obecnego estymatora na historii ma ten sam znak co na żywo
(audyt: `games_won_set*_for` −6,1 pp na drukowanych nogach 10-09..12).

### Bramki kształtu (`LINE_BEYOND_SAMPLE`, `MODE_LOSES`) przy nowym p

Wiersze z nowym p >= 0,70, które bramki odrzuciłyby na własnej próbce wiersza
(w nawiasie: realizacja odrzuconych vs zostawionych, średnie p):

| rynek | p >= 0,70 | LINE_BEYOND | MODE_LOSES | razem | odrzucone: zreal. / p | zostawione: zreal. / p | bez próbki |
|---|---|---|---|---|---|---|---|
| `games_set1_total` | 205 694 | 15 483 | 15 240 | 30 723 (14,9%) | 0,846 / 0,852 | 0,840 / 0,840 | 10 651 |
| `games_set2_total` | 215 117 | 18 948 | 15 426 | 34 374 (16,0%) | 0,853 / 0,859 | 0,850 / 0,849 | 11 203 |
| `games_won_set1_for` | 340 955 | 63 167 | 28 774 | 91 941 (27,0%) | 0,854 / 0,851 | 0,840 / 0,836 | 9 494 |
| `games_won_set2_for` | 331 139 | 61 935 | 29 860 | 91 795 (27,7%) | 0,854 / 0,854 | 0,839 / 0,836 | 9 203 |
| `games_won_set3_for` | 80 506 | 4 703 | 1 109 | 5 812 | 0,853 / 0,848 | 0,829 / 0,831 | 68 125 |
| `sets_total` | 25 513 | 101 | 650 | 751 (2,9%) | 0,707 / 0,754 | 0,757 / 0,759 | 1 390 |

Dla porównania przy obecnym p: `LINE_BEYOND_SAMPLE` 0 (F35 odrzuca próbkę
jednomyślną, zanim wiersz powstanie), `MODE_LOSES` 5 813 / 5 728 / 2 554 /
2 275 / 84 / 0. Przy nowym p bramki usunęłyby 15-28% wierszy strefy druku
gemów w secie, a usunięte wiersze realizują **na poziomie swojego p** (nie
gorzej od zostawionych) - na historii bramki kształtu odrzucałyby tu dobre
wiersze; wyjątek `sets_total` (751 wierszy, −4,7 pp vs p, małe n). „Bez
próbki” = wiersz, którego próbka nie istnieje (< 5 wartości): w SHEET taki
wiersz w ogóle nie powstaje (THIN_SAMPLE przed odczytem ratingu) - dotyczy to
głównie `games_won_set3_for` (68 125 z 80 506), więc na żywo ten rynek nadal
prawie nie miałby wierszy.

### Decyzja

Próg (górna granica < 0, W1+W2) **spełniony dla wszystkich sześciu rynków**,
także w każdym oknie osobno. Przełącznik `TENNIS_SET_RATING_PRICES_FROM_UTC`
zostaje **`None`** w tym commicie (polecenie sesji nadrzędnej: nie włączać).
Włączenie wymaga:
1. refitu krzywych tych rynków: `calibrate_from_cache.py` dziś nie produkuje
   wierszy `games_set*_total`, `games_won_set*_for` ani `sets_total` (bazy
   `games`, `aces`, `double_faults`; `rating_reader` czyta tylko
   `games_won_for` / `games_total`) - replay musiałby wygenerować te wiersze z
   wyniku setowego listingu i wycenić je `MatchForecast.read` (as-of,
   `RatingReplay`), a `fit_confidence` dopasować krzywe `market|kierunek`;
   obecne krzywe (`by_market_direction`, kilkaset-kilka tysięcy wierszy na
   koszyk, ze starego p) czytane na nowym p byłyby źle skalibrowane;
2. odświeżenia line evidence (`refresh_line_evidence.py`) - offsety tych
   kluczy są z wierszy starego estymatora;
3. decyzji, co z bramkami kształtu przy nowym p (wyżej: usuwają wiersze
   realizujące na poziomie p) - osobny pomiar na liniach z ceną;
4. znacznika reguły na wierszu arkusza / `rebuild_plan` (dziś tylko
   `tennis_set_rule` w podsumowaniu SHEET), jeśli włączenie miałoby objąć
   dzień już zbudowany.

### Zastrzeżenia

- Estymator obecny jest odtworzony, nie odczytany z arkuszy: rodzina
  nawierzchni zamiast `groundType`, prior globalny dla wszystkich wierszy
  gemów w secie (na żywo 99% / 78%), bez `MIN_HOURS_BETWEEN_MATCHES` i
  dokładnych reguł SAMPLES. Próbka widzi mecze sprzed godziny meczu, rating -
  sprzed dnia (jak w produkcji).
- Linie stałe (drabina Superbetu z 4 dni), każda linia z równą wagą; bez cen,
  więc nic o ROI ani o warunku pewność × kurs.
- `games_won_set3_for`: Superbet nie wystawiał tego rynku w oknie 10-09..12;
  linie pożyczone.
