# A7 - krzywa koszykówki na liniach postawionych tam, gdzie stał rynek (2026-10-13)

Audyt 2026-10-13, wiersz A7 i Część 4, podsumowanie pkt 2, rozwiązanie (b).
Zgoda operatora: O2 (historyczne kursy Sofascore wyznaczają **tylko pozycję**
linii historii; p dalej wyłącznie ze statystyk - to nie jest „blend the
price”), O6 (instalacja refitu po poprawie), O8 (bridge).

## 1. Rejestracja (zapisana PRZED pomiarem)

Ta sekcja została zapisana i zacommitowana przed uruchomieniem dopasowania
wariantu i porównania. Wyniki są w sekcji 3 i nie zmieniają tej sekcji.

### Problem

`sport_confidence.synthetic_lines` stawia linie historii w kwantylach
(`LINE_QUANTILES`) własnej symulacji modelu. Linia Superbetu stoi tam, gdzie
rynek widzi mediana meczu, więc noga z p ≈ 0,75 to linia, przy której model
nie zgadza się z rynkiem - populacji, której krzywa historii nigdy nie
widziała. Zmierzone w audycie (krzywe `.next`, 3 625 linii / 665 meczów z
odczytem ≥ 0,70): krzywa 0,760, realizacja 0,633, cena bez marży 0,628.
Refit koszykówki tą samą metodą (`data/refit_2026-10-13/bb_base`,
`bb_new`) nie dał poprawy i luka ~-12 pp została.

### Wariant

- **Źródło pozycji linii:** Sofascore `/event/{id}/odds/1/all` meczu z
  historii (backfill `scripts/sofa/backfill_event_odds.py`, cache
  `data/a7_odds/basketball.jsonl`). Z odpowiedzi brane są wyłącznie:
  - `Game total` (okres `Match`): linia z `choiceGroup` -> rodzina `total`
    (753);
  - `Point spread` (okres `Match`): linia z nazwy wyboru „(+11.5) Drużyna”,
    przypisana gospodarzowi albo gościowi po nazwie drużyny Sofascore (nigdy
    po kolejności wyborów) -> rodzina `handicap` (768);
  - `team_total` (758 / 776): pozycja wynikająca z dwóch linii rynku, gdy mecz
    ma dokładnie jeden total T i jeden spread gospodarza h: gospodarz
    (T - h) / 2, gość (T + h) / 2, w połowie punktu (liczba całkowita daje
    dwie linie wokół niej).
  Kursy (`fractionalValue`, `initialFractionalValue`) **nie są zapisywane w
  cache** (`market_lines.trim_markets`), więc nie mogą wejść ani do p, ani
  do pewności. Linie alternatywne, jeśli Sofascore poda kilka `choiceGroup`,
  wchodzą wszystkie (żadnego wyboru „linii głównej” po cenie).
- **p:** z modelu wyników (`score_model`) dokładnie jak dziś - ten sam
  walk-forward, te same reguły dnia `--before 2026-10-13` co `bb_base`
  (świeżość wg epoki, `bb_overtime` wyłączone, `league_rate_rule`
  wyłączone), 1 000 symulacji, ziarno = id meczu. Wynik linii oceniany z
  wyniku meczu tą samą funkcją `grade` co dziś.
- **Populacja dla rodzin z pozycją rynku (`total`, `handicap`,
  `team_total`):** tylko mecze, które mają linie rynku, i tylko na tych
  liniach (obie strony). **Wybór: mecze z liniami rynku, bez linii
  syntetycznych dla tych rodzin.** Uzasadnienie: linie syntetyczne to 13
  kwantyli x mecz i ~70-90% meczów okna nie ma kursów w Sofascore; po
  zmieszaniu populacja krzywej nadal byłaby w ogromnej większości syntetyczna
  i problem z audytu zostałby nietknięty. Żeby mieć liczebność, wariant
  ocenia **każdy** mecz okna z liniami rynku (nie tylko przerzedzone
  `--max-games 4000` / `--max-holdout-games 3000`).
- **Pozostałe rodziny** (zwycięzca, 1X2, połowy, kwarty, parzystość) - bez
  zmian: linie syntetyczne na przerzedzonych meczach, jak dziś.
- Okna: dopasowanie 2025-09-13..2026-09-13, holdout 2026-09-13..10-13 (jak
  `bb_base`).

### Metryka (pomiar poza próbą krzywej)

- **Populacja:** rozliczone linie Superbetu koszykówki 2026-09-29..10-12
  (`basketball_superbet_settled.jsonl` z `bb_base/rows`; p tego samego
  estymatora w obu wariantach), klucze dotknięte zmianą: `total|OVER`,
  `total|UNDER`, `handicap|TEAM`, `team_total|OVER`, `team_total|UNDER`.
- **Pewność** = `realised_lo95` kubełka krzywej (jak `evaluate` /
  `SportCalibration.lookup` bez wymogu admisji), **bez** line evidence -
  to sprawdzian samej krzywej.
- **Pierwszorzędna:** średni log-loss pewności, w parach na liniach pokrytych
  przez obie krzywe: wariant - bazowa, 95% przedział z bootstrapu po meczach
  (2 000 losowań, ziarno 13).
- **Druga część progu:** luka drukowalna = realizacja - średnia pewność na
  liniach z pewnością ≥ 0,70 (osobno dla każdej krzywej; zbiory linii mogą
  się różnić), z 95% przedziałem z bootstrapu po meczach.
- **Raportowane obok (nie próg):** pokrycie (ile linii każda krzywa w ogóle
  czyta), N linii / meczów, wynik per klucz, ten sam pomiar dla wszystkich
  kluczy, holdout historii.

### Próg

Wariant uznany za lepszy, gdy **oba**:

1. Δ log-loss (wariant - bazowa) < 0 i górna granica 95% przedziału < 0;
2. |luka drukowalna wariantu| < |luka drukowalna bazowej|.

Inaczej: nie instalować; wynik zapisany jako zmierzony.

### Czego ten pomiar nie sprawdza

- Hokej (A7 obejmuje też hokej; ten sam skrypt ma `--sport hockey`, pomiar
  osobno).
- Linie Superbetu drabinkowe (alternatywne) mają w Sofascore odpowiednik
  tylko wtedy, gdy Sofascore poda kilka `choiceGroup`; wariant nie wymyśla
  pozycji drabinki.
- Czy total Sofascore obejmuje dogrywkę - linia jest oceniana regułą
  Superbetu 753 (z dogrywką), więc ewentualna różnica przesuwa tylko pozycję
  o ułamek punktu.

## 2. Backfill

Stan cache `data/a7_odds/basketball.jsonl` na pomiar (bez bridge'a w tym
pomiarze; backfill z 2026-10-13 13:20-14:09Z, `loop.log`, przerwany dwoma
seriami 5 x 403):

- cele: 26 332 mecze (okno 395 dni przed 2026-10-13); zapytane 10 662
  (wszystkie z priorytetem 0 = mecze przerzedzonego dopasowania i holdoutu,
  `todo_prio0: 0`; priorytet 1 niezapytany, 15 670), odpowiedź `ok` 8 504,
  `not_found` 2 158;
- **mecze z liniami rynku (`Game total` lub `Point spread`, okres `Match`):
  2 661** (25% zapytanych), po miesiącach od 28 (2025-09) do 539 (2026-05);
  ~2 100 w oknie dopasowania 2025-09-14..2026-09-14.
- W dopasowaniu wariantu: 20 740 wierszy historii z linią rynku
  (`history_fit`), 4 864 w holdoucie (`fitted_from.market_positioned_lines`).

Konsekwencja: kubełki krzywej powyżej p 0,70 dla rodzin z pozycją rynku mają
n < 200 (jedyny wyjątek `team_total|OVER` 0,70-0,75, n 216) - patrz sekcja 3.
Dociągnięcie priorytetu 1 wymaga bridge'a (nie użyto).

## 3. Wyniki

Pomiar 2026-10-14 (UTC) w ramach wariantów V0-V3 koszykówki, szczegóły i
tabele: `basketball_refit_2026-10-13.md`, sekcja „Warianty A7 / A3”. Skrypt:
`data/refit_2026-10-13/bb_variants/compare_bb_variants.py` (importuje metrykę
z `bb_refit/compare_bb_refit.py`), wynik `bb_variants/compare.json`.

**Odstępstwo od rejestracji:** dopasowanie wariantu zrobiono regułami dnia
10-14 (`--before 2026-10-14 --league-rate-rule`), a bazą jest refit z liniami
syntetycznymi tymi samymi regułami (`bb_refit_lr`), nie `bb_base`
(`--before 2026-10-13`). Reszta (populacja, pewność = lo95, bootstrap, próg)
jak w sekcji 1. Odczyt rejestracyjny (linie Superbetu 2026-09-29..10-12, pięć
kluczy, ziarno 13):

| | linie w parach / mecze | log-loss baza | A7 | różnica A7 - baza [95%] |
|---|---|---|---|---|
| A7 (V1) | 36 179 / 1 211 | 0,81141 | 0,69525 | **-0,11616 [-0,12714; -0,10559]** |
| A7 + dogrywka (V2; baza = V3) | 34 430 / 1 211 | 0,81960 | 0,69290 | -0,12670 [-0,13683; -0,11682] |

Luka drukowalna (pewność >= 0,70) na pięciu kluczach: baza 2 375 linii /
465 meczów, **-12,2 pp [-16,6; -7,9]**; A7: **0 linii** - żadna linia
Superbetu tych kluczy nie dostaje pewności >= 0,70.

### Co krzywa A7 mówi

Na liniach postawionych tam, gdzie stał rynek, mecze historii z p modelu
0,60-0,70 realizują 0,48-0,53 (kubełek 0,60-0,70: `total|OVER` 0,524 na 311,
`total|UNDER` 0,480 na 200, `handicap|TEAM` 0,511 na 583, `team_total|OVER`
0,516 na 968, `team_total|UNDER` 0,527 na 740), a p < 0,60 realizuje
0,47-0,51. **Przy linii rynku model wyników nie ma mierzalnej
rozdzielczości na totalach / handicapie / team totalach** - potwierdzenie
hipotezy A7: krzywa syntetyczna (kwantyle własnej symulacji) widzi
rozdzielczość, której przy linii rynku nie ma.

### Próg

1. Log-loss: spełniony z dużym zapasem - ale zysk pochodzi głównie z linii z
   p < 0,5 (zainstalowana krzywa czyta je lo95 ~0,21-0,24, realizują ~0,47);
   takie linie nigdy nie drukują.
2. Luka drukowalna: na pięciu kluczach wariant nie ma ani jednej linii >= 0,70,
   więc nierówność z sekcji 1 jest nieokreślona; zawyżenie znika przez brak
   odczytu, nie przez lepszą kalibrację. Z 1 206 linii 10-05..10-12, które
   zainstalowana krzywa czyta >= 0,70, 1 143 wypada z kubełków A7 (n < 200:
   `NOT_CALIBRATED`, nie drukuje; zainstalowana czyta je średnio 0,767,
   zrealizowały 0,618), 63 A7 czyta < 0,60 (0,54; zrealizowały 0,46). Na wszystkich kluczach luka drukowalna nie
   maleje (-16,1 -> -17,0 pp, bo zostają klucze bez zmiany).

**Wynik: nie zainstalowano i nie wystawiono kandydata** (warunek 2 nie jest
spełniony w odczycie zadanym przez koordynatora). Decyzja, czy „krzywa A7
odcina total / handicap / team total przez pomiar” to poprawa, należy do
operatora; kandydat istnieje jako surowy wynik dopasowania
`data/refit_2026-10-13/bb_variants/v1_a7/cal.json` (przełącznik
`MARKET_POSITIONED_LINES_FROM_UTC` + cache A7). Hokej nie zmierzony.
