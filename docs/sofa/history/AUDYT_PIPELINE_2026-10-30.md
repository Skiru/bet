# Audyt przekrojowy pipeline'u `sofa` + code review — 2026-10-30 (CZĘŚCIOWY)

Stan: raport **częściowy**. Sesja główna została ucięta limitem użycia po 4 z 8
wycinków. Odebrane: SAMPLES, SHEET, CONFIDENCE / kupon / rebuild, SETTLE / ledger.
**Nieodebrane** (audytorzy mogli dokończyć, ale wyniki nie trafiły do raportu):
BOARD / RESOLVE / OFFER, sporty mierzone (SHADOW / CS2 / SPORT_*), refit /
kalibracja / epoki, infrastruktura / bridge / kanał analityków / dokumentacja.
Te cztery trzeba powtórzyć w nowej sesji.

Bramki na HEAD `1f5eb39b` (+ niezacommitowany poranny `sofa_superbet_line_evidence.json`):
pytest `tests/sofa` 6237 passed / 2 skipped (headless Chrome), ruff czysto,
mypy --strict czysto, `check_test_registry` 27 testów / 0 uwag.

Każde ustalenie pochodzi z podagenta-audytora i jest oznaczone jak u niego;
sesja główna **nie zweryfikowała ich lokalnie** (limit) — traktować jako
zweryfikowane przez audytora śladem kodu lub artefaktem, poza pozycjami
oznaczonymi PODEJRZENIE.

## Ranking (najcięższe najpierw)

### KRYTYCZNE

1. **Ledger zamrożony na pierwszym payloadzie Sofascore; re-settle przepisuje tylko `07_settled.json` i oba źródła rozjeżdżają się bez alarmu.**
   `src/bet/sofa/settle.py:619-631` (`ON CONFLICT ... DO UPDATE ... WHERE run_date = 'cache-calibration'` — wiersz live nigdy nie jest aktualizowany), `scripts/sofa/run_settle.py:1252-1300` (każdy re-settle re-graduje wszystko), `:1598-1603` (`merge_settled` podmienia artefakt), `audit_settlement.py:546-571` (7c / ledger / `13_results` czytają tylko DB), `regrade_settled.py:92-110` (`_LISTING_SOURCED`: połówki goli, gemy w secie, zwycięzca, sety nigdy nie regradowane). Sofascore przepisuje `period1/period2` dniami po meczu, a `half_time_disagrees` (`metrics.py:1457`) tego nie widzi, bo marker HT w incydentach to ten sam placeholder (PAOK–AEK 16924709).
   Pomiar: artefakt vs DB różnią się na **373 wierszach 10-16..10-28, 33 drukowane pozycje, 19 odwróconych wyników drukowanych**. Błędne w ledgerze: 15254142 Eskilstuna–Norrköping DFF `double_chance 12` WIN przy golach 82' / 90+3' = 1:1 (przegrana); 17274771 La Serna–Dellien `games_set1_total 10.5 UNDER` LOSS przy secie 4-6 (wygrana). Błędne w artefakcie: 16454836, 16404336, 16924709. 60 z 42 328 wierszy połówek goli w DB nie zgadza się z podziałem goli z incydentów (5 meczów).
   Naprawa: połówki i gemy setowe gradować z incydentów / wyników setów, odmawiać przy sprzeczności ze score; na re-settle pisać `MISMATCH` gdy nowa ocena różni się od zapisanej (jak `sport_day.grade_legs`); regrade ze źródła listingu nigdy bez drugiego zgodnego źródła.

### WYSOKIE

2. **`regrade_settled` regraduje rynki wyniku z ponownie pobranego `/event`, ale nie połówki / gemy — z tego samego przepisu.** `regrade_settled.py:100-110`. `double_chance` 15254142 odwracał się LOSS→WIN→LOSS w kolejnych dniach (`regrade_20261021T062117Z.json`, `…1024T043531Z.json`). Naprawa: jedna polityka na źródło — rynek ze score regradowany tylko gdy score się zmienił i zgadza się z incydentami.
3. **Brak dwu-graderowego `MISMATCH` dla piłki / tenisa.** `record_results.py:44-48` ma exit 1, ale jedyny producent to `sport_day.py:375` (sporty mierzone). CLAUDE.md „1 on a MISMATCH” przecenia. Naprawa: `record_results` porównuje wynik DB drukowanych kluczy z artefaktem dnia.
4. **(PODEJRZENIE co do reguły) Krecz tenisowy zwraca wszystkie rynki meczu, także już rozstrzygnięte.** `run_settle.py:216-221, 1317`. `games_total OVER 20.5` przy 22 rozegranych gemach = zwrot. 658 (10-28) / 835 (10-29) wierszy RETIRED. Źródło w kodzie: „operator 2026-10-07”, nie Regulamin. Do sprawdzenia w Regulaminie Superbetu.
5. **Strona piłkarza po transferze wybierana liczbą startów, także w szerokim oknie 20 meczów sięgającym poprzedniego sezonu.** `samples.py:1420-1437`. Przypadek 10-30, fixture 16310998 Nice–Rennes: Alidu Seidu (Rennes→Nice) ma 1 start w Nice vs 5 w Rennes z kwietnia–maja → `side_b`, 34 wiersze arkusza liczone na centrum Rennes; SETTLE gradowałby z `PLAYER_NOT_IN_SQUAD` (zwrot). Uratowało tylko `SAMPLE_CROSSES_SEASON` (209 dni); transfer letni/zimowy przechodzi. Drugi przypadek: Lautaro Mora (Huracán–Tigre). Naprawa: stronę wyznacza **najnowszy** występ (lub skład przedmeczowy); odmowa, gdy zwycięzca liczbowy różni się od najnowszego.
6. **Crash CONFIDENCE = exit 1 (PARTIAL), a rebuild drukuje poprzednie `08_confidence.json` jako dzisiejszy kupon.** `run_confidence.py:1612` (bez wrappera wyjątku), `rebuild_day.py:71,232` (stop tylko przy `>= 2`). `confidence_older_than_sheet` (`build_coupon_pdf.py:441`) nie porównuje 08 z `04_offer.json`. Naprawa: `main()` CONFIDENCE / COUPON_ASSEMBLY / PDF → `STAGE_EXCEPTION` i rc 2; `rebuild_day` traktuje krok bez `SOFA_SUMMARY` jako FAILED; 04 do strażnika świeżości 08.
7. **`derived.resolve_subject` (`derived.py:289`) jest słabszym dopasowaniem strony niż `determine_side` (`run_sheet.py:835`).** Bez marginesu 10 pkt i `_core_name`; przypadek „ca platense” (10-17) naprawiony tylko w `determine_side` — na `handicap_corners` / `most_corners` nadal ląduje na Lanús. 2 293 wierszy derived z podmiotem nazwowym 10-30. Naprawa: jeden wspólny resolver.

### ŚREDNIE

8. `rebuild_plan` 1c widzi tylko `IDENTITY_GATE_MARKER` (`rebuild_plan.py:176-179, 438-456, 778`); `AWARDED_EXCLUDED`, `SAMPLE_CONFLICT_CUT`, `PLAYER_HISTORY_ANY_TEAM`, `PLAYER_SLUG_NAME` nie piszą markera do `03_samples.json` i czytają zegar ścienny (`samples.py:120-145`). Przełącznik przesunięty w zbudowany dzień zostawia próbki na starej regule bez śladu. (Dwa audyty niezależnie.) 10-29: 5 `isAwarded` w próbkach — zgodnie z bramką daty, ale niewykrywalne z artefaktu.
9. Odmowy rynków derived znikają z `08_refusals.json`: `run_confidence.py:896` (`continue` bez `rec.refuse`), `priced_rows.py:77` (`start` nadpisuje otwarty wiersz). 37 (10-29) / 52 (10-30) wierszy zgubionych, wszystkie THIN_SAMPLE_FOR_BUILDER.
10. `carry_over_on_provider_fault` (`run_samples.py:84-106`) gubi `players` i `schedule` przeniesionego fixture'u — w dzień breakera żaden rung graczy nie jest wyceniony, a wiersze drużynowe drukują się normalnie.
11. Metryka próbki ≠ metryka SETTLE dla trzech rodzin (udokumentowane, nadal dryf): punkty kartkowe (SETTLE odrzuca kartki z ławki, próbki nie; 10-17: 6 wierszy odwróconych), 90'+karne, `half_time_disagrees` tylko w SETTLE. Potrzebny przełącznik + pomiar replay.
12. Builder z jedną nogą PUSH / na stałe niegradowalną wisi UNSETTLED w nieskończoność (`audit_settlement.py:461-483`); `13_results` pisze PENDING („czeka”) choć nic nie czeka (`coupon_results.py:200`). 10-28: B2 Prostějov–Hradec (AET): `corners_total` `EVENT_NOT_FINISHED` na zawsze.
13. Rożne / kartki / strzały meczu pucharowego z dogrywką = `EVENT_NOT_FINISHED` na zawsze (`metrics.py:1530-1536`), a Superbet rozlicza na 90'. 10-28: 381 wierszy. Bez statystyki per okres nie da się gradować — ale pozycja powinna czytać UNGRADEABLE, nie „czeka”.
14. „Finalny” cached `/event` nadpisywany na każdym re-settle (`run_settle.py:264-265`) → cache trzyma najnowszy przepis; z niego graduje `regrade_settled.detail_events` i renderuje się „do przerwy 0:0” PAOK–AEK.
15. `resettle_sweep --refetch-stat-gaps` re-graduje cały dzień dla kilkuset luk (10-28: 61 855 wierszy, ~1 000 zapytań bridge) — to ekspozycja, która produkuje pkt 1.
16. `UNFITTED_CONSTANTS` brak na ~12% wierszy arkusza: `winner_rows` (`run_sheet.py:1400`), `set_market_rows` (`:1989`), `shot_detail_rows` (`:2079`); 7 742 wierszy 10-30.
17. `config_sha` (`sheet_config.py:27-58`) pomija `sofa_football_result.json` (nb_r, 12 780 wierszy 10-30) i `sofa_cup_strength.json` (każde centrum piłkarskie) — edycja zmienia `p_central` bez `CONFIG_CHANGED`.
18. `engine.py:330` `sheet_predictive_sd` czyta `model_fixes_enabled()` z zegara ściennego — utajone (`MODEL_FIXES_FROM_UTC = None`), po ustawieniu rebuild starego dnia tenisa przecenia aces / double faults bez markera.
19. Strażniki świeżości rozbite na dwa skrypty; `build_coupon.py:492` importuje z `build_coupon_pdf.py`. Nowy WATCH sportowy działa tylko dzięki temu, że `reads.json` nowszy od 08 wymusza pełne CONFIDENCE.
20. Dryf dokumentacji: `NO_CLASS_CURVE` nieosiągalne przy line evidence (`run_confidence.py:790-803`; 0 wystąpień) — CLAUDE.md wymienia je wśród bieżących odmów; model-state.md (f) niezgodne kolejnością i etykietami „current” z `audit_ledger.EPOCH_GROUPS` (kod spójny, doc nie).

### NISKIE

- `line_evidence.py:256` nieudokumentowany krok `(key, "*")` (pula sportu w paśmie; 0 użyć na 10-29 / 10-30); `:222` pooled offset klucza dominującego zawiera jego samego (CS2).
- `build_coupon_pdf.py:1070` legacy ścieżka drukuje „kurs po narzucie” (martwa od 10-05; złamanie twardej reguły przy re-renderze starego dnia) — usunąć lub `--legacy`.
- `confidence.py:460-484` `one_sided_single` to test prefiksu stringa na `calibrated_on`.
- `derived.py:442` handicap `market_p` devig proporcjonalny przy `DEVIG_METHOD = "power"` (tylko łańcuch 1).
- `run_sheet.py:3425` `main()` łapie tylko `ValueError` / `OSError` (rc 1 zamiast 2 poza `run_pipeline`).
- `run_settle.py:440-445` `both_over_*` na linii całkowitej nigdy nie pushuje; `metrics.py:1341-1344` identity tylko strona gospodarzy; `settle.py:118` `void_deadline` 23:59:00 zamiast końca dnia.
- `samples.py:1318-1330` PODEJRZENIE: fuzzy matcher może zlać dwie różne osoby jednej strony; `run_samples.py:277` `network_requests` zawyżone; kubeł h2h z perspektywy strony A.
- Zamknięte pozycje re-anotowane przy każdym assembly (peer / price_gap / stakes) — tylko wyświetlanie.

## Zweryfikowane jako poprawne (warte zapisania)

- Cena nie wchodzi do `p_central` (każda ścieżka cenowa za `not stats_only`, test `test_stats_only_sheet`); 20 zbiegów `p_central == market_p` na dzień to ułamki sąsiadów tenisa na siatce 1/600.
- 0 obserwacji po kickoffie w 112 113 drużynowych / 62 671 graczowych; sędzia cięty na 00:00Z dnia; brak wycieku w line evidence (`fitted_from.before = 2026-10-30`).
- Oba kupony przechodzą każdą regułę druku: 0 / 1 715 (10-29) i 0 / 4 197 (10-30) naruszeń; brak `removed_by_reads` wśród drukowanych; 648 zamkniętych pozycji 10-29 śladowalne do `printed/`; builder bez ceny łączonej.
- Pozycje drukowane gradowane po `offered_odds` artefaktu; zwrot 0 u., wygrana kurs−1; `13_results` zachowuje mtime PDF; exit 0/1/2 w `run_settle` / `record_results` / `mark_coupon_results`.
- Arytmetyka Poisson / NB / push / znak handicapu / DNB / both-over / kolejność łańcucha centrum / cięcia as-of w ratingach — sprawdzone.

## Code review (jakość, skrót)

- `process_fixture` (`run_sheet.py:2339`) ~1 100 linii / 40 parametrów; `run_confidence.main` ~1 100 linii jednej pętli; `run_settle.main` ~470 linii z dispatchem powielonym w `grade_live`.
- ~400 linii martwego kodu starej epoki w SHEET / CONFIDENCE (`K_TENNIS_LADDER_CENTRE`, `disagrees_with_price`, `PDF_MAX_SINGLES`, ścieżki `not stats_only`).
- Trzy kopie reguły 15 min startu (`locked_print.kicked_off`, `coupon_sports.started`, `sport_day.KICKOFF_MARGIN`); trzy funkcje klucza pozycji (`settle._row_key`, `audit_settlement._key`, `locked_print.leg_key` — różnie traktują `None` linię); dwa resolvery strony; dwa zegary w SAMPLES (`args.date` vs dzień kickoffu).
- `RefusalRecord` wymaga parowania `start` / `refuse` ręcznie — każdy `continue` gubi wiersz.
- Brak testu „artefakt == DB dla drukowanych pozycji” (wykryłby pkt 1) i testu gracza w obu składach z nierównymi liczbami startów (pkt 5).

## Co dalej

1. Powtórzyć cztery nieodebrane wycinki w nowej sesji (ten sam brief: tylko odczyt, bez bridge'a).
2. Zweryfikować lokalnie pkt 1–3 (jeden skrypt porównujący `07_settled.json` z `sofa_settled_row` dla drukowanych kluczy 10-16..10-28) przed jakąkolwiek naprawą — to poprawka poprawności, idzie od razu z testem.
3. Pkt 4 wymaga Regulaminu Superbetu (tenis, krecz), nie kodu.
4. Pkt 5–7 to poprawki poprawności (zła strona / zły gracz / stary kupon jako nowy) — od razu, z testami.
5. Reszta po przeglądzie operatora.
