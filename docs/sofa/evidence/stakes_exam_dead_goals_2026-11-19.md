# Egzamin: strona w stanie DEAD a liczba goli, piłka nożna kluby (2026-11-19)

**Werdykt: NOT_PASSED.** Grupa `goals` (K = 1) przeszła S1-S5 i na egzaminie 2026 spełnia P1, P2, P3, P4 i P6, ale
**oblewa P5 w jednej zapisanej z góry warstwie (`tb`)**. Reguła (c) wymaga wszystkich sześciu - nic nie jest proponowane
do instalacji, żaden przełącznik. Według reguły to raport zerowy. Mocny sygnał poza P5 jest opisany niżej, bo raport
pokazuje także to, co wspiera hipotezę (to nie jest jej promowanie).

- Specyfikacja: `stakes_prereg_dead_goals_2026-11-19.md`, zamrożona w **9679350c** (przed spojrzeniem walidacyjnym).
  To był **trop**: kierunek wybrano po eksploracji z 11-18. Testowany na walidacji (pierwsze spojrzenie z DEAD) i na
  zapieczętowanej warstwie 2026.
- Skrypt: `scripts/sofa/measure_stakes_exam.py --study dead_goals` (strażnicy z 57e988bd), sha256 `df6f06f2…b3af`.
  Strażnik `stakes_exam_guard.py` sha256 `6a6e1c03…46fc`. Moduł stanu sha256 `99e81fe7…1949`.
- Współczynniki: `stakes_dead_goals_2026-11-19/coefficients.json`, sha256 `89c90e6a…54b0`. Zgłoszenie: `run/submission.json`
  (sha256 `5f87639f…6697`). Zamrożenie i zgłoszenie zacommitowane w **4cf1a89b**, przed egzaminem.
- Wynik: `stakes_dead_goals_2026-11-19/exam_result.json`; log dostępu `run/exam_access.log`; linia w `stakes_exam_log.md`
  (2026-11-19T09:51:29Z).

## Rozwój (S1-S5)

| bramka | wynik |
|---|---|
| S1 (permutacja w drużyna-sezon, eksploracja) | p = 0.005 (minimum 1/201) |
| S2 (permutacja w liga-sezon x tercja x decyl postępu) | p = 0.005 |
| S3 (kierunki dodatnie, eksploracja, tylko kolumny DEAD) | own_DEAD +0.318, opp_DEAD +0.211 - obie zostają. Kierunek wybrano z tych danych, więc nie jest to dowód |
| **S4 (jedno spojrzenie walidacyjne, 2025-09 .. 12)** | **Delta -0.000602 [-0.002420, +0.001172]** nat / mecz, 48 729 meczów / 315 123 wiersze - zalicza (punkt < 0) |
| S5 (moc przy zamrożonym współczynniku) | own_DEAD: n_wymagane 320 przy c = 0.2147 wobec 2 930 stron egzaminu - zalicza (opp_DEAD: 469 przy 0.1773 wobec 2 945) |

Zgłoszono: `goals`, K = 1.

Zamrożone (eksploracja + walidacja, < 2026-01-01; surowy / SE / ściągnięty, tau 0.05):

| metryka | own_DEAD | opp_DEAD | wiersze |
|---|---|---|---|
| goals_for | +0.2725 / 0.0259 / **+0.2147** | +0.2067 / 0.0204 / **+0.1773** | 192 488 |
| goals_1h_for | +0.2639 / 0.0433 / +0.1509 | +0.2544 / 0.0282 / +0.1930 | 134 042 |
| goals_2h_for | +0.3125 / 0.0382 / +0.1972 | +0.1494 / 0.0262 / +0.1173 | 133 887 |

Odniesienie to każdy inny stan (ALIVE, MUST_WIN, SECURED). exp(0.2147) = +24% goli strony "martwej", exp(0.1773) = +19%
goli jej rywala, względem końcowego środka modelu.

## Egzamin 2026-01-01 .. 2026-11-17 (74 079 meczów, 517 611 wierszy)

| kryterium | wynik | zalicza |
|---|---|---|
| P1 Delta / mecz | **-0.003482** [-0.006203, -0.000764], p jednostronne 0.0065, górna przy poziomie Holma 0.05: -0.001201 | tak |
| (na wiersz) | -0.000498, górna 95% -0.000158 | - |
| P2 materialność | wszystkie 6 |c| >= 0.03; wiersze, których dotyka poprawka: 3.41% (own 1.78%, opp 1.81%) | tak |
| P3 linie skalibrowane | -0.000427 / wiersz, górna 95% -0.000323 (9 316 998 linii) | tak |
| P4 kalibracja >= 0.70 | luka bazowa 0.00093, z poprawką 0.00144 (<= +0.005) | tak |
| **P5 warstwy** | 12 z 13 bramkowanych warstw < +5e-4; **`tb`: +0.001085 / wiersz, górna 95% +0.003985 (7 272 wiersze)** | **nie** |
| P6 znak na egzaminie | 6 / 6 zgodnych: goals_for own +0.189 (SE 0.016), opp +0.180 (0.012); 1H own +0.175, opp +0.268; 2H own +0.167, opp +0.134 | tak |

Warstwy P5 (punkt / górna 95% na wiersz): faworyt |s| T1 -0.00029 / +0.00013, T2 -0.00038 / +0.00009, T3 -0.00077 /
-0.00008; krajowe -0.00050 / -0.00017 (kontynentalne: 0 wierszy, w populacji ligowej z konstrukcji); z rundami pucharowymi
-0.00071 / -0.00015, bez -0.00036 / +0.00005; dokładne -0.00487 / -0.00025, ograniczenia -0.00031 / -0.00004; **tb +0.00109 /
+0.00399**, bez tb -0.00052 / -0.00019; pozostałe <= 3 -0.00264 / -0.00066, > 3 -0.00012 / +0.00004; kobiety (współczynniki
mężczyzn) -0.00111 / +0.00016 (Delta / mecz -0.0089 na 4 206 meczach).

**Co to znaczy.** Poza warstwą `tb` wszystko idzie w jedną stronę: poprawka DEAD poprawia prognozę goli na danych
2026, których nikt wcześniej nie widział (P1 p = 0.0065, przedział nie dotyka zera), linie skalibrowane też zyskują, a
współczynniki dopasowane od nowa na samym 2026 (+0.17 .. +0.27) są blisko zamrożonych. Strona spadła / zamknięta w
strefie spadku i jej rywal strzelają ~20% więcej goli, niż przewiduje dzisiejszy środek. To przeciwnie do hipotezy
motywacji ("martwy" zespół słabnie, rywal bez zmian). Warstwa `tb` (mecze, w których stan którejkolwiek strony zależy od
rozstrzygnięcia remisu punktowego - przy DEAD głównie rywal z MUST_WIN `tb`) jest mała (7 272 wiersze, ~1.4%), a jej
górna granica przekracza próg nie-gorzej. Reguła nie przewiduje wyjątku dla jednej warstwy, więc werdykt jest
NOT_PASSED. Czy to szum w małej warstwie, czy realne pogorszenie, ta reguła nie rozstrzyga - na pewno nie wolno
jej "dociągnąć" po fakcie.

Dalszy krok należy do operatora. Werdykt zamyka tę hipotezę na historii (G4: nic już nie zmieniamy). Uczciwa droga
dalej to **nowy, zarejestrowany z góry test w przód** na danych z 2026-11-20 i później (np. `T-STAKES-DEAD-GOALS-FORWARD`,
z tą samą poprawką i z `tb` jako warstwą bramkowaną), nie ponowny egzamin na 2026.

## Pieczęć i dostęp (G2)

- 30 plików wyników egzaminu zapieczętowano 2026-11-19T07:38:00Z (chmod 000, manifest
  `data/refit_2026-11-18_stakes/exam_seal_manifest.json`). Atime każdego pliku przed pieczęcią był równy jego mtime,
  czyli plik nigdy nie był czytany. Haszowanie przy pieczętowaniu czytało surowe bajty (strumieniowy sha256, bez
  deserializacji) i przesunęło atime.
- Egzamin (jedyny kod, który odpieczętowuje) otworzył **29 plików `full/all/exam_y/y/*`** (09:51:30Z, sha256 każdego
  zgodny z manifestem) i zapieczętował je z powrotem (09:52:30Z); 58 linii w `run/exam_access.log`. `exam_y/fr_y.pkl`
  (gole 90 min dla football_result) **nie był otwarty**. Po egzaminie wszystkie 30 plików znów mają tryb 000.
- Preflight przeszedł: `DONE.json` replayu (jednorazowy, z `full46.log`), commit + zgodność z HEAD współczynników,
  rekordów, zgłoszenia, skryptu, strażnika i modułu, pieczęć nienaruszona, brak linii badania w logu.

## Odchylenia i wszystko, na co patrzono

1. **Drugie spojrzenie na walidację grupy goals.** Pierwsze było 11-18 (model MUST_WIN + SECURED, Delta +0.000204),
   to drugie, pierwsze z kolumnami DEAD (G5 <= 3). Zapisane w specyfikacji przed spojrzeniem.
2. **S5 i P2 inne niż wzór 11-18.** Zmiany zapisane i zacommitowane przed walidacją, na liczebnościach bez wyników:
   S5 liczone przy zamrożonym współczynniku, P2 na wierszach, których dotyka poprawka. Przy P2 na kolumnę (1.78% /
   1.81% < 2%) grupa oblałaby P2 z konstrukcji. Przy S5 na 0.03 (n_wymagane 16 372 wobec 2 930) też.
3. **Odpieczętowanie otwiera całe pliki y.** Każdy plik `exam_y/y` zawiera wyniki 2026 wszystkich rynków (gole,
   rożne, kartki, tenis...). Przeszły przez pamięć i zostały odfiltrowane do goli. Policzone zostały tylko gole, ale
   dla przyszłych badań te pliki należy traktować jako otwarte w całości 2026-11-19T09:51Z (log dostępu).
4. **`explore` przed `validate`** (eksploracja, już oglądana) i **`exam --mode fake`** przed egzaminem (hydraulika,
   y losowane z ramienia bazowego, bez logu, bez dostępu do pieczęci) - jak 11-18.
5. **P6 wymagane do PASS** (wzór: opisowe) - zapisane w specyfikacji; tu i tak zalicza.
6. **Warstwa `continental` ma 0 wierszy** (populacja = ligi krajowe). Nie jest bramkowana - jak 11-18.
7. **Brak nowego replayu.** Plik X to replay z 11-18. Jego `DONE.json` dopisano ręcznie 2026-11-19 z logu (rc 0,
   2026-11-18T23:21:03Z), bo stary recorder nie pisał znacznika.
8. Testy bramek uruchamiano na drzewie z cudzymi niezacommitowanymi zmianami (`build_slip.py`, `slip_builder.py`,
   `CLAUDE.md` i inne). Nie dotykano ich ani nie commitowano.

`UNFITTED_CONSTANTS`: granica Z (3 przy n <= 16, inaczej 4), granice {1, n - Z}, enumeracja dokładna r <= 8, 12 drużyn,
25% wywnioskowanych, 30 dni sezonu w toku, tau 0.05.
