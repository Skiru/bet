# Próbki reprezentacji a wiek próbki (2026-10-05, noc)

## Problem

10-05 Superbet wystawił 8 meczów Ligi Narodów. Na kupon trafiło 5 nóg, wszystkie z meczu Francja – Belgia.

CONFIDENCE odrzuca nogę jako `SAMPLE_CROSSES_SEASON`, gdy najstarszy mecz próbki ma więcej niż 180 dni (`MAX_BUILDER_SAMPLE_AGE_DAYS`, `confidence.py:314`). Reprezentacja gra około 10 meczów w roku, więc próbka 10 meczów prawie zawsze sięga dalej niż 180 dni. Francja przeszła tylko dzięki mundialowi: jej próbka rożnych miała 104 dni.

Odtworzenie przebiegu CONFIDENCE z 13:30Z, z zatrzymanym zegarem i logiem bramki dla każdego wiersza:

- 157 ze 178 odmów `SAMPLE_CROSSES_SEASON` dotyczyło meczów reprezentacji;
- każda z tych nóg przeszła wcześniej bramki ceny, krzywej, progu i x;
- bez limitu wieku na kupon trafiłoby 125 nóg Ligi Narodów zamiast 5.

## Pomiar

Metoda jak w `measure_sample_composition.py`: log-loss Poissona średniej z próbki, przedziały 95% z bootstrapu po meczach. Dane: 21 209 meczów o stawkę reprezentacji od 2015 roku, bez towarzyskich. Szczegóły w katalogu `national_samples_2026-10-05/`.

**`goals_for`, zmiana log-loss względem najnowszych 10 meczów** (dodatnia = gorzej):

| reguła | wszystkie reprezentacje | seniorzy |
|---|---|---|
| tylko mecze z 180 dni | +0.022 [+0.018; +0.027] | +0.015 [+0.010; +0.021] |
| tylko mecze z 730 dni | +0.010 [+0.007; +0.013] | +0.005 [+0.002; +0.009] |

**Kalibracja przy p ≥ 0.70** (197 574 wiersze z odtworzenia historii): różnica „trafione − deklarowane” nie zależy od wieku próbki.

| najstarszy mecz próbki | trafione − deklarowane |
|---|---|
| 180–400 dni | +0.005 [−0.001; +0.010] |
| 400–730 dni | +0.004 [−0.000; +0.008] |
| ponad 730 dni | +0.001 [−0.003; +0.004] |

**Rozliczone wiersze reprezentacji na żywo (09-18 – 10-04), p ≥ 0.70:**

| najstarszy mecz próbki | mecze | ROI |
|---|---|---|
| 180–400 dni | 28 | −5.3% |
| 400–730 dni | 122 | −4.8% |
| ponad 730 dni | 41 | −11.0% [−21.4; −0.6] |

Dla porównania cała piłka przy p ≥ 0.70 ma ROI −4.8%. Grupa powyżej 730 dni wypada gorzej, ale to tylko 41 meczów, więc traktujemy to jako podejrzenie, nie wynik. Stąd flaga wieku na każdej nodze.

## Reguła (od 2026-10-06, `epochs.NATIONAL_SAMPLE_AGE_FROM_UTC`)

- **Rozpoznanie meczu reprezentacji.** RESOLVE zapisuje `national_teams`: obie strony mają w `/event` pole `national`.
- **Ocena próbki.** Taki mecz CONFIDENCE ocenia liczbą obserwacji (`THIN_SAMPLE_FOR_BUILDER`), a nie wiekiem.
- **Wiek na nodze.** Wiek próbki jest pokazany jako `NATIONAL_SAMPLE_AGE(oldest N d)` i nie jest bramką.
- **Bez zmian:**
  - `STALE_SAMPLE`, czyli najnowszy mecz starszy niż 60 dni;
  - reguła „te same rozgrywki” dla goli: u seniorów i w Lidze Narodów brak efektu w obie strony;
  - wszystkie bramki ceny i krzywej.
- **Do obserwacji.** Nogi z flagą powyżej 730 dni trzeba mierzyć osobno. Jeśli strata się utrzyma, tańszą alternatywą jest limit 730 dni.

Pomiar wykonał subagent 2026-10-05 wieczorem. Liczby odmów sprawdzono lokalnie: wiek próbek meczów Ligi Narodów w `03_samples.json` wynosi od 104 do 1472 dni.
