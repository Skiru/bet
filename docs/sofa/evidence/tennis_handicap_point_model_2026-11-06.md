# Tenis: handicap gemów z modelu punktowego - pomiar 2026-11-06

Polecenie operatora 2026-11-06: "puść, niech się liczy". **Tylko pomiar:**
nic nie jest podłączone, żaden przełącznik, żadna instalacja, żaden plik
`config/` nie zmieniony, baza czytana tylko do odczytu (`mode=ro`), sieć nie
pytana.

## 0. Reguły zapisane PRZED obejrzeniem wyników (pre-rejestracja)

Ta sekcja powstała, zanim skrypt `scripts/sofa/measure_tennis_handicap_point_model.py`
policzył cokolwiek na liniach Superbetu.

**Model.** `bet.sofa.tennis_point_model` dokładnie w wersji z 11-05 (stałe
wybrane na historii sprzed 2026-01-01, kod niezmieniony): prognoza meczu z
walk-forward (stan sprzed startu), 4 000 symulacji punkt po punkcie, ziarno =
id meczu. Nowy jest tylko odczyt (`bet.sofa.tennis_handicap_point`): "X (L)"
wygrywa, gdy gemy X - gemy rywala + L > 0 (cały mecz; konwencja pipeline'u:
super tie-break decydujący = jeden gem), a dla `handicap_games_won_set1/2` ta
sama różnica w secie 1 / 2 (set 2 zawsze rozegrany w best of three). Linie
.5 - remisu nie ma.

**Rodziny:** (A) `handicap_games` (mecz), (B) `handicap_games_won_set1` +
`handicap_games_won_set2` razem ("handicap w secie").

**Superbet:** wiersze `sofa_settled_row` (to, co SETTLE pisze do
`07_settled.json`), `run_date` 2026-10-20 .. 2026-11-05, WIN / LOSS. Para
linii = (zawodnik A, L) i (zawodnik B, -L) tego samego meczu, obie z kursem;
p bez marży = (1/kA) / (1/kA + 1/kB); para z sumą odwrotności poza [1.00,
1.30] odrzucona. Jedna para = jeden wiersz do Briera, zorientowany na stronę z
linią ujemną (dający gemy); nogi = obie strony. Best of five, mecze spoza
historii i niezgodne strony (02_fixtures vs historia) - odrzucone i
policzone. Dni 09-18..10-19 (dev) liczone tylko do wyłapania błędów
mapowania (strona, znak linii); hold-out 10-20..11-05 liczony **raz**.

**Obecny estymator:** `p_central` wiersza (SHEET, przed krzywą: sąsiedzi
ratingu). Po krzywej: zainstalowana krzywa `handicap_games|OVER`
(`config/sofa_confidence_calibration.json`, `realised_lo95` kubełka;
kobiety - sekcja `by_class.tennis_women`, a gdy jej brak - brak krzywej).
Per set: obecny estymator nie ma krzywej (tylko dowód linii), więc "po
krzywej" dla niego = brak.

**Krzywe modelu:** dopasowane w katalogu roboczym
(`data/refit_2026-11-06_point_handicap_models/`), nie w `config/`, dokładnie
jak `fit_tennis_point_curves.py`: walk-forward 2026-01-01 .. 2026-10-20,
mecze best of three ukończone, wszystkie z historią (statystyki serwisu i
20 000 losowych bez nich, ziarno 11), linie .5 z p w [0.10, 0.90], obie
strony; `EDGES` / `MIN_MARKET_BUCKET` 400 / `MIN_THIN_BUCKET` 100 z
`fit_confidence`, pewność = `realised_lo95` (Wilson). Bez dowodu linii w obu
ramionach (dowód linii jest dopasowywany na tych samych liniach - w próbie).

**Miary na hold-oucie (przedziały 95%, bootstrap po meczach, 2 000):**
1. Brier (i log-loss) model - cena bez marży, model - obecny.
2. Nogi: trafione - p przy p >= 0.70 i przy 0.60-0.70; osobno dla p surowego
   i dla pewności po krzywej, każde ramię na własnym zbiorze nóg.
3. ROI po kursie Superbetu dla nóg >= 0.70 z x = p x kurs >= 0.90, przed i
   po podatku 12% (zwrot 0.88 x kurs) - tylko raport, nie kryterium.

**Historia (bez cen):** walk-forward 2026-01-01 .. 2026-10-16 (koniec replayu
10-17) na wierszach replayu obecnego estymatora (`run_date =
cache-calibration`, `handicap_games`, baza replayu 10-17
`data/refit_2026-10-17/sofa_replay.db`, tylko do odczytu); na mecz jedna
linia: strona gospodarza, linia z p obecnego najbliżej 0.5 (reguła z 10-26 /
11-05); do 15 000 losowych meczów (ziarno 5). Brier / log-loss nowy - obecny,
kalibracja >= 0.70.

**Werdykt per rodzina (miara operatora):**
- *tak dobry jak cena*: górna granica Brier(model) - Brier(cena) <= +0.002;
- *bez nad-obietnicy po krzywej*: przy pewności >= 0.70 górna granica
  (trafione - pewność) >= 0 (przedział obejmuje zero lub jest nad nim), przy
  >= 30 nogach;
- *lepszy od obecnego*: górna granica Brier(model) - Brier(obecny) < 0.

## 1. Populacja

- **Superbet:** pary linii `handicap_games` i `handicap_games_won_set1/2`
  z `sofa_settled_row` (WIN / LOSS, obie strony z kursem, marża w
  [1.00, 1.30]): wczytane 19 135 par 09-18 .. 11-05 (dev 10 086);
  odrzucone (cały zakres): nie-para 2 739 linii, brak ceny 501, brak meczu w
  historii modelu 1 121 (pickle historii z 11-05 18:00 - mecze po nim nie są
  w historii; dev tylko 57, więc to głównie 11-05 hold-outu), rozbieżność
  stron 13, podmiot nierozpoznany 3, ocena sprzeczna z wynikiem 4.
- **Krzywe:** 53 235 meczów walk-forward 2026-01-01 .. 10-20, 3 186 012
  wierszy linii.
- **Historia:** 15 000 meczów (replay 10-17 jako obecny).

## 2. Historia bez cen (handicap_games, 15 000 meczów)

Brier nowy 0.2459, obecny 0.2491: **-0.0033 [-0.0051, -0.0015]**; log-loss
-0.0060 [-0.0101, -0.0022]. Kalibracja surowego p modelu na liniach
historii: >= 0.70 -9.2 pp [-11.6, -6.9] (n 1 525), 0.60-0.70 -5.2 pp - stąd
krzywe. (Obecny na linii najbliżej 0.5 nie ma nóg >= 0.60 - kalibracji
obecnego nie da się tu porównać.)

## 3. Superbet - hold-out 2026-10-20 .. 11-05 (liczony raz)

| rodzina | pary / mecze | model - cena | obecny - cena | model - obecny (Brier) | model - obecny (log-loss) |
|---|---|---|---|---|---|
| handicap_games | 5 809 / 1 688 | +0.0067 [+0.0026, +0.0106] | +0.0107 [+0.0060, +0.0155] | -0.0040 [-0.0097, +0.0015] | -0.0090 [-0.0216, +0.0033] |
| per-set (set1 + set2) | 2 167 / 586 | +0.0030 [-0.0006, +0.0070] | +0.0145 [+0.0061, +0.0226] | **-0.0114 [-0.0185, -0.0040]** | **-0.0311 [-0.0486, -0.0124]** |

Trafione - deklarowane (pp), ROI przy x >= 0.90 przed / po podatku 12%:

| rodzina | wariant | pasmo | n / mecze | dekl. | trafione - dekl. | ROI | po podatku |
|---|---|---|---|---|---|---|---|
| handicap_games | model surowy | >= 0.70 | 1 026 / 639 | 0.770 | -6.9 [-10.4, -3.6] | -5.8 | -17.1 |
| handicap_games | **model po krzywej** | >= 0.70 | 1 020 / 639 | 0.781 | **-8.0 [-11.4, -4.7]** | -5.6 | -16.9 |
| handicap_games | model po krzywej | 0.60-0.70 | 1 782 / 1 312 | 0.656 | -6.3 [-8.7, -3.9] | -5.6 | -16.9 |
| handicap_games | obecny surowy | >= 0.70 | 1 278 / 767 | 0.766 | -7.6 [-10.7, -4.6] | -3.3 | -14.9 |
| handicap_games | **obecny po krzywej** | >= 0.70 | 818 / 489 | 0.766 | **-6.8 [-10.7, -3.1]** | -5.7 | -17.0 |
| handicap_games | obecny po krzywej | 0.60-0.70 | 1 166 / 807 | 0.647 | -7.8 [-10.8, -4.7] | -10.1 | -20.9 |
| per-set | model surowy | >= 0.70 | 1 193 / 456 | 0.796 | -0.8 [-3.6, +1.9] | -3.3 | -14.9 |
| per-set | **model po krzywej** | >= 0.70 | 1 152 / 456 | 0.792 | **-1.0 [-3.8, +1.8]** | -2.9 | -14.6 |
| per-set | model po krzywej | 0.60-0.70 | 627 / 310 | 0.652 | -1.7 [-5.4, +2.1] | -10.1 | -20.8 |
| per-set | obecny surowy (sąsiedzi, bez krzywej) | >= 0.70 | 1 407 / 510 | 0.806 | -6.7 [-9.6, -3.9] | -5.5 | -16.8 |
| per-set | obecny surowy | 0.60-0.70 | 502 / 298 | 0.654 | -0.4 [-4.6, +3.6] | -0.1 | -12.1 |

## 4. Werdykt

**Reguła zamrożona (sekcja 0):** żadna rodzina nie jest "tak dobra jak
cena" (handicap_games +0.0067, per-set górna granica +0.0070 > +0.002).
Per-set: bez nad-obietnicy po krzywej (-1.0 pp, CI przez 0) i lepszy od
obecnego (Brier CI < 0). handicap_games: nad-obietnica -8.0 pp i nie lepszy
od obecnego (CI przez 0).

**Reguła operatora 2026-11-06** (przekazana przez koordynatora, po
hold-oucie, wiąże wszystko): instalować to, co lepsze od OBECNEGO estymatora;
pobicie ceny nie jest wymagane (podawane jako fakt). Rodzina przechodzi, gdy
(a) Brier lub log-loss modelu jest punktowo lepszy od obecnego i (b)
kalibracja >= 0.70 po krzywej nie jest gorsza od obecnej o więcej niż 1 pp.
- **per-set (`handicap_games_won_set1/2`): przechodzi** - Brier -0.0114,
  kalibracja -1.0 pp wobec -6.7 pp obecnego. **Podłączone od 2026-11-06 17:30Z** (pierwotnie 11-07 00:00Z; przesunięte przez operatora).
- **`handicap_games`: nie przechodzi** - (a) tak (Brier -0.0040, log-loss
  -0.0090 punktowo), (b) nie: -8.0 pp wobec -6.8 pp obecnego łańcucha, gorzej
  o 1.2 pp (> 1 pp). Zostaje na obecnym estymatorze (sąsiedzi ratingu +
  krzywa). Granica jest wąska (0.2 pp ponad tolerancję) - to fakt, nie powód
  do jej przesuwania.

**Gdzie model zawodzi:** pełny handicap meczu przeszacowuje przy wysokim p
(-8 pp po krzywej) - tak jak obecny; krzywa z historii nie naprawia tego na
liniach Superbetu (podniosła 0.770 -> 0.781). Cena jest lepsza od modelu w
obu rodzinach.

## 5. Podłączenie i E2E

- Przełącznik `epochs.TENNIS_HANDICAP_POINT_MODEL` od **2026-11-06 17:30Z**
  według zegara budowy (operator przesunął z 11-07 00:00Z: „WŁĄCZ JAK
  NAJWIĘCEJ RZECZY OD DZISIAJ"; 11-06 mieszany, grupa „11-06 mieszany")
  (wymaga też `TENNIS_POINT_MODEL`); marker wiersza
  `tennis_handicap_point_model_rule` - `rebuild_plan` przelicza SHEET dnia,
  którego wiersze tenisa go nie mają; krzywe handicapu tylko dla arkusza ze
  znacznikiem (`tennis_point_curves.handicap_rows_marked`); dowody z linii
  wierszy 11-06 tylko z backfillu. Potem grupa ledgera "od 11-07".
- SHEET: wiersze per-set handicapu są pochodne (`derived.price_derived_rungs`);
  pod przełącznikiem `rating_p` dla tych rynków czyta model punktowy
  (`run_sheet._point_model_rating_p` -> `tennis_point_sheet.PointPricer.p` ->
  `tennis_handicap_point.p_handicap`), notatka `TENNIS_POINT_MODEL: p ...`;
  wiersz bez p modelu = NOT_RATED, nigdy łączny rozkład prób ani sąsiedzi R2.
- CONFIDENCE: krzywe `config/sofa_tennis_handicap_point_curves.json`
  (dopasowane na historii, tylko set1 / set2) nakładane przez
  `tennis_point_curves.for_day` od dnia przełącznika; line evidence tych kluczy
  z p modelu (`data/line_evidence/tennis_handicap_point_model_p.json.gz`,
  11 646 linii 09-18..11-06, z historii z 11-05 18:00).
- `handicap_games` (cały mecz) **nie** podłączony.
- **E2E** (kopia 2026-11-05, SHEET `--event-ids` 52 mecze tenisa, przełącznik
  on vs off, oba exit 0): zmieniło się p wyłącznie w
  `handicap_games_won_set1` (324) i `_set2` (322), średnio |dp| 0.067; 648
  wierszy z notatką modelu, 4 wiersze mniej (p modelu poza rozdzielczością,
  OUTSIDE_MODEL_RESOLUTION 378 -> 382), 0 NOT_RATED; każdy inny rynek
  identyczny; marker na wszystkich 8 076 wierszach on, na żadnym off.
