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
8. analitycy na `legs_requiring_read` (30 meczów o najlepszej wartości +
   nogi builderów + `read_requests.json`; `read_set.py` -> raporty ->
   `merge_reads.py`): `sofa-analyst-football`, `sofa-analyst-tennis`,
   `sofa-analyst-sport` per sport mierzony (część 3);
9. scalenie wet i odczytów, przebudowa jednym poleceniem
   `rebuild_day.py` (stare ceny odświeżone najpierw, potem FIXTURE_CHECK →
   CONFIDENCE → SPORT_CONFIDENCE → `build_coupon.py` → PDF, pisze
   `12_printed.json`, → `audit_variants.py` + `audit_coupon.py`) (część 4);
10. `audit_coupon.py`, `audit_variants.py` (C1–C3, U1–U3), `sofa-verifier`,
    dopisanie jego odczytów, przebudowa `rebuild_day.py` (część 5);
11. raport (część 8);
12. od 2026-10-23: **wieczorna przebudowa** ok. 20:00–21:00Z — mecze
    hokeja / kosza / siatkówki / CS2 po północy UTC (do D+1 05:00Z) na kupon
    dnia D (część 4, „Wieczorna przebudowa”). Ręcznie, nieautomatyczna.

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
PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --from <D-8> --to <D-1>        # dziennik: runs/sofa/ledger/results.jsonl; zastępuje wiersze obu dat; potem PDF / HTML tych dni w kolorach wyniku (13_results.json; --no-mark: nie)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <D-7> --to <D-1>          # odczyt dziennika: tabela na grupę i epokę, nigdy łącznie; ROI z przedziałem 95% po meczach („-” poniżej 20 meczów)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_clv.py --from <D-2> --to <D-1>             # CLV kuponu — pierwsza liczba o wczoraj
```

Kody wyjścia `record_results.py` i `audit_settle_identity.py`: **0** =
rozliczone na tyle, na ile pozwalają settle — pozycje oczekujące widać w
tabeli (kolumna `pending`), nigdy w kodzie wyjścia. To normalny stan D-1:
nogi sportów mierzonych po 00:00Z (NHL/NBA, nocne CS2) rozliczają się w pliku
migawek następnego dnia — pętla CS2 o 05:00Z rozlicza D i D-1 i przegląda
D-7..D-2 (`settle_cs2.py --sweep-from/--sweep-to`), pętla shadow o 05:15Z
rozlicza D, D-1 i D-2 (D-2: przełożony mecz staje się `VOID` dopiero po 23:59
następnego dnia czasu lokalnego); jutrzejsze `--from <D-8>` je domyka. **1** = `MISMATCH` (dwa
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
  przesunięty poza 23:59 następnego dnia czasu lokalnego; przyspieszony o > 48 h), `AWARDED` (przyznany), `RETIRED` (krecz),
  `WALKOVER` (walkower), `CANCELED` (odwołany) i `POSTPONED_BEYOND_VOID`
  (przełożony i nierozegrany do 23:59 następnego dnia czasu lokalnego) — nigdy przegrana, nigdy `sofa_settled_row`
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

Procedura operacyjna: `.claude/commands/sofa-day.md` krok 1a. Po rozliczeniu i
zapisaniu D-1, **przed RESOLVE**: część mostkowa (`refresh_sport_history.py`
i `backfill_event_stats.py` dla hokeja, koszykówki i siatkówki - pyta most i
pisze do `data/sofa.db`, ~10-30 min, `ensure_bridge.py` najpierw), a dopiero
gdy w logu jest `BRIDGE_PART_DONE` - RESOLVE i obok niego same fity:
`refresh_line_evidence.py --before <D> --skip-history` (czytają bazę tylko do
odczytu). CONFIDENCE (krok 3) czeka na linię `EXIT` tego logu. Exit 0 zapisano;
**1** - fit jednego sportu nie wyszedł (sport czyta poprzednie wiersze) albo
crash (`Traceback`); **2** - `fit_line_evidence.py` nie wyszedł (dzień czyta
wczorajszy dowód - powiedz to w raporcie). `fitted_from.before` pliku
`config/sofa_superbet_line_evidence.json` musi być równe `<D>`. `day_status.py`
pokazuje `sport_history` - WARN poniżej 80% przypiętych meczów D-1. To **nie**
jest refit krzywych.

**Rano 2026-10-09 (pierwsze po instalacji refitu z 2026-10-08 23:42Z):** kolejność
to rozlicz i zapisz D-1 (10-08), `refresh_line_evidence.py --before 2026-10-09`,
dopiero potem pierwszy build. Dowód z linii dopasowano do STARYCH krzywych i
stosuje się go do nowych, dopóki się nie przefituje - pierwsze poranki bywają
zaszumione dla przeszacowanych rodzin (`games_won_for` UNDER prawdopodobnie
zaniżone, `goals_total` / `corners_total` możliwe podwójne liczenie). **Dnia
2026-10-08 nie przebudowuje się, nie renderuje PDF ponownie ani nie czyta
od nowa** (zbudowany pod starymi regułami; `build_coupon_pdf` odmawia
`STALE_CONFIDENCE`, a ponowny CONFIDENCE zmieszałby stary estymator z nowymi
krzywymi). Dni od 10-09 to nowa epoka porównywalności - nie sumuje się ich z
wcześniejszymi w dzienniku.

## 2. Dzisiaj

BOARD dotyka tylko Superbetu, więc może iść, gdy SETTLE trzyma jeszcze most.

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <data> --only BOARD > runs/sofa/<data>/pipeline_board.log 2>&1   # BOARD nadaje run_id: odczytaj go z linii SOFA_SUMMARY
# gdy CAŁY krok 1 (settler) skończy - nie tylko proces --only SETTLE: późniejsze skrypty settlera
# czytają bazę, a 2026-10-01 RESOLVE padł obok nich na 'database is locked'. FAILED zatrzymuje dalsze
# etapy (SKIPPED), a przerwany RESOLVE zostawia 02_fixtures.json.INCOMPLETE - wtedy RESOLVE jeszcze raz.
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <data> --from-stage RESOLVE --run-id <id>
```

**Jeden `--run-id` na cały dzień**, inaczej log rozpada się na dwa przebiegi.

Budżet: **2,5–3 h**, z czego większość to SAMPLES. Obserwuj przejścia etapów,
nie odpytuj w pętli:

```bash
grep -E "^--- |: (OK|PARTIAL|FAILED|SKIPPED)|STAGE_EXCEPTION|Traceback" <log> | tail -5   # krótkie wywołania, nigdy tail -f
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
- **Okno dnia sportów mierzonych** (od 2026-10-23 00:00Z,
  `epochs.SPORT_LATE_WINDOW_FROM_UTC`, decyzja operatora 2026-10-22): dzień
  D to [koniec(D-1), D+1 05:00Z) (`sport_identity.day_window`; 10-23 =
  [10-23 00:00Z, 10-24 05:00Z)). Mecze NBA / NHL po północy UTC należą do
  kuponu D, nie do porannego D+1 (tam byłyby `KICKED_OFF`). Piłka i tenis
  bez zmian (doba UTC). Migawki D (SHADOW, CS2) pobierają takie mecze raz
  już w ciągu dnia, do pliku D+1; noga meczu z D+1 ma `window: "late"`;
  mecz już wydrukowany na kuponie D-1 jest `ALREADY_PRINTED_PREV_DAY`.

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

Analitycy biegną **po COUPON_ASSEMBLY**, na `11_coupon.json`. Procedurę
prowadzi `/sofa-analyze` (`.claude/commands/sofa-analyze.md`); dzień robi to
w krokach 5-7 `/sofa-day`. Zbiór do przeczytania
(`confidence.legs_requiring_read`): niezablokowane nogi **30 meczów o
najlepszej wartości** (najlepsza niezablokowana noga meczu: pewność x kurs,
pewność piłki / tenisa i oflagowanej nogi CS2 ucięta do 1/kurs + `price_gap.GAP`;
`read_order: "value"`), każda noga wydrukowanego buildera i wpisy
`runs/sofa/<data>/read_requests.json`; na budowie wstępnej dochodzi bufor
następnych meczów w tej samej kolejności.

1. Zbiór, plik na sport / część (części po <= 12 całych meczów, jeden
   analityk na plik):

   ```bash
   PYTHONPATH=src:. .venv/bin/python scripts/sofa/read_set.py --date <data> --buffer 25 --split 12
   ```

   `--buffer 25` na budowie wstępnej, `--buffer 0` na końcowej. Wynik:
   `runs/sofa/<data>/read_set/read_set_<sport>[_<i>].json`.
2. Analitycy: jedna instancja na plik, wszystkie w jednej wiadomości, na
   pierwszym planie (`football` -> `sofa-analyst-football`, `tennis` ->
   `sofa-analyst-tennis`, hokej / kosz / siatka / CS2 ->
   `sofa-analyst-sport`). Każdy dostaje ścieżkę swojego raportu
   `runs/sofa/<data>/<data>_analiza_<sport>[_<i>].md` (istnieje -> następny
   wolny `_r<n>`; nigdy nie nadpisuj), **sam pisze raport** z blokami
   ```` ```json vetoes ```` (piłka / tenis) i ```` ```json reads ```` i
   zwraca ścieżkę, którą faktycznie zapisał. Nikt nie przepisuje jego
   tekstu ani tablic.
3. Scalenie zwróconych ścieżek (jedno wywołanie może wziąć kilka
   `--report`, nigdy dwa naraz), potem przebudowa:

   ```bash
   PYTHONPATH=src:. .venv/bin/python scripts/sofa/merge_reads.py --date <data> --author analyst --report <zwrócona ścieżka> [--report <...>]
   PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <data>
   ```

   `merge_reads.py` waliduje (`Veto`, `LegRead`), przenosi wcześniejsze weta,
   tylko dopisuje odczyty. Kod 0 scalone, 1 scalone z `UNMATCHED_VETO`, 2
   odmowa, nic nie zapisano - ponów tę instancję z linią odmowy i nową
   ścieżką `_r<n>` (nigdy nie poprawiaj JSON-a ręcznie).
4. Pętla C3: przebudowa przesuwa pozycje, więc po każdej:

   ```bash
   PYTHONPATH=src:. .venv/bin/python scripts/sofa/read_set.py --date <data> --unread --split 12
   ```

   i kroki 2-3 tylko na tych plikach, aż C3 będzie czyste (najwyżej 3
   rundy). `read set: empty` przy czerwonym C3 = wydrukowana noga ma WATCH /
   NO_BET albo brak `reads.json`: przebuduj, nie czytaj.

Noga sportu mierzonego schodzi odczytem `NO_BET` / `WATCH` (ma stronę i
okres), nie wetem. `run_confidence.py` liczy go jako `reads_sport`, nigdy
`UNMATCHED_READ`; działa w COUPON_ASSEMBLY - sprawdź w `11_coupon.json`
`removed_by_reads`. Zgłoś każde `UNMATCHED_VETO` i `UNMATCHED_READ`: nic nie
zrobiło. **`[]` to zdrowa wartość domyślna wet.**

Dodatkowe odczyty na życzenie operatora: `/sofa-analyze` „dodatkowo:
<pozycje>” dopisuje do `read_requests.json` nogę, którą pozycja wskazuje
teraz (`group_key`, `market`, `line`, `direction`; `{"position": n}` tylko
gdy tam nic nie ma), z `requested_by` i `at_utc`. Prośba, która nic nie
objęła, drukuje `UNMATCHED_READ_REQUEST`.

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

Pętla ceny zamknięcia (`capture_closing.py --loop`) startuje sama: pętle
dnia `cs2_daily.py` (z łańcucha o 23:30Z dnia poprzedniego) i
`shadow_daily.py` (04:30Z) przy swoim starcie uruchamiają ją dla swojej daty
(`capture_closing.ensure_loop`), chyba że pętla tej daty już żyje (plik pid
+ linia polecenia; druga pętla kończy się kodem 2). Uruchomiona przed
budową czeka na `11_coupon.json` do końca dnia. Polecenie wyżej jest więc
zapasowe (np. gdy łańcuch pętli dnia się przerwał). 2026-10-15 pętlę
uruchomiono ręcznie o 08:01Z, 85 min po pierwszym druku - nogi meczów z tego
okna nie mają ceny zamknięcia. `day_status.py` daje WARN
`loop:capture_closing` także przed budową, gdy pętla nie działa.

Plan (`bet.sofa.rebuild_plan`, z wieku plików i zegara, bez sieci), po kolei:

- **LATE_RESOLVE** (od 2026-10-21 08:48Z, `epochs.LATE_RESOLVE_FROM_UTC`;
  poprzedzony `ensure_bridge.py`), gdy dzień ma wpis tablicy bez fixture'a,
  który startuje za więcej niż 20 min (albo zdarzenie, którego poprzedni
  późny przebieg nie doprowadził do SHEET): `run_late_resolve.py` pyta
  RESOLVE jeszcze raz tylko o te wpisy i przeprowadza **wyłącznie nowe**
  mecze przez OFFER / SAMPLES / SHEET (`--event-ids`, doklejane do 04 / 03 /
  05; stare wiersze nietknięte). Krok miękki. Ręcznie: najpierw
  `ensure_bridge.py`, potem `run_late_resolve.py --date <d> [--dry-run]`;
  zapis przebiegów w `runs/sofa/<d>/late_resolve.json`. Nowe nogi z
  pierwszych 30 meczów wg wartości wymagają odczytu (`read_set.py --unread`).

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
  nie zbudowany pod regułą stats-only, `epochs.sheet_epoch`; od włączenia pakietu w
  kolejce - `COUNT_DISPERSION`, `TENNIS_SCOPED_TABLE`, `PER_MARKET_K` włączone
  od 2026-10-09 00:00Z (`CARDS_CORRELATION` nadal `None`) - także arkusz dnia
  >= 10-09 bez jego znacznika
  `dispersion_rule` / `tennis_table_rule` / `cards_rule` / `k_rule`). Zmiany kodu
  SHEET albo jego konfiguracji polecenie nie wykrywa — wtedy najpierw
  `run_pipeline.py --only SHEET` ręcznie i napisz, co go wymusiło.
  Pod `FOOTBALL_REFEREE` SHEET wraca też, gdy wiersz kartek / fauli otwartego
  meczu ma `referee_read.status == "NO_REFEREE"`, a baza już zna sędziego
  (`referees.referee_for_event`: etykieta albo /event z RESOLVE / wcześniejszego
  FIXTURE_CHECK; `rebuild_plan.referee_now_known`, jedno zapytanie na mecz).
- **COUPON** (`--only COUPON`, `06_coupon.json` — wejście `audit_coupon`, nie
  kupon) tylko, gdy jest starszy niż arkusz / weta / odczyty.
- potem `ensure_bridge.py`, **FIXTURE_CHECK** (SHEET tej przebudowy idzie
  PRZED nim, więc sędziego, którego nazwał dopiero świeży /event, widzi
  `rebuild_plan.after_fixture_check`: `rebuild_day.py` wstawia wtedy SHEET
  zaraz po FIXTURE_CHECK, przed CONFIDENCE - audyt 2026-10-21 D7), **CONFIDENCE**,
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

### Wieczorna przebudowa (od 2026-10-23)

**Kiedy:** codziennie ok. 20:00–21:00Z, ręcznie (nic jej nie uruchamia
samo). **Po co:** okno dnia sportów mierzonych sięga D+1 05:00Z (2b), więc
mecze hokeja / kosza / siatkówki / CS2 rozpoczynające się po północy UTC są
nogami kuponu D. Poranna budowa wyceni tylko te z nich, które mają już
świeżą cenę (≤ 3 h) i przypięte id; Superbet często wystawia linie później,
a cena sprzed wielu godzin to `STALE_PRICE`. Resztę dokłada wieczór.

```bash
.venv/bin/python scripts/sofa/ensure_bridge.py
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <D> --dry-run   # plan: SHADOW/CS2 z horyzontem do najdalszego startu, SPORT_IDENTITY
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <D>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/read_set.py --date <D> --unread      # nowe nogi do odczytu (C3)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/day_status.py --date <D>
```

**Co dodaje:** nogi meczów z okna D, które jeszcze się nie zaczęły — w tym
z D+1 do 05:00Z (`window: "late"`, z pliku migawek D+1, `source_date` D+1).
Plan przebudowy sam odświeża ceny SHADOW / CS2 i identyfikacje (most).
**Nogi poranne zostają zablokowane** — wydrukowane przed startem nie
zmieniają się; noga zdjęta przed startem zostaje zdjęta. Nowe nogi z
pierwszych 30 meczów wartości wymagają odczytu analityka (`/sofa-analyze`),
potem jeszcze jedna przebudowa. Jeśli `day_status.py` pokaże
`loop:capture_closing` WARN (pętla kursów zamknięcia skończyła się po
ostatnim porannym meczu), uruchom ją: `capture_closing.py --date <D> --loop`.
**Rozliczenie:** poranne kroki pętli (05:00Z / 05:15Z D+1) rozliczają plik
D+1 do D+1 05:00Z (`settle_cs2.py` / `settle_shadow.py --date <D+1>
--kickoff-before <D+1>T05:00:00Z`); SETTLE_AFTER to 4 h, więc mecz po ok.
01:15Z rozlicza się dopiero dzień później, przy rozliczeniu D+1. Dziennik
(`record_results.py`) bierze ocenę z pliku `source_date` nogi.

### Kupon z czatu na kurs docelowy (poza pipeline'em)

Skrót: **`/kupon 11-13`** (opcjonalnie `~5`, `x2`) — operator podaje tylko
godziny, reszta poniżej dzieje się sama.

Gdy operator prosi o kupon AKO „na ~4” (także w oknie godzin, np. 10:00–12:00,
albo kilka rozłącznych), skład robi skrypt, nie ręka — tylko z nóg
`11_coupon.json`, bez sieci, bez stawki i bez ceny kuponu — a każdą nogę
czyta analityk:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_slip.py --date <data> --target 4 \
    --start-from 10:00 --start-to 12:00 --allow-rest \
    --read-set-dir runs/sofa/<data>/read_set_slip
```

- **Wszystkie rynki** (`--allow-rest`, decyzja operatora 2026-10-20). Pierwsza
  linia i tak mówi najpierw „nie”: ile kuponów dzień daje z rodzin na plusie;
  kupon z reszty rynków jest oznaczony „poza poparciem”.
- **Algorytm**: dokładny problem plecakowy z wyborem (jedna noga z meczu) —
  maksymalna zmierzona szansa kuponu przy iloczynie kursów ≥ cel; to samo
  wybiera najmniej nóg, bo każda noga traci podobnie w każdym przedziale kursu
  (10-13..10-19: 1.10–1.30 ROI −5,1%, 1.30–1.70 −4,2%, różnica +0,9 pp
  [−1,0; +2,8]). Stan trzyma dokładny logarytm kursu (koszyki 0,0001 do
  odcięcia Pareto) — kupon 2,00 × 2,00 na cel 4 jest znajdowany, a
  znaleziony zawsze sięga celu. Sprawdzone pełnym przeglądem na losowych danych.
- **Szansa nogi** = min(pewność, cena przy `price_gap`, 1/kurs + luka
  rodziny z `family_record.json`); rodzina na plusie czyta lukę swojej
  selekcji z walk-forward (−0,8 / −1,6 pp), nigdy nadwyżkę.
- **Czytanie**: skrypt zapisuje nieczytane nogi kuponu (z `--reserve 1`
  także kuponu zapasowego; domyślnie wyłączone — plecak liczy wszystko od
  nowa, więc zamiennik rzadko pochodzi z zapasu) do
  `read_set_slip_<sport>.json`; analityk danego sportu czyta plik i pisze
  raport `<data>_analiza_<sport>_kupon_<HHMM>_<runda>.md`; scala się ścieżkę
  z linii `raport:` analityka:
  `merge_reads.py --slip --author analyst --report <ścieżka> --read-set <plik>`
  (`UNMATCHED_READ` / `LEG_WITHOUT_READ` = odczyt bez nogi / noga bez odczytu
  — wraca do analityka). Noga z WATCH / NO_BET / wetem wypada razem z
  trudniejszymi progami tej samej zmiennej (WATCH na OVER 7.5 zdejmuje też
  OVER 8.5), a ponowne uruchomienie liczy kupon od nowa z następną najlepszą
  nogą — i ją też daje do czytania. Koniec, gdy skrypt pisze „Każda noga
  kuponów ma KEEP analityka” (najwyżej 3 rundy; nieczytana noga jest tak
  nazwana). „KEEP (kupon dnia)” = poranny odczyt kuponu dnia, „KEEP (10:42)”
  = odczyt kuponu z czatu starszy niż 3 h (merge `--slip` stempluje
  `read_at_utc`, nowszy odczyt tej samej nogi zastępuje starszy KEEP, nigdy
  WATCH / NO_BET) — oba możliwe, że sprzed składów, więc żaden nie zwalnia
  nogi z odczytu: skrypt daje je analitykom jak nieczytane (operator
  2026-10-21: poranne KEEP kuponu 16-18 nie widziały rezerwowego bramkarza i
  ściany 12 gemów). Wyszukiwanie najpierw składa kupon z nóg ze świeżym KEEP tego kuponu;
  nieczytaną nogę bierze tylko wtedy, gdy z nich nie da się dojść do celu
  (operator 2026-10-21: każda runda wymieniała przeczytane nogi na nowe). Przy
  remisie (różnica szansy < 0,25% na nogę)
  wyszukiwanie woli nogi z świeżym KEEP tego kuponu, żeby pętla
  nie wymieniała ich na nieczytane.
- **Jedna rodzina**: kupon z ≥ 3 nogami jednej rodziny (albo cały z jednej)
  dostaje linię „Uwaga: N z M nóg z jednej rodziny” — ostrzeżenie, nie
  bramka. Werdykty idą przez
  `merge_reads.py --slip` do `reads_slip.json` / `vetoes_slip.json` — kupon
  z czatu je czyta, kupon dnia **nie** (prośba o typy nie rusza kuponu).
- **Wiek ceny**: kolumna „cena sprzed” i linia „Cena starsza niż limit
  pipeline'u” (45 min piłka / tenis, 3 h sporty; u piłki to co najmniej wiek
  kuponu, „≥”) — skrypt nie odświeża cen, rozstrzyga kurs na ekranie.
- Okno powinno zaczynać się ≥ 30 min później — nogi startujące w trakcie
  czytania wypadają. Przewaga selekcji rodzin jest **niepotwierdzona**
  (T-FAMILY-SELECTION; `docs/sofa/evidence/selection_walk_forward_2026-10-20.md`).

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
o żywą cenę i testuje rozkłady pod kątem antyselekcji. Sam pisze raport
`runs/sofa/<data>/<data>_weryfikacja[_r<n>].md` z jednym blokiem
```` ```json reads ````; scal go zwróconą ścieżką i przebuduj - nigdy nie
dopisuj odczytów ręcznie:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/merge_reads.py --date <data> --report <zwrócona ścieżka> --author verifier
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <data>
```

Potem ponownie `audit_variants`; C3 z nieprzeczytanymi nogami -> pętla C3
z kroku 3.

---

## 6. Co zrobić, gdy…

(2026-10-12) Krok pętli dłuższy niż 6 h (`cs2_daily.STEP_TIMEOUT_S`) jest zabijany
razem z grupą procesów i zapisany `STEP_FAILED TIMEOUT` - pętla idzie dalej jak po
każdym błędzie. `day_status.py` ostrzega też o identyfikacji meczów sportów
(`identity`: każde BRIDGE_ABORTED albo udział poniżej hokej 85% / koszykówka 75% /
CS2 45% / siatkówka 25% przy >= 10 meczach; duplikaty 1x1 CS2 nie liczą się).


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
| długi backfill historii (listingi, statystyki, składy) | Tylko przez `backfill_driver.py --preset {listings\|stats\|night} --log runs/sofa/backfill/<nazwa>.log` (albo `--plan <plik.json>`; `--dry-run` pokazuje etapy). Kawałki po 7 min, czeka na przebudowę / rozliczenie / dziennik; rano dodaj `--yield-to-build` (ustępuje BOARD..SHEET dzisiejszego dnia). Trzy razy otwarty bezpiecznik (403 „challenge” 2026-10-22) = sonda mostu co 15 min do 6 h i wznowienie; dopiero potem `STOP` w logu i `day_status.py` ostrzega `backfill`. Nic z tego nie zmienia kuponu. |
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
sekcje per sport, przeczytany zbiór C3 (30 meczów o najlepszej wartości), liczba nóg poza nim, nogi zdjęte
(`removed_by_reads`) z autorem i powodem, D-1 (7c per sport + suma, zwroty,
7i, dziennik per epoka, CLV), audyty C1–C3 / U1–U3, weryfikacja.

Raporty z konkretnych dni i historia znalezisk: [`history/`](history/).
