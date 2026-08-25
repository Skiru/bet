# Plan: prosty pipeline analizy statystyk sportowych (Football + Tennis)

Data: 2026-08-25
Status: zweryfikowany przez trzy niezależne przeglądy (fakty w kodzie + kompletność jako specyfikacji do wdrożenia + spójność wewnętrzna po poprawkach) i uzupełniony o brakujące kontrakty, instrukcje techniczne i plan testów. Gotowy do rozpoczęcia Fazy A.

**Rewizja z 2026-08-25 (druga):** dodano pełne schematy pól dla `EVENT_LIST_V1`/`EVENT_DOSSIER_V1`/`STATS_SHEET_V1`, konkretne formuły (`confidence`, `cross_provider_agreement`, progi `readiness`), źródło linii rynkowych (`STANDARD_MARKET_LINES` — już istnieje w kodzie, nie trzeba go wymyślać), specyfikację współbieżności ENRICH, layout katalogów, konwencję CLI, plan testów oraz naprawiono błąd: metody `*_shadow` w SportDB rzucają wyjątki i nie mają tego samego kontraktu co Highlightly — decyzja poniżej w sekcji 3.

**Rewizja z 2026-08-25 (trzecia):** trzeci przegląd wyłapał błędy, które przetrwały drugą rewizję — naprawione: próg `READY` był nieosiągalny dla tenisa (wymagał 3 priorytetowych metryk, a lista miała tylko 2 — dodano `double_faults_total` jako trzecią); `data_quality` miał inny zestaw wartości niż `readiness`, z którego miał dziedziczyć (ujednolicono); formuła `confidence` nie obejmowała przypadku `NOT_APPLICABLE` (przepisana jako jawna kolejność oceny 1→2→3, bez luk); `hit_rate` mógł dzielić przez zero (dodana reguła: brak próbki = brak wiersza, nie `null`); `google-sports` był używany w tabelach providerów, ale nie było go na liście dozwolonych wartości `ProviderValue.provider` (dodany); zapis wielu metryk dossier do trzech kolumn JSON w `analysis_raw_data` był niejednoznaczny przy odczycie (doprecyzowano: każda kolumna to słownik keyowany nazwą metryki, nie płaska lista); kryterium akceptacji #2 nie miało pokrycia testem obejmującym akurat 3 providerów naraz (dodany `test_three_providers_populate_same_metric`).

## 1. Cel i zakres

**Jedno zdanie:** pipeline zbiera i analizuje surowe statystyki meczowe dla footballu i tenisa, żeby człowiek mógł ręcznie zbudować zakład w Superbet Bet Builder.

**Czego pipeline NIE robi — świadomie i na stałe:**

- nie obstawia, nie tworzy kuponu, nie wykonuje żadnego placementu;
- nie liczy EV, fair odds ani prawdopodobieństwa opartego o kurs;
- nie potrzebuje kursów bukmacherskich do działania — kurs wpisuje człowiek ręcznie w Superbet, poza tym narzędziem;
- nie ma formalnej bramki `REVIEW`/`APPROVE`/`REJECT` jak w poprzedniej wersji planu — wynik to raport do przeczytania, nie decyzja do zatwierdzenia;
- nie zarządza życiem kuponu po jego złożeniu (settlement to zupełnie osobna sprawa, poza zakresem).

To ograniczenie zakresu jest tym, co pozwala pipeline'owi być prostym. Cała złożoność poprzedniej wersji (gate, work orders, hard rules o `bettable`, EV) brała się z tego, że pipeline miał kiedyś prowadzić do automatycznej decyzji bukmacherskiej. Tutaj tej decyzji nie ma — jest tylko dobrze poukładana liczba.

## 2. Flow i kontrakty

```text
DISCOVER -> ENRICH -> ANALYZE
  script     script     script
```

Każdy krok to jeden skrypt, jeden artefakt JSON na wyjściu (`StrictBaseModel` z `src/bet/pipeline/contracts/base.py`, SHA256 per artefakt wg wzorca z `src/bet/pipeline/integration_artifacts.py`), zapisywany automatycznie do bazy (sekcja 8). Nie ma kroku agenta jako bramki decyzyjnej — komentarz agenta AI nad gotowym `STATS_SHEET_V1` to opcjonalna warstwa nad wynikiem, nie kolejny blokujący krok.

### Krok 0: `DISCOVER`

Zbiera listę wydarzeń na dany dzień dla footballu i tenisa, scala duplikaty. Kursy ignorujemy, jeśli źródło je zwraca.

**Źródła** (pełna tabela w sekcji 4.3): The Odds API (główne), Highlightly `discover_matches_result` (drugorzędne, łapie mecze spoza głównych lig), SportDB `get_competition_results_with_evidence` (opcjonalne, per jawnie skonfigurowana liga — wariant `*_with_evidence`, nie `*_shadow`, zgodnie z decyzją o kontrakcie błędów w sekcji 3). Dedup: istniejący `src/bet/discovery/dedup.py` (`DeduplicationEngine.merge()`), bez zmian.

**Schemat `EVENT_LIST_V1`** (lista rekordów, jeden per event):

| Pole | Typ | Wymagane | Przykład / reguła |
|---|---|---|---|
| `event_id` | `str` | tak | `sha256(sport|competition|participants|start_time)` — deterministyczny, stabilny między runami |
| `sport` | `"football" \| "tennis"` | tak | |
| `competition` | `str` | tak | |
| `home_team` / `away_team` | `str \| None` | tak dla football | |
| `player_one` / `player_two` | `str \| None` | tak dla tenisa | |
| `start_time` | `str` (ISO8601 UTC) | tak | |
| `source_ids` | `dict[str, str]` | tak | `{"the-odds-api": "abc123", "highlightly": "456"}` |
| `identity_confidence` | `"CONFIRMED" \| "FUZZY_MATCHED" \| "AMBIGUOUS"` | tak | patrz reguła niżej |
| `status` | `"ACTIVE" \| "BLOCKED_IDENTITY"` | tak | |
| `terminal_reason` | `str \| None` | gdy `BLOCKED_IDENTITY` | np. `"conflicting start_time across sources"` |

**Reguła `identity_confidence`:** `CONFIRMED` — 2+ źródła mają identyczne natywne ID providera po scaleniu; `FUZZY_MATCHED` — scalone wyłącznie po dopasowaniu nazw + czasu; `AMBIGUOUS` → `status=BLOCKED_IDENTITY` — sprzeczna data, uczestnicy albo sport między źródłami, bez automatycznego wyboru "pierwszego" źródła.

**Fail-closed:** pusta lista kończy run statusem `BLOCK_NO_EVENTS` i kodem wyjścia 2 (sekcja 6).

### Krok 1: `ENRICH` — serce tego pipeline'u

Dla każdego eventu pobiera surowe statystyki ze **wszystkich** providerów, którzy dają wartość dla danego sportu (decyzja provider-po-providerze w sekcji 4). Celowo **łączymy** wyniki wielu źródeł zamiast klasycznego fallbacku (próbuj pierwszego, w razie porażki drugiego) — rozbieżność między providerami to informacja dla człowieka, nie błąd do ukrycia.

**Współbieżność (decyzja, nie tylko opis):** wołanie `(event, provider)` to jedna jednostka pracy w `concurrent.futures.ThreadPoolExecutor(max_workers=4)` — wzorzec 1:1 z istniejącym `src/bet/discovery/coordinator.py:EventDiscoveryCoordinator._fetch_all_sources` (`ThreadPoolExecutor(max_workers=3)`, `:169-230`), nie asyncio (w `src/bet` nie ma ani jednego użycia asyncio — trzymamy się istniejącego idiomu). Każde wywołanie owinięte w try/except: **każdy** wyjątek (w tym `SportDBMCPError` i podklasy — patrz sekcja 3) zamienia się w wpis `data_gaps`, nigdy nie przerywa całego runu. Wyczerpanie budżetu jednego providera (np. SerpAPI `MAX_QUERIES_PER_RUN=15`, `google_sports_client.py:111`) oznacza `data_gap` dla pozostałych eventów tylko dla tego providera — reszta providerów i reszta eventów jedzie dalej.

**Schemat `EVENT_DOSSIER_V1`:**

```
event_id: str
sport: str
metrics: dict[str, MetricObservation]   # klucz = kanoniczna nazwa metryki, np. "corners_total"
readiness: "READY" | "PARTIAL" | "BLOCKED"
data_gaps: list[str]                     # np. ["highlightly: HTTP 429 rate limited", "sportdb: brak danych dla player_two"]

MetricObservation:
  canonical_name: str
  team_a_l10: list[ProviderValue]        # ostatnie 10 meczów strony A/gracza 1
  team_b_l10: list[ProviderValue]        # jw. dla strony B/gracza 2
  h2h: list[ProviderValue]

ProviderValue:
  provider: str        # "espn-football" | "highlightly" | "sportdb" | "api-football" | "understat" | "tennis-abstract" | "sackmann" | "espn-tennis" | "google-sports"
  match_id: str         # natywne ID meczu u providera, z którego pochodzi wartość
  match_date: str       # ISO8601
  opponent: str
  value: float
  observed_at: str      # ISO8601 — kiedy MY pobraliśmy tę wartość (nie kiedy odbył się mecz)
```

**Reguła `readiness` (progi, nie tylko słowo):** próg jest identyczny dla obu sportów — "co najmniej 3 priorytetowe metryki" — więc lista priorytetowych metryk musi mieć po 3 pozycje w każdym sporcie, inaczej próg jest nieosiągalny (football: `corners_total`, `cards_total`, `shots_total`; tenis: `total_games`, `aces_total`, `double_faults_total` — trzecia metryka dodana celowo, bo tennis-abstract/sackmann i tak ją zwracają, patrz sekcja 4.2).

- `READY` — co najmniej 2 niezależni providerzy zwrócili dane dla co najmniej 3 priorytetowych metryk sportu;
- `PARTIAL` — co najmniej 1 provider zwrócił dane dla co najmniej 1 priorytetowej metryki;
- `BLOCKED` — zero providerów zwróciło jakiekolwiek dane dla eventu; taki event nie wchodzi do `ANALYZE` (jawny terminal reason, nie ciche pominięcie).

### Krok 2: `ANALYZE`

**Źródło linii rynkowych — już istnieje, nie wymyślamy nowego:** `STANDARD_MARKET_LINES` w `src/bet/stats/market_ranking.py:159-210` definiuje gotowe linie per sport/market (np. football Corners Total `[8.5, 9.5, 10.5, 11.5]`, tenis Total Games `[19.5, 21.5, 22.5, 23.5]`). Dla każdego eventu×marketu testujemy **wszystkie** linie zdefiniowane tam dla danego sportu/marketu, w obu kierunkach (`OVER` i `UNDER`) — pipeline nie zgaduje "właściwej" strony, pokazuje obie, człowiek wybiera.

**Hit-rate — reużyć istniejącą, czystą funkcję:** `compute_hit_rate(values: list[float], line: float, direction: str) -> tuple[int, int, int]` w `scripts/compute_safety_scores.py:357` (zwraca `hits, total, pushes`), zero-coupling, już importowana bezpośrednio (bez manifestu/orchestratora) w `scripts/deep_stats_report.py:31` i `scripts/generate_market_matrix.py:52`. **Nie reużywać** `market_ranking.py`'s `rank_candidates()`/`MarketCandidate` (`market_ranking.py:296,197-219`) — to martwy kod sprzężony ze starymi polami `safety_score`/`ev`/`min_odds`, konstruowany dziś tylko w `tests/conftest.py`. **Nie reużywać** też `rank_markets()` z `compute_safety_scores.py:550` w całości — niesie ze sobą logikę wyboru "najlepszego" marketu i `safety_score`/EV, których ta misja nie potrzebuje; wyciągnąć tylko `compute_hit_rate()` jako czystą funkcję (opcjonalnie: cherry-pick logikę wykrywania fabrykacji/three-way-check z tego samego pliku, jeśli okaże się przydatna — nie jest wymagana do MVP).

**Schemat `STATS_SHEET_V1`** (jeden rekord na event × market × line × direction):

| Pole | Typ | Reguła |
|---|---|---|
| `event_id`, `sport`, `market`, `line`, `direction` | | `market` to kanoniczna nazwa (`corners_total`, `total_aces`, ...) |
| `hits`, `sample_size` | `int` | z `compute_hit_rate()` |
| `hit_rate` | `float \| None` | `hits / sample_size`; jeśli `sample_size == 0`, wiersz dla tego event×market×line×direction **w ogóle nie jest emitowany** (brak danych to brak wiersza, nie wiersz z `null`) |
| `mean`, `median` | `float` | liczone osobno — **średnia nigdy nie zastępuje hit rate**, jedyna zasada przeniesiona wprost z poprzedniej wersji planu |
| `sources` | `list[str]` | providerzy, których surowe wartości weszły do wyliczenia |
| `cross_provider_agreement` | `"AGREE" \| "DISAGREE" \| "SINGLE_SOURCE" \| "NOT_APPLICABLE"` | patrz reguła niżej |
| `confidence` | `"HIGH" \| "MEDIUM" \| "LOW"` | patrz formuła niżej |
| `data_quality` | `"READY" \| "PARTIAL" \| "BLOCKED"` | dokładnie ten sam zestaw wartości co `readiness` dossier dla tego eventu (nie osobny enum) |

**Reguła `cross_provider_agreement`:** dla tego samego meczu historycznego i tej samej kanonicznej metryki — jeśli 2+ providerów zwróciło wartość: `AGREE`, gdy różnica ≤ 1 dla metryk zliczeniowych (wszystkie totale: corners/cards/shots/aces/double_faults/total_games) lub ≤ 5 punktów procentowych dla metryk procentowych (possession, serve%); w przeciwnym razie `DISAGREE` — **obie wartości zostają w `EVENT_DOSSIER_V1` i trafiają do raportu, nigdy nie są cicho uśredniane**. `SINGLE_SOURCE`, gdy tylko jeden provider miał dane dla tego meczu. `NOT_APPLICABLE`, gdy metryka pochodzi tylko ze źródła zagregowanego bez podziału per mecz (np. understat daje `xg_total` zbiorczo).

**Formuła `confidence`** (proste, wytłumaczalne progi w jawnej kolejności oceny — nie model statystyczny):
1. Jeśli `cross_provider_agreement == DISAGREE` lub `sample_size < 5` → `LOW`.
2. W przeciwnym razie, jeśli `sample_size >= 8` → `HIGH`.
3. W przeciwnym razie → `MEDIUM`.

Ta kolejność celowo obejmuje `AGREE`, `SINGLE_SOURCE` i `NOT_APPLICABLE` jednym traktowaniem w krokach 2-3 (bo żaden z nich nie jest sam w sobie problemem jakościowym — problemem jest tylko `DISAGREE` lub za mała próbka), więc żadna kombinacja wejść nie zostaje bez przypisanego poziomu `confidence`.

Sortowanie `STATS_SHEET_V1`: klucz główny `confidence` (HIGH→LOW), klucz drugorzędny `hit_rate` malejąco.

Brak kursu, brak EV, brak pola `bettable` — nie ma zastosowania w tej misji.

## 3. Dlaczego można teraz bezpiecznie włączyć Highlightly i SportDB — i jak obsłużyć ich błędy

Highlightly i SportDB są oznaczone w starym kodzie jako `production_selectable=False` (`enrichment/football_data_foundation/**`, `enrichment/multisport_foundation/**`) — słuszna ostrożność, ale dotyczy frameworku shadow-probe dla **innego** pipeline'u, który miał prowadzić do automatycznych decyzji bukmacherskich. Tu tej decyzji nie ma — jest tylko liczba w raporcie czytanym przez człowieka. Dowody z realnego live-capture (mecz Norwegia-Senegal, MŚ 2026, `tests/fixtures/reports/football_data_foundation/live_response_corpus/run_v3_20260623_131229/`) pokazują, że oba providery zwracają prawdziwe, zgodne ze sobą dane (rożne 5-4, SOT 7-4, xG 2.2/1.72 — identyczne liczby z dwóch niezależnych źródeł).

**Decyzja:** `ENRICH` woła surowe klienty `api_clients/highlightly.py` i `api_clients/sportdb_mcp.py` **bezpośrednio**, z pominięciem całej starej warstwy `football_data_foundation`/`multisport_foundation`. Żadnej flagi w starym kodzie nie trzeba przełączać.

**Naprawiona luka — kontrakt błędów nie jest jednolity, dopóki się o to nie zadba:** `highlightly.py` zawsze zwraca `SourceOperationResult` (nigdy nie rzuca wyjątku na błąd HTTP/API — `_request_with_evidence`, `highlightly.py:160`). `sportdb_mcp.py` ma **dwie równoległe rodziny metod** o różnym kontrakcie: `*_shadow` (`get_match_stats_shadow`, `get_competition_results_shadow`, ...) **rzucają** `SportDBMCPError` i podklasy (`SportDBMCPAuthError`, `SportDBMCPRateLimitError`, `SportDBMCPServerError`, `RequiredPayloadFieldUnknownError`) wprost, nieobsłużone; `*_with_evidence` (`get_match_stats_with_evidence`, `get_competition_results_with_evidence`, ...) normalizują wynik do tego samego `SourceOperationResult`, co Highlightly.

**Decyzja:** `ENRICH` woła wyłącznie warianty `*_with_evidence` SportDB, nigdy `*_shadow`. Dzięki temu jest jeden, jednolity branch obsługi błędów w kodzie ENRICH ("sprawdź `.status`"), zamiast dwóch różnych kontraktów do pilnowania.

## 4. Providerzy: decyzja provider-po-providerze

Zweryfikowane bezpośrednio w kodzie i przez realny live-capture (2026-08-25). Klucze API dla wszystkich providerów poniżej są już skonfigurowane w `.env`.

### 4.1 Football — `ENRICH`

| Provider | Plik klienta | Co konkretnie daje | Decyzja | Akceptacja (test "działa") |
|---|---|---|---|---|
| **ESPN** | `api_clients/espn.py` / `espn_adapter.py` | Najbogatszy zestaw: corners, fouls, yellow/red cards, shots, SOT, possession, passing, crosses, tackles, interceptions, clearances (28 pól, `SOCCER_STAT_MAP:249-277`) | **Włączyć jako pierwsze źródło** — już aktywny w `FALLBACK_CHAINS` | Dla meczu z fixture `live_response_corpus` zwraca niepuste `corners_total` i `cards_total` dla obu drużyn |
| **Highlightly** | `api_clients/highlightly.py` | corners, yellow cards, shots/SOT/blocked, fouls, possession, xG (`STAT_NAME_MAP:25-46`) | **Włączyć**, wołany bezpośrednio (sekcja 3) | Dla meczu Norwegia-Senegal z `live_response_corpus` zwraca `corners_total=5` (dom) / `4` (gość), zgodnie z przechwyconym payloadem |
| **SportDB (Flashscore)** | `api_clients/sportdb_mcp.py`, metody `*_with_evidence` | To samo co Highlightly + red cards + rozbicie na połowy + eventy/składy | **Włączyć**, wyłącznie warianty `*_with_evidence` (sekcja 3) | Dla tego samego meczu zwraca `corners_total=5/4` — zgodne z Highlightly, `cross_provider_agreement=AGREE` |
| **api-football** | `api_clients/api_football.py` | corners, fouls, cards, shots, SOT, possession, saves (`STAT_TYPE_MAP:22-32`) | **Włączyć** jako dodatkowy cross-check | Zwraca niepuste `corners_total` jako trzeci niezależny provider |
| **understat** | `api_clients/understat_client.py` | tylko xG i liczba strzałów, zagregowane | **Włączyć** jako sygnał pomocniczy | Zwraca `xg_total`; brak podziału per mecz jest akceptowalny (`cross_provider_agreement=NOT_APPLICABLE`) |
| **google-sports (SerpAPI)** | `api_clients/google_sports_client.py` | historia H2H (wynik, data, flaga czerwonej kartki) — brak liczb per-statystyka | **Włączyć** jako kontekst H2H, nie źródło do hit-rate | Zwraca listę H2H z co najmniej wynikiem i datą |
| **football-data-org** | `api_clients/football_data_org.py` | `get_fixture_stats()` to pusty stub — zero statystyk meczowych | **Pominąć w tym profilu** — brak wartości dla misji stats-only | n/d |

**Uwaga do naprawienia przy implementacji:** `highlightly.py`'s `STAT_NAME_MAP` (linie 25-46) nie mapuje `Red cards`, mimo że pole istnieje w surowej odpowiedzi providera (`MISSING_TARGET_METRICS`, linia 48) — trafia dziś do `unknown_metrics`. Naprawić przy podłączaniu klienta (red cards to realny market, korelujący z total cards).

### 4.2 Tennis — `ENRICH`

| Provider | Plik klienta | Co konkretnie daje | Decyzja | Akceptacja |
|---|---|---|---|---|
| **tennis-abstract** | `api_clients/tennis_abstract.py` | aces, double faults, first/second serve %, break points saved/faced %, hold%, break%, service/return games | **Włączyć jako pierwsze źródło** — canonical source | Zwraca niepuste `aces_total`/`double_faults_total` dla obu graczy |
| **sackmann** | `api_clients/sackmann_adapter.py` | ten sam zestaw co tennis-abstract, z historycznych CSV ATP/WTA | **Włączyć** — baza historyczna do hit rate | Zwraca te same pola co tennis-abstract dla meczu sprzed >7 dni; świeże mecze mogą jeszcze nie być w CSV — to akceptowalny `data_gap`, nie błąd |
| **espn-tennis** | `api_clients/espn.py` (`_get_tennis_match_stats`) | tylko `sets_won`/`games_won`/`total_sets` | **Włączyć jako baseline** dla `total_games`/`sets` | Zwraca `total_games` nawet gdy tennis-abstract/sackmann jeszcze nie mają danych świeżego meczu |
| **google-sports (SerpAPI)** | `api_clients/google_sports_client.py` | historia H2H setów | **Włączyć** jako kontekst H2H | Zwraca listę H2H z wynikami setów |
| **api-tennis (API-Sports)** | `api_clients/api_tennis.py` | martwy kod — `NXDOMAIN`, `is_available()` zawsze `False` | **Nie włączać** — nieaktywny na poziomie hosta, nie do odblokowania | n/d |

### 4.3 Discovery

| Źródło | Plik | Rola | Decyzja |
|---|---|---|---|
| The Odds API | `discovery/sources/odds_api.py` | główny terminarz, pole `odds` ignorowane | **Włączyć**, bez zmian w kliencie |
| Highlightly (`discover_matches_result`, zapytanie po dacie) | `api_clients/highlightly.py` | łapie mecze spoza głównych lig | **Włączyć** jako drugie źródło discovery |
| SportDB (`get_competition_results_with_evidence`) | `api_clients/sportdb_mcp.py` | terminarz dla jawnie śledzonych lig/sezonów (wymaga slug/id skonfigurowanego ręcznie) | **Włączyć opcjonalnie**, per liga z listy w konfiguracji (prosty YAML/JSON: `{"premier-league": {"country": "england", "season": "2025-2026"}}`) |

### 4.4 Poza zakresem: wszyscy providerzy kursów

**OddsPapi, odds-api-io, api-football-odds oraz pole `odds` z The Odds API — całkowicie poza zakresem tej misji.** Nie liczymy EV, nie potrzebujemy kursów do działania pipeline'u. Zero integracji, zero kodu, zero testów dla tych providerów w tym profilu.

## 5. Taksonomia statystyk — wspólny słownik nazw

ENRICH łączy dane z 4-5 providerów na sport, więc potrzebny jest jeden wspólny zestaw kanonicznych nazw metryk. Każdy klient ma już własną mapę normalizacji: `STAT_NAME_MAP` (Highlightly), `ALLOWED_STAT_MAP` (SportDB), `STAT_TYPE_MAP` (api-football), `SOCCER_STAT_MAP` (ESPN). Zadanie Fazy A: zmapować te cztery na jeden wspólny zestaw kluczy (np. `corners_total`, `cards_total`, `shots_total`, `shots_on_target_total`, `aces_total`, `double_faults_total`, `total_games`) używany w `MetricObservation.canonical_name` — **nie wymyślać piątej, nowej taksonomii od zera**, tylko ujednolicić istniejące cztery. `SPORT_STAT_KEYS`/`SPORT_MARKETS` w `src/bet/stats/market_ranking.py:15-44,144-153` to gotowy punkt startowy dla nazw kanonicznych (są już używane w `normalize_stats.py`, `generate_market_matrix.py`, `build_shortlist.py`).

## 6. Struktura kodu i CLI

**Nowy pakiet, bez rozszerzania starych modułów:**

```
src/bet/simple_stats/
  __init__.py
  contracts.py     # EventListV1, EventDossierV1, StatsSheetV1, MetricObservation, ProviderValue — StrictBaseModel
  providers.py     # cienkie adaptery nad api_clients/*, ujednolicony zwrot (ProviderValue | data_gap) i jednolita obsługa błędów (sekcja 3)
  discover.py      # discover_events(date, sports) -> EventListV1
  enrich.py        # enrich_events(EventListV1) -> EventDossierV1, ThreadPoolExecutor(max_workers=4)
  analyze.py       # analyze_dossier(EventDossierV1) -> StatsSheetV1, używa STANDARD_MARKET_LINES + compute_hit_rate
  persistence.py   # zapis do fixtures/analysis_raw_data/analysis_results (sekcja 8) — nowy, mały writer, nie reużywa football_data_foundation

scripts/
  run_discover.py  # cienki CLI wrapper wołający bet.simple_stats.discover
  run_enrich.py
  run_analyze.py

tests/simple_stats/
  test_discover.py
  test_enrich.py
  test_analyze.py
  test_persistence.py
```

**Konwencja CLI** — wzorowana na istniejącym `scripts/discover_events.py` (plain `argparse`, bez ciężkiej warstwy `--runtime-mode`/ACK-tokenów ze starych `pipeline_steps/sN_*.py`, która należy do frameworku bezpieczeństwa dla automatycznych decyzji bukmacherskich i tutaj nie ma zastosowania):

```bash
run_discover.py --date YYYY-MM-DD [--sports football,tennis] --output-dir PATH [--verbose]
run_enrich.py   --event-list PATH --output-dir PATH [--verbose]
run_analyze.py  --dossier PATH --output-dir PATH [--verbose]
```

Kody wyjścia: `0` = OK (pełne dane), `1` = PARTIAL (są `data_gaps`, ale artefakt powstał), `2` = FAILED (brak artefaktu, np. `BLOCK_NO_EVENTS`). Każdy skrypt drukuje na stdout linię `AGENT_SUMMARY:{json}` z krótkim podsumowaniem liczbowym (ta sama konwencja co `discover_events.py`). Zapis artefaktu przez `write_json_atomic()` z `src/bet/pipeline/run_evidence.py:67` (prosty, bez sprzężenia z manifestem) — nie przez `write_script_evidence()` (sprzężony ze starym manifestem/ID kroków) ani przez gołe `path.write_text()` (niespójne z resztą repo).

## 7. Limity i budżety providerów w ENRICH

- **Trwały budżet per provider (między runami):** reużyć `RateLimiter` z `src/bet/api_clients/rate_limiter.py:102` (thread-safe, plikowy, okna dzienne/godzinne, interfejs `can_request(api_name, cost)`/`record_request(...)`/`get_remaining(...)`) — już wstrzykiwany do klientów przez konstruktor (`GoogleSportsClient.__init__(self, rate_limiter: RateLimiter)`), gotowy do reużycia bez zmian.
- **Limit per run (w ramach jednego wywołania ENRICH):** SerpAPI ma dodatkowo twardy limit `MAX_QUERIES_PER_RUN=15` (`google_sports_client.py:111`), zaimplementowany jako lokalny licznik w pamięci ponad `RateLimiter`. Ten sam wzorzec (licznik per-run + `RateLimiter` pod spodem) zastosować też dla Highlightly i SportDB, z domyślnym limitem **100 wywołań/run na providera** (wystarcza na ok. 20 eventów × 5 zapytań/event przy obu providerach naraz) — do skalibrowania w górę lub w dół po pierwszym dniu pilotażu (sekcja 11, Faza C), gdy będzie znany realny wolumen eventów dziennie.
- **Providerzy webscrapingowi:** `tennis-abstract` (BeautifulSoup) i `sackmann` (surowe CSV z GitHub) nie mają oficjalnego API — pilnować częstotliwości zapytań i cache'ować agresywnie (istniejące TTL w `base_client.py`/`google_sports_client.py` — reużyć, nie wyłączać).

## 8. Baza danych jako source of truth

- `EVENT_LIST_V1` → tabele `fixtures` + `fixture_sources` (już istnieją, `src/bet/db/schema.sql:130-155`, bez migracji).
- `EVENT_DOSSIER_V1` → `analysis_raw_data` (`schema.sql`). `EVENT_DOSSIER_V1.metrics` to `dict[str, MetricObservation]` — wiele metryk na event — więc każda z trzech wolnych kolumn JSON (`team_a_l10_json`, `team_b_l10_json`, `h2h_meetings_json`) przechowuje **dokładne odwzorowanie tego słownika**, nie płaską listę: `{"corners_total": [ProviderValue, ...], "cards_total": [ProviderValue, ...], ...}`, gdzie `team_a_l10_json` odpowiada `metrics[*].team_a_l10`, `team_b_l10_json` odpowiada `metrics[*].team_b_l10`, a `h2h_meetings_json` odpowiada `metrics[*].h2h`. Dzięki kluczowaniu po nazwie metryki przy odczycie nie trzeba zgadywać, do której metryki należy dana wartość. Dla tenisa (brak "drużyny") `team_a_l10_json`/`team_b_l10_json` przechowują analogicznie dane `player_one`/`player_two` — nazwy kolumn zostają bez zmian (są tylko etykietami "strona A"/"strona B" tabeli, nie wymuszają football-owej semantyki). **Nie używamy `fixture_capability_observation`** (`schema.sql:662-700`), mimo że wygląda na pasujące miejsce na lineage: ta tabela ma `team_id INTEGER NOT NULL REFERENCES teams(id)` — twardy wymóg drużyny, a w repo nie ma tabeli `players`, więc tenis singlowy nie zmieściłby się bez naciągania modelu. Dodatkowo jedyni dzisiejsi czytelnicy/pisarze tej tabeli żyją w starym, football-specyficznym stosie (`enrichment/football_data_foundation/canonical_observation_writer.py` i pokrewne), który ten plan świadomie pomija (sekcja 3) — reużycie samej tabeli bez reużycia jej pisarza oznaczałoby ręczne odtwarzanie jej semantyki od zera. Prostsze i tańsze: trzymać lineage w już-elastycznym `analysis_raw_data`.
- `STATS_SHEET_V1` → `analysis_results` (`schema.sql:14-30`) — kolumny `ranking_json`/`stats_summary_json` są wolnym JSON-em bez ograniczeń, `cross_provider_agreement`/`confidence`/`data_quality` wchodzą tam bez migracji.
- **Pominięte celowo:** `gate_results`, `decision_snapshots`, `decision_outcomes`, `bets`, `coupons` — modelują decyzje i wyniki zakładów, których to narzędzie nie podejmuje.

Zapis do bazy **automatyczny** po każdym kroku, przez nowy, mały moduł `src/bet/simple_stats/persistence.py` (sekcja 6) — nie przez `launch_bridge.py`'s `promote_shadow_results()`, bo ten mechanizm i jego allowlist tabel są zbudowane pod tabele decyzji bukmacherskich (`gate_results`, `decision_snapshots`), których tu nie używamy; próba jego reużycia dodałaby z powrotem złożoność, którą ten plan ma unikać.

## 9. Co świadomie usunięto względem poprzedniej wersji planu

| Element poprzedniej wersji | Dlaczego usunięty |
|---|---|
| `REVIEW` (werdykt APPROVE/WATCHLIST/REJECT/BLOCK) | Nie ma decyzji do zatwierdzenia — jest raport do przeczytania |
| `QUOTE_PACK`, `operator_quote`, `bettable`/`not_bettable` | Zero potrzeby kursu w tym narzędziu |
| EV, fair odds, probability-from-odds | Ta misja nigdy nie liczy wartości zakładu, tylko statystykę |
| Human gate S9 jako formalna bramka | Nie ma kuponu do zatwierdzenia |
| Sharding/chunking, work orders, resume, `launch_bridge.py` promote | Zbędna złożoność control-plane nieadekwatna do rozmiaru zadania i tabel, których nie używamy |
| `SportProfile` jako pełny plugin-kontrakt z metodami `review()`; również `pipeline/sports/protocols.py`'s `BaseSportProtocol`/`evaluate_market_readiness()` (`allowed_action: BLOCKED\|ANALYSIS_ONLY\|READY_FOR_PRICING`) | Oba operują na słowniku pojęć z bramki REVIEW/pricing, której tu nie ma; różnica sportowa sprowadza się do tabel z sekcji 4 i słownika z sekcji 5, nie do osobnego interfejsu behawioralnego |

## 10. Plan testów (lekki, ale konkretny)

Reużyć realne przechwycone odpowiedzi z `tests/fixtures/reports/football_data_foundation/live_response_corpus/run_v3_20260623_131229/` (mecz Norwegia-Senegal, Highlightly + SportDB, prawdziwe liczby) jako dane wejściowe zamiast pisać nowe mocki od zera.

- `tests/simple_stats/test_discover.py::test_merges_two_sources_into_one_event` — The Odds API + Highlightly zwracają ten sam mecz, wynik to jeden `EVENT_LIST_V1` z dwoma `source_ids`.
- `tests/simple_stats/test_discover.py::test_ambiguous_identity_blocked` — sprzeczna data/sport między źródłami → `status=BLOCKED_IDENTITY`.
- `tests/simple_stats/test_enrich.py::test_one_provider_failure_does_not_abort_run` — SportDB rzuca `SportDBMCPRateLimitError` w trakcie runu → pozostali providerzy i pozostałe eventy nadal przetworzone, wpis w `data_gaps`.
- `tests/simple_stats/test_enrich.py::test_three_providers_populate_same_metric` — ESPN + Highlightly + SportDB jednocześnie zwracają `corners_total` dla tego samego meczu z `live_response_corpus` → `MetricObservation` ma 3 wpisy `ProviderValue` z różnymi `provider`, `cross_provider_agreement=AGREE`; to bezpośrednie pokrycie kryterium akceptacji #2 z sekcji 12.
- `tests/simple_stats/test_enrich.py::test_disagreement_not_silently_averaged` — Highlightly i SportDB zwracają różne wartości dla `corners_total` tego samego meczu → `cross_provider_agreement=DISAGREE`, obie wartości obecne w dossier.
- `tests/simple_stats/test_enrich.py::test_zero_enrichable_data_yields_blocked` — event bez żadnych danych od providerów → `readiness=BLOCKED`, nie wchodzi do `ANALYZE`.
- `tests/simple_stats/test_analyze.py::test_hit_rate_not_replaced_by_mean` — test regresyjny na `compute_hit_rate()` używany bezpośrednio z realnymi L10.
- `tests/simple_stats/test_analyze.py::test_all_standard_lines_tested` — dla danego marketu w wyniku obecne są wszystkie linie z `STANDARD_MARKET_LINES[sport][market]`, w obu kierunkach.
- `tests/simple_stats/test_persistence.py::test_rerun_is_idempotent` — dwukrotne uruchomienie na tym samym fixture nie duplikuje wierszy w bazie.
- `tests/simple_stats/test_persistence.py::test_tennis_dossier_persists_without_team_id` — test regresyjny na decyzję z sekcji 8 (dossier tenisowy singlowy zapisuje się poprawnie przez `analysis_raw_data`, bez potrzeby `team_id`).

## 11. Wdrożenie (lekkie, trzy fazy)

**Faza A — providerzy i taksonomia:** zmapować `STAT_NAME_MAP`/`ALLOWED_STAT_MAP`/`STAT_TYPE_MAP`/`SOCCER_STAT_MAP` na jeden wspólny zestaw kluczy (sekcja 5); naprawić brak red cards w Highlightly; napisać `src/bet/simple_stats/providers.py` z ujednoliconym kontraktem błędów (sekcja 3, w tym wybór wariantów `*_with_evidence` dla SportDB); przygotować fixture bundle z `live_response_corpus` (reużyć, nie nagrywać nowych).

**Faza B — trzy skrypty + kontrakty + testy:** zaimplementować `contracts.py` (schematy z sekcji 2), `discover.py`/`enrich.py`/`analyze.py`/`persistence.py` oraz CLI wrappery wg sekcji 6; napisać testy z sekcji 10 równolegle z kodem, nie po fakcie.

**Faza C — pilot na żywych danych:** pipeline nie podejmuje żadnej nieodwracalnej akcji (nie stawia zakładów), więc iterować można bezpośrednio na żywych danych od razu po Fazie B, bez wielotygodniowego shadow comparison jak w poprzedniej wersji planu — to był wymóg adekwatny do ryzyka bukmacherskiego, którego tu nie ma. Przejrzeć kilka dni raportów ręcznie i poprawić to, co wygląda źle.

## 12. Kryteria gotowości

- `DISCOVER` znajduje eventy z co najmniej dwóch niezależnych źródeł i poprawnie je scala (sekcja 10, `test_merges_two_sources_into_one_event`);
- `ENRICH` dla przykładowego meczu football pokazuje surowe wartości z co najmniej 3 providerów jednocześnie (ESPN + Highlightly + SportDB), z jawnym `cross_provider_agreement` (sekcja 10, `test_three_providers_populate_same_metric`), i przeżywa awarię jednego providera bez przerywania runu (`test_one_provider_failure_does_not_abort_run`);
- `ANALYZE` pokazuje `hits/sample_size` dla każdej linii z `STANDARD_MARKET_LINES`, nie tylko średnią;
- brak danych od providera kończy się jawnym `data_gap`, nie cichym zerem lub wyjątkiem przerywającym run;
- dossier tenisowy zapisuje się do bazy bez błędu (test regresyjny na decyzję z sekcji 8);
- raport końcowy da się szybko przeczytać i użyć do ręcznego budowania zakładu w Bet Builderze — to jedyny test akceptacyjny, który naprawdę się liczy, bo to jest cel tego narzędzia.

---

## 13. Weryfikacja wdrożenia na żywych danych (2026-08-25)

Ta sekcja jest **dopisana po implementacji**, na podstawie realnych wywołań każdego providera w dniu 2026-08-25. Sekcje 1-12 opisują zamiar; ta sekcja opisuje, co faktycznie działa i które założenia planu okazały się nieaktualne. Wszystkie punkty niżej zostały naprawione w kodzie, chyba że jawnie napisano inaczej.

### 13.1 Założenia planu obalone przez rzeczywistość

| Założenie planu | Co jest naprawdę | Co zrobiono |
|---|---|---|
| §4.3 „The Odds API — **bez zmian w kliencie**" | Miesięczny limit konta wyczerpany (500/500). `/odds` odpowiada `401 OUT_OF_USAGE_CREDITS`, więc DISCOVER zwracał **zero eventów**. Endpoint `/events` jest darmowy (0 kredytów) i zwraca dokładnie pola potrzebne do `EVENT_LIST_V1`. | `OddsAPIEventsAdapter` czyta `/events`. Skoro pipeline i tak ignoruje kursy (§4.4), płacenie kredytu za payload bukmacherski było czystą stratą. |
| §4.3 Highlightly discovery „per liga (league_id/season)" | Endpoint `/matches` przyjmuje zwykły filtr `date` i stronicuje przez `offset` — 167 meczów na 2026-08-25. Ręczna lista lig była niepotrzebna i gubiłaby „mecze spoza głównych lig", czyli jedyny powód istnienia tego źródła. | `HighlightlyDiscoveryAdapter` odpytuje `/matches?date=`. DISCOVER daje **182 eventy, 24 scalone z dwóch niezależnych źródeł** (`identity_confidence=CONFIRMED`) — kryterium gotowości #1 spełnione produkcyjnie. |
| §4.2 sackmann „**Włączyć** — baza historyczna do hit rate" | Repozytorium `github.com/JeffSackmann/tennis_atp` zwraca **404** — zniknęło. Klient zawsze dostaje pustą listę. | Zostawiony w `PROVIDERS_BY_SPORT`; degraduje się do czystego `data_gap`. Traktować jak `api-tennis` z §4.2: martwy upstream, nie do odblokowania po naszej stronie. |
| §4.1 understat „**Włączyć** jako sygnał pomocniczy" | Pakiet `understat` nie instaluje się w tym środowisku (`aiohttp` nie buduje wheela). | Zostawiony; degraduje się do `data_gap`. To sygnał pomocniczy (tylko xG), więc nie blokuje żadnego kryterium. |
| §2 „ENRICH woła Highlightly/SportDB dla bieżącego meczu" | Bieżący mecz jeszcze się **nie odbył** — nie ma z niego statystyk. Wartość tych providerów leży w **historii** (L10 + H2H). | Highlightly: `/last-five-games` + `/head-2-head` → `/statistics/{id}` per mecz historyczny. SportDB: wyniki sezonu ligi → `flashscore_get_match_stats` per mecz. |

### 13.2 Błędy implementacji wykryte tylko na żywych danych

Każdy z poniższych przechodził testy jednostkowe i **jednocześnie** nie działał produkcyjnie. Wszystkie mają teraz test regresyjny (`tests/simple_stats/test_providers.py`, `test_discover.py`, `test_analyze.py`).

1. **Highlightly nigdy nie zwracał danych.** `get_statistics_result` nie tylko *waliduje* `home_team_id`/`away_team_id` — porównuje je z `team.id` w payloadzie, żeby przypisać stronę, i zwraca `SCHEMA_ERROR: unexpected_team_id`, gdy nie pasują. Implementacja podawała placeholdery `"home"`/`"away"`, więc **każde** wywołanie kończyło się błędem. Naprawa: DISCOVER zapisuje natywne ID drużyn w nowym polu `EventRecord.provider_team_ids` (rozszerzenie schematu z §2 — bez niego ten provider jest nieosiągalny).
2. **SportDB normalizer zwracał `{}` na produkcji.** Żywy payload MCP trzyma okresy pod kluczem `data`; tylko przechwyty REST w `tests/fixtures/.../live_response_corpus` używają `body`. Normalizer czytał wyłącznie `body`. Dodatkowo wartości są **stringami** i nie zawsze liczbami (`"48%"`, `"83% (372/450)"`), więc `float()` rzucał i cicho gubił metrykę.
3. **Tenis nie produkował żadnych metryk.** `_combined_from_dict_stats` wymaga par `{"home": x, "away": y}`; tennis-abstract zwraca płaskie skalary jednego gracza. Osobno: `aces`/`double_faults` to liczby **jednego gracza**, więc mapowanie ich wprost na `aces_total` zaniżało sumę meczową o ~połowę i sprawiało, że każda linia UNDER wyglądała na 100% trafień. Naprawa: sumowanie z `oaces`/`odfs` (obecne w surowym wierszu, ale nieeksponowane przez klienta) oraz `total_games = service_games + return_games`.
4. **`cross_provider_agreement` zawsze zwracało `SINGLE_SOURCE`.** Grupowanie po surowym `(opponent, match_date)` nigdy nie łączyło providerów, bo różnie zapisują nazwy („Ulsan HD" vs „Ulsan Hyundai FC") i formaty dat. To **wyłączało cichą** kontrolę, dla której ten pipeline istnieje. Naprawa: kubełkowanie po dniu + klastrowanie po rozmytym dopasowaniu nazw.
5. **ESPN działał tylko dla Anglii.** `get_client("espn-football")` przypina ligę do `eng.1`, więc każdy mecz spoza Premier League padał na `resolve_team_id`. Naprawa: budowanie klienta przez istniejące `get_espn_league_for_competition()`.
6. **SportDB wybierał złą ligę.** `flashscore_search` sortuje po własnej trafności: „La Liga - Spain" → Liga MX (Meksyk), „Brazil Série B" → Serie A (Włochy). Branie `result[0]` przypisałoby historię **cudzej ligi** do naszego meczu. Naprawa: gdy nazwa zawiera kraj, deterministyczne wyliczenie lig tego kraju; punktacja kandydatów; odrzucenie słabego dopasowania (brak danych jest lepszy niż złe dane). Dodatkowo dopasowanie nazw drużyn wewnątrz ligi działa jako druga bariera poprawności.
7. **Zapis do bazy zawsze się wywracał.** `bet.db.connection` celowo nie zgaduje bazy operacyjnej, a `BET_DB_PATH`/`DATABASE_URL` nie są ustawione w `.env`. Naprawa: `default_db_path()` + flaga `--db-path` w każdym skrypcie; wynik zapisu jest teraz widoczny w `AGENT_SUMMARY` (`persisted`, `persist_error`), a nie tylko na stderr.
8. **Cache wyników sezonu SportDB zatruwał się i ścigał.** Trzy sloty tego samego eventu (`team_a`/`team_b`/`h2h`) startowały równolegle, a pusty wynik jednej nieudanej próby był cache'owany, wyłączając SportDB dla całej ligi do końca runu.
9. **Nieświeże mecze wchodziły do próbki.** api-football zwracał mecze z **2024** dla fixture'u z 2026; mieszanie dwuletniej formy z bieżącą daje hit rate, który nie opisuje żadnej z nich. Naprawa: okno 500 dni.
10. **Brak `fixture_sources`.** §8 wskazuje `fixtures` **+** `fixture_sources`, ale zapisywano tylko `fixtures` — czyli gubiono lineage stojący za `identity_confidence`.
11. **§4.1 „Uwaga do naprawienia": red cards.** Wykonane — `"Red cards"` jest teraz w `STAT_NAME_MAP`, a `MISSING_TARGET_METRICS` jest puste.

### 13.3 Limity providerów — stan faktyczny

`highlightly` i `sportdb` **nie miały żadnego wpisu** w `RateLimiter`, więc lokalny limiter uznawał je za nielimitowane, a run dowiadywał się o wyczerpaniu limitu dopiero z `HTTP 429` w połowie pracy. Dodano konserwatywne wpisy (`highlightly: 100/dzień`, `sportdb: 300/dzień`) — do skalibrowania po pierwszym dniu pilotażu (§11, Faza C).

| Provider | Limit | Uwaga operacyjna |
|---|---|---|
| the-odds-api | 500/miesiąc, **wyczerpany** | Nieistotne: pipeline używa darmowego `/events`. |
| highlightly | dzienny, reset UTC | Twardy 429 „You have breached your daily request limits". Najdroższy provider: 1 wywołanie `/statistics` na mecz historyczny. |
| api-football | 100/dzień | Wyczerpuje się przy ~10 eventach. |
| espn | brak | Darmowy i nielimitowany, ale rozpoznaje tylko drużyny z lig, które mapuje `COMPETITION_TO_ESPN_LEAGUE`. |
| sportdb | brak publicznego | Najlepszy zasięg lig spoza Europy Zachodniej. |
| serpapi | 8/dzień | Tylko kontekst H2H, nie zasila hit rate. |

**Wniosek operacyjny:** pełny dzień to 150+ meczów, a każdy kosztuje kilkadziesiąt wywołań. Żaden limit tego nie przetrwa. `run_enrich.py` ma teraz `--max-events` (domyślnie 40) i sortuje eventy „najlepiej potwierdzone najpierw"; eventy poza limitem trafiają do artefaktu jako `BLOCKED` z jawnym powodem, nie znikają po cichu.

### 13.4 Status kryteriów gotowości (§12)

| Kryterium | Status |
|---|---|
| DISCOVER z 2+ niezależnych źródeł, poprawnie scalonych | ✅ 182 eventy, 24 `CONFIRMED` z odds-api + highlightly |
| ENRICH: 3 providerów naraz na tej samej metryce, z jawnym `cross_provider_agreement` | ✅ zweryfikowane na żywo (`espn-football` + `api-football` + `highlightly`, oraz `+ sportdb`) — zależne od dostępnych limitów |
| ENRICH przeżywa awarię providera | ✅ każda awaria to `data_gap`; run kończy się artefaktem |
| ANALYZE pokazuje `hits/sample_size` dla każdej linii | ✅ wszystkie linie z `STANDARD_MARKET_LINES`, w obu kierunkach |
| Brak danych = jawny `data_gap`, nie ciche zero | ✅ |
| Dossier tenisowy zapisuje się do bazy | ✅ zweryfikowane produkcyjnie (`analysis_raw_data`, bez `team_id`) |

**Zastrzeżenie do `readiness=READY` dla tenisa:** próg wymaga 2+ providerów na 3 metrykach priorytetowych, ale realnie dane daje tylko `tennis-abstract` (sackmann martwy, espn-tennis pokrywa jedynie `total_games`/`total_sets`). Tenis osiąga dziś maksymalnie `PARTIAL`. To ograniczenie danych, nie kodu — do decyzji przy kalibracji progów w Fazie C.
