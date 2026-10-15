# Siła lig w pucharach międzynarodowych - wdrożenie, refit, instalacja (2026-10-15/16)

Zgoda operatora 2026-10-15: wdrożyć, zrobić refit piłki i zainstalować przed
budową 2026-10-16; przełącznik `FOOTBALL_CUP_STRENGTH_FROM_UTC` od
2026-10-16 00:00Z, nie wcześniej; wdrażać tylko wariant lepszy poza próbą z
przedziałem nieobejmującym zera. Kupon 10-15 nietknięty. Dowód:
`docs/sofa/evidence/cross_league_cups_2026-10-15.md` (sekcja „Wariant E”).

## 1. Wynik w jednym akapicie

Rating piłkarski zaniżał w pucharach międzynarodowych stronę z silniejszej
ligi (+5,2 pp P(wygranej) [+3,6; +7,0], 2 895 meczów). Od 2026-10-16 00:00Z
`RatingBook` uczy się poprawki siły ligi tylko z meczów cross-league
dziewięciu pucharów, wewnątrz własnej aktualizacji (wariant E). Poza próbą
(TEST od 2025-07-01): log-loss 1X2 **-0,0285 [-0,0381; -0,0188]** na 2 194
meczach (lepiej niż post hoc D, -0,0262); gole 1. / 2. połowy i strzały też
lepiej z przedziałem poniżej zera; **rożne i strzały celne - nie** (bez
korekty). Mecze spoza pucharów: nic nie pogorszone (302 635 meczów, gole
-0,00003 [-0,00006; -0,000003]). Krzywe piłki / tenisa przefitowane na
replayu z tą regułą (125,4 mln wierszy); same krzywe ruszają pewność wspólnych
nóg o najwyżej 0,006 - cała realna zmiana to mecze pucharowe.

## 2. Pomiar przed wdrożeniem (krok a)

`measure_cross_league_cups.py --in-book` (replay produkcyjnego `RatingBook`
A vs E, krok na TRAIN 2024-07-01..2025-06-30, TEST od 2025-07-01, kontrola
cięcia od 2026-01-01), `--spill` (mecze spoza pucharów):

| metryka | krok | TEST 2025-07 (E - A) | TEST 2026-01 | decyzja |
|---|---|---|---|---|
| gole (log-loss 1X2) | 0,05 | -0,0285 [-0,0381; -0,0188] | -0,0233 [-0,0355; -0,0110] | **tak** |
| gole 1. poł. (dewiancja) | 0,05 | -0,0209 [-0,0292; -0,0132] | -0,0191 [-0,0306; -0,0078] | **tak** |
| gole 2. poł. | 0,02 | -0,0143 [-0,0190; -0,0095] | -0,0147 [-0,0216; -0,0075] | **tak** |
| strzały | 0,02 | -0,0478 [-0,0800; -0,0179] | 0,02: -0,0461 [-0,0798; -0,0110] (wybór z TRAIN 0,05 w zerze) | **tak**, z zastrzeżeniem |
| strzały celne | 0,02 | -0,0165 [-0,0322; -0,0014] | w zerze | nie |
| rożne | 0,02 | -0,0062 [-0,0232; +0,0105] | w zerze | nie |

Kalibracja różnicy goli (TEST, strona silniejszej ligi wg Elo pucharowego),
realne - przewidywane: A +0,260 [+0,179; +0,335], E -0,065 [-0,145; +0,008].

## 3. Implementacja (krok b)

| co | gdzie |
|---|---|
| korekta w księdze: `cup_competitions`, `cup_eta` (metryka -> krok), `cup_delta`; czytana na meczu pucharu cross-league, uczona w `update` | `src/bet/sofa/football_rating.py` |
| lista pucharów i kroki (lista operatora, nie fit; poza `config_sha`) | `config/sofa_cup_strength.json`, `src/bet/sofa/cup_strength.py` |
| przełącznik `FOOTBALL_CUP_STRENGTH_FROM_UTC` = 2026-10-16 00:00Z, marker `cup_strength_rule` (`cup_strength_v1`) | `src/bet/sofa/epochs.py` |
| SHEET: księga z korektą, marker na wierszach piłki | `scripts/sofa/run_sheet.py` |
| przebudowa puszcza SHEET na arkuszu bez markera (dzień i zegar >= przełącznika) | `src/bet/sofa/rebuild_plan.py` |
| replay `--cup-strength` (`calibrate_from_cache.py`, `prepare_refit.py rebuild-cache-rows`) | |
| testy | `tests/sofa/test_cup_strength.py` (18) |

Wyłączony = księga jak była: test `test_off_is_the_book_as_it_was`; E2E: SHEET
10-15 z wyłączonym przełącznikiem ma `p_central` identyczne z prawdziwym
arkuszem na 51 026 wspólnych wierszach. Commity: `a0398546`, `d384f850`,
`b2c7e3b3`, `63ee3f66`.

Ograniczenie: korekta próbki B15 (`SampleCorrector`) przeskalowuje mecz
pucharowy z próbki samą sigmą, bez `d` (nie mierzone).

## 4. Refit na kopii (krok c)

- Kopia: `VACUUM INTO data/refit_2026-10-16/sofa_replay.db` (46,7 GB, 8,5 min,
  2026-10-15 10:02Z).
- Replay: `prepare_refit.py --date 2026-10-16 --db-path
  data/refit_2026-10-16/sofa_replay.db --scratch data/refit_2026-10-16/ft
  rebuild-cache-rows --confirm --without-db-backup` + flagi refitu 10-14
  (`--with-halves --player-starts-only --derived
  cards_points,goals,corners,shots_on_target --count-dispersion
  --cards-correlation --per-market-k --tennis-scoped-table --football-rating
  --rated-scope --venue-prior --game-state --rating-weight --season-phase
  --opponent-correction --tennis-set-ratings`) + `--cup-strength`. 10:24Z ->
  15:23Z, **125 381 834 wiersze** (10-14: 121,9 mln), żywe wiersze bez zmian.
- **Fit - błąd i poprawka.** Pierwszy `fit` (17:06Z) padł w `fit_constants`
  (`ZeroDivisionError` w `_brier_by_k`): w bazie są już rozliczone żywe
  wiersze rynków wycenianych samym ratingiem (double_chance 308, first_goal
  197, set_score 167, match_won_for 96, set1 / set2_won_for 94 + 94,
  red_cards 47, penalties 46) z `sample_size = 0`; przy K = 0 n / (n + K)
  dzieli przez zero. Nie ma to związku z pucharami - każdy refit na dzisiejszej
  bazie by padł. Poprawka (`3f77701e`): dopasowania K pomijają wiersze bez
  próbki (ich p nie zależy od K), test regresji. `fit_confidence` bierze tylko
  `sample_size > 0`, więc nie dotyczyło go.
- Drugi `fit` (17:29Z -> 18:38Z): `fit_constants` PARTIAL jak 10-14 (`K_CENTRE`
  15, `K_PRICE` / `MAX_LADDER_SIGMA` bez danych; bazy lig 121 rynków, było
  113 - doszły nowe rynki ratingowe); `fit_confidence` OK, 122,7 mln wierszy,
  96 rynków, 168 kierunków.
- **Klucze dopasowane osobno przeniesione 1:1** z zainstalowanej kalibracji
  (`data/refit_2026-10-16/carry_over.py`): `match_won_for` (+ `tennis_women`)
  i 21 kluczy nowych rynków z 2026-10-15 (`new_market_curves_fitted_from`)
  - `fit_confidence` ich nie produkuje. Po przeniesieniu zestaw kluczy taki
  sam jak zainstalowany; ubyły dwie komórki „thin” (`most_cards_points`
  OVER, `throw_ins_1h_for` OVER). Krzywe nowych rynków (DC / DNB / pierwszy
  gol) były dopasowane na centrach bez korekty pucharowej - na meczach
  pucharowych to przybliżenie (nie przefitowane).
- `compare --days 2026-10-13 2026-10-14` (CONFIDENCE stare vs nowe krzywe,
  zegar budowy, bez SHEET-u): 10-14 drukowane 816 -> 809 (odpadło 10 nóg
  przy progu ~0,70, głównie tenis `games_won_for`; doszły 3; 552 zmienione o
  tysięczne); 10-13 (zegar 21:06Z) 40 -> 40.
  `data/refit_2026-10-16/ft/compare_report.md`.
- `tests/sofa` z `SOFA_CONFIG_DIR` = nowy config: 4 836 passed / 2 skipped.

## 5. E2E na kopii 10-15 (krok d)

Katalog `data/e2e_2026-10-16_cups/`, zegar `SOFA_NOW` = ostatnia przebudowa
08:31:27Z, przełącznik przesunięty na 10-15 tylko w wrapperze
`stage_with_cup_on.py` (kod repo bez zmian). SHEET dwa razy (off / on), potem
CONFIDENCE (single):

| porównanie | wspólne | pewność ruszona | śr. / max | znikło | doszło |
|---|---|---|---|---|---|
| same nowe krzywe (SHEET bez pucharów) | 1 267 | 898 | +0,0001 / 0,006 | 8 | 7 |
| same puchary (nowe krzywe) | 1 245 | 60 (59 pucharowych) | +0,007 / 0,124 | 29 (27 puch.) | 57 (56 puch.) |
| razem: stan 10-15 -> stan od 10-16 | 1 238 | 906 | +0,0005 / 0,124 | 37 | 64 |

SHEET: 95 meczów zmienia `p_central` - 42 z 43 meczów pucharowych na
tablicy i 53 spoza (efekt uboczny zmienionych ilorazów drużyn grających w
pucharach; zmierzony w `--spill` jako neutralny / minimalnie lepszy). Rożne /
kartki / faule meczu pucharowego ruszają się przez stan gry (B1). 50 z 64
nowych nóg ma pewność poniżej 1/kurs.

Mecze wetowane ręcznie przez analityków 10-15 (1X2 SHEET-u, off -> on):

| mecz | gospodarz | gość | co z nogami |
|---|---|---|---|
| Lech - Leverkusen | 0,479 -> 0,425 | 0,287 -> 0,334 | 20 nóg, bez zmian poza kartkami Leverkusen 0,865 -> 0,837 (1X Lecha nie drukuje się w żadnym wariancie) |
| Celje - Omonia | 0,459 -> 0,314 | 0,272 -> 0,410 | „Celje gole < 2,5” 0,822 -> 0,901; „Omonia gole 1. poł. < 1,5” znika |
| CSKA Sofia - Monaco | 0,369 -> 0,149 | 0,407 -> 0,683 | nowe: X2 @1,12 0,883, DNB Monaco 0,800, Monaco strzeli gola 0,906; znika kartki Monaco > 0,5 |
| Egnatia - Midtjylland | 0,397 -> 0,251 | 0,369 -> 0,532 | nowe: rożne Midtjylland > 2,5 (0,840) i > 3,5 (0,727) |

Przy okazji Dinamo Zagrzeb - Anderlecht: 1X 0,855 -> 0,731.

md5 prawdziwych plików 10-15: zmienione między 11:30Z a 13:03Z przez siedem
przebudów z nowymi odczytami analityków (`rebuild_20261015T1130..1258Z`,
`2026-10-15_analiza_*.md`) - nie przez ten E2E: każdy jego przebieg pisał do
`data/e2e_2026-10-16_cups/` (repo odrzuca `SOFA_NOW` na prawdziwym
katalogu), żaden plik 10-15 nie zmienił się w oknach przebiegów E2E
(10:27-10:45Z, ~18:45Z), `05_sheet.json` z identycznym md5.

## 6. Instalacja (krok e)

- 23:00:09Z pierwsza próba `install --confirm`: **odmowa** - plik krzywych w
  scratch różnił się od tego, co zapisał `fit` (przeniesione / podmienione
  klucze z p. 4, 5). Manifest fitu dostał jawny wpis `post_fit_edits` (oba
  skrypty, sha256 surowego fitu i pliku po edycji, kopia surowego fitu
  `ft/sofa_confidence_calibration.fit_only.json`); plik = ten sprawdzony w E2E
  (md5 `da109134…`).
- 23:00:34Z druga próba: odmowa - brak kopii configu; `backup` ->
  `config/backup_2026-10-16` (31 plików).
- **23:02:19Z: zainstalowane** `sofa_engine_constants.json`,
  `sofa_league_baselines.json`, `sofa_market_reliability.json`,
  `sofa_confidence_calibration.json`; testy instalatora **4 845 passed / 2
  skipped**. Żaden test-strażnik nie padł (wszystkie przeszły już wcześniej z
  `SOFA_CONFIG_DIR` = nowy config), więc nic w testach nie poprawiano.
- Weryfikacja po instalacji: md5 czterech plików = md5 configu z E2E;
  `epochs.football_cup_strength` 10-16 04:00Z True, 10-15 False;
  `rebuild_plan` dla 10-16 bez markera puszcza SHEET; 21 kluczy nowych
  rynków i `match_won_for` w pliku; `fitted_from.replay_rules.flags.cup_strength`
  true.
- Kupon 10-15 nie był przebudowywany po instalacji.

## 7. Ledger

Refit instalowany po 23:00Z, przed budową 10-16 - **dzień nie jest
mieszany**. Ale instalacja refitu otwiera epokę (CLAUDE.md, Comparability),
a o 2026-10-16 00:00Z wchodzi też `BASKETBALL_DC_PAIR`: nowa grupa
**„od 10-16”** (`audit_ledger.CUP_STRENGTH_EPOCH_FROM_DATE`, `faf14f75`),
nigdy sumowana z „od 10-15”.

## 8. Otwarte

- Krzywe DC / DNB / pierwszy gol nie są przefitowane z korektą pucharową.
- Korekta próbki B15 bez `d` na meczach pucharowych z próbki.
- Kartki / faule / spalone / połowy rożnych i strzałów - korekta niemierzona.
- 10-16 to piątek - meczów pucharowych mało; pierwszy pełny dzień pucharowy
  pod nową regułą: wtorek 10-20 (LM).
- Czy poprawka bije cenę Superbetu na nogach pucharowych - niezmierzone
  (historia nie ma cen); liczy się seria dni w grupie „od 10-16”.
