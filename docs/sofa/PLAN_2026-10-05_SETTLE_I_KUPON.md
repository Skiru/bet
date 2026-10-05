# Plan 2026-10-05: naprawa SETTLE i jeden kupon ze statystyk

Status: PLAN (wersja 2, po recenzji adwersaryjnej), nic z tego nie jest wdrożone.
Realizacja zaczyna się po zakończeniu `/sofa-day` 10-05 (polecenie operatora:
„od dzisiaj po sofa-day przebudowujemy”). Każdy krok kończy się testem w
`tests/sofa/`, pełnym `pytest`, `ruff`, `mypy --strict` i commitem na `main`.
Kod i testy po angielsku, ten dokument po polsku.

Źródła: przegląd SETTLE czterema agentami (tylko odczyt) i recenzja planu
(15 uwag, wszystkie naniesione), 2026-10-05. Sprawdzone lokalnie: Everton 09-24
(event 16997888, LOSS po przesunięciu o 66 h), siatkówka 10-01 (id 16885527 dla
dwóch meczów Superbetu), 7c liczy każdy wynik inny niż WIN/PUSH jako przegraną
(`audit_settlement.py:190-200`). Liczby podane tylko przez agentów są tak
oznaczone.

---

## Część 0. Zasady

1. **Rozliczenie = id meczu z Sofascore → wynik tego meczu → WIN/LOSS/ZWROT.**
   Gdy id jest znane, nigdy ponowne szukanie po nazwach. Gdy trzeba je znaleźć
   (hokej, koszykówka, siatkówka, CS2 — startują od meczu Superbetu):
   dopasowanie ścisłe (obie nazwy), z zapisanym dowodem, przypięte na stałe i
   unikalne. Wątpliwość = brak oceny, nigdy zgadywanie.
2. **Pewność pochodzi wyłącznie ze statystyk** („w 9 z 10 meczów drużyna X miała
   powyżej 7 rzutów rożnych”), skalibrowana na historii wyników. Cena nie
   wchodzi do pewności ani do kolejności. Cena zostaje tylko jako warunek, że
   zakład da się postawić, i jako filtry, które operator sam ustawił (D1).
3. **Jeden kupon:** `runs/sofa/<d>/KUPON_<d>.pdf`, wszystkie sporty, od najwyższej
   pewności, potem od najwcześniejszego startu; nogi jednego meczu razem.
   Analitycy czytają 30 najlepszych pozycji; operator w każdej chwili może
   zlecić odczyt dodatkowych.
4. Stare dni czytają się dokładnie jak dotąd. Historia (próbki, rating, replay)
   zmienia się tylko świadomie, z podbiciem `HISTORY_PARSER_VERSION`.

---

## Część 1. Decyzje operatora

Już podjęte (2026-10-05): **WATCH rozliczany osobno — TAK; WSZYSTKIE znika — TAK;
start dziś po sofa-day — TAK; jeden kupon wszystkich sportów, top 30 analizowane,
dodatkowe na życzenie — TAK; pewność tylko ze statystyk — TAK.**

Do podjęcia (rekomendacja pogrubiona):

| # | pytanie | rekomendacja |
|---|---|---|
| D1 | Filtry cenowe. Pewność i kolejność są bez ceny. Zostają filtry z rana: `x = pewność × kurs ≥ 0,90`, marża ≤ 15%. Techniczne: jest cena przed startem, nie live (`STALE_PRICE`, `KICKED_OFF`), `ODDS_TOO_LOW` (kurs ≥ 1/0,9202). Pozostałe filtry wybierające cenę: `MAX_DISAGREEMENT` (model > 10 pp nad ceną), `UNREACHABLE_BAR`, `PRICE_MOVED_SINCE_SHEET` | **Zostają filtry z rana i techniczne. `MAX_DISAGREEMENT` i `UNREACHABLE_BAR` wyłączone. `PRICE_MOVED_SINCE_SHEET` zastąpiony: x liczone na świeżym kursie** (jego uzasadnienie — cena w `p_central` tenisa — znika po K1). Pomiar dla `MAX_DISAGREEMENT` (piłka, 09-24..10-04, `measure_disagreement.py --from 2026-09-24 --to 2026-10-04 --profile standard`, wynik z sesji 10-05, przed wdrożeniem zapisać do `data/analysis_2026-10-05/`): odrzucane −3,7% [−9,6; +2,1], dopuszczone −4,8% [−6,1; −3,4] — przedziały się nakładają, czyli to brak dowodu, że bramka pomaga, a nie dowód, że szkodzi |
| D2 | Hokej, koszykówka, siatkówka, CS2 nie mają dziś pewności ze statystyk | **Poza kuponem do czasu przejścia bramki B6 (Faza B).** Pomiar SHADOW/CS2 trwa (z niego jest kalibracja) |
| D3 | Bet Buildery są dziś wybierane w całości ceną: pula po `leg_ev` (`confidence.py:829-849`, `run_confidence.py:858`), kolejność po `ev_after_haircut` (`:925`, PDF `build_coupon_pdf.py:361`), stawialność = EV > 0 po haircucie (`confidence.py:1328-1350`) | **Wybór bez ceny: pula po pewności, kolejność po `combined_probability`; stawialność = x po haircucie ≥ 0,90** (ten sam filtr co single). Alternatywa: buildery bez zmian jako świadomy wyjątek od zasady 2 |
| D4 | Buildery na PDF | **Osobne strony; przy bloku meczu odsyłacz „Bet Builder: #k”** |
| D5 | Poranne pliki 10-05: WARIANT, kupony sportowe, WSZYSTKIE (jeśli `/sofa-day` je zbuduje) | **Zostają jako zapis, rozliczane po staremu. Opcja: przerwać trwający `/sofa-day` przed krokami WARIANT/kupony sportowe/WSZYSTKIE — o 05:44Z nie były jeszcze zbudowane** |
| D6 | Rynki tenisa z ratingiem (`RATED_MARKETS`: games_total, games_won_for, sets_total, handicap_games). Krzywe tenisa są w 98,8% z replay bez ceny i bez ratingu (estymator próbki) | **Za datą graniczną p = estymator próbki (jak w krzywej), rating wyłączony z p** — inaczej drukowana pewność nie pasuje do krzywej. Alternatywa: najpierw zmierzyć kalibrację samego ratingu na rozliczonych wierszach live |
| D7 | Dogrywka w piłce (rożne, kartki itd. pomijane dziś przy meczach 110/120) | **Bez zmian, dopóki nie zostanie sprawdzone, czy `ALL` w `/statistics` zawiera dogrywkę (tylko 11 z 55 takich meczów w cache ma okresy) i jaka jest reguła Superbetu** |

---

## Część 2. Kolejność wykonania

1. Koniec `/sofa-day`: md5 wszystkich PDF i artefaktów 10-05 do
   `data/analysis_2026-10-05/md5_before.txt`.
2. **Faza A — K1–K9, przebudowa 10-05 zaraz po `/sofa-day`.** Każda godzina
   zwłoki to więcej nóg zablokowanych starą regułą (zaczęły się mecze).
3. **Część 4 (SETTLE) przed porannym rozliczeniem 10-06**, w kolejności: A1,
   A3 (zmieniają oceny), A2, A4–A5, potem 2B, 2C, 2D. Pętle `shadow_daily` i
   `cs2_daily` wołają `settle_shadow`/`settle_cs2` jako podprocesy — nowy kod
   zadziała przy ich następnym kroku porannym. Zmiany w ich własnym planie
   (B7) zadziałają dopiero w pętli uruchomionej po zmianie.
4. Recenzja adwersaryjna kodu po Fazie A i po Części 4.
5. Faza B — sport po sporcie, raport i decyzja operatora przed wejściem na kupon.

---

## Część 3. Faza A — jeden kupon ze statystyk (dziś)

**K0. Data graniczna i epoka.** `src/bet/sofa/epochs.py`:
`STATS_ONLY_FROM_UTC` (chwila wdrożenia, stała zapisana w kodzie),
`STATS_ONLY_DATE = "2026-10-05"`, `def stats_only(build_at_utc) -> bool`.
Kluczem jest czas BUILDU, bo 10-05 ma poranne buildy starą regułą.
`05_sheet.json` i `08_confidence.json` zapisują `"epoch": "stats_only"`.
CONFIDENCE w epoce stats_only odmawia (exit 2) SHEET bez tej epoki — zawsze
przebudowa od SHEET. Noga zablokowana zachowuje epokę buildu, w którym ją
wydrukowano (`printed_under`).

**K1. Cena znika z `p_central`** (za `stats_only`):
- `run_sheet.py:1012-1023` — środek ściągany do drabinki Superbetu
  (`K_TENNIS_LADDER_CENTRE`; dotyczy też metryk NB/normalnych tenisa);
- `run_sheet.py:1134-1139` — `blend_with_price` (rating tenisa z `market_p`);
- `run_sheet.py:1148-1161` — `p_empirical_shrunk_to_price`;
- `derived.py:556-570` — `K_DERIVED_CENTRE` / `_shrink_sides_to_diff`
  (wszystkie `handicap_*`, także piłka);
- `derived.py:610-615` — cena w ratingu tenisa dla handicap_games i most_games;
- rynki z ratingiem tenisa wg D6.
Krzywe: tenis 8,97 mln wierszy, 98,8% bez ceny (replay, estymator próbki, bez
ratingu i bez priorytetu poziomu); piłka 49,56 mln, ~206 tys. z ceną
(sprawdzone przez recenzenta zapytaniem do bazy). Dla rynków empirycznych K1
zrównuje dzień z krzywą; dla rynków z ratingiem — D6.
Test: dla każdego rynku niepochodnego `p_central` nie zależy od `market_p`;
dla `handicap_*` nie zależy po wyłączeniu `K_DERIVED_CENTRE`.

**K2. Filtry wg D1.** Za `stats_only`: bez `DISAGREES_WITH_PRICE`
(`confidence.MAX_DISAGREEMENT`), bez `UNREACHABLE_BAR`; `PRICE_MOVED_SINCE_SHEET`
(`run_confidence.py:493`) zastąpione przeliczeniem x na świeżym kursie;
`gap_shrink_k` zostaje 0. Test: noga z modelem 0,85 przy cenie 0,60 nie jest
odrzucana; noga, której x na świeżym kursie < 0,90, jest.

**K3. Kolejność, grupowanie, pozycje.**
- Funkcja czysta `confidence.coupon_order(singles) -> list[Block]`: blok =
  jeden mecz; bloki według najlepszej nogi (pewność malejąco, start rosnąco,
  id meczu); w bloku pewność malejąco, potem rynek, linia. Bez kursu w
  kluczu (dziś remis rozstrzyga `offered_odds`, `run_confidence.py:827-831`).
- **Artefakt zapisuje `singles` już w tej kolejności**, więc
  `printed_singles` = pozycje PDF 1..N; numer pozycji jest jeden dla PDF,
  odczytów i audytu.
- Nogi zablokowane (już grają) — osobna sekcja na górze PDF, bez numerów
  pozycji top 30.
- Test: remis pewności → wcześniejszy start wyżej; nogi jednego meczu razem,
  blok na miejscu najlepszej nogi; kolejność w artefakcie = kolejność PDF.

**K4. Top 30 + dodatkowe na życzenie.** `legs_requiring_read` (dziś
`confidence.py:708-718`): pierwsze 30 pozycji niezablokowanych wg
`coupon_order` ∪ nogi builderów ∪ pozycje z `runs/sofa/<d>/read_requests.json`
(`[{"position"|"sofascore_event_id", "market"?, "line"?, "direction"?,
"requested_by": "operator", "at_utc"}]`). `/sofa-analyze` przyjmuje
„dodatkowo: <numery pozycji>” → dopisuje do `read_requests.json`, analityk
sportu czyta, odczyty scalane, przebudowa. C3 czyta ten sam zbiór. Test.

**K5. Koniec WARIANT, WSZYSTKIE i kuponów sportowych.**
`ConfidenceProfile.retired_from_utc = STATS_ONLY_FROM_UTC` dla `wariant`;
`run_confidence` i `build_coupon_pdf` z `--profile wariant` odmawiają dla
nowszych buildów (exit 2). Profil zostaje dla starych dni (7d, ledger,
`run_settle.printed_keys`, refit go iterują). `run_multi_coupon.py` i
`run_sport_coupon.py` odmawiają po `STATS_ONLY_FROM_UTC`. Test.

**K6. WATCH rozliczany osobno.** Odmowa z `reads.json`
(`read_refusal`, dziś przed bramkami, `run_confidence.py:444`) przeniesiona na
koniec łańcucha bramek; noga, która przeszła wszystko i została usunięta przez
WATCH/NO_BET, trafia do `removed_by_reads` w artefakcie (pełna noga z kursem).
`audit_settlement.py` sekcja 7f i `record_results` wiersz `removed:reads` —
rozliczone jak 7c, nigdy w wyniku kuponu. Test.

**K7. Ledger i audyty.** `record_results.py`: wiersz `official` z polem
`epoch`; `wariant`/`multi` nie powstają dla buildów stats_only.
`audit_ledger.py` grupuje po (wariant, epoka): `do 10-04`, `10-05 rano`,
`stats_only`. `audit_variants.py`: C3 przez K4; M1–M2 wyłączone dla buildów
po `STATS_ONLY_FROM_UTC` (WSZYSTKIE 10-05 = zapis porannej wersji, md5 w
raporcie); nowe U1: kolejność artefaktu = `coupon_order`, U2: brak nogi bez
epoki stats_only poza zablokowanymi. `audit_day_deep.py` wg nowych bramek.

**K8. Kontrakty** (ładują się w nowej sesji): `CLAUDE.md` (sekcja decyzji;
reguły twarde o WARIANT, kuponach sportowych, WSZYSTKIE, „pewność bez
ceny”), `.claude/commands/sofa-day.md`, `sofa-analyze.md`, `sofa-rebuild.md`,
`sofa-verify.md`, `sofa-settle.md`; agenci `sofa-runner`, `sofa-verifier`,
`sofa-settler`, oba analityczne; skille `sofa-pipeline` (+ `references/`),
`sofa-analysis-core`; `docs/sofa/AGENTIC_FLOW.md`, `docs/sofa/PIPELINE.md`.

**K9. Przebudowa 10-05:** SHEET → COUPON → CONFIDENCE → PDF, odczyty
analityków dla nowego top 30, weryfikacja, md5 po. Nogi wystartowane z
porannego PDF zostają zablokowane (12263aac / f3045824).

---

## Część 4. Naprawa SETTLE (przed rozliczeniem 10-06)

### 4A. Piłka i tenis

Stan: tożsamość meczu poprawna — grupowanie po `sofascore_event_id`
(`run_settle.py` main l. 701), świeże `/event/{id}` (`_event_payload`, l. 178);
wg agenta 6735 meczów bez zamiany drużyn.

**A1. Mecz przesunięty o > 48 h jest rozliczany** (Everton 09-24, sprawdzone).
- `src/bet/sofa/settle.py`: `VOID_AFTER = timedelta(hours=48)` przeniesione z
  `shadow.py:119` (import w obu miejscach) i
  `moved_beyond_void(event, kickoffs) -> bool`: `startTimestamp` minus
  najwcześniejszy zegar (`02_fixtures.kickoff_utc`, `superbet_kickoff_utc`,
  `superbet_kickoff_seen_utc`; jak `locked_print.kickoff_clocks`) > 48 h.
- `run_settle.py` po `_event_payload`: → powód pominięcia
  `MOVED_BEYOND_VOID` w `07_settle_skips.json` (jak PUSH, `run_settle.py:322-338`);
  **wiersz w `sofa_settled_row` nie powstaje** (nie zapisywać
  `outcome='VOID'`: 7c liczy go jako przegraną, `fit_confidence.py:162-167`
  ignoruje `outcome`).
- 7c (`audit_settlement.py`), ledger (`record_results.py`,
  `settle_multi_coupon.py:47-96`) czytają ten powód i liczą nogę jako
  **ZWROT (0 j.)**, osobno od „nierozliczone”.
- Dane wstecz: nowa flaga `regrade_settled.py --moved-void` (skrypt nie ma
  `--from/--to`). Klucz `UNIQUE` nie zawiera `run_date` (`settle.py:394-406`),
  więc: jeśli tablica dnia faktycznego rozegrania wyceniła ten klucz →
  przenieść `run_date` na ten dzień; inaczej usunąć wiersz z kopią w
  `runs/sofa/regrade_<ts>.json`. Wypisać zmienione nogi wydrukowane.
  Potem `record_results.py --from 2026-09-18 --to 2026-10-04`.
- Tenis: mecze przesunięte o 24–48 h (wg agenta 18) zostają rozliczane;
  reguła Superbetu niezweryfikowana — otwarte.
- Testy: +66 h → `MOVED_BEYOND_VOID`, brak wiersza, 7c i ledger = zwrot;
  +47 h → rozliczone; `--moved-void` przenosi albo usuwa z kopią.

**A2. Props zawodnika z niewłaściwego składu** (`_settle_player`, l. 353; wg
agenta 6 z 1647 par pasuje do obu składów). Id gracza w danych nie ma
(`03_samples.json` → `players[...]` ma `player`, `matched_name`, `side`,
`squad_matches`). Dopasowanie tylko w składzie strony z
`players[metric|subject].side`; trafienie także w drugim składzie →
`PLAYER_AMBIGUOUS` (pominięcie). Test: „Weverson” (gość) nie z „Reverson”
(gospodarz); nazwisko w obu składach → `PLAYER_AMBIGUOUS`. Dane wstecz:
`regrade_settled.py --players` (nowa flaga), lista zmian.

**A3. Mecz przyznany (`isAwarded: true`).** **Tylko w ścieżce SETTLE**: nowa
`settle.settle_completed(event)` = `is_completed_event` ∧ ¬`isAwarded`;
`is_completed_event` (l. 104) zostaje bez zmian, bo czytają ją też
`samples.py`, `football_rating.py`, `calibrate_from_cache.py`,
`tennis_prior.py`, `run_backfill.py` (zmiana historii w środku epoki refitu).
Powód `AWARDED` = zwrot. To samo w `shadow.build_result`. Test. Dane wstecz:
w cache 1 przypadek (siatkówka 17238228).

**A4. Zablokowana noga bez wiersza SHEET.** `rows_to_consider` (l. 654) już
rozlicza wydrukowane klucze obecne w SHEET. Gdy wiersza nie ma (OFFER po
starcie usunął mecz, `run_sheet.py:1581`): ocenić z `/event` i zapisać do
`runs/sofa/<d>/07_settled_printed.json` — **nie do `sofa_settled_row`**
(kolumny NOT NULL `sample_mean`, `sample_sd`, `p_bar` są nieznane, a wiersz
nie może zasilać krzywych). 7c i ledger czytają oba źródła. Test.

**A5. 7c i ledger biorą wiersze z innej daty z różnych zbiorów**
(`audit_settlement.py:359-361` z SHEET, ledger z wydrukowanych). Oba z
wydrukowanych kluczy (+ A4). Test: ten sam wynik w obu.

**A6.** Dogrywka — wg D7, bez zmian do sprawdzenia.

**A7.** `run_settle.py --date 2026-10-03` (mostek; 2 nogi WARIANT
`SUBJECT_NOT_MATCHED` naprawione 10-04), potem ledger.

### 4B. Hokej, koszykówka, siatkówka

Stan: po znalezieniu meczu ocena idzie tylko po id (`grade_coupon`
`sport_coupon.py:1125` po id Superbetu do zapisanego wyniku); słabe jest
znajdowanie (`find_event`, `settle_shadow.py:381`).

**B0. Jeden zbiór stanów** w `bet.sofa.shadow`: `TERMINAL`, `RETRYABLE`,
`EXCLUDED` (nieliczone nigdzie), importowany przez `settle_shadow`
(dziś l. 97), `settle_cs2` (l. 80), `settle_sport_coupon`, `record_results`
(`FINAL_STATES` l. 61-63). Nowe stany: `DUPLICATE_SOFASCORE_ID`, `WITHDRAWN`,
`ID_CHANGED`, `MOVED_TO`, `AWARDED`, `AMBIGUOUS_START`. Test: ledger ich nie liczy.

**B1. Jedno id Sofascore dla dwóch meczów Superbetu** (sprawdzone: 16885527).
Przy zapisie `settled.json` sprawdzać unikalność `sofascore_event_id` w
plikach D-1..D+1 sportu. Kolizja: zostaje rekord, w którym obie nazwy
przechodzą próg (`fuzz > 82` lub alias) i którego ostatni snapshot Superbetu
jest najpóźniejszy; reszta → `DUPLICATE_SOFASCORE_ID` z `duplicate_of`.
Mecz wycofany (ostatni snapshot > 2 h przed startem, ta sama para drużyn
później pod innym id) → `WITHDRAWN`. Test.

**B2. Nazwa szukanej drużyny nie jest sprawdzana** (`resolve.py:684-700`;
przykład wg agenta „U. De Santiago” → Universidad Católica, id zdarzenia
17207292 sprawdzone, nazwy nie). Zmiana **tylko w gałęzi
`SPORT_SCOPED_SEARCH`** (ta część `resolve.py` służy też RESOLVE piłki i
tenisa): zdarzenie przyjęte, gdy szukana drużyna przechodzi próg względem
swojej strony i przeciwnik względem drugiej, albo przy `MUTUAL_LISTING`.
Reguła jednego wspólnego słowa (`shadow_opponent_agrees`, `resolve.py:257`):
słowo ≥ 5 znaków spoza listy pospolitych/geograficznych
(`config/sofa_name_stopwords.json`: texas, miami, carolina, state, tel, aviv,
city, united, university, universidad, sporting, club, real, …) i tylko
razem z warunkiem nazwy szukanej. Bez zapisu `verified` w cache z dopasowań
przez wspólne słowo i `TOURNAMENT`; błędny wpis „u. de santiago” → 233778
usunięty skryptem z `--dry-run`. Pomiar przed/po: odsetek SETTLED na
10-01..10-04 (żeby nie stracić prawdziwych par) i recall RESOLVE piłki/tenisa
bez zmian. Testy: „hapoel tel aviv” vs „maccabi tel aviv” odrzucone; prawdziwe
pary z 10-01..10-04 (zamrożone przykłady) nadal przyjęte.

**B3. Id przypięte.** Rekord z zapisanym id przy ponownej próbie: `/event/{id}`
wprost, bez szukania; inne id z szukania → `ID_CHANGED`, stare oceny
zostają. Test.

**B4. Ten sam mecz w plikach dwóch dat** (np. koszykówka 15132383 w 10-02 i
10-03, wg agenta). Starszy rekord → `MOVED_TO:<data>`, poza
`record_results.measure_rows` i `rule_rows` (l. 229-235). Test.

**B5. `UNUSUAL` (hokej 15025409, status-glitch).** Ze zbioru `TERMINAL` do
`RETRYABLE` do give-up; przyjęty, gdy `status.type == finished`, wynik spójny
(`build_result`) i nie walkower, krecz, `isAwarded`. Test.

**B6. Orientacja:** porównać id zdarzenia i id drużyn listingu z `/event`;
niezgodność → oceniane tylko linie niezależne od strony. Test.

**B7. `shadow_daily.py:66-85`:** przegląd D-7..D-3 dla rekordów
nieterminalnych (jak `settle_cs2 --sweep`).

### 4C. CS2

Stan: w danych 09-28..10-04 zero pomieszań (wg agenta 218 id, unikalne).
`pick_event` (`cs2.py:675`) wymaga obu nazw powyżej progu (l. 695-697).

**C1. Odstęp startu niekontrolowany** (`MATCH_WINDOW` 6 h, l. 66): kandydat
> 1 h od startu Superbetu odrzucony (`AMBIGUOUS_START`), jeśli Superbet miał
snapshot przedmeczowy później niż start Sofascore + 15 min. Rekord zapisuje
`start_gap_h`. Test: Hotu – Black Phoenix 12:15 przy starcie 18:00 i snapshocie
17:30 → odrzucone.

**C2. Id serii przypięte** (`settle_one`, `settle_cs2.py:191`) jak B3. Test.

**C3. Składy „ex-”** (`esports_score`, l. 637): „ex” jako znacznik składu;
znane przypadki aliasami całych nazw. Test.

**C4. Niezagrana mapa** → zwrot zamiast `UNGRADEABLE` (`actual_value` l. 885,
`sport_coupon._grade_leg`). Test.

### 4D. Wspólne

**D-a.** Nowy skrypt `audit_settle_identity.py` (w `scripts/sofa/`; komendę
dopisać do CLAUDE.md dopiero razem ze skryptem — test dokumentowanych komend):
id użyte > 1 raz, start przesunięty > 48 h a oceniony, wynik nazw < 82 po
którejkolwiek stronie, `ID_CHANGED`, `DUPLICATE_SOFASCORE_ID`, `MOVED_TO`.
Exit 1 przy znalezisku. Wołany w `/sofa-day` po rozliczeniu D-1 i w
`/sofa-settle`.
**D-b.** Każde dopasowanie (shadow, CS2) zapisuje `match_method`,
`name_scores` (obie strony), `start_gap_h`, `matched_at_utc`.
**D-c.** Po 4A–4C: regrade offline z cache, lista dat do ponownego
rozliczenia z mostkiem, na końcu `record_results.py --from 2026-09-18 --to 2026-10-05`.

---

## Część 5. Faza B — pozostałe sporty ze statystyk

Zakres: rynki z wyniku — suma meczu, suma drużyny, handicap, zwycięzca/1X2,
okresy/kwarty/sety, rundy i mapy CS2. Historia jest tylko wynikowa
(`score_model.load_history`: wynik, okresy, sety; wg
`MODELE_HOKEJ_KOSZ_SIATKA.md:326` ok. 27 tys. / 46 tys. / 14 tys. meczów;
CS2 16 826 serii, 24 987 map z rundami). Propsy i inne statystyki poza zakresem.

- **B1** Tożsamość przed meczem regułą z 4B (obie nazwy, unikalność, dowód) →
  `runs/sofa/<d>/sport_fixtures.json`. Nierozpoznany = poza kuponem.
- **B2** Próbki: ostatnie 10 meczów ligowych drużyny (`bet.sofa.comparability`,
  bez sparingów).
- **B3** `p_raw = trafienia / n` na linii („w 9/10 meczach powyżej 5,5”);
  dla każdego rynku zdefiniowany wynik rozliczenia zgodnie z `MarketSpec`
  w `shadow.py` (hokej: czas regulaminowy vs z dogrywką).
- **B4** Kalibracja bez cen: replay chronologiczny, linie z siatki wokół
  środka próbki (jak `calibrate_from_cache.lines_for` — snapshoty Superbetu
  są dopiero od 09-28/29, więc nie mogą być źródłem linii dla historii) →
  krzywa per sport × rodzina rynku, dolna granica Wilsona, `EDGES` jak
  `fit_confidence` → `config/sofa_sport_confidence_calibration.json` z
  `fitted_from`.
- **B5** Pomiar poza próbą: ostatnie 30 dni historii odłożone, oraz linie
  Superbetu z SHADOW/CS2 od 09-28/29 (rozliczone). Uwaga: przy 10 meczach
  linia blisko mediany daje częstość < 0,60 — nogi ≥ 0,70 będą głównie z linii
  alternatywnych i faworytów.
- **B6** Bramka: w każdym kubełku z n ≥ 200 krzywa poza próbą w ±3 pp od
  zrealizowanego. Inaczej sport zostaje poza kuponem. Wejście — decyzja
  operatora po raporcie.
- **B7** Wejście: pewność = krzywa, filtry D1, kolejność/grupowanie/top 30
  jak piłka; analityk sportu (rozszerzony `sofa-sport-runner` lub nowy
  `sofa-analyst-<sport>`); rozliczenie przez naprawiony SETTLE po zapisanym id.
  Siatkówka: reguła rozliczonego turnieju (14 dni) zostaje.

---

Poza planem: reguła kreczu (bez zmian), propsy piłkarskie (zostają),
refit krzywych (osobna decyzja).
