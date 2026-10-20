# Sędzia w kartkach i faulach (piłka), 2026-10-21

Przełącznik: `epochs.FOOTBALL_REFEREE_FROM_UTC` (`referee_v1`), **`None` =
wyłączony** (gotowy, nie włączony). Moduł: `bet.sofa.referees`. Konfiguracja:
`config/sofa_referee_effect.json` (pisze `scripts/sofa/measure_referee_effect.py
measure --write-config`; nieczytana, dopóki przełącznik jest `None`). Backfill:
`scripts/sofa/backfill_referees.py`. Pomiar (tylko odczyt):
`scripts/sofa/measure_referee_effect.py` (`measure` / `coverage` / `live` /
`announce`). Testy: `tests/sofa/test_referees.py`,
`tests/sofa/test_referee_switch.py`. Wyniki surowe (JSON): katalog roboczy sesji
`.../scratchpad/ref/final_A.json`, `final_B.json`, `final_C.json`,
`cov_final.json`.

## Dlaczego

Kartki (`cards_points_*`) i faule (`fouls_*`, z połowami) były wyceniane bez
sędziego. Pomiar 2026-10-08 (`count_families_2026-10-08.md`, sekcja 5) dał
+0,43 pkt [0,24; 0,62] reszty na 1 SD żółtych/mecz sędziego, ale tylko na 563
meczach: sędzia był znany dla ~0,19% meczów ze statystykami (tylko
`sofa_event_detail`), i to jako karta kariery, nie as-of meczu.

## Dane: backfill sędziów (2026-10-20, 21:14-21:56Z)

Kula śnieżna przez most (5 okien, ten sam klient, kubełek i bezpiecznik co
pipeline): (1) ziarno - 2 105 meczów z sędzią w `sofa_event_detail`, 1 188
sędziów; (2) `/referee/{id}/events/last/{p}` każdego znanego sędziego wstecz do
840 dni (30 meczów na stronę); (3) gdy nie ma kogo stronicować -
`/event/{id}` dla meczów piłkarskich ze statystykami w oknie bez etykiety
(round robin po rozgrywkach, najpierw te z tablic, w rozgrywce od najnowszych);
rozgrywka, w której po 25 pytaniach < 5% odpowiedzi nazywa sędziego, jest
pomijana (Sofascore nie ma sędziów dla większości niższych lig). Wynik:

- 3 643 strony sędziów (83 860 etykiet), ok. 17 800 pytań `/event`;
  **0 błędów, 0 odmów (403/429), bezpiecznik ani razu**;
- 83 872 mecze z sędzią, 2 540 sędziów (tabele `sofa_event_referee`,
  `sofa_referee_page`, `sofa_referee`; payloady `/event` zapisane jak RESOLVE
  w `sofa_event_detail`);
- malejące zyski: ostatnie 440 pytań `/event` - 2 nowych sędziów.

### Pokrycie (`coverage`, mecze piłkarskie ze statystykami lub incydentami w `sofa_listed_event`)

| sezon | mecze | z sędzią | udział | w rozgrywkach z tablic | z sędzią | udział |
|---|---|---|---|---|---|---|
| 2024/25 (od 2024-07) | 46 107 | 8 459 | 18,3% | 45 737 | 8 255 | 18,0% |
| 2025/26 | 112 451 | 24 493 | 21,8% | 109 874 | 23 504 | 21,4% |
| 2026/27 (do 10-20) | 39 157 | 7 121 | 18,2% | 37 714 | 6 741 | 17,9% |

Udział jest niski, bo większość meczów w cache'u to niższe ligi, dla których
Sofascore sędziego nie podaje (Segunda Federación, Primera Federación, 3. Liga,
National League North/South, J2, USL Championship, ligi rezerw: 0%). Tam,
gdzie Superbet daje kartki / faule, jest inaczej: **zdarzenia z wierszami
cards_points / fouls w `05_sheet.json` 2026-09-17..10-20 (34 dni): 1 222, z
sędzią w etykietach 1 050 (85,9%)**. Ligi (mecze ze statystykami od
2025-07-01): MLS 679/680, LaLiga 2 567/568, Brasileirão B 562/562, Liga
Profesional 638/639, DIMAYOR 333/334, League One 573/669, League Two 558/683,
FA Cup 120/301; (od 2024-07-01): Liga Konferencji 943/963, National League
706/1 122.

## Cecha as-of (`bet.sofa.referees.RefereeBook`)

Dla meczu w chwili t: poprzednie mecze sędziego w naszej historii (start < t,
z metryką), r_i = y_i / L_i, gdzie y_i to suma meczu (punkty kartkowe obu
stron albo faule obu stron), a L_i - średnia rozgrywki meczu i **as-of** (mecze
przed nim; < 30 meczów -> średnia wszystkich rozgrywek). Cecha = (Σ r_i + K) /
(n + K). Przy jednej rozgrywce to dokładnie (sum_ref + K·L) / (n + K) / L;
sędzia, który sędziuje ligę i puchar, jest czytany na poziomie każdego meczu.
Mecze o tej samej sekundzie startu są czytane, zanim którykolwiek trafi do
księgi (`walk_reads`; test `test_book_reads_only_matches_strictly_before`).
Brak sędziego albo brak rekordu: cecha 1. Kartki czytają rekord punktów
kartkowych, faule (cały mecz i połowy) - rekord fauli z całego meczu. Punkty
kartkowe z historii (`football_rating` -> `metrics.extract_metric`, jak
próbki: kartki anulowane odrzucone, kartki ławki zostają - jak w próbkach;
SETTLE `drop_bench_cards` je odrzuca).

## Pomiar (`measure_referee_effect.py measure`)

Metodologia jak `count_stretch_2026-10-17.md`: centrum = replay centrum
liczników SHEET mecz po meczu na historii z `data/refit_2026-10-17/sofa_replay.db`
(tylko odczyt; `fit_count_stretch.walk`: ostatnie 10 wartości, korekta rywala
B15, K rynku, stawka ligi, blend z ratingiem gdzie rynek oceniany, księga z
siłą pucharów, `--live-rules`), razy zainstalowany GAME_STATE
(`cards_points_for`, `fouls_for`); faule 2. połowy dołożone z
`sofa_event_stats` (`extend_history`, 23 468 meczów). Wariant: centrum ×
cecha^beta. Beta: pseudo-NW Poissona (log-link, offset log centrum, zmienna
log cechy), K z siatki {2, 5, 10, 20, 40, 80} tą samą wiarygodnością - na
treningu. Metryka: log-loss NB liczby (alfa z `config/sofa_count_dispersion.json`
rynek × rozgrywka; połowy fauli nie mają tam alfy - alfa metodą momentów na
treningu, ta sama w obu wariantach), nowa - stara na wiersz, **×1e-4**,
95% bootstrap po meczach (2000, ziarno 0). Po krzywej: na liniach jak
Superbetu (kartki suma 2,5-6,5, strona 0,5-3,5; faule suma 20,5-25,5, strona
9,5-13,5, połowy 4,5-6,5 / 9,5-13,5) p NB OVER/UNDER przez krzywą izotoniczną
(rynek × kierunek × linia) dopasowaną na treningu tego samego wariantu.

### A: fit 2024-10-01..2025-12-31, test 2026-01-01..2026-10-16

| rynek | K | beta | NB wszystkie | NB n_ref >= 5 | po krzywej | po krzywej n_ref >= 5 | mecze (wsz. / n>=5) |
|---|---|---|---|---|---|---|---|
| cards_points_total | 5 | +0,404 | -28,6 [-35,8, -22,0] | -62,9 [-78,8, -47,1] | -14,5 [-18,7, -10,4] | -33,3 [-42,0, -24,6] | 32 094 / 13 994 |
| cards_points_for | 5 | +0,399 | -16,1 [-20,1, -12,4] | -35,4 [-44,0, -26,7] | -9,3 [-11,6, -7,1] | -20,2 [-25,0, -15,3] | 32 094 / 13 994 |
| fouls_total | 10 | +0,678 | -54,3 [-64,8, -44,4] | -115,3 [-136,8, -93,3] | -31,7 [-38,7, -25,0] | -67,6 [-81,7, -53,6] | 37 125 / 16 261 |
| fouls_for | 20 | +0,979 | -27,6 [-33,4, -21,9] | -59,1 [-71,2, -46,8] | -16,6 [-20,4, -12,8] | -37,6 [-45,2, -29,6] | 37 125 / 16 261 |
| fouls_1h_total | 10 | +0,651 | -43,9 [-58,2, -29,1] | -53,5 [-73,0, -32,9] | -1,4 [-16,8, +15,0] | -2,3 [-21,8, +18,7] | 15 999 / 11 730 |
| fouls_1h_for | 10 | +0,641 | -21,2 [-28,3, -13,9] | -25,8 [-35,5, -15,9] | -13,6 [-19,6, -7,4] | -18,1 [-25,9, -10,5] | 15 999 / 11 730 |
| fouls_2h_total | 5 | +0,634 | -67,0 [-83,6, -50,0] | -88,3 [-110,7, -67,6] | -37,7 [-53,2, -21,7] | -44,9 [-63,8, -25,6] | 15 995 / 11 726 |
| fouls_2h_for | 5 | +0,643 | -34,7 [-43,4, -25,9] | -46,1 [-57,9, -35,2] | -20,9 [-27,9, -13,7] | -27,8 [-36,5, -20,0] | 15 995 / 11 726 |

Wiersze testu z rekordem sędziego: kartki 15 025 / 32 094 meczów (46,8%),
faule 17 548 / 37 125 (47,3%), połowy fauli 12 464 / 15 999 (77,9%). Połowy
fauli mają w treningu A tylko 2 160 meczów (statystyki połów w cache'u od
2025), stąd słaba krzywa izotoniczna fouls_1h_total.

### B: fit 2026-01-01..2026-06-30, test 2026-07-01..2026-10-16

| rynek | K | beta | NB wszystkie | NB n_ref >= 5 | po krzywej | po krzywej n_ref >= 5 | mecze (wsz. / n>=5) |
|---|---|---|---|---|---|---|---|
| cards_points_total | 10 | +0,575 | -34,2 [-48,2, -19,7] | -70,3 [-101,6, -37,6] | -21,2 [-30,0, -12,3] | -41,7 [-61,3, -22,3] | 9 385 / 4 284 |
| cards_points_for | 10 | +0,569 | -19,7 [-27,4, -11,6] | -40,4 [-58,0, -22,5] | -13,2 [-18,0, -8,3] | -25,3 [-35,4, -14,8] | 9 385 / 4 284 |
| fouls_total | 10 | +0,748 | -39,9 [-56,5, -23,7] | -83,9 [-124,8, -43,1] | -26,4 [-38,3, -15,2] | -57,3 [-84,2, -30,8] | 14 840 / 5 683 |
| fouls_for | 10 | +0,729 | -21,6 [-30,2, -13,3] | -46,2 [-66,9, -25,2] | -15,4 [-21,3, -9,6] | -32,8 [-46,2, -19,0] | 14 840 / 5 683 |
| fouls_1h_total | 10 | +0,581 | -53,3 [-72,9, -32,8] | -68,6 [-99,5, -38,1] | -30,1 [-46,0, -14,4] | -38,1 [-61,5, -16,1] | 6 008 / 4 006 |
| fouls_1h_for | 10 | +0,570 | -25,8 [-35,3, -15,9] | -33,3 [-48,4, -18,2] | -19,2 [-26,8, -11,2] | -20,2 [-32,0, -9,2] | 6 008 / 4 006 |
| fouls_2h_total | 5 | +0,705 | -43,8 [-75,3, -9,9] | -57,5 [-105,3, -12,6] | -21,0 [-42,8, +1,3] | -32,8 [-62,3, -1,0] | 6 007 / 4 005 |
| fouls_2h_for | 5 | +0,705 | -23,0 [-38,7, -5,9] | -31,2 [-55,0, -8,6] | -20,2 [-30,3, -9,6] | -29,0 [-43,6, -14,1] | 6 007 / 4 005 |

**Surowy NB poniżej zera z przedziałem na wszystkich 8 rynkach w obu
podziałach.** Po krzywej poniżej zera wszędzie poza fouls_1h_total w A
(-1,4 [-16,8, +15,0]; cienki trening) i fouls_2h_total w B (-21,0 [-42,8,
+1,3]); na podzbiorze n_ref >= 5 oba te przypadki: A fouls_1h_total
-2,3 [-21,8, +18,7] (dotyka zera), B fouls_2h_total -32,8 [-62,3, -1,0].
Zysk jest ~2× większy na meczach z rekordem n_ref >= 5 - reszta wierszy nie
zmienia się (cecha 1).

Dla porównania: rozciągnięcie liczników (10-17) dało na stronach -3..-316 ×1e-4,
GAME_STATE dla `cards_points_for` -42,5 ×1e-4 (walk-forward). Sędzia na
kartkach jest tego samego rzędu co GAME_STATE.

Rozrzut mnożnika (test A, wiersze z n_ref >= 5, p10 / p90): kartki 0,932 /
1,056, faule 0,953 / 1,045, połowy fauli 0,951-0,959 / 1,040-1,048. Przy
centrum ~4,2 pkt kartkowych to ok. ±0,25 pkt - spójne z +0,43 pkt na 1 SD z
10-08 po skurczeniu.

### Kalibracja po krzywej, p >= 0,70 (test, wszystkie wiersze; średnia krzywej / realizacja)

| rynek | A stara (n) | A stara | A nowa (n) | A nowa | B stara (n) | B stara | B nowa (n) | B nowa |
|---|---|---|---|---|---|---|---|---|
| cards_points_total | 87 600 | 0,806 / 0,808 | 87 456 | 0,808 / 0,811 | 25 605 | 0,813 / 0,812 | 25 700 | 0,814 / 0,812 |
| cards_points_for | 153 627 | 0,836 / 0,838 | 152 006 | 0,838 / 0,841 | 45 158 | 0,839 / 0,838 | 46 376 | 0,836 / 0,836 |
| fouls_total | 105 161 | 0,813 / 0,812 | 105 260 | 0,816 / 0,816 | 41 007 | 0,808 / 0,816 | 40 782 | 0,813 / 0,821 |
| fouls_for | 162 081 | 0,799 / 0,797 | 168 222 | 0,797 / 0,794 | 63 859 | 0,799 / 0,798 | 63 698 | 0,801 / 0,799 |
| fouls_1h_total | 19 526 | 0,807 / 0,787 | 19 434 | 0,810 / 0,791 | 8 535 | 0,775 / 0,763 | 8 233 | 0,780 / 0,775 |
| fouls_1h_for | 31 203 | 0,765 / 0,769 | 28 098 | 0,775 / 0,779 | 11 122 | 0,775 / 0,765 | 12 012 | 0,770 / 0,761 |
| fouls_2h_total | 14 838 | 0,798 / 0,785 | 19 147 | 0,782 / 0,770 | 7 725 | 0,764 / 0,766 | 7 375 | 0,773 / 0,772 |
| fouls_2h_for | 26 210 | 0,766 / 0,780 | 26 588 | 0,771 / 0,780 | 10 936 | 0,772 / 0,781 | 11 649 | 0,769 / 0,775 |

Obie wersje są skalibrowane w paśmie p >= 0,70 równie dobrze (różnice
średniej i realizacji w granicach 1-2 pp, ten sam kierunek); zysk jest w
rozróżnianiu, nie w poziomie. Nogi wyceniane wyżej / niżej to te same pasma
- czy przebiją cenę Superbetu, **nie mierzone** (linie z historii, nie z
ofert).

## Pokrycie na żywo i kiedy Sofascore podaje sędziego

- `live --date`: wszystkie mecze piłkarskie dnia - sędzia przy RESOLVE
  2026-10-20: 20 / 177 (11%), 2026-10-19: 35 / 172 (20%).
- Tam, gdzie liczy się: zdarzenia z wierszami cards / fouls w `05_sheet.json`,
  sędzia przy RESOLVE (`02_fixtures.json`): 902 / 1 222 (73,8%) w
  2026-09-17..10-20. Ostatnie dni: 10-17 88 / 130, 10-18 92 / 123, 10-19
  20 / 26, 10-20 14 / 37. Nogi wydrukowane z kartkami / faulami: 10-18
  47 / 54, 10-19 6 / 9, 10-20 10 / 18. Sędziowie tych meczów prawie zawsze
  mają rekord: 236 z 245 znanych (10-17..10-20) ma n >= 5 meczów w historii.
- `announce` (2026-10-20 21:53Z, świeże `/event` 465 nadchodzących meczów 60
  rozgrywek z rynkami kartek / fauli, 10-21..10-24): sędzia znany 0-6 h przed
  startem 6 / 8, 6-24 h 16 / 28 (57%), 24-48 h 32 / 55 (58%), 48-72 h 0 / 83,
  > 72 h 0 / 291. **Sofascore podaje sędziego ok. 48 h przed meczem**, w
  części lig dopiero w dniu meczu.

## Zastrzeżenia

- Centrum to przybliżenie centrum SHEET (jak w pomiarze rozciągnięcia
  liczników: stawka ligi bieżąca, venue prior nieodtwarzany); oba warianty
  mają to samo centrum.
- Etykieta sędziego pochodzi ze stron pobranych po meczu, ale obsada jest
  faktem sprzed meczu - użycie jej dla przeszłych meczów to nie wyciek wyniku.
  Na żywo sędzia bywa nieznany przy SHEET (wyżej): wtedy mnożnik 1.
- Połowy fauli: alfa NB metodą momentów (tabela dyspersji nie ma połów); A ma
  cienki trening połów.
- Krzywe zainstalowane dopasowano bez tego terminu; włączenie zmienia p,
  które czytają.

## Wdrożenie (gotowe, WYŁĄCZONE)

- SHEET (`run_sheet.process_fixture`): po GAME_STATE i rozciągnięciu
  liczników, dla rynków z `config/sofa_referee_effect.json`; sędzia z
  `sofa_event_referee` albo z zapisanego `/event` (RESOLVE, FIXTURE_CHECK)
  - `referees.referee_for_event`; rekord z historii piłkarskiej SHEET-u ściśle
  przed cięciem dnia (`referees.fixture_reads`). Wiersz: `referee_rule`
  (`referee_v1`, każdy wiersz piłkarski - znacznik dla `rebuild_plan`) i na
  wierszach kartek / fauli `referee_read` (`APPLIED` z id, n, ratio,
  mnożnikiem; `NO_REFEREE` - mnożnik 1; `NO_REFEREE_RECORD` - sędzia bez
  rekordu, mnożnik 1); nota `REFEREE:`; `UNFITTED_CONSTANTS:
  MIN_LEAGUE_MATCHES`. Wyłączony = wiersze bajt w bajt (test, golden
  `test_off_identical_head`).
- `config/sofa_referee_effect.json`: wszystkie 8 rynków, beta / K z fitu
  2026-01-01..2026-10-16 (jak rozciągnięcie liczników - dojrzała księga):
  kartki suma / strona beta 0,595 / 0,592, K 10; faule suma / strona 0,716 /
  0,703, K 10; faule 1. połowy 0,639 / 0,627, K 10; 2. połowy 0,653 / 0,656,
  K 5.

Czego potrzeba przed włączeniem (decyzja operatora):

1. **Replay i refit**: `calibrate_from_cache.py` nie ma flagi sędziego - replay
   musiałby czytać etykiety (`referees.load_labels`) i prowadzić
   `RefereeBook` mecz po meczu jak `walk_reads` (czytaj przed dodaniem), potem
   mnożyć centrum kartek / fauli jak `--count-stretch`; dopiero na takim
   replayu przeliczyć krzywe piłkarskie. Nie podłączone (nie jest to prosty
   hak: replay nie ma dziś etykiet sędziów).
2. **Moment wyceny**: SHEET biegnie po RESOLVE; sędzia pojawia się ~48 h przed
   meczem, w części lig w dniu meczu. Żeby trafić, `rebuild_day.py` musiałby
   ponownie liczyć SHEET po FIXTURE_CHECK, gdy pojawi się sędzia (dziś
   `rebuild_plan` wymusza SHEET tylko na brak znacznika).
3. `sheet_config.SHEET_OPTIONAL_FILES` - dopisać `sofa_referee_effect.json`
   przy włączeniu (teraz celowo nie: zmieniłby `config_sha` dzisiejszych
   arkuszy).
4. Etykiety bieżące: nowe mecze sędziów trafiają do tabeli przez `/event`
   (RESOLVE / FIXTURE_CHECK, `detail`) i przez ponowny backfill
   (`backfill_referees.py --max-minutes 20`; strona 0 sędziego nie jest
   odświeżana automatycznie - do dopisania przy włączeniu).

## Rekomendacja

Efekt sędziego jest realny i stabilny poza próbą na wszystkich 8 rynkach
(oba podziały, przedziały poniżej zera), dwukrotnie większy tam, gdzie sędzia
ma >= 5 meczów rekordu, a w ligach z rynkami kartek Superbetu sędzia jest
znany dla ~86% meczów po fakcie i ~74% przy RESOLVE. Rekomenduję włączenie
po (1) replayu z terminem i refitcie krzywych piłkarskich oraz (2) ponownym
SHEET po pojawieniu się sędziego. To poprawka kalibracji / rozróżniania;
czy przebija cenę - niemierzone.
