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
