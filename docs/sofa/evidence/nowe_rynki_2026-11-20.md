# Nowe rynki Superbetu: co mamy w statystykach i da się łatwo dodać - 2026-11-20

Pytanie operatora (2026-11-20): dla każdego sportu znaleźć rynek Superbetu, którego
pipeline nie czyta, a który da się policzyć z naszych statystyk i łatwo dodać.

Przegląd był tylko do odczytu: w kodzie, konfiguracji i kuponie nic nie zmieniono.
Raport przeszedł niezależną weryfikację (sekcja 5). Wersja tutaj zawiera jej
potwierdzone poprawki.

**Materiał:**
- ceny rynków nieczytanych z `runs/sofa/<d>/unmapped_prices/`, zapisywane przez
  OFFER (piłka, tenis) oraz SHADOW / CS2 (od 2026-11-05: hokej, kosz, siatkówka,
  CS2), z dni 2026-11-06 .. 11-19 (tenis od 10-17);
- wyniki, statystyki i historia z `data/sofa.db`, tylko do odczytu.

Każdy sport zmierzył osobny agent. Raporty cząstkowe i skrypty leżą w
`docs/sofa/evidence/nowe_rynki_2026-11-20/` (`hockey/`, `football/`, `tennis/`,
`basketball/`, `cs2_vb/`), skrypty weryfikacji w `weryfikacja/`. Skrypty liczyły z
katalogu roboczego, więc ścieżki w ich środku mogą na niego wskazywać.

Oznaczenia:
- **[spr.]** - liczbę przeliczyłem drugi raz sam;
- **[wer.]** - liczbę potwierdził albo poprawił niezależny weryfikator.

## 1. Odpowiedź wprost

**Nie ma rynku, na którym stawianie oferowanej strony daje zysk po 12% podatku.**
Najlepszy wynik przed podatkiem to około zera. Większość kandydatów jest
skalibrowana i drukowałaby nogi mniej więcej po cenie, czyli więcej pozycji, ale
nie lepszy wynik. Jeden wyjątek jakościowy jest w tenisie. Statystyki odróżniają tam
dobry szczebel od złego przy tej samej cenie, tylko nogi jest bardzo mało (sekcja
2).

| sport | najlepszy kandydat | nogi przez bramki | kalibracja nóg | model a cena | ROI przed / po 12% podatku | werdykt |
|---|---|---|---|---|---|---|
| hokej | NHL „z dogrywką i rzutami karnymi”: suma, handicap, gole drużyny (617 / 613 / 621 / 653) | ~44 / dzień przy krzywych NHL z historii, ~59 przy zainstalowanych regulaminowych [wer.]; ~6 na mecz | deklarowane 0,782, trafione 0,791 [0,745; 0,834] | Brier +0,0010 [-0,0046; +0,0062], remis | -3,4% [-9,4; +1,9] / -15,0% | **kandydat nr 1 na pokrycie** |
| tenis | nowy format serwisu „N+” (asy, podwójne błędy, suma; mecz / set / gracz) | 85 nóg w 26 dni na 34 meczach; w 13 dniach zero | 0,746 / 0,770 w paśmie 0,70-0,80 | cena przeszacowuje o ~20 pp; model wybiera szczeble zwracające ~0,99 tam, gdzie wszystkie po tym kursie zwracają 0,70-0,82 [spr.] | -0,8% [-17,2; +12,7] / -12,7% | **statystycznie najciekawszy**, wolumen znikomy |
| piłka | handicap połowy, strona +L („1./2.połowa - handicap”; +0,5 to podwójna szansa połowy) | ~130 nóg / dzień, ale tylko ~55 meczów (2,33 nogi na mecz) [wer.] | 1H -3,1 pp [-6,0; -0,5], **przeszacowuje**; 2H -1,1 pp [-3,7; +1,5] | cena lepsza: 1H +0,0041 [+0,0017; +0,0065], 2H +0,0031 [+0,0007; +0,0058] | 1H -5,7%, 2H -2,7% [-5,9; +0,8] / -14..-17% | kandydat nr 3 |
| siatkówka | „1.Set/Mecz”: faworyt wygra 1. seta i mecz | 68 nóg w ~14 dni | historia 0,823 / 0,816 | Brier +0,0043 [-0,0006; +0,0093] | +7,6% [-5,3; +20,0] / -5,3% | plus to ogólny efekt faworyta (sekcja 3) |
| CS2 | „Liczba dogrywek” poniżej 0,5 (seria) | 48 nóg z 52 serii | BO3: 0,756 / 0,744 | Brier +0,0057 [-0,0023; +0,0148]; model nie różnicuje meczów | **-16,0% [-34,3; -0,1] / -26,1%** [wer.] | nie |
| kosz | double-double „Nie” | ~33 / dzień | 0,872 / 0,859 | Brier +0,0095 [+0,0043; +0,0153], cena lepsza | -2,9% [-6,6; +0,5] / -14,6% | nie |

Bramki: pewność ≥ 0,70, pewność × kurs ≥ 0,90, marża ≤ 15%, kurs ≥ 1,087 (bez górnej
granicy). Nogi jednostronne przechodzą tylko przez `one_sided_single`. ROI liczone
na ostatnim kursie przed startem.

Liczby nóg nie uwzględniają obniżenia przez dowody liniowe, świeżości cen, deduplikacji
zdarzeń ani odczytów analityków. W hokeju liczba nóg zależy od tego, jakie krzywe
zostałyby zainstalowane.

## 2. Sport po sporcie

### Hokej - NHL z dogrywką i karnymi (`hockey/raport_hokej.md`)

**Co to jest.** Rynki 617 (suma goli), 613 (handicap) oraz 621 / 653 (gole drużyny),
wszystkie z dogrywką i karnymi. Wyłącznie NHL: 108 meczów w 11-06..11-20, 2-12
dziennie. Pary dwustronne. Marża: 613 / 617 7,6%, gole drużyny 6,6%, wszystkie pary
7,2% [wer.].

**Jedyne pełnomeczowe linie goli NHL.** W NHL Superbet nie wystawia regulaminowej
sumy, handicapu ani goli drużyny na cały mecz [spr.: w snapshotach SHADOW 64 mecze
NHL z 11-10..11-19 nie mają żadnej linii `total` / `handicap` / `team_total`; inne
ligi mają ich 45 438 / 21 986 / 58 630]. Linie tercji NHL czytamy [wer.].

**Rozliczenie.** Wynik końcowy = wynik regulaminowy + 1 gol dla zwycięzcy dogrywki
lub karnych.
- Sofascore `current` spełnia tę regułę w 6 289 z 6 290 meczów NHL w cache. Wyjątek
  to defekt danych (14198584) [wer.].
- Zgodność z wynikiem Superbetu: 105 / 105.
- Trzy mecze rozstrzygnięte karnymi są zapisane jako `overtime` 1/0, a nie jako
  `penalties`. Grader musi więc czytać `current` / `winnerCode` [wer.].
- Regulaminu Superbetu nie przeczytano.

**Połowa tych nóg to zdarzenia regulaminowe.** Remis po 60' ma zawsze parzystą sumę,
a dogrywka zmienia przewagę z 0 na ±1. Dlatego:
- suma 3,5 / 5,5 / 7,5 / 9,5 z dogrywką to dokładnie regulaminowa suma na tej samej
  linii;
- handicap |h| ≥ 1,5 to dokładnie handicap regulaminowy;
- handicap ±0,5 to zwycięzca z dogrywką (630), którego czytamy;
- nowe zdarzenia to tylko sumy 2,5 / 4,5 / 6,5 / 8,5 i gole drużyny.

Weryfikator potwierdził to na 37 739 i 50 319 parach (mecz × linia). Te tożsamości
trzeba dopisać do `leg_identity`.

**Model.** Rozkład regulaminowy z modelu wyniku plus przekształcenie remisu.
- Wada: model zaniża remis po 60' w NHL: 0,175 wobec rzeczywistych 0,228, różnica
  +5,3 pp [3,8; 6,7] na 3 149 meczach. Cena remisu Superbetu daje 0,226.
- Na liniach z dogrywką ten błąd znosi się z zawyżoną liczbą goli (6,12 wobec 5,96).
  To przypadek, a nie zasługa modelu.

**Wdrożenie.**
- Około dnia pracy plus refit hokeja na kopii bazy, który wymaga zgody operatora.
- Przełącznik od 00:00Z następnego dnia.
- Większość meczów startuje 00:00-03:30Z, 9 ze 108 o 17-23Z [wer.]. Nogi weszłyby
  głównie przez wieczorną przebudowę, a ROI liczono na kursie tuż przed startem. Tego
  przesunięcia czasu nie zmierzono.
- Pułapka refitu: wiersze historii można brać tylko z lig, w których remis po 60'
  nigdy nie jest wynikiem końcowym.

**Odrzucone poboczne.**
- 633 „Wszystkie tercje powyżej 0,5”: w górnym paśmie model przeszacowuje
  (deklaruje 0,704, trafia 0,628).
- 666 / 643 „1. gol”: w cache nie ma kolejności goli w hokeju.

### Tenis - nowy format serwisu „N+” (`tennis/raport_tenis_serwis_N_plus.md`)

**Co to jest.** Od 10-17 Superbet wystawia asy, podwójne błędy i ich sumę jako
jednostronne drabinki „N+”: mecz, set 1 i 2, łącznie i na gracza. Kurs zaczyna się od
1+, przy czym 1+ @ 1,00 jest zablokowane.

**Gdzie.** Format występuje głównie w turniejach Challenger i WTA 125, gdzie
serwisowych rynków wcześniej nie było. W okresie 10-17..11-12 pojawił się też na 46
meczach ATP.
- Stary, dwustronny format „liczba asów” (czytany, wyceniany modelem punktowym)
  idzie za kalendarzem ATP / WTA i zanika z końcem sezonu [spr.: 10-01..10-16 ATP 100
  i WTA 61 meczów; 11-13..11-19 ATP 13 i WTA 4].
- Na żadnym meczu nie ma obu formatów naraz.
- Od 11-13 nowy format jest na 5-57 meczach dziennie, stary na 2-3 [wer.].
- Nowy format to więc **dodatkowe pokrycie niższych turniejów**, a nie utrata
  pokrycia. Wcześniejsza wersja raportu twierdziła inaczej i była błędna.

**Technicznie to samo mapowanie.**
- „N+” = OVER N-0,5 istniejącego klucza.
- Rozliczalnych jest 639 / 696 meczów nowego formatu. 400 losowych ocen zgadza się
  z surowymi statystykami.
- Model punktowy wycenił 696 / 696 meczów (plus 22 mecze kontrolne ze starego
  formatu, zgodność z SHEET r = 0,993).

**Cena jest bardzo droga.** Zwrot ze stawek na wszystkich szablonach wynosi ~57,5%,
na starym formacie 94%. Sprawdzone inną metodą, na samych drabinkach meczowych ze
statystyk `ALL` z 621 meczów, z filtrem przed startem [spr., wer.]:

| drabinka meczowa | trafienie | cena implikuje | zwrot |
|---|---|---|---|
| asy | 0,536 | 0,675 | 0,778 |
| podwójne błędy | 0,435 | 0,682 | 0,61 |

**Statystyki rozróżniają w obrębie ceny, i tylko tu było to wyraźnie widać.** Na
kursach 1,09-1,29 wszystkie szczeble zwracają 0,819 (asy) i 0,695 (podwójne błędy)
[spr.]. 85 nóg wybranych przez model zwraca 0,992, czyli -0,8% [-17,2; +12,7].
Brier modelu jest lepszy od 1/kurs: -0,035 [-0,042; -0,028]. Przewaga leży jednak po
stronie, której Superbet nie oferuje (UNDER), więc grać jej nie można.

**Dlaczego nie teraz.**
- 85 nóg w 26 dni, z czego 13 dni bez żadnej, a 37 nóg wypadło w dwóch dniach.
- Przedział ROI ±15 pp.
- Po podatku -12,7%.

**Pozostałe rynki tenisowe.**
- „Tiebreak w X. secie” to `games_setX_total` 12,5, który już czytamy na 167 / 168
  tych meczów [spr., wer.]. Duplikat.
- „Każdy z zawodników wygra seta” to `sets_total` OVER 2,5, czytane.
- Największy nieczytany rynek tenisowy, „1. gem serwisowy - zwycięzca” (~600 meczów
  w strefie), wymaga danych punkt po punkcie i był odrzucony 10-14. Tu go nie mierzono.

### Piłka - handicap połowy (`football/raport_pilka.md`)

**Duplikaty.** Pełnomeczowy „Handicap” i „Handicap 1X2” w strefie druku to w 96,5% i
97,7% zdarzenia, które już czytamy [wer.]. „Remis w obu połowach: tak” to HT/FT X/X,
też czytane.

**Kandydat.** Handicap połowy: para dwustronna, liczą się tylko gole tej połowy [spr.
kształt: pary „A (-L)” / „B (+L)”, linie ±0,5 / ±1,5 / ±2,5].
- Strona -0,5 to wynik połowy, już czytany.
- Bramki przechodzi strona +L: głównie +0,5, czyli podwójna szansa połowy, potem
  +1,5.
- Nieczytany rynek „1./2.połowa - podwójna szansa” to to samo zdarzenie co +0,5 i ma
  około dwa razy większe pokrycie. Oba trzeba związać w `leg_identity` [wer.].

**Liczby.**
- Rozliczenie z wyniku 90' i `period1` działa dla 96,9% meczów.
- Historia 06-01..10-20 (40 025 meczów): surowe p symulatora skalibrowane, 1H w
  granicach ±1 pp. Wyjątek: 2H +0,5 z -1,6 pp.
- Na żywo 1H przeszacowuje: -3,1 pp [-6,0; -0,5], przedział nie obejmuje zera [wer.].
- Cena jest lepsza od modelu, z przedziałem nad zerem.

**Pozostali kandydaci piłkarscy.**
- „Wygra obie połowy: nie”: nowe zdarzenie, ale -5,3 pp na nogach.
- „BTTS & powyżej L”: przeszacowuje także w historii.

**Wdrożenie.**
- Klucze `result_1h_handicap` / `result_2h_handicap`. Nie `handicap_*`, bo ten
  prefiks oznacza rynek pochodny z próbek.
- Zmiany w OFFER, SHEET (symulator ma już gole per połowa), SETTLE, `leg_identity`,
  krzywych i backfillu dowodów liniowych.
- Zakres mały.

**Nie zmierzono** [wer.]: „przedział goli”, „podwójna szansa & liczba goli”,
„1.połowa liczba goli lub 2.połowa”, europejski handicap połowy.

### Siatkówka (`cs2_vb/raport_cs2_siatkowka.md`)
- „Czy będzie 4./5. set?” to suma setów 3,5 / 4,5. Na 95 z 96 meczów obie linie są w
  snapshotach SHADOW, a ceny bez marży różnią się o +0,012 / +0,008 [wer.].
- **Handicap punktowy 1. seta.** Cena nigdy nie daje ≥ 0,70 (najwyższe uczciwe p to
  0,678), ale model tak. 65 nóg przeszłoby bramki i przeszacowuje o -15,1 pp
  [-29,5; -0,8] [wer.]. Odpada z powodu przeszacowania, nie braku nóg.
- **Punkty drużyny:** uczciwe p 0,48-0,52.
- **„1.Set/Mecz”:** model rally liczy go wprost i jest skalibrowany na historii
  (3 359 meczów), kursy nóg 1,12-1,63.

### CS2 (`cs2_vb/raport_cs2_siatkowka.md`)
- **„Liczba dogrywek” poniżej 0,5:** ~4 serie dziennie po ~1,26. Rozliczenie: mapa
  z ≥ 25 rundami to dogrywka.
  - BO3 bez dogrywki to 0,752 na 8 312 seriach [spr.: 0,7523 / 8 312 z
    `cs2_map` / `cs2_series`].
  - Model daje 0,75-0,76 dla każdego BO3, a siła drużyn nic nie wnosi. Nie odróżnia
    więc dobrego 1,26 od złego.
  - Na 48 nogach z bramek ROI -16,0% [-34,3; -0,1] (trafienie 0,667 wobec 1/kurs
    0,794).
- **„Najwięcej rund w meczu” / „podwójna szansa rundy” = handicap rund serii ±0,5.**
  Na 52 z 58 meczów tę linię czytamy tylko od ±1,5, więc ±0,5 jest nieczytana [spr.,
  wer.]. Pomiar dołożony po weryfikacji:
  - model skalibrowany na historii, ≥ 0,70: deklaruje 0,763, trafia 0,774;
  - przy różnicy zdań z ceną wygrywa cena;
  - na czytanych liniach tej rodziny dowód liniowy ≥ 0,70 to 16 / 36 (0,444) [spr.];
  - przy pewności, jaką pipeline by wydrukował, przechodzą 3 nogi w 15 dni (wszystkie
    przegrane).

  Nie warto.

### Kosz (`basketball/raport_kosz.md`)
- **Kamienie milowe „N+” zawodników** to OVER N-0,5 rodzin, które SHADOW już czyta,
  zwykle po tej samej cenie [spr. 11-18, punkty NBA: na 66 parach 47 identycznych, 12
  niższych, 7 wyższych]. W strefie druku przedłużają drabinkę w dół, a tam model
  jest gorszy od ceny (-6,8%).
- **Double-double:** model zna tylko pojedyncze statystyki. Brier gorszy od ceny z
  przedziałem nad zerem.
- **Statystyki drużyn NBA:** cena nigdy nie daje ≥ 0,70. Pewności modelu na tych
  liniach nie mierzono.

## 3. Ustalenia poboczne

1. **Hokej: model zaniża remis po 60' w NHL o 5,3 pp** [3,8; 6,7]. W NHL czytamy 1X2
   regulaminowe, więc może to dotyczyć remisu i podwójnych szans na kuponie. Wpływu
   na wydrukowane nogi nie mierzono, na razie to podejrzenie.
2. **Siatkówka: faworyt wygrywa częściej, niż mówi cena Superbetu.** Na meczach z
   „1.Set/Mecz” 0,826 wobec 0,724, na wszystkich 992 meczach 11-05..11-19 +4,6 pp.
   - To trop z jednego okna, wybrany po obejrzeniu danych.
   - Przegląd 11-05 mierzył zwycięzcę w siatkówce jako gorszego od ceny w Brierze
     (+19,4e-3).
   - Do pogodzenia testem z zamrożonymi regułami.
3. **Tenis „N+”: cena przeszacowuje szanse o ~20 pp na całej drabince.** To jedyne
   miejsce w przeglądzie, gdzie nasz wybór wyraźnie dzieli szczeble przy tej samej
   cenie. Ceny wciąż się zapisują, więc test w przód z zamrożonymi regułami nie
   wymaga zmian w kodzie.
4. **Hokej wymaga reguł tożsamości przed dodaniem** (sekcja 2). Dziś zdarzenia nie
   drukują się podwójnie tylko dlatego, że Superbet nie wystawia w NHL linii
   regulaminowych.

## 4. Metoda i jej granice

**Przesiew** (`nowe_rynki_2026-11-20/screen.py`) definiował „strefę” po cenie: kurs
1,09-1,43 i uczciwe p ≥ 0,70. Służył tylko do wyboru, gdzie szukać. Pomija nogi, przy
których model mówi ≥ 0,70, a cena mniej [wer.]. Pomiary sportów stosowały już
prawdziwe bramki na p modelu. Sformułowania „0 w strefie” znaczą „cena nigdy nie
daje ≥ 0,70”, a nie „nic się nie wydrukuje”.

**Czego nie sprawdzono:**
- regulaminu Superbetu dla dogrywek w hokeju i CS2, „N+” ani handicapu połowy (reguły
  wywnioskowane z cen i wyników);
- dłuższego okna cen: nieczytane ceny sportów mierzonych są zapisywane dopiero od
  11-05, więc przedziały ROI mają szerokość ±5-15 pp;
- pełnej budowy dnia: dowodów liniowych, świeżości cen, deduplikacji i odczytów
  analityków; liczby nóg to szacunek;
- krzywych nowych kluczy dopasowanych tak jak przy instalacji: w piłce n ≥ 100 zamiast
  400 i bez klasy kobiet, w CS2 i siatkówce p modelu z pulowanym offsetem;
- członu terminarza w centrach piłki z replayu (od 11-09), które różnią się od live o
  2-5%;
- danych z dni bez `04_offer.json` (10-24, 10-31, 11-07) przy porównaniu formatów w
  tenisie.

## 5. Weryfikacja

**Moje przeliczenia [spr.]:**

| twierdzenie | jak | wynik |
|---|---|---|
| NHL bez regulaminowych linii goli na cały mecz | snapshoty SHADOW `runs/sofa/shadow/hockey/2026-11-1*` | 0 na 64 meczach NHL |
| CS2 BO3 bez dogrywki | SQL na `cs2_map` + `cs2_series` | 0,7523 / 8 312 |
| CS2 ±0,5 rund nieczytane | snapshoty CS2 vs mecze z 231535 / 231548 | linia ±0,5 tylko na 6 / 58 |
| CS2 dowód liniowy `rounds_handicap` ≥ 0,70 | `config/sofa_superbet_line_evidence.json` | 16 / 36 |
| kosz „N+” = OVER N-0,5 | surowe pliki 11-18 vs SHADOW | 47 / 66 identyczny kurs |
| tenis: nowy format drogi | `verify_tennis.py` | zwrot 0,778 / 0,612; przy kursach 1,09-1,29 0,819 / 0,695 |
| tenis: formaty a turnieje | `04_offer.json` + `02_fixtures.json` | stary ATP / WTA, nowy Challenger / WTA 125 (+46 ATP) |
| tenis: tiebreak = duplikat | `04_offer.json` | linia 12,5 na 169 / 170 meczów |
| piłka: kształt handicapu połowy | surowe pliki 11-15/16 | pary ±0,5 / ±1,5 / ±2,5 |

**Niezależny weryfikator** dostał raport, dane i kod bez moich wniosków. Każdą jego
uwagę sprawdziłem, zanim ją przyjąłem.

Potwierdził:
- wszystkie tożsamości zdarzeń (hokej, siatkówka, CS2 dogrywki, kosz, piłka);
- regułę rozliczenia NHL;
- zwrot w tenisie (0,778 / 0,610, z filtrem przed startem);
- pozostałe przepisane liczby.

Poprawki przyjęte w tej wersji:
1. Tenis: „zapadnięcie pokrycia modelu punktowego” było błędne. To koniec sezonu ATP
   / WTA, a nowy format to inne turnieje.
2. Tenis odrzucony złym argumentem. Rzeczywiste powody to wolumen i podatek, a model
   rozróżnia szczeble.
3. CS2 ROI: było oczekiwanie z historii (-6,3%), jest wynik na kursach (-16,0%).
4. CS2 ±0,5 rund nie jest czytane, wbrew pierwszej wersji. Dołożono pomiar.
5. Siatkówka: „nigdy 0,70” dotyczyło ceny, nie modelu. Model daje 65 nóg i
   przeszacowuje.
6. Hokej:
   - „jedyne pełnomeczowe” linie goli NHL, bo tercje czytamy;
   - liczba nóg zależy od krzywych (44 / 59);
   - marże, 6 289 / 6 290, karne zapisane jako `overtime`, godziny startu.
7. Piłka:
   - 1H przeszacowuje na żywo;
   - liczba meczów, a nie nóg;
   - powiązanie z podwójną szansą połowy;
   - ROI po podatku -14..-17%;
   - lista niezmierzonych rodzin.
8. Liczby w tenisie: 696 meczów nowego formatu (+22 kontrolne) i 5-57 meczów dziennie
   od 11-13.

## 6. Rekomendacja

Żaden z tych rynków nie poprawi wyniku kuponu po podatku. Jeśli operator chce szerszego
pokrycia, w tej kolejności:

1. **Hokej NHL z dogrywką i karnymi.**
   - To jedyne pełnomeczowe linie goli NHL. Przekształcenie jest arytmetycznie ścisłe,
     rozliczenie sprawdzone 105 / 105, nogi skalibrowane i po cenie.
   - Około dnia pracy plus refit, który wymaga zgody operatora.
   - Przed wdrożeniem trzeba dopisać tożsamości do `leg_identity`, a o remisie w NHL
     zdecydować osobno.
2. **Tenis „N+”: najpierw test w przód, nie wdrożenie.** Statystyki rozróżniają tam w
   obrębie ceny, ale 85 nóg to za mało. Ceny już się zapisują, a samo mapowanie to
   około dnia pracy, gdyby test przeszedł.
3. **Handicap połowy w piłce.** Mały zakres pracy, ale cena jest wyraźnie lepsza, a 1H
   przeszacowuje na żywo.

**Nie dodawać:** CS2 (dogrywki, rundy ±0,5), double-double i „N+” w koszu, pozostałych
rynków siatkówki.

Wszystko, co zmienia druk, podlega CLAUDE.md „Changing the pipeline”: przełącznik od
00:00Z następnego dnia, refit tylko na kopii bazy i za zgodą, test oraz aktualizacja
dokumentacji.
