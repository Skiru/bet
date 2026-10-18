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
(usuniętego z repozytorium 2026-10-05; jest w historii gita).
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
                                                │ KUPON_<data>.html   widok z filtrami (nie kupon)

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

**Kursy nieodwzorowanych rynków są zapisywane** (od 2026-10-14,
`bet.sofa.unmapped_prices`): każdy przebieg OFFER dopisuje każdy kurs, który
trafił do `unmapped_markets`, do `runs/sofa/<d>/unmapped_prices/<ts>.jsonl.gz`
(nowy plik na przebieg, nic nie jest nadpisywane; tylko przed meczem). To
zapis, nie wejście: żaden etap tego nie czyta i nic się od tego nie drukuje.
Powód: rynek, który później zaczniemy modelować (np. strzały zawodnika spoza
pola karnego z `/shotmap`), musi mieć historię cen Superbetu, inaczej jego
dowody z linii (przesunięcie, pasma ceny) startują od zera w dniu włączenia.
Błąd zapisu nie zatrzymuje OFFER (`OFFER_UNMAPPED_PRICES_NOT_WRITTEN`).

**Rodziny MAPPABLE za przełącznikiem `MAPPABLE_FAMILIES_FROM_UTC`**
(`bet.sofa.epochs`, plan nocy 2026-10-12 C1; **włączony od 2026-10-14
00:00Z** decyzją operatora z 2026-10-13 – E2E na próbkach 10-13 czyste on/off,
część z mostem niesprawdzona, Sofascore 403:
`docs/sofa/evidence/mappable_e2e_2026-10-14.md`). Włączony, OFFER czyta dodatkowo
(`market_mapper.classify_mappable_family`, zawsze po wszystkich dotychczasowych
klasyfikatorach): „<drużyna> strzeli gola” i połowy (`goals_for` /
`goals_1h_for` / `goals_2h_for` 0,5; tak = OVER, nie = UNDER; podmiot musi być
stroną listingu – zawodnik ma ten sam kształt nazwy), „Zostanie rozegrany N.
set” (`sets_total` N − 0,5, bez zgadywania best-of), „N.połowa - obie drużyny
strzelą” (`both_over_goals_1h` / `_2h`), „[N. połowa -] każda z drużyn powyżej
X obronionych strzałów przez bramkarza” (`both_over_saves` / `_1h`), „N.
połowa - rzuty rożne - handicap” (`handicap_corners_1h` / `_2h`), „N. set -
handicap gemy” (`handicap_games_won_set1` / `_set2`). Odpowiedź tak/nie na
szczebel, który drabina już kwotuje (`market_mapper.is_ladder_answer`), **nie
dodaje drugiego szczebla**: zostaje szczebel drabiny, odpowiedź wypełnia tylko
szczebel, którego drabina nie ma (2026-10-12: 19 z 546 piłkarskich i 1 z 48
tenisowych), a strony dwóch rynków nigdy się nie mieszają. Przy `None` wyjście
OFFER jest bajt w bajt jak przed zmianą (`tests/sofa/test_mappable_families.py`,
golden `tests/sofa/golden/offer_mappable_off.json`). Nowe rynki pochodne nie
mają krzywej – `NO_LINE_EVIDENCE` do 50 rozliczonych linii; szczeble
`goals_*_for` 0,5 i `sets_total` czytają istniejące krzywe, więc mogą drukować.

**Zwycięzca meczu w tenisie za przełącznikiem `TENNIS_MATCH_WINNER_FROM_UTC`**
(`bet.sofa.epochs`, audyt 2026-10-13 D2; **włączony od 2026-10-14 00:00Z**,
decyzja operatora; umiejętność -0,1263 [-0,1303; -0,1228] log-loss wobec bazy
klasy; próg kalibracji krzywej niespełniony, ale wyłącznie po stronie
ostrożnej: >= 0,70 pewność 0,802 vs realizacja 0,828 na holdoucie; krzywa
`match_won_for` od 2026-10-16 przenoszona przez sam `fit_confidence`,
`fit_meta.carry_separately_fitted_curves` – wcześniej wklejana ręcznie). Włączony,
OFFER czyta „Zwycięzca” (wybory „1” / „2”, tylko mecz tenisowy) jako jeden
dwustronny szczebel `match_won_for`: podmiot = pierwsze nazwisko `matchName`
Superbetu, linia 0,5, OVER = on wygrywa (kurs „1”), UNDER = wygrywa drugi
(kurs „2”) – marża drabiny działa jak wszędzie (`bet.sofa.tennis_winner`).
SAMPLES nie buduje próbki; SHEET liczy p z ratingu as-of
(`MatchForecast.p_side_wins`, bez ceny; brak prognozy = `NOT_RATED`), wiersz
ma `sample_size` 0 i `bar_reason` `rating_only`. CONFIDENCE czyta wyłącznie
krzywą `match_won_for` (kobiety: `by_class.tennis_women`; dziura lub zakres
ponad krzywą = odmowa, nigdy pula – `confidence.OWN_CURVE_ONLY`), potem line
evidence jak każdy klucz; bramki próbki (`LINE_BEYOND_SAMPLE`, `MODE_LOSES`,
rozmiar, wiek) go nie dotyczą, a noga nie wchodzi do builderów. SETTLE:
`winnerCode` z listingu; krecz / walkower to zwrot (`settle.REFUND_REASONS`).
Krzywą dopasowuje `scripts/sofa/fit_tennis_winner_curve.py` (replay ratingu,
plik staged poza `config/`); pomiar i próg:
`docs/sofa/evidence/tennis_match_winner_2026-10-13.md`. Przy `None` OFFER jest
bajt w bajt jak przed zmianą (`tests/sofa/test_audit_2026_10_13_d2.py`).

**Podwójna szansa w piłce za przełącznikiem `FOOTBALL_RESULT_MARKETS_FROM_UTC`**
(`bet.sofa.epochs`, audyt D1, znacznik `result_markets_v1`; **włączony od
2026-10-14 14:20Z**, operator „WŁĄCZ OD TERAZ” – w dzień już zbudowany, 10-14
mieszany; 1X2 i DNB osobnym przełącznikiem, niżej). Włączony, OFFER czyta pełnomeczową
„Podwójna szansa” (wybory „1X” / „X2” / „12”; nie połowy, nie kombinacje
„Podwójna szansa & …”) jako rynek `double_chance`: wybór w `subject`, linia
0,5, kurs DC = OVER, a kurs wyniku z „Mecz”, który ten wybór wyklucza
(`2` / `1` / `X`), = UNDER – marża drabiny działa jak wszędzie. Bez „Mecz”
szczebel jest jednostronny (nie drukuje się bez krzywej), sam „Mecz” bez DC
nie tworzy szczebla. SAMPLES nie buduje próbki; SHEET liczy p wyboru z
niezależnych NB goli obu stron na **czystym ratingu**
(`FootballForecast.centre("goals_for", side)`, `football_result.result_probs`),
r = 7,586 z `config/sofa_football_result.json` (zmierzone, nie z fitu – notka
`UNFITTED_CONSTANTS: FOOTBALL_RESULT_NB_R`); tylko OVER (UNDER to pojedynczy
wynik 1X2, który progu nie spełnił), wiersz ma `result_rule`, `sample_size` 0,
`bar_reason` `rating_only`; brak środka ratingu = brak wiersza (`NOT_RATED`),
para `UNLINKED` dostaje `CROSS_LEAGUE_UNLINKED` jak każdy wiersz piłki.
Od 2026-10-15 00:17Z `double_chance|OVER` (i `women:double_chance|OVER`) ma
**zainstalowaną krzywą z historii** (`fit_double_chance_curve.py`, ten sam
estymator; przyjęta przez jednostronną bramkę holdoutu – patrz „Krzywe
nowych rynków” niżej); CONFIDENCE czyta tylko ją (nigdy pulę,
`confidence.OWN_CURVE_ONLY`), potem line evidence jak każdy klucz. Wybór
(1X / X2 / 12) nie jest w kluczu, więc jedna krzywa łączy trzy wybory
(`docs/sofa/evidence/new_market_curves_2026-10-15.md`). SETTLE rozlicza wybór po wyniku z 90 minut
(`metrics.double_chance_value`, `normaltime` po dogrywce i karnych, jak gole).
Plan i pomiar: `docs/sofa/evidence/football_result_phase_2026-10-13.md`.
Przy `None` OFFER i SHEET są bajt w bajt jak przed zmianą
(`tests/sofa/test_football_double_chance.py`).

**1X2 i zakład bez remisu za przełącznikiem `FOOTBALL_RESULT_1X2_DNB_FROM_UTC`**
(`bet.sofa.epochs`, `bet.sofa.football_1x2_dnb`; **włączony od 2026-10-15
00:00Z**). OFFER czyta dodatkowo „Mecz” 1 / 2 jako `result_1x2` i „Zakład bez
remisu” jako jeden szczebel `draw_no_bet` – OVER gospodarz, UNDER gość, remis
to zwrot (`DNB_DRAW_REFUND`); noga męska we wczesnej fazie sezonu czyta klasę
krzywej `season_early`. Klucze DNB (`draw_no_bet` OVER / UNDER, a także
`season_early:` i `women:` OVER) przeszły jednostronną bramkę holdoutu i mają
zainstalowane krzywe od 2026-10-15 00:17Z; każdy klucz 1X2 bramki nie
przeszedł – krzywej nie ma, `NO_LINE_EVIDENCE` do 50 rozliczonych linii / 15
meczów w kubełku. Pomiar: `docs/sofa/evidence/football_1x2_dnb_phase_2026-10-15.md`.

**Piłkarskie rynki „lub”, handicap i DC & gole za przełącznikiem
`FOOTBALL_SCORE_MARKETS_FROM_UTC`** (`bet.sofa.football_score_markets`;
**włączony od 2026-10-16 07:46Z** – operator przesunął go z 10-17 00:00Z do
zbudowanego dnia, 10-16 jest mieszany, grupa ledgera „10-16 mieszany”;
przebudowa od 07:46Z sama czyta OFFER ponownie, gdy `04_offer.json` nie ma
takiego rungu, i powtarza SHEET, gdy `05_sheet.json` nie ma takiego wiersza,
`rebuild_plan`). OFFER czyta: „Mecz lub liczba goli (L)”
i „<drużyna> / Remis lub powyżej / poniżej X goli w meczu” jako
`result_or_over` / `result_or_under` (podmiot 1 / X / 2, linia L), „Obie
drużyny strzelą gola lub powyżej L gola” jako `btts_or_over`, „… lub obie
drużyny strzelą gola” i „… lub którakolwiek drużyna zachowa czyste konto”
jako `result_or_btts` / `result_or_clean_sheet`, „Handicap” +1.5 / +2.5 /
+3.5 jako `result_handicap` (+0.5 to podwójna szansa – nieczytane) i
„Podwójna szansa & liczba goli” 12 & powyżej / 1X & poniżej jako
`dc_and_over` / `dc_and_under`. Ten sam zakład z dwóch rynków Superbetu –
niższa cena, bez kolizji. SHEET wycenia OVER z siatki NB podwójnej szansy
na czystych centrach ratingu (znacznik `score_market_rule`, faza sezonu
`result_phase`); SETTLE rozlicza zdarzenie na wyniku po 90 minutach przy
0,5 (nie przy linii goli). Krzywa jest **per wycinek** –
`<rynek>@<podmiot>@<linia>|OVER` (`confidence.curve_market`): jedna krzywa
na rynek ukrywała wycinki zawyżające o 3–9 pp; mecz męski we wczesnej fazie
sezonu czyta `season_early:`, kobiecy `women:`; wycinek bez krzywej nie
czyta żadnej puli. Kilka linii jednego meczu to jeden scenariusz, ale PDF
nie grupuje ich jako „ta sama zmienna” (zdarzenia dwuwymiarowe, jak DC).
Pomiar i E2E: `docs/sofa/evidence/football_score_markets_2026-10-16.md`.

**Tenisowe dopełnienie wyniku setów za przełącznikiem
`TENNIS_SET_COMPLEMENTS_FROM_UTC`** (jedzie na `TENNIS_SET_MARKETS`;
**włączony od 2026-10-16 07:46Z**, jak wyżej): `set_score_not`, podmiot „<gracz> 0:2”,
OVER = gracz wygra co najmniej seta – „<gracz> wygra seta” Tak, „Handicap
setowy” „<gracz> (1.5)”, „<gracz> liczba setów” powyżej 0,5 oraz „<rywal>
wygra bez straty seta” Nie (jeden rung, jedna noga); p = 1 − udział 0:2
wśród sąsiadów ratingu (tylko mecze do 3 setów), znacznik
`set_complement_rule`, krzywa własna (+ `tennis_women:`).

**Strzały zawodnika według miejsca i części ciała za przełącznikiem
`SHOT_DETAIL_MARKETS_FROM_UTC`** (`bet.sofa.epochs`, znacznik
`shot_detail_v1`; **włączony od 2026-10-14 14:20Z**, operator „WŁĄCZ OD
TERAZ”, 10-14 mieszany). Włączony,
OFFER czyta osiem rynków „Zawodnik - liczba (celnych) strzałów spoza pola
karnego / głową / lewą nogą / prawą nogą” (`shot_detail.MARKET_NAMES`) tak
samo jak pozostałe rynki zawodnika (`market_mapper.classify_player_market`,
ten sam odczyt zawodnika, linii i kierunku). SAMPLES pobiera do każdego meczu
próbki obok `/lineups` także `/shotmap` (`samples.fetch_shotmap`, cache
`sofa_event_extra`), a `players.squad_statistics(..., shotmap=...)` wpisuje
liczby tylko wtedy, gdy strzały zawodnika w shotmapie równają się jego
`totalShots` z `/lineups` – inaczej (brak shotmapy, niezgodność) to luka
`STAT_KEY_ABSENT`, nigdy zero; próbka zapisuje też pozycję zawodnika z
najnowszego meczu (`position`). SHEET liczy p z `shot_detail.forecast`
(ostatnie starty skurczone do średniej pozycji, Poisson) na pliku
`config/sofa_shot_detail.json` – **zainstalowany** (fit
`data/refit_shot_detail_2026-10-14/`; w `config_sha` wchodzi jako plik
opcjonalny, `sheet_config.SHEET_OPTIONAL_FILES`); bez pliku wiersza nie ma
(`NO_SHOT_DETAIL_FIT`); wiersz ma `shot_detail_rule`, `bar_reason`
`shot_detail`. Od 2026-10-15 00:17Z `player_left_foot_shots_for|OVER` i
`player_right_foot_shots_for|OVER` mają zainstalowaną krzywą z historii
(jednostronna bramka holdoutu); pozostałe sześć (spoza pola karnego, głową i
każdy celny) krzywej nie mają – CONFIDENCE czyta tylko własne linie
Superbetu klucza, `NO_LINE_EVIDENCE` do 50 rozliczonych linii / 15 meczów w
kubełku. SETTLE rozlicza z shotmapy meczu (starter bez strzału w shotmapie
z `totalShots` 0 to 0, niezgodność to luka). Pomiar:
`docs/sofa/evidence/shot_detail_2026-10-14.md`. Przy `None` OFFER, SAMPLES,
SHEET i SETTLE są bajt w bajt jak przed zmianą
(`tests/sofa/test_shot_detail_markets.py`).

**Rynki piłki z incydentów za przełącznikiem
`FOOTBALL_INCIDENT_MARKETS_FROM_UTC`** (`bet.sofa.epochs`, znacznik
`incident_markets_v1`; **włączony od 2026-10-14 14:50Z**, operator „1. 2.
tak”, 10-14 mieszany).
Włączony, OFFER czyta (tylko piłka) „1. gol” jako `first_goal` (wybór
drużyny z nazw listingu Superbetu: `subject` „1” / „2”, „nikt” = „nikt”,
linia 0,5, tylko OVER – szczebel jednostronny, bez krzywej się nie drukuje),
„Liczba czerwonych kartek” jako `red_cards_total` i „Liczba przyznanych
rzutów karnych” jako `penalties_total` (Poniżej / Powyżej X.5, dwustronne);
połowy, warianty drużyn, przedziały minut i „1. gol & …” zostają
nieczytane. SAMPLES nie buduje próbki. SHEET: `first_goal` z niezależnych NB
goli na **czystym ratingu** (jak podwójna szansa, r z
`config/sofa_football_result.json`): P(nikt) = P(0:0), P(strona pierwsza) =
(1 − P(nikt)) × jej udział w oczekiwanych golach; kartki i karne – as-of
częstość rozgrywek (mecze z pełnym zapisem incydentów, czyli z
substytucjami, sprzed dnia) ściągnięta do częstości płci z wagą 30 meczów
(`FOOTBALL_INCIDENT_BASE_M` w `UNFITTED_CONSTANTS`), tylko linie 0,5 i 1,5;
wczytanie częstości z `sofa_event_stats` to ~1 min SHEET (tylko przy
włączonym). Wiersz ma `incident_rule`, `sample_size` 0, `bar_reason`
`rating_only`; para `UNLINKED` dostaje przy `first_goal`
`CROSS_LEAGUE_UNLINKED`. Od 2026-10-15 00:17Z zainstalowane krzywe z
historii mają `first_goal|OVER` (drukuje się jako singiel jednostronny,
`confidence.one_sided_single`), `red_cards_total|UNDER` i
`penalties_total|UNDER`; OVER kartek i karnych krzywej nie ma –
`NO_LINE_EVIDENCE` do 50 rozliczonych linii / 15 meczów w kubełku. SETTLE
rozlicza z incydentów czasu regularnego (`football_incidents.incident_value`:
dogrywka i seria karnych się nie liczą; czerwona = `red` i `yellowRed`
zawodnika, bez sztabu i anulowanych; karny przyznany = gol z karnego +
`inGamePenalty`); zapis niepełny (bez substytucji) to brak oceny kartek i
karnych, lista niezgodna z wynikiem z 90 minut – brak oceny w ogóle.

**Tenis: zwycięzca seta i dokładny wynik w setach za przełącznikiem
`TENNIS_SET_MARKETS_FROM_UTC`** (`bet.sofa.epochs`, znacznik
`tennis_set_markets_v1`; **włączony od 2026-10-14 14:50Z**, operator „1. 2.
tak”, 10-14 mieszany). Włączony, OFFER czyta
(tylko tenis) „X. set - zwycięzca” („1. set - <nazwisko>” / „2. set - …”)
jako `set1_won_for` / `set2_won_for` (podmiot = pierwsze nazwisko listingu,
linia 0,5, OVER on wygrywa seta, UNDER kurs rywala – jak zwycięzca meczu) i
tenisowy „Dokładny wynik” („2:0” … „0:2”) jako `set_score` (podmiot
„<pierwsze nazwisko> a:b”, tylko OVER – jednostronny). SHEET liczy p z 600
sąsiadów ratingu gospodarza (`MatchForecast.neighbours_home`, wygładzenie
jak w pomiarze), tylko best of three; wiersz ma `set_market_rule`. Od
2026-10-15 00:17Z krzywe z historii są zainstalowane dla `set1_won_for` i
`set2_won_for` (OVER i UNDER) oraz `set_score|OVER`, każda także w klasie
`tennis_women:`. SETTLE rozlicza z wyników setów listingu
(`tennis_sets.set_value`). Pomiar obu grup:
`docs/sofa/evidence/football_incidents_tennis_sets_2026-10-14.md`. Przy
`None` OFFER i SHEET są bajt w bajt jak przed zmianą
(`tests/sofa/test_football_incident_markets.py`,
`tests/sofa/test_tennis_set_markets.py`).

**Krzywe nowych rynków (zainstalowane 2026-10-15 00:17Z).** Zgoda operatora
2026-10-14 („zbudować krzywe dla tych wszystkich rynków”); przed budową
10-15, więc dzień nie jest mieszany. `scripts/sofa/install_new_market_curves.py
--dir data/refit_new_markets_2026-10-15 --confirm`, testy `tests/sofa`
przeszły, kopia `config/backup_2026-10-15_new_markets/`; każdy klucz ma w
pliku pochodzenie `new_market_curves_fitted_from`. 29 krzywych z historii
rynków włączonych 10-14 / 10-15, dopasowanych przed 2026-10-15 i przyjętych
przez **jednostronną bramkę holdoutu** (operator 2026-10-14 18:55Z;
`scripts/sofa/new_market_gate.py`: fit przed 2026-09-01, ocena na
09-01..10-13; klucz przechodzi, gdy przy krzywej >= 0,70 ma n >= 300
prognoz holdoutu i zrealizowane − krzywa >= −2 pp – odpada więc tylko za
**zawyżenie**, zaniżenie przechodzi; każdy klucz „12” odrzucony z zasady; reguła dopuszczenia
sportów bez zmian). Piłka / tenis (`config/sofa_confidence_calibration.json`):
`player_left_foot_shots_for` / `player_right_foot_shots_for` OVER,
`double_chance` OVER (+ `women:`), `first_goal` OVER, `penalties_total` /
`red_cards_total` UNDER, `set1_won_for` / `set2_won_for` OVER i UNDER,
`set_score` OVER (każdy + `tennis_women:`), `draw_no_bet` OVER / UNDER (+
`season_early:` i `women:` OVER). Sporty
(`config/sofa_sport_confidence_calibration.json` i jego `.next.json`): hokej
`double_chance` / `period_double_chance` TEAM, koszykówka `double_chance`
TEAM, siatkówka `team_sets_exact` NO / `team_wins_set` YES, CS2
`rounds_handicap` TEAM, `rounds_total` OVER, `team_rounds` OVER. **Każdy inny
nowy klucz** (1X2, „12”, strzały spoza pola / głową / celne, kartki i karne
OVER, połowy i kwarty koszykówki, `sets_count` siatkówki) krzywej nie ma:
`NO_LINE_EVIDENCE`, dopóki jego własne linie nie dadzą 50 rozliczonych linii
/ 15 meczów w kubełku. Line evidence czyta zainstalowane klucze jak każdy
inny (offset / limit pasma tylko obniżają). E2E na kopii 10-14 (zegar
budowy, przed vs po): +110 nóg, 0 utraconych, pewność wspólnych nóg bez
zmian; **102 ze 110 z pewnością poniżej 1/kurs** (przechodzą przez x >=
0,90) – czy te rynki biją cenę Superbetu, nie jest zmierzone. Raport:
`docs/sofa/history/RAPORT_KRZYWE_NOWE_RYNKI_2026-10-15.md`; dowody bramki:
`docs/sofa/evidence/new_market_curves_2026-10-15.md`.

**Sporty mierzone nie mają `unmapped_markets`.** SHADOW i CS2 zapisują w
`snapshots.jsonl` tylko linie, które czytają. Inwentaryzacja ich nieczytanych
nazw (`report_market_coverage.py --date <d> --sports-only`, plan nocy
2026-10-12 C5) pyta więc ofertę Superbetu na żywo (bez mostka; tylko mecze
przed startem – rozegrany mecz nie ma już oferty) albo czyta zapisane payloady
(`--sports-raw-dir`), i daje każdej nazwie jedną etykietę MAPPABLE /
COMPUTABLE / NOT_COMPUTABLE (`market_coverage.classify_sport_market_name`),
obok podsumowania snapshotów dnia. Raport → `market_coverage_sports.json/.md`;
nic, co czyta potok.

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
- **piłka:** mecze towarzyskie wypadają (`config/sofa_friendly_competitions.json`: 853, 1794 i od 30.09 28008 — towarzyskie klubowe kobiet); działa tylko w SAMPLES, więc próbka pobrana przed dodaniem id nadal je zawiera. Od 2026-10-04 wypada też 851 (towarzyskie reprezentacji mężczyzn), więc mecz towarzyski mężczyzn czyta gole z 10 najnowszych meczów o stawkę; `epochs.MEN_FRIENDLY_SAMPLE_WINDOW_FROM_UTC` (od 2026-10-14 00:00Z, decyzja operatora) zmienia to tylko dla meczu dnia w 851 i tylko dla `goals_total` / `goals_for` - patrz sekcja 7, „Reprezentacje, poza audytem”. 852 (kobiety) bez zmian;
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
          (przed 2-5, od epochs.MEN_FRIENDLY_BASELINE_FROM_UTC - 2026-10-14 00:00Z:
           mecz 851, goals_total / goals_for: średnia goli meczów 851 sprzed
           dnia, ≥30 meczów, goals_for = połowa    notka PRIOR_MEN_FRIENDLY)
w_c     = n / (n + K_CENTRE)                           (piłka 15, tenis 5; osobne K na rynek: `PER_MARKET_K`, od 2026-10-09)
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
globalnie 10, piłka 15, tenis 5); `K_PRICE` z tego samego pliku, gdzie ma
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
  rozgrywkami) **obu** z nich. Wspólny puchar, który właśnie grają,
  nie wystarcza. Od 2026-10-07 06:45Z (`epochs.LINK_SHARED_LEAGUE_FROM_UTC`,
  decyzja operatora - z 10-07 nic nie postawiono; wiersze arkusza niosą
  `link_rule`, a przebudowa puszcza SHEET na arkuszu ze starą regułą;
  wcześniej wystarczała liga jednej z nich): beniaminek / spadkowicz ma ligą
  swoją starą ligę, dopóki w nowej nie zagra więcej, i po trzech meczach był
  `LINKED` z nowymi rywalami, a jego stosunki ze starej ligi szły 1:1 bez siły
  ligi (Visby/Roma z HockeyEttan, Leksand z SHL, AZ Havirov z 2. ligi; 10 nóg
  hokejowych 10-07 zdjętych NO_BET). Teraz taka para idzie przez siłę ligi
  (`LINKED_BY_STRENGTH`) albo jest `UNLINKED`. Pomiar:
  `scripts/sofa/measure_link_rule.py`, raport
  `docs/sofa/history/RAPORT_LINKED_2026-10-07.md`. Dotyczy też modelu wyniku
  sportów mierzonych (`score_model` używa tej samej książki ratingów);
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

**Siła ligi w pucharach międzynarodowych (od 2026-10-16 00:00Z,
`epochs.FOOTBALL_CUP_STRENGTH_FROM_UTC`, zgoda operatora 2026-10-15).**
Sigma domeny uczy się z każdego meczu niepołączonego - głównie krajowych
pucharów z własnymi niższymi ligami - więc mierzy przewagę ligi nad jej
zapleczem, a czołowe ligi różnych krajów porządkuje źle (Ekstraklasa -
Bundesliga -0,09, PrvaLiga nad ligą cypryjską). Na 3 740 meczach
pucharowych od 2024-07 rating zaniżał stronę z silniejszej ligi o +5,2 pp
P(wygranej) [+3,6; +7,0]. Teraz `RatingBook` niesie dodatkową korektę `d`
na (rozgrywki krajowe, metrykę), uczoną **tylko** z meczów cross-league
dziewięciu pucharów z `config/sofa_cup_strength.json` (LM, LE, LK, AFC
Elite / Two, Libertadores, Sudamericana, CAF, CONCACAF), krokiem z tego
pliku, wewnątrz `update` (reszta liczona już z `d`, więc ilorazy drużyn
chłoną mniej luki ligowej). Mecz takiego pucharu czyta `sigma_h - sigma_a +
d_h - d_a`; mecz spoza tych pucharów `d` nie czyta (czuje tylko zmienione
ilorazy drużyn, które w pucharach grały). Korekta tylko tam, gdzie poza
próbą lepsza z przedziałem poza zerem: gole (krok 0,05; log-loss 1X2
-0,0285 [-0,0381; -0,0188] na 2 194 meczach TEST), gole 1. poł. (0,05),
gole 2. poł. (0,02), strzały (0,02). Rożne i strzały celne - nie (w zerze);
pozostałe metryki niemierzone, bez korekty. Rożne / kartki / faule meczu
pucharowego i tak się ruszają przez stan gry (B1), który czyta gole. Efekt
uboczny na 302 635 meczach spoza pucharów: gole -0,00003 [-0,00006;
-0,000003] - nic nie pogorszone. Wiersze SHEET-u niosą `cup_strength_rule`
(`cup_strength_v1`); przebudowa dnia >= 10-16 puszcza SHEET na arkuszu bez
niego. Plik `sofa_cup_strength.json` to lista operatora z wybranym krokiem,
nie fit: nie wchodzi do `config_sha`. Replay: `calibrate_from_cache.py
--cup-strength` (`prepare_refit.py rebuild-cache-rows --cup-strength`).
Ograniczenie: korekta próbki B15 przeskalowuje mecz pucharowy z próbki samą
sigmą (bez `d`). Dowód: `docs/sofa/evidence/cross_league_cups_2026-10-15.md`;
raport: `docs/sofa/history/RAPORT_SILA_PUCHAROW_2026-10-16.md`.

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

**Zmierzone 2026-10-13 (audyt), niewłączone:**
- `epochs.FOOTBALL_LEAGUE_RATE_RULE_FROM_UTC` (A2, połowa piłkarska): rozgrywki
  z < 30 meczami bez stawki globalnej (centrum z samej próbki). Na historii
  2025-08-01..2026-10-12 stara reguła (rating ze średnią wszystkich lig w
  połowie centrum) jest lepsza: SE na stronę -0,58 [-0,62; -0,54] na jej
  korzyść, każda metryka tego samego znaku. Zostaje `None`.
- `epochs.UNIT_STRENGTH_FROM_PARENT_FROM_UTC` (A1): jednostka regionalna
  (`assign_league_units`) startuje z siłą rozgrywek-rodzica, nie z 0. Gole,
  one step ahead 06-01..10-12, mecze ponadligowe z jednostką: log-loss
  -0,0010 [-0,0029; +0,0008] na mecz (7 724 mecze) - kierunek zgodny,
  przedział obejmuje zero. Zostaje `None`.

**Reprezentacje, poza audytem - zmierzone 2026-10-13, włączone od 2026-10-14
00:00Z decyzją operatora („Wszystkie rynki włączone”)**
(`docs/sofa/evidence/national_friendly_samples_2026-10-13.md`,
`scripts/sofa/measure_national_friendly_samples.py`; 2 209 meczów
towarzyskich mężczyzn 2015-01-01..2026-10-12, log-loss NB środka przy liczbie
goli, bootstrap po meczach, bez ratingu w środku; kod: `bet.sofa.men_friendly`):
- `epochs.MEN_FRIENDLY_SAMPLE_WINDOW_FROM_UTC` (SAMPLES): mecz dnia w 851 -
  pula próbki goli przyjmuje też mecze 851 stron, a `goals_total` /
  `goals_for` czytają wariant C: wszystkie mecze puli (towarzyskie i o
  stawkę) od najstarszego z 10 najnowszych meczów 851 (minimum 5; mniej albo
  mecz pucharowy - 10 najnowszych z puli) - `men_friendly.pick_friendly_window`.
  Dziś (D, same mecze o stawkę) jest najgorszy: C - D przy priorze as-of
  `goals_total` -0,0071 [-0,0127; -0,0015], `goals_for` -0,0140 [-0,0196;
  -0,0086]; przy priorze globalnym -0,0211 / -0,0252. Połówki goli, inne
  rynki, rating i próbki innych meczów bez zmian; 852 (kobiety: wariant A
  najlepszy) bez zmian.
- `epochs.MEN_FRIENDLY_BASELINE_FROM_UTC` (SHEET): 851 nie ma bazy ligowej
  (wykluczony z każdego fitu), więc środek był ściągany łańcuchem priorów -
  w końcu do globalnej 3,26 gola - a mecze 851 dają średnio 2,54 (2 365 meczów
  do 2026-10-12). Prior `goals_total` meczu 851 to średnia goli (wynik
  regulaminowy) meczów 851 dwóch reprezentacji od 2015-01-01 ściśle przed
  dniem, z indeksu listingów (`sofa_listed_event`, tylko do odczytu, ~20 s,
  tylko w dzień z meczem 851), `goals_for` - połowa; poniżej 30 meczów zwykły
  łańcuch. Notka `PRIOR_MEN_FRIENDLY`. Bez znacznika reguły na wierszu:
  włączony w trakcie dnia - SHEET uruchamia się ręcznie.
- Krzywe historii dopasowano bez tego: w `calibrate_from_cache.py` mecz 851
  nigdy nie wchodzi do historii strony, a jego własne wiersze fit wycina
  (`fit_meta.friendly_exclusion_sql`). Refit niosący te reguły musiałby
  zostawić wiersze 851 w fitcie `goals_total` / `goals_for`, budować ich
  próbkę goli wariantem C (historia stron z meczami 851 - tylko dla celu
  851) i ściągać środek do priora as-of 851 (`men_friendly.baseline_from_events`
  na meczach ściśle wcześniejszych); bez tego krzywe tych rynków opisują mecze
  o stawkę, a mecz 851 czyta je jako przybliżenie.

**Zmierzone 2026-10-13 (audyt B8, B9, B11, A3), sporty mierzone, przełączniki
`None`** (kod za przełącznikiem, bez refitu, nic nie wchodzi do druku):
- `epochs.HK_SHOTS_FROM_UTC`, `epochs.HK_EMPTY_NET_FROM_UTC` (B8, hokej:
  strzały x save% i dopasowana pusta bramka): zamiana centrum na strzały
  `total` +0,00126 [+0,00010; +0,00241] gorzej, mieszanka +0,00025
  [-0,00033; +0,00084]; pusta bramka `handicap` -0,00037 [-0,00074; +0,000006],
  `total` +0,00111 gorzej; strzały są w 6 755 z 29 516 meczów, w październiku
  2026 brak (`docs/sofa/evidence/hockey_goalie_empty_net_2026-10-13.md`,
  `docs/sofa/history/RAPORT_B8_HOKEJ_2026-10-13.md`).
- `epochs.VB_SET_LENGTH_FROM_UTC`, `epochs.VB_SET_HISTORY_FROM_UTC` (B9 / C10,
  siatkówka: tabela długości seta, `score_model.SetLengthTable`): 5 050 meczów
  walk-forward, `points_total` +0,0025 [-0,0005; +0,0054], `points_handicap`
  -0,0011 [-0,0036; +0,0013], `set_extra_points` -0,0004 [-0,0014; +0,0007];
  próg niespełniony; C9 niemierzone (zależy od B9)
  (`docs/sofa/evidence/volleyball_set_length_2026-10-13.md`,
  `docs/sofa/history/RAPORT_B9_C10_C9_2026-10-13.md`).
- `epochs.CS2_MAP_IDENTITY_FROM_UTC` (B11, CS2: kolejność i pula map): 24 995
  map / 11 217 serii, A vs baza +0,00021 [-0,00022; +0,00064] - bez efektu
  (`docs/sofa/evidence/cs2_map_identity_2026-10-13.md`).
- `epochs.BB_OVERTIME_FROM_UTC` (A3, koszykówka: dogrywka w replayu): 1X2
  regulaminu -0,00354 [-0,00719; -0,00015], sumy i zwycięzca bez poprawy; jako
  wariant krzywej +0,00113 [-0,00123; +0,00353]
  (`docs/sofa/evidence/basketball_refit_2026-10-13.md`).
- Refity krzywych na 2026-10-14 (`sport_refit_2026-10-13.md`,
  `basketball_refit_2026-10-13.md`; linie Superbetu 10-05..10-12): koszykówka
  zwykła -0,00042 [-0,00145; +0,00063], hokej +0,00151 [+0,00105; +0,00200]
  gorzej, siatkówka -0,00032 [-0,00175; +0,00120], CS2 -0,00008 [-0,00030;
  +0,00015] - żadna nie zainstalowana. Siatkówka zawyża ~16 pp przy pewności
  >= 0,70 przy obu krzywych (nowa -15,4 pp [-24,4; -6,8]) - jak koszykówka,
  sprawa krzywej / line evidence, otwarta.

**Włączone od 2026-10-14 (koszykówka A7, standing go audytu):**
- `epochs.MARKET_POSITIONED_LINES_FROM_UTC` (2026-10-14 00:00Z): krzywa
  historii koszykówki dopasowana na liniach postawionych tam, gdzie stał rynek
  Sofascore (`data/a7_odds/basketball.jsonl`), p nadal z modelu wyników;
  krzywa w `config/sofa_sport_confidence_calibration.next.json`
  (`effective_from` 2026-10-14; staged CS2 B10 przeniesiony nad plik główny,
  bc69b56e). Log-loss -0,0622 [-0,0702; -0,0546] na 41 414 liniach / 651
  meczach 10-05..10-12. Przy linii rynku p modelu do 0,70 realizuje
  0,47-0,53, więc sumy / handicapy / sumy drużyny (stara krzywa ~0,77,
  realizacja 0,618) trafiają w kubełki n < 200 i przestają drukować (próba na
  sucho: 0 takich nóg). Cache A7 pokrywa ~40% celów (10 662 z 26 332;
  priorytet 1, 15 670 meczów, wymaga mostu)
  (`docs/sofa/evidence/market_positioned_lines_2026-10-13.md`,
  `basketball_refit_2026-10-13.md`).

**Włączone od 2026-10-13 18:10Z razem z refitem piłki / tenisa
(zainstalowanym 18:06Z; krzywe dopasowane na replayu z tymi członami i
ratingiem piłkarskim w centrum, audyt A6; dzień 10-13 mieszany, raport
`docs/sofa/history/RAPORT_REFIT_2026-10-13.md`; od 2026-10-14 05:31Z na
krzywych refitu 2026-10-14, pliki `CONFIG.md` 7.7)**
(pomiary B1 / B2: one step ahead na historii 2025-08-01..2026-10-12, log-loss
NB centrum przy wyniku, nie linie Superbetu):
- `epochs.GAME_STATE_FROM_UTC` (B1): centrum strony `corners_for`,
  `shots_for`, `cards_points_for`, `fouls_for` x exp(beta x oczekiwana różnica
  goli strony z ratingu goli, `FootballForecast.supremacy`); beta w
  `config/sofa_game_state.json` (`scripts/sofa/fit_game_state.py`, dry-run
  domyślnie). Walk-forward: rożne -0,0149 [-0,0160; -0,0138], strzały
  -0,0150 [-0,0164; -0,0137], kartki -0,0043 [-0,0048; -0,0037], faule
  -0,0002 [-0,0004; -0,00003] na stronę; bias faworyta w rożnych -0,63 -> +0,14,
  outsidera +0,57 -> +0,03 (`docs/sofa/evidence/game_state_2026-10-13.md`).
- `epochs.FOOTBALL_RATED_SCOPE_FROM_UTC` (B2): rating (z siłą ligi) wchodzi w
  centrum `football_rating.RATED_SCOPE_MARKETS` (`cards_points_for`,
  `corners_1h_for`, `corners_2h_for`, `offsides_total`); sumy rożnych zostają
  bez ratingu (`corners_total` gorzej: +0,0009 [+0,0003; +0,0015] na mecz).
- `epochs.FOOTBALL_VENUE_PRIOR_FROM_UTC` (B2): centrum z samej próbki
  `corners_1h_for` / `corners_2h_for` x stawka ligi dla dzisiejszego
  gospodarza / średnia stawek miejsc próbki (`FootballForecast.venue_multiplier`;
  próbka nie jest dzielona). `docs/sofa/evidence/unrated_markets_2026-10-13.md`.
- `epochs.FOOTBALL_RATING_WEIGHT_FROM_UTC` (B14): waga ratingu na rynek z
  `config/sofa_rating_weight.json` (`bet.sofa.rating_weight`; rynek spoza
  pliku: `W_FOOTBALL_RATING`; `docs/sofa/evidence/rating_weight_2026-10-13.md`).
- `epochs.SEASON_PHASE_FROM_UTC` (C1): centrum goli x exp(c[rynek][faza])
  z `config/sofa_season_phase.json`, faza sezonu ligi z historii w chwili
  meczu (`docs/sofa/evidence/season_phase_2026-10-13.md`).
- `epochs.TENNIS_SET_RATING_PRICES_FROM_UTC` (B5): gemy setów i `sets_total`
  tenisa z sąsiadów ratingu (`tennis_rating.SET_RATING_PRICED_MARKETS`;
  `docs/sofa/evidence/tennis_set_markets_2026-10-13.md`). Poprawka
  2026-10-14: replay (`calibrate_from_cache.set_values`) bierze bazy setów
  tylko z meczów best-of-three (`metrics.infer_best_of == 3`) - nocny replay
  zapisał 6 688 wierszy `sets_total` 2,5 z meczów best-of-five (Wielkie
  Szlemy, Next Gen Finals), UNDER trafiał ~0. SHEET odmawia `sets_total` na
  meczu, którego format nie jest znanym best-of-three
  (`BEST_OF_FIVE_NOT_MODELLED`, `run_sheet.format_bound_refusal`): krzywa
  jest z best-of-three, a nieznany format sąsiedzi ratingu czytaliby jak
  best-of-three.
- `epochs.TENNIS_ACES_OPPONENT_FROM_UTC` (**wyłączony**, `None`; 2026-10-17):
  centrum asów (mecz, zawodnik, sety) x współczynnik returnującego - asy,
  które serwowali jego rywale (`Observation.against` z jego próbki
  `aces_for`), ściągnięte z K do priora tieru, przez prior
  (`bet.sofa.tennis_aces_opponent`); suma: (c_A f(B) + c_B f(A)) / (c_A + c_B);
  podwójne błędy bez korekty. Wiersz: notatka `TENNIS_ACES_OPPONENT`, znacznik
  `tennis_aces_rule`. Zmierzony i niewłączony: na liniach Superbetu z
  prawdziwym SHEET zero (+0,0060 [-0,0251; +0,0348], 64 mecze), w historii
  łączne gorzej. Krzywe rynków serwisowych (asy z korektą, sety, asy + PB)
  dopasowane, niezainstalowane - na liniach Superbetu zawyżają o 20-30 pp
  (`docs/sofa/evidence/tennis_aces_opponent_2026-10-17.md`, sprawdzian
  `T-TENNIS-SERVE-MARKET-LINE`).
- Bety B1 dopasowano ponownie na żywym centrum (z B2 i wagą B14),
  zainstalowane 2026-10-13 20:57Z (df5323ea): `corners_for` 0,129 -> 0,0986,
  `shots_for` 0,0974 -> 0,0506, `cards_points_for` -0,0845 -> -0,0664,
  `fouls_for` bez zmian (refit +0,000031 gorzej).
- **Refit 2026-10-14** (zainstalowany 05:31Z, `CONFIG.md` 7.7, raport
  `docs/sofa/history/RAPORT_NOC_2026-10-13_14.md`) zastąpił refit z 10-13:
  ten sam replay plus B15, łączniki i zawodnicy ze startów. Od 2026-10-14
  05:45Z `epochs.SAMPLE_OPPONENT_CORRECTION_FROM_UTC` (B15 z A5,
  `bet.sofa.opponent_correction`): próbka strony w piłce przeskalowana do
  neutralnego rywala (`x / def(rywala)`, Maher 1982) i do domeny ligowej
  dzisiejszego meczu przed środkiem SHEET-a (gole i zawodnicy bez korekty);
  wiersz niesie `corrected_sample` i `opponent_rule`, a bramki kształtu i
  `MODEL_ABOVE_OWN_SAMPLE` w CONFIDENCE czytają skorygowane wartości.
  Historia: log-loss po kalibracji lepszy na 12 z 18 rynków rożnych /
  strzałów / fauli z przedziałem poniżej zera, żaden gorszy; w parach
  ponadligowych 3-4 razy więcej. Replay: `calibrate_from_cache.py
  --opponent-correction` (z `--football-rating`). Rebuild uruchamia SHEET
  ponownie, gdy wiersz piłki nie ma `opponent_rule`. SAMPLES zapisuje
  `opponent_id` dopiero od wieczora 2026-10-13 - starsza próbka nie jest
  korygowana, więc B15 działa od SAMPLES dnia 10-14
  (`docs/sofa/evidence/sample_opponent_correction_2026-10-13.md`).
- `K_CENTRE` po reficie: 15 (tenis 8, piłka 15).
- Znaczniki wiersza (od 2026-10-14, poprawka): SHEET stempluje każdy z tych
  sześciu przełączników na wierszach, których dotyczy, gdy jest włączony
  (`epochs.*_MARKER`): piłka - `game_state_rule`, `rated_scope_rule`,
  `venue_prior_rule`, `season_phase_rule`, `rating_weight_rule`; tenis -
  `tennis_set_rule` (tylko na `TENNIS_RATING_PRICES`, jak w SHEET). Wyłączony
  przełącznik: pola nie ma. Przebudowa (`rebuild_plan.audit_sheet_stale`) sama
  puszcza SHEET, gdy przełącznik jest włączony dla dnia i zegara, a wiersz
  piłki (tenisa) nie ma znacznika; arkusz bez piłki (tenisa) nie puszcza SHEET
  w kółko. Dzień < 10-13 i 10-13 przed 18:10Z zostają przy swoim arkuszu.
- Odcisk configu (`config_sha`, `bet.sofa.sheet_config.fingerprint`): skrót
  plików dopasowanych, które czyta SHEET (stałe, bazy lig, reliability, rating
  tenisa, dyspersja, korelacje stron, tabele game state / fazy sezonu / wagi
  ratingu) na każdym wierszu. Inny niż pliki teraz: przebudowa pisze notkę
  `CONFIG_CHANGED`, ale SHEET **nie** puszcza (instalacja nie ma daty, a nigdy
  nie wchodzi w zbudowany dzień bez zgody operatora - wtedy
  `run_pipeline.py --only SHEET` ręcznie). Krzywe historii czyta CONFIDENCE
  przy każdej przebudowie, więc ich refit nie potrzebuje znacznika.

### 7.1b Rating tenisowy (od 2026-10-01)

`config/tennis_rating.json` (`fit_tennis_rating.py --cut <d>`, między dniami):
8 cech plus wyraz wolny, osobno dla ITF / CH / TOUR, w tym `dhigh` i `dtour`
(udział meczów zawodnika powyżej ITF / w tourze) — jedna pula Elo dla
wszystkich poziomów przeszacowywała zawodnika z niższego poziomu o 3–24 pp.
Refit 2026-09-30 po backfillu (cut 2026-10-01, 239 315 meczów): poza próbą
09-17..30 Brier 0,1948 → 0,1884, TOUR 0,2055 → 0,1855. Rynki `games_total`,
`games_won_for`, `sets_total`, `handicap_games`:
`p_central = 0,25·rating + 0,75·market_p` (notka `TENNIS_RATING`: "blended
0.25 with market_p"; w epoce stats-only cena nie wchodzi, a wiersze wyceniane
samym ratingiem - `games_won_for`, `handicap_games`, `most_games` pod
`TENNIS_RATING_PRICES`, rynki setów pod `TENNIS_SET_RATING_PRICES` - mają w
notce "p_central is the rating alone, no price (<przełącznik>)"). Dla TOUR i
CH tabela podobnych meczów pomija mecze rozstrzygnięte super-tie-breakiem
(liczonym jako 1 gem trzeciego seta; 5,1% meczów, prawie wyłącznie ITF).

### 7.1c Pakiety modelowe (zainstalowane 2026-10-08 23:42Z, WŁĄCZONE od 2026-10-09 00:00Z; poza `CARDS_CORRELATION`)

Cztery pakiety zmierzone poza próbą na historii (raporty w
`docs/sofa/evidence/`) są wpięte w kod za przełącznikami w `bet.sofa.epochs`.
Refit z ich flagami zainstalowano 2026-10-08 23:42Z (commity 5330f357 i
fdbe0aae - nowa epoka porównywalności); `COUNT_DISPERSION`, `PER_MARKET_K` i
`TENNIS_SCOPED_TABLE` są **WŁĄCZONE od 2026-10-09 00:00Z** (liczy się dzień
budowany ORAZ zegar budowy; dzień < 10-09 to stary estymator i nie
przebudowuje się go). `CARDS_CORRELATION_FROM_UTC` zostaje `None` (krzywe
jointów kartek nie są czytane, dopóki `DERIVED_CURVES_FROM_UTC` jest `None`) -
czeka na operatora; wiersz nie ma wtedy `cards_rule`. Przebudowa dnia >= 10-09
(`rebuild_plan.py`) sama puszcza SHEET na arkuszu bez znacznika reguły.
Podgląd na danych z 2026-10-07: drukowane nogi 572 -> 634 (piłka 251 -> 269,
tenis 321 -> 365; 47 z 113 nowych to `games_won_for` UNDER), buildery 11 -> 8.
Dowody wyceny (offsety i limity pasm kursu w
`config/sofa_superbet_line_evidence.json`) dopasowano do STARYCH krzywych;
stosuje się je do nowych, dopóki `refresh_line_evidence.py` ich nie przefituje -
pierwsze poranki bywają zaszumione dla przeszacowanych rodzin (`games_won_for`
UNDER prawdopodobnie zaniżone, `goals_total` / `corners_total` możliwe
podwójne liczenie, ostrożnie).

| pakiet | przełącznik | co zmienia | znacznik wiersza | replay |
|---|---|---|---|---|
| dyspersja liczników (ON od 2026-10-09 00:00Z) | `COUNT_DISPERSION_FROM_UTC` | rozrzut piłkarskich liczników z alfy dopasowanej na historii (NB na rozgrywki, `config/sofa_count_dispersion.json`; `shots_total`: normalny z wariancją łączoną) zamiast wariancji z 8-10 meczów; log-loss lepszy na 52/52 rynków (−3,8 gole, −4,1 rożne, −5,7 strzały celne, ×1e-3) | `dispersion_rule` | `--count-dispersion` |
| tabela tenisowa (ON od 2026-10-09 00:00Z) | `TENNIS_SCOPED_TABLE_FROM_UTC` | sąsiedzi ratingu z komórki tier × płeć (tier, potem tabela wspólna, gdy komórka ma < 1200 wyników) i start ratingu `lp_t`; `games_total` −81e-4 [−90; −74] | `tennis_table_rule` | `--tennis-scoped-table`, `fit_tennis_rating.py --tier-start` |
| korelacja kartek (**`None`, czeka na operatora**) | `CARDS_CORRELATION_FROM_UTC` | jointy kartek z korelacją stron +0,126 (dziś: niezależne); `both_over` +0,0016, `handicap` +0,0028, `most` +0,0011 | `cards_rule` | `--cards-correlation` |
| K na rynek (ON od 2026-10-09 00:00Z) | `PER_MARKET_K_FROM_UTC` | `K_CENTRE.by_market.football` (kartki drużyny 25, faule suma 2, strzały drużyny 8, strzały suma 5; gole zostają 15); sumy meczu −6,4e-4 | `k_rule` | `--per-market-k` |

Odrzucone w tym samym przeglądzie (zob. "Zmierzone i odrzucone" w
`CLAUDE.md`): hierarchiczny Empirical Bayes, kopuła t, Dixon-Coles i
bivariate Poisson, ZINB / rodziny empiryczne, kalibracja beta / izotoniczna,
dolny przedział na `p`, hierarchia nawierzchni i model serve/return w tenisie.
Otwarte: korelacja strzałów celnych (pomiar −0,107 vs config −0,003) i rożnych
(docstring −0,279 vs reszta około −0,23); sędzia dla kartek (dane o sędzi są w
856 z 460 tys. meczów - za mało). Przegląd literatury:
`docs/sofa/evidence/LITERATURA_2026-10-08.md`.

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

**W epoce `stats_only` (od 2026-10-05) blokadą jest marża, nie kotwica.**
Noga zawodnika przechodzi CONFIDENCE (krzywa własnego rynku z historii,
line evidence), ale jej drabina nie ma strony „poniżej”, więc `overround`
jest `None`, a `single_is_fairly_priced` (marża ≤ 15%) odrzuca ją jako
singla — bez nazwanego powodu; 10-09..10-10 odpadło tak 5 nóg, które
przeszły wszystkie bramki pewności. Noga ma `one_sided_market: true`. Reguła
dopuszczająca (`confidence.one_sided_single`: krzywa `market:` z ≥ 300
wierszami, x ≥ 0,90 i reszta bramek bez zmian; PDF / HTML pokazują
„1-str.” / „jednostr.” zamiast marży, `audit_variants` C2 sprawdza regułę) stoi
za `epochs.ONE_SIDED_SINGLES_FROM_UTC` — włączone przez operatora od
2026-10-12 00:00Z (pomiar przed: 49 nóg 10-05..10-10, ROI −10,3% [−27; +4]
wobec −3,0% nóg drużynowych — do sprawdzenia na nowych dniach).

**Bramki kształtu próbki u zawodników (od 2026-10-17 00:00Z,
`epochs.PLAYER_SAMPLE_GATES_FROM_UTC`, operator 2026-10-16).** Próbka
zawodnika to jego starty w 10 ostatnich meczach drużyny (5-10 wartości), więc
`THIN_SAMPLE_FOR_BUILDER` (< 10) przepuszczał tylko zawodnika z 10/10
startów, a `LINE_BEYOND_SAMPLE` odrzucał OVER 0,5 zawodnikowi, który w każdym
starcie miał ≥ 1 (10-15: z 57 nóg zawodników po krzywej, line evidence i x
przy cenie arkusza bramki te odcięły 54 - 45 na sześciu rynkach poniżej;
wydrukowało się 5, w tym 2, które przeszły x dopiero po świeżej cenie). Krzywe rynków z `/lineups` są
dopasowane na replayu z próbką od 5 startów i bez bramek kształtu. Od
przełącznika wiersz zawodnika na rynku z `/lineups` (strzały, celne, faule,
odbiory, asysty, spalone - `confidence.PLAYER_SHAPE_GATE_MARKETS`; **nie**
strzały wg nogi / głowy / spoza pola z `/shotmap`, liczone osobnym
estymatorem, ani przechwyty - bez krzywej; niezmierzone) potrzebuje tylko `PLAYER_MIN_SAMPLE` (5)
wartości; wiek próbki, krzywa, line evidence, próg 0,70 i x ≥ 0,90 bez
zmian. Noga, którą bramka by odcięła, ma `player_sample_rule` = nazwa pierwszej
takiej bramki w kolejności CONFIDENCE i **nie wchodzi do Bet Buildera** (pomiar dotyczył singli). Pomiar:
na historii (OVER, pewność ≥ 0,70) grupy odcinane realizują się na swojej
krzywej (+0,5..+1,5 pp), razem ~0,4 pp słabiej niż przepuszczane
(`LINE_BEYOND_SAMPLE` −0,9 [−1,8; +0,1], 5 startów −1,9 pp [−2,9; −0,8]
względem PASS) - bramki lekko wybierają, nie chronią
wydrukowanej pewności; na liniach Superbetu 10-12..10-15 z line evidence:
55 nóg / 37 meczów, −5,9 pp [−15,9; +4,5] pod pewnością, ROI −11,7%
[−23,8; +1,2] (krzywa in-sample) - przy cenie, bez zmierzonej przewagi.
Offset zawodników liczony tylko na liniach x ≥ 0,90 zmierzony i odrzucony.
E2E na 10-15 (czysta kopia, zegar 12:59Z - mecze już rozpoczęte odpadają;
raport `docs/sofa/history/RAPORT_BRAMKI_ZAWODNIKOW_2026-10-16.md`): +40 singli zawodników (22 z
`LINE_BEYOND_SAMPLE`, 18 z `THIN_SAMPLE_FOR_BUILDER`), 0 nóg straconych ani
zmienionych, buildery identyczne.
Dowody: `docs/sofa/evidence/player_sample_gates_2026-10-16.md`,
`docs/sofa/evidence/player_line_evidence_2026-10-16.md`; test na nowych
danych `T-PLAYER-SAMPLE-GATES`.

**Nazwiska (od 2026-10-12 00:00Z, `epochs.PLAYER_NAME_TOKENS_FROM_UTC`).**
Superbet pisze wielu zawodników pełnym nazwiskiem rejestrowym („Andrade,
Matheus Araujo”), Sofascore boiskowym („Matheus Araujo”); `token_sort_ratio`
daje 60–84, poniżej progu 85 `match_player`, i zawodnik nie miał próbki
(346 z 680 `NO_ENTITY_FOUND` 10-08..10-10). Zawodnik, którego `match_player`
nie znalazł w **żadnym** składzie, jest szukany po całych tokenach
(`players.match_player_by_tokens`: ≥ 2 wspólne tokeny, jeden kandydat w
składzie, wszystkie składy wskazują tę samą osobę po tej samej stronie).
Próbka ma `match_rule: "tokens"`, wiersz arkusza notkę `PLAYER_NAME_TOKENS`,
a SETTLE ocenia dokładnie `matched_name` próbki we własnym składzie. Zawodnik
z ławki, który nigdy nie wszedł, ma lukę „named in N squads, never came on”.
Dowody: `docs/sofa/evidence/player_name_tokens_2026-10-11.md`.

**Start w składzie (operator, 2026-10-11).** Superbet zwraca zakład na
zawodnika, który nie wyszedł w podstawowym składzie (Walemark 10-10: z ławki
na 30', 2 celne, „Zwrot”). SETTLE: `PLAYER_NOT_STARTED` (bez wiersza);
nogi `PLAYER_DID_NOT_PLAY` / `PLAYER_NOT_STARTED` są listowane per noga w
`07_settle_skips.json` `void_legs`, a wydrukowana taka noga to w 7c i w
ledgerze zwrot (0 j.). Od 2026-10-12 00:00Z (`PLAYER_STARTS_ONLY_FROM_UTC`)
próbka to jego starty (`appearances: "starts"`, notka `PLAYER_STARTS_ONLY`),
a krzywe zawodników są dopasowane na startach - od refitu 2026-10-14 w
głównym `config/sofa_confidence_calibration.json` (replay z
`--player-starts-only`); `.next.json`, który niósł je od 2026-10-12, usunięto
przy instalacji (kopia w `config/backup_2026-10-15`). Dowody:
`docs/sofa/evidence/player_starts_2026-10-11.md`.

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
[--runs-dir runs/sofa] [--calibration <plik>]` →
**`08_confidence.json`**, **`08_confidence.md`**. Próg
`BELOW_CONFIDENCE_FLOOR` to **0,70** (`confidence.COUPON_PROFILE`).

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
| `DERIVED_NOT_CALIBRATABLE` | rynek pochodny (`both_over_`, `handicap_`, `most_`) — ma 2–252 rozliczonych wierszy i żadna próbka z artefaktów go nie sprawdzi — **do 2026-10-07**; od `epochs.LINE_EVIDENCE_FROM_UTC` (2026-10-08) rynek pochodny czyta wyłącznie własne rozliczone linie Superbetu (`NO_LINE_EVIDENCE`, dopóki ich nie ma) |
| `NO_LINE_EVIDENCE` | od 2026-10-07 10:55Z: rynek bez krzywej przy tym `p` i bez >= 50 własnych rozliczonych linii Superbetu w kubełku (`bet.sofa.line_evidence`) — niezmierzony, nie zgadywany. To samo w SPORT_CONFIDENCE. Klucz bez krzywej czyta dolną granicę Wilsona swoich linii podzielonych przez efekt projektu; od `epochs.BUCKET_DESIGN_EFFECT_FROM_UTC` (2026-10-14 00:00Z, audyt A4) jest to efekt projektu **kubełka** (`deff` zapisywany przez fit dla każdego kubełka; 1, gdy każdy mecz daje jedną linię), nie całego sportu (piłka 2,437). Walk-forward 10-07..10-12: log-loss -0,0351 [-0,0409; -0,0292] (`docs/sofa/evidence/bucket_design_effect_2026-10-13.md`) |
| `NO_CLASS_CURVE` | noga klasy (`women`, `tennis_women`, `tennis_team_cup`), którą krzywe bez klasy by obsłużyły, ale klasa nie ma własnego kubełka |
| `NOT_CALIBRATED` | dla tego kubełka **nie ma pomiaru**; własna liczba modelu nie jest jego substytutem. Od 2026-09-30 także noga **klasy**, której nie obsłużyłaby żadna krzywa (inaczej `NO_CLASS_CURVE`): piłka kobiet (`women`, rozpoznawana po „(K)" Superbetu albo nazwie rozgrywek), tenis kobiet (`tennis_women`), Davis Cup / BJK Cup / pokazówki (`tennis_team_cup`). Noga klasy czyta wyłącznie krzywe swojej klasy (`by_class` w `config/sofa_confidence_calibration.json`, `fit_confidence.py --classes-only`) — nigdy puli, od której klasa się różni (piłka kobiet przy p 0,80–0,85: 0,792 wobec 0,806 mężczyzn; rożne przy 0,90: 0,874 wobec 0,903) |
| `BELOW_CONFIDENCE_FLOOR` | `realised_lo < --floor` |
| `DISAGREES_WITH_PRICE` | `realised_lo − 1/odds > MAX_DISAGREEMENT = 0.10` — **wyłączona w epoce `stats_only`** |
| `FIXTURE_NOT_AS_SCHEDULED` | `fixture_status.json` (FIXTURE_CHECK): mecz drukowany przełożony, odwołany albo przerwany |
| `NEGATIVE_LEG_EV` | noga nie przebija własnej ceny (`profile.clears_price`); od 2026-10-05: pewność × kurs < 0,90, w epoce `stats_only` na świeżym kursie |
| `LINE_BEYOND_SAMPLE` | linia leży poza wszystkim, co próbka widziała |
| `MODE_LOSES` | wartość modalna próbki przegrywa zakład |
| `THIN_SAMPLE_FOR_BUILDER` | mniej niż `MIN_BUILDER_SAMPLE = 10` obserwacji; wiersz zawodnika z rynku `/lineups` od 2026-10-17 (`PLAYER_SAMPLE_GATES_FROM_UTC`): mniej niż `PLAYER_MIN_SAMPLE = 5`, bez `LINE_BEYOND_SAMPLE` / `MODE_LOSES` (noga ma `player_sample_rule`) |
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

**Historia sportów (od 2026-10-12, `refresh_sport_history.py`, `bet.sofa.sport_history`).**
Model wyniku SPORT_CONFIDENCE i fity sportów czytają historię z listingów
drużyn i indeksu meczów (`score_model.load_events`). Piłka i tenis mają ją
świeżą dzięki SAMPLES; sporty mierzone nie mają SAMPLES, a SPORT_IDENTITY
pyta o listingi **przed** meczem - wynik meczu nie trafiał do historii (10-07..10-11:
0-30% rozliczonych meczów; historia stanęła na 10-04). Skrypt (most) pyta
`/event/{id}` raz o każdy mecz z ostatnich 14 dni, który powinien się już
skończyć, a nie jest w historii jako zakończony (kandydaci: strony `next` /
`last`, indeks, przypięte id z `sport_fixtures.json`), i zapisuje go w indeksie
jako mecz obu drużyn. Uruchamia go `refresh_line_evidence.py` (krok 0) co rano;
`day_status.py` - `sport_history` WARN poniżej 80% przypiętych meczów D-1.
Pomiar 2026-10-12 (`measure_sport_history_ab.py`, linie 10-05..10-11): log-loss
modelu bez mierzalnej zmiany (tydzień to ~500 meczów na tle 29-51 tys.);
zysk to pokrycie dowodu z linii (siatkówka 5 318 -> 8 474 rozliczonych linii).

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
`DUPLICATE_*` …). CS2: `cs2.pick_event` (obie nazwy powyżej progu;
rozpoznane id strony, które się nie zgadza, odmawia — `RESOLVED_ID_DISAGREES`),
a gdy nie znajdzie serii — reguła zakotwiczona
`CS2_LISTING_ID_AND_OPPONENT` (od 2026-10-12 wieczorem): jedna strona po
swoim rozpoznanym id, to jedyna seria tej drużyny w ±1 h od startu Superbetu,
druga strona po własnym id albo regułą przeciwnika z rozliczenia
(`shadow_opponent_agrees`) przy tych samych znacznikach składu (academy, ex-,
kobiety). Zmierzone na 10-06..10-12 (replay z cache): +6 serii (Overtake =
Overtake Sector ×3, Apogee = Betclic Apogee, TheONE 1337 = 1337, LL Honved =
Honvéd), każda sprawdzona ręcznie; 0 błędnych id (09-28..10-12, złoty zbiór
CS2 i `tests/sofa/golden/cs2_identity_anchored_2026-10-12.json`). Siatkówka
(od 2026-10-12 wieczorem): drużyna do zapytania (`query_id`) i strona meczu
bez id porównywane także bez słów klubowych (`VOLLEYBALL_CLUB_AFFIXES`: volei,
voleibol, clube, instituto, ec, esporte) — „Capixaba Volei (K)” =
„Instituto Capixaba Voleibol Clube”; nazwa pasująca do dwóch drużyn nadal
odmawia („Londrina (K)”). Replay 10-06..10-12: +5 meczów Superliga C kobiet,
4 z id równym rozliczeniu, 1 sprawdzony ręcznie; 0 błędnych id
(09-28..10-12, złoty zbiór siatkówki). Rekord `IDENTIFIED` jest przypięty i nigdy nie pytany
ponownie; po tym id rozlicza SETTLE. Mecz nierozpoznany, którego start
Superbetu już minął, zachowuje swój ostatni rekord (sprzed startu,
`frozen_at_start: true`) i nie jest pytany ponownie: `events/next` nie
pokazuje meczu w trakcie, a ponowne pytanie nadpisywało powód sprzed startu
`NO_GAME_WITHIN_1H` (10-06..10-12: 3..56 takich rekordów dziennie; od
2026-10-12 wieczorem). Kod 0 / 1 (mecz nierozpoznany albo
odmowa mostu) / 2 (brak migawki żadnego sportu). Z `--if-snapshot` brak
migawki to `NOTHING_TO_DO`, kod 0, bez zapisu pliku — tak pętle
`shadow_daily` / `cs2_daily` pytają o D+1 (od 2026-10-12; wcześniej co pół
godziny logowały FAILED). Blok `sports` w pliku podmienia liczniki tylko
sportów, o które pytano (wcześniej pętla CS2 zerowała hokej i odwrotnie).

**Mapa encji (plan tożsamości K1, od 2026-10-14; odczyt od
`epochs.ENTITY_MAP_FROM_UTC` 2026-10-14 11:30Z, `bet.sofa.entity_map`).** Po
zapisaniu pliku SPORT_IDENTITY uczy `sofa_entity` (osobne połączenie do
zapisu; błąd zapisu nie psuje etapu — `ENTITY_MAP_LEARN_FAILED`, licznik
`entity_map` w `SOFA_SUMMARY`), raz na mecz Sofascore (`sofa_entity_taught`):

- strona potwierdzona **własną nazwą** (metoda `LISTING_NAMES`,
  `LISTING_ID_AND_NAME`, `CS2_PICK_EVENT`, wynik nazwy > 82) → wiersz
  `verified` ze `source = identity_names` i `evidence_event_id`;
- strona potwierdzona tylko **regułą przeciwnika** (`*_ID_AND_OPPONENT`,
  wspólne słowo) → kandydat w `sofa_entity_candidate` (kolejka NEEDS_ALIAS,
  K4), nigdy tożsamość — ta sama zasada co `remember()` w RESOLVE;
- nazwa trzymana z **innym id** → `sofa_entity_conflict`, nigdy nadpisanie
  (od przełącznika także w `cache.save_entity`, czyli RESOLVE i
  SHADOW_SETTLE; wcześniej stare nadpisanie zostaje, konflikt i tak jest
  zapisywany);
- turniej Superbetu → `competition_id` Sofascore w `sofa_tournament_map` (z
  licznikiem; piłka / tenis z RESOLVE pod kluczem `id:<id turnieju
  Superbetu>`); na razie nikt go nie czyta (K2).

Wiersze `identity_names` (i przyszłe `manual`) czytają `TeamResolver`
(SPORT_IDENTITY), `player_model.resolve_team` (wiersze przed meczem
zawodników; wiersz po nazwie niesie `entity_map_rule`) i `cache.get_entity`
dopiero od przełącznika — dzień >= 2026-10-14 i zegar po 11:30Z (operator przesunął wszystkie przełączniki planu tożsamości z 2026-10-15 00:00Z na 2026-10-14 11:30Z; 10-14 jest dniem mieszanym, grupa księgi „10-14 mieszany”). CS2 czyta
tylko wiersze nauczone (po dokładnej nazwie z `cs2_series`, przed jej formą
bez afiksów); własne wiersze `backfill_cs2.py` nadal nie są czytane — jeden
z nich trzyma „Ninjas in Pyjamas” jako NIP Impact (448738), wbrew każdemu
przypiętemu meczowi NIP (366560): jest w kolejce konfliktów. Jednorazowe
uzupełnienie z dni na dysku: `scripts/sofa/backfill_entity_map.py
[--dry-run]` (2026-10-14 09:39Z: 477 nowych nazw, 485 już rozpoznawanych
indeksem — to samo id; 0 sprzeczności; 2 konflikty CS2; 71 kandydatów; 1 470
wierszy turniejów; kopia `sofa_entity` w
`data/backup_entity_map_20261014T093901Z/`). Raport:
`docs/sofa/history/RAPORT_K1_MAPA_ENCJI_2026-10-14.md`.

**Decyzje ręczne (plan tożsamości K4).** `config/sofa_entity_aliases.json`
(`aliases` — nazwa Superbetu to ta drużyna; `rejected` — to nie ten kandydat)
stosuje każdy przebieg SPORT_IDENTITY (`entity_map.sync_manual`, od
przełącznika): alias trzymany ze `source = manual` zastępuje trzymane id i
zamyka konflikty / kandydatów tej nazwy. Kolejka do decyzji:
`scripts/sofa/report_entity_queue.py --date <d>` →
`runs/sofa/<d>/entity_queue.md` (konflikty, kandydaci, gotowe wpisy JSON).
Fuzzy nigdy nie wpisuje decyzji.

**DAY_ANCHOR (plan tożsamości K2, od `epochs.DAY_ANCHOR_FROM_UTC` 2026-10-14
11:30Z; hokej, kosz, siatka — nie CS2).** Gdy w listingu nie ma meczu z obiema
nazwami: jedyny mecz drużyny-kotwicy (strona z rozpoznanym id) w ±1 h od
startu Superbetu (sport, płeć, nie przełożony) jest tym zdarzeniem bez względu
na nazwę drugiej strony (`match_method: "DAY_ANCHOR"`). Dwa takie mecze →
`AMBIGUOUS`; własne id drugiej strony, którego w meczu nie ma →
`RESOLVED_ID_DISAGREES`. Nazwa przeciwnika trafia tylko do kolejki kandydatów.
Backtest z ukrytą nazwą przeciwnika (`measure_day_anchor.py`, 10-05..10-14):
1 578 / 1 578 zidentyfikowanych meczów trafionych, 0 sprzeczności z SETTLE.
Raport: `docs/sofa/history/RAPORT_K2_DAY_ANCHOR_2026-10-14.md`.

**TOURNAMENT_DAY i NOT_ON_SOFASCORE (plan tożsamości K3 / K5, od 2026-10-14
11:30Z).** Piłka w RESOLVE (K8, `FOOTBALL_DAY_ANCHOR_FROM_UTC`, ten sam moment): jedyny mecz drużyny z mapy „verified” w ±1 h od startu Superbetu, w kolejności stron Superbetu, płeć tablicy, nie przełożony, własne id przeciwnika (jeśli jest) w meczu — `resolve.football_day_anchor_event` (3 458 / 3 459 na 10-05..10-14). Zdarzenie, którego **żadna** strona nie ma id, jest dopasowywane po
obu nazwach w meczach swojego turnieju z dnia (`bet.sofa.day_listing`,
`unique-tournament/<ut>/scheduled-events/<d>` przez mapę turniejów, cache
`sofa_day_listing`; słabsza strona ≥ 60, przewaga ≥ 20; `match_method:
"TOURNAMENT_DAY"`). `NO_GAME_WITHIN_1H` z cache strony drużyny (6 h) w
ostatnich 3 h przed startem jest pytany raz świeżo; brak udowodniony
(`reason: "NOT_ON_SOFASCORE"`, `absence_evidence`) tylko na świeżej stronie
drużyny rozpoznanej po id bez żadnego jej meczu w ±12 h. Raport:
`docs/sofa/history/RAPORT_K3_K7_TOZSAMOSC_2026-10-14.md`.

**SPORT_CONFIDENCE** — `scripts/sofa/run_sport_confidence.py --date <d>`,
bez mostu. Czyta `sport_fixtures.json`, migawki SHADOW / CS2,
`config/sofa_sport_confidence_calibration.json` (`fit_sport_confidence.py`,
na kopii bazy, instalacja za zgodą operatora) i bazę (tylko odczyt); pisze
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
starsza niż `sport_day.MAX_PRICE_AGE` = 3 h), `MARKET_NOT_ALLOWED` (lista
`sport_confidence.ALLOWED_MARKETS` / `CS2_FAMILIES`), `NOT_CALIBRATED`,
`BELOW_FLOOR` (0,70), `BELOW_MIN_X` (x < 0,90), `ODDS_TOO_LOW` (kurs <
1/0,9202), `MARGIN_TOO_HIGH` (marża grupy > 15%), `INCOMPLETE_GROUP`,
`NO_MODEL_P`, `TOURNAMENT_NEVER_SETTLED` (siatkówka: turniej bez meczu SETTLED
w ostatnich 14 dniach), `NO_LINE_EVIDENCE`, a od
`epochs.LEAGUE_RATE_RULE_FROM_UTC` (2026-10-14 00:00Z, audyt A2, decyzja
operatora O1) w hokeju, koszykówce i siatkówce także `FRIENDLY_FIXTURE`
(sparing / przedsezon wg `comparability.is_friendly_event` - ta sama reguła co
w piłce; „NBA Preseason”, „CBA Preseason”, „Club Friendlies”) i
`NO_LEAGUE_RATE` (rozgrywki z < 30 meczami w historii: brak własnej stawki,
więc brak p modelu - nigdy średnia wszystkich lig, która przedsezon NBA
wyceniała na 82,8 pkt na stronę; bez fallbacku do ligi macierzystej). Replay
line evidence (`settled_shadow_rows`) stosuje regułę swojego dnia. Od `epochs.LINE_EVIDENCE_FROM_UTC`
(2026-10-08) czytany jest każdy dopasowany klucz, nie tylko `admitted`:
pewność = krzywa, obniżona o istotne zawyżenie na rozliczonych liniach
Superbetu klucza i o limit pasma kursu (`bet.sofa.line_evidence`); noga
niesie wtedy `line_offset` / `price_band_cap`. W tej samej epoce lista rynków
rozszerza się o `sport_confidence.EXTENDED_MARKETS`: koszykówka — kwarty,
2. połowa, dnb, parzyste/nieparzyste; hokej — dnb tercji. Do tego dochodzą
linie zawodników hokeja i koszykówki: `p` to przedmeczowa liczba
`player_model` z `player_model.jsonl` SHADOW, bez krzywej z historii, więc
czytają tylko własne rozliczone linie. Skład drużyny w przeszłym meczu
(próbka zawodnika i pula pozycji): od `epochs.PLAYER_TEAM_FROM_SIDE_FROM_UTC`
(2026-10-14 00:00Z, dzień meczu - dzień SHADOW, data startu w UTC - i zegar
liczenia) to strona (home / away), po której drużyna grała w tym meczu
(`player_model.appearances_from_lineups(..., side)`, `event_side` z
`sofa_listed_event`; mecz, którego ładunek nie nazywa drużyny po żadnej
stronie, odpada). Wcześniej skład czytany był z `teamId` wpisu w
`lineups_json` - a to drużyna zawodnika w chwili pobrania pudełka, nie w tym
meczu: mecz starej drużyny zawodnika po transferze **przeciw** nowej trafiał
do próbki nowej (Carlson `model_n` 5 przy 85 występach, McTavish 6 przy 88,
2026-10-13; `docs/sofa/evidence/sport_player_props_2026-10-13.md`). Błąd
mapowania, ale zmienia `p` modelu zawodnika, więc za przełącznikiem:
dotyczy przedmeczowej liczby SHADOW (`player_model.jsonl`), liczby z
SHADOW_SETTLE (`model_source: settle`) i `measure_player_props.py`; fit
(`fit_player_model.py`) odtwarza ją z `--player-team-from-side`. Wiersze
niosą `player_team_rule`; wyłączony = bajt w bajt jak przedtem. Line
evidence czyta `p` zapisane przed meczem, więc stosuje regułę swojego dnia
z konstrukcji. 2. połowa i 4. kwarta koszykówki: dogrywka
się nie liczy (operator, 2026-10-07) - rozliczane są z regulaminowych
kwart, także w meczu z dogrywką. Krecz (`RETIRED`) to zwrot. Kod 1,
gdy sport jest `NOT_CALIBRATED` albo brak `sport_fixtures.json` — artefakt i
tak powstaje, kupon piłki i tenisa buduje się dalej.

**Rynki pochodne sportów mierzonych za przełącznikiem
`epochs.SPORT_DERIVED_MARKETS_FROM_UTC`** (**włączony od 2026-10-14
14:50Z**, operator „1. 2. tak”, 10-14 mieszany; znacznik `sport_derived_v1`). Rynki, na które model wyniku już odpowiada, bez
nowego źródła danych (`shadow.DERIVED_MARKETS`): hokej - „Podwójna szansa”
606 i „N. tercja - podwójna szansa” 616 (czytane po id, sprawdzone na
ładunkach Superbetu z 2026-10-13: 1X / X2 / 12, kody 10 / 02 / 12, obok „Mecz”
640 z remisem - więc czas regulaminowy, rozliczane dokładnie jak
`result_1x2` / `period_1x2`); koszykówka - „Podwójna szansa”, „N. połowa -
podwójna szansa”, „N. kwarta - podwójna szansa” (regulaminowo, jak 777 / 763
/ 233400 / 779; nazwa z „dogrywką” odrzucona - tam nie ma remisu); siatkówka -
„<drużyna> wygra seta”, „<drużyna> wygra dokładnie N set(y)” (Tak / Nie) i
„Dokładna liczba setów” (3 / 4 / 5) z symulowanego wyniku w setach, jak
`exact_sets` 785. Koszykówka i siatkówka czytane **po nazwie** pod
syntetycznym id < 0 (ładunku tych rynków nie było pod ręką): nazwa albo
wynik, który nie pasuje, odpada - nic nie jest zgadywane. Podwójna szansa ma
nakładające się wyniki: devig proporcjonalnie do sumy 2
(`cs2.group_fair` „double”), marża grupy = połowa nadwyżki
(`cs2.group_overround`), czyli tyle, ile pokazałby szczebel 1X przeciw 2.
SHADOW zapisuje je w migawce (rekord z `derived_rule`), SHADOW_SETTLE
rozlicza, SPORT_CONFIDENCE wycenia z symulacji modelu wyniku. Od 2026-10-15
00:17Z krzywe z historii są zainstalowane dla hokejowych `double_chance` /
`period_double_chance` TEAM, koszykarskiego `double_chance` TEAM i
siatkarskich `team_sets_exact` NO / `team_wins_set` YES (jednostronna bramka
holdoutu, „Krzywe nowych rynków” w sekcji OFFER); każdy klucz „12”, połowy i
kwarty koszykówki oraz `sets_count` siatkówki krzywej nie mają i czytają tylko
własne rozliczone linie Superbetu klucza: do czasu >= 50 linii / 15 meczów w
kubełku `NO_LINE_EVIDENCE`. Wyłączony: migawki, SHADOW_SETTLE
i SPORT_CONFIDENCE bajt w bajt jak przedtem. Pomiar poza próbą na historii
(`scripts/sofa/measure_sport_derived.py`):
`docs/sofa/evidence/sport_derived_2026-10-14.md`.

**Koszykarska podwójna szansa jako para z 1X2
(`epochs.BASKETBALL_DC_PAIR_FROM_UTC`, od 2026-10-16 00:00Z; znacznik
`dc_pair_rule` = `basketball_dc_pair_v1`).** Superbet wystawia koszykarską
„Podwójną szansę” (i „N. połowa - podwójna szansa”) tylko jako 1X / X2, bez
12 - sprawdzone na żywo 2026-10-15 (5 z 30 meczów). Grupa podwójnej szansy
jest przyjmowana tylko w całości (`cs2.DOUBLE_CHANCE_SET`), więc do 10-16
ten rynek nie był czytany wcale (0 linii w 433 migawkach 10-14 / 10-15),
choć przełącznik był włączony, a krzywa zainstalowana. Od 10-16 niepełna
grupa koszykówki jest czytana jako pary dwustronne: każdy wybór przeciw
wynikowi regulaminowego 1X2 tego samego zakresu (mecz 777, połowy 763 /
233400, kwarta 779), który on wyklucza - 1X przeciw „2”, X2 przeciw „1”, 12
przeciw „X”. Te dwa wyniki dzielą wszystkie rozstrzygnięcia, więc p bez
marży i marża (`1/a + 1/b - 1`, reguła 15%) są dokładne. Para ma
syntetyczne id `dc_id x 100 - 1/2/3`, tę samą rodzinę i zakres co podwójna
szansa (czyta krzywą `basketball:double_chance|TEAM`, rozlicza się
regulaminowo); wynik 1X2 w parze to tylko cena (`partner_odds`), nigdy noga
ani rozliczony wiersz. Hokej, siatkówka i pełna grupa bez zmian; wyłączony -
migawki bajt w bajt (`tests/sofa/test_basketball_dc_pair.py`). Odczyt
analityka może nazwać stronę 1X / X2 / 12 (`contracts.READ_SIDES`, od
2026-10-15).

## 10b. COUPON_ASSEMBLY — `11_coupon.json`, jedyny artefakt kuponu

`scripts/sofa/build_coupon.py --date <d>` (albo `run_pipeline.py --only
COUPON_ASSEMBLY`), offline. Wejście: `08_confidence.json` (profil kuponu `COUPON_PROFILE`,
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
  (`confidence.legs_requiring_read`: pierwsze `READ_REQUIRED_SINGLES` = 30 (od 2026-10-09 00:00Z jednostką jest mecz: wszystkie niezablokowane nogi 30 pierwszych meczów kuponu, `READ_REQUIRED_EVENTS`, `read_unit: "event"` w artefakcie; od 2026-10-14 00:00Z, `READ_BY_VALUE_FROM_UTC`, 30 meczów o najwyższej wartości: pewność x kurs najlepszej niezablokowanej nogi meczu, pewność nogi piłkarskiej / tenisowej liczona najwyżej 1/kurs + 0,03, `confidence.read_value`, `read_order: "value"`; operator 2026-10-13)
  pozycji niezablokowanych, każda noga wydrukowanego buildera, prośby z
  `read_requests.json`). Prośba, która nic nie objęła, drukuje
  `UNMATCHED_READ_REQUEST`.
- **Struktura kuponu (od 2026-10-05, plan production grade F4.1-F4.4;
  adnotacja, niczego nie wybiera):**
  - `relations` — dla każdego meczu z ≥ 2 nogami każda para nóg z etykietą
    (`bet.sofa.leg_relations`): `SAME_VARIABLE_IMPLIES` (U2.5 ⇒ U3.5, pole
    `implies`), `SAME_VARIABLE_EXCLUSIVE` (O2.5 / U2.5, `complement`),
    `SAME_VARIABLE_OVERLAP` (O1.5 i U3.5), `DEPENDENT` (total vs drużyna,
    połowa vs mecz, rożne vs strzały, kartki vs faule, gemy vs sety, pochodne
    vs składniki, mapa vs seria) albo `INDEPENDENT_ASSUMED` (brak znanego
    związku — założenie, nie pomiar). Wielkość nogi jest wyprowadzana z mapy
    rynków (`metrics`, `players`, `derived`, `shadow.MARKETS`, `cs2.FAMILIES`),
    z okresem i stroną.
  - `ladders` — nogi jednego meczu będące tą samą zmienną (drabina szczebli,
    para OVER + UNDER): `ladder_no`, `label`, `rungs`, `over_under_pair`;
    singiel na drabinie niesie `ladder_no`. 10-05 (replay): 39 drabin wśród
    pozycji (98 nóg ze 157), 20 par OVER + UNDER; z nogami w grze 53 drabiny.
  - `exposure` — per mecz: pozycje, udział, suma pewności, nogi w grze,
    buildery, `worst_case_lost` (ile pozycji zabiera mecz, gdy wszystko na nim
    przegra); `top_positions_matches` — na ilu meczach stoją pozycje 1-30
    (10-05: 4).
  - `peer` na nodze i `peer_choice` w dokumencie (od
    `epochs.PEER_CHOICE_FROM_UTC` = 2026-10-08 08:10Z, decyzja operatora: „jak
    masz dwie nogi po 1.2 to zaproponuj tę z większą pewnością"; 10-08 to dzień
    mieszany) — **która z nóg jednego meczu o kursie w pasie ±`PEER_BAND` 0,06
    (różne zmienne; ta sama zmienna na dwóch szczeblach to drabina) jest
    pewniejsza** (`bet.sofa.peer_choice`). Pole `peer`: `preferred`, `peers`,
    `best` (najpewniejsza z sąsiadów albo ona sama), `d_confidence`,
    `band`. Na PDF ★ przy najpewniejszej, a słabsza nazywa pewniejszą i różnicę.
    **Adnotacja: żadna noga nie jest dodana, zdjęta ani przestawiona, żadna
    pewność się nie rusza.** Miara to sama pewność, bo żadna inna nie wygrała
    pomiaru (`docs/sofa/evidence/peer_choice_2026-10-08.md`): na 57 791
    rozstrzygniętych parach piłka / tenis (20 dni) pewniejsza noga wygrywa
    53,4% [52,2; 54,7]; rozmiar próbki, własny odsetek trafień, bliskie
    pudła, margines w sd, trafienia u siebie / na wyjeździe, ostatnie 5 meczów,
    popularność turnieju (Sofascore `userCount`) i flagi rezerwy / kobiet /
    pucharu / reprezentacji nie poprawiają jej poza próbą (leave-one-day-out);
    w hokeju, koszykówce i siatkówce różnicy nie da się zmierzyć (2 894 pary,
    49,7% [45,9; 53,6]). Pre-rejestrowany test na nowych danych:
    `T-PEER-CHOICE-edge`.
  - `stakes` na nodze piłkarskiej (`bet.sofa.stakes`, ta sama epoka): mecz
    o utrzymanie (`STAKES_SIX_POINTER`, oba kluby w odległości ≤ 3 pkt od
    linii spadkowej) albo o czołówkę (`STAKES_TOP4`, od linii 4./5. miejsca),
    po ≥ 55% sezonu w lidze ≥ 12 klubów; tabela z `data/cache/football_history.pkl`
    (to, co SHEET sparsował) na chwilę meczu. `effect` = `za` / `przeciw` nodze
    wg zmierzonego kierunku: mecz o utrzymanie ma średnio +0,20 kartki, +0,86
    faulu, -0,15 gola, -0,96 strzału (0,08-0,16 sd; rożne -0,17 [-0,36; +0,04]
    - nie do odróżnienia od zera), mecz o czołówkę +0,22 kartki i -0,19 gola. **Kontekst,
    nie korekta i nie bramka** (jak `MAKEUP_FIXTURE`); nie skorygowane o to, że
    kluby strefy spadkowej są słabe. Brak pliku historii = kupon bez flag,
    nigdy odmowa.
  - `price_gap` na nodze piłkarskiej i tenisowej oraz `price_gap` w dokumencie
    (od `epochs.PRICE_GAP_FLAG_FROM_UTC` = 2026-10-12 11:51Z, decyzja
    operatora 2026-10-12 po kuponach z 10-11, przesunięta przez niego na
    przebudowę kuponu 10-12 - dzień mieszany; `bet.sofa.price_gap`): noga,
    której pewność przewyższa 1/kurs o więcej niż `GAP` 0,03, dostaje flagę
    `CONFIDENCE_ABOVE_PRICE` z `over_price` i zmierzonym zawyżeniem tej grupy.
    Na PDF, HTML i w `.md`: „pewność +0,05 ponad cenę - takie nogi trafiały
    ~7 pp poniżej pewności, około ceny (piłka, 458 nóg 10-09..10-11)". Pomiar
    (`docs/sofa/evidence/price_gap_2026-10-12.md`,
    `scripts/sofa/measure_price_gap.py`): wydrukowane nogi 10-09..10-11 z
    pewnością > 1/kurs + 0,03 trafiały poniżej pewności - piłka 458 nóg /
    269 meczów, -6,8 pp [-12,0; -2,1], tenis 52 / 35, -18,6 pp [-31,0; -5,9] -
    a reszta była skalibrowana (piłka +0,3 pp); ten sam znak każdego dnia
    10-07..10-11. ROI tych nóg nie był mierzalnie gorszy (piłka -1,1% wobec
    -3,8%), więc przekłamuje drukowana liczba, nie pieniądze singli - ważne
    przy mnożeniu pewności w kuponie. **Adnotacja: żadna noga nie jest dodana,
    zdjęta ani przestawiona, żadna pewność się nie rusza.** Hokej, koszykówka,
    siatkówka i CS2 flagi nie dostają: hokej zmierzony tak samo nie ma
    zawyżenia (32 nogi, -1,2 pp [-15,1; +11,9]), koszykówka jest zawyżona po
    obu stronach ceny (-15 / -18 pp), siatkówka i CS2 mają za mało nóg. Pre-rejestrowany
    test na nowych danych: `T-PRICE-GAP-flag`.
  - `coupon_form` / `removed_by_coupon_form` — pokrętła operatora z
    `config/sofa_coupon_form.json` (`docs/sofa/CONFIG.md`): domyślnie
    wszystko się drukuje (`ladder_form: "group"`, bez limitu na mecz); działają
    dopiero od `epochs.COUPON_STRUCTURE_FROM_UTC` (dzień ≥ 2026-10-06).
  - `builders_refused` / `builder_screen_prices` — F4.4, **wyłączone decyzją
    operatora 2026-10-05** („jeżeli chodzi o buildery to nie wyceniaj mi ich,
    sam będę widział”): `epochs.BUILDER_SCREEN_PRICE_FROM_UTC = None`, więc
    żaden builder nie odpada za brak kursu z ekranu, a PDF nie drukuje
    naszego kursu buildera (ani uczciwego, ani po narzucie, ani x, ani EV) -
    tylko nogi (każda z kursem pojedynczym Superbetu), łączne p i „kurs
    buildera: sprawdź na ekranie Superbetu”. Kurs wpisany przez operatora do
    `09_screen_prices.json` jest pokazywany jako jego notatka. Wybór buildera
    bez zmian (najwyższe łączne p meczu, wewnętrznie x po narzucie ≥ 0,90).
    Kod bramki (`…_UNTIMED`, `…_AFTER_START`, `…_OTHER_SLIP`,
    `BUILDER_SCREEN_X_BELOW`) zostaje, nieaktywny.

## 10c. FIXTURE_CHECK — czy mecz drukowany nadal jest grany (od 2026-10-05)

`scripts/sofa/run_fixture_check.py --date <d>` (albo `run_pipeline.py --only
FIXTURE_CHECK`), **most**, w przebudowie po OFFER, przed CONFIDENCE.
`/event/{id}` dla meczów drukowanych i przesuniętych zegarów →
**`runs/sofa/<d>/fixture_status.json`**. postponed / canceled / abandoned →
`FIXTURE_NOT_AS_SCHEDULED` (odmowa w CONFIDENCE). Świeży start zastępuje
zamrożony zegar RESOLVE dla bramki, blokady i `capture_closing` (K12). Bez
mostu: `UNVERIFIED` (pokazane, bez odmowy), kod 1. Odmowa (403 / 429, HTML
zamiast JSON, bezpiecznik otwarty albo wyzwolony) przerywa od razu, reszta
`NOT_ASKED`. Błąd przejściowy na jednym meczu (timeout mostu / 504, 5xx) —
jedna ponowna próba po 5 s, potem ten jeden mecz `UNVERIFIED` z powodem
(`NO_BRIDGE` / `PROVIDER_ERROR`) i sprawdzanie idzie dalej; dwa mecze z rzędu
porzucone tak = most leży, przerwa (2026-10-12 11:53–12:44Z jeden 504 czterokrotnie
zostawił 279–282 mecze `NOT_ASKED` na drukowanym PDF).

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
`08_confidence_sports.json`, `read_requests.json`, `09_screen_prices.json`
albo `config/sofa_coupon_form.json`. Potem zapisuje
`12_printed.json` (manifest wydruku), z którego następna przebudowa blokuje
nogi. Buildery: wyłącznie pozycje przechodzące `is_stakeable`, każda z
własnym śladem dowodowym. **`picks: 0` to odpowiedź legalna i częsta** — i zwykle jest
skutkiem narzutu korelacyjnego, nie braku danych.

**Nazwy jak na ekranie Superbetu** (od 2026-10-16, `bet.sofa.superbet_names`,
tylko wyświetlanie, żadna noga się nie zmienia): każda noga `11_coupon.json`
ma `superbet_market` i `superbet_selection`, czyli nazwę rynku i wybór
dokładnie tak, jak pisze je Superbet. Przykład: „3. tercja - Seattle Kraken -
liczba goli” / „poniżej 1.5”. Handicap ma postać „Seattle Kraken (1.5)”, z
liczbą tej strony, bez plusa, jak na ekranie. Nazwy rynków przeczytano
2026-10-16 z żywej oferty Superbetu (po jednym meczu z każdego sportu).
Drużyna albo zawodnik w piłce i tenisie ma pisownię z tablicy (`01_board.json`,
`board_sides`). Rynek, którego tabela nie zna, zostaje przy starej etykiecie;
nic nie jest zgadywane. W PDF kolumna „rynek” pokazuje nazwę z wyborem
pogrubionym, kolumna „linia” pisze „pow.” / „pon.”, a notki „słabsza o … niż
★” i nagłówki „ta sama zmienna” nazywają nogi tak samo. W HTML kolumna
„rynek” to ta sama nazwa (szukajka ją czyta). Nazwy nadaje COUPON_ASSEMBLY;
PDF i HTML nadają je przy renderze artefaktowi zbudowanemu wcześniej. Powód:
2026-10-15 kupon z czatu opisał nogę jako „Seattle +1.5 w 3. tercji”
(handicap tercji), a postawiony został sąsiedni rynek, „3. tercja - Seattle
Kraken - liczba goli: Poniżej 1.5” @1.21.

Oznaczenia na stronie (od 2026-10-01; pokazane, nie egzekwowane):

- **„ta sama zmienna Z<n>”** (dzień `stats_only`, od 2026-10-05, F4.2):
  przed pierwszym szczeblem każdej drabiny (`ladders` z `11_coupon.json`) wiersz
  nagłówka przez całą tabelę — mecz, zmienna, wszystkie szczeble z numerami
  pozycji, „jedna decyzja o jednej wielkości, nie N niezależnych zakładów”,
  para OVER + UNDER — i dopisek „ta sama zmienna Z<n>” przy każdym szczeblu,
  także w tabeli nóg w grze. Żaden szczebel nie jest zdejmowany (forma
  „jeden szczebel” to decyzja operatora, `ladder_form` w CONFIG.md). Pod
  pozycjami sekcja **„Ekspozycja na mecz”** (`exposure`) i, od 2026-10-06,
  lista **„Bet Buildery bez kursu z ekranu — nie na kuponie”**; builder
  wydrukowany pokazuje kurs z ekranu albo „brak kursu z ekranu”.
- **„ta sama drabina: N”** (dni przed epoką `stats_only`) przy singlu, gdy na
  liście stoi N szczebli jednej
  drabiny (ten sam mecz, rynek i podmiot, `confidence.ladder_key`), plus
  zdanie nad listą z liczbą takich drabin. Dwa szczeble jednej drabiny to
  jedno twierdzenie o jednej liczbie kupione dwa razy — 2026-09-30 kupon
  wydrukował na jednym meczu corners_total 12.5 poniżej, 11.5 poniżej i 7.5
  powyżej. Limit na
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
  zapisany bez rekordu per mecz (sprzed 2026-10-01) daje „- (no per-match record)” — pominięcie go
  zniekształciłoby przedział. Rekord dnia niesie `by_match`
  (`{mecz: [jednostki, rozliczone]}`) i `estimated_builders`: buildery
  rozliczone po szacunku `odds_if_product × haircut`, bo nie zapisano kursu
  z ekranu (7c „(szac.)”) — `audit_ledger` pokazuje je w osobnej kolumnie, bo
  to nie jest kurs, który Superbet wydrukował. Pierwszy odczyt (jeszcze po
  dniach, sprzed tej zmiany): oficjalny kupon 09-19..30 −1,8% [−9,0%;
  +11,1%] — przedział po dniach, nie do porównania z nowymi.
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
- **Termin zwrotu** (od 2026-10-13, Regulamin Zakładów Online 5.E.1.a z
  2026-02-10): mecz nierozegrany **do 23:59 następnego dnia czasu lokalnego
  miejsca meczu** po terminie z oferty jest anulowany (`settle.void_deadline`;
  strefa z kraju obiektu, rozgrywek albo - w sportach drużynowych -
  gospodarza, `config/sofa_country_timezones.json`, UTC gdy nieznany).
  Wcześniej kod czytał 48 h ze starego regulaminu (2022). Mecz przyspieszony
  o > 48 h - jak dotąd. Mecz przerwany (5.D.5: rynek rozstrzygnięty w chwili
  przerwania zostaje ważny, reszta anulowana) - jeszcze nieoceniany, otwarte.
- **Set nierozegrany** (od 2026-10-13, audyt C21): linia siatkówki na set,
  którego mecz nie dotrwał (3:0 nie ma 4. seta), to zwrot (VOID), jak mapa
  CS2 nierozegrana - Regulamin 5.E.1.h-i („w Zdarzeniu nie zostaną spełnione
  warunki”, „nie zostało zakończone oficjalnym wynikiem”;
  `shadow.set_not_played`). Wcześniej `UNGRADEABLE`; żadna drukowana noga
  tego nie dotyczyła.
- **Zwroty** (od 2026-10-05; krecz i walkower od 2026-10-07): mecz przesunięty
  poza termin zwrotu (`MOVED_BEYOND_VOID`), przyznany (`AWARDED`), krecz (`RETIRED`,
  status Sofascore „Retired", kod 92), walkower (`WALKOVER`), mecz odwołany
  (`CANCELED`, od 2026-10-12) albo wciąż przełożony / opóźniony po terminie
  zwrotu (`POSTPONED_BEYOND_VOID`, od 2026-10-12; przed nim
  zostaje `POSTPONED` i czeka na ponowny SETTLE) to zwrot
  (0 j.), nigdy przegrana i nigdy `sofa_settled_row` (trafia do
  `07_settle_skips.json`; `settle.REFUND_REASONS`).
- Mecz piłkarski rozstrzygnięty karnymi (kod 120) bez dogrywki (brak
  `extra1` / `extra2` / `overtime` w wyniku, `current` = `normaltime` +
  `penalties`; np. faza grupowa EFL Trophy) SETTLE rozlicza ze statystyk
  całego meczu - grał 90 minut (od 2026-10-12, `metrics.played_extra_time`).
  Po dogrywce rożne / kartki / faule / strzały zostają `EVENT_NOT_FINISHED`;
  gole zawsze z `normaltime`. Próbki i ratingi nadal pomijają oba rodzaje
  meczów (zmiana tam zmieniłaby to, co się drukuje).
- Propsy zawodników tylko ze składu samego zawodnika (inaczej
  `PLAYER_AMBIGUOUS`); próbka dopasowana po tokenach rozlicza się po swoim
  `matched_name` (kandydat w drugim składzie — `PLAYER_AMBIGUOUS`); wejście z
  ławki to `PLAYER_NOT_STARTED` — zwrot, nie wynik (`void_legs`).
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
nigdy w wyniku kuponu. Sekcje 7 i 7b to materiał wejściowy (legi i kandydaci),
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
  13_results.json                         po rozliczeniu: wynik każdej drukowanej pozycji (oceny dziennika), z niego PDF / HTML w kolorach wyniku
  vetoes.json          Veto[]             kanał analityka; [] w większość dni
  reads.json           LegRead[]          werdykty o nogach (KEEP / WATCH / NO_BET)
  read_requests.json                      prośby operatora o dodatkowy odczyt (pozycja albo group_key)
  10_boosts.json/.md   Boost[]            boosty Superbeta — NIE są kuponem (run_boosts.py)

runs/sofa/cs2/<data>/   — obok dnia, nigdy w nim
  snapshots.jsonl      linie CS2 Superbeta przed startem serii (run_cs2.py, etap CS2)
  settled.json         te linie ocenione z danych Sofascore (settle_cs2.py, CS2_SETTLE)

runs/sofa/shadow/<sport>/<data>/   — sport: hockey | basketball | volleyball
  snapshots.jsonl      linie Superbeta przed startem meczu (run_shadow.py, etap SHADOW)
  settled.json         te linie ocenione z wyniku Sofascore (settle_shadow.py, SHADOW_SETTLE)

runs/sofa/ledger/results.jsonl            dziennik: jeden wiersz na (dzień, grupę) — official, official:pre_stats_only, removed:reads,
                                          measure:<sport>; record_results.py; czyta audit_ledger.py
                                          (grupy epok audit_ledger.EPOCH_GROUPS: ... od 10-09 / od 10-12 / 10-13 mieszany / 10-14 mieszany / od 10-15 - nigdy sumowane)
                                          (wiersze wariant / multi / sport:<sport> / rule:<sport> to wycofane warianty dni do 2026-10-05: czytane, nigdy łączone)
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
się z tym, co się dzieje. Pomiar sam niczego nie bramkuje; od 2026-10-05
08:30Z migawki z `runs/sofa/cs2/` są wejściem SPORT_IDENTITY i
SPORT_CONFIDENCE (§10a), a `settled.json` rozlicza nogi CS2 na kuponie.

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
z plików), dziennik za D-7..D, krótki backfill
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
  po terminie zwrotu (koniec następnego dnia; do 2026-10-13: 48 h) to `VOID` — Regulamin Superbeta 5.E.1.a;
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
  `IN_PLAY_PRICE` nóg sportów na kuponie (`sport_day.grade_legs`) działa też dla CS2. `settled.json` jest
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
  dogrywki jest w `current`, a w żadnym okresie. Mecz hokeja / koszykówki,
  który Sofascore podaje **bez okresów** (sam `current` i `winnerCode`), od
  2026-10-12 jest rozliczany z wyniku końcowego (`score_source: final_only`,
  `t1_reg` / `t2_reg`): rynki całego meczu, a regulaminowe tylko gdy wynik
  regulaminowy wiadomo (`normaltime`, albo `current` gdy nic nie mówi o
  dogrywce); kwarty, połowy i tercje — nie. Kod zwycięzcy musi zgadzać się z
  wynikiem. Wcześniej taki mecz był `DATA_MISMATCH` na zawsze (koszykówka:
  10–22 mecze dziennie od 10-07, m.in. NBL, Serie B, ligi kobiet Austrii i
  Grecji). Historia i dopasowania krzywych (`sport_confidence`) czytają takich
  meczów nadal nie. Rynek bez „(z dogrywką)”
  liczy czas regulaminowy (rodziny hokejowe z dogrywką 613 / 617 / 621 / 653
  nie są mapowane, a NHL jest wystawiana **tylko** z nimi, więc żadna suma NHL
  nie jest mierzona — przegląd 2026-10-01); kwarta 4. i 2. połowa w koszykówce liczą się z okresów
  regulaminowych, także w meczu z dogrywką (operator, 2026-10-07). Gdy nie da się
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
  który ma migawki) pętla zapisuje dziennik (`record_results.py --from
  <najwcześniejszy> --to D`). D-2 doszło 2026-10-01: przełożony mecz staje
  się `VOID` dopiero po terminie zwrotu (koniec następnego dnia; do 2026-10-13: 48 h), a settle D-1 o 05:15Z jest najwyżej
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
  częstość drużyny ściągnięta do częstości bazowej, a od
  `epochs.CS2_TEAM_ROUNDS_RACE_FROM_UTC` (2026-10-13 18:10Z, audyt B10;
  przesunięte przez operatora z 2026-10-14 00:00Z) z
  wyścigu rund (`cs2_engine.team_rounds_from_race`: rozkład wyniku mapy o
  prawdopodobieństwie wygranej z Elo, ten sam co handicap rund) - na żywo, przy
  CS2_SETTLE i w replayu historii; krzywa CS2 dopasowana na tym estymatorze
  (staged od 2026-10-13, od 2026-10-14 w pliku głównym). Walk-forward: log-loss -0,0213 [-0,0237;
  -0,0188] (`docs/sofa/evidence/cs2_team_rounds_race_2026-10-13.md`).

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

**Ekspozycja zliczeń** (`epochs.CS2_COUNT_EXPOSURE_FROM_UTC` 2026-10-13
18:10Z, audyt B12, stała zgoda; przesunięte przez operatora z 2026-10-14
00:00Z): zabójstwa, śmierci, asysty zawodnika i
zabójstwa drużyny z wyścigu rund (W, L) x stawki na rundę
(`cs2_engine.ExposureBook`); log-loss nowy - stary -0,0135 / -0,0258 /
-0,0099 / -0,0380, wszystkie przedziały poniżej zera; headshoty gorsze
(+0,188), zostają przy próbce. Linie evidence tych rodzin dopasowano na
starym p; kontroli na liniach Superbetu 10-05..10-12 nie wykonano
(`docs/sofa/evidence/cs2_kills_exposure_2026-10-13.md`,
`docs/sofa/history/RAPORT_B11_B12_2026-10-13.md`).

**Rundy serii** (`epochs.CS2_SERIES_ROUNDS_FROM_UTC` 2026-10-15 00:00Z,
zlecenie operatora 2026-10-14): `rounds_total`, `rounds_handicap`,
`team_rounds` całej serii z `cs2_engine.series_rounds_side_p` - liczba map
wygranych przez każdą drużynę z rozkładu serii (`SERIES_KAPPA`), rundy każdej
mapy z wyścigu rund pod warunkiem jej zwycięzcy; mapa nierozegrana nic nie
dodaje. Wycena w SPORT_CONFIDENCE, `model_p` przy CS2_SETTLE, odtworzenie w
historii dopasowania. Krzywe historii (`rounds_handicap|TEAM`,
`rounds_total|OVER`, `team_rounds|OVER`, z
`data/refit_new_markets_2026-10-15/cs2_series_rounds/`) **zainstalowane
2026-10-15 00:17Z** - operator zainstalował je mimo ostrzeżenia: bramka na
drabince linii historii je przepuszcza, ale na liniach Superbetu
09-28..10-13 strony z krzywą >= 0,70 trafiły 0,33 przy 0,74 (21 / 19 serii;
`docs/sofa/evidence/cs2_series_rounds_2026-10-15.md`, kontrola na nowych
danych `T-CS2-SERIES-ROUNDS-superbet`; raport
`docs/sofa/history/RAPORT_KRZYWE_NOWE_RYNKI_2026-10-15.md`). Line evidence
czyta je jak każdy klucz (tylko obniża). Parzystość rund nadal bez wyceny.

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
bez zera na co najmniej dwóch dniach). Od 2026-10-05 08:30Z model wchodzi na
kupon nie jako blend z ceną, tylko przez krzywą kalibracji bez cen
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

PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --from <D-8> --to <D-1>           # dziennik runs/sofa/ledger/results.jsonl; zastępuje wiersze tych dat; oznacza wyniki na KUPON pdf / html (--no-mark: nie)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/mark_coupon_results.py --from <d> --to <d>          # 13_results.json + PDF / HTML w kolorach wyniku (samo, bez dziennika)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <d> --to <d>                 # odczyt dziennika: tabela na grupę i epokę, nigdy łącznie
```

Kody wyjścia: **0 = OK, 1 = PARTIAL, 2 = FAILED**. Wyjątek od 2026-09-30:
`record_results.py` kończy się `0` także wtedy, gdy pozycje jeszcze czekają (widać je w tabeli,
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

Od 2026-10-01 rozliczenie nóg sportów mierzonych (`sport_day.grade_legs`) i
dziennik sięga `--from <D-8>`: noga, która po 7 dniach od startu wciąż czeka
(`NOT_ON_SOFASCORE`, `DATA_MISMATCH`), staje się `NOT_GRADED:GAVE_UP`, czyli
nierozliczona, a nie wiecznie „pending”. Noga CS2 z serii ocenionej częściowo
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

## KUPON_<data>.html — widok z filtrami (od 2026-10-08)

Te same nogi z `11_coupon.json` co w PDF (`confidence.printed_singles` i
builderów), w jednym pliku bez serwera (`bet.sofa.coupon_html`, szablon
`src/bet/sofa/templates/coupon_view.html`). **Nie jest kuponem** - kuponem
jest PDF; HTML nie wycenia buildera i nie liczy stawki, a jedyna liczba,
której nie ma w artefakcie, to rekord rodziny (niżej). Filtry: okno godzin
(Europe/Warsaw, minuty od lokalnej północy dnia), minimalna pewność,
minimalne x (pewność × kurs), kurs od-do, sport, turniej, rynek, kierunek, tekst,
„ukryj zablokowane", „tylko czytane przez analityków"; kolumny sortowalne;
grupowanie po meczu. Mecz, którego start z `fixture_status.json` różni się od
zegara nogi, ma znacznik ⚠ z godziną FIXTURE_CHECK i godziną jego
sprawdzenia (10-08: start z rana nie nadążał za przesunięciem meczu).

`build_coupon_pdf.py` zapisuje HTML po każdym renderze PDF (także w
`rebuild_day.py`), więc przebudowany kupon zawsze ma świeży HTML; błąd HTML
zostawia PDF i kończy PARTIAL (exit 1). Sam HTML: `build_coupon_html.py
--date <d>`. Test: `tests/sofa/test_coupon_html.py` (liczba nóg = artefakt,
filtry w prawdziwej przeglądarce, jeśli jest Chrome).

**Rodzina na plusie i selekcja „x ≥ 1 i rodzina na plusie” (od 2026-10-18).** Rodzina to
(sport, rynek, kierunek). `bet.sofa.family_record` liczy jej wynik na
wydrukowanych nogach `official` kuponów z 14 dni przed dniem kuponu (nie
wcześniej niż 2026-10-09), ocenionych jak w ledgerze (`record_results.
graded_confidence`, WIN / LOSS przy cenie wydruku). Rodzina jest „na plusie”
przy >= 50 nogach i zysku w jednostkach. Plik `runs/sofa/<d>/family_record.json`
pisze `scripts/sofa/build_family_record.py` (sam, albo `build_coupon_pdf.py` /
`build_coupon_html.py` przed HTML); liczy go od nowa, gdy go brak, gdy jest z
innego dnia albo gdy ledger zapisano później. Błąd rekordu nie psuje strony:
filtr rodzin znika. Widok ma filtr „tylko rodziny na plusie”, znacznik przy
nodze takiej rodziny (innym nic się nie dopisuje) i przycisk „x ≥ 1 i
rodzina na plusie” (ustawia oba filtry, reszty nie rusza). Pomiar walk-forward
10-12..10-17 (okna 3-8 dni): selekcja -0,6% [-4,8; +3,9] na 1 254 nogach,
reszta kuponu -4,5%; lepsza od reszty w 6 z 6 dni, ale łącznie +4,0 pp
[-0,3; +8,1], 81% nóg z 10-17 - przewaga niepotwierdzona, zysk nieudowodniony (`docs/sofa/evidence/selection_walk_forward_2026-10-18.md`,
`scripts/sofa/measure_selection_walk_forward.py`, sprawdzian
`T-FAMILY-SELECTION`). Kupon (PDF) bez zmian. Test: `tests/sofa/test_family_record.py`.

## Wyniki na kuponie po rozliczeniu (od 2026-10-18)

Gdy dzień jest rozliczony, `record_results.py` (dla każdej zapisanej daty)
wywołuje `mark_coupon_results.py`: zapisuje `13_results.json`
(`bet.sofa.coupon_results`) i przerysowuje `KUPON_<d>.pdf` oraz `.html`
(`build_coupon_pdf.py --with-results`). Każdy wiersz kuponu ma kolor wyniku:
**zielony** weszło, **czerwony** nie weszło, **żółty** nie wiadomo (czeka na
rozliczenie, nie rozliczono, dwa rozliczenia się różnią) albo zwrot (0 j.).
Obok nogi: **typ** (wybór w słowach Superbetu i pewność) i **było** - co
faktycznie policzył rynek (rożne 11, gemy 23; przy rynkach tak/nie - podwójna
szansa, 1X2, „lub" - wynik meczu; handicap sportu mierzonego: różnica 1. drużyna
minus 2.), a pod meczem jego wynik. Buildery i ich nogi tak samo. Na końcu
PDF i strony: podsumowanie w procentach na sport i dla całego kuponu (weszło,
nie weszło, nie wiadomo / zwrot, trafność rozstrzygniętych przy ich średniej
pewności - ile kupon przewidywał, a ile weszło - i jednostki / ROI po 1 j. po
wydrukowanym kursie); HTML ma też filtr „wynik" i podsumowanie bieżącego
filtra.

Oceny są dokładnie te z dziennika (`record_results.graded_confidence`, klucze,
zwroty i reguła builderów jak w 7c; sporty mierzone przez
`coupon_sports.grade`), nigdy drugie rozliczenie; noga, której wyniki nie
zawierają, jest żółta, nigdy zielona. Wynik meczu piłki / tenisa pochodzi z
zapisanego zdarzenia Sofascore (`sofa_event_detail`), sportów mierzonych - z
`settled.json`. Render z wynikami to widok zakończonego dnia, nie wydruk: nie
dopisuje `printed/<ts>.json` i pomija strażników świeżości (krzywe
zainstalowane po buildzie); uruchamia się tylko, gdy oceny się zmieniły
(`--force`: zawsze). Niczego nie zmienia w pewności ani bramkach. Test:
`tests/sofa/test_coupon_results.py`.

## Pomiar: rozliczone linie wg rynku i kierunku (od 2026-10-13)

`scripts/sofa/measure_settled_by_market.py --from <d> --to <d> [--p-min 0.70] [--min-n 20]`
(`bet.sofa.settled_by_market`) - tylko do odczytu. Dla każdego sportu osobno
(football i tennis z `sofa_settled_row`, hokej / koszykówka / siatkówka z wierszy
line evidence z kursem z `shadow/<sport>/<d>/settled.json`, CS2 z
`cs2/<d>/settled.json`; sporty nigdy nie są sumowane) podaje dla każdej pary
(rynek, kierunek) i (rodzina ilości, kierunek): liczbę linii i meczów, trafność,
średnie p modelu, średnie 1/kurs, ROI na jednostkę i 95% przedział bootstrapu po
meczach (ziarno stałe). Mierzy SUROWE p modelu (nie skalibrowaną pewność),
wszystkie szczeble, bez bramek kuponu; tabela niesie ostrzeżenie o wielokrotnych
porównaniach (jeden wiersz na dwadzieścia przekracza zero z samego przypadku).
Wynik jest tropem dla wcześniej zarejestrowanego testu, nigdy bramką.
Przykład: `docs/sofa/evidence/settled_by_market_2026-10-09_12.md`.
