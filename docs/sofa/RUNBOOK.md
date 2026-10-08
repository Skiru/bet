# `sofa` — runbook operatora

Jak przeprowadzić jeden dzień zakładowy. Mechanika etapów jest
w [`PIPELINE.md`](PIPELINE.md), role agentów w
[`AGENTIC_FLOW.md`](AGENTIC_FLOW.md). Tutaj jest **kolejność działań, czas
i decyzje**.

Skrót operacyjny: **`/sofa-day`**. Ten plik mówi, co ta komenda robi i co
zrobić, gdy coś pójdzie inaczej.

Kolejność `/sofa-day` (od 2026-10-05, jeden kupon ze statystyk):

1. `ensure_bridge.py` (część 0);
2. rozliczenie D-1 + `audit_settle_identity.py` (część 1);
3. dziennik: `record_results.py`, `audit_ledger.py`, `audit_clv.py` (część 1);
4. BOARD..COUPON (`run_pipeline.py`, część 2);
5. CONFIDENCE piłki i tenisa (`run_confidence.py`, 2a);
6. świeże migawki `run_pipeline.py --only SHADOW` i `--only CS2`, potem
   SPORT_IDENTITY (most) i SPORT_CONFIDENCE (2b);
7. COUPON_ASSEMBLY (`build_coupon.py` → `11_coupon.json`, 2c);
8. analitycy na `legs_requiring_read` (top 30 + nogi builderów +
   `read_requests.json`): `sofa-analyst-football`, `sofa-analyst-tennis`,
   `sofa-analyst-sport` per sport mierzony (część 3);
9. scalenie wet i odczytów, przebudowa jednym poleceniem
   `rebuild_day.py` (stare ceny odświeżone najpierw, potem FIXTURE_CHECK →
   CONFIDENCE → SPORT_CONFIDENCE → `build_coupon.py` → PDF, pisze
   `12_printed.json`, → `audit_variants.py` + `audit_coupon.py`) (część 4);
10. `audit_coupon.py`, `audit_variants.py` (C1–C3, U1–U3), `sofa-verifier`,
    dopisanie jego odczytów, przebudowa `rebuild_day.py` (część 5);
11. raport (część 8).

---

## 0. Zanim cokolwiek ruszy

```bash
date -u +%F                                             # doba zakładowa kuponu jest w UTC
.venv/bin/python scripts/sofa/ensure_bridge.py          # most, ZAWSZE pierwszy: podnosi go, potem check_bridge
```

Most: **`ok: true` nie wystarcza.** Martwa karta przeglądarki nadal melduje
`ok`. Liczy się **wiek ostatniego pobrania**. Jeśli karta nie żyje — poza BOARD,
OFFER i etapami offline nic nie ruszy. Nie próbuj obejścia i **nie zmieniaj
`SOFA_TARGET_RPS` (20) ani `SOFA_MAX_CONCURRENCY` (5)**.

Od 30.09 `/sofa-day` **sam podnosi most** na starcie tym właśnie
`ensure_bridge.py` (serwer w tle, 5 okien, jeśli trzeba; potem
`check_bridge`).

Działającego mostu nie rusza. Jeśli Chrome jest już otwarty bez flag mostka,
skrypt się zatrzymuje (exit 2): zamknij Chrome całkowicie (Cmd+Q) i uruchom
krok jeszcze raz — agent nigdy nie zamyka przeglądarki operatora.

Kody wyjścia: `0` most działa; `1` działa, ale źle — `check_bridge` zgłosił
FAIL albo karta odpytuje z Chrome'a uruchomionego bez flag (ok. 1 zapytanie/s;
Cmd+Q i powtórz); `2` nie udało się go podnieść (komunikat mówi, co zrobić).
`0` nie wyklucza linii WARN — `check_bridge` kończy się `0` także przy WARN,
więc zawsze przeczytaj wiek ostatniego pobrania.

Ręcznie (to samo, krok po kroku):

```bash
# serwer umiera razem z terminalem, który go uruchomił — na długi przebieg odetnij:
nohup .venv/bin/python scripts/sofa/bridge_server.py >> runs/sofa/bridge_server.log 2>&1 &
.venv/bin/python scripts/sofa/launch_bridge_browser.py --windows 5   # Chrome musi być najpierw całkiem zamknięty
```

1. okna otwiera `launch_bridge_browser.py` — z flagami, bez których Chrome
   dławi kartę w tle do ~1 req/s; okna mogą być zminimalizowane, nie muszą
   być widoczne;
2. liczba okien = `SOFA_MAX_CONCURRENCY` (5) — mniej okien niż workerów to
   zapaść mostu (tabela w CLAUDE.md), nie wolniejszy przebieg;
3. karty same zaczynają odpytywać serwer — to one wykonują żądania, nie
   proces pythonowy;
4. `check_bridge.py` ponownie: trzy kontrole OK **i świeży wiek pobrania**.

`check_bridge.py` sprawdza cztery rzeczy w kolejności i mówi, która padła:
(1) serwer nasłuchuje, (2) jakaś karta go odpytuje — `last_pull_age_s`,
powyżej **30 s** dostajesz `WARN`, (3) prawdziwe zapytanie `/api/v1/` wraca 200
z JSON-em. **403 w punkcie trzecim znaczy przeterminowany `x-captcha` karty** —
przeładuj `sofascore.com`, nie zmieniaj niczego w kodzie. Trzy pierwsze muszą
być OK; czwarta (INFO, krótki burst z bezczynności) nie jest oceną — błędem
jest tylko `WARN … burst probes FAILED`.

Interpreter: `.venv/bin/python` (3.12). `.venv/bin/pip` należy do 3.14
i instaluje tam, gdzie nikt tego nie zaimportuje — instaluj przez
`.venv/bin/python -m pip`.

---

## 1. Rozlicz wczoraj (D-1)

Przed dzisiejszym dniem, bo to karmi kalibrację i **konkuruje o most**.

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only SETTLE
# pętla CS2 D-1 robi to sama o 05:00Z, a dzisiejsza ponawia D-1 jutro rano (cs2_watchdog.py ponawia co godzinę, jeśli ktoś go uruchomił
# dla tej daty - `pgrep -f cs2_watchdog`; domyślnie nic go nie startuje); ręcznie tylko, gdy istnieje
# runs/sofa/cs2/daily_<D-1>.done albo pid z daily_<D-1>.pid nie działa, i żaden watchdog nie pilnuje D-1:
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only CS2_SETTLE
# serie wciąż czekające z D-7..D-2 (pętla robi to sama; tylko daty, których settled.json ma czekającą serię):
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_cs2.py --sweep-from <D-7> --sweep-to <D-2>
# pętla D-1 robi to sama o 05:15Z; ręcznie tylko, gdy nie żyje (brak runs/sofa/shadow/daily_<D-1>.pid
# albo jego pid nie działa) - wznawia się, więc powtórka nie szkodzi, równoległa tak:
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only SHADOW_SETTLE
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settlement.py --date <D-1>
# Luki statystyk zamykają się po kilku dniach (2026-10-01): Sofascore publikuje rożne/strzały/faule niższych lig
# kilka dni po kartkach (National League, Primera B Nacional: D+5..D+7), a samo D-5 zostawiało wydrukowane nogi
# bez rozliczenia (F0.6) - więc co rano przegląd: każdy dzień D-14..D-2 z wydrukowaną nogą, którą SETTLE może
# jeszcze rozliczyć, i zawsze D-5 (jego niewycenione wiersze czytają fity), z --refetch-stat-gaps, potem raz
# regrade_settled.py --apply. Wymaga mostka: wyjście 1 z NO_BRIDGE = nic nie rozliczono ponownie:
PYTHONPATH=src:. .venv/bin/python scripts/sofa/resettle_sweep.py --from <D-14> --to <D-2> --include-day <D-5>
# przypięte id sportów mierzonych (ID_USED_TWICE, MOVED_GRADED, NAME_BELOW, ORIENTATION_IDS, ID_CHANGED, ...):
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settle_identity.py --from <D-1> --to <D-1>
# dziennik:
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_shadow.py --from <D-1> --to <D-1>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_cs2.py --from <D-1> --to <D-1>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --from <D-8> --to <D-1>        # dziennik: runs/sofa/ledger/results.jsonl; zastępuje wiersze obu dat
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <D-7> --to <D-1>          # odczyt dziennika: tabela na grupę i epokę, nigdy łącznie; ROI z przedziałem 95% po meczach („-” poniżej 20 meczów)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_clv.py --from <D-2> --to <D-1>             # CLV kuponu — pierwsza liczba o wczoraj
```

Kody wyjścia `record_results.py` i `audit_settle_identity.py`: **0** =
rozliczone na tyle, na ile pozwalają settle — pozycje oczekujące widać w
tabeli (kolumna `pending`), nigdy w kodzie wyjścia. To normalny stan D-1:
nogi sportów mierzonych po 00:00Z (NHL/NBA, nocne CS2) rozliczają się w pliku
migawek następnego dnia — pętla CS2 o 05:00Z rozlicza D i D-1 i przegląda
D-7..D-2 (`settle_cs2.py --sweep-from/--sweep-to`), pętla shadow o 05:15Z
rozlicza D, D-1 i D-2 (D-2: przełożony mecz staje się `VOID` dopiero 48 h po
starcie); jutrzejsze `--from <D-8>` je domyka. **1** = `MISMATCH` (dwa
oceniające nie zgadzają się co do nogi — defekt, nazwij go), nieczytelny plik
albo, w `audit_settle_identity.py`, znalezisko tożsamości. **2** = awaria
albo brak bazy. Zanim SHADOW_SETTLE / CS2_SETTLE zapisze `settled.json`,
wiersza `measure:<sport>` po prostu nie ma w dzienniku — sprawdź, czy są
wszystkie wiersze `measure:*`, nie tylko kod wyjścia. Po późnym rozliczeniu
albo `regrade_settled.py` powtórz `record_results.py --from <D-8> --to <D-1>`
— zastępuje wiersze tych dat.

Wiersze dziennika `wariant` / `multi` / `sport:<sport>` / `rule:<sport>` to
wycofane warianty dni do 2026-10-05; czyta się je, nigdy nie łączy.

Potem pętle dzisiejszego dnia:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <today> --only CS2
# cały dzień CS2 bez obsługi (ceny do 23:30Z, o 05:00Z D+1 settle D i D-1, przegląd D-7..D-2, dziennik za D-7..D);
# --chain o 23:30Z startuje pętlę D+1 (nocne serie D+1 mają ceny); pętla D-1 z --chain już ją uruchomiła,
# a druga pętla dla daty odmawia (kod 2), więc powtórka nie szkodzi:
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/cs2_daily.py --date <today> --chain >> runs/sofa/cs2/daily_<today>.log 2>&1 &
# pętla D-1 z --chain sama startuje dzisiejszą po swoim rozliczeniu i audycie (ok. 05:20–05:45Z); ręcznie tylko, gdy nie ma
# ani runs/sofa/shadow/daily_<D-1>.pid, ani daily_<today>.pid:
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/shadow_daily.py --date <today> --chain >> runs/sofa/shadow/daily_<today>.log 2>&1 &
```

- SHADOW / SHADOW_SETTLE to pomiar hokeja, koszykówki i siatkówki (jak CS2):
  migawki cen i rozliczenie linii. Od 2026-10-05 08:30Z z tych migawek
  powstają też nogi kuponu (SPORT_IDENTITY → SPORT_CONFIDENCE, krok 2b), a
  SETTLE nóg sportów idzie przez `settled.json` sportu po przypiętym id.
  `PARTIAL`/`FAILED` pomiaru nie blokuje kuponu piłki i tenisa. Druga pętla
  `shadow_daily.py` dla tej samej daty odmawia startu (exit 2), więc
  ponowne uruchomienie jest bezpieczne.
- Pętla czyta swój plan raz, przy starcie: pętla uruchomiona przed zmianą
  kodu wykonuje stare kroki poranne aż do końca (jej następczyni z `--chain`
  ma już nowy kod). Po zmianie `cs2_daily.py` / `shadow_daily.py` powtórz
  nowe kroki poranne ręcznie dla dni, które obejmują stare pętle, i napisz to
  w raporcie — nigdy nie zabijaj pętli, żeby złapała zmianę.

- `PARTIAL` to normalny werdykt.
- **Sekcja 7c audytu to prawdziwy wynik kuponu z PDF** — w dniu stats-only
  tabela per sport × epoka, tabela sportów mierzonych (po kursie z wydruku,
  po przypiętym id; inne id = `NOT_GRADED:ID_CHANGED`) i „Suma kuponu”.
  Sekcje 7 i 7b to materiał wejściowy (legi i kandydaci), **nie zakłady**.
- **Zwroty liczone osobno** (REFUND, 0 j.): `MOVED_BEYOND_VOID` (mecz
  przesunięty o > 48 h), `AWARDED` (przyznany), `RETIRED` (krecz) i
  `WALKOVER` (walkower) — nigdy przegrana, nigdy `sofa_settled_row`
  (`07_settle_skips.json`).
- **7i „Nogi zdjęte przez odczyt”** — `removed_by_reads` z `11_coupon.json`,
  rozliczone osobno, nigdy w wyniku kuponu (dziennik `removed:reads`).
- Noga wydrukowana bez wiersza arkusza rozlicza się do
  `07_settled_printed.json`, nie do `sofa_settled_row`. Propsy zawodników
  tylko ze składu zawodnika (`PLAYER_AMBIGUOUS` w przeciwnym razie).
- `07_settle_skips.json`: wiersz, którego nie dało się ocenić, **nie jest
  przegraną**.

Głębiej i z decyzją o fitowaniu: `/sofa-settle` albo agent `sofa-settler`.

---

### 1a. Odśwież dowód z linii (co rano, po kroku 1)

Po rozliczeniu i zapisaniu D-1, **przed** pierwszym buildem dnia:
`PYTHONPATH=src:. .venv/bin/python scripts/sofa/refresh_line_evidence.py --before <D>`
(~15-20 min, bez mostu; cztery fity wierszy sportowych z `--dry-run` i
`fit_line_evidence.py`; nie dotyka krzywych). Exit 0 zapisano; **1** — fit
jednego sportu nie wyszedł i został jego poprzedni zestaw wierszy (dowód i tak
zapisany); **2** — crash `fit_line_evidence.py` (plik bez zmian, dzień czyta
wczorajszy dowód — powiedz to w raporcie). `fitted_from.before` pliku
`config/sofa_superbet_line_evidence.json` musi być równe `<D>`. To **nie** jest
refit krzywych.

## 2. Dzisiaj

BOARD dotyka tylko Superbetu, więc może iść, gdy SETTLE trzyma jeszcze most.

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <data> --only BOARD --run-id <id>
# gdy CAŁY krok 1 (settler) skończy - nie tylko proces --only SETTLE: późniejsze skrypty settlera
# czytają bazę, a 2026-10-01 RESOLVE padł obok nich na 'database is locked'. FAILED zatrzymuje dalsze
# etapy (SKIPPED), a przerwany RESOLVE zostawia 02_fixtures.json.INCOMPLETE - wtedy RESOLVE jeszcze raz.
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <data> --from-stage RESOLVE --run-id <id>
```

**Jeden `--run-id` na cały dzień**, inaczej log rozpada się na dwa przebiegi.

Budżet: **2,5–3 h**, z czego większość to SAMPLES. Obserwuj przejścia etapów,
nie odpytuj w pętli:

```bash
tail -f -n 0 <log> | grep -E "^--- |: OK|: PARTIAL|: FAILED|STAGE_EXCEPTION|Traceback"
```

Kody wyjścia: **0 OK, 1 PARTIAL, 2 FAILED**.
**`PARTIAL` na RESOLVE / OFFER / SAMPLES to normalny kształt zdrowego
przebiegu.** Zatrzymuje wyłącznie `FAILED`.

### Dwa alarmy, które zwykle są fałszywe

| alarm | co sprawdzić naprawdę |
|---|---|
| `coverage_floor`: „matching regression" | Jest ślepy na dzień tygodnia (mediana z 10 ostatnich przebiegów, `MAX_DROP = 0.40`). Sprawdź wskaźnik RESOLVE: **72–90% jest zdrowe**. |
| „tablica się zapadła" | Rozmiar tablicy to kalendarz: 1040 meczów piłki w niedzielę, 102 w poniedziałek. Zweryfikuj surową odpowiedzią Superbetu. |

### 2a. CONFIDENCE — piłka i tenis

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <data>     # -> 08_confidence.json
```

CONFIDENCE nie jest etapem `run_pipeline.py` (nie ma `--only CONFIDENCE`).
W epoce stats-only odmawia (kod 2) arkusza zbudowanego nie pod tą regułą —
wtedy przebudowa zaczyna się od SHEET.

### 2b. Sporty mierzone na kuponie (od 2026-10-05 08:30Z)

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <data> --only SHADOW      # świeża migawka hokej/kosz/siatka (Superbet)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <data> --only CS2         # świeża migawka CS2 (Superbet)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_identity.py --date <data>              # SPORT_IDENTITY, most -> sport_fixtures.json
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_confidence.py --date <data>            # SPORT_CONFIDENCE, bez mostu -> 08_confidence_sports.json
```

- **SPORT_IDENTITY** pyta raz na mecz `team/<id>/events/next/0` przez most i
  przypina id Sofascore (`IDENTIFIED`; obie nazwy powyżej progu, start ±1 h,
  unikalność w dniu). Rekord `IDENTIFIED` nie jest pytany ponownie; po nim
  rozlicza SETTLE. Czyta migawki D i D+1. `--sport hockey --sport cs2`
  zawęża. Kod 1 = mecz nierozpoznany albo odmowa mostu; 2 = brak migawki
  żadnego sportu. 403 = przerwać, nie ponawiać.
- **SPORT_CONFIDENCE**: pewność = dolna granica Wilsona kubełka kalibracji
  (`config/sofa_sport_confidence_calibration.json`) prawdopodobieństwa
  modelu wyników / silnika CS2; potem filtry ceny: pewność ≥ 0,70, kurs ≥
  1/0,9202, marża grupy ≤ 15%, x ≥ 0,90, cena przed startem nie starsza niż
  3 h (`STALE_PRICE`), lista dozwolonych rynków (`MARKET_NOT_ALLOWED`),
  siatkówka tylko z turnieju z meczem SETTLED w ostatnich 14 dniach. Kod 1,
  gdy sport jest `NOT_CALIBRATED` albo brak `sport_fixtures.json` — artefakt
  i tak powstaje, kupon piłki i tenisa buduje się dalej.

### 2c. COUPON_ASSEMBLY — jeden kupon

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon.py --date <data>     # -> 11_coupon.json (+ 11_coupon.md), offline
```

`11_coupon.json` = `08_confidence.json` + `08_confidence_sports.json` w
kolejności `confidence.coupon_order` (pewność, potem wcześniejszy start, nogi
meczu razem), pozycje 1..N, nogi zablokowane z poprzedniego wydruku na górze
bez numeru, buildery B1.., `removed_by_reads`, kopia `read_requests`. Odmawia,
gdy `08_confidence.json` nie jest profilu kuponu (`COUPON_PROFILE`) w epoce stats-only albo jest
starszy niż arkusz, weta, odczyty lub kalibracja.

---

## 3. Analitycy, weta i odczyty

Analitycy biegną **po COUPON_ASSEMBLY**, na `11_coupon.json`. Czytają zbiór
`confidence.legs_requiring_read`: pierwsze 30 pozycji niezablokowanych (od 2026-10-09 00:00Z jednostką jest mecz: wszystkie niezablokowane nogi 30 pierwszych meczów kuponu, `read_unit: "event"` w artefakcie),
każdą nogę wydrukowanego buildera i to, o co operator poprosił w
`runs/sofa/<data>/read_requests.json`.

```
Task → sofa-analyst-football   "data <data>; run <run_id>; werdykty etapów; nogi piłki do przeczytania"
Task → sofa-analyst-tennis     "data <data>; run <run_id>; werdykty etapów; nogi tenisa do przeczytania"
Task → sofa-analyst-sport      "data <data>; sport hockey; nogi do przeczytania"    (jeden na sport z nogą w zbiorze)
```

Wszystkich w **jednej wiadomości**, żeby szli równolegle. Scal ich tablice
JSON — weta do `runs/sofa/<data>/vetoes.json`, odczyty do `reads.json` —
**najpierw walidując** (`Veto`, `LegRead`: jeden wymyślony klucz wywraca cały
plik). Noga sportu mierzonego schodzi odczytem `NO_BET` / `WATCH` (ma stronę
i okres), nie wetem.

Zgłoś każde `UNMATCHED_VETO` i `UNMATCHED_READ`: nic nie zrobiło, a cichy
no-op czyta się identycznie jak weto uszanowane. Odczyt nogi sportu jest w
`run_confidence.py` zawsze `UNMATCHED_READ` (widzi tylko piłkę i tenis) —
sprawdź go w `11_coupon.json` (`removed_by_reads`, pole `reads`). **`[]` to
zdrowa wartość domyślna wet.**

Dodatkowe odczyty na życzenie operatora: `/sofa-analyze` „dodatkowo:
<pozycje>” dopisuje do `read_requests.json` wpisy `{"position": n}` albo
`{"group_key": "sofa:<id>", ...}` z `requested_by` i `at_utc` (forma
`group_key` przeżywa przesunięcie pozycji). Prośba, która nic nie objęła,
drukuje `UNMATCHED_READ_REQUEST`.

Ten krok wolno pominąć tylko na wyraźną prośbę operatora — i trzeba wtedy
powiedzieć, że się go pominęło (C3 to pokaże).

---

## 4. Przebudowa i PDF

Przebudowa to **jedno polecenie** (plan production grade F0.2) — nigdy
ręczny ciąg skryptów etapów. 2026-10-05 dwie przebudowy poszły na starych
cenach: CONFIDENCE na ofercie starszej niż 45 min opróżnił
`08_confidence.json` do nóg zablokowanych (`STALE_PRICE`), a SHADOW z
domyślnym horyzontem 3 h pominął mecz hokeja o 15:30Z.

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <data> --dry-run   # plan z powodami, nic nie uruchamia
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <data>             # przebudowa [--skip-audits]
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/capture_closing.py --date <data> --loop >> runs/sofa/<data>/capture_closing.log 2>&1 &   # cena zamknięcia nóg (CLV), bez mostu
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_boosts.py --date <data>   # boosty; powtórz kilka razy w ciągu dnia
```

Plan (`bet.sofa.rebuild_plan`, z wieku plików i zegara, bez sieci), po kolei:

- **OFFER** (`run_offer.py --min-minutes-to-kickoff 20`), gdy najstarsza
  cena meczu, który jeszcze można zagrać, jest starsza niż limit CONFIDENCE
  (`SOFA_PRICE_MAX_AGE_MIN`, 45 min) minus 15 min zapasu — przebudowa trwa
  minuty, a limit sprawdza CONFIDENCE, nie start przebudowy. Bez tego
  CONFIDENCE odrzuci każdą cenę (`STALE_PRICE`), a pusty wynik wygląda na
  wniosek analityczny. W epoce stats-only przesunięta cena nie odrzuca nogi,
  tylko przelicza x na świeżym kursie; SHEET po odświeżeniu nie jest
  potrzebny.
- **SHADOW** (`run_shadow.py --horizon-h <do najdalszego otwartego
  startu>`), gdy najnowsza cena otwartego meczu hokeja / kosza / siatki jest
  starsza niż `sport_day.MAX_PRICE_AGE` (3 h) minus 30 min albo ostatnia
  migawka pominęła mecz zaczynający się za jej horyzontem 3 h; **CS2**
  (`--only CS2`) na tej samej regule wieku; po świeżej migawce
  `ensure_bridge.py` + **SPORT_IDENTITY** (most).
- **SHEET** (`--only SHEET`) tylko, gdy CONFIDENCE by go odrzucił (arkusz
  nie zbudowany pod regułą stats-only, `epochs.sheet_epoch`). Zmiany kodu
  SHEET albo jego konfiguracji polecenie nie wykrywa — wtedy najpierw
  `run_pipeline.py --only SHEET` ręcznie i napisz, co go wymusiło.
- **COUPON** (`--only COUPON`, `06_coupon.json` — wejście `audit_coupon`, nie
  kupon) tylko, gdy jest starszy niż arkusz / weta / odczyty.
- potem `ensure_bridge.py`, **FIXTURE_CHECK**, **CONFIDENCE**,
  **SPORT_CONFIDENCE**, **COUPON_ASSEMBLY** (`build_coupon.py`), **PDF**
  (`build_coupon_pdf.py` → `KUPON_<data>.pdf` + `KUPON_<data>.html` + `12_printed.json`),
  `audit_variants.py`, `audit_coupon.py`.

Dzień zakończony (żaden mecz nie da się już zagrać): ceny nie są
odświeżane, plan mówi `DAY_OVER` — ceny są historyczne i każda bramka
cenowa je odrzuci, i to jest poprawne. Każdy krok to podproces z tym samym
poleceniem co w dokumentacji; jedna zwięzła linia na krok, pełne wyjście w
`runs/sofa/<data>/rebuild_<ts>.log`, na końcu `SOFA_SUMMARY` (`stage:
REBUILD`). Kod 0 OK / 1 PARTIAL / 2 FAILED: krok FAILED zatrzymuje dalsze
(SKIPPED, ich artefakty nietknięte) — poza krokami mostu (`ensure_bridge`,
FIXTURE_CHECK, SPORT_IDENTITY), migawkami sportów (SHADOW, CS2) i COUPON (06),
które dają PARTIAL. Odmawia przy ustawionym `SOFA_NOW`, honoruje
`SOFA_RUNS_DIR`. `--skip-audits` pomija oba audyty i mówi to w podsumowaniu.

- **FIXTURE_CHECK** (`run_fixture_check.py`, most) w każdej przebudowie, po
  OFFER, przed CONFIDENCE: `/event/{id}` dla meczów drukowanych i
  przesuniętych zegarów → `fixture_status.json`. Mecz przełożony / odwołany /
  przerwany → `FIXTURE_NOT_AS_SCHEDULED` (odmowa w CONFIDENCE); świeży start
  zastępuje zamrożony zegar RESOLVE dla bramki, blokady i
  `capture_closing`. Bez mostu: `UNVERIFIED`, nic nie odrzucone, kod 1.
  403 przerywa od razu.
- `build_coupon_pdf.py` odmawia (kod 2): `STALE_CONFIDENCE`, gdy
  `08_confidence.json` jest starsze niż `05_sheet.json`, `vetoes.json`,
  `reads.json` albo kalibracja; `STALE_COUPON`, gdy `11_coupon.json` jest
  starsze niż `08_confidence.json`, `08_confidence_sports.json` albo
  `read_requests.json`. W dniu stats-only bez `11_coupon.json` nie drukuje.
- PDF zapisuje `12_printed.json` — następna przebudowa blokuje z niego nogi,
  których mecz już się zaczął (noga wydrukowana przed startem się liczy);
  noga zdjęta przed startem zostaje zdjęta.
- Buildery: wybierane i porządkowane po `combined_probability`; stakeable,
  gdy `combined_probability` × kurs po narzucie 12% ≥ 0,90
  (`stakeable_rule` „x>=0.90”). **Czytaj `stakeable_builders`, nie
  `builders`.** Superbet nie wycenia slipa jako iloczynu nóg — nigdy nie
  podawaj `odds_if_product` jako ceny.
- `run_pipeline.py --only COUPON` po zmianie wet utrzymuje `06_coupon.json`
  (selektor cenowy VALUE, **nie kupon**) zgodnym dla `audit_coupon.py`.

Jeśli dzień jest **zakończony**, nie odświeżaj ceny. Powiedz, że ceny są
historyczne i że każda bramka niżej je teraz odrzuci — bo to poprawne
zachowanie.

---

## 5. Weryfikacja — nie do pominięcia

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <data>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <data>
```

`audit_coupon` sprawdza arytmetykę `05_sheet.json` / `06_coupon.json`
(selektor cenowy). `audit_variants` sprawdza kupon: C1 (świeżość artefaktu i
PDF), C2 (każdy wydrukowany singiel spełnia swoje pokrętła), C3 (odczyty
analityka na zbiorze `legs_requiring_read`, żadna wydrukowana noga z WATCH /
NO_BET), U1 (kolejność `coupon_order`), U2 (epoka `stats_only` na świeżych
singlach piłki i tenisa), U3 (każda świeża noga sportu odtworzona z surowej
migawki Superbetu). Kod 0 brak znalezisk, 1 znaleziska, 2 zły plik.

Potem oddaj dzień agentowi `sofa-verifier` (`/sofa-verify`). Protokół:
[`VERIFY_PROTOCOL.md`](VERIFY_PROTOCOL.md). Audyt sprawdza wiersz wobec niego
samego; agent robi cztery rzeczy, których audyt nie umie — odtwarza wiersz
z `03_samples.json`, sprawdza mapowanie `subject` na stronę, dopytuje Superbet
o żywą cenę i testuje rozkłady pod kątem antyselekcji. Jego odczyty
(`author: "verifier"`) dopisz do `reads.json` i przebuduj jak w kroku 4, potem
ponownie `audit_variants`.

---

## 6. Co zrobić, gdy…

| sytuacja | reakcja |
|---|---|
| kupon wyszedł pusty | **Nie przebudowuj w kółko.** Powiedz, **która bramka** go opróżniła. Sprawdź `06_dropped.json` — na 2026-09-21 wszystkie 118 wierszy VALUE padło na `DISAGREES_WITH_PRICE` (84) i `KICKOFF_TOO_SOON` (34). |
| zmienił się kod po zbudowaniu arkusza | `/sofa-rebuild` — przebudowa z artefaktów, bez SAMPLES (most tylko dla FIXTURE_CHECK). Napisz, **co** się zmieniło: przeliczony arkusz nie jest porównywalny z poprzednim. |
| kupon jest, brakuje odczytu analityków albo operator chce więcej | `/sofa-analyze` (także „dodatkowo: <pozycje>” → `read_requests.json`) — analitycy, scalenie wet i odczytów, przebudowa. |
| sport `NOT_CALIBRATED` / `NOT_IDENTIFIED` | Nogi tego sportu się nie drukują; kupon reszty jest ważny. Kalibrację fituje się tylko między dniami (`fit_sport_confidence.py --before <d>`); brak tożsamości — SPORT_IDENTITY jeszcze raz, gdy most żyje. |
| po refitcie krzywych (piłka, tenis albo sporty) | Między dniami: `fit_sport_confidence.py --sport all --before <d> --dry-run --rows-out <dir> --out <dir>/cal.json` (ok. 15 min na sport, nic nie instaluje), potem `fit_line_evidence.py --before <d> --sport-rows-dir <dir>` — korekta liczona jest względem krzywych zainstalowanych **teraz**, więc stara korekta nie pasuje do nowych krzywych. |
| dużo `NO_LINE_EVIDENCE` | Rynek bez krzywej czeka na >= 50 własnych rozliczonych linii w kubełku `p`; przybywa ich z każdym rozliczonym dniem (`refresh_line_evidence.py` co rano, krok 1a). To nie cięcie z nazwy, tylko brak pomiaru. |
| refit krzywych sportów w ciągu dnia | Nie instaluj nad `config/sofa_sport_confidence_calibration.json` w trakcie dnia. Złóż dopasowanie w `config/sofa_sport_confidence_calibration.next.json` z `"effective_from": "<D+1>"`: SPORT_CONFIDENCE i audyt U3 dnia ≥ D+1 czytają ten plik (`sport_confidence.calibration_path_for`). Dowód z linii licz względem niego: `fit_line_evidence.py --sport-calibration config/sofa_sport_confidence_calibration.next.json`. Po tym dniu przenieś `.next.json` nad główny plik. |
| stała albo baza wygląda źle | Zgłoś. Fitowanie to osobna, świadoma decyzja `sofa-settler` i **nigdy nie dzieje się w środku dnia**. |
| most padł w połowie SAMPLES | Uruchom `ensure_bridge.py` (kod 2 = zamknij Chrome całkowicie i powtórz), potem `--from-stage SAMPLES --run-id <ten sam id>`. Artefakty z dysku zostają. |
| brakuje `05_sheet.json` | Nie ma czego przebudowywać — dzień potrzebuje `/sofa-day`. |
| brakuje `02_fixtures.json` | Stop. Bez niego COUPON nie nazwie meczu, nie zastosuje bramki kickoffu, a `determine_side` nie rozwiąże `subject` na stronę. |

---

## 7. Bramki przed commitem

```bash
.venv/bin/python -m pytest tests/sofa -q
.venv/bin/python -m ruff check src/bet/sofa scripts/sofa
.venv/bin/python -m mypy --strict --no-incremental src/bet/sofa scripts/sofa
```

`ruff` i `mypy` mają **zastaną bazę błędów** (odpowiednio ~100 i ~129 w 10
plikach). Nie porównuj licznika z zerem ani z HEAD — w drzewie bywają cudze
niezacommitowane zmiany. Sprawdzaj, czy błąd wskazuje na linię, **którą sam
napisałeś**.

`ruff` **nie łapie** duplikatu w enumie. Po zmianie w enumie uruchom import.

---

## 8. Raport dnia

Wzór jest w [`AGENTIC_FLOW.md`](AGENTIC_FLOW.md), część 8: jeden kupon,
sekcje per sport, top 30 przeczytane, liczba nóg poza top 30, nogi zdjęte
(`removed_by_reads`) z autorem i powodem, D-1 (7c per sport + suma, zwroty,
7i, dziennik per epoka, CLV), audyty C1–C3 / U1–U3, weryfikacja.

Raporty z konkretnych dni i historia znalezisk: [`history/`](history/).
