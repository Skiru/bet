# Przewaga nad ceną i CLV - gdzie nasza pewność bije Superbet? (2026-11-20)

Zlecenie operatora 11-20: znaleźć kieszeń (sport × rynek × liga × pasmo ×
czas do startu), w której pewność wydrukowanej nogi bije cenę Superbetu bez
marży poza próbą, i sprawdzić to kursem zamknięcia (CLV). Tylko pomiar - nic
nie zmienione w tym, co drukuje kupon.

**W skrócie: kieszeni z przewagą nie ma.** Z 596 komórek dev z n ≥ 300
dwadzieścia wyszło nad zero (losowo spodziewane ~15 z 596 przy 2,5% w
jedną stronę; 108 wyszło istotnie pod zero). Żadna z tych 20 nie miała 300
nóg w hold-oucie, więc reguła nie miała czego zatwierdzić. Skan wszystkich
110 komórek hold-outu z n ≥ 300: zero odkryć po BH. **CLV jest ujemne w
każdej komórce** (≈ −3 do −4%, czyli marża): kurs między wydrukiem a
zamknięciem praktycznie stoi (średnio +0,03% w piłce). Nogi, w których
uważamy się za lepszych od ceny, mają CLV *gorsze*, a nie lepsze
(korelacja (pewność − cena bez marży) z CLV ujemna w każdym sporcie).
Jedyny trop: **siatkówka** (+2,7 pp nad ceną bez marży w obu splitach,
ROI ≈ 0 przed podatkiem) - poniżej progu i najpewniej artefakt de-vigu, nie
przewaga.

## 1. Protokół i dane

- Reguły zamrożone przed uruchomieniem: `przewaga_nad_cena_2026-11-20/PROTOCOL.md`
  (sha256 `264e4521…`, commit f28cd71c; skrypt odmawia przy innym sha).
  Skrypt: `scripts/sofa/measure_price_edge.py` (tylko odczyt plików dni,
  baza nieużywana), test `tests/sofa/test_measure_price_edge.py`. Wyjścia:
  `przewaga_nad_cena_2026-11-20/summary.json`, `cells_edge.csv`,
  `cells_clv.csv`, `cells_clv_over.csv` (komórki z n ≥ 300 w którymś splicie).
- Nogi: każda wydrukowana pojedyncza, rozliczona przez księgę
  (`13_results.json`, wygrana / przegrana; zwroty poza pomiarem), kurs =
  kurs rozliczenia. **Dev 10-13..11-09 (28 dni), hold-out 11-10..11-19
  (10 dni).** Epoki modelu łączone w obu splitach - pytanie dotyczy liczby
  obok ceny, nie wersji modelu.
- Krawędź = wygrana − cena bez marży przy kursie wziętym: piłka / tenis
  `market_p` (de-vig power po drabince) przeniesione na kurs wzięty; sporty
  - de-vig power pary odtworzonej z `overround` (tylko linie dwustronne).
  Noga bez ceny bez marży (piłkarska jednostronna, sport wielostronny) -
  względem 1/kurs (`raw`, surowiej).
- CLV = kurs wzięty × p zamknięcia bez marży − 1; zamknięcie 3-30 min przed
  startem (`closing.jsonl` piłka / tenis, `settled.json` sportów).
- Reguła: kandydat na dev (n ≥ 300, dolna granica 95% CI > 0) → hold-out
  (n ≥ 300, CI 1 − 0,05/k > 0, Bonferroni). Bootstrap po meczach, 2 000
  prób (20 000 dla kandydatów). Skan BH q = 0,10 opisowo.

**Ile komórek:** 11 rodzin (sport, sport×rynek|kierunek, sport×liga,
sport×pasmo, sport×czas, i ich krzyżówki, plus „pewność > cena bez
marży”), 15 435 komórek krawędzi (596 z n ≥ 300 na dev, 110 na hold-oucie),
11 100 komórek CLV (469 / 79), 7 713 komórek CLV nóg „ponad ceną” (171 /
14).

**Sprawdzenie liczb:** niezależny skrypt (subagent, własny kod z tej samej
specyfikacji, bez dostępu do mojego) - piłka fair hold-out n 10 409, 1 625
meczów, trafienie 0,77981, cena bez marży 0,79611, krawędź −0,01630; dev
81 635 / −0,00935; tenis hold-out 4 408 / −0,01450; pasmo 0..0,03 92 /
−0,06445; CLV piłki hold-out 9 537 / −0,03900, tenisa dev 8 728 / −0,03573;
piłka raw hold-out 5 677 / −0,06295. Zgodne z wynikiem skryptu co do 5.
miejsca (CLV piłki dev: 67 917 nóg w obu, z czego 67 910 w komórce „fair”
i 7 jednostronnych z parą zamknięcia; średnia −0,0371).

## 2. Krawędź po sportach (nogi z ceną bez marży)

pp = punkty procentowe trafienia ponad cenę bez marży; ROI przed podatkiem.

| sport | dev n (mecze) | dev krawędź [95%] | dev ROI | hold n (mecze) | hold krawędź [95%] | hold ROI |
|---|---|---|---|---|---|---|
| piłka | 81 635 (9 560) | −0,9 [−1,3; −0,6] | −4,8% | 10 409 (1 625) | −1,6 [−2,7; −0,6] | −5,9% |
| tenis | 9 427 (2 151) | −1,8 [−2,9; −0,7] | −5,7% | 4 408 (834) | −1,5 [−3,0; +0,2] | −5,5% |
| hokej | 5 539 (1 082) | −0,2 [−1,3; +1,0] | −3,5% | 3 100 (570) | −0,8 [−2,6; +0,9] | −4,2% |
| siatkówka | 1 007 (420) | +2,3 [−0,6; +5,2] | −0,5% | 831 (305) | +3,1 [+0,1; +6,3] | +0,1% |
| CS2 | 637 (133) | +1,2 [−4,0; +6,0] | −2,0% | 275 (46) | +0,8 | −3,0% |
| piłka jednostronna (vs 1/kurs) | 35 945 (8 359) | −5,7 [−6,2; −5,2] | −6,8% | 5 677 (1 454) | −6,3 [−7,5; −5,0] | −7,4% |
| hokej wielostronny (vs 1/kurs) | 668 (508) | −7,5 [−10,9; −4,1] | −9,3% | 495 (414) | −7,4 [−11,3; −3,7] | −8,6% |

Koszykówka - za mało nóg na żadną komórkę (n < 300).

Po pasmach (pewność − 1/kurs), piłka: każde pasmo z n ≥ 300 jest pod ceną
bez marży albo przy niej (dev −1,4 / −1,2 / −0,1 / +0,7 / −1,2 / +1,7 pp od
najniższego); pasma ≥ 0 to na hold-oucie ledwie 108 nóg (kupon drukuje
prawie wyłącznie nogi poniżej ceny, x ≥ 0,90). Tenis i hokej - to samo.
Po czasie od wydruku do startu: nic dodatniego w żadnym sporcie (piłka
dev od −2,6 pp przy < 1 h do +0,1 pp przy ≥ 12 h, hold-out wszystko ujemne).

## 3. Kandydaci z dev i dlaczego hold-out ich nie ocenił

20 kandydatów (CI na dev nad zerem), wszystkie piłka:

| komórka | dev n (mecze) | dev krawędź [95%] | hold n | hold krawędź |
|---|---|---|---|---|
| rożne razem OVER | 3 139 (1 823) | +1,9 [+0,1; +3,5] | 229 | +0,6 |
| rożne razem OVER, pewność > cena | 1 904 | +2,5 [+0,1; +4,8] | 109 | +0,1 |
| karne razem UNDER | 1 069 (1 069) | +5,2 [+2,8; +7,6] | 111 | −4,1 |
| karne razem UNDER, 6-12 h | 562 | +5,1 [+1,7; +8,4] | 27 | −5,4 |
| karne razem UNDER, pewność > cena | 767 | +5,9 [+2,9; +8,8] | 83 | −1,3 |
| karne drużyny UNDER | 352 | +4,4 [+0,7; +7,9] | 25 | −17,5 |
| czerwone kartki UNDER, 6-12 h | 580 | +3,4 [+0,4; +6,2] | 36 | −21,0 |
| strzały razem OVER, 6-12 h | 351 (192) | +8,3 [+2,7; +13,5] | 7 | +8,7 |
| 2. Bundesliga (+ pewność > cena) | 964 / 340 (36) | +5,0 / +10,4 | 0 | - |
| Süper Lig (+ pewność > cena) | 1 145 / 379 (34) | +3,4 / +7,1 | 0 | - |
| Liga Portugal (+ pasmo < −0,05, + nie > cena) | 743 / 325 / 533 (27) | +3,4 / +5,3 / +4,2 | 0 | - |
| Serie B, pewność > cena | 545 (50) | +4,3 | 0 | - |
| OTP Bank Liga | 520 (24) | +4,7 | 0 | - |
| Ekstraklasa, pewność > cena | 357 (36) | +5,7 | 0 | - |
| LaLiga, pasmo < −0,05 | 724 (41) | +3,5 | 0 | - |
| Liga Mistrzów, pewność ≤ cena | 861 (52) | +3,1 | 0 | - |

- **Hold-out (11-10..11-19) wypadł w przerwie reprezentacyjnej:** czołowe
  ligi nie grały (w hold-oucie najwięcej nóg mają LaLiga 2, Brasileirão,
  League Two), więc ligowi kandydaci mają 0 nóg. Reguła nie mogła ich
  zatwierdzić. To brak testu, nie obalenie.
- Tam, gdzie hold-out coś miał (rożne, karne, czerwone), kierunek się nie
  utrzymał albo spadł do zera.
- 20 dodatnich z 596 to tyle, ile daje przypadek (~15). Komórki ligowe
  stoją na 24-52 meczach (wiele nóg jednego meczu to nie są niezależne
  próby). Karne / czerwone UNDER to grupa `league_rate` - ta sama co L1 z
  31.10 (`kupon_od_nowa_2026-10-31.md`), wtedy też bez potwierdzenia.

## 4. Skan hold-outu (110 komórek z n ≥ 300, BH q = 0,10): 0 odkryć

Najniższe p jednostronne: Brasileirão Série A +6,2 pp [+0,9; +11,5]
(343 nogi, **8 meczów**, dev −1,0) p = 0,012; siatkówka razem +3,1 p =
0,022; siatkówka „pewność > cena” +3,8 [−0,7; +8,1] p = 0,042. Próg BH
dla najlepszej komórki to 0,10/110 = 0,0009 - żadna go nie przechodzi.

## 5. CLV - czy rynek idzie w naszą stronę? Nie.

| sport | nogi z CLV (dev / hold) | CLV dev | CLV hold | kurs wzięty / zamknięcia (log, średnio) | wyższy / niższy niż zamknięcie |
|---|---|---|---|---|---|
| piłka | 67 910 / 9 537 | −3,71% | −3,90% | +0,03% | 28% / 26% |
| tenis | 8 728 / 3 931 | −3,57% | −3,65% | +0,05% | 19% / 16% |
| hokej | 4 563 / 2 434 | −3,19% | −3,23% | +0,05% | 22% / 20% |
| siatkówka | 668 / 737 | −3,50% | −3,75% | +0,31% | 30% / 22% |
| CS2 | 309 / 146 | −3,92% | −3,35% | +0,00% | 25% / 14% |
| koszykówka | (415 nóg łącznie) | - | - | +0,40% | 49% / 36% |

- CLV ≈ −marża: wzięty kurs prawie zawsze równa się kursowi zamknięcia,
  więc „wartość przy cenie zamknięcia” to cena minus marża. Żadna z 469
  komórek dev z n ≥ 300 nie ma CLV nad zerem; najlepsze (hokej NHL, total
  tercji OVER) −2,6 do −3,0%.
- Ruch ceny jest minimalny: w piłce 28% nóg wzięliśmy po kursie wyższym od
  zamknięcia, 26% po niższym, średnio +0,03%. W siatkówce i koszykówce
  łapiemy trochę wyższe kursy (+0,3 / +0,4%) - za mało, żeby odrobić marżę.

**Pytanie 3 - nogi z pewnością > ceną bez marży:** CLV jest gorsze niż nóg
pozostałych w każdym sporcie (piłka −4,0 vs −3,6%, tenis −4,0 vs −3,4%,
hokej −3,5 vs −3,1%, siatkówka −3,7 vs −3,5%, koszykówka −5,7 vs −2,6%, CS2
−4,4 vs −3,3%). Korelacja (pewność − cena bez marży) z CLV: piłka −0,12,
tenis −0,21, hokej −0,11, siatkówka −0,16, CS2 −0,23, koszykówka −0,37.
Im mocniej „nie zgadzamy się” z ceną, tym mniej rynek idzie za nami - jak w
`price_gap` (−10 pp). Krawędź tych nóg: piłka +0,1 pp dev / 0,0 hold-out
(trafiają dokładnie po cenie bez marży), nogi „nie” −1,5 / −2,1.

## 6. Siatkówka - jedyny trop, nie przewaga

- +2,3 pp dev, +3,1 pp hold-out nad ceną bez marży; ROI −0,5% / +0,1%
  przed podatkiem, czyli trafienie ≈ 1/kurs. Po podatku 12% noga traci
  ok. −12%.
- Najpewniej artefakt de-vigu: krawędź powstaje dlatego, że de-vig power
  przypisuje faworytowi mniej marży, niż Superbet w siatkówce faktycznie na
  nim trzyma. „Bijemy cenę bez marży” znaczy tu „trafiamy po kursie
  surowym”. Cena bez marży sportów jest odtworzona z `overround` (para
  dwustronna), a nie odczytana z drabinki - to dodatkowa niepewność.
- Model siatkówki zmienił się w środku okna (`VB_POINT_MODEL` od 11-06
  17:30Z) - dev to w większości stary model.
- Na 11-08 brak 189 nóg siatkówki (skasowany `11_coupon.json`).

## 7. Czego brakuje w danych

- **Kurs otwarcia:** piłka / tenis - brak. `04_offer.json` jest nadpisywany
  przy każdej przebudowie, więc najwcześniejsza znana cena to pierwszy
  wydruk (`printed/<ts>.json`). Sporty - pierwsza migawka pętli SHADOW /
  CS2 (np. hokej NHL od ~17 h przed startem), czyli najwcześniejszy kurs,
  jaki zobaczyliśmy, nie otwarcie Superbetu. Ruch od pierwszej migawki do
  wydruku w sportach ≈ 0 (hokej +0,01%, siatkówka +0,06%, CS2 −0,4%).
  Pełnej ścieżki otwarcie → wydruk → zamknięcie dla piłki nie da się
  odtworzyć.
- **Zamknięcie:** `closing.jsonl` od 10-01 dla piłki i tenisa (wszystkie
  dni okna; 11-07 i 11-13 mają mało rekordów); nogi jednostronne nie mają
  drugiej strony (`partner_close` = null), więc bez CLV - 31% rekordów.
  Nogi z CLV: piłka 58-59%, tenis 89-92%, hokej 77-80%, siatkówka
  65-86%, koszykówka 71-76%, CS2 47-51% (zamknięcie sportów z
  `settled.json`; brak = linia nie oceniona w oknie 3-30 min).
- **Pliki skasowane 11-19:** 9 dni bez `11_coupon.json` (10-17, 10-18,
  10-24, 10-25, 10-31, 11-01, 11-07, 11-08, 11-14) - piłka / tenis z
  `08_confidence.json` (kompletne), sporty tylko z ostatniej przebudowy
  (np. 11-08: 189 nóg siatkówki, 66 hokeja bez pól). Na tych dniach brak też
  `printed/` - czas do startu tylko z `printed_at_utc`.
- **Jedna linia ceny:** tylko Superbet. Literatura mierzy przewagę ostrą
  linią zamknięcia (Pinnacle); zamknięcie Superbetu to cena miękkiej
  bukmacherki, która prawie się nie rusza - CLV ≈ 0 ruchu jest tu słabym
  dowodem w obie strony.

## 8. Wada znaleziona przy okazji (narzędzie, nie kupon)

`bet.sofa.clv.group_close` normuje każdą grupę > 2 stron do sumy 1. Dla
podwójnej szansy (1X / X2 / 12; hokej `double_chance`,
`period_double_chance`, ~2,5 tys. linii w 10 dniach) prawdziwa suma to 2,
więc p zamknięcia wychodzi ~1/3 i CLV ~−40%. Ta ścieżka jest w
`graded_close_rows` / `audit_clv.py` dla nóg sportów: CLV hokejowych nóg DC
w `audit_clv` jest błędne. Ten raport pomija nogi „raw” hokeja w CLV.
Poprawka (de-vig DC z 1X2 albo suma 2) czeka na decyzję - nie wpływa na
wydruk.

## 9. Wniosek

Nasza pewność jest skalibrowana do trafienia, ale nie zawiera informacji,
której nie ma w cenie Superbetu: w żadnym sporcie, rynku, lidze, paśmie ani
czasie wydruku nie bije ceny bez marży poza próbą, a rynek nie idzie w
naszą stronę do zamknięcia (CLV = −marża; nogi „ponad ceną” mają CLV
gorsze). To samo co 31.10 (`kupon_od_nowa`), 16.11 (progi, flagi) i 19.11
(literatura), teraz zmierzone także kursem zamknięcia.

Co dalej, jeśli operator zechce (bez przełącznika, nic do wdrożenia):

1. Ligowych kandydatów z dev (2. Bundesliga, Süper Lig, Liga Portugal…)
   hold-out nie ocenił (przerwa reprezentacyjna). Można zarejestrować test
   naprzód na danych od 11-21 z tymi samymi komórkami i progiem n ≥ 300.
   Przy ~35 nogach na kolejkę ligi to kilka miesięcy; spodziewany wynik:
   szum.
2. Siatkówka: test naprzód krawędzi przy cenie surowej (trafienie − 1/kurs >
   0), nie przy cenie bez marży, od 11-21, n ≥ 300 nóg; nawet zdany nie
   pokrywa podatku 12%.
3. Bez innej linii ceny (zakaz źródeł spoza Sofascore / Superbet) mocniejszej
   miary CLV nie będzie.
