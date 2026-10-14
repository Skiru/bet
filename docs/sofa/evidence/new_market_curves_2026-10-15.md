# Krzywe nowych rynków z historii - strzały zawodnika i podwójna szansa (2026-10-15)

Plan: `docs/sofa/history/PLAN_KRZYWE_NOWE_RYNKI_2026-10-14.md`, kroki 1-4 dla
dwóch grup (strzały zawodnika `bet.sofa.shot_detail`, podwójna szansa
`bet.sofa.football_result`) oraz instalator (krok 5). **Krzywe są
przygotowane (STAGED), NIE zainstalowane** - instalacja zmienia druk i
wymaga zgody operatora / pętli porannej przed budową 10-15.

**Od 2026-10-14 ~18:55Z bramka jest jednostronna** (decyzja operatora) -
werdykty i tabele niżej to reguła dwustronna, z jaką grupy powstały; obecne
werdykty: sekcja „Bramka jednostronna (decyzja operatora 2026-10-14)” na
końcu.

## Bramka (wspólna, `scripts/sofa/new_market_gate.py`)

- Krzywa: kubełki `fit_confidence.EDGES`, kubełek tylko z >= 400 wierszy
  (`MIN_MARKET_BUCKET`), `realised` i dolna granica Wilsona `realised_lo95`
  (to drukuje CONFIDENCE).
- Krzywa dopasowana na oknie treningowym (do 2026-08-31), czytana na
  2026-09-01..2026-10-13 tak, jak czyta CONFIDENCE: każda prognoza z holdoutu
  dostaje `realised_lo95` swojego kubełka treningowego („wartość krzywej”).
- PASS: wśród prognoz z wartością krzywej >= 0,70 |zrealizowane - średnia
  wartość krzywej| <= 2 pp przy n >= 300 (reguła PASS `measure_calibration.py`).
  95% przedział (losowanie meczów) tylko raportowany, nie decyduje.
- Klucz, który przejdzie: krzywa końcowa na WSZYSTKICH danych sprzed
  2026-10-15. Klucz, który nie przejdzie: brak krzywej (tryb zbierania linii,
  `NO_LINE_EVIDENCE`).

## Grupa 1: strzały zawodnika

`scripts/sofa/fit_shot_detail.py --before 2026-10-15 --holdout-from 2026-09-01
--holdout-to 2026-10-14 --estimator config/sofa_shot_detail.json`, kopia tabel
`data/refit_new_markets_2026-10-15/shot_detail/shot_detail.db` (114 195
wyjściowych składów; trening 88 851, holdout 25 344).

Estymator SHEET-a (`shot_detail.forecast`: ostatnie 10 startów zawodnika,
pula pozycji, K) - w bramce pule i K dopasowane tylko na treningu; krzywa
końcowa liczona zainstalowanym `config/sofa_shot_detail.json` (tym, którym
SHEET wycenia). Linie 0,5 / 1,5 / 2,5 razem na klucz `<metryka>|OVER`.

| klucz | n (krzywa >= 0,70) | mecze | krzywa | zrealizowane | luka [95%] | wynik |
|---|---|---|---|---|---|---|
| `player_right_foot_shots_for|OVER` | 1 154 | 716 | 0,7323 | 0,7470 | +1,46 pp [-0,80; +3,94] | **PASS** |
| `player_left_foot_shots_for|OVER` | 271 | 243 | 0,7111 | 0,7675 | +5,64 pp [+0,26; +10,28] | FAIL (n < 300) |
| `player_shots_outside_box_for|OVER` | 0 | - | - | - | - | FAIL (krzywa treningowa bez kubełka >= 0,70) |
| `player_headed_shots_for|OVER` | 0 | - | - | - | - | FAIL (j.w.) |
| `player_sot_outside_box_for|OVER` | 0 | - | - | - | - | FAIL (j.w.) |
| `player_sot_headed_for|OVER` | 0 | - | - | - | - | FAIL (j.w.) |
| `player_sot_left_foot_for|OVER` | 0 | - | - | - | - | FAIL (j.w.) |
| `player_sot_right_foot_for|OVER` | 0 | - | - | - | - | FAIL (j.w.) |

Prawa noga w kubełkach: 0,70-0,75 n 637, krzywa 0,7033 / zrealizowane 0,7253;
0,75-0,80 n 517, 0,7681 / 0,7737. Krzywa końcowa (do instalacji) ma też
kubełki 0,80-0,825 (n 590, lo95 0,7855) i 0,825-0,85 (n 405, lo95 0,7900),
których krzywa treningowa nie miała - **te dwa kubełki nie były sprawdzone
poza próbą** (bramka jest na kluczu, nie na kubełku). Strzały spoza pola
karnego miały kubełki >= 0,70 na całych danych (fit 10-14), ale nie na
treningu do 08-31 - bez sprawdzenia nie dostają krzywej.

## Grupa 2: podwójna szansa (piłka)

`scripts/sofa/fit_double_chance_curve.py --out-dir
data/refit_new_markets_2026-10-15/double_chance` (domyślnie: od 2024-10-01,
holdout 2026-09-01..2026-10-13, do 2026-10-15). Historia: sparsowany pickle
SHEET-a `data/cache/football_history.pkl` (tylko odczyt). Replay walk-forward
estymatorem SHEET-a (`run_sheet.double_chance_rows`): czyste centra ratingu
`FootballForecast.centre("goals_for")`, NB z `nb_r` 7,586 z
`config/sofa_football_result.json` (zmierzone na 2024-10-01..2026-06-08, przed
holdoutem), p poza [0,05; 0,95] nie wyceniane, UNLINKED wyłączone (22 462
z 594 579 meczów z ratingiem). Wynik w regulaminowym czasie (goals = normaltime).

Klucz jak go czyta CONFIDENCE: `Calibration.realised("double_chance", p,
sport, "OVER", klass)` -> `by_market_direction["double_chance|OVER"]` -
wybór (1X / X2 / 12) nie jest w kluczu, więc krzywa łączy trzy wybory.
Mecze kobiet czytają tylko krzywą klasy (`by_class.women`), więc dopasowano
też `women:double_chance|OVER`. Krzywa główna dopasowana na wszystkich meczach
(jak `fit_confidence`), bramka na meczach mężczyzn (to oni ją czytają).

| klucz | n (krzywa >= 0,70) | mecze | krzywa | zrealizowane | luka [95%] | wynik |
|---|---|---|---|---|---|---|
| `double_chance|OVER` (mężczyźni) | 50 711 | 31 890 | 0,8018 | 0,7914 | -1,04 pp [-1,35; -0,75] | **PASS** |
| `women:double_chance|OVER` | 4 226 | 2 547 | 0,8266 | 0,8199 | -0,67 pp [-1,65; +0,34] | **PASS** |

Diagnostyka (nie decyduje): po wyborze, mężczyźni - 1X -1,53 pp [-2,18;
-0,85] (n 14 267), X2 -1,84 pp [-2,86; -0,70] (n 5 419), 12 -0,67 pp [-1,11;
-0,19] (n 31 025); kobiety - 1X -3,06 pp [-5,45; -0,78] (n 1 090, poza 2 pp),
X2 -2,55 pp [-5,74; +0,61] (n 635), 12 +0,84 pp [-0,67; +2,25] (n 2 501);
wszystkie mecze razem -0,92 pp [-1,22; -0,62].

**Uwaga:** klucz męski przechodzi regułę 2 pp, ale jego przedział leży
całkowicie poniżej zera - na holdoucie (wrzesień-październik, początek
sezonu) krzywa zawyża o ~1 pp, najwięcej na wyborach z remisem (1X, X2) i
w kubełkach 0,85-0,925 (do -2,5 pp). Zgodne z pomiarem C2 z 10-12 (krzywa
historyczna zawyża początek sezonu o 2,4-4 pp; składnik fazy sezonu
`season_phase` nie jest w estymatorze DC). `line_evidence` dalej może tylko
obniżyć.

## Pliki

`data/refit_new_markets_2026-10-15/{shot_detail,double_chance}/`:
`curves.json` (`target`, `fitted_from`, `by_market_direction` / `by_class`
tylko kluczy PASS, `gate` każdego klucza, krzywe treningowe i końcowe
wszystkich kluczy), `gate_report.md`, wiersze (`rows_holdout.csv.gz`,
`rows_final.csv.gz` / `rows.csv.gz`).

## Instalator

`scripts/sofa/install_new_market_curves.py --dir
data/refit_new_markets_2026-10-15 (--dry-run | --confirm)`: zbiera grupy
`shot_detail`, `double_chance`, `football_incidents`, `tennis_sets`,
`sport_derived` (ta do `config/sofa_sport_confidence_calibration.json`,
format `sports.<sport>.curves`, reszta do
`config/sofa_confidence_calibration.json`; pole `target` w `curves.json`
rozstrzyga). Instaluje tylko klucze z `gate[<klucz>].pass == true` (klucz
klasy `women:<klucz>`, klucz sportu `<sport>:<klucz>`); klucz bez wpisu w
`gate` się nie instaluje. Odmawia (exit 2, nic nie zapisane): klucz, który
już ma krzywą (kierunkową lub `by_market`), błędna krzywa, istniejący katalog
kopii. Scala też obok leżący `.next.json`. Kopia zapasowa do
`config/backup_2026-10-15_new_markets/`, zapis atomowy, potem `pytest
tests/sofa -q`; porażka = przywrócenie z kopii. `fitted_from` każdego klucza
w `new_market_curves_fitted_from`. Testy offline:
`tests/sofa/test_install_new_market_curves.py`,
`tests/sofa/test_new_market_curve_fits.py`.

Dry run na tym katalogu (2026-10-14): ADD `player_right_foot_shots_for|OVER`
(6 kubełków), `double_chance|OVER` (10), `women:double_chance|OVER` (10) do
`config/sofa_confidence_calibration.json`. **Nie uruchomiono `--confirm`.**

Nie sprawdzone: E2E na kopii 10-14 (krok 6 planu - ile nóg by się
wydrukowało) - po decyzji o instalacji.

## Grupa 5 - rynki pochodne sportów mierzonych (`shadow.DERIVED_MARKETS`)

Stan: **dopasowane i sprawdzone, NIE zainstalowane** (instaluje
`scripts/sofa/install_new_market_curves.py` za zgodą operatora; jego
`--dry-run` czyta ten kształt: 3 klucze ADD do pliku sportów i do `.next.json`).

- Skrypt: `scripts/sofa/fit_sport_derived.py` (test
  `tests/sofa/test_fit_sport_derived.py`). Wynik:
  `data/refit_new_markets_2026-10-15/sport_derived/` - `curves.json`,
  `gate_report.md` (pełna tabela, kubełki, sekcja „Kształt do instalacji”),
  wiersze `rows/<sport>_{fit,holdout,final}.jsonl` (p, y, mecz, ts).
- Dane: kopia tabel historii (`sofa_entity_events` kind `last` i
  `sofa_listed_event` hokeja / koszykówki / siatkówki) w
  `sport_history.db` tego katalogu; nigdy żywa baza.
- Replay: `sport_confidence.walk_forward_rows` (ten sam, na którym stoją
  krzywe sportów), rynki `DERIVED_HISTORY_MARKETS`, przełączniki estymatora
  z pierwszej budowy 2026-10-15 (koszykówka ze świeżością, reguła stawki ligi;
  bez dogrywki / tempa / strzałów / długości seta), 1000 symulacji.
  Okna: fit 2025-09-01..2026-08-31 (przerzedzone do <= 4000 meczów, jak
  `fit_sport_confidence`), holdout 2026-09-01..2026-10-13 (wszystkie mecze),
  końcowe 2025-10-15..2026-10-14 (<= 4000 meczów).
- Krzywa: konwencja sportów (`sport_confidence.fit_curves`): kubełki `EDGES`,
  **kubełek n >= 200** (`MIN_BUCKET` sportów, nie 400 z planu - tak czyta
  `SportCalibration.lookup`), pewność = dolna granica Wilsona.
- Bramka (holdout przez krzywą z fit): wiersze z wartością krzywej >= 0,70
  łącznie, n >= 300 i |zrealizowane - krzywa| <= 2 pp (obustronnie), ORAZ
  reguła `sport_confidence.admission` (`fit_sport_confidence`: żaden kubełek
  n >= 200 nie zawyża o > 3 pp), ORAZ dla „12” log-loss lepsza od bazy linii
  (górna granica 95% bootstrapu po meczach < 0).

| klucz | wynik | druk n (mecze) | krzywa | zrealizowane | luka [95%] | LL model - baza [95%] |
|---|---|---|---|---|---|---|
| hokej `period_double_chance\|TEAM` | **PASS** | 4303 (1790) | 0,721 | 0,724 | +0,004 [-0,010; +0,017] | -0,0148 [-0,0191; -0,0103] |
| siatkówka `team_sets_exact\|NO` | **PASS** | 7987 (1997) | 0,853 | 0,868 | +0,015 [+0,010; +0,021] | -0,0178 [-0,0222; -0,0136] |
| siatkówka `team_wins_set\|YES` | **PASS** | 2271 (1997) | 0,895 | 0,907 | +0,012 [+0,000; +0,023] | -0,1056 [-0,1186; -0,0922] |
| hokej `double_chance\|TEAM` | FAIL (luka) | 346 (346) | 0,728 | 0,751 | +0,023 [-0,020; +0,067] | -0,0372 |
| hokej `double_chance\|12` | FAIL (luka, „12”) | 2216 | 0,771 | 0,804 | +0,032 [+0,016; +0,049] | -0,0024 [-0,0067; +0,0022] |
| hokej `period_double_chance\|12` | FAIL (luka) | 3646 | 0,707 | 0,743 | +0,035 [+0,021; +0,050] | -0,0018 [-0,0034; -0,0000] |
| kosz `double_chance\|TEAM` | FAIL (luka) | 460 | 0,736 | 0,759 | +0,023 [-0,016; +0,063] | -0,0802 |
| kosz `h1_double_chance\|TEAM` | FAIL (n) | 135 | 0,747 | 0,741 | -0,006 | -0,0429 |
| kosz `h2_double_chance\|TEAM` | FAIL (n) | 132 | 0,702 | 0,750 | +0,048 | -0,0340 |
| kosz `quarter_double_chance\|TEAM` | FAIL (n) | 285 | 0,767 | 0,786 | +0,019 | -0,0244 |
| kosz `double_chance\|12` | FAIL („12”) | 2109 | 0,946 | 0,961 | +0,015 | +0,0065 [+0,0005; +0,0132] |
| kosz `h1/h2/quarter_double_chance\|12` | FAIL („12”) | 2096 / 2098 / 8432 | 0,956 / 0,957 / 0,946 | 0,960 / 0,963 / 0,950 | +0,004 / +0,006 / +0,004 | +0,0012 / +0,0015 / -0,0003 (przedziały przez 0) |
| siatkówka `sets_count\|SETS=3/4/5`, `team_sets_exact\|YES`, `team_wins_set\|NO` | FAIL (n = 0) | 0 | - | - | - | wszystkie < 0 (model lepszy od bazy, ale żadna prognoza nie dochodzi do kubełka >= 0,70 z n >= 200) |

Czytanie: trzy klucze przechodzą; dwa siatkarskie są ostrożne (zrealizowane
o 1,2-1,5 pp powyżej krzywej - dolna granica Wilsona robi swoje, w granicach
2 pp). Luki hokejowe „12” i `double_chance|TEAM` są po stronie ostrożnej
(zrealizowane powyżej krzywej o > 2 pp) - bramka obustronna je odrzuca; to
nie zawyżanie, tylko krzywa z okna fit niedoszacowuje w holdoucie. „12” w
koszykówce: brak przewagi nad bazą (kosz meczowy wręcz gorszy od bazy,
+0,0065 [+0,0005; +0,0132]) - polityka FAIL potwierdzona; hokejowe „12”
też bez przewagi.

Uwaga do instalacji: `team_sets_exact` dopasowany na N = 1 i 2 (jedyne linie
Superbetu 2026-10-14, 32 strony); linia N = 0 / 3 przeczytałaby tę samą
krzywą. `curves.json` niesie `sports.volleyball.fitted_lines`; wpis
`sport_confidence.FITTED_LINES[("volleyball", "team_sets_exact")]` ->
`LINE_OUTSIDE_FIT` to decyzja przy instalacji (zmienia, co się drukuje).
Po instalacji line evidence nadal tylko obniża (offset, cap pasma ceny).

## Grupy 3 i 4 - piłka z incydentów i tenis sety (`scripts/sofa/fit_incident_set_curves.py`)

Plan kroki 1-4. **STAGED, nic nie zainstalowane.** Ta sama bramka co wyżej
(`calibration_audit.MAX_GAP` 2 pp, `MIN_SETTLED` 300; trening przed
2026-09-01, holdout 2026-09-01..2026-10-13, krzywa końcowa przed 2026-10-15,
kubełki `fit_confidence.EDGES`, `MIN_MARKET_BUCKET` 400, Wilson). Klucz główny
oceniany na holdoucie bez klasy (te nogi go czytają), klucz klasy
(`women:`, `tennis_women:`) na holdoucie swojej klasy - CONFIDENCE czyta nogę
klasy wyłącznie z krzywych klasy, bez nich `NO_CLASS_CURVE`.

Kopie (nigdy żywa baza): `football_incidents/incidents.db` (listy incydentów
z `sofa_event_stats`), `football_incidents/football_history.pkl` (historia,
którą parsuje SHEET, kopia z `data/cache/` z 2026-10-14 16:58 lokalnie),
`tennis_sets/tennis.db` (strony `last` tenisa i indeks listingów).

Replay = estymator SHEET, cięcie na dzień UTC (jak SHEET buduje dzień):
`first_goal_probs` na czystych centrach ratingu goli (`RatingBook` z
regułą wspólnej ligi, NB r z `config/sofa_football_result.json`);
`IncidentRates.p_over` meczów z pełnym zapisem sprzed dnia (linie 0,5 / 1,5,
oba kierunki; ocena tylko na pełnym zapisie - tak rozlicza SETTLE);
`tennis_sets.set_win_p` / `score_probs` na sąsiadach gospodarza z
`AsOfRating.model_at(dzień)` i żywym `config/tennis_rating.json` (wariant
`live`, od 2026-04-01 jak krzywa zwycięzcy meczu). p poza [0,05; 0,95]
odrzucone jak w SHEET. `first_goal` meczu UNLINKED jest w wierszach, nie w
krzywej (CONFIDENCE go odrzuca). Zwycięzca seta: OVER = pierwszy na liście
Superbetu, kolejność nic nie znaczy w tenisie, więc obie krzywe kierunkowe
z obu selekcji meczu (jak `match_won_for`) - są równe. Drobna zmiana kodu:
`IncidentRates.add` (`rates_from_records` z niej korzysta, zachowanie
bez zmian, test).

Wiersze: piłka 736 984 selekcji (od 2024-10; 147 242 czytelne listy
incydentów), tenis 392 039 selekcji (od 2026-04-01).

| klucz | n trening | holdout n (krzywa >= 0,70) | krzywa | realizacja | luka pp | wynik |
|---|---|---|---|---|---|---|
| `first_goal|OVER` | 376 040 | 520 | 0,7381 | 0,7442 | +0,62 | **PASS** |
| `red_cards_total|OVER` | 74 945 | 0 | - | - | - | FAIL (n) |
| `red_cards_total|UNDER` | 74 945 | 5 030 | 0,8248 | 0,8302 | +0,54 | **PASS** |
| `penalties_total|OVER` | 78 548 | 0 | - | - | - | FAIL (n) |
| `penalties_total|UNDER` | 78 548 | 4 729 | 0,7836 | 0,8008 | +1,72 | **PASS** |
| `women:first_goal|OVER` | 15 712 | 50 | 0,7270 | 0,8600 | +13,3 | FAIL (n) |
| `women:red_cards_total|UNDER` | 2 713 | 264 | 0,9005 | 0,9167 | +1,62 | FAIL (n) |
| `women:penalties_total|UNDER` | 3 806 | 206 | 0,7760 | 0,7718 | -0,42 | FAIL (n) |
| `women:` OVER kartek / karnych | - | 0 | - | - | - | FAIL (n) |
| `set1_won_for|OVER/UNDER` | 79 244 | 2 239 | 0,7737 | 0,8026 | +2,89 | FAIL (luka) |
| `set2_won_for|OVER/UNDER` | 78 968 | 2 192 | 0,7723 | 0,7974 | +2,51 | FAIL (luka) |
| `set_score|OVER` | 152 579 | 590 | 0,7414 | 0,7983 | +5,69 | FAIL (luka) |
| `tennis_women:set1_won_for|OVER/UNDER` | 34 108 | 1 564 | 0,7686 | 0,7884 | +1,98 | **PASS** (na granicy) |
| `tennis_women:set2_won_for|OVER/UNDER` | 33 730 | 1 642 | 0,7712 | 0,7923 | +2,11 | FAIL (luka) |
| `tennis_women:set_score|OVER` | 65 212 | 304 | 0,7604 | 0,8125 | +5,21 | FAIL (luka) |

Czytanie wyników:
- Piłka: przechodzą `first_goal|OVER`, `red_cards_total|UNDER`,
  `penalties_total|UNDER` (krzywe końcowe 5 / 9 / 9 kubełków). OVER kartek i
  karnych nigdy nie sięga 0,70 - nie ma czego drukować. Kobiety: za mało
  holdoutu (n < 300) - nogi kobiet czytałyby `NO_CLASS_CURVE`.
  `first_goal` jest jednostronny: nawet z krzywą drukuje się jako single
  tylko, jeśli operator rozszerzy `confidence.one_sided_single` (plan,
  „Ograniczenia”).
- Tenis: wszystkie klucze bez klasy odpadają, bo krzywa **zaniża** (realizacja
  2,5-5,7 pp powyżej krzywej) - bramka jest dwustronna, więc FAIL. Podejrzenie
  (niezmierzone): współczynniki `config/tennis_rating.json` dopasowano na
  historii do 2026-10-01, więc w holdoucie prognozy są ostrzejsze niż w
  treningu (look-ahead wariantu `live`). Przechodzi tylko
  `tennis_women:set1_won_for` (+1,98 pp, o włos) - po instalacji drukowałyby
  się wyłącznie nogi seta 1 kobiet, mężczyźni nadal bez krzywej. Decyzja
  operatora, czy instalować klucz klasy bez klucza głównego.
- Dry run instalatora (2026-10-14): ADD `first_goal|OVER`,
  `penalties_total|UNDER`, `red_cards_total|UNDER`,
  `tennis_women:set1_won_for|OVER`, `tennis_women:set1_won_for|UNDER`.
  **Nie uruchomiono `--confirm`.**

Pliki: `data/refit_new_markets_2026-10-15/{football_incidents,tennis_sets}/`
`curves.json` (`target`, `fitted_from`, `by_market_direction` / `by_class`
tylko PASS, `gate` każdego klucza z krzywą treningową i kubełkami holdoutu),
`rows.csv` (key, p, y, event_id, date, klasa, link), `gate_report.md`.
Test: `tests/sofa/test_fit_incident_set_curves.py`. Nie sprawdzone: E2E
(krok 6), przedział bootstrapowy luki (bramka go nie używa).

## Bramka jednostronna (decyzja operatora 2026-10-14)

Decyzja operatora 2026-10-14 ~18:55Z: klucz odpada tylko wtedy, gdy jego
krzywa **zawyża** na holdoucie. PASS: wśród prognoz holdoutu z wartością
krzywej treningowej >= 0,70 n >= 300 **i** zrealizowane - krzywa >= -2 pp;
niedoszacowanie dowolnej wielkości przechodzi (drukowana pewność jest wtedy
ostrożna). Bez zmian: reguła dopuszczenia sportów (`sport_confidence.admission`:
żaden kubełek holdoutu n >= 200 nie zawyża o > 3 pp - już jednostronna);
każdy klucz „12” (bez remisu) odpada z zasady (brak przewagi nad bazą,
zmierzone; log-loss dalej raportowana); klucz, którego krzywa nie sięga
0,70, odpada - teraz także wtedy, gdy kubełka >= 0,70 nie ma krzywa
**końcowa** (`new_market_gate.require_final`; żaden obecny klucz tego nie
dotyczy). Dawny werdykt dwustronny zostaje w każdym wpisie bramki jako
`two_sided_pass` i w raportach (kolumna „dwustronna”), tylko do porównania.

Kod: `scripts/sofa/new_market_gate.py` (`one_sided_pass`, `two_sided_pass`,
`require_final`, `RULE_TEXT`), bramki w `fit_shot_detail.py`,
`fit_double_chance_curve.py`, `fit_incident_set_curves.py`,
`fit_sport_derived.py`. Każdy skrypt ma `--regate`: nowa decyzja z wierszy
zapisanych w katalogu, bez kopii bazy i bez replayu. Testy offline:
`tests/sofa/test_install_new_market_curves.py` (reguła, podłoga krzywej
końcowej), `test_new_market_curve_fits.py`, `test_fit_incident_set_curves.py`,
`test_fit_sport_derived.py` (re-gate z wierszy).

**Ponowna bramka** (2026-10-14, `data/refit_new_markets_2026-10-15/`, nic nie
liczono od nowa poza bramką):

- `shot_detail`: `rows_holdout.csv.gz` przez zapisane `training_curves`;
  krzywe końcowe = zapisane `final_curves_all_keys` (zainstalowany
  estymator, wszystkie starty sprzed 2026-10-15). Liczby odtworzone 1:1.
- `double_chance`: wiersze holdoutu z `rows.csv.gz` przez zapisane krzywe
  treningowe, krzywe końcowe zapisane. Krzywych NIE dopasowano z
  `rows.csv.gz` od nowa: p jest tam zaokrąglone do 6 miejsc i kilka z 1,7 mln
  wierszy przechodzi przez granicę kubełka (różnica n o 1-5 w kubełku).
  Liczby bramki odtworzone 1:1.
- `football_incidents`, `tennis_sets`: `rows.csv` (p zaokrąglone już w
  replayu, więc odtworzenie jest dokładne): trening, holdout i krzywe
  końcowe przeliczone z wierszy - liczby i dawne krzywe końcowe identyczne;
  krzywe nowych kluczy dopasowane na wszystkich wierszach sprzed 2026-10-15,
  tak jak dla dotychczasowych.
- `sport_derived`: `rows/<sport>_{fit,holdout,final}.jsonl` -> krzywe fit,
  `evaluate`, `admission`, krzywe końcowe (okno final 2025-10-15..2026-10-14,
  jak wcześniej) przeliczone; log-loss względem bazy wzięta z zapisanego
  `partial_<sport>.json` (tylko raport). Liczby identyczne.

Przedziały 95% (losowanie meczów) dla incydentów / tenisa policzone teraz
(1000 losowań; bramka ich nie używa).

| klucz | n (mecze) | krzywa | zrealizowane | luka [95%] | dwustronnie | jednostronnie |
|---|---|---|---|---|---|---|
| `player_right_foot_shots_for\|OVER` | 2 076 | - | - | +1,01 pp [-0,71; +2,84] | PASS | PASS |
| `player_left_foot_shots_for\|OVER` | 818 (603) | 0,7666 | 0,8166 | +5,00 pp [+2,09; +7,63] | FAIL | **PASS (nowy)** |
| `player_shots_outside_box_for\|OVER` | 156 | - | - | +3,54 pp | FAIL | FAIL (n < 300) |
| strzały głową / celne (5 kluczy) | 0 | - | - | - | FAIL | FAIL (brak wartości >= 0,70) |
| `double_chance\|OVER` | 50 711 | 0,8018 | 0,7914 | -1,04 pp [-1,35; -0,75] | PASS | PASS |
| `women:double_chance\|OVER` | 4 226 | 0,8266 | 0,8199 | -0,67 pp [-1,65; +0,34] | PASS | PASS |
| `first_goal\|OVER` | 520 (520) | 0,7381 | 0,7442 | +0,62 pp [-3,41; +4,28] | PASS | PASS |
| `red_cards_total\|UNDER` | 5 030 (4 727) | 0,8248 | 0,8302 | +0,54 pp [-0,52; +1,62] | PASS | PASS |
| `penalties_total\|UNDER` | 4 729 (4 352) | 0,7836 | 0,8008 | +1,72 pp [+0,57; +2,84] | PASS | PASS |
| OVER kartek / karnych, wszystkie `women:` piłki | 0-264 | - | - | - | FAIL | FAIL (n < 300) |
| `set1_won_for\|OVER` i `\|UNDER` | 2 239 (2 239) | 0,7737 | 0,8026 | +2,89 pp [+1,21; +4,42] | FAIL | **PASS (nowe)** |
| `set2_won_for\|OVER` i `\|UNDER` | 2 192 (2 192) | 0,7723 | 0,7974 | +2,51 pp [+0,92; +4,19] | FAIL | **PASS (nowe)** |
| `set_score\|OVER` | 590 (590) | 0,7414 | 0,7983 | +5,69 pp [+2,53; +8,76] | FAIL | **PASS (nowy)** |
| `tennis_women:set1_won_for\|OVER` i `\|UNDER` | 1 564 | 0,7686 | 0,7884 | +1,98 pp [-0,23; +4,02] | PASS | PASS |
| `tennis_women:set2_won_for\|OVER` i `\|UNDER` | 1 642 | 0,7712 | 0,7923 | +2,11 pp [+0,06; +4,00] | FAIL | **PASS (nowe)** |
| `tennis_women:set_score\|OVER` | 304 | 0,7604 | 0,8125 | +5,21 pp [+1,14; +9,59] | FAIL | **PASS (nowy)** |
| hokej `period_double_chance\|TEAM` | 4 303 (1 790) | 0,721 | 0,724 | +0,35 pp [-0,97; +1,69] | PASS | PASS |
| hokej `double_chance\|TEAM` | 346 (346) | 0,728 | 0,751 | +2,32 pp [-2,01; +6,66] | FAIL | **PASS (nowy)** |
| kosz `double_chance\|TEAM` | 460 (460) | 0,736 | 0,759 | +2,29 pp [-1,61; +6,33] | FAIL | **PASS (nowy)** |
| siatkówka `team_sets_exact\|NO` | 7 987 (1 997) | 0,853 | 0,868 | +1,50 pp [+0,96; +2,06] | PASS | PASS |
| siatkówka `team_wins_set\|YES` | 2 271 (1 997) | 0,895 | 0,907 | +1,20 pp [+0,04; +2,31] | PASS | PASS |
| hokej `double_chance\|12`, `period_double_chance\|12` | 2 216 / 3 646 | 0,771 / 0,707 | 0,804 / 0,743 | +3,24 / +3,52 pp | FAIL | FAIL (polityka „12”; LL vs baza -0,0024 [-0,0067; +0,0022] / -0,0018 [-0,0034; -0,0000]) |
| kosz `double_chance\|12` i połów / kwart „12” | 2 096-8 432 | - | - | +0,4..+1,5 pp | FAIL | FAIL (polityka „12”) |
| kosz `h1/h2/quarter_double_chance\|TEAM` | 135 / 132 / 285 | - | - | - | FAIL | FAIL (n < 300; h1/h2 też dopuszczenie sportu) |
| siatkówka `sets_count`, `team_sets_exact\|YES`, `team_wins_set\|NO` | 0 | - | - | - | FAIL | FAIL (n = 0) |

Zmiana werdyktu: **11 kluczy** przechodzi teraz, choć odpadało (każdy przez
niedoszacowanie, nigdy przez zawyżenie): lewa noga, `set1_won_for` x2,
`set2_won_for` x2, `set_score`, `tennis_women:set2_won_for` x2,
`tennis_women:set_score`, hokej i kosz `double_chance|TEAM`. Żaden klucz,
który przechodził, nie odpadł.

Krzywe końcowe nowych kluczy (kubełki z `realised_lo95` >= 0,70; reszta
kubełków jest w `curves.json`):
- lewa noga (9 kubełków): 0,75-0,80 0,743 (n 2 382), 0,80-0,825 0,747, 0,825-0,85
  0,784, 0,85-0,875 0,817, 0,875-0,90 0,830, 0,90-0,925 0,817 (n 400);
  kubełek 0,70-0,75 ma lo95 0,689 (nie drukuje). Kubełek 0,90-0,925 nie
  był sprawdzony poza próbą (holdout czytał kubełki 0,75-0,90 krzywej
  treningowej) - bramka jest na kluczu, jak przy prawej nodze;
- `set1_won_for` (10 kubełków; OVER = UNDER): 0,7256 (0,70-0,75, n 7 053) ..
  0,9158 (0,925-0,95); `set2_won_for` (10): 0,7263 .. 0,9357; `set_score`
  (7): 0,7147 (0,70-0,75) .. 0,8865 (0,90-0,925);
- `tennis_women:set2_won_for` (8): 0,7210 .. 0,9076; `tennis_women:set_score`
  (6): kubełek 0,70-0,75 ma lo95 0,6817 (nie drukuje), 0,75-0,80 0,7517 ..
  0,825-0,85 0,8168;
- hokej `double_chance|TEAM` (5): 0,75-0,80 0,7734 (n 596), 0,80-0,825
  0,7836 (n 206); 0,70-0,75 ma 0,6979 (nie drukuje). Na holdoucie drukował
  się tylko kubełek 0,75-0,80 (n 346);
- kosz `double_chance|TEAM` (4): 0,70-0,75 0,7207 (n 415), 0,75-0,80 0,7408
  (n 309).

Czytanie:
- Tenis: krzywe męskie (wcześniej FAIL z powodu niedoszacowania) teraz
  przechodzą; po instalacji męskie nogi setów drukowałyby się z pewnością
  ostrożną na holdoucie o 2,5-5,7 pp. **Podejrzenie (niezmierzone)**:
  część tego niedoszacowania to look-ahead współczynników
  `config/tennis_rating.json` (dopasowane do 2026-10-01, więc holdout jest
  ostrzejszy niż trening). Krzywa końcowa obejmuje holdout, więc
  nieprzyszłe dni mogą się zachowywać raczej jak trening niż holdout -
  nie da się tego tu odróżnić; line evidence po instalacji może tylko obniżyć.
- Hokej / kosz `double_chance|TEAM`: n ledwo ponad 300, przedział luki
  szeroki i przez zero ([-2,0; +6,7] / [-1,6; +6,3]) - przechodzą, bo nie
  zawyżają, nie dlatego, że kalibracja jest dokładna.
- `set_score` i `tennis_women:set_score` niedoszacowują najmocniej (+5,2..+5,7 pp,
  dolna granica > 0) - pewność wydrukowana wyraźnie poniżej realizacji.

**Instalator na sucho** (2026-10-14, po ponownej bramce,
`install_new_market_curves.py --dir data/refit_new_markets_2026-10-15
--dry-run`): **22 klucze ADD** - do `config/sofa_confidence_calibration.json`:
`player_left_foot_shots_for|OVER` (9 kubełków), `player_right_foot_shots_for|OVER`
(8), `double_chance|OVER` (10), `women:double_chance|OVER` (10),
`first_goal|OVER` (5), `penalties_total|UNDER` (9), `red_cards_total|UNDER` (9),
`set1_won_for|OVER` / `|UNDER` (10 / 10), `set2_won_for|OVER` / `|UNDER`
(10 / 10), `set_score|OVER` (7), `tennis_women:set1_won_for|OVER` / `|UNDER`
(8 / 8), `tennis_women:set2_won_for|OVER` / `|UNDER` (8 / 8),
`tennis_women:set_score|OVER` (6); do
`config/sofa_sport_confidence_calibration.json` (i `.next.json`):
`basketball:double_chance|TEAM` (4), `hockey:double_chance|TEAM` (5),
`hockey:period_double_chance|TEAM` (6), `volleyball:team_sets_exact|NO` (9),
`volleyball:team_wins_set|YES` (11). **Nie uruchomiono `--confirm`.**
Kopia stanu sprzed ponownej bramki (curves.json / raporty): katalog
roboczy sesji, nie w repozytorium; dawne werdykty są też w polu
`regated.previous_pass` (`fitted_from` / `partial_<sport>.json`).
