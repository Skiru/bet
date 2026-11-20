# Kosz: nowe rynki Superbetu - milestones "N+", double-double i reszta (2026-11-20)

Badanie tylko do odczytu. Baza `data/sofa.db` otwarta `mode=ro`, wyłącznie zapytania po kluczu (`sofa_event_stats`, `sofa_event_detail`, `sofa_listed_event`, `sofa_listing_event`). Nic w repozytorium nie zmienione. Skrypty i wyniki leżą w
`/private/tmp/claude-501/-Users-mkoziol-projects-bet/04c6201e-4497-4273-b02c-92e4cd7d7f51/scratchpad/basketball/`
(skrypty `extract.py`, `step1_shapes.py`, `step3_model.py`, `step3b_dd_history.py`, `step4_measure.py`, `step5_history_ladder.py`, `step5b_history_calib.py`, `step6_checks.py`; logi `out/*.log`).

## Werdykt

**Żaden z nowych rynków nie jest wart wdrożenia do druku.**

- **Milestones "N+"** to ta sama rodzina, którą SHADOW już czyta dwustronnie (N+ = OVER N−0,5). Na wspólnej linii mają tę samą cenę.
  - Model przewiduje je gorzej od ceny: Brier +2,05×10⁻³ [+0,54; +3,52] wobec surowego 1/kurs, a po Platcie obu stron +3,83 [+2,56; +5,06]. W NBA po Platcie +7,07 [+5,47; +8,87].
  - Nogi, które przeszłyby bramki, trafiają 0,804 przy 1/kurs 0,863. ROI −6,8% [−9,4; −4,5], po podatku −18,0%.
  - Rynek jest jednostronny, więc do druku potrzebowałby własnej krzywej historii (n ≥ 300).
- **Double-double (233573)** to najmniej zły kandydat: dwustronny, z marżą 8,6% i rozliczalny z pudełka w 100%.
  - Model (niezależność trzech brzegowych P(≥10)) jest wyraźnie gorszy od ceny: Brier +9,5×10⁻³ [+4,3; +15,3].
  - Strona „Nie” w bramkach daje 33 nogi dziennie, które trafiają 0,859 przy 1/kurs 0,883. ROI −2,9% [−6,6; +0,5], po podatku −14,6%.
  - Dodałby objętość, nie jakość.
- **Pozostałe rynki** odpadają. Sumy statystyk drużyn (231818–231829, 234463) i „Zwycięzca & liczba punktów” (200806) mają 0 stron w strefie. „Wyścig do X” (750, 97 w strefie) i pierwsze punkty wymagają kolejności zdobyczy, której nie przechowujemy.

Jeśli operator mimo to chce jeden rynek, to **double-double**. Szkic wdrożenia jest w sekcji 6.

## 1. Kształt, wolumen, ligi (krok 1)

Źródło: `runs/sofa/<d>/unmapped_prices/basketball_*.jsonl.gz` (11-05..11-21). Dla każdej selekcji brana jest ostatnia notowana cena przed startem. Start pochodzi z `runs/sofa/shadow/basketball/<d>/settled.json` i `snapshots.jsonl` (`extract.py`). Okno to dzień SHADOW 11-06..11-19; selekcje `status: block` (cena 1,00 albo zablokowana) są pominięte. Wychodzi 48 607 aktywnych selekcji (`out/step1.log`).

**Milestones** (strony, mecze; strefa = kurs 1,09–1,43):

| rynek | NBA | Euroliga | inne ligi | strefa (NBA / EL / inne) | progi N w strefie |
|---|---|---|---|---|---|
| 235311 punkty | 5 809 / 97 | 1 590 / 30 | 3 290 / 80 | 1 081 / 289 / 626 | 5, 10, 15 (NBA do 30) |
| 235312 zbiórki | 4 548 / 97 | 1 008 / 30 | 2 690 / 80 | 880 / 166 / 396 | 3, 5 (7, 10) |
| 235313 asysty | 3 131 / 97 | 658 / 30 | 1 725 / 79 | 446 / 69 / 159 | 3, 5 (7) |
| 235314 PRA | 2 896 / 97 | 845 / 30 | 3 813 / 78 | 537 / 170 / 728 | 10, 15, 25 |
| 235315 trójki | 4 986 / 97 | 1 213 / 30 | 2 839 / 78 | 932 / 183 / 434 | 1, 2 |
| 238440/442/444/446 | - | - | 3 846 / 112, 680 / 54, 510 / 56, 169 / 11 | 657 / 151 / 116 / 38 | 5, 10 pkt; 3, 5 zb./as. |

- „Inne ligi” rynków 2353xx to EuroCup, ACB, GBL i Liga Mistrzów.
- Rynki 238440..446 występują w NBL Australia, BNXT, LNB, ABA, BBL, OBL, TBSL i Serie A (`out/extract.log`).
- Dla 238441, 238443 i 238445 nie ma ani jednej notowanej ceny.

**N+ to OVER N−0,5 tej samej rodziny, ta sama cena.** Na 4 172 selekcjach, gdzie ten sam zawodnik ma w tym samym meczu dwustronną linię OVER N−0,5 (`out/twosided.jsonl` z `settled.json`):

- cena milestone równa OVER w 3 543 przypadkach (85%), wyższa w 499, niższa w 130;
- obie ceny pochodzą z tej samej migawki (mediana różnicy czasu 0 min);
- lepsza cena milestone występuje prawie wyłącznie w ACB (mediana +1,05%) i GBL (+0,86%); NBA 47 z 2 294, Euroliga 10 z 581;
- nawet tam 1/kurs milestone leży o ok. 4,4 pp nad ceną bez marży linii dwustronnej (NBA +3,8 pp, Euroliga +4,3, ACB +4,4). Marża jest więc taka sama jak na stronie OVER.

Rozliczenie też jest tożsame: moja ocena „wartość ≥ N” zgadza się z `actual` SHADOW_SETTLE w 33 620 z 33 620 przypadków (`out/step6.log` (b)).

Milestones w strefie to głównie przedłużenie drabinki w dół, a nie te same linie. Spośród 8 058 selekcji w strefie:

- 25 leży na linii dwustronnej;
- 5 779 leży poniżej najniższej linii dwustronnej (3 341 o ≤ 2 jednostki, 1 759 o 2–5, 679 o > 5);
- 2 254 dotyczy zawodnika bez linii dwustronnej w tej rodzinie.

**Double-double:**

- NBA: 617 par Tak/Nie i 321 samych „Tak”. Euroliga: 28 par i 106 „Tak”. Inne ligi: 63 pary i 339 „Tak”.
- Marża par wynosi 0,086 (mediana) i 0,090 (p90).
- Strefa (kurs 1,09–1,43, p bez marży ≥ 0,70): 220 stron „Nie” i 16 stron „Tak” w NBA.
- Triple-double (233574) ma tylko „Tak” (179 w NBA), czyli jest jednostronny.

## 2. Rozliczalność double-double (krok 2)

- Pudełko: `shadow.build_player_box` na `sofa_event_stats.lineups_json` i `sofa_event_detail` (ta sama ścieżka co SHADOW_SETTLE). Wynik: 313 z 319 meczów `ok`, 5 bez pudełka, 1 niezgodne z wynikiem (`out/step3.log`).
- Klucze `points`, `rebounds`, `assists`, `steals`, `blocks` są obecne u każdego grającego. Nie było ani jednego `NO_STAT`.
- Stan rozliczenia selekcji DD: 2 122 ocenione, 59 `UNMATCHED`, 1 DNP (`out/step4.log`).
- Przechwyty i bloki nie dały ani jednego double-double: 0 z 2 122 selekcji.
- Zawodnik nieznaleziony w pudełku jest dopasowywany tymi samymi funkcjami co `shadow.player_value` (match_player, tokeny, nazwisko, `_bare_name`).

## 3. Model (krok 3)

`player_model` (player_rate_v3) daje tylko rozkłady brzegowe: mieszankę NB po minutach (`count_distribution`) dla każdej rodziny z osobna. **Nie ma rozkładu łącznego.**

- **Milestone:** P(X ≥ N) = `line_probability` przy linii N−0,5 OVER. Liczę je tak jak SHADOW: `player_model.forecast_records`, przypięte drużyny z `sport_fixtures.json` (`run_shadow.pinned_teams`), zegar ostatniej notowanej ceny (`step3_model.py`).
  - `player_model.jsonl` ma liczby tylko dla linii dwustronnych. Milestones nie są czytane, więc ich p nie istnieje w artefaktach dnia; przeliczyłem je.
  - Pokrycie: 44 330 z 46 246 selekcji ma p (96%). Bez p: `NOT_IN_HISTORY` 1 027, `THIN_SAMPLE` 453, `NAME_UNCERTAIN` 436.
- **Double-double:** iloczyn niezależnych P(pts ≥ 10), P(reb ≥ 10), P(ast ≥ 10), bez przechwytów i bloków.
- **Błąd niezależności na historii** (`step3b_dd_history.py`): ostatnie 60 meczów drużyn z meczów DD, zawodnicy z ≥ 20 występami, brzegowe z tej samej próby, więc mierzona jest wyłącznie zależność:

| liga | mecze zawodników | DD rzeczywiste | DD przy niezależności |
|---|---|---|---|
| NBA | 17 610 | 0,0712 | 0,0605 |
| Euroliga | 10 683 | 0,0159 | 0,0106 |
| inne | 25 329 | 0,0219 | 0,0161 |

  - Niezależność zaniża DD o około 15–33% względnie, głównie przy niskich p (NBA p_ind 0–0,05: 0,012 wobec 0,020). W paśmie 0,2–0,6 różnica to 1–3 pp (NBA 0,297 / 0,308; 0,439 / 0,465).
  - **Na oferowanych meczach większym błędem jest ściśnięcie brzegowych do puli niż sama niezależność.** Według przedziałów ceny bez marży (de-vig potęgowy): dla 0–0,1 model 0,099, wynik 0,050; dla 0,5–1,0 model 0,536, wynik 0,690.

## 4. Pomiar na ocenionych ofertach 11-06..11-19 (krok 4)

Plik `out/step4.log`. Bootstrap po meczach (2 000 powtórzeń, 95%). Brier i log-loss podane ×10⁻³, wartość dodatnia oznacza, że cena przewiduje lepiej.

### Milestones (jednostronne)

**Metoda.** Rynek jest jednostronny, więc nie da się go odmarżować z pary. Porównuję model z:

- (a) surowym 1/kurs, który zawiera marżę i dlatego jest korzystny dla modelu;
- (b) ceną po Platcie w tej samej próbie, czyli najlepszym, co może dać jakiekolwiek odmarżowanie monotoniczne.

Model porównuję w wersji surowej i po Platcie w tej samej próbie. Próba to 42 822 ocenione selekcje z p w 313 meczach.

| zakres | n | Brier model − 1/kurs | log-loss | po Platcie obu |
|---|---|---|---|---|
| wszystko | 42 822 | **+2,05 [+0,54; +3,52]** | +2,25 [−1,97; +6,14] | **+3,83 [+2,56; +5,06]** |
| NBA | 20 559 | +5,82 [+3,77; +7,94] | +13,0 [+7,0; +19,2] | +7,07 [+5,47; +8,87] |
| Euroliga | 5 053 | −3,80 [−7,31; −0,35] | −13,5 [−22,9; −4,2] | +1,05 [−1,88; +4,06] |
| inne | 17 210 | −0,74 [−3,08; +1,44] | −6,0 [−12,3; +0,1] | +0,95 [−0,83; +2,73] |

- W Eurolidze i innych ligach model wygrywa tylko z surowym kursem, czyli z marżą. Po Platcie jest remis.
- W NBA (połowa wolumenu) model jest gorszy.
- Po rodzinach, wobec surowego kursu: PRA +4,61 [+1,74; +7,51], asysty +3,49, punkty +1,36, trójki +2,09, zbiórki 0,00.

**Kalibracja modelu** (surowe p; model zaniża):

| pasmo p | n | deklarowane | trafione | 1/kurs | trafione − deklarowane |
|---|---|---|---|---|---|
| 0,60–0,70 | 3 600 | 0,648 | 0,688 | 0,760 | +4,0 pp [+2,3; +5,6] |
| 0,70–0,80 | 3 070 | 0,749 | 0,795 | 0,857 | +4,6 [+2,8; +6,3] |
| 0,80–0,92 | 2 441 | 0,847 | 0,867 | 0,931 | +2,0 [+0,3; +3,5] |

Cena zawyża p o 6–8 pp: dla 1/kurs 0,80–0,92 trafia 0,783 przy 0,860. Model zaniża o 2–4,6 pp. Według lig (0,70–0,92): NBA +3,8 pp [+2,2; +5,5], Euroliga +1,3 [−3,7; +6,0], inne +3,3 [+1,0; +5,5].

Na historii, wśród wszystkich zawodników, kalibracja jest dobra (zob. „Krzywa z historii”). Na oferowanych zawodnikach model zaniża. To efekt doboru: Superbet wystawia milestones zawodnikom rotacji, których pula ściąga w dół. To hipoteza, niezmierzona.

**Bramki** (pewność = surowe p modelu, bez krzywej i bez dowodów linii; p ≥ 0,70 i p × kurs ≥ 0,90):

- 2 491 nóg w 14 dniach (178 dziennie), trafione 0,804 przy p 0,817 i 1/kurs 0,863.
- **ROI −6,83% [−9,44; −4,45], po podatku 12% −18,0% [−20,3; −15,9].**
- Według lig: NBA −7,3%, Euroliga −11,1%, inne −4,5%.
- Połowy okna: 11-06..12 −8,5%, 11-13..19 −5,1%.
- Z pewnością po Platcie (optymistycznie) jest 346 nóg dziennie i ROI −7,2%.
- Cała strefa 1,09–1,43 (7 499 stron): trafione 0,742 przy 1/kurs 0,813, ROI −8,8%. Każdy próg w strefie daje wynik ujemny, od −1,8% (punkty 20+, n 107) do −13,3% (PRA 10+).

**Krzywa z historii** (`step5_history_ladder.py`, `out/step5b.log`): powtórka bez cen na 250 meczach drużyn NBA i Euroligi z 10-10..11-05, czyli przed oknem. Liczone dla wszystkich grających i progów drabinki Superbetu, ścieżką settle (id z pudełka, próbka ucięta przed meczem).

- 108 936 wierszy.
- Kalibracja: 0,70–0,80 deklarowane 0,750, trafione 0,759 (+0,9 [−0,8; +2,5]); 0,80–0,92 +0,8 [−0,5; +2,0].
- Wierszy z p ≥ 0,70 na rodzinę: punkty 3 537, PRA 3 829, zbiórki 1 697, trójki 1 460, asysty 651.
- **Krzywa „market:” z n ≥ 300 jest więc łatwa do osiągnięcia** już z 250 meczów (pełna powtórka z 10-26 ma 770 944 mecze zawodników).
- Krzywa z całej populacji nie oddaje jednak doboru zawodników z oferty, a offset dowodów linii nigdy nie podnosi pewności.

### Double-double (dwustronne)

688 par ocenionych i wycenionych przez model w 143 meczach (NBA 603, inne 58, Euroliga 27). Stawka DD w próbie: 0,190; model 0,194; cena bez marży (proporcjonalnie) 0,234, potęgowo 0,193.

| porównanie | Brier ×10⁻³ | log-loss ×10⁻³ |
|---|---|---|
| model − cena bez marży, proporcjonalnie | **+9,47 [+4,31; +15,32]** | +24,9 [+9,1; +42,5] |
| model − cena bez marży, potęgowo | +12,32 [+7,33; +18,13] | - |
| po Platcie obu w tej samej próbie | +12,56 [+7,28; +18,56] | - |

Cena odmarżowana potęgowo jest dobrze skalibrowana. Według jej przedziałów (cena / wynik): 0,050 / 0,050, 0,177 / 0,170, 0,373 / 0,347, 0,647 / 0,690.

**Kalibracja strony „Nie”** (pewność = 1 − p_ind):

| pasmo pewności | n | deklarowane | trafione |
|---|---|---|---|
| 0,60–0,70 | 52 | 0,659 | 0,577 |
| 0,70–0,80 | 118 | 0,763 | 0,805 |
| 0,80–0,92 | 326 | 0,864 | 0,877 |
| 0,92–1,0 | 124 | 0,947 | 0,927 |

**Bramki dla „Nie”** (pewność ≥ 0,70, × kurs ≥ 0,90, marża ≤ 15%):

- 467 nóg w 14 dniach, czyli 33 dziennie. Trafione 0,859 przy pewności 0,872, cenie bez marży 0,813 i 1/kurs 0,883.
- **ROI −2,91% [−6,64; +0,49], po podatku −14,6% [−17,9; −11,6].**
- Połowy okna: −3,2% i −2,7%.
- NBA: 384 nogi, trafione 0,844 przy 1/kurs 0,873.

**Pozostałe przekroje DD:**

- „Tak” w bramkach: 6 nóg w 14 dniach.
- Cała strona „Tak”: ROI −37,0% (wysoka marża na długim kursie).
- Cała strona „Nie”: −4,1% [−8,1; −0,2].

## 5. Kontrole adwersarialne (każda liczba drugi raz)

Wyniki w `out/step6.log`.

- (a) Moje przeliczone p kontra p przed meczem zapisane przez SHADOW, ta sama linia: 4 005 par, 3 215 dokładnie równych, mediana |d| 0,0000, p95 0,024. Różnice wynikają z późniejszego zegara notowania i nowszych list meczów.
- (b) Moja ocena kontra `actual` z SHADOW_SETTLE: 33 620 / 33 620 zgodnych.
- (c) Brier model − 1/kurs dla milestones policzony od nowa z `scored.jsonl` zwykłymi sumami: +2,05 na 42 822 (tak samo jak w kroku 4).
- (d) Bramka milestones policzona inną drogą: 2 491 nóg, 2 003 wygrane, wynik −170,08 j. = −6,83% (tak samo).
- (e) Bramka DD „Nie” policzona od nowa z `scored.jsonl` (P(≥ 2 z 3) przez wyliczenie 8 przypadków zamiast wzoru zamkniętego): 467 nóg, 401 wygranych, −2,91% (tak samo).
- Strefa pozostałych rynków policzona ponownie z plików `unmapped_prices` (ostatnia aktywna cena, odmarżowanie po grupie): 750 → 97 stron (brief podawał 98), 200806 → 0, 231818–231829 → 0, 234463 → 0.

## 6. Szkic wdrożenia double-double (jeśli operator mimo werdyktu chce)

**Nie zalecam.** Szkic na wypadek decyzji „tak”:

1. **Przełącznik.** `epochs.BASKETBALL_DOUBLE_DOUBLE_FROM_UTC` od następnego dnia 00:00Z, czytany jak `basketball_player_v2`: po dniu rekordu i zegarze. Przy wyłączonym przełączniku migawka ma być identyczna bajt w bajt. Migawki i nogi niosą `double_double_rule`.
2. **`shadow.py`.**
   - Nowa `PlayerSpec` 233573 `player_double_double`, strony YES/NO z „Tak” / „Nie”, kształt dwustronny.
   - `PlayerSpec` dostaje tryb łączenia (`sum` lub `double_double`), a `player_stat_value` zwraca 0/1: ≥ 2 z {pts, reb, ast, stl, blk} ≥ 10.
   - Brak klucza → `NO_STAT`, nieobecność → DNP (Superbet unieważnia).
   - Grading przez `grade_side` na wskaźniku.
   - Triple-double (233574) zostaje poza zakresem: jednostronny.
3. **`player_model.py`.** Funkcja `double_double_probability` liczy rozkłady pts / reb / ast (+ stl / blk) w każdym węźle Gaussa-Hermite'a minut (wspólne minuty = główne źródło korelacji), P(≥ 2) w węźle i średnią po węzłach.
   - Zanim to wejdzie, trzeba zmierzyć na historii wobec niezależności i wobec ceny.
   - Ściśnięcie do puli (sekcja 3) jest większym problemem niż korelacja. Bez poprawy brzegowych zysk będzie mały.
4. **`sport_confidence.py` i dowody linii.** Klucz `basketball|player_double_double|YES/NO` bez krzywej czyta własne rozliczone linie (Wilson / deff). Daje to `NO_LINE_EVIDENCE`, dopóki kubełek nie ma 50 linii i 15 meczów. Przy ok. 49 parach dziennie zajmie to około 1–2 tygodni. Alternatywą jest krzywa z powtórki `fit_player_model.py` (rodzina z łączeniem DD) i rejestr `T-BB-DOUBLE-DOUBLE-calibration`.
5. **`leg_relations`.** DD jest ZALEŻNE od pts / reb / ast tego samego zawodnika: nie może wejść do buildera razem z nimi. `SAME_EVENT_DEDUP` się nie zmienia (DD nie jest tym samym zdarzeniem co żadna noga).
6. **Testy** w `tests/sofa/test_basketball_double_double.py`:
   - parsowanie;
   - ocena: DD z przechwytów i bloków, DNP, brak klucza;
   - wyłączony przełącznik identyczny bajt w bajt;
   - model monotoniczny, a wynik łączny ≥ niezależnemu przy dodatniej korelacji;
   - wpis w `config/sofa_test_registry.json`, `check_test_registry.py`.
7. **Nakład:** około 1–1,5 dnia kodu i testów plus pół dnia pomiaru modelu łącznego. Grupa epoki w księdze tylko wtedy, gdy coś drukuje.

Gdyby operator chciał milestones zamiast DD:

- mapowanie 2353xx / 2384xx na istniejące rodziny przy linii N−0,5 OVER, oznaczone `one_sided_market`;
- własna krzywa historii („market:” z n ≥ 300) z powtórki;
- rozszerzenie `SAME_EVENT_DEDUP` (N+ = OVER N−0,5 tej samej rodziny, ta sama cena w 85%) oraz relacja w `leg_relations`.

To 2–3 dni. Na wyniku ROI −6,8% przed podatkiem i z modelem gorszym od ceny w NBA - nie.

## 7. Ryzyka i rzeczy niesprawdzone

- **Krótkie okno.** 14 dni, 313 meczów z milestones i 143 z wycenionymi parami DD (NBA 603 z 688). Przedziały są szerokie, a wynik DD zależy prawie wyłącznie od NBA.
- **p przeliczone dziś, z bazy w obecnym stanie.** Historia jest ucięta przed startem, ale listy meczów i lineupy pobrane po notowaniu mogą się różnić od tego, co SHADOW widział rano. Kontrola (a): 80% dokładnie równych, p95 |d| 0,024.
- **Cena to ostatnie notowanie przed startem**, a nie cena z chwili druku. Pierwsza cena jest zapisana w `candidates.jsonl`, ale jej nie analizowałem.
- **Brak prawdziwej ceny bez marży dla rynku jednostronnego.** Podaję surowe 1/kurs i Platta. Proporcjonalne odmarżowanie milestones (≈ −4 pp z porównania z parą) nie jest użyte w liczbach Briera.
- **Symulacja bramek jest uproszczona.** Pomija offset i limit pasma dowodów linii, świeżość ceny, start, `SAME_EVENT_DEDUP`, odczyty analityków i regułę jednostronną (dla milestones dziś nic by nie przeszło: pewność z dowodów linii to nie „market:”).
- **Powtórka historii tylko na 250 meczach** (NBA i Euroliga, 10-10..11-05) i wszystkich grających, a nie na zawodnikach z oferty. Pełnej powtórki `fit_player_model.py` nie uruchamiałem z powodu limitu pamięci.
- **Niezależność DD mierzona na brzegowych z tej samej próby**, czyli jest to górna granica samego błędu zależności. Model łączny po minutach nie był zbudowany ani zmierzony.
- **1 653 milestones (3,6%) z oceną `UNMATCHED`.** To prawdopodobnie zawodnicy nieobecni w pudełku, czyli unieważnieni przez Superbet. Nie sprawdzałem ich po kolei.
- **Regulaminu Superbetu dla DD nie czytałem.** Założyłem standard: 2 z pts / reb / ast / stl / blk ≥ 10, z dogrywką.
- **Podatek** liczony jako wypłata × 0,88.
- **Rynek 238440..446** występuje w innych ligach. Model (pula, ligi) jest tam słabiej sprawdzony; NBL Australia dominuje.
