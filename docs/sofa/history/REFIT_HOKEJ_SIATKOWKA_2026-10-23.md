# Refit krzywych hokeja i siatkówki - 2026-10-23 (hokej staged od 10-24, siatkówka NIE)

Zgoda operatora: 2026-10-22 w nocy - refit i instalacja krzywych tam, gdzie
pomiar pokazuje poprawę. Powód: nocny backfill (koniec 2026-10-23 01:07Z)
dodał dużo historii hokeja i siatkówki (siatkówka statystyki + składy
~14,7 tys. celów, listingi nowych drużyn). Procedura jak przy koszykówce
2026-10-22 (`REFIT_KOSZ_SEZON_2026-10-22.md`).

**Wynik: hokej przeliczony i zapisany jako drugi plik staged z datą
2026-10-24 00:00Z; siatkówka niezainstalowana.** 10-22 i 10-23 czytają
dokładnie ten sam plik co wcześniej (`.next.json`) - test
`tests/sofa/test_sport_calibration_dated_stage.py`. Zmiana jest na gałęzi
`wip-sport-dated-stage`; scala ją sesja główna po przeglądzie.

## Dopasowanie (kopia bazy, bez sieci)

```
sqlite3 data/sofa.db "VACUUM INTO 'data/refit_2026-10-23/sp.db'"     # 7 min 35 s, 53,1 GB
SOFA_DB_PATH=data/refit_2026-10-23/sp.db PYTHONPATH=src:. .venv/bin/python \
  scripts/sofa/fit_sport_confidence.py --sport <hockey|volleyball> --before 2026-10-23 \
  --league-rate-rule --dry-run --rows-out data/refit_2026-10-23/rows_<sport> \
  --out data/refit_2026-10-23/base_<sport>.json      # base = kopia .next.json
```

Flagi: zainstalowane sekcje hokeja i siatkówki (fit 2026-10-07) nie niosą
żadnej reguły powtórki; estymator dnia dziś liczy p z regułą stawki ligi
(A2, `LEAGUE_RATE_RULE`), więc `--league-rate-rule`. Bez
`--league-season-restart` (dla hokeja / siatkówki zmierzony gorzej,
2026-10-22), bez A7 hokeja, bez B8 / B9 (wyłączone). Rozliczone linie
Superbetu dostają p z tego samego estymatora dla obu krzywych.

| | hokej | siatkówka |
|---|---|---|
| okno fitu | 2025-09-23..2026-09-23, 785 934 wiersze | to samo, 274 958 wierszy (+ 2 262 rozliczonych linii rodzin tylko-Superbet, 09-29..10-09) |
| holdout historii | 09-23..10-23, 647 144 wiersze / 3 375 meczów | 180 762 / 2 421 |
| rozliczone linie Superbetu | 73 725 linii, 09-29..10-21 | 22 848, 09-29..10-21 (rodziny tylko-Superbet: tylko 10-10..10-21) |
| czas | 908 s | 515 s |

10-22 nie było jeszcze rozliczone - zakres linii kończy się na 10-21.
Zainstalowana krzywa (fit do 09-07) i kandydat (do 09-23) są obie poza
próbą na liniach 09-29.. .

## Pomiar

Pewność = lo95 kubełka (n >= 200), bez wymogu admisji (tak czyta live od
line evidence), bez line evidence; bootstrap po meczach.
`measure_sport_curve_swap.py` (`data/refit_2026-10-23/{hk,vb}_compare.md`),
różnica kalibracji >= 0,70 `calib_diff.py`, holdout `holdout.py` (oba
skrypty pomocnicze w `data/refit_2026-10-23/`).

### Hokej - spełnia wszystkie trzy warunki

| miara | wynik |
|---|---|
| log-loss nowa - zainstalowana, linie Superbetu | **-0,00048 [-0,00062; -0,00033]** (71 948 linii / 1 788 meczów) |
| kalibracja >= 0,70 | zainstalowana -0,5 pp [-1,5; +0,5] (10 330 linii) -> nowa -0,2 pp [-1,2; +0,8] (10 764); różnica +0,30 pp [+0,13; +0,49] |
| holdout historii, log-loss | +0,00003 [-0,00002; +0,00008] - nie gorzej; >= 0,70 +0,8 -> +0,9 pp |

Po rodzinach (log-loss): lepiej `total` -0,00277, `period_total` -0,00101,
`period_team_total` -0,00073; **gorzej `handicap` +0,00224 [+0,00187;
+0,00262]** (5 606 linii / 756 meczów; przy >= 0,70 -1,5 -> -1,8 pp, ta sama
liczba linii). Hybryda bez `handicap` nie była rejestrowana przed pomiarem -
nie zbudowana. `winner` >= 0,70: -6,1 -> -0,3 pp (146 linii, nowa krzywa
niżej). Linie drukowalne (>= 0,70, x >= 0,90, marża <= 15%) 8 690 -> 8 850:
`total` +349 / -41, `period_dnb` +37, `team_total` +105 / -50,
`period_total` +29 / -199, `period_team_total` -57, `winner` -33.
Krzywe nowych rynków (`double_chance`, `period_double_chance` TEAM)
przeniesione bez zmian.

### Siatkówka - NIE zainstalowana

| miara | pełny kandydat | tylko rodziny z historii (krzywe tylko-Superbet z 10-07) |
|---|---|---|
| log-loss, linie Superbetu | -0,00080 [-0,00137; -0,00023] (18 210 linii / 922 mecze) | **-0,00003 [-0,00046; +0,00041]** |
| kalibracja >= 0,70 | -6,9 -> -6,4 pp, różnica +0,56 pp [+0,50; +0,63] | to samo (rodzina `set_winner` nie sięga 0,70) |
| holdout historii | -0,00013 [-0,00028; +0,00002] | to samo |

Cały zysk pełnego kandydata to `set_winner` (-0,00632), rodzina czytana
**tylko z rozliczonych linii Superbetu** (`settled_only_families`:
`set_winner`, `set_points_total`, `set_points_odd_even`, `set_extra_points`),
dopasowana na naszych dniach 09-29..10-09; kandydat dodałby też trzy nowe
krzywe tylko z naszych dni (`set_points_total` OVER, `set_points_odd_even`
EVEN / ODD). Zasada (CLAUDE.md, „Hard rules”; wzmocniona 2026-10-23 przez
`LIVE_ONLY_CURVE_REFUSED`): nasze rozliczone dni to audyt krzywej, nigdy
jej źródło. Bez tego zysku log-loss nie jest lepszy z przedziałem poza zerem
- warunek nie spełniony, siatkówka zostaje na krzywej z 10-07.

Uwaga: z **obiema** krzywymi siatkówka zawyża przy >= 0,70 na
`points_handicap` (-26,0 pp [-34,9; -16,3], 251 linii / 157 meczów) i
`points_total` (-22,2 -> -22,9 pp, 53 linie), `set_handicap` -7,4 -> -6,6 pp;
werdykt samego `measure_sport_curve_swap.py`: `install: false` (rodziny
zawyżające). To pytanie o estymator / line evidence, nie o ten refit.

## Mechanizm instalacji: łańcuch plików staged z datą

`sport_confidence.calibration_path_for` znał jeden plik staged
(`.next.json`, jedno `effective_from` 2026-10-14). Teraz czyta też
`sofa_sport_confidence_calibration.next.<RRRR-MM-DD>.json`
(`effective_from` = data z nazwy, inaczej błąd) i wybiera plik staged z
najpóźniejszym `effective_from` <= dzień. `run_sport_confidence` oznacza
każdy plik staged w `calibration_file` (`is_staged_calibration`).

| dzień | czyta |
|---|---|
| <= 2026-10-13 | `config/sofa_sport_confidence_calibration.json` |
| 2026-10-14..2026-10-23 (w tym 10-22, 10-23) | `config/sofa_sport_confidence_calibration.next.json` (bez zmian) |
| od 2026-10-24 | `config/sofa_sport_confidence_calibration.next.2026-10-24.json` |

Nowy plik = `.next.json` z sekcją hokeja z tego refitu; koszykówka,
siatkówka, CS2 identyczne (test). Line evidence poranka 10-24
(`refresh_line_evidence.py --before 2026-10-24`) czyta krzywą dnia, więc
offsety hokeja liczy już na nowej krzywej. Grupa księgi: istniejąca
„od 10-24” (`LIVE_ONLY_CURVE_REFUSED`), rozszerzona o ten refit - bez nowej
grupy. Test przedrejestrowany `T-HOCKEY-REFIT-1024` (PROPOSED).

## Bramki (gałąź `wip-sport-dated-stage`)

`pytest tests/sofa -q`, `ruff check`, `mypy --strict --no-incremental`,
`check_test_registry.py` - wyniki w opisie commita. Nie testowane: E2E
SPORT_CONFIDENCE na artefaktach dnia z nową krzywą (pierwszy dzień, który
ją czyta, to 10-24).

## Pliki

`data/refit_2026-10-23/`: `rows_hockey/`, `rows_volleyball/` (wiersze i
sekcje, w tym `volleyball_section_history_only.json`), `{hk,vb,vb2}_compare.*`,
`*_holdout.txt`, `*_calib_diff.txt`, `fit_*.out`, skrypty pomocnicze. Kopia
bazy `sp.db` usunięta po pomiarze.
