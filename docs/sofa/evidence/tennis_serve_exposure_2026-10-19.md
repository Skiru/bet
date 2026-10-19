# Asy i podwójne błędy: ekspozycja, turniej, returnujący - wynik pomiaru 2026-10-19

Plan i reguła decyzji zamrożone przed pomiarem:
`tennis_serve_exposure_plan_2026-10-19.md` (z jednym jawnym odstępstwem -
odczyt pustego kubła krzywej, opisanym tam). Skrypt:
`scripts/sofa/measure_tennis_serve_exposure.py`; wyniki i log:
`data/measure_serve_exposure_2026-10-19/` (`replay.md`, `replay.json`;
`replay_v1_rawfallback.md` - przebieg sprzed poprawki harnessu).

Wszystkie przedziały: 95%, losowanie całych meczów.

## Werdykt

**Żaden wariant nie wchodzi do SHEET.** Na historii przeszły tylko asy w
setach (ekspozycja + turniej, z returnującym lub bez), ale na liniach
Superbetu 10-06..10-18 te same warianty nie są lepsze od obecnego środka
(log-loss -0.0006 [-0.0078, +0.0069]) i nogi, które by wydrukowały, zawyżają:
35 nóg / 15 meczów, pewność 0.742, trafione 0.629, luka -11.3 pp [-26.0, +4.4]
(bezpiecznik: nie gorzej niż -2 pp). Sprawdzian na nowych danych:
`T-TENNIS-ACES-SETS-EXPOSURE`.

## 1. Historia (replay, tylko TOUR, best-of-three, train 2024-07..2025-12, test 2026-01..10)

15 084 mecze TOUR, 74% z prognozą ratingu (reszta: wariant = obecny środek).
Krzywa dopasowana na liniach rynkowych (jedna linia na mecz / rynek /
zawodnika, symetrycznie dla ramion), log-loss ramienia minus BASE na teście:

| rodzina | ORACLE (sufit) | EXP | EXP_T | EXP_T_R | >= 0.70 na linii rynkowej |
|---|---|---|---|---|---|
| asy mecz | -0.0139 [-0.0167, -0.0109] | **-0.0022 [-0.0030, -0.0013]** | +0.0000 | **-0.0022 [-0.0036, -0.0010]** | żadne ramię poza ORACLE nie dochodzi do 0.70 |
| asy sety | -0.0058 [-0.0072, -0.0046] | +0.0005 [+0.0000, +0.0010] | **-0.0011 [-0.0017, -0.0003]** | **-0.0038 [-0.0051, -0.0026]** | EXP_T 4 053 nogi, -1.5 pp [-3.0, -0.1]; EXP_T_R 4 371, -1.3 pp [-2.6, +0.1] |
| PB mecz | -0.0097 [-0.0121, -0.0074] | +0.0003 [-0.0003, +0.0009] | -0.0002 [-0.0011, +0.0009] | = EXP_T | EXP_T 363 nogi, -21.2 pp |
| PB sety | -0.0019 [-0.0031, -0.0006] | +0.0014 [+0.0010, +0.0019] | -0.0006 [-0.0015, +0.0004] | = EXP_T | 0 |

Co to znaczy:

- **Długość meczu to największy brakujący czynnik** - wyrocznia (prawdziwa
  liczba gemów) poprawia log-loss 3-10 razy bardziej niż cokolwiek innego.
- **Ale przed meczem prawie nie da się jej przewidzieć.** Oczekiwane gemy z
  ratingu (EXP) dają z tego sufitu niewiele (asy mecz) albo nic / gorzej
  (sety, PB). Literaturowy model "tempo x ekspozycja" jest poprawny, tylko
  ekspozycja przed meczem to głównie szum, który rynek wycenia tak samo jak my.
- **Efekt turnieju (kort, piłki)** jest realny w asach w setach na historii.
- **Podwójne błędy:** nic nie działa poza wyrocznią.
- **Krzywa z całej drabinki (dzisiejsza) na linii rynkowej zawyża:** BASE
  przy >= 0.70 asy mecz -25.7 pp [-30.7, -20.8], PB mecz -30.4 pp - to samo,
  co 10-17 (§4 `tennis_aces_opponent_2026-10-17.md`). Na żywo trzymają to dowody
  linii; krzywa z linii rynkowych po prostu nie dochodzi do 0.70.

## 2. Linie Superbetu 10-06..10-18 (bezpiecznik)

Replay (te same funkcje, krzywe z linii rynkowych dopasowane na wszystkim
przed 10-06) czytany dokładnie na rozliczonych liniach Superbetu; nogi przy
pewności >= 0.70 i x >= 0.90, bez dowodów linii i bez bramek marży / świeżości.
Dołączone 2 452 linie / 60 meczów (pominięte: 855 poza siatką replayu lub bez
próbki >= 8, 562 z innym zapisem nazwiska niż 02_fixtures).

| rodzina | ramię | dLL vs BASE | nogi / mecze | pewność | trafione | luka | 1/kurs | ROI |
|---|---|---|---|---|---|---|---|---|
| asy sety | BASE | - | 10 / 8 | 0.776 | 0.600 | -17.6 pp [-44.4, +11.4] | 0.593 | +4.3% |
| asy sety | EXP_T | -0.0006 [-0.0078, +0.0069] | 35 / 15 | 0.742 | 0.629 | -11.3 pp [-26.0, +4.4] | 0.581 | +8.0% |
| asy sety | EXP_T_R | +0.0020 [-0.0078, +0.0125] | 19 / 9 | 0.766 | 0.632 | -13.4 pp [-36.1, +7.0] | 0.571 | +8.1% |
| asy sety | ORACLE | -0.0292 [-0.0502, -0.0073] | 34 / 20 | 0.785 | 0.706 | -7.9 pp | 0.586 | +23.0% |
| asy mecz | wszystkie poza ORACLE | -0.008..+0.006, przedziały przez zero | 0 | | | | | |
| PB mecz / sety | wszystkie | przedziały przez zero | 0-3 | | | | | |

Dodatni ROI nóg EXP_T (+8%) to 35 nóg z 15 meczów przy luce -11 pp: szum, nie
przewaga. Jedyny wariant z wyraźnym zyskiem to wyrocznia - znajomość długości
meczu, której przed meczem nie mamy.

## 3. Czego to nie mierzy

- Prawdziwy SHEET (`process_fixture`) nie był uruchamiany z nowym środkiem - po
  porażce bezpiecznika na replayu implementacja w SHEET nie ma uzasadnienia.
  Replay liczy środek z priorem tieru jak SHEET, ale próbka >= 8 (SHEET >= 5).
- Krzywe są punktowe (CONFIDENCE czyta `realised_lo95` i dowody linii, które
  tylko obniżają) - na żywo nóg byłoby mniej, nie więcej.
- Priory tieru są dopasowane na całym cache (w każdym ramieniu tak samo).
