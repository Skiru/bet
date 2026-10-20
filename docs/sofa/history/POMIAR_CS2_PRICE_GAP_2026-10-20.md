# CS2: pewność ponad cenę - pomiar i flaga (2026-10-20)

**Wynik:** noga CS2, której pewność przewyższa 1/kurs o więcej niż 0,03,
trafia około ceny, a nie około pewności: 238 linii / 77 serii, **-18,6 pp
[-27,1; -10,1]** wobec pewności, -2,1 pp wobec ceny bez marży. ROI tej grupy
-8,8% [-23,1; +4,9] wobec -0,6% reszty - przedział obejmuje zero. Przekłamuje
drukowana liczba, nie mierzalnie pieniądze - ten sam wzór co w piłce i tenisie.
Decyzja operatora (2026-10-20, „TAK!"): CS2 dostaje flagę `price_gap`
(`CONFIDENCE_ABOVE_PRICE`) od `epochs.CS2_PRICE_GAP_FROM_UTC` = 2026-10-21 00:00Z.
To adnotacja: żadna noga nie jest dodana, zdjęta ani przestawiona na kuponie,
żadna pewność się nie rusza.

## Skąd pytanie

2026-10-20, BBL - BC.Game (DraculaN Playoffs, Bo3): „BBL liczba map: powyżej
0.5" @1.44, pewność 0,718, przegrana 0:2. Operator: „tego dało się uniknąć".
Co wiedziano przed startem:

- **Analityk** (`2026-10-20_analiza_cs2_kupon_1047_1.md`, dossier): turniej
  (DraculaN Playoffs, Season 7, Bo3), faworyta („BBL to underdog meczu",
  Zwycięzca 2.32 / 1.55) i h2h (03.10 BBL 2:1 BC.Game). Werdykt KEEP - nie
  znalazł faktu łamiącego nogę (stand-in, przełożenie, format).
- **Model** (`cs2_engine`, historia ucięta na 11:00Z): turnieju nie zna
  (`MapRow` nie ma pola turnieju, Elo nie ma członu rangi zawodów); h2h widzi
  tylko jako trzy zwykłe mapy w Elo. Faworyta liczy sam, bez ceny: **BBL
  52,7% na serię** (p mapy 0,52; Elo składów 1678 vs 1681, Elo drużyn +22 dla
  BBL; s1mple w bazie 1536 Elo na 118 mapach), rynek bez marży ~40%. Noga:
  `forecast_p` 0,734 -> pewność 0,718, rynek bez marży ~0,64.
- **Rodzina** `cs2|team_maps|OVER` w `family_record.json`: 22 nogi, 18
  wygranych, +0,36 j. - nic nie ostrzegało.

Sama noga BBL była 0,024 ponad 1/kurs, więc i nowa flaga by jej nie
oznaczyła. Wynik meczu nie jest argumentem; pytanie brzmiało, czy rozjazd
modelu z rynkiem jest mierzalnym sygnałem.

## Pomiar

`scripts/sofa/measure_cs2_price_gap.py` (tylko odczyt). Wydrukowanych nóg CS2
było za mało (80 w 10-07..10-19), więc pomiar idzie po wszystkich
rozliczonych liniach Superbetu (`runs/sofa/cs2/<d>/settled.json`, `graded`,
WIN / LOSS): `model_p` z rozliczenia przez zainstalowaną krzywą CS2
(`.next.json`, każdy dopasowany klucz), linia zostaje, gdy przeszłaby próg
kuponu (pewność >= 0,70, x >= 0,90). Bootstrap po seriach, 2000 losowań.

```
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_cs2_price_gap.py --from 2026-09-28 --to 2026-10-19
```

| grupa | linie | serie | trafione | pewność | cena bez marży | trafione - pewność, pp [95%] | trafione - cena, pp [95%] | ROI % [95%] |
|---|---|---|---|---|---|---|---|---|
| drukowalne (pewność >= 0,70, x >= 0,90) | 472 | 135 | 0.667 | 0.750 | 0.665 | -8.3 [-14.9, -1.6] | +0.2 [-6.5, +6.5] | -4.7 [-14.5, +4.4] |
| pewność > 1/kurs + 0.03 (flaga) | 238 | 77 | 0.563 | 0.750 | 0.585 | -18.6 [-27.1, -10.1] | -2.1 [-11.0, +6.4] | -8.8 [-23.1, +4.9] |
| reszta | 234 | 92 | 0.773 | 0.751 | 0.747 | +2.2 [-7.1, +10.7] | +2.6 [-6.5, +11.3] | -0.6 [-12.7, +10.6] |
| rodziny serii, flaga | 38 | 25 | 0.658 | 0.755 | 0.616 | -9.7 [-30.0, +8.8] | +4.2 [-16.8, +23.5] | +2.2 [-30.2, +33.1] |
| rodziny serii, reszta | 135 | 64 | 0.815 | 0.770 | 0.773 | +4.5 [-6.6, +14.5] | +4.2 [-6.6, +14.3] | +1.8 [-12.3, +14.8] |

Dodatkowo (skrypt w scratchpadzie, nie w repo, ten sam zbiór): nogi drużyny,
którą model widzi faworytem, a rynek underdogiem (z `match_winner`): 55 linii
/ 30 serii, trafione 0,691 przy cenie 0,654, ROI 0,0% [-26; +25] - **brak
śladu**, że taki rozjazd w rodzinach serii traci. Nie zdejmujemy nóg za
niezgodę z rynkiem.

**Ograniczenia (nazwane):**
- dowody z linii (offset, czapka pasma) nie są nałożone - tylko obniżają, więc
  część z 238 linii mogła nie przejść progu;
- `model_p` starszego dnia to silnik z tamtego dnia;
- 22 dni, 77 serii z flagą - przedziały szerokie; pieniądze nierozstrzygnięte;
- to linie Superbetu, nie wydrukowane nogi - test na wydrukowanych nogach od
  10-21: `T-CS2-PRICE-GAP-flag` (`config/sofa_test_registry.json`).

## Co się zmienia od 2026-10-21 00:00Z

- `bet.sofa.price_gap`: `MEASURED["cs2"]` (-18,6 pp [-27,1; -10,1], 238 / 77,
  okno 09-28..10-19), `LATER_SPORTS = {"cs2"}` - CS2 flagowany tylko, gdy
  budowa poda `extra` (`epochs.price_gap_sports`).
- `build_coupon.py`: `price_gap_extra`, w dokumencie
  `price_gap.later_sports`.
- PDF / HTML: „pewność +0,07 ponad cenę - takie nogi trafiały ~19 pp poniżej
  pewności, około ceny (CS2, 238 linii Superbetu 09-28..10-19)".
- `confidence.read_value`: oflagowana noga CS2 ma pewność uciętą do 1/kurs +
  0,03 w kolejności czytania analityków (zmienia, które nogi mogą zostać
  zdjęte odczytem - stąd przełącznik od następnego dnia). Dzień zbudowany
  przed przełącznikiem nie ma flag CS2 i czyta się po staremu.
- Kupon z czatu (`slip_builder`): szansa oflagowanej nogi CS2 = cena, nie
  pewność (zasada już obowiązująca dla `price_gap`).

Testy: `tests/sofa/test_cs2_price_gap.py`.
