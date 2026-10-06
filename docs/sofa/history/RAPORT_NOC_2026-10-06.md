# Raport nocny 2026-10-05/06: wszystkie sporty, odrzucenia, poprawki, test e2e

Zlecenie operatora (10-05 wieczorem): sprawdzić każdy sport — co było do zagrania i dlaczego nie trafiło na kupon. Zlokalizować błędy, poprawić je, przetestować i doprowadzić pozostałe sporty do poziomu tenisa i piłki. Jeden kupon, wiele sportów, bez wariantów. Propsy zawodników zostają wyłączone (decyzja z tego samego wieczoru).

## 1. Co było do zagrania 10-05 i dlaczego nie weszło

Liczby pochodzą z przebudowy 13:30Z. Każdy sport odtworzono offline według jego własnego zegara, a liczniki zgadzają się z artefaktem.

| sport | w ofercie | na kuponie | główna przyczyna | błąd czy reguła |
|---|---|---|---|---|
| piłka – reprezentacje | 8 meczów Ligi Narodów | 5 nóg (tylko Francja – Belgia) | `SAMPLE_CROSSES_SEASON`: próbka 10 meczów reprezentacji zawsze sięga dalej niż 180 dni. Odrzucono 157 nóg po wszystkich bramkach ceny i krzywej. | **błąd reguły**, poprawiony |
| hokej | 18 meczów | 8 nóg | 339 nóg z tercji `NOT_CALIBRATED` (krzywe z 3 rozliczonych dni, żaden kubeł nie miał 200 wierszy). 259 nóg liczonych jako `NOT_IDENTIFIED` to mecze już rozpoczęte. | **poprawione** (krzywe, licznik) |
| koszykówka | 20 meczów | 0 | Nic nie jest dopuszczone: na liniach Superbetu model obiecuje 0.75–0.78, a trafia 0.60–0.70 (`total|OVER` 403 wiersze: 0.754 wobec 0.623). Dodatkowo 3 błędy identyfikacji nazw (Mac.Ashdod, Mega Superbet, Zadar U13). | identyfikacja: **błąd**, poprawiony; kalibracja: reguła działa |
| siatkówka | 6 meczów | 1 noga | Turnieje bez rozliczonego meczu w 14 dniach; 4 drużyny bez historii w bazie | reguła |
| CS2 | 55 serii (33 to „1x1”, 8 ESL Pro League) | 0 | `NOT_CALIBRATED`: silnik przegrywa z ceną Superbetu we wszystkich rodzinach, najbardziej na ESL Pro League. Dwie serie EPL odpadły, bo pierwsza identyfikacja ruszyła o 08:22Z, po ich starcie. | reguła; **utajony błąd** linii, poprawiony; pora identyfikacji poprawiona |
| tenis | – | 102 nogi | `TENNIS_SET_MARKET_NOT_ADMITTED` 478 (rynki setowe), `KICKED_OFF` 6608 | decyzja operatora |
| piłka – pozostałe | – | ok. 100 nóg | `DERIVED_NOT_CALIBRATABLE` 699: zmierzone straty (`both_over_goals` 0.837 wobec 0.739). `NOT_CALIBRATED` 342: rynki połówkowe bez własnej krzywej. `OPERATOR_REFUSED` 182 | reguła / następny refit |

## 2. Poprawki (commity na `main`, testy offline, 3553 testy przechodzą)

| commit | co | od kiedy |
|---|---|---|
| `0564c775` | CS2: linia rund drużyny spoza dopasowania krzywej (9.5–12.5) jest odrzucana `LINE_OUTSIDE_FIT`. Te linie trafiały w 0.30 przy pewności 0.731 (20 nóg, 8 serii). | od razu (w CS2 nic nie jest dopuszczone) |
| `cca60a23` | Identyfikacja nazw: kropka między literami rozdziela słowa („Mac.Ashdod”: 75 → 83.3 przy progu 82), drużyny U10–U13 to osobne kadry, alias „mega superbet” → „mega basket”. Rozpoczęty, niezidentyfikowany mecz liczy się jako `KICKED_OFF`. | od razu |
| `3faa471d` | Kalibracja sportów: tercje hokeja i pierwsza połowa koszykówki dopasowywane z historii, a nie z 3 rozliczonych dni | przy refitach |
| `c845f265` | Reprezentacje: RESOLVE zapisuje `national_teams`. CONFIDENCE ocenia próbkę liczbą meczów, a wiek pokazuje flagą `NATIONAL_SAMPLE_AGE(oldest N d)` (dowody: `docs/sofa/evidence/national_samples_2026-10-05.md`) | od dnia 2026-10-06 |
| `cdfd57d1` | Pętle shadow i CS2 uruchamiają SPORT_IDENTITY dla D i D+1 po każdym snapshocie. Przypięty mecz nie jest pytany drugi raz. | nowe pętle (CS2 10-06 od 23:30Z, shadow 10-06 od ok. 04:30Z) |
| `7def49f8` | Refit kalibracji sportów między dniami (00:05Z): hokej i siatkówka na pełnej historii. Hokej zyskuje `period_total|OVER` (316 rozliczonych linii: deklarowane 0.819, trafione 0.832) i `period_team_total|OVER`. | od 10-06 |
| `2105bf7b` | FIXTURE_CHECK: kandydat ponad limit to `OVER_CAP`. PDF pisał wcześniej „przerwane po błędzie” przy przebiegu bez błędu. | od razu |

**Nie zrobione, z powodem:**

- **Koszykówka zostaje `NOT_CALIBRATED`.** Reguła dopuściłaby `h1_total|UNDER` i `h1_team_total|UNDER`, ale na zaledwie 7 i 22 rozliczonych liniach. Ten sam model zawyża pewność we wszystkich kluczach pełnego meczu, w obie strony, więc to raczej zbyt wąski rozkład niż przesunięta średnia (podejrzenie). Potrzebna jest poprawka modelu, a nie luzowanie bramki.
- **CS2 zostaje `NOT_CALIBRATED`.** Na ESL Pro League silnik ma gorszy log-loss niż cena (`match_winner` +0.174 [+0.013; +0.397], 16 serii). Dopuszczenie `match_winner` dłuższym holdoutem to decyzja operatora. Druknęłoby tylko nogi, gdzie model jest powyżej ceny, a to w piłce zmierzony antysygnał.
- **Alias Klagenfurt II ↔ EC KAC II** (1 noga hokeja) nie wszedł. Alias działa globalnie, więc zepsułby piłkarskie „Austria Klagenfurt II”.
- **Mecze nocne D (00:00–04:00Z)** nadal nie mają szans na kupon D, bo przebieg dnia zaczyna się rano. Pętle przypinają je teraz wcześniej, ale kupon budowany o tej porze to osobna decyzja operatora.

## 3. Test e2e: dzień 2026-10-06, zbudowany w nocy

Bridge był uruchomiony o 23:51Z (5 okien, 200 od Sofascore). Kolejność kroków: BOARD 00:01Z → RESOLVE..COUPON → SHADOW / CS2 → SPORT_IDENTITY → FIXTURE_CHECK → CONFIDENCE → SPORT_CONFIDENCE → COUPON_ASSEMBLY → PDF → audyty.

- **BOARD:** 497 meczów (149 piłka, 348 tenis).
- **RESOLVE:** 447 meczów, recall 0.899.
- **SHEET:** 25 610 wierszy, epoka `stats_only`.
- **SPORT_IDENTITY:**
  - hokej 16/16;
  - koszykówka 38/40 (10-05 było 11/21, ale wtedy pierwsza identyfikacja ruszyła dopiero o 08:22Z, więc to nie jest pomiar samej poprawki nazw);
  - siatkówka 1/2;
  - CS2 10/16, przypięte przez nową pętlę o 00:01Z.
- **Kupon (`11_coupon.json`):** 935 pozycji, 15 builderów.
  - Piłka 359. Z tego **207 nóg reprezentacji** z flagą wieku: Liga Narodów UEFA (A, B, C), eliminacje U21, CONCACAF. Mecze towarzyskie nadal są odrzucane.
  - Tenis 556.
  - **Hokej 20.** Z tego 17 to tercje „powyżej 0.5 gola” (NHL, szwajcarska NLB), 3 to total meczu (Białoruś, NLB).
- **SPORT_CONFIDENCE:**
  - koszykówka i CS2: `NOT_CALIBRATED`;
  - siatkówka: `TOURNAMENT_NEVER_SETTLED` (34 nogi).
- **PDF:** wyrenderowany do katalogu roboczego (81 stron), a **nie** do `runs/sofa/2026-10-06`. Wydruk w prawdziwym katalogu zablokowałby nogi w rejestrze kuponu, zanim ktokolwiek je przeczyta. W `runs/sofa/2026-10-06` jest więc 11 bez PDF i bez `printed/`.
- **Audyty:**
  - `audit_variants`: jedna uwaga, C3 — brak odczytów analityków (55 nóg). To oczekiwane, bo analitycy nie byli uruchamiani. Kontrola nóg sportowych (U3) przeszła.
  - `audit_coupon`: kod 0.

Poranny `/sofa-day` buduje 10-06 od nowa (BOARD..PDF, z analitykami) i nadpisuje ten nocny build.

## 4. Do przeczytania rano

1. **Pierwsze 12 pozycji to jeden mecz: Albania – San Marino**, prawie same UNDER z dużą różnicą do kursu.
   - Przykłady: rożne Albanii U8.5 przy pewności 0.91, gdy kurs zakłada 0.68; gole Albanii w 2. połowie U1.5 po 2.65 przy pewności 0.74, gdy kurs zakłada 0.38.
   - Przyczyna: próbka Albanii to mecze z Czechami i Ukrainą, a próbka nie widzi siły dzisiejszego rywala.
   - Reguła reprezentacji jest zmierzona. Na żywo nogi reprezentacji dały ROI −4.8%, tak samo jak cała piłka.
   - Ale niezgoda z ceną to historycznie antysygnał, a bramka `MAX_DISAGREEMENT` jest wyłączona Twoją decyzją.
   - Analitycy czytają pierwszą trzydziestkę, więc to ich mecz. Jeśli taki obraz się powtarza, jest do rozważenia limit nóg na mecz (`max_positions_per_match`).
2. **Nogi reprezentacji z próbką starszą niż 730 dni** na żywo dały −11.0% [−21.4; −0.6], ale na zaledwie 41 meczach. To podejrzenie. Flaga wieku pozwala mierzyć je osobno.
3. **935 pozycji i 81 stron PDF.** Wolumen rośnie razem z liczbą sportów i reprezentacji, a przewagi to nie dodaje.
4. **Szum w logu pętli:** SPORT_IDENTITY dla D+1 kończy się `FAILED`, dopóki nie ma snapshotu D+1. Kod wyjścia jest ignorowany, więc nic się nie psuje.
5. **Niestabilny test w środowisku:** `test_watchdog_relaunches_a_day_whose_pid_file_is_stale` czyta linię poleceń procesu nadrzędnego. Gdy powłoka ma w poleceniu tekst „cs2_daily”, test raz nie przechodzi. To nie jest regresja.
