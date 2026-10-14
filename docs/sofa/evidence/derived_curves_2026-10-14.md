# Krzywe jointów piłki (DERIVED_CURVES) vs dzisiejszy zastępca z dowodu linii (2026-10-14)

Pomiar tylko do odczytu. Nie zmieniono żadnego przełącznika ani pliku konfiguracji.
Skrypt roboczy (scratch, poza repozytorium) odtwarza dokładnie ścieżkę
`run_confidence.py` (linie ~700-720) i `fit_line_evidence.sheet_rows` / `le.fit`.

## Pytanie

Przełącznik `epochs.DERIVED_CURVES_FROM_UTC` (dziś `None`): czy joint piłki
(`both_over_*`, `most_*`, `handicap_*` baz goals / corners / shots_on_target /
cards_points) ma czytać krzywą z historii (refit 2026-10-14 z odtworzonymi
jointami), obniżaną dowodem linii jak każdy inny klucz - zamiast dzisiejszego
zastępcy (granica Wilsona własnych rozliczonych linii Superbetu klucza /
efekt projektu kubełka, `NO_LINE_EVIDENCE` poniżej 50 linii / 15 meczów)?
Przy okazji: co z tego wynika dla `CARDS_CORRELATION_FROM_UTC` i
`DERIVED_SHEET_MARGINS_FROM_UTC` (B3).

## Dane i metoda

- Krzywe: `data/refit_2026-10-14/ft/config/sofa_confidence_calibration.json`
  (`fitted_at_utc` 2026-10-14T02:35Z, DB `data/refit_2026-10-14/sofa_replay.db`,
  `max_settled_run_date` 2026-10-12; replay `--derived cards_points,goals,corners,shots_on_target
  --cards-correlation`, a także `game_state`, `rated_scope`, `venue_prior`,
  `season_phase`, `rating_weight`, `opponent_correction`, `football_rating`,
  `count_dispersion`, `per_market_k` - `fitted_from.replay_rules`). Klucze
  `by_market` / `by_market_direction`: `both_over_*`, `most_*`, `handicap_*`
  czterech baz. Odczyt z flagami jak na żywo (`gap_shrink_k=0`,
  `cap_market_by_thin`, `cap_pool_by_neighbour`).
- Linie testowe: `sofa_settled_row` (data/sofa.db, `mode=ro`), piłka, WIN/LOSS,
  rynki pochodne, `run_date` 2026-10-09..2026-10-12 (11 479 linii; zgodne co do
  liczby z `07_settled.json` tych dni). **10-13 nie jest jeszcze rozliczony** -
  brak wierszy, do dopisania po rozliczeniu. W czterech bazach: **9 547 linii,
  1 536 meczów**. Poza zakresem refitu (zostają przy zastępcy niezależnie od
  przełącznika): `most_corners_1h` 650, `both_over_shots` 487, `most_shots` 294,
  `both_over_fouls` 190, `most_corners_2h` 180, `both_over_offsides` 79,
  `most_shots_1h/2h` 52. Nie ma rozliczonych `handicap_goals` / `most_goals`
  (Superbet ich nie wystawił w tych dniach).
- **Walk-forward dowodu linii**: dla dnia testowego D dowód (`le.fit`) jest
  dopasowany na dniach stats_only 2026-10-05..D-1 - dwa razy:
  - **zastępca** (dziś): klucz pochodny bez bazy (`derived_curves=False`);
  - **krzywa**: `derived_curves=True` na nowych krzywych (offset klucza
    pochodnego liczony względem jego krzywej, jak `fit_line_evidence --derived-curves`;
    pula sportu też na nowych krzywych).
  Odczyt `LineEvidence.read(..., v2=True, bucket_deff=True)` - dzisiejsze
  reguły (offset, cap pasma ceny, efekt projektu kubełka). Klasa meczu jak w
  `run_confidence` (77 linii `women` - brak krzywej klasy, obie ścieżki nic nie
  czytają).
- Metryki: log-loss pewności przy wyniku (krzywa - zastępca, ujemne = krzywa
  lepsza) na liniach, które wyceniają **obie** ścieżki; pokrycie; luka
  drukowalna (realizacja - pewność przy pewności >= 0,70); bootstrap po meczach,
  2000 losowań, ziarno 0 (iloraz sum).

### Zastrzeżenie in-sample (ważne)

Krzywe są dopasowane na historii, która **zawiera mecze dni testowych**
(`max_settled_run_date` 2026-10-12). Dowód linii jest poza próbą (walk-forward),
krzywa nie. Udział 4 dni w ~119 mln ocenionych wierszy replayu jest mały, ale
nie zero - wynik krzywej jest lekko optymistyczny. Czysty test to wiersze
2026-10-13 i późniejsze (po rozliczeniu), z krzywą bez zmian.

### Zastrzeżenie estymatora (ważne)

`p_central` wierszy pochodnych tych dni policzył SHEET z wyłączonymi
`CARDS_CORRELATION`, `DERIVED_SHEET_MARGINS`, `GAME_STATE`,
`FOOTBALL_RATED_SCOPE`, `FOOTBALL_VENUE_PRIOR`, `SAMPLE_OPPONENT_CORRECTION`
itd., a krzywa jest dopasowana na p replayu ze wszystkimi tymi regułami.
Krzywa jest więc czytana na osi p innego estymatora. W szczególności:
- **kartki**: krzywe jointów kartek dopasowano na p z rho = +0,126, a p na
  żywo ma rho = 0. Przy rho > 0 P(obie strony powyżej) rośnie, P(obie poniżej)
  też, a handicap / most przesuwają się ku środkowi; ten sam mecz leży więc w
  innym kubełku p niż w replayu. Wynik kartek poniżej jest odczytem kombinacji,
  która nie zostanie uruchomiona (krzywa z korelacją na p bez niej);
- **B3**: replay daje obu stronom centrum wiersza marginalnego zawsze, gdy
  strona ma próbkę (`calibrate_from_cache.py`, `football_joint_rows` /
  `joint_centres`) - czyli tak, jak SHEET liczyłby z B3 włączonym. Na żywo bez
  B3 joint meczu, w którym jedna strona nie ma kwotowanej drabinki, wraca do
  surowych próbek obu stron. Podział niżej to pokazuje.

## Wynik

### Pokrycie

| zakres | linie | mecze | zastępca wycenia | krzywa wycenia | zastępca >= 0,70 | krzywa >= 0,70 |
|---|---|---|---|---|---|---|
| wszystkie p | 9 547 | 1 536 | 7 895 | 9 459 | 66 | 1 024 |
| p_central >= 0,60 | 2 326 | 942 | 809 | 2 294 | 66 | 1 024 |
| both_over (p >= 0,60) | 2 041 | 941 | 755 | 2 020 | 66 | 999 |
| most (p >= 0,60) | 97 | 78 | 5 | 87 | 0 | 6 |
| handicap (p >= 0,60) | 188 | 103 | 49 | 187 | 0 | 19 |
| goals (p >= 0,60) | 1 058 | 938 | 574 | 1 037 | 35 | 422 |
| corners (p >= 0,60) | 703 | 294 | 209 | 702 | 31 | 369 |
| shots_on_target (p >= 0,60) | 251 | 152 | 10 | 251 | 0 | 110 |
| cards_points (p >= 0,60) | 314 | 153 | 16 | 304 | 0 | 123 |

Zastępca w obszarze druku praktycznie nie istnieje: przy p >= 0,70 wycenia
167 z 1 348 linii (reszta `NO_LINE_EVIDENCE`), a pewności >= 0,70 daje 66
liniom (tylko `both_over_goals` UNDER i `both_over_corners` OVER).

### Log-loss pewności, krzywa - zastępca (linie wyceniane przez obie)

Linie z p < 0,60 to kubełek zbiorczy: obie ścieżki dają tam jedną dolną
granicę całego kubełka, a CONFIDENCE i tak je odrzuca (`CATCH_ALL_BUCKET`).
Rozstrzyga obszar p >= 0,60; całość podana dla pełności.

| zakres | linie | mecze | krzywa | zastępca | realizacja | różnica [95%] |
|---|---|---|---|---|---|---|
| **p >= 0,60, razem** | **809** | **614** | 0,615 | 0,542 | 0,630 | **-0,0154 [-0,0309; +0,0004]** |
| p >= 0,60, both_over | 755 | 600 | 0,613 | 0,547 | 0,630 | -0,0133 [-0,0275; +0,0017] |
| p >= 0,60, handicap | 49 | 48 | 0,646 | 0,467 | 0,612 | -0,0403 [-0,1371; +0,0691] |
| p >= 0,60, most | 5 | - | - | - | - | za mało |
| p >= 0,60, goals (both_over) | 574 | 529 | 0,597 | 0,512 | 0,578 | -0,0104 [-0,0285; +0,0083] |
| p >= 0,60, corners | 209 | 158 | 0,671 | 0,629 | 0,761 | -0,0237 [-0,0495; +0,0031] |
| p >= 0,60, corners / both_over | 155 | 140 | 0,681 | 0,683 | 0,806 | -0,0165 [-0,0290; -0,0033] |
| p >= 0,60, shots_on_target / cards_points | 10 / 16 | - | - | - | - | za mało (zastępca nie wycenia) |
| wszystkie p, razem | 7 895 | 1 500 | 0,312 | 0,328 | 0,407 | +0,0176 [+0,0124; +0,0230] |
| wszystkie p, both_over | 5 305 | 1 499 | | | | +0,0420 [+0,0353; +0,0483] |
| wszystkie p, most | 1 974 | 336 | | | | -0,0449 [-0,0549; -0,0347] |
| wszystkie p, handicap | 616 | 222 | | | | +0,0074 [-0,0030; +0,0187] |
| wszystkie p, goals | 3 401 | 1 496 | | | | +0,0586 [+0,0498; +0,0676] |
| wszystkie p, corners | 2 474 | 318 | | | | -0,0138 [-0,0190; -0,0088] |
| wszystkie p, shots_on_target | 727 | 158 | | | | -0,0391 [-0,0609; -0,0166] |
| wszystkie p, cards_points | 1 293 | 254 | | | | +0,0014 [-0,0110; +0,0145] |

Wartości "wszystkie p" to głównie kubełek zbiorczy (p 0,30-0,60: realizacja
0,39-0,55, krzywa i zastępca czytają 0,28-0,35) - porównanie dwóch dolnych
granic, które nie drukują; nie rozstrzyga.

Według dnia (wszystkie p): 10-09 +0,0192, 10-10 +0,0079 [-0,0022; +0,0174],
10-11 +0,0133, 10-12 +0,0484 - ten sam znak, ten sam powód (kubełek zbiorczy).

Sama krzywa bez dowodu linii (p >= 0,60): -0,0070 [-0,0283; +0,0157].

### Podział wg estymatora (B3): czy obie strony miały centrum marginalne

Strona "ma centrum", gdy w `05_sheet.json` dnia jest wiersz `<baza>_for` z jej
podmiotem (przybliżenie warunku `derived.price_derived_rungs`).

| populacja | linie | p >= 0,60 (obie wyceniają) | log-loss krzywa - zastępca, p >= 0,60 | luka krzywej >= 0,70 (z dowodem linii) | luka samej krzywej >= 0,70 |
|---|---|---|---|---|---|
| obie strony z centrum (estymator replayu) | 6 650 | 1 515 (415) | **-0,0357 [-0,0585; -0,0135]** | +6,0 pp [+3,7; +8,2] (808) | +2,1 pp [-0,1; +4,4] (913) |
| surowe próbki (populacja B3) | 2 897 | 811 (394) | +0,0060 [-0,0158; +0,0275] | -1,0 pp [-6,2; +4,3] (216) | **-11,0 pp [-16,4; -6,1]** (368) |

Tam, gdzie p powstało tym estymatorem, na którym dopasowano krzywą, krzywa
jest wyraźnie lepsza od zastępcy (przedział poza zerem). Na wierszach z
surowych próbek nie ma zysku, a sama krzywa przeszacowuje o 11 pp przy
>= 0,70 - ratuje ją tylko offset dowodu linii.

### Obszar druku (pewność >= 0,70)

| ścieżka | linie | mecze | pewność | realizacja | 1/kurs | ROI [95%] | luka realizacja - pewność [95%] |
|---|---|---|---|---|---|---|---|
| zastępca | 66 | 41 | 0,770 | 0,924 | 0,897 | +3,0% [-5,0; +9,8] | +15,5 pp [+8,7; +21,4] |
| zastępca, x >= 0,90 | 18 | 17 | 0,835 | 0,944 | 0,894 | +5,8% [-9,1; +16,2] | +10,9 pp [-0,5; +17,7] |
| **krzywa** (krzywa, a bez niej zastępca) | **1 024** | **456** | 0,808 | 0,854 | 0,868 | -1,8% [-4,4; +0,7] | **+4,6 pp [+2,4; +6,7]** |
| krzywa, x >= 0,90 | 742 | 372 | 0,821 | 0,842 | 0,857 | -1,9% [-5,2; +1,3] | +2,1 pp [-0,5; +4,8] |
| sama krzywa, bez dowodu linii | 1 281 | 557 | 0,824 | 0,808 | 0,825 | -2,5% | -1,6 pp [-3,8; +0,5] |

Krzywa wg bazy (>= 0,70, z dowodem linii): goals 422 linie +3,2 pp
[-0,7; +6,6], ROI -6,2% [-10,6; -2,1] (x >= 0,90: 239 linii, ROI -8,9%
[-15,4; -3,2]; to prawie wyłącznie `both_over_goals` UNDER, 391 linii);
corners 369 +5,3 pp [+1,9; +8,7], ROI +1,6% [-2,5; +5,4]; shots_on_target 110
+6,0 pp [-0,5; +12,0], ROI +0,3%; cards_points 123 +5,7 pp [-0,5; +11,6], ROI
+1,1%. Rodziny: both_over 999 linii +4,8 pp [+2,6; +6,9]; handicap 19 linii
-8,2 pp [-27,8; +11,4]; most 6 linii. Sama krzywa przeszacowuje gole o -6,8 pp
[-10,5; -3,4] - offset dowodu linii to zbiera (własny offset
`both_over_goals` UNDER -0,112 / -0,074 / -0,050 / -0,073 na 10-09..10-12;
pozostałe klucze zwykle offset puli piłki -0,004..-0,010, a na 10-12
`both_over_goals` OVER -0,177 i `both_over_cards_points` UNDER -0,129 własne).

Krzywa nie przeszacowuje w obszarze druku (jest ostrożna o ~5 pp), ale linie,
które by wpuściła, realizowały razem poniżej ceny (0,854 vs 0,868; -1,5 pp
[-3,6; +0,6]), a gole wyraźnie poniżej.

### Czy to w ogóle dotyka kuponu

Nie. `08_confidence.json` 10-09..10-13: **0 nóg pochodnych piłki** każdego dnia.
Każdy wiersz pochodny, który przejdzie próg pewności i ceny, odrzuca
`THIN_SAMPLE_FOR_BUILDER` (`run_confidence.py:809`): bramka czyta próbkę po
nazwie rynku wiersza, a `03_samples.json` nie ma kluczy `both_over_*` /
`most_*` / `handicap_*` (to samo ustalenie co w `derived_margins_2026-10-13.md`).
Włączenie DERIVED_CURVES dziś nie zmieniłoby ani jednej nogi.

## Werdykty

**DERIVED_CURVES_FROM_UTC - zostaje `None` (wyłączony).**
- W obszarze, w którym noga może drukować (p >= 0,60), krzywa jest lepsza od
  zastępcy, ale przedział dotyka zera: -0,0154 [-0,0309; +0,0004] - próg
  "przedział poza zerem" niespełniony, i to przy krzywej in-sample.
- Zysk jest wyraźny tylko na wierszach liczonych estymatorem replayu (obie
  strony z centrum: -0,0357 [-0,0585; -0,0135]); na wierszach z surowych
  próbek (populacja B3) brak zysku, sama krzywa przeszacowuje tam o 11 pp.
- Pokrycie rośnie radykalnie (pewność >= 0,70: 66 -> 1 024 linii), luka
  druku krzywej +4,6 pp (ostrożna), ale te linie realizowały poniżej ceny
  (ROI -1,8% [-4,4; +0,7]; `both_over_goals` -6,2% [-10,6; -2,1]).
- Na kupon nie wpływa, dopóki `THIN_SAMPLE_FOR_BUILDER` odrzuca każdy wiersz
  pochodny - to decyzja operatora przed jakimkolwiek przełącznikiem jointów.
- Kandydat do włączenia **razem** z resztą tego refitu (krzywe należą do
  estymatora z `GAME_STATE`, `FOOTBALL_RATED_SCOPE`, `FOOTBALL_VENUE_PRIOR`,
  `SAMPLE_OPPONENT_CORRECTION`, `CARDS_CORRELATION`), z B3 i z decyzją o
  bramce próbki wierszy pochodnych; potwierdzić na wierszach >= 2026-10-13
  (poza próbą krzywej). `fit_line_evidence --derived-curves` w dniu włączenia.

**CARDS_CORRELATION_FROM_UTC - zostaje `None`.**
- Bez DERIVED_CURVES nic nie zmienia na kuponie: jointy kartek czytają
  zastępcę, który nie zależy od krzywej, a p z korelacją przesunęłoby tylko
  kubełek dowodu linii, dopasowany na p bez korelacji.
- Na tych danych nie da się go zmierzyć: wiersze 10-09..10-12 mają p z rho = 0,
  a SHEET nie zapisuje centrów stron, więc nie da się ich przeliczyć z
  rho = +0,126. Dowód pozostaje historyczny
  (`dependence_goals_2026-10-08.md`: both_over +0,0016 [0,0009; 0,0022],
  handicap +0,0028, most +0,0011 poprawy log-loss).
- Krzywe jointów kartek tego refitu są dopasowane **z** korelacją: jeśli
  DERIVED_CURVES pójdzie z tymi krzywymi, CARDS_CORRELATION musi wejść w tej
  samej chwili, inaczej kartki czytają krzywą na p innego estymatora (wynik
  kartek wyżej - krzywa vs zastępca przy p >= 0,60: 16 linii wspólnych, luka
  druku +5,7 pp [-0,5; +11,6] na 123 liniach - jest odczytem właśnie takiej
  niespójnej kombinacji).

**DERIVED_SHEET_MARGINS_FROM_UTC (B3) - zostaje `None` do wspólnej decyzji,
ale ten pomiar go wspiera.**
- Próg O5 spełniony na historii (`derived_margins_2026-10-13.md`: -0,0254
  [-0,0264; -0,0245]).
- Tu: wiersze, którym B3 dałoby centrum (dziś surowe próbki, 2 897 z 9 547
  linii, ~30%), to dokładnie te, na których krzywa refitu nie działa (sama
  przeszacowuje o 11 pp przy >= 0,70). Replay krzywych liczy każdy joint tak,
  jak B3 - DERIVED_CURVES bez B3 czytałby krzywą na ~30% wierszy z innym
  estymatorem. Wniosek: B3 i DERIVED_CURVES włączać razem albo wcale.
- Ten pomiar nie wycenia ponownie wierszy pod B3 (brak centrów w artefaktach);
  rozstrzyga historia.

## Do zrobienia

- Po rozliczeniu 2026-10-13 (i kolejnych dni) powtórzyć z tą samą krzywą -
  pierwszy test poza próbą krzywej.
- Decyzja o `THIN_SAMPLE_FOR_BUILDER` dla wierszy pochodnych (bez niej żaden
  z trzech przełączników nie zmienia kuponu).
- `both_over_goals` UNDER: krzywa + offset wpuściłyby ~100 linii dziennie
  realizujących poniżej ceny - sprawdzić przed włączeniem, czy offset na
  nowym estymatorze (z B3) to łapie.
