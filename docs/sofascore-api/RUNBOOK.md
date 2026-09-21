# `sofa` — przegląd procesu i runbook

Napisane 2026-09-21 po przebiegu, w którym pierwsze piętnaście minut poszło na
szukanie etapu `DISCOVER`, którego w tym pipelinie nie ma. Dokument istnieje,
żeby to się nie powtórzyło, i żeby przegląd architektury był w jednym miejscu,
a nie rozsypany po siedmiu plikach znalezisk.

Operacyjny skrót: **`/sofa-day`**. Ten plik jest warstwą pod nim — co każdy
etap naprawdę robi, czym płaci i gdzie kłamie.

---

## 1. Czym `sofa` różni się od `simple`

To są **dwa osobne pipeline'y**, nie dwie wersje jednego.

| | `simple` (stary) | `sofa` (bieżący) |
|---|---|---|
| kod | `scripts/simple/`, `src/bet/simple_stats/` | `scripts/sofa/`, `src/bet/sofa/` |
| źródło statystyk | bzzoiro, ESPN, highlightly… | **wyłącznie Sofascore** |
| źródło cen | Superbet | Superbet |
| etapy | DISCOVER → SUPERBET → ENRICH → MARKET_CONTEXT → TIPSTERS → ANALYZE | BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON |
| produkt | `<date>_kupony.md` | **`KUPON_<date>.pdf`** |
| komenda | `/run-day` (LEGACY) | **`/sofa-day`** |
| analitycy-agenci | tak (football/tennis/baseball) | nie — ścieżka jest w pełni kodowa |
| weta | `<date>_analyst_vetoes.json` | `vetoes.json` (zwykle `[]`) |

`sofa` importuje **zero** z `simple` — to była świadoma decyzja: wiedza się
przenosi, kod nie.

**Nazwy etapów nie mają wspólnego słownika.** Nie ma DISCOVER, nie ma ENRICH,
nie ma ANALYZE. Źródłem prawdy jest `DEFAULT_SEQUENCE` w
`scripts/sofa/run_pipeline.py` — pięćdziesiąt linii, przeczytaj je, zamiast
zgadywać.

---

## 2. Etapy — co robią, czym płacą

### BOARD (E3) — `src/bet/sofa/board.py`

Dzień z tablicy Superbetu. **Jedno** zapytanie HTTP, bez Sofascore, bez mostu,
poniżej sekundy. To jest odpowiednik „discovery".

Filtruje: sporty spoza mapy, deble tenisowe, mecze z kickoffem spoza doby,
turnieje z `config/sofa_board_exclusions.json`.

*Pułapka:* wielkość tablicy zmienia się dramatycznie z dniem tygodnia —
2026-09-20 (niedziela) 1040 meczów piłki, 2026-09-21 (poniedziałek) 102.
To nie awaria. Zweryfikuj surową odpowiedzią Superbetu, zanim zgłosisz problem.

### RESOLVE (E4) — `src/bet/sofa/resolve.py`

Dopina `sofascore_event_id` do każdego meczu z tablicy. **Przez most.**
Najdroższy etap po SAMPLES: ~8 zapytań na mecz.

Zwraca `identity: CONFIRMED | FUZZY` i luki `NO_MATCHING_EVENT`,
`AMBIGUOUS_ENTITY`. Zdrowy wskaźnik dopasowania to **72–90%**.

Zapisuje **oba zegary** — `kickoff_utc` (Sofascore) i `superbet_kickoff_utc` —
plus `kickoff_disagreement_h`. To nie nadmiarowość: w tenisie ITF Superbet
podaje nominalne „nie wcześniej niż", a rozjazd sięga 11 h.

### OFFER (E5) — `src/bet/sofa/offer.py`

Superbet, publiczne, bez limitu. Szybkie. Biegnie **dwa razy**: przed SAMPLES
(żeby nie próbkować metryk, których nikt nie wycenia) i po (żeby próg mierzył
się wobec świeżej ceny).

`status: PRICED | NO_PRICE`. `unmapped_markets` bywa ogromne (21 290
2026-09-21) — czytamy około jednej dziesiątej ekranu Superbetu i to jest znany
stan, nie usterka.

### SAMPLES (E6) — `src/bet/sofa/samples.py`

Ostatnie N meczów każdej strony, per metryka. **Przez most, najdroższy etap** —
~12 zapytań na mecz, przy 0,5 req/s to grubo ponad godzina.

`readiness: READY | PARTIAL | BLOCKED`, `coverage_floor` per sport.

*Pułapka:* `coverage_floor` porównuje z medianą ostatnich przebiegów i **nie
rozróżnia dnia tygodnia**, więc w poniedziałek zawsze krzyczy „matching
regression". Sprawdź wskaźnik RESOLVE, zanim uwierzysz.

### SHEET (E8) — `scripts/sofa/run_sheet.py`, `src/bet/sofa/engine.py`

Serce wyceny. Dla każdego szczebla:

```
prior  = baza ligowa lub globalna        (get_prior)
w_c    = n / (n + K_CENTRE)              (piłka 25, tenis 2)
centre = w_c·mean + (1−w_c)·prior        (albo mean, gdy brak bazy)
p_central:
    tenis i metryki empiryczne  -> p_empirical_raw(hits, n)
    liczniki piłkarskie         -> ujemny dwumianowy wokół centre
    reszta                      -> normalny z podłogą nośnika
p      = max(0.01, p_central − max(0, calibration_correction))
w      = n / (n + K_PRICE)               (K_PRICE = 10, NOT_FITTED)
p_bar  = w·p + (1−w)·market_p            (market_p po devigu potęgowym)
required_odds = 1.10 / p_bar
verdict = VALUE gdy offered > required
```

**Trzy rzeczy, które mylą przy audycie:**

1. `centre` to średnia **po skurczeniu**, nie średnia próbki. Porównywanie jej
   z surową średnią zawsze da „rozjazd".
2. `ladder_centre` / `ladder_sigma` opisują **drabinę bukmachera**, nie nasz
   rozkład. `sigma` rzędu 0,003 to normalna wartość dla drabiny.
3. Tenis używa częstości empirycznej, więc `p_central` **równa się** trafieniom
   w próbce. Piłka nie — i nie powinna.

### COUPON (E9) — `src/bet/sofa/coupon.py`

Wybiera single z wierszy VALUE, **każde odrzucenie zapisując** do
`06_dropped.json`. Bramki: weta, zegar (bierze **wcześniejszy** z dwóch),
wiek ceny (45 min), wiek próbki (60 dni, od 2026-09-21), `MIN_ODDS_FLOOR`,
`MAX_PER_FIXTURE`, jedna rodzina mechanizmu na mecz.

**Sortuje po nadwyżce — i to jest antyselektywne wobec błędu w `p`.**
`surplus = offered − 1.10/p_bar`, więc im mocniej `p` jest zawyżone, tym
pewniej wiersz wchodzi. To własność mechanizmu, nie hipoteza o konkretnym
dniu.

### CONFIDENCE — `src/bet/sofa/confidence.py`

Inne pytanie niż COUPON: nie „czy warte ceny", tylko „jak często to się
zdarza". Buduje Bet Buildery i stosuje **zmierzony narzut korelacyjny 12%**.

Slip jest do postawienia, gdy `is_stakeable` = `best_for_fixture` **i**
`ev_after_haircut > 0`. Oba raportowane osobno.

### PDF — `scripts/sofa/build_coupon_pdf.py`

**To jest kupon.** Renderuje tylko pozycje przechodzące `is_stakeable`.
Zero pozycji to częsta i poprawna odpowiedź.

### SETTLE (E10) — `src/bet/sofa/settle.py`

Rozlicza **zakończony** dzień, nigdy dzisiejszy. Jedyny pisarz, który stawia
cenę Superbetu obok wyniku, więc jedyne źródło dla `fit_k_price`.

### FIT (E11) — `scripts/sofa/fit_constants.py`

**Nie jest w `DEFAULT_SEQUENCE`.** Świadomy, osobny krok.

---

## 3. Przepływ artefaktów

```
Superbet ──► 01_board.json
                  │
        most ──►  02_fixtures.json ──┐
                  │                  │
Superbet ──► 04_offer.json ◄─────────┤   (2×: przed i po SAMPLES)
                  │                  │
        most ──►  03_samples.json ◄──┘
                  │
      config/ ──► 05_sheet.json        (baselines, reliability, engine constants)
                  │
                  ├─► 06_coupon.json + 06_dropped.json   (single VALUE)
                  └─► 08_confidence.json ──► KUPON_<date>.pdf   ★ produkt

           D-1: 05_sheet + wyniki ──► 07_settled.json ──► data/sofa.db
                                                              │
                                                    fit_constants ──► config/
```

Pętla `settled → config → sheet` to jedyne miejsce, gdzie dzień wpływa na
następny. Dlatego przestarzały plik konfiguracyjny jest cichy i kosztowny.

---

## 4. Przegląd: co jest mocne, co słabe

### Mocne

- **Nic nie znika w ciszy.** Każdy odrzucony wiersz ma powód w
  `06_dropped.json`, każda luka próbki ma `GapReason`. `audit_coupon.py`
  sprawdza to maszynowo.
- **Stała bez danych jest `null`, nie wartością zastępczą.** `K_PRICE` jest
  `NOT_FITTED` i każdy wiersz o tym mówi, zamiast udawać kalibrację.
- **Kalibracja jest uczciwa.** Na 2026-09-20 odchyłki `p_bar` od realizacji
  mieściły się w −0,013…+0,025 w dziesięciu kubełkach.
- **Narzut korelacyjny jest zmierzony, nie założony** — i to on decyduje
  o większości dni z pustym kuponem.

### Słabe — i to nie są hipotezy

- **Selekcja jest antyselektywna.** Patrz COUPON wyżej.
- **`K_PRICE` nie da się dopasować.** Krzywa Brier jest monotoniczna do w=0:
  model przegrywa z ceną. Reguła plateau odmawia podania wartości, i to jest
  poprawne zachowanie, nie brak.
- **Ścieżka VALUE-singli ma zły udokumentowany wynik.** −20,4% na 2026-09-20
  przy +8,2% dla PDF-kuponu tego samego dnia.
- **Rynki pochodne i półmeczowe stoją na cienkich danych.** `corners_2h_*` ma
  62 mecze w całej rozliczonej historii.
- **Czytamy ~10% ekranu Superbetu.**
- **Weryfikacja zewnętrzna tenisa jest praktycznie niemożliwa** — statystyki
  gemów w ITF-ach nie są dostępne za darmo, a tenis to zwykle 2/3 kuponu.

---

## 5. Naprawione 2026-09-21

| # | usterka | naprawa | test |
|---|---|---|---|
| Z1 | `stakeable_builders` liczyło `best_for_fixture`, ignorując EV → CONFIDENCE mówił „3", PDF stawiał 0 | wspólny predykat `confidence.is_stakeable`, używany przez oba | `test_confidence_gates.py` ×3 |
| Z2 | `reportlab` niezadeklarowany — PDF, czyli produkt, nie budował się | dodany do `dependencies` | — |
| Z3 | brak bramki na wiek próbki dla singli (cena miała 45 min, próbka nic) | `MAX_SAMPLE_AGE_DAYS = 60` + pole `sample_newest_days` | `test_coupon.py` ×3 |
| Z4 | globalna baza pisana bez `n` i bez progu; `corners_2h_for` zawyżona o 30% | pula trzymana do tego samego progu co wpis ligowy, zapisuje `n`; metadane `fitted_from`; kontrola spójności połówek | `test_baseline_fitting.py` ×10 |
| Z5 | wiersz kuponu nie niósł `calibration_correction` → nie dało się odtworzyć własnego `p_bar` | przeniesione na `CouponRow` | `test_coupon.py` ×1 |

**Zmierzony efekt Z4 na 2026-09-21** (przebudowa tego samego dnia na
poprawionych stałych):

| rodzina | VALUE przed | po |
|---|---|---|
| `corners_2h_*` | 12 | **1** |
| `goals_2h_total` | 9 | 1 |
| `shots_on_target_total` | 3 | **0** |
| **razem** | **142** | **99** |

Z3 zdejmuje kolejne 7, w tym pozycję o najwyższej nadwyżce dnia (+2,741,
próbka sprzed 105 dni). Znikające wiersze to dokładnie te, które niezależna
weryfikacja zewnętrzna odrzuciła.

### Zgłoszone, nienaprawione

- **`.venv` ma dwa interpretery** (`python` 3.12, `pip` → 3.14). To środowisko
  operatora, nie repozytorium.
- **`coverage_floor` jest ślepy na dzień tygodnia** — fałszywy alarm w każdy
  poniedziałek.
- **`pred_sd` nie jest zapisywane** na wierszu arkusza, więc `p_central` da się
  odtworzyć tylko w przybliżeniu (5 z 63 w granicy 0,024).
- **Niespójność sum połówek dla goli** (−13% i −17%) — bazy półmeczowe są
  mierzone na innej, mniejszej populacji meczów niż pełnomeczowe. Kontrola to
  teraz zgłasza; wyrównanie populacji to osobna praca.

---

## 6. Bramki przed commitem

```bash
.venv/bin/python -m pytest tests/sofa -q        # 673 + 2 skipped (2026-09-21)
.venv/bin/python -m ruff check src/bet/sofa scripts/sofa
.venv/bin/python -m mypy --strict src/bet/sofa scripts/sofa
```

`ruff` i `mypy` mają **zastaną bazę błędów** (odpowiednio ~100 i 129 w 10
plikach). Nie porównuj licznika z zerem ani z HEAD — w drzewie bywają cudze
niezacommitowane zmiany. Sprawdzaj, czy błąd wskazuje na linię, którą
napisałeś.

`ruff` **nie łapie** duplikatu w enumie. Po zmianie w enum uruchom import.
