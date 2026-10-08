# Runbook: instalacja czterech pakietów staged (2026-10-08 wieczór -> 2026-10-09 00:00Z)

Status: **próba zrobiona na kopii, nic nie zainstalowane w żywym `config/`** (`git status` czysty, sha256
żywych plików bez zmian po próbie). Operator dał "go": instalacja ok. 23:40Z 2026-10-08, przełączniki epok
od 2026-10-09 00:00Z. Poniżej scenariusz sprawdzony w próbie 2026-10-08 ~19:45-20:15Z (kopie w
`/private/tmp/claude-501/-Users-mkoziol-projects-bet/8b9b285e-d060-410f-b561-ac2f6537b588/scratchpad/p/`).
Pakiety: `COUNT_DISPERSION` + `PER_MARKET_K` (razem; kod wymusza parę) i `TENNIS_SCOPED_TABLE` (z V5
`tennis_rating.json`). `CARDS_CORRELATION` zostaje `None`.

## 0. Co sprawdzono (i czego nie)

Próba: kopia `config/` (r1/r2/r3) + kopia katalogu roboczego (`data/refit_2026-10-09/config` +
`fit_manifest.json`), `prepare_refit.py --config-dir <kopia> --scratch <kopia>` (`resolve_paths` /
`Paths` pozwalają na to, `check_scratch` pilnuje, że scratch nie leży w `config/` ani `runs/`),
`install --confirm` naprawdę wykonany na kopii.

| próba | wynik |
|---|---|
| r1: `backup` + `install --confirm --count-dispersion --tennis-rating --per-market-k` (CLI, jak w nocy) | exit 0, ~100 s; zmieniło się **5 plików**: `sofa_confidence_calibration.json`, `sofa_engine_constants.json`, `sofa_league_baselines.json`, `sofa_market_reliability.json`, `tennis_rating.json`; `sofa_count_dispersion.json` **bajt w bajt ten sam** co żywy (już leży w `config/`, nieaktywny); bez "operator keys carried" |
| r1: `restore --confirm --backup` | "5 file(s) rewritten, 18 already identical"; wszystkie 23 pliki == bajty żywego `config/` (`cmp`) |
| r1: ładowarki | `Calibration.load`, `count_dispersion.parse_table/load_table` (51 rynków), `tennis_rating.load_coefficients` (V5, `lp_t`, `tier_start`, cut 2026-10-01), `run_sheet.load_baselines/load_reliability/load_engine_constants`, `per_market_k.k_for_market` (shots_for 8, goals_for 15) - bez błędu |
| r2: instalacja z bramką `pytest tests/sofa` uruchomioną **na zainstalowanych plikach** (`SOFA_CONFIG_DIR`=kopia) | **bramka FAIL: 1 test** (sekcja 1; 3785 passed) -> instalator sam cofnął pliki, odmówił (`REFUSED: tests failed after install; config restored`); `cmp` == żywy |
| r3: bramka wymuszona na FAIL | to samo cofnięcie; po nim brak `install_manifest.json` |
| kopia repo + zainstalowany config + poprawka V5-testu (bez przełączników) | `pytest tests/sofa`: **3708 passed, 7 skipped** (76 s) - to jest dokładnie bramka prawdziwej instalacji |
| kopia repo + zainstalowany config + poprawka + przełączniki + poprawione testy (sekcja 4) | `pytest tests/sofa`: **3708 passed, 7 skipped**; `ruff` czysty na zmienionych plikach, `mypy --strict epochs.py` czysty, `check_test_registry.py`: 0 findings; `git apply --check` obu łatek na żywym repo: OK |

Uwaga o próbie: w CLI bramka testów chodzi na **żywym** `config/` (`run_tests()` -> `child_env()` zrzuca
`SOFA_CONFIG_DIR`), więc r1 zdał bramkę bez testowania zainstalowanych plików; dlatego r2 (kierowca Pythona
z własną bramką na zainstalowanych plikach) jest próbą, która coś mówi. W prawdziwej instalacji config żywy
= zainstalowany, więc bramka zachowa się jak r2.

Co zmieniło się w 5 plikach (r1, sha256 stare -> nowe, nowe == `outputs_sha256` z `fit_manifest.json`):

| plik | stare | nowe |
|---|---|---|
| `sofa_confidence_calibration.json` | `dc374940afee771b...` | `6cf282d94ae4f5ca...` (też `by_class`: tennis_team_cup / tennis_women / women; `by_market_direction` 97 -> 101 kubełków) |
| `sofa_engine_constants.json` | `a3cef50f4dd9e2ff...` | `e2df9be7325a9780...` (różni się `fitted_from` i `K_CENTRE.curve`; `value` 10, `by_sport` football 15 / tennis 5, `by_market.football` bez zmian) |
| `sofa_league_baselines.json` | `7f3c69b3c7492cec...` | `2622135aa64a4966...` |
| `sofa_market_reliability.json` | `32a627f531c658d0...` | `edf897a4a5ec5129...` |
| `tennis_rating.json` | `289d5e16dde25d78...` | `b064166f70ee2d59...` (V5: `lp_t` + `tier_start`) |

Bez zmian (bajt w bajt): `sofa_side_correlations.json` (null dla cards_points), `sofa_count_dispersion.json`,
`sofa_sport_confidence_calibration.json` i `.next.json`, `sofa_superbet_line_evidence.json`,
`sofa_tennis_tier_baselines.json`, `sofa_settleability.json` i reszta. **Cztery sporty mierzone: żadnej
zmiany** - ich krzywe, evidence i `.next.json` nietknięte; żaden moduł SPORT_CONFIDENCE / SHADOW / CS2 /
SPORT_IDENTITY nie czyta 5 podmienianych plików (grep po `src/` i `scripts/sofa/`: czytelnicy to
`confidence.py`, `run_sheet.py`, `tennis_rating.py`, `tennis_prior.py`, `per_market_k.py`,
`count_dispersion.py`, `derived.py`, `joint.py`, `build_coupon_pdf.py` (tylko mtime kalibracji) i skrypty
`fit_*`/`measure_*`/`calibrate_from_cache`/`prepare_refit`).

Czego **nie** próbowano: pełnego `run_pipeline` / `rebuild_day` / SHEET dnia 10-09 z nowymi plikami
(wymaga bridge i dnia; testy offline to pokrywają, wpływ na kupon niezmierzony), `refresh_line_evidence.py` na
nowych krzywych (15-20 min, DB), pętli przy prawdziwej podmianie (analiza z kodu, sekcja 8), `git commit`.

## 1. BLOKADA nr 1 (naprawić PRZED instalacją): test V5 tenisa

`tests/sofa/test_tennis_rating.py::test_the_checked_in_config_names_features_the_book_computes`
twierdzi `set(meta["features"]) <= set(FEATURES)`. V5 `tennis_rating.json` nazywa cechę `lp_t`, której nie ma
w `FEATURES` (jest w `ALL_FEATURES`, `src/bet/sofa/tennis_rating.py:101-103`; `FEATURES` celowo bez niej).
Z V5 w `config/` ten test pada, więc **prawdziwy `install` cofnąłby się sam** po bramce i nic by nie
zainstalował. Poprawka (łatka A, sekcja 3.1) jest niezależna od przełączników - test przechodzi i ze starym
configiem - więc idzie przed instalacją.

## 2. Odpowiedź: czy `install` przyjmie `sofa_engine_constants.json` z `K_CENTRE.by_market`?

**Tak, bez żadnego ruchu** - pod warunkiem, że pliki w `data/refit_2026-10-09/config/` nie są ręcznie
edytowane po `fit`. Z kodu (`scripts/sofa/prepare_refit.py`):

- `install` (l. 1798-1803) porównuje `fit_manifest.json["outputs_sha256"][name]` z sha256 pliku w
  **katalogu roboczym** `<scratch>/config/<name>` - **nie** z żywym `config/`. Manifest zapisał
  `sofa_engine_constants.json` = `e2df9be7...141c`; plik w katalogu roboczym ma dziś **to samo**
  (sprawdzone; r1 przeszedł). `fit` kopiował bazę ze staged configu (`--config-dir data/refit_2026-10-09_stage/config`),
  który **już miał** `K_CENTRE.by_market` (żywy `config/sofa_engine_constants.json` też ma je dziś, nieaktywne),
  a `fit_constants` je przeniósł (`by_market.football`: cards_points_for 25, fouls_total 2, shots_for 8,
  shots_total 5). Fit i manifest widzą ten sam plik. `base_config_dir` w manifeście (staged, nie `config/`)
  `install` w ogóle nie czyta - luka z raportu staged refitu (sekcja 3, ostatni punkt) nie istnieje.
- `--per-market-k` tylko sprawdza, że `K_CENTRE.by_market.football` jest w pliku roboczym
  (`_check_staged_by_market`, l. 1764) - jest.
- Żywy plik jest porównywany wyłącznie z **backupem** (l. 1808-1815): `backup` zrobiony tuż przed instalacją
  zawsze się zgodzi, dopóki nikt nie dotknie tych plików między `backup` a `install`.
- `install` kopiuje klucze operatora (`OPERATOR_KEYS`) z żywego `config/`; dziś zgadzają się z fitem.

Kiedy by odmówił: `... differs from what fit wrote - refit` (plik roboczy edytowany po `fit`) albo
`config/<f> changed since backup` (żywy plik zmieniony po backupie). Wtedy **nie edytować manifestu**: przy
pierwszym `fit --force` (~40 min, na kopii bazy `data/refit_2026-10-08/sofa_replay.db`, patrz CONFIG.md 7)
albo przywrócić plik roboczy do bajtów z manifestu; przy drugim nowy `backup` i ponowny `install`.
Uwaga: `install` nie sprawdza, czy żywy plik == `base_sha256` z manifestu (tylko backup); to przypadek, w
którym ktoś zmienił żywy plik po stagingu - sekcja 3.0 sprawdza to ręcznie.

## 3. Kolejność nocy (kopiuj-wklej, z katalogu repo)

Czasy: sprawdzenia ~23:15Z; instalacja ~23:40Z (trwa ~100 s: bramka testów 75-80 s); przełączniki i testy
przed 00:00Z (sama wartość `datetime(2026, 10, 9, 0, 0, tzinfo=UTC)` jest w stałych; przełącznik czyta zegar
budowy, więc kiedy wpiszesz, nie ma znaczenia, byle przed pierwszą budową 10-09).

### 3.0 Wstępne sprawdzenia
```bash
cd /Users/mkoziol/projects/bet
git status --short                      # czysto (albo tylko znane pliki dnia)
git rev-parse --short HEAD              # b8572f53 lub nowszy
ps aux | grep -E "run_pipeline|rebuild_day|build_coupon|run_confidence|prepare_refit|fit_" | grep -v grep   # nic
ls config/backup_2026-10-09 2>&1 | head -1          # ma NIE istnieć
shasum -a 256 config/sofa_confidence_calibration.json config/sofa_engine_constants.json \
  config/sofa_league_baselines.json config/sofa_market_reliability.json config/tennis_rating.json
# oczekiwane (stan 2026-10-08 20:05Z):
#  dc374940afee771b9fe6496ee64b55e566aacb856e9cfc0ebfd44bb6bc2ed04c  sofa_confidence_calibration
#  a3cef50f4dd9e2ffdc35cc337789aefcc2ab5b68c07d270d49ee5ea5a39ce461  sofa_engine_constants
#  7f3c69b3c7492cecf75dc8a33a4adcfef85f593fe78890de606beb96591c9fda  sofa_league_baselines
#  32a627f531c658d0727c1f4af580be6e983769d7212099335c57a0dead63e66e  sofa_market_reliability
#  289d5e16dde25d78bf733184a5abdad0df0d95d42557ff74671c89fadf8a9542  tennis_rating
# inna wartość = ktoś ruszył żywy config po stagingu: zatrzymać się i ustalić przed backupem
.venv/bin/python - <<'PY'
import json,hashlib
m=json.load(open("data/refit_2026-10-09/fit_manifest.json")); assert m["complete"]
for n,h in m["outputs_sha256"].items():
    assert hashlib.sha256(open(f"data/refit_2026-10-09/config/{n}","rb").read()).hexdigest()==h,n
print("fit_manifest OK (4 pliki fitu zgodne z manifestem)")
PY
PYTHONPATH=src:. .venv/bin/python scripts/sofa/day_status.py --date 2026-10-08   # pętle żyją, brak MISMATCH
```
Warunek dnia: 10-08 skończony. Po instalacji **żadnej** przebudowy / PDF / reads dla 10-08 (sekcja 6).

### 3.1 Łatka A (blokada nr 1) - osobny commit, przed backupem
```bash
git apply <<'PATCH'
--- a/tests/sofa/test_tennis_rating.py
+++ b/tests/sofa/test_tennis_rating.py
@@ -23,7 +23,7 @@
     PricedRung,
 )
 from bet.sofa.tennis_rating import (
-    FEATURES,
+    ALL_FEATURES,
     MIN_RATED,
     RATED_MARKETS,
     W_TENNIS_RATING,
@@ -189,7 +189,7 @@
     assert loaded is not None, "config/tennis_rating.json must be checked in"
     coefficients, meta = loaded
     assert set(coefficients) == {"ITF", "CH", "TOUR"}
-    assert set(meta["features"]) <= set(FEATURES)
+    assert set(meta["features"]) <= set(ALL_FEATURES)
     assert all(len(c) == len(meta["features"]) + 1 for c in coefficients.values())
     # Refit 2026-09-30 on the backfilled history (239k matches), cut before
     # the first day it prices. dhigh / dtour carry the tier gap one Elo pool
PATCH
.venv/bin/python -m pytest tests/sofa/test_tennis_rating.py -q
.venv/bin/python -m ruff check tests/sofa/test_tennis_rating.py
git add tests/sofa/test_tennis_rating.py && git commit -m "test(sofa): the checked-in tennis_rating may name lp_t (ALL_FEATURES), V5 install

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### 3.2 Backup (nazwa wg CONFIG.md: `config/backup_<data>`, data = `--date`)
```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date 2026-10-09 backup
# -> config/backup_2026-10-09/ (23 pliki + backup_manifest.json); exit 0; katalog już istnieje = odmowa
```
Baza (`--db`) nie jest potrzebna: `install` nie dotyka bazy (reguła "jedna kopia bazy na epokę" bez zmian,
`data/backup_2026-10-05/sofa.db`). `config/backup_*/` jest w `.gitignore`.

### 3.3 Instalacja (wszystkie flagi)
```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date 2026-10-09 \
  install --confirm --count-dispersion --tennis-rating --per-market-k 2>&1 | tee data/refit_2026-10-09/install_console.log
echo "exit=${PIPESTATUS[0]}"
```
Domyślne ścieżki: `--config-dir config`, `--scratch data/refit_2026-10-09`, backup `config/backup_2026-10-09`.
Oczekiwany wydruk: `installed sofa_engine_constants.json`, `..._league_baselines`, `..._market_reliability`,
`..._confidence_calibration`, `installed sofa_count_dispersion.json`, `installed tennis_rating.json`, potem
pytest (3708 passed) i `tests/sofa passed. Commit it as one epoch:`; exit 0; powstaje
`data/refit_2026-10-09/install_manifest.json`. Exit 2 = `REFUSED: ...` (nic nie zmienione albo już cofnięte).
Jeśli bramka padnie, instalator cofnie pliki sam (`restore ... only=`), `sofa_count_dispersion.json` byłby
usunięty tylko gdyby go nie było w backupie (jest, bajt w bajt).

### 3.4 Sprawdzenia po instalacji (tylko odczyt)
```bash
shasum -a 256 config/sofa_confidence_calibration.json config/sofa_engine_constants.json \
  config/sofa_league_baselines.json config/sofa_market_reliability.json config/tennis_rating.json config/sofa_count_dispersion.json
# oczekiwane nowe:
#  6cf282d94ae4f5ca019cdaf4d90eccdb63403f911a3b8b661066bfbb7ffffdd5  sofa_confidence_calibration
#  e2df9be7325a9780cafbd8111775f038a1c39a1fa50bb6e70c1965b13c20141c  sofa_engine_constants
#  2622135aa64a4966f7d6e37e878fa3f7bf3e0982e944ca6be269b0753729e701  sofa_league_baselines
#  edf897a4a5ec512996842b0f0f954b664757545829c47d230eeaad7b2cbf41b1  sofa_market_reliability
#  b064166f70ee2d592ca4500532cbb9293dd0aeb2db5019618173fbdbfe64fc30  tennis_rating
#  5df196d5db815486f364d525b9331e854d2b29784ce22fabc01597828f64ee58  sofa_count_dispersion (bez zmian)
for f in sofa_side_correlations sofa_sport_confidence_calibration sofa_sport_confidence_calibration.next \
         sofa_superbet_line_evidence sofa_tennis_tier_baselines sofa_settleability; do
  cmp -s config/$f.json config/backup_2026-10-09/$f.json && echo "same $f" || echo "CHANGED $f (nie powinno)"; done
PYTHONPATH=src:. .venv/bin/python - <<'PY'
import json
from bet.sofa.confidence import Calibration
from bet.sofa.count_dispersion import load_table
from bet.sofa.tennis_rating import load_coefficients
from bet.sofa.per_market_k import k_for_market
from bet.sofa.config import SofaConfig
from scripts.sofa import run_sheet as rs
Calibration.load(); print("count_dispersion rynków:", len(load_table().markets))
co, meta = load_coefficients(); assert meta["features"][0] == "lp_t" and "tier_start" in meta
e = rs.load_engine_constants(SofaConfig.from_env()); assert k_for_market(e, "football", "shots_for", 15.0) == 8.0
assert e["K_CENTRE"]["by_sport"] == {"football": 15.0, "tennis": 5.0}
print("kalibracja, dyspersja, V5, K per rynek: ładowarki OK")
PY
```
Admisje operatora (`admitted_player_markets`, `refused_markets`) i `by_class` (kobiece / puchary) idą z
instalacją (`install` bierze klucze operatora z żywego pliku); football/tenis `by_class` jest **przefitowany**
(inne bajty, ta sama struktura).

### 3.5 Commit configu (jak drukuje instalator; `config/backup_*` jest ignorowany)
```bash
git add config/sofa_engine_constants.json config/sofa_league_baselines.json config/sofa_market_reliability.json \
  config/sofa_confidence_calibration.json config/sofa_count_dispersion.json config/tennis_rating.json \
  data/refit_2026-10-09/install_manifest.json 2>/dev/null; git status --short
git commit -m "refit 2026-10-09: new comparability epoch (curves, constants, baselines, reliability, tennis V5)

Switches follow in their own commit, effective 2026-10-09 00:00Z.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
(`data/` zwykle jest poza gitem - jeśli `git add` na `install_manifest.json` odmówi, pominąć.)

## 4. Przełączniki epok i testy (łatka B) - przed 00:00Z, osobny commit

Które stałe dostają `datetime(2026, 10, 9, 0, 0, tzinfo=UTC)` (styl jak `READ_EVENTS_FROM_UTC`):
`COUNT_DISPERSION_FROM_UTC`, `PER_MARKET_K_FROM_UTC`, `TENNIS_SCOPED_TABLE_FROM_UTC`.
`CARDS_CORRELATION_FROM_UTC` zostaje `None` (jego krzywe joints nie są czytane przy
`DERIVED_CURVES_FROM_UTC=None`). Kod wymusza parę dyspersja + K (`epochs.require_k_with_dispersion`, wołane
w `run_sheet.py:1796`): obie stałe razem albo obie `None`.

Testy, które pękają po ustawieniu i jak poprawione w łatce B (11 testów w 4 plikach; dwunasty,
`test_tennis_rating`, poprawia łatka A):

| test | co z nim |
|---|---|
| `test_off_identical_head.py::test_every_switch_is_off` | przemianowany na `test_the_switches_are_where_the_install_put_them`: trzy stałe `== datetime(2026,10,9,0,0,tzinfo=UTC)`, `CARDS_CORRELATION_FROM_UTC is None` |
| `test_off_identical_head.py::test_off_is_identical_to_the_commit...` (golden) | **bez zmian i zielony**: goldeny idą przez `process_fixture` / `price_derived_rungs` z jawnymi argumentami, bez zegara; przełączniki czyta tylko `run_sheet` main i `rebuild_plan` |
| `test_count_dispersion.py::test_the_switch_is_off_until_the_operator_sets_it` | -> `test_the_switch_starts_with_the_2026_10_09_epoch` (pin wartości + granica -1 min / 10-08) |
| `test_count_dispersion.py::test_the_shipped_config_is_inert_and_parses` | usunięta asercja `is None` (reszta zostaje; `_doc` pliku nadal zawiera "INERT" - patrz uwaga niżej) |
| `test_count_dispersion.py::test_the_off_path_reads_no_config_and_opens_no_file`, `test_a_sheet_of_the_other_rule_is_re_priced_by_the_rebuild`, `test_the_two_football_switches_cannot_be_on_independently` | `monkeypatch.setattr(epochs, ..., None)` na początku (testy "wyłączone = bez zmian" dostają `None` jawnie, nie z kodu) |
| `test_per_market_k.py::test_the_switch_is_off` | -> `test_the_switch_starts_with_the_2026_10_09_epoch` |
| `test_per_market_k.py::test_the_shipped_file_keeps_its_old_keys` | asercja `is None` zastąpiona pinem `by_market.football.shots_for == 8.0` |
| `test_per_market_k.py::test_rebuild_reruns_sheet_on_a_sheet_of_the_other_rule` | `monkeypatch` -> `None` przed gałęzią "off" |
| `test_tennis_scoped_table.py::test_off_by_default_in_the_epochs` | -> `test_the_switch_starts_with_the_2026_10_09_epoch` |
| `test_tennis_scoped_table.py::test_a_sheet_of_the_other_table_rule_is_re_priced_by_the_rebuild` | `monkeypatch` -> `None` przed gałęzią "off" |
| `test_cards_correlation.py::test_the_switch_is_off...` | **bez zmian** (CARDS zostaje `None`) |

Zasada: testy "off = identyczne" nie zależą od zegara, tylko ustawiają przełącznik jawnie; test pinujący
wartość przełącznika nazywa jego datę. Niezmierzone: zachowanie pakietu testów przy zegarze rzeczywistym
po 00:00Z (próba szła o 20:00Z; `SOFA_NOW` nie nadaje się do symulacji - `run_pipeline` go odrzuca i pada
~20 niezwiązanych testów, także bez łatki). Przejrzane z kodu: przełączniki czyta tylko `run_sheet` main i
`rebuild_plan`, a testy "off" ustawiają je jawnie; po 00:00Z uruchom `pytest tests/sofa` jeszcze raz.

```bash
git apply <<'PATCH'
--- a/src/bet/sofa/epochs.py
+++ b/src/bet/sofa/epochs.py
@@ -242,7 +242,7 @@
 # priced this way carry `dispersion_rule` (COUNT_DISPERSION), so a rebuild
 # re-runs SHEET on a sheet of the other rule (rebuild_plan).
 COUNT_DISPERSION_DATE = "2026-10-09"
-COUNT_DISPERSION_FROM_UTC: datetime | None = None
+COUNT_DISPERSION_FROM_UTC: datetime | None = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
 COUNT_DISPERSION = "count_dispersion"
 
 
@@ -273,7 +273,7 @@
 # the build clock; tennis rows priced this way carry `tennis_table_rule`
 # (TENNIS_SCOPED_TABLE), so a rebuild re-runs SHEET on a sheet of the other rule.
 TENNIS_SCOPED_TABLE_DATE = "2026-10-09"
-TENNIS_SCOPED_TABLE_FROM_UTC: datetime | None = None
+TENNIS_SCOPED_TABLE_FROM_UTC: datetime | None = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
 TENNIS_SCOPED_TABLE = "scoped_table"
 
 
@@ -340,7 +340,7 @@
 # Rows priced this way carry `k_rule` (PER_MARKET_K), so a rebuild re-runs
 # SHEET on a sheet of the other rule.
 PER_MARKET_K_DATE = "2026-10-09"
-PER_MARKET_K_FROM_UTC: datetime | None = None
+PER_MARKET_K_FROM_UTC: datetime | None = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
 PER_MARKET_K = "per_market_k"
 
 
--- a/tests/sofa/test_off_identical_head.py
+++ b/tests/sofa/test_off_identical_head.py
@@ -10,6 +10,7 @@
 from __future__ import annotations
 
 import json
+from datetime import UTC, datetime
 
 from bet.sofa import epochs
 from tests.sofa.off_scenarios import GOLDEN_DIR, all_scenarios
@@ -17,10 +18,12 @@
 GOLDEN = GOLDEN_DIR / "off_identical_head.json"
 
 
-def test_every_switch_is_off() -> None:
-    for name in ("COUNT_DISPERSION", "TENNIS_SCOPED_TABLE", "CARDS_CORRELATION",
-                 "PER_MARKET_K"):
-        assert getattr(epochs, f"{name}_FROM_UTC") is None, name
+def test_the_switches_are_where_the_install_put_them() -> None:
+    start = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
+    for name in ("COUNT_DISPERSION", "TENNIS_SCOPED_TABLE", "PER_MARKET_K"):
+        assert getattr(epochs, f"{name}_FROM_UTC") == start, name
+    # CARDS_CORRELATION stays off: its joints' curves are not read
+    assert epochs.CARDS_CORRELATION_FROM_UTC is None
 
 
 def test_off_is_identical_to_the_commit_the_change_set_started_from() -> None:
--- a/tests/sofa/test_count_dispersion.py
+++ b/tests/sofa/test_count_dispersion.py
@@ -68,11 +68,13 @@
         ]
 
 
-def test_the_switch_is_off_until_the_operator_sets_it() -> None:
-    assert epochs.COUNT_DISPERSION_FROM_UTC is None
-    assert not epochs.count_dispersion_enabled("2026-10-09")
+def test_the_switch_starts_with_the_2026_10_09_epoch() -> None:
+    start = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
+    assert epochs.COUNT_DISPERSION_FROM_UTC == start
+    assert not epochs.count_dispersion_enabled("2026-10-08", start)
     assert not epochs.count_dispersion_enabled(
-        "2030-01-01", datetime(2030, 1, 1, tzinfo=UTC))
+        "2026-10-09", start - timedelta(minutes=1))
+    assert epochs.count_dispersion_enabled("2026-10-09", start)
 
 
 def test_the_switch_reads_the_day_and_the_build_clock(
@@ -156,7 +158,6 @@
     assert t.read("football", "shots_total", None) is not None
     assert t.read("football", "shots_total", None).family == "normal"  # type: ignore[union-attr]
     assert t.read("football", "goals_for", None).family == "nb"  # type: ignore[union-attr]
-    assert epochs.COUNT_DISPERSION_FROM_UTC is None  # nothing reads it yet
 
 
 def test_pooled_alpha_is_the_market_alpha_with_no_cases_and_the_leagues_with_many() -> None:
@@ -182,7 +183,7 @@
         return real_read_text(self, *a, **k)
 
     monkeypatch.setattr(Path, "read_text", spy)
-    assert epochs.COUNT_DISPERSION_FROM_UTC is None
+    monkeypatch.setattr(epochs, "COUNT_DISPERSION_FROM_UTC", None)
     assert not epochs.count_dispersion_enabled("2026-10-09")
     monkeypatch.setattr(cc, "COUNT_DISPERSION", None)
     for _ in range(50):
@@ -254,6 +255,7 @@
         [{"dispersion_rule": epochs.COUNT_DISPERSION}, {}])
     assert epochs.sheet_count_dispersion([])
     # off: a sheet without the rule is kept (nothing changes today)
+    monkeypatch.setattr(epochs, "COUNT_DISPERSION_FROM_UTC", None)
     off = rp.build_plan(rp.DayState("2026-10-09", at, limit, sheet_dispersion=False))
     assert "SHEET" not in off.names()
     monkeypatch.setattr(epochs, "COUNT_DISPERSION_FROM_UTC",
@@ -440,6 +442,8 @@
 ) -> None:
     at = datetime(2026, 10, 9, 7, 0, tzinfo=UTC)
     day = "2026-10-09"
+    monkeypatch.setattr(epochs, "COUNT_DISPERSION_FROM_UTC", None)
+    monkeypatch.setattr(epochs, "PER_MARKET_K_FROM_UTC", None)
     epochs.require_k_with_dispersion(day, at)  # both off: fine
     monkeypatch.setattr(epochs, "COUNT_DISPERSION_FROM_UTC",
                         datetime(2026, 10, 9, tzinfo=UTC))
--- a/tests/sofa/test_per_market_k.py
+++ b/tests/sofa/test_per_market_k.py
@@ -29,11 +29,13 @@
                            "by_market": {"football": {"shots_total": 5.0}}}}
 
 
-def test_the_switch_is_off() -> None:
-    assert epochs.PER_MARKET_K_FROM_UTC is None
-    assert not epochs.per_market_k_enabled("2026-10-09")
+def test_the_switch_starts_with_the_2026_10_09_epoch() -> None:
+    start = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
+    assert epochs.PER_MARKET_K_FROM_UTC == start
+    assert not epochs.per_market_k_enabled("2026-10-08", start)
     assert not epochs.per_market_k_enabled(
-        "2030-01-01", datetime(2030, 1, 1, tzinfo=UTC))
+        "2026-10-09", start - timedelta(minutes=1))
+    assert epochs.per_market_k_enabled("2026-10-09", start)
 
 
 def test_the_shipped_file_keeps_its_old_keys() -> None:
@@ -41,8 +43,7 @@
     assert k["by_sport"]["football"] == 15.0
     assert k["value"] == 10.0
     assert "curve" in k and k["status"] == "FITTED"
-    # a staged by_market table is inert while the switch is None
-    assert epochs.PER_MARKET_K_FROM_UTC is None
+    assert k["by_market"]["football"]["shots_for"] == 8.0  # live from the switch
 
 
 def test_k_for_market_reads_only_football_and_only_listed_markets() -> None:
@@ -93,6 +94,7 @@
     assert epochs.sheet_per_market_k([{"k_rule": epochs.PER_MARKET_K}])
     assert not epochs.sheet_per_market_k([{"k_rule": epochs.PER_MARKET_K}, {}])
     assert epochs.sheet_per_market_k([])
+    monkeypatch.setattr(epochs, "PER_MARKET_K_FROM_UTC", None)
     assert "SHEET" not in rp.build_plan(
         rp.DayState("2026-10-09", at, limit, sheet_k=False)).names()
     monkeypatch.setattr(epochs, "PER_MARKET_K_FROM_UTC",
--- a/tests/sofa/test_tennis_scoped_table.py
+++ b/tests/sofa/test_tennis_scoped_table.py
@@ -143,11 +143,13 @@
     assert "lp_t" not in model.book.features(1, 2, "hard", cut)
 
 
-def test_off_by_default_in_the_epochs() -> None:
-    assert epochs.TENNIS_SCOPED_TABLE_FROM_UTC is None
-    assert not epochs.tennis_scoped_table_enabled("2026-10-09")
+def test_the_switch_starts_with_the_2026_10_09_epoch() -> None:
+    start = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
+    assert epochs.TENNIS_SCOPED_TABLE_FROM_UTC == start
+    assert not epochs.tennis_scoped_table_enabled("2026-10-08", start)
     assert not epochs.tennis_scoped_table_enabled(
-        "2026-10-30", datetime(2026, 10, 30, tzinfo=UTC))
+        "2026-10-09", start - timedelta(minutes=1))
+    assert epochs.tennis_scoped_table_enabled("2026-10-09", start)
 
 
 def test_the_pooled_forecast_names_its_scope() -> None:
@@ -491,6 +493,7 @@
     assert epochs.sheet_tennis_scoped_table([])
     at = datetime(2026, 10, 9, 7, 0, tzinfo=UTC)
     limit = timedelta(minutes=45)
+    monkeypatch.setattr(epochs, "TENNIS_SCOPED_TABLE_FROM_UTC", None)
     off = rp.build_plan(rp.DayState("2026-10-09", at, limit, sheet_tennis_table=False))
     assert "SHEET" not in off.names()  # switch off: nothing changes today
     monkeypatch.setattr(epochs, "TENNIS_SCOPED_TABLE_FROM_UTC",
PATCH
.venv/bin/python -m pytest tests/sofa -q            # 3708 passed, 7 skipped (~75 s)
.venv/bin/python -m ruff check src/bet/sofa scripts/sofa
.venv/bin/python -m mypy --strict --no-incremental src/bet/sofa scripts/sofa
PYTHONPATH=src:. .venv/bin/python scripts/sofa/check_test_registry.py
git add src/bet/sofa/epochs.py tests/sofa && git commit -m "feat(sofa): COUNT_DISPERSION, PER_MARKET_K, TENNIS_SCOPED_TABLE effective 2026-10-09 00:00Z

CARDS_CORRELATION stays off (its joints' curves are not read).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
(`ruff` / `mypy` na całym `src/bet/sofa scripts/sofa`: w próbie sprawdzone tylko zmienione pliki; reszta jak
w HEAD - jeśli coś było czerwone przed, nie jest to tej łatki.) Komentarze w `epochs.py` ("None = waiting for
the operator") po ustawieniu są nieaktualne - dopisać w tym samym commicie, nie zmieniają zachowania.

Dokumentacja (CLAUDE.md "Changing the pipeline" 6): `CLAUDE.md` (sekcja "Model packages" - dziś nie wspomina
tych czterech pakietów; dopisać dyspersję, K per rynek, V5/tabelę scoped, "CARDS_CORRELATION off";
"Comparability": nowa epoka od 2026-10-09 00:00Z), `docs/sofa/CONFIG.md` 7.6 (statusy "bezczynny" ->
"od 2026-10-09 00:00Z"), raport nocy w `docs/sofa/history/`.

## 5. Rano 2026-10-09: line evidence i pierwsza budowa

`refresh_line_evidence.py --before 2026-10-09` **musi** być po instalacji i **przed pierwszą budową 10-09**,
a z natury rzeczy po rozliczeniu D-1 = 10-08 (potrzebuje `07_settled.json` 10-08 i sport settled; o 23:40Z
10-08 jeszcze nie ma rozliczenia - nie da się go zrobić w nocy z pełnymi danymi). To zwykła poranna kolejność
(`/sofa-day`): `ensure_bridge` -> SETTLE / SHADOW_SETTLE / CS2_SETTLE 10-08 -> `audit_settle_identity` ->
`record_results` -> **`refresh_line_evidence.py --before 2026-10-09`** (~15-20 min) -> `run_pipeline --date 2026-10-09`.
- Skutek: `fit_line_evidence` czyta football/tenis przez krzywe **zainstalowane teraz** ("offset jest
  twierdzeniem o tej krzywej, refit krzywych go odświeża"), więc po instalacji odświeża się z nowymi krzywymi -
  to jest zamierzone, wymaga tylko właściwej kolejności.
- Gdyby pętla poranna puściła go **po** instalacji: dokładnie to, co trzeba. Gdyby poszedł **przed** instalacją
  (np. 00:05Z): offsety/pasma cenowe football/tenis byłyby zmierzone względem starych krzywych - powtórzyć po
  instalacji. Gdyby pierwsza budowa 10-09 poszła **przed** odświeżeniem: użyje evidence z 10-08 rano
  (stare krzywe) na nowych krzywych - przebudować po odświeżeniu (`rebuild_day.py`).
- Zastrzeżenie (podejrzenie, niezmierzone): football/tenis wiersze `sheet_days` 10-05..10-08 mają `p_central`
  starego estymatora (stara dyspersja, K, tabela tenisa), a evidence przepuszcza je przez **nowe** krzywe; offset
  to więc para "stare p -> nowa krzywa". Evidence tylko obniża, ale operator powinien wiedzieć, że przez kilka
  dni offsety football/tenis są zmierzone na niezgodnej parze. Do zmierzenia: `refresh_line_evidence.py
  --before 2026-10-09 --dry-run` i porównanie offsetów z plikiem z 10-08.
- Po pierwszej budowie 10-09: wiersze `05_sheet.json` niosą znaczniki reguł:
```bash
.venv/bin/python - <<'PY'
import json,collections
rows=json.load(open("runs/sofa/2026-10-09/05_sheet.json"))   # lista wierszy
c=collections.Counter((r.get("sport"),r.get("dispersion_rule"),r.get("k_rule"),r.get("tennis_table_rule"),r.get("cards_rule")) for r in rows)
for k,v in sorted(c.items(),key=str): print(v,k)
PY
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date 2026-10-09 --dry-run   # nie planuje SHEET
```
  Oczekiwane (`run_sheet.py:1861-1879`: znaczniki idą na **każdy** wiersz dnia, nie tylko na rynki z K per
  rynek): każdy wiersz `dispersion_rule=count_dispersion` i `k_rule=per_market_k`, wiersze tenisa
  dodatkowo `tennis_table_rule=scoped_table`, `cards_rule` = None wszędzie. `run_sheet` exit 2 = para
  przełączników niezgodna (`require_k_with_dispersion`).
- Ledger: nowa epoka (od 2026-10-09 00:00Z) - `record_results` / `audit_ledger` trzymają ją w osobnej grupie,
  nigdy nie sumować z poprzednimi.

## 6. Okno 23:40Z - 00:00Z i dzień 10-08 po instalacji

- Po instalacji (przed łatką B) nowe pliki są już aktywne dla wszystkiego, co je czyta, a przełączniki
  jeszcze `None`: V5 tenisa zmienia `p` tenisa **także przy wyłączonym przełączniku** (CONFIG.md 7.6), nowe
  krzywe / bazy / reliability zmieniają CONFIDENCE i SHEET. Dlatego **dzień 10-08 musi być zamknięty** przed
  instalacją: żadnej przebudowy, `run_confidence`, `build_coupon`, nowych reads dla 10-08.
- `build_coupon_pdf.py` odmówi (`STALE_CONFIDENCE`: `08_confidence.json` starszy od mtime
  `sofa_confidence_calibration.json`, `build_coupon_pdf.py:273-280`) przerenderowania PDF 10-08 po instalacji,
  dopóki nie przejdzie `run_confidence.py` - a ten przeliczyłby 10-08 nowymi krzywymi (mieszany dzień). Nie
  robić; wydrukowane nogi 10-08 i tak są zablokowane (`12_printed.json`). `capture_closing` czyta tylko
  `11_coupon.json`.
- Rozliczenie 10-08 (SETTLE, `sofa_settled_row`) nie czyta tych plików (ocenia wynik, nie p).

## 7. Odwrót (rollback)

Plik `config/backup_2026-10-09/` = stan sprzed instalacji (23 pliki + `backup_manifest.json` z sha256).

**A. Zaraz po instalacji (przed porannym `refresh_line_evidence` i przed pierwszą budową 10-09)** - cały config:
```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date 2026-10-09 restore --confirm --backup config/backup_2026-10-09
for f in config/*.json; do cmp -s $f config/backup_2026-10-09/$(basename $f) || echo "DIFF $f"; done
git revert --no-edit SHA_COMMITU_CONFIGU   # jeśli już był commit (SHA z git log); tak samo SHA łatki B, jeśli była
.venv/bin/python -m pytest tests/sofa -q
```
**B. Po porannym `refresh_line_evidence` / budowie 10-09: NIE używać `restore`.** `restore` przywraca
**wszystkie** pliki z manifestu backupu, a więc cofnąłby też `sofa_superbet_line_evidence.json` (przepisywany
codziennie) i `.next.json` do stanu z 23:40Z. Zamiast tego tylko 5 plików + przełączniki:
```bash
for f in sofa_confidence_calibration sofa_engine_constants sofa_league_baselines sofa_market_reliability tennis_rating; do
  cp -p config/backup_2026-10-09/$f.json config/$f.json; done
git revert --no-edit SHA_LATKI_B ; git revert --no-edit SHA_COMMITU_CONFIGU   # SHA z git log; przełączniki z powrotem na None
.venv/bin/python -m pytest tests/sofa -q
PYTHONPATH=src:. .venv/bin/python scripts/sofa/refresh_line_evidence.py --before 2026-10-09   # evidence znów względem starych krzywych
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date 2026-10-09               # SHEET wykryje regułę i się przeliczy
```
`sofa_count_dispersion.json` zostaje (bajt w bajt ten sam, nieaktywny przy `None`). Przełączniki
`COUNT_DISPERSION` i `PER_MARKET_K` tylko parą (inaczej `run_sheet` exit 2).

## 8. Pętle dzienne a podmiana configu

Żyją (stan 2026-10-08 ~20:05Z): `cs2_daily.py --date 2026-10-08 --chain` (pid 21930), `shadow_daily.py --date
2026-10-08 --chain` (25350), `capture_closing.py --date 2026-10-08 --loop` (25972). Wniosek z kodu:
**podmiana ich nie rusza**.
- `shadow_daily` / `cs2_daily` spawnują świeżo: `run_pipeline.py --only SHADOW | SHADOW_SETTLE | CS2 | CS2_SETTLE`,
  `run_sport_identity.py`, `settle_cs2.py --sweep`, `record_results.py`, `audit_shadow.py`, `audit_cs2.py`.
  Moduły (`run_shadow`, `run_cs2`, `settle_shadow`, `settle_cs2`, `run_sport_identity`, `shadow`, `cs2`,
  `sport_identity`, `settle_identity`) nie importują ani nie czytają: `sofa_engine_constants`,
  `sofa_league_baselines`, `sofa_market_reliability`, `sofa_confidence_calibration`, `tennis_rating`,
  `sofa_count_dispersion` (grep po `src/` i `scripts/sofa/`).
- `capture_closing` to jeden długi proces (kod już zaimportowany, więc edycja `epochs.py` go nie dotyka);
  importuje z `confidence.py` tylko `coupon_artifact`, `is_sheet_sport`, `printed_*` (czyta `11_coupon.json`);
  `confidence.py` przy imporcie czyta tylko `sofa_women_competitions.json` (nietknięty), krzywą dopiero w
  `Calibration.load()`, którego pętle nie wołają.
- Zapisy `install` idą przez `write_bytes_atomic` (plik tymczasowy + `os.replace`): czytelnik widzi plik w całości,
  starą albo nową wersję. Podmiana 5 plików nie jest atomowa **między** plikami (kilka sekund), ale czytają je
  tylko SHEET / CONFIDENCE / PDF (patrz wyżej), których o tej porze nikt nie uruchamia - dlatego warunek
  z 3.0 (żadnych `run_pipeline` / `rebuild_day`, brak procesów).
- Nocne pętle 10-09 startują po 00:00Z z nowym kodem (`epochs.py` z łatki B), ale ich kroki z `epochs`
  nie czytają żadnego z trzech przełączników.

## 9. Co może zablokować noc (lista)

1. Test V5 (sekcja 1) - bez łatki A bramka cofnie instalację. **Pewne, wykryte w próbie.**
2. Ktokolwiek edytuje plik w `data/refit_2026-10-09/config/` po `fit` -> `differs from what fit wrote`.
3. Zmiana któregokolwiek z 5 plików w `config/` między `backup` a `install` -> `changed since backup`.
4. `config/backup_2026-10-09` już istnieje -> `backup` odmawia (zmienić `--date` lub katalog; nazwy nie nadpisywać).
5. Czerwony inny test z `tests/sofa` w chwili instalacji (z próby: poza V5 wszystkie 3785 zielone).
6. Proces trzymający bazę / uruchomiony `rebuild_day` w oknie (nie blokuje instalatora, ale miesza dzień).
7. Przełączniki wpisane bez pary (sekcja 4) albo przed instalacją plików -> SHEET odmawia (exit 2).
