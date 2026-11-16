# Noga „chwiejna” w ocenie analityka — rejestracja i pomiar wstecz (2026-11-16)

Test: **T-STABILITY-LABEL-RETRO** (wstecz, archiwum 10-26..11-15) i
**T-STABILITY-LABEL-FORWARD** (prospektywny, od 2026-11-17 00:00Z).

Decyzja operatora 2026-11-16: analityk ma umieć powiedzieć „ta noga jest
chwiejna”, a taka noga — jeśli pomiar to uzasadni — ma wypadać i być
zastępowana. Bodziec (pojedynczy wynik, **nie argument**): /kupon 11-16, CS2
„Zwycięzca (z dogrywką): Brute” @1.53.

Co już zmierzono (nie powtarzamy):

- Audyt analityków 10-26 (`docs/sofa/history/analitycy_2026-10-26/AUDYT_ANALITYKOW_2026-10-26.md`):
  nogi zdjęte vs KEEP, ROI −0,9 pp [−5,9, +4,2] (1 104 vs 9 198 nóg);
  19 z 24 WATCH stało na formie / h2h / tabeli.
- CS2 match_winner, faworyt @1.10–2.00, linie Superbetu 09-28..11-15, n 1 227:
  „przegrana seria < 48 h” realizacja − fair −1,8 pp [−7,1, +3,6] (n 305);
  „≥ 2 porażki z 3 ostatnich” −2,8 pp [−6,7, +1,1] (próg po fakcie — trop).
- Test „jak typer” (11-16): 0 z 20 przegranych nóg złapanych.

Hipoteza tego testu jest inna niż forma liczona mechanicznie: **całościowy
osąd „chwiejna” (forma, seria porażek, niepewny skład, rotacja, motywacja,
zmienność rynku) wybiera nogi, które realizują się poniżej swojej ceny.**

---

## A. Rejestracja (zapisana i zacommitowana przed klasyfikacją; żadnej etykiety ani wyniku według etykiet nie widziano)

### A1. Definicja (instrukcja dla klasyfikatora, ta sama dla każdego sportu)

> Oceniasz **jedną nogę** (rynek, linia, kierunek, kurs) na podstawie
> **wyłącznie** tekstu analizy meczu napisanego przed meczem. Pytanie: czy
> z tego, co analiza mówi, **zmienna, którą rozlicza ta noga**, jest dziś
> stabilna, czy chwiejna? Nie oceniasz drużyny ani meczu w ogóle — tylko to,
> czy liczba / zdarzenie, od którego zależy noga, może dziś łatwo wypaść
> inaczej niż mówi jej próbka i model.
>
> - **STABILNA** — analiza opisuje zmienną nogi jako przewidywalną: próbka
>   i kontekst są zgodne, nic w tekście nie wskazuje, że dziś mecz będzie
>   inny niż zwykle dla tej zmiennej (skład znany i typowy, brak rotacji,
>   brak serii porażek / załamania formy wpływającej na tę zmienną, marża
>   względem linii wyraźna).
> - **CHWIEJNA** — analiza zawiera choć jeden konkretny powód, przez który
>   **ta zmienna** może dziś wypaść inaczej: świeża seria porażek lub
>   wyraźny spadek formy strony, od której noga zależy; niepewny / zmieniony
>   skład, kluczowy brak, niepotwierdzony bramkarz / zawodnik; rotacja,
>   drugi mecz w krótkim czasie, mecz „bez stawki” lub odwrotnie — skrajna
>   motywacja, która zmienia styl; duża zmienność samej zmiennej (próbka
>   rozrzucona, linia blisko środka, wynik zależny od jednego zdarzenia);
>   dane cienkie lub sprzeczne (mała próbka, inna klasa rozgrywek, mostek
>   międzyligowy). Powód musi działać **przez zmienną nogi** — brak bramkarza
>   to powód dla goli, nie dla rzutów rożnych.
> - **BRAK_PODSTAW** — analiza nie mówi nic, co pozwala ocenić tę nogę (noga
>   nie jest omówiona ani wprost, ani przez swoją rodzinę rynku).
>
> Jedno zdanie powodu (po polsku, z tekstu analizy) i jedna kategoria:
> `FORMA`, `SKŁAD`, `ROTACJA`, `MOTYWACJA`, `ZMIENNOŚĆ`, `DANE`, `INNE`
> (dla STABILNA: kategoria najmocniejszego argumentu za stabilnością albo
> `INNE`). Werdykt analityka (KEEP / WATCH) nie jest odpowiedzią — oceniasz
> stabilność zmiennej, a nie to, czy analityk nogę zostawił.

Przykłady per sport (ilustracja, nie lista zamknięta):

| sport | CHWIEJNA (przykład) | STABILNA (przykład) |
|---|---|---|
| piłka nożna | „gole drużyny poniżej 1.5” przy informacji o nowym trenerze i trzech porażkach z rzędu; rożne strony, która dziś może oddać piłkę (zestawienie przeciw); kartki przy niepotwierdzonym sędzi i derbach; prop zawodnika z niepotwierdzonym składem | suma goli poniżej 4.5 przy obu stronach 9/10 poniżej, skład potwierdzony, nic w kontekście |
| tenis | gemy / sety gracza po krecz lub urazie, zmiana nawierzchni, kwalifikant po trzech meczach w 3 dni; tie-breaki przesądzające o linii | handicap faworyta z wyraźną przewagą serwisu na tej nawierzchni, obaj grali tydzień normalnie |
| hokej | gole / wynik przy niepotwierdzonym bramkarzu, back-to-back, seria porażek; tercje (mała liczba goli, duża wariancja) | suma meczu przy potwierdzonych bramkarzach i stabilnych średnich obu stron |
| koszykówka | suma / handicap przy liście kontuzji (game-time decision), back-to-back, odpoczynek gwiazd; kwarty | suma przy pełnych składach i zgodnym tempie obu drużyn |
| siatkówka | sety / punkty przy rotacji szóstki, meczu pucharowym „między meczami ligowymi”; seria porażek | handicap setowy przy wyraźnej różnicy klas i pełnym składzie |
| CS2 | zwycięzca przy świeżej porażce / serii porażek, zmianie składu (stand-in), niepewnej puli map; mapy / rundy z jednej mapy | seria faworyta przy stabilnym składzie i zgodnej puli map |

### A2. Populacja

- Jednostka: **para (sekcja analizy, noga)** — sekcja z
  `runs/sofa/<d>/analyses.json` lub `analyses_slip.json` (dni 10-26..11-15)
  i noga tego meczu odczytana **w tym samym merge'u**: wpis w `reads.json` /
  `reads_slip.json` z tym samym `sofascore_event_id`, `author` i
  `read_at_utc` = `recorded_at_utc` sekcji. Ten warunek bierze tylko sekcje
  ze stemplem merge'a (`analyses.rebuild` stempluje mtime i nie dopasuje się).
- Sekcja z `recorded_at_utc` < kickoff nogi (`kickoff_utc` z `11_coupon.json`
  tego dnia); bez kickoffu albo od kickoffu — wypada.
- Noga rozliczona przez ledger: `13_results.json` dnia (klucz
  `coupon_results.key_of`; dla sportów dopasowanie po (mecz, rynek, okres,
  podmiot, linia, kierunek), niejednoznaczne — wypada), outcome WIN / LOSS.
  Zwrot, VOID, brak oceny — wypadają. Kurs = `odds` drukowany z
  `13_results.json`, pewność = `confidence` stamtąd.
- Wszystkie sporty. **Pomiar główny: pary z werdyktem KEEP** (z tego
  merge'a). Nogi zdjęte (WATCH / NO_BET) — osobno: football / tenis oceniane
  przez `record_results.graded_confidence` (wariant `removed:reads`);
  raportowane, poza regułą.
- Policzone przed klasyfikacją (bez wyników): 11 243 pary KEEP rozliczone,
  1 518 sekcji, 11 131 różnych nóg; dev 7 529 par, hold-out 3 715.

### A3. Podział (stały)

Według daty UTC kickoffu nogi: **dev = 2026-10-26..2026-11-05**,
**hold-out = 2026-11-06..2026-11-15**.

### A4. Miara

- Główna: realizacja − 1/kurs (kurs drukowany). Raportowane też:
  realizacja − pewność i ROI płaskie po kursie drukowanym.
- Różnica **CHWIEJNA − STABILNA** (BRAK_PODSTAW poza kontrastem, raportowane).
- Bootstrap po meczach (klaster = (dzień, mecz); wszystkie pary meczu
  losowane razem), 2 000 losowań, ziarno 1, przedział percentylowy 95%.
  Osobno per sport i razem.

### A5. Reguła przejścia (zamrożona)

PASSED, gdy jednocześnie:

1. hold-out: CHWIEJNA − STABILNA (realizacja − 1/kurs) < 0 i górna granica
   95% przedziału < 0;
2. dev: ta sama różnica < 0 (punktowo);
3. hold-out: ≥ 150 par KEEP z etykietą CHWIEJNA.

W przeciwnym razie **NOT_PASSED**. Żadnego drugiego podejścia z innym
progiem, definicją, populacją czy podziałem na tych danych — zmiana
definicji to nowy test na nowych danych.

### A6. Kontrola ceny

Ta sama różnica w pasmach kursu: < 1.10 / 1.10–1.30 / 1.30–1.60 / 1.60–2.20
/ ≥ 2.20 (krawędź dolna w paśmie), oraz różnica stratyfikowana po pasmach
(średnia różnic w pasmach ważona liczbą par CHWIEJNA w paśmie, ten sam
bootstrap). Warunek dodatkowy dla wniosku o usuwanie (D): stratyfikowana
różnica na hold-oucie < 0 punktowo. Bez niego — nawet przy PASSED — wynik
jest raportowany jako możliwie cenowy i usuwanie nie jest proponowane.

### A7. Ślepość klasyfikatora

Klasyfikator (agenci Sonnet w Workflow, bez sieci) widzi wyłącznie: tekst
sekcji (sprzed meczu), sport, rynek nogi w słowach Superbetu
(`superbet_market: superbet_selection`), linię, kierunek, kurs drukowany i
klucz nogi. Nie widzi `13_results.json`, ledgera, wyniku ani niczego po
kickoffie. Wynik dokleja dopiero `scripts/sofa/measure_stability_label.py`.
Wejście: `data/stability_retro_2026-11-16/input/shard_*.jsonl`, wyjście:
`data/stability_retro_2026-11-16/labels.jsonl`. Każda noga dostaje
dokładnie jedną etykietę na parę; brakujące etykiety raportowane, nie
uzupełniane po fakcie.

### A8. Test prospektywny T-STABILITY-LABEL-FORWARD

Od 2026-11-17 00:00Z etykieta pochodzi od samego analityka (pole `stability`
w odczycie). Ta sama populacja (KEEP, rozliczone, sekcja sprzed kickoffu),
ta sama miara i reguła A5 (bez warunku dev), `required_n` = 300 par
CHWIEJNA. Zatrzymanie: ocena raz, przy pierwszych 300 parach CHWIEJNA w
kolejności kickoffu; później zebrane — osobno. Wcześniejsze zajrzenie nie
zmienia reguły.

---

## B. Wynik klasyfikacji wstecz — **NOT_PASSED**

**Etykieta „chwiejna” nie wybiera nóg, które realizują się poniżej swojej
ceny.** Hold-out (11-06..11-15): CHWIEJNA − STABILNA (trafność − 1/kurs)
**+0,3 pp [−3,0, +3,8]** na 1 935 vs 1 762 parach KEEP; dev (10-26..11-05)
−1,3 pp [−3,5, +1,1]; po stratyfikacji pasmami kursu (A6) hold-out
+0,3 pp [−3,6, +3,8]. Reguła A5 wymaga górnej granicy hold-outu < 0 — nie
jest spełniona. Zgodnie z rejestracją: **bez drugiego podejścia** na tych
danych, przełącznik usuwania (`STABILITY_REMOVAL`) nie jest proponowany,
etykieta zostaje tylko do wyświetlania, a T-STABILITY-LABEL-FORWARD i tak
się toczy od 2026-11-17.

Co widać (opis, poza regułą):

- Nogi CHWIEJNE mają **niższą cenę** (śr. 1/kurs 0,80 vs 0,84) i niższą
  trafność (0,757 vs 0,800) — klasyfikator wybiera dłuższe kursy, a nie
  nogi gorsze od swojego kursu. W paśmie 1.10–1.30 (najliczniejszym)
  różnica wynosi +0,1 pp [−3,4, +3,9] na hold-oucie.
- Trafność − pewność: CHWIEJNA −1,7 pp, STABILNA −0,1 pp (razem) — to ta
  sama różnica ceny (pewność dłuższych kursów jest mniej trafna), nie
  zysk na decyzji.
- Per sport nic nie przechodzi; najsilniejsze punktowo (CS2 dev −10,9 pp
  [−29,5, +4,3], tenis hold-out −4,2 [−13,6, +5,7]) mają przedziały przez 0
  i przeciwny znak w drugiej połowie lub n < 150. Kategorie (MOTYWACJA
  −7,1 pp, ZMIENNOŚĆ −5,6 pp) to opis bez przedziałów i bez kontroli ceny.
- Nogi zdjęte przez odczyty (WATCH / NO_BET, 137 par): te, które
  klasyfikator nazwał CHWIEJNYMI, realizowały się +2,1 pp **nad** swoją
  ceną — zdejmowanie nóg chwiejnych nie usuwało przegranych (zgodne z
  audytem 10-26).

### Jakość klasyfikacji (zastrzeżenie)

Ślepota zachowana: wejście nie zawierało wyniku (sprawdzone: zero pól
`outcome` / `WIN` w partiach), agenci deklarują brak sieci i innych
plików; jedna zgłoszona „informacja o wyniku” (partia 01, sekcja Voreas –
Fragolad 11-06) to wynik **poprzedniego** meczu tej pary w weekendowej
serii SV League, sprzed kickoffu nogi — nie wyciek. Wykonanie odbiegło od
instrukcji „każda noga osobno”: wszyscy agenci oceniali sekcję całościowo
i nadawali etykiety nogom regułami (regex po słowach Superbetu, wyjątki per
noga), partia 06 przyznaje, że skracała część akapitów. Etykieta jest więc
bliżej „osądu meczu z rozróżnieniem rodzin rynku” niż osądu każdej nogi.
Pomiar mierzy ten właśnie osąd; test prospektywny mierzy etykietę
analityka, który zna mecz i nogę. Podział etykiet: STABILNA 5 676,
CHWIEJNA 5 659, BRAK_PODSTAW 56; 10 agentów Sonnet, ok. 2,3 mln tokenów.

Odstępstwo od A2 (bez wpływu): 16 par KEEP na dev dotyczy nóg, które zdjął
inny odczyt — skrypt ocenił je przez `removed:reads` zamiast
`13_results.json`; niezależne przeliczenie tylko z `13_results.json` daje
ten sam Δ dev −1,3 pp i identyczny hold-out.

Pliki: wejście `data/stability_retro_2026-11-16/input/shard_*.jsonl`,
etykiety `labels.jsonl`, łączenie `pairs.jsonl`, raport `report.md` /
`report.json` (poza gitem). Skrypt: `scripts/sofa/measure_stability_label.py
measure --from 2026-10-26 --to 2026-11-15 --labels ... --pairs ...
--db-path data/sofa.db`.

### Pomiar (2026-10-26..2026-11-15, pary KEEP rozliczone)

**Werdykt A5: NOT_PASSED** — hold-out Δ +0.3 pp [-3.0, +3.8], dev Δ -1.3 pp [-3.5, +1.1], CHWIEJNA na hold-oucie 1935 (min 150); stratyfikowana po pasmach (A6) +0.3 pp [-3.6, +3.8]; wniosek o usuwanie możliwy: nie.

Pominięte: {"unlabelled_pairs": 0, "ungraded_pairs": 3}

#### Razem

| grupa | etykieta | n | mecze | traf. | 1/kurs | pewność | traf.−1/kurs | traf.−pewność | ROI | Δ CH−ST (traf.−1/kurs) | 95% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| dev | STABILNA | 3911 | 617 | 0.804 | 0.836 | 0.801 | -3.2 | +0.3 | -3.8% |  |  |
| dev | CHWIEJNA | 3595 | 749 | 0.757 | 0.802 | 0.778 | -4.5 | -2.1 | -5.7% | -1.3 | [-3.5, +1.1] |
| dev | BRAK_PODSTAW | 36 | 18 | 0.833 | 0.782 | 0.777 | +5.2 | +5.6 | +7.0% |  |  |
| hold-out | STABILNA | 1762 | 332 | 0.790 | 0.837 | 0.798 | -4.7 | -0.8 | -5.7% |  |  |
| hold-out | CHWIEJNA | 1935 | 413 | 0.757 | 0.801 | 0.767 | -4.4 | -1.0 | -5.4% | +0.3 | [-3.0, +3.8] |
| hold-out | BRAK_PODSTAW | 12 | 6 | 0.417 | 0.795 | 0.797 | -37.9 | -38.0 | -48.4% |  |  |
| razem | STABILNA | 5673 | 949 | 0.800 | 0.836 | 0.800 | -3.7 | -0.1 | -4.4% |  |  |
| razem | CHWIEJNA | 5530 | 1162 | 0.757 | 0.802 | 0.775 | -4.5 | -1.7 | -5.6% | -0.8 | [-2.6, +1.1] |
| razem | BRAK_PODSTAW | 48 | 24 | 0.729 | 0.785 | 0.782 | -5.6 | -5.3 | -6.9% |  |  |

#### Per sport (hold-out)

| grupa | etykieta | n | mecze | traf. | 1/kurs | pewność | traf.−1/kurs | traf.−pewność | ROI | Δ CH−ST (traf.−1/kurs) | 95% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| basketball | STABILNA | 7 | 5 | 0.714 | 0.762 | 0.766 | -4.8 | -5.2 | -5.7% |  |  |
| basketball | CHWIEJNA | 50 | 23 | 0.640 | 0.708 | 0.730 | -6.8 | -9.0 | -9.2% | -2.0 | [-30.7, +35.3] |
| cs2 | STABILNA | 10 | 2 | 1.000 | 0.887 | 0.839 | +11.3 | +16.1 | +13.0% |  |  |
| cs2 | CHWIEJNA | 18 | 4 | 0.833 | 0.828 | 0.792 | +0.5 | +4.2 | +3.7% | -10.7 | [-21.2, +22.3] |
| football | STABILNA | 1099 | 144 | 0.776 | 0.838 | 0.791 | -6.1 | -1.5 | -7.3% |  |  |
| football | CHWIEJNA | 979 | 161 | 0.762 | 0.814 | 0.766 | -5.2 | -0.4 | -6.5% | +1.0 | [-3.4, +5.5] |
| football | BRAK_PODSTAW | 2 | 2 | 0.000 | 0.755 | 0.743 | -75.5 | -74.3 | -100.0% |  |  |
| hockey | STABILNA | 213 | 46 | 0.803 | 0.855 | 0.811 | -5.3 | -0.9 | -6.0% |  |  |
| hockey | CHWIEJNA | 462 | 64 | 0.779 | 0.817 | 0.776 | -3.7 | +0.3 | -4.4% | +1.5 | [-5.7, +10.1] |
| hockey | BRAK_PODSTAW | 6 | 3 | 0.500 | 0.823 | 0.793 | -32.3 | -29.3 | -39.0% |  |  |
| tennis | STABILNA | 244 | 51 | 0.824 | 0.846 | 0.798 | -2.2 | +2.6 | -2.9% |  |  |
| tennis | CHWIEJNA | 202 | 55 | 0.733 | 0.797 | 0.753 | -6.4 | -2.1 | -8.5% | -4.2 | [-13.6, +5.7] |
| volleyball | STABILNA | 189 | 84 | 0.804 | 0.803 | 0.823 | +0.1 | -1.9 | -0.3% |  |  |
| volleyball | CHWIEJNA | 224 | 106 | 0.732 | 0.733 | 0.776 | -0.1 | -4.3 | +0.3% | -0.2 | [-10.0, +8.9] |
| volleyball | BRAK_PODSTAW | 4 | 1 | 0.500 | 0.774 | 0.830 | -27.4 | -33.0 | -36.8% |  |  |

#### Per sport (dev)

| grupa | etykieta | n | mecze | traf. | 1/kurs | pewność | traf.−1/kurs | traf.−pewność | ROI | Δ CH−ST (traf.−1/kurs) | 95% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| basketball | STABILNA | 16 | 11 | 0.500 | 0.730 | 0.751 | -23.0 | -25.1 | -33.0% |  |  |
| basketball | CHWIEJNA | 142 | 54 | 0.493 | 0.662 | 0.720 | -16.9 | -22.7 | -25.6% | +6.0 | [-31.5, +35.8] |
| basketball | BRAK_PODSTAW | 2 | 1 | 1.000 | 0.670 | 0.713 | +33.0 | +28.7 | +49.5% |  |  |
| cs2 | STABILNA | 38 | 9 | 0.789 | 0.847 | 0.800 | -5.8 | -1.0 | -6.2% |  |  |
| cs2 | CHWIEJNA | 88 | 16 | 0.591 | 0.758 | 0.765 | -16.7 | -17.4 | -22.6% | -10.9 | [-29.5, +4.3] |
| football | STABILNA | 3070 | 371 | 0.802 | 0.836 | 0.800 | -3.4 | +0.2 | -4.0% |  |  |
| football | CHWIEJNA | 2230 | 386 | 0.777 | 0.814 | 0.783 | -3.7 | -0.7 | -4.4% | -0.3 | [-3.0, +2.6] |
| football | BRAK_PODSTAW | 20 | 14 | 0.750 | 0.805 | 0.788 | -5.5 | -3.8 | -7.1% |  |  |
| hockey | STABILNA | 339 | 79 | 0.853 | 0.854 | 0.807 | -0.1 | +4.5 | -0.1% |  |  |
| hockey | CHWIEJNA | 648 | 101 | 0.781 | 0.820 | 0.781 | -3.9 | +0.0 | -4.7% | -3.8 | [-9.3, +2.0] |
| hockey | BRAK_PODSTAW | 7 | 1 | 1.000 | 0.784 | 0.778 | +21.6 | +22.2 | +28.0% |  |  |
| tennis | STABILNA | 344 | 94 | 0.788 | 0.838 | 0.806 | -5.1 | -1.8 | -6.0% |  |  |
| tennis | CHWIEJNA | 366 | 125 | 0.765 | 0.795 | 0.776 | -3.0 | -1.1 | -3.6% | +2.1 | [-4.4, +9.1] |
| volleyball | STABILNA | 104 | 53 | 0.817 | 0.799 | 0.815 | +1.9 | +0.2 | +3.4% |  |  |
| volleyball | CHWIEJNA | 121 | 67 | 0.678 | 0.713 | 0.760 | -3.5 | -8.3 | -5.9% | -5.4 | [-17.8, +6.0] |
| volleyball | BRAK_PODSTAW | 7 | 2 | 0.857 | 0.746 | 0.763 | +11.1 | +9.4 | +14.0% |  |  |

#### Pasma kursu (hold-out)

| grupa | etykieta | n | mecze | traf. | 1/kurs | pewność | traf.−1/kurs | traf.−pewność | ROI | Δ CH−ST (traf.−1/kurs) | 95% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| <1.10 | STABILNA | 104 | 77 | 0.865 | 0.917 | 0.862 | -5.2 | +0.3 | -5.7% |  |  |
| <1.10 | CHWIEJNA | 51 | 48 | 0.902 | 0.917 | 0.859 | -1.5 | +4.3 | -1.7% | +3.7 | [-7.1, +13.9] |
| 1.10-1.30 | STABILNA | 1426 | 298 | 0.801 | 0.849 | 0.805 | -4.8 | -0.5 | -5.7% |  |  |
| 1.10-1.30 | CHWIEJNA | 1346 | 320 | 0.785 | 0.832 | 0.785 | -4.8 | -0.0 | -5.7% | +0.1 | [-3.4, +3.9] |
| 1.10-1.30 | BRAK_PODSTAW | 8 | 4 | 0.625 | 0.815 | 0.807 | -19.0 | -18.2 | -22.6% |  |  |
| 1.30-1.60 | STABILNA | 230 | 127 | 0.691 | 0.729 | 0.722 | -3.8 | -3.1 | -5.3% |  |  |
| 1.30-1.60 | CHWIEJNA | 507 | 267 | 0.680 | 0.720 | 0.715 | -4.0 | -3.4 | -5.4% | -0.2 | [-7.3, +6.7] |
| 1.30-1.60 | BRAK_PODSTAW | 4 | 3 | 0.000 | 0.756 | 0.776 | -75.6 | -77.6 | -100.0% |  |  |
| 1.60-2.20 | STABILNA | 2 | 2 | 0.500 | 0.612 | 0.743 | -11.2 | -24.3 | -17.0% |  |  |
| 1.60-2.20 | CHWIEJNA | 31 | 28 | 0.581 | 0.561 | 0.731 | +1.9 | -15.0 | +1.4% | +13.1 | – |

#### Pasma kursu (dev)

| grupa | etykieta | n | mecze | traf. | 1/kurs | pewność | traf.−1/kurs | traf.−pewność | ROI | Δ CH−ST (traf.−1/kurs) | 95% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| <1.10 | STABILNA | 193 | 145 | 0.902 | 0.917 | 0.864 | -1.6 | +3.7 | -1.7% |  |  |
| <1.10 | CHWIEJNA | 112 | 89 | 0.857 | 0.917 | 0.863 | -6.0 | -0.6 | -6.6% | -4.4 | [-13.2, +5.0] |
| 1.10-1.30 | STABILNA | 3225 | 544 | 0.811 | 0.848 | 0.807 | -3.6 | +0.4 | -4.3% |  |  |
| 1.10-1.30 | CHWIEJNA | 2479 | 558 | 0.791 | 0.835 | 0.795 | -4.4 | -0.4 | -5.3% | -0.8 | [-3.5, +1.7] |
| 1.10-1.30 | BRAK_PODSTAW | 22 | 14 | 0.864 | 0.831 | 0.805 | +3.2 | +5.9 | +3.9% |  |  |
| 1.30-1.60 | STABILNA | 481 | 270 | 0.721 | 0.734 | 0.736 | -1.2 | -1.5 | -1.5% |  |  |
| 1.30-1.60 | CHWIEJNA | 937 | 520 | 0.672 | 0.718 | 0.728 | -4.5 | -5.5 | -6.6% | -3.3 | [-8.5, +2.3] |
| 1.30-1.60 | BRAK_PODSTAW | 14 | 8 | 0.786 | 0.704 | 0.733 | +8.2 | +5.2 | +11.9% |  |  |
| 1.60-2.20 | STABILNA | 12 | 11 | 0.583 | 0.587 | 0.757 | -0.4 | -17.3 | +1.3% |  |  |
| 1.60-2.20 | CHWIEJNA | 64 | 47 | 0.562 | 0.577 | 0.726 | -1.5 | -16.4 | -2.9% | -1.1 | [-32.5, +34.0] |
| >=2.20 | CHWIEJNA | 3 | 3 | 0.000 | 0.377 | 0.729 | -37.7 | -72.9 | -100.0% | – | – |

#### Autor (razem)

| grupa | etykieta | n | mecze | traf. | 1/kurs | pewność | traf.−1/kurs | traf.−pewność | ROI | Δ CH−ST (traf.−1/kurs) | 95% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| analyst | STABILNA | 5669 | 948 | 0.800 | 0.836 | 0.800 | -3.7 | -0.1 | -4.4% |  |  |
| analyst | CHWIEJNA | 5528 | 1161 | 0.757 | 0.802 | 0.775 | -4.4 | -1.7 | -5.6% | -0.8 | [-2.5, +1.1] |
| analyst | BRAK_PODSTAW | 48 | 24 | 0.729 | 0.785 | 0.782 | -5.6 | -5.3 | -6.9% |  |  |
| verifier | STABILNA | 4 | 1 | 0.500 | 0.833 | 0.770 | -33.3 | -27.0 | -43.0% |  |  |
| verifier | CHWIEJNA | 2 | 1 | 0.500 | 0.867 | 0.792 | -36.7 | -29.2 | -44.5% | -3.4 | [-3.4, -3.4] |

#### CHWIEJNA wg kategorii (razem; opis, poza regułą)

| kategoria | n | traf.−1/kurs | ROI |
|---|---|---|---|
| DANE | 761 | -2.7 | -3.3% |
| FORMA | 354 | -3.9 | -4.9% |
| INNE | 43 | -3.7 | -4.1% |
| MOTYWACJA | 250 | -7.1 | -8.9% |
| ROTACJA | 610 | -3.3 | -3.9% |
| SKŁAD | 1210 | -3.5 | -4.6% |
| ZMIENNOŚĆ | 2302 | -5.6 | -7.2% |

#### Nogi zdjęte przez odczyt (WATCH / NO_BET; poza regułą)

| grupa | etykieta | n | mecze | traf. | 1/kurs | pewność | traf.−1/kurs | traf.−pewność | ROI | Δ CH−ST (traf.−1/kurs) | 95% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| zdjęte | STABILNA | 3 | 3 | 1.000 | 0.825 | 0.751 | +17.5 | +24.9 | +21.3% |  |  |
| zdjęte | CHWIEJNA | 126 | 66 | 0.802 | 0.781 | 0.768 | +2.1 | +3.4 | +2.0% | -15.4 | [-23.2, -7.1] |
| zdjęte | BRAK_PODSTAW | 8 | 8 | 1.000 | 0.821 | 0.768 | +17.9 | +23.2 | +22.2% |  |  |



---

## C. Wdrożenie (tylko wyświetlanie, od 2026-11-16 17:00Z)

- `contracts.LegRead`: opcjonalne `stability` (`STABILNA` / `CHWIEJNA` /
  `BRAK_PODSTAW`) i `stability_reason` (wymagane razem).
- `epochs.STABILITY_LABEL_FROM_UTC` = 2026-11-16 17:00Z (operator: ten sam
  dzień, ok. godzinę po wdrożeniu); `report_check.stability_findings`
  (`STABILNOŚĆ:`) — hook odsyła raport, `merge_reads.py` go odrzuca; raport
  wcześniejszego dnia zachowuje swoje reguły.
- Kontrakt: `sofa-analysis-core` (SKILL.md „Verdicts”, `veto-contract.md`),
  `sofa-pipeline`, skille piłkarski / tenisowy / sportowy, `sofa-verifier.md`
  (weryfikator ocenia sam i może się nie zgodzić). Agenci wczytują definicje
  przy starcie sesji — w już otwartej sesji wymaganie dociera z komunikatu
  hooka.
- Widok: PDF (`read_label` + linia stabilności), HTML (znacznik, filtry
  „chwiejne” / „stabilne”), /kupon md (kolumna „czytana”: `KEEP · chwiejna:
  <powód>`).
- Rozliczenie: `record_results.py` `by_stability` (wiersz dziennika, gdy
  nogi niosą etykietę), audyt 7i — tabela stabilności,
  `measure_read_value.py --all-sports` (KEEP według stabilności, sporty).
- `epochs.STABILITY_REMOVAL_FROM_UTC` = None — **nie proponowany** (B
  NOT_PASSED). Test prospektywny T-STABILITY-LABEL-FORWARD od 2026-11-17.
