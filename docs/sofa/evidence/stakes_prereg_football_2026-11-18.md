# Pre-rejestracja: stawka meczu (stan tabeli) w prognozie - piłka, ligi klubowe (faza A, 2026-11-18)

**Status: GOTOWE DO ZAMROŻENIA.** Faza A = inwentarz danych (same liczebności) + reguły. Commit tego pliku
(SHA = "spec SHA" egzaminu) zamraża dokument **przed** jakimkolwiek spojrzeniem na wynik (reszta,
trafność, średnia goli wg stanu). Do tej chwili żaden wynik wg stanu nie był liczony (sekcja 10). Decyzje
operatora z 2026-11-18 wpisane (sekcja 12). Wzór: `schedule_context_prereg_2026-11-09.md` (reguła (c),
G1-G5) - tam, gdzie ten dokument milczy, obowiązuje tamten dosłownie.

**Zamrożony moduł stanu:** `docs/sofa/evidence/stakes_football_2026-11-18/stakes_state.py`,
sha256 `99e81fe70f6ed6855afb6264e20c8cdf0798126463ca5cba69c958233bee1949` (w F1 przenoszony bez zmian
logiki do `bet.sofa.stakes_state`; test parzystości z tym plikiem). Skrypty liczebności w tym samym katalogu:
`extract.py` (listing -> wiersze), `stats_presence.py` (obecność statystyk), `inventory.py` (stan każdej
strony), `tabulate.py` / `xcover.py` (liczebności; `xcover.py` czyta tylko wiersze X, nigdy magazyn y),
`sanity_unl.py` (kontrola stanu LN); wyniki `tabulate.txt`, `xcover.txt`, `sanity_unl.txt`, `inventory.log`.

## 1. Cel i jedyna definicja "pomogło"

Dokładniejsza prognoza (log score, kalibracja) rynków piłki klubowej przez stan tabeli **każdej strony**
w chwili startu meczu. Dziś model stawki nie zna: `bet.sofa.stakes` tylko wyświetla `STAKES_SIX_POINTER`
/ `STAKES_TOP4` (reszta mierzona względem średniej ligi, nie względem środka modelu - dlatego nigdy nie
była poprawką). Tu reszta jest liczona **względem własnego środka / p modelu** (ten sam, który drukuje
SHEET). Cena Superbetu nie jest kryterium. "Pomogło" = co najmniej jedna grupa zalicza regułę (c) z sekcji 9.

## 2. Okresy (granica = start meczu UTC)

| warstwa | okres | rola |
|---|---|---|
| rozgrzewka (rating, próbki, tabele) | cała historia | tabela as-of z meczów przed startem |
| eksploracja (dopasowanie) | 2024-07-01 .. 2025-08-31 (liczniki od 2025-01-01) | współczynniki, bramki S1-S4 |
| walidacja (<= 3 spojrzenia, G5) | 2025-09-01 .. 2025-12-31 | Delta walidacyjna (S4) |
| egzamin (raz) | **2026-01-01 .. 2026-11-17** | reguła (c) P1-P6 |

Egzamin do 2026-11-17 jest możliwy, bo operator zatwierdził (2026-11-18, D7) nowe odtworzenie (plik X) do
2026-11-17 na kopii bazy - wykonywane w fazie B, nie teraz.

## 3. Populacja

- Mecze z `sofa_listed_event`, sport football, status `finished`, bez towarzyskich (`comparability`), bez
  przyznanych przy stole (`--awarded-excluded`; w tabeli ich punkty się liczą, jak w dossier), tylko rundy
  ligowe / grupowe (`roundInfo` bez `cupRoundType` i bez nazwy rundy).
- **Grupa tabeli** = (uniqueTournament, sezon, tournament). Kwalifikuje się, gdy każda para drużyn występuje
  tyle samo razy m in {1..4} (zdarzenia `finished` + `notstarted`; brakujące pary dozwolone tylko w
  sezonie trwającym - ostatni mecz <= 30 d przed 2026-11-18 - i <= 25% meczów, wtedy brakujące mecze są
  **wnioskowane jako pozostałe** z m); >= 12 drużyn; żadna inna grupa tego samego (rozgrywki, sezon) nie
  dzieli >= 3 drużyn (ligi z podziałem na grupę mistrzowską / spadkową wyłączone).
- Mężczyźni. Kobiety (kluby) = osobna warstwa, instalowana tylko gdy sama zalicza (moc - sekcja 8).
- **Reprezentacje: bez poprawki i bez egzaminu** (D1). Ten sam moduł liczy dla nich stan strony jako
  **flagę wyłącznie do wyświetlania** (PDF / HTML / dossier), która nigdy nie zmienia pewności ani nie
  bramkuje nogi. Definicje z sekcji 4 (granice z 4.2 i h2h UEFA z 4.3) **są definicjami tej flagi**.
- Strona w stanie AMBIGUOUS: mecz wypada z dopasowania i egzaminu; na żywo t = 0 dla obu stron.

## 4. Stan strony (zamrożony; `stakes_state.py`)

### 4.1 Tabela as-of

Punkty 3/1/0 z meczów grupy zakończonych **ściśle przed** startem badanego meczu (mecze o tej samej
godzinie - ostatnia kolejka grana równolegle - są pozostałymi). Pozostałe = pary grupy jeszcze nie
rozegrane w chwili startu (z listingu + wnioskowane z m), bez samego meczu.

### 4.2 Granice (pozycje k, "skończyć w top k")

| rozgrywki | granice B |
|---|---|
| ligi klubowe | {1, n - Z}, Z = 3 przy n <= 16, inaczej 4 (przybliżenie `stakes.py`) |
| flaga reprezentacji: Liga Narodów UEFA A-C (grupy 4) | {1, 2, 3} |
| flaga: Liga Narodów UEFA D | {1} |
| flaga: el. EURO, el. MŚ UEFA, el. MŚ CAF | {1, 2} |
| flaga: el. PNA | {2} |
| flaga: Liga Narodów CONCACAF | {1, n - 1} |
| flaga: el. MŚ CONMEBOL | {6, 7} |

Flaga reprezentacji poza tą listą (el. MŚ AFC / CONCACAF, el. Pucharu Azji, młodzieżowe, kobiece): brak.
"Najlepsze drugie miejsca" między grupami nie są modelowane.

### 4.3 Możliwe / pewne

Dla strony s i każdego wyniku o in {W, R, P} samego meczu: `possible_k(o)` = istnieje dokończenie
pozostałych meczów (W/R/P każdy), w którym s kończy w top k; `certain_k(o)` = każde dokończenie.
**Dokładne wyliczenie** (3^r scenariuszy), gdy pozostałych innych meczów r <= 8; inaczej **ograniczenia**
(wzajemne mecze innych pominięte) - mogą zostawić rozstrzygniętą stronę jako ALIVE, nigdy nie ogłoszą
nierozstrzygniętej jako rozstrzygniętej. Udział dokładnych: kluby 3.2% meczów, 36.3% przy postępie >= 0.9.

Remis punktowy na granicy liczony dwa razy - optymistycznie (s wygrywa każdy remis) i pesymistycznie.
Wyjątek (tylko flaga reprezentacji: Liga Narodów, el. EURO - h2h pierwszym kryterium): remis rozstrzyga mała
tabela (pkt h2h, bilans h2h, gole h2h), gdy wszystkie mecze między remisującymi są rozegrane przed startem i
porządek jest ścisły. Bilans bramek ogółem nie jest kodowany.

### 4.4 Stany

W danym trybie remisów:
- wszystkie granice rozstrzygnięte: **SECURED**, gdy s jest pewnie ponad co najmniej jedną granicą (mistrz,
  utrzymany środek tabeli, zwycięzca grupy), inaczej **DEAD** (spadł / odpadł / zamknięty na dole);
- inaczej **MUST_WIN** (pula, D4), gdy dla jakiejś otwartej k: `possible_k(W)` i nie `possible_k(R)`
  (trzeba wygrać) albo `possible_k(R)` i nie `possible_k(P)` (trzeba co najmniej punktu);
- inaczej **ALIVE** (odniesienie, t = 0).

Stan końcowy: oba tryby zgodne -> ten stan; jeden tryb MUST_WIN, drugi SECURED / DEAD -> MUST_WIN z flagą
`tb` ("wygrać trzema golami"); każda inna niezgodność -> **AMBIGUOUS** (wykluczony).

Kontrola stanu (nie wyniku), Liga Narodów 2026/27 przed 6. kolejką (`sanity_unl.txt`): Walia DEAD (Norwegia
6 pkt i h2h Norwegii), Norwegia MUST_WIN (`tb`), Dania MUST_WIN, Portugalia ALIVE, Austria i Szwecja SECURED,
Polska ALIVE (remis Polski niczego nie zmienia - decyduje mecz Rumunii), Hiszpania i Anglia MUST_WIN (`tb`),
Grecja AMBIGUOUS. Zastrzeżenie: MUST_WIN jest matematyczne (obejmuje gonitwę bez realnej szansy);
warstwa raportowa: pozostałe mecze strony <= 3 vs > 3.

## 5. Grupy i droga poprawki (jak terminarz, D3 tamtego)

G = {`goals` (pełny, 1H, 2H; strony i sumy - droga (i)), `football_result` (1X2 / DC / DNB / wynik
dokładny / klucze symulatora przez środki goli ratingu - droga (ii)), `corners`, `shots_sot`,
`cards_fouls`}; K <= 5. Spalone, obrony, wrzuty, wybicia, odbiory, czerwone / karne, propsy spoza udziału,
joints z surowej próbki: nieobjęte (x1).

t_s = beta_own[stan_s] + beta_opp[stan_rywala], kolumny MUST_WIN, SECURED, DEAD (own i opp; ALIVE = 0),
per (metryka bazowa, połowa); `_total` = suma środków stron. Droga (i) na końcowym środku
(`live_centre` / `centre_chain`), droga (ii) w `FootballForecast.centre("goals_for")` **po** terminie
terminarza (zainstalowany, w obu ramionach). Nigdy (i) i (ii) na jednym wierszu. Klucze progu 0.60: poza
przełącznikiem do ponownego pomiaru progu.

## 6. Estymacja (tylko eksploracja + walidacja)

- Odtworzenie (faza B): nowy plik X `calibrate_from_cache` (flagi z `replay_rules` zainstalowanych krzywych +
  `--schedule-term`, `--form-table-per-family`, `--awarded-excluded`, `--no-write`, `--from 2024-07-01`) do
  2026-11-17 na **kopii bazy** (`VACUUM INTO`); y egzaminu w zapieczętowanym magazynie (G2).
- Poisson GLM z offsetem log(środek końcowy) i efektami stałymi drużyna-sezon; football_result: log loss 1X2
  z `football_1x2_dnb.probabilities` na środkach bazowych vs poprawionych.
- Ściągnięcie c_shr = c · tau² / (tau² + SE²), tau = 0.05, SE klastrowe (drużyna). Zamrożone = ściągnięte z
  eksploracji + walidacji; **te same instaluje się po zaliczeniu**.
- S1: permutacja stanu w obrębie drużyna-sezon (200 powtórzeń), p < 0.05. S2 (zamiast opóźnionej ekspozycji -
  stan jest trwały z kolejki na kolejkę): permutacja stanu w obrębie (liga-sezon, tercja tabeli, decyl postępu
  sezonu), p < 0.05 - oddziela stawkę od pozycji i słabości klubu (zarzut z docstringu `stakes.py`).
- Kierunki S3 (hipoteza motywacji, **nie** pomiar 2026-10-08): own MUST_WIN -> akcje ofensywne own (gole,
  rożne, strzały) w górę; own DEAD i own SECURED -> akcje ofensywne own w dół, opp w górę lub 0; kartki /
  faule -> bez kierunku (wymagają S1 i S2).

## 7. Inwentarz (zapytania 2026-11-18; tylko liczebności, stany po pooled MUST_WIN)

Grupy: kluby **987** (n 12-26, mediana 16; wyłączone: 4 630 niepełny listing, 648 z etapami, 9 965 z < 12
drużynami); reprezentacje **146** (24 niepełne). Mecze klubowe (mężczyźni): 2024-07 .. 2025-12 111 486,
egzamin 2026 81 028; grup z meczem: 251 (2024-07 .. 2025-06), 583 (2025-07 .. 12), 598 (2026).

**Strony-mecze, kluby mężczyźni.** Rozwój = wiersze modelu w pliku X terminarza (2024-07 .. 2025-12).
Egzamin = listing do 2026-11-17 (gole: każdy mecz; liczniki: mecz z daną statystyką w `sofa_event_stats`):

| stan | gole rozwój / egz. | rożne rozwój / egz. | strzały rozwój / egz. | kartki rozwój / egz. |
|---|---|---|---|---|
| MUST_WIN | 3 276 / 7 625 | 417 / 1 692 | 377 / 1 092 | 481 / 1 821 |
| SECURED | 6 798 / 17 429 | 1 115 / 2 804 | 987 / 1 978 | 1 133 / 3 055 |
| DEAD | 1 391 / 3 270 | 228 / 425 | 206 / 309 | 229 / 477 |
| ALIVE (odniesienie) | 194 479 / 127 686 | 22 930 / 36 289 | 20 221 / 24 189 | 25 099 / 38 424 |
| AMBIGUOUS (wykluczony) | 2 548 / 6 046 | 306 / 1 326 | 275 / 840 | 356 / 1 397 |

(Plik X terminarza do 2026-10-20 ma na egzaminie MUST_WIN 7 378 / 1 431 / 1 148 / 1 408 - nowy X do 11-17
dołoży resztę.) Kobiety (kluby, egzamin): MUST_WIN 492, SECURED 1 041, DEAD 216, AMBIGUOUS 399.
Reprezentacje (flaga, tylko opis; egzamin 2026): MUST_WIN 88, SECURED 9, DEAD 14, AMBIGUOUS 62, ALIVE 349.

**Remisy niekodowalne:** AMBIGUOUS = 2.2% stron-meczów klubowych (5.9% przy postępie >= 0.67); reprezentacje
7.7% (6.4%). Stany zależne od rozstrzygnięcia remisu (`tb`): 15.7% MUST_WIN klubów, 19.4% reprezentacji.
Rozgrywki-sezony z rundami pucharowymi (baraże, play-off): 43% meczów klubowych - warstwa P5.

## 8. Tabela mocy (S5; wzór terminarza)

n_wymagane = 7.85 · (1/mu + alpha) · 1.75 / c², mu / alpha z `fb_power.json` terminarza (średni środek
bazowy, bez wyników). Najmniejszy wykrywalny |c| na egzaminie (strony-mecze z sekcji 7; kolumna opp ma
tyle samo; ALIVE = odniesienie, bez c):

| grupa | n przy c=0.03 / 0.05 / 0.10 | MUST_WIN | SECURED | DEAD |
|---|---|---|---|---|
| goals | 16 348 / 5 885 / 1 471 | 0.044 | **0.029** | 0.067 |
| corners | 6 154 / 2 215 / 554 | 0.057 | 0.044 | 0.114 |
| shots_sot | 3 763 / 1 355 / 339 | 0.056 | 0.041 | 0.105 |
| cards_fouls | 2 597 / 935 / 234 | **0.036** | **0.028** | 0.070 |

Skala odniesienia (spojrzenie 2026-10-08, względem ligi): 3.6-5.5% środka. Moc do ~3% ma SECURED (gole,
kartki/faule), MUST_WIN do ~4-6%, DEAD tylko >= 7-11%. S5 liczone ponownie z nowego pliku X tym samym
wzorem; grupa bez mocy idzie tylko pulą zapisaną z góry (`shots_sot` + `corners`; `cards_fouls` bez
partnera) albo wcale.

## 9. Reguła zaliczenia (c) - dosłownie z prereg terminarza, sekcja 8, z podmianami

Podmiany: jednostka = grupa z sekcji 5 (K <= 5); S1/S2 = sekcja 6; "kubeł ekspozycji" P2 = kolumna stanu
(own / opp) z >= 2% wierszy egzaminu grupy; warstwy P5 = kobiety, tercyle |s| faworyta, kontynentalne vs
krajowe, rozgrywki z rundami pucharowymi, dokładne vs ograniczenia, stany `tb`, pozostałe mecze <= 3.
Reszta bez zmian: Delta_g = średnia po meczach egzaminu [S_treat - S_base]; P1 górna jednostronna 95% < 0
(bootstrap gospodarze x goście, 2 000, Holm po K); P2 |c| >= 0.03; P3 linie skalibrowane (krzywe z
rozwoju) Delta <= 0 i górna < +2e-4; P4 kalibracja >= 0.70 na p bazowym, slack 0.005; P5 nie-gorzej
(grupy < +1e-4, warstwy >= 2 000 wierszy < +5e-4); P6 znak egzaminu = znak rozwoju (opisowo). Instalowane
tylko terminy grup zaliczających; zero zaliczeń = raport zerowy. G1-G5 dosłownie; log
`docs/sofa/evidence/stakes_exam_log.md`, skrypt `measure_stakes_exam.py --spec-sha <sha>` odmawia przy
istniejącej linii badania i przy sha256 modułu innym niż wyżej.

## 10. Wcześniejsze spojrzenia (G5)

| kiedy | co | dane | wpływ |
|---|---|---|---|
| 2026-10-08 | `measure_peer_choice.py` sekcja stakes (`peer_choice_2026-10-08.md` sekcja 5): SIX_POINTER / TOP4 vs średnia ligi-sezonu, 23 172 mecze | historia do ~10-08, **w tym część okresu egzaminu** | wielkość efektu (0.08-0.16 sd) znana; kierunki S3 z hipotezy motywacji; inny estymand (liga, nie środek modelu) i inne stany |
| 2026-11-09 | egzamin terminarza | wyniki 2026-01 .. 10-20 otwarte dla innych cech | brak cech stawki; zaakceptowane, jak tam G5 |
| 2026-11-18 | ta faza A | wyniki meczów **przed** każdym startem jako wejście tabeli; w kontroli LN wydruk ok. 30 wyników LN 2026/27 (wejścia tabeli; reprezentacje - poza egzaminem) | żadna reszta / trafność / średnia wg stanu nie była liczona |

## 11. Wdrożenie

Po zaliczeniu (kluby): przełącznik `STAKES_TERM` w `bet.sofa.epochs` od następnego dnia 00:00Z po commicie
instalacji; moduł `bet.sofa.stakes_state` (logika = zamrożony plik, testy offline w `tests/sofa/`), config
`config/sofa_stakes_terms.json` (współczynniki + `unfitted_constants`: Z, granice z 4.2, r <= 8, 12 drużyn,
25% wnioskowanych, 30 d, tau), znacznik `stakes_term_rule` (rebuild_plan re-run SHEET), odwrócony cień
`p_central_no_stakes_term`, krzywe przefitowane na kopii bazy z `--stakes-term`, **go operatora**,
`T-STAKES-TERM-FORWARD` z regułą wycofania jak terminarz. Grupa niekwalifikująca się / AMBIGUOUS = x1.

Niezależnie od egzaminu (D1): flaga stanu reprezentacji (wyświetlanie na PDF / HTML / dossier, nigdy
pewność, nigdy bramka, bez grupy księgi) - od następnego dnia 00:00Z po commicie kodu, jak każda zmiana
wyświetlania. Flagi `stakes.py` zostają.

## 12. Decyzje operatora (2026-11-18)

- **D1 Reprezentacje:** bez poprawki i bez egzaminu; flaga stanu tylko do wyświetlania, definicje z sekcji 4.
- **D2 Liczniki:** eksploracja liczników 2025-01-01 .. 2025-08-31, walidacja 2025-09 .. 12, egzamin bez
  zmian - przesunięcie granicy egzaminu wstecz zmieszałoby okresy już otwarte; cienki rozwój kompensuje
  ściągnięcie (tau).
- **D3 Granice lig:** tylko {1, n - Z} - znaczenie tytułu / awansu i spadku jest wspólne prawie wszystkim
  ligom, 4. miejsce zależy od formatu, którego baza nie zna.
- **D4:** NEED_POINT w puli z MUST_WIN. **D5:** SECURED i DEAD osobno.
- **D6 Ligi < 12 drużyn:** wyłączone, jak `stakes.MIN_TEAMS` - małe ligi częściej grają z podziałem / po
  3-4 razy, a tabela sezonu zasadniczego nie niesie tam stawki.
- **D7:** nowe odtworzenie do 2026-11-17 na kopii bazy - zatwierdzone (faza B).
