# Sofascore API Reference Documentation

## Kontekst i Metodologia
Dokumentacja powstała na bazie reverse-engineeringu oficjalnego API Sofascore (v1). Wszystkie ustalenia pochodzą ze świeżych (live) requestów z 17 września 2026. Pełne logi request/response znajdują się w `docs/sofascore-api/evidence/`.

> **NIEAKTUALNE OD 2026-09-17 ok. 11:00 lokalnego.** Wszystko poniżej opisuje stan
> API sprzed edge-challenge'u, który Sofascore włączył na prefiksie `/api/v1/`.
> Od tego momentu każde zapytanie z `curl_cffi` — niezależnie od odcisku,
> nagłówków, ciastek i IP — zwraca `403 {"error":{"code":403,"reason":"challenge"}}`
> z `server: Varnish`. Mapa endpointów, kształty payloadów i pokrycie lig
> pozostają prawdziwe i użyteczne; **sekcja o rate limitingu i teza o TLS
> impersonation są obalone.** Szczegóły: sekcja "Rate Limiting" niżej.

**Wniosek techniczny (stan na 2026-09-17 rano, już nieaktualny):** API nie weryfikuje tokenów uwierzytelniających dla standardowych endpointów statystycznych czy historycznych. Wydawało się, że kluczem do bezproblemowego pobierania danych jest użycie klienta obsługującego TLS impersonation — dziś wiemy, że impersonacja przechodzi pierwszą bramkę i ginie na drugiej.

## Rate Limiting i Bezpieczeństwo
Podczas drugiej rundy audytu przeprowadzono precyzyjne testy obciążeniowe na kilkuset **różnych**, unikalnych zasobach (różne URL-e eventów, statystyk, składów), by uniknąć ryzyka zafałszowania wyników przez pamięć podręczną (Edge Cache) Cloudflare, co miało miejsce w pierwszej rundzie.

* **Wyniki testu współbieżności:** Przy uderzaniu w ~1000 różnych URL-i z użyciem 100 workerów (współbieżnych połączeń), API obsłużyło ruch z prędkością **~550 req/s** (przeliczone bezpośrednio z `evidence/rate_limit_test_log_100w.jsonl` — min/max timestamp na 1000 zapytań, spójne ze średnim `elapsed_seconds`; wcześniejsza wersja tego dokumentu podawała błędnie ~87 req/s, sprzecznie z własnym logiem). 941/1000 to 200, 56 to uzasadnione 404 (mecze w przyszłości), 3 to timeout połączenia (0.3%, nie 403/429/Cloudflare Challenge — traktuj jako szum sieciowy, nie sygnał blokady).
* **Wyniki testu ciągłego (sustained):** Przy stałym tempie 15 req/s przez 90 sekund (łącznie niemal 1300 zapytań), nie odnotowano żadnych spowolnień ani blokad. Dowód znajduje się w `evidence/rate_limit_sustained_log.jsonl`.
* **Trzy "timeouty połączenia" NIE były szumem sieciowym.** Zdanie wyżej jest
  najprawdopodobniej błędne i zostawione tu jako zapis tego, co myśleliśmy —
  z perspektywy osi czasu to pierwszy sygnał, że edge zaczyna nas odrzucać.

* **CO SIĘ STAŁO POTEM (dopisane 2026-09-18).** Powyższe testy zużyły ~2800
  żądań w 15 minut (09:55–10:30 lokalnego 2026-09-17) ze szczytem 550 req/s
  z jednego IP. Ostatni udany payload w `evidence/` ma znacznik 10:30.
  Pierwsze `403 challenge` jest o 11:49 (`evidence/impl_e1_smoke.jsonl`,
  30/30 403). Od tej pory `/api/v1/` jest zamknięte na stałe dla każdego
  klienta HTTP, jakim dysponujemy. Związek przyczynowy nie jest dowiedziony,
  ale zbieżność jest na tyle mocna, że **ten dokument należy czytać jako
  ostrzeżenie, nie jako instrukcję.**

* **Rekomendacja (zastąpiona).** Poprzednia wersja tego akapitu zalecała
  concurrency 20–50 workerów i stwierdzała, że API jest "w pełni przepuszczalne
  bez konieczności rotacji IP". Nie stosować. Obowiązująca zasada dla każdego
  reverse-engineered API bez SLA: **sekwencyjnie, ≤1 req/s, z backoffem, i nigdy
  testy przepustowości na produkcyjnym endpoincie cudzego serwisu.** Przepustowość
  zmierzona raz, kosztem utraty dostępu, nie jest wiedzą wartą swojej ceny.

* **Stan dostępu:** zablokowany. Zweryfikowane empirycznie: 18 odcisków
  `curl_cffi`, 9 publicznych implementacji z GitHuba, macierz 7 wariantów
  nagłówków, odtworzony 1:1 token `x-requested-with`, dosłowny replay
  działającego requestu z przeglądarki (ten sam `x-captcha`, ciastka, IP, okno
  ważności), Playwright headless i headed z prawdziwym Chrome — wszystko 403.
  Token `x-captcha` niesie claim `f` = odcisk *połączenia*, przeliczany przez
  serwer na żywo, więc nie da się go przenieść do innego klienta.
  Co nadal działa: `img.sofascore.com` (200, Cloudflare) i `/mobile/v4/`
  (dociera do origin, `server: nginx`). Gate jest przypięty do prefiksu
  ścieżki `/api/v1/` na warstwie Fastly.

## Pokrycie lig (Football)
Przetestowano ~12 kluczowych lig z naszego wewnętrznego mappingu. Wszystkie dają się łatwo odnaleźć i posiadają spójne `uniqueTournament.id`.

| Nazwa ligi (z naszej mapy) | Sofascore Unique Tournament Name | ID | Zgodność / Znaleziono |
| :--- | :--- | :--- | :--- |
| Premier League | Premier League | 17 | TAK |
| Ekstraklasa | Ekstraklasa | 202 | TAK |
| Super Lig | Trendyol Süper Lig | 52 | TAK |
| Liga MX | Liga MX, Apertura | 11621 | TAK (podział na Apertura/Clausura) |
| K League 1 | K League 1 | 410 | TAK |
| Superettan | Superettan | 46 | TAK |
| Champions League | UEFA Champions League | 7 | TAK |
| FA Cup | FA Cup | 19 | TAK |
| J1 League | J1 League | 196 | TAK |
| Saudi Pro League | Saudi Pro League | 955 | TAK |
| Brazil Serie B | Brasileirão Série B | 390 | TAK |
| Superliga Argentina | Liga Profesional de Fútbol | 155 | TAK (nowa nazwa to Liga Profesional) |

### Pułapki Wyszukiwania (Search Pitfalls) i Disambiguacja Ligi
Podczas wyszukiwania lig (`/search/all?q={nazwa}`), API **nie zawsze** zwraca właściwy turniej na pierwszym miejscu (`results[0]`), szczególnie przy pospolitych słowach lub lokalnych nazwach. Dowody w `evidence/league_search_disambiguation.json`:
* **Brazil Serie B:** Wyszukiwanie `brazil serie b` zwraca "Brasileirão Betano" (czyli Serie A) na pierwszym miejscu. Trzeba szukać `brasileirao serie b`.
* **Championship:** Wyszukiwanie `championship` zwraca jako top wynik "FIFA World Cup". Correct Championship (kategoria: England) jest drugie.
* **Primeira Liga:** Naiwne wyszukiwanie zwraca ligi z Chile czy Nikaragui. Należy szukać `liga portugal`.
* **Belgian Pro League:** Wyszukiwanie `belgian pro league` daje pustą listę wyników. Należy szukać `pro league`, ale wtedy top wynikiem jest "Saudi Pro League". Belgijska "Pro League" jest dopiero druga.

**Algorytm deterministycznej disambiguacji** do wdrożenia w pipeline:
Gdy szukamy ligi z pliku konfiguracyjnego `config/sportdb_competition_map.json`:
1. Pobierz `country` dla danej ligi z naszego configu.
2. Zrób zapytanie `/search/all?q={flashscore_name_or_display_name}`.
3. Przefiltruj `results` tylko dla `type == "uniqueTournament"`.
4. Wybierz obiekt, w którym wartość `entity.category.name` pasuje do `country` zapisanego w naszym configu (z uwzględnieniem mapowania np. "Europe" dla pucharów UEFA).
5. Nigdy nie polegaj ślepo na indeksie `[0]`.

## Discovery — jak znaleźć mecze (Fixtures)

**Ostrzeżenie (Czego NIE ma):** Endpointy wyszukiwania po konkretnej dacie z README starego repo (np. `/sport/football/scheduled-events/{date}`, `/sport/tennis/scheduled-tournaments/{date}/page/{page}`) **SĄ MARTWE (404)**. Ponadto `/sport/football/events/today`, `/sport/football/fixtures/{date}` itp. również zwracają 404. 

Jedyny wyjątek to `/sport/{sport}/events/live` (np. `/sport/football/events/live`), który zwraca poprawnie mecze trwające aktualnie, ze wszystkich lig na świecie. Nie pozwala on jednak na odkrywanie meczów zaplanowanych na resztę dnia.

Aby zebrać mecze na dany dzień dla konkretnych lig, należy użyć jednego z dwóch **niezawodnych algorytmów discovery**:

### Algorytm A: Przez kategorie i turnieje (Rekomendowany dla "pobierz całą ligę")
1. Pobierz ID ligi z naszego mappingu.
2. Z `/unique-tournament/{id}/seasons` weź ID obecnego sezonu (najwyższe/najnowsze ID).
3. Z `/unique-tournament/{id}/season/{id}/rounds` wyciągnij listę kolejek (rounds).
4. Dla każdej z interesujących Cię rund zawołaj `/unique-tournament/{id}/season/{id}/events/round/{round_id}`.
*Uwaga:* Mechanizm ten może być zbędny jako główna oś, jeśli chcemy dopasować mecze bukmachera. Faza turnieju i ranga (`roundInfo`, `tournament`, `season`) są dostępne na pojedynczym meczu w `/event/{id}`, niezależnie jak go odnaleźliśmy (czy przez Algorytm A czy B).

### Algorytm B: Dopasowanie per-fixture (Główny mechanizm dla Pipeline'u)
Zamiast szukać w ciemno całych lig, szukamy meczu poprzez drużynę z Superbetu:
1. Wyciągnij drużynę/zawodnika z nazwy w ofercie bukmachera (np. dla "Real Madrid·Barcelona" -> "Real Madrid", a dla tenisa "Lan Mi·Amahee Charrier" -> "Lan Mi").
2. Zawołaj `GET /search/all?q={home_team}`. *Uwaga dla tenisa: zawodnicy również są w wynikach jako `type: "team"`.*
3. Pobierz ID tej encji (najlepiej 1-3 pierwsze wyniki `type: "team"`).
4. Pobierz najbliższe spotkania: `GET /team/{id}/events/next/0` (i ewentualnie `last/0` jeśli data to dziś lub wczoraj).
5. Znajdź zdarzenie, w którym data (`startTimestamp`) i drużyna przeciwna (Away/Home Team na Sofascore) zgadzają się z Superbetem.
6. Pobierz `GET /event/{id}` – dostaniesz wszystkie statystyki, składy, **a także strukturę turnieju** (np. `cupRoundType`, `round`), bez posiadania tej wiedzy z góry.

**Zmierzony wskaźnik sukcesu Algorytmu B:**
W rundzie audytowej sprawdzono listę 377 realnych spotkań Superbet (z 17 września 2026).
- **Tenis:** Sukces **~98%** (230 z 234 spotkań z sukcesem połączono z ID na Sofascore). Brak dopasowań dotyczył jedynie ekstremalnie literówkowych zapisów w ofercie u bukmachera.
- **Piłka Nożna:** Sukces **~80%** (115 z 143 spotkań połączono idealnie w pierwszej, naiwnej próbie). 
  - Główne powody odrzuceń: Polskie nazwy państw (Superbet podaje "Chiny (K)", "Francja U20", "Włochy", a Sofascore w profilu zwraca angielskie "China", "France"), co wymaga zastosowania mapowania tłumaczeń w kodzie (które notabene w pipeline i tak istnieje).
  - Skrajne różnice w formacie drużyn rezerw (Superbet np. "CA Boca Juniors (R)", Sofascore np. "Boca Juniors II").

Wniosek: **Algorytm B jest w pełni samowystarczalny i powinien być domyślnym mechanizmem dopasowania**. Algorytm A pozostaje wyłącznie jako "backup" w przypadku braku odnalezienia egzotycznej ligi.

---

## Pełna Lista Wykorzystanych Endpointów (API Reference)

### 1. Wyszukiwanie (Search)
* **Endpoint:** `GET /search/all?q={query}` (lub `/search/team?q={query}`)
* **Opis:** Wyszukiwarka tekstowa zasobów w bazie Sofascore (drużyny, ligi, zawodnicy).
* **Odpowiedź:** Lista w polu `results`. Każdy element to obiekt z `type` ("team", "player", "uniqueTournament") oraz zagnieżdżonym `entity`. Zwraca `score` trafności.
* **Dowód:** `search_all_real_madrid.json`

### 2. Szczegóły Meczu (Event Details)
* **Endpoint:** `GET /event/{id}`
* **Odpowiedź:** Bardzo bogaty obiekt zawierający:
    * `tournament` i `season` (ID, nazwa ligi, sezon)
    * `roundInfo` (runda, e.g. "1")
    * `homeTeam` / `awayTeam` (id, name, colors, manager)
    * `time` (startTimestamp, currentPeriodStartTimestamp)
    * `status` (code, description - np. "Ended")
    * `venue` (stadium name, city, capacity)
    * `referee` (id, name, country)
* **Dowód:** `event_16363633_details.json`

### 3. Statystyki Meczowe - Piłka Nożna
* **Endpoint:** `GET /event/{id}/statistics`
* **Opis:** Agregaty statystyczne meczu dla gospodarzy i gości.
* **Zwracane Grupy (`groupName`):** "Match overview"
* **Klucze Statystyk (`key`):**
  * `ballPossession`, `kilometersCovered`, `expectedGoals`, `bigChanceCreated`, `totalShotsOnGoal`, `goalkeeperSaves`, `numberOfSprints`, `cornerKicks`, `fouls`, `passes`, `totalTackle`, `freeKicks`, `yellowCards`, `avgRating`.
* **Dowód:** `event_16363633_statistics.json`

### 4. Składy i Statystyki Per-Gracz (Player Match Stats) - Piłka Nożna
* **Endpoint:** `GET /event/{id}/lineups`
* **Opis:** Największa przewaga Sofascore nad ESPNem i Bzzoiro. Zwraca pełne składy (`home`, `away`), z podziałem na pozycje, rezerwowych i (co kluczowe) **statystyki dla każdego zawodnika osobno**.
* **Pola w `statistics` zawodnika:**
  * `totalPass`, `accuratePass`, `goalAssist`
  * `totalLongBalls`, `accurateLongBalls`
  * `touches`, `ballRecovery`, `saves`, `savedShotsFromInsideTheBox`
  * `minutesPlayed`, `rating`, `topSpeed`, `kilometersCovered`, `numberOfSprints`
  * `totalBallCarriesDistance`, `ballCarriesCount`, `totalProgression` (fenomenalne dane o wyprowadzaniu piłki)
  * Modele xG/xA: `expectedAssists`, `goalsPrevented`
* **Dowód:** `event_16363633_lineups.json`

### 5. Incydenty Meczowe
* **Endpoint:** `GET /event/{id}/incidents`
* **Opis:** Lista na osi czasu.
* **Typy `incidentType`:** `card`, `goal`, `injuryTime`, `period`, `substitution`
* **Dowód:** `event_16363633_incidents.json`

### 6. Statystyki Sezonowe Zespołu
* **Endpoint:** `GET /team/{team_id}/unique-tournament/{tournament_id}/season/{season_id}/statistics/overall`
* **Opis:** Sumaryczne liczby z całego sezonu. Zwraca ponad 100 metryk (!).
* **Najciekawsze metryki:** `averageBallPossession`, `expectedGoals`, `expectedGoalsOnTarget`, `bigChancesCreated`, `kilometersCovered`, `numberOfSprints`, `accurateOppositionHalfPasses`. Znakomite dane do modelowania xG oraz profili defensywnych.
* **Dowód:** `team_17_tournament_17_season_96668_stats.json`

### 7. Statystyki Sezonowe Zawodnika
* **Endpoint:** `GET /player/{player_id}/unique-tournament/{tournament_id}/season/{season_id}/statistics/overall`
* Opcjonalnie: `/player/{player_id}/statistics/seasons` (podsumowanie przez lata)
* **Dowód:** `player_839956_tournament_17_season_96668_stats.json`

### 8. Kursy (Odds)
* **Endpoint:** `GET /event/{id}/odds/1/all`
* **Opis:** Zwraca ofertę bukmacherów. Co ciekawe, w tablicy rynków każdy wybór ma flagę `winning: true/false`, co oznacza, że rozstrzygają kursy historyczne (super do backtestów bez łączenia na własną rękę!).
* **Dowód:** `event_16363633_odds.json`

---

## Tenis (Tennis Specifics)
API w tenisie jest kompletne, co wypełnia gigantyczną lukę w pipeline. Discovery opiera się na tych samych zasadach co football (wyszukiwanie gracza -> wydarzenia).

* **Szczegóły Meczowe i Statystyki:**
  * Endpoint: `/event/{id}/statistics`
  * W przeciwieństwie do piłki nożnej, tenis dzieli statystyki na zaawansowane grupy:
    * `Service`: `aces`, `doubleFaults`, `firstServeAccuracy`, `secondServeAccuracy`, `firstServePointsAccuracy`, `secondServePointsAccuracy`, `serviceGamesTotal`, `breakPointsSaved`
    * `Points`: `pointsTotal`, `servicePointsScored`, `receiverPointsScored`, `maxPointsInRow`
    * `Games`: `gamesWon`, `serviceGamesWon`, `maxGamesInRow`
    * `Return`: `firstReturnPoints`, `secondReturnPoints`, `breakPointsScored`
* **Punkt po Punkcie:**
  * Endpoint: `/event/{id}/point-by-point`
  * Daje możliwość pełnego otworzenia historii (każdy set, gem i punkt), idealne do modelowania live lub zaawansowanych metryk (momentum).
* **Power Graph:**
  * Endpoint: `/event/{id}/tennis-power` (Wykres przewagi zawodników na osi czasu. Żyje i ma się dobrze - zwraca macierz punktową).

---

## Obsługa Błędów
API jest spójne:
* Zapytanie o zły (nieistniejący) event ID: HTTP `404` (treść: pusty obiekt lub informacja z Nginx).
* Błędny (pusty) search: HTTP `400`
* Mecze bez statystyk (zaplanowane): Endpoint `/statistics` po prostu zwraca 404, więc jego brak bezpiecznie oznacza brak wygenerowanych jeszcze agregatów.

## Podsumowanie Architektoniczne
W ~15 zdaniach:
Sofascore jest fenomenalnym kandydatem na całkowite zastąpienie Bzzoiro i częściowo ESPN. Dostarcza wielokrotnie bogatsze i głębsze dane niż obecne API Bzzoiro (szczególnie distance covered, touches, sprints, czy pełne xG per gracz) oraz potężnie rozwija analizę Tenisa, na którym nam mocno zależało (serwisy, asy, break pointy). Testy obciążeniowe z uzyciem `curl_cffi` sugerowały brak agresywnego zabezpieczenia, co zdawało się czynić go niemal darmowym i skalowalnym providerem — **teza obalona 2026-09-17: te właśnie testy zbiegły się w czasie z trwałą blokadą `/api/v1/` (patrz sekcja Rate Limiting).** Liczba ">2000 req/s" nie ma pokrycia w żadnym logu w `evidence/`; najwyższa zmierzona wartość to ~550 req/s. Największym mankamentem i tzw. "twardym blokerem" dla trywialnej integracji był brak endpointu z meczami dla danej daty (discovery po dacie), ale problem ten jest łatwo i pewnie omijany przez mechanizmy wyszukiwania na osi turniej -> sezon -> runda lub przez historię meczów zespołu. Najmniejszym pierwszym krokiem do integracji w pipeline byłoby zbudowanie w klasie Discovery nowego flow w pythonie (za pomocą `curl_cffi`), które odczytuje ligi z `sportdb_competition_map.json`, wywołuje listę rund i pobiera zaplanowane eventy, a następnie dla nich pobiera `event/{id}/lineups` oraz `/event/{id}/statistics`, by zserializować te dane w istniejący schemat i zwalidować jakość na historycznych betach.
