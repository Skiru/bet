# Bateria statystyk - 2026-11-05

Pomiar jednorazowy, tylko do odczytu. Pytanie operatora: które statystyki,
dodane do **obecnego** p modelu, zbliżają je do ceny Superbetu bez marży, poza
próbą (miara z `docs/sofa/evidence/pokrycie_sportow_2026-11-05.md`: marżę
akceptujemy, pewność ma być uczciwa). Tenis jest poza zakresem (osobny model
punktowy).

Skrypt: `scripts/sofa/measure_feature_battery.py` (`list`, `build`,
`evaluate`). Wyniki: `data/refit_2026-11-05_battery/results.json`. Każda liczba
w sekcjach 2-6 pochodzi z tego pliku.

## 1. Zamrożona lista cech (zapisana 2026-11-05 16:28Z, przed pierwszym wynikiem)

Lista jest w kodzie (`FEATURES`) i nie była zmieniana po zapisaniu. Oznaczenia:
X = statystyka własna rynku w okresie linii (gole, rożne, punkty, sety, rundy
...); S = strona zakładu, O = druga strona, H / A = gospodarz / gość; „l<w>” =
ostatnie w meczów (dla rynków map CS2: map) **ściśle przed** startem; „-
linia” = minus linia (linia marginesu: + linia, zakład wchodzi, gdy margines
+ linia > 0). Cechy orientowane wskazują na S (linia sumy: na gospodarza).
Rodzaje rynków: `total` (suma, OVER), `side` (jedna strona, OVER), `margin`
(wynik / handicap / „most”), `player` (zawodnik, OVER), `other` (parzystość,
dokładne wyniki itp.: tylko cechy ogólne). Sporty: P piłka, H hokej, K kosz,
S siatkówka, CS2.

Cechy oznaczone „cena” są kontrolą: pochodzą z ceny, więc nie są „statystyką”.
Liczę je osobno (osobny BH) i nie wchodzą do modelu „wszystko”.

| id | sporty | rodzaje rynków | definicja | uwaga |
|---|---|---|---|---|
| A01 | P,H,K,S,CS2 | total,side,margin | szacunek X z l3: strona (S za + O przeciw)/2, suma (H suma + A suma)/2, margines (S margines - O margines)/2; minus linia |  |
| A02 | P,H,K,S,CS2 | total,side,margin | jak A01 z l5 |  |
| A03 | P,H,K,S,CS2 | total,side,margin | jak A01 z l10 |  |
| A04 | P,H,K,S,CS2 | total,side,margin | jak A01 z l20 |  |
| A05 | P,H,K,S,CS2 | total,side,margin | trend: szacunek l5 - szacunek l20 |  |
| A06 | P,H,K,S,CS2 | total,side,margin | odsetek meczów l10 (obie strony razem) z X ponad linią |  |
| A07 | P,H,K,S,CS2 | total,side,margin | jak A06 z l20 |  |
| A08 | P,H,K,S,CS2 | total,side,margin | odchylenie standardowe X w l20 (obie strony razem) |  |
| A09 | P,H,K,S,CS2 | total,side | rozproszenie: wariancja / średnia X w l20 |  |
| A10 | P,H,K,S,CS2 | total,side,margin | odległość linii w SD: (szacunek l20 - linia) / A08 |  |
| A11 | P,H,K,S,CS2 | total,side,margin | tylko własna produkcja: S za l10 (suma: mecze H) - linia |  |
| A12 | P,H,K,S,CS2 | total,side,margin | tylko strona rywala: O przeciw l10 (suma: mecze A) - linia |  |
| A13 | P,H,K,S,CS2 | total,side,margin | podział dom / wyjazd: S w meczach w tej samej roli, O w przeciwnej, l10 - linia |  |
| A14 | P,H,K,S,CS2 | total,side,margin | mediana X w l20 (obie strony) - linia |  |
| A15 | P,H,K,S,CS2 | total,side,margin | średnia wykładnicza (półokres 5 meczów) - linia | ponowny test: pamięć wykładnicza odrzucona 10-08 (półokres 180 dni, historia); tu jako dodatek do p wobec ceny |
| A16 | P,H,K,S,CS2 | total,side,margin | liczba dostępnych wartości X w l20 obu stron (cienka próba) |  |
| A17 | P,H,K,S,CS2 | total,side,margin | ostatni mecz: szacunek z l1 - linia |  |
| A18 | P,H,K,S,CS2 | total,side | korekta na rywala multiplikatywna: liga x (S za / liga) x (O przeciw / liga) - linia, l10 |  |
| A19 | P,H,K,S,CS2 | side | profil rywala: odsetek l10 O, w których rywal O przekroczył linię | ponowny test podejrzenia 10-29 (nieodporne), teraz poza próbą |
| L01 | P,H,K,S,CS2 | total,side,margin | stawka ligi X (rozgrywki, 180 dni przed meczem) - linia; margines: przewaga gospodarza x orientacja + linia |  |
| L02 | P,H,K,S,CS2 | total,side | odchylenie strony od ligi: szacunek l20 - stawka ligi |  |
| L03 | P,H,K,S,CS2 | total,side,margin | log(1 + liczba meczów ligi w puli 180 dni) |  |
| L04 | P,H,K,S,CS2 | total,side,margin | średnia przewaga gospodarza w X w lidze (orientowana) |  |
| C01 | P,H,K,S,CS2 | total,side,margin,player,other | dni odpoczynku gospodarza (max 21) |  |
| C02 | P,H,K,S,CS2 | total,side,margin,player,other | dni odpoczynku gościa (max 21) |  |
| C03 | P,H,K,S,CS2 | total,side,margin,player,other | różnica odpoczynku (orientowana) |  |
| C04 | P,H,K,S,CS2 | total,side,margin,player,other | mecz dzień po dniu: min odpoczynek <= 1,5 dnia |  |
| C05 | P,H,K,S,CS2 | total,side,margin,player,other | zagęszczenie: mecze obu stron w 7 dniach przed |  |
| C06 | P,H,K,S,CS2 | total,side,margin,player,other | różnica meczów w 14 dniach (orientowana) |  |
| C07 | P,H,K,S | total,side,margin,player,other | podróż gościa: poprzedni mecz gościa w innym mieście niż ten |  |
| C08 | P,H,K,S | total,side,margin,player,other | podróż gospodarza: poprzedni mecz gospodarza w innym mieście |  |
| C09 | P,H,K,S,CS2 | total,side,margin,player,other | etap sezonu: min liczba meczów stron w tych rozgrywkach i sezonie |  |
| C10 | P,H,K,S,CS2 | total,side,margin,player,other | dni od pierwszego meczu sezonu rozgrywek w puli |  |
| C11 | P,H,K,S | total,side,margin,player,other | mecz pucharowy / play-off (comparability.is_knockout) |  |
| C12 | P,H,K,S,CS2 | total,side,margin | h2h: średnia X w poprzednich spotkaniach (do 5, 400 dni) - linia |  |
| C13 | P,H,K,S,CS2 | total,side,margin,player,other | h2h: liczba spotkań (400 dni) |  |
| C14 | P,H,K,S,CS2 | total,side,margin,player,other | h2h: średni margines wyniku (orientowany) |  |
| S01 | P,H,K,S,CS2 | total,side,margin,player,other | forma: punkty na mecz l5, różnica (orientowana; poza piłką odsetek zwycięstw) |  |
| S02 | P,H,K,S,CS2 | total,side,margin,player,other | jak S01 z l10 |  |
| S03 | P,H,K,S,CS2 | total,side,margin,player,other | margines wyniku na mecz l10, różnica (orientowana) |  |
| S04 | P,H,K,S,CS2 | total,side,margin,player,other | jak S03 z l20 |  |
| S05 | P,H,K,S,CS2 | total,side,margin,player,other | margines H u siebie l10 - margines A na wyjeździe l10 (orientowany) |  |
| S06 | P,H,K,S,CS2 | total,side,margin,player,other | punkty na mecz w tym sezonie rozgrywek, różnica (orientowana) |  |
| S07 | P,H,K,S,CS2 | total,side,margin,player,other | punkty na mecz w sezonie, suma (poziom obu stron) |  |
| S08 | P,H,K,S,CS2 | total,side,margin,player,other | luka miejsc w tabeli odbudowanej z puli (sezon, przed meczem) / liczba drużyn |  |
| S09 | P,H,K,S,CS2 | total,side,margin,player,other | siła z ceny: logit p(wygrana gospodarza) bez marży (orientowany) | cena (kontrola, poza BH i poza modelem 'wszystko') |
| S10 | P,H,K,S,CS2 | total,side,margin,player,other | niezgoda ratingu z ceną: reszta logit ceny gospodarza ~ S04 (dopasowana na rozwoju) | cena (kontrola, poza BH i poza modelem 'wszystko'); ponowny test: niezgoda z ceną jako antysygnał (10-08), adnotacja 11-04 |
| S11 | P,H,K,S,CS2 | total,side,margin,player,other | wyrównanie z ceny: |logit p(gospodarz)| | cena (kontrola, poza BH i poza modelem 'wszystko') |
| P01 | P,H,K,S,CS2 | total,side,margin,player,other | sama cena: logit ceny bez marży tej strony (KONTROLA) | cena (kontrola, poza BH i poza modelem 'wszystko') |
| P02 | P,H,K,S,CS2 | total,side,margin,player,other | marża linii (overround) | cena (kontrola, poza BH i poza modelem 'wszystko') |
| P03 | H,K,S,CS2 | total,side,margin,player,other | ruch linii: logit p teraz - logit p w pierwszym snapshocie | cena (kontrola, poza BH i poza modelem 'wszystko') |
| P04 | H,K,S,CS2 | total,side,margin,player,other | minuty przed startem w chwili ceny | cena (kontrola, poza BH i poza modelem 'wszystko') |
| P05 | P,H,K,S,CS2 | total,side,margin,player,other | wartość linii |  |
| P06 | P | total,side | z próbki SAMPLES: (średnia - linia) / SD próbki wiersza |  |
| P07 | P | total,side,margin,player,other | log(1 + liczebność próbki SAMPLES wiersza) |  |
| T01 | P | total,side,margin | posiadanie l10: strona S - 50, suma |H - A|, margines S - O |  |
| T02 | P | total,side,margin | xG atak l10: S za / H+A za / S - O |  |
| T03 | P | total,side,margin | xG obrona l10: O przeciw / H+A przeciw / O przeciw - S przeciw |  |
| T04 | P | total,side,margin | wielkie szanse l10 (reguła jednolita: strona (S za + O przeciw)/2, suma - mecz, margines S - O) |  |
| T05 | P | total,side,margin | strzały ogółem l10 (reguła jednolita) - tempo |  |
| T06 | P | total,side,margin | rożne na strzał l10 (reguła jednolita, iloraz sum) |  |
| T07 | P | total,side,margin | dotknięcia w polu karnym rywala l10 (reguła jednolita) |  |
| T08 | P | total,side,margin | wejścia w tercję ataku l10 (reguła jednolita) |  |
| T09 | P | total,side,margin | celne dośrodkowania l10 (reguła jednolita) |  |
| T10 | P | total,side,margin | celne długie podania l10 (reguła jednolita) |  |
| T11 | P | total,side,margin | faule l10 (reguła jednolita) |  |
| T12 | P | total,side,margin | żółte kartki l10 (reguła jednolita) |  |
| T13 | P | total,side,margin,player,other | sędzia: żółte kartki na mecz (jego 30 ostatnich meczów przed) |  |
| T14 | P | total,side,margin,player,other | sędzia: faule na mecz (jw.) |  |
| T15 | P | total,side,margin,player,other | sędzia: log(1 + liczba jego meczów w cache) |  |
| T16 | H | total,side,margin | hokej strzały atak l10: S za / H+A za / S - O | B8 (strzały x skuteczność bramkarza w centrum) odrzucone 10-13; tu jako cecha |
| T17 | H | total,side,margin | hokej strzały obrona l10: O przeciw / H+A przeciw / O - S przeciw |  |
| T18 | H | total,side,margin | hokej skuteczność obrony drużyny l10 (1 - gole / strzały przeciw): O / średnia / S - O |  |
| T19 | H | total,side,margin | hokej minuty kar l10 (reguła jednolita) |  |
| T20 | H | total,side,margin,player,other | hokej odsetek dogrywek l20 obu stron |  |
| T21 | H | total,side,margin,player,other | hokej udział goli 3. tercji l20 obu stron |  |
| T22 | H | total,side,margin | hokej Corsi% l10: S - 50 / |H - A| / S - O |  |
| T23 | K | total,side,margin | kosz straty l10 (reguła jednolita) |  |
| T24 | K | total,side,margin | kosz udział punktów z trójek l10 (reguła jednolita, iloraz) |  |
| T25 | K | total,side,margin | kosz trafione wolne l10 (reguła jednolita) |  |
| T26 | K | total,side,margin,player,other | kosz odsetek dogrywek l20 obu stron |  |
| T27 | K | total,side,margin,player,other | kosz odsetek meczów rozstrzygniętych > 15 pkt l20 (garbage time) |  |
| T28 | K | total,side,margin,player,other | kosz udział punktów 4. kwarty l20 |  |
| T29 | K | total,side,margin | kosz zbiórki ofensywne l10 (reguła jednolita) | B7 tempo x efektywność zmierzone 10-13 (wymaga refitu); tu jako cecha |
| T30 | S | total,side,margin,player,other | siatkówka sety na mecz l10 obu stron | B9 / C10 długość seta odrzucone 10-13; tu jako cecha |
| T31 | S | total,side,margin,player,other | siatkówka odsetek meczów 5-setowych l20 |  |
| T32 | S | total,side,margin,player,other | siatkówka punkty na set l10 |  |
| T33 | S | total,side,margin,player,other | siatkówka odsetek wygranych setów, różnica (orientowana; suma |H - A|) |  |
| T34 | S | total,side,margin,player,other | siatkówka odsetek setów na przewagi l20 |  |
| T35 | S | total,side,margin,player,other | siatkówka margines punktów na set, różnica (orientowana; suma |H - A|) |  |
| T36 | CS2 | total,side,margin,player,other | CS2 rundy na mapę l20 map obu stron |  |
| T37 | CS2 | total,side,margin,player,other | CS2 odsetek wygranych map l20, różnica (orientowana; suma |H - A|) |  |
| T38 | CS2 | total,side,margin,player,other | CS2 odsetek map z dogrywką l20 |  |
| T39 | CS2 | total,side,margin,player,other | CS2 wspólna pula map: mapy grane >= 2 razy w 60 dniach przez obie strony |  |
| T40 | CS2 | total,side,margin,player,other | CS2 odsetek serii Bo3 do trzeciej mapy l20 |  |
| T41 | CS2 | total,side,margin,player,other | CS2 zmiana składu: odsetek graczy l5 map spoza map 6-10 (średnia stron) |  |
| T42 | CS2 | total,side,margin,player,other | CS2 różnica rund na mapę l20, różnica (orientowana; suma |H - A|) |  |
| T43 | CS2 | total,side,margin,player,other | CS2 zabójstwa drużyny na rundę l20: S / średnia / S - O |  |
| T44 | CS2 | total,side,margin,player,other | CS2 dni od ostatniej serii (min stron) |  |
| T45 | P | total,side,margin,player,other | składy: regularni zawodnicy spoza przewidywanej XI | NIE MIERZONE |
| Q01 | H,K,CS2 | player | zawodnik: średnia statystyki l5 - linia |  |
| Q02 | H,K,CS2 | player | zawodnik: l10 - linia |  |
| Q03 | H,K,CS2 | player | zawodnik: l20 - linia |  |
| Q04 | H,K,CS2 | player | zawodnik: trend l5 - l20 | ponowny test: człon formy NBA odrzucony 10-26 |
| Q05 | H,K,CS2 | player | zawodnik: SD statystyki l10 |  |
| Q06 | H,K,CS2 | player | zawodnik: odsetek l10 ponad linią |  |
| Q07 | H,K,CS2 | player | zawodnik: odsetek l20 ponad linią |  |
| Q08 | H,K | player | zawodnik: trend minut l3 - l10 |  |
| Q09 | H,K | player | zawodnik: minuty l10 |  |
| Q10 | H,K,CS2 | player | zawodnik: udział w wolumenie drużyny l10 |  |
| Q11 | H,K,CS2 | player | zawodnik: trend udziału l5 - l20 |  |
| Q12 | H,K,CS2 | player | zawodnik: mecze (mapy CS2) w 30 dniach |  |
| Q13 | H,K,CS2 | player | rywal: suma tej statystyki oddana przez O na mecz l10 |  |
| Q14 | H,K | player | zawodnik: odsetek meczów drużyny l10 bez gry |  |
| Q15 | H,K | player | średnia modelu zawodnika (player_model.jsonl) - linia |  |
| Q16 | H,K,CS2 | player | zawodnik: ostatni mecz - linia |  |
| Q17 | H,K,CS2 | player | zawodnik: średnia wykładnicza (półokres 5) - linia |  |

117 cech, w tym 7 cenowych (kontrole), 1 niemierzonych.

## 2. Dane i metoda

**Zbiór.** Rozliczone linie Superbetu 2026-09-28 .. 2026-11-04, ocena z
rozliczenia SETTLE (`build_log.json`):

| sport | źródło wyniku i ceny | p modelu (jak w mierniku 11-05) | wiersze | mecze |
|---|---|---|---|---|
| piłka | `sofa_settled_row`, `market_p` (cena bez marży, obie strony notowane) | `p_central` (SHEET przed krzywą) | 486 485 | 12 545 |
| hokej | SHADOW_SETTLE `settled.json`, `fair_p` | p modelu wyniku z `hockey_superbet_settled.jsonl`; zawodnicy `model_p` | 73 107 | 2 452 |
| kosz | jw. | jw. (`basketball_...`) | 167 460 | 3 883 |
| siatkówka | jw. | jw. (`volleyball_...`) | 19 028 | 1 892 |
| CS2 | CS2_SETTLE `settled.json`, `fair_p` | `model_p` | 36 411 | 902 |

- **Jedna strona na linię:** OVER, T1, YES, ODD (w rynkach trójdrożnych obie
  strony drużyn, w podwójnej szansie 1X i X2). Lustrzana strona tej samej
  linii nie jest liczona drugi raz.
- **Odrzucone wiersze:** piłka 16 012 wierszy, w których podmiotu nie dało się
  przypisać do strony (nazwa Superbetu inna niż w `01_board.json`). Sporty:
  brak p modelu (hokej 105 + 749, kosz 8 755 + 8 305, siatkówka 3 019, CS2
  2 055). Zawodnicy piłki są poza zbiorem: rynek jednostronny, brak ceny bez
  marży.
- **Cechy na stan ze startu:** wyłącznie z cache Sofascore (`mode=ro`, bez
  sieci). Każda historia przechodzi przez `as_of`: mecz liczy się tylko, gdy
  zaczął się **ściśle przed** startem. Pula ligi (180 dni) i tabela sezonu
  też są liczone tylko z meczów przed startem. Test
  `tests/sofa/test_measure_feature_battery.py` dokłada sfabrykowane mecze w
  chwili startu i po nim (z h2h i pulą ligi) i sprawdza, że żadna cecha się
  nie zmienia. Ten sam mecz o sekundę wcześniej zmienia cechy, więc test umie
  się nie udać.
- **Podział po dacie:** rozwój 09-28 .. 10-22 (25 dni), hold-out 10-23 ..
  11-04 (13 dni). Hold-out policzony **raz**, 2026-11-05 16:32Z.
- **Model bazowy:** rekalibracja logistyczna y ~ logit(p) na rozwoju.
  Podaję też surowe p.
- **Komórka (rodzina x cecha):** y ~ logit(p) + z(f) na rozwoju, gdzie z(f) to
  cecha standaryzowana na rozwoju i obcięta do ±5. Gdy cechy brak, wstawiam 0
  i wskaźnik braku. Komórka jest testowana, gdy:
  - cecha ma >= 50 wierszy i >= 30 meczów na rozwoju,
  - SD > 0,
  - hold-out ma >= 30 wierszy z cechą.

  Na hold-oucie liczę:
  - ΔBrier i Δlog-loss (model+cecha − model) z bootstrapem po meczach (1 000
    powtórzeń);
  - jednostronne p dla ΔBrier < 0 (z klastrowane po meczach);
  - lukę do ceny: Brier(model+cecha) − Brier(cena) przed i po.
- **Rodziny z < 100 meczami na hold-oucie** (albo < 100 na rozwoju) są
  wymienione, nie testowane.
- **Wielokrotne testy:** Benjamini-Hochberg q = 0,10 na **wszystkich**
  testowanych komórkach cech statystycznych naraz (6 104). Kontrole cenowe
  (745 komórek) mają osobny BH.
- **Model „wszystko”:** jeden na rodzinę. Zawiera wszystkie cechy niecenowe
  i wskaźniki braku, z karą L2. λ wybieram podziałem czasowym wewnątrz
  rozwoju (ostatnie 30% dni rozwoju jako walidacja), potem dopasowuję na całym
  rozwoju. Wynik na sport to wiersze hold-outu wszystkich rodzin razem.
- **Jedyna zmiana po zamrożeniu:** przebieg próbny `evaluate --dev-check`
  (tylko dni rozwoju, podział 10-15, hold-out nietknięty) pokazał, że λ
  „wszystkiego” zawsze trafiało w górny brzeg siatki 10³. Siatkę poszerzyłem
  do 10⁵ (`LAMBDA_GRID`). Lista cech i reguły komórek się nie zmieniły (`list`
  daje bajt w bajt tę samą tabelę co w sekcji 1).

## 3. Wynik

**Liczby (`results.json` → `summary`):**
- komórek rozważonych 7 170, testowanych 6 849, w tym 6 104 statystycznych i
  745 kontrol cenowych;
- **BH przeszło 155 komórek statystycznych** z 6 104, w 40 rodzinach (piłka
  124, kosz 26, hokej 4, siatkówka 1, CS2 0);
- bez poprawki p < 0,05 miało 574 komórki, przy 305 oczekiwanych, gdyby
  żadna cecha nie działała;
- przy q = 0,10 oczekiwane fałszywe przejścia to do ok. 15 z 155.

**Co te 155 komórek robi z luką do ceny:**
- **127 z 155** zmniejsza Brier, ale luka do ceny zostaje dodatnia, z
  przedziałem nad zerem.
- **19 komórek** jest w rodzinach, gdzie remis z ceną był już przed
  dodaniem cechy. 13 z nich zostaje remisem, 6 schodzi poniżej ceny (niżej).
- **9 komórek** zamyka lukę do remisu: przed przedział był nad zerem, po
  obejmuje zero. Wszystkie są w rodzinach, gdzie luka była mała:
  - piłka `goals_1h_total`, 5 cech formy (A04, A07, A10, A13, A14): luka
    +1,67 [+0,05; +3,19] → najlepiej +1,19 [−0,35; +2,65];
  - piłka `most_cards_points` S05: +9,10 → +4,60 [−0,35; +8,77];
  - piłka `saves_1h_total` A16: 124 mecze;
  - piłka `shots_on_target_1h_total` C01;
  - hokej `result_1x2` S07: o 0,15 × 10⁻³, przedział ledwo dotyka zera.
- **6 komórek** schodzi poniżej ceny: piłka `tackles_for` (A01, A03, A08,
  A15, A17) i `tackles_total` A08. To rodziny ze 180 i 178 meczami na
  hold-oucie, w których luka **już przed** była zerowa (−0,11 [−3,95;
  +3,60]). Pięć skorelowanych cech formy daje ten sam sygnał. Model
  „wszystko” w `tackles_for` daje +0,18, czyli nic. **Podejrzenie, nie
  wynik:** mała próba, jedno okno.

**Gdzie zysk jest największy (wszystkie luki zostają dodatnie, ×10⁻³):**

| rodzina | luka przed | najlepsza cecha | ΔBrier | luka po |
|---|---|---|---|---|
| kosz `winner` | +23,8 | tabela sezonu S08 (S06, A02, A05 podobnie) | −6,1 | +17,7 |
| kosz `total` | +11,8 | forma l5 A02 (A18, L02, A06 podobnie) | −6,7 | +5,2 |
| piłka `most_shots` (423 mecze) | +37,8 | A13 / L01 | ok. −20 | +17,2 .. +18,4 |
| piłka `most_corners_1h` | +19,5 | A13 | −8,2 | +11,3 |
| piłka `draw_no_bet` | +18,6 | punkty w sezonie S06 | −3,8 | +14,8 |
| piłka `result_1x2` | +12,2 | S06 | −1,7 | +10,6 |
| piłka `double_chance` | +12,2 | S06 | −1,6 | +10,6 |
| piłka `goals_for` | +6,8 | forma l20 A04 | −1,0 | +5,7 |
| piłka `goals_1h_for` | +6,8 | podział dom / wyjazd A13 | −1,4 | +5,3 |

**Model „wszystko” (górna granica tych danych):**
- Na sport **żaden nie jest lepszy od samego p** (sekcja 4.5). Kosz −0,85
  [−1,88; +0,25], piłka +0,39 [−0,22; +0,97]. Hokej +1,76, siatkówka +3,45 i
  CS2 +6,39 są gorsze.
- Na rodzinę „wszystko” pomaga tam, gdzie pomagały pojedyncze cechy:
  - kosz `winner` −7,0 [−10,5; −3,8] i `total` −5,6 [−9,0; −2,2];
  - piłka `most_shots` −21,0, `most_corners_1h` −9,4, `draw_no_bet` −4,4,
    `goals_1h_for` −2,0, `goals_for` −1,4.

  W pozostałych rodzinach szkodzi, więc w sumie po sporcie wychodzi zero.
  Po „wszystkim” żadna z tych rodzin nie dochodzi do ceny. Najbliżej jest kosz
  `total`: +6,3 [+2,8; +9,4].

**Kontrole cenowe działają zgodnie z oczekiwaniem.** Sama cena (P01) dodana
do p sprowadza lukę do zera, np. piłka `result_1x2` +12,2 → −0,2 [−0,8;
+0,3], kosz `winner` +23,8 → −0,3. Metoda umie więc wykryć zamknięcie luki,
gdy informacja jest w danych. Niezgoda ratingu z ceną (S10) pomaga tylko
jako zastępstwo ceny.

**Grupy cech, które nie przeszły nigdzie albo prawie nigdzie:**
- sędzia (T13-T15): 0 z 189 komórek; w kartkach i faulach najlepsze
  `cards_points_total` T15 −0,37 [−1,33; +0,65];
- hokej strzały / skuteczność obrony / Corsi / dogrywki (T16-T22): 0 z 80;
- siatkówka (T30-T35): 0 z 60;
- CS2 (T36-T44, pula map, skład): 0 z 99; w CS2 nic nie przeszło;
- zawodnicy (Q01-Q17, tylko kosz, 6 rodzin): 0 z 102. Ponowny test formy
  NBA Q04: najlepsze `player_threes` −0,72 [−1,92; +0,41];
- kosz tempo (T23-T29): 1 z 148 (`team_total` T26 −0,78);
- podróż (C07 / C08): 0 z 80;
- profil rywala A19 (podejrzenie z 10-29, ponowny test): rożne `corners_for`
  −0,66 [−1,43; +0,11], nie przechodzi. Przechodzi tylko w `tackles_for`
  (wyżej).
- pamięć wykładnicza A15 (odrzucona 10-08, ponowny test): przechodzi w 9
  rodzinach, ale jak forma l10 / l20 i z tą samą wielkością. Nie zamyka
  żadnej dużej luki.

**Co z tego wynika:**
- **Zmierzone:** w tej baterii żadna statystyka nie doprowadza naszego p do
  ceny w rodzinie z dużą luką.
- **Zmierzone:** 155 przejść to głównie te same dwa sygnały w wielu
  przebraniach. Pierwszy to forma własnej statystyki rynku (okna l3 .. l20,
  średnia wykładnicza, odsetek nad linią, podział dom / wyjazd). Drugi to
  pozycja w sezonie (punkty na mecz, tabela). W rodzinach marginesowych
  niektóre cechy są wręcz tożsame: L01 = L04 i A03 = S03 przy linii 0.
- **Podejrzenie (interpretacja, nie pomiar):** obecne p **niedoważa
  niedawnej formy i tabeli sezonu**:
  - w koszu `winner` / `total` (rating modelu wyniku);
  - w piłce 1X2 / DC / DNB;
  - w golach jednej strony (zgodne z otwartym podejrzeniem „centrum
    goals_for za mało ściągnięte”, model-state (d) 10-22).

  To kwestia wag w istniejącym modelu, nie nowego źródła danych. Nawet
  najlepszy przypadek zmniejsza lukę o 10-50%, a nie ją zamyka.
- Rzeczy spoza modelu (sędzia, tempo, składy CS2, podróż, udział zawodnika)
  nie dają mierzalnego zysku na tym oknie.

## 4. Tabele (z `results.json`)

### 4.1 Rodziny: liczebności i luka do ceny (Brier ×10⁻³, hold-out)

| sport | rodzina | rodzaj | wiersze rozwój / hold-out | mecze rozwój / hold-out | testowana | surowe p − cena | rekalibrowane p − cena | „wszystko” − p rekal. | „wszystko” − cena |
|---|---|---|---|---|---|---|---|---|---|
| piłka | double_chance | margin | 5818 / 10811 | 2981 / 5558 | tak | +12,10 [+9,65; +14,50] | +12,22 [+9,69; +14,65] | -1,61 [-3,25; -0,01] | +10,62 [+8,33; +13,04] |
| piłka | result_1x2 | margin | 5614 / 10811 | 2877 / 5558 | tak | +12,10 [+9,65; +14,50] | +12,21 [+9,68; +14,63] | -1,64 [-3,28; -0,02] | +10,57 [+8,27; +12,86] |
| piłka | goals_total | total | 27906 / 22420 | 6916 / 5516 | tak | +2,48 [+1,32; +3,63] | +2,34 [+1,14; +3,59] | +0,13 [-0,74; +0,99] | +2,47 [+1,42; +3,57] |
| piłka | both_over_goals | other | 8394 / 6871 | 6871 / 5475 | tak | +4,15 [+2,38; +5,94] | +3,31 [+1,68; +4,88] | -1,17 [-2,58; +0,29] | +2,15 [+0,45; +3,92] |
| piłka | btts_or_over | other | 3389 / 6855 | 2698 / 5422 | tak | +6,88 [+4,71; +9,11] | +2,50 [+0,99; +3,98] | +3,37 [+1,85; +5,08] | +5,88 [+3,49; +8,21] |
| piłka | draw_no_bet | margin | 2070 / 3954 | 2070 / 3954 | tak | +18,37 [+14,50; +22,24] | +18,59 [+14,52; +22,63] | -4,41 [-7,61; -1,26] | +14,18 [+10,63; +17,66] |
| piłka | goals_1h_total | total | 11186 / 9085 | 3650 / 2938 | tak | +1,84 [+0,48; +3,23] | +1,67 [+0,05; +3,19] | -0,34 [-1,29; +0,67] | +1,33 [-0,15; +2,65] |
| piłka | goals_2h_total | total | 11950 / 9787 | 3650 / 2938 | tak | +2,25 [+0,90; +3,50] | +2,29 [+0,87; +3,69] | +0,12 [-0,93; +1,15] | +2,41 [+1,10; +3,77] |
| piłka | goals_for | side | 21064 / 17413 | 3661 / 2932 | tak | +6,70 [+4,93; +8,58] | +6,75 [+4,95; +8,59] | -1,35 [-2,54; -0,19] | +5,40 [+3,80; +7,09] |
| piłka | goals_2h_for | side | 9690 / 8487 | 3599 / 2921 | tak | +6,09 [+4,03; +8,03] | +5,57 [+3,64; +7,42] | -1,51 [-2,95; -0,00] | +4,06 [+2,40; +5,77] |
| piłka | goals_1h_for | side | 8874 / 7611 | 3587 / 2918 | tak | +7,82 [+5,79; +9,85] | +6,77 [+4,86; +8,75] | -2,02 [-3,58; -0,59] | +4,76 [+3,20; +6,52] |
| piłka | result_handicap | margin | 2954 / 6019 | 1436 / 2888 | tak | +10,49 [+7,72; +13,55] | +9,44 [+6,80; +12,18] | -1,80 [-3,77; +0,02] | +7,64 [+5,17; +10,12] |
| piłka | both_over_goals_2h | other | 1560 / 2886 | 1560 / 2886 | tak | +9,03 [+5,53; +12,79] | +2,52 [+0,83; +4,37] | +3,54 [+1,12; +6,02] | +6,06 [+2,98; +9,01] |
| piłka | both_over_goals_1h | other | 1498 / 2728 | 1498 / 2728 | tak | +5,21 [+2,40; +8,03] | +2,02 [+0,47; +3,55] | +0,50 [+0,23; +0,76] | +2,51 [+0,89; +4,07] |
| piłka | corners_total | total | 14463 / 13048 | 2495 / 2221 | tak | +0,93 [-0,67; +2,53] | +0,37 [-1,26; +1,91] | +1,26 [-0,23; +2,71] | +1,63 [-0,33; +3,46] |
| piłka | corners_1h_total | total | 5487 / 5261 | 1137 / 1125 | tak | +0,57 [-1,44; +2,63] | -0,03 [-2,09; +1,87] | +1,27 [-0,28; +2,83] | +1,24 [-1,02; +3,65] |
| piłka | corners_for | side | 12634 / 11462 | 1217 / 1102 | tak | +5,23 [+2,67; +7,94] | +5,36 [+2,79; +8,04] | -1,31 [-3,53; +0,84] | +4,05 [+1,91; +6,13] |
| piłka | most_corners | margin | 2169 / 1962 | 1186 / 1086 | tak | +7,44 [+1,90; +13,25] | +6,49 [+0,94; +12,02] | +3,59 [-1,30; +8,21] | +10,07 [+4,92; +15,63] |
| piłka | result_or_btts | other | 1407 / 3047 | 470 / 1019 | tak | +4,43 [+1,55; +7,67] | +2,72 [+0,15; +5,35] | +7,29 [+4,58; +10,08] | +10,02 [+6,07; +13,90] |
| piłka | result_or_clean_sheet | other | 1410 / 3055 | 470 / 1019 | tak | +4,78 [+2,35; +7,27] | +3,25 [+1,36; +5,11] | +4,77 [+2,81; +6,79] | +8,02 [+5,22; +10,80] |
| piłka | result_or_over | other | 6604 / 14328 | 470 / 1019 | tak | +4,55 [+2,61; +6,50] | +4,31 [+2,42; +6,16] | +1,31 [-0,24; +2,89] | +5,62 [+3,53; +7,78] |
| piłka | result_or_under | other | 6577 / 14224 | 470 / 1019 | tak | +7,63 [+5,01; +10,04] | +7,44 [+4,85; +9,82] | +3,41 [+1,47; +5,45] | +10,84 [+8,15; +13,47] |
| piłka | penalties_total | total | 549 / 1078 | 527 / 1003 | tak | -4,81 [-7,50; -1,89] | -1,02 [-3,36; +1,12] | +2,98 [+1,46; +4,44] | +1,96 [-0,91; +4,70] |
| piłka | cards_points_1h_total | total | 143 / 1119 | 51 / 857 | nie (< 100 meczów) | - | - | - | - |
| piłka | red_cards_total | total | 421 / 856 | 421 / 856 | tak | -0,93 [-3,74; +1,72] | +1,99 [-1,08; +5,20] | -0,81 [-3,12; +1,59] | +1,18 [-2,02; +4,75] |
| piłka | cards_points_total | total | 3487 / 3239 | 918 / 844 | tak | +4,95 [+1,18; +9,32] | +4,01 [+0,57; +7,88] | +2,15 [-1,22; +5,75] | +6,16 [+1,57; +11,05] |
| piłka | cards_points_for | side | 2921 / 3096 | 869 / 838 | tak | +4,80 [+1,76; +8,05] | +3,78 [+0,81; +6,79] | +1,64 [-1,31; +4,42] | +5,42 [+1,50; +9,37] |
| piłka | most_cards_points | margin | 1735 / 1628 | 868 / 814 | tak | +3,39 [-0,57; +7,15] | +9,10 [+4,10; +13,71] | +0,80 [-0,38; +2,16] | +9,91 [+4,75; +14,56] |
| piłka | handicap_corners | margin | 2503 / 2040 | 872 / 784 | tak | +10,26 [+2,51; +17,56] | +4,11 [+1,68; +6,81] | +0,97 [-0,53; +2,48] | +5,08 [+2,46; +7,91] |
| piłka | both_over_cards_points | other | 1413 / 1382 | 817 / 769 | tak | +5,14 [+1,36; +9,48] | +5,28 [+0,60; +9,77] | +3,64 [+0,26; +7,23] | +8,92 [+3,10; +14,97] |
| piłka | corners_1h_for | side | 5023 / 4231 | 836 / 710 | tak | +2,78 [-0,03; +5,47] | +2,90 [+0,17; +5,56] | -0,92 [-3,41; +1,51] | +1,98 [-0,56; +4,53] |
| piłka | red_cards_for | side | 88 / 1203 | 49 / 692 | nie (< 100 meczów) | - | - | - | - |
| piłka | cards_points_1h_for | side | 90 / 1293 | 49 / 691 | nie (< 100 meczów) | - | - | - | - |
| piłka | most_corners_1h | margin | 1481 / 1287 | 741 / 644 | tak | +33,56 [+21,10; +45,20] | +19,47 [+9,44; +28,00] | -9,37 [-14,56; -3,78] | +10,10 [+4,31; +15,41] |
| piłka | shots_on_target_for | side | 4684 / 4516 | 561 / 468 | tak | +4,40 [+0,95; +7,78] | +5,37 [+1,94; +8,76] | +0,85 [-3,36; +4,54] | +6,22 [+1,67; +10,33] |
| piłka | shots_on_target_total | total | 3722 / 3476 | 567 / 467 | tak | +1,47 [-2,12; +5,06] | +3,98 [-0,59; +8,41] | +4,31 [+0,95; +7,93] | +8,29 [+2,63; +13,80] |
| piłka | most_shots_on_target | margin | 936 / 785 | 514 / 446 | tak | +6,43 [-1,16; +14,21] | +6,41 [-1,24; +14,45] | -3,97 [-15,07; +7,15] | +2,43 [-9,33; +14,23] |
| piłka | shots_for | side | 4867 / 4808 | 492 / 442 | tak | +2,12 [-3,95; +8,29] | +3,20 [-2,26; +8,67] | +4,66 [-0,28; +9,22] | +7,86 [+2,73; +13,91] |
| piłka | shots_total | total | 3531 / 3456 | 491 / 441 | tak | +5,51 [-1,17; +12,06] | +8,59 [+1,90; +15,87] | -2,06 [-8,27; +4,49] | +6,52 [-1,62; +14,82] |
| piłka | most_shots | margin | 865 / 747 | 474 / 423 | tak | +36,91 [+19,89; +52,62] | +37,82 [+21,23; +52,08] | -20,96 [-33,92; -7,61] | +16,86 [+2,51; +30,25] |
| piłka | shots_on_target_1h_total | total | 676 / 609 | 458 / 415 | tak | +1,25 [-4,62; +7,41] | +5,92 [+0,29; +11,41] | +3,59 [-5,53; +12,82] | +9,50 [-0,41; +19,98] |
| piłka | saves_for | side | 3102 / 2381 | 492 / 408 | tak | +4,20 [-0,53; +8,80] | +4,16 [+0,00; +8,12] | -1,68 [-7,49; +3,98] | +2,48 [-3,31; +7,98] |
| piłka | saves_total | total | 2001 / 1582 | 492 / 406 | tak | -1,20 [-5,84; +3,09] | -0,17 [-4,66; +4,39] | +4,03 [-0,09; +8,24] | +3,86 [-2,14; +9,35] |
| piłka | shots_1h_total | total | 664 / 598 | 439 / 401 | tak | -1,63 [-9,27; +5,99] | -1,14 [-6,52; +4,20] | +2,71 [-1,66; +6,63] | +1,57 [-4,43; +7,51] |
| piłka | offsides_for | side | 1067 / 1054 | 429 / 376 | tak | +6,56 [+0,50; +12,46] | +5,51 [-0,42; +11,12] | -1,34 [-6,32; +4,08] | +4,16 [-1,42; +9,41] |
| piłka | offsides_total | total | 839 / 1128 | 432 / 375 | tak | +1,77 [-3,44; +7,41] | +1,11 [-4,11; +6,20] | +13,36 [+5,40; +21,23] | +14,48 [+4,84; +22,86] |
| piłka | fouls_for | side | 756 / 543 | 386 / 285 | tak | +0,80 [-7,16; +9,37] | -0,40 [-7,12; +6,97] | -1,81 [-6,76; +3,58] | -2,21 [-7,03; +2,84] |
| piłka | fouls_total | total | 718 / 501 | 387 / 283 | tak | -6,15 [-19,69; +6,22] | -6,11 [-14,11; +1,07] | +1,43 [-4,10; +6,69] | -4,68 [-10,88; +1,00] |
| piłka | shots_on_target_1h_for | side | 453 / 360 | 260 / 196 | tak | +7,52 [+0,03; +15,49] | +5,04 [-1,75; +11,41] | +3,09 [-1,14; +7,30] | +8,13 [-1,20; +17,59] |
| piłka | corners_2h_for | side | 2143 / 1575 | 258 / 187 | tak | +3,59 [-0,27; +7,31] | +4,22 [+0,25; +8,12] | +2,26 [-2,69; +6,63] | +6,48 [+0,57; +12,06] |
| piłka | corners_2h_total | total | 1719 / 1309 | 235 / 187 | tak | +2,32 [-1,10; +5,68] | +4,56 [-0,12; +8,72] | +10,09 [+1,10; +18,49] | +14,65 [+3,40; +25,24] |
| piłka | most_corners_2h | margin | 469 / 374 | 235 / 187 | tak | +20,50 [+0,84; +44,83] | +10,07 [-7,44; +27,23] | -4,77 [-10,49; +0,99] | +5,30 [-9,06; +19,07] |
| piłka | cards_points_2h_total | total | 139 / 447 | 47 / 185 | nie (< 100 meczów) | - | - | - | - |
| piłka | cards_points_2h_for | side | 82 / 336 | 45 / 183 | nie (< 100 meczów) | - | - | - | - |
| piłka | goal_kicks_for | side | 381 / 330 | 209 / 180 | tak | +6,20 [-3,58; +17,50] | +2,45 [-3,99; +8,94] | +2,31 [-1,09; +5,73] | +4,75 [-2,42; +11,61] |
| piłka | tackles_for | side | 377 / 329 | 208 / 180 | tak | +9,86 [-1,73; +20,57] | -0,11 [-3,95; +3,60] | +0,18 [-1,63; +1,91] | +0,07 [-2,86; +2,86] |
| piłka | throw_ins_for | side | 381 / 330 | 209 / 180 | tak | +20,72 [+10,17; +32,01] | +3,90 [-1,94; +10,38] | -5,19 [-9,78; -0,40] | -1,30 [-6,99; +5,05] |
| piłka | goal_kicks_total | total | 315 / 231 | 207 / 178 | tak | -6,69 [-16,74; +5,39] | +3,59 [-13,65; +19,37] | +3,05 [-13,58; +20,68] | +6,63 [-19,09; +31,67] |
| piłka | shots_1h_for | side | 411 / 328 | 236 / 178 | tak | +7,65 [-2,55; +18,57] | +1,93 [-2,22; +5,90] | +0,71 [-2,42; +3,67] | +2,64 [-1,78; +6,93] |
| piłka | tackles_total | total | 203 / 178 | 203 / 178 | tak | -1,86 [-12,25; +8,87] | +0,14 [-3,24; +3,32] | -2,61 [-5,64; +0,06] | -2,47 [-6,63; +1,40] |
| piłka | throw_ins_total | total | 315 / 232 | 207 / 178 | tak | +8,42 [-6,25; +23,31] | +9,42 [-5,12; +24,28] | -8,54 [-17,06; +0,44] | +0,88 [-14,68; +16,40] |
| piłka | penalties_1h_total | total | 46 / 133 | 46 / 133 | nie (< 100 meczów) | - | - | - | - |
| piłka | handicap_cards_points | margin | 1129 / 708 | 209 / 132 | tak | +8,98 [+0,10; +18,29] | +7,06 [-0,85; +15,17] | +0,01 [-8,77; +7,86] | +7,06 [-1,17; +15,36] |
| piłka | penalties_for | side | 80 / 242 | 44 / 132 | nie (< 100 meczów) | - | - | - | - |
| piłka | handicap_corners_1h | margin | 201 / 233 | 113 / 130 | tak | +48,08 [+22,69; +73,76] | +5,65 [-18,04; +28,86] | +12,64 [-1,31; +27,10] | +18,29 [-5,07; +40,98] |
| piłka | handicap_corners_2h | margin | 201 / 233 | 113 / 130 | tak | +19,90 [-6,90; +48,76] | +3,13 [-5,48; +11,45] | -0,19 [-0,71; +0,34] | +2,94 [-5,52; +11,10] |
| piłka | saves_1h_for | side | 343 / 227 | 199 / 124 | tak | +7,69 [-2,52; +18,46] | +16,19 [+5,77; +26,72] | +4,77 [+1,62; +7,73] | +20,96 [+8,75; +33,72] |
| piłka | saves_1h_total | total | 534 / 370 | 178 / 124 | tak | +0,92 [-6,69; +8,18] | +12,18 [+3,73; +21,08] | +8,34 [+1,49; +14,67] | +20,52 [+8,96; +32,79] |
| piłka | penalties_1h_for | side | 65 / 159 | 41 / 105 | nie (< 100 meczów) | - | - | - | - |
| piłka | shots_on_target_2h_for | side | 314 / 180 | 184 / 100 | tak | +10,33 [-1,89; +22,47] | +5,25 [-5,89; +15,61] | +3,49 [+0,48; +6,61] | +8,74 [-4,11; +20,58] |
| piłka | shots_on_target_2h_total | total | 162 / 100 | 162 / 100 | tak | -1,57 [-14,66; +10,70] | +4,38 [-16,38; +25,89] | +10,53 [-1,38; +22,64] | +14,91 [-5,22; +35,11] |
| piłka | shots_2h_for | side | 283 / 143 | 167 / 79 | nie (< 100 meczów) | - | - | - | - |
| piłka | shots_2h_total | total | 142 / 79 | 142 / 79 | nie (< 100 meczów) | - | - | - | - |
| piłka | fouls_1h_for | side | 283 / 122 | 167 / 67 | nie (< 100 meczów) | - | - | - | - |
| piłka | fouls_1h_total | total | 142 / 67 | 142 / 67 | nie (< 100 meczów) | - | - | - | - |
| piłka | fouls_2h_for | side | 283 / 122 | 167 / 67 | nie (< 100 meczów) | - | - | - | - |
| piłka | fouls_2h_total | total | 142 / 67 | 142 / 67 | nie (< 100 meczów) | - | - | - | - |
| piłka | offsides_1h_for | side | 275 / 117 | 163 / 64 | nie (< 100 meczów) | - | - | - | - |
| piłka | offsides_1h_total | total | 138 / 64 | 138 / 64 | nie (< 100 meczów) | - | - | - | - |
| piłka | offsides_2h_for | side | 275 / 117 | 163 / 64 | nie (< 100 meczów) | - | - | - | - |
| piłka | offsides_2h_total | total | 138 / 64 | 138 / 64 | nie (< 100 meczów) | - | - | - | - |
| piłka | handicap_shots_on_target | margin | 251 / 78 | 139 / 46 | nie (< 100 meczów) | - | - | - | - |
| piłka | most_shots_1h | margin | 232 / 90 | 116 / 45 | nie (< 100 meczów) | - | - | - | - |
| piłka | most_shots_2h | margin | 232 / 90 | 116 / 45 | nie (< 100 meczów) | - | - | - | - |
| piłka | throw_ins_1h_for | side | 195 / 78 | 112 / 45 | nie (< 100 meczów) | - | - | - | - |
| piłka | throw_ins_1h_total | total | 102 / 45 | 102 / 45 | nie (< 100 meczów) | - | - | - | - |
| piłka | throw_ins_2h_for | side | 195 / 78 | 112 / 45 | nie (< 100 meczów) | - | - | - | - |
| piłka | throw_ins_2h_total | total | 102 / 45 | 102 / 45 | nie (< 100 meczów) | - | - | - | - |
| piłka | handicap_shots | margin | 71 / 74 | 39 / 44 | nie (< 100 meczów) | - | - | - | - |
| piłka | handicap_shots_2h | margin | 51 / 73 | 28 / 43 | nie (< 100 meczów) | - | - | - | - |
| piłka | red_cards_1h_total | total | 6 / 43 | 6 / 43 | nie (< 100 meczów) | - | - | - | - |
| piłka | handicap_shots_1h | margin | 51 / 72 | 28 / 42 | nie (< 100 meczów) | - | - | - | - |
| hokej | result_1x2 | margin | 2544 / 2290 | 1272 / 1145 | tak | +4,95 [+0,12; +10,24] | +4,69 [+0,11; +9,71] | -1,57 [-5,31; +2,05] | +3,12 [-1,67; +8,03] |
| hokej | double_chance | margin | 1302 / 2206 | 651 / 1103 | tak | +5,44 [+0,43; +10,27] | +5,13 [+0,38; +9,72] | +1,91 [-1,74; +5,66] | +7,04 [+2,50; +11,08] |
| hokej | period_1x2 | margin | 2942 / 2514 | 1233 / 1088 | tak | +2,42 [-0,20; +4,99] | +2,49 [+0,11; +4,97] | +3,17 [+0,24; +6,21] | +5,67 [+2,55; +8,94] |
| hokej | period_total | total | 3408 / 2765 | 1233 / 1086 | tak | +0,29 [-1,37; +1,80] | +0,30 [-1,37; +1,86] | +3,41 [-0,04; +7,01] | +3,71 [+0,41; +7,00] |
| hokej | winner | margin | 1220 / 1073 | 1220 / 1073 | tak | +7,07 [+0,90; +13,05] | +6,33 [+0,28; +12,29] | -1,10 [-6,04; +4,04] | +5,22 [-0,74; +11,55] |
| hokej | team_total | side | 4930 / 4413 | 1112 / 1002 | tak | +4,43 [+1,64; +7,07] | +3,51 [+0,92; +6,03] | +0,03 [-1,85; +1,85] | +3,53 [+0,92; +6,18] |
| hokej | total | total | 3715 / 3342 | 1114 / 1002 | tak | +3,80 [+0,53; +7,01] | +3,06 [-0,13; +6,24] | +0,79 [-2,47; +4,11] | +3,86 [+0,21; +7,41] |
| hokej | period_double_chance | margin | 1184 / 2000 | 592 / 1000 | tak | +2,00 [-0,86; +4,74] | +2,09 [-0,74; +4,87] | +2,88 [-0,80; +6,20] | +4,97 [+1,86; +8,09] |
| hokej | period_dnb | margin | 997 / 859 | 855 / 761 | tak | +4,45 [-1,07; +9,92] | +5,08 [-0,28; +10,36] | +6,49 [+0,76; +12,78] | +11,57 [+5,19; +17,85] |
| hokej | period_team_total | side | 3569 / 2895 | 632 / 541 | tak | +1,51 [+0,05; +2,98] | +1,67 [+0,27; +3,11] | +2,58 [+0,57; +4,72] | +4,26 [+2,19; +6,36] |
| hokej | handicap | margin | 1894 / 1698 | 511 / 455 | tak | +6,12 [+0,17; +11,99] | +4,80 [-0,85; +10,29] | +0,20 [-4,91; +5,26] | +5,00 [-0,31; +10,58] |
| hokej | period_handicap | margin | 1580 / 1225 | 293 / 240 | tak | +2,07 [-0,32; +4,61] | +2,34 [-0,18; +4,96] | +7,65 [+1,85; +13,38] | +9,99 [+4,17; +16,25] |
| hokej | player_pp_points | player | 1840 / 1425 | 120 / 87 | nie (< 100 meczów) | - | - | - | - |
| hokej | player_shots_on_goal | player | 1721 / 1416 | 120 / 87 | nie (< 100 meczów) | - | - | - | - |
| hokej | player_assists | player | 1606 / 1284 | 117 / 86 | nie (< 100 meczów) | - | - | - | - |
| hokej | player_blocked_shots | player | 282 / 307 | 109 / 86 | nie (< 100 meczów) | - | - | - | - |
| hokej | player_faceoff_wins | player | 273 / 244 | 112 / 86 | nie (< 100 meczów) | - | - | - | - |
| hokej | player_points | player | 1606 / 1285 | 117 / 86 | nie (< 100 meczów) | - | - | - | - |
| hokej | player_goalie_saves | player | 168 / 150 | 106 / 82 | nie (< 100 meczów) | - | - | - | - |
| hokej | player_hits | player | 392 / 320 | 111 / 82 | nie (< 100 meczów) | - | - | - | - |
| hokej | player_plus_minus | player | 1198 / 1025 | 110 / 82 | nie (< 100 meczów) | - | - | - | - |
| kosz | odd_even | other | 1762 / 1703 | 1762 / 1703 | tak | +0,46 [-0,31; +1,27] | +0,51 [-0,41; +1,40] | -0,44 [-1,30; +0,40] | +0,07 [-0,28; +0,44] |
| kosz | total | total | 13827 / 14878 | 1772 / 1701 | tak | +9,38 [+2,78; +15,80] | +11,84 [+8,63; +14,84] | -5,57 [-9,00; -2,19] | +6,27 [+2,75; +9,37] |
| kosz | handicap | margin | 7714 / 8109 | 1772 / 1698 | tak | +20,13 [+13,12; +27,09] | +12,28 [+8,42; +16,19] | -0,01 [-1,17; +1,24] | +12,27 [+8,28; +16,22] |
| kosz | winner | margin | 1699 / 1629 | 1699 / 1629 | tak | +23,36 [+16,78; +29,57] | +23,81 [+17,58; +30,06] | -7,03 [-10,54; -3,78] | +16,78 [+11,11; +22,79] |
| kosz | h1_handicap | margin | 3305 / 3692 | 1395 / 1361 | tak | +13,50 [+7,56; +19,84] | +4,53 [+2,24; +6,89] | -1,51 [-3,25; +0,14] | +3,02 [+0,85; +5,04] |
| kosz | h1_total | total | 3355 / 3831 | 1352 / 1360 | tak | +12,61 [+5,30; +19,81] | +4,22 [+0,48; +7,74] | -2,07 [-5,29; +1,29] | +2,15 [+0,21; +4,15] |
| kosz | team_total | side | 7496 / 8745 | 810 / 1193 | tak | +16,59 [+10,85; +22,92] | +3,50 [+1,91; +5,17] | -0,37 [-1,75; +0,85] | +3,13 [+2,03; +4,41] |
| kosz | h1_1x2 | margin | 1538 / 2198 | 769 / 1099 | tak | +9,33 [+3,32; +15,33] | +9,02 [+2,96; +14,78] | +1,65 [-1,86; +5,38] | +10,67 [+4,71; +16,66] |
| kosz | quarter_handicap | margin | 3019 / 3731 | 828 / 1032 | tak | +8,90 [+4,39; +14,23] | +4,42 [+1,35; +7,69] | -0,71 [-3,01; +1,42] | +3,71 [+1,13; +6,49] |
| kosz | quarter_team_total | side | 2156 / 3823 | 597 / 969 | tak | +7,71 [+4,26; +11,26] | +3,69 [+1,47; +5,86] | -0,90 [-2,66; +0,79] | +2,78 [+1,33; +4,33] |
| kosz | quarter_1x2 | margin | 2130 / 3160 | 639 / 957 | tak | +8,02 [+4,65; +11,34] | +6,47 [+3,04; +9,84] | -1,26 [-4,18; +1,39] | +5,21 [+1,33; +9,08] |
| kosz | quarter_total | total | 2154 / 3217 | 693 / 953 | tak | +6,64 [+0,57; +12,78] | +4,61 [+0,39; +8,81] | +3,80 [-0,55; +7,48] | +8,40 [+2,97; +13,41] |
| kosz | h1_team_total | side | 2849 / 3962 | 541 / 942 | tak | +15,21 [+9,55; +20,95] | +4,65 [+2,67; +6,65] | -0,71 [-2,40; +0,94] | +3,94 [+2,57; +5,28] |
| kosz | result_1x2 | margin | 1708 / 1646 | 854 / 823 | tak | +17,94 [+9,81; +25,81] | +19,03 [+10,83; +26,83] | -2,66 [-7,05; +1,72] | +16,37 [+8,02; +24,35] |
| kosz | team_odd_even | other | 1612 / 1625 | 807 / 813 | tak | -0,22 [-0,99; +0,56] | -0,04 [-0,33; +0,27] | -0,01 [-0,03; +0,01] | -0,05 [-0,34; +0,28] |
| kosz | double_chance | margin | 711 / 1554 | 369 / 809 | tak | +17,80 [+9,12; +25,90] | +17,90 [+9,61; +26,00] | +1,67 [-3,11; +6,65] | +19,57 [+10,96; +28,74] |
| kosz | h1_dnb | margin | 610 / 657 | 610 / 657 | tak | +8,55 [+0,52; +16,41] | +6,78 [-1,62; +14,62] | +6,80 [+0,54; +13,74] | +13,57 [+5,09; +21,99] |
| kosz | quarter_dnb | margin | 831 / 837 | 345 / 330 | tak | +7,67 [+2,82; +12,74] | +3,52 [-1,18; +8,01] | -0,69 [-5,83; +4,33] | +2,83 [-3,95; +9,78] |
| kosz | h2_1x2 | other | 299 / 326 | 299 / 326 | tak | +14,20 [+5,36; +23,37] | +15,51 [+5,38; +26,08] | -6,58 [-18,52; +5,27] | +8,93 [-0,44; +17,69] |
| kosz | h2_double_chance | other | 296 / 650 | 148 / 325 | tak | +13,13 [+3,55; +22,44] | +13,35 [+3,78; +22,75] | -0,42 [-1,04; +0,20] | +12,94 [+3,61; +21,95] |
| kosz | h2_dnb | other | 291 / 317 | 291 / 317 | tak | +14,03 [+4,85; +23,20] | +14,54 [+5,16; +24,51] | -5,82 [-17,70; +6,06] | +8,72 [-1,75; +18,59] |
| kosz | h2_handicap | margin | 984 / 1470 | 224 / 264 | tak | +17,14 [+6,56; +29,07] | +8,29 [+2,73; +13,89] | +20,90 [+0,79; +38,26] | +29,19 [+8,46; +47,12] |
| kosz | h2_total | total | 987 / 1471 | 225 / 264 | tak | +15,61 [-1,12; +33,08] | +4,95 [-4,92; +15,43] | +0,82 [-7,92; +9,65] | +5,77 [-2,98; +14,59] |
| kosz | h2_team_total | side | 1517 / 2003 | 225 / 263 | tak | +17,35 [+8,54; +26,94] | +6,86 [+2,57; +11,31] | -0,78 [-4,14; +2,88] | +6,08 [+2,62; +9,52] |
| kosz | player_assists | player | 969 / 1631 | 149 / 194 | tak | +3,12 [-1,49; +7,77] | +1,57 [-2,04; +5,22] | +1,34 [-0,42; +3,11] | +2,91 [-0,59; +6,37] |
| kosz | player_points | player | 1275 / 2047 | 155 / 194 | tak | +3,81 [-0,58; +8,29] | -0,87 [-2,66; +0,81] | -0,15 [-1,18; +0,96] | -1,02 [-2,81; +0,83] |
| kosz | player_pts_ast | player | 955 / 1604 | 148 / 194 | tak | +4,08 [-0,87; +9,27] | -1,45 [-3,77; +0,88] | -0,19 [-1,26; +0,88] | -1,64 [-4,07; +0,90] |
| kosz | player_pts_reb | player | 1036 / 1850 | 150 / 194 | tak | +4,24 [-0,47; +9,11] | -0,49 [-3,21; +2,37] | -0,93 [-2,14; +0,28] | -1,42 [-3,81; +1,17] |
| kosz | player_rebounds | player | 1061 / 1877 | 150 / 194 | tak | +2,56 [-1,52; +7,06] | +1,33 [-1,72; +4,57] | +2,72 [+0,72; +4,72] | +4,06 [+1,04; +7,03] |
| kosz | player_threes | player | 877 / 1574 | 145 / 194 | tak | -0,88 [-4,40; +2,90] | -0,82 [-3,95; +2,37] | +1,56 [-1,17; +3,95] | +0,75 [-2,72; +4,01] |
| kosz | player_steals | player | 553 / 844 | 93 / 103 | nie (< 100 meczów) | - | - | - | - |
| kosz | player_blocks | player | 216 / 320 | 81 / 100 | nie (< 100 meczów) | - | - | - | - |
| kosz | player_fg_attempts | player | 0 / 1032 | 0 / 92 | nie (< 100 meczów) | - | - | - | - |
| kosz | player_fg_made | player | 0 / 1026 | 0 / 92 | nie (< 100 meczów) | - | - | - | - |
| kosz | player_fouls | player | 0 / 1024 | 0 / 92 | nie (< 100 meczów) | - | - | - | - |
| kosz | player_ft_attempts | player | 0 / 1025 | 0 / 92 | nie (< 100 meczów) | - | - | - | - |
| kosz | player_ft_made | player | 0 / 1029 | 0 / 92 | nie (< 100 meczów) | - | - | - | - |
| kosz | player_pts_reb_ast | player | 101 / 654 | 13 / 92 | nie (< 100 meczów) | - | - | - | - |
| kosz | player_threes_attempts | player | 0 / 967 | 0 / 92 | nie (< 100 meczów) | - | - | - | - |
| kosz | player_turnovers | player | 0 / 1025 | 0 / 92 | nie (< 100 meczów) | - | - | - | - |
| kosz | player_twos_attempts | player | 0 / 1025 | 0 / 92 | nie (< 100 meczów) | - | - | - | - |
| kosz | player_twos_made | player | 0 / 1028 | 0 / 92 | nie (< 100 meczów) | - | - | - | - |
| kosz | player_reb_ast | player | 106 / 645 | 14 / 91 | nie (< 100 meczów) | - | - | - | - |
| siatkówka | winner | margin | 725 / 960 | 725 / 960 | tak | +17,54 [+8,74; +25,93] | +21,25 [+12,67; +29,45] | +4,51 [-1,10; +10,88] | +25,76 [+16,10; +35,03] |
| siatkówka | set_winner | margin | 1070 / 2754 | 346 / 881 | tak | +9,07 [+4,98; +12,84] | +10,84 [+7,01; +14,70] | +4,33 [+1,05; +7,56] | +15,18 [+10,86; +19,26] |
| siatkówka | set_points_odd_even | other | 366 / 890 | 345 / 877 | tak | +0,87 [-0,87; +2,63] | +0,64 [-1,60; +2,65] | -0,44 [-2,67; +1,97] | +0,20 [-0,74; +1,11] |
| siatkówka | points_odd_even | other | 617 / 867 | 617 / 867 | tak | +0,47 [-0,56; +1,51] | +1,05 [-0,68; +2,78] | -1,02 [-2,74; +0,64] | +0,02 [-0,16; +0,21] |
| siatkówka | points_total | total | 861 / 1303 | 541 / 806 | tak | +13,19 [+4,17; +22,36] | +2,88 [-0,63; +6,34] | -0,36 [-1,78; +1,14] | +2,52 [-0,76; +5,88] |
| siatkówka | set_handicap | margin | 926 / 1318 | 543 / 734 | tak | +8,05 [+0,87; +15,29] | +13,29 [+6,09; +20,27] | +6,87 [-0,32; +14,74] | +20,16 [+11,81; +29,59] |
| siatkówka | set_points_total | total | 385 / 903 | 290 / 726 | tak | +10,03 [+3,26; +17,46] | +1,97 [-1,85; +5,70] | +3,04 [+0,85; +5,21] | +5,01 [+0,85; +9,08] |
| siatkówka | sets_total | total | 735 / 1052 | 368 / 526 | tak | +1,07 [-3,91; +6,07] | +2,44 [-2,46; +7,21] | +6,44 [+1,88; +11,63] | +8,88 [+3,44; +14,21] |
| siatkówka | points_handicap | margin | 773 / 1121 | 351 / 503 | tak | +14,70 [+0,36; +29,25] | +7,53 [+3,34; +11,65] | +1,84 [-3,15; +6,84] | +9,37 [+4,07; +15,30] |
| siatkówka | team_wins_set | other | 213 / 425 | 107 / 213 | tak | +1,57 [-6,02; +8,96] | +4,05 [-2,48; +10,24] | +11,32 [+5,24; +17,49] | +15,37 [+6,29; +24,25] |
| siatkówka | team_sets_exact | other | 224 / 465 | 56 / 119 | nie (< 100 meczów) | - | - | - | - |
| siatkówka | set_extra_points | other | 28 / 47 | 28 / 47 | nie (< 100 meczów) | - | - | - | - |
| CS2 | match_winner | margin | 464 / 338 | 464 / 338 | tak | +1,93 [-10,77; +14,41] | +3,04 [-9,38; +15,53] | +14,19 [+2,77; +24,62] | +17,23 [-0,03; +33,94] |
| CS2 | map_winner | margin | 850 / 580 | 352 / 240 | tak | +1,25 [-6,64; +8,75] | +0,95 [-6,90; +8,74] | +10,68 [+3,51; +18,38] | +11,62 [+1,43; +20,89] |
| CS2 | maps_handicap | margin | 340 / 283 | 196 / 175 | tak | -2,70 [-16,47; +10,10] | -2,24 [-16,30; +11,35] | +7,18 [-3,39; +18,17] | +4,94 [-11,73; +20,80] |
| CS2 | maps_total | other | 199 / 177 | 196 / 175 | tak | -1,19 [-9,78; +6,95] | +2,18 [-4,76; +8,56] | +7,83 [-4,01; +19,50] | +10,00 [-5,91; +24,23] |
| CS2 | map_rounds_total | total | 2329 / 1715 | 246 / 164 | tak | -0,80 [-5,04; +3,18] | +1,00 [-3,09; +5,37] | +1,72 [-6,14; +10,01] | +2,72 [-5,89; +11,29] |
| CS2 | map_rounds_handicap | margin | 2622 / 2134 | 236 / 163 | tak | -2,81 [-10,85; +5,38] | -2,87 [-10,81; +5,39] | +4,48 [-1,62; +10,35] | +1,61 [-5,93; +9,15] |
| CS2 | rounds_handicap | margin | 124 / 163 | 124 / 163 | tak | +4,73 [-11,94; +23,01] | +4,03 [-5,41; +13,50] | +0,94 [-1,57; +3,31] | +4,97 [-3,98; +14,32] |
| CS2 | rounds_total | total | 124 / 163 | 124 / 163 | tak | +4,72 [-1,82; +11,18] | +3,17 [-4,90; +11,40] | +78,02 [+39,16; +116,56] | +81,20 [+38,71; +122,45] |
| CS2 | map_team_rounds | side | 2365 / 1719 | 170 / 111 | tak | -6,15 [-17,17; +5,02] | -4,62 [-14,46; +5,53] | +3,30 [-1,21; +7,88] | -1,32 [-11,94; +9,68] |
| CS2 | team_maps | other | 598 / 441 | 155 / 111 | tak | -9,09 [-29,25; +9,71] | -8,94 [-29,12; +10,41] | +5,04 [+0,34; +9,80] | -3,90 [-22,72; +14,87] |
| CS2 | team_rounds | side | 208 / 222 | 104 / 111 | tak | +5,16 [-5,26; +15,13] | +7,37 [-3,57; +19,71] | +13,66 [-3,23; +30,47] | +21,04 [+4,18; +39,04] |
| CS2 | player_assists | player | 2463 / 1850 | 132 / 94 | nie (< 100 meczów) | - | - | - | - |
| CS2 | player_deaths | player | 2495 / 1850 | 134 / 94 | nie (< 100 meczów) | - | - | - | - |
| CS2 | player_headshots | player | 2505 / 1850 | 134 / 94 | nie (< 100 meczów) | - | - | - | - |
| CS2 | player_kills | player | 2505 / 1850 | 134 / 94 | nie (< 100 meczów) | - | - | - | - |
| CS2 | team_kills | side | 509 / 376 | 134 / 94 | nie (< 100 meczów) | - | - | - | - |

Pominięte w tabeli: 0 rodzin z < 30 meczami hold-out.

### 4.2 Wyniki po cechach (ΔBrier = model+cecha − model, ×10⁻³, hold-out)

| cecha | komórek | ΔBrier < 0 | górna granica CI < 0 | mediana ΔBrier | najlepsza komórka (rodzina: ΔBrier [CI], p) | przeszło BH |
|---|---|---|---|---|---|---|
| A01 | 101 | 52 | 12 | -0,01 | kosz winner: -3,40 [-4,83; -1,89], p 4.0e-06 | 4 |
| A02 | 101 | 53 | 16 | -0,02 | kosz winner: -3,43 [-4,65; -2,03], p 6.0e-07 | 6 |
| A03 | 101 | 58 | 15 | -0,07 | piłka goals_for: -0,92 [-1,31; -0,53], p 1.6e-06 | 7 |
| A04 | 101 | 61 | 12 | -0,20 | piłka goals_for: -1,02 [-1,50; -0,60], p 3.4e-06 | 5 |
| A05 | 101 | 39 | 11 | +0,09 | kosz winner: -3,94 [-5,52; -2,33], p 1.9e-06 | 1 |
| A06 | 101 | 62 | 15 | -0,12 | piłka goals_for: -0,56 [-0,83; -0,30], p 1.3e-05 | 6 |
| A07 | 101 | 59 | 16 | -0,14 | piłka goals_for: -0,82 [-1,20; -0,46], p 8.0e-06 | 5 |
| A08 | 101 | 47 | 7 | +0,01 | piłka tackles_for: -4,00 [-6,38; -1,96], p 1.3e-04 | 2 |
| A09 | 59 | 21 | 3 | +0,13 | piłka tackles_for: -2,39 [-3,90; -1,04], p 4.1e-04 | 2 |
| A10 | 101 | 64 | 15 | -0,15 | piłka goals_for: -0,96 [-1,38; -0,58], p 2.0e-06 | 5 |
| A11 | 101 | 52 | 9 | -0,00 | piłka goals_for: -0,70 [-1,02; -0,35], p 2.6e-05 | 4 |
| A12 | 101 | 53 | 11 | -0,02 | piłka goals_for: -0,39 [-0,58; -0,20], p 5.8e-05 | 4 |
| A13 | 101 | 55 | 15 | -0,05 | piłka goals_1h_for: -1,43 [-2,02; -0,83], p 9.8e-07 | 6 |
| A14 | 100 | 59 | 8 | -0,04 | piłka goals_for: -0,74 [-1,07; -0,39], p 1.1e-05 | 5 |
| A15 | 101 | 56 | 21 | -0,10 | piłka goals_for: -0,96 [-1,40; -0,55], p 3.2e-06 | 9 |
| A16 | 98 | 38 | 7 | +0,01 | piłka saves_1h_total: -4,63 [-7,02; -2,40], p 2.9e-05 | 2 |
| A17 | 101 | 47 | 6 | +0,02 | piłka tackles_for: -4,65 [-7,82; -1,47], p 1.8e-03 | 1 |
| A18 | 59 | 30 | 3 | -0,02 | kosz total: -5,93 [-8,81; -3,12], p 5.0e-05 | 2 |
| A19 | 27 | 17 | 2 | -0,11 | piłka tackles_for: -1,04 [-1,60; -0,45], p 3.7e-04 | 1 |
| C01 | 126 | 60 | 17 | +0,01 | siatkówka set_handicap: -1,19 [-1,74; -0,61], p 2.0e-05 | 9 |
| C02 | 126 | 56 | 13 | +0,02 | piłka shots_total: -0,41 [-0,62; -0,22], p 4.6e-05 | 3 |
| C03 | 126 | 61 | 7 | +0,00 | kosz result_1x2: -0,26 [-0,42; -0,12], p 1.8e-04 | 2 |
| C04 | 67 | 16 | 0 | +0,15 | hokej result_1x2: -0,08 [-0,17; +0,01], p 3.8e-02 | 0 |
| C05 | 126 | 49 | 4 | +0,02 | piłka shots_total: -0,12 [-0,20; -0,04], p 2.4e-03 | 1 |
| C06 | 126 | 48 | 2 | +0,05 | piłka goals_2h_total: -0,15 [-0,25; -0,06], p 1.1e-03 | 1 |
| C07 | 38 | 8 | 0 | +0,59 | kosz double_chance: -0,07 [-0,22; +0,07], p 1.7e-01 | 0 |
| C08 | 42 | 12 | 0 | +0,29 | kosz quarter_1x2: -0,04 [-0,08; +0,01], p 4.7e-02 | 0 |
| C09 | 126 | 51 | 6 | +0,05 | piłka shots_on_target_2h_total: -2,86 [-4,53; -1,18], p 4.1e-04 | 1 |
| C10 | 126 | 55 | 1 | +0,02 | piłka double_chance: -0,01 [-0,03; -0,00], p 1.9e-02 | 0 |
| C11 | 92 | 37 | 5 | +0,03 | piłka goals_total: -0,15 [-0,23; -0,08], p 5.6e-05 | 2 |
| C12 | 101 | 36 | 4 | +0,17 | CS2 map_rounds_total: -4,48 [-7,90; -0,95], p 5.7e-03 | 0 |
| C13 | 126 | 45 | 2 | +0,04 | piłka goals_total: -0,16 [-0,31; -0,02], p 1.7e-02 | 0 |
| C14 | 126 | 41 | 1 | +0,20 | piłka shots_on_target_2h_total: -14,89 [-25,41; -4,42], p 4.2e-03 | 0 |
| L01 | 101 | 52 | 12 | -0,03 | piłka most_shots: -19,43 [-26,75; -11,42], p 5.7e-07 | 7 |
| L02 | 59 | 23 | 4 | +0,12 | kosz total: -5,38 [-7,77; -2,87], p 1.5e-05 | 2 |
| L03 | 101 | 29 | 2 | +0,07 | kosz total: -1,27 [-2,21; -0,28], p 5.2e-03 | 0 |
| L04 | 101 | 40 | 9 | +0,16 | piłka most_shots: -19,43 [-26,75; -11,42], p 5.7e-07 | 6 |
| P01 (kontrola) | 126 | 104 | 69 | -2,96 | piłka result_1x2: -12,42 [-14,51; -10,27], p 6.6e-31 | 69 |
| P02 (kontrola) | 126 | 74 | 25 | -0,05 | piłka double_chance: -5,78 [-6,78; -4,74], p 2.7e-28 | 24 |
| P03 (kontrola) | 63 | 32 | 11 | -0,04 | kosz winner: -16,20 [-21,48; -10,73], p 2.0e-09 | 11 |
| P04 (kontrola) | 52 | 12 | 0 | +0,09 | kosz result_1x2: -0,01 [-0,02; +0,00], p 6.1e-02 | 0 |
| P05 | 87 | 41 | 8 | +0,02 | piłka goals_1h_for: -1,02 [-1,48; -0,59], p 5.0e-06 | 3 |
| P06 | 38 | 20 | 4 | -0,00 | piłka goals_for: -0,44 [-0,62; -0,25], p 2.3e-06 | 1 |
| P07 | 52 | 26 | 2 | +0,00 | piłka saves_1h_total: -1,59 [-2,86; -0,37], p 7.0e-03 | 0 |
| Q01 | 6 | 1 | 0 | +0,43 | kosz player_threes: -0,89 [-2,49; +0,74], p 1.5e-01 | 0 |
| Q02 | 6 | 2 | 0 | +0,11 | kosz player_threes: -0,44 [-1,98; +1,14], p 2.9e-01 | 0 |
| Q03 | 6 | 2 | 0 | +0,10 | kosz player_threes: -0,25 [-1,65; +1,21], p 3.7e-01 | 0 |
| Q04 | 6 | 1 | 0 | +0,59 | kosz player_threes: -0,72 [-1,92; +0,41], p 1.2e-01 | 0 |
| Q05 | 6 | 2 | 0 | +0,71 | kosz player_assists: -0,08 [-0,85; +0,74], p 4.2e-01 | 0 |
| Q06 | 6 | 1 | 0 | +0,69 | kosz player_threes: -0,23 [-1,17; +0,62], p 3.2e-01 | 0 |
| Q07 | 6 | 1 | 0 | +0,44 | kosz player_threes: -0,10 [-1,13; +0,81], p 4.2e-01 | 0 |
| Q08 | 6 | 1 | 0 | +0,19 | kosz player_threes: -0,35 [-1,61; +0,77], p 2.8e-01 | 0 |
| Q09 | 6 | 0 | 0 | +0,60 | kosz player_pts_ast: +0,35 [-0,57; +1,29], p 7.7e-01 | 0 |
| Q10 | 6 | 2 | 0 | +0,33 | kosz player_assists: -0,35 [-1,17; +0,48], p 2.2e-01 | 0 |
| Q11 | 6 | 1 | 0 | +0,57 | kosz player_threes: -0,39 [-1,30; +0,44], p 2.1e-01 | 0 |
| Q12 | 6 | 1 | 0 | +0,39 | kosz player_threes: -0,33 [-1,23; +0,58], p 2.5e-01 | 0 |
| Q13 | 6 | 1 | 0 | +0,59 | kosz player_threes: -0,40 [-1,31; +0,44], p 2.0e-01 | 0 |
| Q14 | 6 | 0 | 0 | +0,68 | kosz player_pts_ast: +0,02 [-0,77; +0,84], p 5.2e-01 | 0 |
| Q15 | 6 | 1 | 0 | +0,59 | kosz player_threes: -0,09 [-1,22; +0,97], p 4.4e-01 | 0 |
| Q16 | 6 | 2 | 0 | +0,94 | kosz player_assists: -0,09 [-0,29; +0,11], p 2.0e-01 | 0 |
| Q17 | 6 | 2 | 0 | +0,20 | kosz player_threes: -0,58 [-2,35; +1,25], p 2.7e-01 | 0 |
| S01 | 126 | 41 | 6 | +0,11 | kosz winner: -2,81 [-4,14; -1,51], p 3.9e-05 | 1 |
| S02 | 126 | 33 | 5 | +0,14 | piłka double_chance: -1,24 [-1,85; -0,63], p 6.7e-05 | 3 |
| S03 | 126 | 44 | 9 | +0,09 | piłka draw_no_bet: -2,44 [-3,79; -1,07], p 1.2e-04 | 3 |
| S04 | 126 | 49 | 4 | +0,06 | piłka most_shots: -1,90 [-3,01; -0,74], p 4.8e-04 | 2 |
| S05 | 126 | 44 | 4 | +0,10 | piłka most_shots: -9,71 [-13,29; -6,04], p 1.5e-07 | 3 |
| S06 | 126 | 45 | 11 | +0,13 | kosz winner: -4,99 [-7,10; -2,91], p 1.2e-06 | 6 |
| S07 | 126 | 37 | 6 | +0,14 | hokej result_1x2: -0,15 [-0,24; -0,05], p 8.9e-04 | 1 |
| S08 | 126 | 40 | 8 | +0,16 | kosz winner: -6,09 [-8,86; -3,44], p 5.8e-06 | 5 |
| S09 (kontrola) | 126 | 75 | 23 | -0,13 | piłka result_1x2: -10,93 [-13,04; -8,87], p 6.0e-26 | 22 |
| S10 (kontrola) | 126 | 67 | 27 | -0,01 | piłka draw_no_bet: -11,16 [-13,66; -8,44], p 4.5e-18 | 26 |
| S11 (kontrola) | 126 | 63 | 10 | +0,00 | piłka result_1x2: -0,39 [-0,54; -0,24], p 1.8e-07 | 9 |
| T01 | 54 | 26 | 8 | +0,00 | piłka goals_for: -0,47 [-0,70; -0,22], p 4.2e-05 | 5 |
| T02 | 54 | 26 | 4 | +0,04 | piłka draw_no_bet: -1,42 [-2,22; -0,55], p 6.6e-04 | 3 |
| T03 | 54 | 14 | 3 | +0,24 | piłka goals_2h_for: -0,37 [-0,66; -0,07], p 5.1e-03 | 0 |
| T04 | 54 | 25 | 4 | +0,07 | piłka most_shots: -4,38 [-7,64; -1,19], p 4.9e-03 | 0 |
| T05 | 54 | 23 | 6 | +0,03 | piłka result_1x2: -1,13 [-1,71; -0,51], p 8.3e-05 | 6 |
| T06 | 54 | 20 | 2 | +0,06 | piłka shots_total: -2,26 [-4,27; -0,15], p 1.8e-02 | 0 |
| T07 | 54 | 25 | 5 | +0,06 | piłka result_handicap: -1,71 [-2,98; -0,52], p 2.5e-03 | 1 |
| T08 | 54 | 20 | 3 | +0,18 | piłka result_1x2: -0,21 [-0,37; -0,06], p 5.0e-03 | 0 |
| T09 | 54 | 24 | 2 | +0,08 | piłka corners_1h_for: -1,02 [-1,81; -0,11], p 1.0e-02 | 0 |
| T10 | 54 | 19 | 1 | +0,33 | piłka shots_for: -0,07 [-0,13; -0,02], p 4.5e-03 | 0 |
| T11 | 54 | 19 | 0 | +0,14 | piłka most_shots_on_target: -0,60 [-1,31; +0,12], p 5.6e-02 | 0 |
| T12 | 54 | 16 | 1 | +0,05 | piłka cards_points_total: -0,62 [-1,20; -0,07], p 1.6e-02 | 0 |
| T13 | 63 | 16 | 0 | +0,12 | piłka most_shots: -0,16 [-0,35; +0,02], p 4.1e-02 | 0 |
| T14 | 63 | 16 | 2 | +0,16 | piłka shots_on_target_2h_total: -8,03 [-14,52; -1,08], p 9.8e-03 | 0 |
| T15 | 63 | 19 | 0 | +0,10 | piłka cards_points_total: -0,37 [-1,33; +0,65], p 2.4e-01 | 0 |
| T16 | 12 | 6 | 0 | +0,02 | hokej period_handicap: -0,98 [-2,40; +0,43], p 9.2e-02 | 0 |
| T17 | 12 | 6 | 0 | +0,03 | hokej result_1x2: -0,43 [-0,95; +0,11], p 5.4e-02 | 0 |
| T18 | 12 | 2 | 0 | +0,33 | hokej result_1x2: -0,06 [-0,31; +0,19], p 3.3e-01 | 0 |
| T19 | 12 | 3 | 0 | +0,64 | hokej team_total: -0,11 [-0,39; +0,17], p 2.0e-01 | 0 |
| T20 | 12 | 3 | 0 | +0,16 | hokej result_1x2: -0,03 [-0,08; +0,03], p 1.6e-01 | 0 |
| T21 | 12 | 1 | 0 | +0,07 | hokej winner: -0,00 [-0,04; +0,03], p 4.4e-01 | 0 |
| T22 | 8 | 7 | 2 | -0,08 | hokej period_handicap: -1,01 [-2,03; -0,05], p 2.1e-02 | 0 |
| T23 | 19 | 9 | 0 | +0,04 | kosz quarter_total: -0,93 [-2,12; +0,28], p 5.9e-02 | 0 |
| T24 | 19 | 8 | 0 | +0,07 | kosz h2_team_total: -0,58 [-1,19; +0,09], p 3.8e-02 | 0 |
| T25 | 19 | 8 | 3 | +0,04 | kosz h1_1x2: -0,97 [-1,72; -0,24], p 4.2e-03 | 0 |
| T26 | 24 | 8 | 1 | +0,11 | kosz team_total: -0,78 [-1,31; -0,27], p 1.6e-03 | 1 |
| T27 | 24 | 10 | 0 | +0,05 | kosz quarter_team_total: -0,44 [-1,00; +0,12], p 5.4e-02 | 0 |
| T28 | 24 | 5 | 3 | +0,57 | kosz quarter_team_total: -0,79 [-1,50; -0,09], p 1.6e-02 | 0 |
| T29 | 19 | 8 | 2 | +0,20 | kosz quarter_1x2: -0,49 [-0,92; -0,05], p 1.2e-02 | 0 |
| T30 | 10 | 3 | 0 | +0,53 | siatkówka points_odd_even: -0,49 [-1,41; +0,46], p 1.5e-01 | 0 |
| T31 | 10 | 1 | 0 | +0,46 | siatkówka points_total: -0,13 [-1,23; +0,89], p 4.0e-01 | 0 |
| T32 | 10 | 3 | 0 | +0,14 | siatkówka sets_total: -0,49 [-1,23; +0,30], p 1.0e-01 | 0 |
| T33 | 10 | 5 | 0 | +0,19 | siatkówka set_handicap: -1,63 [-3,64; +0,26], p 4.5e-02 | 0 |
| T34 | 10 | 3 | 0 | +0,19 | siatkówka set_points_odd_even: -0,34 [-1,14; +0,42], p 1.9e-01 | 0 |
| T35 | 10 | 5 | 0 | +0,07 | siatkówka set_handicap: -1,12 [-3,01; +0,78], p 1.2e-01 | 0 |
| T36 | 11 | 4 | 0 | +0,11 | CS2 map_winner: -0,23 [-0,57; +0,12], p 9.2e-02 | 0 |
| T37 | 11 | 1 | 0 | +0,94 | CS2 match_winner: -0,07 [-1,71; +1,48], p 4.6e-01 | 0 |
| T38 | 11 | 3 | 0 | +0,66 | CS2 map_winner: -0,43 [-1,60; +0,71], p 2.3e-01 | 0 |
| T39 | 11 | 5 | 0 | +0,00 | CS2 match_winner: -0,46 [-1,59; +0,69], p 2.3e-01 | 0 |
| T40 | 11 | 3 | 0 | +0,24 | CS2 map_rounds_handicap: -1,05 [-3,08; +0,93], p 1.6e-01 | 0 |
| T41 | 11 | 3 | 0 | +0,08 | CS2 rounds_handicap: -0,66 [-5,03; +4,06], p 3.9e-01 | 0 |
| T42 | 11 | 2 | 0 | +0,75 | CS2 team_rounds: -0,25 [-1,03; +0,43], p 2.7e-01 | 0 |
| T43 | 11 | 1 | 0 | +1,02 | CS2 map_rounds_total: -0,13 [-0,46; +0,06], p 1.7e-01 | 0 |
| T44 | 11 | 5 | 0 | +0,00 | CS2 map_rounds_handicap: -0,11 [-0,24; +0,04], p 6.8e-02 | 0 |

Kolumna „najlepsza komórka” to najmniejsze p tej cechy w dowolnej rodzinie. ΔBrier < 0 oznacza, że cecha poprawia p.

### 4.3 Komórki, które przeszły BH (q = 0,10, cechy statystyczne)

| sport | rodzina | cecha | ΔBrier [CI] | Δlog-loss [CI] | p | luka do ceny przed | po |
|---|---|---|---|---|---|---|---|
| piłka | most_shots | S05 | -9,71 [-13,29; -6,04] | -20,61 [-28,14; -13,03] | 1.47e-07 | +37,82 [+21,23; +52,08] | +28,12 [+13,60; +41,05] |
| piłka | most_shots | L01 | -19,43 [-26,75; -11,42] | -41,81 [-57,05; -25,26] | 5.67e-07 | +37,82 [+21,23; +52,08] | +18,39 [+4,47; +32,35] |
| piłka | most_shots | L04 | -19,43 [-26,75; -11,42] | -41,81 [-57,05; -25,26] | 5.67e-07 | +37,82 [+21,23; +52,08] | +18,39 [+4,47; +32,35] |
| kosz | winner | A02 | -3,43 [-4,65; -2,03] | -7,92 [-10,71; -4,86] | 6.04e-07 | +23,81 [+17,58; +30,06] | +20,38 [+14,53; +26,46] |
| piłka | goals_1h_for | A13 | -1,43 [-2,02; -0,83] | -3,51 [-4,96; -2,06] | 9.78e-07 | +6,77 [+4,86; +8,75] | +5,34 [+3,52; +7,26] |
| kosz | winner | S06 | -4,99 [-7,10; -2,91] | -10,98 [-15,63; -6,53] | 1.19e-06 | +23,81 [+17,58; +30,06] | +18,82 [+13,02; +24,74] |
| piłka | goals_for | A03 | -0,92 [-1,31; -0,53] | -2,13 [-3,12; -1,13] | 1.64e-06 | +6,75 [+4,95; +8,59] | +5,82 [+4,14; +7,53] |
| kosz | winner | A05 | -3,94 [-5,52; -2,33] | -9,24 [-12,53; -5,77] | 1.93e-06 | +23,81 [+17,58; +30,06] | +19,87 [+13,79; +25,98] |
| piłka | goals_for | A10 | -0,96 [-1,38; -0,58] | -2,22 [-3,35; -1,15] | 2.00e-06 | +6,75 [+4,95; +8,59] | +5,79 [+4,09; +7,47] |
| piłka | most_shots | A13 | -20,60 [-28,78; -11,65] | -44,80 [-62,03; -26,21] | 2.06e-06 | +37,82 [+21,23; +52,08] | +17,22 [+4,05; +29,70] |
| piłka | goals_for | L01 | -0,69 [-1,00; -0,41] | -1,55 [-2,35; -0,81] | 2.18e-06 | +6,75 [+4,95; +8,59] | +6,05 [+4,28; +7,76] |
| piłka | goals_for | P06 | -0,44 [-0,62; -0,25] | -1,01 [-1,52; -0,52] | 2.31e-06 | +6,75 [+4,95; +8,59] | +6,31 [+4,55; +8,08] |
| piłka | goals_for | A15 | -0,96 [-1,40; -0,55] | -2,20 [-3,30; -1,16] | 3.19e-06 | +6,75 [+4,95; +8,59] | +5,78 [+4,07; +7,51] |
| piłka | goals_for | A04 | -1,02 [-1,50; -0,60] | -2,32 [-3,54; -1,20] | 3.42e-06 | +6,75 [+4,95; +8,59] | +5,72 [+4,02; +7,43] |
| piłka | goals_1h_for | A04 | -1,28 [-1,83; -0,74] | -3,09 [-4,46; -1,70] | 3.95e-06 | +6,77 [+4,86; +8,75] | +5,49 [+3,61; +7,35] |
| kosz | winner | A01 | -3,40 [-4,83; -1,89] | -7,90 [-11,00; -4,61] | 4.04e-06 | +23,81 [+17,58; +30,06] | +20,41 [+14,18; +26,60] |
| piłka | goals_1h_for | P05 | -1,02 [-1,48; -0,59] | -2,50 [-3,67; -1,39] | 4.96e-06 | +6,77 [+4,86; +8,75] | +5,75 [+3,89; +7,60] |
| piłka | most_corners_1h | A13 | -8,15 [-11,57; -4,63] | -16,87 [-24,12; -9,56] | 5.05e-06 | +19,47 [+9,44; +28,00] | +11,32 [+3,44; +18,72] |
| kosz | winner | S08 | -6,09 [-8,86; -3,44] | -13,69 [-19,84; -7,86] | 5.81e-06 | +23,81 [+17,58; +30,06] | +17,72 [+11,94; +23,82] |
| piłka | goals_for | P05 | -0,90 [-1,33; -0,51] | -2,00 [-3,10; -0,99] | 7.07e-06 | +6,75 [+4,95; +8,59] | +5,84 [+4,15; +7,49] |
| piłka | goals_for | A07 | -0,82 [-1,20; -0,46] | -1,95 [-2,89; -1,06] | 7.98e-06 | +6,75 [+4,95; +8,59] | +5,93 [+4,22; +7,61] |
| piłka | goals_1h_for | A10 | -1,15 [-1,70; -0,65] | -2,82 [-4,14; -1,51] | 8.77e-06 | +6,77 [+4,86; +8,75] | +5,62 [+3,74; +7,49] |
| piłka | goals_for | A14 | -0,74 [-1,07; -0,39] | -1,67 [-2,52; -0,75] | 1.11e-05 | +6,75 [+4,95; +8,59] | +6,01 [+4,30; +7,79] |
| piłka | goals_for | A06 | -0,56 [-0,83; -0,30] | -1,36 [-2,01; -0,73] | 1.25e-05 | +6,75 [+4,95; +8,59] | +6,18 [+4,43; +7,90] |
| piłka | goals_1h_for | L01 | -0,82 [-1,21; -0,44] | -2,03 [-3,04; -1,09] | 1.36e-05 | +6,77 [+4,86; +8,75] | +5,95 [+4,08; +7,79] |
| kosz | total | L02 | -5,38 [-7,77; -2,87] | -10,59 [-15,70; -5,18] | 1.53e-05 | +11,84 [+8,63; +14,84] | +6,45 [+2,80; +9,85] |
| piłka | draw_no_bet | S06 | -3,80 [-5,48; -1,90] | -9,45 [-13,54; -4,96] | 1.85e-05 | +18,59 [+14,52; +22,63] | +14,79 [+11,33; +18,55] |
| piłka | draw_no_bet | S08 | -3,44 [-5,12; -1,74] | -8,38 [-12,22; -4,47] | 1.93e-05 | +18,59 [+14,52; +22,63] | +15,15 [+11,50; +18,79] |
| siatkówka | set_handicap | C01 | -1,19 [-1,74; -0,61] | -2,76 [-4,02; -1,45] | 1.98e-05 | +13,29 [+6,09; +20,27] | +12,11 [+5,10; +18,93] |
| piłka | goals_1h_total | A04 | -0,48 [-0,71; -0,25] | -1,20 [-1,82; -0,59] | 2.38e-05 | +1,67 [+0,05; +3,19] | +1,19 [-0,35; +2,65] |
| piłka | goals_for | A11 | -0,70 [-1,02; -0,35] | -1,66 [-2,50; -0,80] | 2.62e-05 | +6,75 [+4,95; +8,59] | +6,05 [+4,29; +7,77] |
| piłka | result_1x2 | L01 | -0,31 [-0,46; -0,16] | -0,92 [-1,27; -0,54] | 2.71e-05 | +12,21 [+9,68; +14,63] | +11,90 [+9,34; +14,38] |
| piłka | result_1x2 | L04 | -0,31 [-0,46; -0,16] | -0,92 [-1,27; -0,54] | 2.71e-05 | +12,21 [+9,68; +14,63] | +11,90 [+9,34; +14,38] |
| piłka | shots_total | C01 | -0,70 [-1,03; -0,36] | -1,52 [-2,24; -0,76] | 2.72e-05 | +8,59 [+1,90; +15,87] | +7,88 [+1,20; +14,98] |
| piłka | double_chance | L01 | -0,32 [-0,47; -0,16] | -0,94 [-1,31; -0,56] | 2.80e-05 | +12,22 [+9,69; +14,65] | +11,90 [+9,34; +14,39] |
| piłka | double_chance | L04 | -0,32 [-0,47; -0,16] | -0,94 [-1,31; -0,56] | 2.80e-05 | +12,22 [+9,69; +14,65] | +11,90 [+9,34; +14,39] |
| piłka | double_chance | S06 | -1,62 [-2,39; -0,86] | -4,08 [-5,84; -2,31] | 2.90e-05 | +12,22 [+9,69; +14,65] | +10,60 [+8,24; +12,98] |
| piłka | saves_1h_total | A16 | -4,63 [-7,02; -2,40] | -9,99 [-15,20; -5,18] | 2.90e-05 | +12,18 [+3,73; +21,08] | +7,55 [-0,25; +15,24] |
| piłka | double_chance | S08 | -1,37 [-2,01; -0,68] | -3,43 [-4,91; -1,85] | 3.61e-05 | +12,22 [+9,69; +14,65] | +10,85 [+8,43; +13,15] |
| kosz | winner | S01 | -2,81 [-4,14; -1,51] | -6,27 [-9,16; -3,47] | 3.89e-05 | +23,81 [+17,58; +30,06] | +20,99 [+15,00; +26,92] |
| piłka | goals_1h_for | A14 | -0,01 [-0,01; -0,00] | -0,02 [-0,03; -0,01] | 4.02e-05 | +6,77 [+4,86; +8,75] | +6,77 [+4,85; +8,74] |
| piłka | goals_for | T01 | -0,47 [-0,70; -0,22] | -1,22 [-1,81; -0,60] | 4.20e-05 | +6,75 [+4,95; +8,59] | +6,28 [+4,45; +8,19] |
| piłka | goals_total | A10 | -0,15 [-0,23; -0,07] | -0,42 [-0,62; -0,22] | 4.43e-05 | +2,34 [+1,14; +3,59] | +2,19 [+1,03; +3,44] |
| piłka | double_chance | T01 | -1,35 [-2,00; -0,59] | -3,28 [-4,74; -1,56] | 4.54e-05 | +12,22 [+9,69; +14,65] | +10,88 [+8,39; +13,34] |
| piłka | result_1x2 | S08 | -1,39 [-2,05; -0,68] | -3,48 [-5,00; -1,85] | 4.55e-05 | +12,21 [+9,68; +14,63] | +10,82 [+8,40; +13,09] |
| piłka | shots_total | C02 | -0,41 [-0,62; -0,22] | -0,91 [-1,35; -0,47] | 4.58e-05 | +8,59 [+1,90; +15,87] | +8,17 [+1,53; +15,38] |
| piłka | result_1x2 | S06 | -1,65 [-2,45; -0,85] | -4,16 [-6,01; -2,30] | 4.94e-05 | +12,21 [+9,68; +14,63] | +10,56 [+8,18; +12,93] |
| kosz | total | A18 | -5,93 [-8,81; -3,12] | -11,71 [-18,08; -5,64] | 5.01e-05 | +11,84 [+8,63; +14,84] | +5,90 [+2,07; +9,58] |
| piłka | goals_total | C11 | -0,15 [-0,23; -0,08] | -0,38 [-0,56; -0,19] | 5.62e-05 | +2,34 [+1,14; +3,59] | +2,19 [+1,00; +3,43] |
| piłka | goals_for | A12 | -0,39 [-0,58; -0,20] | -0,88 [-1,38; -0,38] | 5.75e-05 | +6,75 [+4,95; +8,59] | +6,36 [+4,60; +8,15] |
| piłka | result_1x2 | T01 | -1,35 [-2,02; -0,58] | -3,29 [-4,79; -1,54] | 6.05e-05 | +12,21 [+9,68; +14,63] | +10,86 [+8,38; +13,32] |
| piłka | most_cards_points | S05 | -4,50 [-6,80; -2,08] | -9,58 [-14,50; -4,41] | 6.55e-05 | +9,10 [+4,10; +13,71] | +4,60 [-0,35; +8,77] |
| piłka | double_chance | S02 | -1,24 [-1,85; -0,63] | -3,16 [-4,60; -1,77] | 6.75e-05 | +12,22 [+9,69; +14,65] | +10,98 [+8,45; +13,40] |
| piłka | result_1x2 | T05 | -1,13 [-1,71; -0,51] | -2,75 [-4,15; -1,36] | 8.28e-05 | +12,21 [+9,68; +14,63] | +11,08 [+8,55; +13,48] |
| piłka | goals_1h_for | A15 | -1,03 [-1,58; -0,53] | -2,57 [-3,92; -1,28] | 9.04e-05 | +6,77 [+4,86; +8,75] | +5,74 [+3,86; +7,64] |
| piłka | draw_no_bet | S02 | -2,65 [-4,00; -1,23] | -6,74 [-9,86; -3,45] | 9.10e-05 | +18,59 [+14,52; +22,63] | +15,94 [+12,22; +19,78] |
| piłka | goals_for | A13 | -0,93 [-1,42; -0,46] | -2,17 [-3,46; -0,93] | 9.58e-05 | +6,75 [+4,95; +8,59] | +5,81 [+4,12; +7,47] |
| piłka | result_1x2 | S02 | -1,27 [-1,91; -0,62] | -3,23 [-4,73; -1,76] | 1.09e-04 | +12,21 [+9,68; +14,63] | +10,94 [+8,42; +13,34] |
| piłka | goals_1h_total | A10 | -0,20 [-0,31; -0,09] | -0,53 [-0,83; -0,23] | 1.13e-04 | +1,67 [+0,05; +3,19] | +1,46 [-0,13; +2,98] |
| piłka | draw_no_bet | A03 | -2,44 [-3,79; -1,07] | -6,02 [-8,99; -2,85] | 1.21e-04 | +18,59 [+14,52; +22,63] | +16,15 [+12,36; +19,84] |
| piłka | draw_no_bet | S03 | -2,44 [-3,79; -1,07] | -6,02 [-8,99; -2,85] | 1.21e-04 | +18,59 [+14,52; +22,63] | +16,15 [+12,36; +19,84] |
| piłka | tackles_for | A08 | -4,00 [-6,38; -1,96] | -8,06 [-12,82; -3,96] | 1.25e-04 | -0,11 [-3,95; +3,60] | -4,11 [-8,40; -0,17] |
| hokej | double_chance | C01 | -0,17 [-0,26; -0,08] | -0,31 [-0,50; -0,13] | 1.30e-04 | +5,13 [+0,38; +9,72] | +4,96 [+0,24; +9,54] |
| piłka | tackles_for | A12 | -2,34 [-3,50; -1,04] | -4,70 [-7,02; -2,09] | 1.50e-04 | -0,11 [-3,95; +3,60] | -2,45 [-6,25; +1,17] |
| piłka | goals_1h_for | A03 | -0,84 [-1,31; -0,41] | -2,10 [-3,23; -1,05] | 1.58e-04 | +6,77 [+4,86; +8,75] | +5,93 [+4,04; +7,85] |
| piłka | double_chance | T05 | -1,16 [-1,80; -0,50] | -2,85 [-4,37; -1,32] | 1.74e-04 | +12,22 [+9,69; +14,65] | +11,06 [+8,50; +13,49] |
| kosz | result_1x2 | C03 | -0,26 [-0,42; -0,12] | -0,57 [-0,89; -0,25] | 1.76e-04 | +19,03 [+10,83; +26,83] | +18,77 [+10,51; +26,55] |
| piłka | goals_1h_for | A11 | -0,47 [-0,74; -0,23] | -1,18 [-1,82; -0,57] | 1.80e-04 | +6,77 [+4,86; +8,75] | +6,30 [+4,36; +8,26] |
| piłka | goals_for | A02 | -0,55 [-0,85; -0,26] | -1,23 [-1,98; -0,46] | 1.92e-04 | +6,75 [+4,95; +8,59] | +6,20 [+4,41; +7,98] |
| piłka | double_chance | S03 | -1,17 [-1,80; -0,47] | -2,96 [-4,46; -1,31] | 2.06e-04 | +12,22 [+9,69; +14,65] | +11,05 [+8,62; +13,48] |
| piłka | double_chance | A03 | -1,17 [-1,80; -0,47] | -2,96 [-4,46; -1,31] | 2.06e-04 | +12,22 [+9,69; +14,65] | +11,05 [+8,62; +13,48] |
| piłka | goals_1h_total | A07 | -0,08 [-0,13; -0,04] | -0,21 [-0,33; -0,10] | 2.06e-04 | +1,67 [+0,05; +3,19] | +1,58 [-0,01; +3,11] |
| kosz | h1_handicap | A13 | -1,70 [-2,65; -0,78] | -3,42 [-5,33; -1,57] | 2.19e-04 | +4,53 [+2,24; +6,89] | +2,83 [+0,40; +5,16] |
| piłka | draw_no_bet | T05 | -1,78 [-2,78; -0,85] | -4,52 [-6,80; -2,37] | 2.57e-04 | +18,59 [+14,52; +22,63] | +16,81 [+12,75; +20,69] |
| piłka | shots_on_target_1h_total | C01 | -1,21 [-1,89; -0,54] | -2,54 [-3,99; -1,09] | 2.76e-04 | +5,92 [+0,29; +11,41] | +4,70 [-0,52; +10,14] |
| piłka | draw_no_bet | T01 | -2,26 [-3,45; -0,92] | -5,47 [-8,20; -2,33] | 2.88e-04 | +18,59 [+14,52; +22,63] | +16,33 [+12,55; +20,24] |
| piłka | result_1x2 | A03 | -1,18 [-1,84; -0,45] | -3,00 [-4,56; -1,28] | 2.89e-04 | +12,21 [+9,68; +14,63] | +11,02 [+8,59; +13,47] |
| piłka | result_1x2 | S03 | -1,18 [-1,84; -0,45] | -3,00 [-4,56; -1,28] | 2.89e-04 | +12,21 [+9,68; +14,63] | +11,02 [+8,59; +13,47] |
| piłka | goals_2h_total | C11 | -0,06 [-0,09; -0,02] | -0,14 [-0,22; -0,05] | 3.12e-04 | +2,29 [+0,87; +3,69] | +2,23 [+0,83; +3,63] |
| kosz | total | A06 | -5,45 [-8,59; -2,18] | -10,84 [-17,50; -4,20] | 3.36e-04 | +11,84 [+8,63; +14,84] | +6,38 [+2,80; +9,73] |
| kosz | double_chance | C03 | -0,41 [-0,63; -0,17] | -0,90 [-1,38; -0,39] | 3.50e-04 | +17,90 [+9,61; +26,00] | +17,49 [+9,24; +25,78] |
| piłka | draw_no_bet | L01 | -1,91 [-3,01; -0,70] | -5,19 [-7,90; -2,22] | 3.51e-04 | +18,59 [+14,52; +22,63] | +16,68 [+12,80; +20,49] |
| piłka | draw_no_bet | L04 | -1,91 [-3,01; -0,70] | -5,19 [-7,90; -2,22] | 3.51e-04 | +18,59 [+14,52; +22,63] | +16,68 [+12,80; +20,49] |
| piłka | result_handicap | T01 | -1,87 [-2,88; -0,83] | -5,36 [-8,27; -2,39] | 3.68e-04 | +9,44 [+6,80; +12,18] | +7,57 [+5,02; +10,22] |
| piłka | tackles_for | A19 | -1,04 [-1,60; -0,45] | -2,09 [-3,20; -0,90] | 3.71e-04 | -0,11 [-3,95; +3,60] | -1,15 [-5,02; +2,47] |
| piłka | tackles_for | A09 | -2,39 [-3,90; -1,04] | -4,83 [-7,94; -2,09] | 4.05e-04 | -0,11 [-3,95; +3,60] | -2,50 [-6,50; +1,17] |
| piłka | shots_on_target_2h_total | C09 | -2,86 [-4,53; -1,18] | -5,94 [-9,41; -2,40] | 4.14e-04 | +4,38 [-16,38; +25,89] | +1,52 [-18,71; +21,81] |
| piłka | most_shots | S04 | -1,90 [-3,01; -0,74] | -3,97 [-6,25; -1,59] | 4.80e-04 | +37,82 [+21,23; +52,08] | +35,92 [+19,95; +49,85] |
| piłka | double_chance | A06 | -1,00 [-1,56; -0,42] | -2,57 [-3,83; -1,23] | 4.81e-04 | +12,22 [+9,69; +14,65] | +11,22 [+8,73; +13,66] |
| kosz | total | L04 | -5,74 [-9,15; -2,41] | -11,38 [-18,71; -4,06] | 5.89e-04 | +11,84 [+8,63; +14,84] | +6,10 [+1,88; +10,33] |
| kosz | total | A02 | -6,66 [-11,11; -2,55] | -13,72 [-23,02; -5,10] | 5.91e-04 | +11,84 [+8,63; +14,84] | +5,17 [+0,79; +8,99] |
| piłka | tackles_for | A03 | -4,99 [-7,80; -1,84] | -10,01 [-15,66; -3,69] | 6.30e-04 | -0,11 [-3,95; +3,60] | -5,10 [-9,49; -0,91] |
| piłka | draw_no_bet | A15 | -2,37 [-3,81; -0,92] | -5,93 [-9,33; -2,55] | 6.31e-04 | +18,59 [+14,52; +22,63] | +16,22 [+12,48; +19,92] |
| piłka | draw_no_bet | A02 | -1,97 [-3,10; -0,73] | -4,80 [-7,47; -2,00] | 6.44e-04 | +18,59 [+14,52; +22,63] | +16,63 [+12,92; +20,32] |
| piłka | draw_no_bet | T02 | -1,42 [-2,22; -0,55] | -3,40 [-5,31; -1,45] | 6.59e-04 | +18,59 [+14,52; +22,63] | +17,17 [+13,17; +21,04] |
| piłka | goals_1h_for | A07 | -0,49 [-0,79; -0,21] | -1,21 [-1,89; -0,58] | 6.64e-04 | +6,77 [+4,86; +8,75] | +6,28 [+4,35; +8,24] |
| piłka | result_1x2 | A06 | -1,01 [-1,60; -0,40] | -2,60 [-3,91; -1,20] | 7.02e-04 | +12,21 [+9,68; +14,63] | +11,20 [+8,73; +13,63] |
| piłka | shots_1h_for | A09 | -1,09 [-1,78; -0,42] | -2,19 [-3,56; -0,84] | 7.25e-04 | +1,93 [-2,22; +5,90] | +0,83 [-3,24; +4,89] |
| kosz | result_1x2 | A02 | -0,05 [-0,08; -0,02] | -0,12 [-0,18; -0,06] | 7.30e-04 | +19,03 [+10,83; +26,83] | +18,98 [+10,77; +26,78] |
| piłka | corners_for | P05 | -1,16 [-1,85; -0,47] | -2,73 [-4,37; -1,09] | 7.46e-04 | +5,36 [+2,79; +8,04] | +4,20 [+2,05; +6,46] |
| kosz | result_1x2 | S06 | -2,05 [-3,25; -0,76] | -4,38 [-6,99; -1,66] | 8.25e-04 | +19,03 [+10,83; +26,83] | +16,99 [+9,37; +24,14] |
| kosz | winner | A06 | -0,83 [-1,37; -0,35] | -1,88 [-3,02; -0,80] | 8.39e-04 | +23,81 [+17,58; +30,06] | +22,98 [+16,81; +29,20] |
| piłka | shots_on_target_total | C01 | -0,86 [-1,40; -0,30] | -2,17 [-3,48; -0,81] | 8.54e-04 | +3,98 [-0,59; +8,41] | +3,12 [-1,20; +7,17] |
| piłka | draw_no_bet | A06 | -1,53 [-2,46; -0,51] | -4,10 [-6,20; -1,78] | 8.59e-04 | +18,59 [+14,52; +22,63] | +17,06 [+13,18; +20,96] |
| piłka | double_chance | A15 | -1,10 [-1,74; -0,37] | -2,82 [-4,37; -1,13] | 8.60e-04 | +12,22 [+9,69; +14,65] | +11,12 [+8,69; +13,55] |
| hokej | result_1x2 | S07 | -0,15 [-0,24; -0,05] | -0,26 [-0,44; -0,10] | 8.90e-04 | +4,69 [+0,11; +9,71] | +4,55 [-0,02; +9,56] |
| piłka | goals_2h_for | L04 | -0,32 [-0,52; -0,12] | -0,78 [-1,26; -0,32] | 9.36e-04 | +5,57 [+3,64; +7,42] | +5,26 [+3,36; +7,06] |
| piłka | goals_1h_for | A02 | -0,59 [-0,96; -0,25] | -1,53 [-2,41; -0,69] | 9.45e-04 | +6,77 [+4,86; +8,75] | +6,18 [+4,32; +8,12] |
| kosz | handicap | A11 | -0,35 [-0,56; -0,13] | -0,70 [-1,14; -0,27] | 9.83e-04 | +12,28 [+8,42; +16,19] | +11,93 [+8,13; +15,82] |
| piłka | double_chance | A11 | -0,59 [-0,97; -0,21] | -1,47 [-2,33; -0,59] | 1.01e-03 | +12,22 [+9,69; +14,65] | +11,63 [+9,20; +14,17] |
| piłka | tackles_for | A15 | -4,44 [-7,27; -1,54] | -8,91 [-14,55; -3,10] | 1.02e-03 | -0,11 [-3,95; +3,60] | -4,55 [-8,99; -0,68] |
| piłka | result_1x2 | A15 | -1,11 [-1,77; -0,36] | -2,84 [-4,43; -1,10] | 1.06e-03 | +12,21 [+9,68; +14,63] | +11,10 [+8,71; +13,53] |
| piłka | corners_for | L01 | -0,85 [-1,38; -0,33] | -2,02 [-3,31; -0,74] | 1.06e-03 | +5,36 [+2,79; +8,04] | +4,51 [+2,22; +6,92] |
| piłka | shots_on_target_total | C02 | -0,62 [-1,02; -0,22] | -1,53 [-2,49; -0,55] | 1.08e-03 | +3,98 [-0,59; +8,41] | +3,36 [-1,04; +7,56] |
| hokej | period_total | A14 | -0,17 [-0,29; -0,06] | -0,41 [-0,68; -0,14] | 1.08e-03 | +0,30 [-1,37; +1,86] | +0,12 [-1,55; +1,64] |
| piłka | goals_2h_total | C06 | -0,15 [-0,25; -0,06] | -0,37 [-0,62; -0,14] | 1.09e-03 | +2,29 [+0,87; +3,69] | +2,14 [+0,74; +3,54] |
| kosz | winner | A15 | -1,45 [-2,37; -0,56] | -3,35 [-5,37; -1,35] | 1.18e-03 | +23,81 [+17,58; +30,06] | +22,36 [+16,27; +28,61] |
| piłka | shots_on_target_1h_total | C02 | -0,11 [-0,18; -0,04] | -0,22 [-0,37; -0,08] | 1.20e-03 | +5,92 [+0,29; +11,41] | +5,81 [+0,22; +11,31] |
| hokej | total | A03 | -0,59 [-1,01; -0,19] | -1,27 [-2,18; -0,41] | 1.26e-03 | +3,06 [-0,13; +6,24] | +2,47 [-0,71; +5,48] |
| piłka | goals_total | A14 | -0,07 [-0,11; -0,03] | -0,17 [-0,28; -0,05] | 1.46e-03 | +2,34 [+1,14; +3,59] | +2,27 [+1,11; +3,53] |
| piłka | most_cards_points | S04 | -4,22 [-7,05; -1,31] | -9,08 [-15,11; -3,03] | 1.51e-03 | +9,10 [+4,10; +13,71] | +4,88 [+0,13; +9,42] |
| piłka | goals_total | A07 | -0,18 [-0,30; -0,06] | -0,45 [-0,73; -0,17] | 1.53e-03 | +2,34 [+1,14; +3,59] | +2,16 [+1,01; +3,38] |
| kosz | total | A01 | -6,17 [-10,72; -2,05] | -12,61 [-22,04; -3,95] | 1.55e-03 | +11,84 [+8,63; +14,84] | +5,66 [+1,16; +9,77] |
| kosz | team_total | T26 | -0,78 [-1,31; -0,27] | -1,57 [-2,62; -0,53] | 1.58e-03 | +3,50 [+1,91; +5,17] | +2,71 [+0,98; +4,49] |
| piłka | goals_1h_total | C01 | -0,02 [-0,03; -0,01] | -0,04 [-0,07; -0,02] | 1.60e-03 | +1,67 [+0,05; +3,19] | +1,65 [+0,04; +3,17] |
| piłka | shots_on_target_1h_for | C01 | -0,07 [-0,11; -0,02] | -0,14 [-0,23; -0,04] | 1.60e-03 | +5,04 [-1,75; +11,41] | +4,97 [-1,83; +11,36] |
| kosz | quarter_1x2 | S06 | -1,48 [-2,40; -0,48] | -2,92 [-4,83; -0,88] | 1.67e-03 | +6,47 [+3,04; +9,84] | +4,99 [+1,83; +8,29] |
| piłka | goals_1h_total | A14 | -0,37 [-0,61; -0,13] | -0,92 [-1,57; -0,29] | 1.70e-03 | +1,67 [+0,05; +3,19] | +1,30 [-0,21; +2,75] |
| piłka | shots_total | T05 | -1,41 [-2,31; -0,47] | -3,07 [-5,05; -0,96] | 1.78e-03 | +8,59 [+1,90; +15,87] | +7,18 [+0,38; +14,25] |
| piłka | tackles_for | A17 | -4,65 [-7,82; -1,47] | -9,34 [-15,70; -2,97] | 1.82e-03 | -0,11 [-3,95; +3,60] | -4,76 [-9,23; -0,42] |
| piłka | corners_for | A07 | -1,22 [-2,02; -0,42] | -2,73 [-4,59; -0,86] | 1.85e-03 | +5,36 [+2,79; +8,04] | +4,15 [+1,96; +6,47] |
| kosz | result_1x2 | S08 | -2,81 [-4,59; -0,87] | -6,01 [-9,82; -1,84] | 1.89e-03 | +19,03 [+10,83; +26,83] | +16,22 [+8,81; +23,39] |
| piłka | result_1x2 | A12 | -0,60 [-1,01; -0,18] | -1,48 [-2,41; -0,54] | 1.90e-03 | +12,21 [+9,68; +14,63] | +11,61 [+9,20; +14,14] |
| piłka | shots_for | C01 | -0,63 [-1,05; -0,21] | -1,37 [-2,27; -0,47] | 1.92e-03 | +3,20 [-2,26; +8,67] | +2,57 [-2,78; +7,98] |
| piłka | corners_for | A04 | -1,33 [-2,17; -0,45] | -2,82 [-5,06; -0,49] | 1.92e-03 | +5,36 [+2,79; +8,04] | +4,04 [+1,91; +6,31] |
| kosz | h1_1x2 | A01 | -1,40 [-2,31; -0,51] | -2,81 [-4,75; -0,95] | 1.93e-03 | +9,02 [+2,96; +14,78] | +7,62 [+1,51; +13,24] |
| piłka | tackles_for | A01 | -5,20 [-8,56; -1,70] | -10,44 [-17,19; -3,40] | 1.94e-03 | -0,11 [-3,95; +3,60] | -5,31 [-9,90; -1,06] |
| kosz | h1_1x2 | A15 | -0,15 [-0,24; -0,04] | -0,29 [-0,48; -0,08] | 1.96e-03 | +9,02 [+2,96; +14,78] | +8,87 [+2,84; +14,60] |
| piłka | offsides_for | A10 | -2,95 [-4,92; -0,94] | -6,23 [-10,58; -1,68] | 1.99e-03 | +5,51 [-0,42; +11,12] | +2,56 [-2,11; +7,08] |
| piłka | most_corners_1h | S05 | -7,30 [-12,25; -2,17] | -14,95 [-25,47; -4,07] | 2.03e-03 | +19,47 [+9,44; +28,00] | +12,16 [+4,75; +19,08] |
| piłka | result_handicap | T05 | -1,92 [-3,21; -0,61] | -6,29 [-10,04; -2,67] | 2.04e-03 | +9,44 [+6,80; +12,18] | +7,52 [+4,90; +10,13] |
| piłka | goals_for | A18 | -0,39 [-0,65; -0,12] | -0,91 [-1,59; -0,20] | 2.07e-03 | +6,75 [+4,95; +8,59] | +6,36 [+4,55; +8,19] |
| piłka | goals_total | A16 | -0,06 [-0,10; -0,02] | -0,14 [-0,23; -0,03] | 2.13e-03 | +2,34 [+1,14; +3,59] | +2,28 [+1,08; +3,53] |
| piłka | shots_on_target_for | C01 | -0,51 [-0,83; -0,15] | -1,22 [-2,01; -0,31] | 2.18e-03 | +5,37 [+1,94; +8,76] | +4,86 [+1,49; +8,21] |
| piłka | shots_on_target_for | A04 | -0,20 [-0,34; -0,07] | -0,42 [-0,75; -0,12] | 2.19e-03 | +5,37 [+1,94; +8,76] | +5,17 [+1,75; +8,54] |
| piłka | goals_1h_for | A12 | -0,52 [-0,89; -0,19] | -1,32 [-2,23; -0,50] | 2.30e-03 | +6,77 [+4,86; +8,75] | +6,25 [+4,32; +8,10] |
| piłka | most_shots | T05 | -1,22 [-2,07; -0,35] | -2,56 [-4,35; -0,73] | 2.32e-03 | +37,82 [+21,23; +52,08] | +36,60 [+20,49; +51,05] |
| piłka | shots_on_target_2h_total | L02 | -0,01 [-0,01; -0,00] | -0,01 [-0,02; -0,00] | 2.36e-03 | +4,38 [-16,38; +25,89] | +4,37 [-16,39; +25,88] |
| piłka | goals_1h_total | A13 | -0,26 [-0,45; -0,08] | -0,65 [-1,14; -0,17] | 2.36e-03 | +1,67 [+0,05; +3,19] | +1,40 [-0,17; +2,87] |
| piłka | shots_total | C05 | -0,12 [-0,20; -0,04] | -0,27 [-0,46; -0,09] | 2.36e-03 | +8,59 [+1,90; +15,87] | +8,47 [+1,79; +15,74] |
| piłka | tackles_total | A08 | -4,49 [-7,37; -1,51] | -9,04 [-14,85; -3,01] | 2.43e-03 | +0,14 [-3,24; +3,32] | -4,35 [-8,26; -0,89] |
| piłka | double_chance | T02 | -0,71 [-1,21; -0,17] | -1,75 [-2,92; -0,48] | 2.45e-03 | +12,22 [+9,69; +14,65] | +11,52 [+8,80; +13,93] |
| kosz | total | A15 | -5,90 [-10,13; -1,84] | -11,92 [-21,02; -3,30] | 2.46e-03 | +11,84 [+8,63; +14,84] | +5,93 [+1,83; +9,54] |
| piłka | result_handicap | T07 | -1,71 [-2,98; -0,52] | -5,24 [-8,66; -1,71] | 2.47e-03 | +9,44 [+6,80; +12,18] | +7,73 [+5,19; +10,30] |
| piłka | result_1x2 | T02 | -0,70 [-1,19; -0,16] | -1,72 [-2,87; -0,49] | 2.49e-03 | +12,21 [+9,68; +14,63] | +11,51 [+8,82; +13,93] |

Uwaga: komórki nie są niezależne. `result_1x2`, `double_chance` i `draw_no_bet` to ten sam mecz, a L01 = L04 oraz A03 = S03 w rodzinach marginesowych z linią 0. BH zachowuje FDR przy dodatniej zależności (PRDS).

### 4.4 Kontrole cenowe, które przeszły BH (osobny BH)

| sport | rodzina | cecha | ΔBrier [CI] | luka do ceny przed | po |
|---|---|---|---|---|---|
| piłka | result_1x2 | P01 | -12,42 [-14,51; -10,27] | +12,21 [+9,68; +14,63] | -0,21 [-0,80; +0,34] |
| piłka | double_chance | P01 | -12,44 [-14,54; -10,28] | +12,22 [+9,69; +14,65] | -0,22 [-0,79; +0,33] |
| piłka | double_chance | P02 | -5,78 [-6,78; -4,74] | +12,22 [+9,69; +14,65] | +6,44 [+4,56; +8,24] |
| piłka | result_1x2 | P02 | -4,47 [-5,26; -3,66] | +12,21 [+9,68; +14,63] | +7,74 [+5,73; +9,64] |
| piłka | result_1x2 | S09 | -10,93 [-13,04; -8,87] | +12,21 [+9,68; +14,63] | +1,28 [+0,54; +2,08] |
| piłka | double_chance | S09 | -9,80 [-11,64; -7,92] | +12,22 [+9,69; +14,65] | +2,42 [+1,25; +3,60] |
| piłka | draw_no_bet | S09 | -18,04 [-21,47; -14,55] | +18,59 [+14,52; +22,63] | +0,55 [-0,36; +1,45] |
| piłka | draw_no_bet | P01 | -18,04 [-21,47; -14,55] | +18,59 [+14,52; +22,63] | +0,55 [-0,36; +1,45] |
| piłka | draw_no_bet | P02 | -6,66 [-7,96; -5,33] | +18,59 [+14,52; +22,63] | +11,93 [+8,45; +15,30] |
| piłka | goals_for | P01 | -7,03 [-8,77; -5,38] | +6,75 [+4,95; +8,59] | -0,29 [-0,58; +0,01] |
| piłka | draw_no_bet | S10 | -11,16 [-13,66; -8,44] | +18,59 [+14,52; +22,63] | +7,44 [+4,71; +10,06] |
| piłka | result_1x2 | S10 | -6,62 [-8,06; -4,99] | +12,21 [+9,68; +14,63] | +5,58 [+3,97; +7,37] |
| piłka | double_chance | S10 | -6,27 [-7,65; -4,69] | +12,22 [+9,69; +14,65] | +5,96 [+4,22; +7,78] |
| piłka | goals_for | P02 | -1,25 [-1,59; -0,95] | +6,75 [+4,95; +8,59] | +5,49 [+3,81; +7,13] |
| kosz | winner | S09 | -24,13 [-29,56; -18,13] | +23,81 [+17,58; +30,06] | -0,32 [-2,47; +1,77] |
| kosz | winner | P01 | -24,13 [-29,56; -18,13] | +23,81 [+17,58; +30,06] | -0,32 [-2,47; +1,77] |
| piłka | result_handicap | P01 | -9,41 [-11,78; -7,22] | +9,44 [+6,80; +12,18] | +0,03 [-0,45; +0,55] |
| piłka | goals_1h_for | P01 | -6,81 [-8,56; -5,16] | +6,77 [+4,86; +8,75] | -0,03 [-0,34; +0,30] |
| kosz | winner | S10 | -20,40 [-25,62; -15,27] | +23,81 [+17,58; +30,06] | +3,41 [-0,15; +6,88] |
| piłka | goals_1h_for | P02 | -2,33 [-2,95; -1,73] | +6,77 [+4,86; +8,75] | +4,45 [+2,90; +6,04] |

(pierwsze 20 z 161 wg p; pełna lista w `results.json`, pole `bh_pass_control`)

### 4.5 Model „wszystko” po sportach (hold-out, Brier ×10⁻³)

| sport | wiersze | mecze | Brier p rekal. | Brier „wszystko” | Brier cena | „wszystko” − p rekal. | p rekal. − cena | „wszystko” − cena |
|---|---|---|---|---|---|---|---|---|
| piłka | 244773 | 5568 | 199,25 | 199,65 | 194,01 | +0,39 [-0,22; +0,97] | +5,25 [+4,36; +6,05] | +5,64 [+4,80; +6,37] |
| hokej | 27280 | 1148 | 213,96 | 215,72 | 210,80 | +1,76 [-0,06; +3,50] | +3,15 [+1,14; +5,32] | +4,92 [+3,07; +6,93] |
| kosz | 85817 | 1706 | 246,18 | 245,33 | 239,20 | -0,85 [-1,88; +0,25] | +6,99 [+5,62; +8,40] | +6,13 [+4,90; +7,48] |
| siatkówka | 11593 | 961 | 223,14 | 226,59 | 215,59 | +3,45 [+1,38; +5,53] | +7,55 [+4,97; +10,13] | +11,00 [+8,20; +13,75] |
| CS2 | 7935 | 342 | 217,69 | 224,08 | 219,23 | +6,39 [+1,97; +10,48] | -1,53 [-9,23; +4,87] | +4,86 [-3,10; +12,33] |

Komórek nietestowanych (za mało pokrycia na rozwoju / bez zmienności / < 30 wierszy hold-out): 321.

Cechy z największą liczbą komórek nietestowanych: C07 77, C08 73, C04 59, P05 39, C11 23, P07 11, P04 11, T26 6, T27 6, T28 6, T22 4, A16 3, P06 2, A14 1


## 5. Czego nie zmierzono i dlaczego

- **Tenis:** poza zakresem (osobny model punktowy).
- **Zawodnicy piłki:** rynek jednostronny, brak ceny bez marży, więc nie da
  się ich porównać z ceną (jak w `pokrycie_sportow`).
- **Zawodnicy hokeja (9 rodzin) i CS2 (4 rodziny):** 82-94 mecze na
  hold-oucie (< 100), wymienieni w 4.1, nietestowani. Dotyczy to też
  `player_hits`, jedynej rodziny sportu mierzonego lepszej od ceny w
  przeglądzie pokrycia. Kosz V2 (9 rodzin) ma 0 wierszy na rozwoju: linie
  czytane dopiero od 10-23.
- **T45, regularni spoza przewidywanej XI:** `lineups_prematch.json` istnieje
  tylko dla meczów czytanych przez analityków, od 10-23 (1 003 mecze w 14
  dniach). To próba wybrana przez zestaw do czytania, bez stanu „na start”
  dla reszty. Bramkarz startowy w hokeju: cache nie ma składu przed meczem.
  Zamiast tego jest skuteczność obrony drużyny (T18).
- **Ruch linii w piłce (P03) i minuty przed startem (P04):** OFFER nie
  zapisuje ceny otwarcia ani historii cen w wierszu rozliczenia. W sportach
  mierzonych P03 to pierwszy snapshot dnia wobec ceny rozliczenia.
- **Podróż (C07 / C08):** miasto obiektu bieżącego meczu piłki nie jest w
  cache (`sofa_listed_event` go nie ma). W sportach mierzonych pokrycie jest
  niskie, więc 77 / 73 komórki nietestowane.
- **Stawka / tabela:** S06-S08 to tabela odbudowana z puli meczów
  wczytanych dla zbioru, a nie oficjalna tabela. Bez „meczów o
  utrzymanie / awans” wprost.
- **Sędzia (T13-T15):** pokrycie 60% wierszy piłki (`sofa_event_referee`).
- **Rodziny `other`** (parzystości, dokładne wyniki, kombinacje `result_or_*`,
  `both_over_*`) mają tylko cechy ogólne (kontekst, siła, cena). Własna
  statystyka nie jest zdefiniowana dla połączeń.
- **p bazowe to p sprzed krzywej** (jak w mierniku 11-05). Na kuponie wchodzi
  pewność po krzywej i dowodzie liniowym. Rekalibracja na rozwoju to
  przybliżenie krzywej, nie ta sama krzywa.
- **Jedno okno 38 dni, jeden podział:** każda „poprawa” jest pomiarem na 13
  dniach hold-outu, bez powtórzenia.
- **Nic nie zmienia druku:** brak przełącznika, krzywej i refitu. Bez
  konfiguracji, bez commita.

## 6. Pliki

- `scripts/sofa/measure_feature_battery.py`: lista (`list`), zbiór
  (`build`), ocena (`evaluate`, `--dev-check`). Tylko do odczytu, nie czyta
  rekordu odmów.
- `tests/sofa/test_measure_feature_battery.py`: brak wglądu w przyszłość
  (`as_of`, sfabrykowany przyszły mecz) i krok BH.
- `data/refit_2026-11-05_battery/`:
  - `rows_<sport>.pkl` (zbiór z cechami);
  - `build_log.json`;
  - `results.json` (wszystkie komórki, rodziny, model „wszystko”);
  - `sports/results_dev_check.json` (przebieg próbny na rozwoju).
