# Raport 2026-10-18: krzywe historii per linia (piłka)

Zlecenie operatora: „Popraw!” - przeszacowanie `goals_for` na drukowanych
nogach 10-09..10-17. Dowody: `docs/sofa/evidence/line_curves_2026-10-18.md`.

## Co się okazało

- Krzywa `goals_for` na wszystkich rozliczonych wierszach z ceną jest
  skalibrowana (OVER -0,9 pp, UNDER -0,9 pp, przedziały z zerem); luka na
  drukowanych nogach to głównie selekcja x >= 0,90
  (`selection_walk_forward_2026-10-18.md`), nie wada krzywej.
- Prawdziwa wada siedzi w **linii**: krzywa jest wspólna dla całej siatki linii
  replayu, a p modelu nie jest jednakowo skalibrowane na liniach. Strona
  „trudna” blisko środka przeszacowana (np. `goals_for` UNDER 1,5 -3,85 pp na
  62 tys. wierszy testu), dalekie linie niedoszacowane - suma wychodzi na zero.
  Dotyczy prawie każdego rynku liczbowego piłki.

## Co weszło

| zmiana | gdzie | stan |
|---|---|---|
| krzywa per linia dla 33 kluczy | `bet.sofa.line_curves`, `confidence.Calibration.realised(..., line=)`, sekcja `by_market_direction_line` | zainstalowana 12:04:33Z |
| przełącznik | `epochs.LINE_CURVES_FROM_UTC` 2026-10-19 00:00Z | następny dzień (stała zgoda operatora) |
| lista kluczy | `config/sofa_line_curves.json` | 33 klucze lepsze poza próbą; 6 gorszych i 60 bez różnicy zostaje przy krzywej wspólnej |
| fit | `fit_confidence.py` (każdy pełny fit + `--line-curves-only`) | refit odtwarza sekcję sam |
| instalacja | `scripts/sofa/install_line_curves.py` | kopia `config/backup_2026-10-18_line_curves/`, testy, przywrócenie |
| line evidence | `fit_line_evidence.sheet_rows(per_line=)` | baza wg reguły dnia `--before` |
| CONFIDENCE | `run_confidence.py` | linia przekazywana tylko pod przełącznikiem, tylko piłka |
| ledger | `audit_ledger.EPOCH_GROUPS` „od 10-19” | nowa epoka, dzień nie jest mieszany |
| pomiar | `scripts/sofa/measure_line_curves.py` | w repo |
| sprawdzian | `T-LINE-CURVES` (PROPOSED) | od 10-19 |

## Liczby

- Historia poza próbą, linie Superbetu, p >= 0,70: log-loss -6,4e-4 [-7,0;
  -5,8], średnia |luka| linii 1,21 → 0,92 pp.
- Wiersze z życia 10-09..10-17 (krzywe bez wierszy z życia; replay ma odtworzone
  mecze 10-09..10-12, więc nie w pełni poza próbą): luka -1,09 →
  -0,57 pp; ROI -4,54% → -4,53% - **bez przewagi nad ceną**.
- E2E 10-18 (prawdziwy dzień, zegar 07:08:38Z): wyłączony = prawdziwe
  `08_confidence.json` co do nogi; włączony +57 / -300 nóg; single zawodników
  52 → 41 (strzały na linii 1,5, przeszacowane przez krzywą wspólną).
- E2E 10-15..10-17 (rozliczone): jednostki -599,0 → -582,9, odpadłe 167 nóg
  ROI -9,2%, dodane 35 +2,2%; w granicach szumu.

## Review (iteracyjnie)

- Runda 1: BLOKER - `one_sided_single` uznawał tylko źródło `market:`, więc
  krzywa per linia wycięłaby 47 z 52 singli zawodników; poprawione
  (`OWN_CURVE_SOURCES`) z testem i ponownym E2E. POWAŻNE - definicje
  weryfikatora i analityków traktowałyby źródło `line:` jako defekt;
  zaktualizowane (`.claude/agents/sofa-verifier.md`,
  `sofa-analyst-football.md`, skille `sofa-analysis-core`, `sofa-pipeline`).
  Definicje agentów wczytują się przy starcie sesji: sesja, która zbuduje
  10-19, musi wystartować po tej zmianie. Mniejsze: osłona braku linii
  (`leg_line`), pomiary za regułą dnia, etykieta źródła w PDF, zachowane
  wcięcie pliku krzywych przy instalacji, odmowa `--line-curves-only` do
  zainstalowanego pliku, opisy ograniczeń pomiaru.

## Uczciwie

To poprawka kalibracji (pewność bliżej prawdy, mniej nóg, które drukowały się
za wysoko), nie źródło zysku. Ryzyka do obserwacji: offsety line evidence z
poprzednich poranków liczone na starej bazie (pierwsze dni mogą obniżać
podwójnie - ostrożnie); cap pasma ceny działa progowo i mała zmiana bazy
przeskakuje próg w obie strony (bez zmiany reguły - osobna decyzja).

## Bramki

`tests/sofa`, ruff, mypy --strict, rejestr - wyniki w commicie (sekcja
„Gates” komunikatu).
