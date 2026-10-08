# Rodzina rozkładu predykcyjnego dla liczników piłkarskich (track A2, 2026-10-08)

Pomiar, nie zmiana: nic w `src/bet/sofa`, configach ani bazie nie zostało ruszone.
Skrypt: `scripts/sofa/measure_count_families.py` (`collect` / `analyse` / `referee`),
test: `tests/sofa/test_measure_count_families.py`, wyniki surowe:
`docs/sofa/evidence/count_families_2026-10-08.json`. Baza otwarta tylko `mode=ro`.

## 1. Pytanie i metoda

SHEET wycenia licznik rozkładem ujemnym dwumianowym (NB) dla
`NEGATIVE_BINOMIAL_METRICS`, a dla pozostałych znormalizowanym normalnym z
podłogą nośnika (`engine.sheet_count_p_raw`); wariancja = wariancja próbki
(10 meczów) przeskalowana `centre / mean` i razy `(1 + 1/n)`
(`engine.sheet_predictive_sd`). Mierzone jest **tylko** to, co stoi za średnią:
rodzina i źródło dyspersji.

- **Maszyneria bez zmian.** `calibrate_from_cache.iter_rows` jest uruchamiane
  nietknięte, a jego `_settle_sample` zastąpione kolektorem, więc historia,
  próbki goli z tej samej ligi, shrink `K_CENTRE`, wykluczenie towarzyskich i
  próg `MIN_SAMPLE` są dokładnie replayowe. Kolektor zapisuje (centrum, próbkę,
  średnią, wariancję, wynik) każdego przypadku. Wektorowa kopia estymatora
  bieżącego (`cur`) zgadza się z `sheet_predictive_sd` + `sheet_count_p_raw`
  do 7.6e-14 na losowych przypadkach każdego rynku (kontrola w `analyse`).
- **Dane.** 949 227 skończonych meczów piłkarskich (listing + `/statistics`),
  56 rynków (52 ocenionych, 4 TOO_THIN), statystyki od 2024-11; gole z listingu sięgają dalej wstecz. Siatka jak w replay: 9 połówkowych linii wokół centrum
  (`lines_for`); OVER i UNDER danej linii oceniają się identycznie, więc
  liczona jest jedna strona.
- **Podział czasowy.** trening < 2025-10-01, walidacja 2025-10-01..2026-03-31
  (tylko dobór hiperparametrów: waga poolingu, waga mieszanki, szerokość
  jądra), **test 2026-04-01..2026-10-07 (6 miesięcy)**; parametry po
  dostrojeniu przefitowane na całym treningu+walidacji. Powtórka na
  krótszym oknie (test 2026-07-01..2026-10-07, walidacja od 2026-01-01) dla
  7 rynków: te same znaki i podobne wielkości (sekcja 8). Dla corners_for
  trening+walidacja 82 528 przypadków (w tym walidacja 47 917), test 58 650
  (31 025 meczów); goals_for 1 149 345 / test 325 654.
- **Ocena.** log-loss i Brier po szczeblach, na tych szczeblach, które
  *bieżący* estymator wolno wycenić (`p` w [0.05, 0.95], `outside_model_resolution`).
  Przedziały 95% z bootstrapu **po meczach** (wagi Poisson(1) na meczu, 300
  powtórzeń); osobno znak różnicy w obu połowach okna testowego.
  Wszystkie różnice poniżej to rodzina minus bieżący, razy 1000, **ujemne =
  lepsza**.
- Nie replayowane (tak jak w samym replay): rating piłkarski w centrum, ceny.

## 2. Wynik: najlepsza z rodzin NB-z-dyspersją-z-historii względem bieżącej

Kandydaci wybierani punktowo na teście spośród {nb_pool, nb_lg, nb_lgmu, norm_lg,
cmp} (przekleństwo zwycięzcy możliwe, ale przedziały są wielokrotnie
węższe od różnic, a **jeden z góry ustalony kandydat `nb_lg` przechodzi test
(oba przedziały < 0 i oba połowy okna < 0) na 49 z 52 rynków**, `nb_pool` na 48, patrz niżej).
`nb_pool`: var = mu + alpha_rynek * mu^2; `nb_lg`: alpha (rynek, liga) z
poolingiem częściowym; `nb_lgmu`: to samo razy kształt zależny od centrum;
`norm_lg`: bieżący normalny, ale z tą wariancją; `cmp`: Conway-Maxwell-Poisson.
Kolumna "gap" = deklarowane minus zrealizowane (pp) na szczeblach o pewności
strony >= 0.70 (p <= 0.95): bieżący -> kandydat.

| rynek | bież. | mecze testu | LL / Brier bież. | rodzina | d log-loss x1000 [95%] | d Brier x1000 [95%] | połowy okna (d LL) | gap pp | werdykt |
|---|---|---|---|---|---|---|---|---|---|
| `goals_for` | NB | 175,031 | 0.4970 / 0.1631 | nb_lg | -3.84 [-4.03; -3.64] | -1.22 [-1.29; -1.15] | -4.1 / -3.6 | +0.11 -> +0.45 | ADOPT |
| `goals_total` | NB | 150,878 | 0.4820 / 0.1571 | nb_lgmu | -2.11 [-2.29; -1.94] | -0.61 [-0.66; -0.55] | -2.1 / -2.1 | -0.71 -> +0.08 | ADOPT |
| `goals_1h_for` | NB | 118,147 | 0.5090 / 0.1693 | nb_lgmu | -2.59 [-2.77; -2.40] | -1.05 [-1.13; -0.97] | -2.9 / -2.3 | +1.05 -> +1.38 | ADOPT |
| `goals_1h_total` | NB | 107,916 | 0.5082 / 0.1678 | nb_lgmu | -1.68 [-1.88; -1.48] | -0.67 [-0.73; -0.60] | -1.5 / -1.9 | +0.13 -> +0.76 | ADOPT |
| `goals_2h_for` | NB | 118,189 | 0.5158 / 0.1719 | nb_lg | -2.68 [-2.83; -2.51] | -1.04 [-1.11; -0.97] | -2.5 / -2.8 | +1.44 -> +1.96 | ADOPT |
| `goals_2h_total` | NB | 107,854 | 0.4988 / 0.1635 | nb_lgmu | -1.67 [-1.88; -1.47] | -0.64 [-0.70; -0.57] | -1.3 / -2.1 | -0.38 -> +0.72 | ADOPT |
| `corners_for` | NB | 31,025 | 0.5134 / 0.1692 | nb_lg | -4.14 [-4.45; -3.76] | -1.20 [-1.31; -1.08] | -4.2 / -4.1 | +0.14 -> +0.23 | ADOPT |
| `corners_total` | norm. | 27,625 | 0.5405 / 0.1803 | nb_lgmu | -1.74 [-2.16; -1.31] | -0.58 [-0.74; -0.41] | -2.2 / -1.3 | -0.84 -> -0.04 | ADOPT |
| `corners_1h_for` | NB | 10,524 | 0.4879 / 0.1592 | nb_lg | -4.17 [-4.78; -3.54] | -1.16 [-1.32; -0.95] | -3.9 / -4.4 | -0.26 -> +0.58 | ADOPT |
| `corners_1h_total` | NB | 9,664 | 0.4756 / 0.1545 | nb_pool | -2.15 [-2.69; -1.63] | -0.55 [-0.70; -0.38] | -2.2 / -2.1 | -1.18 -> -0.00 | ADOPT |
| `corners_2h_for` | norm. | 10,522 | 0.5145 / 0.1697 | cmp | -11.79 [-13.10; -10.29] | -4.48 [-4.98; -3.95] | -12.7 / -10.9 | +1.87 -> +0.57 | ADOPT |
| `corners_2h_total` | norm. | 9,663 | 0.4845 / 0.1581 | cmp | -1.45 [-2.15; -0.63] | -0.31 [-0.60; -0.03] | -1.9 / -1.0 | -0.54 -> +0.58 | ADOPT |
| `cards_points_for` | NB | 20,351 | 0.4589 / 0.1479 | nb_lg | -3.86 [-4.30; -3.43] | -0.82 [-0.96; -0.67] | -3.8 / -3.9 | -2.32 -> -0.58 | ADOPT |
| `cards_points_total` | NB | 18,330 | 0.4880 / 0.1592 | nb_lgmu | -1.98 [-2.57; -1.37] | -0.52 [-0.69; -0.32] | -0.9 / -3.1 | -0.77 -> +0.00 | ADOPT |
| `fouls_for` | norm. | 24,890 | 0.5732 / 0.1942 | nb_lg | -2.48 [-2.79; -2.10] | -0.99 [-1.11; -0.83] | -3.2 / -1.7 | -0.84 -> +0.25 | ADOPT |
| `fouls_total` | norm. | 23,010 | 0.6315 / 0.2203 | nb_lgmu | -1.57 [-1.92; -1.19] | -0.69 [-0.85; -0.52] | -2.5 / -0.6 | +0.09 -> +0.54 | ADOPT |
| `shots_for` | norm. | 22,787 | 0.6188 / 0.2142 | cmp | -3.36 [-3.82; -2.91] | -1.29 [-1.47; -1.10] | -4.9 / -1.9 | +1.98 -> +0.54 | ADOPT |
| `shots_total` | norm. | 21,055 | 0.6348 / 0.2218 | norm_lg | -0.89 [-1.15; -0.66] | -0.37 [-0.47; -0.28] | -0.9 / -0.9 | +0.40 -> +0.30 | ADOPT |
| `shots_on_target_for` | norm. | 26,512 | 0.5053 / 0.1663 | nb_lg | -5.66 [-6.24; -5.14] | -2.01 [-2.24; -1.80] | -6.3 / -5.1 | +0.13 -> +0.42 | ADOPT |
| `shots_on_target_total` | norm. | 24,156 | 0.5309 / 0.1765 | nb_lg | -1.38 [-1.84; -0.96] | -0.38 [-0.56; -0.22] | -1.2 / -1.6 | -0.65 -> +0.27 | ADOPT |
| `offsides_for` | NB | 26,391 | 0.4848 / 0.1582 | nb_lg | -4.22 [-4.62; -3.85] | -1.17 [-1.32; -1.03] | -4.5 / -4.0 | -0.79 -> -0.24 | ADOPT |
| `offsides_total` | NB | 24,058 | 0.4752 / 0.1545 | nb_lg | -2.47 [-2.90; -2.01] | -0.61 [-0.73; -0.49] | -3.1 / -1.8 | -1.04 -> -0.17 | ADOPT |
| `offsides_1h_total` | norm. | 9,497 | 0.5251 / 0.1738 | nb_pool | -3.28 [-5.68; -0.93] | -1.23 [-2.11; -0.41] | -4.1 / -2.4 | +1.29 -> +0.68 | ADOPT |
| `offsides_2h_total` | norm. | 9,496 | 0.5220 / 0.1726 | nb_pool | -4.05 [-6.11; -2.00] | -1.58 [-2.41; -0.79] | -5.4 / -2.7 | +1.10 -> +0.41 | ADOPT |

52 z 52 ocenionych rynków (>= 9 245 meczów w teście) ma najlepszą rodzinę
istotnie lepszą od bieżącej; cztery rynki `fouls_1h_*`/`fouls_2h_*` mają za mało
przypadków statystyk połówkowych (TOO_THIN, **nie ocenione**). Pozostałe rynki
(saves, throw_ins, goal_kicks, tackles, połówki shots / SOT / offsides)
w JSON-ie, wszystkie w tym samym kierunku.

Uwaga o rynkach połówkowych i innych poza listą NB: `corners_2h_for`,
`offsides_1h_for/2h_for`, `shots_*_1h/2h`, `saves_*` itd. są dziś wyceniane
normalnym (nie ma ich w `NEGATIVE_BINOMIAL_METRICS`), mimo średnich 0.5-4;
zysk jest tam największy (corners_2h_for -11.8 [-13.1; -10.3],
offsides_2h_for -20.9, offsides_1h_for -16.8; w JSON). Czy Superbet oferuje te
rynki i czy trafiają na kupon - **niezmierzone** tutaj.

## 3. Pytanie 1: która rodzina

Średnio po rynkach z >= 3 000 meczów testowych (52 rynki):

| rodzina | wynik względem bieżącego |
|---|---|
| Poisson | BETTER 9, bez różnicy 34, WORSE 9: nie jest rodziną, tylko brakiem dyspersji; gorszy o +5.4 na goals_for i +5.4 [4.6; 6.0] na corners_for |
| NB, dyspersja z historii (pool / liga) | BETTER 46 / 46 z 52, WORSE 1 (shots_total), reszta bez różnicy; **zwykle -1.4 do -5.7** |
| NB na wariancji próbki dla każdej metryki (`nb_cur`) | tożsame z bieżącym tam, gdzie NB już jest; na metrykach normalnych: corners_total -0.24, fouls -0.8, SOT_for -1.63, **shots_total +1.79**, shots_for +0.26 (to potwierdza dawny wpis w engine.py o stratach NB na shots, ale przyczyna to szum wariancji próbki, nie skośność) |
| zero-inflated NB | pi = 0 w 48 z 52 rynków (nic do zainflowania); w 4 pi 0.005-0.01 bez zysku (cards_points_total +0.10 [0.07; 0.13] względem NB-pool, czyli gorzej) -> **DON'T** |
| Conway-Maxwell-Poisson (nu 0.5-1.1, jeden parametr na rynek) | statystycznie równy `nb_pool` w większości (np. corners_for +0.02 [-0.05; 0.08]); gorszy od `nb_pool` na goals_for +0.75 [0.71; 0.80], offsides_for +0.19, cards_for +0.07; lepszy na shots_for -0.50 [-0.63; -0.39], tackles_total (-1.1 w JSON) -> brak jednolitej korzyści ponad NB, **DON'T jako zamiennik**, ewentualnie opcja per metryka |
| jądrowy rozkład empiryczny (próbka przesunięta o centrum - średnia, jądro normalne) | WORSE 41 z 52, np. corners_for +9.7 [+9.0; +10.3], goals_for +22.0 -> **DON'T** (próbka n = 8-10 jest za mała) |
| mieszanka 50/50 NB + empiryczny | WORSE 18, bez różnicy 19, BETTER 15 (wszystko słabsze od samego NB z dyspersją z historii) -> **DON'T** |
| mieszanka 50/50 NB(wariancja próbki) + NB(liga) | BETTER 43 z 52, słabsza od samego `nb_lg` na 48 z 52 rynków (corners_for -3.21 wobec -4.14); lepsza tylko na tackles_total (-7.64 wobec -5.15), tackles_for, shots_1h_total, throw_ins_total (różnice <= 0.4) |
| normalny bieżący z wariancją z historii (`norm_lg`) | przechodzi test (oba przedziały i obie połowy < 0) na 39 z 52, ale **gorszy od NB na niskich średnich** (goals_for +11.9, offsides_for +9.6, cards_for +4.5 względem bieżącego) i **najlepszy na shots_total** (-0.89 [-1.15; -0.66], gdzie NB jest gorszy o +0.68 [0.30; 1.13]) |

Wniosek: źródłem zysku jest **dyspersja**, nie egzotyczna rodzina. Waga wariancji
próbki w mieszance `nb_blend` (strojona na walidacji z {0, 0.25, 0.5, 0.75}) wyszła **0 w 47
z 52 rynków** i 0.25 w pięciu: wariancja z 8-10 meczów nie wnosi nic ponad
dyspersję z historii. Rodzina: NB tam, gdzie średnia jest niska (gole, rożne,
kartki, spalone, strzały celne, faule); **normalny z wariancją z historii dla
`shots_total`** (NB dokłada skośność, której nie ma: alpha ~ 0.012).

## 4. Pytanie 2: dyspersja per rynek / liga / drużyna

Hierarchia: jedno alpha na rynek (`nb_pool`) -> alpha ligi z poolingiem
częściowym `(A_c + k a_m) / (B_c + k)` (A = suma (y-mu)^2 - mu, B = suma mu^2,
`nb_lg`) -> alpha drużyny zbite do alpha ligi (`nb_team`). Waga k (strojona na
walidacji, 10..10 000 przypadków) wyszła od 100 do 10 000.

- **Ligowa dyspersja jest prawdziwa, ale mała.** Zgodność połówek (parzyste /
  nieparzyste id meczów) alpha po ligach: r = 0.76 (goals_for, 930 lig),
  0.47 (corners_for, 54 ligi), 0.59 (fouls_for), 0.69 (SOT_for), 0.48 (shots_for),
  0.58 (cards_total); **brak** dla corners_total (r = -0.30, 17 lig) i
  SOT_total (-0.22). Zysk `nb_lg` nad `nb_pool` (d LL x1000 [95%]): cards_points_total
  -1.25 [-1.52; -1.03], goals_for -1.07 [-1.17; -0.96], SOT_total -0.35,
  cards_for -0.29, SOT_for -0.24, shots_for -0.22, goals_total -0.20;
  **corners_for tylko -0.06 [-0.09; -0.04]**, corners_total +0.01 [-0.06; 0.06].
  Istotne na 19 z 52 rynków, praktycznie zerowe na reszcie.
- **Islandia a Premier League (rożne).** Nie do rozstrzygnięcia: Islandia
  (Besta deild karla, id 188) nie ma >= 100 przypadków rożnych w replay
  (statystyki Sofascore nie są tam zbierane) - **niemierzone**. Z tego co jest,
  alpha rożnych (próbka do 2026-03-31, 95%): PL 0.083 [0.043; 0.121],
  Bundesliga 0.138 [0.083; 0.188], LaLiga 0.129 [0.072; 0.226], Eliteserien
  **0.234 [0.142; 0.342]**: Norwegia i PL różnią się istotnie. Dla goli (gdzie
  Islandia jest): PL -0.018 [-0.075; 0.031], Besta deild 0.014 [-0.077; 0.110]
  - nierozróżnialne (po 400-1400 przypadków).
- **Drużyna.** W 16 z 26 rynków `_for` pooling wybrał kt = 10 000 (brak efektu
  drużyny), 3 z kt 3 000, 3 z 1 000; najlepsze przyrosty `nb_team` nad `nb_lg`:
  goal_kicks_1h_for -0.05, goal_kicks_2h_for -0.03, reszta < 0.02 (x1000)
  -> **dyspersja drużynowa nie ma zastosowania** (DON'T).
- **Dyspersja zależna od centrum.** alpha rośnie z mu mocno tylko dla goli
  (goals_for: 0.126 w najniższej piątce wg centrum -> 0.421 w najwyższej;
  var/mean 1.14 -> 2.07). `nb_mu` (alpha_rynek * kształt(mu)) -0.37 [-0.43; -0.30] wobec
  `nb_pool` na goals_for; ale `nb_lg` (-1.07) bije `nb_mu`: ta zależność to w
  dużej mierze proxy ligi. `nb_lgmu` poprawia ponad `nb_lg` co najwyżej o 0.06 (cards_points_total) i
  0.03 (goals_1h_for), bywa gorszy: **DON'T**.
- Wartości alpha (cały trening, dopasowanie MLE): corners_for 0.123, goals_for 0.233,
  offsides_for 0.192, SOT_for 0.086, shots_for 0.079, goals_total 0.053,
  cards_for 0.032, fouls_for 0.017, corners_total 0.021, shots_total 0.012.

## 5. Pytanie 3: sędzia przy kartkach

Pokrycie (czytane z `sofa_event_detail.detail_json`, jedyne miejsce, gdzie
sędzia w ogóle jest; `sofa_listed_event` i `incidents_json` go nie mają:
0 z 20 000 incidentów zawiera słowo "referee"):

- 13 714 wierszy detail, z czego 5 448 zakończonych piłkarskich, **856 z
  sędzią** (karta kariery: yellowCards, redCards, games); statystyk
  skończonych w `sofa_event_stats` jest 460 920 (wszystkie sporty) - czyli
  sędzia dostępny dla **~0.19%** meczów z statystykami.
- 563 mecze z sędzią wpadają w przypadki `cards_points_total`, 454 sędziów,
  **maks. 4 mecze na sędziego**. Estymacja efektu konkretnego sędziego jest
  więc niemożliwa; jedyny dostępny test to kowariata "żółte na mecz w
  karcie kariery" (stan z chwili pobrania; zawiera ten mecz i późniejsze,
  więc to nie jest as-of).
- W próbie 563 meczów: reszta (kartki - centrum) rośnie o **+0.43 pkt [0.24; 0.62]
  na 1 SD żółtych/mecz sędziego** (sd reszty 2.33; bootstrap po meczach). Nie
  jest to pomiar poza próbą ani as-of, więc nie oceniam log-lossu.

Werdykt: **INCONCLUSIVE**. Kierunek jest zgodny z intuicją i istotny
wewnątrz próby, ale pokrycie nie pozwala go zreplayować ani wyestymować per
sędzia; wymagałoby pobierania `/event` sędziego przed meczem dla każdego
fixture (sieć, osobny pomiar). Dalej nie badane.

## 6. Ogony drabinki: gdzie bieżąca rodzina się myli

Średnia deklarowana / zrealizowana `p_over` w przedziałach skrajnych (wszystkie 9
szczebli, bez filtra rozdzielczości; n = liczba szczebli), test 2026-04..10:

| rynek | rodzina | p_over [0.00;0.02) | p_over [0.02;0.05) | p_over [0.05;0.10) | p_over [0.90;0.95) | p_over [0.95;0.98) | p_over [0.98;1.00) |
|---|---|---|---|---|---|---|---|
| `goals_for` | cur | 0.005 / 0.009 (n=1,020,932) | 0.033 / 0.034 (n=338,523) | 0.073 / 0.070 (n=294,994) | 0.919 / 0.880 (n=10,835) | 0.960 / 0.911 (n=1,095) | - |
| `goals_for` | nb_lg | 0.005 / 0.008 (n=1,080,063) | 0.033 / 0.039 (n=326,437) | 0.073 / 0.079 (n=272,964) | 0.916 / 0.912 (n=5,695) | 0.961 / 0.937 (n=268) | - |
| `goals_for` | cmp | 0.005 / 0.009 (n=1,114,439) | 0.033 / 0.041 (n=311,878) | 0.073 / 0.079 (n=259,843) | 0.920 / 0.890 (n=11,089) | 0.960 / 0.922 (n=1,278) | - |
| `corners_for` | cur | 0.016 / 0.041 (n=487) | 0.039 / 0.067 (n=11,310) | 0.076 / 0.095 (n=41,741) | 0.927 / 0.918 (n=32,763) | 0.966 / 0.957 (n=23,564) | 0.986 / 0.975 (n=14,019) |
| `corners_for` | nb_lg | - | 0.041 / 0.050 (n=4,449) | 0.080 / 0.082 (n=48,415) | 0.921 / 0.918 (n=33,056) | 0.971 / 0.970 (n=37,793) | 0.981 / 0.983 (n=1,261) |
| `corners_for` | cmp | - | 0.041 / 0.051 (n=4,902) | 0.079 / 0.083 (n=51,483) | 0.922 / 0.923 (n=31,312) | 0.966 / 0.971 (n=36,349) | - |
| `cards_points_for` | cur | 0.007 / 0.005 (n=98,329) | 0.033 / 0.022 (n=40,965) | 0.072 / 0.049 (n=34,203) | 0.921 / 0.918 (n=8,906) | 0.960 / 0.957 (n=793) | - |
| `cards_points_for` | nb_lg | 0.005 / 0.006 (n=118,924) | 0.033 / 0.031 (n=34,509) | 0.072 / 0.063 (n=28,644) | 0.921 / 0.917 (n=12,929) | 0.959 / 0.950 (n=1,572) | - |
| `cards_points_for` | cmp | 0.005 / 0.006 (n=120,019) | 0.033 / 0.032 (n=33,631) | 0.072 / 0.063 (n=28,271) | 0.921 / 0.914 (n=12,659) | 0.959 / 0.944 (n=1,178) | - |
| `offsides_for` | cur | 0.006 / 0.007 (n=153,496) | 0.033 / 0.028 (n=56,569) | 0.073 / 0.062 (n=46,590) | 0.914 / 0.873 (n=676) | - | - |
| `offsides_for` | nb_lg | 0.006 / 0.007 (n=167,698) | 0.033 / 0.033 (n=52,099) | 0.073 / 0.071 (n=41,757) | - | - | - |
| `offsides_for` | cmp | 0.005 / 0.007 (n=170,411) | 0.033 / 0.033 (n=49,494) | 0.073 / 0.071 (n=40,339) | - | - | - |
| `shots_on_target_for` | cur | 0.012 / 0.037 (n=11,467) | 0.035 / 0.063 (n=25,760) | 0.074 / 0.090 (n=36,641) | 0.926 / 0.932 (n=31,555) | 0.965 / 0.975 (n=33,357) | 0.981 / 0.983 (n=1,086) |
| `shots_on_target_for` | nb_lg | 0.016 / 0.028 (n=2,246) | 0.037 / 0.042 (n=22,991) | 0.075 / 0.082 (n=51,938) | 0.923 / 0.926 (n=24,514) | 0.969 / 0.972 (n=32,547) | 0.983 / 0.982 (n=9,492) |
| `shots_on_target_for` | cmp | 0.016 / 0.028 (n=2,101) | 0.037 / 0.041 (n=22,922) | 0.074 / 0.083 (n=52,722) | 0.924 / 0.930 (n=23,640) | 0.967 / 0.974 (n=37,087) | 0.981 / 0.982 (n=2,717) |
| `shots_for` | cur | - | - | 0.094 / 0.167 (n=234) | 0.906 / 0.840 (n=243) | - | - |
| `shots_for` | nb_lg | - | - | - | - | - | - |
| `shots_for` | cmp | - | - | - | - | - | - |

Pozycja szczebla (0 = najnizsza linia siatki, 8 = najwyzsza), srednie p_over / realizacja, corners_for i goals_for:

| rynek | rodzina | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|---|
| `corners_for` | cur | 0.949 / 0.955 | 0.861 / 0.869 | 0.733 / 0.739 | 0.583 / 0.591 | 0.434 / 0.444 | 0.306 / 0.314 | 0.205 / 0.213 | 0.133 / 0.137 | 0.084 / 0.084 |
| `corners_for` | nb_lg | 0.957 / 0.955 | 0.869 / 0.869 | 0.738 / 0.739 | 0.586 / 0.591 | 0.437 / 0.444 | 0.308 / 0.314 | 0.207 / 0.213 | 0.134 / 0.137 | 0.083 / 0.084 |
| `goals_for` | cur | 0.744 / 0.760 | 0.465 / 0.473 | 0.258 / 0.262 | 0.135 / 0.136 | 0.070 / 0.071 | 0.037 / 0.038 | 0.020 / 0.022 | 0.012 / 0.013 | 0.007 / 0.008 |
| `goals_for` | nb_lg | 0.760 / 0.760 | 0.472 / 0.473 | 0.258 / 0.262 | 0.133 / 0.136 | 0.067 / 0.071 | 0.034 / 0.038 | 0.018 / 0.022 | 0.009 / 0.013 | 0.005 / 0.008 |


Czytanie: w ogonie wysokiego `p_over` (czyli OVER przy ~0.90-0.96 i UNDER przy
niskim `p_over`) bieżący estymator jest **zbyt pewny** wszędzie tam, gdzie zawyża
wariancję próbki z małego n: goals_for 0.960 deklarowane / 0.911 zrealizowane
(n = 1 095; `nb_lg`: 0.961 / 0.937, ale n = 268, bo prawie nie wchodzi w ten
ogon), offsides_for 0.914 / 0.873, shots_for 0.906 / 0.840 (n = 243) i
0.094 / 0.167 na dole. Przy niskim `p_over` corners_for: 0.016 / 0.041 i 0.039 /
0.067 (UNDER przy pewności 0.96 realizuje 0.933), `nb_lg` 0.041 / 0.050.
cards_points_for odwrotnie: bieżący jest **zbyt zachowawczy** w niskim ogonie
(0.033 / 0.022, 0.072 / 0.049), `nb_lg` 0.033 / 0.031. Po stronie >= 0.70
(sekcja 2, kolumna gap) bieżący ma gap od -2.3 pp (cards_for) do +2.0 pp
(shots_for, corners_2h_for +1.9); kandydat mieści się w -0.6..+2.0 pp w tabeli wyżej, ale **nie
jest wyraźnie lepiej skalibrowany** w paśmie >= 0.70 (goals_1h_total +0.1 ->
+0.8, goals_2h_for +1.4 -> +2.0): wygrana jest w *rozróżnianiu* (log-loss,
Brier), a nie w samej kalibracji p, którą i tak poprawia krzywa.

## 7. Wdrożenie (propozycja, nic nie wykonano)

Zmieniłoby się: `engine.sheet_predictive_sd` (źródło wariancji: dziś
`max(var, mean) * centre/mean * (1+1/n)`), `engine.sheet_count_p_raw` /
`engine.uses_negative_binomial` / `NEGATIVE_BINOMIAL_METRICS` (lista
metryk NB; pomiar sugeruje NB dla wszystkich liczników z niską średnią i
normalny z nową wariancją dla `shots_total`), `engine.nb_survival` bez
zmian; wywołujący: `scripts/sofa/run_sheet.py` (linie ~830, ~1170, ~1279),
`scripts/sofa/calibrate_from_cache.py::_settle_sample`
(replay musi liczyć tym samym) oraz `src/bet/sofa/derived.py` (wiersz ~247:
złożenia używają `sheet_predictive_sd`). Nowy plik konfiguracyjny z
alpha (rynek) i alpha (rynek, liga) (nowy `fit_*`), przełącznik w `bet.sofa.epochs`.
**Wymaga refitu krzywych** (zmienia `p_central`, na którym kluczowane są krzywe
`config/sofa_confidence_calibration.json` i evidence linii): nowa epoka
porównywalności; instalacja tylko na polecenie operatora, na kopii bazy.

## 8. Ograniczenia i rzeczy niezmierzone

- alpha dopasowane w replay bez ratingu piłkarskiego w centrum; centrum SHEET
  z ratingiem ma inny rozkład błędu, więc żywe alpha może być niższe -
  **niezmierzone** (sugerowane: dopasowanie na centrum z ratingiem po jego replay).
- Pokrycie lig: statystyki od 2024-11, mało lig z >= 400 przypadkami;
  liga bez danych dostaje alpha rynku (pooling), co jest zachowaniem
  przetestowanym (kc 100..10 000).
- Kandydat wybierany punktowo na teście spośród pięciu - patrz sekcja 2 (jeden
  z góry ustalony `nb_lg`: 49/52, `nb_pool`: 48/52).
- Okno alternatywne (test 2026-07-01..2026-10-07, walidacja od 2026-01-01, 200
  powtórzeń; d LL x1000 względem bieżącego): corners_for nb_pool -4.07 [-4.59; -3.59], nb_lg -4.14;
  goals_for nb_lg -3.75 [-4.06; -3.49]; offsides_for nb_lg -3.98; fouls_for nb_lg -1.87;
  corners_total nb_pool -1.36 [-1.94; -0.83]; cards_points_total nb_lg -3.45
  [-4.42; -2.54] (nb_pool -0.85 [-1.90; 0.08], czyli liga jest tam konieczna);
  shots_total NB nadal **gorszy** (+2.00 [1.51; 2.58]), norm_lg -0.89 [-1.18; -0.54].
- Gap na szczeblach >= 0.70 nie jest kryterium wdrożenia (krzywa to skoryguje);
  podany jako informacja.
- Rynki fouls połówkowe: za mało danych (TOO_THIN).

## 9. Sprzeczności z CLAUDE.md i engine.py

- Komentarz w `engine.py` przy `NEGATIVE_BINOMIAL_METRICS` ("NB przegrywa na
  wysokich shots/fouls") jest prawdziwy tylko przy wariancji próbki: z dyspersją
  z historii NB wygrywa na faulach (fouls_for -2.48 [-2.79; -2.10]) i na
  `shots_for` (-3.08 [-3.61; -2.51]); przegrywa nadal na `shots_total`.
- CLAUDE.md ("Wait for a measurement, not a name" / krzywe z historii) nie jest
  naruszone: pomiar jest na historii, a zmiana wymaga przełącznika w epochs i
  refitu za zgodą operatora (punkty 3 i 4 "Changing the pipeline").
- Brak wpisu w "Measured and declined" o rodzinie rozkładu; ten pomiar odrzuca
  (nie do ponownego proponowania bez nowych danych): ZINB, jądrowy
  empiryczny, mieszankę z empirycznym, dyspersję drużynową, Poissona.

## 10. Powtórzenie

```
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_count_families.py collect --out <dir>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_count_families.py analyse --cases <dir> \
  --test-start 2026-04-01 --val-start 2025-10-01 --reps 300 --out-json r.json --md-out r.md
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_count_families.py referee --cases <dir> --out-json ref.json
```
`collect` ~10 minut (ekstrakcja ~5 min, replay ~5 min, ~4.4 GB RAM), `analyse` ~4 minuty.
