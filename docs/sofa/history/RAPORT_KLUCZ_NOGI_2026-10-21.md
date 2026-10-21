# Klucz nogi bez okresu / mapy - 2026-10-21

## Podejrzenie

`locked_print.leg_key` = (id meczu, rynek, podmiot, linia, kierunek) - bez
`period` / `map_nr`. 10-21 wydrukowano CS2 17374496 `map_rounds_handicap`
-4.5 T2 na mapie 2 (@1.54) i na mapie 3 (@1.48): jeden klucz dla dwóch nóg.
`merge_locked`, `carry_over`, `printed_leg_keys` deduplikują po tym kluczu.

## Pomiar (wszystkie `runs/sofa/*/11_coupon.json` i `printed/*.json`)

- Kolizje klucza wśród drukowanych singli są częste, ale **tylko w sportach
  mierzonych**: hokej (tercje), CS2 (mapy), siatkówka (sety) - np. 10-17
  hokej 613 kolizji, 10-21 CS2 196 + hokej 112 (liczone po renderach).
- Żadna noga piłki / tenisa (single, nogi builderów, `legs`) nie ma
  niezerowego `period` ani `map_nr` (połowy siedzą w nazwie rynku, np.
  `goals_1h_total`). Wszystkie buildery (1043) to piłka.
- **Żadna kolizja nie zgubiła nogi ani nie dała dwóm nogom jednej oceny.**
  Każdy konsument `leg_key` dla singli filtruje do piłki / tenisa:
  `run_confidence` (carry_over / merge_locked z `sports={football,tennis}`),
  `printed_leg_keys(sheet_sports_only=True)` w `run_settle`, `record_results`,
  `audit_settlement`; `settleability` i `audit_variants` tylko sporty arkusza.
  Sporty mierzone blokuje `coupon_sports` po `sport_key` (z okresem),
  `first_prints` / `history_keys` po `_any_key` = `sport_key`,
  `13_results.json` po `coupon_results.key_of` (`sport_key` + market_id +
  `map_nr`), księgę po `sport_day.LEG_KEY` (z `period` i `map_nr`).
- `13_results.json` 10-13..10-20: unikalnych kluczy = drukowanych singli =
  wierszy wyników (np. 10-17: 12 128 / 12 128 / 12 128). Księga 10-17 / 10-19
  / 10-20: pozycje sportów mierzonych = drukowane single co do sztuki
  (np. 10-17 hokej 512, CS2 35, siatkówka 40, koszykówka 14).

Wniosek: wada utajona, bez wpływu na żaden zbudowany dzień.

## Poprawka (korekta poprawności, od razu)

`leg_key` dodaje szósty element - `period`, a gdy go brak `map_nr` - tylko
gdy noga go ma (niezerowy). Noga piłki / tenisa zachowuje pięć elementów,
więc zapisane klucze (`printed/<ts>.json`, `printed_after_start`) czytają się
bez zmian. `LegKey` = `tuple[Any, ...]`. Co się drukuje - bez zmian.
Test: `tests/sofa/test_leg_key_period.py` (dwie mapy = dwa klucze, sama
`map_nr`, trzy tercje, piłka bez zmian, `merge_locked` zachowuje obie mapy,
`printed_leg_keys`).

## Czego nie sprawdzono

- Przebudowy dnia (rebuild) z nowym kodem - niepotrzebna, bo żadna noga
  piłki / tenisa nie zmienia klucza; nie uruchomiono.
- `priced_view.leg_key` i `run_settle._sheet_key` to osobne klucze (pierwszy
  już z okresem) - nie ruszane.
