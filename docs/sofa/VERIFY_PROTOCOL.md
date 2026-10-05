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
Od 2026-10-04 ta lista trafia do produktu: oddajesz ją także jako tablicę
odczytów JSON, którą zlecający dopisuje do `reads.json` i na niej
przebudowuje dzień (sekcja 5).
Kończy się werdyktem i **żadną rekomendacją stawki**.

---

## 0. Co jest weryfikowane

**Kuponem jest PDF**, a od 2026-10-05 jego jedynym artefaktem jest
`runs/sofa/<data>/11_coupon.json` (COUPON_ASSEMBLY: piłka i tenis z
`08_confidence.json`, hokej / koszykówka / siatkówka / CS2 z
`08_confidence_sports.json`). Weryfikujesz: **top 30** (pierwsze 30 pozycji
niezablokowanych), **każdą nogę wydrukowanego buildera**, pozycje z
`read_requests.json` i **nogi sportów mierzonych** (z surowej migawki).
Nogi zablokowane (mecz się zaczął, noga była w poprzednim wydruku,
`12_printed.json`) są zapisem wydruku: nie oznaczaj ich `NO_BET` za to, że
dziś by nie przeszły — co najwyżej notatka.

`06_coupon.json` trzyma single VALUE (selektor cenowy), których zmierzony
wynik to **−20,4%** (2026-09-20) wobec **+8,2%** PDF-a tego samego dnia.
W **każdej tabeli nazwij, który plik jest który**. Nazwanie pliku singli
„kuponem" odwraca dzień.

Pewność na nodze jest od 2026-10-05 07:15Z (epoka `stats_only`) wyłącznie ze
statystyk; cena jest tylko filtrem (x = pewność × kurs ≥ 0,90, marża ≤ 15%,
świeża cena, mecz niezaczęty). `forecast_p` („model”) jest nieskalibrowany i
niczego nie bramkuje — rozjazd modelu z pewnością nie jest defektem.

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

### 1b. Kupon: `audit_variants.py` (C1–C3, U1–U3)

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <data>
```

Wyjście `0` = brak znalezisk, `1` = są znaleziska, `2` = zły plik.

- **C1** — artefakt swojego profilu, nie starszy niż arkusz i weta; PDF nie
  starszy od artefaktu.
- **C2** — każdy wydrukowany singiel spełnia swoje pokrętła; noga
  zablokowana sprawdzana wobec `printed_under`.
- **C3** — każda noga z `confidence.legs_requiring_read` (top 30, nogi
  wydrukowanych builderów, `read_requests.json`) ma odczyt
  `author: "analyst"`, a żadna wydrukowana nie ma WATCH ani NO_BET.
- **U1** — świeże single `11_coupon.json` w kolejności `coupon_order`,
  numerowane 1..N, zablokowane na górze bez numeru.
- **U2** — każdy świeży singiel piłki i tenisa niesie epokę `stats_only`.
- **U3** — każda świeża noga sportu mierzonego odtworzona z surowej migawki
  Superbetu z chwili budowy `08_confidence_sports.json`: kurs, czas i wiek
  ceny, marża grupy ≤ 15%, x ≥ 0,90, pewność = kubełek kalibracji
  `forecast_p`.

Linie pod `notes (not defects):` nie są znaleziskiem, ale też nie są
„zaliczone” — wymień je w raporcie. „nothing to check” to nie jest
zaliczenie — powiedz, czego nie było. Dla nogi sportu U3 sprawdza migawkę,
nie dzisiejszą cenę: dopytaj Superbet o żywą cenę jak w 2c (strona i cała
grupa wyników), sprawdź tożsamość meczu w `sport_fixtures.json`
(`IDENTIFIED`, `home_is_team1`) i czy rynek rozlicza się tak, jak mówi
etykieta (czas podstawowy czy z dogrywką, okres, format).

Historyczne (wycofane 2026-10-05: WARIANT i WSZYSTKIE od 07:15Z, kupony
sportowe od 08:30Z; pliki do poranka 10-05 zostają i są rozliczane po
staremu): S1–S5 (kupony sportów) i M1–M3 (WARIANT WSZYSTKIE) odpalają się
tylko dla tych dni, a dla późniejszych buildów są notatkami. WARIANT
(`08_confidence_wariant.json` → `KUPON_<data>_WARIANT.pdf`) weryfikuje się
tylko dla dnia, który go ma — osobno, nigdy łącznie z kuponem.

---

## 2. Cztery rzeczy, których audyt nie umie

Audyt sprawdza wiersz **wobec niego samego**. Wiersz, którego wszystkie pola
są wzajemnie spójne i wszystkie zbudowane na złej próbce, przechodzi go bez
zająknięcia. Dlatego dla **każdej pozycji top 30, każdej nogi buildera i
każdej nogi sportu mierzonego**, którą drukuje PDF (dla nogi sportu 2a to
odtworzenie z migawki i `sport_fixtures.json`, nie z `03_samples.json`):

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

- tenis: odtwórz `p_central` z notatek wiersza (`TENNIS_RATING`: 0,25 ×
  rating + 0,75 × `market_p`; `P_SHRUNK_TO_PRICE`: w × trafienia/n +
  (1−w) × `market_p`, w = n/(n+30)). Niezgodność z tym jest znaleziskiem,
  rozjazd do surowej trafialności nie;
- piłkarskie liczniki idą przez ujemny dwumianowy i różnić się **muszą** — ale
  rozjazd powyżej ~15 pp znaczy, że pracuje prior ligowy, a nie drużyna.
  Policz `n/(n+25)` i powiedz, jaką część środka naprawdę trzyma próbka. Od
  2026-10-04 robi to kod: każda noga ma `sample_hit_rate`, a noga piłkarska
  z `model_p` wyżej o ponad 0,15 (n ≥ 5) wypada z kuponu oficjalnego
  (`MODEL_ABOVE_OWN_SAMPLE`) i zostaje oznaczona w WARIANCIE. Oficjalna noga
  piłkarska ponad tą luką to defekt; trafialność odtwórz z `03_samples.json`,
  nie ufaj polu.

### 2b. Czy `subject` wskazuje tę stronę, o której myśli

Najbardziej kruchy join w pipelinie. Rozwiąż go **niezależnym** matcherem,
który składa diakrytyki, wobec `home_name` / `away_name` z `02_fixtures.json`.
Wiersz `_for` po złej stronie jest niewidoczny w każdej innej kontroli.

### 2c. Dopytaj Superbet o żywą cenę

Przez `OfferFetcher` — ten sam kod, którego użył OFFER — **i** czytając
payload z kursami drugi raz ręcznie. Drugie czytanie weryfikuje twój parser
wobec niego samego. Potwierdź, że rynek, linia, kierunek i cena istnieją tak,
jak twierdzi artefakt, i że mecz nadal jest na tablicy.

Najpierw przeczytaj `fetcher.errors`. Od 2026-10-01 listing Superbetu, który
rzucił błąd, trafia do `fetcher.errors`, a mecz, którego **każdy** listing
rzucił błąd, jest z wyniku `fetch_offers` **pominięty**
(`src/bet/sofa/offer.py`) — pusty wynik wygląda wtedy dokładnie jak mecz
zdjęty z tablicy. Jeśli `fetcher.errors` wymienia któryś z
`superbet_event_ids` meczu, werdykt to **NIE DA SIĘ ZWERYFIKOWAĆ**, nigdy
„niedostępne”. Klienta buduj jak `scripts/sofa/run_offer.py`
(`SuperbetClient(base_url="https://production-superbet-offer-pl.freetls.fastly.net")`
albo `SuperbetClient()`), nigdy dosłownie `SuperbetClient(...)` — Ellipsis
trafia do `base_url.strip()` i rzuca `AttributeError`.

### 2d. Czy mecz naprawdę się nie zaczął — na wcześniejszym zegarze

**Oba stopnie biorą `min(kickoff_utc, superbet_kickoff_utc)`** — COUPON od
dawna, CONFIDENCE od commita `3f1136bc` (2026-09-21); wcześniej czytał sam
zegar Sofascore i to właśnie ścieżka postawiona czytała zły zegar. Na ITF oba
rozjeżdżają się do 11 h. Reguła jest bezpieczna, ale **nie darmowa i nie
jednokierunkowa**: zwykle to Sofascore spóźnia się o 7–9 h i mecz zakończony
wygląda na nadchodzący, ale bywa odwrotnie — 2026-09-21 dla ITF W50 Berkeley
to Sofascore niósł czas *wcześniejszy* i fałszywy (12:00Z = 05:00 lokalnie),
więc `min()` odrzucał mecze realnie jeszcze przed startem. Tamtego dnia
kosztowało to 0 wierszy, bo wszystkie 10 takich fixture'ów miało `NO_PRICE`.
Sprawdź jedno i drugie: czy postawiona noga nie siedzi w szczelinie, i ile
wierszy reguła odrzuciła na zegarze, który był tym błędnym.

---

## 3. Antyselekcja — najważniejszy test

COUPON rankuje po **względnej przewadze cenowej** (`surplus / required_odds`),
a każda miara nadwyżki rośnie, gdy `p` jest **zawyżone**. Wiersze najbardziej
podatne na błąd są więc najczęściej wybierane. To własność mechanizmu, nie
hipoteza o dniu, i z niej biorą się konkretne kontrole
(dotyczą `06_coupon.json`). Kupon (`11_coupon.json`) od 2026-10-05 sortuje po
pewności, nie po cenie — tam test antyselekcji to: czy top 30 skupia się w
jednym rynku, jednej lidze, cienkich kubełkach krzywej (`calibration_n`) albo
w jednym sporcie mierzonym, i ile szczebli jednej drabiny stoi obok siebie.
Kontrole selektora VALUE:

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
   z powodem dla każdego.** To jest produkt. Prozą **i** na samym końcu jako
   jedna ogrodzona tablica JSON obiektów `LegRead`
   (`src/bet/sofa/contracts.py`, strict, `extra="forbid"`; klucze
   `sofascore_event_id`, `market`, `subject`, `line`, `direction`, `verdict`,
   `author: "verifier"`, `reason`, opcjonalnie `context` i `period`; dla nogi
   sportu `market` = rodzina, `direction` = strona T1/T2/DRAW/ODD/EVEN/YES/NO
   albo wynik „3:1”, `period` = okres / kwarta / set / mapa): `verdict:
   "NO_BET"` za defekt (zła strona, nieaktualna albo błędna cena,
   arytmetyka, która się nie odtwarza, zła tożsamość meczu), `"WATCH"` za
   osąd; `[]`, gdy lista jest pusta. Weryfikator nie pisze pliku — zlecający
   dopisuje tablicę do `reads.json`, przebudowuje od CONFIDENCE (FIXTURE_CHECK
   najpierw) przez `build_coupon.py` do PDF i powtarza `audit_coupon` +
   `audit_variants`. NO_BET i WATCH zdejmują nogę z kuponu do
   `removed_by_reads` (rozliczana osobno, `audit_settlement` 7h).

Na koniec werdykt i **żadna rekomendacja stawki**. Kupon bywa technicznie
poprawny i mimo to niewart stawiania: `K_PRICE` i `MAX_LADDER_SIGMA` są
`NOT_FITTED` i każdy wiersz o tym mówi. Decyzja o stawce należy do operatora.
