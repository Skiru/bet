# Poprawki rozliczenia i pętli — 2026-10-12

Źródło: audyt dnia 2026-10-11 (rozliczenie D-1 w ramach `/sofa-day` 10-12).
Żadna z poprawek nie zmienia tego, co się drukuje: to poprawki oceny, raportu
i logów, więc weszły od razu (CLAUDE.md, „Changing the pipeline” 2), każda z
testem.

## A. Koszykówka / hokej bez okresów — `DATA_MISMATCH` na zawsze

**Objaw.** Od 2026-10-07 codziennie 10–22 mecze koszykówki kończyły jako
`DATA_MISMATCH` i nie domykały się mimo ponawiania: 10-07 14, 10-08 10,
10-09 22, 10-10 22, 10-11 22. Na kuponie 10-11 wisiały przez to 3 nogi
(Graz–Klosterneuburg zwycięzca, Amyntas–Olympiacos handicap, Cento–Vigevano
zwycięzca).

**Przyczyna.** Przepuszczone offline przez warunki `shadow.build_result`
payloady z `sofa_event_detail` (22 mecze 10-11): 18 ma tylko `current` i
`winnerCode`, bez `period1..4` (NBL Australii, NBL Bułgarii, Serie B, ligi
kobiet Austrii i Grecji, LNBP). `build_result` odrzucał cały mecz, choć rynki
całego meczu potrzebują tylko wyniku końcowego. 4 pozostałe mają naprawdę
sprzeczne dane (np. 16732075: kwarty gości sumują się do 62 przy `current`
65, a „wygrał” gospodarz z 63) — ich odmowa jest słuszna i zostaje.

**Poprawka.** `build_result(..., allow_final_only=True)` (tylko SHADOW_SETTLE):
mecz bez okresów → `GameResult` bez okresów, z `reg_score`. Oceniane są rynki
całego meczu; regulaminowe tylko gdy wynik regulaminowy wiadomo (`normaltime`
albo `current`, gdy nic nie wskazuje dogrywki); kwarty, połowy, tercje —
nigdy. `winnerCode` musi zgadzać się z wynikiem (karne: dopuszczony remis w
`current`). `settled.json` dostaje `score_source: "final_only"`, `t1_reg`,
`t2_reg`; `sport_day.grade_legs` odtwarza z nich ocenę nogi kuponu. Historia
(`sport_confidence`, `measure_score_history`) zostaje przy domyślnym
`False` — żadna krzywa ani dowód linii się nie zmienia.

**Testy.** `tests/sofa/test_shadow_final_only.py` (6), `test_shadow.py::
test_a_game_published_without_periods_settles_from_its_final_score`.

**E2E.** Najpierw kopia 10-11 w scratchpadzie (`SOFA_RUNS_DIR`, prawdziwy
plik nietknięty — md5): dokładnie 18 meczów → SETTLED, 4 zostają
`DATA_MISMATCH`. Ręcznie sprawdzone: Graz 102:94 (zwycięzca T1 WIN, handicap
−8,5 LOSS, total 196), Amyntas +23,5 przy 60:68 WIN, Sydney 78:84 1X2
regulaminowy T2 WIN. Potem prawdziwy sweep `settle_shadow.py --sweep-from
2026-10-07 --sweep-to 2026-10-11` dla koszykówki i hokeja (kopie przed:
scratchpad sesji):

| dzień | DATA_MISMATCH przed → po | nowo SETTLED | w tym final_only |
|---|---|---|---|
| 10-07 | 14 → 0 | 14 | 14 |
| 10-08 | 10 → 0 | 10 | 10 |
| 10-09 | 22 → 0 | 22 | 21 (1 Sofascore poprawił sam) |
| 10-10 | 22 → 3 | 19 | 19 |
| 10-11 | 22 → 4 | 18 | 18 |

Żaden mecz rozliczony wcześniej nie dostał innej oceny; hokej bez zmian.
`record_results.py --from 2026-10-04 --to 2026-10-11`: oczekujące nogi
kuponu 10-07 4→1, 10-09 7→0, 10-10 9→6, 10-11 4→2. Kupon 10-11: koszykówka
−2,79 → −1,78 j. (Graz +0,21, Amyntas +0,80), suma −116,45 → −115,44 j.
`audit_ledger` bez MISMATCH, `audit_shadow` exit 0.

**Do sprawdzenia ręcznie (podejrzenie):** 2 nowo rozliczone mecze LNBP mają
„Gambusinos de Fresnillo” u Superbetu i „Plateros de Fresnillo” u Sofascore
(`audit_settle_identity` NAME_BELOW) — id przypięte przed meczem, poprawka
tego nie dotyczy.

## B. Raport 7c — tabela „Pojedyncze wg sportu i reguły” pokazywała 0 dla sportów

`render_stats_only_split` szukał nóg hokeja / koszykówki / siatkówki / CS2
wśród wierszy arkusza piłki i tenisa — zawsze 0 rozliczonych. Teraz bierze
ocenę `coupon_sports.grade` (tę samą co tabela sportów nad nią).
Test: `test_stats_only_settlement.py::test_7c_split_grades_measured_sport_legs_from_their_own_grades`.
E2E: `audit_settlement.py --date 2026-10-11` — tabela zgadza się z tabelą
sportów (hokej 239/239 −9,27, kosz 20/22 −1,78, siatka 17/17 −3,66, CS2 1/1).

## C. Pętle logowały `SPORT_IDENTITY FAILED` co pół godziny

Pętle pytają o D+1 po każdej migawce, zanim D+1 ma migawkę → exit 2 FAILED.
`run_sport_identity.py --if-snapshot`: brak migawki = `NOTHING_TO_DO`, kod 0,
bez zapisu pliku; `cs2_daily.identity_steps` (też pętla shadow) przekazuje to
tylko dla D+1. Ręczne uruchomienie bez flagi — jak dotąd (2 FAILED). Pętle
uruchomione przed zmianą (10-12) mają stare kroki do końca; łańcuchowe 10-13
już nowe. Testy: `test_sport_identity.py::test_if_snapshot_...`,
`test_chaos_stages.py` (kroki pętli). E2E: `--date 2026-10-15 --if-snapshot`
→ NOTHING_TO_DO, exit 0, katalog nie powstał.

## D. Blok `sports` w `sport_fixtures.json` zerował sporty, o które nie pytano

`identify()` liczy każdy sport, a scalanie nadpisywało poprzednie liczniki
zerami (pętla CS2 zerowała hokej co pół godziny). Teraz podmieniane są tylko
sporty z `--sport`. Czytał to tylko wydruk SOFA_SUMMARY; rekordy `fixtures`
nie były naruszone (sprawdzone na 10-12). Test w
`test_the_script_writes_sport_fixtures_into_the_runs_dir`.

## Bramki

`pytest tests/sofa`, `ruff`, `mypy --strict`, `check_test_registry.py` —
wyniki w commicie.
