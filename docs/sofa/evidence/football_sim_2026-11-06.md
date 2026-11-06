# Piłka nożna: symulator minuta po minucie - pomiar 2026-11-06

Prośba operatora 2026-11-06 ("ja bym widział właśnie taki symulator minuta po
minucie"). Pomiar tylko do odczytu: żaden etap pipeline'u nie czyta modułu,
żaden przełącznik w `bet.sofa.epochs`, żaden plik `config/` nie zmieniony,
żaden wiersz bazy nie zapisany, sieć nie pytana (tylko cache). Wzorzec: model
punktowy tenisa z 11-05 (`tennis_point_model_2026-11-05.md`).

Kod: `src/bet/sofa/football_sim.py` (model), `scripts/sofa/measure_football_sim.py`
(pomiar), `tests/sofa/test_football_sim.py`. Dane i logi:
`data/football_sim_2026-11-06/`.

## 0. Reguły zapisane PRZED oceną (pre-rejestracja)

Ta sekcja została zapisana w pliku po dopasowaniu stałych na historii sprzed
2026-06-01, a **przed** policzeniem czegokolwiek na historii po tej dacie, na
liniach Superbetu i na cenach rynków ścieżki. Kod modelu i skryptu jest od tej
chwili zamrożony (wyjątek: błąd wykryty na dev - opisany jak w tenisie).

**Model** (szczegóły w sekcji 1): intensywność goli strony = centrum goli
czystego ratingu (`football_rating`, te same flagi co SHEET na 2026-11-06) / 90
x profil czasu (8 przedziałów: 0-14, 15-29, 30-44, doliczony czas - w każdej
połowie) x mnożniki stanu meczu (prowadzenie / remis / strata 1 i 2+ bramkami,
osobno od 71. minuty; czerwona kartka własna / rywala). Czerwone kartki -
własny proces (centrum kartek strony / 90 x profil x stan). Doliczony czas -
rozkład z historii. Liczniki per połowa (rożne, kartki, faule, strzały,
celne) - log-liniowo od centrum połowy z udziałem połowy spędzonym w stanie i
golami w połowie; rozproszenie NB + wspólna słabość (frailty) strony między
połowami i skorelowana między rynkami. 4 000 symulacji na mecz, ziarno = id.

**Okna (rozłączne, w kolejności czasu):**

- dopasowanie stałych: mecze 2025-01-01 .. 2026-05-31 (rating rozgrzany na
  całej wcześniejszej historii, prognoza każdego meczu z ratingu sprzed niego);
- wybór dwóch hiperparametrów (wariancja słabości goli z {0, 0.03, 0.06, 0.10},
  przeskalowanie średniej do centrum tak / nie): dopasowanie na 2025-01-01 ..
  2026-02-28, ocena na 3 000 losowych meczach 2026-03-01 .. 05-31, kryterium
  log-wiarygodność dokładnego wyniku po 90 min + do przerwy; potem stałe
  dopasowane na nowo na całym oknie z wybranymi hiperparametrami;
- **historia (ocena):** 2026-06-01 .. 2026-09-17, do 6 000 losowych meczów z
  centrum goli (ziarno 5);
- **Superbet:** wiersze rozliczone `sofa_settled_row` (run_date 2026-10-07 ..
  11-05; rynki, które SHEET wycenia) oraz ceny rynków, których OFFER nie czyta
  (`unmapped_prices`, 2026-10-14 .. 11-05), rozliczone przez nas z wyniku w
  cache. **Dev = dni <= 2026-10-24, hold-out = 2026-10-25 .. 11-05, liczony
  raz**, po zamrożeniu kodu. Żadna stała nie jest wybierana na liniach
  Superbetu; dev służy wyłącznie do wyłapania błędów (mapowanie stron, nazwy
  rynków, rozliczenie).

**Cena bez marży:** proporcjonalnie w obrębie pełnego, rozłącznego zbioru
wyników: para OVER / UNDER tego samego szczebla z `04_offer.json` dnia (suma
odwrotności w [1.00, 1.30]); rynki ścieżki - wszystkie wyniki rynku z jednego
(ostatniego przed meczem) zrzutu, zbiór musi być kompletny (np. 9 wyników
HT/FT), suma odwrotności w [1.00, 1.30] dla dwóch wyników, [1.00, 1.60] dla
więcej. Dokładny wynik (lista Superbetu jest niepełna) - tylko informacyjnie,
bez werdyktu. Linie całkowite (zwrot przy remisie linii) pomijane.

**Wiersze i przedziały:** para OVER / UNDER = jeden wiersz (OVER, albo UNDER
gdy OVER nie był rozliczony); rynek wielowynikowy = wiersz na każdy wynik.
Brier i log-loss na wierszach; przedziały 95% z bootstrapu po meczach (2 000
losowań, wszystkie wiersze meczu razem). Nogi do kalibracji: oba kierunki
pary, każdy wynik rynku wielowynikowego.

**Rodziny** (każda osobno):

- (a) ścieżka: a1 HT/FT (`1. połowa/mecz`); a2 wynik połowy (`1.połowa -
  1X2`, `2.połowa - 1X2`); a3 połowa z większą liczbą goli; a4 gol w obu
  połowach (drużyna strzeli w obu połowach; obie strzelą 1./2. połowa; obie
  strzelą w przynajmniej jednej połowie); a5 pierwszy / ostatni gol (SHEET
  `first_goal`, `1. gol (przedziały 15-minutowe)`, `1. połowa - 1. gol`,
  `Ostatni gol`); a6 gole w połowach (SHEET `goals_1h/2h_total/for`,
  `both_over_goals_1h/2h`, nieczytane `1.połowa liczba goli & 2.połowa liczba
  goli`);
- (c) kontrola - rynki, które SHEET już wycenia: c1 1X2 / podwójna szansa /
  DNB; c2 `goals_total`; c3 `goals_for`; c4 kombinacje wynik / gole (BTTS,
  `result_or_*`, `btts_or_over`, `dc_and_*`, `result_handicap`); c5 rożne
  (wszystkie); c6 kartki (`cards_points*`, `red_cards*`); c7 faule; c8 strzały
  i celne;
- x (informacyjnie, nieczytane przez SHEET): parzystość goli, dokładna liczba
  goli, dokładny wynik;
- (b) pary nóg jednego meczu (buildery): 10 typów par z rozliczonych wierszy
  Superbetu (gole + rożne, gole + kartki, wynik + gole, wynik + kartki, wynik
  + rożne, BTTS + gole, gole drużyny + rożne tej samej drużyny, rożne +
  kartki, gole 1. + 2. połowy, celne + gole); każda noga = wiersz tego rynku
  z `p_central` SHEET najbliższym 0.70 (typowa noga buildera, wybór niezależny
  od wyniku). Porównanie: p łączne z symulacji vs iloczyn marginesów z
  symulacji vs iloczyn `p_central` SHEET vs k/n `dossier.joint_history`
  (ostatnie 10 meczów każdej strony sprzed meczu, odtworzone z historii; tylko
  przy n >= 5). Ceny buildera nie ma (Superbet nie publikuje, my nie
  zapisujemy) - porównanie z ceną niemożliwe.

**Kryterium główne (operator: "co najmniej tak dobry jak Superbet; marża
zaakceptowana") na hold-oucie, per rodzina:**

1. **nie-gorszy od ceny:** górna granica przedziału Brier(symulator) -
   Brier(cena bez marży) <= 1% Briera ceny w tej rodzinie (= 0.002 przy
   Brierze 0.20, margines tenisa z 11-05; dla rynków wielowynikowych Brier
   wiersza jest mniejszy, więc margines względny);
2. **brak nad-obietnicy przy >= 0.70:** nogi z p symulatora >= 0.70: górna
   granica przedziału (trafione - deklarowane) >= 0; mniej niż 30 nóg = "za
   mało nóg".

Werdykt "co najmniej tak dobry jak Superbet" = 1 i 2. Raportowane obok (nie
kryterium): trafione - deklarowane przy 0.60-0.70; "lepszy od ceny" (górna
granica < 0); ROI nóg z p >= 0.70 i x = p x kurs >= 0.90 przed i po podatku
12% (zwrot 0.88 x kurs).

**Kryterium drugie - wobec obecnego SHEET (`p_central`):** Brier(symulator) -
Brier(obecny): "lepszy" gdy górna granica < 0, "gorszy" gdy dolna > 0, inaczej
"remis". Dla kontroli (c) warunek: **nie gorszy** od obecnego.

**Historia (bez cen):** (c) symulator vs odtworzony obecny estymator
(`sofa_settled_row`, run_date `cache-calibration`, `p_central`) na rynkach
`goals_total`, `goals_for`, `corners_total`, `corners_for`,
`cards_points_total`, `fouls_total`, `shots_total`, `shots_on_target_total`:
jedna linia na (mecz, rynek, strona) - ta z `p_central` najbliżej 0.5 (reguła
tenisa); 1X2 i powyżej 2.5 gola vs wzór SHEET (niezależne NB na czystym
ratingu, r z `config/sofa_football_result.json`); (a) ścieżka vs "niezależne
połowy" - NB per strona i połowa na centrach ratingu `goals_1h_for` /
`goals_2h_for` z tym samym r, gole równomiernie w połowie (to, co dzisiejsze
klocki SHEET dają dla rynku ścieżki).

**(b) kryterium:** p łączne lepsze od iloczynu marginesów, gdy górna granica
Brier(łączne) - Brier(iloczyn) < 0; to samo wobec k/n.

Werdykt per rodzina słowami: "co najmniej tak dobry jak Superbet" (tak / nie),
"wobec obecnego" (lepszy / remis / gorszy), "nad-obietnica >= 0.70" (nie /
tak / za mało nóg).

---

*Wszystko poniżej napisane po pomiarze.*

Kod zamrożony przed oceną: `data/football_sim_2026-11-06/freeze_v1.sha256`
(po dopasowaniu); po poprawkach z dev (sekcja 4) `freeze_v2.sha256`
(`measure_football_sim.py` a447524c..., `football_sim.py` 05e62c07... -
model bez zmian, `params.json` bc756bfd... bez zmian). Hold-out policzony raz,
na v2. Po hold-oucie zmieniono w skrypcie tylko plan zapytania odtworzenia
historii (`+run_date`, ten sam wynik zapytania, bez tego etap historii
skanował całą tabelę na każdą paczkę meczów) i dodano test.

## 1. Model i dane

**Literatura.** Dixon & Coles (1997): niezależne Poissony na sile ataku i
obrony z poprawką niskich wyników; Dixon & Robinson (1998): gole jako proces
narodzin w czasie, intensywność zależna od minuty i bieżącego wyniku
(drużyna prowadząca / przegrywająca zmienia tempo); Karlis & Ntzoufras (2003):
dwuwymiarowy Poisson - korelacja goli stron (tu: wspólna słabość meczu,
`goal_frailty`); efekty stanu w grze (in-play): czerwona kartka obniża
intensywność własną i podnosi rywala (Vecer, Kopriva & Ichiba 2009;
Titman et al. 2015 - wspólny model goli i kartek), przegrywający bije więcej
rożnych i strzałów, prowadzący mniej ("score effects").

**Model** (`src/bet/sofa/football_sim.py`):

- intensywność gola strony w minucie = centrum goli strony z czystego ratingu
  (`football_rating.RatingBook`, flagi SHEET na 2026-11-06:
  link_shared, siła pucharowa, awarded wyłączone, `rated_scope=MARKETS`,
  form_table wyłączone; walk-forward - prognoza każdego meczu sprzed niego)
  / 90 x exp(profil 8 przedziałów czasu) x exp(stan);
- stan (z perspektywy strony): strata 1, strata 2+, prowadzenie 1,
  prowadzenie 2+, osobno strata / prowadzenie od 71. minuty, własna / rywala
  czerwona kartka;
- czerwone kartki: proces strony z przesunięciem = centrum punktów kartek /
  90, profil czasu, stan (strata / prowadzenie / końcówka);
- doliczony czas: rozkład z historii (ogłoszony `injuryTime` albo ostatni
  incydent `addedTime`, maks.), osobno dla połów;
- liczniki per połowa (rożne, punkty kartek bez czerwonych, faule, strzały,
  celne): log-liniowo na centrum połowy (rożne - centra połów z ratingu;
  faule / strzały / celne / kartki - centrum meczu / 2, wyraz wolny połowy
  uczy podziału) z udziałem połowy spędzonym na stracie / prowadzeniu / z
  czerwoną, golami strzelonymi / straconymi w połowie; rozproszenie NB per
  połowa + skorelowana log-normalna słabość (strona x rynek) z momentów;
  punkty kartek = model bez wyrzuceń + 2 za każdą symulowaną czerwoną;
- 4 000 symulacji na mecz, ziarno = id zdarzenia; wybrane hiperparametry
  (walidacja 03-05.2026, sekcja 0): `goal_frailty` 0.03, bez przeskalowania
  średniej (przeskalowanie zaniżało gole: 2.81 vs 2.90 obserwowane; bez niego
  2.88).

**Dane (cache, bez sieci, bez backfillu):** 950 159 meczów w historii
ratingu; 192 696 z listą incydentów, 183 446 z czasami goli (strona
odczytana z bieżącego wyniku, samobóje też), 96 882 z pełnym zapisem
(czerwone kartki), ogłoszony doliczony czas 46 024 (1. poł.) / 49 034 (2.);
połowy: rożne 37 131, punkty kartek 98 442, strzały 37 087, celne 36 599,
faule 25 358 (od 2025-10). Przebiegu meczu (graph / momentum) w cache brak;
shotmap tylko 24 633 mecze - nieużyty. Pokrycie wystarcza; backfill nie był
potrzebny.

## 2. Dopasowane efekty (2025-01-01 .. 2026-05-31)

128 985 meczów; model stanu goli na 62 287 meczach z pełnym zapisem
(171 260 goli, 13 277 czerwonych). Współczynniki w skali log (± SE), w
nawiasie mnożnik:

| stan (gole) | współczynnik | mnożnik |
|---|---|---|
| własna czerwona | -0.598 ± 0.018 | x0.55 |
| czerwona rywala | +0.440 ± 0.011 | x1.55 |
| prowadzenie 2+ | +0.137 ± 0.009 | x1.15 |
| prowadzenie od 71. min | -0.089 ± 0.012 | x0.91 |
| strata 1 / prowadzenie 1 / strata 2+ / strata od 71. | -0.009 / -0.013 / +0.002 / +0.013 (SE ~0.01) | ~x1.0 |

Profil goli (log, przedziały 0-14, 15-29, 30-44, doliczony; 1. i 2.
połowa): -0.225, -0.151, -0.106, +0.068 | -0.032, -0.034, +0.004, +0.201
(gole przyspieszają przez cały mecz; doliczony czas 2. połowy najgęstszy).
Czerwone: strata +0.21 ± 0.022, prowadzenie -0.20 ± 0.024, końcówka +0.09.
Liczniki (1. / 2. połowa): rożne - strata +0.21 / +0.21, prowadzenie
-0.21 / -0.33, własna czerwona -0.57 / -0.44, czerwona rywala +0.40 / +0.38;
strzały - strata +0.15 / +0.17, prowadzenie -0.12 / -0.25, gol strzelony
+0.16 / +0.14; celne - gol strzelony +0.36 / +0.33; faule - prowadzenie
+0.08 / +0.05; kartki - czerwona rywala +0.42 (1. poł.). Doliczony czas
2. połowy - moda 5 minut. Rożne stron skorelowane ujemnie (-0.056).

Wniosek o efektach: przy remisie / jednej bramce różnicy tempo goli się nie
zmienia; zmienia je czerwona kartka (mocno) i wysokie prowadzenie. Za to
liczniki (rożne, strzały) reagują na stan silnie - tego żaden dzisiejszy
klocek SHEET nie modeluje.

## 3. Historia (2026-06-01 .. 09-17, bez cen)

6 000 meczów (5 783 z czasami goli), 35 098 wierszy odtworzenia
(`cache-calibration`). Brier x 1000 (symulator - obecny), przedział 95% z
bootstrapu po meczach; "obecny" dla rodzin (a) = niezależne połowy NB
(sekcja 0), dla (c) = wiersz odtworzenia (estymator z czasu refitu, nie
dzisiejszy SHEET - porównanie wyłącznie orientacyjne, patrz (c3)).

| rodzina | wiersze | sym - obecny (Brier x1000) | trafione - deklarowane przy p >= 0.70 (pp) |
|---|---|---|---|
| a1 HT/FT | 52 047 | -0.58 [-0.83, -0.31] lepszy | -8.3 [-21.1, +3.5] (n 54) |
| a2 wynik połowy | 34 698 | -2.24 [-3.00, -1.51] lepszy | -2.9 [-9.1, +2.9] |
| a3 połowa z więcej goli | 17 349 | -1.61 [-2.61, -0.62] lepszy | - |
| a4 gol w obu połowach | 57 830 | -1.68 [-2.47, -0.91] lepszy | -3.1 [-4.1, -2.0] |
| a5 pierwszy gol | 73 190 | -1.48 [-1.88, -1.07] lepszy | -2.4 [-6.0, +1.1] |
| a6 gole w połowach | 69 396 | -1.57 [-2.22, -0.88] lepszy | -5.2 [-7.8, -2.6] |
| c1 1X2 (wzór SHEET) | 18 000 | +0.06 [-0.15, +0.29] remis | -3.5 [-7.0, -0.0] |
| c2 ponad 2.5 (wzór SHEET) | 6 000 | -1.32 [-2.11, -0.49] lepszy | -5.4 [-7.7, -3.3] |
| c2 goals_total (odtworzenie) | 5 583 | +0.99 [-1.46, +3.56] remis | -9.4 [-13.9, -4.7] |
| c3 goals_for | 11 445 | -14.2 [-16.6, -11.8] lepszy* | -3.0 [-4.6, -1.5] |
| c5 rożne | 3 406 | -6.47 [-10.3, -3.1] lepszy | -4.2 [-9.9, +1.5] |
| c6 kartki | 1 389 | +0.64 [-2.71, +4.28] remis | -11.7 [-25.8, +2.2] (n 43) |
| c7 faule | 2 491 | -2.52 [-7.47, +1.98] remis | -9.0 [-14.8, -3.4] |
| c8 strzały / celne | 4 818 | +4.29 [+0.50, +7.96] gorszy | -14.0 [-18.6, -9.8] |
| x dokładny wynik / liczba goli / parzystość | | -0.04 / -0.17 / +0.10 | - |

\* wiersze odtworzenia `goals_for` pochodzą ze starszego estymatora (refit
replay); na liniach Superbetu (sekcja 5) symulator i dzisiejszy SHEET na
`goals_for` remisują - liczba z historii nie jest przewagą nad SHEET.

Na historii symulator (surowe p, bez krzywej) jest lepszy od "niezależnych
połów" na każdej rodzinie ścieżki - to jest realna wiedza o przebiegu
meczu. Surowe p nad-obiecuje przy >= 0.70 (łącznie -4.0 pp [-4.9, -3.1]) -
jak każdy estymator przed krzywą kalibracyjną.

## 4. Dev (2026-10-07 .. 10-24) - tylko wyłapanie błędów

Znalezione i poprawione przed hold-outem (żadna stała nie zmieniona):

1. **Historia ratingu nie zna świeżych meczów** - buduje się ze stron `last`
   drużyn, które się opóźniają: 2 835 meczów dni Superbetu nie było w
   historii (z 10-25 .. 11-05 ponad połowa), więc nie miały prognozy ani
   wyniku (`live_sides_disagree` 227 877 wierszy). Poprawka: brakujący mecz
   parsowany z jego cache'owanego `/event` (`sofa_event_detail`, to co czyta
   SETTLE) parserem ratingu, scalony w kolejności czasu, zamrożony w
   `history_live.pkl`; 2 294 sparsowane, 2 282 z czasami goli. Po poprawce
   odrzucenia "strony się nie zgadzają" = 213 (różne id rywala).
2. **Propsy zawodników wpadały do rodzin drużynowych** (`player_shots_for`
   pasowało do "shots") i odpadały dopiero na mapowaniu strony (11 wierszy
   zmapowało się mylnie). Poprawka: `player_*` poza pomiarem.
3. Wynik z `/event` bez wyniku po 90 min wywracał rozliczenie ścieżki -
   teraz pomijany (`path_no_score` 9).

Odrzucenia po poprawkach (dev + hold-out razem): brak pary cen OVER / UNDER w
`04_offer` 251 392, rynek nieczytany przez pomiar 265 057 (propsy, inne
rynki), wiersz bez symulowanej selekcji 28 279, wynik ścieżki nieczytany
8 010, zbiór niekompletny 22, mecz bez prognozy 158. Na dev wyniki
symulatora na kontroli (c) leżą przy dzisiejszym SHEET (różnice w granicach
+-2 x 10^-3), więc mapowanie stron i rozliczenie uznano za poprawne.

## 5. Hold-out Superbetu (2026-10-25 .. 11-05, liczony raz)

Brier x 1000; przedziały 95% z bootstrapu po meczach. Kolumna "nad-obietnica
>= 0.70": trafione - deklarowane symulatora (pp). ROI: nogi symulatora z p
>= 0.70 i p x kurs >= 0.90, stawka płaska, przed / po podatku 12%.

| rodzina | wiersze / mecze | sym - cena | obecny - cena | sym - obecny | >= 0.70 (pp) | 0.60-0.70 (pp) | ROI / po podatku | werdykt |
|---|---|---|---|---|---|---|---|---|
| a1 HT/FT | 37 512 / 4 168 | +1.66 [+1.24, +2.06] | brak wyceny | - | -11.9 [-28.4, +4.4] (n 33) | -11.9 [-22.4, -1.4] | -0.0% / -12.0% (n 30) | nie |
| a2 wynik połowy | 13 374 / 2 229 | +5.41 [+3.92, +7.00] | brak wyceny | - | -7.8 [-19.0, +2.7] | -14.5 [-21.9, -7.1] | +8.9% / -4.2% (n 64) | nie |
| a3 połowa z więcej goli | 6 558 / 2 186 | -0.15 [-0.73, +0.41] | brak wyceny | - | za mało nóg | - | - | **co najmniej jak Superbet** (brak nóg >= 0.70) |
| a4 gol w obu połowach | 15 398 / 2 186 | +3.78 [+1.93, +5.50] | brak wyceny | - | -0.4 [-1.8, +1.2] | -1.3 [-4.1, +1.3] | -4.0% / -15.5% | nie |
| a5 pierwszy gol | 16 355 / 2 217 | +4.06 [+2.56, +5.52] | (SHEET tylko `first_goal`) | - | -8.1 [-14.1, -2.0] | -4.5 [-8.3, -0.7] | -8.2% / -19.2% | nie |
| a6 gole w połowach | 70 728 / 2 222 | +2.34 [+1.35, +3.30] | (SHEET połowy) | - | -0.8 [-1.5, -0.0] | -0.1 [-1.1, +0.9] | -4.9% / -16.4% | nie |
| c1 1X2 / DC / DNB | 23 679 / 4 241 | +11.33 [+8.84, +13.74] | +11.20 [+8.85, +13.67] | +0.13 [-0.44, +0.67] remis | -1.7 [-2.7, -0.7] | +0.8 [-0.7, +2.2] | -7.4% / -18.5% | nie |
| c2 goals_total | 17 120 / 4 215 | +5.19 [+3.52, +6.89] | +3.28 [+1.93, +4.66] | +1.90 [+1.05, +2.75] **gorszy** | -1.4 [-2.3, -0.6] | +0.0 [-1.5, +1.4] | -5.6% / -16.9% | nie |
| c3 goals_for | 13 135 / 2 197 | +7.23 [+5.13, +9.45] | +7.12 [+5.10, +9.28] | +0.11 [-0.53, +0.75] remis | -1.0 [-1.9, -0.2] | -0.2 [-1.7, +1.4] | -4.8% / -16.2% | nie |
| c4 wynik / gole kombinacje | 42 400 / 4 221 | +6.15 [+4.37, +8.00] | +6.23 [+4.52, +8.06] | -0.08 [-0.81, +0.69] remis | -1.6 [-2.5, -0.8] | -0.0 [-1.0, +0.8] | -5.5% / -16.9% | nie |
| c5 rożne | 30 476 / 965 | +4.05 [+1.86, +6.29] | +2.45 [+0.59, +4.33] | +1.60 [-0.12, +3.34] remis | +0.1 [-1.0, +1.2] | -0.6 [-1.7, +0.4] | -2.7% / -14.4% | nie |
| c6 kartki | 13 163 / 759 | +5.10 [+2.25, +7.85] | +4.84 [+2.19, +7.44] | +0.27 [-1.53, +2.06] remis | -2.3 [-4.1, -0.6] | -4.3 [-6.3, -2.4] | -6.4% / -17.7% | nie |
| c7 faule | 1 226 / 247 | +0.17 [-9.89, +10.25] | -3.16 [-11.0, +4.45] | +3.33 [-3.49, +9.75] remis | -9.5 [-19.0, -0.3] | -7.0 [-13.9, -0.4] | +12.5% / -1.0% (n 144) | nie |
| c8 strzały / celne | 17 164 / 390 | +7.50 [+3.67, +11.60] | +3.74 [+0.58, +6.85] | +3.76 [+1.15, +6.19] **gorszy** | -1.8 [-3.9, +0.2] | -0.5 [-2.2, +1.1] | -4.0% / -15.5% | nie |
| x parzystość goli | 8 378 / 4 189 | +0.36 [-0.29, +0.94] | - | - | - | - | - | informacyjnie (nie gorszy) |
| x dokładna liczba goli | 7 777 / 1 111 | +1.25 [+0.68, +1.81] | - | - | - | - | - | informacyjnie (gorszy) |
| x dokładny wynik | 171 623 / 4 169 | +0.15 [+0.10, +0.20] | - | - | - | - | - | informacyjnie (lista niepełna) |
| razem | 506 066 / 4 272 | +2.95 [+2.40, +3.51] | | | -1.2 [-1.6, -0.7] | -0.7 [-1.1, -0.2] | -4.9% / -16.3% | nie |

Dev (10-07 .. 10-24) daje ten sam obraz: każda rodzina poza a3 i x jest
gorsza od ceny bez marży z przedziałem wykluczającym zero; a3 nie gorsza.

**Werdykty (kryterium główne):** "co najmniej tak dobry jak Superbet" -
**tylko a3** (połowa z większą liczbą goli: -0.15 [-0.73, +0.41], margines
2.1), ale symulator nie daje tam żadnej nogi >= 0.70, więc nic by się z niej
nie wydrukowało; parzystość goli - nie gorsza, informacyjnie. Pozostałe
rodziny ścieżki (a1, a2, a4, a5, a6) i cała kontrola - **nie**. Kontrola wobec
obecnego SHEET: remis na c1, c3, c4, c5, c6, c7; **gorszy na c2
(`goals_total`) i c8 (strzały)** - warunek "nie gorszy od obecnego" nie
spełniony dla tych dwóch. "Lepszy od ceny" - nigdzie.

## 6. Pary nóg jednego meczu (buildery), hold-out

Noga = wiersz rynku z `p_central` najbliżej 0.70. Brier x 1000; "łączne" =
p wspólne z symulacji, "iloczyn" = iloczyn marginesów symulacji, "iloczyn
SHEET" = iloczyn `p_central`, k/n = `dossier.joint_history` (n >= 5).

| para | n | trafione | łączne - iloczyn | łączne - iloczyn SHEET | łączne - k/n |
|---|---|---|---|---|---|
| obie drużyny ponad X goli + gole razem | 4 201 | 0.395 | **-7.94 [-10.8, -4.8]** | **-8.61 [-11.8, -5.3]** | **-10.2 [-13.1, -7.3]** |
| celne razem + gole razem | 387 | 0.491 | **-6.81 [-12.8, -0.9]** | -1.47 [-8.9, +5.7] | -10.3 [-22.7, +2.0] |
| gole 1. + 2. połowy | 2 211 | 0.544 | -0.01 [-0.25, +0.24] | +0.40 [-1.6, +2.4] | **-10.1 [-14.8, -5.5]** |
| gole + kartki | 682 | 0.447 | -0.08 [-0.43, +0.27] | -0.79 [-4.7, +3.1] | **-13.7 [-22.0, -5.2]** |
| gole + rożne | 957 | 0.490 | -0.41 [-0.84, +0.00] | +4.02 [+0.45, +8.07] | -6.1 [-13.1, +1.2] |
| wynik + gole | 4 223 | 0.349 | -0.53 [-1.40, +0.33] | -0.23 [-1.6, +1.1] | brak k/n |
| wynik + rożne | 958 | 0.376 | -0.22 [-0.63, +0.19] | +3.23 [+0.79, +5.77] | brak k/n |
| wynik + kartki | 683 | 0.373 | +0.05 [-0.23, +0.33] | -2.07 [-5.0, +0.8] | brak k/n |
| rożne + kartki | 588 | 0.476 | -0.03 [-0.42, +0.37] | +4.65 [-0.6, +10.0] | -4.5 [-13.2, +4.2] |
| gole drużyny + jej rożne | 711 | 0.492 | -0.32 [-0.99, +0.37] | +0.53 [-3.6, +4.9] | -6.6 [-15.7, +3.0] |
| razem | 15 601 | 0.419 | **-2.51 [-3.28, -1.69]** | **-1.84 [-3.07, -0.65]** | **-9.42 [-11.8, -6.9]** (n 9 731) |

Korelacja z symulacji ma znaczenie tam, gdzie obie nogi czytają te same gole
(obie strony ponad X + gole razem; celne + gole); dla par różnych zmiennych
(gole / rożne / kartki / wynik) p łączne = iloczyn marginesów (różnice
< 0.5 x 10^-3), więc symulator nie dodaje tam nic. k/n z dossier (do 20
meczów) jest najsłabszym oszacowaniem p łącznego w każdej parze. Ceny
buildera brak - porównania z rynkiem nie ma.

## 7. Rynki, których SHEET dziś nie wycenia

HT/FT (`1. połowa/mecz`), wynik połowy (`1.połowa - 1X2`, `2.połowa - 1X2`),
połowa z większą liczbą goli, drużyna strzeli w obu połowach / obie strzelą
w 1. / 2. połowie / w przynajmniej jednej, pierwszy gol w przedziałach
15-minutowych, `1. połowa - 1. gol`, `Ostatni gol`, `1.połowa liczba goli &
2.połowa liczba goli`, parzystość goli, dokładna liczba goli, dokładny wynik.
Ceny tych rynków leżą w `unmapped_prices/` (OFFER ich nie czyta); symulator
wycenia wszystkie z jednej symulacji.

## 8. Czego wymagałoby podłączenie (nie zrobione)

- przełącznik w `bet.sofa.epochs` (np. `FOOTBALL_SIM`, od następnego dnia
  00:00Z), dzień mieszany przy włączeniu w trakcie;
- OFFER: mapowanie rynków z sekcji 7 w `market_mapper` (dziś tylko zapis do
  `unmapped_prices`), SETTLE: rozliczenie z czasów goli (`incidents_json`;
  mecz bez czasów = nierozliczalny), regrade;
- własne krzywe jak w tenisie (`fit_*_curves` na historii, odtworzenie jak
  SHEET, wiersze bez cen), bo surowe p nad-obiecuje (historia -4.0 pp przy
  >= 0.70); potem klucze line evidence (offset, pasma cen) - bez tego
  `NO_LINE_EVIDENCE`;
- SHEET: centra z `RatingBook` już liczone przez SHEET - symulator czytałby
  je zamiast budować własny walk-forward;
- **czas:** symulacja 0.054-0.061 s na mecz na rdzeń (4 000 symulacji, wszystkie
  selekcje meczu) - ~180-350 meczów piłki dziennie = 10-21 s na jednym
  rdzeniu; walk-forward ratingu osobno 49 s (od 2026-09-18) .. 112 s (od
  2025), a w SHEET już istnieje.

Przy tych wynikach podłączenie nie jest rekomendowane: żadna rodzina, która
dałaby nogę >= 0.70, nie jest co najmniej tak dobra jak cena bez marży.

## 9. Czego nie zmierzono

- przebiegu meczu (momentum / graph) i shotmapy - brak w cache;
- składów (wyjściowa XI) jako modyfikatora intensywności;
- per-ligowych profili czasu i efektów stanu (jeden zestaw dla wszystkich
  lig, kobiety razem z mężczyznami);
- krzywych kalibracyjnych na symulatorze (porównanie dotyczy surowego p,
  obecny SHEET ma `p_central` bez krzywej - oba przed CONFIDENCE);
- dogrywek / karnych (tylko 90 min);
- ceny buildera Superbetu (nie publikowana).
