# Domknięcie luk dnia 2026-10-08

Sesja robocza po zbudowaniu dnia. Liczby pochodzą z porównania plików
(`runs/sofa/2026-10-08/11_coupon.before_fix.json` kontra końcowy
`11_coupon.json`) i z poleceń uruchomionych w sesji. Nie refitowano ani nie
instalowano krzywych, nie zmieniano epok ani bramek.

## Porównanie kuponu

| | przed | po |
|---|---|---|
| pojedyncze razem | 747 | 721 |
| tenis | 360 | 347 |
| piłka | 173 | 171 |
| hokej | 169 | 167 |
| koszykówka | 43 | 34 |
| siatkówka | 1 | 2 |
| CS2 | 1 | 0 |
| buildery drukowane | 0 | 0 |
| nogi zablokowane | 18 | 60 |
| `removed_by_reads` | 16 | 27 |

- Wypadło 36 nóg: 14 przez odczyty, 22 nie wróciły do druku (z artefaktów nie
  da się rozdzielić na pewność < 0,70, wiek ceny i zniknięcie linii).
- Doszło 10 nóg (tenis 2, hokej 2, koszykówka 5, siatkówka 1).
- Pewność zmieniła się o więcej niż 0,01 na 27 nogach, wszystkie to
  koszykówka (2 w górę, 25 w dół).
- Zablokowane nogi: 0 ruszonych (wzrost 18 → 60 to upływ czasu).

## Dowody linii

- Odświeżenie z 04:42Z poprzedziło SHADOW_SETTLE i CS2_SETTLE dnia 10-07
  (05:01-05:17Z). Powtórzono `audit_shadow`, `audit_cs2`, `record_results` i
  `refresh_line_evidence --before 2026-10-08` (exit 0 dla czterech sportów),
  potem jeszcze raz z `--skip-sport-rows` po sweepie.
- **Luka nienaprawiona:** wiersze hokeja z 10-07 to 0 (10-05: 273, 10-06: 356).
  `sofa_listed_event` ma dla hokeja 0 eventów z 10-07 i 10 z 10-06;
  koszykówka i siatkówka mają po 10-04 też tylko garstkę. `backfill_listings
  --dry-run` wskazał 2 encje do pogłębienia, więc to nie jest narzędzie na tę
  lukę (chodzi o świeżość strony 0 listingów, nie o głębokość). Do decyzji
  operatora, najlepiej rano przed budową dnia 10-09.

## Settlement 2026-10-07

- 16 nierozliczonych z 334 eventów: 1 POSTPONED, 12 RETIRED, 3 CANCELED,
  2 NOT_FINISHED; 24 printed legs na 10 eventach. Po sweepie jeden
  NOT_FINISHED się rozliczył (+70 wierszy, mecz 17270267; w cache wisiał
  przeterminowany status `inprogress`).
- 7 eventów RETIRED ma w DB `status.code 92`: zwroty zgodne z
  `settle.REFUND_REASONS`. CANCELED (code 70) nie jest w `REFUND_REASONS`,
  więc 4 nogi (17239649) są UNSETTLED. Czy anulowany mecz ma być zwrotem,
  rozstrzyga regulamin Superbetu (zmiana reguły, nie ruszana).
- Ledger `official` 10-07 po sweepie: 820 pozycji (625 football/tenis + 191
  sporty + 4 buildery), 790 rozliczonych, -48,004 j., 19 zwrotów, 6
  UNSETTLED, 4 PENDING (`PENDING:DATA_MISMATCH`, nogi sportów).
- `audit_ledger`: MISMATCH 0. `audit_settle_identity`: exit 1, 17 znalezisk
  (15 NAME_BELOW, 2 CS2); wszystkie 15 NAME_BELOW to ten sam klub pod inną
  nazwą (id przypięte), obejrzane ręcznie.

## Odczyty

- 15 nóg w `read_requests.json` (9 tenisa z luką model - próbka > 0,15,
  3 hokeja, 1 koszykówka, CS2, 1 o najniższej pewności) plus 2 nogi
  Athletico - Mineiro z C3. Analitycy: 8 WATCH (tenis), reszta KEEP.
- Weryfikator, 3 rundy: 7 + 2 nogi WATCH, runda 3 zwróciła pustą tablicę.
  Rundy 2 i 3 nie odpytywały cen na żywo.
- `reads.json`: 77 → 105 wpisów, wszystkie zwalidowane jako `LegRead`.

## Warunki zamknięcia

Spełnione: `audit_variants` 0 znalezisk, `audit_coupon` exit 0, mtime
(PDF >= `11_coupon` >= wejścia), `12_printed.json` = `11_coupon.json` (721),
wiek cen (oferta 21 min, migawki sportów w limicie).

`day_status`: **WARN** z powodu 2 UNVERIFIED fixtures (17275526 Finland U19 -
Belgium U19, 17275529 Scotland U19 - Croatia U19; Sofascore 404). Żaden nie ma
printed legs ani buildera. Operator przyjął to jako spełnienie warunku
("bez WARN dotyczącego kuponu").

Niesprawdzone: czy `closing.jsonl` obejmuje 10 nowych nóg (pętla czyta
artefakt co przebieg, ok. 5 min).
