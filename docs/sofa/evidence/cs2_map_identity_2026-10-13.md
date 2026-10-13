# B11: CS2 - mapa, kolejność mapy i pula map (audyt 2026-10-13)

Przełącznik: `epochs.CS2_MAP_IDENTITY_FROM_UTC`. Skrypt:
`scripts/sofa/measure_cs2_map_identity.py` (tylko odczyt, kopia bazy
`data/refit_2026-10-13/sofa_replay.db`).

## Diagnoza (sprawdzona w kodzie)

- `cs2_engine.load_history` (`cs2_engine.py:375-446`) nie czyta `map_name`,
  `home_starting_side` ani `home_period1/2`.
- `model_probability`, `map_winner` (`:801-802`): `line.map_nr` nieczytany;
  mapa 1, 2 i 3 serii dostają to samo p. Tak samo replay historii
  (`sport_confidence._cs2_series_rows`, wiersze `map_winner`).

## Co jest znane przed meczem

- Superbet: linia „X wygra N. mapę” niesie tylko `map_nr`. W migawkach
  CS2 z 10-10..10-12 nie ma nazwy mapy w żadnym polu (sprawdzone: jedyne pola
  „*name*” to `match_name`). Veto odbywa się kilka minut przed startem, a
  Sofascore podaje `map_name` po fakcie.
- Strona startowa i połowy: wybór strony następuje po veto, połowy są wynikiem.
  **Przed meczem nie są znane** i nie mogą wejść do p linii przedmeczowej.
  Wchodzą tylko jako diagnostyka (wyrocznia), nie do modelu.
- Znane przed meczem: numer mapy (`map_nr`), format (`best_of` z fixtures),
  strona „gospodarza” Sofascore, historia map obu drużyn (pula).
- Wniosek: rating per mapa może wejść **tylko jako mieszanina po puli map
  drużyn** (wagi z historii), a nie jako p konkretnej mapy.

## Rejestracja (zapisana 2026-10-13 przed uruchomieniem pomiaru)

Modele (wszystkie z tą samą bazą: Elo drużyny / Elo graczy z kalibracją
logistyczną, jak dziś; dodatki fitowane walk-forward z przesunięciem = logit
bazowy, ridge 1,0 do zera, tylko na mapach sprzed punktu refitu):

- **A (kolejność):** logit += δ_k, k = klucz (format, numer mapy):
  `bo1`, `bo3m1`, `bo3m2`, `bo3m3`, `other` (bo2 / bo5 / brak formatu).
  Hipoteza: mapa 1 bo3 to pick jednej strony (jeśli „gospodarz” Sofascore
  częściej wybiera mapę 1, δ_bo3m1 > 0 > δ_bo3m2).
- **B (pula):** logit += c · Δ, Δ = Σ_M w(M) · (D_h(M) − D_a(M)) w logitach,
  D_t(M) = odchylenie Elo drużyny t na mapie M (aktualizowane jak Elo, K_MAP
  = 16, surprise względem Elo drużyny + odchyleń), w(M) ∝ (n_h(M) + 0,5)
  (n_a(M) + 0,5) po mapach, które któraś drużyna grała w ostatnich 30 mapach.
  Stałe K_MAP, POOL_MAPS = 30, α = 0,5 wybrane, nie fitowane
  (`UNFITTED_CONSTANTS`).
- **A+B** razem.
- **Wyrocznia** (diagnostyka, nieużywalna przed meczem): jak B, ale Δ z
  faktycznej mapy M.

Populacja i podział:
- Historia map CS2 z kopii bazy (`sport_confidence.load_cs2`, przed
  2026-10-13), walk-forward jak `cs2_walk_forward_rows`: Elo i kalibracja z
  serii sprzed danej serii (refit co 7 dni), dodatki A / B fitowane w tych
  samych refitach na punktach sprzed nich.
- **Okno główne:** ostatnie 40% serii (po czasie) z 2025-10-13..2026-10-13,
  na mapach z p bazowym (oba zespoły ocenione). Całe okno raportowane obok.

Metryka i próg (O5):
- Log-loss `map_winner` (gospodarz wygrał mapę) na mapę; różnica sparowana
  wariant − baza, średnia na mapę; 95% z bootstrapu po seriach (2000, ziarno 0).
- **H1:** A vs baza. **H2:** A+B vs A. B vs baza raportowane.
- Reguła: A włączane, gdy górna granica H1 < 0; B dokładane, gdy dodatkowo
  górna granica H2 < 0. Gdy H1 nie przechodzi, a B vs baza ma górną granicę
  < 0, włączane samo B. Inaczej przełącznik zostaje `None`.
- **Strażnik:** `map_team_rounds` z wyścigu rund (B10, linie
  `CS2_TEAM_ROUND_LINES`) z p mapy wariantu vs p bazowe - log-loss nie może
  być gorszy (dolna granica 95% > 0 = gorszy = przełącznik `None`).
- Obok (bez progu): kalibracja p >= 0,70 (średnie p vs realizacja), δ_k,
  c, wyrocznia.
- Włączenie wymaga refitu krzywej CS2 (`map_winner`, `map_team_rounds`) w
  replayu tym samym estymatorem na kopii bazy i porównania z sekcją CS2
  `config/sofa_sport_confidence_calibration.next.json`.
- Rynki serii (`match_winner`, `maps_*`, `team_maps`, `exact_maps`) w tym
  teście zostają na p bez numeru mapy (zmiana łańcucha pick/decider to osobna
  pozycja).
