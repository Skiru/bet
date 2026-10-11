# Rynki zawodników: zakład obowiązuje tylko przy wyjściu w składzie (2026-10-11)

## Reguła

Kupon operatora 893M-S19CD8 (2026-10-10): Patrik Walemark (Lech) „celne
strzały powyżej 0,5” — **Zwrot**. Sofascore: Wålemark wszedł z ławki na 30
minut, 2 celne strzały; SETTLE ocenił WIN. Operator potwierdził (2026-10-11):
Superbet zwraca zakład na zawodnika, który nie wyszedł w podstawowym składzie.
Maksym Chłań (start, 71', 1 celny) — WIN u Superbetu i u nas.

Skala: 2 685 z 12 322 rozliczonych linii zawodników 10-05..10-10 (22%) to
wejścia z ławki. Przy kursie 1,0–1,3 trafiały w 32% (kurs implikował 88%),
wyjściowi w 67%.

## Co zmieniono

1. **SETTLE** (`run_settle._settle_player`): wejście z ławki → `PLAYER_NOT_STARTED`
   (bez wiersza, jak `PLAYER_DID_NOT_PLAY`); zawodnik spoza kadry meczowej →
   `PLAYER_NOT_IN_SQUAD`. Wszystkie trzy są listowane per noga w
   `07_settle_skips.json` `void_legs`; wydrukowana noga z tej listy to w 7c i
   w ledgerze **zwrot** (0 j.), nie „w toku”. Poprawka poprawności — od razu.
2. **Przeszłe dni**: `regrade_settled.py --player-not-started --apply`
   (2026-10-11 12:37Z): 5 215 wierszy 09-24..10-10 usuniętych z
   `sofa_settled_row` (24 654 → 19 439), żaden nie był wydrukowany; kopia do
   cofnięcia `runs/sofa/regrade_20261011T123734Z.json`. Ledger przeliczony:
   identyczny poza licznikiem wierszy w bazie.
3. **Próbka = starty** (`epochs.PLAYER_STARTS_ONLY_FROM_UTC`, 2026-10-12 00:00Z):
   zakład jest warunkowy na start, więc próbka to jego starty
   (`appearances: "starts"`, notka `PLAYER_STARTS_ONLY`).
4. **Krzywe** zawodników dopasowane na replayu historii z tą samą regułą
   (`calibrate_from_cache --player-starts-only`: wynikiem jest tylko
   zawodnik wyjściowy, próbką jego starty), przygotowane w
   `config/sofa_confidence_calibration.next.json` od 2026-10-12 00:00Z
   (`confidence.calibration_path_for`; dzień już zbudowany czyta stary plik).
   Pozostałe krzywe bajt w bajt bez zmian (test).

## Pomiar 1: próbka ze startów czy ze wszystkich występów

Replay historii (cache, ten sam estymator co SHEET — zgodność z SHEET
10-09..10-10: 9 374 linii co do 1e-4, 3 różnice jednego zawodnika z nowym
meczem w cache). Populacja: linie „powyżej” zawodników **wyjściowych**
(zakład, który Superbet rozlicza), 492 384 wspólne wiersze z 4 114 meczów.

Surowy log-loss (bez kalibracji) wychodzi **gorzej** dla startów (+0,0052) —
ich surowe p jest bardziej zawyżone. Ale pewność kuponu to p po krzywej,
więc rozstrzyga log-loss po kalibracji kubełkowej, dopasowanej na meczach o
parzystym id i ocenianej na nieparzystych (i odwrotnie):

| rynek | Δ log-loss (starty − wszystkie) | 95% CI (mecze) | AUC wszystkie / starty |
|---|---|---|---|
| razem | **−0,0027** | [−0,0030; −0,0024] | 0,787 / 0,786 |
| strzały | −0,0035 | [−0,0044; −0,0028] | 0,797 / 0,795 |
| faule | −0,0030 | [−0,0037; −0,0024] | 0,783 / 0,783 |
| odbiory | −0,0026 | [−0,0031; −0,0020] | 0,793 / 0,793 |
| celne | −0,0017 | [−0,0025; −0,0010] | 0,743 / 0,741 |
| spalone | −0,0018 | [−0,0028; −0,0007] | 0,700 / 0,700 |
| asysty | −0,0001 | [−0,0005; +0,0001] | 0,613 / 0,614 |

Starty lepsze na 5 z 6 rynków, asysty bez różnicy.

## Pomiar 2: metoda refitu

Replay bez reguły startów, dopasowany tą samą drogą (mała baza, tylko
wiersze zawodników — w `fit_confidence` nie wchodzą do żadnej puli),
odtwarza zainstalowane krzywe z 2026-10-08 w granicach ~1 pp przy ~20%
większej liczbie wierszy (cache urósł). Nowe krzywe (starty) są wyżej, np.
strzały p 0,75–0,80: 0,708 → 0,744; odbiory p 0,85–0,875: 0,729 → 0,760.

## Pomiar 3: co by się drukowało (10-05..10-10, poza próbą dla krzywej)

Prawdziwe linie Superbetu z tych dni, zawodnik wyjściowy, p z próbki startów
(replay), pewność z krzywej liczonej **bez ocenianych meczów**, line evidence
dopasowane na 10-12 (nowe krzywe, wiersze po usunięciu ławki), bramki
kuponu (pewność ≥ 0,70, x ≥ 0,90, krzywa `market:` n ≥ 300):

| grupa | n (mecze) | pewność | trafione | kurs implikuje | ROI [95%] |
|---|---|---|---|---|---|
| pewność ≥ 0,70 | 331 (70) | 0,766 | 0,804 | 0,920 | −12,7% [−17,5; −8,2] |
| **drukowałyby się** | **49 (38)** | 0,794 | 0,755 | 0,844 | **−10,3% [−27,2; +4,4]** |
| — strzały | 37 (30) | 0,801 | 0,811 | 0,853 | −4,8% [−20,5; +10,3] |
| — odbiory | 10 (9) | 0,780 | 0,600 | 0,831 | −27,1% |
| nogi drużynowe tymi samymi bramkami | 7 923 (987) | — | 0,801 | 0,826 | −3,0% [−4,6; −1,3] |

- Krzywa nie zawyża: przy pewności ≥ 0,70 deklaruje 0,766, trafione 0,804.
- Superbet kwotuje te linie krótko: kurs implikuje ~0,84–0,92 przy
  trafieniach ~0,76–0,80, więc bramka x ≥ 0,90 przepuszcza nogi z
  oczekiwanym wynikiem do −10%, i tyle wyszło.
- 49 nóg w 6 dni to mała próba; przedział ROI zawiera wynik nóg drużynowych.
  Zysku nie wykazano; gorszego wyniku też nie (statystycznie).

## Decyzja

Operator (2026-10-11, po tym pomiarze): `ONE_SIDED_SINGLES_FROM_UTC` =
2026-10-12 00:00Z. Wynik −10,3% [−27; +4] na 49 nogach to otwarte pytanie na
nowych danych, nie wykazana przewaga.

## E2E (10-09, 10-10, scratch)

Konfiguracja w scratchu (`SOFA_CONFIG_DIR`: przygotowane krzywe jako
zainstalowane, line evidence z 10-12), próbki zawodników odtworzone z cache w
nowej regule (starty + tokeny), `ONE_SIDED_SINGLES` włączone tylko w
procesie, zegar na czas oferty dnia. SHEET → CONFIDENCE → COUPON_ASSEMBLY →
PDF → audit_variants, rc 0 (audyt 1: C3 / U3 — cechy scratcha); **C2: 0**;
prawdziwe pliki: md5 przed = po.

- 10-09: 0 singli zawodników (żaden nie przeszedł bramek).
- 10-10: 6 piłkarskich singli (notka `PLAYER_STARTS_ONLY` na każdym, 1 po
  tokenach — Owusu); rozliczone SETTLE na prawdziwych składach: 4 WIN,
  1 LOSS, 1 Evander — nie było go w kadrze meczowej. Stary SETTLE zostawiał
  taką nogę nierozliczoną (`PLAYER_NOT_MATCHED`); teraz `PLAYER_NOT_IN_SQUAD`
  (nazwisko z próbki nieobecne we własnej kadrze, nikt nie pasuje po
  tokenach) — zwrot, w `void_legs`.

## Czego nie sprawdzono

- Prawdziwy SAMPLES z regułą startów i tokenów (most) — pierwszy przebieg
  2026-10-12; e2e liczone na próbkach odtworzonych z cache (przybliżenie
  historii: 3 135 różnic obserwacji wobec artefaktu dnia).
- Line evidence na pierwsze dni po zmianie liczy przesunięcia z arkuszy
  ze starą próbką (wszystkie występy) względem nowych krzywych.
