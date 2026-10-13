# B7: tempo (posiadania Olivera) i skuteczność na posiadanie w koszykówce (audyt 2026-10-13)

Przełącznik: `epochs.BB_PACE_FROM_UTC` (domyślnie `None`). Kod:
`score_model` (`PACE_METRICS`, `box_values`, `load_box_scores`,
`attach_box`, `ScoreModel.pace`), replay: `sport_confidence.parse_history(...,
box=...)`, `walk_forward_rows(..., pace=...)`, `settled_shadow_rows(...,
pace=...)`, `fit_sport_confidence --bb-pace`. Skrypt pomiaru:
`scripts/sofa/measure_basketball_pace.py` (tylko odczyt).

## Diagnoza (zweryfikowana w kodzie)

- `score_model.parse_event` czyta z listingu tylko punkty po kwartach;
  `_metrics` dla koszykówki to jedno `bb_reg_for` (punkty regulaminu na
  stronę), `ScoreModel.expected` = stawka ligi x atak x obrona na punktach.
  Ani `score_model.py`, ani `sport_confidence.py` nie czyta
  `sofa_event_stats.statistics_json` (grep: 0 użyć).
- Dane na kopii bazy `data/refit_2026-10-13/sofa_replay.db`: z 51 168 meczów
  historii koszykówki 34 413 ma wiersz w `sofa_event_stats`, 29 725 ma pełny
  box score (`fieldGoalsScored` z próbami, `freeThrowsScored`,
  `offensiveRebounds`, `turnovers`). Pokrycie po miesiącach: 2024-10..2026-05
  ok. 75-90% meczów, 2026-09 791 / 1 228, **2026-10 4 / 1 334** - box score
  koszykówki nie jest pobierany na bieżąco (`backfill_event_stats.py --sport
  basketball` uruchamiany ręcznie).

## Co jest nowe wobec odrzuconego B2B

B2B (back-to-back) to kontekst terminarza mierzony na punktach (+0,06 pkt, se
0,64, bez efektu). B7 to inna oś: **inne wejście** (box score zamiast samych
punktów) i inna struktura centrum - liczba posiadań meczu (tempo obu drużyn)
razy punkty na posiadanie (atak strony x obrona rywala). Nie dotyka
terminarza ani odpoczynku.

## Rejestracja (zapisana 2026-10-13 PRZED uruchomieniem pomiaru)

Estymator nowy (wariant jedyny, rozstrzygający):

- Posiadania strony (Oliver, wersja prosta): `FGA - ORB + TOV + 0,44 x FTA`;
  posiadania meczu = średnia obu stron; przeskalowane do regulaminu
  `4Q / (4Q + 5)` gdy mecz miał dogrywkę (Q = długość kwarty ligi,
  `quarter_minutes_for`). Mecz z posiadaniami poza 40..140 lub bez któregoś
  pola: brak box score.
- Punkty na posiadanie strony = punkty meczu (`current`) / posiadania meczu
  (bez skalowania - dogrywka ma tę samą skuteczność).
- Dwie nowe metryki w tym samym `RatingBook` co punkty: `bb_poss` (tempo:
  atak = własne tempo, obrona = tempo dopuszczane) i `bb_ppp` (atak = ORtg,
  obrona = DRtg). Ta sama mechanika: stawka ligi, link / siła ligi, `MIN_TEAM_MATCHES`.
- Oczekiwane punkty regulaminu strony = średnia(E posiadań gospodarza,
  E posiadań gościa) x E punktów na posiadanie strony; podział na kwarty
  tymi samymi udziałami; szum (`bb_game_sd` / `bb_team_sd` / `bb_quarter_sd`)
  dopasowany momentami na resztach względem NOWEGO centrum (ta sama funkcja).
- Powrót do modelu punktowego (bez zmian), gdy: któraś strona ma < 5 meczów
  z box score, któraś nie miała meczu z box score w ostatnich 60 dniach
  (`PACE_FRESH_S`, wybrane, nie dopasowane), rozgrywki mają < 30 meczów z box
  score (stawka ligi ścisła, bez średniej globalnej), albo para jest UNLINKED
  na metrykach tempa.
- α (`ALPHA_BY_METRIC`) dla `bb_poss` z {0,03; 0,06; 0,10; 0,15} i dla
  `bb_ppp` z {0,03; 0,06; 0,10}: wybrane na oknie strojenia
  **2025-01-01..2025-06-01** kwadratem błędu sumy regulaminu one step ahead
  (tylko mecze, w których działa ścieżka tempa); potem zamrożone.

Model dzisiejszy (porównanie): `build_model` bez box score, te same reguły
dnia 2026-10-13 (świeżość szumu włączona jak na żywo; A2, A3 / C8 wyłączone -
dziś `None`).

**Test A - historia (główny).** Okno **2025-10-01..2026-06-01**, walk-forward:
model przebudowany co 30 dni (jak `walk_forward_rows`), między przebudowami
książka aktualizowana mecz po meczu; co n-ty mecz do 6 000; 1 000 symulacji
na mecz i model, to samo ziarno. Linie: kwartyle (+0,5) sumy regulaminu,
punktów strony i marginesu z meczów 2025-01-01..2025-10-01 (przed oknem,
nigdy z ceny). Metryki na mecz: średni Brier i log-loss po progach dla
`total`, `team_total` (obie strony), `handicap` (margines), oraz zwycięzca z
dogrywką. Różnica w parach nowa - stara; 95% z bootstrapu po meczach (2 000
losowań, ziarno 0). Raportowane też: podzbiór meczów ze ścieżką tempa,
kalibracja p >= 0,70.

**Test B - linie Superbetu.** Rozliczone linie koszykówki 2026-09-29..2026-10-12
(`runs/sofa/shadow/basketball/<d>/settled.json`), model zbudowany na 00:00Z
dnia (`settled_shadow_rows`), p modelu (cena nigdy nie jest wejściem p);
rodziny `total`, `team_total`, `handicap`, `winner`; Brier i log-loss w parach,
bootstrap po meczach. Dodatkowo Brier na liniach głównych (fair 0,45-0,55;
cena wybiera tylko podzbiór, jak w audycie: dziś 0,2593 na totalu).

**Próg (O4, zapisany z góry):** Test A - `total`: górna granica 95% różnicy
Briera **i** log-loss < 0; zwycięzca: dolna granica różnicy Briera <= 0 (nie
gorzej). Test B - `total` i `winner`: przedział różnicy Briera nie leży w
całości powyżej zera. Spełnione oba -> refit krzywej koszykówki na kopii
(`data/refit_2026-10-13/b7/`, `--before 2026-10-13`) i compare w parach z
`data/refit_2026-10-13/bb_base` (holdout historii i linie Superbetu:
log-loss pewności i luka linii >= 0,70). **Bez instalacji i bez
włączania przełącznika.**

## Wynik

(uzupełnione po pomiarze)
