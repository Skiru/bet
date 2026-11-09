# Kartki bez członu closeness — 2026-11-09

Przełącznik `epochs.CARDS_CLOSENESS_OFF_FROM_UTC` = **2026-11-10 00:00Z**
(`cards_closeness_off_v1`). Polecenie operatora 2026-11-09: „zrób 3 iteracje,
sprawdź w symulacji, znajdź dziury i błędy i popraw”, z regułą z 11-06
(„lepsze od obecnego = instaluj, od następnego dnia 00:00Z”). Dzień 11-09
nie jest ruszany. Grupa księgi: „od 11-10” (ta sama, która zaczyna się od
terminarza).

Od przełącznika człon closeness (`bet.sofa.closeness_stretch`) działa tylko
na `shots_total` / `shots_1h_total`. `cards_points_for`, `cards_points_total`
oraz połowy kartek (ich centrum strony bierze człon pełnego meczu przez
`run_sheet.card_half_term_mults`) zachowują GAME_STATE i sędziego, ale już nie
exp(g1 |s| + g2 s²).

## Iteracja 1 — co w pewności faktycznie wchodzi (metadane)

Każda rozliczona noga kuponu 10-24..11-08 (`13_results.json`) połączona z
metadanymi z `11_coupon.json`: 95 156 nóg. Bootstrap / błąd po meczu.

- Kalibracja ogólna: piłka 82 449 nóg, trafione 0,787 przy pewności 0,790;
  tenis 0,777 / 0,789; hokej 0,794 / 0,782.
- Od 10-31 (po `PRICE_GAP_OFFSET`) w piłce i tenisie **żadna metadana nie
  odróżnia trafień od pudeł ponad samą pewność**: próbka własna minus
  pewność, liczność próbki, model minus pewność, rating minus pewność, offset,
  marża, godzina, wiek próbki, źródło krzywej — wszystkie różnice ≤ ~3 pp,
  żadna nie powtarza się w obu połowach okna (10-31..11-04 / 11-05..11-08).
- Pewność powyżej ceny: w piłce od 10-31 prawie znikła (455 nóg). Zostały
  koszykówka i siatkówka (bez offsetu po d). Ponowny pomiar offsetu po d
  dla koszykówki / siatkówki / CS2 na rozliczonych liniach Superbetu (uczenie
  przed cięciem, test po nim; cięcia 10-22 / 10-29 / 11-02; pełny łańcuch z
  limitem pasma kursu): koszykówka lepsza tylko przy cięciu 10-22, przy
  10-29 i 11-02 Brier gorszy (+1,8e-3, +4,3e-3); siatkówka zaniża
  (+4,6 pp wobec +2,3), Brier bez zmian; CS2 za mało. **Bez zmian** — jak
  decyzja z 10-30, teraz na 10 dniach więcej.
- Koszykówka: rynki okresów przed 11-06 −11,0 pp (z −2,7); po
  `BB_PERIOD_MARKET_LINES` +2,5 pp (70 nóg) — już naprawione.

## Iteracja 2 — błędy

- Rozliczenia: każda noga liczbowa (96 456) ma wynik zgodny z `actual`,
  linią i kierunkiem; rynki 0/1 (`result_or_*`, `btts_or_over`, `dc_and_*`)
  i różnicowe (`handicap_cards_points`, `most_*`, różnica z perspektywy
  gospodarza) sprawdzone osobno — **0 błędnych rozliczeń**.
- Bramki druku na wszystkich nogach: 0 nóg z pewnością < 0,70 bez
  `floor_rule`, 0 z x < 0,90, 0 z marżą > 15%.
- Jedyna komórka rynku poza szumem: `cards_points_for|UNDER` −8,3 pp
  (n 292, z −3,0), na linii 2,5: −15,2 pp (n 122, z −3,4); OVER 1,5
  +13 pp. Wzór przesunięcia, nie szumu.

### Kartki na wszystkich rozliczonych liniach Superbetu

`07_settled.json`, każda linia z ceną, krzywe dnia 11-09, drukowalne
(krzywa ≥ 0,70), realizacja − krzywa:

| linia | przed 10-21 | 10-21..10-30 | 10-31..11-08 |
|---|---|---|---|
| cards_points_for UNDER 2,5 | −2,1 [−9,2; +5,6] | −4,4 | −12,2 [−19,0; −5,7] |
| cards_points_total UNDER 4,5 | (nie drukowalne) | −13,5 [−23,4; −3,1] | −16,4 [−25,4; −6,2] |
| cards_points_total UNDER 5,5 | −0,4 | −5,1 | −4,6 |
| cards_points_total OVER 1,5 | +2,3 | +5,6 [+1,9; +10,1] | +5,9 [+2,3; +9,5] |

Przed 10-21 kartki były skalibrowane. Od 10-21 (sędzia i closeness w
centrum kartek) UNDER przeszacowuje, OVER zaniża.

Poziom (faktyczne / centrum SHEET), wszystkie wiersze z wynikiem:

| rynek | przed 10-21 | 10-21..10-30 | 10-31..11-08 |
|---|---|---|---|
| cards_points_total | 1,016 | 1,056 | 1,077 |
| cards_points_for | 1,001 | 1,031 | 1,077 |
| rożne / faule / strzały / gole / auty / spalone (sumy) | 0,96–1,03 | 0,99–1,03 | 0,96–1,02 |

Tylko kartki dryfują. Średni mnożnik od 10-21: sędzia 0,98–0,99,
closeness 0,974.

Wykładnik członu closeness na żywym centrum: faktyczne ~ Poisson(centrum bez
closeness × CL^b), wolny poziom, bootstrap 200. Zainstalowane b = 1.

| rynek | 10-21..11-08 | 10-21..10-30 | 10-31..11-08 |
|---|---|---|---|
| cards_points_for (n 2 185) | −0,20 [−0,65; +0,40] | −0,10 [−0,75; +0,80] | −0,30 [−0,95; +0,40] |
| cards_points_total (n 1 200) | −0,15 [−0,75; +0,45] | +0,00 [−0,85; +1,00] | −0,30 [−1,05; +0,40] |

W każdej połowie przedział wyklucza 1. Przy closeness ≤ 0,85 faktycznych
kartek było 1,40× (drużyna) / 1,49× (suma) centrum; bez członu 1,06 / 1,14.
Sędzia ma dobry kierunek (bez niego mecze „łagodnego” sędziego realizują
0,96–0,99, „surowego” 1,04–1,12) — zostaje.

Pomiar z 10-21 (historia, wszystkie ligi 2026, walk-forward) mówił
odwrotnie. Drukuje populacja Superbetu; ona rozstrzyga.

## Iteracja 3 — symulacja i wdrożenie

Każda rozliczona linia kartek 10-21..11-08 (18 542 linie, 1 200 meczów):
p przeliczone z centrum bez closeness przy dyspersji NB odtworzonej z
własnego p SHEET (|Δp| mediana 0,0000, p95 0,0001 na 18 842 liniach),
przez krzywe; „druk” = pewność ≥ 0,70 i x ≥ 0,90; bootstrap po meczu,
parami wobec obecnego łańcucha.

| wariant | ΔBrier pewności (×1e-4) | druk: realizacja − pewność | ROI |
|---|---|---|---|
| A obecny (closeness, krzywe 11-09) | 0 | −3,0 pp [−5,0; −1,0] | −6,3% |
| **B bez closeness, krzywe 11-09** | **−5,6 [−20,5; +7,6]** | **−2,7 pp [−4,4; −0,8]** | −6,3% |
| C bez closeness, krzywe 10-17 | −6,4 [−22,5; +7,0] | −3,1 pp | −6,4% |
| D closeness, krzywe 10-17 | +0,3 | −3,5 pp | −6,5% |

Log-loss surowego p (bez − z): −36,2e-4 [−75,6; +1,4]; 10-21..10-30
−12,2 [−70,3; +41,1]; 10-31..11-08 −54,7 [−107,9; −6,5]. B jest lepsze
punktowo w obu połowach i nie gorsze w kalibracji ≥ 0,70 — reguła operatora
z 11-06 spełniona. Wdrożone B (krzywe bez zmian).

**To nie jest lekarstwo na przeszacowanie UNDER kartek**: po zmianie
wydrukowane UNDER nadal −5,6 pp (A −5,8). Reszta to dryf poziomu samych
kartek (+3..+5% ponad mnożniki) — otwarte; kandydaci: faza sezonu dla
kartek, średni `ratio` sędziów < 1 (0,98, różnie po ligach, n małe),
refit krzywych kartek na replayu z regułą. Nic z tego nie jest dziś
zmierzone na tyle, by zmieniać.

## Kod

- `epochs.CARDS_CLOSENESS_OFF*`, `epochs.cards_closeness_off(date, build_at)`.
- `closeness_stretch.ClosenessStretchTable.without`, `closeness_stretch.for_day`.
- `run_sheet`: tabela dnia przez `for_day`; marker `cards_closeness_rule`
  (`contracts.SheetRow`, `AUDIT_MARKER_FIELDS`); `rebuild_plan` powtarza SHEET
  na arkuszu bez markera.
- Replay: `calibrate_from_cache --cards-closeness-off` (wymaga
  `--closeness-stretch`, zapisane w `replay_rules`), `prepare_refit
  rebuild-cache-rows --cards-closeness-off`; `REPLAYABLE_SWITCHES`: instalacja
  krzywych bez tej flagi po przełączniku jest odrzucana.
- Line evidence: offsety kluczy kartek są fitowane na p dni sprzed
  przełącznika (z closeness); offset tylko obniża, a przeszacowanie UNDER
  zostaje po zmianie, więc nie budowano backfillu.
- Test: `tests/sofa/test_cards_closeness_off.py`; test naprzód
  `T-CARDS-CLOSENESS-OFF-forward` w `config/sofa_test_registry.json`.
- Skrypty pomiaru (tylko odczyt) w scratchpadzie sesji; liczby powyżej z
  `13_results.json`, `11_coupon.json`, `05_sheet.json`, `07_settled.json`
  dni 10-01..11-08.

## E2E

Kopia dnia 11-09 w scratchpadzie (`SOFA_NOW` 12:20Z), dwa ramiona: kontrola
(przełącznik jak w kodzie, 11-10) i próba (przełącznik przesunięty na 11-09).
Prawdziwe pliki 11-09: md5 bez zmian.

- SHEET: rc 0 w obu, 15 095 wierszy w każdym, te same klucze. Zmienione
  wiersze tylko w rodzinach kartek (179): `cards_points_for` 50,
  `cards_points_total` 40, `most_cards_points` 27, `cards_points_1h_total` 22,
  `cards_points_1h_for` 20, `both_over_cards_points` 14,
  `cards_points_2h_for` 4, `cards_points_2h_total` 2. Żaden inny rynek.
- Marker `cards_closeness_rule` na 8 790 wierszach piłki w próbie, 0 w
  kontroli. Centrum sumy kartek próba / kontrola: średnio 1,020 (min 1,000,
  max 1,046).
- Werdykty: BELOW_BAR 13 662 → 13 663, LEAN 526 → 525.
- CONFIDENCE: rc 0, 722 nogi w obu ramionach, ten sam zbiór; 7 nóg kartek
  (4 czerwone, `cards_points_for` OVER 1,5, `cards_points_total` OVER 3,5) z
  tą samą pewnością (krzywa / line evidence zdominowały różnicę p); 0 nóg
  spoza kartek ze zmienioną pewnością.

Wniosek: zmiana dotyka tylko kartek, skala zgodna z symulacją (centrum
+2% średnio), druk dnia praktycznie bez zmian.
