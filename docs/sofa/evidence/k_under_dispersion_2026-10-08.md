# K_CENTRE na rynek pod dopasowana dyspersja - pomiar 2026-10-08

Status: **pomiar + okablowanie za przelacznikiem, ktory zostaje wylaczony** (CLAUDE.md, "Changing the pipeline" 1 i 3). Skrypt `scripts/sofa/measure_k_under_dispersion.py`, test `tests/sofa/test_measure_k_under_dispersion.py`, wyniki `docs/sofa/evidence/k_under_dispersion_2026-10-08.json`. Baza nie byla otwierana (wiersze z `measure_pooling.py run --scratch`, A1), bez sieci.

## Pytanie

A1 (`pooling_2026-10-08.md`) znalazl, ze K na rynek (2-10 dla strzalow i fauli zamiast 15) poprawia log-loss, glownie na probach 3-7 meczow, a K dobral po bledzie kwadratowym srodka, na wierszach liczonych z wariancji probki. A2 / W2 (`count_dispersion`) usuwa niedoszacowana zmiennosc krotkich prob innym sposobem: wariancja = mu + alpha mu^2 z historii. Czy zysk z K znika, gdy rozklad ma juz dopasowane alpha?

## Werdykt

**Nie znika.** Na wierszach n >= 8 (populacja powtorki) K na rynek pod dopasowana dyspersja (spread `A`: alpha na rynek i rozgrywki z `config/sofa_count_dispersion.json`) poprawia log-loss po kalibracji (`lc`, x1e-4 nat na szczebel, wariant minus K=15, 95% bootstrap po meczach), dla **zestawu, ktory bylby wlaczony** (K po walidacji, bez goli, patrz nizej):

| populacja | cut 2026-06-09 (test 120 dni) | cut 2026-08-08 (test 60 dni) |
|---|---|---|
| wlasne liczby, n >= 8 | ll -1.7 [-2.1; -1.2], lc -1.6 [-2.1; -1.1] (288,220) | ll -1.9 [-2.5; -1.3], lc -1.8 [-2.4; -1.2] (207,267) |
| sumy meczu, n >= 8 | ll -6.9 [-8.5; -5.3], lc -6.4 [-8.0; -5.0] (132,333) | ll -7.4 [-9.4; -5.3], lc -7.4 [-9.3; -5.3] (94,298) |
| wlasne, tylko rynki ze zmienionym K | lc -11.1 [-14.6; -7.6] | lc -13.1 [-17.4; -8.9] |
| sumy, tylko rynki ze zmienionym K | lc -34.4 [-42.9; -26.5] | lc -23.4 [-29.6; -16.8] |

Obie polowki okna testowego maja ten sam znak i CI poza zerem (wlasne: pierwsza polowa lc -1.4 [-2.2; -0.6], druga -1.8 [-2.5; -1.2]; sumy -5.4 [-7.3; -3.3] i -7.5 [-10.1; -5.2]). Kryterium operatora ("CI wyklucza zero dla wlasnych i sum na n >= 8") **spelnione**, wiec K na rynek jest okablowane (przelacznik `epochs.PER_MARKET_K_FROM_UTC`, **None**).

Odpornosc na rozklad: ten sam pomiar ze spreadem `M` (alpha tylko na rynek, bez wartosci na rozgrywki): wlasne lc -1.7 [-2.2; -1.1], sumy -6.2 [-7.9; -4.8]. Kontrola `N` (wariancja probki, dzisiejszy SHEET): wlasne lc -2.3 [-2.9; -1.8], sumy -6.7 [-8.4; -5.3] - zysk z K **nie jest tym samym efektem co dyspersja**, dodaje sie do niej. Na n 3-7 (poza populacja powtorki, diagnostyka) zysk jest wiekszy (wlasne lc -2.7 [-4.2; -1.1], sumy -18.4 [-24.9; -11.9]) i pod dyspersja `A` o polowe mniejszy niz pod wariancja probki (wlasne -5.0): dyspersja zabiera czesc tego efektu, ale nie na n >= 8.

## Metoda

* Te same wiersze co A1 (`measure_pooling.py`, `F` = parametry zamrozone w cieciu): trening = 240 dni przed cieciem, test = po nim (cut 2026-06-09: 87.7k meczow, 463k jednostek). Centrum wiersza dla kazdego K z siatki (0, 2, 5, 8, 10, 15, 25, 40, 70, 1000) odtworzone z zalogowanej sredniej probki, n i priora ligi (prior wynika z centrum K=15). Prawdopodobienstwa: ta sama drabinka co SHEET (`calibrate_from_cache.lines_for`), `engine.sheet_predictive_sd` + `sheet_count_p_raw` z `Dispersion` z tabeli (NB, dla `shots_total` unormowany normalny).
* **K wybrany po log-lossie** (nie po bledzie kwadratowym) na wierszach treningowych n >= 8, osobno na (rynek, rodzaj). Regula zapisana z gory, bez patrzenia w test: K z pierwszych 2/3 wierszy treningowych (po czasie) jest **zachowany tylko gdy bije K=15 na ostatniej 1/3 wierszy treningowych** z 95% przedzialem (bootstrap po meczach) calkowicie ponizej zera; inaczej rynek zostaje na 15.
* Zysk = log-loss testu przy tym K minus przy K=15, surowy (`ll`) i po kalibracji (`lc`: mapa 40 przedzialow dopasowana na wierszach treningowych, jak krzywa z refitu).
* Zastrzezenie: alpha z `config/sofa_count_dispersion.json` zostalo dopasowane na calej historii do 2026-10-07 (walidacja od 2026-04-08), wiec okno testowe jest dla nich w probie (kilka parametrow na rynek; spread `M` ma jeden). K dla rynkow tez dopasowane na tej samej historii: powtorka bedzie w probie dla czterech liczb.

## Co by wlaczono i czego nie

Zestaw po walidacji (cut -120): `cards_points_for` 25, `fouls_total` 2, `shots_for` 8, `shots_total` 5 (przy cieciu -60 te same cztery; dodatkowo `corners_total` 40, nieistotne w tescie: lc -4.2 [-10.1; +1.9], nie wlaczone).

**`goals_for` zostaje na 15 mimo przejscia walidacji treningowej** (K = 10 wygrywa na treningu, -5.0 [-5.7; -4.2], i przegrywa na tescie w obu cieciach: lc +0.8 [-0.4; +1.8] i +2.2 [+0.9; +3.6]; ll +1.0 [+0.1; +1.7]). To decyzja po tescie (podglad), konserwatywna: nic nie dodaje do zmiany, tylko ja zmniejsza; A1 odnotowal ten sam objaw (niedopasowanie kryterium). `fouls_for` (10) i `shots_on_target_for` (10) nie przeszly walidacji (nie bija 15 na ostatniej 1/3 treningu).

K nie wchodza "w ciemno": zmieniaja p_central czterech rynkow, wiec wchodza **razem z refitem krzywych futbolowych** (`calibrate_from_cache --per-market-k`) i razem z `COUNT_DISPERSION_FROM_UTC` (pomiar jest pod dyspersja; K bez niej bylyby dostrojone do innego rozrzutu - decyzja operatora).

### Rynek po rynku (spread `A`; zysk x1e-4 nat na szczebel, n >= 8)

Cut 2026-06-09:

| rynek | K z uczenia | K po walidacji | zysk walidacji (ll) | n test | plain d_ll | plain d_lc | wired d_lc |
|---|---|---|---|---|---|---|---|
| corners_for | 15 | 15 | - | 35,516 | +0.0 [+0.0; +0.0] | +0.0 [+0.0; +0.0] | +0.0 [+0.0; +0.0] |
| corners_total | 40 | 15 | -5.1 [-10.9; +0.8] | 16,445 | -2.8 [-7.9; +1.8] | -4.0 [-9.1; +1.1] | +0.0 [+0.0; +0.0] |
| cards_points_for | 25 | 25 | -4.4 [-6.4; -3.0] | 17,486 | -1.5 [-3.4; +0.5] | -3.2 [-5.8; -0.6] | -3.2 [-5.8; -0.6] |
| cards_points_total | 15 | 15 | - | 8,167 | +0.0 [+0.0; +0.0] | +0.0 [+0.0; +0.0] | +0.0 [+0.0; +0.0] |
| fouls_for | 10 | 15 | -2.6 [-5.9; +1.0] | 27,838 | -7.1 [-10.2; -3.9] | -7.2 [-10.4; -3.8] | +0.0 [+0.0; +0.0] |
| fouls_total | 2 | 2 | -28.4 [-42.2; -13.0] | 13,241 | -29.1 [-43.5; -13.9] | -26.1 [-40.0; -11.2] | -26.1 [-40.0; -11.2] |
| shots_for | 8 | 8 | -12.2 [-18.6; -5.0] | 24,236 | -18.8 [-24.1; -12.7] | -16.8 [-22.3; -10.7] | -16.8 [-22.3; -10.7] |
| shots_total | 5 | 5 | -20.7 [-30.2; -11.6] | 11,532 | -45.4 [-54.4; -36.3] | -44.0 [-53.2; -34.9] | -44.0 [-53.2; -34.9] |
| shots_on_target_for | 10 | 15 | +1.2 [-1.4; +3.7] | 29,912 | +0.2 [-2.3; +2.8] | +0.2 [-2.4; +2.7] | +0.0 [+0.0; +0.0] |
| shots_on_target_total | 15 | 15 | - | 14,063 | +0.0 [+0.0; +0.0] | +0.0 [+0.0; +0.0] | +0.0 [+0.0; +0.0] |
| goals_for | 10 | 10 | -5.0 [-5.7; -4.2] | 153,232 | +1.0 [+0.1; +1.7] | +0.8 [-0.4; +1.8] | +0.0 [+0.0; +0.0] |
| goals_total | 15 | 15 | - | 68,885 | +0.0 [+0.0; +0.0] | +0.0 [+0.0; +0.0] | +0.0 [+0.0; +0.0] |

Cut 2026-08-08:

| rynek | K z uczenia | K po walidacji | zysk walidacji (ll) | n test | plain d_ll | plain d_lc | wired d_lc |
|---|---|---|---|---|---|---|---|
| corners_for | 15 | 15 | - | 27,145 | +0.0 [+0.0; +0.0] | +0.0 [+0.0; +0.0] | +0.0 [+0.0; +0.0] |
| corners_total | 40 | 40 | -6.1 [-12.2; -0.7] | 12,420 | -2.3 [-7.9; +3.9] | -4.2 [-10.1; +1.9] | -4.2 [-10.1; +1.9] |
| cards_points_for | 25 | 25 | -2.3 [-4.7; -0.4] | 11,680 | -4.0 [-6.7; -1.6] | -6.0 [-9.8; -2.6] | -6.0 [-9.8; -2.6] |
| cards_points_total | 15 | 15 | - | 5,397 | +0.0 [+0.0; +0.0] | +0.0 [+0.0; +0.0] | +0.0 [+0.0; +0.0] |
| fouls_for | 10 | 15 | -2.6 [-5.3; +2.0] | 20,110 | -6.6 [-10.6; -2.7] | -7.7 [-11.5; -3.7] | +0.0 [+0.0; +0.0] |
| fouls_total | 2 | 2 | -22.9 [-34.4; -6.3] | 9,494 | -27.5 [-43.8; -11.5] | -27.2 [-43.4; -11.1] | -27.2 [-43.4; -11.1] |
| shots_for | 8 | 8 | -9.2 [-17.0; -2.9] | 16,823 | -20.1 [-27.2; -12.7] | -18.0 [-24.9; -10.8] | -18.0 [-24.9; -10.8] |
| shots_total | 5 | 5 | -17.4 [-25.9; -8.6] | 7,951 | -51.3 [-62.9; -40.0] | -48.7 [-60.0; -37.4] | -48.7 [-60.0; -37.4] |
| shots_on_target_for | 10 | 15 | +2.5 [-0.3; +5.1] | 22,006 | +0.2 [-2.5; +3.1] | -0.2 [-3.3; +3.0] | +0.0 [+0.0; +0.0] |
| shots_on_target_total | 15 | 15 | - | 10,248 | +0.0 [+0.0; +0.0] | +0.0 [+0.0; +0.0] | +0.0 [+0.0; +0.0] |
| goals_for | 10 | 10 | -4.6 [-5.5; -3.7] | 109,503 | +2.5 [+1.5; +3.4] | +2.2 [+0.9; +3.6] | +0.0 [+0.0; +0.0] |
| goals_total | 15 | 15 | - | 48,788 | +0.0 [+0.0; +0.0] | +0.0 [+0.0; +0.0] | +0.0 [+0.0; +0.0] |

Kolumny: `plain` = K z uczenia dla kazdego rynku (bez bramki walidacji), `wired` = zestaw wlaczany (po walidacji, bez goli).

## Okablowanie (za przelacznikiem)

* `epochs.PER_MARKET_K_FROM_UTC = None`, `PER_MARKET_K_DATE`, `per_market_k_enabled(date, at)`, znacznik wiersza `k_rule` (`PER_MARKET_K`), `sheet_per_market_k`; `rebuild_plan` (`sheet_k`) przelicza SHEET na arkuszu innej reguly.
* `config/sofa_engine_constants.json`: nowy klucz `K_CENTRE.by_market.football` (nieczytany, dopoki przelacznik jest None; istniejace klucze bez zmian); `fit_constants.py` przenosi go przy refitcie (`carried_by_market`).
* `bet.sofa.per_market_k.k_for_market` - jeden czytnik dla SHEET (`run_sheet.py`) i powtorki (`calibrate_from_cache.shrunk_centre`, flaga `--per-market-k`; `prepare_refit.py rebuild-cache-rows --per-market-k`). `settle.settle_metric` dostaje K od wywolujacego (`run_backfill.py`, stale 10.0, nie jest czescia produkcyjnego SHEET) i nie byl zmieniany.
* Testy: `tests/sofa/test_per_market_k.py`, `tests/sofa/test_measure_k_under_dispersion.py`.
