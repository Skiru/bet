# Dossier meczu i przegląd kontekstu analityków — 2026-10-20

## Powód

Operator, 2026-10-20, po kuponie z czatu 12-16: odczyty analityków były
płytkie. W sportach analityk sprawdzał tożsamość, cenę i „brak faktu
przeciw”, a w piłce uzasadnienie rożnych brzmiało samo „15/18”. Przyczyna
leżała w kontrakcie (`sofa-analysis-core`): sieć wolno było przeszukać raz na
mecz i tylko wtedy, gdy fakt „mógłby zmienić werdykt”. Analityk sportu nie
miał żadnego kroku statystycznego. Walidator nowego typu
(`check_analyst_report.py`) na raporcie `2026-10-20_analiza_football_2.md`
znalazł 99 uzasadnień KEEP bez treści i 0 sekcji kontekstu przy 12 meczach.

## Co zmieniono

1. **Dossier meczu** (`src/bet/sofa/dossier.py`): offline, czytane z
   `data/sofa.db` (tryb tylko do odczytu) i z artefaktów dnia, bez zapytań.
   Plik `runs/sofa/<d>/dossier/<sport>_<id>.json` piszą `read_set.py` i
   `build_slip.py`; ścieżka trafia do pola nogi `dossier`. Zawartość:
   - forma z ostatnich 10 meczów z okresami / setami, seria, bilans
     dom / wyjazd, odpoczynek oraz mecze w 7 / 14 dni;
   - H2H;
   - tabela odtworzona z listingów (podaje, ile meczów policzyła);
   - stadion z miastem, strefą i godziną lokalną, sędzia, ranking tenisisty;
   - CS2: skład z nowym nazwiskiem, pula map z 90 dni, forma graczy;
   - ruch każdej linii Superbetu przez dzień (sporty) lub drabinka (piłka /
     tenis);
   - wszystkie nogi meczu z wcześniejszymi odczytami;
   - lista kontrolna webu z wpisanymi nazwami i godziną.

   Dossier służy tylko do podglądu: nie zmienia pewności ani bramek.
2. **Kontrakt**:
   - `sofa-analysis-core` krok 3 / 4: obowiązkowy przegląd kontekstu w
     sieci dla każdego nierozpoczętego meczu — newsy, pogoda, nastroje i
     kulisy, stawka, opinie; do ~8 wyszukiwań na mecz;
   - nowy tag `MORALE` (`contracts.ContextSignal`);
   - waga: jedna domena / opinia = najwyżej WATCH przez zmienną nogi,
     dwie domeny = NO_BET;
   - szczegóły w `references/dossier.md` i `references/context-pass.md`;
   - procedury trzech analityków czytają dossier jako pierwsze.
3. **Kontrola jakości**:
   - `bet.sofa.report_check` i `scripts/sofa/check_analyst_report.py`;
   - hook `PostToolUse` (`.claude/settings.json`,
     `.claude/hooks/check_analyst_report.py`) sprawdza każdy zapisany raport
     `_analiza_*.md` i przy błędach (exit 2) odsyła listę agentowi, który
     sam poprawia raport.
4. **Rejestr**: hipoteza `T-CONTEXT-READS-REMOVE-LOSERS` (od 2026-10-21) —
   czy usunięcia z kontekstu zdejmują nogi gorsze od zostawionych w tych
   samych pasmach cen. Przewaga nie jest wykazana; to pomiar, nie obietnica.

## Pomiar pokrycia (2026-10-20, 322 mecze kuponu, 51 s)

| sport | mecze | forma ≥ 5 obu stron | H2H | tabela | miasto |
|---|---|---|---|---|---|
| piłka | 152 | 152 | 109 | 144 | 127 |
| tenis | 113 | 113 | 31 | — | 61 (ranking 110) |
| hokej | 35 | 35 | 35 | 35 | 32 |
| CS2 | 12 | 12 | 3 | — | — (skład 12, zmiana 2) |
| siatkówka | 9 | 4 | 4 | 8 | 9 |
| koszykówka | 1 | 1 | 0 | 1 | 1 |

## E2E (2026-10-20 ok. 12:15 lokalnie)

Kupon z czatu 14-18, 4 nogi: rożne ZED - Modern, strzały Al Riyadh,
strzały Al Qadsiah, gole HPK - Pelicans.
- **Przebieg:** analitycy (piłka i hokej) czytali kontrakt z dysku, bo
  definicje agentów wczytują się na starcie sesji.
- **Rozmiar:** raporty mają 193 + 81 linii, 28 tagów `[WEB: ...]`.
- **Wynik:** 4 × KEEP; `check_analyst_report` OK, `merge_reads --slip` exit 0.
- **Treść uzasadnień:** oczekiwanie w jednostkach rynku, fakty z dossier
  (tabela, odpoczynek, sumy) i kontekst ze źródłem — zmiana trenera,
  rotacja przed Al-Hilal, uraz, rewanż CAF, pogoda, absencje HPK.

Nie sprawdzono:
- składów (za wcześnie);
- bramkarzy startowych hokeja;
- drugiej domeny dla pogody.

Analityk zgłosił niepotwierdzoną (jedna domena) datę ZED - Modern na
21.10, sprzeczną z trzema zegarami artefaktów. Współrzędne stadionu Diriyah
w payloadzie Sofascore wskazują miejsce ok. 200 km od Rijadu; dossier podaje
dane Sofascore bez poprawek.

## Czego nie przetestowano

- **Hook `PostToolUse`:** testowany jako proces z JSON na stdin
  (`tests/sofa/test_report_check.py`). W tej sesji nie działał na żywo, bo
  konfiguracja hooków wczytuje się przy starcie sesji. Pierwsza sesja po
  zmianie: sprawdzić w `/hooks`.
- **Definicje agentów:** te same, wczytują się dopiero od następnej sesji.
- **Pełny poranny zestaw (30 meczów) pod nowym kontraktem:** nie był
  uruchomiony. Koszt czytania wzrośnie (do ~8 wyszukiwań na mecz).
