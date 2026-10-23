# Audyt pokrycia danych - 2026-10-23

Pytanie: czy dane, które leżą w `data/sofa.db`, docierają do czytelników
historii (SAMPLES, `score_model`, `player_model`, SPORT_IDENTITY, silnik CS2)?
Hipoteza z zadania: ta sama klasa błędu („dane są, czytelnik ich nie widzi”)
siedzi w więcej niż jednym sporcie.

Metoda: siedem subagentów, równolegle, tylko do odczytu (piłka, tenis, hokej,
kosz, siatkówka, CS2, liczby nocy 10-22/23). Każdy policzył lejek na dniach
10-21, 10-22, 10-23 i podzielił każdy spadek na klasy: **A** = brak danych w
bazie, **B** = dane są, czytelnik ich nie widzi, **C** = celowa reguła (plik
i linia). Główna sesja odtworzyła lokalnie co najmniej jedną liczbę na sport
(sekcja 9). Skrypty, zapytania i pełne tabele subagentów: scratchpad sesji
(`audit/*.md`, `audit/*.py`); tu tylko wnioski.

## 1. Streszczenie

- **Główny przykład z zadania nie jest błędem czytelnika.** LaMelo Ball
  (1092868) w naszej bazie zagrał 10-21 dla Minnesoty (3426, mecz 16814807),
  a Superbet ma jego linie przy meczu Orlando - Minnesota (15355369). Model
  zawodników czyta tylko mecze dwóch drużyn, które dziś grają
  (`run_shadow.pinned_teams` -> `player_model.load_appearances`,
  `player_model.py:391`). W Minnesocie ma 1 mecz, a jego 84 mecze w Charlotte
  leżą w bazie nieczytane. Ten sam czytelnik ustawiony na Charlotte (3430)
  daje mu 58 meczów.
- **To jest znany, otwarty punkt K7** („zawodnik znany tylko z innej
  drużyny”, model-state.md (b)). Dotyczy kosza, hokeja i piłki. CS2 go nie
  ma: udział gracza idzie za jego id między drużynami. Poprawka jest **zmianą
  modelu**, nie poprawką poprawności: zmienia druk (hokej: 11 z 43 nóg na
  zawodników dotyczy takich graczy), więc wymaga pomiaru i przełącznika.
- **Prawdziwe defekty klasy B są w identyfikacji meczów** (CS2, siatkówka) i
  w kilku miejscach piłki i siatkówki (slug zawodnika, zera spalonych,
  `ENTITY_CONFLICT`, przenumerowana liga Kataru). Każda poprawka zmienia
  druk, więc czeka na decyzję operatora (sekcja 7).
- **Dwa twierdzenia z zadania i raportu nocy są błędne.**
  - Tenis: „208 jałowych rozgrywek” liczyło rozgrywki wszystkich sportów
    (tenisowych jest 174, same ITF i juniorzy), a „0 celów” w nocy wynikało z
    tego, że tenis był już w pełni odpytany o 21:36Z (3 928 meczów).
  - „740 drużyn piłki w kolejce trzeciego przeskoku” to błędny odczyt logu:
    te 740 driver już przeszedł. Prawdziwa kolejka to 1 611.
- **Od razu, bez wpływu na druk, poprawiłem trzy narzędzia** (sekcja 8):
  - instalator krzywych sportowych pisze też do plików z datą (punkt #15
    raportu nocy);
  - driver backfillu nie wchodzi w przeskok ponad limit i loguje prawdziwą
    kolejkę;
  - reguła „jałowych” rozgrywek liczy w obrębie jednego sportu i nie dotyczy
    tenisa.

## 2. Lejki

### Piłka

| | 10-21 | 10-22 | 10-23 |
|---|---|---|---|
| fixtures | 188 | 125 | 344 |
| zablokowane w SAMPLES (zawsze `NO_PRICE`) | 20 | 20 | 13 |
| mecze wycenione | 168 | 105 | 331 |
| wiersze z confidence | 17 998 | 35 713 | 39 182 |
| >= 0,70 | 2 279 | 3 515 | 5 896 |
| pojedyncze nogi (08) | 1 725 | 1 767 | 3 690 |
| strony z próbką < 5 | 2 | 0 | 7 (6 `ENTITY_CONFLICT`) |
| zawodnicy z oferty / z próbką | 478 / 384 | 1 584 / 1 349 | 1 102 / 833 |
| zawodnicy `NO_ENTITY_FOUND` | 94 | 234 | 268 |
| nogi zawodników >= 0,70 | 11 | 19 | 10 |

Oba źródła listy meczów zgadzają się na wszystkich trzech dniach.
`sofa_listed_event` nie ma żadnego meczu, który wymienia drużynę z boardu, a
brakuje go w jej własnym `sofa_listing_event`. Zablokowane fixtures to zawsze
brak ceny, nigdy brak danych.

Liczby z zadania, sprawdzone na 10-23:
- **potwierdzone:** 268 `NO_ENTITY_FOUND`, 215 z 833 zawodników z 1-4
  startami, 86 meczów `THIN_SAMPLE` (83 na `corners_1h_total`, 63 tylko na nim);
- **inaczej niż w zadaniu:** 55 / 55 / 121 to piłka razem z tenisem; sama
  piłka to 36 `INTERNAL_INCONSISTENT` / 53 `STAT_KEY_ABSENT` / 119
  `NO_STATISTICS`;
- **z 7 stron z próbką < 5** sześć to `ENTITY_CONFLICT`, nie trzy.

### Tenis

| | 10-21 | 10-22 | 10-23 |
|---|---|---|---|
| wpisy boardu / niezmostkowane | 525 / 19 | 354 / 4 | 223 / 11 |
| fixtures / zablokowane `NO_PRICE` | 401 / 165 | 289 / 89 | 187 / 59 |
| strony z próbką | 472 | 400 | 256 |
| zakończone single tych graczy w bazie | 43 825 | 39 827 | 26 972 |
| z nich na porównywalnej nawierzchni | 21 681 | 20 759 | 14 052 |
| średnie n na stronę (gemy) | 9,1 | 9,3 | 9,6 |
| nogi >= 0,70 (wszystkie wydrukowane) | 401 | 520 | 297 |

Największe cięcie to reguła nawierzchni (C, około połowy meczów). Replika
przyjęć SAMPLES zgadza się z `03_samples.json` na każdej stronie z próbką
< 5 w dniu 10-23. Z dziesięciu meczów z próbką < 5 osiem to reguła
nawierzchni, a dwa to nowi gracze. Żaden nie jest brakiem danych ani błędem
tożsamości.

### Hokej

| | 10-21 | 10-22 | 10-23 |
|---|---|---|---|
| wydarzenia / zidentyfikowane | 78 / 78 | 46 / 45 | 146 / 146 |
| wiersze nierozpoczęte / z `p` | 3 089 / 3 057 | 2 667 / 2 613 | 6 358 / 6 358 |
| >= 0,70 / nogi | 362 / 247 | 309 / 197 | 889 / 513 |
| zawodnicy (NHL) / z `p` | 339 / 332 | 275 / 257 | 270 / 268 |

Model wyniku (`score_model.load_events`) czyta indeks bez klucza drużyny i
odrzuca tylko 34 z 30 960 zakończonych meczów (nie 3 tercje albo walkower).
Po stronie drużyn nie ma ślepoty czytelnika. Składy NHL w oknach 60 meczów:
960 z 960.

### Kosz

| | 10-21 | 10-22 | 10-23 |
|---|---|---|---|
| wydarzenia / zidentyfikowane | 119 / 115 | 77 / 73 | 131 / 130 |
| drużyny z ratingiem (n >= 5) | 230 / 230 | 144 / 146 | 260 / 260 |
| nogi (wszystkie >= 0,70) | 4 | 5 | 58 (34 + 24 z późnego okna) |
| linie zawodników `NO_MODEL_P` | 1 550 | 102 | 1 594 |

Dzień 10-23 ma **dwa** pliki modelu zawodników: późne mecze NBA (start
10-24 00:00-02:00Z) są w `shadow/basketball/2026-10-24/player_model.jsonl`
(SPORT_CONFIDENCE czyta je po `source_date`). „269 zawodników” z zadania to
tylko plik 10-23, a późny plik dodaje 175 kolejnych. Dziewięć nowych rodzin
(`BASKETBALL_PLAYER_V2`) Superbet nazywa „Imię Nazwisko”, a stare „Nazwisko,
Imię”, więc jeden gracz to dwa napisy: 269 napisów to 161 graczy.

10-21: 1 897 wierszy drużyn `NO_MODEL_P` na 5 meczach NBA. To była dziura w
listach drużyn (A), zamknięta backfillem 10-22. Dzisiejsza powtórka na
zegarze budowy daje wszystkim pięciu meczom `p`.

### Siatkówka

| | 10-21 | 10-22 | 10-23 |
|---|---|---|---|
| fixtures / IDENTIFIED | 57 / 28 | 59 / 27 | 53 / 43 |
| NOT_IDENTIFIED otwarte | 18 | 11 | 2 |
| `NO_LEAGUE_RATE` / `TOURNAMENT_NEVER_SETTLED` | 0 / 0 | 1 / 1 | 1 / 7 |
| nogi | 24 | 12 | 15 |

Liczby z zadania dla 10-23 się potwierdziły z jednym wyjątkiem: otwartych
NOT_IDENTIFIED są **2**, nie 3. Pozostałe 8 zaczęło się przed budową i liczy
się jako KICKED_OFF. Większość zidentyfikowanych nóg odpada na `BELOW_FLOOR`
(krzywa, nie dane).

### CS2

| | 10-21 | 10-22 | 10-23 |
|---|---|---|---|
| serie / IDENTIFIED | 74 / 50 | 69 / 31 | 30 / 24 |
| pojedynki 1x1 (A) | 18 | 31 | 0 |
| NOT_IDENTIFIED z gry obecnej w bazie | 4+1+1 | 3+1 | 6 |
| zidentyfikowane bez `p` Elo | 7 | 5 | 3 |
| nogi | 16 | 20 | 6 |
| zawodnicy / dopasowani / z udziałem | 160 / 157 / 157 | 40 / 40 / 40 | 10 / 10 / 10 |

## 3. Defekty klasy B (dane są, czytelnik ich nie widzi)

Kolejność według liczby nóg i podmiotów, które poprawka może odzyskać.

### B1. Zawodnik znany tylko z innej drużyny (K7) - kosz, hokej, piłka

- **Przyczyna:** próbka zawodnika to mecze **drużyn z dzisiejszego meczu**.
  - kosz / hokej: `player_model.load_appearances` -> `listed_games(team)`,
    `player_model.py:338-447`;
  - piłka: `samples.py:1357-1530`, `_player_observations` po
    `side_results` drużyny.

  Nikt nie szuka gracza po id w składach innych drużyn.
- **Przykłady:**
  - LaMelo Ball: 1 mecz w Minnesocie, 84 w Charlotte;
  - Naz Reid (Charlotte - Atlanta, 10-23): `model_n` 1, w bazie 94 mecze
    Minnesoty z jego nazwiskiem;
  - Ilya Lyubushkin (10-22): `NOT_IN_HISTORY`, nazwisko w 156 składach
    (149 meczów Dallas);
  - Zian Flemming (piłka, 10-23): n=1 w Ipswich, 3 starty w Burnley od
    06-15.
- **Zasięg:**
  - kosz 10-23: 53 graczy (44 transfery w NBA, 9 debiutantów z NCAA), 1 398
    z 1 594 linii `NO_MODEL_P`; 10-21: 36 graczy, 426 linii;
  - hokej: 168 z 884 zawodnik-dni (106 graczy). 156 z nich ma `p`, ale
    policzone na medianie 9 meczów zamiast 60;
  - piłka 10-23: co najmniej 11 transferów wśród 215 graczy z 1-4 startami i
    około 5 wśród `NO_ENTITY_FOUND`;
  - CS2: brak. Udział podąża za id gracza (`cs2_engine.py:1059-1075`,
    `1242-1246`). Dziura tylko w przypadku zera map w nowej drużynie
    (`player_id` szuka w ostatnich 20 mapach drużyny); na tych dniach zero
    przypadków.
- **Druk:**
  - hokej: tak. 11 z 43 nóg zawodników to gracze K7 wycenieni na 5-10
    meczach, choć mają 50+ w poprzednim klubie (Peterka, Marchment, Kuzmenko,
    Trouba..., wszystkie `player_pp_points` UNDER 0,5, confidence
    0,78-0,88). Kierunek zmiany `p` niezmierzony;
  - kosz: na tych dniach nie, bo żadna linia gracza nie doszła do 0,70.
    Dodałoby około 1 400 wycenionych linii dziennie na starcie sezonu, co
    przyspiesza line evidence dla propsów NBA (podejrzenie, niezmierzone);
  - piłka: kilka wierszy dziennie.

### B2. CS2: tożsamość nie pyta ponownie o stronę drużyny z cache

- **Przyczyna:**
  - SPORT_IDENTITY pyta o stronę `next` **jednej** drużyny
    (`sport_identity.py:789`), z cache do 6 h (`config.py:105`);
  - świeże zapytanie (K5) odpala się tylko przy powodzie
    `NO_GAME_WITHIN_1H` (`sport_identity.py:815`), a matcher CS2 nigdy go
    nie daje: zwraca `NO_MATCH_IN_LISTING` (`sport_identity.py:661`, `:687`);
  - strony drugiej drużyny nikt nie pyta.
- **Przykład:** 10-23 Maybe - Eternal Premium, start 10:30Z. Strona Maybe
  (1244353) pobrana 05:31Z ma tylko mecz z Sokerorg o 13:00 i wygasa o
  11:31Z, czyli po starcie meczu.
- **Zasięg:**
  - 23 z 67 chybień z cache (10-08..10-23) leżą potem w `cs2_series` jako ta
    sama para o tej samej godzinie;
  - do tego START_GAP (Nemesis - WW Team) i AMBIGUOUS (Damajuana - Hacha)
    z tej samej przyczyny;
  - 10-23: wszystkie 6 NOT_IDENTIFIED (12 drużyn, wszystkie zweryfikowane,
    z historią).
- **Druk:** tak, dochodzą serie (1-6 dziennie).

### B3. Siatkówka: tożsamość „query-only” odrzuca mecz, który ma

- **Przyczyna:**
  - gdy żadna drużyna nie ma dokładnego id, drużyna znaleziona po nazwie
    (fuzzy) nie jest kotwicą (`sport_identity.py:780`, `:490`) i obie
    nazwy muszą przekroczyć 82 (`_side_ok`, `:466-478`);
  - DAY_ANCHOR bierze tylko rozwiązane id (`:576`).
- **Przykład:** OK Maribor - ACH Lublana (10-23 18:30Z). Strona `next` OK
  i-Vent Maribor (276327) z cache ma mecz 17267345 Maribor - ACH Volley
  Ljubljana o dokładnej godzinie. Nazwy: 100 i 71 („Lublana” to polska
  nazwa).
- **Zasięg:** 11 takich meczów od 10-14. Na 10-21..10-23 dotyczy to 3
  otwartych wydarzeń (68 wierszy).
- **Skutek pośredni:** Deya Burgas - Neftohimic (10-22) był w cache, nie
  został zidentyfikowany, a przy rozliczeniu zapisano go jako
  NOT_ON_SOFASCORE. „Bułgaria - SuperLiga” nie ma więc rozliczonego meczu, a
  2 męskie mecze bułgarskie 10-23 (64 wiersze) dostały
  `TOURNAMENT_NEVER_SETTLED`. To przy założeniu, że rozliczenie oceniłoby
  zidentyfikowany mecz.
- **Druk:** tak.

### B4. Piłka: `ENTITY_CONFLICT` opróżnia próbkę za starcie sprzed lat

- To formalnie reguła C (`samples.py:671-685`). Zasięg jest jednak klasy B,
  bo komentarz uzasadniający regułę („a clash there is a clash near the
  sample”, `samples.py:628-631`) się nie broni.
- **Zasięg:** 12 fixtures w 3 dni, w tym 7 starć starszych niż 4 miesiące.
  Najstarsze: Bayern U19, turniej Spax Cup 2016-05-15. Pula goli tnie już
  przy starciu (`cut_at_conflict`, `samples.py:599`), a próbka nie.
- Dwa z tych starć wywołały turnieje towarzyskie, których brakuje na liście:
  ut 38292 „Memorijalni turnir Mladen Žižović” (Zrinjski) i ut 38659
  „Australian-Croatian Soccer Tournament” (Sydney United 58).
- **Druk:** tak, rynki drużyn tych meczów. Średnio około 11 nóg na
  wyceniony mecz, więc potencjalnie najwięcej nóg ze wszystkich pozycji (to
  oszacowanie, niezmierzone).

### B5. Piłka: slug zawodnika nie jest czytany

- **Przyczyna:** `players.squad_statistics` kluczuje skład tylko po
  `normalize_name(player["name"])` (`players.py:400`). `slug` i
  `shortName` z tego samego wpisu przepadają.
- **Przykład:** Superbet „Julian Chabot”, Sofascore `name: "Jeff Chabot"`,
  `slug: "julian-chabot"`, 17 startów dla Stuttgartu. W bazie 51 składów z
  tym slugiem (sprawdzone lokalnie).
- **Zasięg:** nasze dopasowania na slugu odzyskują 6 / 4 / 7 graczy
  (10-21 / 10-22 / 10-23), głównie regularnych (Bremer, Quaresma, Peglow,
  Pîrvulescu).
- **Druk:** tak, wiersze arkusza. Nogi co najwyżej pojedyncze. Potrzebny
  test fałszywych trafień (slug może należeć do innej osoby).

### B6. Piłka: zera spalonych odtworzone dla drużyny, nie dla zawodnika

- **Przyczyna:** brak pozycji `offsides` w `/statistics` czytelnik drużyn
  traktuje jako 0-0 (`metrics.fill_omitted_zero_pairs`, `metrics.py:729`,
  `749-765`). Czytelnik zawodników czyta surowy payload (`players.py:290`,
  `:310`), więc zera nie udowadnia i każdy zawodnik dostaje
  `STAT_KEY_ABSENT`. Na 6 000 najnowszych meczów pozycji brakowało 401
  razy, a suma zawodników wynosiła 0-0 w 397 z nich.
- **Zasięg:** 35 / 129 / 56 zawodników dziennie. Prawdziwe zera wypadają z
  próbki, więc `p(OVER 0,5)` czyta za wysoko.
- **Druk:** na tych dniach 0 nóg `player_offsides_for`, ale zmienia środki
  arkusza. Krzywa była dopasowana tym samym czytelnikiem, więc poprawka idzie
  w parze z refitem.

### B7. Siatkówka: liga Kataru przenumerowana

- Stawka ligi kluczuje się po id rozgrywek. Sezon 26/27 QVL to id 39366
  (3 mecze), a 104 mecze leżą pod id 2345 (2020-02..2024-12; sprawdzone
  lokalnie: 104 / 3).
- **Zasięg:** 2 mecze, 64 wiersze `NO_LEAGUE_RATE`.
- Do tego klasa A: w bazie nie ma sezonu 25/26, więc stawka spod 2345 ma 22
  miesiące.
- Sprawdzone przez most 2026-10-23: `unique-tournament/2345/seasons` -> 404,
  `39366/seasons` -> tylko 26/27 (106961). Sezonu 25/26 nie ma u źródła.
- **Werdykt: nie defekt.** Zmostkowanie id dałoby stawkę sprzed 22 miesięcy,
  więc `NO_LEAGUE_RATE` (30 meczów nowego id) jest tu właściwe (C). P10
  zamknięty bez zmiany.

### B8. CS2: bramka id drużyny blokuje rating składu

- `RatingModel.home_logit` zwraca None, gdy któraś drużyna (id) ma mniej
  niż 10 map (`cs2_engine.py:356-358`), choć rating składu by wystarczył.
- **Przykład:** 10-21 Envy - FaZe. Envy ma 9 map, a jego gracze 1 078 (958
  jako 3DMAX).
- **Zasięg:** 8 z 16 wydarzeń bez ratingu w 3 dni.
- **Druk:** tak. To zmiana modelu, wymaga pomiaru.

### B9. Mniejsze

- **CS2: „prospects” jest znacznikiem składu, „prospect” nie**
  (`cs2.py:680-686`). Przez to Privateer - Inner Circle Prospects (10-22)
  nie został zidentyfikowany, choć świeża strona miała mecz o tej godzinie.
  Jedna drużyna (29 serii).
- **CS2: nick.** Silnik dopasowuje dokładnie (`cs2_engine.py:1046-1056`),
  rozliczenie po prefiksie (`cs2.py:798-812`). `MartinezSa`: 1 gracz, 3
  serie.
- **CS2: 47 serii z wynikiem bez map** (74 mapy, 0,2%) - Elo ich nie widzi.
- **Hokej / kosz: mecz w liście tylko jednej drużyny.**
  - Przyczyna: `listed_games` filtruje po `entity_id` (`player_model.py:353`),
    strona listy zapisuje tylko właściciela (`listing_index.py:176`), a
    `sport_history.candidates` uznaje mecz za załatwiony
    (`sport_history.py:84`).
  - Zasięg: hokej 23 mecze w oknach NHL (545 występów); kosz 7 274 mecze w
    400 dni, na tych dniach bez skutku.
  - Druk: prawie na pewno nie.
- **Ścisła reguła nazw:** „Stuetzle, Tim” vs „Tim Stützle”, „Chinakhov,
  Yegor” vs „Egor Chinakhov” (hokej, 8 wierszy); „Gregory Jackson” vs „GG
  Jackson II” (kosz, 18 linii). Na tych dniach 0 nóg.
- **Siatkówka: `sofa_day_listing`** to drugie źródło, którego historia nie
  czyta: 90 zakończonych meczów (88 NCAA). Drużyny tracą 0-3 meczów z 45-97.
- **Tenis: stronicowanie.** Listy głębiej niż 5 stron i ponad 200 wierszy
  indeksu (`samples.py:466`, `:296`) czytelnik nie sięga. 3 strony / 7
  meczów, wszystkie starsze niż 180 dni, więc i tak `SAMPLE_CROSSES_SEASON`.
  Bez wpływu na druk.
- **Tenis: reguła „jałowych” rozgrywek w backfillu**
  (`backfill_event_stats.py:155-180`). W ITF statystyki są per mecz, nie per
  rozgrywka. Poprawione (sekcja 8); dotyczy tylko historii do refitów.

### Znalezione przez niezależnego weryfikatora (faza 4.5)

Świeży subagent dostał ten raport z zadaniem znalezienia dziury w każdym
sporcie. Znalazł w pięciu; w hokeju nic, co zmienia druk.

- **B10. Piłka: rekord sędziego widzi mniej więcej połowę jego meczów.**
  - Przyczyna:
    - `referees.fixture_reads` (`referees.py:534`) buduje rekord z
      `football_rating.load_history`, a kartki wymagają `incidents_json`;
    - `_already_asked` backfillu kluczuje tylko po statystykach
      (`backfill_event_stats.py:222`), więc wiersza ze statystykami i bez
      incydentów nikt nie pyta ponownie;
    - mecze sędziego spoza rozgrywek boardu w ogóle nie dostają statystyk
      (`target_competitions` = rozgrywki boardu).
  - Przykład: Cojocaru (92309) ma 30 etykiet, z czego 22 mecze nigdy nie
    dostały statystyk, więc n=7.
  - Zasięg 10-23: sędziowie z 1 906 etykietami przed cięciem, 957 ze
    statystykami, suma n 911. W całej bazie 8 560 meczów z sędzią ma
    statystyki i nie ma incydentów (sprawdzone lokalnie; 8 070 w 365 dniach).
  - Klasa A z defektem narzędzia. Zmienia środki kartek i fauli, więc druk;
    to jednak dane, nie kod (dzienny `backfill_referees.py` robi to samo dla
    etykiet).
  - Naprawa narzędzia (`--incidents-only`, sekcja 8) i backfill w toku.
- **B11. Kosz: NCAA wypada z modelu wyniku.** `parse_event` wymaga
  dokładnie `regulation_periods` (4, `score_model.py:424`), a mężczyźni w
  NCAA grają dwie połowy. 2 842 mecze w 365 dniach. Od startu sezonu
  (~11-03) każdy mecz NCAA bez `p`. Na boardach tych dni NCAA nie było; czy
  Superbet je oferuje, to podejrzenie. Zmienia druk.
- **B12. CS2: serie rozliczone z samego wyniku nie mają `model_p`.**
  Ścieżka „series-only” w `settle_cs2.py:334-362` kończy się przed
  `attach_model`, a `cs2_settled_rows` (`sport_confidence.py:1503`) pomija
  wiersze bez `model_p`. Line evidence CS2 traci 392 linie ze 116 serii
  (232 z 1 480 linii `match_winner`, 15,7%). Zmienia line evidence, czyli
  druk. Kierunek niezmierzony.
- **B13. Siatkówka: mecze „AET” / „AGS” (złoty set) odrzucone i
  nierozliczone.** Liczy się tylko „Ended” (`shadow.py:132`), więc model
  wyniku je odrzuca, a SHADOW_SETTLE daje UNUSUAL (`shadow.py:1574`).
  Przykład: 15999857 Belluno - Altotevere. 44 mecze rocznie, głównie
  play-off; na tych dniach zero.
- **B14. Tenis: rating gubi część rozstrzygniętych singli**
  (`tennis_rating.py:221`, `:233`):
  - 113 meczów „Ended” rocznie bez `winnerCode`, choć wynik w setach jest
    jasny (np. 17362029, 6-0 6-1);
  - 46 singli z graczem typu 0, czytanych jak debel.

  Zasięg: 27 graczy z boardu straciło po jednym meczu w 3 dni. Mały.
- **Hokej:** 19 meczów NHL z 10-20..10-22 ma tylko składy, statystyki NULL
  (zapis `settle_shadow.py:684`). Backfill je dopyta, a przełączniki, które
  ich używają, są wyłączone. 5 meczów ECHL tylko w `sofa_day_listing`. Bez
  wpływu na druk.
- **Sprawdzone i czyste:** filtr meczów towarzyskich (brak fałszywych
  trafień w żadnym sporcie); żaden fixture piłki z `NO_REFEREE` nie miał
  sędziego w bazie w chwili budowy.
- **Korekta liczb:**
  - `sport_fixtures.json` 10-23 przepisano o 10:04Z (pętla), więc hokej
    150 / 150, kosz 134 / 132, siatkówka 64 / 47. Tabele wyżej to stan z
    budowy 08:31Z;
  - CS2 „47 serii bez map” to teraz 50 serii / 79 map, plus 21 serii z
    częścią map.

## 4. Braki danych (A) i plan backfillu

| brak | sport | cele | most | wpływ na druk |
|---|---|---|---|---|
| ITF single pominięte przez regułę „jałowych” (365 d) | tenis | 339 | ~30 s | nie; **zrobione** (sekcja 8: 467 celów, 92 ze statystykami) |
| własne listy drużyn bez żadnej strony (`sofa_listing_event` pusty) | kosz 2 (Kolumbia 300975, 516803), siatkówka 4 | 6 encji | sekundy | nie (model wyniku czyta indeks) |
| sezon 25/26 QVL (Katar) | siatkówka | sprawdzone przez most: nie istnieje | - | nie (B7 zamknięte) |
| mapy 47 serii z wynikiem | CS2 | 47 | sekundy | marginalnie |
| hop 3 listingów piłki | piłka | 1 611 encji | ~1-2 h | nie: 673 z 688 drużyn boardu 10-23 ma kompletną historię, pozostałe 15 nie sięga próbki 10 meczów |
| starsze single tenisa (> 365 d) | tenis | ~111 tys. | ~2,7 h | nie (tylko refit) |
| składy AHL | hokej | 0 z 2 114 meczów ma zawodników | - | Sofascore chyba ich nie publikuje (niesprawdzone) |
| pierwsze połowy rożnych, statystyki per set, zawodnicy w eliminacjach UEFA | piłka / tenis | - | - | Sofascore tego nie podaje (sprawdzone na payloadach i przez most) |

Nie do odzyskania backfillem, bo Sofascore tego nie ma:
- `corners_1h_total`: 12 największych dotkniętych rozgrywek nie ma `1ST` w
  żadnym payloadzie 2026 (np. Cymru Premier 0 z 177);
- asy per set: przez most `periods=ALL` tylko;
- składy bez statystyk zawodników w eliminacjach UEFA (671);
- `groundType` None w tenisie.

## 5. Wykluczenia celowe (C)

| reguła | plik:linia | gdzie widać |
|---|---|---|
| tylko starty, 20 meczów, szeroka próbka od 5 | `samples.py:1354`, `:1436` | 90 / 61 / 47 par `NO_ENTITY_FOUND` piłki 10-23 |
| progi nazw zawodników | `players.py:470`, `:514` | ~20 wariantów w piłce 10-23 |
| gole tylko z tych samych rozgrywek | `comparability.py:205` | 261 meczów pucharowych 10-23 |
| bramka tożsamości per rodzina | `metrics.identity_gap_for_metric` | 36 meczów piłki 10-23 |
| nawierzchnia, best-of, krecz / walkower, debel | `settle.py:302-320`, `metrics.py:768` | tenis, ~50% meczów |
| `SAMPLE_CROSSES_SEASON` 180 d | `confidence.py:388` | tenis B9 |
| `HISTORY_GAMES` 60, `MIN_APPEARANCES` 5 | `player_model.py:112`, `:114` | Kochetkov, Varlamov, Zach Edey |
| homonimy w jednym składzie | `player_model.py:510` | dwóch Eliasów Petterssonów; etykieta `NOT_IN_HISTORY` źle nazywa przyczynę |
| `MIN_TEAM_MATCHES` 5, `MIN_LEAGUE_MATCHES` 30 | `football_rating.py:172-173`, `score_model.py:763-789` | nowe drużyny kosza / siatkówki |
| `TOURNAMENT_NEVER_SETTLED` | `sport_day.py:28-33`, `:114-125` | czyta **nasze** rozliczone linie (`settled.json`) po nazwie turnieju Superbetu, nie historię Sofascore; SRB / NED 10-23 to pierwszy dzień nowego turnieju |
| `RESOLVED_ID_DISAGREES` | `sport_identity.py:597`, `:713` | AEK Larnaca - Tartu: Superbet „Tartu Ulikool/Estiko” trafił w drużynę rezerw 933088; alias w `config/sofa_entity_aliases.json` by to odzyskał |
| `LOOKBACK_DAYS` 365 CS2 | `cs2_engine.py:74` | mapy starsze niż rok |

## 6. Noc 10-22/23: sprostowania

Raport nocy, sekcja 2, kontra log i baza:

| twierdzenie | stan |
|---|---|
| hokej 2 009 (1 337 ze statystykami) | zgadza się (2 009 to cele, 2 005 odpytanych); „+ składy” nie: hokej dostał 0 składów (log), 3 w bazie |
| siatkówka 1 020 | to liczba celów; 289 pominięte jako jałowe, 731 odpytanych, 217 ze statystykami |
| kosz 1 116 (1 011) | zgadza się (+3 z drugiego chunka) |
| piłka 576 | zgadza się, ale ze statystykami tylko 162 |
| tenis 0 celów, 208 jałowych | 0 zgadza się, ale nie przez regułę jałowych: tenis odpytano w całości o 21:36Z (3 928 celów, 2 842 ze statystykami, `backfill_2026-10-22.log:123`); 208 nie ma w żadnym logu i liczy wszystkie sporty (tenisowych jest 174) |
| kolejka do 3. przeskoku 1 / 24 / 7 / 2 / 740 | **błędny odczyt:** driver ogłaszał limit dopiero po chunku, który już ten przeskok przeszedł; prawdziwa kolejka teraz: hokej 4, siatkówka 2, kosz 29, tenis 28, piłka 1 611 (poprawione, sekcja 8) |
| luka seeda: hokej 77, siatkówka 151, piłka 2 598 | zgadza się z pierwszym chunkiem (piłka 2 584); lukę tenisa (1 739) zamknął wcześniejszy driver (21:05-21:27Z), nie nocne etapy |
| hardening #15 | potwierdzone: `also_target` to metadane, których nikt nie czyta; instalator (`install_new_market_curves.py:378`) pisał tylko do pliku zainstalowanego i `.next.json`; poprawione |

Inne dziury w `backfill_listings.py` po c72d4885 / 34dcad47:
1. Sporty mierzone nie mają boardu: `board_entities()` czyta tylko
   `02_fixtures.json`, więc „na boardzie 0” dla hokeja i siatkówki wynika z
   konstrukcji, a nie z pomiaru.
2. Encja, której żadna strona nie wymienia, nigdy nie trafia do kolejki.
3. 317 encji ma stałe chybienie strony 0. Wracają do kolejki w każdym
   przebiegu i nikt ich nie pyta ponownie.
4. Kolejka z założenia nigdy się nie opróżnia.
5. Nieświeżej strony 0 skrypt nie odświeża. Encje boardu z najnowszym meczem
   starszym niż 21 dni: tenis 40, siatkówka 15, piłka 13, kosz 7. Piłka
   odświeża stronę 0 w SAMPLES (każda próbkowana drużyna ma stronę młodszą
   niż dzień); dla tenisa i kosza niesprawdzone.
6. CS2 nie ma trasy listingów.

`report_entity_queue.py` nie jest tylko do odczytu: zapisuje
`runs/sofa/<d>/entity_queue.md` (`report_entity_queue.py:128-131`). Agent CS2
utworzył ten plik w katalogu 10-23. Usunięty (kopia w scratchpadzie), plik
jest w gitignore i nic go nie czyta.

## 7. Plan (faza 2) - czeka na decyzję operatora

Wszystko poniżej **zmienia druk**, więc wymaga przełącznika w
`bet.sofa.epochs` od następnego dnia 00:00Z i zgody operatora. Kolejność:
szacowany zysk w nogach i podmiotach.

| # | poprawka | plik / funkcja | test regresji (pada przed, przechodzi po) | przełącznik | SHEET / SHADOW / refit |
|---|---|---|---|---|---|
| P1 | `ENTITY_CONFLICT` tnie próbkę przy starciu zamiast ją opróżniać + 2 turnieje towarzyskie na listę | `samples.py:671-685`; `config/sofa_friendly_competitions.json` | fixture z dawnym starciem dostaje próbkę sprzed niego; ut 38292 / 38659 są towarzyskie | `SAMPLE_CONFLICT_CUT_FROM_UTC` | SAMPLES + SHEET dla dotkniętych fixtures (rebuild_plan 1c); bez refitu (krzywe czytają replay, który nie zna tego starcia) - **najpierw pomiar**: ile fixtures, czy próbka po cięciu ma >= 10 meczów |
| P2 | CS2 (i każdy sport) ponownie pyta świeżą stronę przy chybieniu z cache blisko startu i pyta drugą drużynę | `sport_identity.identify_event` `:789-823` | chybienie z cache + świeża strona z meczem = IDENTIFIED | `IDENTITY_FRESH_RECHECK_ALL_FROM_UTC` | nic; koszt 1-2 zapytania na chybienie |
| P3 | K7: historia zawodnika z innych drużyn (kosz / hokej po id gracza z indeksu składów; piłka po id) | `player_model.load_appearances`; `samples._player_observations` | LaMelo / Naz Reid / Lyubushkin mają n >= 5 | `PLAYER_HISTORY_ANY_TEAM_FROM_UTC` | **najpierw pomiar** (`measure_player_props.py` wariant any-team, poza próbą): hokej zmienia `p` 11 z 43 nóg; stałe `fit_player_model.py` dopasowane na starym czytelniku, więc prawdopodobnie refit |
| P4 | siatkówka: kotwica „query-only” z jednym meczem o dokładnej godzinie i słabą zgodą przeciwnika (jak `FOOTBALL_SEARCHED_ANCHOR`) | `sport_identity.match_shadow` `:520-614` | Maribor - Lublana IDENTIFIED; mecz z dwoma kandydatami odmawia | `SPORT_QUERY_ANCHOR_FROM_UTC` | nic; **najpierw backtest** na zmostkowanych meczach z ukrytym id (jak K8) |
| P5 | piłka: slug jako druga nazwa zawodnika | `players.squad_statistics` `:400` | „Julian Chabot” -> 863271 | `PLAYER_SLUG_NAME_FROM_UTC` | SAMPLES + SHEET; test fałszywych trafień na historii |
| P6 | piłka: zero spalonych zawodników z odtworzonego 0-0 drużyny | `players.team_totals` `:290` | mecz bez `offsides` -> zera zawodników w próbce | `PLAYER_OMITTED_ZERO_FROM_UTC` | SAMPLES + SHEET; krzywa `player_offsides_for` dopasowana tym samym czytelnikiem - refit tej rodziny |
| P7 | CS2: rating składu bez bramki id drużyny | `cs2_engine.RatingModel.home_logit` `:356` | Envy (9 map) - FaZe ma `p` | `CS2_LINEUP_ELO_UNRATED_FROM_UTC` | **najpierw pomiar** walk-forward |
| P8 | drobne nazwy: CS2 „prospect”, nick po prefiksie w silniku, transliteracja w hokeju (ue -> ü, Yegor / Egor) | `cs2.py:680`, `cs2_engine.player_id`, `player_model.names_agree` | przypadki z sekcji 3 | jeden przełącznik `NAME_RULES_1023_FROM_UTC` | nic |
| P9 | hokej / kosz: przynależność meczu do listy obu drużyn | `sport_history.candidates` / `store_event` | Vancouver @ Florida 16546356 w listach obu | `PLAYER_BOTH_SIDES_LISTED_FROM_UTC` (albo naprawa danych backfillem) | SHADOW przelicza się sam |
| P11 | kosz: model wyniku dla lig z połowami (NCAA) | `score_model.parse_event` `:424` (regulation_periods per liga / format) | mecz NCAA 2 połowy -> parsowany | `BB_HALVES_LEAGUES_FROM_UTC` | **najpierw**: czy Superbet oferuje NCAA (start ~11-03); krzywa kosza dopasowana bez NCAA |
| P12 | CS2: `model_p` dla serii rozliczonych z samego wyniku | `settle_cs2.py:334-362` | seria bez map ma `model_p` | `CS2_SERIES_ONLY_MODEL_P_FROM_UTC` | przelicza line evidence (+392 linie) |
| P13 | siatkówka: AET / AGS (złoty set) | `shadow.py:132`, `:1574` | mecz AGS parsowany / rozliczony | rozliczenie = poprawka poprawności (na żywo, z testem) po ustaleniu, jak Superbet liczy złoty set; model - przełącznik | - |
| P14 | tenis: rating - zwycięzca z wyniku w setach, typ gracza 0 | `tennis_rating.py:221`, `:233` | 17362029 wchodzi do ratingu | `TENNIS_RATING_SCORE_WINNER_FROM_UTC` | rating przelicza się sam; krzywe na replayu - refit przy następnym |
| P10 | siatkówka: Katar 2345 -> 39366 | **zamknięte bez zmiany**: sezonu 25/26 nie ma u źródła (most), stara stawka ma 22 miesiące; `NO_LEAGUE_RATE` do 30 meczów 39366 jest właściwe | - | - | - |

## 8. Co zrobiono od razu (nie zmienia druku)

| commit | co | test |
|---|---|---|
| instalator krzywych | `install_new_market_curves.target_files`: cel sportowy scala do pliku zainstalowanego, `.next.json` i każdego pliku z datą; konflikt w którymkolwiek odmawia | `test_install_new_market_curves.py::test_every_dated_staged_sport_file_is_merged_too`, `::test_a_conflict_in_a_dated_staged_file_refuses` (padały przed) |
| driver backfillu | przy osiągniętym limicie przeskoków driver czyta plan `--dry-run` przed chunkiem i kończy etap bez chodzenia po nowym przeskoku; log „N at the next hop, not walked” to prawdziwa kolejka | `test_backfill_driver.py::test_the_hop_past_the_limit_is_planned_not_walked`, `::test_hop_limit_reached_only_on_a_new_seed_past_the_limit` (padały przed); dry-run na żywo: hokej 4 encje, `listings_seed.json` md5 bez zmian |
| reguła jałowych rozgrywek | liczona w obrębie sportu (`barren_competitions(..., sport=)`), tenis wyłączony (`BARREN_EXEMPT_SPORTS`) | `test_backfill_barren_per_sport.py` (padał przed) |

| backfill incydentów piłki | `backfill_event_stats.py --incidents-only`: `/incidents` dla wierszy piłki ze statystykami i bez incydentów (`incidents_only_targets`); zapisane statystyki nietknięte (`save_event_stats` COALESCE) | `test_backfill_incidents_only.py` (2 testy padały przed; trzeci pilnuje COALESCE) |

Backfill po poprawce (2026-10-23 ~10:00Z):
`backfill_event_stats.py --sport tennis --days 365 --max-minutes 6`
- 467 celów (dawniej pomijane ITF + mecze zakończone od nocy), 0 pominiętych;
- 92 ze statystykami, 375 bez, 0 błędów, bez otwarcia breakera.

Zasila tylko historię refitów asów / podwójnych / serwisu; druku nie
zmienia.

## 9. Liczby odtworzone lokalnie przez główną sesję

- **kosz:**
  - 269 napisów / 212 z `p` / 53 THIN / 4 NOT_IN_HISTORY (`player_model.jsonl`
    10-23, ostatni wiersz na (subject, family));
  - LaMelo: `model_n` 1, przypięcie (3437, 3426), 59 z 60 meczów Charlotte
    w liście z nim, `load_appearances([3423, 3430])` daje 58;
  - Naz Reid: `model_n` 1, w bazie 94 mecze Minnesoty z jego nazwiskiem w
    składzie.
- **hokej:** Lyubushkin 10-22 `model_n` 0 NOT_IN_HISTORY, nazwisko w 156
  składach.
- **siatkówka:** Katar: 104 mecze pod 2345 (do 2024-12-24), 3 pod 39366.
- **CS2:** świeże zapytanie odpala się tylko przy `NO_GAME_WITHIN_1H`
  (`sport_identity.py:815`).
- **tenis:** `backfill_2026-10-22.log:123`: 3 928 celów, 2 842 ze
  statystykami, `skipped_barren` 0; `barren_competitions` bez filtra sportu.
- **piłka:** 51 składów z `slug: "julian-chabot"` i `name: "Jeff Chabot"`;
  klucz składu = sama nazwa (`players.py:400`).
- **noc:** `judge_chunk` ogłaszał `DONE_HOPS` dopiero po chunku z nowym seedem
  (`backfill_driver.py`, przed poprawką `:199-204`).

## 10. Faza 4 - weryfikacja

Pomiary przed / po dla poprawek P1-P10 czekają na decyzję operatora: żadna
nie jest wdrożona. Poprawki z sekcji 8 nie zmieniają druku. Ich weryfikacja
to testy regresji i bramki (sekcja 12).

### Hokej od 10-24 (nowa krzywa)

Powtórka SPORT_CONFIDENCE hokeja offline, na kopiach wejść, na zegarze
budowy każdego dnia: stara krzywa (`.next.json`) kontra nowa
(`.next.2026-10-24.json`).

Odtworzenie prawdziwych dni starą krzywą:
- **10-23:** dokładnie, 513 z 513 nóg z tymi samymi kluczami i confidence
  (sprawdzone lokalnie: plik ma 513 nóg hokeja);
- **10-22:** 195 vs 197;
- **10-21:** 246 vs 247.

Rozjazd 10-21 / 10-22 to stan bazy, nie kod. Model wyniku czyta każdy mecz
z przeszłości bez względu na to, kiedy go pobrano, a nocny backfill dopisał
mecze sprzed tych zegarów budowy. Dlatego „przed / po” na zbudowanych dniach
porównuje dwie powtórki na tej samej bazie, a nie powtórkę z prawdziwym
plikiem.

| dzień | stara: drukuje (>= 0,70) | nowa, line evidence dnia | nowa, line evidence przeliczone na nowej krzywej | handicap stara -> A / B |
|---|---|---|---|---|
| 10-21 | 246 (363) | 216 (+5 / -35) | 232 (+8 / -22) | 5 -> 5 / 5 |
| 10-22 | 195 (306) | 186 (+2 / -11) | 187 (+3 / -11) | 9 -> 8 / 7 |
| 10-23 | 513 (889) | 477 (+18 / -54) | 518 (+29 / -24) | 32 -> 33 / 31 |

- **Sama krzywa** rusza confidence wspólnych nóg średnio o 0,008-0,009:
  sumy i sumy tercji w dół o ~0,005, sumy drużyn w górę o ~0,004.
- **`handicap`** (jedyna rodzina zmierzona jako gorsza): ±1 noga dziennie,
  średni ruch < 0,004.
- **Huśtawkę liczby nóg robi line evidence.** Kary dopasowane do starej
  krzywej na nowej są mniejsze (total OVER -0,025 -> -0,012, winner -0,059 ->
  -0,001). Poranny `refresh_line_evidence.py --before 2026-10-24` dopasuje je
  do nowej krzywej, więc 10-24 będzie wyglądał jak ostatnia kolumna, plus
  rozliczone linie 10-23, których powtórka nie zna.
- **Nie sprawdzono**, jak rozliczyły się zyskane i stracone nogi.
- md5 sześciu prawdziwych plików bez zmian.

## 11. Czego NIE sprawdzono

- Wpływu P1-P10 na druk: nic nie jest wdrożone, a liczby z sekcji 3 to
  zasięgi, nie powtórki SHEET / CONFIDENCE.
- **K7:** kierunku zmiany `p` dla hokeja i tego, czy mecze z innej drużyny
  (inna rola, inna liga) poprawiają log-loss.
- **Tenis:** 34 niezmostkowanych wpisów RESOLVE (19 / 4 / 11) nie badano.
- **Wiarygodność „było w bazie przy budowie”:** każde ponowne pobranie
  nadpisuje `fetched_at` (`listing_index.py:126-131`). Malmö U20 (hokej
  10-21) i 5 meczów NBA (10-21) to klasa A „w chwili budowy” tylko z
  wnioskowania.
- **AHL i sezon 25/26 QVL:** czy Sofascore je ma, nie pytaliśmy przez most.
- **Nieświeże strony 0** tenisistów (39) i drużyn kosza (6) z boardu: czy
  grali od 09-30, niesprawdzone.
- **Dzień 10-24:** jego boardu jeszcze nie ma (`02_fixtures.json`), więc
  lejka dla 10-24 nie liczono.

Niesprawdzone bezpieczniki:
- **`plan_chunk` drivera** w prawdziwym przebiegu nocnym: test jednostkowy i
  jeden dry-run na żywo, bez przebiegu, który dochodzi do limitu.
- **`target_files` instalatora** na prawdziwym katalogu konfiguracji: tylko
  testy na tymczasowych plikach, bez `--dry-run` na żywej konfiguracji (nie
  ma grupy do instalacji).
- **6 encji kosza / siatkówki bez żadnej strony listy:**
  `backfill_listings.py` nie umie wycelować w encję (brak opcji). Dziś bez
  wpływu, bo model wyniku czyta indeks. Zostaje jako pozycja narzędziowa.

## 12. Bramki

Na drzewie z czterema poprawkami narzędzi (bce8a1ae, a3bee5f4, 4096c4a4,
623ce28b):
- pytest `tests/sofa`: 5759 passed / 2 skipped;
- ruff czysty;
- mypy `--strict --no-incremental`: czysty (338 plików);
- `check_test_registry.py`: 25 testów, 0 uwag.

md5 prawdziwych `11_coupon.json` / `KUPON_*.pdf` / `08_confidence_sports.json`
10-21..10-23 zapisano przed pracą
(`scratchpad/audit/md5_before.txt`). Nic w tej sesji ich nie zapisuje.
Dzień 10-23 może się zmienić z innych powodów: czytania analityków,
wieczornego rebuildu operatora.

## 13. Backfill incydentów piłki - stan

`backfill_event_stats.py --incidents-only --days 365`: 20 094 celów.

| przebieg | wynik |
|---|---|
| 1. chunk | breaker otwarty po 22 meczach (3 błędy); most potem zdrowy (112 ms) |
| 2. chunk (4 min) | 3 312 meczów, 3 bez incydentów (404), 0 błędów |
| reszta | `backfill_driver.py --plan <scratch>/incidents_plan.json --log runs/sofa/backfill/incidents_2026-10-23.log --yield-to-build` (w tle) |

- Wiersz z 404 zostaje NULL i wraca jako cel. Driver kończy etap po 3
  chunkach bez postępu, więc to nie zapętla.
- Wpływ: rekord sędziego (`FOOTBALL_REFEREE`) i każdy czytelnik kartek z
  incydentów widzą więcej meczów od następnego buildu. To dane, nie zmiana
  reguły.
