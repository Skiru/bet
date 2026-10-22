# Refit krzywej koszykówki z restartem sezonu - 2026-10-22 (NIE zainstalowano)

Zgoda operatora: 2026-10-22 ~19:40Z, refit i instalacja krzywej kosza z
regułą `LEAGUE_SEASON_RESTART` (`--league-season-restart`), pod warunkiem:
nowa krzywa nie gorsza poza próbą (przedział) ogółem i na nogach >= 0,70.
**Warunek nie jest spełniony - krzywa nie została zainstalowana.** `config/`
nietknięty; 10-22 i 10-23 czytają krzywą A7 z 10-14/10-15
(`config/sofa_sport_confidence_calibration.next.json`). Grupa księgi „od
10-23” bez zmian (żadnej nowej epoki).

## Dopasowanie (kopia bazy, bez sieci)

```
sqlite3 data/sofa.db "VACUUM INTO 'data/refit_2026-10-22b/bb_refit.db'"   # 6 min 57 s, 50,6 GB
SOFA_DB_PATH=data/refit_2026-10-22b/bb_refit.db PYTHONPATH=src:. .venv/bin/python \
  scripts/sofa/fit_sport_confidence.py --sport basketball --before 2026-10-23 \
  --bb-freshness on --league-rate-rule --league-season-restart \
  --market-lines data/a7_odds/basketball.jsonl --dry-run \
  --rows-out data/refit_2026-10-22b/rows --out data/refit_2026-10-22b/cal_staged_base.json
```

Flagi = wszystko, co niesie zainstalowana sekcja (`fitted_from`:
`bb_freshness`, `league_rate_rule`, linie rynku A7 na pełnym cache, bez
`bb_overtime`) + `--league-season-restart`. `--out` to kopia `.next.json`
(z niej przeniesiona krzywa `double_chance|TEAM`). Okno dopasowania
2025-09-23..2026-09-23, holdout 09-23..10-23; 8 519 / 3 905 meczów,
2 549 009 / 2 589 111 wierszy; 2 860 s. Rozliczone linie Superbetu
09-29..10-21: 152 276 linii / 2 229 meczów, p estymatora z restartem dla obu
krzywych. Obie krzywe są poza próbą na tych liniach (zainstalowana do
09-14 / 09-16, nowa do 09-23).

## Pomiar

Pewność = lo95 kubełka (n >= 200), bez wymogu admisji (tak czyta live od
line evidence), bez line evidence; bootstrap po meczach.

**Rozliczone linie Superbetu** (`scripts/sofa/measure_sport_curve_swap.py`,
`data/refit_2026-10-22b/compare_vs_installed.{md,json}`):

| zakres | linie / mecze | log-loss nowa - zainstalowana [95%] |
|---|---|---|
| wszystkie | 146 380 / 2 229 | **+0,00078 [+0,00065; +0,00093]** (gorzej) |
| NBA | 2 750 / 8 | +0,00075 [+0,00019; +0,00132] |
| inne ligi | 143 630 / 2 221 | +0,00078 [+0,00064; +0,00092] |
| h1_total | 8 699 / 1 754 | +0,00680 [+0,00616; +0,00750] |
| h1_team_total | 7 478 / 713 | +0,00429 [+0,00366; +0,00491] |
| quarter_team_total | 5 502 / 791 | +0,00137 [+0,00123; +0,00150] |
| quarter_handicap | 7 302 / 1 041 | -0,00119 [-0,00126; -0,00111] |
| h2_handicap | 2 440 / 289 | -0,00103 [-0,00127; -0,00077] |
| total | 31 044 / 2 219 | -0,00025 [-0,00041; -0,00007] |

Kalibracja przy pewności >= 0,70 (realizacja - pewność):

| | zainstalowana | nowa |
|---|---|---|
| wszystkie | 2 249 linii / 831 meczów, 0,748 -> 0,629, -11,8 pp [-15,2; -8,2] | 2 320 / 831, 0,749 -> 0,630, -11,9 pp [-15,3; -8,4] |
| NBA (8 meczów) | 139, +2,4 pp [-8,2; +12,4] | 141, +2,0 pp [-8,9; +12,4] |
| inne ligi | 2 110, -12,8 pp [-16,3; -9,2] | 2 179, -12,8 pp [-16,2; -9,2] |

Po rodzinach >= 0,70 bez zmian tam, gdzie leży luka (h1_handicap -23,3 pp,
h1_team_total -24,9 -> -25,5, h1_total -24,3 -> -25,2, quarter_handicap
-11,8 pp, n 207-379, obie krzywe). Nowa dodaje 85 nóg h1_1x2 (+2,6 pp
[-5,4; +9,9]) i 28 quarter_team_total, zabiera 42 quarter_1x2.

**Holdout historii** 09-23..10-23 (linie syntetyczne / rynku;
`data/refit_2026-10-22b/holdout_split.py`, ta sama metoda, NBA = unique
tournament 132; podział NBA / inne na liniach Superbetu: `split_nba.py`):

| zakres | linie / mecze | log-loss nowa - zainstalowana | >= 0,70: zainstalowana / nowa |
|---|---|---|---|
| wszystkie | 2 584 370 / 3 905 | -0,00008 [-0,00011; -0,00005] | +2,2 pp / +2,2 pp |
| NBA | 9 251 / 14 | -0,00001 [-0,00050; +0,00057] | -1,9 pp [-4,4; +0,7] / -2,1 pp [-4,5; +0,5] |
| inne ligi | 2 575 119 / 3 891 | -0,00008 [-0,00012; -0,00005] | +2,3 / +2,2 pp |

Holdout historii leży w oknie admisji nowej krzywej i tuż za jej oknem
dopasowania; na liniach, które Superbet faktycznie wystawia, nowa krzywa
jest gorsza z przedziałem nad zerem. NBA ma tu 8 (Superbet) / 14 (historia)
meczów sezonu regularnego - o NBA ten pomiar nie rozstrzyga w żadną stronę.

## Decyzja

Nie instalować: log-loss na rozliczonych liniach Superbetu gorszy
(+0,00078, przedział nad zerem), kalibracja >= 0,70 bez zmian (-11,8 vs
-11,9 pp). Ten sam obraz co 2026-10-16 (`docs/sofa/evidence/
basketball_a7_full_2026-10-16.md`): refit rodzin spoza A7 na nowszym oknie
pogarsza połowy / team totale. Restart sezonu działa od 10-23 w estymatorze
(p), krzywa zostaje z 10-14 - spójność oceniona w raporcie
`NBA_SEZON_STAWKA_LIGI_2026-10-22.md` (kalibracja >= 0,70 nie przesunęła się)
i tu ponownie: zainstalowana krzywa na p z restartem, NBA >= 0,70 +2,4 pp
(Superbet) / -1,9 pp (historia).

Hybryda (tylko klucze, gdzie nowa wygrywa: quarter_handicap, h2_handicap,
total) nie była rejestrowana przed pomiarem - wybór po wyniku; nie
zainstalowana, wymagałaby osobnej decyzji.

## Mechanizm instalacji (sprawdzony, nieużyty)

`sport_confidence.calibration_path_for` zna jeden plik staged (`.next.json`,
jedno `effective_from`, dziś 2026-10-14). Instalacja od 10-23 bez ruszania
10-14..10-22 wymagałaby promocji: `.next.json` -> plik zainstalowany (jak
10-13 z krzywą CS2), nowy `.next.json` z `effective_from` 2026-10-23. Koszt:
dni < 10-14 przy przebudowie czytałyby wtedy krzywą A7 kosza zamiast
sprzed A7 (dni te nie są przebudowywane - `confidence.py`: „promoted ...
once no earlier day is rebuilt”). 10-22 zostałby na starej krzywej.

## Pliki

`data/refit_2026-10-22b/`: `bb_refit.db` (kopia, 50,6 GB - do usunięcia
po przeczytaniu raportu), `fit.log`, `rows/` (wiersze i sekcja),
`compare_vs_installed.{md,json}`, `split_nba_settled.txt`,
`split_nba_holdout.txt`, oba skrypty pomocnicze. Nie testowane: E2E na artefaktach 10-22
(niepotrzebne bez instalacji).
