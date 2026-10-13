# Raport: refit piłki / tenisa 2026-10-13 (nowa epoka porównywalności)

Commit `282713a7`. Bieżący stan opisują `CLAUDE.md` („Refit of 2026-10-13”),
`docs/sofa/PIPELINE.md` (7.1a) i `docs/sofa/CONFIG.md` (7.7); ten dokument
jest zapisem zdarzenia.

## Co zainstalowano

- **Kiedy:** `prepare_refit.py install` 2026-10-13 18:06Z (testy `tests/sofa`
  przeszły); kopia konfiguracji sprzed instalacji: `config/backup_2026-10-14`.
- **Z czego:** krzywe, stałe silnika, bazy lig i niezawodność dopasowane na
  kopii bazy `data/refit_2026-10-13/sofa_replay.db` - 104,5 mln wierszy,
  ostatni rozliczony dzień 2026-10-12. Replay z ratingiem piłkarskim w
  centrum (audyt A6), B1 game state, B2 rated scope i venue prior, B14 waga
  ratingu, C1 faza sezonu, B5 rating setów tenisa (flagi w
  `data/refit_2026-10-13/ft/replay_rules.json`).
- **Stałe:** `K_CENTRE` 10 -> 15, tenis 5 -> 8, piłka 15.

## Co włączono (2026-10-13 18:10Z)

Krzywe opisują centrum z tymi członami, więc centrum weszło razem z nimi
(stała zgoda audytu, O5 / O6): `GAME_STATE_FROM_UTC`,
`FOOTBALL_RATED_SCOPE_FROM_UTC`, `FOOTBALL_VENUE_PRIOR_FROM_UTC`,
`TENNIS_SET_RATING_PRICES_FROM_UTC`, `SEASON_PHASE_FROM_UTC`,
`FOOTBALL_RATING_WEIGHT_FROM_UTC`.

Operator przesunął z 2026-10-14 00:00Z na tę samą chwilę
`CS2_COUNT_EXPOSURE_FROM_UTC` i `CS2_TEAM_ROUNDS_RACE_FROM_UTC`; krzywa CS2
w `config/sofa_sport_confidence_calibration.next.json` ma `effective_from`
2026-10-13.

## Plik `.next.json` piłki / tenisa

`config/sofa_confidence_calibration.next.json` (czytany przez każdy dzień od
2026-10-12) trzymał STARE krzywe plus krzywe zawodników tylko ze startów, a
`install` go nie dotyka - zostawiony ukryłby refit przed każdym dniem >= 10-12.
Teraz to nowy fit z przeniesionymi krzywymi zawodników z 2026-10-11 (różnią
się tylko klucze `player_*`, `test_player_starts_only`), `effective_from`
2026-10-13T18:10Z. Do przeniesienia nad plik główny później.

## Dzień mieszany i dziennik

10-13 jest dniem mieszanym: nogi wydrukowane przed 18:10Z zostają zablokowane
pod starymi krzywymi. Dziennik: grupa „10-13 mieszany”
(`audit_ledger.EPOCH_GROUPS`), nigdy sumowana z „od 10-12” ani „od 10-14”.

## Luka

`rebuild_plan.py` nie zna tych sześciu przełączników ani refitu stałych, więc
przebudowa zostawia `05_sheet.json` starej reguły. SHEET dnia 10-13 puszczono
ręcznie (`run_pipeline.py --only SHEET`).

## Pomiar przed włączeniem

Próba na 10-13 (scratch, zegar porannego buildu): drukowane single 900 -> 1323
(tenis 193 -> 454 z rynków setów, gole piłki 319 -> 416, rożne 163 -> 226),
pewność wspólnych nóg +0,25 pp.

Raport `data/refit_2026-10-13/ft/compare_report.md` liczył SHEET z
wyłączonymi przełącznikami: jego część z replayem kuponu mierzy nowe krzywe na
starym centrum, nie stan zainstalowany.

## Niesprawdzone

- Dowód z linii (`config/sofa_superbet_line_evidence.json`) dopasowano na
  starych krzywych; do porannego `refresh_line_evidence.py` stosuje się go do
  nowych - wpływu nie mierzono.
- Beta kartek B1 dopasowano na centrum bez ratingu, a B2 ratinguje
  `cards_points_for` - do ponownego fitu.
