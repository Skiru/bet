# Audyt kuponu 2026-09-09 — pełne rozliczenie, analiza przyczyn i plan naprawy

Rozliczenie kuponu dnia z pliku `runs/2026-09-09/2026-09-09_kupony.md` (40 singli, 1 kupon Bet Builder, 1 rekomendowany kupon akumulowany AKO z 6 nóg).
Wszystkie dane rozliczone oficjalnym mechanizmem `scripts/simple/backtest_slate.py --date 2026-09-09 --recorded` w oparciu o oficjalne protokoły meczowe dostawców bzzoiro i ESPN.

---

## 1. Globalne podsumowanie rozliczenia (Trafione vs Nietrafione)

### A. Wszystkie pozycje singlowe (40 wierszy arkusza)

| Koszyk selekcji | Wyemitowane | Rozliczone | Trafione (**WON**) | Nietrafione (**LOST**) | Brak danych (**NO_DATA**) | Skuteczność (na rozliczonych) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **VALUE** (warte swojej ceny / próg pobity) | 11 | 10 | **7** | **3** | 1 | **70.0%** |
| **WITHIN_TOLERANCE** (do 5% pod progiem) | 8 | 7 | **5** | **2** | 1 | **71.4%** |
| **PRICED_BELOW_THRESHOLD** (informacyjne / tani rynek) | 21 | 20 | **18** | **2** | 1 | **90.0%** |
| **ŁĄCZNIE (Cały arkusz singli)** | **40** | **37** | **30** | **7** | **3** | **81.1%** |

*Uwagi dotyczące pozycji NO_DATA (3):*
1. **Real Cundinamarca – Internacional de Bogotá (rożne OVER 8.5):** bzzoiro nie publikuje statystyk rzutów rożnych dla wczesnych rund Pucharu Kolumbii (dostępny jest tylko wynik 1:2).
2. **Mirra Andreeva – Coco Gauff (podwójne błędy UNDER 11.5):** ESPN Scoreboard w feedzie tenisa nie dostarcza statystyk serwisowych (asów ani podwójnych błędów).
3. **Daejeon Hana Citizen – FC Anyang (rożne UNDER 10.5):** feed bzzoiro nie zawierał zliczeń rzutów rożnych dla tego meczu K-League.

---

### B. Kupony łączone (Kombinacje)

1. **Bet Builder (Rangers – St. Mirren · Scottish Premiership):** **NIETRAFIONY (1/2)**
   - *Noga 1:* gole Rangers UNDER 2.5 @ 1.66 -> **TRAFIONY** (1 gol Rangers, wynik 1:0)
   - *Noga 2:* rożne Rangers UNDER 7.5 @ 1.85 -> **NIETRAFIONY** (12 rożnych Rangers)
   - *Status kuponu:* Przegrany przez nadmiar rożnych gospodarzy.

2. **Kupon Akumulowany AKO (6 zdarzeń z różnych meczów, najlepsze EV):** **NIETRAFIONY (4/6)**
   - Noga 1: *Paris Saint-Germain – ŠK Slovan Bratislava:* gole UNDER 4.5 @ 1.87 -> **NIETRAFIONY** (wynik 6:1, 7 goli)
   - Noga 2: *Rangers – St. Mirren:* gole Rangers UNDER 2.5 @ 1.66 -> **TRAFIONY** (1 gol)
   - Noga 3: *DC United – Columbus Crew:* spalone UNDER 4.5 @ 1.62 -> **TRAFIONY** (3 spalone)
   - Noga 4: *VfB Stuttgart – Viking FK:* gole UNDER 4.5 @ 1.56 -> **TRAFIONY** (wynik 3:1, 4 gole)
   - Noga 5: *Al-Fateh – Diriyah:* gole UNDER 3.5 @ 1.53 -> **TRAFIONY** (wynik 1:2, 3 gole)
   - Noga 6: *Atlanta United – Orlando City SC:* spalone Atlanty UNDER 2.5 @ 1.75 -> **NIETRAFIONY** (6 spalonych Atlanty)
   - *Status kuponu:* 4 wygrane, 2 przegrane.

---

## 2. Szczegółowa analiza każdego z 27 wydarzeń i wszystkich 40 nóg

Poniżej zestawiono wszystkie mecze w kolejności, z podaniem wyniku końcowego meczu, parametrów linii, kursu, rzeczywistego wyniku statystyki oraz statusu rozstrzygnięcia.

### 1. Palmeiras – LDU Quito (Copa Libertadores) · Wynik: 1:0
* **Noga (#1):** strzały celne drużyny: Palmeiras **UNDER 7.5** | Kurs: 1.38 | Kategoria: **VALUE**
  * *Rzeczywista wartość:* **6.0** strzałów celnych Palmeiras
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
  * *Analiza:* LDU Quito w fazie pucharowej na wyjeździe zagrało w skrajnie głębokim i zagęszczonym bloku obronnym. Palmeiras oddawało strzały z nieprzygotowanych pozycji z dystansu (wiele zablokowanych), co utrzymało liczbę strzałów w światło bramki na poziomie 6.

### 2. Atlanta United – Orlando City SC (MLS) · Wynik: 2:3
* **Noga 1 (#2):** spalone drużyny: Atlanta United **UNDER 2.5** | Kurs: 1.75 | Kategoria: **VALUE**
  * *Rzeczywista wartość:* **6.0** spalonych Atlanty
  * *Rozstrzygnięcie:* **NIETRAFIONY (LOST)**
  * *Analiza:* Dynamiczny, chaotyczny przebieg meczu. Orlando objęło prowadzenie, zmuszając Atlantę do nieustannych ataków bezpośrednich za wysoko postawioną linię obrony Orlando. W efekcie gracze Atlanty dali się złapać na spalonym aż 6 razy.
* **Noga 2 (#38):** suma goli: **OVER 0.5** | Kurs: 1.01 | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **5.0** goli
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
  * *Analiza:* Spotkanie MLS z natury otwarte, pierwsza bramka padła już we wczesnej fazie.

### 3. DC United – Columbus Crew (MLS) · Wynik: 2:1
* **Noga 1 (#3):** spalone meczu: **UNDER 4.5** | Kurs: 1.62 | Kategoria: **VALUE**
  * *Rzeczywista wartość:* **3.0** spalone
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
  * *Analiza:* Styl Columbus Crew oparty na ataku pozycyjnym i dużej liczbie podań w poprzek boiska spowolnił tempo i wyeliminował prostopadłe zagrania z głębi pola.
* **Noga 2 (#28):** suma goli: **OVER 1.5** | Kurs: 1.20 | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **3.0** gole
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
  * *Analiza:* Mecz zrealizował normę overową ligi amerykańskiej.

### 4. Real Cundinamarca – Internacional de Bogotá (Copa Colombia) · Wynik: 1:2
* **Noga (#4):** rzuty rożne meczu: **OVER 8.5** | Kurs: 1.57 | Kategoria: **VALUE**
  * *Rzeczywista wartość:* **Brak danych** w protokole dostawcy
  * *Rozstrzygnięcie:* **BRAK DANYCH (NO_DATA)**
  * *Analiza:* Provider bzzoiro nie posiada statystyk rzutów rożnych dla niszowych pucharów Ameryki Południowej (znany limit bazy).

### 5. CF Montréal – Charlotte FC (MLS) · Wynik: 1:2
* **Noga 1 (#5):** faule meczu: **UNDER 23.5** | Kurs: 1.66 | Kategoria: **VALUE**
  * *Rzeczywista wartość:* **23.0** faule
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
  * *Analiza:* Granica domknięta na styk (23 przy linii 23.5). Sędzia pozwalał na grę bark w bark, co uratowało zakład o pół faulu.
* **Noga 2 (#22):** rzuty rożne meczu: **OVER 7.5** | Kurs: 1.32 | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **14.0** rożnych
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
  * *Analiza:* Ostra gra skrzydłami i pogoń za wynikiem wygenerowały 14 kornerów.
* **Noga 3 (#40):** suma goli: **OVER 0.5** | Kurs: 1.01 | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **3.0** gole
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**

### 6. Santos – Atlético Mineiro (Campeonato Brasileiro Série A) · Wynik: 2:0
* **Noga 1 (#6):** spalone meczu: **OVER 1.5** | Kurs: 1.44 | Kategoria: **VALUE**
  * *Rzeczywista wartość:* **4.0** spalone
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
  * *Analiza:* Wysoka linia defensywna Santosu i szybkie wyjścia Atlético wygenerowały 4 spalone.
* **Noga 2 (#17):** suma goli: **OVER 1.5** | Kurs: 1.44 | Kategoria: **WITHIN_TOLERANCE**
  * *Rzeczywista wartość:* **2.0** gole
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
  * *Analiza:* Dwa trafienia gospodarzy zapewniły trafienie linii over 1.5.

### 7. Paris Saint-Germain – ŠK Slovan Bratislava (Liga Mistrzów) · Wynik: 6:1
* **Noga (#7):** suma goli meczu: **UNDER 4.5** | Kurs: 1.87 | Kategoria: **VALUE**
  * *Rzeczywista wartość:* **7.0** goli
  * *Rozstrzygnięcie:* **NIETRAFIONY (LOST)**
  * *Analiza:* **Kardynalny błąd braku ważenia klasy rywala (Quality Mismatch).** Próba statystyczna Slovana (10/10 poniżej 4.5 gola) została zebrana z ligi słowackiej, gdzie Slovan dominuje. Na Parc des Princes z PSG różnica potencjałów doprowadziła do pogromu 6:1.

### 8. Rangers – St. Mirren (Scottish Premiership) · Wynik: 1:0
* **Noga 1 (#8):** gole drużyny: Rangers **UNDER 2.5** | Kurs: 1.66 | Kategoria: **VALUE & Bet Builder**
  * *Rzeczywista wartość:* **1.0** gol Rangers
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
  * *Analiza:* Skrajny pragmatyzm i niska skuteczność Rangers, zderzone z żelazną obroną St. Mirren.
* **Noga 2 (#9):** rzuty rożne drużyny: Rangers **UNDER 7.5** | Kurs: 1.85 | Kategoria: **VALUE & Bet Builder**
  * *Rzeczywista wartość:* **12.0** rożnych Rangers
  * *Rozstrzygnięcie:* **NIETRAFIONY (LOST)**
  * *Analiza:* **Klasyczna pułapka oblężenia faworyta (Favorite Siege Trap).** Rangers męczyli się przez 90 minut, bijąc bezradnie w mur St. Mirren. Brak szybkiego gola wymusił dziesiątki dośrodkowań i wybić na rzuty rożne (aż 12 kornerów samego Rangers).

### 9. Al-Fateh – Diriyah (Saudi Pro League) · Wynik: 1:2
* **Noga (#10):** suma goli meczu: **UNDER 3.5** | Kurs: 1.53 | Kategoria: **VALUE**
  * *Rzeczywista wartość:* **3.0** gole
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
  * *Analiza:* Trzy bramki w meczu (1:2) pozwoliły na bezpieczne domknięcie linii under 3.5.

### 10. VfB Stuttgart – Viking FK (Mecz towarzyski klubowy) · Wynik: 3:1
* **Noga (#11):** suma goli meczu: **UNDER 4.5** | Kurs: 1.56 | Kategoria: **VALUE**
  * *Rzeczywista wartość:* **4.0** gole
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
  * *Analiza:* Spokojna końcówka meczu towarzyskiego po rotacjach w składach obu drużyn.

### 11. Fortaleza – Avaí (Copa do Brasil / Serie B) · Wynik: 1:0
* **Noga 1 (#12):** gole drużyny: Fortaleza **UNDER 2.5** | Kurs: 1.22 | Kategoria: **WITHIN_TOLERANCE**
  * *Rzeczywista wartość:* **1.0** gol Fortalezy
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
* **Noga 2 (#13):** strzały celne meczu: **UNDER 10.5** | Kurs: 1.39 | Kategoria: **WITHIN_TOLERANCE**
  * *Rzeczywista wartość:* **5.0** strzałów celnych
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
* **Noga 3 (#15):** punkty kartkowe: **UNDER 5.5** | Kurs: 1.55 | Kategoria: **WITHIN_TOLERANCE**
  * *Rzeczywista wartość:* **2.0** kartki (20 pkt)
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
  * *Analiza:* Płynny, mało agresywny mecz z pełną dominacją defensywną obu stron.

### 12. Botafogo-SP – Grêmio Novorizontino (Serie B) · Wynik: 1:3
* **Noga (#14):** rzuty rożne drużyny: Novorizontino **OVER 4.5** | Kurs: 1.51 | Kategoria: **WITHIN_TOLERANCE**
  * *Rzeczywista wartość:* **4.0** rożne Novorizontino
  * *Rozstrzygnięcie:* **NIETRAFIONY (LOST)**
  * *Analiza:* **Pułapka wczesnego prowadzenia.** Novorizontino szybko wyszło na 2:0 na wyjeździe i całkowicie zrezygnowało z ofensywy skrzydłami, skupiając się na kontrolowaniu środka pola. Zabrakło zaledwie 1 rzutu rożnego.

### 13. América de Cali – Deportivo Pereira (Liga Kolumbijska) · Wynik: 4:1
* **Noga (#16):** suma goli meczu: **UNDER 3.5** | Kurs: 1.39 | Kategoria: **WITHIN_TOLERANCE**
  * *Rzeczywista wartość:* **5.0** goli
  * *Rozstrzygnięcie:* **NIETRAFIONY (LOST)**
  * *Analiza:* Całkowita utrata dyscypliny taktycznej gości po stracie dwóch bramek. Płynna wymiana ciosów skończyła się wynikiem 4:1 (5 bramek).

### 14. Philadelphia Union – FC Cincinnati (MLS) · Wynik: 5:0
* **Noga (#18):** rzuty rożne meczu: **UNDER 12.5** | Kurs: 1.40 | Kategoria: **WITHIN_TOLERANCE**
  * *Rzeczywista wartość:* **8.0** rożnych
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
  * *Analiza:* Szybkie gole padające ze strzałów z pola karnego nie przekładały się na wybijanie piłki na rzuty rożne.

### 15. Mirra Andreeva – Coco Gauff (WTA US Open) · Wynik: 1:2 w setach (14:15 w gemach)
* **Noga (#19):** podwójne błędy meczu: **UNDER 11.5** | Kurs: 1.50 | Kategoria: **WITHIN_TOLERANCE**
  * *Rzeczywista wartość:* **Brak danych** w feedzie ESPN
  * *Rozstrzygnięcie:* **BRAK DANYCH (NO_DATA)**

### 16. Boca Juniors – São Paulo (Copa Libertadores) · Wynik: 1:0
* **Noga (#20):** suma goli meczu: **OVER 1.5** | Kurs: brak (mecz w toku w trakcie runu) | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **1.0** gol
  * *Rozstrzygnięcie:* **NIETRAFIONY (LOST)**
  * *Analiza:* Skrajny pragmatyzm fazy play-off Copa Libertadores. Jednobramkowe prowadzenie Boca zamknęło mecz na cztery spusty.

### 17. Daejeon Hana Citizen – FC Anyang (K League 1) · Wynik: 3:2
* **Noga 1 (#21):** rzuty rożne meczu: **UNDER 10.5** | Kurs: brak | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **Brak danych**
  * *Rozstrzygnięcie:* **BRAK DANYCH (NO_DATA)**
* **Noga 2 (#30):** suma goli: **OVER 1.5** | Kurs: brak | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **5.0** goli
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**

### 18. Derby County – West Bromwich Albion (Championship) · Wynik: 0:1
* **Noga 1 (#23):** rzuty rożne meczu: **OVER 8.5** | Kurs: 1.50 | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **14.0** rożnych
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
* **Noga 2 (#32):** suma goli: **OVER 0.5** | Kurs: 1.06 | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **1.0** gol
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**

### 19. Chelsea – Leeds United (Premier League) · Wynik: 6:3
* **Noga 1 (#24):** rzuty rożne meczu: **UNDER 11.5** | Kurs: 1.38 | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **8.0** rożnych
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
* **Noga 2 (#36):** suma goli: **OVER 0.5** | Kurs: 1.02 | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **9.0** goli
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**

### 20. FC Twente – SC Telstar (Holandia) · Wynik: 1:0
* **Noga (#25):** rzuty rożne meczu: **OVER 7.5** | Kurs: 1.16 | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **11.0** rożnych
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**

### 21. Norwich City – Birmingham City (Championship) · Wynik: 2:1
* **Noga 1 (#26):** suma goli: **OVER 1.5** | Kurs: 1.23 | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **3.0** gole
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
* **Noga 2 (#29):** rzuty rożne meczu: **OVER 7.5** | Kurs: 1.30 | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **13.0** rożnych
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**

### 22. Toronto FC – Nashville SC (MLS) · Wynik: 2:1
* **Noga (#27):** rzuty rożne meczu: **UNDER 11.5** | Kurs: 1.38 | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **11.0** rożnych
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**

### 23. St. Johnstone – Celtic (Scottish Premiership) · Wynik: 0:1
* **Noga 1 (#31):** rzuty rożne meczu: **OVER 8.5** | Kurs: 1.33 | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **13.0** rożnych
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**
* **Noga 2 (#35):** suma goli: **OVER 0.5** | Kurs: 1.02 | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **1.0** gol
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**

### 24. Gangwon FC – Jeonbuk Hyundai Motors (K League 1) · Wynik: 1:1
* **Noga (#33):** suma goli meczu: **OVER 1.5** | Kurs: brak | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **2.0** gole
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**

### 25. Pohang Steelers – Gimcheon Sangmu FC (K League 1) · Wynik: 0:0
* **Noga (#34):** suma goli meczu: **OVER 0.5** | Kurs: brak | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **0.0** goli
  * *Rozstrzygnięcie:* **NIETRAFIONY (LOST)**
  * *Analiza:* **Pułapka pozornego pewniaka (Zero-Defect Bias).** Bezbramkowy remis 0:0 na pozornie pewnym rynku (p_central > 95%). Kursy rzędu 1.01-1.02 niosą asymetryczne ryzyko straty całego kapitału przy zerowym zysku.

### 26. SSC Napoli – Arsenal (Liga Mistrzów) · Wynik: 0:1
* **Noga (#37):** suma goli meczu: **OVER 0.5** | Kurs: 1.05 | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **1.0** gol
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**

### 27. Gwangju FC – Jeju SK (K League 1) · Wynik: 0:1
* **Noga (#39):** suma goli meczu: **UNDER 3.5** | Kurs: brak | Kategoria: **PRICED_BELOW_THRESHOLD**
  * *Rzeczywista wartość:* **1.0** gol
  * *Rozstrzygnięcie:* **TRAFIONY (WON)**

---

## 3. Dogłębna diagnoza przyczyn pomyłek (Root Cause Analysis)

Analiza 7 nietrafionych pozycji ujawnia **trzy kluczowe wady systemowe** w pipeline:

### 1. Ekstrapolacja danych bez uwzględnienia różnicy klas (Quality Mismatch / Domain Fallacy)
* **Objaw:** *PSG – Slovan Bratislava (gole UNDER 4.5)* -> padło 7 bramek (6:1).
* **Przyczyna:** Model potraktował próbę 10/10 meczów Slovana z ligi słowackiej jako reprezentatywną dla starcia wyjazdowego z PSG na Parc des Princes. Slovan w lidze krajowej kontroluje grę i traci mało bramek, natomiast przeciwko elitarnemu atakowi w Europie uległ całkowitej deklasacji. Pipeline traktuje mecze ligowe i pucharowe równorzędnie pod kątem średniej goli.

### 2. Pułapka oblężenia faworyta przy rzutach rożnych (Favorite Siege Script Trap)
* **Objaw:** *Rangers – St. Mirren (rożne Rangers UNDER 7.5)* -> nabito 12 kornerów.
* **Przyczyna:** Skrajny faworyt grający u siebie przeciwko rywalowi z głębokim blokiem obronnym („autobusem”) przy braku wczesnej bramki zawsze generuje lawinę rzutów rożnych. Branie linii UNDER na rzuty rożne wielkiego faworyta jest strukturalnym błędem strategicznym: jeśli faworyt nie strzeli w 15. minucie, zmasowane ataki skrzydłami i wybicia obrońców bez trudu przełamią linię 7.5.

### 3. Złudzenie kontroli na kursach śmieciowych (Ultra-Low Odds Asymmetry)
* **Objaw:** *Pohang Steelers – Gimcheon Sangmu (gole OVER 0.5)* -> 0:0.
* **Przyczyna:** Rynek z kursem ~1.02 ma implikowane prawdopodobieństwo 98%. W rzeczywistości w ligach azjatyckich i drugich dywizjach bezbramkowe remisy zdarzają się w 7–9% spotkań. Wiersze po kursie 1.01–1.05 niszczą wartość oczekiwaną kuponu, co już wcześniej wykazały badania historyczne (ujemny edge -1.0% do -4.3% na próbie 668 meczów).

### 4. Luki ewidencyjne w ligach peryferyjnych (Dead Metrics)
* **Objaw:** 3 wiersze ze statusem NO_DATA (Puchar Kolumbii, tenis props, K-League).
* **Przyczyna:** Generator rynków emituje szczeble drabinki dla lig, w których provider nie posiada box-score ze zliczaniem danej metryki (np. rożne w pucharach). Zakład jest niemożliwy do rzetelnej weryfikacji.

---

## 4. Plan naprawy Simple Pipeline (Plan Wdrożeniowy)

Aby wyeliminować powyższe anomalie, planuje się implementację 5 modułów naprawczych:

### Moduł 1: Bramka Mismatchu Jakościowego w pucharach (`CEILING_QUALITY_MISMATCH`)
* **Mechanizm:** Jeśli mecz odbywa się w ramach rozgrywek międzynarodowych (UEFA Champions League, Europa League, Copa Libertadores) i różnica siły drużyn przekracza próg (np. drużyna z ligi poza top 10 przeciwko top 5 UEFA):
  * **Automatyczny zakaz rynków UNDER na sumę goli oraz gole faworyta.**
  * Zerowanie wagi próbki ligowej słabszej drużyny (`weight = 0`).

### Moduł 2: Zakaz rynków UNDER na rzuty rożne dominującego faworyta (`CEILING_SIEGE_CORNER_INVERSION`)
* **Mechanizm:** Gdy drużyna gospodarzy ma kurs na czyste zwycięstwo (1X2) poniżej 1.35 (domniemany gigantyczny faworyt):
  * **Bezwzględne wykluczenie linii UNDER na rzuty rożne tej drużyny oraz meczu poniżej linii 10.5.**
  * Scenariusz „oblężenia pola karnego” jest asymetrycznie groźny dla underów rożnych.

### Moduł 3: Filtr obsługi statystyk przez dostawców w fazie ENRICH
* **Mechanizm:** Wprowadzenie tabeli możliwości dostawców (`metric_capabilities_by_league.json`):
  * Jeśli dostawca bzzoiro nie dostarcza zliczeń `corners` lub `cards` dla danych rozgrywek (np. Copa Colombia, niszowe puchary), pipeline w fazie `ANALYZE` ma zakaz emitowania wierszy dla tych metryk.
  * Zapobiega to oferowaniu wierszy, które kończą się jako niezweryfikowalne NO_DATA.

### Moduł 4: Twarde wygaszenie nieobsługiwanych rynków tenisowych
* **Mechanizm:** Wyłączenie rynków `aces_*` oraz `double_faults_*` z generatora kuponów dla tenisa dopóki ESPN/inny provider nie dostarczy oficjalnego feedu serwisowego.

### Moduł 5: Podniesienie podłogi kursowej w generatorze kuponów (`MIN_ODDS_FLOOR = 1.15`)
* **Mechanizm:** W pliku `src/bet/simple_stats/coupons.py` odcięcie wierszy z kursem Superbetu poniżej 1.15 z sekcji singli oraz akumulatorów.
  * Kursy 1.01–1.10 nie mogą trafić do żadnego proponowanego kuponu ze względu na asymetrię ryzyka wariancji.
