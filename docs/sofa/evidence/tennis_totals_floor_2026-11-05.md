# Tenis: suma gemów / suma setów poniżej progu 0.70 - pomiar (2026-11-05)

Pytanie operatora (2026-11-05): `games_total` i `sets_total` (do dwóch wygranych setów)
prawie nigdy nie drukują się (dziś 3 z 1386 i 16 z 352 szczebli, reszta
`BELOW_CONFIDENCE_FLOOR`). Czy niższy próg (pewność 0.60-0.70 albo sama reguła
x = pewność x kurs >= 0.90) zarabia albo chociaż dorównuje cenie?

**Doprecyzowanie operatora (2026-11-05), przyjęte jako reguła werdyktu:** te nogi
nie muszą pokonać Superbetu - wystarczy, że są tak dobre jak jego cena (marża
akceptowana). Dlatego obok ROI raportujemy (a) trafienia minus podana pewność
(kalibracja: czy drukowana liczba obiecuje za dużo?) i (b) trafienia minus cena
po zdjęciu marży (de-vig), oba z 95% przedziałem z bootstrapu po meczach.
Werdykt reguły: **"skalibrowane"**, gdy przedział (a) zawiera 0 albo leży nad
nim; **"na poziomie ceny"**, gdy przedział (b) zawiera 0 albo leży nad nim;
**"zarabia"** tylko gdy dolna granica ROI > 0.

Skrypt (tylko odczyt): `scripts/sofa/measure_tennis_totals_floor.py`.
Wszystkie liczby poniżej pochodzą z jego wyjścia (`--boot 2000`).

## Wynik w skrócie

- **Żadna reguła nie zarabia.** ROI w części hold-out (10-21..11-04), obie rynki razem:
  R0 (obecna) -3.6% [-9.2, +1.6], R1 -4.6% [-7.7, -1.6], R2 -4.1% [-7.9, -0.4],
  R3 -5.7% [-10.7, -0.7]. Dolna granica ROI > 0 nie występuje w żadnej komórce
  żadnej połowy.
- **Każda reguła jest "skalibrowana" i "na poziomie ceny"** w hold-out - także same
  nogi, które reguła dokłada do R0. Nogi dodane przez R1 (hold-out, 2 023 nogi,
  1 360 meczów): trafienia - pewność +0.6 pp [-1.7, +2.9], trafienia - fair
  +2.4 pp [+0.0, +4.7], ROI -4.8% [-8.3, -1.4]. Czyli: liczba nie obiecuje za
  dużo, noga trafia jak (lub minimalnie powyżej) ceny bez marży, a traci dokładnie
  marżę Superbetu (~5%).
- **Wyjątek do kalibracji:** `games_total` z pewnością 0.65-0.70 (OVER, 150 nóg
  na wszystkich dniach) obiecuje za dużo: trafienia - pewność -6.5 pp [-14.4, +0.8],
  ROI -15.2% [-26.2, -5.2]. W R2 hold-out `games_total` -6.4 pp [-15.0, +1.6]
  (przedział jeszcze dotyka zera, więc formalnie "skalibrowane").
- **Kubełek krzywej 0-0.60 nie ukrywa dyskryminacji ponad cenę:** wewnątrz niego
  AUC modelu jest niższe niż AUC 1/kurs na tych samych wierszach (games OVER
  -0.016 [-0.032, -0.003], games UNDER -0.018 [-0.029, -0.005], sets OVER -0.018
  [-0.037, +0.001]).

**Werdykt wg reguły zleceniodawcy (dolna granica ROI > 0 w hold-out): nie.**
**Werdykt wg reguły operatora (jak cena, marża przyjęta): R1, R2 i R3 spełniają ją
w hold-out** (skalibrowane, na poziomie ceny po de-vig); obecna reguła R0 też.
To nie jest przewaga: każda z nich traci marżę (~3-6% ROI), tak jak drukowany
kupon dziś. Najmniejszy rozrzut i największa próba: R1; `games_total` z pewnością
0.65-0.70 to jedyna komórka, która wyraźnie obiecuje za dużo.

## Populacja i metoda

- **Wiersze:** każdy wiersz arkusza tenisowego `games_total` / `sets_total`
  (tylko linia 2.5) z dni stats-only, rozliczony przez SETTLE (`07_settled.json`,
  grader ledgera) jako WIN / LOSS, po cenie z arkusza (`offered_odds`, poranny
  OFFER, nie cena z późniejszego druku). Krecz / walkower / zwrot nie jest tam
  WIN / LOSS - wyłączone. Dni testu 2026-10-07..2026-11-04 (29 dni), 29 982
  wiersze z odtworzoną pewnością, 38 `NO_LINE_EVIDENCE` pominięte.
- **Dlaczego odtworzenie pewności:** zapis odmów jest nadpisywany przy każdym
  rebuildzie, a ostatni rebuild dnia widzi większość meczów tenisowych jako
  `KICKED_OFF` - pewność odrzuconego wiersza nie jest zapisana dla żadnego dnia.
  Pewność liczona jest więc tak, jak CONFIDENCE liczy ją **dziś**
  (`run_confidence.py`): zainstalowana krzywa (bez kluczy live-only, K13 / K13b),
  potem line evidence (`LineEvidence.read`: offset wg d, cap pasma ceny, v2,
  design effect kubełka) dopasowane **walk-forward** - dla dnia D wyłącznie z
  rozliczonych dni przed D (jak `fit_line_evidence.py --before D`, na wierszach
  tenisowych; wszystkie wielkości tenisowe są per sport).
- **Sprawdzenie odtworzenia** względem nóg zapisanych w `08_confidence.json`:
  10-28..11-04 - 56 nóg, mediana |zapis - replay| 0.0000, 91.1% w 0.005;
  10-17..10-27 - 30 nóg, mediana 0.0162 (wtedy obowiązywały inne reguły: offset
  wg d dopiero od 10-30, krzywe przed przeglądem 10-27). Na wszystkich dniach
  testu (112 nóg) mediana 0.0043, ta sama strona progu 0.70 w 69.6% - czyli
  dla wczesnych dni pomiar mówi "co powiedziałyby dzisiejsze reguły", nie
  "co dzień wydrukował".
- **Przedziały:** bootstrap po meczach (dzień, mecz) - szczeble jednego meczu nie
  są niezależne. Wariant "1 szczebel / mecz": jeden szczebel na (mecz, rynek,
  kierunek), ten z najwyższym x.
- **Fair (de-vig):** (1/kurs) / (1/kurs OVER + 1/kurs UNDER) tam, gdzie oba boki
  szczebla są w arkuszu.
- **Reguły zamrożone przed obejrzeniem ROI:** R1 pewność >= 0.60 & x >= 0.90;
  R2 pewność >= 0.65 & x >= 0.90; R3 x >= 0.95 przy dowolnej pewności; R0 obecna
  (0.70 & 0.90) jako odniesienie. Każda dodatkowo: marża szczebla <= 15%, kurs >=
  `MIN_ODDS_FOR_CEILING`. R3 podano także "bez p < 0.60", bo `CATCH_ALL_BUCKET`
  (`run_confidence.py`) odrzuca wiersz z p_central < 0.60 zaraz po progu - bez
  zniesienia tej bramki R3 i tak nie wydrukowałby takich nóg.
- **Połowy:** I 10-07..10-20, II 10-21..11-04 (hold-out). Podział po dacie.
- **Co zostało zsumowane:** wszystkie dni testu przez grupy epok ledgera od
  "stats_only" do "od 11-03" - dozwolone tylko dlatego, że pewność jest liczona
  jednymi (dzisiejszymi) regułami dla każdego dnia; ceny i populacja meczów są z
  różnych dni. Kobiety i mężczyźni razem (klasa decyduje o krzywej / kluczu
  evidence, nie o tabeli). OVER i UNDER razem w tabelach reguł.

## 1. Kubełki pewności - kluczowe komórki (wszystkie dni testu, wszystkie szczeble)

| rynek | kubełek | n nóg | mecze | trafienia | śr. pewność | śr. fair | traf. - pewność pp | traf. - fair pp | ROI % |
|---|---|---|---|---|---|---|---|---|---|
| games OVER | 0.60-0.65 | 1154 | 1027 | 0.657 | 0.614 | 0.628 | +4.3 [+1.4, +7.4] | +2.9 [+0.0, +6.0] | -3.8 [-8.0, +0.7] |
| games OVER | 0.65-0.70 | 150 | 150 | 0.620 | 0.685 | 0.668 | -6.5 [-14.4, +0.8] | -4.8 [-12.8, +2.4] | -15.2 [-26.2, -5.2] |
| games OVER | >=0.70 | 134 | 132 | 0.754 | 0.733 | 0.722 | +2.1 [-5.3, +9.1] | +3.2 [-4.1, +10.1] | -3.9 [-13.2, +5.2] |
| games UNDER | 0.60-0.65 | 871 | 773 | 0.627 | 0.620 | 0.596 | +0.6 [-2.8, +4.2] | +3.1 [-0.4, +6.5] | -3.5 [-8.9, +1.9] |
| games UNDER | 0.65-0.70 | 27 | 26 | 0.593 | 0.658 | 0.649 | -6.5 [-25.5, +11.9] | -5.7 [-25.5, +12.9] | -15.9 [-43.6, +10.6] |
| sets UNDER | 0.55-0.60 | 196 | 196 | 0.638 | 0.584 | 0.645 | +5.4 [-1.2, +12.0] | -0.7 [-7.3, +5.7] | -9.5 [-18.9, -0.3] |
| sets UNDER | 0.60-0.65 | 914 | 914 | 0.629 | 0.627 | 0.621 | +0.2 [-3.1, +3.4] | +0.8 [-2.4, +4.0] | -7.1 [-11.9, -2.4] |
| sets UNDER | 0.65-0.70 | 1261 | 1261 | 0.699 | 0.663 | 0.662 | +3.5 [+0.9, +6.0] | +3.7 [+1.1, +6.1] | -3.4 [-7.1, -0.0] |
| sets UNDER | >=0.70 | 735 | 735 | 0.751 | 0.742 | 0.746 | +0.9 [-2.3, +3.9] | +0.5 [-2.6, +3.5] | -7.9 [-11.8, -4.2] |

Kubełki < 0.55 (games OVER / UNDER ~10 000 szczebli każdy, sets OVER 3 142):
ROI -11.1%, -7.4%, -13.5%, każdy z przedziałem wykluczającym zero. `sets_total`
OVER nie ma ani jednej nogi z pewnością >= 0.55 (cała krzywa to kubełek 0-0.60,
realizacja 0.30). Pełne tabele z wariantem 1 szczebel / mecz: wyjście skryptu.

## 2. Reguły, hold-out (II połowa 10-21..11-04), obie rynki

| reguła | n nóg | mecze | traf. - pewność pp | traf. - fair pp | ROI % | werdykt |
|---|---|---|---|---|---|---|
| R0 obecna | 370 | 356 | +1.4 [-3.0, +5.4] | +3.7 [-0.7, +7.7] | -3.6 [-9.2, +1.6] | skalibrowane, na poziomie ceny, nie zarabia |
| R1 | 2393 | 1566 | +0.8 [-1.3, +2.8] | +2.6 [+0.5, +4.6] | -4.6 [-7.7, -1.6] | skalibrowane, na poziomie ceny, nie zarabia |
| R1 tylko dodane | 2023 | 1360 | +0.6 [-1.7, +2.9] | +2.4 [+0.0, +4.7] | -4.8 [-8.3, -1.4] | jw. |
| R2 | 1054 | 982 | +1.2 [-1.6, +3.9] | +3.2 [+0.4, +5.9] | -4.1 [-7.9, -0.4] | jw. |
| R2 tylko dodane | 684 | 660 | +1.0 [-2.6, +4.6] | +3.0 [-0.6, +6.6] | -4.4 [-9.5, +0.7] | jw. |
| R3 | 1198 | 918 | -1.1 [-4.3, +2.0] | +2.1 [-1.1, +5.2] | -5.7 [-10.7, -0.7] | jw. |
| R3 tylko dodane | 1037 | 808 | -1.4 [-4.7, +1.9] | +1.6 [-1.8, +4.9] | -6.2 [-11.6, -0.9] | jw. |
| R3 bez p<0.60 | 1136 | 888 | -0.6 [-3.6, +2.5] | +2.7 [-0.4, +5.7] | -4.3 [-9.0, +0.4] | jw. |

I połowa (10-07..10-20), obie rynki: R0 ROI -13.6% [-21.5, -5.7] (traf. - pewność
-6.2 pp [-12.2, -0.2] - R0 obiecywało za dużo na `sets_total`), R1 -5.7%
[-9.3, -1.9] (+0.1 pp [-2.3, +2.7]), R2 -6.9% [-11.6, -1.9] (-0.9 pp
[-4.4, +2.7]), R3 -7.7% [-13.5, -1.6] (-2.1 pp [-5.6, +1.4]).

Po rynkach, hold-out (ROI): R1 `games_total` -6.1% [-10.7, -1.5], `sets_total`
-3.3% [-7.0, +0.2]; R2 `games_total` -13.9% [-25.6, -3.0] (traf. - pewność
-6.4 pp [-15.0, +1.6]), `sets_total` -2.5% [-6.4, +1.7]. Wariant 1 szczebel / mecz
zmienia te liczby o najwyżej 2.1 pp (R1 obie: -3.9% [-6.9, -0.9]).

## 3. Kubełek krzywej 0-0.60 (p_central < 0.60): AUC modelu vs AUC ceny

| rynek | kierunek | n | mecze | AUC model | AUC cena | różnica [95%] |
|---|---|---|---|---|---|---|
| games_total | OVER | 9718 | 3056 | 0.560 | 0.577 | -0.016 [-0.032, -0.003] |
| games_total | UNDER | 9674 | 3077 | 0.580 | 0.598 | -0.018 [-0.029, -0.005] |
| sets_total | OVER | 3140 | 3140 | 0.561 | 0.578 | -0.018 [-0.037, +0.001] |
| sets_total | UNDER | 153 | 153 | 0.519 | 0.506 | +0.013 [-0.158, +0.170] |

Model rozróżnia wynik wewnątrz kubełka (AUC ~0.56-0.58 > 0.5), ale słabiej niż
cena. Rozbicie kubełka zrobiłoby z krzywej lepszą kalibrację, nie przewagę.

## Czego nie zmierzono

- Bramek po progu: kształtu próbki (linia poza próbką, moda przegrywa),
  `STALE_PRICE` / `KICKED_OFF`, odczytów analityków, `BEST_OF_FIVE_NOT_MODELLED`
  poza ograniczeniem do linii 2.5 - każda z nich tylko usuwa nogi.
- Ceny w chwili druku (arkusz ma cenę poranną); CLV.
- Pewności, którą dni faktycznie wydrukowały przed 10-28 (inne krzywe / reguły) -
  odtworzono dzisiejsze reguły.
- Krzywa tenisowa (fit 10-17, historia do 10-16) mogła widzieć część meczów z
  10-07..10-16 w historii, z której jest dopasowana (bez cen); line evidence jest
  ściśle walk-forward.
- Podatku 12% (ROI jest przed podatkiem).

## Wniosek

Obniżenie progu dla tych dwóch rynków **nie da zysku** (żadna komórka z dolną
granicą ROI > 0). Jeśli miarą jest "jak cena, marża przyjęta", R1 (0.60 & x >=
0.90) spełnia ją w hold-out na 2 393 nogach, z pewnością skalibrowaną do ~1 pp i
trafieniami ~2.5 pp ponad ceną bez marży, kosztem ~4-5% ROI - tyle co marża.
Przed jakąkolwiek zmianą: `games_total` 0.65-0.70 obiecuje za dużo (-6.5 pp), a
zmiana drukowania wymaga przełącznika w `bet.sofa.epochs` i decyzji operatora.
