# Próbki goli dla towarzyskich meczów reprezentacji (2026-10-13)

Status: **pre-rejestracja zapisana przed pomiarem** (sekcje 1-6). Wyniki i werdykt
w sekcjach 7-8 dopisane po uruchomieniu `scripts/sofa/measure_national_friendly_samples.py`
(2026-10-13 wieczorem, `data/sofa.db` tylko do odczytu).
Pomiar tylko do odczytu; żadnego przełącznika, żadnej zmiany w pipeline.

## 1. Skąd pytanie

Analityk piłki (noc 2026-10-13): dla meczu towarzyskiego reprezentacji
`samples.pick_same_competition` (`src/bet/sofa/samples.py` ok. 1449-1462,
`comparability.pick_same_competition`) traktuje rozgrywki towarzyskie jak ligę,
więc próbka `goals_total` / `goals_for` to same mecze towarzyskie. Argentyna
(kobiety, rozgrywki 852 "International Friendly Games Women") - próbka sięgnęła
822 dni wstecz i pominęła mecze Copa América 2025 i 2026. To podejrzenie, nie
pomiar.

Stan reguł dziś (z kodu, nie z pomiaru):

- 852 (kobiety) jest w `allowed` w `config/sofa_friendly_competitions.json`,
  więc jego mecze są w puli próbki i reguła "te same rozgrywki" wybiera dla
  meczu 852 najnowsze 10 meczów 852 (gdy jest ich >= 5).
- 851 (mężczyźni) jest w `excluded` od 2026-10-04: mecze 851 w ogóle nie wchodzą
  do puli, więc `pick_same_competition` nic nie znajduje i mecz towarzyski
  mężczyzn dostaje zwykłą próbkę - najnowsze 10 meczów o stawkę. Dla mężczyzn
  wariant A jest więc **kontrfaktyczny** (tak by było, gdyby 851 wrócił do puli),
  a regułą na żywo jest wariant D poniżej.

## 2. Hipoteza

H1: dla meczu towarzyskiego reprezentacji (kobiety 852, mężczyźni 851) środek
goli zbudowany z próbki zawierającej mecze o stawkę (B lub C) przewiduje liczbę
goli lepiej niż próbka z samych meczów towarzyskich (A).
H0: brak różnicy albo A lepsze.

## 3. Populacja i dane

- `data/sofa.db` (tylko odczyt, `mode=ro`), tabela `sofa_listed_event`, piłka,
  mecze zakończone, w których obie strony mają `national: true`.
- Mecze docelowe: rozgrywki 851 i 852, zakończone, z wynikiem regulaminowym
  (`metrics.regulation_score`), od 2015-01-01 do 2026-10-12. Kobiety i mężczyźni
  raportowani osobno, nigdy nie sumowani.
- Historia strony: wszystkie jej zakończone mecze reprezentacji przed
  rozpoczęciem meczu docelowego (ściśle wcześniej), bez rozgrywek z listy
  `excluded` (towarzyskie młodzieżowe itp.) - z wyjątkiem 851 / 852, które są
  przedmiotem pomiaru. Pula patrzy najwyżej `INDEXED_HISTORY_LIMIT` (200)
  meczów wstecz, jak SAMPLES.
- Walk-forward: każda próbka jest budowana wyłącznie z meczów przed meczem
  docelowym; nie ma tu żadnego dopasowywanego parametru wariantu.

## 4. Warianty (na stronę; n = 10, minimum 5)

- **A** (dziś dla 852): najnowsze 10 meczów REGULAR rozgrywek meczu docelowego
  (`comparability.pick_same_competition`), gdy jest ich >= 5; inaczej B. Mecz
  docelowy typu KNOCKOUT nie korzysta z reguły (jak w SAMPLES).
- **B**: najnowsze 10 meczów reprezentacji z puli - towarzyskie i o stawkę razem,
  bez limitu wieku (reguła `NATIONAL_SAMPLE_AGE`: liczy się liczba, nie wiek).
- **C**: wszystkie mecze z puli (towarzyskie + o stawkę) w tym samym oknie
  czasowym co próbka A (od najstarszego meczu A do meczu docelowego); gdy A
  spadło do B - B.
- **D** (dodatkowy, opisowy): najnowsze 10 meczów o stawkę (bez 851 / 852);
  poniżej 5 - B. To reguła na żywo dla mężczyzn.

Przypadek wchodzi do pomiaru, gdy B ma >= 5 meczów po każdej stronie (dla
`goals_for` - po swojej stronie). Ten sam zbiór przypadków dla wszystkich
wariantów (porównanie parami).

## 5. Metryka

Środek jak SHEET bez ratingu (jak `calibrate_from_cache.shrunk_centre`):
średnia próbki ściągnięta do bazowej ligi (`config/sofa_league_baselines.json`
dla rozgrywek meczu docelowego, inaczej `global`) z wagą n / (n + K), K = 15
(`K_CENTRE.by_sport.football`). `goals_total`: próbka to zsumowane gole
meczów obu stron, mecz wspólny raz (`pooled_total_sample`). `goals_for`: próbka
strony.

- **Główna**: log-loss NB przy rzeczywistej liczbie goli, wariancja mu + alpha
  mu^2, alpha z `config/sofa_count_dispersion.json` dla (rynek, rozgrywki)
  (`count_dispersion.DispersionTable.read`).
- **Pomocnicza**: błąd kwadratowy środka.
- Różnica wariant - A na przypadek; 95% przedział z bootstrapu po meczach
  (2000 losowań, seed 0, `centre_replay.boot_by_group`). Także D jako odniesienie
  (B - D, C - D) dla mężczyzn.
- Podzbiory opisowe: przypadki, w których A faktycznie wybrało inną próbkę niż B;
  ostatnie 730 dni (od 2024-10-13).

## 6. Próg i decyzja (ustalone przed pomiarem)

- Wariant X jest **lepszy** od A w danej populacji, gdy przedział 95% różnicy
  log-loss NB (X - A) leży w całości poniżej zera **dla obu rynków**
  (`goals_total` i `goals_for`). Jeden rynek poniżej zera, drugi z zerem w
  przedziale - "wskazanie", nie zmiana.
- Kobiety (852) to populacja, w której reguła działa na żywo - tam werdykt
  dotyczy kodu. Dla mężczyzn (851 wykluczony) werdykt dotyczy tylko tego, czy
  przywracać mecze towarzyskie do puli (B / C vs D), nie reguły na żywo.
- Żaden wynik nie włącza niczego sam: zmiana wpływa na to, co się drukuje, więc
  wymaga przełącznika w `bet.sofa.epochs` i decyzji operatora.

Zastrzeżenia znane przed pomiarem: alpha NB i bazowe ligi są dopasowane na
całej historii (wspólne dla wariantów, więc nie faworyzują żadnego, ale nie są
"as of"); środek nie zawiera ratingu piłkarskiego (`W_FOOTBALL_RATING` 0.5 na
żywo), jak w odtworzeniu historii (audyt A6); kompletność historii reprezentacji
kobiet w cache jest taka, jaką mamy (mecz o stawkę, którego nie ma w cache, nie
trafi do B ani C).

## 7. Wyniki

Wywołanie: `PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_national_friendly_samples.py`
(główne: `--prior baseline`) oraz `--prior asof` (wrażliwość, patrz niżej). Pula:
24 768 meczów reprezentacji, 3 956 meczów towarzyskich 851 / 852 w cache; okres
2015-01-01..2026-10-12. Różnica = wariant - odniesienie, ujemna = lepiej; 95% z
bootstrapu po meczach (2000, seed 0).

### 7.1 Kobiety (852) - tu reguła działa na żywo (A)

1 355 meczów `goals_total`, 2 860 przypadków `goals_for` (1 505 meczów); A wybrało
inną próbkę niż B w 1 225 / 2 163 z nich.

| porównanie | `goals_total` d log-loss NB | `goals_for` d log-loss NB | werdykt |
|---|---|---|---|
| B - A | -0.00141 [-0.01062; +0.00775] | **+0.00631 [+0.00056; +0.01199]** | gorzej |
| C - A | +0.00373 [-0.00638; +0.01369] | +0.00581 [-0.00082; +0.01245] | brak |
| D - A | +0.00895 [-0.00404; +0.02102] | **+0.02208 [+0.01420; +0.03066]** | gorzej |

Błąd kwadratowy mówi to samo (`goals_for` B - A +0.036 [+0.002; +0.070]).
Podzbiór od 2024-10-13 (493 / 1 015 przypadków): B - A `goals_total` -0.0076
[-0.0220; +0.0057], `goals_for` +0.0095 [-0.0016; +0.0213] - brak różnicy.
Prior as-of: ten sam obraz (B - A `goals_for` +0.00605 [+0.00025; +0.01172]).

### 7.2 Mężczyźni (851) - na żywo D (851 wykluczony z puli), A kontrfaktyczne

2 209 meczów `goals_total`, 4 546 przypadków `goals_for` (2 337 meczów).

| porównanie | prior | `goals_total` d log-loss NB | `goals_for` d log-loss NB | werdykt |
|---|---|---|---|---|
| B - A | baseline | +0.00557 [-0.00025; +0.01174] | +0.00432 [-0.00033; +0.00884] | brak |
| C - A | baseline | **-0.00742 [-0.01340; -0.00149]** | **-0.00638 [-0.01148; -0.00125]** | lepiej |
| C - A | as-of | -0.00134 [-0.00799; +0.00548] | +0.00239 [-0.00331; +0.00807] | brak |
| D - A | baseline | **+0.01367 [+0.00617; +0.02195]** | **+0.01881 [+0.01277; +0.02485]** | gorzej |
| D - A | as-of | +0.00574 [-0.00297; +0.01491] | **+0.01644 [+0.00888; +0.02363]** | gorzej |
| C - D | baseline | **-0.02109 [-0.02781; -0.01481]** | **-0.02519 [-0.03051; -0.01986]** | lepiej |
| C - D | as-of | **-0.00707 [-0.01270; -0.00154]** | **-0.01404 [-0.01956; -0.00860]** | lepiej |
| B - D | baseline | **-0.00810 [-0.01230; -0.00382]** | **-0.01449 [-0.01804; -0.01109]** | lepiej |
| B - D | as-of | -0.00474 [-0.00959; +0.00021] | **-0.01337 [-0.01742; -0.00924]** | wskazanie |

Od 2024-10-13 (646 / 1 296 przypadków, prior baseline): C - D `goals_total`
-0.0181 [-0.0299; -0.0059], `goals_for` -0.0166 [-0.0288; -0.0048].

### 7.3 Wrażliwość na prior (dopisana po pierwszym wyniku, nie pre-rejestrowana)

Warianty mają różne n, więc ściąganie do złego prioru faworyzuje większą
próbkę (C). 851 nie ma wpisu w `sofa_league_baselines.json` (jest wykluczony),
więc SHEET ściąga do `global`: `goals_total` 3.26, a mecze 851 dają średnio 2.54
gola (2 365 meczów od 2015; 852: 3.09 przy baseline 2.97). Dlatego dodano
`--prior asof`: średnia własnych meczów towarzyskich rozgrywek ściśle przed
meczem (min. 30 meczów). Przewaga C nad A u mężczyzn **znika** przy priorze as-of
(była skutkiem złego prioru), a przewaga C nad D **zostaje** na obu rynkach.

## 8. Werdykt

- **Podejrzenie analityka (kobiety, 852) - odrzucone.** Próbka z samych meczów
  towarzyskich (A) nie jest gorsza od próbki z meczami o stawkę: B jest
  **gorsze** na `goals_for` (+0.0063 [+0.0006; +0.0120]), C bez różnicy, D (same
  mecze o stawkę) wyraźnie gorsze (+0.0221 [+0.0142; +0.0307]). Próg z sekcji 6
  (oba rynki poniżej zera) nie jest spełniony dla żadnego wariantu. Reguła
  `pick_same_competition` dla 852 zostaje bez zmian. Przypadek Argentyny (822 dni,
  bez Copa América) to pojedynczy mecz; w populacji mecze o stawkę
  (często z wyraźnie słabszym lub silniejszym rywalem) opisują gole w meczu
  towarzyskim gorzej niż wcześniejsze mecze towarzyskie.
- **Nowe ustalenie (mężczyźni, 851).** Reguła na żywo (D: 851 wykluczony z puli
  od 2026-10-04, więc mecz towarzyski mężczyzn czyta same mecze o stawkę) jest
  najgorszym wariantem. C (towarzyskie + o stawkę w oknie próbki towarzyskiej) bije
  D na obu rynkach z przedziałem w całości poniżej zera przy obu priorach
  (baseline: `goals_total` -0.0211, `goals_for` -0.0252; as-of: -0.0071 / -0.0140),
  a także A bije D na `goals_for` przy obu priorach. To spełnia próg sekcji 6
  dla pytania "czy przywrócić mecze towarzyskie do próbki goli meczu towarzyskiego
  mężczyzn" - **kandydat na zmianę, nie zmiana**: wymaga przełącznika w
  `bet.sofa.epochs` i decyzji operatora.
- **Czego ten pomiar nie mówi.** (1) Środek nie zawiera ratingu piłkarskiego
  (`W_FOOTBALL_RATING` 0.5 na żywo), który może częściowo zmniejszyć stratę D.
  (2) Wykluczenie 851 dotyczy też próbek meczów o stawkę (towarzyskie w próbce
  meczu eliminacji) i ratingu - tego nie mierzono; zmiana musiałaby dotyczyć
  tylko meczu docelowego 851 i tylko rynków goli (`SAME_COMPETITION_METRICS`).
  (3) Alpha NB i bazowe ligi są dopasowane na całej historii (wspólne dla
  wariantów). (4) Mierzony jest środek przy liczbie goli, nie linie Superbetu ani
  ROI. (5) Brak bazowej ligi dla 851 (prior 3.26 przy realnych 2.54) to osobna
  wada środka meczu towarzyskiego mężczyzn - widoczna tu jako efekt prioru, nie
  zmierzona na krzywej.
