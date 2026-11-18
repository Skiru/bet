# Egzamin: stawka meczu (stan tabeli), piłka nożna kluby (2026-11-18/19)

**Werdykt: raport zerowy.** Żadna z 5 grup nie przeszła bramek zgłoszenia S1-S5 na rozwoju. **S4 (Delta
walidacyjna < 0) nie przechodzi w żadnej grupie**: poprawka pogarsza wynik poza próbą eksploracji w każdej grupie.
K = 0, więc reguła zaliczenia (c) (P1-P6) nie miała czego testować. Wszystkie grupy `NOT_SUBMITTED`. Zapieczętowane
wyniki egzaminu (2026-01-01 .. 2026-11-17) **nie zostały otwarte**. Nic do instalacji, żaden przełącznik.

- Specyfikacja: `stakes_prereg_football_2026-11-18.md` (zamrożona w 646b1317). Moduł stanów
  `stakes_football_2026-11-18/stakes_state.py`, sha256 `99e81fe7…1949`: zgodny na dysku, w commicie i w kopii
  przebiegu (G1 sprawdzone przez skrypt przed egzaminem).
- Skrypt: `scripts/sofa/measure_stakes_exam.py` (tylko odczyt, offline, kopia bazy; ruff i mypy --strict czyste),
  sha256 `9600636f…778d` (zapisany w rekordzie zamrożenia przed egzaminem).
- Propozycja współczynników: `stakes_football_2026-11-18/coefficients.json`, sha256 `fcd58aa0…a870`; tylko
  propozycja, nie jest instalowana (zero zaliczeń).
- Wynik egzaminu: `stakes_football_2026-11-18/exam_result.json` (K = 0). Artefakty przebiegu:
  `stakes_football_2026-11-18/run/` (explore, validate, power, submission, rekordy hashy, `looks.md`, devtest).
- Linia logu: `stakes_exam_log.md`, 2026-11-18T23:26:55Z.

## Werdykt na grupę i stan

S1/S2: p z 200 permutacji (minimum 1/201 = 0.005). S3: kierunek z punktu (średnia ważona odwrotnością wariancji po
metrykach grupy, dane eksploracji); niezgodny kierunek usuwa kolumny own_ i opp_ tego stanu (M4). S4: Delta na
walidacji (2025-09-01 .. 2025-12-31), nat/mecz, ujemne = lepiej; przedział 95% z bootstrapu gospodarze x goście
(opisowo; bramka to wartość punktowa). S5: najlepsza kolumna (strony-mecze egzaminu z pliku X) wobec n_wymagane
przy |c| = 0.03.

| grupa | S1 p | S2 p | S3 (stany po S3) | S4 Delta [95%] | mecze / wiersze walidacji | S5 najlepsza / wymagane | werdykt |
|---|---|---|---|---|---|---|---|
| goals | 0.005 | 0.005 | DEAD **usunięty** (own_DEAD +0.222); MUST_WIN, SECURED zostają | **+0.000204** [-0.001014, +0.001427] | 48,729 / 315,123 | own_SECURED 16,258 / 16,372 **nie** | NOT_SUBMITTED |
| football_result | 0.005 | 0.005 | DEAD **usunięty** (own_DEAD +0.219); MUST_WIN, SECURED zostają | **+0.000081** [-0.000149, +0.000314] | 49,293 / 49,293 | own_SECURED 16,261 / 9,561 tak | NOT_SUBMITTED |
| corners | **0.791** | **0.766** | wszystkie zgodne | **+0.000119** [-0.001282, +0.001476] | 7,622 / 38,326 | own_SECURED 2,424 / 6,200 **nie** | NOT_SUBMITTED |
| shots_sot | 0.030 | **0.423** | SECURED i DEAD **usunięte** (own_SECURED +0.015, own_DEAD +0.044); zostaje MUST_WIN | **+0.001237** [-0.001688, +0.004253] | 6,311 / 69,162 | opp_MUST_WIN 1,100 / 3,746 **nie** | NOT_SUBMITTED |
| cards_fouls | 0.015 | **0.070** | bez kierunku (nie dotyczy) | **+0.002801** [-0.001754, +0.007465] | 8,116 / 37,174 | opp_SECURED 2,515 / 2,493 tak | NOT_SUBMITTED |
| pula shots_sot + corners | - | - | - | - | - | opp_MUST_WIN 1,368 / 4,455 **nie** | nie utworzona (członkowie nie przechodzą S1-S4) |

W układzie grupa x stan (jednostką egzaminu jest grupa, więc stan dzieli werdykt grupy):

| grupa | MUST_WIN | SECURED | DEAD |
|---|---|---|---|
| goals | NOT_SUBMITTED (S4, S5) | NOT_SUBMITTED (S4, S5) | NOT_SUBMITTED (S3: usunięty) |
| football_result | NOT_SUBMITTED (S4) | NOT_SUBMITTED (S4) | NOT_SUBMITTED (S3: usunięty) |
| corners | NOT_SUBMITTED (S1, S2, S4, S5) | NOT_SUBMITTED (S1, S2, S4, S5) | NOT_SUBMITTED (S1, S2, S4, S5) |
| shots_sot | NOT_SUBMITTED (S2, S4, S5) | NOT_SUBMITTED (S3: usunięty) | NOT_SUBMITTED (S3: usunięty) |
| cards_fouls | NOT_SUBMITTED (S2, S4) | NOT_SUBMITTED (S2, S4) | NOT_SUBMITTED (S2, S4) |

Reguła (c) (P1 Holm, P2 materialność, P3 linie, P4 kalibracja >= 0.70, P5 warstwy, P6 znak) **nie była liczona
na egzaminie** (K = 0). Na danych walidacji (devtest, poniżej) żadna grupa nie przeszłaby P1: Delta > 0 wszędzie.

## Współczynniki zamrożone (eksploracja + walidacja, < 2026-01-01; c_shr = c · tau²/(tau² + SE²), tau 0.05)

Gole na mecz drużyny (`goals_for`, 192,488 wierszy):

| kolumna | surowy | SE | zamrożony |
|---|---|---|---|
| own_MUST_WIN | +0.0269 | 0.0159 | +0.0244 |
| own_SECURED | -0.0488 | 0.0125 | -0.0459 |
| opp_MUST_WIN | +0.0389 | 0.0143 | +0.0360 |
| opp_SECURED | +0.1037 | 0.0133 | +0.0968 |

football_result (`goals_for` na środkach ratingu, 203,322 wiersze): own_MUST_WIN +0.0371, own_SECURED -0.0232,
opp_MUST_WIN +0.0467, opp_SECURED +0.0780. Rożne, strzały, kartki/faule: |c| przeważnie < 0.04 przy SE 0.02-0.09
(pełna tabela w `coefficients.json`). `fouls_1h_for` / `fouls_2h_for`: 27 wierszy w eksploracji, pominięte
(< 2,000).

Co to znaczy: na rozwoju stan tabeli ma wyraźny związek z golami (S1 i S2 p = 0.005; drużyna, której przeciwnik
ma pewne miejsce, strzela ~10% więcej niż przewiduje model) - ale poprawka zamrożona na eksploracji **nie poprawia**
prognozy na walidacji (Delta > 0 w każdej grupie). Kierunek DEAD w golach jest przeciwny hipotezie motywacji: obie
strony meczu "o nic" strzelają więcej (own_DEAD +0.22, opp_DEAD +0.28 w eksploracji), więc DEAD wypadł przez S3.

## Odchylenia (zawsze wybrana opcja ostrożniejsza)

1. **Odtworzenie bez `--schedule-term`:** `calibrate_from_cache` nie ma tej flagi. Zainstalowany człon terminarza
   (`config/sofa_schedule_terms.json`) nałożony offline na środki ratingu ścieżki (ii) (football_result); ścieżka
   (i) (liczniki) go nie dotyczy.
2. **Dodana `--cards-closeness-off`**, jak w dzisiejszym SHEET (od 2026-11-10).
3. **S5 liczy strony-mecze** (jednostka z sekcji 8 specyfikacji), nie wiersze; liczba wierszy podana obok
   w `power.json`.
4. **G1 bez commitu przed egzaminem:** współczynniki i skrypt zahashowane w `run/freeze_record.json` (23:22:59Z)
   przed policzeniem S5 i przed egzaminem; zgłoszenie w `run/submission.json` zahashowane osobno
   (`submission_record.json`); egzamin sprawdził wszystkie trzy hashe i moduł.
5. **Populacja:** kluby mężczyzn, obie strony nie-AMBIGUOUS; kobiety tylko jako warstwa P5 (ze współczynnikami
   mężczyzn).
6. **S3 kolumn opp_** czytane regułą punktową (średnia ważona po metrykach), jak own_.
7. **Warstwy `tb` i "pozostałe <= 3"** zdefiniowane na poziomie meczu.
8. **Tercja tabeli w S2:** pozycja = 1 + liczba drużyn z większą liczbą punktów.
9. **D10 z wzoru terminarza:** środek = końcowy / mnożnik fazy x exp(c_dev) z zatwierdzonego `season_phase_dev.json`.
10. **P6 wymagane do PASS** (spec: "opisowo"; ostrożniej).
11. **Egzamin obejmowałby mecze ALIVE/ALIVE** (różnica zero); nie miało znaczenia przy K = 0.
12. **Pula shots_sot + corners** tylko gdy obaj członkowie przechodzą S1-S4 i jednemu brakuje S5 samemu; wtedy
    zastępuje oba. Tu nie powstała.
13. **Log egzaminu:** plik istniał (linia badania sportów, 2f08d0d7) z kolumnami
    `UTC | badanie | spec SHA | sha256 współczynników | werdykty`, innymi niż log terminarza; dopisano linię
    w kolumnach istniejącego pliku, sha256 modułu w polu werdyktów.
14. **Okno egzaminu:** 2026-01-01 .. 2026-11-17 (replay `--to 2026-11-18`, koniec wyłączny).
15. **Odtworzenie w jednym procesie** (po nieudanych próbach kawałkami, zabitych przez watchdog przy 8 / 16 /
    26 GB w trakcie ładowania historii, bez zapisanych wyników): pełny replay 2024-07-01 .. 2026-11-18,
    watchdog 46 GB, **wyjście normalne rc = 0, szczyt 34.00 GB** (00:21:03 lokalnie). Etapy skryptu: szczyt
    <= 4.66 GB.
16. **Aneks A:** koordynator wspomniał "Aneks A" - istnieje tylko w `stakes_prereg_sports_2026-11-18.md`
    (32ba661e); specyfikacja piłkarska go nie ma. Inwentarz i tabela mocy wzięte z jej sekcji 7-8; S5 policzone
    ponownie z nowego pliku X.

## Wszystko, na co patrzono (G5)

- Faza A powtórzona: 987 grup club_ok, 206,710 wierszy - zgodne z inwentarzem specyfikacji.
- **Eksploracja na niepełnym rozwoju (przed końcem replayu, test instalacji):** recorder trzymał ogon każdego
  miesiąca w pamięci do wyjścia, więc pliki rozwoju na dysku były niepełne (brak 2024-07..09, 2024-12, 2025-01,
  2025-06..07, football_result 0 meczów). Uruchomiono `explore` jako test hydrauliki i zobaczono S1/S2/S3 tej
  niepełnej próby (np. shots_sot S1 p 0.63, cards_fouls S1 p 0.07); wynik odłożony
  (`data/refit_2026-11-18_stakes/partial_plumbing/`), nieużyty. Próba devtest na niej padła (brak prognoz).
  Kod nie był zmieniany po tym spojrzeniu w sposób zależny od wyników (tylko zakres warstw P5 do odczytywanego
  poziomu i format linii logu).
- Pełna eksploracja (`run/explore.json`), **jedno** zalogowane spojrzenie walidacyjne na grupę (`run/looks.md`).
- Devtest (tylko rozwój): maszyneria egzaminu na miesiącach walidacji z prawdziwymi y rozwoju i współczynnikami
  z samej eksploracji (`run/exam_devtest_result.json`): Delta identyczne z walidacją, wszystkie grupy NOT_PASSED.
  Niezalogowane.
- S5 z pliku X egzaminu (bez y) po zamrożeniu (`run/power.json`); test fake (K = 0, pusty).
- Wyniki egzaminu: magazyn `full/all/exam_y` (recorder) i `exam_y/fr_y.pkl` (zapieczętowane gole 90 min, prep)
  zapisane, **nigdy nie odczytane**.

`UNFITTED_CONSTANTS`: granica Z (3 przy n <= 16, inaczej 4), granice {1, n - Z}, enumeracja dokładna r <= 8,
12 drużyn, 25% wywnioskowanych, 30 dni sezonu w toku, tau 0.05.
