# Odpowiedź na audyt końcowy pipeline'u `sofa`

**Data:** 2026-09-18
**Wobec:** `PLAN_SOFA_PIPELINE.md` i audytu z werdyktem NEGATYWNYM.
**Werdykt po tej rundzie:** **nadal nie wystawiam certyfikatu** — i poniżej jest
dokładnie napisane, czego brakuje i dlaczego.

Audyt miał rację w każdym punkcie A1–A7 i w większości C1–C10. Ten dokument
mówi, co naprawiono, co naprawiono *inaczej* niż plan przewidywał (bo okazało
się, że plan był w tym miejscu w błędzie), i co pozostaje niewykonane.

---

## 0. Stan uruchomieniowy

| Bramka | Przed | Po | Komenda |
|---|---|---|---|
| `pytest tests/sofa` | 1 failed, 63 passed | **215 passed, 2 skipped, 0 failed** | `pytest tests/sofa` |
| sieć w CI | wychodziła (403) | **zero sieci**, `sofa_live` odznaczany | `tests/sofa/conftest.py` |
| `ruff check` | 594 błędów | **0** | `ruff check src/bet/sofa scripts/sofa tests/sofa` |
| `mypy --strict src/bet/sofa` | 17 błędów | **0** | `mypy --strict src/bet/sofa` |
| pokrycie `engine.py` | niemierzone | **100%** | `pytest tests/sofa --cov=src/bet/sofa` |
| pełny przebieg 6 artefaktów | nie istniał | **przechodzi offline** | `pytest tests/sofa/test_e2e.py` |

Dwa `skipped` są celowe i głośne:
- `test_live_recall.py` — marker `sofa_live`, poza CI (włącz `SOFA_LIVE=1`);
- `test_e4_precision_ac_requires_a_measured_set` — pomija się z komunikatem
  „E4 precision AC NOT MET: golden set is 'partial_measured' with 5 of 60
  entries", czyli **brak AC jest widoczny w wyjściu testów**, a nie ukryty.

---

## 1. Blokada środowiskowa, która ogranicza tę rundę

Sofascore odpowiada **HTTP 403 `{"reason": "challenge"}`** na każde żądanie
z tej maszyny — `api.sofascore.com`, `www.sofascore.com/api/v1`, każdy
`impersonate`, także po rozgrzaniu sesji stroną główną (sama strona zwraca 200).

Superbet działa normalnie — `measure_mlb.py` pobrał z jego tablicy 50 realnych
fixture'ów MLB, więc to nie jest ogólny brak sieci.

Konsekwencja: **każde AC wymagające żywego Sofascore jest niewykonalne w tej
rundzie**. Dotyczy to E10 (20 000 wierszy), złotego zbioru 60 fixture'ów,
pomiaru baseballu i refitu E11. Kod tych etapów jest dostarczony i przetestowany
offline; brakuje im danych, nie implementacji. Nie zastąpiłem ich niczym
udawanym — to był główny zarzut audytu.

---

## 2. Zarzuty blokujące

### A1 — sfabrykowany pomiar baseballu → **USUNIĘTY**

`docs/sofa/evidence/mlb_measurement.md` z wymyślonymi liczbami
(„50 fixture'ów", „recall 82%") **skasowany**. `measure_mlb.py` przepisany na
realny pomiar: pobiera tablicę Superbetu, przepuszcza przez `resolve`, sonduje
`/event/{id}/statistics` pod kątem `runs`/`hits`, zapisuje surowe payloady do
`mlb_measurement_raw.json` i generuje raport **z tych payloadów**.

Uruchomiony: Superbet oddał 50 fixture'ów, Sofascore odrzucił wszystkie 50
żądań, więc skrypt napisał plik `NOT_MEASURED` mówiący wprost, że żadnej liczby
z niego cytować nie wolno, i wyszedł kodem 2. **Odpowiedź na pytanie audytu
„czy wykluczono baseball": w kodzie tak, w dowodzie nadal nie — ale teraz plik
sam to mówi.**

### A2 — `audit_sample_bias.py` pisał raport zgodności niczego nie sprawdzając → **NAPRAWIONE**

Przepisany na siedem realnych reguł, każda licząca arytmetyczną tożsamość na
obserwacjach dnia:

| Reguła | Co sprawdza |
|---|---|
| kartki: punkty vs żółte | `cards_points >= cards` na tym samym meczu (L4) |
| tenis: gemy z tie-breakiem | `games_total >= 6 × sets_total` (L5) |
| `_total` vs `_for` | `total == for(a) + for(b)` na h2h (L6) |
| towarzyskie | `competition_id` z listy wykluczeń w próbce piłki (§6.1) |
| nawierzchnia i format | każda obserwacja tenisa z nawierzchni i formatu fixture'u (§5.7) |
| inflacja zera | mediana metryki == 0 (L1) |
| jeden wiersz, jedna próbka | ten sam mecz dwa razy po jednej stronie (L13) |

Kluczowa zmiana kontraktu raportu: reguła, której **nie da się** policzyć,
raportuje `UNVERIFIABLE` z powodem — **nigdy `OK`**. `OK` znaczy „sprawdzono na
N obserwacjach", a N jest w raporcie.

Utrwalone testem (`tests/sofa/test_audit_bias.py`, 26 przypadków): każda reguła
łapie podłożone naruszenie i każda mówi `UNVERIFIABLE` na pustym dniu.

**Ta zmiana od razu złapała błąd w moim własnym kodzie** — pierwsza wersja
reguły nawierzchni czytała `defaultPeriodCount` z listingu i oflagowała 18
z 18 obserwacji tenisa. Patrz §4.

### A3 — E10 nie istniał → **DOSTARCZONY (kod), NIEWYKONANY (dane)**

Nowe: `src/bet/sofa/settle.py`, `scripts/sofa/run_backfill.py`,
`tests/sofa/test_settle.py` (36 przypadków).

- **T30** — `settle(actual, line, direction)` czysta, test tabelaryczny,
  PUSH na linii całkowitej dla **obu** kierunków.
- **T31** — osobna implementacja bramki wycieku na ścieżce backfillu, z testem
  na przypadek graniczny „mecz dokładnie o kickoffie".
- **T32** — `is_completed_event` czyta wyłącznie `status.type`/`status.code`.
  Test parametryzowany po nazwiskach: `"Berrettini"`, a także złośliwe
  `"Retief Retirement"` i `"Jiri Vesely (ret)"` — żadne nie jest krezem.

Kod statusu wyprowadzony z evidence, nie zgadnięty: w nagranych payloadach
występuje `code 100 "Ended"` (130 razy) i `code 91 "Walkover"` (raz). Reguła
jest **allow-listą** (`code == 100`), bo deny-lista musiałaby wyliczyć kody,
których nigdy nie widzieliśmy, a ten jeden pominięty cicho stałby się
rozliczonym wierszem.

**Niewykonane:** `sofa_settled_row` ma 0 wierszy. AC (≥20 000 wierszy, ≥8 lig,
≥3 miesiące) i ręczna kontrola transkrypcji 20 wierszy — **niemożliwe bez
Sofascore**. `run_backfill.py` raportuje `meets_ac: false` z liczbami.

### A4 — E11 wyprodukował stałe, których §6.0 zakazuje → **NAPRAWIONE**

`config/sofa_engine_constants.json` **nie twierdzi już, że cokolwiek zmierzono**:

```json
"K_CENTRE":         { "value": null, "status": "NOT_FITTED", "curve": {} },
"K_PRICE":          { "value": null, "status": "NOT_FITTED", "curve": {} },
"MAX_LADDER_SIGMA": { "value": null, "status": "NOT_FITTED",
                      "reason": "needs rows settled against a live Superbet
                                 ladder; backfilled rows have market_p = NULL" },
"fitted_from":      { "settled_rows": 0, "distinct_competitions": 0 }
```

`MAX_LADDER_SIGMA` to osobne ustalenie tej rundy: **nie da się go zfitować
z backfillu w ogóle**, bo historycznych drabin Superbetu nie ma. Wcześniej
funkcja zwracała `return 1.25  # TBD` — liczbę zmierzoną na rozrzucie innego
providera, nieodróżnialną od zfitowanej. Teraz zwraca `None` z powodem, a do
`sofa_settled_row` doszła kolumna `ladder_sigma`, żeby rozliczanie live mogło ją
kiedyś zfitować.

Silnik startuje na jawnie oznaczonych wartościach tymczasowych i **każdy wiersz
arkusza niesie `notes: ["UNFITTED_CONSTANTS: K_CENTRE, K_PRICE,
MAX_LADDER_SIGMA"]`** — nieskalibrowany silnik nie może udawać skalibrowanego.

Naprawione defekty samego fitu (C5):
- baseline grupuje po `(competition_id, market, subject, event)`, nie po samym
  evencie — `MAX` po evencie na rynku `_for` brał zawsze większą stronę
  i systematycznie podnosił prior. Test: `{8, 2}` daje 5.0, nie 8.0.
- zniknął filtr `outcome != 'PUSH'`, który wycinał dokładnie mecze lądujące na
  linii całkowitej — nielosowy wycinek rozkładu usuwany ze statystyki o wartościach.
- wybór `K` to **najmniejsza wartość na plateau**, nie minimum punktowe.
- `import sys` (skrypt wywracał się na własnej ścieżce błędu).

### A5 — T36 nie był testem e2e → **PRZEPISANY**

Poprzedni mockował `fetch_board`, podmieniał całe `run_offer.main` na funkcję
piszącą `[]`, łykał wyjątek z SAMPLES i asertował istnienie plików. Nowy:

- uruchamia **prawdziwe `main()` każdego etapu** przez nowy orkiestrator;
- **nie łapie żadnego wyjątku** — etap, który rzuci, wywala test;
- **pustka jest porażką**: każdy artefakt asertowany jako niepusty, liczby
  wierszy zamrożone w `e2e_expected.json`;
- każdy artefakt przechodzi `model_validate_json` z bajtów na dysku (T15);
- osobno sprawdza, że `edge == round(p_central − market_p, 4)` na każdym
  wycenionym wierszu.

Realny przebieg: 3 fixture'y (2 piłka, 1 tenis) → 3 READY → 7 szczebli →
**14 wierszy arkusza** → 2 single. Poprzednia wersja przechodziła przez silnik
nie licząc ani jednego wiersza.

Bundle (`tests/fixtures/sofascore/e2e_bundle.json`) jest generowany
odtwarzalnym skryptem `build_e2e_bundle.py` i **sam deklaruje swoje pochodzenie**:
kształty są realne (payloady z `evidence/`), ale obsada jest częściowo pochodna —
tylko dwie encje nagrano z pełnym listingiem, a dzień o trzech fixture'ach
potrzebuje sześciu. Plik mówi wprost: to strażnik regresji na granicach etapów,
**nie pomiar pokrycia ani jakości dopasowania**.

### A6 — T04 mierzony na własnym mocku → **PRZEBUDOWANY, AC NADAL NIESPEŁNIONE**

Ręcznie pisany `MockClient` zniknął. Złoty zbiór niesie teraz **surowe payloady**
i test odtwarza je (`ReplayClient` serwuje dokładnie to, co nagrano, a na
zapytanie bez nagranej odpowiedzi zwraca pustkę, nie zgadywankę).

Wpisy są realne — zbudowane z `search_all_real_madrid.json`,
`team_2829_events_last_0.json`, `team_275923_events_last_0.json` — w tym
**negatyw, którego wcześniej nie było**: „Real Madrid·Wolverhampton" w dniu
realnego meczu Realu. To jest dokładnie ta porażka, której plik mierzący sam
recall nie odróżnia od sukcesu.

Plik ma pole `kind`. Test **odmawia cytowania precyzji** z czegokolwiek innego
niż `kind: "measured"`, a `partial_measured` (5 z 60 wpisów) daje SKIP
z komunikatem o niespełnionym AC. `build_golden_set.py` zbuduje prawdziwy zbiór,
gdy sieć wróci — z `expected: null` w każdym wpisie, bo **etykietę stawia
człowiek**, nie maszyna.

### A7 — CI nie było offline → **NAPRAWIONE**

`tests/sofa/conftest.py` odznacza `sofa_live` przez
`pytest_collection_modifyitems` (opt-in: `SOFA_LIVE=1` albo `--sofa-live`).
`pytest tests/sofa` nie dotyka sieci.

---

## 3. Defekty C1–C10

| # | Status | Co zrobiono |
|---|---|---|
| C1 | naprawione | `specialBetValue: null` nie jest już linią 0.0 i nie wywraca OFFER; rynek bez linii ląduje w `unmapped_markets` |
| C2 | naprawione | `get_historical_events` idzie przez cache TTL; parametr przestał być ozdobą |
| C3 | naprawione | `readiness` liczona **per metryka**; nagłówek to najlepsza metryka, ale mapa `readiness_by_metric` jest w podsumowaniu |
| C4 | naprawione | `quote(q, safe="")` w `search()` |
| C5 | naprawione | patrz A4 |
| C6 | naprawione | marker rezerw kotwiczony na **końcu** nazwy; `"FC B Team"` przestało być rezerwami |
| C7 | naprawione | `determine_side` zwraca `None` przy braku dopasowania i przy remisie — wiersz wypada z powodem zamiast lądować u gospodarza |
| C8 | częściowo | emitowane są `ALL_ZERO_SAMPLE`, `THIN_SAMPLE`, `PROVIDER_ERROR`, `CIRCUIT_OPEN`; `identity` przyjmuje `FUZZY`; `STALE_PRICE` raportowane w `06_dropped.json`. `EVENT_NOT_FINISHED` pozostaje nieużyte |
| C9 | naprawione | `scripts/sofa/run_pipeline.py`; A4 (oferta dwa razy) jest w kodzie, nie w konwencji uruchamiania |
| C10 | naprawione | `metrics_fix.py`, `*.bak`, `*.orig`, `*.rej` i 20 plików roboczych z katalogu głównego usunięte |

Dwa wyłomy z części B, obie naprawione:

**Bramka `ladder_sigma` nie jest już furtką.** Było: `l_sigma is None → VALUE`
z komentarzem pytającym samego siebie o poprawność. `None` powstaje przy <2
szczeblach, przy drabinie po jednej stronie 0,5 i przy `sample_sd == 0` — czyli
tam, gdzie informacji jest najmniej. Skoro §3.2 czyni tę bramkę **główną
namiastką korroboracji**, brak pomiaru znaczy brak kontroli, a nie zgodę:
wiersz schodzi do `LEAN` z notatką `NO_LADDER_CHECK`. Trzy testy na produkcyjnej
ścieżce (`test_sheet.py`).

**Powody odrzucenia przestały ginąć.** `build_coupon` zwraca `CouponResult`
z listą `DroppedRow`; `run_coupon` pisze `06_dropped.json` i tabelę
w `06_coupon.md`. Doszedł też powód `FAMILY_SLOT_TAKEN`, którego wcześniej
w ogóle nie było.

`06_coupon.md` zawiera teraz pełną próbkę, `edge`, środek drabiny,
`ladder_sigma`, `bar_reason` i **rozpisaną arytmetykę** — np.
`3.0363 = 1.10 / 0.3623; nadwyżka 3.60 − 3.0363 = +0.5637`.

---

## 4. Co w planie (albo w audycie) okazało się błędne

Plan prosił o to w §10 pkt 5. Cztery rzeczy.

### 4.1 `entity_events` zwracał kopertę, a SAMPLES iterował po niej jak po liście

`client.entity_events` oddaje `{"events": [...], "hasNextPage": ...}`
(potwierdzone: `evidence/team_2829_events_last_0.json`), a
`get_historical_events` iterował po tym obiekcie wprost — czyli po kluczach
`"events"` i `"hasNextPage"` jako po stringach. **Na żywo SAMPLES nie mógł
zbudować ani jednej próbki.** Testy tego nie łapały, bo mock zwracał gołą listę:
test kodował błąd. Audyt tego nie zauważył.

### 4.2 `defaultPeriodCount` nie istnieje w listingu — filtr tenisa odrzucał wszystko

Plan §5.7 mówi „format meczu to pole, nie wniosek z nazwy turnieju" i każe
filtrować próbkę po `best_of`. To pole jest na `/event/{id}` — ale **nie ma go
w listingu**: `evidence/team_275923_events_last_0.json` niesie `groundType`
w 30 z 30 eventów i `defaultPeriodCount` w **0 z 30**. Filtr porównywał więc
`None != 5` i wycinał każdy mecz historyczny. To jest L14 w czystej postaci —
bramka nieosiągalna wygląda jak brak danych.

Naprawa nie kosztuje ani jednego dodatkowego wywołania: **listing rozstrzyga
format sam**. Zwycięzca ma w `current` liczbę wygranych setów, a ta jest
jednoznaczna — 3 wygrane sety to BO5 (BO3 nigdy nie dojdzie do trzech), 2 to
BO3 (zwycięzca BO5 potrzebuje trzech). Sprawdzone na nagranym listingu:
15345277 (Australian Open) → 5, 15543167 (Doha) → 3; reguła rozstrzyga 30 z 30
meczów. To jest lepsze niż plan, bo nie wymaga pomiaru ani dodatkowej rundy.

### 4.3 §5.4a — tej liczby nie trzeba było mierzyć, trzeba było przestać jej trzymać

Plan żądał pobrania meczu z drugą żółtą, żeby rozstrzygnąć, czy `yellowRed` jest
wart +1 czy +3. Audyt słusznie zauważył, że kod trzymał zgadnięte `+2`, a
`incidents_second_yellow.json` był ręcznie napisany.

Ale to pytanie nie potrzebuje odpowiedzi. Superbet liczy wykluczenie za drugą
żółtą jako **3 punkty łącznie**; jedyna niewiadoma to, ile osobnych incydentów
`yellow` Sofascore dołoży obok. Payload odpowiada na to **sam, per mecz**: liczy
się stojące żółte tego zawodnika i dopłaca resztę do trzech. Wynik jest poprawny
przy każdej z trzech możliwych konwencji — i **zostanie poprawny, jeśli
Sofascore zmieni konwencję**, czego pomiar jednego meczu by nie zapewnił.

Fixture przepisany na trzy warianty, jawnie oznaczony `SYNTHETIC`, z testem że
każdy daje 3.0. Plus przypadki, których plan nie przewidział: dwaj wykluczeni
zawodnicy nie pożyczają sobie żółtych (6, nie 3), a anulowana pierwsza żółta
nadal daje 3.

### 4.4 `edge` w artefakcie nie zgadzał się z własnymi liczbami

`edge` liczony był z nieokrągłonych `p_central` i `market_p`, a artefakt
publikuje obie do 4 miejsc. Czytelnik odejmujący dwie wydrukowane liczby
dostawał `0.1435` tam, gdzie pole mówiło `0.1434`. Teraz zaokrąglenie jest
pierwsze, odejmowanie drugie — raport zgadza się z własną arytmetyką (L27).
Złapane przez nowy e2e, nie przez audyt.

---

## 5. Czego nadal nie ma — lista otwarta

| # | Brak | Blokada |
|---|---|---|
| 1 | `sofa_settled_row` = 0 wierszy; AC E10 (20 000 / 8 lig / 3 miesiące) | Sofascore 403 |
| 2 | Ręczna kontrola transkrypcji 20 rozliczonych wierszy | j.w. |
| 3 | Złoty zbiór 60 fixture'ów z etykietami; **precyzja E4 nigdzie nie zmierzona** | j.w. + praca ręczna |
| 4 | Realny fit `K_CENTRE`, `K_PRICE`, `MAX_LADDER_SIGMA`, baseline'y lig, krzywa kalibracji | wymaga #1 |
| 5 | Pomiar baseballu | Sofascore 403 |
| 6 | Weryfikacja live po E4/E6/E8/E9 + 3 fixture'y ręcznie w przeglądarce | j.w. |
| ~~7~~ | ~~Pokrycie `engine.py` ≥ 95%~~ | **spełnione: 100%** (`pytest tests/sofa --cov=src/bet/sofa`) |
| 8 | `EVENT_NOT_FINISHED` w `GapReason` nadal nieemitowane | drobne; enum obiecuje diagnostykę, której nie ma |
| 9 | `mypy --strict` na `scripts/sofa/**` — czysty jest `src`, skrypty nie | AC planu mówi o `src/bet/sofa/**`; `run_sheet.py` dociągnięty, reszta nie |
| 10 | Podłoga pokrycia (T40) podpięta, ale bez historii 3 przebiegów raportuje `NO_BASELINE` | wymaga 3 realnych dni |

---

## 6. Ścieżka do certyfikatu

Siedem kroków audytu, w kolejności, ze statusem:

1. ~~skasować A1 i A2~~ → **zrobione**; oba pomiary wykonują się naprawdę albo
   mówią `NOT_MEASURED` / `UNVERIFIABLE`.
2. ~~dostarczyć E10~~ → **kod zrobiony i przetestowany, dane czekają na sieć**.
3. refit E11 na jego wyniku → **blokowane przez 2**; skrypt naprawiony, pliki
   uczciwie puste.
4. prawdziwy złoty zbiór i prawdziwy e2e → **e2e zrobiony; złoty zbiór
   blokowany przez sieć, ale test nie udaje już, że AC jest spełnione**.
5. ~~rozstrzygnąć `yellowRed` realnym payloadem~~ → **rozwiązane inaczej
   i lepiej**: wyprowadzane z payloadu w locie, poprawne przy każdej konwencji.
6. ~~wykluczyć towarzyskie~~ → **zrobione**, `config/sofa_friendly_competitions.json`,
   dwa id potwierdzone payloadem (853 Club Friendly Games, 1794 MLS All Star Game),
   każde ze ścieżką do pliku dowodowego.
7. ~~podpiąć podłogę pokrycia i domknąć bramkę `ladder_sigma`~~ → **zrobione**.

**Co to znaczy praktycznie:** pipeline jest gotowy na pełny przebieg od strony
kodu — orkiestrator działa, wszystkie sześć artefaktów powstaje, waliduje się
własnymi modelami i zgadza się z własną arytmetyką, a każdy etap zwraca
`0/1/2`. Czego **nie wolno** o nim powiedzieć: że jest skalibrowany. Nie jest,
wie o tym, i pisze to na każdym wierszu, który wyprodukuje.
