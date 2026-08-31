# Plan naprawy: bogata obsługa statystyk piłkarskich

**Autor:** sesja 2026-08-31 · **Stan:** do implementacji
**Punkt odniesienia:** `runs/2026-08-31/` (run `simple_stats-2026-08-31-T042018Z-1489661a`)

Wszystkie liczby w tym dokumencie pochodzą z tego runu i z odczytu kodu, nie z
pamięci. Każda teza ma adres w pliku.

---

## 1. Co jest naprawdę zepsute

### 1.1 Kupon jest wybierany przez skrypt, który nigdy nie widział analizy

To jest przyczyna numer jeden i nie jest to problem danych.

`.claude/commands/run-day.md` ustawia kolejność: **Krok 4** buduje kupon
(`build_coupons.py`), **Krok 5** uruchamia `bet-analyst`. Analityk nie ma
narzędzia Write (celowo — nie może przepisywać artefaktów, które ocenia). Efekt:

* kupon powstaje z czystego sortowania po `p_low` ([coupons.py:307](../src/bet/simple_stats/coupons.py#L307)),
* cała praca kontekstowa analityka — sędzia, kontuzje, tabela, xG, pogoda —
  ląduje wyłącznie w prozie `analiza.md`,
* jedyny kanał zwrotny to ręczne skreślenie wiersza (dziś: 2 single Birrell –
  Marčinko, opisane w nagłówku pliku kuponowego).

Analityk **jest najmocniejszym elementem systemu**. W dzisiejszej analizie sam
dociągnął `get_standings` (bo `season_form` było puste), rozpoznał sędziego z
próbą 3 meczów jako bezwartościowego, wypisał sześciu kontuzjowanych Platense z
datami powrotu, złapał zawieszony mecz US Open. Ta praca nie ma żadnego wpływu
na to, co trafia do kuponu.

### 1.2 Katalog rynków vs. to, co Superbet realnie wystawia

Superbet Bet Builder / SUPERBETS (ze zrzutów operatora, 2026-08-30):

| Noga na ekranie | Kanoniczna nazwa | Stan |
|---|---|---|
| `Real Madryt – liczba goli pow. 1.5` | `goals_for` | **metryka nie istnieje** |
| `Liczba goli pow. 1.5` (mecz) | `goals_total` | rynek zdefiniowany w [market_ranking.py:164](../src/bet/stats/market_ranking.py#L164), metryka nigdy nie zbierana → 0 wierszy |
| `2. połowa – liczba goli pow. 0.5` | `goals_2h_total` | **brak rodziny półmeczowej** |
| `Real Madryt – rzuty rożne pow. 6.5` | `corners_for` | rynek jest, siatka `[3.5, 4.5, 5.5]` — **6.5 poza siatką** |
| `Celne strzały Real Madryt pow. 6.5` | `shots_on_target_for` | siatka `[2.5, 3.5, 4.5, 5.5]` — **6.5 poza siatką** |
| `Liczba rzutów rożnych pow. 7.5` (mecz) | `corners_total` | siatka `[8.5…11.5]` — **7.5 poniżej podłogi** |
| `Każda z drużyn pow. 1.5 celnych` | — | **typ rynku nie istnieje** |
| prop na zawodnika | `player_*` | kod gotowy, `player_props: false` w runie |

Dodatkowo zbierane i nigdy niewyceniane (46–52 dossier każde):
`offsides_total`, `red_cards_total`, `shots_off_target_total`,
`blocked_shots_total`, `possession`. Oraz `shots_total` — metryka jest w 52
dossierach i w `PRIORITY_METRICS`, ale **piłkarska lista `STANDARD_MARKET_LINES`
nie ma rynku „Shots Total"**, więc żaden wiersz nie powstaje.

### 1.3 Nie mamy ceny dla rynków, które wyceniamy — poza jednym

`MARKET_CODES` ([contracts.py:522](../src/bet/simple_stats/contracts.py#L522)) to
zamknięty enum feedu bzzoiro. **Nie ma w nim kartek, fauli ani strzałów celnych.**
Cztery z pięciu dzisiejszych rodzin piłkarskich nie mogą nigdy dostać ceny.

Co feed ma naprawdę, zweryfikowane w dzisiejszym artefakcie:

| Rodzina | Kurs | Model | Dziś wierszy |
|---|---|---|---|
| `total_corners` | tak (926 kwot.) | `prob_corners_over_85/95/105` | 416 |
| `over_under_05/15/25/35` (gole) | **tak (1 895 kwot.)** | **`prob_goals_over_15/25/35`** | **0** |
| `btts` | tak (1 450) | `prob_btts_yes` | 0 |
| `total_red_cards` | w enumie | — | 0 |
| kartki / faule / strzały | **nie istnieje** | **nie istnieje** | 1 728 |

Wniosek: **gole to jedyna nowa rodzina, która wnosi cenę.** Bez ceny nie da się
policzyć przewagi, a bez przewagi sortowanie po `p_low` zawsze wypchnie na górę
najnudniejszy rynek dnia. Dlatego gole idą pierwsze, przed wszystkim innym.

### 1.4 Pokrycie: 73% piłki nie dojechało na arkusz

```
302 odkryte → 192 piłkarskie → 52 z wierszami
by_readiness (po backfillu): READY 27 / PARTIAL 128 / BLOCKED 147
```
Z `data_gaps`: 118 × „no provider returned any data", 150 × „highlightly: run
budget exhausted", 170 × „sportdb: HTTP 402", ESPN nie rozwiązał **67.7%**
fixture'ów (58 z 82 nazw lig). `season_form` = **0/192**, bo wymaga `league_id`
z `fixture_context`, a ten mają tylko mecze odkryte przez bzzoiro — **25/192**.
Sędzia: **24/192**.

### 1.5 Sortowanie po `p_low` premiuje nudę

`MIN_SINGLE_P_LOW = 0.50`, sortowanie `(_is_trivial_under, -p_low, event_id)`.
`TRIVIAL_UNDER_MAX_LINE = 1.5` łapie tylko linie ≤1.5 — UNDER 5.5 kartki w
Veikkausliidze nie jest „trywialny" wg tej definicji, a rynek wycenia go ~1.20.
Aston Villa – Arsenal ma dziś dossier READY, dwa źródła i 92 wiersze
(`cards_total 5.5 UNDER 18/20 p_low 0.699`) i nie ma szans z `21/21 p_low 0.845`.

---

## 2. Zasady, których plan nie narusza

Te reguły są egzekwowane przez kontrakty i testy. Żadna faza ich nie zmienia.

1. **Brak kursu łącznego.** `BetBuilderDraft.combined_price` jest typu `None`.
2. **Brak EV, brak stawek, brak automatycznego zakładu.**
3. **Kontekst (sędzia, kontuzje, forma, ranga) nigdy nie wchodzi do `p_low`.**
   Może degradować, nigdy nie promuje. To zostaje — zmienia się tylko to, że
   degradacja przestaje być prozą, a staje się polem w artefakcie.
4. **Bez interpolacji między liniami.** OVER 10.5 nie jest dowodem o 11.5.
5. **Żaden kurs z feedu nie jest kursem Superbetu** — w feedzie nie ma superbetu.
6. **Awans wymaga dwóch liczb** (model + rynek). Jedna nie wystarcza.
7. **Awaria dostawcy to `data_gap`, nigdy wyjątek.**

---

## 3. Fazy

### Faza 0 — siatka bezpieczeństwa (0.5 dnia) · warunek wejścia dla reszty

Każda kolejna faza zmienia liczbę wierszy w arkuszu, więc bez punktu odniesienia
nie da się odróżnić poprawy od regresji.

* Zamrozić `runs/2026-08-31/2026-08-31_event_dossiers.json` jako fixture
  (`tests/fixtures/simple_stats/dossiers_2026-08-31.json`, przycięty do ~12
  meczów: 3 duże ligi, 3 fińskie/szwedzkie, 3 tenis, 3 BLOCKED).
* `scripts/simple/diff_stats_sheet.py` — replay ANALYZE na zamrożonym dossierze,
  diff wierszy wg klucza `(event_id, market, line, direction, team_name,
  player_name)`; wypisuje dodane / usunięte / zmienione `p_low`.
* Zapisać baseline testów **jako zbiór nazw**, nie liczbę (patrz
  `test-suite-baseline`: 73/161 to znane, wcześniejsze awarie).

**Gotowe, gdy:** `diff_stats_sheet.py` na niezmienionym kodzie daje pusty diff.

---

### Faza 1 — gole (1.5 dnia) · zero nowych zapytań · **największy zwrot**

#### 1a. Zbieranie
`src/bet/simple_stats/providers.py`, `fetch_bzzoiro_history` (~linia 1833):

W pętli po `matches`, **przed** `run_budget.try_consume` i przed pobraniem
`/stats/`, wyciągnąć `match["score"]` (już znormalizowane przez
`_normalize_event_row`, [bzzoiro.py:1769](../src/bet/api_clients/bzzoiro.py#L1769)):

```python
score = match.get("score") or {}
h, a = score.get("home"), score.get("away")
if h is not None and a is not None:
    goal_values = {"goals_total": float(h) + float(a)}
    if mode != "h2h" and side is not None:      # side = "home"/"away" tej drużyny
        goal_values["goals_for"]     = float(h if side == "home" else a)
        goal_values["goals_against"] = float(a if side == "home" else h)
    for name, value in _make_values("bzzoiro", match_id, match_date, opponent, goal_values).items():
        outcome.add(name, value)
```

Uwaga implementacyjna: dziś `side` jest wyliczane dopiero po pobraniu `/stats/`.
Trzeba je policzyć wcześniej — zależy tylko od `home_id`/`away_id`, które już są.

**Decyzja projektowa (świadoma):** gole emitujemy **niezależnie od tego, czy
`/stats/` coś zwróciło**. Dziś 12 meczów miało „8 z 10 h2h bez opublikowanych
statystyk" — te mecze mają wynik i nie mają statystyk. Konsekwencja: `n` dla goli
będzie **większe** niż dla rożnych w tym samym meczu. To nie jest błąd —
`sample_size` jest już per-wiersz i różne per-rynek (dziś `corners_total` n=21 vs
`cards_for` n=9 w tym samym meczu). Wymaga jednego akapitu w `bet-analyst.md`.

`goals_against` jest zbierane, ale w Fazie 1 **nie dostaje rynku** — Superbet nie
wystawia „goli straconych". Trafia do dossiera jako materiał dla Fazy 5.

#### 1b. Kontrakty
`contracts.py`: `COUNT_METRICS += {"goals_total", "goals_for", "goals_against"}`.
`PRIORITY_METRICS["football"]` — **nie ruszać w tej fazie** (patrz Faza 2.4).

#### 1c. Rynki i linie
`market_ranking.py`, `STANDARD_MARKET_LINES["football"]`:
* `Goals Total`: `[1.5, 2.5, 3.5]` → `[0.5, 1.5, 2.5, 3.5, 4.5]`
* nowy `{"market": "Team Goals", "lines": [0.5, 1.5, 2.5], "stat": "goals", "is_combined": False}`

`analyze.py`: `_MARKET_STAT_TO_CANONICAL["goals"]` już wskazuje `goals_total`;
dodać `_TEAM_MARKET_STAT_TO_CANONICAL["goals"] = "goals_for"`.

`coupons.py` `MARKET_LABELS`: `"goals_total": "gole (mecz)"`, `"goals_for": "gole drużyny"`.
`market_ranking.py` `MARKET_PL`: `"Team Goals O/U": "Bramki drużyny"`.

#### 1d. Sygnał rynkowy dla goli — trzy pułapki

**Pułapka 1: mapowanie rynku zależy od linii.** Rożne to jeden kod
(`total_corners`) na wszystkie linie. Gole to **kod na linię**:
`over_under_05/15/25/35`. `SIGNAL_MARKETS` mapuje `row.market → str`, więc
sygnatura musi się zmienić na callable albo dojść osobna tablica:

```python
GOALS_FEED_MARKETS: dict[float, str] = {
    0.5: "over_under_05", 1.5: "over_under_15",
    2.5: "over_under_25", 3.5: "over_under_35",
}
```
Linia 4.5 nie ma kodu w feedzie → `NO_MARKET_DATA` z powodem, nigdy interpolacja.

**Pułapka 2: `quotes = context.odds or context.bookmaker_comparison`**
([market_context.py:620](../src/bet/simple_stats/market_context.py#L620)).
`context.odds` zawiera **wyłącznie** `total_corners` (dziś: 41 meczów, 926 kwot.,
`odds markets: [('total_corners', 926)]`). Gdy jest niepuste — a jest, gdy
istnieje jakikolwiek kurs na rożne — wyrażenie `or` **nigdy nie sięgnie po
`bookmaker_comparison`**, gdzie leżą wszystkie kursy na gole. Wiersz goli
dostałby `NO_MARKET_DATA` mimo 624 kwotowań w tym samym obiekcie.
Naprawa: `quotes = [*context.odds, *context.bookmaker_comparison]` — `_best_quote`
i tak filtruje po `(market, line, outcome)`, więc połączenie jest bezpieczne.
**Ta jedna linijka jest warunkiem, żeby cała Faza 1 miała sens.**

**Pułapka 3: de-vig „najlepszy over vs. najlepszy under" miesza bukmacherów.**
`_best_quote` ([market_context.py:540](../src/bet/simple_stats/market_context.py#L540))
bierze `max(price)` osobno dla każdej strony, a `_market_probability` normalizuje
te dwie liczby względem siebie. Przy rożnych to ~12 kwotowań i zniekształcenie
jest małe. Przy golach to **624 kwotowania z ~26 bukmacherów** — najlepszy over u
jednego i najlepszy under u innego dają sumę implied bliską 1.00 albo poniżej
(syntetyczny arbitraż), a stosunek, z którego liczy się prawdopodobieństwo,
przechyla się w stronę tej strony, którą więcej książek wycenia agresywnie.
**Naprawa:** de-vigować **w obrębie jednego bukmachera**, preferując `pinnacle`
(jest w feedzie — zweryfikowane w dzisiejszym artefakcie), z fallbackiem na
pierwszą książkę kwotującą obie strony. Cena raportowana operatorowi zostaje
najlepsza z rynku; **prawdopodobieństwo** liczone jest z jednej książki.
Rożnych to też dotyczy — poprawka jest wspólna.

**Pułapka 4: `_model_probability` twardo rozgałęzia na `corners_total`**
([market_context.py:528](../src/bet/simple_stats/market_context.py#L528)).
Dodać `MODEL_GOALS_FIELDS = {1.5: "prob_goals_over_15", 2.5: "...25", 3.5: "...35"}`
i gałąź dla `goals_total`. Linie 0.5 i 4.5 → brak modelu → `NO_MARKET_DATA`.
W tej samej funkcji poprawić gałąź `known_lines` w `market_signal_for_row`
([market_context.py:633](../src/bet/simple_stats/market_context.py#L633)) — dziś
wybiera między `MODEL_CORNERS_FIELDS` a tenisem i dla goli wypisałaby mylący powód.

`goals_for` **nie dostaje sygnału** — feed nie ma rynku goli drużynowych,
dokładnie jak `corners_for` ([market_context.py:472](../src/bet/simple_stats/market_context.py#L472)).

#### 1e. Sufit LEAN na golach — sprawdzone, nie założone (review 1)


Przejrzałem wszystkie tablice aliasów dostawców
([providers.py:83-160](../src/bet/simple_stats/providers.py#L83)):
`_ESPN_FOOTBALL_ALIASES`, `_API_FOOTBALL_ALIASES`,
`_HIGHLIGHTLY_NORMALIZED_ALIASES`, `_HIGHLIGHTLY_DISPLAY_NAME_ALIASES`.
**Żadna nie emituje goli.** Konsekwencja jest twarda: każdy wiersz goli będzie
`SINGLE_SOURCE`, a `tier_for_row` ([bet_builder_draft.py:133](../src/bet/simple_stats/bet_builder_draft.py#L133))
ścina `SINGLE_SOURCE` do `LEAN` **niezależnie od próby**. Gole nigdy nie będą
`CALL`.

To trzeba powiedzieć operatorowi wprost, bo koliduje z Fazą 5c: po przejściu na
ranking wg przewagi kupon będzie zbudowany prawie wyłącznie z wierszy `LEAN`.

**Faza 1f (opcjonalna, ~0.5 dnia, wymaga sondy).** `_fetch_l10_generic`
([providers.py:1258](../src/bet/simple_stats/providers.py#L1258)) buduje `combined`
wyłącznie ze `stats_dict`, ale ma pod ręką cały wiersz fixture'a `fx`. **Jeśli**
espn-football i highlightly niosą w nim wynik meczu, dopisanie `goals_total` do
ich ścieżki kosztuje zero wywołań i czyni gole **jedyną rodziną z dwoma
źródłami i ceną naraz** — czyli jedyną, która może być `CALL` z przewagą.
Sonda przed kodem: wypisać klucze jednego `fx` z każdego z tych dwóch dostawców.

**Pułapka w Fazie 1f:** `_is_absent_not_zero`
([providers.py:1284](../src/bet/simple_stats/providers.py#L1284)) odrzuca payload,
w którym „każda statystyka to 0". Gol o wartości `0.0` w prawdziwym meczu 0-0
jest **poprawną obserwacją**, a nie brakiem danych — dopisanie goli do `combined`
**przed** tym sprawdzeniem mogłoby uratować payload, który powinien zostać
odrzucony (patrz `a-zero-that-means-unknown`). Gole muszą być dopisywane
**po** `_is_absent_not_zero`, nigdy przed.

#### 1g. Testy
`tests/simple_stats/test_providers.py` — goals z l10 i z h2h, gol z meczu bez `/stats/`.
`tests/simple_stats/test_analyze.py` — wiersze `goals_total` i `goals_for` z fixture'a.
`tests/simple_stats/test_bzzoiro_market_context.py` — sygnał na `goals_total 2.5`
z `bookmaker_comparison` przy **niepustym** `context.odds` (regresja na pułapkę 2);
`0.5` i `4.5` → `NO_MARKET_DATA` z powodem.

**Gotowe, gdy:** replay dzisiejszego dossiera daje wiersze `goals_total` na
**wszystkich 52 meczach piłkarskich z metrykami** (gole nie zależą od `/stats/`,
więc pokrycie ma być pełne), a spośród **46 meczów, które mają dziś
`predictions` i `bookmaker_comparison`**, ≥35 niesie `market_signal` z werdyktem
innym niż `NO_MARKET_DATA` na liniach 1.5/2.5/3.5. Kryterium jest wyrażone
względem pokrycia dostawcy, nie liczbą bezwzględną — liczba bezwzględna
przeszłaby lub oblała się w zależności od tego, ile meczów było danego dnia.

---

### Faza 2 — siatki linii i metryki już zbierane (0.5 dnia)

1. `Team Corners` `[3.5, 4.5, 5.5]` → `[2.5, 3.5, 4.5, 5.5, 6.5, 7.5]`
2. `Team Shots on Target` `[2.5…5.5]` → `[1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5]`
3. `Corners Total` `[8.5…11.5]` → `[6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5]`
4. Nowy `Shots Total` `[19.5, 22.5, 25.5, 28.5]` — metryka `shots_total` istnieje
   w 52 dossierach, jest w `PRIORITY_METRICS` i **jest wyceniana per-drużyna**
   (`shots_for`, 552 wiersze dziś), ale rynku meczowego nie ma.
   *(Korekta review 1: pierwotnie napisałem, że dopiero ten rynek czyni próg
   `READY` osiągalnym. To nieprawda — `_compute_readiness`
   ([enrich.py:195](../src/bet/simple_stats/enrich.py#L195)) liczy dostawców na
   metrykach **zebranych**, nie na wycenionych rynkach, więc `shots_total` już
   dziś liczy się do `READY`. Rynek dodajemy dlatego, że Superbet go wystawia,
   nie żeby naprawić gotowość.)*
5. Nowe rynki na metryki już zbierane: `Total Offsides` `[1.5, 2.5, 3.5, 4.5]`,
   `Total Red Cards` `[0.5]`, `Team Offsides` `[0.5, 1.5, 2.5]`.
   `possession` i `shots_off_target`/`blocked_shots` — **pomijamy**: `possession`
   to procent (inna reguła zgodności), a Superbet nie wystawia strzałów
   zablokowanych. Zostają w dossierze jako kontekst.

**Ryzyko: rozdęcie arkusza.** Dziś 6 510 wierszy / 5.1 MB. Fazy 1+2 dają
szacunkowo **×2.2** (~14 000 wierszy, ~11 MB). Do zniesienia, ale:
* `build_coupons.py` i tak filtruje po `p_low ≥ 0.50`,
* analityk czyta plik w całości — jego okno kontekstu jest realnym ograniczeniem.
* **Akcja:** `run_analyze.py --max-rows-per-event N` (domyślnie bez limitu) oraz
  osobny, chudy artefakt `<date>_stats_sheet_top.json` (tylko wiersze
  `p_low ≥ 0.50`) — to on idzie do analityka, pełny zostaje na dysku.

**Gotowe, gdy:** dla Real Madryt-podobnego meczu istnieją wiersze `corners_for
6.5` i `shots_on_target_for 6.5`; `diff_stats_sheet.py` nie pokazuje **żadnej
zmiany `p_low`** na wierszach, które istniały wcześniej.

---

### Faza 3 — połowy (2 h sondy + 1–3 dni) · **najpierw sonda, potem kod**

Zrzut operatora ma `2. połowa – liczba goli powyżej 0.5`.

**Krok 3.0 — sonda (2 h, warunek wejścia).** Kod mówi, że `first_half` /
`second_half` leżą obok `home`/`away` w tym samym obiekcie
([bzzoiro.py:578](../src/bet/api_clients/bzzoiro.py#L578)), ale **nie wiadomo,
które statystyki tam są**. Przede wszystkim: **gole w połowach prawie na pewno
nie są w `/events/{id}/stats/`** — wynik jest polem fixture'a, nie statystyką.
Zanim cokolwiek napiszemy, jednym wywołaniem MCP `get_match_detail` na
zakończonym meczu sprawdzić, czy istnieje `period_scores` / `scores.period_1`.
Jeśli nie — gole półmeczowe wymagają `get_match_incidents` (minuty goli), co jest
**+1 wywołanie na mecz historyczny** i wywraca budżet fazy.

* **Wariant A** (są wyniki połów w payloadzie fixture'a): koszt jak Faza 1 — zero
  nowych wywołań. 1 dzień.
* **Wariant B** (trzeba `incidents`): +1 wywołanie × ~25 meczów historycznych ×
  liczba fixture'ów. Przy `RUN_BUDGET_OVERRIDES["bzzoiro"] = 20000` mieści się,
  ale podwaja czas ENRICH. 2–3 dni. **Rekomendacja: odłożyć za Fazę 5.**

Reszta fazy (rożne/kartki/strzały w połowach) idzie z `first_half`/`second_half`
w payloadzie statystyk, jeśli sonda potwierdzi ich obecność.

Nowe metryki: `goals_1h_total`, `goals_2h_total`, `corners_1h_total`,
`cards_2h_total`, … Nazewnictwo: `{stat}_{1h|2h}_{total|for}` — sufiks `_total`/
`_for` **na końcu**, żeby istniejące reguły w `COUNT_METRICS` i
`cross_provider_agreement` działały bez zmian.

**Gotowe, gdy:** sonda ma odpowiedź na piśmie w tym dokumencie, a wybrany wariant
daje wiersze `goals_2h_total 0.5` na ≥20 meczach.

---

### Faza 4 — propy zawodników (1 dzień) · „każda z drużyn" świadomie odpada

#### 4a. Rynek „każda z drużyn pow. X" (`both_teams_over`)
Nowa **rodzina wyprowadzona**, nie nowe zbieranie. Dla metryki `_for` i linii L:
próba = mecze, w których **obie** drużyny przekroczyły L. Problem: `team_a_l10` i
`team_b_l10` to **różne mecze**, więc nie da się z nich zbudować koniunkcji.

**Błąd, który tu popełniłem i naprawiam (review 1).** Pierwotnie zapisałem
`p_low = min(p_low_A, p_low_B)` i nazwałem to „podłogą". To jest odwrotnie:
`P(A∩B) ≤ min(P(A), P(B))` **zawsze**, więc `min` jest **sufitem**. Wstawienie go
w kolumnę `p_low` — którą `coupons.py` czyta jako dolną granicę i z której liczy
`1/p_low` — **zawyżałoby pewność i zaniżało minimalny kurs**. To dokładnie ten
kierunek błędu, który zakaz kursu łącznego istnieje po to, żeby wyłapać.

Trzy warianty, do decyzji przed implementacją:

* **A (rekomendowany).** **Nie emitować rodziny w ogóle w Fazie 4.** Nie mamy
  próby, z której da się policzyć koniunkcję: `team_a_l10` i `team_b_l10` to
  rozłączne zbiory meczów, a h2h ma ~2 spotkania. Zamiast tego wypisywać w
  `analiza.md` obie nogi osobno z adnotacją „Superbet wystawia to jako jedną
  nogę »każda z drużyn«; poniżej dwie osobne historie, których nie wolno
  mnożyć". Koszt: 0 dni. Uczciwość: pełna.
* **B.** Emitować z `p_low` policzonym **z prawdziwej koniunkcji na h2h**, gdy
  h2h ma ≥8 spotkań. Realne dla derbów i rywalizacji ligowych, martwe dla
  reszty. ~0.5 dnia, pokrycie znikome.
* **C.** Nowa ścieżka zbierania: dla każdego meczu z `team_a_l10` sprawdzić, czy
  **przeciwnik w tamtym meczu** też przekroczył L — dane są w
  `/events/{id}/stats/`, które i tak pobieramy, bo `stats["home"]` i
  `stats["away"]` są **oba** w cache'u ([providers.py:1666](../src/bet/simple_stats/providers.py#L1666)).
  To daje prawdziwą koniunkcję na 10+10 meczach za zero dodatkowych wywołań, ale
  mierzy „drużyna A i **ktokolwiek**", nie „A i B". ~1 dzień.

**Rekomendacja: A w Fazie 4, C jako osobna decyzja po Fazie 5.**

#### 4b. Propy zawodników
Kod jest gotowy ([enrich.py:411](../src/bet/simple_stats/enrich.py#L411)),
`PLAYER_PROP_LINES` istnieje, `tier_for_row` ma już sufit LEAN dla przewidywanego
składu. Do zrobienia:
* `--player-props` w Kroku 2 `run-day.md` (dziś nie jest przekazywane),
* koszt: ~20 wywołań/mecz — przy 52 meczach to ~1 040, mieści się w 20 000,
* `PLAYER_PROP_LINES` rozszerzyć o `player_cards` `[0.5]` → już jest; dodać
  `player_shots_on_target` `[0.5, 1.5, 2.5]`,
* **twardy warunek:** prop na zawodnika z listy `unavailable` musi być
  **odrzucony w kodzie**, nie w prozie. Dziś `bet-analyst.md` każe to sprawdzać
  ręcznie. Filtr wchodzi do `_player_prop_rows`, bo `squad_availability` jest już
  w dossierze.
* **timing:** skład bywa dostępny ~1 h przed meczem. Dla runu porannego większość
  propów pójdzie z `lineup_status: predicted` → sufit LEAN. To akceptowalne, ale
  `run-day.md` musi to powiedzieć, żeby operator nie czekał na CALL, który nie
  przyjdzie.

**Gotowe, gdy:** ≥5 meczów ma wiersze propów, żaden prop nie dotyczy zawodnika z
`unavailable`, a `diff_stats_sheet.py` pokazuje wyłącznie wiersze dodane.

---

### Faza 5 — kontekst i ranking wchodzą do decyzji (5–7 dni) · **właściwa naprawa**

#### 5a. Domknąć pokrycie kontekstu
* **`season_form` 0/192 → cel ≥80% meczów piłkarskich.** Przyczyna: `league_id`
  jest tylko na 25 fixture'ach, bo tylko bzzoiro go dostarcza. Naprawa: gdy
  `fixture_context.league_id` jest puste, a mamy `provider_team_ids["bzzoiro"]`,
  wywołać `get_team_detail` raz na drużynę (wynik cache'owany), odczytać ligę,
  potem tabela raz na ligę. Koszt: ~2 wywołania na nową ligę, nie na mecz.
* **`referee` 24/192.** Część to prawdziwe pokrycie (dostawca nie nazywa sędziego
  wcześnie) — ale to musi być **zmierzone**, nie założone: policzyć, ile
  fixture'ów ma `referee_id` i nie ma profilu, i osobno ile nie ma `referee_id`.
  Bez tego rozróżnienia nie wiadomo, czy jest co naprawiać.

#### 5b. Kontekst jako pole, nie jako proza
Nowe pole na `StatsSheetRow`: `context_flags: list[ContextFlag]`, każda flaga to
`{source, direction: SUPPORTS|ARGUES_AGAINST, magnitude, note}`.

Wypełniane **kodem** w nowym module `src/bet/simple_stats/context_flags.py`, z
danych, które są już w dossierze:

| Źródło | Wpływa na | Reguła |
|---|---|---|
| `referee.avg_yellow_per_match` (+ `matches` ≥ 8) | `cards_*` | średnia po drugiej stronie linii → `ARGUES_AGAINST` |
| `referee.avg_fouls_per_match` (+ `matches` ≥ 8) | `fouls_*` | jw. |
| `squad_availability.unavailable_count` ≥ 4 | `shots_*`, `goals_for` tej strony | `ARGUES_AGAINST` na OVER |
| `season_form.xgf` vs. gole faktyczne | `goals_*`, `shots_*` | duża rozbieżność → `ARGUES_AGAINST` |
| `fixture_context.is_local_derby` | `cards_*`, `fouls_*` | `SUPPORTS` na OVER |
| `weather.wind_speed` > 25 | `corners_*`, `shots_*` | `ARGUES_AGAINST` na OVER |
| ranga rozgrywek (nowe, patrz 5d) | wszystko | filtr, nie flaga |

**Reguła kierunkowa, nienegocjowalna:** flaga może **obniżyć** tier o jeden
stopień (`CALL→LEAN`, `LEAN→WEAK`). Nigdy nie podnosi i nigdy nie dotyka `p_low`.
To jest ten sam sufit, który `bet-analyst.md` już nakłada na dowody z sieci —
teraz egzekwowany przez `tier_for_row`, a nie przez dobrą wolę agenta.

#### 5c. Ranking po przewadze, nie po `p_low`
Tam, gdzie wiersz ma `market_signal` z obiema liczbami (po Fazie 1: rożne **i**
gole), policzyć `edge = p_low − market_implied_probability` i sortować kupon po
`edge` malejąco, z `p_low` jako drugim kluczem. Wiersze bez ceny lądują w
osobnej sekcji „bez odniesienia do rynku", nigdy pomieszane z tymi, które je mają.

To jest ta zmiana, która usuwa z czoła kuponu `UNDER 5.5 kartki @ 21/21` — nie
dlatego, że wiersz jest zły, tylko dlatego, że nie ma przy nim ceny i nie da się
powiedzieć, czy jest opłacalny.

**Konsekwencja do zaakceptowania:** po tej zmianie kupon będzie **krótszy**, bo
tylko dwie rodziny mają cenę. To jest uczciwsza odpowiedź niż trzynaście singli
po 1.31.

#### 5d. Ranga rozgrywek
`competition_tier` w `config/` — mapa `competition → TIER_1|TIER_2|TIER_3|YOUTH|
FRIENDLY`, wypełniona ręcznie dla lig, które realnie się pojawiają (dziś: 82
nazwy). Zastosowanie:
* `YOUTH` / `FRIENDLY` (dziś: „U19 league", „Pro League U23", „Brasileiro U17",
  „Friendlies Clubs", „Premier League 2") — **wykluczone z kuponu**, zostają na
  arkuszu. Statystyki juniorskie i sparingowe nie opisują rynku, który ktokolwiek
  wystawia.
* `TIER_1` — dopuszczone do sekcji z ceną nawet przy niższym `p_low`.

To **jedyne miejsce w planie, gdzie „ranga turnieju" jest realizowalna** — model
rangi w rozumieniu siły rywala wymagałby rankingu drużyn, którego żaden dostawca
w rosterze nie serwuje.

#### 5e. Zamknąć pętlę analityk → kupon
Trzy warianty, do decyzji operatora:

* **A (rekomendowany).** Przestawić `run-day.md`: analityk pracuje **przed**
  `build_coupons.py` i zwraca `<date>_analyst_vetoes.json`
  (`[{event_id, market, line, direction, action: VETO|DOWNGRADE, reason}]`).
  `build_coupons.py --vetoes <plik>` je stosuje i **raportuje w pliku kuponowym,
  które wiersze i dlaczego**. Analityk nadal nie ma Write — plik zwraca jako
  strukturę, zapisuje ją orkiestrator. Bariera audytowa zostaje nienaruszona.
* **B.** Zostawić kolejność, dodać `build_coupons.py --rebuild-with-vetoes` jako
  drugi przebieg. Prostsze, ale kupon jest zapisywany dwa razy i pierwszy zapis
  jest wprowadzający w błąd.
* **C.** Nic nie zmieniać, tylko `context_flags` (5b) — bez udziału agenta.
  Najtańsze, ale traci to, co analityk widzi, a kod nie (zawieszony mecz,
  przeniesiony termin, dwa zawieszenia kartkowe wygasające dziś).

**Gotowe, gdy:** kupon zawiera sekcję „z odniesieniem do rynku" posortowaną po
`edge`, żadna pozycja nie pochodzi z rozgrywek `YOUTH`/`FRIENDLY`, a każde veto
analityka jest widoczne w pliku z powodem.

---

### Faza 6 — pokrycie slate'u (2 dni)

* **ESPN: 58 nierozwiązanych nazw lig.** Rozszerzyć przypiętą mapę
  (`verify_espn_competition_map.py` + bramka pinów) o ligi, które realnie wracają
  w slate: Veikkausliiga, Allsvenskan, National League, Primera C. **Tylko przez
  pin z weryfikacją** — nigdy fuzzy (por. wpis o nadgorliwym dopasowaniu z
  2026-08-28).
* **Duplikaty nazw lig w DISCOVER:** `EPL` vs `Premier League`, `Veikkausliiga`
  vs `Veikkausliiga - Finland`, `Superliga`/`Denmark Superliga`/`Danish
  Superliga`. Dziś rozbijają ten sam mecz na dwa wpisy i psują mapowanie ESPN.
  Kanonizacja nazwy rozgrywek przy scalaniu w DISCOVER.
* **highlightly wyczerpany (101/100).** To dominujące źródło **odkrywania** —
  wyczerpanie zmniejsza slate, nie tylko korroborację. Opcje: przenieść odkrywanie
  dużych lig na bzzoiro (uncapped), albo zaakceptować i powiedzieć to w raporcie.
* **sportdb 402 na 159 z 159 żądań.** To uprawnienie/rozliczenie, nie limit.
  Decyzja operatora: opłacić albo wyłączyć z rosteru, żeby przestał produkować
  340 fałszywych `data_gaps` na run.

---

## 3bis. Rzeczy przekrojowe, które muszą iść z każdą fazą (review 2)

Poniższe nie są fazą — to obowiązki, które każda faza zabiera ze sobą. Bez nich
plan wygląda na skończony i nie jest.

### 3bis.1 Przełącznik i wycofanie
Każda faza zmienia kształt arkusza, a arkusz jest wejściem dla dnia zakładowego.
Musi istnieć wyjście awaryjne, którego nie trzeba szukać w gicie o 6 rano:

* `BET_MARKETS_PROFILE=legacy|v2` (env, czytane w `market_ranking.py`) — `legacy`
  odtwarza dokładnie dzisiejszy zestaw rynków i linii.
* Domyślnie `v2` **dopiero po** pierwszym dniu przejechanym równolegle.
* Test, który wymusza, że pod `legacy` `diff_stats_sheet.py` daje pusty diff
  wobec zamrożonego arkusza z Fazy 0. To jedyny sposób, żeby przełącznik nie
  zgnił po dwóch tygodniach.

### 3bis.2 Dokumenty są tu kontraktami, nie opisem
Trzy pliki opisują to, czego kod nie egzekwuje. Rozjazd między nimi a kodem jest
tą samą klasą awarii co błąd w kodzie:

| Plik | Co się zmienia | W której fazie |
|---|---|---|
| `.claude/agents/bet-analyst.md` | tabele rynków i linii (dziś wypisane co do liczby), akapit o `n` goli, akapit o suficie LEAN na golach, `context_flags` | 1, 2, 4, 5 |
| `.claude/commands/run-day.md` | `--player-props`, chudy arkusz, kolejność analityk↔kupon, veta | 2, 4, 5 |
| `docs/SIMPLE_STATS_RUNBOOK.md` | wiersz 143 (rodziny rynków), wiersz 174 („sygnał istnieje tylko na `corners_total`" — po Fazie 1 nieprawda) | 1, 2 |

### 3bis.3 Etykiety polskie
`market_label()` ([coupons.py:163](../src/bet/simple_stats/coupons.py#L163)) przy
braku wpisu zwraca `market.replace("_", " ")` — czyli **angielską nazwę w polskim
pliku kuponowym**, cicho. Każda faza dodająca rynek dodaje wpis do
`MARKET_LABELS` i do `MARKET_PL`. Test: dla każdego rynku w
`STANDARD_MARKET_LINES["football"]` i `PLAYER_PROP_LINES["football"]` istnieje
wpis w `MARKET_LABELS` — parametryzowany, więc nowy rynek bez etykiety zapala
się natychmiast.

### 3bis.4 Rodzina skorelowana musi rosnąć razem z katalogiem
`_CORRELATED_FOOTBALL_FAMILY` ([bet_builder_draft.py:57](../src/bet/simple_stats/bet_builder_draft.py#L57))
jest listą literalną. Nowy rynek spoza niej **nie zapala ostrzeżenia o
korelacji** — a gole korelują ze strzałami i rożnymi silniej niż cokolwiek, co
tam już jest (mecz strzelecki jest meczem rożnym). Do dopisania w Fazie 1:
`goals_total`, `goals_for`; w Fazie 2: `offsides_*`, `red_cards_total`,
`shots_total`; w Fazie 3: cała rodzina półmeczowa; w Fazie 4:
`player_shots_on_target`. Test: żaden rynek piłkarski z
`STANDARD_MARKET_LINES` nie jest poza tym zbiorem, chyba że jawnie wymieniony w
liście wyjątków z komentarzem.

### 3bis.5 Faza 2 dotyka wyłącznie listy piłkarskiej
`STANDARD_MARKET_LINES` to jeden słownik na osiem dyscyplin. Wszystkie zmiany
linii w Fazie 2 są w kluczu `"football"`. Tenis, koszykówka i esport zostają
nietknięte — `bzzoiro-tennis` jest dziś dodatkowo zablokowany uprawnieniowo
(`addon_required`) i nie da się na nim niczego zweryfikować.

### 3bis.6 Kruche założenie: uprawnienie „Football Unlimited"
Cała ścieżka ceny na gole idzie przez `bookmaker_comparison`, a ten wymaga
uprawnienia, którego stan jest **sondowany raz na run** i cache'owany
(`_ENTITLEMENT_CACHE`). Dziś `football_unlimited_entitled: true`. Jeśli
uprawnienie zniknie — tak jak zniknęło dziś uprawnienie tenisowe — gole tracą
cenę i model naraz, a wraz z nimi cała Faza 5c.
**Zabezpieczenie:** `comparison_entitlement != "ENTITLED"` musi być wypisane
**w nagłówku pliku kuponowego**, nie tylko w `data_gaps`. Operator ma zobaczyć,
że dzisiejszy kupon powstał bez odniesienia do rynku, zanim przeczyta pierwszy
wiersz.

### 3bis.7 Jak poznamy, że jest lepiej
Bez tego cały plan jest niesprawdzalny. Kryterium akceptacji dla całości:

1. Odtworzyć **2026-08-30** (dzień ze zrzutów operatora) z zamrożonych dossierów.
2. Sprawdzić, czy arkusz zawiera wiersze dla trzech nóg z SUPERBETS Real Madryt –
   Malaga (`shots_on_target_for 6.5 OVER`, `goals_for 1.5 OVER`,
   `corners_for 6.5 OVER`) i dwóch z Napoli – Como.
3. Sprawdzić, czy `goals_total` na tych meczach niesie `market_signal` z ceną.

To nie jest test „czy typ wygrał" — wynik meczu nie waliduje procesu. To test,
czy **rynek, który operator realnie kliknął, w ogóle istnieje w arkuszu**. Dziś
nie istnieje żaden z pięciu.

---

## 4. Kolejność, zależności, koszt

```
Faza 0 (0.5d)
  ├─> Faza 1  (1.5d)  gole ──┬─> Faza 2 (0.5d) ─> Faza 4 (1d)
  │      └─ Faza 1f (0.5d, opcjonalna, po sondzie)
  │                          └─> Faza 5c  ceny są warunkiem rankingu
  ├─> Faza 6  (2d)   pokrycie ─────────────────────┐
  └─> Faza 3  sonda (2h) ─> Faza 3 (1–3d) ─────────┴─> Faza 5 (5–7d)
```

Zależności twarde:
* **5c wymaga 1.** Bez goli tylko rożne mają cenę — za mało wierszy, żeby
  ranking po przewadze miał sens.
* **5b wymaga 5a.** Flagi kontekstowe z pustego `season_form` to flagi z niczego.
* **Faza 3 nie blokuje niczego.** Jeśli sonda wyjdzie na wariant B, wypada za 5.
* **Faza 6 jest niezależna** i można ją robić równolegle przez inną osobę.

| | Effort | Zwrot |
|---|---|---|
| Faza 0 | 0.5 d | warunek konieczny — bez niej nie odróżnimy poprawy od regresji |
| **Faza 1** | **1.5 d** | **gole: jedyna nowa rodzina z ceną i modelem** |
| Faza 1f | 0.5 d (opcjonalna) | gole z dwóch źródeł → jedyna rodzina zdolna do `CALL` z przewagą |
| Faza 2 | 0.5 d | linie ze zrzutów operatora stają się osiągalne |
| Faza 3 | 2 h sondy + 1–3 d | połowy (wariant zależny od sondy) |
| Faza 4 | 1 d | propy zawodników (rynek „każda z drużyn" świadomie pominięty) |
| Faza 5 | 5–7 d | kontekst decyduje, ranking po przewadze, pętla analityk→kupon |
| Faza 6 | 2 d | slate przestaje się kurczyć (sportdb = decyzja operatora, nie kod) |
| **Razem** | **11–17 dni** | |

**Minimalna sensowna dostawa: Fazy 0+1+2 = 2.5 dnia.** Po niej mecz typu Real
Madryt – Malaga ma wiersze na wszystkie trzy nogi ze zrzutu operatora, a gole
niosą kurs bukmacherski i prawdopodobieństwo modelu.

**Rekomendowany pierwszy commit: Faza 0 + poprawka pułapki 2 z Fazy 1d**
(`context.odds or context.bookmaker_comparison` → konkatenacja). To dwie linijki
i test, a bez nich reszta Fazy 1 jest niema.

## 5. Ryzyka

| Ryzyko | Waga | Środek zaradczy |
|---|---|---|
| Arkusz rośnie ponad okno kontekstu analityka | **wysoka** | chudy `stats_sheet_top.json` (Faza 2) |
| `context.odds or bookmaker_comparison` — po cichu blokuje sygnał na gole | **wysoka** | test regresyjny przy **niepustym** `context.odds` (Faza 1e) |
| Gole z meczów bez `/stats/` dają `n` inne niż reszta rynków | średnia | udokumentowane, akapit w `bet-analyst.md` |
| Sonda połów wychodzi na wariant B | średnia | Faza 3 odłożona za Fazę 5, nie blokuje niczego |
| Krótszy kupon po Fazie 5c | średnia | decyzja operatora **przed** implementacją |
| Rozszerzone linie zmieniają istniejące `p_low` | niska | `diff_stats_sheet.py` musi pokazać wyłącznie wiersze dodane |
| 73/161 istniejących awarii testów maskuje nową | średnia | porównywać **zbiory nazw**, nie liczby |
| Gole na zawsze `SINGLE_SOURCE` → sufit `LEAN`; po Fazie 5c kupon jest wyłącznie z `LEAN` | **wysoka** | Faza 1f (gole z espn/highlightly) albo świadoma zgoda operatora |
| De-vig „najlepszy over vs. najlepszy under" z dwóch różnych książek | **wysoka** | de-vig w obrębie jednego bukmachera, `pinnacle` pierwszy (Faza 1d, pułapka 3) |
| Utrata uprawnienia „Football Unlimited" zabiera cenę **i** model na gole naraz | średnia | `comparison_entitlement` w nagłówku pliku kuponowego (3bis.6) |
| Faza 5b dodaje pole do `StatsSheetRow` → zmienia się każdy artefakt na dysku | niska | pole z wartością domyślną; `diff_stats_sheet.py` porównuje po kluczu, nie po całym obiekcie |
| Faza 5e wariant A zwiększa liczbę fixture'ów do weryfikacji przez MCP (dziś 16, po zmianie cały top arkusza) | średnia | weryfikować tylko kandydatów po filtrze `p_low`, nie cały arkusz; piłka jest uncapped |
| Przełącznik `BET_MARKETS_PROFILE=legacy` gnije i przestaje działać | średnia | test wymuszający pusty diff pod `legacy` (3bis.1) |

---

## 6. Czego ten plan świadomie nie robi

* **Nie liczy kursu łącznego, EV ani stawki.** Nigdzie, w żadnej fazie.
* **Nie modeluje siły drużyny ani rankingu.** Żaden dostawca w rosterze go nie
  serwuje; `competition_tier` (5d) to najbliższe realizowalne przybliżenie.
* **Nie dotyka tenisa.** `bzzoiro-tennis` to 100/dzień i dziś dodatkowo
  `addon_required`. Osobna decyzja, osobny plan.
* **Nie pozwala kontekstowi promować.** Sędzia, kontuzje i forma mogą wyłącznie
  degradować. To reguła, nie ostrożność.
* **Nie buduje rynku „każda z drużyn".** Nie mamy próby, z której da się
  policzyć koniunkcję dwóch stron; wariant, który wyglądał na tanie przybliżenie,
  okazał się sufitem udającym podłogę (Faza 4a). Rynek zostaje opisany w analizie
  jako dwie osobne nogi, których nie wolno mnożyć.
* **Nie zmienia definicji `p_low` ani `wilson_lower_bound`.** Wszystko, co plan
  dokłada — flagi kontekstowe, przewaga, ranga rozgrywek — żyje **obok** tej
  kolumny i nigdy w niej.
* **Nie scrapuje Superbetu.** Granica manualna zostaje nienaruszona.

---

## 7. Log review

**Review 1 — weryfikacja tez planu w kodzie.** Cztery błędy rzeczowe:
`READY` nie zależy od rynków, tylko od metryk (Faza 2.4); `min(p_low_A, p_low_B)`
to sufit, nie podłoga, i zawyżałby pewność (Faza 4a — rodzina wycofana);
gole będą `SINGLE_SOURCE`, bo żaden alias dostawcy ich nie emituje (nowa 1e/1f);
de-vig najlepszy-vs-najlepszy miesza bukmacherów i przy 624 kwotowaniach na gole
zniekształca wynik istotnie (nowa pułapka 3 w 1d). Potwierdzone jako bezpieczne:
`StatsSheetRow.market` to `str`, a `metrics` to `dict[str, …]` bez `Literal` —
nowe metryki i rynki **nie wymagają zmiany kontraktu**.

**Review 2 — dziury.** Plan opisywał kod i milczał o wszystkim wokół niego.
Dodano sekcję 3bis: przełącznik i wycofanie; trzy dokumenty, które są tu
kontraktami (`bet-analyst.md`, `run-day.md`, runbook) i muszą iść z każdą fazą;
cichy fallback `market_label()` do angielskiego; `_CORRELATED_FOOTBALL_FAMILY`
jako lista literalna, która nie rośnie sama; ograniczenie zmian linii do klucza
`"football"`; kruchość uprawnienia „Football Unlimited"; oraz kryterium
akceptacji dla całości — odtworzyć 2026-08-30 i sprawdzić, czy pięć nóg z realnych
zrzutów operatora w ogóle istnieje w arkuszu (dziś nie istnieje ani jedna).

**Review 3 — spójność i wycena.** Suma etapów nie zgadzała się z podaną (13–17
→ **11–17 dni**); Faza 4 spadła z 1.5 d do 1 d po wycofaniu rodziny „każda z
drużyn"; kryterium ukończenia Fazy 1 było liczbą bezwzględną, która przechodzi
albo oblewa się w zależności od wielkości slate'u — przepisane względem pokrycia
dostawcy; graf zależności przerysowany tak, żeby pokazywał, że 5c wymaga 1, a 5b
wymaga 5a; tabela ryzyk uzupełniona o sześć pozycji wynikających z review 1 i 2;
dopisany rekomendowany pierwszy commit (Faza 0 + poprawka konkatenacji kwotowań),
bo bez tych dwóch linijek reszta Fazy 1 nie ma jak zadziałać.
