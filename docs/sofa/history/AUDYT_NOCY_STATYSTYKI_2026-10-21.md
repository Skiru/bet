# Audyt nocy 2026-10-20/21 - siedem przełączników piłkarskich (HEAD 917634a6)

Audytor adwersaryjny. Nic w `runs/sofa/<d>/` ani w `data/sofa.db` MAIN nie zostało
zapisane: md5 wszystkich `*.json/*.pdf/*.html` dni 10-19..10-21 przed i po - identyczne
poza `sport_fixtures.json` 10-20 / 10-21 (mtime 00:35, zapis pętli SHADOW/CS2 -
SPORT_IDENTITY, nie audytu). Baza czytana wyłącznie `mode=ro` (SAMPLES: `get_connection`
podmienione na połączenie ro, każdy `save_*` wyłączony).

## 1. Defekty

| # | waga | gdzie | co | poprawka |
|---|---|---|---|---|
| D1 | ŚREDNIA (błędna ocena) | `src/bet/sofa/football_incidents.py:179` | `in_1h = ... float(i["time"]) <= 45` liczy czerwoną kartkę z `time` = -5 (Sofascore: poza grą - przerwa / po gwizdku) jako 1. połowę. `red_cards_1h_total` / `red_cards_1h_for` źle ocenione (event 17255664: 2 zamiast 1; 16774721: 1 zamiast 0); ok. 254 takich czerwonych w 20 000 meczów cache; te same rekordy budują stawki as-of rynków połówkowych (lekki bias w górę). Kod nowy (card halves, 3e1ad3dd), na żywo od 10-21. | `0 <= float(i["time"]) <= 45` + test (czerwona -5: `red_cards_1h` 0, `red_cards` 1). Łatka: `scratchpad/audit/g/fix_red_1h.patch` |
| D2 | NISKA (bramka) | `src/bet/sofa/epochs.py:2361` | ruff E501 (89 > 88) - `ruff check src/bet/sofa scripts/sofa` pada na HEAD (26e7a5ba). | zawinąć linię; łatka `scratchpad/audit/fix_gates_regrade.patch` |
| D3 | NISKA | `scripts/sofa/regrade_settled.py:515` | `_settle_player(...)` bez `coverage=` - regrade nie zna zera celnych przez słupek ani dwóch reguł nazw; wiersz SETTLE wraca jako `left:STAT_KEY_ABSENT` (szum raportu, wiersza nie usuwa). | `coverage=football_player_coverage(day)`; ta sama łatka |
| D4 | ŚREDNIA (refit) | `scripts/sofa/prepare_refit.py:105-113, 584-586, ~2278` | brak `--player-coverage` (calibrate go ma: `calibrate_from_cache.py:2702/3079`) i brak klucza w `REPLAY_FLAG_KEYS`; następny refit nie odtworzy pokrycia, które już jest na żywo. | dodać parametr, przekazać do calibrate, klucz w `REPLAY_FLAG_KEYS`, argument CLI obok `--closeness-stretch` |
| D5 | ŚREDNIA (refit) | `prepare_refit.py:1939` (`dropped_replay_rules`) | zainstalowane krzywe (10-17) nie mają `closeness_stretch` w `replay_rules`; strażnik sprawdza tylko `requires_replay_flags` krzywych osobnych - refit bez `--closeness-stretch` przejdzie po cichu. | odmowa, gdy włączony dziś przełącznik (`football_closeness_stretch`, `football_player_coverage`) nie ma flagi; dopisać flagi w CLAUDE.md |
| D6 | NISKA (refit) | `config/sofa_confidence_calibration.json` `new_market_curves_fitted_from['player_fouls_drawn_for|OVER']` | brak `requires_replay_flags`; gdy linie fauli na zawodniku zaczną się drukować, `printed_player_ladder` wpuści je do `build_player_rows` i refit nadpisze krzywą zainstalowaną po bramce jednostronnej - bez tej bramki. | strażnik na wpisie albo wykluczenie rynku z wierszy zawodnika refitu |
| D7 | NISKA | `src/bet/sofa/rebuild_plan.py:357` | SHEET powtarzany tylko gdy brak znacznika `referee_read`; sędzia ogłoszony po porannym SHEET (RESOLVE ma sędziego dla 14/37 meczów z kartkami/faulami 10-20) zostaje poza wierszami (`NO_REFEREE`). | w `audit_sheet_stale`: wiersz kartek/fauli `NO_REFEREE`, a `referees.referee_for_event` teraz zwraca sędziego = arkusz nieaktualny |
| D8 | NISKA, sprzed nocy | `.claude/skills/sofa-pipeline/references/model-state.md:530` (c7f3575c) | odwołuje się do nieśledzonego `scripts/sofa/measure_cs2_map_total_race.py`; na czystym checkoucie `test_documented_commands` pada. | zacommitować skrypt (sesja CS2) |

Scalenia ręczne (run_sheet, offer, epochs, contracts, rebuild_plan, sheet_config,
superbet_names, off_scenarios, run_samples, run_settle, settle): każda dodana linia 12
commitów nocy jest w HEAD, brak zdublowanych kluczy / funkcji; `config_sha` obejmuje
`sofa_referee_effect.json`, `sofa_player_share.json`, `sofa_closeness_stretch.json`
(`sheet_config.py:51-55`). **Błędu scalenia nie znaleziono.**

## 2. E2E łączne (wszystkie 7 włączone vs wyłączone, HEAD)

Metoda: worktree HEAD, siedem `*_FROM_UTC` = 2026-10-19 przy `AUDIT_ON=1`, `None` przy 0;
kopia dnia w scratchpadzie (`audit/off`, `audit/on`, bez `printed/` i `12_printed.json`).
OFFER: zapis `unmapped_prices/` (ostatni przebieg na mecz) przez prawdziwy `OfferFetcher`
z `day_flags(date)`, nowe szczeble dołożone do zapisanego `04_offer.json`. SAMPLES offline
(`process_fixture_samples`, klient bez sieci) dla wszystkich meczów piłkarskich, obie gałęzie.
Dalej prawdziwe skrypty: `run_sheet.py`, `run_confidence.py` (`SOFA_NOW` = najnowsza cena + 5 min),
`build_coupon.py`, `build_coupon_pdf.py`. Wszystkie rc 0, zero wyjątków w logach.

| | 10-19 | 10-20 |
|---|---|---|
| OFFER: nowe szczeble wył. / wł. | 0 / 1 997 | 0 / 1 944 (22 rynki; fauli na zawodniku 1 391) |
| SAMPLES wył. vs prawdziwe 03 (metryki drużyn / zawodnicy równe) | 1 158 / 4 786 (dryf cache: +26/-7 metryk, +161/-26 zaw.) | 1 486 / 4 691 (+6 metryk, +15/-13 zaw.) |
| SAMPLES wł.: zawodnicy zmienieni / dodani | 801 / 594 | 783 / 385 |
| SHEET wiersze wył. -> wł. | 34 692 -> 39 420 | 50 272 -> 54 955 |
| SHEET wiersze utracone | 132 (tylko zawodnicy: strzały 72, celne 32, faule 28) | 286 (zaw. 258, `cards_points_total` 20, `both_over_cards_points` 8 - p poza [0,05; 0,95]) |
| SHEET zmienione (główne) | strzały zaw. 1 518, faule zaw. 820, celne zaw. 732, `shots_total` 256, kartki suma 214 / strona 202 | 1 792 / 954 / 854, kartki 246 / 214, `shots_total` 162 |
| SHEET nie-piłka zmienione | 0 | 0 |
| CONFIDENCE nogi wył. -> wł. | 1 736 -> 1 764 (+41 / -13; 40 zmienionych, 11 z inną pewnością) | 2 516 -> 2 540 (+44 / -20; 26 zmienionych, 9 z inną pewnością) |
| nowe nogi wg rynku | red_cards_for 12, penalties_for 6, cards_points_total 5, cards_points_for 4, player_shots_for 3, shots_total 3, penalties_1h_total 3, cards_points_1h_total 3, cards_points_2h_total 2 | penalties_for 10, cards_points_1h_total 9, penalties_1h_total 9, cards_points_total 5, cards_points_2h_total 3, penalties_1h_for 3, player_fouls_drawn_for 2, cards_points_for 2, red_cards_for 1 |
| utracone nogi | cards 6, player_shots 5, player_fouls 1, shots_total 1 | player_shots 8, cards 7, player_fouls 4, shots_total 1 |
| removed_by_reads | 56 -> 54 | 140 -> 146 (+7 auto `MODEL_ABOVE_OWN_SAMPLE`, kartki) |
| buildery (wył. -> wł.; tylko wył. / tylko wł.) | 36 -> 34 (4 / 2) | 39 -> 41 (3 / 5); żaden nowy rynek w builderze |
| PDF / HTML | rc 0 | rc 0 (pozycje 2 868 -> 2 892) |

- `superbet_market` / `superbet_selection`: wszystkie nowe nogi w `11_coupon.json`
  (41 i 44) je mają (np. "1.połowa - Manchester City - liczba przyznanych rzutów karnych:
  poniżej 0.5", "Zawodnik - liczba fauli na zawodniku: Sergino Dest - powyżej 0.5").
- Znaczniki: wł. `referee_rule` / `player_share_rule` / `closeness_rule` na 35 008/35 008
  (10-20) i 29 860/29 860 (10-19) wierszach piłki, 0 tenisa; wył. 0. `player_props_v2_rule`
  tylko na wierszach fauli na zawodniku (1 252 / 1 312). `referee_read` na 620 / 502
  wierszach kartek/fauli (APPLIED 490 / 472, NO_REFEREE 130 / 30). `config_sha`
  e3bfb520c986fb3d w obu gałęziach (pliki są w odcisku także przy wył.). COVERAGE,
  STAT_VARIANTS, CARD_HALVES nie mają znacznika wiersza (tak zaprojektowane).
- Gradowalność (10-19, nowe wiersze nie-zawodnicze ścieżką `run_settle`, cache ro): wszystkie
  rynki ocenione (both_over_* 8, cards_points_1h/2h_* 192, handicap/most_cards_1h/2h 38,
  penalties_* 34, red_cards_* 112) poza 2 `cards_points_1h_total` STAT_KEY_ABSENT (kartka -5
  = połowa nieznana, odmowa zgodnie z regułą). 10-20 jeszcze bez statystyk w cache.

## 3. Interakcje

- **Kartki (strona / suma)**: rating x GAME_STATE x sędzia ratio^0,592 x bliskość
  exp(0,0177|s| - 0,0492 s^2) (`run_sheet.py:2700-2735`). Rozciągnięcie liczników nie ma
  kartek - brak podwójnego liczenia. Bliskość dopasowana z GAME_STATE + rozciągnięciem w
  offsecie (zmierzone razem). **Sędzia i bliskość nigdy razem nie mierzone** (sędzia: centrum x
  GAME_STATE; bliskość bez sędziego). Wielkości: bliskość 0,969 / 0,851 / 0,677 przy |s| 1 / 2 / 3
  (s ucięte na 3,0 - `game_state.MAX_SUPREMACY`; empirycznie kubeł 2,5-3: 0,716); sędzia
  0,84-1,17. Przykład 10-20 (event 16938875, |s| 3,4): kartki pow. 2,5 p 0,736 -> 0,481
  (4,16 x 0,948 x 0,677).
- **`MODEL_ABOVE_OWN_SAMPLE` x sędzia/bliskość**: 10-20 7 nóg kartek przechodzi do
  `removed_by_reads` automatycznie (model - trafienia własnej próbki > 0,15), bo sędzia
  podnosi model ponad próbkę, której sędzia nie zna. Bramka mierzona przed sędzią -
  odcina część zysku sędziego; do zmierzenia (nie defekt).
- **Połówki kartek** (`run_sheet.py:1812`): z surowego centrum ratingu x udział połowy -
  bez GAME_STATE, sędziego i bliskości; brak podwójnego liczenia, zgodne z ich pomiarem;
  niespójne z pełnym meczem tego samego spotkania (połówki tracą zysk sędziego).
- **Karne / czerwone strony**: tylko stawka rozgrywek as-of, bez członu drużyny - 10-20 każda
  drużyna LM `penalties_for` pon. 0,5 = 0,8358, `penalties_1h_for` = 0,8992,
  `penalties_1h_total` = 0,8522 (22 z 44 nowych nóg); statystyka nie odróżnia tu dobrego
  1,20 od złego (wymóg operatora). Precedens: `penalties_total` / `red_cards_total` od 10-14
  też ligowe.
- **Udział zawodnika x rozciągnięcie zawodnika**: przy udziale rozciągnięcie pominięte
  (`not shared`, `run_sheet.py:2772`) - poprawnie, T = `shots_for` strony z GAME_STATE.
  Fallback (brak `shots_for` strony ~12% lub < 3 startów) = stare centrum x rozciągnięcie.
  Bazą pomiaru udziału było własne centrum z rozciągnięciem - zmierzone w tej kombinacji.
- **Udział x sędzia** (faule zawodnika = udział x `fouls_for` strony, która ma teraz
  ratio^0,703): udział mierzony bez sędziego - niezmierzone (x0,89-1,10 przy ratio 0,85-1,15).
- **Udział x pokrycie**: okno 20 meczów tylko dla składów; udział liczy starty w 10 meczach
  bazy - zawodnik wpuszczony oknem zwykle < 3 starty -> fallback; okno mierzone bez
  rozciągnięcia i bez udziału (ewidencja pokrycia 82, 181); 0-2 nogi dziennie.
- **Faule na zawodniku**: bez udziału, rozciągnięcia i sędziego - zgodne z pomiarem.
- Wpływ udziału w E2E: 12 / 6 nóg strzałów/fauli zawodnika wypada (np. Lamine Yamal
  strzały pow. 2,5: p 0,911 -> 0,714; Murilo pow. 0,5: 0,903 -> 0,737); krzywe zawodników są
  fitowane na p własnej próbki z rozciągnięciem (ewidencja udziału 99: krzywa zaniża nogi
  udziału o 2-6 pp przy >= 0,70).

## 4. Ocena nowych rynków (SETTLE)

Ręczna kontrola 20 meczów 10-14..10-19: 236 wartości zgodnych, 0 niezgodnych; 300 meczów: 3 629 / 0;
ścieżka `_settle_derived` (both-over = min stron > linia; handicap strzałów przy -3, -2,5, +2, 0):
4 245 / 0, 49 PUSH na liniach całkowitych, wszystkie poprawne (0 j.). Kartka 45+N -> 1. połowa;
kartka w przerwie: Sofascore zapisuje 46 (2. połowa, dobrze), 45 przed HT (1., nieuniknione)
albo -5 (połówki punktów: odmowa; czerwone: D1). Druga żółta: punkty wg połowy każdej kartki.
Karne: przyznane = gol z karnego + `inGamePenalty`; dogrywka wyłączona. Faule na zawodniku:
brak `wasFouled` = 0 tylko gdy suma strony w [faule rywala - 4, faule rywala], inaczej pominięcie.
Kartki ławki wypadają (filtr `"cards" in market`, `run_settle.py:1353`). Uwagi (pytanie o regułę,
nie kod): czerwona -5 liczy się w pełnym meczu (jak dotąd `red_cards_total`); karny powtórzony
w tej samej minucie liczy się 2 razy (4 / 4 000 meczów).

## 5. Bramki

- `pytest tests/sofa` (MAIN): **5 473 passed, 2 skipped**. W worktree 2 porażki wyłącznie
  środowiskowe (D8 i `test_f15_resolve...` w katalogu /private/tmp).
- `ruff`: **1 błąd** - D2. `mypy --strict --no-incremental` (worktree, bez nieśledzonych
  skryptów): czysto, 318 plików. `check_test_registry`: 21 testów, 0 uwag.
- `day_status.py --date 2026-10-20`: **BROKEN** - `STALE_CONFIDENCE`: `vetoes.json` / `reads.json`
  10:01 (czas lokalny) nowsze niż `08_confidence.json` 08:57 (scalenie odczytu kuponu czatu po
  druku; dzień zakończony); WARN offer (15,8 h), clv 1 819/2 414, identity (basketball 88%,
  cs2 60%, BRIDGE_ABORTED).

## 6. Gotowość refitu

- Odtwarzalne: `--closeness-stretch` (calibrate + prepare_refit, ale tylko ręcznie - D5);
  `--player-coverage` (tylko calibrate - D4).
- Nieodtwarzalne: sędzia (replay nie ma etykiet sędziów) - następny refit dopasuje krzywe
  kartek/fauli (`cards_points` suma/strona, `fouls` suma/strona/1h/2h) na centrach bez sędziego,
  a na żywo centra mają ratio^beta (przy >= 0,70 krzywe w obu wariantach różnią się o 1-2 pp,
  ewidencja sędziego 142; stare krzywe na centrach z sędzią niezmierzone). Udział zawodnika -
  calibrate go nie liczy, krzywe strzałów/celnych/fauli zawodnika zostają fitowane na p własnej
  próbki z rozciągnięciem (niedopasowanie 2-6 pp zostaje). Połówki kartek, czerwone/karne
  stron: osobny skrypt, przeżywają refit przez carry. Warianty statystyk: bez krzywej
  (`NO_LINE_EVIDENCE`). Krzywa fauli na zawodniku: D6.
- Uczciwy następny refit: flagi 10-17 + `--closeness-stretch --player-coverage`; w
  `fitted_from` zapisać, że krzywe kartek/fauli i zawodników są bez reguł sędziego i udziału
  (albo poczekać na haki replayu).

Artefakty audytu: `scratchpad/audit/` (`e2e_prep.py`, `cmp_sheet.py`, `cmp_conf.py`,
`gradeable.py`, gałęzie `off/`, `on/`, logi, `fix_gates_regrade.patch`, `g/fix_red_1h.patch`,
`g/spot.py`); worktree `scratchpad/audit/wt` (detached HEAD, epochs przełączane `AUDIT_ON`) -
usunąć: `git worktree remove --force <ścieżka>`.
