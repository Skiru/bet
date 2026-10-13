# A8: szum symulacji koszykówki - trzy kandydaty (audyt 2026-10-13)

Kandydat, nie stwierdzona przyczyna (Część 4; V2L-3). Skrypt:
`scripts/sofa/measure_basketball_overtime.py --variant a8_*` (tylko odczyt),
ta sama uprząż co A3 + C8.

## Rejestracja (zapisana 2026-10-13 przed uruchomieniem pomiaru)

Warianty, każdy osobno wobec dzisiejszego modelu (z mnożnikiem świeżości,
jak na żywo):
1. `a8_one_step` - reszty kwart do dopasowania szumu liczone krok przed (każdy
   mecz okna wobec książki sprzed niego; `SimParams.bb_resid_one_step`), nie
   wobec książki po całym oknie (`score_model.build_model`);
2. `a8_no_fresh` - bez `bb_fresh_mult` (1,0 / 1,0);
3. `a8_level_power` - `bb_sd_level_power` 0,5 (szum skalowany poziomem sumy).

- Okno: mecze 2026-02-01..2026-05-31, walk-forward (model zbudowany przed
  2025-10-01, książka aktualizowana po meczu), co n-ty mecz do 3 000, 600
  symulacji, to samo ziarno.
- Metryka główna: kalibracja nóg zwycięzcy z p >= 0,70 (realizacja - średnie
  p) i Brier zwycięzcy (z dogrywką), różnica wariant - dziś, 95% z bootstrapu
  po meczach; obok: log-loss 1X2 po regulaminie i Brier sumy z dogrywką.
  Linie Superbetu: nie w tym pomiarze (wymagają odtworzenia modelu as-of
  każdego dnia; zostaje do refitu - `fit_sport_confidence` liczy krzywą i jej
  sprawdzian `superbet_settled`).
- Próg (O5): wariant wchodzi tylko, gdy Brier zwycięzcy i Brier sumy są
  lepsze z górną granicą < 0; wdrażany wyłącznie zwycięski (jeden), za
  przełącznikiem razem z refitem koszykówki.

## Wynik (2026-10-13, `data/audit_2026-10-13/a8_*.json`)

Okno 2026-02-01..2026-06-01, 3 081 meczów, dziś (z mnożnikiem świeżości):
kalibracja zwycięzcy p >= 0,70 0.807 / 0.813 (n 1208).

| wariant | mecze | Brier zwycięzcy, wariant - dziś [95%] | Brier sumy z dogrywką | log-loss 1X2 po regulaminie | kalibracja p >= 0,70 |
|---|---|---|---|---|---|
| `a8_one_step` | 3081 | -0.00036 [-0.00116; +0.00049] | -0.00031 [-0.00095; +0.00029] | -0.00026 [-0.00360; +0.00313] | 0.805 / 0.813 (n 1172) |
| `a8_no_fresh` | 3081 | +0.00000 [-0.00037; +0.00035] | +0.00014 [-0.00013; +0.00040] | -0.00088 [-0.00220; +0.00044] | 0.808 / 0.814 (n 1218) |
| `a8_level_power` | 3081 | +0.00022 [-0.00052; +0.00100] | +0.00019 [-0.00035; +0.00073] | -0.00017 [-0.00357; +0.00305] | 0.805 / 0.813 (n 1198) |

**Żaden wariant nie spełnia progu** (każdy przedział obejmuje zero) -
**zmierzone, nie wdrożone**. `SimParams.bb_resid_one_step` zostaje w kodzie
jako wyłączona opcja pomiarowa. Diagnoza z audytu („symulacja na historii za
szeroka”) nie potwierdza się w tym oknie: kalibracja zwycięzcy >= 0,70 jest
tu w porządku dla wszystkich wariantów.
