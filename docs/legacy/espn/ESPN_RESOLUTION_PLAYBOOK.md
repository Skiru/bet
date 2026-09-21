# ESPN Resolution & Integration Playbook for Bzzoiro

Ten dokument stanowi oficjalny podręcznik (Playbook) architektury, katalogu API, procedur wyszukiwania, mapowania encji oraz rezolucji wydarzeń (event resolution) pomiędzy zewnętrznymi dostawcami kursów (np. Superbet, bzzoiro) a nieoficjalnym interfejsem ESPN API.

Został opracowany na podstawie empirycznej inżynierii wstecznej (reverse engineering), analizy kodu źródłowego repozytorium oraz setek bezpośrednich zapytań HTTP do produkcyjnych środowisk ESPN Core API, Site API i Web Search API przeprowadzonych we wrześniu 2026 r.

---

## A. Architektura Przepływu Danych (Architecture)

Celem integracji jest bezpieczne, deterministyczne i odporne na błędy (fail-closed) mapowanie obiektów:

```text
       Superbet / Bzzoiro Raw Event
                   │
                   ▼
       1. Normalizacja i Ekstrakcja Cech
          (sport, uczestnicy, data/czas, liga, płeć, wiek/rezerwy)
                   │
                   ▼
       2. Weryfikacja Wsparcia Rozgrywek (League Gate)
          Czy ESPN w ogóle obsługuje daną ligę/tier?
          [NIE] ──► PROOF_OF_ABSENCE / EVENT_NOT_FOUND (natychmiastowy fail-closed)
          [TAK]
                   │
                   ▼
       3. Discovery & Rezolucja Kandydatów (Entity Resolution)
          Wyszukanie Home & Away (Team / Athlete)
          Wykrycie duplikatów ID, stubów i ról
          [Brak/Niejednoznaczność] ──► ENTITY_NOT_FOUND lub AMBIGUOUS
          [Znaleziono]
                   │
                   ▼
       4. Powiązanie Wydarzenia (Event Resolution)
          Przeszukanie terminarzy (Schedule), Scoreboardów i Eventlogów
          Ocena kandydatów: Entity Match + Opponent + Date/Time + Tier
          [Brak powiązania] ──► EVENT_NOT_FOUND (z dowodem PROOF_OF_ABSENCE)
          [Dopasowano]
                   │
                   ▼
       5. Wzbogacenie i Statystyki (Enrichment)
          Pobranie statystyk drużynowych, składów, linii punktowych i zdarzeń
```

### Podstawowe Stany Wyjściowe (The 4 States):
1. `EVENT_FOUND`: Obie encje zostały jednoznacznie zidentyfikowane, a konkretne spotkanie dopasowane i zweryfikowane czasowo/konkurencyjnie (Score $\ge 0.80$).
2. `ENTITY_FOUND`: Obie encje (drużyny/zawodnicy) istnieją w ESPN, ale dane spotkanie **nie występuje** w ofercie ESPN (np. turnieje ITF / Challenger w tenisie, sparingi, nielicencjonowane puchary).
3. `EVENT_NOT_FOUND`: Przynajmniej jedna encja nie istnieje w ESPN lub liga jest strukturalnie nieobsługiwana.
4. `AMBIGUOUS`: Zapytanie pasuje do wielu sprzecznych encji bez możliwości rozstrzygnięcia (np. „Arsenal” bez wskazania ligi męskiej vs żeńskiej vs argentyńskiej).

---

## B. Katalog Endpointów ESPN (Endpoint Catalogue)

W ekosystemie ESPN funkcjonują 4 odrębne domeny API, różniące się strukturą URL, nagłówkami i poziomem szczegółowości:

| Endpoint | Domena | Cel / Zastosowanie | Wejście (Input) | Wyjście (Output) | Uwagi / Nagłówki / Rate Limit | Niezawodność |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `https://sports.core.api.espn.com/v2/sports` | Core API | Dynamiczne discovery wszystkich dyscyplin sportowych | `limit=50` | Lista 17 dyscyplin sportowych | Publiczne, brak klucza. Cache: 30 dni. | Bardzo wysoka |
| `https://sports.core.api.espn.com/v2/sports/{sport}/leagues` | Core API | Dynamiczne discovery wszystkich lig dla danego sportu | `sport` (np. `soccer`, `tennis`), `limit=300` | Lista zasobów ligowych (218 lig piłkarskich, 2 tenisowe) | Zwraca kanoniczne slugi. Cache: 7 dni. | Bardzo wysoka |
| `https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard` | Site API | Wyniki na żywo, mecze zakończone, terminarz dnia | `sport`, `league`, `dates=YYYYMMDD` | Pełna lista zdarzeń, statusy, kursy, linescores | **UWAGA: Blokada WAF Akamai!** Nie wysyłać nagłówka `User-Agent: Mozilla/5.0` (zwraca HTTP 403). Używać domyślnego klienta requests lub `Accept: application/json`. | Wysoka |
| `https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams` | Site API | Katalog drużyn danej ligi | `sport`, `league` | Lista obiektów drużyn (ID, nazwy, skróty, logo) | Działa dla lig z aktywnym katalogiem (88 lig). Dla lig martwych zwraca pustą listę. | Wysoka |
| `https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{team_id}/schedule` | Site API | Terminarz i ostatnie mecze drużyny | `sport`, `league`, `team_id` | Lista meczów przeszłych i nadchodzących z datami UTC | Idealne do szukania meczu po drużynie bez znajomości dokładnej daty. | Wysoka |
| `https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{team_id}/roster` | Site API | Skład kadrowy drużyny | `sport`, `league`, `team_id` | Zawodnicy, pozycje, numery, statusy | Przydatne do weryfikacji graczy w piłce. | Wysoka |
| `https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/summary` | Site API | Szczegółowe podsumowanie meczu piłki nożnej | `sport`, `league`, `event={event_id}` | `boxscore.teams` (28 statystyk), `rosters` (statystyki graczy), `keyEvents` | **Działa tylko dla piłki nożnej, koszykówki i hokeja. Dla tenisa zwraca HTTP 400!** | Wysoka |
| `https://site.web.api.espn.com/apis/common/v3/search` | Web API | Globalna wyszukiwarka zawodników i drużyn | `query`, `type=player\|team`, `sport`, `limit` | Kandydaci z `id`, `displayName`, `league`, `country` | Wrażliwa na znaki interpunkcyjne (ukośnik `/` lub myślnik psuje tokenizację). | Wysoka |
| `https://site.api.espn.com/apis/search/v2` | Site API | Wyszukiwarka wieloaspektowa | `query`, `limit` | Zwraca **wszystkie** rekordy (kluczowe do wykrywania zduplikowanych ID zawodników) | Zwraca obiekty z `uid` zawierającym kod sportu i ligi. | Wysoka |
| `https://sports.core.api.espn.com/v2/sports/tennis/leagues/{tour}/athletes/{athlete_id}/eventlog` | Core API | Kompletna historia meczów tenisisty | `tour` (`atp`/`wta`), `athlete_id`, `limit` | Lista referencji do `event`, `competition`, `competitor` | Stuby zwracają HTTP 404; aktywni zawodnicy zwracają realne turnieje i mecze. | Wysoka |
| `https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/rankings` | Site API | Oficjalny ranking ATP / WTA | `tour` (`atp`/`wta`) | Top 150 zawodników z pozycją i punktami | Aktualizowane co tydzień. Cache: 24h. | Wysoka |

---

## C. Strategia Odnajdywania Drużyn (Team Resolution Strategy)

### 1. Źródła danych i mechanizmy:
1. **Search v3 (`/apis/common/v3/search?query=...&type=team&sport=soccer`)**:
   - Pierwszy krok przy braku znajomości ligi.
   - Zwraca `id`, `displayName`, `league`.
2. **Katalog Ligi (`/sports/soccer/{league}/teams`)**:
   - Najbezpieczniejsza metoda przy znanej lidze.
   - Zwraca dokładny zestaw klubów grających w danej klasie rozgrywkowej.
3. **Terminarz Zespołu (`/teams/{id}/schedule`)**:
   - Po znalezieniu ID drużyny gospodarzy pozwala przeszukać jej mecze i znaleźć przeciwnika.

### 2. Obsługa przypadków szczególnych i pułapek (Edge Cases):
- **Suffixy wiekowe (U19, U21, U23, Youth, Juvenil):**
  - **KRYTYCZNE OSTRZEŻENIE:** Funkcja `normalize_team_name` w `src/bet/utils/common.py` bezwarunkowo usuwa tokeny `U19/U21/B/II/Reserves`. Powoduje to, że „Barcelona U19” staje się „barcelona”, co prowadzi do fałszywego zmapowania drużyny młodzieżowej na pierwszy zespół seniorów (ID 83 zamiast 130878)!
  - **Zasada bezpieczna:** Jeżeli zapytanie zawiera znacznik młodzieżowy, resolver **nie może** zaakceptować drużyny seniorskiej. ESPN nie posiada lig młodzieżowych klubowych (brak UEFA Youth League, brak lig hiszpańskich U19). Zapytanie musi zwrócić `ENTITY_NOT_FOUND`.
- **Rezerwy i drugie zespoły (II, B, Castilla, Reserves):**
  - Drużyny rezerw (np. Bayern Munich II, Real Madrid Castilla) posiadają w ESPN własne, odrębne identyfikatory (np. Castilla to ID 7000, Bayern II to ID 21630). Nie wolno mapować ich na klub macierzysty.
- **Kobiety (Women, W, Femenino):**
  - Drużyny kobiece posiadają odrębne ID i ligi (np. Chelsea Men: ID 363 w `eng.1`, Chelsea Women: ID 19970 w `eng.w.1`). Znacznik płci musi bezwzględnie filtrować ligę (`*.w.*`).
- **Reprezentacje narodowe vs Kluby:**
  - Nazwa kraju (np. „Poland”) odpowiada zarówno reprezentacji męskiej (ID 471), kobiecej (ID 19345), młodzieżowej (ID 22032), jak i potencjalnym klubom. Bez kontekstu ligi wynik jest `AMBIGUOUS`.
- **Transliteracje i pisownia niemiecka/turecka/nordycka:**
  - „1. FC Köln” w ESPN figuruje wyłącznie jako „FC Cologne” (ID 122). Wymaga słownika pinów (`_ESPN_TEAM_NAME_PINS`).
  - „Bodø/Glimt” – ukośnik `/` w zapytaniu Search API blokuje tokenizację Akamai/Solr i zwraca 0 wyników. Należy usuwać znaki specjalne i szukać po słowie kluczowym `Bodo` lub `Glimt`.

---

## D. Strategia Odnajdywania Zawodników w Tenisie (Athlete Resolution Strategy)

### 1. Dwuetapowe przeszukiwanie (Dual Search):
Ponieważ ESPN posiada **zduplikowane profile zawodników** (jeden pusty stub bez meczów i jeden profil aktywny), resolver musi odpytywać:
1. `site.api.espn.com/apis/search/v2?query={name}` – zwraca tablicę wszystkich pasujących obiektów z identyfikatorami UID (np. `s:850~l:900~a:14877`).
2. Dla każdego kandydata następuje sprawdzenie endpointu `eventlog`:
   `https://sports.core.api.espn.com/v2/sports/tennis/leagues/{tour}/athletes/{id}/eventlog`
   - Jeśli status to HTTP 404 lub `count == 0` -> rekord jest martwym stubem.
   - Jeśli `count > 0` -> rekord jest aktywnym profilem sportowym.

### 2. Udokumentowane duplikaty zawodników (Empirical Findings):
- **Mika Stojsavljevic**:
  - ID `12347`: pusty stub (brak kraju, eventlog zwraca HTTP 404). Zwracany jako pierwszy przez Search v3!
  - ID `14877`: aktywny profil (Great Britain GBR, 11 turniejów w eventlog m.in. Wimbledon, Nottingham).
- **Lucia Cortez Llorca**:
  - ID `5092`: pusty stub (brak kraju, eventlog HTTP 404).
  - ID `10678`: aktywny profil (Spain ESP, 4 turnieje w eventlog).
- **Ruth Roura Llaverias**:
  - ID `11795`: pusty stub (eventlog HTTP 404).
  - ID `16206`: aktywny profil (Spain ESP, 2 turnieje w eventlog).

### 3. Ograniczenie do turniejów głównych (ATP / WTA):
W tenisie ESPN **nigdy** nie tworzy lig `challenger` ani `itf`. Wszystkie zapytania do endpointów ligowych innych niż `atp` i `wta` zwracają natychmiastowy błąd `HTTP 400 Bad Request`.
Zawodnicy grający wyłącznie w turniejach rangi ITF / Challenger (np. Pavel Lagutin, Meritxell Teixido Garcia, Niklas Schell, Jack Loge) mogą figurować w bazie jako zarejestrowany profil zawodnika, ale ich `eventlog` jest pusty lub zwraca 404, ponieważ ESPN nie rejestruje pojedynków z tych rozgrywek.

---

## E. Strategia Rezolucji Zdarzeń (Event Resolution Strategy)

Dla pary zawodników lub drużyn resolver stosuje model punktowy (Scoring Engine) gwarantujący brak fałszywych dopasowań:

$$Score = S_{entities} + S_{date} + S_{time} + S_{league}$$

1. **Entity Match ($S_{entities} = 0.50$):**
   Obaj uczestnicy muszą zostać znalezieni w tym samym wydarzeniu/meczu. W tenisie sprawdza się, czy ID rywala znajduje się w tablicy `competitors` spotkania w `eventlog` gracza A. W piłce sprawdza się terminarz gospodarza.
2. **Date Match ($S_{date}$ do $0.35$):**
   - Różnica dat $\Delta d = 0$ dni (w UTC): $+0.35$.
   - Różnica dat $\Delta d = 1$ dzień (uwzględnienie stref czasowych / meczów nocnych): $+0.20$.
   - $\Delta d > 1$ dzień: $0.00$ (odrzucenie).
3. **Time Compatibility ($S_{time}$ do $0.14$):**
   - Jeśli czas jest znany i różnica $< 3.0$ h: $+0.13$.
   - Jeśli `timeValid == False` lub czas to `00:00:00` (TBD): $+0.10$.
4. **Próg Akceptacji (Fail-Closed Threshold):**
   - Wymagany wynik minimalny: **$0.80$**.
   - Poniżej $0.80$ resolver zwraca `EVENT_NOT_FOUND` z logiem przyczyny.
   - W przypadku dwóch kandydatów o identycznym najwyższym wyniku: status `AMBIGUOUS`.

---

## F. Dynamiczne Discovery Lig (League Discovery Strategy)

Zamiast sztywno zakodowanych list slugów, discovery opiera się na katalogu ESPN Core:
```text
GET https://sports.core.api.espn.com/v2/sports/soccer/leagues?limit=300
```
- Zwraca **218 lig piłkarskich**.
- Każdy rekord zawiera unikalny `slug` (np. `eng.1`, `esp.1`, `bra.camp.paulista`) oraz numeryczne `id` (np. 700 dla Premier League).
- **Stabilność identyfikatorów:** Slugi są niezmienne w URL-ach API od ponad dekady. Numeryczne ID lig są stabilne w Core API.
- **Weryfikacja dostępności:** Spośród 218 lig, około 88 lig posiada aktywny katalog drużyn (`/teams`). Pozostałe ligi to turnieje historyczne, archiwalne lub niszowe puchary (zwracające HTTP 200 z pustą listą `teams: []`).

---

## G. Normalizacja Czasu i Dat (Time & Date Normalization)

1. **Format Timestampów ESPN:**
   Wszystkie timestampy w polach `date` i `startDate` są zwracane w formacie **ISO-8601 UTC** ze znacznikiem `Z` (np. `2026-09-12T14:00Z`).
2. **Czas lokalny:**
   Czas lokalny stadionu pojawia się wyłącznie w polach tekstowych `status.type.detail` (np. `"Sat, September 12th at 10:00 AM EDT"`). Nie należy na nim polegać przy obliczeniach maszynowych.
3. **Flaga `timeValid`:**
   Pole logiczne w obiekcie `competition`. Jeśli mecz nie ma jeszcze potwierdzonej godziny (TBD), `timeValid` ma wartość `False`, a godzina jest ustawiana domyślnie na `00:00Z` lub godzinę otwarcia kolejki.
4. **Rozbieżność `event.date` vs `competition.date` w tenisie:**
   - `event.date`: Data rozpoczęcia **całego turnieju** (np. `2026-08-24T04:00Z` dla US Open trwającego 2 tygodnie).
   - `competition.date`: Rzeczywista data i godzina **konkretnego meczu** (np. `2026-09-10T23:00Z` dla półfinału Sabalenka vs Pegula).
   - **Kardynalny błąd:** Odczytanie `event.date` w tenisie powoduje błąd przesunięcia daty o kilkanaście dni! Należy bezwzględnie czytać `competition.date`.

---

## H. Obsługa Duplikatów (Duplicate Handling)

| Typ Duplikatu | Przykład z Rzeczywistości | Rozwiązanie Techniczne |
| :--- | :--- | :--- |
| Ten sam zawodnik $\rightarrow$ Wiele ID | Mika Stojsavljevic (ID `14877` i `12347`) | Użycie Search v2, pobranie wszystkich ID, odpytanie `eventlog` i odrzucenie stubów zwracających 404 / 0 meczów. |
| Ta sama drużyna $\rightarrow$ Wiele lig | Arsenal (ID `359` w `eng.1`, ID `19973` w `eng.w.1`, ID `2635` w `arg.3`) | Wymuszenie parametru ligi lub filtra płci; przy braku ujednoznacznienia zwrócenie `AMBIGUOUS`. |
| Nazwa seniorska vs młodzieżowa | Barcelona (senior ID `83`) vs Barcelona U19 (ID `130878`) | Zakaz stripowania suffixów U19/U21 w zapytaniach do encji młodzieżowych. |

---

## I. Dowód Nieobecności Zdarzenia (Negative Lookup / Proof of Absence)

Aby jednoznacznie stwierdzić, że ESPN **nie posiada** danego wydarzenia, a nie jest to błąd wyszukiwarki, należy przeprowadzić procedurę 4-krokowego dowodu:
1. **Dowód ligowy:** Sprawdzenie, czy liga/poziom rozgrywkowy znajduje się w oficjalnym wykazie 218 lig ESPN. Jeśli liga to np. ITF, Challenger, liga fińska, egipska czy 3. liga szwajcarska – brak ligi jest dowodem strukturalnym.
2. **Dowód zawodnika/drużyny:** Wyszukanie w Search v2 i Search v3. Jeśli encja nie istnieje w bazie ESPN – dowód braku uczestnika.
3. **Dowód terminarza (Eventlog / Schedule):** Jeśli obaj uczestnicy istnieją (np. Lagutin i Alcala Gurri), pobiera się pełny `eventlog` obu graczy. Jeśli w ich historii nie ma wspólnego meczu – dowód braku fixture'a.
4. **Dowód Scoreboardu:** Przeszukanie całego dnia zawodów `/scoreboard?dates=YYYYMMDD`. Jeśli meczu tam nie ma – ostateczny `PROOF_OF_ABSENCE`.

---

## J. Macierz Pokrycia Rozgrywek (Coverage Matrix)

### 1. Piłka nożna (Soccer):
- **Wspierane w pełni (Tier 1):** Premier League (`eng.1`), Championship (`eng.2`), League 1 (`eng.3`), League 2 (`eng.4`), National League (`eng.5`), La Liga (`esp.1`), La Liga 2 (`esp.2`), Bundesliga (`ger.1`, `ger.2`), Serie A (`ita.1`, `ita.2`), Ligue 1 (`fra.1`, `fra.2`), Eredivisie (`ned.1`, `ned.2`), Liga Portugal (`por.1`), MLS (`usa.1`), Liga MX (`mex.1`, `mex.2`), Argentyna (`arg.1`, `arg.2`), Brazylia (`bra.1`, `bra.2`), Kolumbia (`col.1`), Chile (`chi.1`), Urugwaj (`uru.1`), Ekwador (`ecu.1`), Paragwaj (`par.1`), Boliwia (`bol.1`), Wenezuela (`ven.1`), Dania (`den.1`), Grecja (`gre.1`), Turcja (`tur.1`), Szkocja (`sco.1`, `sco.2`), Belgia (`bel.1`), Austria (`aut.1`), Szwajcaria (`sui.1`), Szwecja (`swe.1`), Norwegia (`nor.1`), Rumunia (`rou.1`), Izrael (`isr.1`), Arabia Saudyjska (`ksa.1`), Japonia (`jpn.1`), Chiny (`chn.1`).
- **Niezwykłe kraje aktywne:** Gwatemala (`gua.1`), Salwador (`slv.1`), stanowe ligi brazylijskie (`bra.camp.paulista`).
- **Brak wsparcia (0% coverage):**
  - Krajowe ligi młodzieżowe (Barcelona U19, Fenerbahce U19 itp.).
  - Ligi rezerw (MLS Next Pro, liga rezerw Argentyny).
  - Szwecja niższe ligi (Superettan `swe.2` zwraca pusty katalog).
  - Finlandia (Veikkausliiga i niższe ligi – całkowity brak w drzewie ESPN).
  - Kraje bałtyckie (Estonia, Łotwa, Litwa – brak lig krajowych).
  - Egzotyka: Egipt, ZEA, Katar, Uzbekistan, Azerbejdżan, Oman, Jordania, Czarnogóra, Islandia, Nikaragua, Gruzja, Serbia, Iran, Bahrajn, Algieria, Wietnam, Uganda, Kosowo, Irak, 3. liga francuska (National).

### 2. Tenis:
- **Wspierane w pełni:** Turnieje Wielkiego Szlema (US Open, Wimbledon, Roland Garros, Australian Open), ATP Tour (Masters 1000, 500, 250), WTA Tour (1000, 500, 250, wybrane 125).
- **Całkowity brak wsparcia:** ATP Challenger Tour, ITF Men's World Tennis Tour (M15, M25), ITF Women's World Tennis Tour (W15, W35, W50, W75, W100), turnieje juniorskie ITF.

---

## K. Znane Ograniczenia Techniczne (Known Limitations)

1. **WAF User-Agent Blocking:**
   Serwery brzegowe Akamai na domenie `site.api.espn.com` blokują popularne nagłówki przeglądarkowe (`User-Agent: Mozilla/5.0...`) kodem HTTP 403 Access Denied. Klient musi wysyłać nagłówek czysty lub domyślny nagłówek biblioteki requests z `Accept: application/json`.
2. **Wrażliwość wyszukiwarki na znaki specjalne:**
   Wyszukiwarka Web Search (`apis/common/v3/search`) traktuje znak ukośnika `/` i myślnik `-` jako operatory składniowe Lucene/Solr. Wpisanie „Bodo/Glimt” daje 0 wyników; wpisanie „Bodo” lub „Glimt” zwraca poprawny klub.
3. **Brak statystyk meczowych w tenisie:**
   Endpoint `/summary` nie działa dla tenisa (zwraca HTTP 400). Statystyki meczowe ograniczają się do liczby setów i gemów z tablicy `linescores` na scoreboardzie. Asy, podwójne błędy i punkty przełamania nie są udostępniane przez ESPN API.
4. **Lokalizacja statystyk zawodników w piłce nożnej:**
   W endpointach `/summary` dla piłki nożnej pole `boxscore.players` jest zawsze puste (`[]`). Rzeczywiste statystyki indywidualne piłkarzy (strzały, faule, kartki, gole, asysty, minuty) znajdują się w strukturze:
   `summary["rosters"][team_index]["roster"][player_index]["stats"]`.

---

## L. Rekomendowana Polityka Cache'owania (Recommended Caching)

| Zasób | TTL Rekomendowane | Uzasadnienie |
| :--- | :--- | :--- |
| Wykaz dyscyplin i lig (`/sports`, `/leagues`) | 30 dni (720h) | Struktura ligowa ESPN zmienia się rzadziej niż raz na sezon. |
| Katalogi drużyn (`/teams`) | 7 dni (168h) | Zestaw klubów w lidze jest stały w trakcie trwania sezonu. |
| Profile zawodników i drużyn (`athletes/{id}`, `teams/{id}`) | 7 dni (168h) | Identyfikatory i dane biograficzne są trwałe. |
| Tabele ligowe (`/standings`) | 12 godzin | Zmieniają się po zakończeniu serii gier. |
| Wyniki zakończonych meczów (`status == STATUS_FINAL`) | 7 dni (168h) | Wynik meczu zakończonego jest niezmienny. |
| Scoreboard dnia bieżącego (`/scoreboard`) | 5-15 minut | Śledzenie wyników na żywo i zmian godzin meczów. |
| Mecze nadchodzące (prematch) | 2-6 godzin | Uwzględnianie ewentualnych przesunięć godzinowych. |
| Negatywne wyniki wyszukiwania (miss cache) | 24 godziny | Zapobiega powtarzaniu kosztownych pełnych skanów dla nieistniejących fixture'ów. |

---

## M. Katalog 15 Pułapek i Anomalii ESPN API (The 15 Traps Catalog)

Na podstawie 15 iteracji głębokiego review empirycznego zidentyfikowano następujące pułapki techniczne:

1. **Trap 01: Selektywne filtrowanie sygnatur User-Agent przez WAF Akamai**
   - Skrócony nagłówek `Mozilla/5.0` oraz `Wget` zwracają natychmiastowy kod HTTP 403.
   - Prawidłowe działanie zapewniają: domyślny `requests`, `curl/8.x` lub pełny browser UA (`Mozilla/5.0 (Windows NT 10.0; Win64; x64)...`).
2. **Trap 02: Punctuation Lucene Syntax Break w Search API**
   - Znak ukośnika `/` (np. `Bodo/Glimt`) oraz myślniki w zapytaniu tekstowym psują tokenizator Solr/Lucene i zwracają 0 wyników. Zapytania muszą być czyszczone ze znaków interpunkcyjnych.
3. **Trap 03: Zduplikowane profile sportowców (Stub vs Active ID)**
   - W tenisie istnieją martwe stuby (np. Stojsavljevic ID 12347, Cortez Llorca ID 5092, Roura Llaverias ID 11795) obok aktywnych profili (ID 14877, 10678, 16206). Search v3 często zwraca stub jako pierwszy. Należy używać Search v2 i weryfikować `eventlog`.
4. **Trap 04: Odwrócona kolejność `homeAway` na scoreboardzie tenisa**
   - W 100% zbadanych meczów tenisowych (625 na 625 prób) lista zawodników w obiekcie `competitors` ma kolejność `('away', 'home')`. Pobranie `competitors[0]` jako gospodarza daje 100% błędów atrybucji.
5. **Trap 05: Rozbieżność daty turnieju i meczu w tenisie**
   - `event.date` to data startu turnieju (często 2 tygodnie przed meczem). Data meczu znajduje się wyłącznie w `competition.date`.
6. **Trap 06: Fałszywe mapowanie drużyn młodzieżowych i rezerw**
   - Naiwne usuwanie tokenów `U19/U21/II/B/Reserves` powoduje fałszywe dopasowanie do pierwszych drużyn seniorów (np. Barcelona U19 -> Barcelona).
7. **Trap 07: Brak endpointu `/summary` w tenisie**
   - Endpoint `/summary` dla tenisa zwraca HTTP 400. Dane o setach i gemach muszą być czytane ze scoreboardu.
8. **Trap 08: Brak metryk xG i trajektorii boiskowych**
   - ESPN nie udostępnia wskaźników Expected Goals ani współrzędnych strzałów w tablicy `plays`.
9. **Trap 09: Parametr paginacji w Core API**
   - Core API wymaga parametru `page=N`. Parametr `pageIndex=N` jest ignorowany i powoduje zapętlenie na stronie 1. Maksymalny `limit` to 1000.
10. **Trap 10: Martwe katalogi ligowe**
    - Ze 218 lig piłkarskich tylko 88 zwraca rzeczywiste kluby. Pozostałe 130 zwraca kod HTTP 200 z pustą listą `teams: []`.
11. **Trap 11: Brak endpointu `vsathlete` w tenisie**
    - `athletes/{id}/vsathlete/{opp_id}` zwraca HTTP 404. Bilans H2H musi być wyliczany lokalnie z przecięcia `eventlogów`.
12. **Trap 12: Wyniki rzutów karnych w piłce nożnej**
    - Pole `score` odzwierciedla wynik po 120 minutach (np. 0-0). Wynik serii rzutów karnych znajduje się w `shootoutScore` (np. 5 vs 3), a status to `STATUS_FINAL_PEN`.
13. **Trap 13: Krecz i walkower w tenisie**
    - Walkower (`STATUS_WALKOVER`) ma puste linie punktowe. Krecz (`STATUS_RETIRED`) zawiera częściowy wynik i dopisek `ret` w notatce.
14. **Trap 14: Przenormalizowanie nazw klubów**
    - Usunięcie słów ogólnych („United”, „City”) zrównuje Manchester United i Manchester City do jednego tokenu „manchester”.
15. **Trap 15: Przesunięcie doby UTC vs czas lokalny**
    - Mecze rozgrywane późnym wieczorem czasu lokalnego (np. 23:00 UTC w Nowym Jorku) w Europie odbywają się dnia następnego (01:00 CEST). Walidator dat musi dopuszczać okno $\pm 1$ dnia.
