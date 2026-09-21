# Przebieg `sofa` — 2026-09-21 (poniedziałek)

Pełny dzień: SETTLE D-1 → BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET →
COUPON → CONFIDENCE → PDF → weryfikacja wg `PROMPT_FIX_VERIFY_COUPON.md` Cz. 4.

`run_id = day0921`. Werdykt pipeline'u: **PARTIAL** (SHEET i COUPON OK, reszta
PARTIAL — normalny kształt, nie awaria).

---

## Wynik dnia, jednym zdaniem

**Kupon jest pusty i to jest uczciwa odpowiedź.** Żaden z trzech Bet Builderów
nie przechodzi progu EV po zmierzonym narzucie korelacyjnym Superbetu, a 63
single to ta sama rodzina niezgody z ceną, która wczoraj zwróciła −20,4%.

**Ten wniosek jest odporny, nie graniczny.** Sprawdzone na całym zmierzonym
zakresie narzutu (8,8% / 12% / 19,6%):

| mecz | EV @0% | EV @8,8% | EV @12% | EV @19,6% |
|---|---|---|---|---|
| Aldosivi – Atlético Tucumán | +7,99% | −1,51% | −4,96% | −13,17% |
| Real Cundinamarca – Deportes Quindío | +7,37% | −2,08% | −5,51% | −13,67% |
| Nueva Chicago – Patronato | +3,37% | −5,73% | −9,04% | −16,89% |

Dodatnie są wyłącznie w kolumnie 0% — czyli gdyby Superbet wyceniał Bet
Buildera jako czysty iloczyn nóg, czego pomiar nigdy nie pokazał.

---

## 1. Etapy i liczby

| etap | werdykt | liczby |
|---|---|---|
| SETTLE (2026-09-20) | PARTIAL | 34 324 wiersze, 564/578 meczów, 31 815 z ceną |
| BOARD | OK | 302 mecze (102 piłka / 200 tenis) |
| RESOLVE | PARTIAL | 255 meczów, recall 84,4%; 27 `NO_MATCHING_EVENT`, 2 `AMBIGUOUS_ENTITY` |
| OFFER (przed próbkami) | PARTIAL | 255 ofert, 156 z ceną, 99 pustych, 2774 szczeble dwustronne |
| SAMPLES | PARTIAL | 146 READY / 9 PARTIAL / 100 BLOCKED; 1683 zapytania sieciowe, 1298 z cache |
| OFFER (odświeżenie) | PARTIAL | ceny pod próg pobrane ponownie |
| SHEET | OK | 5764 wiersze: 142 VALUE, 320 LEAN, 5253 BELOW_BAR, 49 NO_PRICE |
| COUPON | OK | 63 single wybrane, 79 odrzuconych, **0 niezastosowanych wet** |
| CONFIDENCE | OK | 25 nóg, 3 Bet Buildery, 19 meczów z nogami |
| PDF | OK | **0 pozycji** |

Odrzucenia w COUPON: `FAMILY_SLOT_TAKEN` 75, `KICKOFF_TOO_SOON` 4.

---

## 2. Dlaczego PDF jest pusty

Wszystkie trzy Bet Buildery mają `best_for_fixture: True`, ale ujemne EV po
narzucie 12%:

| mecz | p łączne | kurs po narzucie | EV |
|---|---|---|---|
| Aldosivi – Atlético Tucumán | 0,5714 | 1,663 | **−4,96%** |
| Real Cundinamarca – Deportes Quindío | 0,6316 | 1,498 | **−5,38%** |
| Nueva Chicago – Patronato | 0,7331 | 1,239 | **−9,16%** |

Bramka to `build_coupon_pdf.py:159` — `best_for_fixture and ev_after_haircut > 0`.
Zadziałała poprawnie. Narzut 12% to wielkość **zmierzona** (8,8 / 15,8 / 19,6%
na trzech slipach z 2026-09-20), nie założona.

Zwróć uwagę: `ev_if_product_priced` jest dodatnie dla wszystkich trzech
(+24,3%, +10,6%, +3,2%). Różnica między tą liczbą a `ev_after_haircut` jest
całym wynikiem dnia — i całą różnicą między kuponem opłacalnym a nie.

---

## 3. Weryfikacja kuponu (Cz. 4)

### 4.1 / 4.2 — struktura i arytmetyka

`audit_coupon.py`: **brak znalezisk.** Każdy wiersz kuponu istnieje w arkuszu
jako VALUE, każdy VALUE jest w kuponie albo w `06_dropped.json` z powodem —
zero wierszy zniknęło w ciszy. Arytmetyka przeliczona niezależnie z pól wiersza
zgadza się w 63/63.

Kontrola ręczna na wierszu nr 1 (Tenti – Kestelboim):
`p_bar = 0,5·0,600 + 0,5·0,0964 = 0,3482` ✓ przy `w = n/(n+K_PRICE) = 10/20`;
`required = 1,10 / 0,3482 = 3,159` ✓; `surplus = 5,9 − 3,159 = 2,741` ✓.

`UNFITTED_CONSTANTS: K_PRICE, MAX_LADDER_SIGMA` widnieje przy **63 z 63**
wierszy. Notka jest prawdziwa i nie wolno jej usuwać.

### 4.3 — antyselekcja: tu kupon wypada źle

| rozkład | obserwacja |
|---|---|
| rynek | **42 z 63 to `games_won_for`** — jedna rodzina tenisowa |
| rodzina mechanizmu | tennis_length 42, scoring 14, attacking 5, discipline 2 |
| liga | ITF-y i **kwalifikacje** dominują; ani jednej ligi TOP-5 |
| `sample_size` | **47 z 63 ma n ≤ 10**, w tym 41 dokładnie n=10 |
| nadwyżka | mediana +0,107, maks **+2,741**; 8 wierszy > +0,40 |
| rodzaj niezgody | 36 lokalna, 21 większość drabiny, **6 cała drabina** |

To jest dokładnie wzorzec, który metoda nazywa artefaktem, a nie przewagą:
wygrywa brak danych. Przy n=10 i `K_PRICE=10` waga próbki to 0,5, więc połowa
`p_bar` pochodzi ze zdevigowanej ceny — kupon w dużej mierze mierzy przewagę
ceny nad samą sobą, nie model.

Skrajny przykład (najwyższa nadwyżka w pliku): rynek wycenia „Kestelboim
poniżej 11,5 gema" na **9,6%**, my na **60%**. Sześciokrotna niezgoda na
próbce 10 meczów. Wiersz jest arytmetycznie poprawny i mimo to jest
**dokładnie tym, czego nie należy stawiać**.

### 4.3 — kontrola cen na żywo

Wszystkie **69 nóg** (63 single + 6 nóg Bet Builderów) odpytane ponownie
u Superbetu tą samą ścieżką co OFFER (`OfferFetcher`, nie druga interpretacja
payloadu): **69 potwierdzonych, 0 znikniętych, 0 z dryfem > 5%.** Ceny są
prawdziwe i świeże.

### Zegar

0 meczów na kuponie już rozpoczętych, licząc **wcześniejszym** z dwóch zegarów.
Najwcześniejszy start 06:10 UTC, najpóźniejszy 22:30 UTC.

Rozjazd zegarów dotyczy 79 z 255 meczów, ale **78 z nich to tenis** (do 11 h) —
ITF-y, gdzie Superbet podaje nominalne „nie wcześniej niż" (01:00), a Sofascore
realny termin (10:00). Wszystkie `CONFIRMED`, więc to nie złe dopasowanie, tylko
semantyka terminarza. `coupon.py:114` bierze `min()` z dwóch zegarów, czyli
zachowawczo odetnie część nierozpoczętych ITF-ów. Świadomy koszt bezpieczeństwa.

---

## 4. Alarm, który się zapalił i został rozbrojony dowodem

`coverage_floor` dla piłki: **PARTIAL — 66 READY vs mediana 406 (próg 243,6)**,
z komunikatem „a drop this size is a matching regression until proven otherwise".

**To nie jest regresja dopasowania.** Dowód — wskaźnik RESOLVE po dniach:

| dzień | tablica piłki | dopasowane | wskaźnik |
|---|---|---|---|
| 2026-09-18 | 407 | 294 | 72,2% |
| 2026-09-19 | 1039 | 937 | 90,2% |
| 2026-09-20 | 1040 | 872 | 83,8% |
| **2026-09-21** | **102** | **81** | **79,4%** |

Dopasowanie działa normalnie. Skurczyła się sama tablica, bo **dziś jest
poniedziałek**, a mediana pochodzi z czterech przebiegów, z których trzy to
weekend. Zweryfikowane niezależnie: surowa odpowiedź Superbetu na dziś ma
**104 mecze piłki** (i 2703 wiersze łącznie, z czego 2698 z dzisiejszą datą),
więc 102 na tablicy to pełna oferta książki, nie ucięcie.

Wniosek dla progu: mediana `coverage_floor` nie odróżnia dnia tygodnia i będzie
fałszywie alarmować w każdy poniedziałek.

---

## 5. Znaleziska

### Z1 — `stakeable_builders` ignoruje EV (P2, raportowanie) — **NAPRAWIONE**

`run_confidence.py:457` liczy `sum(1 for b in builders if b["best_for_fixture"])`.
Dziś zgłosiło **`stakeable_builders: 3`**, podczas gdy PDF postawił **0** — bo
PDF dokłada warunek `ev_after_haircut > 0`, którego ta metryka nie zna.

Operator czytający `SOFA_SUMMARY` z CONFIDENCE zobaczy trzy zakłady do
postawienia w dniu, w którym nie ma żadnego. Dwa artefakty tego samego
przebiegu mówią sprzeczne rzeczy o tej samej liczbie.

*Poprawka (2026-09-21):* warunek wyjęty do **jednego wspólnego predykatu**
`bet.sofa.confidence.is_stakeable(builder)`, używanego teraz przez
`run_confidence.py` **i** `build_coupon_pdf.py`. Dwie kopie tego samego
warunku były przyczyną, więc usunięcie jednej kopii, a nie poprawienie obu,
jest właściwą naprawą — inaczej rozjadą się znowu. Predykat obsługuje też
starsze artefakty, które niosą tylko `ev_if_product_priced`.

*Po poprawce, ten sam dzień:* `best_for_fixture: 3`, `stakeable_builders: 0`,
PDF `picks: 0`. Artefakty zgadzają się i żadna informacja nie zginęła —
`best_for_fixture` jest raportowane osobno.

*Testy:* `test_a_builder_with_negative_ev_after_the_haircut_is_not_stakeable`
(dane z tego dnia, wprost), `test_stakeable_needs_both_conditions_not_either`,
`test_an_artifact_predating_the_haircut_falls_back_to_product_ev`.

*Jak mocny jest ten test — uczciwie:* na starym kodzie failuje przez
`ImportError`, bo funkcji nie było, a to słaby powód. **Mocnym dowodem, że
stary kod był zepsuty, jest sam przebieg:** CONFIDENCE wypisał
`stakeable_builders: 3`, a PDF w tym samym przebiegu `picks: 0`.

### Z2 — `reportlab` niezadeklarowany, `.venv` ma dwa interpretery (P2, środowisko) — **CZĘŚCIOWO NAPRAWIONE**

PDF **jest** kuponem, a `build_coupon_pdf.py` padł na `ModuleNotFoundError:
reportlab`. Pakietu nie ma w żadnym pliku wymagań (`pyproject.toml` go nie
wymienia).

Gorsza część: `.venv` ma **dwa** interpretery —
`.venv/bin/python → python3.12` (na nim działa cały pipeline) oraz dołożony
2026-09-16 `.venv/bin/python3.14`, i **`.venv/bin/pip` wskazuje na 3.14**.
Więc `.venv/bin/pip install reportlab` zgłasza sukces, instaluje do
`lib/python3.14/site-packages`, a pipeline dalej go nie widzi. Objaw: pip mówi
„Requirement already satisfied", a import pada.

Obejście użyte dziś: `.venv/bin/python -m pip install reportlab`.

*Poprawka (2026-09-21):* `reportlab>=4,<6` dopisany do `dependencies`
w `pyproject.toml` — jako zależność **runtime**, nie dev, bo PDF jest
produktem, a nie raportem pobocznym.

*Czego NIE naprawiłem:* rozjazdu interpreterów w `.venv`. To zmiana
w środowisku operatora, nie w repozytorium, i przebudowa `.venv` mogłaby
zabrać pakiety, o których nie wiem. Objaw wraca przy każdej instalacji:
IDE zgłasza „Package `reportlab` is not installed" dla nowego wpisu
w `pyproject.toml`, bo patrzy na 3.14. Do decyzji operatora.

---

## 5b. Bramki po poprawkach

| bramka | wynik |
|---|---|
| `pytest tests/sofa` | **659 passed**, 2 skipped (było 656 — trzy nowe testy) |
| `ruff check` | żaden błąd nie wskazuje na linię, którą napisałem |
| `mypy --strict` | `is_stakeable` czyste; 129 błędów to zastana baza w 10 plikach |
| import po zmianie | OK (zasada: po zmianie w module uruchom import) |

Uwaga do porównania z `ruff`/HEAD: `build_coupon_pdf.py`, `run_confidence.py`,
`run_offer.py`, `run_settle.py` i `confidence.py` **miały już niezacommitowane
zmiany, zanim zacząłem**, więc HEAD nie jest bazą tej sesji. Weryfikowałem
per-linia, nie po liczniku.

## 6. Czego ten przebieg NIE przetestował

Zgodnie z zasadą „powiedz wprost, że nie przetestowaliśmy, a nie że działa":

- **Bezpiecznik (F1)** nie dostał okazji — `breaker_state` był `CLOSED` przez
  cały przebieg, do otwarcia trzeba trzech porażek pod rząd.
- **Ponowienie 403 w userscripcie (F2)** — ani jednego 403 w całym dniu.
- Rozliczenie dzisiejszego dnia (SETTLE 2026-09-21) siłą rzeczy nie mogło się
  odbyć; należy je uruchomić jutro.

## 7. Czego świadomie nie zrobiłem

**Nie przefitowałem stałych (E11).** `fit_constants.py` to osobny, świadomy
etap, nie część `DEFAULT_SEQUENCE`; zmiana stałych w trakcie dnia zerwałaby
porównywalność z wczorajszym przebiegiem. Wczorajsze 34 324 wiersze są już
w `sofa_settled_row` i czekają na następny celowy fit.

Stan stałych użytych dziś: `K_CENTRE` FITTED (piłka 25,0, tenis 2,0) z 1 876 612
wierszy; **`K_PRICE` NOT_FITTED**; `MAX_LADDER_SIGMA` NO_DIVERGENCE.

---

## 8. Kontekst z wczoraj (2026-09-20), rozliczony w tym przebiegu

| | wynik |
|---|---|
| PDF-kupon (6 Bet Builderów) | 5/6 slipów, 11/12 nóg, **ROI +8,2%** (ceny w większości szacowane) |
| Ścieżka VALUE-singli | 1213 wierszy, 32,6% trafień, **ROI −20,4%** |
| Kalibracja `p_bar` | uczciwa: odchyłki od −0,013 do +0,025 w dziesięciu kubełkach |

Te dwie liczby obok siebie są najmocniejszym argumentem dnia: **PDF jest
kuponem, `06_coupon.json` nie.** 63 dzisiejsze single należą do tej gorszej
z dwóch populacji.

---

# 10. Weryfikacja pozycja po pozycji (na żądanie operatora)

63 single + 3 Bet Buildery (6 nóg). Każda pozycja odtworzona od zera z surowych
obserwacji w `03_samples.json`, nie z pól, które sama niesie — `audit_coupon.py`
sprawdza spójność wiersza ze sobą, a to jest warstwa niżej.

## 10.1 Obliczenia — cztery niezależne kontrole

| kontrola | wynik |
|---|---|
| `p_bar`, `required_odds`, `surplus`, `edge` | **63/63 dokładnie** |
| `subject` → strona meczu (ryzyko F29) | **47/47** zgodne z niezależnym matcherem składającym diakrytyki |
| `p_central` z właściwej rodziny rozkładu | 58/63 dokładnie, 5 w granicy 0,024 |
| cena na ekranie Superbetu, ponowione zapytanie | **69/69 potwierdzone**, 0 dryfu |

Pełny wzór, który się zgadza w 63/63 — i którego **nie da się odtworzyć
z samego wiersza kuponu**:

```
p      = max(0.01, p_central − max(0, calibration_correction))
w      = n / (n + K_PRICE)                       # K_PRICE = 10
p_bar  = w·p + (1−w)·market_p
required = 1.10 / p_bar
```

`calibration_correction` jest w `05_sheet.json`, ale **nie w `06_coupon.json`**.
Trzy wiersze (16339895, 15275924, 16339894) mają ją niezerową, więc dla nich
kupon nie opisuje własnej arytmetyki. To samo dotyczy `pred_sd`, którego nie ma
nigdzie — stąd te 5 wierszy w granicy 0,024 zamiast dokładnie.

## 10.2 Rozkłady — co wybrało sito

- **42 z 63 to `games_won_for`** (tenis). Te używają `p_empirical_raw`, więc
  `p_central` **jest** częstością własnej próbki — rozbieżność 0,000 na
  wszystkich 42.
- **21 piłkarskich** używa rozkładu (17 ujemny dwumianowy, 4 normalny).
  Tam `p_central` rozjeżdża się z próbką, bo taki jest zamysł.
- **47 z 63 ma n ≤ 10**; przy `K_PRICE=10` waga próbki to ≤ 0,5.
- Nadwyżka: mediana +0,107, maksimum **+2,741**.

## 10.3 Znalezisko Z3 — single nie mają bramki na wiek próbki (P2)

`coupon.py` pilnuje wieku **ceny** (45 min), ale nie wieku **próbki**. Limit
`MAX_BUILDER_SAMPLE_AGE_DAYS = 180` istnieje wyłącznie w ścieżce Bet Builderów
(`run_confidence.py:243`).

Skutek dziś:

| najnowsza obserwacja starsza niż | pozycji |
|---|---|
| 180 dni | 1 (Goffin – Lajal, 193 dni, rozpiętość 366 dni) |
| 90 dni | 2 |
| 30 dni | 5 |

Nie jest to epidemia — 58 z 63 ma świeżą próbkę. Ale **pozycja z najwyższą
nadwyżką w całym pliku** (Kestelboim, +2,741) ma najnowszy mecz sprzed **105
dni**, a najstarszy sprzed 320. To nie przypadek: nieświeża próbka częściej
rozjeżdża się z aktualną ceną, a sito sortuje po nadwyżce, więc **preferuje
właśnie takie wiersze**.

## 10.4 Znalezisko Z4 — bazy ligowe dla rożnych półmeczowych są o 24–32% za wysokie (P1)

To jest najpoważniejsze znalezisko tej weryfikacji i wyszło dopiero przy
konfrontacji z danymi zewnętrznymi.

**Mechanizm.** Wszystkie metryki półmeczowe mają w
`config/sofa_league_baselines.json` **wyłącznie jedną stałą globalną**, bez
podziału na ligi i **bez zapisanego `n`**. Przy `K_CENTRE = 25` dla piłki ta
stała dominuje małą próbkę:

```
Csikszereda, corners_2h_for, n=8, własna średnia 1.125
w_próbki = 8/(8+25)      = 0.2424
centre   = 0.2424·1.125 + 0.7576·3.4286 = 2.870   (arkusz: 2.870)
```

**76% środka pochodzi z jednej globalnej stałej, 24% z meczów tej drużyny.**

**Dlaczego to błąd, a nie strojenie.** Stałe półmeczowe są niespójne
z pełnomeczowymi bazami z tego samego pliku:

| rodzina | 1H | 2H | suma | pełny mecz (mediana lig) | udział 2H |
|---|---|---|---|---|---|
| `corners_total` | 4,077 | 6,500 | 10,577 | 9,904 | **65,6%** |
| `corners_for` | 2,167 | 3,429 | 5,595 | 4,911 | **69,8%** |
| `goals_total` | 1,264 | 1,750 | 3,014 | 3,137 | 55,8% |
| `goals_for` | 0,600 | 0,878 | 1,478 | 1,616 | 54,3% |

Zmierzony udział 2. połowy w rożnych to **52,8%** (footiqo.com, 141 316
meczów). Nasze stałe mówią 65,6% i 69,8% — czyli **+24,3%** i **+32,3%**
za wysoko. Gole są w porządku, rożne nie.

Kilka z tych stałych jest podejrzanie okrągłych — `corners_2h_total = 6.5`,
`fouls_1h_total = 11.0`, `shots_1h_total = 13.0`, `serve_points_set1_total = 4.0`
— co wygląda na fit z kilku obserwacji. Plan (E11) odrzuca wpis ligowy poniżej
30 obserwacji do puli globalnej, ale **sama pula globalna nie ma progu ani
zapisanego `n`**, więc nic nie sygnalizuje, że jest niepewna.

**Zasięg.** Dotyczy wyłącznie piłkarskich wierszy liczonych z rozkładu.
42 pozycje tenisowe używają częstości empirycznej, więc baza w ogóle do nich
nie wchodzi. Realnie uderzone są **2 pozycje** (`corners_2h_for`,
`corners_2h_total`) mocno i 7 goli półmeczowych łagodnie.

*Proponowana poprawka:* (a) wyliczyć stałe półmeczowe jako udział zmierzony
z `sofa_settled_row`, nie osobnym fitem na garstce wierszy; (b) zapisywać `n`
przy każdej stałej globalnej i traktować `n < 30` jak brak bazy; (c) kontrola
spójności w `fit_constants.py`: `1H + 2H` musi się zgadzać z pełnym meczem
w granicy tolerancji — dziś dla `corners_for` rozjazd to 14%.

## 10.5 Weryfikacja zewnętrzna — cztery rynki rozbieżne

Cztery wiersze, gdzie nasz model najmocniej rozjeżdżał się z własną próbką,
sprawdzone w źródłach spoza systemu.

| rynek | nasza próbka | nasz model | zewnętrznie | próg opłacalności | werdykt |
|---|---|---|---|---|---|
| Csikszereda rożne 2H > 2,5 @3,00 | 12,5% | 62,3% | 10–25% | 33,3% | **model ZAPRZECZONY** |
| Criciúma rożne < 5,5 @~2,0 | 20% | 55,6% | 28–42% | 50,0% | **model ZAPRZECZONY** |
| Oțelul rożne 2H > 5,5 @2,75 | 19% | 54,4% | 26–37% | 36,4% | **model ZAPRZECZONY** |
| Barracas celne > 8,5 @~1,9 | 29% | 56,0% | ~50% | 52,6% | **próbka ZAPRZECZONA** |

Zmierzone dane zewnętrzne, kluczowe: **Csikszereda zdobywa 2,6 rożnego przez
CAŁY mecz** (sportsgambler.com, ostatnie 10). Linia 2,5 w samej drugiej połowie
wymaga od nich w 45 minut więcej, niż robią w 90. Nasz model implikuje λ≈3,3
w drugiej połowie, czyli ~6,3 rożnego na mecz — **2,4× ponad pomiar**. To
niezależnie potwierdza Z4.

Dla Oțelul średnia naszej próbki (4,56) zgadza się z zewnętrzną (4,59) niemal
co do setnej — **błąd nie jest w próbce, tylko w przejściu od próbki do
prawdopodobieństwa**. To dokładnie Z4.

Żaden z czterech nie jest dodatni względem danych zewnętrznych.

*Ograniczenia tej weryfikacji, uczciwie:* rożne w podziale na połowy nie są
dostępne w żadnym darmowym źródle (thestatsdontlie i footystats trzymają je za
paywallem), więc pozycje 1 i 3 opierają się na przeliczeniu pełnomeczowej
średniej udziałem 52,8%. To wyprowadzenie z twardej bazy, nie pomiar.
Dla pozycji 2 i 4 są niezależne potwierdzenia (fotmob, apwin, footymetrics).

## 10.6 Weryfikacja zewnętrzna — trzy mecze Bet Builderów

**Terminy potwierdzone.** Wszystkie trzy grane dziś, status „Scheduled", żadnego
przełożenia (365scores API + prasa lokalna, pobrane 2026-09-21). Jedyne
zastrzeżenie: godzina Nueva Chicago – Patronato ma jedno starsze źródło mówiące
17:00 ART wobec dwóch nowszych 19:00 ART (= 22:00 UTC).

### Aldosivi – Atlético Tucumán — odrzucenie potwierdzone z zapasem

| przesłanka | nasze | zewnętrzne (365scores, n=42, III–IX 2026) |
|---|---|---|
| gole w 2. połowie, średnia | 1,50 (n=20) | **1,19** |
| 2. połowa ≥ 2 gole | 11/20 = 55% | **17/42 = 40%** |
| strzały celne ≥ 10 | 7/19 = 37% | **10/41 = 24%** |

Kurs 1,40 na „powyżej 1,5 gola w 2. połowie" implikuje 71,4%. Leg jest poniżej
swojej ceny przy **obu** pomiarach, więc wniosek nie zależy od tego, który
przyjmiemy.

Czego model nie wie, a co działa w tę samą stronę: **Vombergar** (najlepszy
strzelec Aldosivi) wypada z naderwaniem mięśnia, plus Godoy i Chávez; pogoda
w Mar del Plata o 17:30 UTC to **10,5 °C, 97% szans na opad, porywy 89 km/h**
(open-meteo). Odrzucenie tego Bet Buildera było słuszne niezależnie od EV.

### Korekta do analizy zewnętrznej — nie brać jej na wiarę

Analiza twierdziła, że nasze 1,50 bierze się z próbki „przechylonej w stronę
Aldosivi przy pominięciu Tucumána". **To nieprawda i da się to sprawdzić:**

```
side_a (Aldosivi):  n=10  śr=1.60
side_b (Tucumán):   n=10  śr=1.40
pool:               n=20  śr=1.500
```

Próbka jest idealnie zbalansowana. Prawdziwa przyczyna rozjazdu to **okno
czasowe**: nasze obserwacje to 2026-07-24…09-16 (ostatnie 10 meczów każdej
strony), zewnętrzne to marzec–wrzesień (42 mecze). To spór „świeżość vs cały
sezon", nie błąd doboru próby — i nie jest oczywiste, że pełny sezon ma rację.

(Zgodne z tym, co już wiemy: liczby od subagentów trzeba weryfikować.)

### Dwa ostrzeżenia warte zapamiętania

1. **Autogenerowane składy.** sportsgambler.com i goal.com podają „prawdopodobny
   XI" Aldosivi z Vombergarem w ataku i nieaktualnym trenerem. Trenerem jest
   Sanguinetti, a Vombergar jest kontuzjowany. Tych składów nie wolno używać.
2. **Zero, które oznacza brak.** 365scores podaje dla trzech meczów Deportes
   Quindío strzały celne jako 0/1 lub pusto — to braki feedu, nie zera. Każda
   średnia liczona z takiego źródła jest zaniżona. Dokładnie ten wzorzec mamy
   już zanotowany.

### Kontekst, którego model nie ma (obie strony grają o stawkę)

- Aldosivi **ostatnie w Zona B**, gra o utrzymanie; Tucumán walczy o top-8.
- Deportes Quindío jest **dokładnie na kresce** awansu do cuadrangulares.
- Nueva Chicago – Patronato to mecz o spadek; Patronato bez Cortésa, Díaza
  i zawieszonego Piccioniego. Chicago ma **0,64 gola w 2. połowie na mecz**
  i medianę **5 strzałów celnych obu drużyn łącznie**.

---

# 11. Werdykt końcowy weryfikacji

**Kupon (PDF): 0 pozycji.** Poprawnie — potwierdzone na całym zmierzonym
zakresie narzutu korelacyjnego i niezależnie przez dane zewnętrzne, które
podważyły obie przesłanki najlepszego z trzech Bet Builderów.

**63 single z `06_coupon.md`: arytmetycznie bez zarzutu, selekcyjnie nie.**
Nie rekomendowałbym **18 z 63**:

| powód odrzucenia | pozycji |
|---|---|
| nadwyżka > +0,40 (podejrzana z definicji) | 8 |
| model kłóci się z własną próbką o > 15 pp | 8 |
| najnowsza obserwacja starsza niż 30 dni | 5 |
| oparte na zepsutej bazie 2H rożnych (Z4) | 2 |

(kategorie się nakładają; unikalnych pozycji: 18)

Pozostałe 45 przechodzi kontrole mechaniczne, ale **żadnej nie weryfikowałem
zewnętrznie** — to 42 tenisowe ITF-y i kwalifikacje, dla których nie ma
darmowych danych o gemach, plus 3 piłkarskie. O nich mogę powiedzieć tylko
tyle, że arytmetyka i cena się zgadzają.

**Czego ta weryfikacja nie rozstrzyga:** czy `p_empirical_raw` na próbce 10
meczów jest dobrym estymatorem dla gemów w ITF-ach. 42 z 63 pozycji na tym
stoją, `K_PRICE` jest `NOT_FITTED`, a rozliczona historia tenisa jest cienka.
To pytanie na pomiar, nie na opinię.

---

# 12. Przegląd procesu i naprawy (na żądanie operatora)

Przegląd architektury wylądował w nowym `docs/sofascore-api/RUNBOOK.md`;
procedura operacyjna w `.claude/commands/sofa-day.md` (`/sofa-day`).

## 12.1 Przyczyna problemu „jak ostatnio"

Nie było **żadnej** dokumentacji `sofa` opisującej, jak uruchomić dzień.
Istniał `docs/SIMPLE_STATS_RUNBOOK.md` i komenda `/run-day` — **oba dla
starego pipeline'u `simple`**, z etapami DISCOVER / ENRICH / ANALYZE, których
w `sofa` nie ma. Sięgnięcie po nie było jedyną dostępną drogą.

Naprawione trzema rzeczami:

1. **`/sofa-day`** — procedura z nazwami etapów, kosztami, pułapkami
   i protokołem weryfikacji.
2. **`RUNBOOK.md`** — warstwa pod nią: co każdy etap robi, przepływ
   artefaktów, co w tym pipelinie jest mocne, a co słabe.
3. **Baner LEGACY** na `/run-day` i `/rebuild-coupon`, wskazujący na `sofa`.

## 12.2 Naprawy z testami

| # | usterka | naprawa | testy |
|---|---|---|---|
| Z1 | `stakeable_builders` ignorowało EV | wspólny `confidence.is_stakeable` dla CONFIDENCE i PDF | 3 |
| Z2 | `reportlab` niezadeklarowany | dodany do `dependencies` | — |
| Z3 | brak bramki na wiek próbki dla singli | `MAX_SAMPLE_AGE_DAYS = 60`, pole `sample_newest_days` | 3 |
| Z4 | globalna baza bez `n` i bez progu; `corners_2h_for` +30% | pula trzymana do progu wpisu ligowego, zapisuje `n`; metadane `fitted_from`; kontrola udziału połówek | 10 |
| Z5 | wiersz kuponu bez `calibration_correction` | przeniesione na `CouponRow` | 1 |
| Z6 | `coverage_floor` mierzył liczbę, nie udział → fałszywy alarm w poniedziałek | próg liczy **udział READY w meczach sportu**; `current_share`/`median_share` w raporcie | 8 (przepisane) |

Bramki: **675 passed**, `ruff` i `mypy --strict` czyste na wszystkich
zmienionych plikach (bazy zastane niezmienione: `run_samples.py` 10 błędów
w HEAD i 10 teraz).

### Z4 — zmierzony efekt

Przyczyną nie był kod fitu, tylko **przestarzała konfiguracja**: plik baz był
z 2026-09-19, a baza rozliczeń urosła od tego czasu o 88 185 wierszy i 120
rozgrywek. Nic tego nie wykrywało, bo plik nie miał żadnych metadanych,
a wpis `global` nie zapisywał `n`.

Po przefitowaniu:

| metryka | stare | nowe | n | zmiana |
|---|---|---|---|---|
| `corners_2h_for` | 3,4286 | 2,6455 | 110 | **−22,8%** |
| `corners_2h_total` | 6,5000 | 5,1587 | 63 | **−20,6%** |
| `shots_on_target_1h_for` | 2,5714 | 2,1293 | 116 | −17,2% |
| `goals_2h_for` | 0,8776 | 0,7770 | 1368 | −11,5% |
| `fouls_1h_total` | 11,0 | **usunięte** | 17 | poniżej progu |

Nowa wartość `corners_2h_for` (2,6455) trafia w przewidywanie z niezależnej
weryfikacji zewnętrznej (2,59 z udziału 52,8%) — dwie metody, ten sam wynik.

Przebudowa 2026-09-21 na poprawionych stałych:

| rodzina | VALUE przed | po |
|---|---|---|
| `corners_2h_*` | 12 | **1** |
| `goals_2h_total` | 9 | 1 |
| `shots_on_target_total` | 3 | **0** |
| **razem VALUE** | **142** | **99** |

Bramka Z3 zdejmuje kolejne 7, w tym pozycję o najwyższej nadwyżce dnia
(+2,741 na próbce sprzed 105 dni). **Znikają dokładnie te wiersze, które
niezależna weryfikacja zewnętrzna odrzuciła** — żaden z czterech
skontrolowanych rynków nie przetrwał.

### Z6 — próg pokrycia, przed i po

```
przed:  football PARTIAL  66 READY vs median 406 (floor 243.6);
                          a matching regression until proven otherwise
po:     football OK       66 READY = 81.5% of this sport's fixtures,
                          vs median 80.4%
```

Stary próg mierzył wielkość kalendarza i nazywał ją regresją dopasowania.
Nowy mierzy dopasowanie.

## 12.3 Zgłoszone, nienaprawione — świadomie

- **`.venv` ma dwa interpretery** (`python` → 3.12, `pip` → 3.14). To
  środowisko operatora, nie repozytorium; przebudowa `.venv` mogłaby zabrać
  pakiety, o których nie wiem.
- **`pred_sd` nie jest zapisywane** na wierszu arkusza, więc `p_central` da się
  odtworzyć tylko w przybliżeniu (5 z 63 w granicy 0,024).
- **Sumy połówek dla goli nie domykają się** (−13,3% i −17,3%) — nowa kontrola
  to teraz zgłasza i zapisuje w pliku baz. Przyczyna jest znana: bazy
  półmeczowe są mierzone na mniejszej i innej populacji meczów niż
  pełnomeczowe. Wyrównanie populacji to osobna praca, nie poprawka przy okazji.
- **`K_PRICE` nadal `NOT_FITTED`** — to nie brak, tylko wynik: krzywa Brier
  jest monotoniczna do w=0, więc reguła plateau odmawia podania wartości.

---

# 13. Tenis był strukturalnie wykluczony z kuponu (Z7) — NAPRAWIONE

Operator zapytał, czemu przy 200 meczach tenisa kupon go nie ma. Odpowiedź:
**nie mógł go mieć nigdy.**

## 13.1 Objaw i przyczyna

Arkusz 2026-09-21: **3026 wierszy tenisowych wobec 2648 piłkarskich** — tenis
był większością dnia — i **0 nóg** w `08_confidence.json`. Cały PDF był
piłkarski z definicji, każdego dnia.

`fit_confidence.py` przeliczał `p` z rozkładu, więc pomijał rynki o częstości
empirycznej. Bez krzywej `run_confidence.py` odrzucał je jako
`NOT_IN_CALIBRATION_FIT` — 1072 wiersze, w tym cały `games_won_for`
(największy rynek tenisowy: 1084 wiersze tego dnia, 9286 rozliczonych)
i `sets_total`. Ten sam `games_won_for` stanowił **42 z 63 singli VALUE**.

Ścieżka dobra go nie widziała. Ścieżka zła składała się z niego.

## 13.2 Poprawka ma cztery warstwy — pierwsze dwie bez trzeciej są groźne

1. `fit_confidence` kalibruje rynki empiryczne z **zapisanego `p_central`**
   (dla nich `p_central` JEST częstością próbki). 19 → 33 rynki.
2. Bramka odrzuca już tylko rynki bez żadnego modelu.
3. **Sufit zmierzonego zakresu.** Bez tego poprawka natychmiast wyprodukowała
   **12 nóg `games_won_for` po 0,905** — rynek nie ma kubełka powyżej 0,825,
   więc spadał na pulę globalną (74 574 wiersze, prawie same liczniki
   piłkarskie). Jego własny pomiar: najlepszy kubełek realizuje **0,756**.
   To dokładnie katastrofa, przed którą chronił ban.
4. **Pula per sport.** Tenis ma 56 581 rozliczonych wierszy i jest na górze
   mierzalnie słabszy: **0,851 vs 0,907** w kubełku 0,900-0,925 i
   **0,886 vs 0,917** powyżej 0,95.

## 13.3 Efekt i uczciwy wniosek

Tenis z **0 → 2908 z 3026 wierszy skalibrowanych**. Ale jego własna kalibracja
mówi rzecz trzeźwą: **tylko 45 z 2908 sięga pewności 0,80** (5 powyżej 0,85),
107 siedzi w 0,75-0,80. `games_won_for` **nigdy** nie przekracza progu.

**Tenis nie jest już gubiony przez usterkę — jest wewnętrznie rynkiem niskiej
pewności dla tego modelu.** Jego brak na kuponie po tej dacie jest wynikiem
pomiaru, nie wykluczenia. To jest różnica, o którą chodziło.

---

# 14. Dwie iteracje przeglądu produkcyjnego

## Iteracja 1 — znalezisko Z8: kupon nie znał kalibracji

`audit_coupon.py` czysty, ale **8 z 45 wierszy kuponu (27 ze 116 VALUE) stało
powyżej zmierzonego sufitu swojego rynku** — deklarowały `p_central = 0,900`
tam, gdzie `games_won_for` nigdy nie zweryfikował nic ponad 0,825. CONFIDENCE
pilnował tego od kilku godzin, `coupon.py` nie. Dwie ścieżki nie zgadzały się
co do jednego zmierzonego faktu — dokładnie ten wzorzec, który stworzył Z7.

*Poprawka:* wspólna `Calibration.measured_ceiling()` w obu ścieżkach; nowy
powód odrzucenia `ABOVE_MEASURED_CEILING`. Zadziałał na **19 wierszy**,
kupon 45 → 40. Test: 4 przypadki (ponad sufitem, w zakresie, rynek bez
krzywej, brak kalibracji = bramka bezczynna).

*Uwaga metodologiczna:* pierwsza wersja tego testu oskarżyła 21 wierszy. Była
błędna — dla `p_central` poniżej 0,6 kalibracja ma **jeden szeroki kubełek**,
więc jego średnia nie obala konkretnej wartości. Prawdziwe jest tylko
kryterium „powyżej sufitu", gdzie kalibracja wprost odmawia odpowiedzi.

## Iteracja 2 — znalezisko Z9: produkt był luźniejszy niż półprodukt

Przeszedłem **40 pozycji, każdą osobno, siedmioma niezależnymi kontrolami**:
arytmetyka odtworzona od zera, `subject` → strona meczu, sufit kalibracji,
oba zegary, obecność dwustronnego szczebla w ofercie, świeżość próbki.
**40/40 bez znalezisk.** Ceny na żywo: **42/42 potwierdzone, zero dryfu.**

Znalezisko wyszło z porównania ścieżek, nie z wierszy:

```
COUPON:      sample_newest_days > 60   — czy próbka jest AKTUALNA
CONFIDENCE:  sample_oldest_days > 180  — jak daleko WSTECZ sięga
```

To dwa różne pytania, i **CONFIDENCE zadawał tylko drugie**. Ścieżka, która
produkuje stawiany PDF, nie miała żadnej bramki na świeżość — była
**luźniejsza niż ścieżka singli**, których i tak się nie stawia.

*Poprawka:* ta sama stała `MAX_SAMPLE_AGE_DAYS` zaimportowana do obu, plus
`sample_newest_days` na każdej nodze, żeby było widać w PDF. Test pilnuje, że
to jeden obiekt, nie dwie kopie liczby.

*Uczciwie:* dziś ta bramka odrzuciła **0 nóg** — wszystkie 15 miało świeże
próbki. Nie naprawiła niczego w tym dniu; zamknęła asymetrię, która prędzej
czy później by kosztowała.

## Stan końcowy

| | |
|---|---|
| `pytest tests/sofa` | **687 passed**, 2 skipped (było 656 na starcie sesji) |
| `ruff` | bez moich błędów; `run_confidence` 7 → 5 wobec HEAD |
| `mypy --strict` | 4 w `confidence.py`, wszystkie zastane |
| kupon single | 40, arytmetyka 40/40, ceny 42/42 na żywo |
| PDF | 0 pozycji — 1 builder, EV −9,0% po narzucie |

Powody odrzuceń w finalnym kuponie: `KICKOFF_TOO_SOON` 27,
`FAMILY_SLOT_TAKEN` 26, `ABOVE_MEASURED_CEILING` 19, `STALE_SAMPLE` 4.
