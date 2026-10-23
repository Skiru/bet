# Refit krzywych piłki / tenisa na pełniejszej historii - 2026-10-22/23 (NIE zainstalowano)

Zgoda operatora: 2026-10-22 ~21:30Z - refit i instalacja krzywych tam, gdzie
pomiar pokazuje poprawę (przedział ogółem bez zera, nie gorzej na nogach
>= 0,70 ani w żadnej dużej rodzinie). **Warunek nie jest spełniony - nic nie
zostało zainstalowane ani wystawione jako `.next.json`.** `config/`
nietknięty; 10-22, 10-23 i 10-24 czytają krzywe z refitu 2026-10-17 (+ krzywe
per linia z 10-18). Żadnej nowej epoki w księdze.

## Dopasowanie (kopia bazy, bez sieci)

```
sqlite3 data/sofa.db "VACUUM INTO 'data/refit_2026-10-22c/fb.db'"     # 7 min, 51 GB
# config_in = migawka config/*.json z 21:30Z
data/refit_2026-10-22c/chain.sh:
  prepare_refit.py --date 2026-10-23 --db-path $R/fb.db --scratch $R/ft --config-dir $R/config_in \
    rebuild-cache-rows --confirm --without-db-backup --with-halves --player-starts-only \
    --derived cards_points,goals,corners,shots_on_target --count-dispersion --cards-correlation \
    --per-market-k --tennis-scoped-table --football-rating --rated-scope --venue-prior --game-state \
    --rating-weight --season-phase --opponent-correction --tennis-set-ratings --cup-strength \
    --sample-cup-strength --tennis-sample-scope --goals-stretch --count-stretch --player-stretch \
    --closeness-stretch --player-coverage
  fit_confidence.py --db-path $R/fb.db --out $R/cand/full.json            # kopia zainstalowanego pliku
  fit_holdout.py --cut 2026-10-18 -- --db-path $R/fb.db --out $R/cand/holdout.json
```

- Flagi = `fitted_from.replay_rules.flags` zainstalowanych krzywych (10-16b +
  trzy stretche) **plus** `--closeness-stretch --player-coverage`: oba
  przełączniki są włączone od 10-21, a `prepare_refit.py install` odmawia
  replayu bez nich (`REPLAYABLE_SWITCHES`). Nigdy `--tennis-serve-markets` /
  `--tennis-aces-opponent`. Sędzia i udział zawodnika nadal niereplayowalne
  (krzywe tych rynków na centrach bez nich - jak dotąd).
- Replay: 1 302 366 meczów, 127,0 mln wierszy (10-17: 1 282 317 / 121,9 mln) -
  backfill dołożył do replayu tylko ~20 tys. meczów (+1,6%). 16 553 s.
- Fit tylko piłki nie istnieje w narzędziach (`calibrate_from_cache` i
  `fit_confidence` nie mają filtra sportu) - dopasowano oba sporty; historia
  tenisa w kopii jest niepełna (backfill tenisa trwał tej nocy).
- **Znalezisko (do utwardzenia):** `fit_confidence` czyta wszystkie wiersze
  `sofa_settled_row`, także żywe. Rynki, których replay nie wycenia (tenis
  serwis / asy i podwójne błędy w secie / tiebreaki), dostają krzywe wyłącznie
  z naszych rozliczonych dni - wbrew zasadzie "krzywe z historii, nasze dni to
  audyt". Ten refit dodałby nowe takie krzywe (`serve_points_total`,
  `serve_points_set1/2_for`, `double_faults_set1/2_for|OVER`...). W kandydacie
  te klucze zamrożono na wartości zainstalowane
  (`data/refit_2026-10-22c/freeze_live_only.py`, 59 kluczy w `full`, 51 w
  `holdout`; lista w `fitted_from.live_only_keys_frozen_to_installed`). Klucze
  te są w pliku zainstalowanym od wcześniejszych refitów z tego samego powodu.
- Krzywe per linia (`by_market_direction_line`) dopasowuje ten sam
  `fit_confidence` z tych samych wierszy - refitowane razem (43 z 76 kluczy
  bajt w bajt bez zmian), oba ramiona pomiaru czytają swoje krzywe per linia.
  Osobnego refitu nie potrzebują.

## Pomiar (`data/refit_2026-10-22c/measure_swap.py`)

A = zainstalowana krzywa, B = kandydat dopasowany bez meczów od 10-18 i bez
żywych wierszy od 10-18 (`cand/holdout.json`; ta sama procedura co `full`).
Pewność = `Calibration.realised` (lo95; klasa meczu, linia, K13 / K13b, bez
line evidence). Log loss pewności, B - A (x1e-4) na wierszach czytanych przez
oba ramiona; luka = realizacja - pewność na nogach >= 0,70 każdego ramienia;
95%, bootstrap Poissona po meczach (1000).

**Holdout historii** - mecze 10-18..10-22 (poza próbą obu krzywych; A do
10-16):

| zakres | wiersze / mecze | log loss B - A | >= 0,70: A | >= 0,70: B |
|---|---|---|---|---|
| wszystkie | 360 465 / 1 712 | -0,4 [-1,2; +0,4] | 108 450, +0,26 pp [-0,14; +0,65] | 110 732, +0,31 pp [-0,10; +0,69] |
| piłka | 221 763 / 302 | -0,8 [-2,0; +0,5] | +0,23 pp | +0,24 pp |
| piłka mężczyźni | 206 576 / 263 | -0,3 [-1,3; +0,7] | +0,14 pp | +0,15 pp |
| piłka kobiety | 15 187 / 39 | -7,7 [-19,2; +5,4] | +1,55 pp | +1,64 pp |
| tenis | 138 702 / 1 410 | **+0,3 [+0,0; +0,7]** (gorzej) | +0,31 pp | +0,40 pp |
| tenis kobiety | 53 523 / 613 | **+1,2 [+0,5; +1,9]** (gorzej) | +0,68 pp | +0,73 pp |

Rodziny (n >= 300 przy >= 0,70): żadna nie lepsza i nie gorsza w kalibracji
z przedziałem poza zerem, poza drobnymi (`aces_for|OVER` B +2,68 pp vs A
+1,13). Log loss gorszy z przedziałem: `goal_kicks_for|UNDER` +1,7 [+0,2;
+3,3], `games_won_set1_for` OVER +0,9 [+0,3; +1,7] / UNDER +1,1 [+0,3; +1,8];
lepszy: `corners_2h_for|UNDER` -5,1 [-8,4; -2,2], `both_over_shots_on_target|UNDER`,
tenisowe asy. Piłka ma w oknie tylko 302 mecze ze statystykami - moc mała.

**Rozliczone linie Superbetu** (żywe wiersze z ceną, `gated` = pewność
>= 0,70 i x >= 0,90; grupy epok osobno). Poza próbą B tylko grupy od 10-18:

| grupa | sport | log loss B - A | luka gated A | luka gated B |
|---|---|---|---|---|
| 10-18 mieszany | piłka | -0,2 [-1,3; +0,8] | 19 226, -2,87 pp | 19 214, -2,84 pp |
| 10-18 mieszany | tenis | -0,9 [-1,8; +0,1] | -2,59 pp | -2,76 pp |
| od 10-19 | piłka | +1,2 [-0,3; +2,6] | 8 321, -1,01 pp | 8 317, -1,01 pp |
| od 10-19 | tenis | -0,7 [-1,4; -0,2] | -2,99 pp | -2,92 pp |
| 10-21 mieszany | piłka | -1,1 [-2,8; +0,5] | -1,03 pp | -0,98 pp |
| 10-21 mieszany | tenis | -0,9 [-1,7; -0,2] | -0,11 pp | +0,01 pp |

Grupy 10-13..10-17 (w próbie obu krzywych): różnice log loss -1,7..+2,1, luka
gated zmienia się o <= 0,33 pp, wszędzie w przedziale. 10-22 jeszcze nie
rozliczony. Pełne tabele: `data/refit_2026-10-22c/swap_holdout.md` / `.json`.

## Decyzja

Nie instalować. Holdout historii ogółem -0,4 [-1,2; +0,4] x1e-4 - przedział
obejmuje zero (piłka -0,8 [-2,0; +0,5]); tenis gorszy (+0,3 [+0,0; +0,7],
kobiety +1,2 [+0,5; +1,9]); kalibracja >= 0,70 bez zmian (+0,26 -> +0,31 pp).
Przyczyna: replay jest tylko o 1,6% meczów większy niż ten z 10-17, więc
kandydat to prawie ta sama krzywa (zmiany pewności rzędu 0,01).

## Instalacja (sprawdzona, nieużyta)

Krzywa piłki / tenisa obsługuje plik staged: `confidence.calibration_path_for`
czyta `config/sofa_confidence_calibration.next.json`, gdy dzień i zegar
budowy są >= jego `effective_from` (`run_confidence.py`, `fit_line_evidence.py`;
test `tests/sofa/test_player_starts_only.py`). `run_coupon.py` (selektor
VALUE, 06) czyta zawsze plik zainstalowany. Gdyby operator chciał mimo to:

```
.venv/bin/python -c "import json;p='data/refit_2026-10-22c/cand/full.json';d=json.load(open(p));d['effective_from']='2026-10-24T00:00:00Z';json.dump(d,open('config/sofa_confidence_calibration.next.json','w'),indent=1)"
.venv/bin/python -m pytest tests/sofa -q || rm config/sofa_confidence_calibration.next.json
```

(Uwaga: z `.next.json` obok `install_line_curves.py` odmawia; doinstalowania
krzywych nowych rynków do pliku głównego nie trafiłyby do `.next.json`.) Plus
grupa księgi "od 10-24" w `audit_ledger.EPOCH_GROUPS`.

## Pliki

`data/refit_2026-10-22c/`: `chain.sh`, `chain.log` (replay, oba fity),
`config_in/`, `ft/replay_rules.json`, `cand/full.json` (kandydat, zamrożone
klucze z żywych wierszy, `replay_rules` wpisane), `cand/holdout.json`,
`cand/*.raw.json` (przed zamrożeniem), `cache_markets.txt`, skrypty
`fit_holdout.py`, `freeze_live_only.py`, `measure_swap.py`, wyniki
`swap_holdout.{md,json}`. Kopia bazy `fb.db` usunięta po pomiarze. Nie
testowane: E2E na artefaktach dnia (niepotrzebne bez instalacji); bramki
(pytest / ruff / mypy) nie uruchamiane - nie zmieniono kodu.
