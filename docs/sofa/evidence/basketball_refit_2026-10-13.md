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

## Warianty A7 / A3 (2026-10-14, UTC noc z 10-13)

Hipoteza: krzywa historii jest dopasowana na liniach w kwantylach własnej
symulacji modelu, a Superbet stawia linie tam, gdzie stoi rynek - kubełki p
krzywej zapełniają inne linie niż te, które gramy (A7).

### Warianty

Wszystkie: `fit_sport_confidence.py --sport basketball --before 2026-10-14
--league-rate-rule`, `SOFA_DB_PATH=data/refit_2026-10-13/sofa_replay.db`
(tylko odczyt), scratch `data/refit_2026-10-13/bb_variants/<v>/` (`cal.json`,
`rows/`, `fit.log`); `config/` nietknięty, bez bridge'a.

| | co | flagi | czas |
|---|---|---|---|
| V0 | krzywa zainstalowana (baza) | - | - |
| V1 `v1_a7` | linie historii total / handicap / team total w pozycji rynku | `--market-lines data/a7_odds/basketball.jsonl` | 1 577 s |
| V2 `v2_a7_ot` | V1 + dogrywka A3 + C8 w replayu | V1 + `--bb-overtime` | 1 565 s |
| V3 `v3_ot` | sama dogrywka | `--bb-overtime` | 1 718 s |

Cache A7: z 26 332 celów zapytano 10 662 (cały priorytet 0), 2 661 meczów ma
linie rynku (~2 100 w oknie dopasowania); 20 740 wierszy historii z linią
rynku w dopasowaniu. Priorytet 1 (15 670 meczów) wymaga bridge'a - nie
dociągnięto. Szczegóły: `market_positioned_lines_2026-10-13.md` sekcja 2.

### Metoda

`bb_variants/compare_bb_variants.py v1_a7 v2_a7_ot v3_ot` (importuje
`compare_bb_refit.py`: te same funkcje pewności, log-loss, bootstrapu po
meczach 2 000 / ziarno 0, okno linii Superbetu 2026-10-05..10-12, 41 414 linii
/ 651 meczów), wynik `bb_variants/compare.json`. Trzy odczyty:

- **A**: p wariantu (V2 / V3 z dogrywką w `settled_shadow_rows`) przez krzywą
  zainstalowaną i przez krzywą wariantu;
- **R**: te same p przez refit z liniami syntetycznymi tymi samymi regułami
  (`bb_refit_lr` dla V1 / V3, V3 dla V2) i przez wariant - sam efekt A7;
- **B „system”**: V0 na p dnia 10-14 (`bb_refit_lr`) vs wariant na swoich p,
  pary linii - to, co 10-14 by przeczytał.

### Wyniki (wszystkie klucze)

| | odczyt | linie w parach / mecze | log-loss baza | wariant | różnica [95%] |
|---|---|---|---|---|---|
| V1 | A (= B, p bez zmian) | 39 709 / 651 | 0,79357 | 0,73135 | **-0,06223 [-0,07021; -0,05456]** |
| V1 | R (vs `bb_refit_lr`) | 39 711 / 651 | 0,79299 | 0,73133 | -0,06167 [-0,06922; -0,05436] |
| V2 | A | 38 764 / 651 | 0,79712 | 0,73211 | -0,06501 [-0,07204; -0,05825] |
| V2 | R (vs V3) | 38 764 / 651 | 0,79708 | 0,73211 | -0,06498 [-0,07184; -0,05820] |
| V2 | B | 38 711 / 651 | 0,79595 | 0,73224 | **-0,06371 [-0,07124; -0,05651]** |
| V3 | A | 40 892 / 651 | 0,79244 | 0,79242 | -0,00001 [-0,00094; +0,00091] |
| V3 | R (vs `bb_refit_lr`) | 40 892 / 651 | 0,79214 | 0,79242 | +0,00029 [+0,00017; +0,00041] |
| V3 | B | 40 737 / 651 | 0,79182 | 0,79295 | **+0,00113 [-0,00123; +0,00353]** |

Pięć kluczy A7 (`total|OVER/UNDER`, `handicap|TEAM`, `team_total|OVER/UNDER`),
odczyt A: V1 -0,12744 [-0,14250; -0,11324] (19 410 linii / 648 meczów), V2
-0,13688 [-0,15010; -0,12417]; V3 -0,00034 [-0,00198; +0,00130].

Luka drukowalna (pewność >= 0,70, realizacja - pewność):

| | linie / mecze | luka [95%] |
|---|---|---|
| V0 (p dnia 10-14) | 1 764 / 351 | -16,1 pp [-21,2; -10,8] |
| V1 | 486 / 237 | -17,0 pp [-23,8; -9,4] |
| V2 | 427 / 181 | -18,5 pp [-25,7; -11,0] |
| V3 | 1 642 / 316 | -15,6 pp [-20,8; -10,3] |
| V0 na pięciu kluczach A7 | 1 206 / 256 | -15,6 pp [-21,2; -10,2] |
| V1 / V2 na pięciu kluczach A7 | **0** | - |

Kalibracja po kubełkach pewności (B; n, średnia pewność, realizacja):

| kubełek | V0 | V1 | V2 | V3 |
|---|---|---|---|---|
| 0,0-0,5 | 33 406; 0,253; 0,467 | 36 834; 0,379; 0,476 | 35 935; 0,378; 0,474 | 33 495; 0,253; 0,469 |
| 0,5-0,6 | 23; 0,595; 0,696 | 63; 0,540; 0,460 | 66; 0,551; 0,576 | - |
| 0,6-0,7 | 5 663; 0,640; 0,556 | 2 328; 0,642; 0,557 | 2 336; 0,646; 0,551 | 5 755; 0,644; 0,553 |
| 0,7-0,8 | 1 517; 0,745; 0,597 | 456; 0,737; 0,588 | 401; 0,745; 0,571 | 1 436; 0,750; 0,607 |
| 0,8-0,9 | 230; 0,837; 0,600 | 26; 0,844; 0,308 | 21; 0,839; 0,429 | 190; 0,845; 0,600 |
| 0,9-1,0 | 17; 0,929; 0,706 | 4; 0,947; 0,750 | 5; 0,917; 0,800 | 16; 0,924; 0,688 |

Krzywa V1 na pięciu kluczach (kubełek p: n, realizacja w historii przy linii
rynku): 0,00-0,60 - 1 633..5 238, 0,474-0,511; 0,60-0,70 - 200..968,
0,480-0,527; wyżej tylko `team_total|OVER` 0,70-0,75 (n 216, 0,607).
Zainstalowana czyta te same kubełki 0,61-0,73 (0,60-0,70 / 0,70-0,75) i
0,21-0,24 (0,00-0,60).

### Wniosek

- **A7 potwierdza hipotezę:** przy linii rynku p modelu wyników nie odróżnia
  linii na totalach / handicapie / team totalach (realizacja ~0,47-0,53 w
  każdym kubełku do 0,70). Zawyżenie -16 pp na tych kluczach to rozdzielczość
  widziana tylko na liniach syntetycznych.
- **Ale próg koordynatora nie jest spełniony:** log-loss V1 / V2 lepszy z
  przedziałem daleko od zera, lecz luka drukowalna nie maleje (-16,1 ->
  -17,0 / -18,5 pp). Zysk log-loss to głównie linie p < 0,5, które nie
  drukują; pięć kluczy A7 traci wszystkie linie >= 0,70 (1 143 z 1 206 -
  kubełek z n < 200 -> `NOT_CALIBRATED`; zainstalowana czytała je 0,767,
  zrealizowały 0,618), a zostające drukowalne linie (pozostałe klucze,
  krzywe jak w refitcie) mają tę samą lukę. Efekt V1 w druku = przestać
  drukować total / handicap / team total koszykówki - to pomiar, nie cięcie
  po nazwie, ale to zmiana tego, co drukuje, do decyzji operatora.
- **V3 (sama dogrywka) nie jest lepsza:** B +0,00113 [-0,00123; +0,00353],
  R nawet gorzej +0,00029 [+0,00017; +0,00041]; luka -15,6 pp w granicach
  szumu. V2 względem V1 bez istotnej różnicy (B -0,06371 vs -0,06223).
- **Nic nie wystawiono** (`<wariant>_cal.json` nie zapisany), `config/`
  nietknięty. Gdyby operator chciał V1: plik dopasowania
  `data/refit_2026-10-13/bb_variants/v1_a7/cal.json`, przełącznik
  `epochs.MARKET_POSITIONED_LINES_FROM_UTC` (wg komentarza w `epochs`
  działa tylko w replayu dopasowania - live czyta samą krzywą; włączony, by
  kolejne refity dopasowywały tak samo);
  `BB_OVERTIME_FROM_UTC` nie jest potrzebny (V2 wymagałby i jego).

### Czego nie sprawdzono

- Line evidence (offset / cap pasma) na krzywych wariantów; ROI.
- Krzywa A7 przy pełnym cache (priorytet 1, bridge) - kubełki >= 0,70 mogą
  się zapełnić; dziś n < 200.
- Hokej (A7 obejmuje go w audycie).
- Odczyt rejestracyjny A7 regułami `--before 2026-10-13` / `bb_base`
  (zrobiony regułami 10-14, odstępstwo zapisane w dokumencie A7).
