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

## Wynik (2026-10-13, `measure_cs2_count_exposure.py`, baza `data/sofa.db` tylko do odczytu)

Okno główne: ostatnie 40% serii z 2025-10-13..2026-10-13 (6 014 serii),
linie syntetyczne wg rejestracji. Log-loss nowy - stary na linię, 95%
bootstrap po seriach (2000, ziarno 0):

| rodzina | linie | log-loss nowy - stary | strażnik p >= 0,70 (log-loss, linie) |
|---|---|---|---|
| player_kills | 702 848 | -0,0135 [-0,0148, -0,0122] | -0,0164 [-0,0181, -0,0148] (154 924) |
| player_deaths | 702 848 | -0,0258 [-0,0277, -0,0239] | -0,0311 [-0,0335, -0,0289] (167 993) |
| player_assists | 702 848 | -0,0099 [-0,0107, -0,0090] | -0,0121 [-0,0131, -0,0111] (158 394) |
| team_kills | 141 224 | -0,0380 [-0,0414, -0,0347] | -0,0547 [-0,0597, -0,0496] (34 154) |
| player_headshots | 702 826 | **+0,1877** [+0,1834, +0,1918] | +0,2231 (395 563) |

Kalibracja p >= 0,70 (średnie p / realizacja): kills stary 0,738 / 0,734 (n
124 812), nowy 0,771 / 0,765 (117 366); deaths 0,745 / 0,773 vs 0,779 / 0,814;
assists 0,763 / 0,753 vs 0,772 / 0,773; team_kills 0,717 / 0,755 vs 0,792 /
0,796; headshots stary 0,757 / 0,751, nowy 0,774 / **0,535** (n 338 818).

Decyzja: cztery rodziny (kills, deaths, assists, team_kills) mają górną
granicę < 0 i dolną granicę strażnika < 0 (nie gorsze); headshots gorsze -
zostają na `count_p` (`EXPOSURE_FAMILIES` bez `player_headshots`; przyczyna
niezbadana - podejrzenie: sumy zespołowe HS z niepełnych składów; pomiar
2026-10-20 wskazał przyczynę: 239 niemożliwych wierszy headshots > kills
z 2025-10-27, zob. `docs/sofa/history/POMIAR_CS2_PLAYER_KILLS_2026-10-20.md`).
Przełącznik `CS2_COUNT_EXPOSURE_FROM_UTC` włączony na podstawie stałej zgody
audytu (CLAUDE.md, Changing the pipeline 4), pierwotnie na 2026-10-14 00:00Z;
operator przesunął go 2026-10-13 na **2026-10-13 18:10Z** (rebuild refitu,
dzień mieszany) - obowiązuje ta godzina (`epochs.py`). Uwagi: linie są
syntetyczne wokół średniej starego modelu (nie linie Superbetu); kontrola na
rozliczonych liniach Superbetu 10-05..10-12 **nie wykonana**; line evidence
tych rodzin było fitowane na p starego estymatora i do refitu czyta je przy
nowym p (konserwatywnie; zob. `refresh_line_evidence.py`).
