# Plan 2026-10-05: naprawa SETTLE i jeden kupon ze statystyk

Status: PLAN v4 — decyzje operatora D1–D7 naniesione, dwie recenzje
adwersaryjne (15 + 21 uwag) i raport po `/sofa-day` 10-05 uwzględnione. Nic z
tego nie jest wdrożone. Wdrożenie: osobna sesja, `/sofa-day` 10-05 zakończony.

Dla wdrażającego: każdy krok kończy się testem w `tests/sofa/`, pełnym
`pytest tests/sofa`, `ruff check src/bet/sofa scripts/sofa`, `mypy --strict
src/bet/sofa scripts/sofa` i commitem na `main` (bez gałęzi, bez `git stash`).
Kod i testy po angielsku, dokumenty `docs/sofa/` po polsku. Numery linii są ze
stanu `2ad8da50`; przed edycją potwierdź je `grep`.

Źródła: przegląd SETTLE (4 agentów, tylko odczyt), dwie recenzje planu, raport
runu 10-05. Sprawdzone lokalnie: Everton 09-24 (event 16997888 przesunięty o
66 h, rozliczony LOSS), siatkówka 10-01 (id 16885527 dla dwóch meczów
Superbetu), 7c liczy każdy wynik inny niż WIN/PUSH jako przegraną
(`audit_settlement.py:190-200`). Liczby tylko od agentów są tak oznaczone.

---

## Część 0. Zasady

1. **Rozliczenie = id meczu Sofascore → wynik tego meczu → WIN / LOSS / ZWROT.**
   Znane id nigdy nie jest szukane ponownie. Gdy id trzeba znaleźć (hokej,
   koszykówka, siatkówka, CS2 — startują od meczu Superbetu): obie nazwy
   powyżej progu, zapisany dowód, przypięte na stałe, unikalne w dniu.
   Wątpliwość = brak oceny.
2. **Pewność wyłącznie ze statystyk**, skalibrowana na historii wyników bez cen.
   Cena nie wchodzi do pewności, kolejności ani wyboru builderów. Cena jest
   tylko warunkiem postawienia zakładu i filtrami z D1.
3. **Jeden kupon** `runs/sofa/<d>/KUPON_<d>.pdf` dla wszystkich sportów, od
   najwyższej pewności, potem od najwcześniejszego startu, nogi jednego meczu
   razem. Analitycy czytają 30 najlepszych pozycji; operator w każdej chwili
   może zlecić dodatkowe.
4. Stare dni czytają się dokładnie jak dotąd. Historia (próbki, rating, replay)
   zmienia się tylko świadomie (podbity `HISTORY_PARSER_VERSION`).

---

## Część 1. Decyzje operatora (ostateczne)

Z 2026-10-05: WATCH rozliczany osobno; WSZYSTKIE znika; start po `/sofa-day`;
jeden kupon wszystkich sportów; top 30 analizowane + dodatkowe na życzenie;
pewność tylko ze statystyk.

| # | decyzja | gdzie w planie |
|---|---|---|
| D1 | Filtry: x = pewność × kurs ≥ 0,90, marża ≤ 15% (z rana) + techniczne (cena przed startem, nie live: `STALE_PRICE`, `KICKED_OFF`; `ODDS_TOO_LOW` = kurs ≥ 1/0,9202). `MAX_DISAGREEMENT` i `UNREACHABLE_BAR` wyłączone. `PRICE_MOVED_SINCE_SHEET` → x przeliczone na świeżym kursie | K2. Pomiar `MAX_DISAGREEMENT` (piłka 09-24..10-04, `measure_disagreement.py --from 2026-09-24 --to 2026-10-04 --profile standard`, uruchomiony w sesji 10-05; przed K2 uruchomić ponownie i zapisać wynik do `data/analysis_2026-10-05/measure_disagreement.txt`): odrzucane −3,7% [−9,6; +2,1], dopuszczone −4,8% [−6,1; −3,4] — przedziały się nakładają |
| D2 | Hokej, koszykówka, siatkówka, CS2 **na kuponie**, pewność z modelu wyników / silnika CS2 skalibrowanego na historii bez cen | Część 5 (F1–F8). Rynek bez krzywej = `NOT_CALIBRATED`, jak w piłce |
| D3 | Bet Buildery wybierane po pewności | K10 |
| D4 | Buildery na osobnych stronach, odsyłacz przy bloku meczu | K3, K10 |
| D5 | Poranne pliki 10-05 (WARIANT, kupony sportowe, WSZYSTKIE) zostają i są rozliczane po staremu — ostatni raz | K5 |
| D6 | Pewność z próbki (estymator krzywej; także rynki tenisa z ratingiem) + druga liczba „model” (prognoza z głęboko przeanalizowanych statystyk, bez ceny, nieskalibrowana, informacyjna) | K1, K11 |
| D7 | Dogrywka w piłce bez zmian | A6 |

---

## Część 2. Kolejność wykonania (sesja wdrożeniowa)

0. **Start:** `git pull`; testy zielone w głównym checkoutcie; md5 wszystkich
   PDF i artefaktów 10-05 (oficjalny, WARIANT, cztery kupony sportowe,
   WSZYSTKIE) do `data/analysis_2026-10-05/md5_before.txt`. Pliki D5 nie są
   nadpisywane (md5 sprawdzone na końcu).
1. **Decyzja operatora o poprawce próbek** (raport runu): gałąź
   `worktree-agent-a074984278560bcfa`, commit `13756d32` („an old two-squad
   clash no longer empties the goal-sample pool”). Przed scaleniem: testy w
   głównym checkoutcie (11 porażek `test_agentic_config` w worktree wynika z
   położenia worktree — potwierdzić). Zmienia to, co produkuje SAMPLES, więc
   scalić przed K9 (przebudowa i tak zaczyna nową epokę) albo świadomie
   odłożyć.
2. **Faza A (K0–K12)** dla piłki i tenisa, przebudowa 10-05 (K9). Każda godzina
   zwłoki to więcej nóg zablokowanych starą regułą.
3. **Część 4 (SETTLE) przed porannym rozliczeniem 10-06**: A1, A3, A2, A4, A5,
   potem 4B, 4C, 4D. Po wdrożeniu zrestartować pętle `shadow_daily` /
   `cs2_daily` na 10-06 i `capture_closing --loop` (pętla czyta swój plan przy
   starcie).
4. **Faza B (F1–F8)**: najpierw kalibracja i raport (F4–F5), potem wpięcie
   (F7). Przebudowa 10-05 jeszcze raz, jeśli zdąży przed startami; inaczej od
   10-06.
5. Recenzja adwersaryjna kodu po każdym z kroków 2–4 (agent, tylko odczyt),
   poprawki, `/sofa-verify` w NOWEJ sesji (kontrakty agentów ładują się przy
   starcie sesji).

---

## Część 3. Faza A — jeden kupon ze statystyk (piłka, tenis)

**K0. Epoka.** `src/bet/sofa/epochs.py`:
- `STATS_ONLY_DATE = "2026-10-05"`, `STATS_ONLY_FROM_UTC` = chwila wpisana w
  commicie tuż przed K9: późniejsza niż `created_at_utc` ostatniego porannego
  `08_confidence.json` 10-05 (wg recenzenta 2026-10-05T06:13:33Z — potwierdzić
  w pliku) i wcześniejsza niż start K9.
- `stats_only(date, build_at) = date >= STATS_ONLY_DATE and build_at >=
  STATS_ONLY_FROM_UTC`, `build_at = timeutil.now()` (szanuje `SOFA_NOW`, więc
  replay starych dni w `prepare_refit` zostaje starą regułą).
- `05_sheet.json`, `08_confidence.json`, `11_coupon.json` zapisują `"epoch":
  "stats_only"`; CONFIDENCE w epoce stats_only odmawia (exit 2) SHEET bez tej
  epoki — przebudowa zawsze od SHEET.
- Epoka nogi zablokowanej: klucz `epoch` (`old` / `stats_only`) w istniejącym
  słowniku `printed_under` (`locked_print.py:139`); brak klucza = `old`.

**K1. Cena znika z `p_central`** (za `stats_only`):
- `run_sheet.py:1012-1023` — środek ściągany do drabinki Superbetu
  (`K_TENNIS_LADDER_CENTRE`; także metryki NB/normalne tenisa);
- `run_sheet.py:1134-1139` — `blend_with_price` (rating tenisa z `market_p`);
- `run_sheet.py:1148-1161` — `p_empirical_shrunk_to_price`;
- `derived.py:556-570` — `K_DERIVED_CENTRE` / `_shrink_sides_to_diff`
  (`handicap_*`, też piłka);
- `derived.py:610-615` — cena w ratingu tenisa (handicap_games, most_games);
- `RATED_MARKETS` tenisa (games_total, games_won_for, sets_total,
  handicap_games): pewność z estymatora próbki, jak w replay
  (`calibrate_from_cache.py:720-724`); rating idzie do K11 (D6).

Bez zmian i poza ceną (nie przenosić bez decyzji operatora): rating piłki w
`p_central` (`W_FOOTBALL_RATING`, `run_sheet.py:1081`) i priorytet poziomu
tenisa (`run_sheet.py:1031`) — nie są ceną, ale replay krzywych ich nie ma;
znana niezgodność do zmierzenia przed refitem. `06_coupon.json` i `p_bar`
(`bar_probability`, `run_sheet.py:1255-1264`) zostają cenowe — nie są kuponem
i nie wpływają na wydruk ani kolejność. Krzywe (sprawdzone przez recenzenta w
bazie): tenis 8,97 mln wierszy, 98,8% bez ceny; piłka 49,56 mln, ~206 tys. z
ceną.

Test: rynek niepochodny — `p_central` nie zależy od `market_p`; `handicap_*` —
nie zależy po wyłączeniu `K_DERIVED_CENTRE`; stary dzień — bez zmian.

**K2. Filtry wg D1.** Za `stats_only`: bez `DISAGREES_WITH_PRICE`
(`confidence.MAX_DISAGREEMENT`), bez `UNREACHABLE_BAR`; `PRICE_MOVED_SINCE_SHEET`
(`run_confidence.py:493`) → x na świeżym kursie z `04_offer.json`;
`gap_shrink_k` = 0. Test: model 0,85 przy cenie 0,60 nie jest odrzucany; x na
świeżym kursie < 0,90 jest.

**K3. Artefakt kuponu, kolejność, grupowanie, pozycje.**
- **Kupon = `runs/sofa/<d>/11_coupon.json` od Fazy A.** Pisze go nowy
  `build_coupon.py --date <d>` (nowy, w `scripts/sofa`) z `08_confidence.json` (w Fazie B
  także z `08_confidence_sports.json`). Pozycje 1..N, `blocks`,
  `removed_by_reads`, `epoch`, nogi zablokowane — tylko w 11.
  `08_confidence.json` zostaje selekcją piłki/tenisa i wejściem SETTLE/refitu
  (format bez zmian).
- Nowa `confidence.coupon_artifact(run_dir) -> Path`: `11_coupon.json`, jeśli
  istnieje, inaczej `08_confidence.json` (dni dawne). Przechodzą na nią:
  `build_coupon_pdf.py:268`, `confidence.legs_requiring_read` / C3
  (`audit_variants.py:355,568`), `locked_print.carry_over`,
  `capture_closing.py:37`, `audit_clv.py:166`, `audit_settlement.py:634` (7c),
  `record_results.py:115`, `audit_day_deep.py:88`, `audit_trend.py:128`,
  `run_boosts.py:154`. `run_settle.printed_keys` (`:691`) i A4 czytają tylko
  nogi `sport in {football, tennis}`. `prepare_refit.py:1268-1357` zostaje na
  08.
- Kolejność: czysta `confidence.coupon_order(legs) -> list[Block]`; blok =
  jeden mecz (`group_key` = `sofa:<sofascore_event_id>`); bloki wg najlepszej
  nogi: pewność malejąco, start rosnąco, id meczu; w bloku pewność malejąco,
  rynek, linia. Bez kursu i EV w kluczu; także sort `run_confidence.py:820`
  (dziś `-leg_ev`) i `:827-831` (dziś remis `offered_odds`) za `stats_only` =
  `(-confidence, kickoff_utc, sofascore_event_id, market, line)`.
- Nogi zablokowane — osobna sekcja na górze PDF, poza numeracją top 30.
- Okno dnia: kupon dnia D = nogi z `kickoff_utc` w [D 00:00Z, D+1 00:00Z) dla
  każdego sportu (dziś sporty sięgają 06:00 Warsaw D+1,
  `sport_coupon.py:266-269,352-386`; `source_date` zostaje tylko do
  rozliczenia).
- Testy: remis pewności → wcześniejszy start wyżej; nogi meczu razem, blok na
  miejscu najlepszej nogi; kolejność w 11 = PDF; każdy czytelnik z listy na
  dniu z 11 i na dniu bez 11.

**K4. Top 30 + dodatkowe.** `legs_requiring_read(coupon)` (dziś
`confidence.py:708-718`): pierwsze 30 pozycji niezablokowanych ∪ nogi
builderów ∪ pozycje z `runs/sofa/<d>/read_requests.json` (lista wpisów
`{"position": int}` albo `{"group_key", "market"?, "line"?, "direction"?}`,
każdy z `"requested_by": "operator"` i `"at_utc"`). `/sofa-analyze` przyjmuje
„dodatkowo: <numery pozycji>” → dopisuje do `read_requests.json`, analityk
sportu czyta, odczyty scalane, przebudowa od CONFIDENCE. C3 czyta ten sam
zbiór. Test.

**K5. Koniec WARIANT, WSZYSTKIE, osobnych kuponów sportowych.**
- `ConfidenceProfile.retired_from_utc = STATS_ONLY_FROM_UTC` dla `wariant`;
  `run_confidence` i `build_coupon_pdf` z `--profile wariant` odmawiają dla
  nowszych buildów (exit 2). Profil zostaje (7d, ledger,
  `run_settle.printed_keys`, refit iterują `PROFILES`).
- `run_multi_coupon.py` odmawia od `STATS_ONLY_FROM_UTC`;
  `run_sport_coupon.py` odmawia od `SPORTS_ON_COUPON_FROM_UTC` (instalacja F7),
  nie wcześniej — inaczej dni bez żadnego wyniku sportów.
- Pliki 10-05 z rana (D5) zostają, rozliczane po staremu. Test.

**K6. WATCH rozliczany osobno.** Odmowa z `reads.json` (`read_refusal`, dziś
`run_confidence.py:444`) i automatyczny WATCH `MODEL_ABOVE_OWN_SAMPLE`
(`:676-681`) przeniesione na koniec łańcucha bramek. Noga, która przeszła
wszystko, a usunął ją odczyt → `removed_by_reads` w 11 (pełna noga z kursem,
`reason`: `analyst` / `verifier` / `auto`). `audit_settlement.py` sekcja 7f i
`record_results` wiersz `removed:reads` — rozliczane jak 7c, nigdy w wyniku
kuponu. Test.

**K7. Ledger i audyty.**
- `record_results.py`: wiersz `official` z `epoch` i sekcjami per sport. Dzień
  z nogami obu epok (10-05) → dwa wiersze: `official` (świeże i zablokowane z
  `printed_under.epoch == stats_only`) i `official:pre_stats_only`
  (zablokowane z porannego buildu). `wariant`/`multi` nie powstają dla buildów
  stats_only.
- `audit_ledger.py`: grupy (wariant, epoka) — `do 10-04`, `10-05 rano`,
  `stats_only`; nigdy suma.
- `audit_settlement.py` 7c: sekcje per sport + suma kuponu; 7d dla dni z
  WARIANT jak dotąd.
- `audit_variants.py`: C3 przez K4; M1–M2 wyłączone dla buildów po
  `STATS_ONLY_FROM_UTC` (WSZYSTKIE 10-05 = zapis porannej wersji, md5 w
  raporcie); U1 kolejność 11 = `coupon_order`; U2 każda niezablokowana noga ma
  epokę stats_only; U3 (Faza B) każda noga sportu odtworzona z surowego
  snapshotu (kurs, devig, marża, x, wiek ceny, kubełek kalibracji) — zastępuje
  S1–S5.
- `audit_day_deep.py` wg nowych bramek.

**K8. Kontrakty** (ładują się w nowej sesji). `CLAUDE.md`: sekcja decyzji;
przepisać reguły twarde o WARIANT, kuponach sportowych, WSZYSTKIE i „CS2 /
SHADOW never feed or gate the coupon” (od F7 nogi sportów są na kuponie;
pomiar SHADOW/CS2 zostaje); lista komend (`build_coupon.py`,
`fit_sport_confidence.py`, `run_sport_confidence.py`,
`audit_settle_identity.py` — dopisywać dopiero razem ze skryptem, bo
`tests/sofa/test_documented_commands.py` sprawdza istnienie). Komendy:
`sofa-day.md` (bez WARIANT, WSZYSTKIE i czterech równoległych
`sofa-sport-runner`; nowe etapy; top 30 + dodatkowe), `sofa-analyze.md`,
`sofa-rebuild.md`, `sofa-verify.md`, `sofa-settle.md`. Agenci: `sofa-runner`,
`sofa-verifier`, `sofa-settler`, oba analityczne, nowy `sofa-analyst-sport`;
`sofa-sport-runner` wycofany razem z kuponami sportowymi. Skille
`sofa-pipeline` (+ `references/`), `sofa-analysis-core`;
`docs/sofa/AGENTIC_FLOW.md`, `docs/sofa/PIPELINE.md`.

**K9. Przebudowa 10-05:** SHEET → COUPON → CONFIDENCE → `build_coupon.py` →
PDF; odczyty analityków dla nowego top 30; weryfikacja; md5 po (pliki D5 bez
zmian). Nogi wystartowane z porannego PDF zostają zablokowane (12263aac /
f3045824).

**K10. Bet Buildery po pewności (D3, D4).** Za `stats_only`:
`best_leg_per_quantity` (`confidence.py:829-849`) po pewności, nie `leg_ev`;
pula `run_confidence.py:858` po pewności; kolejność builderów (`:925`) i PDF
(`build_coupon_pdf.py:361`) po `combined_probability`; `is_stakeable`
(`confidence.py:1328-1350`) = `combined_probability × odds_after_haircut ≥ 0,90`;
`best_for_fixture` = najwyższe `combined_probability`. Pole `stakeable_rule` w
artefakcie; stare artefakty czytane starym predykatem. Skutek oczekiwany:
buildery 2-, 3-, 4-nogowe są prefiksami jednej puli (`run_confidence.py:861-862`),
więc `best_for_fixture` to prawie zawsze 2-nogowy — nie błąd. Strony builderów
osobno, odsyłacz przy bloku meczu. Test: wybrany builder o wyższym
`combined_probability`, nie o wyższym EV.

**K11. Druga liczba „model” (D6).** Nowe pola nogi `forecast_p` i
`forecast_source` (`football_rating` / `tennis_rating` / `score_model` /
`cs2_engine` / `null`). Istniejące `model_p` (= `p_central`,
`run_confidence.py:698`, czytane przez `prepare_refit.py:1147`) zostaje bez
zmian. Piłka: `forecast_p` = ten sam rozkład predykcyjny co SHEET
(`sheet_predictive_sd`, ten sam estymator) ze środkiem = `expected(...)`
z `football_rating.py:762` (zwraca oczekiwane liczby) dla metryki; rynki
pochodne i `UNRATED_MARKETS` = „—”. Tenis: rating bez `blend_with_price`.
PDF: kolumna „model” obok „pewność”, z dopiskiem, że pewność jest
skalibrowana, a model nie. Nie bramkuje, nie sortuje. Test: `forecast_p` nie
zależy od `market_p`; `model_p` bez zmian.

**K12. Zegar startu zapamiętany przez RESOLVE** (raport runu 10-05: Szanghaj,
RESOLVE 06:20Z, Superbet 07:30Z — przebudowa o 06:12Z zablokowała wcześnie
singli Cui, Vukić i Svrčina U13.5; ceny zamknięcia do CLV ~80 min za
wcześnie). Najwcześniejszy zegar zostaje regułą bramki (chroni przed
spóźnionym zegarem), ale `kickoff_utc` z RESOLVE jest odświeżany z
`/event/{id}` (`startTimestamp`) przy OFFER, gdy `superbet_kickoff_seen_utc`
różni się od niego o > 30 min — zapytanie przez mostek tylko dla takich
meczów. Blokada i `capture_closing` biorą odświeżony zegar, gdy jest. Test:
zegar RESOLVE wcześniejszy o 70 min od obu świeżych zegarów → bramka i
`capture_closing` biorą świeży.

---

## Część 4. Naprawa SETTLE (przed rozliczeniem 10-06)

### 4A. Piłka i tenis

Stan: tożsamość meczu poprawna — grupowanie po `sofascore_event_id`
(`run_settle.py` main l. 701), świeże `/event/{id}` (`_event_payload` l. 178);
wg agenta 6735 meczów bez zamiany drużyn.

**A1. Mecz przesunięty o > 48 h jest rozliczany** (Everton 09-24, sprawdzone).
- `settle.py`: `VOID_AFTER = timedelta(hours=48)` przeniesione z `shadow.py:119`
  (import w obu miejscach); `moved_beyond_void(event, kickoffs) -> bool`:
  |`startTimestamp` − najwcześniejszy zegar| > 48 h (zegary:
  `02_fixtures.kickoff_utc`, `superbet_kickoff_utc`,
  `superbet_kickoff_seen_utc`; jak `locked_print.kickoff_clocks`).
- `run_settle.py` po `_event_payload`: powód pominięcia `MOVED_BEYOND_VOID` w
  `07_settle_skips.json` (jak PUSH, `run_settle.py:322-338`); **wiersz w
  `sofa_settled_row` nie powstaje** (nie zapisywać `outcome='VOID'`: 7c liczy
  go jako przegraną, `fit_confidence.py:162-167` ignoruje `outcome`).
- 7c, `record_results.py`, `settle_multi_coupon.py:47-96`: powód
  `MOVED_BEYOND_VOID` / `AWARDED` = **ZWROT (0 j.)**, osobna kolumna, nie
  „nierozliczone”.
- Dane wstecz: nowa flaga `regrade_settled.py --moved-void` (skrypt nie ma
  `--from/--to`). Klucz UNIQUE bez `run_date` (`settle.py:394-406`): jeśli
  tablica dnia faktycznego rozegrania wyceniła klucz → przenieść `run_date` na
  ten dzień; inaczej usunąć wiersz z kopią w `runs/sofa/regrade_<ts>.json`.
  Lista zmienionych nóg wydrukowanych do raportu. Potem
  `record_results.py --from 2026-09-18 --to 2026-10-05`.
- Tenis 24–48 h (wg agenta 18 meczów): rozliczane; reguła Superbetu otwarta.
- Testy: +66 h i −66 h → `MOVED_BEYOND_VOID`, brak wiersza, 7c i ledger =
  zwrot; +47 h → rozliczone; `--moved-void` przenosi albo usuwa z kopią.

**A2. Props zawodnika z niewłaściwego składu** (`_settle_player` l. 353; wg
agenta 6 z 1647 par w obu składach). Id gracza w danych brak;
`03_samples.json` → `players[...]` ma `side` = `side_a`/`side_b` (mapowanie na
gospodarz/gość przez `02_fixtures`). Dopasowanie tylko w składzie tej strony;
trafienie także w drugim → `PLAYER_AMBIGUOUS`. Test: „Weverson” (gość) nie z
„Reverson” (gospodarz); nazwisko w obu → `PLAYER_AMBIGUOUS`. Dane wstecz:
`regrade_settled.py --players`, lista zmian.

**A3. Mecz przyznany (`isAwarded`).** Tylko ścieżka SETTLE:
`settle.settle_completed(event)` = `is_completed_event` ∧ ¬`isAwarded`;
`is_completed_event` (l. 104) bez zmian (czytają ją `samples.py`,
`football_rating.py`, `calibrate_from_cache.py`, `tennis_prior.py`,
`run_backfill.py`). Powód `AWARDED` = zwrot. To samo w `shadow.build_result`;
CS2 już odrzuca walkower (dopisać test). W cache 1 przypadek (siatkówka
17238228).

**A4. Zablokowana noga bez wiersza SHEET** (OFFER po starcie usunął mecz,
`run_sheet.py:1581`; `rows_to_consider` l. 654 rozlicza tylko klucze obecne w
SHEET): ocenić z `/event` i zapisać do `runs/sofa/<d>/07_settled_printed.json`
— nie do `sofa_settled_row` (NOT NULL `sample_mean`, `sample_sd`, `p_bar`
nieznane; wiersz nie może zasilać krzywych). 7c i ledger czytają oba źródła.
Test.

**A5. 7c i ledger biorą wiersze innej daty z różnych zbiorów**
(`audit_settlement.py:359-361` z SHEET, ledger z wydrukowanych) → oba z
wydrukowanych kluczy (+ A4). Test: ten sam wynik.

**A6.** Dogrywka — bez zmian (D7).

**A7.** `run_settle.py --date 2026-10-03` (mostek; 2 nogi WARIANT
`SUBJECT_NOT_MATCHED` naprawione 10-04), potem ledger.

### 4B. Hokej, koszykówka, siatkówka

Stan: po znalezieniu meczu ocena tylko po id (`grade_coupon`,
`sport_coupon.py:1128`, po `superbet_event_id` do zapisanego wyniku); słabe
jest znajdowanie (`find_event`, `settle_shadow.py:381`).

**B0. Jeden zbiór stanów** w `bet.sofa.shadow`: `TERMINAL`, `RETRYABLE`,
`EXCLUDED`, importowany przez `settle_shadow` (dziś l. 97), `settle_cs2`
(l. 80), `settle_sport_coupon`, `record_results` (`FINAL_STATES` l. 61-63).
Nowe stany: `DUPLICATE_SOFASCORE_ID`, `WITHDRAWN`, `ID_CHANGED`, `MOVED_TO`,
`AWARDED`, `AMBIGUOUS_START`, `DUPLICATE_SUPERBET_TEAM`. Test: ledger ich nie
liczy.

**B1. Jedno id Sofascore dla dwóch meczów Superbetu** (16885527). Przy zapisie
`settled.json`: unikalność `sofascore_event_id` w plikach D-1..D+1 sportu.
Kolizja: zostaje rekord, w którym obie nazwy przechodzą próg (`fuzz > 82` lub
alias) i którego ostatni snapshot jest najpóźniejszy; reszta →
`DUPLICATE_SOFASCORE_ID` (`duplicate_of`). Mecz wycofany (ostatni snapshot
> 2 h przed startem, ta sama para później pod innym id) → `WITHDRAWN`. Test.

**B2. Nazwa szukanej drużyny nie jest sprawdzana** (`resolve.py:684-700`;
„U. De Santiago” → wg agenta Universidad Católica, id 17207292 sprawdzone,
nazwy nie). Tylko gałąź `SPORT_SCOPED_SEARCH` (ten kod służy też RESOLVE
piłki/tenisa): zdarzenie przyjęte, gdy szukana drużyna przechodzi próg wobec
swojej strony i przeciwnik wobec drugiej, albo przy `MUTUAL_LISTING`. Reguła
jednego słowa (`shadow_opponent_agrees`, `resolve.py:257`): słowo ≥ 5 znaków
spoza `config/sofa_name_stopwords.json` (texas, miami, carolina, state, tel,
aviv, city, united, university, universidad, sporting, club, real, …) i tylko
razem z warunkiem nazwy szukanej. Bez zapisu `verified` w cache z dopasowań
przez wspólne słowo i `TOURNAMENT`; wpis „u. de santiago” → 233778 usuwa
skrypt z `--dry-run`. Pomiar przed/po: SETTLED 10-01..10-04 i recall RESOLVE
piłki/tenisa bez spadku. Testy: „hapoel tel aviv” vs „maccabi tel aviv”
odrzucone; zamrożone prawdziwe pary z 10-01..10-04 przyjęte.

**B3. Id przypięte.** Rekord z id przy ponownej próbie: `/event/{id}` wprost;
inne id z szukania → `ID_CHANGED`, stare oceny zostają. Test.

**B4. Ten sam mecz w plikach dwóch dat** (wg agenta koszykówka 15132383 w 10-02
i 10-03). Starszy rekord → `MOVED_TO:<data>`, poza `record_results.measure_rows`
i `rule_rows` (l. 229-235). Test.

**B5. `UNUSUAL`** (hokej 15025409, status-glitch) → `RETRYABLE` do give-up;
przyjęty, gdy `status.type == finished`, wynik spójny (`build_result`), nie
walkower, krecz, `isAwarded`. Test.

**B6. Orientacja:** id zdarzenia i drużyn listingu = `/event`; niezgodność →
tylko linie niezależne od strony. Test.

**B7. `shadow_daily.py:66-85`:** przegląd D-7..D-3 dla rekordów nieterminalnych
(jak `settle_cs2 --sweep`).

### 4C. CS2

Stan: 09-28..10-04 zero pomieszań (wg agenta 218 id, unikalne). `pick_event`
(`cs2.py:675`) wymaga obu nazw > progu (l. 695-697).

**C1. Odstęp startu** (`MATCH_WINDOW` 6 h, l. 66): kandydat > 1 h od startu
Superbetu → `AMBIGUOUS_START`, jeśli Superbet miał snapshot przedmeczowy
później niż start Sofascore + 15 min. `start_gap_h` w rekordzie. Test: Hotu –
Black Phoenix 12:15, start Superbetu 18:00, snapshot 17:30 → odrzucone.

**C2. Id serii przypięte** (`settle_one`, `settle_cs2.py:191`) jak B3. Test.

**C3. Składy „ex-”** (`esports_score`, l. 637): „ex” = znacznik składu; znane
przypadki aliasami całych nazw. Test.

**C4. Niezagrana mapa** → zwrot zamiast `UNGRADEABLE` (`actual_value` l. 885,
`sport_coupon._grade_leg`). Test.

**C5. Drużyna w dwóch meczach Superbetu naraz** (raport runu 10-05: Vitality
Academy w dwóch seriach o 10:30Z). Ta sama nazwa drużyny w ≥ 2 zdarzeniach
Superbetu o startach w odstępie < 3 h → oba `DUPLICATE_SUPERBET_TEAM`, poza
kuponem (F1) i nieoceniane. To samo dla 4B. Test.

### 4D. Wspólne

**D-a.** `audit_settle_identity.py` (nowy, w `scripts/sofa`) (offline, tylko odczyt): id
użyte > 1 raz, |przesunięcie| > 48 h a ocenione, wynik nazw < 82 po
którejkolwiek stronie, `ID_CHANGED`, `DUPLICATE_*`, `MOVED_TO`. Exit 1 przy
znalezisku. Wołany w `/sofa-day` po rozliczeniu D-1 i w `/sofa-settle`.

**D-b.** Każde dopasowanie (shadow, CS2) zapisuje `match_method`,
`name_scores` (obie strony), `start_gap_h`, `matched_at_utc`.

**D-c.** Po 4A–4C: regrade offline z cache; lista dat do ponownego rozliczenia
z mostkiem; na końcu `record_results.py --from 2026-09-18 --to 2026-10-05`.

---

## Część 5. Faza B — hokej, koszykówka, siatkówka, CS2 na kuponie (D2)

Co jest: model wyników `src/bet/sofa/score_model.py` (`build_model`,
`ScoreModel.expected` / `simulate`, `line_probability(ShadowLine, games,
sport)`, historia `load_history` z listingów — wynik, okresy, sety; wg
`MODELE_HOKEJ_KOSZ_SIATKA.md:326` ok. 27 / 46 / 14 tys. meczów); silnik
`src/bet/sofa/cs2_engine.py` (Elo map z kalibracją, rundy drużyn; historia
`cs2_series` / `cs2_map`: 16 826 serii, 24 987 map); `measure_score_history.py`
(walk-forward bez cen). Brakuje: tożsamości przed meczem, kalibracji i wpięcia.

**F1. Tożsamość przed meczem — wymaga zapytań przez mostek.** SHADOW nie pyta
Sofascore (`run_shadow.py:16`), a cache nie ma nadchodzących meczów tych
sportów (wg recenzenta: `sofa_listed_event` 0 hokej/kosz/siatka od godziny
temu; `cs2_series` 0 nadchodzących).
- Id drużyn offline jak `player_model.resolve_team` (`player_model.py:991+`:
  zweryfikowany `sofa_entity`, inaczej dokładna nazwa jednoznaczna w
  listingach).
- Id zdarzenia: `client.entity_events("team", <id>, "next", 0)` dla jednej
  drużyny; druga sprawdzana w odpowiedzi regułą 4B (obie nazwy >
  `NAME_MATCH_THRESHOLD` 82, start ±1 h od Superbetu, unikalność w dniu, C5).
  CS2: nadchodzące serie drużyny tym samym endpointem i `cs2.pick_event`.
- Jedno zapytanie na mecz, raz dziennie, po `ensure_bridge.py`, krótkim
  przebiegiem (zasady mostka z CLAUDE.md; 403 = przerwać, nie ponawiać).
  Cache z TTL jak events/next.
- `runs/sofa/<d>/sport_fixtures.json`: `superbet_event_id`, `sport`,
  `sofascore_event_id`, `home_id`, `away_id`, `home_is_team1`,
  `competition_id`, `match_method`, `name_scores`, `start_gap_h`,
  `matched_at_utc`. Bez `home_is_team1` model nie zna orientacji
  (`measure_score_model.py:108` bierze ją dziś z `settled.json`, po meczu).
  Nierozpoznany → `NOT_IDENTIFIED`, poza kuponem. To id przypina SETTLE.

**F2. Rynki — lista dozwolona (nic poza nią).** Hokej `market_id` 630, 623,
658/652, 604, 640, okresy 649/674/638/678/660; koszykówka 759, 753, 768,
758/776, 777, pierwsza połowa 748/773/200804/200797/763; siatkówka 745,
230058, 100082, 230060, 1069, 744, 782 (lista wg recenzenta z
`shadow.MARKETS`, `shadow.py:161-224` — potwierdzić znaczenie każdego id
przed wdrożeniem). Poza: dnb, odd_even, yes_no, exact, koszykówka druga połowa
i Q4 (dogrywka niejednoznaczna, `last_period_ambiguous_with_ot`), wszystkie
propsy. CS2: `map_winner`, `match_winner`, `map_team_rounds`; poza:
`map_rounds_total` (stała bazowa), `maps_*`, `team_kills`, `player_*`. Wynik
rozliczenia rynku wg `MarketSpec` (`shadow.py`; hokej: regulamin vs z
dogrywką).

**F3. Liczby na nodze** (D6): **pewność** = krzywa kalibracji (F4) z `p_model`
(`score_model.line_probability` / `cs2_engine`), dolna granica Wilsona
kubełka; **próbka** = „k z n” z ostatnich 10 meczów ligowych drużyn
(`bet.sofa.comparability`, bez sparingów) na tej linii, drukowana obok, nie
bramkuje; **model** = `forecast_p = p_model` (K11). Cena tylko jako filtr D1;
korekta ceny faworytów (`config/sofa_sport_price_calibration.json`) przestaje
znaczyć cokolwiek dla kuponu (zostaje w historii kuponów sportowych).

**F4. Kalibracja bez cen.** Nowy `fit_sport_confidence.py --sport
<s> --before <d>` (nigdy w trakcie dnia):
- historia, walk-forward (`build_model` przed każdym meczem):
  `line_probability` na syntetycznym `ShadowLine` z `market_id` rodziny i
  linią z siatki (kwartyle historii ±1 krok); zapis `p_model, y, family,
  market_id, period, line, side, game`. Rodziny z historii: total, team_total,
  handicap, winner, result_1x2 w zakresie pełnym i regulaminowym (hokej,
  koszykówka), sets_total, set_handicap, points_total, winner (siatkówka);
- rodziny okresów i pierwszej połowy — tylko z rozliczonych linii SHADOW
  (`measure_score_model.py --rows-out`, od 09-29); do n ≥ 200 w kubełku
  `NOT_CALIBRATED`;
- CS2: `cs2_engine` walk-forward + `model_p` z `settled.json`
  (`settle_cs2.py:437`);
- krzywa per sport × rodzina, `EDGES` i Wilson jak `fit_confidence.py`,
  kubełek z n < 200 nieużywany → `config/sofa_sport_confidence_calibration.json`
  (`fitted_from`, `n` per kubełek).

**F5. Pomiar poza próbą** → `docs/sofa/RAPORT_KALIBRACJA_SPORTOW_<d>.md`: ostatnie
30 dni historii odłożone + rozliczone linie Superbetu SHADOW/CS2 od 09-28/29;
realizacja vs pewność per kubełek, log-loss, bootstrap po meczach.

**F6. Warunek wejścia rynku:** w kubełkach z n ≥ 200 pewność poza próbą nie
wyższa od zrealizowanego o > 3 pp; inaczej `NOT_CALIBRATED` (nie drukuje się).
D2 już zapadła — raport F5 jest dowodem, nie pytaniem.

**F7. Wpięcie.**
- Nowe etapy w `DEFAULT_SEQUENCE` (`run_pipeline.py:101`), `/sofa-day`,
  `/sofa-rebuild`: `SPORT_IDENTITY` (F1, mostek), `SPORT_CONFIDENCE`
  (`run_sport_confidence.py --date <d>`, po świeżym `--only SHADOW` i
  `--only CS2`) → `runs/sofa/<d>/08_confidence_sports.json`;
  `COUPON_ASSEMBLY` (`build_coupon.py`, po CONFIDENCE, przed PDF).
- Noga sportu: `sport`, `group_key` = `sofa:<sofascore_event_id>`,
  `superbet_event_id`, `market_id`, `family`, `period`, `subject`, `line`,
  `side`, `confidence`, `sample_hit_rate`, `forecast_p`, `odds`, `x`,
  `overround`, `kickoff_utc`, `source_date`, `price_fetched_at_utc` (CS2:
  `team1`, `team2`, `map_nr`).
- Cena: ostatni snapshot przed startem, nie starszy niż
  `sport_coupon.MAX_PRICE_AGE`, inaczej `STALE_PRICE`. Kurs zamknięcia =
  ostatni snapshot przed startem (`shadow.latest_pre_kickoff`, `shadow.py:608`);
  `audit_clv` czyta go z 11.
- Brak `config/sofa_sport_confidence_calibration.json` albo sportu w nim: nogi
  sportu `NOT_CALIBRATED`, exit 1 (PARTIAL), kupon piłki/tenisa budowany, PDF
  mówi „<sport>: brak kalibracji”. Brak `sport_fixtures.json`:
  `NOT_IDENTIFIED`, exit 1.
- Odczyty i weta: `LegRead.direction` (`contracts.py:10`) rozszerzone o
  `T1|T2|DRAW|ODD|EVEN|YES|NO|<wynik>`, nowe pole `period: int | None`; dla
  sportów `market` = `family`; weta i odczyty w `runs/sofa/<d>/vetoes.json` /
  `reads.json` po `sofascore_event_id` z F1. Analityk: nowy
  `sofa-analyst-sport` (tylko odczyt, `--sport`); działa od nowej sesji.
- Blokady nóg sportów jak `locked_print` (z 11).
- Rozliczenie: `sport_coupon.grade_coupon` jako biblioteka, wejście
  `{sport, date, legs: [...pola wyżej]}` per sport; przed oceną
  `settled.events[sb].sofascore_event_id == sport_fixtures.sofascore_event_id`,
  inaczej `NOT_GRADED:ID_CHANGED`. Po kursie z wydruku.
- `SPORTS_ON_COUPON_FROM_UTC` = instalacja F7 (K5). Siatkówka: reguła
  rozliczonego turnieju (14 dni) zostaje.

**F8. Testy:** brak wycieku przyszłości w walk-forward; nogi sportów nie trafiają
do `sofa_settled_row` ani `fit_confidence`; `11_coupon.json` = oba źródła w
`coupon_order`; noga bez tożsamości lub krzywej nie drukuje się; rozliczenie po
przypiętym id; `stats_only` dla starej daty z `SOFA_NOW`; czytelnik 11 vs 08;
`forecast_p` ≠ `model_p`; dwa wiersze ledgera dla 10-05; `LegRead` nogi sportu;
brak pliku kalibracji → exit 1, kupon piłki/tenisa zbudowany; okno UTC dnia
dla sportów; C5.

---

Poza planem: reguła kreczu (bez zmian), propsy piłkarskie (zostają), refit
krzywych piłki/tenisa (osobna decyzja; K1 go nie wymaga dla rynków
empirycznych). Naprawione w trakcie runu 10-05 (nie robić drugi raz):
`f649524f` — `rule_history` pomija zdarzenie bez linii w ostatnim snapshocie
(ledger 09-26..10-04 zapisany ponownie). CLAUDE.md na `main` już mówi
„prints every single / analysts read the best 30” (run 10-05 czytał jego
starszą kopię z początku swojej sesji).
