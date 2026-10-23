# Zadanie: audyt pokrycia danych → plan → poprawki → weryfikacja (wszystkie sporty)

## Dlaczego
Noc 10-22/23 (`docs/sofa/history/NOC_2026-10-22_23.md`) miała dociągnąć
statystyki każdej drużyny i każdego zawodnika we wszystkich sportach, a potem
poprawić modele. Raport mówi „backfill skończony”. W praktyce nikt nie sprawdził,
czy modele **czytają** to, co leży w bazie. Pierwsze sprawdzenie na dniu
2026-10-23 pokazało, że nie:

- **NBA, zawodnicy:** 57 z 269 zawodników z oferty nie ma `p`
  (53 `THIN_SAMPLE`, 4 `NOT_IN_HISTORY`;
  `runs/sofa/shadow/basketball/2026-10-23/player_model.jsonl`, ostatni wiersz
  na (subject, family)). LaMelo Ball (id 1092868) ma `model_n: 1`, a jego id
  jest w `sofa_event_stats.lineups_json` **85 meczów NBA**
  (2025-10-22..2026-10-21). Wszystkie 1 335 meczów NBA od 10-2025 mają składy,
  a Charlotte ma 210 meczów w `sofa_listing_event`. Dane są, model ich nie
  widzi. Skutek: ok. 1 600 linii NBA `NO_MODEL_P` w
  `runs/sofa/2026-10-23/08_refusals_sports.json`.
- **NBA, `player_v2_rule`:** 0 wierszy z tym polem w `player_model.jsonl`
  10-23, choć `BASKETBALL_PLAYER_V2` działa od 10-23 00:00Z. Nie ustalono, czy
  pole ma tam być.
- **Piłka, zawodnicy:** 268 nazwisk z oferty `NO_ENTITY_FOUND` („matched no
  squad member” / „never started”); 215 z 833 zawodników ma 1–4 starty. Nie
  wiadomo, ile to rzeczywistość, a ile dziura w składach albo w dopasowaniu.
- **Piłka, drużyny:** 7 z 331 meczów ma próbkę < 5 (3 z nich to celowe
  `ENTITY_CONFLICT`). 86 meczów ma `THIN_SAMPLE`, prawie wyłącznie na
  `corners_1h_total`. Do tego 55 `INTERNAL_INCONSISTENT`, 55 `STAT_KEY_ABSENT`
  i 121 meczów z `NO_STATISTICS` na jakiejś metryce.
- **Tenis:** nocny backfill statystyk dał **0 celów**, bo 208 rozgrywek
  odrzucono jako „jałowe” (`MAX_BARREN_MISSES`, pierwsze 25 meczów zwróciło
  404, `backfill_event_stats.py`). Nikt nie sprawdził, czy te 404 są prawdziwe
  (np. ręcznie przez most dla 3 rozgrywek). Zostały `NO_STATISTICS` przy asach.
  10 meczów ma próbkę < 5.
- **Siatkówka / CS2:** 6 meczów CS2 i 3 siatkówki `NOT_IDENTIFIED`;
  7 meczów siatkówki `TOURNAMENT_NEVER_SETTLED` (Bułgaria SuperLiga, Holandia
  Eredivisie, Serbia Superliga), 1 `NO_LEAGUE_RATE` (Katar QVL). Nie wiadomo,
  czy historia tych lig jest w bazie i czy nie trafia do modelu.
- **Hokej:** ten sam `player_model.py` co NBA, nikt nie sprawdził pokrycia
  zawodników NHL. Krzywa hokeja przeliczona w nocy wchodzi od 10-24, a pełnej
  przebudowy dnia z nią nikt nie zrobił.

Liczby wyżej policzono jednym przebiegiem na plikach 10-23. **Najpierw je
odtwórz.** Nie ufaj ani im, ani nocnemu raportowi.

Hipoteza robocza do potwierdzenia albo obalenia: ta sama klasa błędu
(**dane w bazie są, czytelnik ich nie widzi**: inny klucz, inny indeks, filtr,
dopasowanie nazwy / id, kursor lub seed, limit okna, wykluczenie przedsezonu,
dwa źródła tego samego, tj. `sofa_entity_events` vs `sofa_listed_event` /
`sofa_listing_event`) siedzi w więcej niż jednym sporcie.

## Zasady (CLAUDE.md obowiązuje w całości; tu tylko przypomnienie)
- Najpierw przeczytaj `.claude/skills/sofa-pipeline/references/model-state.md`.
- Dowód albo nie było: każde twierdzenie z plikiem i linią albo artefaktem i
  polem. Rzecz niezmierzona to podejrzenie i tak ją nazywasz.
- Liczby od subagentów sprawdzasz lokalnie, zanim trafią do raportu.
- Nie wolno: refitów ani instalacji krzywych bez mojej zgody, push bez mojej
  prośby, `git stash`, zmian w wydrukowanych nogach 10-23 i wcześniejszych.
- Poprawka poprawności (dane są, a czytelnik ich nie czyta) wchodzi z testem.
  **Jeśli zmienia to, co się drukuje, dostaje przełącznik w `bet.sofa.epochs`
  od następnego dnia 00:00Z.** Wcześniej tylko na moje słowo. Dla każdej
  poprawki napisz wprost, czy zmienia druk.
- Brak danych naprawia backfill (`scripts/sofa/backfill_driver.py`, krótkie
  przebiegi z wznowieniem; `MIN_INTERVAL_MS` nietykalne), nie wymówka.
- Duże JSON-y czytaj przez `jq` / Pythona, nigdy `cat`.

## Faza 1: Audyt (bez zmian w kodzie)

Dla **każdego sportu** (piłka, tenis, hokej, kosz, siatkówka, CS2) i
**każdego czytelnika historii**:

| sport | czytelnicy do sprawdzenia |
|---|---|
| piłka | SAMPLES drużyn (każda metryka), zawodnicy (`players.match_player`, starty, składy), sędziowie (`bet.sofa.referees`), h2h, dossier |
| tenis | SAMPLES graczy (gemy, sety, asy, podwójne błędy, serwis), identyfikacja, statystyki meczu |
| hokej / kosz | `score_model.load_history` / `load_events` / `load_box_scores`, `player_model.load_appearances` / `own_sample` / `find_player`, SPORT_IDENTITY, `sport_history` |
| siatkówka | score model, stawka ligi (`NO_LEAGUE_RATE`, `TOURNAMENT_NEVER_SETTLED`), identyfikacja |
| CS2 | engine map / serii, gracze (kills / deaths / assists / HS), identyfikacja |

Dla każdej pary (sport, czytelnik):

1. **Lejek dla ofert z 10-23** (i co najmniej 2 wcześniejszych dni, np. 10-21,
   10-22): ile podmiotów (drużyn / zawodników) jest na boardzie → ile ma
   encję → ile meczów leży w bazie (każde źródło osobno) → ile meczów widzi
   czytelnik → ile wchodzi do próbki → ile dostało `p` / confidence. Spadek
   na każdym kroku ma mieć nazwany powód.
2. **Każdy spadek przypisz do jednej z trzech klas:**
   - (A) danych brak w bazie, czyli backfill;
   - (B) dane są, czytelnik ich nie widzi, czyli **defekt**;
   - (C) celowe wykluczenie z nazwaną regułą (np. `ENTITY_CONFLICT`,
     przedsezon, `SAMPLE_CROSSES_SEASON`), z plikiem i linią reguły.
3. **Dla każdej klasy B weź jeden konkretny przykład** (jak LaMelo: id,
   liczba meczów w bazie vs `model_n`) i prześledź go w kodzie do przyczyny.
   Potem policz, ilu podmiotów dotyczy ta sama przyczyna.
4. **Sprawdź samą noc:**
   - 404 tenisa (próbka rozgrywek przez most);
   - 740 drużyn piłki w kolejce trzeciego przeskoku;
   - czy `backfill_listings` po poprawkach `c72d4885` / `34dcad47` nie zostawia
     innych dziur;
   - czy liczby z sekcji 2 raportu nocy zgadzają się z bazą;
   - hardening #15 (`fit_sport_derived.py` / `fit_cs2_series_rounds.py`
     piszą do `.next.json`, którego 10-24+ nie czyta).

Pracę rozdziel na subagentów, jeden na sport, równolegle. Każdy zwraca tabelę
lejka, listę defektów klasy B z przykładem i przyczyną oraz polecenia, którymi
to policzył. Główna sesja odtwarza lokalnie co najmniej po jednej liczbie na
sport.

**Wynik fazy 1:** `docs/sofa/history/AUDYT_POKRYCIA_2026-10-23.md` (po
polsku): lejek na sport, defekty z przykładem, przyczyną, zasięgiem i tym, czy
zmienia druk; braki danych z planem backfillu; wykluczenia celowe.

## Faza 2: Plan
- Lista poprawek uszeregowana według liczby nóg / podmiotów, które odzyskują.
- Dla każdej: plik i funkcja, test regresji (najpierw ma paść, po poprawce
  przejść), czy zmienia druk (wtedy nazwa przełącznika i od kiedy), czy
  wymaga ponownego SHEET / SHADOW / refitu.
- Backfill: co, ile celów, ile czasu mostu.
- **Plan pokaż mi przed wdrożeniem wszystkiego, co zmienia druk albo wymaga
  refitu.** Poprawki, które nie zmieniają druku (narzędzia, raporty, backfill),
  rób od razu.

## Faza 3: Wdrożenie
- Jedna poprawka = jeden commit z testem w `tests/sofa/` (offline, szybki) i
  wpisem w rejestrze testów.
- Bramki przed każdym commitem: pytest `tests/sofa`, ruff, mypy `--strict
  --no-incremental`, `check_test_registry.py`.
- Zaktualizuj CLAUDE.md (sekcja, nie changelog), model-state.md i polski doc
  w `docs/sofa/`.

## Faza 4: Weryfikacja (bez niej zadanie nie jest skończone)
1. **Przed / po na prawdziwych dniach** (10-21, 10-22, 10-23): powtórz lejek
   z fazy 1 na kodzie po poprawce, w katalogu scratch (sprawdź md5 prawdziwych
   `11_coupon.json` / `KUPON_*.pdf` przed i po; scratch rebuild już raz nadpisał
   prawdziwy kupon). Na sport podaj: podmioty z `p` przed → po, odmowy według
   powodu przed → po, nogi ≥ 0,70 przed → po.
2. **LaMelo i każdy przykład z fazy 1** po poprawce mają poprawny `model_n` /
   próbkę. Sprawdzasz wprost, nie przez agregat.
3. **Brak regresji:** wydrukowane nogi zbudowanych dni bez zmian; dni sprzed
   przełącznika czytają to samo co przedtem.
4. **Hokej od 10-24:** dry-run `rebuild_day.py` na scratch z nową krzywą:
   liczba nóg ≥ 0,70 i rozkład rodzin, osobno `handicap`.
5. **Niezależny weryfikator** (`sofa-verifier` albo świeży subagent) dostaje
   raport i ma znaleźć dziurę, której audyt nie złapał, w każdym sporcie.
6. Każdy niesprawdzony bezpiecznik nazwij w raporcie po imieniu.

## Co mam dostać na koniec
- `AUDYT_POKRYCIA_2026-10-23.md` z lejkami, defektami, wynikami przed / po i
  listą tego, czego **nie** sprawdzono.
- Commity na `main` (bez push), bramki zielone (podaj wynik).
- Krótkie podsumowanie w czacie: co naprawione, ile nóg / zawodników
  odzyskano na sport, co czeka na moją decyzję (przełączniki, refity,
  backfill).
