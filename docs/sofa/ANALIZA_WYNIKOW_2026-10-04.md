# Analiza wyników 09-19 … 10-03: co działa, co nie działa i co poprawić

Data: 2026-10-04, ok. 09:00Z.
Zakres: wszystkie rozliczone pozycje KUPONU (oficjalny PDF) i WARIANTU z 15 dni, kupony sportów mierzonych, reguła i pomiar.
Szczegółowy raport z samego 10-03, pozycja po pozycji: `reports/sofa_raport_rozliczenia_szczegolowy_2026-10-03.md`.

---

## W jednym akapicie

**Nasze typy wchodzą dokładnie tak często, jak mówi cena Superbetu, a nie tak, jak mówi pewność drukowana w PDF.**
- Przy wyniku równym cenie traci się marżę bukmachera i ona tłumaczy prawie całą stratę.
- KUPON jest w granicach szumu: −0.6%, 95% [−9.4; +8.0].
- WARIANT traci poza szumem: −5.0% [−7.5; −2.6]. Około 80% jego straty (−145.6 z −182.6 j.) pochodzi z nóg z pewnością 0.65–0.70, czyli spod progu kuponu.
- CLV jest ujemny we wszystkich wariantach: kurs zamknięcia przebija tylko 17–18% naszych nóg.
- Żaden filtr zmierzony na tych danych nie daje przewagi nad rynkiem. Najlepsze podzbiory dochodzą do około −1%, czyli tną stratę, ale jej nie odwracają.
- Realny cel na teraz: przestać płacić marżę za nogi wyceniane na stratę, uszczelnić dane i rozliczenia, i dopiero wtedy szukać źródła informacji, którego cena nie zawiera.

---

## 1. Skąd dane i czego ta analiza nie mówi

- **Źródło:** pozycje zebrał `data/analysis_2026-10-04/collect.py` z `08_confidence*.json` każdego dnia i oceniał je tymi samymi funkcjami co rejestr (`settle_multi_coupon`).
  - Zebrano 4105 pozycji (single i buildery). Rozliczonych singli: KUPON 208, WARIANT 3637.
  - Tabele: `data/analysis_2026-10-04/tables.md`.
  - Przedziały 95%: bootstrap po meczach, a nie po nogach, bo nogi jednego meczu wygrywają i przegrywają razem.
- **Dziś uzupełniłem rozliczenia dni 09-23…09-28.** Doszło 1128 wierszy rozliczeń w dniach 09-25, 09-26 i 09-27, dla meczów, których statystyki przyszły po porannym kroku D-5 (szczegóły w punkcie 3.5). Uzupełnienie 09-22 przerwała odmowa Sofascore (punkt 3.10). Wszystkie liczby niżej są po tym uzupełnieniu, a rejestr jest przeliczony (`record_results.py --from 2026-09-19 --to 2026-10-03`).
- **Ograniczenia:**
  - Wszystko jest *w próbie*: progi, które tu wychodzą lepsze, wybrałem, patrząc na wynik. Dlatego przy każdym kandydacie podaję, w ilu dniach efekt się powtórzył. Zanim cokolwiek trafi do kuponu, każdy kandydat wymaga pomiaru *z góry* na nowych dniach (punkt 5).
  - Dni należą do różnych epok: refit 09-26, refit 10-03 i kilkanaście poprawek kodu. Pewność z 09-22 i z 10-03 pochodzi z innych krzywych.
  - Kupon oficjalny ma 208 rozliczonych singli, więc wynik ±9% jest szumem. Tylko WARIANT ma próbę, na której cokolwiek się rozstrzyga.
  - Buildery są oceniane po **szacowanym** kursie (iloczyn nóg × narzut korelacji). Kursu z ekranu Superbetu nie zapisano ani razu (0 z 67).

## 2. Wynik każdego wariantu (rejestr, każdy osobno, nigdy sumowane)

| wariant | dni | rozliczonych | ROI | 95% (po meczach) | CLV (09-26…10-03) | nogi lepsze od zamknięcia |
|---|---|---|---|---|---|---|
| KUPON (oficjalny PDF) | 15 | 262 | **−0.6%** | [−9.4; +8.0] | −4.54% [−5.11; −4.03] | 18% |
| WARIANT | 11 | 3650 | **−5.0%** | [−7.5; −2.6] | −5.58% [−5.75; −5.42] | 17% |
| WSZYSTKIE | 4 | 181 | +0.3% | [−7.3; +7.1] | - | - |
| kupon HOKEJ | 4 | 35 | −11.6% | [−27.3; +1.1] | −2.15% | 12% |
| kupon CS2 | 4 | 39 | −3.2% | [−17.6; +9.1] | −3.45% | 5% |
| kupon KOSZYKÓWKA | 4 | 34 | +1.5% | [−12.3; +12.6] | −2.01% | 38% |
| kupon SIATKÓWKA | 4 | 18 | +10.8% | (<20 meczów) | −4.21% | 18% |
| reguła hokej (bez kuponu) | 5 | 368 | −7.2% | - | - | - |
| reguła koszykówka | 5 | 122 | −7.9% | - | - | - |
| reguła CS2 | 6 | 96 | +0.6% | - | - | - |
| reguła siatkówka | 5 | 137 | +4.8% | - | - | - |

**Jak to czytać:**
- CLV rozstrzyga szybciej niż ROI, bo odpowiada już po kilkudziesięciu nogach.
- Ujemny CLV wszędzie oznacza, że po naszym wyborze cena przesuwa się *przeciwko* nam. Nie kupujemy przed rynkiem, tylko za nim.
- Przy 82–83% nóg gorszych od zamknięcia kurs, który bierzemy, jest systematycznie gorszy od ceny końcowej.

## 3. Co NIE działa: dowody

### 3.1 Pewność z PDF nie jest prawdopodobieństwem. Rzeczywistość równa się cenie

| | rozliczonych | deklarowana pewność | cena rynku (bez marży) | faktycznie weszło |
|---|---|---|---|---|
| KUPON | 208 | 0.771 | 0.704 | 0.745 |
| WARIANT | 3637 | 0.700 | 0.673 | 0.677 |
| 10-03 KUPON | 23 | 0.812 | 0.744 | 0.739 |
| 10-03 WARIANT | 793 | 0.724 | 0.690 | 0.681 |

- **WARIANT trafia dokładnie tyle, ile mówi rynek** (0.677 wobec 0.673). Przy marży około 9–10% daje to około −5%, i tyle właśnie wychodzi.
- **KUPON wypadł o 4 pp lepiej niż rynek** (0.745 wobec 0.704), ale przedział wyniku obejmuje zero.
- **Pewność jest zawyżona o 2–7 pp.** To ten sam wzorzec, który noc 10-03/04 zmierzyła na całej historii: deklarowane 0.805, zrealizowane 0.745, cena 0.742.
- **Przyczyna jest mechaniczna.** Krzywe pewności są fitowane na wszystkich wierszach z odtworzenia historii, a kupon drukuje tylko wiersze, w których model stoi nad ceną. Wybór tych wierszy sam przesuwa trafność w dół do ceny (antyselekcja). Pewność w PDF nie może więc służyć do oceny wartości zakładu.

### 3.2 WARIANT dopuszcza nogi wyceniane na stratę i to jest cała jego strata

| WARIANT | rozl. | trafność | pewność | rynek | ROI | dni gorsze / dni z danymi |
|---|---|---|---|---|---|---|
| pewność 0.65–0.70 | 1893 | 62.0% | 0.658 | 0.632 | **−7.7%** [−10.8; −4.3] | 7/10 |
| pewność ≥ 0.70 | 1744 | 74.0% | 0.744 | 0.718 | −2.1% | |
| model − cena < 0.02 | 1875 | 66.6% | 0.692 | 0.689 | **−8.7%** | 9/11 |
| model − cena ≥ 0.02 | 1762 | 68.9% | 0.708 | 0.656 | −1.1% | |
| pewność ≥ 0.70 **i** model − cena ≥ 0.02 | 926 | 73.4% | 0.753 | 0.701 | **−0.8%** | |

- **Pierwsza przyczyna: progi WARIANTU.** Próg 0.65 i reguła pewność × kurs ≥ 0.90 wprost dopuszczają nogi, które przy cenie rynku mają ujemną wartość. Pewność × kurs ≥ 0.90 oznacza zgodę na 10% poniżej uczciwego kursu.
- **Druga przyczyna: nogi, w których model nie stoi nad ceną.** Prawie połowa nóg WARIANTU ma model co najwyżej 2 pp nad ceną. Takie nogi płacą pełną marżę (−8.7%), a w KUPONIE prawie ich nie ma (4%), bo bramka ujemnej wartości nogi je odcina.
- **Gdyby WARIANT miał próg 0.70 i wymagał co najmniej 2 pp przewagi modelu nad ceną,** na tych samych danych wyszłoby −0.8% zamiast −5.0%. To nadal strata, a próg jest wybrany po fakcie. Kierunek jest jednak spójny dzień po dniu.
- **Uwaga:** kolumna „dni gorsze” dotyczy tylko porównanych grup (gorsza grupa wypadła gorzej w podanej liczbie dni), a nie ROI całego filtra.
- **Dziś zdecydowałeś, że WARIANT zostaje bez zmian.** To są dane na następną decyzję.

### 3.3 Krzywe dla kobiet (i rozgrywek drużynowych w tenisie) przeceniają pewność o 11.5 pp

- 72 nogi WARIANTU z krzywą klasy weszły w 58.3% przy deklarowanych 69.8%. ROI −18.0% [−38.0; +0.6]; gorzej niż reszta w 3 z 3 dni.
- Klasy dostały własne krzywe 09-30 (sprawa Aktobe–Ajax). Te krzywe stoją na małej próbie i wyraźnie zawyżają pewność.
- W KUPONIE była jedna taka noga (wygrana).

### 3.4 Rynki bez własnej krzywej (pula): gole w 1. połowie poniżej

- W KUPONIE 10-03 gole w 1. połowie poniżej weszły 3 z 6 przy deklarowanych 0.819.
- W całym okresie KUPON ma 12 nóg z pewnością z ogólnej puli: 66.7% przy deklarowanych 0.769.
- **Od 10-04 `goals_1h_total|UNDER` jest w `refused_markets`, na twoją decyzję.**
- W WARIANCIE nogi z puli wypadły na poziomie rynku: 0.730 przy cenie 0.727.

### 3.5 Rożne: co piąta noga nie daje się rozliczyć, a proces zgubił 86 nóg

- **Skala:** na 755 nóg na rożne 219 (29%) było nierozliczonych. Po dzisiejszym uzupełnieniu zostało 133 (17.6%): w WARIANCIE 18%, w KUPONIE 14%. Wszystkie inne rynki są poniżej 10%.
- **Przyczyna 1, proces (naprawione doraźnie, nie systemowo):** statystyki niektórych lig dochodzą po kilku dniach. Poranny krok ponownie rozlicza tylko dzień **D-5**.
  - Przykład: Raith Rovers–Livingston (09-25) dostał rożne do bazy 10-03, ale nikt już nie rozliczył 09-25.
  - 85 nóg miało już statystykę w bazie, a dalej figurowało jako nierozliczone. Dziś uzupełniłem dni 09-25…09-27: 1128 wierszy rozliczeń, z czego 86 to wydrukowane nogi na rożne.
- **Przyczyna 2, dane:** część lig nigdy nie dostaje rożnych w Sofascore. Feed ma 0–2 statystyki na mecz: Norwegia 1st Division, polska II liga, chilijska Liga de Ascenso, część niższych lig angielskich.
  - Przed uzupełnieniem w 10 rozgrywkach nie rozliczyła się ani jedna noga na rożne (51 nóg). Po uzupełnieniu zostały 3 takie rozgrywki z co najmniej 2 nogami (22 nogi), a pozostałe około 110 nóg to głównie mecze z ostatnich dni, w których feed ma 0–2 statystyki (część może jeszcze dojść).
  - **Takich nóg nie da się sprawdzić, a mimo to drukujemy je jako typy.**
- **Skutek uboczny:** jeśli rożne brakują nierównomiernie (np. częściej w meczach bez wydarzeń), to rozliczona część jest stronnicza, a z nią krzywa pewności rożnych. To podejrzenie, nie pomiar.

### 3.6 Buildery: nie wiadomo, ile naprawdę dały

- **KUPON:** 54 rozliczone buildery, weszło 36 (66.7%) przy łącznej p 0.698, szacunkowo −3.47 j.
- **WARIANT:** 13 builderów, weszły 4.
- **Kurs z ekranu: 0 z 67.** Superbet nie wycenia buildera jako iloczynu nóg (zmierzony narzut 8.8–19.6%). Wynik w jednostkach jest więc szacunkiem z założonym narzutem 12%, a nie wypłatą.
- **Nogi, które najczęściej kładą buildery:**
  - gole w 1. połowie poniżej: 4 przegrane z 7;
  - gole w 2. połowie poniżej: 3 z 5;
  - rożne drużyny poniżej: 3 z 8;
  - rożne w 1. połowie poniżej: 3 z 11.

### 3.7 Sporty mierzone: cena bez marży to uczciwa cena, więc kupon cenowy traci marżę

- **Pomiar (strona faworyta, wszystkie linie, 5–6 dni):** faworyci wchodzą o 0.5–1.6 pp rzadziej, niż mówi cena (hokej −1.6 pp, koszykówka −1.1, CS2 −0.5). Siatkówka jest wyjątkiem: +2.1 pp.
- **Rodziny, które wyraźnie przegrywają w regule** (cena przed startem, kilkadziesiąt nóg, więc obserwacja, nie dowód):
  - hokej, gole drużyny w tercji: n=70, −15.7%;
  - hokej, total meczu: n=76, −9.1%;
  - koszykówka, 1. połowa remis bez zakładu: n=27, −17.7%;
  - koszykówka, total: n=28, −11.7%.
- **CS2 w pomiarze:** suma rund mapy −7.4 pp (539 stron, ROI −16.8%), rundy łącznie −7.5 pp.
- **Siatkówka:** zwycięzca meczu +4.5 pp (188 stron), reguła +4.8% na 137 nogach. Pięć dni to za mało. Prawie połowa meczów siatkówki nie ma odpowiednika w Sofascore, a 13 nóg z 09-30 i 10-01 nigdy się nie rozliczy.
- **CLV kuponów sportowych** jest ujemny we wszystkich czterech (od −2.0% do −4.2%).

### 3.8 Tenis

- W WARIANCIE: 643 nogi, ROI −5.6% [−10.8; −0.2].
- Najgorsze rynki:
  - gemy wygrane zawodnika powyżej: 267 nóg, −9.5%;
  - gemy w 2. secie poniżej: 28 nóg, −22.6% [−45.7; 0.0].
- Gemy wygrane zawodnika poniżej: −0.1% (200 nóg), czyli na poziomie rynku.
- W KUPONIE tenis prawie nie występuje (5 nóg w całym okresie).

### 3.9 Bramki startu i zegary (naprawione dziś)

- Superbet podaje, że mecz trwa (`metadata.status`, `offerStateId`), i przesuwa godzinę startu. Pipeline tego nie czytał.
- Seggerman–Tajima: w danych 08:00Z, w Superbecie 06:15Z i mecz już trwał.
- **Od 10-04 (commit `ecd109ba`) kursy na żywo są odrzucane, a bramki biorą najwcześniejszy z trzech zegarów.**

### 3.10 Sofascore: czwarta odmowa w historii

- **Kiedy i jak:** 2026-10-04 08:32:32Z, 5 × 403 w jednej chwili, na trasach `/event/{id}`, przy ponownym rozliczaniu 09-22.
- **Tło:** okna przeglądarki działały wtedy od około 4 h, w normalnym tempie.
- **Skutek:** bezpiecznik się otworzył, 09-22 nic nie dopisał (ani nic nie stracił), a kolejne dni przeszły normalnie.
- **Wniosek:** zgodnie z CLAUDE.md to sygnał, żeby zwolnić. Tego dnia nie dokładałem już zapytań do Sofascore.

## 4. Co działa albo nie szkodzi

- **KUPON (próg 0.70, wartość nogi > 0, marża ≤ 10.5%) nie traci poza szumem:** −0.6% [−9.4; +8.0]. Ma wyraźnie lepszą jakość wyboru niż WARIANT. Prawie nie bierze nóg bez przewagi modelu (4%), a pewność ma bliżej rzeczywistości.
- **Rożne i gole poniżej w KUPONIE** są lekko na plusie (+4.3% i +8.4%), ale przedziały obejmują zero. To nie jest dowód przewagi.
- **Kilka nóg z jednego meczu nie szkodzi wynikowi.** Mecze z 3–5 nogami nie wypadły gorzej, za to zwiększają zmienność dnia.
- **Pierwsza dziesiątka listy w KUPONIE: +8.4%** [−2.8; +18.4], a pozycje 21–30: −19.9% [−39.0; +1.5]. Po uzupełnieniu rozliczeń przedział dla 21–30 obejmuje zero, więc to tylko trop: krótsza lista (20 zamiast 30) może tracić mniej. Do pomiaru, nie do wdrożenia.
- **Kartki w WARIANCIE** (85.0% powyżej, 73.1% poniżej) i **gole w 1. połowie powyżej** (+5.9%, 130 nóg) są na plusie. Skaner nisz z korektą na wielokrotne testy (BH) nie znalazł jednak żadnej niszy na 2407 komórkach, więc to szum.

## 5. Co poprawić: rekomendacje w kolejności

Każda rekomendacja ma dowód (punkt 3) i sposób sprawdzenia. Decyzje o profilach i rynkach są twoje; zmiany kodu wymagają testu w `tests/sofa`.

### Twoje decyzje: dane do nich są wyżej

1. **WARIANT: podnieść próg do 0.70 i wymagać co najmniej 2 pp przewagi modelu nad ceną, albo go wyłączyć.**
   - Dowód: punkt 3.2. Na tych danych −5.0% przechodzi w −0.8%; nogi spod 0.70 to 80% straty, gorsze w 7/10 dni.
   - Warunek zysku nadal nie jest spełniony, więc zmiana tylko zmniejsza stratę.
   - Bezpieczniej najpierw mierzyć: dodać ten wariant jako pomiar w rejestrze (np. `rule:wariant_070_gap002`) bez drukowania i patrzeć 7 dni.
2. **Kobiety i tenisowe rozgrywki drużynowe: odmówić nóg z krzywej klasy do następnego refitu albo podnieść dla nich próg.**
   - Dowód: punkt 3.3, deklarowane −11.5 pp, gorzej w 3/3 dni.
   - To decyzja o rynkach w stylu `refused_markets`, ale po klasie.
3. **Buildery: zapisywać kurs z ekranu albo przestać je drukować.** Bez kursu z ekranu wynik builderów jest nieweryfikowalny (punkt 3.6). Najprostsza droga to skill `bet-slip-audit` na zrzucie ekranu przy każdym stawianym builderze.
4. **Hokej, kupon cenowy:** odmówić krótkich UNDER-ów tercji i drużyn (dowód w punkcie 3.7 i w nocnym raporcie `data/night_2026-10-03/shadow/RAPORT.md`). Najpierw jako pomiar.

### Kod: konkretne poprawki

5. **Stałe domykanie luk w rozliczeniach (P1, mały koszt).** Codziennie, bez mostu, dopisywać rozliczenia dla dni D-14…D-2, których brakujące statystyki są już w bazie.
   - Dziś zrobiłem to ręcznie: `run_settle.py --date <d>` dla 09-22…09-28, 1128 wierszy.
   - Trzeba to wpiąć w poranną procedurę albo do `cs2_daily` / `shadow_daily`, z testem.
   - Bez tego rejestr i krzywe stoją na stronniczo niepełnych danych.
6. **Bramka rozliczalności dla rożnych (P1).** Nie drukować nóg na rynek, którego statystyki Sofascore w danych rozgrywkach historycznie nie publikuje (pokrycie `cornerKicks` per `competition_id` z `sofa_event_stats`; próg do zmierzenia, np. < 80%).
   - Usuwa nogi, których nie da się sprawdzić (z tych dni zostało około 130 takich), i czyści dane do krzywych.
   - Jest `scripts/sofa/audit_stat_completeness.py`: zacząć od niego.
7. **Pewność kotwiczona w cenie (P2, przy następnym reficie, nigdy w trakcie dnia).** Druk pewności zawyżonej o 2–7 pp jest mylący, a krzywa fitowana na wierszach bez ceny nie widzi antyselekcji.
   - Wariant do zmierzenia poza próbą: `gap_shrink_k` (zbudowany w nocy 10-03/04, wyłączony) albo pewność = cena + k·(krzywa − cena) z k fitowanym leave-one-day-out na wierszach drukowanych.
   - Kryterium: Brier/log-loss poza próbą lepszy niż sama krzywa.
8. **Krótsza lista singli w KUPONIE (P3, do pomiaru):** 20 zamiast 30 (punkt 4). Mierzyć z góry na nowych dniach, bo w próbie przedział obejmuje zero.

### Czego NIE robić (zmierzone wcześniej, potwierdzone tu)

- **Nie szukać przewagi w doborze lig czy rynków po fakcie.** Strojenie bramek przegrywa poza próbą (22 680 ustawień, nested: −7.35%), a skaner nisz po korekcie nie znalazł niczego.
- **Nie wybierać nóg, w których model mocno odstaje od ceny.** Powyżej około 8–10 pp to zmierzony anty-sygnał, a `MAX_DISAGREEMENT` już ich nie dopuszcza.
- **Nie traktować wyniku dnia jako argumentu.** 10-03 był stratny, 10-02 zyskowny, a oba mieszczą się w szumie.

## 6. Co zrobiono 2026-10-04

- **Kod (commit `ecd109ba`, wypchnięty):**
  - Odczyt startu meczu z Superbetu: kursy na żywo odrzucane, flaga „rozpoczęty”, trzeci zegar.
  - `refused_markets += goals_1h_total|UNDER` (twoja decyzja).
  - 13 testów w `tests/sofa/test_superbet_live_offer_state.py`.
- **Dzień 10-04:** przebudowany, trzy przebiegi weryfikatora, audyty 0 znalezisk.
- **Rozliczenia:** 10-03 rozliczone (nierozliczone tylko luki w statystykach). Uzupełnione 09-25…09-27 (1128 wierszy), `regrade_settled --apply`, rejestr przeliczony za 09-19…10-03.
- **Raporty:**
  - `reports/sofa_raport_rozliczenia_szczegolowy_2026-10-03.md` (każda pozycja 10-03);
  - ten dokument;
  - tabele w `data/analysis_2026-10-04/tables.md`.
- **Nie zrobione:**
  - 09-22 bez uzupełnienia (przerwane przez 403);
  - punkty 1–8 wyżej;
  - piłkarski backfill 730 dni;
  - refit na kopii bazy (brak RAM-u, z nocy).

## 7. Pliki

- `data/analysis_2026-10-04/collect.py`: zbiera pozycje (`positions.jsonl`).
- `data/analysis_2026-10-04/analyze.py`: przekroje (`tables.md`). Uruchomić ponownie po kolejnych dniach, żeby sprawdzić, czy wnioski się trzymają.
- `data/report_2026-10-03/build_report.py`: raport pozycja po pozycji dla dowolnej daty (`--date`).
