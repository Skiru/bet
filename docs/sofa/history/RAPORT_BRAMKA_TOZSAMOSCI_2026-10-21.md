# Raport: bramka tożsamości per rodzina (2026-10-21)

Przełącznik `epochs.IDENTITY_GATE_PER_FAMILY_FROM_UTC`: **od 2026-10-21
10:50Z, 10-21 mieszany** (decyzja operatora: „MA WEJŚĆ DZISIAJ!”). Grupa księgi:
„10-21 mieszany” (już istnieje); „od 10-22” bez zmian.

## Defekt

`metrics.check_identities` zwracał jeden werdykt dla całego meczu, a SAMPLES
(`samples.process_historical_event`) przykładał go do **każdej** metryki.
Przykład: Roma - Real Madrid (16938872, 2026-10-14, 3-4) - strzały Realu
total 16 wobec celne 8 + niecelne 8 + zablokowane 1 = 17, bez klucza
`hitWoodwork`; gole, rożne, kartki spójne - a wszystkie 52 metryki Realu
dostały `INTERNAL_INCONSISTENT`. Ta sama bramka była w
`settle.historical_sample` i `scripts/sofa/run_backfill.py` (replay
backfillu). SETTLE (ocena legów) tej bramki nie używa - ocena drukowanych
legów się nie zmienia.

## Reguła (od przełącznika)

`metrics.identity_failures` zwraca porażki per rodzina,
`metrics.identity_gap_for_metric` mówi, czy dana metryka jest zablokowana:

| tożsamość | blokuje |
|---|---|
| strzały (`totalShotsOnGoal` vs celne + niecelne + zablokowane, granica = słupek) | `shots_*`, `shots_on_target_*` (mecz, połowy); przez `shots_for` handicapy / oba-powyżej strzałów. Strzały zawodnika idą z lineups - nigdy nie były tu bramkowane |
| gole w incydentach != wynik | metryki z `/incidents`: punkty kartek (mecz, połowy), czerwone, karne. Gole czytane z wyniku - nie blokowane (wynik pilnuje `goal_score_inconsistent`) |
| suma połów gospodarza != `normaltime` | gole (mecz, połowy) i czerwone / karne (czytają wynik 90 min); podzbiór `goal_score_inconsistent` |
| tenis `gamesWon` vs wynik setowy | cały mecz, jak dotąd |
| metryka nieznana modułowi | każda porażka |

Wyłączony przełącznik = stare zachowanie (cały mecz).

## Gdzie działa

- `samples.process_historical_event` / `goal_observations` /
  `process_fixture_samples` (`per_family_identity`), włączane w
  `scripts/sofa/run_samples.py` przez `epochs.identity_gate_per_family(data)`
  (zegar budowy). Wpis `03_samples.json` liczony pod przełącznikiem ma
  `identity_gate: "per_family"` (`FixtureSamples.identity_gate`; bez
  przełącznika pole nie jest zapisywane - artefakt bajt w bajt jak dotąd).
- `settle.historical_sample` i `run_backfill.py` (replay czyta przełącznik wg
  bieżącego zegara - estymator dnia dzisiejszego).
- **Rebuild dnia już zbudowanego** (`bet.sofa.rebuild_plan`, krok 1c):
  `identity_unsampled` wybiera mecze piłki **jeszcze nierozpoczęte**, których
  wpis w `03_samples.json` nie ma znacznika, a ma lukę `INTERNAL_INCONSISTENT`
  (tylko takie mogą zyskać obserwacje). Plan: `BRIDGE` (miękko) ->
  `run_samples.py --event-ids <ids>` (miękko; reszta wpisów zachowana, jak w
  późnym RESOLVE) -> `run_sheet.py --event-ids <ids>` (chyba że cały SHEET i
  tak idzie) -> COUPON / FIXTURE_CHECK / CONFIDENCE / ... Mecz rozpoczęty nigdy
  nie jest liczony od nowa; legi wydrukowane zostają zablokowane.
- Koszt mostu (szacunek, nie pomiar): na 10-21 49 z 188 meczów piłki ma lukę
  `INTERNAL_INCONSISTENT` (z tego otwartych mniej). SAMPLES czyta głównie cache:
  pełny dzień 10-21 to ~11-12 tys. trafień cache i 523-783 zapytań o
  statystyki na 589 meczów, późne RESOLVE 8 meczów - 20 zapytań. Dla <= 49
  meczów spodziewamy się rzędu 50-150 zapytań statystyk plus odczyty list
  meczów - poniżej minuty przy ~11 req/s. Niezmierzone na żywo.

## Pomiar (`scripts/sofa/measure_identity_gate.py`, tylko odczyt)

### A. Co wraca w SAMPLES (03_samples.json 10-17 .. 10-21)

Liczone (mecz dnia, metryka, mecz próbki) z luką `INTERNAL_INCONSISTENT`,
przeczytane ponownie z cache:

| dzień | luki | wracają per rodzina | mecze próbki | rodziny (mecze) |
|---|---|---|---|---|
| 10-17 | 2 708 | 1 677 | 474 | strzały 125, incydenty 46, połowy 7, tenis 32 |
| 10-18 | 2 091 | 1 090 | 372 | strzały 91, incydenty 33, połowy 6, tenis 33 |
| 10-19 | 757 | 311 | 116 | strzały 31, incydenty 5, połowy 1, tenis 30 |
| 10-20 | 1 336 | 417 | 142 | strzały 18, incydenty 6, tenis 45 |
| 10-21 | 859 | 335 | 102 | strzały 30, incydenty 13, połowy 2, tenis 38 |

Wracają głównie: gole (mecz i połowy), rożne, punkty kartek, obrony,
spalone, faule (np. 10-21: goals_for 44, corners_total 19, cards_points 5).
Rodzina „none” (luka, choć payload przechodzi dziś wszystkie tożsamości) to
luki własne `extract_metric` / graczy (`player_shots_on_target_for`, połowy
celnych, `goal_score_inconsistent`) - nie tej bramki; zostają.

### B. Czy przywrócone mecze wyglądają jak reszta (cache, mecze piłki 2026-07-01 .. 10-21, poza próbkami dni)

Średnie sumy meczu, różnica z 95% przedziałem (bootstrap meczów):

| grupa vs zachowane (n ~29 tys.) | gole | rożne | punkty kartek | faule |
|---|---|---|---|---|
| tylko strzały (n 253) | -0.07 [-0.30, +0.17] | +0.30 [-0.13, +0.72] | +0.14 [-0.31, +0.60] | -0.65 [-1.49, +0.10] |

Strzałowe mecze nie różnią się od reszty w żadnej przywracanej rodzinie
(przedziały obejmują zero; rożne i faule z lekkim, nieistotnym przesunięciem -
do obserwacji). Gole meczów z rozjazdem incydentów (n 57): 3.86 wobec 3.03,
+0.83 [+0.34, +1.37] - ale to selekcja z konstrukcji: lista bez goli
(placeholder, same wpisy `period`) łamie tożsamość **tylko** przy wyniku
innym niż 0-0, więc stara bramka trzymała 0-0 takich feedów, a wyrzucała
mecze z golami. Feedy placeholder razem (n 353) mają 1.41 gola wobec 3.03 -
nawet po przywróceniu niżej (zgodne ze znanym „fake 0-0” feedów częściowych,
który zostaje jak był); przywrócenie przesuwa je w stronę reszty, nie dalej.

## Krzywe

Replay krzywych (`calibrate_from_cache` / `prepare_refit rebuild-cache-rows`)
**nigdy nie wołał** `check_identities` - krzywe dopasowano bez żadnej bramki
tożsamości (także mecze ze złymi strzałami w metrykach strzałów). Przełącznik
przybliża SAMPLES do replayu krzywych, nie oddala; refit z tego powodu nie jest
potrzebny. Ratingi (`football_rating`) czytają cache własną drogą - bez zmian.

## Testy i bramki

`tests/sofa/test_identity_gate_per_family.py` (13 testów, liczby 16938872):
gole / rożne / kartki / faule wracają, strzały zostają `INTERNAL_INCONSISTENT`;
przełącznik wyłączony = cały mecz; placeholder blokuje tylko metryki
incydentów; suma połów - tylko wynik; tenis `gamesWon` - cały mecz;
`historical_sample`; zegar przełącznika; plan rebuildu (SAMPLES ->
SHEET --event-ids, tylko otwarte / bez znacznika / z luką). Pełne
`tests/sofa`, ruff, mypy --strict, `check_test_registry.py` - zielone (poza
znanymi E501 w `measure_cs2_map_total_race.py` i mypy `measure_slip_*`).

## Czego nie sprawdzono

- Rebuild na żywym dniu (krok 1c) - tylko testy offline planu; koszt mostu
  to szacunek.
- Wpływ na wydruk (ile legów zmieni się po rebuildzie) - niezmierzony;
  szersze próbki zmieniają centra i gotowość `READY`.
- Brak pomiaru „lepiej na rozliczonych” - to poprawka kompletności próbki,
  nie przewaga.
