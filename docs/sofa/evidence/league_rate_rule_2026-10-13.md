# A2: rozgrywki bez własnej stawki i sparingi (audyt 2026-10-13, decyzja O1)

Przełącznik: `epochs.LEAGUE_RATE_RULE_FROM_UTC` (`league_rate_strict_v1`).
Skrypt: `scripts/sofa/measure_league_rate_rule.py` (tylko odczyt).

## Rejestracja (zapisana 2026-10-13 przed uruchomieniem pomiaru)

Reguła (O1): sparing / przedsezon w hokeju, koszykówce i siatkówce odrzucany
tą samą regułą co `FRIENDLY_FIXTURE` w piłce (`comparability.is_friendly_event`);
rozgrywki z mniej niż `MIN_LEAGUE_MATCHES` (30) meczami nie dostają średniej
wszystkich lig: w sportach `NO_LEAGUE_RATE` (brak p, odmowa), w piłce brak
połowy ratingu w centrum (notatka `NO_LEAGUE_RATE`, centrum z próbki). Bez
fallbacku do ligi macierzystej.

### Test S (sporty: hokej, koszykówka, siatkówka)

- Populacja: rozliczone linie Superbetu 2026-09-29..2026-10-12
  (`data/line_evidence/rows_before_2026-10-13/<sport>_superbet_settled.jsonl`,
  p modelu zbudowanego ściśle przed dniem, stara reguła) w meczach, które
  reguła odrzuca: sparing / przedsezon (`is_friendly_event` na zdarzeniu z
  bazy) albo rozgrywki z `book.leagues[(comp, metryka)].n < 30` w modelu
  as-of dnia. Kontrola: pozostałe mecze tych samych dni.
- Metryka główna: kalibracja nóg „do druku”: pewność = zainstalowana krzywa
  sportu dla dnia (`sport_confidence.calibration_path_for`) odczytana przez
  obecne line evidence (`run_sport_confidence.read_confidence`, z ceną linii),
  nogi z pewnością >= 0,70 i pewność x kurs >= 0,90; realizacja minus średnia
  pewność, 95% przedział z bootstrapu po meczach (2000 losowań, ziarno 0).
- Próg (O5): reguła włączona, gdy górna granica 95% w populacji odrzucanej
  < 0 (te nogi obiecują więcej, niż realizują). Dodatkowo raportowane: ROI
  tych nóg po kursie Superbetu z przedziałem i to samo dla kontroli.
- Zastrzeżenie zapisane z góry: line evidence z 10-13 było dopasowane na tych
  samych dniach (w próbie dla offsetów) - to obniża pewność, więc działa na
  korzyść hipotezy zerowej.

### Test F (piłka)

- Populacja: historia z cache'u (`football_rating.load_history`), mecze
  2025-08-01..2026-10-12 nie-sparingowe, w których rozgrywki miały
  `leagues[(comp, metryka)].n < 30` w chwili meczu (rating one step ahead),
  obie strony z >= 5 meczami w ratingu i >= 5 wartościami w ostatnich 10.
  Metryki bazowe rynków z ratingiem (bez `UNRATED_MARKETS`).
- Centrum A (stara reguła) = 0,5 x rating ze stawką globalną + 0,5 x średnia
  ostatnich 10 strony; centrum B (nowa) = średnia ostatnich 10 (przybliżenie
  centrum z próbki: bez priora K, to samo w A i B).
- Metryka: MSE centrum na stronę; różnica SE_A - SE_B, 95% z bootstrapu po
  meczach (2000, ziarno 0), łącznie i per metryka.
- Próg (O5): część piłkarska włączona, gdy dolna granica łącznej różnicy > 0
  (B lepsze). Gdy nie - część piłkarska zostaje wyłączona osobnym
  rozwiązaniem w kodzie, sporty idą według testu S.

## Wynik (2026-10-13, `data/audit_2026-10-13/a2_*.json`)

### Test S (sporty), linie 2026-09-29..2026-10-12

Mecze odrzucane przez regułę: koszykówka 39 (w tym 27 sparingów /
przedsezonów), siatkówka 19, hokej 0. Nogi „do druku” (pewność >= 0,70,
pewność x kurs >= 0,90):

| sport | grupa | linie | mecze | realizacja - pewność, pp [95%] | ROI [95%] |
|---|---|---|---|---|---|
| hockey | refused | 0 | 0 | - | - |
| hockey | kept | 4213 | 853 | -1.0 [-2.6; +0.6] | -5.3% [-7.2; -3.3] |
| basketball | refused | 8 | 8 | -3.1 [-38.4; +22.8] | +17.2% [-36.9; +61.5] |
| basketball | kept | 341 | 166 | -2.5 [-10.0; +5.2] | +11.9% [-2.4; +26.2] |
| volleyball | refused | 9 | 8 | +11.3 [-12.8; +23.6] | +15.4% [-18.5; +32.0] |
| volleyball | kept | 204 | 175 | -1.5 [-7.8; +4.1] | -3.7% [-11.9; +3.5] |

**Próg O5 niespełniony**: w populacji odrzucanej jest 17 nóg w 16 meczach,
górna granica przedziału > 0 w obu sportach. Pomiar nie rozstrzyga - nie
dowodzi ani szkody, ani zysku.

**Decyzja: przełącznik `LEAGUE_RATE_RULE_FROM_UTC` = 2026-10-14 00:00Z na
podstawie decyzji operatora O1** (odmowa sparingu / przedsezonu tą samą regułą
co `FRIENDLY_FIXTURE`, `NO_LEAGUE_RATE` dla rozgrywek bez stawki), nie na
podstawie O5. To korekta poprawności (CLAUDE.md „Changing the pipeline” 2):
przedsezon NBA był wyceniany średnią wszystkich lig (82,8 pkt na stronę wobec
118 / 112 NBA; noga 10-10 z `forecast_p` 0,9998). Na wiosnę/przy nowych
rozgrywkach populacja odrzucana będzie większa niż w tym oknie.

### Test F (piłka), historia 2025-08-01..2026-10-12, one step ahead

Łącznie SE_stara - SE_nowa na stronę: **-0.581 [-0.621; -0.543]**
(65550 stron) - stara reguła (rating ze stawką globalną w połowie
centrum) jest **lepsza** niż sama próbka w cienkich rozgrywkach.

| metryka | mecze | strony | MSE stara | MSE nowa | różnica [95%] |
|---|---|---|---|---|---|
| cards_points_for | 1033 | 2066 | 2.988 | 3.174 | -0.186 [-0.241; -0.132] |
| corners_1h_for | 519 | 1038 | 3.066 | 3.459 | -0.393 [-0.489; -0.304] |
| corners_2h_for | 519 | 1038 | 4.045 | 4.468 | -0.423 [-0.521; -0.318] |
| corners_for | 1938 | 3876 | 7.953 | 8.875 | -0.922 [-1.048; -0.797] |
| fouls_1h_for | 522 | 1044 | 5.942 | 6.339 | -0.397 [-0.550; -0.251] |
| fouls_for | 1583 | 3166 | 17.584 | 18.876 | -1.292 [-1.599; -0.990] |
| goals_1h_for | 6442 | 12906 | 1.008 | 1.137 | -0.130 [-0.141; -0.118] |
| goals_2h_for | 6476 | 12976 | 1.229 | 1.393 | -0.164 [-0.178; -0.150] |
| goals_for | 8424 | 16876 | 3.239 | 3.780 | -0.540 [-0.582; -0.498] |
| offsides_for | 1712 | 3424 | 2.565 | 2.823 | -0.258 [-0.295; -0.219] |
| shots_1h_for | 521 | 1042 | 9.536 | 10.893 | -1.357 [-1.654; -1.066] |
| shots_for | 995 | 1990 | 26.689 | 31.896 | -5.207 [-5.952; -4.492] |
| shots_on_target_1h_for | 518 | 1036 | 2.555 | 2.756 | -0.201 [-0.267; -0.139] |
| shots_on_target_for | 1536 | 3072 | 6.956 | 7.921 | -0.965 [-1.108; -0.829] |

Każda metryka tego samego znaku. **Część piłkarska: zmierzone, nie włączone**
(`FOOTBALL_LEAGUE_RATE_RULE_FROM_UTC` = None). Zastrzeżenie: centrum z próbki
przybliżone średnią ostatnich 10 bez priora K (tak samo w obu wariantach).
