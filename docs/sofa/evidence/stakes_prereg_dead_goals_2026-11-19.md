# Pre-rejestracja: strona w stanie DEAD a liczba goli - piłka, ligi klubowe (2026-11-19)

**Status: ZAMROŻONE commitem tego pliku** (SHA commitu = "spec SHA" egzaminu), **przed** spojrzeniem walidacyjnym.
Wzór: `stakes_prereg_football_2026-11-18.md` (spec 646b1317) - tam, gdzie ten dokument milczy, obowiązuje tamten
dosłownie (a przez niego `schedule_context_prereg_2026-11-09.md`, reguła (c), G1-G5).

**To jest trop, nie potwierdzenie.** Kierunek hipotezy został wybrany **po** zobaczeniu eksploracji z 2026-11-18:
tam stan DEAD poszedł **przeciw** hipotezie motywacji (obie strony meczu z drużyną "martwą" strzelały więcej:
gole own_DEAD +0.222, opp_DEAD +0.283; `run/explore.json` badania 11-18) i dlatego wypadł przez S3 - nigdy nie miał
spojrzenia walidacyjnego. Eksploracja nie jest więc tu dowodem; dowodem może być tylko walidacja (pierwsze spojrzenie
na DEAD) i egzamin na warstwie 2026, której wyników nikt nie otworzył.

## 1. Hipoteza (jedyna)

**Strona, której własny stan albo stan rywala w chwili startu to DEAD, strzela więcej goli, niż przewiduje końcowy
środek modelu.** Poprawka strony s: t_s = beta_own_DEAD · [stan_s = DEAD] + beta_opp_DEAD · [stan rywala = DEAD];
oba współczynniki dodatnie (kierunek S3). "Pomogło" = grupa `goals` zalicza regułę (c) (sekcja 7).

DEAD (zamrożony moduł, sekcja 4.4 wzoru): wszystkie granice {1, n - Z} rozstrzygnięte, a strona nie jest pewnie ponad
żadną z nich - w ligach klubowych to w praktyce drużyna matematycznie spadła / zamknięta w strefie spadku.

## 2. Co już widziano (G5)

| kiedy | co | dane | wpływ |
|---|---|---|---|
| 2026-11-18 | eksploracja badania 11-18 (`stakes_football_2026-11-18/run/explore.json`), model z 6 kolumnami (MUST_WIN, SECURED, DEAD x own / opp) | 2024-07 .. 2025-08 | **kierunek tej hipotezy**; współczynniki DEAD znane (gole: own +0.222, opp +0.283; football_result: own +0.219, opp +0.316) |
| 2026-11-18 | eksploracja na niepełnym rozwoju (`partial_plumbing/`) | część 2024-07 .. 2025-08 | odłożona, nieużyta |
| 2026-11-18 | **jedno** spojrzenie walidacyjne grupy goals - model MUST_WIN + SECURED (DEAD usunięty) | 2025-09 .. 2025-12 | Delta +0.000204; y walidacji goli widziane zbiorczo przy **innym** modelu; DEAD nie był w nim |
| 2026-11-18 | devtest (maszyneria egzaminu na miesiącach walidacji, współczynniki z samej eksploracji, ten sam model bez DEAD) | 2025-09 .. 2025-12 | Delta jak wyżej; niezalogowany |
| 2026-11-18 | S5 z pliku X egzaminu (bez y): `stakes_football_2026-11-18/run/power.json` | X 2026 | liczebności ekspozycji DEAD (sekcja 6), **bez wyników** |
| 2026-11-19 | ta pre-rejestracja | - | żadnej nowej liczby wg stanu nie liczono |

Spojrzenie walidacyjne tego badania będzie więc **drugim** spojrzeniem na walidację grupy goals (G5: <= 3) i pierwszym
z kolumnami DEAD. Warstwa egzaminu 2026 (`exam_y/fr_y.pkl`, `full/all/exam_y/y/*`, 30 plików) jest zapieczętowana
(chmod 000, manifest `data/refit_2026-11-18_stakes/exam_seal_manifest.json`, 2026-11-19T07:38:00Z; atime każdego
pliku przed pieczęcią = jego mtime, czyli nigdy nieczytany); otwiera ją tylko tryb egzaminu skryptu (commit 57e988bd),
który loguje każde otwarcie.

## 3. Okresy, dane, populacja, stan - bez zmian wobec wzoru

- Okresy (granica = start meczu UTC): eksploracja 2024-07-01 .. 2025-08-31, walidacja 2025-09-01 .. 2025-12-31,
  egzamin **2026-01-01 .. 2026-11-17** (raz).
- Plik X: **ten sam** replay co 11-18 (`data/refit_2026-11-18_stakes/full/all`, kopia bazy, flagi z odchyleń 1-2
  raportu 11-18; znacznik `DONE.json` dopisany 2026-11-19 z logu `full46.log`: rc 0, 2026-11-18T23:21:03Z). Brak
  nowego odtworzenia.
- Populacja: mecze klubowe mężczyzn w grupach tabeli z sekcji 3 wzoru, obie strony nie-AMBIGUOUS; kobiety tylko jako
  warstwa P5 (ze współczynnikami mężczyzn). Środek bazowy = środek końcowy / mnożnik fazy x exp(c_dev) (D10, jak
  odchylenie 9 raportu 11-18).
- Moduł stanu: `docs/sofa/evidence/stakes_football_2026-11-18/stakes_state.py`, sha256
  `99e81fe70f6ed6855afb6264e20c8cdf0798126463ca5cba69c958233bee1949` (sprawdzany przez skrypt przed egzaminem).

## 4. Grupa i model

- **Jedna grupa: `goals`** - `goals_for`, `goals_1h_for`, `goals_2h_for` i ich `_total` (suma środków stron, każda ze
  swoim t), droga (i) na końcowym środku. **K <= 1.**
- **`football_result` nie wchodzi.** Hipoteza mówi o liczbie goli; 1X2 / DC / DNB to inny estymand (kto wygrywa), na
  który symetryczny wzrost goli działa tylko drugorzędnie (przez remisy), a asymetria own / opp byłaby drugą,
  inaczej umotywowaną hipotezą. Dodanie jej podzieliłoby alfa (Holm) bez własnego uzasadnienia. Rożne, strzały,
  kartki: nie (hipoteza nie dotyczy ich; nie oglądano ich wg DEAD poza eksploracją 11-18).
- **Kolumny: tylko `own_DEAD`, `opp_DEAD`**; odniesienie = każdy inny stan (ALIVE, MUST_WIN, SECURED). Model jest
  dopasowany dokładnie w tej postaci, w jakiej byłby stosowany (poprawka tylko dla DEAD); MUST_WIN / SECURED badania
  11-18 nie wracają.
- Estymacja jak wzór sekcja 6: Poisson GLM z offsetem log(środek), efekty stałe drużyna-sezon, SE klastrowe
  (drużyna), ściągnięcie c_shr = c · tau² / (tau² + SE²), tau = 0.05, na metrykę. Zamrożone = ściągnięte z
  eksploracji + walidacji (< 2026-01-01).

## 5. Bramki zgłoszenia S1-S4 (rozwój)

- **S1 / S2**: permutacje jak wzór (200 powtórzeń; S1 w obrębie drużyna-sezon, S2 w obrębie liga-sezon x tercja tabeli
  x decyl postępu), na eksploracji, kolumny DEAD; p < 0.05. Uwaga: eksploracja była już oglądana - S1 / S2 to tylko
  bramka spójności, nie świeży dowód.
- **S3**: oba kierunki dodatnie (średnia ważona odwrotnością wariancji po metrykach grupy, eksploracja, kolumny DEAD).
  Kierunek wybrano z tych danych, więc S3 nie jest dowodem; niezgodny kierunek usuwa obie kolumny (M4) = brak
  poprawki = NOT_SUBMITTED.
- **S4**: **jedno** zalogowane spojrzenie walidacyjne (`looks.md` badania): współczynniki z samej eksploracji,
  Delta na walidacji (nat / mecz) < 0 w punkcie; przedział 95% z bootstrapu gospodarze x goście opisowo.

## 6. S5 - moc przy zamrożonym współczynniku (zmiana wobec wzoru, z powodem)

n_wymagane(c) = 7.85 · (1/mu + alpha) · 1.75 / c², mu / alpha = średni środek / dyspersja wierszy `_for` grupy
na pliku X egzaminu (bez wyników). **c = |zamrożony, ściągnięty współczynnik `goals_for` danej kolumny|**; grupa
przechodzi S5, gdy którakolwiek zachowana kolumna ma tyle stron-meczów egzaminu z kolumną = 1, ile jej własne
n_wymagane.

Powód: wzór liczył moc przy |c| = 0.03 (próg materialności P2), bo spodziewał się efektów 3-5%. Dla DEAD to
niemożliwe z konstrukcji: na egzaminie jest ok. 2 930 stron own_DEAD i 2 945 opp_DEAD (plik X, `power.json` 11-18,
bez y), a n_wymagane(0.03) = 16 372 - badanie nie mogłoby przejść niezależnie od prawdy. Moc liczona jest przy
efekcie, który zostałby zainstalowany - współczynniku **po ściągnięciu** (nie surowym +0.22 z eksploracji, który
niesie klątwę zwycięzcy). Przy mu 1.124 i alpha 0.183 (11-18) oznacza to: S5 przechodzi, gdy zamrożone |c| >= ok.
0.071 dla kolumny z ok. 2 930 stronami.

## 7. Reguła zaliczenia (c) - jak wzór sekcja 9, z jedną zmianą

Delta = średnia po meczach egzaminu [S_treat - S_base] (NB log score, suma wierszy grupy meczu; ujemne = lepiej).
PASS wtedy i tylko wtedy, gdy wszystkie:

- **P1**: jednostronna górna granica 95% Delty < 0 (bootstrap gospodarze x goście, 2 000; Holm przy K <= 1 trywialny);
- **P2 (zmiana)**: |c| zamrożone >= 0.03 dla co najmniej jednej kolumny DEAD **i** wiersze, których dotyka poprawka
  (own_DEAD = 1 lub opp_DEAD = 1), to >= 2% wierszy `_for` grupy na egzaminie. Powód: osobno każda kolumna ma ok.
  1.8% wierszy (own 6 126, opp 6 238 z 344 854; plik X, bez y) - kubeł na kolumnę oblałby P2 z konstrukcji, choć
  poprawka działa na sumie obu (ok. 3.6%). Liczebności są bez wyników; zmiana jest zapisana przed walidacją.
- **P3**: linie skalibrowane (krzywe z rozwoju) Delta <= 0 i górna 95% < +2e-4 nat / wiersz;
- **P4**: kalibracja >= 0.70 na p bazowym, slack 0.005;
- **P5**: warstwy wzoru (kobiety, tercyle |s| faworyta, kontynentalne / krajowe, rozgrywki z rundami pucharowymi,
  dokładne / ograniczenia, `tb`, pozostałe <= 3): górna 95% < +5e-4 przy >= 2 000 wierszy; inne grupy: brak (K <= 1);
- **P6**: współczynnik z ponownego dopasowania na egzaminie ma znak rozwoju - **wymagane do PASS** (jak odchylenie 10
  raportu 11-18, tu zapisane jako reguła).

**Wynik nic nie instaluje i niczego nie przełącza.** PASS = propozycja dla operatora (przełącznik od następnego dnia
00:00Z, krzywe przefitowane na kopii bazy, test w przód - dopiero po jego decyzji). NOT_PASSED / NOT_SUBMITTED =
raport zerowy.

## 8. Procedura i strażnicy

Skrypt `scripts/sofa/measure_stakes_exam.py --study dead_goals` (commit 57e988bd; badanie w logu:
`stakes_dead_goals_2026-11-19`), kolejno, na wspólnych wejściach 11-18 (`dev.pkl`, pickle prep):

1. commit tego pliku (spec SHA);
2. `explore` (S1-S3 na eksploracji, kolumny DEAD);
3. `validate --groups goals` - jedno zalogowane spojrzenie (S4);
4. `freeze --spec-sha <SHA>` (współczynniki do `docs/sofa/evidence/stakes_dead_goals_2026-11-19/coefficients.json`,
   rekord z hashami skryptu, strażnika i specyfikacji), `power` (S5), `submit`;
5. commit współczynników, rekordów i zgłoszenia;
6. `exam --mode fake` (hydraulika, niezalogowana), potem `exam --mode exam --spec-sha <SHA>`: odmawia bez czystego
   `DONE.json` replayu, bez commitu współczynników / zgłoszenia / skryptu / strażnika / modułu (równych HEAD), przy
   zerwanej pieczęci i przy istniejącej linii tego badania w `stakes_exam_log.md`; pliki y otwiera tylko przez
   odpieczętowanie z kontrolą sha256, każde otwarcie loguje do `run/exam_access.log` i pieczętuje z powrotem;
7. raport `stakes_exam_dead_goals_2026-11-19.md`, jedna linia w `stakes_exam_log.md`.

K = 0 po S1-S5 = egzamin nieotwarty (pieczęć zostaje).

`UNFITTED_CONSTANTS` (jak wzór): granica Z (3 przy n <= 16, inaczej 4), granice {1, n - Z}, enumeracja dokładna
r <= 8, 12 drużyn, 25% wnioskowanych, 30 dni sezonu w toku, tau 0.05.
