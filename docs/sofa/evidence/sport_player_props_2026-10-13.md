# Linie zawodników (hokej, koszykówka): próbka modelu i komórka pasma ceny (2026-10-13)

Zlecenie nocne 2026-10-13 po weryfikacji dnia 2026-10-13. Weryfikator dał
WATCH na nogach hokejowych `player_pp_points` UNDER: (a) Carlson, Palmieri,
McTavish - model zawodnika oparty na 5-6 meczach w nowej drużynie; (b)
Fantilli, Schaefer - `forecast_p` 0,807 (0,007 nad krawędzią kubełka 0,800),
więc pewność 0,7231 to dolna granica Wilsona kubełka 0,800-0,825 klucza bez
krzywej (`sb:hockey:player_pp_points|UNDER`, 87 linii), zrealizowanego
głównie na liniach 1,00-1,30, a podana nogom po 1,43-1,65, gdzie ten zakres p
zrealizował ok. 0,60. Dwie podejrzenia, mierzone tylko do odczytu.

Pomiar: `scripts/sofa/measure_sport_player_props.py` (tylko odczyt:
`data/sofa.db` w trybie `mode=ro`, `runs/` i `data/line_evidence/` tylko
czytane; nie dotyka `config/`). Bez przełącznika, bez zmiany potoku, bez
mostu.

## Stan dziś (sprawdzony w kodzie 2026-10-13)

- `player_model.line_probability` (`src/bet/sofa/player_model.py:735`): próbka
  własna zawodnika (`own_sample`) to jego występy w meczach z listingów
  **dwóch dzisiejszych drużyn** (`load_appearances`, 60 najnowszych meczów
  każdej, bez sparingów), z limitem `max_sample` 60; poniżej
  `MIN_APPEARANCES` = 5 (stała niedopasowana, w `UNFITTED`) brak p
  (`THIN_SAMPLE`). Rozmiar próbki to `model_n` na wierszu. Zawodnik po
  transferze ma więc w próbce tylko mecze w nowej drużynie, a jego mecze w
  starej nie istnieją dla modelu. Kurczenie do puli (`prior_games` hokej 1,0,
  koszykówka 2,0) jest jedyną ochroną cienkiej próbki.
- Linie zawodników nie mają krzywej historii; pewność to
  `line_evidence.LineEvidence.read` z `base=None`: dolna granica Wilsona
  kubełka p klucza (n i k podzielone przez efekt projektu kubełka od
  10-14), potem ograniczenie pasmem ceny (`band_cell`,
  `src/bet/sofa/line_evidence.py`). Kolejność komórek pasma: (klucz, pasmo,
  kubełek p) z >= 20 liniami; inaczej **(klucz, pasmo, kubełek p i wszystkie
  wyższe)**; inaczej (v2) poszerzanie w dół - ale suma nadal obejmuje
  wszystkie kubełki powyżej; potem to samo dla całego sportu (`*`); na końcu
  klucz we wszystkich pasmach od kubełka w górę. Ograniczenie działa tylko,
  gdy górna granica Wilsona komórki jest pod pewnością.
- Przykład z 2026-10-13 (plik dowodów w drzewie roboczym, dopasowany rano):
  `player_pp_points|UNDER` w paśmie 1,30-1,60, kubełek 0,800-0,825: 14 linii
  (< 20), więc komórka "od kubełka w górę" = 45 linii, 33 trafione (0,733),
  Wilson górny ok. 0,84 > 0,7231 - brak ograniczenia. Ten sam klucz i pasmo,
  kubełek 0,750-0,800: 73 linie, 44 trafione (0,60). Te liczby to motywacja
  (weryfikator już je widział), nie test - test niżej jest walk-forward i
  obejmuje wszystkie klucze bez krzywej.

Przed rejestracją widziałem tylko liczności (bez wyników): linii z
`model_p >= 0,70`, `model_n < 10`: hokej 105, koszykówka 56; `10-19`: 31 / 19;
`>= 20`: 1 049 / 105.

## Rejestracja (zapisana 2026-10-13 PRZED uruchomieniem pomiaru)

### Dane

- Linie zawodników: `runs/sofa/shadow/{hockey,basketball}/<d>/settled.json`,
  dni 2026-09-29..2026-10-12 (10-13 nierozliczony), każda oceniona strona
  rynku `player_*` z `model_source == "pregame"`, `model_p` nie None,
  `outcome` WIN / LOSS, z kursem. Mecz = `s:<d>:<superbet_event_id>` (jak
  `fit_line_evidence.player_rows`).
- Pozostałe klucze sportów mierzonych (tylko pytanie 2, część wtórna):
  `data/line_evidence/rows_before_2026-10-13/<sport>_superbet_settled.jsonl`
  przez `fit_line_evidence.sport_rows` z krzywymi, które czyta dany dzień
  (`sport_confidence.calibration_path_for`); "bez krzywej" = `base` None.
  Zastrzeżenie: p tych wierszy pochodzi z modelu dopasowanego przed 10-13
  (lekkie zajrzenie w przód w p, nie w wyniki).
- Sporty nigdy nie są sumowane; hokej i koszykówka osobno.

### Bootstrap

Po meczach (wszystkie linie meczu razem), 2000 powtórzeń, ziarno 0,
przedział percentylowy 95%. Kontrast liczony w każdej próbce bootstrapowej z
tej samej próby meczów.

### Pytanie 1: czy rozmiar próbki modelu przewiduje błąd kalibracji

Zmienne na linię:
- `n_team` = `model_n` (mecze z listingów obu dzisiejszych drużyn, limit 60);
- `n_all` = występy zawodnika (`has_played`, ten sam sport, dowolna drużyna i
  rozgrywka, bez sparingów `is_friendly_event`) w 365 dniach przed
  `kickoff_utc`, z `sofa_event_stats.lineups_json` (identyfikator zawodnika
  `model_player_id`);
- `n_other` = te z `n_all`, w których grał dla innej drużyny niż ta z jego
  najnowszego występu przed meczem;
- `moved` = `n_other >= 10` i `n_team < 20` ("nowa drużyna").

Populacja P1: linie z `model_p >= 0,70`. Metryka: luka = średnia
(`y - model_p`) (zrealizowane minus p modelu).

- **K1**: luka(`n_team < 10`) minus luka(`n_team >= 10`).
- **K2**: luka(`moved`) minus luka(reszta).
- Opisowo: luka w przedziałach `n_team` 5-9, 10-19, 20-39, 40-60 oraz
  `moved` x `n_team < 10`.

Próg (per sport): podejrzenie potwierdzone, gdy przedział 95% kontrastu leży
całkiem poniżej zera **i** grupa cienka ma >= 100 linii i >= 30 meczów.
Mniej - "n za małe, brak werdyktu" (liczby i tak podane).

Reguła kandydat **R1** (`MIN_GAMES_WITH_TEAM` = 10): linia z `n_team < 10`
bez p (NO_LINE_EVIDENCE). Oceniana w walk-forward W (niżej) na nogach, które
drukowałyby się dziś: R1 warto proponować tylko, gdy (a) K1 potwierdzone,
(b) nogi usunięte przez R1 mają lukę (zrealizowane minus pewność) z
przedziałem < 0, (c) ROI(usunięte) minus ROI(zostawione) ma przedział < 0.
Inaczej nie (reguła operatora: nie wycinamy tego, co nie wypadło gorzej).

### Pytanie 2: czy kubełek klucza bez krzywej realizuje inaczej w zależności od pasma ceny

Populacja P2: linie kluczy bez krzywej z `p >= 0,70` - (a) linie zawodników
hokej / koszykówka (główna), (b) pozostałe klucze bez krzywej czterech
sportów (wtórna).

- **M2**: w warstwach (sport, klucz, kubełek p z `line_evidence.EDGES`)
  zrealizowane w paśmie >= 1,30 minus zrealizowane w paśmie 1,00-1,30,
  średnia ważona `w = n_lo x n_hi / (n_lo + n_hi)` (styl Cochran-Mantel-
  Haenszel); tylko warstwy z liniami w obu grupach pasm. Opisowo: luka
  (`y - p`) per pasmo.
- Próg: różnica pasm potwierdzona, gdy przedział M2 < 0 (wyższe pasmo przy
  tym samym kubełku realizuje mniej) i >= 30 meczów w paśmie >= 1,30.

**Walk-forward W** (to samo dla R1 i R2): dla każdego dnia testowego d od
2026-10-02 do 2026-10-12 dowody dopasowane `line_evidence.fit` na wierszach
dni < d (linie zawodników + wiersze sportów, jak poranny
`fit_line_evidence.py --sport-rows-dir`), linie dnia d czytane
`LineEvidence(doc, v2=True, bucket_deff=True).read` (reguły od 10-14).
"Drukowałaby się": pewność >= 0,70, pewność x kurs >= 0,90, `overround` <=
0,15 (gdy jest na wierszu). Brak bram startu / świeżości / czytań.

Reguła kandydat **R2** ("pasmo poszerzane tylko w dół"): każda komórka
pasma i komórka "klucz we wszystkich pasmach" sumuje kubełki od `lower` do
kubełka p **włącznie, nigdy wyżej** (komórka dokładna, potem poszerzanie w
dół do 0,70 w paśmie; to samo dla `*`; na końcu klucz we wszystkich pasmach
od kubełka w dół). Reszta reguły bez zmian (ograniczenie tylko, gdy Wilson
górny komórki < pewność, do zrealizowanej stopy komórki).

R2 warto proponować tylko, gdy (a) M2 potwierdzone dla danego sportu (linie
zawodników), (b) nogi, które R2 usuwa (spadek pod bramy), mają lukę z
przedziałem < 0 i ROI(usunięte) minus ROI(zostawione) z przedziałem < 0,
(c) usunięte nogi pochodzą z >= 30 meczów. Inaczej nie.

Raportowane w W per sport i wariant (obecna, R1, R2): nogi, mecze, średnia
pewność, zrealizowane, luka i ROI z przedziałami, plus usunięte / obniżone.

## Odstępstwa od rejestracji (zapisane przed odczytem wyników K2)

- **`n_other` z boku meczu, nie z `teamId`.** Pierwszy przebieg liczył
  drużynę występu z `teamId` wpisu w `lineups_json` i dał `n_other` = 0 dla
  każdej linii (K2 puste). Diagnoza: `teamId` wpisu to drużyna zawodnika w
  chwili pobrania boxu, nie ta, w której grał. Przykład: zawodnik 1147200
  (linia 2026-10-03 Dallas - St. Louis) - 85 występów w 365 dniach, wszystkie
  w meczach Anaheim (3675), każdy wpis z `teamId` 3695 (St. Louis, jego nowa
  drużyna). Pomiar liczy teraz drużynę z boku (home / away) wydarzenia;
  `teamId` trzymany osobno jako `n_mislabelled`. Definicja `moved` bez zmian.
- **Pierwszy dzień testowy W to 2026-10-03**, nie 10-02: 10-02 nie ma linii
  zawodników z liczbą pregame (wszystkie 1 908 to `model_source: settle`).
- **W czyta linie wszystkich czterech sportów** (R2 dotyka też kluczy z
  krzywą i kluczy bez krzywej siatkówki / CS2), raport per sport i klasa
  (`player` / `other` bez krzywej / `curve`).
- Dodane eksploracyjnie (nie rejestrowane, nie werdykt): kontrast
  `n_mislabelled >= 5` vs reszta i skład grupy cienkiej.

## Wyniki (uruchomione 2026-10-13 ok. 22:15 lokalnie)

Dane: 12 428 linii zawodników pregame 2026-09-29..2026-10-12; z `p >= 0,70`:
hokej 1 185 linii / 68 meczów, koszykówka 180 / 42. Wszystkie liczby:
`docs/sofa/evidence/sport_player_props_2026-10-13.json`. Przedziały: bootstrap
po meczach, 2000, ziarno 0.

### Pytanie 1: rozmiar próbki modelu

| sport | grupa | linie / mecze | luka (y - p) [95%] |
|---|---|---|---|
| hokej | `n_team < 10` | 105 / 32 | -14,7 pp [-27,1; -3,8] |
| hokej | `n_team >= 10` | 1 080 / 68 | -3,7 pp [-7,1; -0,1] |
| hokej | **K1** różnica | | **-11,0 pp [-23,6; -0,2]** |
| hokej | `moved` | 97 / 31 | -17,2 pp [-29,4; -6,0] |
| hokej | **K2** różnica | | **-13,6 pp [-26,6; -2,5]** |
| koszykówka | `n_team < 10` | 56 / 27 | -16,5 pp [-28,7; -3,4] |
| koszykówka | `n_team >= 10` | 124 / 35 | -13,5 pp [-26,1; -1,7] |
| koszykówka | K1 różnica | | -3,0 pp [-20,5; +15,5] |
| koszykówka | K2 różnica (`moved` 71 / 28) | | +3,3 pp [-14,4; +20,4] |

Hokej według `n_team`: 5-9 -14,7 pp (105 linii), 10-19 -5,5 [-14,7; +4,8]
(31), 20-39 +1,7 [-4,8; +7,3] (159), 40-60 -4,6 [-8,2; -0,8] (890).

Skład grupy cienkiej (hokej, 105 linii, 26 zawodników): 86 linii to
zawodnicy `moved` (zmienili drużynę), 88 ma >= 5 występów z cudzym `teamId`
(21 z 26 zawodników), tylko 17 linii to zawodnicy z < 20 występami w ogóle.
Cienka, ale nie `moved`: 19 linii / 11 meczów, -4,1 pp [-31,8; +15,1].
Koszykówka: 53 z 56 cienkich linii to `moved`.

Werdykt (próg z rejestracji):
- **Hokej: POTWIERDZONE** - K1 poniżej zera (górna granica -0,2 pp, na
  styk), grupa cienka 105 linii / 32 mecze (próg 100 / 30, na styk). K2 też
  poniżej zera. Cienka próbka w hokeju to w praktyce zawodnik po transferze.
- **Koszykówka: n za małe** (56 linii < 100) - brak werdyktu; i tak różnicy
  nie widać, bo cała koszykówka przy `p >= 0,70` jest ok. 14 pp nad
  realizacją, cienka czy nie.
- **R1 (`MIN_GAMES_WITH_TEAM` 10): nie do oceny, nie proponowane.** W
  walk-forward drukowałoby się tylko 26 nóg zawodników hokejowych (15
  meczów); R1 usuwa 5 nóg z 5 meczów: luka -14,9 pp [-57,2; +27,3], ROI
  -19,2% [-74,8; +36,4], ROI usunięte - zostawione -17,5 pp [-92,1; +27,2].
  Warunki (b) i (c) nie są spełnione - przy tej liczbie nie mogą być.
  Koszykówka: zero nóg zawodników drukowałoby się w W.

Mechanizm (sprawdzony w kodzie i bazie, nie liczba z testu): model czyta
tylko listingi dwóch dzisiejszych drużyn (`load_appearances`), więc po
transferze widzi kilka meczów w nowej drużynie, a mecze w starej nie istnieją
(z założenia). Do tego `appearances_from_lineups`
(`src/bet/sofa/player_model.py:283`) przypisuje występ po `teamId` wpisu,
który jest drużyną z chwili pobrania - mecz starej drużyny **przeciw** nowej
trafia do próbki nowej drużyny. Przykłady 2026-10-13 (`player_model.jsonl`):
Carlson `model_n` 5 przy 85 występach w 365 dniach (52 Washington, 28
Anaheim, 5 w nowej), McTavish 6 przy 88 (83 Anaheim, 5 w nowej), Palmieri
5 przy 27 - wszystkie w tej samej drużynie (to nie transfer; mało meczów w
oknie 60 meczów drużyny). Kurczenie do puli jest słabe (`prior_games` hokej
1,0 gry). Uwaga: przypisanie po `teamId` to błąd mapowania (mecz Anaheim
liczony jako mecz St. Louis), choć mały liczbowo - do decyzji, czy naprawić
jako korektę poprawności (zmienia to, co drukuje).

### Pytanie 2: kubełek bez krzywej a pasmo ceny

M2 (zrealizowane w paśmie >= 1,30 minus 1,00-1,30 w tej samej warstwie
sport x klucz x kubełek p, `p >= 0,70`):

| populacja | warstwy | linie lo / hi | mecze hi | M2 [95%] | werdykt |
|---|---|---|---|---|---|
| hokej, zawodnicy | 19 | 634 / 428 | 67 | **-13,8 pp [-20,3; -6,1]** | potwierdzone |
| koszykówka, zawodnicy | 4 | 10 / 13 | 41 | +4,1 pp [-31,3; +47,2] | n za małe (10 linii lo) |
| hokej, inne bez krzywej | 6 | 37 / 36 | 32 | -12,0 pp [-35,0; +8,5] | niepotwierdzone |
| koszykówka, inne bez krzywej | 10 | 96 / 423 | 197 | -17,6 pp [-35,7; -1,1] | potwierdzone |
| siatkówka, inne bez krzywej | 11 | 120 / 123 | 77 | -15,9 pp [-28,5; -4,1] | potwierdzone |
| CS2, inne bez krzywej | 12 | 844 / 169 | 61 | -18,4 pp [-29,3; -7,0] | potwierdzone |

Luka (y - p) per pasmo, linie zawodników hokeja: 1,00-1,30 +0,6 pp [-2,8;
+3,9] (640 linii, p 0,850); 1,30-1,60 -10,5 [-15,4; -5,1] (428, p 0,757);
1,60-2,20 -11,6 [-20,2; -3,3] (113, p 0,745). Ten sam wzór w każdym sporcie:
pasmo 1,00-1,30 skalibrowane, od 1,30 realizacja o 8-21 pp pod p.

Werdykt M2: **różnica pasm potwierdzona** dla zawodników hokeja i kluczy
bez krzywej koszykówki, siatkówki i CS2: przy tym samym kubełku p linia w
wyższym paśmie realizuje o 14-18 pp mniej. Kubełek bez krzywej (Wilson ze
wszystkich pasm) jest więc w większości zbudowany z linii 1,00-1,30, a
komórka pasma "od kubełka w górę" dokłada wyższe kubełki tego pasma i potrafi
nie dać ograniczenia nodze z niższego kubełka (przypadek Fantilli /
Schaefer).

**R2 w walk-forward (10-03..10-12)**:

| sport, klasa | nogi obecnie (mecze) | R2 usuwa (mecze) | luka usuniętych | ROI usuniętych | ROI usunięte - zostawione |
|---|---|---|---|---|---|
| hokej, zawodnicy | 26 (15) | 4 (4) | -23,8 pp [-73,8; +26,2] | -30,5% [-100; +39] | -30,1 pp [-109,4; +38,9] |
| CS2, inne bez krzywej | 54 (23) | 0 | - | - | - |
| koszykówka / siatkówka / hokej, inne bez krzywej | 0 / 0 / 1 | 0 | - | - | - |
| koszykówka, z krzywą | 409 (169) | 66 (50) | -11,0 pp [-26,7; +1,6] | +4,7% [-22,3; +27,2] | +5,7 pp [-20,4; +28,2] |
| hokej, z krzywą | 2 553 (618) | 38 (36) | -9,2 pp [-24,5; +4,4] | -6,2% [-28,6; +14,8] | +0,2 pp [-23,4; +21,0] |
| siatkówka, z krzywą | 119 (91) | 5 (3) | -18,4 pp [-79,8; +27,1] | +0,2% | +9,3 pp [-90,0; +82,8] |
| CS2, z krzywą | 56 (22) | 0 | - | - | - |

Werdykt R2: **nie proponowane**. Dla kluczy bez krzywej warunek (c) (>= 30
meczów usuniętych) nie jest spełniony - w W reguła obecna (Wilson kubełka +
dzisiejsze ograniczenie) prawie nie drukuje nóg zawodników ani innych kluczy
bez krzywej, więc R2 ma czego usuwać tylko 4 nogi. Dla kluczy z krzywą R2
usuwa nogi, które realizowały pod pewnością (bez przedziału pod zerem), ale
nie wypadły gorzej w pieniądzach (ROI usuniętych minus zostawionych +5,7 i
+0,2 pp, przedziały przez zero) - ten sam wzór co odrzucone 2026-10-12
ostrzejsze ograniczenie pasma.

Odtworzenie nóg z 2026-10-13 (plik dowodów z rana, reguły v2): R2 obniża
Fantilliego (p 0,8069, 1,43) i Schaefera (p 0,8068, 1,51) z 0,7231 do 0,5977
(komórka 1,30-1,60, kubełki 0,750-0,825: 87 linii, 52 trafione) - nie
drukowałyby się. Carlson (1,65, pasmo 1,60-2,20) bez zmiany; McTavish i
Palmieri (p 0,97, 1,16 / 1,28, pasmo 1,00-1,30) bez zmiany - ich problem to
pytanie 1, nie pasmo.

### Podsumowanie

- Oba podejrzenia weryfikatora mają pokrycie w danych: w hokeju linie
  zawodników z cienką próbką (w praktyce po transferze) realizują ok. 11 pp
  gorzej niż reszta (na granicy progu), a kubełek bez krzywej realizuje w
  pasmach >= 1,30 o 14-18 pp mniej niż w 1,00-1,30 (wyraźnie, w trzech
  sportach poza hokejem też).
- Żadna reguła nie przechodzi progu walk-forward: nóg, które dziś
  drukowałyby się z tych komórek, jest w 10 dniach za mało (26 nóg
  zawodników hokeja, 0 koszykówki), a na kluczach z krzywą R2 usuwa nogi,
  które nie były gorsze w pieniądzach. Bez przełącznika.
- Do decyzji operatora (nie test): przypisanie występu po boku meczu zamiast
  `teamId` w `player_model.appearances_from_lineups` (błąd mapowania; zmienia
  to, co drukuje, więc pod przełącznikiem); WATCH na nogach zawodników z
  `model_n < 10` jako odczyt analityka (nie bramka) do czasu nowych danych.
- Ponowny pomiar R1 / R2, gdy W będzie miał >= 30 meczów usuniętych nóg
  (ten sam skrypt, `--to` późniejszy).
