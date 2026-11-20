# Plan wdrożenia nowych rynków Superbetu - 2026-11-20

Źródło: pomiar `docs/sofa/evidence/nowe_rynki_2026-11-20.md` (z niezależną weryfikacją)
oraz cztery plany szczegółowe oparte na kodzie (plik:linia, stan `main` 7942f159).
Plany szczegółowe poprawiły szkice z pomiaru w wielu miejscach (sekcje "Korekty").
Trzy z tych korekt sprawdziłem w kodzie (oznaczone **[spr.]**).

**Nie zrobiono:** niezależnej rundy weryfikacji całego planu (przerwane przez
operatora - "SKOŃCZ"). Zrób ją jako krok 0 sesji wdrożeniowej (sekcja 7).

## 0. Zakres, kolejność, decyzje operatora

| # | rynek | co daje | przewaga | przełącznik | refit / krzywe | nakład |
|---|---|---|---|---|---|---|
| A | hokej NHL 617 / 613 / 621 / 653 "z dogrywką i rzutami karnymi" | jedyne pełnomeczowe linie goli NHL, ~44-59 nóg/dzień (górna granica) | brak (ROI -3,4%, -15% po podatku) | `HK_OT_SO_MARKETS` | tak: krzywe `total_ot`, `team_total_ot` (go) | 1,5-2 dni + refit + E2E 0,5 |
| B | tenis "N+" asy / podwójne błędy / suma (Challenger, WTA 125) | ~3 nogi/dzień | brak po podatku; model dzieli szczeble przy tej samej cenie | `TENNIS_SERVE_N_PLUS` (cień) + `..._PRINT` (druk, `None`) | nie (krzywe punktowe są); backfill dowodów | 2-2,5 dnia |
| C | piłka: handicap połowy (+L) i podwójna szansa połowy | ~130 nóg / ~55 meczów dziennie (przed dowodami) | brak (cena lepsza, 1H przeszacowuje) | `FOOTBALL_SIM_HALF` | tak: staged `sofa_football_sim_curves.next.<D>.json` (go) | ~2,5 dnia |
| D | siatkówka 230059 "1.Set/Mecz" | ~4-5 nóg/dzień (weekendy) | brak (plus = efekt faworyta) | `VB_SET1_MATCH` | nowy plik `sofa_vb_set1_match_curves.json` (go) | ~1,5 dnia |

Wyłączone (zmierzone na minus, nie planowane): CS2 "Liczba dogrywek" i rundy
±0,5, kosz "N+" i double-double, reszta siatkówki. Uzasadnienie: pomiar, sekcja 2.

Kolejność: D -> A -> C -> B (od najmniejszego). Każdy rynek to osobny commit z
własnym przełącznikiem. **Rekomendacja:** jeden wspólny dzień D 00:00Z dla
A / C / D, żeby księga dostała jedną grupę "od D" zamiast trzech. B najpierw w
cieniu, druk dopiero po teście w przód.

Decyzje operatora (przed sesją wdrożeniową):
1. Czy dodawać rynki bez przewagi (więcej nóg, nie lepszy wynik) - A, C, D.
2. Dzień D. Domyślnie 00:00Z dnia po commicie; nigdy w zbudowany dzień bez polecenia.
3. Go na refity / staged krzywe: A (hokej), C (symulator), D (siatkówka).
4. B: cień + test w przód (rekomendacja) czy od razu druk; progi testu (n = 300).
5. Ekspozycja: `max_positions_per_match` dziś wyłączone - A daje 6-13 nóg na mecz NHL,
   C ~2,3 na mecz. Zostawić czy ograniczyć.
6. A: filtr lig do krzywych - rozgrywki bez remisów (domyślnie) czy tylko NHL.
7. C: podwójna szansa połowy jako osobny klucz bez "12" i bez ±3,5 (rekomendacja);
   człon terminarza poza zakresem (rekomendacja, nie ruszać `T-SCHEDULE-TERM-FORWARD`).
8. B: kobiety (WTA 125) nigdy nie wydrukują - `one_sided_single` wymaga źródła
   `market:` / `line:`, a noga klasy ma `tennis_women:market:`. Zostawić czy osobny
   przełącznik.

## 1. Zasady wspólne (obowiązują każdy rynek)

- Wszystko, co zmienia druk: przełącznik w `bet.sofa.epochs` (`datetime | None`,
  `None` do zgody), czytany po dniu rekordu / budowy i zegarze budowy
  (`_audit_1023_on`, `epochs.py:3240`), znacznik na wierszu / nodze, test.
- Przy wyłączonym przełączniku wynik **bajt w bajt** jak dziś (test w każdym rynku):
  snapshoty, `04_offer`, `unmapped_prices`, `05_sheet`, nogi.
- Po włączeniu rynek znika z `unmapped_prices` (przechodzi do snapshotów / ofert).
- Czytelnicy ceny poza pipeline'em muszą dostać tę samą flagę: `build_slip.py`
  (świeża cena /kupon, ~:241-249 i :367), `capture_closing.py`, `verify_legs.py`
  (przez `offer.day_flags` dla piłki / tenisa; dla sportów przez `parse_event`).
  Bez tego noga z /kupon dostaje FRESH_GONE.
- Krzywe tylko z historii, nigdy z naszych dni. Refit tylko na kopii bazy:
  `sqlite3 data/sofa.db "VACUUM INTO 'data/refit_<D>_<rynek>/sofa.db'"`. Skrypty
  sportów czytają bazę z `SOFA_DB_PATH` (nie mają `--db-path`).
  **`fit_sport_confidence.py` bez `--out` zapisuje do zainstalowanego
  `config/sofa_sport_confidence_calibration.json` [spr.: :565, :612] - `--out`
  obowiązkowe.** Nowe krzywe zawsze jako staged / osobny plik z `effective_from`,
  nigdy edycja pliku czytanego przez zbudowane dni.
- Dowody liniowe: klucz z krzywą od dnia 1 czyta pulę sportu z offsetem; własny
  offset od 50 linii / 30 meczów; klucz bez krzywej = `NO_LINE_EVIDENCE` do 50 linii
  / 15 meczów (`line_evidence.py:76, 99`). Backfill z `unmapped_prices` tam, gdzie
  plan go przewiduje.
- `leg_identity` (SAME_EVENT_DEDUP) i `leg_relations` (buildery) - każdy plan
  wymienia swoje tożsamości; testy z logiki, nie z rozliczonych wierszy.
- Nazwy Superbetu (`superbet_names`) i `market_coverage` - każdy rynek.
- Księga: `scripts/sofa/audit_ledger.py` - `EPOCH_GROUPS` (:148) + stała
  `*_EPOCH_FROM_DATE` + gałąź na szczycie `epoch_group` (:328); dzień mieszany tylko
  na polecenie operatora.
- Dokumenty: CLAUDE.md, `.claude/skills/sofa-pipeline/references/model-state.md`
  (a/c/f), `docs/sofa/PIPELINE.md`, `docs/sofa/CONFIG.md`, rejestr
  `config/sofa_test_registry.json` + `docs/sofa/REJESTR_TESTOW.md`
  (`check_test_registry.py` wymaga, by skrypt z pola `evaluation` istniał), skill
  analityka danego sportu (agenci nie czytają CLAUDE.md; zmiana skilla działa od
  następnej sesji).
- Bramki przed commitem: `pytest tests/sofa -q`, `ruff check src/bet/sofa
  scripts/sofa`, `mypy --strict --no-incremental src/bet/sofa scripts/sofa`,
  `check_test_registry.py`.
- E2E zawsze na kopii dnia (`SOFA_RUNS_DIR` w scratchu, `SOFA_ICLOUD_KUPONY_DIR=`,
  kopia bazy), md5 prawdziwych plików przed i po - identyczne. Wariant "wł." w
  scratch worktree ze stałą przełącznika przesuniętą, nigdy commitowaną.
- Git: `git add <ścieżki>` (nigdy `-A`), nigdy `git stash`, commit na `main`, push
  tylko zweryfikowanego SHA.

## 2. A - Hokej NHL z dogrywką i karnymi

**Korekty szkicu (z kodu):**
- Wycena gotowa: `score_model._hockey` już przy remisie dolicza gol zwycięzcy
  dogrywki z `hk_ot_strength` 0,5 [spr.: `score_model.py:1120-1128`, :616]. Zmienia
  się tylko tabela rynków i `shadow._pair`; `DbForecaster.probability` bez zmian.
- Filtr lig do krzywych na poziomie rozgrywek (nie odrzucanie remisów mecz po meczu
  - selekcja po wyniku); mecze tych rozgrywek bez przerzedzania `--max-games`.
- 613 ±0,5 odrzucać przy parsowaniu (= zwycięzca 630, czytany).
- Ocena "incl" z tercji + `winnerCode`, nie z `t1_full` (3 mecze z karnymi zapisane
  jako `overtime` 1/0; `build_result` dopuszcza karne bez +1 w `current`).
- `leg_relations._shadow_spec` przeszukuje tylko `MARKETS` / `DERIVED_MARKETS`
  (:459-469) - dopisać nową tabelę.

**Kroki:**
1. `epochs`: `HK_OT_SO_MARKETS = "hk_ot_so_markets"`, `HK_OT_SO_MARKETS_FROM_UTC`,
   `hk_ot_so_markets(date, build_at)` (wzór `BASKETBALL_PLAYER_V2`, :2268-2281);
   znacznik `hk_ot_so_rule` na rekordzie snapshotu i nodze.
2. `shadow.py`: tabela `HK_OT_SO_MARKETS` - 617 -> `total_ot` (scope `incl`),
   613 -> `handicap` (`incl`; ten sam klucz co 604, tożsame na każdej czytanej linii),
   621 / 653 -> `team_total_ot` (`incl`, T1 / T2); `spec_of`; `parse_line` /
   `parse_event` / `reads_market` z `ot_so=False`; gałąź `incl` w `_pair`
   (suma tercji + 1 dla `winner` przy `overtime`; `final_only` analogicznie).
   Wywołania: `run_shadow.py:210-226`, `build_slip.py:244-247`.
3. `superbet_names.SPORT_MARKETS["hockey"]`: 4 nazwy z ekranu;
   `market_coverage._reader_reads` + nota `hk.ot_so_scope`.
4. `sport_confidence`: `HK_OT_SO_ALLOWED`, `allowed_markets` / `family_of(...,
   ot_so)`; `run_sport_confidence.build_sport` przekazuje flagę i znacznik;
   `settled_shadow_rows` z `ot_so` (bez tego brak dowodów liniowych).
5. Krzywe: `HK_OT_SO_HISTORY_MARKETS = (617, 621, 653)` (613 = krzywa `handicap`),
   stała drabina linii (617: 2,5-9,5; 621 / 653: 0,5-5,5), `ot_always_competitions`
   (≥ 100 meczów, żaden bez zwycięzcy), `fit_sport_confidence.py --hk-ot-so on
   --markets 617,621,653 --out data/refit_<D>/hockey_ot.json`; skrypt składa
   `config/sofa_sport_confidence_calibration.next.<D>.json` = kopia
   `.next.2026-11-07.json` + 4 klucze + `staged_change`, `effective_from` = D.
   Kontrola wrażliwości: fit tylko NHL. Sprawdzić, czy w dniu D nie ma nowego
   przełącznika hokeja do odtworzenia.
6. `leg_identity`: wektor stanów wyniku dla `total` / `total_ot` / `team_total` /
   `team_total_ot` (okres 0) - 617@nieparzyste k ≡ 623@k; 613@h ≡ 604@h działa już
   przez rodzinę `handicap`. `leg_relations`: `_shadow_spec` + `_shadow_period`
   (`incl` = regulamin + OT).
7. Uwaga na kolizję kluczy bez `market_id` (`graded_odds`, `coupon_sports.sport_key`,
   `locked_print.leg_key`): asercja rozłączności 604 / 613 albo `market_id` w kluczu.
8. Księga "od D"; rejestr `T-HK-OT-SO-calibration` (≥ 300 nóg / ≥ 60 meczów,
   realizacja - pewność w ±3 pp); CLAUDE.md "Measured sports" + "One event, one
   leg"; model-state (b): każda zmiana R3 / remisu wymaga ponownego pomiaru `_ot`.

**Testy** (`tests/sofa/test_hk_ot_so_markets.py`): off bajt w bajt; parsowanie
prawdziwego payloadu NHL; 613 ±0,5 -> None; `reads_market` wyprowadza z unmapped;
ocena incl: Ended / AET / AP z `penalties` / AP jako `overtime` / karne bez +1 /
defekt 14198584; incl ≡ reg na nieparzystym k i |h| ≥ 1,5 (siatka stanów);
p incl = p z `t1_full` na symulacjach; rodziny tylko pod przełącznikiem; wiersze
rozliczone od dnia przełącznika; historia tylko z lig bez remisów i bez
przerzedzania; plik staged różni się tylko 4 kluczami; tożsamości; relacje;
nazwy; świeża cena w /kupon; znacznik; grupa księgi.

**E2E:** stare snapshoty nie mają 617 (brak specyfikatorów w unmapped) - E2E na
kopii dnia wdrożenia: żywy `run_shadow.py` do kopii, `run_sport_confidence.py`,
`rebuild_day.py`. Oczekiwane: ≤ 44-59 nóg/dzień, ~6 na mecz (max 9-13), 617 ~45%,
613 ~25%, 621 + 653 ~30%; rozliczenie D-1 zgodne z Superbetem.

**Ryzyka:** skorelowana ekspozycja; nogi NHL wchodzą wieczorną przebudową (ROI
mierzone na kursie przed startem); błąd remisu (-5,3 pp) znosi się przypadkiem;
bez refitu drukuje się tylko 613.

## 3. B - Tenis "N+" (asy, podwójne błędy, suma)

**Korekty szkicu:**
- Dwa przełączniki: cień (mapowanie, wycena, bramki, zapis nóg bez druku) i druk
  (`None` do testu).
- `_add_price` (`offer.py:381-424`) bierze niższy kurs - kursy "N+" w osobnym
  słowniku, dołączane tylko gdy klucza nie ma (jak `score_odds`).
- SHEET pomija rung bez metryki w `03_samples` (`run_sheet.py:2994`) - potrzebne
  SAMPLES dla meczów z "N+" i znacznik `serve_ladder_rule`.
- Regex: "asy + podwójne błędy" nie może dać zawodnika "asy +"; goła nazwa
  "Podwójne błędy" to też rynek "kto więcej" (81 wyborów 11-10..11-19).
- Zablokowane szczeble to nie tylko "1+" (OFFER już je pomija, `offer.py:556`).

**Kroki:**
1. Nowy `src/bet/sofa/serve_ladder.py`: `classify(market, selection, sbv,
   listing_names)` -> `(key, subject, N-0.5, "OVER")`; zakres `^([12])\.\s?set - `,
   sufiks od najdłuższego ("asy + podwojne bledy", "asy", "podwojne bledy"),
   podmiot pusty = `_total`, inaczej dokładnie jedna nazwa listingu; wybór
   `^(\d+)\+$` == N z `offer.parse_line(sbv)` (prefiks "S-" zgodny z setem); klucz
   musi należeć do `epochs.TENNIS_POINT_MODEL_MARKETS`.
2. `offer.classify_odd(..., tennis_serve_n_plus=False)` po gałęzi `tennis_sets`;
   `OfferFetcher`: osobny `n_plus_odds`; `day_flags["tennis_serve_n_plus"]`.
3. `epochs`: `TENNIS_SERVE_N_PLUS(_FROM_UTC)` i `..._PRINT_FROM_UTC = None`; druk
   wymaga cienia i `tennis_point_model`.
4. `PricedRung.ladder_format` (`contracts.py:291`), `SheetRow.serve_ladder_rule`,
   przeniesienie do 07_settled (`run_settle.py` `row_extras`) i na nogę.
5. Cień w `run_confidence.py` (~:1092-1106): noga ze znacznikiem bez druku idzie do
   `shadow_serve_n_plus` w `08_confidence.json` (odmowa `SERVE_N_PLUS_SHADOW`) i do
   dopisywanego `runs/sofa/<d>/shadow_serve_n_plus.jsonl` (`built_at_utc`); przy
   druku - nigdy w builderze.
6. `rebuild_plan`: (a) etykiety "N+" w `unmapped_markets` przy włączonym
   przełączniku -> OFFER; (b) rung "N+" bez metryki w próbkach -> SAMPLES / SHEET
   `--event-ids`; drugi plan bez kroku (test).
7. Dowody liniowe: prefiks klucza `n_plus:` (`fit_line_evidence.sheet_rows` :216 i
   odczyt `run_confidence.py:804-807`); pula sportu nie zabrudzona (wiersze modelu
   punktowego wyłączone od 11-08). Backfill `scripts/sofa/backfill_serve_n_plus_lines.py
   --from 2026-10-20` -> `data/line_evidence/tennis_serve_n_plus_lines.jsonl.gz`.
8. Krzywe bez zmian: `tennis_point_curves` po `market|OVER`, źródło `market:`
   spełnia `OWN_CURVE_SOURCES`. Graderzy bez zmian.
9. `superbet_names`: "[S. set - ]{gracz} asy" / "N+" (nigdy "powyżej 13.5");
   `market_coverage.TENNIS_RULES`: `tn.serve_n_plus`.
10. `day_status`: WARN, gdy przy włączonym przełączniku w `unmapped_markets` są
    etykiety "N+" (zmiana formatu).

**Test w przód `T-TENNIS-SERVE-N-PLUS-FORWARD`** (zamrożony w commicie przed
pierwszym dniem cienia, `PROTOCOL.md` z sha, skrypt
`scripts/sofa/measure_serve_n_plus_forward.py` ze strażnikiem sha jak
`measure_price_edge.py`): jednostka = pierwszy rekord cienia nogi przed startem;
n = pierwsze 300 nóg i ≥ 90 meczów; M1 realizacja - pewność, M2 ROI po kursie, M3
zwrot nóg cienia minus zwrot wszystkich wierszy "N+" przy kursach 1,087-1,30;
PASSED = dolna M1 ≥ -0,05 i M2 ≥ -0,05 i dolna M3 > 0; FAILED = górna M1 < -0,03
albo górna M2 < -0,05; reszta NOT_PASSED; STOPPED_FUTILE bez n do 2027-04-30.
PASSED = rozmowa z operatorem, nigdy automatyczny druk.

**Kolejność commitów:** A kod (oba przełączniki `None`, testy, backfill, skrypt
oceny) -> E2E -> C zamrożenie (protokół, rejestr, cień od D0+1 00:00Z) -> ocena ->
decyzja o druku (od następnego dnia 00:00Z, grupa księgi dopiero wtedy).

**Testy** (`tests/sofa/test_tennis_serve_n_plus.py`, rekordy z
`runs/sofa/2026-11-19/unmapped_prices/20261119T061204.444294Z.jsonl.gz`, mecz
17537878 Gojo - Basavareddy): przełączniki; `day_flags`; 12 szablonów -> klucze
(np. "Asy" "19+" "19" -> `aces_total` 18,5 OVER; "1. set - Nishesh Basavareddy
podwójne błędy" "2+" "1-2" -> `double_faults_set1_for` 1,5); odmowy ("kto więcej",
niezgodne N, "3. set", podmiot spoza listingu, "asy +" nigdy podmiotem); klucze w
modelu i metrykach; off = unmapped; stary format bez zmian; brak scalenia z
dwustronnym; `04_offer` off bajt w bajt; próbki, SHEET, SETTLE z markerem; klucz
dowodów; backfill; `one_sided_single` (kobiety odpadają); cień; nazwy; pokrycie;
rebuild_plan idempotentny; protokół testu.

**E2E:** kopia 11-19 (`SOFA_NOW` 06:20Z): +~30 meczów z rungami, 0 zapytań SAMPLES
(podejrzenie: asy z tego samego `/statistics` - potwierdzić licznikiem), `legs` bez
zmian, cień 0-20 nóg; raportować THIN_SAMPLE / ALL_ZERO_SAMPLE na "N+" (pomiar ich
nie liczył - 85 nóg to górna granica).

## 4. C - Piłka: handicap połowy i podwójna szansa połowy

**Korekty szkicu:**
- **Misgrade:** `run_settle._settle_sim_market` (:384-394) ocenia przy linii wiersza;
  `result_1h_handicap` @1,5 z wartością 1,0 dałby LOSS przy każdej wygranej. Ocena
  wskaźnika przy `fsm.LINE` (0,5), linia handicapu idzie do `sim_value`.
- Łańcuch symulatora nie zna linii (`path_spec`, `path_holds`, `sim_value`,
  `SimPricer.p`, `fit_football_sim_curves` `day_lines` / `_price_job` / `SUBJECTS`) -
  dodać parametr `line`.
- Podwójna szansa połowy jest dwustronna (dopełnienie w "X.połowa - 1X2") i ma inną
  cenę niż handicap +0,5 - **osobny klucz**, nie scalanie (`_add_price` wziąłby
  niższą cenę z cudzym rynkiem).
- Nie dopisywać kluczy do `FOOTBALL_SIM_MARKETS` - zmieniłoby `SCHEDULE_TERM_MARKETS`
  i populację zarejestrowanego `T-SCHEDULE-TERM-FORWARD`. Osobny
  `FOOTBALL_SIM_HALF_MARKETS`; `fsm.MARKETS = BASE | HALF`.
- `--schedule-term` nie wyłącza nowych kluczy sam (`EXCLUDED` z
  `sofa_schedule_terms.json`) - dopisać `EXCLUDED |= fsm.MARKETS -
  SCHEDULE_TERM_MARKETS`.
- Backfill dowodów tnie dni od `FOOTBALL_SIM` (`football_sim_curves.py:199`) -
  dzień włączenia per rynek.
- Skrypt krzywych nie ma `--awarded-excluded` (przyznane odpadają już w pickle'ach) -
  zapisać `fitted_from.awarded_excluded: true`.

**Kroki:**
1. Klucze: `result_1h_handicap` / `result_2h_handicap` (subject strona z +L, `line`
   ∈ {0,5; 1,5; 2,5}, OVER = "B (L)", UNDER = "A (-L)" tylko cena do marży) oraz
   `result_1h_dc` / `result_2h_dc` (subject "1X" / "X2", OVER = DC, UNDER = cena
   pominiętego wyniku połowy z "X.połowa - 1X2"); "12", ±3,5 i linie całkowite
   nieczytane. Żaden klucz z prefiksem `handicap_` / `dc_and_`.
2. `epochs`: `FOOTBALL_SIM_HALF`, `FOOTBALL_SIM_HALF_FROM_UTC = None`, marker,
   `FOOTBALL_SIM_HALF_MARKETS`, `football_sim_half(date, build_at)` (wymaga
   `football_sim`); podłoga 0,70.
3. `contracts.py` pole `football_sim_half_rule`; `run_sheet.py` flaga + marker
   (`stamp_marker`, `AUDIT_MARKER_FIELDS`); `rebuild_plan`
   `sheet_football_sim_half` / `offer_has_sim_half` / `sim_half_offer_stale`.
4. OFFER: `football_sim_markets.classify(..., half, line_text)` - `^[12]\.polowa -
   handicap$` (nie "handicap 1x2"), selekcja `(team) ((-)L)`, kontrola
   `specialBetValue`, strona przez `_side` (F25); `^[12]\.polowa - podwojna
   szansa$`; nowe `half_dc_complement`; `offer.classify_odd(...,
   football_sim_half)`, `day_flags`, `OfferFetcher`, usunięcie szczebli DC bez OVER.
   `superbet_words(..., line)`; `superbet_names._football_tennis` przekazuje `line`.
5. SHEET: `football_sim.path_outcomes` / `path_actual` rodzaj `half_handicap`
   (`own + line > other` na golach połowy); DC = ta sama tablica co +0,5;
   `SimPricer.p(..., line)`; człon terminarza poza zakresem.
6. Krzywe: `fit_football_sim_curves.py` z linią w `SUBJECTS`, `--keys`, `--base
   config/sofa_football_sim_curves.next.2026-11-09.json`, `--effective-from`,
   okno 06-01..10-20, `MIN_MARKET_BUCKET` 400, klasa `women` -> plik
   `config/sofa_football_sim_curves.next.<D>.json` (klucze 11-09 bez zmian + 4
   nowe). Backfill: `measure_football_sim.py --stage live_forecasts` (nowy etap),
   potem `--backfill-out data/line_evidence/football_sim_half_lines.jsonl.gz
   --backfill-from 2026-10-14 --backfill-to <D-1>`.
7. SETTLE: `sim_value(..., line)`, 2H = regulamin - `period1`; odmowy jak dziś.
8. `leg_identity._football_vector` z linią: handicap s@0,5 OVER ≡ `result_Xh_dc`
   (1X / X2); s@0,5 UNDER ≡ `result_Xh` drugiej strony; nie HT/FT,
   `team_scores_both_halves` itd. Buildery nigdy (`RATING_ONLY_MARKETS`).
9. Księga, CLAUDE.md (symulator, "What prints", "Comparability"), model-state,
   PIPELINE.md, CONFIG.md, skill `football-analysis`, rejestr
   `T-FOOTBALL-HALF-HANDICAP-FORWARD`.

**Testy** (`tests/sofa/test_football_sim_half.py`, rekordy z
`runs/sofa/2026-11-16/unmapped_prices/20261116T062608.717829Z.jsonl.gz`, eid
17551008 Czarnogóra U21 - Bośnia i Hercegowina U21): mapowanie par handicapu;
odmowy (zły svb, 3,5, linia całkowita, "handicap 1x2"); DC dwustronne z 1X2
połowy, "12" -> None; tylko pod przełącznikiem; `superbet_words` w obie strony;
SETTLE na prawdziwych meczach (Kazachstan - Słowacja 15534188 HT 1-0 FT 2-2;
Niemcy - Holandia 15534056 HT 1-0 FT 5-0; `_settle_sim_market` z linią 1,5 = WIN);
HALF_TIME_DISAGREES (15458641); `path_holds` ≡ `path_actual`; tożsamości; marker i
tylko OVER; staged krzywe kompletne; backfill per dzień; `SCHEDULE_TERM_MARKETS`
bez zmian; rebuild OFFER -> SHEET; grupa księgi.

**E2E:** kopia 11-16 (ma `05_sheet.json`; handicap na 28 meczach, DC na 49), plik
krzywych w `SOFA_CONFIG_DIR` scratcha z `effective_from` 11-16, `rebuild_day.py
--dry-run` musi pokazać OFFER + SHEET; nowe single tylko z 4 kluczy, reszta nóg i
buildery identyczne, `removed_as_same_event` tylko pary handicap / DC; skala
40-80 nóg (przerwa reprezentacyjna).

**Ryzyka:** 1H przeszacowuje na żywo (-3,1 pp [-6,0; -0,5]) - backfill musi dać
własny offset od D; ekspozycja i zagnieżdżone szczeble; DC na meczach bez
handicapu niezmierzone (rekomendacja: krótki pomiar przed włączeniem).

## 5. D - Siatkówka 230059 "1.Set/Mecz"

**Korekty szkicu:**
- **Misgrade:** `cs2.grade_side` nie zna stron łącznych - "T1/T1" spada do
  ostatniej gałęzi i jest zawsze LOSS [spr.: `cs2.py:544-577`]; to samo
  `volleyball_point_model.win_loss` (:438-460). Gałąź "wskaźnik" w obu.
- Nie dopisywać kluczy do `config/sofa_volleyball_point_curves.json` (czytany przez
  zbudowane dni od 11-06) - osobny plik i osobna nakładka.
- `vb_point_pricer.in_scope` jest bez daty - bramka w parserze SHADOW i
  `run_sport_confidence._allowed`, `in_scope` = suma zbiorów.
- `side_class` zamienia "T1/T1" na TEAM - jawna gałąź SAME / SPLIT.
- `reads_market`, `build_slip.py:244`, `leg_relations._shadow_proposition` muszą
  znać rynek.

**Kroki:**
1. `shadow.MARKETS["volleyball"][230059] = MarketSpec("set1_match",
   kind="set_match", scope="sets")`; `Kind` += "set_match"; strony "T1/T1",
   "T1/T2", "T2/T1", "T2/T2" z nazwy (`_wide_side`, dokładne napisy, bez
   dopasowania przybliżonego - nazwy zawierają "/"); `cs2.SET_MATCH_SET`,
   `set_match_of`, `Shape "joint"`, `complete_group`, `group_shape`; marża 4-drogowa
   przez `group_fair` / `group_overround` (~13,8%; > 15% = MARGIN_TOO_HIGH).
2. `epochs`: `VB_SET1_MATCH = "vb_set1_match_v1"`, `VB_SET1_MATCH_FROM_UTC = None`,
   `VB_SET1_MATCH_LEG_FIELD`, `VB_SET1_MATCH_MARKETS`, `vb_set1_match(date,
   build_at)` (wymaga `vb_point_model`).
3. `parse_line` / `parse_event` / `reads_market(..., set1_match=False)`;
   `run_shadow.py:208-256` i `build_slip.py:242-249` z flagą.
4. Wycena: `volleyball_point_model.actual_values` gałąź `set_match` (zwycięzca seta
   1 i meczu z symulacji); `win_loss` wskaźnik; `VbPricer.p` / `swapped()` bez zmian.
5. Ocena: `shadow.actual_value` gałąź `set_match` (seta 1 z okresów, mecz z
   `result.winner` - złoty set już liczony z setów), `grade_side` wskaźnik.
6. Krzywe: nowy `scripts/sofa/fit_vb_set1_match_curves.py` (walk-forward rally,
   okno jak 16 kluczy, 4 000 symulacji, seed z eid, `MIN_BUCKET` 200, hold-out
   2026-09-29..11-20) -> `config/sofa_vb_set1_match_curves.json`; nakładka w
   `with_vb_point_curves` pod `vb_set1_match`; `side_class` SAME / SPLIT;
   `EXTENDED_MARKETS["volleyball"][230059]`; druga bramka w `_allowed`.
   Dowody: `backfill_vb_point_p.py` po rozszerzeniu `in_scope`.
7. `leg_identity`: brak tożsamości (to część wspólna 745 i 744) - test;
   `leg_relations`: propozycja łączna, `set1_match` w zbiorze `score` (DEPENDENT z
   `winner` / `set_winner`).
8. `superbet_names`: "1.Set/Mecz" / "{A}/{B}"; `market_coverage` nota
   `vb.set_and_match`. "Czy będzie 4./5. set?" zostaje nieczytane.
9. Księga, CLAUDE.md, model-state, PIPELINE.md, CONFIG.md,
   `MODELE_HOKEJ_KOSZ_SIATKA.md`, skill `sport-analysis`, rejestr
   `T-VB-SET1-MATCH-calibration` (SAME ≥ 0,70, ±3 pp, ≥ 300 linii / ≥ 40 meczów).
   Uwaga: `T-PRICE-EDGE-VB-RAW-FORWARD` (zarejestrowany 11-20, od 11-21) liczy
   wszystkie drukowane single siatkówki - nowe nogi zmienią jego populację; opisać
   w rejestrze albo wyłączyć `set1_match` z tej populacji (decyzja operatora).

**Testy** (`tests/sofa/test_vb_set1_match.py`, fixture z
`runs/sofa/2026-11-15/unmapped_prices/volleyball_20261114T070138.253746Z.jsonl.gz`,
event 15721202 "ABEL/Moda (K)" / "Brasilia (K)" 1,75 / 7,9 / 4,7 / 4,4): off bajt w
bajt; przełącznik; 4 strony i marża ≈ 0,1381; niepełna grupa odrzucona;
`group_fair` = 1; `grade_side` wskaźnik (regresja misgrade); złoty set 16562455;
3-4-5 setów (17267101, 17193834, 15609512); partycja i marginesy symulacji
(suma = 1, T1/T1 + T1/T2 = P(set 1)); znaczniki; klucze SAME / SPLIT; nakładka
bez dotykania pliku rally (md5); marża > 15%; nazwy; tożsamość / relacje;
backfill; /kupon; `sample_hit_rate`.

**E2E:** kopie 11-14 / 11-15 z wstrzykniętymi liniami 230059; poza `set1_match`
zero zmian; ~5-11 nóg SAME, kursy 1,12-1,63; pokrycie parsera ~307 meczów.

**Ryzyka:** plus to efekt faworyta, nie rynku; marża blisko 15%; ten sam model
przeszacowuje handicap punktów - hold-out obowiązkowy.

## 6. Kryteria akceptacji (każdy rynek)

1. Testy rynku zielone, `tests/sofa` zielone, ruff, mypy, rejestr.
2. Przełącznik wyłączony = artefakty bajt w bajt.
3. Plik krzywych staged różni się tylko nowymi kluczami; hold-out na historii
   (≥ 0,70: realizacja - pewność ≥ -3 pp).
4. E2E na kopii: liczby nóg w paśmie z planu, inne nogi bez zmian, rozliczenie
   zgodne, md5 prawdziwych plików bez zmian.
5. Dokumenty i księga zaktualizowane; raport po polsku w `docs/sofa/evidence/`.

## 7. Prompt sesji wdrożeniowej (skrót)

Zadanie: wdrożyć rynki z tego planu, które operator zatwierdził (sekcja 0, decyzje
1-8). Najpierw: krok 0 - niezależna weryfikacja tego planu wobec bieżącego `main`
(subagent dostaje plan i kod, nie wnioski; sprawdza każde plik:linia, tożsamości,
misgrade'y z korekt, ścieżki zapisu plików krzywych). Potem rynek po rynku w
kolejności D -> A -> C -> B, każdy: kod + testy -> bramki -> refit na kopii (jeśli
go) -> E2E na kopii -> dokumenty -> commit własnych ścieżek. Po każdym rynku linia
dla operatora i stan w `docs/sofa/history/STAN_NOWE_RYNKI_<data>.md`. Blokada =
zatrzymaj, zapisz stan, nie obchodź reguły.
