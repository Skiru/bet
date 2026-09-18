# `sofa` — usterki z pierwszego przebiegu na żywo

**Otwarty 2026-09-18**, w trakcie pierwszego przebiegu `sofa` po odblokowaniu
Sofascore mostem przeglądarkowym. Żywy dokument: dopisujemy, gdy coś wyjdzie,
skreślamy, gdy naprawione.

Zasada: **każdy wpis ma dowód**. Jeśli czegoś nie zmierzono, jest to napisane
wprost, a wpis oznaczony `PODEJRZENIE`, nie `POTWIERDZONE`.

Legenda wagi: **P0** blokuje backfill · **P1** psuje dzień pracy ·
**P2** marnotrawstwo lub luka diagnostyczna · **P3** porządki.

---

## Otwarte

### F1 · P0 · Bezpiecznik nie ma powrotu

`CircuitBreaker` (`src/bet/sofa/client.py`) otwiera się po
`breaker_threshold` błędach i **nie zamyka się nigdy** — nie ma stanu
half-open ani resetu po czasie. `record_success()` zeruje licznik, ale
`is_open` blokuje wywołanie, zanim do sukcesu w ogóle dojdzie. Obwód raz
otwarty jest martwy do końca życia obiektu klienta.

**Dowód.** Smoke test E1 z 2026-09-18: most padł na kilkanaście sekund,
5 żądań dało błąd, a pozostałe 25 zakończyło się `Circuit breaker is open`
mimo że most wrócił kilka sekund później. Wynik: `{None: 5}` zamiast 30 × 200.

**Skutek.** Backfill na 20 000 wierszy (~3 h) zginie przy pierwszym
mignięciu mostu — na przykład przy przeładowaniu karty odnawiającym
`x-captcha`, które zdarza się z definicji co ~godzinę.

**Poprawka.** Stan half-open: po `breaker_cooldown_s` przepuść jedno żądanie
próbne; sukces zamyka obwód, porażka otwiera ponownie i wydłuża odstęp.

---

### F2 · P1 · Most gubi zadanie trafiające w przeładowanie karty

Gdy userscript wykryje trzy kolejne 403 i przeładuje stronę, żądania
wykonywane w tym oknie kończą się 403 i **przepadają** — kolejka nie ponawia,
oddaje 403 do pipeline'u, a ten liczy je jako błąd providera (i dokłada do
bezpiecznika, patrz F1).

**Dowód.** RESOLVE 2026-09-18, 18 × 403 skupione w wąskim oknie wokół
jednego eventu (`event/16640655` siedmiokrotnie) i trzech wyszukiwań; przed
i po — zero. Reszta przebiegu: 1 301 × 200, 0 × 403.

**Skutek.** ~2% fixture'ów wypada ze slate'u bez powodu merytorycznego.
Przy backfillu ten sam mechanizm zostawia dziury w historii.

**Poprawka.** W `bridge_server.py`: 403 nie jest wynikiem końcowym — odczekaj
na przeładowanie i ponów raz. Dopiero drugie 403 idzie do pipeline'u.

---

### F3 · P0 · Backfill nie jest wznawialny

`scripts/sofa/run_backfill.py` nie zapisuje checkpointu. Przebieg AC E10
(20 000 wierszy, 8 lig, 3 miesiące) trwa przy 2 req/s około 3 godzin i po
przerwaniu zaczyna od zera.

**Status: PODEJRZENIE** — wywnioskowane z braku checkpointu w kodzie, nie
zmierzone przebiegiem. Zweryfikować przed pierwszym backfillem.

**Łagodzące.** Cache statystyk meczów jest wieczny (patrz F4), więc powtórka
nie płaci drugi raz za pobrane mecze. Traci się czas na przejście listy, nie
same dane.

---

### F4 · P2 · Cache negatywny zaprojektowany, nigdy nie podłączony

`resolve.py` wywołuje `cache.save_entity(...)` **wyłącznie po sukcesie**.
Gdy nic nie pasuje, zwraca `None, None, False` i nie zostawia śladu. Ta sama
drużyna będzie odpytywana co dzień, w nieskończoność.

**Dowód, że to przeoczenie, a nie decyzja.** Docstring `cache.get_entity`
brzmi: *„Pobiera encję z bazy (trafienie w cache, **w tym 'rejected'**)"* —
schemat przewiduje status odrzucenia, którego nikt nie zapisuje. W bazie po
1 522 żądaniach: 179 encji, **wszystkie `verified`**, zero `rejected`.

**Skutek.** ~15% odpowiedzi to 404. Każda nierozpoznana drużyna kosztuje
wyszukanie plus do trzech listingów, codziennie. Szacunkowo 20–25% budżetu
żądań idzie na ustalanie w kółko tego samego negatywnego faktu.

**Poprawka.** `save_entity(status="rejected")` w gałęzi „nie znaleziono",
z własnym, krótszym TTL (tydzień?), żeby drużyna dodana do Sofascore później
dostała drugą szansę.

---

### F5 · P2 · Artefakt RESOLVE powstaje dopiero na końcu

`run_resolve.py:111` zapisuje `02_fixtures.json` po przejściu całej pętli.
Przerwanie w 59. minucie nie zostawia artefaktu.

**Łagodzące i zmierzone.** Wywołania API **nie** przepadają: SQLite działa
w `journal_mode=delete`, `synchronous=FULL`, a dane są zacommitowane na
bieżąco — odczytywałem je z osobnego procesu w trakcie przebiegu. Ponowny
start w ciągu 6 h (TTL listingów) odtworzy artefakt z cache'u w minuty.
Traci się minuty, nie godzinę.

---

### F6 · P2 · `EVENT_NOT_FINISHED` nigdy nie jest emitowane

Wartość istnieje w `GapReason` i nie jest nigdzie ustawiana. Enum obiecuje
diagnostykę, której nie ma. (Przeniesione z `AUDIT_RESPONSE.md` §5 poz. 8.)

---

### F7 · P3 · `mypy --strict` nie obejmuje `scripts/sofa/**`

Czysty jest `src/bet/sofa`. Ze skryptów dociągnięty tylko `run_sheet.py`.
AC planu mówi o `src`, więc formalnie spełnione — ale skrypty to jedyne,
co uruchamia operator. (Przeniesione z `AUDIT_RESPONSE.md` §5 poz. 9.)

---

### F8 · P3 · `run.log.jsonl` jest kumulatywny i nierotowany

Jeden plik zbiera żądania ze wszystkich dni i wszystkich etapów. Analiza
pojedynczego przebiegu wymaga ręcznego filtrowania po `ts_utc` — robiłem to
dziś trzy razy, za każdym razem zgadując moment startu.

**Poprawka.** Katalog na dzień (`runs/sofa/<data>/run.log.jsonl`) albo pole
`run_id` w wierszu.

---

### F9 · P3 · 62% tablicy Superbetu to dyscypliny bez nazwy w kodzie

`SPORT_IDS` w `superbet.py` zna dwa id: 5 (piłka), 2 (tenis). Pomiar surowej
tablicy z 2026-09-18: **3 945 wydarzeń**, z czego brane 669 (po odrzuceniu
52 debli i wierszy bez kickoffu w dobie → 613).

Trzy największe odrzucone kubełki nie mają w kodzie nawet nazwy:
`sportId=75` (960), `sportId=24` (826), `sportId=190` (654) — razem 2 440,
czyli 62% tablicy.

Nie twierdzę, że należy je obstawiać. Twierdzę, że **nie wiemy, co
odrzucamy**, a to jest pięć minut roboty. Punkt wyjścia, gdyby kiedyś padło
pytanie o rozszerzenie `sofa` o kolejną dyscyplinę.

---

### F10 · P3 · Serwer mostu nie ma nadzoru

`bridge_server.py` uruchamiany w terminalu ginie razem z nim. Zdarzyło się
raz 2026-09-18 i objawiło się jako `Connection refused` w środku smoke testu
(patrz F1, które to spotęgowało).

**Poprawka.** `launchd`/`nohup` z restartem albo jawny komunikat w
`check_bridge.py`, że serwer powinien żyć poza sesją terminala.

---

## Zamknięte

*(puste — dopisujemy po naprawie, z datą i commitem)*

---

## Zanotowane, nie do naprawy w kodzie

- **Id sezonów wygasają.** `season_events(17, 65275)` daje prawdziwe 404 —
  to id Premier League z `evidence/` z 2026-09-17, a aktualne PL 26/27 to
  **96668**. Sprawdzone: nigdzie w `src`/`scripts`/`config` nie ma
  zahardkodowanych id sezonów. Brać je zawsze z
  `/unique-tournament/{id}/seasons`, nigdy z plików dowodowych.

---

## Pomiary architektoniczne (żeby nie powtarzać)

### Gdzie idzie czas — RESOLVE, 2026-09-18

| | |
|---|---|
| żądań | 2 258 |
| zegar ścienny | 1 135,6 s |
| czas w sieci | 458,9 s (40,4%) |
| **podłoga z limitu 2 req/s** | **1 129 s** |
| wszystko poza siecią (pacing + obliczenia) | **6,6 s — 0,6%** |

**Wniosek: 99,4% czasu przebiegu to limit tempa, który sami narzuciliśmy.**
Zrównoleglenie obliczeń przyspieszyłoby go o pół procenta. Wąskim gardłem jest
most przeglądarkowy (jedna karta, szeregowo, 2 req/s), i to jest wybór, nie
ograniczenie techniczne — patrz `sofascore-rate-limit-hygiene`.

Jedyny etap naprawdę ograniczony procesorem to **masowe przeliczenie metryk
z cache'u** (20 000 meczów, zero sieci) po zmianie kodu. Wtedy, i tylko wtedy:
WAL + `ProcessPoolExecutor` po `event_id`. Nadal SQLite.

### Rozmiar bazy

180 MB po 1 400 listingach (śr. 125 KB na listing). Projekcja po pełnym
backfillu: **~1 GB**. SQLite tego nie zauważy.

Postgres nie rozwiązuje tu żadnego istniejącego problemu: baza jest cache'em
niezmiennych payloadów, kluczowanym po id, z **jednym procesem piszącym**,
dławionym siecią do 2 zapisów na sekundę. Jedyna realna słabość SQLite —
współbieżny zapis z wielu procesów — nie występuje.

`journal_mode=delete` + `synchronous=FULL` zostaje. Przy 2 zapisach/s koszt
jest niemierzalny, a to właśnie te ustawienia sprawiają, że zacommitowane dane
przeżywają ubicie procesu.

### Podział baza vs JSON — zamierzony, zostaje

- **JSON to przepływ.** Sześć artefaktów, każdy wejściem następnego. SHEET da
  się przeliczyć na wczorajszych próbkach bez sieci i bazy, a każdy wiersz
  kuponu jest odtwarzalny za pół roku. W pipelinie zakładowym odpowiedź na
  „skąd wziął się ten zakład" jest warta więcej niż wydajność.
- **Baza to cache i historia.** Drogie payloady (wieczne dla zakończonych
  meczów) plus `sofa_settled_row` do zapytań przekrojowych.

Trzymanie **surowych** payloadów wygląda na marnotrawstwo miejsca, a jest
ubezpieczeniem: pozwala przeliczyć metryki od nowa po zmianie kodu bez ani
jednego zapytania. Przy tak kruchym dostępie do Sofascore to jest tego warte.
