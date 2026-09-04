# Plan: konsolidacja źródeł danych

**Stan:** v3, gotowy do wdrożenia · **Baza:** `runs/2026-09-04/`, `main` @ `4f0d85cf`
· Poprzednie wersje (v1, v2 z pełnym audytem i trzema przeglądami) w historii gita.

## Cel

| sport | discovery | enrichment |
|---|---|---|
| **piłka** | tylko `bzzoiro` | `bzzoiro` + `espn-football` |
| **tenis** | tylko `odds-api` | `espn-tennis` + `tennis-abstract` **tylko** dla asów i podwójnych błędów |

Dwie decyzje projektowe, które upraszczają całość:

- **`espn-tennis` NIE zostaje `PRIMARY_PROVIDER_BY_SPORT`.** Ta tabela to bramka
  cenowa, nie etykieta: `context_flags.py:420` i `bet_builder_draft.py:1023`
  czytają samą przynależność, więc dopisanie tenisa zdejmuje zakaz CALL-i
  tenisowych na wszystkich 452 wierszach — a backtest nie czyta rozliczeń
  tenisowych, więc nie da się tego sprawdzić. Architektura powyżej stoi bez tego.
- **Rodzina `_for` z ESPN w piłce (rożne, faule) jest poza zakresem.** Zmierzona
  korzyść korelacji to `+0.4pp, CI [−2.3, +3.4]` (docstring `tier_for_row`, na tej
  podstawie usunięto ją kiedyś z reguły CALL), a ryzyko realne — patrz pułapka 3.
  Wyjątkiem są **gole**, bo tam zero jest prawdziwym zerem (krok 5).

---

## Kroki, w tej kolejności

Kolejność nie jest dowolna. Kroki 2-3 muszą wyprzedzić 4, a 5 musi wyprzedzić 6.

### 1. Discovery piłki tylko z bzzoiro

**Dlaczego:** `SlateGate` i tak odrzuca każdy mecz bez wiersza bzzoiro — 297 z 342
na 2026-09-04. Odkrycie, którego nie da się wzbogacić, to szum w artefakcie.

**Gdzie:** [discover.py:796-800](../src/bet/simple_stats/discover.py#L796) (lista
adapterów) + [`_fetch_source_events`](../src/bet/simple_stats/discover.py#L599).

```python
# `.get(sport, ())`, nie `[sport]`: --sports jest wolnym tekstem bez argparse
# choices, a OddsAPIEventsAdapter deklaruje też basketball i hockey.
DISCOVERY_SOURCES_BY_SPORT = {
    "football": ("bzzoiro",),
    "tennis": ("odds-api",),   # JEDYNE źródło terminarza tenisa: 15/15 wydarzeń
}
```

Warunek: `sport in source.supported_sports` **i** `source.name in
DISCOVERY_SOURCES_BY_SPORT.get(sport, ())`. **Adaptery nadal konstruujemy** —
lista jest czytana drugi raz przy budowie `source_errors` ([:802](../src/bet/simple_stats/discover.py#L802)).

**Ryzyko cenowe: zero.** Nie tyka żadnej próbki. Oczekiwany wynik harnessu:
zero wierszy z ruchem `p_central`.

### 2. Powierzchnia i format tenisa po `tournamentId`

**Dlaczego tutaj:** to ten krok usuwa zależność espn-tennis od tennis-abstract
jako dawcy — bez niego krok 4 pustoszy największy rynek tenisowy.

**Co jest zepsute:** `config/tennis_surface_map.json` ma 10 wpisów (same Szlemy),
pin po nazwie rozgrywek. Skutek: **3 z 22 tournamentId** mają powierzchnię,
336 z 536 obserwacji nie ma. Reguła jest fail-open, więc próbka miesza korty
twarde, ziemne i trawiaste w milczeniu — awaria Boulter–Muchova, którą ten plik
cytuje jako własne uzasadnienie.

`surface` i `match_level` mają **wspólne źródło**: ustawione na dokładnie 200/536,
NULL na 336, zero przypadków mieszanych. Jedna poprawka naprawia oba.

**Zakres:**
1. Tabela kluczowana po `tournamentId` (obecnym na **536/536** obserwacji) obok
   tabeli nazw, która zostaje dla tennis-abstract (ono id nie podaje).
2. **Lewa strona porównania też.** `scope_values` odrzuca na
   `pv.surface != surface` ([analyze.py:865](../src/bet/simple_stats/analyze.py#L865)),
   a lewy operand idzie z `tennis_surface(competition)` — z nazwy od odds-api.
   Otagowanie prawej strony przy nietkniętej lewej zostawia filtr, który nie
   odpala nigdy. Albo most nazwa→`tournamentId`, albo jawna decyzja, że
   poprawiamy tylko prawą stronę.
3. `tournament_id = comp.get("tournamentId") or event.get("id")`
   ([espn.py:1138](../src/bet/api_clients/espn.py#L1138)) — fallback na id
   **wydarzenia**, per-turniej-per-rok. Kluczować **tylko** po realnym
   `tournamentId`, brak → `data_gap`.
4. Nieznane zostaje nieznane (żadnego zgadywania z miasta), ale przestaje być
   ciche.

### 3. `games_won` per zawodnik z espn-tennis

**Co jest zepsute:** `games_won` i `sets_won` są w surowej odpowiedzi jako
`{'home': x, 'away': y}` ([espn.py:1104-1105](../src/bet/api_clients/espn.py#L1104)),
a `_combined_from_dict_stats` sumuje strony — więc gierki **zawodnika**, czyli
rynek 190 z 452 wierszy, są wyliczane i wyrzucane.

```python
_SIDE_SPLIT_PROVIDERS = frozenset({"espn-tennis"})

# Nazwa per-strona podana WPROST, nie z sufiksu: kanoniczna metryka nazywa się
# `games_won` (tak ją już wydaje tennis-abstract). `total_games_for` NIE ISTNIEJE
# w słowniku. `sets_won` też nie jest kanoniczne (brak w COUNT_METRICS,
# w _TEAM_MARKET_STAT_TO_CANONICAL i w ofercie) — dlatego go tu nie ma.
_SIDE_SPLIT_AS = {"espn-tennis": {"total_games": "games_won"}}
```

Emisja **dodatkowa**, nie podmiana: `total_games` zostaje sumą, `games_won`
dochodzi obok. `side is None` → nie dopisujemy nic. Emisja **po**
`_tennis_match_unfinished` i `_is_absent_not_zero`, żeby krecz nie wszedł do
próbki. Ścieżka `h2h` nie jest objęta (nie ma `side` z założenia).

Oczekiwana korelacja: **`AGREE` albo `PARTIAL_AGREE`** — espn-tennis zwraca ~4-5
meczów przeciw dziesięciu tennis-abstract, a `AGREE` wymaga udziału ≥0,5.
`PARTIAL_AGREE` jest tu poprawnym wynikiem, nie porażką.

### 4. tennis-abstract zawężony do asów i podwójnych błędów

**Bezpieczne dopiero po 2 i 3.** `_row_match_level` mówi to sam:
*„`_share_within_a_match` can still recover it from tennis-abstract's `level`
for the same match"* — tennis-abstract jest nazwanym dawcą powierzchni i formatu.

**Zakres: tylko tabela aliasów** (`_TENNIS_MATCH_STAT_ALIASES`). `first_serve_pct`
i `break_points_faced` zostają w dossierze jako wejście analityczne, nie wychodzą
do arkusza (nie są żadnym oferowanym rynkiem).

**Czego nie wolno:**
- **Nie ruszać `PROVIDERS_BY_SPORT["tennis"]`.** To kolejka pracy, nie lista
  „niepodstawowych" — `_build_tasks` iteruje wyłącznie ją
  ([enrich.py:169](../src/bet/simple_stats/enrich.py#L169)). Usunięcie stamtąd
  espn-tennis znaczy, że nie zostanie odpytany wcale, a pochodne
  `_TENNIS_PROVIDERS` ([providers.py:742](../src/bet/simple_stats/providers.py#L742))
  wyłączają ochronę przed kreczami — krecz przy 7-6 6-7 1-0 jest 27 gierek długi
  i schlebia UNDER.
- **Nie usuwać `total_games` ani `games_won`** z tennis-abstract. Pierwsze to
  jedyna kontrola transkrypcji tenisa, drugie to zapas dawcy na wypadek, gdyby
  krok 2 nie domknął pokrycia. Duplikat jest tu funkcją, nie odpadem.

### 5. Gole z ESPN — osobny commit

**Dlaczego przed 6:** highlightly jest dziś **jedynym** korelatorem rodziny goli
(159 wierszy: `goals_for` 81 AGREE + 6 PARTIAL, `goals_total` 48 AGREE + 24
PARTIAL). Bez tego kroku krok 6 zabiera kontrolę i nic jej nie zastępuje.

**Dlaczego to tanie:** espn-football emituje 0 goli z **dwóch** powodów.
`_parse_espn_score` jest zepsute (ESPN zwraca dwa stringifikowane słowniki
połączone myślnikiem, pierwszy `-` wypada w URL-u) — ale drugi powód wystarcza
naprawić: `_ESPN_FOOTBALL_ALIASES` **nie ma wpisu `goals`**, choć surowy dict
nosi `'goals': {'home': 1.0, 'away': 4.0}`. Jedna linia:

```python
_ESPN_FOOTBALL_ALIASES["goals"] = "goals_total"
```

`goals_for`/`goals_against` wymagają podziału na strony — **i to jedyna rodzina,
gdzie jest to bezpieczne**, bo zero w golach jest prawdziwym zerem
([providers.py:2010-2013](../src/bet/simple_stats/providers.py#L2010)). Można je
dodać przez ten sam `_SIDE_SPLIT_AS` (wpis dla `espn-football`).

**Osobny commit i weryfikacja przed krokiem 6:** dwie zmiany rodziny goli w
jednym runie są nieprzypisywalne. Sprawdzić, że gole ESPN zgadzają się z bzzoiro,
zanim highlightly odejdzie.

### 6. Usunięcie highlightly z ENRICH

`NATIVE_ID_PROVIDERS_BY_SPORT["football"]`: `("highlightly", "bzzoiro")` →
`("bzzoiro",)` ([providers.py:91-93](../src/bet/simple_stats/providers.py#L91)).
Klient i tabele aliasów zostają nieużywane, jak sportdb i api-football.

**Dlaczego to jest tanie:** highlightly wnosi ponad bzzoiro dokładnie jedną
metrykę — `expected_goals_total` — która ma 0 wierszy w arkuszu i jest wykluczona
w [analyze.py:493](../src/bet/simple_stats/analyze.py#L493). Dotknęła 6 dossierów
przy 100/100 zużytej kwoty.

Sprawdzić, że `preflight.py` nie wymaga highlightly do GO.

### 7. Monitoring i odbiór

**Pusty sport musi obniżyć werdykt.** `out.error()` dopisuje tylko do `_issues`
([agent_output.py:117](../scripts/agent_output.py#L117)) — trzeba **trzeciego
członu** w wyrażeniu werdyktu:

```python
by_sport = Counter(e.sport for e in active)          # Counter wymaga importu
empty = [s for s in (sports or ["football","tennis"]) if not by_sport.get(s)]
for s in empty:
    out.error(f"SPORT_EMPTY: {s}: discovery returned no ACTIVE events", recoverable=True)
metrics["events_by_sport"] = dict(by_sport)
verdict = "OK" if (persisted and not blocked and not result.degraded_reasons
                   and not empty) else "PARTIAL"
```

To nie jest teoretyczne: wszechświat tenisowy OddsAPI to 44 klucze turniejowe
(22 ATP na ~60+ turniejów w sezonie), dziś aktywne 2 — są tygodnie z zerem.

**Podłoga pokrycia zamiast `SLATE_CRITICAL_SOURCES`.** Nie dopisywać tam bzzoiro
ani odds-api: `_degraded_reasons` promuje **wyłącznie** komunikat zawierający
literał `"quota exhausted"` ([discover.py:823-836](../src/bet/simple_stats/discover.py#L823)),
a bzzoiro nie ma dziennego limitu, a `/events` odds-api kosztuje 0 kredytów.
Zamiast tego: podłoga liczby zdarzeń ACTIVE per sport wobec kroczącej mediany
N poprzednich runów — artefakty są już w `runs/`, zero wywołań do providera.

---

## Pułapki — sprawdzić każdą przed commitem

1. **`PROVIDERS_BY_SPORT` to kolejka pracy.** Usunięcie z niej providera znaczy,
   że nie zostanie odpytany. Pochodne: `_TENNIS_PROVIDERS` (ochrona przed
   kreczami), `NAME_DRIVEN_PROVIDERS`, `_TENNIS_PROVIDERS` w teście weryfikacji
   providerów.
2. **`PRIMARY_PROVIDER_BY_SPORT` to bramka cenowa.** Nie dopisywać tenisa
   (patrz „Cel").
3. **ESPN emituje `0.0` per strona dla tego, czego nie ma.** Zweryfikowane:
   `'corners': {'home': 16.0, 'away': 0.0}` w meczu, gdzie strona wyjazdowa miała
   11 strzałów i 4 gole. `_representative` używa `median_low`, więc to zero
   wygrywa i zawyża `p_central` → `min_acceptable_odds` spada. `p_low` i `hits`
   są chronione, **bar nie**. Dlatego rożne i faule z ESPN są poza zakresem, a
   gole (gdzie zero jest prawdziwe) nie.
4. **Obserwacje espn-football są odporne na `scope_values`:** `competition_id` i
   `season_id` na **0 z 2385**. STALE_SEASON i pin na sparingi nie mogą odpalić.
   Gorzej — `scope_values` biegnie przed `_one_per_day`, więc wiersz ESPN może
   **przeżyć** wiersz bzzoiro słusznie odrzucony jako STALE_SEASON. Dotyczy
   kroku 5: uzupełnić te pola albo zaakceptować, że gole ESPN nie są zakresowane.
5. **`best_of` z `format.regulation.periods` jest odrzucone.**
   [espn.py:1140-1149](../src/bet/api_clients/espn.py#L1140): `periods=5` dla
   **damskiego** singla US Open i dla Monte-Carlo. Test
   `test_the_match_format_is_not_read_off_the_scoreboard` to pilnuje.
6. **`espn.py:1106` wpisuje `total_sets` identycznie po obu stronach** — mina dla
   każdego, kto rozszerzy `_SIDE_SPLIT_AS`.
7. **Zmiany parsowania (2, 3, 5) nie są czyste do wycofania.**
   `betting/data/stats_cache` ma 1,4 GB i skan tenisowy ESPN jest zapisywany dla
   każdego sparsowanego meczu — wynik zależy od wieku cache'u. Bump wersji
   schematu albo `rm -rf betting/data/stats_cache/espn`, **jako część zmiany**.
   Kroki 1 i 6 są czyste (jedno słowo w krotce).

---

## Odbiór

**Bramka główna — harness różnicowy.** Przebudować dzień z tych samych artefaktów
(`/rebuild-coupon`) i zróżnicować wiersz w wiersz po
`(event_id, market, line, direction)`:

- ile wierszy ruszyło `p_central` o >0,02
- ile zmieniło `tier`, w każdym kierunku
- ilu spadł `min_acceptable_odds`
- histogram `sample_excluded` per powód
- różnica samego kuponu

Wszystkie kryteria zliczające przechodzą, gdy jakość spada — dlatego to jest
bramka, a nie dodatek. **Dla kroku 1 wartość oczekiwana: zero poruszonych
wierszy.** Dla 2, 3, 5: nazwana, przejrzana lista.

**Regresy do sprawdzenia (baza → po):**

| | baza 2026-09-04 | po |
|---|---|---|
| wydarzenia piłkarskie / tenisowe w `event_list` | 342 / 15 | ≈45 / **15** |
| `no_primary_identity`, **per sport** | 297 piłka, 0 tenis | 0 / **0** |
| dossiery `READY` | 23 | ≥23 |
| wiersze `aces_*` + `double_faults_*` | 112 | **112** |
| wiersze `games_won` z `espn-tennis` | 0 | >0 |
| obserwacje espn-tennis z `surface` | 200/536 | ≥95%, braki nazwane |
| `games_won` z `match_level is None` pod męskim Szlemem | — | nie rośnie |
| wiersze goli z korelatorem | 159 (highlightly) | ≥159 (ESPN) |
| tier tenisa `CALL` | 0 | **0** |
| duplikat Athletic Club / Vila Nova | 2 `event_id` | 1 |

**Testy uruchamiać po ścieżce** (`pytest tests/simple_stats/`), nie `pytest` bez
argumentów: całe repo kończy `5415 tests collected, 23 errors` → `Interrupted`
i nie wykonuje niczego (sprawdzone 2026-09-04, patrz
`test-suite-blocked-at-collection`). Ścieżkowo jest zielone: 2704 testy.

**Testy, które te zmiany złamią:**

| test | plik | krok |
|---|---|---|
| `test_the_two_providers_report_the_same_quantity_for_total_games` | `test_tennis_sources.py` | 3 |
| `test_pinned_competitions_resolve`, `test_only_surface_bearing_providers_record_it` | `test_tennis_surface_scope.py` | 2 |
| `test_the_real_configs_on_disk_load` | `test_config_robustness.py` | 2 |
| `test_tennis_still_has_two_independent_providers` | `test_tennis_providers.py` | 4 |
| `test_providers_for_covers_both_name_and_native_id_families`, `test_thin_quota_is_warned_about_before_the_run` | `test_preflight.py` | 6 |
| `test_football_paired_stats_still_use_the_paired_combiner` | `test_providers.py` | 3, 5 |
| `test_every_gate_reason_has_a_kind`, `test_gated_events_are_reported_as_blocked_with_the_reason` | `test_enrich.py` | 7 — **pominięcie powoduje żywe wywołanie sieciowe** |

Nowe testy: suma vs jedna strona (`total_games` / `games_won`), roster discovery
per sport z `.get()`, domknięcie rachunku per sport w DISCOVER.

---

## Dokumenty do poprawy w tym samym commicie

Wczytywane do agentów w czasie działania — inaczej będą wprowadzać w błąd:

- `.claude/skills/tennis-analysis/` — `references/data-inventory.md:20-21, 91-93, 148`,
  `SKILL.md:8-14, 132-137`, `event-protocol.md:91` (czyni środek pooled z
  `total_sets` obowiązkowym powodem veta — krok 3 to zmienia)
- `.claude/skills/football-analysis/references/market-playbook.md:86, 127`
- `.claude/agents/bet-analyst-tennis.md:3, 45-46, 72`;
  `.claude/agents/bet-simple.md:75, 169, 217-224, 269-279` (dodać `SPORT_EMPTY`)
- `.claude/commands/run-day.md:45, 49-66, 85-91, 306-312`
- `docs/SIMPLE_STATS_RUNBOOK.md:300-303, 694-695, 802-810, 840-849, 879-889`;
  `docs/MORNING.md:19, 27, 44, 59, 64`
- Docstringi będące źródłem prawdy: `providers.py:69-93`, `:95-125`, `:862-880`,
  `:988-1000`, `contracts.py:305-311`, `enrich.py:772-788`
- Pamięci: `highlightly-drives-discovery` (nieaktualna dla piłki),
  `provider-capability-map` (*„the fix is almost always highlightly quota"*),
  `surface-contamination-and-friendly-leak:52-60`

---

## Czego ten plan **nie** daje

**Pokrycia.** Piłka zostaje na 45 meczach z 342, bo katalog bzzoiro to 83 ligi —
i nic tu tego nie podnosi. Tenis zostaje na 15, bo OddsAPI ma 44 klucze
turniejowe. Plan czyni dane poprawnie zakresowanymi i uczciwie raportowanymi;
nie zwiększa ich ilości.

Trzy niezbadane dźwignie pokrycia, poza zakresem: **(a)** `api-football`
(zawieszone) i `sportdb` (402) — problem rozliczeniowy, nie techniczny, klienci
zostali w repo; **(b)** tablica Superbeta jako źródło discovery tenisa — już
pobieramy 299 wydarzeń tenisowych z nazwami i kickoffem przeciw 15 od OddsAPI;
**(c)** płatny tier Highlightly — da `corners_total`/`fouls_total` na całym
slate, ale nigdy per drużyna.

---

## Liczby bazowe (2026-09-04)

357 wydarzeń (342 piłka, 15 tenis) · źródła piłki: highlightly 340, bzzoiro 45,
odds-api 37 · podział piłki: 288 tylko highlightly, 44 hl+bz, 8 hl+oa, 1 bz, 1 oa ·
katalog bzzoiro **83 ligi** (na żywo) · `no_primary_identity` 297 = 342−45,
wszystkie piłka · metryki: bzzoiro 54, highlightly 14 (nadwyżka:
`expected_goals_total`, 0 wierszy), espn-football 9 (nadwyżka: brak) · dossiery
dotknięte: bzzoiro 42, espn 27, highlightly 6 · DISAGREE 86/86 od espn-football ·
wiersze `_for` piłki: 3508 SINGLE_SOURCE, 81 AGREE, 6 PARTIAL (wszystkie
`goals_for`, od highlightly) · espn-football `competition_id`/`season_id`: 0/2385 ·
tenis: 1939 obserwacji (tennis-abstract 1403, espn-tennis 536), `surface`
1403/1403 vs 200/536, `competition_id` 0/1403 vs 536/536, espn po obu stronach
13/15 · arkusz tenisa 452 wiersze, wszystkie z ceną, 0 w kuponie · READY tenisa 0
(sufit `with_two_or_more` = 1 przy progu 3) · ESPN tenis: `statsSource: none`,
`/summary` 400 — asów i podwójnych błędów nie będzie nigdy.

### Komendy

```bash
# rozkład źródeł per sport
python3 -c "
import json; from collections import Counter
el=json.load(open('runs/2026-09-04/2026-09-04_event_list.json'))
for sp in ('football','tennis'):
    e=[x for x in el['events'] if x['sport']==sp]
    print(sp, len(e), Counter(tuple(sorted(x['source_ids'])) for x in e).most_common(6))"

# metryki i zasięg per provider
python3 -c "
import json; from collections import defaultdict
d=json.load(open('runs/2026-09-04/2026-09-04_event_dossiers.json'))
by=defaultdict(set); hit=defaultdict(set)
for e in d['dossiers']:
    for m,b in (e['metrics'] or {}).items():
        for s in ('team_a_l10','team_b_l10','h2h'):
            for o in (b.get(s) or []):
                by[o['provider']].add(m); hit[o['provider']].add(e['event_id'])
for p in by: print(p, len(by[p]),'metryk,', len(hit[p]),'dossierów')"

# pokrycie surface / competition_id per provider (pułapka 4, krok 2)
python3 -c "
import json; from collections import Counter
d=json.load(open('runs/2026-09-04/2026-09-04_event_dossiers.json'))
c=Counter()
for e in d['dossiers']:
    for m,b in (e['metrics'] or {}).items():
        for s in ('team_a_l10','team_b_l10','h2h'):
            for o in (b.get(s) or []):
                c[(o['provider'], bool(o.get('surface')), bool(o.get('competition_id')))]+=1
print(c)"

# sufit ESPN w tenisie
curl -s 'https://sports.core.api.espn.com/v2/sports/tennis/leagues/atp/events/189-2026/competitions/184607' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['statsSource'])"

# surowy podział home/away z ESPN, z zerem które znaczy "nie wiem" (pułapka 3)
python3 -c "
import sys; sys.path.insert(0,'src')
from bet.api_clients.rate_limiter import RateLimiter
from bet.api_clients.espn import ESPNClient
c=ESPNClient(sport='football', league='ned.2', rate_limiter=RateLimiter())
fx=c.get_team_last_fixtures(c.resolve_team_id('Vitesse'), last_n=5)
print(c.get_fixture_stats_result(fx[0]['id']).value[0].stats)"

# wszechświat tenisowy OddsAPI (0 kredytów)
python3 -c "
import os,requests
from pathlib import Path
for line in Path('.env').read_text().splitlines():
    if 'ODDS' in line and '=' in line and not line.strip().startswith('#'):
        k,v=line.split('=',1); os.environ[k.strip()]=v.strip().strip('\"')
key=os.environ.get('ODDS_API_KEY') or os.environ.get('THE_ODDS_API_KEY')
r=requests.get('https://api.the-odds-api.com/v4/sports',params={'apiKey':key,'all':'true'})
tn=[s for s in r.json() if s['key'].startswith('tennis_')]
print(len(tn),'kluczy,',sum(1 for s in tn if s['active']),'aktywnych')"
```
