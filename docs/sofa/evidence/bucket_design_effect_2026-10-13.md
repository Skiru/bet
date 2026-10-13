# A4: efekt projektu per kubełek (audyt 2026-10-13)

Przełącznik: `epochs.BUCKET_DESIGN_EFFECT_FROM_UTC`. Kod: `line_evidence._cells`
(pole `deff` kubełka), `LineEvidence.deff_for`. Skrypt:
`scripts/sofa/measure_bucket_design_effect.py` (tylko odczyt).

## Rejestracja (zapisana 2026-10-13 przed uruchomieniem pomiaru)

- Populacja: klucze **bez krzywej** (wiersz bez `base`) we wszystkich sportach:
  piłka i tenis z `07_settled.json` dni stats-only, hokej / koszykówka /
  siatkówka / CS2 z `data/line_evidence/rows_before_2026-10-13/*_superbet_settled.jsonl`.
- Podział poza próbą: walk-forward po dniach testowych 2026-10-07..2026-10-12;
  line evidence dopasowane (`le.fit`, reguły v2) wyłącznie na liniach dni
  wcześniejszych niż dzień testowy, odczyt linii dnia testowego starą regułą
  (efekt projektu sportu) i nową (efekt projektu kubełka).
- Metryka główna: log-loss odczytanej pewności na liniach, które czytają obie
  reguły i których pewność w którejkolwiek regule >= 0,70; różnica
  nowa - stara, 95% z bootstrapu po meczach (2000, ziarno 7).
- Próg (O5): włączyć, gdy górna granica 95% różnicy < 0.
- Raportowane obok: nogi „do druku” (pewność >= 0,70, pewność x kurs >= 0,90)
  w obu regułach - realizacja minus pewność i ROI z przedziałami; osobno nogi
  dodane przez nową regułę; per sport.

## Wynik (2026-10-13, `data/audit_2026-10-13/a4.json`)

| zakres | linie / mecze (log-loss) | log-loss nowa - stara [95%] | do druku, stara: nogi / mecze, realizacja - pewność, ROI | do druku, nowa | dodane przez nową |
|---|---|---|---|---|---|
| all | 1898 / 682 | -0.0351 [-0.0409; -0.0292] | 200 / 169: +0.8 pp [-5.1; +6.5], ROI -4.8% [-11.5; +1.7] | 675 / 419: +2.1 pp [-0.6; +4.7], ROI -3.2% [-6.2; -0.3] | 477 / 321: +4.5 pp [+1.6; +7.3], ROI -2.4% [-5.9; +0.7] |
| cs2 | 110 / 13 | -0.0513 [-0.0786; -0.0264] | 2 / 1: -23.8 pp [-23.8; -23.8], ROI -33.5% [-33.5; -33.5] | 36 / 13: +13.8 pp [+4.4; +20.4], ROI +9.6% [-0.7; +16.9] | 34 / 12: +16.4 pp [+8.3; +21.0], ROI +12.1% [+2.8; +18.1] |
| football | 1200 / 398 | -0.0398 [-0.0474; -0.0321] | 111 / 85: -1.2 pp [-9.1; +6.2], ROI -7.6% [-16.5; +0.8] | 465 / 264: +2.7 pp [-0.6; +5.7], ROI -3.2% [-6.9; +0.3] | 355 / 229: +5.4 pp [+2.1; +8.2], ROI -1.7% [-5.5; +1.5] |
| hockey | 14 / 14 | +0.0030 [-0.0785; +0.1190] | - | 1 / 1: -86.5 pp [-86.5; -86.5], ROI -100.0% [-100.0; -100.0] | 1 / 1: -86.5 pp [-86.5; -86.5], ROI -100.0% [-100.0; -100.0] |
| tennis | 574 / 257 | -0.0230 [-0.0323; -0.0132] | 87 / 83: +4.0 pp [-4.2; +11.9], ROI -0.5% [-10.4; +8.6] | 173 / 141: -1.5 pp [-7.0; +4.2], ROI -5.4% [-12.1; +1.2] | 87 / 79: -2.7 pp [-10.9; +4.6], ROI -10.0% [-19.7; -0.8] |

**Próg spełniony** (łącznie górna granica < 0; piłka, tenis i CS2 osobno też).
Przełącznik `BUCKET_DESIGN_EFFECT_FROM_UTC` = 2026-10-14 00:00Z (O5).

Co widać obok: nowa reguła drukuje ~3,4 x więcej nóg z kluczy bez krzywej,
dodane nogi realizują ponad pewnością (piłka +5,4 pp), czyli odczyt jest
nadal ostrożny. ROI dodanych nóg piłki i CS2 nie jest gorszy niż starych;
**tenis: dodane nogi ROI -10,0% [-19,7; -0,8] na 87 nogach / 79 meczach** -
zastrzeżenie do obserwacji (test w rejestrze `T-A4-bucket-deff`), nie kryterium
(kryterium zapisane z góry to log-loss).
