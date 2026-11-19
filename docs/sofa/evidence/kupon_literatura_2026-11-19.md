# /kupon a literatura - pomiar (2026-11-19): NOT_PASSED, nic nie wdrożone

Zlecenie operatora (11-19, po wygranym AKO 7 nóg @4,40): wprowadzić do
metody składania nóg `/kupon` poprawki zgodne z literaturą, przetestować,
sprawdzić E2E na >= 10 rozliczonych dniach. Protokół i reguła zamrożone przed
hold-outem: `kupon_literatura_2026-11-19/PROTOCOL.md` (sha256 `d2c6e29d…`,
sprawdzony przed odczytem hold-outu).

**W skrócie:** poprawka z literatury (szansa nogi = min(pewność, cena bez
marży) zamiast min(pewność, 1/kurs)) **nie przeszła** hold-outu: kupony
zwróciły −1,6 pp [−4,6; 0,0] względem obecnego `/kupon` (11 dni, 903
kupony). Prognoza nóg nie gorsza (Brier −0,00011 [−0,00029; +0,00004]), ale
pieniądze nie lepsze. `/kupon` zostaje bez zmian. Literatura i nasze dane
zgadzają się co do jednego: marża mnoży się w AKO - żadna metoda wyboru nóg
tego nie odrabia.

## Co sprawdzono (literatura → ramię)

| źródło | wniosek | ramię |
|---|---|---|
| Shin 1993; Štrumbelj 2014; Clarke, Kovalchik, Ingram 2017 | prawdziwe p nogi = kurs bez marży (FLB: faworyt niesie mniej marży), nie 1/kurs | **FAIR**: min(pewność, `market_p` - de-vig power; noga jednostronna 0,9465/kurs) |
| Kelly 1956; Miller i Davidow 2019 | kryterium = wartość oczekiwana, nie szansa | **FAIR_EV**: FAIR + szukanie max Σ log(szansa × kurs) |
| Buchdahl; Newall 2015 | marża to koszt każdej nogi, w AKO mnożony | obie (marża w szansie) |
| Bar-Hillel 1973; Tversky i Kahneman 1974 | ludzie przeceniają zdarzenia łączne | bez zmian: 2 nogi domyślnie |

Obecny `/kupon` (OLD): min(pewność, 1/kurs), najwyższa szansa przy iloczynie
>= cel; nogi ponad ceną są dla niego równe (szansa × kurs = 1).

## Dane

`11_coupon.json` + `13_results.json`: dev 10-13..11-04 (17 dni), hold-out
11-05..11-18 (11 dni). Odtworzenie `slip_builder.build` (prawdziwy kod
`/kupon`) z `reads.json` / `vetoes.json` dnia, okna 4 h co 2 h od 10:00,
decyzja 60 min przed oknem, 3 rozłączne kupony, żądania (1,5; 2 nogi),
(2,0; 2), (3,0; 3), (4,4; 7); bez świeżego kursu. Zwrot po podatku 12%
z ocen księgi. CI bootstrap po dniu. Skrypty: `kupon_literatura_2026-11-19/`.

## Nogi (kurs 1,10-2,00, dwustronne)

| | dev (n 29 280) | hold-out (n 14 459) |
|---|---|---|
| Brier min(pewność, 1/kurs) | 0,16619 | 0,17012 |
| Brier min(pewność, market_p) | 0,16608 | 0,17001 |
| różnica | −0,00011 [−0,00037; +0,00013] | −0,00011 [−0,00029; +0,00004] |
| zwrot / cena: dwustronne / jednostronne | 0,954 / 0,947 | 0,942 / 0,936 |

Struktura z literatury jest w danych (1,10-1,25: marża < 9% zwraca 0,964
ceny, >= 9% 0,942 - dev), ale nie przekłada się na lepszy kupon.

## Kupony

| | dev: zwrot | hold-out: zwrot | hold-out: obiecana / weszło |
|---|---|---|---|
| OLD | −20,5% | −23,1% | 39,5% / 39,3% |
| FAIR | −21,0% | −24,7% | 39,0% / 38,1% |
| FAIR_EV | −23,5% | −25,7% | 38,1% / 38,1% |
| FAIR − OLD (sparowane) | −1,4 pp [−9,1; +6,2] | **−1,6 pp [−4,6; 0,0]** | |
| FAIR_EV − OLD | −3,1 pp [−10,8; +5,1] | −2,3 pp [−9,4; +4,1] | |

Na dev wybrany FAIR (reguła 1). Hold-out: (a) Brier nie gorszy - spełnione;
(b) zwrot >= OLD - **niespełnione**. Kalibracja obiecanej szansy, lepsza na
dev (OLD 43,3% obiecane / 40,4% weszło; FAIR 40,0 / 40,1), na hold-oucie się
nie powtórzyła (OLD 39,5 / 39,3).

Uwaga (niewyjaśnione): na dev FAIR zmieniał 91% kuponów, na hold-oucie 16%.

## Wniosek

Każdy wariant traci 15-35% po podatku w każdym celu ceny; im więcej nóg, tym
więcej (4,4 przy 7 nogach). Kod `/kupon` bez zmian; zmiana i testy były
gotowe i wycofane po hold-oucie.
