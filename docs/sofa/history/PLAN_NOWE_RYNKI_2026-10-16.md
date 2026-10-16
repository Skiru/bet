# Plan: nowe rynki z istniejącego modelu (2026-10-16) — lista kontrolna

Worktree `../bet-wt-newmarkets`, gałąź `wt/new-markets-2026-10-16`. Żywa sesja sofa-day działa na `main` — **nie ruszamy** `runs/sofa/2026-10-16/`, `data/sofa.db` (tylko odczyt), `config/` w main.
Przełączniki: `FOOTBALL_SCORE_MARKETS_FROM_UTC`, `TENNIS_SET_COMPLEMENTS_FROM_UTC` = 2026-10-17 00:00Z (następny dzień, nie mieszamy 10-16). **Zmiana 2026-10-16: operator „Włącz od teraz” → 2026-10-16 07:46Z, 10-16 mieszany (grupa „10-16 mieszany”), `rebuild_plan` sam powtarza OFFER / SHEET.**

Legenda: [x] zrobione i sprawdzone, [~] w toku, [ ] do zrobienia, ✗ odrzucone (z powodem).

## A. Rodziny rynków (z `market_coverage.md` 10-16) — decyzja i dowód

Iteracja 1 = historia, bramka jednostronna (fit < 09-01, holdout 09-01..10-13). Iteracja 2 = linie Superbetu 10-14..10-16.
Skrypty: scratchpad `iter1.py`, `iter2.py`, `iter2_eval.py`.

| rodzina (Superbet) | klucz | it.1 | it.2 (linie) | decyzja |
|---|---|---|---|---|
| Mecz lub liczba goli / X wygra lub pow./pon. X goli | result_or_over / result_or_under | PASS (6 kluczy, luka −0,6..+0,1 pp) | 1432 nóg, −2,4 pp, ROI −3,2% | [x] wdrożone |
| Obie strzelą lub powyżej L | btts_or_over | PASS | 38 nóg, −4,4 pp | [x] wdrożone |
| X wygra lub obie strzelą / remis lub obie strzelą | result_or_btts | PASS | razem z niżej: 69 nóg, −7,8 pp | [x] wdrożone |
| X wygra lub którakolwiek czyste konto | result_or_clean_sheet | PASS | (j.w.) | [x] wdrożone |
| Handicap (2-drożny) +1.5/+2.5/+3.5 | result_handicap (nie `handicap_` — `is_derived` by go zabił) | PASS (dog_not_lose) | 236 nóg, −5,5 pp, ROI −0,9% | [x] wdrożone (+0.5 = DC, pominięte) |
| Podwójna szansa & liczba goli: 12 & pow., 1X & pon. | dc_and_over / dc_and_under | PASS | 28 nóg, +2,5 pp | [x] wdrożone |
| Tenis: X wygra seta / bez straty seta / handicap setowy ±1.5 / liczba setów 0.5 | set_score_not | PASS (+1,6 pp men, +0,5 women) | 114 nóg, −7,0 pp | [x] wdrożone |
| Handicap faworyta (−1.5…) | — | FAIL zawyża −5,2 pp | — | ✗ |
| Mecz & liczba goli, wynik & BTTS, gole & BTTS | — | FAIL zawyża / nigdy ≥0,70 | — | ✗ |
| DC & gole: 1X & pow., X2 & pow./pon., 12 & pon. | — | FAIL / n<300 / nigdy ≥0,70 | — | ✗ |
| Przedział goli (całkowity) | goals_interval | PASS | 0 nóg przechodzi bramki kuponu | ✗ (brak zysku) |
| Parzystość goli, dokładna liczba goli drużyny, przedziały drużyny | — | nigdy ≥0,70 | — | ✗ |
| Kopie (Każdy wygra seta, Dokładna liczba setów, liczba setów 1.5, …) | — | to samo zdarzenie | cena 1–3% lepsza w ~8% | ✗ (bez nowych nóg) |
| Kombinacje `;`, połowy, incydenty, gemy/punkty | — | wymaga nowego modelu | — | ✗ poza zakresem |
| Tenis: handicap DF / asów w secie, punkty w secie | — | brak krzywej / modelu | — | ✗ poza zakresem |

## B. Wdrożenie — punkty styku (każdy z testem)

Piłka (`bet.sofa.football_score_markets`):
- [x] moduł: classify / event_mask / row_p / outcome / note
- [x] klasyfikacja sprawdzona na wszystkich nazwach 10-14..16 (0 błędnych przypisań; nieczytane = odrzucone selekcje)
- [x] pary cen: marża mediana 6–9 %, max 12 %; kolizje Mecz-lub vs wygra-lub łączone po cichu (min)
- [x] epochs: switch + funkcja + rule name (2026-10-17 00:00Z)
- [x] tennis_winner.RATING_ONLY_MARKETS += MARKETS
- [x] offer.py: flaga, extra-klasyfikacja (tylko gdy nic innego nie sklasyfikowało), ciche łączenie (min), UNDER bez OVER odrzucony
- [x] run_offer.py + capture_closing.py: flaga
- [x] contracts.SheetRow: `score_market_rule`, `set_complement_rule`; sheet_row_json usuwa je przy None (bajt w bajt — złapane testem)
- [x] run_sheet.py: score_market_rows (OVER only, UNLINKED note, NOT_RATED, result_phase)
- [x] metrics: score_market_value (90 min)
- [x] run_settle.py: grading przy 0.5 (NIE przy linii goli!) — test
- [x] regrade_settled.py: ta sama ścieżka — test
- [x] CONFIDENCE: OWN_CURVE_ONLY; krzywa PER WYCINEK `market@subject@line` (confidence.curve_market; pula nigdy) — także fit_line_evidence; klasy women / season_early (leg_class); rodzina `goals` dla builderów
Tenis (`tennis_sets.SET_SCORE_NOT`):
- [x] stałe + classify_set_complement + complement_note
- [x] set_value dla SET_SCORE_NOT (1 − set_score)
- [x] kanoniczny podmiot „<gracz> 0:2” (not X 2:0 = not Y 0:2 — inaczej 2 nogi na 1 zdarzenie)
- [x] epochs switch (jedzie na TENNIS_SET_MARKETS); offer flaga; run_sheet set_market_rows OVER = 1 − p
- [x] settle (_settle_set_market parsuje subject dla SET_SCORE_NOT)
Krzywe:
- [x] scripts/sofa/fit_score_market_curves.py (piłka z wierszy cup 10-16, tenis z tennis_sets rows) + gate_report — run 1: pula per rynek ukrywała wycinki −3..−9 pp → run 2: per wycinek (92/132 PASS) → run 3: + klasa season_early: 133 krzywe piłki + 2 tenis
- [x] install_new_market_curves.py: GROUPS += 2 grupy
- [x] instalacja w worktree config (dry-run → confirm, backup config/backup_2026-10-17_score_markets, tests passed)
Weryfikacja:
- [x] testy jednostkowe (test_football_score_markets.py 84, test_tennis_set_complements.py 24) + off-scenario (wyłączone = bajt w bajt)
- [x] bramki: pytest tests/sofa 4953 passed, ruff, mypy --strict, check_test_registry (+T-SCORE-MARKETS-superbet)
- [x] E2E w scratch 10-14/15/16 (OFFER z zapisanych kursów → SHEET → CONFIDENCE → kupon → PDF/HTML → audit_coupon/variants); md5 10-15 bez zmian, 10-16 tylko żywa przebudowa
- [x] porównanie: +484/+536/+1068 nóg, 0 utraconych/zmienionych; rozliczone 1018 nóg +1,2 pp [−1,8, +4,2]
Dokumenty:
- [x] CLAUDE.md sekcja, PIPELINE.md, CONFIG.md 7.9, evidence, raport, skille analityków, audit_ledger „od 10-17”
- [x] merge do main — operator 2026-10-16 07:46Z: „Wrzucaj do maina! Włącz od teraz”

### E. Włączenie w zbudowany dzień 10-16 (07:46Z)

- [x] przełączniki 2026-10-16 07:46Z (testy przełącznika i day_flags)
- [x] `rebuild_plan`: OFFER, gdy oferta bez rungu nowych rynków; SHEET, gdy arkusz bez wiersza (wzór D2) + testy (stan, observe na plikach, zegar przed 07:46Z)
- [x] ledger „10-16 mieszany” (zamiast „od 10-16”), test, legenda
- [x] dokumenty: CLAUDE.md, PIPELINE.md, CONFIG.md 7.9, skille, verifier
- [ ] E2E poligon na aktualnym 10-16 (off/on, ten sam zegar 08:10Z)
- [ ] bramki, commit, fast-forward main
- [ ] po merge: prawdziwy `rebuild_day.py` z `main` na kopii 10-16 (zegar żywy, sieć), md5 prawdziwego dnia bez zmian
- [ ] restart pętli `capture_closing` 10-16 na nowym kodzie

## C. Odkrycia w trakcie (nie gubić)

1. `handicap_*` = rynek pochodny (`is_derived`) → krzywe nieczytane przy DERIVED_CURVES off. Nazwa `result_handicap`.
2. Wiersz SHEET przy wyłączonym przełączniku dostawał `score_market_rule: null` → nie bajt w bajt; poprawione w `sheet_row_json`.
3. Krzywa jednego rynku po wszystkich liniach: luka −0,5 pp, wycinki −3..−9 pp (ogon NB przy wysokich „lub powyżej”, remis „lub …”). → krzywe per wycinek.
4. Wczesna faza sezonu zawyża 1–5 pp w wielu wycinkach → klasa `season_early` jak 1X2/DNB.
5. Tenis: „X bez straty seta – Nie” ≡ „Y wygra seta – Tak” → kanoniczny podmiot.
6. fit_line_evidence czyta krzywą tym samym kluczem (curve_market) — inaczej offsety liczone od innej krzywej.
7. Znane, nie moje: fit_line_evidence nie stosuje leg_class (1X2 season_early) — tak samo dla nowych rynków; do zgłoszenia.

## D. Przegląd końcowy — macierz etap → kod → test

| etap | zmiana | test |
|---|---|---|
| OFFER (`offer.py`, `run_offer`) | klasyfikacja, ciche łączenie, UNDER bez OVER odrzucony, `day_flags` | `test_classify_*`, `test_switch_on_offer_*`, `test_switch_off_offer_*`, `test_day_flags_cover_every_offerfetcher_switch` |
| SAMPLES | bez próbki (rating-only) | `test_rating_only_and_never_derived`, `test_samples_never_builds_a_set_sample` (SET_MARKETS) |
| SHEET | `score_market_rows`, `set_market_rows` (1 − p), znaczniki, faza | `test_sheet_*`, `test_sheet_prices_one_minus_the_score`, `test_switch_off_sheet_has_no_such_row`, `off_identical_head` |
| CONFIDENCE | `curve_market` (wycinek), `leg_class`, pula nigdy | `test_confidence_reads_the_installed_slice_curves` (cały etap), `test_a_slice_without_its_curve_*`, `test_own_curve_or_nothing` |
| line evidence (`fit_line_evidence`) | krzywa wycinka, klucz rynku | `test_line_evidence_reads_the_slice_curve_and_keys_the_market` |
| COUPON_ASSEMBLY / PDF / HTML | `display_market` | `test_the_coupon_names_the_leg_in_superbets_words`; E2E PDF |
| capture_closing | `day_flags`, `close_record` | `test_the_closing_capture_finds_a_score_market_leg`, `test_day_flags_*` |
| SETTLE / regrade | przy 0,5, 90 min, sety | `test_settle_*`, `test_regrade_grades_like_settle` (oba pliki) |
| ledger | grupa „od 10-17” | `test_audit_2026_10_13` |
| refit (`fit_confidence`, `fit_sport_confidence`) | przenoszenie krzywych osobnych | `test_refit_carries_new_market_curves.py` (6, w tym na zainstalowanych plikach) |
| krzywe | fit + instalacja | `test_installed_set_curves_men_and_women` (SET_MARKETS ⊇ set_score_not), E2E |
| agenci / skille | verifier, scout, analysis-core, football-, tennis-analysis, sofa-pipeline | `day_flags` w przepisach sprawdzany testem |
| dokumenty | CLAUDE.md, PIPELINE, CONFIG 7.9, evidence, raport | — |

Nie testowane automatycznie (nazwane): prawdziwy OFFER z sieci (E2E szedł na zapisanych kursach), rozliczenie przez `run_settle` na żywej bazie (E2E oceniał funkcjami SETTLE w trybie tylko-do-odczytu).
