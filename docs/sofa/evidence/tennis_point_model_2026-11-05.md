# Tenis: model punktowy od dołu (plan B) - pomiar 2026-11-05

Go operatora 2026-11-05 na "plan B" z `tennis_serve_markets_plan_2026-10-26.md`.
Pomiar tylko do odczytu: żaden przełącznik nie włączony, żaden plik `config/`
nie zmieniony, żaden wiersz bazy nie zapisany, sieć nie pytana (tylko cache).

## 0. Reguły zapisane PRZED obejrzeniem wyników (pre-rejestracja)

Ta sekcja została napisana i zapisana w pliku, zanim skrypt pomiarowy policzył
cokolwiek na liniach Superbetu. Uzupełnienie operatora z 2026-11-05 (cel: nie
pobić Superbetu, tylko przewidywać co najmniej tak dobrze jak jego cena)
wpisane tu przed pierwszym przebiegiem.

**Rodziny** (każda osobno; kierunek OVER niesie całą informację pary, więc
jedna linia = jeden wiersz OVER z p modelu, p obecnego i ceną bez marży z pary
OVER/UNDER tej samej linii):

1. `games_total` (gemy w meczu), 2. `sets_total` (2.5, best of three),
3. `games_set1_total` + `games_set2_total` (gemy w secie, razem),
4. `games_won_for` (gemy zawodnika), 5. `aces_for` + `aces_total` (asy, mecz),
6. `double_faults_for` + `double_faults_total` (podwójne błędy, mecz),
7. `serve_points_for` + `serve_points_total` (asy + podwójne błędy, mecz),
8. rynki na set: `aces_set{1,2}_*`, `double_faults_set{1,2}_*`,
   `serve_points_set{1,2}_*` (razem jedna rodzina "serwis w secie").

**Dane Superbetu:** `sofa_settled_row`, `run_date` od 2026-09-18 (żywe dni),
WIN / LOSS, oba kierunki linii z kursem (para do zdjęcia marży: p_nv =
(1/kurs_OVER) / (1/kurs_OVER + 1/kurs_UNDER); para z sumą odwrotności poza
[1.00, 1.30] odrzucona jako niespójna). Mecze best of five i mecze bez
prognozy modelu (zawodnik bez historii punktów = prognoza z prioru jest
prognozą - liczona; brak meczu w historii = wiersz odrzucony i policzony).

**Podział czasu:** dni z liniami posortowane; pierwsze ~2/3 dni = rozwój
(dev), ostatnia ~1/3 dni = hold-out, obliczany **raz**, po zamrożeniu kodu i
stałych. Stałe modelu (wariancje prioru, dryf, szum formy, rozproszenie NB)
dobierane wyłącznie na historii Sofascore sprzed 2026-01-01; dev służy do
wyłapania błędów (mapowanie zawodnika na stronę, linie), nie do strojenia na
wynikach.

**Kryterium główne (operator 2026-11-05) - NIE-GORSZY OD CENY:** na hold-oucie
dla każdej rodziny Brier(model) - Brier(cena bez marży), przedział 95% z
bootstrapu po meczach (2 000 losowań; wszystkie linie meczu razem).
"Tak dobry jak cena" = górna granica przedziału <= **+0.002**. Margines
ustalony przed obejrzeniem: 0.002 Briera to ok. 1% Briera rynku przy p ~0.5
(Brier ~0.24) i rząd wielkości szumu między dniami widziany w poprzednich
pomiarach tenisa (różnice cena - stała -0.0095 na 7 849 liniach); mniejszego
marginesu przy kilkuset meczach hold-outu nie da się rozstrzygnąć. To samo
podajemy dla log-loss (informacyjnie, margines +0.005).
**Kalibracja:** realizacja vs deklarowane p w kubełkach p (0.0-0.1, ..., 0.9-1.0,
z kierunkiem: OVER p, UNDER 1-p - każda noga osobno); kubełek >= 0.70 (obie
strony, nogi z p >= 0.70): przedział 95% realizacji (bootstrap po meczach)
musi zawierać deklarowane średnie p (brak nad-obietnicy typu 0.781 -> 0.548
z 10-26).

**Kryterium drugie - lepszy od obecnego modelu:** Brier(model) - Brier(obecne
p_central z SHEET), przedział po meczach wykluczający zero (górna granica < 0).

**Raportowane, nie kryterium:** nogi z p modelu >= 0.70 i x = p x kurs >= 0.90
- deklarowane vs realizacja, ROI po kursie Superbetu z przedziałem. Noga
realizująca się w cenie bez marży traci ok. marżę - to zaakceptowane.

**Historia (walk-forward, Sofascore):** model w porządku czasu, prognoza meczu
z ocen sprzed jego startu (aktualizacja dopiero po prognozie). Okres testu:
2026-01-01 .. 2026-09-17 (przed liniami Superbetu). Porównanie z obecnym
estymatorem odtworzonym w replayu (`sofa_settled_row`, `run_date =
cache-calibration`, p_central) na liniach rynkowych: jedna linia na (mecz,
rynek, zawodnik) - ta, na której p obecnego estymatora jest najbliżej 0.5
(reguła z 10-26). Przedziały po meczach.

Werdykt per rodzina słowami: "tak dobry jak cena" (tak / nie), "lepszy od
obecnego modelu" (tak / nie), "skalibrowany przy >= 0.70" (tak / nie / za mało
nóg: < 30 nóg).

---

*Wszystko poniżej napisane po pomiarze. Liczby z
`scripts/sofa/measure_tennis_point_model.py`; wyniki i skrypty strojenia w
`data/refit_2026-11-05_tennis_point_model/` (`superbet_holdout.json`,
`superbet_dev.json`, `superbet_lines.jsonl`, `history.json`, `tune*.py`,
`tune.json`, `tune.log`, `tune_match_after_fix.log`, `fit_form.py`).*

## Werdykt (hold-out 2026-10-20 .. 11-04, 16 dni, liczony raz)

| rodzina | linie / mecze | Brier model - cena [95%] | tak dobry jak cena (<= +0.002) | Brier model - obecny [95%] | lepszy od obecnego | p >= 0.70: deklar. / trafione [95%] (nogi / mecze) | skalibrowany >= 0.70 |
|---|---|---|---|---|---|---|---|
| `games_total` | 6 709 / 1 716 | +0.0029 [+0.0002, +0.0057] | **nie** (gorszy) | +0.0022 [-0.0007, +0.0052] | nie | 0.761 / 0.632 [0.573, 0.689] (400 / 288) | **nie** (zawyża ~13 pp) |
| `sets_total` | 1 797 / 1 797 | -0.0005 [-0.0020, +0.0010] | **tak** | +0.0001 [-0.0018, +0.0021] | nie (remis) | 0.762 / 0.779 [0.737, 0.818] (434 / 434) | tak |
| gemy w secie (`games_set1/2_total`) | 18 842 / 1 716 | -0.0003 [-0.0011, +0.0004] | **tak** | -0.0021 [-0.0030, -0.0012] | **tak** | 0.842 / 0.847 [0.840, 0.854] (12 500 / 1 716) | tak |
| `games_won_for` | 13 176 / 1 908 | +0.0050 [+0.0027, +0.0074] | **nie** (gorszy) | -0.0014 [-0.0045, +0.0015] | nie (remis) | 0.778 / 0.769 [0.757, 0.781] (5 213 / 1 871) | tak (ogony 0.9-1.0 zawyżają) |
| asy (mecz, `_for` + `_total`) | 924 / 219 | +0.0026 [-0.0083, +0.0135] | nie (nierozstrzygnięte) | -0.0397 [-0.0650, -0.0157] | **tak** | 0.762 / 0.690 [0.565, 0.800] (100 / 53) | tak (szeroki przedział) |
| podwójne błędy (mecz) | 921 / 219 | -0.0035 [-0.0110, +0.0041] | nie (nierozstrzygnięte) | -0.0211 [-0.0345, -0.0087] | **tak** | 0.775 / 0.721 [0.644, 0.792] (219 / 75) | tak |
| asy + podw. błędy (`serve_points`, mecz) | 928 / 219 | -0.0023 [-0.0121, +0.0077] | nie (nierozstrzygnięte) | -0.0446 [-0.0696, -0.0220] | **tak** | 0.743 / 0.621 [0.448, 0.800] (58 / 35) | tak (szeroki przedział) |
| serwis w secie (asy / pb / suma, sety 1-2) | 3 959 / 216 | -0.0015 [-0.0062, +0.0029] | nie (nierozstrzygnięte) | -0.0323 [-0.0430, -0.0217] | **tak** | 0.764 / 0.750 [0.685, 0.814] (356 / 78) | tak |
| wszystkie rynki serwisu razem | 6 732 / 219 | -0.0013 [-0.0063, +0.0036] | nie (nierozstrzygnięte) | -0.0335 [-0.0457, -0.0224] | **tak** | - | - |
| wszystko | 47 256 / 2 122 | +0.0015 [+0.0001, +0.0028] | nie | -0.0057 [-0.0080, -0.0034] | **tak** | 0.818 / 0.815 [0.808, 0.822] (19 280 / 2 026) | tak |

"Nierozstrzygnięte" = punkt blisko zera, ale przy 219 meczach przedział ma
szerokość ~0.01-0.02 Briera, więc reguła (górna granica <= +0.002) nie jest
spełniona; to nie jest dowód, że model jest gorszy od ceny.

Słowami:

- **Rynki serwisu (asy, podwójne błędy, ich suma; mecz i sety 1-2):** model od
  dołu jest **dużo lepszy od obecnego SHEET** (Brier -0.021..-0.045, każdy
  przedział wyklucza zero, na dev i na hold-oucie) i **przestaje obiecywać za
  dużo**: przy p >= 0.70 obecny SHEET deklaruje 0.78-0.80 i trafia 0.50-0.63,
  model deklaruje 0.74-0.78 i trafia 0.62-0.75, każdy przedział zawiera
  deklarację. Wobec ceny bez marży: punktowo remis (-0.0035..+0.0026), ale
  **nie-gorszości z marginesem 0.002 nie wykazano** (za mało meczów). Podwójne
  błędy na dev wyszły lepiej od ceny (-0.0189 [-0.0285, -0.0088]), na
  hold-oucie już -0.0035 [-0.0110, +0.0041] - zgodne z zanikającym rozjazdem
  linii Superbetu opisanym 10-26, nie z trwałą przewagą modelu.
- **`sets_total` i gemy w secie:** **tak dobre jak cena** (górna granica <=
  +0.002 Briera; log-loss też w marginesie 0.005) i skalibrowane przy >= 0.70;
  gemy w secie dodatkowo lepsze od obecnego estymatora, `sets_total` remis.
- **`games_total` i `games_won_for`:** **gorsze od ceny** (przedział > 0) i nie
  lepsze od obecnego (remis). `games_total` przy p >= 0.70 zawyża (0.761 ->
  0.632); na liniach, które Superbet stawia wysoko (24.5+), model daje 0.22-0.38
  OVER, realizacja 0.33-0.44 (dev) - rynek widzi wyrównanie meczu, którego
  rating punktów nie widzi.
- **Lepszy od ceny:** nigdzie na hold-oucie z przedziałem wykluczającym zero.

Nogi, które model by ocenił >= 0.70 przy x = p x kurs >= 0.90 (hold-out; to
samo kryterium dla obecnego `p_central` dla porównania):

| zbiór | nogi / mecze | deklarowane | trafione [95%] | cena bez marży | ROI po kursie [95%] |
|---|---|---|---|---|---|
| serwis (wszystkie rodziny), model | 659 / 122 | 0.766 | 0.715 [0.649, 0.775] | 0.637 | +3.2% [-6.6, +12.5] |
| serwis, obecny SHEET | 1 880 / 208 | 0.782 | 0.533 [0.480, 0.583] | 0.553 | -12.2% [-21.1, -3.8] |
| gemy / sety (4 rodziny), model | 16 943 / 1 965 | 0.825 | 0.818 [0.811, 0.825] | 0.783 | -3.8% [-4.7, -2.9] |
| gemy / sety, obecny SHEET | 17 507 / 1 996 | 0.825 | 0.805 [0.797, 0.812] | 0.773 | -4.3% [-5.3, -3.3] |

ROI nie jest kryterium (operator 2026-11-05): noga w cenie bez marży traci
około marży. Dodatnie ROI nóg serwisu ma przedział przez zero (dev: +15.6%
[+8.0, +22.6] na 869 nogach / 165 meczach - nie powtórzyło się).

## 1. Model (`src/bet/sofa/tennis_point_model.py`)

1. **Ocena serwis / return na poziomie punktu.** logit P(serwujący i wygrywa
   punkt przeciw returnującemu j) = `c[płeć, tier, nawierzchnia] + S_i - R_j`
   - kombinacja Barnetta-Clarke'a / Klaassena-Magnusa (siła serwisu przeciw
   sile returnu wokół średniej komórki), na skali logitu, żeby nie wyjść poza
   [0, 1]. S i R to rozkłady normalne aktualizowane mecz po meczu w
   kolejności czasu krokiem "assumed density" (rozszerzony Kalman) na
   dwumianowej liczbie wygranych punktów serwisowych - rating typu Glicko na
   poziomie punktu. Dlaczego to, a nie ridge refitowany co dzień
   (`price_tennis_serve_model.py` z 09-23): prognoza "as of" wychodzi za darmo
   (prognoza ze stanu przed meczem, dopiero potem aktualizacja; mecze o tej
   samej sekundzie startu wszystkie prognozowane przed aktualizacją) - jeden
   przebieg po 269 197 meczach zamiast refitu na każdy dzień; skurcz do prioru
   (nowy zawodnik = średnia komórki z wariancją prioru), utrata pewności w
   czasie (dryf) i szum dnia meczu (tłumi aktualizację) to jawne stałe.
2. **Mecze bez statystyk** (większość ITF, prawie cała historia sprzed
   2025-05): wynik w gemach odwrócony na przesunięcie logitów obu serwujących
   (`score_shift`: oczekiwany udział gemów = zaobserwowany) i dodany jako
   pseudo-punkty (`SCORE_WEIGHT` 0.7 x 3.15 x gemy na stronę); nie rusza
   stawek komórek ani licznika punktów zawodnika.
3. **Asy i podwójne błędy** jako ułamek własnych punktów serwisowych, ten sam
   krok na (asy, punkty serwisowe) i (pb, punkty serwisowe): asy = komórka +
   serwujący + returnujący ("asy dopuszczone") + turniej (korty / piłki); pb =
   komórka + serwujący + turniej.
4. **Mecz symulowany punkt po punkcie** (4 000 symulacji, ziarno = id meczu):
   p serwisu każdej strony losowane z niepewności ratingu plus forma dnia
   (wspólny składnik dominacji - kto ma dzień, serwuje i returnuje lepiej),
   tie-break przy 6-6, best of three, decydujący super tie-break do 10 tam,
   gdzie wcześniejsze trzysetówki turnieju (as of) tak go zapisały - liczony
   jako jeden gem (konwencja pipeline'u, `tennis_score`). Gemy, sety, gemy w
   secie, gemy zawodnika i punkty serwisowe każdego seta pochodzą z tych samych
   symulacji, więc rynki jednego meczu nie mogą sobie przeczyć. Rynki na set
   warunkowe na rozegranie seta.
5. **Liczby serwisu:** ujemny dwumian ze średnią = stawka x punkty serwisowe z
   symulacji, kształt zmierzony (asy mecz 4, pb mecz 10, asy set 5, pb set 10;
   Poisson wyraźnie gorszy: log-lik. asów -49 734 vs -47 646, pb -52 048 vs
   -51 500); suma dwóch liczb (`_total`, asy + pb) - NB dopasowany momentami.
6. **Porównywalność:** czytnik historii to `tennis_rating.parse_event` z regułą
   `TENNIS_RATING_SCORE_WINNER` (towarzyskie / pokazowe, walkowery, debel,
   nieczytelny wynik - poza); mecz skreczowany niczego nie uczy i nie jest
   oceniany; best of five poza; statystyki z niespójnymi tożsamościami
   (punkty serwisowe jednej strony = punkty returnowe drugiej) odrzucone.

## 2. Dane i strojenie

- Historia: 269 197 meczów singlowych (strony `last` + indeks listingów),
  66 528 ze statystykami serwisu (od 2025-05 prawie wszystkie CH / TOUR, ITF
  15-35% meczów miesiąca).
- **Stałe wybrane wyłącznie na historii sprzed 2026-01-01** (walidacja
  2025-09-01..12-31, prognoza as of z całej wcześniejszej historii):
  - rating serwisu, log-loss na punkt (1 743 190 punktów): prior 0.1, dryf
    1e-4 / dzień, forma 0.1, returner 0.1; waga meczów bez statystyk 0 / 0.15 /
    0.4 / 0.7 / 1.0 -> 0.676487 / 0.675247 / 0.675069 / 0.675030 / 0.675025
    (0.7: dalej płasko);
  - asy: prior 0.3, dryf 5e-4, forma 0.2, returnujący 0.05, turniej 0.05
    (0.159047 vs 0.160947 najgorsze w siatce 32 wariantów); pb: prior 0.15,
    dryf 5e-4, forma 0.05, turniej 0.03 (0.186572 vs 0.187387; 24 warianty);
  - forma dnia meczu: zmierzona nadwyżka wariancji logitu 0.085 / 0.077,
    kowariancja -0.048 (7 621 meczów, obie strony z > 300 punktami); na 3 000
    meczach walidacji log-lik. sumy gemów 2.9638 / 2.9496 / **2.9490** /
    2.9683 i log-loss liczby setów 0.5879 / 0.5804 / **0.5780** / 0.5792 przy
    0 / 0.25 / 0.5 / 1 x zmierzonej - wysyłana połowa (0.04 / -0.0225); waga
    0 / 0.3 / 0.7 przy połowie formy: 2.9977 / 2.9572 / 2.9490;
  - kształty NB: największa wiarygodność na siatce (walidacja 2025-09..12,
    25 668 stron-meczów; per set 46 254).
- Superbet: 116 559 par linii (OVER + UNDER z kursem) z `sofa_settled_row`
  09-18..11-04; odrzucone przy ładowaniu: 4 115 bez kursu, 289 jednostronnych,
  2 z marżą poza [1.00, 1.30]; przy wycenie (dev + hold-out): 2 699 linii
  meczów nieobecnych w historii, 90 linii, gdzie strony 02_fixtures nie
  zgadzają się z historią, 6 z nierozpoznanym zawodnikiem. Dev = 09-18..10-19
  (32 dni), hold-out = 10-20..11-04 (16 dni). Pooled w obrębie rodziny:
  wszystkie turnieje, płcie, nawierzchnie, linie; rodzina "asy" = `aces_for` +
  `aces_total` itd.
- Obecny model = `p_central` z rozliczonego wiersza (SHEET, przed krzywymi i
  dowodami linii CONFIDENCE) - ta sama definicja co w pomiarze 10-26.

### Co dev znalazł (błąd, nie strojenie)

Pierwszy przebieg dev pokazał `games_total` z Brierem o +0.033 gorszym od ceny i
deklaracją 0.92 przy p >= 0.70. Przyczyna: w turniejach z super tie-breakiem
symulator grał jako super tie-break **także drugiego** seta. Poprawione (tylko
przy 1:1 w setach), test `test_match_tiebreak_decider_counts_one_game`
rozszerzony; stałe formy i wagi przeliczone ponownie na historii sprzed 2026 -
ten sam wybór (0.5 x forma, waga 0.7). Żadna stała nie została dobrana na
liniach Superbetu. Kod zamrożony commitem `e0ff3f10` przed hold-outem.

## 3. Historia, walk-forward 2026-01-01..09-17 (bez cen)

15 000 losowych meczów (ziarno 5) z wierszami replayu obecnego estymatora;
jedna linia na (mecz, rynek): ta, gdzie p replayu najbliżej 0.5. Replay
zawiera z sum tylko `games_total`, `aces_total`, `double_faults_total` (bez
`sets_total`, gemów w secie, rynków zawodnika - te tylko na Superbecie).

| rynek | linie (= mecze) | Brier nowy / obecny | nowy - obecny [95%] | log-loss nowy - obecny [95%] | p >= 0.70: deklar. / trafione [95%] (nogi) |
|---|---|---|---|---|---|
| games_total | 6 672 | 0.2378 / 0.2495 | -0.0117 [-0.0141, -0.0092] | -0.0244 [-0.0295, -0.0191] | 0.766 / 0.760 [0.719, 0.799] (437) |
| aces_total | 7 765 | 0.2228 / 0.2480 | -0.0251 [-0.0286, -0.0215] | -0.0529 [-0.0609, -0.0446] | 0.783 / 0.754 [0.738, 0.771] (2 479) |
| double_faults_total | 7 765 | 0.2329 / 0.2489 | -0.0159 [-0.0190, -0.0127] | -0.0325 [-0.0392, -0.0252] | 0.766 / 0.723 [0.702, 0.744] (1 608) |

Na historii model jest lepszy od odtworzonego obecnego estymatora na każdym z
trzech rynków; przy >= 0.70 asy i pb zawyżają o 3-4 pp (przedział nie
obejmuje deklaracji), gemy zgodne. Uwaga: linia "najbliżej 0.5 dla obecnego"
to linia, na której obecny estymator jest najmniej pewny - wybór neutralny
wobec wyniku, ale nie identyczny z linią Superbetu.

## 4. Dev (09-18..10-19) i Brier bezwzględny

| rodzina | linie / mecze | Brier nowy / obecny / cena | model - cena | model - obecny |
|---|---|---|---|---|
| games_total | 11 714 / 2 927 | 0.2446 / 0.2444 / 0.2378 | +0.0067 [+0.0038, +0.0098] | +0.0001 [-0.0029, +0.0033] |
| sets_total | 2 860 / 2 860 | 0.2131 / 0.2173 / 0.2112 | +0.0019 [+0.0005, +0.0033] | -0.0042 [-0.0068, -0.0017] |
| gemy w secie | 24 141 / 2 448 | 0.1705 / 0.1736 / 0.1704 | +0.0002 [-0.0004, +0.0008] | -0.0030 [-0.0041, -0.0019] |
| games_won_for | 21 128 / 3 077 | 0.2219 / 0.2221 / 0.2118 | +0.0100 [+0.0079, +0.0123] | -0.0002 [-0.0027, +0.0024] |
| asy | 884 / 224 | 0.2414 / 0.2640 / 0.2421 | -0.0007 [-0.0126, +0.0107] | -0.0226 [-0.0412, -0.0032] |
| podwójne błędy | 883 / 223 | 0.2082 / 0.2524 / 0.2271 | -0.0189 [-0.0285, -0.0088] | -0.0442 [-0.0598, -0.0300] |
| serve_points | 879 / 223 | 0.2406 / 0.2697 / 0.2435 | -0.0028 [-0.0123, +0.0069] | -0.0290 [-0.0526, -0.0052] |
| serwis w secie | 4 019 / 219 | 0.2377 / 0.2710 / 0.2408 | -0.0031 [-0.0080, +0.0015] | -0.0333 [-0.0432, -0.0234] |

Hold-out, Brier nowy / obecny / cena: games_total 0.2443 / 0.2421 / 0.2414;
sets_total 0.2078 / 0.2077 / 0.2083; gemy w secie 0.1631 / 0.1652 / 0.1634;
games_won_for 0.2180 / 0.2194 / 0.2130; asy 0.2439 / 0.2836 / 0.2414; pb
0.2294 / 0.2506 / 0.2329; serve_points 0.2435 / 0.2881 / 0.2458; serwis w
secie 0.2391 / 0.2714 / 0.2407. Log-loss model - cena (hold-out): asy +0.0058
[-0.0178, +0.0296], pb -0.0062 [-0.0227, +0.0109], serve_points -0.0041
[-0.0253, +0.0166], serwis w secie -0.0032 [-0.0131, +0.0061], games_total
+0.0069 [+0.0010, +0.0129], sets_total -0.0015 [-0.0052, +0.0024], gemy w
secie -0.0017 [-0.0038, +0.0005], games_won_for +0.0159 [+0.0096, +0.0223].

## 5. Kalibracja na hold-oucie (model; nogi obu kierunków)

Pełne tabele per kubełek p: `superbet_holdout.json` (`calibration_new`,
`calibration_current`). Najważniejsze:

- `games_total`: 0.7-0.8 deklarowane 0.741 / trafione 0.627 [0.569, 0.687]
  (316 nóg), 0.8-0.9 0.838 / 0.651 [0.549, 0.750] (83) - zawyża; środek
  zgodny (0.452 / 0.451, 0.548 / 0.549).
- `sets_total`: 0.6-0.7 0.655 / 0.674, 0.7-0.8 0.736 / 0.758, 0.8-0.9 0.842
  / 0.852 - zgodne.
- gemy w secie: każdy kubełek w granicach ~2 pp (0.9-1.0: 0.926 / 0.935).
- `games_won_for`: 0.9-1.0 0.956 / 0.827 [0.779, 0.877] (272 nogi), 0.0-0.1
  0.044 / 0.173 - ogony zbyt pewne; 0.7-0.8 0.747 / 0.757 zgodny.
- asy 0.7-0.8: 0.742 / 0.671 [0.550, 0.783] (79); pb 0.7-0.8: 0.745 / 0.686
  [0.601, 0.763] (156); serwis w secie 0.7-0.8: 0.739 / 0.714 [0.635, 0.787]
  (269), 0.8-0.9: 0.839 / 0.854 (82).

## 6. Co by zmienił przełącznik (niczego nie włączono)

Nic nie jest podłączone: żaden etap nie importuje modułu (test
`test_no_pipeline_stage_reads_the_model`), w `bet.sofa.epochs` nie dodano
przełącznika. Gdyby operator zdecydował, sensowny zakres z tego pomiaru:

- **tak:** rynki serwisu (asy / pb / suma; mecz i sety 1-2) - zamiast dzisiejszego
  `p_central`, który przy >= 0.70 trafia 0.53 przy deklaracji 0.78; na
  hold-oucie 659 nóg / 122 mecze przy >= 0.70 i x >= 0.90 zamiast 1 880 / 208,
  trafione 0.715 vs 0.533. Gemy w secie i `sets_total` - tak dobre jak cena.
- **nie:** `games_total`, `games_won_for` (gorsze od ceny, nie lepsze od
  obecnych).
- Mechanika: nowy przełącznik `TENNIS_POINT_MODEL_FROM_UTC` (domyślnie
  następny dzień 00:00Z, decyzja operatora), znacznik wiersza SHEET; model
  liczony as of z cache przy budowie dnia (wczytanie historii z bazy 155 s;
  czas przebiegu ratingu w SHEET niezmierzony; symulacja 20 000 meczów 0.18 s,
  więc 4 000 na mecz to ułamek sekundy). CONFIDENCE: dzisiejsze krzywe serwisu są
  dopasowane do starego estymatora (i 50 kluczy to `LIVE_ONLY_CURVE_REFUSED`)
  - model nie potrzebuje krzywej (jest skalibrowany sam), ale reguła "krzywe z
  historii" wymagałaby albo krzywej dopasowanej na replayu tego modelu, albo
  zgody operatora na czytanie p modelu wprost z dowodami linii (które tylko
  obniżają). To wymaga go operatora; nic z tego nie zrobiono.
- Nowy test w przód (propozycja, niezarejestrowana): nogi serwisu modelu >= 0.70
  od dnia włączenia, kryterium jak `T-TENNIS-SERVE-MARKET-LINE` (trafione >=
  deklarowane - 2 pp, >= 200 nóg / 100 meczów).

## 7. Czego nie zmierzono

- Prawdziwego CONFIDENCE (krzywe + dowody linii) - porównanie na surowym
  `p_central`; prawdziwe CONFIDENCE tylko obniża.
- Dostępności danych w chwili budowy: model czyta dzisiejszy cache (mecze
  dociągnięte później - nie wyniki meczu prognozowanego, ale np. wczorajsze
  statystyki, których rano mogło nie być). Kurs Superbetu = kurs z OFFER, nie
  zamknięcia.
- Superbet hold-out obejmuje tylko mecze obecne w historii (2 699 linii poza).
- Rynki per set 3, `most_*`, `handicap_*`, `tiebreaks_total`, `set_score` -
  model je umie policzyć (te same symulacje), ale ich nie mierzono.
- Podziału na płeć / tier / nawierzchnię w werdykcie (pooled w rodzinie);
  rynki serwisu Superbetu to prawie wyłącznie TOUR (430 z 468 meczów) i CH.
- Poziomu zawodników w komórce: mecze dwóch "ocenionych" zawodników mają
  średni rezyduum logitu serwisu +0.05 (komórka zawiera słabszych) - nie
  poprawiano.
- Reguły Superbetu dla super tie-breaka w gemach (konwencja pipeline'u: 1 gem).
