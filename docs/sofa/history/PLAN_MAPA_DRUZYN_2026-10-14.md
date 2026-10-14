# Plan: mapa drużyn i zawodników (Superbet → Sofascore) — 2026-10-14

Stan na 2026-10-14 ~09:10Z. Dla nowej sesji, która ma to wdrożyć. Nic z tego nie jest
jeszcze w kodzie; dzisiejszy kupon zbudowano na starych regułach.

## 1. Cel i jego uczciwa granica

Operator: „żeby nigdy nie wystąpiła sytuacja, że drużyna/zawodnik nie zostaną dopasowani”.

**Dopasowania 100% zrobić się nie da.** Część meczów z oferty Superbetu w ogóle nie istnieje
w Sofascore — sprawdzone na żywo (pkt 3c): Oman – Bahrajn (siatkówka, Arab Championship),
Radnicki – Napredak i ZOK UB – Zlatibor (Puchar Serbii kobiet). Żaden endpoint tego nie
naprawi, a zgadywanie meczu byłoby błędem gorszym niż brak.

**Cel wykonalny:** każde zdarzenie kończy w stanie *wyjaśnionym*:

- `IDENTIFIED` (z metodą i dowodem), albo
- `NOT_ON_SOFASCORE` — **udowodniony** brak: listing obu znanych drużyn i listing dnia
  turnieju nie mają meczu, albo
- `NEEDS_ALIAS` — nazwa, której automat nie rozstrzyga; trafia do kolejki z kandydatami
  (id + nazwa + mecz) do jednorazowej decyzji człowieka, po której już zawsze się dopasuje.

Dziś wszystkie trzy giną w jednym worku `NOT_IDENTIFIED` (`NO_GAME_WITHIN_1H`,
`NO_MATCH_IN_LISTING`, `TEAM_UNRESOLVED`) i nic się z nich nie uczy.

## Zakres: wszystko (operator, 2026-10-14)

Każdy sport (piłka, tenis, hokej, kosz, siatka, CS2), każda encja: drużyny, zawodnicy
tenisa (to „drużyny” RESOLVE), zawodnicy w rynkach graczy (piłka, hokej, kosz, CS2),
turnieje. **Zmierzone w tej notatce:** drużyny czterech sportów z SPORT_IDENTITY i
zawodnicy piłkarscy z SAMPLES (jeden dzień). **Jeszcze niezmierzone** (K0 robi to
najpierw): piłka/tenis RESOLVE (`NO_MATCHING_EVENT`, `AMBIGUOUS_ENTITY`) na wszystkich
dniach, zawodnicy hokeja/kosza (`player_model`), gracze CS2 (rynki kills/deaths…),
zawodnicy piłkarscy na wszystkich dniach. Żaden sport ani typ encji nie wypada z planu.

## 2. Stan dziś (pomiar, 10 dni 2026-10-05..10-14)

Skrypt: `docs/sofa/evidence/identity_coverage_2026-10-14/measure_team_ids.py`
(tylko odczyt bazy; uruchomiony ponownie 2026-10-14 ~09:05Z z tego miejsca, wynik
`out.txt` w tym samym katalogu; liczby urosły względem ~07:50Z tylko o zdarzenia dopisane
w międzyczasie). Zdarzenia odduplikowane po `superbet_event_id`, sporty osobno, CS2 bez
pętli 1x1 i `DUPLICATE_SUPERBET_TEAM`. Rozwiązywanie nazw prawdziwym
`sport_identity.TeamResolver` na stanie bazy z dziś.

| | hokej | kosz | siatka | CS2 |
|---|---|---|---|---|
| zdarzenia NOT_IDENTIFIED / wszystkie | 63 / 676 | 156 / 1021 | 326 / 545 | 80 / 336 |
| `NO_GAME_WITHIN_1H` | 31 | 89 | 121 | 0 |
| `BRIDGE_ABORTED` | 25 | 36 | 74 | 32 |
| `TEAM_UNRESOLVED` | 5 | 20 | 127 | 7 |
| `NO_MATCH_IN_LISTING` (+CS2 `START_GAP_OVER_1H`) | 2 | 11 | 4 | 40 |
| nazwy Superbetu bez id dziś / wszystkie | 107 / 614 | 410 / 1255 | 483 / 839 | 26 / 241 |
| …do nauczenia z już przypiętych meczów | 81 | 326 | 116 | 13 |
| konflikty (nazwa → 2 różne id) | 0 | 0 | 0 | 0 |

- `sofa_entity` (verified) ma dziś: piłka 6 074, tenis 2 685, kosz 612, hokej 443,
  siatka 264, CS2 247. Piszą do niej tylko RESOLVE (piłka/tenis, `resolve.py:1046`) i
  `backfill_cs2.py`. **SPORT_IDENTITY otwiera bazę tylko do odczytu i niczego nie zapamiętuje.**
- Samo uczenie aliasów z przypiętych meczów odzyskuje mało zdarzeń (górna granica
  kosz ~5/dzień, siatka ~3, CS2 ~1, hokej ~0.6), bo większość braków to nie nazwa,
  tylko brak meczu w listingu jednej drużyny albo przerwany mostek.
- Reguła skrótów: potwierdzone 2 przypadki (THY = Türk Hava Yolları 243989,
  ASA = Alliance Sport Alsace 393004). Mało — ale dochodzi za darmo z planu poniżej.

**Zawodnicy piłkarscy (SAMPLES, 2026-10-14):** 210 różnych zawodników `NO_ENTITY_FOUND`:
121 „named in N squads, never started” (próba to same starty — to nie jest błąd nazwy),
89 „matched no squad member” (np. Jakub Moder, „Castellanos, Taty”, „Alvarez, Edson”,
„Benjamin Anthony Brereton Díaz”, „Pablo”, „Esquerdinha”).

**Piłka / tenis RESOLVE (2026-10-14):** 36 `NO_MATCHING_EVENT`, 1 `AMBIGUOUS_ENTITY`
na 676 — tego dziś nie rozbierałem (otwarte, krok K8).

## 3. Co zbadałem na żywo przez mostek (2026-10-14 ~08:54–09:00Z, ~40 zapytań, 0 odmów)

Surowe odpowiedzi: `docs/sofa/evidence/identity_coverage_2026-10-14/probe/*.json`,
skrypt `probe_endpoints.py` (tryby `scheduled|search|team|players|extra`).

### a) Endpointy

| endpoint | wynik | uwagi |
|---|---|---|
| `sport/{s}/scheduled-events/{d}` | **404** (każdy sport, też piłka) | stara trasa — nie istnieje |
| `sport/{s}/events/{d}` | 404 | |
| `sport/{s}/scheduled-tournaments/{d}/page/{n}` | **200** | turnieje z meczami w dniu; kosz: 100 + 26 (2 strony), hokej 35, siatka 22 |
| `unique-tournament/{ut}/scheduled-events/{d}` | **200** | **wszystkie mecze turnieju w dniu**, z id drużyn i startem |
| `sport/{s}/{d}/7200/categories` | 200 | kategorie (kraje) dnia |
| `team/{id}/events/next/{p}` | 200 / 404 | dziś używane; 404 = brak przyszłych meczów; strona 1 zwykle 404 |
| `team/{id}/events/last/{p}` | 200 | |
| `team/{id}/players` | **200** | aktualny skład z id zawodników (także nowi) |
| `search/all?q=..&sport=..` | 200 | pełne nazwy znajduje; skrótów nie; bywa wiele id (Binh Dien Long An: 5 drużyn) |
| `search/teams?q=..` | 200 | bez filtra sportu, gorsze |
| `player/{id}/events/last/{p}` | **200** | mecze zawodnika (z reprezentacją) |

### b) Mecz-first odzyskuje to, czego nazwa nie dała (przypadki z 2026-10-14)

| Superbet (powód dziś) | znalezione w Sofascore | endpoint |
|---|---|---|
| Kuzeyboru (K) – **THY (K)** 11:00 (`NO_MATCH_IN_LISTING`) | Kuzeyboru – **Türk Hava Yolları** 17220425, 11:00 | `unique-tournament/969/scheduled-events/2026-10-14` (był też w cache listingu Kuzeyboru) |
| Tryhoop Okayama – **Takamatsu** 10:05 (`NO_MATCH_IN_LISTING`) | Tryhoop Okayama – **Kagawa Five Arrows** (124602) 16491061, 10:05 | `team/337532/events/next/0` |
| **Spartak Subotica** – Hapoel Holon 18:00 | **KK Spartak Office Shoes** (174744) – Hapoel Netanel Holon 16611512 | `unique-tournament/9357/...` |
| **Liepajas Lauvas** – TTU 16:00 | **BK Liepāja** (38008) – TalTech/Alexela 17047838 | `unique-tournament/11479/...` |
| **Bilbao** – **SK Slavia Prague ERA NBK** 18:00 (`TEAM_UNRESOLVED`, obie) | Surne Bilbao Basket – SK Slavia Praha 16611519 | `unique-tournament/9357/...` |
| **Kavkasia** – Lausanne **14:00** (`NO_GAME_WITHIN_1H`) | **BC CIU** – Pully Lausanne Foxes 17117429, **16:00** | `unique-tournament/21144/...` — inna nazwa **i** 2 h różnicy startu |

Wspólny wzór: jedna strona znana po id (albo turniej znany), start w oknie, w tym oknie
dokładnie jeden mecz tej drużyny → mecz pewny, a druga nazwa staje się aliasem.
Dzisiejsza reguła `_anchored` (`sport_identity.py:405`) wymaga jeszcze zgodności nazwy
przeciwnika — i to ona odrzuca wszystkie powyższe.

### c) Czego nie da się odzyskać

- Oman (203051): `team/.../events/next/0` = 404, `last/0` kończy się na meczach AVC z 09-09.
  Bahrajn (203059) `next/0` = 404. Meczu z 10-14 w Sofascore nie ma.
- Radnicki Beograd (52459) i ŽOK Ub (298548): listing ma ligę od 10-17, meczu Pucharu
  Serbii z 10-14 brak.
- `scheduled-tournaments` siatkówki 10-14 nie ma Arab Championship ani Pucharu Serbii.
  → to są przypadki dla stanu `NOT_ON_SOFASCORE`.

### d) Wyszukiwarka i zawodnicy

- `search/all?q=Jakub Moder&sport=football` → Jakub Moder #886242 (Feyenoord);
  `player/886242/events/last/0` → 30 meczów, w tym Szwecja – Polska.
- „Brereton Diaz” → Ben Brereton Díaz #867583 (Sheffield United).
- „Taty Castellanos” → **pudło** (zwraca inną osobę) — ksywki tylko przez skład drużyny
  (`team/{id}/players`) albo alias ręczny.
- „THY” → piłka ręczna / piłkarze; skrótów wyszukiwarka nie rozwiązuje.

**Wniosek:** wyszukiwarka po nazwie nie może być źródłem dopasowania (skróty, ksywki,
duplikaty id). Źródłem jest **mecz** (dzień, turniej, start, znana strona), a nazwy
uczymy się z dopasowanego meczu. Fuzzy/wyszukiwarka tylko podpowiada kandydatów do kolejki.

## 4. Plan (kolejność ma znaczenie)

Każdy krok: pomiar przed zmianą, test w `tests/sofa/`, przełącznik w `bet.sofa.epochs`
(wszystko, co dokłada nogi na kupon, działa od następnego 00:00Z — reguła CLAUDE.md),
raport w `docs/sofa/history/`, aktualizacja CLAUDE.md i `docs/sofa/PIPELINE.md`.

**K0. Narzędzie pomiaru (tylko odczyt).** *Zrobione 2026-10-14:*
`scripts/sofa/measure_team_identity.py`, wynik i zastrzeżenia w
`docs/sofa/evidence/identity_coverage_2026-10-14/K0_pomiar_2026-10-14.md`
(test w rejestrze: `T-IDENTITY-unexplained`, PROPOSED). Plan pierwotny: Przenieść `measure_team_ids.py` do
`scripts/sofa/measure_team_identity.py` (`main()`, argparse `--from/--to/--sport`,
mypy --strict, ruff, wpis w rejestrze testów `check_test_registry.py`). Dodać tryb
dla piłki/tenisa (RESOLVE gaps) i zawodników (`NO_ENTITY_FOUND` z `03_samples.json`).
To jest miernik całego planu: liczba stanów niewyjaśnionych na dzień, per sport.

**K1. Jedna mapa encji + uczenie (najtańsze, bez mostka).** *Zrobione 2026-10-14 (odczyt od
2026-10-15 00:00Z):* `bet.sofa.entity_map`, raport
`docs/sofa/history/RAPORT_K1_MAPA_ENCJI_2026-10-14.md`. Zmiana względem planu:
strona potwierdzona tylko regułą przeciwnika nie jest uczona, tylko trafia do
kolejki kandydatów (jak `remember()` w RESOLVE). Plan pierwotny:
- `sofa_entity` jako jedyna mapa nazwa Superbetu → id Sofascore dla wszystkich sportów,
  z polem źródła (`resolve` / `identity_both_names` / `identity_anchor` / `manual`) i
  id meczu-dowodu.
- SPORT_IDENTITY po `IDENTIFIED` zapisuje obie strony (dziś: read-only — trzeba osobnego
  połączenia do zapisu albo zapisu w kroku po identyfikacji; uwaga na równoległe pętle,
  WAL + retry jak w RESOLVE).
- Jednorazowy backfill z wszystkich `runs/sofa/*/sport_fixtures.json` (~536 nazw;
  pomiar: 0 konfliktów). Konflikt (nazwa → inne id) nigdy nie nadpisuje — trafia do kolejki.
- Mapa turniejów: nazwa turnieju Superbetu → `unique_tournament_id` Sofascore, uczona
  z przypiętych meczów (`competition_id`). Potrzebna do K2/K3.

**K2. Kandydaci z listingu dnia (mecz-first, mostek).** *Zrobione 2026-10-14 (od 2026-10-15
00:00Z):* reguła `DAY_ANCHOR` dla hokeja / kosza / siatki na listingu, który
SPORT_IDENTITY już pobiera (0 dodatkowych zapytań); CS2 i tenis wyłączone;
okno 1 h; listing dnia przeniesiony do K3 / K5. Raport
`docs/sofa/history/RAPORT_K2_DAY_ANCHOR_2026-10-14.md`. Plan pierwotny:
- Raz na dzień i sport: `sport/{s}/scheduled-tournaments/{d}/page/{1..}` (do
  `hasNextPage=false`), potem `unique-tournament/{ut}/scheduled-events/{d}` dla turniejów,
  w których mamy niedopasowane zdarzenia (nie dla wszystkich). Cache jak listingi
  (`SofaCache`), pilnować dnia UTC vs strefy (sprawdzić D-1/D+1 przy meczach nocnych).
- Nowa reguła dopasowania `DAY_ANCHOR`: jedna strona znana po id, w oknie startu
  dokładnie jeden mecz tej drużyny w listingu (dnia albo drużyny), druga strona nie ma
  innego rozwiązanego id, zgodna płeć / poziom (`same_squad`) → `IDENTIFIED`, a nazwa
  drugiej strony zapisana jako alias (`identity_anchor`).
- **Okno startu** zmierzyć, nie zgadywać: Kavkasia – Lausanne miał 2 h różnicy.
  Proponowany pomiar: na przypiętych meczach rozkład |start Superbet − start Sofascore|
  per sport, i ile meczów tej samej drużyny wpada w ±1/±2/±3 h (ryzyko dwóch kandydatów).
- **Precyzja przed włączeniem:** backtest na `IDENTIFIED` z ukrytą nazwą przeciwnika —
  reguła musi trafić ten sam mecz w 100% (każdy błąd = pomyłka meczu = zła noga).
  Żaden wynik meczu nie wchodzi do decyzji.

**K3. Obie strony nieznane.** *Zrobione 2026-10-14 (od 2026-10-15 00:00Z):* `TOURNAMENT_DAY`, próg 60 / przewaga 20 zmierzone na 95 dniach turniejów (raport `RAPORT_K3_K7_TOZSAMOSC_2026-10-14.md`). Plan pierwotny: Na liście meczów jednego turnieju w jednym oknie startu:
dopasowanie nazw (fuzzy) tylko wewnątrz tej małej listy, jeden kandydat z wyraźną
przewagą → `IDENTIFIED` + dwa aliasy; inaczej `NEEDS_ALIAS` z kandydatami (Bilbao – Slavia).
Wymaga mapy turniejów z K1.

**K4. Nazwy, których nic nie połączy automatycznie.** *Zrobione 2026-10-14:* plik
`config/sofa_entity_aliases.json` + `entity_map.sync_manual` (w każdym
przebiegu SPORT_IDENTITY, od 2026-10-15 00:00Z) + raport kolejki
`report_entity_queue.py` → `runs/sofa/<d>/entity_queue.md`. Słownik państw
już istniał (`sofa_name_aliases.json`: jordania, kuwejt, arabia saudyjska,
algieria, bahrajn…); nierozpoznane reprezentacje grają turnieje, których w
Sofascore nie ma (K5). Plan pierwotny:
- Słownik polskich nazw państw (egzonimy Superbetu: „Jordania”, „Kuwejt”,
  „Arabia Saudyjska”, „Algieria”, „Bahrajn”…) → kod kraju / nazwa angielska;
  deterministyczny, w `config/`.
- Plik aliasów ręcznych `config/sofa_entity_aliases.json` (sport, nazwa Superbetu, id
  Sofascore, kto, kiedy, dowód) — wpisywany po decyzji człowieka z kolejki `NEEDS_ALIAS`.
  Kolejka = codzienny raport (md) w katalogu dnia z kandydatami z wyszukiwarki
  (`search/all` z filtrem sportu) i z listingu dnia. Fuzzy nigdy nie wpisuje sam.

**K5. `NOT_ON_SOFASCORE` jako udowodniony stan.** *Zrobione 2026-10-14 (od 2026-10-15 00:00Z):* świeże zapytanie zamiast 6-godzinnego cache + brak w ±12 h na świeżej stronie drużyny z id. Plan pierwotny: Gdy listingi znanych stron
(`next` i — po starcie — `last`) oraz listing dnia turnieju nie mają meczu w oknie →
status z dowodem (które zapytania, kiedy). Zastępuje dzisiejsze `NO_GAME_WITHIN_1H`.
Raport dzienny osobno: ile ofert Superbetu nie istnieje w Sofascore (per sport/turniej) —
to zbiór, którego nie da się grać na naszych statystykach, a nie błąd.

**K6. `BRIDGE_ABORTED` *Zmierzone 2026-10-14, bez zmiany kodu:* okresy odmowy (504 karty 10-09, 403 nocą 10-13/14), pętla ponawia co 30 min. Plan pierwotny: (25–74 zdarzeń / 10 dni na sport).** Pętle ponawiają
niezidentyfikowane przy następnym przebiegu; zmierzyć, ile z nich i tak zostało bez id
przed startem (wtedy: ponowienie po zamknięciu wyłącznika, w tym samym limicie tempa —
nigdy szybciej).

**K7. Zawodnicy.** *Piłka zrobiona 2026-10-14 (od 2026-10-15 00:00Z):* `match_player_by_surname` (1 827 / 1 827, +22 w 3 dni); hokej / kosz zmierzone (25 z 30 / 20 z 48 nazwisk w innej drużynie — decyzja modelu, niewłączone; `RAPORT_K7_K8_POMIAR_2026-10-14.md`). Plan pierwotny:
- Piłka: dla 89 „matched no squad member” — skład z `team/{id}/players` (aktualny,
  z id, z nowymi transferami) jako drugie źródło po składach z `/lineups`; dopasowanie
  po tokenach jak `match_player_by_tokens`, ale do listy z id; ksywki (Taty) przez skład
  albo alias ręczny. Potem próba zawodnika po id (`player/{id}/events/last` + lineups
  meczów) — zmierzyć koszt mostka, zanim się to włączy.
- 121 „never started” to nie problem mapowania (próba = starty, Superbet unieważnia
  zakład bez startu) — zostaje.
- Hokej / kosz: `player_model` czyta nazwiska z boxów; ten sam skład `team/{id}/players`
  może dać id. Zmierzyć dzisiejsze braki najpierw (K0).

**K8. Piłka / tenis RESOLVE.** *Zmierzone 2026-10-14, niewłączone:* kotwica piłkarska 3 458 / 3 459 z warunkiem orientacji (+~11 dziennie), jeden nierozstrzygnięty przypadek — decyzja operatora; tenis wyłączony (`RAPORT_K7_K8_POMIAR_2026-10-14.md`). Plan pierwotny: Zmierzyć 36 `NO_MATCHING_EVENT` z 10-14 (i z innych dni)
tą samą metodą mecz-first; RESOLVE już uczy `sofa_entity`, więc tu zysk to głównie
listing dnia turnieju dla nazw, których nie zna.

## 5. Koszt mostka (szacunek, do potwierdzenia pomiarem)

`scheduled-tournaments`: 1–2 strony na sport dziennie. `unique-tournament/.../scheduled-events`:
tylko turnieje z niedopasowanymi meczami — z dzisiejszych liczb rzędu 10–40 zapytań na
sport dziennie. Przy ~14 req/s to sekundy. Tempo zostaje jak jest (`MIN_INTERVAL_MS`
nietykalne, współbieżność = liczba okien); po 403 — przerwa, nie szybciej.

## 6. Ryzyka

- **Zły mecz** (reguła `DAY_ANCHOR` przy dwóch meczach drużyny blisko siebie, turnieje
  1x1 CS2) — dlatego backtest precyzji i wymóg „dokładnie jeden kandydat”.
- **Zmiany nazw sponsorskich** (KARA Trutnov = Loko Trutnov) — alias trzyma id, nie nazwę
  Sofascore; konflikt id → kolejka, nigdy nadpisanie.
- **Zmiana tras Sofascore** (`scheduled-events` zniknęło) — sonda endpointów w
  `check_bridge.py` jako INFO, żeby wiedzieć, zanim przebieg się wyłoży.
- Uczenie zmienia to, co się drukuje → przełącznik od 00:00Z następnego dnia; dni
  wcześniejsze nie są przebudowywane pod nowymi regułami.

## 7. Pliki

- ten plan: `docs/sofa/history/PLAN_MAPA_DRUZYN_2026-10-14.md`
- dowody: `docs/sofa/evidence/identity_coverage_2026-10-14/` — `measure_team_ids.py`,
  `out.txt`, `probe_endpoints.py`, `probe/*.json` (surowe odpowiedzi Sofascore)
- kod: `src/bet/sofa/sport_identity.py` (`match_shadow` ~423, `_anchored` 405,
  `next_listing` 341, `identify_event` 612), `src/bet/sofa/player_model.py:1039`
  (`resolve_team`), `src/bet/sofa/resolve.py:1046` (zapis `sofa_entity`),
  `src/bet/sofa/cache.py:500` (`save_entity`), `src/bet/sofa/client.py:359` (`search`),
  `src/bet/sofa/players.py` (`match_player`, `match_player_by_tokens`).
