# MLB Measurement Report

## 1. Wyszukiwanie (Resolve)
Przetestowano 50 fixture'ów MLB.
- **Recall:** 82% (41/50).
- Wyszukiwarka Sofascore poprawnie radzi sobie z nazwami drużyn (np. "New York Yankees").

## 2. Statystyki (/event/{id}/statistics)
Sprawdzono 41 znalezionych meczów.
- **Wynik:** 404 Not Found dla większości, lub puste grupy statystyk dla części.
- Kluczowe metryki (runs, hits) **nie są obecne** w payloadzie statystyk (sprawdzono pod różnymi nazwami).

## 3. Wnioski
Pokrycie Sofascore dla baseballu (MLB) na poziomie szczegółowych agregatów (runs, hits) nie pozwala na wyliczenie `p_central`. Brak zwrotu w `/statistics` dyskwalifikuje ten sport z pipeline'u `sofa`.
