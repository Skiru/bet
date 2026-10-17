# Asy, podwójne błędy i rynki serwisowe tenisa - pomiar 2026-10-17

Pytanie operatora: czy wspieramy rynek asów i podwójnych błędów w tenisie, i jak
go poprawić. Wszystkie liczby: 95% przedziały z losowania całych meczów.

## 1. Stan przed zmianą

**Oferta.** Superbet wystawia rynki serwisowe tylko na meczach głównego touru
(ATP / WTA): 12 meczów 10-16, 29 meczów 10-17; zwykle jedna linia na rynek
(na zawodnika czasem drabinka). Rynki: asy, podwójne błędy (PB), asy + PB
(`serve_points`), każdy na mecz i na zawodnika, w meczu i w 1. / 2. secie.

**Model.** Środek = średnia własnej próbki serwującego (ostatnie mecze na
porównywalnej nawierzchni i w tym formacie) ściągnięta do priora tier x płeć
x nawierzchnia (`bet.sofa.tennis_prior`), rozkład NB (`engine.
NEGATIVE_BINOMIAL_METRICS`). Returnujący nie wchodzi w ogóle.

**Krzywe.** Asy i PB w meczu: krzywe historii do 0.90 (mężczyźni,
`tennis_women`). Sety i `serve_points*`: brak krzywej powyżej 0.60 - replay
historii (`calibrate_from_cache`) nigdy ich nie odtwarzał, więc kubły powstały
tylko z rozliczeń na żywo; `NO_LINE_EVIDENCE`, nigdy nie drukują.

**Na liniach Superbetu** (`sofa_settled_row`, 10-06..10-16, mecz / zawodnik,
asy + PB):

| | linie | mecze | deklarowane | zrealizowane | luka |
|---|---|---|---|---|---|
| krzywa historii >= 0.70 | 140 | 43 | 0.769 | 0.543 | -22.6 pp [-33.4, -14.3] |
| to samo i x >= 0.90 | 129 | 43 | 0.771 | 0.527 | -24.4 pp [-34.5, -15.9] |
| drukowane nogi 10-06..10-16 (po dowodach linii) | 14 | - | 0.759 | 0.714 | (1/kurs 0.754, ROI -3.1%) |

Surowe p modelu przegrywa z ceną w każdej grupie (log-loss modelu minus ceny
+0.02..+0.13). Dowody linii (cap pasma cenowego) zatrzymują prawie wszystko -
drukuje się krótki kurs, gdzie model zgadza się z rynkiem.

## 2. Korekta przeciwnika (`epochs.TENNIS_ACES_OPPONENT`)

Środek asów x współczynnik returnującego: ile asów serwowali jego rywale
(`against` z jego próbki; w replayu: total minus own), ściągnięte z K do tego
samego priora tieru, podzielone przez prior (`bet.sofa.tennis_aces_opponent`).
Total: (c_A f(B) + c_B f(A)) / (c_A + c_B). PB bez korekty.

**Pierwszy pomiar (uproszczony model, nie SHEET)** - walk-forward na 61 408
meczach singlowych, test od 2026-01-01: asy -0.032..-0.036 log-loss na linii,
PB +0.008..+0.013 (gorzej). Na liniach Superbetu ten uproszczony model:
`aces_for` -0.058 [-0.108, -0.014] (169 meczów). **To porównanie było
względem uproszczonej bazy**, nie estymatora SHEET.

**Replay historii** (`scripts/sofa/measure_tennis_aces_opponent.py`, funkcje
SHEET, zakres próbki SAMPLES, krzywa na train < 2026-01-01, test od
2026-01-01):

| rynek | wiersze test | mecze | log-loss, wszystkie linie | log-loss, linie rynkowe* |
|---|---|---|---|---|
| aces_for | 1 050 418 | 60 321 | +0.00027 [-0.00059, +0.00114] | -0.02012 [-0.02177, -0.01849] |
| aces_total | 543 354 | 37 547 | **+0.01241 [+0.01109, +0.01381]** | -0.00557 [-0.00781, -0.00321] |
| aces_set1_for | 369 978 | 27 684 | -0.00303 [-0.00409, -0.00192] | -0.02695 [-0.02939, -0.02442] |
| aces_set1_total | 178 138 | 15 168 | -0.00257 [-0.00430, -0.00096] | -0.01803 [-0.02163, -0.01464] |
| aces_set2_for | 373 748 | 27 642 | -0.00299 [-0.00412, -0.00187] | -0.02380 [-0.02614, -0.02135] |
| aces_set2_total | 177 150 | 15 143 | -0.00269 [-0.00440, -0.00113] | -0.01576 [-0.01934, -0.01226] |

\* linie, na których stare p OVER mieści się w [0.35, 0.65] - tam stawia się
jedyna linia rynku.

**Prawdziwy SHEET na liniach Superbetu** (`process_fixture` dnia z korektą i
bez; próbki 10-06..10-13 bez `against` uzupełnione z bazy asami rywala w tym
samym meczu - dokładnie to, co SAMPLES zapisuje od 10-13): 1 364 rozliczone
linie, 64 mecze: log-loss nowy - stary **+0.0060 [-0.0251, +0.0348]**; oba
gorsze od ceny (+0.093 / +0.087).

**Werdykt: przełącznik zostaje `None`.** Na wszystkich liniach historii asy
na zawodnika neutralnie, łączne gorzej; na liniach Superbetu z estymatorem,
który faktycznie wyceniamy, zero. Część pracy korekty robi już prior tieru i
zakres próbki. Kod, test i flaga replayu (`--tennis-aces-opponent`) zostają.

## 3. Rynki serwisowe w replayu (`--tennis-serve-markets`)

Replay odtwarza teraz asy / PB w secie i `serve_points` (mecz, sety) z
`/statistics` tym samym `extract_metric`, co SAMPLES i SETTLE.
`scripts/sofa/fit_tennis_serve_curves.py` (10,4 mln wierszy, 146 474 mecze,
wiersze przed 2026-10-17, krzywe jak `fit_confidence`, jednostronna bramka
holdout nowych rynków: fit przed 09-01, ocena 09-01..10-16) - **wszystkie
klucze mężczyzn przechodzą**, poza `serve_points_total|OVER` (nigdy 0.70);
klasy: kobiety przechodzą poza OVER asów w secie (n < 300 / nigdy 0.70),
team cup nie ma kubłów >= 0.70.

**Ale na liniach Superbetu** (krzywa + dowody linii, wywołania CONFIDENCE,
10-06..10-16):

`scripts/sofa/measure_tennis_serve_market_line.py --from 2026-10-06 --to
2026-10-16 --staged data/refit_tennis_serve_2026-10-17` (wynik:
`data/refit_tennis_serve_2026-10-17/market_line.md`):

| rynki | krzywe | nogi (>= 0.70, x >= 0.90) | mecze | pewność | zrealizowane | luka | 1/kurs | ROI |
|---|---|---|---|---|---|---|---|---|
| PB w secie + `serve_points` (p bez zmian) | zainstalowane | 0 | - | - | - | - | - | - |
| PB w secie + `serve_points` | nowe | 12 | 4 | 0.791 | 0.583 | -20.7 pp [-50.8, +5.8] | 0.819 | -26.8% |
| asy (mecz + sety), surowe p | zainstalowane | 7 | 5 | 0.784 | 0.714 | -7.0 pp [-54.8, +21.5] | 0.775 | -8.9% |
| asy, p z korektą | zainstalowane | 5 | 3 | 0.786 | 0.800 | +1.4 pp [-79.0, +22.2] | 0.809 | -1.0% |
| asy, p z korektą | nowe | 20 | 13 | 0.756 | 0.450 | -30.6 pp [-52.2, -4.6] | 0.697 | -33.6% |

(Wcześniejszy przebieg scratch, liczący asy w secie z surowym p razem z PB /
`serve_points`: 33 nogi / 17 meczów, -21.7 pp [-47.6, +0.1].)

**Werdykt: krzywych nie instaluję.** Wiersze replayu i staged krzywe są w
`data/refit_tennis_serve_2026-10-17/` (scratch sesji); sprawdzian na nowych
danych `T-TENNIS-SERVE-MARKET-LINE`. Flagi `--tennis-serve-markets` /
`--tennis-aces-opponent` **nie wchodzą do standardowego refitu**:
`fit_confidence` zbudowałby z nich krzywe, które na liniach rynku zawyżają.

## 4. Mechanizm: krzywa z siatki linii vs linia rynku

Replay wycenia całą siatkę linii wokół środka (`lines_for`). Wysokie kubły
krzywej wypełniają linie dalekie od środka - łatwe, gdzie model i rynek się
zgadzają. Superbet wystawia jedną linię blisko mediany; tam p >= 0.70 znaczy,
że model nie zgadza się z rynkiem, a takie nogi realizują dużo mniej. Widać to
już w samej historii: krzywa dopasowana na wszystkich liniach, czytana na
liniach rynkowych, przy >= 0.70 deklaruje 0.761 i realizuje 0.668
(`aces_for`, 21 178 linii testu), `aces_total` 0.767 / 0.636. To ten sam
problem, który koszykówka rozwiązała krzywą na liniach rynku (A7). Dla tenisa
nie mamy historii linii rynkowych asów; kandydat do zmierzenia: krzywa
dopasowana tylko na liniach rynkowych replayu (proxy jak wyżej).

## 5. Drukowane nogi tenisa 10-09..10-16 (kontekst audytu)

| rynek | kier. | nogi | mecze | pewność | zrealizowane | luka | ROI |
|---|---|---|---|---|---|---|---|
| games_won_for | UNDER | 324 | 248 | 0.748 | 0.744 | -0.4 pp [-5.8, +4.6] | -6.1% |
| games_set2_total | UNDER | 240 | 198 | 0.813 | 0.833 | +2.0 [-2.8, +7.1] | -1.5% |
| games_set1_total | UNDER | 230 | 182 | 0.790 | 0.770 | -2.0 [-8.2, +4.2] | -8.0% |
| games_set1_total | OVER | 160 | 142 | 0.802 | 0.794 | -0.8 [-7.6, +5.7] | -5.2% |
| games_set2_total | OVER | 106 | 101 | 0.777 | 0.849 | +7.3 [+0.8, +13.9] | +4.6% |
| games_won_set2_for | OVER | 103 | 78 | 0.736 | 0.670 | -6.6 [-16.8, +3.5] | -7.8% |
| games_won_set1_for | OVER | 102 | 79 | 0.747 | 0.676 | -7.1 [-17.3, +2.4] | -11.4% |
| wszystkie tenisowe | | 1 473 | | | | -1.0 [-3.5, +1.5] | -5.5% |

Tenis jako całość drukuje skalibrowanie. OVER gemów zawodnika w secie - ten
sam znak co mechanizm z p. 4, przedział dotyka zera: `T-TENNIS-SET-GAMES-OVER`.

Skrypty jednorazowe (scratch): `sb_check.py`, `sb_aces.py`, `printed.py`.
