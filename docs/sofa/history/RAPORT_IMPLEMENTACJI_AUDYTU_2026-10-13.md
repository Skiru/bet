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
| 2 | A1, A4, B1, B2, B3, B5, B10; B6 jako zarejestrowany test | A1, A4 zrobione; reszta - niżej „otwarte” |
| 3 | B13, potem B15 (z A5) | otwarte |
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

### Ledger

Nowa grupa epoki „od 10-14” w `audit_ledger.EPOCH_GROUPS` (A2 + A4 zmieniają
druk od 2026-10-14 00:00Z). Dzień 2026-10-13 nie jest mieszany: żaden
przełącznik nie działa przed 10-14.

## Bramki

`pytest tests/sofa -q`, `ruff`, `mypy --strict --no-incremental`,
`check_test_registry.py` - wyniki w commicie etapu.

## Otwarte

(uzupełniane po każdym etapie)
