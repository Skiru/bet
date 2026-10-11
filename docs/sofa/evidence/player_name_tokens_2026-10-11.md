# Rynki zawodników w piłce: pokrycie, dopasowanie nazwisk i blokada marży (2026-10-11)

Pytanie operatora (2026-10-11): ile tracimy na rynkach zawodników? Dane:
`runs/sofa/2026-10-08..10` (oferta `04_offer.json`, próbki `03_samples.json`,
arkusz `05_sheet.json`, `08_confidence.json`, `11_coupon.json`) i cache
składów `/lineups` w `data/sofa.db`. Skrypty pomiarowe były jednorazowe (w
scratchu sesji); liczby poniżej są z nich, nie z pamięci.

## 1. Co weszło na kupon

| dzień | nogi zawodników na kuponie | przeszły CONFIDENCE, nie wydrukowane |
|---|---|---|
| 10-08 | 0 | 0 |
| 10-09 | 0 | 2 (piłka) |
| 10-10 | 2 (hokej, `player_pp_points` UNDER 0.5) | 3 (piłka) |
| 10-11 | 0 | 0 |

Wszystkie 5 piłkarskich nóg odpadło na `confidence.single_is_fairly_priced`:
Superbet kwotuje propsy piłkarzy tylko po stronie „powyżej”, więc drabina nie
ma marży (`overround = None`), a reguła „marża ≤ 15%” traktuje brak marży jak
marżę za wysoką. Bez nazwanego powodu na wierszu. (4 z 5 wygrało - to fakt o
dniu, nie argument; próba jest za mała na cokolwiek.)

## 2. Pokrycie oferty (10-08..10-10)

39 468 linii zawodników z kursem „powyżej”:

| powód | linie | udział |
|---|---|---|
| wiersz w arkuszu | 11 536 | 29% |
| p poza 5–95% (głównie długie kursy) | 8 783 | 22% |
| próbka < 5 występów | 8 590 | 22% |
| brak próbki (`NO_ENTITY_FOUND`) | 7 164 | 18% |
| same zera | 3 267 | 8% |

Powody poza „wiersz w arkuszu” odtworzone z próbek regułami SHEET (SHEET nie
zapisuje powodów pominięcia, tylko liczniki); „p poza 5–95%” liczone z
odsetka trafień próbki, nie z p modelu - przybliżenie. Przy kursie ≤ 1,60
(6 397 linii, tam noga może przejść progi): 58% ma wiersz, 22% cienka
próbka, 18% brak próbki.

## 3. Dlaczego brak próbki

680 par (dzień, mecz, zawodnik) z `NO_ENTITY_FOUND`, odtworzonych na
składach z cache:

| przyczyna | n |
|---|---|
| **inny zapis nazwiska** (najlepszy wynik `token_sort_ratio` 60–84) | 346 (263 przy kursie ≤ 1,60) |
| nie ma go w składach (wynik < 60) | 195 |
| dopasowany, ale nigdy nie wszedł (ławka) | 117 |
| dopasowany, inne luki statystyk | 22 |

Superbet pisze wielu zawodników pełnym nazwiskiem rejestrowym, Sofascore
nazwiskiem boiskowym: „Andrade, Matheus Araujo” / „Matheus Araujo”,
„Santos Batista, Joao Gabriel” / „Joao Gabriel”, „Goncalves, Julio Cesar” /
„Julio Cesar” (głównie Brazylia, Portugalia). Podejrzenie o transfery
(Minamino, Adingra…) **nie** jest główną przyczyną - niezmierzone osobno.
Ławka to poprawny brak próbki; od teraz luka mówi „named in N squads, never
came on” zamiast mylącego „matched no squad member”.

Superbet podaje przy zawodniku id Sportradara (`sr:player:…`), nie
Sofascore - mapy między nimi nie mamy, więc dopasowanie zostaje po nazwisku.

## 4. Reguła tokenów i jej sprawdzenie

`players.match_player_by_tokens`: jedyny w składzie kandydat, którego tokeny
nazwiska zawierają się w tokenach nazwiska Superbetu (lub odwrotnie), przy
**≥ 2 wspólnych tokenach**; dwóch zawierających się kandydatów (także
jednotokenowy „carlos” obok „joao carlos”) to brak odpowiedzi. Działa tylko
jako fallback dla zawodnika, którego `match_player` nie znalazł w **żadnym**
składzie, i tylko gdy wszystkie odpowiadające składy wskazują tę samą osobę
po tej samej stronie.

**Precyzja (pośrednio):** na zawodnikach, których `match_player` już
dopasowuje, reguła tokenów wskazała tę samą osobę w **20 033 z 20 033**
meczo-składów (≥ 2 tokeny: 19 424 / 19 424; 1 token: 609 / 609).

**Tożsamość (niezależnie od naszego modelu):** jeśli to ten sam człowiek,
kurs Superbetu na „strzały powyżej 0,5” powinien porządkować odsetek trafień
jego próbki tak, jak dla dopasowań fuzzy:

| grupa | n | Spearman(1/kurs, trafienia w próbce) |
|---|---|---|
| obecne dopasowania (`match_player`) | 1 471 | 0,506 |
| nowe, ≥ 2 wspólne tokeny | 108 | **0,513** |
| nowe, 1 wspólny token | 23 | 0,292 |
| losowy kolega z drużyny | 1 366 | 0,039 |

Stąd `PLAYER_TOKEN_MIN_SHARED = 2`: jeden token nie jest wykazany jako ta sama
osoba.

**Równoważność refaktoru:** stara (`HEAD`) i nowa `build_player_samples` z
wyłączonym przełącznikiem na tych samych składach (10-08..10-10, 76 meczów,
8 881 próbek): próbki identyczne w 76/76; luki identyczne poza opisem ławki.

**Zasięg:** replay na składach z cache dodaje 616 próbek po tokenach (445 z
≥ 5 występami) w trzy dni - przybliżenie (historia odtworzona z obserwacji
metryk, nie dokładnie ta, którą widzi SAMPLES).

**Rozliczalność:** SETTLE dostaje `matched_name` próbki z `match_rule`
„tokens” i ocenia dokładnie to nazwisko we własnym składzie (kandydat w
drugim składzie, dowolną regułą, to `PLAYER_AMBIGUOUS`). Na 616 próbkach z
10-08..10-10 i składach rozegranych meczów: 390 ocenionych, 132 nie zagrało
(zwrot), 90 nie było w kadrze meczowej (nierozliczone, jak każdy taki
zawodnik), 4 luki statystyk. Bez tej ścieżki: 0 z 616.

## 5. Zmiany

- `epochs.PLAYER_NAME_TOKENS_FROM_UTC` = 2026-10-12 00:00Z (dodaje próbki,
  więc wiersze i nogi - od następnego dnia). Wiersz arkusza niesie notkę
  `PLAYER_NAME_TOKENS`, próbka `match_rule`.
- `epochs.ONE_SIDED_SINGLES_FROM_UTC` = `None` (**czeka na operatora**):
  noga z drabiny bez strony „poniżej” może być singlem, gdy jej pewność
  pochodzi z krzywej własnego rynku (`market:`) z ≥ 300 wierszami
  (`ONE_SIDED_MIN_CURVE_N`, próg PASS `measure_calibration`); x ≥ 0,90 i
  reszta bramek bez zmian; noga ma `one_sided_market`, PDF / HTML pokazują
  „1-str.” (PDF) / „jednostr.” (HTML) w kolumnie marży, `audit_variants` C2 sprawdza regułę zamiast
  marży. Wariant „zmierzona marża rodziny” odpadł: na rynku jednostronnym
  marży nie da się zmierzyć.

## 6. Replay end-to-end (10-10, scratch)

Kopia dnia 2026-10-10 w scratchu (bez historii druku - nic nie zablokowane z
prawdziwego wydruku), zegar `SOFA_NOW` 2026-10-10 14:40Z (oferta z 14:37Z),
nowy kod SHEET → CONFIDENCE → COUPON_ASSEMBLY → PDF / HTML → audyty.
Prawdziwe pliki dnia: md5 przed = po.

| wariant | wiersze arkusza | nogi | single | nogi zawodników | single zawodników |
|---|---|---|---|---|---|
| B0: oryginalne próbki, przełącznik jedn. wył. | 45 797 | 1 317 | 1 313 | 3 | 0 |
| V1: + próbki po tokenach (replay) | 46 669 | 1 318 | 1 313 | 4 | 0 |
| V2: V1 + `ONE_SIDED_SINGLES` wł. | 46 669 | 1 318 | 1 317 | 4 | 4 |

- Tokeny: +872 wiersze, wszystkie z notką `PLAYER_NAME_TOKENS`; **0**
  istniejących wierszy ze zmienionym `p_central`; +1 noga po bramkach
  pewności (Owusu, Toronto - Montréal, `player_shots_for` 1.5 OVER @1.21,
  pewność 0,795).
- Przełącznik: +4 single (Blondel, Goes, Homenchenko, Owusu; krzywe
  `market:` n = 1 240 / 4 179 / 1 702 / 1 240; x 0,90–0,96), **0** usuniętych.
- PDF renderuje je z „1-str.” w kolumnie marży; `audit_variants` bez żadnej
  uwagi C2 (pozostałe uwagi: U3 - brak snapshotów sportów w scratchu, C3 -
  odczyty analityków przypisane do pozycji prawdziwego kuponu; oba to cechy
  scratcha, nie zmiany).

Nie sprawdzone: prawdziwy SAMPLES z przełącznikiem (wymaga mostu; próbki po
tokenach w replayu są przybliżeniem) - pierwszy przebieg to 2026-10-12.
