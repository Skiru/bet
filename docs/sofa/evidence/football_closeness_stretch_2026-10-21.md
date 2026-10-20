# Wyrównanie meczu w licznikach piłki (closeness stretch), 2026-10-21

Przełącznik: `epochs.FOOTBALL_CLOSENESS_STRETCH_FROM_UTC` (`closeness_stretch_v1`,
**`None` = wyłączony**; datę wybiera sesja główna). Moduł:
`bet.sofa.closeness_stretch` (arytmetyka i gramatyka pliku z
`bet.sofa.supremacy_stretch`, postać "sumy"). Współczynniki:
`config/sofa_closeness_stretch.json` (pisze `scripts/sofa/fit_closeness_stretch.py`,
domyślnie dry-run; fit 2026-01-01..2026-10-20, `fitted_from`). Znacznik wiersza:
`closeness_rule` (każdy wiersz piłki), notatka `CLOSENESS_STRETCH`. Replay:
`calibrate_from_cache.py --closeness-stretch` (`prepare_refit.py
rebuild-cache-rows --closeness-stretch`) - **refit krzywych po włączeniu powinien
nieść tę flagę**. Literatura: `literature_football_counts.md` pomysły 3 i 4
(Buraimo, Forrest, Simmons 2010: odwrócone U kartek; Yip i in. 2021: dyspersja
rożnych zależna od |s|).

## Poprawka

centrum x exp(g1 |s| + g2 s^2), s = oczekiwana różnica goli gospodarza z księgi
goli ratingu (`FootballForecast.supremacy`, przycięta do +-3, `MAX_SUPREMACY`,
niedopasowane); |s| i s^2 są takie same dla obu stron, więc rynek strony czyta to
samo s co suma. Po GAME_STATE, venue prior i rozciągnięciu liczników; beta
GAME_STATE (`cards_points_for` -0,0664 s) zostaje, g dopasowane na żywym centrum
z tą betą w offsecie.

| rynek | postać | g1 | g2 | mnożnik przy \|s\| = 1 / 2 / 3 |
|---|---|---|---|---|
| cards_points_for | \|s\| + s^2 | +0,0170 | -0,0526 | 0,965 / 0,838 / 0,655 |
| cards_points_total | \|s\| + s^2 | +0,0177 | -0,0492 | 0,969 / 0,851 / 0,677 |
| shots_total | \|s\| | +0,0147 | 0 | 1,015 / 1,030 / 1,045 |
| shots_1h_total | \|s\| | +0,0163 | 0 | 1,016 / 1,033 / 1,050 |

Kartki: mniej w meczu rozstrzygniętym (zgodnie z literaturą), strzały: więcej w
meczu nierównym. Kontrola na kubełkach (realizacja / żywe centrum, 2026):
`cards_points_total` |s| 0-0,25: 1,011, 1-1,5: 0,937, 2-2,5: 0,863, 2,5-3: 0,716
(model 0,994 / 0,942 / 0,896 / 0,868 dla postaci |s|, stąd s^2).

## Pomiar

Replay centrum liczników SHEET mecz po meczu (`fit_count_stretch.walk`: ostatnie
10 wartości, korekta rywala B15, K rynku, stawka ligi, blend z ratingiem gdzie
rynek jest oceniany, księga z siłą pucharów; reguły na żywo 2026-10-20) x
GAME_STATE / rozciągnięcie liczników tam, gdzie rynek je ma. Wiersze od
2025-08-01, historia `data/cache/football_history.pkl` z 2026-10-20 (kopia,
tylko odczyt). Log-loss NB z zainstalowaną alfą ligi
(`config/sofa_count_dispersion.json`; `shots_total` znormalizowany rozkład
normalny jak w SHEET), nowe - stare, x1e-4 na wiersz, bootstrap meczów (1000).
- WF: walk-forward miesięczny 2026-01..10 (fit na wszystkim przed miesiącem);
- przed 2026 -> 2026: fit 2025-08..12, test 2026-01-01..10-19;
- H1 -> 07..: fit 2026-01..06, test 2026-07-01..10-19;
- "krzywa": p na liniach, które Superbet kwotuje (linie z SHEET 10-18..10-20, p
  starego modelu 0,03-0,97), oba kierunki, przez zainstalowane krzywe (linia ->
  kierunek -> rynek -> pula piłki, punkt `realised`), binarny log-loss;
  "&ge;0,70": to samo tylko na nogach z krzywą &ge; 0,70 (stara albo nowa) - obszar
  druku.

Reguła przyjęcia: WF z przedziałem poniżej zera, żaden test stały istotnie gorszy
(NB ani krzywa), krzywa na obu testach średnio nie gorsza, obszar &ge; 0,70 nie
gorszy.

### Przyjęte

| rynek | postać | WF NB | <2026 NB | <2026 krzywa | <2026 &ge;0,70 | H1 NB | H1 krzywa | H1 &ge;0,70 | mecze |
|---|---|---|---|---|---|---|---|---|---|
| cards_points_for | \|s\|+s^2 | -23,4 [-29,5; -17,7] | -21,6 [-26,2; -16,3] | -6,8 [-9,5; -4,3] | -14,4 [-18,2; -10,5] | -9,1 [-24,6; +4,9] | +0,0 [-6,3; +7,1] | -4,8 [-16,5; +6,9] | 51 423 |
| cards_points_total | \|s\|+s^2 | -34,6 [-43,0; -24,7] | -31,7 [-40,2; -23,9] | -10,6 [-13,8; -7,4] | -17,3 [-22,5; -12,4] | -11,7 [-33,5; +12,5] | -4,9 [-13,3; +3,4] | -5,5 [-21,0; +10,5] | 51 423 |
| shots_total | \|s\| | -11,2 [-15,5; -6,8] | -12,9 [-19,4; -7,1] | +0,5 [-1,7; +2,6] | -2,4 [-6,0; +1,6] | -19,1 [-23,6; -14,8] | -3,8 [-5,6; -1,8] | -8,7 [-12,0; -5,4] | 47 827 |
| shots_1h_total | \|s\| | -7,5 [-12,0; -3,1] | -8,5 [-13,8; -3,1] | -0,0 [-5,4; +5,8] | -6,2 [-14,1; +1,0] | -13,2 [-18,3; -7,7] | -3,8 [-10,2; +2,7] | -5,1 [-14,7; +4,1] | 24 091 |

s^2 kontra samo |s| (WF, nowe - stare): `cards_points_total` -11,2 [-17,8; -4,7],
`cards_points_for` -6,9 [-11,3; -2,8] - przyjęte; `shots_total` +1,0 [-0,3; +2,1],
`shots_1h_total` +3,4 [+0,3; +6,8] - zostaje |s|. (Zlecenie mówiło "sumy: tylko
|s|"; dla sumy kartek s^2 wygrał na każdym teście, więc wzięty.)

Miesiące WF (x1e-4): `cards_points_total` |s| ujemny w 9 z 10 miesięcy (09: +23);
`shots_total` dodatni 01-03 (+27, +12, +9), ujemny 04-10 (-4..-40) - efekt
strzałów jest słabszy zimą (inny miks lig), średnio na plus.

Kalibracja na nogach &ge; 0,70 przez starą krzywą (średnia pewność / realizacja):
`cards_points_total` H1 0,845/0,845 -> 0,848/0,845 (-0,3 pp), `cards_points_for`
H1 0,850/0,851 -> 0,852/0,850 (-0,2 pp), `shots_total` H1 0,829/0,823 ->
0,829/0,823, `shots_1h_total` H1 0,774/0,746 -> 0,774/0,747 - przesunięcie w
obszarze druku w granicach 0,3 pp (przed 2026 na kartkach w drugą stronę).

### Odrzucone (zmierzone)

- `fouls_for` / `fouls_total`: przed 2026 lepiej (-6,6 / -10,0), ale fit H1 na
  2026-07.. istotnie gorszy (NB +11,7 [+3,3; +20,0] / +33,8 [+21,4; +46,1];
  `fouls_total` krzywa +14,5 [+9,2; +19,9]); miesiące WF od 2026-08 dodatnie.
  Zależność fauli od |s| nie jest stabilna (zgodnie z 10-17: "zysk przed 2026 nie
  utrzymał się").
- `corners_total`: WF -10,1 [-14,8; -5,7], ale po krzywej zero (+0,1 [-1,7; +2,0] /
  -1,7 [-4,6; +1,0]; &ge;0,70 +1,2 / -0,2) - krzywa kubełkowa to wchłania.
- `corners_1h_total`: po krzywej gorzej (+6,6 [+4,4; +8,7], +5,2 [+1,9; +8,9]).
- `corners_for`, `shots_for`, `shots_1h_for`, `shots_on_target_for`,
  `offsides_for` (strona, na GAME_STATE / rozciągnięciu liczników): |s| bez zysku
  (WF -2,3..+1,4, krzywa 0..+5,5).
- `shots_on_target_total`: ma już g1 |s| w rozciągnięciu liczników; dodatkowe |s|
  zero (WF +0,5 [-0,3; +1,3]).
- `offsides_total`: zero (WF -0,0 [-0,3; +0,2]).
- `fouls_1h_for` / `fouls_1h_total`: brak alfy w pliku dyspersji (SHEET liczy
  wariancję z próbki), alfa MLE rynku = podłoga 1e-4 - pomiar nie odtwarza SHEET;
  H1 i tak istotnie gorszy. Połowy `shots_2h` / `fouls_2h` (2-4 wiersze dziennie)
  nie mierzone (wymagają skanu `sofa_event_stats`).

### Dyspersja zależna od |s| (pomysł 4) - odrzucona

alpha = alpha_ligi x exp(d |s|), jedno d na rynek (MLE NB na treningu). NB lepiej
na stronach: `shots_for` WF -44,6 [-52,3; -37,4] (d -0,42), `shots_1h_for` -40,2
(d -0,59), `shots_on_target_for` -10,7 (d -0,38), `offsides_for` -3,5 (d -0,26),
`corners_for` -4,2 (d -0,16); sumy zero albo gorzej. Krzywa na wszystkich
liniach też lepsza (np. `shots_1h_for` -7,0 / -11,6), **ale w obszarze druku
(&ge; 0,70) gorzej**: `shots_1h_for` H1 +14,4 [+6,9; +21,2], `shots_on_target_for`
+5,8 [+3,0; +8,5], `offsides_for` +4,3 [+1,9; +6,8], `corners_for` +2,5 [+0,9;
+4,2], `shots_for` +3,2 [-1,1; +7,5]; pewność na nogach &ge; 0,70 przechodzi z
lekkiego niedoszacowania w przeszacowanie (`shots_1h_for` H1 0,839/0,833 ->
0,846/0,828). Wymaga krzywych dopasowanych na replayu z tą dyspersją - nie
wdrożone. Kandydat do pomiaru razem z refitem.

## E2E (kopia dni 10-19 / 10-20 w scratchu, kod z worktree)

SHEET w procesie (historia z kopii pickla, `SOFA_NOW` = zegar ostatniego
CONFIDENCE: 10-19 11:12:35Z, 10-20 06:57:56Z), wyłączony vs włączony, potem
CONFIDENCE na każdej kopii. Pliki MAIN nietknięte (md5 `05_sheet.json` /
`08_confidence.json` / `11_coupon.json` przed i po).

- 10-20 wyłączony = prawdziwy `05_sheet.json`: `p_central` równe na 50 109 /
  50 109 wspólnych wierszach (różnica zbioru wierszy: oferta odświeżona po SHEET).
  `config_sha` zmienia się samą obecnością pliku (`SHEET_OPTIONAL_FILES`, jak
  pliki rozciągnięć) - wiersze poza tym bajt w bajt.
- Wyłączony vs włączony, SHEET: poza czterema rynkami i łącznikami kartek
  wszystkie wiersze identyczne (10-19: 33 490, 10-20: 49 367). Ruszone: 10-19 704
  wiersze (cards_points_for 202, cards_points_total 214, shots_total 246,
  shots_1h_total 42) + łączniki kartek 157 (`both_over_` 76, `most_` 63,
  `handicap_` 18 - czytają centra stron); 10-20 654 + 207. Centrum kartek x0,655
  (|s| = 3) .. x1,002, strzałów x1,001 .. x1,050; |dp| do 0,25. Wiersze znikające
  / dochodzące tylko na kartkach (linie poza rozdzielczością modelu po przesunięciu
  centrum: 10-19 -2, 10-20 -22 / +6).
- CONFIDENCE, single drukowane: 10-19 1 867 -> 1 868 (+3 / -2, 4 zmienione,
  średnio -0,45 pp), 10-20 2 476 -> 2 472 (+3 / -7, 5 zmienionych, +1,36 pp);
  żadna noga spoza czterech rynków. Buildery: 10-19 jeden kandydat mniej
  (16653122 bez nogi `cards_points_total` 1,5 OVER), 10-20 bez zmian.
- Rozliczone 10-19: nowe 3/3 wygrane, odpadłe 2/2 wygrane - N za małe na
  wniosek. 10-20 jeszcze nierozliczony.
- Uwaga: CONFIDENCE na kopii czyta line evidence z worktree (HEAD), nie poranne
  odświeżenie z MAIN, więc wyłączony nie odtwarza dokładnie prawdziwych pewności
  10-20 - porównanie wył./wł. jest na tym samym configu.

## Zastrzeżenia

- Łączniki kartek (`both_over_cards_points`, `handicap_cards_points`,
  `most_cards_points`) ruszają się przez centra stron; nie były mierzone osobno
  (mierzone były brzegi).
- Krzywe zostają z refitu 2026-10-17 (bez tego członu); test "po krzywej"
  sprawdza właśnie to połączenie. Refit po włączeniu: z `--closeness-stretch`.
- Nie mierzone: czy nogi przebiją cenę Superbetu.
- Skrypty pomiaru (tylko odczyt) i wyniki:
  `/private/tmp/claude-501/-Users-mkoziol-projects-bet/903bccad-c2ff-46fb-9191-12f8ef2c9866/scratchpad/closeness/`
  (`a_walk.py`, `b_analyse.py`, `c_month.py`, `d_bins.py`, `e_g2_vs_g1.py`,
  `results_final.json`, `e2e_*.py`).
