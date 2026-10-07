# 2026-10-07 — dowód z linii Superbetu: nic nie ucinamy z nazwy

## Decyzje operatora (2026-10-07)

1. Miarą nie jest „czy bijemy cenę” (x ≥ 0,90 i tak akceptuje marżę), tylko
   to, czy statystyki odróżniają dobre 1.20 od złego 1.20. Ta sama zasada dla
   każdego sportu. Rynek, który dziś tego nie robi, **nie jest wycinany** —
   mierzymy go dalej.
2. „Krzywa per pasmo kursu”: pewność nie wyższa, niż takie `p` trafiało na
   liniach Superbetu w tym samym paśmie kursu. Kurs tylko obniża.

## Pomiar

`docs/sofa/evidence/discrimination_within_price_2026-10-07.md`. W skrócie:

- statystyki rozróżniają nogi w paśmie kursu: piłka +14,4 pp [+8,2; +19,6],
  koszykówka +9,1 pp [+1,0; +15,4];
- hokej, siatkówka, tenis i CS2: szum;
- krzywa liczona tylko z `p` zawyża przy długich kursach (koszykówka handicap
  p 0,70–0,80: 0,81 przy kursie < 1,30, 0,62 przy 1,60–2,20; tenis
  `games_won_for` OVER przy 1,60–2,20: 0,47 przy deklarowanych ~0,75).

## Zmiana (od 2026-10-08 00:00Z, `epochs.LINE_EVIDENCE_FROM_UTC`)

- `bet.sofa.line_evidence`, `scripts/sofa/fit_line_evidence.py`,
  `config/sofa_superbet_line_evidence.json` (dopasowany 2026-10-07: piłka i
  tenis 10-05..10-06, sporty 09-20..10-06, wiersze z
  `fit_sport_confidence.py --before 2026-10-07 --dry-run --rows-out`).
- CONFIDENCE: bez odmów z nazwy (`refused_markets`, `admitted_player_markets`,
  `admitted_tennis_set_markets`, `DERIVED_NOT_CALIBRATABLE`).
- SPORT_CONFIDENCE: każdy dopasowany klucz, nie tylko `admitted`; koszykówka
  i CS2 nie są już `NOT_CALIBRATED` w całości.
- Pewność = najniższa z: krzywej (obniżonej o istotne zawyżenie klucza na
  jego liniach) i limitu pasma kursu (gdy linie pasma trafiały istotnie
  poniżej). Rynek bez krzywej: dolna granica Wilsona własnych linii, inaczej
  `NO_LINE_EVIDENCE`.

## Powtórka kuponu 10-07 (SOFA_NOW 07:31Z, katalog roboczy)

| | stara reguła | nowa |
|---|---|---|
| piłka + tenis, nogi niezablokowane | 590 | 389 (+102 / −303) |
| hokej | 80 | 171 |
| koszykówka | 0 | 40 |
| siatkówka | 0 | 0 (`TOURNAMENT_NEVER_SETTLED`) |
| CS2 | 0 | 0 |

- Wypada głównie tenisowe `games_won_for` (−253). Na swoich liniach z
  10-05..10-06 deklarowało 0,751, a trafiało 0,633 (278 linii, 89 meczów).
- Dochodzą rynki setowe tenisa i `goals_1h_total UNDER` (deklarowane 0,799,
  trafione 0,800 na 110 liniach).
- Średnie 1/kurs drukowanych nóg rośnie z 0,71 do 0,80, czyli kupon przesuwa
  się w stronę krótszych kursów.

## Czego nie zrobiono

- Rynki bez modelu (`MARKET_NOT_ALLOWED`): kwarty, druga połowa, parzyste /
  nieparzyste, dnb i propsy zawodników w koszykówce i hokeju. To następna
  praca: model dla każdej rodziny, potem ten sam dowód z linii.
- Siatkówka nadal wymaga turnieju z rozliczonym meczem w ostatnich 14 dniach.
  To bramka modelu, nie nazwy; nie była mierzona.
- `CROSS_LEAGUE_UNLINKED`, `NOT_SETTLEABLE`, `NO_CLASS_CURVE` bez zmian.
- Piłka i tenis mają tylko dwa dni linii stats-only. Korekty i limity są
  liczone na małej próbie i rosną z każdym rozliczonym dniem
  (`fit_line_evidence.py` między dniami, po każdym refitcie krzywych).
- Suspicion (niezmierzone): hokej handicap przy p ≥ 0,95 i kursie 1,37 drukuje
  0,957, bo ani klucz, ani sport nie mają tam 20 linii w paśmie.
- Test `test_chaos_stages::test_offer_refused_from_the_first_request_fails_and_keeps_the_file`
  pada też na czystym HEAD; nie badany.

## Dopisek: rynki koszykówki i hokeja bez modelu (2026-10-07, popołudnie)

Operator: „TAK” — modele dla brakujących rynków.

- **Rodziny drużynowe** (`sport_confidence.EXTENDED_MARKETS`, od 2026-10-08):
  - koszykówka: kwarty (total, handicap, team total, dnb, 1X2), 2. połowa
    (te same), dnb 1. połowy, parzyste/nieparzyste (mecz i drużyna);
  - hokej: dnb tercji.

  Model wyników już symulował każdą kwartę, więc nic nowego nie modelowano.
  Rodziny są oceniane na historii (`HISTORY_MARKETS`, kwarty 1–4) i
  sprawdzane na liniach Superbetu jak każdy klucz.
- **2. połowa i 4. kwarta koszykówki — `OT_RULE_UNKNOWN`.** Superbet nazywa je
  bez „(z dogrywką)”, a jego regulamin (support.superbet.pl, czytany
  2026-10-07) nie mówi, czy dogrywka się liczy. Mecz z dogrywką rozlicza takie
  nogi jako UNGRADEABLE. Operator może to rozstrzygnąć z własnego rozliczonego
  zakładu.
- **Linie zawodników hokeja i koszykówki.** `p` to przedmeczowa liczba
  `player_model` (`player_model.jsonl` SHADOW). Rozliczenie bierze wynik
  SHADOW_SETTLE z protokołu meczu. Krzywej z historii nie ma, więc dziś
  wszystkie mają `NO_LINE_EVIDENCE`: przedmeczowych rozliczonych linii jest
  tylko z ok. 22 meczów koszykówki i 30 hokeja (od 10-02), a żaden kubełek
  nie ma 50 linii. Wiersze `model_source = settle` (model sprzed meczu, ale
  zawodnik dopasowany po protokole) to inne źródło i nie są łączone.
- **Refit krzywych sportów** (`--before 2026-10-07`, nowe rodziny) jest w
  `config/sofa_sport_confidence_calibration.next.json`
  (`effective_from` 2026-10-08). Dzień 10-07 czyta stare krzywe. Dowód z
  linii jest policzony względem nowych.
- **Powtórka sportów 10-07** (nowe krzywe, dowód z linii):
  - hokej 166 nóg, w tym 2 dnb tercji;
  - koszykówka 42, w tym 1 handicap 2. połowy z `OT_RULE_UNKNOWN`;
  - CS2 3;
  - siatkówka 0;
  - `MARKET_NOT_ALLOWED` dla hokeja i koszykówki: 0.
- **Nie zrobione:**
  - niemodelowane rodziny siatkówki i CS2 (`MARKET_NOT_ALLOWED` 176 / 1682);
  - zawodnicy bez przedmeczowego `p`: koszykówka `TEAM_UNRESOLVED` 1152
    wierszy 10-07, `THIN_SAMPLE` 362, `NOT_IN_HISTORY` 152.

## Dopisek 2: siatkówka, CS2, drużyny zawodników + testy e2e (2026-10-07, wieczór)

- **Siatkówka** (`EXTENDED_MARKETS`): dokładny wynik w setach i parzyste /
  nieparzyste punktów meczu (oba oceniane na historii), parzyste /
  nieparzyste punktów seta i „set na przewagi” (tylko z rozliczonych linii).
- **CS2** (`CS2_EXTENDED_FAMILIES`): każda rodzina, którą wycenia silnik —
  handicap i suma rund mapy, zabójstwa drużyny, zabójstwa / śmierci / asysty /
  headshoty zawodnika. Nogi oparte na statystykach meczu biorą wynik
  rozliczonej linii CS2_SETTLE. Rynki serii (`maps_*`, `team_maps`,
  `exact_maps`, `rounds_*`, parzystość rund) zostają bez modelu: silnik ich
  nie wycenia.
- **Model zawodników w SHADOW** czyta najpierw drużyny przypięte przez
  SPORT_IDENTITY, a dopiero potem nazwy (`teams_source`). Na migawkach
  koszykówki z 10-07: linie z `p` 544 → 944; tam, gdzie zadziałały obie
  metody, przypięte identyfikatory zgadzały się z nazwami w 20 na 20 meczów.

### Testy end-to-end (prawdziwe dane, katalog roboczy, SOFA_NOW)

- **Pełny łańcuch 10-07** (CONFIDENCE → SPORT_CONFIDENCE → COUPON_ASSEMBLY →
  PDF → audit_coupon → audit_variants) pod nową epoką: każdy etap kod 0, poza
  `audit_variants` z kodem 1 od 29 uwag C3 (nowe nogi w top 30 bez odczytu
  analityka — oczekiwane w powtórce). U3 przelicza każdą nogę sportową
  ponownie i nie dał żadnej uwagi. Prawdziwy `11_coupon.json` nietknięty
  (md5 bez zmian).
- **Błąd znaleziony przez e2e:** `run_sport_confidence._allowed` gubił flagę
  epoki dla CS2, przez co 1682 linie zostały `MARKET_NOT_ALLOWED`. Poprawione,
  dodany test.
- **Rozliczenie:** każda rozliczona linia rodzin rozszerzonych, rozliczona jak
  noga kuponu (`sport_day.grade_legs`), porównana z wynikiem SHADOW / CS2:
  - koszykówka i hokej: 7785 / 7785 zgodnych;
  - zawodnicy 10-06: 3570 / 3570;
  - CS2: 12 424 / 12 424;
  - siatkówka: 2222 / 2222.

  Nogi sportowe powtórki 10-06: 112, wszystkie WIN / LOSS, bez
  UNGRADEABLE i MISMATCH.
- **Wybór plików:** 10-07 czyta stare krzywe, 10-08 plik `.next.json`;
  epoka włącza się 10-08 00:00Z, a przebudowa 10-07 po północy zostaje przy
  starej regule.
- **Nie przetestowane na żywo:** przypięte drużyny w samej pętli SHADOW
  (`forecast_players`). Sprawdzone tylko na zapisanych migawkach; pierwszy
  prawdziwy przebieg to pętla 10-08.

## Dopisek 3: epoka przesunięta na 2026-10-07 10:55Z (decyzja operatora)

Operator: „chciałbym, aby dzisiejszy kupon był przebudowany z nowymi
zasadami”.

- `epochs.LINE_EVIDENCE_FROM_UTC` ustawione na 2026-10-07 10:55Z, a
  `effective_from` krzywych sportów `.next.json` na 2026-10-07. Tak samo
  rano przesunięto `LINK_SHARED_LEAGUE`.
- 10-07 jest dniem mieszanym: wydruki sprzed 10:55Z są po starej regule,
  przebudowa po tej godzinie po nowej. 380 nóg zablokowanych wcześniej
  zostaje bez zmian.
- Przebudowa (`rebuild_day.py`, 10:54Z, run `rebuild-4ec438fa`): wszystkie
  etapy z kodem 0 lub PARTIAL. 851 pozycji, w tym 471 świeżych:

  | sport | świeże nogi |
  |---|---|
  | piłka | 197 |
  | hokej | 168 |
  | tenis | 56 |
  | koszykówka | 47 |
  | CS2 | 2 |
  | siatkówka | 1 |

  Audit: tylko 29 uwag C3 (top 30 bez odczytu analityka).
- Model zawodników w pętli SHADOW na żywo: 474 linie z `p` po przypiętych
  drużynach, `TEAM_UNRESOLVED` 20.

## Dopisek 4: kalibracja poza próbą, poprawki po weryfikacji, CS2 serie (ok. 11:00–11:55Z)

- **Test poza próbą.** Dowód z linii dopasowany na wcześniejszych dniach,
  nogi drukowane na późniejszych, przedział z bootstrapu po meczach.
  - Pierwsza wersja (korekta tylko przy istotnym zawyżeniu) przy małej
    próbie przepuszczała prawdziwe zawyżenia:
    - tenis: pewność 0,778 wobec trafień 0,698;
    - koszykówka: 0,748 wobec 0,647.
  - Teraz korekta to zmierzony punkt klucza (≥ 50 linii, 30 meczów), a gdy
    klucz ma za mało danych, korekta całego sportu (≥ 20 meczów).
  - Wynik poza próbą (pewność / trafienia):

    | sport | pewność | trafienia | przedział obejmuje 0 |
    |---|---|---|---|
    | piłka | 0,815 | 0,810 | tak |
    | hokej | 0,787 | 0,780 | tak |
    | koszykówka | 0,755 | 0,690 | tak |
    | tenis | 0,738 | 0,658 | tak |
    | siatkówka | 0,760 | 0,684 | tak |

  - CS2 zawyżał o −25 pp (39 linii, 15 serii). Korekta sportu −0,204 jest
    zmierzona tylko na danych na żywo.
- **Weryfikator, runda 1.**
  - Pozycja 1 (Mannheim −4.5, 0,9448) nie miała żadnej linii Superbetu przy
    swoim `p`. Teraz bez komórki pasma limit daje własne linie klucza ze
    wszystkich pasm, od `p` w dół do 0,70.
  - Nogi sportowe miały puste `unfitted_constants`. Poprawione na nogach i w
    nagłówku PDF.
  - 4 odczyty WATCH: Mannheim −4.5 i −3.5, Köln 1. tercja U1.5, Paris –
    ASVEL handicap 2. połowy (`OT_RULE_UNKNOWN`).
- **CS2 serie:** liczba map, handicap map, mapy drużyny i dokładny wynik.
  Rozkład wyniku serii z korelacją map, κ = 6.
- **Rozpoznawanie meczów koszykówki.** Reguła „jeden mecz drużyny w oknie”
  łamała złoty test wabika oraz ochronę przed drużyną rezerw (Kataja
  Talents), więc ją wycofałem. Zamiast niej 4 ręcznie zweryfikowane aliasy.
  Koszykówka ma 97 rozpoznanych meczów zamiast 93.
- **Wiersze dowodu** leżą w `data/line_evidence/rows_before_2026-10-07`
  (wcześniej w katalogu tymczasowym).
- **Godziny:** dwie wcześniejsze notki miały czas lokalny zamiast UTC
  („13:00Z” i „13:35Z” to ok. 11:35Z). Poprawione.
- **Nie modelowane** (lista w CLAUDE.md):
  - rynki wynikowe piłki i tenisa (OFFER `unmapped_markets`, ok. 27 800
    linii 10-07);
  - rundy serii CS2;
  - rynki pochodne i setowe kobiet ponad zmierzony zakres.
