# Stawka meczu w modelu - CS2 i tenis: notatka wykonalności (faza A, 2026-11-18)

**Werdykt: niewykonalne jako poprawka modelu - ani CS2, ani tenis.** Żaden przypadek nie ma liczby meczów, przy
której test dokładności / kalibracji rozstrzygnąłby efekt rzędu, jakiego można się spodziewać. Pre-rejestracji
egzaminu nie ma; jest ta notatka z liczebnościami. Do rozważenia jest wyłącznie flaga **tylko do wyświetlenia**
(sekcja 5).

Stan wiedzy: liczone **wyłącznie liczebności** meczów wg przypadku. Żaden wynik badanego meczu, żadna reszta, żaden
log score wg przypadku nie był liczony. Wyniki *wcześniejszych* meczów tego samego etapu / tego samego tie służą
tylko do ustalenia przypadku (bilans as-of), tak jak zrobiłby to SHEET na żywo. Baza tylko do odczytu
(`file:data/sofa.db?mode=ro`), bez sieci. Skrypty i wyjścia: katalog scratch sesji
(`stakes_cs2_tennis/cs2_counts.py`, `tennis_counts.py`, `*.txt`) - pomiar, nic w `src/` / `config/`.

## 1. Co jest w danych

### CS2
- `cs2_series` (19,103 serii, 2025-10-01 .. 2026-11-18, wszystkie zakończone do 2026-10): turniej = nazwa **etapu**
  (`tournament`, np. "CCT Europe Group A", "IEM Stage 2", "PGL Playoffs"), `season_id`, `best_of`, wynik w mapach.
- `roundInfo`: **brak w ogóle** - 0 z 24,575 wpisów CS2 w `sofa_listed_event`, 0 z 1,002 `sofa_event_detail`
  serii CS2. Jest `tournament.isGroup` (listing; 19,077 z 19,103 serii ma wpis listingu).
- Starsza historia CS2 praktycznie nie istnieje w cache (listing csgo: 879 wpisów w 2024, 262 w 2023) - cała próba
  to ~13 miesięcy. Dłuższa historia wymagałaby backfillu sieciowego (`backfill_cs2.py`), poza tą fazą.
- Format etapu rozpoznawalny tylko strukturalnie (z kształtu całego etapu - na żywo z opublikowanej drabinki):
  Swiss = 16 drużyn, 30-34 serie, max 3 W / 3 L (93 etapy); GSL = 4 drużyny, 5 serii (725); round robin =
  `isGroup` i n(n-1)/2 serii (112); playoff = "Playoff" w nazwie (591); reszta 204 etapy.
- Bilans as-of drużyny w etapie = zakończone wcześniej serie tego samego etapu. **Nie da się** odróżnić górnej i dolnej
  drabinki playoffów (brak `roundInfo`), ani "martwego" meczu round robin (liczba miejsc awansu nieznana).

### Tenis
- `roundInfo` jest (nazwa rundy / numer), ale "stawka" istnieje tylko w: tie drużynowych (Davis Cup, Billie Jean King
  Cup, United Cup, Hopman) i grupach round robin (ATP Finals, WTA Finals, Next Gen Finals).
- Tie nie ma identyfikatora: grupowane po (turniej, sezon, para krajów graczy, okno 6 dni); stan tie = wcześniejsze
  zakończone rubbery; mecz "rozstrzygnięty" = kraj ma już większość zaplanowanych rubberów (z odwołanymi). Przybliżenie:
  okno 6 dni może przeciąć tie (nie mierzone).
- Obrona punktów rankingowych: **nie do policzenia** (cache nie ma punktów rankingu do obrony) - nazwane, poza zakresem.

## 2. Liczebności (zakończone mecze; bez wyników)

### CS2 - serie (mapy zakończone), rozwój 2025-10-01 .. 2026-04-30, odłożone 2026-05-01 .. 2026-10-31

| przypadek | serie rozwój | serie odłożone | mapy rozwój / odłożone | serie ze statystykami map rozwój / odłożone |
|---|---|---|---|---|
| Swiss decyder 2-2 | 92 | 70 | 229 / 167 | 92 / 70 |
| Swiss mecz o odpadnięcie (x-2) | 288 | 191 | 680 / 449 | 287 / 189 |
| Swiss mecz o awans (2-x) | 256 | 174 | 601 / 417 | 256 / 172 |
| Swiss pozostałe | 1,071 | 642 | 2,471 / 1,426 | 1,067 / 638 |
| GSL decyder (1-1 vs 1-1) | 267 | 257 | 651 / 611 | 266 / 253 |
| GSL mecz przegranych (0-1 vs 0-1) | 292 | 289 | 678 / 662 | 286 / 279 |
| GSL mecz zwycięzców (1-0 vs 1-0) | 295 | 283 | 671 / 657 | 294 / 278 |
| GSL otwarcie | 790 | 748 | 1,647 / 1,617 | 770 / 716 |
| round robin, ostatnia kolejka strony | 135 | 116 | 172 / 158 | 135 / 115 |
| round robin, wcześniej | 365 | 331 | 432 / 394 | 363 / 316 |
| playoff, ostatnia seria etapu (finał) | 311 | 246 | 856 / 690 | 310 / 246 |
| playoff, pozostałe | 3,496 | 2,780 | 8,111 / 6,488 | 3,442 / 2,709 |
| inne etapy | 1,649 | 1,422 | 2,716 / 2,324 | 1,632 / 1,317 |

Liczby to górna granica: nie sprawdzono, ile z tych serii silnik ocenia (`cs2_engine.MIN_MAPS_RATED` = 10 map obu drużyn).

### Tenis - single, rozwój 2024-07-01 .. 2025-12-31, odłożone 2026-01-01 ..

| przypadek | rozwój | odłożone | uwaga |
|---|---|---|---|
| tie: martwy rubber (tie już rozstrzygnięty) | 31 | 9 | + 77 odwołanych (zwrot u Superbetu) |
| tie: rubber, w którym kraj może zamknąć tie | 518 | 195 | + 98 odwołanych |
| tie: wcześniejsze rubbery | 559 | 247 | |
| RR Finals: 3. mecz, jedna strona 2-0 lub 0-2 | 18 | 2 | |
| RR Finals: 3. mecz, pozostałe | 6 | 1 | |
| RR Finals: wcześniejsze | 48 | 12 | |

## 3. Tabela mocy

Reguła domu (pre-rejestracja terminarza, sekcja 7, S5): wynik binarny zwycięzcy wymaga ~4.9k · 1.75 = **8,575**
meczów w kubełku na 1 pp średniej |Delta p|. Uzupełniająco: minimalny wykrywalny przesuw kalibracji
(80% mocy, alfa 0.05 dwustronnie, p ~ 0.5, DEFF 1.75 - mapy jednej serii nie są niezależne):
MDE = 2.8 · sqrt(0.25 · 1.75 / n).

| kubeł (pooling z góry) | n rozwój | n odłożone | MDE rozwój | MDE odłożone | 8,575 osiągnięte? |
|---|---|---|---|---|---|
| CS2 eliminacja: Swiss x-2 + 2-2 + GSL decyder + GSL przegranych (mapy) | 2,238 | 1,889 | 3.9 pp | 4.3 pp | nie |
| CS2 awans: Swiss 2-x + GSL zwycięzców (mapy) | 1,272 | 1,074 | 5.2 pp | 5.7 pp | nie |
| CS2 Swiss 2-2 sam (mapy) | 229 | 167 | 12.2 pp | 14.3 pp | nie |
| CS2 finał playoffu (mapy) | 856 | 690 | 6.3 pp | 7.0 pp | nie |
| CS2 RR ostatnia kolejka (mapy) | 172 | 158 | 14.1 pp | 14.7 pp | nie |
| tenis tie "może zamknąć" (mecze) | 518 | 195 | 8.1 pp | 13.3 pp | nie |
| tenis martwy rubber + RR 2-0/0-2 (mecze) | 49 | 11 | 26 pp | 56 pp | nie |

## 4. Dlaczego to nie wystarczy (poza liczbami)

- **Stawka w CS2 jest symetryczna** tam, gdzie ją widać: Swiss paruje równe bilanse, GSL tak samo - obie strony grają
  o to samo. Nie przesuwa więc p zwycięzcy w żadną stronę; poprawka mogłaby być tylko członem rozrzutu (skala logitu
  ku 0.5, rozkład liczby map). Przykład skali: k = 0.9 przy p = 0.65 zmienia p o ~1.4 pp - trzy razy poniżej MDE
  największego kubła (3.9 pp). Asymetryczne przypadki (martwy mecz round robin, dolna drabinka) są w danych
  **nierozpoznawalne** (brak `roundInfo`, brak liczby miejsc awansu).
- Zakłócenia nie do oddzielenia przy tych n: etapy Swiss to prawie wyłącznie LAN najwyższego poziomu (Major, IEM, ESL
  Pro League); efekt etapu = efekt poziomu turnieju.
- Na żywo: bilans as-of w Swiss / GSL wymaga wyników serii rozegranych **kilka godzin wcześniej tego samego dnia** w
  `cs2_series`; czy historia CS2 jest odświeżana w ciągu dnia przed SPORT_CONFIDENCE - nie sprawdzone (otwarte).
- Tenis: martwe rubbery są głównie odwoływane (77 odwołanych vs 40 rozegranych), a rozegrane grają często rezerwowi -
  to, czy taki mecz w ogóle trafia do oferty, nie było sprawdzane.

## 5. Co zamiast: flaga tylko do wyświetlenia (propozycja, nic nie wdrożone)

Na wzór `bet.sofa.stakes` (piłka): pokazana przy nodze, **nigdy** nie zmienia pewności ani nie bramkuje.

- CS2 `STAKES_ELIMINATION` (Swiss x-2 / 2-2, GSL decyder / mecz przegranych), `STAKES_ADVANCEMENT` (Swiss 2-x, GSL
  zwycięzców), `STAKES_GRAND_FINAL` (ostatnia seria playoffu, gdy drabinka opublikowana), opcjonalnie
  `RR_LAST_ROUND` (bez oceny "martwy" - nie da się). Źródło: `cs2_series` (etap, sezon) + `isGroup` z listingu;
  format etapu z liczby drużyn / serii w opublikowanym etapie.
- Tenis `TIE_DEAD_RUBBER` (tie rozstrzygnięty), `TIE_CLINCHER` (kraj może zamknąć tie), `RR_DECIDED_SIDE` (3. mecz
  grupy Finals, strona 2-0 lub 0-2). Źródło: listing tenisa (turniej, sezon, kraje graczy, `winnerCode` wcześniejszych
  rubberów).
- Flaga do analityka (kontekst), ewentualny test w przód (`T-...-flag`) dopiero przy kilkuset nogach - przy obecnym
  wolumenie CS2 na kuponie i rzadkości tie w tenisie nie ma terminu, w którym to nastąpi (nie szacowane).

## 6. Decyzje otwarte (operator)

1. Czy flaga wyświetlana (sekcja 5) w ogóle jest potrzebna - wartość tylko jako kontekst dla analityka; jeśli tak,
   przełącznik w `bet.sofa.epochs` od następnego dnia 00:00Z (zmienia to, co drukuje PDF / HTML).
2. Czy zlecić backfill historii CS2 sprzed 2025-10 (sieć, godziny mostu): podwojenie próby nadal nie zbliża
   kubła eliminacji do 8,575 map, więc samo to nie zmieni werdyktu.
3. Czy człon rozrzutu CS2 (skala logitu / rozkład map w meczach eliminacyjnych) mierzyć jako osobny problem -
   zmiana rozkładu map (`SERIES_KAPPA`) jest pytaniem o rozkład, nie o stawkę, i wymaga własnej pre-rejestracji.
