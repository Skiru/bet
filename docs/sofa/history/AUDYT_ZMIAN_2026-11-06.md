# Audyt zmian i poprawek modeli z 2026-11-06 (wykonany 2026-11-07)

Zakres: 7 commitów z 11-06 (d16ca339, 5369a050, b2fe015b, 6c1b6407, 13297bc1,
2b6a358a, 8c771a47) i dwa przełączniki z wieczora 11-05, które pierwszy raz
działały 11-06 (`TENNIS_POINT_MODEL`, `BB_PERIOD_MARKET_LINES`). Pięć
niezależnych przeglądów (symulator piłkarski, model rally siatkówki, model
punktowy i handicap setowy tenisa, refit replay-rules + tabela sezonowa,
przełączniki / dzień mieszany / stan na żywo), druga runda na zduplikowane
zdarzenia, kluczowe liczby sprawdzone lokalnie. Bramki przed zmianami:
pytest 6636 passed, ruff, mypy --strict, rejestr testów — czyste.

## Wynik w jednym zdaniu

Żaden nowy model nie drukował ani nie rozliczał źle; znaleziony błąd jest
starszy niż 11-06 i 11-06 go tylko ujawnił: **to samo zdarzenie drukowało się
dwa razy pod dwiema nazwami rynku** (od 10-15, 667 nóg do 11-06).

## Sprawdzone na danych i czyste

- **Symulator piłkarski**: zgodny z analitycznym Poissonem połów (200 tys.
  ścieżek); mapowanie OFFER poprawne na 4 800 szczeblach (strona, kolejność
  kombinacji, słowa Superbetu 95/95); niezależne przeliczenie 4 386
  rozliczonych wierszy 11-06 — 0 rozbieżności; bramki druku, `floor_rule`,
  zero nóg w builderach, pierwszy druk 17:54Z; okna parametrów / krzywych /
  hold-outu rozłączne.
- **Tenis**: 4 260 wierszy SHEET odtworzonych co do zaokrąglenia na obecnej
  bazie (bez podglądania przyszłości); symulator zgodny z dokładnym
  rachunkiem seta; 3 932 rozliczone wiersze — 0 rozbieżności; nogi w zakresie
  czytały krzywe modelu punktowego; handicap setowy 11-06 nie wydrukował się.
- **Siatkówka**: set i mecz zgodne z rozwiązaniem łańcucha Markowa; 35 nóg z
  właściwymi etykietami modelu; nakładka krzywych włącza się o 17:30Z, 11-07
  bez zmian; poprawka U3 (8c771a47) poprawna, niczego nie ukrywa.
- **Refit i tabela sezonowa**: różnią się tylko deklarowane klucze (25 + 13
  wycinków; 11-07 dodatkowo 4 krzywe tabeli), 29 zmienionych krzywych
  monotonicznych; `calibration_path_for` poprawny dla każdej chwili
  11-05..11-08; 35 rodzin zapisanych jak w wierszach; odtworzenie = żywy kod.
- **Dzień mieszany 11-06**: 3 881 zablokowanych nóg z pewnością i kursem
  równymi pierwszemu drukowi, żadna po starcie, 259 zdjętych zostało
  zdjętych; każdy przełącznik czytany „dzień i zegar” w każdym czytelniku;
  rebuild dnia wcześniejszego nie łapie nowych reguł.

## Naprawione (2026-11-07)

1. **Jedno zdarzenie — jedna noga** (`SAME_EVENT_DEDUP`, od 2026-11-08 00:00Z,
   operator „TAK!”). `bet.sofa.leg_identity` nazywa zdarzenie nogi logicznie
   (piłka: ocena na każdej ścieżce wyniku graderami SETTLE; hokej / koszykówka:
   zbiór marginesów; siatkówka / CS2 bo3: zbiór wyników setów / map);
   `build_coupon` zostawia jedną nogę na (mecz, zdarzenie). Znalezione na
   kuponach 10-13..11-06: `goals_for` strony > 0,5 = `result_or_btts` tej
   strony (360 grup), „nie 0-0” pod czterema nazwami (119), hokej handicap
   ±0,5 = podwójna szansa (74), siatkówka handicap ±2,5 = „wygra seta” (41),
   `btts_any_half` UNDER = `btts_halves` Nie/Nie (2). Grupowanie identyczne
   przy ścieżkach 0..6 i 0..9 goli na połowę. ROI bez zmian (−5,27% w obu
   wariantach), ale ledger liczył te wyniki podwójnie i ekspozycja była
   podwójna. Widok historyczny: `measure_same_event.py`. Grupa „od 11-08”.
   Nogi CS2 niosą teraz `best_of` (bez niego brak dopasowania).
2. **Tenis bez pola formatu** nie jest już wyceniany jak do dwóch wygranych
   setów (`tennis_point_sheet.fixture_match`); poprawka poprawności, na żywo
   od razu — 12 689 z 12 689 meczów z 60 dni ma format 3, więc niczego nie
   zmienia w historii.
3. **`day_status.py` `line_evidence`**: WARN, gdy dowód linii jest
   dopasowany na wcześniejszy dzień (wcześniej nic tego nie mówiło).
4. **`run_coupon.py`** (06_coupon, selektor VALUE) czyta kalibrację dnia
   (`calibration_path_for`), a nie zainstalowany plik.
5. **Pula tenisa w `fit_line_evidence`** bez wierszy modelu punktowego (od
   dopasowania na 11-08; wchodzą tylko własną ścieżką), **gubione powody
   pominięć tabeli sezonowej** w `run_sheet`, **COUPON przed ponownym SHEET**
   w rebuildzie — szczegóły w commicie.
6. **Dokumentacja**: kartki a tabela (`handicap_cards_points` OVER jest w 35),
   grupa „od 11-06” nie zawiera żadnego dnia, start krzywych symulatora
   11-06 17:30Z, przeliczenie dowodu linii 11-06 17:34:29Z (nogi symulatora
   czytały własne przesunięcia, nie zbiorcze), floor symulatora = 3 różne
   zdarzenia, „Brier lepszy w każdej rodzinie” siatkówki tylko punktowo,
   połowa potwierdzająca tabeli nie była ślepa, pochodzenie plików staged.
7. Pliki `config/sofa_settleability.2026-11-0{3..6}.json` (czytane przez
   build) dodane do repozytorium.

## Otwarte — do pomiaru albo decyzji operatora

- Rynki wielowynikowe symulatora omijają regułę marży 15% (39 z 52 nóg
  `half_goals_combo` 11-06 przy 15,2–16,9%).
- Reguła floora symulatora łagodna (górna granica ≥ 0 bez marginesu) i
  mierzona na ostatnim snapshocie przed startem, nie na cenach druku.
- Siatkówka: płeć tylko z historii, brak minimum historii, przewaga
  gospodarza na neutralnym terenie, bo3 jak bo5, dwa klucze z za małą liczbą
  linii na własne przesunięcie.
- Dowód linii dla 35 rodzin tabeli z p bez tabeli (tylko obniża).
- U3 / verify_legs czytają obecny dowód linii, nie ten z buildu (starsze).
- Noga setowa tenisa przy kreczu zwracana w całości — Superbet może rozliczać
  zakończony set (nie sprawdzone offline).
- `slip_builder.is_stat_market` (niezacommitowana praca w drzewie, nie z
  11-06) przepuszcza rynki wyniku i goli jako „statystyczne” — dotyczy tylko
  `/kupon --stat-markets`.

## Fakty o dniu 11-06 (małe n, nie dowód decyzji)

| rodzina | n | wygrane | Σpewność | Σ1/kurs | jednostki |
|---|---|---|---|---|---|
| sym. team_scores_both_halves UNDER (≥ 0,70) | 49 | 37 | 38,13 | 40,74 | −4,26 |
| sym. team_scores_both_halves UNDER (floor) | 18 | 13 | 11,99 | 12,78 | +0,25 |
| sym. half_goals_combo OVER (≥ 0,70) | 6 | 6 | 4,48 | 4,81 | +1,50 |
| sym. half_goals_combo OVER (floor) | 46 | 30 | 29,86 | 31,81 | −2,56 |
| sym. btts_any_half / btts_halves (floor, te same 2 zdarzenia) | 2+2 | 1+1 | 2,48 | 2,66 | −1,00 |
| siatkówka rally (winner / set_winner / set_handicap) | 34 rozl. | 28 | — | — | +2,14 |
| tenis model punktowy, gemy w secie | 145 rozl. | 122 | 116,97 | 123,93 | −2,42 |
| tenis model punktowy, serwis | 37 rozl. | 34 | 29,06 | 31,08 | +3,58 |
