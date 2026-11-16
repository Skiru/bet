# Audyt symulacji meczów - live 2026-11-06 17:30Z .. 2026-11-10 (2026-11-11)

Trzy modele symulacyjne weszły razem 11-06 17:30Z (tenis per-set games od 11-06 00:00Z):

- **piłka** - symulator minutowy (`FOOTBALL_SIM`, rynki ścieżki: HT/FT, połowy, obie połowy, combo goli w połowach; próg 0.60 dla 4 kluczy),
- **tenis** - model punkt po punkcie (`TENNIS_POINT_MODEL` - gemy w secie, asy, podwójne, punkty serwisowe; `TENNIS_HANDICAP_POINT_MODEL` - handicap gemów w secie),
- **siatkówka** - model wymian (`VB_POINT_MODEL`).

Audyt tylko do odczytu: nic nie zmieniono w kodzie, konfiguracji ani bazie. To **audyt krzywych**, nie powód do zmiany - 5 dni to szum, a "weszło" nie wchodzi do następnej decyzji.

Metoda (wspólna): nogi wydrukowane z `11_coupon.json`, rozliczone z `13_results.json` (oceny księgi); stawka płaska 1, przed podatkiem; 95% CI z bootstrapu po meczach (2 000 losowań). "Ile pomaga" = Brier skill score modelu wobec (a) estymatora, który zastąpił, (b) ceny Superbetu bez marży, (c) dla piłki - częstości bazowej (rynki ścieżki nie miały wcześniej modelu). Ujemny ΔBrier = model lepszy.

Główne liczby wydrukowanych nóg sprawdzone niezależnie skryptem (piłka 1 315 nóg / trafność 0.704 / ROI -7.6%; tenis 558 / 0.819 / -4.0%; siatkówka 410 / 0.795 / +3.8%) - zgodne co do cyfry.

## Odpowiedź w jednym zdaniu

Symulacje pomagają **w kalibracji, nie w pieniądzach**: tenis per-set games o ~1% (Brier, CI dotyka 0), piłka o 1.1-1.4% względem częstości bazowej, siatkówka live **nie** jest lepsza od modelu wyników (-0.9%); **żadna nie bije ceny** (piłka -1.7%, siatkówka -3.5%, tenis handicap per set gorszy z CI bez zera; tenis per-set games = cena).

## 1. Piłka - symulator minutowy

### Wydrukowane nogi

| zakres | nogi / mecze | pewność | 1/kurs | trafność | traf. - pewność (pp) | traf. - 1/kurs (pp) | ROI |
|---|---|---|---|---|---|---|---|
| **razem 11-06..11-10** | **1 315 / 773** | .715 | .762 | .704 | **-1.0 [-3.6, +1.5]** | -5.8 [-8.3, -3.2] | **-7.6% [-11.0, -4.2]** |
| tsbh UNDER >= 0.70 | 580 / 501 | .784 | .835 | .772 | -1.1 [-4.5, +2.3] | -6.2 | -7.3% |
| tsbh UNDER próg 0.60 | 286 / 276 | .664 | .707 | .626 | -3.8 [-9.4, +1.7] | -8.1 | -11.4% [-19.4, -3.7] |
| half_goals_combo próg 0.60 | 337 / 293 | .650 | .696 | .662 | +1.2 [-4.0, +6.3] | -3.4 | -5.0% |
| half_goals_combo >= 0.70 | 60 / 60 | .732 | .770 | .750 | +1.8 [-9.5, +11.9] | -2.0 | -3.1% |
| btts_any_half UNDER próg | 33 | .623 | .670 | .576 | -4.7 [-22.8, +13.4] | -9.4 | -13.8% |
| btts_halves próg | 19 | .618 | .666 | .632 | +1.4 [-20.0, +22.5] | -3.4 | -5.1% |

Dzienne ROI: 11-06 -4.9%, 11-07 -8.5%, 11-08 -5.7%, 11-09 -26.4% (28 nóg), 11-10 -10.1%. 11 zwrotów i 4 nieznane poza tabelą. 11-06 / 11-07 `btts_any_half` UNDER i `btts_halves` "Nie/Nie" to jedno zdarzenie (liczone podwójnie do `SAME_EVENT_DEDUP` 11-08).

- Udział w kuponie: 4.5% nóg (1 330 z 29 467), -99.5 z -1 494.1 j. ROI kuponu z nimi **-5.16%**, bez nich **-5.05%** - symulator odjął ~0.1 pp. Pozostała piłka w tych dniach: -5.2%, traf. - pewność +0.7 pp.
- Hold-out zapowiadał +1.9 pp [+0.2, +3.6] i ROI -4.2%; live -1.0 pp i -7.6%. Przedziały zachodzą tylko na 0.2-1.5 - nieco gorzej, ale nie wyraźnie inaczej. Pasma progu zgodne z hold-outem (combo +2.9 -> +1.2; tsbh UNDER -2.3 -> -3.8).

### Wszystkie rozliczone linie (45 608 wierszy, 2 080 meczów; z ceną bez marży 30 096 / 1 090)

| porównanie | Brier | skill | ΔBrier [95% CI] |
|---|---|---|---|
| model vs częstość bazowa globalna | .1896 vs .1916 | **+1.1%** | -.0020 [-.0040, .0000] |
| model vs częstość bazowa ligi | .1896 vs .1923 | **+1.4%** | -.0027 [-.0045, -.0008] |
| model vs cena bez marży | .1896 vs .1864 | **-1.7%** | +.0032 [+.0019, +.0046] |
| (cena vs częstość bazowa) | .1864 vs .1916 | +2.7% | |

Częstość bazowa z backfillu `football_sim_lines.jsonl.gz` 10-14..11-05 (przed mierzonymi dniami); cena bez marży proporcjonalnie w pełnych partycjach wyników (mediana marży 12.1%); `htft` nie ma pełnej partycji - niezmierzony.

- Wyraźna przewaga nad częstością bazową tylko `team_scores_both_halves` (+3.8%) i `result_2h` (+2.7%); reszta +-1.2%. Względem ceny gorszy w każdym rynku poza `higher_scoring_half` (+0.1%).
- `p_central` przeszacowuje na górze: 0.7-0.8 -> 0.748 vs 0.705 (n 995), >= 0.9 -> 0.918 vs 0.848 (n 79). Krzywa + line evidence to w większości ściąga (pewność 0.7-0.8: 0.752 vs 0.789 zrealizowane).
- Oceny: 24 losowe wiersze zgodne z własnym przeliczeniem HT/FT; pełny przebieg 44 221 wierszy - 36 niezgodności na 10 meczach, wszystkie z payloadów `/event` pobranych ponownie 11-11 (period1 0-0 vs incydent HT). Dwie wydrukowane nogi na tych meczach ocenione dobrze. Jeden mecz (16788836, htft) nierozstrzygnięty - dotyczy tylko przyszłego regrade.
- Pokrycie: 11-10 104 mecze -> 91 symulowanych: 11 `NO_PRICE`, 2 polskie amatorskie bez rynków ścieżki. Superbet tych rynków tam nie wystawia - nie defekt.

## 2. Tenis - model punkt po punkcie

### Wydrukowane nogi (558 ocenionych / 133 mecze; 34 zwroty - krecze, 3 nieznane)

| zakres | nogi / mecze | pewność | 1/kurs | trafność | traf. - pewność (pp) | traf. - 1/kurs (pp) | ROI |
|---|---|---|---|---|---|---|---|
| **razem** | **558 / 133** | .803 | .853 | .819 | **+1.6 [-1.6, +4.6]** | -3.4 [-6.7, -0.3] | **-4.0% [-7.9, -0.4]** |
| gemy w secie | 487 / 132 | .807 | .857 | .823 | +1.6 [-2.0, +5.0] | -3.4 | -3.9% [-8.3, +0.1] |
| - OVER | 171 / 105 | .808 | .869 | .877 | +6.9 [+2.0, +11.4] | +0.9 | +1.3% |
| - UNDER | 316 / 128 | .807 | .851 | .794 | -1.2 [-6.4, +3.5] | -5.7 | -6.8% |
| serwis (asy, podwójne, punkty) | 71 / 12 | .776 | .827 | .789 | +1.3 [-9.9, +10.3] | -3.8 | -4.7% |
| handicap gemów w secie | 0 | - | - | - | - | - | - |

2.0% nóg kuponu, 33% nóg tenisowych. Hold-out: +0.6 pp [-0.4, +1.6], ROI -5.0% - live zgodny. Handicap per set nie wydrukował nic (`NEGATIVE_LEG_EV`, `THIN_SAMPLE_FOR_BUILDER`, poniżej progu).

### Wszystkie rozliczone linie (7 255; cena bez marży z pary OVER/UNDER)

| rodzina | linie / mecze | Brier model - stary | Brier model - cena | p >= 0.70: deklarowane -> zrealizowane |
|---|---|---|---|---|
| gemy w secie | 4 193 / 389 | **-0.0017 [-0.0039, +0.0003]** (skill 1.0%) | -0.0007 [-0.0024, +0.0009] | .837 -> .844 |
| serwis, mecz | 792 / 38 | niezmierzone | +0.0034 [-0.0085, +0.0151] | .772 -> .748 |
| serwis, set | 1 198 / 38 | niezmierzone | +0.0060 [-0.0036, +0.0156] | .792 -> .723 |
| handicap w secie | 1 004 / 153 | niezmierzone | **+0.0078 [+0.0010, +0.0148]** | .783 -> .763 |

- Stary estymator odtworzony tylko dla gemów w secie (`forecast_p` = stare `p_central` na 100% wierszy 11-04/11-05). Dla serwisu i handicapu brak starego p - wymagałoby ponownego SHEET z wyłączonymi przełącznikami (poza audytem tylko do odczytu).
- Gemy w secie: jak hold-out (-0.0021) i na poziomie ceny; dzień po dniu znak się zmienia - zysk niestabilny na 5 dniach.
- Handicap w secie gorszy od ceny z CI bez zera (hold-out +0.0030 - szerzej live). Reguła operatora 11-06 nie wymaga bicia ceny - nie powód do wyłączenia, ale do obserwacji.

### Przed / po (gemy w secie, wydrukowane)

| okres | nogi / dzień | ocenione / mecze | traf. - pewność | ROI |
|---|---|---|---|---|
| 10-30..11-05, stary estymator | 147 | 948 / 272 | -3.4 [-6.3, -0.7] | -9.6% [-13.0, -6.3] |
| 11-06..11-10, model punktowy | 103 | 487 / 132 | +1.6 [-2.0, +5.0] | -3.9% [-8.3, +0.1] |

Mniej nóg (~-30%), z przeszacowania -3.4 pp na skalibrowane; ROI ~+5.7 pp lepiej - **nie przyczynowo** (w tym samym oknie: nowe krzywe, refit 11-06 17:30Z, dzienne line evidence i podział puli tenisa od 11-08, inny miks turniejów), formalnego testu różnicy nie robiono.

Spot-check 5 nóg z cache Sofascore (gemy setu, asy, podwójne): wszystkie ocenione poprawnie.

## 3. Siatkówka - model wymian

### Wydrukowane nogi (11-06 17:30Z .. okno 11-10)

| zakres | nogi / mecze | pewność | 1/kurs | trafność | traf. - pewność (pp) | traf. - 1/kurs (pp) | ROI |
|---|---|---|---|---|---|---|---|
| **model wymian, razem** | **410 / 158** | .789 | .764 | .795 | **+0.6 [-4.6, +5.5]** | +3.1 [-1.9, +8.0] | **+3.8% [-3.5, +10.7]** |
| model wyników, te same rodziny 10-27..11-06 | 229 / 163 | .764 | .748 | .725 | -3.9 [-10.3, +2.4] | -2.3 | -3.3% [-11.9, +5.2] |
| set_winner | 249 / 105 | .779 | .765 | .799 | +2.0 [-2.8, +6.6] | +3.4 | +4.3% |
| winner | 85 / 85 | .808 | .779 | .800 | -0.8 [-9.5, +6.5] | +2.1 | +1.3% |
| set_handicap | 61 / 56 | .814 | .772 | .803 | -1.1 [-11.6, +8.4] | +3.2 | +4.7% |
| kontrola: rodziny nadal na modelu wyników, 11-07..11-10 | 156 / 82 | .789 | .819 | .808 | +1.8 [-3.7, +7.4] | -1.1 | -1.0% |

Lepszy wynik wydruku to w dużej części okres: kontrola (rynki bez modelu wymian) też się poprawiła (wcześniej -2.6 pp). Przedziały obu modeli zachodzą na siebie.

### Wszystkie rozliczone linie (4 678 / 304 mecze, linie z oboma p)

| rodzina | n / m | Brier wymiany - wyniki | wymiany - cena | hold-out wymiany - wyniki |
|---|---|---|---|---|
| points_handicap | 397 / 176 | **+0.0248 [+0.0073, +0.0431]** (gorszy) | +0.0198 | -0.0048 |
| points_total | 433 / 249 | -0.0024 [-0.0116, +0.0078] | +0.0095 | -0.0052 |
| set_handicap | 419 / 218 | -0.0000 [-0.0104, +0.0110] | +0.0038 | -0.0057 |
| exact_sets | 1 656 / 276 | +0.0008 [-0.0016, +0.0033] | +0.0020 | -0.0014 |
| set_points_total | 283 / 214 | **-0.0101 [-0.0202, -0.0005]** (lepszy) | +0.0037 | -0.0069 |
| set_winner | 906 / 282 | +0.0009 [-0.0038, +0.0059] | +0.0070 | -0.0033 |
| winner | 302 / 302 | -0.0009 [-0.0098, +0.0084] | +0.0172 | -0.0059 |
| **razem** | 4 678 / 304 | **+0.0016 [-0.0028, +0.0064]** (skill -0.9%) | **+0.0063 [+0.0002, +0.0127]** (-3.5%) | -0.0030 [-0.0049, -0.0011] |

- Live model wymian **nie potwierdza** przewagi z hold-outu (-0.0030 -> +0.0016). Kobiety: lekko lepszy (-0.0035 [-0.0087, +0.0015]); mężczyźni: gorszy (+0.0068 [+0.0002, +0.0139]).
- points_handicap przy pewności >= 0.70: **-22.5 pp [-37.9, -7.1]** (n 80; model wyników -8.8) - przeszacowanie z hold-outu (-19.7) się potwierdza; line evidence przepuściła tylko 3 nogi, ale dziura jest otwarta. set_handicap +1.0, winner +3.6, set_winner +1.4 - zgodnie z hold-outem.
- Pokrycie: 34% zdarzeń bez pinu Sofascore (165 `NOT_ON_SOFASCORE`) - strata wspólna obu modelom; brak p wymian tylko na 26 liniach przypiętych zdarzeń; płeć: 0 meczów "(K)" z męskim side-outem. Niezmierzone: bo3 jako bo5, przewaga gospodarza na neutralnym terenie. 59 wydrukowanych nóg bez klucza w backfillu - prawdopodobnie późne okno pod inną datą, niesprawdzone.
- Spot-check 4 nóg z wynikami setów: wszystkie poprawne.

## 4. Wnioski

| model | vs poprzedni estymator | vs cena | wydruk: traf. - pewność | wydruk ROI |
|---|---|---|---|---|
| piłka - symulator | brak poprzednika; vs częstość bazowa +1.1..1.4% | **-1.7%** | -1.0 pp | -7.6% (kupon -5.16% z, -5.05% bez) |
| tenis - gemy w secie | **+1.0%** (CI dotyka 0) | ~0 (+0.4%) | +1.6 pp | -3.9% |
| tenis - handicap w secie | niezmierzone | gorszy (CI bez 0) | 0 nóg | - |
| tenis - serwis | niezmierzone | gorszy (CI z 0), 38 meczów | +1.3 pp (12 meczów) | -4.7% |
| siatkówka - wymiany | **-0.9%** (CI z 0); points_handicap gorszy | **-3.5%** | +0.6 pp | +3.8% (kontrola też w górę) |

1. Symulacje nie dały przewagi nad ceną w żadnym sporcie - zgodnie z tym, co mówiły hold-outy (instalacja z reguły "lepsze niż obecne", nie "lepsze niż cena").
2. Kalibracja wydruku trzyma się (wszystkie przedziały traf. - pewność zawierają 0) - to jest rzeczywista korzyść: wydrukowana liczba mniej kłamie, zwłaszcza w tenisie (z -3.4 pp na +1.6 pp).
3. Zastrzeżenia do obserwacji (podejrzenia, nie decyzje - każda zmiana wymaga pomiaru i zgody operatora):
   - siatkówka points_handicap: gorsza od modelu wyników live i -22.5 pp przy >= 0.70;
   - siatkówka mężczyźni: lekko gorsza od modelu wyników;
   - piłka: `p_central` symulatora przeszacowuje powyżej 0.7 (krzywa łata), pasmo progu tsbh UNDER -11.4% ROI;
   - tenis handicap w secie: gorszy od ceny szerzej niż w hold-oucie.
4. Ponowny pomiar po ~3 tygodniach własnych rozliczonych wierszy (~4x więcej meczów), te same skrypty.

Skrypty i dane: `/private/tmp/claude-501/-Users-mkoziol-projects-bet/f2d2e839-59e7-4c56-b692-988597ecb3e2/scratchpad/{football_sim,tennis_point,vb_rally}/` (katalog sesji - skopiować, jeśli mają zostać).
