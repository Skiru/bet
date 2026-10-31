# Kupon z czatu (`/kupon`): który przepływ traci najmniej (2026-10-31)

Pytanie operatora (10-31): który sposób składania kuponu z czatu (AKO) z nóg
kuponu dnia traci najmniej po podatku? Odpowiedź: **żaden nie wychodzi nad
zero po podatku**; najmniej tracą pojedyncze nogi i kupony 2-nożne, każda
kolejna noga kosztuje ok. 5% zwrotu, Bet Buildery tracą tyle co pojedyncze
albo więcej, a stary cel `build_slip.py` (maks. iloczyn pewności, 2-5 nóg)
był najgorszy. Na tej podstawie operator dał zgodę (10-31) na przepływ
„najmniejszej straty” w `/kupon` (`bet.sofa.slip_builder`, sekcja na końcu).

Wszystko offline, tylko do odczytu (`runs/sofa/<d>/printed/*.json`,
`13_results.json`, `closing.jsonl`, `data/sofa.db` w trybie `mode=ro`).
Skrypty i surowe wyniki: `docs/sofa/evidence/slip_flow_backtest_2026-10-31/`
(kopie ze scratchpada sesji; tabela nóg `legs.pkl` ~45 MB nie jest
skopiowana - `load.py` odtwarza ją z artefaktów dni). Liczby poniżej są
przepisane z plików `*.out` w tym katalogu.

## Metoda

- **Dni**: dev (walk-forward) 2026-10-13..10-26 (14 dni), hold-out
  2026-10-27..10-30 (4 dni), oglądany **raz**, po zamrożeniu przepływów.
- **Moment decyzji**: pierwszy wydruk dnia (`printed/<ts>.json`, rano), kurs z
  tego wydruku; noga rozpoczęta przed wydrukiem odpada; nogi do startu > 15
  min. Ocena: `13_results.json` (oceny dziennika), brakujące z
  `sofa_settled_row`.
- **Podatek**: polski podatek od obrotu 12% - wypłata = 0,88 × stawka ×
  iloczyn kursów, gdy wszystkie nogi wchodzą.
- **ROI nogi** przed podatkiem = trafienie × kurs − 1; przedziały: bootstrap
  po meczu (1000 prób). Kupony: do 10 rozłącznych kuponów dziennie (jedna
  noga z meczu), stała stawka 1 j., przedziały po dniu i po kuponie,
  losowe przepływy w 20-30 ziarnach.

## 1. Noga kuponu realizuje się poniżej ceny

`per_leg_13results.out` - wszystkie ocenione nogi `13_results.json`
2026-10-20..10-30 (won / lost, z kursem):

| n | trafienie | śr. 1/kurs | trafienie / (1/kurs) | zwrot na 1 j. |
|---|---|---|---|---|
| 49 189 | 0,7815 | 0,8270 | 0,9450 | 0,9449 |

`per_leg.out` - te same dni z tabeli wydruków (poranny wydruk,
odduplikowany): n 50 749, trafienie 0,782, 1/kurs 0,827, stosunek **0,946**;
ROI −5,5% [−6,1; −4,9]. Stała w kodzie `REALISED_PER_LEG = 0.946`
(źródło podane przy stałej; z pełnego `13_results` wychodzi 0,945 - różnica
w trzecim miejscu, bez wpływu na wnioski).

Stąd linia pieniędzy kuponu n-nożnego: **0,88 × 0,946^n − 1**
(1 noga −16,8%, 2 −21,2%, 3 −25,5%, 4 −29,5%).

## 2. Hold-out 2026-10-27..10-30 (`final_holdout.out`)

Próg niskiej marży z walk-forward na każdy dzień hold-outu: 0,08.

Nogi (pojedyncze):

| pula | n | ROI przed podatkiem | pojedyncza po podatku | trafienie | 1/kurs |
|---|---|---|---|---|---|
| niska marża (dwustronne, overround < 0,08) | 1 624 | −5,8% [−9,0; −2,7] | −17,1% [−19,9; −14,4] | 0,775 | 0,821 |
| wszystkie drukowane | 14 750 | −5,2% [−6,5; −4,0] | **−16,6%** [−17,7; −15,5] | 0,782 | 0,825 |

Kupony (do 10 rozłącznych dziennie, stawka 1 j., wypłata 0,88 × iloczyn):

| przepływ | nóg | iloczyn | trafienie | ROI po podatku | CI po dniu | CI po kuponie | ziarna |
|---|---|---|---|---|---|---|---|
| F1 niska marża, 2 nogi [1,6; 2,4], losowo | 2,00 | 1,71 | 0,519 | −24,6% | [−42,1; −9,0] | [−29,4; −19,6] | [−44,2; −6,3] |
| F2 niska marża, 3 nogi [2,5; 3,5], losowo | 3,00 | 2,58 | 0,360 | −26,4% | [−57,3; −7,1] | [−33,2; −19,2] | [−52,0; −3,8] |
| B1 wszystkie, 2 nogi [1,6; 2,4], losowo | 2,00 | 1,71 | 0,569 | **−19,0%** | [−22,7; −15,3] | [−23,8; −14,2] | [−39,5; +3,7] |
| B2 wszystkie, 3 nogi [2,5; 3,5], losowo | 3,00 | 2,58 | 0,345 | −30,2% | [−37,0; −20,4] | [−36,9; −23,4] | [−49,4; −12,6] |
| B3 wszystkie, 2-4 nogi [2,5; 3,5], losowo | 4,00 | 2,65 | 0,334 | −28,5% | [−31,5; −25,6] | [−35,2; −21,5] | [−49,9; −5,4] |
| B4 **stary cel** (maks. iloczyn pewności) 2-4 [2,5; 3,5] | 3,50 | 2,52 | 0,350 | −31,5% | [−53,6; −9,6] | [−60,5; −0,9] | 40 kuponów |

## 3. Dev 2026-10-13..10-26

### Cel kuponu (`iter_a_slips.out`; cel [2,5; 3,5], 2-4 nogi, do 3 kuponów dziennie)

| cel wyszukiwania | kuponów | trafienie | śr. iloczyn | nóg | ROI po podatku [CI] |
|---|---|---|---|---|---|
| CUR log(pewność) - stary cel | 42 | 0,214 | 2,52 | 3,57 | **−60,9%** [−80,0; −41,5] |
| EVc log(min(pewność, 1/kurs + 0,03) × kurs) | 42 | 0,381 | 3,52 | 4,00 | −5,1% [−50,1; +42,6] |
| EVraw log(pewność × kurs) | 42 | 0,214 | 3,45 | 3,69 | −51,4% [−78,7; −23,4] |
| LOWM overround ≤ 0,06, log(pewność) | 27 | 0,259 | 2,53 | 3,85 | −42,1% [−76,6; −1,7] |
| SPEC bez rynków „stopy bazowej” | 42 | 0,190 | 2,52 | 3,57 | −66,2% [−84,9; −47,1] |
| KEEP tylko nogi z porannym KEEP | 39 | 0,436 | 2,53 | 3,41 | −18,4% [−49,7; +11,8] |
| RAND (30 ziaren) | 42/ziarno | 0,351 | 2,64 | - | −22,0% (ziarna [−58,3; +12,5]) |

Stary cel kupował największe niezgody modelu z ceną (pewność wysoko ponad
1/kurs) - a te realizują się po cenie (`T-PRICE-GAP-flag`). Dlatego szansa
nogi w `/kupon` to `min(pewność, 1/kurs)` dla nogi > 3 pp ponad ceną (już w
kodzie przed 10-31).

### Pule nóg (`iter_b_legs.out`; ROI nogi przed podatkiem; implikowany losowy AKO po podatku = 0,88 × (1 + r)^n − 1)

| pula | n | ROI | pojedyncza po podatku | 2 nogi | 3 nogi |
|---|---|---|---|---|---|
| P0 wszystkie drukowane | 65 334 | −5,4% [−6,0; −4,8] | −16,7% | −21,2% | −25,5% |
| P1 dwustronne, overround < 0,08 | 7 116 | **−3,1%** [−4,6; −1,6] | −14,7% | −17,4% | −19,9% |
| P2 dwustronne, overround < próg walk-forward | 9 185 | −3,2% [−4,6; −1,8] | −14,8% | −17,5% | −20,1% |
| P3 poranny KEEP | 6 027 | −3,9% [−5,9; −1,7] | −15,5% | −18,8% | −22,0% |
| P4 overround < 0,08 i KEEP | 1 287 | −4,8% [−9,4; −1,1] | −16,2% | −20,3% | −24,1% |
| P5 najniższa marża w drabince | 39 881 | −4,9% [−5,5; −4,3] | −16,4% | −20,5% | −24,4% |
| P6 najwyższa pewność w drabince | 54 339 | −5,4% [−5,9; −4,9] | −16,8% | −21,3% | −25,6% |
| P7 zgoda 0 ≤ pewność − 1/kurs < 0,03 | 7 167 | −4,5% [−5,9; −2,9] | −15,9% | −19,7% | −23,2% |
| P8 kurs ≥ 1,30 | 11 892 | −5,1% [−6,4; −3,8] | −16,5% | −20,7% | −24,7% |
| P9 overround < 0,08 i kurs ≥ 1,30 | 1 356 | −3,3% [−7,4; +0,5] | −14,9% | −17,7% | −20,4% |

### Niska marża w obrębie rynku (`iter_c.out`)

49 rynków z nogami obu rodzajów, 7 113 nóg niskiej marży: różnica ROI
(niska − wysoka), ważona n niskiej: **+2,16 pp [+0,13; +4,24]**. Per sport
(przed podatkiem): piłka −3,8% vs −5,4%, hokej −2,3% vs −4,4%, tenis +6,9%
(n 123) vs −4,4%. Na hold-oucie się **nie** potwierdziło: −5,8% vs −5,2%
(tabela 2). Dlatego w `/kupon` niska marża jest tylko rozstrzygnięciem
remisu, nie bramką.

### Ruch ceny do zamknięcia (`iter_a_clv.out`, kontekst)

54 824 nogi z ceną zamknięcia; nogi, których kurs potem spadł: −3,7% po
cenie porannej; bez ruchu −5,4%; wydłużone −7,7%. Korelacja ruchu z
pewność − 1/kurs 0,088, z marżą −0,02 - ruchu nie widać rano; nie użyte.

## 4. Bet Buildery (`builders.out`)

Drukowane buildery (pierwszy wydruk dnia), ocena z `13_results.json`
`builders`. Superbet nie wycenia buildera jako iloczynu - kurs modelowany
**założeniem** 0,90 × iloczyn kursów nóg (i dla porównania 1,00 ×):

| okres | n | trafienie | śr. iloczyn pewności | śr. iloczyn kursów | po podatku przy 1,00 × | po podatku przy 0,90 × |
|---|---|---|---|---|---|---|
| dev 10-13..10-26 | 88 | 0,670 | 0,685 | 1,57 | −7,4% [−22,0; +7,0] | **−16,6%** [−29,8; −3,7] |
| hold-out 10-27..10-30 | 10 | 0,400 | 0,686 | 1,59 | −39,8% [−85,2; +5,6] | **−45,8%** [−86,6; −4,9] |

## Co z tego weszło do `/kupon` (zgoda operatora 2026-10-31)

1. **Domyślnie 2 nogi** (`slip_builder.MAX_LEGS = 2`; `--max-legs` podnosi
   limit, a odpowiedź podaje wtedy koszt każdej nogi: 0,88 × 0,946^n − 1).
   **Buildery wyłączone** (`--builders` tylko na prośbę; odpowiedź podaje
   −16,6% / −45,8%).
2. **Cel poza zasięgiem limitu nóg** (np. ~4 z 2 nogami po maks. 2,00):
   pierwsza linia mówi „na ~4 trzeba 3 nóg - każda kolejna noga to ok. −5%
   więcej; z 2 nogami najbliżej ~X” i skrypt składa najbliższy kupon pod
   celem (najwyższy iloczyn osiągalny limitem nóg, przy nim najlepsza
   szansa) - nigdy po cichu dodatkowej nogi; kod wyjścia 1.
3. **Niska marża**: noga z dwustronnej drabinki z overround < 0,08 dostaje w
   wyszukiwaniu +0,25% względnej szansy (`LOW_MARGIN_TIE`, tyle co premia za
   świeży KEEP) - jawna, mała preferencja działająca jak rozstrzygnięcie
   remisu; pokazywana szansa bez zmian; kolumna „marża” („1-str.” = rynek
   jednostronny, bez overround).
4. **Cel bez zmian**: maks. suma log(szansy zmierzonej) przy iloczynie kursów
   ≥ cel, jedna noga z meczu.
5. **Uczciwa linia pieniędzy** zamiast „zwrot wg naszych liczb” (liczonego z
   pewności): „oczekiwany zwrot po podatku ≈ 0,88 × 0,946^n − 1 = −X% stawki
   (zmierzone: nogi kuponu 10-20..10-30, n 49 189; podatek 12%)” - w
   pierwszych liniach i przy każdym kuponie; pojedyncza poniżej kursu
   1/0,88 = 1,136 ma dopisek „wygrana zwraca mniej niż gotówka”.

Testy: `tests/sofa/test_slip_builder.py` (`test_default_is_two_legs_and_builders_are_opt_in`,
`test_target_out_of_reach_of_the_leg_limit_is_said_first`,
`test_low_margin_leg_wins_a_tie_and_the_margin_is_shown`,
`test_objective_is_the_measured_chance_unchanged`,
`test_money_line_is_measured_after_tax_never_our_confidence`).

Zastrzeżenia: hold-out to 4 dni (10 builderów, 40 kuponów starego celu) -
przedziały szerokie; 0,946 to średnia wszystkich nóg kuponu, nie konkretnej
nogi; kurs buildera 0,90 × iloczyn to założenie (zmierzony markup 8,8-19,6%).
