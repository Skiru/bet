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
| T-F54-coupon-failure | kryterium porażki, zapisane przed wynikami | jak T-F53 | 2026-10-06.. | >= 300 nóg / >= 100 meczów | po F2: CLV < 0 z całym przedziałem poniżej 0 = „brak przewagi”, kupon zostaje narzędziem informacyjnym | PROPOSED |
| T-PEER-CHOICE-edge | z dwóch nóg jednego meczu o kursie w pasie 0,06 pewniejsza (★ z `bet.sofa.peer_choice`) wygrywa częściej, gdy dokładnie jedna wygrała | nogi `official` na 11_coupon.json, różne zmienne, od 2026-10-09 | 2026-10-09..2027-01-08 | >= 3 000 rozstrzygniętych par w >= 300 meczach | POTWIERDZONY: dolna granica 95% > 50% (piłka + tenis); OBALONY: górna < 52% | PROPOSED |

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
