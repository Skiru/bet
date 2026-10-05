# Plan: sofa „production grade” (2026-10-05)

Odpowiedź na pytanie operatora z 2026-10-05: „czy pipeline jest w 100%
production grade - wszystkie statystyki każdego sportu, skalibrowane modele,
kontekst wydarzeń, wybór najlepszych rynków, nic nie pomija, tautologie?”

**Nie.** Poniżej: co dokładnie nie jest spełnione (z liczbą i źródłem), plan
dojścia z mierzalnym kryterium zakończenia każdej fazy, i czego żaden plan
nie może obiecać.

## 0. Dwie różne rzeczy pod jednym słowem

1. **Poprawność i niezawodność (A).** Potok robi to, co deklaruje, codziennie,
   bez ręcznego ratowania, i nie gubi niczego po cichu. To jest inżynieria -
   da się to zbudować i sprawdzić testem.
2. **Przewaga nad ceną (B).** Kupon zarabia albo bije cenę zamknięcia. Tego nie
   da się zbudować dekretem - da się to tylko **zmierzyć**. Dziś pomiar mówi,
   że przewagi nie ma (sekcja 1, wiersz „przewaga”).

„Production grade” w tym planie = A spełnione w całości **i** B rozstrzygnięte
uczciwym pomiarem z góry zapisanym (sekcja 3, F5). Wynik „przewagi nie ma” też
jest rozstrzygnięciem.

## 1. Stan na 2026-10-05 - wymaganie po wymaganiu

| wymaganie | stan | dowód |
|---|---|---|
| wszystkie statystyki każdego sportu | **nie** | OFFER 10-05: 17 166 rynków Superbetu niezmapowanych (`total_unmapped`); CONFIDENCE 10-05: `TENNIS_SET_MARKET_NOT_ADMITTED` 1 158, `DERIVED_NOT_CALIBRATABLE` 888, `NOT_CALIBRATED` 405; koszykówka i CS2 `NOT_CALIBRATED` (0 nóg), siatkówka 0 zidentyfikowanych meczów; 6 sportów, inne nieobjęte |
| skalibrowane modele | **niepotwierdzone** | epoka stats-only ma pół dnia - zgodność drukowanej pewności z realizacją **nie jest zmierzona**; przed nią: pewność 0,805 vs realizacja 0,745 vs cena 0,742; krzywe klas (kobiety, puchar drużynowy) -11,5 pp; `UNFITTED_CONSTANTS` (14 pozycji, m.in. `K_PRICE`, `MAX_LADDER_SIGMA`) na każdym wierszu; sporty: dopuszczone tylko 3 klucze hokeja i 2 siatkówki (`RAPORT_KALIBRACJA_SPORTOW_2026-10-05.md`) |
| kontekst wydarzeń | **częściowo, ręcznie** | kod zna: ligę, rundę, `MAKEUP_FIXTURE` / `LONG_LAYOFF` / `CONGESTED` (pokazywane, nie bramka), towarzyskie, klasy; nie zna: składów, nieobecności, sędziego, stawki meczu, pogody - to czyta analityk, i tylko pierwsze 30 pozycji + buildery (10-05: 32 nogi z 157) |
| wybór najlepszych rynków | **nie** | kolejność = pewność; nie ma reguły wyboru rynku, która bije marżę poza próbą (sweep 22 680 ustawień; skaner nisz 0/1 506 po BH; selekcja lig -21..-33%) |
| nic nie pomija | **nie** | 10-05: 12 nóg tenisa wypadło z rekordu wydruku przez nadpisanie `12_printed.json` (odtworzone ręcznie); FIXTURE_CHECK pytał tylko o mecze z 11; K14 łapie przerwany mecz dopiero po pierwszym wydruku (RESOLVE nie zapisuje statusu); rożne: 29% wydrukowanych nóg bez rozliczenia (analiza 10-04) |
| tautologie / zależności między nogami | **nie** | 10-05: 39 drabin z >= 2 szczeblami (98 nóg z 157), 20 par OVER + UNDER tej samej wielkości jednego meczu, pozycje 1-30 na **4** meczach; brak silnika relacji (implikacja U2.5 => U3.5, total vs suma drużyn, połowa vs mecz) |
| przewaga | **nie ma** | CLV official 09-19..10-04: **-4,32% [-4,71; -3,93]**, 86 nóg, 19% bije zamknięcie; ROI official -0,8% [-9,1; +7,7] (294 rozliczone - szum); 3% przewagi wymaga ~4 400 pozycji |
| niezawodność operacyjna | **nie** | 10-05: dwie przebudowy na nieświeżych cenach (STALE_PRICE wyczyścił 08 do nóg w grze; SHADOW z horyzontem 3 h pominął hokej o 15:30Z), trzy poprawki kodu w trakcie dnia; testy chaosu (403, bezpiecznik, wznowienie) nigdy nie uruchomione celowo; 90 błędów ruff |

## 2. Zasady planu

- **Każda faza ma kryterium zakończenia w liczbach.** „Zrobione” = kryterium
  spełnione na danych, nie „kod napisany”.
- **Mierz zanim użyjesz.** Każda nowa cecha / krzywa / reguła wchodzi tylko po
  teście poza próbą z przedziałem (jak `measure_schedule_context`: nadrobiony
  mecz zmierzony bez efektu - pokazywany, nie bramka).
- **Nigdy w trakcie dnia.** Refity i zmiany reguły między dniami, z backupem i
  raportem porównania (`prepare_refit.py`), jak dotąd.
- **Epoki osobno.** Każda zmiana reguły = nowa epoka w ledgerze, nigdy sumowana.

## 3. Fazy

### F0 - Poprawność i nic po cichu (najpierw; inżynieria)

| # | zadanie | kryterium zakończenia |
|---|---|---|
| F0.1 | Rekord wydruku tylko dopisywany: `12_printed.json` -> historia renderów (`printed/<ts>.json`), blokada czyta pierwszy wydruk nogi | test: noga z wcześniejszego renderu przeżywa dowolną liczbę przebudów; zero nóg w `printed_after_start` bez wpisu w historii |
| F0.2 | Jedno polecenie przebudowy we właściwej kolejności (OFFER jeśli > 45 min, SHADOW z horyzontem do najdalszego startu jeśli > 3 h, FIXTURE_CHECK, CONFIDENCE, SPORT_CONFIDENCE, COUPON_ASSEMBLY, PDF, audyty); `/sofa-verify` i `/sofa-rebuild` wołają tylko je | test: przebudowa na starej ofercie odświeża ją zamiast oddawać pusty kupon |
| F0.3 | Faktyczny start w tenisie z `time.currentPeriodStartTimestamp` (Sofascore), nie z `startTimestamp` planu gier | 10-05 odtworzone: Grenier 09:40:52, Tarvet ~09:14 - zgodnie z pomiarem |
| F0.4 | Status meczu przed pierwszym wydrukiem: FIXTURE_CHECK (lub RESOLVE) dla każdego meczu z nogą przechodzącą bramki, nie tylko wydrukowanych | test: mecz `interrupted` nie trafia na pierwszy wydruk |
| F0.5 | PDF mówi prawdziwy powód UNVERIFIED (404 != „brak mostka”) | test |
| F0.6 | Rożne i późne statystyki: codzienne D-14..D-2 dorozliczenie z cache + bramka rozliczalności per rozgrywki | odsetek wydrukowanych nóg bez rozliczenia po D+3 < 2% przez 7 dni |
| F0.7 | 90 błędów ruff do zera; test niestabilny (raz widziany) zidentyfikowany | `ruff check` czysto w CI |

### F1 - Pokrycie: wszystkie rynki, które da się policzyć

| # | zadanie | kryterium zakończenia |
|---|---|---|
| F1.1 | Klasyfikacja 17 166 niezmapowanych rynków: (a) mamy statystykę - zmapować, (b) da się policzyć z historii, (c) nie da się (np. brak źródła) - lista z powodem | każdy rynek Superbetu dnia ma jedną z trzech etykiet; raport dzienny |
| F1.2 | Tożsamość sportów (SPORT_IDENTITY): 10-05 hokej 9/14, koszykówka 8/19, siatkówka 0/3, CS2 12/28 (16 `DUPLICATE_SUPERBET_TEAM`) | >= 95% meczów na tablicy zidentyfikowanych, 0 błędnych w złotym zbiorze >= 50 meczów na sport |
| F1.3 | Rynki tenisa zablokowane regułą (`TENNIS_SET_MARKET_NOT_ADMITTED`) i pochodne bez kalibracji: dla każdej rodziny - zmierzyć albo udokumentować, dlaczego nie | lista rodzin z decyzją i pomiarem |
| F1.4 | Statystyki Sofascore, których nie czytamy (per sport inwentarz endpointów vs. `metrics.py`) | inwentarz; każda pozycja: używana / zmierzona-bez-zysku / do zrobienia |
| F1.5 | Nowe sporty tylko z realnym źródłem statystyk i rozliczenia (bez symulacji: Superbet 190, 75, 157, 70 zostają poza) | decyzja operatora per sport po F1.1 |

### F2 - Kalibracja: pewność = częstość

| # | zadanie | kryterium zakończenia |
|---|---|---|
| F2.1 | Pomiar epoki stats-only: drukowana pewność vs realizacja, per krzywa (`calibrated_on`), per sport, bootstrap po meczu | dla każdej krzywej z >= 300 rozliczonymi nogami: |pewność - realizacja| <= 2 pp i przedział zawiera 0; krzywa, która nie przechodzi, przestaje drukować |
| F2.2 | Odłożone defekty modelu przed następnym refitem (`open-defects-2026-09-25`): wariancja NB przy przesuniętym środku (F2), awans / spadek w próbie (F5), kartki trenerów | każdy naprawiony z testem albo zmierzony jako bez wpływu |
| F2.3 | `UNFITTED_CONSTANTS` (14): każda stała dopasowana na historii z plateau albo usunięta z modelu | lista pusta - dopiero wtedy wolno zdjąć znacznik |
| F2.4 | Krzywe klas (kobiety, puchar drużynowy; -11,5 pp): refit na własnej klasie albo odmowa | jak F2.1 |
| F2.5 | Sporty: koszykówka i CS2 bez dopuszczonych kluczy; hokej / siatkówka po 2-3 klucze | klucz drukuje dopiero po kryterium F2.1 na liniach Superbetu (nie tylko historii) |

### F3 - Kontekst: z ręki analityka do zmierzonej cechy

| # | zadanie | kryterium zakończenia |
|---|---|---|
| F3.1 | Składy i nieobecności (Sofascore `/lineups` przed meczem, `missingPlayers`): kiedy są dostępne (sonda: 9 h przed - brak; zmierzyć 1-3 h) | tabela dostępności per liga / sport |
| F3.2 | Każda cecha kontekstu (skład, sędzia, stawka / runda, odpoczynek, pogoda dla piłki) jako osobny pomiar log-loss poza próbą | cecha wchodzi do modelu tylko z przedziałem poprawy < 0; inaczej zostaje notatką na PDF |
| F3.3 | Analitycy na wszystkich nogach, nie tylko 30 - albo uzasadnienie limitu kosztem | decyzja operatora (koszt: czas sieci + tokeny) |

### F4 - Zależności między nogami (tautologie) i ekspozycja

| # | zadanie | kryterium zakończenia |
|---|---|---|
| F4.1 | Silnik relacji nóg jednego meczu: implikacja (U2.5 => U3.5, O2.5 => O1.5), wykluczenie, zależność (total vs suma drużyn, połowa vs mecz, rożne vs strzały) | test na wszystkich parach rynków z mapy; każda para nóg na kuponie ma etykietę relacji |
| F4.2 | Drabina = jedna decyzja: na PDF jedna noga na wielkość (najwyższe x) albo grupa wyraźnie opisana „ta sama zmienna” | 0 drabin drukowanych jako niezależne pozycje bez opisu |
| F4.3 | Ekspozycja per mecz: ile pozycji i jaka część pewności siedzi na jednym meczu (10-05: 1-30 na 4 meczach) | raport na PDF; limit - decyzja operatora |
| F4.4 | Buildery: cena tylko z ekranu Superbetu (0/67 z ceną ekranu do 10-04) | każdy builder na kuponie ma zapisany kurs ekranu albo nie drukuje się |

### F5 - Przewaga: rozstrzygnięcie zamiast nadziei

| # | zadanie | kryterium zakończenia |
|---|---|---|
| F5.1 | Rejestr testów z góry (hipoteza, reguła, liczba nóg, kryterium stopu) zanim cokolwiek zostanie „wybrane”: kandydaci z pomiarów - football `goals_total` (b 0,50 [0,26; 0,75]), totale hokeja (b 0,98), boosty jako osobna pula | plik rejestru w repo; żadna reguła nie jest oceniana na danych, na których powstała |
| F5.2 | CLV każdego dnia (pętla `capture_closing`) - brakujące dni 09-19..09-27 to dziura, nie zero | 100% dni z `closing.jsonl` |
| F5.3 | Kryterium przewagi kuponu | CLV: dolna granica 95% > 0 na >= 300 nogach / >= 100 meczach **albo** ROI: dolna granica > 0 na ~4 400 pozycjach (przy ~150 pozycjach dziennie ~30 dni) |
| F5.4 | Kryterium porażki, zapisane teraz | jeśli po F2 i F5.3 CLV zostaje < 0 z przedziałem: wniosek „brak przewagi”, kupon pozostaje narzędziem informacyjnym, nie zakładem |

### F6 - Operacje

| # | zadanie | kryterium zakończenia |
|---|---|---|
| F6.1 | Testy chaosu celowo: 403, bezpiecznik, wznowienie każdego backfillu, brak mostka w trakcie dnia | każda ścieżka odpaliła w teście integracyjnym i zachowała się zgodnie z kontraktem |
| F6.2 | Monitoring dnia: wiek oferty, wiek migawek sportów, pętle (CS2 / SHADOW / CLV), mostek, zgodność ledgera - jeden raport statusu | raport w każdym przebiegu `/sofa-day` |
| F6.3 | Kolejne dni bez ręcznej interwencji (mostek, pętla, przebudowa w złej kolejności) | 7 kolejnych dni |

## 4. Kolejność

F0 -> F1.2 + F2.1 (pomiar, nie zmiana) -> F4 -> F2.2-F2.5 (refit, między dniami) ->
F1.1 / F1.3 / F1.4 -> F3 -> F5 trwa od pierwszego dnia (CLV, rejestr) i
rozstrzyga na końcu. F6 równolegle.

Uzasadnienie: bez F0 każdy pomiar dalej jest na danych z dziurami; F2.1 mówi,
czy epoka stats-only w ogóle drukuje prawdę, zanim coś do niej dołożymy; F4
nie zmienia modelu, a od razu zmienia to, co operator widzi na kuponie.

## 5. Decyzje operatora (nie kodu)

1. Limit ekspozycji na mecz (F4.3) i forma drabiny na PDF (F4.2).
2. Czy analitycy czytają wszystkie nogi (F3.3) - koszt.
3. Propsy zawodników: dopuszczone wbrew pomiarowi (ślepo -45,8% [-50,9; -40,0]);
   ponowne dopuszczenie tylko po kryterium F2.1 na liniach Superbetu.
4. Nowe sporty (F1.5).
5. Kryterium porażki F5.4 - zatwierdzić teraz, przed wynikami.

## 6. Czego plan nie obiecuje

- **Zysku.** Wszystko, co do 10-04 zmierzono, sprowadza się do ceny: trafienia
  = cena, strata = marża, CLV = -marża. Plan daje uczciwe rozstrzygnięcie, nie
  przewagę.
- **„100%”.** Statystyki istnieją tylko dla części rynków; składy bywają
  niedostępne przed meczem; tenis ITF nie ma zewnętrznego źródła prawdy.
  Celem jest: każdy rynek ma etykietę (liczymy / nie da się i dlaczego) i nic
  nie znika bez śladu.
- **Stałości.** Każdy refit to nowa epoka; wyniki epok się nie sumują.

## 7. Stan wdrożenia (2026-10-05, ~12:30Z)

„Zrobione” znaczy: kryterium spełnione na danych. „Zbudowane” znaczy: kod i
test są, ale kryterium wymaga dni, decyzji operatora albo refitu.

| # | stan | dowód / liczba |
|---|---|---|
| F0.1 | **spełnione** | `printed/<ts>.json` tylko dopisywane; blokada czyta pierwszy wydruk; test: noga przeżywa 4 przebudowy bez niej; 10-05 zasiane z `12_printed.json` (md5 identyczne). 12 nóg sprzed tej zmiany nie do odzyskania z rekordu |
| F0.2 | **spełnione** | `rebuild_day.py`; test „stara oferta -> OFFER przed CONFIDENCE”; na żywo 10-05 11:43Z odświeżył ofertę (46 min) i SHADOW z horyzontem 12,25 h (26 meczów poza 3 h) |
| F0.3 | **spełnione** | `real_start_utc` z `currentPeriodStartTimestamp` - okresy; Grenier 09:40:52Z, Tarvet 09:14:04Z (z płatnych danych w DB) |
| F0.4 | **spełnione** | FIXTURE_CHECK pyta też kandydatów (10-05: 135 meczów zamiast 102); test: mecz `interrupted` nie trafia na pierwszy wydruk; na żywo El Porvenir - Cañuelas odrzucony |
| F0.5 | **spełnione** | powód UNVERIFIED (NOT_FOUND / PROVIDER_REFUSED / NO_BRIDGE ...); PDF 10-05: „Sofascore nie zna meczu (404): 2” |
| F0.6 | zbudowane, **nie spełnione** | baza: 9,6% wydrukowanych nóg bez rozliczenia po D+3 (225/2 344, 09-25..10-01); rożne 40,3%; codzienny `resettle_sweep.py` D-14..D-2; bramka NOT_SETTLEABLE (6 komórek rożnych) od 10-06; poza próbą 10,2% -> 5,4%. Kryterium 7 dni najwcześniej ~10-13. **Pierwszy przebieg na żywo 10-05 ~12:50Z** (09-21..10-03): +1 128 rozliczonych wierszy, regrade 512 wartości / 80 odwróconych wyników (72 w wierszach kalibracji cache); wydrukowane nogi do rozliczenia: 10-03 84 -> 23, 10-02 20 -> 4, 09-29 3 -> 1, 09-22/26/27 bez zmian (statystyk nadal brak); ledger przeliczony 09-27..10-04, MISMATCH 0 |
| F0.7 | **spełnione** | ruff 90 -> 0; test niestabilny nie powtórzył się w 8 przebiegach (w tym 3 tasowane) - nazwa nieznana |
| F1.1 | **spełnione** (10-05) | 0 UNCLASSIFIED na 18 214 nazwach (27 757 wystąpień): MAPPABLE 239, COMPUTABLE 14 161, NOT_COMPUTABLE 3 814; `docs/sofa/evidence/market_coverage_2026-10-05.md`. Mapowanie propozycji MAPPABLE - decyzja (zmienia kupon) |
| F1.2 | zbudowane, **nie spełnione** | replay 09-28..10-04: hokej 98,8%, kosz 96,7%, siatka 94,3%, CS2 95,9% meczów, które Sofascore zna; jako odsetek tablicy 97,2 / 90,2 / 51,6 / 55,3%. 0 błędnych id; złote zbiory po 120 przypadków. Blokuje: mecze, których Sofascore nie ma (pętle CS2 1x1), drużyny bez id w cache |
| F1.3 | **spełnione** | `blocked_families_2026-10-05.md`: każda rodzina z decyzją i pomiarem; pochodne zawyżają (both_over_goals -10,6 pp, handicap_games -11,8 pp) |
| F1.4 | **spełnione** | `sofascore_stat_inventory_2026-10-05.md`; hokej/kosz/siatka `/statistics` w cache, nieczytane |
| F1.5 | decyzja operatora | sekcja w raporcie pokrycia |
| F2.1 | zbudowane, **nierozstrzygnięte** | `measure_calibration.py`; epoka stats-only: 0 rozliczonych -> INSUFFICIENT; stara epoka official 294 nogi, +2,9 pp [-2,9; +8,5]. Bramka „krzywa nie przechodzi -> nie drukuje” wyłączona (`CURVE_STATUS_FROM_UTC = None`) |
| F2.2 | zmierzone, za flagą | `model_defects_2026-10-05.md`: wariancja NB tenisa (aces_for -0,0139 [-0,0150; -0,0130]) za `MODEL_FIXES_FROM_UTC = None`; NB piłki i kartki trenerów naprawione wcześniej; awans/spadek - sama notatka |
| F2.3 | **nie spełnione** | 14 stałych opisanych, plan dopasowania; nic nie dopasowano (refit między dniami) |
| F2.4, F2.5 | **nie spełnione** | czekają na rozliczone dni epoki i refit |
| F3.1 | w pomiarze | cache nie odpowie (wszystkie 51 598 składów pobrane po meczu); sonda `probe_lineup_availability.py` uruchomiona 10-05 ~12:55Z (11 meczów: skład potwierdzony w 3, wszystkie 0-2 h przed startem; 0 w 2-3 h) i w pętli co 30 min do 23:00Z (`runs/sofa/2026-10-05/lineup_probe.jsonl`, `--summary`); tabela per liga wymaga kilku dni |
| F3.2 | zmierzone | runda sezonu poprawia (goals_total -0,00173 [-0,00200; -0,00147]); sędzia i nieobecności - przedział zawiera 0 (notatka); pogoda - brak danych. Nic nie weszło do modelu |
| F3.3 | decyzja operatora | |
| F4.1 | **spełnione** | `leg_relations.py`: test na wszystkich parach kluczy (>50 000 par); 10-05: 430/430 par z etykietą |
| F4.2 | **spełnione** | każda drabina pod nagłówkiem „ta sama zmienna”; forma „jeden szczebel” wyłączona (decyzja) |
| F4.3 | **spełnione** (raport) | sekcja „Ekspozycja na mecz”; 10-05: pozycje 1-30 na 4 meczach; limit - decyzja |
| F4.4 | **zamknięte decyzją operatora** | 2026-10-05: „nie wyceniaj mi ich, sam będę widział” - sofa nie drukuje kursu buildera (PDF: łączne p i „sprawdź na ekranie Superbetu”); bramka ceny z ekranu wyłączona (`BUILDER_SCREEN_PRICE_FROM_UTC = None`) |
| F5.1 | **spełnione** | `REJESTR_TESTOW.md` + `config/sofa_test_registry.json`, 5 testów PROPOSED (do zatwierdzenia), walidator |
| F5.2 | **nie spełnione** | `closing.jsonl` w 5 z 17 dni; dziura 09-19..09-30 (283 nogi) zostaje; od 10-01 prawie 100% |
| F5.3, F5.4 | zapisane | kryteria w rejestrze; rozstrzygnięcie po ~4 400 pozycjach |
| F6.1 | **częściowo** | `test_chaos.py` 18 testów + `test_chaos_stages.py` (SAMPLES, SETTLE z `--refetch-stat-gaps`, `resettle_sweep.py`, OFFER, SHADOW / CS2, pętle, sonda half-open, `backfill_event_stats` hokej/kosz/siatka); naprawione: 3 backfille wychodziły 1 zamiast 2 po otwarciu bezpiecznika; Superbet bez bezpiecznika (OFFER/SHADOW/CS2/CLV pytały każde zdarzenie po 403 i timeoucie) - teraz ten sam bezpiecznik co Sofascore, OFFER zachowuje poprzednią cenę nieodpytanych; SETTLE z odmową na ostatnich zdarzeniach mówił `breaker_open: false` (sweep szedł dalej w 403); SAMPLES przeniesione z poprzedniego przebiegu = OK; migawka SHADOW/CS2 z samymi odmowami = PARTIAL; krok pętli zabity sygnałem (-9) = sukces; watchdog CS2 brał cudzy pid za żywą pętlę; `capture_closing --loop` zawsze 0 i ginął na błędzie między przebiegami. NOT_TESTED: `run_boosts.py` (jeden błąd Superbetu kończy przebieg), krok pętli, który wisi (brak limitu czasu) |
| F6.2 | **spełnione** | `day_status.py` w `/sofa-day` |
| F6.3 | **nie spełnione** | 7 dni od dziś |

Poprawki znalezione przy weryfikacji 10-05 (po wdrożeniu): handicap T2 sportu
drukował znak drużyny 1 (Herlev, Esbjerg - zdjęte NO_BET, poprawione w kodzie);
fałszywy „pominięty przez horyzont” w planie przebudowy (poprawione).
Druga runda tego samego dnia (po „pushnij i upewnij się”): OFFER pomija mecz na
tych samych zegarach co CONFIDENCE (`locked_print.starts_after`; 10-05: Gaubas,
Monteiro - Moller dostałyby świeżą cenę zamiast 39-minutowej); FIXTURE_CHECK pyta
też przypięte mecze sportów (10-05 13:06Z: 35) i SPORT_CONFIDENCE / COUPON_ASSEMBLY
odrzucają FIXTURE_NOT_AS_SCHEDULED; C2 obejmuje nogi sportów; Superbet ma
bezpiecznik; 9 naruszeń kontraktu z testów chaosu naprawionych; sofa nie wycenia
builderów (decyzja operatora).

Podejrzenie weryfikatora zmierzone (`measure_pool_holes.py`): pula, która
wypełnia dziurę w krzywej rynku, zawyżała (57 nóg, 48 meczów: deklarowane 0,775,
zrealizowane 0,649, -12,6 pp [-24,1; -1,2]); ograniczenie najbliższym własnym
koszykiem poniżej (K13b) od 2026-10-06. Rynki bez żadnej własnej krzywej czytane
z puli też zawyżają (-14,1 pp [-21,0; -7,2], 290 nóg) - osobna decyzja operatora.
Nazwy klubów z „&” mapowane od 2026-10-06 (37 wystąpień 09-18..10-05).
