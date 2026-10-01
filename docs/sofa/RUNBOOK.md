# `sofa` — runbook operatora

Jak przeprowadzić jeden dzień zakładowy. Mechanika etapów jest
w [`PIPELINE.md`](PIPELINE.md), role agentów w
[`AGENTIC_FLOW.md`](AGENTIC_FLOW.md). Tutaj jest **kolejność działań, czas
i decyzje**.

Skrót operacyjny: **`/sofa-day`**. Ten plik mówi, co ta komenda robi i co
zrobić, gdy coś pójdzie inaczej.

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
# kilka dni po kartkach, a cache pyta ponownie dopiero mecz sprzed >= 4 dni - więc co rano ponowne rozliczenie D-5
# (dopisuje tylko brakujące wiersze) i poprawa wierszy rozliczonych z wczesnego snapshotu:
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_settle.py --date <D-5> --refetch-stat-gaps
PYTHONPATH=src:. .venv/bin/python scripts/sofa/regrade_settled.py --apply
# każdy wariant D-1 i dziennik:
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_sport_coupon.py --from <D-8> --to <D-1>   # cztery kupony sportów, po wydrukowanym kursie; także D-2: jego pozycje po 00:00Z rozliczają się w pliku D-1
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_multi_coupon.py --from <D-8> --to <D-1>   # WARIANT WSZYSTKIE, sekcja po sekcji
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_shadow.py --from <D-1> --to <D-1>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_cs2.py --from <D-1> --to <D-1>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --from <D-8> --to <D-1>        # dziennik: runs/sofa/ledger/results.jsonl; zastępuje wiersze obu dat
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <D-7> --to <D-1>          # odczyt dziennika: tabela na wariant, nigdy łącznie; ROI z przedziałem 95% po meczach („-” poniżej 20 meczów)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_clv.py --from <D-2> --to <D-1>             # CLV na wariant — pierwsza liczba o wczoraj
```

Kody wyjścia `settle_sport_coupon.py`, `settle_multi_coupon.py` i
`record_results.py` (od 2026-09-30): **0** = rozliczone na tyle, na ile
pozwalają settle — pozycje oczekujące widać w tabeli (kolumna `pending`),
nigdy w kodzie wyjścia. To normalny stan D-1: pozycje kuponu sportu po
00:00Z (NHL/NBA, nocne CS2) rozliczają się w pliku migawek dzisiejszego dnia
i są oceniane jutro rano — pętla CS2 o 05:00Z rozlicza D i D-1, przegląda
D-7..D-2 (`settle_cs2.py --sweep-from/--sweep-to`: tylko daty z czekającą
serią) i ocenia kupony CS2 oraz dziennik za D-7..D; pętla shadow o 05:15Z
rozlicza D, D-1 i D-2 (D-2: przełożony mecz staje się `VOID` dopiero 48 h po
starcie) i ocenia kupony sportów oraz dziennik za te dni; jutrzejsze `--from <D-2>` też je domyka. **1** = `MISMATCH` (dwa
oceniające nie zgadzają się co do nogi — defekt, nazwij go) albo nieczytelny
plik (nazwany w tabeli). **2** = awaria albo, w `record_results.py`, brak
bazy (nic się wtedy nie zapisuje). Zanim SHADOW_SETTLE / CS2_SETTLE zapisze `settled.json`, pozycje
kuponu sportu mają PENDING, ale wiersza `measure:<sport>` po prostu nie ma w
dzienniku (nie jest „oczekujący”) - sprawdź, czy są wszystkie wiersze
`measure:*`, nie tylko kod wyjścia. Po późnym rozliczeniu powtórz
`record_results.py --from <D-8> --to <D-1>` — zastępuje wiersze tych dat.

Potem pętle dzisiejszego dnia:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <today> --only CS2
# cały dzień CS2 bez obsługi (ceny do 23:30Z, o 05:00Z D+1 settle D i D-1, przegląd D-7..D-2, kupony CS2 i dziennik za D-7..D);
# --chain o 23:30Z startuje pętlę D+1 (nocne serie D+1 mają ceny); pętla D-1 z --chain już ją uruchomiła,
# a druga pętla dla daty odmawia (kod 2), więc powtórka nie szkodzi:
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/cs2_daily.py --date <today> --chain >> runs/sofa/cs2/daily_<today>.log 2>&1 &
# pętla D-1 z --chain sama startuje dzisiejszą po swoim rozliczeniu i audycie (ok. 05:20–05:45Z); ręcznie tylko, gdy nie ma
# ani runs/sofa/shadow/daily_<D-1>.pid, ani daily_<today>.pid:
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/shadow_daily.py --date <today> --chain >> runs/sofa/shadow/daily_<today>.log 2>&1 &
```

- SHADOW / SHADOW_SETTLE to pomiar hokeja, koszykówki i siatkówki (jak CS2):
  **nie kupon**, a ich `PARTIAL`/`FAILED` nie blokuje dnia. Druga pętla
  `shadow_daily.py` dla tej samej daty odmawia startu (exit 2), więc
  ponowne uruchomienie jest bezpieczne.
- Pętla czyta swój plan raz, przy starcie: pętla uruchomiona przed zmianą
  kodu wykonuje stare kroki poranne aż do końca (jej następczyni z `--chain`
  ma już nowy kod). Po zmianie `cs2_daily.py` / `shadow_daily.py` powtórz
  nowe kroki poranne ręcznie dla dni, które obejmują stare pętle, i napisz to
  w raporcie — nigdy nie zabijaj pętli, żeby złapała zmianę.

- `PARTIAL` to normalny werdykt.
- **Sekcja 7c audytu to prawdziwy wynik kuponu z PDF.** Sekcje 7 i 7b to
  materiał wejściowy (legi i kandydaci), **nie zakłady**. Sekcja 7d to
  WARIANT — obok 7c, nigdy łącznie.
- `07_settle_skips.json`: wiersz, którego nie dało się ocenić, **nie jest
  przegraną**.

Głębiej i z decyzją o fitowaniu: `/sofa-settle` albo agent `sofa-settler`.

---

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

---

## 3. Analitycy i weta

`vetoes.json` czytają **COUPON i CONFIDENCE naraz**, więc analitycy biegną
**po SHEET**, a dzień przebudowuje się po nich. Sekwencja domyślna zdąży już
uruchomić COUPON — to normalne.

```
Task → sofa-analyst-football   "data <data>; run <run_id>; werdykty etapów; <n> piłkarskich VALUE"
Task → sofa-analyst-tennis     "data <data>; run <run_id>; werdykty etapów; <n> tenisowych VALUE"
```

Obu w **jednej wiadomości**, żeby szli równolegle. Scal ich tablice JSON do
`runs/sofa/<data>/vetoes.json` — **najpierw walidując**: jeden wymyślony klucz
wywraca cały plik, a etap rusza wtedy z zerem wet i melduje zero.

Zgłoś każde `UNMATCHED_VETO`: nic nie zrobiło, a cichy no-op czyta się
identycznie jak weto uszanowane. **`[]` to zdrowa wartość domyślna.**

Ten krok wolno pominąć tylko na wyraźną prośbę operatora — i trzeba wtedy
powiedzieć, że się go pominęło.

---

## 4. Przebudowa, confidence i PDF

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_offer.py --date <data> --min-minutes-to-kickoff 20
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <data> --only SHEET
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <data> --only COUPON
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <data>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <data>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <data> --profile wariant
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <data> --profile wariant
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/capture_closing.py --date <data> --loop >> runs/sofa/<data>/capture_closing.log 2>&1 &   # cena zamknięcia singli (CLV), bez mostu
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_boosts.py --date <data>   # boosty; powtórz kilka razy w ciągu dnia
```

- Odśwież OFFER, jeśli poprzedni jest starszy niż **45 minut** — inaczej oba
  etapy odrzucą każdą cenę, a pusty wynik będzie wyglądał na wniosek
  analityczny. Po odświeżeniu **zawsze SHEET** — przesunięta cena jest
  odrzucana (`PRICE_MOVED_SINCE_SHEET`).
- `--min-minutes-to-kickoff` przyjmuje tylko `run_offer.py`; `run_pipeline.py`
  kończy się na niej kodem 2. Bez niej późne odświeżenie spędza ~90 minut na
  wycenie meczów już rozegranych.
- `build_coupon_pdf.py` odmawia (kod 2, `STALE_CONFIDENCE`), gdy confidence
  jest starsze niż `05_sheet.json` albo `vetoes.json` — wtedy najpierw
  `run_confidence.py` dla tego profilu.
- **Czytaj `stakeable_builders`, nie `builders`.** Oba są raportowane właśnie
  dlatego, że się różnią.
- **`picks: 0` to odpowiedź legalna i częsta.** Slip musi być
  `best_for_fixture` **i** mieć dodatni EV po zmierzonym narzucie
  korelacyjnym (12%; zmierzony zakres 8,8–19,6%). Samo
  `ev_if_product_priced > 0` nie znaczy nic — Superbet nie wycenia slipa jako
  iloczynu nóg.

Jeśli dzień jest **zakończony**, nie odświeżaj ceny. Powiedz, że ceny są
historyczne i że każda bramka niżej je teraz odrzuci — bo to poprawne
zachowanie.

### 4a. Kupony eksperymentalne: CS2, hokej, koszykówka, siatkówka (od 30.09)

Eksperyment operatora. **To nie jest kupon** i nigdy nie trafia do
`runs/sofa/<d>/`. Pliki leżą obok pomiaru:
`runs/sofa/cs2/<d>/KUPON_<d>_CS2.pdf`,
`runs/sofa/shadow/<sport>/<d>/KUPON_<d>_{HOKEJ,KOSZYKOWKA,SIATKOWKA}.pdf`.

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_shadow.py --date <d> --horizon-h 24     # świeże ceny hokej/kosz/siatka (tylko Superbet)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only CS2       # świeże ceny CS2
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D+1> --only CS2     # nocne serie CS2 leżą w pliku D+1
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_coupon.py --date <d> --sport all
```

Rozliczenie kuponów sportów za D-1 (`settle_sport_coupon.py`) jest w kroku 1.

Albo cztery agenty `sofa-sport-runner` równolegle, po jednym na sport.

- Kupon tych sportów **nie czyta modelu** (`score_model.py` i silnik CS2 to
  tylko pomiar). Pewność to cena Superbet bez marży, więc
  przy uczciwej cenie każda pozycja traci średnio tyle, ile marża.
- Reguła: na mecz jedna strona z fair p ≥ 0,70, marżą linii ≤ 10,5% i
  kursem ≥ 1,087, ta o najwyższym fair p × kurs (najmniejsza zapłacona marża); maks. 10 pozycji;
  cena nie starsza niż 3 h; bez linii zawodników. Wszystkie stałe są
  UNFITTED.
- Dzień kuponu trwa do 06:00 czasu warszawskiego następnego dnia, więc mecze
  nocne (NHL, NBA) z pliku D+1 też się liczą. Przebudowa zostawia nogi już
  rozpoczęte bez zmian („w toku”); każda wersja trafia do
  `sport_coupon_builds.jsonl`. Nogi wcześniejszych wersji i `replaced_legs`
  są zapisane, ale **nie są rozliczane** — wynik kuponu to tylko nogi
  ostatniej wersji (`sport_coupon_settled.json`). Dnia, którego okno się
  zamknęło, nie da się przebudować.
- Pewność liczona jest z całej grupy wyników rynku: para, 1X2 (trzy wyniki)
  albo pełny zestaw dokładnych wyników. 1X2 bez wyceny remisu nie jest ceną.
- Tylko pojedyncze. Rozliczane per sport po wydrukowanym kursie, z zapisanego
  wyniku meczu (także gdy Superbet zdjął później linię), nigdy łączone z
  kuponem ani ze sobą.
- Rynki mierzone od 30.09: 1X2 (hokej, koszykówka: mecz, połowy, kwarty,
  tercje), parzystość (koszykówka, siatkówka, CS2 — rundy na mapie), dokładny
  wynik (siatkówka w setach, CS2 w mapach), set na przewagi (siatkówka).
  Niemierzone, z powodem: podwójna szansa (to 1X2 sprzedane drugi raz),
  pierwszy gol / kto pierwszy do N punktów (brak kolejności zdobyczy w
  wyniku), progi zawodników „5+” (rynek jednostronny, nie ma z czym
  zdevigować), double-double (klucze statystyk niezweryfikowane), kombinacje.

Korekta jednorazowa (30.09): do 30.09 CS2_SETTLE oceniał też linie, które
Superbet zdjął przed startem, po ich starej cenie. `regrade_cs2_snapshots.py
--from <d> --to <d>` usuwa takie strony offline (kopia: `settled.pre_regrade.json`);
29.09 miał ich 22 z 302. Po nim `record_results.py` dla tych dni.

### 4b. WARIANT WSZYSTKIE i dziennik wyników (od 30.09, domyślnie w /sofa-day)

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_multi_coupon.py --date <d>     # po kuponie i czterech kuponach sportów
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <d>       # każdy wariant przeliczony z surowych danych
```

Rozliczenie WSZYSTKIE za D-1 (`settle_multi_coupon.py`) i dziennik
(`record_results.py`) są w kroku 1.

- `runs/sofa/multi/<d>/KUPON_<d>_WSZYSTKIE.pdf` to **złożenie**, nie nowy
  wybór: pojedyncze i buildery z oficjalnego PDF oraz nogi czterech kuponów
  sportów, dokładnie po ich kursach. Sekcja z nieaktualnego lub brakującego
  źródła jest wyłączona z podanym powodem.
- Po każdej przebudowie kuponu albo kuponu sportu złożenie trzeba powtórzyć
  (`audit_variants` M2 to wykrywa). Kupon sportu zbudowany ponad 6 h przed
  złożeniem jest wyłączony (`STALE`); po 06:00 czasu warszawskiego D+1 okno
  dnia jest zamknięte i skrypt odmawia (kod 2) — wariant jest ostateczny.
- Dziennik ma jeden wiersz na (dzień, wariant): kupon (7c), WARIANT (7d),
  każdy kupon sportu, WSZYSTKIE, `rule:<sport>` (reguła samej ceny odtworzona
  na rozliczonym dniu, wybór przed wynikiem, po ostatniej cenie przed
  startem — także w dniu bez kuponu) i `measure:<sport>` (pomiar ceny:
  `favourite_side` tylko z linii dwudrożnych, więc porównywalny przez
  granicę 30.09; obok `by_shape`, `by_family` i `players`). Każdy wiersz
  wariantu ma `outcomes` (liczba ocen każdego rodzaju; `MISMATCH` to defekt,
  nie wynik). Z niego — i tylko z niego, osobno per wariant — czyta się
  wyniki z wielu dni:
  `PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <d> --to <d> [--variant sport:hockey]`.
- Weta (`vetoes.json` w katalogu sportu) tylko usuwają: przełożony mecz,
  zmiana składu w CS2, nietypowy format. Nigdy „ta liga gra under”.

---

## 5. Weryfikacja — nie do pominięcia

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <data>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <data>
```

WARIANT (`KUPON_<data>_WARIANT.pdf`) sprawdza `audit_variants` (C1/C2: świeżość,
profil, reguła każdej pozycji), ale jego nóg z próbek nie odtwarza żaden
skrypt — nazwij go weryfikatorowi wprost. Potem oddaj dzień agentowi `sofa-verifier` (`/sofa-verify`). Protokół:
[`VERIFY_PROTOCOL.md`](VERIFY_PROTOCOL.md). Audyt sprawdza wiersz wobec niego
samego; agent robi cztery rzeczy, których audyt nie umie — odtwarza wiersz
z `03_samples.json`, sprawdza mapowanie `subject` na stronę, dopytuje Superbet
o żywą cenę i testuje rozkłady pod kątem antyselekcji.

---

## 6. Co zrobić, gdy…

| sytuacja | reakcja |
|---|---|
| kupon wyszedł pusty | **Nie przebudowuj w kółko.** Powiedz, **która bramka** go opróżniła. Sprawdź `06_dropped.json` — na 2026-09-21 wszystkie 118 wierszy VALUE padło na `DISAGREES_WITH_PRICE` (84) i `KICKOFF_TOO_SOON` (34). |
| zmienił się kod po zbudowaniu arkusza | `/sofa-rebuild` — przebudowa z artefaktów, bez mostu i bez SAMPLES. Napisz, **co** się zmieniło: przeliczony arkusz nie jest porównywalny z poprzednim. |
| arkusz jest, brakuje odczytu analityków | `/sofa-analyze` — analitycy, scalenie wet, przebudowa. Bez Sofascore. |
| stała albo baza wygląda źle | Zgłoś. Fitowanie to osobna, świadoma decyzja `sofa-settler` i **nigdy nie dzieje się w środku dnia**. |
| most padł w połowie SAMPLES | Uruchom `ensure_bridge.py` (kod 2 = zamknij Chrome całkowicie i powtórz), potem `--from-stage SAMPLES --run-id <ten sam id>`. Artefakty z dysku zostają. |
| brakuje `05_sheet.json` | Nie ma czego przebudowywać — dzień potrzebuje `/sofa-day`. |
| brakuje `02_fixtures.json` | Stop. Bez niego COUPON nie nazwie meczu, nie zastosuje bramki kickoffu, a `determine_side` nie rozwiąże `subject` na stronę. |

---

## 7. Bramki przed commitem

```bash
.venv/bin/python -m pytest tests/sofa -q
.venv/bin/python -m ruff check src/bet/sofa scripts/sofa
.venv/bin/python -m mypy --strict src/bet/sofa scripts/sofa
```

`ruff` i `mypy` mają **zastaną bazę błędów** (odpowiednio ~100 i ~129 w 10
plikach). Nie porównuj licznika z zerem ani z HEAD — w drzewie bywają cudze
niezacommitowane zmiany. Sprawdzaj, czy błąd wskazuje na linię, **którą sam
napisałeś**.

`ruff` **nie łapie** duplikatu w enumie. Po zmianie w enumie uruchom import.

---

## 8. Raport dnia

```
KUPON:    runs/sofa/<data>/KUPON_<data>.pdf — <n> pozycji
WARIANT:  runs/sofa/<data>/KUPON_<data>_WARIANT.pdf — <n> pozycji (NIE kupon; 0.65 / x ≥ 0.90)
SHEET:    <n> wierszy, <n> VALUE (<n> piłka / <n> tenis)
RUN:      <run_id> · <werdykt> · <n> na tablicy → <n> dopasowanych (<x>%) → <n> READY
WETA:     <n> zastosowanych, <n> bez dopasowania
SETTLE:   D-1 <n> wierszy, PDF-kupon <w>/<n> slipów (sekcja 7c)
POMIAR:   D-1 CS2 <n> serii / hokej <n> / kosz <n> / siatka <n> rozliczonych — pomiar, NIE kupon
SPORTY:   CS2 <n> / HOKEJ <n> / KOSZ <n> / SIATKA <n> pozycji (NIE kupon; cena bez marży, bez modelu); weta <n>
WSZYSTKIE: runs/sofa/multi/<data>/KUPON_<data>_WSZYSTKIE.pdf — <n> pozycji, sekcje <k>/5 (wyłączone: <…>)
D-1 WYNIKI: kupon <u> j. · WARIANT <u> j. · sporty <u>/<u>/<u>/<u> j. · WSZYSTKIE <u> j. (każdy osobno, nigdy sumowane) · pomiar fair p vs trafione per sport → dziennik · reguła CS2/HOKEJ/KOSZ/SIATKA <u> j. · MISMATCH <n> (audit_ledger.py)
CLV D-1:    kupon <x%> [lo; hi] · WARIANT <x%> · sporty <x%>/<x%>/<x%>/<x%> (audit_clv.py; każdy osobno)
AUDYT WARIANTÓW: <n> znalezisk
WERYFIKACJA: <n>/<n> arytmetyka, <n>/<n> ceny na żywo, <n> pozycji odrzuconych
UWAGA:    <największa słabość dnia, jedna>
```

Raporty z konkretnych dni i historia znalezisk: [`history/`](history/).
