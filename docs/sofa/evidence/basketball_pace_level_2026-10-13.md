# B7b: tempo z box score tylko jako poziom sumy w koszykówce (audyt 2026-10-13)

Kontynuacja B7 (`docs/sofa/evidence/basketball_pace_2026-10-13.md`, próg
niespełniony: tempo x skuteczność jako centrum pogorszyło zwycięzcę, handicap
i team total; total lepszy tylko na liniach Superbetu, Brier -0,0042
[-0,0079; -0,0006], na historii +0,0004 [-0,0004; +0,0013]).

## Rejestracja B7b (zapisana 2026-10-13 PRZED implementacją i pomiarem)

**Nowa oś.** B7 zastępowało całe centrum (obie strony) iloczynem tempo x
skuteczność, więc ruszało też różnicę. B7b zostawia centrum ratingu punktów
(dziś na żywo) i z box score bierze tylko **poziom** meczu:

- Mnożnik meczu `f = średnia(E posiadań gospodarza, E posiadań gościa) /
  stawka posiadań ligi`, gdzie E posiadań to rating `bb_poss` z B7 (ten sam
  `RatingBook`, as-of, α = 0,10 zamrożone w B7 - nic nie stroję), a stawka
  ligi to `league_rates(rozgrywki, bb_poss)` (średnia gosp./gość, ścisła:
  >= `MIN_LEAGUE_MATCHES` meczów z box score, bez średniej globalnej).
- `f = 1` (model dzisiejszy), gdy: któraś strona ma < 5 meczów z box score,
  któraś nie miała meczu z box score w ostatnich 60 dniach (`PACE_FRESH_S`),
  para jest UNLINKED na `bb_poss`, rozgrywki nie mają stawki posiadań.
- Zastosowanie: z centrum punktów (po wszystkich dzisiejszych regułach) suma
  `T = eh + ea`, różnica `M = eh - ea`; nowe `eh' = (f·T + M) / 2`,
  `ea' = (f·T - M) / 2` (obie >= 0), kwarty tymi samymi udziałami.
  **Różnica zostaje z ratingu punktów.** Dosłowne pomnożenie obu stron przez
  `f` przeskalowałoby też różnicę (f = 1,05 przesuwa różnicę 10 pkt o 0,5
  pkt), więc zwycięzca i handicap nie byłyby niezmienione z konstrukcji -
  dlatego wariantem rozstrzygającym jest skalowanie sumy przy stałej różnicy.
- Szum (`bb_game_sd` / `bb_team_sd` / `bb_quarter_sd`, `period_sd`)
  **dopasowany wokół centrum punktów, jak dziś** (mnożnik włączany po
  dopasowaniu), a `bb_sd_level_power` = 0 (dziś): rozkład różnicy w symulacji
  jest ten sam co dziś - z dokładnością do zaokrąglenia kwart do liczb
  całkowitych i obcięcia przy zerze. Sprawdzenie: w teście A raportuję
  różnicę Briera / log-loss zwycięzcy i handicapu oraz maksymalne |Δp| na
  tych rodzinach (oczekiwane: szum zaokrąglenia, rzędu 1e-3 na p, przedział
  różnicy obejmujący zero).
- Ryzyko (podejrzenie, przed pomiarem): rating punktów już niesie poziom
  drużyn (szybkie drużyny mają wyższe ataki i obrony punktowe), więc mnożnik
  tempa może liczyć tempo drugi raz. Test to rozstrzyga; nie dodaję
  wykładnika ani skurczu (byłoby to strojenie po fakcie).

Przełącznik: nowy `epochs.BB_PACE_LEVEL_FROM_UTC` (domyślnie `None`, model
bajt w bajt dzisiejszy), flaga replayu `fit_sport_confidence --bb-pace-level`,
pomiar `measure_basketball_pace.py --variant level`.

**Ten sam harness i okna co B7** (`scripts/sofa/measure_basketball_pace.py`,
historia `data/audit_2026-10-13/bb_history.pkl`, box score z kopii
`data/refit_2026-10-13/sofa_replay.db`):

- **Test A - historia:** walk-forward 2025-10-01..2026-06-01, model co 30 dni,
  książka aktualizowana mecz po meczu, co n-ty mecz do 6 000, 1 000
  symulacji na mecz i model, to samo ziarno; linie kwartylowe (+0,5) z meczów
  2025-01-01..2025-10-01; Brier i log-loss `total`, `team_total`,
  `handicap`, zwycięzca; różnica w parach nowa - dzisiejsza, 95% bootstrap po
  meczach (2 000 losowań, ziarno 0).
- **Test B - linie Superbetu:** rozliczone linie koszykówki
  2026-09-29..2026-10-12 (`settled_shadow_rows`, model na 00:00Z dnia, cena
  nigdy wejściem p), te same rodziny, w parach, bootstrap po meczach.
- Model dzisiejszy w obu testach jak w B7 (świeżość szumu włączona; A2, A3 /
  C8 wyłączone, dziś `None`).

**Próg (zapisany z góry):**

1. `total`: górna granica 95% różnicy Briera **i** log-loss < 0 - **w obu**
   testach (historia i linie Superbetu).
2. Zwycięzca i handicap: dolna granica 95% różnicy Briera <= 0 (nie gorzej) -
   w obu testach.
3. `team_total`: raportowany, nie rozstrzyga.

Spełnione -> krzywa koszykówki dopasowana na kopii z nowym estymatorem
(`fit_sport_confidence --sport basketball --before 2026-10-13
--bb-pace-level`, `data/refit_2026-10-13/b7b/`) i compare w parach z
`data/refit_2026-10-13/bb_base` (log-loss pewności na wspólnych liniach
holdoutu historii i Superbetu, luka linii >= 0,70). **Bez instalacji i bez
włączania przełącznika.** Niespełnione -> bez refitu, kod zostaje jako
wyłączona opcja.
