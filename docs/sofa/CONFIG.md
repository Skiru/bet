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
| `sofa_confidence_calibration.json` | `fit_confidence.py` (`--classes-only` odświeża tylko `by_class`, reszta bajt w bajt) | `run_confidence.py`, `coupon.py` | krzywe `pooled` / `pooled_by_sport` / `by_market`, sufit każdego rynku; `by_class` — krzywe klas meczu (`women`, `tennis_women`, `tennis_team_cup`), noga klasy czyta tylko je |
| `sofa_side_correlations.json` | `measure_side_correlations.py` | `joint.py`, `derived.py` | `correlation` (**residual**, nie `raw_correlation`), `residual_pairs` |
| `sofa_reserve_competitions.json` | ręcznie, z dowodem (kolizje terminów na główną ligę, 2026-10-02) | `reserve_squads.py` → `samples.py`, `football_rating.py` | rozgrywki, w których kluby z `reserve_when_main_in` grają drugim składem pod id pierwszej drużyny; każdy wpis z liczbami `evidence`; brak pliku = tylko reguła kolizji |
| `sofa_friendly_competitions.json` | ręcznie, z dowodem | `samples.py`, `football_rating.py` | każdy wpis wskazuje plik dowodowy; id, nigdy nazwa; `allowed` — towarzyskie zostawione celowo, z powodem (851, 852: reprezentacje seniorskie) |
| `tennis_rating.json` | `fit_tennis_rating.py --cut <d>` (między dniami) | `run_sheet.py` | `fitted_from.cut_utc`, `features` zawiera `dhigh`/`dtour`, `n` na poziom |
| `sofa_women_competitions.json` | `find_women_competitions.py` | `run_sheet.py` | rozgrywki kobiece z cache (≥80% meczów kobiecych) — pula `PRIOR_GLOBAL_WOMEN` |
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
| `SOFA_TARGET_RPS` | **20** (od 2026-09-22 przy 5 oknach; wcześniej 14) | ma leżeć **powyżej** pojemności kart, nie na niej — zagłodzony kubełek daje 2,0 req/s, nasycony 8,6 (2026-09-22, 3 karty, powtórzone 2×) |
| `SOFA_MAX_CONCURRENCY` | **5** (= liczba okien; wcześniej 3) | pula wątków w RESOLVE, SAMPLES i SETTLE; **jedno zadanie na kartę**. Martwa konfiguracja do 2026-09-22; RESOLVE i SETTLE dostały pulę 2026-09-22 (SETTLE szło 0,094 req/s przy p50 20 020 ms — to okno `/pull`, nie sieć — mając `in_flight 1, pending 0`). Przy celu 14: 3 wątki 8,62 req/s przy p50 357 ms, 24 wątki **1,88** req/s — nadmiar nie daje nic i pogłębia kolejkę |
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
2. `half_match_coherence` — kontrola sumy połówek (od 2026-10-02 wieczór
   na tych samych meczach — patrz sekcja zmian niżej). Stan z pul bazowych:
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

### Zmiany z 2026-10-01 — zadziałają przy **następnym** fitcie między dniami

Kod się zmienił, pliki w `config/` nie: krzywe i stałe na dysku są nadal
z ostatniego fitu, a poniższe zmieni dopiero kolejny, świadomy fit.

- **Rynki pochodne (`both_over_`, `handicap_`, `most_`) wypadają z obu
  fitów** (`market_mapper.is_derived`). `fit_confidence.py` oceniał je jako
  „wynik > linia” na `p` odbudowanym z `sample_mean`/`sd`, a SETTLE rozlicza
  je po stronie (handicap wygrywa przy marży > −linia, `most_` po stronie
  albo remisie); na 2026-09-30 nie zgadzało się to z zapisanym wynikiem na
  351/1243 wierszach handicapu i 197/431 `most_`, a każdy z nich wchodził do
  `pooled_by_sport` i krzywych klas. `fit_constants.py` z tego samego powodu
  nie ocenia ich przy `K_CENTRE` (wycenia je `derived.py`, który `K_CENTRE`
  nie czyta). CONFIDENCE i tak odmawia nóg pochodnych.
- **Prior `K_CENTRE` zostawia własny mecz poza sobą** (`fit_constants.
  leave_match_out_prior`): bazy ligowe są fitowane na każdym rozliczonym
  wierszu, także tych, na których ocenia się `K_CENTRE`, więc wartość wiersza
  siedziała w priorze, którym go oceniano (do 2 z 30+ wartości ligi), i krzywa
  ciągnęła `K` ku „ufaj lidze”. Odejmowany jest mecz, nie dzień: 25,8 mln
  wierszy kalibracji z cache'u leży pod jedną `run_date` i nie ma daty meczu.
  Bazy zapisywane do `sofa_league_baselines.json` dalej zawierają każdy mecz.
- **`calibrate_from_cache.py` składa zduplikowane listingi**
  (`samples.one_listing_per_match`): Sofascore wystawia niektóre mecze dwa
  razy pod dwoma id, a powtórka rozliczała drugą kopię na próbce, która już
  zawierała ten sam mecz — własny wynik we własnej próbce.
- Pliki fitu (`sofa_engine_constants.json`, `sofa_league_baselines.json`,
  `sofa_market_reliability.json`, krzywe `fit_confidence`) są zapisywane
  atomowo (`bet.sofa.atomic`): przerwany fit nie zostawia uciętego JSON-a.

### Zmiany z 2026-10-02 — działają od razu, bez fitu

- **Propsy graczy nie wchodzą na kupon same przez fit.** `AWAITING_OWN_CURVE`
  wygasa, gdy rynek dostanie własną krzywą, a najbliższy `fit_confidence`
  da ją każdemu propsowi. CONFIDENCE odmawia więc propsów
  (`PLAYER_PROP_NOT_ADMITTED`), dopóki rynek nie zostanie dopuszczony z nazwy
  w `config/sofa_confidence_calibration.json`:
  `"admitted_player_markets": ["player_shots_for"]`. To decyzja operatora,
  nie skutek fitu (09-26..09-29 nogi buildera z propsów: deklarowane 0,776,
  zrealizowane 0,624; ceny jednostronne). Od 2026-10-02 (wieczór) fit
  kluczuje każdy wiersz na **zapisanym** `p_central` (patrz niżej), więc
  krzywa propsa opisuje `p`, które SHEET zapisał.
- **Korekta z `sofa_market_reliability.json` nie dotyczy tenisowego `p`
  już przyciągniętego do ceny** (blend ratingu z ceną, próbka dociągnięta do
  ceny szczebla; `run_sheet.row_correction`). Plik był fitowany na mieszance
  estymatorów, głównie próbkowych. Zmierzone 2026-10-02 na 50 434 rozliczonych
  wierszach tenisa z ceną, 09-24..10-01, w odległości < 0,15 od ceny: bez
  korekty 0,751 deklarowane / 0,759 zrealizowane w 0,7-0,8, 0,849 / 0,850 w
  0,8-0,9; korekta pogarszała Briera o 0,00028 (połówki po id meczu +0,00016
  / +0,00040). Tenisowe wiersze z samej próbki korektę zachowują — to one są
  przeszacowane (0,749 / 0,614, n=500) i korekta im pomaga w obu połówkach.
  Wpływa na `p_bar` i werdykt SHEET, nie na PDF (CONFIDENCE czyta `p_central`).

### Zmiany z 2026-10-02 (wieczór) — część działa dopiero po refitcie

- **`fit_confidence` kluczuje każdy wiersz na zapisanym `p_central`** — tym,
  pod którym CONFIDENCE szuka nogi. Wcześniej (poza rynkami empirycznymi)
  liczył `p` od nowa z surowych `sample_mean`/`sd`, bez shrinku do prioru,
  więc kubełki 0,80-0,95 `throw_ins_total` / `fouls_total` w kandydacie
  10-02 trzymały wiersze, które SHEET wycenił niżej (+3-6 pp zawyżenia).
  Fit otwiera bazę tylko do odczytu.
- **`calibrate_from_cache` liczy `p` tak jak SHEET** — te same funkcje
  (`engine.sheet_predictive_sd`, `engine.sheet_count_p_raw`): rozkład ujemny
  dwumianowy dla `NEGATIVE_BINOMIAL_METRICS`, wariancja skalowana
  środek/średnia dla liczników piłkarskich, rynki empiryczne z częstości
  próbki. **Kolejność refitu: najpierw `rebuild-cache-rows`, potem `fit`.**
  Fit nowym kodem na starych wierszach replayu (normalny zamiast NB) pogarsza
  `goals_total` i `cards_points_total` (zapisane `p` replayu i SHEET-u to
  wtedy dwa różne estymatory). Nie odtwarzane w replayu: ratingi (piłka,
  tenis) i priory tenisowe (tier / drabinka).
- **Tenisowe rynki gemów w secie wymagają dopuszczenia z nazwy**
  (`games_set1_total`, `games_set2_total`, `games_won_set1_for`,
  `games_won_set2_for`): CONFIDENCE odmawia ich jako
  `TENNIS_SET_MARKET_NOT_ADMITTED`, dopóki nie zostaną wpisane do
  `"admitted_tennis_set_markets": [...]` w
  `config/sofa_confidence_calibration.json` (fit i install przenoszą klucz).
  W kandydacie 10-02 ich nowe krzywe sięgały 0,925 i poza próbką (po dacie)
  zawyżały o 2-3 pp. Ostatnio drukowane w WARIANCIE 09-23..09-25 (z puli
  tenisowej); 10-01 i 10-02: zero nóg, więc dzisiejszy dzień się nie zmienia.
- **Żaden rynek tenisowy „w secie” nie pożycza puli tenisowej** — ani nad,
  ani wewnątrz własnego zakresu: dziura w krzywej to odmowa, nie pula.
- **`half_match_coherence` liczone na tych samych meczach** (te same pary
  mecz/strona z połową 1, połową 2 i całym meczem), a nie na pulach bazowych:
  połowy są tylko z żywego SETTLE, pełny mecz głównie z replayu. Na żywej
  bazie 10-02: wszystkie rodziny w granicach 0,1% (gole n=2980 par).
  Wcześniejsze −15%/−28% w kandydacie były różnicą populacji.
- **Pula `global` rynku połówkowego wymaga ≥ 2 rozgrywek**
  (`MIN_HALF_POOL_COMPETITIONS`). W kandydacie 10-02 osiem pul połówkowych
  miało n=30 z jednej ligi (np. `throw_ins_1h_for`, `shots_2h_for`).

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

---

## 7. Refit krok po kroku (`prepare_refit.py`)

Fit między dniami, rozpisany na kroki, które operator odpala **pojedynczo**.
Każdy krok drukuje, co zrobił, i odmawia (exit 2, `REFUSED: ...`) zamiast
zgadywać. Do `config/` piszą tylko `install` i `restore`, oba za `--confirm`.
Wszystko inne ląduje w katalogu roboczym `data/refit_<data>/` — nigdy pod
`runs/` ani `config/` (skrypt odmawia takiej ścieżki).

**Kiedy:** rano, **po** rozliczeniu D-1 (`run_settle.py`, `record_results.py`)
i **przed** startem dnia. Nigdy w trakcie dnia (sekcja 5, punkt 3). Nowe pliki
otwierają nową epokę porównywalności — commit mówi to wprost.

**Jak replay widzi inne pliki:** `SOFA_CONFIG_DIR` (`bet.sofa.config.config_dir`)
przestawia każdy czytnik konfiguracji — `run_sheet.py` (bazy, wiarygodność,
stałe, bazy tenisowe), `confidence.py` (krzywe, rozgrywki kobiece),
`samples.py` (towarzyskie, turnieje bez statystyk), `derived.py` (korelacje),
`tennis_rating.py`, `names.py`, `board.py`, `calibrate_from_cache.py`. Bez
zmiennej: `config/` w repo. Pisarze (fit_*) nadal piszą tam, gdzie każe im
linia poleceń.

### Komendy na 2026-10-03

```bash
# 0. warunek: 2026-10-02 rozliczony i zapisany w ledgerze; dzień 10-03 jeszcze nie ruszył
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date 2026-10-03 backup --db data/backup_2026-10-03/sofa.db
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date 2026-10-03 rebuild-cache-rows --dry-run
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date 2026-10-03 rebuild-cache-rows --confirm
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date 2026-10-03 fit
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date 2026-10-03 compare --days 2026-10-01 2026-10-02
# przeczytaj data/refit_2026-10-03/compare_report.md, zdecyduj
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date 2026-10-03 install --confirm
# commit, który install wydrukuje: "refit 2026-10-03: new comparability epoch"
# odwrót w razie potrzeby:
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date 2026-10-03 restore --confirm --backup config/backup_2026-10-03
```

Czasy zmierzone 2026-10-02 (próba na kopii bazy w katalogu tymczasowym,
niczego w `data/sofa.db`, `config/` ani `runs/sofa` nie ruszając; maszyna
zajęta równolegle wypełnianiem indeksu i pętlami CS2/shadow):

| krok | czas | uwagi |
|---|---|---|
| `backup --db` | ~40 s | kopia 24 GB: 36 s; wolne miejsce sprawdzane |
| `rebuild-cache-rows --dry-run` | 2 s | 25 841 116 wierszy replayu, 255 017 żywych w 14 `run_date` |
| `rebuild-cache-rows --confirm` | **~27 min** | DELETE 100 s + `calibrate_from_cache` ~25 min, szczyt RSS **~24,6 GB**; replay 999 805 meczów, wierszy replayu 25,8 mln → **55,2 mln** |
| `fit` | **~48 min** po przebudowie (54,1 mln wierszy: `fit_constants` 44 min, `fit_confidence` 4 min, szczyt RSS ~20 GB); bez przebudowy 25 min + 5 min | `fit_constants` kończy się exit 1 (`PARTIAL`) — to normalne |
| `compare` (2 dni, bez SHEET) | 12 s | z `--with-sheet` +~10 min na dzień (niezmierzone tutaj) |
| `install` | ~70 s | to głównie `pytest tests/sofa` (65 s) |

Co pokazała próba (na bazie z 2026-10-02, przed rozliczeniem 10-01/10-02 —
jutro liczby będą inne): po przebudowie replayu globalne `K_CENTRE` 25 → 15,
tenis 2 → 5, piłka bez zmian (25); `half_match_coherence` gorsza
(`goals_for` −15,9% wobec −10,8%, nowa pozycja `goals_total` −14,1%); 82
nowe krzywe `by_market_direction`; krzywe `player_*` są tylko w kubełku
0–0,6 (`player_shots_for` n=1974, zrealizowane 0,27). Replay 09-30/10-01:
WARIANT 10-01 80 → 103 nogi, oficjalny 4 → 7.

`all-prep` robi kroki 1–4 jednym poleceniem (`--with-cache-rows --confirm`
dokłada krok 2); po kolei jest czytelniej.

### Co robi każdy krok

1. **`backup`** — każdy `config/*.json` (bez `api_keys.json`) do
   `config/backup_<data>/` z `backup_manifest.json` (sha256). Istniejący
   katalog = odmowa. `--db <ścieżka>`: najpierw wolne miejsce (odmowa poniżej
   2× rozmiaru bazy z `-wal`/`-shm`), próba `PRAGMA wal_checkpoint(TRUNCATE)`,
   kopia trzech plików; jeśli baza zmieniła się w trakcie kopiowania (pisarz
   obok), exit 1 i ostrzeżenie — kopia mogła wyjść niespójna.
2. **`rebuild-cache-rows`** (opcjonalny, **długi**) — procedura z 2026-09-26:
   usuwa wiersze `run_date='cache-calibration'` partiami po 500 000 (pisarz
   obok czeka sekundy, nie cały DELETE), a potem uruchamia
   `calibrate_from_cache.py` na **bieżących** stałych i bazach. Wiersze żywe
   są przed i po liczone per `run_date` razem z `SUM(id)`/`MAX(id)` (podmiana
   wiersza zmienia id, nawet gdy liczba stoi — tak zniknęło 3154 wierszy
   09-26); jakakolwiek zmiana = przerwanie (przed `calibrate`, jeśli wyszła
   przy usuwaniu). `--out` replayu nigdy nie może wskazać `config/`
   (higiena, punkt 1). `--dry-run` tylko liczy, tylko do odczytu. Dlaczego
   tym razem warto: wiersze replayu są z 2026-09-26, a od tego czasu
   `calibrate_from_cache.py` skleja zduplikowane listingi (10-01) i czyta
   strony ∪ indeks `sofa_listed_event` (8f186dca); kartki sztabu (8f186dca)
   poprawiły `outcome` 7296 wierszy replayu przez `regrade_settled.py`, ale
   ich `sample_mean` jest dalej ze starego kodu (wniosek z kodu,
   niezmierzony). **Jeśli `index_listing_events.py` jeszcze wypełnia
   indeks, replay zobaczy indeks w połowie** — poczekaj na jego koniec albo
   świadomie pomiń ten krok. Inny pisarz bazy (indeks, pętle CS2/shadow)
   czeka między partiami; skrypt wypisuje procesy z otwartą bazą.
3. **`fit`** — kopia bieżącego `config/` do `data/refit_<data>/config/`,
   potem `fit_constants.py --config-dir` i `fit_confidence.py --out` na tę
   kopię (`fit_confidence` przenosi `admitted_player_markets` z kopii).
   Exit 1 z `fit_constants` to normalny `PARTIAL` (`K_PRICE` `NOT_FITTED`).
   Sha256 żywego `config/` przed i po — zmiana = przerwanie.
   `fit_manifest.json` zapisuje, z czego i kiedy fitowano.
4. **`compare`** — `compare_report.md` + `.json` w katalogu roboczym: każda
   stała (wartość i status, `K_CENTRE.by_sport`), 20 baz ligowych o
   największym |Δ| i `half_match_coherence`, kubełki wiarygodności o
   największej zmianie korekty, krzywe `pooled` / `pooled_by_sport` /
   `by_market` (ruch `realised_lo95`, kubełki, które zniknęły — tam noga
   spada na pulę albo dostaje `NOT_CALIBRATED`), nowe `by_market_direction`,
   `by_class`, każda krzywa `player_*` z `n` i `realised` (pod decyzję
   `admitted_player_markets`), `fitted_from`. Potem **replay kuponu**: każdy
   dzień kopiowany (z czasami modyfikacji, jak `cp -p`) do
   `data/refit_<data>/replay/{old,new}/runs/sofa/<dzień>/`, CONFIDENCE (oba
   profile) i PDF puszczone z zegarem zamrożonym na `created_at_utc`
   prawdziwego artefaktu, raz na kopii starego configu, raz na nowym.
   Wynik fitu to różnica **old vs new** (nogi wypadłe, dodane, zmiana
   pewności); osobno „dryf kodu” — prawdziwy artefakt vs replay na starym
   configu. md5 prawdziwego dnia przed i po każdym etapie; zmiana = przerwanie
   (pętla `capture_closing.py` i logi są pominięte). Wynik rozliczonej nogi z
   `sofa_settled_row` jest **in-sample** — te dni są w ficie; to informacja,
   nigdy dowód. **SHEET nie jest powtarzany** bez `--with-sheet`: `p_bar`,
   korekta wiarygodności, priory ligowe i `K_CENTRE` działają w SHEET, więc
   bez tej flagi replay pokazuje tylko wpływ krzywych pewności na wiersze
   starego arkusza (z flagą: ~10 min na dzień przy pierwszym parsowaniu).
5. **`install --confirm`** — wymaga kompletnego `fit_manifest.json` (sha256
   plików roboczych = to, co zapisał fit) i backupu, którego sha256 zgadza
   się z obecnym `config/`. Kopiuje cztery pliki fitu atomowo
   (`bet.sofa.atomic`); `admitted_player_markets` bierze z **obecnego**
   `config/` (decyzja operatora wygrywa z fitem). Potem
   `pytest tests/sofa -q`; porażka = automatyczny powrót backupu. Na koniec
   drukuje komendę commita.
6. **`restore --confirm --backup <katalog>`** — `config/` z backupu, z
   weryfikacją sha256 przed i po.

**Poza tym narzędziem:** `fit_tennis_rating.py --cut`,
`fit_tennis_tier_baselines.py`, `measure_side_correlations.py` — osobne
fity, nie ruszane tutaj. Dopuszczenie propsa (`admitted_player_markets`) to
osobna, ręczna decyzja po przeczytaniu raportu.
