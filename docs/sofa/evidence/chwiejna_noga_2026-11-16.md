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

## B. Wynik klasyfikacji wstecz

(uzupełniane po pomiarze)
