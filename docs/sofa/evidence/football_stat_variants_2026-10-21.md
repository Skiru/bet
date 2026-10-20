# Warianty statystyk piłkarskich (klasa A) i rozkłady liczników (klasa B) – 2026-10-21

Noc 2026-10-20/21, pakiet „football stat variants”. Przełącznik
`epochs.FOOTBALL_STAT_VARIANTS_FROM_UTC` – **wyłączony (`None`)**; datę ustala
sesja główna. Źródło nazw: `runs/sofa/2026-10-14..10-20/unmapped_prices/`
(inwentarz nieczytanych rynków piłkarskich, klasy A/B/C/D).

## Klasa A – zmapowane (tylko mapper, metryka już modelowana)

`market_mapper.classify_stat_variant` (mecz piłkarski, po wszystkich innych
klasyfikatorach OFFER):

| nazwa Superbetu | wybór / sbv | rynek | próbka strony |
|---|---|---|---|
| Każda drużyna powyżej X rzutów z autu | „Powyżej 13.5 - Tak” / „13.5” | `both_over_throw_ins` | `throw_ins_for` |
| Każda drużyna powyżej X wybić od bramki | „Powyżej 4.5 - Tak” / „4.5” | `both_over_goal_kicks` | `goal_kicks_for` |
| Każda z drużyn powyżej X odbiorów | „Powyżej 12.5 - tak” / „12.5” | `both_over_tackles` | `tackles_for` |
| Strzały - Handicap | „LASK Linz (8.5)” | `handicap_shots` | `shots_for` |
| 1. połowa - liczba strzałów - handicap | „Liverpool (-3.5)” | `handicap_shots_1h` | `shots_1h_for` |
| 2. połowa - liczba strzałów - handicap | „LASK Linz (3.5)” | `handicap_shots_2h` | `shots_2h_for` |

Linia both-over z `specialBetValue`, sprawdzona z liczbą w wyborze (niezgodność
= odmowa); linia handicapu z nawiasu wyboru (sbv to linia gospodarza pary),
klub musi być stroną listingu. Wycena SHEET: istniejący łączny rozkład stron
(`bet.sofa.derived.price_derived_rungs`), korelacja stron z
`config/sofa_side_correlations.json` (shots −0,093; throw_ins / goal_kicks /
tackles / shots_1h / shots_2h niezmierzone → 0, jak dla already-live
`both_over_saves`). SETTLE: `_settle_derived` (minimum stron ≥ floor(linia)+1;
przewaga strony > −linia; statystyki regulaminowe; trafienie całkowitej linii =
„PUSH”). Nogi niosą nazwy Superbetu (`superbet_names.STAT_VARIANT_*`).

**Już czytane – nic do zrobienia:** obie drużyny > X obron bramkarza (mecz /
1. połowa), „1./2. połowa - rzuty rożne - handicap”, „Liczba czerwonych kartek”
0,5/1,5 – wszystkie rekordy w `unmapped_prices` z 2026-10-14 przed włączeniem
`MAPPABLE_FAMILIES` / `FOOTBALL_INCIDENT_MARKETS` (12Z–14Z), od 10-15 zero.
Inne linie czerwonych kartek niż 0,5/1,5 w 10-14..10-20: brak.

## Klasa B – zmierzone i odrzucone (nigdy >= 0,70 albo kopia czytanego szczebla)

`scripts/sofa/measure_stat_variant_distributions.py --from 2026-10-14 --to
2026-10-20 --history-from 2026-10-09`. p z rozkładu predykcyjnego SHEET:
NB wokół `centre` wiersza z dopasowaną dyspersją (`var = mu + alpha mu^2`,
`engine.nb_survival`). Rekonstrukcja sprawdzona na 4 950 centrach: maks. |p −
p_central| = 5,7e-5. Ponieważ alpha > 0, rozkład jest zawsze szerszy niż
Poisson – pasmo o stałej szerokości nie może być bardziej prawdopodobne niż
w Poissonie.

Historia (każdy mecz z centrum, 10-09..10-20):

| licznik | mecze | centrum min / mediana | maks. parzystość | maks. pasmo wewn. | maks. pojedyncza wartość | >= 0,70 |
|---|---|---|---|---|---|---|
| corners_total (pasmo 3) | 1 739 | 7,41 / 9,60 | 0,500 | 0,401 | 0,139 | 0 |
| corners_1h_total (pasmo 2) | 835 | 3,42 / 4,59 | 0,501 | 0,402 | 0,211 | 0 |
| corners_for (pasmo 2) | 1 689 | 1,93 / 4,86 | 0,521 | 0,520 | 0,277 | 0 |
| cards_points_total (wartość) | 687 | 2,61 / 4,39 | 0,508 | 0,230 | 0,230 | 0 |

Kwotowane przez Superbet (10-14..10-20, ostatnia aktywna cena dnia):

| rodzina | wybory (zdarzenia) | maks. p | p >= 0,70 |
|---|---|---|---|
| Nieparzysta/parzysta liczba rzutów rożnych | 930 (465) | 0,500 | 0 |
| 1.połowa - nieparzysta/parzysta | 682 (341) | 0,501 | 0 |
| Liczba rzutów rożnych - przedziały: 9-11 | 450 | 0,344 | 0 |
| 1.połowa - przedział: 5-6 | 378 | 0,310 | 0 |
| <drużyna> - przedział: 3-4 / 5-6 | 1 332 | 0,358 | 0 |
| Dokładna liczba kartek: 4..11 | 1 208 | 0,192 | 0 |

Pasma skrajne („<9”, „12+”, „0-2”, „7+”, „<5”, „0-3”, „12+”) to dokładnie
szczebel O/U (UNDER 8,5, OVER 11,5, ...). Na tym samym meczu szczebel O/U był
kwotowany w 2 988 z 3 290 takich wyborów (kartki „12+”: 0 / 151, p maks.
0,077); cena pasma = cena O/U w 2 941, lepsza w 30 (mediana różnicy 0,0 %).
Gdzie szczebla O/U nie było (302),
żaden wybór nie miał p >= 0,70. Siedem wyborów z p >= 0,70 (corners_for „7+”
4, 1. połowa „<5” 3) to kopie kwotowanych szczebli – ta sama noga, nic nowego.
Wniosek: parzystość, przedziały i dokładna liczba kartek **nie są budowane**
(jak parzystość / dokładne gole 10-16, model-state (d)); połowy kartek pominięte
(osobny pakiet).

## E2E (offline, kopie, baza `mode=ro`)

`scripts/sofa/measure_stat_variants_e2e.py --days 2026-10-18 2026-10-19
2026-10-20 --grade-days 2026-10-14 .. 2026-10-19`; scratch:
`/private/tmp/claude-501/-Users-mkoziol-projects-bet/903bccad-c2ff-46fb-9191-12f8ef2c9866/scratchpad/fsv/e2e/`.

- OFFER: zapisane nieczytane kursy (ostatni run OFFER, który widział mecz)
  przez prawdziwy `OfferFetcher` z nazwami listingu z `01_board.json`.
  Przełącznik wyłączony: **0 nowych szczebli każdego dnia**. Włączony:

| dzień | mecze | nowe szczeble | wiersze SHEET (wyceniona strona) | p >= 0,70 i p x kurs >= 0,90 |
|---|---|---|---|---|
| 10-14 | 10 | 167 | 130 | 22 |
| 10-15 | 36 | 444 | 355 | 65 |
| 10-16 | 1 | 2 | 2 | 0 |
| 10-17 | 17 | 131 | 120 | 10 |
| 10-18 | 4 | 57 | 57 | 8 |
| 10-19 | 2 | 4 | 4 | 0 |
| 10-20 | 10 | 141 | 116 | 27 |

  (Każdy both-over to tylko „Tak” – wiersz UNDER powstaje jako NO_PRICE.)
  162 szczebli bez wiersza: handicap, którego klubu `derived.resolve_subject`
  nie przypisze (token_sort_ratio < 70, np. „LASK Linz” / „LASK”) – istniejąca
  reguła wszystkich handicapów pochodnych, nie zmieniana.
- SAMPLES: próbki stron były w `03_samples.json` prawie zawsze (Superbet
  kwotuje te rynki tam, gdzie kwotuje rynki drużyn); brakujące (4 mecze)
  odbudowane z `/statistics` tych samych meczów co próbka `corners_for`;
  odbudowa porównana z próbkami dnia: 5 838 / 5 838 wartości równe.
- SHEET: replay `price_derived_rungs` z argumentami SHEET odtwarza zapisane
  wiersze pochodne (bazy bez centrów marginalnych): pola modelu równe 10-17
  583/583, 10-18 172/172, 10-19 57/57, 10-20 370/370 (różnice tylko
  `market_p` / `p_bar` po odświeżeniu cen bez SHEET; 10-14..10-16 różni się
  `calibration_correction` – konfiguracja niezawodności zmieniona po tych
  dniach). **Stare wiersze z nowymi szczeblami = bez nich, bajt w bajt: 0
  meczów z różnicą** (wszystkie 7 dni).
- CONFIDENCE (prawdziwy `run_confidence.py` na kopii dnia, zegar 5 min po
  najnowszej cenie): 10-18 8 727 → 8 727 nóg, 10-19 1 853 → 1 853, 10-20
  2 493 → 2 493; **utracone 0, zmienione 0, nowe 0**. Nowe wiersze:
  `NO_LINE_EVIDENCE` (57 / 4 / 116) i `NO_PRICE` (UNDER bez ceny) –
  oczekiwane: brak krzywej, brak rozliczonych linii.

## Rozliczenie (sanity, 10-14..10-19, statystyki z cache, `_settle_derived`)

64 mecze, 668 wycenionych (kwotowanych) wierszy, wszystkie rozliczone (0
`DERIVED_SUBJECT`, 0 braków danych). Realizacja − p (bootstrap po meczach,
95 %):

| rynek | n | wszystkie p | n p >= 0,70 | p >= 0,70 |
|---|---|---|---|---|
| both_over_goal_kicks | 165 | +0,2 pp [−10,5, +11,0] | 29 | −0,4 pp [−14,6, +13,3] |
| both_over_throw_ins | 143 | +0,4 [−14,7, +15,1] | 23 | −24,5 [−47,2, +0,1] |
| both_over_tackles | 162 | +15,9 [+0,8, +31,1] | 16 | −23,1 [−43,3, +7,4] |
| handicap_shots | 80 | +2,6 [−2,9, +8,0] | 21 | −31,4 [−53,4, −11,0] |
| handicap_shots_1h | 60 | +0,6 [−5,7, +7,0] | 14 | −36,4 [−62,2, −8,1] |
| handicap_shots_2h | 58 | +5,4 [+0,3, +11,7] | 10 | −21,2 [−51,1, +8,3] |
| **razem** | 668 | +4,8 [−0,0, +9,8] | 113 | **−20,6 [−30,7, −11,3]** |

Surowe p łącznego rozkładu (próbka bez przeoru, bez korekty przeciwnika) jest
w środku skalibrowane, ale **przy p >= 0,70 zawyża o ~20 pp** (mała próba,
szczeble jednego meczu skorelowane). To nie trafia do kuponu: bez krzywej
pewność to tylko dolna granica Wilsona własnych linii / deff (line evidence),
więc te p nie zostaną wydrukowane wprost. Dodatkowo: wszystkie te szczeble są
jednostronne (Superbet nie kwotuje UNDER / pary), a `confidence.
one_sided_single` dopuszcza pojedynczą nogę jednostronną tylko z własną
krzywą historyczną n >= 300 – rynki pochodne krzywych nie mają
(`DERIVED_CURVES_FROM_UTC = None`), więc **jako pojedyncze nie wydrukują się
także po uzbieraniu linii**; mogą najwyżej wejść do builderów. Realny zysk
włączenia: wiersze SHEET i rozliczone linie Superbetu (materiał dla line
evidence i przyszłej krzywej pochodnej), zero zmian w drukowanych nogach.

## Testy i bramki

`tests/sofa/test_football_stat_variants.py` (55): przełącznik i zegar,
`day_flags`, każda polska nazwa i odmowy (sbv ≠ wybór, brak linii, brak
tak/nie, klub spoza listingu, `;`, nazwy innych klasyfikatorów, rynki czasowe),
wyłączony = `OfferFetcher` bez parametru, włączony dodaje dokładnie nowe
szczeble i nie rusza innych, mecz tenisowy nic, SAMPLES prosi o metryki
stron, SHEET wycenia każdy rynek (dopełnienie handicapu = 1) i nie rusza starych
wierszy, SETTLE każdego rynku (WIN/LOSS, połowy osobno, PUSH, brak statystyki),
nazwy Superbetu w obie strony. `pytest tests/sofa`: 5 285 passed, 1 failed –
`test_documented_commands[...measure_cs2_map_total_race.py]` (model-state.md
odwołuje się do skryptu, którego nie ma w repo na HEAD; nie z tego pakietu).
ruff, mypy --strict, `check_test_registry.py`: czyste.

## Ryzyka / otwarte

- Włączenie w zbudowany dzień: `rebuild_plan` nie wie o tym przełączniku (nie
  wymusza ponownego OFFER) – planowane 00:00Z następnego dnia nie potrzebuje.
- Korelacja stron dla throw_ins / goal_kicks / tackles / shots_1h/2h
  niezmierzona (0) – jak dla już działających `both_over_saves`.
- Kursy z `unmapped_prices` od 10-14 można by rozliczyć wstecz jako linie dla
  line evidence (potrzebny p z replayu SHEET) – nie zrobione.
