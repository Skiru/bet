# Audyt pokrycia - wdrożenie planu P1-P14 („ALL IN”), 2026-10-23

Decyzja operatora 2026-10-23 ~13:50Z: „ALL IN” dla planu z
[AUDYT_POKRYCIA_2026-10-23.md](AUDYT_POKRYCIA_2026-10-23.md) (sekcja 7).
Zasady decyzji:

- pozycje bez pomiaru (P2, P8, P9, P12, P14): włączone od 2026-10-24 00:00Z,
  gdy kod i testy przechodzą;
- pozycje z pomiarem (P1, P3, P4, P5, P6, P7): włączone tylko, gdy pomiar
  poza próbą jest lepszy (bootstrap po meczach / grach, przedział bez zera),
  a dla poprawki pokrycia: dodane wiersze skalibrowane i nic gorzej na
  wierszach istniejących; inaczej kod i test zostają, przełącznik `None`;
- refity (stałe `fit_player_model.py` dla P3, rodzina `player_offsides_for`
  dla P6): tylko na kopii bazy, instalacja tylko do pliku stagowanego /
  datowanego od 2026-10-24 i tylko, gdy lepiej.

Wszystkie przełączniki są w `src/bet/sofa/epochs.py` (blok „Coverage audit
2026-10-23” na końcu pliku), czytane po dniu buildu i zegarze buildu
(`_audit_1023_on`); wyłączony = dokładnie stare wywołanie (nowy argument nie
jest przekazywany). Grupa księgi: **„od 10-24”** - ta sama co
`LIVE_ONLY_CURVE_REFUSED` i krzywa hokeja z `.next.2026-10-24.json`, bez dnia
mieszanego (`scripts/sofa/audit_ledger.py`, `LIVE_ONLY_CURVE_EPOCH_FROM_DATE`).
Kupon 10-23 nietknięty: żadna przebudowa, nic pod `runs/sofa/`.
Szczegóły liczb po angielsku: `.claude/skills/sofa-pipeline/references/model-state.md`,
sekcja (a) „Coverage audit 2026-10-23”.

## 1. Stan przełączników (z kodu, `epochs.py`, 2026-10-23)

| # | przełącznik | stan | dlaczego |
|---|---|---|---|
| P1 | `SAMPLE_CONFLICT_CUT_FROM_UTC` | **10-24 00:00Z** | odzyskane +0,51 pp [+0,15; +0,85] (sekcja 6) |
| P2 | `IDENTITY_FRESH_RECHECK_ALL_FROM_UTC` | **10-24 00:00Z** | bez pomiaru, kod + testy |
| P3 | `PLAYER_HISTORY_ANY_TEAM_FROM_UTC`, `PLAYER_HISTORY_ANY_TEAM_SPORTS` = {hokej, piłka} | **10-24 00:00Z, hokej i piłka** | hokej lepszy; piłka: dodane skalibrowane (sekcja 6); kosz gorszy |
| P4 | `SPORT_QUERY_ANCHOR_FROM_UTC` (`QUERY_ANCHOR_SPORTS` = {siatkówka}) | **10-24 00:00Z** | backtest 0 złych na 2 480 |
| P5 | `PLAYER_SLUG_NAME_FROM_UTC` | **10-24 00:00Z** | 0 innych osób na 24 321 (sekcja 6) |
| P6 | `PLAYER_OMITTED_ZERO_FROM_UTC` | `None` | zmierzone gorzej (sekcja 6) |
| P7 | `CS2_LINEUP_ELO_UNRATED_FROM_UTC` | **10-24 00:00Z** | dodane skalibrowane, stare bez zmian |
| P8 | `NAME_RULES_1023_FROM_UTC` | **10-24 00:00Z** | bez pomiaru |
| P9 | `PLAYER_BOTH_SIDES_LISTED_FROM_UTC` | **10-24 00:00Z** | bez pomiaru |
| P10 | - | zamknięte bez zmiany | Katar 2345 -> 39366: brak sezonu u źródła |
| P11 | `BB_HALVES_LEAGUES_FROM_UTC` | `None` | brak NCAA kosza w ofercie Superbetu |
| P12 | `CS2_SERIES_ONLY_MODEL_P_FROM_UTC` | **10-24 00:00Z** (zegar rozliczenia) | bez pomiaru |
| P13 | rozliczenie: bez przełącznika; model: `VB_GOLDEN_SET_FROM_UTC` | rozliczenie **na żywo od 10-23**; model **10-24 00:00Z** | poprawka poprawności + fakt Superbetu ustalony |
| P14 | `TENNIS_RATING_SCORE_WINNER_FROM_UTC` | **10-24 00:00Z** | bez pomiaru; podpięte w SHEET (`run_sheet.load_tennis_rating`), +173 mecze (sekcja 5) |

## 2. Tożsamość sportów (P2, P4, P8-CS2)

**P2 - świeża strona i druga drużyna.** `sport_identity.identify_event`
(`fresh_all`): ponowne pytanie o świeżą stronę drużyny (K5) odpala się przy
KAŻDEJ odmowie przeczytanej z cache w `FRESH_RECHECK_WITHIN` (3 h) od startu,
w każdym sporcie, raz na drużynę na przebieg; gdy dalej nic, pytana jest
strona drugiej drużyny (jej id, bez niego id z zapytania; najpierw cache,
świeża w oknie). Pola rekordu: `second_team_id`, `second_listing_from_cache`,
`second_fresh_recheck`, `identified_by_second_team` / `second_team_reason`.
`NOT_ON_SOFASCORE` czyta stronę pierwszej drużyny i wymaga zgody strony
drugiej: jeśli druga strona pokazuje mecz, ale go odrzuca (AMBIGUOUS,
START_GAP...), zostaje `NO_GAME_WITHIN_1H` z polem
`absence_contradicted_by_second_team` (przegląd R1 F4, sekcja 10); breaker /
`BRIDGE_ABORTED` bez zmian. Koszt (górna granica,
`scripts/sofa/measure_audit1023_p2_recheck_cost.py`): 179 / 123 / 156
dodatkowych zapytań 10-21 / 10-22 / 10-23 (niepełny), ~15 s mostu dziennie.
Testy: `tests/sofa/test_audit1023_p2_fresh_recheck.py` (8; 5 pada na HEAD).

**P4 - kotwica zapytania w siatkówce.** `sport_identity.match_query_anchor`
po odmowie `match_shadow`, gdy żadna strona nie ma rozwiązanego id: jedyny
mecz drużyny z zapytania o dokładnej godzinie Superbetu (luka 0), płeć, nie
przełożony; nazwa szukanej strony >= 90 i ten sam skład; przeciwnik: najpierw
WETO (zapytanie przeciwnika wskazuje drużyny, a przeciwnik meczu nie jest
żadną z nich), potem MUTUAL / NAME >= 65 / SHARED_WORD; dwa mecze =
AMBIGUOUS. `match_method` QUERY_ANCHOR, `query_anchor_rule`; mapa encji nie
uczy się z niego nazw. `run_sport_identity.py` podaje jawnie
`anchor_opponents=resolver.query_ids`.
Backtest (`scripts/sofa/measure_audit1023_p4_query_anchor.py`, kopia bazy,
10-05..10-23, id ukryte):

| sport | wybory (prawdziwa drużyna / dzisiejsze query id) | złe | fałszywy przeciwnik przyjęty | odzyskane z odmów query-only |
|---|---|---|---|---|
| siatkówka | 1 308 / 1 172 (3 podszywające się id, odrzucone) | **0** | 18 z 15 280 | 11 z 96 (8 zgodne z rozliczeniem, 0 sprzeczne, 3 nierozliczone) |
| hokej | 2 548 / 2 437 | 0 | 18 z 24 308 | 4 z 11 |
| koszykówka | 3 218 / 2 542 | 0 | 44 z 20 236 | 15 z 38 |

Włączona tylko siatkówka (zakres pozycji). Hokej i kosz zmierzone czysto -
dopisanie ich do `QUERY_ANCHOR_SPORTS` to decyzja operatora, od kolejnego
dnia. Kalibracja dodanych nóg niezmierzona (11 zdarzeń w 19 dni).
Testy: `tests/sofa/test_audit1023_p4_query_anchor.py` (12).

**P8 (CS2 w tożsamości).** „prospect” = znacznik składu „prospects”
(`cs2.ROSTER_MARKER_FOLD`; Sofascore „Inner Circle Prospect”, Superbet „Inner
Circle Prospects”), czytany przez `match_cs2`, `match_cs2_anchored`,
`_cs2_same_roster` i rozliczenie CS2. Privateer - Inner Circle Prospects
przypina się od 10-24 (test `test_audit1023_wiring_cs2_identity.py`).

## 3. Zawodnicy hokeja / kosza (P3, P8-hokej, P9)

**P3 / K7 - historia z innych drużyn.** `player_model.load_appearances(any_team=True)`
(wymaga reguły stron `PLAYER_TEAM_FROM_SIDE`): próbka zawodnika obejmuje też
listy `last` drużyn-rówieśników (rywali obu drużyn w wczytanych meczach),
czytane po stronie składu, oznaczone `foreign` - tylko w jego próbce, nigdy
w puli. `find_player` pyta rówieśników tylko przy NOT_IN_HISTORY, ścisłą
regułą (dwóch zgodnych = NAME_UNCERTAIN). Wiersz `player_history_rule:
"any_team_peers"`. SHADOW_SETTLE (liczba rozliczeniowa) czyta to samo po
dniu meczu. Stałe modelu rozwiązywane po dniu (`params_path_for`); żaden plik
`config/sofa_player_model.next.<data>.json` nie jest przygotowany.

Pomiar (`scripts/sofa/measure_audit1023_p3_player_any_team.py`, kopia bazy,
rozliczone linie zawodników Superbetu 09-29..10-22, bootstrap 1 000 po meczach):

| | hokej (24 838 stron, 155 meczów) | kosz (27 864 stron, 245 meczów) |
|---|---|---|
| strony z p | 22 418 -> 24 294 | 18 696 -> 22 726 |
| wspólne: log loss | **-0,0018 [-0,0034; -0,0003]** | -0,0013 [-0,0045; +0,0019] |
| wspólne: Brier | -0,0007 [-0,0012; -0,0002] | - |
| dodane faworyzowane: deklarowane / trafione | 0,667 / 0,647, -0,020 [-0,055; +0,013] | 0,627 / 0,544, **-0,083 [-0,115; -0,052]** |
| decyzja | **ON** | **OFF** |

Przykłady: Lyubushkin (Boston, 10-22) NOT_IN_HISTORY -> n=29; LaMelo Ball
n=1 -> 59, Naz Reid n=1 -> 55 (kosz - wyłączony). Ścieżka nazw w hokeju:
6 085 -> 6 205 zgodnych z boxem, 1 nowy inny gracz (0,016%). Model dalej
gorszy od ceny (+0,0070 [+0,0027; +0,0111] zamiast +0,0088).
Refit hokeja na nowym czytelniku (`fit_player_model.py --sport hockey
--any-team`: prior_games 2,0, calibration_b 0,930) wobec zainstalowanych
stałych na tym samym czytelniku: -0,0003 [-0,0008; +0,0001] -
**niezainstalowany** (plik gotowy:
`data/refit_2026-10-23_allin/p3/fit_hockey_any.json`). Refitu kosza nie było
(jedna ewaluacja celu > 12 min). Uwaga: line evidence kluczy `player_*`
hokeja zbudowano na starym p (~9% stron zmienia p).
Testy: `tests/sofa/test_audit1023_p3_player_any_team.py` (9).

**P8 - transliteracja w hokeju.** `player_model.names_agree(translit)`:
ue/oe/ae -> u/o/a, początkowe „ye” -> „e”, x -> ks, końcowe -iy/-ij/-y -> -i;
tylko równość złożonych tokenów (bez prefiksu, inicjału, ratio). Na 7 271
nazwiskach hokeja 0 nowych zgodnych par różnych id (kosz: 20, np. Braeden /
Braden Smith - dlatego tylko hokej). Wiersz `name_rule: "translit_1023"`.
Testy: `tests/sofa/test_audit1023_p8_hockey_translit.py` (15).

**P9 - mecz w liście obu drużyn.** `sport_history.list_both_sides` zapisuje
brakującą stronę meczu (z zapisanego payloadu) jako rodzaj `last_side`; nic,
co czyta `last`, jej nie widzi. Model zawodników (liczba przedmeczowa SHADOW
po dniu meczu i zegarze migawki, liczba rozliczeniowa po dniu meczu) czyta
`listing_kinds` = `("last", "last_side")` od przełącznika, wiersz
`player_lists_rule: "both_sides"`. **Naprawa danych przeszła 2026-10-23
~15:20Z** (sesja główna, `refresh_sport_history.py --both-sides-only`):
42 892 wiersze `last_side`; mecze z ostatnich 400 dni: hokej 1 241, kosz
7 273; Vancouver @ Florida 16546356 jest teraz w liście 3692. Dalej robi to
każdy `refresh_sport_history.py`. `fit_player_model.py` czyta tylko `last`
(do zmiany przy następnym reficie). Wpływ na p i druk niezmierzony.
Testy: `tests/sofa/test_audit1023_p9_both_sides.py`,
`test_audit1023_wiring_both_sides.py`, `test_audit1023_wiring_p9_players.py`.

## 4. CS2 (P7, P8-silnik, P12)

**P7 - rating składu bez bramki id drużyny.** `cs2_engine.RatingModel.home_logit`:
para, której id drużyn nie mają obu `MIN_MAPS_RATED`, dostaje p z luki
składu przez własną kalibrację (`fit_unrated`: wyraz wolny z par ocenionych,
nachylenie z punktów walk-forward par nieocenionych). Pary ocenione bez
zmian. Czyta SPORT_CONFIDENCE i `settle_cs2.attach_model`. Bez refitu
krzywych.
Pomiar (`scripts/sofa/measure_audit1023_p7_cs2_lineup_unrated.py`, kopia bazy,
2025-10-23..2026-10-22, ocena od 02-20, bootstrap po seriach): 567 serii /
1 221 map zyskuje liczbę (111 serii w ostatnich 30 dniach); 8 575 serii
ocenionych - 0 zmienionych wierszy. Mapy: log loss 0,628 wobec 0,690 stałej
udziału gospodarza (-0,062 [-0,078; -0,046]); zrealizowane - deklarowane:
gospodarz -0,8 pp [-3,6; +2,0], faworyt +1,7 pp [-0,9; +4,3], nachylenie
1,12 [0,95; 1,33]. Serie: faworyt +2,7 pp [-1,0; +6,3]. Zastrzeżenie: wariant
kalibracji wybrany spośród trzech na tych samych danych. Envy - FaZe 10-21:
dziś p = None, pod przełącznikiem 0,411. Nie mierzone na liniach Superbetu.
Testy: `tests/sofa/test_audit1023_p7_cs2_lineup_unrated.py` (5).

**P8 - nick po prefiksie w silniku.** `cs2_engine.player_id(prefix)`: bez
dokładnego nicku w żadnym ze składów (kolejność rozliczenia,
`cs2.MapResult.player`; przegląd R1 F1) - jeden zawodnik, którego nick >= 5 liter zaczyna nazwę
linii (albo odwrotnie), jak w rozliczeniu; dwóch = nikt. Testy:
`tests/sofa/test_audit1023_p8_cs2_names.py` (6).

**P12 - `model_p` serii rozliczonych z samego wyniku.** `settle_cs2.settle_one`
(ścieżka series-only) woła `attach_model` (błąd -> `model_error`, ocena
zostaje); przełącznik czytany **po zegarze rozliczenia**, bo `model_p`
czyta tylko poranny fit line evidence, nigdy zbudowany kupon. Serie sprzed
przełącznika - jednorazowo (offline, idempotentne, odmawia `SWITCH_OFF`):

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_cs2.py --attach-series-only-model \
    --sweep-from 2026-09-28 --sweep-to 2026-10-23
```

**10-24 rano, przed `refresh_line_evidence.py --before 2026-10-24`** (RUNBOOK
1a). Próba na kopiach (zegar 10-24 06:00Z): 116 serii, 392 linie W/L, 346
dostaje `model_p`, 46 bez (pary nieocenione), 0 błędów, ~10 min.
Testy: `tests/sofa/test_audit1023_p12_cs2_series_only_model.py` (2).

## 5. Siatkówka, kosz, tenis (P13, P11, P14)

**P13 - złoty set.** Fakt Superbetu: Regulamin pkt 5.D.3.a („za oficjalny
wynik uznaje się rezultat uzyskany na boisku w regulaminowym czasie gry”),
brak osobnego zapisu o złotym secie; `resolvingRules` w ofercie siatkówki
puste; żaden rynek czytany przez SHADOW nie dotyczy awansu. Fakt Sofascore:
sety meczu w `period1..N`, złoty set w `overtime`, `winnerCode` na 28 z 90
meczów AET / AGS to zwycięzca dwumeczu (12193496: sety 3-1, winnerCode 2).
- **Rozliczenie (poprawka poprawności, na żywo od 10-23, bez przełącznika):**
  `shadow.GOLDEN_SET_DESCRIPTIONS` = {AET, AGS} tylko dla siatkówki;
  `event_state` -> FINISHED; `build_result` bierze zwycięzcę z setów (tylko
  kompletny mecz do 3, sety == `current`). Na cache 89 z 90 ocenionych
  (15670573: sety 3-0 vs `current` 3-1 -> DATA_MISMATCH). W `settled.json`
  siatkówki 0 rekordów na takim meczu - nic do ponownego rozliczenia
  (`scripts/sofa/measure_audit1023_p13_golden_set.py`). Hokejowy AET bez zmian.
- **Model (`VB_GOLDEN_SET`, 10-24 00:00Z):** `score_model.parse_event(golden_set)`,
  podpięte w `sport_confidence.parse_history` / `TeamGames.build` przez
  `run_sport_confidence`; fity i line evidence zostają przy `False` do refitu.
  Historia +89 meczów, najpóźniejszy 2026-05-01.
Testy: `tests/sofa/test_audit1023_p13_golden_set.py` (9),
`test_audit1023_wiring_score_history.py`; `test_shadow.py::test_event_state`
ma poprawioną asercję (siatkówka AET -> FINISHED).

**P11 - NCAA kosz w połowach: WYŁĄCZONE.** Kod jest
(`score_model.BB_HALVES_COMPETITIONS`, `basketball_halves`, `parse_event(halves)`,
podpięte w SPORT_CONFIDENCE), przełącznik `None`, bo: (a) brak NCAA kosza w
ofercie Superbetu (snapshoty 09-29..10-24: zero; oferta do 11-12: zero;
struct ma „USA - NCAA” 36 / 2108 / 33447 i „(K)” 2175 / 33361 bez sportu);
(b) krzywa kosza dopasowana bez NCAA, a mecze NCAA ruszają globalną stawkę
ligi (`RatingBook.global_league`); (c) rozliczenie połów nie istnieje
(`build_result` wymaga 4 kwart). Wrócić, gdy mecz NCAA będzie w snapshocie
SHADOW (~11-03): najpierw rozliczenie połów, potem replay krzywej i wpływ na
inne ligi. Testy: `tests/sofa/test_audit1023_p11_halves.py` (5).

**P14 - tenis, zwycięzca z wyniku w setach.** Z kodu i testu:
`tennis_rating.parse_event(score_winner=True)` / `load_history(score_winner=)`:
mecz „Ended” bez `winnerCode` bierze zwycięzcę z kompletnego wyniku w setach
(`winner_from_sets`; nigdy Retired / Walkover / Defaulted, nigdy winnerCode 3),
a strona typu 0, która nie jest drużyną (nie narodowa, bez „/”, bez
subTeams), jest zawodnikiem. 17362029 (ITF M15 Ithaca, 6-0 6-1, winnerCode
null) wchodzi do ratingu tylko z przełącznikiem. Przełącznik ustawiony od
10-24 00:00Z. Podpięcie: SHEET `run_sheet.load_tennis_rating` czyta przełącznik po dniu
budowy i zegarze (rating budowany od nowa w każdym przebiegu, bez cache
między dniami). Pomiar: historia 261 184 -> 261 357 meczów (+173, 0
utraconych); 10-23: te same 184 ze 187 meczów z ratingiem, największy ruch
p wygranej gospodarza 0,018 (jeden > 0,01). Wiersze SHEET tenisa nie mają
znacznika tej reguły - commit musi wejść przed porannym SHEET 10-24.
Testy: `tests/sofa/test_audit1023_p14_tennis_rating.py` (12).

## 6. Piłka: P1, P3, P5, P6

- **P3 piłka - WŁĄCZONE** od 10-24 00:00Z (`"football"` w
  `PLAYER_HISTORY_ANY_TEAM_SPORTS`). Cienka próbka zawodnika (po oknie 20
  meczów) uzupełniana startami tego samego id w składach innych drużyn
  (tylko składy z cache, nigdy po nazwisku). Rówieśnicy = przeciwnicy
  z właściwej próbki strony; mecze każdego z nich przechodzą tę samą
  akceptację co próbka (`samples.peer_history`: zakończone, bez
  towarzyskich, jeden wpis na mecz, RESERVE_SQUAD, jeden skład na id /
  cięcie P1), jeden wiersz na (mecz, rówieśnik), statystyki czytane
  z godziną startu (wiersz tymczasowy nie dowodzi zera). Pomiar
  `measure_audit1023_p3_any_team_football.py` powtórzony 10-23 na tej
  regule (przegląd R2 #1-#3, #8; sekcja 10), mecze 2026-08-01..10-20
  (3 371), historie z cięciem P1: dodane wiersze do druku 5 497 (562 mecze),
  realised - confidence +0,25 pp [-0,82; +1,28], dodane minus bazowe
  +0,07 pp [-1,03; +1,10]; żaden rynek nie wyklucza zera; istniejące wiersze
  bez zmian z konstrukcji -> WŁĄCZONE. Zastrzeżenie: okno = start
  sezonu; środki z udziału (`player_share`) nie widzą obcych meczów.
- **P5 - WŁĄCZONE** od 10-24 00:00Z. Slug Sofascore jako ostatnia reguła
  dopasowania (`match_rule "slug"`); `contracts.PlayerSample` i SETTLE
  (`run_settle.player_token_names`, ocena po `matched_name`) dopisane przez
  główną sesję (`tests/sofa/test_audit1023_p5_settle.py`). Test fałszywych
  trafień: 15 423 składy, 600 124 wpisy - ten sam człowiek 24 321, inny 0;
  na żywo 10-21..10-23 odzyskane 4 / 4 / 6 nazw, każda z jednym id.
- **P6 - WYŁĄCZONE**, refit nie zainstalowany: poza próbą log loss +0,00030
  [-0,00025; +0,00086], na wierszach, które oceniał stary czytelnik
  +0,00080 [+0,00025; +0,00141] - gorzej.

- **P1 - WŁĄCZONE** od 10-24 00:00Z. Strona z `ENTITY_CONFLICT` zachowuje
  najnowsze 10 meczów po najnowszym starciu (tylko gdy ma ich 10 - to
  dokładnie to, co czyta replay krzywych); 2 turnieje towarzyskie w nowym
  kluczu `excluded_from_sample_conflict_cut`, czytanym tylko pod
  przełącznikiem (kategorie w JSON niezweryfikowane w payloadzie). Pomiar
  `measure_audit1023_p1_conflict_cut.py`, piłka 2025-10-01..10-20 (427 031
  meczów): odzyskane 8 339 stron w 7 709 meczach; wiersze do druku
  odzyskane 93 631 (6 269 meczów): realised - confidence +0,51 pp [+0,15;
  +0,85], odzyskane minus czyste +0,35 pp [-0,05; +0,75]; wiersze bez
  starcia bez zmian. Jeden rynek z 23 poniżej: shots_for -4,6 pp [-6,6;
  -2,6] (2 144 wiersze) - tyle daje przypadek, pilnuje go line evidence. Na
  żywo 10-21..10-23: 8 z 12 stron odzyskanych.

> Wyniki agentów A i F są wyżej w tej sekcji (i w sekcji 5); stan w kodzie:
> P1, P5, P3-piłka i P14 od 2026-10-24 00:00Z, P6 `None`.

## 7. Podpięcie i smoke

Podpięcie (agent G): `run_sport_confidence.py` (P7 `build_ratings(..., True)`,
P8 `model_probability(name_rules=True)`, P13 / P11 flagi historii; nowa
właściwość `DbForecaster._day` - bez daty dzień zegara buildu, bo `str(None)`
porównywałby się jako późniejszy od każdej daty), `sport_identity.py` (P8 w
ścieżkach CS2), `run_sport_identity.py` (P4 weto), `refresh_sport_history.py`
(P9 `last_side` po każdym refreshu, `--both-sides-only`), `player_model.py`
i `settle_shadow.py` (P9, P3 w liczbie rozliczeniowej). Każde podpięcie: przy
wyłączonym przełączniku argument nie jest przekazywany.

Smoke offline SPORT_CONFIDENCE 10-23 (kopia wejść, kopia bazy, P7 / P8 / P13
przestawione na 10-23, zegary 08:51Z i 14:00Z): 0 zmienionych nóg i 0
zmienionych p w każdym sporcie (o 08:51Z hokej 513 / kosz 58 / siatkówka 0 /
CS2 6 nóg) - tego dnia brak nieocenionej pary CS2 wśród otwartych serii.
Smoke nie obejmuje P8 w SPORT_IDENTITY (tylko test).

## 8. Co zostaje / niesprawdzone

- P3 hokej: line evidence `player_*` zbudowane na starym p; pierwsze dni po
  10-24 czytają kubełki z innego p. Refit kosza na czytelniku any-team -
  otwarte.
- P3: 1 nowy inny gracz w ścieżce nazw hokeja - nie ustalono którego.
- P4: kalibracja dodanych nóg siatkówki niezmierzona; hokej / kosz poza zakresem.
- P7: wpływ na drukowane nogi CS2 niezmierzony na liniach Superbetu; wariant
  kalibracji wybrany na tych samych danych.
- P9: wpływ na p i druk niezmierzony; `fit_player_model.py` czyta tylko `last`.
- P11: rozliczenie połów niezaimplementowane.
- P12: jednorazowy backfill 10-24 rano jeszcze nieuruchomiony na `runs/sofa/`.
- SHADOW_SETTLE: liczba rozliczeniowa nie czyta stałych dnia
  (`params_path_for`) ani transliteracji P8 - nie wchodzi do druku ani do
  line evidence.

## 9. Bramki

Wyniki bramek z raportów agentów (przed sekcją 6): ruff i `mypy --strict`
czyste na dotkniętych plikach, `check_test_registry.py` 0 uwag, pełne
`pytest tests/sofa`: 5 895 passed, 1 failed -
`test_audit1023_p3_any_team_football.py::test_the_player_switches_by_day_and_build_clock`
(test agenta A w toku: nie podmienia `PLAYER_HISTORY_ANY_TEAM_SPORTS`).
Po sekcji 6 (commit 0a6f39af): pełne `pytest tests/sofa` - 5 918 passed, 0
failed; z poprawkami przeglądu (dossier: reguły nazw zawodnika) 5 923 passed,
2 skipped, 0 failed.

## 10. Przegląd iteracyjny 2026-10-23 wieczór

Runda 1: czterech recenzentów nad `625d89e7..HEAD` (tylko odczyt, bez sieci,
kopia bazy `data/refit_2026-10-23_allin/sofa_copy.db`), potem trzech
naprawiających (X1 sporty, X2 piłka, X3 dokumentacja / agenci) i ta
dokumentacja (X4). Nic nie zatwierdzone (bez commita).

**R1 - sporty (4 uwagi, MINOR):**
- F1 P8: prefiks nicku drużyny 1 wygrywał z dokładnym nickiem drużyny 2 ->
  poprawione: dokładny nick w obu składach przed prefiksem
  (`cs2_engine._nick_on_team`, `model_probability`), jak w rozliczeniu;
  test `test_audit1023_p8_cs2_names.py`.
- F2 P7: pary bez ratingu czytają człony kolejności map / puli z par
  ocenionych (niezmierzone) -> zmierzone, kod bez zmian: grupa bez ratingu
  567 serii / 1 221 map, walk-forward, log loss -0,0017 [-0,0037; +0,0002]
  wobec wersji bez członów, faworyt +0,4 pp [-2,2; +2,8], nachylenie 1,08 -
  skalibrowane, `p_map_nr` zostaje (docstring `cs2_engine.p_map_nr`).
- F3 P12: rozliczenie CS2 biegnące równolegle mogło nadpisać dopisane
  `model_p` -> poprawione: `settle_cs2.keep_attached_models` pod blokadą
  pliku; testy w `test_audit1023_p12_cs2_series_only_model.py`.
- F4 P2: odmowa strony drugiej drużyny nie blokowała `NOT_ON_SOFASCORE` ->
  poprawione: zostaje `NO_GAME_WITHIN_1H`, pole
  `absence_contradicted_by_second_team`; test
  `test_audit1023_p2_fresh_recheck.py`.

**R2 - piłka / tenis (9 uwag, MINOR):**
- #1, #2, #3, #8 P3 piłka: mecz dwóch rówieśników liczony raz, rówieśnicy
  bez akceptacji próbki właściwej, pomiar nie odpowiadał regule na żywo,
  statystyki bez godziny startu -> poprawione (`samples.peer_history`,
  wiersz na (mecz, rówieśnik), `get_event_stats(kickoff_ts=...)`; test
  `test_audit1023_p3_peer_acceptance.py`); pomiar powtórzony na regule na
  żywo: 5 497 dodanych wierszy do druku w 562 meczach, +0,25 pp [-0,82;
  +1,28], dodane minus bazowe +0,07 [-1,03; +1,10] - piłka zostaje w
  `PLAYER_HISTORY_ANY_TEAM_SPORTS` (sekcja 6; pomiar sprzed
  przeglądu nieaktualny). Uwaga: #3 częściowo błędna - stary pomiar też
  brał rówieśników z 10 najnowszych meczów.
- #4 refit: P1 / P3 / P5 / P14 poza listami przełączników replayu ->
  ostrzeżenia (`prepare_refit.UNREPLAYED_AUDIT_SWITCHES`,
  `replay_switch_warnings`; `fit_sport_confidence.py` dla P7 / P13,
  `fitted_from.unreplayed_switches`), nigdy odmowa; test
  `test_refit_audit1023_switches.py`.
- #5 P14: mecz kobiecy tylko po płci gospodarza -> którakolwiek strona „F”
  (`tennis_rating.parse_event`); test `test_audit1023_p14_female_either_side.py`.
- #6 `find_friendly_competitions.py`: klucz
  `excluded_from_sample_conflict_cut` traktowany jako przejrzany; test
  `test_find_friendly_reviewed_ids.py`.
- #7 P5: dossier nie znajdował zawodnika po slugu -> poprawione przez X3
  (dossier czyta `matched_name` próbki). Notatka SHEET dla sluga
  (`PLAYER_NAME_SLUG` w `run_sheet.player_coverage_notes`) - nie dodana.
- #9 `rebuild_plan` bez znaczników P1 / P3 / P5 / P14 - zostawione (niżej).

**R3 - dokumentacja / agenci (10 uwag):** F1 kolejność kroku P12 w
`sofa-day.md` 1a, F2 agenci nie znali zmian 10-24 (skille), F3 dossier
a reguły nazw (slug / transliteracja / inner_surname), F4 / F5 / F6 / F7 /
F8 / F9 rozjazdy dokumentów z kodem (zbiór `{hokej, piłka}`, tabela
przełączników, otwarte pytania, CLAUDE.md, commands.md, CONFIG.md) -
wszystkie poprawione przez X3 (test `test_dossier_match_rules.py`). F10
znacznik nóg CS2 z kalibracji par bez ratingu -> poprawione przez X1:
`lineup_unrated_rule: "cs2_lineup_unrated_1023"`
(`cs2_engine.LINEUP_UNRATED_RULE`, `run_sport_confidence`; test
`test_audit1023_p7_unrated_marker.py`), także w skillu analityka sportu.

**R4 - próba generalna e2e** (kopie APFS 10-23, sieć zablokowana, przełączniki
audytu przestawione na 10-23 00:00Z, zegary etapów prawdziwego dnia; ON vs OFF):
bez awarii na każdym etapie offline. SPORT_CONFIDENCE OFF = prawdziwy plik
(592 nogi), ON 596 (siatkówka 15 -> 19, P13). SHEET 64 973 vs 64 743 wierszy
(piłka +234, propsy; P14 zmienia p na 5 901 wierszach tenisa, 25 o > 5 pp; bez
NaN). CONFIDENCE 4 009 vs 4 010; kupon 4 520 vs 4 517 pozycji, 0 naruszeń
reguł druku, `verify_legs --all` DEFECT 0. Model zawodników hokeja: p zmienia
się na 136 z 1 026 wierszy (66 o > 5 pp). P12 attach: 116 serii, 392 linie,
346 z `model_p`, 0 błędów, 8,5 min. Line evidence: CS2 +346 wierszy. 45
skryptów procedury importuje się i parsuje argumenty. Nie próbowane (most /
sieć): BOARD, RESOLVE, OFFER, snapshoty SHADOW / CS2, zachowanie
SPORT_IDENTITY (P2 / P4 / P8 - tylko brak awarii), FIXTURE_CHECK, ocena w
SETTLE, agenci.

**Incydent R4:** `read_set.py` pomijał `SOFA_RUNS_DIR` i pierwsza próba zapisała
`runs/sofa/2026-10-23/read_set/` i `dossier/` z prawdziwego kuponu (~20:02
lokalnie); przywrócone z klona ~20:05 (tylko daty plików nowe). Pliki kuponu,
`reads.json` i księga nietknięte (md5). Poprawka: `read_set.py`,
`merge_reads.py`, `build_slip.py`, `verify_legs.py` biorą domyślny
`--runs-dir` z `SOFA_RUNS_DIR`, a trzy piszące odmawiają przy `SOFA_NOW` na
prawdziwym katalogu (`tests/sofa/test_scripts_honour_runs_dir_env.py`).

**Runda 2 (R5, przegląd poprawek):** bez blokad; poprawione:
`settle_cs2.keep_attached_models` bierze pola modelu tylko z rekordu tej samej
serii i tej samej kolejności drużyn; dossier szuka `matched_name` próbki tylko
po stronie zawodnika. Obserwacja bez zmiany: P1 w `peer_history` zeruje
rówieśnika ze starciem 5-19 meczów wstecz (ta sama reguła co próbka, zmierzona).
Do obserwacji pierwszych dni: nogi zawodników hokeja (line evidence dopasowane
na starym p), siatkówka (krzywa dopasowana bez P13).

**Zostaje:**
- `rebuild_plan` bez znaczników P1 / P3 / P5 / P14 (R2 #9): SAMPLES /
  SHEET dnia 10-24 zbudowane przed 00:00Z zostałyby na starych regułach,
  a przebudowa by ich nie powtórzyła. Dziś dla 10-24 istnieje tylko
  `sport_fixtures.json`; sofa-day biegnie po północy.
- P14 jako odtwarzana flaga refitu (`--tennis-score-winner` w
  `calibrate_from_cache` / `RatingReplay.from_db` i w `REPLAYABLE_SWITCHES`)
  - na razie tylko ostrzeżenie.
- P9 w `fit_player_model.py` (czyta tylko `last`).
- Znacznik P7 tylko na nogach (`08_confidence_sports.json` ->
  `11_coupon.json`); rozliczone wiersze CS2 (`settle_cs2.attach_model`) i
  księga go nie niosą.
- Notatka SHEET dla dopasowania po slugu (R2 #7, druga połowa).

Bramki naprawiających: X1 5 958 passed, 2 skipped; X2 5 952 passed, 2
skipped (potem tylko komentarz w `epochs.py`, podzbiór 544 passed); ruff,
`mypy --strict --no-incremental` czyste, `check_test_registry.py` 0 uwag.

## 11. Próba generalna na żywym moście (R6, 2026-10-23 19:21-20:15Z)

Dzień 2026-10-24 zbudowany na żywo w katalogu na brudno (`SOFA_RUNS_DIR`) i na
klonie bazy (`SOFA_DB_PATH`), wszystkie przełączniki audytu oraz
`LIVE_ONLY_CURVE_REFUSED` przestawione na 2026-10-23 00:00Z (hook), most
Sofascore i Superbet prawdziwe: 11 030 zapytań do Sofascore i 3 164 do
Superbetu, 0 odmów, breakery zamknięte. Każdy etap bez Traceback i bez FAILED:
BOARD 1 341, RESOLVE 1 312 (recall 98,2%), OFFER 1 312 (0 błędów), SAMPLES (P1:
16 notatek cięcia, P3: 181 uzupełnień, P5: 90 próbek po slugu), SHEET 199 155
wierszy bez NaN, CONFIDENCE 13 591 nóg, FIXTURE_CHECK, SHADOW / CS2 (D i D+1),
SPORT_IDENTITY (hokej 74/75, kosz 138/140, siatkówka 84/101, CS2 15/20; 13
zdarzeń już przypiętych w żywym pliku - te same id), SPORT_CONFIDENCE 472 nogi,
COUPON_ASSEMBLY 13 716 pozycji i 12 builderów (0 naruszeń reguł druku, każda
noga słowami Superbetu), PDF / HTML, read_set (284 nogi do czytania, zgodnie z
C3), rebuild_day `--dry-run`, late RESOLVE, `verify_legs` DEFECT 0. Izolacja
czysta (md5 plików kuponu 10-21..10-23, `reads.json`, księga bez zmian; nic w
`config/`; żaden proces nie trzymał `data/sofa.db`).

Poprawione: COUPON tworzył pusty `vetoes.json` po `06_coupon.json`, więc
pierwszy rebuild każdego dnia dokładał zbędny krok COUPON (`run_coupon.py`,
asercja w `tests/sofa/test_e2e.py`).

Nie dało się sprawdzić wieczorem: tenis cienki (107 meczów), brak linii
zawodników hokeja (P3 / P8 hokej), żadne zdarzenie w 3 h przed startem (P2
świeże pytanie), P7 (brak pary bez ratingu), P12 attach i refit line evidence
(zrobione offline w R4), rozliczenia, rebuild nie na sucho, analitycy.
