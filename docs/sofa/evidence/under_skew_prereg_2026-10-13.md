# Prerejestracja: skos UNDER po reficie 2026-10-13 (T-UNDER-SKEW)

Zapisane 2026-10-13 ok. 18:40Z, **przed** pierwszym rozliczonym dniem nowych krzywych. Plan operatora z 2026-10-13 (kolejka po refitcie, punkty 1–3): jedna ogólna hipoteza zamiast listy rynków wybranych po wyniku.

## Skąd hipoteza (dane już widziane - nie są testem)

Rozliczone linie 10-09..10-12, surowe `p_central` >= 0,70, bootstrap po meczach, stare krzywe i stare centrum
(tabela z sesji 2026-10-13 oraz `settled_by_market_2026-10-09_12.md`):
- rożne "poniżej" przegrywały w każdym z sześciu rynków (od -2,6% do -14,0% ROI; najgorzej 2. połowa: trafione 72-73% przy modelu 81-85%),
  a "powyżej" było na cenie lub nad nią (jedyny przedział nad zerem: rożne drużyny OVER +3,4% [+0,1; +6,6]);
- 14 porównań na 4 dniach - jedno wyjście ponad zero to tyle, ile daje przypadek. Te dni wybrały hipotezę, więc nie mogą jej sprawdzić.

## Hipoteza

H1: na krzywych z refitu 2026-10-13 (zainstalowane 18:06Z, centrum z B1/B2/B14/C1/B5 od 18:10Z) wydrukowane nogi **UNDER** realizują się
poniżej swojej pewności bardziej niż nogi **OVER** tej samej rodziny.

H0: różnica (zrealizowane - pewność)_UNDER - (zrealizowane - pewność)_OVER >= 0.

## Dane testowe

- Dni: od **2026-10-14** (pierwszy cały dzień nowej epoki; 10-13 jest dniem mieszanym i nie wchodzi) do pierwszego dnia, w którym oba kierunki rodziny mają >= 150 rozliczonych wydrukowanych nóg z >= 60 meczów, najpóźniej 2026-10-27.
- Nogi: wydrukowane single `11_coupon.json` (nie `removed_by_reads`, nie zablokowane z innej epoki), rozliczone WIN/LOSS; zwroty poza próbą.
- Pewność: `confidence` z kuponu. Pozycje z `price_gap` liczone tak samo (pomiar dotyczy krzywej, nie ceny).
- Osobno: piłka (rodziny `settle_family`: corners, goals, shots, cards), tenis (games), hokej, koszykówka, siatkówka, CS2 (rynki). Sporty nigdy nie są sumowane.

## Metryka i próg

- Dla każdej (sportu, rodziny) z oboma kierunkami nad progiem n: D = mean(won - confidence | UNDER) - mean(won - confidence | OVER), przedział 95% z bootstrapu po meczach (2000 losowań, seed 0).
- **Potwierdzenie H1 dla rodziny:** cały przedział D poniżej zera **i** po poprawce Holma na liczbę badanych rodzin.
- Jako drugi wynik (bez progu): ROI kierunku przy cenie wydruku, z przedziałem.

## Co z tego wynika

- Rodzina z potwierdzoną H1 jest kandydatem na zmianę - **przez przełącznik w `epochs` i nową epokę**, nigdy przez wybór lig, bramek ani "drukuj tylko OVER" (CLAUDE.md: strojenie bramek po wynikach przegrywa poza próbą).
- Brak potwierdzenia = koniec tematu do nowego dowodu; nie przesuwa się okna ani progu po obejrzeniu danych.

## Narzędzie

`scripts/sofa/measure_settled_by_market.py` daje surowe p na wszystkich liniach (obraz, nie test). Test liczy się na wydrukowanych nogach z pewnością; skrypt testu powstanie przed pierwszym odczytem wyniku, z tym dokumentem jako specyfikacją.
