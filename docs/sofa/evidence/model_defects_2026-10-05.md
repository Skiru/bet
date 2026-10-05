# Defekty modelu, stałe niedopasowane i cechy kontekstu - pomiar 2026-10-05

Plan `docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md`, zadania **F2.2, F2.3, F3.1,
F3.2**. Wszystko offline: baza `data/sofa.db` otwarta tylko do odczytu, bez mostka,
bez Superbetu, bez żadnego `fit_*` / `prepare_refit`. Dzień 10-05 trwa, a krzywe
pewności (refit `6fea99fd`) są dopasowane do dzisiejszego `p_central` - **każda
zmiana modelu czeka za nową stałą `bet.sofa.epochs.MODEL_FIXES_FROM_UTC = None`**
(wyłączona). Operator włącza ją razem z następnym refitem (`prepare_refit.py`),
między dniami. Stała jest czytana z zegara ściennego, nie z `SOFA_NOW`: replay
cache refitu i replay SHEET „as of” muszą liczyć tym estymatorem, który opiszą nowe
krzywe.

Narzędzie pomiaru: `scripts/sofa/measure_model_defects.py` (podkomendy
`nb-variance`, `promotion`, `context --feature ...`, `bench-cards`), na wspólnym
loaderze `scripts/sofa/measure_sample_composition.load` (ten sam odczyt meczu co
SAMPLES: gole po 90 minutach, bez statystyk meczu z dogrywką, bez towarzyskich,
próbka goli z własnych rozgrywek dla meczu ligowego). Okno: mecze
2025-08-01..2026-10-03 (cechy rundy, składu i sędziego do 10-04). **Przedziały 95%
z losowania całych meczów** (bootstrap 1000 razy, `paired_interval`), plus znak w
dwóch połowach parzystości id meczu. `d` = kandydat - obecnie; **ujemne = lepiej**.

## Podsumowanie

| # | pozycja | czy nadal istnieje | pomiar (poza próbą) | decyzja |
|---|---|---|---|---|
| D1 | wariancja NB przy przesuniętym środku - **piłka** | **nie** - naprawione 2026-10-02 (`engine.sheet_predictive_sd`, `engine.py:287-317`) | goals_for log-loss -0,01008 [-0,01045; -0,00971]; corners_for -0,00707; offsides_total -0,00166; goals_total -0,00025 | potwierdzone; zostaje. Uwaga: goals_1h_total bez zysku (Brier 0,5: +0,00042 [+0,00001; +0,00084], 5 906 meczów) - do decyzji przy reficie |
| D1 | wariancja NB przy przesuniętym środku - **tenis** | **tak** - `sheet_predictive_sd` skaluje tylko `sport == "football"` | aces_for -0,01394 [-0,01497; -0,01295], aces_total -0,00564, double_faults_for -0,00463, double_faults_total -0,00170 (wszystkie przedziały < 0, obie połowy) | **naprawione za flagą** (`TENNIS_DISPERSION_SCALED_METRICS`); games_total pominięte (Brier linii mieszany) |
| D2 | awans / spadek w próbie (Zaragoza 6/10, Girona 4/10) | **tak** (próba bierze najnowsze 10 bez względu na ligę; reguła własnych rozgrywek od 10-04 tylko dla goli i dopiero od 5 meczów) | strona dotknięta = 3,4% przypadków goals_for; reszta: goals_for -0,214 [-0,235; -0,190], corners_for -0,206, fouls_for +0,318. Wyrzucenie meczów z innej ligi **nie pomaga** (goals_for -0,0078 [-0,0160; +0,0002]; corners_for +0,0207 [+0,0085; +0,0345] gorzej) | **notatka** `OTHER_DIVISION_SAMPLE` za flagą (pokazywana, nie bramka); próbka bez zmian. Jako korekta środka: goals_for -0,00011 [-0,00016; -0,00006] - kandydat F3.2 |
| D3 | kartki trenerów w `cards_points` | **nie** - naprawione 2026-10-02 (`metrics._is_staff_card`, `metrics.py:711`, użyte w `:758` i `:819`) | - | zostaje |
| D3' | kartki rezerwowych, którzy nie weszli (regulamin Superbetu ich nie liczy) | **tak** (`metrics.py:799-801`, docstring `calculate_cards_points`) | 149 z 4 023 meczów z /lineups (3,70%) ma taką kartkę, 1,32 pkt na mecz, średnio 0,049 pkt na mecz | **zmierzone, bez naprawy**: wymaga /lineups (w cache 4 551 meczów piłki z ~900 tys.); reguła `time == -5` jest niejednoznaczna (122 takie kartki dostali gracze, którzy grali) |
| D4 | `MIN_ODDS` 1,0867 surowsze niż sufity krzywych | **tak** (`confidence.py:288-289`, `run_confidence.py:159`, `:447`) | 20 z 51 krzywych `by_market` ma sufit > 0,9202 (do 0,9843); 10-05: 212 z 783 wierszy pod progiem miałoby x >= 0,90; rozliczone 09-19..10-04: piłka n=6 655, ROI -3,66% [-4,43; -2,91] | **decyzja operatora** (to warunek zakładu, nie model); bez zmian |

Cechy kontekstu (F3.2), Poisson log-loss średniej z próbki z korektą
`log(lam) = log(średnia) + a + b.x`, `a`, `b` dopasowane na jednej połowie id,
oceniane na drugiej; porównanie z samym `a` (żeby globalne przesunięcie próbki nie
zostało przypisane cesze):

| cecha | goals_total | goals_for | corners_total | yellow_cards_total | werdykt |
|---|---|---|---|---|---|
| runda (początek / koniec sezonu) | **-0,00173 [-0,00200; -0,00147]** | **-0,00111 [-0,00128; -0,00095]** | **-0,00034 [-0,00060; -0,00005]** | **-0,00063 [-0,00095; -0,00035]** | przechodzi (najsilniejsza) |
| puchar / play-off vs liga | -0,00001 [-0,00003; +0,00002] | **-0,00008 [-0,00012; -0,00004]** | -0,00002 [-0,00018; +0,00013] | **-0,00018 [-0,00034; -0,00003]** | przechodzi dla goals_for i kartek, minimalnie |
| odpoczynek / natłok | **-0,00015 [-0,00023; -0,00008]** | -0,00002 [-0,00006; +0,00002] | -0,00007 [-0,00034; +0,00020] | -0,00009 [-0,00029; +0,00010] | przechodzi tylko goals_total, minimalnie |
| strona z innej ligi (awans / spadek) | **-0,00009 [-0,00014; -0,00004]** | **-0,00011 [-0,00016; -0,00006]** | +0,00005 [-0,00001; +0,00010] | +0,00005 [-0,00002; +0,00011] | przechodzi dla goli |
| sędzia (żółte kartki / mecz w karierze) | - | - | - | -0,00279 [-0,01122; +0,00675] (499 meczów) | **notatka** - przedział obejmuje 0 |
| nieobecni (`missingPlayers`) | - | -0,00015 [-0,00120; +0,00095] (2 645 meczów) | - | - | **notatka** - przedział obejmuje 0 |
| pogoda | - | - | - | - | **brak danych** w cache (Sofascore nie podaje jej w przechowywanych payloadach) |

**Żadna cecha kontekstu nie weszła dziś do modelu.** Te, które przechodzą kryterium,
są kandydatami na następny refit (sekcja 6): korekta środka wymaga dopasowania
współczynników między dniami i tej samej korekty w replayu cache, inaczej krzywa
opisze inny `p_central`. Wszystkie te pomiary są względem **surowej średniej z
próbki**, nie pełnego środka SHEET (shrink do bazy ligi K_CENTRE, rating) - przed
instalacją trzeba je powtórzyć względem `p_central` replayu.

---

## 1. F2.2 / D1 - wariancja rozkładu ujemnego dwumianowego przy przesuniętym środku

**Defekt (09-25):** SHEET przesuwa środek (shrink do bazy ligi przez `K_CENTRE`,
rating), a wariancja NB zostawała wariancją surowej próbki (Brazylia U0,5 -12,9 pp;
188 wierszy >= 5 pp; Livingston P(0) = 0,71).

**Stan w kodzie:** dla piłki naprawione 2026-10-02 (`8cfdd50e`):
`engine.sheet_predictive_sd` (`src/bet/sofa/engine.py:287`) skaluje wariancję i
średnią przez `centre / mean` (zachowuje indeks dyspersji), wołane w
`scripts/sofa/run_sheet.py:1144` i w replayu `scripts/sofa/calibrate_from_cache.py:727`,
`:980`. Dla tenisa **nadal**: warunek `sport == "football"`. W epoce stats-only
środek tenisa przesuwa się do bazy poziomu (`tennis_prior.tier_prior`, `K_CENTRE`
tenis = 5, czyli o 1/3 przy n = 10) dla aces / double faults / games_total /
sets_total.

**Pomiar:** `measure_model_defects.py nb-variance --sport {football|tennis}`.
Środek = `n/(n+K) * średnia + K/(n+K) * baza` (piłka: baza rozgrywek z
`config/sofa_league_baselines.json`, K = 15; tenis: baza płeć x poziom x
nawierzchnia z `config/sofa_tennis_tier_baselines.json`, K = 5, tylko do trzech
setów, próbka = ostatnie 10 meczów gracza na porównywalnej nawierzchni). „Obecnie”
= surowa wariancja, „kandydat” = `sheet_predictive_sd` (wariancja x centre/mean).
Ocena: log-loss NB zrealizowanej liczby i Brier P(> linia). Bazy są dopasowane na
tej samej historii (to samo dla obu ramion - porównujemy tylko wariancję).

Piłka (naprawa już zainstalowana - potwierdzenie z przedziałem):

| metryka | przypadki | d log-loss NB [95%] | Brier głównej linii | środek przesunięty > 20%: d log-loss |
|---|---|---|---|---|
| goals_for | 709 191 | -0,01008 [-0,01045; -0,00971] | 0,5: -0,00217 [-0,00225; -0,00210] | -0,02031 [-0,02118; -0,01947] |
| goals_total | 335 246 | -0,00025 [-0,00040; -0,00010] | 1,5: +0,00009 [+0,00007; +0,00012]; 3,5: -0,00010 | +0,00315 [+0,00022; +0,00619] (5 834) |
| corners_for | 121 851 | -0,00707 [-0,00772; -0,00639] | 4,5: -0,00013 [-0,00019; -0,00008] | -0,02677 [-0,02960; -0,02400] |
| offsides_total | 47 196 | -0,00166 [-0,00210; -0,00125] | 3,5: -0,00022 [-0,00027; -0,00018] | -0,01086 [-0,01934; -0,00200] |
| offsides_for | 104 878 | -0,00651 [-0,00724; -0,00583] | 1,5: +0,00013 [+0,00001; +0,00024] | -0,01321 [-0,01524; -0,01112] |
| goals_1h_for | 31 059 | -0,00364 [-0,00482; -0,00247] | 0,5: +0,00015 [-0,00018; +0,00048] | -0,00398 [-0,00623; -0,00190] |
| goals_2h_for | 33 033 | -0,00324 [-0,00430; -0,00200] | 1,5: -0,00009 [-0,00014; -0,00004] | -0,00298 [-0,00549; -0,00089] |
| goals_1h_total | 5 906 | +0,00018 [-0,00114; +0,00161] | 0,5: +0,00042 [+0,00001; +0,00084] | +0,00587 [-0,00159; +0,01259] (581) |

Wniosek: naprawa piłkarska jest właściwa tam, gdzie środek naprawdę się przesuwa
(goals_for, rożne, spalone). Na `goals_total` przy dużym przesunięciu i na
`goals_1h_total` jest bez zysku lub minimalnie gorsza - do rozważenia przy reficie
(np. wyłączyć skalowanie dla tych dwóch); dziś **nic nie zmieniono** w piłce.

Tenis (defekt nadal w kodzie):

| metryka | przypadki | d log-loss NB [95%] | parzyste / nieparzyste | Brier linii |
|---|---|---|---|---|
| aces_for | 128 641 | **-0,01394 [-0,01497; -0,01295]** | -0,01389 / -0,01398 | 2,5: -0,00085; 4,5: -0,00019; 6,5: +0,00005 |
| aces_total | 52 067 | **-0,00564 [-0,00636; -0,00503]** | -0,00606 / -0,00521 | 5,5: -0,00029; 8,5: -0,00003; 11,5: +0,00004 |
| double_faults_for | 130 616 | **-0,00463 [-0,00527; -0,00396]** | -0,00455 / -0,00472 | 1,5: -0,00117; 2,5: -0,00069; 3,5: -0,00023 |
| double_faults_total | 52 068 | **-0,00170 [-0,00205; -0,00134]** | -0,00155 / -0,00185 | 3,5: -0,00043; 5,5: -0,00029 |
| games_total | 86 694 | -0,00045 [-0,00052; -0,00038] | -0,00041 / -0,00049 | 20,5: **+0,00011** [+0,00011; +0,00012]; 22,5: +0,00002; 24,5: -0,00004 |

**Naprawa (za flagą):** `engine.TENNIS_DISPERSION_SCALED_METRICS` = aces_for,
aces_total, double_faults_for, double_faults_total; `sheet_predictive_sd` skaluje je
jak piłkę, gdy `epochs.model_fixes_enabled()`. games_total pominięty: log-loss
lepszy, ale Brier linii, na których się gra, mieszany - a krzywa czyta
prawdopodobieństwo linii. Ta sama funkcja liczy SHEET i replay cache, więc po
włączeniu flagi refit dopasuje krzywe do nowego `p_central`. Test:
`tests/sofa/test_model_fixes_epoch.py`.

## 2. F2.2 / D2 - awans i spadek w próbie

**Defekt:** próbka strony to jej 10 najnowszych meczów bez względu na ligę;
beniaminek przynosi mecze z niższej ligi (Zaragoza 6/10, Girona 4/10). Od 10-04 gole
w meczu ligowym biorą mecze własnych rozgrywek (`comparability.pick_same_competition`,
`samples.py:1353-1368`), ale dopiero od 5 takich meczów i nic poza golami.

**Detektor** (`measure_model_defects.other_division`, w potoku
`schedule.other_division_matches`): w 10 najnowszych meczach strony >= 3 mecze
ligowe (REGULAR) **innej ligi tego samego kraju** (kategorii) **i** strona nie grała
w lidze meczu ligowo przed bieżącym sezonem (ma historię sprzed sezonu, ale żadnego
meczu ligowego tych rozgrywek). Drugi warunek odsiewa Apertura / Clausura (dwie
rozgrywki jednego kraju) i krajowy drugi turniej.

| metryka | przypadki oznaczone | udział | reszta (rzecz. - średnia próbki) [95%] | d log-loss bez meczów innej ligi [95%] | parz. / nieparz. |
|---|---|---|---|---|---|
| goals_for | 23 306 | 3,39% | **-0,214 [-0,235; -0,190]** | -0,00782 [-0,01602; +0,00023] | -0,00779 / -0,00785 |
| goals_total | 19 392 | 5,64% | -0,088 [-0,118; -0,062] | +0,00243 [-0,00083; +0,00557] | +0,00530 / -0,00044 |
| corners_for | 3 665 | 3,11% | -0,206 [-0,294; -0,115] | **+0,02073 [+0,00846; +0,03446]** (gorzej) | +0,02795 / +0,01351 |
| corners_total | 3 345 | 5,68% | +0,017 [-0,106; +0,140] | +0,00440 [-0,00098; +0,01004] | |
| shots_for | 1 717 | 2,03% | -0,204 [-0,456; +0,036] | -0,00901 [-0,03770; +0,01981] | |
| fouls_for | 2 763 | 2,83% | **+0,318 [+0,155; +0,488]** | +0,01065 [-0,00750; +0,02584] | |
| yellow_cards_for | 4 115 | 3,26% | +0,070 [+0,030; +0,114] | +0,00515 [-0,00163; +0,01135] | |

Wniosek: próbka takiej strony **jest** przesunięta (gole i rożne zawyżone, faule
zaniżone - zgodne z beniaminkiem), ale prosta naprawa próbki (wyrzucić mecze innej
ligi) nie poprawia prognozy poza próbą - zostawia za mało świeżych meczów, a rożne
psuje. Zmierzone jako bez efektu dla naprawy próbki. Jako korekta środka (cecha
F3.2, sekcja 5) daje goals_for -0,00011 [-0,00016; -0,00006], goals_total
-0,00009 [-0,00014; -0,00004] (współczynnik własnej strony -0,065 / -0,057, czyli
ok. -6% goli) - kandydat na refit.

**Wdrożone (za flagą):** notatka `OTHER_DIVISION_SAMPLE(home 7/10 from another
league of its country)` w `FixtureSchedule.flags()` (`src/bet/sofa/schedule.py`),
liczona w SAMPLES (`samples.py`, `fixture_schedule(..., category_name)`), trafia na
nogę jako `context_flags` i na PDF jak `LONG_LAYOFF`. Pokazywana, nigdy bramka;
liczona tylko gdy `model_fixes_enabled()`. Pole `SideSchedule.other_division`
domyślnie 0, więc stare `03_samples.json` czytają się bez zmian. Test:
`tests/sofa/test_other_division_note.py`.

## 3. F2.2 / D3 - kartki w `cards_points`

- **Kartki sztabu:** naprawione 2026-10-02 (`8f186dca`): `metrics._is_staff_card`
  (`metrics.py:711`) - `manager` bez `player` - pomijane w `cards_not_recorded`
  (`:758`) i `calculate_cards_points` (`:819`). Defekt nie istnieje.
- **Kartki rezerwowych, którzy nie weszli** (regulamin Superbetu, Komunikat 06/2022:
  „kartki pokazane ... zawodnikom na ławce rezerwowych nie będą brane pod uwagę”) -
  nadal liczone; docstring `calculate_cards_points` (`metrics.py:799-801`) mówi to
  wprost. Pomiar (`measure_model_defects.py bench-cards`) na 4 023 meczach piłki z
  /lineups (minutesPlayed) i /incidents w cache: **149 meczów (3,70%)** ma kartkę dla
  rezerwowego bez minut, **1,32 pkt** na taki mecz, średnio **0,049 pkt** na mecz
  (przy średniej cards_points_total ok. 4,5 to ok. 1%). 159 z 169 takich kartek ma
  `time = -5` (jak kartki sztabu). Ale `time = -5` dostało też 122 graczy, którzy
  grali (kartka po zejściu / po gwizdku) - reguła „pomiń -5” byłaby niejednoznaczna
  wobec regulaminu.
- **Decyzja:** zmierzone, bez naprawy. Czysta naprawa wymaga /lineups dla każdego
  meczu próbki i rozliczenia (cache: 4 551 meczów piłki z /lineups na ~900 tys.) i
  odczytu regulaminu dla zawodnika, który zszedł. To dotyczy też **rozliczenia**
  (SETTLE czyta ten sam `calculate_cards_points`) - ok. 3,7% meczów może być
  rozliczonych o 1-2 pkt za wysoko. Do decyzji operatora: (a) zapytać Superbet o
  zawodnika po zmianie, (b) backfill /lineups dla meczów z rynkiem kartek.

## 4. F2.2 / D4 - `MIN_ODDS` 1,0867 a sufity krzywych

`confidence.CONFIDENCE_CEILING = 0.9202` (`confidence.py:288`) pochodzi ze starej
krzywej łącznej; `MIN_ODDS = 1/0.9202 = 1.0867` (`run_confidence.py:159`) odrzuca
nogę jako ODDS_TOO_LOW (`run_confidence.py:447`) **zanim** policzy pewność.
Uzasadnienie („poniżej nie da się mieć dodatniego EV”) pochodzi z reguły x > 1,0;
od 10-05 reguła to x >= 0,90.

- Krzywe `config/sofa_confidence_calibration.json` (refit 10-05): 20 z 51
  `by_market` ma najwyższy `realised_lo95` > 0,9202 - player_assists_for 0,9843,
  tackles_for 0,9628, cards_points_for 0,9524, goals_total 0,9446, goals_for 0,9445,
  offsides_total 0,9444 ... shots_on_target_total 0,9223; łączne: piłka 0,9427,
  tenis 0,9257.
- 10-05 (`05_sheet.json`): 783 wiersze pod progiem, z tego **212** z x >= 0,90 przy
  krzywej (goals_total 47, goals_for 40, games_won_set2_for 27, corners_total 25);
  10-04: 1 293, z tego 543.
- Rozliczone 09-19..10-04 (`sofa_settled_row`), wiersze pod progiem z x >= 0,90 przy
  dzisiejszej krzywej (bez innych bramek CONFIDENCE, `p_central` z ówczesnych
  arkuszy): piłka n = 6 655 (1 980 meczów), realizacja 0,9271 vs pewność 0,9079
  (+1,93 pp [+1,26; +2,65]), **ROI -3,66% [-4,43; -2,91]**; tenis n = 1 262 (793
  mecze), realizacja 0,8994 vs 0,8618, **ROI -3,88% [-5,83; -2,09]**.

Wniosek: próg jest niespójny z krzywymi, ale to **warunek zakładu**, nie model, a
nogi, które by wpuścił, tracą jak reszta kuponu (marża). Bez zmian; decyzja
operatora (jak MAX_DISAGREEMENT - między dniami).

## 5. F3.2 - cechy kontekstu, osobne pomiary log-loss

Metoda (`measure_model_defects.py context --feature ...`): dla każdego meczu
ligowego (REGULAR; dla `knockout` także pucharowe) średnia z próbki SAMPLES jest
prognozą, korekta `log(lam) = log(średnia) + a + b.x` (GLM Poissona z offsetem)
dopasowana na jednej połowie parzystości id, oceniona na drugiej (oba kierunki).
`d` = log-loss z cechą - log-loss z samym `a`. Kryterium planu: cecha wchodzi tylko
z przedziałem poprawy < 0.

**Runda** (sezon ma długość z **poprzedniego** sezonu tych rozgrywek - pierwsza
wersja brała najwyższą rundę bieżącego sezonu, co w trwającym sezonie nazywa dwie
najnowsze kolejki „ostatnimi”; odrzucona jako przeciek):

| metryka | przypadki | d [95%] | współczynniki (połowa 0 / 1), względem środka sezonu |
|---|---|---|---|
| goals_total | 265 285 | -0,00173 [-0,00200; -0,00147] | ostatnie 2 kolejki +0,114 / +0,105; ostatnie 20% +0,053 / +0,055; kolejki 1-3 -0,020 / -0,027 |
| goals_for | 543 811 | -0,00111 [-0,00128; -0,00095] | +0,115 / +0,110; +0,054 / +0,061; -0,037 / -0,040 |
| corners_total | 53 168 | -0,00034 [-0,00060; -0,00005] | -0,011 / -0,003; +0,011 / +0,007; -0,024 / -0,022 |
| yellow_cards_total | 57 185 | -0,00063 [-0,00095; -0,00035] | -0,060 / -0,076; -0,036 / -0,043; -0,017 / -0,005 |

Koniec sezonu: ok. +11% goli i -6% żółtych kartek wobec średniej próbki; początek
sezonu: -2..-4% goli. Najsilniejsza cecha z mierzonych (dla porównania: reguła
własnych rozgrywek z 10-04 dała goals_for -0,0055).

**Puchar / play-off vs liga** (`comparability.match_kind`): goals_total -0,00001
[-0,00003; +0,00002]; goals_for -0,00008 [-0,00012; -0,00004] (KNOCKOUT -0,043 /
-0,032); corners_total -0,00002 [-0,00018; +0,00013]; yellow_cards_total -0,00018
[-0,00034; -0,00003] (KNOCKOUT -0,042 / -0,053).

**Odpoczynek / natłok** (`bet.sofa.schedule`; ten sam odczyt co
`measure_schedule_context.py`, którego tabela reszt z 10-04 jest w
`data/analysis_2026-10-04_history/schedule_context.md`: przerwa >= 21 dni goals_total
-0,122 [-0,155; -0,092]): goals_total -0,00015 [-0,00023; -0,00008] (>= 21 dni
-0,033 / -0,034); goals_for -0,00002 [-0,00006; +0,00002]; corners_total -0,00007
[-0,00034; +0,00020]; yellow_cards_total -0,00009 [-0,00029; +0,00010]. Reszta jest
realna, ale grupa mała - zysk w log-loss znikomy. Nadrobiony mecz (MAKEUP_FIXTURE)
był zmierzony 10-04 bez efektu.

**Strona z innej ligi** (detektor z sekcji 2 jako cecha): goals_total -0,00009
[-0,00014; -0,00004]; goals_for -0,00011 [-0,00016; -0,00006] (własna -0,065 /
-0,057); corners_total +0,00005 [-0,00001; +0,00010]; yellow_cards_total +0,00005
[-0,00002; +0,00011].

**Sędzia:** Sofascore podaje sędziego z jego kartkami w karierze tylko w `/event/{id}`
(`sofa_event_detail`: 875 z 6 432 meczów piłki, od 2026-09-18; 691 sędziów).
`02_fixtures.json` ma pole `referee` wypełnione dla 6-24% meczów piłki dnia (09-26..10-05).
Cecha `log(żółte / mecz w karierze)`, sędziowie z >= 10 meczami: yellow_cards_total
-0,00279 [-0,01122; +0,00675] (499 meczów), yellow_cards_for -0,00227 [-0,00678;
+0,00248] (501). Kierunek spójny (elastyczność +0,18..+0,30), przedział obejmuje 0
- **notatka**. Uwaga: liczby kariery są z chwili pobrania (zwykle przed meczem;
późniejsze pobranie zawiera ten mecz - jeden z ok. 100+).

**Nieobecni** (`missingPlayers` z /lineups, typ `missing`, nie `doubtful`): goals_for
-0,00015 [-0,00120; +0,00095] (2 645 meczów; własni +0,011 / +0,014, rywala -0,005 /
-0,019) - **notatka**. Lista z cache jest pobrana po meczu (sekcja 7), więc nie wiemy,
ile z niej było znane przed startem.

**Pogoda:** brak w jakimkolwiek przechowywanym payloadzie - niemierzalne bez nowego
źródła (zasada: tylko Sofascore + Superbet).

## 6. F2.3 - `UNFITTED_CONSTANTS` (14 pozycji)

Lista z `runs/sofa/2026-10-05/08_confidence.json` (`unfitted_constants`); znacznik
stawia `run_sheet.py:1498-1499` (i `derived.py:799`) na każdym wierszu, który
przez stałą przeszedł. Na `05_sheet.json` 10-05 (17 747 wierszy, stats-only):
K_PRICE i MAX_LADDER_SIGMA na wszystkich, W_FOOTBALL_RATING + 9 stałych ratingu na
2 726; K_TENNIS_LADDER_CENTRE i W_TENNIS_RATING tylko na nogach zablokowanych z
porannego (przed-stats-only) wydruku. **Znacznik nie jest zdejmowany.**

| stała | gdzie | co robi | wpływa na pewność w epoce stats-only? | plateau offline? | plan na następny refit |
|---|---|---|---|---|---|
| K_PRICE | `engine.py:9`; czyt. `run_sheet.py:859`; `bar_probability`, UNREACHABLE_BAR (`:1480`) | waga ceny w `p_bar` (06_coupon, selektor VALUE) | **nie** (cena poza `p_central`; UNREACHABLE_BAR wyłączony) | dopasowanie istnieje: `fit_constants` krzywa Brier maleje do K = 1000 (sama cena) - status NOT_FITTED | stała opisuje tylko 06_coupon (nie kupon): albo zostawić znacznik tylko na wierszach starej epoki, albo usunąć z `p_bar`; decyzja przy refit |
| MAX_LADDER_SIGMA | `engine.py:8`; `run_sheet.py:1456` | werdykt LEAN zamiast VALUE gdy drabina się nie zgadza | **nie** (tylko werdykt 06) | zmierzone: NO_DIVERGENCE na 263 022 wierszach (pasma deklarowane = zrealizowane) - progu nie da się dopasować, bo nic nie rozróżnia | usunąć z modelu (bramka bez sygnału) albo zostawić jako 06-only |
| K_TENNIS_LADDER_CENTRE | `run_sheet.py:199` | shrink środka tenisa do środka drabiny (ceny) | **nie** (`not stats_only`, `run_sheet.py:1072`, `:1380`) | dopasowany na MAE środka (płasko 15-100), nie na prawdopodobieństwie | epoka stats-only go nie używa - usunąć ze ścieżki stats-only po wygaśnięciu nóg starej epoki |
| W_TENNIS_RATING | `tennis_rating.py:93` | waga ratingu tenisa wobec ceny | **nie** (rating tylko jako `forecast_p`) | Brier płaski 0,10-0,30 na 5 dniach | jak wyżej |
| W_FOOTBALL_RATING | `football_rating.py:124` | waga ratingu wobec środka próbki | **tak** (środek piłki, 2 726 wierszy 10-05) | **tak**: replay cache z W w {0; 0,25; 0,5; 0,75; 1}, kryterium jak K_CENTRE (największe W w 0,0005 od minimum Brier), walk-forward po dniach; dziś wybrane na 5 dniach (Brier 0,1952 / 0,1932 / 0,1928 / 0,1938 / 0,1963) | dopasować w refit jako `config/sofa_engine_constants.json` W_FOOTBALL_RATING |
| ALPHA_STRENGTH | `football_rating.py:163` | krok uczenia siły ligi | tak (przez rating) | tak - wybrane na błędzie kwadratowym środka; dopasowanie na log-loss / Brier możliwe w `measure_football_rating.py` (siatka) | siatka {0,01..0,05}, plateau, okno 06-01..08-15 / walidacja 08-15..09-30 jak dotąd, ale na prawdopodobieństwie |
| MIN_STRENGTH_LINKS | `football_rating.py:164` | min. meczów bez łącznika, by liga miała siłę (inaczej UNLINKED) | tak (decyduje o UNLINKED - odmowie) | częściowo: wpływa na pokrycie, nie tylko błąd; siatka {5, 10, 20} z raportem pokrycia | siatka z kosztem pokrycia; decyzja operatora |
| MAX_SURPRISE | `football_rating.py:169` | obcięcie zaskoczenia jednego wyniku | tak | tak (siatka {2, 3, 5}) | jak ALPHA_STRENGTH |
| LINK_MIN_MATCHES | `football_rating.py:161` | min. meczów w jednych rozgrywkach, by dwie drużyny były „połączone” | tak (LINKED / UNLINKED) | wybrane ręcznie; siatka {2, 3, 5} możliwa | jak MIN_STRENGTH_LINKS |
| CROSS_RATIO_POWER | `football_rating.py:179` | shrink współczynników przy meczu z inną ligą | tak | już płasko 0,5-0,7 (błąd kwadratowy) | potwierdzić plateau na log-loss |
| LINK_WINDOW_S | `football_rating.py:160` | okno łączenia (365 dni) | tak | strukturalne; siatka {180, 365, 730} d możliwa | jedna siatka z raportem, potem decyzja |
| TEAM_COMP_MEMORY | `football_rating.py:162` | pamięć rozgrywek drużyny (40 meczów) - domena | tak | strukturalne; siatka {20, 40, 80} | jak wyżej |
| MIN_GROUP_TEAMS | `football_rating.py:385` | min. drużyn w grupie, by grupa była własną ligą | tak (podział lig na grupy) | to podział, nie wynik - nie dopasowuje się na prawdopodobieństwie; czułość: ile meczów zmienia jednostkę | zmierzyć czułość; jeśli znikoma - zadeklarować jako regułę strukturalną (udokumentowaną), wtedy wolno zdjąć ze znacznika |
| GROUP_STAGE_MIN_MATCHES | `football_rating.py:386` | min. meczów w etapie grupy | jak wyżej | jak wyżej | jak wyżej |

Kryterium F2.3 („lista pusta”) w tym przebiegu **nie jest spełnione**: nic nie
zostało dopasowane (zakaz `fit_*` w trakcie dnia). Cztery stałe (K_PRICE,
MAX_LADDER_SIGMA, K_TENNIS_LADDER_CENTRE, W_TENNIS_RATING) nie dotykają pewności w
epoce stats-only - ich droga do usunięcia to zawężenie znacznika do wierszy, na
które działają, a to jest zmiana artefaktu do zrobienia razem z refitem, nie dziś.

## 7. F3.1 - dostępność składów przed meczem (co mówi cache)

`sofa_event_stats.lineups_json`: 51 598 payloadów, wszystkie meczów zakończonych.
Czas pobrania względem startu (`fetched_at` - `startTimestamp` z `sofa_listed_event`):

| sport | payloady | `confirmed` true / false / brak | `missingPlayers` (niepuste) | pobranie po starcie: min / p5 / mediana | przed startem |
|---|---|---|---|---|---|
| piłka | 4 551 | 4 369 / 70 / 112 | 3 460 (76%) | 2,6 h / 103,8 h / 4 357 h | **0** |
| koszykówka | 34 037 | 2 788 / 28 498 / 2 751 | 22 (NBA) | 9,3 h / 2 737 h / 8 360 h | **0** |
| hokej | 9 707 | 6 788 / 1 092 / 1 827 | 0 | 5,8 h / 217 h / 8 234 h | **0** |
| siatkówka | 3 281 | 0 / 1 158 / 2 123 | 0 | 72,6 h / 689 h / 6 388 h | **0** |

(22 payloady bez wiersza w `sofa_listed_event`, pominięte.) Typy `missingPlayers`:
`missing` 13 594, `doubtful` 3 974; kody `reason` 1 (15 644), 11 (683), 13 (368), 3,
4, 0, 12, 2 - znaczenia kodów Sofascore nie podaje w payloadzie, nie są tu
interpretowane. Ligi z `missingPlayers` (piłka, 62 rozgrywki): MLS 462, Liga
Profesional 376, Brasileirão Série B 321, LaLiga 2 309, Brasileirão 227 ...

**Cache nie odpowiada na pytanie F3.1**: nie ma ani jednego pobrania przed startem,
więc nie wiadomo, kiedy skład i nieobecności się pojawiają. Jedyna obserwacja przed
meczem: 2026-10-01, 9 h przed - brak (`docs/sofa/MODELE_HOKEJ_KOSZ_SIATKA.md:362`).

**Sonda dla operatora:** `scripts/sofa/probe_lineup_availability.py` (mostek, ten
sam `SofascoreClient` z kubełkiem i bezpiecznikiem, jedno zapytanie naraz, domyślnie
<= 20 meczów, twardo <= 60 na przebieg, 403 = stop). Czyta mecze dnia z
`02_fixtures.json` i `sport_fixtures.json`, pyta tylko te, które startują w oknie
(`--min-hours` .. `--max-hours` od teraz), pomija pytane < 30 min temu, dopisuje
wiersze do `runs/sofa/<d>/lineup_probe.jsonl` (status OK / NOT_FOUND / ERROR,
`confirmed`, liczba zawodników i wyjściowych, formacja, missing / doubtful na
stronę, godziny do startu). `--summary` składa z tego offline tabelę per sport x
rozgrywki x horyzont (po starcie, 0-30 min, 30-60 min, 1-2 h, 2-3 h, 3-6 h, > 6 h).
Propozycja: 3-4 przebiegi dnia (3 h, 2 h, 1 h, 30 min przed blokiem startów), po 20
meczów. **Nie uruchomiona** (wymaga mostka; decyzja operatora). Test offline z
fałszywym klientem: `tests/sofa/test_probe_lineup_availability.py`.

## 8. Czego nie zrobiono i dlaczego

- **Żadnego refitu, żadnego `fit_*`** - zakaz w trakcie dnia. Naprawa tenisa (D1) i
  notatka D2 czekają za `MODEL_FIXES_FROM_UTC = None`.
- **Cechy F3.2, które przechodzą kryterium (runda, puchar, odpoczynek, inna liga),
  nie są wpięte w SHEET** - korekta środka potrzebuje współczynników dopasowanych
  między dniami do configu, tej samej korekty w replayu cache i ponownego pomiaru
  względem pełnego `p_central` (shrink + rating), bo tu mierzono względem surowej
  średniej. Długość sezonu dla rundy musi pochodzić z poprzedniego sezonu (cache) -
  SHEET dziś jej nie zna.
- **Kartki rezerwowych (D3')** - bez naprawy: brak /lineups dla większości historii
  i niejednoznaczny regulamin dla zawodnika po zmianie.
- **MIN_ODDS (D4)** - decyzja operatora, nie zmieniono.
- **Piłkarska wariancja NB dla goals_total przy dużym przesunięciu i goals_1h_total**
  - zmierzona bez zysku / minimalnie gorzej; nie zmieniono (już zainstalowane i
  krzywe 10-05 na tym dopasowane).
- **Sonda składów** - nie uruchomiona (mostek).
- **Rating piłki w pomiarze D1** - środek przesuwany tylko przez K_CENTRE i bazę
  ligi; rating (W_FOOTBALL_RATING) przesuwa go mocniej, ale jego replay jest ciężki i
  nie był uruchamiany.
- Nie sprawdzono: wpływu naprawy tenisa na krzywe (`calibrated_on`) - pokaże to
  `prepare_refit.py compare` po włączeniu flagi.

## Odtworzenie

```bash
DB=/Users/mkoziol/projects/bet/data/sofa.db
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_defects.py --db $DB nb-variance --sport football
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_defects.py --db $DB nb-variance --sport tennis
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_defects.py --db $DB promotion
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_defects.py --db $DB bench-cards
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_defects.py --db $DB context --feature knockout
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_defects.py --db $DB context --feature rest
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_defects.py --db $DB context --feature promotion
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_defects.py --db $DB --end 2026-10-04 context --feature round
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_defects.py --db $DB --end 2026-10-04 context --feature referee
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_defects.py --db $DB --end 2026-10-04 context --feature missing
```

Każdy przebieg piłki czyta ~1 mln zdarzeń i ~460 tys. statystyk (ok. 10-15 min,
~6 GB RAM). Pomiar MIN_ODDS (sekcja 4) był jednorazowym skryptem w scratchpadzie
(`Calibration.realised` na wierszach `05_sheet.json` i `sofa_settled_row`), nie jest
w repo.
