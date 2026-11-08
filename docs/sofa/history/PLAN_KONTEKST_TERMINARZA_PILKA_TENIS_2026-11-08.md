# Plan: kontekst terminarza i zmęczenia w prognozie - piłka i tenis (v2, 2026-11-08)

Status: **plan po trzech rundach przeglądu; nic nie wdrożone, nic nie zmierzone na nowo.**
Materiały (wiążące, po angielsku): `docs/sofa/evidence/kontekst_terminarza_2026-11-08/`
- `r1_*` - inwentarz rynków piłki (133 klucze) i tenisa (44 klucze), dane i mechanizm odtwarzania, wcześniejsze pomiary + literatura;
- `r2_coverage_review.md` (C1-C32), `r2_method_review.md` (M1-M18) - recenzje pokrycia i metody;
- `r3_final_review.md` - recenzja końcowa: status każdej uwagi C/M, usterki D1-D25 z tekstem zastępczym,
  **reguła zaliczenia (c)** i **lista kroków wdrożenia (d)**.

**Hierarchia:** gdzie ten plan i `r3_final_review.md` się różnią, wygrywa ten plan; gdzie plan milczy,
obowiązują teksty zastępcze D1-D25, reguła (c) i lista (d) z `r3` - dosłownie.

## 1. Cel

Nie przewaga nad ceną. **Prognoza potoku dla każdego rynku piłki i tenisa ma być dokładniejsza**: środek bliżej
tego, co się dzieje, pewność równa trafności. Ocena na historii ze znanymi wynikami, właściwą regułą punktacji
(log score), **bez ceny Superbetu jako kryterium**. Jedyna zmiana w tym planie to **poprawka terminarza / zmęczenia**;
przesadna pewność przy kursach >= 1.40 to osobne badanie, nigdy mieszane z tymi wariantami (D21).

Definicja "pomogło" = **reguła (c)** z `r3`: grupa statystyk zalicza egzamin tylko przy P1-P6 (jednostronna górna
granica 95% Delta < 0 po korekcie Holma, bootstrap klastrowy dwukierunkowy; efekt materialny >= 3% środka;
kalibracja linii i >= 0.70 nie gorsza; nie-gorszość każdej innej grupy i warstwy). "100% pewności" w statystyce nie
istnieje - ta reguła jest jej zamrożonym, liczbowym zamiennikiem.

## 2. Co wiemy (skrót r1)

- **Piłka:** terminarz liczony w SAMPLES (`schedule.py`) jest tylko opisem. Wcześniejsze pomiary (10-04/05 vs próbka,
  11-05 vs cena) nigdy względem środka modelu. Dwie drogi wejścia: końcowy środek (liczniki, gole, propsy przez udział)
  i rating (`FootballForecast.centre`: 1X2 / DC / DNB / wynik dokładny / symulator = 51% nóg >= 0.70).
  Poza zasięgiem: karne / czerwone (średnia ligowa), propsy niezależne od drużyny, "każda z drużyn" w połowach (surowa próbka).
- **Tenis:** zmęczenie tylko w ratingu (`dmin78`, `drest`, `dn7`; dopasowany 10-08, przed P14 i poprawką best-of-five);
  brak czasu = 0 minut (ITF); cechy tylko jako różnica graczy (sumy nie reagują na dwóch zmęczonych); model punktowy
  i stara próbka bez zmęczenia.
- **Dane:** liczniki piłkarskie realnie od 2024Q4/2025Q1 (rożne 2024Q3: 354 mecze), serwis tenisa od 2025Q2,
  cache tenisa kończy się 2026-10-19 (D1).

## 3. Decyzje tego planu (ponad `r3`)

1. **Okresy - D1 dosłownie.** Egzamin 2026-01-01..2026-10-31 (tenis do końca cache, 2026-10-19 - napisać to w raporcie).
   Rozwój z rozgrzewką: gole / wynik / tenis zwycięzca-gemy-sety od 2024-07-01; liczniki piłki od 2025-01-01;
   serwis tenisa od 2025-05-01. Eksploracja do 2025-08-31, walidacja 2025-09..12 (<= 3 zapisane spojrzenia).
2. **Droga poprawki - D3 dosłownie** (jedna droga na wiersz; nigdy (i) i (ii) na tym samym wierszu).
3. **Instalowane są zamrożone współczynniki, które zdały egzamin** (z eksploracji + walidacji), nie ponownie
   dopasowane na pełnej historii - inaczej wdrożylibyśmy coś, czego egzamin nie widział (rozstrzyga pkt 16 listy (d)).
4. **Cień - wariant odwrócony (r3 sekcja 6):** po zaliczeniu przełącznik od następnego dnia 00:00Z (reguła operatora
   2026-11-06 "lepsze od obecnego = wdrożyć"), każdy objęty wiersz niesie `p_central` bez poprawki; test
   `T-SCHEDULE-TERM-FORWARD` zarejestrowany przed dniem przełącznika, reguła wycofania zapisana z góry.
5. **Zgoda operatora (2026-11-08):** sesja wykonująca ma zgodę na przefitowanie krzywych na kopii bazy i instalację
   **wyłącznie** grup, które zaliczyły regułę (c), z przełącznikiem od następnego dnia 00:00Z, nigdy w zbudowany dzień.
   Żadna grupa nie zalicza = commit tylko pomiaru i raportu "zmierzone i odrzucone", bez przełącznika i bez configu.
6. **Status każdej uwagi:** pre-rejestracja (F0) zawiera tabelę wszystkich C1-C32, M1-M18, D1-D25 ze statusem
   (wdrożone / odrzucone z powodem) - częściowe statusy z `r3` (a) muszą dostać regułę albo liczbę.
7. **Piłka narodowa** wyłączona z dopasowania i egzaminu (mundial 2026 w okresie egzaminu); kobiety i tenis
   kobiet / drużynowy jako osobne warstwy, instalowane tylko gdy ich warstwa zalicza (D11).
8. **Progi 0.60** (tenis sumy, 4 klucze symulatora): klucz progu dostaje poprawione p dopiero po ponownym
   pomiarze progu tą samą zamrożoną procedurą; do tego czasu wyłączony z przełącznika (D13).
9. **Praca wielodniowa:** sesja prowadzi plik stanu `docs/sofa/history/STAN_KONTEKST_TERMINARZA_<data>.md`
   (faza, SHA, hashe, ścieżki plików, co dalej), żeby kolejna sesja mogła wejść bez powtarzania.

## 4. Fazy (szczegóły: lista (d) w `r3`, kroki 1-34)

| faza | co | bramka |
|---|---|---|
| F0 | pre-rejestracja (mechanizmy, cechy, formy, grupy, droga D3, okresy D1, tabela mocy, reguła (c), strażnicy G1-G5, wcześniejsze spojrzenia, cechy niemożliwe do policzenia, tabela rodzin z kodu, tabela statusów C/M/D) + ten plan - **jeden commit, SHA zapisany** | brak analizy przed commitem |
| F1 | `bet.sofa.schedule_features` (czysty, as-of, wspólny dla odtworzenia i SHEET) + testy (bez przecieku, mieszanie w obrębie dnia, zgodność z SAMPLES, wyświetlanie bez zmian) | bramki repo |
| F2 | kopia bazy (VACUUM INTO), rejestrator wg D4, próba 5 dni (zgodność p do 1e-9), pełny przebieg ~6 h w tle; egzamin rozdzielony na X / y (G2); tenis: rating z cięciem rozwoju w obu wariantach, model punktowy po dniu | próba zgodna |
| F3 | eksploracja: GLM z offsetem (drużyna-sezon), kontrast w meczu, warstwy, rozrzut, połowy, tylko-prognoza vs +aktualizacja; S1-S3 | |
| F4 | zamrożenie współczynników, walidacja (<= 3 spojrzenia), S4-S5; commit JSON współczynników + skryptu egzaminu (hashe) | |
| F5-F6 | jeden egzamin `measure_schedule_exam.py --spec-sha`, reguła (c), raport po polsku z każdą rodziną | log egzaminu odmawia drugiego przebiegu |
| F7 | tylko grupy zaliczone: kroki (d) 13-34 - przełącznik w `epochs`, haki, marker + `rebuild_plan`, przefitowania na kopii jako `.next.<D>.json`, line evidence, grupa księgi, rejestr, dokumentacja, bramki, E2E na kopii dnia | bramki + E2E |
| F8 | commit tylko własnych ścieżek, push tylko zweryfikowanego SHA | `origin/main` nie przesunął się |

## 5. Mechanizmy (do zamrożenia w F0, z poprawkami D14 / D22)

**Piłka (strona i rywal):** odpoczynek w godzinach / 24 (przedziały <= 3, 4-5, 6-8, 9-20, >= 21 dni), mecze w 7 / 14 / 21 dni,
mecz kontynentalny w poprzednich 4 dniach (i interakcja z krótkim odpoczynkiem), powrót po przerwie reprezentacyjnej,
dogrywka / karne w poprzednim meczu, minuty podstawowych i czerwona kartka w poprzednim meczu (jeśli pokrycie składów
wystarczy - zmierzyć w F0), ważny mecz w ciągu 4 dni (rotacja), strefa czasowa (eksploracyjnie). Kontrole: faza sezonu, rozgrywki, siła faworyta.

**Tenis (gracz, suma i max obu):** obciążenie gemami w 78 h / 7 dni (pełne pokrycie), punkty z flagą pokrycia, minuty tylko
jako wrażliwość; wygrane rundy w bieżącym turnieju osobno od meczów z poprzednich turniejów; dominacja w poprzednim meczu
(kontrola); przerwa >= 21 dni; krecz w 14 dniach; debel tego samego dnia; kwalifikacje; zmiana nawierzchni / hali.
Nowe cechy **zastępują** `dmin78` / `dn7` / `drest` w wariancie (nie obok). Na żywo: przez `config/tennis_rating.next.<D>.json`.

**Nie do policzenia (nazwane):** odległość podróży, wysokość, pogoda, trener (backfill), konflikty / morale.

## 6. Ryzyka

- Wynik "żadna grupa nie zalicza" jest realny (pomiar 10-04, literatura: efekty małe) - to pełnoprawny wynik.
- Część okresu była już oglądana (10-04/05, 11-05) - wymienione w raporcie (G5).
- Kilkudniowa praca, pełne przebiegi ~6 h; tylko na kopii bazy, pętle dzienne zostają włączone.
- Drzewo robocze dzielone z innymi sesjami: nigdy `git stash`, nigdy `git add -A`.
