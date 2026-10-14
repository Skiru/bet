# Strzały zawodnika według miejsca i części ciała (`/shotmap`), 2026-10-14

Rynki Superbetu „Zawodnik - liczba (celnych) strzałów spoza pola karnego /
głową / lewą nogą / prawą nogą” leżały w `unmapped_markets` jako
NOT_COMPUTABLE („shotmap nie w cache; /lineups podaje tylko sumy”). Brakowało
pobrania, nie źródła: Sofascore `/event/{id}/shotmap` podaje każdy strzał z
zawodnikiem, współrzędnymi, typem (gol / obroniony / niecelny / zablokowany /
słupek) i częścią ciała. Dziś: 21 meczów z tymi rynkami, 3 021 linii (wyłącznie
„powyżej”).

## Dane

- `sofa_event_extra` (kind `shotmap`), `scripts/sofa/backfill_event_extra.py`:
  mecze piłki z ostatnich 365 dni z zapisanymi składami zawodników; 5 187
  meczów piłki ze shotmapą (rozgrywki, które jej nie mają, pomijane po
  `MAX_BARREN_MISSES` pustych odpowiedziach).
- Granica pola karnego `bet.sofa.shot_detail`: x > 17 lub y poza 20,4..79,6
  (współrzędne 0..100 od linii bramkowej). Na 45 meczach odtwarza statystykę
  drużyny Sofascore `totalShotsOutsideBox` na 87 z 90 stron (x > 15,7 - geometryczne
  16,5 m ze 105 m: 69; > 16,5: 84; > 17,5: 82).
- Liczba strzałów zawodnika ze shotmapy = `totalShots` z `/lineups` na 3 013 z
  3 045 występów; celny = `goal` lub `save` (jak „celne” Sofascore).
- Test na prawdziwym meczu: Viking - Bayern 10-13 (strony 2 / 8 jak statystyka
  drużyny; Olise 1 celny strzał spoza pola - Superbet rozliczył „powyżej 0,5”
  jako wygraną na kuponie operatora).
- Błąd znaleziony i naprawiony w trakcie (50ba4e76): uzupełnianie dat z indeksu
  bez sportu wpuściło mecze hokeja (shotmapy bez `playerCoordinates`) -
  pierwsze dopasowanie liczyło hokeistów jako piłkarzy z zerem strzałów.
  Wyniki niżej są po naprawie.

## Model i pomiar (walk-forward, tylko dane sprzed meczu)

Tylko mecze, w których zawodnik **wyszedł w pierwszym składzie** (Superbet
zwraca stawkę, gdy nie wyszedł). Prognoza: średnia z ostatnich 10 meczów
zawodnika w podstawie, ściągnięta do średniej jego pozycji (G / D / M / F)
liczonej tylko z wcześniejszych dni, K pseudo-meczów; ogon Poissona.
`scripts/sofa/measure_shot_detail.py`, `scripts/sofa/fit_shot_detail.py`
(dopasowanie na kopii tabel w `data/refit_shot_detail_2026-10-14/`).

Log-loss (średnio na linię 0,5 / 1,5 / 2,5; K=0 to sama średnia zawodnika):

| wielkość | K=0 | najlepsze K | log-loss |
|---|---|---|---|
| strzały spoza pola | 0,3437 | 5 | 0,2694 |
| strzały prawą nogą | 0,3635 | 5 | 0,2921 |
| strzały lewą nogą | 0,2997 | 2 | 0,2234 |
| strzały głową | 0,2546 | 5 | 0,1696 |
| celne spoza pola | 0,2048 | 10 | 0,1105 |

Sama średnia zawodnika (to, co liczy „k/n z próbki”) jest wyraźnie gorsza od
ściągniętej do pozycji - próbka 10 meczów jednego zawodnika jest za głośna.

## Krzywa z historii (to, co wydrukowałby pipeline)

Przedziały jak w `fit_confidence` (min. 400 prognoz), wszystkie linie razem:

| wielkość | prognoza | n | zrealizowane | dolna granica 95% |
|---|---|---|---|---|
| spoza pola | 0,70-0,75 | 585 | 0,754 | 0,717 |
| spoza pola | 0,75-0,80 | 441 | 0,796 | 0,756 |
| prawa noga | 0,70-0,75 | 1 917 | 0,724 | 0,704 |
| prawa noga | 0,75-0,80 | 1 385 | 0,796 | 0,774 |
| prawa noga | 0,80-0,825 | 558 | 0,823 | 0,789 |
| prawa noga | 0,825-0,85 | 410 | 0,829 | 0,790 |
| lewa noga | 0,70-0,75 | 916 | 0,723 | 0,693 |
| lewa noga | 0,75-0,80 | 960 | 0,751 | 0,723 |

Model jest skalibrowany tam, gdzie drukowałby (zrealizowane ≈ prognoza).
Rynki **celne** (spoza pola, głową, lewą, prawą) i strzały głową nie osiągają
0,60 w ani jednym przedziale z 400 prognozami - nie drukowałyby się.

## Czego ten pomiar nie mówi

- **Nic o cenie.** Superbet wystawia te rynki tylko „powyżej”, bez marży do
  odczytania; historii cen nie ma. Od 2026-10-14 OFFER zapisuje kursy
  nieczytanych rynków (`runs/sofa/<d>/unmapped_prices/`); dopiero rozliczone
  linie powiedzą, czy pewność 0,72-0,80 bije kurs. Strzały zawodnika „zwykłe”
  (już czytane) były po cenie Superbetu na minusie (-14,3% [-18,8; -9,6],
  10-09..10-13) - to ostrzeżenie, nie wynik dla tych rynków.
- Jedna kropka w czasie (365 dni, bez podziału na sezony); pozycja z
  `/lineups` meczu, nie z kadry.

## Stan

Kod: cache i pobieranie (`2b8cbc48`), estymator i dopasowanie (`6b19cca1`),
naprawa sportu (`50ba4e76`). Plik estymatora i krzywe są **przygotowane, nie
zainstalowane** (`data/refit_shot_detail_2026-10-14/{sofa_shot_detail.json,
curves.json}`); włączenie wymaga przełącznika w `bet.sofa.epochs` i zgody
operatora na instalację krzywych.
