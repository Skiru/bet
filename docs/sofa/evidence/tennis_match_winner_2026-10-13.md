# D2: tenis - zwycięzca meczu z ratingu as-of (audyt 2026-10-13)

Przełącznik: `epochs.TENNIS_MATCH_WINNER_FROM_UTC` (domyślnie `None`).
Zgoda operatora na refit zwycięzcy meczu tenisa: 2026-10-13 (O6, V2L-19).
Kod: `bet.sofa.tennis_winner`; dopasowanie i pomiar:
`scripts/sofa/fit_tennis_winner_curve.py` (tylko odczyt bazy, krzywa do
katalogu roboczego, nigdy do `config/`).

## Rejestracja (zapisana 2026-10-13 przed uruchomieniem pomiaru)

- Hipoteza: p zwycięstwa gracza z ratingu as-of, którym SHEET już liczy
  (`tennis_rating.AsOfRating`, tabela tier x płeć i `tier_start`,
  `MatchForecast.p_home`), niesie informację ponad stopę bazową klasy, a
  krzywa historii dopasowana na replayu tego p jest skalibrowana w kubełkach
  >= 0,70. Cena nie wchodzi do p (nigdzie).
- Populacja: historia singli z bazy (`tennis_rating.load_history`), mecze
  zakończone (bez kreczu i walkowera - Superbet je zwraca), best-of-3
  (SHEET nie wycenia best-of-5), obaj gracze z >= `MIN_RATED` meczów
  (inaczej SHEET nie ma prognozy), bez pucharów drużynowych i pokazówek
  (`CLASS_TENNIS_TEAM_CUP` - CONFIDENCE ich nie drukuje). Model na dzień
  meczu (cięcie 00:00Z), jak SHEET.
- Okno walk-forward: mecze 2026-04-01 .. 2026-10-12 (koniec 2026-10-13 00:00Z,
  wyłącznie). Krzywa uczona na meczach < 2026-08-15, holdout 2026-08-15 ..
  2026-10-12.
- Dwa warianty współczynników (jak C3, `measure_tennis_outcome_model.py`):
  `live` = `config/tennis_rating.json` (to, co drukuje SHEET; współczynniki
  dopasowane na historii do 2026-10-01 - znane spojrzenie w przód replayu) i
  `clean` = `tier_start` i współczynniki dopasowane na meczach przed
  2026-04-01 (bez spojrzenia w przód).
- Metryka 1 (umiejętność): średni log-loss p zwycięstwa gospodarza minus
  log-loss stopy bazowej klasy (tier x płeć, as-of, Laplace) na całym oknie;
  95% przedział z bootstrapu po meczach (1000, ziarno 20261012). Obok: Brier.
- Metryka 2 (kalibracja krzywej): krzywa uczona jak `fit_confidence.py`
  (kubełki `EDGES`, `MIN_MARKET_BUCKET` 400, `realised_lo95` = dolna granica
  Wilsona) na wierszach treningowych obu stron meczu; na holdoucie każdy mecz
  daje faworyzowaną stronę (p >= 0,5), drukowana pewność = `realised_lo95`
  kubełka krzywej treningowej. Luka = średnia pewność - realizacja w
  holdoucie, per kubełek >= 0,70 i łącznie >= 0,70; 95% przedział z bootstrapu
  po meczach.
- Próg (oba warunki):
  1. log-loss lepszy od bazy: górna granica 95% różnicy < 0, w obu
     wariantach;
  2. wariant `live`: w każdym kubełku >= 0,70 z n >= 300 (holdout) oraz
     łącznie >= 0,70: |luka| <= 2 pp (reguła PASS `measure_calibration.py`,
     `calibration_audit.MAX_GAP` / `MIN_SETTLED`). Kubełek z n < 300 jest
     INSUFFICIENT i nie rozstrzyga. Dodatkowo raportuję drugi warunek PASS
     `calibration_audit` (przedział zawiera 0) - przy pewności liczonej jako
     dolna granica Wilsona luka jest z konstrukcji ujemna, więc ten warunek
     jest informacyjny, nie jest progiem.
- Krzywa do instalacji: ten sam fit na wszystkich wierszach okna (wariant
  `live`), klucz `match_won_for` w `by_market` i w `by_class.tennis_women.
  by_market`; bez krzywych kierunkowych (strona OVER to pierwszy gracz
  Superbetu - kolejność bez znaczenia, krzywa jest symetryczna).
- Nakładanie się z „Measured and declined”: brak (nowy rynek, bez ceny w p).

## Wynik (2026-10-13, `data/refit_2026-10-13/d2/`)

Kopia bazy `data/refit_2026-10-13/sofa_replay.db`; historia 246 293 meczów
singlowych. W oknie 49 791 meczów z prognozą (trening 35 513 < 08-15,
holdout 14 278). Odpadły: bez ratingu 14 596 (gracz < `MIN_RATED`, brak
współczynników tieru), nieukończone (krecz / walkower) 2 410, best-of-5 404,
puchary drużynowe 266. Pliki: `results.json`, `report.md`,
`rows_live.csv`, `rows_clean.csv`, `tennis_winner_curve.json`.

**Metryka 1 - umiejętność (log-loss p_home minus baza klasy, na mecz):**

| wariant | n | LL model | LL baza | różnica [95%] | Brier różnica [95%] | |
|---|---|---|---|---|---|---|
| live | 49 791 | 0,5654 | 0,6917 | **-0,1263 [-0,1303; -0,1228]** | -0,0567 [-0,0583; -0,0552] | PASS |
| clean | 49 791 | 0,5668 | 0,6917 | **-0,1249 [-0,1289; -0,1213]** | -0,0562 [-0,0578; -0,0547] | PASS |
| live, sam holdout | 14 278 | | | -0,1338 [-0,1408; -0,1275] | | |

Zgodne z C3 (RAPORT_NOC_2026-10-12: -0,1232 na 06-09..10-07).

**Metryka 2 - kalibracja krzywej treningowej na holdoucie (live; faworyt
meczu; pewność = `realised_lo95` kubełka; luka = pewność - realizacja):**

| kubełek | n | średnie p | pewność | realizacja | luka pp [95%] | werdykt |
|---|---|---|---|---|---|---|
| 0,700-0,750 | 1709 | 0,725 | 0,714 | 0,742 | -2,8 [-5,0; -0,7] | FAIL |
| 0,750-0,800 | 1486 | 0,775 | 0,759 | 0,789 | -2,9 [-4,8; -0,8] | FAIL |
| 0,800-0,825 | 716 | 0,812 | 0,784 | 0,834 | -5,0 [-7,8; -2,2] | FAIL |
| 0,825-0,850 | 642 | 0,837 | 0,826 | 0,871 | -4,5 [-6,8; -2,0] | FAIL |
| 0,850-0,875 | 568 | 0,862 | 0,849 | 0,845 | +0,4 [-2,4; +3,6] | PASS |
| 0,875-0,900 | 528 | 0,888 | 0,884 | 0,886 | -0,2 [-2,8; +2,5] | PASS |
| 0,900-0,925 | 421 | 0,912 | 0,905 | 0,926 | -2,1 [-4,5; +0,5] | FAIL |
| 0,925-0,950 | 366 | 0,937 | 0,937 | 0,948 | -1,1 [-3,3; +1,3] | PASS |
| 0,950-1,010 | 341 | 0,968 | 0,948 | 0,977 | -2,9 [-4,3; -1,4] | FAIL |
| łącznie >= 0,70 | 6777 | 0,815 | 0,802 | 0,828 | -2,6 [-3,5; -1,7] | FAIL |

Wariant clean: łącznie -2,5 [-3,4; -1,7], 4 z 9 kubełków PASS (tabela w
`report.md`).

**Werdykt wobec progu: NIE spełniony.** Warunek 1 (umiejętność) spełniony z
dużym zapasem w obu wariantach. Warunek 2 (|luka| <= 2 pp w każdym
rozstrzygającym kubełku i łącznie) - nie: 5 z 9 kubełków i łączny wynik
wychodzą poza 2 pp. **Wszystkie przekroczenia są po stronie ostrożnej**
(drukowana pewność poniżej realizacji, czyli niedoszacowanie); żaden kubełek
nie zawyża pewności o więcej niż +0,4 pp (live) / +1,7 pp (clean), a ich
przedziały obejmują zero.

Rozbicie (diagnostyka po fakcie, nie część progu): luka punktowa krzywej
(`realised` treningu minus realizacja holdoutu, ważona n holdoutu) to łącznie
-1,0 pp (clean -0,9), a samo p modelu na holdoucie jest niedoszacowane o
1,3 pp (0,815 vs 0,828) - faworyci wygrywali w sierpniu-październiku częściej
niż w kwietniu-sierpniu; reszta luki, -1,6 pp, to dolna granica Wilsona
(n treningu 750-4200 na kubełek). Line evidence dołoży jeszcze ujemny offset tenisa (pula sportu,
dopóki klucz nie ma 50 własnych linii) - też w dół.

**Krzywa staged** (`data/refit_2026-10-13/d2/tennis_winner_curve.json`,
wszystkie wiersze okna, wariant live): `by_market.match_won_for` np.
0,700-0,750 n 5925 lo95 0,7206; 0,800-0,825 n 2353 lo95 0,7967;
0,900-0,925 n 1485 lo95 0,9093; `by_class.tennis_women.by_market.match_won_for`
0,700-0,750 n 2546 lo95 0,7294. Bez krzywych kierunkowych. Nie zainstalowana;
przełącznik `None`. Decyzja (próg niespełniony od strony ostrożnej) należy do
koordynatora / operatora.

Zastrzeżenia: współczynniki `live` widziały historię do 2026-10-01 (znane
spojrzenie w przód replayu; `clean` bez niego daje to samo); reguła Superbetu
dla zwycięzcy przy kreczu niesprawdzona w regulaminie (pipeline zwraca każdy
krecz - `RETIRED` w `REFUND_REASONS`); best-of-5 i ~23% meczów bez ratingu (14 596 z 64 387)
nie drukują (`NOT_RATED`).
