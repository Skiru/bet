# Plan: League of Legends jako nowy sport

**Stan:** v1, draft — research zakończony, implementacja NIE rozpoczęta.
**Baza:** research w rozmowie 2026-09-14, brak commitów kodu.

## Dlaczego LoL, a nie inne esporty

Cztery kandydaci sprawdzone i odrzucone tego samego dnia, dla porządku:

| Sport | Wolumen na Superbecie dziś | Źródło danych | Werdykt |
|---|---|---|---|
| **CS2** | tylko ligi drugorzędne (CCT Europe, United21, ESEA, Fiesta Series) — jedyne znajome marki to "NAVI Junior"/"Spirit Academy"/"ENCE Prospects", rezerwy, nie główne składy | brak dobrego: HLTV bez oficjalnego API (`gigobyte/HLTV` martwy), Leetify/FACEIT dają dane per-gracz z własnych meczów, nie mecze orga-vs-orga | odrzucony na obu osiach naraz |
| **Dota 2** | 8 meczów, same "EPL League/World Series", "Star Series" — bez majorów/ESL/IEM/DPC | OpenDota: w pełni darmowe i bogate, ale dla prawdziwego pro-Dota — te konkretne ligi raczej nieujęte | odrzucony na wolumenie |
| **Valorant** | 9 meczów, realnie tier-1 (VCT Champions: G2, Liquid, Paper Rex, LOUD, T1) | Riot API: personal/dev key **nie jest wydawany** dla Valoranta (`developer.riotgames.com/docs/valorant`: "Personal Key Applications are currently not supported") — trzeba production key z akceptacją Riota jako partnera esportowego | odrzucony na dostępie, nie na wolumenie — **do rewizji jeśli kiedyś dostaniemy production key** |
| **League of Legends** | 11 meczów, tier-1: LEC (Na'Vi–Movistar KOI), LCS, LPL (JD Gaming, Top Esports), CBLOL | Riot API: match-v5/league-v4/summoner-v4 działają od razu na darmowym dev-key, bez akceptacji partnera | **jedyny kandydat, który przechodzi obie bramki** |

Table tennis (Setka Cup itd.), siatkówka, piłka ręczna sprawdzone we wcześniejszych
turach tej samej rozmowy — też odrzucone (brak darmowego bogatego źródła albo
brak wolumenu). Nie powtarzać tego researchu bez nowego powodu.

## Co dokładnie daje Riot API (dev key, bez akceptacji)

- `match-v5`: pełny match detail — per-gracz KDA, CS, złoto, obrażenia, wardy,
  built items, per-minutowe timeline (`match-v5/timelines`).
- `league-v4`: ranking graczy (nieistotne dla pro-scenowych meczów, ale
  przydatne gdyby kiedyś chcieć statystyk formy solo-queue zawodników).
- `summoner-v4` / `account-v1`: mapowanie nazwa gracza → PUUID, wymagane do
  odpytania `match-v5` per gracz.
- **Ograniczenie regionalne, ważne dla architektury:** `match-v5` i
  `account-v1` żyją pod routingiem kontynentalnym (`americas`/`europe`/`asia`),
  a `summoner-v4`/`league-v4` pod routingiem platformowym (`euw1`, `na1`,
  `kr`, ...). LEC → `europe`/`euw1`, LCS → `americas`/`na1`, LPL i CBLOL →
  `asia`/odpowiednio (LPL nie ma oficjalnego platform-routing dla Chin w
  publicznym Riot API — **do zweryfikowania, ryzyko: brak pokrycia LPL**).
- Riot API **nie ma natywnego pojęcia "mecz ligi pro"** — `match-v5` zwraca
  mecze po PUUID gracza, nie po nazwie turnieju. Trzeba więc: (a) znać
  PUUID-y zawodowych graczy każdej drużyny, (b) filtrować ich historię
  meczów po oknie czasowym i (osobno) po tym, czy to faktycznie mecz ligowy
  a nie solo-queue — Riot nie oznacza tego pola wprost, trzeba wnioskować z
  `gameType`/`queueId` (turnieje pro grane są zwykle na dedykowanym `queueId`
  dla Esports Client, ale to wymaga potwierdzenia per-liga).

To jest największa niepewność planu — nie sprawdziliśmy jeszcze w praktyce,
czy `queueId`/`gameType` faktycznie separuje mecze LEC/LCS/LPL od zwykłego
solo-queue graczy, ani czy Riot w ogóle indeksuje profesjonalne konta
graczy pod tym samym `match-v5` co konta amatorskie (część lig gra na
zamkniętej infrastrukturze Riot Esports, nie na publicznym live-serwerze —
**do zweryfikowania jako krok 0, przed czymkolwiek innym**).

## Jak to się wpina w istniejący pipeline

Wzorzec: piłka ma `bzzoiro` jako `PRIMARY_PROVIDER_BY_SPORT["football"]`
([providers.py:138](../src/bet/simple_stats/providers.py#L138)), tenis nie ma
primary w ogóle (`corroborators_for` traktuje sport bez primary jako "każdy
provider to źródło", patrz [providers.py:141-155](../src/bet/simple_stats/providers.py#L141)).
LoL wygląda architekturalnie jak tenis: jedno źródło (Riot), zero
konkurencyjnego korroboratora na start.

Punkty rozszerzenia, w kolejności, w jakiej trzeba je dotknąć:

1. **`discover.py`**: nowy adapter `RiotLoLEventsAdapter` z
   `supported_sports = ["lol"]`, dodany do
   `DISCOVERY_SOURCES_BY_SPORT` ([discover.py:899](../src/bet/simple_stats/discover.py#L899)).
   Musi produkować terminarz meczów LEC/LCS/LPL/CBLOL — ale Riot API **nie
   ma endpointu "nadchodzące mecze ligi"**, tylko historię rozegranych
   meczów per gracz. Terminarz nadchodzących meczów trzeba wziąć skądinąd
   (np. z samej oferty Superbet, tak jak dziś robi to `--event-list` dla
   piłki/tenisa — patrz [analyze-event-list-is-not-optional] w pamięci) —
   Riot służy tylko do wzbogacania **rozegranych** meczów, nie do discovery
   nadchodzących.
2. **`api_clients/`**: nowy klient `riot.py` (wzorem `espn.py`/`bzzoiro.py`)
   — cienki wrapper nad `match-v5`/`account-v1`/`summoner-v4`, z rate
   limiterem (Riot dev key: 20 req/1s, 100 req/2min — dużo niżej niż
   `bzzoiro`, trzeba policzyć budżet per dzień na ~11 meczów × 10 graczy).
3. **`enrich.py` / `providers.py`**: `STAT_NAME_MAP` dla LoL — jakie metryki
   w ogóle mają sens jako rynek do wyceny? To wymaga osobnej decyzji, bo LoL
   nie ma odpowiednika "rogi"/"gemy" — kandydaci: total kills (mapa), total
   dragon/baron kills, first blood, czas trwania gry, per-gracz KDA/CS. Nie
   zakładać z góry które z nich Superbet w ogóle oferuje jako rynek — trzeba
   to sprawdzić na ofercie, tak jak `superbet-market-matcher` robi to dla
   piłki.
4. **Dopasowanie nazw**: gracze/drużyny LoL nie mają odpowiednika
   `discovery/team_aliases.py` dziś — trzeba zbudować od zera mapę
   nazwa-z-Superbetu → PUUID/nazwa-w-Riot-API. Ryzyko analogiczne do
   [tipster-matcher-vetoed-real-fixtures] i [athletic-club-cannot-match-at-superbet]
   w pamięci: inicjały, skróty, transfery graczy między drużynami w trakcie
   sezonu (Riot API śledzi gracza po koncie, nie po drużynie — trzeba
   osobno śledzić rosters, bo PUUID nie mówi "gra teraz dla X").
5. **Nowy analityk**: wzorem `bet-analyst-football.md`/`bet-analyst-tennis.md`
   ([.claude/agents/](../../.claude/agents/)) — `bet-analyst-lol.md` + skill
   `lol-analysis` (wzorem `football-analysis`/`tennis-analysis` w
   [.claude/skills/](../../.claude/skills/)), bo `bet-simple` deleguje czytanie
   per-sport do dedykowanych analityków, nie robi tego samo.
6. **Rozliczenie (`settle.py`)**: LoL potrzebuje własnej logiki
   rozstrzygania wyniku (kto wygrał mapę/mecz Bo1/Bo3/Bo5 — formaty różnią
   się między LEC play-in a playoffami), analogicznie do tego jak tenis ma
   osobne rozliczanie setów/gemów.

## Kroki, w tej kolejności

### 0. Weryfikacja techniczna (zanim cokolwiek innego)

Zarejestrować dev key na `developer.riotgames.com`, odpytać `match-v5` dla
znanego gracza jednej z drużyn LEC dziś grających, i potwierdzić:
- czy w ogóle widać jego profesjonalne mecze (czy Riot Esports gra na
  publicznie odpytywalnej infrastrukturze),
- czym różni się `queueId`/`gameType` meczu pro od solo-queue,
- realny rate limit konta deweloperskiego (dokumentacja bywa nieaktualna).

Jeśli to się nie potwierdzi, cały plan pada na starcie — **to jest bramka,
nie formalność**.

### 1. Terminarz: skąd biorą się nadchodzące mecze

Riot nie daje terminarza. Albo scrapować oficjalną stronę `lolesports.com`
(ma własne, nieoficjalne, ale stabilne API — `esports-api.lolesports.com`,
używane przez ich własny klient webowy, **nie sprawdzone w tej rozmowie —
do zbadania jako część kroku 0**), albo iść tak jak dziś: terminarz z oferty
Superbet, wzbogacenie z Riot.

### 2. Rynki: co Superbet w ogóle oferuje na LoL

Sprawdzić ofertę (`superbet-market-matcher`-style) na kilku dniach: total
kills, handicap na kille, first blood/dragon/baron, total czasu gry,
ewentualnie mapy w Bo3/Bo5. Bez tego kroki 3-4 nie wiedzą, co w ogóle mierzyć.

### 3. Klient Riot + mapowanie nazw

`api_clients/riot.py` + tabela alias nazwa-Superbet → PUUID, budowana
ręcznie na start (11 meczów/dzień to mała, ręcznie weryfikowalna lista, nie
trzeba fuzzy-matchingu od razu — [dedup-one-club-one-instant] i
[a-surname-was-read-as-a-retirement] w pamięci uczą, żeby nie budować
automatycznego dopasowania nazw bez ręcznej weryfikacji na małej próbce
najpierw).

### 4. Enrichment + STAT_NAME_MAP dla LoL

Dopiero po kroku 2 (wiadomo co mierzyć) i 3 (jest skąd wziąć dane).

### 5. Analityk + skill

`bet-analyst-lol.md` + `lol-analysis` skill, wzorem tenisa — dopiero gdy
enrichment produkuje realne wiersze do przeczytania.

### 6. Rozliczenie

Format meczu (Bo1/Bo3/Bo5) per faza turnieju, osobno per liga — bez tego
backtest ([backtest-settles-the-arguments] w pamięci) nie może nic
powiedzieć o jakości.

## Co zostaje poza zakresem na start

- **Valorant** — zablokowany na dostępie do API, nie na wolumenie; rewizja
  jeśli kiedykolwiek dostaniemy production key.
- **LPL (Chiny)** — realne ryzyko braku pokrycia w publicznym Riot API
  (inna infrastruktura regionalna); traktować jako "być może odpada" do
  potwierdzenia w kroku 0, nie planować na niego enrichmentu z góry.
- **Rynki gracza (KDA, CS per gracz)** — dopiero po tym jak total
  kills/handicap na mapę udowodni się jako warte budowania; nie budować
  wszystkiego na raz.
