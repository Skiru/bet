# Plan Naprawy Simple Pipeline: Eliminacja Wad Modelowych i Ślepych Plam (2026-09-10)

Dokument powstał po audycie kuponu z dnia 2026-09-09 (`docs/AUDYT_KUPONU_2026-09-09.md`), gdzie zidentyfikowano 7 rozliczonych strat na 37 zdarzeń (skuteczność 81.1%), z czego kluczowe pozycje VALUE poległy na powtarzalnych, systemowych mechanizmach:
1. **Mismatch klasowy w Europie** (PSG – Slovan 6:1 przy under 4.5)
2. **Oblężenie faworyta vs rożne** (Rangers – St. Mirren 12 rożnych przy under 7.5)
3. **Wariancja niskich kursów** (Pohang – Gimcheon 0:0 przy over 0.5 @1.02)
4. **Martwe metryki** (NO_DATA w Pucharze Kolumbii i tenisie)

Poniżej przedstawiono architekturę, specyfikację kodu, plan wdrożenia i testy regresyjne.

---

## 1. Zidentyfikowane luki systemowe

| Identyfikator | Zdarzenie testowe | Błędne założenie pipeline | Rzeczywisty mechanizm boiskowy |
|---|---|---|---|
| **GAP-1: Quality Mismatch** | PSG – Slovan (U4.5 gola @1.87) | Próbka ligowa Slovana (10/10 U4.5) określa rozkład w UCL | Elitarny faworyt przeciwko zespołowi z ligi o 3 poziomy niższej generuje blowout (6:1) |
| **GAP-2: Siege Corner Inversion** | Rangers – St. Mirren (Rangers rożne U7.5 @1.85) | Średnia rożnych faworyta jest stała niezależnie od rywala | Głęboki blok rywala + brak szybkiego gola = zmasowane bicie w mur i eksplozja rożnych (12) |
| **GAP-3: Zero-Defect Trap (<1.10)** | Pohang – Gimcheon (O0.5 gola @1.02) | p_central 98% gwarantuje opłacalność po 1.02 | 0:0 zdarza się w 7-9% ligowych meczów; kurs 1.02 ma ujemne EV i niszczy kapitał przy wariancji |
| **GAP-4: Unmeasured Metrics** | Real Cundinamarca (rożne), Andreeva (DF) | Generator emituje rynki, dla których nie ma protokołu | Zakłady wiszą jako martwe, niemożliwe do zweryfikowania przez oficjalne źródła |

---

## 2. Moduły techniczne do wdrożenia

### Moduł 1: Bramka `CEILING_QUALITY_MISMATCH`
* **Lokalizacja:** `src/bet/simple_stats/context_flags.py` oraz `src/bet/simple_stats/coupons.py`
* **Zasada działania:**
  * Weryfikacja typu rozgrywek (`competition` w UCL, UEL, Conference League, Copa Libertadores).
  * Jeśli mecz odbywa się w europejskich pucharach i różnica kursowa 1X2 na faworyta wynosi < 1.25 (lub różnica rankingu ligi > 15 pozycji):
    - **Weto:** `CEILING_QUALITY_MISMATCH`
    - **Akcja:** Zakaz rynków `goals_total UNDER` oraz `goals_for UNDER` (dla faworyta).
    - **Waga próbki:** `weight = 0` (zerowanie wagi próbki ligowej słabszej drużyny).

### Moduł 2: Bramka `CEILING_SIEGE_CORNER_INVERSION`
* **Lokalizacja:** `src/bet/simple_stats/context_flags.py` oraz `src/bet/simple_stats/coupons.py`
* **Zasada działania:**
  * Gdy gospodarz jest dominującym faworytem ligowym (kurs 1X2 < 1.35):
    - **Weto:** `CEILING_SIEGE_CORNER_INVERSION`
    - **Akcja:** Bezwzględna dyskwalifikacja rynków `corners_for UNDER` na faworyta oraz `corners_total UNDER` poniżej linii 11.5.
    - **Uzasadnienie:** Scenariusz „obrony Częstochowy” przez outsidera drastycznie zawyża liczbę rzutów rożnych faworyta.

### Moduł 3: Filtr nieobsługiwanych metryk ligowych (`UNSUPPORTED_LEAGUE_METRICS`)
* **Lokalizacja:** `src/bet/simple_stats/analyze.py`
* **Zasada działania:**
  * Rejestr lig i pucharów, dla których bzzoiro nie posiada oficjalnego zliczania rzutów rożnych/kartek (np. Copa Colombia, niszowe puchary krajowe).
  * Jeśli liga znajduje się na liście, etap `ANALYZE` pomija generowanie wierszy dla tych rynków, zapobiegając emisji martwych typów.

### Moduł 4: Twarde wygaszenie nieobsługiwanych rekwizytów tenisowych
* **Lokalizacja:** `src/bet/simple_stats/coupons.py`
* **Zasada działania:**
  * Dodanie rynków `aces_*` oraz `double_faults_*` do listy rynków zablokowanych (podobnie jak wyłączone już `player_prop_unpriceable`), dopóki nie zostanie zintegrowany provider ze statystykami serwisowymi tenisa.

### Moduł 5: Podniesienie dolnej granicy kursu w kuponie (`MIN_ODDS_FLOOR = 1.15`)
* **Lokalizacja:** `src/bet/simple_stats/coupons.py`
* **Zasada działania:**
  * Wiersze z kursem Superbetu poniżej 1.15 (np. 1.01, 1.02, 1.05) zostają automatycznie skierowane do kategorii `PRICED_TOO_LOW` i nie mogą trafić do sekcji rekomendowanych singli ani do żadnego sugerowanego kuponu akumulowanego.
  * Zgodnie z analizą historyczną (668 wierszy), pasmo 1.00-1.10 ma udokumentowany ujemny edge (-1.0% do -4.3%).

---

## 3. Plan wdrożenia krok po kroku

1. **Krok 1:** Implementacja reguł `is_quality_mismatch` oraz `is_heavy_favorite_siege` w `src/bet/simple_stats/context_flags.py`.
2. **Krok 2:** Dodanie odpowiednich sufitów (`CEILING_QUALITY_MISMATCH`, `CEILING_SIEGE_CORNER_INVERSION`) w `src/bet/simple_stats/coupons.py`.
3. **Krok 3:** Wprowadzenie progu `MIN_ODDS_FLOOR = 1.15` w filtracji singli i selektorze akumulatora w `src/bet/simple_stats/coupons.py`.
4. **Krok 4:** Wycofanie `double_faults_*` i `aces_*` z oferty kuponowej tenisa.
5. **Krok 5:** Przygotowanie testów jednostkowych i regresyjnych:
   * `tests/simple_stats/test_regression_2026_09_10_quality_mismatch.py`
   * `tests/simple_stats/test_regression_2026_09_10_siege_corners.py`
   * `tests/simple_stats/test_regression_2026_09_10_odds_floor.py`
6. **Krok 6:** Re-run backtestu za pomocą `scripts/simple/backtest_slate.py --date 2026-09-09 --rebuilt` i weryfikacja czy straty PSG i Rangers znikają z rekomendacji bez utraty wygranych pozycji.
