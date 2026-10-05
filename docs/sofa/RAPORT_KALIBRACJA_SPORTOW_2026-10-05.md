# Raport: kalibracja pewności hokeja, koszykówki, siatkówki i CS2 (2026-10-05)

Plan `docs/sofa/PLAN_2026-10-05_SETTLE_I_KUPON.md`, część 5, F4–F6 (decyzja D2).
Pewność nogi tych sportów = dolna granica Wilsona kubełka krzywej, do którego
wpada prawdopodobieństwo modelu (`score_model` / `cs2_engine`). **Cena nie wchodzi
nigdzie**: ani do modelu, ani do krzywej, ani do oceny poza próbą. Liczby poniżej
pochodzą wyłącznie z poleceń wymienionych przy każdej tabeli.

## 1. Wynik w jednym miejscu

| sport | dopuszczone (drukują się) | NOT_CALIBRATED |
|---|---|---|
| hokej | `handicap\|TEAM`, `team_total\|OVER`, `total\|OVER` | `total\|UNDER`, `team_total\|UNDER` (zawyżone kubełki historii odłożonej), `winner`, `result_1x2`, wszystkie okresy (`period_*`) |
| koszykówka | — | wszystko: `total`, `team_total`, `handicap` zawyżone na rozliczonych liniach Superbetu (kubełki 0,60–0,75, o 3,3–11,2 pp); `winner`, `result_1x2`, pierwsza połowa bez kubełka do druku z n ≥ 200 |
| siatkówka | `points_total\|UNDER`, `sets_total\|UNDER` | `points_handicap`, `set_handicap`, `points_total\|OVER` (zawyżone), `sets_total\|OVER`, `winner`, `set_winner`, `set_points_total` |
| CS2 | — | `map_winner`, `match_winner`, `map_team_rounds\|UNDER` (brak kubełka do druku z n ≥ 200), `map_team_rounds\|OVER` (zawyżenie 5,75 pp na liniach Superbetu) |

Plik: `config/sofa_sport_confidence_calibration.json` — krzywe, listy `admitted`
/ `not_calibrated` z powodem i pełny wynik poza próbą (`oos`) per sport. Klucz
niedopuszczony = noga `NOT_CALIBRATED` w `run_sport_confidence.py`; sport bez
żadnego dopuszczonego klucza ma status `NOT_CALIBRATED` i exit 1 (PARTIAL).
Koszykówka i CS2 nie drukują dziś nic.

Polecenie (raz, między dniami, baza tylko do odczytu):

```
SOFA_DB_PATH=/Users/mkoziol/projects/bet/data/sofa.db SOFA_RUNS_DIR=/Users/mkoziol/projects/bet/runs/sofa PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_sport_confidence.py --sport all --before 2026-10-05 --sims 2000 --events-cache <zrzuty load_events> --rows-out data/analysis_2026-10-05/sport_calibration
```

Tabele: `PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_sport_confidence.py --tables`
(czyta tylko plik kalibracji). Surowe wiersze (JSONL per sport i populacja),
`<sport>_section.json`, `fit_stdout.json`, `fit_stderr.log`, `tables.md`:
`data/analysis_2026-10-05/sport_calibration/` w worktree (`data/` jest w
`.gitignore`, więc nie w commicie; wynik poza próbą jest też w pliku kalibracji).

## 2. Jak to policzono

**Rynki (F2).** `sport_confidence.ALLOWED_MARKETS`, każde id sprawdzone w
`shadow.MARKETS` (test `test_every_allowed_market_is_the_shadow_market_it_claims`):
hokej 630, 623, 658/652, 604, 640 i okresy 649, 674/638, 678, 660; koszykówka 759,
753, 768, 758/776, 777 i pierwsza połowa 748, 773, 200804/200797, 763; siatkówka
745, 230058, 100082, 230060, 1069, 744, 782. CS2: `map_winner`, `match_winner`,
`map_team_rounds`. Poza listą: dnb (także hokejowe 662), parzystość, tak/nie,
dokładny wynik, koszykówka druga połowa i kwarty, propsy, CS2 `map_rounds_total`,
`maps_*`, `team_kills`, `player_*`. 744 (zwycięzca seta) ma w `shadow.MARKETS`
rodzaj `dnb`; set nie ma remisu, więc to zwycięzca — zostawiony na liście.
Klucz krzywej = rodzina × strona (`OVER`/`UNDER`/`DRAW`, strona drużyny `TEAM`).

**Historia, walk-forward (F4).** Okno dopasowania 2025-09-05..2026-09-05, ostatnie
30 dni (2026-09-05..2026-10-05) odłożone. Każdy mecz prognozowany z modelu
zbudowanego tylko z meczów, które zaczęły się wcześniej (`score_model.build_model`
co 30 dni, między przebudowami książka ratingów aktualizowana mecz po meczu;
mecze o tym samym starcie prognozowane, zanim którykolwiek zostanie nauczony —
testy `test_walk_forward_never_reads_the_game_itself_or_a_later_one`,
`test_games_sharing_a_start_are_forecast_before_either_is_learnt`). Do 4 000 meczów
w oknie dopasowania i 3 000 w odłożonym (równomiernie przerzedzone), 2 000
symulacji na mecz (pipeline: 4 000). Linie syntetyczne: 13 kwantyli (0,05–0,95)
rozkładu **symulowanego dla danego meczu**, pół punktu od liczby całkowitej;
linia, na której symulacja daje p < 0,01 lub > 0,99, nie jest liczona.
CS2: Elo map + Elo graczy odtwarzane seria po serii, kalibracja logistyczna
dopasowywana co 7 dni na prognozach sprzed dopasowania (test zgodności z
`cs2_engine.model_probability` przy dopasowaniu przed każdą serią), rundy
drużyny na liniach 9,5 / 10,5 / 11,5 / 12,5.

**Okresy i pierwsza połowa** — tylko z rozliczonych linii SHADOW
(`runs/sofa/shadow/<sport>/<d>/settled.json`, model zbudowany przed dniem):
2026-09-29..10-01 dopasowuje, 10-02..10-04 poza próbą.

**Poza próbą (F5)**, dwie populacje: `history_holdout` (30 dni historii) i
`superbet_settled` (rozliczone linie Superbetu: SHADOW 09-29..10-04 z p modelu
sprzed dnia; CS2 09-28..10-04 z `model_p` zapisanym przez
`settle_cs2.attach_model`). Log-loss pewności i surowego p modelu; realizacja
minus pewność z 95% przedziałem z bootstrapu **po meczach** (2 000 losowań).
„Do druku” = wiersze z pewnością ≥ 0,70 (podłoga oficjalnego kuponu).

**Warunek wejścia (F6)** — `sport_confidence.admission`:
1. jak w planie: żaden kubełek poza próbą z n ≥ 200, w żadnej populacji, nie
   drukuje pewności wyższej od realizacji o > 3 pp;
2. **dodatkowo**: co najmniej jeden kubełek *do druku* (pewność ≥ 0,70) z
   n ≥ 200 poza próbą — inaczej `NO_OOS_PRINTABLE_BUCKET`;
3. **dodatkowo**: wiersze do druku jednej populacji łącznie nie mogą zawyżać o
   > 3 pp przy n ≥ 200 ani mieć górnej granicy 95% (realizacja − pewność)
   poniżej −3 pp przy dowolnym n.

Uzasadnienie 2 i 3: drugi przebieg (pięć kwantyli, sama reguła 1) dopuścił
klucze, których jedynym kubełkiem z n ≥ 200 poza próbą był zbiorczy 0,00–0,60
(nic nie mówi o nodze drukowanej), oraz siatkówkę `set_handicap|TEAM`, której
linie Superbetu do druku dały 0,639 przy pewności 0,827 (n = 61, górna granica
−0,0775). Reguła „n ≥ 200 w kubełku” nie czyta kilkudziesięciu linii Superbetu
na kubełek, a to one są celem.

## 3. Dopuszczone klucze — poza próbą, wiersze do druku

Źródło: `fit_sport_confidence.py --tables` (kolumny „printable”) = plik
kalibracji, `oos.<populacja>.<klucz>.printable`. Luka = realizacja − pewność
[95% bootstrap po meczach].

| sport | klucz | populacja | n | pewność | realizacja | luka [95%] |
|---|---|---|---|---|---|---|
| hokej | handicap\|TEAM | historia odłożona | 10 471 | 0,845 | 0,844 | −0,001 [−0,010; +0,008] |
| hokej | handicap\|TEAM | linie Superbetu | 384 | 0,763 | 0,742 | −0,021 [−0,072; +0,029] |
| hokej | team_total\|OVER | historia odłożona | 4 301 | 0,836 | 0,849 | +0,013 [+0,001; +0,025] |
| hokej | team_total\|OVER | linie Superbetu | 398 | 0,808 | 0,794 | −0,014 [−0,053; +0,026] |
| hokej | total\|OVER | historia odłożona | 3 296 | 0,840 | 0,865 | +0,025 [+0,010; +0,040] |
| hokej | total\|OVER | linie Superbetu | 163 | 0,789 | 0,761 | −0,028 [−0,102; +0,042] |
| siatkówka | points_total\|UNDER | historia odłożona | 7 280 | 0,826 | 0,847 | +0,021 [+0,005; +0,036] |
| siatkówka | points_total\|UNDER | linie Superbetu | 7 | 0,760 | 0,286 | −0,474 [−0,761; +0,243] |
| siatkówka | sets_total\|UNDER | historia odłożona | 909 | 0,751 | 0,799 | +0,047 [+0,022; +0,074] |
| siatkówka | sets_total\|UNDER | linie Superbetu | 57 | 0,748 | 0,807 | +0,059 [−0,046; +0,158] |

Linie Superbetu do druku per kubełek (wszędzie n < 200, za mało na regułę 1;
plik kalibracji `oos.superbet_settled.<klucz>.buckets`; n / pewność / realizacja):

| klucz | kubełki |
|---|---|
| hokej handicap\|TEAM | 0,70–0,75: 137 / 0,706 / 0,701; 0,75–0,80: 104 / 0,746 / 0,702; 0,80–0,825: 45 / 0,794 / 0,822; 0,825–0,85: 35 / 0,809 / 0,886; 0,85–0,875: 32 / 0,838 / 0,750; 0,875–0,90: 12 / 0,861 / 0,917; 0,90–0,925: 11 / 0,893 / 0,818; 0,925–0,95: 5 / 0,918 / 0,400; 0,95–1,01: 3 / 0,962 / 0,667 |
| hokej team_total\|OVER | 0,75–0,80: 135 / 0,734 / 0,674; 0,80–0,825: 41 / 0,753 / 0,707; 0,825–0,85: 54 / 0,796 / 0,852; 0,85–0,875: 38 / 0,843 / 0,921; 0,875–0,90: 40 / 0,857 / 0,950; 0,90–0,925: 39 / 0,903 / 0,821; 0,925–0,95: 51 / 0,924 / 0,882 |
| hokej total\|OVER | 0,75–0,80: 73 / 0,736 / 0,740; 0,80–0,825: 21 / 0,786 / 0,762; 0,825–0,85: 22 / 0,810 / 0,682; 0,85–0,875: 22 / 0,833 / 0,864; 0,875–0,90: 12 / 0,858 / 0,750; 0,90–0,925: 6 / 0,899 / 0,833; 0,925–0,95: 7 / 0,921 / 0,857 |
| siatkówka points_total\|UNDER | 0,75–0,80: 3 / 0,734 / 0,333; 0,80–0,825: 4 / 0,779 / 0,250 |
| siatkówka sets_total\|UNDER | 0,70–0,75: 37 / 0,738 / 0,757; 0,75–0,80: 14 / 0,786 / 0,857; 0,80–0,825: 6 / 0,727 / 1,000 |

## 4. Co z tego wynika i czego nie wiem

- **Hokej**: na historii odłożonej trzy dopuszczone klucze są skalibrowane albo
  ostrożne (luka ≥ 0). Na liniach Superbetu do druku luka jest ujemna we
  wszystkich trzech (−1,4 do −2,8 pp), przedziały obejmują zero, n 163–398.
  To najmocniejszy dowód, jaki jest — i jest słaby.
- **Siatkówka `points_total|UNDER`**: dopuszczona na historii (7 280 wierszy do
  druku, luka +2,1 pp), ale na liniach Superbetu do druku 2 z 7 (0,286 przy
  0,760). Siedem linii nie przekracza progów reguły 3 (górna granica +0,243),
  więc klucz przeszedł. **To podejrzenie, nie pomiar** — do obejrzenia przy
  pierwszym rozliczeniu.
- **Siatkówka `sets_total|UNDER`** (w praktyce „poniżej 4,5 seta”): ostrożna w
  obu populacjach.
- **Koszykówka**: na historii odłożonej model jest skalibrowany (dodatek A), ale
  na liniach Superbetu jego p ≥ 0,60 realizuje się wyraźnie niżej
  (`total|OVER` 0,70–0,75: 0,610 przy 0,722, n = 210; `handicap|TEAM`,
  `team_total`, `total|UNDER` w kubełku 0,60–0,70 zawyżone o 3,3–10,4 pp).
  Superbet stawia linie tam, gdzie model nie zgadza się z rynkiem — ten sam
  mechanizm co „rozbieżność z ceną jest antysygnałem” w piłce (podejrzenie, nie
  zmierzone tu wprost). Koszykówka nie drukuje się.
- **Zbiorczy kubełek 0,00–0,60** na liniach Superbetu realizuje się do 31 pp
  wyżej niż jego lo95 (totale i handicapy hokeja, koszykówki i siatkówki 12–31
  pp; np. hokej `total|OVER` 0,403 przy 0,199) — łączy
  wszystko od 0 do 0,6 i nie jest pewnością żadnej nogi; nie drukuje się
  (podłoga 0,70).
- **Ograniczenie siatki linii**: p modelu siatkówki (i częściowo koszykówki)
  skupia się przy kwantylach (`points_total|UNDER`: kubełki 0,75–0,80,
  0,80–0,825, 0,85–0,875, 0,90–0,925, 0,95–1,01 po 3 881 wierszy, a 0,70–0,75 i
  0,825–0,85 bez wierszy). Noga z p modelu w pustym kubełku jest
  `NOT_CALIBRATED`. `LINE_QUANTILES` to stała niedopasowana.
- **Okresy, pierwsza połowa, set**: 3 dni linii do dopasowania (35–132 mecze)
  i 3 do sprawdzenia — żaden klucz nie ma kubełka do druku z n ≥ 200. Wrócą,
  gdy przybędzie dni (`fit_sport_confidence.py` między dniami).
- **CS2**: 1 371 serii odłożonych; Elo rzadko daje p ≥ 0,70 w kubełku z
  n ≥ 200.
- Próba dymna producenta (nie dowód jakości): `run_sport_confidence.py --date
  2026-10-04` pod `SOFA_NOW=2026-10-04T15:00:00Z` na kopii katalogów w
  scratchpadzie, z `sport_fixtures.json` złożonym z identyfikatorów znanych po
  rozliczeniu 10-04 i z tym plikiem kalibracji: hokej 22 nogi, siatkówka 5,
  koszykówka `NOT_CALIBRATED`, CS2 `NOT_IDENTIFIED` (brak tożsamości CS2 w
  próbie), exit 1.

## 5. Odstępstwa od planu i rzeczy niesprawdzone

- Plan: linie z „kwartyli historii ±1 krok”. Zrobione: kwantyle rozkładu
  symulowanego meczu — globalne kwartyle stawiają np. 150,5 pod mecz NBA
  (~230 pkt) i zapełniają górne kubełki liniami, których nikt nie wystawia.
  Żadna cena linii nie ustawia.
- Warunek wejścia zaostrzony (punkty 2–3 w części 2).
- Rodziny okresów: dopasowanie i sprawdzenie na połowach dni rozliczonych (plan
  nie mówi, jak dzielić).
- 2 000 symulacji na mecz w dopasowaniu (pipeline 4 000); CS2: kalibracja Elo
  co 7 dni, nie przed każdą serią.
- Historia z jednego zrzutu `score_model.load_events` (baza tylko do odczytu,
  ok. 08:55Z 2026-10-05; hokej 31 321, koszykówka 55 560, siatkówka 20 998
  zdarzeń), przycięta do startów przed 2026-10-05.
- `settled.json` czytane na żywo, gdy rozliczenie działało obok: między
  przebiegami liczba linii siatkówki zmieniła się 3 240 → 3 230, koszykówki
  25 145 → 25 101. Wynik to stan plików z chwili przebiegu.
- Przebiegi: (1) przerwany po hokeju, (2) pięć kwantyli i sama reguła 1 —
  dopuścił klucze bez dowodu w strefie druku
  (`data/analysis_2026-10-05/sport_calibration_run2_5quantiles/`), (3) obecny.
  Zmiany między (2) i (3) wynikały z tego, co pokazał (2) — to dopasowanie
  reguły po obejrzeniu danych i tak trzeba to czytać.
- Niesprawdzone: ROI (z założenia — pewność bez ceny; filtry ceny D1 stosuje
  `run_sport_confidence.py`), dzień po 10-05 (powie pierwsze rozliczenie),
  tożsamość F1 na żywo (wymaga mostka).

## Dodatek A. Wszystkie klucze — poza próbą

Źródło: `PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_sport_confidence.py --tables`.
`conf.` = średnia pewność (lo95 kubełka), `printable` = wiersze z pewnością
≥ 0,70, `realised-conf.` z 95% bootstrapem po meczach.

### hockey

fit 2025-09-05..2026-09-05, holdout 2026-09-05..2026-10-05; rows {'history_fit': 283374, 'history_holdout': 111253, 'settled_fit': 1945, 'superbet_settled': 18271}; games {'history_fit': 4258, 'history_holdout': 1667, 'settled_fit': 132, 'superbet_settled': 542}

| key | status | population | n | games | conf. | realised | realised-conf. [95%] | log-loss conf. | log-loss model | printable n | printable conf. | printable realised | printable gap [95%] |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| handicap\|TEAM | ADMITTED | history_holdout | 29432 | 1667 | 0.493 | 0.500 | +0.007 [+0.007; +0.008] | 0.5240 | 0.4847 | 10471 | 0.845 | 0.844 | -0.001 [-0.010; +0.008] |
| handicap\|TEAM | ADMITTED | superbet_settled | 1934 | 259 | 0.410 | 0.500 | +0.090 [+0.085; +0.095] | 0.6868 | 0.6365 | 384 | 0.763 | 0.742 | -0.021 [-0.072; +0.029] |
| period_1x2\|DRAW | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | history_holdout | 0 | | | | | | | | | | |
| period_1x2\|DRAW | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | superbet_settled | 0 | | | | | | | | | | |
| period_1x2\|TEAM | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | history_holdout | 0 | | | | | | | | | | |
| period_1x2\|TEAM | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | superbet_settled | 0 | | | | | | | | | | |
| period_handicap\|TEAM | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | history_holdout | 0 | | | | | | | | | | |
| period_handicap\|TEAM | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | superbet_settled | 0 | | | | | | | | | | |
| period_team_total\|OVER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 0 | | | | | | | | | | |
| period_team_total\|OVER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 818 | 207 | 0.298 | 0.359 | +0.061 [+0.025; +0.095] | 0.6617 | 0.6009 | 0 | - | - | - |
| period_team_total\|UNDER | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | history_holdout | 0 | | | | | | | | | | |
| period_team_total\|UNDER | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | superbet_settled | 0 | | | | | | | | | | |
| period_total\|OVER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 0 | | | | | | | | | | |
| period_total\|OVER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 633 | 346 | 0.340 | 0.414 | +0.074 [+0.030; +0.118] | 0.6901 | 0.6515 | 0 | - | - | - |
| period_total\|UNDER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 0 | | | | | | | | | | |
| period_total\|UNDER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 655 | 364 | 0.288 | 0.359 | +0.071 [+0.031; +0.111] | 0.6645 | 0.6072 | 0 | - | - | - |
| result_1x2\|DRAW | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 1667 | 1667 | 0.196 | 0.191 | -0.004 [-0.023; +0.015] | 0.4883 | 0.4868 | 0 | - | - | - |
| result_1x2\|DRAW | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 489 | 489 | 0.196 | 0.200 | +0.005 [-0.030; +0.040] | 0.5010 | 0.5040 | 0 | - | - | - |
| result_1x2\|TEAM | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 3159 | 1667 | 0.373 | 0.387 | +0.014 [+0.003; +0.024] | 0.6575 | 0.6410 | 0 | - | - | - |
| result_1x2\|TEAM | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 927 | 489 | 0.370 | 0.387 | +0.017 [-0.004; +0.036] | 0.6560 | 0.6382 | 0 | - | - | - |
| team_total\|OVER | ADMITTED | history_holdout | 21991 | 1667 | 0.365 | 0.385 | +0.021 [+0.012; +0.029] | 0.5137 | 0.4563 | 4301 | 0.836 | 0.849 | +0.013 [+0.001; +0.025] |
| team_total\|OVER | ADMITTED | superbet_settled | 2283 | 474 | 0.384 | 0.503 | +0.119 [+0.092; +0.145] | 0.6974 | 0.6176 | 398 | 0.808 | 0.794 | -0.014 [-0.053; +0.026] |
| team_total\|UNDER | NOT_CALIBRATED: OVERSTATES: history_holdout bucket 0.850-0.875 confidence above realised by 0.0314 | history_holdout | 22012 | 1667 | 0.618 | 0.614 | -0.004 [-0.012; +0.004] | 0.4849 | 0.4561 | 10873 | 0.884 | 0.875 | -0.009 [-0.018; -0.001] |
| team_total\|UNDER | NOT_CALIBRATED: OVERSTATES: history_holdout bucket 0.850-0.875 confidence above realised by 0.0314 | superbet_settled | 2319 | 474 | 0.457 | 0.490 | +0.033 [+0.006; +0.059] | 0.6485 | 0.6100 | 490 | 0.802 | 0.741 | -0.061 [-0.108; -0.018] |
| total\|OVER | ADMITTED | history_holdout | 14720 | 1667 | 0.388 | 0.415 | +0.027 [+0.015; +0.040] | 0.5111 | 0.4513 | 3296 | 0.840 | 0.865 | +0.025 [+0.010; +0.040] |
| total\|OVER | ADMITTED | superbet_settled | 1618 | 474 | 0.365 | 0.501 | +0.136 [+0.101; +0.174] | 0.7265 | 0.6369 | 163 | 0.789 | 0.761 | -0.028 [-0.102; +0.042] |
| total\|UNDER | NOT_CALIBRATED: OVERSTATES: history_holdout bucket 0.800-0.825 confidence above realised by 0.0347 | history_holdout | 14731 | 1667 | 0.591 | 0.584 | -0.007 [-0.020; +0.006] | 0.4843 | 0.4510 | 6721 | 0.883 | 0.879 | -0.004 [-0.016; +0.008] |
| total\|UNDER | NOT_CALIBRATED: OVERSTATES: history_holdout bucket 0.800-0.825 confidence above realised by 0.0347 | superbet_settled | 1618 | 474 | 0.420 | 0.499 | +0.078 [+0.044; +0.114] | 0.6752 | 0.6369 | 213 | 0.781 | 0.756 | -0.025 [-0.088; +0.034] |
| winner\|TEAM | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 3194 | 1667 | 0.477 | 0.487 | +0.010 [+0.005; +0.014] | 0.6748 | 0.6595 | 110 | 0.736 | 0.754 | +0.019 [-0.063; +0.101] |
| winner\|TEAM | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 957 | 501 | 0.475 | 0.487 | +0.012 [+0.004; +0.020] | 0.6733 | 0.6591 | 29 | 0.736 | 0.724 | -0.012 [-0.184; +0.126] |

### basketball

fit 2025-09-05..2026-09-05, holdout 2026-09-05..2026-10-05; rows {'history_fit': 422266, 'history_holdout': 159031, 'settled_fit': 2404, 'superbet_settled': 25101}; games {'history_fit': 3874, 'history_holdout': 1459, 'settled_fit': 113, 'superbet_settled': 567}

| key | status | population | n | games | conf. | realised | realised-conf. [95%] | log-loss conf. | log-loss model | printable n | printable conf. | printable realised | printable gap [95%] |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| h1_1x2\|DRAW | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | history_holdout | 0 | | | | | | | | | | |
| h1_1x2\|DRAW | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | superbet_settled | 0 | | | | | | | | | | |
| h1_1x2\|TEAM | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | history_holdout | 0 | | | | | | | | | | |
| h1_1x2\|TEAM | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | superbet_settled | 0 | | | | | | | | | | |
| h1_handicap\|TEAM | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 0 | | | | | | | | | | |
| h1_handicap\|TEAM | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 1294 | 347 | 0.439 | 0.502 | +0.064 [+0.044; +0.084] | 0.7013 | 0.7171 | 0 | - | - | - |
| h1_team_total\|OVER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 0 | | | | | | | | | | |
| h1_team_total\|OVER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 476 | 129 | 0.365 | 0.408 | +0.042 [-0.030; +0.115] | 0.6797 | 0.7015 | 0 | - | - | - |
| h1_team_total\|UNDER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 0 | | | | | | | | | | |
| h1_team_total\|UNDER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 576 | 128 | 0.487 | 0.559 | +0.072 [+0.001; +0.144] | 0.6966 | 0.7287 | 0 | - | - | - |
| h1_total\|OVER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 0 | | | | | | | | | | |
| h1_total\|OVER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 593 | 290 | 0.307 | 0.462 | +0.155 [+0.085; +0.229] | 0.7431 | 0.6920 | 0 | - | - | - |
| h1_total\|UNDER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 0 | | | | | | | | | | |
| h1_total\|UNDER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 723 | 322 | 0.546 | 0.534 | -0.012 [-0.079; +0.053] | 0.6911 | 0.7405 | 0 | - | - | - |
| handicap\|TEAM | NOT_CALIBRATED: OVERSTATES: superbet_settled bucket 0.600-0.700 confidence above realised by 0.0852 | history_holdout | 37934 | 1459 | 0.493 | 0.500 | +0.007 [+0.007; +0.007] | 0.4940 | 0.4637 | 14590 | 0.846 | 0.849 | +0.003 [-0.006; +0.013] |
| handicap\|TEAM | NOT_CALIBRATED: OVERSTATES: superbet_settled bucket 0.600-0.700 confidence above realised by 0.0852 | superbet_settled | 4704 | 559 | 0.356 | 0.500 | +0.144 [+0.135; +0.152] | 0.7787 | 0.6763 | 572 | 0.781 | 0.698 | -0.083 [-0.161; -0.006] |
| result_1x2\|DRAW | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 1459 | 1459 | 0.036 | 0.037 | +0.001 [-0.008; +0.011] | 0.1583 | 0.1616 | 0 | - | - | - |
| result_1x2\|DRAW | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 249 | 249 | 0.036 | 0.044 | +0.008 [-0.016; +0.036] | 0.1818 | 0.1879 | 0 | - | - | - |
| result_1x2\|TEAM | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 2666 | 1459 | 0.425 | 0.450 | +0.025 [+0.016; +0.033] | 0.6540 | 0.6246 | 127 | 0.757 | 0.740 | -0.017 [-0.095; +0.054] |
| result_1x2\|TEAM | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 468 | 249 | 0.416 | 0.455 | +0.039 [+0.019; +0.058] | 0.6444 | 0.5978 | 23 | 0.757 | 0.870 | +0.113 [-0.061; +0.243] |
| team_total\|OVER | NOT_CALIBRATED: OVERSTATES: superbet_settled bucket 0.600-0.700 confidence above realised by 0.0327 | history_holdout | 37858 | 1459 | 0.488 | 0.484 | -0.003 [-0.013; +0.007] | 0.4736 | 0.4422 | 14514 | 0.833 | 0.853 | +0.020 [+0.010; +0.031] |
| team_total\|OVER | NOT_CALIBRATED: OVERSTATES: superbet_settled bucket 0.600-0.700 confidence above realised by 0.0327 | superbet_settled | 2318 | 274 | 0.331 | 0.476 | +0.146 [+0.096; +0.199] | 0.7740 | 0.6946 | 182 | 0.753 | 0.604 | -0.149 [-0.276; -0.017] |
| team_total\|UNDER | NOT_CALIBRATED: OVERSTATES: superbet_settled bucket 0.600-0.700 confidence above realised by 0.1036 | history_holdout | 37932 | 1459 | 0.500 | 0.515 | +0.015 [+0.005; +0.025] | 0.4821 | 0.4420 | 14588 | 0.839 | 0.873 | +0.034 [+0.024; +0.045] |
| team_total\|UNDER | NOT_CALIBRATED: OVERSTATES: superbet_settled bucket 0.600-0.700 confidence above realised by 0.1036 | superbet_settled | 2237 | 274 | 0.334 | 0.521 | +0.187 [+0.136; +0.236] | 0.8260 | 0.6981 | 88 | 0.774 | 0.693 | -0.081 [-0.256; +0.068] |
| total\|OVER | NOT_CALIBRATED: OVERSTATES: superbet_settled bucket 0.700-0.750 confidence above realised by 0.1120 | history_holdout | 18780 | 1459 | 0.488 | 0.483 | -0.005 [-0.018; +0.007] | 0.4654 | 0.4311 | 7108 | 0.828 | 0.864 | +0.036 [+0.022; +0.050] |
| total\|OVER | NOT_CALIBRATED: OVERSTATES: superbet_settled bucket 0.700-0.750 confidence above realised by 0.1120 | superbet_settled | 4322 | 564 | 0.345 | 0.482 | +0.137 [+0.089; +0.189] | 0.7616 | 0.6925 | 403 | 0.754 | 0.623 | -0.132 [-0.242; -0.022] |
| total\|UNDER | NOT_CALIBRATED: OVERSTATES: superbet_settled bucket 0.600-0.700 confidence above realised by 0.0343 | history_holdout | 18967 | 1459 | 0.492 | 0.513 | +0.022 [+0.009; +0.035] | 0.4754 | 0.4302 | 7295 | 0.826 | 0.879 | +0.052 [+0.039; +0.066] |
| total\|UNDER | NOT_CALIBRATED: OVERSTATES: superbet_settled bucket 0.600-0.700 confidence above realised by 0.0343 | superbet_settled | 4123 | 565 | 0.334 | 0.508 | +0.174 [+0.125; +0.230] | 0.7983 | 0.6936 | 222 | 0.744 | 0.631 | -0.113 [-0.238; +0.014] |
| winner\|TEAM | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 2642 | 1459 | 0.444 | 0.466 | +0.022 [+0.015; +0.029] | 0.6575 | 0.6274 | 144 | 0.788 | 0.764 | -0.025 [-0.094; +0.038] |
| winner\|TEAM | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 1000 | 542 | 0.441 | 0.472 | +0.031 [+0.021; +0.042] | 0.6589 | 0.6221 | 52 | 0.788 | 0.827 | +0.038 [-0.077; +0.135] |

### volleyball

fit 2025-09-05..2026-09-05, holdout 2026-09-05..2026-10-05; rows {'history_fit': 259640, 'history_holdout': 96986, 'settled_fit': 218, 'superbet_settled': 3230}; games {'history_fit': 3881, 'history_holdout': 1456, 'settled_fit': 35, 'superbet_settled': 223}

| key | status | population | n | games | conf. | realised | realised-conf. [95%] | log-loss conf. | log-loss model | printable n | printable conf. | printable realised | printable gap [95%] |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| points_handicap\|TEAM | NOT_CALIBRATED: OVERSTATES: history_holdout bucket 0.700-0.750 confidence above realised by 0.0413 | history_holdout | 37856 | 1456 | 0.494 | 0.500 | +0.006 [+0.006; +0.006] | 0.4612 | 0.4256 | 14560 | 0.872 | 0.873 | +0.001 [-0.007; +0.010] |
| points_handicap\|TEAM | NOT_CALIBRATED: OVERSTATES: history_holdout bucket 0.700-0.750 confidence above realised by 0.0413 | superbet_settled | 308 | 90 | 0.385 | 0.500 | +0.115 [+0.083; +0.149] | 0.8692 | 0.7778 | 65 | 0.813 | 0.554 | -0.259 [-0.473; -0.057] |
| points_total\|OVER | NOT_CALIBRATED: OVERSTATES_PRINTABLE: superbet_settled n=11 confidence 0.7594 realised 0.2727 (realised-confidence -0.4866, 95% upper -0.1604) | history_holdout | 18729 | 1456 | 0.501 | 0.513 | +0.012 [-0.002; +0.025] | 0.4720 | 0.4432 | 7081 | 0.860 | 0.886 | +0.026 [+0.013; +0.039] |
| points_total\|OVER | NOT_CALIBRATED: OVERSTATES_PRINTABLE: superbet_settled n=11 confidence 0.7594 realised 0.2727 (realised-confidence -0.4866, 95% upper -0.1604) | superbet_settled | 238 | 172 | 0.293 | 0.534 | +0.241 [+0.139; +0.348] | 0.9016 | 0.7329 | 11 | 0.759 | 0.273 | -0.487 [-0.760; -0.160] |
| points_total\|UNDER | ADMITTED | history_holdout | 18928 | 1456 | 0.478 | 0.482 | +0.004 [-0.009; +0.017] | 0.4768 | 0.4414 | 7280 | 0.826 | 0.847 | +0.021 [+0.005; +0.036] |
| points_total\|UNDER | ADMITTED | superbet_settled | 231 | 169 | 0.300 | 0.459 | +0.159 [+0.063; +0.263] | 0.8583 | 0.7367 | 7 | 0.760 | 0.286 | -0.474 [-0.761; +0.243] |
| set_handicap\|TEAM | NOT_CALIBRATED: OVERSTATES_PRINTABLE: superbet_settled n=61 confidence 0.8299 realised 0.6393 (realised-confidence -0.1906, 95% upper -0.0791) | history_holdout | 12548 | 1455 | 0.490 | 0.500 | +0.010 [+0.009; +0.012] | 0.5724 | 0.5371 | 3162 | 0.845 | 0.841 | -0.004 [-0.020; +0.011] |
| set_handicap\|TEAM | NOT_CALIBRATED: OVERSTATES_PRINTABLE: superbet_settled n=61 confidence 0.8299 realised 0.6393 (realised-confidence -0.1906, 95% upper -0.0791) | superbet_settled | 470 | 176 | 0.440 | 0.500 | +0.060 [+0.047; +0.075] | 0.7054 | 0.6913 | 61 | 0.830 | 0.639 | -0.191 [-0.311; -0.079] |
| set_points_total\|OVER | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | history_holdout | 0 | | | | | | | | | | |
| set_points_total\|OVER | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | superbet_settled | 0 | | | | | | | | | | |
| set_points_total\|UNDER | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | history_holdout | 0 | | | | | | | | | | |
| set_points_total\|UNDER | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | superbet_settled | 0 | | | | | | | | | | |
| set_winner\|TEAM | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | history_holdout | 0 | | | | | | | | | | |
| set_winner\|TEAM | NOT_CALIBRATED: NO_FIT_BUCKET_WITH_N>=200 | superbet_settled | 0 | | | | | | | | | | |
| sets_total\|OVER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 2906 | 1456 | 0.342 | 0.353 | +0.011 [-0.007; +0.031] | 0.6066 | 0.5642 | 0 | - | - | - |
| sets_total\|OVER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 188 | 94 | 0.373 | 0.394 | +0.020 [-0.056; +0.100] | 0.6130 | 0.6023 | 0 | - | - | - |
| sets_total\|UNDER | ADMITTED | history_holdout | 2527 | 1427 | 0.581 | 0.607 | +0.025 [+0.003; +0.046] | 0.6107 | 0.6072 | 909 | 0.751 | 0.799 | +0.047 [+0.022; +0.074] |
| sets_total\|UNDER | ADMITTED | superbet_settled | 182 | 94 | 0.575 | 0.599 | +0.024 [-0.057; +0.101] | 0.6110 | 0.6081 | 57 | 0.748 | 0.807 | +0.059 [-0.046; +0.158] |
| winner\|TEAM | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 2548 | 1456 | 0.432 | 0.443 | +0.011 [+0.003; +0.019] | 0.5904 | 0.5329 | 519 | 0.804 | 0.796 | -0.008 [-0.042; +0.026] |
| winner\|TEAM | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 397 | 222 | 0.420 | 0.456 | +0.036 [+0.015; +0.054] | 0.6463 | 0.5850 | 71 | 0.799 | 0.747 | -0.052 [-0.155; +0.038] |

### cs2

fit 2025-09-05..2026-09-05, holdout 2026-09-05..2026-10-05; rows {'history_fit': 370118, 'history_holdout': 48942, 'superbet_settled': 2042}; games {'history_fit': 11429, 'history_holdout': 1371, 'superbet_settled': 165}

| key | status | population | n | games | conf. | realised | realised-conf. [95%] | log-loss conf. | log-loss model | printable n | printable conf. | printable realised | printable gap [95%] |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| map_team_rounds\|OVER | NOT_CALIBRATED: OVERSTATES: superbet_settled bucket 0.600-0.700 confidence above realised by 0.0575 | history_holdout | 20417 | 1226 | 0.606 | 0.615 | +0.010 [+0.002; +0.017] | 0.6617 | 0.6621 | 717 | 0.722 | 0.718 | -0.004 [-0.037; +0.030] |
| map_team_rounds\|OVER | NOT_CALIBRATED: OVERSTATES: superbet_settled bucket 0.600-0.700 confidence above realised by 0.0575 | superbet_settled | 570 | 37 | 0.620 | 0.591 | -0.029 [-0.069; +0.011] | 0.6839 | 0.6914 | 37 | 0.730 | 0.486 | -0.244 [-0.413; -0.084] |
| map_team_rounds\|UNDER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 20456 | 1226 | 0.385 | 0.384 | -0.001 [-0.008; +0.006] | 0.6658 | 0.6614 | 0 | - | - | - |
| map_team_rounds\|UNDER | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 584 | 37 | 0.384 | 0.411 | +0.027 [-0.013; +0.065] | 0.6787 | 0.7008 | 0 | - | - | - |
| map_winner\|TEAM | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 5524 | 1235 | 0.496 | 0.498 | +0.002 [-0.001; +0.004] | 0.6782 | 0.6630 | 0 | - | - | - |
| map_winner\|TEAM | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 538 | 110 | 0.494 | 0.498 | +0.004 [-0.006; +0.013] | 0.6742 | 0.6557 | 0 | - | - | - |
| match_winner\|TEAM | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | history_holdout | 2392 | 1235 | 0.487 | 0.489 | +0.002 [-0.003; +0.006] | 0.6661 | 0.6446 | 92 | 0.721 | 0.728 | +0.007 [-0.090; +0.094] |
| match_winner\|TEAM | NOT_CALIBRATED: NO_OOS_PRINTABLE_BUCKET_WITH_N>=200 (confidence >= 0.7) | superbet_settled | 310 | 165 | 0.482 | 0.474 | -0.008 [-0.023; +0.007] | 0.6592 | 0.6142 | 8 | 0.721 | 0.875 | +0.154 [-0.096; +0.279] |

## Dodatek B. Kubełki dopuszczonych kluczy (poza próbą, n >= 200)

Źródło jak wyżej. gap = pewność − realizacja (dodatnia = zawyżenie).

| key | population | bucket | n | conf. | realised | gap |
|---|---|---|---|---|---|---|
| handicap\|TEAM | history_holdout | 0.000-0.600 | 16728 | 0.252 | 0.265 | -0.013 |
| handicap\|TEAM | history_holdout | 0.600-0.700 | 2233 | 0.640 | 0.645 | -0.005 |
| handicap\|TEAM | history_holdout | 0.700-0.750 | 1272 | 0.706 | 0.711 | -0.004 |
| handicap\|TEAM | history_holdout | 0.750-0.800 | 1372 | 0.746 | 0.757 | -0.011 |
| handicap\|TEAM | history_holdout | 0.800-0.825 | 745 | 0.794 | 0.799 | -0.005 |
| handicap\|TEAM | history_holdout | 0.825-0.850 | 803 | 0.809 | 0.803 | +0.006 |
| handicap\|TEAM | history_holdout | 0.850-0.875 | 875 | 0.838 | 0.839 | -0.001 |
| handicap\|TEAM | history_holdout | 0.875-0.900 | 984 | 0.861 | 0.859 | +0.003 |
| handicap\|TEAM | history_holdout | 0.900-0.925 | 1167 | 0.893 | 0.883 | +0.010 |
| handicap\|TEAM | history_holdout | 0.925-0.950 | 1564 | 0.918 | 0.921 | -0.003 |
| handicap\|TEAM | history_holdout | 0.950-1.010 | 1689 | 0.962 | 0.949 | +0.013 |
| handicap\|TEAM | superbet_settled | 0.000-0.600 | 1267 | 0.252 | 0.400 | -0.148 |
| handicap\|TEAM | superbet_settled | 0.600-0.700 | 283 | 0.640 | 0.618 | +0.021 |
| team_total\|OVER | history_holdout | 0.000-0.600 | 15496 | 0.196 | 0.217 | -0.022 |
| team_total\|OVER | history_holdout | 0.600-0.700 | 1438 | 0.604 | 0.636 | -0.032 |
| team_total\|OVER | history_holdout | 0.700-0.750 | 756 | 0.697 | 0.709 | -0.012 |
| team_total\|OVER | history_holdout | 0.750-0.800 | 862 | 0.734 | 0.748 | -0.015 |
| team_total\|OVER | history_holdout | 0.800-0.825 | 425 | 0.753 | 0.774 | -0.021 |
| team_total\|OVER | history_holdout | 0.825-0.850 | 426 | 0.796 | 0.836 | -0.040 |
| team_total\|OVER | history_holdout | 0.850-0.875 | 454 | 0.843 | 0.872 | -0.029 |
| team_total\|OVER | history_holdout | 0.875-0.900 | 538 | 0.857 | 0.874 | -0.016 |
| team_total\|OVER | history_holdout | 0.900-0.925 | 649 | 0.903 | 0.901 | +0.002 |
| team_total\|OVER | history_holdout | 0.925-0.950 | 947 | 0.923 | 0.921 | +0.003 |
| team_total\|OVER | superbet_settled | 0.000-0.600 | 1461 | 0.196 | 0.387 | -0.191 |
| team_total\|OVER | superbet_settled | 0.600-0.700 | 290 | 0.604 | 0.624 | -0.021 |
| total\|OVER | history_holdout | 0.000-0.600 | 9852 | 0.199 | 0.224 | -0.025 |
| total\|OVER | history_holdout | 0.600-0.700 | 1048 | 0.598 | 0.654 | -0.056 |
| total\|OVER | history_holdout | 0.700-0.750 | 524 | 0.694 | 0.721 | -0.027 |
| total\|OVER | history_holdout | 0.750-0.800 | 587 | 0.736 | 0.775 | -0.039 |
| total\|OVER | history_holdout | 0.800-0.825 | 339 | 0.786 | 0.832 | -0.046 |
| total\|OVER | history_holdout | 0.825-0.850 | 380 | 0.810 | 0.832 | -0.021 |
| total\|OVER | history_holdout | 0.850-0.875 | 371 | 0.833 | 0.868 | -0.035 |
| total\|OVER | history_holdout | 0.875-0.900 | 416 | 0.858 | 0.885 | -0.027 |
| total\|OVER | history_holdout | 0.900-0.925 | 560 | 0.899 | 0.911 | -0.011 |
| total\|OVER | history_holdout | 0.925-0.950 | 643 | 0.921 | 0.928 | -0.007 |
| total\|OVER | superbet_settled | 0.000-0.600 | 1051 | 0.199 | 0.403 | -0.205 |
| total\|OVER | superbet_settled | 0.600-0.700 | 277 | 0.598 | 0.632 | -0.034 |
| points_total\|UNDER | history_holdout | 0.000-0.600 | 10192 | 0.208 | 0.199 | +0.010 |
| points_total\|UNDER | history_holdout | 0.600-0.700 | 1456 | 0.629 | 0.647 | -0.018 |
| points_total\|UNDER | history_holdout | 0.750-0.800 | 1456 | 0.734 | 0.748 | -0.013 |
| points_total\|UNDER | history_holdout | 0.800-0.825 | 1456 | 0.779 | 0.805 | -0.025 |
| points_total\|UNDER | history_holdout | 0.850-0.875 | 1456 | 0.826 | 0.846 | -0.020 |
| points_total\|UNDER | history_holdout | 0.900-0.925 | 1456 | 0.872 | 0.895 | -0.023 |
| points_total\|UNDER | history_holdout | 0.950-1.010 | 1456 | 0.919 | 0.942 | -0.023 |
| sets_total\|UNDER | history_holdout | 0.000-0.600 | 1233 | 0.421 | 0.435 | -0.014 |
| sets_total\|UNDER | history_holdout | 0.600-0.700 | 385 | 0.694 | 0.704 | -0.009 |
| sets_total\|UNDER | history_holdout | 0.700-0.750 | 522 | 0.738 | 0.774 | -0.036 |
| sets_total\|UNDER | history_holdout | 0.750-0.800 | 281 | 0.786 | 0.794 | -0.008 |
