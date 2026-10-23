# Rzeczywisty skład a prognoza statystyk drużyny - górna granica (2026-10-23)

**Pytanie.** Czy znajomość *rzeczywistej* jedenastki (kto wyszedł w pierwszym
składzie) poprawia przedmeczową prognozę liczników drużyny - poza próbą? To
górna granica dla pomysłu "czytaj przewidywane składy Sofascore": przewidywany
skład może być tylko gorszy od rzeczywistego.

**Werdykt.** Dla strzałów, strzałów celnych, rożnych i goli - **brak zysku**
(przedział 95% obejmuje zero w obu podziałach, a w podziale czasowym znak
bywa niekorzystny). Dla fauli - zero w podziale czasowym, ledwie poniżej zera
w podziale parzystym (niespójne). **Jedyny spójny zysk: punkty kartkowe**
(-0.0036 nat [-0.0058, -0.0016] czasowo, -0.0032 [-0.0052, -0.0013]
parzystość) - ok. 0.2% log-loss, Brier na 1.5 -0.0011 przy 0.225. To górna
granica (rzeczywisty skład) wobec słabej bazy bez sędziego; nie jest to
podstawa do zmiany. Pomysł przewidywanych składów dla liczników drużyny -
**zamknięty**. Strona zawodnika: patrz sekcja 5 (realny, mierzalny efekt).

Nic w potoku nie zostało zmienione. Skrypt: `scripts/sofa/measure_lineup_absence.py`
(tylko odczyt, `mode=ro`).

```
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_lineup_absence.py collect --out <f.jsonl.gz>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_lineup_absence.py analyse --features <f.jsonl.gz> --split 2026-05-01 --json <out.json>
```

## 1. Dane

- `data/sofa.db` (żywa baza, tylko odczyt). Mecze piłkarskie z listą składów:
  **15 237** (`calibrate_from_cache.player_targets`: zakończone, bez sparingów,
  jedna lista na mecz). Uwaga: zlecenie zakładało ~54 tys. - w bazie jest
  ~99 tys. wierszy `lineups_json`, ale piłka nożna to ~15 tys. (reszta:
  koszykówka ~61,6 tys., hokej ~11,2 tys., siatkówka ~10,4 tys.).
- Odpadły: 8 182 drużyno-mecze z cienką historią (< 5 wcześniejszych meczów
  ze składem albo ostatni > 45 dni wcześniej), 3 198 meczów, gdzie tylko jedna
  strona miała historię (backfill składów obejmuje drużyny z rynkami
  zawodników), 148 stron bez pełnej jedenastki.
- Zostało: **9 473 mecze, 18 946 drużyno-meczów, 2025-10-10 .. 2026-10-22**.
- Mecze pucharowe (`comparability.is_knockout`): 2 290 drużyno-meczów -
  flaga jest w bazie obu ramion (rotacja w pucharach jest znana przed meczem).

## 2. Cechy (as-of, tylko wcześniejsze mecze drużyny ze składem, okno 10)

| cecha | definicja |
|---|---|
| `miss` | udział "masy startowej" (starty/N) zawodników spoza dzisiejszej XI |
| `miss_core` | odsetek filarów (start w >= 70% meczów okna) spoza XI |
| `miss_att` | udział nieobecnych w strzałach drużyny w oknie |
| `miss_def` | `miss` tylko bramkarze + obrońcy |
| `changes` | zawodnicy XI spoza poprzedniej XI / 11 |

Rozkład (wszystkie 18 946 wierszy):

| | p50 | p90 | p99 |
|---|---|---|---|
| `miss` | 0.373 | 0.536 | 0.745 |
| `miss_core` | 0.222 | 0.500 | 0.889 |
| `miss_att` | 0.404 | 0.598 | 0.796 |
| `miss_def` | 0.333 | 0.558 | 0.776 |
| `changes` | 0.273 | 0.545 | 0.909 |

`miss_core` >= 0.3 (co najmniej ~30% filarów poza składem): **33.7%**
drużyno-meczów; >= 0.5: 12.2%. `miss` jest wysokie u wszystkich (p10 0.236),
bo rotacja rozkłada 11 startów na ~16-18 zawodników - sam `miss` mierzy
głównie rotację.

## 3. Model

Na każdy licznik osobno, Poisson log-liniowy dopasowany na zbiorze uczącym:

- **baza**: `log mu = b0 + b1 log(średnia "za" drużyny) + b2 log(średnia
  "przeciw" rywala) + b3 dom + b4 puchar` (średnie z ostatnich 10 meczów, min. 5);
- **rozszerzony**: baza + 5 cech własnych + te same 5 cech rywala (osłabiona
  obrona rywala -> więcej "za").

Ocena na zbiorze testowym: log-loss NB (dyspersja z metody momentów na
zbiorze uczącym, osobno dla ramienia) i Poissona, Brier na typowych liniach;
delta = rozszerzony - baza (ujemna = skład pomaga); 95% przedział z
bootstrapu meczów (1000 losowań). Dwa podziały: **czasowy** (uczenie przed
2026-05-01, test od 2026-05-01) i **parzystość id** (parzyste uczą,
nieparzyste testują). Baza celowo prosta (bez SHEET, ratingu, prioru ligi,
sędziego) - zysk tutaj byłby warunkiem koniecznym, nie wystarczającym.

## 4. Wyniki (delta log-loss NB, nat na drużyno-mecz)

| licznik | test (wiersze / mecze) czas. | delta czas. [95%] | delta parzystość [95%] | baza NB (czas.) |
|---|---|---|---|---|
| shots_for | 7 470 / 3 735 | +0.00157 [-0.00065, +0.00369] | -0.00161 [-0.00338, +0.00018] | 3.0209 |
| shots_on_target_for | 7 700 / 3 850 | -0.00047 [-0.00225, +0.00145] | -0.00143 [-0.00306, +0.00019] | 2.2508 |
| corners_for | 7 702 / 3 851 | +0.00012 [-0.00207, +0.00235] | -0.00126 [-0.00320, +0.00075] | 2.3786 |
| fouls_for | 7 674 / 3 837 | -0.00071 [-0.00187, +0.00045] | -0.00086 [-0.00170, -0.00007] | 2.7326 |
| goals_for | 8 190 / 4 095 | -0.00015 [-0.00159, +0.00128] | -0.00010 [-0.00124, +0.00113] | 1.5086 |
| cards_points_for | 7 702 / 3 851 | **-0.00358 [-0.00576, -0.00155]** | **-0.00322 [-0.00523, -0.00133]** | 1.7760 |

Brier (delta [95%], podział czasowy; parzystość w nawiasie klamrowym gdy
przedział wyklucza zero):

| licznik | linia | baza | delta |
|---|---|---|---|
| shots_for | 10.5 / 12.5 | 0.1923 / 0.2224 | +0.00043 [-0.00021, +0.00108] / +0.00029 [-0.00035, +0.00099] {12.5 parz.: -0.00073 [-0.00131, -0.00016]} |
| shots_on_target_for | 3.5 / 4.5 | 0.2195 / 0.2317 | -0.00013 [-0.00077, +0.00044] / -0.00017 [-0.00083, +0.00041] |
| corners_for | 4.5 / 5.5 | 0.2374 / 0.2214 | +0.00024 [-0.00059, +0.00102] / +0.00023 [-0.00053, +0.00099] |
| fouls_for | 10.5 / 12.5 | 0.2106 / 0.2251 | -0.00025 [-0.00064, +0.00006] / -0.00025 [-0.00066, +0.00012] |
| goals_for | 0.5 / 1.5 | 0.1847 / 0.2320 | -0.00023 [-0.00058, +0.00012] / +0.00004 [-0.00043, +0.00057] |
| cards_points_for | 1.5 / 2.5 | 0.2254 / 0.2272 | -0.00106 [-0.00178, -0.00033] / -0.00069 [-0.00152, +0.00014] {2.5 parz.: -0.00094 [-0.00168, -0.00018]} |

Duże absencje (`miss_core` >= 0.3), delta NB, podział czasowy: shots_for
**+0.00506 [+0.00126, +0.00894]** (2 824 wiersze - *gorzej*, czyli nadmierne
dopasowanie / niestacjonarność), SOT +0.00007 [-0.00312, +0.00344], corners
+0.00077 [-0.00313, +0.00437], fouls -0.00108 [-0.00279, +0.00045], goals
+0.00075 [-0.00172, +0.00347], cards **-0.00653 [-0.01012, -0.00269]**.
Nawet w meczach z dużymi brakami skład nie pomaga strzałom / rożnym / golom.

Wielkość efektu (zmiana środka na +10 pp cechy, model rozszerzony, czasowo):
`miss_att` -2.5% strzałów, -3.2% SOT, -2.8% goli; `miss` -4.1% rożnych przy
`opp_miss` +3.9% (te dwa znoszą się częściowo; przy parzystości te same
znaki i rzędy). Kartki: `miss` +5.8%, `miss_core` -3.1%, `opp_miss_core`
-2.5%. Efekty są realne co do kierunku (brak strzelców = mniej strzałów), ale
zbyt małe wobec szumu licznika, by przesunąć log-loss.

## 5. Strona zawodnika (pomiar, nie wdrożenie)

Pytanie: gdy najlepszy strzelec drużyny (udział >= 15% strzałów drużyny w
oknie, >= 5 startów) nie wychodzi w XI, czy pozostali startujący oddają więcej
strzałów, niż wynika z ich surowego udziału? Predykcja = udział zawodnika
(jego strzały / strzały drużyny w jego startach, m = 0 - odpowiednik
`bet.sofa.player_share` *bez* ściągania do prioru pozycji) x **rzeczywiste**
strzały drużyny w tym meczu (izoluje sam podział, nie poziom drużyny).

| najlepszy strzelec | drużyno-mecze | faktyczne / przewidziane [95%] |
|---|---|---|
| nieobecny | 5 429 | **1.049 [1.041, 1.057]** |
| obecny | 13 003 | 1.004 [0.999, 1.008] |

Gdy lider strzałów nie gra, pozostali strzelają o ~4.5 pp więcej względem
swojego udziału niż gdy gra - udział nie jest stały, przejmują część jego
wolumenu. Jednocześnie strzały drużyny spadają (`miss_att` -2.5% na 10 pp).
**Podejrzenie (niezmierzone):** model udziału z ściąganiem (m > 0) i
mnożnikiem drużyny SHEET może ten efekt częściowo maskować lub wzmacniać;
czy przekłada się to na lepsze linie zawodników przy cenie Superbetu - nie
zmierzone. Wymagałoby też znajomości składu przed meczem (dla rynków
zawodników Superbet i tak unieważnia niestartujących - skład jest znany ok.
1 h przed meczem).

## 6. Zastrzeżenia

- **Górna granica**: użyto składu rzeczywistego (znany ~1 h przed meczem,
  potwierdzony). Przewidywany skład Sofascore będzie gorszy.
- Baza jest słabsza niż SHEET (brak ratingu, prioru ligi, sędziego, game
  state). Zysk kartkowy może częściowo pochodzić z tego, co SHEET już ma -
  **podejrzenie**: kartki mogą reagować na absencje przez zawieszenia za
  kartki (nieobecny "kartkowicz" = mniej kartek), co jest wiadome przed
  meczem bez składu. Nie zmierzone.
- Historia składów pokrywa ~15 tys. meczów (drużyny z rynkami zawodników,
  od ~2025-10); "okno 10" to 10 ostatnich meczów *ze składem* - luki w
  backfillu skracają okno (warunek: ostatni mecz <= 45 dni wcześniej).
- Wartości strzałów zawodnika: `totalShots`, w braku suma
  celne + niecelne + zablokowane, brak klucza = 0 (tylko do wag cech).
- Jeden zestaw cech, jedno okno (10), jeden próg filara (0.7) - bez
  przeszukiwania (żeby nie dopasować się do testu).
- Pomiar jest tylko pomiarem: żadnego przełącznika, krzywej ani epoki.
