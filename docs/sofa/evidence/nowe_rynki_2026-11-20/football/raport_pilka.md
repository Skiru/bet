# Piłka: nowe rynki ścieżki wyniku z symulatora - walidacja kandydatów (2026-11-20)

Pomiar tylko do odczytu. Żaden plik repozytorium nie zmieniony, nic nie
zatwierdzone, baza otwarta `mode=ro` (zapytania po kluczu / indeksie), sieć nie
pytana (tylko cache). Skrypty i wyniki: katalog tego raportu
(`/private/tmp/claude-501/-Users-mkoziol-projects-bet/04c6201e-4497-4273-b02c-92e4cd7d7f51/scratchpad/football/`).
Szczyt pamięci: 2,06 GB (centra, `live_centres.log`), historia 0,56 GB
(`history.log`).

## W skrócie

- **Wybór: handicap połowy (1. i 2. połowa, strona z +L)** - "1.połowa -
  handicap" / "2.połowa - handicap", nowe klucze np. `result_1h_handicap` /
  `result_2h_handicap`. Dwustronny (para Superbetu, marża ~9,4%), oceniany z
  `period1` i wyniku 90 min, symulator już daje gole na połowę. Na historii
  06-01..10-20 surowe p symulatora jest skalibrowane (1. połowa ±1 pp w każdym
  przedziale, 2. połowa -0,5..-0,8 pp). Na żywo 11-06..11-19 przy bramkach z
  krzywą historii: 1H 894 nóg, 2H 906 nóg (ok. 64 / dzień każda połowa),
  trafione - pewność -3,1 pp [-6,0; -0,5] / -1,1 pp [-3,7; +1,5]; z dzisiejszym
  pulowanym offsetem line evidence +1,1 / +2,2 pp. ROI -5,7% / -2,7% przed
  podatkiem, ok. -17% / -14% po podatku 12%.
- **Przewagi nad ceną nie ma w żadnym kandydacie:** Brier(symulator) -
  Brier(cena bez marży) > 0 wszędzie, przedział wyklucza zero w 7 z 10
  rodzin (to samo przy de-vig potęgowym). Nowy klucz to wolumen i kalibracja,
  nie zysk - jak dotychczasowe klucze symulatora (audyt 11-11).
- **Odpadają jako to samo zdarzenie co rynek już czytany:** "Handicap"
  (pełny mecz, nieczytana reszta = ±0,5 = 1X2 / podwójna szansa, ±4,5+ rzadkie)
  i "Handicap 1X2" (europejski 3-drogowy: każda strona nie-remisowa =
  `result_handicap` +L albo DC; remis = dokładna przewaga, nigdy w strefie).
  "Remis w obu połowach: tak" = HT/FT X/X (czytany).
- Odpadają z powodu kalibracji / wolumenu: "Obie drużyny strzelą & powyżej L"
  (nad-obietnica -6..-8 pp na żywo, -1..-3 pp w historii), połówkowe "zakład
  bez remisu" (548 meczów, ~40% zwrotów, Brier 1H gorszy +0,017), "wygra
  przynajmniej jedną połowę" (128 meczów).
- Drugi wybór: "<drużyna> wygra obie połowy: nie" - największe pokrycie (2142
  mecze, 153 / dzień), w historii skalibrowany (+0,2 pp przy 0,80-0,92 na
  34 908 wierszach), ale wydrukowane nogi -5,3 pp [-7,9; -2,6] z krzywą (selekcja
  przeciw cenie), ROI -5,3%.

## 0. Dane i metoda

- Ceny: `runs/sofa/<d>/unmapped_prices/2026*.jsonl.gz` (pliki OFFER, bez
  prefiksu sportu) 2026-11-06..11-19, mecze piłki z `02_fixtures.json`, nazwy
  stron z `01_board.json`; na selekcję ostatni aktywny snapshot przed startem
  (`inventory.py` -> `cand_prices.jsonl.gz`, 68 561 selekcji kandydatów).
- Cena bez marży: proporcjonalnie w pełnej, rozłącznej grupie z JEDNEGO
  snapshotu (tak / nie; para handicapu: strona A -L i B +L; 3 wyniki
  handicapu europejskiego). Strefa = kurs 1,09-1,43 i p bez marży >= 0,70.
- Ocena: SETTLE-owe `football_sim_markets.sim_value` (90 min + doliczony czas,
  po dogrywce `normaltime`; `period1`; odmowy INTERNAL_INCONSISTENT,
  NO_HALF_TIME_SCORE, HALF_ABOVE_MATCH, HALF_TIME_DISAGREES) na `sofa_event_detail`
  + `sofa_event_stats.incidents_json`, `settle.is_completed_event` i
  `settle_completed` (przyznany walkowerem odpada) - `step23_live.py`.
- Model: dokładnie SHEET-owy `football_sim_sheet.SimPricer` (4 000 ścieżek,
  ziarno = id, `config/sofa_football_sim_params.json`) na centrach czystego
  ratingu as-of. Centra 11-06..11-19 (forecastów brak po 11-05):
  `live_centres.py` = ta sama maszyneria co backfill line evidence
  (`measure_football_sim.fresh_book` z flagami BOOK_DAY 2026-11-06,
  `walk_forward_centres`, brakujące mecze sparsowane z `/event`): 4 626 z 4 969
  meczów, 4 610 z centrum goli. Bez schedule term (krzywe symulatora też były
  dopasowane bez niego). Z łącznego rozkładu (h1, a1, h2, a2) liczone p każdej
  selekcji (`simcore.py`, `cands.py`); zakład bez remisu warunkowo na brak
  remisu w połowie.
- Historia: `data/football_sim_2026-11-06/minute_history.pkl` +
  `forecasts.pkl`, okno 2026-06-01..10-20 - to samo co
  `fit_football_sim_curves.py` (40 025 meczów, zgadza się z `fitted_from.matches`
  krzywych), 1 783 546 wierszy (`step4_history.py`).
- Przedziały: bootstrap po meczach (2 000 losowań; historia 500), wszystkie
  wiersze meczu razem (`stats.py`).

## 1. Kształty, wolumen, marża, strefa, to samo zdarzenie

Źródło: `step1_summary.json`, `step1_same_event_printable.json`
(`step1_shapes.py`, `step1_dup_printable.py`). "Dup" = wektor wyniku na
ścieżkach `leg_identity._STATES` równy wektorowi wiersza, który dziś MOŻE się
wydrukować (1X2 / DC OVER, liczniki goli obu kierunków, rynki wyniku OVER,
klucze symulatora: dwustronne oba kierunki, reszta OVER).

| kandydat (nazwa Superbetu) | mecze | śr. / dzień | marża med. [p10, p90] | strefa nowa | strefa dup | uwagi |
|---|---|---|---|---|---|---|
| "{drużyna} wygra obie połowy" tak/nie | 2 142 | 153 | 1,082 [1,048; 1,088] | 1 122 (1 118 "nie") | 0 | nowe zdarzenie |
| "Remis w obu połowach" tak/nie | 548 | 39 | 1,085 | 390 ("nie") | 0 | "tak" = HT/FT X/X (czytany) |
| "Obie drużyny strzelą gola & powyżej L gola" | 4 092 | 292 | 1,086 | 618 (616 "nie") | 0 | tylko L 2,5 / 3,5 w ofercie |
| "1.połowa - handicap" | 850 | 61 | 1,094 [1,070; 1,099] | 1 061 | 3 | linie ±0,5 / ±1,5 / ±2,5 (±3,5 rzadko); -0,5 = `result_1h` |
| "2.połowa - handicap" | 850 | 61 | 1,095 [1,071; 1,099] | 1 124 | 17 | jw., -0,5 = `result_2h` |
| "1./2.połowa - zakład bez remisu" | 548 | 39 | 1,094 | 136 / 124 | - | warunkowy (zwrot przy remisie połowy), brak klucza |
| "Handicap" (reszta nieczytana) | 2 160 | 154 | 1,114 | 40 | 1 158 | ±0,5 = 1X2 / DC; 1,5-3,5 już mapowane (`result_handicap`); ±4,5+ |
| "Handicap 1X2" (europejski, "(0:1)") | 548 | 39 | 1,125 (3 wyniki) | 19 | 896 | strony = `result_handicap` +L / DC; remis = dokładna przewaga |
| "{drużyna} wygra przynajmniej jedną połowę" | 128 | 9 | 1,086 | 55 | 0 | mały wolumen |

Dokładne kształty: handicap połowy to azjatycki połówkowy 2-drogowy, liczony
na golach SAMEJ połowy (para "A (-L)" / "B (+L)", `specialBetValue` = linia
gospodarza); handicap pełnego meczu ("Handicap") - ten sam kształt na całym
meczu; "Handicap 1X2" - europejski 3-drogowy z wynikiem startowym "(x:y)"
(`specialBetValue` "0:1", "1:0", "0:2", "2:0", "0:3", ...).

Wszystkie nogi, które przeszły bramki (sekcja 3), handicapu połowy są stroną
**+L** (1H: 578 / 347 / 28 / 1 na +0,5 / +1,5 / +2,5 / +3,5; 2H: 498 / 451 /
72 / 2 / 1) - strona -L nigdy nie jest w strefie, więc wystarczy wiersz OVER
strony +L, a strona -L jest tylko ceną do marży (konwencja `result_handicap`).
Strona +0,5 połowy = podwójna szansa połowy (rynek "1.połowa - podwójna
szansa" Superbet daje jednostronnie; nie czytać obu - to samo zdarzenie).

## 2. Ocena (bez incydentów)

Każdy kandydat to zdarzenie na (wynik do przerwy, wynik 90 min) - żadnej
kolejności goli. Pokrycie na meczach oferowanych 11-06..11-19
(`step2_coverage.json`, `live_grades.json`):

- mecze: 3 889 OK + 78 po dogrywce (oceniane na `normaltime`) z 4 093 =
  **96,9%**; reszta: 64 "notstarted" w cache (nieodświeżony detal, nie
  odmowa reguły), 28 NO_HALF_TIME_SCORE, 16 HALF_TIME_DISAGREES, 12
  przełożone, 3 INTERNAL_INCONSISTENT, 1 w trakcie, 1 przyznany, 1 odwołany;
- selekcje (bez braku centrum): handicap 1H 7 673 / 7 863 (97,6%), 2H 7 976 /
  8 173 (97,6%), "wygra obie połowy" 7 902 / 8 128 (97,2%), "remis w obu"
  96,7%, BTTS & powyżej 97,0%; zakład bez remisu: 1H 642 ocenione + 416
  zwrotów, 2H 724 + 334.

**Sprawdzenie (drugą drogą):** mój odczyt (HT, 90 min) wobec wierszy, które
SETTLE już rozliczył dla kluczy symulatora 11-06..11-19 (`sofa_settled_row`
htft / result_1h / result_2h / team_scores_both_halves / btts_halves):
**42 969 zgodnych, 3 niezgodne** - wszystkie trzy to jeden mecz (16604736,
rozliczony 11-16 przy 1-0, cache dziś 1-1: wynik zmieniony po rozliczeniu -
sprawa resettle, nie reguły); 132 wiersze SETTLE ocenił, a ja dziś odmawiam
HALF_TIME_DISAGREES (`check_grades_and_p.py`).

## 3. Model kontra cena na żywo 11-06..11-19

`step3_results.json` (`step3_analyse.py`), `step3c_results.json`
(`step3c_lineev.py`).

**Sprawdzenia modelu (drugą drogą):**
1. Centra: moje (walk-forward) vs notatki żywego SHEET (`05_sheet.json`, które
   przetrwały: 11-09 / 16 / 18 / 19, wiersze `team_scores_both_halves`, klucz
   bez schedule term): mediana |różnicy względnej| 3,4% / 5,0% / 3,0% / 1,9%,
   średnia ze znakiem +1,0 / +2,6 / -0,3 / -1,4% (`check_centres.py`). Nie
   identyczne (żywy SHEET czyta inny stan historii - "sheet lag" i flagi dnia).
2. p "remis w obu połowach: tak" (moje) vs `p_central` HT/FT X/X żywego SHEET
   (to samo zdarzenie): 11-06..08 n 310, mediana |różnicy| 0,0027, korelacja
   0,990; 11-09..19 n 180 (żywy z schedule term), 0,0040, 0,980.
3. Strefa "wygra obie połowy: nie" policzona od zera z surowych plików (bez
   `template_of` i parsera): 3 850 par, 1 119 w strefie, marża med. 1,0816 -
   vs 3 847 grup / 1 118 / 1,0816 w kroku 1 (`check_zone_independent.py`).

**Brier / log-loss** (jeden wiersz na grupę: strona z wyższym p bez marży,
wybrana przed wynikiem; symulator - cena; > 0 = symulator gorszy):

| kandydat | wiersze / mecze | Brier sym / cena | ΔBrier [95%] | Δlog-loss [95%] | ΔBrier vs de-vig potęgowy |
|---|---|---|---|---|---|
| handicap 1H | 3 432 / 798 | 0,1316 / 0,1275 | +0,0041 [+0,0017; +0,0065] | +0,0095 [+0,0015; +0,0177] | +0,0055 [+0,0030; +0,0079] |
| handicap 2H | 3 721 / 798 | 0,1382 / 0,1351 | +0,0031 [+0,0007; +0,0058] | +0,0058 [-0,0014; +0,0137] | +0,0041 [+0,0015; +0,0069] |
| wygra obie połowy | 3 654 / 2 031 | 0,1039 / 0,0996 | +0,0044 [+0,0025; +0,0062] | +0,0173 [+0,0108; +0,0238] | +0,0046 [+0,0028; +0,0064] |
| remis w obu połowach | 504 / 504 | 0,1079 / 0,1071 | +0,0009 [-0,0017; +0,0038] | +0,0034 [-0,0067; +0,0149] | +0,0029 [+0,0005; +0,0052] |
| BTTS & powyżej L | 4 713 / 3 915 | 0,2364 / 0,2312 | +0,0051 [+0,0028; +0,0075] | +0,0119 [+0,0064; +0,0172] | +0,0051 [+0,0028; +0,0076] |
| zakład bez remisu 1H | 299 | 0,2217 / 0,2043 | +0,0174 [+0,0076; +0,0274] | +0,0383 | - |
| zakład bez remisu 2H | 345 | 0,2089 / 0,2004 | +0,0085 [-0,0010; +0,0180] | +0,0196 | - |
| wygra przynajmniej 1 połowę | 256 / 128 | 0,2152 / 0,2122 | +0,0030 [-0,0074; +0,0133] | +0,0052 | - |
| Handicap (reszta) | 3 844 / 2 048 | 0,2156 / 0,2025 | +0,0130 [+0,0096; +0,0166] | +0,0302 | - |
| Handicap 1X2 | 2 471 / 504 | 0,1659 / 0,1612 | +0,0047 [-0,0004; +0,0100] | +0,0127 | - |

**Kalibracja surowego p symulatora na żywo** (obie strony, bez duplikatów;
trafione - deklarowane, pp):

| kandydat | 0,60-0,70 | 0,70-0,80 | 0,80-0,92 |
|---|---|---|---|
| handicap 1H | n 459: +0,2 [-3,8; +4,6] | n 639: +0,3 [-2,9; +3,6] | n 1 030: +2,2 [+0,4; +3,9] |
| handicap 2H | n 501: -2,7 [-6,5; +0,9] | n 660: +2,9 [-0,1; +5,9] | n 1 175: +1,2 [-0,6; +2,9] |
| wygra obie połowy | n 155: -3,6 [-11,3; +3,9] | n 428: +7,9 [+4,4; +11,4] | n 1 785: +0,0 [-1,5; +1,5] |
| remis w obu połowach | n 1 | n 43: +10,7 [+1,1; +19,8] | n 440: +1,3 [-1,7; +4,3] |
| BTTS & powyżej L | n 1 563: -3,0 [-5,6; -0,6] | n 729: -6,3 [-9,7; -2,9] | n 263: -8,3 [-13,4; -3,4] |

Ta sama tabela dla p bez marży (cena): handicap 1H +2,0 / +3,9 / +5,6, 2H +1,7
/ +4,6 / +4,6 - de-vig proporcjonalny zaniża faworyta (zwykły błąd metody), więc
"trafione - cena bez marży" > 0 nie jest przewagą; liczy się ROI przy kursie.

**Bramki** (pewność >= 0,70, pewność x kurs >= 0,90, marża <= 15%, kurs >=
1/0,9202, bez duplikatów; wszystkie ocenione nogi 11-06..11-19). Trzy warianty
pewności: A = surowe p; B = krzywa historii (sekcja 4, realised_lo95 kubełka
EDGES, n >= 100, jak `fit_football_sim_curves.py`); C = B + dzisiejszy
pulowany offset line evidence piłki wg d = krzywa - 1/kurs (to, co czyta klucz
bez własnych linii: `sport_printable_by_gap`, `config/sofa_superbet_line_evidence.json`
z 11-20), **bez** capu pasma ceny.

| kandydat | wariant | nogi (śr. / dzień) | pewność | trafione | 1/kurs | trafione - pewność [95%] | ROI [95%] | ROI po podatku |
|---|---|---|---|---|---|---|---|---|
| handicap 1H | A | 940 (67) | 0,806 | 0,769 | 0,816 | -3,7 [-6,4; -1,0] | -6,1 [-9,4; -2,7] | -17,4 |
| handicap 1H | B | 894 (64) | 0,802 | 0,771 | 0,814 | -3,1 [-6,0; -0,5] | -5,7 [-9,3; -2,2] | -17,0 |
| handicap 1H | C | 780 (56) | 0,784 | 0,795 | 0,833 | +1,1 [-1,8; +3,7] | -4,8 [-8,1; -1,5] | -16,2 |
| handicap 2H | A | 1 010 (72) | 0,811 | 0,797 | 0,818 | -1,4 [-3,9; +1,1] | -2,5 [-5,7; +0,7] | -14,2 |
| handicap 2H | B | 906 (65) | 0,801 | 0,790 | 0,813 | -1,1 [-3,7; +1,5] | -2,7 [-5,9; +0,8] | -14,3 |
| handicap 2H | C | 701 (50) | 0,795 | 0,817 | 0,846 | +2,2 [-0,5; +5,0] | -3,4 [-6,7; -0,1] | -15,0 |
| wygra obie połowy | A | 985 (70) | 0,840 | 0,789 | 0,835 | -5,1 [-7,7; -2,4] | -5,1 [-8,2; -2,0] | -16,5 |
| wygra obie połowy | B | 923 (66) | 0,836 | 0,783 | 0,832 | -5,3 [-7,9; -2,6] | -5,3 [-8,7; -2,0] | -16,7 |
| wygra obie połowy | C | 798 (57) | 0,811 | 0,796 | 0,855 | -1,5 [-4,5; +1,2] | -6,9 [-10,3; -3,6] | -18,1 |
| remis w obu połowach | B | 337 (24) | 0,844 | 0,861 | 0,888 | +1,6 [-2,3; +5,2] | -3,0 [-7,1; +1,0] | -14,6 |
| remis w obu połowach | C | 337 (24) | 0,834 | 0,861 | 0,888 | +2,7 [-1,1; +6,2] | -3,0 [-7,6; +1,1] | -14,6 |
| BTTS & powyżej L | B | 814 (58) | 0,750 | 0,688 | 0,740 | -6,2 [-9,6; -3,1] | -7,1 [-11,8; -2,4] | -18,3 |
| BTTS & powyżej L | C | 345 (25) | 0,755 | 0,765 | 0,802 | +1,0 [-3,6; +5,3] | -4,5 [-10,6; +0,9] | -16,0 |
| zakład bez remisu 1H | B | 30 (10 zwrotów) | | | | -7,3 [-29; +12] | -14,4 | |
| zakład bez remisu 2H | B | 29 (14 zwrotów) | | | | +3,5 [-17; +22] | +3,9 | |
| wygra przynajmniej 1 poł. | B | 22 | | | | +3,1 [-15; +20] | +4,0 | |
| Handicap / Handicap 1X2 | B | 0 | | | | | | |

Wolumen jest skupiony w weekendy (handicap 2H B: 11-07 228, 11-08 233, 11-14
98, 11-15 38; dni robocze 13-38); 11-09..11-17 to przerwa reprezentacyjna.

## 4. Historia (na tym byłaby dopasowana krzywa) - 2026-06-01..10-20

`step4_results.json` (`step4_analyse.py`); klucze jak krzywe: `<rynek>|tak/nie`
albo `<rynek>|OVER` (strony i linie razem); trafione - deklarowane w pp.

| klucz | wiersze | 0,60-0,70 | 0,70-0,80 | 0,80-0,92 | 0,92+ |
|---|---|---|---|---|---|
| handicap 1H \|OVER (+L) | 240 150 | +0,8 [+0,3; +1,4] | -0,2 [-0,6; +0,3] | +0,1 [-0,1; +0,4] | -0,1 [-0,2; +0,0] |
| handicap 2H \|OVER (+L) | 240 150 | -0,0 [-0,5; +0,5] | -0,6 [-1,1; -0,2] | -0,8 [-1,0; -0,5] | -0,5 [-0,7; -0,4] |
| wygra obie połowy \|nie | 80 050 | +1,6 [-0,1; +3,2] | +0,5 [-0,5; +1,6] | +0,2 [-0,1; +0,5] | -0,4 [-0,7; -0,2] |
| remis w obu połowach \|nie | 40 025 | +2,0 (n 202) | +2,7 [+1,4; +4,0] | -0,2 [-0,6; +0,1] | -1,1 [-1,9; -0,3] |
| BTTS & powyżej L \|nie | 120 075 | +0,5 [-0,1; +1,0] | -1,2 [-1,7; -0,7] | -2,8 [-3,2; -2,3] | -3,3 [-4,1; -2,6] |
| BTTS & powyżej L \|tak | 120 075 | -8,7 | -14,4 | -21,2 | - |
| gol w obu połowach \|tak | 40 025 | -0,9 | -3,5 [-4,7; -2,4] | -5,5 [-7,7; -3,6] | +2,5 (n 58) |
| zakład bez remisu 1H | 48 418 | -1,0 | -0,9 | -0,9 | -4,3 |
| zakład bez remisu 2H | 54 078 | -1,2 | -2,3 [-3,4; -1,1] | -1,7 | -0,6 |

Handicap połowy na linię (p 0,70-0,95): 1H +0,5 -0,2 pp [-0,6; +0,1] (n
41 668), +1,5 +0,1 [-0,2; +0,3] (57 722), +2,5 +0,4 [-0,1; +0,9] (12 053);
2H +0,5 **-1,6 [-2,0; -1,2]** (35 399), +1,5 -0,5 [-0,8; -0,3] (62 476), +2,5
+0,5 [+0,1; +0,8] (21 222). Kobiety >= 0,70: 1H 0,910 deklarowane / 0,896
trafione, 2H 0,903 / 0,893 (klasa `women` potrzebna jak dla dzisiejszych
kluczy). Krzywa z realised_lo95 kubełka i tak wchłania te -0,5..-1,6 pp.

Wniosek historii: surowe p symulatora jest dla handicapu połowy i "wygra obie
połowy: nie" dobrze skalibrowane - na tym da się dopasować krzywą. Na żywo
wydrukowane nogi spadają poniżej krzywej (B) tam, gdzie bramka x >= 0,90 wybiera
mecze, w których model rozjeżdża się z ceną, a cena jest lepsza (Brier) -
najmocniej "wygra obie połowy" (-5,3 pp), najsłabiej handicap 2H (-1,1 pp).
Pulowany offset line evidence (C) tę selekcję koryguje.

## 5. Ranking i wybór

| kandydat | drukowalne / dzień (B) | kalibracja historii | na żywo B | vs cena | wysiłek |
|---|---|---|---|---|---|
| **handicap 1H + 2H** | 64 + 65 | bardzo dobra (1H), dobra (2H; +0,5 -1,6 pp) | -3,1 / -1,1 pp | gorszy (ΔBrier +0,003..+0,004) | mały: jeden kształt dla 2 połów, ocena z HT/FT, symulator ma gole per połowa |
| "wygra obie połowy: nie" | 66 | dobra | -5,3 pp | gorszy | mały |
| "remis w obu połowach: nie" | 24 | dobra (0,80-0,92) | +1,6 pp | remis / gorszy | mały, ale "tak" = HT/FT X/X (nie drukować) |
| BTTS & powyżej L "nie" | 58 | nad-obietnica | -6,2 pp | gorszy | mały - odpada |
| zakład bez remisu połowy | 2 | -1..-2 pp | n < 30 | gorszy (1H) | warunkowy, zwroty - odpada |
| Handicap / Handicap 1X2 | 0 | - | - | - | duplikaty - odpada |

**Wybór: handicap połowy** (`result_1h_handicap`, `result_2h_handicap`).
Dlaczego: największy drukowalny wolumen z kandydatów nie-duplikatów (ok. 130
nóg / dzień obu połów razem w B, w weekend ~450), najlepsza kalibracja w
historii i najmniejsza nad-obietnica wydrukowanych nóg na żywo, ROI najbliżej
zera (2H -2,7% [-5,9; +0,8]); czysta para dwustronna (marża ~9,4%, zawsze
<= 15%), ocena z `period1` i wyniku 90 min - nic z incydentów. Nie jest to
przewaga: cena jest lepsza od symulatora (ΔBrier > 0), po podatku ~-14..-17%.

## 6. Szkic wdrożenia (nie wdrożone)

Zmienia to, co drukuje -> przełącznik w `bet.sofa.epochs` od następnego dnia
00:00Z (operator może przesunąć), nowa grupa księgi.

1. `src/bet/sofa/epochs.py`: `FOOTBALL_SIM_HALF_HANDICAP_FROM_UTC =
   datetime(<D>, 0, 0, tzinfo=UTC)`, `FOOTBALL_SIM_HALF_HANDICAP_MARKETS =
   frozenset({"result_1h_handicap", "result_2h_handicap"})`,
   `football_sim_half_handicap(date, build_at)` (wzór `football_sim`),
   marker `("football_sim_hh_rule", "football_sim_half_handicap_v1",
   "football")`. NIE dopisywać do `FOOTBALL_SIM_MARKETS` (stała z assertem w
   `football_sim_markets`, czytana przez zbudowane dni) - zamiast tego
   `epochs.football_sim_markets(date, build_at)` = bazowe | nowe, gdy włączone.
   Nazwy nie mogą zaczynać się od `handicap_` (`market_mapper.derived_base`
   uznałby je za rynek pochodny SHEET-u z próbek). Poza
   `SCHEDULE_TERM_MARKETS` (egzamin 11-09 ich nie objął) i poza
   `FOOTBALL_SIM_FLOOR_KEYS` (podłoga 0,70).
2. `src/bet/sofa/football_sim_markets.py`: `classify(..., half_handicap=False)`
   - "1.połowa - handicap" / "2.połowa - handicap" (folded `^[12]\.\s?polowa -
   handicap$`), selekcja `"<drużyna> (<±L>)"` dopasowana dokładnie do nazwy
   listingu (`_side`), L w {0,5; 1,5; 2,5}: +L -> (rynek, strona, L, "OVER"),
   -L -> (rynek, druga strona, L, "UNDER") (tylko cena do marży, jak
   `result_handicap`); `valid_subject` / `path_holds` (własne + L > rywala na
   golach połowy: 1H = `period1`, 2H = 90 min - `period1`); `sim_value` z
   rynkiem w `MARKETS | HALF_HANDICAP` (ocena to poprawność - zawsze);
   `path_spec` -> nowy `path_outcomes` kind `"half_handicap"` (param (połowa,
   L)) w `football_sim.py` oraz `path_actual`; `describe`, `superbet_words`
   ("1.połowa - handicap", "<drużyna> (+L)").
3. `src/bet/sofa/offer.py`: `day_flags` + `classify_odd(...,
   football_sim_half_handicap=...)`, wpięte za `football_sim`.
4. `scripts/sofa/run_sheet.py`: wiersze tylko OVER (nie w `SIM_TWO_SIDED`),
   `fss.SimPricer.p` przez `path_spec`; marker na każdym wierszu piłki;
   `src/bet/sofa/rebuild_plan.py`: `offer_has_sim` / marker nowej reguły (re-run
   OFFER / SHEET jak dla `FOOTBALL_SIM_MARKER`).
5. `src/bet/sofa/tennis_winner.py` `RATING_ONLY_MARKETS` += nowe (nigdy w
   builderze); `src/bet/sofa/leg_identity.py` `_football_vector` - gałąź
   nowego rynku (wtedy strona -0,5 ewentualnie wydrukowana = `result_1h`
   OVER, dedupe ją złapie; +0,5 nowe zdarzenie); `superbet_names`.
6. `scripts/sofa/run_settle.py` / `regrade_settled.py`: `_settle_sim_market`
   obsłuży przez `sim_value` (nic więcej, jeśli `MARKETS` w `sim_value`
   obejmie nowe).
7. `src/bet/sofa/football_sim_curves.py`: `_in_scope` / `no_pool` czytają
   `epochs.football_sim_markets(date)` (albo stały zbiór bazowy | nowy, a
   nakładka i tak tylko pod przełącznikiem) - nowe klucze bez puli.
8. Krzywe: `scripts/sofa/fit_football_sim_curves.py` - `subjects()` +=
   `(rynek, "1"/"2", "OVER")` dla L 0,5 / 1,5 / 2,5 (kolumna linii w wierszu -
   dziś `rows_for` zakłada linię 0,5; potrzebny `line` w kluczu wiersza);
   bieg na KOPII bazy (`VACUUM INTO 'data/refit_<D>/sofa.db'`, potem
   `--db-path <kopia>`; sam fit czyta pickle `data/football_sim_2026-11-06/`)
   `--out config/sofa_football_sim_curves.next.<D>.json` = kompletny plik:
   klucze `.next.2026-11-09.json` (z `--schedule-term`, jak dziś) + nowe
   (bez terminu) - czyli dwa biegi scalone albo `--schedule-term` z nowymi
   rynkami w `EXCLUDED`. Install tylko z go operatora.
9. Line evidence: `--backfill-out` z nowymi rynkami na 10-14..dzień przed
   przełącznikiem; `forecasts_live.pkl` kończy się 11-05 - trzeba
   rozszerzyć (jak `live_centres.py` tutaj); osobny plik
   `data/line_evidence/football_sim_half_handicap_lines.jsonl.gz` albo
   regeneracja `football_sim_lines.jsonl.gz` (obecny plik niezmieniony
   bajt w bajt dla starych kluczy). `refresh_line_evidence.py` bez zmian.
10. Testy (`tests/sofa/test_football_sim_half_handicap.py`, offline):
    prawdziwe nazwy z `unmapped_prices` (para "PSIM Yogyakarta (-1.5)" /
    "Dewa United (1.5)" -> jeden szczebel OVER/UNDER), strona po dokładnej
    nazwie, linia całkowita / ±3,5 odrzucona; ocena: gol w doliczonym czasie
    1. połowy w 1H, dogrywka nie liczy się do 2H, odmowy jak
    `test_contradictions_are_refused_never_guessed`; OFFER czyta tylko pod
    przełącznikiem; SHEET: marker, OVER only, NOT_RATED bez centrum;
    `superbet_words` round-trip; `leg_identity`: -0,5 == `result_1h` OVER;
    nakładka krzywych tylko pod przełącznikiem; bramki druku bez zmian;
    `check_test_registry.py`. Bramki commita z CLAUDE.md.
11. Dokumentacja: CLAUDE.md (sekcja symulatora), model-state.md (przełącznik,
    dowód, grupa księgi), `docs/sofa/evidence/football_sim_half_handicap_<D>.md`,
    PIPELINE.md / CONFIG.md po polsku.

Przed włączeniem (reguła "zmierz najpierw"): zamrożona reguła na hold-oucie
(np. 11-20..12-03) wariantu B / C z pełnym łańcuchem (krzywa + line evidence z
backfillu do dnia przed oknem), jak `measure_football_sim_wiring.py`.

## 7. Ryzyka i rzeczy niesprawdzone

- **Brak przewagi:** model gorszy od ceny w każdej rodzinie; ROI wszystkich
  wariantów < 0, po podatku -14..-18%. Nowe nogi to wolumen i kalibracja.
- Centra na żywo to moja powtórka walk-forward (flagi BOOK_DAY 11-06), nie
  liczby żywego SHEET (różnica mediany 2-5%); od 11-09 żywy SHEET mnoży centra
  kluczy ścieżki przez schedule term - tu nie (nowe klucze i tak poza
  terminem).
- Wariant C bez capu pasma ceny (`price_band_cap`) i bez progu
  `MIN_EVIDENCE_*`; offset pulowany z pliku fitted 11-20 (zawiera linie po
  11-06 - lekki przeciek w czasie dla C).
- Krzywe B dopasowane przeze mnie pulą wszystkich klas (bez osobnej klasy
  `women`, bez `MIN_MARKET_BUCKET` 400 - przyjąłem n >= 100); prawdziwy fit może
  dać inne krawędzie.
- Kalibracja na żywo: 14 dni, w tym przerwa reprezentacyjna; mecze z
  handicapem połowy to tylko 850 z ~4 100 (oferta Superbetu, głównie większe
  ligi).
- Regulamin Superbetu dla "1./2.połowa - handicap" (że liczy tylko gole tej
  połowy, 2H bez dogrywki) **nie sprawdzony w tekście regulaminu** - wnioskuję
  z cen (np. 2H "-1.5" po 12,0) i ze zgodności kalibracji z oceną "tylko
  połowa"; to samo dla "Handicap 1X2" (wynik startowy).
- De-vig proporcjonalny zaniża faworyta; wniosek "cena lepsza" sprawdzony też
  de-vigiem potęgowym (ten sam znak).
- 64 mecze z cache w stanie "notstarted" i 132 wiersze SETTLE vs moja odmowa
  HALF_TIME_DISAGREES - nie wyjaśnione per mecz.
- Nieczytane jednostronne ("przedział goli", "1./2.połowa - podwójna szansa",
  "podwójna szansa & liczba goli", przedziały goli połów, "gol w obu
  połowach") nie mierzone tu poza historią "gol w obu połowach" (nad-obietnica
  -3,5..-5,5 pp przy >= 0,70); jednostronne potrzebowałyby własnej krzywej n >=
  300. Rynki kolejności goli (incydenty) pominięte.

## Pliki

Skrypty: `inventory.py`, `cands.py`, `step1_shapes.py`,
`step1_dup_printable.py`, `live_centres.py`, `simcore.py`, `step23_live.py`,
`step4_history.py`, `stats.py`, `step3_analyse.py`, `step3c_lineev.py`,
`step4_analyse.py`, `check_centres.py`, `check_grades_and_p.py`,
`check_zone_independent.py`. Wyniki: `templates.json`, `step1_summary.json`,
`step1_same_event_printable.json`, `step2_coverage.json`, `live_grades.json`,
`live_eval.jsonl.gz`, `step3_results.json`, `step3c_results.json`,
`history_rows.jsonl.gz`, `step4_results.json`, `centres_live_1106_1119.pkl`.
