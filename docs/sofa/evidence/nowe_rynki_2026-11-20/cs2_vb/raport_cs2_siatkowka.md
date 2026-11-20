# Nowe rynki Superbetu: CS2 i siatkówka - walidacja (2026-11-20)

Badanie tylko do odczytu. Nic w repo nie zmienione, nic nie zatwierdzone. Baza `data/sofa.db` otwierana `mode=ro`, zapytania po kluczu / indeksie (`cs2_series`, `cs2_map`, `sofa_listed_event` po `sport`). Jedno zapytanie na żywo do Superbetu (zdarzenie 16011396, odczyt pola `info` rynku 231528). Skrypty i wyniki: `/private/tmp/claude-501/-Users-mkoziol-projects-bet/04c6201e-4497-4273-b02c-92e4cd7d7f51/scratchpad/cs2_vb/`.

## Wnioski w skrócie

| sport | najlepszy kandydat | czy coś wydrukuje | przewaga nad ceną | werdykt |
|---|---|---|---|---|
| CS2 | 231528 "Liczba dogrywek" **Poniżej 0.5** (cała seria) | tak, ~3 nogi/dzień po ~1.26 | brak: model nie lepszy od ceny (Brier +0.0057 [-0.0023, +0.0148], 52 serie); statystyka nie odróżnia dobrej 1.26 od złej (sd p 0.028) | skalibrowany „wypełniacz”; nie warto dla przewagi, tylko gdy operator chce więcej nóg CS2 |
| siatkówka | 230059 "1.Set/Mecz", wybór **faworyt wygra 1. seta i mecz** | tak, ~4-5 nóg/dzień (weekendy), kursy 1.12-1.63 | brak: model nie lepszy od ceny (Brier +0.0043 [-0.0006, +0.0093], 286 meczów); dodatni ROI okna = ogólna nadwyżka faworytów, widoczna też na rynku zwycięzcy | możliwy, skalibrowany na historii; przewagi nie ma |

Reszta kandydatów: albo to samo zdarzenie co rynek już czytany, albo cena nigdy nie dochodzi do 0.70 (szczegóły niżej).

## Dane

- `extract.py` -> `unmapped_candidates.jsonl`: 54 776 notowań rynków kandydujących z `runs/sofa/2026-11-*/unmapped_prices/{cs2,volleyball}_*.jsonl.gz` (pliki CS2 od 11-06, siatkówki od 11-05).
- Dla każdego zdarzenia brane jest **ostatnie notowanie przed startem**. Start pochodzi z `runs/sofa/cs2/<d>/snapshots.jsonl` i `runs/sofa/shadow/volleyball/<d>/snapshots.jsonl`.
- Przypięte id: CS2 z `runs/sofa/<d>/sport_fixtures.json`, siatkówka z `runs/sofa/shadow/volleyball/<d>/settled.json` (`pinned_id`, `home_is_team1`, `t1_periods` w orientacji team1 Superbetu).

## 1. CS2 "Liczba dogrywek" (231528)

### Zakres i kształt
- Rynek dwudrogowy na linii 0.5: "Poniżej 0.5" / "Powyżej 0.5", `specifiers: {"total": "0.5"}`. Pole `info` (żywy odczyt zdarzenia 16011396): „Poniżej 0.5 dogrywek”, bez numeru mapy. Nie ma też żadnego rynku dogrywek na poziomie mapy: przeszukano wszystkie `marketName` CS2 z „dogryw” bez sufiksu „(z dogrywką)”.
- **Zakres = cała seria (wniosek).** Mapa nierozegrana niczego nie dodaje (2-0 w BO3 ma 2 mapy). Tekstu Regulaminu dla tego rynku nie sprawdzałem.
- Wolumen: 58 zdarzeń w 15 dniach (11-06..11-20), 1-11 dziennie, średnio ~3,9 (`cs2_ot_events.py`).
- Turnieje: BLAST Rivals 13, StarLadder Ranked 13, PGL Cluj-Napoca Open Qualifier 12, RUSH:Brno 10, IEM Beijing 5, EPL Asia 2, ESL Challenger EU 2, NODWIN 1.
- Format: BO3 50, BO5 2, nieznany 6. BO1 w ofercie nie wystąpił.
- Marża: średnio 0.089 (0.082-0.099), więc reguła 15% przechodzi. Kurs "Poniżej" 1.18-1.30, mediana 1.26. Fair p(Poniżej) mediana 0.725 (kwantyle 0/10/50/90/100%: 0.603 / 0.721 / 0.725 / 0.747 / 0.772).

### Rozliczalność
- Dogrywka na mapie: przy MR12 wynik w regulaminowym czasie ma najwyżej 24 rundy (13-11), a pierwsza dogrywka kończy się przy co najmniej 28. Stąd **OT ⇔ home_rounds + away_rounds >= 25**.
- Sprawdzone dwoma sposobami na `cs2_map` (skończone mapy skończonych serii):
  - 28 198 map z rundami; OT według sumy rund 3 236, według kolumn `home/away_overtime` 3 238;
  - tylko 2 wiersze sprzeczne, oba to defekty danych: 15731081 (10-13 z kolumnami OT) i 16214532 (0-0 z OT);
  - map MR15 brak: każda mapa z maks. 16 rundami ma min. >= 12.
- Pokrycie w historii: kompletne rundy wszystkich map ma ~78% skończonych serii BO3 (2026-02..11, miesięcznie 0.69-0.82; listopad niepełny).
- Na zdarzeniach z oferty: **52 z 58 rozliczalne**. Pozostałe 6: 3 nieprzypięte (NOT_IDENTIFIED) i 3 przypięte, ale serii jeszcze nie ma w `cs2_series`. Na 52 serie OT według sumy rund = OT według kolumn (16/52).
- Pułapka wdrożeniowa: `settle_cs2` przy `series_only_maps` ocenia tylko `cs2.SERIES_FAMILIES` (`scripts/sofa/settle_cs2.py:346`). Nowa rodzina **nie może** tam trafić, bo placeholdery 1-0 oceniłyby się jako „bez dogrywki”.

### To samo zdarzenie co rynek czytany?
- **BO1:** "Poniżej 0.5 dogrywek" ⇔ "1. mapa - Liczba rund" PONIŻEJ 24.5, a ta linia jest czytana (`map_rounds_total`, 9 132 notowania 24.5 w snapshotach CS2). To jedno zdarzenie, więc wymaga wpisu w `leg_identity` (SAME_EVENT_DEDUP). W ofercie 11-06..11-20 BO1 nie było.
- **BO3/BO5:** żadna czytana rodzina nie jest tym zdarzeniem. `map_rounds_total` dotyczy jednej mapy, a `rounds_total` serii to inna wielkość.

### Model i kalibracja na historii
- Narzędzie: `cs2_ot_walkforward.py`. p mapy pochodzi z odtworzenia jak przy dopasowaniu krzywej (`sport_confidence.cs2_walk_forward_rows`: Elo, kalibracja co 7 dni, stan na start serii).
- Dwa warianty P(brak OT w serii):
  - **race**: `series_distribution_mixed(p, bo)` (SERIES_KAPPA 6) × P(brak OT | zwycięzca mapy) z wyścigu rund (`cs2_engine._race_dist`);
  - **base**: ten sam rozkład liczby map × (1 - udział OT wszystkich wcześniejszych map, LOOKBACK).
- Okno 2026-02-01..11-20: 7 812 serii (BO3 7 186, BO1 547, BO5 79). Nieocenione: 3 115 bez ratingu, 4 137 z niekompletnymi rundami (`cs2_ot_analyse.py`).

| | n | realizacja „bez OT” | p race | p base | realizacja - race | log loss race - base |
|---|---|---|---|---|---|---|
| BO3 | 7 186 | 0.744 | 0.756 | 0.749 | -1.24 pp [-2.22, -0.29] | -0.00021 [-0.00099, +0.00056] |
| BO1 | 547 | 0.890 | 0.892 | 0.886 | -0.13 pp [-2.71, +2.43] | ~0 |
| BO5 | 79 | 0.595 | 0.637 | 0.628 | -4.2 pp [-14.7, +6.7] | +0.0011 |

- **Druga droga** (sam SQL, bez ratingu, serie BO3 „Ended” 02-01..11-20 z kompletnymi rundami): 8 312 serii, bez OT 0.752. Seria 2-mapowa 0.804, 3-mapowa 0.677. Zgodne z 0.744 z odtworzenia (inny podzbiór: w SQL także pary bez ratingu).
- OT na mapę według faworyta: [0.5,0.6) realizacja 0.120 (race 0.114), [0.6,0.7) 0.113 (0.108), [0.7,0.8) 0.107 (0.096), [0.8,0.9) 0.068 (0.077). Zależność od siły par istnieje, ale jest słaba.
- **p prawie stałe**: BO3 p_race w 0.70-0.80, w praktyce 0.75-0.76; po miesiącach 0.753-0.760, a realizacja miesięczna 0.697-0.764 (szum).
- Poziom turnieju nic nie zmienia (`cs2_ot_tier.py`): te same `unique_tournament_id` co w ofercie dają bez OT 0.748 (n 2 393); pozostałe 0.738 (n 5 189).
- **Wniosek o dyskryminacji:** model z wyścigiem nie jest lepszy od stałej. Krzywa dopasowana na historii da pewność ~0.74 każdej serii BO3, więc nie odróżni dobrej 1.26 od złej.

### Model a cena Superbetu (52 przypięte serie z oferty, `cs2_ot_vs_price.py`)
- Realizacja „Poniżej” 0.692; model 0.751; fair 0.726; średnie 1/kurs 0.790.
- Brier model - fair **+0.0057 [-0.0023, +0.0148]**; log loss +0.0168 [-0.0054, +0.0433]. Model nie jest lepszy od ceny.
- Korelacja p modelu z fair 0.853: Superbet też wycenia bliskość par i format.
- Realizacja - model -5.9 pp [-19.4, +6.3]; mała próba.

### Bramki
- Krzywej dla tego klucza nie dopasowałem. Przybliżenie: pewność = p + wspólny offset CS2 -1.64 pp (`config/sofa_superbet_line_evidence.json`, `sport_printable.cs2`, fit przed 11-20). CS2 nie korzysta z PRICE_GAP_OFFSET, a nowy klucz nie ma jeszcze własnych linii.
- Wynik: 48 z 52 przechodzi (pewność >= 0.70, x >= 0.90, marża <= 15%). Trafienia 0.667 przy 1/kurs 0.794; ROI -16.0% [-34.3, -0.1] przed podatkiem, -26.1% po 12%.
- Oczekiwanie z historii: 0.744 × 1.26 = 0.937, czyli **-6.3% przed podatkiem i -17.5% po**. To nie jest przewaga, tylko kurs z marżą.
- Próg x >= 0.90 przy pewności ~0.725 wymaga kursu >= 1.24. W ofercie to ~75-80% zdarzeń, czyli **~3 nogi/dzień**.

### Inne rynki CS2 z listy
- **231535** "Drużyna - najwięcej wygranych rund w meczu" (1X2) i **231548** "Podwójna szansa rundy": "1" = rundy T1 > T2 ⇔ `rounds_handicap` T1 -0.5; "1X" ⇔ T1 +0.5. Linie ±0.5 `rounds_handicap` są czytane (snapshoty: -0.5 ×772, +0.5 ×290). **To samo zdarzenie**, więc odrzucone (nie mierzone).
- **235657/235658** liczba zabójstw na mapie: 0 notowań w strefie, linie ~50/50 (135.5-138.5). Nic nie wydrukuje.
- **231557** "X mapa - podwójna szansa": wycenia remis mapy (np. "FURIA lub BetBoom" 1.08, czyli ~7% na remis). Semantyka niejasna (remis mapy w CS2?), tylko 16 zdarzeń. Odrzucone do czasu sprawdzenia Regulaminu.
- 231533 parzystość rund: model jej nie wycenia (model-state); poza zakresem.

## 2. Siatkówka

### 2a. "Czy będzie 5. set?" (200849) / "Czy będzie 4. set?" (200852)
- Logicznie to `sets_total` 4.5 / 3.5 (tak = POWYŻEJ). SHADOW czyta `sets_total` (230058, `shadow.MARKETS["volleyball"]`). Złoty set nie liczy się w żadnym z nich (5.D.3.a).
- `vb_same_event.py`: 720 notowań złączonych z tym samym snapshotem SHADOW (ten sam `fetched_at`), w ostatnim notowaniu 94 zdarzenia.
- Fair p(tak) - p(POWYŻEJ): średnio +0.006 (5. set) i +0.011 (4. set); maks. |różnica| 0.055-0.057.
- Marża tak/nie 0.086 wobec 0.076 dla `sets_total`.
- Kurs tak/nie wyższy po stronie „nie” w 22 z 94 (5. set) i 39 z 94 (4. set); po stronie „tak” w 5 i 4.
- **Werdykt: to samo zdarzenie, odrzucone.** Najwyżej alias cenowy przez SAME_EVENT_DEDUP (wyższy kurs wygrywa). Zysk znikomy, nie mierzony.

### 2b. Rozkład cen fair (ostatnie notowanie przed startem, `vb_price_dist.py`)

| rynek | zdarzenia | marża | fair p 50% / 90% / 99% / maks. | wybory fair >= 0.70 |
|---|---|---|---|---|
| 230059 1.Set/Mecz (4 wybory) | 307 | 0.136 | 0.175 / 0.577 / 0.757 / 0.82 | 44 (wszystkie: faworyt wygra seta i mecz; kursy 1.11-1.28, mediana 1.21) |
| 786 1. set - handicap punkty | 306 | 0.092 | 0.50 / 0.607 / 0.667 / 0.678 | **0** |
| 100080 / 100081 punkty drużyny | 126 / 126 | 0.086 | 0.484-0.516 | **0** |
| 240723 wynik po 3 setach | 31 | 0.136 | maks. 0.572 | 0 |
| 240724 wynik po 2 setach | 31 | 0.111 | maks. 0.664 | 0 |
| 235045 1. set dokładny wynik | 31 | 0.357 | maks. 0.225 | 0 |

- **786 i punkty drużyny** Superbet ustawia na ~50/50, więc noga wydrukuje się tylko wtedy, gdy model odbiega od ceny o 15+ pp.
- Na ofercie (`vb_measure.py` + `vb_analyse.py`), set-1 handicap przy p >= 0.70 (65 nóg / 52 mecze): deklarowane 0.751, realizacja 0.600, czyli -15.1 pp [-29.5, -0.8]. To ta sama nadobietnica co pełny handicap punktowy (model-state: -19.7 pp).
- Na historii model jest skalibrowany na własnych liniach, ale gorzej na liniach minusowych: -2.5..-7.5 realizacja 0.71-0.77 przy 0.79-0.80 (`vb_joint_hist_analyse.py`; CI nie grupowane po meczu).
- Brier model - fair: 786 +0.0053 [-0.0054, +0.0171]; punkty drużyny -0.0003 / +0.0021 (CI ±0.02).
- **Werdykt: odrzucone.**

### 2c. "1.Set/Mecz" (230059): wspólny rozkład zwycięzcy 1. seta i meczu
- **Model:** `volleyball_point_model.simulate` zwraca punkty każdego seta w każdej symulacji (`VbSim.points [S,5,2]`). Wspólny rozkład liczy się więc wprost: (P[:,0,0] > P[:,0,1]) × (sety team1 > sety team2), 4 000 symulacji z ziarnem = id meczu, jak `vb_point_pricer.VbPricer`.
- **Rozliczenie:** 1. set z `t1_periods[0]` vs `t2_periods[0]`, mecz z `winner` w `settled.json`. Złoty set jest już wyłączony (`shadow.GOLDEN_SET_DESCRIPTIONS`, zwycięzca z setów).
- **Nazwy:** "A/B" = zwycięzca 1. seta / zwycięzca meczu. Nazwy drużyn mogą zawierać "/" (ABEL/Moda), więc parser musi porównywać z dokładnym `f"{team1}/{team2}"`.
- **Pokrycie:** 307 zdarzeń. 286 rozliczalnych z przypięciem i prognozą. Pozostałe: 88 grup nieprzypiętych lub nierozliczonych, po 2 z NO_PRE_START_PRICE i DUPLICATE_SOFASCORE_ID.

#### Historia (kalibracja modelu na wspólnym rozkładzie)
- `vb_joint_history.py`: walk-forward 2026-03-01..11-20, czyli po strojeniu parametrów (< 03-01). Co 4. mecz, obie strony widziane >= 5 razy, `vb_point_pricer.PARAMS`. Daje 3 359 meczów.
- Historia wczytana tylko z indeksu `sofa_listed_event` (101 966 meczów, `load_vb_history.py`), bez skanu stron.
- Wszystkie 4 wybory, pasma co 0.1: przerwa w [-1.3, +0.7] pp z CI obejmującym 0. Wyjątek to pasmo [0.9, 1.0): -4.5 pp [-8.8, -0.6].
- **p >= 0.70** (zawsze faworyt seta i meczu): n 1 019 (~30% meczów), deklarowane 0.823, realizacja 0.816, **-0.7 pp [-3.2, +1.5]**.
- P(zwycięzca 1. seta = zwycięzca meczu): model 0.794, realizacja 0.782.

#### Oferta (286 meczów; `vb_analyse.py`)
- Brier model - fair (wszystkie 4 wybory, bootstrap po meczu): **+0.0043 [-0.0006, +0.0093]**; log loss +0.0071 [-0.0059, +0.0200]. Model nie jest lepszy od ceny.
- Faworyt „seta i meczu” (286): model 0.565, fair 0.540, 1/kurs 0.613, realizacja 0.664.
- Bramki na surowym p modelu (bez krzywej; krzywa z historii ≈ tożsamość przy -0.7 pp; wspólny offset siatkówki -0.49 pp):
  - **68 nóg / 68 meczów** (~4,5/dzień, skupione w weekendy: 11-07 23, 11-14 11, 11-15 11);
  - kursy 1.12-1.63; kobiety 31, mężczyźni 37;
  - trafienia 0.809 przy 1/kurs 0.746 (p 0.780);
  - ROI +7.6% [-5.3, +20.0] przed podatkiem, -5.3% po 12%;
  - 10 z 286 grup ma marżę > 15% (reguła je odrzuca).
- **Sprawdzenie dodatniego ROI drugą drogą** (`vb_joint_vs_winner.py`: ten sam snapshot, rynki czytane 745 zwycięzca i 744 zwycięzca 1. seta), 281 meczów:
  - faworyt wygrał mecz 0.826 przy fair 0.724 (+10.2 pp), a 1. seta 0.722 przy fair 0.651 (+7.1 pp);
  - wszystkie mecze siatkówki SHADOW 11-05..11-19 (`settled.json`, 745): faworyt 0.779 przy fair 0.733 (+4.6 pp, n 992); 10-05..11-04: +3.7 pp (n 1 853).
  - **Nadwyżka okna to nadwyżka faworytów na rynku zwycięzcy, który już czytamy, a nie cecha rynku 4-drogowego.** Model nie przewidział jej lepiej niż cena.
- To samo zdarzenie? „Faworyt wygra 1. seta i mecz” to część wspólna dwóch czytanych nóg (745 i 744 s1), nie żadna z nich. Tożsamości nie ma, jest **ekspozycja** na ten sam mecz.

## 3. Wybór po jednym na sport i szkic wdrożenia (nie wdrażam)

### CS2: "Liczba dogrywek" (rodzina np. `series_overtimes`, OVER/UNDER 0.5)
1. `src/bet/sofa/cs2.py`:
   - `parse_line`: "Liczba dogrywek" -> `Cs2Line(family="series_overtimes", map_nr=0, line=0.5, side=OVER/UNDER)`; dopisać do `_READ_MARKET_NAMES`;
   - `actual_value`: liczba rozegranych map z `t1_rounds + t2_rounds >= 25`; None, gdy brak rund. Odmawiać przy sprzeczności (np. suma >= 25 przy maks. < 16);
   - rodzina **poza** `SERIES_FAMILIES` (placeholdery `series_only_maps`).
2. `src/bet/sofa/cs2_engine.py`: `series_overtime_p(p_map, best_of, line, side)` = Σ `series_distribution_mixed(p,bo)[a,b]` × n1^a × n2^b. Zalecany wariant **base**: (1 - udział OT historii)^(a+b), jak `base_rate` w `map_rounds_total`. Surowy -0.46 pp [-1.44, +0.49] wobec -1.24 dla race, log loss bez różnicy. Gałąź w `model_probability` pod flagą.
3. `src/bet/sofa/epochs.py`: `CS2_SERIES_OVERTIME_FROM_UTC` = 00:00Z dnia następującego po zgodzie operatora; `run_sport_confidence` przekazuje flagę.
4. `sport_confidence.cs2_walk_forward_rows`: wiersze rodziny na linii 0.5.
5. `fit_sport_confidence.py --sport cs2` na **kopii bazy**: nowe klucze `series_overtimes|UNDER/OVER` w nowym datowanym `config/sofa_sport_confidence_calibration.next.<D>.json`, pozostałe klucze bajt w bajt.
6. Line evidence narasta z CS2_SETTLE (do 50 linii / 15 gier offset wspólny -1.64 pp).
7. `src/bet/sofa/leg_identity.py`: BO1 `series_overtimes` UNDER 0.5 ≡ `map_rounds_total` mapa 1 UNDER 24.5 (OVER ≡ OVER); tylko przy `best_of == 1`.
8. `superbet_names`: brzmienie „Liczba dogrywek: Poniżej 0.5”.
9. Testy (`tests/sofa/`): parsowanie; ocena (16-14 = OT, 13-11 brak, 2-0 BO3, placeholder odmówiony, sprzeczny wiersz odmówiony); suma p = 1; tożsamość BO1; wyłączony przełącznik daje bajt w bajt.
10. Nakład: ~1 dzień kodu i testów plus ~1 h refitu krzywej CS2 na kopii.

### Siatkówka: "1.Set/Mecz" (rodzina np. `set1_match`, wybory T1T1 / T1T2 / T2T1 / T2T2)
1. `src/bet/sofa/shadow.py`: 230059 w `MARKETS["volleyball"]` z nowym rodzajem grupy 4-drogowej; nazwy porównywane z dokładnym `f"{team1}/{team1}"` itd. (nazwy z "/"). Fair z `group_fair` (cała grupa) i kompletność grupy. `actual_value`: (1. set, mecz) z setów meczu, bez złotego seta.
2. `src/bet/sofa/volleyball_point_model.py`: `actual_values` dla nowego rodzaju (wektorowo, jak wyżej); `vb_point_pricer.in_scope` przez nowy przełącznik `epochs.VB_SET1_MATCH_FROM_UTC` (00:00Z dnia po zgodzie), rynek w zakresie modelu wymian.
3. Krzywe: rozszerzyć `scripts/sofa/measure_volleyball_point_model.py` (walk-forward wierszy) i dopasować klucze (`set1_match|SAME`, `set1_match|SPLIT` lub po stronie) do `config/sofa_volleyball_point_curves.json` (nowa wersja, dzień po zgodzie). Line evidence przez `backfill_vb_point_p.py` (klucz w zakresie).
4. `leg_identity`: brak tożsamości (część wspólna dwóch nóg); ekspozycja zostaje sekcją „ekspozycja na mecz”.
5. Testy: parsowanie z "/" w nazwie, ocena ze złotym setem, suma 4 wyborów = 1, wyłączony przełącznik daje bajt w bajt, marża > 15% odmówiona.
6. Nakład: ~1,5 dnia plus walk-forward krzywej (~2 min na 1/4 historii, całość ~10 min).

**Rekomendacja:** żaden z dwóch rynków nie ma zmierzonej przewagi nad ceną. Oba spełniają reguły pipeline'u (skalibrowane na historii, rozliczalne, marża <= 15%), więc drukowałyby się jako nogi „cena z marżą”: CS2 ~3/dzień, siatkówka ~4-5/dzień. Wdrożenie to decyzja operatora o liczbie nóg, nie o przewadze. CS2 dodatkowo łamie miarę „statystyka odróżnia dobrą 1.20 od złej”: pewność jest praktycznie stała.

## 4. Ryzyka i rzeczy niesprawdzone
- Zakresu „Liczba dogrywek” nie sprawdziłem w tekście Regulaminu; `info` mówi tylko „Poniżej 0.5 dogrywek”. Seria i „mapa nierozegrana nic nie dodaje” to wnioski.
- Turnieje MR15 / bez dogrywek: w cache żadnych, ale przyszły taki mecz oceniłby się źle bez strażnika.
- Krzywej CS2 ani siatkówki nie dopasowałem. Pewność przybliżona przez p + wspólny offset; liczba nóg przechodzących bramki jest szacunkiem.
- Okno ofert to tylko 11-05/06..11-20 (zapis `unmapped_prices` od 11-05): 52 serie CS2 i 286 meczów siatkówki. Przedziały szerokie.
- Historia siatkówki pochodzi z samego indeksu listingów (nie ze stron jak `score_model.load_events`); różnica niezmierzona. Historia co 4. mecz, filtr ratingu >= 5. CI handicapu na historii nie są grupowane po meczu.
- Odtworzenie CS2 ładuje historię od 2025-11-21 (LOOKBACK 365 od 11-21). Styczeń 2026 ma krótszy rozbieg Elo, a ocena startuje od 02-01.
- Ceny wzięte z ostatniego notowania przed startem, nie z ceny druku; kurs zamknięcia nie badany.
- 6 z 58 serii CS2 z oferty nierozliczalnych (3 nieprzypięte, 3 jeszcze nie w cache). Pokrycie rund w historii ~78% serii BO3.
- 231557 (remis mapy) i 231535/231548 nie mierzone (uznane za to samo zdarzenie / niejasne).
- Nadwyżka faworytów siatkówki (+4.6 pp w 992 meczach 11-05..11-19) to trop dla rynku zwycięzcy, nie dla tego badania. Niezweryfikowana poza oknem.
- 12% podatek liczony jako 0.88 × wypłata.

## Skrypty (scratch)
`extract.py`, `cs2_ot_events.py`, `cs2_ot_walkforward.py`, `cs2_ot_analyse.py`, `cs2_ot_tier.py`, `cs2_ot_vs_price.py`, `vb_same_event.py`, `vb_price_dist.py`, `load_vb_history.py`, `vb_measure.py`, `vb_analyse.py`, `vb_joint_vs_winner.py`, `vb_joint_history.py`, `vb_joint_hist_analyse.py`. Wyniki pośrednie: `cs2_ot_events.json`, `cs2_ot_wf_rows.jsonl`, `vb_rows.jsonl`, `vb_joint_hist.jsonl`, `vb_history.pkl`.

## 5. Uzupełnienie: CS2 231535 / 231548 (handicap rund serii ±0.5) - zmierzone

**Korekta wcześniejszej sekcji.** Pisałem, że ±0.5 `rounds_handicap` jest czytane, więc oba rynki to „to samo zdarzenie”. Na tych zdarzeniach to nieprawda. W snapshotach CS2 (`runs/sofa/cs2/<d>/snapshots.jsonl`) linia |line| < 1.5 istnieje tylko na 6 z 58 zdarzeń z 231535; na 52 Superbet daje handicap rund serii od ±1.5. Rynki są więc nieczytanymi wersjami czytanej rodziny:
- "1" = T1 -0.5, "2" = T2 -0.5 (231535);
- "1X" = T1 +0.5, "X2" = T2 +0.5 (231548).

Wszystkie z dogrywką, jak `cs2.actual_value` dla `rounds_handicap`. Skrypt: `cs2_rounds_dc.py`; wiersze: `cs2_rounds_dc_rows.json`.

### Kształt, wolumen, marża
- 231535 (1 / X / 2): 58 zdarzeń, marża 3-drogowa średnio 0.124 (0.112-0.147).
- 231548 (1X / X2): 39 zdarzeń. Marża pary „DC + przeciwny wynik 1X2” (1X z "2", X2 z "1", jak `shadow` DC_PAIR dla koszykówki): 0.073 (0.060-0.079).
- Fair 1X: de-vig pary minus de-vig 3-drogowy (f1 + fX) = -0.019 (sd 0.007, n 30). Wynik Briera prawie się od tego nie zmienia (+0.0289 vs +0.0278).
- Remis rund (X) w BO3: model 0.0184, realizacja 0.0175 (7 186 serii). Zgodne, drugie wyprowadzenie z historii.
- Rozliczalne: 52 zdarzenia (3 nieprzypięte, 3 jeszcze nie w cache). Ocena: suma rund T1 - T2 po rozegranych mapach (`cs2_ot_wf_rows.jsonl`, orientacja z `home_is_team1`).

### Model (ścieżka na żywo)
`cs2_engine.series_rounds_side_p(p_t1, best_of, "rounds_handicap", ±0.5, side)`, gdzie p mapy pochodzi z odtworzenia jak przy dopasowaniu krzywej (`sport_confidence.cs2_walk_forward_rows`, stan na start). To ta sama funkcja, która wycenia czytane linie, a ±0.5 należy do `CS2_SERIES_ROUND_LINES` BO3, więc istniejąca krzywa `rounds_handicap|TEAM` była na niej dopasowana.

### Kalibracja na historii (2026-02-01..11-20)
- BO3: 28 744 wierszy, pasma 0.1 z przerwą w [-1.5, +1.5] pp, każde CI obejmuje 0.
  - **p >= 0.70: n 3 042 (1 685 serii), deklarowane 0.763, realizacja 0.774, +1.1 pp [-1.0, +3.0].**
  - Po stronie: "1" 0.765/0.779, "2" 0.751/0.772, "1X" 0.766/0.772, "X2" 0.751/0.769.
- BO1 (1 = 1X, remis rund niemożliwy na jednej mapie): p >= 0.70 n 152, +5.7 pp [-3.7, +14.1].
- BO5: n 37, +6.7 pp [-10.8, +20.3].
- Model zmienia się mocno między meczami: na ofercie sd p 0.149-0.171 (dla porównania „Liczba dogrywek” 0.028).

### Model a cena (52 zdarzenia, bootstrap po meczu)

| strony | wiersze / mecze | Brier model - fair | log loss model - fair | realizacja - model | realizacja - fair | korelacja p z fair | sd(p - fair) |
|---|---|---|---|---|---|---|---|
| "1"/"2" (-0.5) | 104 / 52 | +0.0006 [-0.0357, +0.0356] | +0.0140 [-0.0695, +0.0963] | -1.0 pp [-3.9, +0.9] | +0.3 pp | 0.597 | 0.130 |
| "1X"/"X2" (+0.5) | 60 / 30 | +0.0301 [-0.0215, +0.0803] | +0.0844 [-0.0359, +0.2087] | +0.8 pp | +1.4 pp | 0.659 | 0.140 |

- **Czy model odróżnia dobrą 1.20 od złej?** Odróżnia mecze od siebie, ale jego rozbieżność z ceną nie niesie informacji.
  - Wiersze, gdzie model > fair o 0.05+ (n 66): trafienia 0.409, fair 0.418, model 0.556. Realizacja idzie za ceną, model obiecuje 15 pp za dużo.
  - Gdzie model < fair o 0.05+ (n 50): trafienia 0.520, fair 0.554, model 0.412.
  - Wiersze w meczu są komplementarne, więc zdarzenia liczą się podwójnie.
- Spójne z line evidence dla czytanych linii tego klucza (`config/sofa_superbet_line_evidence.json`, `keys.cs2["rounds_handicap|TEAM"].printable`): 36 linii / 36 gier, pewność 0.736, realizacja 0.444 (-29.1 pp [-45.7, -12.8]). Przy n < 50 nie stosuje się własnego offsetu, tylko wspólny -1.64 pp.

### Bramki (pewność >= 0.70, x >= 0.90, marża <= 15%, bez górnej granicy kursu)
- **Na pewności, jaką SPORT_CONFIDENCE wydrukowałby 2026-11-20** (krzywa `config/sofa_sport_confidence_calibration.next.2026-11-07.json` `rounds_handicap|TEAM` + line evidence, odczyt jak `run_sport_confidence.read_confidence`):
  - p 0.70-0.75 daje 0.712 - 0.016 = **0.696**, czyli poniżej progu; p >= 0.75 daje 0.78-0.875;
  - limit pasma cenowego klucza tnie kursy 1.43+ (np. 0.683 i 0.455);
  - **3 nogi w 15 dni**: 15549995 "1" i "1X" po 1.21 (ten sam mecz, zagnieżdżone) oraz 15995336 "1X" 1.43. Wszystkie przegrane.
- **Na surowym p modelu:** 15 nóg / 9 meczów (kursy 1.14-2.15), trafienia 0.600 przy 1/kurs 0.736 (p 0.770, fair 0.673). ROI -18.2% [-65.2, +24.2] przed podatkiem, -28.0% po 12%.
- Nogi, które przechodzą, to przypadki „model powyżej ceny” (średnio fair 0.67-0.72 przy pewności 0.77-0.85), czyli dokładnie wzór, który na czytanych liniach tego klucza przeszacowuje o ~29 pp.

### Werdykt
**Nie warto.**
- Na historii model jest dobrze skalibrowany (BO3 >= 0.70: +1.1 pp), ale na cenie Superbetu nie jest od niej lepszy.
- Jego rozbieżności z ceną rozstrzygają się po stronie ceny.
- Przy realnej pewności przez bramki przeszłoby ~0.2 nogi dziennie, a te nogi to klasa nadobiecująca.

Wdrożenie byłoby tanie, bo rodzina, krzywa i ocena już istnieją (~0.5 dnia): 231548 jako `rounds_handicap` ±0.5 parowany z 1X2 (wzór DC_PAIR), "1"/"2" z 231535 jako -0.5 z marżą 3-drogową, przełącznik w `epochs` od 00:00Z następnego dnia, testy parsowania i orientacji. Nie rekomenduję. Jeśli kiedyś, to tylko z CS2 `price_gap` (już działa) i przy zagnieżdżeniu "1" ⊂ "1X" w jednym meczu jako ekspozycji (to nie jest ta sama noga dla SAME_EVENT_DEDUP).

### Niesprawdzone
- Krzywa i line evidence są z 11-20, a ich linie częściowo z tego samego okna (inne linie, te same tygodnie).
- 30-52 zdarzenia: przedziały szerokie.
- Ceny z ostatniego notowania przed startem, nie z druku.
- 6 zdarzeń z linią ±0.5 w snapshocie nie porównałem z ceną DC (alias cenowy).
