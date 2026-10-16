# Raport 2026-10-16: nowe rynki z istniejącego modelu (worktree `wt/new-markets-2026-10-16`)

Polecenie operatora: „zrób worktree osobne i wdróż oba punkty” – (1) piłkarskie
rynki „lub” + handicap słabszej strony, (2) tenisowe dopełnienia wyniku
setów; bez długich procesów, z testami i weryfikacją, bez ruszania żywej
sesji sofa-day. Lista kontrolna: `PLAN_NOWE_RYNKI_2026-10-16.md`.

## Co weszło

- `bet.sofa.football_score_markets` (nowy): 8 rynków, klasyfikacja nazw
  Superbetu, siatka NB, rozliczenie, klucz krzywej wycinka, klasa
  `season_early`.
- `tennis_sets.SET_SCORE_NOT` + `classify_set_complement` (kanoniczny
  podmiot „<gracz> 0:2”).
- przełączniki `FOOTBALL_SCORE_MARKETS_FROM_UTC`,
  `TENNIS_SET_COMPLEMENTS_FROM_UTC` = 2026-10-17 00:00Z;
- OFFER / run_offer / capture_closing, SHEET (`score_market_rows`,
  `set_market_rows`), CONFIDENCE (`curve_market`, `leg_class`),
  `fit_line_evidence` (ten sam klucz krzywej), SETTLE / regrade (przy 0,5),
  `audit_ledger` (grupa „od 10-17”), rodzina `goals` dla builderów;
- krzywe: `scripts/sofa/fit_score_market_curves.py` →
  `data/refit_new_markets_2026-10-17/`, zainstalowane w configu worktree
  (135 kluczy); test rejestru `T-SCORE-MARKETS-superbet`;
- skille analityków (football-analysis, tennis-analysis): znaczenie nowych
  nóg.

## Pułapki złapane po drodze

1. `handicap_*` = rynek pochodny → krzywa nieczytana; nazwa `result_handicap`.
2. wiersz SHEET przy wyłączonym przełączniku dostawał `score_market_rule:
   null` (nie bajt w bajt) – złapane testem, poprawione w `sheet_row_json`
   i `off_scenarios`;
3. krzywa jednego rynku ukrywała wycinki −3..−9 pp → krzywe per wycinek;
4. wczesna faza sezonu −1..−5 pp → klasa `season_early`;
5. „X bez straty seta – Nie” ≡ „Y wygra seta – Tak” → jeden rung;
6. rozliczenie wskaźnika 1/0 przy linii goli (np. 2.5) zawsze dałoby UNDER
   → ocena przy 0,5, z testem.

## Weryfikacja

- `tests/sofa` (cały), ruff, mypy --strict, `check_test_registry` – zielone;
- E2E w poligonie (`scratchpad/e2e`, baza tylko do odczytu, zegar 08:10Z) na
  10-14 / 10-15 / 10-16: SHEET off = on bez nowych bajt w bajt, 0 nóg
  utraconych lub zmienionych, +484 / +536 / +1 068 nóg; rozliczone 10-14..15:
  1 018 nóg / 233 mecze, realizacja − pewność +1,2 pp [−1,8, +4,2], ROI
  −2,4 % [−6,1, +1,2]; tenis 27 nóg −9,8 pp (otwarte);
- prawdziwe pliki 10-15 nietknięte (md5); 10-16 zmieniała tylko żywa
  przebudowa sofa-day (0 nowych rungów / nóg w prawdziwym 10-16).

## Przegląd końcowy – znalezione i naprawione

1. refit gubił wszystkie osobno dopasowane krzywe (także 29 kluczy 10-15 i
   `match_won_for`) – teraz przenosi je sam `fit_confidence` /
   `fit_sport_confidence` (`fit_meta`), z testem na zainstalowanych plikach;
2. weryfikator i scout pytali Superbet bez nowych flag – `offer.day_flags`;
3. etykiety PDF / HTML w słowach Superbetu;
4. testy etapów CONFIDENCE (cały etap) i `fit_line_evidence`;
5. sprzeczności w dokumentach (Not modelled yet, match_won_for „wklejany”,
   tabela przełączników skilla) usunięte.

## Nie zrobione / otwarte

- merge do `main` – decyzja operatora (żywa sesja sofa-day na `main`);
- grupowanie linii jednego meczu jako „ta sama zmienna” (dwuwymiarowe);
- `fit_line_evidence` bez `leg_class` (jak 1X2 / DNB);
- tenis `set_score_not` na liniach Superbetu – obserwować.
