# A7 koszykówka - krzywa na pełnym cache kursów Sofascore (2026-10-16)

**Wynik: pełnej sekcji nie instalować; zainstalowano hybrydę** - krzywe
tylko rodzin A7 z pełnego cache (operator 2026-10-15, „WŁĄCZ JUŻ DZISIAJ”;
sekcja „Hybryda” na końcu). Reguła decyzji (koordynator 2026-10-15:
log-loss lepszy z przedziałem nieobejmującym zera **i** żadna rodzina nie
zawyża pewności o więcej niż 2 pp przy >= 0,70 na n >= 200) nie jest
spełniona - log-loss na wszystkich kluczach jest gorszy. `config/`
nietknięty; dzień >= 2026-10-14 czyta dalej krzywą A7 z 10-14
(`config/sofa_sport_confidence_calibration.next.json`). E2E (krok e) i
instalacji (krok f) nie wykonano - reguła mówi „raport i stop”.

## Dopasowanie

`fit_sport_confidence.py --sport basketball --before 2026-10-16
--league-rate-rule --market-lines data/a7_odds/basketball.jsonl --dry-run
--rows-out data/refit_2026-10-16_bb/bb_a7_full/rows` na `data/sofa.db` (tylko
odczyt; bez kopii bazy - brak miejsca na dysku). Flagi jak przy instalacji
A7 z 2026-10-14 (`fitted_from` w `.next.json`): `bb_freshness` wł. (auto),
`bb_overtime` wył., `league_rate_rule` wł., linie rynku dla total /
handicap / team total. Dopasowanie 2025-09-16..2026-09-16, holdout
09-16..10-16, 2 127 s.

| | krzywa zainstalowana (10-14) | nowa (pełny cache) |
|---|---|---|
| mecze z liniami rynku w cache | 2 661 | 5 910 |
| wiersze historii z linią rynku (fit / holdout) | 20 740 / 4 864 | 50 360 / 5 312 |
| mecze w dopasowaniu | 5 712 | 7 369 |

Krzywa nowa na rodzinach A7 (historia, linia rynku; kubełek p: n,
realizacja, lo95): `total|OVER` < 0,60 - 4 146, 0,507, 0,492; 0,60-0,70 -
618, 0,549, 0,509; `total|UNDER` 0,60-0,70 - 654, 0,494, 0,456;
`handicap|TEAM` 0,70-0,75 - 271, 0,583, 0,524; `team_total|OVER` 0,70-0,75 -
391, 0,563, 0,513; 0,75-0,80 - 203, 0,650, 0,582; `team_total|UNDER`
0,70-0,75 - 388, 0,557, 0,507. Pełny cache wypełnił kubełki >= 0,70, ale
realizują 0,56-0,65: **przy linii rynku model wyników nie rozróżnia linii
total / handicap / team total** - to samo, co A7 pokazało 10-13 na 40%
cache. Najwyższa pewność, jaką nowa krzywa daje linii tych rodzin, to 0,58
(zainstalowana 0,54).

## Pomiar poza próbą

`scripts/sofa/measure_sport_curve_swap.py` (tylko odczyt; ta sama metryka co
`basketball_refit_2026-10-13.md` - skrypt odtwarza tamten wynik:
-0,0624 [-0,0696; -0,0549] wobec udokumentowanego -0,0622): rozliczone linie
Superbetu koszykówki **2026-10-05..10-14, 56 740 linii / 792 mecze**; p
estymatora dnia 10-16 (`--league-rate-rule`), te same dla obu krzywych.
Pewność = lo95 kubełka z n >= 200, bez wymogu admisji, **bez line evidence**.
Bootstrap po meczach, 2 000. Obie krzywe poza próbą (dopasowane do 09-14 /
09-16). Wynik: `data/refit_2026-10-16_bb/bb_a7_full/compare_vs_installed.{json,md}`.

### Log-loss pewności (nowa - zainstalowana)

| zakres | linie w parach / mecze | zainstalowana | nowa | różnica [95%] |
|---|---|---|---|---|
| **wszystkie klucze** | 54 273 / 792 | 0,73179 | 0,73213 | **+0,00034 [+0,00001; +0,00068]** |
| rodziny A7 (total, handicap, team total) | 25 712 / 789 | 0,69524 | 0,69264 | -0,00260 [-0,00319; -0,00199] |
| pozostałe rodziny | 28 561 / 788 | 0,76469 | 0,76768 | +0,00299 [+0,00264; +0,00334] |
| total | 12 107 / 785 | 0,69563 | 0,69174 | -0,00388 [-0,00491; -0,00288] |
| handicap | 6 460 / 787 | 0,69571 | 0,69342 | -0,00229 [-0,00282; -0,00171] |
| team_total | 7 145 / 399 | 0,69416 | 0,69345 | -0,00071 [-0,00195; +0,00052] |
| h1_total | 3 086 / 587 | 0,84736 | 0,85754 | +0,01018 [+0,00872; +0,01153] |
| h1_team_total | 2 740 / 251 | 0,84678 | 0,85270 | +0,00592 [+0,00494; +0,00695] |
| h2_handicap | 892 / 111 | 0,84113 | 0,84723 | +0,00610 [+0,00478; +0,00732] |

Zysk na rodzinach A7 jest realny, ale mniejszy niż strata na rodzinach
refitowanych tą samą metodą co dotąd (linie syntetyczne, nowsze okno).

### Kalibracja przy pewności >= 0,70

| | linie / mecze | pewność | realizacja | luka [95%] |
|---|---|---|---|---|
| zainstalowana | 684 / 301 | 0,746 | 0,617 | -12,9 pp [-19,0; -6,9] |
| nowa | 592 / 232 | 0,760 | 0,596 | **-16,4 pp [-22,7; -10,0]** |

Luka -16 pp się nie zmniejsza - rośnie. Rodzin z n >= 200 linii przy
>= 0,70 nie ma ani w jednej, ani w drugiej krzywej (największa: `winner`
157 -> 81), więc druga część reguły jest pusta; o wyniku decyduje log-loss.
Po rodzinach (zainstalowana -> nowa): `winner` +1,4 pp (157) -> -3,7 pp
(81); `h1_handicap` -21,3 -> -21,3 pp (133); `h1_team_total` -32,2 ->
-32,5 pp (86); `h1_total` -28,3 -> -26,6 pp (76 -> 73); `quarter_handicap`
-17,6 -> -17,5 pp (72).

Kubełki pewności (n, średnia pewność, realizacja):

| kubełek | zainstalowana | nowa |
|---|---|---|
| 0,0-0,5 | 50 142; 0,374; 0,475 | 46 105; 0,368; 0,469 |
| 0,5-0,6 | 93; 0,540; 0,559 | 4 706; 0,511; 0,538 |
| 0,6-0,7 | 3 406; 0,643; 0,561 | 3 360; 0,646; 0,559 |
| 0,7-0,8 | 626; 0,737; 0,620 | 534; 0,750; 0,597 |
| 0,8-0,9 | 51; 0,837; 0,549 | 51; 0,836; 0,549 |
| 0,9-1,0 | 7; 0,941; 0,857 | 7; 0,926; 0,857 |

### Linie drukowalne po rodzinach

Pewność >= 0,70 (w nawiasie dodatkowo x >= 0,90 i marża <= 15%; kursy z
`settled.json`, tylko do tego zliczenia):

| rodzina | zainstalowana -> nowa |
|---|---|
| total / handicap / team_total | 0 -> 0 (0 -> 0) |
| winner | 157 -> 81 (75 -> 45) |
| h1_1x2 | 18 -> 0 (11 -> 0) |
| quarter_1x2 | 13 -> 1 (5 -> 1) |
| quarter_total | 28 -> 35 (28 -> 35) |
| h2_1x2 / h2_dnb | 0 -> 6 / 0 -> 4 |
| h1_total | 76 -> 73 |
| pozostałe | bez zmian |

Totale, handicapy i team totals nie drukują ani z zainstalowaną, ani z nową
krzywą - pełny cache tego nie zmienia.

## Wniosek

- Pełny cache potwierdza A7: przy linii rynku p modelu wyników na
  totalach / handicapie / team totalach realizuje ~0,47-0,65 w każdym
  kubełku; żadna taka linia nie dostaje pewności 0,70.
- Refit całej sekcji koszykówki jest gorszy (log-loss +0,00034
  [+0,00001; +0,00068], luka -12,9 -> -16,4 pp): nie instalować.
- Hybryda (nowe krzywe tylko rodzin A7, reszta z 10-14) - zainstalowana na
  polecenie operatora, sekcja niżej.

## Hybryda - zainstalowana 2026-10-15 11:29:38Z

Polecenie operatora 2026-10-15 („WŁĄCZ JUŻ DZISIAJ”) po pomiarze pełnej
sekcji. **Wariant nie był zarejestrowany przed pomiarem** - wybrany po
obejrzeniu wyników per rodzina; zapisane tutaj jawnie.

- Sekcja koszykówki `config/sofa_sport_confidence_calibration.next.json`
  (`effective_from` 2026-10-14, bez zmiany): pięć kluczy A7 (`total|OVER`,
  `total|UNDER`, `handicap|TEAM`, `team_total|OVER`, `team_total|UNDER` -
  krzywa, `curve_source`, `oos`, `not_calibrated`) z dopasowania na pełnym
  cache; każdy inny klucz, z `double_chance|TEAM`, jak w dopasowaniu z
  10-14. Pozostałe sporty i metadane pliku bez zmian (sprawdzone przed
  zapisem). Ślad: `fitted_from.a7_families_refit`. Plik główny
  (`sofa_sport_confidence_calibration.json`, dni < 10-14) nietknięty.
- Działa od razu dla każdego dnia >= 10-14 (także przebudowy 10-14 /
  10-15). Kupon 10-15 nie był przebudowany. Druk się nie zmienia (niżej),
  więc dzień nie jest mieszany i ledger nie otwiera epoki.
- Kopia zapasowa: `config/backup_2026-10-15_bb_a7_hybrid/` (oba pliki
  krzywych sportów). Po zapisie `pytest tests/sofa`: 4 835 przeszło, 2
  pominięte. Test-strażnik `tests/sofa/test_basketball_a7_hybrid.py`.

**Pomiar** (ta sama populacja i metryka co wyżej, hybryda - zainstalowana
przed zmianą): wszystkie klucze 54 325 linii / 792 mecze, log-loss 0,73169
-> 0,73046, **-0,00123 [-0,00151; -0,00096]**; luka przy >= 0,70 bez zmian
(684 / 301, -12,9 pp); linie drukowalne bez zmian w każdej rodzinie.

**E2E** na kopii dnia 10-15 w scratch (`SOFA_RUNS_DIR`, `SOFA_CONFIG_DIR`,
`SOFA_NOW=2026-10-15T08:35:00Z`, budowa 08:32:21Z), `run_sport_confidence.py`
trzy razy:

| konfiguracja | nogi sportów | nogi koszykówki | kursy | poniżej 1/kurs |
|---|---|---|---|---|
| dziś (przed zmianą) | 221 | 3 (`winner`) | 1,31 / 1,32 / 1,43 | 2 |
| hybryda | 221 | 3 - te same, pewność bez zmian | 1,31 / 1,32 / 1,43 | 2 |
| pełna sekcja | 218 | 0 (trzy `winner` wypadają) | - | - |

Wariant „dziś” odtwarza prawdziwy `08_confidence_sports.json` 10-15 co do
nogi (221, 0 różnic pewności). md5 36 prawdziwych plików `runs/sofa/2026-10-15/`
przed i po - identyczne.

## Czego nie sprawdzono

- Line evidence (offset / cap pasma) na nowych krzywych poza E2E 10-15; ROI.
- Dogrywka (A3) - pozostaje wyłączona, nie mierzona ponownie.
