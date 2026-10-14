# Rynki pochodne sportów mierzonych - pomiar poza próbą (2026-10-14)

Przełącznik: `epochs.SPORT_DERIVED_MARKETS_FROM_UTC` (`None`, czeka na
operatora; znacznik `sport_derived_v1`). Skrypt (tylko odczyt):
`scripts/sofa/measure_sport_derived.py`.

## Co jest mierzone

Rynki, na które model wyniku (`bet.sofa.score_model`) już odpowiada, bez
nowego źródła danych (`shadow.DERIVED_MARKETS`):

- hokej: podwójna szansa meczu (606, czas regulaminowy - jak `result_1x2`
  640) i tercji (616, jak `period_1x2` 660);
- koszykówka: podwójna szansa meczu, 1. i 2. połowy i kwarty (regulaminowo,
  jak 777 / 763 / 233400 / 779);
- siatkówka: „<drużyna> wygra seta” (`team_wins_set`), „<drużyna> wygra
  dokładnie N set(y)” (`team_sets_exact`, N = 1 i 2) i „Dokładna liczba
  setów” (`sets_count`, 3 / 4 / 5).

Replay = ten sam walk-forward, na którym dopasowywane są krzywe sportów
(`sport_confidence.walk_forward_rows`): każdy mecz prognozowany z modelu
zbudowanego wyłącznie z meczów sprzed niego (przebudowa co 30 dni, książka
ratingu aktualizowana mecz po meczu), 1000 symulacji na mecz. Ustawienia
estymatora jak na żywo 2026-10-14: koszykówka ze świeżością
(`BB_FRESHNESS`), reguła stawki ligi (`LEAGUE_RATE_RULE`) włączona, bez
dogrywki / tempa / długości seta (te przełączniki są wyłączone). Okno:
2025-10-14 .. 2026-10-13, mecze przerzedzone równomiernie do <= 4000 na sport.
Baza (base rate) = zrealizowany odsetek tej samej linii (rodzina, okres,
strona, N) w 20 000 najnowszych meczach PRZED oknem (gospodarz = team1, jak w
wierszach). Różnica log-loss model - baza z 95% przedziałem z bootstrapu po
MECZACH (2000 losowań; linie jednego meczu nie są niezależne). Ceny nie ma
nigdzie.

```
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sport_derived.py \
    --sport all --start 2025-10-14 --end 2026-10-14 --max-games 4000 --sims 1000
```

Mecze w replayu: hokej 4573, koszykówka 3425, siatkówka 3085 (historia przed
końcem okna: 29 546 / 51 270 / 23 541).

## Wynik - log-loss wobec bazy i udział p >= 0,70

Klucz = `rodzina|klasa strony` (jak krzywa; 1X i X2 to `TEAM`, „12” i
„SETS=N” mają własne).

| sport | klucz | n | mecze | LL model | LL baza | różnica [95%] | p>=0,70: n (udział) | zrealizowane (Wilson) |
|---|---|---|---|---|---|---|---|---|
| hokej | `double_chance\|12` | 4573 | 4573 | 0,4916 | 0,4916 | -0,0000 [-0,0025; +0,0026] | 4573 (100%) | 0,806 (0,794) |
| hokej | `double_chance\|TEAM` | 9146 | 4573 | 0,6268 | 0,6683 | -0,0415 [-0,0485; -0,0345] | 2024 (22,1%) | 0,793 (0,775) |
| hokej | `period_double_chance\|12` | 13719 | 4573 | 0,6039 | 0,6050 | -0,0011 [-0,0022; +0,0001] | 6891 (50,2%) | 0,734 (0,723) |
| hokej | `period_double_chance\|TEAM` | 27438 | 4573 | 0,6306 | 0,6461 | -0,0155 [-0,0185; -0,0127] | 8060 (29,4%) | 0,749 (0,739) |
| kosz | `double_chance\|12` | 3425 | 3425 | 0,1634 | 0,1615 | +0,0019 [-0,0018; +0,0060] | 3425 (100%) | 0,962 (0,955) |
| kosz | `double_chance\|TEAM` | 6850 | 3425 | 0,5751 | 0,6773 | -0,1021 [-0,1138; -0,0901] | 1404 (20,5%) | 0,835 (0,814) |
| kosz | `h1_double_chance\|12` | 3425 | 3425 | 0,1541 | 0,1538 | +0,0003 [-0,0011; +0,0018] | 3425 (100%) | 0,964 (0,958) |
| kosz | `h1_double_chance\|TEAM` | 6850 | 3425 | 0,6236 | 0,6852 | -0,0615 [-0,0707; -0,0516] | 939 (13,7%) | 0,798 (0,771) |
| kosz | `h2_double_chance\|12` | 3425 | 3425 | 0,1561 | 0,1557 | +0,0004 [-0,0010; +0,0018] | 3425 (100%) | 0,964 (0,957) |
| kosz | `h2_double_chance\|TEAM` | 6850 | 3425 | 0,6383 | 0,6864 | -0,0481 [-0,0585; -0,0377] | 867 (12,7%) | 0,797 (0,769) |
| kosz | `quarter_double_chance\|12` | 13700 | 3425 | 0,2049 | 0,2047 | +0,0002 [-0,0005; +0,0009] | 13700 (100%) | 0,948 (0,944) |
| kosz | `quarter_double_chance\|TEAM` | 27400 | 3425 | 0,6584 | 0,6882 | -0,0298 [-0,0336; -0,0255] | 2026 (7,4%) | 0,772 (0,754) |
| siatka | `sets_count\|SETS=3` | 3085 | 3085 | 0,6612 | 0,6932 | -0,0319 [-0,0420; -0,0218] | 193 (6,3%) | 0,819 (0,758) |
| siatka | `sets_count\|SETS=4` | 3085 | 3085 | 0,6145 | 0,6247 | -0,0101 [-0,0144; -0,0059] | 0 | - |
| siatka | `sets_count\|SETS=5` | 3085 | 3085 | 0,5031 | 0,5166 | -0,0135 [-0,0215; -0,0057] | 0 | - |
| siatka | `team_sets_exact\|NO` | 12340 | 3085 | 0,3686 | 0,3866 | -0,0180 [-0,0213; -0,0149] | 12338 (100%) | 0,868 (0,862) |
| siatka | `team_sets_exact\|YES` | 12340 | 3085 | 0,3686 | 0,3866 | -0,0180 [-0,0212; -0,0149] | 0 | - |
| siatka | `team_wins_set\|NO` | 6170 | 3085 | 0,4247 | 0,5407 | -0,1160 [-0,1262; -0,1052] | 187 (3,0%) | 0,818 (0,757) |
| siatka | `team_wins_set\|YES` | 6170 | 3085 | 0,4247 | 0,5407 | -0,1160 [-0,1261; -0,1054] | 4468 (72,4%) | 0,871 (0,861) |

(YES i NO jednej linii to dopełnienia - ta sama log-loss.)

## Kalibracja (kubełki `sport_confidence.EDGES`, wybrane)

Pełne kubełki (n, średnie p, zrealizowane, Wilson) - w JSON skryptu
(`--json-out`). Najważniejsze:

- **hokej `double_chance|12`** - model zawyża: średnie p 0,828 przy
  zrealizowanych 0,806; kubełek 0,800-0,825 (n 1846) p 0,813 / 0,788,
  0,825-0,850 (n 1590) p 0,835 / 0,808. Bez przewagi nad bazą (różnica 0,0000).
- **hokej `double_chance|TEAM`** - skalibrowany do lekko ostrożnego:
  0,700-0,750 p 0,723 / 0,735 (n 859), 0,750-0,800 p 0,772 / 0,787 (n 540).
- **hokej `period_double_chance`** - skalibrowany (0,700-0,750: TEAM p 0,723
  / 0,720, n 4622; „12” p 0,722 / 0,727, n 5822); „12” bez przewagi nad bazą.
- **kosz `*_double_chance|12`** - zawsze >= 0,94 (remis w regulaminie /
  połowie / kwarcie rzadki), bez przewagi nad bazą; przy kursie ~1,03 i tak
  nie przejdzie `ODDS_TOO_LOW`.
- **kosz `*_double_chance|TEAM`** - mecz ostrożny (0,700-0,750 p 0,724 /
  0,755; 0,750-0,800 p 0,773 / 0,801); połowy i kwarty skalibrowane.
- **siatka `team_wins_set|YES`** - zawyża w środku zakresu: 0,600-0,700 p
  0,655 / 0,599 (n 659), 0,700-0,750 p 0,725 / 0,673 (n 443), 0,800-0,825
  p 0,812 / 0,768 (n 263); od 0,825 w górę skalibrowany. Mimo to największa
  przewaga nad bazą (-0,116).
- **siatka `team_sets_exact|NO`** - skalibrowany do lekko ostrożnego w
  każdym kubełku (np. 0,825-0,850 p 0,839 / 0,851, n 2100).
- **siatka `sets_count|SETS=3`** - mało linii >= 0,70 (193), zgodne w
  granicach szumu.

## Co z tego wynika

- Model ma realną przewagę nad bazą na wszystkich kluczach „drużynowych”
  (podwójna szansa 1X / X2, liczba setów, sety drużyny) - przedziały w
  całości poniżej zera.
- „12” (brak remisu) w hokeju i koszykówce **nie** odróżnia meczów od bazy;
  w hokeju meczowe „12” jest dodatkowo zawyżone o ~2 pp. To jest dokładnie
  to, co line evidence (klucz bez krzywej czyta tylko własne linie
  Superbetu, dolna granica Wilsona) ma ograniczyć - przełącznik nie wprowadza
  krzywej z historii.
- Siatkarskie `team_wins_set|YES` w zakresie 0,60-0,82 zawyża o 4-6 pp -
  jak reszta siatkówki (CLAUDE.md: ~16 pp przy >= 0,70 na liniach
  Superbetu). Przed ewentualną krzywą z historii trzeba to zmierzyć na
  liniach Superbetu.

## Czego ten pomiar nie sprawdza

- **Ceny Superbetu** - żadnej linii pochodnej nie ma jeszcze w migawkach
  (SHADOW ich nie czyta, póki przełącznik jest wyłączony). Czy model bije
  cenę, rozstrzygną dopiero rozliczone linie po włączeniu.
- Kształt ładunku koszykówki i siatkówki - nie było ich surowych ładunków;
  czytane po nazwie z próby pokrycia rynków 2026-10-14, niepasująca nazwa /
  wynik odpada. Hokej sprawdzony na ładunkach z 2026-10-13
  (`tests/sofa/golden/superbet_hockey_double_chance_2026-10-13.json`).
- Linie „dokładnie N setów” tylko N = 1 i 2 (te, które Superbet wystawił
  2026-10-14); format best-of-3 w siatkówce nie był osobno mierzony.
- Okres: jeden rok, przerzedzony do <= 4000 meczów na sport; bez podziału
  na ligi.
