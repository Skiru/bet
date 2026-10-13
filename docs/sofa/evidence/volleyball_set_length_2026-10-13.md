# B9 / C10 / C9: siatkówka - długość seta i rynki setowe (audyt 2026-10-13)

Pozycje audytu `docs/sofa/history/AUDYT_RYNKOW_KONTEKST_2026-10-13.md`:
B9 (`points_total`, `points_handicap`: mecze o 4-6 pkt za krótkie), C10
("set na przewagi" zaniżony, 9,7% wobec 12,3% M - zależy od B9), C9 (rynki
setowe 744 / 782 / 781 / 100077 bez krzywej historii; decyzja operatora O3:
wracają po B9 i pomiarze poza próbą, przez przełącznik).

## Diagnoza sprawdzona w kodzie (przed rejestracją)

- `src/bet/sofa/score_model.py:788` `_volleyball`: każda akcja seta z tym
  samym p (udział punktów z ratingu, plus szok meczu `vb_match_sd` 0,03);
  `SimParams.vb_set_sd = 0.0` (`:358`), `SimParams.vb_sideout = 0.0` (`:364`).
  Długość seta (punkty przegranego) wynika wyłącznie z tego p - model nie ma
  żadnego parametru, który ustawiałby długość niezależnie od udziału.
- `src/bet/sofa/sport_confidence.py:213` `HISTORY_MARKETS["volleyball"]` bez
  744 / 782 / 781 / 100077; `:215` `PERIODS` bez siatkówki (więc
  `market_periods` zwraca `()` dla rynku setowego); `:217`
  `SETTLED_ONLY_FAMILIES` - te rodziny tylko z rozliczonych linii Superbetu.
  Zainstalowana krzywa siatkówki (`config/sofa_sport_confidence_calibration.json`,
  fitted_from before 2026-10-07): `set_points_total|*`, `set_extra_points|*`,
  `set_points_odd_even|*` - `NO_FIT_BUCKET_WITH_N>=200`.
- Diagnostyka audytu (`vb_iid.py`) była **w próbie** (udział zrealizowany w
  tym samym meczu). Side-out 0,6-0,7 nie zamyka luki (M 158,4-160,4 wobec
  165,8) i psuje P(5 setów) - dlatego nie side-out.

Przed rejestracją obejrzałem tylko: liczbę meczów w historii per miesiąc
(gęsta od 2024-09; 23 357 meczów, K 16 385 / M 6 972) i liczbę rozliczonych
linii Superbetu per rodzina (09-29..10-12: `points_total` 978 linii / 353
mecze, `points_handicap` 678 / 195, `set_winner` 2 040 / 417,
`set_points_total` 850 / 356, `set_points_odd_even` 864 / 409,
`set_extra_points` 50 / 25). Żadnej statystyki wynik - model.

## Model B9 (kalibrator długości seta, Część 5 (b); zapisany przed pomiarem)

Przełącznik `epochs.VB_SET_LENGTH_FROM_UTC` (domyślnie `None` - model bajt w
bajt dzisiejszy). Na żywo (SPORT_CONFIDENCE), w replayu line evidence
(`settled_shadow_rows`) i w replayu historii fitu
(`fit_sport_confidence --vb-set-length`).

- **Kto wygrywa set - bez zmian.** Symulacja akcji (`_volleyball`) rozstrzyga
  zwycięzcę każdego seta jak dziś, tym samym strumieniem liczb losowych.
  Zwycięzca meczu, `sets_total`, `set_handicap`, `exact_sets`, `set_winner`
  są więc identyczne co do bitu (test).
- **Ile punktów ma przegrany seta - z tabeli.** Osobny generator (ziarno
  pochodne od ziarna symulacji) losuje punkty przegranego `L` z empirycznego
  rozkładu komórki; wynik seta: zwycięzca `target` przy `L <= target - 2`,
  inaczej `L + 2` (przewagi). `target` 25, w 5. secie 15.
- **Tabela** (`score_model.SetLengthTable`, budowana w `build_model`) z meczów
  siatkówki z ostatnich 365 dni przed cięciem modelu, one step ahead: udział
  `s = eh / (eh + ea)` z książki ratingu **przed** aktualizacją tym meczem
  (mecz bez oczekiwania - pominięty). Faworyt = strona z `s >= 0,5`, luka
  `g = |s - 0,5|`. Mecz wchodzi, gdy ma 3-5 setów i każdy set ma format
  25 / 15 (zwycięzca = target i przegrany <= target - 2, albo zwycięzca >
  target i różnica 2); inaczej mecz pominięty w tabeli.
- **Komórka:** płeć (`FootballResult.women`) x rodzaj seta (zwykły / 5.) x
  czy set wygrał faworyt x przedział luki (5 przedziałów: kwintyle `g` meczów
  okna - granice z samego predyktora, bez wyniku). Komórka z < 200 setami
  -> ta sama bez przedziału luki -> płeć x rodzaj -> brak (set zostaje z
  wynikiem symulacji akcji).
- Płeć meczu w symulacji: z mapy drużyna -> płeć z historii przed cięciem
  (`ScoreModel.women_of`; drużyna z prognozą ma zawsze historię, bo
  `MIN_TEAM_MATCHES`).
- Liga **nie** jest w komórce (C19 - tempo ligi - to osobna pozycja).
- Stałe wybrane, nie dopasowane (`UNFITTED_CONSTANTS`): okno 365 dni,
  5 przedziałów, minimum 200 setów.

## Pomiar (`scripts/sofa/measure_volleyball_set_length.py`, tylko odczyt)

Historia z kopii bazy `data/refit_2026-10-13/sofa_replay.db`
(`score_model.load_events`, zapisana do `data/audit_2026-10-13/volleyball_events.pkl`).

**Test A - historia, walk-forward 2025-10-01..2026-10-13.** Model (książka,
tabela) budowany z meczów sprzed cięcia co 30 dni (`REBUILD_DAYS`), między
przebudowami książka aktualizowana mecz po meczu; mecze o tym samym starcie
prognozowane przed nauką któregokolwiek. Co n-ty mecz, do 6 000; 2 000
symulacji na mecz; stary i nowy model z tym samym ziarnem. Linie stałe, z
meczów 2024-10-01..2025-10-01 (przed oknem), osobno dla płci, kwantyle 10 /
25 / 50 / 75 / 90% (podłoga + 0,5):
- `points_total` (230060): suma punktów meczu, strona OVER;
- `points_handicap` (1069): różnica gospodarz - gość, strona T1 przy
  handicapie `-c`;
- `set_points_total` (782): suma punktów seta (kwantyle setów zwykłych),
  każdy set 1-5, p warunkowe na rozegraniu seta (jak rozlicza Superbet);
- `set_extra_points` (100077): YES, każdy set 1-5.
p linii przez `line_probability` (semantyka rozliczenia), przycięte do
`[0,5/(n+1); 1 - 0,5/(n+1)]`. Metryka: log-loss na mecz (średnia po liniach
rodziny), różnica nowa - stara, 95% bootstrap po meczach (2 000, ziarno 0).
Obok: Brier, kalibracja linii z p >= 0,70 (średnie p / realizacja), średnia
symulowana suma punktów vs realna per płeć, częstość setów na przewagi per
płeć, maks. |Δp| rynków wyniku (zwycięzca, sety, handicap setowy, dokładny
wynik, zwycięzca seta).

**Test B - linie Superbetu** 2026-09-29..2026-10-12
(`runs/sofa/shadow/volleyball/<d>/settled.json`, jak `settled_shadow_rows`:
model na 00:00Z dnia, cena nigdy wejściem p): te same rodziny plus
`points_odd_even`, `set_points_odd_even`, `set_winner`; log-loss p modelu
(nie krzywej) nowa - stara, w parach, bootstrap po meczach.

## Próg B9 / C10 (zapisany z góry)

1. **B9:** test A, `points_total` **i** `points_handicap`: górna granica 95%
   różnicy log-loss < 0.
2. **Strażnik B9:** test B, `points_total` i `points_handicap`: przedział nie
   leży w całości powyżej zera (nie gorzej).
3. **Strażnik konstrukcji:** maks. |Δp| rynków wyniku = 0 (test A i B).
4. **C10:** test A, `set_extra_points`: górna granica 95% < 0 (ten sam
   przełącznik co B9 - to ten sam mechanizm).
5. Raportowane, nie rozstrzygają: Brier, kalibracja, `set_points_total`,
   parzystości.

Spełnione 1-3 -> próg O5 spełniony; ale p `points_*` i rynków setowych się
zmienia, więc krzywa siatkówki musi być dopasowana na tym estymatorze:
refit na kopii (`fit_sport_confidence.py --sport volleyball --before
2026-10-13 --dry-run --vb-set-length`, `data/refit_2026-10-13/vb_b9/`) i
bazowy na tym samym kodzie (`vb_base/`), compare w parach: log-loss pewności
na wspólnych liniach holdoutu historii i na liniach Superbetu, luka linii
drukowalnych. **Konfiguracji nie instaluję; przełącznik zostaje `None`** -
instalacja krzywej i ustawienie przełącznika to decyzja sesji nadrzędnej.
Niespełnione -> kod zostaje jako wyłączona opcja, bez refitu.

## C9 - rynki setowe z historii (zapisane z góry; tylko gdy B9 spełnione)

Przełącznik `epochs.VB_SET_HISTORY_FROM_UTC` (domyślnie `None`): fit dla dnia
>= przełącznika (albo flaga `--vb-set-history`) dodaje do wierszy historii
siatkówki 744 / 782 / 781 / 100077 na setach 1-5 (`PERIODS["volleyball"]`),
a te rodziny przestają być `SETTLED_ONLY`. Na żywo nic poza krzywą (klucze
czyta się tak samo). Pomiar na fitach `vb_b9_c9/` (`--vb-set-length
--vb-set-history`):

1. klucz setowy przechodzi własną regułę dopuszczenia F6 (`scf.admission`:
   holdout historii i linie Superbetu);
2. umiejętność: na rozliczonych liniach Superbetu rodzin setowych p modelu
   ma log-loss niższy niż 0,5 (moneta; linia Superbetu stoi w okolicy
   środka), górna granica 95% (bootstrap po meczach) < 0;
3. linie drukowalne (pewność >= 0,70) rodzin setowych na Superbecie, gdy
   >= 30 meczów: realizacja - pewność, dolna granica 95% >= -0,03
   (`MAX_OVERSTATEMENT`); mniej meczów - raportowane jako nierozstrzygające.

Spełnione 1-3 dla klucza -> klucz gotowy do krzywej; przełącznik i
instalacja - jak B9, decyzja sesji nadrzędnej (to ta sama instalacja krzywej
siatkówki). Niespełnione -> `None`.

## Wynik

Pomiar wykonany `measure_volleyball_set_length.py` (historia z
`data/audit_2026-10-13/volleyball_events.pkl`; test A: 5 050 meczów, 2 000
symulacji, 2025-10-01..2026-10-13; test B: 449 meczów Superbetu 09-29..10-12).
Różnice nowa - stara, log-loss na mecz, 95% bootstrap po meczach.

**Test A (historia, walk-forward):**

| rodzina | log-loss nowa - stara |
|---|---|
| `points_total` | +0,00248 [-0,00045, +0,00538] |
| `points_handicap` | -0,00110 [-0,00358, +0,00132] |
| `set_extra_points` (C10) | -0,00039 [-0,00141, +0,00069] |
| `set_points_total` (raport.) | -0,00699 [-0,00876, -0,00521] |

Średnia suma punktów meczu (symulacja stara / nowa / realna): M 165,2 / 171,4 /
166,3; K 160,9 / 163,6 / 161,1. Sety na przewagi M 10,1% / 13,1% / 13,2%,
K 9,4% / 10,3% / 10,4%. Maks. |Δp| rynków wyniku (zwycięzca, sety, handicap
setowy, dokładny wynik, zwycięzca seta) = 0 w obu testach (strażnik
konstrukcji spełniony).

**Test B (449 meczów Superbetu):** `points_total` +0,00304 [-0,01087,
+0,01644]; `points_handicap` +0,01477 [-0,00170, +0,03258]; `set_extra_points`
(30 linii / 15 meczów) +0,01119 [-0,0205, +0,0332]; `set_points_total`
-0,00122 [-0,01644, +0,01462]. Strażnik 2 (przedział nie w całości > 0)
spełniony.

**Werdykt wg progu:** warunek 1 (górna granica < 0 dla `points_total` ORAZ
`points_handicap`) **niespełniony** - `points_total` jest nominalnie gorszy,
`points_handicap` przedział obejmuje zero; warunek 4 (C10) niespełniony.
Mechanizm poprawia poziom (średnie i częstość przewag zgodne z realem), ale
nie rozdzielczość linii: w historii dawniej stara symulacja nie miała
błędu poziomu 4-6 pkt (165,2 wobec 166,3), co audyt w próbie pokazał inaczej.
**Przełączniki `VB_SET_LENGTH_FROM_UTC` i `VB_SET_HISTORY_FROM_UTC` zostają
`None`; refitu nie robiono; C9 nie mierzone** (zależy od spełnionego B9;
kod C9 jest wyłączoną opcją `--vb-set-history`). Do rozważenia przy
nowych danych: tabela po lidze (C19) albo tylko dla `set_points_total`
(-0,0070 [-0,0088, -0,0052] - ale to rodzina rozliczana tylko z linii
Superbetu, bez własnej rejestracji; nie zmieniam progu po fakcie).
