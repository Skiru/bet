# Pomiar: która szansa nogi najlepiej przewiduje wynik - cel kuponu z czatu (2026-10-20)

Pomiar tylko do odczytu. Nic w potoku, konfiguracji, kuponach, odczytach ani w księdze nie zostało zmienione.
Skrypt: `scripts/sofa/measure_slip_chance.py` (wynik poniżej odtwarza
`PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_slip_chance.py --from 2026-10-13 --to 2026-10-19`, ziarno 20261020, 2000 losowań).

## Pytanie

`slip_builder.best_slip` (dokładny plecak wielokrotnego wyboru) maksymalizuje iloczyn „szans zmierzonych” nóg przy iloczynie kursów >= cel. Optymalizator jest dokładny, więc kupon jest najlepszy tylko wtedy, gdy szansa jednej nogi jest najlepszym dostępnym oszacowaniem. Porównano, które prawdopodobieństwo nogi najlepiej przewiduje, czy wydrukowana noga wygra - kalibracja i ranking przy podobnej cenie:

- **a** - `confidence` z kuponu (wydrukowana, z `13_results.json`);
- **b** - `slip_builder.measured_chance(...)` liczona **walk-forward**: dzień d czyta tylko `runs/sofa/<d>/family_record.json` (14 dni ściśle przed d; plik był dla każdego z 7 dni, przeliczenie nie było potrzebne);
- **b0** - to samo bez stałej warstwy `TIER_SHORTFALL` (te stałe zmierzono na 10-12..10-19, więc dla tych dni są w próbie - sprawdzenie, czy to coś zmienia);
- **c** - 1/kurs;
- **d** - 1/kurs bez marży, proporcjonalnie: (1/kurs) / (1 + `overround` grupy nogi). Marża jest tylko na nogach dwustronnych / z grupą: 20 949 z 29 408 nóg; jednostronne (propsy, szczeble tylko OVER) jej nie mają, więc **d** liczone jest tylko na tym podzbiorze.

## Dane

- Dni: **2026-10-13 .. 2026-10-19 (7 dni)**. 10-20 jeszcze nierozliczony - pominięty.
- Nogi: każda wydrukowana pojedyncza noga z `13_results.json` (`legs`) z wynikiem WIN / LOSS, złączona z `11_coupon.json` (`singles` + `legs`) przez `coupon_results.key_of` - złączyły się wszystkie. Zwroty, VOID, UNSETTLED, UNGRADEABLE, PENDING pominięte. **Buildery pominięte** (`13_results.json` `builders`): ich nogi nie są graded jako pojedyncze; noga buildera, która była też pojedynczą, jest w próbie jako pojedyncza.
- Kurs i pewność: te z `13_results.json` (cena, po której noga jest rozliczona); `price_gap`, `overround`, rodzina - z nogi w `11_coupon.json`.
- 29 470 nóg WIN/LOSS; 62 bez szansy zmierzonej (rodzina i sport nieobecne w rekordzie dnia) pominięte -> **29 408 nóg, 3 572 meczów**, trafienie 0,782.
- Per sport (nogi / mecze): piłka 25 539 / 2 582, tenis 1 889 / 474, hokej 1 677 / 361, siatkówka 114 / 68, CS2 108 / 32, koszykówka 81 / 55.
- Per dzień: 10-13 1 022, 10-14 1 163, 10-15 1 391, 10-16 3 076, **10-17 12 042 (41%)**, **10-18 8 829 (30%)**, 10-19 1 885.
- Źródło szansy b: pewność 14 131, rodzina 11 610, sport 1 618, „selekcja (walk-forward)” 2 049.

**Ograniczenia, nazwane:** tylko 7 dni, dwa z nich dają 71% nóg; piłka to 87% nóg, więc wynik „ogółem” jest wynikiem piłki. Pliki `family_record.json` zostały odbudowane 2026-10-20 - okno dni jest ściśle przed d (brak wyniku dnia d), ale oceny dni wcześniejszych zawierają późniejsze dorozliczenia (resettle); żywy rekord w dniu d widział D-1 nieco mniej rozliczony. Nie zmierzono: sportów mierzonych osobno z sensowną mocą (CS2, koszykówka, siatkówka - po kilkadziesiąt meczów), pasma 1,70-2,00 (38 nóg).

## Metoda

- Brier i log-loss każdego estymatora; 95% przedziały z bootstrapu **meczów** (losowanie meczów ze zwracaniem, 2000 powtórzeń); różnice sparowane (b−a, b−c, a−c, …) na tych samych losowaniach. Ujemna różnica = pierwszy estymator lepszy.
- Kalibracja: przedziały p, N, średnia p, trafienie.
- Ranking przy cenie: w pasmach kursu 1,10-1,20 / 1,20-1,30 / 1,30-1,45 / 1,45-1,70 / 1,70-2,00 podział na medianie (p − 1/kurs); porównanie (trafienie − 1/kurs) górnej i dolnej połowy (cena w paśmie kontrolowana), przedział z bootstrapu meczów; AUC a i b w paśmie (1000 losowań) obok AUC samego 1/kurs.
- Bez jednego dnia: znak różnic Brier po wyrzuceniu każdego dnia po kolei. Zakresy „bez każdego dnia” dla rankingu w pasmach policzono jednorazowo tymi samymi funkcjami skryptu (nie ma ich w załączniku), a udział nóg z b = a w paśmie - tak samo.
- Druga runda: tylko nogi, które builder może wziąć (kurs 1,10-2,00): 28 188 nóg, 3 560 meczów.

## Wyniki w skrócie

| | Brier ×1000 Δ [95%] | log-loss ×1000 Δ [95%] | bez każdego dnia |
|---|---|---|---|
| b − a (wszystkie) | −0,64 [−1,28; −0,02] | −2,32 [−4,16; −0,58] | znak stały (−0,79..−0,21) |
| b − c (wszystkie) | −1,22 [−1,87; −0,53] | −5,10 [−7,27; −2,78] | znak stały |
| a − c (wszystkie) | −0,58 [−1,17; 0,00] | −2,77 [−4,73; −0,84] | znak stały |
| b − b0 | 0,00 [−0,03; 0,03] | −0,01 [−0,10; 0,08] | - |
| b − a (kurs 1,10-2,00) | −0,62 [−1,24; −0,01] | −2,31 [−4,12; −0,54] | znak stały |
| b − d (nogi z marżą) | −0,33 [−0,82; 0,13] | −0,99 [−2,39; 0,36] | - |
| a − d (nogi z marżą) | −0,02 [−0,98; 0,93] | +0,46 [−2,38; 3,31] | - |

Per dzień b − a (Brier ×1000): −0,9 / −1,5 / +2,3 / +0,6 / −0,5 / −1,6 / −0,1 - lepsza w 4 z 7 dni; łączny znak nie zależy od jednego dnia.

**Kalibracja.** Pewność (a) jest za wysoka u góry: 0,85-0,90 -> trafienie o 2,7 pp niżej, 0,90+ -> o 6,8 pp niżej (537 nóg); średnio 0,794 przy trafieniu 0,782. Szansa zmierzona (b) średnio 0,774 - lekko za nisko w dole (0,60-0,70: +3 pp), blisko w środku. Przewaga b w Brier/log-loss to głównie **poziom** (obniża za wysokie pewności), nie lepsze rozróżnianie.

**Ranking przy cenie (najważniejsze dla plecaka).** Wewnątrz pasma ceny:
- a: górna połowa (pewność wyżej nad ceną) realizuje więcej ponad cenę we wszystkich pasmach: 1,10-1,20 +0,8 pp [−0,7; 2,3], 1,20-1,30 +0,9 [−0,8; 2,5], **1,30-1,45 +2,8 pp [0,2; 5,6]** (bez każdego dnia: +2,1..+3,2), 1,45-1,70 +6,2 [−0,4; 12,4] (bez każdego dnia +5,3..+10,1).
- b: 1,10-1,20 +1,0 [−0,5; 2,5], 1,20-1,30 −0,1 [−1,8; 1,5], **1,30-1,45 −0,8 [−3,5; 1,8]**, 1,45-1,70 +3,9 [−2,4; 10,0]. W 1,30-1,45 b nie odróżnia lepszej nogi od gorszej (bez każdego dnia −1,3..0,0), a a odróżnia.
- Powód (mechanizm, nie pomiar): b = min(pewność, 1/kurs + niedobór rodziny); w 1,30-1,45 b równa się pewności tylko w 21% nóg, w 1,45-1,70 w 0% - wtedy (b − 1/kurs) to niedobór rodziny, a rekord rodziny z 14 dni nie przewiduje wyniku nogi. Ranking a w pasmach 1,30-1,70 przepada.
- AUC w paśmie: a i b ~0,51-0,54, oba poniżej AUC samego 1/kurs w paśmie (0,52-0,55) - rozróżnianie każdego estymatora przy cenie jest słabe.

**Per sport:** przewaga b nad a i nad c jest tylko w piłce (b−a −0,80 [−1,48; −0,13], b−c −1,63 [−2,31; −0,90], a−c −0,82 [−1,43; −0,17]). W tenisie, hokeju, CS2, siatkówce b jest nominalnie gorsza od a i od c (żaden przedział nie wyklucza zera); w hokeju i tenisie cena (c) ma nominalnie najniższy Brier.

## Wniosek

1. Dla **kalibracji całego kuponu** szansa zmierzona (b) jest najlepsza z mierzonych: lepsza od pewności i od ceny, przedziały wykluczają zero (b−a ledwo: górna granica −0,02 w Brier, −0,58 w log-loss), znak trzyma bez każdego dnia. To wynik piłki i to różnica poziomu: b nie obiecuje 0,85-0,90 tam, gdzie nogi trafiają 0,84. Iloczyn szans b jest więc uczciwszą „szansą kuponu” niż iloczyn pewności.
2. Dla **wyboru nóg przy podobnej cenie** - a to decyduje o tym, który kupon wybierze plecak - b **nie jest** lepsza od pewności, a w paśmie 1,30-1,45 jest gorsza: pewność rozróżnia (+2,8 pp [0,2; 5,6]), b nie (−0,8 pp [−3,5; 1,8]). Ograniczenie min(…, 1/kurs + niedobór rodziny) zastępuje sygnał pewności rekordem rodziny, który przy cenie nic nie mówi.
3. Stała warstwy (`TIER_SHORTFALL`) nie zmienia niczego (b − b0 = 0,00), więc jej pomiar w próbie nie psuje tego wyniku.
4. Cena bez marży (d) nie jest lepsza od pewności (a − d ≈ 0); b − d bez przewagi poza szumem.
5. **Co builder powinien używać:** na tych danych żaden estymator nie wygrywa na obu osiach. Najbardziej obronny wariant to ranking z pewności, poziom obniżony jak w b - np. pewność przeskalowana tak, by była skalibrowana (krzywa poziomu walk-forward) zamiast min z niedoborem rodziny. **To podejrzenie, niezmierzone** - wymaga osobnego pomiaru walk-forward, zanim cokolwiek zmieni się w `slip_builder`. Do tego czasu: różnice między a i b są małe (≤ 1 promil Briera), mieszczą się blisko szumu w każdym sporcie poza piłką, a 7 dni z 71% nóg w dwóch dniach to za mało, by przestawiać cel plecaka.

Bez zmian w potoku. Rekomendacja nie jest zmianą - operator decyduje.

## Załącznik: pełny wynik skryptu


- 2026-10-13: rekord rodzin plik (dni 2026-10-09..2026-10-12); wyniki {'WIN': 807, 'LOSS': 222, 'REFUND': 16}
- 2026-10-14: rekord rodzin plik (dni 2026-10-09..2026-10-13); wyniki {'WIN': 926, 'LOSS': 269, 'REFUND': 12, 'UNSETTLED': 5, 'UNGRADEABLE': 1, 'VOID': 8}
- 2026-10-15: rekord rodzin plik (dni 2026-10-09..2026-10-14); wyniki {'LOSS': 260, 'REFUND': 26, 'WIN': 1154, 'UNSETTLED': 1, 'PENDING:DATA_MISMATCH': 2, 'VOID': 2}
- 2026-10-16: rekord rodzin plik (dni 2026-10-09..2026-10-15); wyniki {'WIN': 2463, 'LOSS': 613, 'UNSETTLED': 31, 'REFUND': 25, 'VOID': 5}
- 2026-10-17: rekord rodzin plik (dni 2026-10-09..2026-10-16); wyniki {'WIN': 9436, 'LOSS': 2606, 'REFUND': 43, 'UNSETTLED': 35, 'VOID': 6, 'PENDING:DATA_MISMATCH': 1, 'UNGRADEABLE': 1}
- 2026-10-18: rekord rodzin plik (dni 2026-10-09..2026-10-17); wyniki {'WIN': 6777, 'LOSS': 2052, 'UNSETTLED': 40, 'REFUND': 61, 'VOID': 5, 'UNGRADEABLE': 2}
- 2026-10-19: rekord rodzin plik (dni 2026-10-09..2026-10-18); wyniki {'LOSS': 392, 'WIN': 1493, 'REFUND': 5, 'UNSETTLED': 22, 'UNGRADEABLE': 1}
- nogi WIN/LOSS: 29470; bez szansy zmierzonej (brak rodziny i sportu w rekordzie): 62 - pominięte
- źródło b: {'sport': 1618, 'pewność': 14131, 'rodzina': 11610, 'selekcja (walk-forward)': 2049, None: 62}; warstwy: {3: 24548, 2: 3513, 1: 1409}

### Wszystkie nogi

Nogi / mecze per sport: basketball 81 / 55, cs2 108 / 32, football 25539 / 2582, hockey 1677 / 361, tennis 1889 / 474, volleyball 114 / 68
Nogi per dzień: 2026-10-13 1022, 2026-10-14 1163, 2026-10-15 1391, 2026-10-16 3076, 2026-10-17 12042, 2026-10-18 8829, 2026-10-19 1885

#### Brier i log-loss, wszystkie nogi (a, b, b0, c)

**Wszystkie nogi: a/b/b0/c** - 29408 nóg, 3572 meczów, trafienie 0.782

| estymator | średnia p | Brier [95%] | log-loss [95%] |
|---|---|---|---|
| a: pewność (confidence) | 0.794 | 0.1683 [0.1641; 0.1723] | 0.5185 [0.5085; 0.5281] |
| b: szansa zmierzona (measured_chance) | 0.774 | 0.1677 [0.1638; 0.1713] | 0.5162 [0.5074; 0.5245] |
| b0: szansa zmierzona bez stałej warstwy | 0.775 | 0.1677 [0.1638; 0.1713] | 0.5162 [0.5074; 0.5245] |
| c: 1/kurs | 0.824 | 0.1689 [0.1644; 0.1731] | 0.5213 [0.5102; 0.5318] |

Różnice sparowane (ujemna = pierwszy lepszy), te same losowania meczów:

| para | Δ Brier ×1000 [95%] | Δ log-loss ×1000 [95%] |
|---|---|---|
| b − a | -0.64 [-1.28; -0.02] | -2.32 [-4.16; -0.58] |
| b − c | -1.22 [-1.87; -0.53] | -5.10 [-7.27; -2.78] |
| a − c | -0.58 [-1.17; 0.00] | -2.77 [-4.73; -0.84] |
| b0 − a | -0.64 [-1.27; -0.03] | -2.32 [-4.14; -0.61] |
| b − b0 | 0.00 [-0.03; 0.03] | -0.01 [-0.10; 0.08] |

#### Z ceną bez marży (d) - tylko nogi z marżą grupy (20949 z 29408)

**Wszystkie nogi: z d** - 20949 nóg, 3417 meczów, trafienie 0.785

| estymator | średnia p | Brier [95%] | log-loss [95%] |
|---|---|---|---|
| a: pewność (confidence) | 0.793 | 0.1668 [0.1624; 0.1713] | 0.5149 [0.5045; 0.5255] |
| b: szansa zmierzona (measured_chance) | 0.771 | 0.1665 [0.1625; 0.1706] | 0.5135 [0.5044; 0.5228] |
| b0: szansa zmierzona bez stałej warstwy | 0.771 | 0.1665 [0.1625; 0.1706] | 0.5135 [0.5044; 0.5228] |
| c: 1/kurs | 0.821 | 0.1672 [0.1625; 0.1720] | 0.5169 [0.5054; 0.5284] |
| d: 1/kurs bez marży (proporcjonalnie) | 0.751 | 0.1668 [0.1632; 0.1706] | 0.5145 [0.5062; 0.5229] |

Różnice sparowane (ujemna = pierwszy lepszy), te same losowania meczów:

| para | Δ Brier ×1000 [95%] | Δ log-loss ×1000 [95%] |
|---|---|---|
| b − a | -0.31 [-1.03; 0.39] | -1.45 [-3.47; 0.51] |
| b − c | -0.71 [-1.46; 0.05] | -3.37 [-5.86; -0.89] |
| a − c | -0.41 [-1.07; 0.27] | -1.92 [-4.11; 0.35] |
| b0 − a | -0.32 [-1.03; 0.36] | -1.47 [-3.45; 0.48] |
| b − b0 | 0.01 [-0.02; 0.04] | 0.02 [-0.08; 0.11] |
| d − c | -0.38 [-1.41; 0.66] | -2.38 [-5.65; 0.93] |
| a − d | -0.02 [-0.98; 0.93] | 0.46 [-2.38; 3.31] |
| b − d | -0.33 [-0.82; 0.13] | -0.99 [-2.39; 0.36] |

#### Per sport (a, b, c)

| sport | N | mecze | trafienie | Brier a | Brier b | Brier c | Δ b−a ×1000 [95%] | Δ b−c ×1000 [95%] | Δ a−c ×1000 [95%] | log-loss a | log-loss b | log-loss c |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| basketball | 81 | 55 | 0.568 | 0.2764 | 0.2556 | 0.2672 | -20.74 [-81.69; 41.16] | -11.60 [-46.41; 26.10] | 9.15 [-27.36; 52.85] | 0.7578 | 0.7056 | 0.7411 |
| cs2 | 108 | 32 | 0.787 | 0.1636 | 0.1689 | 0.1642 | 5.29 [-0.44; 10.85] | 4.68 [-0.91; 9.68] | -0.61 [-6.70; 5.85] | 0.5059 | 0.5202 | 0.5072 |
| football | 25539 | 2582 | 0.779 | 0.1702 | 0.1693 | 0.1710 | -0.80 [-1.48; -0.13] | -1.63 [-2.31; -0.90] | -0.82 [-1.43; -0.17] | 0.5230 | 0.5202 | 0.5267 |
| hockey | 1677 | 361 | 0.815 | 0.1487 | 0.1488 | 0.1472 | 0.14 [-1.34; 1.45] | 1.66 [-0.63; 3.74] | 1.52 [-0.70; 3.68] | 0.4719 | 0.4724 | 0.4668 |
| tennis | 1889 | 474 | 0.803 | 0.1551 | 0.1564 | 0.1549 | 1.24 [-0.50; 2.97] | 1.44 [-1.24; 3.85] | 0.21 [-1.94; 2.09] | 0.4868 | 0.4903 | 0.4864 |
| volleyball | 114 | 68 | 0.754 | 0.1866 | 0.1894 | 0.1848 | 2.83 [-15.36; 20.41] | 4.56 [-8.16; 16.61] | 1.74 [-9.22; 12.50] | 0.5671 | 0.5636 | 0.5543 |

#### Bez jednego dnia (znak różnicy Brier)

| para | Δ Brier ×1000 ogółem | per dzień (Δ Brier ×1000) | bez dnia: min..max | znak stały bez każdego dnia |
|---|---|---|---|---|
| b − a | -0.64 | -0.9 / -1.5 / +2.3 / +0.6 / -0.5 / -1.6 / -0.1 | -0.79..-0.21 | tak |
| b − c | -1.22 | +1.7 / -2.1 / +2.8 / +0.5 / -1.4 / -2.6 / -0.3 | -1.43..-0.61 | tak |
| a − c | -0.58 | +2.6 / -0.6 / +0.5 / -0.1 / -0.9 / -1.0 / -0.1 | -0.70..-0.39 | tak |
| b − b0 | +0.00 | -0.0 / -0.0 / +0.0 / +0.0 / -0.0 / -0.0 / +0.0 | -0.00..+0.00 | NIE |

Dni w kolejności: 2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-17, 2026-10-18, 2026-10-19.

#### Kalibracja

**a: pewność (confidence)**

| przedział p | N | średnia p | trafienie | trafienie − p |
|---|---|---|---|---|
| 0.70-0.75 | 6981 | 0.726 | 0.716 | -0.010 |
| 0.75-0.80 | 9092 | 0.777 | 0.765 | -0.012 |
| 0.80-0.85 | 8364 | 0.824 | 0.821 | -0.002 |
| 0.85-0.90 | 4434 | 0.868 | 0.841 | -0.027 |
| 0.90+ | 537 | 0.914 | 0.845 | -0.068 |

**b: szansa zmierzona (measured_chance)**

| przedział p | N | średnia p | trafienie | trafienie − p |
|---|---|---|---|---|
| 0.00-0.50 | 35 | 0.446 | 0.571 | +0.125 |
| 0.50-0.60 | 200 | 0.568 | 0.635 | +0.067 |
| 0.60-0.65 | 714 | 0.630 | 0.664 | +0.034 |
| 0.65-0.70 | 1946 | 0.679 | 0.708 | +0.029 |
| 0.70-0.75 | 6947 | 0.726 | 0.733 | +0.007 |
| 0.75-0.80 | 8811 | 0.775 | 0.781 | +0.005 |
| 0.80-0.85 | 7803 | 0.824 | 0.837 | +0.013 |
| 0.85-0.90 | 2892 | 0.865 | 0.849 | -0.016 |
| 0.90+ | 60 | 0.903 | 0.883 | -0.020 |

#### Ranking w paśmie ceny

Pasmo dzielone na medianie (p − 1/kurs); 'trafienie − 1/k' to trafienie minus średnie 1/kurs w połowie (cena kontrolowana); różnica górna − dolna w punktach procentowych (trafienie − 1/kurs), bootstrap meczów; AUC estymatora w paśmie vs AUC samego 1/kurs.

| pasmo kursu | N | mecze | est. | mediana p−1/k | górna połowa: trafienie − 1/k | dolna połowa: trafienie − 1/k | górna − dolna (trafienie − 1/k) [95%] | AUC est. [95%] | AUC 1/k |
|---|---|---|---|---|---|---|---|---|---|
| 1.10-1.20 | 12269 | 3001 | a | -0.048 | -0.041 (n 6134) | -0.049 (n 6135) | 0.8 [-0.7; 2.3] pp | 0.531 [0.517; 0.546] | 0.548 |
| 1.10-1.20 | 12269 | 3001 | b | -0.055 | -0.040 (n 6128) | -0.050 (n 6141) | 1.0 [-0.5; 2.5] pp | 0.539 [0.525; 0.553] | 0.548 |
| 1.20-1.30 | 10366 | 2999 | a | -0.038 | -0.036 (n 5134) | -0.045 (n 5232) | 0.9 [-0.8; 2.5] pp | 0.522 [0.508; 0.535] | 0.531 |
| 1.20-1.30 | 10366 | 2999 | b | -0.051 | -0.041 (n 5177) | -0.040 (n 5189) | -0.1 [-1.8; 1.5] pp | 0.522 [0.508; 0.534] | 0.531 |
| 1.30-1.45 | 4548 | 2146 | a | -0.006 | -0.021 (n 2274) | -0.049 (n 2274) | 2.8 [0.2; 5.6] pp | 0.512 [0.493; 0.531] | 0.525 |
| 1.30-1.45 | 4548 | 2146 | b | -0.036 | -0.039 (n 2254) | -0.031 (n 2294) | -0.8 [-3.5; 1.8] pp | 0.512 [0.494; 0.530] | 0.525 |
| 1.45-1.70 | 967 | 718 | a | +0.062 | +0.022 (n 482) | -0.041 (n 485) | 6.2 [-0.4; 12.4] pp | 0.496 [0.455; 0.534] | 0.519 |
| 1.45-1.70 | 967 | 718 | b | -0.032 | +0.011 (n 463) | -0.028 (n 504) | 3.9 [-2.4; 10.0] pp | 0.533 [0.494; 0.572] | 0.519 |
| 1.70-2.00 | 38 | - | - | za mało nóg (< 40) | | | | | |

### Nogi, które builder może wziąć (kurs 1.10-2.00)

Nogi / mecze per sport: basketball 78 / 54, cs2 100 / 32, football 24536 / 2579, hockey 1628 / 360, tennis 1734 / 467, volleyball 112 / 68
Nogi per dzień: 2026-10-13 968, 2026-10-14 1108, 2026-10-15 1324, 2026-10-16 2945, 2026-10-17 11553, 2026-10-18 8482, 2026-10-19 1808

#### Brier i log-loss, wszystkie nogi (a, b, b0, c)

**Nogi, które builder może wziąć (kurs 1.10-2.00): a/b/b0/c** - 28188 nóg, 3560 meczów, trafienie 0.779

| estymator | średnia p | Brier [95%] | log-loss [95%] |
|---|---|---|---|
| a: pewność (confidence) | 0.791 | 0.1703 [0.1660; 0.1744] | 0.5231 [0.5130; 0.5329] |
| b: szansa zmierzona (measured_chance) | 0.770 | 0.1696 [0.1658; 0.1734] | 0.5208 [0.5120; 0.5297] |
| b0: szansa zmierzona bez stałej warstwy | 0.771 | 0.1696 [0.1658; 0.1735] | 0.5208 [0.5120; 0.5297] |
| c: 1/kurs | 0.820 | 0.1708 [0.1663; 0.1752] | 0.5255 [0.5143; 0.5362] |

Różnice sparowane (ujemna = pierwszy lepszy), te same losowania meczów:

| para | Δ Brier ×1000 [95%] | Δ log-loss ×1000 [95%] |
|---|---|---|
| b − a | -0.62 [-1.24; -0.01] | -2.31 [-4.12; -0.54] |
| b − c | -1.17 [-1.81; -0.48] | -4.68 [-6.78; -2.46] |
| a − c | -0.55 [-1.14; 0.01] | -2.37 [-4.33; -0.49] |
| b0 − a | -0.63 [-1.25; -0.02] | -2.31 [-4.11; -0.58] |
| b − b0 | 0.00 [-0.03; 0.03] | 0.01 [-0.08; 0.09] |

#### Z ceną bez marży (d) - tylko nogi z marżą grupy (20155 z 28188)

**Nogi, które builder może wziąć (kurs 1.10-2.00): z d** - 20155 nóg, 3403 meczów, trafienie 0.782

| estymator | średnia p | Brier [95%] | log-loss [95%] |
|---|---|---|---|
| a: pewność (confidence) | 0.790 | 0.1686 [0.1642; 0.1730] | 0.5192 [0.5086; 0.5297] |
| b: szansa zmierzona (measured_chance) | 0.767 | 0.1683 [0.1644; 0.1723] | 0.5178 [0.5088; 0.5270] |
| b0: szansa zmierzona bez stałej warstwy | 0.768 | 0.1683 [0.1644; 0.1723] | 0.5178 [0.5087; 0.5270] |
| c: 1/kurs | 0.818 | 0.1690 [0.1644; 0.1737] | 0.5208 [0.5096; 0.5321] |
| d: 1/kurs bez marży (proporcjonalnie) | 0.748 | 0.1687 [0.1651; 0.1723] | 0.5189 [0.5109; 0.5270] |

Różnice sparowane (ujemna = pierwszy lepszy), te same losowania meczów:

| para | Δ Brier ×1000 [95%] | Δ log-loss ×1000 [95%] |
|---|---|---|
| b − a | -0.26 [-0.99; 0.46] | -1.35 [-3.40; 0.72] |
| b − c | -0.65 [-1.42; 0.10] | -2.93 [-5.35; -0.57] |
| a − c | -0.38 [-1.05; 0.23] | -1.58 [-3.78; 0.47] |
| b0 − a | -0.27 [-0.99; 0.45] | -1.37 [-3.41; 0.69] |
| b − b0 | 0.01 [-0.02; 0.04] | 0.02 [-0.08; 0.12] |
| d − c | -0.30 [-1.33; 0.73] | -1.91 [-5.12; 1.33] |
| a − d | -0.08 [-1.13; 0.95] | 0.33 [-2.68; 3.36] |
| b − d | -0.34 [-0.82; 0.15] | -1.02 [-2.39; 0.38] |

#### Per sport (a, b, c)

| sport | N | mecze | trafienie | Brier a | Brier b | Brier c | Δ b−a ×1000 [95%] | Δ b−c ×1000 [95%] | Δ a−c ×1000 [95%] | log-loss a | log-loss b | log-loss c |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| basketball | 78 | 54 | 0.577 | 0.2717 | 0.2581 | 0.2696 | -13.57 [-67.87; 43.26] | -11.49 [-48.74; 25.75] | 2.08 [-26.62; 33.42] | 0.7473 | 0.7111 | 0.7465 |
| cs2 | 100 | 32 | 0.780 | 0.1678 | 0.1736 | 0.1684 | 5.72 [-0.48; 11.44] | 5.14 [-1.21; 10.77] | -0.58 [-7.61; 6.46] | 0.5160 | 0.5314 | 0.5168 |
| football | 24536 | 2579 | 0.776 | 0.1719 | 0.1711 | 0.1727 | -0.81 [-1.43; -0.18] | -1.56 [-2.25; -0.84] | -0.76 [-1.36; -0.10] | 0.5271 | 0.5242 | 0.5303 |
| hockey | 1628 | 360 | 0.812 | 0.1504 | 0.1505 | 0.1488 | 0.12 [-1.42; 1.50] | 1.67 [-0.48; 3.78] | 1.55 [-0.69; 3.76] | 0.4761 | 0.4764 | 0.4709 |
| tennis | 1734 | 467 | 0.795 | 0.1601 | 0.1614 | 0.1600 | 1.29 [-0.72; 3.19] | 1.42 [-1.18; 4.09] | 0.14 [-1.88; 2.14] | 0.4987 | 0.5023 | 0.4985 |
| volleyball | 112 | 68 | 0.759 | 0.1835 | 0.1862 | 0.1806 | 2.76 [-15.50; 20.54] | 5.68 [-6.90; 17.38] | 2.92 [-7.26; 13.03] | 0.5597 | 0.5558 | 0.5412 |

#### Bez jednego dnia (znak różnicy Brier)

| para | Δ Brier ×1000 ogółem | per dzień (Δ Brier ×1000) | bez dnia: min..max | znak stały bez każdego dnia |
|---|---|---|---|---|
| b − a | -0.62 | -0.1 / -1.5 / +2.4 / +0.7 / -0.6 / -1.7 / -0.2 | -0.78..-0.16 | tak |
| b − c | -1.17 | +1.8 / -1.8 / +3.1 / +0.6 / -1.4 / -2.6 / -0.2 | -1.38..-0.57 | tak |
| a − c | -0.55 | +1.8 / -0.3 / +0.7 / -0.2 / -0.8 / -0.9 / -0.0 | -0.63..-0.34 | tak |
| b − b0 | +0.00 | -0.0 / -0.0 / +0.0 / +0.0 / +0.0 / -0.0 / +0.0 | +0.00..+0.00 | tak |

Dni w kolejności: 2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-17, 2026-10-18, 2026-10-19.

#### Kalibracja

**a: pewność (confidence)**

| przedział p | N | średnia p | trafienie | trafienie − p |
|---|---|---|---|---|
| 0.70-0.75 | 6977 | 0.726 | 0.716 | -0.009 |
| 0.75-0.80 | 9090 | 0.777 | 0.765 | -0.012 |
| 0.80-0.85 | 8034 | 0.823 | 0.819 | -0.004 |
| 0.85-0.90 | 3666 | 0.867 | 0.837 | -0.030 |
| 0.90+ | 421 | 0.914 | 0.846 | -0.068 |

**b: szansa zmierzona (measured_chance)**

| przedział p | N | średnia p | trafienie | trafienie − p |
|---|---|---|---|---|
| 0.00-0.50 | 29 | 0.460 | 0.621 | +0.161 |
| 0.50-0.60 | 200 | 0.568 | 0.635 | +0.067 |
| 0.60-0.65 | 714 | 0.630 | 0.664 | +0.034 |
| 0.65-0.70 | 1945 | 0.679 | 0.708 | +0.029 |
| 0.70-0.75 | 6947 | 0.726 | 0.733 | +0.007 |
| 0.75-0.80 | 8811 | 0.775 | 0.781 | +0.005 |
| 0.80-0.85 | 7422 | 0.823 | 0.835 | +0.012 |
| 0.85-0.90 | 2106 | 0.864 | 0.849 | -0.015 |
| 0.90+ | 14 | 0.901 | 0.929 | +0.027 |

#### Ranking w paśmie ceny

Pasmo dzielone na medianie (p − 1/kurs); 'trafienie − 1/k' to trafienie minus średnie 1/kurs w połowie (cena kontrolowana); różnica górna − dolna w punktach procentowych (trafienie − 1/kurs), bootstrap meczów; AUC estymatora w paśmie vs AUC samego 1/kurs.

| pasmo kursu | N | mecze | est. | mediana p−1/k | górna połowa: trafienie − 1/k | dolna połowa: trafienie − 1/k | górna − dolna (trafienie − 1/k) [95%] | AUC est. [95%] | AUC 1/k |
|---|---|---|---|---|---|---|---|---|---|
| 1.10-1.20 | 12269 | 3001 | a | -0.048 | -0.041 (n 6134) | -0.049 (n 6135) | 0.8 [-0.7; 2.3] pp | 0.531 [0.517; 0.546] | 0.548 |
| 1.10-1.20 | 12269 | 3001 | b | -0.055 | -0.040 (n 6128) | -0.050 (n 6141) | 1.0 [-0.5; 2.5] pp | 0.539 [0.525; 0.553] | 0.548 |
| 1.20-1.30 | 10366 | 2999 | a | -0.038 | -0.036 (n 5134) | -0.045 (n 5232) | 0.9 [-0.8; 2.5] pp | 0.522 [0.508; 0.535] | 0.531 |
| 1.20-1.30 | 10366 | 2999 | b | -0.051 | -0.041 (n 5177) | -0.040 (n 5189) | -0.1 [-1.8; 1.5] pp | 0.522 [0.508; 0.534] | 0.531 |
| 1.30-1.45 | 4548 | 2146 | a | -0.006 | -0.021 (n 2274) | -0.049 (n 2274) | 2.8 [0.2; 5.6] pp | 0.512 [0.493; 0.531] | 0.525 |
| 1.30-1.45 | 4548 | 2146 | b | -0.036 | -0.039 (n 2254) | -0.031 (n 2294) | -0.8 [-3.5; 1.8] pp | 0.512 [0.494; 0.530] | 0.525 |
| 1.45-1.70 | 967 | 718 | a | +0.062 | +0.022 (n 482) | -0.041 (n 485) | 6.2 [-0.4; 12.4] pp | 0.496 [0.455; 0.534] | 0.519 |
| 1.45-1.70 | 967 | 718 | b | -0.032 | +0.011 (n 463) | -0.028 (n 504) | 3.9 [-2.4; 10.0] pp | 0.533 [0.494; 0.572] | 0.519 |
| 1.70-2.00 | 38 | - | - | za mało nóg (< 40) | | | | | |
