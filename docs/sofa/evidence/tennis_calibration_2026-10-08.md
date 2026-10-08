# Tenis, metoda kalibracji i przedziały niepewności — pomiar 2026-10-08

Ścieżka A4. Pomiar tylko do odczytu (`scripts/sofa/measure_tennis_calibration.py`,
test: `tests/sofa/test_measure_tennis_calibration.py`, wyniki:
`docs/sofa/evidence/tennis_calibration_2026-10-08.json`). Żaden config, krzywa ani
stała nie została zmieniona; nic nie wymaga decyzji przed refitem.

## Metoda (wspólna)
- Źródło wierszy: **kopia** bazy `data/refit_2026-10-08/sofa_replay.db` otwarta
  `mode=ro` (live `data/sofa.db` nietknięta). Wiersze `run_date = 'cache-calibration'`
  (replay historii, nie nasze rozliczone dni), p >= 0,60. Tenis 4,03 mln wierszy,
  piłka 19,9 mln; historia od ok. 2025-05 (tenis) / 2024-05 (piłka).
- Podział czasowy: **trening do 2026-04-01, test 2026-04-01..2026-10-07**
  (6 miesięcy, > 2 miesiące wymagane). Tenis: 2,04 mln wierszy testowych w 52,5 tys.
  meczów; piłka: 6,6 mln w 175 tys. meczów.
- Przedziały: bootstrap **po meczach** (Poisson, 300–1000 prób), różnice sparowane.
  „d" = metoda minus punkt odniesienia w nat (ujemne = lepsza), zapisane w jednostkach
  1e-4 nat tam, gdzie podano `e-4`.
- Zastrzeżenie wspólne: wiersze replaya są wyceniane estymatorem SHEET z
  współczynnikami ratingu dopasowanymi z podglądem przyszłości (8 parametrów na tier,
  patrz `AsOfRating`); linie to siatka połówkowa, nie drabina Superbetu.

## (b) Metoda kalibracji: izotoniczna / beta (Kull 2017) / gładki monotoniczny spline vs koszyki

Krzywa produkcyjna (`fit_confidence.py`): 11 stałych koszyków `EDGES`, realised na
koszyk, per `market|kierunek` (>= 400 wierszy w koszyku, inaczej pula sportu);
CONFIDENCE czyta **dolną granicę Wilsona 95%** koszyka (`Calibration.realised`).

| test 2026-04..10, wiersze p >= 0,60 | log-loss koszyki | beta | spline | izotoniczna | ECE koszyki / beta |
|---|---|---|---|---|---|
| tenis (14 rodzin) | 0,49288 | −7,5e-4 [−8,1; −7,0] | −7,1e-4 [−7,6; −6,5] | −6,6e-4 [−7,1; −6,0] | 0,0017 / 0,0018 |
| piłka (53 rodziny) | 0,49343 | −7,5e-4 [−7,8; −7,2] | −8,0e-4 [−8,2; −7,7] | −7,7e-4 [−8,0; −7,4] | 0,0031 / 0,0034 |

- Zysk to ok. 0,15% log-lossu; poprawia 13/14 (tenis) i 38–40/40 (piłka, 40 największych
  rodzin) rodzin, pogarsza 0–1. **ECE nie jest lepsze** (0,0017–0,0018 tenis, 0,0031 vs
  0,0034 piłka).
- Wiarygodność 0,70–0,95 (p surowe): różnica log-lossu beta −3,9e-4 (tenis) / −3,2e-4
  (piłka); luka realised − confidence w zbiorze drukowanym (conf >= 0,70): koszyki
  tenis −0,0014 [−0,0027; −0,0004], piłka −0,0037 [−0,0043; −0,0032]; beta/spline/izotoniczna
  −0,0016..−0,0040 (nie lepiej). **Dolna granica Wilsona, którą CONFIDENCE drukuje**, daje
  lukę +0,0041 [+0,0028; +0,0052] (tenis, konserwatywna) i +0,0007 [+0,0002; +0,0012]
  (piłka) — najlepiej skalibrowany zbiór drukowany jest w produkcji; metoda gładka
  zwraca estymatę punktową i wymagałaby własnej dolnej granicy.
- Dryf: log-loss koszyków piłki 0,4901 (pierwsza połowa testu) -> 0,4967 (druga);
  każda metoda dziedziczy ten dryf (−0,4 pp w zbiorze drukowanym).
- **Reżim cienkich danych** (rodzina dopasowana na próbce 0,5% / 2% meczów treningu;
  koszyk wraca do puli, gdy < 400 wierszy; mediana 890 / 3350 wierszy w tenisie,
  590 / 2400 w piłce): przy 0,5% koszyki+pula wygrywają z beta o +23e-4 (tenis),
  +6e-4 (piłka), a izotoniczna jest gorsza o +115e-4 / +79e-4; przy 2% beta wygrywa
  o −11e-4 [−12; −10] (tenis) i −17e-4 [−18; −17] (piłka). Przecięcie leży
  ok. 1,5–2,5 tys. wierszy na rodzinę. Beta *z priorem z puli* nie była mierzona.

**Werdykt (b): NIE (nie zamieniać).** Zysk jest realny statystycznie, ale rzędu
7e-4 nat i bez poprawy ECE ani wiarygodności w okolicy 0,70–0,95. INCONCLUSIVE tylko
dla beta jako zastępstwa koszyków cienkich (K13/K13b) — wymaga wariantu z priorem z puli.

## (c) Dolna granica p (przedział) tylko obniżająca pewność

Przybliżenie: p_lo = Φ(Φ⁻¹(p) − z·se/s), se = sd/√n · n/(n+K_CENTRE) (błąd
standardowy skurczonego centrum; replay przechowuje tylko `sample_sd`, więc
s = max(sd; 0,5) — przybliżenie). **k/n własnej próbki nie jest w wierszach replaya**,
więc wariantu „Beta(k+1, n−k+1) łączony z p modelu" nie zmierzono (sugestia, nie
pomiar). Reguła „A" odtwarza trzy mechanizmy: koszyk rodziny (lo95), K13 (pula
ograniczona cienkim koszykiem rodziny), K13b (najbliższy własny koszyk poniżej).

- Próbki replaya to prawie wyłącznie n = 8–10 i 15–20; **cienkie koszyki dotykają
  0,02% (piłka) i 0,07% (tenis) wierszy testu** — K13/K13b prawie nie działa w replayu.
- Luka realised − confidence w zbiorze drukowanym, reguła A (bez przedziału):
  tenis +0,0042 (n10 +0,0032 [+0,0020; +0,0042], n >= 20 +0,0071 [+0,0052; +0,0089]);
  piłka +0,0005 (n8–9 +0,0009 [−0,0024; +0,0048], n10 0,0000 [−0,0006; +0,0006],
  n11–19 +0,0025 [+0,0012; +0,0040], n >= 20 +0,0008). **Nie ma zależności luki od
  rozmiaru próbki, którą przedział mógłby naprawić.**
- Z przedziałem (min(A, krzywa przy p_lo)), z = 0,5 / 1,0 / 1,645: luka rośnie do
  +0,017 / +0,034 / +0,056 (piłka) i +0,022 / +0,039 / +0,061 (tenis) — jednolite
  zaniżenie. Odrzucone nogi mają realised równe temu, co krzywa im przypisywała
  (z = 1: 0,733 vs 0,733 piłka; 0,730 vs 0,727 tenis), czyli przedział zabiera nogi
  poprawnie wycenione. Powód: se/s zależy tylko od n i dla n ≈ 10 jest stałe
  (0,149–0,158) — terciele po se/s są zdegenerowane.

**Werdykt (c): NIE.** Na replayu n >= 8 przedział = stałe przesunięcie p. INCONCLUSIVE
dla żywych nóg z n < 8 (kobiety/początek sezonu): w replayu < 50 takich nóg w zbiorze
drukowanym.

## (a) Silnik tenisa

Panel: 243 025 meczów singla (`load_history`), 152 287 wierszy z oboma graczami >= 10
meczów ratingu, best-of-3; trening 103 465, test 48 645 (2026-04-01..10-07). Rating
V0 = produkcyjne 8 cech, współczynniki per tier dopasowane na treningu. Wiersze zdarzeń:
42 zdarzenia na mecz (games_total 16,5..25,5; games_won_for obu stron 6,5..13,5;
handicap_games margin > −6,5..6,5; most_games; sets_total 3 sety), tylko p odniesienia
w (0,05; 0,95); „p70" = strona, którą obstawiałaby kupon (>= 0,70). Czytanie z
sąsiadów jak w produkcji (600, tabela bez match-tiebreaków dla CH/TOUR).

### Powierzchnia, tier, cienkie ratingi (prawdopodobieństwo zwycięstwa, test)
| wariant | log-loss | d vs V0 [95%] |
|---|---|---|
| V0 produkcja | 0,56815 | — |
| V1 bez powierzchni | 0,56915 | +10,1e-4 [+6,5; +13,8] (powierzchnia coś daje, głównie TOUR: +78e-4) |
| V2 powierzchnia 3-kl. hierarchiczna (odchylenie od ratingu ogólnego, κ=1) | 0,56805 | −1,0e-4 [−4,4; +2,1] |
| V3 powierzchnia 4-kl. (hala osobno), κ=1 | 0,56787 | −2,7e-4 [−6,1; +0,4] |
| V4 produkcja + odchylenie 4-kl. | 0,56761 | −5,3e-4 [−8,0; −2,5] |
| V5 start ratingu wg tieru pierwszego meczu | 0,56711 | **−10,4e-4 [−12,6; −8,3]** (ITF −9,7; CH −12,6; TOUR −12,5) |
| V6 skurcz cienkich (lp/(1+15/nmin)) | 0,56794 | −2,1e-4 [−3,9; −0,6] |
| V7 + różnica serwis/return w p wygranej | 0,56787 | −2,8e-4 [−5,9; 0,0] |
| V8 współczynniki tier x płeć | 0,56782 | −3,3e-4 [−5,6; −1,0] |

Rynki (sąsiedzi z tego samego wariantu, d vs V0, 1e-4 nat, [95%]): V5 daje
games_total −8,1 [−11,6; −5,0], games_won_for −9,8 [−12,7; −7,2], handicap −9,0
[−12,3; −5,1], most_games −7,7 [−12,7; −1,6], sets −4,9 [−9,5; 0,0], w obu połowach
okna (H1 i H2 ujemne we wszystkich rodzinach). V4 (powierzchnia 4-kl.): handicap −5,0
[−8,9; −0,5], most −6,0 [−11,8; −0,3], games_total −1,6 (ns). Pozostałe warianty
powierzchni i V6/V7 w granicach szumu lub gorsze (V7 games_total p70 +5,3 [+1,6; +9,0]).
Średni zysk V5 to ok. 0,15–0,2% log-lossu: **mały, spójny, niedramatyczny**.

### Gdzie rating jest cienki
(`coverage_test_window`, `thin`.) Odsetek meczów, w których oboje gracze mają >= 10
meczów (= jest forecast): ITF mężczyźni 70,4%, ITF kobiety 74,7%, CH 96,7% / 97,3%
(M/K), TOUR 96,9% / 96,0%. Mediana min(n) graczy: ITF M 35, ITF K 44, CH 102–103,
TOUR 100–113; udział min(n) < 20: ITF 23% / 20%, CH 1–2%, TOUR < 1%. Log-loss p
wygranej: ITF 0,55–0,56, CH 0,60–0,61, TOUR 0,60–0,62 (ITF „łatwiejszy" przez
nierówne pary, nie przez lepszy rating). Cienki obszar to ITF/UTR (30% meczów bez
forecastu) — tam hierarchiczny start wg tieru (V5) daje −9,7e-4.

### Neighbourhood: tabela sąsiadów per tier (NOWE, nieoczekiwane)
Ten sam p (V0), tabela sąsiadów zawężona do grupy meczu (test, d vs V0 w 1e-4 nat):

| zawężenie | games_total | games_won_for | handicap | most_games | sets_total |
|---|---|---|---|---|---|
| tier (ITF/CH/TOUR) | −68,5 [−75,9; −62,4] | −31,5 [−34,8; −28,1] | −7,8 [−10,5; −5,2] | +1,1 (ns) | −22,5 [−28,1; −16,5] |
| tier x płeć | −81,3 [−89,9; −73,9] | −37,3 [−41,8; −33,4] | −16,3 [−20,2; −12,8] | +1,4 (ns) | −22,6 [−28,6; −14,9] |
| tier x powierzchnia | −66,6 | −29,2 | −3,9 (ns) | +8,0 (gorzej) | −20,4 |

Obie połowy testu zgodne (games_total −68 / −69). Przyczyna: tabela jest zdominowana
przez ITF; ten sam p daje w TOUR/CH więcej gemów. Obciążenie drabiny games_total
(średnia pred − realised): V0 ITF +5,6 pp, CH −6,7 pp, TOUR −7,9 pp; zawężone
per tier +3,1 / −1,3 / −1,0 pp. **Zysk przeżywa kalibrację** (krzywa koszykowa
dopasowana na pierwszej połowie testu, wspólna dla tierów jak produkcyjna, ocena na
drugiej): games_total −64,2 [−73,7; −55,6] (tier), −74,9 [−86,9; −63,9] (tier x płeć),
games_won_for −28,0 / −30,8, handicap −9,9 / −16,6, sets −10,1 / −9,1.
**Sprzeczność z komentarzem** w `tennis_rating.py` (wiersze 49–51: „Scoping the
neighbours by tier or by surface was measured and did not help (Brier 0.2372 / 0.2377
/ 0.2378)") — tamten pomiar to 5 dni i 251 meczów; ten: 48,6 tys. meczów, 6 miesięcy,
log-loss na liniach. Z CLAUDE.md sprzeczności nie ma (tabela sąsiadów nie jest tam
opisana jako ustalona).

### Rozkład serwis/return (hold i break osobno, Klaassen–Magnus)
Implementacja: oceny serwisu `s_i` i returnu `r_j` online (SGD na punktach z
`/statistics`, 71 652 meczów z kompletną statystyką; dobór `m0=8`, floor 0,06 na
3 miesiącach przed cięciem), P(punkt na serwisie) = σ(μ + s_i − r_j), gra -> tiebreak
(7 pkt, różnica 2) -> set -> mecz bo3 (niezależne, identyczne sety, pierwszy
serwujący uśredniony). Testowane na TOUR+CH, gracze z >= 6 meczów statystyk,
10 830 meczów:

| model | games_total | games_won_for | handicap | most | sets |
|---|---|---|---|---|---|
| KM czysty (tylko oceny punktowe) vs V0 | +96 [+37; +164] | +383 [+332; +440] | +553 | +692 | +126 |
| KM hybryda (p zwycięstwa z Elo, poziom serwisu z ocen) vs V0 | +111 [+53; +174] | +58 [+31; +87] | +25 [+10; +41] | −10 [−20; 0] | +117 [+44; +177] |
| 50/50 V0 + KM hybryda vs V0 | −168 [−195; −138] | −78 [−91; −63] | −49 [−57; −43] | −8 | −81 |
| 50/50 V0 + KM bez ocen graczy (poziom ogólny) vs V0 | −151 [−174; −124] | −69 | −41 | −8 | −81 |

Duży zysk z mieszanki to w większości **kasowanie obciążenia tabeli sąsiadów** (V0 pred
− realised −7..−9 pp na TOUR/CH, KM +5..+13 pp), nie informacja o serwisie: wersja bez
ocen graczy daje prawie to samo. Na tabeli zawężonej per tier x płeć mieszanka 50/50
nie pomaga (games_total +19,7 [+1,7; +42,2]); waga 0,25 daje −15,6 [−24,6; −4,3]
(bez ocen graczy −8,6 [−17,2; +1,5]) — waga wybrana po fakcie, dwie wagi sprawdzone.
Korelacja siły serwisu (suma `s−r`) z resztą gemów ponad p Elo: 0,11 (n=10 830) —
jest sygnał, ale niewielki.

**Werdykt (a):**
- Rozkład serwis/return jako *zastępstwo*: **NIE** (gorzej o 0,01–0,07 nat).
  Jako 25% domieszka: INCONCLUSIVE (−15,6e-4 po fakcie; wymaga zarejestrowanego testu).
- Powierzchnia hierarchiczna 3/4-kl.: **NIE** (CI obejmuje 0 poza V4: −5,3e-4).
- Tier-init (V5): drobny, spójny zysk (−10e-4) — kandydat do następnego refitu.
- **Tabela sąsiadów per tier (x płeć): TAK, największy zmierzony efekt** (−68..−81e-4
  games_total, −31..−37e-4 games_won_for), przeżywa kalibrację.

## Konsekwencje wdrożeniowe (nic nie wdrożone)
- Tabela per tier: `tennis_rating.TennisRatingModel.__init__/_neighbours/forecast`,
  `build_model`, `AsOfRating._add` / `TennisRatingModel.insert` (replay), nowy przełącznik
  w `bet.sofa.epochs` (zmienia, co się drukuje). **Wymaga refitu krzywych tenisa**
  (replay `calibrate_from_cache.py` z nowym estymatorem) i odświeżenia line evidence;
  decyzja operatora (CLAUDE.md, „Changing the pipeline" 3–4).
- V5 (start wg tieru): `RatingBook.__init__/update`, ponowny `fit_tennis_rating.py`
  (nowa cecha `lp_t` w `FEATURES`) — też nowy epoch + refit.
- (b), (c): bez zmian w kodzie.

## Czego nie zmierzono
Cen Superbetu (brak historii), k/n próbki, żywej drabiny linii; wariantu beta z priorem
z puli; CS2 / hokej / koszykówka; pięciosetowych meczów; dokładnej reguły K13/K13b na
żywych nogach (replay prawie nie trafia w cienkie koszyki); wpływu przełączenia
tabeli na liczbę i skład nóg drukowanych (wymaga pełnego replaya).
