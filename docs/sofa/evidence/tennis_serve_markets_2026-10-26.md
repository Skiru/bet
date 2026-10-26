# Asy, podwójne błędy i punkty serwisowe na liniach Superbetu - czy da się je włączyć (pomiar 2026-10-26)

Pomiar tylko do odczytu: nic nie zainstalowano, żaden przełącznik nie zmieniony,
żaden wiersz bazy nie zapisany. Wszystkie przedziały: 95%, losowanie całych
**meczów** (nie nóg). Skrypty i dane robocze (scratch):
`/private/tmp/claude-501/-Users-mkoziol-projects-bet/031df3fd-91c0-4fd8-900a-a8653fb9ff38/scratchpad/`
(`extract.py` wyciąga wiersze z `sofa_settled_row`, `m2.py` .. `m6.py` pomiary,
`hist.py` historia replayu). Uruchomienie: `.venv/bin/python <skrypt> <scratch>`
(m2/m3), pozostałe bez argumentów; `extract.py` i `hist.py` z `S=<scratch>
PYTHONPATH=src:.`.

## Werdykt

**KEEP OFF dla wszystkich rodzin; żadna reguła "ENABLE ONLY dir + band" nie
przechodzi.** Powód jest ten sam co 10-17 / 10-19, teraz na 20 367 liniach /
312 meczach (zamiast 12-64 meczów):

1. Prawdziwy środek SHEET (`p_central` rozliczonych wierszy) na liniach Superbetu
   jest **gorszy od ceny i gorszy od stałej**; przy p >= 0.70 zawyża o 17-26 pp.
2. Krzywa z historii nie naprawia: krzywa z całej drabinki zawyża tak samo
   (-22 pp), a krzywa z linii rynkowych **nigdzie nie dochodzi do 0.70** - więc
   nic by nie wydrukowała.
3. Jedyne nogi, które przechodzą bramki po rekalibracji (walk-forward z ceną),
   to krótkie ceny, gdzie "pewność" to w istocie cena bez marży; realizują się
   w cenie (ROI +3.3% [-1.8, +8.4]), model nic nie dodaje. To nie jest pewność
   "ze statystyk" (zasada: statystyki odróżniają dobre 1.20 od złego 1.20).
4. Jedyny sygnał - UNDER podwójnych błędów realizuje się powyżej ceny (ROI +6.8%
   [+0.9, +13.5], 3 215 nóg / 311 meczów) - jest niestabilny (połowa A +12.5%,
   połowa B +1.6% [-6.6, +9.5]), wybrany po obejrzeniu danych, ma pewność ~0.59
   (< 0.70, czyli i tak nic by nie przeszło bramki) i może być artefaktem źródła
   (patrz Podejrzenia).

## 1. Inwentarz danych

Źródło: `sofa_settled_row`, `run_date` ustawione (żywe), sport tennis, rynki
`aces*`, `double_faults*`, `serve_points*`, WIN / LOSS, `offered_odds` obecny:
**20 367 wierszy (19 342 w parach OVER/UNDER z tej samej linii), 312 meczów,
36 dni z danymi (2026-09-18 .. 2026-10-25; 09-28 i 10-14 puste)**. Dzienne
liczby: od 54 (09-19) do 1 198 (10-20), zwykle 500-1 000. Obie strony zawsze
kwotowane (OVER i UNDER każdej linii); marża pary ~8-9% (1/kurs OVER + 1/kurs
UNDER = ~1.09). Na jeden (mecz, rynek, zawodnik) Superbet daje najczęściej
**jedną** linię (7 326 z 8 067 trójek; reszta 2-5 linii).

Wiersze na rodzinę (OVER; UNDER tyle samo): aces_for 875, aces_total 442,
aces_set1/2_for ~640, aces_set1/2_total ~320, to samo dla double_faults i
serve_points (18 rynków x 2 kierunki = 36 komórek). Pełna tabela per rynek /
kierunek: wynik `m2.py` (sekcja 2).

Historia (replay `cache-calibration` w `sofa_settled_row`): tylko `aces_for`
(2.06 mln wierszy / 105 tys. meczów), `aces_total`, `double_faults_for`,
`double_faults_total`. Rynków per-set i `serve_points_*` historia **nie ma**
(replay ich nie czyta bez `--tennis-serve-markets`); ich krzywe w pliku to krzywe
"tylko z naszych dni" (50 kluczy, `LIVE_ONLY_CURVE_REFUSED`, nie czytane od 10-24).

Linia a mediana modelu: kwantyle p_central OVER na linii Superbetu 1% / 5% / 25%
/ 50% / 75% / 95% / 99% = 0.11 / 0.21 / 0.37 / 0.50 / 0.63 / 0.79 / 0.89 - linie
leżą blisko mediany modelu, ale w ogonie model "nie zgadza się" z rynkiem (p >=
0.70: 2 778 nóg, 307 meczów). Kursy: mediana 1.85, 5% = 1.42, 95% = 2.57.

Co drukowano: 28 nóg w całości (aces_for 14, double_faults_for 14) w 11
kuponach 10-06..10-24 (`runs/sofa/*/11_coupon.json`, liczone po (mecz, rynek,
zawodnik, linia, kierunek)), od 10-19 jedna noga.

## 2. Szyper SHEET na liniach Superbetu (m2.py, m3.py)

Wszystkie wiersze priced przed meczem (SHEET stats-only; `p_central`
bez ceny). Pooled po: wszystkich liniach Superbetu danej rodziny i kierunku,
meczach 09-18..10-25, bez rozróżnienia klasy. `y - p` = trafione minus średnie
p; `y - 1/kurs` = trafione minus cena (z marżą); ROI przy cenie Superbetu.
Skrót (N nóg = N wierszy; mecze ~304-311 dla `_for`, ~294-306 dla `_total`):

| rodzina | kier. | N | y - p [95%] | y - 1/kurs [95%] | ROI [95%] |
|---|---|---|---|---|---|
| aces_for | OVER | 872 | +2.8 [-2.0, +6.4] | -2.5 [-6.6, +1.4] | -4.8% [-12.6, +4.5] |
| aces_for | UNDER | 872 | -2.8 [-6.7, +1.2] | -6.7 [-11.3, -2.0] | -12.8% [-20.5, -5.3] |
| aces_total | UNDER | 442 | -5.1 [-11.3, +1.5] | -6.9 [-13.0, -0.1] | -12.5% [-24.9, +0.9] |
| double_faults_for | OVER | 874 | -9.9 [-13.6, -5.9] | -12.4 [-16.0, -8.7] | -26.2% [-33.6, -18.5] |
| double_faults_for | UNDER | 874 | +9.9 [+6.5, +13.3] | +2.9 [-0.5, +6.4] | +4.2% [-3.7, +11.4] |
| double_faults_total | OVER | 440 | -15.4 [-21.1, -8.8] | -16.4 [-21.7, -10.6] | -32.4% [-42.1, -23.4] |
| double_faults_total | UNDER | 440 | +15.4 [+9.8, +20.5] | +7.1 [+1.6, +12.5] | +13.2% [+3.0, +23.6] |
| double_faults_set2_total | UNDER | 321 | +21.3 [+15.7, +27.3] | +7.2 [+2.1, +12.0] | +13.0% [+2.9, +23.1] |
| serve_points_for | OVER | 868 | -6.1 [-11.5, -1.3] | -4.3 [-8.7, +0.4] | -8.1% [-18.0, -0.8] |
| serve_points_total | UNDER | 440 | +6.4 [-0.3, +12.4] | -2.8 [-9.2, +3.7] | -5.5% [-17.0, +6.5] |

(pozostałe 26 komórek: `m2.py`; każda ma ROI ujemny lub przedział przez zero
poza double_faults UNDER, patrz niżej). Żadna komórka OVER nie ma dodatniego
ROI z przedziałem wykluczającym zero; 29 z 36 komórek ma `y - 1/kurs` < 0 (punkt, nie przedział).

Przy p_central >= 0.70 (surowo, bez krzywej): aces 1 124 nogi / 264 mecze, trafione
0.533, `y - p` = -25.4 pp [-30.6, -19.8]; serve_points 879 / 236, -26.0 pp
[-32.2, -20.2]; double_faults 775 / 242, -16.9 pp [-22.2, -12.3]. W sumie
(m3.py) 2 778 nóg, trafione 0.548, średnie p 0.781, 1/kurs 0.608, ROI -10.1%.

**Brier / log-loss** (walk-forward po dniach, 7 849 linii OVER / 258 meczów,
2026-09-26..10-25; wartość dodatnia = pierwszy gorszy; m4.py). Pooled po
wszystkich rodzinach, jedna linia na parę (OVER niesie całą informację pary):

- model - cena (bez marży): Brier **+0.0302 [+0.0205, +0.0401]**, log-loss +0.0718
  [+0.0507, +0.0966] - model gorszy od ceny;
- model - stała (stopa trafień z wcześniejszych dni, per rodzina): **+0.0207
  [+0.0116, +0.0304]** - model gorszy nawet od stałej;
- cena - stała: -0.0095 [-0.0132, -0.0059] - cena niesie informację;
- logit(cena, model) - cena: -0.0008 [-0.0033, +0.0017]; kalibracja samej ceny -
  cena: -0.0014 [-0.0038, +0.0011] - **model nie dodaje nic do ceny**.
Każda z 6 rodzin (aces/df/serve x for/total) osobno: model - cena dodatni, wszystkie 6
z przedziałem > 0 (df_for +0.0116 [+0.0048, +0.0192] najmniej źle).

## 3. Poprawka "krzywa z linii rynkowych" (m6.py, h1.py)

(a) Krzywa dopasowana jak dziś, na całej drabince historii (poza zdarzeniami z
żywych dni), odczytana na liniach Superbetu: nogi z krzywą >= 0.70 - **743 nogi
/ 251 mecze, pewność 0.788, trafione 0.580 (-20.8 pp), 1/kurs 0.642, ROI -10.4%**;
po bramce x >= 0.90: 702 / 250, trafione 0.566, ROI -10.5%. Tylko `aces_for/total`,
`double_faults_for/total` (innych rynków historia nie ma).

(b) Krzywa z linii rynkowych (jedna linia na mecz / rynek / zawodnika, najbliższa
p = 0.5), historia 495 842 pozycji, 4 rynki: **żaden kubełek nie dochodzi do
0.70** - maks. trafione w kubełku z n >= 100: aces_for 0.542, aces_total 0.550,
double_faults_for 0.669 (n = 154, p 0.665), double_faults_total 0.536. Co więcej
już na historii p = 0.62-0.67 na linii rynkowej realizuje 0.36-0.57 (aces_for
(0.65, 0.7]: p 0.665 -> 0.498; aces_total (0.6, 0.65]: 0.614 -> 0.365).
Wniosek: rynek wie więcej niż nasz środek, gdy się z nim nie zgadza; krzywa
rynkowa przypisałaby pewność < 0.70 każdej nodze, więc przy bramce 0.70 **nic by
nie wydrukowano** (to nie błąd - to wynik). Ograniczenie: historia z replayu
nie ma znacznika czasu w `sofa_settled_row`, więc krzywa nie jest
walk-forward po dacie; zdarzenia żywych dni (312) wyłączone, nakładanie z historią
minimalne.

(c) Rekalibracja walk-forward na samej cenie i modelu (audyt, NIE źródło krzywej:
żywe dni nie mogą być źródłem krzywej): nogi z p_hat >= 0.70 i p_hat x kurs >=
0.90: **776 nóg / 175 meczów, p_hat 0.770, trafione 0.751, y - pewność -1.9 pp
[-5.6, +1.4], y - 1/kurs +1.9 [-1.6, +5.5], ROI +3.3% [-1.8, +8.4]**. Z tego
UNDER 687 (ROI +4.5% [-0.9, +9.7]), OVER 89 (-6.4% [-19.9, +6.2]); df_for 473 nogi
(+5.3% [-0.7, +11.5]), df_total 194 (+8.1% [-1.2, +16.5]), aces_for 89 (-11.7%
[-24.2, -0.1]). Te nogi to krótkie ceny; ich pewność jest w istocie ceną bez
marży (model nie dodaje - sekcja 2). Realizują się w cenie, ale to nie jest
pewność ze statystyk, a podstawa (cena) nie jest naszą krzywą.

## 4. Werdykt per rodzina (testowano 36 komórek rynek x kierunek, 6 rodzin zbiorczo)

Przy 36 komórkach około 2 spodziewa się przypadkowo wykluczających zero
(jedna na dwadzieścia); poniższe "wykluczające zero" liczono dla `y - 1/kurs`.

| rodzina | decyzja | N nóg / meczów | dowód |
|---|---|---|---|
| aces_for / aces_total (+ per set) | **KEEP OFF** | 875 / 311, 442 / 306 (+ set 637-640 / 304-306, 318-320 / 294-296) | surowo p >= 0.70: -25 pp; UNDER aces_for ROI -12.8% [-20.5, -5.3]; krzywa rynkowa max 0.55 |
| serve_points_* | **KEEP OFF** | 868 / 310 itd. | OVER -8% ROI; UNDER przez zero; brak historii replayu (rynki set i serve_points bez krzywej historycznej) |
| double_faults_* OVER | **KEEP OFF** | 874 / 310, 440 / 305 | -26..-32% ROI, wszystkie 6 komórek ujemne z przedziałem < 0 |
| double_faults_* UNDER | **KEEP OFF (obserwacja)** | 3 215 / 311 (6 komórek razem) | +6.8% [+0.9, +13.5], ale połowa B +1.6% [-6.6, +9.5]; pewność ~0.59 < 0.70; 6 komórek jedna kohorta meczów, nie 6 niezależnych testów; 3 z 6 wykluczają zero na `y - 1/kurs` (df_set2_for, df_set2_total, df_total) |
| nogi "krótka cena" po rekalibracji | **KEEP OFF** | 776 / 175 | ROI +3.3% [-1.8, +8.4], przez zero; to cena, nie statystyka |

Zasada UNDER-df-w-paśmie ceny: UNDER kurs < 1.5 (418 nóg / 129 meczów): trafione
0.792, y - 1/kurs +2.1 [-2.8, +7.0], ROI +2.7% [-3.1, +9.0] - przez zero; pasmo
1.5-1.7: 735 / 245, +4.9 [+0.6, +9.6], ROI +7.8% [+0.9, +14.4] (pewność < 0.70).
Nie dochodzi do progu dowodu przy 36 testach i niestabilności w czasie.

Krótkie ceny wszystkich rynków (m3.py, wszystkie nogi, pooled po rynkach):
kurs < 1.43: OVER 456 / 107 meczów trafione 0.726 vs 1/kurs 0.779 (-5.3 pp
[-11.2, +0.5]), UNDER 562 / 121, -3.8 pp [-9.5, +2.5] - czyli realizują się
**poniżej** ceny o mniej więcej marżę (powyżej ceny bez marży o +2.4 / +3.9
pp). To jest rynek skalibrowany z marżą, nie przewaga; operator akceptuje nogi
realizujące się "w cenie", ale nie ma tu pewności ze statystyk do pokazania.

## 5. Wzór przełącznika (tylko projekt, nic nie zaimplementowano)

Gdyby operator mimo wszystko chciał włączyć rodzinę po pomyślnym nowym teście:

- `bet.sofa.epochs`: nowa stała `TENNIS_SERVE_MARKET_CURVES_FROM_UTC` (domyślnie
  następny dzień 00:00Z), pomocnik "od dnia i zegara budowy" jak
  `TENNIS_ACES_OPPONENT_FROM_UTC`; marker wiersza (np. `tennis_serve_rule`),
  żeby `rebuild_plan` wiedział, czy arkusz ma regułę.
- Pliki: `config/sofa_confidence_calibration.json` (grupa `tennis_serve`
  instalowana przez `install_new_market_curves.py`, ZASTĘPUJE krzywe tych
  rynków), `config/sofa_live_only_curves.json` (50 kluczy trzeba by zdjąć z
  listy odrzuceń TYLKO jeśli krzywe zostaną dopasowane z historii - dziś ich
  nie czyta nic, `LIVE_ONLY_CURVE_REFUSED`), odświeżenie
  `config/sofa_superbet_line_evidence.json` (robi `refresh_line_evidence.py`).
- Flagi refitu: `--tennis-serve-markets --tennis-aces-opponent` w replayu
  (obecnie nigdy przekazywane; `prepare_refit.py install` odmawia refitu bez
  tych flag, jeśli zainstalowana jest osobno dopasowana krzywa
  `requires_replay_flags`), plus **nowy** wybór pozycji: krzywa dopasowana na
  liniach rynkowych (jedna linia / mecz / rynek / zawodnik, najbliższa p = 0.5),
  nie na całej drabince (`lines_for`) - `fit_tennis_serve_curves.py` dziś
  dopasowuje na drabince. Wynik tego pomiaru: taka krzywa nie osiągnie 0.70.
- Dowody linii: tylko obniżają (offset klucza i pułap pasma cen); przy
  zawyżeniu rzędu 20-26 pp wycięłyby prawie wszystko poza krótkimi cenami -
  dokładnie obecne zachowanie (14 wydrukowanych nóg 10-06..10-16 trafione 0.714
  vs pewność 0.759, z model-state). Nowy przełącznik niczego tu nie zmienia, jeśli
  krzywa nie przekroczy 0.70.
- Testy: nowy plik w `tests/sofa/`, wpis w `config/sofa_test_registry.json`
  (`T-TENNIS-SERVE-MARKET-LINE` istnieje - kryterium: nogi >= 0.70 realizują
  >= pewność - 2 pp [95% po meczach] na liniach Superbetu przy N >= 200 nóg /
  100 meczach).
- Wymagany go operatora (instalacja zmienia to, co się drukuje); nie wstecz.

Kryterium ponownego otwarcia (pre-registered propozycja, niezmierzona):
krzywa z linii rynkowych daje kubełek >= 0.70 z n >= 300 w historii **oraz**
walk-forward na liniach Superbetu przy >= 200 nogach / 100 meczach `y - pewność`
>= -2 pp z dolną granicą > -5 pp.

## Podejrzenia (niezmierzone)

- UNDER podwójnych błędów: realizacja 0.59-0.63 przy cenie bez marży 0.51 na
  linii leżącej na medianie modelu; ten sam efekt widać na tych samych 94-188
  zdarzeniach w historii replayu (OVER trafione ~0.31-0.32), a na pozostałych
  ~175 tys. zdarzeń historii ~0.50. Możliwe wyjaśnienia (nie sprawdzone):
  populacja meczów z Superbetu ma mniej podwójnych błędów niż próbka modelu
  (poziom turnieju / nawierzchnia), albo zliczanie Sofascore odbiega od
  rozliczenia Superbetu (dostawca statystyk). Nie sprawdzono rozliczenia
  Superbetu na żywych kuponach.
- Przy asach linie leżą poniżej realizacji (aces_for: linia 5.21, realizacja
  5.91, centrum modelu 5.65) - nie zmierzono, czy to selekcja meczów ze
  statystykami.
- Nie testowano: podziału na klasę (kobiety / puchary), wpływu surfaces, odczytu
  wiersza przez prawdziwe CONFIDENCE (pewność z krzywych + dowodów linii) -
  zastąpiono go surowym p_central i krzywą z historii. Prawdziwy CONFIDENCE
  tylko obniża, więc wynik "KEEP OFF" nie powinien się zmienić na korzyść.
- Historia replayu bez znacznika czasu - krzywa (a) i (b) nie jest
  walk-forward po dacie.
- Wiersze 10-18 i wcześniejsze liczone starszym SHEET (aces opponent włączone
  od 10-17 / 10-18; serve_points / per-set liczone `tennis_serve_markets`
  tylko jeśli SHEET je ceniło tamtego dnia) - nie rozdzielono epok.

## Dodatek (2026-10-26): czy rozjazd w podwójnych błędach to dane?

Szybki pomiar na tych samych 305 meczach z linią `double_faults_total`
(skrypty `df1.py`..`df3.py` w scratchpadzie sesji; bez przedziałów ufności).

- Linia Superbetu: średnio 5,79; wynik ze statystyk Sofascore: średnio 4,97
  (mediana 4); OVER weszło w 32,5% meczów. Dla asów łącznie: linia 10,46,
  wynik 11,17, OVER 49%.
- Rozjazd jest równomierny po koszykach linii (OVER 0,31-0,35 w każdym z
  czterech), więc to nie jest skutek jednej skrajnej grupy.
- Zero podwójnych błędów w sumie: 9 z 305 meczów - brak stat-placeholderów
  jako przyczyny.
- Po czasie: różnica linia - wynik malała: 09-24..30 -1,27; 10-01..07 -0,95;
  10-16..23 -0,59; od 10-24 -0,60 (OVER 0,21 -> 0,45). Zgodne z poprawianiem
  linii przez Superbet albo ze zmianą składu turniejów - nierozstrzygnięte.
- Wewnętrzna zgodność Sofascore (173 mecze z point-by-point): zlicza
  pointDescription 2 = podwójny błąd średnio 4,45 vs 4,87 w statystykach
  (|różnica| 0,45), asy (kod 1) 8,16 vs 10,86. Statystyki są WYŻSZE niż drugie
  źródło Sofascore, więc nasz zapis nie zaniża podwójnych błędów względem
  Sofascore. Nie mówi to nic o źródle rozliczenia Superbetu (drugiego źródła
  nie mamy).

Wniosek: brak dowodu na błąd po naszej stronie liczenia; rozjazd wygląda na
cechę linii Superbetu, słabnącą. Hipoteza "rynek zaniża UNDER" wymaga testu
w przód (od 10-26), nie wydruku.
