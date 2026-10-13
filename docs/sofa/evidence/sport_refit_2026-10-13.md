# Refit krzywych pewności CS2, hokeja i siatkówki pod reguły dnia 2026-10-14 (2026-10-13)

**Wynik: wszystkie trzy - zostawić (keep).** Żadna nowa krzywa nie jest
lepsza z przedziałem wykluczającym zero; hokej jest istotnie gorszy.
Nic nie zapisano w `config/`; nic nie wystawiono jako
`sport_refit/<sport>/cal.json` do złożenia (pliki tam leżą jako wynik
pomiaru, nie do instalacji). Wzór: `basketball_refit_2026-10-13.md`.

## Co zrobiono

- Kopia bazy tylko do odczytu: `data/refit_2026-10-13/sofa_replay.db`
  (`SOFA_DB_PATH`). Scratch: `data/refit_2026-10-13/sport_refit/<sport>/`.
- `fit_sport_confidence.py --sport <s> --before 2026-10-14 --out
  <scratch>/cal.json --rows-out <scratch>/rows` (bez `--dry-run`), `nice 10`:
  - hokej, siatkówka z `--league-rate-rule` (p linii Superbetu = estymator
    dnia 10-14; `LEAGUE_RATE_RULE` jest i tak włączona dla historii
    `--before 2026-10-14`); okno 2025-09-14..2026-09-14, holdout
    09-14..10-14; hokej 565 s, siatkówka 285 s;
  - CS2: wyścig rund (B10) włączony regułą dnia (`cs2_team_rounds_race`
    dla 10-14), 15 s.
- Stara krzywa = to, co dzień 10-14 czyta dziś
  (`calibration_path_for` -> `sofa_sport_confidence_calibration.next.json`):
  CS2 - refit B10 `--before 2026-10-13`; hokej / siatkówka - sekcje równe
  plikowi zainstalowanemu (`--before 2026-10-07`, holdout 09-07..10-07,
  linie Superbetu w dopasowaniu tylko siatkówki 09-29..10-02). Dni
  10-05..10-12 są poza dopasowaniem obu krzywych (wyjątek obsłużony niżej).
- **CS2_COUNT_EXPOSURE (B12) nie dotyczy krzywych**: replay historii CS2
  nie produkuje rodzin kills / deaths / assists / team_kills, a żadna
  krzywa CS2 (stara ani nowa) nie ma ich kluczy - czytają tylko line
  evidence. Refit niczego dla nich nie zmienia; ich line evidence
  dopasowane na starym p to osobna sprawa (CLAUDE.md, B12).

## Metoda pomiaru

Skrypt (tylko odczyt):
`data/refit_2026-10-13/sport_refit/compare_sport_refit.py <sport>`
(adaptacja `bb_refit/compare_bb_refit.py`), wynik `<sport>/compare.json`.

- Populacja: rozliczone linie Superbetu 2026-10-05..10-12 z `rows/<s>_superbet_settled.jsonl`.
- Pewność = `realised_lo95` kubełka krzywej z n >= 200, **bez line evidence**;
  CS2 `map_team_rounds` tylko na liniach dopasowania (`LINE_OUTSIDE_FIT`).
- A „krzywa”: to samo p (estymator 10-14) czytane starą i nową krzywą.
  CS2: `model_p` z rozliczenia, a `map_team_rounds` przeliczone wyścigiem
  rund na stan dnia (jak `measure_cs2_team_rounds_race.py`; 1 356 z 1 384
  linii, reszta bez p wyścigu odpada).
- B „system” (hokej, siatkówka): stare p (`data/line_evidence/rows_before_2026-10-13`,
  reguła dnia) + stara krzywa vs nowe p + nowa krzywa. Na wspólnych liniach
  p są identyczne (0 różnic) - reguła ligowa tylko usuwa linie (siatkówka:
  292 z 4 942, hokej: 0) - więc B = A.
- Rodziny tylko z rozliczonych linii (siatkówka: `set_winner`,
  `set_points_*`) mierzone tylko poza `settled_dates_fit` nowej krzywej
  (09-29..10-05), tzn. 10-06..10-12.
- Log-loss pewności nowa - stara w parach; 95% z bootstrapu po meczach
  (2 000, ziarno 0). Luka drukowalna = realizacja - pewność przy
  pewności >= 0,70.

## Wyniki

| sport | linie w parach / mecze | log-loss stara | nowa | różnica nowa - stara [95%] | werdykt |
|---|---|---|---|---|---|
| CS2 | 3 024 / 167 | 0,66391 | 0,66383 | -0,00008 [-0,00030; +0,00015] | keep |
| hokej | 21 670 / 553 | 0,66017 | 0,66168 | **+0,00151 [+0,00105; +0,00200]** (gorzej) | keep |
| siatkówka | 3 582 / 205 | 0,65021 | 0,64989 | -0,00032 [-0,00175; +0,00120] | keep |

Klucze admitowane w którejkolwiek krzywej:

| sport | linie / mecze | różnica [95%] |
|---|---|---|
| CS2 (`team_maps\|OVER`) | 127 / 32 | -0,00029 [-0,00184; +0,00078] |
| hokej | 12 601 / 537 | +0,00169 [+0,00105; +0,00234] |
| siatkówka (`points_total\|UNDER`, `sets_total\|UNDER`) | 329 / 165 | +0,00192 [+0,00038; +0,00329] |

Luka drukowalna (pewność >= 0,70, realizacja - pewność; linie / mecze):

| sport | stara | nowa |
|---|---|---|
| CS2 | 160 / 53, +3,5 pp [-8,1; +13,2] | 175 / 61, +3,7 pp [-7,6; +13,7] |
| hokej | 3 034 / 447, -0,2 pp [-2,1; +1,6] | 3 050 / 448, -0,7 pp [-2,6; +1,1] |
| siatkówka | 244 / 115, -16,3 pp [-24,5; -7,9] | 231 / 112, -15,4 pp [-24,4; -6,8] |

Uwagi per klucz (A, różnica log-loss [95%]):

- **CS2**: żaden klucz nie wychodzi poza zero (np. `map_team_rounds|OVER`
  -0,00016 [-0,00068; +0,00032], `|UNDER` -0,00019 [-0,00042; +0,00003],
  `match_winner|TEAM` +0,00023 [-0,00044; +0,00088]). Nowa krzywa różni się
  od staged o jeden dzień historii - zmiana pomijalna. Admisja bez zmian
  (`team_maps|OVER`).
- **Hokej**: gorzej `total|OVER` +0,0050 [+0,0030; +0,0070], `handicap|TEAM`
  +0,0048 [+0,0034; +0,0062], `team_total|OVER` +0,0046 [+0,0036; +0,0056],
  `period_team_total|OVER` +0,0024, `period_total|OVER` +0,0023,
  `period_handicap|TEAM` +0,0014, `result_1x2|TEAM` +0,0015; lepiej
  `total|UNDER` -0,0032 [-0,0044; -0,0020], `period_total|UNDER` -0,0007
  [-0,0013; -0,00002]. Admisja nowej: wypada `period_team_total|UNDER` i
  `total|OVER`, wchodzą `period_total|UNDER` i `total|UNDER`. Stara krzywa
  jest na liniach Superbetu skalibrowana (kubełek 0,7-0,8: 0,751 vs 0,754;
  0,8-0,9: 0,843 vs 0,835).
- **Siatkówka**: lepiej `set_handicap|TEAM` -0,0048 [-0,0075; -0,0026]; gorzej
  `points_total|OVER` +0,0042 [+0,0024; +0,0059], `points_handicap|TEAM`
  +0,0028 [+0,0013; +0,0043], `points_total|UNDER` +0,0012 [+0,0008;
  +0,0017]. Nowa krzywa ma nowe klucze z rozliczonych linii
  (`set_points_odd_even`, `set_points_total|OVER`) - bez starej pary, poza
  porównaniem (pokrycie nowej 4 069 vs starej 3 595 linii). Zawyżenie
  ~-16 pp przy >= 0,70 zostaje przy obu krzywych (kubełek 0,8-0,9: 0,83
  vs realizacja 0,53 / 0,45) - sprawa krzywej / line evidence, nie wieku.

## Wniosek

- CS2: keep - `.next.json` (refit B10 od 10-13) zostaje; refit na dzień
  później niczego nie zmienia. B12 nie ma krzywej do refitu.
- Hokej: keep - nowa krzywa istotnie gorsza (+0,00151), luka drukowalna
  bez poprawy.
- Siatkówka: keep - różnica w zerze, klucze admitowane gorsze
  (+0,00192 z przedziałem powyżej zera).
- Próg (lepsza z przedziałem wykluczającym zero, luka nie gorsza) nie
  spełniony w żadnym sporcie: nic do złożenia w
  `config/sofa_sport_confidence_calibration*.json`.

## Czego nie sprawdzono

- Wpływu line evidence (offsety / cap pasma) - pomiar samej krzywej.
- ROI - metryką jest log-loss i kalibracja pewności.
- CS2: p rodzin innych niż `map_team_rounds` to `model_p` z rozliczenia
  (estymator dnia rozliczenia); dla kluczy z krzywą B10/B12 ich nie zmienia.
- Holdout historii jako kryterium (okna holdoutu starych krzywych są inne).
