# Weryfikacja rozliczenia 2026-10-16 wiersz po wierszu (2026-10-17)

Zlecenie operatora: każde wydarzenie i każdy rynek 10-16 zweryfikować przez
SETTLE, znaleźć błędy, które dały złe wyniki, iteracyjnie do czysta.

Kontekst: restart Maca 2026-10-16 18:58Z zabił pętle shadow / cs2 10-16,
mostek i `capture_closing` - poranne kroki pętli (SHADOW_SETTLE 10-16 / 10-15
/ 10-14, CS2_SETTLE 10-16 / 10-15, sweepy) wykonane ręcznie; pętle 10-17
uruchomione 05:03Z. Dziura CLV: 618 drukowanych nóg po 18:45Z bez kursu
zamknięcia.

## Metoda

Cztery niezależne sprawdzenia, każde własnym kodem z surowych danych w
`data/sofa.db` (bez `settle.py` / `metrics.extract_metric` / grading
`shadow` / `cs2` - te tylko czytane jako definicje rynków):

1. piłka + tenis: każdy wiersz `sofa_settled_row` run_date 2026-10-16;
2. hokej / kosz / siatka / CS2: każda linia `settled.json` 10-14..10-16 +
   tożsamość każdego meczu (700); grader sprawdzony testem negatywnym
   (odwrócona orientacja -> 6 052 rozbieżności);
3. każdy wiersz / linia nierozliczona lub zwrot: czy powód jest prawdziwy
   (składy, statusy na żywo, ~80 zapytań do Sofascore);
4. kompletność kuponu i arytmetyka ledgera (zapisy wydruku, ceny, duplikaty,
   każdy dzień 09-19..10-16).

## Iteracja A - znalezione defekty

| # | defekt | kod | skutek 10-16 |
|---|---|---|---|
| 1 | kartka zawodnika z ławki liczona do punktów kartek (komunikat 06/2022: nie liczy się) | `metrics.calculate_cards_points` | Leganés - Córdoba (Á. Millán), Rapid - Hartberg (L. Marić): 6 wyników odwróconych, 16 wartości; poza kuponem |
| 2 | wynik połowy przepisany przez Sofascore po meczu (Stocksund: period1 0-0 wobec HT 0-2 w zdarzeniach) - regrade odwróciłby 10 poprawnych wierszy | `extract_metric` połowy | 0 dziś, ryzyko |
| 3 | koszykówka: nazwiska zawodników tylko `match_player` | `shadow.player_value` | 32 linie nierozliczone (Montero, Diouf, Alston Jr.; Balcerowski / Stewart to pseudonimy) |
| 4 | koszykówka: pełny wynik bez `winnerCode` odrzucony | `shadow.build_result` | Shumen - Botev, 16 linii |
| 5 | CS2: pseudonim wydłużony przez Superbet (MartinezSa / martinez) | `cs2.MapResult.player` | fnatic - Heroic, 16 linii |

Poza tym zgodne: piłka + tenis 38 369 / 38 398 (reszta = Stocksund po stronie
skryptu i #1), sporty 50 706 / 50 706, każdy powód nierozliczenia
uzasadniony poza #3-#5, ledger bez MISMATCH.

## Poprawki (commit d5210b89, testy `tests/sofa/test_settle_verification_2026_10_17.py`)

1. `metrics.drop_bench_cards`: przy rozliczaniu (SETTLE i regrade) kartka
   zawodnika, który według składów był na ławce (rezerwowy, który nie wszedł
   - tylko gdy zapis ma zmiany i zawodnik nie ma minut; wszedł po kartce;
   zszedł przed kartką), jest pomijana. Próbki bez zmian. Bez składów -
   jak dotąd. `regrade_settled.py --cards-bench --apply`: 28 wyników
   odwróconych 09-19..10-16 (6 na 10-16), 121 wartości; żaden nie był
   drukowaną nogą (dwie drukowane zmieniły tylko wartość). Log
   `runs/sofa/regrade_20261017T094146Z.json`.
2. `metrics.half_time_disagrees`: przy rozliczaniu połowy odrzucone
   (`INTERNAL_INCONSISTENT`), gdy znacznik HT w zdarzeniach przeczy
   `period1`; rozliczony wiersz zostaje. Odpala na 32 z 7 678 meczów w cache.
3. `shadow.player_value`: reguła tokenów i nazwiska z piłki + tokeny bez
   przyrostków Jr/Sr/II (tylko rozliczenie sportów).
4. `shadow.build_result(allow_final_only=True)`: brak `winnerCode` przy
   rozstrzygniętym wyniku - zwycięzca z wyniku; historia bez zmian.
5. `cs2.MapResult.player`: jeden pseudonim >= 5 liter będący prefiksem.

Dane: 10-16 rozliczone ponownie (`resettle_sweep`; SHADOW_SETTLE / CS2_SETTLE
po usunięciu rekordów 5 meczów z kopią w
`data/backup_settled_20261017T0945Z/`): +70 linii sportów (0 zmienionych),
+58 wierszy piłki (Ahrobiznes - Metalist rozegrany 10-17 1-0, 14 rożnych
opublikowanych później). Ledger przeliczony 09-19..10-16.

## Iteracja B - czysto

Piłka + tenis 38 438 / 38 456 (18 = Stocksund, poprawne w bazie); sporty
20 407 / 20 407, nowe linie sprawdzone w surowym boksie; żadnego złego
zwrotu; ledger 28 dni zgodny co do grosza, 0 MISMATCH. Maccabi Haifa (K) =
Neve Shanan Haifa (Sofascore 52458, dawniej „Maccabi Haifa/Neve Sheanan”).

## Wynik 10-16 (official, 10-16 mieszany)

-109,66 j. (pojedyncze -109,04, buildery -0,62 szac.), 3 052 rozliczonych z
3 142; ROI -3,6% [-5,8, -1,3]. removed:reads +1,22 j.

## Otwarte (decyzja operatora / czas)

- **Krecz w tenisie** zwraca wszystkie nogi; jeśli Superbet zostawia rynki
  rozstrzygnięte przed kreczem: 8 z 23 zwrotów 10-16 byłoby 5 WIN / 3 LOSS.
- **Mecz przerwany** (`interrupted`) nigdy nie staje się zwrotem (5.D.5
  otwarte): 4 mecze ITF (16 nóg) i Næstved - B93 (12 nóg) po terminach
  (20:59Z / 21:59Z 10-17) zostaną nierozliczone na zawsze.
- Termin zwrotu ITF bez kraju w danych liczony w UTC (opisane zachowanie).
- Plik skipów liczy 26 wierszy Stocksund jako nierozliczone, choć 22 są
  rozliczone w bazie (księgowość, nie wynik).
- 30 nóg rożnych (14 meczów) czeka na dostawcę; poranny sweep.
- 6 linii pomiaru koszykówki z pseudonimami (Balcerowski, Stewart).
- ZED - Azam: zapis goli niespójny z wynikiem połowy; dwa źródła Sofascore
  (period1, HT) mówią 1-1 - LOSS zostaje.
