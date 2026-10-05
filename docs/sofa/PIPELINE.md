# `sofa` — pełny opis pipeline'u

Jedyny obowiązujący pipeline w tym repozytorium. Statystyki: **Sofascore**.
Ceny: **Superbet**. Produkt: **`runs/sofa/<data>/KUPON_<data>.pdf`**.

Ten dokument opisuje przepływ w całości i w szczegółach: każdy etap, czym
płaci, co zapisuje, jaką bramkę stosuje i z jaką stałą. Jest źródłem
pochodnym — **źródłem prawdy jest kod**, a przy każdej liczbie napisane jest,
w którym pliku ona żyje. Gdy dokument i kod się rozejdą, rację ma kod, a ten
plik jest usterką.

Co czytać zamiast tego:
- chcesz przeprowadzić dzień → [`RUNBOOK.md`](RUNBOOK.md)
- chcesz zrozumieć rolę agentów → [`AGENTIC_FLOW.md`](AGENTIC_FLOW.md)
- chcesz zweryfikować gotowy kupon → [`VERIFY_PROTOCOL.md`](VERIFY_PROTOCOL.md)
- chcesz ruszyć stałą lub bazę ligową → [`CONFIG.md`](CONFIG.md)
- chcesz wiedzieć, co odpowiada API Sofascore → [`REFERENCE.md`](REFERENCE.md)

---

## 0. Najpierw: nazwy etapów

```
BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON
                                          ↘ CONFIDENCE ─────────────┐
   SHADOW / CS2 (migawki) → SPORT_IDENTITY → SPORT_CONFIDENCE ──────┤
                                                    COUPON_ASSEMBLY → PDF   ★ produkt
        w przebudowie, po OFFER, przed CONFIDENCE:  FIXTURE_CHECK
        (osobno, świadomie:)  SETTLE → FIT
```

**Nie ma etapu `DISCOVER`, `ENRICH`, `ANALYZE`, `MARKET_CONTEXT` ani
`TIPSTERS`.** To słownik wycofanego pipeline'u `simple`
(`scripts/simple/`, `src/bet/simple_stats/`, dokumentacja w `docs/legacy/`).
Oba pipeline'y **nie dzielą ani linii kodu, ani jednej nazwy etapu**, i nie
istnieje mapowanie między nimi. Sięgnięcie po słownik `simple` to najczęstszy
sposób na zmarnowanie pierwszego kwadransa sesji — zdarzyło się 2026-09-21
i jest powodem, dla którego ten akapit stoi na początku.

Źródło prawdy o kolejności: `DEFAULT_SEQUENCE` w `scripts/sofa/run_pipeline.py`
(kończy się na COUPON). `SETTLE` i `FIT` **nie są** w `DEFAULT_SEQUENCE` —
celowo. Poza sekwencją, ale w `STAGE_MODULES` (więc `--only X` działa):
`FIXTURE_CHECK` (`run_fixture_check.py`), `SPORT_IDENTITY`
(`run_sport_identity.py`), `SPORT_CONFIDENCE` (`run_sport_confidence.py`),
`COUPON_ASSEMBLY` (`build_coupon.py`), oraz `SETTLE`, `CS2`, `CS2_SETTLE`,
`SHADOW`, `SHADOW_SETTLE`. CONFIDENCE (`run_confidence.py`) i PDF
(`build_coupon_pdf.py`) to skrypty, nie moduły etapów — nie ma `--only
CONFIDENCE`.

| pojęcie | znaczenie |
|---|---|
| **fixture** | jeden mecz, klucz `sofascore_event_id` (int) |
| **metric** | mierzona wielkość, np. `corners_total`, `games_won_for` (30 piłkarskich w `FOOTBALL_METRICS`, 25 tenisowych w `TENNIS_METRICS`, 3 zawodnicze w `PLAYER_METRICS` z `src/bet/sofa/players.py`) |
| **subject** | czyja to wielkość; `""` dla metryk `*_total`, nazwa strony dla `*_for`, **nazwisko zawodnika** dla `player_*_for` |
| **rung / szczebel** | jedna linia rynku: (market, subject, line, direction) |
| **ladder / drabina** | wszystkie linie tego samego rynku wystawione przez Superbet |
| **p_central** | prawdopodobieństwo z naszej próbki; od 2026-10-05 07:15Z (epoka `stats_only`) bez ceny w środku |
| **p_bar** | p_central po korekcie kalibracyjnej, zmieszane z ceną rynku — cenowe, tylko dla `06_coupon.json` |
| **pewność** (`confidence`) | dolna granica zmierzonej realizacji kubełka krzywej — jedyna liczba, po której kupon sortuje i bramkuje |
| **model** (`forecast_p`) | rating / model wyniku / silnik CS2, nieskalibrowany; drukowany obok, nigdy nie bramkuje ani nie sortuje |
| **surplus** | `offered_odds − required_odds` |
| **leg / noga** | pojedyncza pozycja kuponu (singiel albo noga Bet Buildera), rankowana `confidence`, nie `p_central` |
| **builder** | Bet Builder: 2–4 legi z **jednego** meczu |

---

## 1. Mapa dnia

```
                    Superbet (publiczne, bez limitu)
                              │
                       ┌──────▼──────┐
                       │   BOARD     │  1 request, <1 s
                       └──────┬──────┘
                              │ 01_board.json          (BoardFixture[])
      most przeglądarkowy     │
      (Sofascore 403 bez niego)
                       ┌──────▼──────┐
                       │  RESOLVE    │  ~8 req/fixture
                       └──────┬──────┘
                              │ 02_fixtures.json       (Fixture[])
                       ┌──────▼──────┐
                       │  OFFER #1   │  Superbet; które rynki mają cenę
                       └──────┬──────┘
                              │ 04_offer.json          (FixtureOffer[])
                       ┌──────▼──────┐
                       │  SAMPLES    │  ~12 req/fixture — 80% czasu dnia
                       └──────┬──────┘
                              │ 03_samples.json        (FixtureSamples[])
                       ┌──────▼──────┐
                       │  OFFER #2   │  świeża cena pod próg
                       └──────┬──────┘
                              │ 04_offer.json  (nadpisane)
   config/sofa_*.json ──►┌────▼────┐
                         │  SHEET  │  offline, cała wycena
                         └────┬────┘
                              │ 05_sheet.json          (SheetRow[])
             vetoes.json ─────┼─────────────────┐
                       ┌──────▼──────┐    ┌─────▼──────────┐
                       │   COUPON    │    │  CONFIDENCE    │
                       └──────┬──────┘    └─────┬──────────┘
            06_coupon.json/.md│                 │ 08_confidence.json/.md
            06_dropped.json   │                 │
                              │           ┌─────▼───────────┐
             (NIE jest kuponem)           │ COUPON_ASSEMBLY │ ◄── 08_confidence_sports.json
                                          └─────┬───────────┘
                                                │ 11_coupon.json
                                          ┌─────▼──────┐
                                          │    PDF     │
                                          └─────┬──────┘
                                                │ KUPON_<data>.pdf  ★ produkt, 12_printed.json

   Sporty mierzone (od 2026-10-05 08:30Z):
     SHADOW / CS2 snapshots.jsonl ──► SPORT_IDENTITY (most) ──► sport_fixtures.json
                                  └─► SPORT_CONFIDENCE ──► 08_confidence_sports.json
   Złożenie (od 2026-10-05):
     08_confidence.json + 08_confidence_sports.json + vetoes/reads/read_requests
       ──► COUPON_ASSEMBLY ──► 11_coupon.json ──► PDF ──► KUPON_<data>.pdf + 12_printed.json

   D-1:  05_sheet + wyniki ──► SETTLE ──► 07_settled.json ──► data/sofa.db
                                                                  │
                                                     FIT (osobno) ──► config/
```

Pętla `SETTLE → data/sofa.db → FIT → config/ → SHEET` jest **jedynym**
miejscem, w którym jeden dzień wpływa na następny. Dlatego przeterminowany
plik konfiguracyjny jest cichy i kosztowny, a przefitowanie w środku dnia
psuje porównywalność z dniem poprzednim.

---

## 2. Etap 0 — most przeglądarkowy

Od 2026-09-17 Sofascore odpowiada **403 na każdego klienta nieprzeglądarkowego**
na prefiksie `/api/v1/`. Nie omija tego `curl_cffi`, nie omija tego żaden
odcisk TLS. Jedyna działająca droga to **prawdziwa karta przeglądarki** na
`sofascore.com` z userscriptem, który odpytuje lokalny serwer o zadania.

```
pipeline ──HTTP──► bridge_server.py (127.0.0.1:8787) ◄──polling── karta Chrome
   (src/bet/sofa/bridge_transport.py)                     (userscripts/sofascore-bridge.user.js)
```

- Uruchomienie: `.venv/bin/python scripts/sofa/ensure_bridge.py` (serwer
  w tle + 5 okien `launch_bridge_browser.py`, potem `check_bridge`).
- Kontrola: `.venv/bin/python scripts/sofa/check_bridge.py` — **`ok: true` to
  za mało.** Martwa karta nadal raportuje `ok`. Liczy się **wiek ostatniego
  pobrania** (`last_pull_age_s`).
- Okna: otwieraj je **`scripts/sofa/launch_bridge_browser.py`** (domyślnie 5).
  Karty **nie muszą być widoczne** — dawna reguła „trzy nienachodzące się okna
  na wierzchu" była obejściem błędu, nie wymogiem. Chrome klamruje `setTimeout`
  w ukrytej karcie do ≥1000 ms, a `pace()` w userscripcie właśnie na nim czeka,
  więc karta w tle chodziła ~1 req/s zamiast 2,86. Flagi startowe to usuwają:
  p90 obiegu spadł z 9 436 ms do 224 ms przy oknach **zminimalizowanych**.
  Chrome musi być przedtem całkiem zamknięty — to flagi tworzenia procesu.
- Tempo: `SOFA_TARGET_RPS` domyślnie **20**, `SOFA_MAX_CONCURRENCY` **5**.
  `SOFA_MAX_CONCURRENCY` **równa się liczbie okien** i nigdy nie schodzi
  poniżej: pomiar 2026-09-22 na pięciu oknach dał 3 → 0,15 req/s (p50
  20 138 ms), 5 → **11,67 req/s** (p50 354 ms), 8 → 11,72 (668 ms), 12 → 11,66
  (1010 ms). Powyżej liczby okien rośnie wyłącznie kolejka; poniżej most
  zapadł się 78-krotnie, bo bezczynne karty wracały do ówczesnego 20 s
  `/pull` (od 2026-09-23 jest to 1 s, a od 2026-09-29 `/pull` odpowiada w
  50 ms, gdy jakieś zadanie jest w karcie — pojedyncze żądanie zeszło z ~2 s
  do ~145 ms).
  Bucket musi stać **powyżej** pojemności kart (5 × 2,86 = 14,3 req/s).
  Wcześniejsze „plateau 3,9 req/s" było artefaktem przyrządu: skrypt rampował
  tylko `target_rps`, `max_concurrency` trzymał na 3, i mierzył jako latencję
  czas obejmujący własny token bucket. Oba błędy naprawione. Seria z 2026-09-17 (szczyt 550 req/s) to był **jeden** klient
  `curl_cffi` ze 100 workerami, bez przeglądarki — most takiego kształtu nie
  produkuje. **`MIN_INTERVAL_MS` nigdy nie obniżaj**: to tempo pojedynczego
  połączenia. Przepustowość bierze się z liczby kart.
- Bezpiecznik: 3 porażki pod rząd otwierają obwód (`breaker_threshold`),
  cooldown 30 s rosnąco do 300 s. `record_success` zeruje licznik — dlatego
  przebieg bez zakłóceń **nie testuje** bezpiecznika i nie wolno raportować,
  że „działa".

Bez mostu da się uruchomić wyłącznie **BOARD**, **OFFER** i etapy offline
(SHEET, COUPON, CONFIDENCE, PDF). RESOLVE, SAMPLES i SETTLE bez niego stoją.

---

## 3. BOARD — dzień z tablicy Superbetu

`src/bet/sofa/board.py`, `scripts/sofa/run_board.py --date <d>` →
**`01_board.json`**

To jest „discovery" tego pipeline'u: pytamy **bukmachera**, nie dostawcę
statystyk, co jest dziś do postawienia. Jedno zapytanie HTTP, poniżej sekundy,
bez mostu i bez Sofascore.

Filtry, w kolejności:
1. sporty spoza `SPORT_IDS = {"football": 5, "tennis": 2}` (`src/bet/sofa/superbet.py`);
2. deble tenisowe (nazwa zawiera separator pary);
3. kickoff poza dobą UTC dnia;
4. turnieje z `config/sofa_board_exclusions.json` (decyzja operatora, za co nie płacimy).

Pole po polu (`BoardFixture`): `superbet_event_id` (str), `sport`,
`match_name`, `side_a`, `side_b`, `kickoff_utc`, `tournament_id`, `category_id`.

**Pułapka kalendarzowa.** Rozmiar tablicy to kalendarz, nie awaria:
2026-09-20 (niedziela) — 1040 meczów piłki, 2026-09-21 (poniedziałek) — 102.
Zanim zgłosisz „tablica padła", sprawdź surową odpowiedź Superbetu.

---

## 4. RESOLVE — tożsamość meczu

`src/bet/sofa/resolve.py`, `scripts/sofa/run_resolve.py --date <d>` →
**`02_fixtures.json`**. **Most**, ~8 zapytań na mecz.

Dopina `sofascore_event_id` do meczu z tablicy: szuka encji (drużyna/zawodnik)
po nazwie, pobiera jej listingi (`next`/`last`, `LISTING_KINDS_BY_SPORT`)
i szuka zdarzenia, które pasuje obiema stronami i czasem.

Bramki dopasowania:

| stała | wartość | rola |
|---|---|---|
| `NAME_MATCH_THRESHOLD` | 82.0 | minimalny wynik podobieństwa nazwy |
| `NAME_EXACT_THRESHOLD` | 99.0 | próg „to na pewno ta sama nazwa" |
| `ORIENTATION_MARGIN` | 20.0 | o ile lepsze musi być dopasowanie odwrócone, by uznać zamianę stron |
| `MATCH_WINDOW_S` | per sport, domyślnie 24 h | dopuszczalny rozjazd czasu |
| `MATCH_LOGIC_VERSION` | 6 | stempluje **negatywny cache**; zmiana logiki unieważnia zapamiętane pudła (4: aliasy krajów, 5: wyszukiwanie bez „(w)”/„(r)”, 6 od 2026-10-01: końcowe „Reserve(s)” Sofascore składa się do „(r)” — „River Plate Reserve” wobec „CA River Plate (R)” dawało 75,9 przy progu 82) |

`MATCH_LOGIC_VERSION` to nie kosmetyka. Negatywny cache pamięta „szukaliśmy
i nie ma", co jest faktem o świecie tylko wtedy, gdy szukanie było poprawne.
2026-09-18 błędna bramka płci uczyniła 175 tenisistek nierozwiązywalnymi,
zapisała je jako pudła, a po naprawie RESOLVE wyprodukował **bajt w bajt
identyczny artefakt**, bo już nie zapytał.

Od 2026-10-01 **nazwa zweryfikowana** (`status = verified` w cache encji) jest
sprawdzana mimo świeżego wpisu w tabeli pudeł i nigdy nie dostaje pudła
zapisanego: jej „brak” znaczył „ten jeden mecz nie jest jeszcze w jej
listingu”, a nie „tej drużyny nie da się znaleźć”. Wcześniej pudło sprawdzane
jako pierwsze blokowało pytanie o znane id na siedem dni — 2026-10-01 ok. 26
nierozpoczętych meczów tenisowych (Tien–Hurkacz), w piłce Croatia U19 i Jerash.

Wynik na mecz: `identity: CONFIRMED | FUZZY` albo luka
(`NO_ENTITY_FOUND`, `AMBIGUOUS_ENTITY`, `NO_MATCHING_EVENT`).
**Zdrowy wskaźnik dopasowania: 72–90%.**

`Fixture` niesie m.in.: `home_name`/`away_name` i `home_entity_id`/`away_entity_id`,
`competition_name`/`competition_id`/`season_id`, `round_number`/`round_name`,
`cup_round_type`, `previous_leg_event_id`, `venue_name`, `referee`
(`RefereeRecord` — wypełniony na ~9% meczów, bo sędziego ogłasza się późno),
`ground_type` i `default_period_count` (tenis: nawierzchnia i format),
oraz **oba zegary**: `kickoff_utc` (Sofascore), `superbet_kickoff_utc`
i `kickoff_disagreement_h`.

**Dwa zegary to nie nadmiarowość.** W ITF Superbet podaje nominalne „nie
wcześniej niż", a Sofascore lokalny czas turnieju; rozjazd sięga **11 h**
i biegnie w złą stronę — *mecz zakończony wygląda na nadchodzący*. COUPON
bierze **wcześniejszy** z dwóch.

Mecz wystawiony na tablicy dwa razy: zegar Superbetu bierze się z pierwszego
listingu, **chyba że** ten pokazuje dokładnie 00:00:00Z, a drugi realny czas
(`resolve.merged_superbet_kickoff`). Superbet wystawia część meczów ITF na
00:00Z, zanim zna godzinę; 2026-10-01 trzy takie mecze miały w drugim
listingu 11:08Z, a bramka „wcześniejszy zegar” uznała je za rozpoczęte
i zdjęła wszystkie 168 wycenionych szczebli. Prawdziwa północ istnieje
(piłka południowoamerykańska), więc 00:00Z to zaślepka tylko obok innego
listingu tego samego meczu.

---

## 5. OFFER — co w ogóle ma cenę

`src/bet/sofa/offer.py`, `scripts/sofa/run_offer.py --date <d>` →
**`04_offer.json`**. Superbet, publiczne, bez limitu, bez mostu.

Biegnie **dwa razy w jednym dniu i to jest projekt, nie pomyłka**:

1. **przed SAMPLES** — żeby nie płacić mostem za metrykę, której nikt nie
   wycenia (A5). SAMPLES czyta ten artefakt (`metrics_from_offer`) i tylko dla
   nieobjętych nim meczów pyta Superbet na żywo;
2. **po SAMPLES, tuż przed COUPON** — żeby próg mierzył się wobec **świeżej**
   ceny. Kolejność siedzi w `DEFAULT_SEQUENCE`, a nie w głowie osoby
   uruchamiającej etapy, bo tak właśnie poranna cena trafia na wieczorny kupon.

Na mecz (`FixtureOffer`): `status: PRICED | NO_PRICE`, `rungs` (`PricedRung`:
`market`, `subject`, `line`, `over_odds`, `under_odds`, **`fetched_at_utc`**),
`unmapped_markets`, `price_collisions`.

`fetched_at_utc` jest per szczebel i to on decyduje później o `STALE_PRICE`
(limit **45 min**, `SofaConfig.price_max_age_min`).

**Błąd jednego listingu Superbetu to luka, nie `FAILED`** (od 2026-10-01).
Wcześniej jeden wyjątek (usunięte zdarzenie odpowiada 404) wychodził z
`fetch_offers` i wywracał cały OFFER, a z nim łańcuch. Teraz błąd trafia do
`OfferFetcher.errors`, podsumowanie etapu liczy go w `fetch_errors` (pierwsze
20 na stderr jako `OFFER_FETCH_ERROR`), a werdykt jest `PARTIAL`. Mecz,
którego **każdy** listing zawiódł, nie dostaje wpisu wcale — nie pustego —
żeby odświeżenie z filtrem nie nadpisało cen, które poprzedni plik wciąż ma.

**`unmapped_markets` to znany stan, nie usterka.** W `04_offer.json`
z 2026-09-21: **20 851** nieodwzorowanych nazw rynków wobec **4161**
wycenionych szczebli na 255 meczach (169 `PRICED`, 86 `NO_PRICE`). Liczba
zmienia się z każdym odświeżeniem oferty — rano tego samego dnia było ich
21 290 — więc cytuj ją z artefaktu, nie z pamięci. Rząd wielkości jest stały:
do naszych metryk mapuje się około **jednej dziesiątej** ekranu Superbetu
(`src/bet/sofa/market_mapper.py`). Wszystko, czego nie znamy, jest zapisane
z nazwą — po to, żeby dało się zmierzyć, co tracimy.

Flaga `--min-minutes-to-kickoff` ma znaczenie przy **późnym** odświeżeniu: bez
niej etap wycenia całą tablicę razem z meczami już rozegranymi (2026-09-20:
890 zakończonych meczów opłaconych, żeby dojść do 185 otwartych, ~90 minut).

---

## 6. SAMPLES — próbka, czyli cały koszt dnia

`src/bet/sofa/samples.py`, `scripts/sofa/run_samples.py --date <d>` →
**`03_samples.json`**. **Most, ~12 zapytań na mecz — grubo ponad godzina.**

Dla każdej strony meczu i każdej metryki, którą ktoś wycenia, pobiera
**ostatnie `sample_n = 10` zakończonych meczów przed kickoffem**
(`get_historical_events`) i wylicza z nich wartość metryki
(`process_historical_event`, `src/bet/sofa/metrics.py`).

Zakresy (scoping), zanim mecz historyczny wejdzie do próbki:
- **piłka:** mecze towarzyskie wypadają (`config/sofa_friendly_competitions.json`: 853, 1794 i od 30.09 28008 — towarzyskie klubowe kobiet); działa tylko w SAMPLES, więc próbka pobrana przed dodaniem id nadal je zawiera;
- **piłka, druga drużyna pod id pierwszej** (od 2026-10-02, `src/bet/sofa/reserve_squads.py`): mecze, które klub zagrał rezerwami / U23 w rozgrywkach bez osobnego bytu „B” (Londrina — Copa Paraná), wypadają z próbki drużyny. Rozstrzyga kolizja terminów: dwa mecze drużyny w rozgrywkach X w odstępie 6–44 h od meczu jej głównej ligi czynią całą parę (drużyna, X) drugim składem (krajowe i kontynentalne puchary: 0 kolizji na ~7 800 meczów), a w rozgrywkach z listy `config/sofa_reserve_competitions.json` — główna liga drużyny z `reserve_when_main_in` (stanowe puchary Brazylii dla Série A/B, Copa Santa Fe dla Liga Profesional). Gdy mecz dnia sam jest meczem drugiego składu, strona zostaje pusta. Luka `RESERVE_SQUAD` mówi, co wypadło;
- **tenis:** mecz historyczny liczy się tylko, gdy
  `surfaces_comparable(event.groundType, fixture.ground_type)` **i**
  `infer_best_of(event) == fixture.default_period_count`. Na poziomie
  Challengerów i ITF te pola są najcieńszą częścią danych, a **`null` znaczy,
  że porównanie nie może się udać i zakres po prostu nie zadziałał** — nie że
  jest szeroki. Etykieta ogólna („Hard”, „Clay”) pasuje do każdej
  konkretnej z tej samej rodziny („Hardcourt outdoor/indoor”; „Red clay”,
  „Green clay”); dwie konkretne muszą się zgadzać. Do 2026-09-23 porównanie
  było dosłowne i 111 z 316 meczów tenisowych tego dnia (etykieta „Hard” lub
  „Clay”) miało przez to próby po 0–3 mecze.

`MetricSample` trzyma trzy listy: `side_a`, `side_b`, `h2h`. Jedna
`Observation` to `sofascore_event_id`, `match_date_utc`, `opponent`, `value`,
`competition_id`, `season_id`, `venue` (`home`/`away`/`None`).

**Które obserwacje trafiają do którego szczebla** — to decyduje `run_sheet.py`,
nie SAMPLES, i łatwo się na tym pomylić:

- rynek `*_total` (bez `subject`) **łączy** `side_a + side_b + h2h`
  i **deduplikuje po `sofascore_event_id`** — jeden mecz historyczny daje jedną
  obserwację, nawet gdy obie strony w nim grały;
- rynek `*_for` (z `subject`) czyta **wyłącznie stronę, którą nazywa**
  (`determine_side`). **H2H nie dociera do rynków per strona w ogóle** — to
  projekt, nie luka. Od 2026-10-01 dwie strony bliżej niż 10 pkt
  (`SIDE_MATCH_MARGIN`) to brak odpowiedzi (wcześniej tylko równość — „martinez”
  przy dwóch Martinezach szło do krótszego nazwiska; na 1 557 dopasowaniach z
  trzech dni 0 przypadków w marginesie), a w tenisie nazwisko, którego token sort
  nie umieścił (drugie imię, inicjał, człony sklejone, literówka — 6 drabin
  09-30), dostaje stronę tylko gdy jedna strona pasuje ≥ 90, a druga < 50;
- **nie ma filtra wieku wewnątrz próbki.** Ośmioletnie spotkanie h2h waży tyle
  samo, co zeszłomiesięczne. Wiek bramkują dopiero COUPON (`MAX_SAMPLE_AGE_DAYS
  = 60` na najświeższej obserwacji) i CONFIDENCE (180 dni na najstarszej), i to
  na poziomie całego kubełka, nie pojedynczego meczu.

Gotowość (`compute_readiness`, `min_sample = 5`):

| poziom | warunek |
|---|---|
| `READY` | **obie** strony mają ≥ 5 obserwacji tej metryki |
| `PARTIAL` | co najmniej jedna strona ma ≥ 1 |
| `BLOCKED` | żadna nie ma nic |

Gotowość meczu to jego **najlepsza** metryka — uczciwe tylko razem z mapą
per metryka, dlatego artefakt zapisuje obie.

Każda luka ma powód (`GapReason`): `NO_ENTITY_FOUND`, `AMBIGUOUS_ENTITY`,
`NO_MATCHING_EVENT`, `EVENT_NOT_FINISHED`, `NO_STATISTICS`, `NO_INCIDENTS`,
`STAT_KEY_ABSENT`, `ALL_ZERO_SAMPLE`, `OUTSIDE_MODEL_RESOLUTION`,
`INTERNAL_INCONSISTENT`, `ENTITY_CONFLICT`, `RESERVE_SQUAD`, `THIN_SAMPLE`,
`SURFACE_UNKNOWN`, `NO_PRICE`, `STALE_PRICE`, `PROVIDER_ERROR`,
`CIRCUIT_OPEN`. Awaria dostawcy blokuje
**mecz**, nie dzień. Od 2026-10-01 podsumowanie liczy
`provider_fault_fixtures` — mecze, które straciły metryki przez awarię
dostawcy i nie miały czego przenieść — i każdy taki mecz daje `PARTIAL`
(`samples_verdict`); wcześniej wyłącznik otwarty w połowie SAMPLES
przerzedzał dzień przy werdykcie `OK`.

**Incydenty meczu z cache.** `NULL` w `incidents_json` znaczy „nigdy nie
pytano”, nie „brak”: mecz zapisany dla meczu bez rynku kartek ma statystyki,
a nie ma incydentów, i każda późniejsza próbka kartek czytała go jako
`NO_INCIDENTS` bez pytania (2026-10-01: 118 luk na 59 zdarzeniach, wszystkie
`NULL`). Od 2026-10-01 SAMPLES raz pyta `/incidents`, gdy rynek kartek tego
potrzebuje; 404 zapisuje się jako `{}` (fakt, za który się już nie płaci)
i jest czytane jako „brak incydentów”. Awaria przy tym pytaniu kosztuje tylko
metryki kartek (`NO_INCIDENTS`), nigdy cały mecz.

**`coverage_floor` (`src/bet/sofa/coverage.py`) jest ślepy na dzień tygodnia.**
Porównuje z medianą ostatnich 10 przebiegów (`MAX_DROP = 0.40`), więc
poniedziałek — 102 mecze wobec niedzielnych 1040 — zawsze woła „matching
regression". Sprawdź wskaźnik RESOLVE (72–90%), zanim uwierzysz.

---

## 7. SHEET — wycena

`scripts/sofa/run_sheet.py --date <d>`, `src/bet/sofa/engine.py`
(+ `derived.py`, `joint.py`) → **`05_sheet.json`**. Offline, bez sieci.

Dla **każdego** szczebla, który ma próbkę i cenę, powstaje jeden `SheetRow`.
2026-09-21: 5782 wiersze (3160 tenis, 2622 piłka).

### 7.1 Łańcuch arytmetyczny

Od 2026-09-23 liga bez dopasowanej bazy nie jest już ściągana do średniej
globalnej (3,29 gola — wszystkie ligi świata), jeśli dzień ma jej własne mecze:
Gaucho Serie A2 miała w próbkach 72 mecze po 2,10 gola, a cena mówiła 2,1.
Punkty 2 i 3 nie dotyczą metryk połówkowych (`_1h_`/`_2h_`): Sofascore potrafi
źle podzielić gole na połowy przy dobrym wyniku końcowym (NPFL: 2:0 do przerwy
zapisane jako 0 + 5). Wiersz `_total` nie powstaje, gdy któraś strona ma mniej
niż `min_sample` własnych obserwacji — pula byłaby wtedy historią jednej
drużyny pod nazwą meczu (`THIN_SAMPLE`).

```
prior   = w tej kolejności (piłka):
          1. baza ligowa dopasowana               (config/sofa_league_baselines.json)
          2. średnia ligi z meczów w próbkach dnia, bez meczów wycenianego
             spotkania, ≥30 obserwacji            notka PRIOR_FROM_DAY_SAMPLES
          3. średnia lig, w których drużyny grają na co dzień (puchary)
                                                  notka PRIOR_FROM_TEAMS_LEAGUES
          4. mecz kobiet: pula lig kobiecych (config/sofa_women_competitions.json,
             ≥300 meczów)                          notka PRIOR_GLOBAL_WOMEN
          5. globalna
w_c     = n / (n + K_CENTRE)                           (piłka 25, tenis 2)
centre  = w_c·sample_mean + (1 − w_c)·prior            (albo sample_mean, gdy brak bazy)

p_central:
    metryki empiryczne (sets_total, games_won_for,
                        games_won_set{1,2,3}_for)   → częstość trafień w próbce;
                                                      tenis z drabiną: ściągnięta
                                                      ku market_p wagą n/(n+30)
    liczniki piłkarskie (NEGATIVE_BINOMIAL_METRICS) → ujemny dwumianowy wokół centre
    reszta                                          → normalny, podłoga nośnika −0.5
                                                      (COUNT_SUPPORT_FLOOR)
p_central ∈ [P_FLOOR 0.05, P_CEILING 0.95]; poza tym przedziałem szczebel jest
odmawiany (nierozwiązywalny), a nie przycinany do brzegu.

p       = max(0.01, p_central − max(0, calibration_correction))
market_p= zdevigowana cena Superbetu, metodą potęgową (DEVIG_METHOD = "power")
w       = n / (n + K_PRICE)                            (K_PRICE = 10.0, status NOT_FITTED)
p_bar   = w·p + (1 − w)·market_p                       (bez ceny: p_bar = p)
required_odds = 1.10 / p_bar                           (marża LEAN; CALL = 1.05)
surplus = offered_odds − required_odds
edge    = p_central − market_p
verdict = VALUE, gdy offered_odds > required_odds
```

Skąd która stała: `K_CENTRE` z `config/sofa_engine_constants.json` (FITTED:
globalnie 15, piłka 25, tenis 2); `K_PRICE` z tego samego pliku, gdzie ma
wartość `null` i status `NOT_FITTED` — wtedy silnik używa udokumentowanego
startu `K_PRICE = 10.0` z `engine.py`, a **każdy wiersz niesie o tym notkę
`UNFITTED_CONSTANTS`** (2026-09-21: 5782 z 5782).

### 7.1a Rating piłkarski i siła ligi (od 2026-09-30)

`centre` wiersza piłkarskiego to w połowie (`W_FOOTBALL_RATING = 0.5`) rating
atak/obrona drużyn (`src/bet/sofa/football_rating.py`). Stosunki ataku i obrony
są liczone względem ligi, w której mecz się odbył, więc są porównywalne tylko
między drużynami jednej ligi. FK Aktobe (kobiety, Kazachstan: 20:0, 15:0, 12:0)
dostało atak 2,54 i obronę 0,35 i w Europa Cup kobiet zostało wycenione
2,59 : 1,45 przeciw Ajaxowi, tydzień po porażce 0:8. Stąd trzy zmiany:

- **połączenie** — drużyny są `LINKED`, gdy obie zagrały ≥3 mecze
  (`LINK_MIN_MATCHES`) w rozgrywkach, które są ligą (najczęstszymi
  rozgrywkami) co najmniej jednej z nich. Wspólny puchar, który właśnie grają,
  nie wystarcza;
- **siła ligi** — dla par niepołączonych osobny współczynnik na (ligę, metrykę)
  w skali logarytmicznej, uczony tylko z meczów między ligami
  (`ALPHA_STRENGTH = 0.02`); gdy któraś liga ma <10 takich meczów
  (`MIN_STRENGTH_LINKS`), para jest `UNLINKED`;
- **limit zaskoczenia** — jeden wynik nie przesuwa stosunku o więcej niż
  `alpha·(MAX_SURPRISE − stosunek)`, `MAX_SURPRISE = 3`.

Mecze towarzyskie (`config/sofa_friendly_competitions.json`, 39 id) nie wchodzą
do historii ratingu. Mecz drugiego składu pod id pierwszej drużyny
(`reserve_squads`, od 2026-10-02) nie przesuwa ratingu żadnej ze stron — liczy
go tylko stawka rozgrywek, w których go zagrano. Liga zbyt rzadka na własną stawkę spada na globalną stawkę
**swojej płci**.

Pomiar (prognoza jeden mecz naprzód, poza próbą 2026-08-15..09-30, bez
towarzyskich): błąd kwadratowy spadł na każdej z 14 metryk — gole −0,36%,
faule −9,9%, spalone −1,4%, pary połączone siłą ligi −2,4% do −13%. Stałe
wybrano na 06-01..08-15 po błędzie środka, nie po prawdopodobieństwie — każdy
wiersz wyceniony ratingiem wymienia je w `UNFITTED_CONSTANTS`.

Po weryfikacji na żywo 10-01 (sofa-verifier) doszły jeszcze trzy rzeczy:

- **stawka ligi** jest zwykłą średnią, dopóki liga ma mniej niż ~50 meczów,
  a dopiero potem średnią wykładniczą (`LEAGUE_RUNNING_MEAN`). Wcześniej
  pierwszy mecz w cache ważył 32% po 57 meczach: Puchar Ligi ZEA miał
  2,1 gola na mecz zamiast 3,1 i dał dwa fałszywe „poniżej". Gole poza
  próbą −1,7%;
- **stosunki drużyny spoza ligi rywala** są ściągane ku 1 potęgą
  `CROSS_RATIO_POWER = 0.6` — zdobyte przeciw własnej lidze, przenoszą się
  tylko częściowo (Baio & Blangiardo 2010). Minimum płaskie 0,5–0,7;
- **rozrzut idzie za środkiem**: gdy prior albo rating przesuwa `centre`,
  wariancja i podłoga Poissona skalują się o `centre / sample_mean`
  (zachowany indeks dyspersji). Brier na 102 154 rozliczonych wierszach
  liczników 09-20..29: 0,1986 → 0,1982, lepiej w 8 z 10 dni.

Znane ograniczenie (zmierzone, nie naprawione): w skrajnych meczach słabej
ligi przeciw mocnej siła ligi uczy się wolno (`ALPHA_STRENGTH = 0.02` wygrywa
średnio; szybsze tempo psuje przeciętną prognozę). Aktobe - Ajax po
backfillu: 1,21 : 1,20 zamiast 2,59 : 1,45 — lepiej, ale daleko od 0:8.
Tam chroni głównie bramka `DISAGREES_WITH_PRICE`.

**Grupy regionalne (od 2026-10-02).** Jedno `uniqueTournament` Sofascore
potrafi trzymać kilka grup, które ze sobą nie grają (Kakkonen 11509: grupy
A/B/C jako osobne `tournament.id`; szwedzka Division 2 2026: sześć grup bez
`groupName`). Rating czytał takie rozgrywki jako jedną ligę, więc JBK
Pietarsaari (grupa C) i FC Honka (grupa B) były `LINKED` w barażu.
Teraz w obrębie (rozgrywki, sezon) drużyny łączą tylko mecze etapów
kołowych (`GROUP_STAGE_MIN_MATCHES = 3` meczów na drużynę); gdy powstają
≥2 składowe po ≥6 drużyn (`MIN_GROUP_TEAMS`) i ≥3 różnych rywali na drużynę,
każda składowa jest osobną „ligą" dla połączenia, domeny i siły ligi
(`assign_league_units`). Baraż ani puchar ich nie łączy — para z dwóch grup
jest `LINKED_BY_STRENGTH` dopiero przy zmierzonej sile obu grup, inaczej
`UNLINKED`. Stawka ligi i bazy `baselines` zostają na całe rozgrywki (jeden
poziom rozgrywkowy; podział tylko by je przerzedził). W cache 10-02: 684 z
11 719 par (rozgrywki, sezon), 177 711 meczów; żadna czołowa liga się nie dzieli.

Wiersz meczu `UNLINKED` dostaje notkę `CROSS_LEAGUE_UNLINKED` i CONFIDENCE
go odrzuca: ani próbka, ani rating nie opisują drugiej ligi, więc jedyną
liczbą porównującą obie drużyny jest cena (na rozliczonych 09-20..29 model
przegrywał tam z ceną o 0,0127 Briera wobec 0,0106 gdzie indziej). Na
tablicy 09-30 był to jeden mecz — właśnie Aktobe - Ajax.

Brak danych nie jest argumentem: `scripts/sofa/backfill_listings.py` pogłębia
historię każdej drużyny z cache (i każdego rywala) do 730 dni, porcjami i z
wznowieniem. Od 2026-10-01 naprawia też **przerwane łańcuchy stron**: strona 0
listingu jest zawsze najnowsza, więc gdy SAMPLES / RESOLVE odświeżają strony
0–2, głębsze strony starszego backfillu przestają się z nimi stykać, a mecze,
które w międzyczasie przesunęły się przez granicę, nie leżą na żadnej
stronie z cache (zawodnik 65576: strona 2 pobrana 09-28 sięgała 2025-10-31,
strona 3 pobrana 09-18 zaczynała się 2025-10-03). Encja z taką luką w oknie
nie jest „gotowa” i jest pobierana od pierwszej przerwanej strony
(`EntityState.first_gap`, margines `SHIFT_MARGIN_S` = 6 h; na cache z
2026-10-01, piłka, 730 dni: 874 encje z luką przy 0 h, 940 przy 6 h, 976 przy
24 h). `--dry-run` podaje `gapped` i `gapped_on_board` i czyta bazę tylko do
odczytu.

Statystyki meczów, które cache już zna, dociąga
`scripts/sofa/backfill_event_stats.py --sport {football|tennis} --days N`;
`--board-days N` (od 2026-10-01) zawęża to do meczów drużyn / zawodników
z ostatnich N tablic (artefakty RESOLVE), czyli stron, które faktycznie
wyceniamy. Wznawialny: zdarzenie już w `sofa_event_stats` (także zapytane
z 404) nie jest pytane ponownie.

### 7.1b Rating tenisowy (od 2026-10-01)

`config/tennis_rating.json` (`fit_tennis_rating.py --cut <d>`, między dniami):
8 cech plus wyraz wolny, osobno dla ITF / CH / TOUR, w tym `dhigh` i `dtour`
(udział meczów zawodnika powyżej ITF / w tourze) — jedna pula Elo dla
wszystkich poziomów przeszacowywała zawodnika z niższego poziomu o 3–24 pp.
Refit 2026-09-30 po backfillu (cut 2026-10-01, 239 315 meczów): poza próbą
09-17..30 Brier 0,1948 → 0,1884, TOUR 0,2055 → 0,1855. Rynki `games_total`,
`games_won_for`, `sets_total`, `handicap_games`:
`p_central = 0,25·rating + 0,75·market_p` (notka `TENNIS_RATING`). Dla TOUR i
CH tabela podobnych meczów pomija mecze rozstrzygnięte super-tie-breakiem
(liczonym jako 1 gem trzeciego seta; 5,1% meczów, prawie wyłącznie ITF).

### 7.2 Trzy rzeczy, które wyglądają na usterkę i nią nie są

1. `centre` to średnia **po skurczeniu** ku bazie ligowej. Porównanie jej
   z surową średnią próbki zawsze pokaże „rozjazd" — to `K_CENTRE` przy pracy.
2. `ladder_centre` / `ladder_sigma` opisują **drabinę bukmachera**, nie nasz
   rozkład. `ladder_sigma` rzędu 0,003 jest normalne.
3. Tenis (`sets_total`, `games_won_for`, `games_won_set{1,2,3}_for`) używa
   częstości empirycznej. Gdy szczebel ma drabinę Superbetu, ściąganie
   (`K_TENNIS_LADDER_CENTRE`) odbywa się **na prawdopodobieństwie**:
   `p = w·trafienia/n + (1−w)·market_p`, `w = n/(n+30)` — więc `p_central`
   zawsze leży między próbką a ceną (od 2026-09-23; przesuwanie próbki na
   środek drabiny traktowało medianę jak średnią i przestrzelało obie
   wielkości). Bez drabiny i bez przesunięcia `p_central` **równa się**
   trafieniom w próbce. Piłka idzie przez ujemny
   dwumianowy i różnić się **musi**; rozjazd powyżej ~15 pp znaczy, że pracuje
   baza ligowa, a nie drużyna — `n/(n+25)` mówi, ile naprawdę waży próbka.

### 7.3 Bramka drabiny

Szczebel bez mierzalnej drabiny nie może zostać `VALUE` — zostaje `LEAN`
z zapisanym powodem. Kontrola jest **bezskalowa**: porównuje rozrzut naszego
rozkładu z rozrzutem drabiny jako **stosunek**
(`MIN_SPREAD_RATIO = 0.5`, `MAX_SPREAD_RATIO = 2.0`), bo pasmo na wartości
bezwzględnej odpala się na wielkości próbki, nie na błędzie.

Notki, które to zapisują (realne liczności z 2026-09-21):
`NO_LADDER_CHECK` (72), `ONE_SIDED_LADDER` (72),
`LADDER_SPREAD_DISAGREES` (39), `LADDER_DISAGREES` (25),
`NO_PRICE_ANCHOR` (28), `PRICE_GAP` (1394), `UNREACHABLE_BAR` (706).

`UNREACHABLE_BAR` to osobna, uczciwa informacja: przy tej cenie i tym `n`
**żadna** próbka nie zrobiłaby z wiersza VALUE, bo `p` jest ograniczone przez
`P_CEILING` (`bar_is_unreachable`). Dotyczyło to 21% wycenionych wierszy piłki.

### 7.4 Rynki pochodne — obie strony naraz

`src/bet/sofa/derived.py` + `joint.py` wyceniają to, czego nie umie żaden
rozkład brzegowy: `both_over_<metric>` („każda z drużyn powyżej X"),
`most_<metric>` („najwięcej kartek"), `handicap_<metric>`.

Zależność jest **zmierzona, nie założona**: korelacja per metryka
w `config/sofa_side_correlations.json` (rożne **−0.279**, strzały **−0.439**
na 926 meczach). Niezależność zawyża P(obie powyżej) o ~9% względnych
i zawsze w stronę, która sprawia, że „tak" wygląda tanio. Konstrukcja: kopuła
gaussowska nad dwoma rozkładami brzegowymi (Poisson, gdy wariancja ≤ średnia;
ujemny dwumianowy, gdy większa), z parametrem rozwiązanym tak, by
*obserwowana* korelacja złożenia równała się zmierzonej.

Ograniczenie podane wprost: rynki porównawcze **nie mają drabiny**, więc przy
działającej bramce drabiny nie mogą dziś trafić do kuponu. To sufit, nie błąd.
Notki: `DERIVED` (1002), `MARKET_MARGINAL_JOINT`, `NO_MARKET_MARGINAL`,
`NO_MARKET_MARGINAL_CHECK`, `MARGINAL_DISAGREEMENT`.

### 7.4a Rynki zawodnicze — podmiotem jest człowiek

Dwie rodziny, które wyglądają podobnie i podobne **nie są**.

**Tenis — `games_won_set{1,2,3}_for`.** „1. set - Kenta Kawada liczba gemów".
Zawodnik w tenisie zawsze był stroną, brakowało tylko metryki na **pojedynczy
set**; bez niej `_SUBJECT_IS_SCOPE` słusznie odrzucał te rynki, bo jedyne, co
mogłyby wtedy dostać, to próbka z całego meczu (to defekt F29). Źródłem nie
jest `/statistics` — `gamesWon` nie ma tam klucza per set i brakuje go na 35%
meczów — tylko **wynik setowy z listingu** (`homeScore.periodN`), czyli składnik
niezmiennika, który `check_identities` i tak już egzekwuje. Zero dodatkowych
zapytań.

Rynek jest **dwustronny** (poniżej/powyżej na każdym szczeblu), więc daje się
odvigować, przechodzi bramkę drabiny i **może trafić do kuponu**.
2026-09-22: 827 wycenionych rynków na 166 meczach tenisowych, wszystkie
wcześniej lądowały w `unmapped_markets`.

Rozkład jest bimodalny — dolina na 5 (4,4%), ściana na 6 (45,6%), zmierzone na
80 149 meczach z cache'u (`docs/sofa/evidence/games_won_per_set_distribution.md`)
— a Superbet stawia szczebel na 5,5, dokładnie na urwisku. Dlatego te trzy
metryki od pierwszego dnia liczą się z **częstości empirycznej**, nie z krzywej
normalnej. To jest F49 powtórzone o jeden set niżej.

**Piłka — `player_shots_for`, `player_shots_on_target_for`,
`player_assists_for`.** „Zawodnik - liczba strzałów". To trzecia oś obok
`*_total` i `*_for`: podmiot nie jest żadną ze stron, a próbką są **występy
jednego człowieka**. Źródło to `/event/{id}/lineups` — jedno zapytanie na mecz
historyczny obsługuje cały skład (alternatywa, `/player/{id}/statistics`, to
200 zapytań na jeden mecz). Pobierane **tylko** wtedy, gdy oferta faktycznie
niesie szczebel zawodniczy: 2026-09-22 dotyczyło to 4 z 182 meczów piłkarskich.

Trzy pułapki, każda zamknięta w kodzie:

- Zawodnik z ławki, który nie wszedł, ma w payloadzie `totalShots: 0` i **nie
  ma** `minutesPlayed`. To nie jest zero — Superbet taki zakład **zwraca**,
  nie rozlicza. Bramką wejścia jest `minutesPlayed`.
- `onTargetScoringAttempt` bywa **pominięte**, gdy wynosi zero (6 z 31
  grających w nagranym payloadzie). Zero bierzemy tylko wtedy, gdy zamyka się
  tożsamość `totalShots == celne + niecelne + zablokowane + słupek`
  (31/31 w nagranym payloadzie); gdy się nie zamyka — `INTERNAL_INCONSISTENT`.
- `totalOffside`, `fouls`, `totalTackle` i `interceptionWon` też bywają
  pominięte przy zerze (obecne u 9–50% grających). Od 2026-09-29 zero
  udowadnia **suma drużyny**: suma grających równała się statystyce drużyny
  z `/statistics` w 98,9% (spalone), 97,7% (faule), 98,0% (odbiory) i 97,9%
  (przechwyty) z ~1550 meczów-drużyn. Zero bierzemy tylko w meczu, w którym
  ta suma się domyka; w pozostałych 1–2% to luka. Stąd nowe metryki
  `player_offsides_for`, `player_fouls_for` („liczba popełnionych fauli”),
  `player_tackles_for` („liczba odbiorów”), `player_interceptions_for`.
  „Faule na zawodniku” (`wasFouled`) domykają się z faulami rywala tylko w
  58%, więc **nie są** mapowane; „odbiory na zawodniku” nie mają klucza.

I ograniczenie, które decyduje o wartości całej rodziny: **Superbet kwotuje te
rynki jednostronnie**. 437 selekcji „powyżej" i **0** „poniżej" na tablicy
2026-09-22. Bez drugiej strony nie ma czego odvigować, `market_p` jest `None`,
więc `NO_PRICE_ANCHOR` zatrzymuje wiersz na `LEAN` i **żaden zakład
zawodniczy w piłce nie może dziś trafić do kuponu**. To jest zamierzone:
2026-09-19 nieukotwione wiersze miały medianę nadwyżki 4,95 wobec 0,24 dla
ukotwionych — to nie przewaga, to brak kontroli. Rodzina jedzie jako prognoza,
dopóki nie zmierzymy marży tych rynków na rozliczonych dniach.

Wiersz zawodniczy niesie notkę `PLAYER_MINUTES` (mediana minut, ile występów
60'+, ile z ilu meczów próbki) — bo próbka złożona z wejść na 12 minut i
próbka złożona ze startów to nie jest ta sama wielkość, a nic innego w wierszu
nie umiałoby tego powiedzieć.

**Od 2026-10-01 `player_assists_for`, `player_shots_on_target_for`
i `player_shots_for` liczą się rozkładem ujemnym dwumianowym**
(`engine.NEGATIVE_BINOMIAL_METRICS`), nie normalnym. Zmierzone na każdym
rozliczonym wierszu zawodniczym 2026-09-24..30: normalna arkusza dawała
medianowo +8 pp na każdym „powyżej” (asysty 0,5 powyżej: deklarowane 0,243,
zrealizowane 0,081, n = 495). ΔBrier NB wobec normalnej przy tym samym
środku i odchyleniu: asysty −0,03136 (n = 546), celne −0,01473 (1317),
strzały −0,00749 (2379); dwie pierwsze są poniżej progu n ≥ 2000 i weszły na
zgodnym znaku w obu połówkach (parzyste / nieparzyste id), jak wcześniej
metryki połówkowe.

„Liczba strzałów w obramowanie bramki” to strzały w słupek lub poprzeczkę,
a nie drużyna o nazwie „w obramowanie bramki” — od 2026-10-01 mapper nie
czyta jej jako strony (`_SUBJECT_IS_NOT_A_SIDE`; 13 szczebli 2026-10-01).

### 7.5 Werdykty

`VALUE` (przebija próg) · `LEAN` (blisko, ale bramka drabiny lub próg mówi nie)
· `BELOW_BAR` · `NO_PRICE` · `BLOCKED`.
2026-09-21: 118 VALUE, 300 LEAN, 5317 BELOW_BAR, 47 NO_PRICE.

---

## 8. `vetoes.json` — jedyny kanał analityka

Plik `runs/sofa/<data>/vetoes.json`, pisany **po SHEET, przed COUPON**,
czytany przez **COUPON i CONFIDENCE naraz** (oraz przez COUPON_ASSEMBLY dla
nóg sportów mierzonych — tam weto ma tylko kierunek OVER/UNDER, więc nazywa
cały mecz albo rodzinę; nogę sportu zdejmuje odczyt `NO_BET` w `reads.json`) (to drugie od 2026-09-21 — wcześniej
weto zdejmowało singla i zostawiało identyczny szczebel jako nogę Bet Buildera,
czyli w produkcie, który się stawia).

```json
[{"sofascore_event_id": 15275920, "market": "corners_total", "subject": null,
  "line": 9.5, "direction": "OVER",
  "reason_class": "SAMPLE_UNINFORMATIVE",
  "reason": "siedem z dziesięciu obserwacji sprzed zmiany trenera 12 sierpnia"}]
```

- `market` / `subject` / `line` / `direction` są **nullowalne, a `null` znaczy
  „wszystkie"** — i to jest normalny kształt, bo próbka, która nie opisuje
  meczu, jest zepsuta na każdym szczeblu.
- `reason_class` ∈ `SAMPLE_UNINFORMATIVE | CONTEXT | PRICE | OTHER`.
- Weto `CONTEXT` ma dodatkowo `context` — **jaki** kontekst: `MOTIVATION`
  (stawka meczu, punkty do obrony), `ROTATION` (rezerwowy skład), `ABSENCES`
  (brak podstawowych), `DERBY` (derby, rewanż), `SCHEDULE` (zmęczenie,
  terminarz), `CONDITIONS` (pogoda, boisko). Pole istnieje tylko przy
  `CONTEXT`; przy innej klasie plik nie przejdzie walidacji. W `reason` weto
  kontekstowe podaje domenę źródła i czas publikacji.
- Każdy zawetowany wiersz i tak jest rozliczany. `audit_settlement` (sekcja
  7e) i `scripts/sofa/audit_vetoes.py --from <d> --to <d>` pokazują, co weta
  wycięły — osobno dla każdej klasy i tagu, wobec reszty tablicy w tych samych
  przedziałach kursu. Weto zapisane po starcie meczu jest wyłączone z oceny.
- Model ma `extra="forbid"`: **wymyślony klucz** (`action`, `player`,
  `event_id`) wywraca **cały plik**, a etap rusza wtedy z **zerem** wet
  i melduje zero. Dlatego walidacja przed zapisem jest obowiązkowa.
- Weto, które nie trafia w żaden wiersz, jest drukowane jako `UNMATCHED_VETO`
  przez oba etapy i liczone w podsumowaniu — nigdy nie znika po cichu.
- **Weto może wyłącznie usuwać. W `sofa` nie istnieje promocja wiersza.**
- Obok wet: `reads.json` (`LegRead`, werdykt o nodze: KEEP / WATCH / NO_BET,
  od 2026-10-05 także strony sportów i `period`) — WATCH i NO_BET zdejmują
  nogę do `removed_by_reads` w `11_coupon.json` (rozliczana osobno, 7i); oraz
  `read_requests.json` — prośby operatora o dodatkowy odczyt (pozycja albo
  `group_key`), które poszerzają zbiór `legs_requiring_read`, nie wydruk.
  Szczegóły: [`AGENTIC_FLOW.md`](AGENTIC_FLOW.md), część 2.
- `[]` to zdrowa wartość domyślna i tak wygląda większość dni.

---

## 9. COUPON — single VALUE (to **nie** jest kupon)

`src/bet/sofa/coupon.py`, `scripts/sofa/run_coupon.py --date <d>
[--max-singles N]` → **`06_coupon.json`**, **`06_coupon.md`**,
**`06_dropped.json`**.

Ten etap niczego nie przelicza. Wybiera spośród wierszy `VALUE` i **mówi na
głos, dlaczego każdego niewybranego nie wybrał**.

### 9.1 Bramki, w kolejności wykonania

| # | powód odrzucenia | warunek |
|---|---|---|
| 1 | `NO_FIXTURE` | wiersza nie da się przypiąć do meczu z `02_fixtures.json` |
| 2 | `KICKOFF_TOO_SOON` | **wcześniejszy** z dwóch zegarów nie jest dalej niż **15 min** w przyszłości (`min_kickoff = now + 15 min`, `run_coupon.py`) |
| 3 | `ODDS_TOO_LOW` | `offered_odds < MIN_ODDS_FLOOR = 1.25` |
| 4 | `VETOED` | trafione weto z `vetoes.json` |
| 5 | `STALE_PRICE` | `fetched_at_utc` starsze niż **45 min** |
| 6 | `DISAGREES_WITH_PRICE` | `p_central − market_p > MAX_DISAGREEMENT = 0.10` — **`p_central`, nie `p_bar`** |
| 7 | `ABOVE_MEASURED_CEILING` | `p_central` ≥ zmierzony sufit kalibracyjny **tego** rynku |
| 8 | `STALE_SAMPLE` | najświeższy mecz w próbce starszy niż `MAX_SAMPLE_AGE_DAYS = 60` |
| 9 | `MAX_SINGLES` | limit dnia (domyślnie **brak**: `MAX_SINGLES = None`) |
| 10 | `MAX_PER_FIXTURE` | więcej niż **3** wiersze z jednego meczu |
| 11 | `FAMILY_SLOT_TAKEN` | druga pozycja z tej samej **rodziny mechanizmu** na tym meczu (limit **1**) |
| 12 | `NO_ODDS` / `NO_SURPLUS` | wiersz bez ceny lub bez nadwyżki dotarł tu mimo wszystko |

`DISAGREES_WITH_PRICE` to bramka **zmierzona**, nie ostrożnościowa. Na 6187
wierszach niosących realną cenę Superbetu (`coupon.py`, `confidence.py:37-51`):

| model − cena | n | model mówi | realizacja |
|---|---|---|---|
| +0,10–0,15 | 441 | 0,609 | **0,444** |
| +0,20–0,30 | 255 | 0,677 | **0,400** |
| +0,30 i wyżej | 328 | 0,800 | **0,451** |

Powyżej +0,10 realizacja spada **poniżej rzutu monetą**, podczas gdy
deklaracja dalej rośnie. Nadwyżka, po której ten etap rankuje, rośnie
dokładnie z tym rozjazdem — selektor koncentruje się więc w zmierzonym
obszarze ujemnym z konstrukcji. Zgoda z ceną jest sygnałem, niezgoda
anty-sygnałem.

Bramka istniała wyłącznie na ścieżce stawianej do 2026-09-21, więc plik singli
— ten, którego się **nie** stawia — był bardziej pobłażliwy z dwóch produktów
czytających ten sam arkusz.

### 9.2 Ranking — i tu dokumentacja bywała nieaktualna

Kolejność jest **dwustopniowa**:

1. **względna przewaga cenowa**: `surplus / required_odds` — nie surowy
   `surplus`. Surowa nadwyżka niesie człon `1/p`, więc przy tej samej jakości
   okazji długi strzał punktuje wielokrotnie wyżej (mediana nadwyżki spada 79×
   od najniższego do najwyższego pasma `p`, a względnej tylko 11× — reszta to
   skala). Ranking po surowej nadwyżce robił z kuponu skaner długich strzałów
   (mediana `p_bar` 0,129 wobec 0,225 po poprawce) akurat w ogonie, w którym
   `p` jest zawyżone.
2. **szerokość przed głębią**: wiersze sortowane po `(ile wierszy ten mecz już
   ma, ranga)`, więc najlepszy wiersz każdego meczu konkuruje przed drugim
   wierszem jakiegokolwiek innego. Limit — jeśli w ogóle ustawiony — ścina
   głębię, nigdy szerokość.

### 9.3 Antyselekcja — własność mechanizmu

Selekcja premiuje wiersz tym mocniej, im bardziej `p` jest **zawyżone**, bo
dokładnie to podnosi nadwyżkę. To nie hipoteza o konkretnym dniu, tylko
własność sortowania, więc: **nadwyżka powyżej +0,40 jest podejrzana
z definicji** — na płynnym rynku nie ma darmowych 40%. Każdą rozbierz ręcznie.

### 9.4 Dlaczego `06_coupon.json` nie jest kuponem

Ścieżka singli VALUE ma **zmierzony zły wynik**: **−20,4%** na 2026-09-20,
tego samego dnia, w którym Bet Buildery z PDF-a dały **+8,2%**. Na dysku leżą
trzy pliki, które nazywają się kuponem; stawia się **wyłącznie
`KUPON_<data>.pdf`**. Zaraportowanie `06_coupon` jako „kuponu" odwraca dzień.

---

## 10. CONFIDENCE — legi i Bet Buildery (to jest droga do produktu)

`src/bet/sofa/confidence.py`, `scripts/sofa/run_confidence.py --date <d>
[--profile standard|wariant] [--floor …] [--runs-dir runs/sofa]` →
**`08_confidence.json`**, **`08_confidence.md`**. `--floor` to
`BELOW_CONFIDENCE_FLOOR`; domyślnie **0,70** (`DEFAULT_FLOOR`, profil
`standard`).

**Epoka `stats_only` (od 2026-10-05 07:15Z, `bet.sofa.epochs`).** Pewność
jest wyłącznie ze statystyk: SHEET trzyma cenę poza `p_central`, a cena jest
tylko warunkiem zakładu — x = pewność × kurs ≥ 0,90, marża drabiny ≤ 15%,
`ODDS_TOO_LOW`, mecz niezaczęty, świeża cena. `DISAGREES_WITH_PRICE`
(`MAX_DISAGREEMENT`) i `UNREACHABLE_BAR` są wyłączone; przesunięta cena
przelicza x na świeżym kursie z `04_offer.json` zamiast odmowy
`PRICE_MOVED_SINCE_SHEET` (ta zostaje dla buildów starej epoki). Cienki
kubełek kierunku ogranicza także krzywą `by_market` (K13). Noga niesie
`forecast_p` / `forecast_source` (`football_rating`, `tennis_rating`; dla
sportów `score_model`, `cs2_engine`) — „model”, nieskalibrowany, nigdy
bramka. CONFIDENCE odmawia (kod 2) arkusza zbudowanego nie pod tą regułą —
przebudowa reguły zaczyna się od SHEET. Sortowanie singli:
`(-confidence, kickoff_utc, sofascore_event_id, market, line)`.

**Historyczne: wariant operatora (`--profile wariant`, 2026-09-23 –
2026-10-05).** Próg 0,65, x ≥ 0,90, marża do 15%, pliki
`08_confidence_wariant.json/.md` i `KUPON_<data>_WARIANT.pdf`, rozliczany w 7d.
Wycofany 2026-10-05 od 07:15Z: `--profile wariant` odmawia (kod 2) dla
późniejszych buildów; pliki do poranka 10-05 zostają i są rozliczane po
staremu.

COUPON pyta „czy to warte ceny". CONFIDENCE pyta **inne pytanie**: „jak często
to się w ogóle zdarza". Na 6187 wierszach z realną ceną model **przegrywa**
pierwszy spór z samą ceną (Brier 0,2067 wobec 0,1845), a na 1 868 474
rozliczonych wierszach jest skalibrowany do 0,3 pp wszędzie do ~0,90 — czyli
drugie pytanie potrafi odpowiedzieć, a pierwsze nie.

Dwie rzeczy, których ten etap nie robi, bo od nich wraca się do kuponu:
nie podaje **własnego** punktowego oszacowania (każda liczba to **dolna
granica** zmierzonej realizacji, więc cienki kubełek czyta się jako mniej
pewny, nie jako precyzyjniejszy) i nie twierdzi pewności — krzywa kończy się
na `CONFIDENCE_CEILING = 0.9202`, bo kubełki 0,900–0,925 i 0,925–0,950
realizują się identycznie (0,9083). Leg podany jako 0,98 byłby kłamstwem
o jakieś siedem punktów.

### 10.1 Bramki nogi, w kolejności

Pierwsze siedem to bramki dostępności i czasu — te same pytania co w COUPON,
ale **własne progi**, i jedno ważne odstępstwo:

| powód odmowy | znaczenie |
|---|---|
| `NO_PRICE` | szczebel bez ceny |
| `ODDS_TOO_LOW` | poniżej `MIN_ODDS_FOR_CEILING = 1/0.9202 ≈ 1.0867` — **nie** 1,25 jak w singlach. Poniżej tej ceny noga nie może mieć dodatniego EV przy tej krzywej, niezależnie od meczu |
| `NO_FIXTURE` | brak meczu w `02_fixtures.json` |
| `VETOED` | trafione weto |
| `KICKED_OFF` | wcześniejszy z dwóch zegarów jest bliżej niż `MIN_MINUTES_TO_KICKOFF` (15 min). Od 2026-09-23 OFFER, COUPON i CONFIDENCE czytają ten sam zegar (`effective_kickoff`) i ten sam margines; wcześniej CONFIDENCE nie miało marginesu, a OFFER filtrowało po samym zegarze Sofascore |
| `NO_FETCHED_AT` | szczebel bez znacznika pobrania ceny |
| `STALE_PRICE` | cena starsza niż 45 min |
| `NOT_IN_CALIBRATION_FIT` | metryka nie należy do rodziny, na której fitowano krzywą |
| `CROSS_LEAGUE_UNLINKED` | mecz piłkarski drużyn bez wspólnej ligi i bez zmierzonej siły ich lig (§7.1a) — decyzję oddajemy cenie |
| `DERIVED_NOT_CALIBRATABLE` | rynek pochodny (`both_over_`, `handicap_`, `most_`) — ma 2–252 rozliczonych wierszy i żadna próbka z artefaktów go nie sprawdzi |
| `NO_CLASS_CURVE` | noga klasy (`women`, `tennis_women`, `tennis_team_cup`), którą krzywe bez klasy by obsłużyły, ale klasa nie ma własnego kubełka |
| `NOT_CALIBRATED` | dla tego kubełka **nie ma pomiaru**; własna liczba modelu nie jest jego substytutem. Od 2026-09-30 także noga **klasy**, której nie obsłużyłaby żadna krzywa (inaczej `NO_CLASS_CURVE`): piłka kobiet (`women`, rozpoznawana po „(K)" Superbetu albo nazwie rozgrywek), tenis kobiet (`tennis_women`), Davis Cup / BJK Cup / pokazówki (`tennis_team_cup`). Noga klasy czyta wyłącznie krzywe swojej klasy (`by_class` w `config/sofa_confidence_calibration.json`, `fit_confidence.py --classes-only`) — nigdy puli, od której klasa się różni (piłka kobiet przy p 0,80–0,85: 0,792 wobec 0,806 mężczyzn; rożne przy 0,90: 0,874 wobec 0,903) |
| `BELOW_CONFIDENCE_FLOOR` | `realised_lo < --floor` |
| `DISAGREES_WITH_PRICE` | `realised_lo − 1/odds > MAX_DISAGREEMENT = 0.10` — **wyłączona w epoce `stats_only`** |
| `FIXTURE_NOT_AS_SCHEDULED` | `fixture_status.json` (FIXTURE_CHECK): mecz drukowany przełożony, odwołany albo przerwany |
| `NEGATIVE_LEG_EV` | noga nie przebija własnej ceny (`profile.clears_price`); od 2026-10-05: pewność × kurs < 0,90, w epoce `stats_only` na świeżym kursie |
| `LINE_BEYOND_SAMPLE` | linia leży poza wszystkim, co próbka widziała |
| `MODE_LOSES` | wartość modalna próbki przegrywa zakład |
| `THIN_SAMPLE_FOR_BUILDER` | mniej niż `MIN_BUILDER_SAMPLE = 10` obserwacji |
| `SAMPLE_CROSSES_SEASON` | najstarsza obserwacja starsza niż `MAX_BUILDER_SAMPLE_AGE_DAYS = 180` |
| `STALE_SAMPLE` | najświeższa starsza niż `MAX_SAMPLE_AGE_DAYS = 60` — **ta sama stała co w COUPON**, celowo w jednym miejscu |

Bramki kształtu (`LINE_BEYOND_SAMPLE`, `MODE_LOSES`) potrzebują **rozkładu**,
nie podsumowania: próbka potrafi zaraportować 20/20 i nic nie znaczyć, a
średnia potrafi leżeć wygodnie nad linią, której modalny wynik przegrywa.

Pole po polu `leg`: `model_p` (nasze `p_central`), `confidence`
(**dolna granica zmierzonej realizacji** — to jest liczba, po której się
rankuje), `calibrated_on`, `calibration_n`, `sample_size`,
`sample_oldest_days`, `sample_newest_days`, `sample_min`/`max`,
`offered_odds`, `implied_p`, `shading` (`confidence − 1/odds`),
`leg_ev` (`confidence·odds − 1`), `market_p`.

### 10.2 Budowa Bet Buildera

- tylko **jeden mecz**, `MIN_BUILDER_LEGS = 2` … `MAX_BUILDER_LEGS = 4`;
- **jedna noga na WIELKOŚĆ, nie na rynek** (`QUANTITY_FAMILIES`): gole drużyny
  i total meczu to ta sama wielkość policzona dwa razy (λ = 2,165), a ich
  przemnożenie sprzedaje dwie nogi jako cztery;
- w epoce `stats_only` pula, wybór i kolejność builderów idą po
  **pewności / `combined_probability`** (K10), nie po EV; buildery 2-, 3- i
  4-nogowe są prefiksami jednej puli, więc `best_for_fixture` to zwykle
  2-nogowy — to nie błąd. Do 2026-10-05: pula i kombinacje rankowane po **`leg_ev`**, na **obu** poziomach. Ranking po
  `confidence` to ranking po **krótkości ceny** (książka wycenia niemal-pewniak
  niemal-pewniakiem) — to był defekt z 2026-09-20, a naprawienie samego
  sortowania międzyrodzinowego zostawiło go żywym o poziom niżej;
- `BUILDER_LEGS_INCOHERENT`: nogi, które kłócą się o tempo meczu, są ujemnie
  skorelowane, więc iloczyn zawyżałby złożenie;
- prawdopodobieństwo złożenia: iloczyn skorygowany **empirycznym złożeniem**
  na wspólnych meczach (`MIN_JOINT_SAMPLE = 8`), a nie samą niezależnością;
- cena: `odds_product` to iloczyn nóg, a `effective_odds` to on **po
  zmierzonym narzucie korelacyjnym** `BUILDER_CORRELATION_HAIRCUT = 0.12`
  (zmierzony zakres na ekranach Superbetu 8,8–19,6%). **Superbet nie wycenia
  slipa jako iloczynu nóg**, więc `ev_if_product_priced` sam z siebie nic nie
  znaczy.

### 10.3 `is_stakeable` — jedyna definicja „to jest zakład"

```python
# stats_only (stakeable_rule == "x>=0.90"):
is_stakeable(b) == b["best_for_fixture"] and b["combined_probability"] * b["odds_after_haircut"] >= 0.90
# starsze artefakty, czytane predykatem, z którym je zbudowano:
is_stakeable(b) == b["best_for_fixture"] and b["ev_after_haircut"] > 0
```

Dwa warunki, nie jeden: `best_for_fixture` broni przed postawieniem jednego
meczu trzy razy z jednej opinii, a test EV pyta, czy pozycja przeżywa
zmierzony narzut. Predykat mieszka w `confidence.py` i używają go **oba**
miejsca (`run_confidence.py` i `build_coupon_pdf.py`), bo napisany dwa razy
zaczął dawać dwie odpowiedzi: 2026-09-21 CONFIDENCE meldował
`stakeable_builders: 3` dla dnia, w którym PDF postawił **zero**.

**Czytaj `stakeable_builders`, nie `builders`.** Oba są raportowane właśnie
dlatego, że się różnią.

---

## 10a. Sporty mierzone na kuponie — SPORT_IDENTITY i SPORT_CONFIDENCE (od 2026-10-05 08:30Z)

Od `SPORTS_ON_COUPON_FROM_UTC` (2026-10-05 08:30Z, `bet.sofa.epochs`) nogi
hokeja, koszykówki, siatkówki i CS2 drukują się na **jednym** kuponie. Pomiar
SHADOW / CS2 zostaje; jego migawki są wejściem.

**SPORT_IDENTITY** — `scripts/sofa/run_sport_identity.py --date <d> [--sport
hockey --sport cs2]` (albo `run_pipeline.py --only SPORT_IDENTITY`), **most**,
po świeżym `--only SHADOW` i `--only CS2`. Jedno zapytanie
`team/<id>/events/next/0` na mecz; druga drużyna sprawdzana w odpowiedzi
(obie nazwy powyżej progu, start ±1 h od Superbetu, unikalność w dniu). Czyta
migawki D i D+1. Pisze **`runs/sofa/<d>/sport_fixtures.json`**:
`superbet_event_id`, `sport`, `sofascore_event_id`, `home_id`, `away_id`,
`home_is_team1`, `competition_id`, `match_method`, `name_scores`,
`start_gap_h`, `matched_at_utc`, `status` (`IDENTIFIED` / `NOT_IDENTIFIED` /
`DUPLICATE_*` …). Rekord `IDENTIFIED` jest przypięty i nigdy nie pytany
ponownie; po tym id rozlicza SETTLE. Kod 0 / 1 (mecz nierozpoznany albo
odmowa mostu) / 2 (brak migawki żadnego sportu).

**SPORT_CONFIDENCE** — `scripts/sofa/run_sport_confidence.py --date <d>`,
bez mostu. Czyta `sport_fixtures.json`, migawki SHADOW / CS2,
`config/sofa_sport_confidence_calibration.json` (`fit_sport_confidence.py`,
tylko między dniami) i bazę (tylko odczyt); pisze
**`runs/sofa/<d>/08_confidence_sports.json`**. Dla każdej strony meczu ze
startem w [D 00:00Z, D+1 00:00Z): pewność = dolna granica Wilsona kubełka
kalibracji, w który wpada prawdopodobieństwo modelu wyników (`score_model`)
albo silnika CS2 (`cs2_engine`), bez ceny. Pola nogi: `sport`, `group_key`
(`sofa:<id>`), `sofascore_event_id`, `superbet_event_id`, `market_id`,
`family`, `period`, `subject`, `line`, `side`, `confidence`,
`calibrated_on`, `calibration_n`, `sample_hit_rate`, `sample_k`, `sample_n`,
`forecast_p`, `forecast_source`, `odds`, `x`, `overround`, `kickoff_utc`,
`source_date`, `price_fetched_at_utc`, `match`, `competition`. Odmowy:
`NOT_IDENTIFIED`, `DUPLICATE_*`, `KICKED_OFF` (wcześniejszy z zegarów
Superbetu i Sofascore), `STALE_PRICE` (najnowsza migawka przed startem
starsza niż `sport_coupon.MAX_PRICE_AGE` = 3 h), `MARKET_NOT_ALLOWED` (lista
`sport_confidence.ALLOWED_MARKETS` / `CS2_FAMILIES`), `NOT_CALIBRATED`,
`BELOW_FLOOR` (0,70), `BELOW_MIN_X` (x < 0,90), `ODDS_TOO_LOW` (kurs <
1/0,9202), `MARGIN_TOO_HIGH` (marża grupy > 15%), `INCOMPLETE_GROUP`,
`NO_MODEL_P`, `TOURNAMENT_NEVER_SETTLED` (siatkówka: turniej bez meczu SETTLED
w ostatnich 14 dniach). Kod 1,
gdy sport jest `NOT_CALIBRATED` albo brak `sport_fixtures.json` — artefakt i
tak powstaje, kupon piłki i tenisa buduje się dalej.

## 10b. COUPON_ASSEMBLY — `11_coupon.json`, jedyny artefakt kuponu

`scripts/sofa/build_coupon.py --date <d>` (albo `run_pipeline.py --only
COUPON_ASSEMBLY`), offline. Wejście: `08_confidence.json` (profil standard,
epoka `stats_only`; odmowa, gdy jest inny albo starszy niż `05_sheet.json`,
weta, odczyty lub kalibracja) i `08_confidence_sports.json`. Wyjście:
**`runs/sofa/<d>/11_coupon.json`** (+ `11_coupon.md`) — nadzbiór formatu 08;
każdy czytelnik idzie przez `confidence.coupon_artifact()` (11, a dla dni bez
niego 08).

- Kolejność `confidence.coupon_order`: bloki po jednym meczu (`group_key`),
  ułożone po najlepszej nodze — pewność malejąco, wcześniejszy start, id
  meczu; w bloku pewność, rynek, linia. Bez kursu i EV w kluczu. Pozycje
  1..N.
- Nogi zablokowane (mecz już się zaczął, noga była w poprzednim wydruku —
  `12_printed.json`, `locked_print`, dla sportów `locked_sport_legs`) idą na
  górę, bez numeru, z `printed_under` (w tym `epoch`). Noga zdjęta przed
  startem zostaje zdjęta.
- Buildery B1.. (osobne strony PDF, odsyłacz przy bloku meczu).
- `removed_by_reads`: nogi, które przeszły każdą bramkę, a zdjął je odczyt
  WATCH / NO_BET albo automatyczny `MODEL_ABOVE_OWN_SAMPLE`, z `reason`
  (`analyst` / `verifier` / `auto`). Dla nóg sportów weta i odczyty stosuje tu
  `coupon_sports.apply_reads` (z `period`).
- Kopia `read_requests` i zbiór do przeczytania
  (`confidence.legs_requiring_read`: pierwsze `READ_REQUIRED_SINGLES` = 30
  pozycji niezablokowanych, każda noga wydrukowanego buildera, prośby z
  `read_requests.json`). Prośba, która nic nie objęła, drukuje
  `UNMATCHED_READ_REQUEST`.

## 10c. FIXTURE_CHECK — czy mecz drukowany nadal jest grany (od 2026-10-05)

`scripts/sofa/run_fixture_check.py --date <d>` (albo `run_pipeline.py --only
FIXTURE_CHECK`), **most**, w przebudowie po OFFER, przed CONFIDENCE.
`/event/{id}` dla meczów drukowanych i przesuniętych zegarów →
**`runs/sofa/<d>/fixture_status.json`**. postponed / canceled / abandoned →
`FIXTURE_NOT_AS_SCHEDULED` (odmowa w CONFIDENCE). Świeży start zastępuje
zamrożony zegar RESOLVE dla bramki, blokady i `capture_closing` (K12). Bez
mostu: `UNVERIFIED` (pokazane, bez odmowy), kod 1. 403 przerywa od razu.

---

## 11. PDF — produkt

`scripts/sofa/build_coupon_pdf.py --date <d> [--out …] [--runs-dir …]` →
**`runs/sofa/<data>/KUPON_<data>.pdf`** i **`runs/sofa/<data>/12_printed.json`**

W dniu `stats_only` renderuje `11_coupon.json` (bez niego odmawia): nogi
zablokowane na górze, potem tabela „Pozycje” w kolejności pozycji, blok meczu
z godziną startu i oznaczeniem sportu (poza piłką), kolumny „pewność”
(skalibrowana), „model” (`forecast_p`, nieskalibrowany), kurs, x, marża,
próbka; buildery na osobnych stronach z odsyłaczem przy bloku meczu. Odmowy (kod 2): `STALE_CONFIDENCE` — `08_confidence.json`
starszy niż `05_sheet.json`, `vetoes.json`, `reads.json` albo kalibracja;
`STALE_COUPON` — `11_coupon.json` starszy niż `08_confidence.json`,
`08_confidence_sports.json` albo `read_requests.json`. Potem zapisuje
`12_printed.json` (manifest wydruku), z którego następna przebudowa blokuje
nogi. Buildery: wyłącznie pozycje przechodzące `is_stakeable`, każda z
własnym śladem dowodowym. `--profile wariant` (historyczne) odmawia dla
buildów po 2026-10-05 07:15Z. **`picks: 0` to odpowiedź legalna i częsta** — i zwykle jest
skutkiem narzutu korelacyjnego, nie braku danych.

Oznaczenia na stronie (od 2026-10-01; pokazane, nie egzekwowane):

- **„ta sama drabina: N”** przy singlu, gdy na liście stoi N szczebli jednej
  drabiny (ten sam mecz, rynek i podmiot, `confidence.ladder_key`), plus
  zdanie nad listą z liczbą takich drabin. Dwa szczeble jednej drabiny to
  jedno twierdzenie o jednej liczbie kupione dwa razy — 2026-09-30 kupon
  wydrukował na jednym meczu corners_total 12.5 poniżej, 11.5 poniżej i 7.5
  powyżej, a 2026-10-01 WARIANT dziesięć takich drabin (22 wiersze). Limit na
  mecz był testowany wstecz i jest decyzją operatora.
- **„start przed renderem PDF”**, gdy noga w chwili renderowania jest już
  w marginesie startu CONFIDENCE (`MIN_MINUTES_TO_KICKOFF`, wcześniejszy
  z dwóch zegarów) albo się zaczęła. CONFIDENCE bramkuje na swoim zegarze;
  PDF przerenderowany później z tego samego JSON-a drukował nogę po starcie
  bez słowa. Noga zostaje (rozlicza się JSON), jest oznaczona, a skrypt pisze
  `WARNING` na stderr.
- Bet Builder pokazuje wyłącznie **„kurs po narzucie”** (`odds_after_haircut`
  z `confidence.py`), nigdy iloczynu kursów nóg — Superbet tak slipu nie
  wycenia (zmierzony narzut 8,8–19,6%).

PDF renderuje się do pliku tymczasowego obok i jest przenoszony na miejsce
(`os.replace`): przerwany render nie zostawia uciętego `KUPON_*.pdf`.

To jest jedyny plik, który się stawia.

---

## 11a. CLV, boosty, metoda zdejmowania marży (od 2026-10-01)

Po przeglądzie praktyki (fora, systemy open source, narzędzia komercyjne)
dodane trzy pomiary — żaden nie zmienia kuponu:

- **CLV** (`capture_closing.py` + `audit_clv.py`): czy wydrukowana cena była
  lepsza od ceny zamknięcia Superbeta (pobranej 3–30 min przed meczem,
  zdjętej metodą potęgową). `EV_CLV = kurs wzięty × p zamknięcia − 1`,
  przedział z bootstrapu po meczach (`clv.cluster_ratio_interval`; poniżej
  20 meczów `MIN_CLUSTERS` drukowane jest „-” — przy dwóch meczach bootstrap
  może zwrócić tylko ich własne średnie, a `audit_clv` drukował
  [−9,67%; −3,18%] z 2 nóg 2 meczów). Rozrzut CLV na zakład jest ~10× mniejszy
  niż zysku, więc odpowiada w dziesiątkach nóg, a nie tysiącach. To
  zamknięcie bukmachera „miękkiego" — słabszy test niż zamknięcie ostrej ceny;
  linia, której Superbet nie rusza, to „nietestowane", nie „neutralne".
  Pierwszy odczyt (kupony sportowe 09-30): −2,3% … −7,1% — kurs prawie się
  nie rusza, więc CLV ≈ ujemna marża, czego należy oczekiwać po kuponie z
  samej ceny.
- **Boosty**: pojedynczy boost dostaje EV wobec swojego rynku sprzed podbicia
  z całym rynkiem zdjętym z marży (`Boost.fair_p`, `ev_at_fair`). Kombinacja
  nie dostaje żadnego prawdopodobieństwa (zasada: żadnej ceny kombinacji poza
  `confidence.py`).
- **Metoda zdejmowania marży** (`measure_devig.py`, 98 702 rozliczone strony
  09-20..30): potęgowa 0,20047, Shin 0,20038, proporcjonalna 0,20088 —
  potęgowa zostaje (Shin lepszy o 0,00009, przedział dotyka zera).
- **Ledger** podaje przedział ROI z bootstrapu **po meczach** (od
  2026-10-01; nogi jednego meczu dzielą jego scenariusz, a dzień też nie jest
  jednostką — przy dwóch dniach bootstrap po dniach zwracał tylko ROI tych
  dwóch dni). Poniżej 20 meczów kolumna pokazuje „- (<20 matches)”, a dzień
  zapisany bez rekordu per mecz (sprzed 2026-10-01 albo powtórka reguły,
  która zapisuje same sumy) daje „- (no per-match record)” — pominięcie go
  zniekształciłoby przedział. Rekord dnia niesie `by_match`
  (`{mecz: [jednostki, rozliczone]}`) i `estimated_builders`: buildery
  rozliczone po szacunku `odds_if_product × haircut`, bo nie zapisano kursu
  z ekranu (7c „(szac.)”) — `audit_ledger` pokazuje je w osobnej kolumnie, bo
  to nie jest kurs, który Superbet wydrukował. Pierwszy odczyt (jeszcze po
  dniach, sprzed tej zmiany): oficjalny kupon 09-19..30 −1,8% [−9,0%;
  +11,1%], WARIANT −3,8% [−5,3%; −1,3%] — przedziały po dniach, nie do
  porównania z nowymi.
- **Czego to nie zmienia** (przegląd literatury i praktyki): model z samych
  wyników nie bije ceny na zwycięzcy (rynek zna składy, kontuzje, bramkarza);
  sumy niosą trochę informacji; rynki siatkówki są niezbadane. Przewaga u
  bukmachera „miękkiego", jeśli jest, leży w propsach, boostach i wolno
  poruszanych liniach — to hipoteza do pomiaru przez CLV, nie reguła.

## 12. SETTLE — rozliczenie dnia zakończonego

`src/bet/sofa/settle.py`, `scripts/sofa/run_settle.py --date <d>
[--include-unpriced]` → **`07_settled.json`**, `07_settle_skips.json`
i wiersze w **`data/sofa.db`** (`sofa_settled_row`). **Most.**

Nie ma go w `DEFAULT_SEQUENCE` i to jest projekt: puszczony na dzisiaj znajdzie
każdy mecz nierozegrany. Uruchamia się dla **D-1**, zanim ruszy dzisiejszy dzień,
bo konkuruje z nim o most.

- `PARTIAL` to normalny werdykt (mecze niezakończone, luki statystyk).
- **Wiersz, którego nie dało się ocenić, nie jest przegraną.** Liczenie ślepego
  wiersza jako przegranej zaniża model dokładnie tyle samo, ile liczenie go
  jako wygranej zawyża. Dlatego istnieje `07_settle_skips.json`.
- `--include-unpriced` ocenia też wiersze, których Superbet nigdy nie wycenił.
  Nie dotrą do fitu `K_PRICE` (`market_p` jest dla nich NULL z konstrukcji), ale
  są prawdziwymi prognozami i tylko one mówią, co zrobiła **cała** tablica.
- SETTLE to **jedyny pisarz, który stawia cenę Superbetu obok wyniku**, więc
  jedyne źródło dla `fit_k_price` i `MAX_LADDER_SIGMA`.
- **Zwroty** (od 2026-10-05): mecz przesunięty o > 48 h (`MOVED_BEYOND_VOID`)
  albo przyznany walkowerem (`AWARDED`) to zwrot (0 j.), nigdy przegrana i
  nigdy `sofa_settled_row` (trafia do `07_settle_skips.json`).
- Propsy zawodników tylko ze składu samego zawodnika (inaczej
  `PLAYER_AMBIGUOUS`).
- Noga wydrukowana bez wiersza arkusza rozlicza się do
  **`07_settled_printed.json`**, nigdy do `sofa_settled_row`.
- Nogi sportów mierzonych nigdy nie trafiają do `sofa_settled_row` ani do
  `fit_confidence`; rozlicza je `settled.json` sportu (SHADOW_SETTLE /
  CS2_SETTLE) po id przypiętym w `sport_fixtures.json` — inne id to
  `NOT_GRADED:ID_CHANGED`. Przypięcia sprawdza
  `scripts/sofa/audit_settle_identity.py --from <d> --to <d>` (`ID_USED_TWICE`,
  `MOVED_GRADED`, `NAME_BELOW`, `ORIENTATION_IDS`, `ID_CHANGED`,
  `IDENTITY_STATE`, `IDENTITY_PENDING`; kod 0 / 1 / 2).

Granica metody, podana wprost: nie mamy historycznych cen Superbetu. Wstecz da
się mierzyć **kalibrację prawdopodobieństwa** (czy 85% znaczy 85%). **Nie da
się mierzyć ROI.** Nie raportuj drugiego z pierwszego.

Odczyt: `scripts/sofa/audit_settlement.py --date <d>` — **sekcja 7c to
prawdziwy wynik kuponu z PDF** (w dniu `stats_only`: tabela per sport ×
epoka, tabela sportów mierzonych po kursie z wydruku, „Suma kuponu”; zwroty
osobno); **7i „Nogi zdjęte przez odczyt”** — `removed_by_reads`, osobno,
nigdy w wyniku kuponu; 7d (WARIANT) tylko dla dni do poranka 2026-10-05
(historyczne). Sekcje 7 i 7b to materiał wejściowy (legi i kandydaci),
**nie zakłady**. Potem `scripts/sofa/audit_day_deep.py --date <d>`
— czy pudło było **systematyczne** (środek w złym miejscu) czy **dyspersją**,
i czy dzisiejsze bramki nadal postawiłyby wczorajszy zakład.

---

## 13. FIT — stałe z rozliczonej tabeli

`scripts/sofa/fit_constants.py --db-path data/sofa.db --config-dir config`

**Poza `DEFAULT_SEQUENCE`, świadomie.** Przefitowanie w środku dnia psuje
porównywalność z wczorajszym przebiegiem: ten sam arkusz przeliczony na nowych
stałych jest innym arkuszem, i nikt już nie odróżni zmiany modelu od zmiany
rynku.

Szczegóły — który plik, kto go pisze, co znaczy `NOT_FITTED`, jak czytać
`half_match_coherence` — w [`CONFIG.md`](CONFIG.md). Od 2026-10-01
`fit_confidence.py` i `fit_constants.py` pomijają rynki pochodne
(`most_` / `handicap_` / `both_over_`), prior `K_CENTRE` jest liczony bez
ocenianego meczu (leave-one-match-out), a `calibrate_from_cache.py` składa
zduplikowane listingi — krzywe zmienią się dopiero przy **następnym** fitcie
między dniami (CONFIG.md §4).

---

## 14. Artefakty dnia

```
runs/sofa/<data>/
  01_board.json        BoardFixture[]     mecze z tablicy Superbetu
  02_fixtures.json     Fixture[]          tożsamość, OBA zegary, sędzia, runda, nawierzchnia
  03_samples.json      FixtureSamples[]   obserwacje per metryka, per strona + luki
  04_offer.json        FixtureOffer[]     wycenione szczeble + fetched_at_utc, unmapped_markets
  05_sheet.json        SheetRow[]         każdy szczebel wyceniony, z werdyktem i notkami
  06_coupon.json/.md   Coupon             single VALUE — NIE jest kuponem
  06_dropped.json      DroppedRow[]       każdy VALUE, który nie wszedł, z powodem
  07_settled.json      (tylko D-1)        ocenione wiersze; także do data/sofa.db
  07_settle_skips.json (tylko D-1)        czego nie dało się ocenić i dlaczego
  07_settled_printed.json (tylko D-1)     nogi wydrukowane bez wiersza arkusza, ocenione (nie do sofa_settled_row)
  08_confidence.json/.md                  legi i Bet Buildery piłki i tenisa (wejście SETTLE i refitu)
  sport_fixtures.json                     SPORT_IDENTITY: przypięte id Sofascore sportów mierzonych
  08_confidence_sports.json               SPORT_CONFIDENCE: nogi hokej / kosz / siatka / CS2
  fixture_status.json                     FIXTURE_CHECK: status i świeży start meczów drukowanych
  11_coupon.json/.md                      COUPON_ASSEMBLY: jedyny artefakt kuponu (pozycje, bloki, zablokowane, removed_by_reads)
  KUPON_<data>.pdf                        ★ produkt — to jest kupon
  12_printed.json                         manifest tego, co PDF wydrukował; z niego blokuje następna przebudowa
  vetoes.json          Veto[]             kanał analityka; [] w większość dni
  reads.json           LegRead[]          werdykty o nogach (KEEP / WATCH / NO_BET)
  read_requests.json                      prośby operatora o dodatkowy odczyt (pozycja albo group_key)
  08_confidence_wariant.json/.md, KUPON_<data>_WARIANT.pdf
                                          historyczne (wycofane 2026-10-05 07:15Z): wariant, rozliczany w 7d
  10_boosts.json/.md   Boost[]            boosty Superbeta — NIE są kuponem (run_boosts.py)

runs/sofa/cs2/<data>/   — obok dnia, nigdy w nim
  snapshots.jsonl      linie CS2 Superbeta przed startem serii (run_cs2.py, etap CS2)
  settled.json         te linie ocenione z danych Sofascore (settle_cs2.py, CS2_SETTLE)
  sport_coupon.json/.md, sport_coupon_builds.jsonl, sport_coupon_settled.json, KUPON_<data>_CS2.pdf
                       historyczne (wycofane 2026-10-05 08:30Z): kupon eksperymentalny CS2

runs/sofa/shadow/<sport>/<data>/   — sport: hockey | basketball | volleyball
  snapshots.jsonl      linie Superbeta przed startem meczu (run_shadow.py, etap SHADOW)
  settled.json         te linie ocenione z wyniku Sofascore (settle_shadow.py, SHADOW_SETTLE)
  sport_coupon.json/.md, sport_coupon_builds.jsonl, sport_coupon_settled.json,
  KUPON_<data>_{HOKEJ,KOSZYKOWKA,SIATKOWKA}.pdf
                       historyczne (wycofane 2026-10-05 08:30Z): kupon eksperymentalny sportu

runs/sofa/multi/<data>/                   historyczne (wycofane 2026-10-05 07:15Z)
  multi_coupon.json/.md, multi_coupon_settled.json, KUPON_<data>_WSZYSTKIE.pdf

runs/sofa/ledger/results.jsonl            dziennik: jeden wiersz na (dzień, wariant) — official, official:pre_stats_only, removed:reads,
                                          measure:<sport>, rule:<sport> (dawniej też wariant, sport:<sport>, multi); record_results.py; czyta audit_ledger.py
```

Od 2026-10-01 każdy artefakt etapu, PDF i plik fitu w `config/` jest
zapisywany atomowo (`src/bet/sofa/atomic.py`): do `<nazwa>.<pid>.<wątek>.tmp`
obok celu, potem `os.replace`. Etap przerwany w trakcie zapisu nie zostawia
uciętego JSON-a, który następny etap by przeczytał (albo odrzucił z błędem
wskazującym złą przyczynę).

`10_boosts.*` pisze `scripts/sofa/run_boosts.py --date <d>`, poza
`DEFAULT_SEQUENCE`: migawka każdego kursu z tagiem `price_boost` — kurs po
podbiciu, kurs sprzed podbicia i nogi, sklasyfikowane tą samą funkcją co
OFFER. Kolejne uruchomienie tego dnia dopisuje obserwacje, nie nadpisuje.
`audit_boosts.py --from <d> --to <d>` i sekcja 7f `audit_settlement`
sprawdzają, czy boosty trafiają częściej niż ich próg po podbiciu i przed nim.
Ocenić da się tylko boost, którego mecz jest na tablicy `sofa`, a każda noga
w arkuszu — API ofert Superbeta nie podaje wyników.

### CS2 — pomiar ceny, nie kupon

Od 2026-09-28 `sofa` mierzy Counter-Strike 2 obok kuponu. To **pomiar, nie
rynek na kupon**: pytanie brzmi, czy kurs Superbeta po zdjęciu marży już zgadza
się z tym, co się dzieje — jeśli tak, próbka nie ma czego dodać i CS2 na kupon
nie trafia. Nic z `runs/sofa/cs2/` nie jest czytane przez etap, który buduje
kupon. Od 2026-09-30 obok pomiaru jest eksperymentalny `KUPON_<d>_CS2.pdf`
(tylko cena, bez modelu) — też NIE kupon.

```
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d>   --only CS2         # kilka razy dziennie
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only CS2_SETTLE  # rano, bridge musi działać
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_cs2.py --from <d> --to <d>
```

Cały dzień CS2 bez obsługi (zapis cen co 30 min do 23:30Z; z `--chain` o
23:30Z startuje pętla D+1, więc nocne serie D+1 mają ceny; następnego dnia o
05:00Z CS2_SETTLE dla D i D-1, potem przegląd D-7..D-2
(`settle_cs2.py --sweep-from <D-7> --sweep-to <D-2>` — tylko daty, których
`settled.json` brakuje albo wciąż ma czekającą serię, rozstrzygnięte offline
z plików), rozliczenie kuponów CS2 i dziennik za D-7..D, krótki backfill
z poszanowaniem karencji i audyt do logu; druga pętla dla tej samej daty
odmawia, kod 2). Bez przeglądu seria, która wciąż czekała na D-2, nie była
już nigdy pytana i nie dochodziła nawet do `GAVE_UP` po 7 dniach (audyt
2026-10-01):

```
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/cs2_daily.py --date <d> --chain \
    >> runs/sofa/cs2/daily_<d>.log 2>&1 &
```

Pętla czyta swój plan raz, przy starcie: pętla uruchomiona przed zmianą kodu
wykonuje stare kroki poranne aż do końca (jej następczyni z `--chain` ma już
nowy kod).

Strażnik (`cs2_watchdog.py --dates <d1,d2> --until <UTC>`) co 5 min: wznawia
padnięty `cs2_daily` (plik `daily_<d>.pid` bez `.done`), restartuje serwer
bridge, gdy nie nasłuchuje, ponawia CS2_SETTLE co godzinę, dopóki są serie do
ponowienia, i zgłasza `ALERT_TABS`, gdy karty przestały odpytywać — tego nie
naprawi sam, bo wymaga zamknięcia Chrome. Każda linia logu zaczyna się od
`WATCHDOG`.

- **CS2** (`run_cs2.py`) pyta tylko Superbeta (sportId 55): każdą pełną
  grupę wyników serii, która się jeszcze nie zaczęła (linie dwudrożne, a od
  2026-09-30 także dokładny wynik w mapach i parzystość rund na mapie, każda
  zdevigowana po całej grupie), dopisuje do `snapshots.jsonl`.
- **CS2_SETTLE** (`settle_cs2.py`) bierze ostatni kurs sprzed startu, znajduje
  serię w Sofascore (kategoria „Counter Strike”; drużyna e-sportowa jest osobna
  dla każdej gry), odtwarza mapy po kolei i ocenia linie dopiero wtedy, gdy mapy
  dają dokładnie wynik serii podany przez Sofascore. Seria w toku jest ponawiana;
  po 48 h od startu to `VOID` — tak jak w Regulaminie Superbeta (5.E.1.a);
  po 7 dniach bez oceny `GAVE_UP` (nasze). Od 2026-10-01 seria bez wierszy
  zawodników nie czeka w całości (`STATS_PENDING`, karencja 72 h): czekają
  tylko linie zawodników i zabójstw drużyny na mapie bez tych wierszy
  (`stats_pending`), a linie serii, map i rund są oceniane od razu — dawniej
  zwycięzca meczu wisiał dłużej, niż pętla kiedykolwiek sięgała (rozlicza po
  ~29 h i ~53 h). Seria bez wyników rund ocenia linie serii i liczy resztę
  (`series_only_skipped`; 09-30 zgubiło bez śladu 114 ze 154). `SETTLED`
  z `pending_sides` > 0 (`pending_reason` `SERIES_ONLY` / `STATS_PENDING`)
  jest pytany ponownie, a nieudana ponowna próba nigdy nie zastępuje ocen,
  które już są. Rekord ma `sofascore_start_utc` (od 2026-10-01), więc
  `IN_PLAY_PRICE` kuponu sportowego działa też dla CS2. `settled.json` jest
  zapisywany pod blokadą (`<plik>.lock`): równoległe rozliczenie (strażnik,
  ręczne) zachowuje serie, których to nie dotknęło. Nazwy: sufiks „.gg”
  (Superbet „KUUSAMO” / Sofascore „KUUSAMO.gg”) i znaczniki składu kobiet
  („MIBR (K)” / „MIBR fe”, wcześniej 76,9 przy progu 82 — każda seria kobiet
  była `NOT_ON_SOFASCORE`) są składane; skład kobiet nigdy nie pasuje do
  męskiego.
- **audit_cs2.py**: pokrycie (stany i turnieje), potem dla każdej rodziny rynku
  kurs bez marży, trafialność, różnica, Brier, zwrot i marża; osobno faworyci
  i underdogi. Linie jednej serii są skorelowane — czytaj kolumnę `series`.

### Hokej, koszykówka, siatkówka — pomiar ceny, nie kupon

Od 2026-09-29 tak samo jak CS2, dla trzech sportów drużynowych, które Superbet
wystawia w dużej liczbie (29.09: hokej 49 meczów / 16 turniejów, koszykówka 70
/ 31, siatkówka 49 / 23). Pytanie jest to samo: czy kurs bez marży już zgadza
się z wynikiem? Od 2026-10-05 08:30Z migawki z `runs/sofa/shadow/` są
wejściem SPORT_IDENTITY i SPORT_CONFIDENCE (§10a), a `settled.json`
rozlicza nogi tych sportów na kuponie; `PARTIAL`/`FAILED` pomiaru nie blokuje
kuponu piłki i tenisa.

```
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d>   --only SHADOW         # kilka razy dziennie, tylko Superbet
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only SHADOW_SETTLE  # rano, bridge musi działać
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_shadow.py --from <d> --to <d> [--sport hockey]
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/shadow_daily.py --date <d> --chain \
    >> runs/sofa/shadow/daily_<d>.log 2>&1 &    # cały dzień bez obsługi: ceny do 04:30Z D+1, o 05:15Z settle D, D-1 i D-2 i dziennik za te dni, potem --chain startuje D+1
```

- **SHADOW** (`run_shadow.py`): Superbet sportId 3 (hokej), 4 (koszykówka),
  1 (siatkówka); e-hokej (157) i e-koszykówka (70) to symulacje i nie są
  czytane. Rynek rozpoznaje po `marketId` (jeden identyfikator na typ rynku we
  wszystkich meczach), stronę po `code` i po treści — gdy się nie zgadzają,
  linia wypada. Czytana jest każda pełna grupa wyników: linie dwudrożne
  (zwycięzca z dogrywką, sumy, sumy drużyn, handicapy, zakład bez remisu —
  całość, tercje, połowy, kwarty, sety), a od 2026-09-30 także 1X2 (1X2 bez
  remisu nie jest ceną), parzystość, set na przewagi (tak/nie) i dokładny
  wynik w setach (siatkówka), każda zdevigowana po całej grupie. Pyta o mecz, gdy startuje w ciągu `--horizon-h` (3 h) albo gdy dzień
  nie ma go jeszcze w ogóle; mecze następnego dnia w horyzoncie trafiają do
  pliku tamtego dnia (późne NHL/NBA po 00:00Z).
- **SHADOW_SETTLE** (`settle_shadow.py`): mecz znajduje resolverem RESOLVE
  (ten sam cache, bramki płci „(K)” i poziomu drużyny; okno 6 h). Szukanie
  jest zawężone do sportu (`&sport=`), czyta tylko pierwszą stronę
  `events/last`, a mecze wirtualne / e-sportowe („(Cyber)”, „(eSport)”,
  kategoria `virtual-*`) są odrzucane. Bramka przeciwnika jest łagodniejsza
  niż w piłce: pełny wynik nazwy bez markera „(K)” i osobno dla każdej części
  „sponsor/klub”, albo — gdy oba zegary zgadzają się co do 15 min — wspólne
  wyróżniające słowo przeciwnika, którego nie ma w nazwie szukanej drużyny
  (więc „Dynamo Moscow” nie potwierdzi sam siebie przez „moscow”).
  `/event/{id}` pyta świeżo i ocenia dopiero, gdy wynik się zgadza: suma
  okresów = `normaltime`, dogrywka tylko z remisu, sety = `current`. Gol z
  dogrywki jest w `current`, a w żadnym okresie. Rynek bez „(z dogrywką)”
  liczy czas regulaminowy (rodziny hokejowe z dogrywką 613 / 617 / 621 / 653
  nie są mapowane, a NHL jest wystawiana **tylko** z nimi, więc żadna suma NHL
  nie jest mierzona — przegląd 2026-10-01); kwarta 4. i 2. połowa w koszykówce po dogrywce są
  nieoceniane (nazwa nie mówi, czy dogrywka się wlicza). Gdy nie da się
  pewnie powiedzieć, która strona Sofascore to drużyna 1 Superbeta, oceniane
  są tylko sumy (`orientation_unclear: true`). Listing odwrócony (gospodarz
  Sofascore = drużyna 2 Superbeta) jest oceniany ze strony drużyny 1 —
  bramka orientacji RESOLVE jest tu wyłączona, bo settle sam czyta
  orientację. Zegar przedmeczowy to **wcześniejszy** z dwóch (start Superbeta
  i `startTimestamp` Sofascore), jak w piłce: gdy mecz zaczął się wcześniej,
  oceniana jest ostatnia cena sprzed prawdziwego startu, a gdy takiej nie ma
  — stan `NO_PRE_START_PRICE` (ostateczny, tylko dla meczu zakończonego).
  Wiek ceny (`minutes_before_kickoff`) liczony jest do tego wcześniejszego
  zegara. Brak odpowiedzi `/event` to
  `ERROR` (ponawiany), nigdy wynik z listingu. Stany jak w CS2; po 7 dniach
  `GAVE_UP` (nasze), nigdy `VOID` Superbeta. Mecz `NOT_ON_SOFASCORE` niesie
  od 2026-10-01 `miss` (`team1` / `team2`): pierwszą bramkę, która opróżniła
  szukanie danej strony (`CACHED_MISS`, `NO_SEARCH_RESULT`, `NO_CANDIDATE`
  z `search_teams`, `NO_LISTING`, `NO_GAME_IN_WINDOW` z `nearest_gap_h`,
  `GENDER_REFUSED` / `OPPONENT_REFUSED` z `in_window`), odczytaną z już
  opłaconego wyszukiwania i z cache, bez nowego żądania — 30 z 50 meczów
  siatkówki 09-29..30 skończyło jako `NOT_ON_SOFASCORE` i nic nie mówiło
  dlaczego. Każdy oceniony wiersz ma
  `minutes_before_kickoff` — wiek ceny; audyt dzieli po nim (sekcja 5).
  Koszt: mecz szuka tylko w pierwszej stronie `events/last` (~3–9 żądań na
  zimnym cache, ~1 s na żądanie przez bridge).
- **audit_shadow.py**: per sport pokrycie, cena vs wynik per rodzina,
  kierunek (OVER / drużyna 1), faworyci vs underdogi, mecze z dogrywką vs
  bez, wiek ceny. Sekcje 2, 2b, 4 i 5 biorą **jedną stronę każdej linii**
  (faworyta albo stałą) — obie strony razem dają średni kurs i trafialność
  0,500 z samej konstrukcji, więc różnica byłaby zawsze zerowa. Linie
  jednego meczu są skorelowane — czytaj kolumnę `games`. Kolumna `SE pp` to
  błąd standardowy różnicy liczony klastrami po meczu, a `read` mówi, co
  wolno z komórki wyczytać: `too few` (< 30 meczów), `noise` (różnica w
  granicach 2 SE), `lead only` (poza 2 SE, ale dane z < 7 dni), `signal`.
  Przy tylu komórkach mniej więcej co dwudziesta wygląda na sygnał
  przypadkiem — sygnał to pytanie na kolejne tygodnie, nie zakład.
- **Rynki zawodników (od 2026-09-29).** Hokej: punkty, asysty, celne
  strzały, punkty w przewadze, bilans +/-, zablokowane strzały, wygrane
  wznowienia, hity, obrony bramkarza. Koszykówka: punkty, asysty, zbiórki,
  trójki, przechwyty, bloki i kombinacje (P+Z+A, Z+A, P+A, P+Z). Tylko
  linie dwustronne, więc dewig działa jak dla drużyn. Rozliczane z
  `/event/{id}/lineups` (jedno żądanie na mecz, świeże), zawodnik dopasowany
  jak w piłce (`players.match_player`). Zawodnik, który nie zagrał
  (`secondsPlayed` 0 lub brak), to VOID — Superbet zwraca stawkę. Pudełko
  musi się zgadzać z wynikiem: w koszykówce suma punktów = wynik, w hokeju
  suma goli = wynik (gol z karnych może być w `current`) — inaczej żadna
  linia zawodnika z meczu nie jest oceniana (`player_box`). Znaczenie kluczy
  sprawdzone 2026-09-29: suma zawodników = statystyka drużyny w 12/12
  meczach (hokej: strzały, hity, bloki; kosz: asysty, bloki, przechwyty,
  trójki, punkty). Na żywo: 39/40 pudełek hokejowych i 34/40 koszykarskich
  spójnych. Od 2026-10-01 odpowiedź `/lineups` zakończonego meczu trafia do
  cache (`sofa_event_stats.lineups_json` było puste dla wszystkich 3052
  ocenionych stron zawodników), więc ocenę zawodnika da się sprawdzić na
  pudełku, z którego ją wzięto; pusta odpowiedź nie jest zapisywana.
- **shadow_daily.py**: jedna pętla na datę — druga odmawia startu (exit 2),
  gdy `daily_<d>.pid` wskazuje żywy proces `shadow_daily.py` tej daty; plik
  pid znika, gdy pętla się kończy. Pętla D łapie mecze D+1 tylko do ~07:30Z
  (ostatni snapshot 04:30Z + horyzont 3 h), dlatego `--chain` po porannym
  settle i audycie sam startuje pętlę D+1 (też z `--chain`) do
  `daily_<D+1>.log`. Łańcuch zatrzymuje się, zabijając pid z
  `daily_<d>.pid`. Rano po SHADOW_SETTLE (D, D-1 i D-2 — każdy dzień,
  który ma migawki) pętla rozlicza kupony sportów za te dni
  (`settle_sport_coupon.py`, tylko dni do 2026-10-05 — historyczne, kupony
  wycofane 2026-10-05) i zapisuje dziennik (`record_results.py --from
  <najwcześniejszy> --to D`). D-2 doszło 2026-10-01: przełożony mecz staje
  się `VOID` dopiero 48 h po starcie, a settle D-1 o 05:15Z jest najwyżej
  ~35 h po nim — bez D-2 przełożony mecz nigdy nie był `VOID` i kończył jako
  `GAVE_UP`. Settle D-2 wypada 53–77 h po meczu; mecz już rozliczony jest
  zachowywany, pytane są tylko czekające.

**Historia i silnik.** `scripts/sofa/backfill_cs2.py --days 180` wczytuje z
Sofascore historię CS2 do tabel `cs2_series`, `cs2_map`, `cs2_player_map` w
`data/sofa.db`: serie, mapy (z dogrywką i połowami) i wiersze zawodników na
mapę. Drużyny bierze z migawek Superbeta i dokłada ich rywali (jeden krok).
Wznawialny — seria kompletna nie jest pytana ponownie; CS2_SETTLE dopisuje do
tych tabel każdą rozliczoną serię. **Kursów historycznych nie ma** (API ofert
Superbeta podaje tylko bieżącą tablicę), więc backfill nie przyspiesza pomiaru
ceny — daje historię modelowi.

Silnik (`src/bet/sofa/cs2_engine.py`) liczy dla każdej ocenionej linii
prawdopodobieństwo z historii sprzed startu serii (cięcie na wcześniejszym z
dwóch zegarów, rozliczana seria wykluczona po id):

- zwycięzca mapy i meczu — Elo na mapach, skalibrowane regresją logistyczną
  z członem gospodarza na własnych przewidywaniach „walk-forward” (tylko
  dane sprzed cięcia), i dokładny rozkład wyniku serii (Bo1/Bo2/Bo3/Bo5);
- zabójstwa/śmierci/asysty/headshoty zawodnika i zabójstwa drużyny —
  rozkład ujemny dwumianowy z `engine.nb_survival` (ostatnie ≤20 map), a gdy
  wariancja nie przekracza średniej — normalny z poprawką ciągłości;
- rundy na mapie — sama częstość bazowa z historii; rundy drużyny na mapie —
  częstość drużyny ściągnięta do częstości bazowej.

**Liczba map, handicap map i mapy drużyny nie dostają liczby.** Model ze
stałym p na mapę zawyżał serie trzymapowe (0,482 wobec 0,424 na 876 Bo3) —
prawdziwe serie są bardziej jednostronne. Na linii całkowitej remis (void)
jest wyłączany z obu stron. Zmierzone na historii 2026-09-28: zwycięzca
meczu 0,2423 wobec 0,2462 dla stałej, statystyki zawodników ≈ moneta —
silnik ledwo bije częstość bazową, a z ceną porównuje go dopiero CS2_SETTLE.

Backfill po odmowie Sofascore (403/429) zatrzymuje się od razu i zapisuje
`runs/sofa/cs2/backfill_cooldown.json` — kolejne uruchomienie odmawia startu
przez 12 h (`--force`, żeby nadpisać). Domyślnie `--max-minutes 6`: jedyna
odmowa w historii przyszła po ~8 min pełnej szerokości; backfill jest
wznawialny, więc uruchamia się go krótko i wielokrotnie.

Pozostałe rodziny nie dostają liczby (nigdy zgadywanej). Stałe silnika są
`UNFITTED` i tak raportowane. `audit_cs2.py` sekcja 3b porównuje Brier kursu,
modelu i ich średniej na tych samych stronach; `--history` pokazuje zawartość
tabel i Brier Elo w teście wstecznym na historii.

Oceniane rodziny: zwycięzca meczu i mapy, liczba i handicap map, rundy (mecz,
mapa, drużyna) i handicap rund, zabójstwa drużyny na mapie oraz zabójstwa,
śmierci, headshoty i asysty zawodnika na mapie. Pomijane: zabójstwa z AWP
(Sofascore ich nie podaje), kombinacje, boosty, dokładne wyniki, rundy
pistoletowe.

Sprawdzone 2026-09-28: `display` mapy w Sofascore zawiera dogrywkę i wiersze
zawodników też (magic – GamerLegion, Ancient 19–17: 24 + 12 rund; sFade8 32–28,
REZ 28–27 — tak samo jak na dust2.us). 84 z 95 serii CS2 z tego dnia to
„Winners series 1x1” i „H2H Liga” — te same 3–4 drużyny co kilka minut —
których Sofascore nie ma; `NOT_ON_SOFASCORE` w pokryciu to głównie one.

Log całego przebiegu: `runs/sofa/run.log.jsonl` (jedna linia JSON na zdarzenie,
`run_id` spina etapy). Baza: `data/sofa.db`.

---

#### Model wyniku (od 2026-10-01) — pomiar, nie kupon

`src/bet/sofa/score_model.py` jest pierwszym modelem samego wyniku tych
sportów. Rating to ten sam `RatingBook` co w piłce (siła ligi, ściąganie
poza ligą), liczony na wyniku całego meczu w czasie regulaminowym
(koszykówka α 0,06, hokej 0,02 — wybrane po błędzie prognozy na historii
2026-03-01..07-15, sprawdzone na 07-15..09-29) i dzielony na okresy według
zmierzonych udziałów; siatkówka — punkty na set (α 0,04). Mecz jest
**symulowany**, a każda symulacja oceniana tym samym `shadow.actual_value` /
`shadow.grade`, którym rozlicza SHADOW_SETTLE, więc prawdopodobieństwo linii
ma dokładnie semantykę jej rozliczenia (czas podstawowy, dogrywka, karne,
push).

Co weszło (każde zmierzone na historii, w obu oknach):

- koszykówka: wspólny szok meczu (tempo) dopasowany metodą momentów na
  resztach kwart — kowariancja między drużynami 1,57 > wewnątrz drużyny
  0,73; średni Brier progów 0,18038 → 0,17972 (tune), 0,18450 → 0,18368 (test);
- hokej: gol do pustej bramki / 6 na 5 przy prowadzeniu 1–2 (0,2 / 0,05) i
  dogrywka ściągnięta do połowy ku monecie; 0,20558 → 0,20514 / 0,20373 →
  0,20353 (mały efekt, ale w obu oknach). Różnica 3 goli jest w historii
  częstsza niż 2 (0,203 vs 0,188) — podpis pustej bramki.

Co odpadło po pomiarze: mecz dzień po dniu (reszta +0,06 pkt, se 0,64 —
efekt NBA z literatury nie występuje w naszych ligach), mocniejsza separacja
drużyn (gorzej w każdym wariancie), wspólny szok Poissona w hokeju
(kowariancja −0,04), w siatkówce szum seta i model zagrywki (lepsza liczba
setów, gorszy zwycięzca).

Przeciw cenie Superbetu (`measure_score_model.py`, 09-29 + 09-30, bootstrap
po meczach; `measure_model_information.py` — test łączony: b ≈ 0 = model
nic nie dodaje do ceny):

| sport | mecze | Brier cena / model | blend 0,25 − cena [95%] | b [95%] |
|---|---|---|---|---|
| hokej | 100 | 0,2153 / 0,2190 | −0,0005 [−0,0029; +0,0019] | 0,12 [−0,55; 0,75] |
| koszykówka | 99 | 0,2345 / 0,2369 | −0,0014 [−0,0045; +0,0016] | 0,37 [−0,13; 0,96] |
| siatkówka | 16 | 0,2226 / 0,1950 | −0,0116 [−0,0290; +0,0025] | 1,13 [−0,19; 3,18] |

Test łączony per rynek: model niesie informację na **sumach** — hokej
b = 0,98 [−0,07; 2,14] przy wadze ceny c = 0,10, koszykówka b = 0,70
[−0,44; 2,26] — a na **zwycięzcy** cena wie więcej (hokej b = −0,38,
koszykówka −0,14, CS2 ok. 0): rynek zna składy, kontuzje i bramkarza.

Żaden sport nie przeszedł reguły wejścia (blend lepszy od ceny z przedziałem
bez zera na co najmniej dwóch dniach), więc kupony sportowe zostały z samej
ceny (do ich wycofania 2026-10-05). Od 2026-10-05 08:30Z model wchodzi na
kupon inaczej: nie jako blend z ceną, tylko przez krzywą kalibracji bez cen
(`config/sofa_sport_confidence_calibration.json`, §10a), a cena jest tylko
filtrem. Kandydaci do obserwacji: sumy hokeja i koszykówki, siatkówka. CS2: silnik dostał Elo zawodników (składy zamiast nazw drużyn; na
historii 0,2382 → 0,2368, bootstrap po seriach [−0,00268; −0,00025]), ale
wobec ceny przegrywa jak wcześniej (0,2026 cena, 0,2171 model, 32 serie).
Literatura (NBA/NHL/CS2) mówi to samo: model z samych wyników nie bije ceny;
zyski dają składy, bramkarz i połączenie z kursem.

## 15. Uruchamianie

```bash
# interpreter ma znaczenie: .venv niesie dwa. `python` to 3.12 i to on
# uruchamia pipeline; `pip` należy do 3.14 i instaluje tam, gdzie nikt nie
# zaimportuje.
.venv/bin/python -m pip install <pkg>      # dobrze
.venv/bin/pip install <pkg>                # po cichu bezużyteczne

.venv/bin/python scripts/sofa/ensure_bridge.py                                    # zawsze pierwsze: podnosi most, potem check_bridge

PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only BOARD --run-id <id>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --from-stage RESOLVE --run-id <id>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only SETTLE

PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <d>                       # 08_confidence.json (piłka, tenis)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only SHADOW            # świeża migawka sportów
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only CS2
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only SPORT_IDENTITY    # most → sport_fixtures.json
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only SPORT_CONFIDENCE  # → 08_confidence_sports.json
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only COUPON_ASSEMBLY   # → 11_coupon.json (= build_coupon.py)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only FIXTURE_CHECK     # w przebudowie, przed CONFIDENCE; most
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <d>                     # KUPON_<d>.pdf + 12_printed.json
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <d>                       # C1–C3, U1–U3
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settle_identity.py --from <D-1> --to <D-1>

PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settlement.py --date <D-1>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_day_deep.py --date <D-1>

PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --from <D-8> --to <D-1>           # dziennik runs/sofa/ledger/results.jsonl; zastępuje wiersze tych dat
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <d> --to <d>                 # odczyt dziennika: tabela na wariant i epokę, nigdy łącznie

# historyczne (wycofane 2026-10-05) — tylko rozliczenie dni do poranka 10-05:
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_sport_coupon.py --from <d> --to <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_multi_coupon.py --from <d> --to <d>
```

Kody wyjścia: **0 = OK, 1 = PARTIAL, 2 = FAILED**. Wyjątek od 2026-09-30:
`record_results.py` (oraz historyczne `settle_sport_coupon.py` i
`settle_multi_coupon.py`) kończy się `0` także wtedy, gdy pozycje jeszcze czekają (widać je w tabeli,
kolumna `pending`), `1` tylko przy `MISMATCH` (dwa oceniające nie zgadzają
się co do nogi — to defekt) albo nieczytelnym pliku, `2` przy awarii albo
(record_results) braku bazy.
Od 2026-10-01 etap `FAILED` **zatrzymuje etapy po nim** (domyślnie; dawne
`--stop-on-failure` jest przyjmowane, ale nic już nie zmienia). Etapy za nim
są raportowane jako `SKIPPED` i nie ruszają swoich artefaktów, bo każdy czyta
poprzedni: tego dnia zablokowana baza zatrzymała RESOLVE na 15 z 461 meczów,
a OFFER i SAMPLES nadpisały dzień tymi 15. `--continue-on-failure` to
świadomy wyjątek. RESOLVE przerwany wyjątkiem zostawia
`02_fixtures.json.INCOMPLETE`; OFFER, SAMPLES, SHEET, COUPON, CONFIDENCE i PDF
odmawiają go czytać (`UPSTREAM_INCOMPLETE`, kod 2), aż czysty RESOLVE usunie
znacznik. Baza działa w trybie WAL (czytający nie blokują zapisu), a zajęty
COMMIT jest ponawiany (`bet.sofa.db`).

Historyczne (kupony sportowe i WSZYSTKIE wycofane 2026-10-05; dziennik
działa tak dalej). Od 2026-10-01 rozliczenie kuponów sportowych, WSZYSTKIE i dziennik sięga
`--from <D-8>`: noga, która po 7 dniach od startu wciąż czeka
(`NOT_ON_SOFASCORE`, `DATA_MISMATCH`), staje się `NOT_GRADED:GAVE_UP`, czyli
nierozliczona, a nie wiecznie „pending”. Kupon sportowy nie bierze już
sparingów ani turniejów, których pomiar nie znalazł na Sofascore
(`friendly_tournament`, `unsettleable_tournament`; lista z dowodem w
`sport_coupon.json`). Turniej jest „nierozliczalny”, gdy w ostatnich 14
rozliczonych dniach przed D co najmniej połowa z ≥ 2 jego meczów była
`NOT_ON_SOFASCORE` — albo, od audytu 2026-10-01, gdy **każdy** z jego
widzianych meczów (≥ 1) był `NOT_ON_SOFASCORE` (`UNSETTLEABLE_ALL_MIN_EVENTS`;
kupon siatkówki 10-01 wydrukował dwie nogi „Brazylia - Paulista U19” i jedną
„Szwecja - Puchar Ligi”, każdy z jednym wcześniejszym, nieznalezionym meczem —
1/1 prześlizgnęło się pod regułą ≥ 2). Turniej niewidziany przechodzi: nie ma
jeszcze dowodu przeciw niemu. Dwie odmowy tylko dla CS2 (od 2026-10-01):
`unseen_team` — strona, której magazyn serii (`cs2_series`) nigdy nie widział
(dopasowanie nazw jak w CS2_SETTLE; „Winners series 1x1” 09-30 poszło 30/30
`NOT_ON_SOFASCORE`), liczone raz na budowę i zapisane w `refused_events`, żeby
`audit_variants` powtórzył dokładnie to, co budowa odrzuciła; pusty magazyn
nie odrzuca niczego — i `no_tournament` — zdarzenie CS2 bez turnieju (gdy
Superbet nie oddał struktury), którego ani bramka sparingów, ani
nierozliczalnych nie umie przeczytać. Noga CS2 z serii ocenionej częściowo
(`pending_sides` w `settled.json`) jest `PENDING:<pending_reason>`, nie
`UNGRADEABLE`, dopóki rekord nie jest ostateczny albo noga nie minie 7 dni.

**`PARTIAL` na RESOLVE / OFFER / SAMPLES to normalny kształt zdrowego
przebiegu**, nie awaria: zawsze jakieś mecze mają luki. Zatrzymuje wyłącznie
`FAILED`.

Budżet czasu pełnego dnia: **2,5–3 h**, z czego większość to SAMPLES.

---

## 16. Co w tym pipelinie jest słabe — i to nie są hipotezy

| rzecz | pomiar |
|---|---|
| selekcja singli jest antyselektywna wobec błędu w `p` | własność sortowania; single −20,4% wobec PDF +8,2% tego samego dnia (2026-09-20) |
| `K_PRICE` nie da się dopasować | krzywa Briera monotoniczna do `w = 0`: model przegrywa z ceną. Reguła plateau **odmawia** podania wartości i to jest informacja, nie brak |
| `MAX_LADDER_SIGMA` bez dywergencji | `NO_DIVERGENCE` na 80 148 wierszach: deklarowane ≈ realizowane w każdym paśmie |
| czytamy ~10% ekranu Superbetu | `unmapped_markets` = 21 290 na 2026-09-21 |
| rynki pochodne nie mają drabiny | nie mogą dziś trafić do kuponu — sufit podany wprost |
| bazy półmeczowe stoją na cieńszej populacji niż pełnomeczowe | `half_match_coherence` w `sofa_league_baselines.json` raportuje niespójność goli −13% / −17% |
| tenisowe rynki długości są przeszacowane o ~25 pp | zmierzone 2026-09-06, **świadomie niepoprawione** (ryzyko przeuczenia) |
| `games_won_for` jest bimodalne, a linia 11,5 leży w dolinie | jeden dzień: 10:17, 11:10, **12:159**, 13:84 |
| tenisa praktycznie nie da się zweryfikować zewnętrznie | statystyki gemów ITF nie są darmowe, a tenis to zwykle 2/3 tablicy |
| `pred_sd` nie jest zapisywane na wierszu | `p_central` odtwarza się tylko przybliżenie (5 z 63 poza tolerancją 0,024) — znane ograniczenie, nie znalezisko |
| `fit_confidence.py` fituje na nieskurczonym `p` | mediana rozjazdu 0,0291, p90 0,1322, 52,4% wierszy poza jednym kubełkiem — patrz `CONFIG.md` |

---

## 17. Twarde zasady

- Nigdy nie wymyślaj liczby, meczu, ceny ani dostępności rynku.
- Nigdy nie podawaj ceny łączonej (parlay / Bet Builder) spoza tego, co
  policzył `confidence.py`, i nigdy nie przedstawiaj `odds_if_product` jako ceny.
- Żadnego dobierania stawki, żadnego automatycznego stawiania.
- Nigdy nie czytaj, nie wypisuj i nie loguj wartości z `.env`.
- Nigdy nie przefitowuj stałych w środku dnia.
- Nigdy nie usuwaj notki `UNFITTED_CONSTANTS`, żeby raport lepiej się czytał.
- Rozliczony wynik jest faktem o dniu, **nie o decyzji, która go wywołała**.
  „Wygrało" nie wchodzi do uzasadnienia następnej decyzji.
