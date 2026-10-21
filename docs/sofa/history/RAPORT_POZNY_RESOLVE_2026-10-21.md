# Późny RESOLVE — 2026-10-21

Przełącznik: `epochs.LATE_RESOLVE_FROM_UTC = 2026-10-21 08:48Z` (operator:
„Włączaj od razu!”). Dzień 10-21 jest **mieszany** (`audit_ledger`
„10-21 mieszany”; „od 10-21” nie trzyma żadnego dnia). Nogi wydrukowane
wcześniej zostają zablokowane.

## Dowód (sesja główna, 2026-10-21, tylko odczyt)

- RESOLVE biegnie raz, rano (10-21: tablica 06:13Z, `02_fixtures.json` 06:53Z).
- Wpisy tenisowe z 10-07..10-20 nigdy nie zmostkowane, których mecz później
  był w listingu znanego zawodnika: **65**; dla **39** z nich id Sofascore jest
  większe od każdego id zmostkowanego przez RESOLVE tego dnia — Sofascore
  założył mecz ITF **po** porannym przebiegu (piłka: 4 takie).
- Sprawdzenie na żywo 10-21 08:40Z na kopii bazy (bez missów, bez listingów w
  cache): z nierozpoczętych niezmostkowanych wpisów tenisowych „Atharva
  Sharma·Parth Aggarwal” (ITF M25 Luanda 2) i „Gilberto Ravasio·Cesar
  Bouchelaghem” (ITF M15 Monastir 35) rozwiązują się dzisiejszym kodem, bez
  aliasu.
- Utracony mecz to średnio ~1,2 wydrukowanej nogi w tenisie, ~8,6 w piłce.

## Co zbudowano

- `bet.sofa.late_resolve` (offline): kandydaci (wpis tablicy bez fixture'a,
  start > 20 min, zaślepka 00:00Z pominięta), `merge_by_event` (dokleja
  wiersze nowych meczów, stare zostają), zapis `late_resolve.json` z
  dokańczaniem przerwanego przebiegu.
- `scripts/sofa/run_late_resolve.py`: `_resolve_one` RESOLVE-u na
  kandydatach, listingi czytane świeżo (`LATE_LISTING_TTL_MIN` 30 min — poranna
  kopia z 6 h TTL to ta, w której meczu nie było), missy encji bez zmian;
  zdarzenie już znane dniu nietknięte; nowe otwarte mecze dopisane do 02, potem
  `run_offer.py` / `run_samples.py` / `run_sheet.py --event-ids`.
- `rebuild_plan`: krok 0 (BRIDGE + LATE_RESOLVE, miękki) tylko przy włączonym
  przełączniku i istniejącej pracy; po nim zawsze COUPON (06).
- Testy: `tests/sofa/test_late_resolve.py` (18): nowe mecze dodane, stare
  wiersze 02 / 03 / 05 nietknięte, rozpoczęte i znane pominięte, przełącznik
  wyłączony = nic, porażka etapu zostawia mecze w toku.

## Przebieg na żywo 2026-10-21 (rebuild 08:48Z)

- Kandydaci: 13 (685 wpisów już zmostkowanych, 20 rozpoczętych / < 20 min).
- **Nowe mecze: 8** — piłka 7 (Como U20 – Manchester United U19 UYL,
  Ethiopia Bunna – Negelle Arsi, CA Independiente B – San Francisco FC B,
  Atlas FC U21 – Club América U21, Al Ahly – Canal SC, Nova Cidade – Macaé,
  AA Carapebus – Goytacaz), tenis 1 (Barbara Gatica – Giovana Schincariol
  Barbosa, ITF W15 Campina Grande; próbka BLOCKED). Luki: 4
  NO_MATCHING_EVENT. Każde dopasowanie sprawdzone okiem (5 FUZZY: nazwy
  zgodne — Ethiopian Coffee = Ethiopia Bunna, El Qanah = Canal SC itd.).
- **Nowe wydrukowane single (`11_coupon.json`): 43, wszystkie piłka**
  (Al Ahly 12, Como U20 9, Independiente B 6, Atlas U21 6, Carapebus 5,
  Nova Cidade 4, Ethiopia Bunna 1) + Bet Builder dla Al Ahly – Canal SC.
  Tenis 0.
- Niezmienność (porównanie z kopią sprzed przebiegu): `02_fixtures.json`
  581 → 589, `03_samples.json` 581 → 589, `05_sheet.json` 50 090 → 50 526;
  w każdym pliku pierwsze wpisy (stare) **identyczne** po sparsowaniu, dodane
  wyłącznie nowe zdarzenia. `04_offer.json`: krok OFFER przebiegu przeniósł
  581 starych wpisów bez zmian (`carried_forward_from_previous_offer` 581);
  ceny potem odświeżył zwykły krok OFFER przebudowy (jak w każdej
  przebudowie). Wiersze nowe mają ten sam `config_sha` (e3bfb520c986fb3d).
- AUDIT_VARIANTS PARTIAL: C3 — nowe nogi (np. Carapebus) i nogi przesunięte
  przebudową drukują się bez odczytu; trzeba `read_set.py --unread` i
  analityków (zwykła ścieżka po przebudowie). **Nie zrobione w tym zadaniu.**

## Czego nie zrobiono / nie sprawdzono

- Dwa tenisowe przypadki z dowodu (Ravasio·Bouchelaghem, Sharma·Aggarwal)
  **nie** rozwiązały się na żywo: ich nazwy są niezweryfikowane i mają miss
  encji z 2026-10-20 05:40Z (TTL 7 dni), który zgodnie z zadaniem jest
  honorowany. Sprawdzenie sesji głównej kasowało missy na kopii. Czy późny
  przebieg ma ignorować miss niezweryfikowanej nazwy starszy niż poranny
  RESOLVE — decyzja operatora (zmienia to semantykę cache'u).
- Nie zmierzono jeszcze, ile nóg późny przebieg daje dziennie i jak się
  rozliczają (pierwszy dzień: 10-21).
