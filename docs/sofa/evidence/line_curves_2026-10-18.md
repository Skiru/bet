# Krzywe historii per linia (piłka) - pomiar i wdrożenie 2026-10-18

Zlecenie operatora (2026-10-18, „Popraw!”): przeszacowanie `goals_for`
widoczne na drukowanych nogach 10-09..10-17 (OVER -4,1 pp, UNDER -3,1 pp).

## 1. Skąd luka: wspólna krzywa na wszystkie linie

Na **wszystkich** rozliczonych wierszach `goals_for` z ceną Superbetu
(10-09..10-17, mężczyźni, dzisiejsza krzywa) przy pewności >= 0,70: OVER
-0,9 pp [-2,8; +0,9] (1 949 wierszy), UNDER -0,9 pp [-2,1; +0,3] (4 280) - krzywa
kierunku jest w sumie skalibrowana; luka na drukowanych nogach to w większości
selekcja x >= 0,90 (OVER -3,3 pp, UNDER -2,3 pp), opisana w
`selection_walk_forward_2026-10-18.md`. Wyjątek to **linia**: UNDER 1,5 -3,9 pp
[-7,3; -0,7] (726 wierszy).

Krzywa jest fitowana per rynek x kierunek na całej siatce linii replayu
(`lines_for`), a Superbet wystawia kilka linii przy środku. Na całym replayu
2026-10-17 (wszystkie mecze, krzywa w próbie) `goals_for` UNDER: linia 0,5
-7,1 pp, 1,5 **-2,4 pp [-2,6; -2,3]** (304 875 wierszy), 2,5 -0,2, 3,5 +0,6 ...
6,5 +1,0, 9,5 +2,7; OVER 3,5 -5,5, 4,5 -14,6. Strona „trudna” blisko środka
jest przeszacowana, dalekie trywialne linie niedoszacowane, a suma wychodzi na
zero. Ten sam mechanizm, co przy rynkach serwisowych tenisa
(`tennis_aces_opponent_2026-10-17.md`, sekcja 4).

## 2. Pomiar poza próbą (historia)

`scripts/sofa/measure_line_curves.py --db data/refit_2026-10-17/sofa_replay.db`:
replay 2026-10-17, mecze piłki mężczyzn, trening 2025-07-01..2026-03-31, test
2026-04-01..2026-10-12 (data meczu z listingu; 59,4 mln wierszy w oknie), ocena
**tylko na liniach rynkowych** - liniach z >= 20 wierszami z ceną Superbetu
10-09..10-17. Warianty, każdy fitowany jak `fit_confidence` (kubełki, Wilson,
>= 400 wierszy):

- A - krzywa wspólna (dzisiejsza),
- B - krzywa per linia (kubełek bez 400 wierszy czyta A),
- C - jedna krzywa z samych linii rynkowych.

| | A | B | C |
|---|---|---|---|
| luka przy krzywej >= 0,70 (wszystkie klucze) | +0,04 pp | +0,50 pp | +0,28 pp |
| średnia \|luka\| linii, ważona | 1,21 pp | **0,92 pp** | 1,24 pp |
| log-loss na wierszach z p >= 0,70, vs A | - | **-6,4e-4 [-7,0; -5,8]** | -1,2e-4 [-1,4; -1,0] |

Per klucz (rynek x kierunek): **B lepsze w 33** (przedział poniżej zera; klucze
wybrano na tym samym oknie testowym, więc ich pojedyncze „poniżej zera” są
mierzone na oknie, które je wybrało - kilka jest na granicy: `fouls_1h_for`
UNDER, `fouls_for` OVER, `saves_for` OVER, `goals_2h_total` OVER; łączny wynik
-6,4e-4 jest od tego odporny; sprawdzian na nowych danych per klucz), gorsze
w 6 (`goal_kicks_total` OVER, `saves_1h_for` OVER, `shots_1h_total` OVER,
`shots_on_target_2h_for` OVER, `shots_total` OVER / UNDER), bez różnicy w 60.
Krzywe per linia dostaje tylko 33 lepszych (`config/sofa_line_curves.json`):

| klucz | wiersze testu | B - A log-loss x1e4 [95%] | śr. \|luka\| linii A → B (pp) | luka A → B (pp) |
|---|---|---|---|---|
| `shots_on_target_2h_total\|UNDER` | 2 547 | -38,6 [-58,9; -16,3] | 3,22 → 0,66 | -3,22 → -0,22 |
| `shots_2h_for\|UNDER` | 15 302 | -25,3 [-32,2; -18,6] | 3,71 → 1,76 | -3,71 → -1,76 |
| `player_tackles_for\|OVER` | 51 503 | -24,4 [-29,9; -18,5] | 1,96 → 1,28 | +1,06 → +0,82 |
| `shots_2h_total\|UNDER` | 2 352 | -22,5 [-30,7; -13,5] | 4,51 → 2,69 | -4,51 → -2,69 |
| `shots_on_target_1h_for\|UNDER` | 9 359 | -21,6 [-30,3; -12,5] | 2,2 → 0,5 | -2,20 → +0,16 |
| `player_shots_for\|OVER` | 22 825 | -20,4 [-28,0; -13,6] | 4,38 → 3,15 | +3,23 → +2,41 |
| `shots_1h_for\|UNDER` | 21 209 | -20,2 [-26,9; -13,9] | 2,3 → 0,47 | -2,30 → -0,07 |
| `player_fouls_for\|OVER` | 39 562 | -19,0 [-24,4; -13,0] | 0,92 → 0,85 | +0,82 → +0,76 |
| `corners_for\|UNDER` | 197 749 | -18,3 [-21,3; -14,9] | 1,69 → 0,77 | +0,14 → +0,70 |
| `goals_1h_for\|UNDER` | 273 904 | -16,3 [-18,5; -14,1] | 1,07 → 0,11 | -0,26 → +0,07 |
| `goals_2h_for\|UNDER` | 287 911 | -16,1 [-18,2; -14,2] | 1,34 → 0,29 | -0,70 → -0,29 |
| `offsides_for\|UNDER` | 40 142 | -14,3 [-21,5; -6,7] | 0,6 → 1,94 | -0,58 → +1,59 |
| `shots_on_target_2h_for\|UNDER` | 17 733 | -11,4 [-17,2; -5,9] | 1,65 → 0,24 | -1,65 → -0,24 |
| `fouls_2h_for\|OVER` | 4 470 | -10,8 [-19,5; -1,8] | 1,2 → 3,19 | -1,20 → +0,91 |
| `goals_1h_total\|UNDER` | 163 622 | -10,5 [-13,2; -8,2] | 0,72 → 0,23 | +0,02 → +0,08 |
| `shots_on_target_for\|UNDER` | 157 213 | -9,6 [-12,1; -7,4] | 1,21 → 0,63 | -0,17 → +0,51 |
| `shots_for\|UNDER` | 98 619 | -9,1 [-13,7; -4,3] | 2,04 → 0,57 | -1,29 → -0,22 |
| `goals_2h_total\|UNDER` | 186 464 | -8,6 [-11,1; -6,3] | 0,92 → 0,58 | -0,56 → -0,55 |
| `corners_1h_total\|OVER` | 19 924 | -8,2 [-12,4; -3,5] | 1,59 → 1,55 | +1,15 → +1,37 |
| `goal_kicks_for\|UNDER` | 26 989 | -8,2 [-11,2; -5,2] | 2,27 → 1,03 | -2,21 → -0,76 |
| `goals_for\|UNDER` | 580 686 | -8,2 [-9,2; -7,1] | 0,93 → 0,38 | -0,70 → -0,38 |
| `corners_2h_for\|UNDER` | 51 313 | -6,8 [-11,3; -1,7] | 0,69 → 0,97 | +0,14 → +0,95 |
| `corners_2h_total\|OVER` | 21 278 | -5,1 [-9,1; -0,9] | 1,88 → 2,01 | +1,88 → +2,01 |
| `goals_total\|OVER` | 232 505 | -4,5 [-6,2; -2,8] | 1,27 → 1,29 | +0,81 → +1,24 |
| `corners_1h_for\|UNDER` | 39 824 | -4,4 [-9,0; -0,6] | 0,54 → 1,24 | +0,21 → +1,24 |
| `saves_for\|UNDER` | 90 441 | -4,2 [-6,5; -1,8] | 0,6 → 0,29 | -0,52 → +0,04 |
| `goals_total\|UNDER` | 301 964 | -3,6 [-4,9; -2,4] | 0,86 → 0,54 | -0,78 → -0,54 |
| `shots_for\|OVER` | 57 091 | -3,2 [-5,9; -0,5] | 2,18 → 2,8 | +1,85 → +2,63 |
| `corners_for\|OVER` | 125 708 | -3,0 [-4,4; -1,6] | 1,1 → 1,16 | +0,65 → +1,03 |
| `fouls_for\|OVER` | 55 040 | -1,6 [-3,0; -0,4] | 0,51 → 0,68 | -0,28 → +0,68 |
| `saves_for\|OVER` | 73 508 | -1,6 [-2,8; -0,5] | 1,49 → 1,58 | +1,46 → +1,57 |
| `fouls_1h_for\|UNDER` | 5 110 | -1,3 [-2,7; -0,0] | 0,34 → 1,38 | -0,34 → +0,87 |
| `goals_2h_total\|OVER` | 96 324 | -1,0 [-1,9; -0,2] | 1,38 → 1,26 | +1,15 → +1,25 |

Gdzie średnia \|luka\| rośnie (np. `offsides_for` UNDER, `fouls_2h_for` OVER),
to w stronę niedoszacowania: krzywa per linia ma mniej wierszy, więc jej dolna
granica Wilsona jest niżej - ostrożniej, nie śmielej. Przykłady linii:
`goals_for` UNDER 1,5 -3,85 → -0,49 pp (62 297 wierszy), `goals_total` UNDER 3,5
-2,30 → -0,31, `corners_for` UNDER 5,5 -2,69 → +0,18, `shots_1h_for` UNDER 6,5
-2,86 → -0,21.

## 3. Wiersze z życia

Krzywe B fitowane na wierszach replayu (bez wierszy z życia, ale bez cięcia
po dacie: replay zawiera odtworzone mecze 10-09..10-12, więc ta część nie jest
w pełni poza próbą), nałożone na
wszystkie rozliczone wiersze z ceną Superbetu 10-09..10-17 w 33 kluczach
(125 788 wierszy, bez line evidence i bez pozostałych bramek):

| | luka przy pewności >= 0,70 | „drukowalne” (>= 0,70, x >= 0,90) | ROI [95%] | jednostki |
|---|---|---|---|---|
| A | -1,09 pp [-1,70; -0,39] | 25 925 / 2 869 meczów | -4,54% [-5,56; -3,60] | -1 176,0 |
| B | **-0,57 pp [-1,27; +0,09]** | 24 698 / 2 869 meczów | -4,53% [-5,46; -3,67] | -1 118,2 |

Odpadłe w B: 1 823 wiersze, ROI -5,84% [-9,19; -2,59]; dodane: 596, -8,16%
[-12,48; -3,65]; wspólne: 24 102, -4,44%. **Kalibracja lepsza, ROI bez zmian** -
mniej strat z mniejszej liczby nóg, nie przewaga nad ceną.

## 4. Wdrożenie i E2E

- Fit: `fit_confidence.py --db-path data/refit_2026-10-17/sofa_replay.db --out
  data/refit_line_curves_2026-10-18/sofa_confidence_calibration.json
  --line-curves-only` (119 040 225 wierszy, 33 klucze, 371 linii, 7,5 min);
  zainstalowane `install_line_curves.py --confirm` 2026-10-18 12:04:33Z
  (kopia `config/backup_2026-10-18_line_curves/`, tests/sofa 5 182 passed).
  Instalacja przed przełącznikiem nic nie zmienia: bez linii odczyt identyczny na
  320 733 / 320 733 wierszach 10-09..10-17.
- Przełącznik `epochs.LINE_CURVES_FROM_UTC` = 2026-10-19 00:00Z (następny dzień;
  stała zgoda operatora „instaluj zawsze, sam decyduj”).
- E2E 10-18 (kopia dnia, kod z przełącznikiem wymuszonym, zegar ostatniego
  CONFIDENCE 07:08:38Z): wyłączony = prawdziwe `08_confidence.json` noga w nogę
  (9 146, 0 różnic); włączony 8 903 nogi: +57 / -300, 1 565 wspólnych zmienia
  pewność (średnio -0,09 pp), żadna noga spoza piłki. Odpadają głównie
  `goals_total` UNDER 3,5 (56), `goals_1h_total` UNDER 1,5 (54), `goals_for`
  UNDER 1,5 (26). Single 8 758 → 8 515; single zawodników 52 → 41
  (`player_shots_for` 31 → 19, wszystkie odpadłe na linii 1,5, gdzie krzywa
  wspólna przeszacowuje -1,50 pp [-2,91; -0,06], a per linia -1,04;
  `player_fouls_for` 17 → 17, `player_tackles_for` 4 → 5).
- Poprawka z review (runda 1): pojedyncza noga jednostronna (zawodnik) drukuje
  się tylko na krzywej własnego rynku - `confidence.one_sided_single` czytał
  wyłącznie źródło `market:`, więc źródło `line:` wycinało 47 z 52 singli
  zawodników 10-18. Od poprawki `OWN_CURVE_SOURCES` = `market:` i `line:` (nadal
  n >= 300); test w `tests/sofa/test_line_curves.py`.
- E2E 10-15..10-17 (rozliczone, zegary budowy, piłka): 14 802 → 14 670
  rozliczonych nóg, luka -0,66 → -0,57 pp, ROI -4,05% → -3,97%, jednostki
  -599,0 → -582,9; odpadłe 167 nóg ROI -9,19%, dodane 35 +2,17%. Kierunek
  dobry, skala mała, w granicach szumu.
- Line evidence: od porannego odświeżenia z `--before 2026-10-19` baza offsetów
  to krzywa per linia (`fit_line_evidence.sheet_rows(per_line=)`,
  `fitted_from.per_line_base`). Offsety z poprzednich poranków liczono na bazie A
  - przy pierwszych dniach mogą obniżać podwójnie (ostrożnie). Plik dowodów jest
  jeden: przebudowa dnia sprzed 10-19 po porannym odświeżeniu 10-19 czyta
  offsety liczone na bazie per linia przy bazie wspólnej (dla 33 kluczy).
  Pomiary, które odtwarzają pewność dnia (`measure_price_gap.py`,
  `measure_player_line_evidence.py`, `measure_player_sample_gates.py`), idą za
  regułą dnia (`line_curves.day_reads_per_line`).
- `curve_status` (wyłączony) i `calibration_audit` grupują po dokładnym
  `calibrated_on`: krzywa per linia jest tam osobną krzywą (mniejsze n), więc i
  odrzucana byłaby osobno - spójne, odnotowane.
- Zainstalowana krzywa (`fit_confidence` na całej `sofa_settled_row` kopii)
  zawiera też 447 562 wiersze piłki z życia 09-18..10-16, więc E2E 10-15/10-16
  jest dla niej częściowo w próbie - jak dla każdej dotychczasowej krzywej.
- Obserwacja (nie zmiana): cap pasma ceny działa progowo (gdy wartość > górna
  granica komórki, spada do jej wyniku), więc mała zmiana bazy przeskakuje próg
  w obie strony - 10-18: `goals_1h_for` UNDER 1,5 0,750 → 0,873, `corners_for`
  UNDER 9,5 0,844 → 0,700. Reguła capa bez zmian (zmiana zmienia druk, osobna
  decyzja).
- Zakres: tylko piłka mężczyzn; noga klasy (kobiety, season_early) czyta krzywe
  klasy bez zmian; tenis i sporty mierzone bez zmian. Refit odtwarza sekcję sam
  (`fit_confidence` pisze ją przy każdym pełnym fitcie z listy kluczy).

Sprawdzian na nowych danych: `T-LINE-CURVES`.
