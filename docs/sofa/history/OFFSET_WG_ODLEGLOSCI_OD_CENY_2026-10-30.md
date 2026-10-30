# Offset line evidence według odległości od ceny — 2026-10-30

Przełącznik `epochs.PRICE_GAP_OFFSET_FROM_UTC` = **2026-10-30 08:45Z**
(piłka, tenis, hokej; `PRICE_GAP_OFFSET_SPORTS`). Decyzja operatora 2026-10-30:
„Robić C! I wprowadzić już od dzisiaj". Dzień 10-30 jest **mieszany**: nogi
wydrukowane przed 08:45Z zostają zablokowane na starym offsecie. Grupa ledgera
to „10-30 mieszany”, a od 10-31 zaczyna się grupa „od 10-31”. Commity:
`9911603a` (kod, testy, plik dowodów) i `3afa261a` (dokumentacja).

## Skąd się wzięło

Operator: „słabo działają rynki goli”. Pomiar na wydrukowanych nogach
piłkarskich z `13_results.json`, 10-13..10-29, z bootstrapem po meczu:

| | n | trafione − pewność | trafione − 1/kurs | ROI |
|---|---|---|---|---|
| rynki goli | 15 204 | −1,4 pp [−2,3; −0,6] | −4,5 pp | −5,5% |
| pozostałe rynki | 47 943 | −1,6 pp [−2,1; −1,2] | −4,6 pp | −5,5% |

Gole w meczu i w połowach mieszczą się w ±2 pp. Odstają **gole drużyny
(`goals_for`)**: OVER −5,3 pp [−7,8; −2,5] (n=1 002, prawie cała linia 0,5),
UNDER −3,1 pp [−5,4; −1,0] (n=1 413).

## Diagnoza

- Krzywa `goals_for` na replayu historii (`data/refit_2026-10-17/sofa_replay.db`,
  test 07-01..10-17) zgadza się z wynikami: OVER 0,5 +0,2 pp przy n=106 tys.,
  UNDER od −0,7 do −1,0 pp. Refit nie jest potrzebny.
- Na wszystkich drukowalnych liniach Superbetu (krzywa ≥ 0,70) offset wynosi
  tylko −0,7 pp. Wydrukowane z nich: −6,2 pp [−8,9; −3,5]. Niewydrukowane: +0,4.
- Mechanizm: linie realizują względem krzywej zależnie od d = krzywa − 1/kurs.
  Dla piłki, wszystkie drukowalne linie 10-05..10-29, wychodzi kolejno
  +3,0 / −1,4 / −4,9 / −8,2 / −15,3 pp dla d < −0,05 / −0,05..0 / 0..0,03 /
  0,03..0,06 / ≥ 0,06. Bramka x ≥ 0,90 wycina większość linii z d < −0,05,
  a to one równoważyły jedną liczbę offsetu. Ten sam kształt mają wszystkie
  rynki; gole drużyny mają po prostu najwięcej takich linii (46% wobec 18%
  w rożnych).

## Pomiar poza próbą (2026-10-30)

Wiersze zbudowano kodem `fit_line_evidence`; odtwarzają plik z 10-30 co do
liczby. Metody dopasowano na danych uczących, druk symulowano bramkami
pewność ≥ 0,70, x ≥ 0,90 i marża ≤ 15% tam, gdzie są obie strony. Różnice
liczono parami względem obecnej reguły, z bootstrapem po meczu.

- **A** — obecna reguła: jeden offset klucza.
- **B** — offset liczony na populacji bramki.
- **C** — offset według przedziału d, ściągany do puli sportu.
- **D** — limit pewność ≤ 1/kurs + k.

Wyniki C, podział: uczenie < 10-22, test 10-22..10-29:

| sport | kalibracja wydrukowanych | Brier (wszystkie drukowalne) | ROI |
|---|---|---|---|
| piłka | +1,31 pp [+1,19; +1,45] | −1,01e-3 [−1,30; −0,80] | −0,04 pp [−0,22; +0,13] |
| tenis | +0,97 pp [+0,43; +1,51] | −1,37e-3 [−2,3; −0,4] | −0,11 pp (ns) |
| hokej | +1,99 pp [+1,24; +2,75] | −1,69e-3 [−2,8; −0,5] | +0,86 pp (ns) |

Podział < 10-18 daje to samo. Pozostałe warianty i sporty:

- **B** praktycznie nic nie zmienia.
- **D** daje około 85% zysku C.
- **Koszykówka**: za mało nóg (68–259 wydrukowanych).
- **Siatkówka**: w jednym podziale ROI spada o −2,95 pp [−5,86; −0,12].
- **CS2**: nie da się zmierzyć.

Te trzy sporty zostają przy starej regule.

**To poprawka kalibracji, nie przewaga.** Trafione − 1/kurs pozostaje bez
zmian (piłka około −4,7 pp przy każdej metodzie). Statystyki nie biją ceny;
C sprawia tylko, że wydrukowana liczba mówi prawdę.

## Co wdrożono

- `line_evidence.fit` zapisuje dwie nowe sekcje:
  - `keys.<sport>.<klucz>.printable_by_gap`: n, mecze i suma (y − krzywa)
    w każdym przedziale d;
  - `sport_printable_by_gap`: średnia luka sportu w przedziale.

  `fit_line_evidence.py` zapisuje też `price_gap_edges` i `price_gap_shrink_k`.
  Stare sekcje pliku pozostają bajt w bajt takie same.
- `LineEvidence.gap_offset` liczy offset jako
  (suma luk klucza + 200 × luka puli) / (n + 200), nigdy powyżej 0.
  Limit pasma kursu jest bez zmian. Źródło nogi dostaje znacznik
  `...−0,0xxxsbd<przedział>`. Starego offsetu używa noga bez ceny, sport spoza
  listy oraz plik bez nowych sekcji.
- Stałe `PRICE_GAP_EDGES` i `PRICE_GAP_SHRINK_K` są w `UNFITTED_CONSTANTS`.
  K wybrano z siatki 0..2000 według Briera na ostatnich 5 dniach danych
  uczących; wynik był płaski od 100 do samej puli.
- Plik `config/sofa_superbet_line_evidence.json` dopasowano ponownie przed
  przełącznikiem (`--before 2026-10-30`). Krzywe nie zostały ruszone.
- Odczyt: CONFIDENCE, SPORT_CONFIDENCE, `verify_legs.py` i `audit_variants.py`
  biorą przełącznik według dnia i zegara budowy.
- Testy: `tests/sofa/test_line_evidence_price_gap.py`; grupy ledgera
  w `test_audit_2026_10_13.py`. Bramki: 6243 testy, ruff, mypy, rejestr — wszystko
  przeszło.

## Przebudowa 10-30

`rebuild_day.py --date 2026-10-30` ruszył o 08:46:17Z, CONFIDENCE zakończył
się o 08:50Z. Etapy: świeże ceny (OFFER), SHADOW, FIXTURE_CHECK (766 meczów,
0 UNVERIFIED), CONFIDENCE..PDF. AUDIT_VARIANTS zwrócił PARTIAL z 66
ustaleniami — wszystkie to C3, czyli nogi czytanej dwudziestki bez odczytu
po przebudowie. `day_status` OK, kopia w iCloud równa lokalnemu renderowi.

Kupon miał 4 245 nóg przed przebudową i 4 282 po niej. Nogi wydrukowane
przed 08:45Z są zablokowane: piłka 63, tenis 55, siatkówka 1. Zmiany
na nogach otwartych, obecnych w obu wersjach:

| sport | wspólne | średnia zmiana pewności | obniżone / podniesione | wypadły / weszły |
|---|---|---|---|---|
| piłka | 2 826 | −1,15 pp | 1 452 / 870 | 288 / 338 |
| tenis | 304 | −0,45 pp | 150 / 105 | 56 / 61 |
| hokej | 499 | −0,58 pp | 148 / 130 | 71 / 52 |

`goals_for` (nogi otwarte):
- OVER (53 nogi): średnia pewność spadła z 0,812 do 0,791; 1/kurs to 0,841.
- UNDER (73 nogi): średnia pewność spadła z 0,813 do 0,798.

Część nóg ma pewność wyższą niż przed przebudową. Te nogi mają d < −0,05:
offset ich przedziału przycina się do 0 i jest łagodniejszy niż jeden offset
klucza. Pewność nigdy nie przekracza krzywej. Zmiany obejmują też odświeżone
ceny (OFFER), więc nie wszystko wynika z przełącznika.

Otwarte: odczyt analityków dla 66 nóg C3 (`/sofa-analyze`).
