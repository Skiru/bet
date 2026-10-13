# B12: CS2 - zabójstwa, zgony, asysty, HS z ekspozycji w rundach (audyt 2026-10-13)

Przełącznik: `epochs.CS2_COUNT_EXPOSURE_FROM_UTC`. Skrypt:
`scripts/sofa/measure_cs2_count_exposure.py` (tylko odczyt, kopia bazy
`data/refit_2026-10-13/sofa_replay.db`).

## Diagnoza (sprawdzona w kodzie)

- `cs2_engine.count_p` (`cs2_engine.py:628`) na próbce `player_values`
  (`:727`) / `team_kills` (`:753`): surowe NB / normal z ostatnich 20 map
  gracza (drużyny). Nie zna oczekiwanej liczby rund mapy ani rywala
  (`model_probability`, `:870`, `:872-875`).

## Rejestracja (zapisana 2026-10-13 przed uruchomieniem pomiaru)

Model (statystyka S w {kills, deaths, assists, headshots}; drużyna = suma
pięciu graczy):

- Rozkład wyniku mapy (W rund własnych, L rund rywala) z wyścigu rund
  `map_distribution_for(p_map)` (B10), p_map z ratingu jak dziś.
- Średnia drużyny przy (W, L): m_own(S) · m_opp(S) · (c_w(S) · W + c_l(S) · L).
  c_w, c_l: najmniejsze kwadraty na wszystkich wcześniejszych mapach
  (sumy bieżące, bez wyrazu wolnego). m_own: (obserwowane + K_T · ē) /
  (oczekiwane + K_T · ē) na ostatnich 20 mapach drużyny, K_T = 5 map
  (ē = średnie oczekiwane na mapę). m_opp: to samo dla rywala na statystyce
  „przeciw” (kills ↔ deaths; asysty i HS bez m_opp).
- Gracz: udział w statystyce drużyny z jego ostatnich 20 map (po id gracza,
  także w innych drużynach), ściągnięty do 0,2 z K_P = 2 mapami.
- Rozkład: mieszanina po (W, L) rozkładu NB (wariancja = φ · μ, gdy φ > 1)
  albo normalnego z poprawką ciągłości (wariancja max(φ, 0,5) · μ). φ per
  statystyka i poziom (gracz / drużyna): średnie (x − μ(W, L))² / μ z
  wcześniejszych prognoz walk-forward przy faktycznych (W, L).
- Stałe K_T, K_P, 0,2 wybrane, nie fitowane (`UNFITTED_CONSTANTS`).

Linie syntetyczne (jak Superbet: blisko średniej): c = round(średnia
dzisiejszej próbki starego modelu), h = max(1, round(sd / 2)); linie
c − 0,5 − h, c − 0,5, c + 0,5, c + 0,5 + h; obie strony. Linia liczona tylko,
gdy oba modele dają p (stary: >= 8 map w próbce).

Populacja i podział:
- Historia map CS2 z kopii bazy (`sport_confidence.load_cs2`, przed
  2026-10-13), walk-forward: każda mapa prognozowana ze stanu sprzed serii
  (Elo, kalibracja co 7 dni, próbki, c, m, φ tylko z wcześniejszych map).
- **Okno główne:** ostatnie 40% serii (po czasie) z 2025-10-13..2026-10-13.

Metryka i próg (O5):
- Log-loss p strony; różnica nowy − stary na linię, 95% z bootstrapu po
  seriach (2000, ziarno 0), **osobno dla każdej rodziny**: `player_kills`,
  `player_deaths`, `player_assists`, `player_headshots`, `team_kills`.
- Reguła: przełącznik obejmuje rodziny z górną granicą < 0; pozostałe
  zostają na `count_p`. Żadna - przełącznik `None`.
- **Strażnik (per rodzina):** log-loss na liniach, gdzie którykolwiek model
  daje p >= 0,70 - dolna granica 95% > 0 (gorszy) wyklucza rodzinę.
- Obok (bez progu): kalibracja p >= 0,70, Brier, linie Superbetu 10-05..10-12
  (`model_p` przy rozliczeniu vs nowy p as-of dnia; kontrola).
- Te rodziny nie mają krzywej z historii (tylko line evidence z rozliczonych
  linii, `settle_cs2.attach_model`), więc refit krzywej nie jest potrzebny;
  line evidence z dni sprzed przełącznika czyta p starego estymatora.
