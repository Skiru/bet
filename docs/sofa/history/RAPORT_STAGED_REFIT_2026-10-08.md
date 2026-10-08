# Raport: refit etapowy (staged) z czterema wyłączonymi pakietami, 2026-10-08

Status: **nic nie zainstalowane**. Nie uruchomiono `install` ani `restore`, nie ruszono
`config/*`, `runs/`, `data/sofa.db` ani żadnego przełącznika epok. Wszystko poszło na kopii bazy
(`data/refit_2026-10-08/sofa_replay.db`, snapshot z 2026-10-07 ~17:12Z) i w katalogach roboczych.
Sprawdzono po fakcie: sha256 `config/sofa_confidence_calibration.json` = `dc374940...` (jak w
`install_manifest.json`), `sofa_sport_confidence_calibration.json` = `219a38da...`,
`tennis_rating.json` = `289d5e16...`; krok `fit` sam weryfikuje, że żywy config się nie zmienił.

## 1. Stan kodu (rekord)

- `git rev-parse HEAD` = `3550966ee935a79c7c46aa31a185366df810ca55`, 64 wpisy w `git status --short`.
- Skrót zawartości zmienionych/nowych plików (sha256 z konkatenacji, kolejność `git status`):
  - w chwili restartu replayu (kod z poprawką F1, 4 flagi + `--derived cards_points`): `59db65711349c5266f4ce870d6b400a84ada7ab2b764d451b76b39c48fb533ce`
  - na końcu pracy: `f11556f17caa1a61...` (kod ruszył jeszcze, wg koordynatora bez wpływu na liczby replayu: `run_sheet` exit 2 przy błędach configu, flagi `install`, `fit_count_dispersion --db/--write`).
- Pierwszy replay (stary `calibrate_from_cache`, joints bez alfy) został przerwany i **odrzucony**
  (log: `scratchpad/r/rebuild_aborted_oldcode.log`); jego wiersze były już skasowane na kopii, a pełny
  replay z kodem po F1 odbudował je od zera. Wszystkie liczby poniżej pochodzą z replayu po F1.

## 2. Co uruchomiono (komendy do powtórzenia)

Staged config: `data/refit_2026-10-09_stage/config` (kopia `config/*.json` bez `api_keys.json`) z
podmienionym `tennis_rating.json`. **Mechanizm staged configu istnieje:** `prepare_refit.py --config-dir <dir>`
ustawia `SOFA_CONFIG_DIR` dla replayu (`bet.sofa.config.config_dir`), a `fit` kopiuje ten katalog do
`<scratch>/config`. Katalog staged musi leżeć poza `--scratch` (check_scratch), stąd dwa osobne
katalogi. Żywy `config/tennis_rating.json` nie został nadpisany.

```bash
export P="PYTHONPATH=src:. .venv/bin/python"
# 1. V5 tenisa do staged configu (db z kopii przez SOFA_DB_PATH), cut jak w zainstalowanym (2026-10-01)
SOFA_DB_PATH=$PWD/data/refit_2026-10-08/sofa_replay.db PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_tennis_rating.py \
  --cut 2026-10-01 --tier-start --out data/refit_2026-10-09_stage/config/tennis_rating.json
# 2. backup staged configu, replay (4 flagi + joints kart), fit, compare
R="PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date 2026-10-09 --config-dir data/refit_2026-10-09_stage/config --db-path data/refit_2026-10-08/sofa_replay.db --scratch data/refit_2026-10-09"
$R backup
$R rebuild-cache-rows --confirm --without-db-backup --derived cards_points --count-dispersion --cards-correlation --per-market-k --tennis-scoped-table
$R fit
$R compare --days 2026-10-05 2026-10-06
```

Czasy: replay ~45 min (RSS szczyt **19,4 GB**, powyżej budżetu 16 GB; maszyna 48 GB), `fit_constants`
2001 s, `fit_confidence` 431 s, `compare` 10 s. Wynik: 59 819 093 wierszy replayu (przed: 59 504 765, w tym
wiersze joints kart); wiersze żywe (19 `run_date`) bez zmian. `K_CENTRE` po refit: 10 / football 15 / tennis 5
(bez zmian), `K_CENTRE.by_market.football` przeniesione przez `fit_constants` (cards_points_for 25,
fouls_total 2, shots_for 8, shots_total 5).

Hold-out alf (drugi replay, tylko zrzut wierszy, bez `fit`): alfy dyspersji dopasowane na danych
**< 2026-06-09** (`fit_count_dispersion.py --before 2026-06-09 --cases <a2/cases> --out
data/refit_2026-10-09_stage2/config/sofa_count_dispersion.json --write`), reszta jak wyżej, replay z
`--config-dir data/refit_2026-10-09_stage2/config`, scratch `data/refit_2026-10-09b`.

Artefakty: `data/refit_2026-10-09/config/` (4 pliki fitu: `sofa_confidence_calibration.json`,
`sofa_engine_constants.json`, `sofa_league_baselines.json`, `sofa_market_reliability.json`),
`fit_manifest.json` (complete: true), `compare_report.md/.json`, `analysis.json`,
`analysis_with_cut.json`, `paired_run1.json`, `paired_run2.json`, `curve_family_summary.json`,
zrzuty wierszy `rows_old.npz` (zainstalowane reguły, sprzed przebudowy), `rows_new.npz`, `rows_new2.npz`;
staged config: `data/refit_2026-10-09_stage/config/` (V5 `tennis_rating.json`, `sofa_count_dispersion.json`)
i `..._stage2/`. Skrypty analizy: `/private/tmp/claude-501/.../scratchpad/r/{dump_rows,analyse,paired,tables}.py`
(poza repo; nie dodane do niego).

## 3. Czego NIE zrobiono i dlaczego

- **Czterech sportów mierzonych** (hokej, koszykówka, siatkówka, CS2) nie refitowano: pakiety dotyczą
  liczników piłkarskich i tenisa, krzywe sportów (`sofa_sport_confidence_calibration*.json`) ich nie czytają.
- **`compare --with-sheet`** nie uruchomiono. `compare` bez SHEET powtarza CONFIDENCE na starych wierszach
  arkusza, więc **nie mierzy pakietów** (p_central z arkusza jest stare); sekcja "Coupon replay" w
  `compare_report.md` pokazuje tylko wpływ nowych krzywych na stare p, a PDF-y zgłosiły `STALE_COUPON`
  (exit 2) - znany kształt tego replayu, nie błąd pakietów. Skutek na kupon wymaga SHEET na rozliczonym dniu.
- **Atrybucja per pakiet**: replay ma cztery flagi naraz. Marginesy piłkarskie to efekt `COUNT_DISPERSION` +
  (tylko 4 rynki) `PER_MARKET_K`; `CARDS_CORRELATION` dotyka wyłącznie joints kart; tenis to wyłącznie
  `TENNIS_SCOPED_TABLE`. Rozdzielenia dyspersji od K na 4 rynkach nie zmierzono (wymagałby trzeciego replayu).
- **`install`** nie uruchamiany. Nie sprawdzono, czy `install` przyjmie `fit_manifest.json` z
  `base_config_dir` = katalog staged (a nie `config/`), bo wymaga backupu zgodnego z żywym `config/`:
  to luka do sprawdzenia przed instalacją (podejrzenie, niezmierzone).
- Klasy kobiece / puchary tenisowe (`by_class`) nie były analizowane osobno; analiza wierszy używa
  krzywych głównych (replay nie niesie klasy).

## 4. Krzywe: stare vs nowe, p >= 0,70 (kubełki `by_market_direction`, sekcja bez joints)

Źródło: `analysis.json` (`curve_rows`), `curve_family_summary.json`. Po 495 kubełkach `by_market_direction`
obecnych w obu plikach średnia zmiana `realised_lo95` to **-0,0006** (praktycznie zero), ale z rozrzutem po rodzinach:

| rodzina (kierunek) | lo95 stare | lo95 nowe | zmiana |
|---|---|---|---|
| saves_for UNDER | 0,868 | 0,849 | -0,0195 |
| cards_points_for OVER / UNDER | 0,863 / 0,869 | 0,846 / 0,855 | -0,017 / -0,014 |
| goal_kicks_total UNDER | 0,798 | 0,782 | -0,016 |
| fouls_for UNDER | 0,810 | 0,795 | -0,014 |
| shots_on_target_for UNDER | 0,858 | 0,844 | -0,014 |
| goals_total OVER (n=977 k) | 0,856 | 0,843 | -0,013 |
| goals_total UNDER (n=1,59 M) | 0,860 | 0,851 | -0,009 |
| handicap_games OVER (tenis, pochodny) | 0,849 | 0,836 | -0,013 |
| shots_for OVER | 0,733 | 0,764 | +0,031 |
| saves_for OVER | 0,816 | 0,843 | +0,027 |
| throw_ins_for OVER / total UNDER | 0,704 / 0,706 | 0,728 / 0,729 | +0,024 / +0,023 |
| tackles_for OVER | 0,771 | 0,793 | +0,022 |
| games_won_for UNDER (tenis) | 0,783 | 0,803 | +0,020 |
| games_total UNDER (tenis) | 0,724 | 0,739 | +0,015 |
| shots_on_target_for OVER | 0,815 | 0,831 | +0,017 |

Znak realised - nominal (flip) na poziomie rodzin: żadna rodzina nie zmieniła znaku luki poza szumem
(sekcja 6). Nowe krzywe są wyraźnie niżej tam, gdzie stary estymator był zbyt pewny (liczniki z małą średnią:
gole, kartki, interwencje), a wyżej tam, gdzie wariancja próbki zbyt rozszerzała rozkład (strzały, rzuty
auty, odbiory).

**Utrata / zysk wsparcia (kubełki p >= 0,70):** z 947 par (sekcja, klucz, kubełek) 880 w obu plikach, 19
tylko w starym, 48 tylko w nowym (z czego 41 to joints kart, patrz 5).
Tylko w starym (gubią wsparcie): `by_market_direction`: corners_total|UNDER 0,925-0,950 (n 1777),
goal_kicks_for|UNDER 0,925-0,950 (7835), offsides_for|OVER 0,900-0,925, shots_for|OVER 0,900-0,925 (752),
shots_for|UNDER 0,875-0,925, throw_ins_for OVER/UNDER 0,825-0,850 (~2550 każdy), throw_ins_total OVER/UNDER
0,750-0,800 (~525); `by_market`: shots_for 0,900-0,925, shots_total 0,825-0,850, throw_ins_for 0,825-0,850,
throw_ins_total 0,750-0,800. Część z nich zeszła do `thin_by_market_direction` (corners_total|UNDER
0,925-0,950 n=211, goal_kicks_for|UNDER 0,925-0,950 n=124, shots_for|UNDER 0,875-0,900 n=164), reszta
wypadła w ogóle: noga w tym kubełku spadnie na pulę z ograniczeniem K13/K13b albo na `NO_LINE_EVIDENCE`.
Rynki, które tracą górny kubełek: **shots_for, throw_ins_for, throw_ins_total, offsides_for**.
Zyskują nowe kubełki: fouls_for OVER 0,925-0,950, goal_kicks_total OVER 0,875-0,900.

## 5. Ile wierszy replayu by się wydrukowało (confidence >= 0,70), stare vs nowe

Metoda: `Calibration.realised` (z `cap_market_by_thin` i `cap_pool_by_neighbour`) dla każdego wiersza
replayu o p >= 0,55; stare wiersze (reguły zainstalowane) czytane starymi krzywymi, nowe nowymi. Bramki
cenowe (`confidence x odds >= 0,90`, ODDS_TOO_LOW, marża drabinki) **nie do oceny** (brak cen w replayu), więc
to liczba szczebli z pewnością >= 0,70 w całej historii, nie liczba nóg kuponu. Rynki pochodne (joints, tenisowe
`handicap_games`/`most_games`) pominięte: `run_confidence` ignoruje ich krzywe, dopóki
`DERIVED_CURVES_FROM_UTC` jest `None` (`scripts/sofa/run_confidence.py:681`), więc **krzywe joints kart
z `--derived cards_points` są nieczytane** i nie mogą niczego wydrukować.

| sport | wiersze >= 0,70 stare | nowe | zmiana | luka zrealizowane - pewność stare / nowe |
|---|---|---|---|---|
| piłka (bez joints) | 14 418 086 | 14 650 330 | +1,6% | +0,24 pp / +0,28 pp |
| tenis (bez joints) | 2 669 744 | 2 692 610 | +0,9% | +0,41 pp / +0,42 pp |

Duże zmiany liczby szczebli >= 0,70 (rodziny >= 30 tys.): throw_ins_for +44,5%, shots_for +23,4%, tackles_for
+21,9%, shots_on_target_for +11,2%, tackles_total +10,9%, saves_for +10,5%, fouls_total +10,0%, shots_total
+7,9%, goal_kicks_total +7,9%, fouls_for +6,4%, tenis games_won_for +6,7%; w dół: cards_points_for -6,9%,
tenis games_total -6,7%, offsides_total -3,7%, goals_total -3,4%, goals_for -2,4%. Rynki bez zmiany (nietknięte
przez pakiety): wszystkie `player_*`, tenisowe aces / double_faults, saves_total.
Uwaga: wiersze nie są nogami kuponu; to są szczeble drabinek całej historii (jedna mecz-rynek = wiele szczebli).

## 6. Kalibracja na okresie wyłączonym (hold-out)

Okno: piłka >= 2026-06-09 (data odcięcia dla K per rynek), tenis >= 2026-10-01 (cut `fit_tennis_rating`;
**tylko ~8 dni**, 30 tys. wierszy >= 0,70). W hold-oucie krzywa dla **każdego** reżimu (stary replay / nowy
replay) jest dopasowana własną, uproszczoną procedurą na wierszach sprzed odcięcia (market|kierunek -> market ->
pula sportu, Wilson 95%, progi 400/400/200 jak `fit_confidence`) i oceniona na wierszach po odcięciu - więc
porównanie jest jednorodne, ale **nie jest** zainstalowaną krzywą. Luka = zrealizowane minus pewność.

| piłka (bez joints), p >= 0,70 | n stare | luka | n nowe | luka | n nowe, alfy < 06-09 | luka |
|---|---|---|---|---|---|---|
| 0,70-0,75 | 426 186 | +0,48 pp | 522 508 | +0,21 pp | 520 642 | +0,20 pp |
| 0,75-0,80 | 587 367 | -0,13 pp | 555 300 | -0,06 pp | 551 554 | -0,08 pp |
| 0,80-0,85 | 466 922 | -0,12 pp | 494 913 | -0,05 pp | 497 739 | -0,09 pp |
| 0,85-0,90 | 522 867 | -0,16 pp | 517 084 | -0,09 pp | 523 408 | -0,08 pp |
| 0,90+ | 575 363 | -0,11 pp | 587 889 | -0,02 pp | 587 189 | -0,13 pp |
| razem | 2 578 705 | -0,03 pp | 2 677 694 | -0,00 pp | 2 680 532 | -0,04 pp |

Tenis (>= 2026-10-01, n ~ 6 tys. na kubełek): stare +0,66 / +0,37 / +0,33 / +0,78 / +0,93 pp, nowe
+0,69 / +0,31 / +0,76 / +0,89 / +0,88 pp; razem +0,61 vs +0,70 pp. Obie wersje konserwatywne (zrealizowane
nieco wyżej niż pewność); różnica nieistotna przy tej próbie.

**Rodziny z luką gorszą niż -1 pp lub o odwróconym znaku** (flagi z `tables.py`, rodziny >= 2000 wierszy hold-outu):
- `football:tackles_total`: luka -1,28 pp -> -1,72 pp (alfy z całej historii) / **-1,32 pp (alfy < 06-09)**:
  pogorszenie jest artefaktem in-sample alf, z uciętymi alfami wraca do starego poziomu (nadal ~-1,3 pp
  przepewne zarówno stare, jak nowe).
- `football:fouls_total`: +0,12 -> -0,30 pp (-0,37 przy uciętych alfach): zmiana znaku o 0,3-0,5 pp, bez znaczenia.
- `football:shots_for` -0,92 -> -0,58 / -0,77, `throw_ins_for` +1,15 -> +0,89 / +0,80: poprawa lub bez zmian.
Pozostałe rodziny z n >= 2000 nie przekroczyły progów flagi (zmiana znaku przy |luka| > 0,4 pp albo luka < -1 pp
i gorsza o > 0,3 pp od starej); to są progi ustawione przeze mnie, nie z repozytorium.

### In-sample vs poza próbą (uczciwie)

- Krzywe pewności: zawsze dopasowane na całym replayu (in-sample dla własnych kubełków); hold-out wyżej to
  krzywa sprzed odcięcia oceniona po nim.
- **Alfy dyspersji, K per rynek, `tier_start`/współczynniki tenisa**: oryginalne pliki były dopasowane na tej
  samej historii. Dla alf zrobiono hold-out (drugi replay, alfy < 2026-06-09, oceniane >= 06-09); K per rynek
  były w dowodzie wybrane na train i walidowane na ostatniej trzeciej (test od 06-09), a tenis ma cut
  2026-10-01 (hold-out 8 dni).
- Parowany wynik na poziomie wierszy (ten sam szczebel, p stare vs nowe, wiersze z p >= 0,55 w obu reżimach,
  okno hold-out, błąd standardowy klastrowany po meczu; `paired_run1/2.json`), różnica nowe minus stare, x1000,
  ujemna = lepiej:

| | n sparowanych | log-loss [95%] alfy z całej historii | log-loss [95%] alfy < 06-09 | Brier alfy z całej historii | Brier alfy < 06-09 |
|---|---|---|---|---|---|
| piłka | 3 886 241 | -3,20 [-3,33; -3,06] | **-2,83 [-2,96; -2,69]** | -1,08 | -0,98 |
| tenis | 49 921 | **-3,77 [-5,38; -2,17]** | to samo (tenis nie czyta alf) | -1,33 | -1,33 |

  Zysk piłkarski spada o ~12% przy alfach uciętych przed oknem testowym (in-sample zawyża zysk), ale
  pozostaje wyraźnie dodatni, przedział nie obejmuje zera. Wszystkie 22 rodziny piłkarskie i 6 tenisowych
  (>= 3000 sparowanych wierszy; `player_*` bez zmiany, tenis `games_total` poniżej progu 3000) mają górną granicę
  przedziału < 0 w obu wariantach. Największe zyski (alfy < 06-09):
  tackles_for -5,7, tackles_total -3,8, goal_kicks_for -3,6, corners_for -3,9, shots_on_target_for -4,3;
  najmniejsze: goal_kicks_total -1,2, saves_total -2,0, corners_total -1,4. Tenis: games_won_for **-13,2**,
  handicap_games -10,0 (pochodny, nie drukuje), aces / double_faults -0,8..-1,1.
  Ten pomiar jest zgodny z `count_families_2026-10-08.md` i `tennis_calibration_2026-10-08.md`, ale zrobiony
  na replayu, który dodatkowo zawiera SHEET-owy shrink K i reguły rozkładu - więc potwierdza efekt na
  poziomie wiersza, **nie na poziomie kuponu**.

## 7. Rekomendacje per pakiet (decyzja operatora, nic nie instalowane)

| pakiet | rekomendacja | uzasadnienie |
|---|---|---|
| `COUNT_DISPERSION` | **INSTALL** (razem z `PER_MARKET_K`, kod wymusza parę: `require_k_with_dispersion`) | hold-out z alfami < 06-09: log-loss -2,83e-3 [-2,96; -2,69] na 3,9 mln wierszy, wszystkie rodziny lepsze, luka kalibracji ~0 w każdym kubełku, liczba szczebli >= 0,70 +1,6%. Zastrzeżenia: `tackles_total` przepewne ~-1,3 pp (tak samo jak dziś); 10 kubełków górnych traci wsparcie (shots_for, throw_ins_*, offsides_for); po instalacji obowiązkowo odświeżyć line evidence i zbudować epokę; skutek na kupon (SHEET na rozliczonym dniu) niezmierzony |
| `PER_MARKET_K` | **INSTALL razem z dyspersją**, atrybucja NEEDS MORE | wszystkie 4 rynki K (cards_points_for, fouls_total, shots_for, shots_total) mają dodatni zysk w hold-oucie (-3,4 / -1,5 / -2,6 / -2,4 e-3), ale nie rozdzielono go od dyspersji; sam z siebie bez dyspersji nie zainstalować (zaprojektowane parą) |
| `TENNIS_SCOPED_TABLE` | **INSTALL** | tenis log-loss -3,77e-3 [-5,38; -2,17] poza próbą współczynników (8 dni), games_won_for -13,2e-3; luka konserwatywna (+0,7 pp). Liczba szczebli: games_won_for +6,7%, games_total -6,7%. Hold-out krótki; mocniejszy dowód to 48,6 tys. meczów w `tennis_calibration_2026-10-08.md`. Wymaga instalacji `tennis_rating.json` V5 (nie jest jednym z 4 plików fitu: sprawdź flagę `install --tennis-rating`) i przełącznika razem |
| `CARDS_CORRELATION` | **NEEDS MORE / DON'T teraz** | wpływ wyłącznie na joints kart; ich krzywe nie są czytane (`DERIVED_CURVES_FROM_UTC=None`), więc nic nie zmienia na kuponie; rho=0,126 zmierzone in-sample (jeden parametr); joints kart z replayu mają luki +0,7 (both_over) i +1,4 pp (handicap) w hold-oucie, czyli konserwatywne, ale bez drugiej strony (brak starego replayu joints) nie ma porównania. Włączać dopiero z `DERIVED_CURVES` |

Kolejność zmian dla operatora, jeśli da "go": jeden nowy epok (tennis V5 + dyspersja + K razem), `install`
z odpowiednimi flagami (`install --help`), potem `refresh_line_evidence.py`, potem przełączniki epok w
`bet.sofa.epochs` z datą następnego dnia 00:00Z, najpierw SHEET na rozliczonym dniu (`--with-sheet`).

## Wdrożenie (2026-10-08 23:42Z)

Refit zatwierdzony przez operatora zainstalowano 2026-10-08 23:42Z (commit
5330f357: nowe krzywe piłki i tenisa, `config/sofa_count_dispersion.json`,
`tennis_rating.json` V5 z `tier_start`, `K_CENTRE.by_market`, bazy ligowe,
wiarygodność rynków - **nowa epoka porównywalności**). Commit fdbe0aae ustawił
`COUNT_DISPERSION_FROM_UTC`, `PER_MARKET_K_FROM_UTC` i
`TENNIS_SCOPED_TABLE_FROM_UTC` na 2026-10-09 00:00Z (liczy się dzień budowany
ORAZ zegar budowy). `CARDS_CORRELATION_FROM_UTC` zostaje `None`. Kopia sprzed
instalacji: `config/backup_2026-10-09`. Dzień 2026-10-08 zbudowano pod starymi
regułami i po instalacji nie jest przebudowywany, renderowany ani czytany od nowa.

Kontrole po instalacji - sha256 sześciu zainstalowanych plików (początek):

| plik | sha256 |
|---|---|
| `sofa_confidence_calibration.json` | `6cf282d9...` |
| `sofa_engine_constants.json` | `e2df9be7...` |
| `sofa_league_baselines.json` | `2622135a...` |
| `sofa_market_reliability.json` | `edf897a4...` |
| `tennis_rating.json` | `b064166f...` |
| `sofa_count_dispersion.json` | `5df196d5...` |

Szczegóły kroków: `RUNBOOK_INSTALL_2026-10-08.md`. Dowód z linii był dopasowany do
starych krzywych - pierwsze poranki (`refresh_line_evidence.py`) bywają zaszumione.
