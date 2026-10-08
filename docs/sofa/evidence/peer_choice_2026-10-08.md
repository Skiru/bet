# Którą z dwóch nóg po tym samym kursie proponować - dowody (2026-10-08)

Pytanie operatora (po przegranej 10-07): „jak masz dwie nogi po 1.2 to musisz mi
zaproponować tę która ma większą pewność wejścia, na bazie głębokiej analizy
statystyk oraz metadanych jak ranga turnieju". Przypadek wzorcowy: Internacional -
Corinthians, kartki łącznie powyżej 3,5 (pewność 0,812, próbka 19/20, n = 20)
obok Corinthians kartki poniżej 4,5 (0,882, próbka 9/10, n = 10), kursy 1,16 i
1,19; Corinthians przegrali na 5 kartkach.

**Pierwszy wniosek, wbrew intuicji operatora:** na dwudziestu dniach (62 tys. nóg,
57,8 tys. rozstrzygniętych par) **żadna** statystyka próbki ani metadana turnieju nie
poprawia kolejności po pewności poza próbą. Pewność jest już najlepiej zmierzoną
miarą; przewaga jest realna i mała.

| co sprawdzono | wynik |
|---|---|
| wyższa pewność wygrywa pary (piłka + tenis) | **53,4% [52,2; 54,7]**, 57 791 par w 3 145 meczach; przy różnicy pewności ≥ 0,04: 55,4% [53,2; 57,2] |
| własny odsetek trafień k/n | 50,3% [48,8; 51,7] - bez informacji ponad pewność |
| większa próbka n | 52,7% [51,3; 54,2] - tyle co pewność (próbka i typ rynku są splecione: total ma n = 20, strona n = 10) |
| total zamiast strony drużyny | 53,0% [51,5; 54,6] (piłka 53,7%) - nie ponad pewność |
| OVER / UNDER, margines w sd, bliskie pudła | 49,7% / 50,3% / 50,5% / 48,8% - nic |
| cecha dodana do `logit(p_bar)`, leave-one-day-out | log-loss piłka 0,4819 → 0,4816 przy wszystkich cechach naraz; tenis 0,4731 → 0,4726; różnice w czwartym miejscu |
| ranga turnieju (Sofascore `userCount`), rezerwy / kobiety / puchar | bez poprawy (piłka 0,4819; 0,4819; tenis 0,4730; 0,4733); reprezentacje: flaga się nie uogólnia (dni z meczami reprezentacji są nieliczne) |
| trafienia u siebie / na wyjeździe, ostatnie 5 meczów | 0,4876 → 0,4876 / 0,4873 |
| hokej, koszykówka, siatkówka | 49,7% [45,9; 53,6] na 2 894 parach w 320 grach: **brak przewagi do zmierzenia** |

**Stawka meczu** (czego żaden z powyższych nie widział) policzona z tabeli ligi na
chwilę meczu (`bet.sofa.stakes`): mecz o utrzymanie (oba kluby w odległości ≤ 3 pkt
od linii spadkowej, ≥ 55% sezonu) ma względem średniej swojej ligi-sezonu
**+0,20 kartki, +0,86 faulu, -0,15 gola, -0,96 strzału** (sekcja 5) - to
0,08-0,16 odchylenia standardowego: **efekt jest prawdziwy i mały**. Nie jest
skorygowany o to, że kluby strefy spadkowej są słabe (reszta liczona względem ligi,
nie względem własnych próbek klubów), więc wchodzi na kupon jako flaga z kierunkiem,
nie jako poprawka pewności.

**Co to znaczy dla Corinthians.** Flaga stawki wskazuje Internacional - Corinthians
jako mecz o utrzymanie (73% sezonu, oba kluby 2 pkt od linii) i efekt stawki idzie
**przeciw** nodze „kartki drużyny poniżej" i **za** nogą „kartki łącznie powyżej".
Przesunięcie jest rzędu 0,1 odchylenia - 1-2 pp na nodze - przy różnicy pewności 0,07;
★ zostaje przy nodze o wyższej pewności, a przy obu nogach stoi flaga. Tego jednego meczu nie
rozstrzyga żaden pomiar: przegrana noga miała ~12% szans na pudło.

**Czego nie zmierzono.** Stawki innej niż pozycja w tabeli (derby, finał, mecz o puchar
bez tabeli) - brak jej w artefaktach; tylko tabela ligi z podziałem przybliżonym
(strefa spadkowa 3 kluby do 16 drużyn, 4 powyżej; ligi z fazami play-off czytane jako
jedna tabela). Dwadzieścia dni to dwie epoki reguł (`p_bar` to liczba arkusza przed
krzywą, nie wydrukowana pewność). Przedziały to bootstrap po meczach; pary jednego
meczu nie są niezależne. Pre-rejestrowany test na nowych danych:
`T-PEER-CHOICE-edge` (od 2026-10-09).

Odtworzenie: `PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_peer_choice.py --sections pairs,features,cells,sports,stakes`.
Surowe tabele poniżej (`peer_choice_2026-10-08.json` obok).

---


Wygenerowane przez `scripts/sofa/measure_peer_choice.py` (tylko odczyt). Para = dwie różne zmienne jednego meczu, kurs w pasie ±0.06, `p_bar` ≥ 0.7, dokładnie jedna z dwóch weszła; przedziały 95% to bootstrap po meczach.

## 1. Którą nogę wskazuje reguła i jak często ta noga wygrywa

### football

| reguła | par | meczów | trafia | 95% |
|---|---|---|---|---|
| p_bar (the pipeline's confidence) | 44145 | 1902 | 53.4% | [51.8%; 54.8%] |
| own hit rate k/n | 39954 | 1877 | 50.0% | [48.2%; 51.8%] |
| larger own sample n | 30849 | 1761 | 53.0% | [51.6%; 54.7%] |
| total preferred over a side | 23533 | 1701 | 53.7% | [51.7%; 55.3%] |
| OVER preferred | 23417 | 1720 | 50.4% | [47.3%; 54.1%] |
| UNDER preferred | 23417 | 1720 | 49.6% | [45.9%; 52.7%] |
| larger margin in sd | 44177 | 1902 | 50.3% | [48.5%; 52.0%] |
| fewer near misses | 33780 | 1867 | 48.5% | [46.7%; 50.2%] |
| p_bar, gap >= 0.04 | 20375 | 1589 | 55.7% | [53.4%; 57.8%] |

### tennis

| reguła | par | meczów | trafia | 95% |
|---|---|---|---|---|
| p_bar (the pipeline's confidence) | 13646 | 1243 | 53.3% | [51.9%; 54.5%] |
| own hit rate k/n | 11303 | 1214 | 51.2% | [49.2%; 53.1%] |
| larger own sample n | 7261 | 1060 | 51.5% | [49.1%; 53.6%] |
| total preferred over a side | 7019 | 1053 | 51.0% | [48.5%; 53.4%] |
| OVER preferred | 7299 | 1131 | 47.6% | [44.3%; 50.7%] |
| UNDER preferred | 7299 | 1131 | 52.4% | [49.3%; 55.7%] |
| larger margin in sd | 13715 | 1243 | 51.1% | [49.5%; 52.7%] |
| fewer near misses | 9461 | 1179 | 49.8% | [47.8%; 51.7%] |
| p_bar, gap >= 0.04 | 4557 | 1028 | 54.4% | [51.8%; 57.3%] |

### all

| reguła | par | meczów | trafia | 95% |
|---|---|---|---|---|
| p_bar (the pipeline's confidence) | 57791 | 3145 | 53.4% | [52.2%; 54.7%] |
| own hit rate k/n | 51257 | 3091 | 50.3% | [48.8%; 51.7%] |
| larger own sample n | 38110 | 2821 | 52.7% | [51.3%; 54.2%] |
| total preferred over a side | 30552 | 2754 | 53.0% | [51.5%; 54.6%] |
| OVER preferred | 30716 | 2851 | 49.7% | [46.7%; 52.7%] |
| UNDER preferred | 30716 | 2851 | 50.3% | [47.3%; 53.3%] |
| larger margin in sd | 57892 | 3145 | 50.5% | [49.1%; 52.1%] |
| fewer near misses | 43241 | 3046 | 48.8% | [47.2%; 50.2%] |
| p_bar, gap >= 0.04 | 24932 | 2617 | 55.4% | [53.2%; 57.2%] |

## 2. Czy jakakolwiek cecha poprawia pewność poza próbą

Leave-one-day-out, log-loss (niżej = lepiej) i AUC.

### football

| cechy | log-loss | AUC | nóg |
|---|---|---|---|
| p_bar only | 0.4819 | 0.6032 | 40019 |
| + own hit rate | 0.4818 | 0.6038 | 40019 |
| + sample size / side | 0.4818 | 0.6034 | 40019 |
| + near misses | 0.4817 | 0.6042 | 40019 |
| + share of sample from this competition | 0.4819 | 0.6030 | 40019 |
| + model - sample gap | 0.4817 | 0.6039 | 40019 |
| + margin in sd | 0.4816 | 0.6047 | 40019 |
| everything above | 0.4816 | 0.6049 | 40019 |
| + tournament popularity (Sofascore userCount) | 0.4819 | 0.6030 | 40019 |
| + reserve / women / cup | 0.4819 | 0.6031 | 40019 |
| + national team | 0.5039 | 0.5984 | 40019 |

### tennis

| cechy | log-loss | AUC | nóg |
|---|---|---|---|
| p_bar only | 0.4731 | 0.6108 | 22374 |
| + own hit rate | 0.4723 | 0.6146 | 22374 |
| + sample size / side | 0.4733 | 0.6099 | 22374 |
| + near misses | 0.4728 | 0.6114 | 22374 |
| + share of sample from this competition | 0.4731 | 0.6103 | 22374 |
| + model - sample gap | 0.4722 | 0.6147 | 22374 |
| + margin in sd | 0.4727 | 0.6131 | 22374 |
| everything above | 0.4726 | 0.6127 | 22374 |
| + tournament popularity (Sofascore userCount) | 0.4730 | 0.6111 | 22374 |
| + reserve / women / cup | 0.4733 | 0.6097 | 22374 |
| + national team | 0.4731 | 0.6108 | 22374 |

### football_side_form

| cechy | log-loss | AUC | nóg |
|---|---|---|---|
| p_bar only | 0.4876 | 0.6039 | 15061 |
| + venue hit rate | 0.4876 | 0.6037 | 15061 |
| + last-5 hit rate | 0.4873 | 0.6053 | 15061 |

## 3. Rynki: zrealizowane minus `p_bar` (p_bar ≥ 0,75, ≥150 nóg)

| komórka | nóg | meczów | p | trafia | różnica | 95% |
|---|---|---|---|---|---|---|
| football|corners_2h_for|OVER | 180 | 98 | 0.845 | 0.739 | -0.106 | [-0.167; -0.053] |
| tennis|games_total|UNDER | 217 | 86 | 0.812 | 0.751 | -0.060 | [-0.159; +0.029] |
| football|corners_1h_for|OVER | 361 | 273 | 0.824 | 0.773 | -0.051 | [-0.089; -0.012] |
| football|shots_on_target_for|UNDER | 299 | 124 | 0.827 | 0.786 | -0.041 | [-0.088; +0.013] |
| football|corners_2h_total|OVER | 166 | 104 | 0.846 | 0.807 | -0.039 | [-0.107; +0.026] |
| football|shots_on_target_total|UNDER | 224 | 134 | 0.830 | 0.799 | -0.031 | [-0.092; +0.040] |
| tennis|games_won_set2_for|UNDER | 1416 | 1119 | 0.890 | 0.873 | -0.017 | [-0.033; -0.002] |
| tennis|games_set2_total|OVER | 1216 | 1135 | 0.833 | 0.820 | -0.013 | [-0.036; +0.009] |
| tennis|games_won_set1_for|UNDER | 1532 | 1188 | 0.887 | 0.878 | -0.009 | [-0.025; +0.006] |
| football|cards_points_total|UNDER | 212 | 145 | 0.830 | 0.821 | -0.009 | [-0.073; +0.044] |
| football|goals_1h_for|UNDER | 996 | 688 | 0.858 | 0.850 | -0.007 | [-0.030; +0.013] |
| football|goals_1h_total|UNDER | 2150 | 2108 | 0.850 | 0.843 | -0.007 | [-0.021; +0.008] |
| football|goals_for|UNDER | 3810 | 2400 | 0.831 | 0.825 | -0.006 | [-0.018; +0.005] |
| tennis|games_set1_total|OVER | 1281 | 1167 | 0.838 | 0.835 | -0.003 | [-0.023; +0.019] |
| football|goals_total|UNDER | 3786 | 3114 | 0.827 | 0.827 | -0.000 | [-0.012; +0.014] |
| tennis|games_won_set2_for|OVER | 2029 | 950 | 0.824 | 0.825 | +0.001 | [-0.018; +0.020] |
| football|corners_for|UNDER | 1405 | 445 | 0.830 | 0.832 | +0.002 | [-0.020; +0.025] |
| football|corners_1h_total|UNDER | 594 | 445 | 0.824 | 0.827 | +0.002 | [-0.030; +0.036] |
| tennis|games_set2_total|UNDER | 1995 | 1281 | 0.843 | 0.846 | +0.003 | [-0.017; +0.021] |
| tennis|sets_total|UNDER | 277 | 277 | 0.801 | 0.805 | +0.004 | [-0.042; +0.049] |
| tennis|games_won_for|UNDER | 1823 | 1406 | 0.787 | 0.790 | +0.004 | [-0.016; +0.024] |
| tennis|games_set1_total|UNDER | 2034 | 1298 | 0.841 | 0.845 | +0.004 | [-0.018; +0.022] |
| football|corners_1h_for|UNDER | 407 | 231 | 0.813 | 0.818 | +0.005 | [-0.035; +0.040] |
| football|goals_total|OVER | 2401 | 2386 | 0.825 | 0.831 | +0.006 | [-0.008; +0.021] |
| football|corners_2h_for|UNDER | 169 | 92 | 0.822 | 0.828 | +0.007 | [-0.045; +0.064] |
| football|goals_2h_for|UNDER | 1188 | 707 | 0.838 | 0.844 | +0.007 | [-0.016; +0.026] |
| football|corners_for|OVER | 834 | 435 | 0.829 | 0.837 | +0.008 | [-0.023; +0.034] |
| football|corners_total|OVER | 1266 | 677 | 0.834 | 0.843 | +0.008 | [-0.015; +0.035] |
| football|corners_2h_total|UNDER | 186 | 97 | 0.846 | 0.855 | +0.008 | [-0.059; +0.070] |
| tennis|games_won_set1_for|OVER | 2004 | 965 | 0.823 | 0.834 | +0.011 | [-0.006; +0.028] |
| football|corners_total|UNDER | 1358 | 591 | 0.843 | 0.854 | +0.011 | [-0.016; +0.039] |
| football|shots_on_target_for|OVER | 253 | 149 | 0.828 | 0.842 | +0.014 | [-0.034; +0.048] |
| football|goals_2h_total|UNDER | 2173 | 2032 | 0.820 | 0.835 | +0.015 | [-0.001; +0.031] |
| football|cards_points_total|OVER | 151 | 139 | 0.829 | 0.848 | +0.018 | [-0.043; +0.066] |
| football|goals_2h_total|OVER | 1943 | 1943 | 0.803 | 0.825 | +0.022 | [+0.007; +0.040] |
| tennis|games_won_for|OVER | 1211 | 917 | 0.810 | 0.834 | +0.024 | [-0.002; +0.046] |
| football|corners_1h_total|OVER | 533 | 445 | 0.820 | 0.852 | +0.032 | [-0.001; +0.068] |
| football|shots_on_target_total|OVER | 232 | 148 | 0.825 | 0.858 | +0.033 | [-0.023; +0.079] |
| football|goals_for|OVER | 934 | 825 | 0.791 | 0.831 | +0.040 | [+0.017; +0.065] |
| football|goals_1h_total|OVER | 358 | 358 | 0.779 | 0.827 | +0.048 | [+0.012; +0.094] |

## 4. Hokej, koszykówka, siatkówka (nogi z ceną Superbetu + p z repleju)

| sport | nóg | p | trafia | par | gier | wyższe p wygrywa | 95% |
|---|---|---|---|---|---|---|---|
| basketball | 1606 | 0.767 | 0.722 | 856 | 58 | 48.1% | [38.8%; 59.2%] |
| hockey | 3736 | 0.796 | 0.766 | 2007 | 244 | 50.4% | [45.8%; 54.9%] |
| volleyball | 356 | 0.814 | 0.789 | 31 | 18 | 45.2% | [23.6%; 62.5%] |
| all | - | - | - | 2894 | 320 | 49.7% | [45.9%; 53.6%] |

## 5. Mecz o coś (bet.sofa.stakes): reszta względem średniej ligi-sezonu

23172 meczów ze statystykami w 476 ligosezonach; bootstrap po ligosezonach.

### STAKES_SIX_POINTER

| statystyka | meczów | różnica | 95% | w sd |
|---|---|---|---|---|
| cards | 1354 | +0.195 | [+0.057; +0.329] | +0.08 |
| fouls | 1115 | +0.856 | [+0.425; +1.298] | +0.13 |
| corners | 1354 | -0.168 | [-0.359; +0.044] | -0.05 |
| goals | 1354 | -0.148 | [-0.252; -0.049] | -0.08 |
| shots | 948 | -0.963 | [-1.361; -0.555] | -0.16 |
| sot | 1155 | -0.416 | [-0.604; -0.242] | -0.12 |

### STAKES_TOP4

| statystyka | meczów | różnica | 95% | w sd |
|---|---|---|---|---|
| cards | 1166 | +0.218 | [+0.083; +0.377] | +0.09 |
| fouls | 945 | +0.345 | [-0.089; +0.790] | +0.05 |
| corners | 1166 | +0.104 | [-0.096; +0.332] | +0.03 |
| goals | 1166 | -0.187 | [-0.276; -0.098] | -0.11 |
| shots | 800 | -0.018 | [-0.499; +0.469] | -0.00 |
| sot | 1012 | -0.207 | [-0.420; +0.002] | -0.06 |

