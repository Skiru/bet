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
