# Stan pracy: kontekst terminarza piłka / tenis (plik stanu, aktualizowany po każdej fazie)

Plan: `docs/sofa/history/PLAN_KONTEKST_TERMINARZA_PILKA_TENIS_2026-11-08.md`; instrukcja:
`docs/sofa/evidence/kontekst_terminarza_2026-11-08/PROMPT_SESJI_WDROZENIOWEJ.md`;
pre-rejestracja: `docs/sofa/evidence/schedule_context_prereg_2026-11-09.md`.

## Faza bieżąca: F7 - instalacja `football_result` (egzamin: PASS tylko ta grupa; commit wyniku `d996e343`)

| faza | stan | SHA / hash / ścieżka |
|---|---|---|
| F0 pre-rejestracja + plan + materiały r1-r3 + tabela rodzin z kodu | commit `2b291085` (lokalnie; nie wypchnięty) | |
| F1 `src/bet/sofa/schedule_features.py` + `tests/sofa/test_schedule_features.py` (11 testów) | w tym samym commicie (G1: moduł przed przebiegiem) | sha256 modułu - sekcja "Hashe" niżej |
| kopia bazy | gotowa (585 s) | `data/refit_2026-11-08_schedule/sofa_copy.db` (VACUUM INTO z `file:data/sofa.db?mode=ro`, start 2026-11-09 ~00:00Z), log `vacuum.log` |
| F2 rejestrator (D4) `data/refit_2026-11-08_schedule/record.py`; próba 5 dni 2025-10-01..05 (`smoke/`, `smoke.log`) | zakończona: rc 0, 18 663 619 rekordów, 1 932 266 prognoz, 30 247 s (`full.log` SUMMARY) | potem pełny przebieg `--from 2024-07-01` -> `full/`, `full.log` |
| tenis zwycięzca: eksploracja, walidacja (spojrzenie 1/3), S1-S5, zamrożenie | zrobione | `tennis/tw_frozen.json`, `looks.md` |
| F3-F8 (piłka, wynik 1X2, gemy tenisa, egzamin, wdrożenie, push) | nie zaczęte - czekają na `SUMMARY` | |

## Hashe
- `src/bet/sofa/schedule_features.py` sha256 `70d11ec3c0627dd36d72e9140f9b7a74f364147b5898649948a140c88ae50db9`
- pre-rejestracja sha256 `a106b9900629ab3c2d3df71227f33e0313363a576d7ae18ac480b16e1f727157`

## Uwagi
- Lokalny `main` przy starcie miał 2 cudze commity niewypchnięte (e4fb587d, a1bb93e4; `origin/main` = bf72c923):
  push mojego SHA wypchnie też je - decyzja w F8.
- Rejestrator: `--players skip` (bez wierszy zawodników; `--player-share` wtedy zdjęte - zasila tylko wiersze
  zawodników); propsy przez udział dziedziczą termin drużyny, oceniane na wierszach drużyn.
- Kontrola D4: `p_central` w wierszu jest zaokrąglone do 6 miejsc - porównanie round(p,6) vs zapis, próg 1e-9.
- Bramki przy F0: `tests/sofa/test_player_sample_gates.py::test_off_the_gates_refuse_as_before` pada w drzewie
  roboczym, przechodzi na czystym HEAD e4fb587d (sprawdzone w osobnym worktree) - przyczyna w cudzych
  niezacommitowanych zmianach (`config/sofa_superbet_line_evidence.json`, slip builder), nie w ścieżkach tej pracy.
- Cudze niezacommitowane ścieżki przy starcie: `config/sofa_superbet_line_evidence.json`, `scripts/sofa/build_slip.py`,
  `src/bet/sofa/slip_builder.py`, `tests/sofa/test_slip_builder.py`, `config/sofa_settleability.2026-11-08.json`,
  `docs/sofa/evidence/ucl_kolejka_2026-11-03_04_kartki.md` - nigdy nie dodawane.

## Następny krok (dla kolejnej sesji)
Stan na 2026-11-09 ~00:30Z (zegar UTC maszyny 11-08 23:50Z):
- Próba D4 zgodna: 2 293 232 wiersze przeliczone, 0 rozbieżności, 19 min (`smoke.log`).
- Pełny przebieg `full/` w toku (`full.log`; koniec = linia `SUMMARY`). Jeśli padł: wznowić tym samym poleceniem
  (`record.py data/refit_2026-11-08_schedule/full --from 2024-07-01`, katalog `full/` usunąć przed restartem).
- Tenis zwycięzca: eksploracja S1 p=0.005, S2/S3 zdane (po usunięciu `games7d_prev`, pkt 5), walidacja (spojrzenie 1)
  Delta -0.001855 [-0.004799, +0.001177] -> S4 zdane; S5 zdane (33 894 >= 8 575); współczynniki zamrożone
  `tennis/tw_frozen.json`. Log spojrzeń: `data/refit_2026-11-08_schedule/looks.md`.
- Gotowe skrypty (scratch, `data/refit_2026-11-08_schedule/`): `fb_analysis.py` (load/explore/validate/freeze),
  `fr_analysis.py`, `tg_build.py validate|exam`, `tw_analysis.py`, `fr_build.py` (wykonany), `football_features.py`
  (wykonany, 910 985 meczów).
- Po `SUMMARY`: `fb_analysis.py load` -> `explore` -> decyzje M4 -> `validate <grupy> '<drop json>'` (<= 3 spojrzenia)
  -> `freeze`; `fr_analysis.py load/explore/validate/freeze`; `tg_build.py validate` + walidacja grupy gemów;
  potem `measure_schedule_exam.py` (do napisania wg pkt 8), commit skryptów + zamrożonych JSON, jeden egzamin.

## Doprecyzowania wykonawcze (zapisane PRZED pierwszą analizą wyników; nie zmieniają reguły (c))
1. (2026-11-09, przed eksploracją) Tenis zwycięzca: `qual` jest cechą meczu (jednakowa dla obu graczy) - jako
   różnica graczy = 0, więc w wariancie zwycięzcy nie występuje; zostaje dla serwisu. Wariant fitowany na wierszach
   z pokryciem kalendarza obu graczy; wiersz bez pokrycia dostaje p wariantu bazowego (x1). Oba warianty: per tier,
   tylko best-of-three (jak `fit_coefficients`), stan ratingu i cech na 00:00Z dnia meczu.
2. S1 tenis: permutacja kolumn gracza w obrębie (gracz, rok kalendarzowy), 200 powtórzeń, statystyka = zysk
   log-likelihood wariantu nad bazą na eksploracji (in-sample). S2 tenis: `games78` gracza z jego poprzedniego
   ocenianego meczu jako cecha opóźniona obok bieżącej. S3: znak współczynnika ważony liczbą wierszy tierów.
3. Piłka, wynik NB wiersza licznika: środek z książki rodziny `market|OVER` (`FOOTBALL_FORM_TABLE_FAMILIES`);
   gdy OVER i UNDER rynku czytają różne książki - książka OVER. Wiersze `*_total` = suma dwóch stron, każda ze swoim t
   (t strony liczone na `_for` tej samej metryki bazowej).
4. Rejestrator: `--players skip` (bez wierszy zawodników).
5. (eksploracja tenisa, przed walidacją) `games7d_prev` miał w eksploracji znak przeciwny do zarejestrowanego
   (+0.027 ważone; zarejestrowany: w dół) - wg M4 (r3: "a significant coefficient with a sign against the mechanism
   is rejected") mechanizm usunięty z grupy `tennis_winner`; grupa idzie dalej z pozostałymi. Spojrzenia w
   eksploracji są nieograniczone; walidacja jeszcze nie oglądana.
6. (przed walidacją grup gemów / serwisu) `tennis_games_sets` liczona na wierszach ratingu zapisanych przez
   rejestrator (`games_won_for`, `games_won_set1/2/3_for`; linie z `lines_for(środek bazowy)`, tylko OVER - UNDER
   jest dopełnieniem); `games_total` i `sets_total` to klucze progu 0.60 (D13) - poza przełącznikiem, więc wariant =
   baza (Delta 0), nie liczone. `set1/2_won_for`, `set_score(_not)`, `handicap_games`, `most_games` - poza zapisem
   rejestratora, raportowane jako "nieocenione w egzaminie". Tabela sąsiadów w każdym wariancie: wpisy z p wariantu
   (współczynniki: walidacja - z eksploracji; egzamin - zamrożone), reszta jak `AsOfRating` (komórki tier/płeć).
   S1-S3 wspólne z `tennis_winner` (te same cechy). `tennis_serve` (model punktowy): wariant zwycięzcy go nie
   zmienia (Delta 0 dla P5).
7. (przed analizą) `football_result`: termin goli dopasowany do zapisanych środków ratingu `goals_for`
   (książka rodziny `result_1x2|OVER`), cel = gole w 90'; ocena = log loss 1X2 (wielomianowy, jeden na mecz) z
   `football_result.result_probs(lh, la, nb_r)`; klucze symulatora / DC / DNB / wynik dokładny - opisowo.
   Odrzucenie mechanizmu wg M4 (znak przeciwny do zarejestrowanego, niezależnie od istotności) - ta sama reguła
   co w tenisie (pkt 5) dla wszystkich grup.
8. (przed jakąkolwiek walidacją piłki) Operacjonalizacja P1-P6 w `measure_schedule_exam.py`:
   - P1: Delta_g = średnia po meczach (suma po wierszach grupy); bootstrap dwukierunkowy 2000 (piłka: gospodarz x gość;
     tenis: gracz x turniej-tydzień); p jednostronne = udział replik >= 0; Holm na K zgłoszonych; górna granica
     jednostronna 95% raportowana na poziomie alfa_Holm.
   - P2: piłka - jakikolwiek współczynnik zamrożony |c| >= 0.03 (dowolna metryka grupy, own lub opp) na kolumnie,
     której wiersze narażone (kolumna = 1) to >= 2% wierszy egzaminu grupy; tenis zwycięzca - średnie |p_t - p_b|
     >= 0.01 w kubełku (`games78` >= 3 u któregokolwiek gracza / `layoff21` / `ret14`) z >= 2% meczów.
   - P3: krzywe z rozwoju per wariant: kubły EDGES `fit_confidence` na (rynek, kierunek), wartość = Wilson lo95
     (`realised_lo95`, to co czyta CONFIDENCE), kubeł >= 400 wierszy, inaczej kubeł zbiorczy grupy >= 200, inaczej
     wiersz poza P3; linie = `lines_for(środek bazowy)` obu kierunków; Delta_line na wiersz, bootstrap jak P1.
   - P4: wiersze z p skalibrowanym bazy >= 0.70; |realised - średnie p|.
   - P5: dla każdej innej grupy Delta na wiersz (suma różnic / liczba wierszy), górna granica 95% < +1e-4; warstwy:
     kobiety, terciles |supremacy| faworyta (granice z rozwoju), kontynentalne vs krajowe, runda <= 3 (strona ma
     <= 2 mecze w (rozgrywki, sezon) przed meczem), tiery tenisa; n >= 2000 wierszy, górna granica < +5e-4.
   - P6: współczynniki z P2 (|c| >= 0.03) przefitowane na egzaminie (bez ściągania) mają znak z rozwoju.
9. (2026-11-09 ~08:35Z, po eksploracji piłki, PRZED jakąkolwiek walidacją piłki / wyniku 1X2) Usunięcie mechanizmu
   wg M4 w piłce: mechanizm = kolumna kalendarza `c` (np. R1); jeśli jego zarejestrowany kierunek (S3, ważony
   odwrotną wariancją po metrykach grupy) jest przeciwny, z grupy wypadają wszystkie jej kolumny: `own_c`, `opp_c`,
   a dla R1 / `cont_prev4` także interakcja `cont_prev4_x_R1` (own i opp). Kolumny bez zarejestrowanego kierunku
   (`R4_*`, `cont_next4`, opp) zostają - na egzamin idą tylko z S1 i S2 grupy (pre-rejestracja sekcja 6).
   Grupa z S1 p >= 0.05 nie jest zgłaszana (kartki + faule: p 0.348; `fouls_1h/2h_for` po 26 wierszy na eksploracji
   - poniżej 2000, poza fitem).
10. (D10, przed walidacją piłki) Faza sezonu: przefitowana na rozwoju (`fit_season_phase.py --before 2026-01-01
   --awarded-excluded`, train_from 2024-10-01 jak zainstalowana) -> `season_phase_dev.json`; zastosowana offline do
   każdego zapisanego wiersza goli: centre = final / zapisany mnożnik fazy x exp(c_dev[rynek][faza as-of]) (faza =
   ostatni, czysto mnożnikowy krok łańcucha, `calibrate_from_cache.py:1353`), w obu wariantach; etykiety faz
   `phase_labels.py` (`season_phase.phases_by_event`, awarded excluded). Eksploracja piłki liczona przed tą zmianą
   (zainstalowana faza) - powtórzona dla goli i wyniku 1X2 po zmianie; obowiązuje powtórzona.

## Bramki zgłoszenia S1-S3 (eksploracja; `fb_explore.log`, `fr_explore.log`, `tennis/tw_explore.json`)
| grupa | S1 p | S2 lag (beta R1, beta lag) / bez mechanizmu | S3 / M4 | stan |
|---|---|---|---|---|
| goals | 0.005 | -0.0049 / 0.0022 (0.0022 < 0.00245) zdane; opp R1 na spalonych 0.0355 (SE 0.021, CI pokrywa 0) zdane | wszystkie zgodne | -> walidacja (po D10, pkt 10) |
| corners | 0.005 | 0.0067 / 0.0150 - **niezdane** | R1, dense14 przeciwne (M4) | **nie zgłaszana (S2)** |
| shots_sot | 0.005 | 0.0239 / 0.0072 (< 0.01195) zdane | R1 przeciwny -> usunięty (pkt 9) | -> walidacja |
| cards_fouls | 0.348 | - | n/d | **nie zgłaszana (S1)** |
| offsides | 0.159 | - | n/d | **nie zgłaszana (S1)** |
| football_result | 0.005 | -0.0049 / 0.0001 zdane (wiersze ratingu); bez mechanizmu wspólne z piłką | wszystkie zgodne | -> walidacja |
| tennis_winner | 0.005 | games78 -0.0974 / lag +0.0009 zdane | `games7d_prev` usunięty (pkt 5) | S4 zdane, zamrożone |
S2 dla rożnych i strzałów liczone, jak zapisano w kodzie przed wynikiem, na kolumnie R1 - stosowane dosłownie (bez
zamiany na inną kolumnę po wyniku).
11. S5 piłka (`fb_power.py` -> `fb_power.json`, tylko X egzaminu): n_req = 7.85 (1/mu + alpha) 1.75 / 0.03^2; zdane gdy
   >= 1 zachowana kolumna ma wiersze narażone >= n_req (jak w tenisie: `games78` jako największy kubeł). Wynik:
   gole n_req 16 347, own_R2 207 245 -> zdane; strzały n_req 3 762, own_R2 79 660 -> zdane; wynik 1X2 - te same
   mecze i kolumny co gole (wiersze ratingu) -> zdane. (rożne 6 153 / 44 080, kartki 2 596 / 62 810, spalone 14 109 /
   41 400 - raportowane, grupy odpadły na S1/S2.)
12. `tennis_games_sets`: X walidacji `tg_build.py validate` (526 572 linii OVER, 19 491 meczów, 511 230 linii z p
   wariantu != p bazy); S4 (`tg_score.py`, spojrzenie 1, `looks.md`): Delta -0.010219 [-0.049016, +0.027154] na
   mecz (suma ~27 linii) -> zdane. S5: te same mecze egzaminu i kubły co `tennis_winner` (33 894 >= 8 575) -> zdane.

## Lista otwartych punktów planu (kontrola kompletności, 2026-11-09 ~08:10Z)
- [x] (pkt 16) F3 opisowo (nie bramki, do raportu): kontrast w meczu (różnica stron), warstwy (kobiety, |s| terciles,
      kontynentalne / krajowe, runda <= 3), test rozrzutu chi2/df, połowy (per metryka - jest w fitach),
      tylko-prognoza vs +aktualizacja (D3 iii: termin poza aktualizacją ratingu; wariant +aktualizacja opisowo).
- [x] (pkt 16) r3 krok 8: raport X egzaminu (bez wyników): rozkłady ekspozycji, wiersze grupa x kubeł; kontrola
      odtworzenie vs żywe (ostatnie 30 dni `03_samples.json`, kubły w 3 pp).
- [x] (pkt 15, S2 niezdane) tennis_serve: budowa / eksploracja / moc (agent w tle), potem walidacja (spojrzenie zalogowane) i zamrożenie.
- [x] (pkt 13-14) walidacje: gole, strzały, wynik 1X2 (w toku, spojrzenie 1); zamrożenie piłki i 1X2.
- [x] `tg_build.py exam` (X egzaminu gemów, bez wyników).
- [x] `measure_schedule_exam.py` + test w `tests/sofa/`; krzywe P3 z rozwoju; P5 warstwy.
- [x] commit skryptów + zamrożonych JSON (SHA 87a5087f) -> jeden egzamin -> raport PL -> F7 / odrzucenie -> F8.
13. Walidacja piłki (spojrzenie 1, spec 5f910b239ced, faza z rozwoju D10): gole Delta -0.000120 [-0.000838, +0.000516]
   na 146 240 meczach -> S4 zdane; strzały + celne Delta +0.002881 [-0.002107, +0.007896] -> **S4 niezdane, grupa
   nie zgłaszana**. Strzałów nie przespecyfikowuję po wyniku (żadnego kolejnego spojrzenia dla nich).
14. Walidacja wyniku 1X2 (spojrzenie 1, spec 69bf7055a099): Delta -0.000327 [-0.000513, -0.000137] na 137 984
   meczach (log loss 1X2 na mecz) -> S4 zdane.
   Zgłoszone do egzaminu (stan na teraz): goals, football_result, tennis_winner, tennis_games_sets; tennis_serve w budowie.
15. `tennis_serve` (`serve_build.py`, `serve_analysis.py`, `serve_explore.log`, `tennis/serve_power.json`):
   eksploracja - M4 usuwa `games7d_prev` (+0.00036); S1 p 0.0100 zdane; S3 zdane; **S2 niezdane** (beta games78
   -0.00262, lag -0.00207; |lag| >= 0.5|beta|) -> **grupa nie zgłaszana**, walidacja nieuruchomiona (bez spojrzenia).
   S5 (opisowo): games78>=3 / layoff21 / qual zdane, ret14 2 002 < 2 134. Odstępstwa od dosłowności zapisane przez
   wykonawcę (filtr best-of-three z historii turnieju, delta bez wyrazu wolnego, kolumny tylko serwującego, wzór
   mocy - analog logitowy) - raport je wymieni.
   **Zgłoszone do egzaminu (ostatecznie, K = 4): goals, football_result, tennis_winner, tennis_games_sets.**
16. r3 krok 8 (`desc/exam_x_report.md|json`, tylko X): odtworzenie vs żywe (fixtures z `03_samples.json` 10-02..10-31,
   12 702 vs 25 127 meczów): największa różnica kubła R2 +2.80 pp (< 3 pp) -> zgodne. F3 opisowo
   (`desc/f3_desc.md|json`, eksploracja): kontrast w meczu, warstwy, chi2/df (NB z zapisanym alpha 0.93 / 0.96 / 0.88),
   połowy; wariant "+aktualizacja" niepoliczalny z zapisu (wymaga drugiego przebiegu rejestratora z terminem w
   `RatingBook.update`) - w raporcie jako nieliczone.
17. Egzamin przygotowany: `scripts/sofa/measure_schedule_exam.py` (+ `tests/sofa/test_measure_schedule_exam.py`, 9
   testów), dane grup `docs/sofa/evidence/kontekst_terminarza_2026-11-08/scripts/exam_groups.py` (+ kopie
   `fb_analysis.py`, `fr_analysis.py`, `tw_analysis.py`, `nbvec.py`; G1: skrypt sprawdza, że importuje tylko te kopie,
   i porównuje je oraz `frozen/*.json` bajt w bajt z commitem `--spec-sha`). NB wektorowo = silnik do 8.5e-15.
   Próba na sucho (`--mode fake`, wyniki egzaminu losowane z bazy, nic nie otwarte, `looks.md` bez zmian):
   przeszła w 391 s / 12 GB; wszystkie 4 grupy Delta > 0 (jak powinno przy wynikach z bazy) - maszyneria działa.
   Znaleziony i poprawiony w próbie: brak `competition_id` w 0.5% wierszy (warstwa kontynentalna).
   Następny krok: bramki -> commit spec (SHA) -> `measure_schedule_exam.py --spec-sha <SHA> --mode exam` raz.
18. Bramki przed commitem specyfikacji: pytest 6683 passed / 2 failed (`test_player_sample_gates.py` - te same co w F0;
   na czystym HEAD 2b291085 + moje pliki 17/17 passed - przyczyna w cudzych niezacommitowanych zmianach), ruff czysto,
   mypy --strict czysto (389 plików), rejestr testów 0 uwag.

## F5-F6 EGZAMIN (jedyny) - 2026-11-09 08:31:08Z..08:39:21Z, spec `87a5087f59796dd0efb6cd33160ac88b04120d2b`
Log: `docs/sofa/evidence/schedule_context_exam_log.md`; wynik: `docs/sofa/evidence/kontekst_terminarza_2026-11-08/exam_result.json`.
| grupa | Delta (mecz) [95%] | p jedn. / Holm | P2 | P3 | P4 | P5 | P6 | werdykt |
|---|---|---|---|---|---|---|---|---|
| football_result | -0.000223 [-0.000340, -0.000101] | 0.0005 / 0.0125 tak | tak | -0.000155 (gór. -0.000052) tak | tak | tak | tak | **PASS** |
| goals | +0.000083 [-0.000382, +0.000547] | 0.633 nie | tak | +0.000053 nie | tak | nie (kontynentalne) | tak | NOT_PASSED |
| tennis_winner | -0.001577 [-0.003220, +0.000050] | 0.031 / 0.0167 nie | tak | tak | tak | nie (CH, TOUR, mężczyźni, gemy) | tak | NOT_PASSED |
| tennis_games_sets | -0.013186 [-0.034016, +0.008766] | 0.1175 / 0.025 nie | tak | tak | tak | nie (CH, TOUR) | tak | NOT_PASSED |
"Pomogło" = tak (1 grupa). Do instalacji (F7) tylko `football_result`: zamrożone `fr_frozen.json` na drodze (ii)
(środki goli ratingu -> 1X2 / DC / DNB / wynik / symulator), przełącznik od 2026-11-10 00:00Z (najwcześniej; nigdy w
zbudowany dzień). Gole (i), tenis - bez zmian (x1).

## F7 - lista kroków (r3 13-35) tylko dla `football_result` (droga ii); stan
- [x] 13 raport skutków (`kontekst_terminarza_2026-11-08/d12/d12_report.md`: 747 wypada / 198 wchodzi, trafienia 0,7819 -> 0,7822) (egzamin + rozliczone 10-13..11-07, klucze drogi ii); progi: 4 klucze progu 0.60 symulatora
      (`team_scores_both_halves` UNDER, `half_goals_combo` OVER, `btts_any_half` UNDER, `btts_halves` OVER) WYŁĄCZONE
      z przełącznika (D13; plan pkt 8) - czytają p bez poprawki.
- [x] 14 (`SCHEDULE_TERM_FROM_UTC` = 2026-11-10 00:00Z, ustawione 09:59Z) `epochs`: `SCHEDULE_TERM`, `SCHEDULE_TERM_FROM_UTC` = dzień po commicie instalacji 00:00Z, helper, marker.
- [x] 15 (SHEET: `schedule_term.py`, `run_sheet.schedule_term_rows`; parzystość cech 0/1152 stron na kopii; fittery `--schedule-term`: DC, 1X2/DNB, wynikowe, pierwszy gol, symulator; `test_schedule_term_replay.py` 17 testów) hak tylko dla konsumentów drogi (ii) w SHEET (owinięty prognoz ratingu, oba tomy) + identyczny w replay
      fitterów; test zgodności live == replay.
- [x] 16 `config/sofa_schedule_terms.json` = zamrożone współczynniki z rozwoju (`fr_frozen.json`, NIE przefit na
      pełnej historii - plan 3.3), w `SHEET_OPTIONAL_FILES`.
- [x] 17 (`schedule_term`, `p_central_no_schedule_term`, `schedule_term_rule`; przeniesione do nóg CONFIDENCE i `07_settled.json`; NIE do `sofa_settled_row` - brak wolnej kolumny, migracja wymaga zgody operatora) pole wiersza: termin, cechy, `p_central` bez poprawki (cień odwrócony).
- [x] 18 `rebuild_plan` marker.  [x] 19 testy `rating_market_gap` / `SAME_EVENT_DEDUP`.  [x] 20 wyświetlanie (PDF / HTML / dossier / read set: "kontekst terminarza w modelu (t = ...)", `schedule_term_view.py`) + skille (football-analysis, sofa-analysis-core, tennis-analysis).
- [x] 21 testy (`test_schedule_term*.py`: 18 + 17 + 12 + 12).
- [x] 22-27 krzywe drogi (ii) przefitowane na kopii z terminem i kontrolą bez (`f7/`); `.next.2026-11-10.json` (138 kluczy; 2 zostają
      zainstalowane - nie przechodzą bramki także bez terminu) + `sofa_football_sim_curves.next.2026-11-10.json`; 22 (rebuild-cache-rows)
      niepotrzebny: żaden klucz zakresu nie pochodzi z ogólnego fitu (sprawdzone: 140 kluczy, wszystkie z `new_market_curves_fitted_from`).
      [x] 25 tabele środka: żadna z 6 nie czyta poprawionych środków; `nb_r` i frailty symulatora zmierzone - bez zmian (`step25/report.md`).
- [x] 28 line evidence: `backfill_schedule_term_p.py` -> `data/line_evidence/schedule_term_p.json.gz` (10-14..11-08), `fit_line_evidence` + `refresh_line_evidence` krok 1c. [x] 29 grupa księgi "od 11-10".
- [x] 30 rejestr `T-SCHEDULE-TERM-FORWARD` (przed D; reguła wycofania z pre-rejestracji 11).
- [x] 31 dokumentacja (CLAUDE.md, model-state.md, PIPELINE, CONFIG, RUNBOOK, REJESTR_TESTOW, raport `docs/sofa/evidence/schedule_context_2026-11-09.md`) (model-state.md, CLAUDE.md, PIPELINE/CONFIG/RUNBOOK, raport PL).
- [x] 32 bramki (6746 passed, ruff, mypy, rejestr). [x] 33 E2E na kopii 11-08 - wszystko PASS, md5 1 020 plików bez zmian (`e2e/`). [x] 34 commit `ab9df80f` (tylko własne ścieżki) - bramki na czystym worktree commita 6740 passed / 8 skipped, ruff, mypy, rejestr; `origin/main` bf72c923 bez ruchu -> push ab9df80f 2026-11-09 ~11:12Z (razem z wcześniejszymi niewypchniętymi: e4fb587d, a1bb93e4 - cudze poprawki, przeszły bramki; 2b291085, 87a5087f, d996e343).

## Po instalacji: operator przeniósł przełącznik na dziś (2026-11-09)
Operator: „włącz to wszystko co poprawiłeś na dzisiaj i przebuduj kupon”. `SCHEDULE_TERM_FROM_UTC` 2026-11-10 00:00Z ->
**2026-11-09 11:30Z**; pliki krzywych przemianowane na `.next.2026-11-09.json` (effective_from 11:30Z, treść bez zmian);
księga „11-09 mieszany”, potem „od 11-10”; poprawka backfillu: wiersz policzony przez SHEET pod przełącznikiem nie jest
poprawiany drugi raz (test). Bramki 6748 passed; commit `1304a5bc` wypchnięty. Line evidence przefitowane na 11-09 o
11:35Z z p po poprawce. `rebuild_day.py --date 2026-11-09` 11:35-11:57Z: SHEET powtórzony (marker), 8 795 wierszy piłki z
markerem, 3 473 z cieniem, p ruszyło na 2 456 (maks. 0,039); `config_sha` 9bd05a66; brak `WARN rating_market_gap`;
AUDIT_VARIANTS 0 uwag; druk `printed/20261109T115737Z`, 34 nogi zablokowane z wcześniejszych druków; notka na 259
miejscach HTML; `day_status` OK (iCloud zgodny, line_evidence 11:35Z). Kod wyjścia przebudowy 1 = PARTIAL kroków
LATE_RESOLVE / OFFER / SPORT_IDENTITY (zdrowe).
