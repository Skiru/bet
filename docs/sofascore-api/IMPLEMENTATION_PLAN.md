# Plan implementacji: Sofascore jako provider

Status audytu wejściowego: 3 rundy zamknięte, zweryfikowane wobec surowych
logów w `docs/sofascore-api/evidence/` (nie na słowo agenta — zobacz
weryfikację throttlingu, search disambiguation i match-rate w historii tej
sesji). Jedna poprawka do zrobienia przed startem: `REFERENCE.md` sekcja
"Rate Limiting" podaje "~87 req/s" dla testu ze 100 workerami; policzone
bezpośrednio z `evidence/rate_limit_test_log_100w.jsonl` (min/max timestamp
na 1000 unikalnych URL-i) daje **~550 req/s**. Log jest wewnętrznie spójny
(średni `elapsed_seconds` × liczba workerów się zgadza), więc popraw liczbę w
dokumencie na podstawie logu, nie odwrotnie.

## 0. Decyzja architektoniczna: jeden repo, nowy moduł, fazowany rollout

Nie nowe repo. Silnik p_low/p_central/bar-basis, backtest, coupon builder i
kontrakty agentów analitycznych są source-agnostic i mają za sobą dziesiątki
naprawionych błędów (corroboration bias, ladder scale-free checks,
cross-match arithmetic — cała historia w pamięci projektu). Duplikowanie ich
w nowym repo to albo przepisanie od zera z ryzykiem odtworzenia tych samych
błędów, albo kopiuj-wklej, czyli i tak fork.

Sofascore wchodzi jako **nowy provider w istniejącym module**
(`src/bet/simple_stats/providers.py` + nowy `src/bet/api_clients/sofascore.py`),
dokładnie tak jak bzzoiro/ESPN/highlightly już tam są. Rollout jest fazowany,
nie big-bang:

- **Faza 1 (ten plan):** Sofascore jako dodatkowy provider obok bzzoiro/ESPN,
  wyniki widoczne w dossier ale NIE zastępują istniejących źródeł.
- **Faza 2:** po zebraniu ~2 tygodni realnych danych produkcyjnych, backtest
  porównawczy (patrz sekcja 5) rozstrzyga czy Sofascore koreluje/przewyższa
  bzzoiro na tych samych meczach.
- **Faza 3:** dopiero po Fazie 2 rozważ zmianę `PRIMARY_PROVIDER_BY_SPORT` na
  Sofascore i wygaszenie bzzoiro/ESPN dla pokrytych sportów — to już ma
  precedens w tym repo (`football-bzzoiro-only-plan`, pamięć projektu), rób
  to tą samą metodą: przełącznik konfiguracyjny + measured record, nie
  usuwanie starego kodu na starcie.

Nigdy nie retirujemy bzzoiro/ESPN w Fazie 1. Match-rate 80.4% dla piłki
(zmierzone) oznacza, że ~20% fixture'ów i tak potrzebuje fallbacku — to nie
jest błąd do naprawienia przed startem, to jest stały stan, na który
architektura musi mieć odpowiedź od pierwszego dnia.

## 1. Twarde reguły implementacyjne

Te reguły są nienegocjowalne — łamią je dopiero jeśli user je jawnie
zmieni, nie na uznanie implementującego.

### 1.1 Transport
- Wyłącznie `curl_cffi`, `impersonate="chrome124"`, nagłówek
  `Referer: https://www.sofascore.com/`. Żadnego `requests`/`httpx` do
  Sofascore — potwierdzone że zwykłe biblioteki dostają inne traktowanie.
- Klient ma być testowalny bez sieci: ten sam wzorzec co
  `SuperbetClient` (`HTTPTransport` Protocol + wstrzykiwany transport w
  testach) w `src/bet/api_clients/superbet.py`. Skopiuj strukturę tej klasy,
  nie wymyślaj nowej.

### 1.2 Rate limiting — bądź bardziej ostrożny niż wynik testu pozwala
Mierzone: zero blokad przy ~550 req/s burst i 15 req/s sustained przez 90s.
Mimo to:
- **Produkcyjny limit: token-bucket ograniczający tempo do 10-15 req/s, plus
  osobny strop max 20 workerów współbieżnie.** To dwa różne pokrętła, nie
  jedno — sam limit workerów niczego nie ogranicza w czasie (20 workerów
  bez pacingu i tak wybije >100 req/s, jak pokazał log). Nie dlatego że
  test tego wymaga, ale dlatego że to reverse-engineered API bez SLA — jeśli
  Cloudflare kiedyś zaostrzy regułę, chcemy być daleko pod progiem, nie na
  nim. Oba jako **parametry konfigurowalne**
  (`SOFASCORE_TARGET_RPS`, `SOFASCORE_MAX_CONCURRENCY`), nie stałe w kodzie.
- Każdy nie-200/404 (403, 429, timeout, Cloudflare challenge HTML zamiast
  JSON) musi natychmiast: (a) zalogować się jako `data_gap`, (b) po **3
  kolejnych** takich błędach wstrzymać dalsze zapytania do tego providera na
  resztę runu (circuit breaker, wzorzec podobny do istniejącego "provider
  quota self-corrects" w pamięci projektu — sprawdź czy tam jest już
  gotowa implementacja tego wzorca do reużycia zanim napiszesz nową),
  (c) NIE być cichym retry w nieskończoność.
- Realny sufit (~550 req/s) nigdy nie powinien być celem operacyjnym — dzienny
  wolumen pipeline'u to setki zapytań, nie tysiące na sekundę. Jeśli kod kiedyś
  dąży do granicy testu, to sygnał że coś jest źle zaprojektowane (np. brak
  cache'owania team id), nie że trzeba przesunąć limit.

### 1.3 Dopasowanie fixture'u — wyłącznie Algorytm B, z cache'em
Potwierdzone w Problemie #3: dopasowanie idzie po drużynie+dacie, kontekst
turnieju (`roundInfo`, `tournament`, `cupRoundType`) przychodzi z
`/event/{id}` PO dopasowaniu. Implementacja:

1. `split_match_name()` z `superbet.py` (już istnieje, użyj tej samej
   funkcji, nie pisz drugiej) → nazwy drużyn/zawodników z oferty Superbeta.
2. **Cache team id w bazie, nie wyszukuj za każdym razem.**
   **Korekta po weryfikacji kodu (nie ufaj poprzedniej wersji tego akapitu
   bez sprawdzenia — dokładnie ta sama zasada co dla audytu Sofascore):**
   `team_source_aliases` / `TeamSourceAliasRepo` (`src/bet/db/repositories.py`,
   metoda `get_verified_provider_team_id`) to **generyczna, gotowa
   infrastruktura o właściwym kształcie** (team_id → source → provider_team_id,
   z `confidence`/`status`), ale dziś jest używana wyłącznie przez
   `src/bet/enrichment/football_data_foundation/canonical_fixture_resolver.py`
   — **nie przez `simple_stats`**. `simple_stats/superbet_offer.py` dopasowuje
   nazwy zupełnie inną drogą: `bet.discovery.team_aliases`
   (`resolve_team_alias` + `normalize_team_name`), czysto w pamięci, bez
   trwałego cache'u żadnego numerycznego ID providera. W `simple_stats` dziś
   **nie istnieje** mechanizm cache'owania obcego ID.
   Decyzja dla Gemini (do udokumentowania w PR, nie do przemilczenia):
   **(a)** reużyj `TeamSourceAliasRepo` z `source="sofascore"` mimo że to
   cross-subsystem reuse — schemat na to pozwala (kolumny są generyczne,
   `team_id` wskazuje na tę samą tabelę `teams`), i to dużo tańsze niż
   duplikować tabelę, **albo (b)** jeśli reuse okaże się kolidować z
   założeniami `canonical_fixture_resolver.py` (sprawdź jego czytelników
   przed zapisem), zbuduj nową, mniejszą tabelę o tym samym kształcie
   scope'owaną do `simple_stats`. Nie zostawiaj tego bez cache'u — codzienne
   `/search/all` dla tych samych klubów to niepotrzebny ruch.
   **Tenis: cache providera dla pojedynczych zawodników nie ma dziś ŻADNEGO
   odpowiednika w schemacie** (`athletes` jest ESPN-specific:
   `UNIQUE(external_id, sport_id)`, `source DEFAULT 'espn'`, kolumny nie
   pasują do wzorca provider-name→provider-id). To osobna decyzja
   projektowa do rozstrzygnięcia w PR, nie do zgadnięcia teraz.
3. Dla znalezionego team id: `/team/{id}/events/next/{page}` (mecz
   przyszły) lub `/events/last/{page}` (mecz zakończony), przeszukaj strony
   0-2 (nie więcej — jeśli mecz nie jest w pierwszych ~90 wydarzeniach
   drużyny wokół daty meczu, to prawdopodobnie zły team id, nie problem
   paginacji).
4. Dopasuj po `matchDate` (± 1 dzień, timezone-aware — patrz pamięć
   projektu "pipeline-timestamps-are-local-not-utc", ten sam typ błędu tu
   czyha) I stringu przeciwnika (fold + fuzzy próg, analogicznie do
   dedup w `src/bet/discovery/dedup.py`).
5. Brak dopasowania → `data_gap`, **nigdy cichy fallback na zgadywanie
   najbliższego meczu**. Znane, zaakceptowane przyczyny porażki (z
   Problemu #3, nie trzeba ich "naprawiać" na starcie): tłumaczenia nazw
   krajów ("Chiny (K)" vs "China"), drużyny rezerw, bardzo niszowe ligi.
   Loguj przyczynę strukturalnie (enum, nie wolny tekst), żeby dało się
   policzyć rozkład przyczyn porażek w produkcji.

### 1.4 Wyszukiwanie lig — nigdy `results[0]`
Jeśli którykolwiek kod (np. Faza 3 discovery po lidze) używa
`/search/all?q=<liga>`, musi filtrować po `category.country` względem
oczekiwanego kraju z `config/sportdb_competition_map.json`/
`config/espn_competition_map_verification.json`, dokładnie jak
`_sportdb_competition_refs` w `src/bet/simple_stats/providers.py` już to
robi dla innego providera. Zero wyjątków — sam branding "search" sugerujący
że pierwszy wynik jest dobry, nie jest prawdą (dowód:
`evidence/league_search_disambiguation.json`, "championship"→FIFA World Cup).

### 1.5 Kontrakt zwrotny
Każda funkcja fetchująca z Sofascore zwraca `FetchOutcome`
(`src/bet/simple_stats/providers.py`) — `metrics: dict[str, list[ProviderValue]]`
+ `data_gaps: list[str]`. `PROVIDER_NAMES` w `src/bet/simple_stats/contracts.py`
musi dostać nowy literal `"sofascore"` (pydantic strict mode odrzuci wszystko
inne — to jest zamierzone, nie obejście). Żadna funkcja nie rzuca wyjątku na
brak danych — brak danych to `data_gap`, wyjątek to bug.

### 1.6 Zero fabrykowanych danych
To już raz ugryzło ten pipeline (`enrich-fallback-fabricated-stats.md` w
pamięci projektu — hardcoded fallback statystyki spowodowały 43/64 błędnych
VALUE rows). Sofascore's `0.0`/`null`/brakujące pole dla nieopisanej
statystyki (np. `expectedGoals` nieobecne dla amatorskiej ligi) musi zostać
`data_gap`, nigdy nie być interpretowane jako wartość 0.

## 2. Struktura modułu

```
src/bet/api_clients/sofascore.py       # SofascoreClient, curl_cffi, HTTPTransport protocol
src/bet/simple_stats/providers.py      # fetch_sofascore_* funkcje, wzorzec fetch_bzzoiro_*
src/bet/simple_stats/sofascore_match.py  # Algorytm B: team resolve + fixture match + cache read/write
config/sofascore_team_aliases_seed.json  # opcjonalny ręczny seed dla największych klubów (przyspiesza cold start)
docs/sofascore-api/                    # już istnieje — REFERENCE.md, evidence/, ten plan
tests/fixtures/sofascore/              # nowy — kopie realnych evidence/*.json jako fixtures testowe
tests/simple_stats/test_sofascore_match.py
tests/simple_stats/test_fetch_sofascore.py
tests/api_clients/test_sofascore_client.py
```

## 3. Mapowanie pól (Sofascore → nasz schemat)

Zbuduj tabelę jawnie w kodzie (docstring albo stała), nie w głowie:

| Sofascore | Nasze pole | Uwaga |
|---|---|---|
| `event.roundInfo.name` + `cupRoundType` | fixture context (stakes) | wypełnia dziurę z `fixture_context-stakes-never-populate` |
| `event.venue`, `event.referee` | fixture context | jak wyżej |
| `event.previousLegEventId` | fixture context (2-leg tie) | |
| `statistics[].expectedGoals` | nowy `ProviderValue` metric `xg_for`/`xg_against` | NIE istnieje dziś w schemacie — sprawdź czy `canonical_name` już to wspiera zanim dodasz nowy |
| `lineups[].statistics.rating` itd. | per-player metrics | dopiero jeśli jest downstream konsument — nie dodawaj pól bez odbiorcy |
| `odds/1/all` | **nieużywane** | Superbet zostaje jedynym źródłem ceny, nie importuj tego pola do niczego cenowego |

Nie dodawaj pola do `ProviderValue`/`canonical_name`, jeśli żaden istniejący
market/analyst konsument go nie czyta — to dokładnie klasa "over-engineering"
której unikamy (patrz zasady sesji).

## 4. Testy — co musi przejść przed merge

1. **Unit: `SofascoreClient`** — mock transportu (wzorzec z
   `tests/simple_stats/test_superbet_offer.py`), test na status 200/404/timeout,
   test że circuit breaker się aktywuje po N błędach non-200/404 pod rząd.
2. **Unit: dopasowanie fixture'u** — użyj **realnych** plików z
   `docs/sofascore-api/evidence/per_fixture_match_test.json` jako fixture
   testowego (143 piłka + 234 tenis, już mamy oczekiwany wynik per wpis) —
   to jest gotowy regression test, nie trzeba wymyślać nowych przypadków.
   Test przechodzi jeśli match-rate nie spadnie poniżej zmierzonych 80%/98%
   ± mały margines.
3. **Unit: search disambiguation** — `tests/fixtures/sofascore/` z kopią
   `league_search_disambiguation.json`; test że dla każdej z 20 lig w tym
   pliku algorytm wybiera poprawny wpis (po `category.country`), nie
   `results[0]`.
4. **Integration: fetch_sofascore_* → FetchOutcome** — analogicznie do
   istniejących testów `fetch_bzzoiro_*` w `tests/simple_stats/`, z
   nagraną fixturą (VCR-style, nie live call w CI).
5. **Contract: `PROVIDER_NAMES` obejmuje `"sofascore"`, pydantic strict mode
   odrzuca literówkę** — jednoliniowy test, ale musi być, bo to jedyna
   ochrona przed cichym dropem danych.
6. **Zero fabrykacji: property test** — dla dowolnego pustego/brakującego
   pola w evidence fixture, `fetch_sofascore_*` NIGDY nie zwraca `0.0` jako
   `ProviderValue.value` — musi trafić do `data_gaps`. To bezpośrednia
   ochrona przed powtórką `enrich-fallback-fabricated-stats`.

## 5. Backtest porównawczy przed Fazą 3 (bramka do przełączenia primary)

Nie przełączaj `PRIMARY_PROVIDER_BY_SPORT` na Sofascore na podstawie samego
match-rate. Zbuduj (analogicznie do istniejącego harness
`estimator-bakeoff-ladder-yardstick` z pamięci projektu):
- Weź ~2 tygodnie fixture'ów gdzie **oba** providery (bzzoiro i Sofascore)
  dały dane na tej samej metryce.
- Porównaj rozkłady, nie tylko średnie — sample size, spread.
- Ustal próg: Sofascore zastępuje bzzoiro na metrykę/sport tylko jeśli
  koreluje ≥ jakiś próg (do ustalenia z operatorem) I nie zawęża próbki
  (nie chcemy węższej bazy dla rzadkich lig, którymi bzzoiro dziś żyje).

## 6. Co Gemini ma raportować (i jak będę weryfikował)

Ta sesja pokazała trzykrotnie, że deklarowane liczby trzeba sprawdzać wobec
surowych dowodów, nie wobec prozy. Ta sama zasada obowiązuje implementację:

- **Każdy raport z etapu implementacji musi wskazywać plik(i) dowodowe**:
  wynik testu (pytest output zapisany, nie tylko "testy przechodzą"), log
  live-runa na realnym dniu (`runs/<date>/`), diff pokrywający dokładnie to
  co zmieniono.
- **Żadna liczba (match-rate, req/s, coverage %) bez pliku źródłowego**,
  z którego da się ją odtworzyć samodzielnie (tak jak zrobiłem to teraz z
  `rate_limit_test_log_100w.jsonl`).
- Ja weryfikuję każdy etap względem tego planu **przed** przejściem do
  następnego — nie czekam do końca całej implementacji, żeby błąd (jak
  fabrykowane statystyki w przeszłości tego repo) nie zdążył wjechać na
  produkcyjny coupon.

## 7. Kolejność prac (dla Gemini)

1. `src/bet/api_clients/sofascore.py` + testy transportu (sekcja 4.1) —
   **bez** integracji z resztą pipeline'u jeszcze.
2. `sofascore_match.py` (Algorytm B + cache w `team_source_aliases`) +
   regression test na `per_fixture_match_test.json` (sekcja 4.2).
3. `fetch_sofascore_*` w `providers.py`, `PROVIDER_NAMES` update,
   mapowanie pól z sekcji 3 — zacznij od fixture context (najniższe ryzyko,
   największa znana luka: `roundInfo`/`venue`/`referee`), dopiero potem
   statystyki liczbowe.
4. Suchy przebieg na jednym realnym dniu obok istniejącego pipeline'u
   (Sofascore fetch się loguje, ale nic z niego jeszcze nie wpływa na
   coupon) — porównaj `data_gaps` rate z zmierzonym 80%/98%.
5. Dopiero po punkcie 4 rozmowa o Fazie 2/3.
