# Czy statystyki odróżniają nogi przy tym samym kursie? (2026-10-07)

Pytanie operatora: czy statystyki (liga, turniej, drużyny, zawodnicy, forma,
poziom rywala) mówią, że jedno 1.20 jest pewniejsze od innego 1.20 — dla
**każdego** sportu tak samo. Odpowiedź tylko z rozliczonych linii, które
Superbet faktycznie wystawił. Materiał roboczy, nie lista zakładów.

## Metoda

- Linia = jedna strona linii Superbetu, rozliczona WIN / LOSS, z kursem.
- `p` ze statystyk, bez ceny:
  - piłka i tenis: `p_central` z `07_settled.json`, tylko dni epoki stats-only
    (2026-10-05, 2026-10-06). Wcześniej tenisowy `p_central` był w 75% ceną
    (`tennis_rating.blend_with_price`), więc starsze dni odpadają;
  - hokej, koszykówka, siatkówka, CS2: `p` modelu wyników / silnika CS2
    zbudowanego na dzień meczu (`fit_sport_confidence.py --before 2026-10-07
    --dry-run --rows-out`, `superbet_settled`), połączone z kursem rozliczonej
    strony w `settled.json`, 09-20..10-06 (shadow od 09-29, CS2 od 09-28).
- W każdym paśmie kursu (1.01–1.15, 1.15–1.25, 1.25–1.40, 1.40–1.60,
  1.60–2.00, 2.00–3.00, pasmo z >= 30 liniami): linie posortowane po `p`,
  podzielone na trzy. Δ = trafienia górnej trzeciej minus dolnej, średnia
  ważona po pasmach. Przedział 95% z bootstrapu po meczach (300 losowań).
- „ROZRÓŻNIA” = dolna granica Δ > 0; „szum” = przedział obejmuje 0.
- Linie jednego meczu są skorelowane; czytaj kolumnę „mecze”.

## Podsumowanie

| sport | Δ góra−dół, pp [95%] | odczyt |
|---|---|---|
| piłka (2 dni) | +14,4 [+8,2; +19,6] | rozróżnia (gole total O/U) |
| koszykówka | +9,1 [+1,0; +15,4] | rozróżnia (handicap +20,7, zwycięzca, 1X2) |
| hokej | +3,0 [−1,3; +7,2] | szum |
| siatkówka | +3,6 [−6,1; +14,5] | szum (sets_total UNDER +25,1 [+4,3; +41,0]) |
| tenis (2 dni) | +2,0 [−4,2; +8,2] | szum |
| CS2 | −2,6 [−13,6; +10,3] | szum |

Operator: szum dziś nie jest powodem do cięcia — rynek zostaje, jest mierzony
dalej (`epochs.LINE_EVIDENCE_FROM_UTC`).

## Krzywa z samego p zawyża na długich kursach

Ta sama pewność modelu trafia inaczej w różnych pasmach kursu (Superbet,
09-20..10-06):

| rynek | p modelu | kurs < 1.30 | 1.30–1.60 | 1.60–2.20 |
|---|---|---|---|---|
| koszykówka handicap | 0,70–0,80 | 0,81 (n=70) | 0,79 (n=151) | **0,62** (n=168) |
| koszykówka handicap | 0,80–0,875 | 0,91 (n=34) | 0,72 (n=32) | **0,62** (n=55) |
| koszykówka total OVER | 0,70–0,80 | 0,92 (n=73) | **0,57** (n=195) | **0,51** (n=99) |
| hokej handicap | 0,70–0,80 | 0,82 (n=112) | **0,60** (n=117) | – |
| hokej team_total UNDER | 0,70–0,80 | 0,75 (n=146) | **0,60** (n=102) | **0,53** (n=19) |
| tenis games_won_for OVER | >= 0,70 | – | – | **0,47** (n=119) |

Decyzja operatora (2026-10-07): „krzywa per pasmo kursu” — pewność nie
wyższa, niż takie `p` trafiało w tym paśmie (`bet.sofa.line_evidence`).
Kurs wybiera pasmo i tylko obniża.

## Tabele szczegółowe

### football (10-05..10-06, p_central stats-only)

| rynek | mecze | linie | Δ trafień góra−dół, pp [95% bootstrap po meczach] | ROI wszystkich | ROI górnej 1/3 [95%] | odczyt |
|---|---|---|---|---|---|---|
| **WSZYSTKO** | 209 | 13755 | +14.4 [+8.2; +19.6] | -20.2% | -3.0% [-8.7%; +2.2%] | ROZRÓŻNIA |
| goals_total|UNDER | 205 | 856 | +18.5 [+6.9; +28.6] | -14.1% | -2.2% [-14.2%; +8.6%] | ROZRÓŻNIA |
| goals_total|OVER | 205 | 838 | +13.0 [+1.9; +22.8] | -11.5% | +5.1% [-8.6%; +17.4%] | ROZRÓŻNIA |
| goals_for|OVER | 122 | 731 | +0.3 [-11.0; +14.5] | -21.5% | -2.2% [-17.1%; +13.5%] | szum |
| goals_for|UNDER | 122 | 681 | -1.8 [-13.4; +8.5] | -9.3% | -4.1% [-20.1%; +8.9%] | szum |
| corners_total|UNDER | 80 | 458 | +5.1 [-12.6; +21.9] | -30.8% | -23.2% [-48.2%; -1.2%] | szum |
| corners_total|OVER | 80 | 455 | +6.5 [-7.4; +22.0] | -6.6% | +11.4% [-7.4%; +31.5%] | szum |
| corners_for|OVER | 42 | 430 | +14.1 [-3.9; +31.6] | -5.5% | +4.9% [-15.7%; +25.7%] | szum |
| corners_for|UNDER | 42 | 425 | +14.0 [-5.8; +34.1] | -22.2% | +1.4% [-19.4%; +21.0%] | szum |
| goals_2h_total|OVER | 121 | 394 | +10.5 [-8.3; +23.4] | -14.7% | +2.9% [-18.2%; +20.8%] | szum |
| goals_2h_total|UNDER | 121 | 387 | +15.5 [-0.5; +29.8] | -8.6% | -2.6% [-19.6%; +14.1%] | szum |
| goals_1h_total|OVER | 121 | 373 | +9.4 [-11.0; +24.9] | -8.9% | -2.7% [-28.2%; +29.9%] | szum |
| goals_1h_total|UNDER | 121 | 367 | +14.6 [-3.5; +30.2] | -15.1% | +1.6% [-16.9%; +18.6%] | szum |
| goals_2h_for|OVER | 122 | 332 | +7.5 [-11.0; +24.2] | -19.7% | -11.3% [-33.2%; +10.0%] | szum |
| goals_1h_for|OVER | 122 | 318 | +1.1 [-14.7; +18.3] | -21.6% | -16.4% [-39.9%; +9.2%] | szum |
| goals_2h_for|UNDER | 122 | 315 | -0.2 [-12.4; +17.2] | -10.0% | -5.1% [-23.6%; +16.0%] | szum |
| goals_1h_for|UNDER | 122 | 303 | +5.9 [-8.9; +17.1] | -6.9% | -1.3% [-19.8%; +12.4%] | szum |
| both_over_goals|OVER | 202 | 256 | -0.9 [-17.1; +18.2] | -7.0% | -11.7% [-35.2%; +10.9%] | szum |
| both_over_goals|UNDER | 202 | 254 | -0.4 [-17.2; +18.2] | -7.2% | -15.0% [-39.0%; +10.1%] | szum |
| corners_1h_total|OVER | 48 | 204 | +23.3 [-7.2; +49.4] | +2.5% | +19.3% [-20.0%; +61.7%] | szum |
| corners_1h_total|UNDER | 48 | 204 | +26.3 [-8.8; +45.6] | -29.9% | -6.8% [-47.4%; +20.0%] | szum |
| corners_1h_for|OVER | 29 | 162 | +29.5 [-16.1; +57.1] | -4.1% | +1.8% [-37.7%; +63.4%] | szum |
| player_assists_for|OVER | 26 | 161 | – | – | – | brak pasma n>=30 |
| both_over_corners|OVER | 34 | 161 | -18.3 [-63.3; +22.7] | -6.8% | +2.6% [-58.7%; +72.7%] | szum |
| corners_1h_for|UNDER | 29 | 160 | +29.2 [-11.2; +59.7] | -16.1% | +21.9% [-30.1%; +61.5%] | szum |
| cards_points_total|OVER | 34 | 113 | -10.0 [-52.7; +24.5] | -13.2% | +5.9% [-50.5%; +59.0%] | szum |
| cards_points_total|UNDER | 34 | 108 | +60.0 [+10.0; +92.3] | -17.8% | +76.6% [-11.1%; +122.1%] | ROZRÓŻNIA |
| most_corners|OVER | 36 | 105 | – | – | – | brak pasma n>=30 |
| most_cards_points|OVER | 31 | 92 | – | – | – | brak pasma n>=30 |

za mało danych (<20 meczów): cards_points_for|OVER(31), cards_points_for|UNDER(31), both_over_cards_points|OVER(30), both_over_cards_points|UNDER(30), player_shots_on_target_for|OVER(15), player_shots_for|OVER(13), player_fouls_for|OVER(9), player_tackles_for|OVER(8), player_offsides_for|OVER(10), corners_2h_total|OVER(5), corners_2h_total|UNDER(5), corners_2h_for|OVER(5), corners_2h_for|UNDER(5), shots_on_target_total|OVER(15), shots_on_target_total|UNDER(15), shots_on_target_for|OVER(15), shots_on_target_for|UNDER(15), shots_on_target_1h_total|OVER(12), shots_on_target_1h_total|UNDER(12), shots_on_target_1h_for|OVER(5), shots_on_target_1h_for|UNDER(5), shots_on_target_2h_total|OVER(5), shots_on_target_2h_total|UNDER(5), shots_on_target_2h_for|OVER(5), shots_on_target_2h_for|UNDER(5), shots_total|OVER(12), shots_total|UNDER(12), shots_for|OVER(13), shots_for|UNDER(13), shots_1h_total|OVER(13), shots_1h_total|UNDER(13), shots_1h_for|OVER(6), shots_1h_for|UNDER(6), fouls_total|OVER(11), fouls_total|UNDER(11), fouls_for|OVER(11), fouls_for|UNDER(11), shots_2h_total|OVER(6), shots_2h_total|UNDER(6), shots_2h_for|OVER(6), shots_2h_for|UNDER(6), fouls_1h_total|OVER(6), fouls_1h_total|UNDER(6), fouls_1h_for|OVER(6), fouls_1h_for|UNDER(6), tackles_total|OVER(8), tackles_total|UNDER(8), fouls_2h_total|OVER(6), fouls_2h_total|UNDER(6), fouls_2h_for|OVER(6), fouls_2h_for|UNDER(6), tackles_for|OVER(8), tackles_for|UNDER(8), saves_total|OVER(13), saves_total|UNDER(13), saves_for|UNDER(13), saves_for|OVER(13), saves_1h_total|OVER(5), saves_1h_total|UNDER(5), saves_1h_for|OVER(5), saves_1h_for|UNDER(5), offsides_total|OVER(11), offsides_total|UNDER(11), offsides_for|OVER(11), offsides_for|UNDER(11), offsides_1h_total|OVER(6), offsides_1h_total|UNDER(6), offsides_1h_for|OVER(6), offsides_1h_for|UNDER(6), offsides_2h_total|OVER(6), offsides_2h_total|UNDER(6), offsides_2h_for|OVER(6), offsides_2h_for|UNDER(6), throw_ins_total|OVER(8), throw_ins_total|UNDER(8), throw_ins_for|OVER(8), throw_ins_for|UNDER(8), throw_ins_1h_total|OVER(6), throw_ins_1h_total|UNDER(6), throw_ins_1h_for|OVER(6), throw_ins_1h_for|UNDER(6), throw_ins_2h_total|OVER(6), throw_ins_2h_total|UNDER(6), throw_ins_2h_for|OVER(6), throw_ins_2h_for|UNDER(6), goal_kicks_total|OVER(8), goal_kicks_total|UNDER(8), goal_kicks_for|OVER(8), goal_kicks_for|UNDER(8), both_over_fouls|OVER(11), both_over_offsides|OVER(9), both_over_shots|OVER(13), both_over_shots_on_target|OVER(15), handicap_cards_points|OVER(6), handicap_corners|OVER(33), handicap_shots_on_target|OVER(6), most_corners_1h|OVER(25), most_corners_2h|OVER(5), most_shots|OVER(12), most_shots_1h|OVER(6), most_shots_2h|OVER(6), most_shots_on_target|OVER(12)

### tennis (10-05..10-06, p_central stats-only)

| rynek | mecze | linie | Δ trafień góra−dół, pp [95% bootstrap po meczach] | ROI wszystkich | ROI górnej 1/3 [95%] | odczyt |
|---|---|---|---|---|---|---|
| **WSZYSTKO** | 223 | 17975 | +2.0 [-4.2; +8.2] | -11.2% | -6.9% [-12.5%; -1.2%] | szum |
| handicap_games|OVER | 203 | 1530 | -0.7 [-16.6; +13.3] | -8.4% | -10.8% [-25.9%; +2.2%] | szum |
| games_won_for|UNDER | 208 | 1441 | +0.7 [-6.8; +8.9] | -11.3% | -4.4% [-14.4%; +8.2%] | szum |
| games_won_for|OVER | 208 | 1418 | +6.6 [-2.9; +13.5] | -12.0% | -5.8% [-19.7%; +5.6%] | szum |
| games_won_set1_for|UNDER | 208 | 1355 | -1.7 [-10.8; +7.0] | -17.8% | -6.7% [-20.0%; +3.8%] | szum |
| games_won_set1_for|OVER | 208 | 1339 | -4.6 [-13.0; +3.3] | -9.1% | -12.0% [-21.7%; -1.2%] | szum |
| games_won_set2_for|UNDER | 208 | 1321 | -3.1 [-11.7; +7.6] | -14.4% | -16.3% [-26.7%; -4.1%] | szum |
| games_won_set2_for|OVER | 207 | 1294 | -3.8 [-12.4; +5.6] | -6.2% | -5.8% [-16.9%; +6.7%] | szum |
| games_set2_total|UNDER | 203 | 1014 | +6.3 [-3.3; +17.7] | -10.8% | -4.5% [-16.7%; +7.9%] | szum |
| games_set1_total|UNDER | 203 | 1010 | +3.5 [-6.2; +12.8] | -13.5% | -5.9% [-20.0%; +3.4%] | szum |
| games_set2_total|OVER | 203 | 976 | +6.7 [-4.1; +16.6] | -9.0% | -2.1% [-13.6%; +11.5%] | szum |
| games_set1_total|OVER | 203 | 962 | +5.7 [-4.6; +16.3] | -9.2% | -0.2% [-11.7%; +10.4%] | szum |
| games_total|OVER | 203 | 782 | +6.9 [-9.8; +18.9] | -8.7% | +1.2% [-19.6%; +16.6%] | szum |
| games_total|UNDER | 203 | 782 | +3.2 [-11.0; +18.7] | -8.3% | -12.2% [-30.3%; +7.4%] | szum |
| most_games|OVER | 80 | 235 | +0.6 [-27.8; +40.6] | -34.2% | -15.2% [-50.5%; +27.4%] | szum |
| sets_total|OVER | 181 | 181 | -3.0 [-25.3; +14.8] | -24.0% | -33.0% [-66.3%; -5.2%] | szum |
| sets_total|UNDER | 181 | 181 | -0.7 [-22.1; +14.3] | -1.7% | -1.0% [-24.0%; +13.8%] | szum |
| tiebreaks_total|OVER | 80 | 92 | +21.7 [-11.4; +52.3] | -31.3% | -19.5% [-73.9%; +62.6%] | szum |

za mało danych (<20 meczów): aces_total|OVER(22), aces_total|UNDER(22), aces_for|OVER(22), aces_for|UNDER(22), aces_set1_total|OVER(22), aces_set1_total|UNDER(22), aces_set2_total|OVER(22), aces_set2_total|UNDER(22), aces_set1_for|OVER(22), aces_set1_for|UNDER(22), aces_set2_for|OVER(22), aces_set2_for|UNDER(22), double_faults_total|OVER(22), double_faults_total|UNDER(22), double_faults_for|OVER(22), double_faults_for|UNDER(22), double_faults_set1_total|OVER(22), double_faults_set1_total|UNDER(22), double_faults_set2_total|OVER(22), double_faults_set2_total|UNDER(22), double_faults_set1_for|OVER(22), double_faults_set1_for|UNDER(22), double_faults_set2_for|OVER(22), double_faults_set2_for|UNDER(22), serve_points_total|OVER(22), serve_points_total|UNDER(22), serve_points_for|OVER(22), serve_points_for|UNDER(22), serve_points_set1_total|OVER(22), serve_points_set1_total|UNDER(22), serve_points_set2_total|OVER(22), serve_points_set2_total|UNDER(22), serve_points_set1_for|OVER(22), serve_points_set1_for|UNDER(22), serve_points_set2_for|OVER(22), serve_points_set2_for|UNDER(22), tiebreaks_total|UNDER(80), most_aces|OVER(21), most_aces_set1|OVER(22), most_aces_set2|OVER(22), most_double_faults_set1|OVER(22), most_double_faults_set2|OVER(22), most_serve_points|OVER(21), most_serve_points_set1|OVER(22), most_serve_points_set2|OVER(22)


### basketball (Superbet 09-20..10-06; połączone 28773, bez modelu 27248, wierszy modelu 28819)

| rynek | mecze | linie | Δ trafień góra−dół, pp [95% bootstrap po meczach] | ROI wszystkich | ROI górnej 1/3 [95%] | odczyt |
|---|---|---|---|---|---|---|
| **WSZYSTKO** | 589 | 28773 | +9.1 [+1.0; +15.4] | -8.7% | -1.1% [-8.6%; +4.7%] | ROZRÓŻNIA |
| handicap|TEAM | 581 | 4912 | +20.7 [+9.4; +29.9] | -7.4% | +9.8% [-0.3%; +18.4%] | ROZRÓŻNIA |
| total|UNDER | 588 | 4598 | +4.8 [-6.1; +14.2] | -3.0% | +1.4% [-12.9%; +15.3%] | szum |
| total|OVER | 588 | 4598 | +4.9 [-5.4; +15.0] | -12.9% | -10.9% [-26.6%; +3.4%] | szum |
| team_total|UNDER | 290 | 2439 | +10.1 [-0.4; +20.1] | -0.9% | +8.2% [-6.1%; +20.6%] | szum |
| team_total|OVER | 290 | 2439 | +10.1 [-0.5; +19.2] | -15.4% | -7.7% [-21.8%; +6.1%] | szum |
| h1_handicap|TEAM | 478 | 2426 | +9.8 [-2.0; +21.2] | -8.2% | -0.2% [-11.0%; +10.4%] | szum |
| h1_total|UNDER | 477 | 1266 | +1.4 [-10.4; +13.1] | +3.9% | +7.5% [-10.1%; +22.5%] | szum |
| h1_total|OVER | 477 | 1266 | +0.9 [-10.9; +11.8] | -20.6% | -24.0% [-37.6%; -8.6%] | szum |
| h1_team_total|UNDER | 209 | 1107 | +3.6 [-8.7; +12.9] | +5.6% | +12.7% [-4.4%; +25.7%] | szum |
| h1_team_total|OVER | 209 | 1107 | +1.3 [-10.3; +12.1] | -21.5% | -26.5% [-41.9%; -7.7%] | szum |
| winner|TEAM | 564 | 1091 | +10.7 [+1.4; +19.5] | -11.1% | +2.6% [-6.4%; +10.8%] | ROZRÓŻNIA |
| result_1x2|TEAM | 265 | 521 | +17.1 [+0.8; +31.3] | -12.3% | +9.0% [-8.4%; +23.7%] | ROZRÓŻNIA |
| h1_1x2|TEAM | 246 | 492 | +10.6 [-6.0; +25.6] | -5.7% | +2.9% [-14.1%; +19.6%] | szum |
| result_1x2|DRAW | 265 | 265 | – | – | – | brak pasma n>=30 |
| h1_1x2|DRAW | 246 | 246 | – | – | – | brak pasma n>=30 |

### cs2 (Superbet 09-20..10-06; połączone 2696, bez modelu 15276, wierszy modelu 2696)

| rynek | mecze | linie | Δ trafień góra−dół, pp [95% bootstrap po meczach] | ROI wszystkich | ROI górnej 1/3 [95%] | odczyt |
|---|---|---|---|---|---|---|
| **WSZYSTKO** | 185 | 2696 | -2.6 [-13.6; +10.3] | -9.4% | -13.8% [-25.0%; -3.0%] | szum |
| map_team_rounds|UNDER | 52 | 841 | -5.7 [-18.2; +7.1] | -7.9% | -10.2% [-23.1%; +4.2%] | szum |
| map_team_rounds|OVER | 52 | 841 | -7.9 [-17.7; +5.2] | -10.1% | -18.7% [-30.2%; -1.9%] | szum |
| map_winner|TEAM | 130 | 644 | +3.2 [-8.6; +16.8] | -8.9% | -12.1% [-22.8%; +2.5%] | szum |
| match_winner|TEAM | 185 | 370 | +9.1 [-14.0; +27.0] | -12.1% | -10.5% [-30.1%; +9.4%] | szum |


### hockey (Superbet 09-20..10-06; połączone 20858, linie bez modelu 9992)

| rynek | mecze | linie | Δ trafień góra−dół, pp [95% bootstrap po meczach] | ROI wszystkich | ROI górnej 1/3 [95%] | odczyt |
|---|---|---|---|---|---|---|
| **WSZYSTKO** | 556 | 20858 | +3.0 [-1.3; +7.2] | -9.1% | -8.3% [-12.1%; -4.5%] | szum |
| team_total|UNDER | 485 | 2376 | +0.8 [-5.4; +8.5] | -11.0% | -10.7% [-17.1%; -2.9%] | szum |
| team_total|OVER | 485 | 2362 | +1.9 [-4.4; +7.7] | -7.1% | -7.5% [-14.5%; -0.2%] | szum |
| handicap|TEAM | 268 | 1988 | -0.6 [-10.2; +10.0] | -9.1% | -10.5% [-19.4%; -1.0%] | szum |
| total|UNDER | 485 | 1651 | +6.5 [-2.5; +15.1] | -7.6% | -6.2% [-16.8%; +3.8%] | szum |
| total|OVER | 485 | 1651 | +3.2 [-5.4; +12.0] | -8.8% | -8.8% [-19.5%; +2.8%] | szum |
| period_team_total|UNDER (okres 1) | 301 | 1163 | +1.4 [-6.1; +8.2] | -11.9% | -11.1% [-18.2%; -2.7%] | szum |
| period_team_total|OVER (okres 1) | 301 | 1163 | -6.0 [-16.4; +4.1] | -4.5% | -13.3% [-25.1%; +1.0%] | szum |
| period_total|UNDER (okres 1) | 517 | 1144 | +0.7 [-8.7; +10.0] | -14.7% | -12.3% [-22.5%; -1.1%] | szum |
| period_total|OVER (okres 1) | 517 | 1144 | +4.2 [-5.0; +11.0] | -2.0% | -6.3% [-17.0%; +1.5%] | szum |
| winner|TEAM | 515 | 1023 | +1.0 [-8.6; +11.5] | -10.0% | -7.5% [-17.7%; +2.3%] | szum |
| result_1x2|TEAM | 503 | 1006 | -0.2 [-10.9; +9.0] | -11.7% | -11.5% [-23.4%; +0.5%] | szum |
| period_1x2|TEAM (okres 1) | 470 | 940 | +5.1 [-4.1; +14.7] | -11.9% | -6.3% [-22.0%; +8.5%] | szum |
| period_handicap|TEAM (okres 1) | 121 | 718 | +2.8 [-9.1; +18.4] | -8.2% | -9.9% [-21.6%; +3.6%] | szum |
| result_1x2|DRAW | 503 | 503 | – | – | – | brak pasma n>=30 |
| period_1x2|DRAW (okres 1) | 470 | 470 | +9.0 [-3.4; +18.8] | -11.4% | -5.6% [-27.5%; +14.9%] | szum |
| period_handicap|TEAM (okres 2) | 33 | 198 | -31.4 [-68.9; +8.1] | -7.7% | -35.9% [-76.5%; +1.8%] | szum |
| period_handicap|TEAM (okres 3) | 33 | 196 | +29.7 [-3.2; +69.2] | -1.3% | +22.9% [-11.8%; +64.7%] | szum |
| period_team_total|UNDER (okres 3) | 33 | 151 | -1.6 [-29.6; +29.9] | +8.8% | +5.3% [-27.2%; +50.1%] | szum |
| period_team_total|OVER (okres 3) | 33 | 151 | +10.1 [-18.6; +39.4] | -31.2% | -12.5% [-49.1%; +15.3%] | szum |
| period_team_total|UNDER (okres 2) | 33 | 141 | -11.8 [-35.2; +11.0] | -3.6% | -3.2% [-47.8%; +28.0%] | szum |
| period_team_total|OVER (okres 2) | 33 | 141 | -15.8 [-44.1; +21.5] | -5.3% | -23.6% [-52.4%; +14.7%] | szum |
| period_total|UNDER (okres 2) | 33 | 98 | -9.1 [-45.5; +45.5] | -2.1% | -17.5% [-59.4%; +64.9%] | szum |
| period_total|OVER (okres 2) | 33 | 98 | +20.0 [-19.0; +63.3] | -3.7% | +29.1% [-38.3%; +105.2%] | szum |
| period_total|UNDER (okres 3) | 33 | 98 | +0.0 [-33.3; +45.5] | +10.9% | +15.9% [-53.3%; +70.7%] | szum |
| period_total|OVER (okres 3) | 33 | 98 | -4.8 [-33.3; +36.4] | -37.0% | -34.5% [-68.1%; +26.5%] | szum |
| period_1x2|TEAM (okres 2) | 31 | 62 | – | – | – | za mało |
| period_1x2|TEAM (okres 3) | 31 | 62 | – | – | – | za mało |
| period_1x2|DRAW (okres 2) | 31 | 31 | – | – | – | za mało |
| period_1x2|DRAW (okres 3) | 31 | 31 | – | – | – | za mało |

### volleyball (Superbet 09-20..10-06; połączone 3096, linie bez modelu 3156)

| rynek | mecze | linie | Δ trafień góra−dół, pp [95% bootstrap po meczach] | ROI wszystkich | ROI górnej 1/3 [95%] | odczyt |
|---|---|---|---|---|---|---|
| **WSZYSTKO** | 235 | 3096 | +3.6 [-6.1; +14.5] | -9.8% | -6.2% [-15.8%; +3.0%] | szum |
| set_handicap|TEAM | 187 | 490 | +5.1 [-11.1; +20.3] | -9.0% | -4.5% [-22.5%; +9.9%] | szum |
| winner|TEAM | 234 | 460 | -2.2 [-18.9; +11.3] | -15.2% | -4.3% [-21.6%; +7.2%] | szum |
| points_handicap|TEAM | 92 | 312 | +10.9 [-22.8; +37.9] | -7.7% | +3.0% [-27.5%; +28.6%] | szum |
| set_winner|TEAM (okres 1) | 135 | 270 | -6.6 [-29.6; +15.8] | -12.8% | -28.7% [-49.0%; -5.5%] | szum |
| points_total|UNDER | 181 | 247 | +11.6 [-14.9; +27.0] | -14.2% | -7.3% [-43.1%; +12.5%] | szum |
| points_total|OVER | 181 | 247 | +6.5 [-12.5; +25.3] | -2.0% | +4.8% [-23.3%; +32.8%] | szum |
| sets_total|UNDER | 98 | 196 | +25.1 [+4.3; +41.0] | +2.9% | +22.6% [-6.8%; +45.6%] | ROZRÓŻNIA |
| sets_total|OVER | 98 | 196 | +23.5 [-7.5; +43.4] | -24.0% | -12.6% [-44.1%; +23.1%] | szum |
| set_winner|TEAM (okres 2) | 77 | 154 | +16.2 [-19.7; +44.0] | -9.4% | +22.9% [-19.2%; +52.1%] | szum |
| set_winner|TEAM (okres 3) | 67 | 134 | -24.4 [-45.5; +33.6] | -0.6% | -26.3% [-53.5%; +58.6%] | szum |
| set_points_total|UNDER (okres 1) | 115 | 133 | -13.5 [-37.8; +10.3] | -9.2% | -19.4% [-48.7%; +6.3%] | szum |
| set_points_total|OVER (okres 1) | 115 | 133 | -12.4 [-39.5; +13.5] | -6.9% | -17.4% [-50.5%; +12.8%] | szum |
| set_winner|TEAM (okres 4) | 37 | 74 | – | – | – | za mało |
| set_winner|TEAM (okres 5) | 15 | 30 | – | – | – | za mało |
| set_points_total|UNDER (okres 2) | 10 | 10 | – | – | – | za mało |
| set_points_total|OVER (okres 2) | 10 | 10 | – | – | – | za mało |
