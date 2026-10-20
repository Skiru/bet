# Pokrycie rynków zawodników w piłce: SAMPLES (2026-10-21)

Przełącznik: `epochs.FOOTBALL_PLAYER_COVERAGE_FROM_UTC` - **wyłączony**
(`None`); datę ustawia sesja główna. Wyłączony = bajt w bajt jak dziś
(E2E poniżej: replay SAMPLES z wyłączonym przełącznikiem odtwarza prawdziwe
`03_samples.json`). Centrum zawodnika (model udziału) nie jest tu zmieniane -
zmienia się tylko to, **czy** zawodnik ma próbkę i z ilu meczów.

Narzędzie pomiaru: `scripts/sofa/measure_player_coverage.py` (`identity`,
`window`; tylko odczyt).

## 1. Skąd brak wiersza SHEET (10-17..10-20)

Każdy szczebel zawodnika z końcowego `04_offer.json` (170 099 szczebli,
6 678 zawodnik-mecz-dzień) przypisany do pierwszej przyczyny braku wiersza
w `05_sheet.json`:

| przyczyna | szczeble | udział |
|---|---|---|
| ma wiersz SHEET | 42 601 | 25% |
| `THIN_SAMPLE` (< 5 startów w 10 ostatnich meczach drużyny) | 57 616 | 34% |
| próbka jest, SHEET odrzuca linię (`OUTSIDE_MODEL_RESOLUTION`: p poza [0,05; 0,95] - wysokie szczeble) | 23 369 | 14% |
| `NO_ENTITY_FOUND` - w kadrach, ale **nigdy nie zaczął** | 20 621 | 12% |
| `NO_ENTITY_FOUND` - nie znaleziony w żadnej kadrze | 12 467 | 7% |
| próbka z samych zer (`ALL_ZERO_SAMPLE`) | 12 328 | 7% |
| szczebel doszedł po SAMPLES (oferta poranna go nie miała) | 969 | 1% |
| `AMBIGUOUS_ENTITY` | 128 | 0% |

Każdy rynek ma ten sam rozkład (strzały 34% / 26%, faule 34% / 29%, asysty
34% / 14% z 25% zer). `THIN_SAMPLE` u strzałów: 1 start 636 zawodników,
2 - 569, 3 - 543, 4 - 516; prawie zawsze z 10 meczów drużyny z kadrą (2 175
z 2 264). „14% odrzucone przez SHEET” i „7% zer” to nie SAMPLES - poza
zakresem.

**Czy ci zawodnicy grają ten mecz?** (10-17..10-19, kadra meczu docelowego z
cache): ma wiersz - 78% zaczęło; `THIN_SAMPLE` - 43% zaczęło, 24% weszło z
ławki, 21% w kadrze bez gry, 9% poza kadrą; „nigdy nie zaczął” - 12%
zaczęło; „nie znaleziony” - 60% poza kadrą meczu (kontuzje, nieobecni: Kirił
Despodov, John Souttar), 35% w kadrze pod inną pisownią, 2% zaczęło.
Superbet zwraca zakład zawodnika, który nie zaczął (zwrot, 0 j.).

**Przyczyny na 40 losowych „nie znaleziony”** (kadry z cache): brak w kadrze
meczu (większość); transliteracja polska / angielska (Jehor Macenko / Yegor
Matsenko, Wiktor Cyhankow / Viktor Tsygankov, Bohdan Wjunnyk / Bogdan
Viunnyk); znak elizji (Daniel N\`Lundulu / Dan N'Lundulu); pełne hiszpańskie
nazwisko (Javier Martinez Calvo / Javi Martinez); nowy zawodnik drużyny
(Karlan Grant, Ivan Mesik - w kadrze meczu, nie w 10 poprzednich);
zdrobnienia (Charalampos / Charis Mavrias, Konstantinos / Kostas Fortounis) i
jednowyrazowe nazwy Superbetu (Bremer, Peglow) - **nie** poprawiane (patrz
ryzyka).

## 2. Poprawka (a): strzał w słupek liczony raz

Tożsamość, która dowodzi brakującego zera celnych, dodawała `hitWoodwork` do
`celne + niecelne + zablokowane`. Strzał w słupek jest już w jednej z tych
trzech. Najnowsze 20 000 składów w cache (`identity`):

| | grający z `totalShots` | 3 składniki domykają | 4 składniki domykają |
|---|---|---|---|
| `onTargetScoringAttempt` obecne | 59 804 | **59 804** | 57 388 |
| `onTargetScoringAttempt` brak | 153 243 | **153 243** | 151 127 |

213 047 / 213 047 dla trzech składników; czteroskładnikowa odrzucała jako
`INTERNAL_INCONSISTENT` dokładnie 2 116 udowodnionych zer - każde z
`hitWoodwork`. Zawodnik, który trafił w słupek, tracił ten mecz z próbki
celnych (próbka zawyżona: wypadały mecze z 0 celnych). Za przełącznikiem:
`players.SHOTS_IDENTITY_PARTS`, `extract_player_metric(woodwork_once=True)` w
SAMPLES, a SETTLE czyta tak samo dzień z przełącznikiem (inaczej noga
„celne poniżej” zawodnika ze słupkiem zostałaby nierozliczona;
`07_settle_skips.json` 10-14..10-19: 2-17 wystąpień
`player_shots_on_target_for:INTERNAL_INCONSISTENT` dziennie).

## 3. Poprawka (b): starty w 20 ostatnich meczach

Zawodnik z < 5 startami w 10 ostatnich meczach drużyny dostaje próbkę z
najnowszych (najwyżej 10) startów w 20 ostatnich (`samples.PLAYER_WIDE_SAMPLE_N`,
ten sam listing i `finish_history` co próbka, starsze mecze tylko po kadrę).
Próbka > 180 dni nadal odpada w CONFIDENCE (`SAMPLE_CROSSES_SEASON`).

Replay historii 08-01..10-19 (`window`, 3 058 meczów docelowych, kod
`calibrate_from_cache.build_player_rows`: tylko wyjściowi, próbka = starty,
p jak replay bez stretchu - jednakowo dla obu grup), odczyt przez
zainstalowaną krzywą (`Calibration.realised`, przed line evidence), wiersze z
pewnością ≥ 0,70, CI = bootstrap po meczach:

| rynek | kier. | BASE n | W20 n | BASE realised − pewność | W20 realised − pewność | W20 − BASE |
|---|---|---|---|---|---|---|
| asysty | UNDER | 14 837 | 1 451 | +0,5 [+0,0; +0,9] | +1,2 [−0,3; +2,7] | +0,7 [−1,0; +2,3] |
| faule | OVER | 5 411 | 505 | +0,5 [−0,5; +1,7] | +3,0 [−0,8; +6,8] | +2,5 [−1,7; +6,3] |
| faule | UNDER | 43 736 | 4 587 | +0,5 [+0,1; +0,8] | −0,1 [−1,2; +1,0] | −0,6 [−1,7; +0,7] |
| spalone | UNDER | 11 627 | 1 440 | +1,0 [+0,4; +1,6] | +0,2 [−1,5; +1,7] | −0,8 [−2,6; +0,6] |
| strzały | OVER | 8 353 | 783 | +2,0 [+1,0; +2,8] | +3,0 [+0,1; +5,7] | +1,1 [−1,7; +3,8] |
| strzały | UNDER | 55 171 | 5 873 | −0,4 [−0,8; +0,0] | −0,5 [−1,8; +0,7] | −0,1 [−1,4; +1,0] |
| celne | UNDER | 31 143 | 3 434 | −0,1 [−0,6; +0,3] | −0,3 [−1,5; +0,9] | −0,1 [−1,5; +1,1] |
| odbiory | OVER | 11 143 | 1 105 | +1,4 [+0,6; +2,2] | +2,3 [−0,2; +4,7] | +0,8 [−1,8; +3,3] |
| odbiory | UNDER | 50 575 | 5 353 | +0,1 [−0,4; +0,5] | −0,0 [−1,2; +1,1] | −0,1 [−1,3; +1,1] |
| **razem** | | 231 996 | 24 531 | +0,2 [+0,1; +0,4] | +0,2 [−0,4; +0,7] | **−0,1 [−0,6; +0,5]** |

(pp.) Odzyskane wiersze realizują się na krzywej jak dzisiejsze - żadna grupa
nie jest gorsza z przedziałem poza zerem; +10,6% wierszy ≥ 0,70. Alternatywa
„obniż próg do 3-4 startów z 10” na tych samych wierszach: log-loss
W20 − LOW **−0,0339 [−0,0387; −0,0293]** (48 892 wiersze) - szersze okno
jest wyraźnie lepsze niż niższy próg. Uwaga: BASE jest in-sample dla krzywej
(dopasowanej na takich wierszach); W20 nie było w jej dopasowaniu.

Replay odtwarza regułę flagą `calibrate_from_cache --player-coverage`
(test `test_the_replay_widens_a_thin_starter_like_samples`).

**Nie zrobione:** historia z poprzedniego klubu (`/player/{id}/events/last`).
W cache nie ma tej trasy, więc nie da się jej zmierzyć offline; na żywo to
1 + ~10 zapytań (listing zawodnika + składy obcych meczów) na zawodnika -
przy ~550 zawodnikach `THIN_SAMPLE` dziennie kilka tysięcy zapytań mostu.

## 4. Poprawka (c): dwie reguły nazw

Po regule nazwiska (K7), na tych samych warunkach („każda kadra, która
odpowiada, wskazuje tę samą osobę po tej samej stronie”):

- `players.match_player_by_transliteration`: obie nazwy złożone
  transliteracją (`w→v`, `j/y→i`, `ts/tz→c`, `cz→ch`, `sz→sh`, `x→ks`,
  `kh→h`, `g→h`, bez `` ` ' . ``), porównane tylko regułą tokenów i regułą
  nazwiska (całe tokeny). Próba z progiem podobieństwa na złożonych nazwach
  dawała innego człowieka 18 razy na 12 989 (Kirian / Adrian Rodriguez,
  Wanderson / Wenderson) - odrzucona; podwójne litery nie są składane
  („saleem” ≠ „salem”).
- `players.match_player_by_inner_surname`: ostatni token Sofascore jest
  jednym z dalszych tokenów nazwy Superbetu (≥ 3 tokeny, bez przecinka),
  imiona mają wspólny prefiks ≥ 3 liter; „Abdul…” nie jest prefiksem
  (Abdulelah / Abdul Rahman Al Khaibari to dwaj ludzie).

Precyzja (jak K7): 10-12..10-20, 23 666 par (zawodnik z `match_rule: fuzzy`,
kadra jego meczu) - reguła na pełnej kadrze: **0 razy inny człowiek**
(transliteracja 22 519 ten sam, 1 147 brak; nazwisko w środku 1 039 / 22 627);
po usunięciu prawdziwego zawodnika z kadry: **0 fałszywych wskazań** na
23 666 dla obu reguł. Zasięg: ~29 + ~16 z 893 luk „nie znaleziony” na
strzałach w 9 dni (część to przeciwnicy z meczów bezpośrednich - liczba
orientacyjna). SETTLE ocenia te próbki po `matched_name` jak tokeny
(`run_settle.player_token_names`) i w dniu z przełącznikiem szuka kandydata
także tymi regułami w drugiej kadrze (`PLAYER_AMBIGUOUS`).

## 5. E2E (offline, kopia; baza tylko do odczytu)

SAMPLES (część zawodników) odtworzone z cache dla meczów piłkarskich z
zawodnikami (10-19: 17 meczów, 10-20: 15), klient bez sieci (każde zapytanie
policzone jako brak w cache), wyłączony vs włączony; potem SHEET i
CONFIDENCE na kopiach dnia w scratchpadzie (`SOFA_RUNS_DIR`), nigdy w
`runs/sofa/<d>/`.

| | 10-19 | 10-20 |
|---|---|---|
| wyłączony vs prawdziwe `03_samples.json` (te same wartości) | 4 786 / 0 różnych | 4 691 / 0 różnych |
| próbki odzyskane (≥ 5 obserwacji tylko z włączonym) | 936 | 840 |
| - okno 20 / transliteracja / nazwisko w środku / słupek | 904 / 13 / 15 / 4 | 837 / 0 / 0 / 3 |
| próbki utracone | 0 | 0 |
| próbki zmienione (celne: słupek) | 17 | 31 |
| szczeble z próbką ≥ 5 (z wszystkich szczebli zawodników) | 7 213 → 9 990 (z 18 388) | 8 267 → 10 699 (z 16 776) |
| zapytania, których cache nie zna (włączony) | 1 składy, 20 shotmap | 24 składy, 34 shotmap, 1 statystyki |
| wiersze SHEET | 14 264 → 17 042 | 15 960 → 18 580 |
| wiersze nie-zawodnicze zmienione | 0 | 0 |
| wiersze zmienione (celne, słupek) / utracone | 74 / 2 | 128 / 14 |
| nogi CONFIDENCE (single) | 476 → 476 | 407 → 409 |
| nogi utracone / ze zmienioną pewnością | 0 / 0 | 0 / 0 |
| nowe nogi | 0 | 2 |

Utracone wiersze SHEET to wysokie szczeble celnych (Ramon Terrats 2,5,
Darwin Nunez 3,5, Mason Greenwood 4,5), których p ≈ 0,05 po dodaniu meczów
z zerem wypadło poza [0,05; 0,95] - nikt ich nie drukuje. Nowe wiersze w
CONFIDENCE odpadają głównie `BELOW_CONFIDENCE_FLOOR` (+1 307 / +1 240) i
`NO_PRICE` (+1 389 / +1 310 - strona „poniżej” rynku jednostronnego). Nowe
nogi 10-20: Kaan Kairinen faule powyżej 0,5 (pewność 0,782, kurs 1,20) i
Kaheem Parris strzały powyżej 0,5 (0,742, kurs 1,22), obie `PLAYER_WIDE_WINDOW`.
Druk rośnie więc o 0-2 nogi dziennie; pokrycie SHEET o ~17-20%.

## 6. Ryzyka i otwarte

- 43% zawodników `THIN_SAMPLE` zaczyna mecz: część nowych nóg to zwroty
  (0 j.), ale zajmują miejsce na liście do czytania.
- `prepare_refit.py` nie przekazuje jeszcze `--player-coverage` do replayu:
  przy następnym refitcie po włączeniu trzeba go dodać do `replay_rules`
  (krzywe są skalibrowane dla odzyskanych wierszy już dziś - tabela w 3).
- Pomiar W20 bez `player_stretch` (który SHEET stosuje) - jednakowo dla obu
  grup; brak pomiaru na liniach Superbetu (nogi jeszcze nie istniały).
- Nie poprawione: zdrobnienia, jednowyrazowe nazwy Superbetu (pojedynczy
  token nieudowodniony, K-pomiar 2026-10-11), historia z poprzedniego klubu,
  `STAT_KEY_ABSENT` rynków z shotmapy (shotmapa ≠ `totalShots`).
- Pre-existing: `tests/sofa/test_documented_commands.py` pada na
  `scripts/sofa/measure_cs2_map_total_race.py` (plik jest w MAIN, nie w
  repozytorium) - niezwiązane z tą zmianą.
