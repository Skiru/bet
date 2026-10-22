# Rejestr testów z góry (F5.1)

Plan: `docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md`, F5.1-F5.4. Wersja
maszynowa: `config/sofa_test_registry.json` - **ona jest wiążąca**; ten plik
jest jej opisem. Walidator: `scripts/sofa/check_test_registry.py` (offline;
exit 1, gdy okno danych testu zaczyna się w dniu rejestracji albo przed nim).

## Zasady

1. **Test ocenia się wyłącznie na danych, których nie było w chwili zapisu.**
   `data_window.from` > `registered_on` - walidator odrzuca inaczej.
2. **Reguła po zapisie się nie zmienia.** Zmieniona reguła (inny próg, refit
   krzywej, nowa bramka) = nowy test, nowy identyfikator, nowa data.
3. **Kryterium stopu jest zapisane przed wynikami.** Wgląd pośredni może tylko
   zatrzymać test jako beznadziejny (`STOPPED_FUTILE`), nigdy ogłosić sukcesu.
4. **Status `PROPOSED`** = zapisane przez kod, nie zatwierdzone przez operatora.
   Jeśli operator zatwierdzi test później niż 2026-10-05, `registered_on` i
   `data_window.from` przesuwają się na dzień zatwierdzenia (walidator
   sprawdza je ponownie).
5. Pule nigdy się nie sumują (ledger: każda pula osobno).

## Testy

| id | hipoteza | populacja | okno danych | wymagane n | kryterium | status |
|---|---|---|---|---|---|---|
| T-F51-01-football-goals-total-blend | model piłki niesie informację o `goals_total` ponad cenę; blend kroczący wybiera OVER z zyskiem | piłka, `goals_total` OVER, wycenione wiersze SHEET epoki stats-only | 2026-10-06..2027-04-05 | ~4 400 nóg, >= 100 meczów | ROI: dolna granica 95% > 0 przy ostatnim wglądzie; wgląd co 1 100 nóg tylko na „beznadziejny” (górna < 0) | PROPOSED |
| T-F51-02-hockey-totals | sumy hokeja z modelu wyniku przez krzywą bez cen biją zamknięcie | hokej, `total` / `team_total`, nogi `official` na 11_coupon.json | 2026-10-06..2027-01-05 | >= 300 nóg, >= 100 meczów | CLV: dolna granica 95% > 0; górna < 0 = FAILED | PROPOSED |
| T-F51-03-boosts-separate-pool | pojedyncze boosty Superbetu mają dodatnie EV przy zdewigowanym rynku sprzed podbicia | `10_boosts.json`, `combo` false, `fair_p` ustawione; osobna pula, nigdy na kuponie | 2026-10-06..2027-01-05 | >= 300 boostów, >= 100 meczów | ROI: dolna granica 95% > 0; górna < 0 = FAILED | PROPOSED |
| T-F53-coupon-edge | oficjalny kupon stats-only bije cenę | `official`, epoka stats_only, od 2026-10-06 | 2026-10-06.. | CLV >= 300 nóg / >= 100 meczów **albo** ROI ~4 400 pozycji | przewaga: CLV dolna 95% > 0 **albo** ROI dolna 95% > 0 | PROPOSED |
| T-F54-coupon-failure | kryterium porażki; zatwierdzone przez operatora 2026-10-13 (werdykt „brak przewagi nad ceną” przyjęty na danych 10-06..10-11: CLV −5,16% i −3,95%, cały przedział < 0 - dane widziane przed zatwierdzeniem, więc nie wynik testu; zasada 4) | jak T-F53 | 2026-10-14.. | >= 300 nóg / >= 100 meczów | po F2: CLV < 0 z całym przedziałem poniżej 0 = „brak przewagi”, kupon zostaje narzędziem informacyjnym | REGISTERED |
| T-PEER-CHOICE-edge | z dwóch nóg jednego meczu o kursie w pasie 0,06 pewniejsza (★ z `bet.sofa.peer_choice`) wygrywa częściej, gdy dokładnie jedna wygrała | nogi `official` na 11_coupon.json, różne zmienne, od 2026-10-09 | 2026-10-09..2027-01-08 | >= 3 000 rozstrzygniętych par w >= 300 meczach | POTWIERDZONY: dolna granica 95% > 50% (piłka + tenis); OBALONY: górna < 52% | PROPOSED |
| T-PRICE-GAP-flag | noga piłkarska / tenisowa z pewnością > 1/kurs + 0,03 (flaga `CONFIDENCE_ABOVE_PRICE`, `bet.sofa.price_gap`) trafia poniżej wydrukowanej pewności, reszta nie | nogi `official` na 11_coupon.json, piłka i tenis osobno, od 2026-10-13 | 2026-10-13..2027-01-12 | >= 500 nóg z flagą w >= 300 meczach (piłka) | POTWIERDZONY: górna granica 95% < 0 (piłka); OBALONY: dolna > -2 pp - flaga przestrzega na wyrost | REGISTERED |
| T-CS2-PRICE-GAP-flag | noga CS2 z pewnością > 1/kurs + 0,03 (flaga `CONFIDENCE_ABOVE_PRICE` od `epochs.CS2_PRICE_GAP_FROM_UTC`) trafia poniżej wydrukowanej pewności, reszta nie | nogi CS2 z 11_coupon.json od 2026-10-21, ocena CS2_SETTLE, zdjęte odczytem poza | 2026-10-21..2027-01-20 | >= 200 nóg z flagą w >= 70 seriach | POTWIERDZONY: górna granica 95% < 0; OBALONY: dolna > -2 pp | REGISTERED |
| T-SPORT-LATE-WINDOW | nogi hokeja / kosza / siatkówki / CS2 meczów po północy UTC, które kupon dnia D drukuje od `epochs.SPORT_LATE_WINDOW_FROM_UTC` (pole `window: "late"`, wieczorny rebuild), realizują względem pewności nie gorzej niż pozostałe nogi tych sportów z dnia D | single sportów mierzonych z 11_coupon.json od 2026-10-23, ocena `coupon_sports.grade` z pliku `source_date` nogi, zdjęte odczytem poza; per sport i łącznie (z nazwą puli) | 2026-10-23..2027-01-22 | >= 300 nóg „late” w >= 100 meczach | POTWIERDZONY: dolna granica 95% różnicy (late - reszta) > -3 pp; OBALONY: górna < 0 (decyzja o oknie wraca do operatora) | REGISTERED |
| T-A2-league-rate-refusals | mecze hokeja / kosza / siatkówki odrzucane regułą stawki ligi (`FRIENDLY_FIXTURE`, `NO_LEAGUE_RATE`, `epochs.LEAGUE_RATE_RULE_FROM_UTC`) zrealizowałyby poniżej pewności starej wyceny (stawka wszystkich lig) | linie Superbetu odrzucanych meczów od 2026-10-14, wycenione starą regułą; kontrola: mecze zachowane | 2026-10-14..2027-04-13 | >= 150 nóg „do druku” w >= 60 meczach | POTWIERDZONY: górna granica 95% realizacja - pewność < 0; OBALONY: dolna > 0 (operator wraca do połowy `NO_LEAGUE_RATE` z O1) | REGISTERED |
| T-A4-bucket-deff | nogi dodane przez efekt projektu kubełka (klucze bez krzywej, `epochs.BUCKET_DESIGN_EFFECT_FROM_UTC`) realizują co najmniej na poziomie pewności | nogi `official` od 2026-10-14 z pewnością z line evidence klucza bez krzywej, „dodane” vs „zachowane”, per sport (tenis pod obserwacją: w walk-forward ROI dodanych -10,0% [-19,7; -0,8]) | 2026-10-14..2027-01-13 | >= 300 dodanych nóg w >= 150 meczach | POTWIERDZONY: dolna granica realizacja - pewność > -2 pp; OBALONY: górna < 0 (operator cofa przełącznik) | REGISTERED |
| T-IDENTITY-unexplained | po włączeniu mapy encji (plan `PLAN_MAPA_DRUZYN_2026-10-14.md`, K1–K7) każde zdarzenie i zawodnik każdego sportu kończy dzień jako IDENTIFIED, NOT_ON_SOFASCORE albo NEEDS_ALIAS, a żadnej identyfikacji nowej reguły nie podważa rozliczenie | wszystkie zdarzenia tablicy (piłka / tenis) i `sport_fixtures.json` (bez 1x1 i `DUPLICATE_SUPERBET_TEAM`), piłkarze `03_samples.json`, zawodnicy `player_model` hokeja / kosza, gracze CS2; każdy sport i typ encji osobno (`measure_team_identity.py`) | 2026-10-15..2027-01-14 | 14 kolejnych dni po ostatnim przełączniku | POTWIERDZONY: 14 dni z 0 niewyjaśnionych (poza `BRIDGE_ABORTED` ponawianym w K6) i 0 sprzeczności; OBALONY: dowolna sprzeczność identyfikacji nowej reguły (operator cofa przełącznik) albo po 30 dniach niewyjaśnione nie spadną poniżej 10% bazy K0 | REGISTERED |
| T-CS2-SERIES-ROUNDS-superbet | na liniach rund serii CS2, które Superbet faktycznie wystawia, strony z przygotowaną krzywą historii >= 0,70 realizują > 10 pp poniżej krzywej (niezgoda z linią = antysygnał; 09-28..10-13: 21 stron / 19 serii, 0,33 przy 0,74) | strony `rounds_total` / `rounds_handicap` / `team_rounds` rozliczone przez CS2_SETTLE z `model_p` (od `epochs.CS2_SERIES_ROUNDS_FROM_UTC`), czytane krzywą zainstalowaną 2026-10-15 00:17Z w `config/sofa_sport_confidence_calibration.json` (decyzja operatora: instalować mimo ostrzeżenia; ta sama krzywa co w `data/refit_new_markets_2026-10-15/cs2_series_rounds/curves.json`) | 2026-10-15..2027-01-14 | >= 100 stron / >= 60 serii | POTWIERDZONY (odinstalować te krzywe - wniosek dla operatora): górna granica 95% (zrealizowane - krzywa) < −0,10; OBALONY: dolna > −0,03; przy n < 100 do końca okna - STOPPED_FUTILE | REGISTERED |
| T-PLAYER-SAMPLE-GATES | nogi zawodników drukowane tylko dzięki zdjęciu bramki kształtu próbki (`player_sample_rule` = zdjęta bramka, `epochs.PLAYER_SAMPLE_GATES_FROM_UTC`) trafiają nie więcej niż 3 pp poniżej wydrukowanej pewności | nogi `official` z 11_coupon.json i zdjęte przez odczyt (`removed_by_reads`, osobno) od 2026-10-17, rynki z `/lineups`, zwroty (zawodnik nie wyszedł) poza; obok nogi zawodników bez pola i ROI | 2026-10-17..2027-01-16 | >= 400 nóg w >= 200 meczach | POTWIERDZONY: dolna granica 95% > -3 pp; OBALONY: górna < -3 pp (operator wyłącza przełącznik) | PROPOSED |
| T-TENNIS-SET-GAMES-OVER | drukowane nogi OVER gemów zawodnika w secie (`games_won_set1_for` / `games_won_set2_for`, cena z sąsiadów ratingu) trafiają nie więcej niż 3 pp poniżej wydrukowanej pewności | nogi `official` z 11_coupon.json i zdjęte przez odczyt (osobno) od 2026-10-18; ROI obok | 2026-10-18..2027-01-17 | >= 400 nóg w >= 250 meczach | POTWIERDZONY: dolna granica 95% > -3 pp; OBALONY: górna < -3 pp (refit krzywej na liniach rynkowych, decyzja operatora) | PROPOSED |
| T-TENNIS-SERVE-MARKET-LINE | staged krzywe rynków serwisowych tenisa (asy z korektą returnującego, PB w secie, asy + PB) czytane przez dowody linii na rozliczonych liniach Superbetu nie zawyżają o więcej niż 3 pp - warunek instalacji | każda rozliczona linia tych rynków od 2026-10-18, pewność jak w CONFIDENCE >= 0,70 i x >= 0,90 (`scripts/sofa/measure_tennis_serve_market_line.py`) | 2026-10-18..2027-01-17 | >= 150 nóg w >= 80 meczach | POTWIERDZONY: dolna granica 95% > -3 pp (krzywe i przełącznik mogą wejść za zgodą operatora); OBALONY: górna < -3 pp | PROPOSED |
| T-FAMILY-SELECTION | selekcja „x ≥ 1 i rodzina na plusie” widoku HTML (`bet.sofa.family_record`: x = pewność × kurs >= 1 i rodzina - sport, rynek, kierunek - na plusie na nogach z dni przed, >= 50 nóg) traci mniej niż cały kupon, może realizować przy cenie lub ponad | nogi `official` 11_coupon.json, zablokowane włącznie, bez usuniętych odczytem; wszystkie sporty razem jak w widoku i osobno | 2026-10-19..2027-01-18 | >= 5 000 nóg w >= 2 500 meczach | ZYSK: dolna granica 95% ROI selekcji > 0; MNIEJSZA STRATA: selekcja minus reszta > 0 z przedziałem, a sama selekcja z zerem w przedziale; OBALONY: górna granica różnicy < +1 pp - filtr znika z widoku; decyzja tylko, gdy żaden dzień nie ma więcej niż połowy nóg selekcji | PROPOSED |
| T-LINE-CURVES | noga piłki mężczyzn z 33 kluczy `config/sofa_line_curves.json` drukowana przez krzywą per linię (`calibrated_on` „line:...”) trafia w granicach 2 pp od wydrukowanej pewności i bliżej niż przez krzywą wspólną | nogi `official` piłki z `line:` od 2026-10-19, zablokowane włącznie, bez usuniętych odczytem | 2026-10-19..2027-01-18 | >= 1 500 nóg w >= 800 meczach | POTWIERDZONY: przedział luki w [-2; +2] pp i |luka| mniejsza niż krzywej wspólnej; OBALONY: górna granica < -2 pp - operator wyłącza przełącznik | PROPOSED |
| T-TENNIS-ACES-SETS-EXPOSURE | asy w secie liczone jako tempo x oczekiwane gemy seta z ratingu, x efekt turnieju (ramię EXP_T, `scripts/sofa/measure_tennis_serve_exposure.py`), przez krzywą z linii rynkowych, na rozliczonych liniach Superbetu nie zawyżają o więcej niż 3 pp - warunek wdrożenia w SHEET | każda rozliczona linia asów w secie (zawodnik i łączne) od 2026-10-20 dołączona do replayu, pewność >= 0,70 i x >= 0,90; obok log-loss EXP_T minus obecny środek | 2026-10-20..2027-01-19 | >= 150 nóg w >= 60 meczach | POTWIERDZONY: dolna granica 95% > -3 pp i log-loss nie gorszy (wtedy SHEET za przełącznikiem i sprawdzian prawdziwym SHEET); OBALONY: górna < -3 pp | PROPOSED |
| T-BB-PLAYER-V2-calibration | przedmeczowe `p` `player_model` na dziewięciu nowych rodzinach zawodników koszykówki (`shadow.PLAYER_V2_MARKETS`, od `epochs.BASKETBALL_PLAYER_V2_FROM_UTC`: rzuty wolne trafione / oddane, z gry trafione / oddane, za 2 trafione / oddane, za 3 oddane, faule osobiste, straty) jest skalibrowane na rozliczonych liniach Superbetu: trafienia minus średnie `p` w paśmie `p` >= 0,70 w granicach 3 pp na rodzinę | wiersze SHADOW_SETTLE (WIN / LOSS) id 231804-231811 i 200985 od 2026-10-23, ostatnia prognoza sprzed meczu | 2026-10-23..2027-01-31 | >= 300 linii / >= 40 meczów na rodzinę w paśmie | POTWIERDZONY: przedział zawiera 0 i mieści się w ±3 pp; OBALONY: górna granica < −3 pp | REGISTERED |

Pełne reguły (dokładne formuły, źródła cen, sposób rozliczenia) są w
`config/sofa_test_registry.json`, pole `rule`.

## Skąd liczby (źródła)

| liczba | źródło |
|---|---|
| football `goals_total` b = 0,50 [0,26; 0,75] | `docs/sofa/history/RAPORT_NOC_2026-10-04.md` wiersz 60; szczegóły `data/night_2026-10-03/edge/RAPORT.md` (poza gitem): 7 074 wierszy / 1 791 meczów, b = 0,496 [0,258; 0,753]; kontrola `measure_model_information.py` b = 0,4961 [0,2699; 0,7213] |
| najlepsza reguła `goals_total` OVER, próg 1,05: +6,7% [−15,9; +29,3], 160 zakładów / 82 mecze / 6 dni | jw. (`data/night_2026-10-03/edge/RAPORT.md`, krok 2) |
| hokej sumy b = 0,98 [−0,07; 2,14] (c = 0,10) | `docs/sofa/PIPELINE.md` wiersz 1541; `docs/sofa/MODELE_HOKEJ_KOSZ_SIATKA.md` wiersz 48 |
| boosty: 12 pojedynczych dwustronnych, średnie EV +0,1% | `docs/sofa/history/RAPORT_NOC_2026-10-04.md` wiersz 68 |
| kryterium F5.3 (CLV 300 nóg / 100 meczów, ROI ~4 400 pozycji, ~150 dziennie) | `docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md` wiersz 105 |
| kryterium porażki F5.4 | tamże, wiersz 106 |
| CLV official 09-19..10-04: −4,32% [−4,71; −3,93], 86 nóg | plan, wiersz 34; odtworzone 2026-10-05 przez `audit_clv.py --from 2026-09-19 --to 2026-10-04` (ta sama liczba) |

## Czego nie znaleziono (nie wymyślone)

- **Dzienna liczba boostów** do rozliczenia - nie ma jej w `docs/sofa`; czas
  trwania T-F51-03 jest nieznany.
- **Które rodziny hokeja tworzyły „sumy”** w teście b = 0,98 - cytowane
  dokumenty tego nie mówią; T-F51-02 ustala je jako `total` + `team_total`.
- **Wymagane n dla T-F51-01** z pomiaru tej reguły - nie ma; przyjęte ~4 400
  z planu (sekcja 1: tyle pozycji potrzeba, by pokazać 3% przewagi). Przy
  tempie z nocy 10-03 (160 zakładów / 6 dni) to ~165 dni - stąd koniec okna.
- **CLV dla wierszy niewydrukowanych** - `capture_closing.py` zapisuje
  zamknięcie tylko nóg z wydruku, więc T-F51-01 ocenia ROI, nie CLV.

## Uwagi

- b = 0,50 zmierzono na `p_central` **starej** epoki (z ceną w środku). W
  epoce stats-only `p_central` to inna wielkość - T-F51-01 niczego z tamtego
  pomiaru nie używa poza hipotezą; blend dopasowuje się wyłącznie na
  wierszach nowej epoki z dni wcześniejszych niż dzień zakładu.
- b = 0,98 hokeja ma przedział z zerem i pochodzi z dwóch dni pomiaru
  cieni (09-29, 09-30) - to powód do testu, nie dowód przewagi.
