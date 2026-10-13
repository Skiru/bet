# MAPPABLE_FAMILIES – próba E2E przed włączeniem (2026-10-13 wieczór, dzień 2026-10-14)

Warunek operatora (2026-10-13): `MAPPABLE_FAMILIES_FROM_UTC` – tak, ale dopiero
po pełnym dniu E2E w scratchu, z SAMPLES i mostem, po kuponie dnia.

## Werdykt

**NIE ROZSTRZYGNIĘTO – warunek operatora nie jest spełniony.** Pełnego dnia
2026-10-14 z mostem nie zbudowano. Pre-flight `ensure_bridge.py` o 20:38Z:
serwer i karta żywe, ale Sofascore odpowiedział
`403 {"reason": "challenge"}` (nieświeży x-captcha karty). Zgodnie z zasadą
„403 = zwolnij” próbę z mostem przerwano po tym jednym pytaniu: bez
przeładowywania karty i bez ponawiania. RESOLVE i SAMPLES dnia 10-14 nie
biegły.

W części, którą dało się zrobić bez mostu, **nic się nie zepsuło**: żaden etap
się nie wywrócił, zasada „odpowiedź tak/nie nie dodaje drugiego szczebla”
trzymała, nogi i kupon są identyczne on/off, a 12 sprawdzonych szczebli zgadza
się z surowym Superbetem. Jeśli operator uzna, że to wystarczy, przełącznik
można włączyć od następnego 00:00Z. Ryzyko, którego ta próba nie sprawdziła,
jest opisane w sekcji „Czego nie sprawdzono”.

## Co uruchomiono

- Worktree `main` @ `eb711213` w scratchu, w nim
  `MAPPABLE_FAMILIES_FROM_UTC = 2026-10-13 00:00Z` (tylko w worktree). Drugi
  worktree to ten sam commit z przełącznikiem `None`. Do obu skopiowano
  niezacommitowany `config/sofa_superbet_line_evidence.json` z `main`, więc
  config jest identyczny z produkcją (poza backupami).
- Bez mostu nie da się zrobić RESOLVE dnia 10-14, dlatego wzięto prawdziwe
  `01_board`, `02_fixtures`, `03_samples` i `08_confidence_sports` dnia
  **2026-10-13** (`runs/sofa/2026-10-13`, tylko odczyt). Na nich puszczono,
  osobno on i off: świeży OFFER
  (`--min-minutes-to-kickoff 20`, tylko mecze przed startem), SHEET,
  `run_confidence.py --runs-dir`, `build_coupon.py`. Katalogi:
  `data/e2e_2026-10-14/runs_1013_on`, `data/e2e_2026-10-14/runs_1013_off`.
  OFFER on i off biegły jeden po drugim w odstępie ok. 1 min, przy tych
  samych cenach.
- Zakres: 11 meczów (5 tenis, 6 piłka). Pozostałe 666 już się zaczęło.
- Do `runs/sofa` i `config/` w `main` nic nie zapisano.

## Wyniki

### Etapy (on / off)

| etap | on | off |
|---|---|---|
| OFFER | PARTIAL (normalny), 0 `fetch_errors`, 0 `price_collisions` | to samo |
| szczeble w `04_offer.json` | 910 | 836 |
| `unmapped_markets` | 2005 | 2060 |
| SHEET | OK, 1078 wierszy | OK, 990 wierszy |
| CONFIDENCE | OK, 71 nóg | OK, 71 nóg |
| COUPON_ASSEMBLY | OK, 163 pozycje | OK, 163 pozycje |

Żadnego tracebacka w żadnym logu.

### Szczeble dodane przez rodziny MAPPABLE (+74)

| rodzina | szczeble | dwustronne | uwagi |
|---|---|---|---|
| `handicap_games_won_set1` | 30 | 0 | jednostronne jak każdy handicap (każdy wybór to osobna propozycja OVER; tak samo zapisane są 1802 szczeble `handicap_games` w prawdziwym 04 z 10-13) |
| `handicap_games_won_set2` | 30 | 0 | j.w. |
| `both_over_goals_1h` | 5 | 5 | tak = OVER |
| `both_over_goals_2h` | 5 | 5 | |
| `goals_for` 0,5 | 2 | 2 | drabina strony zaczynała się od 1,5 (CD Tapatío, Brazylia (K)) |
| `goals_2h_for` 0,5 | 2 | 2 | j.w. |
| `goals_1h_for`, `sets_total` | 0 | – | każda odpowiedź trafiła na szczebel, który drabina już kwotuje |
| `both_over_saves(_1h)`, `handicap_corners_1h/2h` | 0 | – | nie było ich wśród 11 meczów |

### Drugi szczebel na tej samej linii

**0.** Klucz (rynek, podmiot, linia) w żadnym meczu nie występuje dwa razy. Na
żadnym szczeblu z wersji off cena się nie zmieniła i żaden nie zniknął.
Odpowiedzi tak/nie na szczeble, które drabina już ma (np. „Athletic Club MG
strzeli gola” 1,23/3,65 = `goals_for` 0,5 drabiny; „Zostanie rozegrany 3. set”
= `sets_total` 2,5 w 5 meczach tenisowych), zostały pominięte. Szczebel
drabiny został.

### SHEET

- +88 wierszy (2 kierunki na dwustronnym szczeblu, 1 na handicapie).
  Werdykty nowych: 75 BELOW_BAR, 11 LEAN, 2 VALUE (`goals_for` / `goals_2h_for`
  UNDER Brazylii; VALUE to selektor `06_coupon.json`, nie kupon).
- Na istniejących wierszach `p_central`, `forecast_p` i kurs bez zmian.
  Inne są tylko `ladder_centre` / `ladder_sigma` na 4 wierszach `goals_2h_for`
  1,5 (Tapatío, Brazylia): drabina z jednego szczebla ma teraz dwa, więc
  powstało dopasowanie drabiny. To liczba po stronie ceny i do pewności nie
  wchodzi.

### CONFIDENCE i kupon

- Nogi on = off: 71 = 71, te same klucze, pewności i kursy. `11_coupon.json`
  on i off różnią się tylko znacznikami czasu.
- Odmowy: +88, czyli dokładnie tyle, ile przybyło wierszy:
  - `NO_LINE_EVIDENCE` 11 → 91 (+80): 20 `both_over_goals_1h/2h` i 60
    handicapów setowych. Nie mają krzywej ani 50 rozliczonych linii w kubełku,
    zgodnie z `PIPELINE.md` §5;
  - `ODDS_TOO_LOW` 48 → 50 (+2): `goals_for` 0,5 OVER po 1,05 i 1,04;
  - `BELOW_CONFIDENCE_FLOOR` 772 → 778 (+6): pozostałe wiersze `goals_*_for`
    0,5 (p modelu 0,15–0,68 albo UNDER).
- `NOT_CALIBRATED`: 0 w obu (sporty mierzone są skopiowane, MAPPABLE ich nie
  dotyczy).
- **Nogi drukowane per rodzina: 0 on, 0 off.** Na tych 11 meczach żadna nowa
  rodzina nie dała nogi.

### Kontrola 12 szczebli wobec surowego Superbetu (`/v2/pl-PL/events/{id}`, 20:5xZ)

| # | Superbet: rynek / wybór / kurs | szczebel | ok |
|---|---|---|---|
| 1 | „Brazylia (K) strzeli gola” tak 1,04 / nie 8,7 | `goals_for` brazylia 0,5 O 1,04 U 8,7 | tak |
| 2 | „2.połowa - Brazylia (K) strzeli gola” 1,24 / 3,55 | `goals_2h_for` 0,5 O 1,24 U 3,55 | tak |
| 3 | „1.połowa - obie drużyny strzelą” (BRA-ARG) 5 / 1,13 | `both_over_goals_1h` O 5,0 U 1,13 | tak |
| 4 | „2.połowa - obie drużyny strzelą” (BRA-ARG) 3,65 / 1,23 | `both_over_goals_2h` O 3,65 U 1,23 | tak |
| 5 | „CD Tapatio strzeli gola” 1,05 / 7,8 | `goals_for` cd tapatio 0,5 O 1,05 U 7,8 | tak |
| 6 | „2.połowa - CD Tapatio strzeli gola” 1,29 / 3,25 | `goals_2h_for` 0,5 O 1,29 U 3,25 | tak |
| 7 | „1.połowa - obie drużyny strzelą” (Athletic-Londrina) 5,1 / 1,14 | `both_over_goals_1h` O 5,1 U 1,14 | tak |
| 8 | „1.połowa - Athletic Club MG strzeli gola” 1,92 / 1,76 | brak nowego szczebla; drabina `goals_1h_for` 0,5 1,92/1,76 | tak (bez duplikatu) |
| 9 | „Zostanie rozegrany 3. set” Tak 2,35 / Nie 1,52 (Boscardin Dias-Mena) | brak nowego; drabina `sets_total` 2,5 O 2,35 U 1,52 (tak = OVER, N − 0,5) | tak (bez duplikatu) |
| 10 | „1. set - handicap gemy” „Pedro Boscardin Dias (-1.5)” sbv `-1.5-1` 2,17 | `handicap_games_won_set1` pedro −1,5 2,17 | tak |
| 11 | ten sam rynek, „Facundo Mena (1.5)” sbv `-1.5-1` 1,6 | `handicap_games_won_set1` facundo +1,5 1,6 (linia z wyboru, nie z sbv) | tak |
| 12 | „2. set - handicap gemy” „Nicolas Kicker (-3.5)” sbv `3.5-2` 2,95 | `handicap_games_won_set2` kicker −3,5 2,95 | tak |

### Testy

`tests/sofa` w worktree z włączonym przełącznikiem: 4344 passed, 7 skipped,
1 failed. Padł tylko `test_the_switch_is_off_until_the_operator_sets_it`:
strażnik zakłada `None` i przy włączaniu trzeba go zmienić. Golden
`offer_mappable_off.json` jest liczony z jawnym `mappable_families=False`, więc
nie padł.

## Czego nie sprawdzono

1. **SAMPLES z mostem i oferta z włączonym przełącznikiem.** To jest
   właściwy warunek operatora. Na 11 meczach `metrics_from_offer` nie zażądał
   ani jednej dodatkowej metryki: brakujące próbki (`goals_1h_for`,
   `games_won_set1_for` itd.) budują już istniejące drabiny. Rodziny, których
   tu nie było, chcą `saves_for`, `saves_1h_for`, `corners_1h_for` i
   `corners_2h_for`. Wszystkie mają ekstraktor w `metrics.py` i czyta się je z
   tego samego `/event/{id}/statistics`, co mecz już pobiera, więc koszt mostu
   nie powinien wzrosnąć. To wniosek z kodu, nie pomiar.
2. **Skala dnia.** W nieodwzorowanych nazwach prawdziwego `04_offer.json` z
   10-13 (677 meczów) jest: 765 nazw „<drużyna> strzeli gola” (128 meczów),
   510 połówkowych (128), 256 połówkowych BTTS (128), 194 handicapów setowych
   (97 meczów), 96 „Zostanie rozegrany N. set” (96), 24 obron bramkarza (16)
   i 16 handicapów rzutów rożnych w połowie (8). Większość odpowiedzi na
   gole i sety trafia na szczebel drabiny i niczego nie dodaje. Na pełnym
   dniu szczebli przybędzie rzędu kilkuset, głównie z `NO_LINE_EVIDENCE`.
   Ile nóg wydrukuje się z `goals_*_for` 0,5 przy cenach z dnia, nie
   zmierzono.
3. `both_over_saves(_1h)`, `handicap_corners_1h/2h` i wypełnienie szczebla
   `sets_total` (gdy drabina nie ma N − 0,5) nie wystąpiły ani razu.
4. Próba była mała: 11 meczów (5 tenisowych z 10, które według Sofascore
   zaczynały się ponad 20 min po 20:40Z; reszta była już po starcie u
   Superbetu albo odpadła na progu).

## Co dalej

Powtórzyć dzień 2026-10-14 (albo 10-15) z mostem, kiedy karta zostanie
przeładowana ręcznie i `check_bridge.py` da OK, po kuponie dnia: `run_pipeline.py`
BOARD..COUPON w `SOFA_RUNS_DIR=data/e2e_2026-10-14/runs`, potem OFFER, SHEET,
CONFIDENCE i COUPON_ASSEMBLY off na tych samych próbkach. Worktree w scratchu
tej sesji przepadnie z sesją. Odtworzenie: `git worktree add` + jedna linia w
`src/bet/sofa/epochs.py`.
