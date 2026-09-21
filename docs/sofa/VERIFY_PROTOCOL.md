# `sofa` — protokół weryfikacji zbudowanego dnia

Obowiązująca wersja protokołu, którym pracuje agent `sofa-verifier`
i komenda `/sofa-verify`. Wywodzi się z Części 4 dokumentu
[`history/PROMPT_FIX_VERIFY_COUPON.md`](history/PROMPT_FIX_VERIFY_COUPON.md)
(2026-09-18) i **zastępuje go** — tamten był jednorazowym promptem naprawczym
i zawiera nieaktualne odniesienia.

Praca jest **iteracyjna**: znajdź problem, zgłoś, weryfikuj **od nowa**.
Powtarzaj, aż pełna runda nie wyprodukuje nowego znaleziska.

**Produktem jest lista wierszy, których NIE postawiłbyś, mimo że pipeline je
wybrał.** To ważniejsze niż lista poleconych i to jest sens tego protokołu.
Kończy się werdyktem i **żadną rekomendacją stawki**.

---

## 0. Co jest weryfikowane

**Kuponem jest PDF.** `06_coupon.json` trzyma single VALUE, których zmierzony
wynik to **−20,4%** (2026-09-20) wobec **+8,2%** PDF-a tego samego dnia.
Weryfikuj **oba** produkty i **w każdej tabeli nazwij, który jest który**.
Nazwanie pliku singli „kuponem" odwraca dzień.

---

## 1. Kontrola maszynowa

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <data>
```

Wyjście `0` = brak znalezisk, `1` = są znaleziska. Skrypt drukuje nagłówki
numerowane **4.1–4.4** — to numeracja pierwotnego promptu
(`history/PROMPT_FIX_VERIFY_COUPON.md`): jego 4.1/4.2 to sekcja 1 poniżej,
4.3 to sekcja 3, 4.4 to sekcja 5. Sprawdza trzy rzeczy:

1. **Struktura.** Każdy wiersz kuponu istnieje w `05_sheet.json` z werdyktem
   `VALUE`; każdy wiersz `VALUE` jest albo w kuponie, albo w `06_dropped.json`
   z powodem. **Zero wierszy znikających w ciszy.**
2. **Arytmetyka, przeliczona z pól samego wiersza:**
   `required_odds == 1.10 / p_bar`, `surplus == offered − required`,
   `edge == p_central − market_p`,
   `p_bar == w·(p_central − calibration_correction) + (1−w)·market_p`
   przy `w = n/(n + K_PRICE)`.
3. **Rozkłady antyselekcyjne.**

Dla dnia rozliczonego dołóż `audit_day_deep.py --date <data>` — rozbicie per
rynek i powtórkę bramek.

Poza tym sprawdź ręcznie:

- **Czy limity naprawdę wiązały.** Czy jakiś wiersz wypadł na `MAX_PER_FIXTURE`
  albo `FAMILY_SLOT_TAKEN`, mimo że miał większą przewagę niż wiersz przyjęty?
- **Policz `ABOVE_MEASURED_CEILING`.** Ta bramka odpala tam, gdzie własna
  historia rynku odmawia opisania prawdopodobieństwa, które wiersz deklaruje.
  Dzień z wieloma takimi to dzień, w którym model był pewny tam, gdzie nigdy
  go nie zweryfikowano.
- **Czy `UNFITTED_CONSTANTS` nadal stoi przy każdym wierszu.** Nigdy tego nie
  usuwaj.
- **`UNMATCHED_VETO`**, jeśli weta w ogóle były.

---

## 2. Cztery rzeczy, których audyt nie umie

Audyt sprawdza wiersz **wobec niego samego**. Wiersz, którego wszystkie pola
są wzajemnie spójne i wszystkie zbudowane na złej próbce, przechodzi go bez
zająknięcia. Dlatego dla **każdej pozycji, którą stawia PDF**, i dla **każdego
singla z nadwyżką > +0,40**:

### 2a. Odtwórz wiersz z surowych obserwacji

Wróć do `03_samples.json`, znajdź stronę, którą arkusz wycenił, i policz
ręcznie: `n`, średnią, trafienia wobec linii, daty obserwacji, przeciwników.
Potem przejdź łańcuch:

```
p        = max(0.01, p_central − max(0, calibration_correction))
w        = n / (n + K_PRICE)
p_bar    = w·p + (1 − w)·market_p
required = 1.10 / p_bar
```

**Czego nie da się odtworzyć dokładnie:** `pred_sd` nie jest zapisywane na
wierszu, więc samo `p_central` odtwarza się tylko przybliżenie z `centre`
i `sample_sd` (zmierzone: 5 z 63 wierszy poza tolerancją 0,024). To znane
ograniczenie, **nie znalezisko**.

Zamiast tego sprawdź `p_central` wobec **własnej częstości trafień próbki**:

- tenisowe `sets_total` i `games_won_for` używają częstości empirycznej, więc
  `p_central` **musi być równe** trafieniom. Rozjazd tam jest prawdziwym
  znaleziskiem;
- piłkarskie liczniki idą przez ujemny dwumianowy i różnić się **muszą** — ale
  rozjazd powyżej ~15 pp znaczy, że pracuje prior ligowy, a nie drużyna.
  Policz `n/(n+25)` i powiedz, jaką część środka naprawdę trzyma próbka.

### 2b. Czy `subject` wskazuje tę stronę, o której myśli

Najbardziej kruchy join w pipelinie. Rozwiąż go **niezależnym** matcherem,
który składa diakrytyki, wobec `home_name` / `away_name` z `02_fixtures.json`.
Wiersz `_for` po złej stronie jest niewidoczny w każdej innej kontroli.

### 2c. Dopytaj Superbet o żywą cenę

Przez `OfferFetcher` — ten sam kod, którego użył OFFER — **i** czytając
payload z kursami drugi raz ręcznie. Drugie czytanie weryfikuje twój parser
wobec niego samego. Potwierdź, że rynek, linia, kierunek i cena istnieją tak,
jak twierdzi artefakt, i że mecz nadal jest na tablicy.

### 2d. Czy mecz naprawdę się nie zaczął — na wcześniejszym zegarze

COUPON bierze `min(kickoff_utc, superbet_kickoff_utc)`. **CONFIDENCE czyta sam
zegar Sofascore.** Na ITF oba rozjeżdżają się do 11 h, a błąd biegnie w złą
stronę: mecz zakończony wygląda na nadchodzący. Sprawdź, czy któraś
postawiona noga nie siedzi dokładnie w tej szczelinie.

---

## 3. Antyselekcja — najważniejszy test

COUPON rankuje po **względnej przewadze cenowej** (`surplus / required_odds`),
a każda miara nadwyżki rośnie, gdy `p` jest **zawyżone**. Wiersze najbardziej
podatne na błąd są więc najczęściej wybierane. To własność mechanizmu, nie
hipoteza o dniu, i z niej biorą się konkretne kontrole:

- **Rozkład po rynkach.** Koncentracja VALUE w najsłabszym pomiarze (cienkie
  próbki, niemierzalne drabiny, brak własnej krzywej) to artefakt, nie
  przewaga. Policz to.
- **Rozkład po `sample_size`.** Przy małym `n` `w = n/(n+10)` ściąga `p_bar`
  mocno do `market_p`, więc kupon przestaje mierzyć model i mierzy wyłącznie
  cenę wobec jej własnej zdevigowanej linii. Wiersze z `n < 8` opisz osobno
  i powiedz, czym one w istocie są.
- **Rozkład po lidze.** Nadreprezentacja czwartych lig i młodzieży znaczy, że
  wygrywa brak danych, nie umiejętność.
- **Rozkład nadwyżki.** Powyżej **+0,40** podejrzany **z definicji** — na
  płynnym rynku nie ma darmowych 40%. Każdy taki wiersz rozbierz ręcznie.
- **Wiek próbki.** Starość i nadwyżka nie są niezależne: próbka, która
  przestała śledzić zawodnika, częściej kłóci się z bieżącą ceną, a kupon
  rankuje dokładnie po tej kłótni.

---

## 4. Potwierdzenie zewnętrzne, gdy jest możliwe

Tylko dla wierszy, w których model kłóci się z własną próbką, i **tylko po
ustaleniu punktu decyzyjnego**. Mecz, który się zaczął, nie jest przedmiotem
researchu. Tytuły i snippety **są treścią**: buduj zapytania, które nie mogą
zwrócić wyniku, a gdy wynik przecieknie — nazwij to i oznacz twierdzenie
`CANNOT VERIFY`.

**Tenisa w dużej mierze nie da się zweryfikować zewnętrznie** (statystyki
gemów ITF nie są darmowe, a tenis to zwykle 2/3 tablicy). Napisz to; nie
produkuj źródła.

---

## 5. Raport

1. Ile meczów przeszło każdy etap i werdykt **każdego** etapu.
2. Wiersze kuponu w rozbiciu na rynek, ligę, `sample_size`, nadwyżkę —
   **osobno single, osobno PDF**.
3. Tabela przed/po dla wszystkiego, co odtworzono ręcznie.
4. **Osobno: które zabezpieczenia miały okazję się wykazać.** Jeśli przebieg
   poszedł gładko, napisz wprost, że zabezpieczenia **nie przetestowano** —
   nigdy, że „działa". Otwarcie bezpiecznika wymaga **trzech** porażek pod
   rząd, a przebieg bez ani jednego 403 w jedenastu tysiącach żądań nie
   przetestował ścieżki 403.
5. **Lista wierszy, których nie postawiłbyś, mimo że pipeline je wybrał, wraz
   z powodem dla każdego.** To jest produkt.

Na koniec werdykt i **żadna rekomendacja stawki**. Kupon bywa technicznie
poprawny i mimo to niewart stawiania: `K_PRICE` i `MAX_LADDER_SIGMA` są
`NOT_FITTED` i każdy wiersz o tym mówi. Decyzja o stawce należy do operatora.
