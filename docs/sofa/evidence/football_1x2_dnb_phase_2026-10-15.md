# 1X2 i DNB piłki z klasą krzywej po fazie sezonu (2026-10-14 wieczór, na 10-15)

Polecenie operatora 2026-10-14 ~18:55Z: zbudować 1X2 (wygrana gospodarzy /
gości) i DNB („Zakład bez remisu”) z krzywą znającą fazę sezonu, gotowe na
jutro, jeśli przejdą. Tło: `football_result_phase_2026-10-13.md` (D1) - DNB
nie przeszło progu, bo **krzywa z historii** przeszacowywała start sezonu
(-2,9 pp test, -3,5 pp sie-wrz), a surowe p NB na czystym ratingu było
skalibrowane; 1X2 po krzywej -4,08 pp.

Skrypt: `scripts/sofa/fit_result_1x2_dnb_curve.py` (tylko odczyt historii,
krzywe ZAPISANE, nie zainstalowane). Wyniki:
`data/refit_new_markets_2026-10-15/football_result_1x2_dnb/` (`curves.json`
w kształcie instalatora, `gate_report.md`, `rows.csv.gz`, `matches.csv.gz`).

## Rejestracja (przed uruchomieniem)

- **Model:** jak podwójna szansa (`football_result.result_probs`): niezależne
  NB goli stron na czystym ratingu (`FootballForecast.centre("goals_for")`,
  as-of), r = 7,586 z `config/sofa_football_result.json`. 1X2 „1” = P(wygrana
  gospodarzy), „2” = P(wygrana gości); DNB gospodarze = h / (h + a), goście =
  a / (h + a); remis w DNB to zwrot stawki, więc mecz zremisowany nie jest
  prognozą DNB. Remis 1X2 nie jest wyceniany (nie sięga 0,70).
- **Klasa krzywej:** faza meczu as-of (`season_phase.phases_by_event`):
  `season_early` = mecz mężczyzn w fazie `early` (kolejki 1-3);
  `women` = mecz kobiet (każda faza, jak dotąd); bez klasy = pozostałe mecze
  mężczyzn (mid / late / final / brak fazy). Każda krzywa dopasowana tylko na
  swoich wierszach.
- **Klucze:** `result_1x2|OVER` (obie strony w jednym kluczu; strony jako
  diagnostyka), `draw_no_bet|OVER` (gospodarze), `draw_no_bet|UNDER` (goście)
  - DNB to jeden szczebel dwustronny, więc każda strona ma swoją krzywą.
- **Okna:** trening 2024-10-01..2026-08-31, holdout 2026-09-01..2026-10-13,
  krzywa końcowa do 2026-10-14 włącznie. UNLINKED wyłączone (SHEET i tak je
  odrzuca): 22 462 z 594 579 meczów z ratingiem.
- **Próg (jednostronny, decyzja operatora 2026-10-14 ~18:55Z,
  `new_market_gate`):** wiersze z wartością krzywej >= 0,70, n >= 300,
  realised - krzywa >= -2 pp; krzywa końcowa musi sięgać 0,70.
- **Porównanie:** ten sam klucz bez klasy fazy (jedna krzywa dla mężczyzn) i
  wariant „bez krzywej, surowe p NB” (p >= 0,70, realised - p).

## Wynik (holdout 2026-09-01..2026-10-13)

Wybory: trening 1 907 476, holdout 124 470 (bez klasy 98 043,
`season_early` 17 294, `women` 9 133).

| klucz | werdykt | n (mecze) | krzywa | realised | luka [95% po meczach] |
|---|---|---|---|---|---|
| `draw_no_bet\|OVER` | **PASS** | 5 909 | 0,8131 | 0,7939 | -1,92 pp [-3,03; -0,86] |
| `draw_no_bet\|UNDER` | **PASS** | 2 011 | 0,8131 | 0,7931 | -1,99 pp [-3,75; -0,22] |
| `season_early:draw_no_bet\|OVER` | **PASS** | 524 | 0,7449 | 0,7748 | +2,99 pp [-0,50; +6,57] |
| `season_early:draw_no_bet\|UNDER` | FAIL (n 98) | 98 | 0,7219 | 0,7041 | -1,78 pp [-10,97; +7,40] |
| `women:draw_no_bet\|OVER` | **PASS** | 623 | 0,8239 | 0,8234 | -0,05 pp [-2,89; +2,79] |
| `women:draw_no_bet\|UNDER` | FAIL | 506 | 0,7876 | 0,7431 | -4,45 pp [-8,30; -0,39] |
| `result_1x2\|OVER` | FAIL | 2 755 | 0,8223 | 0,7844 | -3,79 pp [-5,35; -2,31] |
| `season_early:result_1x2\|OVER` | FAIL (n 269) | 269 | 0,7149 | 0,7175 | +0,26 pp [-4,90; +5,44] |
| `women:result_1x2\|OVER` | FAIL | 877 | 0,7833 | 0,7594 | -2,39 pp [-5,11; +0,25] |

1X2 per strona (bez klasy): „1” -3,69 pp [-5,49; -1,68] (n 1 946), „2”
-4,02 pp [-6,82; -1,29] (n 809) - obie przeszacowane.

Bez klasy fazy (jedna krzywa mężczyzn, ten sam holdout):

| klucz | cały holdout | tylko `early` | reszta |
|---|---|---|---|
| `draw_no_bet\|OVER` | -2,07 pp (n 6 889) FAIL | -4,83 pp (980) | -1,61 pp (5 909) |
| `draw_no_bet\|UNDER` | -2,37 pp (n 2 289) FAIL | -5,66 pp (278) | -1,91 pp (2 011) |
| `result_1x2\|OVER` | -3,92 pp (n 3 164) FAIL | -6,80 pp (409) | -3,49 pp (2 755) |

Surowe p NB bez krzywej (p >= 0,70):

| klucz | n | średnie p | realised | luka [95%] |
|---|---|---|---|---|
| `draw_no_bet\|OVER` mężczyźni | 6 889 | 0,7930 | 0,7891 | -0,39 pp [-1,38; +0,50] |
| `draw_no_bet\|OVER` bez `early` | 5 909 | 0,7933 | 0,7939 | +0,06 pp [-1,06; +1,11] |
| `draw_no_bet\|OVER` `early` | 980 | 0,7913 | 0,7602 | -3,11 pp [-5,89; -0,51] |
| `draw_no_bet\|UNDER` mężczyźni | 2 289 | 0,7953 | 0,7881 | -0,72 pp [-2,39; +0,90] |
| `result_1x2\|OVER` mężczyźni | 3 164 | 0,7812 | 0,7800 | -0,12 pp [-1,51; +1,26] |
| `result_1x2\|OVER` `early` | 409 | 0,7815 | 0,7506 | -3,08 pp [-7,28; +1,15] |

## Co z tego wynika

1. **Klasa fazy naprawia start sezonu w DNB.** Bez niej krzywa mężczyzn
   przeszacowuje mecze `early` o 4,8 pp (gospodarze) / 5,7 pp (goście);
   krzywa `season_early` czyta ten sam p dużo niżej (p 0,80-0,825: 0,744
   zamiast 0,832) i w holdoucie jest ostrożna (+3,0 pp). Na kolejkach 1-3
   rating jest nieaktualny (lato, transfery), więc p jest zbyt pewne - widać
   to i w surowym p (`early` -3,1 pp).
2. **Klucze bez klasy DNB przechodzą na granicy:** -1,92 / -1,99 pp, a
   przedział 95% leży cały poniżej zera - krzywa wciąż przeszacowuje ~2 pp
   (trening widział lepsze lata niż wrzesień 2026). Surowe p jest tu
   skalibrowane (+0,06 pp), krzywa podnosi je o ~2 pp. Jednostronny próg
   przepuszcza; to fakt do pilnowania na liniach Superbetu, nie dowód zysku.
3. **1X2 nie przechodzi w żadnej klasie.** Krzywa bez klasy -3,8 pp,
   `season_early` za mało wierszy (269 < 300), kobiety -2,4 pp. Surowe p 1X2
   jest skalibrowane poza startem sezonu (-0,1 pp), więc winna jest znowu
   krzywa - ale wariant „bez krzywej” nie ma ścieżki w CONFIDENCE (rynek
   ratingowy czyta tylko własną krzywą albo własne linie).
4. Goście `season_early` i kobiety-goście DNB odpadają (n 98; -4,45 pp).

## Decyzja i stan

- Przełącznik `epochs.FOOTBALL_RESULT_1X2_DNB_FROM_UTC` = **2026-10-15
  00:00Z** (przeszły co najmniej jeden klucz: cztery klucze DNB). Obejmuje
  oba rynki: OFFER czyta „Mecz” 1 / 2 jako `result_1x2` (OVER; UNDER = DC
  „X2” / „1X”) i „Zakład bez remisu” jako jeden szczebel `draw_no_bet`
  (subject „1”, OVER = gospodarze, UNDER = goście; strona po nazwie z
  listingu Superbetu, niejednoznaczna nazwa - pominięta); SHEET wycenia
  (`result_1x2_dnb_rule`, `result_phase`); CONFIDENCE czyta mecz mężczyzn w
  fazie `early` z klasy `season_early` (`football_1x2_dnb.leg_class`);
  SETTLE: wynik po 90 minutach, remis w DNB = zwrot (`DNB_DRAW_REFUND` w
  `void_legs`, 0 u. w 7c i rejestrze).
- **Krzywe NIE są zainstalowane** (potrzebna zgoda operatora). Do instalacji
  `install_new_market_curves.py` grupa musi trafić do jego `GROUPS` (dziś jej
  tam nie ma - plik edytuje inna sesja). Do tego czasu każda noga 1X2 / DNB
  czyta tylko własne linie Superbetu: `NO_LINE_EVIDENCE`, nic się nie
  drukuje. 1X2 nie ma krzywej i po instalacji też czyta tylko własne linie
  (do 50 linii / 15 meczów w kubełku).
- Po instalacji klasa `season_early` żyje w `by_class` pliku kalibracji;
  `fit_confidence` przy następnym refitcie jej nie odtworzy (jak
  `match_won_for`) - trzeba ją ponownie dołączyć.

## Zastrzeżenia

- Jeden krok walk-forward; holdout to 6 tygodni, w ~14% `early`.
- Selekcja „krzywa >= 0,70” liczona na wyborach wszystkich meczów historii,
  nie na liniach Superbetu (ceny w historii nieznane); marży i progu
  pewność x kurs >= 0,90 ten pomiar nie widzi.
- Faza na żywo: `SeasonPhaseIndex.phase` z historii przed dniem (SHEET), w
  pomiarze - przed meczem; mecz dnia, który nie ma poprzedniego sezonu w
  historii (puchar, nowe rozgrywki) nie ma fazy i czyta krzywą bez klasy.
- Nazwy Superbetu sprawdzone na `tests/sofa/golden/offer_mappable_items.json`
  (Villarreal - Napoli) i `runs/sofa/2026-10-1*/unmapped_prices`
  („Zakład bez remisu”, wybory = nazwy drużyn; 1 140 cen); połowy
  („1.połowa - zakład bez remisu”) zostają niezmapowane. Nie sprawdzono
  E2E na żywym OFFER (bez mostka / sieci w tej sesji).
