# Hokej: rynki Superbetu "z dogrywką i rzutami karnymi" i rynki poboczne

Data: 2026-11-20. Badanie tylko do odczytu: żaden plik repozytorium nie został zmieniony. Skrypty i wyniki leżą w
`/private/tmp/claude-501/-Users-mkoziol-projects-bet/04c6201e-4497-4273-b02c-92e4cd7d7f51/scratchpad/hockey/`.

## Werdykt

**Rynki 617 / 613 / 621 / 653 warto dodać tylko jako poprawkę zasięgu, nie jako źródło przewagi.** Ich wycena jest
dokładnym przekształceniem rozkładu wyniku po regulaminowym czasie, który model już symuluje: `_hockey` dopisuje
zwycięzcy dogrywki lub karnych jedną bramkę. Sprawdziłem to na każdej z 3149 gier NHL w powtórce. Wyniki dają się
rozliczyć w 100% (105/105 rozegranych zdarzeń). Krzywe są skalibrowane, a jakość modelu jest równa jakości ceny.
Przewagi nie ma.

- Na 105 meczach NHL (11-06..11-20, 4020 stron) różnica Brier model minus rynek wynosi **+0,0010 [-0,0046; +0,0062]**.
  Żaden z czterech rynków nie jest lepszy od ceny.
- Bramki druku (pewność ≥ 0,70, x ≥ 0,90, marża ≤ 15%) przepuszczają **657 nóg, około 44 dziennie, 6,3 na mecz**
  (krzywe NHL z historii). Trafienie 0,791 przy pewności 0,782, więc kalibracja jest dobra. ROI wynosi
  **-3,4% [-9,4; +1,9]**, a po podatku 12% **-15%**. Prosta reguła bez modelu ("każda krótka strona po kursie
  1,09-1,43") daje -4,6% [-7,9; -1,1]. Model nie wybiera lepiej niż cena.
- **Kluczowe odkrycie (sekcja 3).** 613 na każdej oferowanej linii (|h| ≥ 1,5) oraz 617 na liniach 3,5 / 5,5 / 7,5 /
  9,5 to **to samo zdarzenie** co handicap 604 i suma 623 w regulaminowym czasie. Tak wychodzi z logiki, a powtórka
  potwierdza to na 9447 + 12596 parach gra×linia. Nowej wyceny wymagają tylko 617 na liniach 2,5 / 4,5 / 6,5 / 8,5
  oraz 621 / 653.
- **Sedno: P(remis po 60').** Model zaniża remis w NHL o **+5,3 pp [+3,8; +6,7]**: daje 0,175, a w rzeczywistości jest
  0,228. Rynek (1X2 640 po zdjęciu marży) daje 0,226. Na liniach "z dogrywką" ten błąd prawie się nie przenosi, bo
  błędy się znoszą: model ma za dużo goli (6,12 wobec 5,96) i za mało remisów. Przeskalowanie remisów poprawia
  log-loss remisu o -0,0115 [-0,0160; -0,0071], a sum "incl" nie zmienia (-0,00004 [-0,00018; +0,00010]).
- Rynki poboczne (633 "Wszystkie tercje powyżej 0,5", 643 / 666 "1. gol"): **nie dodawać**. 633 nie ma strony, która
  mogłaby się wydrukować. 643 / 666 nie mają w cache kolejności goli dla hokeja: incydenty są puste w 299 z 299
  sprawdzonych wierszy.

Zalecenie: dodać to za przełącznikiem (sekcja 7) wtedy, gdy celem jest pokrycie NHL. NHL jest dziś wyceniane tylko przez
1X2, zwycięzcę, tercje i zawodników. Nie należy obiecywać, że te nogi poprawią wynik kuponu: dorzucą około 40-60 nóg
NHL dziennie, każdą mniej więcej po swojej cenie.

## 1. Kształt rynków (`s02_offers.py`, `s03_shapes.py` → `out_s03_shapes.txt`)

Źródło to `runs/sofa/2026-11-*/unmapped_prices/hockey_*.jsonl.gz` (515 plików). Dla każdej pary
(zdarzenie, rynek, specialBetValue, wybór) wziąłem ostatnią cenę ze statusem `active` sprzed `kickoff_utc` z
`runs/sofa/shadow/hockey/<d>/snapshots.jsonl`. Połączenie z Sofascore idzie przez `settled.json`
(`sofascore_event_id`, `home_is_team1`).

| rynek | zdarzenia | rozgrywki | linie (sbv × zdarzenia) | pary 2-drogowe | mediana marży | strony w strefie* |
|---|---|---|---|---|---|---|
| 617 Liczba goli (z dogr. i karnymi) | 108 | tylko USA - NHL | 3,5..8,5 ×108, 9,5 ×87, 2,5 ×38 | 735 (38 jednostronnych przy 2,5) | 0,076 | 379 |
| 613 Handicap (z dogr. i karnymi) | 108 | tylko NHL | ±1,5 / ±2,5 / ±3,5 ×108, -4,5 ×68, +4,5 ×51 | 670 (97 jednostronnych) | 0,076 | 313 |
| 621 drużyna 1 - liczba goli (incl) | 108 | tylko NHL | 3,5 ×108, 2,5 ×101, 4,5 ×74, 1,5 ×40 | 330 | 0,066 | 109 |
| 653 drużyna 2 - liczba goli (incl) | 108 | tylko NHL | 2,5 ×108, 3,5 ×107, 1,5 ×64, 4,5 ×53 | 334 | 0,066 | 121 |
| 633 Wszystkie tercje > X | 134 | Liiga, SHL, NLA, CHL, Extraliga, DEL | 0,5 | 134 | 0,086 | 0 |
| 643 1. tercja - 1. gol | 407 | AHL 102, Maxa liga, Liiga... | 3-drogowy | - | 0,129 | 9 |
| 666 1. gol | 407 | jw. | 3-drogowy (z "żadna") | - | 0,080 | 16 |
| 236253 wyścig do 2 / 236266 pierwszy gol incl | 108 | NHL | 3- / 2-drogowe | - | 0,09 | 0 |

\* Strefa to kurs 1,09-1,43 i p po zdjęciu marży ≥ 0,70 (definicja zlecającego). Mamy 108 zdarzeń, a nie 96,
bo dane sięgają 11-20 włącznie. Dziennie jest 2-12 meczów NHL.

Kontrole:
- 621 to zawsze drużyna 1, a 653 drużyna 2 (660 / 668 nazw zgodnych z `team1` / `team2`, 0 sprzecznych).
- W 613 `specialBetValue` to handicap drużyny 1 (1437 / 1437).
- Dla NHL SHADOW czyta dziś 640 (1X2 regulaminowe), 630 (zwycięzca incl), 606 (podwójna szansa), tercje i
  zawodników. Rynków 623 / 604 / 658 / 652 Superbet dla NHL nie wystawia (`snapshots.jsonl` 11-10..11-19).

## 2. Reguła rozliczenia (`s05_results.py`, `results.pkl`)

- **Superbet.** Regulaminu nie ma w repozytorium (`grep "Regulamin"`), a w sieci go nie znalazłem. Tekstu `info` rynku
  617 nie udało się odczytać, bo dla dzisiejszych meczów NHL nie było jeszcze kursów. Dowód pochodzi z własnych metadanych
  wyniku Superbetu (`GET /v2/pl-PL/events/<id>`, pole `metadata`). Przykład: Vegas - Dallas (15592280) ma tercje 0-2,
  2-0, 1-1, dogrywkę 0-0, **PENALTIES 1-2**, a `homeTeamScore/awayTeamScore` **3 / 4**. Wynik końcowy Superbetu liczy
  więc rzuty karne jako jedną bramkę dla zwycięzcy, a nie jako bramki z serii. U Columbus - Dallas jest PENALTIES 2-0
  i wynik 2-1. Rynek "Zwycięzca (z dogrywką i rzutami karnymi)" ma `info` "…wygra mecz (włącznie z dogrywką i rzutami
  karnymi)".
- **Sofascore w cache.** Przejrzałem wszystkie 6290 zakończonych gier NHL z `sofa_listed_event` (2022-02..2026-11):
  - 4887 to "Ended" z `current` równym sumie tercji;
  - 982 to "AET" z `normaltime` remisowym i `overtime` 1 / 0;
  - 420 to "AP" z `overtime` 0 / 0 i `penalties` 1 / 0;
  - zawsze zachodzi `current` = suma tercji + 1 dla zwycięzcy (1 wyjątek "Ended" z sumą tercji różną od `current`).
- Przykłady AET: Montreal - Utah 2+0+2 / 2+1+1, OT 1-0, current 5-4. New Jersey - St. Louis current 5-4. Colorado -
  Nashville OT 0-1, current 2-3.
- Przykłady AP: Columbus - Dallas 1-1, pen 1/0, current 2-1. Chicago - Winnipeg 4-4, current 4-5. San Jose - Pittsburgh
  2-2, current 2-3.
- **Reguła:** wynik incl = wynik regulaminowy + 1 dla zwycięzcy dogrywki lub karnych.
  - suma incl = suma reg + 1{remis};
  - drużyna incl = drużyna reg + 1{remis i ta drużyna wygrała};
  - margines incl = margines reg albo ±1 przy remisie.
- **Weryfikacja na 105 rozliczonych zdarzeniach z 108** (3 to mecze z 11-20 nad ranem, których SHADOW_SETTLE jeszcze
  nie przeszedł): 81 Ended, 16 AET, 8 AP. `current` Sofascore = reguła = wynik końcowy Superbetu: **105/105**. Pokrycie
  rozliczenia wynosi 100% zdarzeń rozliczonych przez SHADOW.
- Drugie liczenie (`s08_checks.py`, `out_s08.txt`) przechodzi przez kod `shadow.build_result(allow_final_only=True)` i
  `shadow.actual_value` / `grade`, z czterema rynkami dopisanymi w procesie jako specyfikacja o zasięgu "full". Daje
  **4020 / 4020 zgodnych ocen**: 617 1430, 621 640, 653 648, 613 1302. `GameResult.t1_full` (Sofascore `current`) już
  jest wynikiem, który rynek liczy.

## 3. Czy to te same zdarzenia, co rynki już czytane

Remis regulaminowy ma zawsze parzystą sumę bramek, a dogrywka zmienia margines tylko z 0 na ±1. Stąd:

- **617 przy L = k + 0,5 z nieparzystym k (3,5 / 5,5 / 7,5 / 9,5) to to samo zdarzenie co 623 przy tej samej linii.**
  Remis przy sumie k jest niemożliwy, więc +1 nigdy nie przekracza linii. Powtórka: 9447 / 9447 par gra×linia ma ten
  sam wynik i to samo p.
- **617 przy parzystym k (2,5 / 4,5 / 6,5 / 8,5) różni się** od 623 dokładnie wtedy, gdy mecz skończył się remisem
  k/2 : k/2. Było tak w 457 z 6298 par gra×linia, a powtórka wykazuje inny wynik dokładnie w tych grach.
- **613 przy każdym |h| ≥ 1,5 to to samo zdarzenie co 604 przy tym samym h.** Dla drużyny 1 z -1,5 potrzeba marginesu
  ≥ 2, którego remis (±1) nie daje. Dla drużyny 1 z +1,5 wystarczy margines ≥ -1, a remis go spełnia w obu wariantach.
  Powtórka: 12596 / 12596 par. 613 przy ±0,5 to byłby zwycięzca 630, ale w danych takiej linii nie ma.
- **621 / 653 różnią się na każdej linii** (remis k : k, drużyna wygrywa dogrywkę).
- `SAME_EVENT_DEDUP` (`bet.sofa.leg_identity`, hokej jako zbiór marginesów regulaminowych) nie zna 613 ani 617.
  Ponieważ Superbet nie wystawia 604 / 623 dla NHL, dziś żaden bliźniak by się nie wydrukował. Przy wdrożeniu trzeba
  jednak dopisać 613@h ≡ 604@h oraz 617@nieparzyste ≡ 623@to samo. Inaczej przy pierwszym meczu z obiema rodzinami
  ledger policzy jedno zdarzenie dwa razy. Uwaga: 613 +1,5 nie jest podwójną szansą (ta wymaga marginesu ≥ 0).

## 4. Model: remis i dogrywka (`s04_walk.py` → `walk.pkl`, `s06_analyse.py` → `out_s06.txt`)

Powtórka walk-forward wiernie odtwarza `sport_confidence.walk_forward_rows`:
- `build_model` jest przebudowywany co 30 dni, a księga ratingów aktualizowana mecz po meczu;
- mecze o tej samej godzinie są prognozowane, zanim którykolwiek z nich trafi do księgi;
- parametry hokeja są dzisiejsze: `SimParams()`, ścisła stawka ligowa, link "shared league", bez strzałów, bez
  dopasowanego pustego bramkarza i bez R3;
- ziarno symulacji to id Sofascore, jak w `DbForecaster`; 4000 symulacji od 2026-10-01, 2000 wcześniej.

Okno 2024-09-15..2026-11-21 obejmuje 3149 gier NHL (2024-25: 1398, 2025-26: 1393, 2026-27: 358), wszystkie z p.
Do porównań dochodzi co dziesiąta gra innych lig (5130). Historia pochodzi z `sofa_listed_event` po indeksie sportu
(107225 sparsowanych gier); skan stron `sofa_entity_events` pominąłem.

**P(remis po 60')**

| | n | model | realizacja | realizacja - model (bootstrap po meczu) |
|---|---|---|---|---|
| NHL ogółem | 3149 | 0,1749 | 0,2283 | **+0,053 [+0,038; +0,067]** |
| 2024-25 | 1398 | 0,1747 | 0,2082 | +0,034 [+0,012; +0,055] |
| 2025-26 | 1393 | 0,1755 | 0,2498 | +0,074 [+0,052; +0,096] |
| 2026-27 | 358 | 0,1736 | 0,2235 | +0,050 [+0,008; +0,093] |
| inne ligi (próbka) | 5130 | 0,1696 | 0,1949 | +0,025 [+0,015; +0,036] |

- Brier remisu: model 0,1791, stała 0,1762. Model rozróżnia remisy gorzej niż stała, a jego p remisu prawie się nie
  zmienia (97% gier ma p < 0,20).
- Drugie liczenie (`out_s08.txt`): w surowych danych tych 3149 gier status AET/AP ma 719 = 0,2283, a `normaltime`
  remisowy też 0,2283. Zgadza się.
- Na 105 meczach z ofertą: model 0,172, Superbet (640, 3 strony po zdjęciu marży) 0,226, realizacja 0,229.
- Bramki regulaminowe: średnia z symulacji 6,12 wobec 5,96 w rzeczywistości. To znany efekt dodatkowej późnej bramki
  (R3, model-state.md).

**P(gospodarz wygrywa dogrywkę lub karne | remis)**

- 719 remisów: gospodarz wygrał 0,526 [0,490; 0,561] (AET 0,533 na 493 grach, AP 0,509 na 226).
- Model (`hk_ot_strength` 0,5) daje 0,510, różnica +0,016 [-0,020; +0,051]. Brier modelu 0,2519, a stałej 0,5 0,2500.
- Wniosek: wartość 0,5 wystarcza. Siła drużyn w dogrywce nic tu nie dodaje.

**Próba korekty remisu.** To sonda, nie propozycja. Pomnożyłem komórki remisowe przez k = 1,242, dobrane na 2024-25,
i sprawdziłem na sezonach 2025-27 (1751 gier):

| co | zmiana log-loss |
|---|---|
| remis | -0,0115 [-0,0160; -0,0071] |
| suma incl | -0,00004 [-0,00018; +0,00010] |
| drużyna incl | -0,00008 [-0,00031; +0,00018] |

Rynkom incl korekta nic nie daje. Zaniżony remis szkodzi raczej 1X2 640, podwójnej szansie i handicapowi ±0,5 (DRAW),
choć tam błąd częściowo maskują krzywe. To osobny temat i ani nie mierzyłem go dalej, ani nie wdrażałem.

## 5. Pomiar

### 5a. Linie stałe na historii NHL (p surowe, 226728 wierszy)

| rodzina (OVER / drużyna 1) | realizacja - deklaracja | Brier | log-loss |
|---|---|---|---|
| suma reg | -0,017 [-0,029; -0,006] | 0,1870 | 0,5565 |
| suma incl | -0,010 [-0,022; +0,002] | 0,1866 | 0,5564 |
| drużyna reg | -0,013 [-0,021; -0,005] | 0,1978 | 0,5823 |
| drużyna incl | -0,006 [-0,014; +0,002] | 0,1984 | 0,5833 |
| handicap reg = incl | -0,001 [-0,012; +0,011] | 0,1817 | 0,5483 |

W pasmach p:
- suma incl 0,70-0,80: +0,025 [+0,014; +0,036], czyli model zaniża (reg +0,003);
- suma incl 0,80-0,92: -0,008;
- drużyna incl 0,80-0,92: -0,022 [-0,031; -0,013] (reg -0,020);
- handicap 0,80-0,92: -0,035 [-0,047; -0,024].

Przy p ≥ 0,60 suma incl ma +0,003 [-0,005; +0,010], a reg +0,001. Drużyna incl ma -0,009 [-0,014; -0,003], a reg
-0,007. **Dodanie dogrywki nie psuje kalibracji względem rynków, które już drukujemy.** Linia incl O4,5 jest lepiej
skalibrowana (+0,007) niż reg O4,5 (-0,011).

Krzywe NHL dopasowałem na wierszach historii sprzed 2026-10-01 (`fit_curves`, efektywne n, monotoniczne; pewność to
`realised_lo95`). Na hold-oucie 2026-10-01..11-20 pewność jest konserwatywna: suma incl +0,036 [+0,011; +0,058],
drużyna incl +0,031 [+0,011; +0,050].

### 5b. Oferowane linie Superbetu (105 meczów, 4020 stron; pominięte: 132 grupy jednostronne, 62 grupy nierozliczone)

| rynek | strony | Brier model - rynek | log-loss model - rynek |
|---|---|---|---|
| 617 | 1430 | +0,0049 [-0,0004; +0,0101] | +0,0102 [-0,0026; +0,0243] |
| 617 tylko parzyste k | 630 | +0,0051 [-0,0008; +0,0114] | +0,0115 [-0,0034; +0,0281] |
| 613 | 1302 | -0,0023 [-0,0083; +0,0042] | -0,0061 [-0,0260; +0,0145] |
| 621 | 640 | -0,0017 [-0,0129; +0,0096] | -0,0027 |
| 653 | 648 | +0,0016 [-0,0079; +0,0114] | +0,0056 |
| wszystkie | 4020 | +0,0010 [-0,0046; +0,0062] | +0,0021 [-0,0114; +0,0167] |

Kalibracja surowego p na oferowanych stronach (deklaracja / realizacja / cena po zdjęciu marży):
- 0,60-0,70: 0,649 / 0,659 / 0,642;
- 0,70-0,80: 0,751 / 0,755 / 0,732;
- 0,80-0,92: 0,858 / 0,859 / 0,821.

Drugie liczenie p: `score_model.line_probability` na GameResult odbudowanych z rozkładu łącznego daje maksymalną
różnicę 1e-16 (20 stron).

### 5c. Bramki druku (pewność ≥ 0,70, pewność×kurs ≥ 0,90, marża ≤ 15%; bez dowodów liniowych)

| krzywe | nogi | nogi na mecz (max) | pewność | trafienie | 1/kurs | ROI | ROI po 12% podatku |
|---|---|---|---|---|---|---|---|
| NHL z historii (nowe klucze) | 657 | 6,3 (9) | 0,782 | 0,791 [0,745; 0,834] | 0,818 | -3,4% [-9,4; +1,9] | -15,0% [-19,8; -10,3] |
| zainstalowane reg. (total / team_total / handicap) | 886 | 8,4 (13) | 0,824 | 0,830 [0,793; 0,865] | 0,857 | -3,4% [-8,0; +1,2] | -15,0% |

- Dziennie (krzywe NHL): od 13 (11-17) do 84 (11-15) nóg. Według rynku: 617 298, 613 165, 621 + 653 194. Aż 301 z 657
  nóg to zdarzenia tożsame z regulaminowymi.
- Wyniki osobno:
  - 613: ROI +0,0% [-9,1; +8,1];
  - 617: -4,5% [-10,3; +1,3];
  - 621 + 653: -4,5% [-13,2; +4,1].
- Trafienie ponad cenę po zdjęciu marży (+3,0 pp [-1,4; +7,4]) to efekt faworyta. Wszystkie krótkie strony bez modelu
  dają +1,9 pp [-0,8; +4,6] i ROI -4,6% [-7,9; -1,1] na 1079 stronach.
- Wszystko to jest mniej więcej po cenie. Nie mierzyłem obniżenia przez dowody liniowe: nowe klucze nie mają jeszcze
  rozliczonych linii, a 613 i 617 z nieparzystym k czytałyby offsety swoich rodzin regulaminowych. Liczby nóg są więc
  górną granicą.

## 6. Rynki poboczne (`s07_periods.py` → `periods.pkl`, `s09_secondary.py` → `out_s09.txt`)

- **633 "Wszystkie tercje powyżej 0,5 gola":**
  - da się rozliczyć w 100%, z wyników tercji;
  - p modelu to odsetek symulacji z bramką w każdej tercji;
  - 3060 gier sześciu lig 2025-09..2026-11: model 0,587, realizacja 0,596, różnica +0,010 [-0,009; +0,028];
  - modelowi brak rozdzielczości: w pasmie p ≥ 0,68 deklaracja 0,704 wobec 0,628 realizacji (n 207);
  - tylko 3,1% gier ma p ≥ 0,70, a rynek nie daje żadnej strony z p ≥ 0,70 (maksimum 0,643 po kursie 1,43);
  - krzywa obcięłaby pewność do około 0,63, więc **nic się nie wydrukuje. Nie dodawać.**
- **643 "1. tercja - 1. gol" i 666 "1. gol":**
  - incydentów hokejowych w cache nie ma: na 299 rozliczonych zdarzeniach `incidents_json` jest NULL, a 63 nie mają
    wiersza;
  - z samych wyników tercji 643 da się rozliczyć w 69,7% przypadków (0:0 albo strzelała jedna strona), 666 tylko w
    13,7%;
  - jest model z dwóch procesów Poissona: P(brak gola w 1. tercji) 0,198 wobec 0,191; faworyt pierwszy w 1. tercji
    maksymalnie 0,646, więc nigdy ≥ 0,70;
  - strony z p ≥ 0,70 po zdjęciu marży to w 9 / 27 przypadkach kobiece mecze reprezentacji (Kanada / USA (K)) po kursie
    1,02-1,12;
  - wymagałoby to pobierania incydentów (bridge) przy rozliczeniu i backfillu historii pod krzywe;
  - **nie dodawać.**
- 236253 (wyścig do 2) i 236266 (pierwszy gol incl) też wymagają kolejności goli. W strefie 0 stron.

## 7. Szkic wdrożenia (najlepszy kandydat: 617 / 621 / 653 / 613)

1. **`src/bet/sofa/epochs.py`:**
   - nowa stała `HK_OT_SO_MARKETS_FROM_UTC`, domyślnie następny dzień 00:00Z, a wcześniej tylko na polecenie
     operatora;
   - funkcja dnia i zegara budowy;
   - marker `hk_ot_so_rule` na wierszach i nogach;
   - grupa w ledgerze.
2. **`src/bet/sofa/shadow.py`:**
   - nowa tabela `OT_SO_MARKETS["hockey"]` na wzór `DERIVED_MARKETS`;
   - `parse_event` / `parse_line` czytają ją tylko przy włączonym przełączniku, a `spec_of` i `reads_market` ją znają;
   - po włączeniu rynki znikają z `unmapped_prices`;
   - `parse_line` już parsuje te nazwy: "Powyżej / Poniżej" + `specifiers.total`, "Drużyna (-1,5)" + `hcp`, nazwa
     drużyny w `marketName`. Trzeba to potwierdzić testem na prawdziwym payloadzie.
   - Propozycja rodzin:
     - **613 przy |h| ≥ 1,5 → `handicap`, zasięg "reg"** (zdarzenie tożsame, krzywa `handicap|TEAM`, rozliczenie bez
       zależności od dogrywki); |h| < 1,5 odrzucić (to zwycięzca);
     - **617 przy nieparzystym k → `total`, zasięg "reg"**;
     - **617 przy parzystym k → `total_ot`, zasięg "full"**;
     - **621 / 653 → `team_total_ot`, zasięg "full"**, team T1 / T2.
     - Prostsza wersja (cała 617 jako `total_ot`) też działa, ale wtedy `leg_identity` musi znać tożsamość z
       nieparzystym k.
3. **Rozliczenie, `shadow._pair` / `actual_value`:** zasięg "full" już zwraca `t1_full` / `t2_full`, czyli `current`;
   na 105 zdarzeniach zgadza się w 100%. Bezpieczniej dla hokeja liczyć "full" jako regulaminowe + 1{overtime} dla
   zwycięzcy, bo docstring `build_result` ostrzega, że bramka z karnych nie zawsze trafia do `current`. W NHL na 6395
   grach zawsze trafiała, ale w innych ligach (AHL, Europa) tego nie sprawdzałem.
4. **`src/bet/sofa/sport_confidence.py`:**
   - nowe rodziny w `ALLOWED_MARKETS` / `EXTENDED_MARKETS` za przełącznikiem oraz w `HISTORY_MARKETS["hockey"]`;
   - **wiersze historii dla rodzin `_ot` tylko z rozgrywek, w których remis po 60' nigdy nie jest końcowy** (NHL, AHL,
     ligi z dogrywką). W ligach z remisem `current` = regulaminowe, a model zawsze rozgrywa dogrywkę, co dałoby błędne
     oceny. Jest to ryzyko przy dopasowaniu.
   - Pozycje linii: `LINE_QUANTILES` (floor + 0,5) obejmują obie parzystości. Lepiej dodać stałą drabinę NHL (2,5..9,5;
     drużyna 1,5..4,5).
5. **Krzywe:** `scripts/sofa/fit_sport_confidence.py --sport hockey` na kopii bazy (`VACUUM INTO`, `--db-path`,
   `--without-db-backup`). Nowe klucze `total_ot|OVER/UNDER` i `team_total_ot|OVER/UNDER` trafiają do datowanego
   `config/sofa_sport_confidence_calibration.next.<D>.json`, a pozostałe klucze zostają bajt w bajt. Wymaga zgody
   operatora.
6. **Dowody liniowe:** `settled_shadow_rows` / `refresh_line_evidence.py` podchwycą nowe rodziny same. Przez pierwsze
   tygodnie nowe klucze czytają offset puli hokeja.
7. **`src/bet/sofa/leg_identity.py`:** 613@h ≡ 604@h i 617@nieparzyste ≡ 623@to samo, na zbiorze marginesów i sum
   regulaminowych. Zdarzenia z parzystym k i 621 / 653 potrzebują wymiaru dogrywki (reg1, reg2, zwycięzca dogrywki).
8. **Pozostałe pliki:**
   - `superbet_names.py` (słowa Superbetu);
   - `market_coverage.py` (reguła `hk.ot_so_scope` → zmapowana);
   - docstring `shadow.py`, `docs/sofa/PIPELINE.md`, model-state.md.
9. **Testy** w `tests/sofa/test_hockey_ot_so_markets.py`:
   - parsowanie 4 rynków z payloadu;
   - rozliczenie Ended / AET / AP (`penalties` 1/0, `current` +1) i przypadek "SO bez +1 w current";
   - tożsamości 613 = 604 i 617 przy nieparzystym k = 623;
   - wyłączony przełącznik daje snapshot bajt w bajt;
   - `reads_market`;
   - rejestr testów (`check_test_registry.py`).
10. **Nakład:** około 1 dzień kodu i testów plus refit hokeja (godziny, na kopii bazy). NHL zaczyna się 00:00-03:30Z,
    więc te nogi trafią na kupon tylko przez ręczny wieczorny rebuild (`SPORT_LATE_WINDOW`), jak dzisiejsze nogi NHL.

## 8. Ryzyka i rzeczy niesprawdzone

- **Mała próba.** Dane to 105 meczów z 15 dni na starcie sezonu, wszystkie przedziały ufności obejmują zero. Brak
  przewagi oznacza tylko, że jej nie wykryto. To samo dotyczy wyników ±.
- **Ekspozycja.** 6-13 nóg na jeden mecz NHL, silnie skorelowanych (suma, drużyna, handicap jednego wyniku). Wynik dnia
  NHL będzie zależał od kilku meczów.
- **Remis zaniżony o 5 pp** w modelu regulaminowym. W rynkach incl błąd się znosi z nadmiarem goli i krzywe to łapią.
  Kompensacja jest jednak przypadkowa i każda poprawka nadmiaru goli (np. R3) ją rozbije. Trzeba wtedy przemierzyć
  rodziny `_ot` razem z nią.
- **Regulaminu Superbetu nie przeczytałem**, a tekstu `info` rynku 617 nie odczytałem (dla NHL nie było jeszcze
  kursów). Reguła "karne = 1 bramka" opiera się na metadanych wyniku Superbetu (homeTeamScore / awayTeamScore przy
  PENALTIES) i na 105/105 zgodnościach z Sofascore.
- **Powtórka a produkcja.** Historia pochodzi tylko z `sofa_listed_event` (bez skanu stron, który robi `load_events`).
  Model był przebudowywany co 30 dni zamiast świeżo w chwili budowy. Krzywe NHL dopasowałem tylko na NHL i tylko na moich
  stałych liniach, a nie przez `fit_sport_confidence.py`. Pewność na żywo jest więc przybliżona.
- **Nie mierzyłem:**
  - obniżenia przez dowody liniowe (offset z odległości od ceny, ograniczenie w pasmach cenowych);
  - świeżości ceny i STALE_PRICE;
  - odrzuceń przez analityków;
  - innych lig z dogrywką;
  - rynku 236253 / 236266 poza strefą;
  - 613 ±0,5 (nieoferowane).
- Zmierzone przy okazji, bez działań: zaniżony remis szkodzi raczej 640 / 606 (DRAW i podwójna szansa) niż nowym
  rynkom.

## Pliki

- `s01_load_events.py`: historia hokeja z `sofa_listed_event` (zapytanie po indeksie) do `hockey_events.pkl`.
- `s02_offers.py`, `s03_shapes.py`: kształt rynków (`out_s03_shapes.txt`).
- `s05_results.py`: wyniki Sofascore i metadane Superbetu (`results.pkl`).
- `s04_walk.py`: walk-forward NHL (`walk.pkl`, `walk.log`).
- `s06_analyse.py`: kalibracja, oferowane linie i bramki druku (`out_s06.txt`, `analysis.pkl`).
- `s08_checks.py`: druga ścieżka ocen i p, remis z surowych danych, sonda korekty remisu (`out_s08.txt`, z dopisanym
  rozbiciem nóg na rynki).
- `s07_periods.py`, `s09_secondary.py`: 633 / 643 / 666 (`periods.pkl`, `out_s09.txt`).
