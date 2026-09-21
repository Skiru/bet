# Audyt kuponu 2026-09-02 — dlaczego to przegrywa i co z tym zrobić

Rozliczenie kuponu `runs/2026-09-02/2026-09-02_kupony.md` (15 singli + 8 kuponów
BB = 47 predykcji) plus 891 rozliczonych wierszy z pięciu wcześniejszych dni.
Wszystkie liczby są odtwarzalne z `scripts/simple/backtest_slate.py`.

---

## 0. Zanim cokolwiek policzyliśmy: rozliczaliśmy mecze w trakcie

Pierwsze uruchomienie backtestu o 20:12 UTC zwróciło „hit 36.4% przy claimed
56.3%, ROI −56.5%”. **Cała ta liczba była artefaktem zegara.** Wszystkie
dwanaście meczów kuponu było wtedy w `2nd_half`, a jedenaście wierszy zostało
ocenionych na podstawie liczników z ~70. minuty. Burnley „przegrał” rożne
powyżej 7.5 przy 3 rożnych, mając jeszcze pół godziny gry.

Powód: `/events/{id}/stats/` odpowiada dla meczu w trakcie dokładnie tak samo
jak dla zakończonego — na samym bloku statystyk nie ma żadnego znacznika.
`match_status` był w tym samym payloadzie, jedno poziom wyżej, obok wyniku,
który ta funkcja i tak już czytała.

Gorzej: `_fetch_one` zapisywał te częściowe liczniki do
`runs/_backtest_actuals.json`, a ten cache leży na dysku na zawsze. Zatruło to
20 wpisów (12 meczów kuponu + 8 innych), które skaziłyby każdy przyszły
backtest każdego przyszłego dnia.

**Naprawione i zweryfikowane:**

* `_is_finished()` czyta `match_status`; mecz, który nie jest w pełnym czasie,
  nie jest ani rozliczany, ani cache'owany. Brak znacznika = nie rozliczamy
  (fail closed — cache przeżywa uruchomienie, które go zapisało).
* Nagłówek raportu podaje liczbę meczów jeszcze nieskończonych osobną linią,
  bo inaczej gubi się wśród ~250 luk „no bzzoiro id”: to problem *czasu*, nie
  pokrycia, i lekarstwem jest poczekać.
* Cache wyczyszczony — 20 zatrutych wpisów usunięte po weryfikacji statusu
  każdego z 34 dzisiejszych meczów obecnych w cache. Zostało 76 wpisów,
  wszystkie potwierdzone jako `finished`.
* 10 testów w `tests/simple_stats/test_backtest_slate.py`.

### Kontrola poprawności rozliczania

Zanim wyciągnęliśmy jakikolwiek wniosek z rozliczeń, sprawdziliśmy, czy
endpoint historii i endpoint statystyk meczu liczą to samo — gdyby historia
podawała węższą definicję strzału niż `/stats/`, każdy wiersz `shots_*` byłby
rozliczany przeciw większej liczbie, niż z której był próbkowany, i całe
poniższe wnioskowanie byłoby artefaktem.

**714 sparowanych obserwacji tego samego meczu, pięć metryk, 100% identyczne**
(`shots_for`, `shots_on_target_for`, `corners_for`, `fouls_for`, `cards_for`;
średnia różnica +0.00). Ścieżka rozliczeniowa jest zdrowa.

---

## 1. Najważniejsza liczba: „VALUE” nie wygrało nigdy

Na 71 rozliczonych wierszach, które pipeline **faktycznie wysłał** w plikach
kuponów z pięciu dni:

| etykieta | n | wygrane | trafienia |
|---|--:|--:|--:|
| **VALUE** (cena ≥ próg — „warte swojej ceny”) | **7** | **0** | **0.0%** |
| PRICED_BELOW_THRESHOLD (odrzucone jako za tanie) | 9 | 7 | 77.8% |
| OFFER_EMPTY | 11 | 7 | 63.6% |
| bez ceny Superbetu | 44 | 36 | 81.8% |

Jedyna etykieta, którą pipeline mówi „to jest warte postawienia”, ma bilans
**0 z 7**. Wiersze, które odrzuca jako wystawione za tanio, wygrywają w tempie
całej populacji.

Ta sama rzecz widziana od strony ceny, na tych samych 71 wierszach:

| cena Superbetu | n | trafienia |
|---|--:|--:|
| < 1.20 | 1 | 100.0% |
| 1.20–1.50 | 5 | 60.0% |
| 1.50–2.00 | 6 | 50.0% |
| **≥ 2.00** | **4** | **0.0%** |

Gradient jest monotoniczny. **Im wyżej rynek wycenia nasz wiersz, tym gorzej
nam wychodzi.** Cena Superbetu nie jest źródłem przewagi — jest korektą naszej
próby. Tam, gdzie bukmacher najbardziej się z nami nie zgadza, mylimy się my.

Charakter tych siedmiu przegranych jest jednoznaczny: sześć z nich to
per-team UNDER na wolumenie (strzały / rożne / strzały celne). Nie były to
bliskie pudła:

```
LOST @2.47  shots_for UNDER 13.5            -> 34    (Remo v Coritiba)
LOST @2.12  shots_on_target_for UNDER 3.5   ->  4    (Preston v Bristol City)
LOST @2.07  shots_for UNDER 12.5            -> 16    (Birmingham v Southampton)
LOST @1.88  corners_total UNDER 8.5         -> 16    (Torino v Monza)
LOST @1.92  shots_on_target_for UNDER 4.5   ->  7    (Remo v Coritiba)
LOST @2.70  corners_for UNDER 4.5           ->  5    (Sheffield United v Bolton)
LOST @1.49  shots_on_target_total OVER 7.5  ->  3    (Lincoln City v Blackburn)
```

### Co już działa

`--rebuilt` (dzisiejszy kod na zamrożonych dossier tych samych pięciu dni)
emituje **zero** wierszy VALUE na 891 rozliczonych pozycji — 69 wycenionych
wierszy, wszystkie PRICED_BELOW_THRESHOLD, żaden powyżej 1.70. Poprawki po
2026-09-01 zamknęły ten archetyp *w piłce*.

**Ale dzisiejszy jedyny wiersz VALUE to tenis** (Sabalenka – Iatcenko, gemy
17.5 OVER @ 2.02), a ścieżka rozliczeniowa nie obsługuje tenisa wcale. Bramka,
która naprawiła piłkę, jest w tenisie nieprzetestowana — i tenis to jedyne
miejsce, gdzie żyje jedyna rekomendacja tego pliku.

---

## 2. Dlaczego przegrały te, które już się skończyły

### FC Thun 0–0 FC Lausanne-Sport — gole 2.5 OVER, 14/18, p_low 0.530 — PRZEGRANE

Próba n=18 rozkłada się tak:

| blok | obserwacje | trafienia | co to naprawdę jest |
|---|--:|--:|---|
| Thun, Super League (comp 15) | 4 | 4 | ✔ to opisuje ten mecz |
| **Thun, europejskie kwalifikacje (comp 8, 7)** | **6** | **5** | ✘ inne rozgrywki |
| Lausanne, Super League (comp 15) | 5 | 2 | ✔ to opisuje ten mecz |
| **h2h z poprzedniego sezonu** | **3** | **3** | ✘ nie ten sezon |

Jedna trzecia próby to mecze Thun w Europie z Lech Poznań, Víkingur Reykjavík
i Dinamo Zagreb — inne rozgrywki, inny profil wariancji. Kolejne 17% to h2h z
poprzedniego sezonu. A blok, który najlepiej opisuje dzisiejszy wieczór — obecna
forma Lausanne w lidze (5, 1, 4, 1, 2) — jest **2/5 i mówi UNDER**.

### Grasshopper Zürich 2–0 FC St Gallen — gole 2.5 OVER, 14/18, p_low 0.513 — PRZEGRANE

| blok | obserwacje | trafienia |
|---|--:|--:|
| GC + St Gallen, Super League | 8 | 7 |
| **St Gallen, europejskie puchary (comp 83, 8)** | **6** | **5** |
| **h2h z poprzedniego sezonu** | **4** | **2** |

Tu jest to jeszcze wyraźniejsze: h2h tej dokładnej pary to **0, 3, 5, 2 —
mediana 2.5, dokładnie na linii**. Blok najbardziej specyficzny dla tego
zestawienia przewidział wynik (padły 2 gole) i został przegłosowany przez sześć
obserwacji z europejskich pucharów St Gallen, które poszły 5/6 na OVER.

**Każda obserwacja ma równą wagę.** To jest wspólna przyczyna obu przegranych.

### Ile to kosztuje w skali całego kuponu

Przeliczenie p_low tylko na podpróbce z **własnych rozgrywek fixture'u i
bieżącego sezonu**:

| # | mecz | rynek | wysłane n / hits / p_low | te same rozgrywki n / hits / p_low | delta |
|--:|---|---|---|---|--:|
| 3 | FC Thun – Lausanne | gole 2.5 | 18 / 14 / 0.530 | 9 / 6 / 0.354 | **−0.176** |
| 10 | Millwall – Wrexham | gole 3.5 U | 12 / 11 / 0.548 | 7 / 5 / 0.359 | **−0.189** |
| 4 | Flamengo – Mirassol | gole 3.5 U | 20 / 16 / 0.517 | 14 / 9 / 0.388 | −0.129 |
| 5 | Burton – Wimbledon | gole 3.5 U | 11 / 11 / 0.588 | 7 / 6 / 0.487 | −0.101 |
| 14 | Motherwell – Dundee Utd | gole 0.5 | 16 / 14 / 0.640 | 12 / 10 / 0.552 | −0.088 |
| 2 | WBA – Charlton | gole 1.5 | 12 / 10 / 0.552 | 7 / 6 / 0.487 | −0.065 |
| 11 | Grasshopper – St Gallen | gole 2.5 | 18 / 14 / 0.513 | 9 / 7 / 0.453 | −0.061 |
| 6 | Motherwell – Dundee Utd | rożne 7.5 | 14 / 11 / 0.520 | 12 / 9 / 0.468 | −0.053 |
| 9 | Reading – Mansfield | rożne 7.5 | 9 / 8 / 0.524 | 7 / 6 / 0.487 | −0.037 |
| 8 | Luton – Stockport | gole 1.5 | 11 / 11 / 0.635 | 10 / 9 / 0.596 | −0.039 |
| 7 | Quindío – Llaneros | gole 0.5 | 12 / 12 / 0.757 | 11 / 11 / 0.741 | −0.016 |
| 15 | Burnley – Middlesbrough | rożne 7.5 | 10 / 9 / 0.544 | 8 / 7 / 0.529 | −0.015 |
| 12 | Flamengo – Mirassol | rożne 11.5 U | 27 / 20 / 0.553 | 15 / 13 / 0.621 | +0.068 |
| 13 | Burnley – Middlesbrough | gole 0.5 | 10 / 9 / 0.596 | 8 / 8 / 0.676 | +0.080 |

**12 z 14 wierszy spada**, a oba rozliczone przegrane siedzą w grupie z
największym spadkiem. Zastrzeżenie: n spada do 7–9, co jest chude, i dwa
wiersze rosną — to nie jest gotowa poprawka, tylko pomiar rozmiaru problemu.

---

## 3. Bramka „stary sezon” nie widzi bloku h2h

`scope_values` odrzuca obserwację jako `STALE_SEASON` tylko wtedy, gdy ma ona
`season_id` różny od bieżącego. Blok h2h od bzzoiro **nie ma ani
`competition_id`, ani `season_id`** — i to nie jest wyjątek:

* obserwacji h2h w dzisiejszych dossier: **2058**
* bez `competition_id`/`season_id`: **1933 (93.9%)** — dla porównania bloki
  l10: 8.7%
* z sezonu poprzedniego (przed 2026-07-01): **1867 (90.7%)**
* z tego niewidocznych dla bramki: **1751**

Czyli: `STALE_SEASON` odrzucił dziś 16 198 obserwacji z bloków l10 i **~0** z
h2h, mimo że 91% h2h to poprzedni sezon. Reguła „nie wiemy, z jakich rozgrywek
to było, więc nie wyrzucamy” jest rozsądna jako rzadki fallback (i tak jest
udokumentowana), ale dla całego bloku h2h jest ścieżką *domyślną*.

Skutek jest podwójny: te obserwacje wchodzą z pełną wagą **i** podnoszą n, co
zacieśnia przedział Wilsona. Na wierszach kuponu to typowo 10–25% próby
(WBA 2/12, Motherwell rożne 3/14, Grasshopper 4/18, Luton 2/11).

Analityk wyłapał to ręcznie w dwóch przypadkach — „a single 19-corner h2h
observation” (Reading) i „h2h of this exact pairing ran 8, 5, 6” (Motherwell)
— czyli defekt jest na tyle duży, że widać go golym okiem w prozie.

---

## 4. Bramka „trywialny UNDER” nie złapała dziś ani jednego wiersza

`is_trivial_under(row)` to `direction == "UNDER" and line <= 1.5`. Reguła jest
zawiązana na *numerze linii*, więc nie widzi:

* `goals_1h_total UNDER 4.5` @ **1.002** — „mniej niż 5 goli w pierwszej
  połowie”, zmierzona baza 98.5%,
* `goals_total OVER 0.5` @ **1.009** — trywialne po stronie OVER, której
  reguła nie obejmuje wcale.

**Wynik na dzisiejszym pliku: reguła linii złapała 0 z 47 pozycji. Reguła
zawiązana na cenie (< 1.20) łapie 32 z 47** — w tym 27 z 32 nóg Bet Buildera i
4 z 15 singli.

Rozkład cen nóg BB: **41% poniżej 1.05**, 85% poniżej 1.15, zero nóg
osiągających swój własny `min_acceptable_odds`. Iloczyn nóg (naiwny, czyli
zawyżony — korelacja obniża prawdziwą cenę) dla 7 z 8 kuponów wypada między
1.13 a 1.39.

### Że to jest realny koszt, a nie estetyka — 2026-09-01 rozliczone po nogach

Dodaliśmy rozliczanie nóg BB (`--legs`); wcześniej **32 z 47 predykcji kuponu
nie były mierzone nigdy**. Na 2026-09-01: nogi 24/27 = 88.9% trafień, ale ROI
na cenach nóg **−3.1%**. Po kuponach:

```
#1 Rochdale – Shrewsbury      DEAD  ← corners_total OVER 6.5 -> 4   @1.17
#2 Sheffield Utd – Bolton     ALL LANDED   iloczyn 1.38
#3 Lincoln – Blackburn        DEAD  ← goals_total OVER 0.5 -> 0     @1.05
#4 Huddersfield – Oxford      DEAD  ← goals_2h_total UNDER 3.5 -> 4 @1.05
#5 Fleetwood – Oldham         ALL LANDED   iloczyn 1.27
#6 Preston – Bristol City     ALL LANDED   iloczyn 1.92
#7 Cheltenham – York          ALL LANDED   iloczyn 1.38
#8 Chesterfield – Gillingham  ALL LANDED   iloczyn 1.12
```

5 z 8 kuponów weszło w całości. Zwrot: 1.38+1.27+1.92+1.38+1.12 = **7.07 na
8 postawionych = −11.6%**, i to licząc iloczyn naiwny, czyli za wysoki.

**Wszystkie trzy kupony zabiła noga wyceniona na 1.05–1.17.** Noga za 1.05
dodaje 5% do wypłaty i ~5–8% szansy unieważnienia całego kuponu. Jest ujemna,
chyba że jej prawdziwe prawdopodobieństwo przekracza ~95% — a `goals over 0.5`
to zmierzone 95.1%, czyli dokładnie na granicy, i w Lincoln – Blackburn padło
0:0.

---

## 5. p_low jest zbyt konserwatywne na populacji i zbyt optymistyczne na tym, co wybieramy

To jest sprzeczność, której nikt dotąd nie zestawił obok siebie.

Na **całym zbiorze kandydatów** (`--rebuilt`, 891 rozliczonych wierszy) p_low
zaniża o +15 do +23pp w każdym koszyku — dokładnie tak, jak opisuje komentarz
w `bet_builder_draft.BAR_BASES`:

```
p_low 0.50-0.55  n= 87  claimed 0.528  realised 0.747  (+0.219)
p_low 0.55-0.60  n=162  claimed 0.574  realised 0.809  (+0.234)
p_low 0.60-0.70  n=184  claimed 0.638  realised 0.842  (+0.205)
p_low 0.70-0.85  n=450  claimed 0.743  realised 0.896  (+0.152)
```

Na **15 wierszach, które faktycznie wyszły** (`--recorded`, 71 rozliczonych)
p_low **zawyża** w każdym koszyku poniżej 0.70:

```
p_low 0.50-0.55  n=  2  claimed 0.524  realised 0.500  (-0.024) OVERSTATED
p_low 0.55-0.60  n=  9  claimed 0.571  realised 0.222  (-0.349) OVERSTATED
p_low 0.60-0.70  n=  7  claimed 0.640  realised 0.571  (-0.069) OVERSTATED
```

Wiersz z p_low 0.55–0.60 wygrywa 81% czasu w populacji. Ten sam wiersz
*wybrany do kuponu* wygrywa 22%. **Selekcja jest antypredykcyjna** — w każdym
koszyku p_low ranking wybiera najgorszych jego członków, bo ranking wybiera po
nadwyżce ceny nad progiem, a wysoka cena znaczy, że bukmacher uważa to za
mniej prawdopodobne.

To jest ten sam mechanizm co „VALUE 0/7”, tylko zmierzony na całej dystrybucji.

### Skutek uboczny: próg jest nieosiągalny

Ponieważ `min_acceptable_odds = (1/p_low) × margines`, zaniżenie o 23pp windu-
je żądaną cenę o 0.848/0.613 = **1.38 przed** marginesem tierowym, więc
faktyczne żądanie to 1.45–1.52, nie reklamowane 1.05–1.10. Dziś:
**14 z 15 singli i 0 z 32 nóg** jest „poniżej progu”. Plik dostarcza jeden zakład.

---

## 6. Miara zewnętrzna: ile z 47 predykcji było w ogóle warte swojej ceny

Wycena każdej pozycji przeciw **zmierzonej bazie** z 344 zakończonych meczów w
`runs/_backtest_actuals.json` — bez żadnej informacji o drużynach:

| | pozycji |
|---|--:|
| cena bije bazę populacyjną (edge > +2%) | **4** |
| około fair (±2%) | 13 |
| **poniżej bazy populacyjnej** | **25** |
| brak miary (tenis, rynki per-team/gracz) | 5 |

Zawężone do rozgrywek, w których kupon faktycznie siedzi (Championship +
League 1 + League 2, 60 zakończonych meczów), 15 pozycji EFL: **2 bije bazę,
7 poniżej, 6 fair**. Dwie, które biją:

* **S2** WBA – Charlton, gole 1.5 OVER @ 1.24 (baza EFL 85.0% → fair 1.176,
  **+5.4%**) — czyli wiersz #2, oznaczony „poniżej progu”, był grywalny.
* **BB8.4** Burnley – Boro, kartki 5.5 UNDER @ 1.27 (baza 89.7% → fair 1.115,
  **+13.9%**) — najsilniejsza pozycja w całym pliku, zakopana jako
  poddprogowa noga Bet Buildera.

Zastrzeżenie: baza populacyjna miesza rozgrywki i jest testem podłogi, nie
wyceną fair. Wiersz poniżej bazy nie jest automatycznie zły, jeśli fixture jest
naprawdę bardziej skrajny niż średnia. Ale kierunek dowodu jest jednoznaczny, a
jedyny wiersz oznaczony VALUE nie ma miary wcale.

---

## 7. Plan poprawek

Kolejność jest kolejnością siły dowodu, nie łatwości.

### Zrobione w tej sesji

1. **Bramka pełnego czasu w rozliczaniu** (`_is_finished`) + wyczyszczenie 20
   zatrutych wpisów cache + osobna linia raportu o meczach w trakcie. 10 testów.
2. **Rozliczanie nóg Bet Buildera** (`--legs`, `settle_slip_legs`). 32 z 47
   predykcji kuponu nie były mierzone nigdy. 6 testów.
3. **`--bar-basis {p_low,p_central}`** przepchnięte do `backtest_slate.py`.
   `BAR_BASES` istnieje po to, żeby paper-tradować ramię `p_central`, a do teraz
   nie dawało się go rozliczyć wcale — flaga była zdefiniowana w
   `build_coupons`, ale żaden backtest jej nie podawał.

### P1 — selekcja, bo to ona kosztuje

4. **Przestać rankować po nadwyżce ceny.** Zmierzone: VALUE 0/7, a hit rate
   spada monotonicznie z ceną (100% → 60% → 50% → 0%). Cena bukmachera jest
   korektą naszej próby, nie przewagą. Ranking powinien iść po sile dowodu
   (n, zgodność między dostawcami, dopasowanie rozgrywek), a cena powinna być
   *filtrem* („nie stawiaj poniżej fair”), nie *sortowaniem*.
5. **Bramka trywialności zawiązana na cenie, nie na linii.** `is_trivial_under`
   → `is_trivial(row)`: odrzuć/zdegraduj, gdy `superbet_price < 1.20`
   niezależnie od kierunku i linii. Dziś: 0 złapanych vs 32 z 47. Trzy z ośmiu
   kuponów z 2026-09-01 zabiła noga za 1.05–1.17.
6. **Nie budować Bet Buildera z nóg poddprogowych.** Dziś 0 z 32 nóg osiąga
   własny `min_acceptable_odds`, a plik i tak emituje 8 kuponów opisanych jako
   „trzymane tylko jako kontekst”. Kupon, którego żadna noga nie jest typem,
   nie powinien się drukować — albo powinien mieć minimum nóg *powyżej* progu.

### P2 — próba

7. **Dopasowanie rozgrywek jako waga, nie jako filtr.** Oba dzisiejsze
   rozliczone przegrane mają ⅓ próby z europejskich pucharów. Twarde odcięcie
   zbija n do 7–9 (za chudo), więc właściwa forma to waga malejąca dla obcych
   rozgrywek — analogicznie do tego, jak `venue` jest priorem, nie splitem
   (patrz `[[venue-is-a-prior-not-a-split]]`). Wymaga mapy „które comp_id są
   pokrewne”, budowanej pinami, tak jak `config/observation_scope.json`.
8. **Zamknąć dziurę w bramce sezonu dla h2h.** 1751 z 2058 obserwacji h2h to
   poprzedni sezon, niewidoczny dla `STALE_SEASON`, bo bzzoiro nie stempluje
   bloku h2h. Fallback datowy: gdy `competition_id`/`season_id` są puste, ale
   `match_date` jest znana, porównaj z najstarszą datą wśród obserwacji
   oznaczonych jako bieżący sezon w tej samej próbie. Używa wyłącznie
   informacji z próby, tak jak sam cel sezonowy.
9. **Rozliczanie tenisa.** Jedyna rekomendacja dzisiejszego pliku to tenis, a
   backtest nie obsługuje tenisa wcale — bramka, która naprawiła VALUE w piłce,
   jest tam nieprzetestowana. Ścieżka istnieje i jest tania: `total_games`
   pochodzi z tennis-abstract (`service_games` + `return_games`) i
   espn-tennis, oba adresowane nazwą, więc rozliczenie po kluczu
   (gracz, przeciwnik) — tym samym, którego używa `_tennis_match_key` —
   działa dzień po meczu.
10. **Pooled estimator dla mismatchu.** Wiersz Sabalenka – Iatcenko twierdzi
    p_central 82.5% dla gemów 17.5 OVER przy cenie 2.02 (49.5%). Próba to
    mecze Sabalenki z zawodniczkami z czołówki (22, 16, 20, 32, 19, 18) i mecze
    Iatcenko z jej rówieśniczkami (18, 28, 20) — ani jedna obserwacja nie
    opisuje spotkania faworytki z kwalifikantką, a taki mecz to 15–17 gemów.
    To znany defekt (`[[pooled-estimator-targets-wrong-quantity]]`), ale tutaj
    produkuje **jedyny** typ w pliku.

### P3 — higiena, sprawdzone i niepilne

11. `current_season` jest kluczowane samym `competition_id`, podczas gdy pin
    zakresu jest kluczowany `(provider, competition_id)`. Sprawdzone na
    dzisiejszych danych: **0 kolizji na 41 comp_id** (bzzoiro używa małych
    intów, highlightly wielkich), więc to defekt latentny, nie aktywny. Warto
    domknąć przy okazji, nie osobno.
12. Filtr powierzchni w tenisie jest jednostronny: tennis-abstract podaje
    `surface`, espn-tennis podaje `null`, więc obserwacje espn nie są nigdy
    filtrowane po powierzchni. Dziś bez szkody (wszystkie mecze espn Sabalenki
    były na twardej), ale bramka działa tylko na połowie dostawców.
