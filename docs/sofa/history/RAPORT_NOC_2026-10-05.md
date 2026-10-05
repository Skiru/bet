# Noc 2026-10-04/05 — refit i przegląd wszystkich sportów

Polecenie operatora: refit krzywych po zmianie reguł próbek z 10-04 (po
rozliczeniu 10-04, przed dniem), a w nocy iteracyjny przegląd wszystkich
sportów z poprawkami, testami i weryfikacją na żywo. Wszystkie commity na
`main`, **niewypchnięte**. Szczegóły i dowody w opisach commitów.

## 1. Refit — stan

- Próba na klonie APFS bazy (`cp -c`, 0 B na dysku) dwa razy zawisła.
  Przyczyny i poprawki:
  - `3620dc45`: replay trzymał 1,41 mln pełnych zdarzeń wszystkich sportów
    (25 GB); szczyt pamięci 31,5 → 20,3 GB. Przy okazji 39 meczów piłki
    wraca do replayu (sklejane z meczem innego sportu o tych samych nazwach).
  - `0dedf68f`: kasowanie sklejonych duplikatów szło indeksem `run_date`
    (2490 × 59 mln wierszy); teraz indeksem po id zdarzenia (0,01 s / 100).
  - Trzecia próba czysta (replay 26 min, fit 31 min, compare 8 min);
    raport próby: `data/refit_rehearsal_2026-10-04b/work/compare_report.md`.
- Na prawdziwej bazie: `backup --db` (`data/backup_2026-10-05/sofa.db`,
  `config/backup_2026-10-05/`), potem `rebuild-cache-rows` — cztery razy, bo
  przegląd zmieniał to, co produkuje historia; ostatni na kodzie `50a236f0`.
- **Rano (01:58–02:52Z), zrobione:** SETTLE 10-04 (588/596 meczów, 23 208
  wierszy) → refetch luk 09-30 → `regrade_settled --apply` (8 odwróconych
  wyników 09-24, 61 wartości) → ledger 09-27..10-04 (10-04: oficjalny 19/10,
  −3,28 j., −11,3%; WARIANT 303/169, −50,92 j., −10,8%) → `fit` → `compare
  --days 2026-10-03 2026-10-04 --with-sheet` → **`install` (commit `6fea99fd`)**.
  K_CENTRE piłka 15 / tenis 5 bez zmian, krzywe 92 → 94 (żadna nie znikła),
  half_match_coherence OK; replay oficjalnego kuponu 10-03 34 → 36 nóg, 10-04
  32 → 32. Klucze operatora przeniesione. Uwaga: 39 starych wierszy, których
  nowy kod nie rozlicza (np. Buxton), regrade zostawia z dawnym wynikiem.

## 2. Poprawki (przegląd: 5 recenzentów + 2 rundy przeglądu własnych poprawek)

Zmienia to, co produkuje historia (`HISTORY_PARSER_VERSION` 2026-10-04.5):

| commit | co |
|---|---|
| `c4149ec9` | gole z tych samych rozgrywek tylko dla meczów ligowych — **zmierzone**: na 24 777 / 31 738 meczach pucharowych reguła gorsza (goals_total +0,00546 [+0,00373; +0,00725], goals_for +0,01227 [+0,00951; +0,01526] log-loss); wynik sam sobie przeczący nie jest liczbą goli (Buxton – South Shields); gemy tenisa z wyniku setów (Shang – Mannarino: 19 zamiast 21, 8 odwróconych rozliczeń) |
| `12e8d1e4`, `5012026c`, `0e6e8187` | replay czyta gole, gemy i zakończenia jak SAMPLES/SETTLE; krecze i walkowery poza replayem (4,5% zakończonych meczów tenisa w próbce); pokazówki tenisowe poza fitem; „Coverage canceled” to nie zakończony mecz. Populacja gemów tenisa w replayu **bez zmian** (rozszerzenie o ~145 tys. meczów bez statystyk to osobna decyzja do zmierzenia) |
| `7e964b98` | tie-breaki z wyniku setów (statystyka 0/0 przy 7-6) |

Rozliczanie i zapis wyników:

| commit | co |
|---|---|
| `cd21f23e`, `1f5af54e` | SETTLE przypisuje drużynę jak SHEET — wydrukowane nogi typu „utsikten” były nierozliczalne (39 podmiotów odzyskanych, 0 zmienionych na 10 503); rynki pochodne tak samo; brak wierszy PUSH |
| `cd21f23e` | 7c / 7d / ledger nigdy nie biorą wiersza replayu (`cache-calibration`) jako wyniku wydrukowanej nogi |
| `2ef7a299`, `1f5af54e` | zamrożony zegar (`SOFA_NOW`) odrzucany w każdym skrypcie piszącym do `runs/sofa` (sprawdzone na żywo) |
| `29ca4569` | PDF nie drukuje z CONFIDENCE starszego niż plik krzywych (`refused_markets`) |

Sporty mierzone:

| commit | co |
|---|---|
| `f7898d05` | CS2: aliasy NIP / BET-M 33, drugi skład (Academy, Impact…) to inna drużyna, rewanże w grupie, brak ceny po starcie wg Sofascore |
| `452387bd`, `50a236f0` | CS2: nieudana ponowna próba nie gubi turnieju ani stanu „nie znaleziono” |
| `43b126c3`, `2aad6272` | shadow: mecz bez linii dostaje pusty rekord (koniec rozliczania cen sprzed 10–12 h), a mimo to jest rozliczany (nogi kuponu) |
| `04d131f1`, `1f5af54e` | siatkówka: zwycięzca z setów przy `winnerCode` 3, tylko przy wygranej 3 setami |

## 3. Weryfikacja na żywo

- CS2 sweep 09-28..10-03: wszystkie 11 serii NiP / 33 **SETTLED** (np.
  NiP – GamerLegion 388 stron), rewanże Hotu i OMEGA rozliczone.
- Shadow 10-03: siatkówka DATA_MISMATCH 9 → 1, SETTLED 94 → 103.
- `SOFA_NOW` + `run_coupon --date 2026-10-04`: REFUSED, katalog dnia nietknięty.
- Testy: 2878 zielonych; mypy --strict czysty.

## 4. Do decyzji operatora (nie zmienione)

1. **Który PDF jest kuponem dnia.** Przebudowa po pierwszych startach usuwa
   z 7c/ledgera nogi wydrukowane wcześniej (10-03: 1 oficjalna, 66 WARIANT;
   10-04: 21 WARIANT). Czy liczyć każdą nogę wydrukowaną przed jej startem?
2. **Krecz w tenisie.** Rynki rozstrzygnięte przed kreczem (set 1, przekroczony
   OVER) dziś nie są rozliczane. Reguła Superbetu niesprawdzona — jedno
   źródło (meczyki.pl: „krecz = zwrot dla wszystkich zdarzeń, które nie mogły
   być rozliczone”).
3. **Rekalibracja ceny w kuponach hokeja i koszykówki** (`data/analysis_2026-10-04_shadow/RAPORT.md`):
   cena przecenia faworytów o 3–4 pp; rekalibracja daje uczciwe p, ROI bez zmian.
4. **Siatkówka:** ponad połowa nóg kuponu z turniejów, których Sofascore nie
   ma (20/38 nierozliczalne) — wymagać ≥1 rozliczonego meczu turnieju?
5. **Populacja gemów tenisa w replayu** (mecze bez `/statistics`) — zmierzyć
   osobno przed włączeniem.

### 4a. Decyzje operatora — 2026-10-05 rano, przed dniem 10-05

Obowiązują od kuponu 10-05; wcześniejsze dni to inny eksperyment i nie są
łączone z późniejszymi.

- **Kupon oficjalny:** pewność × kurs ≥ 0,90 i marża linii do 15% (do 10-04:
  x > 1,00 i 10,5%); próg pewności 0,70 i honorowanie WATCH bez zmian. Tego
  samego ranka zniesiony limit 30 pojedynczych na PDF („nie limituj do 30”):
  oficjalny drukuje cały artefakt, jak WARIANT (na 10-04 nowa reguła dałaby
  303 pojedyncze). Analitycy czytają najwyżej 30 najlepszych: C3 wymaga
  odczytu tylko dla pierwszych 30 pojedynczych (kolejność artefaktu) i nóg
  builderów; reszta drukuje się bez odczytu. Próg pewności 0,80 rozważony i odrzucony („chcę mieć dużo
  opcji”). WARIANT bez zmian (0,65 / x ≥ 0,90 / 15%). Pomiar
  (`measure_disagreement.py`, 09-24..10-04, jedna krzywa, bez limitu marży):
  piłka stara reguła 2574 wierszy ROI −4,5% [−7,2; −2,0], nowa 8871 wierszy
  −4,8% [−6,1; −3,4]; tenis 151 wierszy −5,1% [−15,3; +5,3] → 3559 wierszy
  −3,8% [−5,7; −1,9]. Więcej wyboru przy tej samej stracie na zakład — nie
  przewaga. Commit `ec7af960`.
- **Pkt 1 — tak:** noga wydrukowana przed startem meczu się liczy. Przebudowa
  zachowuje na kuponie (zablokowane, „w grze”) nogi, których mecz już
  wystartował; noga usunięta przebudową *przed* startem zostaje usunięta.
- **Pkt 2 — bez zmian:** krecz jak dotąd (rynki rozstrzygnięte przed kreczem
  nie są rozliczane).
- **Pkt 3 — tak**, plus kupony sportowe (CS2, hokej, koszykówka, siatkówka):
  p × kurs ≥ 0,90 i marża do 15%; hokej i koszykówka drukują i progują
  p = a + c·logit(fair p) (`scripts/sofa/fit_sport_price_calibration.py`,
  `config/sofa_sport_price_calibration.json`, linie 09-29..10-03: hokej
  c = 0,893, LODO 0,869–0,914; koszykówka c = 0,888, LODO 0,845–0,918).
  Uwaga: devig Superbetu zrzuca marżę na outsidera, faworyt ma x ≈ 0,95 nawet
  przy 15% marży — próg 0,90 rzadko decyduje.
- **Pkt 4 — tak:** noga siatkówki wymaga turnieju z ≥1 rozliczonym meczem
  w ostatnich 14 dniach pomiaru.
- **Pkt 5 — tak:** zmierzyć osobno przed następnym refitem.
- **Propsy piłkarskie zostają** w `admitted_player_markets` (operator).
- Commity nocy wypchnięte na `origin/main`.

## 5. Inne sporty — pomiar (`data/analysis_2026-10-04_shadow/RAPORT.md`)

Na 5 rozliczonych dniach żaden model (hokej, koszykówka, siatkówka) nie bije
ceny Superbetu; koszykówka-handicap prerejestrowana do testu od 10-04
(`PREREJESTRACJA_koszykowka_handicap.md`); CS2 parzystość rund — przypadek
(24 931 map: 55,15% vs cena ~54,8%).
