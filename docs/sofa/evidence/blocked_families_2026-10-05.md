# Rodziny rynków zablokowane w CONFIDENCE - 2026-10-05 (plan F1.3)

Plan `docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md`, F1.3: dla każdej rodziny
(klucza rynku) odrzucanej kodem `TENNIS_SET_MARKET_NOT_ADMITTED`,
`DERIVED_NOT_CALIBRATABLE` i `NOT_CALIBRATED` - liczba, decyzja w zapisie,
pomiar (istniejący albo zrobiony tu) i czego brakuje do pomiaru.

Dokument niczego nie zmienia: żadna reguła, krzywa ani konfiguracja nie jest
ruszana. Dopuszczenie rodziny to decyzja operatora między dniami.

## 1. Skąd liczby i jak liczone

- **Kody odmów nie są zapisywane per wiersz.** `run_confidence.py` tylko
  zlicza je w liczniku `refused[...]` (np. `scripts/sofa/run_confidence.py:624`
  DERIVED, `:633` TENNIS_SET, `:666` NOT_CALIBRATED) i wypisuje sumy w
  podsumowaniu. Ani `08_confidence.json`, ani `11_coupon.json`, ani logi nie
  mają rekordu „ten wiersz, ten kod". Żeby rozbić sumy na rodziny, CONFIDENCE
  odtworzono w katalogu roboczym (`/private/tmp/.../scratchpad/runs*`,
  zamrożony zegar `SOFA_NOW`, nakładka zapisująca wiersz za każdym
  zliczeniem). Żaden plik w repo ani w `runs/` nie został zmieniony.
- **Jednostka = jeden wiersz `05_sheet.json`** (mecz, rynek, podmiot, linia,
  kierunek), czyli jeden szczebel w jednym kierunku. Wiersz liczy się raz,
  przy pierwszej bramce, która go odrzuci. Kolejność bramek: ... KICKED_OFF /
  STALE_PRICE, ..., DERIVED_NOT_CALIBRATABLE, PLAYER_PROP_NOT_ADMITTED,
  TENNIS_SET_MARKET_NOT_ADMITTED, OPERATOR_REFUSED, NO_CLASS_CURVE,
  NOT_CALIBRATED.
- **Sumy zależą od zegara**, bo wiersze już odrzucone jako KICKED_OFF nie
  dochodzą do tych bramek:

| zamrożony zegar | TENNIS_SET | DERIVED | NOT_CALIBRATED | KICKED_OFF |
|---|---|---|---|---|
| 08:35Z | 2089 | 1113 | 529 | 3323 |
| **09:50Z** | **1158** | **887** | **405** | 4858 |
| 10:58:44Z (czas ostatniego `08_confidence.json`) | 965 | 827 | 354 | 5972 |

  Liczby planu (1158 / 888 / 405) odpowiadają budowie około 09:50Z; DERIVED
  różni się o 1, a plan nie mówi, z której budowy pochodzą. Odtworzenie z
  10:58:44Z daje dokładnie stan prawdziwego `08` (154 świeże nogi = 211 minus
  57 zablokowanych). **Tabele niżej są z odtworzenia 09:50Z.** Liczby per
  rodzina zostały sprawdzone ponownie z pliku rekordów (sumy 1158 / 887 / 405
  się zgadzają).

## 2. TENNIS_SET_MARKET_NOT_ADMITTED - 1158 wierszy, tylko tenis, 27 meczów

| rodzina | wiersze 10-05 | OVER / UNDER |
|---|---|---|
| games_won_set1_for | 343 | 177 / 166 |
| games_won_set2_for | 334 | 171 / 163 |
| games_set1_total | 243 | 118 / 125 |
| games_set2_total | 238 | 112 / 126 |

**Decyzja w zapisie.**
- `TENNIS_SET_GAMES` (`src/bet/sofa/confidence.py:242-252`): rynek wchodzi
  tylko z nazwy, przez `admitted_tennis_set_markets` w
  `config/sofa_confidence_calibration.json`.
- Klucza nie ma w konfiguracji, więc nic nie jest dopuszczone.
- Uzasadnienie w kodzie: w kandydacie refitu 10-02 nowe krzywe sięgały
  0,80-0,925 (wysyłane kończyły się na 0,60-0,70) i „poza próbą po dacie
  zawyżały o 2-3 pp". Dziury w zakresie, czytane z puli tenisowej, zawyżały
  bardziej.
- Commit `8cfdd50e` (2026-10-02 13:42 +0200, „tennis set admission"); po
  polsku w `docs/sofa/CONFIG.md:265-272`.
- **Decyzji operatora za ani przeciw nie ma w zapisie** - plan F1.3 o nią
  prosi.
- Kod nie ma wiersza w tabeli odmów `docs/sofa/PIPELINE.md`.

**Istniejące pomiary.**
- Liczby „2-3 pp poza próbą" nie ma w żadnym pliku: `data/refit_2026-10-02/compare_report.md`
  wymienia tylko nowe krzywe.
- Te rynki drukowały się wyłącznie w WARIANCIE 09-23..09-25: 157 nóg, z
  czego 150 rozliczonych. Trafiły 114/150 = 0,760 przy średniej pewności
  0,720 i cenie 0,732; ROI przy kursie -0,8%. To pomiar w próbie, bez
  przedziału.
- Krzywe tych czterech rynków powstały tylko z wierszy na żywo (SETTLE): w
  replayu cache jest 0 wierszy.

**Pomiar tutaj** (`scripts/sofa/measure_blocked_families.py`): wiersze na
żywo z `sofa_settled_row` z `p_central >= 0,70`, przedział 95% z
losowania całych meczów.

| rynek | okno | wiersze | mecze | pewność | realizacja | różnica [95%] | cena | ROI przy kursie (n) |
|---|---|---|---|---|---|---|---|---|
| games_set1_total | 09-18..10-04 | 3165 | 1067 | 0,833 | 0,835 | +0,002 [-0,011; 0,015] | 0,838 | -3,4% (2913) |
| games_set2_total | 09-18..10-04 | 3322 | 1113 | 0,836 | 0,835 | -0,001 [-0,014; 0,013] | 0,845 | -4,5% (2929) |
| games_won_set1_for | 09-18..10-04 | 3974 | 1236 | 0,824 | 0,822 | -0,002 [-0,014; 0,011] | 0,838 | -3,7% (3674) |
| games_won_set2_for | 09-18..10-04 | 4081 | 1240 | 0,826 | 0,817 | -0,009 [-0,021; 0,003] | 0,842 | -4,5% (3605) |
| games_set1_total | 09-26..10-04 | 2118 | 723 | 0,832 | 0,831 | -0,001 [-0,017; 0,015] | 0,836 | -3,7% (1866) |
| games_set2_total | 09-26..10-04 | 2284 | 768 | 0,835 | 0,834 | -0,001 [-0,017; 0,015] | 0,844 | -4,6% (1891) |
| games_won_set1_for | 09-26..10-04 | 2471 | 760 | 0,824 | 0,811 | -0,013 [-0,029; 0,003] | 0,837 | -4,5% (2171) |
| games_won_set2_for | 09-26..10-04 | 2594 | 778 | 0,826 | 0,805 | -0,022 [-0,038; -0,005] | 0,840 | -5,6% (2118) |

**Co z tego wynika.**
- Na rozliczonych wierszach pewność dnia zgadza się z realizacją w
  granicach przedziału. Jedyny wyjątek: `games_won_set2_for` od 09-26 zawyża
  o 2,2 pp, a przedział nie zawiera zera.
- Realizacja jest stale poniżej ceny, a ROI wynosi od -3,4% do -5,6%.
- Uwaga: `p_central` tych wierszy to estymator dnia rozliczenia. Do
  2026-10-05 07:15Z w tenisie mieszał cenę, więc nie jest tą krzywą
  statystyczną, przez którą drukowałby dziś kupon.

**Czego brakuje do decyzji.**
- Dopasować cztery krzywe walk-forward po dacie.
- Odtworzyć CONFIDENCE z dopuszczonymi rynkami na rozliczonych dniach
  epoki stats-only.
- Ocenić drukowane nogi z bootstrapem po meczu, według kryterium F2.1.

## 3. DERIVED_NOT_CALIBRATABLE - 887 wierszy (piłka 623, tenis 264), 79 meczów

| rodzina | wiersze 10-05 | rodzina | wiersze 10-05 |
|---|---|---|---|
| handicap_games (tenis) | 206 | both_over_shots_on_target | 36 |
| both_over_goals | 132 | both_over_shots | 32 |
| both_over_corners | 72 | most_shots_on_target | 26 |
| most_corners | 49 | handicap_cards_points | 24 |
| most_cards_points | 48 | most_shots | 20 |
| both_over_cards_points | 43 | both_over_fouls | 14 |
| most_games (tenis) | 39 | most_corners_2h / most_shots_1h / most_shots_2h | 12 każdy |
| handicap_corners | 39 | both_over_offsides / handicap_shots_on_target | 8 każdy |
| most_corners_1h | 36 | tenis: most_aces_set1/2, most_double_faults_set1/2, most_serve_points_set2 | 3 każdy |
| | | tenis: most_serve_points_set1 2; most_aces 1; most_serve_points 1 | |

**Decyzja w zapisie.**
- `DERIVED_PREFIXES = ("both_over_", "handicap_", "most_")`
  (`src/bet/sofa/confidence.py:89-97`).
- Uzasadnienie w kodzie: „2-252 rozliczonych wierszy na rynek", żadna
  próbka jednej strony nie sięga rozkładu łącznego, a każdy wiersz niesie
  `ONE_SIDED_LADDER` i `NO_MARKET_MARGINAL`.
- Commit `da5cefe3` (2026-09-19): 44 z 54 kandydatów opierało się na
  both_over_*.
- Od `00ebbef6` (2026-10-01) `scripts/sofa/fit_confidence.py:202-214` w
  ogóle pomija rynki pochodne w dopasowaniu. Liczenie ich jako „actual >
  line" nie zgadzało się z zapisanym wynikiem w 351/1243 wierszy handicapu i
  197/431 wierszy most_ z 09-30.
- Dlatego w pliku kalibracji nie ma żadnej krzywej dla rynku pochodnego.

**Rodziny i sposób wyceny.**
- both_over_: min(a, b) powyżej progu; most_: a > b albo remis; handicap_:
  różnica.
- `bet.sofa.derived` liczy je z rozkładów brzegowych każdej strony.
  `bet.sofa.joint` łączy strony kopułą Gaussa z korelacją zmierzoną per
  metryka.

**Stan danych.** Liczba „2-252" z komentarza jest nieaktualna: dziś jest
10 866 wierszy na żywo `both_over_goals` i 12 166 `handicap_games`.

**Pomiar tutaj** (wiersze na żywo, p >= 0,70, 09-18..10-04; pełna tabela w
wyjściu skryptu):

| rynek | wiersze | mecze | pewność | realizacja | różnica [95%] | cena | ROI (n) |
|---|---|---|---|---|---|---|---|
| both_over_goals | 1638 | 1616 | 0,801 | 0,696 | -0,106 [-0,129; -0,084] | 0,701 | -5,7% (1632) |
| both_over_corners | 1133 | 492 | 0,835 | 0,803 | -0,032 [-0,057; -0,007] | brak | -9,2% (708) |
| both_over_cards_points | 262 | 199 | 0,814 | 0,672 | -0,142 [-0,201; -0,088] | 0,695 | -9,4% (262) |
| both_over_shots_on_target | 362 | 218 | 0,807 | 0,760 | -0,048 [-0,094; -0,003] | brak | -5,6% (237) |
| both_over_shots | 267 | 144 | 0,797 | 0,712 | -0,085 [-0,161; -0,016] | brak | -1,6% (245) |
| both_over_fouls | 84 | 57 | 0,774 | 0,643 | -0,131 [-0,249; -0,011] | brak | -6,6% (66) |
| most_corners | 61 | 61 | 0,768 | 0,557 | -0,210 [-0,325; -0,090] | 0,598 | -12,7% (61) |
| handicap_corners | 135 | 122 | 0,773 | 0,519 | -0,254 [-0,347; -0,158] | 0,524 | -10,1% (135) |
| handicap_cards_points | 83 | 68 | 0,781 | 0,687 | -0,094 [-0,202; 0,005] | 0,692 | -6,1% (83) |
| handicap_games (tenis) | 972 | 481 | 0,782 | 0,664 | -0,118 [-0,161; -0,079] | 0,654 | -9,6% (691) |
| most_games (tenis) | 27 | 27 | 0,742 | 0,370 | -0,372 [-0,550; -0,188] | 0,536 | -25,4% (25) |
| most_aces (tenis) | 29 | 29 | 0,824 | 0,655 | -0,169 [-0,334; -0,001] | 0,745 | -19,4% (28) |
| pozostałe most_* (piłka i tenis) | 2-39 każdy | | | | przedziały szerokie, po obu stronach zera | | |

- Od 09-26 obraz jest ten sam: both_over_goals -0,126 [-0,158; -0,096],
  handicap_games -0,065 [-0,129; -0,005].
- Zgadza się to z wcześniejszą notatką: przewaga modelu na handicapie
  tenisowym to antysygnał (memory `tennis-handicap-model-edge-is-anti-signal`,
  -22% na 87 wierszach).

**Co z tego wynika.** Model pochodny stale zawyża: both_over_goals o ~11 pp,
handicap_games o ~12 pp, handicap_corners o ~25 pp. Odmowa jest zmierzona,
nie tylko zadeklarowana.

**Czego brakuje do dopuszczenia.**
- Krzywa dopasowana na wyniku ocenianym po stronie
  (`run_settle._settle_derived`), nie „actual > line", sprawdzona poza próbą.
- Cena po devigu dla rynków jednostronnych. both_over_corners / _shots /
  _shots_on_target nie mają dziś `market_p`.

## 4. NOT_CALIBRATED - 405 wierszy (piłka 340, tenis 65), 39 meczów

Reguła: `run_confidence.py:663-667` - brak pomiaru dla tego kubełka, „liczba
modelu nie jest zamiennikiem". Trzy przyczyny:

**(a) Rynek ma własną krzywą, ale twierdzenie leży na jej zmierzonym suficie
lub nad nim** (`confidence.py:1344-1365`, „cisza powyżej zmierzonego zakresu
jest dowodem").

| rodzina | wiersze 10-05 | sufit krzywej |
|---|---|---|
| corners_1h_for | 35 | 0,70 |
| corners_1h_total | 14 | 0,80 |
| corners_2h_for | 25 | 0,60 |
| corners_2h_total | 20 | 0,60 |
| goals_1h_for | 20 | 0,70 |
| goals_2h_for | 17 | 0,80 |
| goals_2h_total | 4 | 0,85 |
| shots_on_target_1h_total | 1 | 0,60 |
| tenis sets_total | 11 (w tym 4 z klasy tennis_women) | 0,70; klasa 0,60 |
| tenis tiebreaks_total | 7 | 0,60 |
| tenis serve_points_for | 5 | 0,60 |

Sufity połówek wynikają z rozmiaru kubełka, a nie z danych. Przykład:
goals_2h_total ma 993 wiersze na żywo z p >= 0,85, ale rozłożone na cztery
kubełki, każdy poniżej `min_market_bucket` = 400. W replayu cache połówek
nie ma wcale.

**(b) Brak krzywej i zakaz pożyczania puli** (`AWAITING_OWN_CURVE`,
`confidence.py:167-180`, commit `8eec9217` z 2026-09-25):
- piłka: fouls_2h_for 16 / _total 8; shots_2h_for 10 / _total 8;
  shots_on_target_2h_for 16 / _total 8; offsides_1h_for 16 / _total 8;
  offsides_2h_for 16 / _total 8; saves_1h_for 16 / _total 24;
  throw_ins_1h_for 16 / _total 8; throw_ins_2h_for 16 / _total 8;
- tenis: per-set aces / double_faults / serve_points dla setów 1 i 2
  (`_for` po 4, `_total` po 2; razem 36) oraz serve_points_total 6.
- Strażnik zdejmuje się sam, gdy rynek dostanie własną krzywą. Dla połówek
  wcześniej może to zrobić tylko refit z `--with-halves` - otwarta decyzja
  operatora nr 7 w `docs/sofa/history/RAPORT_NOC_2026-10-04.md:78`.

**(c) Propsy bez kubełka OVER przy tej pewności** (krzywa OVER kończy się
na 0,75): player_shots_on_target_for 1, player_offsides_for 1.

**Pomiar tutaj** (wiersze na żywo, p >= 0,70, 09-18..10-04):

| rynek | wiersze | mecze | pewność | realizacja | różnica [95%] | cena | ROI (n) |
|---|---|---|---|---|---|---|---|
| corners_1h_for | 1065 | 362 | 0,819 | 0,772 | -0,047 [-0,076; -0,019] | 0,799 | -8,0% |
| corners_1h_total | 1548 | 564 | 0,808 | 0,819 | +0,011 [-0,010; 0,031] | 0,795 | -1,4% |
| corners_2h_for | 473 | 97 | 0,834 | 0,744 | -0,089 [-0,129; -0,053] | 0,788 | -9,1% |
| corners_2h_total | 476 | 94 | 0,839 | 0,792 | -0,046 [-0,094; -0,004] | 0,827 | -8,1% |
| goals_1h_for | 1920 | 925 | 0,858 | 0,838 | -0,021 [-0,037; -0,004] | 0,843 | -4,6% |
| goals_2h_for | 2325 | 968 | 0,836 | 0,828 | -0,007 [-0,024; 0,007] | 0,831 | -4,1% |
| goals_2h_total | 5040 | 2425 | 0,802 | 0,825 | +0,023 [0,013; 0,033] | 0,827 | -3,8% |
| sets_total | 605 | 605 | 0,764 | 0,744 | -0,020 [-0,056; 0,013] | 0,739 | -4,0% |
| tiebreaks_total | 175 | 175 | 0,839 | 0,857 | +0,018 [-0,032; 0,065] | 0,837 | +0,5% |
| serve_points_for | 86 | 69 | 0,788 | 0,442 | -0,346 [-0,464; -0,242] | 0,534 | -18,9% |
| aces_set1_for | 71 | 60 | 0,782 | 0,465 | -0,317 [-0,437; -0,197] | 0,545 | -16,5% |
| double_faults_set2_total | 38 | 37 | 0,756 | 0,368 | -0,388 [-0,550; -0,223] | 0,561 | -40,8% |
| serve_points_set2_for | 46 | 40 | 0,773 | 0,478 | -0,295 [-0,431; -0,159] | 0,520 | -17,2% |
| player_shots_on_target_for | 593 | 77 | 0,834 | 0,762 | -0,072 [-0,109; -0,034] | brak | -23,7% (123) |
| połówki strzałów / fauli / spalonych / obron / autów | 1-25 każdy | | | | za mało (pierwszy wiersz 09-26) | | |

**Co z tego wynika.**
- Tenisowe rynki serwisu w secie zawyżają o 18-42 pp, co potwierdza notatkę
  z 2026-09-30: 149/253 = 0,589 przy pewności 0,777.
- Rożne w połówce dla jednej drużyny zawyżają o 5-9 pp.
- goals_2h_total i corners_1h_total nie zawyżają; goals_2h_total jest
  nawet o 2,3 pp poniżej realizacji. Tu odmowa jest artefaktem sufitu
  kubełka, a nie zmierzonym zawyżeniem.
- Każda rodzina ma ROI poniżej zera albo za mało wierszy, żeby cokolwiek
  powiedzieć.

**Czego brakuje do decyzji.**
- Dla (a): refit z mniejszym `min_market_bucket` dla połówek, albo z
  replayem `--with-halves` - decyzja operatora, między dniami.
- Dla (b): wiersze na żywo zbierają się od 09-26; przy obecnym tempie
  (1-25 wierszy z p >= 0,70 na rodzinę) do kryterium F2.1 (300 nóg) potrzeba
  tygodni. Szybciej da to tylko replay.

## 5. Zastrzeżenia

- `p_central` w `sofa_settled_row` to estymator dnia rozliczenia (przed
  epoką stats-only w tenisie mieszał cenę), a nie krzywa stats-only.
- Liczone są wszystkie wiersze z p >= 0,70, nie tylko te, które kupon by
  wziął. To pomiar „czy rodzina zawyża", nie wynik kuponu.
- Oba kierunki szczebla są zapisane, więc tabela „wszystkie wiersze" dałaby
  ~0,5 z konstrukcji. Dlatego tylko pasmo p >= 0,70.
- Zagnieżdżone linie jednego meczu są skorelowane; przedziały losują całe
  mecze.
- Wiersze z replayu cache (`run_date LIKE 'cache%'`) są pominięte. Dla tych
  rodzin ich nie ma, z wyjątkiem dwóch propsów.

Odtworzenie: `PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_blocked_families.py --min-p 0.70 [--from 2026-09-26]`
(baza tylko do odczytu; liczby z 2026-10-05 po południu, ostatni dzień
rozliczony 10-04).
