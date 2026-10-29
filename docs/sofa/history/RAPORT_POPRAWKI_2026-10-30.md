# Poprawki po weryfikacji 2026-10-29 - raport (praca 2026-10-29, dzień docelowy 2026-10-30)

Źródło zadań: otwarte punkty raportu `RAPORT_USTERKI_WERYFIKACJI_2026-10-29.md`
(A dossier a walkowery, B powtórka krzywych a `AWARDED_EXCLUDED`, C liga
drużyny po awansie / spadku, D ściąganie przewagi faworyta w pucharze).
„Jutro” = 2026-10-30 (budowa nie ruszyła: w `runs/sofa/2026-10-30/` tylko
`sport_fixtures.json` pętli).

## Co włączone i od kiedy

| zadanie | stan | od kiedy |
|---|---|---|
| A dossier bez meczów przyznanych przy stoliku | włączone - ten sam przełącznik `AWARDED_EXCLUDED` (mecze od 2026-10-30 00:00Z), tylko widok i kontrola `RYNEK:` | 2026-10-30 00:00Z (dzień meczu, zegar budowy) |
| B powtórka krzywych zna `AWARDED_EXCLUDED` | włączone w kodzie (`--awarded-excluded`); refitu nie było | od razu (narzędzia refitu) |
| C liga „w której drużyna gra teraz” | **niewłączone** - zmierzone gorzej, `RATING_DOMAIN_CURRENT_LEAGUE_FROM_UTC = None` | - |
| D ściąganie przewagi w pucharze | **niewłączone** - brak poprawy poza próbą z przedziałem bez zera; bez przełącznika | - |

Druk 10-30 zmienia się tylko o to, co i tak wchodziło od 10-30
(`AWARDED_EXCLUDED` z commita 662087a9). Nowa wersja parsera historii piłki
(`HISTORY_PARSER_VERSION` 2026-10-30.1, pole `FootballResult.knockout`)
wymusza jednorazowe przeparsowanie `football_history.pkl` (~10 min) przy
pierwszym SHEET.

## A. Dossier

`dossier.awarded_out_at` (= `epochs.awarded_excluded` dnia meczu): mecz
przyznany przy stoliku zostaje w `last_games` z `awarded: true`, wypada z
`summary` (forma, średnie, odpoczynek), `style`, `style.matchup` (podstawa
`report_check.market_findings`), stawki ligi, metryk h2h (spotkanie z flagą,
bez `metrics`), `joint_history` i znacznika „zestawienie” w KUPON html;
odbudowana tabela liczy jego punkty. Schemat dossier bez zmian (3) -
dodane pole jest opcjonalne. Dossier dni przed przełącznikiem bajt w bajt
jak dotąd (test). Testy: `tests/sofa/test_dossier.py` (cztery nowe).

E2E (scratch `data/refit_2026-10-30/dossier_{ctl,trt}`, przełącznik
tymczasowo na 10-29): Kalev - Kalju U21 (15514384) - walkower z Maardu
(2026-09-13, 0:0) oznaczony, `summary.n` 10 -> 9 po obu stronach, zestawienie
„2. połowa poniżej 3.5” 8/9 i 9/9 -> 9/10 i 10/10; Arka - Stal, Ribadesella -
Racing, Prat - Athletic: dossier identyczne. `merge_reads.py --dry-run`
raportu `2026-10-29_analiza_football_1_r1.md` na tych dossier: raport
sparsowany (1 weto, 69 odczytów), bez błędu schematu; rc 1 wyłącznie od
ostrzeżeń `UNMATCHED_READ` zawężonego zestawu (tak samo w kontroli).

## B. Powtórka krzywych

`calibrate_from_cache --awarded-excluded`: `load_cache` pomija mecz
przyznany przy stoliku (historia i cel), historia ratingu przez
`without_awarded`, historia gracza przez `admitted_football_event`; zapisane
w `replay_rules`. Ta sama flaga w `fit_goals_stretch`, `fit_count_stretch`,
`fit_closeness_stretch`, `fit_game_state`, `fit_player_stretch`,
`fit_joint_curves` (pickle `--played-cache` pamięta flagę). `prepare_refit`:
flaga `--awarded-excluded`; `AWARDED_EXCLUDED` przeniesiony z ostrzeżeń
(`UNREPLAYED_AUDIT_SWITCHES`) do odmów (`REPLAYABLE_SWITCHES`) - instalacja
przy włączonym przełączniku bez tej flagi odmawia
(`--allow-missing-replay-flag` jako jawny wyjątek). Testy:
`tests/sofa/test_refit_awarded_excluded.py`.

Skala (`scripts/sofa/measure_awarded_scale.py`, kopia bazy,
2025-10-01..2026-10-28): 6 012 wyników przyznanych w historii (3 086 w
oknie); 30 511 z 427 264 meczów (7,1%) ma taki wynik w ostatnich 10 jednej
ze stron. Rating goli bez nich, krok naprzód: +0,00011 [+0,00003; +0,00019]
log-loss Poissona na stronę (345 861 meczów; dotknięte +0,00074 [-0,00015;
+0,00164]) - nie lepiej. **Refitu dla samego B nie robiłem**; następny refit
musi mieć flagę (wymusza to `install`). Otwarte: czy rating ma je
zatrzymać (model-state (e)).

## C. Liga drużyny po awansie / spadku - zmierzone, odrzucone

`scripts/sofa/measure_rating_domain.py` (kopia bazy, bez walkowerów, krok
naprzód jak książka SHEET, bootstrap po meczach; wybór 2025-07-01..2026-06-30,
test 2026-07-01..10-28). Δ = kandydat minus obecna reguła (365 dni × 40
meczów), dodatnie = gorzej, log-loss Poissona na stronę, test:

| wariant | goals_for wszystkie | goals_for: pierwsze 20 po zmianie ligi | 1X2 pierwsze 20 | rożne pierwsze 20 | kartki pierwsze 20 |
|---|---|---|---|---|---|
| liga „teraz”, 30 dni | +0,0064 [+0,0056; +0,0072] N 86 063 | +0,0177 [+0,0156; +0,0199] N 30 681 | +0,0172 | +0,0112 | -0,0017 |
| liga „teraz”, 60 dni | +0,0063 [+0,0056; +0,0071] | +0,0179 [+0,0158; +0,0199] N 30 182 | +0,0174 | +0,0118 | -0,0017 |
| liga „teraz”, 90 dni | +0,0056 [+0,0049; +0,0064] | +0,0166 [+0,0145; +0,0188] | +0,0165 | +0,0113 | -0,0018 |
| modalna 180 d × 20 | +0,0016 [+0,0010; +0,0021] | +0,0071 [+0,0052; +0,0090] | +0,0066 | +0,0079 | -0,0013 |
| modalna 180 d × 40 | +0,0014 [+0,0009; +0,0020] | +0,0065 [+0,0046; +0,0084] | +0,0062 | +0,0073 | -0,0012 |
| modalna 365 d × 20 | +0,0009 [+0,0005; +0,0012] | +0,0035 [+0,0021; +0,0050] | +0,0025 | +0,0034 | -0,0018 |
| modalna 365 d × 80 | +0,0000 [-0,0001; +0,0001] | -0,0001 [-0,0004; +0,0002] | +0,0002 | +0,0002 | +0,0001 |
| modalna 730 d × 40 | -0,0003 [-0,0007; +0,0002] | +0,0022 [+0,0011; +0,0032] | +0,0023 | -0,0007 | +0,0008 |

Każda szybsza zmiana domeny jest gorsza; obecna reguła jest najlepsza lub
równa najlepszej. Przyczyna: współczynniki awansowanej drużyny są zarobione
w starej lidze, a opóźnienie reguły modalnej wycenia ją przez siłę lig, aż
się dostosują. Arka - Stal jako para międzyligowa to reguła działająca
zgodnie z pomiarem, nie wada. Kod zostaje (wyłączony, przetestowany:
`tests/sofa/test_rating_domain_current_league.py`); modele sportów nigdy go
nie czytają (książka `score_model` ma `current_league_domain=False`, test).

## D. Ściąganie przewagi faworyta w pucharze - zmierzone, odrzucone

`scripts/sofa/measure_cup_supremacy_shrink.py` (kopia bazy, bez
walkowerów, centra ratingu goli KNOCKOUT + LINKED_BY_STRENGTH od
2025-07-01, 14 025 meczów; gole faworyta = gole słabszego + T + k(s - T)
powyżej T; T, k z wiarygodności NB do 2026-06-30). Puchary krajowe: T 2,0,
k 0,45 (8 508 meczów). Poza próbą 2026-07-01..10-28, N 4 166:

| rynek | Δ log-loss | przy s >= T (N 908) |
|---|---|---|
| gole drużyny | -0,0020 [-0,0043; +0,0003] | -0,0091 [-0,0191; +0,0012] |
| suma goli | -0,0025 [-0,0061; +0,0011] | -0,0116 [-0,0285; +0,0047] |
| 1X2 | -0,0017 [-0,0038; +0,0002] | -0,0077 [-0,0166; +0,0010] |
| faworyt -2,5 | -0,0011 [-0,0039; +0,0018] | -0,0052 [-0,0182; +0,0076] |

Wszystkie przedziały zawierają 0 -> nie włączam (bramka: lepiej z
przedziałem bez zera). Puchary międzynarodowe (T 0,5, k 0,7, 554 mecze
testu): gorzej (+0,0020..+0,0051). Sam błąd centrum trzyma się poza próbą
(marża przy s >= 2: -0,50 [-0,68; -0,30], N 908). Liczby z 10-29 (inna
sesja, centra z historią z walkowerami) dały to samo: -0,0015 [-0,0037;
+0,0007] na 4 217 meczach.

## E2E dnia 2026-10-29 (scratch)

Kopia `runs/sofa/2026-10-29` (+ shadow / cs2 dnia) i kopia bazy, dwa
ramiona: kontrola `AWARDED_EXCLUDED = None`, wariant od 2026-10-29 00:00Z
(tymczasowa, niezacommitowana zmiana `epochs.py`, przywrócona -
`git checkout`). Etapy: `run_samples.py --event-ids` (Kalev 15514384, Arka -
Stal 17121168, Auriense - Deportivo 17259844, Prat - Athletic 17324748,
Ribadesella - Racing 17259846), `run_sheet.py` (cały dzień),
`run_confidence.py`, `build_coupon.py`, `build_coupon_pdf.py`,
`SOFA_ICLOUD_KUPONY_DIR=` puste. Wyniki:

- SHEET: 40 601 / 40 602 wierszy; p zmienione w 9 977 wierszach 148 meczów,
  **tylko piłka** (tenis bez zmian); Δp średnio -0,00001, p5 -0,0036, p95
  +0,0036, max |Δp| 0,075 (Kalev - Kalju U21: rynki łączone wynik / gole).
- Nogi drukowane w kontroli (1 634 piłki): 752 z innym p, 14 o > 0,01, 9 o
  > 0,02; najwyżej 8 przekroczyłoby próg 0,70 / x 0,90 (górne oszacowanie,
  Δp przeniesione 1:1 na pewność; m.in. Kalev - Kalju U21 „Nõmme Kalju U21
  lub poniżej 4.5” -0,047).
- Statusów druku nie porównano wprost: wariant liczony później dostał
  STALE_PRICE na wszystkim (26 337 odmów) - świadomie bez odświeżania cen
  z Superbetu.
- `day_status.py` na obu ramionach: rc 1 (WARN), te same linie, bez FAIL.
- Prawdziwe `11_coupon.json` / `KUPON_2026-10-29.pdf` / `.html`: zmienione
  w trakcie przez rebuild głównego drzewa (`rebuild_20261029T113933Z.log`,
  zapis 11:46Z, przed startem E2E); po E2E niezmienione względem stanu z
  11:46Z (md5 w `data/refit_2026-10-30/md5_real_after_e2e.txt`). Kopia
  iCloud z 11:46Z (render głównego drzewa).

## Czego nie sprawdziłem

- Pełnego `rebuild_day.py` w scratch nie puściłem: plan żądał LATE_RESOLVE,
  OFFER (263 mecze), SHADOW (15,5 h) i FIXTURE_CHECK na żywo, dwa razy;
  etapy offline zamiast niego.
- SPORT_CONFIDENCE nie był liczony w E2E; nietkniętość sportów przez C
  pokazują test i to, że C jest wyłączone (książka sportów nie zbiera
  `team_leagues`).
- Kontroli D względem ceny na rozliczonych liniach Superbetu nie robiłem
  (nic do włączenia).
- Refitu nie było, więc nie było instalacji ani E2E krzywych.

## Bramki

`pytest tests/sofa`, `ruff`, `mypy --strict`, `check_test_registry.py` -
wyniki w commicie / raporcie końcowym sesji.
