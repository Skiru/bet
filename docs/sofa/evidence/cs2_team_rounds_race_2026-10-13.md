# B10: CS2 `map_team_rounds` z wyścigu rund (audyt 2026-10-13)

Przełącznik: `epochs.CS2_TEAM_ROUNDS_RACE_FROM_UTC`. Kod:
`cs2_engine.team_rounds_from_race`, `model_probability(..., team_rounds_race)`.
Skrypt: `scripts/sofa/measure_cs2_team_rounds_race.py` (tylko odczyt).

## Rejestracja (zapisana 2026-10-13 przed uruchomieniem pomiaru)

- Hipoteza: p linii „X - liczba rund na N. mapie” liczone z rozkładu wyniku
  mapy (`map_distribution_for(p_map)`, ten sam wyścig rund co handicap rund)
  jest lepsze niż dzisiejsza częstość własnych rund drużyny skurczona do bazy
  (`shrunk_frequency`), bo rundy drużyny >= 13 to w praktyce wygrana mapy.
- Populacja: historia map CS2 z bazy (`sport_confidence.load_cs2`), serie z
  rundami, okno ewaluacji 2025-10-13..2026-10-13; linie
  `CS2_TEAM_ROUND_LINES` (9,5 / 10,5 / 11,5 / 12,5), obie strony, obie drużyny.
- Podział poza próbą: walk-forward jak `cs2_walk_forward_rows` - Elo map i
  jego kalibracja logistyczna z meczów sprzed serii (refit co 7 dni), próbka
  drużyny i stopa bazowa tylko z wcześniejszych map.
- Metryka: log-loss p strony; różnica wyścig - częstość na serię, 95% z
  bootstrapu po seriach (2000, ziarno 0). Obok: Brier, kalibracja kubełków
  >= 0,70 (realizacja - średnie p) dla obu.
- Próg (O5): włączyć, gdy górna granica 95% < 0. Włączenie wymaga refitu
  krzywej CS2 `map_team_rounds` w replayu historii tym samym estymatorem
  (`fit_sport_confidence.py --sport cs2` na kopii bazy, `.next` / instalacja
  według O6) - bez niego krzywa czytałaby p innego estymatora.
- Nakładanie się: pozycja „queued” z CLAUDE.md; pomiar 2026-10-07 (CS2-1:
  -0,025 [-0,028; -0,021]) był w innym oknie i bez rejestracji - ten jest
  nowym, zarejestrowanym pomiarem.

## Wynik (2026-10-13, `data/audit_2026-10-13/b10.json`)

Okno 2025-10-13..2026-10-13: 316024 linii wspólnych w 8738 seriach
(tylko stara: 29064 - wyścig bez Elo obu drużyn; tylko nowa:
8248 - drużyna bez własnych map).

- log-loss wyścig - częstość: **-0.0213 [-0.0237; -0.0188]**
- Brier: -0.0098 [-0.0109; -0.0087]
- kalibracja linii z p >= 0,70: stara 23637 linii, średnie p
  0.734, realizacja 0.698; nowa 33245
  linii, p 0.756, realizacja 0.758.

| linia / strona | linie | log-loss różnica [95%] |
|---|---|---|
| 10.5|OVER | 39503 | -0.0206 [-0.0232; -0.0180] |
| 10.5|UNDER | 39503 | -0.0206 [-0.0232; -0.0180] |
| 11.5|OVER | 39503 | -0.0221 [-0.0247; -0.0195] |
| 11.5|UNDER | 39503 | -0.0221 [-0.0247; -0.0195] |
| 12.5|OVER | 39503 | -0.0230 [-0.0255; -0.0205] |
| 12.5|UNDER | 39503 | -0.0230 [-0.0255; -0.0205] |
| 9.5|OVER | 39503 | -0.0193 [-0.0216; -0.0169] |
| 9.5|UNDER | 39503 | -0.0193 [-0.0216; -0.0169] |

**Próg spełniony** (górna granica < 0 łącznie i na każdej linii). Włączenie
idzie z refitem krzywej CS2 na tym estymatorze (niżej, raport implementacji).
Zastrzeżenie: `LINE_OUTSIDE_FIT` zostaje (krzywa nadal dopasowana na
9,5-12,5; poza nimi niezmierzone).

## Refit i instalacja (O6)

- Kopia bazy: `data/refit_2026-10-13/sofa_replay.db` (`VACUUM INTO`, 574 s).
- `fit_sport_confidence.py --sport cs2 --before 2026-10-13` dwa razy na kopii:
  obecny estymator (`data/refit_2026-10-13/cs2_base/`) i wyścig rund
  (`--cs2-team-rounds-race`, `cs2_race/`). Pozostałe krzywe CS2 identyczne.
- Compare na holdoucie historii (30 dni): log-loss pewności
  `map_team_rounds|OVER` 0,6479 (wyścig) vs 0,6622; `|UNDER` 0,6644 vs 0,6658;
  realizacja - pewność OVER +0,5 pp [-0,1; +1,2], UNDER -0,3 pp [-1,0; +0,4].
- Linie Superbetu 10-05..10-12 (p przeliczone wyścigiem as-of dnia, krzywa z
  refitu; kontrola, nie kryterium): 1336 linii / 46 serii,
  log-loss p wyścig - stare p -0.0291 [-0.0599; +0.0049]; nogi „do druku”
  stara reguła 5 / 2 serii, realizacja - pewność -33.4 pp;
  nowa 46 / 11 serii, +6.8 pp [-8.2; +19.2],
  ROI +5.3% [-14.2; +22.8].
- Instalacja: backup `config/backup_2026-10-13_audit/`; dotychczasowy
  `sofa_sport_confidence_calibration.next.json` (od 2026-10-07) przeniesiony
  na plik zainstalowany (dni 10-07..10-13 czytają to samo; dni < 10-09 nie są
  przebudowywane); nowy `.next.json` = to samo z sekcją CS2 z refitu,
  `effective_from` 2026-10-14. Przełącznik
  `CS2_TEAM_ROUNDS_RACE_FROM_UTC` = 2026-10-14 00:00Z. Dzień 10-13 nie jest
  mieszany.
- Line evidence: offsety CS2 `map_team_rounds` z dni <= 10-13 są liczone na p
  starego estymatora czytanym przez nową krzywą - pierwsze poranki są
  zaszumione dla tego klucza (jak po refitach 10-07 / 10-08).
