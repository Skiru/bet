# /kupon a literatura - protokół (zapisany przed hold-outem, 2026-11-19)

Pytanie operatora (11-19, po wygranym AKO 7 nóg @4,40): czy metoda, którą
`/kupon` składa nogi, jest zgodna z literaturą, a jeśli nie - poprawić ją,
przetestować i sprawdzić E2E na >= 10 rozliczonych dniach.

## Co mówi literatura (i co z tego wynika dla wyboru nóg)

1. **Marża jest kosztem każdej nogi, a w AKO się mnoży** (Buchdahl, *Squares &
   Sharps, Suckers & Sharks*; Newall 2015, *JDM*). Wartość oczekiwana kuponu =
   0,88 × Π (p_i × kurs_i): liczy się udział marży w każdej nodze.
2. **Prawdziwe p nogi szacuje się z kursu bez marży, nie z 1/kurs**
   (Shin 1993; Štrumbelj 2014, *IJF*; Clarke, Kovalchik i Ingram 2017,
   „Adjusting bookmaker's odds to allow for overround”). Marża nie rozkłada
   się równo: faworyt niesie jej mniej (efekt faworyt-longshot, Snowberg i
   Wolfers 2010). Pipeline ma już `market_p` = metoda „power” na
   dwustronnej drabince (`engine.devig`; 09-18: lepsza od proporcjonalnej i
   Shina).
3. **AKO ma sens tylko, gdy nogi mają przewagę** (Miller i Davidow, *The
   Logic of Sports Betting*; Kelly 1956): kryterium wyboru to wartość
   oczekiwana, nie sama szansa.
4. **Ludzie przeceniają zdarzenia łączne** (Bar-Hillel 1973; Tversky i
   Kahneman 1974) - liczba nóg zostaje domyślnie 2 (bez zmian).

Obecny `/kupon`: szansa = min(pewność, 1/kurs), szukanie = najwyższa szansa
przy iloczynie kursów >= cel. Nogi z pewnością ponad ceną są dla niego
równe (szansa × kurs = 1 dla każdej), więc marży nie widzi (poza remisem
LOW_MARGIN_TIE +0,25%).

## Ramiona

- **OLD** - obecny `slip_builder`.
- **FAIR** - szansa = min(pewność, p bez marży): `market_p` nogi
  dwustronnej (przy świeżym kursie: ten sam udział marży, `market_p × kurs
  kuponu / kurs świeży`), dla nogi jednostronnej (marży nie znamy)
  `ONE_SIDED / kurs`, ONE_SIDED = 0,9465 (dev: zrealizowane / cena nóg
  jednostronnych 1,10-2,00). Szukanie bez zmian.
- **FAIR_EV** - FAIR, a szukanie maksymalizuje Σ log(szansa × kurs)
  (wartość oczekiwaną) zamiast Σ log szansy.

## Dane

Dni z `11_coupon.json` i `13_results.json` (10-13..11-18, 28 dni; brak
10-17/18, 10-24/25, 10-31..11-01, 11-07/08, 11-14 - pliki usunięte 11-19).
**dev 10-13..11-04 (17 dni)**, **hold-out 11-05..11-18 (11 dni)**.
Odtworzenie: `slip_builder.build` na `singles` dnia z jego `reads.json` /
`vetoes.json`, okna 4 h od 10:00 co 2 h (czas lokalny), decyzja 60 min przed
oknem, 3 rozłączne kupony na żądanie, żądania (cel, maks. nóg) = (1,5; 2),
(2,0; 2), (3,0; 3), (4,4; 7); bez świeżego kursu (nieodtwarzalny).
Ocena: `13_results.json` (oceny księgi); zwrot po podatku = 0,88 × Π kursów
nóg niezwróconych, gdy wszystkie wygrały, inaczej 0; kupon z nogą
`unknown` poza oceną. CI: bootstrap po dniu (1000), sparowany po
(dzień, cel, okno, ranga).

## Reguła (zamrożona przed hold-outem)

1. Na dev wybieram jedno ramię: FAIR albo FAIR_EV, to z wyższą średnią
   sparowaną różnicą zwrotu kuponu względem OLD (wszystkie żądania razem).
2. Na hold-oucie, raz: ramię wchodzi do `/kupon`, gdy
   (a) różnica Briera nóg min(pewność, p bez marży) − min(pewność, 1/kurs)
   ma punkt <= 0 (prognoza nie gorsza), **i**
   (b) sparowana różnica średniego zwrotu kuponu ramię − OLD ma punkt >= 0.
   Reguła operatora 11-06: „lepsze niż obecne = wdrażamy, nie musi bić
   ceny”. CI raportowane zawsze; przedział przez zero = mówię wprost, że to
   szum.
3. `/kupon` to nie kupon dnia - nic nie drukuje, więc bez przełącznika w
   `epochs` i bez grupy księgi.
