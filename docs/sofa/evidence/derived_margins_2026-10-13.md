# B3: brzegi jointu piłki bez kwotowanej drabinki strony (audyt 2026-10-13)

Przełącznik: `epochs.DERIVED_SHEET_MARGINS_FROM_UTC` (`derived_sheet_margins_v1`),
domyślnie `None`. Skrypt: `scripts/sofa/measure_derived_margins.py` (tylko odczyt).
Testy: `tests/sofa/test_audit_2026_10_13_b3.py`.

## Diagnoza (sprawdzona w kodzie, 2026-10-13)

- `scripts/sofa/run_sheet.py` (`process_fixture`, blok `marginal_centres`, za
  `price_derived_rungs` po wierszach marginalnych): centrum strony trafia do
  jointu **tylko z wiersza marginalnego**, a wiersz marginalny powstaje tylko
  dla szczebla, który Superbet kwotuje (`corners_for` z podmiotem strony).
- `src/bet/sofa/derived.py` (`price_derived_rungs`, `mc_a` / `mc_b`): joint
  bierze centra tylko wtedy, gdy są **obie**; z jedną brakującą obie strony
  wracają do surowej próbki (średnia i wariancja 10 ostatnich meczów strony:
  bez priora, bez K_CENTRE, bez ratingu, bez rywala).
- `derived.py` (gałąź `K_DERIVED_CENTRE`, `not stats_only`): kotwica handicapu
  w drabince jest wyłączona w epoce stats_only, więc nic innego nie poprawia
  tej różnicy.
- Przykład z 10-13 (`runs/sofa/2026-10-13/05_sheet.json`, zdarzenie 16864335):
  `handicap_corners` Kyoto -2,5 p 0,0598 przy `market_p` 0,5041;
  `most_corners` Kyoto p 0,141 przy 0,7211; `sample_mean` -3,8 (surowa różnica).
- `CROSS_LEAGUE_UNLINKED`: wiersze marginalne meczu bez łącza dostają notatkę
  i CONFIDENCE je odrzuca (`run_confidence.py`, `has_cross_league_unlinked_note`);
  wiersze pochodne tego samego meczu jej nie dostają.

## Zmiana (za przełącznikiem)

- `run_sheet.sample_centre`: wydzielona z `process_fixture` formuła centrum
  wiersza marginalnego (prior: dzień / ligi drużyn / pula kobiet / globalny;
  K_CENTRE, per rynek od `PER_MARKET_K`; potem `W_FOOTBALL_RATING` x rating).
  Wiersz marginalny liczy się nią dalej - jedna formuła, test złotego pliku
  `test_off_identical_head.py` przechodzi.
- `run_sheet.sheet_derived_margins` (tylko przy włączonym przełączniku i
  `DERIVED_MARGINAL_CENTRES`): strona metryki z `DERIVED_MARGINAL_CENTRES_METRICS`
  bez wiersza marginalnego dostaje centrum z `sample_centre` (strona cienka
  albo same zera - jak dotąd bez centrum). Wiersze pochodne dostają notatkę
  `SHEET_MARGIN: ...`, a stałe nie dopasowane (`W_FOOTBALL_RATING`, ...)
  dochodzą do ich `UNFITTED_CONSTANTS`.
- Mecz, którego metryka jest `UNLINKED` (ten sam warunek co dla wiersza
  marginalnego: `link_status(metryka) or fixture_link()`): każdy wiersz
  pochodny piłki dostaje notatkę `CROSS_LEAGUE_UNLINKED`, więc CONFIDENCE
  odrzuca go jak wiersze marginalne.
- **Nie zrobione (poza zakresem, nakłada się na odrzucone):** zależność stron
  zależna od różnicy sił (P3/M) - "per-league-class correlation" i kopuła t są
  na liście "Measured and declined"; wymagałaby nowej osi dowodu (O4).
  Rozszerzenie zbioru metryk o `shots_for` / `fouls_for` / `offsides_for` to C16.

## Rejestracja (zapisana 2026-10-13 przed uruchomieniem pomiaru)

### Test H (główny): historia, one step ahead

- Źródło: `data/cache/football_history.pkl` (sparsowana historia SHEET,
  `football_rating.load_history`), czytana bez zapisu.
- Rating: `football_rating.RatingBook` odtwarzany w kolejności czasu od
  początku historii, każdy mecz prognozowany **przed** jego aktualizacją
  (`FootballForecast(book, ...)`, reguła łącza z `epochs.link_shared_league`
  dla bieżącej daty = włączona).
- Próbka strony: 10 ostatnich wartości metryki strony sprzed meczu (gole:
  reguła tej samej rozgrywki, jak `measure_dependence_goals.collect_joint_inputs`),
  co najmniej 8 (`MIN_SAMPLE` replayu), obie strony nie same zera.
- Bazy: `goals`, `corners`, `shots_on_target`, `cards_points`
  (`DERIVED_MARGINAL_CENTRES_METRICS`), rho z `config/sofa_side_correlations.json`
  (kartki: null -> 0, jak SHEET przy `CARDS_CORRELATION` wyłączonym).
- Okno testu: mecze 2026-01-01..2026-10-12 (rating rozgrzany od początku
  historii). Na bazę losowo (ziarno 0) do 15 000 kwalifikujących się meczów
  (koszt jointu ~17 ms; liczba podana w wyniku).
- Modele (ten sam joint `joint.build_joint`, ta sama rho):
  - **OLD** - obie strony z surowej próbki (dzisiejsze zachowanie, gdy
    drabinki jednej strony brak);
  - **NEW** - obie strony formułą SHEET: prior `prior_for(baselines)`
    (replay; prior dnia z `resolve_prior` nie jest odtwarzany), K z
    `K_CENTRE.by_market` (PER_MARKET_K), potem 0,5 x centrum ratingu
    (`FootballForecast.centre`, gdy jest) + 0,5 x centrum próbki; wariancja
    `marginal_centred_stats` z dyspersją `config/sofa_count_dispersion.json`
    (COUNT_DISPERSION włączone od 10-09).
  - Mecze z metryką `UNLINKED`: NEW odmawia - **wyłączone z porównania**,
    raportowane osobno (liczba meczów i kalibracja OLD przy p >= 0,70).
- Zdarzenia (linie w stylu Superbetu, niezależne od wyniku): `both_over` na 7
  połówkach wokół min(średnich centrów obu modeli), handicap obu stron na 7
  połówkach wokół różnicy średnich centrów, `most` (gospodarz, gość, remis).
  Liczone tylko zdarzenia, w których **oba** modele mają p w [0,05; 0,95]
  (odmowa `OUTSIDE_MODEL_RESOLUTION` w SHEET).
- Metryka główna: średni log-loss na zdarzenie, różnica NEW - OLD, łącznie po
  bazach i klasach; 95% przedział z bootstrapu po meczach (2000 losowań,
  ziarno 0; iloraz sum).
- **Próg (O5): górna granica 95% różnicy log-loss NEW - OLD < 0.** Dodatkowo
  raportowane (nie decydują): Brier, każda baza x klasa (`both_over`,
  `handicap`, `most`), kalibracja obszaru do druku (p >= 0,70: realizacja -
  średnie p dla OLD i NEW, bootstrap po meczach).
- Zastrzeżenia zapisane z góry: (1) populacja to wszystkie mecze historii, a
  zmiana dotyczy tylko meczów bez drabinki strony - kontrfaktyczna różnica
  OLD vs NEW jest ta sama, ale mecze bez drabinki mogą być inne (niższe ligi,
  mecze ponadligowe); (2) bazowe średnie lig (`sofa_league_baselines.json`)
  i dyspersja są dopasowane na całej historii (patrzą w przód, jak w replayu
  krzywych); (3) prior dnia (`resolve_prior`) nie jest odtwarzany.

### Interakcja z bramkami kształtu (A5)

Operator: model meczowy mierzyć razem z `MODE_LOSES`, `LINE_BEYOND_SAMPLE`,
`MODEL_ABOVE_OWN_SAMPLE`. Dla wiersza pochodnego CONFIDENCE czyta próbkę po
nazwie rynku wiersza (`run_confidence.side_observations`:
`samples[...]["metrics"].get(row["market"])`), a `03_samples.json` nie ma
kluczy `both_over_*` / `most_*` / `handicap_*` (sprawdzone na 10-13: tylko
metryki `*_for` / `*_total`). Lista wartości jest więc pusta i:
- `line_is_beyond_sample`, `mode_loses` zwracają `False`,
  `model_above_own_sample` zwraca `None` (mniej niż `MIN_OWN_SAMPLE`) -
  **0 wierszy zdejmowanych przy starym i nowym p**, z konstrukcji;
- ale `len(values) < MIN_BUILDER_SAMPLE` (10) -> `THIN_SAMPLE_FOR_BUILDER`
  odrzuca **każdy** wiersz pochodny, który przejdzie próg pewności i ceny.

Sprawdzone wykonaniem (skrypt roboczy, nie w repozytorium; `run_confidence.main`
na dniu testowym z `tests/sofa/test_stats_only_confidence.py`, odczyt dowodu
linii podmieniony na 0,85): wiersz `goals_total` OVER 1,5 p 0,86 @1,40 -> na
kuponie; ten sam wiersz jako `both_over_goals` 0,5 -> `THIN_SAMPLE_FOR_BUILDER: 1`,
kupon pusty. Pomiar policzy, ile wierszy NEW / OLD przeszłoby próg pewności,
ale w obecnym kodzie żaden wiersz pochodny nie trafia na kupon niezależnie od
B3 (i od A4).

### Liczność populacji na żywo

Na dniach 2026-10-09..2026-10-13 (`05_sheet.json`, `04_offer.json`): liczba
wierszy pochodnych piłki z metryką z `DERIVED_MARGINAL_CENTRES_METRICS`, w
których jedna strona nie ma kwotowanej drabinki (brak wiersza marginalnego
`<metryka>_for` z podmiotem strony), i ile z nich ma mecz `UNLINKED`
(notatka na wierszach marginalnych meczu). Tylko liczność - bez ponownej wyceny.

## Wynik (2026-10-13, `measure_derived_margins.py`, 2000 losowań po meczach)

### Test H - historia, mecze 2026-01-01..2026-10-12, one step ahead

Populacja (mecze z próbką obu stron; `UNLINKED` poza porównaniem):

| baza | kwalifikujące się mecze | z ratingiem obu stron | UNLINKED (NEW odmawia) | ocenione (losowo) |
|---|---|---|---|---|
| goals | 206 919 | 206 917 | 5 764 | 15 000 |
| corners | 38 389 | 38 387 | 873 | 15 000 |
| shots_on_target | 33 039 | 33 039 | 708 | 15 000 |
| cards_points | 28 184 | 0 (rating nie ocenia kartek; samo K_CENTRE) | 573 | 15 000 |

Log-loss i Brier na zdarzenie, **NEW - OLD** (ujemne = NEW lepsze), 95%:

| baza / klasa | zdarzenia | log-loss NEW - OLD | Brier NEW - OLD |
|---|---|---|---|
| **łącznie** | **1 161 233 (60 000 meczów)** | **-0,0254 [-0,0264; -0,0245]** | -0,0100 [-0,0103; -0,0096] |
| both_over | 231 149 | -0,0298 [-0,0310; -0,0286] | -0,0112 [-0,0116; -0,0107] |
| handicap | 750 407 | -0,0256 [-0,0268; -0,0244] | -0,0099 [-0,0104; -0,0095] |
| most | 179 677 | -0,0191 [-0,0203; -0,0180] | -0,0085 [-0,0090; -0,0080] |
| goals / both_over | 34 298 | -0,0361 [-0,0392; -0,0330] | -0,0136 |
| goals / handicap | 163 137 | -0,0226 [-0,0248; -0,0203] | -0,0080 |
| goals / most | 44 860 | -0,0180 [-0,0203; -0,0157] | -0,0080 |
| corners / both_over | 74 938 | -0,0332 [-0,0356; -0,0309] | -0,0125 |
| corners / handicap | 203 031 | -0,0269 [-0,0295; -0,0243] | -0,0109 |
| corners / most | 44 942 | -0,0191 [-0,0215; -0,0168] | -0,0086 |
| shots_on_target / both_over | 74 585 | -0,0302 [-0,0325; -0,0278] | -0,0112 |
| shots_on_target / handicap | 198 584 | -0,0332 [-0,0358; -0,0305] | -0,0132 |
| shots_on_target / most | 44 880 | -0,0246 [-0,0270; -0,0222] | -0,0112 |
| cards_points / both_over | 47 328 | -0,0193 [-0,0215; -0,0173] | -0,0073 |
| cards_points / handicap | 185 655 | -0,0186 [-0,0205; -0,0169] | -0,0071 |
| cards_points / most | 44 995 | -0,0148 [-0,0169; -0,0129] | -0,0063 |

Obszar do druku (p >= 0,70), realizacja - średnie p: OLD **-1,94 pp
[-2,13; -1,74]** (257 221 zdarzeń, przeszacowuje), NEW **+1,46 pp [+1,29; +1,63]**
(254 021 zdarzeń, lekko niedoszacowuje). Mecze `UNLINKED` (5 000 z 7 918,
losowo): OLD przy p >= 0,70 realizuje **-4,7 pp [-5,4; -4,0]** (21 303
zdarzenia) - odmowa odbiera wiersze, które przeszacowywały najbardziej.

**Próg O5 spełniony**: górna granica łącznej różnicy log-loss -0,0245 < 0;
każda z 12 komórek baza x klasa tego samego znaku z przedziałem poza zerem.

### Liczność na żywo (`05_sheet.json`)

| dzień | wiersze pochodne (4 metryki) / mecze | bez drabinki jednej strony: wiersze / mecze | w tym UNLINKED | wszystkie pochodne piłki w meczach UNLINKED |
|---|---|---|---|---|
| 10-09 | 1 741 / 321 | 586 / 186 | 4 / 2 | 4 / 2 |
| 10-10 | 3 189 / 336 | 823 / 155 | 8 / 3 | 15 / 5 |
| 10-11 | 5 385 / 752 | 1 544 / 457 | 44 / 7 | 117 / 11 |
| 10-12 | 1 475 / 140 | 450 / 73 | 47 / 5 | 136 / 9 |
| 10-13 | 1 348 / 218 | 333 / 103 | 6 / 3 | 93 / 12 |

"Bez drabinki" = brak wiersza marginalnego strony (drabinka niekwotowana albo
wiersz marginalny nie powstał, np. cienka próbka) - dokładnie to, co widzi joint.

### Interakcja z bramkami (A5) - wynik

Bramki kształtu (`LINE_BEYOND_SAMPLE`, `MODE_LOSES`, `MODEL_ABOVE_OWN_SAMPLE`)
zdejmują **0 wierszy pochodnych przy OLD i przy NEW** - nie widzą żadnej
próbki wiersza pochodnego. Każdy wiersz pochodny, który przeszedłby próg
pewności i ceny, odrzuca `THIN_SAMPLE_FOR_BUILDER` (wykonane, sekcja wyżej).
**Skutek: przełącznik poprawia p_central wierszy pochodnych, ale dopóki ta
bramka czyta próbkę po nazwie rynku wiersza, żaden wiersz pochodny piłki nie
trafi na kupon - z B3 ani bez.** To osobna sprawa (poza B3), do decyzji.

### Decyzja

Przełącznik `DERIVED_SHEET_MARGINS_FROM_UTC` **zostaje `None`** (polecenie
sesji koordynującej: zmierzyć, nie włączać). Próg O5 jest spełniony.
Przed włączeniem: (1) dowód linii kluczy pochodnych (`fit_line_evidence`)
był dopasowany na starym p - po włączeniu offsety i kubełki tych kluczy
startują od nowa; (2) bramka `THIN_SAMPLE_FOR_BUILDER` dla wierszy
pochodnych decyduje, czy zmiana w ogóle dotknie kuponu.

Zastrzeżenia: populacja historyczna to wszystkie mecze, nie tylko te bez
drabinki strony; prior z `sofa_league_baselines.json` i dyspersja patrzą w
przód (jak replay krzywych); prior dnia (`resolve_prior`) nie odtworzony;
zdarzenia to siatka linii wokół centrów, nie faktyczne linie Superbetu.
Zależność stron zależna od różnicy sił (P3/M) nie mierzona i nie wdrożona.
