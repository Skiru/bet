# Pomiar: rozrzut goli drużyny (goals_for) i podwójna szansa - 2026-10-22

Status: **pomiar, nic nie wdrożone** (oba warianty poprawki odpadły na
kryterium zarejestrowanym z góry). Żadnego przełącznika, żadnej zmiany w
`src/` ani `config/`; baza nie była otwierana (historia z pikla SHEET).

## Skąd pytanie

`data/diag_2026-10-22/DIAGNOZA.md` (przegląd ~100 rodzin, więc jedna na
dwadzieścia przechodzi przypadkiem):

* `goals_for|UNDER` poniżej pewności w 7 / 7 grupach epok (test znaków
  p = 0,008), `goals_for|OVER` w 6 / 7 - podejrzenie: rozkład goli drużyny w
  SHEET jest za wąski;
* `double_chance|OVER` ujemne w 6 / 6 grup (p = 0,016), dowody linii tego nie
  łapią - podejrzenie: model DC (niezależne NB na czystym ratingu,
  r = 7,586) jest za pewny siebie.

## Prerejestracja

Zapisana przed pierwszym liczeniem: `data/diag_2026-10-22/goals_for/PREREG.md`,
sha256 `6e02703f217b9bf1b94e42ad014df7635321c400e1abbfb766fd4012130c5913`
(`PREREG.sha256`, 2026-10-22 21:38:53Z; `data/` nie jest w gicie, więc hasz
jest zobowiązaniem). Streszczenie:

* **Historia, nie nasze dni**: pikiel SHEET `data/cache/football_history.pkl`
  (934 619 meczów, do 2026-10-22), krok naprzód `bet.sofa.centre_replay.walk`
  (rating czytany przed meczem, siła pucharów), centrum `goals_for` jak SHEET
  buduje je 2026-10-23: `live_centre` (waga ratingu, zakres) x rozciągnięcie
  goli v2 (faza sezonu meczu) x faza sezonu; alpha z
  `config/sofa_count_dispersion.json` (rozgrywki, inaczej rynek). DC: czyste
  centra ratingu, NB r 7,586 (arytmetyka `football_result.result_probs`).
* **Okna**: TRAIN 2025-07-01..2026-03-31 (228 984 mecze), TEST
  2026-04-01..2026-10-21 (164 251 meczów, 328 502 strony); połówki testu
  04..06 i 07..10-21 osobno. Przedziały 95% z losowania meczów (2000, seed 0).
* **Część 1** (diagnoza): VR = suma (y - mu)^2 / suma (mu + alpha mu^2),
  losowany PIT (10 koszyków), masa ogonów T (koszyk 1 + 10; 0,20 gdy
  skalibrowany). Za wąski = CI VR > 1 i CI T > 0,20; za szeroki = oba CI poniżej.
* **Część 2** (jednoparametrowe poprawki, dwustronne): A - alpha + d dla
  `goals_for` (d z MLE NB na TRAIN); B - r modelu DC (MLE 1X2 na TRAIN).
  Metryka główna A: log loss drabinki `goals_for` 0,5..3,5; B: log loss trzech
  selekcji DC. Strażnicy: btts, suma goli z konwolucji 0,5..5,5, 1X2, DC.
  Surowo i po kalibracji (mapa 20 kwantyli p dopasowana na TRAIN - krzywe są
  dopasowane na powtórce, więc poprawka musi ją przeżyć).
* **Kryterium**: główna metryka lepsza z CI w całości poniżej 0 surowo **i**
  po kalibracji, ten sam znak w obu połówkach testu; żaden strażnik gorszy z
  CI w całości powyżej 0.

Odstępstwa: brak (siatka r 400 punktów + Poisson jak zapisano; K pmf = 16
goli na stronę).

## Wyniki

### Część 1 - rozkład goli drużyny nie jest za wąski, jest **za szeroki**

| model / klasa (TEST) | n stron | VR [95%] | T [95%] | y - mu |
|---|---|---|---|---|
| SHEET goals_for, wszystko | 328 502 | **0,888 [0,880; 0,897]** | **0,191 [0,189; 0,192]** | +0,019 |
| kobiety | 25 698 | 0,832 [0,797; 0,866] | 0,185 | +0,048 |
| mężczyźni, alpha własnych rozgrywek | 297 324 | 0,892 [0,884; 0,901] | 0,191 | +0,017 |
| mężczyźni, alpha rynku (fallback) | 5 480 | 1,054 [0,979; 1,132] | 0,200 | -0,008 |
| mu < 0,8 | 22 398 | 1,164 [1,129; 1,201] | 0,214 | **+0,112** |
| mu 0,8-1,3 | 90 595 | 1,050 [1,034; 1,066] | 0,204 | +0,084 |
| mu 1,3-1,8 | 95 888 | 0,953 [0,940; 0,966] | 0,192 | +0,016 |
| mu >= 1,8 | 119 621 | 0,827 [0,815; 0,839] | 0,177 | **-0,046** |
| abs(s) >= 1 | 97 652 | 0,811 [0,797; 0,827] | 0,184 | -0,016 |
| DC: czysty rating, r 7,586, wszystko | 328 502 | 1,130 [1,119; 1,141] | 0,206 [0,204; 0,207] | +0,060 |
| DC: kobiety | 25 698 | 1,427 [1,368; 1,484] | 0,226 | +0,111 |

Werdykt części 1 (reguła z prerejestracji): **SHEET `goals_for` jest za
szeroki** (VR i T poniżej 1 / 0,20 z CI), nie za wąski - podejrzenie S1 w
wersji "rozrzut" odpada. To, co wygląda na rozrzut, idzie z poziomem centrum:
strona z niskim centrum strzela więcej niż ono mówi (+0,11 gola przy
mu < 0,8), z wysokim mniej (-0,05 przy mu >= 1,8) - centrum jest za mało
ściągnięte do średniej, a nie rozkład za wąski (podejrzenie, nie mierzone
jako poprawka). Strony modelu DC są za wąskie (VR 1,13), ale same
prawdopodobieństwa DC na historii są **niedoszacowane, nie przeszacowane**:
realizacja minus p w koszykach 0,70-0,80 +0,52 pp [+0,32; +0,72], 0,80-0,90
+1,21 [+1,00; +1,41], >= 0,90 +0,57 [+0,18; +0,93].

### Część 2 - obie poprawki odpadają

Log loss nowe minus stare, x1e-4 na szczebel, TEST [95%], połówki.

Poprawka A (d = -0,065 z TRAIN, czyli węższy rozkład - kierunek odwrotny do
podejrzenia):

| rynek | surowo | po kalibracji |
|---|---|---|
| **goals_for 0,5..3,5** | -1,39 [-1,93; -0,86] (h1 -3,85, **h2 +1,39**) | **+0,38 [+0,16; +0,64]** (gorzej) |
| goals_for pełne pmf | -11,67 [-13,70; -9,60] | - |
| btts | -8,89 [-10,92; -6,95] | -0,12 [-0,69; +0,49] |
| suma goli (konwolucja) | -7,12 [-7,84; -6,43] | -0,31 [-0,60; -0,04] |
| DC | +0,34 [-0,30; +0,95] | -0,01 [-0,54; +0,55] |
| 1X2 | **+1,53 [+0,44; +2,65]** (gorzej) | - |

Odpada na trzech warunkach: znak w drugiej połówce, po kalibracji gorzej z CI
powyżej 0, 1X2 gorzej. Średnia zmiana p na szczeblach >= 0,70: 0,72 pp.

Poprawka B (r = 21,4 z TRAIN):

| rynek | surowo | po kalibracji |
|---|---|---|
| **DC** | -0,76 [-1,69; +0,18] (h1 -5,50, h2 +4,59) | -0,48 [-1,10; +0,18] |
| btts (siatka ratingu) | **+25,70 [+22,62; +28,71]** (gorzej) | -1,45 [-1,79; -1,11] |
| suma goli (siatka) | **+1,32 [+0,14; +2,46]** (gorzej) | -0,50 [-0,76; -0,24] |
| 1X2 | +0,68 [-0,92; +2,40] (h1 -7,20, h2 +9,59) | - |

Odpada: główna metryka z CI przez zero, połówki o przeciwnych znakach,
strażnicy surowo gorsi.

### Wiarygodność po kalibracji (historia, pewność >= 0,70)

| | n szczebli | realizacja - pewność |
|---|---|---|
| goals_for OVER (stary) | 244 825 | +0,42 pp [+0,27; +0,57] |
| goals_for UNDER (stary) | 598 840 | -0,81 pp [-0,91; -0,71] |
| DC (stary) | 266 046 | -0,23 pp [-0,37; -0,10] |

Na historii, po mapie dopasowanej na wcześniejszym oknie, oba rynki są
skalibrowane z dokładnością do ~1 pp - rozkład nie tłumaczy -2..-17 pp z
żywych dni.

## Werdykt

* Rozkład goli drużyny w SHEET **nie jest za wąski** (VR 0,888, za szeroki);
  jednoparametrowa korekta rozrzutu nie przechodzi kryterium. Model DC nie
  przeszacowuje na historii (realizacja powyżej p przy p >= 0,70); korekta r
  nie przechodzi. **Nic nie wdrożone**, żadnego przełącznika, refit krzywych z
  tego powodu niepotrzebny.
* Ujemne wyniki na żywych nogach `goals_for` / `double_chance` pozostają
  podejrzeniem gdzie indziej: krzywa vs powtórka (kalibracja na historii
  trzyma ~1 pp), selekcja przez cenę (`price_gap`: nogi z pewnością ponad
  cenę realizują się około ceny) albo różnica centrum na żywo vs powtórka
  (próbka z SAMPLES, prior ligi) - niezmierzone tutaj.
* Otwarte (podejrzenie, nie zarejestrowane, nie mierzone jako poprawka):
  centrum `goals_for` za mało ściągnięte do średniej (+0,11 gola przy
  mu < 0,8, -0,05 przy mu >= 1,8).

## Pliki

`data/diag_2026-10-22/goals_for/` (git-ignored): `PREREG.md`,
`PREREG.sha256`, `collect.py` (wiersze powtórki -> `rows.npz`, 84 s),
`analyse.py` (-> `analyse.out`, `results.json`).
