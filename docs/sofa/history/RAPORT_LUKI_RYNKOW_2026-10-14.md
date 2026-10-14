# Luki w rynkach - przegląd i wdrożenie, 2026-10-14

Prośba operatora: znaleźć, co Sofascore ma dla rynków, których nie czytamy,
zbudować model i krzywe na historii, „wszystkie po kolei”. Wszystko, co
zmienia druk, jest za przełącznikiem `None`; włączenie i instalacja krzywych
czekają na decyzję operatora.

## Co zrobiono

| krok | stan | commit |
|---|---|---|
| 1. Zapis kursów nieczytanych rynków (każdy przebieg OFFER -> `runs/sofa/<d>/unmapped_prices/`) | **działa od dziś** (10-14: 125 850 kursów z 242 meczów) | 6864cc3e |
| 2a. Cache `sofa_event_extra` (shotmap / point-by-point / incidents) + `backfill_event_extra.py` | działa; 5 756 meczów piłki ze shotmapą, tenis point-by-point 60 dni (reszta roku w toku) | 2b8cbc48, 833f77ff, 50ba4e76 |
| 2b. Strzały zawodnika spoza pola / głową / lewą / prawą (`bet.sofa.shot_detail`) - pomiar, dopasowanie, podpięcie OFFER -> SAMPLES -> SHEET -> SETTLE | gotowe, przełącznik `SHOT_DETAIL_MARKETS_FROM_UTC = None`, plik estymatora i krzywe przygotowane w `data/refit_shot_detail_2026-10-14/` | 6b19cca1, 2de6b62e, 7276613b |
| 3. Podwójna szansa w piłce (plan audytu D1) | gotowe, `FOOTBALL_RESULT_MARKETS_FROM_UTC = None` | 4f8da016 |
| 4. Tenis „po N gemach / punktach” | zmierzone - **nie drukowałoby się** | 77d76531 |
| Raport pokrycia: etykiety „brak źródła” dla shotmap / point-by-point poprawione | gotowe | 77d76531 |

Dowody: `docs/sofa/evidence/shot_detail_2026-10-14.md`,
`docs/sofa/evidence/tennis_game_order_2026-10-14.md`,
`docs/sofa/evidence/football_result_phase_2026-10-13.md` (DC).

## Najważniejsze liczby

- Shotmap: granica pola karnego x > 17 odtwarza statystykę drużyny Sofascore
  na 87/90 stron; liczba strzałów = `totalShots` na 3 013/3 045 występów.
  Model (średnia 10 meczów w podstawie ściągnięta do pozycji, Poisson)
  skalibrowany walk-forward: spoza pola 0,70-0,75 -> 0,754 (n 585), 0,75-0,80
  -> 0,796 (n 441); prawa noga do 0,825-0,85 -> 0,829 (n 410). Rynki „celne”
  nie dochodzą do 0,60.
- Tenis: remis po 2 gemach -0,033 log-loss, ale na górze przeszacowanie 3-9 pp;
  nic >= 0,70.
- DC: zarejestrowany próg spełniony 10-13 (-0,0394 log-loss, -0,91 pp po
  krzywej przy p >= 0,70).

## Błędy znalezione i naprawione w trakcie

- Pobieranie shotmap wpuściło mecze hokeja (uzupełnianie dat z indeksu bez
  sportu); pierwsze dopasowanie liczyło hokeistów jako piłkarzy. Naprawione,
  dopasowanie powtórzone (50ba4e76).
- Indeks list trzyma czasem kopię meczu sprzed startu (`notstarted`) - filtr
  statusu wyrzucałby rozegrane mecze; usunięty (833f77ff).
- Wybór celów pobierania trzymał całą historię list w pamięci (15 GB) -
  przeniesiony do SQL.

## Weryfikacja

- Bramki na `main` po każdym kroku: 4 549 testów, ruff, mypy strict, rejestr.
- E2E: SHEET nowym kodem na kopii 10-14 (przełączniki wyłączone) =
  produkcyjny `05_sheet.json` (27 788 wierszy, 0 różnic `p_central`; różni się
  tylko `sample_newest_days`, wiek względem zegara). Prawdziwe pliki dnia -
  md5 bez zmian.
- **Nie przetestowane**: żaden przełącznik nie był włączony na żywo; SETTLE
  nowych rynków tylko offline; CONFIDENCE nie porównany E2E (zegar i kursy
  się zestarzały).

## Decyzje dla operatora

1. **`SHOT_DETAIL_MARKETS_FROM_UTC`** - rekomendacja: włączyć od następnego
   dnia **bez instalowania krzywej**: OFFER czyta, SHEET wycenia, SETTLE
   rozlicza; CONFIDENCE odmawia `NO_LINE_EVIDENCE`, więc nic się nie drukuje,
   a linie się rozliczają. Wymaga skopiowania
   `data/refit_shot_detail_2026-10-14/sofa_shot_detail.json` do `config/`
   (plik estymatora, nie krzywa). Krzywą (`curves.json`) instalować dopiero,
   gdy rozliczone linie Superbetu pokażą, że pewność 0,72-0,80 nie przegrywa
   z kursem - zwykłe strzały zawodnika były po cenie -14,3% [-18,8; -9,6].
2. **`FOOTBALL_RESULT_MARKETS_FROM_UTC`** (DC) - tak samo: włączenie = zbieranie
   linii, druk dopiero po 50 rozliczonych liniach w kubełku.
3. **Tenis point-by-point**: nic do włączenia; ponowny pomiar po pobraniu roku.
4. DNB: nadal czeka na nowy zarejestrowany test (plan D1).
