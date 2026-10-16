# Nowe rynki z istniejącego modelu: piłkarskie „lub” / handicap / DC & gole i tenisowe dopełnienia wyniku setów (2026-10-16)

Pytanie operatora (2026-10-16): ile rynków z `unmapped_markets` da się dodać
z obecnego modelu i krzywych, najmniejszym kosztem, bez długich procesów.
Odpowiedź: nie samo mapowanie nazw (kopie istniejących rynków dają tylko
1–3 % lepszą cenę w ~8 % par), tylko **nowe krzywe na wierszach, które
replaye już mają** – bez backfillu i bez replayu.

## Źródła (bez nowego replayu)

- piłka: `data/refit_new_markets_2026-10-16_cup/football_result_1x2_dnb/rows.csv.gz`
  – wiersze fitu 1X2/DNB z księgą z siłą lig w pucharach (`--cup-strength`):
  na mecz czyste centra goli ratingu `lh` / `la` as-of, gole po 90 min,
  kobiety, faza sezonu as-of; UNLINKED pominięte. 570 124 mecze
  (2024-10 .. 2026-10-14). p każdego zdarzenia = masa zdarzenia na siatce
  NB (r 7,586, `config/sofa_football_result.json`) – arytmetyka SHEET;
- tenis: `data/refit_new_markets_2026-10-15/tennis_sets/rows.csv` – udziały
  dokładnych wyników sąsiadów ratingu gospodarza, mecze do 3 setów, 50 183
  mecze; „nie <gracz> 0:2” = 1 − p „home 0:2” (gracz gospodarzem) i
  1 − p „home 2:0” (gracz gościem).
- skrypt: `scripts/sofa/fit_score_market_curves.py`; wynik
  `data/refit_new_markets_2026-10-17/{football_score_markets,tennis_set_complements}/`
  (`curves.json`, `gate_report.md`).

## Iteracja 1: historia, bramka jednostronna

Fit przed 2026-09-01, ocena na 09-01..10-13, krzywa końcowa przed 10-15;
klucz przechodzi, gdy przy krzywej >= 0,70 n >= 300 i realizacja − krzywa
>= −2 pp (`new_market_gate`), **plus** (dodane tutaj) żaden wycinek z
n >= 300 nie zawyża o więcej niż 2 pp.

Najpierw jedna krzywa na rynek (wszystkie podmioty i linie razem): luki
pulowane −0,2..−0,8 pp, ale wycinki rozjeżdżały się systematycznie:

| wycinek (holdout, krzywa pulowana) | n | luka pp |
|---|---|---|
| result_or_over 1 @ 4.5 / 5.5 | 6 006 / 4 121 | −3,5 / −3,2 |
| result_or_over X @ 4.5 | 975 | −7,5 |
| result_or_under X @ 2.5 | 1 523 | −9,1 |
| result_or_btts X | 5 931 | −5,6 |
| btts_or_over @ 5.5 | 5 663 | −4,4 |
| result_or_over 1 @ 0.5 | 17 260 | +1,1 |

(ogon goli NB przy wysokich „lub powyżej”, remis w „lub …”). Dlatego krzywa
jest **per wycinek** – `<market>@<podmiot>@<linia>|OVER`
(`confidence.curve_market`; wiersz zachowuje swój rynek, OFFER / SETTLE /
line evidence bez zmian). Drugie odkrycie: we wczesnej fazie sezonu wiele
wycinków zawyżało o 1–5 pp (jak 1X2 / DNB 10-15) – więc klasa
`season_early` (mężczyźni we wczesnej fazie, własne krzywe), krzywa bez
klasy na pozostałych meczach mężczyzn, `women` osobno.

Wynik (`football_score_markets/gate_report.md`): **133 krzywe przeszły**
(mężczyźni 50, season_early 40, kobiety 43), 49 nie (n < 300 albo
zawyżenie: `result_or_over` 1 @ 4.5 −2,5 pp, 1 @ 5.5 −3,4 pp,
`result_or_under` 1 @ 0.5 −2,5 pp, `women:result_or_under` 2 @ 0.5 −3,6 pp).
Tenis: `set_score_not|OVER` +2,49 pp [+1,57, +3,33] (n 5 080),
`tennis_women:` +1,13 pp [−0,17, +2,39] (n 3 605) – obie PASS.

Odrzucone w iteracji 1 (pomiar `iter1.py`, ta sama bramka): handicap
faworyta (−5,2 pp), wszystkie „&” (wynik & gole, wynik & BTTS, gole & BTTS –
zawyżają albo nigdy >= 0,70), DC & gole poza 12 & powyżej / 1X & poniżej,
parzystość i dokładne liczby goli, przedziały goli drużyny (nigdy >= 0,70);
przedział goli całkowity przeszedł, ale na cenach Superbetu 0 nóg
przechodzi bramki kuponu.

## Iteracja 2 / E2E: linie Superbetu przez prawdziwy pipeline

Poligon (scratch, kopie artefaktów, baza tylko do odczytu, zegar
zamrożony na 08:10Z dnia): OFFER dobudowany prawdziwym `OfferFetcher` z
zapisanych `unmapped_prices` dnia → SHEET → CONFIDENCE (zainstalowane
krzywe wycinków + line evidence) → COUPON_ASSEMBLY → PDF/HTML, wariant z
przełącznikami wyłączonymi i włączonymi na tym samym wejściu.

| dzień | SHEET off = on bez nowych | nowe wiersze | nogi off → on | utracone / zmienione | nowe nogi / mecze (nowe mecze) |
|---|---|---|---|---|---|
| 10-14 | tak (23 947) | 4 046 | 734 → 1 218 | 0 / 0 | 484 / 100 (23) |
| 10-15 | tak (52 987) | 4 590 | 1 259 → 1 795 | 0 / 0 | 536 / 135 (15) |
| 10-16 | tak (37 481) | 9 180 | 1 435 → 2 503 | 0 / 0 | 1 068 / 239 (25) |

(10-14: tenisowe dopełnienia nie, bo `TENNIS_SET_MARKETS` włączono tego
dnia o 14:50Z, po zegarze 08:10Z replayu.)

Rozliczone nowe nogi 10-14 + 10-15 (wynik po 90 min / sety z
`sofa_event_detail`, funkcjami SETTLE; bootstrap po meczach):

| rodzina | nogi | mecze | pewność | trafione | 1/kurs | realizacja − pewność pp [95 %] | ROI po cenie [95 %] |
|---|---|---|---|---|---|---|---|
| result_or_over / _under | 804 | 206 | 0,812 | 0,826 | 0,849 | +1,4 [−1,9, +4,6] | −2,6 % [−6,5, +1,2] |
| result_handicap | 118 | 102 | 0,827 | 0,822 | 0,830 | −0,5 [−7,8, +6,6] | −0,7 % [−9,8, +8,2] |
| pozostałe „lub” / DC & gole | 69 | 50 | 0,775 | 0,841 | 0,820 | +6,6 [−3,2, +14,7] | +2,8 % [−9,4, +12,9] |
| set_score_not | 27 | 27 | 0,801 | 0,704 | 0,847 | −9,8 [−27,0, +7,1] | −16,9 % [−37,4, +3,3] |
| **razem** | **1 018** | **233** | 0,811 | 0,823 | 0,845 | **+1,2 [−1,8, +4,2]** | **−2,4 % [−6,1, +1,2]** |

Wniosek: piłkarskie nogi są skalibrowane na liniach Superbetu (pewność nie
obiecuje za dużo) i realizują się mniej więcej po cenie – nowe opcje, nie
zmierzona przewaga. Tenis: dwa pomiary z tym samym znakiem (iteracja 2 na
krzywej pulowanej: 96 nóg −7,0 pp [−17,8, +2,9]; E2E 27 nóg −9,8 pp),
przedziały przez zero – obserwować (`T-SCORE-MARKETS-superbet`), line
evidence obniży klucz, gdy uzbiera 50 linii / 30 meczów.

## Ograniczenia (zmierzone lub nazwane)

- kilka linii jednego rynku w meczu (np. `result_or_under` 1 @ 3.5 / 4.5 /
  5.5) to jedno ryzyko (scenariusz meczu), a PDF nie grupuje ich jako „ta
  sama zmienna” – `leg_relations` modeluje przedziały jednej wielkości, te
  zdarzenia są dwuwymiarowe (jak DC / 1X2); widać je w sekcji ekspozycji;
- więcej nóg w pierwszych 30 meczach według wartości → więcej odczytów
  analityków (C3 w poligonie 10-15: 64 → 215 pozycji bez odczytu);
- `fit_line_evidence.py` nie stosuje `leg_class` (season_early) – tak samo
  jak dla 1X2 / DNB;
- tylko OVER każdego rungu jest wyceniany (UNDER to rodzina „&”).
- dopóki klucz nie ma własnych rozliczonych linii, line evidence obniża go
  pulowanym offsetem piłki (−1 pp) i limituje pulowanym pasmem ceny piłki
  (`cap:*@1.30-1.60`: ~0,69 przy p 0,83) – większość nóg powyżej kursu 1,30
  nie drukuje (E2E 10-15: 125 nóg z limitem); to istniejący bezpiecznik,
  liczby E2E już go zawierają.

## Przegląd końcowy (2026-10-16) – poprawki

- refit gubił krzywe dopasowane osobno (nowe rynki 10-15 i 10-17,
  `match_won_for`; dotąd ręczny `carry_over.py`) → `fit_meta.
  carry_separately_fitted_curves` w `fit_confidence`,
  `carry_sport_new_market_curves` w `fit_sport_confidence`, test na
  prawdziwych zainstalowanych plikach;
- przepis weryfikatora i scouta tworzył `OfferFetcher` bez nowych flag
  (jak 10-15: 160 „brakujących” nóg) → `offer.day_flags(date)` dla
  wszystkich czytelników + test, że obejmuje każdy parametr;
- PDF / HTML nazywał nogi `result_or_under (1) 5.5 OVER` → etykieta w
  słowach Superbetu (`display_market`);
- test całego etapu CONFIDENCE na zainstalowanych krzywych (wycinek z
  krzywą, wycinek odrzucony → NO_LINE_EVIDENCE, season_early, limit pasma)
  i `fit_line_evidence` (krzywa wycinka, klucz rynku);
- dokumenty: „Not modelled yet” (CLAUDE.md, sofa-pipeline) poprawione,
  odrzucone rynki dopisane do „Measured and declined”, tabela przełączników
  w skillu, verifier / analysis-core opisują nogi tylko-z-ratingu.

