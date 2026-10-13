# D1: DNB i podwójna szansa z czystego ratingu z fazą sezonu (audyt 2026-10-13)

Pomiar: `scripts/sofa/measure_football_result_phase.py` (tylko odczyt), na
`scripts/sofa/measure_football_result_model.py` (pomiar C2 z
`RAPORT_NOC_2026-10-12.md`) i `bet.sofa.season_phase` (C1).

## Diagnoza

- Rynki wyniku piłki nie są wyceniane: OFFER zostawia je w `unmapped_markets`
  (`market_coverage`: `fb.result`, `fb.double_chance`, `fb.dnb`).
- Pomiar C2 (10-12): DNB -0,0792 [-0,0818; -0,0764] log-loss względem stopy
  bazowej ligi, DC -0,0376; krzywa z historii przeszacowuje w oknie testowym o
  2,4-4 pp w sierpniu-wrześniu (start sezonu). Operator 10-13 odmówił DNB / DC
  bez fazy sezonu.

## Rejestracja (zapisana 2026-10-13 PRZED uruchomieniem pomiaru)

- **Model:** niezależne NB goli stron na **czystym ratingu**
  (`FootballForecast.centre("goals_for", side)`, as-of), r dopasowane na
  treningu (`nb_rating` z C2); wariant z fazą: centra obu stron x exp(c[faza]),
  c dopasowane (`season_phase.fit_coefficients`) na centrach ratingu
  treningu; faza z `season_phase.phases_by_event` (as-of).
- **Okna:** trening 2024-10-01..2026-06-08, test 2026-06-09..2026-10-12 (jeden
  krok walk-forward: r, c fazy i krzywe dopasowane tylko na treningu; trening
  obejmuje sierpień-wrzesień 2025, więc krzywa widziała jeden start sezonu).
- **Krzywa:** kubełki 0,05 per (rynek, wybór) z treningu (`fit_curves` z C2,
  min. 200 wyborów), jak krzywe pipeline'u.
- **Populacja progu:** mecze test bez `UNLINKED` (odrzucane i tak).
- **Metryki:**
  1. d log-loss (z fazą - bez fazy) per mecz, DNB / DC / 1X2, 95% bootstrap
     po meczach (2000, ziarno 0);
  2. d log-loss (model z fazą - stopa bazowa ligi), jak w C2;
  3. kalibracja po krzywej wyborów do druku (p >= 0,70): realised - p z 95%
     bootstrapem po meczach, cały test i sierpień-wrzesień 2026 razem.
- **Próg do implementacji D1 (dla DNB i DC osobno), wszystkie trzy:**
  (a) model z fazą lepszy od bazy: górna granica 95% < 0;
  (b) po krzywej wybory p >= 0,70 w całym teście: |luka| <= 2 pp przy
      n >= 300 (reguła PASS `measure_calibration.py`);
  (c) to samo w sierpniu-wrześniu 2026 (start sezonu): |luka| <= 2 pp przy
      n >= 300.
  Metryka 1 jest raportowana (czy faza pomaga), nie jest progiem D1.

## Wynik

(uzupełniane po pomiarze)
