# Tenis: rynki serwisu Superbetu w nowym formacie "N+" - walidacja (2026-11-20)

Pomiar tylko do odczytu: nic w repozytorium nie zmienione, baza otwarta `mode=ro`,
sieć nie pytana (cache + `unmapped_prices`). Skrypty i wyniki w tym katalogu
(`s1_collect.py` .. `s7_extra.py`, logi `s2.log`, `s4.log`, `s5.log`, `s7.log`).

## Werdykt

**Nie dodawać do druku.** Rynek jest prawdziwy, rozliczalny w 100% i model punktowy
wycenia go dobrze (skalibrowany), ale Superbet płaci na tych drabinkach "N+"
**57.5% stawki w zwrocie** (stare dwustronne O/U tych samych wielkości: 94%).
Po wszystkich bramkach zostaje ~3 nogi dziennie, realizacja ≈ cena, ROI -0.8%
[-17.2, +12.7] przed podatkiem, -12.7% [-26.3, -0.8] po 12% podatku (85 nóg /
34 mecze, hold-out). Model nie znajduje przecenionych szczebli: szczeble, gdzie
p modelu >= 1/kurs, tracą -27.9%. Te same liczby można zbierać dalej bez kodu:
OFFER już zapisuje je w `unmapped_prices`, a ten pomiar da się powtórzyć.

## 1. Inwentarz (s1_collect.py, s2_inventory.py -> s2.log)

Źródło: pliki OFFER `runs/sofa/<d>/unmapped_prices/<ts>.jsonl.gz` (bez prefiksu
sportu), tenis wg `02_fixtures.json`, strony Superbetu z `01_board.json`;
ostatni snapshot przed startem (min(kickoff Sofascore, kickoff Superbetu)) na
(event, rynek, wybór). Szablony: `market_coverage.template_of`.

- **Dni z formatem:** 30 (10-17 .. 11-20); **696 meczów, 94 309 wyborów,
  18 792 drabinek** (średnio 5.0 szczebla). 10-15/10-16 brak; w dni 10-20, 10-26,
  10-27, 11-02, 11-03 formatu nie było wcale (w plikach tylko "Podwójne błędy"
  dwu-drogowe i handicap) - to oferta zmienna dzień do dnia, nie trwałe przejście.
- **Mecze dziennie:** 10-17..11-09: 4-33; od 11-10: 66, 30, 24, 21, 10, 5, 32, 57,
  31, 30, 23 (11-20 niezakończony). Drugi sposób (surowy zgrep "Asy" w plikach
  11-17): 58 eventów (z eventami tylko po starcie), mój licznik przed startem 57.
- **Kategorie:** Challenger 469, WTA 125 120, ATP 82, WTA 25 - nie ITF.
- **Szablony** (24, każdy ~3 500 wyborów): mecz / 1. set / 2. set x suma / {a} /
  {b} x asy / podwójne błędy / asy + podwójne błędy. Wybór "N+",
  `specialBetValue` "N" (mecz) albo "S-N" (set S); niezgodnych z nazwą: 0 z 94 309.
- **Status:** ostatni snapshot przed startem `block` = 8 500 wyborów (8 425 nigdy
  aktywnych, wszystkie z kursem 1.00 - to szczeble "1+" (5 206), "2+" (2 051) ...;
  "1+ @1.00" = zablokowany, niegrywalny). Wyłączone z pomiaru.
- **Kursy (ostatni aktywny):** 1.01-1.086 6 228 (ODDS_TOO_LOW), 1.087-1.30 14 221,
  1.30-1.60 14 739, 1.60-2.20 19 478, 2.20-5 20 375, >= 5 10 843.
- **Świeżość:** od ostatniej ceny do startu p10/p50/p90 = 0.6 / 3.4 / 8.8 h.
- Drabinki niemonotoniczne: 45 z 18 792.
- Poza zakresem: "Podwójne błędy" (kto więcej, 1 083 wyborów z nazwiskiem) i
  "Podwójne błędy - handicap" (820; w `market_coverage` już MAPPABLE
  `tn.handicap_double_faults`), "Dwa asy / dwa podwójne błędy z rzędu" (11).

## 2. Ten sam event, strony, równoważność

- **Brak podwójnego liczenia:** eventy z kluczami serwisu w `04_offer.json` (stary
  format, 10-01..11-20) a eventy nowego formatu: **część wspólna 0**. Stary
  format: ATP 329, WTA 174, Challenger 24, WTA 125 10, BJK 6 - turnieje rozłączne.
- **Strony:** {a} = `side_a` z boardu; we wszystkich 696 meczach `side_a` ↔
  `home_name` Sofascore (tokeny nazwisk; 0 zamienionych, 0 niejasnych) - zgodnie
  z F25. Więc {a} = home, {b} = away.
- **"N+" == OVER (N-0.5)** tego samego klucza (np. "1. set - {a} asy 2+" =
  `aces_set1_for` OVER 1.5 strony a): liczba całkowita >= N ⇔ > N-0.5; brak pusha.
  Mapowanie szablon -> klucz: `s3_grade.py` (`TPL`). Regulaminu Superbetu dla
  "N+" nie czytałem (patrz ryzyka).

## 3. Rozliczalność (s3_grade.py)

Jak SETTLE (`run_settle._event_payload` + `metrics.extract_metric(...,
settling=True)`): `sofa_event_detail` -> `is_completed_event` /
`settle_completed`, `sofa_event_stats.statistics_json` -> `extract_flat_statistics`.

- Mecze: **639 OK / 696**; reszta: RETIRED 22 (zwrot), NOT_FINISHED 29 (23 to
  mecze 11-20, 6 starszych), WALKOVER 3, CANCELED 3. **Każdy wybór meczu OK
  rozliczony** (0 luk statystyk: 86 598 WIN/LOSS; Challenger 424/424 OK ma
  statystyki asów / pb, też per set). Pokrycie = 100% zakończonych normalnie.
- Drugi sposób: 400 losowych rozliczonych wyborów przeliczone wprost z surowego
  `statistics_json` (okres ALL/1ST/2ND, `aces` / `doubleFaults`): **400/400 zgodnych**.

## 4. Model (s4_model.py -> s4.log; s5_measure.py)

Ścieżka SHEET (`run_sheet.load_point_pricer`): `load_point_history` (276 962
meczów, 639 s, RSS 0.41 GB) -> `tennis_point_sheet.fixture_match` ->
`forecast_fixtures` (as of startu) -> `PointPricer` (4 000 symulacji, ziarno =
id). **718 prognoz, 0 NOT_RATED** (wszystkie bo3, oba id). p(N+) =
`PointPricer.p(id, klucz, strona, N-0.5, "OVER")`.

**Sprawdzenie odtworzenia SHEET:** te same wywołania dla 22 meczów starego
formatu 11-12..11-19 vs ich `p_central` w `sofa_settled_row`: 2 582 wierszy,
średnio |różnica| 0.0127 (max 0.080), średnia ze znakiem 0.0000, korelacja
0.993; 44% w 0.005. Różnice są per mecz (0.001..0.048) - mój przebieg czyta
dzisiejszy cache (mecze dociągnięte po budowie dnia). Brier na tych wierszach:
mój 0.2052, SHEET 0.2083 - mój p jest lekko lepiej poinformowany (ryzyko
optymizmu, nie bias kierunkowy).

**Łańcuch CONFIDENCE** (jak `run_confidence.py` dla dnia 11-20): `Calibration`
-> `live_only_curves.for_day` -> `tennis_point_curves.for_day` (krzywe
`config/sofa_tennis_point_curves.json`, klucz `market|OVER`, klasa
`tennis_women` z `match_class`) -> `LineEvidence` (zainstalowana, v2,
offset wg d dla tenisa) -> `Settleability` -> bramki: conf >= 0.70, conf x kurs
>= 0.90, kurs >= 1/0.9202, `one_sided_single` (źródło "market:"/"line:", n >= 300).
- Krzywe mają kubełki do 0.875-0.900; p >= 0.90 nie ma krzywej (klucze w
  `no_pool_keys`) -> czyta tylko własne linie (`sb:`), co **nie** spełnia
  `one_sided_single` (89 nóg odrzuconych tak).
- Źródło nóg po bramkach: zawsze "market:<klucz>|OVER", n bucketu 2 000-50 000 ->
  `one_sided_single` spełnione. NOT_SETTLEABLE: 0.
- Odmowy (wszystkie dni, 86 598 rozliczonych): conf < 0.70 71 697, zablokowane
  7 806, ODDS_TOO_LOW 5 604, x < 0.90 1 184, one-sided bez własnej krzywej 89,
  NO_LINE_EVIDENCE 61, **przechodzi 157**.

## 5. Pomiar (s5_measure.py -> s5.log; s7_extra.py -> s7.log)

Hold-out = mecze 10-21..11-19 (krzywe z historii < 10-20, stałe modelu < 2026):
**73 716 wyborów grywalnych, 600 meczów**. Bootstrap po meczach, 2 000 losowań.

### Brier / log-loss

| rodzina | wybory | Brier model | Brier 1/kurs | model - 1/kurs [95%] | model - "de-vig 8.8%" [95%] |
|---|---|---|---|---|---|
| wszystko | 73 716 | 0.1767 | 0.2115 | -0.0348 [-0.0420, -0.0280] | -0.0200 [-0.0255, -0.0146] |
| asy, mecz | 8 486 | 0.2040 | 0.2252 | -0.0212 [-0.0333, -0.0091] | -0.0088 [-0.0180, +0.0004] |
| asy, set | 16 477 | 0.1549 | 0.1780 | -0.0232 [-0.0294, -0.0169] | -0.0126 [-0.0178, -0.0072] |
| pb, mecz | 7 825 | 0.1965 | 0.2528 | -0.0562 [-0.0681, -0.0447] | -0.0346 [-0.0436, -0.0250] |
| pb, set | 16 556 | 0.1300 | 0.1697 | -0.0397 [-0.0450, -0.0346] | -0.0260 [-0.0304, -0.0219] |
| asy+pb, mecz | 8 769 | 0.2257 | 0.2634 | -0.0376 [-0.0513, -0.0238] | -0.0195 [-0.0295, -0.0092] |
| asy+pb, set | 15 603 | 0.1968 | 0.2338 | -0.0370 [-0.0454, -0.0284] | -0.0205 [-0.0270, -0.0139] |

Log-loss model - de-vig: -0.0529 [-0.0666, -0.0400]. "De-vig 8.8%" =
(1/kurs)/(1 + mediana marży par O/U starego formatu tego klucza, 0.087-0.090,
z `sofa_settled_row`) - **przybliżenie i to złe**: prawdziwa marża tego formatu
jest kilka razy większa (niżej). Model "wygrywa" z ceną, bo cena jest bardzo
zawyżona, nie dlatego, że model ma przewagę: średnio 1/kurs 0.548, p modelu
0.348, realizacja 0.368.

### Cena: zwrot dla gracza (drugi sposób na to samo)

- Każdy grywalny szczebel hold-outu: **RTP = mean(wygrana x kurs) = 0.575**
  (73 716); kurs 1.00-1.15: 0.786; 1.15-1.30: 0.758; 1.30-1.60: 0.724;
  1.60-2.20: 0.634; 2.20-5: 0.426; >= 5: 0.173.
- Stary format, strony OVER tych samych kluczy (10-21..11-19, 10 312 linii):
  **RTP 0.94**, mediana marży pary 8.8%.
- Najniższy aktywny szczebel drabinki: 1/kurs 0.866, realizacja 0.662 (16 200);
  drugi 0.647 / 0.445; trzeci 0.480 / 0.293.
- Po kategoriach (1/kurs, p, realizacja): ATP 0.586 / 0.385 / 0.394; Challenger
  0.554 / 0.351 / 0.376; WTA 125 0.509 / 0.319 / 0.336; WTA 0.537 / 0.350 / 0.295 (17 meczów).

### Kalibracja (hold-out)

| pasmo | wg p modelu: deklar. / realiz. [95%] (n / mecze) | wg confidence | wg 1/kurs |
|---|---|---|---|
| 0.60-0.70 | 0.647 / 0.685 [0.662, 0.709] (7 442 / 598) | 0.650 / 0.689 [0.665, 0.711] | 0.650 / 0.462 [0.439, 0.486] |
| 0.70-0.80 | 0.742 / 0.767 [0.741, 0.788] (4 210 / 567) | 0.746 / 0.770 [0.747, 0.794] (3 930 / 559) | 0.749 / 0.547 [0.524, 0.571] |
| 0.80-0.92 | 0.825 / 0.810 [0.756, 0.858] (490 / 192) | 0.820 / 0.806 [0.755, 0.854] (418 / 184) | 0.858 / 0.657 [0.637, 0.678] |

Model i confidence skalibrowane (w środku lekko ostrożne, +2-4 pp); cena
nad-obiecuje o ~20 pp w każdym paśmie.

### Nogi po wszystkich bramkach

Hold-out: **85 nóg / 34 mecze** w 26 dniach z formatem = **3.3 dziennie**, ale
13 z 26 dni ma 0 (rozkład: 0,0,8,0,2,2,1,3,20,0,0,0,0,17,0,8,6,2,2,0,0,0,2,12,0,0).
Kursy 1.09-1.29. Confidence 0.770, p 0.771, 1/kurs 0.830, **realizacja 0.824
[0.694, 0.929]**, realizacja - confidence +0.053 [-0.079, +0.162].
**ROI przed podatkiem -0.8% [-17.2, +12.7]; po 12% podatku -12.7% [-26.3, -0.8].**
Wszystkie dni (z 10-17..10-20, gdzie krzywe mogły widzieć część meczów): 157 nóg
/ 47 meczów, realizacja 0.777, ROI -7.3% [-20.5, +4.3], po podatku -18.5%
[-30.0, -8.3] (70 nóg z samego 10-17).
Warianty (hold-out): p modelu >= 0.70 i x >= 0.90 bez krzywej: 206 nóg, ROI -5.8%;
krzywa bez dowodów linii: 184 nogi, -1.5%; pełny łańcuch -0.8%; **p modelu >=
1/kurs (każdy p): 327 nóg, realizacja 0.385 vs 1/kurs 0.422, ROI -27.9%**.
Dowody linii prawie nic nie ruszają (offset średnio -0.0012 na wierszach z
krzywą >= 0.70; 145 nóg przycięte przez band cap).

## 6. Te same klucze w starym formacie (s6_old.py -> old_pairs.jsonl)

`sofa_settled_row` 10-21..11-19, strony OVER z parą, p modelu z backfillu
(`data/line_evidence/tennis_point_model_p.json.gz`, dni < 11-06) albo
`p_central` (>= 11-06): 10 289 linii / 286 meczów. Brier model - cena bez marży
-0.0011 [-0.0057, +0.0034] (asy mecz +0.0027, pb mecz -0.0046 - wszystkie
przedziały przez zero) - jak w pomiarze z 11-05: "tak dobry jak cena". Średnio
1/kurs OVER 0.538, cena bez marży 0.492, p 0.474, realizacja 0.507.
**Nowy format jest wyceniony inaczej:** marża efektywna wielokrotnie większa
(RTP 0.575 vs 0.94), stare drabinki stawiają linię blisko 50%, nowe pokazują 5
szczebli od ~1.05-1.25 w górę, wszystkie OVER.

## 7. Szkic wdrożenia (gdyby operator chciał; NIE rekomendowane do druku)

1. `bet.sofa.epochs`: `TENNIS_SERVE_N_PLUS_FROM_UTC` (następny dzień 00:00Z),
   funkcja `tennis_serve_n_plus(date, build_at)`.
2. `src/bet/sofa/market_mapper.py`: nowa funkcja `classify_serve_ladder(market_name,
   selection, raw_line, listing_names)` - 24 szablony (fold: "asy",
   "podwojne bledy", "asy + podwojne bledy", z prefiksem "[12]. set - " i
   opcjonalnym zawodnikiem, zawodnik = jedna z `listing_names`, kolejność stron
   jak F25); wybór `^(\d+)\+$` -> (klucz, podmiot, N-0.5, "OVER"); sprawdzić, że
   N z nazwy = N z `specialBetValue` (prefiks seta = zakres, jak `offer.parse_line`).
3. `src/bet/sofa/offer.py` `classify_odd`: nowy argument `tennis_serve_n_plus`,
   wołany na końcu (jak `tennis_sets`), tylko dla meczu tenisowego; nieaktywne
   (`block`, 1.00) i tak odrzuca OFFER. Brak UNDER -> `run_confidence` sam wpisze
   `one_sided_market` (pętla `one_sided`, wiersze 383-411).
4. Kolizje: na meczu z oboma formatami ten sam klucz / linia dałby dwa kursy -
   dziś część wspólna 0, ale reguła `price_collisions` musi wybrać dwustronny.
5. `src/bet/sofa/market_coverage.py`: reguły `_m(...)` dla szablonów -> MAPPABLE
   (dziś "asy..." UNCLASSIFIED, "podwojne bledy" `tn.double_faults_unknown_shape`).
6. `bet.sofa.superbet_names`: nazwy "1. set - X asy: 2+" na nodze.
7. SETTLE: bez zmian (te same klucze, linie .5, `_subject_is_home` po nazwisku).
8. SHEET / krzywe: bez zmian (klucze w `TENNIS_POINT_MODEL_MARKETS`); marker
   wiersza zbędny, ale formatowi przydałby się znacznik (`serve_n_plus_rule`),
   bo dowody linii (`fit_line_evidence`) zmieszają linie RTP 0.57 i 0.94 w tym
   samym kluczu `aces_set1_for|OVER` (pasma cen / band cap liczone wspólnie).
9. Testy (`tests/sofa/`): klasyfikacja każdego szablonu + "S-N", strona {a}/{b},
   blokada nazwy z liczbą ("1. set - X asy 2+" nie może trafić do `aces_for`),
   przełącznik on/off, settle z fixture'em, `one_sided_single` na nodze z
   krzywą i bez (p >= 0.90), rejestr testów.
10. Wysiłek: ~1 dzień z testami; grupa księgi "od <dzień>".

## 8. Ryzyka i czego nie sprawdziłem

- **Regulamin Superbetu dla "N+"** (>= N, co przy kreczu / niedokończonym secie)
  - nieprzeczytany. Przy "> N" realizacja byłaby jeszcze niższa, więc wniosek o
  RTP się nie zmienia.
- **Ceny na ekranie** vs payload API - nie porównane (bez operatora). Cena =
  ostatni snapshot OFFER przed startem (mediana 3.4 h przed), nie zamknięcie.
- Mój p czyta dzisiejszy cache (|diff| 0.013 do SHEET, bez biasu); lekki optymizm.
- Dowody linii / settleability = pliki z 11-20, nie as of dnia nogi; krzywe na
  historii < 10-20, więc 10-17..10-19 tylko w "wszystkie dni".
- Nie symulowane: STALE_PRICE / świeżość, start, odczyty analityków, SAME_EVENT
  (kilka szczebli jednej drabinki może przejść naraz - liczone wszystkie).
- 85 nóg / 34 mecze: przedział ROI ±15 pp - nie da się rozstrzygnąć zysku, ale
  da się rozstrzygnąć skalę (3/dzień, często 0) i cenę (RTP 0.575).
- "De-vig" przez marżę starego formatu jest przybliżeniem i tu nieadekwatnym
  (marża formatu N+ jest kilka razy większa); prawdziwego de-vig drabinki
  jednostronnej nie da się zrobić.
- Formatu nie było w części dni; jego przyszły zakres (więcej ATP?) nieznany.
