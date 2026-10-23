# Krzywe dopasowane wyłącznie z naszych rozliczonych dni - 2026-10-23

Przełącznik `epochs.LIVE_ONLY_CURVE_REFUSED_FROM_UTC` = **2026-10-24 00:00Z**
(zgoda operatora na poprawki 2026-10-23; nic, co zmienia druk, przed tą
chwilą). Grupa księgi: „od 10-24”. Bez refitu, bez zmiany pliku krzywych.

## Problem

Zasada (CLAUDE.md): krzywe dopasowuje się na **historii** zdarzeń i
statystyk, odtworzonej na stan sprzed każdego meczu; nasze rozliczone dni są
audytem krzywej, nigdy jej źródłem. `fit_confidence` czytał jednak wszystkie
wiersze `sofa_settled_row` - replay (`run_date = 'cache-calibration'`) i
wiersze SETTLE z naszych dni razem. Rynek, którego replay nie wycenia,
dostawał więc krzywą wyłącznie z naszych dni (znalezisko refitu 10-22,
`REFIT_PILKA_2026-10-22.md`).

## Pomiar (zadanie 1)

Plik czytany przez każdy dzień 10-13..10-23: `config/sofa_confidence_calibration.json`
(brak `.next.json` piłki / tenisa; `confidence.calibration_path_for`).
Obecne krzywe pochodzą z refitu 2026-10-17 na
`data/refit_2026-10-17/sofa_replay.db` (+ krzywe per linia z tej samej bazy,
+ krzywe dopasowane osobno). Poprawiony `fit_confidence` uruchomiony na tej
samej bazie (wynik w scratchu, plik zainstalowany nietknięty):

- **50 kluczy** odrzuconych jako „tylko nasze dni”; wszystkie są w pliku
  zainstalowanym, żaden nie jest krzywą dopasowaną osobno
  (`new_market_curves_fitted_from`);
- pozostałe 283 krzywe najwyższego poziomu odtworzone **bajt w bajt** - ta
  sama baza, ten sam kod poza nową regułą;
- krzywe per linia (`config/sofa_line_curves.json`, 33 klucze piłki) i klasy
  piłki kobiet: **żaden** klucz bez historii.

Wszystkie 50 to tenis:

| rodzina | klucze (mężczyźni) | `tennis_women` (thin) |
|---|---|---|
| `serve_points_for` / `_set1_for` / `_set2_for` / `_total` / `_set1_total` / `_set2_total` | 3 by_market, 1 kierunek, 11 thin | 6 |
| `aces_set1_for` / `aces_set2_for` / `aces_set1_total` / `aces_set2_total` | 2 by_market, 8 thin | 3 |
| `double_faults_set1_for` / `_set2_for` / `_set1_total` / `_set2_total` | 2 by_market, 6 thin | 4 |
| `tiebreaks_total` | 1 by_market, OVER (kierunek), UNDER (thin) | OVER (thin) |

Liczność: 100-1 167 wierszy na klucz, razem 15 029 (lista z `n` w
`config/sofa_live_only_curves.json`, pole `rows`). **Żaden z tych kluczy nie
ma kubełka >= 0,70** - krzywa sama nie mogła wydrukować nogi; działała jako
sufit (pewność < 0,70 -> BELOW_CONFIDENCE_FLOOR) albo jako kubełek thin
przycinający pulę `pooled:tennis`.

Nogi 2026-10-13..10-22 (`08_confidence.json` `legs` + `removed_by_reads`,
`11_coupon.json` pojedyncze i nogi builderów; źródło z `calibrated_on`):

- nogi przepuszczone (>= 0,70) i wydrukowane, które **czytały** jedną z 50
  krzywych: **0 / 0** (z 35 949 przepuszczonych, 37 362 wydrukowanych);
- nogi rynków tych kluczy w ogóle: 6 wydrukowanych `tiebreaks_total` UNDER
  (10-15: 3, 10-16: 3), wszystkie już ze ścieżki bez krzywej (`sb:tennis:...`,
  p powyżej sufitu krzywej) - przełącznik ich nie zmienia.

Wyników rozliczonych tych nóg nie używam jako argumentu (zasada: wynik to fakt
o dniu, nie o decyzji).

Replay odmów 10-21 / 10-22 (`08_refusals.json`, wiersze tych rynków, krzywa
zainstalowana vs bez kluczy, obecny plik line evidence - przybliżenie):
~500 wierszy dziennie zmienia odczyt (pula przycięta thin albo krzywa < 0,70
-> własne linie Superbetu albo NO_LINE_EVIDENCE), **0** zmienia
drukowalność (pewność >= 0,70 i x >= 0,90). Skutek dla druku od 10-24 jest
więc mały, a gdyby się pojawił - pochodzi z własnych rozliczonych linii
Superbetu (line evidence), tak jak dla każdego rynku bez krzywej.

## Poprawka narzędzia (zadanie 2) - działa od razu, nie zmienia druku

`scripts/sofa/fit_confidence.py` śledzi dla każdego klucza (rynek, kierunek,
thin, klasa, pula sportu, pula globalna, linia), czy dotarł do niego wiersz
replayu (`live_only_curves.REPLAY_RUN_DATE`). Klucz, do którego dotarły tylko
nasze wiersze, **nie dostaje krzywej** i trafia na listę `live_only_refused`
(w pliku wyjściowym i w JSON-ie na stdout; w trybach `--classes-only` /
`--line-curves-only` do `by_class_fitted_from` / `line_curves_fitted_from`).
Krzywa dopasowana osobno (własny skrypt na historii) przeniesiona przez
`carry_separately_fitted_curves` nie jest na liście. W kluczu z historią
wiersze z naszych dni dalej się liczą (osądzane jest tylko pochodzenie
klucza). Tabela bez kolumny `run_date` (ręczne fixture'y testów) liczy każdy
wiersz jako historię; prawdziwa tabela ma `run_date NOT NULL`.
`prepare_refit.py fit` woła ten sam `fit_confidence` - nic więcej do zmiany.

## Przełącznik dla zainstalowanych krzywych (zadanie 3)

`bet.sofa.live_only_curves`: lista 50 kluczy w
`config/sofa_live_only_curves.json` (osobny plik - plik krzywych nietknięty,
więc `build_coupon_pdf` nie uzna dzisiejszego CONFIDENCE za nieaktualne).
Od 2026-10-24 00:00Z (dzień i zegar budowy) `run_confidence.py` i
`fit_line_evidence.py` (baza dnia `--before`) czytają kalibrację bez tych
kluczy (`for_day` -> `strip`): klucz nie ma krzywej i **żadna pula go nie
zastępuje** (`Calibration.no_pool_keys`), więc czyta własne linie Superbetu
albo NO_LINE_EVIDENCE. Sufit rynków niezmierzonych (`unproven_ceiling`)
zostaje ten z pełnego pliku - inne nogi się nie ruszają. Dzień 10-23
(zbudowany wcześniej lub przebudowany później) czyta dokładnie to, co czytał.

## Testy i bramki

`tests/sofa/test_live_only_curves.py`: fit bez krzywej dla klucza tylko z
naszych dni (i lista), pule bez historii, linia bez historii, krzywa
osobna przeniesiona nie na liście, `strip` (brak krzywej i puli, inne klucze
bez zmian), przełącznik (10-23 bez zmian, 10-24 przed 00:00Z bez zmian, od
00:00Z zmienione), spójność listy z plikiem zainstalowanym.
`test_audit_2026_10_13.py`: grupa księgi „od 10-24”.

Rejestr testów (`check_test_registry.py`) przechowuje hipotezy
przedrejestrowane, nie pliki pytest - ta poprawka nie stawia hipotezy o
przewadze, wpisu nie dodano; rejestr przechodzi bez uwag.

## Nie zrobione / do decyzji

- Refit z nową regułą nie był uruchamiany na nowo; kandydat 10-22c zamrażał
  te klucze ręcznie (`freeze_live_only.py`) - przy instalacji refitu
  poprawiony `fit_confidence` robi to sam, a listę z pliku kandydata
  (`live_only_refused`) warto porównać z `config/sofa_live_only_curves.json`.
- Pule (`pooled_by_sport`) dalej mieszają replay z naszymi wierszami; klucze
  z historią także. To nie jest „krzywa tylko z naszych dni”, ale nasze dni
  nadal w nich ważą - osobne pytanie przed następnym refitem.
