# Plan na noc 2026-10-14/15: krzywe z historii dla nowych rynków

Zgoda operatora (2026-10-14 ~14:45Z): „zbudować krzywe dla tych wszystkich
rynków, zaktualizować model i przeliczyć ... na jutro będzie gotowe ... w nowej
sesji”. To zgoda na dopasowanie i instalację krzywych nowych rynków **przed
budową 2026-10-15** (dzień 10-15 czysty, nie mieszany), pod warunkiem bramek
niżej - rynek, który ich nie przejdzie, zostaje bez krzywej (tryb zbierania
linii). Nie obejmuje refitu istniejących krzywych piłki / tenisa / sportów.

## Rynki (wszystkie włączone 10-14, bez krzywej)

| grupa | klucze | przełącznik | estymator (SHEET / SPORT_CONFIDENCE) |
|---|---|---|---|
| strzały zawodnika | `player_{shots_outside_box,headed_shots,left_foot_shots,right_foot_shots}_for`, `player_sot_*` | `SHOT_DETAIL_MARKETS` 14:20Z | `bet.sofa.shot_detail.forecast` + `config/sofa_shot_detail.json` |
| podwójna szansa piłka | `double_chance` (1X/X2/12, OVER) | `FOOTBALL_RESULT_MARKETS` 14:20Z | `bet.sofa.football_result` (NB, czysty rating, r 7,586) |
| piłka z incydentów | `first_goal`, `red_cards_total`, `penalties_total` | `FOOTBALL_INCIDENT_MARKETS` 14:50Z | `bet.sofa.football_incidents` |
| tenis sety | `set1_won_for`, `set2_won_for`, `set_score` | `TENNIS_SET_MARKETS` 14:50Z | `bet.sofa.tennis_sets` (rating) |
| sporty mierzone | hokej / koszykówka `double_chance`, `period_double_chance`, h1/h2/quarter; siatkówka `team_wins_set`, `team_sets_exact`, `sets_count` | `SPORT_DERIVED_MARKETS` 14:50Z | score model (`shadow.DERIVED_MARKETS`) |

## Kroki

1. **Kopia danych** (CLAUDE.md „Changing the pipeline” 4): `VACUUM INTO` nie
   jest potrzebny dla strzałów (gotowa kopia tabel
   `data/refit_shot_detail_2026-10-14/shot_detail.db`); dla reszty kopia
   tylko tabel, które czyta pomiar (wzór `fit_shot_detail.make_copy`) do
   `data/refit_new_markets_2026-10-15/`. Nigdy fit na żywej bazie.
2. **Replay historii tym samym estymatorem**, walk-forward (tylko dane sprzed
   meczu) - skrypty pomiarowe już to robią:
   - strzały: `fit_shot_detail.py --before 2026-10-15` (krzywa w `curves.json`);
   - DC: `measure_football_result_phase.py` / `measure_football_result_model.py`
     (wariant czystego ratingu, r jak w configu);
   - incydenty: `measure_football_incidents.py`;
   - tenis sety: `measure_tennis_outcome_model.py` (wariant `live`);
   - sporty: `measure_sport_derived.py`.
   Każdy musi zapisać wiersze (p, y, mecz, data) - dopisać `--rows-out`, jeśli
   go nie ma.
3. **Krzywa**: kubełki `fit_confidence.EDGES`, `MIN_MARKET_BUCKET` 400,
   `realised_lo95` = Wilson (jak `fit_confidence.curve`), per
   `"<market>|<direction>"` (sporty: format pliku
   `config/sofa_sport_confidence_calibration.json`).
4. **Bramka na kluczu (przed instalacją)**: krzywa dopasowana na oknie do
   2026-08-31, sprawdzona na 2026-09-01..10-13 (poza próbą): w kubełkach
   >= 0,70 |zrealizowane - realised_lo95 krzywej| w granicach, a łącznie dla
   druku (p krzywej >= 0,70) luka <= 2 pp przy n >= 300 (reguła PASS
   `measure_calibration.py`). Nie przechodzi -> bez krzywej. Zapisać wynik
   każdego klucza w raporcie.
5. **Instalacja** (tylko przechodzące klucze): scalić wpisy do
   `config/sofa_confidence_calibration.json` (`by_market_direction`) i
   `config/sofa_sport_confidence_calibration.json`, z `fitted_from` dla
   każdego; kopia zapasowa `config/backup_2026-10-15_new_markets/` przed
   zmianą; `tests/sofa` musi przejść, inaczej przywrócić. **Przed** budową
   10-15 (pętla poranna). Po instalacji: `line_evidence` nadal może tylko
   obniżyć (offset puli sportu, cap pasma ceny).
6. **Weryfikacja**: E2E na kopii 10-14 (CONFIDENCE z nowymi krzywymi na
   zamrożonym zegarze, `SOFA_NOW` tylko w skrypcie scratch) - ile nóg nowych
   rynków by się wydrukowało, przy jakim kursie, ile z pewnością poniżej
   1/kurs (te dostają `price_gap` tylko w piłce/tenisie); md5 prawdziwych
   plików przed i po.
7. **Raport** `docs/sofa/history/RAPORT_KRZYWE_NOWE_RYNKI_2026-10-15.md` i
   wpis w CLAUDE.md (Confidence: nowe krzywe, epoka ledgera „od 10-15”).

## Ograniczenia znane dziś

- Jednostronne (`first_goal`, `set_score`, strzały zawodnika): drukują się jako
  single tylko przez `confidence.one_sided_single` (krzywa własnego rynku
  n >= 300) - dziś ta reguła jest dla rekwizytów zawodników piłki; czy
  rozszerzyć ją na `first_goal` / `set_score` - decyzja operatora (marża
  Superbetu: „1. gol” 7-13%, dokładny wynik w setach ~17% > 15%).
- Brak historii cen tych rynków: krzywa mówi, jak często wchodzi, nie czy
  bije kurs. Kursy zapisywane od 10-14 (`unmapped_prices/`, a dla czytanych
  rynków `04_offer.json` / SHADOW).
- Koszykówka / siatkówka: nazwy rynków niesprawdzone na surowym payloadzie -
  pierwsze migawki 10-14 po 14:50Z obejrzeć (`runs/sofa/shadow/...`).
- Strzały zawodnika „zwykłe” były po cenie -14,3% (10-09..10-13).

## Dane historyczne pod krzywe (stan 2026-10-14 15:05Z)

| rynki | źródło historii | stan |
|---|---|---|
| podwójna szansa piłka, piłka z incydentów | listing (wyniki) + `sofa_event_stats.incidents_json` - w cache | gotowe, bez pobierania |
| tenis sety | listing (wyniki setów) - w cache | gotowe |
| sporty: DC, sety siatkówki | historia sportów (`refresh_sport_history.py` co rano) | gotowe |
| strzały zawodnika | `/shotmap` dla meczów z `/lineups` zawodników: 5 760 meczów | **poszerzane**: `backfill_football_lineups.py`, potem `backfill_event_extra.py --kind shotmap` (kolejka od 16:30Z, porcje, stop przy odmowie) |
| hokej / koszykówka / siatkówka z incydentów (1. gol, wyścig do X) | `/incidents` 120 dni (~10 tys. meczów) | pobiera agent od 15:05Z; najpierw pomiar - krzywa tylko jeśli przejdzie |
| tenis „po N gemach / punktach” | `/point-by-point` 60 dni (19 624 meczów) | pomiar: nie drukuje; reszta roku na końcu kolejki (niski priorytet) |

Log kolejki: `runs/sofa/backfill/history_for_curves_2026-10-14.log`.

## Postęp (2026-10-14 15:25Z)

Kroki 1-4 (dopasowanie + bramka na odłożonym oknie 09-01..10-13) robione już
dziś po południu, równolegle, do `data/refit_new_markets_2026-10-15/<grupa>/`
(`shot_detail`, `double_chance`, `football_incidents`, `tennis_sets`,
`sport_derived`; każda z `curves.json` i `gate_report.md`), zbiorczo w
`docs/sofa/evidence/new_market_curves_2026-10-15.md`. Instalacja: skrypt
`scripts/sofa/install_new_market_curves.py --dir data/refit_new_markets_2026-10-15
--confirm` (kopia `config/backup_2026-10-15_new_markets/`, testy, przywrócenie
przy błędzie) - **uruchomić po 00:00Z 10-15, przed budową dnia**; dziś nie, bo
CONFIDENCE czyta krzywe przy każdej przebudowie i zmieniłby dzisiejszy kupon.
Nowa sesja: sprawdzić raporty bramek, uruchomić instalator, zrobić krok 6 (E2E)
i 7 (raport, CLAUDE.md).

Nazwy rynków koszykówki / siatkówki sprawdzone 15:20Z na surowych ofertach
Superbetu (6+6 meczów): czytane podwójna szansa (mecz, 2. połowa), „wygra
seta”, „wygra dokładnie N set(y)”, „dokładna liczba setów”; migawki SHADOW
mają już `derived_rule`.

## Wyniki bramek i decyzje operatora (2026-10-14 ~15:45Z)

Wszystkie 5 grup dopasowane i sprawdzone (`docs/sofa/evidence/new_market_curves_2026-10-15.md`;
commity 979b5db2, ab77ba33, a4f2a3b9). Instalator na sucho dodaje **11 kluczy**:
`player_right_foot_shots_for|OVER`, `double_chance|OVER`, `women:double_chance|OVER`,
`first_goal|OVER`, `penalties_total|UNDER`, `red_cards_total|UNDER`,
`tennis_women:set1_won_for|OVER` i `|UNDER`, `hockey:period_double_chance|TEAM`,
`volleyball:team_sets_exact|NO`, `volleyball:team_wins_set|YES`.

Decyzje operatora (AskUserQuestion, 15:45Z) - **instalować tak, jak instalator na sucho**:
1. prawa noga: cała krzywa, łącznie z przedziałami 0,80-0,85 nieobjętymi sprawdzianem;
2. tenis: zainstalować klucz kobiecy 1. seta mimo braku męskiego;
3. siatkówka „wygra dokładnie N setów”: nie odrzucać linii N = 0 / 3;
4. „pierwszy gol” ma drukować się jako singiel jednostronny - kod już na to
   pozwala (`run_confidence`: OVER bez UNDER = `one_sided_market`;
   `confidence.one_sided_single`: krzywa `market:` z n >= 300) - sprawdzić w E2E.

**Po 00:00Z 10-15, przed budową dnia:**
`PYTHONPATH=src:. .venv/bin/python scripts/sofa/install_new_market_curves.py --dir data/refit_new_markets_2026-10-15 --confirm`,
potem E2E (krok 6: ile nóg nowych rynków się drukuje, ile z pewnością poniżej 1/kurs,
czy `first_goal` przechodzi jako singiel), raport i CLAUDE.md (krok 7; epoka ledgera „od 10-15”).
