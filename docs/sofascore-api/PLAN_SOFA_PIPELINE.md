# `sofa` — samodzielny pipeline zakładowy na jednym providerze (Sofascore)

**Dla:** agenta implementującego (Gemini 3.1 Pro Preview) pracującego w repo `bet`.
**Status:** plan finalny, zatwierdzony kierunek z 2026-09-17.
**Zastępuje:** `docs/sofascore-api/IMPLEMENTATION_PLAN.md` — tamten opisywał
Sofascore jako dodatkowy provider wewnątrz `simple_stats`. Nie realizuj go.
**Wejście faktograficzne:** `REFERENCE.md`, `AUDIT_FINDINGS.md`, `evidence/`.
Każde twierdzenie o API, którego nie ma w `evidence/`, jest hipotezą.

---

## 0. Czym ten pipeline jest, a czym nie jest

`sofa` to **nowy, samodzielny pipeline zakładowy**. Ma własne kontrakty, własny
silnik prawdopodobieństwa, własny builder kuponu, własne artefakty, własne testy
i własny CLI.

### 0.1 Zasada nieprzecinania się z `simple` — twarda

> **`src/bet/sofa/**` i `scripts/sofa/**` nie importują NICZEGO z
> `src/bet/simple_stats/**`, `scripts/simple/**` ani
> `src/bet/discovery/**`. Zero wyjątków.**

Dotyczy to również: `contracts.py`, `analyze.py`, `coupons.py`,
`bet_builder_draft.py`, `providers.py`, `enrich.py`, `discover.py`,
`calibration.py`, `settle.py`, `forecast.py`, `dedup.py`, `team_aliases.py`.

**Egzekwowane testem, nie obietnicą** — patrz T00 w sekcji 8.

Wolno importować **wyłącznie** z:
- biblioteki standardowej,
- zależności zewnętrznych z `pyproject.toml` (`curl_cffi`, `pydantic`,
  `rapidfuzz`, `SQLAlchemy`…),
- `src/bet/sofa/**` (własny kod).

Jedyny obiekt współdzielony z resztą repo to **plik SQLite**, i to tylko dlatego,
że to jeden plik na dysku — `sofa` tworzy w nim **własne tabele z prefiksem
`sofa_`** i nie czyta ani nie zapisuje żadnej istniejącej tabeli. Jeśli wolisz
osobny plik bazy (`data/sofa.db`) — jeszcze lepiej, i to jest domyślna
rekomendacja (patrz I3).

### 0.2 Co wolno przenieść z `simple`

**Wiedzę, nie kod.** `simple` to ~28 000 linii, w których zapisano kilkadziesiąt
naprawionych błędów arytmetycznych i statystycznych. Ta wiedza jest wartością;
kod, który ją niesie, jest obciążony rosterem sześciu providerów, quotami,
korroboracją i warstwami zgodności wstecznej, których tu **nie ma i nie będzie**.

Sekcja 9 to katalog lekcji przeniesionych jawnie: każda z powodem i z testem,
który ją utrwala. Jeśli implementujesz coś z tej listy — **napisz to od nowa**,
zaglądając do `simple` po uzasadnienie i po liczby, nie po linijki.

### 0.3 Czego `sofa` nie robi w tej iteracji

- Nie stawia zakładów. Produkuje kupon jako raport; decyzja o grze jest operatora.
- Nie obsługuje baseballu. `evidence/` nie zawiera **ani jednego** pliku MLB —
  pokrycie Sofascore dla baseballu jest niezmierzone. Etap E12 to pomiar, nie kod.
- Nie czyta tipsterów, nie liczy konsensusu rynkowego z innych bukmacherów,
  nie generuje PDF-ów. Te warstwy istnieją w `simple` i mogą zostać tam.
- Nie ma fallbacku na inne źródło. Fixture bez dopasowania wypada ze slate'u.

---

## 1. Decyzje architektoniczne

Podjęte, nie do rozważenia. Jeśli któraś okaże się w praktyce zła — zgłoś to
w raporcie z etapu, nie zmieniaj po cichu.

### A1. Superbet jest osią discovery; Sofascore nie jest i nie może być
Discovery po dacie w Sofascore **nie istnieje** — `/sport/football/scheduled-events/{date}`,
`/sport/football/events/today`, `/sport/football/fixtures/{date}` zwracają 404
(`evidence/discovery_football_scheduled_events_date.json`,
`discovery_football_events_date.json`, `discovery_football_fixtures.json`,
`scheduled_events_today.json`). Alternatywa (liga → sezon → runda) wymagałaby
crawlera po wszystkich ligach świata.

Nie jest to jednak problem, bo **obstawiamy wyłącznie to, co Superbet ma na
tablicy**. Board Superbetu jest więc jedynym poprawnym slate'em, a nie obejściem.
Konsekwencja: `sofa` nigdy nie wzbogaca fixture'u, którego nie da się kupić.

### A2. Tożsamość fixture'u to `sofascore_event_id` — jeden klucz, nie dwa
`simple` mintuje `event_id` jako SHA-256 z `(sport|competition|participants|start_time)`
i potem dopasowuje go do Superbetu po nazwach — co udokumentowanie gubiło
fixture'y i podwajało je. W `sofa`:

```
superbet_event_id  --(resolve)-->  sofascore_event_id  ==  klucz główny fixture'u
```

**Dwa różne `superbet_event_id` wskazujące na ten sam `sofascore_event_id` to
jeden fixture.** To nie jest hipoteza: 2026-09-12 cztery mecze tenisa miały po
dwa osobne wpisy na tablicy Superbetu. Deduplikacja jest obowiązkowa i ma własny
test (L12).

Odwrotny przypadek — jeden `superbet_event_id` dopasowany do dwóch różnych
eventów Sofascore — jest błędem rozwiązywania, nie fixture'em, i kończy się
`AMBIGUOUS` (nie zgadywaniem).

### A3. Pipeline jest ciągiem czystych transformacji nad artefaktami JSON
Każdy etap: czyta artefakt(y) → woła sieć tylko w swojej warstwie klienta →
zapisuje jeden artefakt → emituje jedną linię podsumowania. Każdy etap daje się
uruchomić osobno na zapisanym wejściu. To jest jedyny sposób, żeby dało się
debugować zły dzień bez ponownego płacenia za sieć.

```
runs/sofa/<YYYY-MM-DD>/
  01_board.json          BOARD_V1          (Superbet)
  02_fixtures.json       FIXTURES_V1       (Sofascore: tożsamość + kontekst)
  03_samples.json        SAMPLES_V1        (Sofascore: historia + metryki)
  04_offer.json          OFFER_V1          (Superbet: drabiny cenowe)
  05_sheet.json          SHEET_V1          (silnik: p_central, bar, edge)
  06_coupon.json         COUPON_V1         (selekcja)
  06_coupon.md           kupon dla człowieka
  run.log.jsonl          jeden wiersz na żądanie sieciowe
```

### A4. Oferta Superbetu jest czytana **dwa razy** i to jest celowe
Raz przed próbkowaniem (żeby wiedzieć, które fixture'y i które rynki w ogóle
mają cenę — patrz A5), i raz bezpośrednio przed budową kuponu (świeża cena).
Cena starsza niż `PRICE_MAX_AGE_MIN` (domyślnie 45 min) w momencie budowy kuponu
**blokuje wiersz**, nie ostrzega. `simple` uczyło się tego na 52 raportowanych
wierszach VALUE przy 82 realnych.

### A5. Drabinę rynków dyktuje oferta, nie my
Nie ma listy „standardowych linii". Dla każdego fixture'u bierzemy **te linie,
które Superbet faktycznie wystawił**, i wyceniamy dokładnie je. Powód: wiersz
na linii, której nikt nie kwotuje, jest nieobstawialny, a linia wymyślona przez
nas zawsze wygląda lepiej niż ta, którą rynek naprawdę wycenił.

Konsekwencja praktyczna: `03_samples` jest budowany **tylko dla metryk, które
mają cenę w `01_board`/`04_offer`**. To jest też najtańszy możliwy budżet
wywołań.

### A6. Prognoza powstaje przed ceną, cena jest drugim krokiem
Silnik liczy `p_central` z samej próbki i priorów, **nie widząc ceny**. Dopiero
osobny, jawny krok miesza to z odvigowaną ceną rynkową (A7) i liczy przewagę.
Dwa kroki, dwa pola w artefakcie, dwa testy. Bez tego nie da się odpowiedzieć na
pytanie „czy model coś umie", bo umiejętność i kalibracja to dwa różne pytania.

### A7. Cena rynkowa jest dowodem, nie tylko progiem
Odvigowana drabina Superbetu to prognoza kogoś, kto ma więcej danych niż nasze
10 meczów. Wchodzi do arytmetyki jako cel skurczu (`w·p_próbka + (1−w)·p_rynek`),
a nie tylko jako próg do przebicia. Ale **nigdy nie zastępuje próbki całkowicie** —
wtedy nie byłoby żadnej przewagi do znalezienia.

### A8. Jeden provider ⇒ korroboracja nie istnieje jako pojęcie
Patrz sekcja 3 — to jest na tyle ważne, że ma własny rozdział.

### A9. Kalibracja jest bootstrapowana wstecz, nie po dwóch tygodniach czekania
Sofascore ma historię do 2000 roku (`evidence/team_2829_events_last_50.json`).
Można więc **odtworzyć dowolny miniony dzień**: zbudować próbkę „na stan sprzed
meczu", policzyć `p_central` i rozliczyć ją realnym wynikiem. To daje dziesiątki
tysięcy rozliczonych wierszy **zanim padnie pierwszy zakład** — czego `simple`
nigdy nie mógł zrobić, bo bzzoiro miał quotę dzienną.

**Granica tej metody, wprost:** historycznych cen Superbetu nie mamy. Wstecz da
się zmierzyć **kalibrację prawdopodobieństwa** (czy 85% znaczy 85%), nie da się
zmierzyć **ROI**. Nie myl tych dwóch i nie raportuj drugiego z pierwszego.

### A10. Warstwa analityka (agent) jest zaprojektowana od razu, dostarczana później
Kontrakt veta (`VETO_V1`) powstaje w E8 i builder kuponu go konsumuje od
pierwszego dnia — tyle że lista jest pusta. Agent analityczny to osobny
deliverable po E11. Powód: veto musi mieć *pełny klucz* (fixture + rynek +
linia + kierunek + podmiot), a dopisanie klucza później to przepisanie
selekcji. `simple` zapłacił za to dwa razy (veto bez nazwy gracza rozszerzało
się na 20 zawodników; veto z przestarzałym hashem cicho nie robiło nic).

---

## 2. Decyzje infrastrukturalne

### I1. Język, wersja, narzędzia
Python 3.12 (`pyproject.toml: target-version = "py312"`). `ruff` (select
`E,F,I,N,W,UP`, line-length 88) i `mypy --strict` muszą być czyste na całym
`src/bet/sofa/**` — repo ma `strict = true`, a nowy moduł nie ma prawa startować
z długiem.

### I2. Zależności
Dodaj do `[project.dependencies]` w `pyproject.toml`:
```toml
"curl_cffi>=0.7,<1",
```
**Sprawdzone: dziś go tam nie ma.** Jest tylko przypadkiem zainstalowany lokalnie
(0.15.0). Bez tego wpisu świeży klon i CI nie zbudują `sofa`. To jest pierwszy
commit, przed jakimkolwiek kodem.

Nic więcej nie dodawaj. `pydantic`, `rapidfuzz`, `SQLAlchemy` już są.

### I3. Trwałość — osobny plik SQLite
`data/sofa.db`, ścieżka z `SOFA_DB_PATH` (domyślnie `data/sofa.db`). Osobny plik,
nie współdzielony z `bet.db`: „jeden plik, własne tabele z prefiksem" też by
zadziałało, ale osobny plik czyni zasadę z 0.1 sprawdzalną przez `ls`, a nie
przez czytanie schematu.

Schemat tworzony przez `sofa.db.migrate()` — czysty SQL, idempotentny
(`CREATE TABLE IF NOT EXISTS`), uruchamiany przy każdym starcie. Cztery tabele:

```sql
-- nazwa z Superbetu -> encja Sofascore
CREATE TABLE IF NOT EXISTS sofa_entity (
    sport          TEXT    NOT NULL,          -- 'football' | 'tennis'
    query_key      TEXT    NOT NULL,          -- znormalizowana nazwa z Superbetu
    sofascore_id   INTEGER NOT NULL,
    sofascore_name TEXT    NOT NULL,
    entity_type    TEXT    NOT NULL,          -- 'team' | 'player'
    country        TEXT,
    status         TEXT    NOT NULL DEFAULT 'candidate',  -- candidate|verified|rejected
    verified_at    TEXT,
    last_used_at   TEXT,
    hit_count      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (sport, query_key)
);

-- niezmienna historia: statystyki zakończonego meczu nigdy się nie zmieniają
CREATE TABLE IF NOT EXISTS sofa_event_stats (
    sofascore_event_id INTEGER PRIMARY KEY,
    fetched_at         TEXT NOT NULL,
    statistics_json    TEXT,       -- NULL = 404, czyli "brak agregatów"
    incidents_json     TEXT,       -- NULL = 404
    status_type        TEXT NOT NULL
);

-- listing meczów drużyny/zawodnika, cache krótkoterminowy (TTL)
CREATE TABLE IF NOT EXISTS sofa_entity_events (
    sofascore_entity_id INTEGER NOT NULL,
    kind                TEXT    NOT NULL,     -- 'last' | 'next'
    page                INTEGER NOT NULL,
    fetched_at          TEXT    NOT NULL,
    events_json         TEXT    NOT NULL,
    PRIMARY KEY (sofascore_entity_id, kind, page)
);

-- rozliczone wiersze: jedyne źródło kalibracji
CREATE TABLE IF NOT EXISTS sofa_settled_row (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date           TEXT    NOT NULL,
    sofascore_event_id INTEGER NOT NULL,
    sport              TEXT    NOT NULL,
    competition_id     INTEGER,
    market             TEXT    NOT NULL,
    subject            TEXT    NOT NULL,      -- '' dla match total, inaczej nazwa strony/gracza
    line               REAL    NOT NULL,
    direction          TEXT    NOT NULL,      -- OVER | UNDER
    sample_size        INTEGER NOT NULL,
    p_central          REAL    NOT NULL,
    p_bar              REAL    NOT NULL,
    market_p           REAL,                  -- odvigowana cena, NULL wstecz
    actual_value       REAL    NOT NULL,
    outcome            TEXT    NOT NULL,      -- WIN | LOSS | PUSH
    settled_at         TEXT    NOT NULL,
    UNIQUE(sofascore_event_id, market, subject, line, direction)
);
```

`sofa_event_stats` jest trwały i **nigdy nie wygasa** — zakończony mecz się nie
zmienia. `sofa_entity_events` ma TTL (`SOFA_EVENTS_TTL_MIN`, domyślnie 360 min),
bo listing przyszłych meczów żyje.

### I4. Konfiguracja — wyłącznie przez env, z jednym miejscem odczytu
`src/bet/sofa/config.py`, jedna dataclass `SofaConfig` z `from_env()`.
Żadnych `os.environ` rozsianych po kodzie. Wszystkie wartości domyślne są
w tej jednej klasie i są wypisane w `--help`.

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `SOFA_DB_PATH` | `data/sofa.db` | baza |
| `SOFA_RUNS_DIR` | `runs/sofa` | artefakty |
| `SOFA_TARGET_RPS` | `10` | token-bucket |
| `SOFA_MAX_CONCURRENCY` | `8` | strop workerów |
| `SOFA_BREAKER_THRESHOLD` | `3` | kolejne błędy → otwarcie |
| `SOFA_EVENTS_TTL_MIN` | `360` | TTL listingu |
| `SOFA_SAMPLE_N` | `10` | mecze na stronę |
| `SOFA_MIN_SAMPLE` | `5` | poniżej — brak wiersza |
| `SOFA_PRICE_MAX_AGE_MIN` | `45` | świeżość ceny |
| `SOFA_SHRINK_K` | `10` | waga ceny (do re-fitu, patrz 6.6) |

### I5. Logowanie — jeden wiersz JSON na żądanie, zawsze
`run.log.jsonl`: `{ts_utc, stage, method, url, status, elapsed_ms, cache_hit,
breaker_state}`. To jest ten sam wymóg, którego brak sprawił, że twierdzenie
„2300 req/s" z pierwszej rundy audytu okazało się nieodtwarzalne. Log jest
artefaktem, nie debugiem — bez niego nie wolno raportować żadnej liczby o ruchu.

### I6. Czas — UTC wszędzie, bez wyjątku
Każdy timestamp w każdym artefakcie jest `datetime` **aware** w UTC, serializowany
z sufiksem `Z`. Sofascore podaje `startTimestamp` jako epoch UTC — konwertuj
przez `datetime.fromtimestamp(ts, UTC)`, nigdy `utcfromtimestamp` (deprecated)
i nigdy `fromtimestamp` bez tz. Funkcja `sofa.timeutil.now()` jest jedynym
źródłem „teraz"; testy ją podmieniają.

`simple` prawie stracił blok 18:30–19:00 UTC, bo `ts` drukował UTC+2 bez etykiety.
Tu etykieta jest w typie, nie w konwencji.

### I7. Współbieżność
`ThreadPoolExecutor(max_workers=SOFA_MAX_CONCURRENCY)` **plus** token-bucket
w kliencie. To dwa różne pokrętła i oba są potrzebne: 20 workerów bez pacingu
wybija >100 req/s (widać w `evidence/rate_limit_test_log_100w.jsonl`).
Zmierzony sufit ~550 req/s nie jest celem — jeśli kod do niego dąży, brakuje
cache'u, nie limitu.

### I8. Kod wyjścia i podsumowanie
Każdy skrypt: `0 = OK`, `1 = PARTIAL`, `2 = FAILED`. Jedna linia
`SOFA_SUMMARY: {json}` na stdout na końcu procesu, z `stage`, `verdict`,
`metrics`, `output_path`. Własny, minimalny format — nie importuj
`scripts/agent_output.py` (to jest kod `simple`; skopiuj 30 linii, jeśli
potrzebujesz tego kształtu).

---

## 3. Jeden provider — co z tego wynika i co znika

To jest największa różnica projektowa wobec `simple` i największe źródło
pokusy, żeby przenieść kod, który tu nie ma sensu.

### 3.1 Co znika całkowicie — nie implementuj

| Pojęcie z `simple` | Dlaczego znika |
|---|---|
| `PROVIDER_NAMES`, `ProviderValue.provider` | jest jeden; pole o stałej wartości to nie dane |
| `PRIMARY_PROVIDER_BY_SPORT`, `corroborators_for` | nie ma kogo rankingować |
| `AGREE` / `DISAGREE` / `SINGLE_SOURCE` | każdy wiersz jest single-source z definicji; flaga o stałej wartości wprowadza w błąd |
| korekta `p_low` za korroborację | nie ma korroboracji |
| quota, `reset_provider_quota`, apportionment cap | Sofascore nie ma quoty; cap dzielony per sport potrafił wyzerować cały sport |
| `NATIVE_ID_PROVIDERS_BY_SPORT`, `provider_team_ids` | jest jeden schemat id |
| `SLATE_CRITICAL_SOURCES`, `degraded_reasons` per źródło | jedno źródło; degradacja jest binarna |

### 3.2 Czego brak drugiego źródła **nie** zwalnia — i co je zastępuje

Korroboracja pełniła jedną realną funkcję: wykrywała, że próbka nie opisuje tego
meczu. Z jednym providerem tę funkcję muszą przejąć **trzy inne mechanizmy** i
każdy z nich jest tu obowiązkowy, nie opcjonalny:

1. **Bramka drabiny (`LADDER_SIGMA`)** — jak daleko środek naszej próbki leży od
   środka, który implikuje cała odvigowana drabina Superbetu, mierzone w
   odchyleniach *tej próbki*. To jest jedyny zewnętrzny pomiar, jaki mamy na
   żywo. W `simple` to była jedna z kilku bramek; tutaj jest **główną**.
2. **Rozliczenie wsteczne (A9)** — jedyna prawda naziemna.
3. **Kontrola spójności wewnętrznej payloadu** — patrz 5.5. Sofascore publikuje
   te same wielkości na kilka sposobów (suma strzałów vs rozkład; gemy vs wynik
   setowy; gole w `homeScore` vs incydenty typu `goal`). Te tożsamości muszą się
   zgadzać, a rozjazd jest sygnałem transkrypcji, nie szumem.

### 3.3 Gotowość (`readiness`) mierzy **głębokość próbki** i nic więcej

```
READY    obie strony mają >= SOFA_MIN_SAMPLE (5) obserwacji metryki
PARTIAL  co najmniej jedna strona ma >=1, ale nie obie >=5
BLOCKED  żadna strona nie ma obserwacji
```

**Nie** „dwa źródła zgodne". W `simple` próg wymagający dwóch źródeł przy suficie
jednego dał tenisowi 0 z 14 gotowych fixture'ów przez kilka dni, wyglądając na
brak danych. Obowiązkowy test (T14): na realnym dniu `READY > 0` dla **obu**
sportów. Zero READY w którymkolwiek sporcie to nie wynik, to nieosiągalna bramka.

---

## 4. Kontrakty danych

Wszystkie w `src/bet/sofa/contracts.py`, pydantic v2, `model_config =
ConfigDict(extra="forbid", strict=True)`. Nowe pole = świadoma decyzja, nie
przypadek. Nie ma domyślnych wartości dla pól, które muszą być zmierzone.

```python
Sport = Literal["football", "tennis"]
Direction = Literal["OVER", "UNDER"]
Readiness = Literal["READY", "PARTIAL", "BLOCKED"]

class GapReason(StrEnum):                 # 2.5 — enum, nigdy wolny tekst
    NO_ENTITY_FOUND       = "NO_ENTITY_FOUND"
    AMBIGUOUS_ENTITY      = "AMBIGUOUS_ENTITY"
    NO_MATCHING_EVENT     = "NO_MATCHING_EVENT"
    EVENT_NOT_FINISHED    = "EVENT_NOT_FINISHED"
    NO_STATISTICS         = "NO_STATISTICS"
    NO_INCIDENTS          = "NO_INCIDENTS"
    STAT_KEY_ABSENT       = "STAT_KEY_ABSENT"
    ALL_ZERO_SAMPLE       = "ALL_ZERO_SAMPLE"
    INTERNAL_INCONSISTENT = "INTERNAL_INCONSISTENT"
    THIN_SAMPLE           = "THIN_SAMPLE"
    NO_PRICE              = "NO_PRICE"
    STALE_PRICE           = "STALE_PRICE"
    PROVIDER_ERROR        = "PROVIDER_ERROR"
    CIRCUIT_OPEN          = "CIRCUIT_OPEN"

class BoardFixture(BaseModel):            # 01_board
    superbet_event_id: str
    sport: Sport
    match_name: str
    side_a: str                           # nazwa z Superbetu, surowa
    side_b: str
    kickoff_utc: datetime

class Fixture(BaseModel):                 # 02_fixtures — klucz: sofascore_event_id
    sofascore_event_id: int
    superbet_event_ids: list[str]         # >1 = zdublowany wpis na tablicy (A2)
    sport: Sport
    kickoff_utc: datetime
    home_name: str                        # z Sofascore, nie z Superbetu
    away_name: str
    home_entity_id: int
    away_entity_id: int
    competition_name: str                 # uniqueTournament.name
    competition_id: int                   # uniqueTournament.id  <- klucz, nie napis
    season_id: int
    category_name: str                    # kraj / 'ATP' / 'WTA'
    identity: Literal["CONFIRMED", "FUZZY"]
    # kontekst — piłka
    round_number: int | None
    round_name: str | None
    cup_round_type: int | None
    previous_leg_event_id: int | None     # tylko dwumecze; patrz 5.6
    venue_name: str | None
    referee: RefereeRecord | None
    has_xg: bool
    # kontekst — tenis
    ground_type: str | None               # 'Hardcourt outdoor' itd.  <- 5.7
    best_of: int | None                   # defaultPeriodCount: 3 lub 5

class RefereeRecord(BaseModel):
    name: str
    games: int
    yellow_cards: int
    red_cards: int
    yellow_red_cards: int

class Observation(BaseModel):             # jedna obserwacja jednej metryki
    sofascore_event_id: int               # mecz historyczny
    match_date_utc: datetime
    opponent: str
    value: float
    competition_id: int | None
    season_id: int | None
    venue: Literal["home", "away"] | None # piłka: zawsze; tenis i h2h: None (L7)

class MetricSample(BaseModel):
    metric: str                           # canonical, sekcja 5
    side_a: list[Observation]
    side_b: list[Observation]
    h2h: list[Observation]

class FixtureSamples(BaseModel):          # 03_samples
    sofascore_event_id: int
    readiness: Readiness
    metrics: dict[str, MetricSample]
    gaps: list[GapEntry]                  # GapEntry = {reason: GapReason, metric, detail}

class PricedRung(BaseModel):              # 04_offer
    market: str
    subject: str                          # '' | nazwa strony | nazwa gracza
    line: float
    over_odds: float | None
    under_odds: float | None
    fetched_at_utc: datetime

class SheetRow(BaseModel):                # 05_sheet
    sofascore_event_id: int
    sport: Sport
    market: str
    subject: str
    line: float
    direction: Direction
    sample_size: int
    sample_mean: float
    sample_sd: float
    centre: float                         # po skurczu do priora ligi (6.2)
    p_central: float                      # 6.3 — bez ceny
    market_p: float | None                # odvigowana cena tej szczebli (6.4)
    ladder_centre: float | None           # środek implikowany całą drabiną
    ladder_sigma: float | None            # |centre - ladder_centre| / sample_sd
    p_bar: float                          # po korekcie kalibracyjnej i skurczu do ceny (6.5)
    bar_reason: str | None
    required_odds: float                  # margin / p_bar
    offered_odds: float | None
    edge: float | None                    # p_central - market_p
    surplus: float | None                 # offered_odds - required_odds
    verdict: Literal["VALUE", "LEAN", "BELOW_BAR", "NO_PRICE", "BLOCKED"]
    notes: list[str]
```

`COUPON_V1` i `VETO_V1` — sekcja 7, E8/E9.

**Reguła kontraktowa (test T15):** każdy artefakt zapisany na dysk daje się
wczytać z powrotem przez `Model.model_validate_json()` **bez żadnej tolerancji**.
Artefakt, który nie waliduje się własnym modelem, to `FAILED`, nie ostrzeżenie.

---

## 5. Mapowanie Sofascore → nasz słownik

Ta sekcja jest zweryfikowana wobec `evidence/`, nie wobec `REFERENCE.md`.
**Trzy rzeczy poniżej są sprzeczne z tym, co sugeruje REFERENCE.md lub nazwy
pól w API.** Każda ma dowód arytmetyczny — odtwórz go, zanim cokolwiek napiszesz.

### 5.1 PUŁAPKA #1 — `totalShotsOnGoal` to **wszystkie strzały**, nie celne

`evidence/event_16363633_statistics.json`, strona gospodarzy:

```
totalShotsOnGoal      20      <- WSZYSTKIE strzały
shotsOnGoal            6      <- strzały CELNE
shotsOffGoal           6
blockedScoringAttempt  8
                      ---
        6 + 6 + 8  =  20      <- tożsamość się domyka
```

Nazwa `totalShotsOnGoal` czyta się jak „shots on goal", a znaczy „total shots".
Zmapowanie jej na „strzały celne" zawyża rynek **ponad trzykrotnie** i przechodzi
każdy test wewnętrzny, bo jest konsekwentnie złe. Poprawnie:

| Sofascore key | canonical |
|---|---|
| `totalShotsOnGoal` | `shots_total` / `shots_for` |
| `shotsOnGoal` | `shots_on_target_total` / `shots_on_target_for` |
| `shotsOffGoal` | `shots_off_target_total` |
| `blockedScoringAttempt` | `blocked_shots_total` |

Test T08a sprawdza dokładnie tę tożsamość na nagranym payloadzie.

### 5.2 PUŁAPKA #2 — klucze nie siedzą w grupie, której się spodziewasz

`offsides` jest w grupie **`Attack`**, nie `Match overview`.
`shotsOnGoal` jest w **`Shots`**. `goalkeeperSaves` jest w dwóch grupach naraz.

**Szukaj po `key`, płasko, po wszystkich grupach danego `period`.** Filtrowanie
po `groupName == "Match overview"` (co sugeruje REFERENCE.md sekcja 3) gubi
połowę potrzebnych metryk w ciszy.

Grupy w evidence: `Match overview`, `Shots`, `Attack`, `Passes`, `Duels`,
`Defending`, `Goalkeeping`. Okresy: `ALL`, `1ST`, `2ND`.

### 5.3 PUŁAPKA #3 — gole i połówki są **za darmo**, bez wywołania `/statistics`

`/team/{id}/events/last/{page}` zwraca 30 pełnych obiektów eventu, każdy z:

```json
"homeScore": {"current": 2, "period1": 1, "period2": 1, "normaltime": 2, "aggregated": 3}
"tournament": {"uniqueTournament": {"id": 7}}, "season": {"id": 76953},
"status": {"type": "finished"}, "roundInfo": {...}, "hasXg": true,
"previousLegEventId": ..., "hasEventPlayerStatistics": ...
```

(`evidence/team_2829_events_last_0.json`)

Czyli `goals_total`, `goals_for`, `goals_1h_*`, `goals_2h_*`, `competition_id`
i `season_id` pochodzą **z listingu**, nie ze statystyk. Trzy konsekwencje:
- budżet wywołań spada o metrykę, która ma najwięcej wierszy na arkuszu;
- mecz, którego `/statistics` zwraca 404, **nadal daje gole** — nie jest stracony;
- `period1`/`period2` dają połówki bez odejmowania, więc nie powstaje ujemna
  liczba goli, na której `simple` się kiedyś przewrócił.

**Nie licz goli z incydentów** (drugie źródło, druga transkrypcja) — użyj ich
tylko jako kontroli spójności (5.5).

### 5.4 Kartki punktowe — jedyna metryka wymagająca `/incidents`

Superbet rozlicza „Liczba kartek" w punktach: żółta 1, czerwona prosta 2, druga
żółta +1 ponad dwie już policzone żółte. `/statistics` daje **tylko**
`yellowCards`; czerwonych tam nie ma w ogóle (sprawdzone — brak klucza).

`/event/{id}/incidents` (`evidence/event_16363633_incidents.json`):
```json
{"incidentType": "card", "incidentClass": "yellow",
 "isHome": true, "rescinded": false, "time": 34, "playerName": "..."}
```

**PUŁAPKA #4 — `rescinded`.** Kartka anulowana ma `rescinded: true` i **nie
liczy się**. Nie ma o tym słowa w żadnej dokumentacji. Filtruj bezwarunkowo.

`incidentClass` ∈ {`yellow`, `red`, `yellowRed`}. Punktacja:
```
yellow    -> +1
red       -> +2        (czerwona prosta)
yellowRed -> +1        (obie żółte są już policzone osobno? -> SPRAWDŹ, 5.4a)
```

**5.4a — jedna liczba, której nie wolno zgadnąć.** Czy Sofascore emituje
osobny incydent `yellow` dla pierwszej żółtej zawodnika, który potem dostaje
`yellowRed`? Jeśli tak, `yellowRed` jest wart **+1**. Jeśli nie — **+3**.
W `evidence/` nie ma meczu z drugą żółtą (jedyny plik incydentów ma dwie zwykłe
żółte). **Pobierz mecz z drugą żółtą, zapisz go jako
`tests/fixtures/sofascore/incidents_second_yellow.json`, policz ręcznie i
udokumentuj wynik w raporcie z etapu.** Ta jedna liczba decyduje o poprawności
całej rodziny rynku kartkowego. Kontrola krzyżowa:
`Fixture.referee` niesie `yellowCards` / `redCards` / `yellowRedCards` osobno —
jeśli te trzy sumują się do liczby incydentów sędziego, masz odpowiedź.

Rozróżnienie zera od braku (obowiązkowe):
- payload `/incidents` **istnieje** i nie ma incydentu czerwonej → **realne 0**;
- payload `/incidents` **nie istnieje** (404) → `GapReason.NO_INCIDENTS`,
  **nigdy 0**.

### 5.5 Tożsamości wewnętrzne — zastępują drugiego providera (3.2 pkt 3)

Sprawdzaj przy każdym wczytaniu meczu historycznego. Rozjazd → obserwacja
odrzucona z `INTERNAL_INCONSISTENT`, nie uśredniona.

| Tożsamość | Źródła |
|---|---|
| `shotsOnGoal + shotsOffGoal + blockedScoringAttempt == totalShotsOnGoal` | `/statistics` |
| liczba incydentów `goal` == `homeScore.current + awayScore.current` | `/incidents` vs listing |
| `period1 + period2 == current` (gole, bez dogrywki) | listing |
| suma `gamesWon` obu stron == suma gemów z wyniku setowego | tenis |
| `1ST + 2ND == ALL` dla metryk zliczających | `/statistics` |

Ostatnia jest tylko raportowana, nie blokująca: `simple` zmierzył 0,91–2,21%
rozjazdu połówek u innego providera i to jest normalny poziom szumu dla tej
klasy danych. Pozostałe cztery są blokujące.

### 5.6 Piłka — tabela mapowania

| Sofascore | canonical `_total` | canonical `_for` | źródło |
|---|---|---|---|
| `homeScore.current` + `awayScore.current` | `goals_total` | `goals_for` | listing |
| `homeScore.period1` … | `goals_1h_total` | `goals_1h_for` | listing |
| `homeScore.period2` … | `goals_2h_total` | `goals_2h_for` | listing |
| `cornerKicks` | `corners_total` | `corners_for` | `/statistics` |
| `yellowCards` | `cards_total` | `cards_for` | `/statistics` |
| incydenty (5.4) | `cards_points_total` | `cards_points_for` | `/incidents` |
| `fouls` | `fouls_total` | `fouls_for` | `/statistics` |
| `offsides` (grupa `Attack`) | `offsides_total` | `offsides_for` | `/statistics` |
| `totalShotsOnGoal` | `shots_total` | `shots_for` | `/statistics` |
| `shotsOnGoal` | `shots_on_target_total` | `shots_on_target_for` | `/statistics` |
| `expectedGoals` | `xg_total` | `xg_for` | `/statistics`, tylko gdy `hasXg` |

`_total` = suma obu stron w jednym meczu. `_for` = wkład jednej strony.
**Nigdy nie wpisuj wartości jednej strony do `_total`** — to nie jest „prawie to
samo", to inna wielkość, i taki błąd potrafi odczytać cały slate jako rozjazd
z rynkiem.

`previous_leg_event_id`: obecny **tylko** w dwumeczach (potwierdzone —
jest w listingu meczu playoff LM, nie ma go w payloadzie meczu Premier League).
Traktuj jako opcjonalny; jego brak nie jest luką.

### 5.7 Tenis — dwie rzeczy, które Sofascore daje natywnie, a `simple` musiał zgadywać

**`groundType`** na `/event/{id}`: `"Hardcourt outdoor"`
(`evidence/event_15345277_details.json`). Nawierzchnia przychodzi z każdym
meczem, **także challengerowym**. `simple` miał na to mapę konfiguracyjną
z ~10 wpisami wielkoszlemowymi i zidentyfikowane, niezałatane ryzyko pomieszania
nawierzchni. Tutaj to jest pole. Normalizuj do `{hard, clay, grass, carpet}` +
`indoor/outdoor` i **filtruj próbkę po nawierzchni** — mecz na mączce nie opisuje
meczu na hardzie.

**`defaultPeriodCount`**: `5` dla Australian Open, `3` dla BO3
(`evidence/event_15345277_details.json`). Format meczu to pole, nie wniosek z
nazwy turnieju. Cała heurystyka „czy to Wielki Szlem, czy kwalifikacje" —
która w `simple` raz wygasiła cały rynek ATP (0 → 54 wierszy po naprawie), a raz
za łatwo odpuszczała — **nie jest tu potrzebna**. Próbka do rynku długości meczu
musi mieć ten sam `best_of` co dzisiejszy mecz. Kropka.

**PUŁAPKA #5 — `serviceGamesTotal` gubi tie-break.** `evidence/event_15345277_statistics.json`:

```
serviceGamesTotal   17 + 17 = 34
gamesWon            20 + 15 = 35
wynik setowy        7-6(8-6), 6-4, 7-5  ->  13 + 10 + 12 = 35
```

Brakujący gem to gem tie-breakowy, który nie ma serwującego w sensie tej
statystyki. `gamesWon` i wynik setowy zgadzają się dokładnie; `serviceGamesTotal`
jest **jednokierunkowo za niski** o jeden gem na każdy set 7-6. Używaj `gamesWon`
(albo sumy z `period{1..5}` + `periodNTieBreak`), nigdy `serviceGamesTotal`.

| Sofascore | canonical |
|---|---|
| suma `gamesWon` obu stron | `games_total` |
| `gamesWon` zawodnika | `games_won_for` |
| liczba rozegranych setów (z `period{1..5}`) | `sets_total` |
| suma `aces` obu stron | `aces_total` |
| `aces` zawodnika | `aces_for` |
| suma `doubleFaults` | `double_faults_total` |
| `doubleFaults` zawodnika | `double_faults_for` |
| `tiebreaks` (grupa `Miscellaneous`) | `tiebreaks_total` |

**`aces_total` to suma obu zawodników.** Zmapowanie asów jednego gracza na
`aces_total` daje ~połowę realnej wartości i sprawia, że każda linia UNDER
wygląda na 100% trafień. Test T09 to utrwala.

Tenis: `Observation.venue` zawsze `None` (L7). Na turnieju neutralnym nikt nie
gra u siebie, a nazwanie slotu 1 „home" wymyśla fakt.

### 5.8 Czego nie mapować

- `/event/{id}/odds/1/all` — Superbet jest jedyną ceną. Nie importuj tego do
  niczego cenowego, nawet „dla porównania" (to jest dokładnie ten mechanizm,
  przez który cudza cena wchodzi do arytmetyki tylnymi drzwiami).
- statystyki per-gracz z `/lineups` — bogate, ale props przy cenach Superbetu
  zmierzono na −30,5% w paśmie. Poza `aces_for` / `double_faults_for` /
  `games_won_for` (mają realne rynki) nie dodawaj metryk bez odbiorcy.
- `/point-by-point`, `/tennis-power`, `heatmap` — brak odbiorcy.
- `ballPossession` — suma obu stron to zawsze 100, czyli stała w przebraniu.

---

## 6. Silnik — dokładna arytmetyka

To jest część, którą `simple` wypracował najdrożej. Poniżej: wzory, stałe i —
najważniejsze — **które stałe wolno przepisać, a które trzeba zmierzyć od nowa**.

### 6.0 Stałe przenoszalne vs stałe do ponownego pomiaru

| Element | Przenieść? | Dlaczego |
|---|---|---|
| dyspersja predykcyjna `σ²(1+1/n)` | **tak** | czysta matematyka |
| granica wygranej / obsługa pusha | **tak** | czysta matematyka |
| clamp `p ∈ [0.05, 0.95]` | **tak** | strukturalny |
| cap Laplace'a przy zerze pudeł | **tak** | matematyka |
| `p_low` jako sufit przy `n < 8` | **tak** | strukturalny |
| `bar = margin / p` | **tak** | definicja |
| kształt skurczu `w = n/(n+k)` | **tak** | strukturalny |
| marże progów `CALL 1.05 / LEAN 1.10` | **tak** | polityka operatora |
| **`k = 10`** | **NIE** | dopasowane na próbkach bzzoiro, 2 slate'y |
| **`MAX_LADDER_SIGMA = 1.25`** | **NIE** | dopasowane na rozkładzie innego providera |
| **`market_reliability.json`** | **NIE** | krzywa kalibracji cudzych próbek |
| **`league_baselines.json`** | **NIE** | kluczowana cudzymi id lig |
| **`market_priors.json`** | **NIE** | j.w. |
| pasma cenowe i ich zmierzone krawędzie | **NIE** | zmierzone na cudzym arkuszu |

**To jest dziura, którą trzeba zobaczyć, zanim się w nią wpadnie.** Skopiowanie
`market_reliability.json` do `sofa` byłoby zastosowaniem korekty zmierzonej na
próbkach innego providera do naszych liczb — czyli korekty, która nie wie, co
koryguje. Start bez korekty (identyczność) jest **poprawny**; start z cudzą
krzywą jest błędem, który się nie ujawni.

Ścieżka bootstrapu: E10 (backfill) buduje własne `sofa_settled_row`, E11 fituje
z nich własne `k`, `LADDER_SIGMA`, kalibrację i baseline'y lig — **kluczowane
`uniqueTournament.id`**, co jest lepszym kluczem niż napis, którym operował
`simple`.

### 6.1 Próbka

Dla metryki `m` i fixture'u `F`:
- `side_a` = ostatnie `SOFA_SAMPLE_N` (10) zakończonych meczów strony A
  **przed** `F.kickoff_utc`,
- analogicznie `side_b`,
- `h2h` = mecze, w których przeciwnikiem była druga strona (wyciągane z już
  pobranej historii, **bez osobnego wywołania**).

Filtry obowiązkowe:
- `status.type == "finished"`;
- `startTimestamp < F.kickoff_utc` — brak tego filtru to wyciek przyszłości,
  najcichszy możliwy błąd (T12);
- tenis: `ground_type` zgodny z dzisiejszym; `best_of` zgodny z dzisiejszym;
- piłka: mecze towarzyskie i sparingi przedsezonowe **wykluczone** z próbki do
  rynków zliczających (rozpoznaj po `uniqueTournament.id` z listy wykluczeń
  budowanej w E10, nie po nazwie);
- deduplikacja obserwacji między `side_a`, `side_b` i `h2h`: **jeden mecz
  historyczny wnosi jedną obserwację do `_total`**, choćby występował w trzech
  koszykach.

**Jeden wiersz opisuje jedną próbkę.** Nie wolno skleić dwóch zakresów (np.
„ostatnie 10" i „ostatnie 5 na tej nawierzchni") w jeden wiersz — `sample_size`
przestaje wtedy znaczyć to, co mówi, a to jest liczba, przez którą dzielą
wszystkie wagi.

### 6.2 Środek

```
mean   = średnia arytmetyczna obserwacji
prior  = baseline ligi dla tej metryki (sofa_league_baseline, klucz: competition_id)
         -> fallback: baseline globalny metryki
         -> fallback: brak priora, centre = mean
w_c    = n / (n + K_CENTRE)                      # K_CENTRE do fitu w E11
centre = w_c * mean + (1 - w_c) * prior
```

Prior **musi** być per-liga. `simple` zmierzył, że prior ślepy na ligę potrafi
być całą różnicą: `goals_1h_total` = 0,821 w argentyńskiej Liga Profesional na
145 meczach przeciwko przypiętemu globalnemu 1,243 — i tamtego dnia to był cały
jedyny zakład dnia, po jednej stronie progu z globalnym priorem i po drugiej
z ligowym. Tutaj mamy `uniqueTournament.id`, więc klucz jest twardy.

Dom/wyjazd jest **priorem, nie podziałem próbki**: nie dziel 10 meczów na 5+5
(to szum na drużynę), tylko przesuń `centre` o zmierzoną różnicę dom−wyjazd
danej metryki, pulowaną po wszystkich ligach.

### 6.3 Prawdopodobieństwo z samej próbki (bez ceny)

```
var_sample = max(wariancja próbki, mean)          # podłoga: rozkład zliczający
var_pred   = var_sample * (1 + 1/n)               # <- (a)
sd         = sqrt(var_pred)
boundary   = line               jeśli line jest połówkowa
           = ceil(line) - 0.5   dla UNDER na linii całkowitej      <- (b)
           = floor(line) + 0.5  dla OVER  na linii całkowitej
z          = (boundary - centre) / sd   (dla OVER: z = -z)
p_central  = clamp(Φ(z), 0.05, 0.95)
```

**(a)** — to jest wariancja *następnej* obserwacji, nie próbki już widzianej.
`Var(X_new − mean̂) = σ²(1 + 1/n)`. Użycie samej wariancji próbki czyni
`p_central` nadmiernie pewnym **w obu kierunkach** naraz, przez co OVER i UNDER
nadal sumują się do 1 i żaden test niezmienników tego nie łapie. `simple`
zmierzył realny niedomiar dokładnie tam, gdzie `n` jest małe: przy n=5 deklarowane
sd 2,78 przeciwko realnemu 3,26 (stosunek 1,17), przy n=12 — 1,00.
`sqrt(1+1/5) = 1,095` tłumaczy większość tej luki.

**(b)** — linia całkowita daje **push**, a nie wygraną żadnej ze stron. Odczyt Φ
dokładnie na linii rozdaje masę pusha po połowie na OVER i UNDER, zawyżając obie.
Tenisowe totale bywają całkowite, więc to nie jest przypadek teoretyczny.

`p_low` (dolne ograniczenie: środek przesunięty 1,96 błędu standardowego
przeciwko zakładowi) liczymy **osobno** i używamy **tylko** jako sufitu przy
`n < 8` (6.5). Nie jest podstawą progu — `simple` zmierzył na 5 036 rozliczonych
wierszach, że `p_low` zaniża o +23,5 pp (deklarowane 0,613 przy realnych 0,848),
a ponieważ próg to `1/p`, zaniżenie o 23 pp przy p≈0,6 zawyża żądaną cenę
o czynnik 1,38 **przed** marżą. To zbanowało 341 z 341 wycenionych wierszy piłki
jednego dnia.

### 6.4 Cena rynkowa — odvigowanie i środek drabiny

Dla każdego szczebla z dwustronną ceną:
```
implied_over  = 1/over_odds ; implied_under = 1/under_odds
overround     = implied_over + implied_under
market_p      = implied_<kierunek> / overround
```
Jednostronna cena → `market_p = None`. **Nie da się odvigować jednej strony** i
nie wolno tego udawać.

Środek drabiny (`ladder_centre`): mając ≥2 szczeble tej samej metryki, których
odvigowane prawdopodobieństwa **przechodzą przez 0,5**, interpoluj liniowo punkt
`p = 0.5`. Mniej niż dwa szczeble albo drabina w całości po jednej stronie 0,5 →
`ladder_centre = None`. Jeden szczebel daje prawdopodobieństwo, nie położenie;
ekstrapolacja poza zakres, który bukmacher wystawił, jest wymyślaniem.

### 6.5 Próg (`p_bar` → `required_odds`)

Trzy etapy, w tej kolejności i nie w innej:

```
1) p = p_central
   jeśli hits == n (zero pudeł):  p = min(p, laplace(hits, n) = (hits+1)/(n+2))
   jeśli n < 8:                   p = min(p, p_low)
   -> bar_reason zapisuje, co ograniczyło

2) p = max(0.01, p - calibration_correction(market, p))
   calibration_correction czyta sofa_market_reliability (E11).
   Przed E11 jest identycznie zerowa — i to jest poprawny stan startowy.
   Ta korekta może wyłącznie OBNIŻAĆ p, czyli wyłącznie PODNOSIĆ próg.

3) jeśli market_p jest znane:
       w = n / (n + K_PRICE)
       p_bar = w * p + (1 - w) * market_p
   w przeciwnym razie:
       p_bar = p        # nie da się skurczyć do ceny, której nie ma

required_odds = round(TIER_MARGIN[tier] / p_bar, 4)
TIER_MARGIN = {"CALL": 1.05, "LEAN": 1.10}
```

Kolejność jest istotna: etap 2 mówi, co **ten rynek** dowiózł przy deklaracjach
tej wielkości — to nie jest fakt o próbce, więc idzie po niej. Skurcz do ceny
z nieskorygowanej deklaracji mieszałby opinię bukmachera z liczbą, o której już
wiemy, że jest gorąca.

`required_odds` liczone **w jednym miejscu**. `simple` miał ten wzór wypisany
trzykrotnie: w sondzie warunku, w polu artefaktu i w kluczu sortowania. Zgadzały
się, ale nic tego nie wymuszało.

### 6.6 Bramki

```
edge     = p_central - market_p                # centrum vs centrum, nigdy p_bar
surplus  = offered_odds - required_odds
VALUE    <=> surplus > 0  AND  ladder_sigma <= MAX_LADDER_SIGMA
```

**`edge` liczy się na `p_central`, nie na `p_bar` ani `p_low`.** Odjęcie dolnego
ograniczenia od odvigowanego centrum porównuje dwie różne wielkości i nazywa
resztę przewagą. `simple` wypuścił wiersz opisany jako +9,7 pp, którego realny
rozjazd z rynkiem wynosił +31,6 pp — a to jest liczba, którą operator czyta
przy podejmowaniu decyzji.

**`ladder_sigma` demotuje, rozjazd ceny tylko adnotuje.** To są dwie różne
bramki i mieszanie ich kosztowało `simple` jego jedynego realnego wiersza tamtego
dnia. Duży rozjazd z ceną bywa prawdziwą przewagą; próbka, której środek leży
dwa odchylenia od środka drabiny, to próbka opisująca inny mecz.

`MAX_LADDER_SIGMA` startowo `1.25` jako **wartość tymczasowa oznaczona w kodzie
jako do fitu w E11**, nie jako stała przeniesiona z autorytetu.

### 6.7 Nogi w jednym meczu i akumulatory

- Dwie nogi z **tego samego** meczu nie mają wspólnej ceny, której moglibyśmy
  użyć — i nie wolno mnożyć ich pojedynczych kursów. `simple` zmierzył
  zależność między nogami tego samego meczu na λ=1,009 przy 12 555 parach, czyli
  praktycznie niezależność — ale to jest stwierdzenie o **prawdopodobieństwie**,
  nie o **cenie**. Bukmacher wycenia Bet Buildera własnym modelem.
- Nogi z **różnych** meczów są niezależne i ich kursy się mnożą — ale
  arytmetyka musi być wykonana i pokazana: slip 5-nogowy przy 87% na nogę to
  0,87⁵ = 0,50, czyli rzut monetą, nie „pięć pewniaków".
- Akumulator nie ratuje nogi poniżej progu. Jeśli noga nie przechodzi sama,
  nie przechodzi w slipie.

`sofa` w tej iteracji buduje **wyłącznie singli**. Slipy są etapem po E11.

### 6.8 Selekcja kuponu

```
kandydat            verdict == VALUE
                    AND kickoff_utc > now + 15 min          # L19
                    AND cena nie starsza niż PRICE_MAX_AGE  # A4
                    AND offered_odds >= MIN_ODDS_FLOOR (1.25)
                    AND nie ma pasującego veta              # A10
sortowanie          surplus malejąco
limity              MAX_PER_FIXTURE = 3
                    MAX_PER_MECHANISM_FAMILY_PER_FIXTURE = 1
                    MAX_SINGLES = 40
```

**Rodzina mechanizmu**, nie rynek. `goals_total 5.5 UNDER`, `goals_1h_total 3.5
UNDER`, `goals_2h_total 3.5 UNDER` i `goals_for 2.5 UNDER` to cztery odczyty
jednego zdania „czy w tym meczu padają gole", nie cztery wiersze. Rodziny:
`scoring` (gole, xG), `attacking` (strzały, rogi, spalone), `discipline`
(kartki, faule), `tennis_length` (gemy, sety), `tennis_serve` (asy, podwójne).

**PUŁAPKA — limit rodziny nie może wyrzucić wiersza VALUE na rzecz gorszego.**
W obrębie rodziny slot wygrywa wiersz z **największą nadwyżką ceny**, nie
z największym rozjazdem prawdopodobieństwa. `simple` miał tu błąd, przez który
slot wygrywał wiersz, który progu nie przechodził.

---

## 7. Etapy implementacji

Jeden etap = jeden PR = jeden raport (sekcja 10) = jedno review operatora.
**Nie zaczynaj etapu N+1 przed review etapu N.**

| # | Etap | Dostarcza |
|---|---|---|
| E0 | Szkielet, konfiguracja, zasada nieprzecinania | `pyproject`, `config.py`, `timeutil.py`, T00 |
| E1 | `SofascoreClient` | transport, limity, breaker, log |
| E2 | Baza i cache | `db.py`, migracja, `sofa_entity`, `sofa_event_stats` |
| E3 | BOARD | `01_board.json` |
| E4 | RESOLVE | `02_fixtures.json` + złoty zbiór |
| E5 | Mapowanie metryk | `metrics.py` + wszystkie pułapki z sekcji 5 |
| E6 | SAMPLES | `03_samples.json` |
| E7 | OFFER | `04_offer.json` |
| E8 | SHEET | `05_sheet.json` + silnik z sekcji 6 |
| E9 | COUPON | `06_coupon.json/.md` + `VETO_V1` |
| E10 | Backfill i rozliczanie | `sofa_settled_row`, dziesiątki tysięcy wierszy |
| E11 | Fit stałych | własna kalibracja, `K`, `LADDER_SIGMA`, baseline'y lig |
| E12 | Hardening + e2e + baseball (pomiar) | pełny zestaw, raport |

---

### E0 — Szkielet i zasada nieprzecinania

**Pliki:** `pyproject.toml`, `src/bet/sofa/{__init__,config,timeutil,errors}.py`,
`tests/sofa/test_isolation.py`, `tests/sofa/conftest.py`.

**AC:**
- `curl_cffi>=0.7,<1` w `[project.dependencies]`; `pip install -e .` w czystym
  venv kończy się sukcesem — **zapisz output**.
- **T00 (test izolacji):** przechodzi po AST wszystkich plików w
  `src/bet/sofa/**` i `scripts/sofa/**`, zbiera każdy `import` / `from … import`
  i **failuje**, jeśli którykolwiek moduł zaczyna się od `bet.simple_stats`,
  `bet.discovery`, `bet.api_clients` (poza `bet.sofa`), `bet.db`, `bet.stats`,
  `bet.enrichment`, albo jeśli ścieżka pliku wskazuje na `scripts/simple`.
  Test musi też wykrywać `importlib.import_module("bet.simple_stats…")` —
  sprawdź literały stringowe przekazywane do `import_module`.
- `conftest.py` z guardem sieciowym: fixture `autouse`, który podmienia transport
  na rzucający `RuntimeError("network access in unit test")`. Żaden test w
  `tests/sofa/` nie wychodzi do sieci.
- `ruff` i `mypy --strict` czyste.
- `SofaConfig.from_env()` ma test na każdą wartość domyślną z tabeli I4.

---

### E1 — `SofascoreClient`

**Pliki:** `src/bet/sofa/client.py`, `tests/sofa/test_client.py`.

Metody: `search(q)`, `entity_events(entity_id, kind, page)`, `event(id)`,
`event_statistics(id)`, `event_incidents(id)`.
Transport za `Protocol`, wstrzykiwany w testach. `curl_cffi` z
`impersonate="chrome124"` i `Referer: https://www.sofascore.com/`.

**Reguła błędów — precyzyjnie, bo tu było najłatwiej o pomyłkę:**

| Odpowiedź | Wynik | Licznik breakera |
|---|---|---|
| 200 + JSON | dane | reset |
| **404** | `None` — legalny brak zasobu | **reset** |
| 403, 429, 5xx | `None` + `PROVIDER_ERROR` | +1 |
| HTML zamiast JSON (Cloudflare) | `None` + `PROVIDER_ERROR` | +1 |
| timeout połączenia | jeden retry z backoffem; potem `None` | +1 dopiero po retry |

404 **nie jest błędem**: `/event/{id}/statistics` na meczu zaplanowanym zwraca
404 (to poprawna odpowiedź „brak agregatów"), `/team/{id}/events/next/0` zwraca
404 dla drużyny bez nadchodzących meczów (potwierdzone —
`evidence/team_8473_events_next_0.json`), a 56 z 1000 odpowiedzi w teście
obciążeniowym to właśnie takie 404. Wliczanie ich do breakera zamyka obwód na
normalnym porannym slate'cie.

**AC:**
- `pytest tests/sofa/test_client.py` — 0 failed, zero sieci. Przypadki: każdy
  wiersz tabeli powyżej; po `SOFA_BREAKER_THRESHOLD` kolejnych błędach czwarte
  wywołanie **nie dociera do transportu** (assert na liczniku mocka);
  404 po dwóch błędach zeruje licznik.
- Test tempa z fake-clockiem: 30 żądań przy `TARGET_RPS=10` zajmuje ≥ 2,9 s.
- Każde żądanie pisze wiersz do `run.log.jsonl` — test na kształt wiersza.
- **Live smoke:** 30 żądań na realne id z `evidence/`, log zapisany do
  `docs/sofascore-api/evidence/impl_e1_smoke.jsonl`. Raportuj rozkład statusów
  i median czasu.

---

### E2 — Baza i cache

**Pliki:** `src/bet/sofa/db.py`, `src/bet/sofa/cache.py`, `tests/sofa/test_db.py`,
`tests/sofa/test_cache.py`.

**AC:**
- `migrate()` idempotentna — uruchomiona dwukrotnie na tej samej bazie nie
  zmienia schematu (porównaj `sqlite_master` przed i po).
- **`sofa_event_stats` jest trwały:** drugi `enrich` tego samego dnia wykonuje
  **zero** żądań `/event/{id}/statistics` (T13, assert na liczniku transportu).
- `sofa_entity_events` respektuje TTL — test z fake-clockiem.
- `sofa_entity`: `status='verified'` ustawiany **wyłącznie** po znalezieniu
  eventu potwierdzonego datą i przeciwnikiem, nigdy w momencie wyszukiwania.
  `rejected` nigdy nie jest zwracany jako trafienie.
- **Test normalizacji rezerw:** `"CA Boca Juniors (R)"`, `"Boca Juniors II"`
  i `"Boca Juniors"` dają **trzy różne** `query_key`. Sklejenie ich to fałszywe
  dopasowanie gorsze niż jego brak.

---

### E3 — BOARD

**Pliki:** `src/bet/sofa/superbet.py` (własny, minimalny klient — **nie**
importuj `bet.api_clients.superbet`), `src/bet/sofa/board.py`,
`scripts/sofa/run_board.py`, `tests/sofa/test_board.py`.

Własny klient Superbetu to ~150 linii: jeden endpoint prematch po oknie czasu
i jeden po liniach fixture'u. Separator nazw to **U+00B7 MIDDLE DOT** (`·`),
nie kropka i nie myślnik — rozdzielenie po złym znaku daje jednostronną nazwę,
która nie dopasuje się do niczego. Sport id: piłka 5, tenis 2.

**AC:**
- `pytest tests/sofa/test_board.py` — 0 failed, na nagranym payloadzie.
- `kickoff_utc` jest aware i w UTC; test z payloadem, w którym czas lokalny ≠ UTC.
- Bez capa na liczbę fixture'ów. Cap na tym etapie zamieniałby fixture'y
  wyceniane w „nie na tablicy" — `simple` zmierzył 9 takich na jednym dniu.
- **Live:** `run_board.py --date <dziś>` → raport z liczbą fixture'ów per sport
  + porównanie z `simple`'owym artefaktem oferty z tego samego dnia. Różnica
  > 5% oznacza zły filtr sportów, nie mniejszy dzień.

---

### E4 — RESOLVE

**Pliki:** `src/bet/sofa/resolve.py`, `src/bet/sofa/names.py`,
`config/sofa_name_aliases.json`, `scripts/sofa/run_resolve.py`, testy T04–T07.

**Algorytm — dokładnie ten:**

1. `split_match_name` po `·` → `(side_a, side_b)`.
2. Normalizacja (`names.py`) — **tu, nie później**:
   - **Fold diakrytyków, który nie kasuje liter.** `ø`, `ł`, `đ`, `ı`, `æ`, `ß`
     nie mają dekompozycji NFD i naiwny `unicodedata.normalize('NFD')` +
     odfiltrowanie non-ASCII zamienia je w **spację**, rozbijając token na dwa.
     `simple` na tym stracił dopasowania na 752 wierszach. Użyj jawnej tabeli
     podstawień (`ø→o, ł→l, đ→d, ı→i, æ→ae, ß→ss, ð→d, þ→th`) **przed** NFD.
     Test T06 sprawdza dokładnie te znaki.
   - **Polskie nazwy krajów i reprezentacji.** `"Chiny (K)"` → `China W`,
     `"Wietnam (K)"` → `Vietnam W`, `"Hongkong (K)"` → `Hong Kong W`,
     `"Francja U20"` → `France U20`. `(K)` to drużyna kobiet, nie część nazwy.
     Cztery pierwsze porażki piłki w `evidence/per_fixture_match_test.json` to
     dokładnie ta klasa.
   - **Rezerwy:** `(R)` ↔ ` II` / ` B` / ` U21` → wspólny, **jawny** marker.
     Nigdy nie usuwaj markera po cichu.
3. Cache (E2). Trafienie `verified` → bez `/search/all`.
4. Pudło → `/search/all?q={side_a}`, weź **do 3** wyników `type == "team"`
   (w tenisie zawodnicy też są `type: "team"`). **Nigdy `results[0]`** —
   `evidence/league_search_disambiguation.json`: `championship` → FIFA World Cup,
   `brazil serie b` → Serie A, `pro league` → Saudi Pro League.
5. Dla każdego kandydata: `/team/{id}/events/next/{0..2}` **oraz**
   `/events/last/{0..2}`. Obie strony są potrzebne: mecz rozpoczynający się dziś
   może już przejść z `next` do `last`. Listing jest **rosnąco po czasie**,
   `page 0` to najbliższe/najnowsze, wyższa strona = starsza
   (potwierdzone: `last/0` 2026-02→2026-09, `last/10` 2021, `last/50` 2000).
   Strony 0–2 i koniec — mecz poza pierwszymi ~90 wydarzeniami oznacza złego
   kandydata, nie problem paginacji.
6. Dopasowanie wymaga **obu** warunków: `|startTimestamp − kickoff| ≤ 24 h`
   (aware) **i** zgodność nazwy przeciwnika (fold + fuzzy, próg 0,85 `rapidfuzz`).
7. Sukces → encja `verified`, `/event/{id}` → wypełnij `Fixture` (sekcja 4),
   w tym `ground_type`, `best_of`, `referee`, `round_*`, `previous_leg_event_id`.
8. **Deduplikacja po `sofascore_event_id`** — dwa `superbet_event_id` na jeden
   event to jeden `Fixture` z dwoma wpisami w `superbet_event_ids` (A2).
9. Dwaj kandydaci → dwa różne eventy w oknie → `AMBIGUOUS_ENTITY`, fixture
   wypada. Bez zgadywania.
10. Brak dopasowania → `GapReason`, fixture wypada.

**Złoty zbiór — i dlaczego `per_fixture_match_test.json` nim nie jest.**

Ten plik zapisuje **wyjście algorytmu**, nie prawdę. Jego wiersze to
`match_name`, `sofascore_id`, `tournament`, `round`, `success` — **bez daty
meczu, bez nazw drużyn zwróconych przez Sofascore i bez niezależnie
potwierdzonego oczekiwanego id**. Zatem:
- dopasowanie do **innego meczu tej samej drużyny** jest w nim nieodróżnialne
  od sukcesu — a to jest właśnie ta porażka, która kosztuje pieniądze, bo
  buduje dossier z cudzego meczu;
- plik mierzy **recall**; **precision jest niezmierzona**;
- nie zawiera par request→response, więc **nie da się z niego zrobić testu
  offline**.

Zbuduj `tests/fixtures/sofascore/golden_matches.json`: 60 fixture'ów (40 piłka,
20 tenis) z realnego boardu, każdy z **pełnym dowodem** — nazwa i kickoff
z Superbetu, `sofascore_id`, `startTimestamp`, `homeTeam.name`, `awayTeam.name`,
`tournament.name` — a następnie **przejrzyj listę ręcznie** i oznacz każdy wpis
`expected: "match" | "no_match"` + `expected_sofascore_id`. To jest praca do
wykonania, nie formalność. Do tego zapisz surowe payloady, żeby test był offline.

**AC:**
- **T04: precision ≥ 0,98** na złotym zbiorze (≤ 1 fałszywe dopasowanie na 60).
  Fałszywe dopasowanie **blokuje etap**.
- T05: dla każdej ligi z `league_search_disambiguation.json` wybór po
  `category.country`, nie `results[0]`.
- T06: fold nie kasuje `ø ł đ ı æ ß ð þ`; okno ±24 h aware; 30 h odrzucone.
- T07: `AMBIGUOUS_ENTITY` przy dwóch kandydatach; deduplikacja dwóch
  `superbet_event_id` na jeden event.
- L1 (live, marker `sofa_live`, poza CI): recall na
  `per_fixture_match_test.json`. Oczekuję **poprawy** wobec 80,4%/98,3%, nie
  utrzymania — normalizacja z kroku 2 powinna odzyskać większość z 28 porażek
  piłki. Raportuj rozkład `GapReason` przed i po.
- `02_fixtures.json` waliduje się własnym modelem.
- **`ground_type` i `best_of` niepuste dla ≥ 99% fixture'ów tenisa;
  `round_number` niepuste dla ≥ 95% fixture'ów piłki.**

---

### E5 — Mapowanie metryk

**Pliki:** `src/bet/sofa/metrics.py`, testy T08–T11.

Zaimplementuj sekcję 5 w całości. Tabela mapowania jest **stałą w kodzie**
(`Final[dict]`), nie wiedzą w głowie.

**AC:**
- **T08a:** tożsamość `shotsOnGoal + shotsOffGoal + blockedScoringAttempt ==
  totalShotsOnGoal` na nagranym payloadzie; `shots_on_target_total` = 7 (6+1),
  a **nie** 24, dla `event_16363633`.
- T08b: wyszukiwanie klucza jest płaskie po grupach — `offsides` znalezione
  mimo że siedzi w `Attack`.
- T09: `aces_total` = suma obu stron (2+7=9), nie 2. `games_total` = 35
  z `gamesWon`, **nie** 34 z `serviceGamesTotal`; test zawiera ten dowód
  liczbowy jako assert.
- T10: punkty kartkowe wg 5.4; kartka z `rescinded: true` **nie liczy się**;
  brak payloadu `/incidents` → `NO_INCIDENTS`, nigdy 0. Plus fixture z drugą
  żółtą (5.4a) i udokumentowana rozstrzygnięta wartość.
- **T11 (anty-fabrykacja, property test):** iteruje po **wszystkich** plikach
  `tests/fixtures/sofascore/statistics_*.json`; dla każdego brakującego klucza
  wynik **nie zawiera** `value == 0.0` dla tej metryki, a **zawiera**
  `GapReason.STAT_KEY_ABSENT`. To jest bezpośrednia ochrona przed powtórką
  z 2026-09-12, gdzie zmyślone fallbackowe próbki dały 43 z 64 wierszy VALUE.
- T08c: gole i połówki czytane **z listingu**, nie ze `/statistics` — test
  sprawdza, że mapowanie goli działa na payloadzie, w którym `/statistics`
  w ogóle nie ma.
- Tożsamości z 5.5 — cztery blokujące, jedna raportowana.

---

### E6 — SAMPLES

**Pliki:** `src/bet/sofa/samples.py`, `scripts/sofa/run_samples.py`, T12–T14.

Implementuje 6.1. Pobiera **tylko metryki, które mają cenę** (A5).

**AC:**
- T12: mecz z `startTimestamp` **po** kickoffie dzisiejszego fixture'u nigdy nie
  wchodzi do próbki.
- T13: drugi przebieg tego samego dnia — **zero** żądań statystyk.
- T14: `READY` osiągalne na realnym dniu dla **obu** sportów (3.3).
- Tenis: próbka filtrowana po `ground_type` **i** `best_of`; test na to.
- Deduplikacja: jeden mecz historyczny = jedna obserwacja `_total`, choćby
  występował w `side_a`, `side_b` i `h2h`.
- **Live:** pełny `run_samples` na realnym dniu. Raportuj: rozkład `readiness`,
  top 10 `GapReason`, liczbę żądań z cache'em i bez, medianę `sample_size`
  per metryka.

---

### E7 — OFFER

**Pliki:** `src/bet/sofa/offer.py`, `scripts/sofa/run_offer.py`, T16.

Pobiera drabiny cenowe dla fixture'ów z `02_fixtures.json` po
`superbet_event_ids` (join tożsamościowy, bez porównywania nazw — A2).

**AC:**
- T16: każdy `Fixture` z `superbet_event_ids` dostaje drabinę albo jawny
  `NO_PRICE`; żadnego dopasowania po nazwie w kodzie (grep w teście).
- Nierozpoznane nazwy rynków **lądują w osobnej liście** `unmapped_markets`,
  nie znikają. Rynek, który Superbet dodał, ma się pojawić jako diagnostyka.
- `fetched_at_utc` na każdym szczeblu — bez tego nie da się wyegzekwować A4.

---

### E8 — SHEET

**Pliki:** `src/bet/sofa/engine.py`, `scripts/sofa/run_sheet.py`, T17–T21.

Implementuje sekcję 6. Osobne, testowalne funkcje:
`predictive_sd`, `winning_boundary`, `p_central`, `p_low`, `devig`,
`ladder_centre`, `bar_input`, `bar_probability`, `required_odds`, `edge`.

**AC (testy niezmienników — te łapią błędy, których testy przykładów nie łapią):**
- T17: `p_central(OVER) + p_central(UNDER) == 1` dla tej samej linii **przed**
  clampem; po clampie różnica ≤ 2·(1−0,95).
- T18: `p_central` jest **monotoniczne** po linii — OVER maleje, UNDER rośnie.
- T19: `required_odds` maleje monotonicznie z `p_bar`; `required_odds` przy
  `p_bar → 0` nie jest nieskończone (podłoga 0,01).
- T20: `predictive_sd(values)` > `sample_sd(values)` dla każdego `n ≥ 2`,
  a stosunek → 1 przy rosnącym `n`. Assert na `sqrt(1+1/5) ≈ 1,0954`.
- T21: linia całkowita → `winning_boundary` odsuwa się o 0,5 w obie strony;
  test, że masa pusha nie trafia do żadnej ze stron.
- T22: `devig` na jednostronnej cenie zwraca `None`, nie połowę.
- T23: `ladder_centre` = `None` przy <2 szczeblach i przy drabinie w całości
  po jednej stronie 0,5.
- T24: korekta kalibracyjna może wyłącznie obniżyć `p` (własność, nie przykład).
- T25: `edge` liczone z `p_central`, nie `p_bar` — test przez konstrukcję wiersza,
  w którym te dwie liczby się różnią.
- **Live:** `05_sheet.json` na realnym dniu. Liczba wierszy ≠ 0 dla rodzin:
  `goals_total`, `corners_total`, `cards_points_total`, `shots_on_target_total`
  (piłka); `games_total`, `sets_total`, `aces_total` (tenis). Rodzina z zerem
  wierszy = brak mapowania, nie brak danych — znajdź która.
- **Trzy fixture'y sprawdzone ręcznie:** dla 2 piłkarskich i 1 tenisowego
  rozpisz w raporcie pełną próbkę (data, przeciwnik, wartość) i potwierdź każdą
  liczbę **niezależnie na sofascore.com w przeglądarce**. To jedyny moment,
  w którym wyłapiesz transkrypcję przesuniętą o kolumnę.

---

### E9 — COUPON i kontrakt veta

**Pliki:** `src/bet/sofa/coupon.py`, `src/bet/sofa/veto.py`,
`scripts/sofa/run_coupon.py`, T26–T29.

`VETO_V1` — klucz **pełny od pierwszego dnia**:
```python
class Veto(BaseModel):
    sofascore_event_id: int          # nie hash nazwy — L20
    market: str | None               # None = cała rodzina
    subject: str | None              # nazwa gracza/strony; None = wszystkie
    line: float | None
    direction: Direction | None
    reason_class: Literal["SAMPLE_UNINFORMATIVE","CONTEXT","PRICE","OTHER"]
    reason: str
```
`reason_class == "SAMPLE_UNINFORMATIVE"` ustawia `force_weight = 0` w skurczu
(6.5 etap 3) — próbka uznana za nieinformatywną jest warta zero obserwacji,
czego żaden wzór na `n` nie wyrazi.

**AC:**
- T26: veto bez `subject` **nie** rozszerza się na wszystkich zawodników —
  test z 3 graczami, veto na jednego, dwa pozostałe wiersze przeżywają.
- T27: veto, które nie pasuje do żadnego wiersza, **jest raportowane jako
  `UNMATCHED_VETO`**, nie znika po cichu. `simple` miał 3 z 4 vet nie
  pasujących do niczego i nikt tego nie widział.
- T28: limit rodziny wybiera wiersz o **największej nadwyżce**, nie o
  największym rozjeździe — test z konstrukcją, w której te dwa się różnią.
- T29: wiersz z kickoffem w przeszłości nie trafia do kuponu; wiersz z ceną
  starszą niż `PRICE_MAX_AGE_MIN` dostaje `STALE_PRICE` i wypada.
- `06_coupon.md` zawiera dla każdego wiersza: próbkę, `centre`, `p_central`,
  `market_p`, `p_bar`, `required_odds`, `offered_odds`, `surplus` — **wszystkie
  liczby, z których da się odtworzyć decyzję**. Raport, który nie zgadza się
  z własną arytmetyką, to raport do wyrzucenia; generuj tekst z tych samych
  wielkości, na których liczy kod, nie z osobnego przebiegu.

---

### E10 — Backfill i rozliczanie

**Pliki:** `src/bet/sofa/settle.py`, `scripts/sofa/run_backfill.py`, T30–T32.

To jest etap, który daje `sofa` coś, czego `simple` nigdy nie miał: prawdę
naziemną w skali, **przed** pierwszym zakładem (A9).

Dla listy minionych dat i listy lig:
1. zbierz eventy (`/unique-tournament/{ut}/season/{s}/events/round/{n}` albo
   historia drużyn),
2. dla każdego zbuduj próbkę **na stan sprzed kickoffu** (te same filtry co 6.1),
3. policz `p_central` / `p_bar` dla siatki linii wokół środka próbki,
4. rozlicz realnym wynikiem, zapisz do `sofa_settled_row`.

**AC:**
- T30: rozliczenie jest **czyste** — funkcja `settle(actual, line, direction)`
  z testem tabelarycznym na wszystkie przypadki, w tym PUSH na linii całkowitej.
- T31: **brak wycieku przyszłości** w backfillu — próbka dla meczu z dnia D nie
  zawiera żadnej obserwacji z dnia ≥ D. To jest ten sam test co T12, ale na
  ścieżce backfillu, i musi być osobny, bo to osobny kod.
- T32: rozliczanie tenisa nie myli się na **nazwisku** — `"ret"` w
  `"Berrettini"` nie może zostać odczytane jako krecz. Szukaj statusu
  w `status.type` / `winnerCode`, nigdy w napisie nazwiska. (`simple` miał
  dokładnie ten błąd i blokował mu on każdy backtest tenisa.)
- **≥ 20 000 rozliczonych wierszy** w `sofa_settled_row` po tym etapie, z ≥ 8
  różnych lig i ≥ 3 miesięcy kalendarzowych. Jedna liga w jednej fazie sezonu
  to nie jest próbka.
- **Niezależna kontrola transkrypcji:** dla 20 losowych rozliczonych wierszy
  potwierdź `actual_value` ręcznie w przeglądarce. Rozliczanie prognozy wobec
  tego samego źródła, z którego pochodzi próbka, **nie wykryje systematycznego
  błędu transkrypcji** — ta kontrola jest jedynym miejscem, gdzie taki błąd może
  wyjść. Zapisz wynik jako plik.

---

### E11 — Fit własnych stałych

**Pliki:** `scripts/sofa/fit_constants.py`, `config/sofa_*.json`, T33–T35.

Z `sofa_settled_row` zbuduj **własne**:
- `sofa_league_baselines.json` — `{metric: {competition_id: mean, n}}`,
  klucz to `uniqueTournament.id`. Wpis poniżej 30 obserwacji → fallback do
  puli globalnej, nie zapisywany.
- `sofa_market_reliability.json` — `{market: {bucket p_central: realised, n}}`.
  Korekta stosowana **tylko** tam, gdzie ogon puli nie obejmuje zera; inaczej
  zero korekty i adnotacja. Korekta, która odpala na obu kierunkach, dopasowuje
  się do szumu, którego nie mierzy.
- `K_CENTRE`, `K_PRICE` — po siatce (0, 2, 5, 8, 10, 15, 25, ∞), kryterium:
  mediana błędu bezwzględnego `p_central` wobec realizacji. Wybierz **najmniejszą
  wartość na plateau**, nie minimum punktowe — krzywa jest płaska i błąd
  ufania próbce za bardzo jest tym, który już raz kosztował.
- `MAX_LADDER_SIGMA` — po rozliczonych wierszach, jako próg, powyżej którego
  realizacja wyraźnie odbiega od deklaracji.

**AC:**
- T33: fit jest **deterministyczny** — dwa przebiegi na tej samej bazie dają
  identyczne pliki (hash).
- T34: **bramka skalowo-niezależna.** Każde kryterium porównujące rozrzuty
  normalizuje przez własny rozrzut próbki. Pasmo na surowym stosunku odpala na
  wielkości liczby, nie na błędzie — `simple` miał ten błąd i wyglądał on jak
  wykrywanie problemu.
- T35: brak pliku konfiguracyjnego = brak korekty (identyczność), nie crash
  i nie wartość domyślna z sufitu. Problem konfiguracyjny ma degradować do
  starego zachowania, nie opróżniać środka.
- **Raport:** dla każdej stałej — wartość, krzywa, liczba wierszy, przedział.
  Każda liczba ze ścieżką do pliku.

---

### E12 — Hardening, e2e i pomiar baseballu

**Pliki:** `tests/sofa/test_e2e.py`, `scripts/sofa/check_schema.py`,
`scripts/sofa/audit_sample_bias.py`, T36–T42.

**Test e2e (T36) — pełny przebieg offline, bez sieci.** Nagraj komplet
payloadów dla **jednego dnia z 3 fixture'ami** (2 piłka, 1 tenis), wstrzyknij
transport odtwarzający, przepuść `run_pipeline` od `01_board` do `06_coupon`
i porównaj **wszystkie sześć artefaktów** z zamrożonymi wzorcami. To jest
jedyny test, który łapie regresje na granicach etapów.
AC: przechodzi w CI, < 10 s, zero sieci.

**Testy degradacji (T37–T39):**
- 403 na wszystkim → `FAILED` z czytelnym powodem, **żadnego artefaktu
  arkusza**, nigdy zawieszenia;
- `/statistics` pusty dla wszystkich meczów → `BLOCKED`, zero wierszy, nie zera;
- HTML zamiast JSON → `PROVIDER_ERROR`, breaker, `FAILED`.

**T40 — podłoga pokrycia.** Liczba fixture'ów `READY` dziś porównana z własną
kroczącą medianą z ostatnich 10 przebiegów, **per sport**. Spadek > 40% →
`PARTIAL` i jawny powód. Bez tego ciche pogorszenie dopasowywania (np. zmiana
zachowania `/search/all`) zmniejsza slate i nikt tego nie zauważy.
**Podłoga musi być liczona per sport** — wspólna mediana odpala na sporcie,
który akurat urósł, i milczy na tym, który padł.

**T41 — audyt obciążenia próbki.** `audit_sample_bias.py`: czy próbka mierzy tę
wielkość, którą bukmacher rozlicza. Minimum: kartki (żółte vs punkty), gemy
(z tie-breakiem vs bez), `_total` vs `_for`, mecze towarzyskie w próbce
ligowej, mieszanie nawierzchni w tenisie. Raport zapisany, każda flaga wyjaśniona.

**T42 — stabilność schematu.** `check_schema.py` uderza w ~10 realnych id
i sprawdza obecność kluczowych pól (`groundType`, `defaultPeriodCount`,
`shotsOnGoal`, `cornerKicks`, `incidentClass`, `roundInfo`, `referee`,
`uniqueTournament.id`). Zniknięcie pola to **błąd**, nie `data_gap` — API jest
reverse-engineered i nie ma SLA. Uruchamiaj przed każdym dniem produkcyjnym.

**Baseball — pomiar, nie kod.** Pobierz 50 realnych fixture'ów MLB z boardu
Superbetu, przepuść przez `resolve`, zmierz recall i sprawdź, czy
`/event/{id}/statistics` w ogóle zwraca `runs`/`hits`. Zapisz evidence.
Dopiero ten raport jest podstawą do decyzji o trzecim sporcie.

**Pozostałe AC:**
- `ruff` i `mypy --strict` czyste na całym `src/bet/sofa/**`.
- T00 (izolacja) nadal przechodzi — sprawdź, czy nic się nie wkradło.
- Pokrycie testami `src/bet/sofa/engine.py` ≥ 95% linii (to jest moduł, w którym
  błąd nie rzuca wyjątku, tylko zmienia liczbę).

---

## 8. Zestawienie testów

CI: `pytest tests/sofa` — **w 100% offline, zawsze**.

| # | Plik | Co utrwala |
|---|---|---|
| T00 | `test_isolation.py` | zero importów z `simple`/`discovery`/`db`/`api_clients` |
| T01–T03 | `test_client.py` | statusy, breaker (404 ≠ błąd), tempo, log |
| — | `test_db.py`, `test_cache.py` | idempotencja migracji, trwały cache statystyk, TTL listingu, `verified` tylko po potwierdzeniu, rezerwy nie kolidują |
| — | `test_board.py` | separator `·`, UTC, brak capa |
| T04 | `test_resolve_golden.py` | **precision ≥ 0,98** na złotym zbiorze |
| T05 | `test_resolve_disambiguation.py` | nigdy `results[0]` |
| T06 | `test_resolve_names.py` | fold nie kasuje `ø ł đ ı æ ß ð þ`; okno ±24 h |
| T07 | `test_resolve_dedup.py` | `AMBIGUOUS`; dwa superbet id → jeden fixture |
| T08 | `test_metrics_football.py` | 6+6+8=20; płaskie szukanie klucza; gole z listingu |
| T09 | `test_metrics_tennis.py` | `aces_total` = suma; `games_total` 35 ≠ 34 |
| T10 | `test_metrics_cards.py` | punkty kartkowe; `rescinded`; 404 ≠ 0 |
| T11 | `test_no_fabrication.py` | property po **wszystkich** fixture'ach: brak klucza → gap, nigdy 0.0 |
| T12 | `test_samples_no_leak.py` | zero wycieku przyszłości |
| T13 | `test_samples_cache.py` | drugi przebieg = zero żądań statystyk |
| T14 | `test_samples_readiness.py` | READY osiągalne dla obu sportów |
| T16 | `test_offer.py` | join po id; `unmapped_markets` nie znika |
| T17–T25 | `test_engine_invariants.py` | suma do 1, monotoniczność, push, `σ√(1+1/n)`, devig jednostronny, korekta tylko w dół, `edge` z `p_central` |
| T26–T29 | `test_coupon.py` | veto z podmiotem, `UNMATCHED_VETO`, rodzina po nadwyżce, kickoff i świeżość ceny |
| T30–T32 | `test_settle.py` | PUSH, brak wycieku w backfillu, „ret" w nazwisku |
| T33–T35 | `test_fit.py` | determinizm, skalowa niezależność, brak configu = brak korekty |
| T36 | `test_e2e.py` | **pełny przebieg 6 artefaktów, offline** |
| T37–T39 | `test_degraded.py` | 403 / puste / HTML → nigdy arkusz z liczbami |
| T40 | `test_coverage_floor.py` | podłoga per sport wobec własnej mediany |
| L1 | `test_live_recall.py` `@sofa_live` | recall na `per_fixture_match_test.json`, poza CI |
| L2 | `test_live_schema.py` `@sofa_live` | obecność pól kluczowych, poza CI |

Markery do dopisania w `pyproject.toml`:
```toml
markers = [
    ...,
    "sofa_live: live Sofascore calls, opt-in, never in CI",
]
```

**Weryfikacja live — po każdym etapie, nie na końcu:**

| Po etapie | Co uruchamiasz | Co raportujesz |
|---|---|---|
| E1 | 30 żądań smoke | rozkład statusów, median ms, plik `.jsonl` |
| E4 | resolve realnego dnia | recall per sport, rozkład `GapReason`, pokrycie `ground_type`/`best_of`/`round` |
| E6 | samples realnego dnia | rozkład `readiness`, top 10 gapów, żądania z/bez cache'u, mediana `sample_size` |
| E8 | sheet realnego dnia | wiersze per rodzina rynku + **3 fixture'y ręcznie w przeglądarce** |
| E9 | coupon realnego dnia | liczba VALUE, rozkład nadwyżek, pełna arytmetyka na każdym wierszu |
| E10 | backfill | ≥ 20 000 wierszy, ≥ 8 lig, ≥ 3 miesiące + **20 wierszy ręcznie** |
| E11 | fit | krzywe i przedziały każdej stałej |
| E12 | 3 pełne dni | e2e zielony, degradacja, podłoga pokrycia, schemat |

---

## 9. Katalog lekcji przeniesionych z `simple`

Każda lekcja to zdanie, powód i test, który ją utrwala. **Przepisz mechanizm od
nowa — do `simple` zaglądaj po uzasadnienie, nie po linijki.**

| # | Lekcja | Test |
|---|---|---|
| L1 | Zero od providera bywa „nie wiem"; mediana 0 to sygnał, nie dana | T11 |
| L2 | Zmyślona próbka fallbackowa raz dała 43/64 błędnych wierszy VALUE | T11 |
| L3 | Czerwonej kartki provider nie wypisuje jako 0 — brak payloadu ≠ zero | T10 |
| L4 | Rynek kartek to punkty, nie żółte | T10 |
| L5 | Gemy bez tie-breaka zaniżają jednokierunkowo | T09 |
| L6 | `_total` ≠ wartość jednej strony | T08 |
| L7 | Dom/wyjazd to prior, nie podział próbki; w tenisie i h2h nie istnieje | T17 |
| L8 | `p_low` zaniża o ~23 pp; próg buduje się na `p_central` | 6.3, 6.5 |
| L9 | Rozrzut próbki ≠ rozrzut predykcyjny | T20 |
| L10 | Linia całkowita to push, nie pół wygranej | T21 |
| L11 | Prior ślepy na ligę potrafi być całą przewagą | 6.2, E11 |
| L12 | Jeden mecz, dwa wpisy na tablicy — dedup po id źródła prawdy | T07 |
| L13 | Jeden wiersz opisuje jedną próbkę; sklejenie zakresów zawyża `sample_size` | 6.1 |
| L14 | Bramka nieosiągalna wygląda jak brak danych | T14 |
| L15 | Bramka musi być skalowo-niezależna | T34 |
| L16 | Rozjazd ceny adnotuje, rozjazd drabiny demotuje | 6.6 |
| L17 | `edge` liczony z centrum, nie z dolnego ograniczenia | T25 |
| L18 | Limit rodziny nie może wyrzucić lepszego wiersza | T28 |
| L19 | Brak filtra kickoffu — zakończone mecze lądują na szczycie arkusza | T29 |
| L20 | Veto bez pełnego klucza rozszerza się albo nie robi nic po cichu | T26, T27 |
| L21 | Timestamp bez strefy to timestamp w złej strefie | I6, T06 |
| L22 | Fold diakrytyków potrafi skasować litery i rozbić token | T06 |
| L23 | `results[0]` z wyszukiwarki bywa inną ligą | T05 |
| L24 | Recall bez precision to nie pomiar dopasowania | T04 |
| L25 | Cena czytana raz rano jest nieaktualna wieczorem | T29, A4 |
| L26 | Cap na etapie oferty zamienia „wyceniane" w „nie na tablicy" | E3 |
| L27 | Raport musi wynikać z tej samej arytmetyki, którą liczy kod | E9 |
| L28 | Testy potrafią wydać budżet produkcyjny | conftest, T00 |
| L29 | Akumulator nie ratuje nogi poniżej progu; 5 nóg po 87% to rzut monetą | 6.7 |
| L30 | Props przy cenach Superbetu były −30,5% — nie dodawaj metryk bez odbiorcy | 5.8 |
| L31 | „ret" w nazwisku odczytane jako krecz zablokowało cały backtest tenisa | T32 |
| L32 | Podłoga pokrycia liczona wspólnie milczy o sporcie, który padł | T40 |
| L33 | Analiza napisana po wyniku jest skażona — punkt decyzji jest przed meczem | E9 |

---

## 10. Kontrakt raportowania

W audycie Sofascore **trzykrotnie** deklarowana liczba nie zgadzała się
z surowym dowodem: „2300 req/s" bez pliku evidence, „~87 req/s" sprzeczne
z własnym logiem, „mamy już infrastrukturę cache" podpięta do innego podsystemu.
Do tego w tym planie znalazłem czwartą: `totalShotsOnGoal` czytane jako strzały
celne, co zawyżałoby rynek trzykrotnie. Ta sama zasada obowiązuje implementację.

Raport z każdego etapu zawiera:

1. **Diff** — dokładnie to, co zmieniono, nic ponadto.
2. **Output `pytest` zapisany do pliku.** Zdanie „testy przechodzą" bez pliku
   jest odrzucane bez czytania reszty raportu.
3. **Dla każdej liczby: ścieżka do pliku i komenda**, którą da się ją odtworzyć
   samodzielnie.
4. **Lista rzeczy niezrobionych i dlaczego.** Etap zdany częściowo i opisany
   uczciwie jest wart więcej niż etap zdany na papierze.
5. **Co w tym planie okazało się błędne.** Plan stoi na evidence z 2026-09-17
   i lekturze kodu; nie jest wyrocznią. Cztery pułapki z sekcji 5 znalazłem,
   czytając surowe payloady zamiast dokumentacji — rób tak samo.

Review operatora następuje **po każdym etapie**, przed startem następnego.
