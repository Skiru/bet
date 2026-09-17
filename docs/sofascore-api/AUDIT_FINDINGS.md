# Audyt REFERENCE.md — co się potwierdziło, co trzeba powtórzyć

Data: 2026-09-17. Ten dokument to wynik weryfikacji pierwszej rundy audytu
(`REFERENCE.md` + `evidence/`) przez osobę/agenta, który sprawdził twierdzenia
tamtego dokumentu wobec surowych dowodów zapisanych na dysku, a nie wobec
prozy. Cel tego pliku: dać kolejnemu agentowi dokładnie to, co trzeba
dokończyć lub powtórzyć — bez ponownego przechodzenia przez to, co już stoi
na solidnym dowodzie.

## Zweryfikowane jako prawdziwe (nie trzeba powtarzać)

Sprawdzone bezpośrednio w plikach `evidence/*.json`, nie na podstawie opisu:

- **Prawdziwe xG per mecz.** `event_16363633_statistics.json` zawiera
  `expectedGoals` i `expectedGoalsOnTarget` per drużyna, per okres gry,
  realne wartości liczbowe (np. 1.88 vs 0.20). Nie jest to placeholder ani
  zero.
- **Historia drużyny sięga do 2000 roku.** `team_2829_events_last_50.json`
  (status 200, 30 wydarzeń) ma pierwszy mecz z kwietnia 2000, ostatni z
  listopada 2000. Paginacja `/team/{id}/events/last/{page}` faktycznie działa
  tak głęboko.
- **Endpoint kursów istnieje i jest poprawnie opisany.**
  `GET /event/{id}/odds/1/all` zwraca realny rynek 1X2 z fractional odds
  (`event_16363633_odds.json`). Sekcja 8 w REFERENCE.md to poprawnie
  odzwierciedla. Nieistotne operacyjnie (Superbet zostaje jedynym źródłem
  ceny), ale dokumentacyjnie w porządku.
- **Pokrycie lig zgodne z realnym pinned mapem.** 12 z 28 zweryfikowanych lig
  w `config/sportdb_competition_map.json` przetestowano i ID-eki się zgadzają
  (Ekstraklasa 202, K League 1 410, Premier League 17, Saudi Pro League 955,
  itd.) — nie zmyślone.
- **Struktura endpointów meczowych** (`/event/{id}`, `/event/{id}/statistics`,
  `/event/{id}/lineups`, `/event/{id}/incidents`) i ich słowniki pól w
  REFERENCE.md odpowiadają temu, co widać w evidence.

## Problem #1 (krytyczny): wniosek o throttlingu jest niewiarygodny

REFERENCE.md, sekcja "Rate Limiting i Bezpieczeństwo", twierdzi: **3000
requestów, 80 workerów, 2300 req/s, 100% status 200, zero blokad** — i na tej
podstawie rekomenduje 20-50 workerów jako bezpieczne w produkcji.

To twierdzenie **nie ma pliku evidence** (jedyne z całego audytu bez
odpowiadającego dowodu na dysku), mimo wyraźnej instrukcji żeby każdy wynik
miał zapisaną surową parę request→response.

Co więcej, skrypt który to policzył (`docs/sofascore-api/scripts/sofa_test.py`,
funkcja `test_rate_limit`) **uderza 3000 razy w JEDEN i ten sam URL** przez
jedną współdzieloną sesję curl_cffi. Kilka endpointów w evidence pokazuje
nagłówek `cache-control: public, s-maxage=...` — to prawie na pewno oznacza,
że test mierzył szybkość serwowania z cache brzegowego Cloudflare/CDN dla
identycznego zasobu, **nie realną ochronę API przy różnych zasobach**, a
dokładnie tak będzie wyglądał ruch produkcyjny (setki różnych event/team id
dziennie, nigdy ten sam URL w kółko). Dodatkowo `if __name__ == '__main__':
pass` w zapisanym skrypcie oznacza, że liczby "2300 req/s" nie są
odtwarzalne z tego co leży na dysku — pochodzą z jakiegoś nieudokumentowanego
wywołania interaktywnego.

**Wniosek: rekomendacja "20-50 workerów bezpiecznie" jest niepotwierdzoną
hipotezą, nie wynikiem pomiaru. Nie wdrażaj jej do pipeline'u bez powtórki.**

### Co zrobić w kolejnej rundzie
1. Wygeneruj listę **co najmniej 200-500 różnych, realnych ID** (event id z
   różnych lig/dat, team id) — nie jeden powtarzany URL. Najlepiej wymieszaj
   typy endpointów (`/event/{id}`, `/event/{id}/statistics`,
   `/event/{id}/lineups`, `/team/{id}/events/last/0`) żeby wynik odzwierciedlał
   realny mix ruchu.
2. Odpal test z rosnącą współbieżnością (np. 5, 20, 50, 100, 200 workerów) i
   dla każdego poziomu zapisz: całkowity czas, req/s, rozkład kodów statusu
   (200/403/429/inne), oraz czy którykolwiek response miał treść Cloudflare
   challenge zamiast JSON-a.
3. **Zapisz surowy log per-request** do pliku (timestamp, url, status,
   czas odpowiedzi) — nie tylko podsumowanie w prozie. Np.
   `docs/sofascore-api/evidence/rate_limit_test_log.jsonl`, jedna linia na
   request.
4. Utrzymaj sesję przez dłużej niż 1-2 sekundy — zrób też test "sustained":
   stałe tempo (np. 10 req/s) przez 5-10 minut, żeby złapać ewentualny
   throttling czasowy (nie tylko burst).
5. Jeśli po tym wszystkim wciąż zero blokad — świetnie, ale wtedy podaj
   rekomendację bezpiecznego tempa z realnym pomiarem za sobą, nie z
   ekstrapolacji jednego cache'owanego URL-a.

## Problem #2: pułapka w search nie trafiła do dokumentacji

`evidence/search_league_brazil_serie_b.json` pokazuje, że
`GET /search/all?q=brazil serie b` zwraca na **pozycji 0** "Brasileirão
Betano" (`brasileirao-serie-a`, czyli **Serie A**) — prawidłowa Serie B
(id 390) jest dopiero na pozycji 1. Agent to zauważył i poprawnie dotarł do
właściwego ID przez lepsze zapytanie (`search_league_brazil_serie_b2.json`,
`q=brasileirao serie b`), ale **REFERENCE.md nie zawiera o tym ostrzeżenia**
— tabela pokrycia lig po prostu pisze "TAK" bez zastrzeżenia.

To dokładnie ta sama klasa błędu, przed którą chroni istniejący kod w
`src/bet/simple_stats/providers.py` (`_sportdb_competition_refs`) — tamten
docstring opisuje wprost, że naiwne wyszukiwanie tekstowe zwraca złą ligę na
pierwszej pozycji ("La Liga - Spain" → Liga MX pierwsza). Ktoś, kto zbuduje
adapter Sofascore na podstawie samego REFERENCE.md i weźmie `results[0]` bez
disambiguacji, wpadnie w ten sam błąd, który już raz naprawialiśmy dla innego
providera.

### Co zrobić w kolejnej rundzie
1. Dodaj do REFERENCE.md sekcję "Pułapki wyszukiwania" z tym konkretnym
   przykładem (Serie A vs Serie B) jako dowodem.
2. Przetestuj `/search/all` na **wszystkich pozostałych ~16 nieprzetestowanych
   pinowanych ligach** z `config/sportdb_competition_map.json` (m.in. La Liga,
   Serie A, Bundesliga, Ligue 1, Championship, Eredivisie, Primeira Liga,
   Allsvenskan, Eliteserien, Brazil Serie A, Swiss Super League, Belgian Pro
   League, Scottish Premiership, Austrian Bundesliga, MLS, Superliga,
   Super League Greece) i dla każdej zanotuj: czy `results[0]` to poprawna
   liga, a jeśli nie — jakie zapytanie trzeba użyć żeby trafić poprawnie.
3. Na tej podstawie zaproponuj **deterministyczny algorytm disambiguacji**
   (np. dopasowanie po `category.country` + `entity.name` fold, analogicznie
   do tego co już robi `_sportdb_competition_refs`), nie samo "weź pierwszy
   wynik".

## Problem #3 (ustalenie operatora, 2026-09-17): dopasowanie per-fixture, nie discovery per-liga

W trakcie tego audytu operator zauważył coś, co zmienia priorytet całej
integracji, i sprawdziłem to na żywo:

**Superbet w ogóle nie daje nam nazwy ligi/turnieju.** Wywołałem live
`SuperbetClient.events_by_date()` (klient już istnieje w
`src/bet/api_clients/superbet.py`) — zwraca 1784 eventy na dziś, każdy z
polami `sportId`, `categoryId`, `tournamentId` (goła liczba), `matchName`,
`matchDate`. **Zero pola z czytelną nazwą turnieju.** Sprawdziłem cały repo
(`grep -rn "categoryName\|tournamentName"`) — nigdzie w kodzie ani configu
nie ma mapowania tych ID na nazwy. Próbowałem 12 różnych zgadywanych
endpointów Superbeta (`/v2/pl/categories`, `/v2/pl/menu`,
`/v2/pl/navigation`, `/v2/pl/sports/{id}/categories`, itd.) — wszystkie 404.
To by wymagało osobnego reverse-engineeringu, TAK SAMO jak dla Sofascore.

**Ale to nie jest potrzebne**, bo dopasowanie fixture'u nie musi znać nazwy
ligi z góry. Dokładnie tak samo już dopasowujemy Superbeta do bzzoiro: po
nazwach drużyn (`split_match_name` w `src/bet/api_clients/superbet.py`) i
dacie, nie po nazwie ligi. Ten sam mechanizm działa do Sofascore:

1. `matchName` z Superbeta → `split_match_name()` → nazwa drużyny gospodarzy
2. `GET /search/all?q=<drużyna>` → team id po stronie Sofascore (search po
   drużynach działa dobrze — problem z niejednoznacznością z Problemu #2
   dotyczył **lig**, nie klubów, nie testowaliśmy jeszcze niejednoznaczności
   nazw klubów, ale jest dużo mniej prawdopodobna niż dla lig)
3. `GET /team/{id}/events/next/0` (lub `/events/last/0` dla meczów, które już
   się skończyły) → znajdź event pasujący datą (`matchDate` z Superbeta) i
   przeciwnikiem
4. `GET /event/{id}` na znalezionym evencie **od razu zwraca `roundInfo`
   (round, name, cupRoundType), `tournament`, `season`** — czyli fazę
   turnieju, rangę rozgrywek, wszystko czego operator chciał, bez
   wcześniejszej wiedzy "to jest puchar". Zweryfikowane już w audycie:
   Copa del Rey (puchar, nie liga) zwraca `roundInfo: {"round": 28, "name":
   "Semifinals", "cupRoundType": 2}` przez dokładnie tę samą ścieżkę co
   liga.

**Wniosek: mecz ligowy i pucharowy przechodzą identyczną ścieżkę
dopasowania — różnica ujawnia się dopiero po stronie odpowiedzi, jako pole,
nie jako osobna gałąź logiki wcześniej.** To oznacza, że **Algorytm A**
(discovery przez `unique-tournament → season → rounds`, opisany wyżej w tym
dokumencie) może być zbędny dla głównego przypadku użycia — potrzebny
byłby tylko gdybyśmy chcieli *proaktywnie* odkrywać mecze, których jeszcze
nie ma na Superbecie. **Algorytm B** (drużyna+data) powinien być głównym
mechanizmem integracji, bo lista meczów do dopasowania i tak już mamy z
Superbeta (`runs/<date>/<date>_superbet_offer.json`, obecnie 377 eventów w
dniu 2026-09-17).

### Co zrobić w kolejnej rundzie (priorytet wyższy niż Problem #2)
1. Weź realną listę meczów z `runs/2026-09-17/2026-09-17_superbet_offer.json`
   (pole `superbet_match_name`, ~377 wpisów football+tenis) jako **wejście
   testowe**, nie wymyślone przykłady.
2. Dla próbki (np. 40-60 meczów, w tym mecze z nisz: puchary, kwalifikacje,
   mniejsze ligi) przejdź pełny łańcuch: split nazwy → `/search/all` →
   team id → `/team/{id}/events/next|last/{page}` → dopasowanie po dacie →
   `/event/{id}`. Zapisz **wskaźnik sukcesu** (ile % fixture'ów z Superbeta
   dało się jednoznacznie dopasować do konkretnego event id na Sofascore) i
   **każdy przypadek porażki z powodem** (drużyna nie znaleziona, więcej niż
   jeden kandydat na tę datę, nazwa drużyny niejednoznaczna jak np. rezerwy
   "Real Madrid II" vs "Real Madrid").
3. Sprawdź osobno tenis — tam `matchName` to gracze, nie drużyny, i turnieje
   są jednorazowe/cotygodniowe (dużo wyższa kardynalność niż w piłce) — czy
   ten sam łańcuch (`/search/all?q=<gracz>` → wydarzenia gracza →
   dopasowanie po dacie+przeciwniku) działa równie dobrze.
4. Dopiero jeśli wskaźnik sukcesu Algorytmu B jest za niski na jakimś
   segmencie (np. niszowe puchary krajowe), rozważ Algorytm A jako
   uzupełnienie dla tego segmentu — nie jako domyślny mechanizm.

## Porządek w repo

Skrypty audytowe (`sofa_test.py`, `fetch_evidence_1.py`...`fetch_evidence_13.py`)
zostały przeniesione z root repo do `docs/sofascore-api/scripts/` — trzymaj
się tej lokalizacji w kolejnej rundzie (dopisuj kolejne `fetch_evidence_N.py`
tam, albo jeden większy skrypt), nie zostawiaj plików roboczych w root.

## Zakres tej rundy — czego NIE trzeba robić

- Struktura endpointów meczowych, lineups, statystyk sezonowych, tenisa —
  zweryfikowane, nie powtarzaj.
- Discovery przez `unique-tournament → season → rounds → events/round/{n}` —
  zweryfikowane jako działające i deterministyczne, nie powtarzaj (ale patrz
  Problem #3: to prawdopodobnie NIE jest droga, którą warto budować jako
  pierwszą).
- Brak endpointu discovery-po-dacie — potwierdzone martwe, nie powtarzaj.
- **Nie szukaj endpointu Superbeta tłumaczącego `tournamentId`/`categoryId`
  na nazwę ligi.** Sprawdzone: nie istnieje w oczywistych miejscach (12
  zgadywanych ścieżek, wszystkie 404) i — ważniejsze — Problem #3 pokazuje,
  że w ogóle nie jest potrzebny. Dopasowanie idzie po drużynie+dacie, a
  kontekst turnieju (faza, ranga) przychodzi z Sofascore's `/event/{id}` już
  PO dopasowaniu, nie musi być znany wcześniej.

Skup się wyłącznie na: (1) poprawnym pomiarze throttlingu na różnych
zasobach z zapisanym logiem, (2) domknięciu pokrycia lig + udokumentowaniu
pułapki search, (3) zmierzeniu wskaźnika sukcesu dopasowania per-fixture
(Algorytm B) na realnej liście meczów z Superbeta — to jest teraz priorytet
architektoniczny, bo od niego zależy czy Algorytm A w ogóle jest potrzebny.
Po tych trzech punktach dokument będzie gotowy jako podstawa do decyzji
architektonicznej.
