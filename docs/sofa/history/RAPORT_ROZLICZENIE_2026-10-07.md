# Rozliczenie kuponu 2026-10-07 — co weszło, co nie, i czy dało się uniknąć

Raport z 2026-10-08. Źródła: `runs/sofa/2026-10-07/11_coupon.json`,
`printed/*.json` (21 wydruków), tabela `sofa_settled_row`, ledger
(`record_results.graded_confidence` — ta sama funkcja, która pisze ledger),
`runs/sofa/shadow/basketball/2026-10-07/settled.json`, zrzuty ekranu slipu
`8923-1TYO9F` od operatora. Dzisiejszy kupon: `runs/sofa/2026-10-08/11_coupon.json`.
Nic nie refitowano, nie zmieniono epok ani bramek. Pełna lista nóg:
`reports/rozliczenie_nog_2026-10-07.csv` (829 pojedynczych: 816 `official` +
13 `removed:reads`, z wynikiem i wartością faktyczną tam, gdzie baza ją ma).

## 1. Werdykt w pięciu zdaniach

1. Slip `8923-1TYO9F` (7 zdarzeń, kurs 9,51) przegrał na **dwóch nogach z
   piętnastu**: `Grêmio Anápolis – Goiânia poniżej 3,5 gola` (4 gole) i
   `Corinthians poniżej 4,5 kartki` (5). To 2 pudła, oczekiwane przy
   średniej pewności 0,846 to **2,3**. To rozrzut, nie błąd nogi.
2. Slip miał z konstrukcji ok. **8% szans** na komplet (iloczyn pewności naszych
   nóg, przy założeniu niezależności grup; uczciwy kurs ~12,4 wobec 9,51).
   Przegrywa się go ~9 razy na 10.
3. Piłka nożna wczoraj była **skalibrowana** (233 nogi, 78,5% trafień przy
   pewności 78,9%). Strata kuponu (-48,26 j.) wzięła się gdzie indziej:
   tenis z porannego wydruku (-19,5 j.), koszykówka (-20,5 j.), hokej (-10,5 j.).
4. Z danych sprzed meczu dało się zobaczyć jedno ostrzeżenie dotyczące przegranej
   Corinthians (zastrzeżenie analityka o stawce meczu, zapisane i zignorowane
   przy `KEEP`). Przy Anápolis nie było żadnego.
5. Dzisiejszy kupon **nie powtarza** największej wczorajszej dziury
   (tenis `games_won_for OVER`: 164 nogi → 2). Powtarza dwa wzorce, które nie są
   błędem, ale są ryzykiem: nogi „cards OVER total + cards UNDER drużyny" w tym
   samym meczu (Santos – Flamengo) i drabiny jednego meczu w koszykówce.

## 2. Wynik kuponu dnia (to, co ledger nazywa `official`)

Dzień był **mieszany**: poranny wydruk 04:34Z pod starymi regułami, reguła
dowodów linii od 10:55Z, pakiety modeli od 14:05Z, nowe krzywe od 17:51Z.
Wyniki z różnych godzin to różne eksperymenty (CLAUDE.md, „Comparability").

| sport | pozycji | rozliczone | weszło / nie | pewność śr. | trafień | wynik (j.) |
|---|---|---|---|---|---|---|
| tenis | 391 | 368 | 239 / 129 | 0,767 | 64,9% | -13,80 |
| piłka | 234 | 233 | 183 / 50 | 0,789 | 78,5% | -3,26 |
| hokej | 130 | 129 | 95 / 34 | 0,796 | 73,6% | -10,15 |
| koszykówka | 50 | 47 | 19 / 28 | 0,760 | 40,4% | -20,54 |
| CS2 | 10 | 9 | 8 / 1 | 0,802 | 88,9% | +0,49 |
| siatkówka | 1 | 1 | 0 / 1 | 0,844 | 0% | -1,00 |
| **pojedyncze razem** | **816** | **787** | **544 / 243** | | **69,1%** | **-48,26** |

Reszta pozycji: 19 zwrotów (krecz / walkower, 0 j.), 5 UNSETTLED, 4
`PENDING:DATA_MISMATCH` (nogi sportów), 1 VOID. Buildery z PDF (kurs szacowany
−12%, nie z ekranu): **B1 Nanjing – Shaanxi WIN**, **B2 Wu – Zheng LOSS**
(`double_faults_for OVER 1,5`, padło 1), **B3 Vinotinto – Cuenca**
nierozliczony (brak statystyki `corners_total`), **B4 Operário – Botafogo-SP WIN**:
+0,256 j. Razem ledger: **-48,004 j.**, `MISMATCH 0`. Nogi zdjęte przez odczyty
(`removed:reads`, poza wynikiem kuponu): 13 nóg, 11 / 2, +1,43 j.

### Gdzie naprawdę padło -48 j.

| wycinek | nóg | trafień | pewność | wynik |
|---|---|---|---|---|
| tenis, mecze startujące **przed 10:55Z** (poranny wydruk, bez dowodów linii) | 323 | 61,9% | 0,764 | **-19,53** |
| tenis, mecze po 10:55Z | 45 | 86,7% | 0,788 | +5,73 |
| w tym tenis `games_won_for OVER` (cały przed 14:05Z) | 164 (73 mecze) | **52,4%** | 0,753 | **-16,85** |
| tenis `games_won_for UNDER` | 151 | 76,2% | 0,782 | +4,94 |
| koszykówka `handicap` T2 | 19 (7 meczów; 14 nóg w trzech: Aris, Oradea, Trier) | 15,8% | 0,77 | -14,66 |
| koszykówka `handicap` T1 | 24 | 62,5% | 0,76 | -3,41 |
| hokej `period_total` OVER + `period_team_total` UNDER | 57 | 77% | 0,83 | -5,31 |
| piłka `corners_total` | 35 | 65,7% | 0,80 | -6,53 |
| piłka `goals_total` | 75 | 85,3% | 0,80 | +4,72 |

- **Tenis `games_won_for OVER`** to największa dziura dnia: próbka własna
  (n = 10) **nie dyskryminuje** — nogi z `sample_hit_rate` 0,7 / 0,8 / 0,9
  zrealizowały 52,6% / 52,9% / 50,0%. Klasa ogólna `market:` 44,2% (86 nóg),
  kobieca `tennis_women:` 61,5% (78 nóg), przy pewności 0,755 / 0,751.
  Dowody linii z 3 dni (`config/sofa_superbet_line_evidence.json`, n = 1650
  linii, 224 gier) pokazują ten sam kierunek: kubełek 0,70–0,75 zrealizował
  62% (75/121), 0,75–0,80 71% (90/126).
- **Koszykówka**: 18 meczów, a 19 nóg T2 to w praktyce trzy–cztery monety — faworyci
  wygrali wysoko (Trier 92:59 Batumi, Oradea 93:67 Fribourg, Aris 93:80 Burgos),
  a nogi „faworyt nie wygra o więcej niż X" padły hurtem. `design_effect`
  koszykówki w pliku dowodów to 6,33. Znak linii jest poprawny: `line` T2 to
  handicap drużyny 1, PDF pisze go jako własny (`display_line`), a rozliczenie
  zgadza się z wynikiem (Burgos +13,5 przy przegranej 13 → WIN, +12,5 → LOSS).
- **Piłka**: pewność 0,789 vs trafienia 0,785. Słabe są rynki rożnych
  (`corners_total` 65,7% przy 0,80; `corners_for` 50% na 12 nogach;
  `shots_on_target_for` 33% na 6) — próbki za małe na wniosek, zapisane jako
  obserwacja do kolejnego pomiaru (CLAUDE.md: „measure the admitted football props
  separately").
- Kalibracja po kubełkach pewności (7b audytu, football + tenis): 0,70–0,75:
  67,0% (n = 200); 0,75–0,80: 65,3% (n = 242); 0,80–0,85: 79,0%; 0,85–0,90: 89,5%.
  Dziura siedzi w dwóch dolnych kubełkach i jest tenisowa.

## 3. Twój slip `8923-1TYO9F`, noga po nodze

Stawka 2,00 PLN gotówki / 1,76 wkład, kurs 9,51 (iloczyn kursów, które widać na
zrzutach, = 9,52). Status: **Przegrany**. Zielone = weszło, czerwone = nie.

| # | mecz (wynik) | noga | pewność | kurs | próbka | odczyt analityka | wynik |
|---|---|---|---|---|---|---|---|
| 1 | Cadenasso – Giunta (0:2) | 2. set, Cadenasso gemy powyżej 3,5 | 0,818 | 1,16 | 9/10, min 1 maks 6 | brak (poza top 30) | **WIN** (5 gemów) |
| 2 | Zamora – Barinas (0:0) | 1. połowa, gole poniżej 2,5 | 0,816 | 1,13 | 17/20 | brak | **WIN** |
| 3 | Grêmio Anápolis – Goiânia (4:0, czerwona dla Goiânia) | gole poniżej 3,5 | 0,822 | 1,19 | 17/20, maks 5 | brak (poza top 30) | **LOSS** (4 gole) |
| 4a | Bragantino – Mirassol (1:1) | gole poniżej 4,5 | 0,897 | | 17/19 | KEEP | WIN (2) |
| 4b | | celne strzały powyżej 6,5 | 0,873 | | 15/18 | brak | WIN (11) |
| 4c | | 1. połowa, gole poniżej 2,5 | 0,852 | | 18/19 | KEEP | WIN (0) → **builder WIN 1,50** |
| 5a | Internacional – Corinthians (2:1) | kartki łącznie powyżej 3,5 | 0,812 | | 19/20 | KEEP | WIN (9) |
| 5b | | Internacional kartki powyżej 1,5 | 0,807 | | 9/10 | KEEP („six-pointer raises card risk") | WIN (4) |
| 5c | | **Corinthians kartki poniżej 4,5** | **0,882** | | 9/10, maks 5 | KEEP („one value above the line; relegation stakes not in artifacts (caveat)") | **LOSS** (5) → **builder LOSS 1,55** |
| 6a | Vitória – Chapecoense (4:0) | rzuty rożne poniżej 14,5 | 0,875 | | 19/20 | brak | WIN (9) |
| 6b | | rzuty rożne powyżej 6,5 | 0,870 | | 17/20 | brak | WIN (9) |
| 6c | | celne strzały powyżej 6,5 | 0,873 | | 17/20 | brak | WIN (12) |
| 6d | | gole poniżej 4,5 | 0,849 | | 19/20 | brak | WIN (4) → **builder WIN 1,75** |
| 7a | Vila Nova – Cuiabá (0:0) | rzuty rożne powyżej 7,5 | 0,819 | | 17/20 | brak | WIN (12) |
| 7b | | gole poniżej 3,5 | 0,822 | | 17/20 | brak | WIN (0) → **builder WIN 1,50** |

Kontrola: **13 z 15 nóg weszło.** Każda z nóg 1, 3, 5c, 7b istnieje u nas jako
pojedynczy wydruk, więc rozliczenie w sofa i na Superbecie jest zgodne co do
każdej z 15 (wartości faktyczne z `07_settled.json`: Anápolis 4, Corinthians 5,
Internacional 4, kartki łącznie 9, Cadenasso 5).

Co pokazują dwie przegrane:

- **Anápolis – Goiânia, poniżej 3,5.** Liga `Goiano, Divisão de Acesso`
  (drugi poziom stanowy), krzywa `market:goals_total|UNDER` (138 859 wierszy,
  wszystkie ligi), próbka 17/20 z jednym meczem na 5 golach. Pewność 0,822 = „raz
  na 5–6 razy to nie wejdzie", a wczoraj goals UNDER na całej piłce weszło
  w 84,9% (53 nogi). Nic w artefaktach nie ostrzegało; czerwona kartka dla
  Goiânia (ze zrzutu) to zdarzenie w trakcie meczu.
- **Corinthians, poniżej 4,5 kartki.** Próbka n = 10 (średnia 2,7, maks 5), a ta
  sama drużyna w innej nodze miała `misses 4,4,5; stakes caveat`. Analityk w tym
  samym meczu napisał o nodze Internacional OVER, że „six-pointer raises card
  risk" — a przy UNDER Corinthians wpisał `KEEP` z zastrzeżeniem. Dwie nogi tego
  samego scenariusza („ostry mecz") siedziały w slipie po przeciwnych stronach:
  total kartek OVER 3,5 wygrywa przy ostrym meczu, Corinthians UNDER 4,5 w nim
  przegrywa. To jest jedyne ostrzeżenie sprzed meczu, jakie znalazłem; to
  osąd analityka, nie błąd kodu.

### Dwie nogi twojego slipu nie ma w końcowym kuponie

`11_coupon.json` z 19:13Z (a więc PDF i ledger) nie zawiera **Corinthians
poniżej 4,5** ani **Zamora – Barinas 1. połowa poniżej 2,5**. Obie były na
wydruku od 04:34Z / 10:59Z, i na wydruku z 18:21Z (twój slip: 18:01Z), po czym
wypadły z wydruku 19:13Z — przed startem, więc obowiązuje „noga zdjęta przed
startem zostaje zdjęta".

- Corinthians 4,5: w ofercie z 19:11Z **nie ma już tej linii** (Superbet
  oferuje `cards_points_for corinthians` tylko 1,5 / 2,5 / 3,5) — brak ceny.
- Zamora 1H: cena pobrana 18:18Z, rebuild 19:11Z → 53 min wobec limitu 45 min;
  najpewniej `STALE_PRICE` (powodu nie widać w logu, więc to hipoteza).

Skutek: **przegrana noga twojego slipu (Corinthians 4,5) nie występuje w
ledgerze** — ledger czyta tylko końcowy `11_coupon.json`. Wszystkich takich nóg
„wydrukowanych, a potem zdjętych przed startem" (poza `removed_by_reads`) jest
**298**; z tych, które mają wiersz w bazie, piłka: 52 WIN / 21 LOSS (+14,99 j.),
tenis: 47 / 39 (+21,80 j.); 101 nóg sportów mierzonych (grade z pinned id, nie
liczone tutaj) i 38 piłki / tenisa bez wiersza nie ocenione. To nie
jest anty-selekcja (zdjęte wygrywały częściej), ale jest to luka widoczna dla
operatora: rozliczenie „kuponu" nie obejmuje tego, co operator mógł postawić
z wcześniejszego PDF. Do decyzji, nie zmieniane.

## 4. Czy dało się uniknąć porażki?

**Na poziomie nogi: nie z danych, które istniały.** Obie przegrane miały
pewność 0,82–0,88; 2 pudła na 15 nóg przy oczekiwanych 2,3 to wynik środkowy.
Gdyby wczorajszy wynik był dostępny przed meczem, nie zmieniłby krzywej
piłkarskiej (była skalibrowana, +/-0,4 pp).

**Na poziomie slipu: tak, ale to nie jest wada kuponu.**
Iloczyn pewności grup (1: 0,818; 2: 0,816; 3: 0,822; 4: 0,668; 5: 0,578;
6: 0,565; 7: 0,673) to **0,0805**. Przy kursie 9,51 daje to oczekiwane
-23% (uczciwy kurs ~12,4). Założenie niezależności grup i traktowanie pewności jako
prawdopodobieństwa (jest jej dolnym ograniczeniem) są niepewne w obie strony;
korelacja nóg *w obrębie* meczu (buildery) jest dodatnia, więc 4–7 mogą być
nieco lepsze niż iloczyn, a Superbet wycenia buildery z narzutem 8,8–19,6%.
Pojedyncze nogi kuponu to pozycje po ~0,8; **sofa nie wycenia i nie
sugeruje łączenia ich w jeden slip** (CLAUDE.md: bez wyceny kombinacji, bez
stawek), więc to jest informacja, nie rekomendacja.

**Co mogło zmienić wynik tego jednego slipu, gdyby zastosować wcześniej:**

| reguła | czy złapałaby wczoraj | stan |
|---|---|---|
| analityk: „stakes caveat" / „six-pointer" przy cards ⇒ WATCH dla UNDER na kartki w tym meczu | tak, Corinthians 4,5 i 3,5 | **nie istnieje**; to zmiana tego, co się drukuje, wymaga pomiaru i przełącznika epoki — sugestia, nie wdrożona |
| `MODEL_ABOVE_OWN_SAMPLE` (luka > 0,15) | nie: model 0,858, próbka 0,90 (luka ujemna) | działa, nie dotyczy |
| odczyt 30 pierwszych pozycji | nie: nogi 1, 2, 3, 4b, 6a–d, 7a–b nie miały odczytu (poza top 30) | działa jak zaprojektowano |
| ograniczenie nóg na mecz (`max_positions_per_match`) | nie dotyczy konstrukcji slipu operatora | wyłączone, decyzja operatora |

Czyli: **nie znalazłem błędu w kuponie z 10-07, który doprowadził do tej
porażki.** Znalazłem jedną rzecz sprawdzalną ręcznie (zastrzeżenie analityka
sprzeczne z `KEEP`) i jedną strukturalną (7 grup po ~0,8).

## 5. Dzisiejszy kupon (2026-10-08) — kontrola pod kątem wczorajszych strat

Kupon z 06:38Z: 721 pojedynczych (tenis 347, piłka 171 w 51 meczach, hokej 167,
koszykówka 34, siatkówka 2), 0 builderów, 60 nóg zablokowanych, 27 zdjętych przez
odczyty. `audit_coupon` (4.1/4.2) i `audit_variants`: **0 znalezisk**.
`day_status`: WARN.

| sprawdzenie | wynik |
|---|---|
| tenis `games_won_for OVER` (wczoraj 164 nogi, 52,4%) | **2 nogi** dziś. Powód z artefaktów nie rozdzielony między dowody linii (odświeżone dziś 06:17Z, obejmują 10-07), nowe krzywe 17:51Z i estymator rating; **nie testowałem**, która zmiana to robi |
| tenis `games_won_for UNDER` (wczoraj 76,2% przy 0,78) | 52 nogi, pewność 0,742 |
| tenis nogi per set `games_won_set1/2_for OVER` | **108 nóg** (64 + 44), liczone **własną próbką n = 10** (`forecast_p` puste), krzywe `market_thin` (n = 199 / 262). To ten sam rodzaj estymatora, który wczoraj nie dyskryminował na `games_won_for`. Dowody linii dla tych kluczy: set 2 kubełki 0,75–0,80: 72%; 0,80–0,85: 81%; set 1: 0,75–0,80: 73%, 0,80–0,825: 71%, 0,825–0,85: 67%. Wczoraj tych nóg rozliczono 8 + 8 (14 z 16 weszło) — za mało na wniosek. **Ryzyko niezmierzone** |
| piłka `goals_total UNDER` w niższych ligach (wzorzec Anápolis) | 42 nogi, pewność śr. 0,813; w tym niższe ligi i rezerwy argentyńskie (5 meczów `Reserve`). Kalibracja klucza wczoraj dobra (84,9%). Nie błąd; to samo ryzyko 1 na 5–6 |
| piłka `cards_points_for UNDER` n = 10 (wzorzec Corinthians) | 2 nogi: Athletico 3,5 (read KEEP) i Flamengo 3,5 (**bez odczytu**) |
| ten sam mecz: kartki OVER total **i** UNDER drużyny | **Santos – Flamengo**: cards total OVER 3,5 (0,727) + Flamengo cards UNDER 3,5 (0,787) + total UNDER 7,5 — dokładnie struktura, która wczoraj przegrała. Mecz nie jest w odczytach |
| koszykówka | 34 nogi w 10 meczach; **Valencia – Hapoel 9 nóg, Bayern – Virtus 6, Panathinaikos 5, Real – Partizan 5 (T2)** — każda drabina to jedna moneta. Pewności obniżone o offset -0,0568 (poranna poprawka dzisiaj obniżyła 25 nóg koszykówki, wg raportu domknięcia). Wczorajszy wynik T2: 15,8% |
| świeżość cen | **oferta ma 68 min** (limit rebuildu 45 min) — przed postawieniem trzeba `rebuild_day.py` albo sprawdzić ceny ręcznie; kupon z 06:38Z ma ceny z 06:18Z |
| FIXTURE_CHECK | 411 sprawdzonych, 2 UNVERIFIED (17275526, 17275529, U19), bez nóg na kuponie |
| wiek ostatniego zamknięcia ledgera | `MISMATCH 0`, D-1 zapisany w 6 wariantach |

**Wniosek:** w dzisiejszym kuponie nie znalazłem błędu, który wyjaśniałby
wczorajszą stratę, bo wczorajsza strata nie była jednym błędem. Główną dziurę
(poranny tenis `games_won_for OVER`) dzisiejszy kupon ma drastycznie mniejszą;
nie wiem, czy naprawioną, bo to wymaga rozliczenia dzisiejszych nóg. Ryzyka
otwarte: 108 nóg setowych na tym samym typie estymatora, drabiny koszykówki i
struktura Santos – Flamengo.

## 6. Luki audytu, które znalazłem po drodze

1. **`audit_settlement.py` (7c) i `audit_day_deep.py` liczą 625 pojedynczych i
   633 nogi**, a ledger ma **816 + 4 buildery**. Brakuje 191 nóg sportów
   mierzonych (czytają `08_confidence.json`, nie `11_coupon.json`).
   „Suma kuponu -48,26 j." w 7c się zgadza, tabele wokół niej nie. Sprawdzone:
   liczby powyżej z `graded_confidence`, nie z tych audytów. Nie poprawiałem.
2. **Nogi wydrukowane i zdjęte przed startem (298) nie są nigdzie
   rozliczone** (sekcja 3).
3. `CANCELED` (code 70) nie jest w `settle.REFUND_REASONS`: 4 nogi meczu
   17239649 (Radenković – Obradović) są UNSETTLED; już opisane w raporcie
   domknięcia, rozstrzyga regulamin Superbetu.
4. Pewność 0,88 Corinthians UNDER 4,5 przy n = 10 pochodzi z krzywej
   `market:cards_points_for|UNDER` (29 941 wierszy); nie mierzyłem, czy krzywa
   rynków drużynowych jest skalibrowana w górnym kubełku (osobny pomiar,
   jedna noga nie jest dowodem).

## 7. Czego nie sprawdziłem

- Przyczyny zniknięcia Zamora 1H w rebuildzie 19:13Z (tylko hipoteza `STALE_PRICE`).
- Czy zmniejszenie `games_won_for OVER` z 164 do 2 to zasługa dowodów linii,
  nowego estymatora czy po prostu innej tablicy meczów.
- Standingów, stawki meczu Internacional – Corinthians i czerwonej kartki w
  Anápolis poza zrzutem ekranu i zapisami analityka (brak źródła w artefaktach).
- Dzisiejszych cen na żywo (brak sieci / mostu w tej sesji).
- Wpływu korelacji w obrębie meczów na wartości 4–7 slipu (iloczyn to
  przybliżenie).

## 8. Co zostało zrobione, a co nie

Zapisano tylko raport i CSV w `docs/sofa/history/`. **Nie** zmieniono kodu,
konfiguracji, krzywych, kuponu ani PDF, nie uruchamiano refitu ani rebuildu,
nic nie commitowano. Propozycje do decyzji operatora (każda zmienia to, co się
drukuje, więc wymaga pomiaru i przełącznika `bet.sofa.epochs`):
(a) odczyt analityka z „stakes / six-pointer" przy kartkach ⇒ `WATCH` dla UNDER
tego meczu; (b) pomiar nóg setowych tenisa `games_won_set*_for OVER` wobec
estymatora rating; (c) rozliczanie nóg wydrukowanych i zdjętych przed startem
w osobnym wariancie ledgera; (d) naprawa źródła audytu 7c / deep na
`11_coupon.json`.
