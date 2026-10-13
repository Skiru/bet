# Raport implementacji audytu 2026-10-13

Wejście: `docs/sofa/history/AUDYT_RYNKOW_KONTEKST_2026-10-13.md` (commit
5e0c6928), decyzje operatora O1–O9. Kolejność według „Kolejność proponowana”.
Każda pozycja: diagnoza sprawdzona w kodzie, test zarejestrowany w
`docs/sofa/evidence/` przed pomiarem, kod za przełącznikiem w `bet.sofa.epochs`,
test w `tests/sofa/test_audit_2026_10_13.py`, pomiar skryptem `measure_*`,
decyzja według O5 (albo decyzji operatora, gdy ją wydał).

## Plan etapów

| etap | pozycje | stan |
|---|---|---|
| 1 | A2, C21 | zrobione (ten raport) |
| 2 | A1, A4, B1, B2, B3, B5, B10; B6 jako zarejestrowany test | A1, A4, B10 zrobione; B1, B2, B3, B5, B6 - agenci |
| 3 | B13, potem B15 (z A5) | B13 zrobione; B15 - agent |
| 4 | refit piłki i tenisa: A6 + B14 + C1 (+ wyniki 2-3), potem D1; D2 osobno | otwarte |
| 5 | koszykówka: A3 + C8, pomiar A8, jeden refit | otwarte |
| 6 | B7, A7, B9, C9/C10, B11-B12, B8, B4 | otwarte |

## Etap 1

### C21 - siatkówka: set nierozegrany

- Diagnoza: potwierdzona. `shadow.actual_value` zwraca `None` dla seta poza
  rozegranymi (`shadow._pair`, `period > len(t1)`), więc noga kuponu była
  `UNGRADEABLE` (`sport_day._grade_leg`), a SHADOW_SETTLE liczyło ją jako
  „ungradeable”. Mapa CS2 w tej samej sytuacji była już `VOID` (`cs2.map_not_played`).
- Regulamin: Regulamin Zakładów Wzajemnych przez sieć Internet zatwierdzony
  10.02.2026 (DRG2.6841.1.2026), 5.E.1.h („Zdarzenie nie zostało zakończone
  oficjalnym wynikiem”) i 5.E.1.i („w Zdarzeniu nie zostaną spełnione warunki
  określone przez Spółkę w przedmiocie zakładu”) - anulowanie, czyli zwrot.
- Zrobione: `shadow.set_not_played`; SHADOW_SETTLE liczy taką linię jako
  `void`, `sport_day._grade_leg` zwraca `VOID`. Poprawka rozliczenia - od razu,
  bez przełącznika (CLAUDE.md „Changing the pipeline” 2).
- Skutek wstecz: żadna wydrukowana noga siatkówki nie dotyczyła seta 4/5
  (kupony 2026-10-05..10-13: 42 nogi siatkówki, wszystkie całego meczu), więc
  ledger się nie zmienia.
- Testy: `test_a_volleyball_set_never_played_is_a_refund`,
  `test_set_not_played_only_for_volleyball_sets`.

### A2 - rozgrywki bez własnej stawki, sparingi (O1)

- Diagnoza: potwierdzona. `RatingBook.league_rates` przy n < 30 brał
  `global_league` (`football_rating.py`, dawniej :770-779); SPORT_CONFIDENCE nie
  miał bramki sparingu. W `sport_fixtures.json` 2026-10: 40 zidentyfikowanych
  meczów „NBA Preseason”, 7 „CBA Preseason”, 7 „Club Friendlies”.
- Zrobione:
  - `league_rates(..., strict)` / `expected(..., strict)` - tylko prognoza;
    uczenie ratingu bez zmian (test);
  - score model: `ScoreModel.strict_league_rate`, `no_league_rate`;
    SPORT_CONFIDENCE: odmowy `FRIENDLY_FIXTURE` (`comparability.is_friendly_event`
    na wpisie `sport_fixtures.json`) i `NO_LEAGUE_RATE`; replay line evidence
    (`settled_shadow_rows`) stosuje regułę dnia;
  - piłka: `FootballForecast.strict_league_rate` / `no_league_rate`, notatka
    `NO_LEAGUE_RATE` w SHEET - za osobnym przełącznikiem.
- Pomiar (`docs/sofa/evidence/league_rate_rule_2026-10-13.md`,
  `scripts/sofa/measure_league_rate_rule.py`):
  - sporty, rozliczone linie Superbetu 09-29..10-12: mecze odrzucane -
    koszykówka 39 (27 przedsezonów / sparingów), siatkówka 19, hokej 0; nóg
    „do druku” w nich 17 w 16 meczach: koszykówka realizacja - pewność
    -3,1 pp [-38,4; +22,8] (8 nóg), siatkówka +11,3 pp [-12,8; +23,6] (9) -
    **nie rozstrzyga**;
  - piłka, historia 2025-08-01..2026-10-12, one step ahead w rozgrywkach z
    n < 30: stara reguła lepsza, SE na stronę **-0,581 [-0,621; -0,543]**
    (65 550 stron), każda metryka tego samego znaku.
- Przełączniki:
  - `LEAGUE_RATE_RULE_FROM_UTC` = **2026-10-14 00:00Z** (sporty) - **na podstawie
    decyzji operatora O1 i jako korekta poprawności, nie O5** (pomiar O5 nie
    rozstrzyga przy 17 nogach). To jedyny włączony przełącznik tej sesji bez
    pomiaru spełniającego próg O5 - wskazany wprost dla weryfikacji.
  - `FOOTBALL_LEAGUE_RATE_RULE_FROM_UTC` = **None** (zmierzone, gorsze).
- Rejestr: `T-A2-league-rate-refusals` (od 2026-10-14).
- Testy: `test_a_thin_competition_has_no_rate_only_under_the_rule`,
  `test_the_rule_never_changes_what_the_rating_learns`,
  `test_the_score_model_withholds_a_thin_competition`,
  `test_a_preseason_game_is_refused_like_a_football_friendly`,
  `test_a_game_without_a_league_rate_is_refused`,
  `test_the_league_rate_rule_reads_the_day_and_the_clock`.

## Etap 2 (część)

### A4 - efekt projektu per kubełek

- Diagnoza: potwierdzona. `LineEvidence.read` (v2) dzielił linie kubełka klucza
  bez krzywej przez `design_effect` sportu (piłka 2,437 w pliku 10-13).
- Zrobione: fit zapisuje `deff` kubełka (`_cells`), `LineEvidence(bucket_deff)`
  / `deff_for`; plik bez `deff` czyta efekt sportu. Wpięte w CONFIDENCE,
  SPORT_CONFIDENCE i `audit_variants` (U3 czyta tę samą regułę).
- Pomiar (`docs/sofa/evidence/bucket_design_effect_2026-10-13.md`,
  walk-forward 10-07..10-12, wszystkie sporty, klucze bez krzywej): log-loss
  pewności nowa - stara **-0,0351 [-0,0409; -0,0292]** (1 898 linii / 682
  mecze); piłka -0,0398 [-0,0474; -0,0321], tenis -0,0230 [-0,0323; -0,0132],
  CS2 -0,0513 [-0,0786; -0,0264]; hokej 14 linii (nierozstrzygnięte).
  Nogi do druku: 200 -> 675; dodane 477 nóg / 321 mecze, realizacja - pewność
  +4,5 pp [+1,6; +7,3], ROI -2,4% [-5,9; +0,7]. **Zastrzeżenie: dodane nogi
  tenisa ROI -10,0% [-19,7; -0,8] (87 nóg / 79 meczów)** - pod obserwacją.
- Przełącznik: `BUCKET_DESIGN_EFFECT_FROM_UTC` = **2026-10-14 00:00Z** (O5).
  Pierwszy plik z `deff` zapisze poranny `refresh_line_evidence.py` 10-14;
  do tego czasu odczyt jest jak dotąd.
- Rejestr: `T-A4-bucket-deff`.
- Testy: `test_a_bucket_of_one_line_a_game_is_not_shrunk_by_the_sports_design_effect`,
  `test_the_bucket_design_effect_switch_reads_day_and_clock`,
  `test_line_evidence.py::test_fit_buckets_and_the_printable_gap` (pole `deff`).

### A1 - siła jednostki regionalnej

- Diagnoza: potwierdzona w kodzie - nowa jednostka (`assign_league_units`)
  dostaje `_Strength()` z sigma 0 przy pierwszej aktualizacji residuum.
  (Liczb J1 0,168 / 0,108 / 0,419 nie przeliczałem.)
- Zrobione: `RatingBook.unit_strength_from_parent`, `_strength_entry` (start z
  sigma rodzica `unit_comp`), `replay(..., unit_strength_from_parent)`, SHEET.
  Bez fallbacku dla cienkiej jednostki (bloker V1-1).
- Pomiar (`docs/sofa/evidence/unit_strength_2026-10-13.md`): gole, one step
  ahead 06-01..10-12, mecze ponadligowe z jednostką regionalną: log-loss
  Poissona -0,0010 [-0,0029; +0,0008] na mecz (7 724 mecze); wszystkie mecze
  ponadligowe -0,0003 [-0,0008; +0,0003]; wszystkie -0,00006 [-0,0002; +0,0001].
- Przełącznik: `UNIT_STRENGTH_FROM_PARENT_FROM_UTC` = **None** (zmierzone, nie włączone).

### B10 - CS2 `map_team_rounds` z wyścigu rund

- Diagnoza: potwierdzona (`cs2_engine.model_probability`: `shrunk_frequency`
  własnych rund drużyny, bez rywala).
- Zrobione: `cs2_engine.team_rounds_from_race` (rozkład wyniku mapy
  `map_distribution_for(p_map)`), `model_probability(team_rounds_race)`;
  przełącznik działa w SPORT_CONFIDENCE, w `settle_cs2` (p przy rozliczeniu ->
  line evidence) i w replayu historii (`cs2_walk_forward_rows`,
  `fit_sport_confidence --cs2-team-rounds-race`). `LINE_OUTSIDE_FIT` bez zmian.
- Pomiar (`docs/sofa/evidence/cs2_team_rounds_race_2026-10-13.md`): historia
  2025-10-13..2026-10-13, 316 024 linii / 8 738 serii, log-loss wyścig -
  częstość **-0,0213 [-0,0237; -0,0188]**, każda linia i strona < 0;
  kalibracja p >= 0,70: wyścig 0,756 / 0,758, stary 0,734 / 0,698.
- Refit (O6) na kopii bazy `data/refit_2026-10-13/sofa_replay.db`: compare na
  holdoucie - log-loss pewności OVER 0,6479 vs 0,6622, UNDER 0,6644 vs 0,6658;
  linie Superbetu 10-05..10-12 (kontrola): -0,029 [-0,060; +0,005].
  Backup `config/backup_2026-10-13_audit/` (lokalny, poza gitem), `.next`
  przeniesiony na plik zainstalowany, nowy `.next` z sekcją CS2,
  `effective_from` 2026-10-14.
- Przełącznik: `CS2_TEAM_ROUNDS_RACE_FROM_UTC` = **2026-10-14 00:00Z** (O5/O6).
- Testy: `test_team_rounds_from_the_race_follow_the_map_winner`,
  `test_model_probability_reads_the_race_only_under_the_switch`,
  `test_the_cs2_race_switch_reads_day_and_clock`.

### B1 - rola faworyt / outsider (stan meczu)

- Diagnoza: potwierdzona. `run_sheet.py` (blok `FOOTBALL_RATING`, ok.
  :1197-1223) miesza rating Maher i próbkę bez terminu „różnica sił -> styl”;
  `FootballForecast.centre` (`football_rating.py`) go nie ma.
- Zrobione: `bet.sofa.game_state` (tabela beta, `fit_beta`),
  `FootballForecast.supremacy`, `bet.sofa.centre_replay` (wspólna
  rekonstrukcja centrum one step ahead), SHEET za przełącznikiem
  (notatka `GAME_STATE`, `MAX_SUPREMACY` w `UNFITTED_CONSTANTS`),
  `scripts/sofa/fit_game_state.py` -> `config/sofa_game_state.json`.
- Pomiar (`docs/sofa/evidence/game_state_2026-10-13.md`,
  `scripts/sofa/measure_game_state.py`, walk-forward miesięczny,
  2025-08-01..2026-10-12): log-loss NB na stronę `corners_for` -0,01490
  [-0,01600; -0,01383] (123 130 stron / 61 565 meczów), `shots_for` -0,01504
  [-0,01638; -0,01374], `cards_points_for` -0,00425 [-0,00479; -0,00372],
  `fouls_for` -0,00020 [-0,00037; -0,00003]. Próg spełniony dla czterech.
- Przełącznik: `GAME_STATE_FROM_UTC` = **None** do refitu piłki (etap 4):
  próg O5 spełniony, ale zmiana centrum bez krzywych dopasowanych na tym
  estymatorze czytałaby krzywe innego estymatora (replay nie ma ratingu, A6);
  „Kolejność” pkt 4 wnosi wyniki etapu 2 do refitu. Beta kartek trzeba
  przeliczyć, jeśli razem z B2 (`cards_points_for` w ratingu).

### B2 - rynki `UNRATED_MARKETS`

- Diagnoza: potwierdzona. `football_rating.UNRATED_MARKETS` (wybór z 5 dni
  w próbie); `venue` nieczytane w SHEET.
- Zrobione: `FootballForecast.rated_scope` + `RATED_SCOPE_MARKETS`,
  `FootballForecast.venue_multiplier` + `VENUE_PRIOR_MARKETS`, SHEET za
  dwoma przełącznikami.
- Pomiar (`docs/sofa/evidence/unrated_markets_2026-10-13.md`,
  `scripts/sofa/measure_unrated_markets.py`): rating lepszy dla
  `cards_points_for` -0,00503 [-0,00547; -0,00459], `corners_1h_for`
  -0,01632, `corners_2h_for` -0,01099, `offsides_total` -0,00503 (każdy
  także w podoknach poza wyborem stałych); `corners_total` gorzej +0,00092
  [+0,00034; +0,00153], połowy sum bez różnicy. Gospodarz lepszy dla
  `corners_1h_for` -0,00639 [-0,00804; -0,00466] i `corners_2h_for` -0,00308
  [-0,00463; -0,00157]; `cards_points_for` -0,00119, ale podokno post ma znak +.
- Przełączniki: `FOOTBALL_RATED_SCOPE_FROM_UTC`, `FOOTBALL_VENUE_PRIOR_FROM_UTC`
  = **None** do refitu piłki (etap 4), jak B1. `corners_total` i połowy sum:
  zmierzone, nie włączone (zostają w `UNRATED_MARKETS`).
- Testy B1/B2: `tests/sofa/test_audit_2026_10_13_b1b2.py`.

## Etap 3 (część)

### B13 - rywal w `Observation`

- Zrobione: `Observation.opponent_id`, `Observation.against` (wartość rywala
  tej samej metryki „_for” w tym samym meczu), domyślnie None - stare
  `03_samples.json` się parsują. Wypełniane w `samples.process_historical_event`
  i w ścieżce listingowej goli. Siła rywala as-of nie jest zapisywana w
  próbce: liczy ją SHEET z `RatingBook` (B15) po `opponent_id` i dacie.
- Wpływ na druk: brak (nikt jeszcze nie czyta pól).
- Test: `test_an_observation_carries_its_opponent_and_old_samples_still_parse`.

### B5 - tenis: gemy w setach i `sets_total` z sąsiadów ratingu (agent, scalone)

- Diagnoza: potwierdzona (`engine.py:42` częstość własna skurczona do priora
  globalnego; `tennis_rating.RATING_PRICED_MARKETS` bez tych rynków).
- Zrobione: `tennis_rating.SET_RATING_PRICED_MARKETS`, `Outcome.set3`,
  `read` dla `games_won_set3_for`; SHEET za `TENNIS_SET_RATING_PRICES_FROM_UTC`.
- Pomiar (`docs/sofa/evidence/tennis_set_markets_2026-10-13.md`), walk-forward
  w dwóch oknach, log-loss na liniach Superbetu z arkuszy 10-09..10-12
  (x1e-4): `games_set1_total` -186,5 [-198,3; -174,1] (53 850 meczów),
  `games_set2_total` -171,9, `games_won_set1_for` -651,7 [-670,0; -632,7],
  `games_won_set2_for` -679,8, `games_won_set3_for` -875,3 (3 678),
  `sets_total` -216,4. Próg spełniony na wszystkich sześciu (też w każdym
  oknie osobno).
- Bramki kształtu (A5): pod nowym p `LINE_BEYOND_SAMPLE` + `MODE_LOSES`
  zdjęłyby 15-28% wierszy >= 0,70 rynków gemów w secie, które realizowały na
  poziomie swojego p - na historii bramki wyrzucają tu dobre wiersze;
  `sets_total` 2,9% (-4,7 pp). Decyzja o bramkach - z refitem.
- Przełącznik: **None** do refitu tenisa (etap 4): replay
  (`calibrate_from_cache`) nie generuje dziś wierszy tych rynków.

### B6 - tenis: siła serwisu jako druga oś sąsiadów (zarejestrowany test)

- Nowe względem odrzuconego 10-08: rozkład zostaje empiryczny z sąsiadów,
  zmienia się tylko wybór sąsiadów (p/σ, D/σ), nie model zastępczy.
- Wynik: `games_won_for` gorzej +8,1e-4 [+1,5; +14,3], `handicap_games`
  gorzej +17,7e-4; lepsze tylko `tiebreaks_total` -32,6e-4 i
  `games_set2_total` -10,8e-4 - **próg niespełniony na rynkach docelowych**,
  bez przełącznika (`docs/sofa/evidence/tennis_serve_neighbours_2026-10-13.md`).
  `tiebreaks_total` - kandydat na nowy test na nowych danych.

## Etap 5 - koszykówka

### A3 + C8 - dogrywka (długość z ligi, „overtime spike”)

- Diagnoza: potwierdzona (`score_model._basketball`: `q_len = 10.0 if
  len(mu1) == 4`, koszykówka ma zawsze 4 kwarty).
- Zrobione: `TWELVE_MINUTE_QUARTERS` (NBA 132, NBA Preseason 2329, PBA 1656 /
  1712 / 1956; `defaultPeriodLength` w bazie tylko dla NBA Preseason i PBA),
  `SimParams.bb_tie_pull` / `bb_tie_window` (3, wybrane), `BB_TIE_PULL`
  0,0299 dopasowane momentem 2025-10-01..2026-02-01; przełącznik
  `BB_OVERTIME_FROM_UTC` na żywo, w replayu line evidence i w
  `fit_sport_confidence` (`--bb-overtime`, `--league-rate-rule`).
- Pomiar (`docs/sofa/evidence/basketball_overtime_2026-10-13.md`), 3 081
  meczów 2026-02..05: log-loss 1X2 po regulaminie **-0,0035 [-0,0072;
  -0,0001]**, Brier sumy z dogrywką +0,00001 [-0,0007; +0,0007]. Próg spełniony.

### A8 - szum symulacji (trzy kandydaty)

- `a8_one_step` / `a8_no_fresh` / `a8_level_power`: Brier zwycięzcy i sumy -
  każdy przedział obejmuje zero (`docs/sofa/evidence/basketball_noise_2026-10-13.md`).
  **Zmierzone, nie wdrożone**; `SimParams.bb_resid_one_step` zostaje jako
  wyłączona opcja.

### Ledger

Nowa grupa epoki „od 10-14” w `audit_ledger.EPOCH_GROUPS` (A2 + A4 zmieniają
druk od 2026-10-14 00:00Z). Dzień 2026-10-13 nie jest mieszany: żaden
przełącznik nie działa przed 10-14.

## Bramki

`pytest tests/sofa -q`, `ruff`, `mypy --strict --no-incremental`,
`check_test_registry.py` - wyniki w commicie etapu.

## Otwarte

(uzupełniane po każdym etapie)
