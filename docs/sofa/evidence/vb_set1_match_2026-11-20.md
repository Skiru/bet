# Siatkówka „1.Set/Mecz” (Superbet 230059) - wdrożenie i pomiar, 2026-11-20

Plan: `docs/sofa/history/PLAN_NOWE_RYNKI_2026-11-20.md`, sekcja 5 (rynek D).
Decyzja operatora 2026-11-20: „wykonaj go w całości, zweryfikuj, otestuj”.
Przełącznik `epochs.VB_SET1_MATCH_FROM_UTC` = **2026-11-22 00:00Z** (według dnia
i zegara budowy, wymaga `VB_POINT_MODEL`); grupa księgi **„od 11-22”**.

## Wniosek

- Krzywa z historii przechodzi regułę planu: na odłożonej próbie
  2026-09-29..11-20 klucz `set1_match` SAME przy pewności >= 0,70 realizuje
  **+0,41 pp [-1,33; +2,17]** względem pewności (1 877 meczów; reguła: >= -3 pp).
- To pomiar kalibracji, nie przewagi nad ceną. Cenę porównał pomiar planu
  (`docs/sofa/evidence/nowe_rynki_2026-11-20.md`, sekcja 2: kursy z
  `unmapped_prices` przeciw wynikom z historii, 286 meczów): Brier model -
  cena bez marży +0,0043 [-0,0006; +0,0093] (cena nie gorsza), ROI nóg przez
  bramki +7,6% [-5,3; +20,0] przed podatkiem, -5,3% po 12%; plus to ogólny
  efekt faworyta. Żadna linia 230059 nie była rozliczona przez SHADOW_SETTLE
  (kursy leżały tylko w `unmapped_prices`), więc dowodów z linii jeszcze nie
  ma.
- Dwa najwyższe kubełki (0,925-0,95 i >= 0,95, po ~120 wierszy) przeszacowują
  o 4,0 i 4,6 pp - górny koniec do obserwacji w
  `T-VB-SET1-MATCH-calibration`.

## Co zrobiono (różnice wobec planu)

| plan | wykonanie | dlaczego |
|---|---|---|
| `shadow.MARKETS["volleyball"][230059]` | osobna tabela `shadow.SET_MATCH_MARKETS`, czytana tylko z flagą `set1_match` w `parse_line` / `parse_event` / `reads_market`; dopisana do `spec_of`, `leg_relations._shadow_spec`, `mapped_sport_markets`, `market_coverage` | wpis w `MARKETS` czytałby rynek przy wyłączonym przełączniku (brak bajt w bajt) i zmieniałby `market_coverage._reader_reads` (weryfikacja planu D-F1) |
| `EXTENDED_MARKETS["volleyball"][230059]` | `sport_confidence.VB_SET1_MATCH_ALLOWED` za flagą w `allowed_markets` / `family_of` / `_allowed` / `settled_shadow_rows` | klucz `EXTENDED_MARKETS` byłby rodziną „tylko z rozliczeń”, którą `fit_sport_confidence` dopasowałby z naszych dni na p modelu wyniku (łamie „krzywe tylko z historii”) |
| skrypt oceny testu nie nazwany | `fit_vb_set1_match_curves.py --forward --to <d>` | rejestr wymaga istniejącego skryptu |
| „wystarczy flaga w verify_legs przez parse_event” | flaga w `scf.family_of` weryfikatora i w `audit_variants.snapshot_family` (U3) | weryfikator nie parsuje ładunku sportów; bez flagi każda noga byłaby defektem (D-F2) |

Poprawka poprawności (bez przełącznika, bo dotąd nieosiągalna): `cs2.grade_side`
i `volleyball_point_model.win_loss` mają gałąź „wskaźnik” dla stron łącznych.
Przed nią „T1/T1” spadałoby do gałęzi handicapu: wygrana = LOSS, przegrana =
VOID (test obu przypadków).

## Krzywe (historia Sofascore, kopia bazy)

Kopia: `data/refit_2026-11-22_vb/sofa.db` (`VACUUM INTO`, 2026-11-20
18:53-19:04Z). Skrypt: `scripts/sofa/fit_vb_set1_match_curves.py`
(`SOFA_DB_PATH` = kopia, 2 procesy, `nice`). Model wymian ze stałymi
`vb_point_pricer.PARAMS`, krokowo po historii (prognoza przed meczem, mecz
uczy dopiero po niej), 4 000 symulacji z ziarnem = id meczu, cztery strony
każdego meczu do pięciu setów (gospodarz = team1), rozliczone jak w
SHADOW_SETTLE.

- Historia 101 966 meczów; krokowo 33 860 meczów w oknie 2025-10-01..2026-11-20.
- Dopasowanie 2025-10-01..2026-09-28: 27 908 meczów, 111 632 wiersze,
  `sport_confidence.fit_curves`, MIN_BUCKET 200.
- SPLIT ma jeden kubełek < 0,60 (realizacja 0,104) - nigdy się nie drukuje.

Odłożona próba 2026-09-29..11-20 (5 952 mecze, 23 808 wierszy, oceniona raz):

| klucz | wiersze | pewność | realizacja | realizacja - pewność |
|---|---|---|---|---|
| SAME, wszystkie | 11 904 | 0,385 | 0,394 | +0,91 pp [+0,36; +1,48] |
| SAME, >= 0,70 | 1 877 | 0,801 | 0,805 | **+0,41 pp [-1,33; +2,17]** |
| SPLIT, wszystkie | 11 904 | 0,102 | 0,106 | +0,43 pp [-0,10; +0,97] |

Kubełki SAME >= 0,70 (pewność / realizacja / n): 0,70-0,75 0,721 / 0,724 / 438;
0,75-0,80 0,770 / 0,779 / 452; 0,80-0,825 0,787 / 0,813 / 182; 0,825-0,85
0,818 / 0,806 / 160; 0,85-0,875 0,814 / 0,840 / 156; 0,875-0,90 0,852 / 0,861 /
137; 0,90-0,925 0,884 / 0,928 / 111; **0,925-0,95 0,901 / 0,861 / 115; >= 0,95
0,951 / 0,905 / 126**.

Wynik i krzywe: `config/sofa_vb_set1_match_curves.json` (pole
`vb_set1_match_curves.holdout`), wiersze `data/refit_2026-11-22_vb/fit/`.

## E2E na kopii

E2E_EVIDENCE

## Testy z góry

- `T-VB-SET1-MATCH-calibration` (zarejestrowany 2026-11-20, okno od 11-22):
  SAME >= 0,70, ±3 pp, >= 300 linii / >= 40 meczów.
- `T-PRICE-EDGE-VB-RAW-FORWARD`: zamrożony `measure_price_edge.py` (strażnik
  sha) bierze każdy drukowany singiel siatkówki, więc policzy też nogi
  `set1_match`. Skrypt nie zmieniony; zastrzeżenie w rejestrze: każdy raport
  podaje werdykt na populacji skryptu i bez nóg `set1_match` /
  `vb_set1_match_rule`, a zarejestrowana populacja to ta bez nich.
- Populacja rośnie też w T-SPORT-LATE-WINDOW, T-A4-bucket-deff,
  T-LESSER-LOSS-flag (marża ~13,8% > 8,6% - te nogi nigdy nie są
  oznaczone), T-TOP-BAND-090-after-price-gap-offset, T-KUPON-PRICE-RISE-DROP,
  T-STABILITY-LABEL-FORWARD: zastrzeżenie w rejestrze, definicja bez zmian,
  raport podaje też wynik bez tych nóg.

Testy: `tests/sofa/test_vb_set1_match.py`.
