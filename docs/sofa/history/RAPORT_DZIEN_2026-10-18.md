# Dzień 2026-10-18 (niedziela)

Kupon: `runs/sofa/2026-10-18/KUPON_2026-10-18.pdf`. Ostatnia przebudowa o 07:08Z (`rebuild_day.py`). Sprawdzenie `audit_variants` dało 0 znalezisk, `audit_coupon` jest OK.

## Kupon

- **Pozycje:** 9 028 numerowanych singli oraz 76 zablokowanych z druku z 06:45Z. Zablokowane to piłka 35 i tenis 41, ich mecze już się zaczęły.
- **Bet Buildery:** 12 (B1..B12). sofa nie podaje ich kursu.
- **Single według sportu (bez zablokowanych):**

  | sport | single |
  |---|---|
  | piłka | 8 523 |
  | hokej | 269 |
  | tenis | 159 |
  | siatkówka | 53 |
  | CS2 | 17 |
  | koszykówka | 7 |

- **Status sportów:** hokej, koszykówka, siatkówka i CS2 mają status OK.
- **Odczyty i weta:** zastosowano 523 odczyty (w tym 71 sportowych), 0 nie znalazło dopasowania. Weto 1 (CONTEXT), też bez niedopasowań.
- **`removed_by_reads` (129 nóg):**
  - 123 to automatyczna bramka MODEL_ABOVE_OWN_SAMPLE.
  - WATCH od analityka:
    - Davidovich Fokina - Jodar: Jodar liczba podwójnych błędów, powyżej 0.5 @1.29. Własne linie klucza dały -24 pp.
    - Davidovich Fokina - Jodar: Jodar liczba gemów, poniżej 14.5 @1.30. Rating 0.79, a próbka 4/10.
    - Alvarado - Cipolletti: Alvarado liczba goli, poniżej 1.5 @1.50 (motywacja, rewanż).
    - Güemes - Almagro: Handicap Güemes (+1.5) @1.71. Güemes nie strzelił gola w 5 ostatnich meczach.
  - NO_BET od weryfikatora. Obie nogi nie spełniają już x ≥ 0.90 przy żywej cenie Superbetu:
    - M'gladbach - Hoffenheim: liczba obronionych strzałów, poniżej 8.5 (1.25 → 1.24).
    - M'gladbach - Hoffenheim: Hugo Bolin, strzały powyżej 1.5 (1.27 → 1.25).
- **Weto CONTEXT na całe zdarzenie:** GD Alcochetense - CS Marítimo (Puchar Portugalii). Rating, licząc przez siłę lig, robi stronę z niższej ligi silniejszą. To wzorzec Aktobe.

## Przebieg

- **Mostek:** Chrome padł około 05:13Z i jedno zadanie utknęło. `ensure_bridge.py` ponownie otworzył 5 okien, a `check_bridge` dał OK.
- **D-1 (10-17):**
  - Rozliczył `sofa-settler`. SHADOW_SETTLE pętli przypadł na awarię mostka (2 ERROR w hokeju), więc puściłem go ponownie, gdy pętla się skończyła: 0 błędów.
  - Wynik 7c: -560.32 j. na 11 527 singlach.
  - Ledger 10-17 (mieszany): ROI -4.7% [-6.0; -3.3]. MISMATCH 0.
  - CLV kuponu: -3.84%.
- **Dowody linii:** `refresh_line_evidence.py --before 2026-10-18` zakończył się z exit 0, `fitted_from.before` = 2026-10-18. Sam fit wierszy koszykówki trwał ok. 45 min.
- **Etapy:** BOARD (1 262), RESOLVE PARTIAL (1 190 dopasowanych, 94.3%), OFFER PARTIAL ×2, SAMPLES OK, SHEET OK (123 650 wierszy, `stats_only`), COUPON OK.
- **Pokrycie rynków:** 180 nazw bez klasyfikacji (290 wystąpień), 7 MAPPABLE.
- **Kupon wstępny:** zbudowany na dowodach z 10-17, bo fit koszykówki jeszcze trwał. Analitycy przeczytali 402 nogi: piłka 2 WATCH, tenis 2 WATCH, sporty mierzone same KEEP.
- **Przebudowa na nowych dowodach:** przesunęła trzydziestkę meczów o najlepszej wartości. C3 wykazało 101 nóg bez odczytu w 19 meczach.
- **Druga runda:** 188 odczytów, w tym bufor 8 kolejnych meczów piłki oraz kandydaci do builderów. Dała 7 WATCH i weto Alcochetense. Po przebudowie C3 = 0.
- **Weryfikator:** 2 NO_BET (cena). Arytmetyka 78/78 rynków wynikowych zgodna, ceny na żywo 20/20 meczów, tożsamości sportowe zgodne.
- **`day_status`:** WARN. Przyczyny: CLV 64/76 (dzień w toku) oraz UNVERIFIED 46 meczów spoza limitu FIXTURE_CHECK, żaden z nich nie jest w zestawie odczytu. Pętle capture_closing, shadow i cs2 działają.

## Poprawka testów

Poranne dowody dały własne rozliczone linie kluczom, które cztery testy brały za „bez linii”: `double_chance`, `penalties_total`, koszykówka `h2_double_chance` oraz pasmo 1.00-1.30 strzałów prawą nogą. Testy czytały zainstalowany plik dowodów, więc nie były hermetyczne.

- Nowy pomocnik `tests/sofa/evidence_without.py` podsuwa kopię dowodów bez wskazanych rynków.
- Test rynków pochodnych sportów uznaje teraz źródło `sb:` za własne linie.
- Kod produkcyjny jest bez zmian.
- Wynik: `tests/sofa` 5 127 passed. ruff, mypy i rejestr testów czyste.

## Słabość dnia

Druga runda analityka piłki nie miała żadnych sprawdzeń w sieci (składy, absencje, stawka). Ponad 8 700 drukowanych pozycji poza zestawem odczytu poszło bez odczytu, zgodnie z regułą operatora. 64% nóg piłkarskich to rynki „lub” i podwójna szansa z jednej siatki NB na mecz. Ich jedyny pomiar na cenach Superbetu: ROI -2.4% [-6.1; +1.2].
