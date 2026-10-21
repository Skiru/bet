# RESOLVE: rezerwy i młodzież — drugie wyszukanie (2026-10-21)

Przełącznik `epochs.SQUAD_SEARCH_RETRY_FROM_UTC` = **2026-10-22 00:00Z**
(zbudowany dzień 10-21 nietknięty). SHADOW_SETTLE czyta regułę od razu.
Grupa ledgera „od 10-22”.

## Przyczyna

`resolve.search_query` usuwa z klucza nasz znacznik „(r)” (normalize_name
zamienia końcowe U21 / II / B / Reserves na „(r)”, `names.py`). Tak
wprowadzono go 2026-09-28, bo Sofascore nic nie zwraca dla „ca penarol (r)”.
Skutek uboczny: „Atlas U21” szło jako „atlas”, Sofascore zwracał pierwszą
drużynę (Atlas FC, CA Atlas, Chabab Atlas Khénifra), a „Atlas FC U21”
(1111909) nie było w wynikach w ogóle. Pierwsza drużyna nie zostanie
sparowana z rezerwami (bramka poziomu przeciwnika w `match_quality`), ale też
rezerwy nie zostaną znalezione — `NO_MATCHING_EVENT` i wpis w
`sofa_entity_miss` na 7 dni.

## Pomiar przed zmianą

`scripts/sofa/measure_squad_search.py` (tylko odczyt; tryb `--live` to same
wyszukania przez most, serie po 40; tryb `--replay` na kopii bazy).

Tablice 10-07..10-21, piłka: **1 100** pozycji ze stroną poniżej seniorów,
**138** bez meczu (12,5%), **168** różnych stron.

Wyszukania na żywo (2026-10-21, 168 stron):

| | stron |
|---|---|
| zwykłe wyszukanie ma kandydata właściwego poziomu w pierwszej trójce | 71 |
| znajduje go tylko drugie wyszukanie (nazwą Superbetu) | **25** |
| nie znajduje żadne | 72 |

Przykłady „tylko drugie”: Atlas U21 → Atlas FC U21, Club America U21,
Guadalajara U21, CF Monterrey U21, Cracovia II, GKS Katowice II → GKS II
Katowice, Ruch Chorzów II, Wisła Kraków II, Al Hilal / Al Nassr / Al Watan /
Al Tadamon U21, NEC Nijmegen U21, Urawa Red Diamonds U21, San Martin SJ (R) →
San Martin Reserve, RC Montevideo (R) → Racing de Montevideo Reserve.

Drugie wyszukanie daje też złe kluby właściwego poziomu (Barcelona B →
Espanyol B, Neom SC U21 → Germany U21). Dlatego para dalej wymaga przeciwnika,
czasu i orientacji — jak każda.

## Powtórka RESOLVE (precyzja)

Każda ze 138 pozycji przez `run_resolve._resolve_one` dwa razy na odchudzonej
kopii bazy (`data/refit_2026-10-21_squad/slim.db`: schemat + `sofa_entity`,
listingi pobrane na żywo; tabela pudeł czyszczona przed każdym przebiegiem):
reguła wyłączona, potem włączona.

| | pozycji |
|---|---|
| bez meczu w obu | 111 |
| mecz w obu (ten sam) | 21 |
| **mecz tylko z regułą** | **6** |
| zmieniony mecz | 0 |
| utracony mecz | 0 |

Sześć nowych par, każda sprawdzona wzrokowo — poprawne:

| dzień | Superbet | Sofascore | rozgrywki |
|---|---|---|---|
| 10-08 | CA Belgrano (R) · San Martin SJ (R) | Belgrano Reserve – San Martin Reserve | Primera LPF, Reserves |
| 10-10 | GKS Katowice II · Ruch Chorzów II | GKS II Katowice – Ruch II Chorzów | IV liga śląska |
| 10-12 | Al Hilal U21 · AL Watan U21 | Al-Hilal U21 – Al-Watan U21 | U21 Elite League |
| 10-13 | Al Nassr U21 · AL Tadamon U21 | Al-Nassr U21 – Al-Tadamon U21 | U21 Elite League |
| 10-14 | Cracovia II · Wisła Kraków II | Cracovia II – Wisła II Kraków | Puchar Polski, okręg Kraków |
| 10-17 | Kawasaki Frontale U21 · Urawa Reds U21 | Kawasaki Frontale U21 – Urawa Red Diamonds U21 | U-21 J. League |

Zysk jest mały: ok. 0,4 meczu dziennie. 25 stron znalezionych wyszukaniem
dało 6 meczów, bo przy części starych meczów listing już ich nie zawiera albo
przeciwnik nie przechodzi bramki nazwy. **Nie sprawdzono**: przyszłego dnia
na żywo (pierwszy test to RESOLVE 10-22).

## Poprawka

- `resolve.squad_retry_queries(side, norm)`: nazwa z tablicy bez nawiasowych
  znaczników Superbetu („(R)”, „(K)”, „(W)”, „(F)”); nazwa oznaczona tylko
  „(R)” dostaje „ Reserve” (pisownia Sofascore); pusta dla seniorów i dla nazw,
  których znacznik zwykłe wyszukanie już zawiera (U23, U19).
- `resolve.squad_level_candidate(norm, entity)`: kandydat musi mieć ten sam
  nie-seniorski poziom co strona; pierwsza drużyna nigdy.
- `SofaResolver.resolve_entity`: drugie wyszukanie tylko, gdy zwykłe nic nie
  dopasowało i nie dało ani jednego kandydata poziomu strony; już rozwiązywane
  strony nie zmieniają się.
- `SofaCache.get_entity_miss(recorded_after=)`: pudło zapisane przed
  przełącznikiem nie blokuje takiej nazwy (bez podbijania
  `MATCH_LOGIC_VERSION`, które unieważniłoby wszystkie pudła).

## Ścieżka rozliczeń (pkt 4 zlecenia)

`resolve.py` ~l. 1262 to `resolve_league` — szuka rozgrywek, nie drużyn;
znacznik go nie dotyczy. Jedyne wyszukanie drużyny to `resolve_entity`,
wspólne dla RESOLVE i SHADOW_SETTLE (`settle_shadow.py`, `record_miss=False`).
Piłkarski SETTLE i audyt tożsamości rozliczeń czytają id z `02_fixtures.json`
i niczego nie szukają. SHADOW_SETTLE ma ten sam problem (hokej / koszykówka /
siatkówka: „... B”, „... II”) — dostaje regułę od razu; rozlicza tylko
przypięte id (`NOT_GRADED:ID_CHANGED` inaczej), więc może tylko rozliczyć
więcej, nigdy źle.

## Czego to nie naprawia

- Strony „U19” bez kandydata U19 w wynikach (29, z tego 23 włoskie — Primavera 1 i 2):
  „udinese u19” nie daje kandydata U19; do zmierzenia osobno.
- MLS Next Pro: Sofascore pisze „Houston Dynamo 2”, „Los Angeles FC 2” —
  końcowe „2” nie jest znacznikiem rezerw w `names.py`.
- „B” w środku nazwy („Žalgiris B Vilnius”), belgijskie „B” / „U21”
  (Leuven B, Sint-Truiden B, SK Beveren U21) — brak kandydata w obu
  wyszukaniach.
- Nazwy tłumaczone (Ethiopian Coffee = Ethiopia Bunna) — aliasy.

## Bramki

`pytest tests/sofa` 5 540 passed; ruff i mypy czyste dla zmienionych plików
(pozostałe błędy mypy w `measure_slip_chance.py` / `measure_slip_objective.py`
i ruff w `measure_cs2_map_total_race.py` są wcześniejsze, nie z tej zmiany);
`check_test_registry.py` 0 findings. Test: `tests/sofa/test_resolve_squad_search.py`.
