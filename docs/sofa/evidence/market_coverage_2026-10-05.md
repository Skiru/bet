# Pokrycie rynków Superbetu - 2026-10-05 (plan F1.1, F1.5)

Plan `docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md`, F1.1. Każdy rynek
Superbetu dnia, którego OFFER nie odczytał, dostaje dokładnie jedną z
trzech etykiet. Kryterium: koszyk UNCLASSIFIED ma być pusty.

To raport, nie wejście potoku. Nie zmienia tego, co OFFER mapuje, ani tego,
co wybiera kupon. Etykieta MAPPABLE to propozycja: zmapowanie rynku dodaje
wiersze do budowy, więc może wejść tylko między dniami, za epoką w
`bet.sofa.epochs`.

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/report_market_coverage.py --date 2026-10-05
# domyślnie runs/sofa/<d>/market_coverage.{json,md}; exit 0 = 0 UNCLASSIFIED, 1 = są (wypisane), 2 = brak pliku
```

Metoda jest w `src/bet/sofa/market_coverage.py`, testy w
`tests/sofa/test_market_coverage.py`. Wynik w JSON leży obok tego pliku:
`market_coverage_2026-10-05.json`. Krok jest też w `.claude/commands/sofa-day.md`
(Step 2, po OFFER).

## 1. Etykiety

- **MAPPABLE** - statystykę już liczymy, bo jest metryką w `bet.sofa.metrics`
  albo rynkiem pochodnym na niej (`bet.sofa.derived`). Brakuje tylko nazwy w
  `market_mapper` albo zakresu (połowa / set) na istniejącym kształcie
  pochodnym. Uwaga podaje proponowaną metrykę.
- **COMPUTABLE** - da się policzyć z historii, którą trzymamy w cache:
  - wyniki setów i połów w listingu,
  - incydenty goli i kartek z minutą i zawodnikiem,
  - `/statistics` per okres,
  - `/lineups`.

  Potrzebna jest jednak nowa wielkość albo nowa wycena: rozkład, łączny
  rozkład dwóch stron, model wyniku. **Warunek: wynik pytania musi być
  widoczny w historii i w SETTLE**, bo inaczej nie da się go skalibrować ani
  rozliczyć. Uwaga mówi, czego potrzeba.
- **NOT_COMPUTABLE** - żadne źródło, które trzymamy, nie zapisuje tej
  wielkości. Uwaga podaje powód. Przykład: kto wygrał 5. gema albo stan
  po 4 gemach. Model z częstości utrzymań serwisu dałby jakąś liczbę, ale
  wyniku nie widać ani w historii, ani w SETTLE, więc to NOT_COMPUTABLE.
- **UNCLASSIFIED** - żadna reguła nie pasuje. Ten koszyk jest liczony i
  wypisywany, nigdy ukrywany.

**Kombinacje Superbetu** to nazwy łączone `;` (gotowe SuperBets). Każdą
część klasyfikuje się osobno:
- NOT_COMPUTABLE, jeśli którakolwiek część jest NOT_COMPUTABLE;
- UNCLASSIFIED, jeśli którakolwiek część jest nieznana;
- w pozostałych przypadkach COMPUTABLE: potrzebny jest łączny rozkład
  części, a cena kombinacji to cena Superbetu, nigdy iloczyn nóg.

**Porównywanie nazw.**
- Nazwy są składane przez `market_mapper.fold`, który zamienia też „ł".
- Nazwy stron z tablicy i z Sofascore zastępuje się `{a}` / `{b}`, tylko
  jako całe słowa: strona „Fran" nie zjada początku „Francesco".
- Liczby zamienia się na `#`, z wyjątkiem liczebników porządkowych
  („1. set", „2.połowa"), bo 3. set nie ma zadeklarowanych metryk.

Dwie reguły biorą pierwszeństwo przed tabelą:
- **`mapper.current`** - nazwa, którą dzisiejszy `market_mapper` czyta. Na
  dawnym dniu to luka już zamknięta. Nazwa z dopiskiem OFFER „(no line)"
  albo „(unparseable line)" trafia do `mapper.line_refused`.
- **`mapper.side_name_refused`** - wzorzec pasuje, ale strażnik podmiotu
  odrzuca nazwę strony. Przykład: „Dagenham & Redbridge - liczba goli";
  znak „&" w nazwie klubu blokuje `_SUBJECT_IS_COMBINATION`.

## 2. Wejście

| plik | mtime (UTC) | sha256 |
|---|---|---|
| `runs/sofa/2026-10-05/01_board.json` | 2026-10-05T04:57:04 | `0918590f5468…af9cba` |
| `runs/sofa/2026-10-05/02_fixtures.json` | 2026-10-05T05:33:47 | `8ef7c023…ff0d9f` |
| `runs/sofa/2026-10-05/04_offer.json` | 2026-10-05T11:43:17 | `98d78e29…414be2` |

Pełne skróty są w JSON (`inputs`).

**Liczba niezmapowanych zależy od tego, kiedy OFFER biegł**, bo każde
odświeżenie nadpisuje `04_offer.json`:

| moment | niezmapowane |
|---|---|
| poranny OFFER (`pipeline_0500.log`) | 26 756 |
| plik z ~10:57Z | 27 627 |
| plik z 11:43Z (ten raport) | 27 757 |

Liczby planu (17 166) nie odtworzyłem z żadnej wersji pliku, którą widziałem.

## 3. Wynik

| | wystąpienia | różne nazwy |
|---|---|---|
| rynki oferowane (zmapowane + niezmapowane) | 32 618 | - |
| **zmapowane** (OFFER zrobił z nich szczeble) | **4 861** (14,9%) | - |
| niezmapowane | 27 757 | 18 214 |
| MAPPABLE | 512 | 239 |
| COMPUTABLE | 22 050 | 14 161 |
| NOT_COMPUTABLE | 5 195 | 3 814 |
| **UNCLASSIFIED** | **0** | **0** |

**Jak liczone.**
- Jedno wystąpienie niezmapowane to jedna para (mecz, nazwa) w
  `unmapped_markets`.
- Zmapowane to różne trójki (mecz, rynek, podmiot) ze szczebli `04_offer`.
  `most_` i `handicap_` liczą się raz na (mecz, rynek), bo to jeden rynek
  Superbetu dla wszystkich wyborów.
- Zmapowane są więc liczone w kluczach sofa, nie w nazwach Superbetu - to
  przybliżenie.
- Rynek zmapowany, którego wybór nie jest „powyżej / poniżej", OFFER
  pomija bez śladu (`classify_odd` zwraca `(None, None)`). Takich
  wystąpień nie widać ani tu, ani nigdzie.

| sport | MAPPABLE | COMPUTABLE | NOT_COMPUTABLE | UNCLASSIFIED |
|---|---|---|---|---|
| piłka | 345 | 12 269 | 327 | 0 |
| tenis | 167 | 9 781 | 4 868 | 0 |

**Co zajmuje ekran.** 16 942 z 27 757 wystąpień (61%) to kombinacje
Superbetu:

| sport | kombinacje COMPUTABLE | kombinacje NOT_COMPUTABLE |
|---|---|---|
| piłka | 7 037 | - |
| tenis | 6 794 | 3 111 |

Części tych kombinacji to w większości szczeble, które już wyceniamy:
- piłka: 13 750 części MAPPABLE na 18 855;
- tenis: 9 976 części MAPPABLE na 22 109.

Na tenisowe NOT_COMPUTABLE składa się:
- 1 756 pojedynczych nazw na poziomie gema i punktu (`tn.game_order`
  1 020 i `tn.points_in_game` 736);
- 3 111 kombinacji z taką częścią.

Wszystkie wymagałyby historii punkt po punkcie. Endpoint istnieje
(`docs/sofa/evidence/event_15345277_point_by_point.json`), ale nie jest
pobierany do cache.

**Sprawdzenie na innych dniach.** Te same reguły na
`runs/sofa/2026-09-18..2026-10-04` dają 0 UNCLASSIFIED na każdym z 17 dni.
Reguły pisałem jednak, patrząc na te dni - to sprawdzenie w próbie. Nowa
nazwa w nowym dniu wypadnie jako UNCLASSIFIED (exit 1) i trzeba będzie
dopisać regułę.

## 4. MAPPABLE - propozycje (żadna nie wdrożona)

| rodzina | wyst. 10-05 | propozycja | co trzeba w kodzie |
|---|---|---|---|
| `fb.team_scores_half` | 148 | goals_1h_for / goals_2h_for OVER 0.5 | rynek tak/nie bez linii, czyli nowy klasyfikator jak `classify_derived_market` dla BTTS |
| `tn.handicap_games_set` | 112 | handicap_games_set1 / _set2 | zakres seta na handicapie (jak `_MOST_SCOPED`); uwaga: per-set gemy to dziś `TENNIS_SET_MARKET_NOT_ADMITTED` (F1.3) |
| `fb.team_scores` | 76 | goals_for OVER 0.5 | tak/nie |
| `fb.btts_half` | 74 | both_over_goals w połowie | zakres połowy na both_over; pochodne i tak są `DERIVED_NOT_CALIBRATABLE` (F1.3) |
| `tn.deciding_set_played` | 55 | sets_total OVER 2.5 / 4.5 | tak/nie |
| `fb.both_over_saves`, `_saves_half`, `_throw_ins`, `_goal_kicks`, `_tackles` | 27 | both_over_<metryka> | nazwy w `_DERIVED_METRIC_NAMES`; Superbet pisze tu „Każda drużyna", nie „Każda z drużyn" |
| `fb.handicap_shots`, `_shots_half`, `_corners_half` | 20 | handicap_<metryka>[_1h] | wzorzec „Strzały - Handicap" i zakres połowy |
| (inne dni) `mapper.side_name_refused` | 37 wystąpień 09-26..10-03 | goals_for / goals_1h_for / goals_2h_for | **prawdziwa luka**: nazwy klubów z „&" (Dagenham & Redbridge, Wingate & Finchley, H&W Welders, Havant & Waterlooville) odrzuca strażnik kombinacji |
| (inne dni) `fb.most_h2h`, `fb.handicap_half`, `fb.goal_kicks_half_for`, `tn.any_tiebreak`, `tn.handicap_games_set3`, `tn.handicap_double_faults`, `fb.most_half` | - | patrz JSON / reguły | |

Na kuponie stats-only rynki pochodne i tenisowe rynki w secie są dziś
odrzucane w CONFIDENCE (`blocked_families_2026-10-05.md`). Zmapowanie ich
nazw nie doda więc nogi, dopóki nie dostaną krzywej. Doda je dopiero do
SHEET.

## 5. COMPUTABLE nie znaczy „warto"

Etykieta mówi tylko, że wielkość da się policzyć i rozliczyć z danych, które
trzymamy. Nie mówi, że model pobije cenę. Pomiary już są:
- rynki wyniku: model wyniku hokeja na zwycięzcy / 1X2 jest gorszy od ceny
  (`docs/sofa/RAPORT_KALIBRACJA_SPORTOW_2026-10-05.md`);
- rynki pochodne zawyżają o 3-25 pp (F1.3);
- propsy zawodników ślepo -45,8%.

Każda nowa rodzina wchodzi według reguły planu „mierz zanim użyjesz".

## 6. Czego ten raport nie obejmuje

- **Hokej, koszykówka, siatkówka, CS2.** SHADOW i CS2 zapisują w
  `snapshots.jsonl` tylko rodziny, które mapują; nazwy niezmapowanych
  rynków tych sportów nie trafiają do żadnego artefaktu. Raport obejmuje
  więc piłkę i tenis z OFFER. Żeby objąć resztę, SHADOW / CS2 musiałyby
  zapisywać `unmapped_markets` jak OFFER - to zmiana zapisu, nie selekcji;
  nie wprowadzona.
- **Weryfikacja źródeł per rodzina.** Etykiety COMPUTABLE opierają się na
  tym, że klucz jest w cache (np. `bodyPart` gola w
  `footballPassingNetworkAction` ma ~26 tys. meczów piłki, `hitWoodwork` -
  106 z 265 meczów próbki). Nie sprawdzono, czy wartości zgadzają się z
  rozliczeniem Superbetu. Tak trzeba zrobić przy każdym mapowaniu, jak przy
  `tackles` / `wasFouled` (players.py:85-98).

## 7. F1.5 - kandydaci na nowe sporty (decyzja operatora)

Zasada planu: sport wchodzi tylko z realnym źródłem statystyk i rozliczenia.
Symulacje Superbetu zostają poza: 190 (wirtualna piłka), 75 (e-piłka), 157
(e-hokej), 70 (e-koszykówka).

**Stan faktyczny w repo.**
- `sofa_listed_event` zna tylko sześć sportów: football, tennis,
  ice-hockey, basketball, volleyball, esports.
- `superbet.SPORT_IDS` w BOARD ma tylko piłkę (5) i tenis (2).
- Pozostałe identyfikatory Superbetu są w kodzie SHADOW / CS2: 3, 4, 1, 55.
- Żaden artefakt nie zapisuje pełnej listy sportów Superbetu. To, czy
  Superbet wystawia dany sport, jest więc tu **niesprawdzone**.

| sport | źródło statystyk i rozliczenia | stan w repo | co trzeba, żeby rozstrzygnąć |
|---|---|---|---|
| baseball (MLB i inne) | Sofascore ma baseball (wynik po zmianach) - niesprawdzone w cache | `docs/sofa/evidence/mlb_measurement.md`: **NOT_MEASURED** (09-17, 50/50 zapytań nieudanych); „poza sofa, bo niezmierzony, nie odrzucony" | ponowić `scripts/sofa/measure_mlb.py` przez most; jedna sonda BOARD Superbetu (identyfikator sportu, rynki) |
| piłka ręczna | Sofascore - niesprawdzone (0 meczów w cache) | brak | sonda BOARD + listing / wynik Sofascore na 1 dniu, jak SHADOW |
| futbol amerykański (NFL / NCAA) | Sofascore - niesprawdzone | brak | jak wyżej |
| tenis stołowy | Sofascore - niesprawdzone; ligi typu „Setka Cup" to prawdziwe mecze, ale o niskiej wiarygodności (ryzyko integralności - podejrzenie, niezmierzone) | brak | jak wyżej + decyzja, czy ligi z serii dziennych w ogóle dopuszczać |
| rzutki, snooker | Sofascore - niesprawdzone (lotki: legi; snooker: frejmy) | brak | jak wyżej |
| esport poza CS2 (LoL, Dota 2, Valorant) | Sofascore esports - niesprawdzone; CS2 już mierzone jako „~stopa bazowa" | CS2 na kuponie od 10-05 | ta sama ścieżka co CS2 (`cs2_store`), osobny pomiar |
| MMA, rugby, futsal, krykiet | niesprawdzone | brak | jak wyżej |

Nic z tej tabeli nie zostało zmierzone. Każdy sport to osobna epoka i
osobny wiersz w ledgerze, nigdy nie sumowane. Pierwszym krokiem jest
zawsze pomiar jak SHADOW (ceny i rozliczenie bez kuponu), nie kupon.

---

Poniżej tabele wygenerowane przez `report_market_coverage.py` z plików z
sekcji 2.

## Rodziny

| sport | etykieta | rodzina | wystąpienia | szablony | propozycja / potrzeba / powód | przykład |
|---|---|---|---|---|---|---|
| football | MAPPABLE | `fb.team_scores_half` | 148 | 4 | goals_1h_for / goals_2h_for OVER 0.5 (tak/nie) | 1.połowa - Smederevo strzeli gola |
| tennis | MAPPABLE | `tn.handicap_games_set` | 112 | 2 | handicap_games_set1 / _set2 (games_won_set1_for; handicap z zakresem seta jak most_ w _MOST_SCOPED) | 1. set - handicap gemy |
| football | MAPPABLE | `fb.team_scores` | 76 | 2 | goals_for OVER 0.5 (tak/nie) | Smederevo strzeli gola |
| football | MAPPABLE | `fb.btts_half` | 74 | 2 | both_over_goals w połowie (zakres połowy na kształcie both_over; goals_1h_for / goals_2h_for są metrykami) | 1.połowa - obie drużyny strzelą |
| tennis | MAPPABLE | `tn.deciding_set_played` | 55 | 1 | sets_total OVER 2.5 (Bo3) / 4.5 (Bo5) - odpowiedź tak/nie na drabinie, którą już wyceniamy | Zostanie rozegrany 3. set |
| football | MAPPABLE | `fb.both_over_saves` | 9 | 1 | both_over_saves (saves_for jest metryką; brak nazwy w _DERIVED_METRIC_NAMES) | Każda z drużyn powyżej X obronionych strzałów przez bramkarza |
| football | MAPPABLE | `fb.handicap_shots_half` | 8 | 2 | handicap_shots_1h (shots_1h_for) | 1. połowa - liczba strzałów - handicap |
| football | MAPPABLE | `fb.handicap_corners_half` | 8 | 2 | handicap_corners_1h / _2h (corners_1h_for; handicap z zakresem połowy jak most_ w _MOST_SCOPED) | 1. połowa - rzuty rożne - handicap |
| football | MAPPABLE | `fb.both_over_throw_ins` | 5 | 1 | both_over_throw_ins (throw_ins_for; Superbet pisze 'Każda drużyna', nie 'Każda z drużyn') | Każda drużyna powyżej X rzutów z autu |
| football | MAPPABLE | `fb.both_over_goal_kicks` | 5 | 1 | both_over_goal_kicks (goal_kicks_for) | Każda drużyna powyżej X wybić od bramki |
| football | MAPPABLE | `fb.both_over_saves_half` | 4 | 1 | both_over_saves_1h (saves_1h_for jest metryką) | 1. połowa - każda z drużyn powyżej X obronionych strzałów przez bramkarza |
| football | MAPPABLE | `fb.both_over_tackles` | 4 | 1 | both_over_tackles (tackles_for) | Każda z drużyn powyżej X odbiorów |
| football | MAPPABLE | `fb.handicap_shots` | 4 | 1 | handicap_shots (shots_for; wzorzec 'liczba X - handicap' nie łapie 'Strzały - Handicap') | Strzały - Handicap |
| football | COMPUTABLE | `superbet_combo` | 7037 | 2572 | łączny rozkład części (jak combined_probability buildera) | Poniżej 4.5 gola w meczu; Powyżej 0.5 gola w meczu; Poniżej 2.5 gola w 1.połowie |
| tennis | COMPUTABLE | `superbet_combo` | 6794 | 122 | łączny rozkład części (jak combined_probability buildera) | 1. set - Joao Domingues wygra 6:0, 6:1 lub 6:2; 2. set - Joao Domingues wygra 6:0, 6:1 lub |
| football | COMPUTABLE | `fb.result_combo` | 1265 | 12 | model wyniku (łączny rozkład goli obu stron) - historia goli (wynik + połowy w listingu, goal_for obu stron) | Mecz & liczba goli (2.5) |
| tennis | COMPUTABLE | `tn.sets` | 1240 | 17 | model setów/gemów z wyniki setów (homeScore.periodN + periodNTieBreak w listingu) | Dokładna liczba setów |
| tennis | COMPUTABLE | `tn.set_score` | 552 | 6 | rozkład wyniku seta - wyniki setów (homeScore.periodN + periodNTieBreak w listingu) | 1. set - dokładny wynik |
| football | COMPUTABLE | `fb.result_half` | 437 | 16 | model wyniku (łączny rozkład goli obu stron) - historia goli (wynik + połowy w listingu, goal_for obu stron) | 1.połowa - 1X2 |
| tennis | COMPUTABLE | `tn.set_winner` | 349 | 4 | model setów/gemów z wyniki setów (homeScore.periodN + periodNTieBreak w listingu) | 1. set - zwycięzca & liczba gemów |
| football | COMPUTABLE | `fb.result` | 344 | 7 | model wyniku (łączny rozkład goli obu stron) - historia goli (wynik + połowy w listingu, goal_for obu stron) | Mecz |
| football | COMPUTABLE | `fb.ht_ft` | 340 | 5 | model wyniku (łączny rozkład goli obu stron) - historia goli (wynik + połowy w listingu, goal_for obu stron) | 1. połowa lub mecz |
| tennis | COMPUTABLE | `tn.games_distribution` | 337 | 5 | rozkład gemów z wyniki setów (homeScore.periodN + periodNTieBreak w listingu) | Którykolwiek set zakończy się do zera |
| tennis | COMPUTABLE | `tn.winner` | 297 | 3 | model zwycięzcy (tennis_rating - forecast bez kalibracji) / wyniki setów (homeScore.periodN + periodNTieBreak w listingu) | Zwycięzca |
| football | COMPUTABLE | `fb.goal_timing` | 282 | 13 | minuta/kolejność goli - incydenty Sofascore (gole/kartki z minutą i zawodnikiem, sofa_event_stats.incidents_json) | 1. gol |
| football | COMPUTABLE | `fb.result_or` | 276 | 12 | model wyniku (łączny rozkład goli obu stron) - historia goli (wynik + połowy w listingu, goal_for obu stron) | Cypr wygra lub którakolwiek drużyna zachowa czyste konto |
| football | COMPUTABLE | `fb.halves` | 224 | 8 | model wyniku (łączny rozkład goli obu stron) - historia goli (wynik + połowy w listingu, goal_for obu stron) | Połowa z większą liczbą goli |
| football | COMPUTABLE | `fb.btts_combo` | 215 | 3 | model wyniku (łączny rozkład goli obu stron) - historia goli (wynik + połowy w listingu, goal_for obu stron) | Obie drużyny strzelą gola & powyżej 2.5 gola |
| football | COMPUTABLE | `fb.goals_for_distribution` | 192 | 8 | rozkład goals_for (dokładna liczba, parzystość, przedziały) - historia goli (wynik + połowy w listingu, goal_for obu stron) | Armenia U21 - przedział goli w każdej połowie |
| football | COMPUTABLE | `fb.player_goals` | 179 | 14 | gole zawodnika z incydentów (player, minuta, assist1) / /lineups (statystyki zawodnika; w cache ~4,5 tys. meczów piłki) | Którykolwiek z zawodników strzeli gola |
| football | COMPUTABLE | `fb.goal_sequence` | 168 | 6 | przebieg wyniku z kolejności goli - incydenty Sofascore (gole/kartki z minutą i zawodnikiem, sofa_event_stats.incidents_json) | Armenia U21 będzie prowadzić w dowolnym momencie |
| football | COMPUTABLE | `fb.goals_distribution` | 165 | 4 | rozkład goals_total (dokładna liczba, parzystość, przedziały) - historia goli (wynik + połowy w listingu, goal_for obu stron) | Nieparzysta/parzysta liczba goli |
| football | COMPUTABLE | `fb.side_result` | 160 | 6 | model wyniku (łączny rozkład goli obu stron) - historia goli (wynik + połowy w listingu, goal_for obu stron) | Smederevo wygra obie połowy |
| football | COMPUTABLE | `fb.goals_half_for_distribution` | 132 | 6 | rozkład goals_1h_for / goals_2h_for - historia goli (wynik + połowy w listingu, goal_for obu stron) | 1.połowa - Cypr - dokładna liczba goli |
| football | COMPUTABLE | `fb.corners_distribution` | 121 | 6 | rozkład corners_* (parzystość, przedziały) z /statistics | 1.połowa - nieparzysta/parzysta liczba rzutów rożnych |
| football | COMPUTABLE | `fb.goals_halves_for` | 102 | 4 | model wyniku (łączny rozkład goli obu stron) - historia goli (wynik + połowy w listingu, goal_for obu stron) | Armenia U21 - 1.połowa liczba goli & 2.połowa liczba goli |
| tennis | COMPUTABLE | `tn.tiebreak_set` | 100 | 2 | tie-break w secie N z wyniki setów (homeScore.periodN + periodNTieBreak w listingu) | Tiebreak lub Super Tiebreak w decydującym secie |
| football | COMPUTABLE | `fb.cards_half_or_exact` | 91 | 12 | kartki w połowie / dokładna liczba z minutą kartki - incydenty Sofascore (gole/kartki z minutą i zawodnikiem, sofa_event_stats.incidents_json) | 1. połowa - liczba kartek |
| football | COMPUTABLE | `fb.goals_halves` | 89 | 3 | model wyniku (łączny rozkład goli obu stron) - historia goli (wynik + połowy w listingu, goal_for obu stron) | 1.Połowa - liczba goli & liczba goli w meczu |
| football | COMPUTABLE | `fb.red_cards` | 62 | 6 | card|red, card|yellowRed - incydenty Sofascore (gole/kartki z minutą i zawodnikiem, sofa_event_stats.incidents_json) | 1.połowa - liczba czerwonych kartek |
| tennis | COMPUTABLE | `tn.points` | 60 | 6 | pointsTotal w /statistics (ALL i okresy setów); brak metryki | 1. set - Daniil Medvedev liczba punktów |
| football | COMPUTABLE | `fb.player_goal_detail` | 44 | 5 | bodyPart / situation / współrzędne gola (footballPassingNetworkAction) - incydenty Sofascore (gole/kartki z minutą i zawodnikiem, sofa_event_stats.incidents_json) | Zawodnik - strzeli gola głową |
| football | COMPUTABLE | `fb.any_player` | 43 | 6 | maksimum po zawodnikach - /lineups (statystyki zawodnika; w cache ~4,5 tys. meczów piłki) | Którykolwiek z zawodników odda powyżej X strzałów |
| football | COMPUTABLE | `fb.woodwork` | 42 | 3 | klucz hitWoodwork w /statistics (tylko część meczów - pokrycie do zmierzenia); brak metryki | Kenia - Liczba strzałów w obramowanie bramki |
| football | COMPUTABLE | `fb.penalties` | 41 | 6 | goal|penalty + inGamePenalty|missed - incydenty Sofascore (gole/kartki z minutą i zawodnikiem, sofa_event_stats.incidents_json) | Liczba przyznanych rzutów karnych |
| football | COMPUTABLE | `fb.player_pair` | 40 | 40 | suma/łączny rozkład dwóch zawodników - /lineups (statystyki zawodnika; w cache ~4,5 tys. meczów piłki) | Cherki, Rayan & De Ketelaere, Charles każdy odda 1+ celnych strzałów i każdy zostanie sfau |
| football | COMPUTABLE | `fb.player_cards` | 39 | 3 | kartki zawodnika z incydentów - incydenty Sofascore (gole/kartki z minutą i zawodnikiem, sofa_event_stats.incidents_json) | Zawodnik - otrzyma 1. kartkę |
| tennis | COMPUTABLE | `tn.service_points` | 30 | 3 | punkty serwisowe zawodnika = mianownik firstServeAccuracy w /statistics ("62/87" -> 87); brak metryki | Daniil Medvedev liczba serwisów |
| football | COMPUTABLE | `fb.player_woodwork` | 29 | 29 | klucz hitWoodwork w /lineups - /lineups (statystyki zawodnika; w cache ~4,5 tys. meczów piłki) | Cherki, Rayan odda strzał w obramowanie bramki |
| football | COMPUTABLE | `fb.card_timing` | 28 | 4 | minuta kartki - incydenty Sofascore (gole/kartki z minutą i zawodnikiem, sofa_event_stats.incidents_json) | 1. kartka |
| football | COMPUTABLE | `fb.own_goals` | 23 | 1 | goal|ownGoal - incydenty Sofascore (gole/kartki z minutą i zawodnikiem, sofa_event_stats.incidents_json) | Liczba goli samobójczych |
| tennis | COMPUTABLE | `tn.double_faults_unknown_shape` | 22 | 1 | double_faults_* są metrykami, ale kształt wyborów tego rynku nie jest zapisany w 04_offer - sprawdzić payload przed mapowaniem | Podwójne błędy |
| football | COMPUTABLE | `fb.goal_method` | 15 | 1 | bodyPart / situation / goalType gola (footballPassingNetworkAction, ~26 tys. meczów) - incydenty Sofascore (gole/kartki z minutą i zawodnikiem, sofa_event_stats.incidents_json) | Sposób zdobycia 1. gola |
| football | COMPUTABLE | `fb.incident_specials` | 15 | 4 | incydenty Sofascore (gole/kartki z minutą i zawodnikiem, sofa_event_stats.incidents_json) (addedTime) | Czerwona kartka lub gol w doliczonym czasie 2. połowy |
| football | COMPUTABLE | `fb.person_cards` | 10 | 10 | kartka zawodnika lub trenera (incydent card: player / manager) - incydenty Sofascore (gole/kartki z minutą i zawodnikiem, sofa_event_stats.incidents_json) | Zinedine Zidane & Mark van Bommel każdy otrzyma kartkę |
| football | COMPUTABLE | `fb.goalkeeper_specials` | 8 | 2 | wasFouled / goalAssist bramkarza - /lineups (statystyki zawodnika; w cache ~4,5 tys. meczów piłki) | Każdy bramkarz zostanie sfaulowany |
| football | COMPUTABLE | `fb.player_fouled` | 6 | 1 | klucz wasFouled w /lineups (market_mapper 2026-09-29 uznał, że żaden klucz tego nie dowodzi - do weryfikacji na rozliczeniu) - /lineups (statystyki zawodnika; w cache ~4,5 tys. meczów piłki) | Zawodnik - liczba fauli na zawodniku |
| football | COMPUTABLE | `fb.saves_halves` | 4 | 1 | goalkeeperSaves w okresach 1ST/2ND /statistics (saves_2h nie jest metryką) | Każdy bramkarz obroni strzał w każdej połowie |
| football | COMPUTABLE | `fb.substitutions` | 1 | 1 | substitution - incydenty Sofascore (gole/kartki z minutą i zawodnikiem, sofa_event_stats.incidents_json) | Każda z drużyn wykorzysta wszystkie 5 zmian |
| tennis | NOT_COMPUTABLE | `superbet_combo` | 3111 | 21 | co najmniej jedna część NOT_COMPUTABLE (rozbicie na części niżej) | 1. set - dokładny wynik po 4 gemach: 2:2; 2. set - dokładny wynik po 4 gemach: 2:2 |
| tennis | NOT_COMPUTABLE | `tn.game_order` | 1020 | 6 | brak historii gem po gemie: wynik seta nie mówi, kto wygrał który gem ani jaki był stan po N gemach (/point-by-point nie w cache); model z częstości utrzymań serwisu (serviceGamesWon) dałby liczbę, której nie da się skalibrować ani rozliczyć | 1. set - będzie prowadzić po 2 gemach |
| tennis | NOT_COMPUTABLE | `tn.points_in_game` | 736 | 6 | brak historii punkt po punkcie (Sofascore /point-by-point nie jest pobierane do cache): wyniku nie widać ani w historii, ani w SETTLE - model punktu dałby liczbę, której nie da się skalibrować ani rozliczyć | Dokładny wynik - wynik po 3 punktach w 1. gemie serwisowym Joao Domingues |
| football | NOT_COMPUTABLE | `fb.non_goal_event_timing` | 206 | 25 | brak kolejności/minuty zdarzeń innych niż gole i kartki (incydenty Sofascore nie zawierają rożnych, fauli, strzałów, autów, wybić, spalonych) | Kto pierwszy wykona X rzutów różnych |
| football | NOT_COMPUTABLE | `fb.player_shot_detail` | 76 | 9 | brak części ciała / miejsca strzałów niebędących golem (shotmap nie w cache; /lineups podaje tylko sumy) | Zawodnik - liczba celnych strzałów głową |
| football | NOT_COMPUTABLE | `fb.var_review` | 15 | 4 | brak źródła: incydent varDecision zapisuje decyzję, nie podejście sędziego do monitora | Sędzia podejdzie do monitora VAR co najmniej dwa razy |
| football | NOT_COMPUTABLE | `fb.player_pair_fouled_each_other` | 14 | 14 | brak źródła: /lineups nie mówi, kto kogo sfaulował | Cherki, Rayan & De Ketelaere, Charles sfaulują się nawzajem |
| football | NOT_COMPUTABLE | `fb.specials` | 8 | 2 | brak źródła w danych Sofascore (zdarzenie spoza statystyk meczu) | Każda drużyna wykona rzut rożny z każdego narożnika boiska |
| football | NOT_COMPUTABLE | `fb.player_goal_detail_unknown` | 4 | 1 | brak źródła: bodyPart gola zna tylko right-foot/left-foot/head/other | Zawodnik - strzeli gola z przewrotki |
| football | NOT_COMPUTABLE | `fb.player_tackled` | 3 | 1 | brak klucza: /lineups ma totalTackle (wykonane), nie odbiory na zawodniku | Zawodnik - liczba odbiorów na zawodniku |
| football | NOT_COMPUTABLE | `boost` | 1 | 1 | promocja Superbetu bez zdefiniowanej wielkości (boost; osobny snapshot run_boosts) | Boost |
| tennis | NOT_COMPUTABLE | `boost` | 1 | 1 | promocja Superbetu bez zdefiniowanej wielkości (boost; osobny snapshot run_boosts) | Boost |

## Kombinacje Superbetu (`;`) - części

| sport | etykieta części | rodzina | części |
|---|---|---|---|
| tennis | COMPUTABLE | `tn.winner` | 4131 |
| tennis | MAPPABLE | `tn.games_set_total` | 3534 |
| football | COMPUTABLE | `fb.side_result` | 3265 |
| football | MAPPABLE | `fb.goals_total` | 3201 |
| tennis | NOT_COMPUTABLE | `tn.points_in_game` | 2200 |
| tennis | NOT_COMPUTABLE | `tn.game_order` | 2074 |
| football | MAPPABLE | `fb.player_sot` | 2042 |
| tennis | COMPUTABLE | `tn.set_score` | 1881 |
| football | MAPPABLE | `fb.goals_for` | 1746 |
| tennis | MAPPABLE | `tn.games_total` | 1057 |
| tennis | COMPUTABLE | `tn.set_winner` | 1005 |
| tennis | MAPPABLE | `tn.sets_total` | 920 |
| football | COMPUTABLE | `fb.player_goals` | 875 |
| tennis | COMPUTABLE | `tn.sets` | 842 |
| football | MAPPABLE | `fb.corners_total` | 760 |
| tennis | MAPPABLE | `tn.tiebreaks_total` | 679 |
| football | MAPPABLE | `fb.corners_for` | 662 |
| football | MAPPABLE | `fb.cards_total` | 658 |
| tennis | MAPPABLE | `tn.games_won_for` | 620 |
| football | MAPPABLE | `fb.player_shots` | 607 |
| tennis | MAPPABLE | `tn.handicap_games` | 595 |
| football | MAPPABLE | `fb.player_fouls` | 588 |
| tennis | MAPPABLE | `tn.handicap_games_set` | 576 |
| football | MAPPABLE | `fb.both_over_corners` | 477 |
| football | COMPUTABLE | `fb.person_cards` | 452 |
| tennis | MAPPABLE | `tn.aces_for` | 440 |
| football | MAPPABLE | `fb.goals_half_total` | 420 |
| football | MAPPABLE | `fb.btts` | 420 |
| tennis | MAPPABLE | `tn.most_aces_set` | 382 |
| football | MAPPABLE | `fb.most_corners` | 345 |
| football | MAPPABLE | `fb.both_over_cards` | 317 |
| tennis | MAPPABLE | `tn.games_won_set_for` | 316 |
| tennis | MAPPABLE | `tn.aces_total` | 286 |
| tennis | MAPPABLE | `tn.aces_set_for` | 264 |
| football | MAPPABLE | `fb.cards_for` | 259 |
| football | MAPPABLE | `fb.player_tackles` | 248 |
| football | MAPPABLE | `fb.sot_total` | 240 |
| football | COMPUTABLE | `fb.goal_sequence` | 219 |
| football | MAPPABLE | `fb.sot_for` | 217 |
| football | COMPUTABLE | `fb.player_goal_detail` | 192 |
| tennis | MAPPABLE | `tn.double_faults_total` | 154 |
| football | MAPPABLE | `fb.goals_half_for` | 116 |
| football | COMPUTABLE | `fb.halves` | 102 |
| football | MAPPABLE | `fb.shots_total` | 90 |
| tennis | MAPPABLE | `tn.double_faults_set_for` | 88 |
| football | MAPPABLE | `fb.fouls_for` | 68 |
| football | MAPPABLE | `fb.offsides_total` | 56 |
| football | MAPPABLE | `fb.shots_for` | 49 |
| football | MAPPABLE | `fb.fouls_total` | 45 |
| tennis | MAPPABLE | `tn.double_faults_for` | 43 |
| football | MAPPABLE | `fb.most_sot` | 42 |
| football | MAPPABLE | `fb.tackles_for` | 27 |
| tennis | MAPPABLE | `tn.aces_set_total` | 22 |
| football | MAPPABLE | `fb.both_over_sot` | 18 |
| football | MAPPABLE | `fb.tackles_total` | 18 |
| football | MAPPABLE | `fb.most_cards` | 14 |

## UNCLASSIFIED

Brak - każda nazwa dnia ma etykietę.
