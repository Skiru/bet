# D1: DNB i podwójna szansa z czystego ratingu z fazą sezonu (audyt 2026-10-13)

Pomiar: `scripts/sofa/measure_football_result_phase.py` (tylko odczyt), na
`scripts/sofa/measure_football_result_model.py` (pomiar C2 z
`RAPORT_NOC_2026-10-12.md`) i `bet.sofa.season_phase` (C1).

## Diagnoza

- Rynki wyniku piłki nie są wyceniane: OFFER zostawia je w `unmapped_markets`
  (`market_coverage`: `fb.result`, `fb.double_chance`, `fb.dnb`).
- Pomiar C2 (10-12): DNB -0,0792 [-0,0818; -0,0764] log-loss względem stopy
  bazowej ligi, DC -0,0376; krzywa z historii przeszacowuje w oknie testowym o
  2,4-4 pp w sierpniu-wrześniu (start sezonu). Operator 10-13 odmówił DNB / DC
  bez fazy sezonu.

## Rejestracja (zapisana 2026-10-13 PRZED uruchomieniem pomiaru)

- **Model:** niezależne NB goli stron na **czystym ratingu**
  (`FootballForecast.centre("goals_for", side)`, as-of), r dopasowane na
  treningu (`nb_rating` z C2); wariant z fazą: centra obu stron x exp(c[faza]),
  c dopasowane (`season_phase.fit_coefficients`) na centrach ratingu
  treningu; faza z `season_phase.phases_by_event` (as-of).
- **Okna:** trening 2024-10-01..2026-06-08, test 2026-06-09..2026-10-12 (jeden
  krok walk-forward: r, c fazy i krzywe dopasowane tylko na treningu; trening
  obejmuje sierpień-wrzesień 2025, więc krzywa widziała jeden start sezonu).
- **Krzywa:** kubełki 0,05 per (rynek, wybór) z treningu (`fit_curves` z C2,
  min. 200 wyborów), jak krzywe pipeline'u.
- **Populacja progu:** mecze test bez `UNLINKED` (odrzucane i tak).
- **Metryki:**
  1. d log-loss (z fazą - bez fazy) per mecz, DNB / DC / 1X2, 95% bootstrap
     po meczach (2000, ziarno 0);
  2. d log-loss (model z fazą - stopa bazowa ligi), jak w C2;
  3. kalibracja po krzywej wyborów do druku (p >= 0,70): realised - p z 95%
     bootstrapem po meczach, cały test i sierpień-wrzesień 2026 razem.
- **Próg do implementacji D1 (dla DNB i DC osobno), wszystkie trzy:**
  (a) model z fazą lepszy od bazy: górna granica 95% < 0;
  (b) po krzywej wybory p >= 0,70 w całym teście: |luka| <= 2 pp przy
      n >= 300 (reguła PASS `measure_calibration.py`);
  (c) to samo w sierpniu-wrześniu 2026 (start sezonu): |luka| <= 2 pp przy
      n >= 300.
  Metryka 1 jest raportowana (czy faza pomaga), nie jest progiem D1.

## Wynik (2026-10-13, `scripts/sofa/measure_football_result_phase.py`)

Trening 2024-10-01..2026-06-08: 494 867 meczów, test 2026-06-09..2026-10-12:
76 806 meczów (bez `UNLINKED` w obu). Współczynniki fazy na centrach czystego
ratingu (trening): early -0,0388, late +0,0348, final +0,0450. r NB:
A 7,586, B 7,602. Sierpień-wrzesień 2026 = 19 453 z 26 170 wyborów DNB do
druku po krzywej (okno testu to głównie start sezonu).

| rynek | B - A (faza pomaga?) [95%] | B - baza [95%] | mecze |
|---|---|---|---|
| DNB | -0,000046 [-0,000062; -0,000031] | **-0,0830 [-0,0860; -0,0803]** | 61 343 |
| DC | -0,000048 [-0,000077; -0,000019] | **-0,0394 [-0,0407; -0,0380]** | 76 806 |
| 1X2 | -0,000076 [-0,000130; -0,000020] | -0,0691 [-0,0715; -0,0666] | 76 806 |

Kalibracja wyborów p >= 0,70 (realised - p, 95% po meczach); „surowe” = p
modelu bez krzywej, „krzywa” = po krzywej z treningu:

| rynek | wariant | surowe, test | krzywa, test | surowe, sie-wrz | krzywa, sie-wrz |
|---|---|---|---|---|---|
| DNB | A | -0,25 pp [-0,75; +0,25] (23 539) | -2,96 pp [-3,45; -2,48] (26 170) | -0,91 pp [-1,49; -0,31] (17 487) | -3,54 pp [-4,12; -2,96] (19 453) |
| DNB | B (faza) | -0,22 pp [-0,72; +0,28] (23 499) | **-2,89 pp [-3,36; -2,41] (26 139)** | -0,88 pp [-1,46; -0,31] (17 442) | **-3,46 pp [-4,05; -2,91] (19 417)** |
| DC | A | +0,34 pp [+0,15; +0,54] (121 599) | -0,98 pp [-1,17; -0,78] (121 599) | +0,16 pp [-0,08; +0,38] (91 009) | -1,15 pp [-1,39; -0,93] (91 009) |
| DC | B (faza) | +0,39 pp [+0,18; +0,58] (121 589) | **-0,91 pp [-1,11; -0,71] (121 589)** | +0,22 pp [-0,01; +0,45] (90 996) | **-1,07 pp [-1,30; -0,84] (90 996)** |
| 1X2 | B (faza) | +1,24 pp (8 024) | -4,08 pp (12 718) | +0,55 pp (6 069) | -4,88 pp (9 605) |

**Próg zarejestrowany:**
- **DC: spełniony** - (a) -0,0394 względem bazy; (b) po krzywej -0,91 pp przy
  n = 121 589; (c) sierpień-wrzesień -1,07 pp przy n = 90 996.
- **DNB: niespełniony** - (a) tak (-0,0830), ale (b) po krzywej -2,89 pp i
  (c) -3,46 pp: krzywa przeszacowuje o więcej niż 2 pp.

Co z tego wynika:
1. **Faza sezonu w centrum prawie nie zmienia rynków wyniku** (B - A rzędu
   -0,00005 na mecz, choć przedział wyklucza 0). To arytmetyka: ten sam
   mnożnik na golach obu stron przesuwa głównie remis, nie to, kto wygrywa.
   Operator chciał fazy przed DNB / DC, bo krzywa przeszacowuje start sezonu;
   term w centrum tego nie naprawia (DNB po krzywej -3,54 -> -3,46 pp).
2. **Przeszacowanie robi krzywa, nie model:** surowe p NB na czystym ratingu
   jest skalibrowane w teście (DNB -0,2 pp, DC +0,4 pp), a krzywa z treningu
   podnosi p o ~1,5 pp (DNB: średnie p 0,803 -> 0,818) - w treningu wybory
   0,70+ realizowały powyżej p, w teście już nie. Poza sierpniem-wrześniem
   (6 717 wyborów DNB) luka po krzywej to ok. -1,3 pp, w sie-wrz -3,5 pp:
   faza ma znaczenie dla **krzywej**, nie dla centrum. Kandydat (niezmierzony,
   nie rejestrowany): klasa krzywej po fazie (`early` / reszta) albo brak
   krzywej dla DNB (surowe p skalibrowane) - nowy test z rejestracją.
3. UNLINKED wyłączone w obu oknach (SHEET je odrzuca).

Zastrzeżenia: jeden krok walk-forward (r, c, krzywe z jednego treningu); test
to w ~75% start sezonu, więc „cały test” i „sie-wrz” nie są niezależne;
selekcja „p >= 0,70” liczona na wyborach wszystkich meczów, nie na liniach
Superbetu (ceny nieznane w historii) - line evidence tych rynków nie istnieje.

## Decyzja i plan implementacji (DC; DNB czeka)

Próg spełnia tylko podwójna szansa. Implementacja DC nie zmieściła się w tej
sesji, bo dotyka pięciu etapów i replayu krzywych, który zmienia inna sesja.
Nic z poniższego nie jest wdrożone. Przełącznik nie istnieje.

1. **Przełącznik:** `epochs.FOOTBALL_RESULT_MARKETS_FROM_UTC`
   (`result_markets_v1`, domyślnie `None`) z predykatem (date, build_at), jak
   pozostałe.
2. **OFFER / `market_mapper`:** „Podwójna szansa” (pełny mecz; nie połowy, nie
   `fb.result_combo`) jako rynek `double_chance`, wybór `1X` / `X2` / `12` w
   `subject`, jedna kwota na wybór (`over_odds`; `under_odds` = kwota
   dopełnienia z „Mecz” 1X2: `2` / `1` / `X`, gdy jest; inaczej rynek
   jednostronny - marża liczona z trzech kwot DC jako drabiny). Klasyfikacja
   w `market_coverage` przechodzi z `fb.result` (COMPUTABLE) do MAPPABLE
   tylko przy włączonym przełączniku; wyłączony = OFFER bajt w bajt (wzorzec
   `MAPPABLE_FAMILIES_FROM_UTC`).
3. **SHEET:** nowa funkcja czysta `football_result.result_probs(lh, la, r)`
   (siatka NB z `measure_football_result_model.count_pmf` / `score_grid` /
   `market_probs`, przeniesiona do `src/bet/sofa/`) na **czystym ratingu**
   `FootballForecast.centre("goals_for", side)` (nie mieszance W - C2:
   mieszanka niedopewna o 15-18 pp), r z configu (dopasowane na historii,
   dziś 7,6). Faza sezonu: dozwolona (`season_phase.apply` na obu centrach),
   ale zysk znikomy (B - A -0,00005) - decyzja przy refitcie. `UNLINKED`:
   odmowa `CROSS_LEAGUE_UNLINKED` jak dziś. Brak ratingu którejkolwiek strony:
   brak wiersza (nie ma próbki „wyniku” do podstawienia).
4. **Krzywa:** `market:double_chance|<wybór>` z replayu historii
   (`calibrate_from_cache.py` - wymaga replayu ratingu A6, prowadzonego przez
   inną sesję) albo bez krzywej: surowe p było skalibrowane w teście
   (+0,4 pp), a krzywa z treningu przesunęła je o -0,9 pp. Do zmierzenia
   przed wyborem. Line evidence: klucz `double_chance` czyta własne linie
   Superbetu (dziś zero rozliczonych, więc `NO_LINE_EVIDENCE` do 50 linii /
   15 meczów w kubełku) - druk zacznie się dopiero po zebraniu linii.
5. **SETTLE:** `metrics.extract_metric` dla `double_chance` z `homeScore` /
   `awayScore` `normaltime` - zakres czasu (regulaminowy czy z dogrywką) do
   sprawdzenia w Regulaminie Zakładów Online przed kodem, niezweryfikowany
   tutaj; test na mecz z dogrywką i karnymi (kod 120). `sofa_settleability.json` bez zmian.
6. **Testy:** mapowanie nazw Superbetu (z `runs/sofa/<d>/04_offer.json`
   `unmapped_markets`), p z siatki (suma 1X + X2 + 12 = 2), odmowa UNLINKED,
   przełącznik wyłączony = OFFER / SHEET bajt w bajt, rozliczenie.
7. **DNB:** dopiero po nowym, zarejestrowanym teście krzywej znającej fazę
   (klasa krzywej `early` / reszta) albo bez krzywej; dziś po krzywej -2,9 pp
   (-3,5 pp w sierpniu-wrześniu).
