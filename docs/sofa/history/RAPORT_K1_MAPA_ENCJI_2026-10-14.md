# K1: mapa encji Superbet → Sofascore — raport (2026-10-14)

Plan: `docs/sofa/history/PLAN_MAPA_DRUZYN_2026-10-14.md`, krok K1. Miernik:
`docs/sofa/evidence/identity_coverage_2026-10-14/K0_pomiar_2026-10-14.md`.

## Co zmienione

- **`bet.sofa.entity_map`** — jedna mapa w `sofa_entity`, nowe kolumny
  `source` (NULL = mapa sprzed K1: RESOLVE, SHADOW_SETTLE, backfill_cs2;
  `resolve`, `backfill_cs2`, `identity_names`, `manual`) i
  `evidence_event_id`; nowe tabele `sofa_entity_conflict`,
  `sofa_entity_candidate` (kolejka NEEDS_ALIAS), `sofa_tournament_map`,
  `sofa_entity_taught` (jedna lekcja na mecz Sofascore). Schemat w
  `db.migrate`.
- **SPORT_IDENTITY uczy się** (`run_sport_identity.learn`, osobne połączenie
  do zapisu, po zapisaniu `sport_fixtures.json`; błąd zapisu nie psuje
  etapu): strona potwierdzona własną nazwą (`LISTING_NAMES`,
  `LISTING_ID_AND_NAME`, `CS2_PICK_EVENT`, wynik nazwy > 82) →
  `identity_names`; strona tylko z reguły przeciwnika → kandydat; nazwa
  trzymana z innym id → konflikt. Rekord ma teraz też `sofascore_home` /
  `sofascore_away` (nazwy osobno).
- **Konflikt nigdy nie nadpisuje** — `entity_map.learn` od razu,
  `cache.save_entity` (RESOLVE, SHADOW_SETTLE) od przełącznika; konflikt jest
  zapisywany zawsze.
- **RESOLVE uczy mapę turniejów** (`run_resolve.learn_tournaments`, klucz
  `id:<id turnieju Superbetu>`, licznik `tournament_map_events` w podsumowaniu).
- **Odczyt za przełącznikiem** `epochs.ENTITY_MAP_FROM_UTC` = 2026-10-15
  00:00Z (dzień i zegar): `TeamResolver(learned=...)`,
  `player_model.resolve_team(..., learned)` (+ znacznik `entity_map_rule`
  na wierszu po nazwie, przenoszony do `settled.json` przez `MODEL_KEYS`),
  `cache.get_entity`. CS2 czyta wyłącznie wiersze nauczone. Wyłączony =
  zachowanie sprzed K1 (testy: `tests/sofa/test_entity_map.py`, 15).
- **`scripts/sofa/backfill_entity_map.py`** — jednorazowe uczenie z dni na
  dysku; `--dry-run` robi wszystko w jednej transakcji i ją wycofuje.

Zmiana względem planu: plan zakładał zapis „obu stron” po każdym
`IDENTIFIED`. Strona potwierdzona tylko wspólnym słowem (reguła przeciwnika)
nie jest uczona — RESOLVE od dawna odmawia tego samego (`remember()`: „wspólne
słowo to dowód o jednym meczu, nie o nazwie”), a K0 pokazał, że przeciwnik w
listingu bywa inną osobą. Trafia do kolejki z kandydatem (id i nazwa z meczu)
— jedna decyzja człowieka (K4).

## Pomiar przed włączeniem (przypięte mecze 2026-10-05..10-14, tylko odczyt)

| | hokej | kosz | siatka | CS2 |
|---|---|---|---|---|
| nazwy, które dziś nie mają id, a zostaną nauczone | 78 | 286 | 107 | 6 |
| nazwy rozpoznawane dziś indeksem listingów, teraz trzymane (to samo id) | 90 | 263 | 115 | 17 |
| nauczone id ≠ id dzisiejszego resolvera | 0 | 0 | 0 | 0 |
| nazwa przypięta do dwóch id | 0 | 0 | 0 | 0 |
| kandydaci (tylko reguła przeciwnika; nazwa × id) | 5 | 51 | 12 | 3 |

Razem 71 otwartych kandydatów. Turnieje: 1 470 wierszy (piłka 822, tenis 371, kosz 157, hokej 50,
siatka 42, CS2 28).

**Zysk bezpośredni (górna granica, przyczynowo):** 32 mecze niezidentyfikowane
w 10 dni miały stronę, której nazwa nie miała id, a była nauczona z
wcześniejszego meczu (kosz 14, siatka 14, hokej 4; CS2 0). To ~3 mecze dziennie
— zgodne z szacunkiem planu. Większość to `NO_GAME_WITHIN_1H` / `BRIDGE_ABORTED`,
które nazwa sama nie naprawi; mapa jest przede wszystkim warunkiem K2 (kotwica
wymaga id jednej strony).

**Precyzja:** żaden nauczony wiersz nie zmienia odpowiedzi resolvera tam,
gdzie ten już odpowiadał (0 / 962); wiersz nauczony jest czytany przed
indeksem, więc to był warunek.

## Konflikty znalezione (do decyzji)

| sport | nazwa | trzymane | oferowane przez przypięte mecze |
|---|---|---|---|
| CS2 | ninjas in pyjamas | 448738 „Ninjas in Pyjamas Impact” (backfill_cs2, 2026-09-28) | 366560 „NIP” (Team Falcons – NIP 10-14, Inner Circle – NIP 10-12, obie nazwy 100) |
| CS2 | golden horde | 1106544 „Golden Horde” | 1272785 „The Golden Horde” (ex-RUSTEC – The Golden Horde 10-12) |

NIP Impact to inny skład — wiersz backfill_cs2 jest błędny (wpływa na to,
które listingi `backfill_cs2.py` dociąga; resolver CS2 tych wierszy nie
czyta). Naprawa: `purge_entity_alias.py` — decyzja operatora. Golden Horde:
dwa id w Sofascore, nie rozstrzygam.

## Uruchomione na żywej bazie

`backfill_entity_map.py` 2026-10-14 09:39Z (najpierw `--dry-run`, wyniki
identyczne): tylko nowe wiersze; kopia `sofa_entity` w
`data/backup_entity_map_20261014T093901Z/sofa_entity.json`. Do 2026-10-15
00:00Z nic ich nie czyta; dzień 10-14 (zbudowany) nie jest przebudowywany i
nigdy nie przeczyta nauczonych wierszy (reguła dnia).

## Czego nie sprawdzono

- Zapisu w pętlach na żywo: pierwszy przebieg SPORT_IDENTITY nowym kodem
  pokaże licznik `entity_map` w `SOFA_SUMMARY` (pętle uruchamiają każdy krok
  świeżym kodem). Równoległe pętle piszą przez `get_connection` (WAL,
  timeout 30 s) — nie testowane pod obciążeniem.
- Wpływu na druk od 10-15: zmierzona tylko górna granica (32 / 10 dni);
  pierwsze dni po przełączniku pokaże `measure_team_identity.py`.
