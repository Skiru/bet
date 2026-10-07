# 2026-10-07 — dowód z linii Superbetu: nic nie ucinamy z nazwy

## Decyzje operatora (2026-10-07)

1. Miarą nie jest „czy bijemy cenę” (x ≥ 0,90 i tak akceptuje marżę), tylko
   to, czy statystyki odróżniają dobre 1.20 od złego 1.20. Ta sama zasada dla
   każdego sportu. Rynek, który dziś tego nie robi, **nie jest wycinany** —
   mierzymy go dalej.
2. „Krzywa per pasmo kursu”: pewność nie wyższa, niż takie `p` trafiało na
   liniach Superbetu w tym samym paśmie kursu. Kurs tylko obniża.

## Pomiar

`docs/sofa/evidence/discrimination_within_price_2026-10-07.md`. W skrócie:

- statystyki rozróżniają nogi w paśmie kursu: piłka +14,4 pp [+8,2; +19,6],
  koszykówka +9,1 pp [+1,0; +15,4];
- hokej, siatkówka, tenis i CS2: szum;
- krzywa liczona tylko z `p` zawyża przy długich kursach (koszykówka handicap
  p 0,70–0,80: 0,81 przy kursie < 1,30, 0,62 przy 1,60–2,20; tenis
  `games_won_for` OVER przy 1,60–2,20: 0,47 przy deklarowanych ~0,75).

## Zmiana (od 2026-10-08 00:00Z, `epochs.LINE_EVIDENCE_FROM_UTC`)

- `bet.sofa.line_evidence`, `scripts/sofa/fit_line_evidence.py`,
  `config/sofa_superbet_line_evidence.json` (dopasowany 2026-10-07: piłka i
  tenis 10-05..10-06, sporty 09-20..10-06, wiersze z
  `fit_sport_confidence.py --before 2026-10-07 --dry-run --rows-out`).
- CONFIDENCE: bez odmów z nazwy (`refused_markets`, `admitted_player_markets`,
  `admitted_tennis_set_markets`, `DERIVED_NOT_CALIBRATABLE`).
- SPORT_CONFIDENCE: każdy dopasowany klucz, nie tylko `admitted`; koszykówka
  i CS2 nie są już `NOT_CALIBRATED` w całości.
- Pewność = najniższa z: krzywej (obniżonej o istotne zawyżenie klucza na
  jego liniach) i limitu pasma kursu (gdy linie pasma trafiały istotnie
  poniżej). Rynek bez krzywej: dolna granica Wilsona własnych linii, inaczej
  `NO_LINE_EVIDENCE`.

## Powtórka kuponu 10-07 (SOFA_NOW 07:31Z, katalog roboczy)

| | stara reguła | nowa |
|---|---|---|
| piłka + tenis, nogi niezablokowane | 590 | 389 (+102 / −303) |
| hokej | 80 | 171 |
| koszykówka | 0 | 40 |
| siatkówka | 0 | 0 (`TOURNAMENT_NEVER_SETTLED`) |
| CS2 | 0 | 0 |

- Wypada głównie tenisowe `games_won_for` (−253). Na swoich liniach z
  10-05..10-06 deklarowało 0,751, a trafiało 0,633 (278 linii, 89 meczów).
- Dochodzą rynki setowe tenisa i `goals_1h_total UNDER` (deklarowane 0,799,
  trafione 0,800 na 110 liniach).
- Średnie 1/kurs drukowanych nóg rośnie z 0,71 do 0,80, czyli kupon przesuwa
  się w stronę krótszych kursów.

## Czego nie zrobiono

- Rynki bez modelu (`MARKET_NOT_ALLOWED`): kwarty, druga połowa, parzyste /
  nieparzyste, dnb i propsy zawodników w koszykówce i hokeju. To następna
  praca: model dla każdej rodziny, potem ten sam dowód z linii.
- Siatkówka nadal wymaga turnieju z rozliczonym meczem w ostatnich 14 dniach.
  To bramka modelu, nie nazwy; nie była mierzona.
- `CROSS_LEAGUE_UNLINKED`, `NOT_SETTLEABLE`, `NO_CLASS_CURVE` bez zmian.
- Piłka i tenis mają tylko dwa dni linii stats-only. Korekty i limity są
  liczone na małej próbie i rosną z każdym rozliczonym dniem
  (`fit_line_evidence.py` między dniami, po każdym refitcie krzywych).
- Suspicion (niezmierzone): hokej handicap przy p ≥ 0,95 i kursie 1,37 drukuje
  0,957, bo ani klucz, ani sport nie mają tam 20 linii w paśmie.
- Test `test_chaos_stages::test_offer_refused_from_the_first_request_fails_and_keeps_the_file`
  pada też na czystym HEAD; nie badany.
