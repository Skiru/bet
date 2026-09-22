# `sofa` — konfiguracja, stałe i pętla kalibracji

Wszystko, co przenosi wiedzę z jednego dnia na następny, przechodzi przez
`config/sofa_*.json`. Nic innego nie niesie stanu między dniami — dlatego
przeterminowany plik konfiguracyjny jest **cichy i kosztowny**, a fitowanie
w złym momencie jest błędem, nie stratą minuty.

```
05_sheet + wyniki ──► SETTLE ──► data/sofa.db ──► fit_constants.py ──► config/*.json ──► SHEET
                                       └──────► fit_confidence.py ──► sofa_confidence_calibration.json
```

---

## 1. Pliki konfiguracyjne

| plik | pisze | czyta | co trzeba sprawdzić |
|---|---|---|---|
| `sofa_engine_constants.json` | `fit_constants.py` | `engine.py` | `fitted_from`, status **każdej** stałej, `K_CENTRE.by_sport` |
| `sofa_league_baselines.json` | `fit_constants.py` | `run_sheet.py` (`get_prior`) | `fitted_from`, `half_match_coherence`, czy liga z dzisiejszej tablicy ma wpis |
| `sofa_market_reliability.json` | **wyłącznie** `fit_constants.py` | `run_sheet.py` (`calibration_correction`), `coupon.py` (sufit) | czy per rynek jest `status: MEASURED` i ile `n` |
| `sofa_confidence_calibration.json` | `fit_confidence.py` | `run_confidence.py`, `coupon.py` | krzywe `pooled` / `pooled_by_sport` / `by_market`, sufit każdego rynku |
| `sofa_side_correlations.json` | `measure_side_correlations.py` | `joint.py`, `derived.py` | `correlation` (**residual**, nie `raw_correlation`), `residual_pairs` |
| `sofa_friendly_competitions.json` | ręcznie, z dowodem | `samples.py` | każdy wpis wskazuje plik dowodowy; id, nigdy nazwa |
| `sofa_board_exclusions.json` | ręcznie, z pomiarem | `board.py` | **pusty jest poprawny** — wykluczenie bez pomiaru to cięcie pokrycia w przebraniu oszczędności |
| `sofa_no_stats_tournaments.json` | `fit_no_stats_tournaments.py` (poza sekwencją) | `samples.py` | `fitted_at_utc`, `min_events` ≥ 10, `events_examined`; każdy wpis to turniej, który **ani razu** nie oddał `/event/{id}/statistics` |
| `sofa_name_aliases.json` | ręcznie | `names.py` | aliasy PL→EN (111 wpisów): `anglia → england` itd. |

### Tempo, zakładki i współbieżność — co z czym chodzi w parze

Zmierzone 2026-09-22, most na żywo:

| warstwa | zmierzone | sufit |
|---|---|---|
| round-trip mostu | **175 ms** | **5,7 req/s** na zakładkę |
| `MIN_INTERVAL_MS` w userscripcie | 350 ms | 2,86 req/s |
| kubełek przy `SOFA_TARGET_RPS=2` | 500 ms | **2,0 req/s — dziś to wiąże** |

Stąd dwa wnioski, które trzeba trzymać razem:

1. **20 req/s przez jedną zakładkę jest nieosiągalne.** Nawet przy
   `MIN_INTERVAL_MS = 0` sufit to 5,7 req/s, bo tyle trwa obieg.
2. **`SOFA_MAX_CONCURRENCY` bez `SOFA_TARGET_RPS` nic nie daje.** Kubełek jest
   globalny. Pula wątków ma sens dopiero, gdy pracy jest komu dać — czyli przy
   **wielu zakładkach** `sofascore.com`. `bridge_server.claim()` nie jest
   związany z zakładką: każdy `/pull` zdejmuje inne zadanie, a `lastRequestAt`
   w userscripcie żyje per zakładka, więc K zakładek to K równoległych żądań,
   **każda nadal we własnym rytmie 350 ms**.

To jest istotne rozróżnienie wobec 2026-09-17: wtedy było jedno połączenie
`curl_cffi` ze 100 workerami i szczytem 550 req/s. Tutaj rośnie liczba
połączeń, a nie tempo połączenia — Sofascore widzi użytkownika z kilkoma
kartami. **Decyzja o podniesieniu jednego i drugiego należy do operatora** i
nie zapada w trakcie dnia.

### Zakładka zdławiona przez przeglądarkę

`check_bridge.py` mierzy obieg i ostrzega powyżej 600 ms. Zdrowo jest ~175 ms;
zdławiona zakładka odpowiada na **tych samych trasach** w ~1997 ms. To nie
Sofascore i nie pora doby — godzina 21 UTC zawiera oba tryby na różnych
przebiegach. Jeden nocny przebieg zapłacił za to ~5,3 godziny. Trzymaj kartę
widoczną i maszynę obudzoną.

### Zmienne środowiskowe (`SofaConfig.from_env`, `src/bet/sofa/config.py`)

| zmienna | domyślnie | uwaga |
|---|---|---|
| `SOFA_DB_PATH` | `data/sofa.db` | |
| `SOFA_RUNS_DIR` | `runs/sofa` | |
| `SOFA_TARGET_RPS` | **2** | ustaw z plateau `measure_bridge_capacity.py`, **nigdy powyżej** — 3,9 req/s na 3 kartach (2026-09-22); wyżej rośnie kolejka, nie tempo |
| `SOFA_MAX_CONCURRENCY` | 2 | pula wątków w SAMPLES. **Martwa konfiguracja do 2026-09-22** — czytana i nieużywana. Sama nic nie przyspiesza: kubełek `SOFA_TARGET_RPS` jest globalny, więc bez podniesienia tempa pula czeka na tokeny |
| `SOFA_BREAKER_THRESHOLD` | 3 | trzy porażki **pod rząd**; sukces zeruje licznik |
| `SOFA_BREAKER_COOLDOWN_S` / `_MAX_` | 30 / 300 | bez nich obwód nigdy się nie zamykał |
| `SOFA_EVENTS_TTL_MIN` | 360 | |
| `SOFA_ENTITY_MISS_TTL_MIN` | 10080 (7 dni) | negatywny cache, stemplowany `MATCH_LOGIC_VERSION` |
| `SOFA_LISTING_MISS_TTL_MIN` | 720 | wieczna pamięć pudła listingu kosztowała 28% budżetu żądań |
| `SOFA_EVENT_DETAIL_TTL_MIN` | 60 | sędzia ogłaszany późno; mecz zakończony i tak jest cache'owany na stałe |
| `SOFA_SAMPLE_N` | 10 | ile ostatnich meczów do próbki |
| `SOFA_MIN_SAMPLE` | 5 | próg `READY` na metrykę, per strona |
| `SOFA_PRICE_MAX_AGE_MIN` | 45 | `STALE_PRICE` |
| `SOFA_SHRINK_K` | 10 | |
| `SOFA_RUN_ID` | — | spina etapy w logu |

---

## 2. Stałe silnika i ich status

`config/sofa_engine_constants.json`, stan po fitcie z 2026-09-21
(1 964 797 rozliczonych wierszy, 1188 rozgrywek):

| stała | wartość | status | znaczenie |
|---|---|---|---|
| `K_CENTRE` | 15.0 globalnie, **piłka 25.0, tenis 2.0** | `FITTED` | ile próbka waży wobec bazy ligowej: `w_c = n/(n+K)` |
| `K_PRICE` | `null` → silnik używa `10.0` z `engine.py` | **`NOT_FITTED`** | ile nasze `p` waży wobec ceny rynku |
| `MAX_LADDER_SIGMA` | `null` → `1.25` z `engine.py` | **`NO_DIVERGENCE`** | próg rozjazdu z drabiną |

**`null` ze statusem `NOT_FITTED` to poprawny wynik, nie luka.** Kryterium
fitu to „największe nie-wartownicze K w paśmie 0,0005 od minimum Briera";
gdy pasmo pokrywa całą siatkę, reguła plateau **odmawia** podania wartości.
Dla `K_PRICE` krzywa Briera jest monotoniczna aż do `w = 0`: model przegrywa
z ceną i nie ma wewnętrznego optimum. To informacja, nie brak — i dlatego
**każdy** wiersz arkusza niesie notkę `UNFITTED_CONSTANTS`. Nigdy jej nie
usuwaj i nigdy nie podstawiaj pożyczonej wartości domyślnej.

`MAX_LADDER_SIGMA` ma `NO_DIVERGENCE` na 80 148 wierszach: w każdym paśmie
deklarowane ≈ realizowane (największy rozjazd 0,0004). Nie ma czego kalibrować.

`K_CENTRE` per sport nie jest kosmetyką: przy tenisowym `K = 2` i `n = 10`
próbka trzyma **83%** środka, więc czysta próbka jest uszanowana, a zła
niepoprawiona. Przy piłkarskim `K = 25` i `n = 8` próbka ma **24%** — wiersz
`*_1h_*` / `*_2h_*` jest w trzech czwartych priorem ligowym i trzeba o tym
mówić przy każdym takim wierszu.

---

## 3. Bazy ligowe

`config/sofa_league_baselines.json` — średnia realizowana wartość rynku per
rozgrywki: **48 rodzin metryk** plus trzy klucze metadanych (`_doc`,
`fitted_from`, `half_match_coherence`). Wpis poniżej `min_baseline_observations = 30`
**nie jest zapisywany** — łącznie z pulą `global`, trzymaną do tego samego
progu i zapisującą własne `n`. Brak wpisu znaczy brak prioru, a wtedy
`run_sheet` bierze za środek samą średnią próbki.

**Co sprawdzać przed zaufaniem arkuszowi:**

1. `fitted_from` — `settled_rows`, `distinct_competitions`, `fitted_at_utc`.
   Do 2026-09-21 ten plik nie niósł **żadnych** metadanych, a kopia w `config`
   była zbudowana na tabeli, która urosła od tego czasu o 88 185 wierszy
   i 120 rozgrywek — i nic na dysku tego nie mówiło.
2. `half_match_coherence` — kontrola sumy połówek. Stan bieżący:
   `goals_for: 1H 0.619 + 2H 0.777 = 1.396 wobec pełnego 1.689 (−17,3%)`,
   `goals_total: −13,3%`. To **realna niespójność**: bazy półmeczowe fitują
   się na mniejszej i innej populacji meczów niż pełnomeczowe. Raportowane,
   jeszcze nienaprawione.
3. Czy rozgrywki z dzisiejszej tablicy w ogóle mają wpis.

Historia, która mówi, dlaczego to nie jest formalność: priory półmeczowe
rożnych były **24–32% za wysokie** przez dwa dni. Poprawka zabrała dniowi
VALUE ze **142 na 99**, `corners_2h_*` z 12 na 1, `shots_on_target_total`
z 3 na 0 — a znikające wiersze były dokładnie tymi, które niezależna
weryfikacja zewnętrzna już wcześniej odrzuciła.

---

## 4. Wiarygodność rynków i sufit kalibracyjny

`config/sofa_market_reliability.json` (75 kluczy: rynek, `rynek|OVER`,
`rynek|UNDER`, plus pula `_pooled`) trzyma per kubełek `p`: `realised`, `n`, `correction`,
`ci_lower`, `status`. `correction` wchodzi do arkusza jako
`calibration_correction` i **tylko obniża** `p`
(`p = max(0.01, p_central − max(0, correction))`).

`config/sofa_confidence_calibration.json` odpowiada na inne pytanie: co
**w praktyce** dzieje się z deklaracją modelu. Kubełki mają `n`, `realised`
i `realised_lo95`, a CONFIDENCE rankuje po **dolnej granicy**, nigdy po
punkcie. Rynek z za małą liczbą wierszy w kubełku (`min_market_bucket = 400`)
spada na krzywą **swojego sportu** (`pooled_by_sport`: football, tennis),
potem globalną (`pooled`); własne krzywe ma dziś **33 rynki** (`by_market`); kubełek nieobecny we
wszystkich trzech oznacza **odmowę** wiersza (`NOT_CALIBRATED`), nie zgadywanie.

**Reguła, której złamanie kosztuje:** rynek z własną krzywą **nie może**
pożyczać puli **powyżej szczytu własnego zmierzonego zakresu**. Cisza powyżej
sufitu rynku jest dowodem — mówi, że model nigdy nie wyprodukował tam pewnej
prognozy, która by się potwierdziła. `games_won_for` ma 9286 rozliczonych
wierszy i **ani jednego kubełka powyżej 0,825**; zjazd na pulę 0,905 dał
dwanaście tenisowych nóg z deklaracją, jakiej ten rynek nigdy nie dostarczył.

Ten sam sufit trzyma single jako `ABOVE_MEASURED_CEILING` (COUPON) i nogi jako
`NOT_CALIBRATED` (CONFIDENCE) — celowo ta sama reguła w obu produktach.

### Znana otwarta usterka: `fit_confidence.py` fituje na nieskurczonym `p`

Skrypt przelicza `p` z surowej `sample_mean`, **pomijając** skurczenie
`K_CENTRE` ku bazie ligowej, które `run_sheet.py` stosuje **przed** wyceną.
Zmierzone na realnym arkuszu (3398 niepochodnych wierszy licznikowych):
mediana rozjazdu **0,0291**, p90 **0,1322**, **52,4%** wierszy poza jednym
kubełkiem 0,025; najgorzej `goals_for` (mediana 0,083). Tenisowe
`games_total` przy `K_CENTRE = 2` rozjeżdża się o 0,0052 — i to właśnie
potwierdza, że przyczyną jest skurczenie, a nie arytmetyka.

Skutek: krzywa obsługująca piłkarskie metryki licznikowe opisuje model, który
nie jedzie. `fit_constants.py` został na to poprawiony, `fit_confidence.py`
**nie**. Dopóki tak jest: sufit piłkarskiego rynku raportuj jako
**przybliżony**, a ruchu krzywej na tych rynkach nie traktuj jako dowodu
o modelu.

---

## 5. Higiena — trzy rzeczy, które już raz poszły źle

1. **Jeden plik, jeden pisarz.** `sofa_market_reliability.json` należy
   **wyłącznie** do `fit_constants.py`. `calibrate_from_cache.py --out` pisze
   krzywą **niebramkowaną**, do wglądu, i **nigdy** nie wolno jej kierować na
   tę ścieżkę: gdy dwóch pisarzy dzieliło plik, pusty nadpisał zmierzony
   i zameldował sukces.
2. **Nigdy nie edytuj stałej ręcznie.** Fituj albo zgłoś. Ręczna wartość nie
   ma `fitted_from` i nikt po tygodniu nie odróżni jej od zmierzonej.
3. **Nigdy nie fituj w środku dnia.** Ten sam arkusz przeliczony na nowych
   stałych jest innym arkuszem — porównywalność z wczoraj znika, a wraz z nią
   możliwość odróżnienia zmiany modelu od zmiany rynku.

---

## 6. Kiedy fitować

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_constants.py \
    --db-path data/sofa.db --config-dir config
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_confidence.py \
    --db-path data/sofa.db --out config/sofa_confidence_calibration.json
```

**Tak:** rozliczona tabela urosła istotnie · kontrola spójności nie przechodzi
· baza jest demonstracyjnie zła · zmieniła się logika metryki, więc historia
mierzy teraz co innego.

**Nie:** dzień poszedł źle · kupon wyszedł pusty · „dawno nie fitowaliśmy".

Po fitcie raportuj: `fitted_from` i o ile się ruszyło, `half_match_coherence`,
status każdej stałej, i czy któraś krzywa wiarygodności ruszyła na tyle, by
przesunąć wiersze.
