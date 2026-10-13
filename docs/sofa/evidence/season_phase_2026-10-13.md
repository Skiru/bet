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

## Wynik (2026-10-13, `scripts/sofa/measure_season_phase.py`, okno 2025-08-01..2026-10-12)

Walk-forward miesięczny (c z wierszy przed 1. dniem miesiąca, trening od
2024-10-01). Log-loss NB na wiersz (strona albo mecz dla `_total`); różnica
nowa - stara, 95% bootstrap po meczach (2000, ziarno 0). Wiersze bez fazy
liczą się z różnicą 0 (metryka główna); obok - tylko wiersze z fazą.

| rynek | wiersze / mecze | z fazą | różnica, wszystkie [95%] | różnica, z fazą [95%] | log-loss stara -> nowa |
|---|---|---|---|---|---|
| `goals_for` | 759 798 / 379 899 | 496 200 | **-0,00019 [-0,00023; -0,00015]** | -0,00029 [-0,00035; -0,00023] | 1,62814 -> 1,62795 |
| `goals_total` | 379 899 / 379 899 | 248 100 | **-0,00039 [-0,00047; -0,00031]** | -0,00060 [-0,00072; -0,00048] | 2,02884 -> 2,02845 |
| `goals_1h_for` | 521 414 / 260 707 | 369 648 | **-0,00013 [-0,00015; -0,00010]** | -0,00018 [-0,00022; -0,00014] | 1,09652 -> 1,09639 |
| `goals_1h_total` | 260 707 / 260 707 | 184 824 | **-0,00030 [-0,00035; -0,00024]** | -0,00042 [-0,00050; -0,00034] | 1,49921 -> 1,49891 |
| `goals_2h_for` | 521 438 / 260 719 | 369 830 | **-0,00006 [-0,00010; -0,00002]** | -0,00008 [-0,00014; -0,00002] | 1,22225 -> 1,22220 |
| `goals_2h_total` | 260 719 / 260 719 | 184 915 | **-0,00012 [-0,00021; -0,00003]** | -0,00016 [-0,00029; -0,00003] | 1,62237 -> 1,62225 |

Centrum ma rating w 100% wierszy okna (rekonstrukcja `centre_replay`).

Per faza (stosunek Σy / Σcentrum w oknie; bias centrum - wynik stara -> nowa;
różnica log-loss w fazie [95%]):

| rynek | early | mid (bez zmian) | late | final |
|---|---|---|---|---|
| `goals_for` | 0,970; +0,050 -> -0,019; -0,00077 [-0,00107; -0,00046] | 1,005; -0,008 | 1,043; -0,068 -> -0,032; -0,00062 [-0,00082; -0,00042] | 1,069; -0,115 -> -0,063; -0,00178 [-0,00219; -0,00135] |
| `goals_total` | 0,977; +0,076 -> -0,043; -0,00053 [-0,00111; +0,00007] | 1,006; -0,019 | 1,044; -0,137 -> -0,068; -0,00194 [-0,00239; -0,00149] | 1,072; -0,239 -> -0,135; -0,00529 [-0,00623; -0,00429] |
| `goals_1h_for` | 1,008; -0,005 -> -0,019; **+0,00025 [+0,00012; +0,00039]** | 1,035; -0,023 | 1,077; -0,00097 [-0,00118; -0,00076] | 1,109; -0,00187 [-0,00231; -0,00146] |
| `goals_1h_total` | 1,014; **+0,00053 [+0,00030; +0,00078]** | 1,036 | 1,078; -0,00222 | 1,112; -0,00449 |
| `goals_2h_for` | 0,986; **+0,00047 [+0,00008; +0,00084]** | 1,027 | 1,052; -0,00038 | 1,097; -0,00195 |
| `goals_2h_total` | 0,992; **+0,00136 [+0,00056; +0,00209]** | 1,028 | 1,053; -0,00089 | 1,100; -0,00486 |

Połowy okna (metryka główna):

| rynek | 2025-08..2026-02 | 2026-03..2026-10 |
|---|---|---|
| `goals_for` | -0,00012 [-0,00016; -0,00008] | -0,00025 [-0,00031; -0,00019] |
| `goals_total` | -0,00014 [-0,00023; -0,00006] | -0,00062 [-0,00075; -0,00050] |
| `goals_1h_for` | -0,00002 [-0,00004; +0,00001] | -0,00023 [-0,00028; -0,00018] |
| `goals_1h_total` | -0,00005 [-0,00009; +0,00000] | -0,00054 [-0,00064; -0,00043] |
| `goals_2h_for` | -0,00002 [-0,00007; +0,00004] | -0,00009 [-0,00016; -0,00003] |
| `goals_2h_total` | +0,00000 [-0,00012; +0,00012] | -0,00023 [-0,00037; -0,00009] |

Współczynniki walk-forward (pierwszy miesiąc 2025-08 -> ostatni 2026-10),
`goals_for`: early -0,041 -> -0,036, late +0,010 -> +0,034, final +0,013 -> +0,049
(koniec sezonu 2025/26 w treningu podniósł je w drugiej połowie okna).

**Próg zarejestrowany (górna granica < 0 per rynek): spełniony dla wszystkich
sześciu rynków.** Efekt jest ok. 4 razy mniejszy niż pomiar 10-05 względem
surowej średniej (`goals_total` -0,00039 na mecz wobec -0,00173): pełne centrum
(rating + skurczenie) już częściowo nosi fazę. Zysk siedzi w końcu sezonu
(`late`, `final`); faza `early` poprawia pełny mecz (`goals_for`), ale
**pogarsza połowy** (`goals_1h_*`, `goals_2h_*`, przedziały wykluczają 0).
Powód: term fazy jest względem połowy sezonu, a centra połów mają poziomowy
bias (Σy/Σcentrum w `mid` 1,027-1,036), więc przesunięcie `early` w dół
oddala je od wyniku. Rejestracja nie przewidywała wyboru komórek
(rynek x faza), więc plik zawiera wszystkie współczynniki; usunięcie `early`
dla połów to decyzja sesji koordynującej (nowy pomiar albo zgoda operatora).

Współczynniki do pliku (`fit_season_phase.py --before 2026-10-13 --write`,
wszystkie wiersze 2024-10-01..2026-10-12) - `config/sofa_season_phase.json`:

| rynek | early | late | final |
|---|---|---|---|
| `goals_for` | -0,0361 | +0,0339 | +0,0492 |
| `goals_total` | -0,0297 | +0,0338 | +0,0505 |
| `goals_1h_for` | -0,0247 | +0,0383 | +0,0560 |
| `goals_1h_total` | -0,0195 | +0,0384 | +0,0572 |
| `goals_2h_for` | -0,0438 | +0,0236 | +0,0538 |
| `goals_2h_total` | -0,0384 | +0,0235 | +0,0554 |

**Przełącznik `SEASON_PHASE_FROM_UTC` zostaje `None`** (polecenie sesji
nadrzędnej: włącza go razem z refitem piłki, którego replay woła
`season_phase.SeasonPhaseIndex` / `season_phase.apply`).

Zastrzeżenia:
1. Pomiar centrum, nie linii Superbetu ani krzywej; krzywe zainstalowane
   opisują estymator bez fazy.
2. W SHEET indeks fazy liczy mecze drużyny z historii w cache'u (listingi
   `last` + indeks); brak meczu w cache'u zaniża rundę. Dzień na żywo widzi
   historię sprzed cięcia 00:00Z, nie mecze rozegrane tego dnia przed startem.
3. Progi faz (`EARLY_ROUNDS` 3, `FINAL_ROUNDS` 2, `LATE_SHARE` 0,8,
   `MIN_SEASON_ROUNDS` 10) wybrane w pomiarze 10-05, nie dopasowane
   (`UNFITTED_CONSTANTS` na wierszu).
4. B14 (W per rynek) zmienia centrum, na którym dopasowano c; przy obu
   włączonych - ponowny fit.
5. `early` pogarsza połowy (wyżej) - do decyzji przed włączeniem.
