# B7: tempo (posiadania Olivera) i skuteczność na posiadanie w koszykówce (audyt 2026-10-13)

Przełącznik: `epochs.BB_PACE_FROM_UTC` (domyślnie `None`). Kod:
`score_model` (`PACE_METRICS`, `box_values`, `load_box_scores`,
`attach_box`, `ScoreModel.pace`), replay: `sport_confidence.parse_history(...,
box=...)`, `walk_forward_rows(..., pace=...)`, `settled_shadow_rows(...,
pace=...)`, `fit_sport_confidence --bb-pace`. Skrypt pomiaru:
`scripts/sofa/measure_basketball_pace.py` (tylko odczyt).

## Diagnoza (zweryfikowana w kodzie)

- `score_model.parse_event` czyta z listingu tylko punkty po kwartach;
  `_metrics` dla koszykówki to jedno `bb_reg_for` (punkty regulaminu na
  stronę), `ScoreModel.expected` = stawka ligi x atak x obrona na punktach.
  Ani `score_model.py`, ani `sport_confidence.py` nie czyta
  `sofa_event_stats.statistics_json` (grep: 0 użyć).
- Dane na kopii bazy `data/refit_2026-10-13/sofa_replay.db`: z 51 168 meczów
  historii koszykówki 34 413 ma wiersz w `sofa_event_stats`, 29 725 ma pełny
  box score (`fieldGoalsScored` z próbami, `freeThrowsScored`,
  `offensiveRebounds`, `turnovers`). Pokrycie po miesiącach: 2024-10..2026-05
  ok. 75-90% meczów, 2026-09 791 / 1 228, **2026-10 4 / 1 334** - box score
  koszykówki nie jest pobierany na bieżąco (`backfill_event_stats.py --sport
  basketball` uruchamiany ręcznie).

## Co jest nowe wobec odrzuconego B2B

B2B (back-to-back) to kontekst terminarza mierzony na punktach (+0,06 pkt, se
0,64, bez efektu). B7 to inna oś: **inne wejście** (box score zamiast samych
punktów) i inna struktura centrum - liczba posiadań meczu (tempo obu drużyn)
razy punkty na posiadanie (atak strony x obrona rywala). Nie dotyka
terminarza ani odpoczynku.

## Rejestracja (zapisana 2026-10-13 PRZED uruchomieniem pomiaru)

Estymator nowy (wariant jedyny, rozstrzygający):

- Posiadania strony (Oliver, wersja prosta): `FGA - ORB + TOV + 0,44 x FTA`;
  posiadania meczu = średnia obu stron; przeskalowane do regulaminu
  `4Q / (4Q + 5)` gdy mecz miał dogrywkę (Q = długość kwarty ligi,
  `quarter_minutes_for`). Mecz z posiadaniami poza 40..140 lub bez któregoś
  pola: brak box score.
- Punkty na posiadanie strony = punkty meczu (`current`) / posiadania meczu
  (bez skalowania - dogrywka ma tę samą skuteczność).
- Dwie nowe metryki w tym samym `RatingBook` co punkty: `bb_poss` (tempo:
  atak = własne tempo, obrona = tempo dopuszczane) i `bb_ppp` (atak = ORtg,
  obrona = DRtg). Ta sama mechanika: stawka ligi, link / siła ligi, `MIN_TEAM_MATCHES`.
- Oczekiwane punkty regulaminu strony = średnia(E posiadań gospodarza,
  E posiadań gościa) x E punktów na posiadanie strony; podział na kwarty
  tymi samymi udziałami; szum (`bb_game_sd` / `bb_team_sd` / `bb_quarter_sd`)
  dopasowany momentami na resztach względem NOWEGO centrum (ta sama funkcja).
- Powrót do modelu punktowego (bez zmian), gdy: któraś strona ma < 5 meczów
  z box score, któraś nie miała meczu z box score w ostatnich 60 dniach
  (`PACE_FRESH_S`, wybrane, nie dopasowane), rozgrywki mają < 30 meczów z box
  score (stawka ligi ścisła, bez średniej globalnej), albo para jest UNLINKED
  na metrykach tempa.
- α (`ALPHA_BY_METRIC`) dla `bb_poss` z {0,03; 0,06; 0,10; 0,15} i dla
  `bb_ppp` z {0,03; 0,06; 0,10}: wybrane na oknie strojenia
  **2025-01-01..2025-06-01** kwadratem błędu sumy regulaminu one step ahead
  (tylko mecze, w których działa ścieżka tempa); potem zamrożone.

Model dzisiejszy (porównanie): `build_model` bez box score, te same reguły
dnia 2026-10-13 (świeżość szumu włączona jak na żywo; A2, A3 / C8 wyłączone -
dziś `None`).

**Test A - historia (główny).** Okno **2025-10-01..2026-06-01**, walk-forward:
model przebudowany co 30 dni (jak `walk_forward_rows`), między przebudowami
książka aktualizowana mecz po meczu; co n-ty mecz do 6 000; 1 000 symulacji
na mecz i model, to samo ziarno. Linie: kwartyle (+0,5) sumy regulaminu,
punktów strony i marginesu z meczów 2025-01-01..2025-10-01 (przed oknem,
nigdy z ceny). Metryki na mecz: średni Brier i log-loss po progach dla
`total`, `team_total` (obie strony), `handicap` (margines), oraz zwycięzca z
dogrywką. Różnica w parach nowa - stara; 95% z bootstrapu po meczach (2 000
losowań, ziarno 0). Raportowane też: podzbiór meczów ze ścieżką tempa,
kalibracja p >= 0,70.

**Test B - linie Superbetu.** Rozliczone linie koszykówki 2026-09-29..2026-10-12
(`runs/sofa/shadow/basketball/<d>/settled.json`), model zbudowany na 00:00Z
dnia (`settled_shadow_rows`), p modelu (cena nigdy nie jest wejściem p);
rodziny `total`, `team_total`, `handicap`, `winner`; Brier i log-loss w parach,
bootstrap po meczach. Dodatkowo Brier na liniach głównych (fair 0,45-0,55;
cena wybiera tylko podzbiór, jak w audycie: dziś 0,2593 na totalu).

**Próg (O4, zapisany z góry):** Test A - `total`: górna granica 95% różnicy
Briera **i** log-loss < 0; zwycięzca: dolna granica różnicy Briera <= 0 (nie
gorzej). Test B - `total` i `winner`: przedział różnicy Briera nie leży w
całości powyżej zera. Spełnione oba -> refit krzywej koszykówki na kopii
(`data/refit_2026-10-13/b7/`, `--before 2026-10-13`) i compare w parach z
`data/refit_2026-10-13/bb_base` (holdout historii i linie Superbetu:
log-loss pewności i luka linii >= 0,70). **Bez instalacji i bez
włączania przełącznika.**

## Wynik (2026-10-13, `data/refit_2026-10-13/b7/{tune,history,superbet}.json`)

Historia z `data/audit_2026-10-13/bb_history.pkl` (51 168 meczów, ta sama co
A3 / C8 / A8), box score z kopii bazy: 29 480 meczów z posiadaniami w zakresie.

**Strojenie α** (2025-01-01..2025-06-01, 6 079 meczów ze ścieżką tempa,
MSE sumy regulaminu; punkty na tych samych meczach 269,12):

| α poss \ α ppp | 0,03 | 0,06 | 0,10 |
|---|---|---|---|
| 0,03 | 275,20 | 277,37 | 285,62 |
| 0,06 | 269,54 | 271,53 | 279,53 |
| 0,10 | **267,74** | 269,36 | 276,75 |
| 0,15 | 268,95 | 270,12 | 276,73 |

Wybrane `bb_poss` 0,10, `bb_ppp` 0,03 (`score_model.PACE_ALPHA`); zysk na
strojeniu 0,5% MSE. `bb_ppp` 0,03 leży na brzegu siatki - siatka była
zarejestrowana, nie rozszerzałem jej.

**Test A - historia 2025-10-01..2026-06-01**, 6 319 meczów (ścieżka tempa w
4 259), linie: suma 148,5 / 161,5 / 174,5, strona 72,5 / 80,5 / 89,5,
margines -6,5 / 4,5 / 14,5. Nowa - stara, 95% bootstrap po meczach:

| rodzina | Brier | log-loss | Brier stara / nowa |
|---|---|---|---|
| total | +0,00042 [-0,00043; +0,00129] | +0,00143 [-0,00097; +0,00380] | 0,1686 / 0,1690 |
| team_total | +0,00214 [+0,00142; +0,00282] | +0,00599 [+0,00413; +0,00785] | 0,1699 / 0,1720 |
| handicap | +0,00404 [+0,00309; +0,00498] | +0,01091 [+0,00846; +0,01332] | 0,1731 / 0,1772 |
| zwycięzca | +0,00584 [+0,00449; +0,00716] | +0,01486 [+0,01156; +0,01803] | 0,1979 / 0,2037 |

Tylko mecze ze ścieżką tempa (4 259): total Brier +0,00076 [-0,00048;
+0,00198], zwycięzca +0,00863 [+0,00668; +0,01044]. Kalibracja totalu
p >= 0,70: stara 0,850 / realizacja 0,843 (n 11 630), nowa 0,852 / 0,841
(n 11 767).

**Test B - linie Superbetu 2026-09-29..2026-10-12** (81 011 linii; p zmienione
na 36 896; mecze: total 1 245, handicap 1 239, team_total 572, zwycięzca
1 189). Nowa - stara:

| rodzina | Brier | log-loss | Brier stara / nowa |
|---|---|---|---|
| total | **-0,00417 [-0,00794; -0,00063]** | -0,00949 [-0,01774; -0,00163] | 0,2451 / 0,2410 |
| team_total | -0,00013 [-0,00332; +0,00306] | -0,00090 [-0,00751; +0,00590] | 0,2548 / 0,2547 |
| handicap | +0,00180 [-0,00164; +0,00501] | +0,00460 [-0,00315; +0,01189] | 0,2501 / 0,2519 |
| zwycięzca | +0,00346 [+0,00105; +0,00586] | +0,00801 [+0,00254; +0,01346] | 0,2100 / 0,2134 |

Linie główne (fair 0,45-0,55; cena tylko wybiera podzbiór): total 5 798 linii
/ 1 244 mecze **0,2593 -> 0,2562**, -0,00312 [-0,00675; +0,00032] (stara
liczba audytu 0,2593 odtworzona); handicap 0,2636 -> 0,2661; team_total
0,2588 -> 0,2601; zwycięzca (288) 0,2468 -> 0,2475. Wszystkie nadal > 0,25.

## Werdykt: **próg NIESPEŁNIONY**

- Test A: `total` - przedział Briera i log-loss obejmuje zero (brak
  poprawy); zwycięzca **gorszy** (dolna granica +0,00449 > 0). Handicap i
  team total też gorsze.
- Test B: `total` lepszy (przedział poniżej zera), ale zwycięzca gorszy
  (przedział w całości powyżej zera).

Refitu krzywej (`data/refit_2026-10-13/b7/`) i compare z `bb_base` **nie
wykonano** - zgodnie z rejestracją warunkiem był spełniony próg. Przełącznik
`BB_PACE_FROM_UTC` zostaje `None`; kod zostaje jako wyłączona opcja
(bajt w bajt identyczny model, test `test_off_is_byte_identical_...`).

Odczyt (podejrzenie, niezmierzone): wolna α efektywności (0,03 wobec 0,06
punktów) spłaszcza różnice sił drużyn - stąd gorszy zwycięzca i handicap -
a tempo poprawia tylko poziom sumy, i to na październikowych liniach rynku,
nie na historii. Kolejny test (nowa rejestracja, nowe dane): tempo z
box score tylko jako mnożnik sumy (centrum różnicy z ratingu punktów).

Zastrzeżenia:
- Box score koszykówki nie jest pobierany na bieżąco (2026-10: 4 z 1 334
  meczów); na liniach 09-29..10-12 ratingi tempa są z września lub starsze
  (reguła 60 dni). Włączenie na żywo wymagałoby codziennego
  `backfill_event_stats.py --sport basketball`.
- Posiadania Olivera w wersji prostej (bez udziału zbiórek rywala); jedna
  dogrywka zakładana przy skalowaniu.
- 1 000 symulacji na mecz i model, to samo ziarno w parze.
