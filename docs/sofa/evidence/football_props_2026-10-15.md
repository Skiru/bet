# Rynki zawodników piłkarskich osobno (2026-10-15, noc)

Pozycja z listy „Before the next refit” w CLAUDE.md: zmierzyć dopuszczone
rynki zawodników piłkarskich osobno. Tylko odczyt (`data/sofa.db`, `mode=ro`).

## Dane

Rozliczone wiersze `sofa_settled_row`, piłka, `player_*`, dni 2026-10-12..14
(od `PLAYER_STARTS_ONLY`: próbki ze startów, krzywe zawodników ze startów),
WIN / LOSS: **8 767 wierszy**. Pewność = zainstalowana krzywa
(`confidence.Calibration.realised(market, p_central, "football",
direction)`, bez line evidence, bez bramek kuponu); ROI przy kursie
oferowanym; bootstrap meczów 95%, 2 000 powtórzeń.

## Wynik (pewność >= 0,70)

| rynek | linie / mecze | pewność | realizacja | realizacja - pewność | ROI |
|---|---|---|---|---|---|
| **wszystkie** | 319 / 51 | 0,774 | 0,752 | -2,1 pp [-6,9; +2,7] | **-16,5% [-21,7; -11,3]** |
| player_shots_for | 153 / 49 | 0,786 | 0,778 | -0,8 pp [-8,0; +6,8] | -13,4% [-21,7; -4,9] |
| player_tackles_for | 97 / 22 | 0,769 | 0,701 | -6,8 pp [-16,9; +3,0] | -25,5% [-36,3; -14,9] |
| player_fouls_for | 42 / 31 | 0,745 | 0,833 | +8,9 pp [-6,2; +20,1] | -4,0% [-21,6; +8,9] |
| player_right_foot_shots_for | 16 / 10 | 0,750 | 0,812 | +6,2 pp [-12,4; +24,8] | -1,9% [-22,0; +16,7] |
| player_left_foot_shots_for | 11 / 9 | 0,796 | 0,455 | -34,1 pp [-61,0; -2,0] | -47,9% [-79,3; -14,3] |

Surowe p modelu na tych samych dniach (`measure_settled_by_market.py --from
2026-10-12 --to 2026-10-14`, p >= 0,70): 847 linii / 54 mecze, trafienia
0,682 przy p 0,796 i 1/kurs 0,838, ROI -18,8% [-22,9; -14,8] - model zawyża
~11 pp, krzywa to zbiera.

Wydrukowane nogi zawodników piłkarskich 10-12..10-14: **jedna** (Hugo
Vetlesen strzały > 0,5 @1,16, pewność 0,840 - przegrana); pozostałe
wydrukowane `player_*` to hokejowe `player_pp_points`.

## Wniosek

- Krzywa rynków zawodników jest skalibrowana na nowych danych (luka w zerze);
  model surowy zawyża, krzywa to poprawia.
- Superbet wycenia te rynki krótko (1/kurs ~0,84-0,86 przy realizacji
  ~0,75): przy cenie są na minusie, i dlatego reguły kuponu (pewność x kurs
  >= 0,90, singiel jednostronny tylko z krzywą n >= 300) prawie nic z nich nie
  drukują. To działa jak trzeba - nie ma tu nic do włączenia.
- `player_left_foot_shots_for` OVER (zainstalowany 2026-10-15) zawyża o
  -34 pp na 11 liniach / 9 meczach - za mało na decyzję, do obserwacji
  (`T-` w rejestrze nie dodany; klucz i tak nie drukował).
- Trzy dni, 51 meczów: to audyt, nie źródło krzywej (krzywe z historii).
