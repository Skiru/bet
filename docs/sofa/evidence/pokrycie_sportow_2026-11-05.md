# Pokrycie statystyk i rynków poza tenisem - 2026-11-05

Przegląd tylko do odczytu. Pytanie operatora (2026-11-05): „w pozostałych sportach -
piłka, hokej, kosz, siatkówka, CS2 - pokrycie statystyk, także zawodników, jest
słabe”. Miara operatora: rynek warto wyceniać, gdy przewidujemy go co najmniej tak
dobrze jak cena Superbetu bez marży (marżę akceptujemy), z uczciwą (skalibrowaną)
pewnością. Tenis jest tu tylko wierszem odniesienia.

Pomiar: `scripts/sofa/measure_coverage_2026_11_05.py` (sekcje `artifacts`, `details`,
`yardstick`, `cache`). Wyniki: `data/refit_2026-11-05_coverage/*.json`. Każda liczba
poniżej pochodzi z tych plików.

## 0. Zakres, źródła i ograniczenia

- **Dni:** 14 zbudowanych dni 2026-10-22 .. 2026-11-04. Wartości „/dzień” to suma
  z 14 dni podzielona przez 14.
- **Linia** to jedna grupa (mecz, rynek, okres, podmiot, linia). Obie strony linii
  dwudrożnej liczą się raz. **Strona** to jeden kierunek.
- **Rekord odmów CONFIDENCE** (`08_refusals*.json`) jest zapisywany przy ostatniej
  przebudowie dnia, często wieczorem. Wiersze `KICKED_OFF` nie przeszły przez
  bramki, więc są liczone osobno: to 40% stron piłki, 32% hokeja, 38% kosza, 61%
  siatkówki i 74% CS2. Wszystkie udziały „dlaczego nie drukuje” są liczone **bez
  KICKED_OFF**. Liczby wydrukowanych nóg pochodzą z `11_coupon.json` i obejmują
  nogi zablokowane z porannego druku.
- Rekord odmów ma strażnika `tests/sofa/test_priced_rows.py`: żaden skrypt w
  `scripts/sofa` nie może go czytać. Tabele odmów (sekcja 3) policzyłem więc
  skryptem tymczasowym poza repozytorium, tą samą logiką. Wynik leży w
  `data/refit_2026-11-05_coverage/refusals.json`. Skrypt w repo go nie czyta.
- **Kopia bazy przez `VACUUM INTO` się nie zmieściła.** `data/sofa.db` ma 56 GB, a
  wolnego miejsca było 27 GB. Wszystkie zapytania szły na żywej bazie w trybie
  `mode=ro`, tylko po kluczach albo po indeksie `run_date` / `sport`.
- **SHADOW / CS2 nie zapisują rynków, których nie czytają.** OFFER zapisuje je w
  `unmapped_prices`, ale tylko dla piłki i tenisa. Dla hokeja, kosza, siatkówki i
  CS2 nie da się więc offline policzyć, ile Superbet oferuje poza naszymi
  rodzinami (luka nr 9).
- Bez sieci. Konfiguracja nie była zmieniana, nic nie zostało zacommitowane.

## 1. Tabela główna (na dzień, 10-22 .. 11-04)

| sport | mecze | linie oferowane drużyn / zawodników | linie z p (rekord) | strony >= 0,70 | wydrukowane strony | bez KO: zmierzone poniżej / nie da się zmierzyć / przeszło | Brier nasze p − cena (×10⁻³), drużyny / zawodnicy |
|---|---|---|---|---|---|---|---|
| piłka | 433 | 36 077 / 41 865 (+45 339 wystąpień niezmapowanych nazw) | 32 763 / 14 814 | 2 924 / 92 | 4 496 / 20 | 26 430 / 538 / 1 795 | **+5,0** [+4,3; +5,8] / nieporównywalne (rynki jednostronne) |
| hokej | 88 | 1 750 / 580 | 1 053 / 480 | 321 / 64 | 305 / 26 | 3 015 / 43 / 230 | **+4,6** [+3,4; +5,9] / **+2,5** [+1,3; +3,8] |
| kosz | 149 | 5 930 / 2 025 | 2 993 / 1 454 | 30 / 0 | 21 / 0 | 8 501 / 1 796 / 18 | **+11,4** [+9,4; +14,1] / +4,4 (po Platcie **+0,9 [−0,3; +2,1]**) |
| siatkówka | 112 | 1 344 / 0 | 357 / 0 | 53 / 0 | 55 / 0 | 778 / 290 / 22 | **+8,8** [+6,1; +11,3] / - |
| CS2 | 55 | 1 030 / 560 | 185 / 110 | 27 / 0 | 47 / 0 | 580 / 48 / 12 | **+3,6** [+0,1; +7,4] / +2,7 (po Platcie **+0,8 [−0,3; +1,7]**) |
| tenis (odn.) | - | (w `market_coverage`) | 8 660 | 450 | 373 | 4 383 / 234 / 143 | **+8,5** [+6,3; +10,6] |

Jak czytać kolumny:
- „Linie z p” w sportach mierzonych to tylko linie ocenione przed startem.
- Brier dodatni oznacza, że cena przewiduje lepiej od nas. Przedziały 95% pochodzą
  z bootstrapu po meczach.
- Piłka i tenis: `sofa_settled_row` z okna, p_central (p z SHEET przed krzywą)
  porównane z `market_p` (cena bez marży, obie strony notowane).
- Sporty mierzone: wszystkie rozliczone linie Superbetu od 09-28 / 09-29 do 11-04.
  Dla drużyn p modelu wyniku pochodzi z `<sport>_superbet_settled.jsonl`, a
  `fair_p` z SHADOW_SETTLE. Dla zawodników i CS2 użyte są `model_p` i `fair_p`
  z rozliczonej linii.
- „Po Platcie” oznacza rekalibrację w tej samej próbie. To górna granica tego, co
  da jakakolwiek krzywa na tych wierszach.

**Wniosek główny (zmierzone):** w żadnym sporcie zagregowanym nie przewidujemy
lepiej od ceny bez marży. Kalibracja tego nie zmienia: Platt w tej samej próbie
przesuwa wynik co najwyżej do remisu. Remis z ceną (przedział obejmuje zero po
Platcie) mają **zawodnicy kosza i zawodnicy CS2** oraz pojedyncze rodziny
wymienione w sekcji 6. Mało drukujemy w koszu, siatkówce i CS2 głównie dlatego,
że **zmierzyliśmy i wychodzi poniżej progu 0,70** (BELOW_FLOOR), a nie z braku
danych. Dane i miara są, tylko p jest poniżej progu.

## 2. Oferta a to, co czytamy

### Piłka (niezmapowane nazwy, `market_coverage.json`, 14 / 14 dni)

To wystąpienia (mecz, nazwa rynku) na dzień, a nie linie. Etykiety:

| etykieta | /dzień |
|---|---|
| COMPUTABLE | 44 702 |
| NOT_COMPUTABLE | 634 |
| UNCLASSIFIED | 3 |
| MAPPABLE | 0 |

| rodzina (COMPUTABLE, chyba że zaznaczono) | /dzień | czego brakuje |
|---|---|---|
| `superbet_combo` (gotowe SuperBety) | 26 286 | łączny rozkład części |
| `fb.result_combo` | 4 714 | model wyniku (łączny rozkład goli) |
| `fb.ht_ft` | 2 009 | model wyniku |
| `fb.result_half` | 1 946 | model wyniku |
| `fb.halves` | 977 | model wyniku |
| `fb.goals_distribution` | 957 | rozkład goals_total |
| `fb.side_result` | 907 | model wyniku |
| `fb.goal_timing` | 816 | incydenty (minuta gola) |
| `fb.result` (dokładny wynik) | 774 | model wyniku |
| `fb.player_goals` | 743 | gole zawodnika z incydentów / lineups |
| `fb.btts_combo` | 730 | model wyniku |
| `fb.goals_for_distribution` | 666 | rozkład goals_for |
| `fb.goal_sequence` | 634 | kolejność goli z incydentów |
| `fb.non_goal_event_timing` (NOT_COMPUTABLE) | 600 | brak źródła |
| `fb.goals_half_for_distribution` | 455 | |
| `fb.goals_halves` / `_for` | 403 / 363 | |
| `fb.corners_distribution` | 399 | |
| `fb.any_player`, `player_goal_detail`, `player_cards`, `woodwork` | 164 / 148 / 118 / 106 | |

Zmapowane linie piłki: 36 077 drużynowych i 41 865 zawodników na dzień. Zawodnicy
to 37 rozgrywek, najwięcej Championship (3 920 linii na dzień okna), Serie A
(3 323) i Brasileirão (2 273).

### Sporty mierzone (linie z ostatniego snapshotu meczu, na dzień)

| sport | największe rodziny |
|---|---|
| hokej | team_total 332, total 254, period_team_total 217, period_total 208, handicap 126, player_pp_points 110, player_shots_on_goal 110, player_points 100, player_assists 100, player_plus_minus 80, player_hits 25, player_blocked_shots 24, player_faceoff_wins 19, player_goalie_saves 12 |
| kosz | total 1 273, handicap 766, team_total 697, h1_* ok. 300 każda, quarter_* 244-292, player_points 190, player_rebounds 172, player_pts_reb 169; 9 rodzin V2 (rzuty wolne, z gry, za 2, faule, straty) po ok. 93 |
| siatkówka | set_winner 312, set_handicap 121, points_total 118, winner 109, sets_total 105, set_points_odd_even 100, set_points_total 97; brak linii zawodników |
| CS2 | map_rounds_handicap 234, map_rounds_total 195, map_team_rounds 168, player_kills / deaths / assists / headshots po 140, map_winner 106, **map_rounds_odd_even 66 (bez wyceny: 0 wierszy w rekordzie)** |

Rynków niezmapowanych w tych sportach nie znamy (sekcja 0).

## 3. Dlaczego wycenione linie nie drukują (strony na dzień, bez KICKED_OFF)

| sport | zmierzone poniżej (floor / x / kurs) | nie da się zmierzyć | gdzie „nie da się zmierzyć” |
|---|---|---|---|
| piłka | drużyny 18 608, zawodnicy 7 822 | 538 | rozproszone: goals_total 48, corners_total 48, result_or_* po 44 (NO_LINE_EVIDENCE 135, CROSS_LEAGUE_UNLINKED 129) |
| hokej | drużyny 2 094, zawodnicy 921 | 43 | NHL zawodnicy: NO_LINE_EVIDENCE 14, NO_MODEL_P 9; Allsvenskan NOT_IDENTIFIED 8 |
| kosz | drużyny 6 076, zawodnicy 2 425 | **1 796** | **NCAA NO_LEAGUE_RATE 723** (total / handicap); **NBA zawodnicy NO_MODEL_P 474 + NO_LINE_EVIDENCE 473**; NBA drużyny NO_LINE_EVIDENCE 29; ACB zawodnicy NO_MODEL_P 17 |
| siatkówka | 778 | 290 | NOT_IDENTIFIED 166 (Argentyna, Urugwaj, NCAA K), TOURNAMENT_NEVER_SETTLED 67 (Puchar Francji 31, LVA, Serbia, Holandia), NO_LEAGUE_RATE Katar 9 |
| CS2 | 580 | 48 | NOT_IDENTIFIED (IEM Beijing 9, CCT NA 7) |
| tenis (odn.) | 4 383 | 234 | |

Uwagi do tabeli:
- Piłka: 15 134 stron zawodników na dzień to `NO_PRICE` po stronie UNDER.
  SHEET wycenia oba kierunki, a Superbet notuje props tylko OVER. To nie jest
  odmowa.
- Rozliczenie traci całe mecze (zdarzenia w 14 dni, `settled.json`):
  - siatkówka: NOT_ON_SOFASCORE 250 i GAVE_UP 207 przy 1 100 SETTLED (Wietnam,
    Argentyna, Portugalia A2, Kazachstan U21);
  - CS2: NOT_ON_SOFASCORE 176 i GAVE_UP 168 przy 397 SETTLED, z czego 309 to
    „Winners series 1x1”;
  - kosz: **DATA_MISMATCH 139, w tym 136 w NCAA**, GAVE_UP 25 przy 1 896 SETTLED;
  - hokej: 7 / 7 / 4 przy 1 206.

## 4. Statystyki w cache (rozgrywki z fixtures okna, zakończone mecze z 365 dni przed 11-04)

| sport | rozgrywek | mecze | wyniki okresów | statystyki drużyn | składy / statystyki zawodników |
|---|---|---|---|---|---|
| piłka | 562 | 123 222 | 0,961 | 0,581 (ważone meczami okna 0,651) | 0,107 / 0,103 |
| - z flagą Sofascore `hasEventPlayerStatistics` | 99 | 25 378 | 0,999 | 0,980 | 0,445 / **0,433** |
| - bez flagi | 461 | 97 844 | 0,952 | **0,477** | 0,019 / 0,018 |
| hokej | 50 | 20 908 | 0,999 | 0,523 | 0,177 / 0,149 (NHL 1,00; Liiga, SHL, czeska Extraliga ~1,00; AHL 0,00; NL A: składy 0,91, statystyki 0,00) |
| kosz | 137 | 31 216 | 0,987 | 0,951 | 0,925 / 0,918 (NBA 1,00, NCAA M 0,93, NCAA K 0,00) |
| siatkówka | 94 | 17 982 | 0,998 | 0,432 | 0,185 / 0,185 |
| CS2 | 31 | 10 355 serii | mapy 0,881 | kompletne staty map 0,871 | zawodnicy na wszystkich mapach 0,590 (ESEA 0,08, United21 0,12, Dust2.dk 0,21) |

Trend:
- Piłka: statystyki drużyn wzrosły z 0,46-0,49 (11.2025-05.2026) do 0,70-0,76
  (08-10.2026).
- Siatkówka: statystyki drużyn spadły z 0,42-0,67 do 0,03-0,26 od 08.2026, a
  zawodnicy z 0,20-0,42 do **0,00** od 08.2026. To zmiana pobierania albo
  Sofascore (podejrzenie). Żaden czytany rynek siatkówki nie używa tych statystyk:
  sety i punkty pochodzą z wyników okresów (0,998).
- Kosz: listopad 0,37, bo nowe mecze nie są jeszcze pobrane.
- CS2: zawodnicy na mapach w zakresie 0,47-0,71 miesięcznie.

Czego potrzebuje rynek, a czego brakuje:
- **Props piłki** są oferowane tylko w 37 rozgrywkach, gdzie cache zawodników ma
  ~1,00. Wyjątki: Liga Europy 0,70, Liga Konferencji 0,57 i Liga Mistrzów 0,79.
  Luki w próbkach pochodzą z wcześniejszych meczów zawodników w ligach bez
  lineups:
  - `NO_STATISTICS` na dzień: LK 490, LE 402, Ekstraklasa 170, Süper Lig 108,
    Pro League 98;
  - w sumie na dzień: `NO_STATISTICS` 1 886, `STAT_KEY_ABSENT` 748,
    `NO_ENTITY_FOUND` 2 668 (1 686 „nigdy nie wystąpił w podstawowym składzie” -
    z założenia; 982 „brak w składzie”).
  - W 99 rozgrywkach z flagą Sofascore brakuje statystyk zawodników dla
    **14 402** zakończonych meczów. Przykłady: Primera Federación 0,16, League
    Two 0,04, League One 0,30, J1 0,00, USL Championship 0,00, Serie C A/B/C
    0,07-0,14.
- **Props hokeja** to tylko NHL, a box NHL to 1,00. Brak statystyk drużyn
  (NCAA 0,13, WHL 0,12) nie dotyka żadnej czytanej rodziny hokeja: wszystkie są
  golowe.
- **Props kosza** to NBA, Euroliga, ACB, EuroCup, GBL i Liga Mistrzów. Box
  wszędzie ~1,00.

## 5. Zawodnicy

| sport | linie oferowane / dzień | z p | odmowy modelu (linie / dzień) | rozliczone | niedopasowani przy rozliczeniu |
|---|---|---|---|---|---|
| piłka | 41 865 | 14 814 linii w rekordzie (35%), 92 strony >= 0,70, 20 wydrukowanych | brak próbki: luki z sekcji 4 | - | - |
| hokej | 580 (model 632 linii) | 625 | THIN_SAMPLE 3,4, NOT_IN_HISTORY 3,3, NAME_UNCERTAIN 0,3 | 1 148 stron / dzień | 12,4 linii / dzień (NHL 174 w 14 dni) |
| kosz | 2 025 (model 2 773) | 2 268 (82%) | **THIN_SAMPLE 392**, **NOT_IN_HISTORY 99**, NAME_UNCERTAIN 14; Grecja GBL / EuroCup TEAM_UNRESOLVED 666 / 350 / 292 w 14 dni | 3 956 stron / dzień | **92 linie / dzień** (NBA 666, Euroliga 134, GBL 130, ACB 112 w 14 dni); DNP 3,1 |
| CS2 | 560 | 110 stron z p na dzień (bez KO) | NO_MODEL_P ~1 | 1 117 stron / dzień | 0; `ungradeable` 3,4 |
| siatkówka | 0 (SHADOW nie czyta żadnego rynku zawodnika) | - | - | - | - |

Dowód liniowy zawodników (`config/sofa_superbet_line_evidence.json`):
- kosz: 38 kluczy, 11 ma kubełek >= 0,70 z n >= 50 i 15 meczami;
- hokej: 18 kluczy, 5 takich (wszystkie UNDER);
- CS2: 8 kluczy, 3 takie.

Dowód jest, więc przy braku druku nogi są zmierzone poniżej progu (kosz 0
drukowanych stron, CS2 0). Hokej drukuje 26 stron zawodników dziennie.

## 6. Miara operatora po rodzinach (Brier p − cena, ×10⁻³, [95%])

Lepsze od ceny albo remis (przedział obejmuje zero lub jest poniżej zera):
- **hokej `player_hits` −11,3 [−19,0; −4,1]** (1 492 linie, 211 meczów; po Platcie
  −11,4). Jedyna rodzina sportu mierzonego wyraźnie lepsza od ceny. To trop:
  mała próba i jedno okno.
- piłka `penalties_total` −4,7 [−7,1; −1,8] (2 236; p tych linii jest daleko od
  0,70);
- remis w piłce: `fouls_*` −3,0 [−10,0; +3,8], `goal_kicks_*`, `red_cards_*`,
  `saves_*`, `shots_*`, `offsides_*`, `penalties_for`, `most_cards_points`;
- remis w hokeju: `period_total` +0,5 [−0,5; +1,4], `player_shots_on_goal`,
  `player_blocked_shots`, `player_faceoff_wins`, `player_goalie_saves`;
- remis w koszu po Platcie: zawodnicy (points −1,1 [−2,4; +0,2], pts_reb −1,6
  [−3,4; 0,0], rebounds, threes, assists, blocks, steals, V2), parzystości;
- remis w siatkówce: `sets_total`, `team_wins_set`, `points_total` (po Platcie),
  parzystości;
- remis w CS2: `map_rounds_total` +0,6 [−1,9; +2,6], `map_winner`,
  `maps_handicap`, `exact_maps`, zawodnicy po Platcie; `team_kills` −4,9 [−8,2;
  −1,4] tylko po Platcie w tej samej próbie.

Wyraźnie gorsze od ceny:
- kosz: winner +21,7, handicap +19,4, total +13,2, team_total +13,9;
- siatkówka: winner +19,4, set_handicap +12,9;
- hokej: winner +13,1, handicap +8,7;
- piłka: draw_no_bet +18,9, most_shots +33,0, most_corners_1h +24,8,
  result_* +7,8.

Remis nie daje druku tam, gdzie p jest blisko 0,5. Tak jest w liniach głównych,
parzystościach i zawodnikach CS2: próg 0,70 wyklucza je niezależnie od jakości.

## 7. Luki do zamknięcia, ranking

Kolumny: wolumen, czego brakuje, czy pomoże backfill, rozmiar i status.

| # | luka | wolumen | czego brakuje | backfill? | rozmiar | status |
|---|---|---|---|---|---|---|
| 1 | Zawodnicy kosza bez p lub bez dowodu (NBA na starcie sezonu) | THIN_SAMPLE 392 + NOT_IN_HISTORY 99 linii / dzień; NO_MODEL_P 474 + NO_LINE_EVIDENCE 473 stron / dzień | model (MIN_APPEARANCES, zawodnik z innej drużyny), krzywa z historii boxów (box 0,92-1,00) | nie (dane są) | średni: krzywa z odtworzenia historii, bez nowych danych | zmierzone; remis z ceną tylko po Platcie, więc druk niepewny |
| 2 | Kosz NCAA `NO_LEAGUE_RATE` | 723 strony / dzień | model: stawka ligi na starcie sezonu (< 30 meczów) | nie (cache NCAA 0,93) | mały, minie z sezonem | zmierzone (wolumen); przyczyna to podejrzenie; drużyny kosza +11,4 gorsze od ceny |
| 3 | Kosz NCAA `DATA_MISMATCH` w rozliczeniu | 136 meczów w 14 dni | rozliczenie (NCAA gra połowy; ćwiartki / box?) | nie | mały, poprawka poprawności | podejrzenie co do przyczyny |
| 4 | Piłka: zawodnicy bez próbki z meczów w ligach bez lineups (LK / LE / Ekstraklasa ...) | NO_STATISTICS 1 886 + STAT_KEY_ABSENT 748 wpisów / dzień; 14 402 mecze w ligach z flagą | dane | **tak:** `backfill_football_lineups.py` dla 99 rozgrywek z flagą (~14,4 tys. zapytań, ok. 20-25 min mostu przy 11,7 req/s) | mały | luka zmierzona; zysk to podejrzenie (props piłki nieporównywalne z ceną, jednostronne; 92 strony >= 0,70 na dzień) |
| 5 | Sporty mierzone nie zapisują niezmapowanych rynków | nieznany | instrumentacja (jak OFFER `unmapped_prices`) | nie | mały, nie zmienia druku | zmierzone (brak zapisu) |
| 6 | Hokej `player_hits`, `player_blocked_shots`, `player_faceoff_wins` | 25 / 24 / 19 linii / dzień | dowód liniowy (NO_LINE_EVIDENCE); hits lepsze od ceny | nie | mały: zbierać dalej, mierzyć ponownie | trop zmierzony (n 1 492) |
| 7 | Siatkówka: identyfikacja i turnieje | NOT_IDENTIFIED 166 + NEVER_SETTLED 67 stron / dzień; 457 meczów w 14 dni nierozliczonych (NOT_ON_SOFASCORE / GAVE_UP) | dane Sofascore (Argentyna, Urugwaj, Wietnam) | nie (brak na Sofascore) | - | zmierzone; drużyny siatkówki +8,8 gorsze od ceny |
| 8 | CS2: zawodnicy w historii (ESEA 0,08, United21 0,12, Dust2.dk 0,21) | 560 linii / dzień ogółem, wszystkie BELOW_FLOOR | dane | **może:** `backfill_cs2.py`, jeśli Sofascore ma mapy z graczami (niesprawdzone) | mały | podejrzenie; zawodnicy CS2 to remis po Platcie, p ~0,5 |
| 9 | Piłka: rodziny modelu wyniku (result_combo, ht_ft, result_half, halves, side_result, dokładny wynik, btts_combo) | ok. 12 tys. wystąpień (mecz, nazwa) / dzień | model łącznego rozkładu goli i mapowanie | nie | duży | zmierzone na istniejących `result_*`: +7,8 [+6,4; +9,5] gorsze od ceny, więc niski priorytet |
| 10 | CS2 „Winners series 1x1” i `map_rounds_odd_even` | 309 meczów nierozliczonych w 14 dni; 66 linii / dzień | brak na Sofascore / brak wyceny | nie | - | zmierzone; nie warto (parzystość ~0,5) |

## 8. Czego nie sprawdzono

- Udziały odmów bez KICKED_OFF pomijają 32-74% stron, ocenianych dopiero
  wieczorem. Rekord z porannej budowy nie jest zachowywany.
- Brier porównuje **surowe** p modelu (przed krzywą i dowodem liniowym) z ceną.
  Platt w tej samej próbie to granica optymistyczna dla modelu, nie pomiar poza
  próbą.
- Props piłki (jednostronne, 1/kurs z marżą) nie dają się uczciwie porównać z ceną
  bez marży. Wiersz `player_* one_sided` (−22,8) to artefakt marży, nie przewaga.
- Nie sprawdziłem, czy Sofascore ma lineups dla 14 402 meczów z flagą (sieć), ani
  czy ma graczy CS2 dla ESEA / United21.
- Wyniki piłki i tenisa dotyczą okna 10-22 .. 11-04; sportów mierzonych - wszystkich
  dni od 09-28 / 09-29. Epoki nie były rozdzielane.
