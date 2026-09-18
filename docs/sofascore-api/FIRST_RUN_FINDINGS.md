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

### F12 · P2 · Slate schodzi do lig, w których nie ma danych

Tablica Superbetu zawiera U17, U19 i czwarte/szóste ligi. Sofascore nie
prowadzi dla nich statystyk połówkowych: `period1` brakuje w **100%** meczów
Liga 4 Teleorman, Liga Elitelor U17, Campionatul Național U19, w ~95% fińskiej
Nelonen i w 46 z 60 IV ligi kujawsko-pomorskiej.

Kod obsługuje to poprawnie (`STAT_KEY_ABSENT`, nigdy zero), więc to nie jest
usterka danych. Ale pipeline płaci pełną cenę w zapytaniach za fixture'y,
z których nie da się zbudować połowy rynków.

**Decyzja operatora, nie poprawka.** Opcje: próg poziomu rozgrywek w BOARD,
lista wykluczeń, albo świadome zostawienie tak jak jest.

---

## Zamknięte — F9 (2026-09-18)

Nazwane wszystkie duże kubełki `sportId` z tablicy Superbetu (4 108 zdarzeń
tego dnia). Potwierdzone próbką nazw meczów, nie zgadywane:

| sportId | co to jest | n | dowód | brane? |
|---|---|---|---|---|
| 75 | **e-piłka (FIFA)** | 1 034 | 100% nazw ma nick gracza: `Maroko (Lumix)·Belgia (Tesla)` | nie, słusznie |
| 24 | **tenis stołowy** | 862 | czeskie Liga Pro, mecze co kilkanaście minut | nie, poza zakresem |
| **190** | **piłka nożna KOBIET** | **646** | **100% nazw ma sufiks `(W)`**: `Arsenal (W)·Liverpool (W)` | **nie — i to jest do przemyślenia** |
| 5 | piłka mężczyzn | 395 | — | tak |
| 2 | tenis | 283 | — | tak |
| 70 | **e-koszykówka (NBA2K)** | 245 | `New York Knicks (ARACHNE)·…` | nie, słusznie |
| 3 | hokej | 97 | — | nie |
| 4 | koszykówka | 87 | — | nie |

**Najważniejsze: piłka kobiet to 646 zdarzeń — więcej niż piłka mężczyzn (395)**
— a `sofa` pomija ją w całości. To nie są dane gorszej jakości ani e-sport:
Sofascore prowadzi WSL i inne ligi kobiece tak samo jak męskie. Cały aparat
(metryki, drabiny, silnik) zadziałałby bez zmian; `SPORT_IDS` w `superbet.py`
zna po prostu dwa id.

Reszta odrzuconego wolumenu broni się sama: 1 279 zdarzeń to e-sport
(symulacje, nie mecze), 862 to tenis stołowy, którego `sofa` nie modeluje.

**Do decyzji: czy dodać `sportId=190`.** Koszt to jedna linia w `SPORT_IDS`
plus weryfikacja, że RESOLVE trafia w nazwy z sufiksem `(W)` — bo
`normalize_name` może go zjeść i pomylić drużynę kobiet z męską. **Tego nie
sprawdziłem i to jest realne ryzyko**, nie formalność.

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


---

## Audyt semantyczny pobranych danych (2026-09-18)

Wykonany na tym, co RESOLVE zdążył pobrać przed przerwaniem: **271 encji,
1 748 listingów, 43 985 zdarzeń**. Bez sieci — wyłącznie na cache'u i plikach
dowodowych.

### Czysto

| Sprawdzenie | Wynik |
|---|---|
| Tożsamość encji | **0** id osiągalnych z więcej niż jednej nazwy, **0** nazw wskazujących więcej niż jedno id. Mapowanie 1:1. |
| Klucze metryk | Wszystkie **30** zadeklarowanych metryk (22 piłka, 8 tenis) mają realne źródło. 13 to klucze ze `statistics`, reszta wyprowadzana z listingu/incydentów. **Zero literówek.** |
| Pola listingu | `id`, `startTimestamp`, `homeTeam`, `awayTeam`, `homeScore`, `awayScore`, `status.type` — **100%** obecności. `winnerCode` 99,9%. |
| Spójność listing↔encja (piłka) | **0** zdarzeń zapisanych pod encją, której nie dotyczą, z 28 876. |
| Najgorsze dopasowania nazw | Skróty i diakrytyki (`NuPS → Nummelan Palloseura`, `ŁKS Łomża`, `Świt Skolwin Szczecin`, `plaza amador (r) → Plaza Amador Reserves U20`), nie pomyłki. Dodatkowo RESOLVE przyjmuje encję dopiero po znalezieniu meczu zgodnego co do kickoffu i przeciwnika, więc sama podobność nazwy nie wystarcza. |

### Dwie rzeczy warte wiedzy (obie obsłużone poprawnie)

**Deble rozcieńczają listing tenisisty.** 24,7% zbuforowanych zdarzeń
tenisowych (3 737 z 15 109) to mecze deblowe, w których `homeTeam` to para
o własnym id. Kod je odrzuca bramką `home_id != entity_id and away_id !=
entity_id`, więc do próbki nie wchodzą — i dobrze, bo `gamesWon` z debla nie
opisuje singla, a atrybucja strony byłaby odwrócona. Zmierzone skutki
rozcieńczenia: **mediana 61 dostępnych meczów singlowych** na encję, tylko
3,2% encji poniżej 10, **zero** encji bez singli. Nie zagłodzi próbki.

**Połówki nie istnieją w 16% meczów piłkarskich.** `homeScore.period1`
występuje w 84,4% zakończonych meczów, `period2` w 83,0%. Kod zwraca
`STAT_KEY_ABSENT`, **nigdy zera** — czyli bez pułapki „zero znaczy brak".
Mediana meczów z `period1` w próbce last-10 to **10,0**, a poniżej progu
`min_sample=5` wpada 15,9% encji.

Kluczowe jest **gdzie** brakuje: brak jest skoncentrowany w młodzieży
i najniższych ligach, gdzie sięga 100%.

| Rozgrywki | Brak `period1` |
|---|---|
| Liga Elitelor - Seria Vest U17 | 21/21 |
| Liga 4 Teleorman / Ilfov / Alba U19 | 100% |
| Campionatul Național U19 (Seria 3, 9) | 100% |
| Liga de Tineret - Seria Vest | 76/80 |
| Nelonen (fińska 4. liga) | ~95% |
| IV. Liga Kujawsko-pomorska | 46/60 |

To nie jest usterka danych, tylko sygnał o poziomie rozgrywek — i argument
za tym, żeby `sofa` w ogóle nie schodziła do tych lig. Wiąże się z F9: tablica
Superbetu zawiera mecze U17 i czwartych lig, dla których połówkowe rynki nie
mają pokrycia. **Do decyzji operatora**, nie do naprawy w kodzie.

**Wniosek dla RESOLVE:** na tym, co pobrał, nie widać ani jednego błędu
dopasowania. Problem tego etapu był wyłącznie operacyjny (F11), nie
semantyczny.
