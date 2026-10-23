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
| P1 | `SAMPLE_CONFLICT_CUT_FROM_UTC` | `None` | pomiar w toku (sekcja 6) |
| P2 | `IDENTITY_FRESH_RECHECK_ALL_FROM_UTC` | **10-24 00:00Z** | bez pomiaru, kod + testy |
| P3 | `PLAYER_HISTORY_ANY_TEAM_FROM_UTC`, `PLAYER_HISTORY_ANY_TEAM_SPORTS` = {hokej} | **10-24 00:00Z, tylko hokej** | hokej lepszy; kosz gorszy; piłka - pomiar w toku |
| P4 | `SPORT_QUERY_ANCHOR_FROM_UTC` (`QUERY_ANCHOR_SPORTS` = {siatkówka}) | **10-24 00:00Z** | backtest 0 złych na 2 480 |
| P5 | `PLAYER_SLUG_NAME_FROM_UTC` | `None` | pomiar w toku |
| P6 | `PLAYER_OMITTED_ZERO_FROM_UTC` | `None` | pomiar w toku |
| P7 | `CS2_LINEUP_ELO_UNRATED_FROM_UTC` | **10-24 00:00Z** | dodane skalibrowane, stare bez zmian |
| P8 | `NAME_RULES_1023_FROM_UTC` | **10-24 00:00Z** | bez pomiaru |
| P9 | `PLAYER_BOTH_SIDES_LISTED_FROM_UTC` | **10-24 00:00Z** | bez pomiaru |
| P10 | - | zamknięte bez zmiany | Katar 2345 -> 39366: brak sezonu u źródła |
| P11 | `BB_HALVES_LEAGUES_FROM_UTC` | `None` | brak NCAA kosza w ofercie Superbetu |
| P12 | `CS2_SERIES_ONLY_MODEL_P_FROM_UTC` | **10-24 00:00Z** (zegar rozliczenia) | bez pomiaru |
| P13 | rozliczenie: bez przełącznika; model: `VB_GOLDEN_SET_FROM_UTC` | rozliczenie **na żywo od 10-23**; model **10-24 00:00Z** | poprawka poprawności + fakt Superbetu ustalony |
| P14 | `TENNIS_RATING_SCORE_WINNER_FROM_UTC` | **10-24 00:00Z** (ustawiony) | bez pomiaru; podpięcie i liczenie w toku (sekcja 6) |

## 2. Tożsamość sportów (P2, P4, P8-CS2)

**P2 - świeża strona i druga drużyna.** `sport_identity.identify_event`
(`fresh_all`): ponowne pytanie o świeżą stronę drużyny (K5) odpala się przy
KAŻDEJ odmowie przeczytanej z cache w `FRESH_RECHECK_WITHIN` (3 h) od startu,
w każdym sporcie, raz na drużynę na przebieg; gdy dalej nic, pytana jest
strona drugiej drużyny (jej id, bez niego id z zapytania; najpierw cache,
świeża w oknie). Pola rekordu: `second_team_id`, `second_listing_from_cache`,
`second_fresh_recheck`, `identified_by_second_team` / `second_team_reason`.
`NOT_ON_SOFASCORE` czyta dalej tylko stronę pierwszej drużyny; breaker /
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
dokładnego nicku - jeden zawodnik, którego nick >= 5 liter zaczyna nazwę
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

## 6. Piłka: P3, P5, P6 (zdecydowane) i P1 (pomiar w toku)

- **P3 piłka - WŁĄCZONE** od 10-24 00:00Z (`"football"` w
  `PLAYER_HISTORY_ANY_TEAM_SPORTS`). Cienka próbka zawodnika (po oknie 20
  meczów) uzupełniana startami tego samego id w składach innych drużyn
  (przeciwnicy z próbki, tylko składy z cache, nigdy po nazwisku). Pomiar
  `measure_audit1023_p3_any_team_football.py`, mecze 2026-08-01..10-20
  (3 371): dodane wiersze do druku 4 247 (458 meczów), realised - confidence
  +0,52 pp [-0,68; +1,73], dodane minus bazowe +0,36 pp [-0,92; +1,61];
  istniejące wiersze bez zmian z konstrukcji. Zastrzeżenie: okno = start
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

> **P1 - pomiar historii w toku** (cięcie próbki przy `ENTITY_CONFLICT` +
> 2 turnieje towarzyskie w nowym kluczu
> `excluded_from_sample_conflict_cut`). Na żywo 10-21..10-23: 12 stron z
> `ENTITY_CONFLICT`, 8 odzyskanych. `SAMPLE_CONFLICT_CUT_FROM_UTC` = `None`
> do wyniku replayu.

> **Miejsce na wyniki - NIE są to decyzje.** W chwili pisania (2026-10-23)
> pomiary agentów A (piłka: P1 cięcie próbki przy `ENTITY_CONFLICT` +
> 2 turnieje towarzyskie, P5 slug zawodnika, P6 zera spalonych zawodników
> i refit rodziny `player_offsides_for`, P3 piłka) i F (P14: liczba meczów
> dodanych do ratingu tenisa, podpięcie w SHEET) nie są zakończone.
> Stan w kodzie: `SAMPLE_CONFLICT_CUT_FROM_UTC`, `PLAYER_SLUG_NAME_FROM_UTC`,
> `PLAYER_OMITTED_ZERO_FROM_UTC` = `None`; „football” poza
> `PLAYER_HISTORY_ANY_TEAM_SPORTS`; `TENNIS_RATING_SCORE_WINNER_FROM_UTC` =
> 10-24 00:00Z. Ta sekcja, `CLAUDE.md` i `model-state.md` dostaną wyniki po
> ich zakończeniu.

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
