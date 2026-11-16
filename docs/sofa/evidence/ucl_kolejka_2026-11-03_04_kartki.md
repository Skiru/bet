# Liga Mistrzów 2026-11-03 i 2026-11-04: rozliczenie kolejki i pomiar kartek (2026-11-05)

Pomiar tylko do odczytu: żaden kod, konfiguracja, krzywa ani artefakt potoku nie
został zmieniony. Kod roboczy w scratchpadzie sesji (`ucl.py`, `extract.py`,
`centres.py`, `conflegs.py`, `bias.py`, `raw_halves.py`) - nie jest to czysty
skrypt `measure_*`, więc nie trafił do `scripts/sofa/`. Oceny nóg to oceny
ledgera (`13_results.json`); przedziały 95% to bootstrap po meczach.

## Pytanie operatora

Ile rynków Ligi Mistrzów z 11-03 i 11-04 weszło, dlaczego reszta nie weszła i
czy to wada modelu - "upewnij się na liczbach".

## Werdykt

**Wady modelu nie ma; przegrana kolejka to rzadka 1. połowa w kartkach plus
skupienie wielu nóg kartkowych na mecz.**

- Cała LM (pojedyncze z kuponu): 717 rozliczonych nóg, 589 weszło (82,1%) przy
  pewności 79,6% i cenie 83,9%; płasko 1 u. na nogę −15,0 u. (−2,1%). Przegranych
  128 przy oczekiwanych z pewności ~146.
- Cała strata to kartki: 98 nóg, 32 przegrane przy oczekiwanych 19,9, −19,6 u.
  Rożne +13,2 u., gole / wynik −6,1 u.
- Kartki w modelu sprawdzone trzema niezależnymi drogami (niżej) - poziom, udział
  1. połowy i kalibracja w normie. Kolejka miała 2,0 punktu kartkowego w 1. połowie
  na mecz przy normie 1,33 (P = 2,7% dla 18 losowych meczów fazy ligowej).
- Rynek widział to tak samo: nogi kartkowe "poniżej" miały pewność 0,802, a 1/kurs
  0,848 (Superbet był jeszcze pewniejszy UNDER); trafność 0,662. Ani model, ani cena
  nie miały informacji o kartkowym przebiegu.

## 1. Kolejka mecz po meczu

| dzień | mecz | wynik | nogi | weszło | przegrało | zwrot | oczek. przegr. | 1 u./noga |
|---|---|---|---|---|---|---|---|---|
| 11-03 | Atlético - Bayern | 0:2 | 41 | 36 | 5 | 1 | 8,1 | +1,8 |
| 11-03 | Bodø/Glimt - Lille | 0:0 | 36 | 30 | 6 | 1 | 7,5 | −0,1 |
| 11-03 | Barcelona - Aston Villa | 3:0 | 42 | 37 | 5 | 0 | 8,7 | +2,2 |
| 11-03 | Feyenoord - Inter | 0:3 | 34 | 27 | 7 | 0 | 7,3 | −1,4 |
| 11-03 | Galatasaray - Stuttgart | 2:0 | 57 | 44 | 13 | 0 | 11,6 | −5,3 |
| 11-03 | LASK - Slovan | 4:0 | 36 | 32 | 4 | 0 | 7,0 | +1,7 |
| 11-03 | Man Utd - Roma | 3:2 | 38 | 24 | 14 | 0 | 7,9 | −9,2 |
| 11-03 | Szachtar - Sporting | 0:1 | 29 | 23 | 6 | 0 | 5,9 | −1,6 |
| 11-03 | Villarreal - PSG | 0:6 | 39 | 29 | 10 | 1 | 8,0 | −4,0 |
| 11-04 | AEK - Real Madryt | 2:3 | 41 | 36 | 5 | 1 | 8,6 | +2,4 |
| 11-04 | Dortmund - Betis | 2:1 | 39 | 32 | 7 | 0 | 7,9 | −1,2 |
| 11-04 | Porto - Napoli | 4:1 | 47 | 38 | 9 | 0 | 9,3 | −2,0 |
| 11-04 | Fenerbahçe - Liverpool | 3:2 | 44 | 40 | 4 | 0 | 9,0 | +3,9 |
| 11-04 | PSV - Club Brugge | 1:2 | 45 | 39 | 6 | 0 | 9,4 | +1,5 |
| 11-04 | RB Lipsk - Man City | 2:3 | 35 | 31 | 4 | 0 | 6,9 | +1,5 |
| 11-04 | Lens - Como | 1:9 | 50 | 42 | 8 | 0 | 10,2 | +0,2 |
| 11-04 | Slavia - Arsenal | 1:2 | 29 | 25 | 4 | 0 | 6,1 | +1,0 |
| 11-04 | Viking - Sabah | 4:1 | 35 | 24 | 11 | 0 | 7,0 | −6,5 |

11-03: 352 nogi, 80,1%, −16,0 u. 11-04: 365 nóg, 84,1%, +0,9 u.

Bet Buildery LM (jeden na mecz, najwyższe `combined_probability`): 11-03 7 z 8
weszło (Man Utd - Roma przegrał na pierwszej nodze), 11-04 2 z 4 (Porto - Napoli
i Dortmund - Betis przegrały na nodze kartkowej). Ceny buildera sofa nie podaje.

Czytania: 11-03 żaden mecz LM nie był czytany (od 11-02 czytania tylko na
żądanie); 11-04 analitycy przeczytali 7 meczów LM i dali KEEP każdej nodze
kartkowej (sędzia i skład bez zmian). Czytania i automat usunęły w obu dniach 22
nogi LM, z czego 21 by weszło.

## 2. Gdzie przegrało

| grupa rynków | nogi | przegrane | oczek. przegrane | 1 u./noga |
|---|---|---|---|---|
| kartki | 98 | 32 | 19,9 | −19,6 |
| gole / wynik | 235 | 43 | 49,3 | −6,1 |
| rożne | 235 | 25 | 45,0 | +13,2 |
| obrony / strzały / spalone | 76 | 16 | 17,9 | −1,1 |
| zawodnicy | 26 | 8 | 6,5 | −4,1 |
| karne | 47 | 4 | 7,9 | +2,7 |

Kartki: centrum modelu 3,66, fakt 4,33 na mecz (18 meczów); w 1. połowie 1,25 i 2,0.
Najwięcej nóg zabiły mecze z kartkami ponad model: Galatasaray - Stuttgart (8),
Man Utd - Roma (9, czerwona Cunhy w 90+1'), Dortmund - Betis (8), Porto - Napoli
(7, czerwona Rafy Marína w 88' i karny), Viking - Sabah (czerwona McCarthy'ego w
76'), Lipsk - City (6). Gole / wynik: mecze skrajne - Lens - Como 1:9, Villarreal
- PSG 0:6 (4:0 po 17'), Bodø - Lille 0:0 (deszcz, wiatr, sztuczna murawa), Man Utd
- Roma 0:2 do przerwy i 3:2. Relacje: Sky Sports, Vavel, Football Italia, ESPN,
UEFA (część kartek tylko ze skrótów wyszukiwarki).

## 3. Pomiar kartek

### (a) Model kontra fakt, wszystkie rozliczone mecze sezonu (05_sheet.json, 09-17..11-04)

| rynek | grupa | mecze | model | fakt | fakt − model [95%] |
|---|---|---|---|---|---|
| cards_points_total | LM | 51 | 3,68 | 3,78 | +0,10 [−0,47; +0,71] |
| cards_points_total | LE + LKE | 73 | 4,28 | 4,16 | −0,11 [−0,58; +0,34] |
| cards_points_total | reszta | 1 956 | 4,43 | 4,64 | +0,21 [+0,11; +0,32] |
| cards_points_1h_total | LM | 27 | 1,22 | 1,67 | +0,45 [−0,05; +0,99] |
| cards_points_1h_total | puchary UEFA | 64 | - | - | +0,46 [+0,14; +0,80] |
| cards_points_1h_total | puchary UEFA bez 11-03/04 | - | - | - | +0,39 [+0,06; +0,76] |

LM według kolejek (cały mecz, model / fakt): 10-13 3,72 / 4,00; 10-14 3,78 / 3,75;
10-20 3,91 / 2,50; 10-21 3,40 / 3,67; 11-03 3,60 / 4,11; 11-04 3,72 / 4,56.
Centrum 1. połowy to udział połowy x centrum całego meczu
(`football_card_halves.CardHalfRates.half_share`).

### (b) Surowa historia Sofascore (incydenty, od 2021-07, 47 288 meczów z sędzią)

| grupa | mecze | średnio pkt kartkowych | 1. połowa | udział 1. połowy [95%] |
|---|---|---|---|---|
| LM | 687 | 4,11 | 1,44 | 0,350 [0,330; 0,370] |
| LE | 641 | 4,38 | 1,51 | 0,346 [0,327; 0,367] |
| LKE | 935 | 4,67 | 1,55 | 0,332 [0,317; 0,347] |
| top 5 lig | 2 414 | 4,16 | 1,35 | 0,323 [0,314; 0,334] |
| inne | 42 611 | 4,36 | 1,48 | 0,340 [0,338; 0,342] |

Model użył dla LM udziału 0,349 - zgodnego z historią. Faza ligowa / grupowa LM:
4,17 (2024/25, 138), 3,84 (2025/26, 144), 3,85 (2026/27 do 11-02, 60).

### (c) Kalibracja pewności nóg kartkowych (wszystkie wydrukowane, od 09-17)

| | nogi | mecze | pewność | trafność | różnica [95%] |
|---|---|---|---|---|---|
| LM "poniżej" | 98 | 37 | 0,800 | 0,704 | −9,6 pp [−23,6; +4,1] |
| LM "powyżej" | 26 | 18 | 0,805 | 0,731 | −7,4 pp [−28,8; +12,1] |
| LE/LKE "poniżej" | 107 | 45 | 0,800 | 0,841 | +4,1 pp [−5,4; +12,6] |
| reszta "poniżej" | 1 129 | 595 | 0,783 | 0,762 | −2,1 pp [−5,4; +1,1] |
| powtórka historii, puchary UEFA, `cards_points_total` UNDER p 0,70-0,95 | 474 wiersze | 148 | - | - | +1,6 pp [−3,4; +6,5] |

### (d) Rzadkość kolejki

Pula: faza ligowa LM 2024-2026 (324 mecze, średnio 3,95 pkt, sd 2,24; 1. połowa
1,33, sd 1,34). Losując 18 meczów: średnia >= 4,35 w 21,7% losowań, średnia 1.
połowy >= 2,0 w 2,7% losowań.

## Co z tego wynika

1. Kartek LM w modelu nie poprawiać na podstawie tej kolejki: poziom, udział
   połowy i kalibracja są w normie; zmiana wyuczona na jednej rzadkiej kolejce
   byłaby dopasowaniem do szumu.
2. Do obserwacji (podejrzenie, nie pomiar): nadwyżka kartek 1. połowy w pucharach
   UEFA na żywych dniach (+0,46 [+0,14; +0,80], 64 mecze). Historia jej nie
   potwierdza. Powtórzyć pomiar po fazie ligowej (koniec stycznia 2027) na
   wszystkich meczach pucharowych z liniami 1. połowy.
3. Skupienie: 98 nóg kartkowych na 18 meczach (do 6 na mecz) przegrywa razem.
   Limit nóg na mecz (`max_positions_per_match` w `config/sofa_coupon_form.json`,
   dziś wyłączony) zmienia rozrzut wyniku, nie jego wartość oczekiwaną - to decyzja
   operatora, nie poprawka modelu.
