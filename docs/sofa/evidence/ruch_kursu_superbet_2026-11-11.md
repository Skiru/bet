# Ruch kursu Superbetu jako sygnał - pomiar 2026-11-11 (iteracja 1)

**Wniosek: odrzucone.** Ostatni kurs Superbetu zawiera już ruch, który do
niego doprowadził. Noga, której kurs skrócił się od pierwszego notowania, nie
wchodzi istotnie częściej, niż mówi ten ostatni kurs (bez marży), a ROI zostaje
−7..−8%. Niczego nie wdrażam.

Skrypt (tylko odczyt):

```
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_price_drift.py --split 2026-10-25
```

## Dane

- Każda linia SHADOW (hokej, koszykówka, siatkówka) rozliczona WIN / LOSS w
  `runs/sofa/shadow/<sport>/<dzień>/settled.json`, 09-29..11-10.
- Do niej pierwsze przedmeczowe notowanie tej samej linii z `snapshots.jsonl`.
- 783 801 linii: 523 tys. koszykówka, 187 tys. hokej, 74 tys. siatkówka.
- Ruch: ln(pierwszy kurs / kurs rozliczenia). Plus oznacza, że kurs się skrócił.
- Oceniam trafienia minus `fair_p` przy kursie rozliczenia, z bootstrapem po
  meczach. ROI liczone przy kursie rozliczenia, przed podatkiem.

## Wynik (wszystkie trzy sporty)

| ruch | dev ≤ 10-25 | hold-out > 10-25 |
|---|---|---|
| wydłużył 3-10% | −0,66 pp [−2,01; +0,50], ROI −12,4% | −0,85 pp [−1,94; +0,19], ROI −12,0% |
| bez ruchu | 0,00 pp, ROI −9,5% | −0,04 pp, ROI −10,4% |
| skrócił 3-10% | +0,88 pp [−0,31; +2,06], ROI −8,0% | +0,90 pp [−0,20; +2,05], ROI −7,7% |
| skrócił > 10% | +0,06 pp [−2,09; +1,94] | +1,39 pp [−0,92; +3,80], ROI −7,0% |

- Kierunek się powtarza: linie skracane wypadają ~1 pp lepiej, linie
  wydłużane ~1 pp gorzej. Wszystkie przedziały obejmują jednak zero, a efekt
  jest pięć razy mniejszy od marży (~8-10% na tych liniach).
- Krótkie ceny (fair ≥ 0,70, `--min-fair 0.70`) nie dają spójnego wyniku
  między połówkami. Skrócone 3-10%: dev −0,90 pp, hold-out +1,20 pp.
- Po drodze wyszło coś innego: losowa linia Superbetu w tych sportach traci
  8-10% przed podatkiem, a nasz wydrukowany kupon −4..−5%. Selekcja ze
  statystyk już teraz ścina około połowy marży.

## Iteracja 2: marża na naszej stronie zakładu (wydrukowane single 10-30..11-10)

- Marża własna nogi to 1/kurs minus `market_p` (kurs bez marży, metoda
  potęgowa). Liczona na 43 524 wydrukowanych singlach z `market_p`.
- Kwintyle z dev (do 11-04), od najniższej do najwyższej marży własnej:
  - ROI dev: −3,2 / −4,7 / −6,0 / −5,2 / −5,3%;
  - ROI hold-out: −3,8 / −3,8 / −4,3 / −5,4 / −6,8%.
- Nogi trafiają średnio ~1 pp poniżej `market_p` (0,791 wobec 0,801), więc
  strata to prawie dokładnie marża nałożona na naszą stronę.
- To ta sama informacja co marża rynku w `lesser_loss`. Wewnątrz marży
  < 8,6% podział po marży własnej daje dev +2,3% przy n 344, ale hold-out
  −0,5% przy n 305 - nie powtarza się. Niczego nie wdrażam.

## Iteracja 3: „poniżej" kontra „powyżej" przy tej samej cenie (literatura: gracze przepłacają za „powyżej")

- Wydrukowane single liczbowe (sumy, rożne, kartki, strzały, gemy itd.)
  10-30..11-10, ROI przed podatkiem, przedziały z bootstrapu po meczach.
- **Piłka** (n po 2-4 tys. na komórkę):

  | kurs | „poniżej" dev / hold-out | „powyżej" dev / hold-out |
  |---|---|---|
  | 1,00-1,20 | −4,5% / −4,1% | −4,9% / −5,0% |
  | 1,20-1,40 | −3,8% / −4,1% | −4,8% / −3,1% |

  Różnicy nie ma.
- **Tenis:** obie strony −4..−13%, bez spójnego kierunku.
- **Hokej, krótkie „poniżej" 1,00-1,20:** +0,9% [−3,2; +4,8] przy n 395 (dev)
  i +2,1% [−3,5; +6,9] przy n 221 (hold-out). Za mało, przedziały obejmują
  zero. To tylko trop do ponownego pomiaru przy ~1 000 nóg.
- **Rynki zwycięzcy w tenisie** (`match_won_for`, `set1/2_won_for`): 37-60 nóg
  na komórkę, połówki się nie zgadzają.

Niczego nie wdrażam.
