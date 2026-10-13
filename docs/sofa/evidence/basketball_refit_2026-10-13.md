# Refit krzywej pewności koszykówki pod reguły dnia 2026-10-14 (2026-10-13)

**Wynik: nie instalować.** Nowa krzywa nie jest lepsza z przedziałem
wykluczającym zero; luka „drukowalna” (~-16 pp) zostaje bez zmian. Konfiguracja
(`config/sofa_sport_confidence_calibration*.json`) nietknięta.

## Co zrobiono

- Kopia bazy tylko do odczytu: `data/refit_2026-10-13/sofa_replay.db`
  (`SOFA_DB_PATH`; `data/sofa.db` nieużywana). Scratch:
  `data/refit_2026-10-13/bb_refit/`, `bb_refit_lr/`.
- `fit_sport_confidence.py --sport basketball --before 2026-10-14 --out
  <scratch>/cal.json --rows-out <scratch>/rows` (bez `--dry-run`, bo
  `--dry-run` nie zapisuje `--out`; `--out` wskazuje scratch). Reguły dnia
  10-14 z `epochs`: `bb_freshness` wł., `league_rate_rule` wł.
  (`LEAGUE_RATE_RULE_FROM_UTC` 2026-10-14 00:00Z), `bb_overtime` / `bb_pace` /
  `MARKET_POSITIONED_LINES` wył. (jak live). Okno dopasowania
  2025-09-14..2026-09-14, holdout 2026-09-14..10-14; 3 936 meczów w
  dopasowaniu, 1 969 w holdoucie; 1 713 s.
- Drugi przebieg z `--league-rate-rule` (`bb_refit_lr/`, 1 680 s): bez
  flagi `settled_shadow_rows` liczy p linii Superbetu regułą *ich* dnia
  (< 10-14, więc reguła wyłączona) - z flagą p linii Superbetu jest p
  estymatora dnia 10-14 (372 z 41 786 linii 10-05..10-12 odpada:
  `NO_LEAGUE_RATE` / `FRIENDLY_FIXTURE`). **Krzywe obu przebiegów są
  identyczne** (krzywa = tylko historia, a historia w obu ma regułę);
  różni się tylko admisja. Liczby niżej z `bb_refit_lr`.
- Stara krzywa: sekcja `basketball` pliku zainstalowanego (identyczna w
  `.next.json`), `--before 2026-10-08`, holdout 09-08..10-08 - dni
  10-05..10-12 są poza jej oknem dopasowania (dni 10-05..10-07 w jej
  holdoucie). Nowa: 10-05..10-12 w holdoucie, poza dopasowaniem. Obie poza
  próbą na populacji pomiaru.

## Metoda pomiaru

Skrypt (tylko odczyt): `data/refit_2026-10-13/bb_refit/compare_bb_refit.py
bb_refit_lr`, wynik `bb_refit_lr/compare.json`.

- Populacja: rozliczone linie Superbetu koszykówki 2026-10-05..10-12
  (`basketball_superbet_settled.jsonl` z `--rows-out`, z
  `runs/sofa/shadow/basketball/<d>/settled.json`): 41 414 linii / 651 meczów.
- Pewność = `realised_lo95` kubełka krzywej z n >= 200 (jak
  `SportCalibration.lookup(require_admitted=False)` - odczyt epoki line
  evidence), **bez line evidence** (sprawdzian samej krzywej).
- A „krzywa”: te same p (estymator dnia 10-14) czytane starą i nową krzywą.
  B „system”: stare p (`bb_base`, reguła ligowa wył.) + stara krzywa vs
  nowe p + nowa krzywa, w parach na tych samych liniach.
- Log-loss pewności, nowa - stara, w parach; 95% z bootstrapu po meczach
  (2 000, ziarno 0). Luka drukowalna = realizacja - pewność na liniach z
  pewnością >= 0,70.

## Wyniki

| porównanie | linie w parach / mecze | log-loss stara | nowa | różnica nowa - stara [95%] |
|---|---|---|---|---|
| A krzywa, wszystkie klucze | 40 852 / 651 | 0,79169 | 0,79126 | **-0,00042 [-0,00145; +0,00063]** |
| B system, wszystkie klucze | 40 796 / 651 | 0,79254 | 0,79144 | -0,00110 [-0,00281; +0,00044] |
| A, klucze admitowane w którejkolwiek | 8 979 / 638 | 0,80040 | 0,80103 | +0,00063 [-0,00017; +0,00149] |

Luka drukowalna (pewność >= 0,70, realizacja - pewność):

| | stara | nowa |
|---|---|---|
| A wszystkie klucze | 1 764 linii / 351 meczów, -16,1 pp [-21,2; -10,8] | 1 692 / 352, -16,1 pp [-21,3; -10,8] |
| A klucze admitowane | 215 / 164, -4,9 pp [-11,9; +2,5] | 201 / 161, -2,1 pp [-9,4; +4,8] |

Kalibracja po kubełkach pewności (A, wszystkie klucze; n, średnia pewność,
realizacja):

| kubełek | stara | nowa |
|---|---|---|
| 0,6-0,7 | 5 663; 0,640; 0,556 | 5 756; 0,642; 0,557 |
| 0,7-0,8 | 1 517; 0,745; 0,597 | 1 478; 0,747; 0,603 |
| 0,8-0,9 | 230; 0,837; 0,600 | 197; 0,845; 0,564 |
| 0,9-1,0 | 17; 0,929; 0,706 | 17; 0,932; 0,706 |

Klucze z największą zmianą (A, różnica log-loss [95%]): poprawa
`team_total|OVER` -0,0127 [-0,0152; -0,0099], `total|OVER` -0,0114
[-0,0143; -0,0085], `h1_total|OVER` -0,0112 [-0,0137; -0,0087];
pogorszenie `h2_total|UNDER` +0,0163 [+0,0094; +0,0229], `h2_team_total|UNDER`
+0,0108, `team_total|UNDER` +0,0062, `total|UNDER` +0,0059, `handicap|TEAM`
+0,0053 [+0,0046; +0,0060]. Nowa krzywa podnosi OVER kosztem UNDER;
netto zero.

Admisja nowej krzywej (z `--league-rate-rule`): `h2_handicap|TEAM`,
`h2_team_total|OVER/UNDER`, `h2_total|UNDER`, `quarter_1x2|TEAM`,
`quarter_dnb|TEAM`, `quarter_total|OVER/UNDER`, `winner|TEAM`. Przy line
evidence (od 10-07) admisja nie decyduje o druku - liczy się krzywa i
offsety.

## Wniosek

- Refit tą samą metodą na estymatorze dnia 10-14 nie zamyka zawyżenia
  koszykówki: krzywa historii czyta ~0,75 tam, gdzie linie Superbetu
  realizują ~0,60 - to samo przy starej i nowej krzywej. Przyczyna nie leży w
  wieku krzywej ani w regule ligowej (jak w A7: `bb_base` / `bb_new`).
  Zawyżenie łapie dziś line evidence (offset klucza / cap pasma), nie krzywa.
- Próg O6 (poprawa w compare z przedziałem wykluczającym zero) niespełniony:
  nic nie zainstalowano, `.next.json` (CS2 od 10-13) bez zmian.
- Zdanie z CLAUDE.md „krzywe historii przyjmą regułę ligową z refitem
  koszykówki”: krzywa z regułą jest zmierzona i nie różni się istotnie;
  live p od 10-14 i tak liczy się z regułą (tylko odpadają linie).

## Czego nie sprawdzono

- Wpływu line evidence (offsety / cap pasma) na nową krzywą - pomiar krzywej
  samej.
- ROI - metryką jest kalibracja i log-loss pewności.
- Holdoutu historii jako kryterium (stara krzywa ma inne okno holdoutu).
