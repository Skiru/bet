# Bramki próbki zawodników - przełącznik od 2026-10-17 (raport 2026-10-16)

**Decyzja operatora (2026-10-16):** „Dorzuć te nogi i włączymy od jutra” - `epochs.PLAYER_SAMPLE_GATES_FROM_UTC` = 2026-10-17 00:00Z (dzień budowy i zegar; 10-16 i wcześniejsze dni nie zmieniają się przy żadnym rebuildzie). Grupa ledgera „od 10-17” (ta sama granica co rynki wyniku).

## Co się zmienia

Wiersz piłkarski na jednym z sześciu rynków `confidence.PLAYER_SHAPE_GATE_MARKETS` (strzały, celne, faule, odbiory, asysty, spalone), który odcięłaby bramka kształtu próbki (`confidence.shape_gate_refusal`: `LINE_BEYOND_SAMPLE`, `MODE_LOSES`, `THIN_SAMPLE_FOR_BUILDER` < 10), przechodzi, jeśli ma >= `PLAYER_MIN_SAMPLE` (5) wartości. Noga ma `player_sample_rule` = pierwsza bramka, którą zdjęto, i nie wchodzi do Bet Buildera. Noga, którą bramki przepuszczają i tak, nie ma pola i zachowuje się jak dotąd (także w builderach). Strzały wg nogi / głowy / spoza pola (`/shotmap`, estymator `shot_detail`) i przechwyty (bez krzywej) - bez zmian.

## Dlaczego

Od 10-12 próbka zawodnika to jego starty w 10 ostatnich meczach drużyny (5-10 wartości), więc bramka 10 wartości przepuszczała tylko zawodnika z 10/10 startów. 10-15: z 19 018 wierszy zawodników 57 przeszło krzywą, line evidence i x przy cenie arkusza, bramki odcięły 54 (45 na sześciu rynkach), wydrukowało się 5 (w tym 2 dopiero przy świeżej cenie).

## Pomiar (szczegóły w dowodach)

- Historia (`player_sample_gates_2026-10-16.md`, OVER): grupy odcinane realizują się na swojej krzywej (+0.5..+1.5 pp), razem ~0.4 pp słabiej od przepuszczanych; `LINE_BEYOND_SAMPLE` -0.9 [-1.8, +0.1], próbka 5 startów -1.9 [-2.9, -0.8]. Bramki lekko wybierają, nie chronią wydrukowanej pewności.
- Linie Superbetu, walk-forward line evidence 10-12..10-15 (`player_line_evidence_2026-10-16.md`): bez bramek 55 nóg / 37 meczów, -5.9 pp [-15.9, +4.5], ROI -11.7% [-23.8, +1.2]; krzywa in-sample. Przy cenie, bez zmierzonej przewagi. Offset tylko z linii x >= 0.90 (V1) - odrzucony.

## E2E na 10-15

Czysta kopia artefaktów 10-15 (wejścia do CONFIDENCE), zegar zamrożony na 12:59Z (moment ostatniego `08_confidence.json` dnia), CONFIDENCE -> COUPON_ASSEMBLY -> PDF, przełącznik wyłączony vs włączony; prawdziwe pliki dnia nietknięte (md5 przed i po):

| | wyłączony | włączony |
|---|---|---|
| single w `11_coupon.json` | 1 492 | 1 532 |
| nowe single | - | +40 (strzały 23, faule 9, odbiory 8; `LINE_BEYOND_SAMPLE` 22, `THIN_SAMPLE_FOR_BUILDER` 18) |
| nogi stracone / zmienione | - | 0 / 0 |
| `player_sample_rule` na nodze, która była już wcześniej | - | 0 |
| buildery | 32 | 32 (identyczne) |
| `removed_by_reads` | 48 | 48 |

Nowe nogi: pewność średnio 0.782, kurs 1.231, najwcześniejszy start 16:45Z. 40 zamiast 45 z lejka dnia, bo o 12:59Z część meczów już się zaczęła albo miała nieświeżą cenę (lejek liczono na całym arkuszu, bez zegara). Wyłączony przełącznik = kod sprzed zmiany (HEAD d9a24b7b) bajt w bajt na nogach `08_confidence.json` (1 317 = 1 317).

## Przeglądy

Trzy rundy przeglądu (agent + własny), poprawki w commitach d86b6457, c1442c9c i kolejnym:
1. zakres zawężony do rynków `/lineups` (bez shot detail), znacznik tylko na nodze z faktycznie zdjętą bramką, jedna kolejność bramek (`shape_gate_refusal`), `audit_day_deep` czyta własną próbkę zawodnika, porównanie „vs PASS” w pomiarze w obrębie kierunku (pierwszy raport porównywał z pulą zdominowaną przez UNDER: -0.2 pp wyglądało jak +0.9), dokumentacja analityków i weryfikatora;
2. zakres = sześć zmierzonych rynków (przechwyty poza), `/sofa-analyze` nie wyrzuca weta analityka na zdjętą bramkę, test na nowych danych liczy też nogi zdjęte odczytem, próg kursu w pomiarze (60 -> 55 nóg), test na ścieżce stats-only;
3. liczby w dokumentach uzgodnione z raportami skryptów, drugi blok `audit_day_deep`, kryteria `T-PLAYER-SAMPLE-GATES` rozłączne (OBALONY: górna granica < -3 pp), ten raport.

## Sprawdzian

`T-PLAYER-SAMPLE-GATES` (PROPOSED): nogi z `player_sample_rule` (drukowane i zdjęte odczytem) od 10-17; POTWIERDZONY gdy dolna granica 95% (zrealizowane - pewność) > -3 pp przy >= 400 nogach / 200 meczach; OBALONY gdy górna < -3 pp - operator wyłącza przełącznik.
