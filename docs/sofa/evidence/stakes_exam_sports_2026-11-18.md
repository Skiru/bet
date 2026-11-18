# Egzamin: stawka meczu w hokeju, koszykówce i siatkówce (2026-11-18)

**Werdykt: raport zerowy.** Żadna z 6 grup nie przeszła bramek zgłoszenia S1-S5 na rozwoju (22/23 + 23/24 + 24/25),
więc K = 0 i reguła zaliczenia (P1-P6) nie miała czego testować. Wszystkie grupy: `NOT_SUBMITTED`. Zapieczętowane
wyniki egzaminu (25/26) **nie zostały otwarte** (odchylenie 10). Nic do instalacji, brak `coefficients.json`.

Specyfikacja: `stakes_prereg_sports_2026-11-18.md` (zamrożona w 646b1317, Aneks A 32ba661e).
Skrypt: `scripts/sofa/measure_stakes_exam_sports.py` (tylko odczyt, offline; ruff i mypy --strict czyste),
sha256 `cce1544b…eb0e6`. Wyniki: `docs/sofa/evidence/stakes_sports_2026-11-18/run/`.

## Werdykt na grupę

Δ S4 = średnia po meczach rozwoju w oknie z [S_treat - S_base] przy "zostaw jeden sezon"; dodatnie = gorzej. Bramka
S4 to wartość punktowa (sekcja 8), więc przedziału nie liczono.

| grupa | S1 p (perm.) | S2 placebo | S3 znaki | S4 Δ (nat/mecz) | mecze w oknie | werdykt |
|---|---|---|---|---|---|---|
| hk_goals | 0.005 | **nie** | tak | **+0.00261** | 5,632 | NOT_SUBMITTED |
| hk_result | 0.005 | **nie** | tak | **+0.00075** | 5,632 | NOT_SUBMITTED |
| bb_points | 0.005 | tak | **nie** | **+0.00640** | 11,358 | NOT_SUBMITTED |
| bb_result | 0.005 | tak | **nie** | **+0.00224** | 11,358 | NOT_SUBMITTED |
| vb_points | 0.005 | tak | **nie** | **+0.00231** | 4,089 | NOT_SUBMITTED |
| vb_result | 0.005 | tak | **nie** | **+0.01429** | 4,089 | NOT_SUBMITTED |

S5 (moc) spełniona dla wszystkich trzech sportów (Aneks A). S1 p = 1/201 to minimum przy 200 permutacjach.
**S4 nie przechodzi w żadnej grupie**: poprawka pogarsza wynik poza próbą w każdym sporcie. Werdykt nie zależy więc od
odczytania S2 ani S3.

## Współczynniki z rozwoju (zamrożone = ściągnięte; sha256 `4ad47fcb…93c8`)

Jednostki: hokej i koszykówka w logu środka regulaminowego; siatkówka w d (logit wymiany), identyfikowalne tylko
own - opp, więc opp = -own. Placebo to stan z pierwszego meczu okna przypisany meczom z GP/N w [0.40, 0.60).

| sport | współczynnik | surowy | SE | zamrożony | placebo |
|---|---|---|---|---|---|
| hokej | own_MUST_WIN | +0.0174 | 0.0146 | +0.0160 | -0.0171 |
| hokej | own_SECURED | -0.0461 | 0.0129 | -0.0432 | -0.0582 |
| hokej | own_DEAD | +0.0195 | 0.0239 | +0.0159 | -0.0990 |
| hokej | opp_MUST_WIN | -0.0140 | 0.0146 | -0.0129 | +0.0120 |
| hokej | opp_SECURED | +0.0085 | 0.0141 | +0.0079 | -0.1040 |
| hokej | opp_DEAD | +0.1032 | 0.0189 | +0.0903 | **+0.1812** |
| koszykówka | own_MUST_WIN | +0.0026 | 0.0024 | +0.0025 | -0.0017 |
| koszykówka | own_SECURED | -0.0098 | 0.0021 | -0.0097 | +0.0026 |
| koszykówka | own_DEAD | +0.0195 | 0.0029 | +0.0191 | -0.0061 |
| koszykówka | opp_MUST_WIN | -0.0033 | 0.0024 | -0.0033 | +0.0003 |
| koszykówka | opp_SECURED | -0.0045 | 0.0021 | -0.0045 | -0.0128 |
| koszykówka | opp_DEAD | +0.0087 | 0.0026 | +0.0086 | +0.0252 |
| siatkówka | own_MUST_WIN | +0.0056 | 0.0083 | +0.0048 | +0.0078 |
| siatkówka | own_SECURED | -0.0258 | 0.0066 | -0.0232 | -0.0020 |
| siatkówka | own_DEAD | +0.0095 | 0.0076 | +0.0083 | -0.0278 |

Margines own - opp (zamrożony; S3: MUST_WIN w górę, SECURED i DEAD w dół):

| sport | MUST_WIN | SECURED | DEAD |
|---|---|---|---|
| hokej | +0.0289 | -0.0512 | -0.0745 |
| koszykówka | +0.0058 | -0.0052 | **+0.0105** |
| siatkówka | +0.0096 | -0.0465 | **+0.0166** |

Co pokazują bramki:

- **Hokej S2.** Jedyny materialny współczynnik (|β| >= c_sport 0.05) to opp_DEAD +0.090: przeciwnik "martwy" daje
  więcej goli. Placebo tego stanu, przypisane meczom z połowy sezonu, gdy nic jeszcze nie jest rozstrzygnięte, wynosi
  +0.181, czyli dwa razy więcej. To jakość drużyny (słabe drużyny tracą gole), a nie stawka.
- **Koszykówka i siatkówka S3.** DEAD ma znak przeciwny do zarejestrowanego: strona "martwa" punktuje więcej, nie mniej.
- **Wszędzie S4 > 0.** Bez względu na znaki poprawka pogarsza log score poza próbą.

## Odtworzenie i G1

| sport | migawka bazy (UTC) | wiersze zdarzeń | stany rozwój (MW/AL/SEC/DEAD) | stany egzamin | = Aneks A | mecze rozwoju z centrum | egzaminu | bez centrum modelu |
|---|---|---|---|---|---|---|---|---|
| hokej | 2026-11-18 15:39:20 | 114,093 | 2456/3992/3562/922 | 959/1508/1516/376 | tak | 22,070 | 8,701 | 221 |
| koszykówka | 2026-11-18 15:34:56 | 343,734 | 4565/6738/7882/4767 | 1447/2570/3122/2027 | tak | 45,187 | 17,256 | 7,853 |
| siatkówka | 2026-11-18 15:41:55 | 109,173 | 1118/1798/3307/1848 | 471/654/1199/653 | tak | 17,110 | 6,293 | 494 |

Zamrożenie (`freeze_record.json`): 2026-11-18 15:57:28Z, przed otwarciem czegokolwiek z egzaminu. Zamknięcie
egzaminu (`freeze_record.exam.json`): 15:58:33Z, `exam_outcomes_opened: false`. Skróty zapieczętowanych plików:
`run/sealed_outcomes.sha256`; same pliki zostały w scratchpadzie, nieotwarte.

## Odchylenia (każde wybrane jako opcja zachowawcza, bez patrzenia na wynik egzaminu)

1. Baza czytana na żywo (`?mode=ro`, migawki w tabeli wyżej), a nie z kopii `VACUUM INTO`. Pętle w tym czasie piszą.
2. Zdarzenia: najpierw strony drużyn, potem indeks. Kopia z indeksu wygrywa tylko przy pobraniu ściśle późniejszym;
   to przybliżenie `load_events`.
3. **Remis faz głównych.** W El Salvador LMB 24/25 (ut 17343, sezon 74021) "Apertura" i "Clausura" mają po 110
   meczów. `states.py` bierze wtedy pierwszą nazwę w kolejności wierszy, a ta kolejność różniła się między migawkami
   (pierwszy przebieg koszykówki: G1 = nie, MW 4559 zamiast 4565). Przypięto wybór Aneksu A ("LMB, Clausura",
   `MAIN_PHASE_TIE`). G1 wykrył to przed estymacją, a innych remisów nie ma (`main_phase_ties` w `*_record.json`).
4. Mecze bez centrum modelu są pominięte; liczby w tabeli wyżej. W koszykówce to 7,853 meczów z rozwoju i egzaminu
   razem: ligi, którym model punktów nie daje centrum.
5. Przejście modelu as-of działa na dzisiejszych przełącznikach: restart sezonu i świeżość w koszykówce włączone,
   tempo, rzuty, pusta bramka, dogrywka i późny gol wyłączone. Rozgrzewka 22/23 jest cienka.
6. Koszykówka: Poisson z SE klastrowym (drużyna) zamiast quasi-Poissona. Estymacja punktowa jest ta sama, a
   nadrozproszenie pokrywa SE klastrowe.
7. Siatkówka: model parami w jednostkach d, więc identyfikowalne jest tylko own - opp (β_opp = -β_own).
8. S3 zastosowane do wszystkich grup, także sum. Sekcja 8 mówi "suma: n/d". Nie zmienia to werdyktu, bo S4 nie
   przechodzi nigdzie.
9. S1: statystyka Walda permutacji liczona z macierzą V z rozwoju (200 powtórzeń, ziarno 7).
10. **K = 0, więc egzaminu nie otwarto.** Reguła zaliczenia nie ma żadnej grupy do testowania, a otwarcie 25/26
    tylko opisowo zużyłoby sezon egzaminacyjny dla przyszłego badania. Linia w logu mówi "K=0, egzamin nieotwarty".
11. Nazwy wzięte z polecenia koordynatora: log `stakes_exam_log.md` i skrypt `measure_stakes_exam_sports.py`.
    Specyfikacja (sekcja 8) podaje `stakes_sports_exam_log.md` i `measure_stakes_sports_exam.py`; pliku logu o
    nazwie ze specyfikacji nie ma.
12. Krzywe linii (P3/P4) miały być uproszczone (kubełki 0.05, >= 30 wierszy), ale nie powstały, bo nic nie zostało
    zgłoszone. `curves_dev.json` jest pusty.

## Co oglądano (G5)

- Wyniki **rozwoju** w S1-S4: współczynniki, placebo, Δ "zostaw jeden sezon".
- Liczebności stanów ponownie, w G1.
- Diagnostyka remisu LMB: porównanie stanów migawki Aneksu A z obecnym odczytem, bez wyników.
- Wyników egzaminu 25/26 **nie oglądano**.

## Pliki

- `scripts/sofa/measure_stakes_exam_sports.py`
- `docs/sofa/evidence/stakes_sports_2026-11-18/run/`: `coefficients_frozen.json`, `curves_dev.json`,
  `freeze_record.json`, `freeze_record.exam.json`, `exam_result.json`, `{sport}_record.json`,
  `sealed_outcomes.sha256`, `keep_aneksA.json`
- `docs/sofa/evidence/stakes_exam_log.md`
