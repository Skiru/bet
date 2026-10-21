# Pomiar: cel plecaka kuponu z czatu - pewność skalibrowana zamiast szansy zmierzonej? (2026-10-20)

Pomiar tylko do odczytu. Nic w potoku (`src/bet/sofa/*`), konfiguracji, kuponach, odczytach ani w księdze nie zostało zmienione.
Skrypt: `scripts/sofa/measure_slip_objective.py`; wynik w załączniku odtwarza
`PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_slip_objective.py --from 2026-10-13 --to 2026-10-19` (ziarno 20261020, 2000 losowań).
Poprzedni pomiar: `docs/sofa/history/POMIAR_SZANSA_NOGI_KUPON_CZAT_2026-10-20.md`.

## Pytanie

Poprzedni pomiar: szansa zmierzona b (`slip_builder.measured_chance`) jest lepiej skalibrowana niż pewność a, ale a lepiej porządkuje nogi wewnątrz pasma ceny (1,30-1,45: +2,8 pp dla a, −0,8 pp dla b). Czy cel „porządek z pewności, poziom uczciwy” wybiera lepsze kupony niż obecny builder?

## Warianty (zarejestrowane przed pierwszym wynikiem, bez dopisków po fakcie)

- **B** (obecny): b = `measured_chance`, walk-forward (dzień d czyta tylko `runs/sofa/<d>/family_record.json`, 14 dni ściśle przed d).
- **A**: surowa pewność a (wydrukowana, `13_results.json`).
- **H1**: a_cal - pewność przekalibrowana walk-forward. Dla dnia testowego d: regresja **izotoniczna** (PAV na (a, trafienie), remisy łączone, potem interpolacja liniowa między średnimi a bloków - mapa ściśle rosnąca, płaska poza końcami; obcięta do [0,01; 0,99]), dopasowana na wszystkich rozliczonych wydrukowanych pojedynczych nogach kuponu `official` z dni **2026-10-05 .. d−1**; per sport, gdy sport ma ≥ 300 nóg treningowych, inaczej na wszystkich sportach razem. **Bez kursu jako współzmiennej** (wybrane przed wynikami - prostsza mapa).
- **H2**: min(a_cal, b) - uczciwy poziom, ograniczenie buildera zachowane.

Nie dodano żadnego wariantu po wynikach.

## Dane i okna treningowe

- **Test**: 2026-10-13 .. 2026-10-19, każda wydrukowana pojedyncza noga WIN/LOSS z `13_results.json` złączona z `11_coupon.json`, z określoną szansą b: **29 408 nóg / 3 572 meczów** (ten sam zbiór co w poprzednim pomiarze; 62 nogi bez b pominięte). Pula buildera (kurs 1,10-2,00): 28 188 nóg / 3 560 meczów.
- **Historia przed testem**: 2026-10-05 .. 10-12 (pierwszy kupon `11_coupon.json` to 10-05), oceny przez `record_results.graded_confidence` (ten sam grader co księga; na 10-13 zgadza się z `13_results.json`: 807 WIN / 222 LOSS): **8 859 nóg** (piłka 5 718, tenis 1 683, hokej 1 212, koszykówka 190, siatkówka 37, CS2 19).
- **Okno treningowe per dzień testowy** (rosnące, od 10-05 do d−1; od 10-13 dni testowe wchodzą do treningu następnych): 10-13: 8 859 nóg; 10-14: 9 881; 10-15: 11 044; 10-16: 12 435; 10-17: 15 511; 10-18: 27 553; 10-19: 36 382. Własna krzywa: piłka, tenis, hokej każdego dnia; koszykówka, siatkówka, CS2 zawsze z krzywej wspólnej. Żaden dzień nie odpadł z H1 - wszystkie warianty porównane na tych samych 7 dniach.
- **Ograniczenie, nazwane**: pewności z 10-05..10-12 pochodzą z innych krzywych (przed dowodem linii 10-07, przed refitem 10-13, przed rozciąganiem 10-17); izotoniczna uczy się mapy starszych pewności. To walk-forward bez podglądania, ale mapa może być nieaktualna - podejrzenie jako przyczyna złego wyniku H1 w tenisie (patrz niżej), niezmierzone.

## Metoda

1. **Noga**: Brier, log-loss, różnice sparowane (H1−B, H2−B, A−B, H1−A, H2−H1), bootstrap meczów (2000); kalibracja w przedziałach; ranking w paśmie kursu (podział na medianie p − 1/kurs, różnica (trafienie − 1/kurs) górnej i dolnej połowy); bez jednego dnia; per sport.
2. **Kupon**: dla każdego dnia testowego i okna startu (czas lokalny Europe/Warsaw): (i) **okna 3 h rozłączne** 10-13, 13-16, 16-19, 19-22, 22-01 - nie dzielą meczów, interwał z bootstrapu jednostek (dzień, okno), cele jednego okna razem w jednostce; (ii) **okna 3 h przesuwne** startujące co godzinę 10:00-23:00 - nakładają się, więc interwał z bootstrapu **dni** (7 dni - interwał zgrubny); (iii) cały dzień (7 kuponów na cel - tylko opisowo). Cele 2, 4, 8. Dokładny plecak `slip_builder.best_slip` (≤ 5 nóg, jedna z meczu, kurs 1,10-2,00), jak `build(..., allow_rest=True, slips=1)`: najpierw warstwy rodzin na plusie, cała pula, gdy one nie dają kuponu (265 z 379 kuponów na wariant z warstw na plusie - ten sam podział dla każdego celu). Odczyty, weta i filtr startu względem „teraz” pominięte (są z chwili budowy). **Zwroty**: pula to tylko nogi WIN/LOSS - noga zwrócona / VOID / nierozliczona jest usunięta z puli przed wyszukiwaniem, jednakowo dla każdego celu (w prawdziwym kuponie zwrot i tak usuwa nogę; tu plecak nie może jej wybrać - lekki podgląd, ten sam dla wszystkich wariantów).
   Na kupon: wszystkie nogi wygrane (tak/nie), średnia (trafienie − 1/kurs) na nogę, przewidywana szansa kuponu wg celu i wg b.
3. Bez jednego dnia (znak), per sport nóg wybranych kuponów, liczba jednostek potrzebnych do rozstrzygnięcia.

## Wyniki

### Noga (pula buildera, 28 188 nóg)

| para | Δ Brier ×1000 [95%] | Δ log-loss ×1000 [95%] | bez każdego dnia |
|---|---|---|---|
| H1 − B | **+1,04 [+0,46; +1,60]** | +2,90 [+1,39; +4,38] | znak stały (+0,92..+1,36) |
| H2 − B | **+0,64 [+0,38; +0,90]** | +1,50 [+0,90; +2,09] | znak stały (+0,41..+0,94) |
| A − B | +0,62 [+0,01; +1,24] | +2,31 [+0,54; +4,12] | znak stały |
| H1 − A | +0,42 [+0,08; +0,74] | +0,59 [−0,33; +1,48] | - |

- **H1 jest gorszy od B i nawet od surowej pewności** w Brier (przedziały wykluczają zero). Izotoniczna z przeszłych dni nie przenosi się: w tenisie H1 − B +3,47 [+1,19; +5,95], w piłce +0,97 [+0,39; +1,57]; hokej −0,27 [−1,96; +1,39]. Przekalibrowana pewność 0,90+ dalej obiecuje o 8 pp za dużo (109 nóg), a 83 nogi zjechały poniżej 0,60 przy trafieniu 0,69 (stara mapa dolnego końca).
- **H2 jest za nisko** (min dwóch obniżeń): trafienie przewyższa p o ~1 pp w każdym przedziale 0,60-0,85, stąd gorszy Brier niż B.
- **Ranking w paśmie** (górna − dolna połowa, pp): 1,30-1,45 A +2,8 [0,2; 5,6], H1 +2,1 [−0,6; 4,9], B −0,8 [−3,5; 1,8], H2 −0,5 [−3,3; 2,2]; 1,45-1,70 A +6,2 [−0,4; 12,4], H1 +4,1, B +3,9, H2 +3,3. H1 zachowuje porządek a tylko częściowo (osobne krzywe sportów i płaskie końce mapy); H2 ma porządek b, bo min wybiera zwykle b.

### Kupon

Kalibracja liczby kuponu (wszystkie cele razem, średnio przewidywana → zrealizowana):

| cel | okna rozłączne (94 kupony) | okna przesuwne (264) |
|---|---|---|
| B | 0,289 → 0,223 | 0,291 → 0,280 |
| A | 0,431 → 0,234 | 0,433 → 0,235 |
| H1 | 0,416 → 0,213 | 0,419 → 0,242 |
| H2 | 0,284 → 0,277 | 0,287 → 0,307 |

**A i H1 obiecują kupon dwa razy za wysoko** (zrealizowana − przewidywana ≈ −0,16..−0,24 przy każdym celu, przedziały wykluczają zero). Mechanizm: plecak wybiera nogi, gdzie cel najbardziej przewyższa cenę - a tam pewność przesadza (por. `price_gap`: nogi z pewnością ponad ceną realizują się mniej więcej po cenie). Kalibracja izotoniczna względem samego a tego nie naprawia - przy wyborze liczy się a − 1/kurs, nie a. Liczba kuponu B i H2 jest bliska realizacji (przedziały obejmują zero poza H2 przy celu 4, gdzie realizacja była wyżej niż obietnica).

Różnice sparowane względem B (ten sam dzień, okno, cel):

| para | okna | inny zestaw nóg | Δ wygrany kupon [95%] | Δ śr. (trafienie − 1/k) na nogę [95%] |
|---|---|---|---|---|
| H1 − B | rozłączne, wszystkie cele (94) | 85% | −0,011 [−0,125; +0,105] | −3,7 [−10,6; +2,4] pp |
| H1 − B | przesuwne, wszystkie (264) | 88% | −0,038 [−0,113; +0,056] | −4,8 [−9,6; +0,1] pp |
| H2 − B | rozłączne, wszystkie (94) | 27% | +0,053 [−0,010; +0,124] | +0,7 [−2,1; +3,3] pp |
| H2 − B | przesuwne, wszystkie (264) | 27% | +0,027 [−0,019; +0,078] | +0,7 [−0,9; +2,5] pp |
| A − B | rozłączne, wszystkie (94) | 84% | +0,011 [−0,086; +0,111] | −1,0 [−6,5; +4,3] pp |
| A − B | przesuwne, wszystkie (264) | 85% | −0,045 [−0,134; +0,066] | −4,2 [−10,3; +0,9] pp |

Per cel (pełne tabele w załączniku): H1 − B przy celu 4: −9,0 pp [−15,8; −2,4] (rozłączne) i −9,1 [−14,5; −3,3] (przesuwne) na nogę - H1 wyraźnie gorszy; A − B przy celu 4 podobnie (−7,6 / −9,4 pp). H2 − B przy celu 4: +0,143 [+0,029; +0,257] wygranych kuponów (rozłączne, 35 par), +0,071 [+0,010; +0,133] (przesuwne) - jedyna komórka „na plus” z przedziałem bez zera, **jedna z 9** (3 pary × 3 cele) w każdym rodzaju okien; przy celu 2 i 8 H2 − B ≈ 0 (przy 8: −0,029 [−0,069; 0,000] przesuwne). Cały dzień: 7 kuponów na cel - bez wniosku; H2 wybiera tam prawie zawsze to samo co B (5% różnych).

**Bez jednego dnia**: H1 − B na nogę ujemne bez każdego dnia (rozłączne −5,3..−1,9 pp, przesuwne −6,2..−2,9 pp) - H1 stale gorszy; ujemny w każdym dniu 10-16..10-19 (najmocniej 10-17: −13,3 pp rozłączne, −15,3 pp przesuwne), dodatni 10-13..10-15. H2 − B w wygranych dodatnie bez każdego dnia (rozłączne +0,024..+0,076, przesuwne +0,009..+0,045), ale na nogę znak nie trzyma w oknach rozłącznych (−0,45..+1,41 pp). Dni 10-17 i 10-18 (71% nóg) nie dominują wyniku H2: per dzień w wygranych −0,07 / +0,25 / +0,09 / +0,15 / 0,00 / −0,07 / +0,07 (rozłączne).

**Per sport** (nogi wybranych kuponów, okna przesuwne, śr. trafienie − 1/k): H1 bierze więcej hokeja (214 nóg vs 122 w B) i ten hokej realizuje −10,9 pp; piłka w H1 −3,2 pp vs +2,6 w B. H2 ≈ B w składzie (piłka 731 / +3,0 pp vs 699 / +2,6). Sporty poza piłką mają po kilkanaście-kilkadziesiąt nóg w kuponach - bez wniosku per sport.

**Ile trzeba**: przy obserwowanej różnicy H2 − B w wygranych (+0,053, SD 0,31 na jednostkę dzień×okno×cel) przedział wykluczy zero przy ~130 jednostkach rozłącznych (~9 dni po 15); dla różnicy +0,7 pp na nogę (SD 0,125) potrzeba ~1 360 jednostek (~90 dni). Wykrycie +5 pp wygranych: ~145 jednostek (~10 dni). Liczba „jednostek” zakłada niezależność celów w jednym oknie - w praktyce dłużej.

## Wniosek

1. **H1 (pewność przekalibrowana izotonicznie) nie powinna zastąpić b.** Na nodze jest gorsza od b (Brier +1,04 ×10⁻³ [+0,46; +1,60]) i od surowej pewności; w kuponach jej liczba obiecuje ~0,42 przy realizacji ~0,21-0,24, a przy celu 4 nogi realizują ok. 9 pp mniej ponad cenę niż przy B (przedział bez zera). Porządek z pewności, przeniesiony do plecaka, wybiera nogi, gdzie pewność najbardziej przewyższa cenę - a tam pewność przesadza. Kalibracja względem samej pewności tego nie usuwa.
2. **H2 (min(a_cal, b)) - nie rozstrzygnięte.** Wybiera inny kupon w 27% przypadków; wygrane kupony +5,3 pp [−1,0; +12,4] (okna rozłączne) i +2,7 pp [−1,9; +7,8] (przesuwne, bootstrap dni), na nogę +0,7 pp [−2,1; +3,3] - wszystkie przedziały obejmują zero. Jedyna komórka z przedziałem bez zera (cel 4) to jedna z dziewięciu - tyle daje przypadek. Na nodze H2 jest gorzej skalibrowana niż b (za nisko). Do rozstrzygnięcia potrzeba ok. 130-150 rozłącznych jednostek (dzień × okno × cel), czyli co najmniej ~10 kolejnych rozliczonych dni, przy założeniu niezależności celów - realnie więcej.
3. **slip_builder nie zmienia celu.** b zostaje: jego liczba kuponu jest najbliżej realizacji (0,29 → 0,22-0,28), a żaden wariant nie daje lepszych kuponów z przedziałem wykluczającym zero. Ewentualny następny pomiar: H2 jako test zarejestrowany od 10-20 (te same reguły, bez zmian), nie przestawienie buildera.

Bez zmian w potoku. Rekomendacja nie jest zmianą - operator decyduje.

## Załącznik: pełny wynik skryptu

## Dane i okna treningowe

- historia 2026-10-05..2026-10-12: 8859 nóg WIN/LOSS; per sport {'tennis': 1683, 'football': 5718, 'hockey': 1212, 'volleyball': 37, 'basketball': 190, 'cs2': 19}; per dzień {'2026-10-05': 189, '2026-10-06': 807, '2026-10-07': 791, '2026-10-08': 700, '2026-10-09': 1462, '2026-10-10': 1709, '2026-10-11': 2483, '2026-10-12': 718}
- 2026-10-13: rekord rodzin plik (dni 2026-10-09..2026-10-12); wyniki {'WIN': 807, 'LOSS': 222, 'REFUND': 16, 'no_measured_chance': 7}
- 2026-10-14: rekord rodzin plik (dni 2026-10-09..2026-10-13); wyniki {'WIN': 926, 'LOSS': 269, 'REFUND': 12, 'UNSETTLED': 5, 'UNGRADEABLE': 1, 'VOID': 8, 'no_measured_chance': 32}
- 2026-10-15: rekord rodzin plik (dni 2026-10-09..2026-10-14); wyniki {'LOSS': 260, 'REFUND': 26, 'WIN': 1154, 'UNSETTLED': 1, 'PENDING:DATA_MISMATCH': 2, 'VOID': 2, 'no_measured_chance': 23}
- 2026-10-16: rekord rodzin plik (dni 2026-10-09..2026-10-15); wyniki {'WIN': 2463, 'LOSS': 613, 'UNSETTLED': 31, 'REFUND': 25, 'VOID': 5}
- 2026-10-17: rekord rodzin plik (dni 2026-10-09..2026-10-16); wyniki {'WIN': 9436, 'LOSS': 2606, 'REFUND': 43, 'UNSETTLED': 35, 'VOID': 6, 'PENDING:DATA_MISMATCH': 1, 'UNGRADEABLE': 1}
- 2026-10-18: rekord rodzin plik (dni 2026-10-09..2026-10-17); wyniki {'WIN': 6777, 'LOSS': 2052, 'UNSETTLED': 40, 'REFUND': 61, 'VOID': 5, 'UNGRADEABLE': 2}
- 2026-10-19: rekord rodzin plik (dni 2026-10-09..2026-10-18); wyniki {'LOSS': 392, 'WIN': 1493, 'REFUND': 5, 'UNSETTLED': 22, 'UNGRADEABLE': 1}
- 2026-10-13: trening 2026-10-05..2026-10-12, 8859 nóg; własna krzywa: football 5718, hockey 1212, tennis 1683; pula (wszystkie sporty, 8859): basketball
- 2026-10-14: trening 2026-10-05..2026-10-13, 9881 nóg; własna krzywa: football 6377, hockey 1336, tennis 1884; pula (wszystkie sporty, 9881): basketball
- 2026-10-15: trening 2026-10-05..2026-10-14, 11044 nóg; własna krzywa: football 7092, hockey 1487, tennis 2170; pula (wszystkie sporty, 11044): basketball
- 2026-10-16: trening 2026-10-05..2026-10-15, 12435 nóg; własna krzywa: football 7960, hockey 1668, tennis 2509; pula (wszystkie sporty, 12435): basketball, cs2, volleyball
- 2026-10-17: trening 2026-10-05..2026-10-16, 15511 nóg; własna krzywa: football 10254, hockey 2042, tennis 2872; pula (wszystkie sporty, 15511): basketball, cs2, volleyball
- 2026-10-18: trening 2026-10-05..2026-10-17, 27553 nóg; własna krzywa: football 21475, hockey 2550, tennis 3100; pula (wszystkie sporty, 27553): basketball, cs2, volleyball
- 2026-10-19: trening 2026-10-05..2026-10-18, 36382 nóg; własna krzywa: football 29736, hockey 2843, tennis 3297; pula (wszystkie sporty, 36382): basketball, cs2, volleyball

## Poziom nogi


**Wszystkie nogi z b** - 29408 nóg, 3572 meczów, trafienie 0.782

| cel | średnia p | Brier [95%] | log-loss [95%] |
|---|---|---|---|
| B: b = measured_chance (obecny) | 0.774 | 0.1677 [0.1638; 0.1713] | 0.5162 [0.5074; 0.5245] |
| A: a = pewność | 0.794 | 0.1683 [0.1641; 0.1723] | 0.5185 [0.5085; 0.5281] |
| H1: a_cal (izotoniczna walk-forward) | 0.784 | 0.1687 [0.1647; 0.1726] | 0.5191 [0.5097; 0.5282] |
| H2: min(a_cal, b) | 0.767 | 0.1683 [0.1646; 0.1718] | 0.5176 [0.5090; 0.5257] |
| c: 1/kurs | 0.824 | 0.1689 [0.1644; 0.1731] | 0.5213 [0.5102; 0.5318] |

| para | Δ Brier ×1000 [95%] | Δ log-loss ×1000 [95%] |
|---|---|---|
| H1 − B | 1.02 [0.48; 1.56] | 2.86 [1.39; 4.30] |
| H2 − B | 0.61 [0.36; 0.86] | 1.39 [0.80; 1.97] |
| A − B | 0.64 [0.02; 1.28] | 2.32 [0.58; 4.16] |
| H1 − A | 0.39 [0.07; 0.71] | 0.54 [-0.34; 1.42] |
| H2 − H1 | -0.42 [-0.94; 0.11] | -1.47 [-2.96; -0.02] |

**Nogi kursu 1,10-2,00 (pula buildera)** - 28188 nóg, 3560 meczów, trafienie 0.779

| cel | średnia p | Brier [95%] | log-loss [95%] |
|---|---|---|---|
| B: b = measured_chance (obecny) | 0.770 | 0.1696 [0.1658; 0.1734] | 0.5208 [0.5120; 0.5297] |
| A: a = pewność | 0.791 | 0.1703 [0.1660; 0.1744] | 0.5231 [0.5130; 0.5329] |
| H1: a_cal (izotoniczna walk-forward) | 0.781 | 0.1707 [0.1666; 0.1747] | 0.5237 [0.5141; 0.5330] |
| H2: min(a_cal, b) | 0.764 | 0.1703 [0.1665; 0.1740] | 0.5223 [0.5137; 0.5309] |
| c: 1/kurs | 0.820 | 0.1708 [0.1663; 0.1752] | 0.5255 [0.5143; 0.5362] |

| para | Δ Brier ×1000 [95%] | Δ log-loss ×1000 [95%] |
|---|---|---|
| H1 − B | 1.04 [0.46; 1.60] | 2.90 [1.39; 4.38] |
| H2 − B | 0.64 [0.38; 0.90] | 1.50 [0.90; 2.09] |
| A − B | 0.62 [0.01; 1.24] | 2.31 [0.54; 4.12] |
| H1 − A | 0.42 [0.08; 0.74] | 0.59 [-0.33; 1.48] |
| H2 − H1 | -0.40 [-0.93; 0.11] | -1.40 [-2.88; 0.02] |

### Bez jednego dnia (pula buildera)

| para | Δ Brier ×1000 ogółem | per dzień | bez dnia: min..max | znak stały |
|---|---|---|---|---|
| H1 − B | +1.04 | +3.2 / +3.3 / -1.5 / +1.9 / +0.6 / +1.3 / +0.6 | +0.92..+1.36 | tak |
| H2 − B | +0.64 | +1.9 / +2.2 / +1.3 / +2.6 / +0.2 / +0.0 / +0.9 | +0.41..+0.94 | tak |
| A − B | +0.62 | +0.1 / +1.5 / -2.4 / -0.7 / +0.6 / +1.7 / +0.2 | +0.16..+0.78 | tak |

### Per sport (pula buildera)

| sport | N | mecze | Brier B | Brier A | Brier H1 | Brier H2 | Δ H1−B ×1000 [95%] | Δ H2−B ×1000 [95%] |
|---|---|---|---|---|---|---|---|---|
| basketball | 78 | 54 | 0.2581 | 0.2717 | 0.2613 | 0.2592 | 3.19 [-43.28; 48.49] | 1.12 [-0.47; 3.26] |
| cs2 | 100 | 32 | 0.1736 | 0.1678 | 0.1699 | 0.1745 | -3.65 [-9.12; 2.10] | 0.91 [-2.65; 4.23] |
| football | 24536 | 2579 | 0.1711 | 0.1719 | 0.1721 | 0.1715 | 0.97 [0.40; 1.55] | 0.42 [0.17; 0.68] |
| hockey | 1628 | 360 | 0.1505 | 0.1504 | 0.1502 | 0.1509 | -0.27 [-2.10; 1.66] | 0.37 [-0.30; 1.02] |
| tennis | 1734 | 467 | 0.1614 | 0.1601 | 0.1649 | 0.1654 | 3.47 [1.24; 5.81] | 4.01 [1.94; 6.11] |
| volleyball | 112 | 68 | 0.1862 | 0.1835 | 0.1861 | 0.1869 | -0.13 [-15.56; 16.15] | 0.63 [-0.23; 1.49] |

### Kalibracja (pula buildera)

**B: b = measured_chance (obecny)**

| przedział p | N | średnia p | trafienie | trafienie − p |
|---|---|---|---|---|
| 0.00-0.60 | 229 | 0.554 | 0.633 | +0.079 |
| 0.60-0.70 | 2659 | 0.666 | 0.696 | +0.030 |
| 0.70-0.75 | 6947 | 0.726 | 0.733 | +0.007 |
| 0.75-0.80 | 8811 | 0.775 | 0.781 | +0.005 |
| 0.80-0.85 | 7422 | 0.823 | 0.835 | +0.012 |
| 0.85-0.90 | 2106 | 0.864 | 0.849 | -0.015 |
| 0.90+ | 14 | 0.901 | 0.929 | +0.027 |

**A: a = pewność**

| przedział p | N | średnia p | trafienie | trafienie − p |
|---|---|---|---|---|
| 0.70-0.75 | 6977 | 0.726 | 0.716 | -0.009 |
| 0.75-0.80 | 9090 | 0.777 | 0.765 | -0.012 |
| 0.80-0.85 | 8034 | 0.823 | 0.819 | -0.004 |
| 0.85-0.90 | 3666 | 0.867 | 0.837 | -0.030 |
| 0.90+ | 421 | 0.914 | 0.846 | -0.068 |

**H1: a_cal (izotoniczna walk-forward)**

| przedział p | N | średnia p | trafienie | trafienie − p |
|---|---|---|---|---|
| 0.00-0.60 | 83 | 0.395 | 0.687 | +0.291 |
| 0.60-0.70 | 1904 | 0.667 | 0.696 | +0.029 |
| 0.70-0.75 | 5857 | 0.727 | 0.730 | +0.004 |
| 0.75-0.80 | 8560 | 0.776 | 0.770 | -0.006 |
| 0.80-0.85 | 9419 | 0.825 | 0.817 | -0.008 |
| 0.85-0.90 | 2256 | 0.859 | 0.851 | -0.008 |
| 0.90+ | 109 | 0.924 | 0.844 | -0.080 |

**H2: min(a_cal, b)**

| przedział p | N | średnia p | trafienie | trafienie − p |
|---|---|---|---|---|
| 0.00-0.60 | 309 | 0.511 | 0.647 | +0.136 |
| 0.60-0.70 | 3695 | 0.664 | 0.699 | +0.035 |
| 0.70-0.75 | 6464 | 0.727 | 0.742 | +0.015 |
| 0.75-0.80 | 8638 | 0.775 | 0.785 | +0.010 |
| 0.80-0.85 | 7822 | 0.824 | 0.833 | +0.009 |
| 0.85-0.90 | 1260 | 0.857 | 0.859 | +0.002 |

### Ranking w paśmie ceny (pula buildera)

| pasmo kursu | N | cel | górna − dolna połowa (trafienie − 1/k) [95%] | AUC |
|---|---|---|---|---|
| 1.10-1.20 | 12269 | B | 1.0 [-0.5; 2.5] pp | 0.539 |
| 1.10-1.20 | 12269 | A | 0.8 [-0.7; 2.3] pp | 0.531 |
| 1.10-1.20 | 12269 | H1 | 1.1 [-0.4; 2.5] pp | 0.530 |
| 1.10-1.20 | 12269 | H2 | 0.4 [-1.1; 1.8] pp | 0.535 |
| 1.20-1.30 | 10366 | B | -0.1 [-1.8; 1.5] pp | 0.522 |
| 1.20-1.30 | 10366 | A | 0.9 [-0.8; 2.5] pp | 0.522 |
| 1.20-1.30 | 10366 | H1 | 0.6 [-1.1; 2.3] pp | 0.519 |
| 1.20-1.30 | 10366 | H2 | -0.8 [-2.5; 0.8] pp | 0.518 |
| 1.30-1.45 | 4548 | B | -0.8 [-3.5; 1.8] pp | 0.512 |
| 1.30-1.45 | 4548 | A | 2.8 [0.2; 5.6] pp | 0.512 |
| 1.30-1.45 | 4548 | H1 | 2.1 [-0.6; 4.9] pp | 0.510 |
| 1.30-1.45 | 4548 | H2 | -0.5 [-3.3; 2.2] pp | 0.514 |
| 1.45-1.70 | 967 | B | 3.9 [-2.4; 10.0] pp | 0.533 |
| 1.45-1.70 | 967 | A | 6.2 [-0.4; 12.4] pp | 0.496 |
| 1.45-1.70 | 967 | H1 | 4.1 [-2.1; 10.1] pp | 0.495 |
| 1.45-1.70 | 967 | H2 | 3.3 [-2.9; 9.4] pp | 0.525 |
| 1.70-2.00 | 38 | - | za mało nóg | |

## Poziom kuponu

Notatki z budowy: 2026-10-13: pula 1,10-2,00 968 nóg (bez godziny startu 0); knapsack 2 s; 2026-10-14: pula 1,10-2,00 1108 nóg (bez godziny startu 0); knapsack 2 s; 2026-10-15: pula 1,10-2,00 1324 nóg (bez godziny startu 0); knapsack 7 s; 2026-10-16: pula 1,10-2,00 2945 nóg (bez godziny startu 0); knapsack 6 s; 2026-10-17: pula 1,10-2,00 11553 nóg (bez godziny startu 0); knapsack 214 s; 2026-10-18: pula 1,10-2,00 8482 nóg (bez godziny startu 0); knapsack 18 s; 2026-10-19: pula 1,10-2,00 1808 nóg (bez godziny startu 0); knapsack 2 s

Kupony z warstw na plusie (supported) vs z całej puli: {('B', False): 114, ('A', False): 114, ('H1', False): 114, ('H2', False): 114, ('B', True): 265, ('A', True): 265, ('H1', True): 265, ('H2', True): 265}

### okna 3 h rozłączne (10/13/16/19/22) - bootstrap jednostek (dzień, okno); okna nie dzielą meczów

Kalibracja liczby kuponu: przewidywana szansa celu vs zrealizowana (wszystkie nogi wygrane).

| cel | kurs | kuponów | śr. nóg | przewidywana | zrealizowana [95%] | zreal. − przew. [95%] | śr. (trafienie − 1/k) na nogę [95%] | przewidywana wg b |
|---|---|---|---|---|---|---|---|---|
| B | 2 | 35 | 2.37 | 0.475 | 0.343 [0.200; 0.514] | -0.132 [-0.278; 0.037] | -4.7 [-13.6; 4.4] pp | 0.475 |
| A | 2 | 35 | 2.57 | 0.595 | 0.400 [0.229; 0.543] | -0.195 [-0.351; -0.045] | -2.1 [-10.6; 5.9] pp | 0.461 |
| H1 | 2 | 35 | 2.51 | 0.583 | 0.343 [0.200; 0.514] | -0.240 [-0.390; -0.077] | -4.0 [-10.5; 3.2] pp | 0.459 |
| H2 | 2 | 35 | 2.46 | 0.467 | 0.343 [0.200; 0.514] | -0.124 [-0.271; 0.040] | -7.3 [-16.9; 1.7] pp | 0.472 |
| B | 4 | 35 | 4.31 | 0.229 | 0.229 [0.086; 0.371] | -0.001 [-0.139; 0.143] | 3.3 [-2.8; 9.4] pp | 0.229 |
| A | 4 | 35 | 4.57 | 0.373 | 0.171 [0.057; 0.314] | -0.202 [-0.323; -0.067] | -4.3 [-10.9; 1.9] pp | 0.214 |
| H1 | 4 | 35 | 4.51 | 0.358 | 0.171 [0.057; 0.314] | -0.186 [-0.307; -0.049] | -5.7 [-13.2; 1.1] pp | 0.216 |
| H2 | 4 | 35 | 4.29 | 0.224 | 0.371 [0.229; 0.543] | 0.148 [0.002; 0.317] | 6.6 [-0.3; 13.2] pp | 0.227 |
| B | 8 | 24 | 5.00 | 0.107 | 0.042 [0.000; 0.125] | -0.065 [-0.110; 0.019] | -1.0 [-7.7; 5.7] pp | 0.107 |
| A | 8 | 24 | 5.00 | 0.278 | 0.083 [0.000; 0.208] | -0.195 [-0.289; -0.069] | 2.2 [-4.3; 8.2] pp | 0.092 |
| H1 | 8 | 24 | 5.00 | 0.257 | 0.083 [0.000; 0.208] | -0.174 [-0.269; -0.049] | -3.5 [-11.0; 3.9] pp | 0.094 |
| H2 | 8 | 24 | 5.00 | 0.106 | 0.042 [0.000; 0.125] | -0.065 [-0.110; 0.020] | 0.7 [-5.9; 6.6] pp | 0.107 |

Różnice sparowane (ten sam dzień, okno, cel). „inne” = odsetek par, w których cel wybrał inny zestaw nóg niż B.

| para | cel | par | inne | Δ zrealizowana (wygrany kupon) [95%] | Δ śr. (trafienie − 1/k) na nogę [95%] | Δ przewidywana wg b |
|---|---|---|---|---|---|---|
| H1 − B | 2 | 35 | 80% | 0.000 [-0.200; 0.172] | 0.7 [-9.4; 10.7] pp | -0.0159 |
| H1 − B | 4 | 35 | 86% | -0.057 [-0.229; 0.086] | -9.0 [-15.8; -2.4] pp | -0.0136 |
| H1 − B | 8 | 24 | 92% | 0.042 [0.000; 0.125] | -2.6 [-11.7; 6.6] pp | -0.0132 |
| H1 − B | wszystkie | 94 | 85% | -0.011 [-0.125; 0.105] | -3.7 [-10.6; 2.4] pp | -0.0144 |
| H2 − B | 2 | 35 | 26% | 0.000 [-0.114; 0.114] | -2.6 [-8.5; 2.3] pp | -0.0025 |
| H2 − B | 4 | 35 | 40% | 0.143 [0.029; 0.257] | 3.3 [-0.2; 6.7] pp | -0.0020 |
| H2 − B | 8 | 24 | 8% | 0.000 [0.000; 0.000] | 1.7 [0.0; 4.2] pp | -0.0005 |
| H2 − B | wszystkie | 94 | 27% | 0.053 [-0.010; 0.124] | 0.7 [-2.1; 3.3] pp | -0.0018 |
| A − B | 2 | 35 | 77% | 0.057 [-0.114; 0.200] | 2.6 [-7.0; 12.5] pp | -0.0139 |
| A − B | 4 | 35 | 86% | -0.057 [-0.229; 0.086] | -7.6 [-14.3; -1.6] pp | -0.0151 |
| A − B | 8 | 24 | 92% | 0.042 [0.000; 0.125] | 3.2 [-4.4; 11.4] pp | -0.0148 |
| A − B | wszystkie | 94 | 84% | 0.011 [-0.086; 0.111] | -1.0 [-6.5; 4.3] pp | -0.0146 |

### okna 3 h przesuwne co godzinę 10:00-23:00 - bootstrap DNI (okna się nakładają)

Kalibracja liczby kuponu: przewidywana szansa celu vs zrealizowana (wszystkie nogi wygrane).

| cel | kurs | kuponów | śr. nóg | przewidywana | zrealizowana [95%] | zreal. − przew. [95%] | śr. (trafienie − 1/k) na nogę [95%] | przewidywana wg b |
|---|---|---|---|---|---|---|---|---|
| B | 2 | 98 | 2.34 | 0.477 | 0.418 [0.316; 0.520] | -0.059 [-0.160; 0.040] | -1.0 [-8.5; 6.2] pp | 0.477 |
| A | 2 | 98 | 2.59 | 0.596 | 0.408 [0.265; 0.551] | -0.187 [-0.346; -0.027] | -2.8 [-10.3; 5.5] pp | 0.464 |
| H1 | 2 | 98 | 2.50 | 0.587 | 0.378 [0.255; 0.520] | -0.209 [-0.356; -0.050] | -3.3 [-11.1; 5.2] pp | 0.461 |
| H2 | 2 | 98 | 2.40 | 0.472 | 0.439 [0.316; 0.582] | -0.033 [-0.154; 0.106] | -1.4 [-9.8; 7.5] pp | 0.476 |
| B | 4 | 98 | 4.27 | 0.231 | 0.276 [0.184; 0.357] | 0.044 [-0.047; 0.127] | 4.5 [-1.6; 9.2] pp | 0.231 |
| A | 4 | 98 | 4.55 | 0.372 | 0.173 [0.061; 0.296] | -0.198 [-0.325; -0.049] | -4.9 [-12.8; 3.5] pp | 0.219 |
| H1 | 4 | 98 | 4.50 | 0.356 | 0.194 [0.092; 0.316] | -0.162 [-0.291; -0.021] | -4.6 [-11.7; 3.2] pp | 0.219 |
| H2 | 4 | 98 | 4.22 | 0.226 | 0.347 [0.255; 0.449] | 0.121 [0.024; 0.225] | 6.4 [1.1; 11.2] pp | 0.229 |
| B | 8 | 68 | 5.00 | 0.109 | 0.088 [0.024; 0.222] | -0.020 [-0.088; 0.117] | -0.7 [-5.2; 5.8] pp | 0.109 |
| A | 8 | 68 | 4.97 | 0.287 | 0.074 [0.012; 0.208] | -0.213 [-0.287; -0.072] | -0.8 [-4.2; 4.1] pp | 0.093 |
| H1 | 8 | 68 | 5.00 | 0.267 | 0.118 [0.043; 0.241] | -0.149 [-0.228; -0.013] | -3.1 [-7.0; 2.8] pp | 0.094 |
| H2 | 8 | 68 | 5.00 | 0.108 | 0.059 [0.000; 0.188] | -0.049 [-0.107; 0.081] | -0.1 [-5.2; 7.1] pp | 0.108 |

Różnice sparowane (ten sam dzień, okno, cel). „inne” = odsetek par, w których cel wybrał inny zestaw nóg niż B.

| para | cel | par | inne | Δ zrealizowana (wygrany kupon) [95%] | Δ śr. (trafienie − 1/k) na nogę [95%] | Δ przewidywana wg b |
|---|---|---|---|---|---|---|
| H1 − B | 2 | 98 | 82% | -0.041 [-0.184; 0.102] | -2.2 [-11.3; 6.3] pp | -0.0160 |
| H1 − B | 4 | 98 | 89% | -0.082 [-0.214; 0.061] | -9.1 [-14.5; -3.3] pp | -0.0125 |
| H1 − B | 8 | 68 | 94% | 0.029 [-0.032; 0.079] | -2.4 [-5.1; 0.3] pp | -0.0142 |
| H1 − B | wszystkie | 264 | 88% | -0.038 [-0.113; 0.056] | -4.8 [-9.6; 0.1] pp | -0.0142 |
| H2 − B | 2 | 98 | 24% | 0.020 [-0.041; 0.082] | -0.4 [-2.9; 2.3] pp | -0.0017 |
| H2 − B | 4 | 98 | 38% | 0.071 [0.010; 0.133] | 1.9 [0.1; 3.8] pp | -0.0017 |
| H2 − B | 8 | 68 | 16% | -0.029 [-0.069; 0.000] | 0.6 [-0.7; 2.3] pp | -0.0006 |
| H2 − B | wszystkie | 264 | 27% | 0.027 [-0.019; 0.078] | 0.7 [-0.9; 2.5] pp | -0.0014 |
| A − B | 2 | 98 | 79% | -0.010 [-0.184; 0.143] | -1.8 [-11.9; 6.5] pp | -0.0131 |
| A − B | 4 | 98 | 86% | -0.102 [-0.265; 0.061] | -9.4 [-17.6; -1.7] pp | -0.0117 |
| A − B | 8 | 68 | 94% | -0.015 [-0.062; 0.038] | -0.1 [-3.7; 2.8] pp | -0.0160 |
| A − B | wszystkie | 264 | 85% | -0.045 [-0.134; 0.066] | -4.2 [-10.3; 0.9] pp | -0.0133 |

### cały dzień - bootstrap dni

Kalibracja liczby kuponu: przewidywana szansa celu vs zrealizowana (wszystkie nogi wygrane).

| cel | kurs | kuponów | śr. nóg | przewidywana | zrealizowana [95%] | zreal. − przew. [95%] | śr. (trafienie − 1/k) na nogę [95%] | przewidywana wg b |
|---|---|---|---|---|---|---|---|---|
| B | 2 | 7 | 2.00 | 0.489 | 0.571 [0.143; 0.857] | 0.083 [-0.346; 0.369] | 0.7 [-27.9; 22.1] pp | 0.489 |
| A | 2 | 7 | 2.71 | 0.688 | 0.571 [0.143; 0.857] | -0.116 [-0.517; 0.190] | 5.5 [-10.0; 20.4] pp | 0.469 |
| H1 | 2 | 7 | 2.71 | 0.706 | 0.286 [0.000; 0.714] | -0.421 [-0.716; -0.019] | -6.1 [-16.8; 7.8] pp | 0.464 |
| H2 | 2 | 7 | 2.00 | 0.489 | 0.571 [0.143; 0.857] | 0.083 [-0.346; 0.369] | 0.7 [-27.9; 22.1] pp | 0.489 |
| B | 4 | 7 | 3.71 | 0.239 | 0.000 [0.000; 0.000] | -0.239 [-0.240; -0.239] | 0.4 [-6.7; 4.1] pp | 0.239 |
| A | 4 | 7 | 4.43 | 0.460 | 0.286 [0.000; 0.714] | -0.174 [-0.484; 0.249] | -1.5 [-16.1; 12.5] pp | 0.235 |
| H1 | 4 | 7 | 4.71 | 0.475 | 0.286 [0.000; 0.714] | -0.189 [-0.490; 0.204] | 1.3 [-12.8; 15.3] pp | 0.233 |
| H2 | 4 | 7 | 3.71 | 0.239 | 0.000 [0.000; 0.000] | -0.239 [-0.240; -0.239] | 0.4 [-6.7; 4.1] pp | 0.239 |
| B | 8 | 7 | 5.00 | 0.117 | 0.143 [0.000; 0.429] | 0.026 [-0.117; 0.312] | 2.6 [-8.8; 16.8] pp | 0.117 |
| A | 8 | 7 | 5.00 | 0.321 | 0.286 [0.000; 0.714] | -0.035 [-0.338; 0.356] | -0.6 [-20.8; 19.6] pp | 0.105 |
| H1 | 8 | 7 | 5.00 | 0.319 | 0.286 [0.000; 0.714] | -0.033 [-0.336; 0.358] | 2.4 [-17.7; 22.4] pp | 0.106 |
| H2 | 8 | 7 | 5.00 | 0.117 | 0.143 [0.000; 0.429] | 0.026 [-0.117; 0.312] | 5.4 [-3.1; 16.8] pp | 0.117 |

Różnice sparowane (ten sam dzień, okno, cel). „inne” = odsetek par, w których cel wybrał inny zestaw nóg niż B.

| para | cel | par | inne | Δ zrealizowana (wygrany kupon) [95%] | Δ śr. (trafienie − 1/k) na nogę [95%] | Δ przewidywana wg b |
|---|---|---|---|---|---|---|
| H1 − B | 2 | 7 | 100% | -0.286 [-0.857; 0.429] | -6.8 [-35.0; 29.6] pp | -0.0249 |
| H1 − B | 4 | 7 | 100% | 0.286 [0.000; 0.714] | 0.9 [-16.5; 19.4] pp | -0.0065 |
| H1 − B | 8 | 7 | 100% | 0.143 [0.000; 0.429] | -0.2 [-8.7; 8.4] pp | -0.0109 |
| H1 − B | wszystkie | 21 | 100% | 0.048 [-0.286; 0.476] | -2.0 [-17.5; 15.0] pp | -0.0141 |
| H2 − B | 2 | 7 | 0% | 0.000 [0.000; 0.000] | 0.0 [0.0; 0.0] pp | +0.0000 |
| H2 − B | 4 | 7 | 0% | 0.000 [0.000; 0.000] | 0.0 [0.0; 0.0] pp | +0.0000 |
| H2 − B | 8 | 7 | 14% | 0.000 [0.000; 0.000] | 2.9 [0.0; 8.6] pp | +0.0000 |
| H2 − B | wszystkie | 21 | 5% | 0.000 [0.000; 0.000] | 1.0 [0.0; 2.9] pp | +0.0000 |
| A − B | 2 | 7 | 100% | 0.000 [-0.571; 0.571] | 4.8 [-25.8; 35.9] pp | -0.0198 |
| A − B | 4 | 7 | 100% | 0.286 [0.000; 0.714] | -1.8 [-19.6; 18.4] pp | -0.0042 |
| A − B | 8 | 7 | 100% | 0.143 [0.000; 0.429] | -3.1 [-12.1; 5.6] pp | -0.0120 |
| A − B | wszystkie | 21 | 100% | 0.143 [-0.190; 0.524] | -0.1 [-15.8; 16.5] pp | -0.0120 |

### Bez jednego dnia (kupony)

| para | okna | miara | ogółem | per dzień | bez dnia: min..max | znak stały |
|---|---|---|---|---|---|---|
| H1 − B | block | Δ wygrany | -0.011 | +0.07 / +0.17 / +0.18 / -0.08 / -0.07 / -0.20 / -0.07 | -0.037..+0.025 | NIE |
| H1 − B | block | Δ (trafienie − 1/k) pp | -3.732 | +5.24 / +5.30 / +3.14 / -12.15 / -13.28 / -3.79 / -7.74 | -5.302..-1.919 | tak |
| H2 − B | block | Δ wygrany | +0.053 | -0.07 / +0.25 / +0.09 / +0.15 / +0.00 / -0.07 / +0.07 | +0.024..+0.076 | tak |
| H2 − B | block | Δ (trafienie − 1/k) pp | +0.666 | -3.07 / +8.31 / -3.13 / +5.68 / +0.00 / -3.24 / +1.08 | -0.452..+1.408 | NIE |
| A − B | block | Δ wygrany | +0.011 | -0.07 / +0.17 / +0.27 / +0.00 / -0.07 / -0.07 / -0.07 | -0.024..+0.025 | NIE |
| A − B | block | Δ (trafienie − 1/k) pp | -1.047 | +3.80 / +4.19 / +6.80 / -4.49 / -5.79 / +0.43 / -9.85 | -2.088..+0.494 | NIE |
| H1 − B | slide | Δ wygrany | -0.038 | -0.03 / +0.09 / +0.19 / -0.06 / -0.19 / -0.12 / -0.08 | -0.069..-0.009 | tak |
| H1 − B | slide | Δ (trafienie − 1/k) pp | -4.838 | +0.48 / +0.58 / +4.99 / -4.74 / -15.27 / -6.84 / -9.90 | -6.193..-2.865 | tak |
| H2 − B | slide | Δ wygrany | +0.027 | -0.07 / +0.15 / +0.03 / +0.08 / +0.00 / +0.00 / +0.03 | +0.009..+0.045 | tak |
| H2 − B | slide | Δ (trafienie − 1/k) pp | +0.719 | -1.67 / +4.56 / -2.40 / +3.54 / +0.48 / -0.74 / +1.62 | +0.151..+1.148 | tak |
| A − B | slide | Δ wygrany | -0.045 | -0.17 / +0.09 / +0.22 / +0.00 / -0.21 / -0.07 / -0.08 | -0.082..-0.014 | tak |
| A − B | slide | Δ (trafienie − 1/k) pp | -4.169 | -0.57 / -0.63 / +5.88 / -0.23 / -19.22 / -2.18 / -8.88 | -5.555..-1.321 | tak |

Dni w kolejności: 2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-17, 2026-10-18, 2026-10-19.

### Nogi wybranych kuponów per sport

| cel | okna | nogi kuponów per sport (n, śr. trafienie − 1/k pp) |
|---|---|---|
| B | block | basketball 1, -62.9; cs2 10, +2.0; football 239, +2.4; hockey 39, -13.8; tennis 65, -2.8 |
| A | block | basketball 10, +2.5; cs2 5, +14.1; football 248, +0.7; hockey 49, -15.1; tennis 56, -3.8; volleyball 2, +43.4 |
| H1 | block | basketball 8, +4.9; cs2 5, +14.1; football 233, -2.8; hockey 66, -17.3; tennis 52, +2.0; volleyball 2, -18.1 |
| H2 | block | basketball 1, -62.9; cs2 10, +2.5; football 256, +2.0; hockey 40, -6.4; tennis 49, +3.9 |
| B | slide | basketball 1, -62.9; cs2 20, -8.0; football 699, +2.6; hockey 122, -7.8; tennis 145, +2.2 |
| A | slide | basketball 27, +2.0; cs2 10, +14.2; football 715, -2.2; hockey 152, -11.6; tennis 128, -3.3; volleyball 6, +41.1 |
| H1 | slide | basketball 22, +6.7; cs2 10, +3.8; football 656, -3.2; hockey 214, -10.9; tennis 118, +1.5; volleyball 6, +0.1 |
| H2 | slide | basketball 1, -62.9; cs2 20, -7.2; football 731, +3.0; hockey 121, -4.1; tennis 116, +3.4 |

### Ile jednostek trzeba (okna rozłączne, wszystkie cele)

| para | miara | Δ zaobserwowana | SD na jednostkę (dzień, okno, cel) | jednostek, by 95% przedział wykluczył 0 przy tej Δ | ≈ dni (15 jednostek / dzień) | jednostek dla Δ = 2 pp (trafienie − 1/k) / 5 pp (wygrany) |
|---|---|---|---|---|---|---|
| H1 − B | wygrany kupon | -0.0106 | 0.475 | 7,661 | 511 | 347 |
| H1 − B | trafienie − 1/k na nogę | -0.0373 | 0.256 | 181 | 12 | 630 |
| H2 − B | wygrany kupon | +0.0532 | 0.306 | 128 | 9 | 144 |
| H2 − B | trafienie − 1/k na nogę | +0.0067 | 0.125 | 1,362 | 91 | 151 |
| A − B | wygrany kupon | +0.0106 | 0.427 | 6,201 | 413 | 281 |
| A − B | trafienie − 1/k na nogę | -0.0105 | 0.242 | 2,058 | 137 | 564 |
