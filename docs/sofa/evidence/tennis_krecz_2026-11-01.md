# Tenis: krecz i luka model − próbka (2026-11-01)

**Powód.** 01.11 noga „1. set - Jose Pereira liczba gemów: powyżej 4.5” (1.35,
pewność 0,711, rating `tennis_rating` 0,75, własna próbka 6/10) przegrała:
Storck Franca wygrał 6-3 6-3, utrzymał każde podanie. Pereira skreczował
25.10 przy 1-6. SAMPLES pomija mecz zakończony nieprawidłowo (status 91 / 92),
więc tego meczu nie widziała żadna liczba. Analityk tenisa znalazł krecz, ale
reguła z 27.10 („fakt nowszy niż cena”) pozwoliła mu tylko na notatkę.
Operator: „to powinno było wiedzieć albo agent zaflagować / zdjąć”.

## Pomiar (tylko odczyt, `measure.py`, wynik `out.txt` w katalogu obok)

Populacja: nogi tenisa z `08_confidence.json` 10-05..10-31 (pewność ≥ 0,70,
kurs Superbetu), po deduplikacji 7 869, ocenione WIN/LOSS 7 271
(`sofa_settled_row`). Dev ≤ 24.10, kontrola 25..31.10 (zawiera dzień
mieszany 30.10). Przedziały: bootstrap meczów, 2 000 losowań.

**A - krecz gracza, którego noga potrzebuje, w 14 dniach przed meczem**
(mecz singlowy przegrany Retired / Walkover / kod 98):

| | n nóg | mecze | trafienie − pewność | trafienie − 1/kurs | ROI |
|---|---|---|---|---|---|
| dev, flaga | 55 | 31 | −5,6 [−21,2; +8,7] | −6,2 [−19,6; +6,5] | −10,5% |
| dev, reszta | 2 823 | 1 202 | −4,1 | −3,6 | −4,8% |
| kontrola, flaga | 21 | 15 | +13,9 [−2,3; +24,1] | +10,6 [−5,2; +21,1] | +14,1% |
| kontrola, reszta | 1 290 | 475 | −1,5 | −4,4 | −5,5% |

Wersja ścisła (bez ukończonego meczu od kreczu): 13 / 5 nóg, trafione 12 / 5.
Szersza populacja (wiersze SHEET z `p_central` ≥ 0,70, kontrola): flaga 199
nóg, +0,6 pp względem ceny [−8,7; +8,2]. Flaga zapala się 0-5 nóg dziennie.

**B - luka model − własna próbka > 0,15 (jak `MODEL_ABOVE_OWN_SAMPLE` w
piłce):** kontrola flaga 155 nóg −5,4 pp względem ceny [−13,8; +2,4], ROI
−6,6% wobec −6,5% reszty. Pereira miał lukę dokładnie 0,15, więc B by go nie
złapał. 0,10 i 0,20 tylko jako czułość (niezarejestrowane): 0,20 na kontroli
−13,9 pp [−28,8; +0,3], na dev odwrotnie.

## Wnioski

- **Automatycznej bramki nie ma podstaw włączać** - ani A, ani B: przedział
  na kontroli obejmuje zero, a A na kontroli idzie w przeciwną stronę (próbka
  mała, szum).
- **Decyzja operatora (01.11): WATCH „KRECZ:” od raportów 02.11** - nie jako
  wynik pomiaru, tylko reguła analityka, sprawdzana przez kod
  (`report_check.retirement_findings`, dossier `sides.<strona>.retirement`).
  Zdjęte nogi idą do `removed_by_reads` z tagiem `RETIREMENT` i księga
  rozlicza je osobno - to jest pomiar poza próbą tej reguły
  (`T-KRECZ-WATCH`, `config/sofa_test_registry.json`). Historia
  (A powyżej) mówi, że może nie pomagać; jeśli zdjęte nogi zrealizują się na
  cenie lub wyżej, reguła do wycofania.
- Niezmierzone: różnica flaga − reszta z własnym przedziałem; zwroty (gracz,
  który znów skreczuje, = zwrot, 6 takich nóg poza ROI).
