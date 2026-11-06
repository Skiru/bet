# Replay reguł, których refit nie odtwarzał, i plan nocny (2026-11-05)

Zlecenie operatora (2026-11-05, wieczór): spisać każdą regułę, która zmienia żywe p, a której żaden fit nie odtwarza (każdy sport, każdy rynek), ułożyć ranking według spodziewanego zysku i wykonać najcenniejsze w nocy w jednej kolejce. Niczego nie instalować. Werdykt i dokładne polecenie instalacji należą do operatora (przed budową 2026-11-06).

**W skrócie:**
- Inwentarz (sekcja 1) i plan (sekcja 2) zapisałem **przed** wykonaniem czegokolwiek. Wyniki są w sekcjach 3 i dalej.
- Najwięcej daje jeden replay piłki i tenisa na kopii bazy, z sędzią, udziałem zawodnika i P14 jako nowymi flagami. Zainstalowanej krzywej z 10-17 brakuje też domkniętych już flag `--closeness-stretch`, `--player-coverage` i `--awarded-excluded`.
- Nadobiecywanie pasma >= 0.90 (−7,1 pp) już zmierzyłem (sekcja 2, pozycja 2). 727 z 790 nóg pochodzi sprzed `PRICE_GAP_OFFSET` (10-30 08:45Z). Mechanizm siedzi w dowodzie linii, nie w krzywej. Po przełączniku: +2,5 pp [−4,3, +8,9] (n 48).

## 1. Inwentarz: reguły zmieniające żywe p bez replayu w fitcie

Źródła: `bet.sofa.epochs` (wszystkie `*_FROM_UTC`), `fitted_from.replay_rules.flags` w `config/sofa_confidence_calibration.json` (krzywe 10-17, 21 flag), `fitted_from` sekcji w `config/sofa_sport_confidence_calibration.next.2026-10-28.json`, `prepare_refit.replay_switch_gaps` (`UNREPLAYABLE_SWITCHES`, `UNREPLAYED_AUDIT_SWITCHES`), `fit_sport_confidence.UNREPLAYED_AUDIT_SWITCHES`, model-state (a)/(c). Każdą pozycję sprawdziłem w kodzie.

Liczba nóg to średnia drukowanych singli dziennie w `11_coupon.json` z 10-28..11-04 (8 dni, razem 5 087 nóg dziennie). Dryf pochodzi z audytu `audyt_krzywych_refit_2026-11-05.md` (T3a/T3b/T5) i oznacza trafione − pewność.

| reguła (od) | dotyka | da się odtworzyć as-of? | dryf, który może tłumaczyć | nogi / dzień | koszt |
|---|---|---|---|---:|---|
| `FOOTBALL_REFEREE` (10-21) | krzywe cards_points_* i fouls_* (też połowy i jointy) | **tak**: `RefereeBook` przesuwany po historii do 00:00Z dnia meczu, tak jak w `referees.fixture_reads`; sędzia meczu z `load_labels`, a gdy go brak, ×1 | cards_points −2,1/−2,7 pp, cards_points_total UNDER −4,1/−4,8, cards_points_for UNDER −4,5/−4,6, both_over_cards_points UNDER −5,5 | 113 (kartki) + 3 (faule) | kod 1–2 h, w replayu wspólnym |
| `FOOTBALL_PLAYER_SHARE` (10-21) | player_shots_for / _shots_on_target_for / _fouls_for | **tak**: udział z jego startów i wolumenu drużyny w tych samych meczach (statystyki meczu) × centrum drużyny z replayu drużynowego tego meczu (live_centre, łańcuch jak w SHEET) | model-state: krzywe na starym p zaniżają o 2–6 pp przy >= 0.70 | 8,6 | kod 2–3 h, w replayu wspólnym |
| `TENNIS_RATING_SCORE_WINNER` P14 (10-24) | rating tenisa: games_won_for, games_total, handicap/most_games, set ratings, match_won_for | **tak**: `load_history(score_winner=True)` w `RatingReplay.from_db` | games_won −3,4, match_won_for OVER −7,0; ale P14 zmienia tylko +173 z 261 357 meczów historii (model-state (a)), więc **spodziewany zysk ~0** | 90 (z ratingu meczu) | 15 min, w replayu wspólnym |
| `FOOTBALL_CLOSENESS_STRETCH` (10-21) | cards_points_for/_total, shots_total/_1h_total | flaga jest od 10-21, zainstalowana krzywa 10-17 jej nie ma | shots −3,5 pp, cards (jak wyżej) | 28 (strzały, sumy) + kartki | 0 (sama flaga) |
| `FOOTBALL_PLAYER_COVERAGE` (10-21), `AWARDED_EXCLUDED` (10-30) | próbki zawodników; wyniki przyznane przy zielonym stoliku | flagi są, krzywa 10-17 ich nie ma (install bez `--awarded-excluded` jest odrzucany) | – | gracze 20,6 | 0 |
| `SAMPLE_CONFLICT_CUT` P1 (10-24) | próbki piłki | replay drużynowy w ogóle nie stosuje reguły jednego składu (historia z `Played`), więc nie ma czego ciąć. W replayu zawodników da się to zrobić jednym argumentem (`finish_history(conflict_cut=True)`) | brak przypisanego dryfu (dotyczy tylko stron z konfliktem encji) | ułamek | 10 min, dodatek |
| `PLAYER_HISTORY_ANY_TEAM` P3, piłka (10-24) | cienkie próbki zawodników | tak co do zasady (`samples.any_team_sample` na składach rywali z cache), ale to osobny czytnik do przeniesienia | brak (dotyczy próbek cienkich) | < 20,6 | 3–4 h. **Pomijam dziś**: niski zysk |
| `PLAYER_SLUG_NAME` P5 (10-24) | dopasowanie nazw Superbetu | **bez znaczenia w replayu**: podmiotem jest nazwa z Sofascore dopasowana do składu Sofascore, slug niczego nie zmienia | – | – | – |
| `JOINT_FILLED_SIDE_CHAIN` R1 (10-28) | jointy piłki | **już odtworzony**: replay daje obu stronom jointu centrum przez `live_centre` na skorygowanej próbce (model-state: „the chain the joint curves' replay already applied”). Sędzia wejdzie do jointów kartek razem z flagą | – | 266 (jointy) | 0 |
| `IDENTITY_GATE_PER_FAMILY` (10-21) | próbki piłki | replay nie ma żadnej bramki tożsamości (`match_values`), ani starej, ani nowej. Dodanie jej zmienia populację i wymaga osobnego pomiaru | nieprzypisany | – | 2 h. **Pomijam** |
| `TENNIS_SET_HANDICAP_NEIGHBOURS` R2 (10-28) | handicap_games_won_set1/2 | replay nie pisze tych kluczy (brak krzywej, tylko dowód linii) | – | **0** drukowanych | pomijam |
| `TENNIS_TOTALS_FLOOR` (11-05 17:05Z) | próg druku, nie p | nie dotyczy | – | – | – |
| `TENNIS_POINT_MODEL` (11-06) | osobny agent, osobne krzywe | poza zakresem | – | – | – |
| koszykówka `LEAGUE_SEASON_RESTART` (10-23) | krzywa kosza (10-14) | **już odtwarzana** przez `fit_sport_confidence` dla `--before` >= 10-23. Zmierzona dwa razy: 10-22 nie zainstalowana, dziś dry-run gorszy (audyt T4: +0,00060 Brier) | bb >= 0.70 −13,4 pp; połowy i kwarty to rozrzut okresów (model-state (e)), nie ta reguła | 18,6 | 0. **Bez nocnego biegu** |
| siatkówka `VB_GOLDEN_SET` P13 (10-24) | historia siatkówki | tak: `parse_history(golden_set=True)` w fitcie sportu | vb >= 0.70 −3,8 pp; points_handicap −24,8 pp to model punktów, nie P13 | 63,8 (points*: 0,8) | 1 h |
| CS2 `CS2_LINEUP_ELO_UNRATED` P7 (10-24) | pary bez ratingu | tak, ale `fit_unrated` musiałby być dopasowywany krocząco w walk-forward | CS2 skalibrowane (T4 +1,1 / +0,8 pp) | część z 40 | 3 h. **Pomijam** |
| hokej, krzywe drużyn | – | brak nieodtworzonej reguły (refit 10-23) | skalibrowane | – | – |
| hokej/kosz, stałe zawodników (10-02) | p graczy (bez krzywej) | P3 hokej: `fit_player_model.py --any-team`. `PLAYER_BOTH_SIDES_LISTED` nie: fit czyta tylko `last` | – | hokej 28,6 | 2 h, pomiar na liniach Superbetu |
| **pasmo >= 0.90** (prośba operatora) | dowód linii, nie krzywa | – | −7,1 pp [−10,3, −4,9] (n 790) | 1–24 dziennie od 10-31 | zmierzone (sekcja 2) |

Poza zakresem reguł bez replayu (to model, nie replay): połowy i kwarty kosza, punkty siatkówki, `handicap_games` tenisa (−7,4/−9,3 pp; `rating_derived_rows` jest odtwarzane). Te dryfy łapie dziś dowód linii.

## 2. Plan nocny według spodziewanego zysku (dryf × nogi), zapisany przed wykonaniem

1. **Wspólny replay piłki i tenisa** na `data/refit_2026-11-05_replay/sofa_copy.db` (VACUUM INTO 17:01–17:13Z, 54,7 GB). Flagi zainstalowanego fitu (21) plus `--closeness-stretch --player-coverage --awarded-excluded` plus nowe `--referee --player-share --tennis-score-winner` (+ P1 w replayu zawodników). Kolejność: testy offline, sprawdzenie równości p z `05_sheet.json`, replay (~5–6 h), fit pełny i fit z hold-outem od 10-18, pomiar (a)/(b). Zysk: kartki (113 nóg/dzień, −2..−5 pp), strzały, zawodnicy. Tenis przez P14 ~0 (+173 meczów).
2. **Pasmo >= 0.90**: zmierzone wieczorem (`data/refit_2026-11-05_replay/topband/`). Odtwarza się dokładnie: n 790, 0.842 wobec 0.913. 727 nóg sprzed `PRICE_GAP_OFFSET` daje −7,7 pp [−11,0, −4,9], a 48 nóg z 10-31..11-04 daje +2,5 pp [−4,3, +8,9]. Gradient po d = pewność − 1/odds: d < 0 +0,4 pp, 0–0,03 −7,1, 0,03–0,06 −11,9, >= 0,06 −16,0 [−25,2, −7,8]. Krzywe (górne kubełki na historii skalibrowane, n 13k–183k) i źródło krzywej niczego nie rozróżniają. Mechanizm: offset per klucz liczony przed 10-30 rozcieńczały linie z d < 0. Największy wkład: `result_handicap|OVER` −10,2 pp, `double_chance|OVER` −21,4 pp, `result_or_over|OVER`, `result_or_under|OVER`, `goals_for|UNDER` (krzywe per linia). Nie robię refitu. Wniosek: test zarejestrowany z góry na nogach od 10-31, ocena przy n >= 300.
3. **Hokej, stałe zawodników z P3** (`fit_player_model.py --any-team --player-team-from-side --sport hockey` na kopii) oraz pomiar na rozliczonych liniach Superbetu wobec zainstalowanych (28,6 nogi/dzień). Tylko jeśli zostanie czas po 1.
4. **Siatkówka P13**: tani fit sportu z `golden_set`, mały spodziewany zysk. Tylko jeśli zostanie czas.
5. Pomijam (powody w tabeli): P3 piłka, bramka tożsamości, R2, P7, restart kosza (już zmierzony gorzej).

## 3. Reguły werdyktu, zamrożone przed wynikami (2026-11-05, przed replayem)

Rodzina = klucz krzywej `market|DIRECTION` (piłka, tenis). Kandydat = krzywe z replayu z nowymi flagami. Zainstalowane = `config/sofa_confidence_calibration.json` (10-17). Pewność w obu ramionach = `Calibration.realised` tak jak w `run_confidence` (bez dowodu linii; dowód linii jest przeliczany co rano na nowych krzywych). Narzędzie: `data/refit_2026-10-22c/measure_swap.py` z dodanym pasmem 0,60–0,70 i licznikiem nóg, które wchodzą do druku lub z niego wypadają.

- **(a) hold-out na historii.** Fit kandydata z cięciem 2026-10-18 (`fit_holdout.py`: wiersze replayu meczów od 10-18 i żywe wiersze od 10-18 poza fitem; klucze bez wiersza replayu zamrożone na zainstalowanych, `freeze_live_only.py`). Na wierszach replayu meczów 10-18..11-04 (nowe p z sędzią i udziałem) liczę log-loss kandydata minus zainstalowanych i trafione − pewność przy >= 0,70. Warunek: log-loss rodziny nie gorszy, czyli górna granica 95% CI różnicy <= +0,5 × 1e-4, a punktowo <= 0. Kalibracja >= 0,70 nie gorsza o więcej niż 1 pp.
- **(b) rozliczone linie Superbetu od 10-17.** Wiersze arkusza z ceną (`offered_odds`), rozliczone, `run_date` 10-18..11-04, osobno grupy epok ledgera. Dla każdego ramienia trafione − pewność przy pewności >= 0,70 (i x >= 0,90) oraz przy 0,60–0,70; 95% CI z bootstrapu po meczach (1000 losowań Poissona). Warunek: |dryf| kandydata < |dryf| zainstalowanych (dryf idzie w stronę 0), a żadna rodzina z n >= 50 nogami >= 0,70 nie nadobiecuje bardziej (dryf kandydata nie niższy niż zainstalowanych o więcej niż 1 pp).
- **Werdykt** per rodzina: (a) nie gorszy **i** (b) spełniony. Instaluję tylko rodziny, które przeszły. Pozostałe klucze zostają zainstalowane. Liczę i podaję nogi, które zaczną lub przestaną się drukować (n, dni).
- Równość p replayu z żywym SHEET (sekcja 4) jest warunkiem wstępnym. Jeśli nie zachodzi, nie uruchamiam replayu.

## 4. Równość replayu z żywym SHEET (10-31..11-04)

Replay okna z wszystkimi flagami (`--no-write`, `data/refit_2026-11-05_replay/verify/run_window.py`), porównany z `05_sheet.json` tych dni (`compare_rows.py`). Wiersze dopasowane po (mecz, rynek, strona, linia, kierunek); „ta sama próbka” = ta sama liczność i średnia próbki.

| klasa wierszy | ta sama próbka n | mediana abs dp | p90 | p99 | max | udział <= 0,01 |
|---|---:|---:|---:|---:|---:|---:|
| piłka, bez sędziego (kontrola) | 14 980 | 0,0012 | 0,0095 | 0,026 | 0,056 | 0,909 |
| piłka, sędzia APPLIED | 242 | 0,0011 | 0,0050 | 0,018 | 0,020 | 0,967 |
| zawodnicy bez udziału | 24 866 | 0,0000 | 0,0000 | 0,073 | 0,311 | 0,966 |
| zawodnicy z udziałem, mecze wycenione przez replay drużyn | 16 928 | 0,0018 | 0,043 | 0,184 | 0,568 | 0,781 |
| tenis, rating | 27 656 | 0,0050 | 0,015 | 0,033 | 0,068 | 0,790 |

Odczyt:
- **Sędzia:** kod jest identyczny jak w SHEET. `referees.fixture_reads`, czyli ta sama funkcja, którą woła `run_sheet`, na tej samej kopii bazy daje 714/714 identycznych odczytów. Mnożnik żywy wobec replayu różni się o medianę 0,0004 (p99 0,015, n 6 072). To dane dopisane po budowie dnia: etykiety sędziów i historia. 104 wiersze nie miały jeszcze sędziego przy budowie. Rozkład różnic wierszy z sędzią jest taki sam jak wierszy kontrolnych, więc człon niczego nie dokłada. Różnica bazowa replayu (książka ratingu urosła od budowy) istniała już przed tą zmianą (`calibrate_from_cache`, „Residual difference from the sheet”).
- **Udział zawodnika:** porównałem wejścia każdego wyliczenia (`share_inputs.py`, 2 948 zawodników-rynków):
  - 88% ma identyczne wejścia (wolumen jego i drużyny, liczba startów, prior pozycji), a centrum zgadza się do 0,6% (różnica centrum drużyny, mediana 0,4%).
  - W 12% replay dopasował więcej startów (323 z 348). To zgodne z danymi dopisanymi po budowie, np. próbka drużyny przy budowie miała 9 meczów ze statystyką, dziś ma 10.
  - Wykryty i naprawiony błąd replayu: zawodnicy meczu, którego replay drużyn nie wycenił (mecz nie był jeszcze w listingach drużyn), dostawali stare centrum. Teraz nie dają wierszy (`share_no_team_replay`, test).
- **P14:** różnice wierszy ratingu tenisa to różnica historii (rating na dłuższej historii). P14 dokłada 173 mecze.
- Ścisłej równości wierszy nie da się osiągnąć bez odtworzenia bazy z chwili budowy. Nowe człony są liczone tym samym kodem i na tych samych wejściach, co SHEET.

## 5. Sporty: koszykówka (połowy i kwarty), siatkówka P13, hokej P3

**Koszykówka, połowy i kwarty na liniach z pozycji rynku (zainstalowane do pliku z datą 11-06).** Przyczynę znalazł przegląd (`data/refit_2026-11-05_replay/drifts/`):
- krzywe okresów dopasowano na liniach w kwantylach własnej symulacji modelu;
- Superbet stawia linię okresu tam, gdzie rynek oczekuje wyniku (kwarta ok. 0,25 × suma meczu, połowa ok. 0,5, handicap ok. H/4, H/2);
- wysokie p przy linii Superbetu oznacza więc głównie spór z centrum rynku;
- na historii, przy liniach w pozycji rynku, surowe p zawyża tak samo (−13,3 pp).

Poprawka: rodziny okresów dopasowane na liniach = suma i handicap meczu z Sofascore ÷ liczba okresów, ±0, 1, 2 pkt. Implementacja: `sport_confidence.period_position_lines`, przełącznik dopasowania `epochs.BB_PERIOD_MARKET_LINES_FROM_UTC` (11-06 00:00Z). Fit `--before 2026-11-06` na kopii. Do pliku `config/sofa_sport_confidence_calibration.next.2026-11-06.json` weszło tylko 15 kluczy okresów, reszta bez zmian. Rozliczone linie Superbetu 10-18..11-04:

| | zainstalowane | refit, linie syntetyczne (kontrola) | **nowy plik** |
|---|---|---|---|
| >= 0,70: n, trafione − pewność | 3 632, −14,1 [−17,6, −10,6] | 3 300, −15,5 | 1 046, **−0,0 [−3,4, +3,6]** |
| 0,60–0,70 | 13 691, −8,8 [−10,3, −7,2] | 14 000, −8,2 | 8 635, −5,3 [−7,2, −3,4] |
| log-loss wobec zainstalowanych (wiersze >= 0,60) | – | +0,0005 [−0,0001, +0,0010] | **−0,0206 [−0,0250, −0,0159]** |

Każda rodzina okresu ma niższy log-loss, z przedziałem bez zera, i żadna nie nadobiecuje bardziej. Historia (fit < 06-01, ocena >= 06-01, linie z pozycji rynku): log-loss −0,0011 [−0,0041, +0,0019], czyli nie gorzej. Większość nóg okresów przestaje się drukować (wiersze >= 0,70: 3 632 → 1 046 w 18 dni). Zostaje −5,3 pp w paśmie 0,60–0,70 (siatka ±2 pkt jest moja, nie dopasowana).

**Siatkówka P13 (złoty set w historii fitu):** replay jest wpięty (`fit_sport_confidence`, `golden_set` według dnia fitu). Werdykt negatywny, nic nie zainstalowano. Na liniach Superbetu od 10-18 refit z P13 jest gorszy od zainstalowanego w `points_handicap` (log-loss +0,0045 [+0,0031, +0,0061]). Ogółem: +0,00066 z P13 wobec −0,00068 bez P13.

**Hokej, stałe zawodników z P3** (`fit_player_model.py --sport hockey --any-team --player-team-from-side`, kopia bazy): nie zainstalowane. Na 39 540 stronach / 244 meczach w porównaniu z zainstalowanymi stałymi: log-loss −0,00017 [−0,00049, +0,00014], Brier +0,00012 [+0,00001, +0,00022]. Od 10-24 (poza próbą decyzji z 10-23): log-loss +0,00022, Brier +0,00023 [+0,00006, +0,00041]. Pliki: `data/refit_2026-11-05_replay/p3/`.

## 6. Punkt 5: waga formy w ratingu (koszykówka, piłka). Reguły zamrożone przed wynikami (2026-11-05 ok. 20:50Z)

Źródło podejrzenia: `docs/sofa/evidence/bateria_statystyk_2026-11-05.md`, sekcja 3. Bateria podejrzewa, że nasze p za słabo waży niedawną formę i tabelę sezonu. Dotyczy to koszykówki `winner` / `total` oraz w piłce 1X2 / DC / DNB i `goals_for` / `goals_1h_for`. Zmieniam tylko wagi istniejącego modelu. Cech baterii nie dokładam do p. Każde ramię liczę as-of i da się je odtworzyć replayem. Krzywe dopasowuję na tym samym ramieniu.

**Pokrętło (jedno na model, wybrane przed wynikami).** Szybkość, z jaką rating drużyny idzie za ostatnimi meczami, to krok `alpha` w `RatingBook.update`. Innego członu formy w tych rynkach nie ma. Tabeli sezonu w modelu nie ma; wolniejsza `alpha` jest jej przybliżeniem, więc siatka idzie w obie strony.
- Koszykówka: `score_model.SCORE_ALPHA["bb_reg_for"]` (dziś 0,06), siatka {0,04; 0,06; 0,08; 0,10; 0,12; 0,15}.
- Piłka: `football_rating.ALPHA_BY_METRIC["goals_for"]` (0,04) i `["goals_1h_for"]` (0,02), razem × {0,75; 1; 1,25; 1,5; 2}. Ten krok zasila też sumy goli i handicapy. Ocena obejmuje więc każdą rodzinę goli, nie tylko podejrzane.

**Koszykówka:**
- **Wybór** na rozwoju. Walk-forward `fit_sport_confidence` z `--before 2026-10-07`, hold-out historii to 30 dni przed tą datą. Kryterium: surowe p modelu, log-loss sumaryczny `winner` + `total` + `handicap`. Wygrywa jedna `alpha`. Jeśli wygrywa 0,06, koniec, nic nie zmieniam.
- **(a)** Wybrana `alpha` wobec 0,06, każde ramię z własnymi krzywymi (`--before 2026-11-06`). Hold-out historii 10-07..11-05, rozłączny z wyborem, bootstrap po meczach. Warunek dla puli (winner, total, handicap, team_total): log-loss pewności punktowo <= 0 i górna granica 95% CI <= +0,5 × 1e-4. Żadna z tych rodzin nie może być gorsza z przedziałem nad zerem.
- **(b)** Rozliczone linie Superbetu od 10-18, per rodzina:
  - trafione − pewność przy >= 0,70 i 0,60–0,70. |dryf| nie większy o więcej niż 1 pp w żadnej rodzinie z n >= 50 nogami >= 0,70;
  - Brier pewności minus Brier ceny bez marży (`fair_p` z `settled.json` SHADOW_SETTLE, łączone po meczu, rynku, linii i stronie), na wierszach pokrytych przez oba ramiona. Luka do ceny nie może urosnąć (punktowo).
- **Werdykt:** (a) i (b) spełnione. Wtedy zmiana `alpha` za przełącznikiem w `epochs` od 00:00Z dnia D. Nowe krzywe koszykówki (wszystkie klucze, łącznie z okresami z sekcji 5) idą do `config/sofa_sport_confidence_calibration.next.<D>.json`. D to najwcześniej dzień po instalacji, nigdy 11-05.

**Piłka:**
- **Wybór i (a)** na historii, tańszym narzędziem z tym samym ratingiem: `measure_dependence_goals.py goals` (trening do 2026-09-30, test 2026-10-01..2026-11-04, mnożnik `alpha` jak w siatce). Kryterium wyboru: log-loss sumaryczny 1X2 + DC + DNB + `goals_for`. Warunek (a): wybrany mnożnik nie gorszy w żadnej rodzinie goli (sumy, handicapy, `goals_for`, połowy) z przedziałem nad zerem, a w sumie punktowo <= 0.
- **(b)** Dopiero dla wybranego mnożnika: pełny replay `calibrate_from_cache` (te same flagi co sekcja 3, plus mnożnik), fit krzywych `fit_confidence` i `fit_result_1x2_dnb_curve`. Potem rozliczone linie Superbetu od 10-18, z tymi samymi warunkami dryfu i luki do ceny (`market_p` z `sofa_settled_row`).
- **Werdykt i termin:** jak w koszykówce, przełącznik w `epochs` od 00:00Z dnia D i krzywe do pliku `.next`. Jeden pełny replay to ok. 3 h, a dodatkowo fit i pomiar. Nie zmieści się przed budową 11-06 ani 11-07.

**Piłka, ramię „osobny krok dla rynków wyniku”.** Dopisane 2026-11-05 przed jakimkolwiek wynikiem punktu 5, na polecenie operatora „porządnie, wszystko po kolei”. Ramię uruchamiam tylko wtedy, gdy wspólny mnożnik `alpha` wyjdzie mieszany: lepszy w 1X2 / DC / DNB, a gorszy w rodzinie goli z przedziałem nad zerem.
- Nowa metryka ratingu: osobna książka goli tylko do centrów 1X2 / DC / DNB, z własnym krokiem. Sumy goli, handicapy i `goals_for` zostają na dzisiejszej `alpha`.
- Siatka kroku: te same mnożniki × {0,75; 1,25; 1,5; 2}. Wybór na tym samym treningu (do 09-30) po log-loss 1X2 + DC + DNB.
- (a) jak wyżej, na teście 10-01..11-04. Pozostałe rodziny goli z definicji się nie zmieniają, sprawdzam to wprost: identyczne p.
- (b) pełny replay z nową metryką, refit `fit_result_1x2_dnb_curve`, linie Superbetu od 10-18, te same warunki.
- Własny przełącznik w `epochs` od 00:00Z dnia D. Instalacja tylko przy (a) i (b). W przeciwnym razie wpisuję ramię jako zmierzone i odrzucone.

**Ramię „tabela sezonu” (koszykówka i piłka).** Dopisane 2026-11-05 przed jakimkolwiek wynikiem punktu 5, na żądanie operatora: `alpha` nie zastępuje tabeli.
- **Tabela as-of** z naszych wyników Sofascore (cache, bez sieci), liczona z meczów tych samych rozgrywek i sezonu (`season.id` zdarzenia), zakończonych ściśle przed startem. Wyniki przyznane przy stole (`isAwarded`) i towarzyskie są poza tabelą.
- **Trzy wielkości różnicy między stronami**, każda standaryzowana na treningu:
  - punkty na mecz (piłka 3/1/0, koszykówka odsetek zwycięstw);
  - pozycja w tabeli jako (miejsce − 1)/(liczba drużyn − 1);
  - różnica bramek / punktów na mecz.
- **d** = średnia tych trzech wartości z, pomnożona przez n/(n+5), gdzie n = mniejsza liczba meczów obu stron w sezonie. Przy n < 3 d = 0.
- **Wejście do ratingu** jako korekta centrum: centrum strony × exp(+w·d/2), rywala × exp(−w·d/2). Suma meczu zmienia się więc tylko w drugim rzędzie.
- **Jedna waga w na model**, wybierana z siatki {0; 0,02; 0,04; 0,06; 0,08; 0,12} na tym samym treningu i po tym samym kryterium co `alpha`.
- **Puchary.** Siła ligi już jest w modelu. Sprawdzam tylko człon dwumeczu: w rewanżu różnica bramek z pierwszego meczu, wejście jak d, osobna waga z tej samej siatki. Jeśli cache nie ma powiązania meczów dwumeczu, podaję to jako niezmierzalne, bez zgadywania.
- **Ramiona do raportu:** sama `alpha`, sama tabela, `alpha` + tabela (wybrane łącznie na treningu). Każde ramię ma (a) na tym samym teście i (b) na liniach Superbetu od 10-18, z tymi samymi warunkami.
- **Instalacja:** tylko ramię, które przejdzie. Własny przełącznik w `epochs` (tabela to nowy człon SHEET) od 00:00Z dnia D, pełny replay z tym członem i refit krzywych. Daty jak wyżej: koszykówka najwcześniej 11-07, piłka najwcześniej 11-08. Tabela wymaga nowego kodu w ratingu i w replayu, więc terminy mogą się przesunąć. Wtedy podam nową datę.

### 6.1 Piłka, wybór i (a). Wyniki 2026-11-06 ok. 01:50Z

**Narzędzie.** Zamiast `measure_dependence_goals.py` użyłem własnej uprzęży `data/refit_2026-11-05_replay/item5/fb_select.py`, bo tamta nie ma tabeli ani osobnej metryki. Wielkość jest ta sama:
- czyste centra goli ratingu, jak w `fit_result_1x2_dnb_curve`: pickle historii, wyniki przyznane przy stole poza historią, siła pucharów jak zainstalowana;
- NB z `nb_r`, ta sama arytmetyka co `football_result`;
- mecze UNLINKED są pominięte.

**Okna:** trening 06-01..09-30 (91 331 meczów), test 10-01..11-04 (23 366 meczów).
**Miara:** log-loss na mecz minus ramię bazowe (×10⁻³), bootstrap po meczach.
**Skale tabeli** (trening, 305 860 meczów): pkt/mecz 0,891, pozycja 0,423, różnica bramek 2,02.

Wybór na treningu (kryterium 1X2 + DNB + DC + `goals_for`):
- sama `alpha`: ×2;
- sama tabela: w 0,12;
- `alpha` + tabela łącznie: ×1,5 i w 0,12;
- osobny krok rynków wyniku: ×2.

**Uwaga do siatek:** wszystkie wybory leżą na brzegu siatki (w 0,12, ×2). Siatek nie poszerzam, bo są zamrożone. Poszerzenie to nowa reguła na później.

**Test (a), 10-01..11-04, ×10⁻³:**

| ramię | 1X2 | DNB | DC | goals_for | suma | handicap | gole 1. poł. |
|---|---|---|---|---|---|---|---|
| sama `alpha` ×2 | −7,2 [−8,8, −5,7] | −9,1 | −12,7 | −2,0 [−4,5, +0,4] | **+10,5 [+8,8, +12,0]** | −11,1 | +1,5 [−0,3, +3,4] |
| sama tabela w 0,12 | −4,5 [−5,0, −4,0] | −5,2 | −7,6 | −7,5 [−8,2, −6,8] | −1,1 [−1,4, −0,9] | −7,4 | −5,9 [−6,4, −5,3] |
| `alpha` ×1,5 + tabela | −8,6 | −10,3 | −14,8 | −9,5 | **+3,6 [+2,7, +4,5]** | −13,5 | −5,4 |
| osobny krok ×2 (tylko rynki wyniku) | −6,6 [−8,0, −5,1] | −8,4 | −11,6 | 0 | 0 | 0 | 0 |
| osobny krok ×2 + tabela | −8,4 [−10,3, −6,6] | −10,5 | −14,7 | −7,5 | −1,1 | −7,4 | −5,9 |

Odczyt:
- **Wspólna `alpha` znów wychodzi mieszana**, jak 10-08: suma goli gorsza z przedziałem nad zerem. Ramię nie przechodzi (a), więc uruchamiam osobny krok.
- **Tabela przechodzi (a) w każdej rodzinie.** Sumy goli też są lepsze.
- **Osobny krok przechodzi (a).** Pozostałe rodziny goli mają identyczne p, co sprawdziłem: różnica 0.
- **Najlepsze ramię to osobny krok + tabela.**
- Kolejność na treningu i na teście jest ta sama.

Dalej (b): kod w SHEET i replayu, pełny replay i refit krzywych. Termin: najwcześniej 11-08.

### 6.2 Poszerzone siatki. Reguła zamrożona 2026-11-06 ok. 01:55Z, przed przeliczeniem

Polecenie: wybory z 6.1 leżą na brzegu siatek. Siatki poszerzam tak:
- waga tabeli w: {0; 0,02; 0,04; 0,06; 0,08; 0,12; 0,16; 0,20; 0,25; 0,30};
- mnożnik kroku (wspólnego i osobnego): {0,75; 1; 1,25; 1,5; 2; 2,5; 3; 4}.

Wybieram **tylko na treningu** (06-01..09-30), tym samym kryterium co w 6.1. Test 10-01..11-04 liczę raz i podpisuję jako **drugie spojrzenie na to samo okno testowe** (pierwsze było w 6.1).
- Jeśli wybór się przesunie, wartość z poszerzonej siatki idzie do replayu. Rozstrzyga wtedy (b) na liniach Superbetu od 10-18, poza próbą.
- Jeśli się nie przesunie, zostaje wybór z 6.1.

Koszykówka dostaje tę samą siatkę w od razu. Krok `bb_reg_for` jest bezwzględny: {0,04; 0,06; 0,08; 0,10; 0,12; 0,15; 0,20; 0,25}. Ta reguła jest zapisana przed pierwszym wynikiem koszykówki.

### 6.3 Poszerzone siatki: wybór na treningu, drugie spojrzenie na test (2026-11-06 ok. 02:20Z)

Wybór na treningu (kryterium jak w 6.1):

| ramię | wybór w 6.1 | wybór na poszerzonej siatce | gdzie leży |
|---|---|---|---|
| sama `alpha` | ×2 | ×2 | wewnątrz siatki, bez zmiany |
| sama tabela | w 0,12 | **w 0,30** | znowu na brzegu |
| `alpha` + tabela | ×1,5 / 0,12 | **×1,25 / 0,30** | – |
| osobny krok | ×2 | ×2 | wewnątrz siatki, bez zmiany |
| osobny krok + tabela | ×2 / 0,12 | **×1,5 / 0,30** | – |

Najlepszy wynik na treningu ma `alpha` ×1,25 + tabela 0,30: −47,6 × 10⁻³ wobec −47,3 dla osobnego kroku ×1,5 + tabeli.

Test 10-01..11-04, **drugie spojrzenie na to samo okno testowe** (×10⁻³):

| ramię | 1X2 | DNB | DC | goals_for | suma | handicap | gole 1. poł. |
|---|---|---|---|---|---|---|---|
| sama tabela 0,30 | −8,4 [−9,6, −7,3] | −9,8 | −14,4 | −14,0 | −2,2 [−2,9, −1,5] | −13,6 | −12,6 |
| `alpha` ×1,25 + tabela 0,30 | −9,9 [−11,4, −8,4] | −11,6 | −16,9 | −13,8 | +0,2 [−0,7, +1,2] | −15,5 | −12,0 |
| osobny krok ×1,5 + tabela 0,30 | −9,6 [−11,4, −7,7] | −11,6 | −16,7 | −14,0 | −2,2 [−3,0, −1,5] | −13,6 | −12,6 |

Odczyt:
- Wybór tabeli przesunął się na 0,30 i dalej leży na brzegu. Poprawa rośnie monotonicznie z w. Ten sam kierunek widać na teście.
- **(a) przechodzą trzy ramiona**, wszystkie z tabelą 0,30. W ramieniu `alpha` ×1,25 + tabela suma goli ma przedział obejmujący zero, więc nie jest gorsza z przedziałem nad zerem.
- Zgodnie z regułą 6.2 do replayu idą wartości z poszerzonej siatki. O wyniku rozstrzyga (b).

### 6.4 Waga tabeli jako parametr ciągły. Reguła zamrożona 2026-11-06 ok. 02:30Z, przed przeliczeniem

Decyzja koordynatora: do replayu idzie ramię A, czyli krok ×1,25 + tabela. Siatek dalej nie poszerzam, bo w dwa razy wylądowało na brzegu.

Reguła:
- **Dopasowanie w.** Krok trzymam na ×1,25. Parametr w ∈ [0, 1] dopasowuję metodą największej wiarygodności, tylko na treningu 06-01..09-30. Funkcja celu to kryterium wyboru: suma log-loss 1X2 + DNB + DC + `goals_for`, czyli ujemny log wiarygodności tych czterech rodzin. Szukanie złotym podziałem do 0,005.
- **Test.** 10-01..11-04 liczę raz i podpisuję jako trzecie spojrzenie na to samo okno.
- **Replay.** Dopasowane w idzie do replayu. Sędzią poza próbą jest (b) na liniach Superbetu od 10-18.
- **Flaga.** Jeśli w > ok. 0,6, tabela przejmuje pracę ratingu. To podejrzenie, że prior albo poziom ratingu jest zły, do osobnego zbadania później. Dziś nic z tym nie robię.
- **Do raportu (b), z picklem, dla rynków wyniku:** obok A także B (osobny krok ×1,5 + tabela) i sama tabela. W teście sama tabela była lepsza od A w sumach goli: −2,2 [−2,9; −1,5] wobec +0,2 [−0,7; +1,2].

**Wynik 6.4 (2026-11-06 ok. 02:45Z).**
- Dopasowane **w = 0,341**, krok ×1,25, trening n = 91 331. Wartość leży wewnątrz [0, 1] i jest poniżej 0,6, więc flagi nie ma.
- Funkcja celu na treningu (średni log-loss czterech rodzin, mniej = lepiej):

  | w | funkcja celu |
  |---|---|
  | 0 | 6,4444 |
  | 0,12 | 6,4274 |
  | 0,30 | 6,4158 |
  | 0,341 | 6,4154 (minimum) |
  | 0,5 | 6,4215 |
  | 1,0 | 6,5151 |

- Test 10-01..11-04, **trzecie spojrzenie na to samo okno**, ×10⁻³ wobec ramienia bazowego:

  | rodzina | różnica |
  |---|---|
  | 1X2 | −10,1 [−11,8, −8,5] |
  | DNB | −11,8 |
  | DC | −17,2 |
  | goals_for | −13,9 |
  | suma | +0,2 [−0,9, +1,2] |
  | handicap | −15,6 |
  | gole 1. poł. | −13,0 |

Do replayu idzie A: krok goli ×1,25 (`goals_for` 0,05, `goals_1h_for` 0,025) i tabela w = 0,341.

### 6.5 Piłka (b), rynki wyniku (1X2 / DNB / DC), z pickla (2026-11-06 ok. 03:20Z)

Metoda: `data/refit_2026-11-05_replay/item5/fb_b_results.py`.
- Dla każdego ramienia krzywe dopasowuję tak jak `fit_result_1x2_dnb_curve` / `fit_double_chance_curve` (`gate_mod.fit_curve` per klasa), na meczach replayu przed 10-18.
- Czytam je na rozliczonych liniach Superbetu 10-18..11-04, z ceną, WIN / LOSS, z własnym p ramienia dla tego meczu.
- Ramię A liczy kod produkcyjny: `football_rating.enable_form_table` i `FootballForecast.centre`.
- Linia bazowa to te same reguły bez tabeli.

Wyniki. Pierwsza liczba w komórce dryfu to liczba nóg w paśmie, dryf = trafione − pewność w pp, luka do ceny = Brier pewności − Brier ceny bez marży (×10⁻³):

| ramię | rodzina | >= 0,70 | 0,60–0,70 | luka do ceny |
|---|---|---|---|---|
| baza | 1X2 | 374: −4,0 [−8,4, +0,1] | 571: −6,6 | +26,9 [+23,5, +30,4] |
| baza | DNB | 1 116: −1,2 [−3,8, +1,0] | 967: −0,4 | +30,0 |
| baza | DC | 6 877: −1,8 [−2,7, −0,9] | 2 524: +1,7 | +11,2 |
| **A** (krok ×1,25 + tabela 0,341) | 1X2 | 404: −2,3 [−6,1, +1,5] | 957: −3,5 | **+22,8** [+19,3, +25,9] |
| **A** | DNB | 1 287: +0,9 [−1,3, +3,1] | 978: −0,5 | **+25,5** |
| **A** | DC | 7 157: −1,2 [−2,1, −0,3] | 2 083: +1,8 | **+9,8** |
| T (sama tabela) | 1X2 / DNB / DC | 570: −3,7 / 1 249: −0,2 / 7 127: −1,4 | – | +23,4 / +25,7 / +9,7 |
| B (osobny krok ×1,5 + tabela) | 1X2 / DNB / DC | 420: −1,8 / 1 305: +0,4 / 7 171: −1,1 | – | +22,9 / +26,2 / +10,3 |

Odczyt:
- **Rynki wyniku: A spełnia (b) w każdej rodzinie.** |dryf| przy >= 0,70 maleje: 1X2 4,0 → 2,3, DNB 1,2 → 0,9, DC 1,8 → 1,2. Luka do ceny maleje o 1,4–4,5 × 10⁻³. Nóg >= 0,70 jest więcej: 8 367 → 8 848 w 18 dniach.
- Luka do ceny zostaje dodatnia, z przedziałem nad zerem. Model dalej przegrywa z ceną, tylko mniej.
- T i B są w tym samym miejscu co A. W sumach goli w teście (a) sama tabela była lepsza od A: −2,2 [−2,9; −1,5] wobec +0,2 [−0,7; +1,2].
- Rodziny goli (`goals_for`, sumy) rozstrzyga (b) po pełnym replayu z `--form-table`.

## 7. Werdykt replayu z regułami (sędzia, udział, P14, P1), 2026-11-06 ok. 07:40Z

Replay skończył się o 06:39Z (1 457 004 mecze, 139,5 mln wierszy, `player_replay` OK, `share_no_team_replay` 271). Fit pełny i fit z hold-outem (cięcie 10-18) skończyły się o 07:21Z. `fit_confidence` odrzucił 51 kluczy tenisa „tylko z żywych wierszy” i zamroził je na zainstalowanych. Pomiar: `measure_swap.py` (historia 10-18..11-04 z wierszy replayu, rozliczone linie Superbetu 10-18..11-04). Pliki: `data/refit_2026-11-05_replay/rules_holdout.{md,json}`, werdykt `verdict.py`, `rules_verdict.txt`.

Jak czytam (b) reguły z sekcji 3 (zapisane przed odczytem wyników). `measure_swap` liczy (b) osobno w każdej grupie epok ledgera. Rodzina spełnia (b), gdy oba warunki zachodzą:
- suma po grupach n × |dryf| kandydata jest mniejsza niż zainstalowanych (sumuję wyniki grup, a nie ich wiersze);
- w żadnej grupie z n >= 50 kandydat nie nadobiecuje bardziej o ponad 1 pp.

Rodzina bez żywych nóg >= 0,70 nie ma czym spełnić (b), więc nie przechodzi.

**Przeszło 17 z 160 rodzin** (log-loss historii B − A × 1e-4, górna granica):

| rodzina | (a) log-loss | (b) suma n·abs(dryf), przed → po |
|---|---|---|
| cards_points_total UNDER | −17,1 (−9,9) | 50,2 → 44,7 |
| both_over_cards_points UNDER | −8,6 (−2,9) | 17,7 → 14,7 |
| cards_points_for UNDER | −5,2 (−1,5) | 33,3 → 30,2 |
| goals_total UNDER | −2,4 (−0,2) | 185,2 → 180,1 |
| goals_2h_total OVER / UNDER | −1,9 / −1,3 | 55,6 → 54,5 / 105,3 → 103,8 |
| corners_2h_total OVER | −1,9 (−0,8) | 13,3 → 13,3 |
| saves_for OVER | −1,0 (−0,4) | 18,9 → 18,0 |
| corners_for OVER / UNDER | −0,5 / −0,2 | 78,2 → 77,4 / 92,4 → 89,2 |
| goals_2h_for UNDER, goals_1h_for UNDER, goals_for OVER | −0,3 / −0,1 / −0,0 | prawie bez zmian |
| shots_on_target_for OVER, shots_on_target_total UNDER | −0,0 / −0,2 | bez zmian |
| tenis games_won_for OVER, handicap_games OVER | −0,4 / −0,3 | 102,3 → 102,3 / 76,4 → 74,6 |

Nie przeszły:
- kartki OVER: (a) z górną granicą nad progiem albo grupa gorsza o więcej niż 1 pp (od 10-24, od 10-31);
- player_shots_for OVER: od 10-24 gorzej;
- shots_total: (a);
- rodziny zawodników bez żywych nóg >= 0,70;
- player_fouls_drawn_for UNDER: nie ma zainstalowanej krzywej, więc (a) nie ma z czym porównać. Nie dodaję.

Poza kartkami UNDER (o 0,5–1 pp bliżej zera w każdej grupie) ruchy nie przekraczają 0,5 pp. To poprawka kalibracji, nie przewaga.

**Złożony plik.** Plik staged = plik zainstalowany bajt w bajt, a z kandydata podmieniam tylko `by_market_direction[f]` i `by_market_direction_line[f]` rodzin, które przeszły. Nie ruszam pul, `by_market`, krzywych klas, limitów thin ani pasów live-only (`compose_staged.py`). Ponowny pomiar (b) złożonego pliku z hold-outem (`rules_composed_live.json`, żywa baza tylko do odczytu):
- 15 rodzin piłki dalej spełnia (b), tenis handicap_games OVER też;
- **tenis games_won_for OVER już nie** (102,3 → 102,5): jego poprawa w pełnym kandydacie pochodziła z kluczy, których nie podmieniam. Wypada;
- zostaje 16 rodzin, czyli 25 kluczy;
- piłka razem: suma n·abs(dryf) 3 626 → 3 604, +120 / −186 nóg drukowanych w 18 dniach.

(a) złożonego pliku nie da się już policzyć ponownie, bo replay A nadpisuje wiersze replayu reguł. Rodzina czyta (a) z tej samej krzywej kierunku, którą podmieniam.

## 8. Koszykówka, punkt 5: wybór na rozwoju (2026-11-06 ok. 10:15Z)

Siatka z reguły 6.2: `alpha` {0,04; 0,06; 0,08; 0,10; 0,12; 0,15; 0,20; 0,25} × w {0; 0,02; 0,04; 0,06; 0,08; 0,12; 0,16; 0,20; 0,25; 0,30}, czyli 80 ramion. Walk-forward jak w `fit_sport_confidence`, hold-out to 30 dni przed 10-07, surowe p. Skale tabeli z treningu: ppg 0,331, pozycja 0,415, różnica 15,1 pkt (n 36 283). Pliki: `data/refit_2026-11-05_replay/item5/` (`bb_select.py`, `select.json`, `bb_score2.py`, `select_matched.json`).

**Problem metody.** Linie syntetyczne stoją w kwantylach modelu danego ramienia, więc ramiona dzielą z bazą tylko ok. 30% kluczy (mecz, linia). Wynik na części wspólnej (reguła zamrożona) jest obciążony. Dlatego policzyłem drugi raz: każde ramię czytam na liniach ramienia bazowego, interpolując liniowo po jego własnej drabince tego meczu (pokrycie 92–98% linii). Kryterium się nie zmienia. Tę metodę zapisałem **po** zobaczeniu wyniku z części wspólnej. Oba liczenia dają tę samą kolejność.

Wynik (log-loss × 1e-4 wobec `alpha` 0,06 / w 0, linie dopasowane):

| ramię | razem [95%] | winner | total | handicap |
|---|---|---|---|---|
| **alpha 0,04, w 0** | **−26,0 [−39,3, −12,1]** | −19,5 | −38,3 | −15,2 |
| alpha 0,04, w 0,02 | −20,1 [−32,6, −4,6] | −6,9 | −33,6 | −9,2 |
| alpha 0,04, w 0,04 | −14,0 [−27,5, +0,8] | −6,3 | −31,3 | +1,6 |
| alpha 0,06, w 0,02 | +4,8 [−0,6, +11,6] | +15,7 | +4,2 | +3,6 |
| alpha 0,06, w 0,06 | +23,4 [+12,0, +37,6] | +47,6 | +5,7 | +37,3 |
| alpha 0,08, w 0 | +31,1 [+20,0, +43,0] | +13,3 | +57,2 | +7,1 |

Odczyt:
- **Tabela sezonu w koszykówce: zmierzona i odrzucona.** Przy każdej `alpha` pogarsza wynik, monotonicznie w w, najbardziej w winner i handicapie. Najlepsze w = 0.
- **Wybrana `alpha` to 0,04**, wolniejsza od dzisiejszej. Leżała na dolnym brzegu siatki. Na polecenie koordynatora (11-06 ok. 10:15Z) poszerzyłem siatkę w dół: `alpha` {0,02; 0,025; 0,03; 0,035} przy w = 0, ten sam hold-out, oba sposoby liczenia. Wynik (× 1e-4 wobec 0,06):
  - linie dopasowane: 0,02 −11,0 [−41,5, +17,6]; 0,025 −21,9 [−47,1, +4,2]; 0,03 −22,8 [−43,7, −2,2]; 0,035 −22,5 [−39,0, −4,1]; **0,04 −26,0 [−39,3, −12,1]**;
  - część wspólna kluczy: 0,02 −11,6; 0,025 −18,7; 0,03 −14,6; 0,035 −12,8; **0,04 −23,2**;
  - w obu liczeniach **0,04 jest optimum wewnątrz siatki**. Wolniejsze kroki poprawiają sumy (do −61,7), ale psują winner i handicap.
- Następny krok według reguły 6: (a) hold-out 10-07..11-05 z własnymi krzywymi (`--before 2026-11-06`) i (b) linie Superbetu od 10-18. Oba na kopii bazy, po łańcuchu A piłki. Przełącznik najwcześniej od 11-08.

## 9. Rynki wyniku i wycinki rynków wyniku pod ramieniem A (2026-11-06 ok. 11:00–11:40Z)

Zgoda koordynatora 11-06 (reguła operatora „instaluj, co jest lepsze od dzisiejszego estymatora”): wycinki rynków wyniku (`fit_score_market_curves.py`, nieedytowany) dopasowane na wierszach 1X2 ramienia A, ta sama zamrożona reguła na wycinek co w `refit_rynki_wynikowe_2026-11-05.md` sekcja 1. Moja kopia reguły (`scoreA/verdict_slices.py`) odtwarza werdykty tamtego raportu co do jednego (0 rozbieżności, 13 „instaluj”).

**Metoda.** Pomiar (b) tamtego raportu bierze p z `07_settled.json`, a żywe p nie ma tabeli, więc dla A nie nadaje się. Tu oba ramiona biorą p z replayu as-of tych samych meczów (`scoreA/measure_A.py`, `measure_A2.py`, tylko odczyt):
- baza = krzywe zainstalowane na p dzisiejszego estymatora (wiersze `data/refit_2026-11-05_score/install`);
- A0 = krzywe zainstalowane na p ramienia A (to, co poszłoby bez refitu wycinka);
- A = refit `oos` (`--before 2026-10-18`, bramka 09-01..10-18) na p ramienia A. Pomiar idzie na `oos`. Instaluje się pełny fit (`scoreA/install`, `--before 2026-11-05`, bramka 09-18..11-05, okna jak w tamtym raporcie).
- (a) historia 10-18..11-05; (b) rozliczone linie Superbetu 10-18..11-04.

**Wyniki (dryf = trafione − pewność przy >= 0,70):**
- Wszystkie wycinki A, które przeszły własną bramkę, bez `dc_and_over`, wobec bazy: log-loss historii −0,0022 [−0,0027, −0,0017], Superbet −0,0012 [−0,0020, −0,0004], dryf Superbetu −0,51 → −0,43 pp.
- Sama reguła na wycinek przepuszcza 19 wycinków. Pozostałe czytałyby wtedy krzywą zainstalowaną na p ramienia A (A0: −0,86 pp), a całość wypada gorzej od bazy (−0,76 pp). Dlatego koordynator wybrał cały zestaw z bramką na wycinek.
- **Bramka na wycinek** (Superbet >= 0,70, n >= 50, |dryf| gorszy od bazy o > 1 pp → zostaje zainstalowana): 4 wycinki, `women:btts_or_over@-@2.5` (+1,3 → +4,7), `women:result_or_over@2@3.5` (−2,7 → −3,9), `women:result_or_under@1@2.5` (−1,6 → −3,5), `women:result_or_under@X@3.5` (+0,5 → +2,0).
- Z 130 wycinków: 5 nie przeszło bramki pełnego fitu (season_early / women), 9 to nowe klucze (poza zakresem refitu, nie dodaję). **Do pliku: 119 wycinków**. Złożony efekt (119 + reszta A0) wobec bazy: historia −0,0022 [−0,0027, −0,0017], Superbet −0,0012 [−0,0020, −0,0004], dryf −0,52 → −0,44 pp.
- Druk 10-18..11-04, przybliżenie pierwszego rzędu (żywa pewność + zmiana krzywej i p, offset / cap bez zmian): z 34 594 wydrukowanych nóg rodzin rynków wyniku 2 658 przestałoby przechodzić (18 dni), 766 zaczęłoby (14 dni). Głównie `result_or_under` / `result_or_over` @2.5 / @3.5. To w większości ruch p ramienia A, nie krzywych.

**Rynki wyniku wobec A0 (ta sama reguła, refit A sam wobec krzywej zainstalowanej na p A):**

| klucz | A0 dryf Superbet | refit A | log-loss Superbet | werdykt |
|---|---|---|---|---|
| `draw_no_bet` UNDER | −8,9 pp (n 452) | −0,1 pp (n 318) | −0,0042 [−0,0073, −0,0014] | instaluj |
| `draw_no_bet` OVER | −2,1 pp | +1,7 pp (n 872) | −0,0003 [−0,0024, +0,0019] | instaluj (klasy: brak dowodu) |
| `double_chance` OVER (+ women) | −2,8 pp | −1,1 pp (n 4 817) | −0,0014 [−0,0021, −0,0007] | instaluj |
| `dc_and_over@12@1.5` | −7,2 pp | −4,9 pp (n 369) | −0,0019 [−0,0032, −0,0008] | instaluj |
| `dc_and_over@12@2.5` | −7,6 pp | −4,5 pp (n 80) | | nie (n < 100 przy >= 0,70) |
| pozostałe `dc_and_over` | | | | brak dowodu / bramka - zostają |

Do zapisu: `draw_no_bet` UNDER na krzywej zainstalowanej pod A (A0) wobec bazy: historia −0,0 → −5,3 pp [−8,0, −2,3], Superbet −3,9 → −8,9 pp. `dc_and_over` OVER (rodzina) A0 wobec bazy: Superbet −5,0 (n 307) → −6,4 pp (n 467), historia −1,6 → −2,7 pp. „Bez refitu” z tamtego raportu dotyczyło p bez tabeli. Pod A krzywa zainstalowana obiecuje za dużo, więc refit DNB UNDER i `dc_and_over@12@1.5` wchodzi za zgodą koordynatora.

**Pickle historii przepisany o 11:10Z** (`data/cache/football_history.pkl`, nie przeze mnie): fit DC ramienia A powtórzony na nowym pliku (`scoreA/pklcheck_dc_A`) daje te same mecze (705 076), te same selekcje (1 967 946 / 24 814 / 1 992 760), krzywe i `rows.csv.gz` bajt w bajt. **Bez wpływu.**

**Tenis `games_won_for` (`by_market` + OVER), punkt 4 koordynatora:** nie spełnia (b) wobec zainstalowanej (102,3 → 102,5). Zostaje.

**Wariant tylko z regułami** (gdy A nie przejdzie): 16 rodzin (25 kluczy) + 13 wycinków „instaluj” z `data/refit_2026-11-05_score/staged`. Bez 1X2, bez `dc_and_over`, bez DNB UNDER. E2E na kopii 11-04: dzień 11-06 czyta plik zainstalowany o każdej godzinie, 11-07 plik `.next`; rusza się 2 844 pewności, wszystkie na podmienionych kluczach, 0 na innych; nogi 2 003 → 1 998.
