# /kupon pewny - backtest na historii (2026-11-01)

**Tryb** (`build_slip.py --safest`, commit 5a032e22, operator 2026-11-01:
„chcę żeby weszło, nawet jak mniej zarobimy”): kupon z najwyższą zmierzoną
szansą przy iloczynie kursów nóg ≥ cel (domyślnie i najniżej 1,14 - poniżej
wygrana po podatku 12% zwraca mniej niż stawka).

**Metoda** (`kupon_pewny_2026-11-01/replay.py`, `analyse.py`, `extra.py`):
dni 10-13..10-31 (19 dni z `11_coupon.json` i `13_results.json`), 7 okien
po 2 h (10:00-24:00 czasu polskiego), „teraz” = start okna − 60 min, 3
rozłączne kupony na prośbę, 133 prośby na wariant; odczyty / weta dnia
(`reads.json`, `vetoes.json`), bez odczytów kuponów z czatu i bez
dopytywania kursu. Ocena: oceny księgi (`13_results.json`); kupon z
przegraną nogą przegrany, z nieznaną wyłączony, zwrot = 0. Zwrot po podatku
= 0,88 × iloczyn − 1. Przedziały: bootstrap dni (2 000).

| wariant | okres | kupony | nóg/kupon | szansa zmierzona | trafione [95%] | iloczyn | zwrot po podatku [95%] |
|---|---|---|---|---|---|---|---|
| domyślny ~2 | dev 10-13..10-24 | 239 | 2,00 | 0,500 | 0,483 [0,393; 0,575] | 1,99 | −16,1% [−31,6; −0,5] |
| domyślny ~2 | kontrola 10-25..10-31 | 145 | 2,00 | 0,501 | 0,450 [0,390; 0,518] | 1,98 | −21,9% [−32,8; −10,4] |
| domyślny ~1.25 | dev | 247 | 1,17 | 0,788 | 0,778 [0,738; 0,822] | 1,26 | −13,6% [−17,9; −8,7] |
| domyślny ~1.25 | kontrola | 147 | 1,16 | 0,787 | 0,762 [0,664; 0,850] | 1,26 | −15,4% [−26,0; −5,8] |
| **pewny (1,14)** | dev | 249 | 1,00 | 0,857 | **0,867 [0,837; 0,900]** | 1,155 | −12,0% [−15,0; −8,6] |
| **pewny (1,14)** | kontrola | 147 | 1,00 | 0,855 | **0,838 [0,775; 0,895]** | 1,155 | −14,5% [−20,7; −9,1] |
| pewny ~1.3 | dev | 246 | 1,25 | 0,758 | 0,733 [0,673; 0,791] | 1,31 | −15,5% [−22,4; −8,7] |
| pewny ~1.3 | kontrola | 147 | 1,22 | 0,755 | 0,722 [0,669; 0,783] | 1,32 | −16,6% [−22,9; −9,5] |

## Wnioski

1. **Kalibracja:** tryb pewny trafia tyle, ile obiecuje - 0,856 obiecane,
   0,856 [0,828; 0,887] trafione (wszystkie dni). Na nogę realizuje się na
   cenie (0,857 przy średnim 1/kurs 0,866) - przewagi nad ceną nie ma.
2. **Strata:** najmniejsza z wariantów, ale różnice w granicach szumu:
   pewny − domyślny ~2 +5,4 pp [−5,7; +15,8], pewny − domyślny ~1.25 +1,4 pp
   [−3,0; +5,3]. To efekt jednej nogi zamiast dwóch (każda noga kosztuje).
3. **Trafialność:** wyraźnie wyższa - ~86% wobec ~77% (~1.25) i ~47% (~2).
   Cel operatora („żeby weszło”) spełniony, za cenę ~+15% z wygranej.
4. **Zachowanie:** brak pustych odpowiedzi, brak meczu dwa razy, żadna noga
   poniżej 1,10, żaden kupon poniżej celu; 395 z 396 kuponów to jedna noga
   (jedyny dwunożny: okno bez nogi ≥ 1,14 - 1,11 × 1,10). 172 z 396 wyborów
   leży dokładnie na 1,14: szansa jest ucięta ceną, więc tryb w praktyce
   wybiera najkrótszy kurs ≥ 1,14.

**Niezmierzone:** pierwszeństwo przeczytanych nóg w granicy 1 pp (bez
odczytów kuponów z czatu w powtórce), dopytywanie kursu. **Zastrzeżenia:**
`11_coupon.json` to stan końcowy dnia (ceny ostatniej przebudowy, odczyty
mogą być późniejsze niż „teraz”), kontrola to 7 dni, kupony jednego dnia są
skorelowane (stąd bootstrap dni).
