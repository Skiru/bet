# Rating piłkarski w pucharach międzynarodowych: luka między ligami (2026-10-15)

Skrypt: `scripts/sofa/measure_cross_league_cups.py` (tylko odczyt; test
`tests/sofa/test_measure_cross_league_cups.py`). Pomiar, nie zmiana: żaden
przełącznik, config ani kod w `src/` nie został ruszony.

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_cross_league_cups.py \
    --db data/sofa.db --json-out <f> --md-out <f>      # ~30 s
```

## Pytanie

Przy budowie 2026-10-15 analitycy wystawili 104 weta CONTEXT i wiele WATCH,
bo rating piłkarski na meczach pucharów europejskich / AFC stawiał stronę ze
słabszej ligi wyżej albo na równi: Lech Poznań - Bayer Leverkusen 1X2
0.48 / 0.29, Celje nad Omonią, CSKA Sofia ~ Monaco, Egnatia nad Midtjylland.
Księga siły lig (`football_rating.RatingBook.strength`) daje tam luki bliskie
zera (POL-GER -0.09, ALB-DEN -0.06), a goals_for czyta rating z wagą ~0.95.
Czy to na historii systematyczny błąd, o ile, i czy przemierzona luka go
usuwa?

## Dane

- Historia piłkarska SHEET-a: `data/cache/football_history.pkl` (926 332
  mecze, tylko odczyt; towarzyskie poza, rezerwy oznaczone, jednostki lig
  przypisane - to samo, co czyta `football_rating.load_history`). Baza
  `data/sofa.db` otwarta `mode=ro` wyłącznie po nazwy rozgrywek
  (`sofa_tournament_map`).
- Rozgrywki (`INTL_COMPS`): Liga Mistrzów 7, Liga Europy 679, Liga
  Konferencji 17015, AFC Champions League Elite 463, AFC Champions League
  Two 668, Libertadores 384, Sudamericana 480, CAF Champions League 1054,
  CONCACAF Champions Cup 498. Mężczyźni, od 2024-07-01 (wcześniej puchary są
  w cache'u pojedynczo).
- Mecz cross-league: obie strony mają domenę (modalna jednostka ligowa w
  oknie linku, `RatingBook.domain`) i domeny należą do różnych rozgrywek,
  żadna z nich nie jest pucharem. 3 740 takich meczów; poza: 108 tej samej
  ligi, 99 z domeną-pucharem, 18 bez domeny, 1 bez goli.
- Z centrum ratingu (obie strony >= `MIN_TEAM_MATCHES`): **3 689**, w tym
  **3 364 LINKED_BY_STRENGTH** (to, co SHEET wycenia i co może się
  wydrukować) i 325 UNLINKED (CONFIDENCE je odrzuca, `CROSS_LEAGUE_UNLINKED`).
  Wg rozgrywek: LM 632, LE 606, LK 987, ACL Elite 260, ACL Two 240,
  Libertadores 309, Sudamericana 306, CAF 270, CONCACAF 79. Historii jest
  dość - to nie jest pomiar na garstce meczów.

## Metoda

- **Replay as-of.** Jeden `RatingBook(shared_league_link=True)` karmiony
  goals_for w kolejności czasu; każdy mecz pucharowy wyceniony PRZED
  aktualizacją grupy meczów o tym samym czasie startu. Centra to czyste
  centra ratingu `FootballForecast.centre("goals_for", side)` (stawka ligi x
  exp(luka) x ilorazy^0.6) - skrypt sprawdza, że jego własna arytmetyka
  odtwarza je dokładnie. 1X2 z niezależnych NB goli, r = 7.586
  (`config/sofa_football_result.json`) - ta sama arytmetyka, co wiersze
  `result_1x2` / `double_chance` w SHEET.
- **Proxy siły ligi z samych danych** (`CupLeagueElo`): Elo na różnicy
  bramek tylko z wcześniejszych meczów cross-league w tych pucharach -
  s_ligi, oczekiwana różnica gospodarza = s_h - s_a + przewaga gospodarza
  (bieżąca średnia), krok 0.05 (wybrany, nie dopasowany); czytane dopiero
  gdy obie ligi mają >= 10 takich meczów (2 895 z 3 364 wierszy).
- **Kalibracja**: wiersze zorientowane na stronę S, którą faworyzuje dana
  luka; realne minus przewidywane (różnica bramek, gole S, gole rywala,
  P(wygrana S)), bootstrap meczów 95%, 1000 powtórzeń.
- **Warianty 1X2** (hiperparametry wybrane na TRAIN = mecze
  LINKED_BY_STRENGTH 2024-07-01..2025-06-30, 1 170; ocena na TEST =
  od 2025-07-01, 2 194):
  - A - centra SHEET-u bez zmian;
  - B - przefitowana luka księgi: log-luka x c i potęga ilorazów k
    (siatka; wybrane c = 1.0, k = 0.4);
  - C - log-luka + b x (luka Elo w golach) (wybrane b = 0.1);
  - D - log-luka + (d_h - d_a), gdzie d ligi uczy się online tylko z meczów
    pucharowych na resztach samego D (krok wybrany 0.05).

## Wyniki

### Kalibracja wg luki proxy (Elo z pucharów), LINKED_BY_STRENGTH, wszystkie konfederacje

S = liga silniejsza wg pucharów. Dodatnie "realne - przew." = rating nie
docenia strony z silniejszej ligi.

| luka Elo (gole) | n | luka księgi S (log) | przew. GD | realne GD | realne - przew. GD | P(S wygra) | realne - P |
|---|---|---|---|---|---|---|---|
| 0-0.2 | 672 | +0.022 | +0.05 | +0.06 | +0.01 [-0.14, +0.14] | 0.388 | -1.0 pp [-4.8, +2.7] |
| 0.2-0.5 | 834 | +0.079 | +0.19 | +0.33 | +0.15 [+0.02, +0.27] | 0.415 | +3.0 pp [-0.3, +6.0] |
| 0.5-1 | 917 | +0.149 | +0.34 | +0.66 | +0.32 [+0.21, +0.45] | 0.446 | +6.0 pp [+3.0, +9.3] |
| >=1 | 472 | +0.238 | +0.62 | +1.29 | +0.67 [+0.52, +0.84] | 0.502 | +16.6 pp [+12.3, +20.4] |
| razem | 2 895 | +0.114 | +0.27 | +0.53 | **+0.26 [+0.19, +0.32]** | 0.433 | **+5.2 pp [+3.6, +7.0]** |

Rozkład na gole (razem): gole S +0.14 [+0.09, +0.19], gole rywala -0.12
[-0.16, -0.08] na mecz - suma prawie zero, więc **sumy goli nie są
skrzywione, skrzywione są rynki stron** (1X2, DC, DNB, goals_for, handicapy).
Remisy w koszyku >= 1: przewidywane 0.228, realne 0.163.

Tylko UEFA (1 904): razem +0.33 [+0.25, +0.42] GD, +7.3 pp [+5.2, +9.4];
koszyk >= 1 (315): +0.79 [+0.59, +1.00] GD, **+20.0 pp [+14.8, +25.1]**.
Tylko AFC (355): +0.39 [+0.21, +0.56] GD, +7.1 pp [+2.0, +11.6].

### Kalibracja wg luki samej księgi

Ta sama populacja (3 364), S = strona faworyzowana przez księgę: razem
+0.03 [-0.04, +0.09] GD, +1.0 pp [-0.6, +2.6]; żaden koszyk nie odbiega z
przedziałem poza zerem. Czyli **względem własnej luki model jest
skalibrowany - nie widzi tylko tego, czego luka nie zawiera**. Dlatego
skalowanie luki (B) nic nie daje: księga nie jest tylko ściśnięta, ma zły
porządek lig.

### Log-loss 1X2 na TEST (wariant - A, na mecz; ujemne = lepiej)

| zakres | n | LL A | B - A | C - A | D - A |
|---|---|---|---|---|---|
| wszystkie | 2 194 | 1.0299 | -0.0014 [-0.0035, +0.0009] | -0.0111 [-0.0149, -0.0077] | **-0.0262 [-0.0366, -0.0161]** |
| UEFA | 1 414 | 1.0305 | -0.0022 [-0.0050, +0.0008] | -0.0145 [-0.0194, -0.0098] | -0.0309 [-0.0452, -0.0168] |
| AFC | 270 | 1.0309 | -0.0078 [-0.0156, +0.0000] | -0.0214 [-0.0339, -0.0091] | -0.0532 [-0.0851, -0.0208] |
| luka Elo >= 0.5 | 991 | 0.9979 | -0.0014 [-0.0049, +0.0018] | -0.0232 [-0.0308, -0.0160] | -0.0441 [-0.0643, -0.0252] |

Kalibracja D na TEST (2 058 z proxy): P(S wygra) realne - przew. razem
-1.4 pp [-3.5, +0.8], koszyk >= 1 +1.0 pp [-3.9, +6.1] (A: +5.7 pp
[+3.5, +7.9] i +18.4 pp [+13.3, +23.4]). D lekko przestrzela różnicę bramek
(-0.10 [-0.18, -0.02] GD razem, -0.21 [-0.39, -0.01] w >= 1), więc to
kierunek, nie gotowy estymator.

### Przypadki z 2026-10-15 (stan na koniec historii)

| para (słabsza wg pucharów - silniejsza) | luka księgi (log) | dodatek D (log) | luka Elo (gole) | mecze pucharowe lig |
|---|---|---|---|---|
| POL-GER (Lech - Leverkusen) | -0.092 | -0.121 | -0.72 | 123 / 170 |
| SLO-CYP (Celje - Omonia) | +0.158 | -0.299 | -0.92 | 85 / 101 |
| BUL-FRA (CSKA Sofia - Monaco) | -0.276 | -0.476 | -1.53 | 79 / 157 |
| ALB-DEN (Egnatia - Midtjylland) | -0.057 | -0.301 | -1.01 | 45 / 101 |

We wszystkich czterech luka z pucharów wskazuje to samo, co analitycy, a
księga w SLO-CYP ma nawet odwrotny znak. Korelacja sigma księgi z Elo
pucharowym po 40 ligach z największą liczbą meczów pucharowych: 0.67;
przykłady rozjazdu: PrvaLiga sigma +0.52 / Elo -0.32, Scottish Premiership
+0.47 / -0.12, Allsvenskan +0.39 / -0.35 vs Premier League +0.89 / +2.20.

Przyczyna (z kodu, `RatingBook.update`): sigma domeny uczy się z KAŻDEGO
meczu niepowiązanego - krajowe puchary z niższymi ligami, beniaminkowie,
spadkowicze - i z tego samego residuum, które równolegle wchłaniają ilorazy
drużyn. Ekstraklasa ma 362 takie mecze w księdze, z czego meczów
pucharowych cross-league od 2024-07 jest 123: sigma mierzy głównie przewagę
ligi nad jej własnymi niższymi ligami, więc wszystkie ekstraklasy kończą w
okolicy +0.4..+0.6 i luka między nimi jest bliska zera (podejrzenie co do
proporcji - udział meczów pucharowych w linkach księgi nie był liczony
wprost).

## Werdykt

- **Błąd jest realny i systematyczny.** Na 2 895 meczach pucharowych
  LINKED_BY_STRENGTH rating nie docenia strony z silniejszej (wg wyników
  pucharowych) ligi o +0.26 [+0.19, +0.32] bramki na mecz i +5.2 pp
  [+3.6, +7.0] prawdopodobieństwa wygranej; przy luce >= 1 gola (472 mecze,
  ~16% populacji) o +0.67 bramki i +16.6 pp [+12.3, +20.4]. Weta analityków
  z 10-15 idą w kierunku zmierzonego błędu.
- **Przefitowanie samej luki księgi (B) tego nie naprawia**
  (-0.0014 [-0.0035, +0.0009]). **Siła ligi z wyników pucharowych naprawia**:
  jako dodatek do log-luki uczony tylko z meczów pucharowych (D)
  -0.0262 [-0.0366, -0.0161] log-loss 1X2 na mecz poza próbą (2 194 mecze),
  przy luce >= 0.5 -0.0441 [-0.0643, -0.0252]; prostsze proxy Elo (C)
  -0.0111 [-0.0149, -0.0077].
- **Nie zmierzono**: innych metryk niż gole (corners / shots mają własne
  sigma - prawdopodobnie ten sam mechanizm, do zmierzenia per metryka);
  wersji wbudowanej w `RatingBook.update` (tu D jest dodatkiem post hoc i nie
  zmienia aktualizacji ilorazów - wersja w księdze musi być zmierzona
  osobno); wpływu na wydrukowane nogi i na ceny Superbetu (historia nie ma
  cen); meczów krajowych pucharów z niższymi ligami (poza zakresem).

## Co potrzebowałaby poprawka

Zmienia to, co się drukuje, więc: przełącznik w `bet.sofa.epochs` (np.
`FOOTBALL_CUP_STRENGTH_FROM_UTC`, domyślnie None / następny dzień 00:00Z),
siła ligi z meczów międzynarodowych pucharów klubowych w `RatingBook`
(lista rozgrywek w configu, nie w kodzie), znacznik na wierszu SHEET-u
(`cup_strength_rule`) z ponownym SHEET-em w `rebuild_plan.py`, ta sama
reguła w replayu (`calibrate_from_cache.py --cup-strength`) i refit krzywych
piłkarskich na kopii bazy - krzywe są dopasowane na centrach replayu, a
krzywe 1X2 / DNB są jeszcze tylko stage'owane. To nie jest pozycja audytu
2026-10-13, więc stała zgoda jej nie obejmuje: potrzebna decyzja operatora.
Do tego czasu weta CONTEXT na takich meczach mają oparcie w pomiarze.
