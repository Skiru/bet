# K2: reguła DAY_ANCHOR — raport (2026-10-14)

Plan: `docs/sofa/history/PLAN_MAPA_DRUZYN_2026-10-14.md`, krok K2. Backtest:
`scripts/sofa/measure_day_anchor.py`, wynik
`docs/sofa/evidence/day_anchor_backtest_2026-10-14.md`.

## Reguła

Hokej / kosz / siatka (`sport_identity.match_shadow`, `day_anchor=True`): gdy
w listingu nie ma meczu z obiema nazwami, **jedyny mecz drużyny-kotwicy**
(strona z rozpoznanym id) w oknie ±1 h od startu Superbetu — ten sam sport,
płeć tablicy, nie przełożony / odwołany — jest tym zdarzeniem, bez względu na
nazwę drugiej strony. `match_method: "DAY_ANCHOR"`, `name_scores` zostają w
rekordzie. Odmowy: dwa takie mecze → `AMBIGUOUS`; własne id drugiej strony,
którego w meczu nie ma (albo id kotwicy po złej stronie) →
`RESOLVED_ID_DISAGREES`. Drużyna tylko „do zapytania” (`query_id`, bez id)
nie jest kotwicą. Za przełącznikiem `epochs.DAY_ANCHOR_FROM_UTC` = 2026-10-15
00:00Z (dzień i zegar). Nazwa przeciwnika **nigdy nie jest uczona** — trafia
do kolejki kandydatów (`entity_map.OPPONENT_METHODS`).

To świadomie luzuje dotychczasową zasadę „druga drużyna musi być nazwana w
listingu” (`test_the_other_team_must_be_named_in_the_listing` — zostaje dla
wyłączonego przełącznika; przy przełączniku Sparta – Kometa wobec Sparta –
Liberec nadal odmawia, gdy Kometa ma własne id), z jednego powodu: klub nie
gra dwóch meczów w godzinę.

## Pomiar (2026-10-05..10-14, tylko odczyt)

Kandydaci: wszystkie zapisane mecze drużyny-kotwicy (`sofa_listed_event`,
strony `sofa_entity_events`, `cs2_series`), z **najnowszą pobraną wersją**
każdego meczu. Pierwsze uruchomienie dało 2 błędy precyzji — oba były
artefaktem backtestu: stara strona z cache (sprzed zamiany terminów przez
Sofascore) nadpisywała wersję po meczu (Rouen – Chamonix 10-09: rozegrany
16355418 na starej stronie miał datę 2027-01-22, a jego przełożony bliźniak
16355274 — 10-09 18:00). Po poprawce:

| sport | IDENTIFIED, nazwa przeciwnika ukryta (id kotwicy z chwili identyfikacji) | NOT_IDENTIFIED: reguła wskazuje | z tego potwierdzone później przez SETTLE | sprzeczne z SETTLE |
|---|---|---|---|---|
| hokej | **591 / 591** | 23 | 21 | 0 |
| kosz | **793 / 793** | 60 | 41 | 0 |
| siatka | **194 / 194** | 25 | 17 | 0 |
| CS2 (zmierzone, niewłączone) | 228 / 228 | 20 | 10 | 0 |

Okno: 2 h dodaje jeden mecz kosza (Kavkasia – Lausanne / BC CIU – Pully
Lausanne, +2 h), 3–4 h nic w sportach klubowych; w CS2 rośnie tylko
niejednoznaczność (17 → 66 `AMBIGUOUS` na IDENTIFIED). Okno zostaje **1 h**.

**Zysk na żywo jest mniejszy niż kolumna „wskazuje”.** Większość tych meczów to
`NO_GAME_WITHIN_1H` — listing w chwili identyfikacji meczu nie miał, SETTLE
znalazł go później; tego DAY_ANCHOR nie naprawi (to K6: ponowne pytanie).
Na żywo pomaga przy `NO_MATCH_IN_LISTING`: w 10 dni hokej 2, kosz 6, siatka 4.
Powtórka kodu na listingach z cache dnia 10-13 / 10-14 (`match_shadow` z
przełącznikiem): 8 meczów zidentyfikowanych — Tryhoop Okayama – Kagawa Five
Arrows, Kuzeyboru – Türk Hava Yolları, BK Liepāja – TalTech/Alexela, KK
Spartak Office Shoes – Hapoel Netanel Holon, Skyliners Juniors – Dragons
Rhöndorf, Schweriner SC – Dresdner SC, Hapoel Kfar Saba – S.C Eilabun, ETV
Hamburg – SWE Volleyteam (Erfurt); MZT Skopje – Tartu odmówione
(`RESOLVED_ID_DISAGREES`).

## Dlaczego nie CS2 i nie tenis

- **CS2:** serie się opóźniają (starty SETTLE z 10-05..10-14 do 2–4 h od
  Superbetu), drużyna gra kilka serii dziennie, a 10-06 BAKS – Clutchain
  (Superbet) było o tej samej godzinie BakS – OldBoys (Sofascore) — decyzja
  zapisana w `test_cs2_anchored_another_opponent_is_not_this_series`. Wśród
  10 niepotwierdzonych wskazań CS2 jest Copenhagen Wolves – „Ex - Eternal Fire
  Academy” jako Copenhagen Wolves – Bread Eaters. CS2 zostaje przy regule
  przeciwnika.
- **Tenis** (K0): zawodnik bywa podmieniany (Biro – Pankratova jako Biró –
  Kalyakina). Tenis to RESOLVE, krok K8.

## Ryzyko zostawione otwarte

Wśród 12 niepotwierdzonych wskazań sportów klubowych z `NO_MATCH_IN_LISTING`
jedno ma innego przeciwnika: **BC Barcelos (K) – Francisco Franco (K)**
(Superbet) = **BC Barcelos – CAB Madeira** (Sofascore, LFB kobiet, 10:00).
Kotwica jest pewna (jedyny mecz Barcelos w godzinie), ale nie wiadomo, kto
grał: jeśli Sofascore ma złego przeciwnika, noga byłaby liczona na
statystykach złego rywala. Reguła nie uczy tej nazwy (kandydat). Kontrola na
nowych danych: każde `DAY_ANCHOR` sprawdza SETTLE (sprzeczność =
`T-IDENTITY-unexplained` FAILED, przełącznik cofa operator).

## Zmiany

- `src/bet/sofa/sport_identity.py`: `day_anchor_orientation`, `match_shadow(...,
  day_anchor)`, `identify_event` / `identify(..., day_anchor)`.
- `scripts/sofa/run_sport_identity.py`: `day_anchor=epochs.day_anchor(date, at)`.
- `src/bet/sofa/epochs.py`: `DAY_ANCHOR_FROM_UTC`, `day_anchor()`.
- `src/bet/sofa/entity_map.py`: `DAY_ANCHOR` w `OPPONENT_METHODS`; strona,
  której id resolver miał już w chwili identyfikacji (`team1_id` /
  `team2_id`), jest uczona (to tylko utrwalenie tego, co wiedział indeks) —
  `reteach_sides` / `backfill_entity_map.py --reteach` zastosowane 09:59Z:
  11 nazw nauczonych, 16 kandydatów zamkniętych (`HELD`), kopia
  `data/backup_entity_map_20261014T095927Z/`.
- `scripts/sofa/measure_day_anchor.py` (backtest), testy
  `tests/sofa/test_day_anchor.py` (12), `tests/sofa/test_entity_map.py` (+1).

## Odstępstwo od planu

Plan K2 zakładał pobieranie listingu dnia (`scheduled-tournaments` +
`unique-tournament/{ut}/scheduled-events`). Pomiar pokazał, że DAY_ANCHOR na
żywo działa na listingu, który SPORT_IDENTITY już pobiera — **zero
dodatkowych zapytań mostka**. Listing dnia jest potrzebny tam, gdzie żadna
strona nie ma id (K3) i do dowodu braku (K5) — tam go dodam.
