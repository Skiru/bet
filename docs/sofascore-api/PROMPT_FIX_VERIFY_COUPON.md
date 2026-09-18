# Prompt: naprawić usterki drugiego przebiegu, zweryfikować, wyprodukować kupon i rozebrać go na części

Napisany 2026-09-18, po drugim przebiegu `sofa` na żywo. Do wklejenia w świeżą
sesję. Zakłada `main` z commitem `b0736355` (findings F13–F32) i **niczym
więcej** — żadna z opisanych usterek nie jest jeszcze naprawiona w kodzie.

Dwie rzeczy są w nim celowe i łatwo je zepsuć, zmieniając kolejność:
**F18 idzie pierwsze, choć blokerem jest F32** (bez diagnostyki nie widać
skutków pozostałych poprawek — w drugim przebiegu ukryła błąd P0 na trzy
godziny), oraz **przy trzech znaleziskach oczywista poprawka jest gorsza od
właściwej** (F25, F28, F30) — dlatego każda ma jawne ostrzeżenie.

---

## Źródło prawdy

`docs/sofascore-api/FIRST_RUN_FINDINGS.md` — przeczytaj **w całości**, zanim
cokolwiek zmienisz. Na końcu jest tabela triage'u; zacznij od niej, ale nie
poprzestawaj na niej, bo w pełnych wpisach są zastrzeżenia, które decydują
o kształcie poprawki. Plan to `docs/sofascore-api/PLAN_SOFA_PIPELINE.md`.

Nie ufaj pamięci ani podsumowaniom — wszystko poniżej ma oparcie we wpisach
F13–F32 i tam są dowody.

## Zasady pracy (obowiązują cały czas)

- **Każda poprawka ma test, który failuje na starym kodzie z właściwego
  powodu.** Nie „pilnuje zachowania na przyszłość" — failuje, bo stary kod
  był zepsuty. Przy każdym teście napisz uczciwie, który to przypadek;
  wpisy F13–F32 mają gotowe propozycje testów z konkretnymi wartościami.
- **Czego nie zmierzyłeś, oznaczaj `PODEJRZENIE`.** Nie podnoś na
  `POTWIERDZONE` bez pomiaru.
- **Bramki przed każdym commitem:** `pytest tests/sofa` (229 przechodziło
  przed poprawkami — podaj nową liczbę), `ruff check`, `mypy --strict` na
  `src/bet/sofa` i `scripts/sofa`. `ruff` nie łapie duplikatu w enumie — po
  zmianie w enum uruchom import.
- **Commituj małymi krokami**, jedna usterka na commit, z numerem F w tytule.
- Aktualizuj `FIRST_RUN_FINDINGS.md`: przenoś naprawione do „Zamknięte"
  z nazwą testu. Jeśli pomiar przy naprawie pokaże coś innego, niż wpis
  twierdzi — **popraw wpis** i zostaw ślad, że był błędny.

## Czego nie robić

- Nie podnoś `SOFA_TARGET_RPS` ani współbieżności. Sufit i tak leży
  w userscripcie (`MIN_INTERVAL_MS = 350`, pętla szeregowa) — zmierzone.
  550 req/s zamknęło nam API 2026-09-17.
- Nie wracaj do `curl_cffi` / transportu `direct`. Zamknięte, zmierzone.
- Nie startuj backfillu (E10).
- Nie dodawaj `sportId=190` (piłka kobiet), dopóki F16 i F25 nie są
  naprawione — dziś dosypałoby to samych nietrafień.

---

# Część 1 — naprawy, w tej kolejności

## 1.1 Najpierw widoczność i podstawy

1. **F18** — `flush=True` przy `SOFA_SUMMARY`; `run_pipeline` wypisuje werdykt
   **każdego** etapu na `stderr`, nie tylko przy `FAILED`.
2. **F13** — `SOFA_RUN_ID` ustawiany **przed** pętlą etapów, nie po; nowy
   identyfikator na każdy przebieg (nie `setdefault`), opcja `--run-id`,
   ten sam identyfikator w `SOFA_SUMMARY`.
3. **F22 + F20** — `stage` przychodzi od wywołującego, nie jest przyszyty do
   metody klienta. Dotyczy `SofascoreClient.entity_events` (dziś na sztywno
   `"RESOLVE"`) **i** `SuperbetClient` (dziś na sztywno `"BOARD"`). Dodaj
   test-strażnik: żadna publiczna metoda klienta nie przekazuje literału
   etapu do `_execute`.
   *Dlaczego tak wysoko:* ta jedna usterka wygenerowała trzy błędne
   twierdzenia w trakcie audytu. Bez niej każdy pomiar kosztu etapu kłamie.
4. **F14** — `migrate()` w konstruktorze `SofaCache` (konstruktor jest
   bezpieczniejszy niż `run_*.py`, bo nie da się go ominąć). Test: `SofaCache`
   na ścieżce do nieistniejącego pliku obsługuje odczyt i zapis **każdej**
   z pięciu tabel; plus strażnik, że każda tabela z `migrate()` istnieje po
   zbudowaniu cache'u. **Uwaga:** na maszynie operatora brakująca tabela
   została dołożona ręcznie, więc lokalnie usterka się nie objawi — sprawdzaj
   na świeżym pliku bazy.
5. **F15** — `run_pipeline.run_stage` łapie `Exception`, loguje z `run_id`,
   zwraca 2. Zapis artefaktu w `run_resolve.py` przenieś do `finally` (dziś
   F5 nie obowiązuje dla wyjątku innego niż `CircuitOpenError`).

## 1.2 Bloker kuponu

6. **F32** — `odds_items = (odds_data or {}).get("odds") or []`.
   Bramka `"odds" not in odds_data` nie łapie `"odds": null`, a `null` jest
   postacią **dominującą** (zmierzone: 68 na 69 fixture'ów) — tak Superbet
   opisuje mecz, którego już nie wycenia.
   **Wyciągnij to do jednej funkcji** używanej przez `offer.py` **i**
   `samples.py` — dziś są dwie kopie tej samej bramki, jedna poprawna
   (`samples.py:79`), jedna nie, i to ta druga zabrała cały dzienny kupon.
   Test: fixture z `{"odds": None}` daje ofertę z zerem szczebli i **nie**
   przerywa przetwarzania pozostałych fixture'ów.

## 1.3 Poprawność wyceny — tu oczywista poprawka jest zła

7. **F29** — `fold()` nie usuwa liter bez rozkładu NFD. Dodaj mapę
   `{"ł":"l","đ":"d","ø":"o","ı":"i","æ":"ae","ß":"ss","þ":"th"}` **przed**
   normalizacją. To odblokowuje **osiem** martwych odwzorowań (m.in.
   `shots_total`, `shots_on_target_total`, `double_faults_total` i ich
   warianty per-strona). Dołóż wzorzec na per-drużynowe połówki
   (`goals_1h_for` / `goals_2h_for` **istnieją** w `FOOTBALL_METRICS` i są
   nieużywane).
   **Niezależnie** zabezpiecz `determine_side`: subject, z którego po
   usunięciu nazwy drużyny zostaje nierozpoznany tekst („1.połowa - "), musi
   być odrzucony, a nie dopasowany na 73,2 przy progu 70. `fold()` naprawia to
   u źródła, ale ta bramka jest ostatnią linią obrony i dziś przecieka przy
   dłuższych nazwach drużyn (678 z 1 160 kombinacji, 232 z 290 fixture'ów).
   Weryfikacja: **15 z 30 metryk nie powstało ani raz** w 484 fixture'ach.
   Po poprawce policz to samo. Pięć z tych piętnastu ma inne przyczyny
   i **nie są usterką** — patrz wpis.

8. **F25** — nie naprawiaj przez sufiks w nazwie drużyny. Sofascore **nie**
   oznacza drużyn kobiecych konsekwentnie (encja 296052 nazywa się „IF
   Gnistan", a gra wyłącznie w rozgrywkach kobiecych). Zrób dwie bramki:
   - **płeć z `competition_name`**, nie z nazwy drużyny. Sprawdzone na
     danych z 2026-09-18: łapie dokładnie ten jeden rozjazd, **zero**
     fałszywych alarmów (285 zgodnych męskich, 4 kobiece).
   - **orientacja stron**: `side_a/side_b` Superbetu vs `home/away`
     Sofascore. Sprawdzone: 483 z 484 zgodne, 0 niejednoznacznych,
     odwrócenie rozstrzygnięte stosunkiem 200,0 do 54,5.
     Ta bramka ma **własną wartość**: bez niej rynki per-drużyna mogą być
     przypisane odwrotnie nawet przy poprawnie zidentyfikowanym meczu.
   **Nie ścinaj globalnie okna ±24 h.** W piłce ±6 h byłoby darmowe (mediana
   rozjazdu 0 min), ale w tenisie rozjazdy ośmiogodzinne są legalne i masowe
   (F26). Okno musi zależeć od sportu.

9. **F16** — ujednolić marker płci: `(K)`, `(W)`, `(F)`, `Women`, `Kobiety` do
   jednej postaci. Lepiej: wyciąć marker z nazwy i przenieść do kolumny
   `gender` w `sofa_entity`, wchodzącej do klucza — wtedy drużyna kobiet
   i mężczyzn nie pomylą się nawet przy zgodnym kickoffie, co domyka
   resztkowe ryzyko z F25.

10. **F28** — **nie** dodawaj `hitWoodwork` do tożsamości na sztywno.
    Zmierzone trzy warianty: dzisiejszy blokuje 30,5%, „plus poprzeczka"
    12,1%, **tolerancja `abs(total − base) <= hitWoodwork` — 1,4%**.
    Sofascore jest niekonsekwentny co do podwójnego liczenia (reszty ujemne
    w 73 przypadkach), więc żadna tożsamość dokładna nie jest powszechnie
    prawdziwa. Użyj tolerancji.
    Testy z prawdziwych payloadów: `total=8, on=3, off=3, blocked=1, wood=1`
    musi **przejść**; `total=10, on=9, off=1, blocked=1, wood=0` (event
    `14195525`) musi być **zablokowany**.
    Po poprawce sprawdź, czy zniknęło obciążenie kierunkowe — dziś odrzucane
    mają medianę strzałów 25 vs 23 i narożnych 10 vs 9, czyli wypadają mecze
    ofensywne.

11. **F30** — wyłącz podłogę Poissona dla metryk, które **nie są** licznikami
    zdarzeń niezależnych: `sets_total`, `tiebreaks_total`, `xg_*`. Zmierzone:
    podłoga nie wiąże ani razu dla 26 metryk, gdzie jest uzasadniona, i wiąże
    3,34× dla `sets_total`, gdzie jest bezsensowna.
    **Ale to usuwa tylko 12 z 16 punktów błędu.** Pozostałe 4 pp zostają, bo
    dla zmiennej dwuwartościowej (2 albo 3 sety) rozkład normalny jest złym
    modelem. Prawda empiryczna: 0,2870 (252/878). Zaproponuj operatorowi
    decyzję: częstość empiryczna, model set-by-set, albo wyłączenie rynku.
    **Nie udawaj, że zmiana wariancji to naprawa.**
    Kontekst: dziś ten błąd nie wchodzi do kuponu, bo 16 z 16 drabin
    `sets_total` ma jeden szczebel i bramka drabiny wymusza `LEAN`. Na BO5
    (Wielki Szlem) kwotowane są 2,5 i 3,5 — wtedy staje się żywy.

12. **F21** — ponowienie w `_execute` łapie `RequestsError` z `curl_cffi`,
    a most rzuca `ProviderError`, więc ponowień nie ma od 2026-09-17.
    Wprowadź `TransportError` rzucany przez oba transporty i ponawiaj po nim;
    `ProviderError` zostaw na błędy semantyczne. Rozważ timeout — dziś 30 s
    przy medianie odpowiedzi 150 ms.
    Test: transport rzuca raz, potem zwraca 200 → `_execute` zwraca dane
    i wykonał **dwa** wywołania.

## 1.4 Marnotrawstwo i diagnostyka

13. **F17** — cache negatywnej odpowiedzi listingu, **z krótkim TTL** (dzień,
    nie wiecznie — `events/next` zmienia się z natury; wieczne zapamiętanie
    zamieni marnotrawstwo na cichą lukę, czyli gorszy błąd). Osobno: dla
    tenisa nie wywołuj `events/next` wcale — zmierzone 179/179 to 404,
    a `events/last` dla tenisa niesie też mecze `notstarted` (179 w cache'u).
14. **F26** — bramka czasowa kuponu musi używać **czasu Superbetu**, nie
    Sofascore. To Superbet przyjmuje zakład. Zapisz rozjazd w artefakcie
    (`kickoff_disagreement_h`) i traktuj > 2 h jako sygnał.
15. **F27** — przy dwóch listingach tego samego meczu nie nadpisuj ceny
    („ostatni wygrywa"). Rozstrzygaj jawnie, zapisz obie, podnieś sygnał przy
    rozjeździe. Unia rynków jest dobra — problemem jest tylko kolizja.
16. **F24** — przekazuj przez most nagłówki diagnostyczne (`retry-after`,
    `x-ratelimit-*`, `server-timing`, `age`, `x-cache`) do wiersza logu.
17. **F19** — zdecyduj i **napisz w docstringu prawdę**: albo usuń
    przedsamplowy OFFER (dziś nie ma odbiorcy), albo niech SAMPLES czyta
    `04_offer.json` zamiast pytać Superbet po raz drugi (~600 żądań/dzień).
18. **F31** — użyj `MAX_PER_MECHANISM_FAMILY_PER_FIXTURE` albo je usuń;
    `assert row.surplus is not None` zamień na jawne `DroppedRow`.

## 1.5 Do decyzji operatora, nie do naprawy — zapytaj i czekaj

- **F12** — czy schodzić do U17/U19 i czwartych lig (100% braku połówek).
- **`cards_total`/`cards_for`** — żadna nazwa Superbetu na nie nie wskazuje;
  `Liczba kartek` → `cards_points_total`. Usunąć metrykę czy dorobić rynek?
- **`sets_total`** — wyceniać z błędem 4 pp czy wyłączyć (F30)?
- **`has_xg`, `best_of`** — usunąć czy przezwać (opisują pole meczu
  rozegranego / liczbę połów, nie to, co sugeruje nazwa).
- **mecze `AET`/`AP`** — 366 meczów; odrzucanie jest **słuszne** dla metryk
  zliczających (120 minut), ale gole da się odzyskać z `normaltime`.

---

# Część 2 — weryfikacja poprawek

Nie ufaj samym testom jednostkowym. Powtórz **pomiary z findings** na tych
samych danych i porównaj przed/po. Wszystko offline, na `data/sofa.db`
i artefaktach z `runs/sofa/2026-09-18/`:

| co | było | ma być |
|---|---|---|
| metryk powstających z 30 zadeklarowanych | 15 | więcej; wymień które i dlaczego reszta nie |
| meczów blokowanych przez tożsamość strzałów | 30,5% | ~1,4% |
| obciążenie odrzuconych (mediana strzałów) | 25 vs 23 | bez różnicy |
| `p_central` OVER 2,5 setów | 0,4466 | ~0,33 po podłodze; prawda 0,287 |
| rozjazd płci Superbet↔Sofascore | 1 przechodzi jako `CONFIRMED` | 0 |
| odwrócenia stron | 1 przechodzi | 0 |
| żądania `events/next` dla tenisa | 179, wszystkie 404 | 0 |
| 404 odkrywane ponownie między przebiegami | 225 | 0 w obrębie dnia |

Powtórz też kontrole, które **wyszły czysto** — mają zostać czyste: zero
przecieków z przyszłości do próbki (uruchom **prawdziwą**
`get_historical_events` z klientem rzucającym wyjątek przy próbie sieci),
zero duplikatów fixture'ów, zero debli w próbkach tenisowych, zero sparingów,
brak niemożliwych zer, `shots` > `shots_on_target` w medianach, własności
`engine.py` (komplementarność, push na liniach całkowitych, monotoniczność,
`ladder_centre` z błędem 0, `required_odds × p = marża`).

---

# Część 3 — wyprodukuj kupon

**Preflight (nie startuj, dopóki nie trzy razy OK):**

    cd ~/projects/bet
    pgrep -f bridge_server.py || nohup .venv/bin/python scripts/sofa/bridge_server.py > /tmp/sofa_bridge.log 2>&1 &
    .venv/bin/python scripts/sofa/check_bridge.py

Karta sofascore.com otwarta, userscript 2.3.0, i **w osobnym oknie na
wierzchu** — zejście karty na drugi plan spowalnia pipeline czterokrotnie
(F23, potwierdzone: opóźnienie 155 ms → 1 992 ms, gdy operator otworzył
Superbet w tej samej przeglądarce).

**Tania ścieżka — nie powtarzaj SAMPLES bez potrzeby.** `02_fixtures.json`,
`03_samples.json` i 6 731 statystyk w `sofa_event_stats` są na dysku. Jeśli
poprawki nie zmieniły semantyki próbek, wystarczy OFFER → SHEET → COUPON
(~600 wywołań do Superbetu, resztę offline). **F28 i F30 zmieniają
semantykę**, więc najpewniej trzeba przeliczyć SAMPLES — ale to będzie tanie,
bo statystyki są w cache'u i koszt to głównie Superbet.

Przy pełnym przebiegu eksportuj `SOFA_RUN_ID` i raportuj co ~2 minuty: proces
żyje, żądania i rozkład statusów, tempo, liczniki bazy. Zgłaszaj natychmiast:
serię 403, `Circuit breaker is open`, `PROVIDER_ERROR`, tempo odbiegające od
~2 req/s, brak przyrostu liczników.

---

# Część 4 — głęboka, iteracyjna weryfikacja kuponu

To właściwe zadanie, nie dodatek. Iteracyjnie: znajdź problem, napraw,
przelicz kupon, weryfikuj **od nowa**. Powtarzaj, aż pełna runda nie
wyprodukuje nowego znaleziska.

## 4.1 Struktura — czy artefakt jest spójny sam ze sobą

- Każdy wiersz kuponu istnieje w `05_sheet.json` z werdyktem `VALUE`.
- Każdy wiersz `VALUE` z arkusza jest albo w kuponie, albo w `dropped`
  z powodem. **Zero wierszy, które zniknęły w ciszy.**
- Liczby w wierszu spójne, przeliczone **niezależnie z pól samego wiersza**:
  `required_odds == marża / p_bar`, `surplus == offered_odds − required_odds`,
  `edge == p_central − market_p`, `p_bar == w·p + (1−w)·market_p` przy
  `w = n/(n+K_PRICE)`.
- **Ślad audytowy musi zgadzać się z arytmetyką wiersza** — notka w `.md` ma
  być generowana z tych samych wielkości, nie opisywana obok.
- Limity zadziałały: `MAX_SINGLES`, `MAX_PER_FIXTURE`, jedna rodzina
  mechanizmu na fixture. Sprawdź, czy któryś wiersz wypadł przez limit, mimo
  że miał większy surplus niż przyjęty.
- `UNMATCHED_VETO` raportowane, jeśli są weta.
- `UNFITTED_CONSTANTS` widoczne przy każdym wierszu, jeśli stałe nie są
  dopasowane. **Nie usuwaj tej notki** — to ona mówi, że kalibracji nie ma.

## 4.2 Logika — czy każdy wiersz zasługuje na miejsce

Dla **każdego** wiersza przejdź łańcuch wstecz i rozpisz go: mecz → encje →
próbka (ile obserwacji, z jakich meczów, jaki zakres dat) → metryka → linia →
cena. Potem **adwersaryjnie** spróbuj wywrócić wiersz:

- Czy próbka mierzy to, co bukmacher rozliczy? (zakres metryki, strona,
  połowa vs cały mecz, dogrywka)
- Czy `subject` faktycznie wskazuje stronę, którą myśli, że wskazuje? Po F29
  to najbardziej podatne miejsce.
- Czy `centre` jest wiarygodny przy tym `n`? Czy `p_low`/Laplace ograniczyły?
- Czy drabina była mierzalna, czy wiersz przeszedł bez sprawdzenia?
  (zmierzone: tylko **52,4%** drabin da się sprawdzić; `sets_total`
  i `aces_*` były **0%**)
- Czy cena jest świeża i z tej samej strony rynku?
- Czy mecz naprawdę się jeszcze nie zaczął — **według zegara Superbetu**,
  nie Sofascore (F26)?

## 4.3 Poprawność — antyselekcja, i to jest najważniejszy test

Zmierzone i potwierdzone: `coupon.py` sortuje malejąco po `surplus`, a
`surplus = offered − marża/p_bar`. Więc **im mocniej p jest zawyżone, tym
pewniej wiersz wchodzi do kuponu.** Mechanizm selekcji jest antyselektywny
wobec błędu w p. Z tego wynikają konkretne kontrole:

- **Rozkład wierszy po rynkach.** Jeśli VALUE koncentruje się w metrykach
  o najsłabszym pomiarze (mała próbka, niemierzalna drabina, brak
  kalibracji) — to nie przewaga, to artefakt. Policz to.
- **Rozkład po `sample_size`.** Przy małym `n` `bar_probability` ściąga p
  mocno do `market_p` (`w = n/(n+10)`), więc kupon przestaje mierzyć model
  i mierzy wyłącznie przewagę ceny nad zdevigowaną linią. Wiersze z n < 8
  opisz osobno i powiedz, czym one w istocie są.
- **Rozkład po lidze.** Nadreprezentacja czwartych lig i młodzieży
  (F12/F28) to sygnał, że wygrywa brak danych, nie przewaga.
- **Rozkład `surplus`.** Wiersz z ekstremalnym surplusem jest podejrzany
  **z definicji** — na płynnym rynku nie ma darmowych 40%. Każdy taki
  rozbierz ręcznie.
- **Kontrola na żywo:** dla każdego wiersza pobierz aktualną cenę
  z Superbetu i potwierdź, że rynek, linia, kierunek i cena naprawdę
  istnieją tak, jak artefakt twierdzi.

## 4.4 Raport końcowy

- ile fixture'ów przeszło każdy etap i werdykty (OK/PARTIAL/FAILED);
- ile wierszy w kuponie, w rozbiciu na rynek, ligę, `sample_size`, `surplus`;
- tabela przed/po dla pomiarów z Części 2;
- **osobno: czy F1 (breaker półotwarty), F2 (ponowienie 403 w userscripcie)
  i F11 (błąd per fixture) miały okazję się wykazać.** Jeśli przebieg poszedł
  bez zakłóceń — **powiedz wprost, że ich nie przetestowaliśmy, a nie że
  działają.** W drugim przebiegu F11 przeszło (2 z 2 timeoutów), a F1 i F2 nie
  dostały okazji: do otwarcia breakera potrzeba **trzech porażek pod rząd**
  (`record_success` zeruje licznik), a 403 nie było ani jednego w 11 748
  żądaniach;
- lista wierszy, których **nie** poleciłbyś, mimo że kupon je wybrał, wraz
  z powodem — to jest ważniejsze od listy poleconych.

---

## Uwaga końcowa

Prompt kończy się raportem i listą wierszy do odrzucenia, a **nie**
rekomendacją stawiania. Po Części 4.3 może się okazać, że kupon jest
technicznie poprawny i mimo to niewart stawiania — bo `K_CENTRE`, `K_PRICE`
i `MAX_LADDER_SIGMA` nadal nie są dopasowane do danych i każdy wiersz o tym
mówi w `UNFITTED_CONSTANTS`. Decyzja o stawce należy do operatora.
