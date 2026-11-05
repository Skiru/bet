# Refit krzywych rynków wyniku (piłka) - pomiar kandydata (2026-11-05)

Kontekst: audyt `docs/sofa/evidence/audyt_krzywych_refit_2026-11-05.md`, kandydat 3
(`dc_and_over` −7,2 pp, `draw_no_bet` UNDER −5,2 pp trafione minus pewność na liniach
Superbetu od 10-18). Nic nie zainstalowane; konfiguracja nietknięta.

## 1. Reguła zamrożona przed wynikami (zapisana przed pierwszym uruchomieniem)

**Co jest dopasowywane.** Dwa skrypty, tak jak krzywe zainstalowane 10-15 / 10-16:
`fit_result_1x2_dnb_curve.py` (wiersze 1X2 / DNB z replayu ratingu na sparsowanej
historii SHEET; krzywe `draw_no_bet|OVER/UNDER` z klasami) i na jego wierszach
`fit_score_market_curves.py --only football` (wszystkie wycinki
`<rynek>@<podmiot>@<linia>|OVER`, klasy: bez klasy, `women`, `season_early`).
Flagi replayu jak w zainstalowanym `fitted_from`: `--cup-strength` (config), `nb_r` z
`config/sofa_football_result.json`, `--from 2024-10-01`; do tego `--awarded-excluded`
(przełącznik AWARDED_EXCLUDED jest włączony). Wejście: kopia
`data/cache/football_history.pkl` z 11-05 06:57 (md5 94cec203…) w
`data/refit_2026-11-05_score/` - ani skrypt 1X2/DNB, ani skrypt rynków wyniku nie
otwiera bazy (czytają tylko tę sparsowaną kopię historii), więc `VACUUM INTO` bazy
nie jest potrzebne do dopasowania. Linie Superbetu do pomiaru (b) czytam z
`runs/sofa/<d>/07_settled.json` (bez bazy, jak `measure_refit_readiness.py drift`).
Tenisowe `set_score_not` nie jest częścią tego refitu (wymaga replayu tenisa z
kopii `tennis.db`, `fit_incident_set_curves.py`).

**Dwa kandydaty z jednego replayu:**
- `oos` (do pomiaru): `--before 2026-10-18`, bramka skryptu na `[2026-09-01, 2026-10-18)`.
  Poza próbą dla okna pomiaru 10-18..11-04, tak jak krzywa zainstalowana (przed 10-15).
- `install` (do ewentualnej instalacji): `--before 2026-11-05`, bramka na
  `[2026-09-18, 2026-11-05)`. Na oknie pomiaru jest w próbie - jego liczby z (b) są
  tylko informacyjne.

**(a) Historia, hold-out po dacie:** mecze historii `[2026-10-18, 2026-11-05)` (po
`--before` kandydata `oos` i po dacie dopasowania zainstalowanych). Każdy wiersz
(klucz z klasą) czytany przez krzywą zainstalowaną i przez `oos` tak, jak czyta je
CONFIDENCE (`Calibration.realised`, wartość `realised_lo95`, bez wiersza, gdy krzywej
brak). Na wierszach, które czytają obie: log-loss i Brier (różnica kandydat − zainstalowana,
95% bootstrap po meczach, 1000 powtórzeń), trafione − pewność w pasmach 0.60–0.70 i
>= 0.70 (pasmo wg własnej pewności każdej krzywej). **Gorzej** = dolna granica 95% różnicy
log-loss > 0.

**(b) Linie Superbetu 2026-10-18..2026-11-04:** każdy rozliczony (WIN / LOSS) wiersz
SHEET kluczy rynków wyniku i `draw_no_bet` z `07_settled.json`, klasa jak w CONFIDENCE
(`match_class`, potem `leg_class` dla `season_early`), czytany przez krzywą
zainstalowaną i `oos`; pewność = sama krzywa (offset i cap dowodu linii są dopasowane
na tych liniach - nie wchodzą). Na wycinek (klucz krzywej z klasą) i na rodzinę
(`dc_and_over|OVER`, `draw_no_bet|UNDER`, …): trafione − pewność przy >= 0.70 i
0.60–0.70, 95% bootstrap po meczach; do tego sparowana różnica Briera.

**Werdykt na wycinek (klucz z klasą):** „instaluj” tylko gdy jednocześnie
1. (a) nie jest gorzej (definicja wyżej), i
2. (b) przy >= 0.70 (n >= 100 linii u kandydata lub u zainstalowanej) |trafione − pewność|
   kandydata jest mniejsze niż zainstalowanej, i
3. w żadnym paśmie (>= 0.70, 0.60–0.70; n >= 100) kandydat nie obiecuje za dużo bardziej
   niż zainstalowana: górna granica CI kandydata < 0 przy górnej granicy zainstalowanej >= 0
   albo średnia luka kandydata niższa niż zainstalowanej - każde z nich = „nie”.
Wycinek bez linii (n < 100 w obu pasmach u obu) = „brak dowodu (b)”, zostaje
zainstalowana. Wycinek, którego kandydat nie przeszedł własnej bramki skryptu, = „nie”.

**Druk 10-18..11-04 (przybliżenie, nie pełny replay CONFIDENCE):** wiersze tych kluczy z
ostatniego `08_refusals.json` dnia, które padły tylko na progu pewności / x (albo
przeszły): nowa pewność = stara + (krzywa kandydata(p) − krzywa zainstalowana(p)), offset
i cap trzymane bez zmian (poranne przeliczenie dowodu linii częściowo zjadłoby różnicę);
liczę nogi, które zaczęłyby / przestałyby przechodzić 0.70 i x >= 0.90.

## 2. Co uruchomiono

- `fit_result_1x2_dnb_curve.py --history data/refit_2026-11-05_score/football_history.pkl --from 2024-10-01 --awarded-excluded --cup-strength --matches-cache data/refit_2026-11-05_score/matches.csv.gz`:
  `install/` (`--holdout-from 2026-09-18 --holdout-to 2026-11-05 --before 2026-11-05`; 2 411 106 selekcji, 1:56 min) i
  `oos/` (`--holdout-from 2026-09-01 --holdout-to 2026-10-18 --before 2026-10-18`, ten sam replay z cache).
- `fit_score_market_curves.py --only football --football-rows data/refit_2026-11-05_score/install/football_result_1x2_dnb/rows.csv.gz` z tymi samymi oknami do `install/` i `oos/`
  (`fitted_from.awarded_excluded: true` przejęte z wierszy).
- Pomiar: `data/refit_2026-11-05_score/measure.py` (tylko odczyt, bez sieci i bazy; wynik `m_oos/measure.json`, `m_install/measure.json`, werdykty `m_oos/verdicts.json`).
- Odstępstwo od zlecenia: **nie robiłem `VACUUM INTO` bazy** - oba skrypty czytają wyłącznie sparsowaną historię (pickle), skopiowaną do katalogu refitu; linie Superbetu pochodzą z `07_settled.json`. Baza nie była otwierana ani razu.

Bramka skryptów (jednostronna, −2 pp przy krzywej >= 0.70, n >= 300):
- wycinki rynków wyniku: `oos` 142 z 198 przechodzi (zainstalowane 133; żaden zainstalowany nie wypada), `install` 134 z 198 (wypadają 4 zainstalowane: `season_early:btts_or_over@-@4.5`, `season_early:dc_and_under@1X@5.5`, `season_early:result_or_clean_sheet@1@0.5`, `women:dc_and_over@12@2.5`);
- DNB: `oos` - **`draw_no_bet|UNDER` NIE przechodzi** (luka −2,41 pp na hold-out 09-01..10-18; ta sama surowa p bez krzywej: −0,30 pp [−1,61, +1,06], n 3 174), `install` - przechodzi. Nowe klucze, które przeszły, a nie są zainstalowane (`women:result_1x2|OVER`, `women:draw_no_bet|UNDER`, kilka wycinków), pominąłem: to nowe krzywe, nie refit.

## 3. Wyniki

### (a) Historia, mecze 2026-10-18..11-04 (7 839 meczów; krzywa zainstalowana vs `oos`)

137 wycinków czytanych przez obie krzywe: **gorzej** (dolna granica Δlog-loss > 0) w 5 (`dc_and_over@12@0.5`, `result_handicap@1@1.5`, `result_handicap@1@3.5`, `result_or_under@2@2.5`, `women:result_or_over@X@1.5`), lepiej (górna < 0) w 8, bez różnicy w 124. Różnice log-loss są rzędu 1e-4.

Na historii z tego samego okresu krzywe są skalibrowane tam, gdzie linie Superbetu dryfują:

| wycinek | n >= 0.70 | zainstalowana | kandydat `oos` | Δlog-loss [95%] |
|---|---:|---|---|---|
| `draw_no_bet|UNDER` | 531 | +0,4 [−3,2, +3,4] | bez zmian (kandydat odpadł na bramce) | 0 |
| `draw_no_bet|OVER` | 1 420 | +0,8 [−1,2, +2,6] | +0,5 [−1,4, +2,4] | +0,00002 [−0,00016, +0,00020] |
| `dc_and_over@12@1.5` | 1 533 | −2,2 [−4,2, −0,1] | −2,2 [−4,1, −0,1] | +0,00006 [−0,00004, +0,00015] |
| `dc_and_over@12@2.5` | 525 | +1,1 [−2,5, +4,5] | +1,2 [−2,4, +4,7] | +0,00006 [−0,00010, +0,00021] |

### (b) Linie Superbetu 2026-10-18..11-04 (trafione − pewność krzywej, pp [95% po meczach])

| wycinek | n >= 0.70 zainst. | kandydat `oos` | 0.60–0.70 zainst. | kandydat | ΔBrier x1e4 |
|---|---|---|---|---|---|
| `dc_and_over|OVER` (rodzina) | 447: −7,2 [−12,6, −2,5] | −7,2 [−12,5, −2,4] | 1 498: −3,1 [−5,7, −0,6] | −3,3 [−5,8, −0,8] | +0,21 [−0,58, +0,94] |
| `dc_and_over@12@1.5` | 366: −5,3 [−9,9, −0,9] | −5,3 [−9,9, −0,9] | 1 164: −2,6 [−5,4, +0,2] | −2,8 [−5,6, +0,0] | +0,09 [−0,48, +0,62] |
| `dc_and_over@12@2.5` | 81: −16,0 [−26,4, −5,2] | −15,8 [−26,2, −5,0] | 334: −4,9 [−10,3, +0,5] | −4,9 [−10,3, +0,4] | +0,33 [−0,75, +1,33] |
| `draw_no_bet|UNDER` | 355: −5,4 [−9,7, −1,1] | bez zmian (odpadł) | 466: −2,9 [−7,4, +1,2] | bez zmian | 0 |
| (`install`, w próbie) `draw_no_bet|UNDER` | | −5,8 [−10,1, −1,5] | | | |
| `draw_no_bet|OVER` | 1 130: −1,1 [−3,3, +1,3] | −1,3 [−3,5, +1,1] | 1 019: −0,6 [−3,7, +2,3] | −0,8 [−3,8, +2,2] | +1,34 [+0,61, +2,09] |
| wszystkie klucze rynków wyniku + DNB | 95 722: −0,5 [−0,8, −0,1] | 96 373: −0,5 [−0,8, −0,2] | 37 244: +0,4 [−0,1, +0,8] | +0,3 [−0,1, +0,8] | **+0,63 [+0,40, +0,87]** |

Odczyt: refit **nie rusza** dryfu `dc_and_over` (−7,2 → −7,2 pp) ani `draw_no_bet` UNDER (kandydat poza próbą nie przechodzi własnej bramki; wersja w próbie obiecuje jeszcze więcej, −5,8 pp). W sumie kandydat jest na liniach Superbetu **gorszy** w Brierze (+0,63e-4 [+0,40, +0,87]; log-loss +0,00014 [+0,00008, +0,00019]).

Skąd dryf (diagnoza, nie werdykt): dla tych samych meczów p SHEET-u na żywo ≈ p replayu (DNB średnio |Δ| 0,019, `dc_and_over` 0,011), wyniki zgodne w 100%. DNB UNDER p >= 0.70 na meczach z linią Superbetu: p 0,789, trafione 0,774 (na żywo) / 0,783 (replay), a krzywa podnosi taką p o ~+1,5 pp, bo w całej historii 2024-10..10-17 model w tym zakresie zaniżał. W całej historii 10-18..11-04 krzywa jest skalibrowana (+0,4 pp), w podzbiorze meczów, które Superbet wystawia, nie jest. To przesunięcie **populacji** (mix lig Superbetu) przy małym n (355 / 379 meczów), a nie przestarzała krzywa - refit na historii go nie zobaczy. Mechanizmem, który ten podzbiór czyta, jest dowód linii (offset, refit co rano; np. `dc_and_over@12@1.5` drukował 10-25 z `line_offset` −0,0559). 1 789 z 5 080 wierszy DNB z Superbetu nie ma w ogóle wiersza w replayu (nie zbadane - najpewniej mecze bez historii obu stron).

### Druk 10-18..11-04 (przybliżenie z sekcji 1)

Cały kandydat `oos`: z 35 185 wydrukowanych nóg tych kluczy przestałoby przechodzić 315 (głównie `result_or_under@X@4.5` 104, `@X@3.5` 61), zaczęłoby 142 z 37 762 odrzuconych na progu (głównie `result_or_under@1@2.5` 31). Tylko 13 wycinków „instaluj” (niżej): −44 / +1 nóg. Nogi odrzucone KICKED_OFF w ostatnim przebiegu nie mają pewności i nie są widoczne.

## 4. Werdykt (reguła z sekcji 1)

| werdykt | wycinków |
|---|---:|
| instaluj | 13 |
| nie (b) - nie bliżej zera albo obiecuje więcej | 52 |
| nie (a) - gorzej na historii | 5 |
| nie - kandydat odpadł na bramce | 58 |
| brak dowodu (b) - zostaje zainstalowana | 76 |

13 „instaluj”: `dc_and_under@1X@5.5`, `result_handicap@1@2.5`, `result_handicap@2@3.5`, `result_or_over@X@2.5`, `result_or_under@1@4.5`, `@1@5.5`, `@2@4.5`, `@2@5.5`, `@X@5.5`, `women:btts_or_over@-@2.5`, `women:result_or_over@1@0.5`, `@2@0.5`, `@2@1.5`. Każdy przesuwa lukę przy >= 0.70 o 0,04–0,25 pp - daleko w szumie (CI ±1–5 pp). Żaden z nich nie jest wycinkiem dryfującym. `dc_and_over` (wszystkie wycinki) i `draw_no_bet` UNDER: **nie**.

**Rekomendacja: nic nie instalować.** Reguła formalnie przepuszcza 13 wycinków, ale zysk jest pomijalny, a kandydat jako całość jest na liniach gorszy. Dryfu z audytu refit krzywej nie naprawi; zostaje dowodowi linii. Jeśli operator mimo to chce 13 wycinków: przygotowany katalog `data/refit_2026-11-05_score/staged/football_score_markets/curves.json` (krzywe wersji `install`, wszystkie 13 przeszły też jej bramkę; `replace_markets` 13 wycinków, a pozostałe klasy tych wycinków niosą zainstalowane krzywe bez zmian - 26 kluczy przeniesionych, choć `new_market_curves_fitted_from` przypisze je temu dopasowaniu). Dry-run przeszedł:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/install_new_market_curves.py --dir data/refit_2026-11-05_score/staged --confirm --backup-dir config/backup_2026-11-05_score_markets
```

Zmienia tylko `config/sofa_confidence_calibration.json` (brak `.next.json`); kopia w `config/backup_2026-11-05_score_markets/`, potem `tests/sofa`, przy porażce przywrócenie. Instalacja jest bez daty: tylko za zgodą operatora i przed CONFIDENCE następnego dnia, nigdy w dzień zbudowany.

## Czego nie sprawdzono

- Tenisowego `set_score_not` (wymaga replayu tenisa z kopii bazy).
- Pełnego replayu CONFIDENCE (offset dowodu linii przeliczony na nowej krzywej) - druk liczony w przybliżeniu pierwszego rzędu.
- Dlaczego 35% wierszy DNB z Superbetu nie ma wiersza w replayu historii.
- Kodu nie zmieniałem; bramki (pytest / ruff / mypy) nie były potrzebne i nie były uruchamiane.
