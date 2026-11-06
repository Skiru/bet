# Piłka - rynki symulatora: próg pewności 0,60 - pomiar 2026-11-06

Zgoda operatora („TAK!") przekazana przez sesję główną: zmierzyć próg 0,60 dla
rynków symulatora (`epochs.FOOTBALL_SIM_MARKETS`), tak jak
`TENNIS_TOTALS_FLOOR` 11-05 (`tennis_totals_floor_2026-11-05.md`,
`scripts/sofa/measure_tennis_totals_floor.py`).

## 0. Reguły zapisane PRZED liczeniem (pre-rejestracja)

Sekcję zapisano przed policzeniem jakiejkolwiek liczby w paśmie 0,60-0,70.
Znane wcześniej były tylko liczby z `football_sim_wiring_2026-11-06.md` (nogi
>= 0,70).

**Populacja:**

- linie backfillu `data/line_evidence/football_sim_lines.jsonl.gz` z dni
  2026-10-20..11-05, czyli odłożona próba wpięcia (po oknie krzywych
  06-01..10-19);
- ostatni zrzut przed startem, rozliczenie `football_sim_markets.sim_value`
  (to samo, co SETTLE);
- p jak w SHEET.

**Pewność** jak w wariancie B wpięcia: krzywa `config/sofa_football_sim_curves.json`
nałożona na kalibrację dnia 2026-11-07, potem dowody z linii zainstalowane dziś
(`LineEvidence.read`, ustawienia dnia 11-07).

**Pasmo:** pewność w [0,60; 0,70). Noga musi przejść wszystkie pozostałe bramki
druku, tak jak CONFIDENCE:

- kurs >= `MIN_ODDS_FOR_CEILING` (`ODDS_TOO_LOW`);
- p_central >= 0,60 (`CATCH_ALL_BUCKET`);
- x = pewność x kurs >= 0,90;
- przy rynkach dwustronnych (`team_scores_both_halves`, `btts_any_half`) marża
  szczebla <= 15% z obu cen tego samego zrzutu, bez drugiej ceny odmowa;
- jednostronna tylko z własną krzywą (źródło `market:` / `line:`) z n >= 300.

**Jednostka oceny:** osobno każdy z 11 kluczy rynek|kierunek
(`htft|OVER`, `result_1h|OVER`, `result_2h|OVER`, `higher_scoring_half|OVER`,
`team_scores_both_halves|OVER`, `team_scores_both_halves|UNDER`,
`btts_halves|OVER`, `btts_any_half|OVER`, `btts_any_half|UNDER`,
`first_goal_1h|OVER`, `half_goals_combo|OVER`). Klasa `women` liczy się do
swojego klucza.

**Statystyki** (bootstrap po meczach, 2 000 losowań, ziarno 7, wszystkie nogi
meczu razem):

- (a) trafione minus pewność (kalibracja);
- (b) trafione minus cena bez marży. Przy rynkach dwustronnych marżę zdejmuje
  się proporcjonalnie z pary cen szczebla. Przy rynkach wielowynikowych - z
  pełnego zbioru wyników rynku w tym samym zrzucie meczu: htft 9 wyników,
  result 1H/2H 3, połowa z większą liczbą goli 3, btts_halves 4, pierwszy gol
  1. połowy 3, kombinacje goli 4 wyniki tej samej pary linii. Suma
  odwrotności musi mieścić się w [1,00; 1,60] (reguła pomiaru symulatora), a
  zbiór niepełny daje brak ceny bez marży dla nogi;
- (c) trafione minus 1/kurs;
- ROI płaskiej stawki i ROI po podatku 12% (zwrot 0,88 x kurs) - **jako fakty,
  nie kryterium**.

**Werdykt na klucz** (reguła operatora z 11-05 dla tenisa, „jak cena, marża
przyjęta"). Klucz PRZECHODZI, gdy jednocześnie:

1. **n_min:** w paśmie >= 100 nóg i >= 50 meczów (w oknie 17 dni);
2. **skalibrowane:** górna granica przedziału (a) >= 0, czyli przedział
   zawiera 0 albo leży nad nim;
3. **na poziomie ceny:** górna granica przedziału (b) >= 0, liczona na nogach
   z ceną bez marży. Jeśli takich nóg jest mniej niż 100, warunek nie jest
   spełniony.

Klucz, który nie spełnia któregokolwiek warunku, nie dostaje progu 0,60.
Wynik liczony **raz**. Żadnych progów pośrednich (0,65), podziałów ani
zmian reguły po obejrzeniu liczb.

Skrypt (tylko odczyt): `scripts/sofa/measure_football_sim_floor.py`.

## 1. Wynik

Skrypt uruchomiony raz (`--out`). W oknie 168 194 linii; w paśmie po
wszystkich bramkach 2 512 nóg / 1 711 meczów.

Odmowy w paśmie:

- `x < 0,90`: 3 004;
- `ODDS_TOO_LOW`: 17;
- jednostronne bez własnej krzywej: 2;
- bez pewności: 200 (cała próba).

Przedziały 95% z bootstrapu po meczach (pp = punkty procentowe):

| klucz | nogi / mecze | pewność | trafione | traf. - pewność | traf. - cena bez marży | ROI | ROI po podatku | werdykt |
|---|---|---|---|---|---|---|---|---|
| `half_goals_combo` OVER | 1 351 / 1 121 | 0,645 | 0,674 | +2,9 [+0,4; +5,4] | +6,6 [+4,1; +9,0] | -3,2% [-6,8; +0,3] | -14,8% | **PASS** |
| `team_scores_both_halves` UNDER | 897 / 872 | 0,654 | 0,631 | -2,3 [-5,5; +0,8] | -1,4 [-4,6; +1,6] | -9,9% [-14,5; -5,6] | -20,7% | **PASS** (na granicy) |
| `btts_any_half` UNDER | 110 / 110 | 0,619 | 0,664 | +4,4 [-4,7; +12,7] | +4,8 [-4,3; +13,0] | -0,9% [-14,5; +11,6] | -12,8% | **PASS** |
| `btts_halves` OVER | 106 / 106 | 0,620 | 0,708 | +8,8 [+0,2; +17,1] | +12,5 [+3,9; +20,9] | +5,8% [-7,0; +18,3] | -6,9% | **PASS** |
| `first_goal_1h` OVER | 18 / 18 | 0,606 | 0,611 | +0,6 [-21,9; +22,9] | | -6,4% | | za mało nóg |
| `result_2h` OVER | 16 / 16 | 0,627 | 0,688 | +6,0 [-18,1; +25,5] | | 0,0% | | za mało nóg |
| `result_1h` OVER | 7 / 7 | 0,605 | 0,429 | -17,7 | | -35,4% | | za mało nóg |
| `htft` OVER | 4 / 4 | 0,606 | 0,500 | | | | | za mało nóg |
| `team_scores_both_halves` OVER | 3 / 3 | | | | | | | za mało nóg |
| `btts_any_half` OVER, `higher_scoring_half` OVER | 0 | | | | | | | za mało nóg |

Całe pasmo: 2 512 nóg, +1,3 pp [-0,7; +3,2] wobec pewności, +3,8 pp [+1,8;
+5,7] wobec ceny bez marży, -3,6 pp [-5,7; -1,7] wobec 1/kurs, ROI -5,2%
[-8,1; -2,4], po podatku -16,6%.

**Werdykt: próg 0,60 przechodzi dla 4 z 11 kluczy:**

- `half_goals_combo` OVER;
- `team_scores_both_halves` UNDER;
- `btts_any_half` UNDER;
- `btts_halves` OVER.

Pozostałe 7 kluczy ma za mało nóg w paśmie (n_min) i dostaje „zmierzone i
odrzucone".

Uwagi (fakty, nie kryterium):

- **`team_scores_both_halves` UNDER przechodzi na granicy.** Średnio obiecuje
  za dużo (-2,3 pp; górna granica +0,8) i traci najwięcej: ROI -9,9%, po
  podatku -20,7%. Reguła zamrożona go przepuszcza.
- **Dwa wąskie klucze częściowo się pokrywają.** `btts_any_half` UNDER („nie"
  przy „obie strzelą w którejkolwiek połowie") to to samo zdarzenie co
  `btts_halves` „Nie/Nie"; pozostałe wybory `btts_halves` są inne. Oba klucze
  mają po ok. 110 nóg, a przedziały sięgają ok. +-8 pp.
- **Żaden klucz nie zarabia po podatku.** Przewagi nad ceną nie ma; nogi są
  „jak cena" (marża przyjęta), jak tenis 11-05.

## 2. Wpięcie

- `epochs.FOOTBALL_SIM_FLOOR_FROM_UTC` = 2026-11-07 00:00Z (razem z
  `FOOTBALL_SIM`), `FOOTBALL_SIM_FLOOR` = 0,60, `FOOTBALL_SIM_FLOOR_KEYS` (4
  klucze), `epochs.leg_floor`.
- Noga wydrukowana poniżej 0,70 niesie `floor_rule` (własny próg; audyt C2 go
  sprawdza) i nie wchodzi do buildera.
- PDF w nagłówku: „piłka: rynki połów od 0.6".
- Grupa ledgera „od 11-07".
- Testy: `tests/sofa/test_football_sim_floor.py`.

E2E na kopii dnia 2026-11-05 (zegar 17:10Z), symulator włączony, próg
włączony wobec wyłączonego:

- single +63, 0 ubyło (49 `half_goals_combo`, 11 `team_scores_both_halves`
  UNDER, 2 `btts_halves`, 1 `btts_any_half` UNDER). Wszystkie z `floor_rule`
  0,6, pewność 0,606-0,685, kurs >= 1,32;
- pozostałe nogi bez zmian (0 zmian pewności, kursu i blokady); buildery 54 /
  54 identyczne, 0 nóg z progiem w builderach;
- `audit_variants` C2 bez uwag (pod przełącznikiem); różni się tylko nota C3
  (283 wobec 263 nóg do czytania wydrukowanych bez czytania);
  `audit_coupon` identyczny;
- PDF wyrenderowany bez błędu.
