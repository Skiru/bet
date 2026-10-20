# Kartki w połowach, czerwone kartki i karne drużyn / 1. połowy (2026-10-21)

Przełącznik: `epochs.FOOTBALL_CARD_HALVES_FROM_UTC` (**`None`, wyłączony**;
znacznik `card_halves_v1`). Moduł: `src/bet/sofa/football_card_halves.py`;
ocena: `metrics.calculate_cards_points_by_half`, `metrics.CARD_INCIDENT_SCOPES`
(przez `extract_metric`), `football_incidents.read_incidents` (pola
`red_cards_1h` / `penalties_1h`). Pomiar: `scripts/sofa/measure_football_card_halves.py`
(tylko odczyt, `mode=ro`); krzywe: `scripts/sofa/fit_incident_set_curves.py
--group card_halves` (kopie, przygotowane, **nie zainstalowane**).

## 1. Reguła rozliczenia (źródło)

Superbet, **Oficjalny Komunikat nr 06/2022** (strona superbet.pl/wiki
„oficjalny-komunikat-nr-06-2022-z-dnia-18-11-2024-r”, treść w wersji od
16.12.2025), sekcja 2 („kartki”, zakłady na łączną liczbę żółtych i
czerwonych kartek):

- „Żółta kartka liczona jest jako 1 kartka”, „Czerwona kartka liczona jest
  jako 2 kartki”, „Wykluczenie zawodnika z powodu 2 żółtych kartek liczone
  jest jako 3 kartki”;
- „Kartki pokazane sztabowi szkoleniowemu oraz zawodnikom na ławce
  rezerwowych nie będą brane pod uwagę”, „Kartki pokazane po ostatnim
  gwizdku nie będą brane pod uwagę”;
- „Kartki pokazane w przerwie meczu są uznawane za pokazane w drugiej
  połowie” (o ile zawodnik wznowi grę).

„1. / 2. połowa - [<drużyna>] liczba kartek” to ten sam rynek (punkty kartek
1 / 2 / 3, jak `cards_points_total`), zawężony do połowy. **Komunikat nie
mówi, jak dzieli się wykluczenie za dwie żółte, gdy pierwsza żółta padła w
innej połowie.** Przyjęta reguła (ZAŁOŻENIE): punkty każdej kartki należą do
połowy, w której ją POKAZANO – pierwsza żółta 1 w swojej połowie, druga
żółta (Sofascore: jeden incydent `yellowRed`) reszta do 3, czyli 2, w swojej.
Uzasadnienie: tylko ta reguła pozwala rozliczyć rynek 1. połowy w przerwie
(żółta z 1. połowy jest wtedy faktem; późniejsze wykluczenie nie może jej
cofnąć), a suma połów = punkty całego meczu. Połowa z `time` incydentu:
≤ 45 (z doliczonym 45+N) = 1., 46..90 (z 90+N) = 2., > 90 = dogrywka (żadna).
Kartka zawodnika bez czasu meczu (Sofascore −5) = `CARD_HALF_UNKNOWN`
(mecz bez oceny połów). Sztab, kartki anulowane (`rescinded`) i ławka
(`metrics.drop_bench_cards` w SETTLE) odpadają jak w całym meczu.

Kartka w przerwie: Sofascore nie ma znacznika przerwy; kartka czytana jest w
połowie, którą wskazuje `time` (45+N = 1. połowa). Ryzyko – patrz niżej.

Czerwone kartki (`red`, `yellowRed` zawodnika) i rzuty karne przyznane (gol
z karnego + `inGamePenalty`, strona = drużyna wykonująca) – jak w rynkach z
10-14 (`football_incidents.read_incidents`), czas regularny, tylko pełny zapis
(z substytucjami); 1. połowa = `time` ≤ 45. „Obie drużyny otrzymają czerwoną
kartkę”: obie strony ≥ 1 czerwona w czasie regularnym.

### Ile meczów reguła dotyczy (cache, mecze historii z punktami kartek)

| wielkość | wartość |
|---|---|
| zapisy incydentów meczów historii | 157 664 |
| mecze z wartością połów | 80 337 |
| `CARD_HALF_UNKNOWN` (kartka zawodnika bez czasu) | 1 605 (2,0% zapisów z kartkami) |
| suma połów = punkty meczu | 80 326 / 80 337 (11 rozbieżnych) |
| mecze z `yellowRed` | 6 769 |
| **mecze z `yellowRed`, którego pierwsza żółta była w innej połowie** | **2 508 = 3,1% meczów** |
| mecze z `yellowRed` bez wcześniejszej żółtej w zapisie | 281 |
| kartki w 45+N (1. połowa, doliczony czas) | 10 560 z 340 073 (3,1%) w 9 233 meczach |

3,1% meczów to nie „mało”: przy innej regule Superbetu (np. całe 3 pkt w
połowie wykluczenia) rozliczenie linii 2. połowy różniłoby się w części z
nich. Ryzyko otwarte do weryfikacji na rozliczonych liniach Superbetu
(pierwsze kupony z tymi rynkami) – patrz „Ryzyka”.

## 2. Model kartek połowy (pomiar walk-forward)

Mecze w kolejności czasu; book ratingu (`cards_points_for`) i każda częstość
aktualizowane po wycenie meczu. Dopasowanie r: 2025-08-01..2026-02-28
(24 729 meczów); test (out of sample): 2026-03-01..2026-10-13 (25 211 meczów).
Modele (na stronę, połowa h):

- **share**: centrum ratingu kartek całego meczu × as-of udział połowy
  rozgrywek (ściągnięty do płci, `SHARE_M` 30 meczów);
- **sample**: własna próbka połowy (10 ostatnich meczów strony, ściągnięta do
  średniej rozgrywek wagą 5);
- **team**: centrum ratingu × własny udział połowy drużyny (ściągnięty do
  udziału rozgrywek wagą 10).

r (siatka 0,5..50, 1e6): share 1. połowa 1e6 (Poisson), 2. połowa 12.

Log-loss liczby na mecz (suma dwóch stron; niżej = lepiej), różnica
model − share, bootstrap meczów 95%:

| połowa | share (strony / suma) | sample − share (suma) | team − share (suma) | Poisson − NB (suma) |
|---|---|---|---|---|
| 1. | 2,2130 / 1,5430 | +0,0144 [+0,0116, +0,0174] | +0,0045 [+0,0031, +0,0061] | 0 (r = Poisson) |
| 2. | 3,0656 / 1,9835 | +0,0138 [+0,0113, +0,0168] | +0,0026 [+0,0016, +0,0035] | +0,0104 [+0,0092, +0,0117] |

Strony: sample − share 1. połowa +0,0392 [+0,0354, +0,0438], 2. +0,0336
[+0,0296, +0,0381]. Tylko mężczyźni: ten sam znak i rząd (1. połowa sample −
share +0,0139 [+0,0108, +0,0170]). **Wybrany: share** (lepszy od obu z
przedziałem wykluczającym zero); NB 2. połowy lepszy od Poissona.

Kalibracja share na linii Superbetu (test, p ≥ 0,70, obie strony rynku):
łącznie 1. połowa p 0,8425 / realizacja 0,8403 (n 120 775 selekcji), 2.
połowa 0,8201 / 0,8118 (n 123 922). UNDER-y skalibrowane (np. 1. poł. suma
2,5 UNDER 0,8297 / 0,8314, n 21 753; 2. poł. suma 4,5 UNDER 0,8284 / 0,8302),
OVER-y zawyżone (1. poł. suma 0,5 OVER 0,7959 / 0,7565, −3,9 pp, n 19 948;
2. poł. suma 2,5 OVER 0,7502 / 0,6994) – to robota krzywej z historii (pkt 4).

## 3. Czerwone kartki i karne drużyn / 1. połowy (pomiar walk-forward)

Mecze z pełnym zapisem, test 2025-08-01..2026-10-13; log-loss model − baza
(częstość płci), bootstrap 95%; kalibracja UNDER przy p ≥ 0,70 (OVER nigdy
nie sięga 0,70).

| rynek | n | OVER realiz. | liga − baza | UNDER p / realiz. |
|---|---|---|---|---|
| red_cards_for 0,5 | 116 378 | 0,1002 | −0,00529 [−0,00602, −0,00458] | 0,8992 / 0,8999 |
| red_cards_for 1,5 | 116 378 | 0,0067 | −0,00057 [−0,00104, −0,00008] | 0,9932 / 0,9933 |
| red_cards_1h_total 0,5 | 58 189 | 0,0540 | −0,00243 [−0,00341, −0,00142] | 0,9458 / 0,9460 |
| red_cards_1h_for 0,5 | 116 378 | 0,0279 | −0,00138 [−0,00188, −0,00083] | 0,9719 / 0,9721 |
| penalties_for 0,5 | 116 378 | 0,1322 | −0,00465 [−0,00516, −0,00409] | 0,8676 / 0,8678 |
| penalties_1h_total 0,5 | 58 189 | 0,1130 | −0,00268 [−0,00359, −0,00179] | 0,8881 / 0,8870 |
| penalties_1h_for 0,5 | 116 378 | 0,0586 | −0,00144 [−0,00189, −0,00100] | 0,9420 / 0,9414 |
| both_red_cards | 58 189 | 0,0161 | −0,00162 [−0,00255, −0,00056] | 0,9838 / 0,9839 |

Warianty: częstość ligi z podziałem gospodarz / gość – penalties_for
−0,00512 (o 0,0005 lepiej od ligi), red_cards_for −0,00496 (gorzej), reszta
gorzej; częstość drużyny (TEAM_M 20) – gorzej od ligi wszędzie (red_cards_1h_for
i penalties_1h_for gorzej od bazy). both_red jako iloczyn stron: log-loss
−0,00476, ale zaniżona realizacja (p 0,9883 / 0,9839, −0,43 pp – zależność
stron). **Wybrana: częstość ligi** (jak rynki z 10-14), jedna reguła dla
wszystkich; podział domowy dla penalties_for zmierzony, nieużyty (różnica w
czwartym miejscu).

## 4. Krzywe z historii (przygotowane, NIE zainstalowane)

`data/refit_card_halves_2026-10-21/card_halves/{curves.json,rows.csv,gate_report.md}`
(kopia incydentów `.../football_incidents/incidents.db` + pickle historii);
replay estymatorem SHEET (book dnia: shared link, cup strength, rated scope),
wiersze od 2025-08-01, 3 116 292 wiersze. Bramka jednostronna (trening przed
2026-09-01, holdout 09-01..10-13, krzywa ≥ 0,70: realizacja − krzywa ≥ −2 pp
przy n ≥ 300).

PASS (klucz główny): `cards_points_1h_for|UNDER` (n 9 521, −0,26 pp),
`cards_points_1h_total|OVER` (2 986, +2,36), `cards_points_1h_total|UNDER`
(8 013, −0,22), `cards_points_2h_for|OVER` (7 534, +1,66),
`cards_points_2h_for|UNDER` (411, +2,56), `cards_points_2h_total|OVER`
(6 567, +1,80), `cards_points_2h_total|UNDER` (6 324, +0,07),
`handicap_cards_points_1h|OVER` (4 250, −1,00), `penalties_1h_for|UNDER`
(8 392, +0,46), `penalties_1h_total|UNDER` (5 585, +1,19),
`penalties_for|UNDER` (11 194, +1,04), `red_cards_1h_for|UNDER` (954, +0,49),
`red_cards_1h_total|UNDER` (2 838, +1,09), `red_cards_for|UNDER` (11 180,
+0,24). Klasa `women:` PASS: `cards_points_1h_for|UNDER`,
`cards_points_2h_total|UNDER`, `handicap_cards_points_1h|OVER`,
`penalties_1h_for|UNDER`, `penalties_1h_total|UNDER`, `penalties_for|UNDER`.

FAIL: `cards_points_1h_for|OVER` (n 150, −3,98 pp), `both_red_cards|UNDER`
(n 279), wszystkie OVER czerwonych / karnych i `most_*`,
`handicap_cards_points_2h` (brak selekcji ≥ 0,70).

Instalacja (`install_new_market_curves.py`) wymaga zgody operatora; bez niej
nowe klucze czytają tylko własne linie Superbetu – `NO_LINE_EVIDENCE` na
start, nic się nie drukuje.

## 5. E2E (oferty zapisane 10-18..10-20)

Skrypt: `scratchpad/e2e_card_halves.py` (OFFER `classify_odd` na zapisanych
cenach + SHEET `process_fixture` z przełącznikiem wył. / wł.; baza tylko do
odczytu, nic nie zapisano do `runs/`).

| dzień | mecze porównane | wył. == wł. minus nowe | nowe wiersze | drukowałoby się (krzywa, ≥ 0,70, × kurs ≥ 0,90) |
|---|---|---|---|---|
| 10-18 | 996 | 996 | 1 700 | 136 |
| 10-19 | 172 | 172 | 384 | 32 |
| 10-20 | 177 | 177 | 628 | 46 |

- Przy wyłączonym przełączniku `classify_odd` mapuje 0 nowych kursów, a SHEET
  jest równy SHEET-owi wł. po odjęciu nowych wierszy (każdy mecz).
- `red_cards_1h_for` i `both_red_cards` dają głównie `OUTSIDE_MODEL_RESOLUTION`
  (p powyżej sufitu modelu), tak jak SHEET robi dla każdego takiego p.
- "Drukowałoby się" to przybliżenie: tylko krzywa, bez korekty linii Superbetu,
  bez widełek 15% i bez odczytów. Bez instalacji krzywych drukuje się 0
  (`NO_LINE_EVIDENCE`).

### Rozliczenie, kontrola sensu (10-14..10-19, zapisane oferty)

Oceniono 6 731 wierszy (3 278 WIN / 3 453 LOSS) tym samym `extract_metric` /
`_settle_derived`, którego używa SETTLE. Odmowy z nazwą, np.
`CARD_HALF_UNKNOWN` (kartka bez minuty), `ZERO_NOT_RECORDED`,
`EVENT_NOT_FINISHED` (dogrywka), `STAT_KEY_ABSENT`, `CARDS_NOT_RECORDED`.

Kalibracja surowego p (średnie p / trafienia, wszystkie wiersze): połowy kartek
w granicy 1–5 pp; `red_cards_for` OVER 0,098 / 0,067, `red_cards_1h_total`
OVER 0,074 / 0,038 (OVER przeszacowany, zgodnie z historią).

Wiersze, które drukowałyby się z krzywej: 579 ocenionych, 469 trafionych
(81,0%) przy średniej pewności 0,827 i średnim 1/kurs 0,833. Różnica
trafień od pewności −1,7 pp [−5,0, +1,5] (bootstrap po wierszach, 95%),
−16,7 j. na 579 (−2,9%). Sześć dni, mała próba: to sprawdzenie sensu, nie
pomiar przewagi. Kurs i realizacja są zbliżone, czyli to samo co na pozostałych
rynkach.

## Ryzyka otwarte

- Podział wykluczenia za dwie żółte między połowy to założenie (3,1% meczów
  ma `yellowRed` z pierwszą żółtą w drugiej połowie). Do sprawdzenia na
  pierwszych rozliczonych liniach Superbetu: mecz z takim wykluczeniem i linią
  2. połowy na granicy.
- Kartka w przerwie: Superbet liczy ją w 2. połowie, Sofascore nie ma
  znacznika – czytamy ją wg `time` (45+N → 1. połowa). Kartki 45+N to 3,1%
  kartek; jaka ich część to przerwa – nieznane (podejrzenie: mała).
- `SHARE_M` 30, `BASE_M` 30 – wagi wybrane, nie dopasowane
  (`UNFITTED_CONSTANTS`).
- `rebuild_plan` nie zna tego przełącznika (włączenie w zbudowany dzień nie
  wymusi ponownego OFFER) – plan: włączenie od 00:00Z nowego dnia.
- SHEET przy włączonym czyta incydenty historii drugi raz (osobno od rynków
  z 10-14): ~30-60 s.
