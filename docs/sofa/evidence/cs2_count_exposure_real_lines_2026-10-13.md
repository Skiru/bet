# B12, kontrola na prawdziwych liniach Superbetu (CS2, 2026-10-13)

Uzupełnienie `cs2_kills_exposure_2026-10-13.md` (tam: linie syntetyczne;
"kontrola na rozliczonych liniach Superbetu nie wykonana"). Tylko odczyt.

## Metoda

- Linie: `runs/sofa/cs2/<d>/settled.json`, dni 2026-10-05..2026-10-12, rodziny
  player_kills / player_deaths / player_assists / team_kills, wyniki WIN / LOSS
  (4 368 stron linii w 35 seriach; obie strony każdej linii).
- Dla każdej linii odtworzone `settle_cs2.attach_model`: historia sprzed startu
  serii (`load_history`, baza `data/sofa.db` tylko do odczytu), te same
  przełączniki dnia (map identity, round race); p stary = `exposure=None`,
  p nowy = `exposure=build_exposure(history)`. Nowy p dla wszystkich 4 368
  linii pochodzi z modelu ekspozycji (`round_exposure`), stary z NB / normal.
- Log-loss nowy - stary na linię, 95% bootstrap po seriach (2000, ziarno 0,
  `measure_cs2_map_identity.boot`). Strażnik: linie, gdzie któryś p >= 0,70.
- Status druku liczony samym surowym p: p >= 0,70 i p x kurs >= 0,90, BEZ line
  evidence (które tylko obniża), więc to górna granica liczby linii.
- Uwaga: świeży p "stary" różni się od zapisanego `model_p` do 0,108 na
  pojedynczych liniach (baza zmieniła się od rozliczenia); wnioski dotyczą
  pary stary / nowy liczonej na tej samej historii.

## Wynik

| rodzina | linie / serie | log-loss nowy - stary | strażnik p>=0,70 (n) |
|---|---|---|---|
| player_kills | 1 396 / 35 | -0,0162 [-0,0248, -0,0076] | -0,090 [-0,155, -0,027] (33) |
| player_deaths | 1 376 / 35 | -0,0219 [-0,0440, +0,0003] | -0,076 [-0,126, -0,015] (89) |
| player_assists | 1 312 / 33 | -0,0160 [-0,0296, -0,0029] | -0,061 [-0,164, +0,042] (22) |
| team_kills | 284 / 35 | -0,0304 [-0,0577, -0,0024] | -0,066 [-0,294, +0,314] (4) |
| razem | 4 368 / 35 | -0,0189 [-0,0288, -0,0088] | -0,077 [-0,119, -0,033] (148) |

Kalibracja p >= 0,70 (srednie p / realizacja): stary n 142, 0,742 / 0,535;
nowy n 10, 0,718 / 0,400. Stary model zawyża o ok. 20 pp na tych liniach
(Superbet stawia je blisko średniej, p >= 0,70 to wybór modelu przeciw
kursowi); nowy prawie nie produkuje takich p.

Status druku (surowe p): stary 142 linii wchodziłoby (hit 0,535, ROI -7,2%),
nowy 10 (hit 0,400, ROI -29%, n za małe), wspólne 4, dochodzi 6, odpada 138.
Średnie |dp| = 0,058.

## Wnioski i zastrzeżenia

- Kierunek zgodny z pomiarem syntetycznym: log-loss lepszy w każdej rodzinie,
  w trzech z czterech i razem z przedziałem poniżej zera (player_deaths
  graniczny, +0,0003). Strażnik nie wyklucza żadnej rodziny.
- Nowy model niemal wygasza druk tych rodzin (142 -> 10 linii), czyli głównie
  usuwa zawyżone p starego modelu, które realizowało 0,535 przy p 0,742.
- Próba mała: 35 serii z 8 dni, 148 linii p >= 0,70 (w tym rozjazd po
  serii, bo linie jednej serii są zależne); ROI i kalibracja nowego p (n 10)
  nie mówią nic. Nie zmierzone: line evidence (offset / pasmo cenowe) na tych
  liniach; to tylko surowe p.
