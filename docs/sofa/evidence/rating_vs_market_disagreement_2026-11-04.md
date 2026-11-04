# Rozjazd ratingu z rynkiem a nogi od niego zależne (pomiar 2026-11-04)

Pomiar tylko do odczytu: żaden kod, konfiguracja, krzywa ani artefakt potoku nie
zostały zmienione. Kod roboczy w scratchpadzie sesji (`extract.py`,
`build_legs.py`, `analyze.py`, `tables.py`, `extra.py`, `robust.py`, `fav.py`) -
nie jest to czysty skrypt `measure_*`, więc nie trafił do `scripts/sofa/`.

## Pytanie operatora

Przypadek 2026-11-04: FC Seoul - Thể Công - Viettel (AFC Champions League Two,
sofa:16864091). Noga „FC Seoul - liczba goli: poniżej 3.5” @1.44, pewność
0,751. Nasz rating widzi drużyny prawie równo, Superbet wycenia Seoul na −2.5
handicap ~1.9-2.0 i wygraną 1.10. Tydzień wcześniej (10-28) Seoul wygrał 5:0 w
Hanoi i takie same nogi UNDER przegrały.

Hipoteza: **gdy nasz rating (oczekiwana różnica goli) mocno rozjeżdża się z
1X2 / handicapem / sumami drużyn Superbetu, nogi zależne od tego obrazu
realizują się poniżej swojej ceny** - rating się myli, nie rynek. Zwłaszcza w
pucharach międzyligowych.

## Werdykt

**Brak sygnału względem ceny; wyraźny i spójny sygnał względem pewności.**

- Nogi zależne od obrazu meczu realizują się przy wysokim rozjeździe **tak samo
  względem ceny jak wszędzie** (tracą zwykłą marżę, ok. −6 pp). Cała drabina:
  D ≥ 1,0 minus D w −0,5..0,5 = **+0,3 pp [−2,2; +3,1]** (10 130 meczów).
  Wydrukowane nogi zależne: dev (do 10-24) −6,1 pp [−11,7; −0,3], **hold-out
  (od 10-25) +1,8 pp [−4,3; +7,5]** - reguła z dev nie powtarza się.
- Te same nogi realizują się **poniżej swojej pewności**: wydrukowane zależne
  D ≥ 1,0 −8,6 pp [−13,0; −4,7] względem pasma środkowego; najwyższy decyl D
  dev −9,6 pp [−13,9; −5,6], hold-out −5,7 pp [−10,5; −1,0]. Nogi „zgodne z
  rynkiem” (faworyt OVER, faworyt wygra) realizują się przy D ≥ 1 o +16 pp
  **powyżej** pewności (cała drabina). To jest obraz „rating się myli, rynek ma
  rację”: wynik idzie za ceną, a nasza liczba za ratingiem.
- Wniosek dla pieniędzy: odrzucenie takich nóg **nie poprawiłoby ROI** (ROI
  D ≥ 1 minus środek, wydrukowane zależne: −3,6 pp [−9,3; +1,8]); to problem
  kalibracji wydrukowanej pewności (zawyżona liczba), nie selekcji. To ten sam
  mechanizm, który już zmierzono jako `price_gap` (`T-PRICE-GAP-flag`: −10,0 pp
  względem pewności na 2 111 nogach, realizacja ok. przy cenie).
- Puchary kontynentalne: sygnał względem ceny widać tylko na garstce meczów
  (hold-out cała drabina, D ≥ 1: 14 meczów, −16,8 pp [−29,6; −3,8]; wydrukowane
  10 meczów, −16,6 pp [−44,3; +7,9]). **Podejrzenie**, nie pomiar. Puchary
  krajowe idą w przeciwną stronę (wydrukowane +7,6 pp [−0,6; +16,3]).
- Dokładnie noga typu Seoul (faworyt - liczba goli poniżej, wydrukowana, D ≥ 1):
  dev 48 nóg / 43 mecze −23,6 pp względem 1/kurs [−38,4; −7,9]; **hold-out 39 /
  35: +1,2 pp [−12,3; +12,7]**. Wynik z dev się nie utrzymał.

## Co już było zmierzone (nie powtarzane)

- Rozjazd model − cena per wiersz jako bramka: anty-sygnał na 88 095 wierszach
  (2026-09-21); „blending the price into confidence or gating on disagreement
  with it” - odrzucone (`model-state.md`, sekcja „measured and declined”).
  Ten pomiar jest inny: rozjazd **na poziomie meczu** (oczekiwana różnica
  goli), a pytanie dotyczy nóg, które od tego obrazu zależą.
- `price_gap` / `CONFIDENCE_ABOVE_PRICE` (10-19): nogi z pewnością > 1/kurs +
  0,03 realizują się ok. przy cenie, −10 pp względem pewności - adnotacja.
- `FOOTBALL_CUP_STRENGTH` (10-16): 3 740 międzyligowych meczów pucharowych
  zaniżało stronę mocniejszej ligi o +5,2 pp P(wygranej); poprawka działa od
  10-16.
- Remisy pucharowe przy dużej różnicy poziomów (10-29): na historii rating jest
  przy największych różnicach **zbyt stromy**, nie zbyt płaski (margines przy
  s ≥ 2: −0,46 [−0,58; −0,33]); shrink pucharowy niezwłączony. Tam porównanie
  było z wynikiem, tu z ceną Superbetu.

## Metoda

**Dane.** Dni 2026-09-24..2026-11-03 (wydrukowane od 2026-10-05). Wiersze
piłkarskie z ceną z `sofa_settled_row` (`data/sofa.db`, tylko odczyt,
`offered_odds` nie null, wynik WIN / LOSS): 1 470 168 wierszy, z tego 890 849 w
meczach z oboma widokami i w grupach poniżej. Pewność całej drabiny:
`08_refusals.json` (istnieje od 10-21; tylko mecze nierozpoczęte w chwili
ostatniej przebudowy dnia - wybór po godzinie startu) i `08_confidence.json`.
Pewność nóg wydrukowanych: `11_coupon.json` `singles` (dokładnie wydrukowana
liczba). „Wydrukowane” = piłkarskie `singles` w `11_coupon.json` (77 795 nóg,
8 223 mecze).

**Nasz widok.** Czyste centra ratingu gospodarzy i gości z noty
`FOOTBALL_RATING` wiersza `goals_total` w `05_sheet.json` („home X + away Y”;
13 850 meczów; 70 z noty wyniku). Wariant kontrolny: końcowe centra wierszy
`goals_for` (po wadze ratingu, rozciągnięciu itd.).

**Widok rynku.** Ostatni zapisany snapshot `04_offer.json` (uwaga: może być
późniejszy niż druk). Każdy szczebel dwustronny odwiedzony proporcjonalnie
(1/over : 1/under). Do (λ_gosp, λ_gość) dopasowane dwa niezależne rozkłady NB
(r = 7,586, jak `FOOTBALL_RESULT_NB_R`) minimalizujące sumę kwadratów błędów
prawdopodobieństw: 1X2 „1” i „2”, podwójna szansa „12” (= brak remisu), linie
`goals_for` obu drużyn, linie `goals_total`; siatka 0,05..5,0 co 0,025. Mecz
wchodzi, gdy ma 1X2 (1 i 2) albo oba `goals_for`. RMSE dopasowania: mediana
0,013, p99 0,026. 10 416 meczów z oboma widokami (10 132 z rozliczonymi nogami).

**Rozjazd.** Faworyt = strona z wyższym λ rynku.
D = (λ_fav − λ_dog)_rynek − (μ_fav − μ_dog)_nasz. D > 0: rynek widzi faworyta
mocniejszego niż my. Koszyki ustalone przed obejrzeniem wyników: < −0,5;
−0,5..0,5; 0,5..1,0; 1,0..1,5; ≥ 1,5 gola. Rozkład D na meczach: mediana +0,14,
p95 +1,07, p99 +1,84; liga p95 +0,94, puchary krajowe +1,92, kontynentalne +1,80.

**Grupy nóg.**
- ZALEŻNE: `goals_for` faworyta UNDER; `goals_for` słabszego OVER; „wynik
  słabszego” (1X2 słabszego lub remis, podwójna szansa słabszy+X, DNB słabszy,
  `result_handicap` słabszy +L); „słabszy/remis lub poniżej” (`result_or_under`
  z podmiotem słabszy lub X, `dc_and_under` 1X gdy gospodarz jest słabszy).
- ZGODNE Z RYNKIEM: `goals_for` faworyta OVER, słabszego UNDER, wynik
  faworyta, `result_or_over` faworyta.
- Osobno: `goals_total` UNDER / OVER, połowy, kontrola nie-golowa (rożne,
  kartki, strzały, faule, spalone...).

**Miary.** trafione − średnie 1/kurs (kalibracja względem ceny; zawiera marżę),
ROI płaskiej stawki przy cenie, trafione − pewność. 95% CI: bootstrap po
meczach (1 000 losowań; nogi jednego meczu nie są niezależne). Różnica
koszyków: niezależny bootstrap meczów w obu koszykach.

**Dev / hold-out.** Reguła „D ≥ 1,0, grupa ZALEŻNE” ustalona z góry (próg z
pytania), oceniona osobno na dev (dni ≤ 2026-10-24) i hold-out (≥ 2026-10-25).
Hold-out jest cienki: w koszyku D ≥ 1 ma 202 wydrukowane mecze (dev 229).

**Grupy epok.** Dni obejmują ok. 20 grup `audit_ledger.EPOCH_GROUPS` (od
„stats_only” 10-05 po „od 11-03”) - **zsumowane**, wbrew zwyczajowi księgi.
Miara względem ceny jest na to mało czuła (cena nie zależy od naszej epoki);
miara względem pewności - bardziej (krzywe, offset line evidence od 10-30).

## Wyniki

### 1. Cała drabina, grupa ZALEŻNE (n nóg / meczów; źródło `sofa_settled_row` × `05_sheet` × `04_offer`)

| D | nóg | meczów | trafione | śr. 1/kurs | trafione − 1/kurs, pp | ROI % | trafione − pewność, pp (n) |
|---|---|---|---|---|---|---|---|
| < −0,5 | 11 777 | 828 | 0,522 | 0,592 | −7,0 [−8,9; −5,0] | −14,1 [−18,2; −9,8] | +8,0 [+3,9; +12,6] (2 358) |
| −0,5..0,5 | 105 251 | 7 075 | 0,521 | 0,580 | −6,0 [−6,7; −5,3] | −13,4 [−14,8; −11,9] | +2,4 [+1,2; +3,6] (26 562) |
| 0,5..1,0 | 24 076 | 1 612 | 0,481 | 0,543 | −6,2 [−7,6; −4,8] | −15,2 [−18,5; −11,9] | −3,3 [−5,6; −0,6] (6 462) |
| 1,0..1,5 | 6 002 | 416 | 0,425 | 0,503 | −7,8 [−10,8; −5,0] | −19,4 [−26,8; −11,1] | −6,3 [−11,7; −1,4] (1 456) |
| ≥ 1,5 | 3 116 | 199 | 0,435 | 0,451 | −1,6 [−5,5; +2,5] | −8,4 [−20,1; +4,6] | −0,9 [−11,2; +9,1] (670) |

D ≥ 1,0 minus −0,5..0,5: względem 1/kurs **+0,3 [−2,2; +3,1]**; ROI −2,2
[−8,5; +4,6]; względem pewności **−7,0 [−11,7; −2,2]**.
Dev: względem 1/kurs −0,5 [−3,5; +2,6], pewność −12,1 [−19,1; −6,1].
Hold-out: względem 1/kurs +1,3 [−2,5; +5,0], pewność −3,3 [−10,3; +3,4].
Nachylenie (trafione − 1/kurs) na 1 gol D: dev +0,1 pp [−1,2; +1,6], hold-out
+0,7 [−0,8; +2,2].

ZGODNE Z RYNKIEM (98 266 nóg): D ≥ 1 minus środek względem 1/kurs −0,3 [−2,4;
+2,0], względem pewności **+16,1 [+8,7; +23,0]** (pewność zaniżona tam, gdzie
rynek widzi faworyta mocniej).

Kontrola nie-golowa (296 163 nóg, obie strony drabiny): −4,5..−4,6 pp względem
1/kurs w każdym koszyku - tło marży, bez zależności od D.

### 2. Wydrukowane nogi ZALEŻNE (źródło `11_coupon.json` singles × `sofa_settled_row`)

| D | nóg | meczów | trafione | śr. 1/kurs | trafione − 1/kurs, pp | ROI % | trafione − pewność, pp |
|---|---|---|---|---|---|---|---|
| < −0,5 | 219 | 124 | 0,767 | 0,850 | −8,3 [−15,1; −1,6] | −9,6 [−18,3; −1,3] | −2,0 [−9,5; +4,2] |
| −0,5..0,5 | 11 015 | 4 201 | 0,782 | 0,836 | −5,3 [−6,4; −4,2] | −6,4 [−7,8; −5,0] | −1,4 [−2,5; −0,4] |
| 0,5..1,0 | 3 421 | 1 143 | 0,764 | 0,817 | −5,3 [−7,2; −3,3] | −6,5 [−9,4; −3,7] | −4,5 [−6,7; −2,5] |
| 1,0..1,5 | 716 | 262 | 0,703 | 0,805 | −10,2 [−15,2; −5,6] | −12,9 [−20,1; −6,8] | −11,5 [−16,2; −7,2] |
| ≥ 1,5 | 247 | 98 | 0,769 | 0,781 | −1,2 [−8,4; +5,6] | −1,4 [−11,6; +8,0] | −5,9 [−13,7; +1,0] |

| D ≥ 1,0 minus −0,5..0,5 | względem 1/kurs, pp | ROI, pp | względem pewności, pp |
|---|---|---|---|
| wszystkie dni (963 nogi / 360 meczów w D ≥ 1) | −2,6 [−7,1; +1,5] | −3,6 [−9,3; +1,8] | −8,6 [−13,0; −4,7] |
| dev ≤ 10-24 | **−6,1 [−11,7; −0,3]** | −8,3 [−15,9; −0,4] | −12,9 [−18,8; −6,9] |
| hold-out ≥ 10-25 | **+1,8 [−4,3; +7,5]** | +2,3 [−5,3; +10,2] | −3,4 [−9,3; +2,6] |
| liga | −6,8 [−12,3; −1,9] | −9,0 [−15,9; −2,7] | −11,8 [−16,9; −6,5] |
| puchar krajowy | +7,6 [−0,6; +16,3] | +10,6 [−0,0; +20,5] | −0,3 [−8,4; +7,7] |
| kontynentalny | −7,6 [−23,4; +8,5] | −12,5 [−34,0; +8,7] | −17,2 [−33,8; +0,3] |

Uwaga: koszyk 1,0..1,5 jest słaby, a ≥ 1,5 - nie; brak monotoniczności.
Nachylenie na 1 gol D (wydrukowane zależne): dev −1,6 pp [−4,6; +1,3], hold-out
+0,8 [−2,1; +3,8].

Decyle D (wydrukowane zależne; progi 0,04 / 0,275 / 0,545 / 0,825), górne 10%:
dev 963 nogi / 316 meczów: względem 1/kurs −6,6 [−10,7; −2,4], pewność −9,6
[−13,9; −5,6]; hold-out 618 / 253: −6,5 [−11,0; −2,2], pewność −5,7 [−10,5;
−1,0]. Dolny kwartyl: dev −5,0 / −0,3, hold-out −7,3 / −1,4. Względem ceny
górny decyl nie odstaje od dolnego kwartyla (tło marży); względem pewności -
odstaje w obu połowach.

Wariant z końcowymi centrami `goals_for` zamiast czystego ratingu (D ≥ 1:
602 nogi / 208 meczów): względem 1/kurs +1,5 [−3,8; +6,6]; pewność −5,2
[−10,3; −0,4]; dev 0,0 / −8,0, hold-out +3,4 / −2,4.

### 3. Pojedyncze grupy wydrukowane (D ≥ 1 minus środek)

| grupa | względem 1/kurs, pp | względem pewności, pp |
|---|---|---|
| faworyt - liczba goli poniżej | −8,4 [−19,5; +2,8] | −17,0 [−27,7; −5,1] |
| słabszy lub remis / lub poniżej | −2,8 [−7,7; +2,0] | −7,5 [−12,1; −2,9] |
| wynik słabszego | +2,3 [−6,0; +10,2] | −8,1 [−16,5; +0,5] |
| słabszy - liczba goli powyżej | −5,2 [−19,6; +10,3] | −12,8 [−29,3; +2,6] |
| mecz - liczba goli poniżej | +0,1 [−6,8; +6,9] | −2,4 [−9,7; +4,4] |

Faworyt - liczba goli poniżej, wydrukowane, D ≥ 1:

| | nóg / meczów | trafione | śr. 1/kurs | trafione − 1/kurs, pp | trafione − pewność, pp |
|---|---|---|---|---|---|
| dev | 48 / 43 | 0,500 | 0,736 | −23,6 [−38,4; −7,9] | −32,8 [−48,7; −17,1] |
| hold-out | 39 / 35 | 0,795 | 0,783 | +1,2 [−12,3; +12,7] | −0,6 [−14,5; +11,9] |

### 4. Związek z `price_gap`

Wydrukowane zależne z pewnością > 1/kurs + 0,03 (1 690 nóg): D ≥ 1 (396 / 204
mecze) −9,2 pp względem 1/kurs, −18,3 względem pewności; środek (507 / 332)
−5,5 / −11,1; różnica −3,7 [−11,5; +3,8] / −7,2 [−14,8; +0,8]. Bez
`price_gap` (13 928): różnica −1,7 [−6,8; +2,9] / −3,4 [−7,8; +0,9]. D niesie
mniej więcej to samo co `price_gap`; ewentualna nadwyżka mieści się w szumie.

### 5. Jak często

Wydrukowane piłkarskie 10-05..11-03: 3 200 z 77 795 nóg (4,1%) w 431 z 8 223
meczów ma D ≥ 1; zależne: 963 z 15 618 (6,2%), średnio ~32 nogi dziennie
(maks. 175 na 10-17). Klasy: liga 623, puchar krajowy 255, kontynentalny 85.

### 6. Przypadki Seoul - Viettel

- **2026-10-28** (sofa:16864128, Viettel gospodarzem, wynik 0:5): rynek λ
  Viettel 1,05 / Seoul 1,90 (Seoul +0,85); nasz rating Viettel 1,63 / Seoul
  1,01 (Viettel +0,62); **D = +1,47** (koszyk 1,0..1,5, puchar
  kontynentalny). Wydrukowane i przegrane zależne nogi: FC Seoul poniżej 2.5
  @1,41 (pewność 0,896), Viettel powyżej 0.5 @1,53 (0,708), „1 lub poniżej
  3.5” @1,34 (0,865), „X lub poniżej 3.5” @1,31 (0,748), „X lub poniżej 4.5”
  @1,13 (0,843), mecz poniżej 4.5 @1,14 (0,840). Wygrały dwie nogi „lub
  powyżej 1.5”. Pojedynczy mecz - ilustracja, nie dowód. (Uwaga sesji
  głównej: końcowy `11_coupon.json` z 10-28 ma inne kursy tych nóg - np.
  FC Seoul poniżej 2.5 @1,29, Viettel powyżej 0.5 @1,57, „1 lub poniżej
  3.5” @1,27; pewności te same. Kursy powyżej pochodzą z innej migawki;
  na wniosek pomiaru to nie wpływa.)
- **2026-11-04** (sofa:16864091, Seoul gospodarzem; nierozliczony): rynek
  Seoul 3,10 / Viettel 0,58 (+2,53); nasz rating 1,58 / 1,13 (+0,45);
  **D = +2,08** (koszyk ≥ 1,5). W tym koszyku wydrukowane zależne nogi
  realizowały się przy cenie (−1,2 pp [−8,4; +5,6], 247 nóg / 98 meczów) i
  5,9 pp poniżej pewności [−13,7; +1,0].

## Jak wyglądałby przełącznik (gdyby sygnał się utrzymał)

Pomiar nie uzasadnia odrzucania nóg: względem ceny nic nie odstaje poza dev.
To, co stoi - zawyżona pewność przy dużym D - jest kalibracją:
1. **Adnotacja** (jak `price_gap`): „rating vs rynek: D = +2,1 gola” na nodze
   zależnej, bez bramki. Najbliższe temu, co mierzy ten raport.
2. **Podstawa WATCH dla analityka** (jak `RYNEK:`): tylko po pomiarze poza
   próbą tagu w księdze; dziś wynik na hold-out względem ceny jest zerowy.
3. **Obniżenie pewności w stronę ceny** dla nóg zależnych przy D ≥ 1 -
   to wmieszanie ceny w pewność, wprost odrzucone przez operatora
   („blending the price into confidence”); kalibracja zrobiłaby się lepsza,
   ROI nie (nogi i tak realizują się przy cenie). Offset line evidence po
   odległości od ceny (`PRICE_GAP_OFFSET`, od 10-30) już częściowo to robi.
4. Pucharowe mecze kontynentalne: zebrać więcej (dziś 21 + 10 wydrukowanych
   meczów w D ≥ 1) przed czymkolwiek.

## Czego NIE sprawdzono

- Cena rynku z ostatniego snapshotu `04_offer.json`, nie z chwili druku ani z
  zamknięcia (CLV nie liczone).
- Dopasowanie λ zakłada niezależne NB obu drużyn (bez korelacji, bez
  Dixon-Colesa); handicap azjatycki i remisowe szczeble „&” nie weszły do
  dopasowania.
- Pewność całej drabiny tylko od 10-21 i tylko dla meczów nierozpoczętych w
  chwili ostatniej przebudowy (dla 10-28 Seoul - Viettel brak, bo mecz był
  rano); dla wydrukowanych pewność pełna.
- Grupy epok zsumowane; nie rozbito na kobiety / klasy / sezon wczesny.
- Nie replayowano historii (tylko nasze dni z cenami Superbetu); nie
  sprawdzono buildera, `first_goal`, DNB z remisem (zwrot), „12”, 1X2 połów
  wyniku.
- Klasyfikacja pucharu po nazwie rozgrywek i `cup_round_type` (regex) - nie
  ręcznie.
- Hold-out cienki; koszyki nie są monotoniczne; dziesiątki porównań w tym
  raporcie - pojedynczy CI wykluczający zero (np. dev liga) nie jest odkryciem.
