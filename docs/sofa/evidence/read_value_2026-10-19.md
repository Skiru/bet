# Czy odczyty analityków i weryfikatora poprawiają kupon (2026-10-19)

Pomiar tylko do odczytu, bez przełącznika i bez zmiany potoku:
`scripts/sofa/measure_read_value.py --from 2026-10-09 --to 2026-10-18`.
Populacja: każda noga piłki / tenisa, która dostała werdykt w `reads.json` i
została rozliczona, oceniona tak, jak ocenia ją księga
(`record_results.graded_confidence`: wydrukowane nogi i `removed:reads`, bez
nóg zdjętych automatyczną bramką MODEL_ABOVE_OWN_SAMPLE, `reason: "auto"`).
Sporty mierzone (hokej, kosz, siatkówka, CS2) nie wchodzą - ocenia się je
osobno i nigdy nie łączy. Autor usunięcia = `reason` nogi w `11_coupon.json`.
Przedziały 95% z bootstrapu po meczach.

| grupa | n | mecze | trafienia | pewność | 1/kurs | ROI | ROI 95% |
|---|---|---|---|---|---|---|---|
| przeczytane, na kuponie | 5411 | 493 | 0.794 | 0.799 | 0.816 | -2.6% | [-4.5, -0.6] |
| usunięte odczytem (WATCH / NO_BET) | 192 | 76 | 0.781 | 0.780 | 0.785 | -0.2% | [-11.0, +9.4] |
| usunięte przez analityków | 161 | 64 | 0.820 | 0.773 | 0.779 | +5.4% | [-4.1, +13.8] |
| usunięte przez weryfikatora | 31 | 15 | 0.581 | 0.816 | 0.816 | -29.2% | [-54.1, +0.8] |

(trafienia - 1/kurs) usuniętych minus zostawionych: **+1.8 pp [-6.4, +9.0]**.

## Co z tego wynika

- Nie ma dowodu, że werdykty analityków poprawiają kupon: nogi przez nich
  usunięte zagrały punktowo **lepiej** niż zostawione (0.820 przy pewności
  0.773). Usunięcia weryfikatora (defekty) trafiają w nogi wyraźnie słabsze
  (0.581 przy 0.816), ale to 31 nóg z 15 meczów i przedział ROI dotyka zera -
  sygnał do potwierdzenia na nowych dniach, nie wynik.
- Klasyfikacja ~650 powodów WATCH / NO_BET z 10-09..10-19 (słowa kluczowe,
  przybliżona): najczęstszy powód analityków to "próbka k/n poniżej
  pewności / model nad próbką / próbka nie zna klasy rywala" - czyli
  podważanie krzywej skalibrowanej na historii surową próbką. Defekty
  (zła tożsamość, wycofana linia, mecze towarzyskie w próbce, brak kartek
  w danych, sędzia przy czerwonych kartkach) są nieliczne i mechaniczne.
- Wniosek dla kosztu: rozszerzenie czytania LLM na wszystkie mecze nie ma
  dziś uzasadnienia w wyniku; tańsza droga to deterministyczne sprawdzenia
  defektów na wszystkich nogach i LLM tylko na nogach oznaczonych.
  **Decyzja operatora** - zmiana zasad werdyktów zmienia to, co się drukuje.

Pomiar powtarzać na nowych dniach tym samym skryptem.
