# Noc 2026-10-20/21 - piłka: każda statystyka Superbetu (kartki, faule, zawodnicy, strzały)

Polecenie operatora (10-20 wieczorem): ultra szczegółowe, iteracyjne poprawki modelu piłki,
żeby liczyć każdą statystykę dostępną w Superbecie, w każdej kombinacji; test w kodzie, E2E,
pełny głęboki audyt, most Sofascore wolno włączyć. Praca na stałym przyzwoleniu z 10-15
(lepiej poza próbą z przedziałem bez zera, testy, raport, przełącznik; nigdy w zbudowany dzień).

**Wszystkie przełączniki działają od 2026-10-21 00:00Z.** Dzień 10-21 nie był zbudowany
(w `runs/sofa/2026-10-21/` tylko `sport_fixtures.json` pętli), więc dzień nie jest mieszany.
Grupa księgi: "od 10-21" (razem z dwoma przełącznikami CS2 tego samego momentu).

## 1. Rozpoznanie (przed zmianami)

- **Rynki nieczytane** (`unmapped_prices` 10-14..10-20): kartki w połowach (486 meczów/tydz.),
  czerwone / karne drużyny i połowy (100-360), faule na zawodniku (173), "każda drużyna powyżej X"
  wrzutów / wybić / odbiorów, handicapy strzałów, przedziały / parzystość rożnych, "którykolwiek
  z zawodników", strzelcy goli, kartka zawodnika, obramowanie bramki, rynki minutowe (tych
  ostatnich Sofascore nie rozliczy - brak osi czasu rożnych / fauli).
- **Rynki czytane**: w kartkach / faulach / strzałach nie brakowało estymatora - krzywa i line
  evidence uczciwie spychały je pod 0,70. Dwie prawdziwe luki: 66-87% oferowanych szczebli
  zawodników nie miało wiersza SHEET (SAMPLES: za mało startów, nazwisko, brak klucza), a p
  strzałów zawodnika (~0,51) leżało daleko od 1/kurs (~0,80).
- **Literatura**: sędzia (mnożnik żółtych 0,77-1,27 - tyle co rozrzut drużyn), mecz wyrównany =
  więcej kartek, korelacja kartek stron, udział zawodnika w wolumenie drużyny.

## 2. Co weszło (przełącznik, pomiar, dowód)

Log-loss x1e-4 (nowy minus stary, ujemny = lepiej), 95% bootstrap po meczach, poza próbą.

| przełącznik | co | pomiar | dowód |
|---|---|---|---|
| `FOOTBALL_REFEREE` | kartki / faule (8 rynków z połowami fauli) x stopa sędziego as-of (skurczona, K 10) ** beta; sędzia z `sofa_event_referee` (backfill przez most: 83 872 mecze, 2 540 sędziów, 21,4 tys. zapytań, 0 odmów) albo z `/event` meczu | test 2026: kartki suma -28,6 [-35,8; -22,0], kartki drużyny -16,1, faule suma -54,3, faule drużyny -27,6; drugi podział też poniżej zera; kalibracja >= 0,70 bez zmian (zysk = rozróżnianie meczów) | `docs/sofa/evidence/referee_effect_2026-10-21.md` |
| `FOOTBALL_CLOSENESS_STRETCH` | kartki (strona, suma) i strzały (suma, 1. połowa) x exp(g1 abs(s) + g2 s^2) | kartki suma walk-forward -34,6 [-43,0; -24,7]; ponad sędzią -33,4 [-47,8; -17,6]; razem przeszacowanie >= 0,70 najwyżej 0,2 pp | `docs/sofa/evidence/football_closeness_stretch_2026-10-21.md` |
| `FOOTBALL_PLAYER_SHARE` | strzały / celne / faule zawodnika = skurczony udział w wolumenie jego drużyny x centrum drużyny dziś (rating, gra, rywal); celne x skurczona celność | historia: strzały 0,5 -235, celne 0,5 -228 (każda linia poniżej zera); rozliczone linie Superbetu 10-12..10-19: strzały -178 [-240; -104], celne -168, faule -239 [-305; -170] | `docs/sofa/evidence/football_player_share_2026-10-21.md` |
| `FOOTBALL_PLAYER_COVERAGE` | SAMPLES: zero celnych udowodnione (213 047 / 213 047), cienki zawodnik z ostatnich 20 meczów, dwie reguły nazw (0 pomyłek na 23 666) | odzyskane wiersze jak bazowe: -0,1 pp [-0,6; +0,5]; SHEET +17-20% wierszy zawodników | `docs/sofa/evidence/football_player_coverage_2026-10-21.md` |
| `FOOTBALL_PLAYER_PROPS_V2` | "Zawodnik - liczba fauli na zawodniku" (`player_fouls_drawn_for`), krzywa zainstalowana | holdout przy krzywej >= 0,70: +1,79 pp [+0,32; +3,33], n 3 008 | `docs/sofa/evidence/football_player_props_v2_2026-10-21.md` |
| `FOOTBALL_STAT_VARIANTS` | "Każda drużyna powyżej X rzutów z autu / wybić od bramki", "Każda z drużyn powyżej X odbiorów", "Strzały - Handicap", handicapy strzałów połów | bez krzywej: NO_LINE_EVIDENCE do czasu własnych linii | `docs/sofa/evidence/football_stat_variants_2026-10-21.md` |
| `FOOTBALL_CARD_HALVES` | kartki w 1. / 2. połowie (suma, drużyna, najwięcej, handicap), czerwone / karne drużyny i połowy, obie drużyny z czerwoną | 18 krzywych (bramka jednostronna); rozliczenie 10-14..10-19: drukowalne 579 wierszy 0,810 przy 0,827 | `docs/sofa/evidence/football_card_halves_2026-10-21.md` |
| `FOOTBALL_CARD_HALVES_TERMS` | połowy od pełnego centrum kartek (z sędzią i abs(s)); karne / czerwone drużyny z oczekiwaną różnicą bramek | połowa 2 strona -87 [-105; -67]; karne drużyny -36,7 [-43,4; -30,6]; karne LM 10-20: 0,655-0,923 zamiast płaskiego 0,836 | `docs/sofa/evidence/football_card_halves_terms_2026-10-21.md` |

Zasada rozliczenia kartek w połowie (komunikat Superbetu nr 06/2022): żółta 1, czerwona 2,
czerwona za dwie żółte 3; kartka w przerwie = 2. połowa; sztab / ławka / po gwizdku nie liczą
się. **Założenie**: dwie żółte rozbite między połowy liczą się 1 + 2 tam, gdzie pokazano
kartkę (3,1% meczów) - sprawdzić na pierwszych rozliczonych liniach.

## 3. Zmierzone i odrzucone (nie budować bez nowych dowodów)

- "Zawodnik - otrzyma kartkę" (tylko "Tak"): p nigdy >= 0,70 (max 0,536 na 120 294 startach).
- "Którykolwiek z zawodników ... powyżej X": iloczyn graczy przegrywa ze stałą w 8 z 9 rynków.
- Parzystość / przedziały rożnych, dokładna liczba kartek: nigdy 0,70 poza kopiami szczebli O/U.
- Udział zawodnika dla odbiorów (0,5 gorzej +51), abs(s) dla fauli (H1 +33,8 gorzej), rożnych,
  stron; dyspersja zależna od abs(s) (gorzej przy >= 0,70 przez krzywe).
- Strzelcy goli: jednostronne "Tak", nie osiągają 0,70 - nie budowane.

## 4. E2E i audyt

- Każdy pakiet: wyłączony = bajt w bajt dzisiejszy; włączony = zmieniają się tylko jego wiersze.
- **Łączne E2E** (wszystkie 7 włączone vs wyłączone, kopie 10-19 / 10-20, prawdziwe skrypty
  SHEET -> CONFIDENCE -> kupon -> PDF, rc 0): nogi 10-19 1 736 -> 1 764 (+41 / -13), 10-20
  2 516 -> 2 540 (+44 / -20); inne sporty 0 zmian; każda nowa noga ma słowa Superbetu;
  ręczne sprawdzenie rozliczeń 3 629 / 0 niezgodności (300 meczów). md5 prawdziwych plików
  kuponu niezmienione.
- **Audyt** (`docs/sofa/history/AUDYT_NOCY_STATYSTYKI_2026-10-21.md`): bez błędów scalania;
  8 defektów, naprawione: D1 czerwona z `time` -5 liczona do 1. połowy (błędna ocena; test),
  D2 ruff, D3 regrade bez reguły pokrycia, D4 / D5 refit bez flag `--player-coverage` /
  `--closeness-stretch` (install teraz odmawia), D6 refit nadpisywałby bramkowane krzywe nowych
  rynków bez bramki (teraz zainstalowana wygrywa), D7 sędzia ogłoszony po porannym SHEET (rebuild
  teraz powtarza SHEET). D8 (sprzed nocy, plik innej sesji nieśledzony) - zostawiony.
- Bramki na końcu: pytest tests/sofa 5 499 passed (2 skipped; `test_f15_resolve_writes_...`
  bywa niestabilny pod `-n 8`, przechodzi sam), ruff / mypy czyste poza nieśledzonymi plikami
  innej sesji (`measure_slip_*.py`, `measure_cs2_map_total_race.py`), rejestr testów 0 uwag.

## 5. Ryzyka i co dalej

- **To kalibracja i rozróżnianie, nie przewaga.** Żaden pomiar nie pokazał zysku względem ceny
  Superbetu; propsy zawodników tracą ~18% przy starym i nowym modelu (marża jednostronnej drabinki).
- **Refit**: krzywe kartek / fauli / zawodników dopasowano bez sędziego i bez udziału (nieodtwarzalne
  w replayu); krzywe zawodników nie doszacowują modelu udziałowego o 2-6 pp przy >= 0,70 (ostrożnie).
  Następny refit: flagi 10-17 + `--closeness-stretch --player-coverage`.
- **Sędzia**: znany ~48 h przed meczem; poranna budowa ma go dla większości meczów z kartkami;
  `backfill_referees.py` dopisany do kroku 1a `/sofa-day`. Bramka `MODEL_ABOVE_OWN_SAMPLE` zdejmuje
  więcej nóg kartek (próba drużyny nie zna sędziego) - z założenia, do pomiaru.
- **Nowe rynki bez krzywej** (warianty statystyk) czekają na 50 rozliczonych linii w kubełku.
- Faule zawodnika prawie przestają się drukować (stary model: 57 nóg trafiało 0,632 przy ~0,73).
- `eb8bf308` przy rozwiązywaniu konfliktu objął też `config/sofa_superbet_line_evidence.json`
  z porannego odświeżenia 10-20 (plik, na którym zbudowano 10-20; treść niezmieniona przeze mnie).
- Do obserwacji na żywych liniach: kartki w połowie przy dwóch żółtych, karne / czerwone drużyn,
  faule na zawodniku (zgodność z dostawcą Superbetu niesprawdzona).

## 6. Rano 10-21: rynki łączone drukowalne (przed budową dnia)

Operator: "wszystkie rynki to wszystkie" - rynki łączone (obie drużyny powyżej X, najwięcej,
handicap) liczone, ale bez krzywej nie mogły się drukować. Od 10-21 00:00Z (`DERIVED_CURVES`,
`CARDS_CORRELATION`, `DERIVED_SHEET_MARGINS`, `DERIVED_SAMPLE_GATES`) czytają krzywe historii;
krzywe na linię goli w połowach i obron oraz 10 krzywych kobiet zainstalowane
(`fit_joint_curves.py`, bramka jednostronna, `docs/sofa/evidence/joint_curves_2026-10-21.md`).

- **Poprawka line evidence** (7b41d17f): poranne odświeżenie nie podawało `--derived-curves`, więc
  rynek łączony brałby krzywą, ale tylko wspólną poprawkę sportu (-0,6 pp). Na rozliczonych liniach
  Superbetu 10-05..10-19 "Obie drużyny strzelą powyżej 1.5 gola: nie" przy pewności 0,836
  zrealizowało 0,765 (-7,1 pp [-9,3; -4,9], 1 393 linie) - bez poprawki drukowałoby się ~7 pp za
  wysoko. Teraz własna poprawka klucza obniża pewność.
- **E2E 10-20** (kod main, kopia dnia, line evidence z poprawką): 114 nóg łączonych (1. połowa obie
  strzelą: nie 44, 2. połowa 41, rożne każda powyżej 11, obie powyżej 1.5 gola: nie 11, celne 3,
  najwięcej celnych 2, kartki 2), każda w słowach Superbetu; inne rynki bez zmian poza kalibracją
  line evidence. Pliki prawdziwego kuponu 10-20 nietknięte (md5).
- Fałszywy alarm po drodze: moje E2E uruchomiło ramię "on2" z wyłączonymi przełącznikami (błąd
  skryptu testowego, nie potoku).
- **Krzywe pozostałych rynków łączonych** (zainstalowane rano, przed budową 10-21; kopia
  `config/backup_2026-10-21_joint_curves_g3`): 130 krzywych na linię (faule i połowy, strzały i
  połowy, spalone, rzuty z autu, wybicia od bramki, odbiory, rożne w połowach; ich handicapy) + 12
  krzywych kobiet. Bramka odrzuciła linie, które przeszacowują > 2 pp (obie powyżej strzałów "nie"
  10.5-14.5, połowy 6.5 / 7.5, handicap strzałów 1. połowy 2.5) - te linie nie mają krzywej.
  "Najwięcej" fauli / spalonych / autów / wybić / odbiorów / strzałów w połowach i rożnych w połowach
  nie osiąga 0,70 na historii - nie drukuje się, widać je w zakładce "Wszystkie wyceny".
- **E2E 10-20 po instalacji**: +1 noga ("2. połowa - rzuty rożne - handicap"), 0 utraconych / zmienionych.
  Tego dnia Superbet wystawiał przy faulach / strzałach / spalonych "każda z drużyn" tylko stronę
  "tak" (krzywe przeszły głównie dla "nie"); auty / wybicia / odbiory OFFER czyta dopiero od 10-21.
