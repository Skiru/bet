# A3 + C8: dogrywka koszykówki - długość i „overtime spike” (audyt 2026-10-13)

Przełącznik: `epochs.BB_OVERTIME_FROM_UTC`. Kod: `score_model._basketball`
(`quarter_minutes`, `SimParams.bb_tie_pull` / `bb_tie_window`),
`score_model.quarter_minutes_for`. Skrypt:
`scripts/sofa/measure_basketball_overtime.py` (tylko odczyt).

## Rejestracja (zapisana 2026-10-13 przed uruchomieniem pomiaru)

- A3: dogrywka skalowana jako 5/10 kwarty zawsze (`q_len = 10.0 if
  len(mu1) == 4`, a koszykówka ma zawsze 4 kwarty). Nowa reguła: 5/12 w
  rozgrywkach z kwartami 12-minutowymi - stała per liga
  (`TWELVE_MINUTE_QUARTERS`: NBA 132, NBA Preseason 2329, PBA 1656 / 1712 /
  1956; Sofascore `defaultPeriodLength` = 12 tylko dla NBA Preseason i PBA w
  bazie, NBA z reguł ligi), wszędzie indziej 5/10.
- C8: remis po regulaminie niedoszacowany (~0,022 vs ~0,040). Nowa reguła:
  wynik regulaminowy z różnicą 1..`bb_tie_window` (3, wybrane, nie
  dopasowane) z prawdopodobieństwem `bb_tie_pull` staje się remisem (strona
  przegrywająca dorabia różnicę w ostatniej kwarcie - gra na faul / za 3 pod
  koniec; Ely, Cheap Talk 2009). `bb_tie_pull` dopasowane momentem na meczach
  przed oknem (udział remisów w historii wobec symulacji).
- Okno ewaluacji: mecze 2026-02-01..2026-05-31 (sezon), model as-of każdego
  meczu (walk-forward: książka aktualizowana po meczu), co n-ty mecz do
  limitu 3 000; 600 symulacji na mecz, to samo ziarno w obu wariantach.
- Metryka główna: log-loss trójdrogowego 1X2 po regulaminie (1 / remis / 2)
  na mecz, nowa - stara; 95% z bootstrapu po meczach (2000, ziarno 0).
- Próg (O5): włączyć, gdy górna granica < 0 **i** Brier sumy z dogrywką
  (próg = mediana sum historii) nie jest gorszy (dolna granica różnicy <= 0).
- Włączenie wymaga refitu krzywej koszykówki tym samym estymatorem (etap 5:
  jeden refit po A2, A3 + C8 i pomiarze A8).

## Wynik (2026-10-13, `data/audit_2026-10-13/a3c8.json`)

- Dopasowanie `bb_tie_pull` (okno 2025-10-01..2026-02-01, 1951 meczów):
  remisy w historii 0.0267, w symulacji 0.0226, masa w
  oknie 1..3 pkt 0.135 -> **0.0299**.
- Ewaluacja 2026-02-01..2026-06-01, 3081 meczów: remis po regulaminie -
  rzeczywisty 0.0415, stary 0.0236, nowy 0.0278.
- log-loss 1X2 po regulaminie nowa - stara: **-0.00354 [-0.00719; -0.00015]**
- Brier sumy z dogrywką (próg 163.5): +0.00001 [-0.00069; +0.00071]
- Brier zwycięzcy: -0.00032 [-0.00118; +0.00055]; kalibracja p >= 0,70:
  stara 0.807 / 0.813 (n 1208), nowa
  0.808 / 0.814 (n 1205).

**Próg spełniony** (górna granica log-loss < 0, suma bez pogorszenia).
Remis nadal niedoszacowany (0,028 wobec 0,042): okno dopasowania (październik -
styczeń) miało mniej remisów niż okno ewaluacji - kierunek dobry, skala
ostrożna. Przełącznik `BB_OVERTIME_FROM_UTC` wchodzi z refitem krzywej
koszykówki (etap 5).
