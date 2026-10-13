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

## Wynik (2026-10-13, `data/refit_2026-10-13/b7b/{history,superbet}.json`)

`measure_basketball_pace.py --variant level`, historia
`data/audit_2026-10-13/bb_history.pkl` (51 168 meczów, 29 480 z posiadaniami
w zakresie), box score z kopii bazy. Mnożnik `f` na meczach ścieżki tempa
(historia): kwantyle 5 / 25 / 50 / 75 / 95% = 0,942 / 0,978 / 1,000 / 1,022 /
1,060.

**Test A - historia 2025-10-01..2026-06-01**, 6 319 meczów (mnożnik w
4 259), linie jak w B7 (suma 148,5 / 161,5 / 174,5, strona 72,5 / 80,5 /
89,5, margines -6,5 / 4,5 / 14,5). Nowa - dzisiejsza, 95% bootstrap po
meczach:

| rodzina | Brier | log-loss | Brier dziś / nowa |
|---|---|---|---|
| total | **+0,00570 [+0,00439; +0,00713]** | +0,01753 [+0,01363; +0,02180] | 0,1686 / 0,1743 |
| team_total | +0,00344 [+0,00265; +0,00426] | +0,00991 [+0,00765; +0,01228] | 0,1699 / 0,1733 |
| handicap | +0,00019 [-0,00002; +0,00041] | +0,00061 [+0,00007; +0,00114] | 0,1731 / 0,1733 |
| zwycięzca | +0,00017 [-0,00018; +0,00052] | +0,00056 [-0,00026; +0,00139] | 0,1979 / 0,1981 |

Tylko mecze z mnożnikiem (4 259): total Brier +0,00845 [+0,00662;
+0,01041]. Kalibracja totalu p >= 0,70: dziś 0,850 / realizacja 0,843
(n 11 630), nowa **0,861 / 0,826** (n 12 108) - nowa pewność przesadzona.

**Test B - linie Superbetu 2026-09-29..2026-10-12** (81 011 linii, p zmienione
na 26 888; mecze: total 1 245, handicap 1 239, team_total 572, zwycięzca
1 189). Nowa - dzisiejsza:

| rodzina | Brier | log-loss | Brier dziś / nowa |
|---|---|---|---|
| total | +0,00538 [-0,00121; +0,01222] | +0,01599 [-0,00011; +0,03373] | 0,2451 / 0,2505 |
| team_total | +0,00369 [-0,00137; +0,00924] | +0,01041 [-0,00169; +0,02322] | 0,2548 / 0,2585 |
| handicap | -0,00076 [-0,00179; +0,00023] | -0,00178 [-0,00406; +0,00041] | 0,2501 / 0,2493 |
| zwycięzca | -0,00032 [-0,00099; +0,00034] | -0,00062 [-0,00213; +0,00088] | 0,2100 / 0,2096 |

Linie główne (fair 0,45-0,55; cena tylko wybiera podzbiór): total 5 798 linii
/ 1 244 mecze 0,2593 -> 0,2649, +0,00565 [+0,00031; +0,01139].

**Sprawdzenie konstrukcji (zwycięzca, handicap).** Różnica Briera zwycięzcy i
handicapu obejmuje zero w obu testach, rzędu 1e-4 (B7: zwycięzca +0,0058
[+0,0045; +0,0072]). Maks. |Δp| na linii: historia zwycięzca 0,080, handicap
0,078; Superbet 0,061 / 0,063 - większe niż zapisane w rejestracji „rzędu
1e-3". Przyczyna (zweryfikowana testem): symulacja ciągnie liczby losowe
warunkowo (przyciąganie remisu, dogrywka), więc ten sam seed rozjeżdża się
między modelami mecz po meczu - p obu modeli to niezależne estymaty z 1 000
symulacji (błąd Monte Carlo ok. 0,016 na p = 0,5), nie te same liczby. Rozkład
różnicy jest ten sam; test `test_winner_and_handicap_are_unchanged_up_to_rounding`
sprawdza go na rozkładzie. Log-loss handicapu na historii +0,00061 [+0,00007;
+0,00114] (nie kryterium; Brier, kryterium, obejmuje zero) - podejrzenie:
zaokrąglenie kwart przy przesuniętym poziomie, niezmierzone dalej.

## Werdykt: **próg NIESPEŁNIONY**

- Kryterium 1 (total, oba testy): historia **gorzej** (Brier +0,0057, przedział
  w całości powyżej zera), Superbet bez poprawy (przedział obejmuje zero,
  punkt +0,0054).
- Kryterium 2 (zwycięzca, handicap nie gorzej): spełnione w obu testach -
  zgodnie z konstrukcją.

Odczyt: potwierdza zapisane z góry ryzyko - rating punktów już niesie poziom
drużyn, mnożnik tempa liczy tempo drugi raz (pewność totalu p >= 0,70 rośnie
z 0,850 do 0,861, realizacja spada z 0,843 do 0,826). Refitu krzywej
(`data/refit_2026-10-13/b7b/`) i compare z `bb_base` **nie wykonano**.
Przełącznik `BB_PACE_LEVEL_FROM_UTC` zostaje `None`; kod zostaje jako
wyłączona opcja (model bajt w bajt dzisiejszy, test
`test_off_is_byte_identical_whatever_the_history_carries`).

Zastrzeżenia: te same co B7 - box score koszykówki nie jest pobierany na
bieżąco (2026-10: 4 z 1 334 meczów), na liniach 09-29..10-12 ratingi tempa
są wrześniowe lub starsze (reguła 60 dni); posiadania Olivera w wersji
prostej; 1 000 symulacji na mecz i model.
