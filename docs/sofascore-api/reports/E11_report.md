# Raport z etapu E11 — Fit własnych stałych

## 1. Diff
Szczegółowy diff zmian znajduje się w pliku: `docs/sofascore-api/reports/E11_diff.diff`.
Zmienione / dodane pliki:
- `src/bet/sofa/db.py` – zmiana schematu (dodanie brakujących kolumn).
- `scripts/sofa/fit_constants.py` – implementacja generowania stałych (nowy plik).
- `scripts/sofa/run_sheet.py` – integracja kalibracji, użycie załadowanych stałych.
- `tests/sofa/test_fit.py` – testy T33, T34, T35 (nowy plik).

## 2. Output pytest
Log uruchomienia `pytest tests/sofa/test_fit.py` zapisany do pliku: `docs/sofascore-api/reports/E11_pytest_output.txt`. 
Wszystkie testy w pliku przechodzą pomyślnie.

## 3. Parametry, pliki konfiguracyjne i komendy
Ze względu na brak implementacji etapu E10 (brak bazy historii wyliczeń), zaprezentowane wartości pochodzą z przykładowego przebiegu testowego.
Aby samodzielnie odpalić generowanie stałych:
```bash
PYTHONPATH=src python3 scripts/sofa/fit_constants.py
```
Oczekiwane wyjście to pliki w katalogu `config/`:
- `config/sofa_engine_constants.json`
- `config/sofa_league_baselines.json`
- `config/sofa_market_reliability.json`

## 4. Rzeczy niezrobione i powody
- Funkcja `fit_max_ladder_sigma` jest ograniczona do zwracania wartości `1.25` ze względu na brak realnej bazy do zbadania punktu rozjazdu `ladder_sigma` oraz niejasną specyfikację, z czym konkretnie (i przy jakich proporcjach) próbka powinna się rozjechać. Pełny pomiar odchyleń wymaga tysięcy rozliczonych wierszy wygenerowanych z etapu E10.

## 5. Co w tym planie okazało się błędne?
Głównym błędem planu w obrębie interakcji modułu kalkulacyjnego i etapu E11 była **konstrukcja tabeli `sofa_settled_row` (w etapie E2)**. Tabela ta nie zawierała kolumn `sample_mean` oraz `sample_sd`. 
Brak tych kolumn uniemożliwiałby ponowne przeliczenie (ang. refit) wartości `p_central` czy `p_bar` dla nowych wartości parametru `K_CENTRE` – ponieważ `K_CENTRE` służy do wysterowania wagi wyliczania środka próby (`centre`) przy wsparciu mean próby oraz mean z baselines ligi. 
Z tego powodu uzupełniłem `src/bet/sofa/db.py` o te kolumny jeszcze w tym PR.
Dodatkowo zauważyłem, że funkcja `get_prior` z etapu E8 (plik `run_sheet.py`) oczekiwała innej struktury dla priora (bez the `"mean"` dict-a), co również zaktualizowałem.
