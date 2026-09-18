# Drugi przebieg `sofa` — raport z weryfikacji (2026-09-18)

Dokument kończy Część 4 `PROMPT_FIX_VERIFY_COUPON.md`. **Nie jest rekomendacją
zakładu.** Kończy się listą wierszy, których **nie** rekomenduję, mimo że kupon
je wybrał.

Wszystkie liczby pochodzą z artefaktów w `runs/sofa/2026-09-18/` i z
`runs/sofa/run.log.jsonl`. Wszystko, czego nie zmierzono, jest oznaczone
`PODEJRZENIE`.

---

## 1. Co zostało naprawione

Część 1 promptu (F13–F32) — **19 usterek, po jednym commicie na usterkę**, każda
z testem failującym na starym kodzie z właściwego powodu.

Poza zakresem promptu znalazły się w trakcie pracy jeszcze cztery, wszystkie
wykryte przez **uruchomienie**, nie przez test:

| | co | jak wykryte |
|---|---|---|
| **F33** | `/event/{id}` nie miał cache'u wcale — 46% requestów RESOLVE | analiza kosztu ponownego przebiegu |
| **F34** | błąd dopasowania zatruwa cache negatywny, a trucizna przeżywa poprawkę | poprawka F25 dała **bajt w bajt identyczny** artefakt |
| **F35** | clamp `[0.05, 0.95]` stał się roszczeniem wartości | audyt kuponu Części 4 |
| **F36** | `surplus` rankuje po 1/p | rozkłady z sekcji 4.3 |
| **F37** | trzy timeouty co 61 minut | przegląd logu requestów (**PODEJRZENIE**) |

F34 jest z nich najważniejsza jako lekcja: była **utajona w każdej** dzisiejszej
poprawce dopasowania (F16, F25 i okno F25), a TTL 7 dni znaczył, że ujawniłaby
się dopiero za tydzień.

Bramki na koniec: **343 testy przechodzą**, 2 pominięte, `ruff` i `mypy --strict`
czyste na `src/bet/sofa` i `scripts/sofa`.

---

## 2. Pomiary przed/po (Część 2)

| co mierzone | przed | po |
|---|---|---|
| metryki, które kiedykolwiek powstały | 15 / 30 | **25 / 28** |
| blokada przez niespójność strzałów | 21.2% | **2.0%** |
| kierunkowe obciążenie tej blokady | rożne 9 vs 9 | zniknęło |
| `p_central` dla OVER 2.5 setów | 0.4597 | **0.3251** (= prawda empiryczna) |
| niezgodność płci | 1 | **0** |
| odwrócona orientacja stron | 1 | **0** |
| tenis w `events/next` | 179 | **0** |
| przeciek z przyszłości / duplikaty / self-reference | — | **0** na 870 próbkach |

Trzy metryki nadal nie powstają: `xg_total`, `xg_for`, `tiebreaks_total`.
**Żadnej z nich Superbet nie wycenia**, więc nie są stratą.

### Skuteczność RESOLVE po sportach

| | baza (2. przebieg) | z błędem F25 | **finalnie** |
|---|---|---|---|
| piłka | 73.8% | 72.7% | 72.2% |
| tenis | 84.3% | 58.4% | **82.8%** |
| razem | 77.7% | 66.2% | **76.1%** |
| fixture'y w turniejach kobiecych | — | **0** | **56** |

Brakuje ~10 fixture'ów względem bazy. Zakładam, że to bramki F25 słusznie
odrzucają złe dopasowania (okno 6 h dla piłki, orientacja), ale **tego nie
zmierzono** — `PODEJRZENIE`.

---

## 3. Czego **nie** przetestowano

**F1, F2 i F11 — obsługa błędów, ponowień i bezpiecznika — nie zostały
sprawdzone na żywo i nie wolno ich uznać za działające.**

Na 20 072 requestów z tego dnia: **zero** odpowiedzi 403, 429 i 5xx, bezpiecznik
**ani razu** nie otworzył się (`CLOSED` w 100% wpisów). Jedyne zaobserwowane
zachowanie awaryjne to trzy timeouty z F37 — pojedyncze, nieeskalujące.

Kod tych ścieżek ma testy jednostkowe. Nie ma **żadnego** dowodu z ruchu
produkcyjnego, bo produkcja nie dostarczyła ani jednego błędu, na którym mógłby
zadziałać.

---

## 4. Kupon

40 singli z 920 wierszy VALUE (sheet: 10 960 wierszy). Audyt
(`scripts/sofa/audit_coupon.py`) zwraca **zero znalezisk strukturalnych i
arytmetycznych**: każdy wiersz kuponu istnieje w sheecie jako VALUE, każdy
wiersz VALUE albo trafił na kupon, albo ma zapisany powód odrzucenia, a
`required_odds`, `surplus`, `edge` i tożsamość zwężania odtwarzają się z
własnych pól wiersza.

### Weryfikacja ceny na żywo

Oferta Superbeta pobrana ponownie po zbudowaniu kuponu:

- **36 / 40** — nadal wystawione po tej samej cenie
- **3 / 40** — cena się ruszyła (−9.1%, +5.1%, −3.7%), wszystkie **nadal biją próg**
- **1 / 40** — **zdjęte z oferty**: `Widzew Łódź – Wieczysta Kraków, corners_for 1.5 UNDER`

### Rozkład (sekcja 4.3)

Wszystkie 40 wierszy to **piłka nożna**; tenis nie dał ani jednego. Rynki:
`goals_for` 22, `corners_for` 9, `shots_on_target_for` 3, `goals_total` 3,
reszta po jednym. Rozrzut lig jest szeroki — 27 różnych rozgrywek, żadna nie ma
więcej niż 4 wiersze.

Rozkład `p_bar`: **16** wierszy poniżej 0.15, **12** w 0.15–0.30, **12** w
0.30–0.50, **zero** powyżej 0.50.

---

## 5. Wierszy, których **nie** rekomenduję

Kryterium nie jest „przegra". Kryterium brzmi: **czy potrafię obronić liczbę,
którą model podstawił pod ten wiersz.**

### 5.1. Sześć wierszy, których własna próbka nigdy nie przekroczyła granicy

Model przypisuje im 5.8–13.1%, a w próbce, z której sam liczy środek, zdarzyło
się to **zero razy**:

| mecz | rynek | `p_bar` | próbka | kurs |
|---|---|---|---|---|
| Wisła Kraków – Śląsk Wrocław | `goals_for 4.5 OVER` | 0.089 | **0/9** | 75.00 |
| Polonia Bytom – Ruch Chorzów | `corners_for 0.5 UNDER` | 0.106 | **0/10** | 30.00 |
| Stade de Reims – Montpellier | `goals_for 4.5 OVER` | 0.058 | **0/9** | 45.00 |
| Monza – Sassuolo | `corners_for 0.5 UNDER` | 0.096 | **0/10** | 25.00 |
| IF Gnistan – HJK | `goals_total 0.5 UNDER` | 0.131 | **0/19** | 13.00 |
| Espanyol – Elche | `corners_for 0.5 UNDER` | 0.093 | **0/10** | 17.00 |

Trzy z nich to „drużyna nie wykona **ani jednego** rzutu rożnego". To nie jest
zdarzenie rzadkie — to zdarzenie, którego w danych nie ma.

### 5.2. Siedem dalszych, gdzie zdarzyło się to raz

`Brentford – Chelsea goals_for 5.5 OVER` (1/10, kurs 55), `Sokół Kleczew`,
`Zawisza Bydgoszcz`, `Kasımpaşa shots_on_target_for 0.5 UNDER`,
`VfL Wolfsburg goals_for 3.5 OVER`, `Brentford – Chelsea corners_for 9.5 OVER`,
`Central Córdoba shots_on_target_for 0.5 UNDER` (1/8).

Jedno trafienie na dziewięć czy dziesięć obserwacji nie odróżnia p=0.10 od
p=0.03. Przedział ufności obejmuje obie wartości, a cała teza tych wierszy
zależy od tego, która z nich jest prawdziwa.

**Razem 13 z 40 wierszy** opiera się na zdarzeniu widzianym co najwyżej raz.

### 5.3. Wiersz, którego już nie ma

`Widzew Łódź – Wieczysta Kraków, corners_for 1.5 UNDER` — zniknął z oferty
między zbudowaniem kuponu a kontrolą. Nie ma czego obstawiać.

### 5.4. Pięć wierszy, których nie udało mi się zweryfikować wstecz

`Briton Ferry Llansawel`, `FC Hertha Wels`, `UTA Arad`, `KS Polonia Nysa`,
`Fujairah FC` — w każdym z nich `subject` nie dopasował się do żadnej ze stron
fixture'u w moim skrypcie kontrolnym, więc **nie wiem**, jaka próbka za nimi
stoi. To wada skryptu kontrolnego, nie dowód usterki w pipelinie — ale wiersza,
którego nie sprawdziłem, nie zaliczam jako sprawdzonego.

### 5.5. Zastrzeżenie obejmujące **cały** kupon

Żaden wiersz nie ma `p_bar > 0.50`, a 16 ma poniżej 0.15. Dokładnie w tym
paśmie model zawyża `p` o **~39% względnie** (F36, pomiar wewnątrzpróbkowy).
Ranking bezwymiarowy usunął wzmocnienie tego obciążenia, ale **nie samo
obciążenie**. Dopóki nie zostanie ono skalibrowane na danych spoza jednego dnia,
kupon jako całość należy czytać jako **niezweryfikowany**, a nie jako
konserwatywny.

Do tego stałe `K_CENTRE`, `K_PRICE` i `MAX_LADDER_SIGMA` nadal nie są dopasowane
— każdy wiersz sam to zgłasza przez `UNFITTED_CONSTANTS`.

---

## 6. Co zostaje po tym dniu

Zmierzone i naprawione: 23 usterki. Zmierzone i świadomie nienaprawione:
obciążenie dolnego ogona (F36 §2) — bo poprawka na jednym dniu byłaby
dopasowaniem do szumu. Zaobserwowane i nierozpoznane: F37.

Najtańszy następny krok, jaki widzę, to **nie** kolejna poprawka modelu, tylko
zebranie drugiego i trzeciego dnia, żeby cokolwiek dało się kalibrować poza
próbką. `coverage_floor` już dziś mówi `NO_BASELINE — only 1 comparable past
run(s), need 3`.
