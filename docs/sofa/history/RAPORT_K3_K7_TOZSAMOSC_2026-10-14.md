# K3, K5, K6, K7 (piłka): tożsamość — raport (2026-10-14)

Plan: `docs/sofa/history/PLAN_MAPA_DRUZYN_2026-10-14.md`. Wcześniejsze kroki:
`RAPORT_K1_MAPA_ENCJI_2026-10-14.md`, `RAPORT_K2_DAY_ANCHOR_2026-10-14.md`.
Wszystko, co zmienia druk, działa od **2026-10-15 00:00Z** (dzień i zegar);
dzień 10-14 nie jest przebudowywany.

## K3 — mecz w liście turnieju dnia (`TOURNAMENT_DAY_FROM_UTC`)

Gdy **żadna** strona meczu hokeja / kosza / siatki nie ma id, nie ma kogo
zapytać o listing. Turniej Superbetu bywa jednak znany (mapa turniejów, K1):
`unique-tournament/<ut>/scheduled-events/<dzień>` daje wszystkie mecze
turnieju z id obu drużyn. W tej małej liście (jeden turniej, ±1 h, sport,
płeć, nie przełożony) mecz jest wybierany po **słabszej** z dwóch nazw
(`day_listing.tournament_day_match`): próg 60, przewaga nad następnym meczem
20. `bet.sofa.day_listing` (cache `sofa_day_listing`: dzień miniony raz na
zawsze, dzisiejszy po 45 min), `SofascoreClient.tournament_day_events` /
`scheduled_tournaments`, `sport_identity.identify_event(..., tournament_day)`.

Pomiar (`scripts/sofa/measure_tournament_day.py`, 10-05..10-14, **95 zapytań
mostka**, 0 odmów; pierwsza próba zatrzymała się na pojedynczym 403 —
odczekane 10 min, potem 2 zapytania diagnostyczne, oba 200):

| próg / przewaga | IDENTIFIED (id ukryte) | cele (żadna strona bez id): zidentyfikowane |
|---|---|---|
| 50 / 10 | 287 dobrze, 0 źle | 24 z 42 |
| **60 / 20** | **284 dobrze, 0 źle** | **24 z 42** |
| 70 / 20 | 275, 0 źle | 11 |
| 82 / 20 | 266, 0 źle | 1 |

Z 24 wskazań 15 SETTLE znalazł później sam jako ten sam mecz, 0 sprzeczności;
pozostałe 9 czytają się jednoznacznie (Zlatibor – Niš, Pardubice – Nový
Jičín, Prizma – Panter, Vilsbiburg – Suhl, Capixaba – Azul Mania…). Powtórka
kodu na cache dnia 10-13: Prizma Riga – Panter, Vilsbiburg – Suhl
zidentyfikowane. Listing „dnia” obejmuje szersze okno niż dzień UTC (z 1 075
meczów 356 z wieczoru dnia poprzedniego, 68 z rana następnego) — bez wpływu,
dopasowanie i tak filtruje ±1 h. Turnieje bez mapy (siatkówka: 170 zdarzeń w 10
dni, Argentyna / Czechy regionalnie, U19) — tu K3 nie pyta.

Nazwa strony > 82 jest uczona, niższa trafia do kolejki (`TOURNAMENT_DAY` w
obu zbiorach metod `entity_map`).

## K5 — `NOT_ON_SOFASCORE` (`NOT_ON_SOFASCORE_FROM_UTC`)

Pomiar zmienił obraz `NO_GAME_WITHIN_1H`:

- **do 10-12** większość takich werdyktów to mecze zapytane **po starcie**
  (114 ze 116 znalezionych potem przez SETTLE) — defekt naprawiony 10-12
  wieczorem (`frozen_at_start`). Liczby `NO_GAME_WITHIN_1H` z K0 i K2 dla dni
  sprzed 10-13 są tym zawyżone;
- **od 10-13** wszystkie zapytane przed startem (10-13: 6, 10-14: 12), ale **17
  z 18 odczytanych z cache** strony drużyny, który żyje do 6 h
  (`events_ttl_min = 360`) — mecz dodany albo przesunięty w Sofascore przez
  ten czas był niewidoczny.

Reguła: `NO_GAME_WITHIN_1H` z cache w ostatnich 3 h przed startem → jedno
świeże zapytanie o tę drużynę (raz na drużynę w przebiegu; ≤ ~60 zapytań
dziennie przy dzisiejszej liczbie) i ponowne dopasowanie. Brak udowodniony
(`reason: "NOT_ON_SOFASCORE"`, status nadal `NOT_IDENTIFIED`, nadal pytany do
startu, `absence_evidence` w rekordzie) tylko gdy: **świeża** strona, drużyna
rozpoznana po id (nie „do zapytania”), **żaden** jej mecz w ±12 h. Mecz 1–12 h
obok zostaje `NO_GAME_WITHIN_1H` z `nearest_game_h` (Kavkasia – Lausanne
10-14: Sofascore miał mecz 2 h później — przesunięty start, nie brak).
Przypadki z planu (Oman – Bahrajn, Arab Championship; Puchar Serbii kobiet)
spełnią regułę przy pierwszym świeżym zapytaniu.

## K6 — `BRIDGE_ABORTED`: pomiar, bez zmiany kodu

167 zdarzeń 10-05..10-14 skończyło jako `BRIDGE_ABORTED`, SETTLE znalazł potem
102. Źródło: **okresy odmowy**, nie pojedyncze błędy — 10-09 od ~13:30Z karta
mostka nie odpowiadała (504 w każdym przebiegu do końca dnia: 127 zdarzeń),
noc 10-13/14 Sofascore odpowiadał 403 na każde zapytanie pętli CS2 od 23:30 do
~05:00Z. Pętla pyta co 30 min i ponawia niezidentyfikowane do startu
(`identify`: tylko `IDENTIFIED` i rozpoczęte są zatrzymane), więc po
odblokowaniu mostka mecze wracają; giną te, które zaczęły się w trakcie
odmowy. Szybsze ponawianie łamie zasadę mostka; `day_status.py` już ostrzega
o każdym `BRIDGE_ABORTED`. Do zrobienia po stronie operatora, nie kodu: ręczne
rozwiązanie wyzwania przy nocnych 403, `ensure_bridge.py` przy 504.

## K7 — zawodnicy piłkarscy po nazwisku (`PLAYER_NAME_SURNAME_FROM_UTC`)

Z 89 piłkarzy 10-14 „matched no squad member”: 31 jest w składach pod krótszą
formą imienia (Trey Nyoni / Treymaurice, Ben Chrisene / Benjamin Joshua, Sam
Field / Samuel Edward, Evan Ndicka / „Evan N Dicka”), 57 nie ma w żadnym
zapisanym składzie (nowi, nieużywani — bez próbki i tak), 1 inny przypadek.
Mostek nie jest potrzebny.

Reguła (`players.match_player_by_surname`, ostatni fallback SAMPLES po regule
tokenów): całe nazwisko równe (ostatni token, albo dwa przy pojedynczej
literze) i imiona ze wspólnym **prefiksem ≥ 3 liter**, dokładnie jeden
kandydat po jednej stronie. Backtest
(`docs/sofa/evidence/identity_coverage_2026-10-14/k7/surname_backtest.py`,
kod produkcyjny, 10-12..10-14):

| wariant | dopasowani dziś: ten sam człowiek | inny człowiek | nowi |
|---|---|---|---|
| wspólny pierwszy inicjał | 1 808 | **6** (Reina Campos, Alberto → Andrés Campos; „… Silva”, „… Santos”) | 39 (w tym widocznie błędni) |
| **prefiks ≥ 3** | **1 827** | **0** | **22** (~7 dziennie) |

Próba precyzji (1 827) jest mniejsza niż reguły tokenów (20 033): górna
granica błędu ≈ 0,16% (95%). SAMPLES zapisuje `match_rule: "surname"`, SHEET
notatkę `PLAYER_NAME_SURNAME`, SETTLE ocenia `matched_name` jak przy
tokenach i odmawia (`PLAYER_AMBIGUOUS`), gdy druga drużyna ma kandydata
któregokolwiek z trzech dopasowań.

Nie zrobione w K7: zawodnicy hokeja / kosza (`NOT_IN_HISTORY` 55 / 62 w 10
dni, `NAME_UNCERTAIN` 10 / 12) i gracze CS2 (`NOT_IN_HISTORY` 6) — kolejny krok;
`team/{id}/players` (mostek) dla 57 nieobecnych w składach nie daje próbki,
więc nie jest włączany.

## Zmiany w kodzie

`src/bet/sofa/day_listing.py` (nowy), `client.py` (2 trasy), `db.py`
(`sofa_day_listing`), `sport_identity.py` (`identify_event`: TOURNAMENT_DAY,
świeże zapytanie, `NOT_ON_SOFASCORE`; `fresh_listing`, `nearest_game_h`),
`entity_map.py` (metody), `epochs.py` (`TOURNAMENT_DAY_FROM_UTC`,
`NOT_ON_SOFASCORE_FROM_UTC`, `PLAYER_NAME_SURNAME_FROM_UTC`), `players.py`
(`match_player_by_surname`), `samples.py`, `contracts.py` (`match_rule`),
`scripts/sofa/run_sport_identity.py`, `run_samples.py`, `run_sheet.py`,
`run_settle.py`, `measure_tournament_day.py` (nowy). Testy:
`tests/sofa/test_day_listing.py`, `test_not_on_sofascore.py`,
`test_player_name_surname.py`.

## Czego nie sprawdzono

- Żaden z trzech przełączników nie działał jeszcze na żywo; pierwszy przebieg
  pętli po 2026-10-15 00:00Z pokaże liczniki. Zapis cache listingów z dwóch
  pętli naraz (WAL, timeout 30 s) nie był testowany pod obciążeniem.
- K5: zysk świeżego zapytania (ile meczów dodanych w Sofascore „po cache”) nie
  jest zmierzony — nie da się go odtworzyć z historii.
