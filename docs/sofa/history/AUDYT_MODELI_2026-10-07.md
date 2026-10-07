# Audyt modeli, silnika i rynków — 2026-10-07 (wieczór)

Pięciu audytorów (tylko do odczytu): piłka, tenis, hokej + koszykówka,
siatkówka + CS2, kalibracja i line evidence. Pomiary na 2 dniach live
(10-05, 10-06) i replayu; liczby audytorów poniżej są ich, nie moje, chyba że
zaznaczono. Tam, gdzie nie ma pomiaru poza próbką — podejrzenie.

## Wdrożone (przełącznik `epochs.LINE_EVIDENCE_V2_FROM_UTC`, **2026-10-07 13:42Z** - operator przesunął na dziś)

| id | co | kierunek | test |
|---|---|---|---|
| W1 | komórka pasma kursu poszerza się w dół w obrębie pasma, zanim wejdzie inna (`band_cell`) | tylko obniża | `test_a_thin_expensive_cell_widens_down_inside_its_band` |
| W2 | klucz bez krzywej: min. 15 gier w kubełku, Wilson na liniach / design effect sportu | tylko obniża | `test_lines_of_a_few_games…`, `test_the_design_effect…` |
| CS2-2 | pula offsetu sportu liczona bez klucza > 50% linii (`without`) | **może podnieść** inne klucze CS2 (decyzja operatora) | `test_a_dominant_key_is_left_out…` |
| CS2-best_of | brak `best_of` ≠ BO3 (SPORT_CONFIDENCE i `settle_cs2`) | odmowa zamiast zgadywania | dwa testy `best_of` |

Fit 10-07 (do scratchpadu, config nietknięty): design effect football 1.78,
tennis 1.44, basketball 6.33, hockey 1.80, volleyball 2.31, **CS2 1.0**
(audytor mierzył 3.3 inną metodą — moja estymata jest nie wyższa, więc dla CS2
W2 jest łagodniejsze niż w audycie). CS2 `without`: 14 linii / 11 gier —
poniżej 20 gier, więc pozostałe klucze CS2 dostają offset 0.

## Kolejka (wymaga refitu krzywych i więcej niż 2 dni danych — nie wdrożone)

- **T1 tenis:** `games_won_for` — `forecast_p` (rating) bije `p_central` na
  log-loss o −0.086 [−0.124, −0.050] (n=1415); `handicap_games` p bez informacji.
- **T3 tenis:** `games_total` NB zawyża OVER o ok. 4–5 pp (rozkład dwumodalny).
- **CS2-1:** `map_team_rounds` z wyścigu rund zamiast częstości własnej:
  −0.025 log-loss [−0.028, −0.021] w walk-forward (na liniach Superbetu
  −0.021 [−0.057, +0.012], nieistotne).
- **CS2-3:** liczby killi / headshotów bez umiejętności względem ceny.
- **F1 piłka:** `both_over_goals` (BTTS) gorsze od stopy bazowej (Brier
  +0.011 [+0.004, +0.019]); joint z surowych średnich bez shrinku i ratingu.
- **F3 piłka:** rating nie jest w replayu kalibracji (`calibrate_from_cache.py:722`).
- **Koszykówka F1:** klasa świeżości (mecze w 120 dniach) jako wymiar offsetu;
  −0.14 przy ≤2 meczach, −0.06 przy 3–9. Jedno okno 8 dni, 73% początek sezonu.
- **Hokej F3:** gol pustej bramki liczony podwójnie (+0.14 gola); mały wpływ.
- **W3 (offset price-blind × cap):** offset pooled obniża tanie pasmo, które
  realizuje powyżej krzywej (tenis 1.0–1.3: +0.064). Poprawka by **podnosiła**
  — wymaga decyzji operatora (reguła „tylko obniża").
- **W4–W8:** shrinkage offsetu per klucz, selekcja czytanych pozycji
  (optimizer's curse), joint buildera z małego n, 2 dni dowodu.

## Pytania do operatora (nie do rozstrzygnięcia kodem)

1. Jak Superbet liczy gem w super-tiebreaku (jeden gem do zwycięzcy)? (`tennis_score.py:75`; ok. 5% ITF)
2. Jak Superbet traktuje krecza — zwrot czy rozliczenie? Dziś: nierozliczony (`run_settle.py:189`).
3. Czy dogrywka liczy się w „2. połowie" i Q4 koszykówki? (`OT_RULE_UNKNOWN`)

## Sprawdzone, bez defektu

Grading pushów i `most_`, indeksowanie `nb_survival`, wyciek ratingu piłki;
arytmetyka tiebreaków i best-of w tenisie; MR12 i dogrywki CS2; deuce i
extra points w siatkówce; scope dogrywki i push w hokeju/koszykówce.

## Czego nie zmierzono

Offsety sportów poza próbką, CLV, wpływ reguły line evidence na dzisiejsze nogi
(niewyrozliczone), BO5 w CS2 (43 serie), serwis per set w tenisie.

## Dopisane po odpowiedziach operatora (2026-10-07)

- Krecz = zwrot (`settle.RETIRED`, kod Sofascore 92); 2. połowa i Q4
  koszykówki liczone z regulaminowych kwart, dogrywka się nie liczy
  (`OT_RULE_UNKNOWN` usunięte). Dni już rozliczone zachowują stare rozliczenie
  (`FINISHED_ABNORMALLY` w `07_settle_skips.json`, wiersze pomiarowe H2/Q4 z
  dogrywką bez oceny) do ponownego SETTLE danego dnia; ledger dni sprzed
  2026-10-07 nie jest przeliczany wstecz.
- Offset CS2: reszta puli (14 linii / 11 gier) jest poniżej progu 20 gier,
  więc inne klucze CS2 czytają offset 0, nie -0.204 (decyzja operatora; to
  jedyna zmiana v2, która może podnieść pewność).
