# Incydenty Sofascore dla sportów mierzonych - rynki kolejności (2026-10-14)

Pomiar (tylko odczyt, nic w potoku tego nie czyta). Pytanie: czy rynki
Superbetu, których nie da się rozliczyć z wyników per okres, warto podłączyć
przez `/event/{id}/incidents`:

- hokej `hk.goal_order` - "1. gol" i "1. tercja - 1. gol" (kto strzeli
  pierwszego gola, albo brak gola; 28 wystąpień w próbie oferty 2026-10-14),
- koszykówka `bb.score_order` - "Wyścig do X punktów (z dogrywką)" (5 wystąpień),
- siatkówka - w próbie oferty 2026-10-14 (`market_coverage_sports.md`) **nie
  ma** rodziny wymagającej incydentów (exact_sets_derived, sets_count,
  set_points_handicap, set_and_match liczy się z wyników setów). Siatkówki nie
  mierzono.

## Co zrobiono

1. `scripts/sofa/backfill_event_extra.py --kind incidents --sport
   hockey|basketball|volleyball`: cele to mecze danego sportu, które indeks
   `sofa_listed_event` (slug `ice-hockey` / `basketball` / `volleyball`) trzyma
   jako `finished` - historia modelu wyniku. Piłki nożnej nigdy (jej incydenty
   są w `sofa_event_stats.incidents_json`). Zapis do `sofa_event_extra`
   (kind `incidents`); pusta odpowiedź = `{}`; zawody, które dały
   `MAX_BARREN_MISSES` pustych odpowiedzi z rzędu, są pomijane.
   Testy: `tests/sofa/test_event_extra.py`.
2. Pobieranie (most, 2026-10-14 od 15:05Z): cele w oknie 120 dni - hokej 3 091,
   koszykówka 3 880, siatkówka 2 723.
   - hokej: próba 20 (OK), potem porcja `--max-minutes 7`: **odmowa po 120
     meczach** (breaker otwarty, 7 błędów, exit 2) o 15:08Z. Zgodnie z regułą
     pobieranie przerwano - bez ponowienia.
   - koszykówka: tylko próba 10 meczów (przed porcją hokeja), siatkówka: 0.
   - **W cache: hokej 140, koszykówka 10, siatkówka 0.** Reszta czeka na
     kolejne porcje po ostygnięciu mostu (wznawialne - mecz z wierszem nie jest
     pytany drugi raz).
3. `scripts/sofa/measure_sport_incidents.py` - walk-forward na historii
   (`score_model.load_events` -> `sport_confidence.parse_history`), jak
   `walk_forward_rows`: model z meczów ściśle przed pierwszym ocenianym,
   przebudowa co `REBUILD_DAYS` (30), księga ratingów aktualizowana po każdej
   godzinie startu; reguły dnia (ścisła stawka ligi, świeżość koszykówki).
   Testy: `tests/sofa/test_measure_sport_incidents.py`.

## Model

- **Hokej "1. gol"**: oczekiwane gole per tercja z `ScoreModel.expected`, obie
  strony jako niezależne procesy Poissona: P(brak) = exp(-suma),
  P(gospodarz pierwszy) = suma_k P(brak przed k) (1 - exp(-tot_k)) eh_k/tot_k.
  Zakres: czas regulaminowy (założenie, **nie sprawdzone** w regulaminie
  Superbetu). "1. tercja - 1. gol" - to samo dla tercji 1.
- **Koszykówka, wyścig do X** (X = 10, 15, 20, 25, 30 - jakie X Superbet
  wystawia, **nie odczytano**): z symulacji modelu wyniku udział gospodarza w
  punktach regulaminowych q na losowanie; wyścig to ciąg akcji punktowych -
  gospodarz z p = q, wartość 1/2/3 z bieżących udziałów akcji meczów ocenionych
  wcześniej (0,34 / 0,50 / 0,17 na 9 meczach).
- Baza: bieżący udział klas meczów ocenionych wcześniej (prior Laplace'a).

## Fakty o danych (do zapamiętania)

- Hokej: **52% meczów (72 / 140) ma w incydentach tylko tercje, bez goli**
  (niższe ligi) - `no_score_detail`. 1 mecz z liczbą goli niezgodną z wynikiem.
- Hokej: zegar incydentów bywa odwrócony - 16836848 ma w 1. tercji gole na 4',
  11', 19' z wynikami 3-0, 2-0, 1-0; numery `id` idą z wynikiem. Kolejność
  czytamy więc z **bieżącego wyniku**, nigdy z `time`. Każdy gol jest
  sprawdzany: jego `isHome` musi być stroną, której wynik wzrósł o 1.
- Koszykówka: bieżący wynik spójny z czasem (16747278); 2 z 9 meczów bez akcji
  punktowych, 1 z nieciągłym wynikiem (skok > 3 pkt).

## Wyniki

### Hokej (66 meczów ocenionych, okno incydentów to ostatnie dni)

| rynek | gry | log-loss model | baza | różnica [95% bootstrap meczów] | wiersze stron >= 0,70 |
|---|---|---|---|---|---|
| 1. gol (regulamin) | 66 | 0,6579 | 0,7746 | -0,1167 [-0,1958, -0,0447] | 1 / 132 |
| 1. tercja - 1. gol | 66 | 1,0079 | 1,1011 | -0,0932 [-0,1838, -0,0029] | 1 / 132 |

Uwaga: baza startuje od zera (prior 1/3 na "brak gola", który zrealizował się
0 razy w 66), więc jej rozgrzewka zawyża przewagę modelu. Wobec stałej
równej zrealizowanym udziałom (w próbie - optymistyczne dla bazy: 0,693 i
1,049) model jest lepszy o ok. -0,035 i -0,041 - bez przedziału, na 66
meczach nic z tego nie wynika.

Kalibracja (wiersze stron, 132): koszyk < 0,60: śr. p 0,480, zrealizowane
0,466 (Wilson dolna 0,379); 0,60-0,70: 13 wierszy, p 0,631, zrealizowane
0,769 (Wilson 0,497); >= 0,70: 1 wiersz.

### Koszykówka (6 meczów ocenionych)

Log-loss model - baza dla X = 10 / 15 / 20 / 25 / 30: -0,052 / -0,140 /
+0,030 / -0,120 / -0,029, każdy przedział szeroki na +-0,2-0,3. Sześć meczów
to nie pomiar. 0 wierszy >= 0,70.

### Ile wierszy mogłoby w ogóle drukować (model nie potrzebuje incydentów)

Rozkład p modelu na **każdym** ocenianym meczu ostatnich 120 dni historii:

| rynek | wiersze stron | >= 0,70 | udział |
|---|---|---|---|
| hokej 1. gol | 4 948 | 90 | 1,8% |
| hokej 1. tercja - 1. gol | 4 948 | 18 | 0,4% |
| koszykówka wyścig do 10 | 5 322 | 50 | 0,9% |
| wyścig do 15 | 5 322 | 105 | 2,0% |
| wyścig do 20 | 5 322 | 154 | 2,9% |
| wyścig do 25 | 5 322 | 193 | 3,6% |
| wyścig do 30 | 5 322 | 237 | 4,5% |

To strukturalne: P(pierwszy gol) ~ udział strony w tempie strzelania, a 0,70
wymaga stosunku tempa 2,3 : 1; wyścig do małego X jest bliski losowania nawet
przy wyraźnym faworycie. Ok. 0,7 wiersza hokeja dziennie przekroczyłoby
0,70 przed krzywą kalibracji - a krzywa (MIN_BUCKET 200 na koszyk) wymaga
setek takich wierszy rozliczonych z incydentów.

## Werdykt: podłączenie teraz się nie opłaca

1. Na kupon (pewność >= 0,70) trafiłoby 0,4-4,5% wierszy stron, przed
   kalibracją; kalibrację da się dopasować dopiero na dużej historii
   incydentów, a w hokeju połowa meczów nie ma goli w incydentach.
2. Dyskryminacja na obecnych danych (66 / 6 meczów) jest niemierzalna -
   różnica wobec bazy w hokeju jest głównie rozgrzewką bazy.
3. Do sprawdzenia przed jakąkolwiek decyzją: (a) zakres "1. gol" w regulaminie
   Superbetu (regulamin czy z dogrywką; co przy 0-0 i karnych), (b) jakie X
   Superbet wystawia w "Wyścig do X punktów" i co, gdy nikt nie dojdzie do X,
   (c) dokończyć pobieranie (hokej ~2 950, koszykówka ~3 870 meczów zostało)
   i powtórzyć pomiar: `measure_sport_incidents.py --sport hockey|basketball`.
   Jeśli po tym `1. gol` wyjdzie z przedziałem poniżej zera wobec bazy
   znającej udział klas - podłączenie jako rynek dwustronny przez krzywą z
   historii (jak inne klucze), ale skala (<2% wierszy) każe najpierw zrobić
   rynki o większym pokryciu.

## Niesprawdzone

- Przyczyna odmowy o 15:08Z (403 / 429 / 5xx - nie zalogowano typu; breaker
  `SOFA_BREAKER_*` otworzył się po 7 błędach).
- Zakres rozliczenia obu rynków w Superbecie (patrz wyżej).
- Siatkówka: nie pobrano ani jednego meczu; brak rynku, który by tego wymagał.
- Model wyścigu traktuje akcje jako niezależne (wolne rzuty przychodzą
  parami, posiadania się przeplatają) - kalibracja pokaże, czy to przeszkadza.
