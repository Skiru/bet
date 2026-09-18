# `sofa` — usterki z pierwszego przebiegu na żywo

**Otwarty 2026-09-18**, w trakcie pierwszego przebiegu `sofa` po odblokowaniu
Sofascore mostem przeglądarkowym. Żywy dokument: dopisujemy, gdy coś wyjdzie,
skreślamy, gdy naprawione.

Zasada: **każdy wpis ma dowód**. Jeśli czegoś nie zmierzono, jest to napisane
wprost, a wpis oznaczony `PODEJRZENIE`, nie `POTWIERDZONE`.

Legenda wagi: **P0** blokuje backfill · **P1** psuje dzień pracy ·
**P2** marnotrawstwo lub luka diagnostyczna · **P3** porządki.

---

## Zamknięte

Wszystkie naprawione 2026-09-18, każda z testem w
`tests/sofa/test_first_run_fixes.py` (14 testów).

Uczciwie o sile tych testów: `test_f4_resolver_skips_the_network_for_a_known_miss`,
`test_f11_*`, `test_f6_*` i `test_f8_*` failują na kodzie sprzed poprawki
**z właściwego powodu** — liczą zapytania, sprawdzają obecność artefaktu, luki
i pola. Testy `test_f1_*` failowałyby na starym kodzie przez `TypeError`
(`CircuitBreaker` nie przyjmował `cooldown_s`), więc pilnują zachowania na
przyszłość, ale nie są dowodem, że stary kod był zepsuty — tym dowodem jest
przebieg opisany w F1 i F11.

| # | Co zrobiono | Test |
|---|---|---|
| **F1** | `CircuitBreaker` ma stan half-open: po `breaker_cooldown_s` (30 s) przepuszcza **jedną** próbę; sukces zamyka obwód, porażka otwiera ponownie i podwaja odstęp do `breaker_max_cooldown_s` (300 s). Zegar wstrzykiwany, więc test nie śpi. | `test_f1_*` (5) |
| **F2** | Userscript 2.3.0: 403 nie jest już wynikiem końcowym — most czeka na odświeżenie tokenu i ponawia raz, zanim odda błąd. | ręczny (patrz niżej) |
| **F3** | Backfill wznawia się. Checkpointem jest **sama tabela `sofa_settled_row`**, nie osobny plik stanu — plik stanu może kłamać, wiersz w tabeli jest tym, co przebieg ma wyprodukować. `--no-resume` wymusza przeliczenie. | `test_f3_*` |
| **F4** | Tabela `sofa_entity_miss` z własnym TTL (7 dni). Nietrafiona nazwa kosztuje teraz jedno zapytanie na tydzień, nie cztery dziennie. Trafienie kasuje wpis. | `test_f4_*` (5) |
| **F5** | Artefakt powstaje także po przerwaniu — pętla nie wyrzuca już wyjątku poza siebie (patrz F11). | `test_f11_*` |
| **F6** | `EVENT_NOT_FINISHED` jest emitowane przy odrzuceniu meczu z próbki, ze statusem i id w `detail`. | `test_f6_*` |
| **F7** | `mypy --strict` przechodzi na **39 plikach** — `src/bet/sofa` **i** `scripts/sofa`. 76 „błędów" okazało się brakiem `py.typed`; realnych było 14 i wszystkie naprawione. Jeden z nich był prawdziwą kolizją: w `run_samples.py` `verdict` był jednocześnie zmienną pętli po `CoverageVerdict` i werdyktem etapu. | `mypy --strict` |
| **F8** | Każdy wiersz logu niesie `run_id`; `run_pipeline.py` bije jeden identyfikator na całą sekwencję. Koniec ze zgadywaniem momentu startu. | `test_f8_*` |
| **F10** | `check_bridge.py` mówi wprost, że serwer ginie z terminalem i podpowiada `nohup`. | — |
| **F11** | `run_resolve.py` łapie `ProviderError` **per fixture** — luka w slate'cie zamiast końca etapu. `CircuitOpenError` przerywa pętlę (dalsze próby nie mają sensu), ale artefakt i tak zostaje zapisany, a werdykt to `PARTIAL`. | `test_f11_*` |

---

## Otwarte

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
