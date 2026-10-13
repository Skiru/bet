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

## Wynik

(niżej, po uruchomieniu)
