# Raport nocy 2026-10-12 → 10-13

Plan: `docs/sofa/history/PLAN_NOC_2026-10-12.md` (v3, dwie recenzje adwersaryjne).
Mandat operatora (~20:40Z): „jeżeli zmiany są lepsze – automatycznie przełączaj;
wszystko z obliczeń, testów, poprawek i weryfikacji”. Mostek podniesiony 20:20Z
(5 okien, 115–206 ms), działał całą noc bez odmowy.

## Najpierw wynik

| co | stan |
|---|---|
| kupon epoki od 10-09 (po nocnym rozliczeniu) | **−4,3% [−6,2; −2,6]**, 5 647 rozliczonych (było 5 607); MISMATCH 0 |
| CLV epoki | −3,95% [−4,07; −3,83], 3 780 nóg / 751 meczów – **przewagi nad ceną nie ma** |
| kalibracja całości | +1,0 pp [−0,4; +2,5] PASS; piłka i hokej PASS; koszykówka +16,5 pp [+3,1; +30,8] |
| przełączniki włączone tej nocy | **żaden** – jedyny kandydat (strażnik kubełkowy sportów) zmierzony gorzej; reszta to poprawki poprawności |
| instalacje krzywych / stałych | **żadna** (`config/*.json` sha256 = stan z 20:42Z, poza zacommitowanym porannym line evidence) |
| bramki na `HEAD` | pytest 4 036+ / ruff / mypy --strict / rejestr testów – zielone |

## Co zrobiono (commity na `main`)

| commit | co | dowód |
|---|---|---|
| `0ee9f064` | line evidence 10-12 w git (pliki 10-09..10-11 nigdy nie były – historia offsetów istnieje tylko w nogach) | – |
| `cafe0d67`, `c75a7015` | **Historia hokeja / koszykówki / siatkówki znów się uzupełnia.** SPORT_IDENTITY pyta o listingi przed meczem, więc od 10-05 wyniki nie wchodziły do historii (10-07..10-11: 0–30% rozliczonych meczów; 10-11: 16 z 377). `refresh_sport_history.py` (most) pyta `/event/{id}` o mecze, które powinny się skończyć; krok 0 porannego `refresh_line_evidence.py`; `day_status` `sport_history` WARN < 80% | na żywo: 1 514 zapytań, 1 407 zakończonych dopisanych; 10-11 teraz 374/377 (99%) |
| `54051b8b` | SETTLE: mecz **odwołany** = zwrot; **przełożony > 48 h** = zwrot (`POSTPONED_BEYOND_VOID`); mecz 90' + karne bez dogrywki (kod 120 bez `extra1/2`) oceniany z całego meczu | sweep 10-05..10-11 na żywo: 21 wartości, 2 odwrócone wyniki; 15 + 10 nóg zwrotów, 6 nóg rożnych EFL Trophy ocenionych; 8 odwołanych sprawdzonych ręcznie – żaden nie rozegrany pod innym id |
| `80b0473f` | odczyty nóg sportów nie są już `UNMATCHED_READ` (diagnostyka) | – |
| `791ab1e3`, `7f76a7e6` | FIXTURE_CHECK: jeden 504 mostka nie przerywa całości (10-12: 4 wydruki z 279–282 meczami UNVERIFIED); jedna ponowna próba po 5 s, potem tylko ten mecz UNVERIFIED; 403 / bezpiecznik dalej zatrzymują | testy z fałszywym transportem |
| `c022a255` | SPORT_IDENTITY nie pyta po starcie – zostaje rekord sprzed startu (`frozen_at_start`) | 3–56 rekordów dziennie było nadpisywanych |
| `1a918092` | CS2: kotwica na rozpoznanym id drużyny (jak w pozostałych sportach) | replay 10-06..10-12: +6 serii, 0 błędnych id (rozliczenia + złoty zbiór, nowy zbiór 15 przypadków) |
| `c6f43c13` | siatkówka: nazwy bez afiksów klubowych (vôlei, clube, EC…) | +5 meczów (4 z id = id rozliczenia), 0 błędnych |
| `8790c457`, `ba7a0e85` | rynki MAPPABLE (drużyna strzeli gola, BTTS w połowie, 3. set rozegrany, handicap gemów w secie, …) za `MAPPABLE_FAMILIES_FROM_UTC` = **`None`** | przy wyłączonym `04_offer.json` identyczny bajt w bajt (golden z 40b42923); 20 nowych szczebli/dzień czytałoby istniejące krzywe – **nie włączone**: brak replayu E2E z włączonym (wymaga SAMPLES przez most) |
| `08d8af7d` | inwentarz niezmapowanych rynków sportów mierzonych (raport) | 10-13: 745 nazw, 0 UNCLASSIFIED |
| `e3603634`, `82c9b78c`, `5d5c570f` | krok pętli: limit 6 h (≥ 3× najdłuższy krok 119,7 min), zabija grupę procesów, `STEP_FAILED TIMEOUT`; `run_boosts` – błąd jednego meczu pomijany; `day_status` `identity` | czasy kroków z 29 logów pętli 09-28..10-12 |
| `7d39b78f` | `measure_sport_guard.py`, `measure_sport_history_ab.py` (dowody, tylko odczyt) | – |

## Pomiary (tylko odczyt)

**Historia sportów – A/B** (`measure_sport_history_ab.py`, linie Superbetu 10-05..10-11, model as-of
z historii sprzed naprawy vs po): log-loss bez mierzalnej zmiany – hokej −0,45e-3 [−1,86; +0,98],
koszykówka +1,11e-3 [−1,63; +3,83], siatkówka +0,1e-3 [−3,0; +3,4]. Tydzień to ~500 meczów na tle
29–51 tys. **Zawyżenie koszykówki nie bierze się z nieświeżej historii.** Zysk naprawy: pokrycie
dowodu z linii (siatkówka 5 318 → 8 474 rozliczonych linii) i poprawność danych.

**Koszykówka – skąd +16,5 pp.** Znak i strona handicapu poprawne (złota noga Centrum Tigers T1 +9,5
@ 1,83, 92:123 – LOSS słusznie). Krzywa historii nie przenosi się na linie Superbetu: przed offsetem
0,762 vs realizacja 0,615, **−14,6 pp [−19,6; −9,6]** na 1 710 liniach / 353 meczach; powyżej p 0,7
model nie różnicuje (0,7–0,8: 0,706; 0,8–0,9: 0,701). Hokej skalibrowany (−0,1 pp). Siatkówka −13 pp.

**Strażnik kubełkowy sportów – odrzucony** (`measure_sport_guard.py`, walk-forward 10-07..10-11,
dowód dopasowany na dniach wcześniejszych; 1 885 nóg / 536 meczów): obecnie −2,2 pp [−4,6; +0,2],
ROI −5,4%; cap punktowy zdejmuje 135 nóg, które **nie** wypadły gorzej (ROI −4,7%); cap Wilsona
zdejmuje 8 – wszystkie wygrane. Wpisane do „Measured and declined”. To pytanie o krzywą (następny refit).

**Piłka – krzywe FAIL** (hold-out replayu z kopii 10-08): `goals_total` zdrowe (+0,4 / −0,8 pp na
hold-oucie); `corners_total OVER` zaniżona (−1,7 hold-out, −4,3 wszystkie wiersze, −6,9 druk) – traci
nogi, nie obiecuje za dużo; line evidence tylko obniża, więc poprawka = centrum rożnych w reficie.

**Tenis** (+3,3 pp): luka siedzi w nogach z flagą `price_gap` (+18,6 pp [+5,8; +30,1] na 52);
reszta +0,4 pp. Per-set `games_won_set1/2_for OVER` zawyżone na nowym estymatorze (+9,9 / +12,2 pp).

**Offsety line evidence** odtworzone dzień po dniu 10-09..10-12: zgodne z nogami (≤ 0,5 pp), rodziny
przecenione ruszają się ≤ 1,3 pp/dzień. `games_won_for OVER` tenisa (−8,5 / −12,1) zmierzone na
wierszach starego estymatora, nowy jest tam skalibrowany (−0,2 pp, n 117) – **przeobniżone**;
kandydat (dowód na wierszach ≥ 10-09), za mało dni na walk-forward.

**Propsy piłkarzy (10-12: 0 nóg)** – replay CONFIDENCE: blokuje krzywa OVER (BELOW_CONFIDENCE_FLOOR
1 995, NO_PRICE 2 117 na UNDER), **nie** n < 10 (THIN_SAMPLE: 2). Backfill składów niezasadny.

**Hokej handicap p ≥ 0,95** – podejrzenie puste: żadna noga nie miała p ≥ 0,95.

**Identyfikacja na żywo 10-06..10-12**: hokej 73–97%, koszykówka 70–96%, siatkówka 3–56%, CS2 52–100%
(bez pętli 1×1). 10-12: 27 odmów CS2 to „Winners series 1x1” (słuszne), 7 showmatchów.

**Rejestr testów**: `T-F54` (kryterium porażki: górna granica CLV < 0) spełnione liczbowo w obu
oknach (10-06..08: −5,16% [−5,44; −4,89]; 10-09..11: −3,95% [−4,07; −3,83]); test jest PROPOSED –
**decyzja operatora**. `T-PRICE-GAP-flag` 0/500 (start 10-13). `T-PEER-CHOICE-edge`: 1 778/3 000 par,
trafność 49,9% [45,9; 53,7].

**C2 – rynki wyniku w piłce** (`measure_football_result_model.py`, walk-forward, test 2026-06-09..10-06,
80 425 meczów; model `nb_rating`: rating w centrum, NB r ≈ 7): log-loss względem stopy bazowej ligi –
DNB −0,0792 [−0,0818; −0,0764] (skill 11,7%, ~19% wyborów ≥ 0,70), podwójna szansa −0,0376 (6,2%,
>50% ≥ 0,70), 1X2 −0,0658 (6,4%, 3–5%). **BTTS gorzej niż baza** (+0,0064), parzystość i dokładny
wynik – nic nie osiąga 0,70, HT/FT – 0,3% do druku. Krzywa z historii przeszacowuje w oknie testowym
o 2,4–4 pp (sierpień–wrzesień: początek sezonu) – przed drukiem potrzebna krzywa znająca fazę
sezonu; UNLINKED zostaje odrzucone (1/7 umiejętności, −6..−8 pp). Centrum SHEET (mieszanka 0,5
z próbką) jest dla wyników **niedopewne** (+15–18 pp przy p 0,6–0,8) – użyć czystego ratingu.

**C3 – rynki wyniku w tenisie** (`measure_tennis_outcome_model.py`, 31 753 mecze 06-09..10-07,
rating as-of SHEET): zwycięzca meczu −0,1232 [−0,1277; −0,1189] względem bazy, skalibrowany
w ±1,3 pp, **45,7% meczów ≥ 0,70** (0,812 vs 0,818 zrealizowane); zwycięzca 1. seta −0,0895;
dokładny wynik w setach −0,1404 (3% wyników ≥ 0,70); decydujący set mały (TOUR mężczyźni – zero).
Kolejność do refitu: zwycięzca meczu, 1. set, wynik w setach. Otwarte: reguła Superbetu przy
kreczu, super-tiebreak jako set, ~20% meczów bez ratingu.

## Weryfikacja

- **E2E**: dzień 10-12 skopiowany do scratch, CONFIDENCE → SPORT_CONFIDENCE → kupon → PDF/HTML na
  zamrożonym zegarze 13:16Z, kodem po nocy. Piłka 556, tenis 131, CS2 1 – **identyczne** z produkcją;
  hokej / koszykówka: 2 nogi więcej, 1 zamieniona, 9 zmian pewności – wyłącznie inne `forecast_p`
  (model widzi świeże wyniki). md5 prawdziwych plików `runs/sofa/2026-10-12/` przed i po: identyczne.
- **Przegląd adwersaryjny** wszystkich commitów nocy: 0 blokerów; 2 MAJOR (historia pytała o dzisiejsze
  mecze przed startem; `--dry-run` porannego skryptu używał mostka) – **naprawione** w `c75a7015`
  z testami; drobne: 404 nie jest PARTIAL, skan z filtrem sportu.
- **Nie przetestowane**: limit 6 h kroku pętli przy uśpieniu Maca (zegar monotoniczny – niezmierzone);
  FIXTURE_CHECK z ponowieniem na żywym moście; mapowania C1 z włączonym przełącznikiem (wymaga SAMPLES).

## Decyzje dla operatora

0. **Następny refit (zgoda na refit)**: krzywe dla tenisa – zwycięzca meczu / 1. set / wynik w setach;
   piłka – DNB, podwójna szansa, 1X2 z krzywą fazy sezonu (C2/C3 wyżej).

1. **`T-F54`**: kryterium porażki spełnione – zatwierdzić werdykt „brak przewagi nad ceną”?
2. **`MAPPABLE_FAMILIES_FROM_UTC`**: włączyć po replayu E2E z SAMPLES (dzień z mostem)?
3. **Koszykówka**: krzywa zawyża na liniach Superbetu −14,6 pp przed offsetem – refit krzywych sportów
   z oceną na liniach Superbetu przy następnym refitcie (zgoda na refit).
4. **Zwroty**: „abandoned” i „notstarted > 48 h” celowo **nie** są zwrotem w piłce/tenisie (sporty
   mierzone je zwracają) – potwierdzić regułę Superbetu.

## Kopie i pliki

- `data/refit_2026-10-08/sofa_replay.db` – źródło zainstalowanych krzywych, **zostaje** (dopisane do CLAUDE.md).
- `data/refit_2026-10-12/sofa_replay.db` (45 GB, migawka 20:39Z = historia sprzed naprawy) – baza A/B;
  do skasowania, gdy niepotrzebna (decyzja operatora, dysk 66 GB wolne).
- Wyniki: `data/refit_2026-10-12/{measure,ops,guard,fresh_rows,e2e,c2,c3}/`.
- Worktree agentów w `.claude/worktrees/` – ich commity są na `main` (cherry-pick).

## Do rana (checklista)

1. `ensure_bridge.py`, potem rozliczenie D-1 jak zwykle.
2. `refresh_line_evidence.py --before 2026-10-13` – teraz najpierw odświeża historię sportów.
3. `day_status.py --date 2026-10-13`: `sport_history` i `identity` muszą być OK.
4. `resettle_sweep` – przełożone mecze 10-11 (Abha, Panama ×2) zamienią się w zwrot po 48 h.
