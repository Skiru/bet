# CS2: rundy serii - model, pomiar walk-forward i bramka (2026-10-15)

Zlecenie operatora 2026-10-14 ~18:55Z: wycenić rundy całej serii CS2. Przełącznik
`epochs.CS2_SERIES_ROUNDS_FROM_UTC` = **2026-10-15 00:00Z** (trzy klucze przeszły
bramkę operatora). Krzywe **przygotowane, NIE zainstalowane**:
`data/refit_new_markets_2026-10-15/cs2_series_rounds/` (`curves.json`,
`gate_report.md`, `partial_cs2.json`, `rows/`). Skrypt:
`scripts/sofa/fit_cs2_series_rounds.py`.

## Rynki Superbetu

Migawka CS2 czyta je od początku (`cs2.parse_line`), a CS2_SETTLE je rozlicza
(`cs2.actual_value`) - do dziś bez p modelu (`model_p: null`), więc nie mogły
być nogą:

| nazwa Superbetu | rodzina | linia | klucz krzywej |
|---|---|---|---|
| `Liczba rund (z dogrywką)` | `rounds_total` | suma rund obu drużyn | `rounds_total\|OVER/UNDER` |
| `Handicap rund (z dogrywką)` | `rounds_handicap` | handicap drużyny 1 na (rundy 1 - rundy 2) | `rounds_handicap\|TEAM` |
| `<drużyna> liczba rund (z dogrywką)` | `team_rounds` | rundy jednej drużyny | `team_rounds\|OVER/UNDER` |

Kształt oferty (migawki 2026-09-28..10-14, 616 zdarzeń): **jedna linia główna
na zdarzenie** (czasem przesuwana), bez drabinki. Bo1: suma 19,5-22,5 (238 z
369 razy 21,5), handicap ±2,5..±7,5; bo3: suma 38,5-52,5 (najczęściej
50,5-52,5), handicap ±0,5..±14,5, rundy drużyny 12,5-26,5 (183 z 276 razy
26,5); bo5: kilka zdarzeń. `team_rounds` jest wystawiane rzadziej (13 z 49
zdarzeń 10-14). Rynek „drużyna - najwięcej wygranych rund w meczu” występuje
tylko w kombinacjach Superbetu i nie jest czytany.

## Rozliczenie

Rundy wszystkich **rozegranych** map, z dogrywkami (`cs2.actual_value`: suma
po `maps`); mapa nierozegrana nic nie dodaje. Sprawdzone na zapisanym
rozliczeniu: NIP - GamerLegion 2026-09-28, mapy 19-17, 14-16, 13-6, 13-9 =
107 = `actual` w `runs/sofa/cs2/2026-09-28/settled.json`. Seria rozliczona
tylko z wyniku serii (`series_only`, bez rund map) nie rozlicza rund
(`sport_day`: tylko `cs2.SERIES_FAMILIES`). **Niezweryfikowane:** jak
Superbet rozlicza linię rund serii przerwanej / oddanej walkowerem lub
skróconej - regulaminu dla e-sportu nie czytałem; kod traktuje to tak samo
jak pozostałe rynki serii (`cs2.event_state`).

## Model (`cs2_engine.series_rounds_side_p`)

Liczba map wygranych przez każdą drużynę z rozkładu serii, którego już
używają rynki serii (`series_distribution_mixed`, `SERIES_KAPPA` 6); każda
mapa wygrana przez drużynę to losowanie z wyścigu rund mapy
(`map_distribution_for`, ten sam co `map_rounds_handicap` i
`team_rounds_from_race`) pod warunkiem, że tę mapę wygrała. Wyścig czytany
przy p serii (mieszanie Beta ustala tylko, ile map wygra każda strona).
p mapy = `RatingModel.p_map` (Elo map skalibrowane). Brak ceny. Bo1 = wyścig
jednej mapy (test: zgodność do 2e-3).

## Pomiar walk-forward (historia, kopia tabel CS2)

`data/refit_new_markets_2026-10-15/cs2_series_rounds/cs2_history.db` (kopia
`cs2_series` / `cs2_map` / `cs2_player_map` z `data/sofa.db`, 17 328 serii).
Jedno przejście `sport_confidence.cs2_walk_forward_rows(series_rounds=True)`
(Elo i kalibracja odtwarzane w czasie, kalibracja co 7 dni na
wcześniejszych przewidywaniach); seria tylko wtedy, gdy każda jej mapa ma
wynik rund i liczba map = wynik serii. Linie historii:
`sport_confidence.CS2_SERIES_ROUND_LINES` - zakres linii Superbetu na format
(bo1 / bo3 / bo5; handicap obu znaków).

| okno | od | do (bez) | wiersze | serie |
|---|---|---|---|---|
| fit | 2025-10-21 | 2026-09-01 | 804 580 | 7 110 |
| holdout | 2026-09-01 | 2026-10-14 | 163 574 | 1 483 |
| final (krzywe przygotowane) | 2025-10-21 | 2026-10-15 | 968 272 | 8 594 |

Bramka (operator, jednostronna): wiersze holdoutu z wartością krzywej
(okno fit, `realised_lo95`) >= 0,70, n >= 300 i zrealizowane - krzywa >=
-0,02, ORAZ `sport_confidence.admission` na holdoucie.

| klucz | wynik | druk n (serie) | krzywa | zrealizowane | luka [95%] | udział >= 0,70 | log-loss model - baza [95%] |
|---|---|---|---|---|---|---|---|
| `rounds_handicap\|TEAM` | **PASS** | 14 170 (1 483) | 0,789 | 0,813 | +0,024 [+0,008; +0,038] | 23,3% | -0,0458 [-0,0568; -0,0346] |
| `rounds_total\|OVER` | **PASS** | 629 (629) | 0,718 | 0,758 | +0,040 [+0,005; +0,073] | 3,1% | -0,0005 [-0,0042; +0,0036] |
| `rounds_total\|UNDER` | FAIL | 183 (162) | 0,765 | 0,754 | -0,011 [-0,088; +0,061] | 0,9% | jak wyżej |
| `team_rounds\|OVER` | **PASS** | 13 687 (1 483) | 0,798 | 0,821 | +0,023 [+0,009; +0,038] | 44,3% | -0,0323 [-0,0403; -0,0243] |
| `team_rounds\|UNDER` | FAIL | 443 (253) | 0,842 | 0,824 | -0,018 [-0,067; +0,027] | 1,4% | jak wyżej |

Powody FAIL: `rounds_total|UNDER` n = 183 < 300 i kubełek 0,60-0,70 zawyża o
3,8 pp; `team_rounds|UNDER` - kubełek 0,900-0,925 (n 299) zawyża o 3,7 pp.
Log-loss liczony na surowym p modelu, sparowany z częstością linii (format,
linia, strona) z okna fit, przedział bootstrap po seriach; dla OVER i UNDER
jednej linii jest ten sam. Długość serii (suma rund) nie ma umiejętności
ponad częstość linii; handicap i rundy drużyny mają. Kalibracja po kubełkach
(wszystkie kubełki n >= 200 w holdoucie): `gate_report.md`.

## Druga populacja: linie Superbetu (nie bramka - czytać przed instalacją)

Te same przejścia historii wycenione na liniach, które Superbet faktycznie
wystawił i CS2_SETTLE rozliczył (2026-09-28..10-13: 218 zdarzeń, 1 236 stron;
w historii 212 serii, 1 204 wiersze; wynik z historii a wynik CS2_SETTLE:
0 niezgodnych). Linie odwrócone do strony gospodarza Sofascore
(`fit_cs2_series_rounds.home_oriented`).

- Udział wierszy z krzywą >= 0,70: handicap 4,0% (17 z 424), suma 0%, rundy
  drużyny OVER 2,2%, UNDER 1,1% - linia Superbetu stoi tam, gdzie model widzi
  ~50/50.
- Wiersze z krzywą >= 0,70 (wszystkie klucze): **23 strony / 19 serii,
  zrealizowane 0,304 przy krzywej 0,733**; klucze z PASS: 21 / 19,
  zrealizowane 0,333 przy 0,735. Handicap: 17 stron, 0,294 przy 0,738,
  luka -0,444 [-0,639; -0,207].
- Surowe p modelu na liniach Superbetu: handicap p 0,7-0,9 -> zrealizowane
  0,25-0,31 (17 wierszy), p 0,6-0,7 -> 0,57 (56); suma p 0,6-0,7 -> 0,33 (12).
  Log-loss model - baza: handicap -0,024 [-0,062; +0,016], suma -0,004
  [-0,018; +0,010], rundy drużyny -0,016 [-0,046; +0,015] - przedziały
  obejmują zero.

Wniosek: krzywa przechodzi bramkę na drabince linii historii, ale tam, gdzie
Superbet stawia linię, niezgoda modelu z linią jest antysygnałem (jak
`map_team_rounds` 2026-10-05 i ogólnie „niezgoda z ceną”). Próba Superbetu
jest mała (19 serii), ale górna granica luki handicapu to -21 pp.

## Co włączono, co nie

- **Przełącznik** `CS2_SERIES_ROUNDS_FROM_UTC` = 2026-10-15 00:00Z (reguła
  operatora: klucz przeszedł). Od niego: `cs2_engine.model_probability`
  (`series_rounds=True`) wycenia trzy rodziny, SPORT_CONFIDENCE je dopuszcza
  (`sport_confidence.family_of(..., series_rounds=True)`, razem z
  `extended`), CS2_SETTLE dopisuje `model_p` (`settle_cs2.attach_model`, dzień
  oferty), `cs2_settled_rows` je czyta (dowód linii), a
  `fit_sport_confidence.py` odtwarza je w historii dla dnia >= przełącznika.
  Migawka CS2 i rozliczenie były gotowe wcześniej - wyłączone = bajt w bajt
  (sprawdzone: SPORT_CONFIDENCE 10-14 dla CS2 w trybie off = artefakt dnia,
  te same 6 nóg i te same odmowy).
- **Krzywe nie są zainstalowane.** Bez krzywej klucz czyta tylko własne
  rozliczone linie Superbetu (Wilson / design effect, 50 linii i 15 meczów w
  kubełku p) - do tego czasu `NO_LINE_EVIDENCE`. E2E 10-14 (zegar budowy
  15:13Z, przełącznik wymuszony): `MARKET_NOT_ALLOWED` 388 -> 172 (216 stron
  rund serii dopuszczonych: 188 po starcie, 16 niezidentyfikowanych, 12
  `NO_LINE_EVIDENCE`), nogi bez zmian (6). Z krzywymi wmerge'owanymi do
  kopii kalibracji: 06:30Z i 15:13Z - 0 nóg rund serii (poniżej progu).
- **Instalator:** od commita 850729b2 (inny agent, 2026-10-14 19:09Z)
  `install_new_market_curves.py` zna grupę `cs2_series_rounds` (cel
  `SPORT_TARGET`): `--dry-run` dodaje `cs2:rounds_handicap|TEAM` (11
  kubełków), `cs2:rounds_total|OVER` (4), `cs2:team_rounds|OVER` (11). Przy
  line evidence krzywa jest czytana bez `admitted`, więc `--confirm` = te
  klucze drukują. Zaplanowana instalacja po 00:00Z 10-15 (decyzja operatora
  z 15:45Z dotyczyła 11 kluczy) zabierze je razem z resztą - **operator
  decyduje świadomie, po przeczytaniu sekcji o liniach Superbetu**; aby je
  pominąć, usunąć katalog `cs2_series_rounds` z `--dir` albo grupę z
  `GROUPS`.

## Otwarte / niezweryfikowane

- Reguła Superbetu dla serii przerwanej / walkowera na liniach rund serii -
  nie czytana.
- Niezgoda z linią Superbetu na 19 seriach - do potwierdzenia na danych od
  10-15 (`T-CS2-SERIES-ROUNDS-superbet` w `config/sofa_test_registry.json`).
- Linie historii to drabinka zakresu Superbetu, nie linia, którą Superbet
  postawiłby na danej serii; brak `FITTED_LINES` dla tych rodzin (linia
  spoza zakresu przeczyta tę samą krzywą).
- Format nieznany: SPORT_CONFIDENCE go nie zgaduje (v2), `p` = None.
