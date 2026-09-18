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

## Zamknięte — drugi przebieg (F13–F32), 2026-09-18

Wszystkie dziewiętnaście wpisów naprawione, każdy osobnym commitem z numerem F
w tytule, testy w `tests/sofa/test_second_run_fixes.py`. Suite: **229 → 326**
przechodzących, `ruff` i `mypy --strict` czyste na `src/bet/sofa` i `scripts/sofa`.

| # | co zrobiono | test failuje na starym kodzie? |
|---|---|---|
| **F13** | `SOFA_RUN_ID` bity **przed** pętlą etapów, przypisaniem nie `setdefault`, opcja `--run-id`, id w `SOFA_SUMMARY` | tak — etapy widziały `""` |
| **F14** | `migrate()` w konstruktorze `SofaCache`; strażnik „każda tabela z `migrate()` istnieje" | tak — `no such table` |
| **F15** | `run_stage` łapie `Exception` → 2; zapis artefaktu RESOLVE w `finally` | tak — wyjątek wychodził z `main()`, artefakt nie powstawał |
| **F16** | `(K)/(W)/(F)/Women/Kobiety` → jedna postać `(w)`, zostaje w kluczu | tak — `'millonarios w' != 'millonarios (w)'` |
| **F17** | `sofa_listing_miss` z TTL 12 h; dla tenisa tylko `events/last` | tak — liczba żądań |
| **F18** | `flush=True` na każdym `SOFA_SUMMARY`; werdykt **każdego** etapu na `stderr` | tak — plik pusty / brak werdyktu |
| **F19** | SAMPLES czyta `04_offer.json`; docstring A4 poprawiony (wariant 2) | tak — SAMPLES pytał Superbet ponownie |
| **F20+F22** | `stage` z kontekstu wywołującego (`contextvars`), nie z metody; strażnik na literały | tak — 6 literałów |
| **F21** | `TransportError` z obu transportów, ponawiany; timeout mostu 30 s → 12 s | tak — 1 próba zamiast 2 (dowód end-to-end) |
| **F24** | 8 nagłówków diagnostycznych: userscript 2.4.0 → serwer → transport → wiersz logu | tak |
| **F25** | płeć z `competition_name`, orientacja stron, okno **per sport** (piłka 6 h, tenis 24 h) | tak — `CONFIRMED` zamiast odrzucenia |
| **F26** | bramka czasowa kuponu na zegarze Superbetu; `kickoff_disagreement_h` w artefakcie | tak |
| **F27** | kolizja cen rozstrzygana jawnie (ostrożniejsza), zapisana w `price_collisions` | tak — wynik zależał od kolejności |
| **F28** | `abs(total − base) <= hitWoodwork` zamiast równości | tak — realny payload `13531730` |
| **F29** | `_SINGLETONS` przed NFD; wzorce `goals_1h_for`/`goals_2h_for`; bramka zakresu w `determine_side` | tak — 12 z 14 |
| **F30** | podłoga Poissona wyłączona dla nie-liczników; `sets_total` z **częstości empirycznej** (decyzja operatora) | tak |
| **F31** | stała rodziny faktycznie czytana; `assert` → jawny `DroppedRow` | tak |
| **F32** | `odds_items()` — jedna funkcja dla `offer.py` i `samples.py` | tak — `TypeError` na `offer.py:25` |

Decyzje operatora, wykonane przy okazji:

| pytanie | decyzja | co wyszło |
|---|---|---|
| `sets_total` | częstość empiryczna | błąd 16 pp → **0** (estymator z definicji trafia w próbkę) |
| `cards_total`/`cards_for` | „dorobić rynek" | **rynku nie ma** — wyliczone na żywej tablicy; metryki usunięte, 30 → 28 zadeklarowanych |
| F12 (niskie ligi) | lista wykluczeń w BOARD | mechanizm jest, **lista pusta** — pomiar nie uzasadnia ani jednego wykluczenia |
| `AET`/`AP` | odzyskać gole z `normaltime` | 775 z 824 meczów odzyskanych, metryki zliczające nadal odrzucane |
| `has_xg`/`best_of` | usunąć / przezwać | `has_xg` usunięte, `best_of` → `default_period_count` |

### Pomiary przed/po (Część 2 promptu)

| co | było | jest |
|---|---|---|
| metryk powstających z zadeklarowanych | 15 z 30 | **25 z 28** |
| meczów blokowanych przez tożsamość strzałów | 21,2% (1 797 meczów) | **2,0%** |
| obciążenie odrzuconych: strzały / narożne | 25 vs 24 · 10 vs 9 | 22,5 vs 24 · **9 vs 9** |
| `p_central` OVER 2,5 setów (prawda 0,3251) | 0,4597 | **0,3251** |
| rozjazd płci przechodzący jako `CONFIRMED` | 1 | **0** |
| odwrócenia stron przechodzące | 1 | **0** |
| `events/next` dla tenisa | 179, same 404 | **0** |
| przeciek z przyszłości / duplikaty / self-reference | 0 | **0** (870 próbek, mediana 10) |
| arytmetyka `engine.py` | dokładna | dokładna (`required_odds × p` z błędem 3e-05) |

Trzy metryki, których nadal nie da się wyprodukować — **i nie są usterką**:
`xg_total`, `xg_for` (Superbet nie wycenia xG) oraz `tiebreaks_total`
(Superbet nie wystawia takiego rynku).

**Korekty własnych liczb**, zostawione świadomie: skala F28 (patrz wpis),
oraz pierwotne twierdzenie tego dokumentu, że tablica schodzi do lig bez
danych — na samej tablicy 256 z 290 fixture'ów piłkarskich jest w
rozgrywkach z ≥90% pokryciem połówek, a **żaden** nie ma 0%. Rozgrywki z
zerowym pokryciem, które wpis wymienia, pojawiają się w **próbkach
historycznych przeciwników**, nie na tablicy.

---

## Otwarte

### F33 · P2 · `/event/{id}` nie jest cache'owany wcale — ~45% żądań RESOLVE przy trzecim przebiegu

**POTWIERDZONE** pomiarem na żywym przebiegu (2026-09-18, `run_id=df72150396e6`),
zgłoszone przez operatora pytaniem „przecież już to mamy".

`parse_fixture` woła `client.event(event["id"])` dla **każdego przyjętego
fixture'u**, żeby dobrać to, czego nie ma w listingu — sędziego, `round_number`,
`ground_type`, `defaultPeriodCount`. Ta trasa nie ma cache'u w żadnej postaci:
ani tabeli, ani TTL, ani negatywów.

Zmierzone po 615 żądaniach tego przebiegu:

| trasa | żądań | udział |
|---|---|---|
| **`event/{id}`** | **282** | **45,9%** |
| `search/all` | 153 | 24,9% |
| `team/{id}/events/last` | 151 | 24,6% |
| `team/{id}/events/next` | 28 | 4,6% |

Dla porównania, co cache **oszczędza** w tym samym przebiegu: 6 731
zbuforowanych statystyk meczowych (nie pobierane w ogóle), 4 351 listingów
w TTL, 491 encji bez `search/all`. Czyli wszystko inne jest już oszczędzane —
`event/{id}` jest **jedyną** trasą płaconą w całości przy każdym przebiegu.

**Dlaczego to nie jest trywialne do naprawienia i dlaczego nie robię tego dziś:**
payload `/event/{id}` meczu **jeszcze nierozegranego** legalnie się zmienia —
sędzia jest ogłaszany późno (F-pomiar: `referee` wypełnione w 9% fixture'ów,
co jest właśnie objawem późnego ogłoszenia). Wieczny cache zamroziłby pustego
sędziego. To jest dokładnie ta pułapka, którą F17 opisał dla `events/next`:
**zamiana marnotrawstwa na cichą lukę jest gorszym błędem.**

Właściwy kształt to najpewniej krótki TTL, zależny od tego, czy mecz się już
odbył: dla `status.type == "finished"` payload jest niezmienny i może być
wieczny (tak jak `sofa_event_stats`), dla nierozpoczętego — TTL rzędu
kilkudziesięciu minut. Tego **nie zmierzyłem**: nie wiem, jak często
`referee`/`round_name` faktycznie zmieniają się między przebiegami tego samego
dnia, więc dobór TTL oznaczam `PODEJRZENIE` i zostawiam do decyzji.

**Oszczędność, gdyby to zrobić:** przy dzisiejszym slate'cie rzędu 500 żądań
na przebieg, czyli ~4 minuty przy 2 req/s — porównywalnie z F17 (242) i F19
(~600) razem wziętymi.

**Test (kiedy będzie naprawiane):** dwa wywołania `parse_fixture` dla tego
samego zakończonego meczu → drugie zero żądań; dla meczu nierozpoczętego po
przesunięciu zegara za TTL → jedno żądanie.

---


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

---

## F13 · P2 · `SOFA_RUN_ID` jest ustawiany po zakończeniu wszystkich etapów — F8 jest bezczynne w przebiegu przez `run_pipeline.py`

**POTWIERDZONE** (czytaniem kodu, przed drugim przebiegiem 2026-09-18).

`scripts/sofa/run_pipeline.py` ustawia identyfikator przebiegu **za** pętlą,
która uruchamia etapy:

```python
for stage, label in sequence:      # ← wszystkie etapy logują tutaj
    code = run_stage(stage, args.date)
...
os.environ.setdefault("SOFA_RUN_ID", uuid.uuid4().hex[:12])   # ← dopiero tu
```

`SofaConfig.from_env()` czyta `run_id=os.environ.get("SOFA_RUN_ID", "")`
(`config.py:54`), a `SofascoreClient` przepisuje to do każdego wiersza
`runs/run.log.jsonl` (`client.py:203`). Skoro zmienna powstaje po ostatnim
etapie, **każdy wiersz logu z przebiegu uruchomionego przez `run_pipeline.py`
niesie `run_id: ""`** — a wylosowany identyfikator trafia wyłącznie do
`SOFA_SUMMARY`, gdzie nie ma z czym go skorelować.

Skutek jest dokładnie ten, który F8 miało usunąć: filtrowanie logu po
przebiegu wraca do zgadywania po `ts_utc`. Etapy uruchamiane pojedynczo
(`python -m scripts.sofa.run_resolve`) też mają `""`, o ile operator sam nie
wyeksportuje zmiennej.

**Dodatkowo, drugi defekt w tej samej linii:** `setdefault` jest tu złym
wywołaniem nawet po przeniesieniu na początek — jeśli `SOFA_RUN_ID` zostało
odziedziczone ze środowiska poprzedniego przebiegu (np. wyeksportowane
w powłoce), dwa przebiegi dostaną **ten sam** identyfikator i zleją się
w logu. To jest ta sama klasa błędu co F8, tylko odwrócona.

**Proponowana poprawka:** przenieść ustawienie `SOFA_RUN_ID` przed pętlę
i pozwolić na jawne nadpisanie (`--run-id`), a domyślnie bić **nowy**
identyfikator zamiast dziedziczyć:

```python
os.environ["SOFA_RUN_ID"] = args.run_id or uuid.uuid4().hex[:12]
for stage, label in sequence:
    ...
```

i wpisać ten sam identyfikator do `SOFA_SUMMARY`.

**Test:** wywołać `main()` z podstawionymi etapami, które zapisują
`SofaConfig.from_env().run_id` w momencie swojego wykonania, i sprawdzić, że
(a) wszystkie widzą niepusty identyfikator, (b) identyczny, (c) różny od
identyfikatora poprzedniego wywołania. Taki test **failuje na dzisiejszym
kodzie z właściwego powodu** — dziś etapy widzą `""` — więc jest dowodem
usterki, nie tylko strażnikiem zachowania.

**Obejście użyte w tym przebiegu:** `SOFA_RUN_ID` wyeksportowany ręcznie
przy starcie, żeby monitoring miał po czym filtrować. Nie naprawiam kodu
w trakcie przebiegu.

---

## F14 · P0 · Schemat bazy nie jest nigdzie zakładany — `migrate()` wywołują wyłącznie testy

**POTWIERDZONE** dwukrotnie: awarią drugiego przebiegu na żywo (2026-09-18)
i eksperymentem na czystej bazie.

Drugi przebieg padł na **pierwszym fixture'cie** RESOLVE:

```
File "src/bet/sofa/resolve.py", line 95, in resolve_entity
  if self.cache.get_entity_miss(sport, norm_side):
File "src/bet/sofa/cache.py", line 202, in get_entity_miss
sqlite3.OperationalError: no such table: sofa_entity_miss
```

`sofa_entity_miss` to tabela dodana przez **F4**. `bet.sofa.db.migrate()`
zakłada ją poprawnie i jest idempotentna (`CREATE TABLE IF NOT EXISTS`).
Problem jest inny i szerszy:

```
$ grep -rn "migrate" src scripts | grep -v src/bet/sofa/db.py
(nic)
```

**Nikt nie wywołuje `migrate()` w kodzie produkcyjnym.** Jedynymi
wywołującymi są testy (`tests/sofa/test_db.py` i 9 innych plików).
`git log -S"db.migrate" -- src scripts` nie zwraca ani jednego commita —
ten wywołanie nigdy nie istniało, nie zostało usunięte.

Żywa baza ma `sofa_entity` i `sofa_entity_events` tylko dlatego, że
`migrate()` puszczono kiedyś ręcznie. Skutek: **każda tabela dodana do
`migrate()` po tym momencie nigdy nie dociera do żywej bazy.** F4 wygląda na
zamknięte (ma 5 przechodzących testów — bo testy same wołają `migrate()`),
a na żywo wywraca cały etap.

Drugi, gorszy wariant tej samej usterki: **na czystej maszynie pipeline nie
wystartuje wcale.** Zmierzone na pustym pliku bazy:

```
SOFA_DB_PATH=…/fresh.db → SofaCache.get_entity('football','anything')
FRESH DB FAILS: OperationalError no such table: sofa_entity
```

Czyli `sofa` nie da się dziś uruchomić od zera bez ręcznego kroku, którego
nie ma w żadnej instrukcji ani w `run_pipeline.py`.

**Proponowana poprawka:** `migrate(config.db_path)` w konstruktorze
`SofaCache` (tam, gdzie po pierwszym razie jest niemal darmowa i nie da się
jej pominąć), albo — jeśli koszt na każde utworzenie cache'u przeszkadza —
raz na początku `run_pipeline.main()` **i** w każdym `run_*.py`, bo etapy są
uruchamiane pojedynczo. Konstruktor jest bezpieczniejszy: nie ma drogi
wejścia, która go omija.

**Test:** zbudować `SofaCache` na ścieżce do nieistniejącego pliku i wykonać
odczyt oraz zapis każdej z pięciu tabel. **Failuje na dzisiejszym kodzie
z właściwego powodu** (`no such table`), więc jest dowodem usterki. Dodatkowo
test-strażnik: dla każdej tabeli wymienionej w `migrate()` sprawdzić, że
istnieje po zbudowaniu cache'u — to wyłapie następną tabelę dodaną bez
migracji.

**Obejście użyte w tym przebiegu:** ręczne `migrate('data/sofa.db')`.
Idempotentne. Zmierzone: przed migracją baza miała `sofa_entity`,
`sofa_entity_events`, `sofa_event_stats`, `sofa_settled_row` — brakowało
**dokładnie jednej** tabeli, `sofa_entity_miss`, czyli tej dodanej przez F4.
Po migracji pięć tabel, liczniki bez zmian (271 / 1 748 / 0 / 0 / 0).

---

## F15 · P1 · Ani F11, ani `run_pipeline` nie powstrzymały wyjątku etapu — jeden błąd zabił całą sekwencję

**POTWIERDZONE** tą samą awarią (2026-09-18).

Wyjątek z F14 nie został złapany **na żadnym z trzech poziomów**, na których
istniała obrona:

1. **F11 w `run_resolve.py`** łapie `ProviderError` per fixture i
   `CircuitOpenError` dla pętli. `sqlite3.OperationalError` nie jest ani
   jednym, ani drugim — poleciał przez pętlę na wylot. F11 chroni przed
   awarią *providera*, a nie przed awarią etapu; awaria, którą dziś
   zobaczyliśmy, była lokalna.
2. **F5** („artefakt powstaje także po przerwaniu") nie zadziałało z tego
   samego powodu: `runs/sofa/2026-09-18/02_resolve.json` **nie powstał**.
   Zapis artefaktu jest za pętlą, nie w `finally`.
3. **`run_pipeline.main()`** nie ma `try`/`except` wokół `run_stage`:

   ```python
   for stage, label in sequence:
       code = run_stage(stage, args.date)     # wyjątek leci na wylot
   ```

   Efekt: padł nie tylko RESOLVE, ale **cały pipeline** — pięć dalszych
   etapów nie dostało szansy, a `--stop-on-failure` nie było podane, więc
   pipeline miał jawnie polecenie iść dalej i nie posłuchał.

To wprost przeczy docstringowi modułu:

> „Stage entry points are imported lazily inside run_stage **so that a broken
> stage module fails that stage, not the whole run**."

Leniwy import broni tylko przed `ImportError`. Przed błędem *wykonania*
etapu nie broni nic, a to on jest prawdopodobny.

Warto zauważyć, że w tym konkretnym przypadku dalsze etapy i tak nie
zbudowałyby sensownego kuponu (bez RESOLVE nie ma encji) — ale werdykt
`FAILED` dla RESOLVE i przejście dalej dałoby artefakty i podsumowanie
zamiast nagiego traceback z kodem wyjścia 1.

**Proponowana poprawka:** dwie, niezależne.
- W `run_pipeline.run_stage`: złapać `Exception`, zalogować z `run_id`
  i zwrócić 2 (`FAILED`). `SystemExit` jak dziś.
- W `run_resolve.py` (i każdym `run_*.py`): przenieść zapis artefaktu do
  `finally`, żeby F5 obowiązywało dla dowolnego wyjątku, nie tylko dla
  `CircuitOpenError`.

**Test:** podstawić etap, który rzuca `RuntimeError`, i sprawdzić, że
`main()` zwraca 1/2 oraz że **pozostałe etapy zostały wywołane**.
**Failuje na dzisiejszym kodzie z właściwego powodu** (dziś wyjątek wychodzi
z `main()`), więc jest dowodem. Analogicznie dla artefaktu RESOLVE: rzucić
z providera wyjątek inny niż `ProviderError` i sprawdzić, że
`02_resolve.json` istnieje.

---

## F16 · P1 · Piłka kobiet **jest** w slate'cie — i `normalize_name` czyni ją niedopasowywalną. Koryguje F9

**POTWIERDZONE** co do mechanizmu i co do 6 z 6 sprawdzonych nazw; liczba
końcowa `PODEJRZENIE` do zakończenia RESOLVE (48 nazw jeszcze nie
próbowanych w momencie pisania).

### Najpierw korekta F9

F9 ustalił, że `sofa` „pomija [piłkę kobiet] w całości", bo `SPORT_IDS`
w `superbet.py` zna tylko `5` i `2`, a kobiety to `sportId=190`.
**To jest nieprawda dla tablicy, którą pipeline faktycznie czyta.**

Zmierzone na `01_board.json` z 2026-09-18 (623 fixture'y):

| | |
|---|---|
| fixture'y z markerem `(K)` po którejkolwiek stronie | **27 z 623** |
| z tego: marker po **obu** stronach | **27** (100%) |
| po jednej stronie (czyli mecz mieszany — byłby błędem) | **0** |
| sport w artefakcie | `football` we wszystkich 27 |

Czyli Superbet podaje część meczów kobiecych **w kategorii piłki męskiej**,
oznaczając je polskim `(K)`, i te mecze przechodzą przez BOARD normalnie.
Wniosek F9 — „decyzja: czy dodać `sportId=190`" — trzeba przeformułować:
nie chodzi o **włączenie** piłki kobiet, bo już jest, tylko o **dodanie jej
reszty**. A zanim cokolwiek dodamy, trzeba naprawić to poniżej, bo dziś
większy wolumen oznaczałby tylko więcej nietrafień.

### Usterka

`normalize_name` tłumaczy polski marker `(K)` na `w`, ale **gubi przy tym
nawiasy**, których nie gubi przy angielskim `(W)`:

```
'Millonarios (K)'      -> 'millonarios w'
'LD Alajuelense (K)'   -> 'ld alajuelense w'
'Azzurri United FC (K)'-> 'azzurri united fc w'
'Moravia (K)'          -> 'moravia w'
'Arsenal (W)'          -> 'arsenal (w)'      ← nawiasy zostają
```

Nazwy własne Sofascore niosą `(W)` (F9 zmierzył: 100% nazw w `sportId=190`).
Ich znormalizowana postać to więc `arsenal (w)`, a znormalizowany klucz
z Superbetu to `arsenal w`. **Te dwa napisy nigdy nie będą równe.**
Wszystkie 54 nazwy stron z markerem `(K)` na dzisiejszej tablicy normalizują
się do sufiksu ` w` (sprawdzone: 54/54).

Skutek — **liczby końcowe, po zakończeniu RESOLVE** (zastępują wcześniejsze
6/6, które opisywało dopiero rozgrzany etap):

| | |
|---|---|
| nazwy stron `(K)` na tablicy | 54 |
| z tego w `sofa_entity_miss` | **47 (87%)** |
| z tego rozwiązane do `sofa_entity` | **7 (13%)** |
| fixture'y kobiece dowiezione do `02_fixtures.json` | **4 z 27 (15%)** |

**Korekta własnej tezy:** napisałem wyżej „te dwa napisy nigdy nie będą
równe", i to jest prawda o **porównaniu kluczy** — ale nie o całym
rozwiązywaniu. 7 nazw jednak przeszło, bo `resolve_entity` po nietrafieniu
w cache pyta `search/all`, a wyszukiwarka Sofascore jest rozmyta i na zapytanie
`millonarios w` potrafi zwrócić właściwą drużynę kobiet. Czyli zepsuta
normalizacja nie zamyka drogi całkowicie — **obniża skuteczność z ~78%
(średnia slate'u) do 13%**. To słabsza teza niż moja pierwotna i jest
zmierzona, a nie wyprowadzona.

### Czego to **nie** robi — i to jest dobra wiadomość

F9 obawiał się, że `normalize_name` „zje sufiks i pomyli drużynę kobiet
z męską". **Tego nie widać.** Nie ma ani jednego błędnego dopasowania:
wszystkie 6 to nietrafienia. Broni tego bramka opisana w audycie
semantycznym — RESOLVE przyjmuje encję dopiero po znalezieniu meczu zgodnego
co do kickoffu **i** przeciwnika, a męski odpowiednik nie zagra o tej samej
godzinie z tą samą drużyną. Czyli tracimy fixture, nie psujemy próbki.
Ryzyko podmiany pozostaje jednak **teoretycznie otwarte** dla przypadku,
w którym oba warunki przypadkiem zagrają; nie zmierzyłem, jak blisko temu
było, i nie twierdzę, że nie może się zdarzyć.

### Proponowana poprawka

Doprowadzić oba markery do **jednej** postaci i zrobić z tego cechę encji,
a nie część napisu. Marker płci jest informacją strukturalną: dwie różne
drużyny o tej samej nazwie. Najtaniej: normalizować `(K)`, `(W)`, `(F)`,
`Women`, `Kobiety` do wspólnego sufiksu `(w)` — wtedy `millonarios (w)`
spotyka się z `millonarios (w)`. Lepiej: wyciąć marker z nazwy i przenieść
do osobnej kolumny `gender` w `sofa_entity`, wchodzącej do klucza — wtedy
drużyna kobiet i mężczyzn nie mogą się pomylić nawet przy zgodnym kickoffie,
i domyka się otwarte ryzyko z akapitu powyżej.

**Test:** sparametryzowany po `('Millonarios (K)', 'Millonarios (W)')`
i pozostałych wariantach — obie strony muszą dać **identyczny** klucz,
a klucz drużyny kobiet musi być **różny** od klucza drużyny mężczyzn
(`Millonarios`). **Failuje na dzisiejszym kodzie z właściwego powodu**:
pierwszy asercja pada na `'millonarios w' != 'millonarios (w)'`. Do tego
test na `sofa_entity_miss`: po RESOLVE na slate'cie z jednym meczem `(K)`
liczba nietrafień dla tych nazw musi być 0 — ten failuje dziś na 2.

---

## F17 · P2 · 404 na listingu nie jest zapamiętywany — 28% budżetu RESOLVE idzie na ponowne odkrywanie tego samego braku

**POTWIERDZONE** pomiarem na `runs/sofa/run.log.jsonl`, dwa przebiegi
(2026-09-18). To dokładnie ta sama klasa marnotrawstwa, którą **F4** usunął
dla *nazw* — i której nikt nie usunął dla *listingów*.

### Skąd te 404 się biorą — zmierzone po sporcie

**Uwaga: pierwsza wersja tego wpisu wyjaśniała 404 „rozrzutem na trzech
kandydatów z `search` plus 25% tablicy już rozpoczętej". Arytmetyka się
zgadzała, ale wyważenie było błędne.** Pomiar po sporcie pokazuje coś innego
i zostawiam tu ślad tej pomyłki, bo to jest dokładnie ten przypadek, w którym
zgodna suma podpiera zły wniosek.

`events/next` w tym przebiegu, po sporcie encji:

| sport encji | 200 | 404 | odsetek 404 |
|---|---|---|---|
| **tenis** | **0** | **179** | **100%** |
| piłka | 48 | 5 | 9% |
| nieznane id (kandydat z `search`, nigdy nie przyjęty) | 62 | 108 | 64% |

Czyli trzy różne źródła, o zupełnie różnej naturze:

1. **Tenis — 179 z 179, sto procent.** Sofascore nie obsługuje
   `team/{id}/events/next/` dla encji tenisowych. Ani jeden raz. To nie jest
   „brak nadchodzących meczów" — to trasa, która dla tenisa nie istnieje.
   Każda encja tenisowa kosztuje jedno żądanie gwarantowanie nieudane.
   *Dlaczego* tak jest, oznaczam `PODEJRZENIE` (drabinki turniejowe nie są
   ustalone do końca poprzedniej rundy, więc Sofascore mógł tej trasy po
   prostu nie zaimplementować); **fakt** 179/179 jest `POTWIERDZONY`.
2. **Kandydaci-śmiecie z `search` — 64%.** To jest koszt z założenia:
   `resolve_entity` bierze do trzech kandydatów (zmierzone: średnio 1,55 na
   zapytanie), a najwyżej jeden jest właściwy. Tego się nie da usunąć bez
   pogorszenia trafności.
3. **Piłka, realne drużyny — 9%.** Marginalne. To jest ten przypadek, który
   błędnie uznałem za główny: mecz już się rozpoczął i wypadł z „next".

**Danych to nie traci.** Encje tenisowe rozwiązują się normalnie, bo
`events/last` dla tenisa zawiera też mecze nierozpoczęte — zmierzone na
cache'u: 13 234 zdarzeń w listingach `last` encji tenisowych, z tego
**179 `notstarted`** i 156 z przyszłym `startTimestamp`. Fallback w
`_fetch_events` robi więc swoje. To jest czyste marnotrawstwo, nie luka.

Breaker poprawnie nie liczy 404 jako awarii — `breaker={'CLOSED': 1349}` przy
296 czterystaczwórkach. Pod tym względem wszystko działa.

### Usterka

`Resolver._fetch_events` zapisuje do cache'u **tylko odpowiedź niepustą**:

```python
data = self.cache.get_entity_events(entity_id, kind, page)
if not data:
    data = self.client.entity_events(entity_id, kind, page)
    if data:                                   # ← 404 tu nie wchodzi
        self.cache.save_entity_events(entity_id, kind, page, data)
```

Brak listingu nie jest więc nigdzie zapisywany i jest odkrywany od nowa
za każdym razem. Zmierzone:

| | |
|---|---|
| `events/next` 404 w tym przebiegu | **267** żądań, 250 różnych URL-i |
| z tego URL-e, o których **pierwszy przebieg już wiedział**, że dają 404 | **225** |
| powtórzenia tego samego URL-a **w obrębie** tego przebiegu | **17** |
| razem zmarnowane | **242** z ~870 żądań RESOLVE = **28%** |

Docstring F4 w `resolve.py` opisuje ten sam rachunek dla nazw: „~20% of the
request budget spent re-learning the same negative fact". Dla listingów jest
to 28% i nikt tego nie policzył, bo 404 nie wygląda w logu na koszt.

### Proponowana poprawka — z zastrzeżeniem, które jest istotne

Cache'ować **negatywną** odpowiedź, ale **z krótkim TTL**, nie na zawsze.
`events/next` zmienia się z natury: drużyna bez nadchodzącego meczu dziś
będzie go mieć w przyszłym tygodniu. Zapamiętanie 404 bezterminowo zamieniłoby
marnotrawstwo na cichą lukę w danych, czyli gorszy błąd.

Właściwy zakres to **jeden dzień** (albo `min(TTL_listingu, do najbliższej
północy)`): w obrębie przebiegu i między przebiegami tego samego dnia
odpowiedź jest stabilna, a nazajutrz pytamy znowu. Tabela `sofa_entity_miss`
z F4 ma już wzorzec, na którym to się opiera — osobna tabela na negatywy
z własnym TTL.

**Test:** dwa wywołania `_fetch_events` dla id, którego transport zwraca 404 —
drugie musi wykonać **zero** żądań; i trzecie po przesunięciu wstrzykniętego
zegara za TTL — musi wykonać **jedno**. Pierwsza asercja **failuje na
dzisiejszym kodzie z właściwego powodu** (liczy 2 żądania zamiast 1), więc
jest dowodem usterki; druga jest strażnikiem poprawności TTL, żeby poprawka
nie zamieniła kosztu na lukę.

**Poprawka wynikająca z pomiaru po sporcie (ważniejsza niż cache negatywów):**
dla tenisa `events/next` nie powinno być w ogóle wywoływane. `_fetch_events`
iteruje po `("next","last")` bez względu na sport; wystarczy, żeby kolejność
i zbiór tras zależały od sportu — dla tenisa samo `("last",)`. To usuwa
**179 żądań z tego przebiegu** (≈1,5 minuty przy 2 req/s) i nie traci ani
jednego zdarzenia, bo `last` dla tenisa niesie także mecze `notstarted`.
Dla piłki `next` zostaje, bo tam działa (48 z 53 na 200).

**Test:** `_fetch_events` dla encji tenisowej nie może wykonać **żadnego**
żądania na `/events/next/`; dla piłkarskiej musi. **Failuje na dzisiejszym
kodzie z właściwego powodu** — dziś tenis wykonuje to żądanie i dostaje 404.

---

## F18 · P1 · OFFER zwrócił `FAILED` bez ani jednego słowa diagnostyki — `SOFA_SUMMARY` jest buforowane i niewidoczne w trakcie przebiegu

**POTWIERDZONE** (2026-09-18, drugi przebieg).

Cała treść `/tmp/sofa_run.log` po 33 minutach przebiegu, w którym RESOLVE
wykonał 3 377 żądań i OFFER się wywrócił:

```
--- RESOLVE ---
--- OFFER (pre-sample: which markets have a price at all) ---
OFFER (pre-sample: which markets have a price at all): FAILED (exit 2)
--- SAMPLES ---
```

Cztery linie. **Ani werdyktu RESOLVE, ani powodu awarii OFFER.**

Mechanizm: znaczniki etapów i komunikat o `FAILED` idą na `stderr`
(niebuforowany), a `SOFA_SUMMARY` — łącznie z polem `metrics.error`, które
`run_offer.py` wypełnia treścią wyjątku — idzie na `stdout`. Pod
przekierowaniem `nohup … > plik` Python buforuje `stdout` blokowo, więc
podsumowania wszystkich etapów siedzą w buforze do zakończenia procesu.
Werdykt etapu jest z definicji informacją, którą trzeba zobaczyć **w
trakcie**, a nie po.

To wyjaśnia też, dlaczego w pierwszym (wywróconym) przebiegu było widać
`SOFA_SUMMARY` z BOARD: proces zginął, bufor się przy tym opróżnił.

Co udało się ustalić o samej awarii OFFER **bez** tego komunikatu:
- Superbet odpowiedział **200 na 95 z 95** wywołań, więc to nie była awaria
  sieci ani HTTP.
- `04_offer.json` **nie powstał**, a `run_offer.py` zapisuje go po
  `fetch_offers`. Czyli sterowanie poszło **ścieżką wyjątku**, nie ścieżką
  „wszystkie oferty puste" (ta też daje `FAILED`, ale po zapisie pliku).
- Zatem: wyjątek wewnątrz `fetcher.fetch_offers(fixtures)`, najpewniej przy
  walidacji/parsowaniu, nie przy pobieraniu. Dokładna treść jest w buforze
  i odczytam ją, gdy proces się zakończy. Do tego czasu przyczyna to
  `PODEJRZENIE`.

**Proponowana poprawka:** `flush=True` przy każdym `print(SOFA_SUMMARY…)`
(albo `PYTHONUNBUFFERED=1` w instrukcji uruchomienia — ale to zaklęcie, które
łatwo pominąć, więc lepiej w kodzie). Dodatkowo `run_pipeline` powinien
wypisywać werdykt każdego etapu na `stderr`, razem ze znacznikiem — dziś
wypisuje tylko przy `FAILED`, i to bez powodu.

**Test:** uruchomić etap jako podproces z przekierowanym `stdout`, przerwać
go po pierwszym podsumowaniu i sprawdzić, że podsumowanie jest już w pliku.
**Failuje na dzisiejszym kodzie z właściwego powodu** — dziś plik jest pusty.

---

## F19 · P2 · Przedsamplowy OFFER nie jest przez nikogo czytany — uzasadnienie A4 nie odpowiada kodowi

**POTWIERDZONE** czytaniem kodu (2026-09-18). Wyszło przy diagnozie F18.

`run_pipeline.py` uruchamia OFFER dwa razy i tłumaczy to wprost:

> „The offer is read **twice on purpose** (A4): once before sampling, **so we
> only pay for metrics somebody actually prices**, and once immediately before
> the coupon so the price the bar is compared against is fresh."

Pierwsza połowa tego zdania nie opisuje kodu. Oszczędność **jest**
realizowana, ale zupełnie inaczej: `run_samples.py` konstruuje własnego
`SuperbetClient` (linia 38) i przekazuje go w dół, a `samples.py` pyta
Superbet **sam, na żywo, per fixture**:

```python
metrics_to_collect = fetch_available_metrics(fixture, superbet_client)   # samples.py:326
```

`run_samples.py` nie zawiera ani jednego odwołania do `04_offer.json`
(sprawdzone `grep`em: zero trafień na `offer` poza własnym `03_samples.json`).
Artefakt oferty czyta dopiero SHEET (`run_sheet.py:475`).

Skutek: **pierwsze wywołanie OFFER nie ma żadnego odbiorcy.** Zapisuje
`04_offer.json`, którego nic nie czyta, zanim drugie wywołanie go nadpisze.
Jego jedyne efekty to koszt w żądaniach do Superbetu i możliwość wywrócenia
przebiegu werdyktem `FAILED` — czyli dokładnie to, co dziś się stało.

**Dobra wiadomość dla tego przebiegu:** awaria przedsamplowego OFFER jest
**nieszkodliwa**. SAMPLES od niego nie zależy i normalnie pracuje. Ryzyko
dotyczy wyłącznie **drugiego** wywołania OFFER, bo SHEET bez `04_offer.json`
nie zbuduje kuponu.

**Proponowana poprawka — do decyzji operatora, bo są dwa sensowne kierunki:**
1. Usunąć przedsamplowy OFFER z sekwencji i poprawić docstring. Najprostsze,
   oszczędza żądania. Traci jednak wczesne ostrzeżenie „Superbet dziś nie
   odpowiada / zmienił format", które dostajemy przed 30 minutami SAMPLES.
2. Zostawić go **jako bramkę**, ale jawnie: niech SAMPLES czyta
   `04_offer.json` zamiast pytać Superbet po raz drugi. Wtedy zdanie z A4
   staje się prawdziwe, a liczba wywołań do Superbetu spada o połowę.

Zanim to rozstrzygniemy, warto zmierzyć, ile wywołań do Superbetu robi
SAMPLES — jeśli to jedno na fixture, wariant 2 oszczędza ~600 żądań dziennie.

**Test:** dla wariantu 2 — SAMPLES na slate'cie z gotowym `04_offer.json`
nie może wykonać **żadnego** żądania do Superbetu. Failuje dziś z właściwego
powodu (dziś wykonuje jedno na `superbet_event_id`).

---

## F20 · P3 · Każde żądanie do Superbetu jest w logu opisane jako `stage: "BOARD"`

**POTWIERDZONE** (2026-09-18). Wszystkie 95 wierszy Superbetu z tego
przebiegu — w tym te wykonane przez OFFER i przez SAMPLES — mają
`stage: "BOARD"`:

```
{('BOARD', 200): 95}
```

Rozróżnić je dało się wyłącznie po `ts_utc` i po 30-minutowej dziurze na
RESOLVE. To psuje dokładnie tę zdolność, którą F8 miało dać: przypisanie
kosztu do etapu. Przy diagnozie F18 musiałem odtwarzać granicę etapów
z odstępów między znacznikami czasu — czyli robić to, co F8 miało zlikwidować.

`SofascoreClient._log` przyjmuje `stage` jako argument wywołania;
`SuperbetClient` najwyraźniej ma go przyszytego na sztywno.

**Proponowana poprawka:** przekazywać `stage` do `SuperbetClient` tak samo jak
do `SofascoreClient`.

**Test:** wywołać `SuperbetClient` z etapu `OFFER` i sprawdzić, że wiersz
logu niesie `stage: "OFFER"`. Failuje dziś z właściwego powodu.

---

## F21 · P1 · Ponowienie w `_execute` jest martwym kodem pod mostem — a most jest jedynym transportem

**POTWIERDZONE** (2026-09-18) pomiarem czasu jednej rzeczywistej awarii.

O 09:54:51 jedno żądanie SAMPLES przepadło:

```json
{"stage":"SAMPLES","url":".../event/16779467/statistics",
 "status":null,"elapsed_ms":30003,"breaker_state":"CLOSED"}
```

`client._execute` ma dla awarii sieciowej ścieżkę z **jednym ponowieniem**:

```python
try:
    resp = self.transport.get(url, timeout=timeout)
except RequestsError:                      # ← curl_cffi
    time.sleep(1.0); ...  retry once  ...
except Exception as e:                     # ← wszystko inne: bez ponowienia
    self.breaker.record_failure(); ...; raise ProviderError(...)
```

`RequestsError` jest importowany z `curl_cffi`. Ale `make_transport()`
zwraca domyślnie **`BrowserBridgeTransport`** (`SOFA_TRANSPORT` domyślnie
`"bridge"`, i słusznie — direct to gwarantowane 403), a ten transport na
każdą awarię rzuca **`ProviderError`**, nigdy `RequestsError`
(`bridge_transport.py:72,74,80,84`). `ProviderError` nie jest podklasą
`RequestsError`, więc trafia do `except Exception` — **gałąź z ponowieniem
jest pod mostem nieosiągalna.**

Dowód z pomiaru, nie z lektury: między poprzednim wierszem logu (09:54:21,2)
a wierszem awarii (09:54:51,5) minęło **30,3 s**. Gdyby ponowienie zadziałało,
byłoby to ~61 s (30 s + 1 s `sleep` + 30 s). Jedna próba, jeden wpis, zero
ponowień.

Znaczenie: most jest jedynym działającym transportem od 2026-09-17, więc
**mechanizm, który miał wchłaniać przelotne zadławienia mostu, jest bezczynny
od tego dnia.** To też domyka wyjaśnienie śmierci pierwszego przebiegu: jeden
`bridge HTTP 504` nie został ponowiony, bo nie mógł być.

Efekt uboczny, kosmetyczny, ale potwierdzający ścieżkę: komunikat wychodzi
podwójnie owinięty — `ProviderError("Unexpected error: bridge …")`.

**Proponowana poprawka:** łapać na tej gałęzi `(RequestsError, ProviderError)`
— albo, czyściej, wprowadzić `TransportError` rzucany przez oba transporty
i ponawiać po nim, zostawiając `ProviderError` na błędy semantyczne. Przy
okazji przemyśleć, czy 30 s to właściwy limit dla `event/{id}/statistics`:
mediana tego wywołania w tym przebiegu to ~150 ms, więc 30 s czeka 200 razy
dłużej niż typowa odpowiedź.

**Test:** transport podstawiony tak, by pierwsze wywołanie rzuciło
`ProviderError`, a drugie zwróciło 200 — `_execute` musi zwrócić dane
i wykonać **dwa** wywołania. **Failuje na dzisiejszym kodzie z właściwego
powodu**: dziś wykonuje jedno i podnosi wyjątek.

---

## F11 — pierwszy prawdziwy sprawdzian: **zadziałało** (ale w `samples.py`, nie w `run_resolve.py`)

Ta sama awaria z 09:54:51 jest **pierwszym rzeczywistym testem wzorca F11**
w tym przebiegu, i wzorzec się obronił.

`ProviderError` z martwej ścieżki (F21) poleciał w górę i został złapany
**per fixture** w `samples.py:304-306`:

```python
except CircuitOpenError as exc: return _blocked(fixture, GapReason.CIRCUIT_OPEN, str(exc))
except ProviderError as exc:    return _blocked(fixture, GapReason.PROVIDER_ERROR, str(exc))
```

Zmierzone skutki:

| | |
|---|---|
| fixture'y utracone | **1** (werdykt `BLOCKED`, `gaps=[PROVIDER_ERROR]`) |
| etap przerwany? | **nie** — 184 kolejne żądania po awarii, wszystkie 200/404 |
| breaker | pozostał `CLOSED` (jedna porażka poniżej progu — poprawnie) |
| ponowienie żądania | **0** (patrz F21) |

Dwa zastrzeżenia, żeby nie odczytać tego lepiej, niż wypadło:

1. **To nie był test `run_resolve.py`.** Ochrona, która zadziałała, siedzi
   w `samples.py`. Zmierzone: `run_samples.py` nie ma ani jednego `except`
   (`grep`: zero trafień) — ratuje go moduł poniżej. Warto sprawdzić, czy
   pozostałe etapy (SHEET, COUPON, OFFER) mają cokolwiek; OFFER, jak widać
   po F18, ma — i to on właśnie zwrócił `FAILED`.
2. **Koszt to cały fixture, nie jedna metryka.** Jeden 30-sekundowy timeout
   na jednym `statistics` wyrzucił cały mecz do `BLOCKED`. Docstring
   `process_fixture_samples` mówi, że to zamierzone („A provider failure
   blocks this fixture, not the day"), i przy działającym ponowieniu z F21
   ten fixture najpewniej by się uratował.

---

## Pokrycie RESOLVE — pomiar drugiego przebiegu (2026-09-18)

Etap zakończony, **3 377 żądań**, artefakt `02_fixtures.json`.

| | |
|---|---|
| fixture'y z tablicy | 623 |
| **dowiezione do `02_fixtures.json`** | **484 (77,7%)** |
| piłka | 290 z 393 (73,8%) |
| tenis | 194 z 230 (84,3%) |
| tożsamość `CONFIRMED` | 369 (76,2%) |
| tożsamość `FUZZY` | 115 (23,8%) |

Dla porównania: pierwszy przebieg umarł po 420 z 613, nie kończąc etapu.

### Wypełnienie pól — i jedna rzecz, która wygląda na lukę

| pole | wypełnione |
|---|---|
| `competition_name` / `competition_id` / `season_id` / `category_name` | 484/484 (100%) |
| `round_number` | 448/484 (93%) |
| `best_of` (tenis) | 194/194 (100%) — wszystkie `3`, czyli dziś zero BO5 |
| `ground_type` (tenis) | 170/194 (88%) |
| `venue_name` | 175/484 (36%) |
| `round_name` | 134/484 (28%) |
| `cup_round_type` | 128/484 (26%) |
| `referee` | 42/484 (9%) |
| `previous_leg_event_id` | 4/484 (1%) |

Niskie `referee` i `previous_leg_event_id` są spodziewane — sędzia jest
ogłaszany późno, a drugich meczów po prostu dziś prawie nie ma. `ground_type`
brakujące w 24 z 194 meczów tenisowych to znany kształt problemu
(Challengery bez pinu nawierzchni).

**Co wymaga uwagi: `has_xg` jest `True` dla 4 z 290 meczów piłkarskich —
1,4%.** Czyli xG na dzisiejszym slate'cie praktycznie nie istnieje.

**ROZSTRZYGNIĘTE — `POTWIERDZONE`, i nie jest to usterka zachowania.**
`has_xg` w `Fixture` opisuje **mecz rozegrany**, nie zdolność ligi. Dowody:

- Ligi, w których xG na pewno jest, mają `False`: `2. Bundesliga`
  (Wolfsburg–Darmstadt), `Eredivisie` (Groningen–Zwolle),
  `Austrian Bundesliga` (Rapid–WSG Tirol), `Ekstraklasa`
  (Widzew–Wieczysta). Gdyby pole opisywało ligę, byłoby `True`.
- Rozkład względem kickoffu jest wymowny: dla meczów **już rozpoczętych**
  `True` w 3 z 32 (9%), dla **jeszcze nierozpoczętych** w 1 z 258 (0,4%) —
  a tym jedynym jest Chinese League 1 o 10:00 UTC, czyli tuż po chwili
  obserwacji. Dwudziestotrzykrotna różnica.
- Pozostałe 29 rozpoczętych meczów bez xG to Algeria U20, Israel Liga Alef
  i podobne — tam Sofascore xG faktycznie nie liczy (F12).

Czyli `resolve.py:223` czyta `event.get("hasXg", False)` z payloadu meczu,
który się jeszcze nie odbył, gdzie ta flaga z natury jest fałszywa.

**Dlaczego to nie psuje danych:** bramkowanie metryki xG dzieje się
w zupełnie innym miejscu i **poprawnie** — `metrics.py:361` sprawdza
`hasXg` na **każdym meczu historycznym z próbki** osobno:

```python
if sofascore_key == "expectedGoals" and not listing_event.get("hasXg", False):
```

To jest właściwe pytanie zadane we właściwym miejscu. A `Fixture.has_xg`
nie ma **żadnego konsumenta** — `grep` po `src/bet/sofa` i `scripts/sofa`
znajduje tylko deklarację w `contracts.py:69` i przypisanie
w `resolve.py:223`.

**Waga: P3.** Pole wprowadzające w błąd, nie błąd w zachowaniu. Poprawka to
albo usunięcie go z `Fixture`, albo nazwanie zgodnie z treścią
(`kickoff_event_has_xg`), żeby nikt go w przyszłości nie użył jako bramki
„czy da się tu policzyć xG" — bo w tej roli odpowiadałby „nie" dla całej
Bundesligi.

**Test:** `Fixture` zbudowany z payloadu meczu nierozpoczętego w lidze z xG
— asercja opisująca, że to pole **nie** jest bramką zdolności; plus test na
`metrics.py`, że próbka złożona z meczów z `hasXg=True` daje `xg_total`,
a z `hasXg=False` daje `STAT_KEY_ABSENT`, nigdy zero.

**Uwaga metodologiczna do siebie:** pierwszy raz policzyłem to pole jako
„100% wypełnione", bo test „nie `None`/`""`/`[]`" traktuje `False` jako
wartość obecną. Dla pola logicznego ten test nie mierzy niczego. Liczby dla
`has_xg` powyżej pochodzą z przeliczenia wartości, nie z obecności.

---

## Pomiar architektoniczny: `SOFA_TARGET_RPS` nie jest dziś wąskim gardłem

**POTWIERDZONE** czytaniem kodu obu stron mostu (2026-09-18). Zapisane, bo
pytanie „czy nie da się po prostu puścić 20 req/s" wróci, a odpowiedź jest
techniczna, nie tylko ostrożnościowa.

Userscript ma **własny** limit, niezależny od konfiguracji Pythona:

```js
const MIN_INTERVAL_MS = 350;   // userscripts/sofascore-bridge.user.js:58
```

To sufit **~2,86 req/s**. Do tego pętla jest **szeregowa**: `bridge_server.py`
wydaje jedno zadanie na `claim` (`self._pending.pop(0)`), jedna karta je
wykonuje i wraca po następne. Nie ma współbieżności, którą dałoby się
podnieść parametrem.

Konsekwencja: podniesienie `SOFA_TARGET_RPS` **nie zwiększy tempa** — tylko
przeniesie rolę limitera z kubełka w Pythonie na userscript, i zbuduje kolejkę
przed kartą. Zmierzony zapas jest mały, nie dziesięciokrotny:

| | |
|---|---|
| tempo obserwowane (RESOLVE, SAMPLES) | 1,72–2,00 req/s |
| sufit mostu | ~2,86 req/s |
| **maksymalny możliwy zysk z rozkręcenia strony Pythona** | **~1,5×** |

Dla porównania z rozumowaniem „WordPress unosi 120 req/s, więc 20 to mało":
to porównanie mierzy **przepustowość**, a nas ogranicza **tolerancja**.
120 req/s WordPressa to suma po wszystkich odwiedzających; my jesteśmy jednym
IP. 20 req/s przez godzinę to 72 000 żądań z jednego adresu bez wzorca
zachowania człowieka — to podpis, który się blokuje niezależnie od
przepustowości. A 2026-09-17 przeszliśmy tę granicę raz (szczyt 550 req/s)
i nie ma już kolejnego obejścia w zapasie.

**Gdzie naprawdę leży skrócenie przebiegu — w usuwaniu żądań, nie w tempie.**
Z pomiarów tego przebiegu:

| źródło | żądań | który wpis |
|---|---|---|
| `events/next` dla tenisa (100% 404) | 179 | F17 |
| 404 odkrywane ponownie, znane z poprzedniego przebiegu | 225 | F17 |
| drugie pytanie Superbetu przez SAMPLES, choć artefakt istnieje | ~600 | F19 |
| **razem** | **~1 000** | **≈8 minut przy 2 req/s** |

To jest ta sama oszczędność co podniesienie limitu o 1,5×, tylko bez ryzyka.

---

## F22 · P2 · Etap w logu jest przyszyty do metody klienta, nie do wywołującego — koszt SAMPLES ukrywa się pod `RESOLVE`

**POTWIERDZONE** (2026-09-18). Rozszerza F20 z `SuperbetClient` na
`SofascoreClient`, czyli na cały log.

Zauważone tak: licznik żądań `RESOLVE` **rósł po zakończeniu etapu** — 3 486
o 12:16, 3 505 dwie minuty później, choć w tym czasie chodził SAMPLES.

Przyczyna jest w jednej linii:

```python
def entity_events(self, entity_id, kind, page):
    url = f"…/team/{entity_id}/events/{kind}/{page}"
    return self._execute(url, stage="RESOLVE")      # ← client.py:292
```

`stage` jest własnością **metody**, nie wywołującego. A `entity_events`
wywołuje też SAMPLES, przez `get_historical_events` — kiedy strona listingu
nie jest w cache'u albo trzeba zejść głębiej, żeby uzbierać `sample_n=10`.

Zmierzone:

| | |
|---|---|
| żądania opisane `RESOLVE`, wykonane **po** starcie SAMPLES | **146** |
| wszystkie na `team/{id}/events/last/{page}` | 146 (100%) |
| z tego strony głębsze niż zerowa | **64** (rozkład: p0 82, p1 25, p2 9, p3 17, p4 13) |
| prawdziwy koszt SAMPLES do tej chwili | 1 631 `statistics` + 146 listingów = **1 777** |
| **udział kosztu SAMPLES ukryty pod etykietą `RESOLVE`** | **8,2%** |

**Dwie moje wcześniejsze liczby były przez to błędne** i poprawiam je tutaj:

1. Napisałem, że „SAMPLES robi *wyłącznie* `event/{id}/statistics`, żadnych
   listingów". Nieprawda — robi też listingi, w tym zejścia do 4. strony.
   Wyszło mi tak, bo filtrowałem log po etykiecie etapu, a etykieta kłamie.
2. Raportowane co dwie minuty liczniki `by_stage` są od momentu startu
   SAMPLES zawyżone dla `RESOLVE` i zaniżone dla `SAMPLES`. Sam werdykt
   „RESOLVE domknięty na 3 377 żądań" pozostaje prawdziwy, bo dotyczy
   momentu przed startem następnego etapu.

Wartość diagnostyczna, którą to psuje, jest dokładnie tą, po którą wprowadzono
F8: nie da się zapytać „ile kosztował etap", bo odpowiedź zależy od tego,
która metoda klienta akurat była użyta.

**Proponowana poprawka:** `stage` musi przyjść od wywołującego — parametr
w `entity_events` (i w każdej innej metodzie, która ma go dziś na sztywno),
domyślnie `"CLIENT"`, przekazywany z `run_*.py`. Alternatywnie kontekst
przebiegu (`contextvars`) ustawiany raz na etap, co ma tę zaletę, że nie da
się go zapomnieć przy dodaniu nowej metody.

**Test:** wywołać `entity_events` z zadeklarowanego etapu `SAMPLES`
i sprawdzić, że wiersz logu niesie `stage: "SAMPLES"`. **Failuje na
dzisiejszym kodzie z właściwego powodu** — dziś niesie `"RESOLVE"`.
Dodatkowo test-strażnik: dla każdej publicznej metody `SofascoreClient`
sprawdzić, że nie przekazuje literału do `_execute`; to wyłapie następną
metodę dopisaną z przyszytym etapem.

---

## F23 · P2 · Przepustowość mostu zależy od stanu karty w przeglądarce — 13× wzrost opóźnienia bez udziału Sofascore

**POTWIERDZONE** co do przyczyny lokalnej, `PODEJRZENIE` co do dokładnego
mechanizmu (2026-09-18, ~10:08 UTC, w trakcie SAMPLES).

### Objaw

Skokowa zmiana, nie degradacja:

| minuta przebiegu | żądań/min | mediana `elapsed_ms` |
|---|---|---|
| 2–45 | ~119–127 | **148–174** |
| **46** | **32** | **1 992** |
| 47 | 31 | 1 996 |

Opóźnienie ×13, przepustowość ÷4, w jednej minucie. Dotyczy **wszystkich**
tras jednakowo (`event/{id}/statistics` i `team/{id}/events/last` po ~1 990 ms),
statusy bez zmian (200/404), **zero 403**, breaker `CLOSED`.

### Czego to nie jest — i dlaczego to sprawdziłem, zanim zgłosiłem

Pierwsza hipoteza brzmiała „Sofascore zaczął nas dławić" (tarpit ze stałym
dodanym opóźnieniem), bo rozrzut jest nienaturalnie wąski: 1 988–2 015 ms,
odchylenie ~±10 ms. Zator sieciowy jest **rozedrgany**; stały dodatek
~1,84 s to *polityka*, nie kongestia. To był wniosek wart natychmiastowego
zgłoszenia — i błędny.

Wykluczone pomiarem:

| sprawdzenie | wynik |
|---|---|
| sieć do Sofascore | `ping api.sofascore.com` → **23,3 ms**, 0% straty, stddev 0,4 ms |
| kod odpowiedzi | bez zmian, zero 403, zero 429 |
| obciążenie maszyny | **load average 4,24** |
| procesy | `cameracaptured` 17,4%, `coreaudiod` 16,6%, Chrome Renderer 25,3%, Chrome Helper 30,5% |

Czyli w chwili skoku na maszynie trwała rozmowa wideo, a Chrome był zajęty.
Sieć i serwer są niewinne: przyczyna jest **lokalna**.

### Mechanizm — `PODEJRZENIE`

Najprawdopodobniej dławienie timerów w karcie w tle. Userscript odmierza
tempo przez `setTimeout`:

```js
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function pace() { const wait = MIN_INTERVAL_MS - (…); if (wait > 0) await sleep(wait); }
```

Chrome ogranicza timery w kartach niewidocznych (zwykle do ~1/s, po kilku
minutach ukrycia jeszcze ostrzej). Zamierzone 350 ms staje się wtedy ~1 s,
a pętla odbierająca zadania dokłada drugie tyle — co składa się na
obserwowane ~2 s.

**Rywalizację o procesor udało się wykluczyć kontrprzykładem.** Epizod trwał
dokładnie dwie minuty i sam się skończył:

| minuta | żądań/min | mediana `elapsed_ms` | `load average` |
|---|---|---|---|
| 45 | 100 | 151 | — |
| **46** | **32** | **1 992** | 4,24 |
| **47** | **31** | **1 996** | — |
| 48 | 96 | **160** | — |
| 49–51 | 125 | 153–159 | **5,35** |

W chwili powrotu do normy obciążenie maszyny było **wyższe** niż w czasie
awarii (5,35 vs 4,24), a Chrome nadal zajmował ~55% procesora (Helper 29,9%
+ Renderer 24,3%, do tego WindowServer 34,5%). Gdyby przyczyną było
zagłodzenie procesora, opóźnienie nie wróciłoby do 153 ms przy rosnącym
obciążeniu.

Zostaje więc **widoczność karty** — i to zostało **POTWIERDZONE
niezależnie**: zapytany o tamte dwie minuty operator podał, że włączył
wtedy w przeglądarce Superbet i zaraz go zamknął. Zgadza się i co do
przyczyny (karta sofascore.com zeszła na drugi plan), i co do czasu trwania
(dwie minuty). Mechanizm nie jest już hipotezą; formalnie nie zmierzyłem
`document.visibilityState`, ale zeznanie operatora i pomiar wskazują to samo,
a alternatywa procesorowa jest **wykluczona kontrprzykładem** powyżej.

**To jest praktyczna pułapka, nie ciekawostka:** zajrzenie do Superbetu
w tej samej przeglądarce — czyli rzecz, którą operator robi w trakcie dnia
zakładowego najzupełniej naturalnie — spowalnia pipeline czterokrotnie.
Karta mostu powinna siedzieć w osobnym oknie, którego się nie zasłania.

### Dlaczego to jest warte wpisu

Bo to znaczy, że **czas przebiegu zależy od tego, czy operator patrzy na
kartę sofascore.com**. Przy etapie liczonym w godzinach to nie jest
ciekawostka: przełączenie się na spotkanie wydłuża SAMPLES czterokrotnie,
bez żadnego sygnału w logu, który by na to wskazywał. Jest to też dobra
wiadomość w drugą stronę: to nie zbliża nas do blokady, a efektywne tempo
spadło do ~0,5 req/s, czyli *łagodniejszego* niż zakładane.

**Proponowana poprawka (obejście, nie naprawa):** poprosić Chrome, by nie
usypiał tej karty — w praktyce trzymać ją w osobnym oknie na wierzchu, albo
wyłączyć dla niej „Memory Saver"/throttling. Programowo pomogłoby zastąpienie
`setTimeout` czymś, czego Chrome nie dławi (`Worker` z własnym zegarem albo
`requestAnimationFrame`… który w tle też jest wstrzymywany — więc realnie
`Worker`). Do rozważenia, czy warto: koszt jest tylko czasowy.

---

## F24 · P2 · Most wyrzuca nagłówki odpowiedzi — dokładnie te, które odpowiadają na pytanie „czy nas dławią"

**POTWIERDZONE** (2026-09-18), wyszło przy diagnozie F23.

Userscript odsyła do serwera tylko trzy rzeczy:

```js
payload = { id: job.id, status: res.status, body: body };   // user.js:189
```

a `bridge_server.py` przechowuje dokładnie tyle (`__slots__ = ("id","url",
"done","status","body","error","created")`). **Nagłówki odpowiedzi są
odrzucane.**

W chwili, gdy opóźnienie skoczyło 13× i trzeba było rozstrzygnąć, czy to
Sofascore nas dławi, jedyne miejsce, które mogłoby to powiedzieć wprost —
`Retry-After`, `X-RateLimit-*`, `Server-Timing`, `Age`, `X-Cache` — było
wyrzucone. Rozstrzygnięcie poszło więc przez wnioskowanie poboczne (ping,
`load average`, lista procesów), a nie przez odczyt.

Jest to ta sama klasa luki co „prowizja licznika sam się koryguje z nagłówków"
u innego dostawcy: nagłówki to jedyne miejsce, w którym dostawca **mówi**
o limitach, zamiast kazać nam ich zgadywać.

**Proponowana poprawka:** przekazywać wybrane nagłówki (`retry-after`,
`x-ratelimit-*`, `server-timing`, `age`, `x-cache`, `x-served-by`) w polu
`headers` zadania i zapisywać je w wierszu logu. Nie wszystkie — tylko te
diagnostyczne, żeby nie puchło.

**Test:** transport podstawiony tak, by zwrócił `Retry-After: 30` — wiersz
logu musi to pole nieść. **Failuje dziś z właściwego powodu**: dziś nie ma
gdzie go zapisać.

---

## F25 · P0 · Mecz męski dopasowany do żeńskiego, `identity: CONFIRMED` — dwie bramki przeszły, trzeciej nie ma

**POTWIERDZONE** (2026-09-18) na artefakcie `02_fixtures.json`, pełnym
łańcuchem dowodowym. **To jest jedyne znalezisko tego przebiegu, które wprost
prowadzi do postawienia zakładu na inny mecz, niż się myśli.**

### Co się stało

| | |
|---|---|
| Superbet (`14810549`) | **IF Gnistan · HJK Helsinki**, 2026-09-**18** 16:00 UTC |
| dopasowane zdarzenie Sofascore (`16681087`) | **HJK Helsinki · IF Gnistan**, 2026-09-**19** 15:00 UTC |
| rozgrywki | **`Kansallinen Liiga, Women, Championship group`** |
| werdykt tożsamości | **`CONFIRMED`** |

Czyli: inny dzień, **inna płeć**, i **odwrócone strony**. Zakład z męskiej
Veikkausliigi zostałby wyceniony na próbkach z żeńskiej Kansallinen Liigi.

### Dlaczego obie bramki przeszły

`match_quality` wymaga dwóch warunków i **oba były spełnione**:

1. **Okno ±24 h**: `abs(09-19 15:00 − 09-18 16:00) = 23 h` — mieści się
   w oknie z zapasem godziny.
2. **Nazwa przeciwnika**: te same dwa kluby grają i w lidze męskiej,
   i w żeńskiej, więc `hjk helsinki` pasuje idealnie.

Znalazło się **dokładnie jedno** pasujące zdarzenie, więc kod nie uznał tego
za niejednoznaczne i zapisał `status='verified'`, `identity='CONFIRMED'`.

### Sedno: Sofascore **nie** oznacza konsekwentnie drużyn kobiecych

To jest założenie, na którym opierał się F9 — i jest błędne. Encja
**296052 nazywa się po prostu `IF Gnistan`**, bez sufiksu, a w jej listingu
100% zdarzeń to rozgrywki kobiece:

| rozgrywki w listingu encji 296052 | zdarzeń |
|---|---|
| Kansallinen Liiga, Women | 14 |
| Kansallinen Liiga, Women, Championship group | 10 |
| Ykkönen, Women | 6 |
| Suomen Cup, Women | 6 |
| Kansallinen Cup, Women | 1 |

37 wystąpień, wszystkie kobiece, nazwa bez `(W)`. Tak samo `HJK Helsinki`
w tym listingu. **F9 zmierzył sufiksy w nazwach z tablicy Superbetu dla
`sportId=190`, nie w nazwach drużyn u Sofascore** — i te dwie rzeczy zostały
zlane w jedno. Sufiks nazwy nie jest wiarygodnym nośnikiem płci po stronie
Sofascore.

### Skala i to, co ją dziś ograniczyło

| | |
|---|---|
| fixture'y piłkarskie w artefakcie | 290 |
| rozjazd płci Superbet↔Sofascore | **1 (0,34%)** |
| zgodne, oba kobiece | 4 |
| zgodne, oba męskie | 285 |
| **odwrócenie stron** w całym artefakcie | **1 — ten sam mecz** |

Jeden przypadek na 290. Ale mechanizm jest ogólny: wystarczy, że te same
dwa kluby grają w obu ligach w odstępie mniejszym niż 24 h. W weekend, gdy
ligi męskie i żeńskie grają równolegle, to przestaje być rzadkie. Nie mam
pomiaru z innych dni, więc **częstotliwość** oznaczam `PODEJRZENIE`; ten
jeden przypadek jest `POTWIERDZONY`.

### Dwie niezależne bramki, z których każda złapałaby to sama

Obie są tanie i żadnej dziś nie ma.

**(a) Płeć z nazwy rozgrywek, nie z nazwy drużyny.** Nazwy rozgrywek są
u Sofascore oznaczane rzetelnie — `Kansallinen Liiga, Women` — nawet tam,
gdzie nazwy drużyn nie są. Reguła: płeć wyprowadzona z markera `(K)` po
stronie Superbetu musi zgadzać się z płcią wyprowadzoną z
`competition_name` po stronie Sofascore; niezgoda = odrzucenie, nie `FUZZY`.
Sprawdzone na dzisiejszych danych: ta reguła daje 285 zgodnych męskich,
4 zgodne kobiece i **wyłapuje dokładnie ten jeden rozjazd**, zero fałszywych
alarmów.

**(b) Orientacja stron.** Zmierzone na całym artefakcie: `side_a/side_b`
Superbetu zgadza się z `home/away` Sofascore w **483 z 484** fixture'ów,
niejednoznacznych **zero** — a jedynym odwróceniem jest ten mecz
(`direct=54,5` vs `cross=200,0`, czyli rozstrzygnięcie bez cienia
wątpliwości). Sygnał jest więc ostry i praktycznie bezszumny.

Warto zauważyć, że bramka (b) ma **własną, osobną wartość**: bez niej rynki
per-drużyna (`*_for`, narożne danej strony, kartki danej strony) mogą zostać
przypisane odwrotnie, i to nawet przy poprawnie zidentyfikowanym meczu.
Dziś nic tego nie sprawdza.

### Poprawka i zwężenie okna

Poza (a) i (b): **okno ±24 h jest za szerokie** dokładnie o tyle, ile trzeba,
by wpuścić mecz „tych samych drużyn nazajutrz". Rozjazd wyniósł 23 h.
Zważywszy, że mediana rozjazdu kickoffu dla piłki to 0 minut, okno rzędu
±6 h byłoby w piłce bez kosztu. **Dla tenisa nie** — tam rozjazdy
ośmiogodzinne są masowe i mają inną przyczynę (patrz F26), więc okno musi
być zależne od sportu, a nie ścięte globalnie.

**Test:** fixture Superbetu `IF Gnistan · HJK Helsinki` @ 09-18 16:00 wobec
listingu zawierającego wyłącznie zdarzenie żeńskie @ 09-19 15:00 —
`resolve_entity` musi zwrócić brak dopasowania, **nie** `CONFIRMED`.
**Failuje na dzisiejszym kodzie z właściwego powodu**: dziś zwraca
`CONFIRMED`. Drugi test, na orientację: zdarzenie z odwróconymi stronami
musi zostać odrzucone (albo oznaczone), a nie przyjęte.

---

## F26 · P2 · Kickoff meczów ITF jest o strefę czasową turnieju późniejszy — i to on karmi bramkę czasową kuponu

**POTWIERDZONE** (2026-09-18) na artefaktach, z policzoną sygnaturą
mechanizmu. Powiązane z F25: to druga połowa wyjaśnienia rozjazdów czasu,
i to ona przesądza, że okna dopasowania nie wolno ściąć globalnie.

### Nasz kod liczy epoch poprawnie — rozjazd jest między źródłami

Sprawdzone na surowym payloadzie z cache'u, żeby wykluczyć własny błąd:

```
raw startTimestamp = 1789725600  ->  UTC 2026-09-18T10:00
artifact kickoff_utc =                   2026-09-18T10:00     ✓ zgadza się
superbet                                 2026-09-18T01:04
```

Czyli `sofa` nic nie psuje przy konwersji. Nie zgadzają się **źródła**.

### Sygnatura: różnica **równa się przesunięciu strefowemu miejsca turnieju**

| Δ (Sofa − Superbet) | strefa miasta | turniej |
|---|---|---|
| +9,1 h / +8,9 h / +8,9 h / +8,8 h | Kyoto **+9** | ITF W35 Kyoto |
| +8,6 h / +8,0 h / +8,0 h / +7,3 h | Guiyang **+8** | ITF M25 Guiyang |
| +8,5 h / +8,0 h / +8,0 h / +8,0 h | Shenyang **+8** | ITF W35 Shenyang |

**12 z 12** przypadków rozjazdu >6 h, dla których dało się przypisać strefę
miasta, ma różnicę równą tej strefie (±1,5 h). Losowo złe dane nie dają
takiej zgodności — **exact offset to podpis usterki konwersji**, nie szumu.

Kierunek wskazuje na Sofascore: ITF W35 w Kyoto o 01:04 UTC to 10:04 czasu
lokalnego, czyli typowa poranna sesja ITF; wersja Sofascore (10:00 UTC) to
19:00 lokalnie. Najprostsze wyjaśnienie: **dla turniejów ITF Sofascore
publikuje czas lokalny tak, jakby był UTC.** To wyjaśnienie oznaczam
`PODEJRZENIE` — nie mam niezależnego źródła prawdy, a jedyne, o które mógłbym
zapytać, to właśnie Sofascore. **Sygnatura 12/12 jest `POTWIERDZONA`.**

Zakres: dotyczy **tylko ITF**. Rozkład wszystkich 191 porównywalnych
fixture'ów tenisowych ma **122 z różnicą 0 h**; ATP/WTA/Challengery się
zgadzają. Gdyby Sofascore mylił strefy zawsze, zera by nie było.

### Dlaczego to boli: karmi jedyną bramkę czasową kuponu

`coupon.py:99` odrzuca fixture'y z `kickoff_utc <= now + 15 min` — czyli
`sofa`, inaczej niż stary pipeline, **ma** filtr kickoffu. Tylko że dostaje
do niego wartość spóźnioną o 7–9 h, a błąd idzie w najgorszą stronę:
**mecz zakończony wygląda na nadchodzący.**

Zmierzone o 10:20 UTC, na żywo, na dzisiejszym artefakcie:

| | |
|---|---|
| fixture'y, w których czas Superbetu **już minął**, a artefaktu **nie** | **6** |
| czyli przeszłyby bramkę `kickoff > now+15min` z rozstrzygniętym wynikiem | 6 |

Konkretnie: Yidi Yang–Sijia Wei (naprawdę 02:30, artefakt 10:30),
Eri Shimizu–Jia-Jing Lu (02:55 / 12:00), Kristiana Sidorova–Yufei Ren
(03:00 / 11:30), Natsuki Yoshimoto–Ena Shibahara (03:13 / 12:00),
Sheng Tang–Chase Ferguson (03:27 / 12:00), Alibek Kachmazov–Robin Catry
(04:42 / 12:00).

**Amortyzator sprawdzony i POTWIERDZONY — dlatego waga to P2, nie P1.**
Zapytałem Superbet o wszystkie 6 zagrożonych fixture'ów:

| fixture | czas prawdziwy | czas w artefakcie | wycenione rynki **teraz** |
|---|---|---|---|
| Yidi Yang · Sijia Wei | 02:30 | 10:30 | **0** |
| Eri Shimizu · Jia-Jing Lu | 02:55 | 12:00 | **0** |
| Kristiana Sidorova · Yufei Ren | 03:00 | 11:30 | **0** |
| Natsuki Yoshimoto · Ena Shibahara | 03:13 | 12:00 | **0** |
| Sheng Tang · Chase Ferguson | 03:27 | 12:00 | **0** |
| Alibek Kachmazov · Robin Catry | 04:42 | 12:00 | **0** |

6 z 6 bez ceny. Mecz rozstrzygnięty schodzi z tablicy, więc OFFER nie ma co
zapisać i wiersz nie dojdzie do kuponu.

**Ale to jest ochrona przez przypadek, nie przez projekt**, i dlatego wpis
zostaje otwarty: chroni nas *delisting u bukmachera*, a nie bramka, którą
napisaliśmy w tym celu. Nie zadziała dla meczu granego na żywo, na który
Superbet **wciąż wystawia** kursy — a wtedy kickoff spóźniony o 8 h mówi
„jeszcze się nie zaczęło" o spotkaniu w trzecim secie.

### Poprawka

Nie „naprawiać" czasu Sofascore, bo nie wiemy, który jest prawdziwy —
tylko **przestać ufać jednemu źródłu w milczeniu**:

1. **Bramka czasowa kuponu powinna używać czasu Superbetu**, nie Sofascore.
   To Superbet przyjmuje zakład i to jego zegar decyduje, czy rynek jest
   otwarty. Kickoff Sofascore niech służy do dopasowania tożsamości, nie do
   decyzji „czy jeszcze można".
2. **Rozjazd > 2 h między źródłami to sygnał, nie szum** — zapisać go
   w artefakcie (`kickoff_disagreement_h`) i traktować jako powód do
   `FUZZY`/odrzucenia, tak jak F25 proponuje dla płci. Dziś rozjazd 23 h
   przechodzi bez śladu.
3. **Okno dopasowania per sport**: w piłce mediana rozjazdu to 0 min, więc
   ±6 h jest darmowe i domyka F25. W tenisie ±24 h musi zostać, dopóki ITF
   rozjeżdża się o 9 h — i właśnie dlatego F25 nie wolno załatwić globalnym
   ścięciem okna.

**Test:** fixture z rozjazdem 9 h między Superbetem a Sofascore musi trafić
do artefaktu z zapisanym rozjazdem i nie może przejść bramki kuponu, jeśli
czas Superbetu już minął. **Failuje na dzisiejszym kodzie z właściwego
powodu** — dziś przechodzi, bo bramka patrzy na zły zegar.

---

## F27 · P2 · Przy dwóch listingach Superbetu o tym samym meczu cena jest nadpisywana milcząco, „ostatni wygrywa"

Mechanizm **POTWIERDZONY** czytaniem kodu; **skutek `PODEJRZENIE`** — dziś
nie dało się go wywołać (wyjaśnienie niżej).

20 z 484 dzisiejszych fixture'ów niesie **po dwa** `superbet_event_id`
(18 tenis, 2 piłka) — Superbet wystawia ten sam mecz dwa razy.
`OfferFetcher` przechodzi po wszystkich id i wpisuje kursy do wspólnego
słownika kluczowanego `(market, subject, line)`:

```python
if direction == "OVER":
    combined_odds[key]["over_odds"] = float(price)      # offer.py
else:
    combined_odds[key]["under_odds"] = float(price)
```

Przypisanie, nie porównanie. Jeśli oba listingi wyceniają
`goals_total 2.5 OVER` **różnie**, wygrywa ten, który przyszedł później —
bez porównania, bez śladu w artefakcie, bez ostrzeżenia. O tym, która cena
zostanie, decyduje kolejność `superbet_event_ids`, czyli szczegół budowy
tablicy.

Dlaczego to nie jest kosmetyka: cała decyzja zakładowa to porównanie
prawdopodobieństwa z ceną. Milcząco wybrana **wyższa** cena produkuje edge,
którego nie ma; **niższa** ukrywa wartość, która jest.

### Czego nie udało się zmierzyć i dlaczego

Sprawdziłem 8 z 20 przypadków, pytając Superbet o oba id osobno.
W **żadnym** nie było dwóch *jednocześnie żywych* listingów: siedem par
miało 0 i 0 wycenionych rynków (mecze ITF już się zakończyły — patrz F26),
jedna para miała 0 i 8. Wspólnych kluczy `(market, subject, line, direction)`:
**zero**. Nie ma więc ani jednego dowodu na rozjeżdżające się ceny — i ani
jednego na to, że się nie rozjeżdżają.

Warto zauważyć, że w tej jednej parze 0/8 scalanie przez **unię** zadziałało
na naszą korzyść: odzyskało listing, który żyje. Unia jest dobra; problemem
jest tylko rozstrzyganie kolizji.

### Proponowana poprawka

Przy kolizji nie nadpisywać, a **rozstrzygać jawnie i zapisywać fakt**:
wziąć cenę ostrożniejszą (niższą dla strony, którą obstawiamy), zapisać obie
w artefakcie i podnieść rozjazd jako sygnał, gdy przekroczy próg. Zasada jest
ta sama co w F25 i F26: **niezgoda dwóch źródeł ma zostawić ślad, a nie
zniknąć.**

**Test:** dwa listingi tego samego meczu, oba wyceniające
`goals_total 2.5 OVER`, jeden 1,80, drugi 1,95 — artefakt musi nieść obie
i wybraną świadomie, a nie tę, która przyszła druga. **Failuje na dzisiejszym
kodzie z właściwego powodu**: dziś wynik zależy od kolejności wejścia.

---

## Weryfikacja pipeline'u 2026-09-18 — co sprawdzono i wyszło **czysto**

Zapisane, żeby nie powtarzać i żeby wiadomo było, czego F25/F26/F27 **nie**
dotyczą. Wszystko offline, na artefaktach i cache'u.

| Sprawdzenie | Metoda | Wynik |
|---|---|---|
| **Przeciek z przyszłości do próbki** | wywołanie **prawdziwej** `get_historical_events` z klientem, który rzuca wyjątek przy próbie sieci (więc tylko cache) | **615 próbek encji, 0 zdarzeń o/po kickoffie** |
| **Mecz w swojej własnej próbce** | j.w. | **0** |
| **Rozmiary próbek** | j.w. | mediana **10**, maks. 10 (zgodnie z `sample_n`) |
| **Jedno zdarzenie Sofascore w dwóch wierszach** | zliczenie `sofascore_event_id` | **0** |
| **Jedno id Superbetu w dwóch wierszach** | zliczenie | **0** |
| **Poprawność scalania podwójnych listingów** | porównanie nazw stron w obu wpisach z tablicy, weryfikacja u Sofascore | **20 z 20 poprawnych** |
| **Orientacja stron (home/away)** | `fuzz.ratio` prosto vs na krzyż, na całym artefakcie | **483 z 484 zgodne, 0 niejednoznacznych, 1 odwrócona** (ta z F25) |
| **Konwersja epoch → UTC** | surowy `startTimestamp` z cache'u vs `kickoff_utc` w artefakcie | **zgadza się co do minuty** |

Dwie uwagi do przypadków, które wyglądały na błąd i **nie są**:

- **`Piikkiön Palloseura`** miał dwa listingi Superbetu z *różnymi*
  przeciwnikami: `· Jyty` i `· Jyrkkalan Tykit`. Wyglądało na zlanie dwóch
  różnych meczów. Sofascore rozstrzyga: przeciwnikiem jest
  **Jyrkkälän Tykit**, a `Jyty` to jego skrót. Scalenie poprawne.
- **`best_of: 2` dla wszystkich 290 fixture'ów piłkarskich** —
  semantycznie bez sensu (piłka nie ma „best of"), bo pole bierze
  `defaultPeriodCount`, czyli liczbę połów. Dla tenisa to samo pole daje
  poprawne `3`. Nic w `src/bet/sofa` nie czyta `best_of` dla piłki, więc
  **P3** — nazwa pola opisuje coś innego, niż pole zawiera. Tej samej klasy
  co `has_xg`.

---

## Weryfikacja metryk 2026-09-18 — uruchomiona **prawdziwym** `extract_metric` na 1 757 zbuforowanych meczach

Bez sieci. Dla każdego zbuforowanego meczu policzone wszystkie 30 metryk
z obu stron, przez `extract_flat_statistics` + `extract_metric`, i zebrany
rozkład wyników wraz z powodami braku.

### Sanity check median — wszystkie zgodne z rzeczywistością

| metryka | mediana | maks. | ocena |
|---|---|---|---|
| `goals_total` | 3,00 | 13 | ✓ |
| `corners_total` | 9,00 | 23 | ✓ |
| `cards_total` (żółte) | 4,00 | 11 | ✓ |
| `cards_points_total` | 5,00 | 10 | ✓ |
| `fouls_total` | 25,00 | 53 | ✓ |
| `shots_total` | **24,00** | 43 | ✓ |
| `shots_on_target_total` | **8,00** | 20 | ✓ |
| `xg_total` | 2,46 | 6,9 | ✓ |
| `games_total` (tenis) | 20,00 | 39 | ✓ |
| `sets_total` | 2,00 | 3 | ✓ |
| `aces_total` | 4,00 | 38 | ✓ |
| `double_faults_total` | 6,00 | 25 | ✓ |

**Najważniejsze z tej tabeli:** `shots_total` (mediana 24) jest wyraźnie
większe od `shots_on_target_total` (mediana 8). To potwierdza, że
odwzorowanie nie jest odwrócone — `totalShotsOnGoal` to **wszystkie** strzały,
`shotsOnGoal` to strzały celne, i tak są użyte. Pułapka nazewnicza Sofascore
nie zadziałała.

### Zero kontra brak — trzyma

| metryka | wartości | zer | ocena |
|---|---|---|---|
| `shots_total`, `shots_for` | 474 | **0** | ✓ niemożliwe zero nie występuje |
| `xg_total`, `xg_for` | 356 | **0** | ✓ |
| `games_total` | 892 | **0** | ✓ |
| `sets_total` | 1 576 | **0** | ✓ |
| `corners_total` | 884 | 2 | ✓ (0 narożnych bywa) |
| `fouls_total` | 742 | 2 | ✓ |

Ani jedna metryka, dla której zero jest fizycznie niemożliwe, nie ma zer.
Braki wychodzą jako `STAT_KEY_ABSENT` / `NO_STATISTICS`, nie jako 0,0 —
czyli reguła L1/L2 obowiązuje w praktyce, nie tylko w docstringu.

`tiebreaks_total` ma 678 zer na 894 (76%) i moja heurystyka „dominacja zer"
to podniosła — **fałszywy alarm**: większość meczów nie ma tie-breaka, więc
zero jest tam prawdziwą wartością. Zapisuję to, bo ta heurystyka („mediana 0
to sygnał") jest skądinąd dobra i warto wiedzieć, gdzie nie działa.

### Braki statystyk są skoncentrowane tam, gdzie się tego spodziewamy

`event/{id}/statistics` odpowiada **404 w 904 z 3 254** wywołań (28%), co
zgadza się z `NO_STATISTICS = 910` policzonym niezależnie z ekstrakcji.
To te same najniższe ligi i młodzież co w F12.

### Korekta: **incydenty są pobierane** — moja wcześniejsza diagnoza była błędna

Zobaczyłem `NO_INCIDENTS` w 1 898 z 1 938 ocen `cards_points_*` i zacząłem
to opisywać jako strukturalną lukę („nic nie woła `/incidents`"). **Nieprawda.**
`samples.py:199-203` woła je warunkowo:

```python
needs_incidents = sport == "football" and bool(...)
if needs_incidents:
    incidents_json = client.event_incidents(event_id)
```

— czyli tylko wtedy, gdy Superbet wycenia dla danego fixture'u rynek na punkty
kartkowe. W logu tego przebiegu jest **58** wywołań `event/{id}/incidents`,
wszystkie 200. Wysoki `NO_INCIDENTS` na zbuforowanych meczach jest więc
**zamierzoną oszczędnością (A5)**, nie luką: nie płacimy za incydenty meczów,
których kartkowych rynków nikt nie wycenia.

### Skorygowany skład żądań przebiegu (etykiety etapów pominięte — kłamią, F22)

| trasa | żądań | 200 | 404 |
|---|---|---|---|
| `event/{id}/statistics` | 3 254 | 2 349 | 904 |
| `team/{id}/events/last/{page}` | 1 797 | 1 771 | 26 |
| `team/{id}/events/next/{page}` | 862 | 420 | 442 |
| `search/all` | ~500 | ~500 | 0 |
| `event/{id}` | 484 | 484 | 0 |
| Superbet `events` | 288 | 288 | 0 |
| `event/{id}/incidents` | 58 | 58 | 0 |

**To druga korekta mojego twierdzenia o SAMPLES.** Powiedziałem najpierw
„wyłącznie `statistics`", potem poprawiłem na „`statistics` + listingi".
Pełny skład to `statistics` + listingi + `incidents` + Superbet. Za każdym
razem mój błąd brał się z tego samego: filtrowania po etykiecie `stage`,
która jest przyszyta do metody klienta (F22).

---

## F28 · P1 · Tożsamość strzałów pomija `hitWoodwork` — odrzuca 30% meczów, gdy realny błąd to 1,4%, i odrzuca je **kierunkowo**

**POTWIERDZONE** (2026-09-18) pomiarem na 580 zbuforowanych meczach.

### Bramka

`check_identities` (`metrics.py`) blokuje mecz, gdy:

```python
if s_on + s_off + s_blk != s_tot:      # shotsOnGoal + shotsOffGoal + blockedScoringAttempt == totalShotsOnGoal
    return GapReason.INTERNAL_INCONSISTENT
```

To bramka **blokująca cały mecz dla wszystkich metryk** —
`samples.py:229-231` robi `if ident_gap: collected[metric] = ident_gap`
dla każdej metryki po kolei. Jeden nieudany rachunek strzałów kasuje z próbki
także narożne, kartki, spalone i faule tego spotkania.

Zmierzone, kto blokuje: ze 99 zablokowanych meczów **94 to ta jedna bramka**
(3 tenis, 2 połówki z listingu). Więc to ona jest całym zjawiskiem.

### Dowód, że tożsamość jest po prostu nieprawdziwa

Rozkład rozbieżności `total − (on+off+blocked)` jest nieprzypadkowy:

| rozbieżność | przypadków |
|---|---|
| **+1** | **171** |
| +2 | 22 |
| +3 | 1 |
| −1 | 3 |

Małe dodatnie liczby całkowite. A w payloadach jest osobny klucz, którego
tożsamość nie uwzględnia: **`hitWoodwork`, obecny w 507 payloadach.**
Wszystkie obejrzane przykłady mają go niezerowego. Czyli strzał w słupek
jest u Sofascore czwartą kategorią, a rachunek liczy trzy.

### Ale poprawka „dodaj poprzeczkę" też jest zła — i to jest sedno

Sprawdziłem trzy sformułowania na tych samych 580 meczach:

| reguła | zablokowanych | odsetek |
|---|---|---|
| **dzisiejsza**: `base == total` | **177** | **30,5%** |
| `base + hitWoodwork == total` | 70 | 12,1% |
| **tolerancja**: `abs(total − base) <= hitWoodwork` | **8** | **1,4%** |

**KOREKTA (2026-09-18, przy naprawie).** Powtórzyłem ten pomiar na
**1 797** zbuforowanych meczach zamiast 580 i liczby wyszły inne. Wniosek
się nie zmienia — wzmacnia się:

| reguła | zablokowanych | odsetek |
|---|---|---|
| dzisiejsza: `base == total` | 381 | **21,2%** |
| `base + hitWoodwork == total` | 391 | **21,8%** |
| tolerancja: `abs(total − base) <= hitWoodwork` | **36** | **2,0%** |

Dwie poprawki do wpisu powyżej. Po pierwsze, skala przesady to **10×**,
nie 22× (21,2% wobec 2,0%). Po drugie — i to jest ważniejsze —
**„plus poprzeczka" jest na tej próbce *gorsze* od dzisiejszego kodu**
(391 zablokowanych wobec 381), a nie dwa i pół raza lepsze. Teza wpisu
(„oczywista poprawka też jest zła") okazuje się mocniejsza, niż była
napisana: ta reguła nie poprawia niczego, tylko przenosi blokady z jednych
meczów na inne. Rozkład reszt na tej próbce: `{-2: 1, -1: 23, 0: 3165,
+1: 347, +2: 52, +3: 5, +4: 1}` — ujemne reszty istnieją i potwierdzają
niekonsekwencję Sofascore co do podwójnego liczenia.

Obciążenie kierunkowe potwierdzone i **usunięte przez poprawkę**:

| | przed (mediana) | po (mediana) |
|---|---|---|
| strzały: zablokowane vs zachowane | **25,0 vs 24,0** | 22,5 vs 24,0 (n=36) |
| narożne: zablokowane vs zachowane | **10,0 vs 9,0** | **9,0 vs 9,0** |

Czyli systematyczne wypadanie meczów ofensywnych zniknęło.

Dodanie poprzeczki na sztywno zostawia 70 zablokowanych z resztami
**ujemnymi** (−1 w 62 przypadkach, −2 w 11) — czyli tam poprzeczka jest
**już wliczona** w jedną z trzech kategorii (najpewniej w strzały niecelne).
**Sofascore jest niekonsekwentny co do tego, czy `hitWoodwork` jest
podwójnie liczony**, więc żadna tożsamość dokładna nie jest powszechnie
prawdziwa. Właściwe jest ograniczenie rozbieżności **do liczby strzałów
w słupek** — wtedy oba warianty konwencji przechodzą.

Pozostałe 8 to prawdziwe błędy danych: `hitWoodwork = 0`, a rozbieżność ±1
lub 2. Dokładnie to, co bramka ma łapać. **1,4% zamiast 30,5% — bramka
odrzuca dziś 22 razy więcej, niż powinna.**

### Dlaczego to nie jest zwykła utrata danych

Odrzucenie jest **obciążone kierunkowo**, bo strzał w słupek koreluje
z liczbą strzałów. Zmierzone:

| | zablokowane | zachowane | różnica |
|---|---|---|---|
| mediana `shots_total` | **25,0** | 23,0 | **+2,0** |
| mediana `corners_total` | **10,0** | 9,0 | **+1,0** |
| średnia `shots_total` | 24,73 | 23,56 | +1,17 |

Z próbki wypadają systematycznie mecze **bardziej ofensywne**. Średnia
`shots_total` liczona na tym, co zostało, jest przez to zaniżona o ~0,35
strzału (~1,5%) względem pełnej populacji. To niewiele, ale jest
**jednokierunkowe**, a przy liniach na strzały i narożne jednokierunkowe
przesunięcie jest dokładnie tym rodzajem błędu, który nie znika w praniu.

Większym kosztem jest jednak samo pokrycie: wyrzucenie ~30% kwalifikujących
się meczów skraca próbki i wypycha fixture'y pod `min_sample=5`, czyli
zamienia wierszy gotowe na `NOT_READY`. Tego nie zmierzyłem osobno —
oznaczam `PODEJRZENIE`.

### Poprawka

```python
gap = abs(s_tot - (s_on + s_off + s_blk))
if gap > stats.get("hitWoodwork", (0.0, 0.0))[side]:
    return GapReason.INTERNAL_INCONSISTENT
```

Do rozważenia osobno: czy `ident_gap` musi kasować **wszystkie** metryki.
Dziś 94 z 99 blokad pochodzi z rachunku strzałów, który leży w tym samym
payloadzie co narożne i kartki, więc blokowanie całości jest spójne i tej
części **nie** krytykuję. Warto to jednak przemyśleć dla bramki na połówki
z listingu, która dotyczy innego payloadu (dziś tylko 2 przypadki, więc
sprawa teoretyczna).

**Test:** mecz z `total=8, on=3, off=3, blocked=1, hitWoodwork=1` musi
przejść (dziś **failuje z właściwego powodu** — jest blokowany); mecz
z `total=10, on=9, off=1, blocked=1, hitWoodwork=0` musi być zablokowany.
Oba przypadki wzięte z prawdziwych payloadów (`13531730`, `14195525`).

---

## F29 · P0 · `fold()` nie usuwa polskiego „ł" — rynki połówkowe trafiają na próbkę **całego meczu**

**POTWIERDZONE** (2026-09-18): mechanizm przez wywołanie prawdziwych funkcji,
skala przez pomiar na 290 fixture'ach piłkarskich, prawdziwe nazwy rynków
pobrane z Superbetu.

### Przyczyna: jedna litera

`market_mapper.fold()` usuwa znaki diakrytyczne przez rozkład NFD i odrzucenie
znaków łączących. To działa dla `ó ż ę ą ś ć ń ź`, bo każdy z nich rozkłada
się na literę + znak łączący. **Nie działa dla `ł`**, bo `ł` (U+0142) nie ma
takiego rozkładu — jest jednym, niepodzielnym punktem kodowym:

```
'ó': NFD=2 znaki -> fold daje 'o'    ✓
'ł': NFD=1 znak  -> fold daje 'ł'    ✗
```

Sprawdzone tą samą pułapką: `đ`, `ø`, `ı` też przechodzą nietknięte.

Skutkiem są **klucze słownika, do których nie da się dojść**, bo wszystkie
zawierają „polowa" lub „strzalow", a Superbet pisze „połowa" i „strzałów":

| klucz w `MATCH_MARKET_NAMES` | docelowa metryka | osiągalny? |
|---|---|---|
| `1.polowa - liczba goli` | `goals_1h_total` | **nie** |
| `1. polowa - liczba goli` | `goals_1h_total` | **nie** |
| `2.polowa - liczba goli` | `goals_2h_total` | **nie** |
| `2. polowa - liczba goli` | `goals_2h_total` | **nie** |
| `liczba celnych strzalow` | `shots_on_target_total` | **nie** |
| `liczba strzalow` | `shots_total` | **nie** |

Potwierdzone bezpośrednio: `classify_market("Liczba celnych strzałów")`
zwraca **`None`**.

### Co się dzieje zamiast tego

Nazwa nie trafia w słownik, spada więc do `TEAM_MARKET_PATTERNS`, gdzie wzorzec
`^(?P<team>.+?) - liczba goli$` łapie ją, **traktując „1.połowa" jako nazwę
drużyny**:

```
"1.połowa - liczba goli"                -> ('goals_for', '1.połowa')
"1.połowa - Hapoel Tel Aviv - liczba goli" -> ('goals_for', '1.połowa - hapoel tel aviv')
```

**Żaden kurs się nie gubi** — zmierzone: 398 zaklasyfikowanych kursów przed
i po poprawce fold. To nie jest utrata pokrycia, to **przetrasowanie**:
ze 128 kursów przypisanych do `goals_for` aż **48 to w rzeczywistości
totale połówkowe**.

### Dwa różne skutki, rozdzielone przez próg 70

`run_sheet.determine_side` liczy `token_sort_ratio(subject, nazwa_drużyny)`
i odrzuca wiersz poniżej `SIDE_MATCH_THRESHOLD = 70.0`.

**(a) Totale połówkowe — złapane.** `"1.połowa"` vs nazwy drużyn daje 10–33,
więc wiersz wypada z `NO_MATCHING_EVENT` i komentarzem „subject matches
neither side". Bramka, której docstring mówi wprost „Returning None rather
than defaulting to the home side is the point", robi swoje. Koszt: **każdy
rynek na gole w połowie na całej tablicy jest po cichu pomijany**, a metryki
`goals_1h_total` / `goals_2h_total` — które istnieją i działają — są martwym
kodem.

**(b) Warianty per-drużyna — PRZECIEKAJĄ.** Tu prefiks „1.połowa - " jest
rozcieńczany przez nazwę drużyny, więc podobieństwo rośnie ponad próg:

| subject | podobieństwo | wynik |
|---|---|---|
| `1.połowa - darmstadt` | 62,5 | złapane |
| `2.połowa - wolfsburg` | 66,7 | złapane |
| `1.połowa - bandirmaspor` | 68,6 | złapane |
| **`1.połowa - hapoel tel aviv`** | **73,2** | **przecieka** |
| `1.połowa - ACS Academia de Fotbal Viitorul Cluj` | **86,7** | **przecieka** |

**O tym, czy wiersz przecieka, decyduje długość nazwy drużyny** — im dłuższa,
tym mocniej rozcieńcza prefiks i tym pewniej przekracza próg. To jest
arbitralne i niewykrywalne z artefaktu.

Skala, zmierzona na wszystkich kombinacjach strona×połowa dla 290 fixture'ów
piłkarskich:

| | |
|---|---|
| kombinacji zbadanych | 1 160 |
| złapanych przez `determine_side` | 482 |
| **przeciekających** | **678 (58,4%)** |
| **fixture'ów, których to dotyczy** | **232 z 290** |

Zastrzeżenie: to jest **górna granica**. Liczy, ile kombinacji *przeszłoby*
bramkę; ile faktycznie stanie się wierszem, zależy od tego, czy Superbet
wystawia dla danego meczu rynek na gole drużyny w połowie. W próbce 11
fixture'ów wystawiał go dla kilku. Liczby podobieństwa i mechanizm są
`POTWIERDZONE`; **zrealizowana** liczba złych wierszy to `PODEJRZENIE`.

### Dlaczego to P0: błąd wyceny jest ogromny i idzie w stronę fałszywej wartości

Wiersz powstaje z ceną za linię **połówkową**, a prawdopodobieństwo liczone
z próbki **całego meczu**. Zmierzone mediany z tego samego przebiegu:

| | mediana |
|---|---|
| `goals_for` (cały mecz, jedna drużyna) | **1,00** |
| `goals_1h_for` (połowa, jedna drużyna) | **0,00** |
| `goals_total` | 3,00 |
| `goals_1h_total` | 1,00 |

Model pytany o „powyżej 0,5 gola Hapoelu w pierwszej połowie" odpowiada
rozkładem dla **całego meczu**, czyli dwa razy większym. Wychodzi z tego
„prawie pewne przejście" i fałszywy nadmiar wartości na OVER — dokładnie
ten rodzaj błędu, który sam się promuje na górę kuponu.

### Poprawka

Rozszerzyć `fold()` o odwzorowanie liter, które nie mają rozkładu NFD, przed
normalizacją:

```python
_SINGLETONS = {"ł":"l","đ":"d","ø":"o","ı":"i","æ":"ae","ß":"ss","þ":"th"}
```

To samo naprawia (a) i (b) u źródła: nazwa trafia w słownik i staje się
`goals_1h_total`, a wariant per-drużyna wymaga dodatkowo wzorca
`^(?P<half>[12])\. ?polowa - (?P<team>.+?) - liczba goli$` odwzorowanego na
`goals_1h_for` / `goals_2h_for` (te metryki **istnieją** w `FOOTBALL_METRICS`
i są dziś nieużywane).

Niezależnie warto **zabezpieczyć próg**: `determine_side` powinno odrzucać
subject, który po usunięciu nazwy drużyny zostawia nierozpoznany tekst —
72 znaki „1.połowa - " to nie szum, to zakres rynku.

**Test:** `classify_market("1.połowa - liczba goli")` musi zwrócić
`("goals_1h_total","")`; `classify_market("Liczba celnych strzałów")` musi
zwrócić `("shots_on_target_total","")`; a `determine_side("1.połowa - Hapoel
Tel Aviv", fixture)` musi zwrócić `None` **albo** rynek musi być
zaklasyfikowany jako połówkowy. **Wszystkie trzy failują dziś z właściwego
powodu** — pierwsze dwa dają `('goals_for','1.połowa')` i `None`, trzeci
zwraca `side_a` z podobieństwem 73,2.

---

## F30 · P1 · Podłoga wariancji Poissona rozjeżdża `sets_total` o 16 pp — model żąda kursu 2,46 tam, gdzie uczciwa bramka to 3,83

**POTWIERDZONE** (2026-09-18) na 878 zbuforowanych meczach tenisowych,
z **prawdziwą wartością odniesienia** — rzecz rzadka w tym projekcie
i tu dostępna, bo zmienną da się po prostu policzyć.

### Mechanizm

`engine.predictive_sd` podłoguje wariancję średnią:

```python
var_sample = max(variance, mean)      # podłoga Poissona
var_pred = var_sample * (1.0 + 1.0/n)
```

Dla liczby zdarzeń niezależnych to rozsądne zabezpieczenie przed zbyt ciasną
próbką. Ale `sets_total` w formacie BO3 **przyjmuje dokładnie dwie wartości:
2 albo 3**. Zmierzony rozkład:

```
{2.0: 626, 3.0: 252}
```

Wariancja jest prawdziwie mała (0,2049), a średnia to 2,287. Podłoga
zastępuje więc wariancję liczbą **jedenaście razy większą** i rozmywa rozkład
dwupunktowy w coś, co prawie nie odróżnia 2 od 3.

### Skutek, policzony wobec prawdy empirycznej

| | P(sets > 2,5) | kurs uczciwy | bramka przy marży 1,10 |
|---|---|---|---|
| **empiria (252/878)** | **0,2870** | **3,48** | **3,83** |
| model z podłogą | **0,4466** | 2,24 | **2,46** |
| model bez podłogi (samo sd próbki) | 0,3268 | 3,06 | 3,37 |

**Błąd modelu to +16,0 pp**, z czego **+12,0 pp wnosi sama podłoga**
(sd rośnie z 0,475 do 1,586, czyli 3,34×).

W pieniądzu: model przyjmie zakład po **2,46**, gdy uczciwa cena wymaga
**3,83**. To nie jest utrata wartości — to systematyczne kupowanie kursu
o ponad trzydzieści procent za niskiego, za każdym razem, na rynku, który
Superbet wystawia (widziałem „Liczba setów" z 10 szczeblami w próbce ofert).
Kierunek jest zawsze ten sam: podłoga przyciąga p do 0,5, więc **zawyża
stronę mniej prawdopodobną**, a na BO3 mniej prawdopodobne jest zawsze OVER.

### Gdzie podłoga wiąże, a gdzie nie — i to jest najciekawsze

Zmierzone dla wszystkich 30 metryk (n≥30, przy n=10):

| metryka | wariancja < średnia? | zawyżenie sd |
|---|---|---|
| **`tennis/sets_total`** | tak | **3,34×** |
| `football/xg_total` | tak | 1,53× |
| `football/xg_for` | tak | 1,38× |
| `tennis/tiebreaks_total` | tak (równe) | 1,00× |
| **pozostałe 26** (gole, narożne, kartki, faule, strzały, spalone, asy, DF, gemy) | **nie** | **1,00×** |

**Podłoga nie wiąże ani razu tam, gdzie jest uzasadniona, i wiąże mocno
wyłącznie tam, gdzie jest bezsensowna.** Liczniki zdarzeń piłkarskich
i tenisowych są nadrozproszone (wariancja > średnia), więc `max()` ich nie
dotyka. Dotyka dokładnie dwóch rzeczy, które **nie są** licznikami zdarzeń
niezależnych: liczby setów (zmienna ograniczona) i xG (zmienna ciągła).

### Poprawka — i zastrzeżenie, że sama podłoga to nie całość problemu

Najprościej: nie stosować podłogi Poissona do metryk, które nie są licznikami
— wyłączyć ją dla `sets_total`, `tiebreaks_total` i `xg_*`. To usuwa 12 z 16
punktów błędu.

Ale **pozostałe 4 pp nie znikną**, bo dla zmiennej dwuwartościowej rozkład
normalny jest po prostu złym modelem: `calc_p_central` całkuje dzwon tam,
gdzie są dwa słupki. Uczciwym estymatorem dla `sets_total` jest
**częstość empiryczna** z próbki (albo model set-by-set), nie CDF normalny.
Dopóki tego nie ma, ten rynek lepiej wyłączyć niż wyceniać — i to jest
decyzja operatora, nie poprawka w kodzie.

Dla `xg_*` zawyżenie 1,53× oznaczam `PODEJRZENIE`: xG jest ciągłe i dodatnie,
więc podłoga jest tam konceptualnie nie na miejscu, ale nie mam wartości
odniesienia, żeby powiedzieć, o ile błądzi wynikowe p.

**Test:** `predictive_sd` dla `sets_total` (mean 2,287, var 0,205, n=10) nie
może zwrócić sd większego niż ~0,5; oraz `p_central` dla OVER 2,5 na tej
próbce musi wypaść w granicach kilku punktów od 0,287. **Oba failują dziś
z właściwego powodu** — dziś dają 1,586 i 0,447.

### Ograniczenie skutku — dlaczego P1, a nie P0

**Bramka drabiny blokuje ten wiersz strukturalnie.** Zmierzone na 16 realnych
ofertach tenisowych: **16 z 16 drabin `sets_total` ma dokładnie jeden szczebel
dwustronny (2,5)**. `ladder_centre` wymaga co najmniej dwóch, więc zwraca
`None`, a `run_sheet` wpisuje wtedy `NO_LADDER_CHECK` i wymusza werdykt
**LEAN** — nigdy `VALUE`. Na formacie BO3 ten błąd **nie może** dziś wejść do
kuponu jako singiel.

Komentarz przy tej bramce mówi, że „the ladder gate is the ONLY external check
a live row ever gets" — i tu właśnie zadziałał jako ostatnia linia obrony przed
błędem, którego nie dotyczył.

Dwa zastrzeżenia, które utrzymują wpis otwartym:

1. **Wiersze LEAN nadal niosą złe liczby.** Człowiek czytający arkusz zobaczy
   `p_central = 0,447` przy prawdzie 0,287 i może na tej podstawie podjąć
   decyzję ręcznie. Arkusz jest artefaktem do czytania, nie tylko wejściem
   kuponu.
2. **Na BO5 ryzyko jest żywe.** W Wielkim Szlemie kwotowane są 2,5 **i** 3,5,
   czyli dwa szczeble — drabina staje się mierzalna i `VALUE` znów możliwe,
   już z błędem +16 pp. Dziś wszystkie 194 mecze tenisowe mają `best_of = 3`,
   więc problem jest uśpiony, nie rozwiązany.

### Co przy okazji wyszło **czyste** w silniku

Wszystkie funkcje `engine.py` przetestowane własnościowo, bez zarzutu:

| własność | wynik |
|---|---|
| `p_OVER + p_UNDER == 1` dla tej samej linii niecałkowitej | **0 odchyleń** (poza celowym klamrowaniem 0,05/0,95) |
| linie całkowite = semantyka pushu | `line=2` → OVER od 2,5, UNDER do 1,5; dokładnie 2 nie wygrywa żadnej strony ✓ |
| `p_OVER` nierosnące w linii | ✓ |
| `ladder_centre` odtwarza środek spójnej drabiny | błąd **0,000** dla 2,6 / 9,3 / 23,1 |
| `get_required_odds(p) * p == marża` | dokładnie 1,05 / 1,10 ✓ |
| `predictive_sd` faktycznie dochodzi do `calc_p_central` | ✓ (`run_sheet.py:311,320`) — znany błąd „sd próbki jako sd predykcyjne" tu **nie** występuje |

Odnotowane jako zachowanie projektowe, nie usterka: przy małym `n`
`bar_probability` ściąga p mocno do `market_p` (`w = n/(n+10)`), więc dla
n=3 i `market_p=0,9` p_bar skacze z 0,30 na 0,75. Bramka przestaje wtedy
mierzyć nasze zdanie i mierzy wyłącznie przewagę ceny nad zdevigowaną linią.
To jest spójne i konserwatywne, ale warto wiedzieć, że dla krótkich próbek
kupon jest selektorem ceny, nie modelu.

---

## Weryfikacja filtra zakończeń — poprawny, z jedną możliwością odzyskania danych

**Pułapka „ret" w nazwisku jest zamknięta i sprawdzona.**
`settle.is_completed_event` patrzy wyłącznie na `status.type` / `status.code`,
nigdy na napis z nazwą, a docstring wprost wskazuje historyczny błąd
(`"ret"` w „Berrettini"). Zweryfikowane empirycznie na 39 878 zakończonych
zdarzeniach: odrzucane są **3,0%**, i rozkład powodów jest sensowny.

| odrzucone | n | słusznie? |
|---|---|---|
| tenis `92 Retired` | 499 | ✓ |
| tenis `91 Walkover` | 306 | ✓ |
| tenis `98 Defaulted` | 1 | ✓ |
| piłka `91 Walkover` / `93 Removed` / `92 Retired` / `31 Halftime` | 15 | ✓ |
| **piłka `120 AP` (po karnych)** | **269** | **do przemyślenia** |
| **piłka `110 AET` (po dogrywce)** | **97** | **do przemyślenia** |

### O tych 366 meczach po dogrywce/karnych

Odrzucenie ich jest **słuszne dla metryk zliczających** i chcę to powiedzieć
wprost, bo pierwszy odruch jest odwrotny: mecz po dogrywce trwa 120 minut,
więc jego narożne, kartki i faule są zawyżone o jedną trzecią. Wpuszczenie
takiego meczu do próbki przesunęłoby ją w górę — czyli byłby to błąd tej samej
klasy co F28, tylko w drugą stronę.

**Ale dla goli dane da się odzyskać.** Sofascore trzyma w listingu
`homeScore.normaltime` — wynik po 90 minutach — i kod już go czyta
w `check_identities`. Metryki `goals_*` mogłyby więc brać `normaltime`
i zachować te 366 meczów, zamiast tracić je razem z metrykami zliczającymi.

**Waga: P3.** Kierunek dzisiejszego zachowania jest konserwatywny — tracimy
dane, nie psujemy ich. Zysk to ~1,5% próbek goli piłkarskich, głównie
w rozgrywkach pucharowych, gdzie i tak mamy najmniej obserwacji.

**Test:** mecz ze `status.code=110` i `normaltime` 1:1 przy `current` 2:1
musi dać `goals_total = 2` (z 90 minut), a **nie** 3, i nie może wnieść
obserwacji do `corners_total`. Failuje dziś z właściwego powodu — dziś nie
wnosi nic do żadnej z tych metryk.

---

## F29 / F30 — wzmocnienie: selekcja kuponu **preferuje** właśnie te złe wiersze

**POTWIERDZONE** (2026-09-18) czytaniem `coupon.py` + `run_sheet.py`
i policzone na medianach zmierzonych w tym przebiegu. Dopisane osobno, bo
zmienia to skutek F29 i F30 z „powstaje zły wiersz" na „zły wiersz wygrywa
miejsce w kuponie z dobrym".

Łańcuch jest krótki i domknięty:

```
p zawyżone  ->  p_bar zawyżone  ->  required_odds = 1.10 / p_bar   MNIEJSZE
            ->  surplus = offered_odds - required_odds             WIĘKSZE
            ->  candidates.sort(key=surplus, reverse=True)         WYŻEJ
```

`coupon.py` sortuje kandydatów **malejąco po `surplus`** i przydziela
miejsca po kolei: `MAX_SINGLES=40`, `MAX_PER_FIXTURE=3`, jedna rodzina
mechanizmu na fixture. Wiersz z zawyżonym p ma więc **z definicji** większy
surplus od wiersza poprawnego i zabiera mu miejsce — a dla F29 rodzina jest ta
sama (`goals_for` i `goals_total` to obie `"scoring"`), więc konkurują
bezpośrednio.

### Policzony przykład dla F29

Linia „powyżej 0,5 gola drużyny w 1. połowie", wyceniona na próbce całego
meczu zamiast połówkowej. Obie próbki z tego przebiegu:

| | centre | sd | `p_central` | `required_odds` |
|---|---|---|---|---|
| **źle**: linia 1H na próbce całego meczu | 1,49 | 1,556 | **0,7377** | **1,491** |
| **dobrze**: linia 1H na próbce 1H | 0,64 | 0,877 | 0,5634 | 1,952 |

I skutek przy realnych cenach:

| oferowany kurs | werdykt przy złej próbce | werdykt przy dobrej |
|---|---|---|
| 1,60 | **VALUE** (surplus +0,109) | poniżej bramki (−0,352) |
| 1,70 | **VALUE** (surplus +0,209) | poniżej bramki (−0,253) |
| 1,85 | **VALUE** (surplus +0,359) | poniżej bramki (−0,102) |

Czyli w całym realistycznym zakresie cen zły wiersz jest **fałszywym VALUE**,
a poprawny nie kwalifikuje się wcale. Model żąda 1,49 tam, gdzie uczciwa
bramka to 1,95.

**Korekta do F30, którą muszę tu zrobić:** napisałem najpierw, że zawyżone
p dla `sets_total` „trafi na szczyt listy kandydatów". **To jest nieprawda na
BO3** i dowiedziałem się tego dopiero, mierząc głębokość drabin. Lista
kandydatów w `coupon.py` zawiera wyłącznie wiersze `VALUE`, a `sets_total`
na BO3 nigdy nie osiąga `VALUE`, bo drabina ma jeden szczebel i bramka
drabiny wymusza `LEAN` (patrz F30). Wzmocnienie opisane w tej sekcji dotyczy
więc **F29, nie F30** — a F30 stanie się jego przypadkiem dopiero na BO5,
gdzie drabina ma dwa szczeble.

**Wniosek, który wydaje mi się najważniejszy z całej weryfikacji:** mechanizm
selekcji nie jest neutralny wobec błędu w p. Jest wobec niego
**antyselektywny** — im mocniej p jest zawyżone, tym pewniej wiersz wchodzi
do kuponu. Dlatego F29 i F30 nie da się odłożyć jako „szumu w arkuszu":
to są wiersze, które sam kupon wybiera preferencyjnie.

---

## F31 · P3 · Dwie drobne rzeczy w `coupon.py`

**POTWIERDZONE** czytaniem kodu (2026-09-18). Oba nieszkodliwe dziś,
oba typu „pułapka na następnego czytającego".

**(a) `MAX_PER_MECHANISM_FAMILY_PER_FIXTURE = 1` nie jest nigdzie używane.**
`grep` po `src/`, `scripts/` i `tests/` znajduje **wyłącznie linię
definicji** (`coupon.py:26`). Limit jest zaszyty w warunku
`if family in families`, co na sztywno oznacza „jeden". Zmiana stałej na 2
nie zrobi nic — a wygląda, jakby miała zrobić. Poprawka: albo użyć stałej
(`if len([f for f in families if f == family]) >= MAX_...`), albo ją usunąć.

**(b) `assert row.surplus is not None` na ścieżce produkcyjnej.**
`coupon.py` opiera się na `assert` dla niezmiennika, który komentarz
tłumaczy bramką `ODDS_TOO_LOW` — ale ta bramka pilnuje `offered_odds`, nie
`surplus`. Gdyby wiersz `VALUE` miał `surplus=None`, sortowanie potraktuje
go jako 0,0 i przepuści, a potem `assert` wywróci **cały etap COUPON**.
Do tego `assert` znika przy uruchomieniu z `-O`, więc zabezpieczenie jest
warunkowe. Poprawka: zamienić na jawne odrzucenie wiersza z powodem
(`DroppedRow(row, "NO_SURPLUS")`), spójnie z resztą tego etapu, która
o każdym odrzuceniu mówi wprost.

**Test:** wiersz `VALUE` z `surplus=None` nie może wywrócić `build_coupon` —
ma wylądować w `dropped` z własnym powodem. Failuje dziś z właściwego powodu.

---

## Mierzalność drabin — ile wierszy może w ogóle zostać `VALUE`

**POTWIERDZONE** (2026-09-18) na realnych ofertach Superbetu dla 14 fixture'ów.

Bramka drabiny jest **poprawna i skalowo niezależna** — `run_sheet.py:371`
liczy `l_sigma = abs(centre - lc) / sample_sd`, czyli normalizuje rozjazd
własnym rozrzutem próbki, a nie pasmem ilorazowym. To jest dokładnie ta
postać, której wymaga wcześniejsze ustalenie o skalowej niezależności.
`MAX_LADDER_SIGMA = 1,25`, a `PRICE_GAP` tylko dopisuje notkę i nigdy nie
degraduje — też zgodnie z ustaleniem, że rozjazd ceny adnotuje, a rozjazd
drabiny degraduje.

Pytanie praktyczne jest inne: **jak często da się ją policzyć.** Wymaga co
najmniej dwóch szczebli dwustronnych, między którymi zdevigowane `p_over`
przechodzi przez 0,5.

| | drabin | udział |
|---|---|---|
| **mierzalne** (znaleziono `ladder_centre`) | **33** | **52,4%** |
| mniej niż 2 szczeble dwustronne | 29 | 46,0% |
| ≥2 szczeble, brak przejścia przez 0,5 | 1 | 1,6% |

Czyli **blisko połowa drabin nie może dać `VALUE`** — nie z powodu błędu,
tylko dlatego, że Superbet kwotuje na nich za mało linii dwustronnie.
Rozbicie na rynki pokazuje, gdzie to boli:

| rynek | drabin | mierzalnych |
|---|---|---|
| `games_total` | 8 | **8 (100%)** |
| `goals_total` | 6 | **6 (100%)** |
| `corners_total` | 3 | 2 (67%) |
| `corners_for` | 3 | 2 (67%) |
| `goals_for` | 32 | 15 (47%) |
| **`sets_total`** | **8** | **0 (0%)** |
| **`aces_total` / `aces_for`** | **3** | **0 (0%)** |

`sets_total` i `aces_*` są **strukturalnie niemierzalne** na tym slate'cie:
zmierzone osobno, 16 z 16 drabin `sets_total` ma dokładnie jeden szczebel
dwustronny (linia 2,5), bo na BO3 nie ma innej sensownej linii.

**Dwa wnioski.** Po pierwsze, to jest przypadkowe zabezpieczenie przed F30
(patrz tam). Po drugie, jeśli szerokość kuponu jest wąskim gardłem, to
`goals_for` — 32 drabiny, największa pula — traci ponad połowę swojego
potencjału na tej bramce, i warto by wiedzieć, czy to brak drugiej linii
u Superbetu, czy brak przejścia przez 0,5. Nie rozdzieliłem tych dwóch
przyczyn dla samego `goals_for`; globalnie 46,0% to za mało szczebli,
a 1,6% to brak przejścia, więc niemal na pewno to pierwsze.

---

## Weta i podłoga pokrycia — jedno czyste, drugie bezczynne

### Weta: czysto, i to w trzech punktach, które gdzie indziej zawiodły

`veto.py` + `run_coupon.py` sprawdzone pod kątem trzech znanych pułapek:

| pułapka | jak jest w `sofa` |
|---|---|
| weto dopasowywane po identyfikatorze zależnym od nazwy rozgrywek (przez co cicho nie trafia) | **nie występuje** — kluczem jest `sofascore_event_id`, stabilne id dostawcy |
| weto nie potrafi wskazać zawodnika/strony, więc rozlewa się na wszystkie | **nie występuje** — `market`, `subject`, `line`, `direction` są opcjonalne i `None` znaczy „dowolny"; weto może być dowolnie wąskie |
| weto, które nie trafiło w żaden wiersz, milczy | **nie występuje** — `find_unmatched_vetoes` jest **wywoływane** (`run_coupon.py:171`), logowane i raportowane w kuponie jako sekcja `## UNMATCHED_VETO` |

Ostatni punkt sprawdziłem osobno, bo istnienie funkcji to nie to samo co jej
podłączenie — a lekcją z poprzedniego pipeline'u było właśnie, że cisza jest
usterką.

### Podłoga pokrycia: poprawnie napisana, **dziś bezczynna**

`coverage.py` liczy medianę kroczącą **per sport** (a nie wspólną — co było
przedmiotem osobnego ustalenia), okno 10 przebiegów, próg spadku 40%,
minimum 3 przebiegi historii.

Uruchomiona na dzisiejszym stanie:

```
football  history_runs=0  NO_BASELINE
tennis    history_runs=0  NO_BASELINE
```

Powód: w `runs/sofa/` jest **jeden** katalog przebiegu poza dzisiejszym
(2026-09-17), a i on ma tylko **1 fixture READY dla piłki i 0 dla tenisa**,
bo tamten przebieg zginął w RESOLVE (F11). `MIN_HISTORY = 3`, więc bramka
zwróci `NO_BASELINE` jeszcze przez co najmniej dwa pełne przebiegi.

**To nie jest usterka — to koszt bycia na drugim przebiegu.** Zapisuję, bo ma
dwie konsekwencje, o których łatwo zapomnieć:

1. **`NO_BASELINE` nie jest zapewnieniem.** W najbliższych przebiegach
   podłoga nie powie nic o jakości dopasowania, a wygląda na bramkę, która
   „przeszła".
2. **Ta bramka i tak nie wyłapałaby dzisiejszych znalezisk.** Mierzy *liczbę*
   fixture'ów READY, a F25 (zły mecz), F16 (kobiety nietrafione) i F29
   (przetrasowany rynek) nie zmniejszają tej liczby — F25 wręcz ją
   podtrzymuje, bo dopasowanie „się udało". Podłoga pokrycia chroni przed
   zapaścią ilościową, nie przed cichym pogorszeniem trafności. Na to drugie
   potrzebne są bramki z F25: płeć z nazwy rozgrywek i orientacja stron.

---
---

# Triage drugiego przebiegu (2026-09-18) — skrót

Dziewiętnaście wpisów, F13–F31. Kolejność malejąca po wadze; „dowód" mówi,
czy liczby pochodzą z pomiaru, czy z lektury kodu.

## Blokuje zakłady — naprawić przed następnym kuponem

| # | co | skala | dowód |
|---|---|---|---|
| **F29** | `fold()` nie usuwa „ł" → rynki połówkowe wyceniane na próbce całego meczu; przy dłuższych nazwach drużyn przechodzą bramkę stron | 678 z 1 160 kombinacji, 232 z 290 fixture'ów; przykład: model żąda 1,49 zamiast 1,95 | pomiar + realne nazwy rynków |
| **F25** | mecz męski dopasowany do żeńskiego jako `CONFIRMED` (inny dzień, odwrócone strony); Sofascore nie oznacza drużyn kobiecych sufiksem | 1 z 290; mechanizm ogólny | pełny łańcuch dowodowy |
| **F14** | `migrate()` nie jest wołane w kodzie produkcyjnym → `sofa` nie startuje na czystej bazie, a nowe tabele nigdy nie docierają do żywej | zabiło start przebiegu | awaria + test na czystej bazie |

## Psuje liczby, nie zatrzymuje dnia

| # | co | skala | dowód |
|---|---|---|---|
| **F28** | tożsamość strzałów pomija `hitWoodwork` → odrzuca 30,5% meczów zamiast 1,4%, **kierunkowo** (mecze ofensywne) | mediana odrzuconych: strzały 25 vs 23, narożne 10 vs 9 | pomiar, 580 meczów |
| **F30** | podłoga wariancji Poissona zawyża sd `sets_total` 3,34× → p mylne o +16 pp; dziś blokowane przez bramkę drabiny, żywe na BO5 | 878 meczów, prawda empiryczna 0,287 vs model 0,447 | pomiar z prawdą odniesienia |
| **F21** | ponowienie w `_execute` łapie `RequestsError` z `curl_cffi`, a most rzuca `ProviderError` → **żadnych ponowień od 2026-09-17** | 1 fixture stracony dziś; wyjaśnia śmierć 1. przebiegu | pomiar czasu (30,3 s vs 61 s) |
| **F15** | wyjątek etapu nie jest łapany na żadnym z trzech poziomów → padł cały pipeline, choć nie proszono o `--stop-on-failure` | 5 etapów nie dostało szansy | awaria |
| **F18** | `SOFA_SUMMARY` idzie na buforowane `stdout` → werdykty etapów niewidoczne w trakcie; OFFER zwrócił `FAILED` bez słowa | cały log to 4 linie | awaria |
| **F16** | `(K)` Superbetu normalizuje się na ` w`, a Sofascore niesie `(w)` → skuteczność dla piłki kobiet spada z ~78% do 13% | 47 z 54 nazw nietrafionych, 4 z 27 fixture'ów | pomiar |

## Marnotrawstwo i luki diagnostyczne

| # | co | skala |
|---|---|---|
| **F17** | 404 listingu nie jest zapamiętywany (potrzebny **krótki** TTL, nie wieczny) + tenis pyta `events/next`, które dla niego nie istnieje | 242 z ~870 żądań RESOLVE = 28% |
| **F19** | przedsamplowy OFFER nie ma odbiorcy — SAMPLES pyta Superbet sam; uzasadnienie A4 nie opisuje kodu | ~600 zbędnych żądań/dzień |
| **F22** | `stage` przyszyty do metody klienta → koszt SAMPLES ukryty pod `RESOLVE`; **wygenerował trzy moje błędne twierdzenia** | 8,2% kosztu etapu |
| **F26** | kickoff ITF późniejszy o strefę turnieju, i to on karmi bramkę czasową kuponu | 12 z 12 zgodne z offsetem miasta; 6 fixture'ów zagrożonych |
| **F27** | dwa listingi tego samego meczu → cena nadpisywana „ostatni wygrywa" | 20 fixture'ów; skutku nie dało się dziś wywołać |
| **F23** | przepustowość mostu zależy od widoczności karty — Superbet w tej samej przeglądarce spowalnia pipeline 4× | opóźnienie 155 ms → 1 992 ms |
| **F24** | most wyrzuca nagłówki odpowiedzi — te, które mówią o dławieniu | diagnozę F23 trzeba było robić okrężnie |
| **F13** | `SOFA_RUN_ID` ustawiany za pętlą etapów → F8 bezczynne | każdy wiersz logu miał `run_id: ""` |

## Porządki

| # | co |
|---|---|
| **F20** | żądania do Superbetu logowane jako `stage: "BOARD"` |
| **F31** | `MAX_PER_MECHANISM_FAMILY_PER_FIXTURE` nieużywane; `assert` na ścieżce produkcyjnej |
| — | `has_xg` i `best_of` opisują coś innego, niż sugeruje nazwa (pole meczu rozegranego / liczba połów) |
| — | mecze `AET`/`AP` odrzucane słusznie dla metryk zliczających, ale gole da się odzyskać z `normaltime` (366 meczów) |

## Co sprawdzono i **działa** — żeby nie sprawdzać drugi raz

| obszar | wynik |
|---|---|
| przeciek z przyszłości do próbki | **0** na 615 próbek encji (prawdziwą funkcją kodu) |
| duplikaty fixture'ów | **0** w obie strony |
| orientacja stron | 483 z 484 zgodne |
| deble w próbkach tenisowych | **0** na 6 645 zdarzeń |
| sparingi w próbkach | **0** |
| zero kontra brak | ani jednej metryki z niemożliwym zerem |
| `shots` vs `shots_on_target` | mediany 24 vs 8 — odwzorowanie nieodwrócone |
| arytmetyka `engine.py` | komplementarność, push, monotoniczność, `ladder_centre` (błąd 0,000), marża — wszystko dokładne |
| `predictive_sd` dochodzi do `p_central` | tak — znany błąd „sd próbki jako predykcyjne" **nie** występuje |
| bramka drabiny | skalowo niezależna (`/sample_sd`), nie pasmo ilorazowe |
| pułapka „ret" w nazwisku | zamknięta, sprawdzona na 39 878 zdarzeniach |
| weta | klucz stabilny, dowolnie wąskie, nietrafione **raportowane** |
| bramki, które złapały prawdziwy błąd | `determine_side` (F29a), drabina (F30), per-fixture catch w `samples.py` (F21), kickoff+przeciwnik (wszystko poza F25) |

## Czego **nie** zweryfikowano

- **SHEET i COUPON na *dzisiejszym* slate'cie** — `03_samples.json` nie
  istniał w trakcie weryfikacji. Natomiast **prawdziwy kod obu etapów został
  uruchomiony end-to-end na danych syntetycznych** w odizolowanym
  `SOFA_RUNS_DIR` i przeliczony ręcznie co do ostatniej cyfry — patrz sekcja
  poniżej. Czego brakuje, to potwierdzenia na realnej skali i realnych
  ofertach.
- **`xg_*` a podłoga wariancji** — zawyżenie 1,53× potwierdzone, wpływ na p
  nie, bo brak wartości odniesienia.
- **Częstotliwość F25 w innych dniach** — dziś 1 z 290; nie wiem, ile jest
  w weekend, gdy ligi męskie i żeńskie grają równolegle.
- **Czy F27 realnie przestrzeliwuje cenę** — dziś ani jedna para listingów
  nie była jednocześnie żywa.


---

## Weryfikacja SHEET → COUPON end-to-end (prawdziwy kod, dane syntetyczne)

**POTWIERDZONE** (2026-09-18). Uruchomione w osobnym `SOFA_RUNS_DIR`
w katalogu tymczasowym, żeby nie kolidować z trwającym przebiegiem. Wejście:
jeden fixture piłkarski, `goals_total` z 10 obserwacjami na stronę
(20 meczów, średnia 3,0), drabina czterech szczebli dwustronnych wyceniona
mniej więcej uczciwie.

`run_sheet` wygenerował 8 wierszy (4 linie × 2 kierunki). **Każda liczba
przeliczona ręcznie i zgodna:**

| wielkość | wartość z kodu | rachunek sprawdzający |
|---|---|---|
| `sample_size` | 20 | 10 + 10, obie strony z różnych meczów |
| `sample_sd` | 1,1239 | Σd² = 24, /19 = 1,263, √ = 1,124 ✓ |
| `p_central` OVER 1,5 | 0,8010 | sd_pred = √(3,0·1,05) = 1,7748; z = 1,5/1,7748 = 0,845; Φ = 0,8009 ✓ |
| komplementarność | 0,8010 / 0,1990 | suma **1,0000** ✓ |
| symetria wokół środka | p(OVER 3,5) = p(UNDER 2,5) = 0,3891 | 2,5 i 3,5 są równo odległe od 3,0 ✓ |
| `market_p` OVER 1,5 | 0,7707 | (1/1,22)/((1/1,22)+(1/4,10)) ✓ |
| `ladder_centre` | 2,8723 | interpolacja 2,5→3,5 przy p 0,5814→0,3627 ✓ |
| `ladder_sigma` | 0,1137 | \|3,0 − 2,8723\| / **1,1239** ✓ — dzielnikiem jest sd **próbki** |
| `p_bar` | 0,7909 | w = 20/30; 0,6667·0,8010 + 0,3333·0,7707 ✓ |
| `required_odds` | 1,3908 | 1,10 / 0,7909 ✓ |
| `edge` | 0,0303 | 0,8010 − 0,7707 ✓ |
| `surplus` | −0,1708 | 1,22 − 1,3908 ✓ |

Wszystkie 8 wierszy wyszło `BELOW_BAR` — poprawnie, bo drabinę wyceniłem
uczciwie, więc żaden szczebel nie bije marży 10%. **Uczciwa drabina nie
produkuje VALUE** i to jest właściwy wynik, nie brak działania.

Następnie podniosłem OVER 2,5 z 1,62 na 2,30 (wymagane było 1,830):

```
SHEET:  {"BELOW_BAR": 7, "VALUE": 1}
COUPON: {"selected": 1, "value_rows": 1, "dropped": 0}
```

Dokładnie jeden wiersz stał się `VALUE` i kupon go wybrał. Po zmianie ceny
przeliczyły się też `market_p` (0,5814 → 0,4945) i `ladder_centre`
(2,8723 → 2,480), a `ladder_sigma` wyniosła 0,463 — poniżej progu 1,25,
więc bramka drabiny przepuściła. Spójnie.

### Dwie rzeczy warte odnotowania z samego artefaktu

**Ślad audytowy jest generowany z własnych liczb rachunku**, a nie opisywany
słowami obok:

```
- n=20, średnia=3.000, sd=1.124 → środek 3.000
- środek drabiny=2.480, ladder_sigma=0.463, ograniczenie progu: none
- 1.9227 = 1.10 / 0.5721; nadwyżka 2.30 − 1.9227 = +0.3773
```

To jest dokładnie ta postać, przy której notka nie może zaprzeczyć swojej
arytmetyce — wielkości w uzasadnieniu **są** wielkościami z obliczenia.

**Nieustawione stałe są widoczne w wierszu**, nie ukryte:
`UNFITTED_CONSTANTS: K_CENTRE, K_PRICE, MAX_LADDER_SIGMA`. Przebieg jedzie na
wartościach domyślnych i **mówi to wprost** przy każdym wierszu — czyli
kalibracja nie jest udawana. Warto o tym pamiętać przy czytaniu dzisiejszego
kuponu: żadna z trzech stałych nie jest jeszcze dopasowana do danych.

---

## Awarie żądań w tym przebiegu — dwie, obie tej samej natury

**POTWIERDZONE** pomiarem na logu (2026-09-18).

| # | czas UTC | trasa | `elapsed_ms` | odstęp w logu | skutek |
|---|---|---|---|---|---|
| 1 | 09:54:51 | `event/16779467/statistics` | 30 003 | 30,3 s | fixture → `BLOCKED` |
| 2 | 10:55:52 | `event/14083156/statistics` | 30 115 | 30,5 s | fixture → `BLOCKED` |

**2 awarie na 10 804 żądania = 0,019%.** Obie na `/statistics`, obie dokładnie
na 30-sekundowym limicie mostu (`bridge_timeout = max(timeout, 30.0)`), obie
z `breaker_state: CLOSED`, po obu etap poszedł dalej w ciągu 40–700 ms.

Trzy rzeczy, które to potwierdza:

1. **Wzorzec F11 działa** — dwa razy z dwóch. Koszt to jeden fixture, nie dzień.
2. **F21 potwierdzone po raz trzeci** — odstęp w logu to ~30 s, a nie ~61 s
   (30 s + 1 s `sleep` + 30 s), czyli ponowienia **nie było** ani razu.
3. **Timeout 30 s jest 200× dłuższy niż typowa odpowiedź** (mediana
   `/statistics` to ~150 ms). Przy działającym ponowieniu oba fixture'y
   najpewniej by się uratowały.

### Korekta do interpretacji progu breakera

Chciałem zapisać, że po dwóch awariach jesteśmy „jedną od progu" (`threshold=3`).
**To jest nieprawda** i warto to mieć na piśmie, bo licznik wygląda na
kumulacyjny, a nie jest:

```python
def record_success(self) -> None:
    self.failures = 0          # ← każdy sukces zeruje licznik
```

`CircuitBreaker.failures` zlicza porażki **następujące po sobie**. Obie nasze
awarie były odosobnione — po każdej natychmiast przyszedł sukces — więc
licznik szedł 1→0 i 1→0.

**Konsekwencja dla F1:** odosobnione timeouty **nie mają drogi** do
przetestowania stanu półotwartego. Żeby breaker się w ogóle otworzył,
potrzeba **trzech porażek pod rząd**, czyli trwałej awarii mostu — dokładnie
tego, co zabiło pierwszy przebieg. Dwa pojedyncze timeouty tego nie zbliżają,
a odsetek 0,019% mówi, że taka seria jest w normalnych warunkach mało
prawdopodobna. **F1 pozostaje nieprzetestowane i najpewniej takie zostanie,
dopóki most znów nie padnie na dłużej.**

---

## F32 · P0 · `"odds": null` przechodzi bramkę „brak klucza" — OFFER wywraca cały dzień na pierwszym zakończonym meczu

**POTWIERDZONE** (2026-09-18) tracebackiem i pomiarem na żywej ofercie.
**To jest bezpośrednia przyczyna tego, że drugi przebieg nie wyprodukował
kuponu.**

### Błąd

```python
odds_data = self.client.event_odds(su_id)
if not odds_data or "odds" not in odds_data:     # offer.py:20
    continue
...
for item in odds_data["odds"]:                   # offer.py:25  <-- TypeError
```

Traceback, odtworzony:

```
File "src/bet/sofa/offer.py", line 25, in fetch_offers
    for item in odds_data["odds"]:
TypeError: 'NoneType' object is not iterable
```

Bramka pyta, czy klucz **istnieje**. Superbet zwraca klucz **istniejący
o wartości `null`**. `"odds" in odds_data` jest więc prawdą, `continue` nie
wykonuje się, a `for` dostaje `None`.

### Dlaczego to nie jest przypadek brzegowy

Zmierzone na pierwszych 60 fixture'ach dzisiejszego artefaktu:

| postać `odds` w odpowiedzi | wystąpień |
|---|---|
| lista kursów | **1** |
| **`null`** | **68** |
| klucz nieobecny | 0 |

`null` jest postacią **dominującą**, nie wyjątkiem — tak Superbet opisuje mecz,
którego już nie wycenia. A pierwszy fixture w artefakcie (`14810267`,
mecz ekwadorski o 00:00, dawno zakończony) ma dokładnie `"odds": null`,
więc etap ginie **na pierwszym elemencie pętli**, nie dochodząc do żadnego
meczu, który cenę ma.

To wyjaśnia też, dlaczego nie wyszło to wcześniej: błąd odpala się tylko, gdy
na tablicy jest mecz bez kursów. Przebieg 2026-09-17 był mały i wczesny
(1 fixture READY), więc go nie trafił. Dziś, przy 484 fixture'ach i 154
rozpoczętych przed startem OFFER, trafia natychmiast. **Usterka jest zależna
od godziny uruchomienia** — im później w dniu, tym pewniej.

### Ta sama obrona jest obok napisana poprawnie

`samples.py:79`, ten sam payload, ten sam dostawca:

```python
odds = odds_data.get("odds") or []
```

Dlatego **SAMPLES przeszedł na `OK`, a OFFER padł na tych samych danych.**
Dwie kopie tej samej intencji w dwóch plikach, jedna poprawna, jedna nie —
i ta niepoprawna zabrała cały dzienny kupon.

### Skutek na przebiegu

| etap | werdykt |
|---|---|
| RESOLVE | PARTIAL |
| **OFFER (przedsamplowy)** | **FAILED** |
| SAMPLES | **OK** (336 READY z 484) |
| **OFFER (odświeżenie)** | **FAILED** |
| SHEET | FAILED — brak `04_offer.json` |
| COUPON | FAILED — brak arkusza |
| **PIPELINE** | **FAILED** |

SHEET i COUPON nie miały własnej usterki: padły, bo nie dostały wejścia.

### Poprawka

```python
odds_items = (odds_data or {}).get("odds") or []
if not odds_items:
    continue
for item in odds_items:
```

Warto przy okazji rozważyć wyciągnięcie tego do jednej funkcji używanej
i przez `offer.py`, i przez `samples.py`, żeby nie było dwóch kopii bramki,
z których jedna może się zepsuć osobno.

**Test:** `fetch_offers` na fixture'cie, dla którego transport zwraca
`{"odds": None}`, musi zwrócić ofertę z zerem szczebli, **nie** podnieść
wyjątku; a przy drugim fixture'cie z prawdziwymi kursami musi je zwrócić
(czyli: jeden pusty mecz nie kasuje reszty tablicy). **Failuje na dzisiejszym
kodzie z właściwego powodu** — dziś podnosi `TypeError` na pierwszym.

### Powiązanie z F15 i F18

Ten jeden `TypeError` kosztował cały dzień **dlatego**, że trzy inne rzeczy
nie zadziałały:

- **F15** — `run_pipeline` nie ma `try/except` wokół etapów, a OFFER łapie
  `Exception` u siebie i zwraca 2, więc pipeline poszedł dalej z etapami,
  które bez oferty nie mogą działać. Poszedł „dalej", ale w próżnię.
- **F18** — komunikat `'NoneType' object is not iterable` istniał od
  **09:52**, czyli od trzech godzin, ale siedział w buforze `stdout`
  i zobaczyłem go dopiero po zakończeniu procesu. Trzy godziny SAMPLES
  przeliczyło się na oczach diagnostyki, która milczała o tym, że kuponu
  i tak nie będzie.
- **F19** — gdyby przedsamplowy OFFER był bramką (a nie martwym etapem,
  którego nikt nie czyta), jego `FAILED` mógłby zatrzymać przebieg przed
  trzema godzinami zbierania próbek albo przynajmniej krzyknąć.

**To jest najlepszy argument z całego przebiegu za naprawą F18 w pierwszej
kolejności.** Sama w sobie jest tylko luką diagnostyczną; w praktyce ukryła
błąd P0 na trzy godziny.

---

## F29 — pełna skala po zakończeniu przebiegu: **osiem** martwych odwzorowań, potwierdzonych artefaktem

**POTWIERDZONE** (2026-09-18) na `03_samples.json` z pełnego przebiegu
(484 fixture'y) plus bezpośrednim testem `classify_market`.

Pierwotnie policzyłem cztery nieosiągalne klucze. Po przejrzeniu **wszystkich**
nazw rynków Superbetu jest ich więcej — pułapka `ł` trafia w każdą nazwę,
która to „ł" zawiera, a zawierają je „połowa", „strzałów" i „błędów":

| metryka | nazwa u Superbetu | `classify_market` zwraca |
|---|---|---|
| `goals_1h_total` | `1.połowa - liczba goli` | `('goals_for','1.połowa')` ✗ |
| `goals_2h_total` | `2.połowa - liczba goli` | `('goals_for','2.połowa')` ✗ |
| `shots_total` | `Liczba strzałów` | **`None`** |
| `shots_on_target_total` | `Liczba celnych strzałów` | **`None`** |
| **`double_faults_total`** | **`Liczba podwójnych błędów`** | **`None`** |
| `shots_for` | `Liczba strzałów <drużyna>` | **`None`** |
| `shots_on_target_for` | `Liczba celnych strzałów - <drużyna>` | **`None`** |
| **`double_faults_for`** | **`<gracz> liczba podwójnych błędów`** | **`None`** |

Kontrola negatywna: te same wzorce **działają**, gdy poda się im wejście bez
`ł` — `"liczba celnych strzalow - Wolfsburg"` daje
`('shots_on_target_for','wolfsburg')`. Czyli wzorce są dobre, psuje je
wyłącznie `fold()`.

### Potwierdzenie z artefaktu: 15 z 30 metryk nie powstało **ani raz**

Na 484 fixture'ach zadeklarowane są 30 metryk, a realnie powstało **15**:

```
nigdy nie powstały: cards_for, cards_total, double_faults_for,
double_faults_total, goals_1h_for, goals_1h_total, goals_2h_for,
goals_2h_total, shots_for, shots_on_target_for, shots_on_target_total,
shots_total, tiebreaks_total, xg_for, xg_total
```

**Dziesięć z tych piętnastu to bezpośrednie ofiary `ł`** (osiem z tabeli
powyżej plus `goals_1h_for` i `goals_2h_for`, które dodatkowo nie mają
własnego wzorca). Pozostałe pięć ma inne przyczyny i **nie są usterką**:

- `cards_for` / `cards_total` — żadna nazwa Superbetu na nie nie wskazuje;
  `Liczba kartek` jest odwzorowana na `cards_points_total`. Metryka oparta na
  `yellowCards` istnieje, ale nic jej nie wycenia. **Do decyzji, czy w ogóle
  ma zostać** — zwłaszcza że wcześniej ustalono, iż Superbet liczy też
  czerwone, więc `cards_points_*` jest tu właściwym wyborem.
- `tiebreaks_total` — Superbet nie wystawia takiego rynku.
- `xg_total` / `xg_for` — Superbet nie wycenia xG.

### Co to zmienia w ocenie

Nie chodzi tylko o przetrasowane rynki połówkowe. **Osiem odwzorowań nie
działa wcale**, w tym trzy rodziny rynków, które realnie się obstawia:
strzały, strzały celne i podwójne błędy. Przy ustaleniu, że wąskim gardłem
kuponu jest szerokość, a nie cena, to jest jedna z najtańszych poprawek
o największym zwrocie w całym dokumencie — jeden słownik znaków.

**Test (rozszerzony):** parametryzowany po ośmiu nazwami z tabeli; każda musi
dać właściwą metrykę. Dziś **wszystkie osiem failuje z właściwego powodu**.

---

## F35 — clamp `[0.05, 0.95]` stał się roszczeniem wartości w ogonie

**Status: NAPRAWIONE** (`OUTSIDE_MODEL_RESOLUTION`). Znalezione przez audyt
kuponu z Części 4, **nie przez test** — i to jest tu najważniejsze. Każdy test
jednostkowy `calc_p_central` przechodził, bo funkcja robiła dokładnie to, co
obiecywała w docstringu.

### Dowód

Na kuponie z 2026-09-18 **33 z 40** wierszy miały `p_central` przyklejone
dokładnie do 0.05. Wiersz na szczycie:

```
Espanyol - Elche: goals_for elche 6.5 OVER @ 150.0
  p_central = 0.05, market_p = None, p_bar = 0.05
  required_odds = 1.10 / 0.05 = 22.0
  surplus = 150.0 - 22.0 = +128.0
```

Model twierdzi, że Elche strzela siedem goli **raz na dwadzieścia meczów**.

### Mechanizm, nie dzień

Clamp powstał, żeby jednomyślna próbka dziesięciu nie ogłaszała pewności. To
jest dobry powód, żeby **odmówić podania liczby** — i zły powód, żeby podać
zamiast niej 0.05. Wartość po clampie nie jest tańszym oszacowaniem; jest
komunikatem „to pytanie jest poza moją rozdzielczością". Wyceniona, staje się
twierdzeniem, że każda niemożliwość zdarza się raz na dwadzieścia razy.

Kupon sortuje po `surplus`, a `surplus` rośnie wraz z zawyżeniem `p`. Podłoga
zawyża `p` o największą dostępną marżę, więc trafia na szczyt listy. Zagęszczenie
zmierzone na trzech etapach:

| etap | wiersze z clampem |
|---|---|
| cały sheet | 649 / 12258 = **5.3%** |
| VALUE | 135 / 1055 = **12.8%** |
| kupon | 33 / 40 = **82.5%** |

Rozstrzygająca jest **asymetria**: sufit 0.95 dał **0** wierszy VALUE, podłoga
dała 135. Clamp jest symetryczny w formie i jednostronny w skutkach, bo sufit
*zaniża* surplus. To odróżnia usterkę od dnia z dobrymi okazjami.

### Dlaczego nie obniżenie podłogi

Obniżenie clampu do np. 0.001 jest poprawką pozornie oczywistą i gorszą:
pozwoliłoby rozkładowi normalnemu wyceniać skrajny ogon rozkładu **zliczeń**,
gdzie przybliżenie normalne jest bezwartościowe. Zamieniłoby liczbę widocznie
absurdalną na niewidocznie błędną. Rung poza pasmem jest **odrzucany**, tak jak
odrzucana jest próbka samych zer (`ALL_ZERO_SAMPLE`) — z zapisanym powodem.

Ta sama polityka obowiązuje w `settle.py`, inaczej backtest mierzyłby populację,
która nie trafia na kupon (lekcja z F30).

### Efekt

SHEET: 12258 → 10960 wierszy, 1298 rungów odrzuconych jako
`OUTSIDE_MODEL_RESOLUTION`. VALUE 1055 → 920. Z kuponu zniknęło całe
`goals_1h_total 4.5 OVER` (11 wierszy — pięć goli do przerwy).

**Test:** `test_f35_a_tail_rung_produces_no_priced_row` w `test_sheet.py`, na
ścieżce produkcyjnej. Na starym kodzie failuje z właściwym powodem:
`p_central=0.05, surplus=119.07`.
