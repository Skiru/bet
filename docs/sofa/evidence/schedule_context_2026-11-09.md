# Kontekst terminarza w prognozie piłki i tenisa - wynik i wdrożenie (2026-11-09)

**Werdykt: pomogło - tylko `football_result` (1X2 ze środków goli ratingu).** Gole (liczniki), zwycięzca tenisa i
gemy / sety tenisa zmierzone i odrzucone. Wdrożone od **2026-11-10 00:00Z** (`epochs.SCHEDULE_TERM_FROM_UTC`),
grupa ledgera „od 11-10”.

Plan: `docs/sofa/history/PLAN_KONTEKST_TERMINARZA_PILKA_TENIS_2026-11-08.md`; pre-rejestracja (zamrożona przed
jakimkolwiek spojrzeniem na wyniki): `docs/sofa/evidence/schedule_context_prereg_2026-11-09.md`; reguły wiążące:
`docs/sofa/evidence/kontekst_terminarza_2026-11-08/r3_final_review.md`; przebieg sesji:
`docs/sofa/history/STAN_KONTEKST_TERMINARZA_2026-11-09.md`.

## 1. Egzamin (jeden, reguła (c) bez zmian)

2026-11-09 08:31:08Z, spec `87a5087f59796dd0efb6cd33160ac88b04120d2b`, okno egzaminu 2026-01-01..2026-10-20, K = 4,
Holm jednostronny, bootstrap gołębnikowy (piłka: gospodarze x goście; tenis: gracz x tydzień turnieju), 2000 losowań.
Log: `schedule_context_exam_log.md`; wynik: `kontekst_terminarza_2026-11-08/exam_result.json`.

| grupa | Delta Brier / mecz [95%] | p jedn. / poziom Holma | P2 | P3 | P4 | P5 | P6 | werdykt |
|---|---|---|---|---|---|---|---|---|
| football_result | −0,000223 [−0,000340; −0,000101] | 0,0005 / 0,0125 | tak | −0,000155 (gór. −0,000052) | tak | tak | tak | **PASS** |
| goals | +0,000083 [−0,000382; +0,000547] | 0,633 | tak | +0,000053 nie | tak | nie (kontynentalne) | tak | NOT_PASSED |
| tennis_winner | −0,001577 [−0,003220; +0,000050] | 0,031 / 0,0167 | tak | tak | tak | nie (CH, TOUR, mężczyźni, gemy) | tak | NOT_PASSED |
| tennis_games_sets | −0,013186 [−0,034016; +0,008766] | 0,1175 / 0,025 | tak | tak | tak | nie (CH, TOUR) | tak | NOT_PASSED |

Grupy zatrzymane na bramkach zgłoszenia (rozwój 2024-07-01..2026-01-01, S1-S5): rożne (S2: kontrola opóźnienia
0,015 wobec < 0,0034), strzały / celne (M4 usunął R1; S4 +0,002881), kartki / faule (S1 p 0,348), spalone (S1 p 0,159),
serwis tenisa (S2: opóźnienie −0,00207 wobec beta −0,00262).

**Wszystkie spojrzenia (G5)** - `kontekst_terminarza_2026-11-08/dev_results/looks.md`: walidacja tennis_winner
−0,001855 [−0,004799; +0,001177]; tennis_games_sets −0,010219 [−0,049016; +0,027154]; goals −0,000120 [−0,000838;
+0,000516]; shots_sot +0,002881 [−0,002107; +0,007896] (S4 nie); football_result −0,000327 [−0,000513; −0,000137].
Egzamin: jedno spojrzenie na grupę (wyżej).

## 2. Co wdrożono (tylko droga (ii) `football_result`)

- **Rynki objęte** (`epochs.SCHEDULE_TERM_MARKETS`): `result_1x2`, `draw_no_bet`, `double_chance`, rynki wyniku
  (`btts_or_over`, `dc_and_over`, `dc_and_under`, `result_handicap`, `result_or_btts`, `result_or_clean_sheet`,
  `result_or_over`, `result_or_under`), `first_goal` i rynki ścieżki symulatora.
- **Nieobjęte:** cztery klucze progu 0,60 symulatora (`team_scores_both_halves`, `half_goals_combo`, `btts_any_half`,
  `btts_halves` - D13: próg zmierzono na p bez poprawki); wszystkie liczniki (gole, rożne, kartki, strzały, faule,
  spalone...), stan gry, punkty kartek, próbki, cały tenis, sporty mierzone.
- **Mechanizm:** czyste środki goli ratingu x exp(t) strony; t = człony własne i rywala (22 współczynniki zamrożone z
  rozwoju, `config/sofa_schedule_terms.json` = `fr_frozen.json`, nigdy przefit na pełnej historii): odpoczynek R1 <
  3,5 dnia, R2 3,5-5,5, R4 8,5-20,5 (po przerwie reprezentacyjnej lub nie), R5 >= 20,5 (zima / inne; R3 =
  odniesienie), mecz kontynentalny w 96 h przed (i x R1) / po, dogrywka w 7 dniach, >= 4 mecze w 14 dniach.
  Reprezentacje i brak pokrycia kalendarza: t = 0. Stałe kalendarza w `unfitted_constants`.
- **Zgodność live == replay:** 0 rozbieżności (200 losowych meczów października + pełny dzień 384 meczów; cechy 0/1152
  stron); fittery odtwarzają tę samą funkcję (`test_schedule_term_replay.py`).
- **Cień odwrócony:** wiersz niesie `schedule_term` i `p_central_no_schedule_term`; przenoszone do nóg CONFIDENCE
  (`{status, t_home, t_away}`) i `07_settled.json`. **Nie** do `sofa_settled_row` (brak wolnej kolumny - migracja
  wymaga zgody operatora); test na przyszłość czyta `07_settled.json`.
- **Wyświetlanie:** „kontekst terminarza w modelu (t = ... gosp. / ... gości)” na PDF / HTML / w dossier i read set,
  tylko gdy t zmieniło p. Skille analityków: WATCH oparty wyłącznie na odpoczynku liczy to podwójnie dla tych rynków.

## 3. Krzywe (przefitowane na kopii bazy, z kontrolą bez poprawki)

Kopia: `data/refit_2026-11-08_schedule/` (VACUUM INTO z bazy tylko do odczytu); wyniki w
`kontekst_terminarza_2026-11-08/f7_refit/`. Każdy fitter dwa razy: kontrola (bez) i termin (`--schedule-term`).

| fitter | czas kontrola / termin | przesunięcie lo95 termin vs kontrola (maks.) | bramki |
|---|---|---|---|
| podwójna szansa | 132 s / 388 s | 0,0010 | bez zmian |
| 1X2 / DNB (okno 10-15) | 140 s / 395 s | 0,0026-0,0102 | bez zmian werdyktu |
| 1X2 / DNB (okno 11-05) | 176 s / 632 s | 0,0022-0,0093 | bez zmian |
| rynki wyniku (wiersze 10-15) | 88 s / 89 s | 0,0152 | bez zmian na kluczach zainstalowanych |
| rynki wyniku (wiersze 11-05) | 75 s / 76 s | 0,0239 (13 zainstalowanych: 0,0092) | bez zmian |
| pierwszy gol | 173 s / 245 s | 0,0063 (czerwone / karne identyczne) | bez zmian |
| symulator | 660 s / 1124 s | 0,0062 (cienkie 0,021); kontrola = plik zainstalowany bajt w bajt | klucze progu identyczne |

Zainstalowane jako pliki datowane (nigdy na plik zainstalowany, nigdy w zbudowany dzień):
`config/sofa_confidence_calibration.next.2026-11-10.json` - plik 11-07 + **138** kluczy z refitu z poprawką (ten sam
fitter i okno co zainstalowane; `staged_change.schedule_term_keys`); **2 klucze zostają zainstalowane**
(`draw_no_bet|UNDER` luka −0,0234, `result_or_over@2@5.5|OVER` −0,0229 - nie przechodzą bramki także w kontroli, więc
przyczyną jest nowsza historia, nie poprawka; otwarte). `config/sofa_football_sim_curves.next.2026-11-10.json` -
nowy łańcuch datowany (`football_sim_curves.path_for`). Przeliczenie wierszy cache (krok 22, ~6 h) niepotrzebne:
żaden z 140 kluczy zakresu nie pochodzi z ogólnego fitu (wszystkie w `new_market_curves_fitted_from`).

**Tabele środka (krok 25):** żadna z sześciu tabel (waga ratingu, stan gry, rozciągnięcia, faza sezonu,
sędzia, rozproszenie liczników) nie czyta poprawionych środków - poprawiony prognostyk istnieje tylko w
`run_sheet.schedule_term_rows` i trafia wyłącznie do pięciu wyceniaczy drogi (ii); zostają bez zmian (dowód plik:linia w
`kontekst_terminarza_2026-11-08/step25/`). Dotknięte wejście ma `nb_r` = 7,586 (`sofa_football_result.json`): najlepsze r
to samo z poprawką i bez (gole 7 / 6, 1X2 100 / 15 na rozwoju / egzaminie), poza próbą nie gorzej (gole +0,00038
[+0,00031; +0,00045] z poprawką wobec +0,00039 bez; 1X2 −0,00014 [−0,00034; +0,00004] wobec −0,00008); przy 7,586
środki poprawione lepsze (log-wiarygodność / mecz: gole +0,00045 [+0,00033; +0,00056], 1X2 +0,00022 [+0,00016;
+0,00029]) - zostaje. Symulator: frailty 0,03 przy środkach poprawionych +0,00056 [+0,00042; +0,00069] - zostaje;
stałe kształtu minutowego nie badane (wymagałoby odtwarzania incydentów; krzywe symulatora przefitowane).

## 4. Dowód z linii (line evidence)

`scripts/sofa/backfill_schedule_term_p.py` -> `data/line_evidence/schedule_term_p.json.gz` (dni 10-14..11-08; 472 937
z 473 251 rozliczonych wierszy w zakresie - 314 poza rozdzielczością modelu; 123 715 linii symulatora); od fitu na
11-10 klucze zakresu czytają linie przy p z poprawką (wiersze sprzed przełącznika z backfillu, od niego własne
`p_central`); poranne odświeżenie krok 1c dopisuje nowe dni. Próbny fit `--before 2026-11-10`: każdy klucz spoza
zakresu, pasma i pule identyczne; offsety kluczy zakresu przesunięte o −0,73..+0,51 pp (np. `double_chance|OVER`
−1,21 -> −1,18; `draw_no_bet|UNDER` −5,45 -> −6,02; `first_goal|OVER` −3,12 -> −2,61). Zgodność z SHEET: t identyczne
na 3 182 meczach (10-17, 10-25, 11-08).

## 5. Skutek na rozliczonych dniach 10-13..11-07 (D12, przybliżenie)

`kontekst_terminarza_2026-11-08/d12/d12_report.md`. Pewność zakotwiczona na zapisanej nodze (dawne pliki line
evidence nadpisane), p bazowe z notek z 3 miejscami - przybliżenie, nie dokładne odtworzenie.

| | bez poprawki | z poprawką |
|---|---|---|
| nogi zakresu przechodzące wszystkie bramki | 56 708, trafione 0,7819 | 56 159, trafione 0,7822 |
| wypadają z druku | - | 747, trafione 0,7554 |
| wchodzą do druku (dolna granica, 10-21..11-07) | - | 198, trafione 0,7538 |
| `price_gap` (zakres) | 2 705, 0,6982 | 2 698, 0,6998 |
| `rating_market_gap` (single piłki) | 1 099, 0,7298 | 1 088, 0,7307 |

t != 0 na 30 923 z 57 802 nóg (średnie |t| strony 0,007, maks. 0,132). `MODEL_ABOVE_OWN_SAMPLE`: 0 zdjęć w
zakresie (wiersze drogi (ii) nie mają próbki). `SAME_EVENT_DEDUP`: zmiana wyboru w 9 grupach. Klucze symulatora w
zakresie: żadna noga nie była drukowana w okresie.

## 6a. E2E na kopii dnia 2026-11-08 (bramki i E2E przed commitem)

Bramki: pytest `tests/sofa` 6 746 passed / 2 skipped, ruff czysto, mypy --strict czysto (393 pliki), rejestr 36 testów
0 uwag. E2E (`kontekst_terminarza_2026-11-08/e2e/`): kopia `runs/sofa/2026-11-08` + kopia bazy, `SOFA_NOW` 11-08
08:00Z, przełącznik i pliki `.next.2026-11-10` podstawione w procesie, sieć zablokowana; SHEET -> CONFIDENCE ->
COUPON_ASSEMBLY -> PDF, każdy kod 0.
- `rebuild_plan`: z przełącznikiem planuje SHEET (brak znacznika), bez - „SHEET kept”.
- SHEET: 43 002 z 43 022 wierszy zakresu z cieniem (20 wierszy istnieje tylko dzięki poprawce - p blisko 0,05 / 0,95,
  BELOW_BAR; 37 szczebli odwrotnie znika), 0 z 104 895 wierszy spoza zakresu zmieniło p, cień = p bez przełącznika na
  43 002 z 43 002; klucze progu 0,60 bez zmian (9 010 wierszy); p ruszyło na 17 473 wierszach, średnio |dp| 0,0040,
  maks. 0,0363; t != 0 na 644 z 1 778 stron, zakres −0,049..+0,069. `config_sha` obejmuje `sofa_schedule_terms.json`.
  Czas SHEET: ok. 13,6 min z przełącznikiem wobec ok. 10 min bez (budowa kalendarza).
- CONFIDENCE: 5 025 nóg zakresu niesie pola, 0 spoza; krzywe z `.next.2026-11-10` (2 992 nogi o tym samym p z inną
  pewnością - wszystkie na kluczach różnych między plikami 11-07 / 11-10); 290 nóg `floor_rule` identycznych; brak
  `WARN rating_market_gap`.
- Kupon: 9 874 pozycji; notka w HTML i PDF 1 826 razy. Nogi zakresu na kuponie: 4 761 z poprawką wobec 4 737 bez
  (ten sam zegar), 129 tylko z poprawką, 105 tylko bez.
- Pliki prawdziwe: md5 1 020 plików (`runs/sofa/2026-11-08`, `config/*.json`, `data/line_evidence`, `data/cache`)
  identyczne przed i po; `data/sofa.db` - ten sam rozmiar, mtime ruszył przez żywy przebieg 11-09.
- Nie testowane: etapy sieciowe, SETTLE na nowych polach w pętli żywej (test jednostkowy jest), świeży fit line evidence
  w E2E (próbny fit w sekcji 4).

## 6. Test na przyszłość i wycofanie

`T-SCHEDULE-TERM-FORWARD` (`config/sofa_test_registry.json`, zarejestrowany 2026-11-09, okno od 2026-11-10): Delta
Briera 1X2 z `p_central` wobec `p_central_no_schedule_term`, ~158 000 meczów i min. 6 tygodni (co później - przy
~300-400 meczach dziennie ok. 13-17 miesięcy). Reguła wycofania (pre-rejestracja, sekcja 11): bez poprawki lepiej
(Delta > 0, dolna granica 95% > 0) = przełącznik wyłączony od następnego dnia 00:00Z.

## 6b. Commit i push

Instalacja: commit `ab9df80f` (2026-11-09), wypchnięty na `origin/main` (szybkie przewinięcie z `bf72c923`); przełącznik
od 2026-11-10 00:00Z - następny dzień po commicie instalacji. Wcześniejsze commity badania: `2b291085` (F0), `87a5087f`
(spec egzaminu), `d996e343` (wynik egzaminu).

## 7. Otwarte

- Wariant „+update” (aktualizacja ratingu z poprawką) - nieobliczalny w tym przebiegu; nie zgłaszany.
- Serwis tenisa: odchylenia budowy względem pre-rejestracji opisane w STAN (doprecyzowania); grupa nie zgłoszona.
- Wycinki: wynik w podgrupach to opis (P5), nie podstawa do włączania czegokolwiek osobno.
- `draw_no_bet|UNDER`, `result_or_over@2@5.5|OVER` - przestają przechodzić swoją bramkę na nowszej historii (także
  bez poprawki); decyzja o ich losie to osobny pomiar i zgoda operatora.
- `sofa_settled_row` bez pól cienia - migracja kolumny na zgodę operatora.
- Cień: ~20 wierszy dziennie przy p ~0,05 / 0,95 istnieje tylko z poprawką (bez pary w teście na przyszłość), ~37 znika - BELOW_BAR, bez wpływu na druk.
- SHEET dłuższy o ok. 3-4 min na przebieg (kalendarz terminarza).
- `rating_market_gap` czyta notę `goals_total` (bez poprawki) w 9 136 z 9 187 widoków - celowo bez zmian.
