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

(uzupełniane po backfillu)

## 3. Wyniki

(uzupełniane po pomiarze)
