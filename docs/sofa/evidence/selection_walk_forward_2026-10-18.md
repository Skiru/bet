# Gdzie kupon traci i jaka selekcja nóg traci mniej - pomiar 2026-10-18

Zlecenie operatora (2026-10-18, po dniu poprawek 10-17): „mieć zysk z tego”.
Populacja: nogi `official` kuponu (`11_coupon.json`, wydrukowane, także
zablokowane), ocenione tak jak ocenia je ledger
(`record_results.graded_confidence`), WIN / LOSS przy cenie wydruku; zwrot,
void i nierozliczone nie liczą się. Dni 2026-10-09..2026-10-17 (od refitu
2026-10-08; 10-13, 10-14, 10-16 i 10-17 to dni mieszane - liczby łączą ich
epoki). 10-17 był rozliczony częściowo. Przedziały 95% z losowania par (dzień, mecz).

Powtórzenie: `scripts/sofa/measure_selection_walk_forward.py --from 2026-10-12
--to 2026-10-17` - drukuje każdą tabelę tego dokumentu poza sekcją 3.

## 1. Kupon jest skalibrowany i traci marżę

| sport | nogi | mecze | pewność | trafione | 1/kurs | ROI [95%] |
|---|---|---|---|---|---|---|
| piłka | 20 595 | 2 543 | 0,794 | 0,786 | 0,822 | -4,3% [-5,3; -3,3] |
| hokej | 2 220 | 532 | 0,785 | 0,804 | 0,825 | -2,6% [-5,1; -0,2] |
| tenis | 1 859 | 527 | 0,785 | 0,782 | 0,820 | -4,8% [-7,8; -2,0] |
| koszykówka | 178 | 104 | 0,746 | 0,579 | 0,693 | -15,0% [-33,1; +3,8] |
| CS2 | 115 | 36 | 0,764 | 0,774 | 0,808 | -4,7% [-16,8; +6,7] |
| siatkówka | 100 | 83 | 0,755 | 0,690 | 0,762 | -9,3% [-21,9; +1,8] |

Wszystkie sporty: 25 067 nóg / 3 825 meczów, ROI -4,3% [-5,2; -3,5] (stan
rozliczeń 2026-10-18 rano). Luka trafione - pewność: piłka -0,8 pp [-1,6; -0,1],
hokej +1,9 [+0,0; +3,8], tenis -0,4 [-2,8; +1,9], koszykówka -16,7 [-27,2; -6,0]
(znana luka krzywej koszykówki), siatkówka -6,5 [-15,1; +1,3]. Strata to cena: kupon
drukuje nogi z x = pewność x kurs >= 0,90, więc głównie poniżej ceny
(średnio 0,794 wobec 0,822).

## 2. Luka rośnie z pewnością ponad cenę (piłka)

| pewność - 1/kurs | nogi | luka [95%] | ROI |
|---|---|---|---|
| < -0,05 | 7 025 | +1,8 pp [+0,8; +2,9] | -5,7% |
| -0,05..-0,02 | 6 081 | -0,3 pp [-1,4; +0,8] | -4,6% |
| -0,02..0 | 3 035 | -1,4 pp [-3,1; +0,3] | -3,1% |
| 0..+0,03 | 2 577 | -2,5 pp [-4,6; -0,6] | -1,4% |
| > +0,03 | 1 877 | -9,2 pp [-11,9; -6,5] | -4,2% |

Realizacja ciągnie do ceny: tam, gdzie model jest daleko pod ceną, trafia
więcej niż mówi; tam, gdzie nad ceną, mniej. Ten sam kształt mają tenis i
hokej (tabele skryptu). To ten sam mechanizm, co flaga `price_gap`
(T-PRICE-GAP-flag) i obniżka per przedział pewność - cena zmierzona i
odrzucona 2026-10-12 (nie poprawiała ROI) - **nie proponuję jej ponownie.**

Rynki z największą stratą to nie wady pojedynczych krzywych:

7 z 10 rynków o największej stracie ze skryptu (pominięte: `corners_total`
UNDER, `goals_2h_total` OVER / UNDER - luka w granicach szumu):

| rynek (piłka) | nogi | mecze | pewność | trafione | luka [95%] | ROI | jednostki |
|---|---|---|---|---|---|---|---|
| `result_or_over` OVER | 2 765 | 955 | 0,795 | 0,776 | -1,9 pp [-3,8; -0,0] | -6,9% | -189,8 |
| `double_chance` OVER | 1 370 | 1 052 | 0,780 | 0,766 | -1,4 pp [-3,5; +0,5] | -5,6% | -76,8 |
| `result_or_under` OVER | 3 154 | 1 043 | 0,801 | 0,803 | +0,3 pp [-1,8; +2,2] | -2,4% | -75,3 |
| `goals_total` OVER | 958 | 938 | 0,793 | 0,765 | -2,7 pp [-5,4; -0,1] | -7,1% | -68,1 |
| `goals_total` UNDER | 1 314 | 1 068 | 0,799 | 0,782 | -1,7 pp [-4,3; +0,7] | -4,8% | -62,5 |
| `goals_for` UNDER | 907 | 739 | 0,802 | 0,771 | -3,1 pp [-6,0; -0,1] | -5,4% | -48,7 |
| `goals_for` OVER | 473 | 431 | 0,785 | 0,744 | -4,1 pp [-7,9; -0,4] | -8,2% | -38,7 |

Strata każdego z nich to głównie cena (ROI -5..-7% przy luce -1..-4 pp).
`result_or_over` to dwa dni (10-16 +2,0 pp, 10-17 -2,5 pp - rozbicie dzienne
poza skryptem, z tej sesji; rynek od 10-16 07:46Z) - przedział dotyka zera. `goals_for` jest zawyżone w obu kierunkach na
9 dniach z czterema epokami: kandydat do zmierzenia na historii (rozrzut /
rozciągnięcie s), nie do korekty z rozliczeń (krzywe tylko z historii).

## 3. Rynki tenisa, które nie drukują - słusznie

`games_total` na liniach Superbetu (dowody linii z poranka 10-18): p modelu
0,70-0,75 OVER realizuje 51/85 = 0,60, 0,75-0,80 24/37 = 0,65, UNDER 0,70-0,75
14/34 = 0,41. Offset i cap pasma ceny słusznie spychają je poniżej 0,70. Asy /
PB w secie: `tennis_aces_opponent_2026-10-17.md` (-20..-31 pp). Krzywa na
liniach rynkowych może tylko obciąć; zysku tu nie ma.

## 4. Selekcja walk-forward (dni testu 10-12..10-17)

Dla dnia D rodziny (sport, rynek, kierunek) „na plusie” z dni przed D
(`family_record.window`: 14 dni, nie wcześniej niż 10-09 - na tych dniach
testu okna miały **3-8 dni**; >= 50 nóg, jednostki > 0), potem nogi D.
Pomiar stosuje `family_record.selected` (x >= 1 i rodzina na plusie); strona
liczy x tą samą `family_record.selection_x` i sprawdza ten sam warunek w
JavaScripcie (test w przeglądarce).

| selekcja | nogi | mecze | trafione | 1/kurs | jednostki | ROI [95%] |
|---|---|---|---|---|---|---|
| cały kupon | 19 413 | 2 560 | 0,788 | 0,823 | -830,96 | -4,3% [-5,3; -3,3] |
| x >= 1 | 3 827 | 1 344 | 0,747 | 0,765 | -89,90 | -2,3% [-5,0; +0,2] |
| rodzina na plusie | 4 373 | 1 360 | 0,800 | 0,817 | -85,26 | -1,9% [-4,0; +0,1] |
| kurs 1,40-2,00 | 1 190 | 805 | 0,676 | 0,680 | -5,38 | -0,5% [-4,9; +3,9] |
| **x >= 1 i rodzina na plusie** | 1 254 | 602 | 0,760 | 0,765 | -6,92 | **-0,6% [-4,8; +3,9]** |
| reszta kuponu (bez selekcji) | 18 159 | 2 527 | 0,790 | 0,827 | -824,04 | -4,5% [-5,5; -3,6] |

**Selekcja minus reszta: +4,0 pp [-0,3; +8,1]** (pary na tych samych
losowaniach (dzień, mecz)).

| dzień | okno (dni) | nogi dnia | selekcja: nogi | ROI selekcji | ROI reszty | różnica |
|---|---|---|---|---|---|---|
| 10-12 | 3 | 718 | 21 | +10,6% | -6,3% | +16,9 pp |
| 10-13 | 4 | 1 029 | 36 | -1,0% | -4,0% | +3,1 pp |
| 10-14 | 5 | 1 195 | 47 | +8,0% | -6,2% | +14,2 pp |
| 10-15 | 6 | 1 414 | 74 | +2,5% | -1,2% | +3,7 pp |
| 10-16 | 7 | 3 071 | 61 | +0,6% | -3,5% | +4,2 pp |
| 10-17 | 8 | 11 986 | 1 015 | -1,5% | -5,0% | +3,5 pp |

Selekcja wg sportu: piłka 1 175 nóg -0,8% [-5,5; +3,3], hokej 63 nogi +5,8%
[-10,4; +20,2], tenis 16 nóg -9,0%.

Jak to czytać, uczciwie:

- Selekcja wypadła lepiej od reszty kuponu **w 6 z 6 dni** (test znaków
  dwustronnie p = 0,03), ale łączna różnica ma zero w przedziale, a **81% nóg
  selekcji to jeden dzień, 10-17** (dzień mieszany, rozliczony częściowo,
  12 tys. wydruków). Losowanie meczów nie widzi zależności wewnątrz dnia, więc
  przedział jest raczej za wąski niż za szeroki.
- Przewaga nad resztą jest **niepotwierdzona**, zysk **nieudowodniony**.
- Pięć reguł porównano naraz na tych samych dniach; najlepsza z pięciu wypada
  na nowych danych zwykle trochę gorzej.
- Dni okna są ocenione dzisiejszym rozliczeniem (z porannymi doliczeniami);
  rekord na żywo przy budowie D widzi D-1 słabiej rozliczony. Na żywo okno
  dojdzie do 14 dni (od 10-23) - takiego okna ten pomiar nie widział.
- Rodziny na plusie to głównie rożne OVER, strzały OVER, hokej total UNDER,
  sety tenisa - te same, co `corners_total` OVER z 10-06..10-12.

**Werdykt:** kupon bez zmian (reguła x >= 0,90 to decyzja operatora). Widok
HTML dostaje filtr „min. x”, filtr i znacznik „rodzina na plusie” oraz przycisk
„x ≥ 1 i rodzina na plusie” (`bet.sofa.family_record`, `family_record.json`).
Sprawdzian na nowych danych: `T-FAMILY-SELECTION` (PROPOSED). Na 10-18
selekcja zostawia 143 z 9 104 nóg w 73 meczach.
