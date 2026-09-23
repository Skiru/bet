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
                                          ↘ CONFIDENCE → PDF
        (osobno, świadomie:)  SETTLE → FIT
```

**Nie ma etapu `DISCOVER`, `ENRICH`, `ANALYZE`, `MARKET_CONTEXT` ani
`TIPSTERS`.** To słownik wycofanego pipeline'u `simple`
(`scripts/simple/`, `src/bet/simple_stats/`, dokumentacja w `docs/legacy/`).
Oba pipeline'y **nie dzielą ani linii kodu, ani jednej nazwy etapu**, i nie
istnieje mapowanie między nimi. Sięgnięcie po słownik `simple` to najczęstszy
sposób na zmarnowanie pierwszego kwadransa sesji — zdarzyło się 2026-09-21
i jest powodem, dla którego ten akapit stoi na początku.

Źródło prawdy o kolejności: `DEFAULT_SEQUENCE` w `scripts/sofa/run_pipeline.py`.
`SETTLE` i `FIT` **nie są** w `DEFAULT_SEQUENCE` — celowo.

| pojęcie | znaczenie |
|---|---|
| **fixture** | jeden mecz, klucz `sofascore_event_id` (int) |
| **metric** | mierzona wielkość, np. `corners_total`, `games_won_for` (30 piłkarskich w `FOOTBALL_METRICS`, 25 tenisowych w `TENNIS_METRICS`, 3 zawodnicze w `PLAYER_METRICS` z `src/bet/sofa/players.py`) |
| **subject** | czyja to wielkość; `""` dla metryk `*_total`, nazwa strony dla `*_for`, **nazwisko zawodnika** dla `player_*_for` |
| **rung / szczebel** | jedna linia rynku: (market, subject, line, direction) |
| **ladder / drabina** | wszystkie linie tego samego rynku wystawione przez Superbet |
| **p_central** | prawdopodobieństwo z naszej próbki |
| **p_bar** | p_central po korekcie kalibracyjnej, zmieszane z ceną rynku |
| **surplus** | `offered_odds − required_odds` |
| **leg** | pojedyncza pozycja w Bet Builderze, rankowana `confidence`, nie `p_central` |
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
                              │           ┌─────▼──────┐
             (NIE jest kuponem)           │    PDF     │
                                          └─────┬──────┘
                                                │ KUPON_<data>.pdf  ★ produkt

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

- Uruchomienie: `.venv/bin/python scripts/sofa/bridge_server.py` i otwarta
  karta z aktywnym userscriptem.
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
  zapada się 78-krotnie, bo bezczynne karty wracają do 20 s `/pull`.
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
| `MATCH_LOGIC_VERSION` | 3 | stempluje **negatywny cache**; zmiana logiki unieważnia zapamiętane pudła |

`MATCH_LOGIC_VERSION` to nie kosmetyka. Negatywny cache pamięta „szukaliśmy
i nie ma", co jest faktem o świecie tylko wtedy, gdy szukanie było poprawne.
2026-09-18 błędna bramka płci uczyniła 175 tenisistek nierozwiązywalnymi,
zapisała je jako pudła, a po naprawie RESOLVE wyprodukował **bajt w bajt
identyczny artefakt**, bo już nie zapytał.

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
- **piłka:** mecze towarzyskie wypadają (`config/sofa_friendly_competitions.json`);
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
  projekt, nie luka;
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
`INTERNAL_INCONSISTENT`, `THIN_SAMPLE`, `SURFACE_UNKNOWN`, `NO_PRICE`,
`STALE_PRICE`, `PROVIDER_ERROR`, `CIRCUIT_OPEN`. Awaria dostawcy blokuje
**mecz**, nie dzień.

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

```
prior   = baza ligowa, a gdy jej nie ma — globalna     (config/sofa_league_baselines.json)
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
- `totalOffside` też bywa pominięte, ale **nie ma** tożsamości, która
  udowodniłaby zero, więc `player_offsides_for` **nie istnieje**, mimo że
  Superbet ten rynek wycenia.

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

### 7.5 Werdykty

`VALUE` (przebija próg) · `LEAN` (blisko, ale bramka drabiny lub próg mówi nie)
· `BELOW_BAR` · `NO_PRICE` · `BLOCKED`.
2026-09-21: 118 VALUE, 300 LEAN, 5317 BELOW_BAR, 47 NO_PRICE.

---

## 8. `vetoes.json` — jedyny kanał analityka

Plik `runs/sofa/<data>/vetoes.json`, pisany **po SHEET, przed COUPON**,
czytany przez **COUPON i CONFIDENCE naraz** (to drugie od 2026-09-21 — wcześniej
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

**Wariant operatora (`--profile wariant`, od 2026-09-23).** Próg pewności
**0,65** i kurs do **10% poniżej uczciwego** (pewność × kurs ≥ 0,90); limit
niezgody z kursem (0,10) i marży (10,5%) bez zmian. Pisze do **własnych**
plików — `08_confidence_wariant.json/.md` i `KUPON_<data>_WARIANT.pdf` — i nigdy
nie nadpisuje oficjalnego kuponu. Zmierzony przed dodaniem na 18–22.09
(`scripts/sofa/sweep_confidence_gates.py`, każdy dzień na krzywej, która go nie
widziała): **−3,2%** na zakład przy 5 802 zakładach, wobec −2,9% oficjalnego
przy 1 655. Kupuje więcej zakładów, nie przewagę. Rozliczany obok kuponu w
sekcji **7d** raportu `audit_settlement.py`, z osobnym wierszem „tylko w
wariancie” — to jest dokładnie to, co wariant dokłada.

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
| `DERIVED_NOT_CALIBRATABLE` | rynek pochodny (`both_over_`, `handicap_`, `most_`) — ma 2–252 rozliczonych wierszy i żadna próbka z artefaktów go nie sprawdzi |
| `NOT_CALIBRATED` | dla tego kubełka **nie ma pomiaru**; własna liczba modelu nie jest jego substytutem |
| `BELOW_CONFIDENCE_FLOOR` | `realised_lo < --floor` |
| `DISAGREES_WITH_PRICE` | `realised_lo − 1/odds > MAX_DISAGREEMENT = 0.10` |
| `NEGATIVE_LEG_EV` | noga nie przebija własnej ceny (`leg_is_ev_positive`) |
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
- pula i kombinacje rankowane po **`leg_ev`**, na **obu** poziomach. Ranking po
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

## 11. PDF — produkt

`scripts/sofa/build_coupon_pdf.py --date <d> [--out …] [--runs-dir …]` →
**`runs/sofa/<data>/KUPON_<data>.pdf`**

Renderuje **wyłącznie** pozycje przechodzące `is_stakeable`, każdą z własnym
śladem dowodowym. **`picks: 0` to odpowiedź legalna i częsta** — i zwykle jest
skutkiem narzutu korelacyjnego, nie braku danych.

To jest jedyny plik, który się stawia.

---

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

Granica metody, podana wprost: nie mamy historycznych cen Superbetu. Wstecz da
się mierzyć **kalibrację prawdopodobieństwa** (czy 85% znaczy 85%). **Nie da
się mierzyć ROI.** Nie raportuj drugiego z pierwszego.

Odczyt: `scripts/sofa/audit_settlement.py --date <d>` — **sekcja 7c to
prawdziwy wynik kuponu z PDF**; sekcje 7 i 7b to materiał wejściowy (legi
i kandydaci), **nie zakłady**. Potem `scripts/sofa/audit_day_deep.py --date <d>`
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
`half_match_coherence` — w [`CONFIG.md`](CONFIG.md).

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
  08_confidence.json/.md                  legi i Bet Buildery
  KUPON_<data>.pdf                        ★ produkt — to jest kupon
  vetoes.json          Veto[]             kanał analityka; [] w większość dni
```

Log całego przebiegu: `runs/sofa/run.log.jsonl` (jedna linia JSON na zdarzenie,
`run_id` spina etapy). Baza: `data/sofa.db`.

---

## 15. Uruchamianie

```bash
# interpreter ma znaczenie: .venv niesie dwa. `python` to 3.12 i to on
# uruchamia pipeline; `pip` należy do 3.14 i instaluje tam, gdzie nikt nie
# zaimportuje.
.venv/bin/python -m pip install <pkg>      # dobrze
.venv/bin/pip install <pkg>                # po cichu bezużyteczne

.venv/bin/python scripts/sofa/check_bridge.py                                     # zawsze pierwsze

PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only BOARD --run-id <id>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --from-stage RESOLVE --run-id <id>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only SETTLE

PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <d> --profile wariant     # wariant, obok kuponu
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <d> --profile wariant   # → KUPON_<d>_WARIANT.pdf

PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settlement.py --date <D-1>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_day_deep.py --date <D-1>
```

Kody wyjścia: **0 = OK, 1 = PARTIAL, 2 = FAILED**.
`--stop-on-failure` przerywa przy pierwszym `FAILED` zamiast iść dalej.

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
