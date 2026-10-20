# Zawodnicy w piłce: kto ma rację - nasze p czy cena Superbetu; model udziału w drużynie (2026-10-21)

Przełącznik: `epochs.FOOTBALL_PLAYER_SHARE_FROM_UTC` (**WYŁĄCZONY**, `None`; datę ustala sesja główna).
Marker wiersza: `player_share_rule` = `player_share_v1`. Kod: `src/bet/sofa/player_share.py`,
`scripts/sofa/run_sheet.py` (`player_share_centre`), pomiar `scripts/sofa/measure_player_share.py`,
testy `tests/sofa/test_player_share.py`. Plik konfiguracji przygotowany, **nie zainstalowany**:
`data/refit_player_share_2026-10-21/sofa_player_share.json` (cechy replayu obok: `features.jsonl.gz`).

## 1. Diagnoza: "model p ~0,51 przy cenie ~0,80"

Źródło: rozliczone wiersze `sofa_settled_row` (OVER) dni 10-12..10-19 złączone z `05_sheet.json`
dnia (p SHEET, kurs Superbetu z arkusza), krzywa = zainstalowana `config/sofa_confidence_calibration.json`
(bez line evidence). Rynki zawodników są **jednostronne** (tylko "powyżej"), więc 1/kurs zawiera całą
marżę - nie ma czego odvigować; poniżej 1/kurs surowe.

`player_shots_for` OVER (10 392 linie, 253 mecze):

| linia | N | trafienia | śr. p SHEET | śr. 1/kurs | śr. krzywa | traf. - p | traf. - 1/kurs | LL(p) - LL(1/kurs) |
|---|---|---|---|---|---|---|---|---|
| 0,5 | 2561 | 0,537 | 0,505 | 0,750 | 0,546 | +0,032 | −0,212 | −0,103 |
| 1,5 | 2713 | 0,331 | 0,345 | 0,526 | 0,332 | −0,014 | −0,195 | −0,083 |
| 2,5 | 2017 | 0,238 | 0,252 | 0,387 | 0,209 | −0,014 | −0,149 | −0,048 |
| 3,5 | 1367 | 0,152 | 0,194 | 0,302 | 0,141 | −0,042 | −0,149 | −0,054 |
| 4,5 | 857 | 0,111 | 0,153 | 0,236 | 0,090 | −0,042 | −0,125 | −0,027 |

Wg koszyka ceny (1/kurs) - trafienia [95% bootstrap meczów]: 0,7-0,8: 0,496 [0,464; 0,530] przy śr.
p 0,490 i 1/kurs 0,748; 0,8-0,9: 0,655 [0,623; 0,686] (p 0,589, 1/kurs 0,843); 0,9-1,0: 0,781
[0,746; 0,812] (p 0,723, 1/kurs 0,949).

`player_shots_on_target_for` OVER (5 259 linii, 276 meczów): linia 0,5 trafienia 0,348, p 0,331,
1/kurs 0,463; 1,5: 0,154 / 0,183 / 0,239. Faule (6 797): 0,5 trafienia 0,610, p 0,691, 1/kurs
0,789; krzywa 0,596. Odbiory (3 964): 0,5 trafienia 0,666, p 0,752, 1/kurs 0,873; krzywa 0,655.
Spalone 0,5: 0,306 / p 0,487 / 1/kurs 0,448. Strzały głową 0,5: 0,200 / p 0,215 / 1/kurs 0,378;
spoza pola 0,5: 0,336 / 0,335 / 0,522.

**Kto ma rację: co do poziomu - nasze p.** Na strzałach i celnych p jest skalibrowane w granicach
1-4 pp, a 1/kurs zawyża OVER o 15-21 pp na linii 0,5 i 1,5 (jednostronny rynek z marżą); log-loss
naszego p jest lepszy od 1/kurs o 0,05-0,10 nat na liniach 0,5-3,5. "p 0,51 przy cenie 0,80" to
marża Superbetu, nie błąd modelu - dlatego 10 504 wierszy odpada na progu 0,70: zawodnik naprawdę
oddaje ≥ 1 strzał w ~54%, a nie w 80%. Faule / odbiory / spalone: p zawyżone o 8-18 pp, ale krzywa
to koryguje (krzywa ≈ trafienia).

**Co do kolejności - cena wie więcej.** Regresja logistyczna trafienia na logit p i logit 1/kurs
(linie ≤ 2,5, 200 bootstrapów meczów): strzały b_p +0,342 [+0,261; +0,437], b_cena +0,591 [+0,505;
+0,672]; celne b_p +0,232 [+0,111; +0,361], b_cena +0,930 [+0,798; +1,057]; faule +0,131 / +0,785;
odbiory +0,304 / +0,463. Cena po odjęciu poziomu marży rozróżnia zawodników lepiej niż nasze p -
stąd brak przewagi (memory "player props never +EV" nadal obowiązuje).

**Gdzie p jest niskie na 0,5.** Nie przez rozmiar próbki (n 5-6: traf. 0,545 / p 0,507; n 9-10:
0,529 / 0,503) ani rozciągnięcie (bez: 0,545 / 0,514; s<0: 0,517 / 0,498; s>0: 0,545 / 0,497), tylko
przez **brak skurczu**: zawodnik ze średnią startów < 0,8 trafia 0,400 przy p 0,320 (N 1251), ze
średnią ≥ 1,5 0,781 przy p 0,807 (N 547). Środek zawodnika to surowa średnia 5-10 startów -
`NO_PRIOR: no baseline for player_shots_for` (w `config/sofa_league_baselines.json` nie ma ani
jednego klucza zawodnika, więc K_CENTRE nie działa); korekta rywala B15 zawodników nie obejmuje.
To regresja do średniej, którą naprawia skurcz udziału - punkt 2.

## 2. Model udziału (`bet.sofa.player_share`)

    centre = share x T
    share  = (jego strzały w jego startach + m x prior_pozycji) / (strzały drużyny w tych meczach + m)
    T      = środek wiersza shots_for jego strony z tego samego arkusza (rating W, game state, korekta rywala)
    SOT:   x (jego celne + m_acc x celność_pozycji) / (jego strzały + m_acc)

Rozrzut: ta sama reguła co dziś (`engine.sheet_predictive_sd`, wariancja próbki przeskalowana do
środka). Rozciągnięcie zawodnika nie jest stosowane do środka udziału (game state ma już T).

### 2a. Historia (out of sample)

`measure_player_share.py collect` na `data/refit_2026-10-17/sofa_replay.db` (tylko odczyt), mecze
z cache składów 2025-09-01..2026-10-12, starty zawodników (jak SETTLE), próbka = jego starty w 10
ostatnich meczach drużyny (`finish_history`), T przez `calibrate_from_cache.live_centre` (rating z
wagą rynku, venue prior, game state; środek próbki skurczony do bazy ligi z K rynku). Bez korekty
rywala B15 próbki drużyny (waga ratingu 0,85 - B15 dotyczy 15% środka). Czytane tylko próbki, w
których każdy start ma statystyki drużyny (live 96% obserwacji, 03_samples 10-12..10-19; stary cache
replayu ma zera-zaślepki przy `NO_STATISTICS`). Dopasowanie (m, m_acc, priory pozycji) siatką na
log-loss przed 2026-04-01, test 2026-04-01..2026-10-12; Δ log-loss B − A binarnie na linii, bootstrap
1000 meczów.

| rynek | trening / test (mecze testu) | m | linia | Δ log-loss [95%] |
|---|---|---|---|---|
| player_shots_for | 47 754 / 51 650 (5 066) | 40 | 0,5 | −0,02349 [−0,02549; −0,02164] |
| | | | 1,5 | −0,01968 [−0,02170; −0,01775] |
| | | | 2,5 | −0,01244 [−0,01408; −0,01083] |
| | | | 3,5 | −0,00755 [−0,00874; −0,00639] |
| player_shots_on_target_for | 38 015 / 41 086 (5 037) | 40, m_acc 40 | 0,5 | −0,02281 [−0,02509; −0,02050] |
| | | | 1,5 | −0,01538 [−0,01716; −0,01370] |
| | | | 2,5 | −0,00664 [−0,00777; −0,00556] |
| player_fouls_for | 49 593 / 53 851 | 80 (brzeg siatki) | 0,5 | +0,00021 [−0,00147; +0,00192] |
| | | | 1,5 / 2,5 | −0,0342 / −0,0379 |
| player_tackles_for | 48 185 / 50 635 | 80 (brzeg) | 0,5 | **+0,00510 [+0,00341; +0,00686]** |
| | | | 1,5 / 2,5 | −0,0238 / −0,0414 |

Priory udziału strzałów (trening): F 0,163, M 0,098, D 0,047, G 0,010, wszyscy 0,089; celność
F 0,420, M 0,362, D 0,364, wszyscy 0,382.

Kalibracja przy p ≥ 0,70 (test, surowe p): strzały 1,5 - A p 0,792 / traf. 0,726 (n 3 883), B p
0,784 / 0,769 (n 2 838); 2,5 - A 0,781 / 0,642, B 0,771 / 0,686. Przez zainstalowaną krzywę (≥ 0,70):
0,5 - A krzywa 0,799 / traf. 0,836 (n 12 067), B 0,794 / 0,850 (n 11 858); 1,5 - A 0,776 / 0,749,
B 0,772 / 0,798. Krzywa dopasowana na p A zaniża B o 2-6 pp (ostrożnie; refit krzywych na replayu
z udziałem by to podniósł). Celne: żadna linia nie dochodzi do krzywej ≥ 0,70 w żadnej z gałęzi.

**Faule włączone do pliku (poprawka 2026-10-21 po ponownym sprawdzeniu sesji głównej)**: na 0,5
bez zmiany (+0,00021, przedział obejmuje zero), na 1,5 / 2,5 wyraźnie lepiej (−0,0342 [−0,0374;
−0,0309], −0,0379 [−0,0412; −0,0349]); linie Superbetu (2b) to potwierdzają. m = 80 leży na brzegu
siatki - "prawie sam prior pozycji x środek fouls_for strony" (priory F 0,092, M 0,089, D 0,081,
G 0,010, wszyscy 0,085). **Odbiory nie są włączone**: na 0,5 gorzej z przedziałem powyżej zera;
pliku dla nich nie ma - SHEET ich nie ruszy.

### 2b. Linie Superbetu 10-12..10-19

Funkcja SHEET (`run_sheet.player_share_centre`) na artefaktach dni (03_samples, wiersze shots_for
z 05_sheet, strona przez `determine_side`), plik przygotowany powyżej, p A = p wydrukowanego arkusza.
Pokrycie: 13 818 z 15 651 wierszy dostaje udział; 1 830 bez wiersza shots_for strony (stary środek),
3 bez próbki; 3 259 bez pozycji (prior wszystkich).

| rynek | linie (mecze) | Δ log-loss B − A [95%] | 0,5 | 1,5 | 2,5 |
|---|---|---|---|---|---|
| player_shots_for | 9 392 (251) | −0,01775 [−0,02403; −0,01044] | −0,0247 [−0,0351; −0,0131] | −0,0148 [−0,0228; −0,0065] | −0,0155 [−0,0250; −0,0055] |
| player_shots_on_target_for | 4 426 (251) | −0,01683 [−0,02366; −0,00971] | −0,0187 [−0,0287; −0,0087] | −0,0144 [−0,0229; −0,0050] | −0,0131 [−0,0253; −0,0015] |

Średnie na 0,5 (strzały): trafienia 0,532, p A 0,501, p B 0,542, 1/kurs 0,749. Celne 0,5: 0,345 /
0,328 / 0,354 / 0,461.

Przez zainstalowaną krzywą, strzały, krzywa ≥ 0,70: A n 614, krzywa 0,777, traf. 0,769; B n 531,
0,766, traf. 0,793. Z dodatkowym x ≥ 0,90 przy cenie arkusza (bez line evidence i reszty bramek):
A 176 nóg, traf. 0,665, −32,3 j. (ROI −18%); B 83 nogi, 0,663, −14,8 j. (ROI −18%). **Poprawka
kalibracji, nie przewaga**: mniej nóg, ten sam zwrot na nogę.

**Faule** (`player_fouls_for`, ten sam skrypt, T = środek wiersza `fouls_for` strony): 6 797 wierszy
OVER, 6 235 z udziałem, 562 bez wiersza `fouls_for` strony; 1 527 bez pozycji. 6 235 linii / 192
mecze:

| linia | N | trafienia | p A | p B | 1/kurs | Δ log-loss B − A surowe p [95%] | przez krzywą [95%] |
|---|---|---|---|---|---|---|---|
| razem | 6 235 | 0,330 | | | | **−0,02389 [−0,03051; −0,01697]** | +0,00030 [−0,00224; +0,00289] |
| 0,5 | 2 161 | 0,607 | 0,692 | 0,730 | 0,790 | +0,00058 [−0,00816; +0,01071] | +0,00029 [−0,00431; +0,00518] |
| 1,5 | 1 999 | 0,279 | 0,365 | 0,375 | 0,459 | −0,03481 [−0,04623; −0,02450] | +0,00227 [−0,00277; +0,00698] |
| 2,5 | 1 335 | 0,122 | 0,201 | 0,161 | 0,260 | −0,03222 [−0,04169; −0,02255] | −0,00149 [−0,00397; +0,00063] |
| 3,5 | 585 | 0,031 | 0,132 | 0,073 | 0,157 | −0,05107 [−0,06286; −0,03831] | - |

Surowe p B jest lepsze w puli z przedziałem poniżej zera, 0,5 nie gorsze. Przez zainstalowaną krzywą
- neutralnie: krzywa faulów już naprawia poziom starego p (pewność A 0,328, B 0,328, trafienia 0,330).
Krzywa ≥ 0,70: A n 365, krzywa 0,729, traf. 0,726; B n 131, 0,715, 0,733. Z x ≥ 0,90: **A 57 nóg,
traf. 0,632, −10,7 j.; B 5 nóg, 0,800, +0,3 j.** - B prawie nie drukuje faulów (mało nóg, wynik
bez znaczenia statystycznego).

## 3. E2E (kopie dni 10-19 i 10-20, zegar = `created_at_utc` końcowego 08_confidence dnia)

Kopie w scratchu (bez wydruków / kuponu / blokad), DB tylko do odczytu, cache historii piłki skopiowany
obok. Trzy gałęzie SHEET: kod HEAD (`git archive`), nowy kod wyłączony, nowy kod włączony (plik
przygotowany w kopii `config/`); potem CONFIDENCE na off / on z `SOFA_NOW` = `created_at_utc`
końcowego `08_confidence.json` dnia (10-19 11:12:25Z, 10-20 06:57:47Z).

| | 10-19 | 10-20 |
|---|---|---|
| SHEET HEAD = nowy kod wyłączony (md5 05_sheet.json) | **identyczne** | **identyczne** |
| wiersze off / on | 34 351 / 34 489 | 50 250 / 50 234 |
| wiersze zmienione | tylko player_shots_for 1 414, player_shots_on_target_for 734, player_fouls_for 820; **0 innych** | 1 792 / 854 / 956; **0 innych** |
| wiersze tylko off / tylko on | 130 / 268 (dalekie linie strzałów / celnych / faulów przechodzą przez `OUTSIDE_MODEL_RESOLUTION`) | 252 / 236 (j.w.) |
| kolejność wspólnych wierszy | ta sama | ta sama |
| OVER strzały: udział / stary środek | 589 / 118 | 812 / 84 |
| OVER celne: udział / stary środek | 275 / 92 | 373 / 54 |
| OVER faule: udział / stary środek | 419 / 27 | 495 / 21 |
| marker `player_share_rule` | 24 929 / 24 929 wierszy piłkarskich | 30 287 / 30 287 |
| śr. Δp strzały OVER 0,5 / 1,5 / 2,5 | +0,055 / +0,020 / −0,005 | +0,007 / −0,018 / −0,034 |
| śr. Δp faule OVER 0,5 / 1,5 / 2,5 / 3,5 | +0,041 / +0,033 / −0,015 / −0,052 | +0,022 / −0,006 / −0,055 / −0,070 |
| singli CONFIDENCE off / on | 1 867 / 1 862 | 2 476 / 2 464 |
| nogi stracone / nowe / zmiana pewności | 7 / 2 / 0 - 6 `player_shots_for`, 1 `player_fouls_for` | 12 / 0 / 1 - 8 `player_shots_for`, 4 `player_fouls_for` |
| nogi inne niż zawodnicy stracone / nowe / zmienione | 0 / 0 / 0 | 0 / 0 / 0 |
| buildery off / on | 34 / 34 | 41 / 41 |
| rozliczone (10-19) | stracone: W 4 L 3, −2,34 j.; nowe: W 1, +0,26 j. | dzień nierozliczony |

Stracone nogi to głównie OVER 0,5 z pewnością 0,73-0,85 zawodników o krótkiej, wysokiej próbce
(np. obrońca Florian Lejeune, Lamine Yamal 2,5; faule: Adrian Bajrami, Armando Obispo, Pablo Rosario,
Evan N'Dicka) - udział ściąga ich ku priorowi pozycji. Nowe: Matheus Bidu 0,5 (0,798), Yacine Adli
0,5 (0,742). SHEET z kodem HEAD i nowym kodem wyłączonym, puszczone ponownie razem z gałęzią faulów:
md5 dalej identyczne (`sample_newest_days` zależy od zegara ściennego, więc gałęzie porównuje się
z tego samego dnia).

## 4. Ryzyka / otwarte

- Faule: m = 80 na brzegu siatki (większe m może być jeszcze lepsze - nie mierzone); przez
  zainstalowaną krzywą zmiana jest neutralna (krzywa faulów już poprawia poziom), w praktyce
  przełącznik prawie wyłącza druk faulów (57 -> 5 nóg 10-12..10-19).

- Krzywe zawodników są dopasowane na p A; B przez nie jest zaniżane o 2-6 pp przy ≥ 0,70 (ostrożnie).
  Refit krzywych na replayu z udziałem wymaga flagi replayu (`calibrate_from_cache` dziś udziału nie
  liczy) - nie zrobione.
- Line evidence rynków zawodników jest dopasowane na starym p - po włączeniu offsety mieszają oba p
  przez kilka dni.
- T w historii pomija korektę rywala B15 próbki drużyny (live ją ma, waga 15%).
- Pozycja tylko z próbki shot-detail; zawodnik bez niej czyta prior wszystkich (0,089) - dla
  napastnika zaniża (F 0,163); 3 259 z 13 818 wierszy 10-12..10-19.
- Wiersz zawodnika strony bez wiersza `shots_for` (Superbet nie wystawił strzałów drużyny) zostaje na
  starym środku (12% wierszy 10-12..10-19).
