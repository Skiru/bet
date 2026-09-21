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
date -u +%F                                             # doba zakładowa jest w UTC
.venv/bin/python scripts/sofa/check_bridge.py           # most, ZAWSZE pierwszy
```

Most: **`ok: true` nie wystarcza.** Martwa karta przeglądarki nadal melduje
`ok`. Liczy się **wiek ostatniego pobrania**. Jeśli karta nie żyje — poza BOARD,
OFFER i etapami offline nic nie ruszy. Nie próbuj obejścia i **nigdy nie
podnoś `SOFA_TARGET_RPS`**.

Podniesienie mostu (robi to **operator**, nie agent — agent ma się zatrzymać
i powiedzieć, że most stoi):

```bash
# serwer umiera razem z terminalem, który go uruchomił — na długi przebieg odetnij:
nohup .venv/bin/python scripts/sofa/bridge_server.py > /tmp/sofa_bridge.log 2>&1 &
```

1. otwórz kartę na `sofascore.com` z aktywnym userscriptem
   `userscripts/sofascore-bridge.user.js`;
2. karta sama zaczyna odpytywać serwer — to ona wykonuje żądania, nie proces
   pythonowy;
3. `check_bridge.py` ponownie: trzy linie OK **i świeży wiek pobrania**;
4. karta musi zostać **otwarta i aktywna** przez cały przebieg. Uśpiona karta
   przestaje odpytywać, a most nadal melduje `ok`.

`check_bridge.py` sprawdza dokładnie trzy rzeczy w kolejności i mówi, która
padła: (1) serwer nasłuchuje, (2) jakaś karta go odpytuje — `last_pull_age_s`,
powyżej **30 s** dostajesz `WARN`, (3) prawdziwe zapytanie `/api/v1/` wraca 200
z JSON-em. **403 w punkcie trzecim znaczy przeterminowany `x-captcha` karty** —
przeładuj `sofascore.com`, nie zmieniaj niczego w kodzie.

Interpreter: `.venv/bin/python` (3.12). `.venv/bin/pip` należy do 3.14
i instaluje tam, gdzie nikt tego nie zaimportuje — instaluj przez
`.venv/bin/python -m pip`.

---

## 1. Rozlicz wczoraj (D-1)

Przed dzisiejszym dniem, bo to karmi kalibrację i **konkuruje o most**.

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only SETTLE
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settlement.py --date <D-1>
```

- `PARTIAL` to normalny werdykt.
- **Sekcja 7c audytu to prawdziwy wynik kuponu z PDF.** Sekcje 7 i 7b to
  materiał wejściowy (legi i kandydaci), **nie zakłady**.
- `07_settle_skips.json`: wiersz, którego nie dało się ocenić, **nie jest
  przegraną**.

Głębiej i z decyzją o fitowaniu: `/sofa-settle` albo agent `sofa-settler`.

---

## 2. Dzisiaj

BOARD dotyka tylko Superbetu, więc może iść, gdy SETTLE trzyma jeszcze most.

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <data> --only BOARD --run-id <id>
# gdy SETTLE skończy:
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
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <data> --only OFFER
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <data> --only COUPON
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <data>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <data>
```

- Odśwież OFFER, jeśli poprzedni jest starszy niż **45 minut** — inaczej oba
  etapy odrzucą każdą cenę, a pusty wynik będzie wyglądał na wniosek
  analityczny.
- Przy **późnym** odświeżeniu dodaj `--min-minutes-to-kickoff 20`, żeby etap
  nie spędził ~90 minut na wycenie meczów już rozegranych.
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

---

## 5. Weryfikacja — nie do pominięcia

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <data>
```

Potem oddaj dzień agentowi `sofa-verifier` (`/sofa-verify`). Protokół:
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
| most padł w połowie SAMPLES | Napraw kartę, potem `--from-stage SAMPLES --run-id <ten sam id>`. Artefakty z dysku zostają. |
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
SHEET:    <n> wierszy, <n> VALUE (<n> piłka / <n> tenis)
RUN:      <run_id> · <werdykt> · <n> na tablicy → <n> dopasowanych (<x>%) → <n> READY
WETA:     <n> zastosowanych, <n> bez dopasowania
SETTLE:   D-1 <n> wierszy, PDF-kupon <w>/<n> slipów (sekcja 7c)
WERYFIKACJA: <n>/<n> arytmetyka, <n>/<n> ceny na żywo, <n> pozycji odrzuconych
UWAGA:    <największa słabość dnia, jedna>
```

Raporty z konkretnych dni i historia znalezisk: [`history/`](history/).
