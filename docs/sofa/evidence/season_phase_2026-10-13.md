# C1: faza sezonu w centrum goli (audyt 2026-10-13)

Przełącznik: `epochs.SEASON_PHASE_FROM_UTC` (`season_phase_v1`), domyślnie `None`.
Współczynniki: `config/sofa_season_phase.json` (pisze `scripts/sofa/fit_season_phase.py`,
domyślnie dry-run). Moduł: `bet.sofa.season_phase`. Pomiar:
`scripts/sofa/measure_season_phase.py` (tylko odczyt), rekonstrukcja centrum:
`bet.sofa.centre_replay`.

## Diagnoza (sprawdzona w kodzie 2026-10-13)

- Kodu fazy sezonu nie ma: `grep -rn "round_number\|season_phase" src/bet/sofa scripts/sofa/run_sheet.py`
  nie znajduje użycia w centrum. `Fixture.round_number` jest w kontrakcie
  (`contracts.py:89`), SHEET go nie czyta.
- `MODEL_FIXES_FROM_UTC` (`epochs.py:171`) bramkuje tylko F2.2 (dyspersja NB
  tenisa i notatka `OTHER_DIVISION_SAMPLE`), nie fazę.
- Pomiar z 2026-10-05 (`measure_model_defects.py:688-735`, `season_rounds` /
  `round_label`; `model_defects_2026-10-05.md` §5) był **względem surowej
  średniej próbki** i na podziale po parzystości id (nie walk-forward):
  goals_total -0,00173 [-0,00200; -0,00147], goals_for -0,00111.
- Centrum SHEET dla goli (`run_sheet.py:1197-1223`): 0,5 x rating +
  0,5 x próbka skurczona do priora (K rynku). Ani rating (średnia
  wykładnicza po wszystkich fazach), ani próbka nie wiedzą, w której fazie
  sezonu jest mecz.

## Definicja fazy (as-of, bez zaglądania w przyszłość)

`season_phase.SeasonPhaseIndex`, budowany z historii (`football_rating.load_history`)
mecz po meczu; o mecz pyta się **przed** dodaniem go do indeksu:

- runda strony = 1 + liczba jej meczów w (rozgrywki, sezon Sofascore) przed
  startem; runda meczu = średnia obu stron;
- długość sezonu = mediana liczby meczów drużyny w **poprzednim** sezonie tych
  rozgrywek (najpóźniejszy inny sezon, który zaczął się przed bieżącym),
  liczona na meczach przed startem;
- etykieta (`phase_label`, progi z pomiaru 10-05, wybrane, nie dopasowane):
  `early` runda <= 3; `final` ostatnie 2 rundy; `late` runda / długość >= 0,8;
  `mid` reszta; brak fazy, gdy długość < 10 (puchary, fazy grupowe), brak
  poprzedniego sezonu, brak id sezonu albo runda > długość (zmieniony format).

SHEET buduje ten sam indeks z historii przed cięciem dnia (00:00Z), tym samym
cięciem, co książka ratingu.

## Rejestracja (zapisana 2026-10-13 PRZED uruchomieniem pomiaru)

- **Hipoteza:** centrum x exp(c[rynek][faza]); c fazy `mid` = 0 (to term fazy,
  nie korekta poziomu centrum). c[faza] = log(Σy/Σcentrum) fazy minus to samo
  dla `mid` (MLE Poissona z offsetem log centrum, wskaźnik na fazę, wyraz
  wolny pominięty w zastosowaniu).
- **Rynki:** `goals_for`, `goals_total`, `goals_1h_for`, `goals_1h_total`,
  `goals_2h_for`, `goals_2h_total`.
- **Centrum bazowe = pełne centrum na żywo** w rekonstrukcji `centre_replay`:
  0,5 x rating (`FootballForecast.centre`, as-of) + 0,5 x próbka (10 ostatnich
  wartości, skurczona do stawki ligi z książki, K rynku z `PER_MARKET_K`);
  bez ratingu - sama próbka. To nie jest SHEET bajt w bajt (prior z książki,
  nie z `config`; próbka z historii, nie z SAMPLES) - to samo w obu wariantach.
- **Populacja:** historia z cache'u, mecze 2025-08-01..2026-10-12 (UTC), strony
  z >= 5 wartościami w ostatnich 10; mecze bez fazy dostają różnicę 0 (są w
  mianowniku - efekt na rynku tak, jak byłby wyceniany).
- **Poza próbą (walk-forward):** c dopasowane na wierszach ściśle przed
  pierwszym dniem ocenianego miesiąca (trening od 2024-10-01); minimum 500
  wierszy na fazę, inaczej faza bez współczynnika.
- **Metryka główna:** log-loss NB obserwowanej liczby przy średniej = centrum,
  alfa z zainstalowanej tabeli dyspersji (`config/sofa_count_dispersion.json`,
  rynek x rozgrywka); różnica nowa - stara na wiersz.
- **Przedział:** 95% bootstrap po meczach (2000 losowań, ziarno 0).
- **Próg (O5):** per rynek górna granica 95% różnicy < 0. Rynek, który go nie
  spełnia, nie wchodzi do pliku.
- **Wtórne (nie progowe):** różnica tylko na wierszach z fazą; bias
  (centrum - wynik) per faza przed i po; połowy okna (2025-08..2026-02,
  2026-03..2026-10); współczynniki per miesiąc.
- **Zastrzeżenia zapisane z góry:** replay krzywych
  (`calibrate_from_cache.py`) nie odtwarza ratingu piłki (A6) ani fazy - po
  włączeniu krzywe muszą być dopasowane na estymatorze z fazą (refit). Pomiar
  dotyczy centrum, nie linii Superbetu.

## Wynik

(uzupełniane po pomiarze)
