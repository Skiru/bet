# Zakłady na zawodników piłki v2 (2026-10-21) - faule na zawodniku, kartki, „którykolwiek z zawodników”

Przełącznik: **`epochs.FOOTBALL_PLAYER_PROPS_V2_FROM_UTC = None`** (wyłączony;
datę ustala sesja główna / operator). Znacznik wiersza SHEET:
`player_props_v2_rule = "player_props_v2"`. Skrypt pomiarów (tylko odczyt):
`scripts/sofa/measure_player_props_v2.py` (`proof`, `fouls-drawn`, `cards`).
Baza: `data/sofa.db` otwarta `mode=ro`.

## Werdykt

| rynek Superbetu | zdarzeń / tydz. | decyzja |
|---|---|---|
| „Zawodnik - liczba fauli na zawodniku” | 173 | **zbudowany** za przełącznikiem: `player_fouls_drawn_for`; krzywa historyczna przeszła bramkę, **wystawiona, nie zainstalowana** |
| „Zawodnik - otrzyma kartkę” / „czerwoną kartkę” / „1. kartkę” | 263 / 254 / 254 | **stop**: tylko „Tak”, P ≥ 0,70 nie zdarza się ani razu w 120 294 startach |
| „Którykolwiek z zawodników … powyżej X” (celne, strzały, faule, spalone, odbiory) | 96-237 | **stop**: iloczyn niezależnych zawodników przegrywa ze stałą częstością bazową |
| pary zawodników („… łącznie N+”) | ogon < 9 zdarzeń | pominięte (te same braki co wyżej, mały wolumen) |
| udział strzałów x minuty (pkt 5 zlecenia) | - | pominięte na polecenie koordynatora (osobny agent) |

## 1. Czy brak `wasFouled` to zero (`proof`)

Mecz-drużyna: suma `wasFouled` grających (minutesPlayed) wobec fauli
grających rywala. 25 550 meczów-drużyn z kluczem w cache.

| kanał Sofascore | meczów-drużyn | średni niedobór | suma = faule rywala | suma > faule rywala |
|---|---|---|---|---|
| pisze klucz każdemu grającemu (także 0) | 2 224 | 0,71 | 47,4% | 1,4% |
| pomija zera | 23 326 | 0,58 | 56,8% | 0,06% |

Niedobór nie jest śladem zgubionych kluczy: tam, gdzie Sofascore zapisuje
wszystkie zera, jest **taki sam** (nawet większy). To faule bez
poszkodowanego (ręka itp.). Stąd 58% „domknięcia” z `players.py` było
prawdą, ale złym pytaniem. Reguła (`players._zero_proven_by_opponent`):
brak klucza = 0 tylko, gdy klucz jest u co najmniej jednego grającego tej
drużyny i suma leży w [faule drużyny rywala − 4, faule drużyny rywala]
(`OPPONENT_BOUND_MAX_SHORTFALL = 4`: w kanale „pełnym” niedobór 0-4 w 99,8%).
Wobec statystyki drużyny z `/statistics`: reguła trzyma w 23 077 z 23 162
meczów-drużyn pomijających zera (99,6%) i 2 134 z 2 146 pełnych; reszta to
luka (`STAT_KEY_ABSENT`), nigdy zero. W replayu: 5 142 luk na 280 669
występów (1,8%).

## 2. Estymator i krzywa (`fouls-drawn`)

Replay repo (`calibrate_from_cache.build_player_rows`, jego starty w
ostatnich 10 meczach drużyny, środek = średnia próbki, spread SHEET), 10 499
meczów 2025-09-05..2026-10-19, OVER na liniach 0.5-4.5 (Superbet kwotuje
tylko „powyżej”). NB vs normalny przy tym samym środku i sd, wiersze, które
obie wersje wyceniają (357 095), 95% bootstrap po meczach:

| linia | n | zrealizowane | normalny | NB | Δ log-loss NB − normalny |
|---|---|---|---|---|---|
| 0.5 | 128 478 | 0,551 | 0,651 | 0,506 | −0,0162 [−0,0181; −0,0142] |
| 1.5 | 107 013 | 0,284 | 0,380 | 0,296 | −0,0290 [−0,0303; −0,0277] |
| 2.5 | 69 887 | 0,153 | 0,241 | 0,198 | −0,0238 [−0,0246; −0,0229] |
| 3.5 | 36 544 | 0,088 | 0,169 | 0,148 | −0,0154 [−0,0162; −0,0147] |
| 4.5 | 15 173 | 0,055 | 0,133 | 0,123 | −0,0093 [−0,0102; −0,0085] |
| razem | 357 095 | | | | **−0,0211 [−0,0221; −0,0202]** |

Wniosek: metryka idzie do `engine.NEGATIVE_BINOMIAL_METRICS` (nowa metryka,
żaden istniejący wiersz się nie zmienia).

Krzywa historyczna `player_fouls_drawn_for|OVER` (`new_market_gate`,
jednostronna): fit przed 2026-09-01 (320 709 wierszy), holdout
09-01..10-13 (51 419): przy wartości krzywej ≥ 0,70 **n 3 008 (1 241
meczów), krzywa 0,761, zrealizowane 0,779, luka +1,79 pp [+0,32; +3,33] -
PASS** (też wg dawnej reguły dwustronnej). Krzywa końcowa (wiersze przed
10-14) sięga 0,70 od kubełka 0,750-0,800 (lo95 0,725) do 0,925-0,950
(lo95 0,870). Wystawiona: `data/refit_player_props_v2_2026-10-21/
player_props_v2/` (`curves.json`, `rows.csv.gz`, `gate_report.md`);
instalacja (`install_new_market_curves.py --dir data/refit_player_props_v2_2026-10-21
--confirm`, grupa `player_props_v2`) zmienia to, co drukuje - **tylko za zgodą
operatora**. Bez niej noga dostaje `NO_LINE_EVIDENCE`.

## 3. E2E offline (10-14..10-20, zapisane dni, tylko odczyt)

Skrypt w scratchu (`e2e.py`): (1) każdy zapisany nieodczytany kurs dnia
(`unmapped_prices`) przez `classify_odd` wył./wł.; (2) najnowszy snapshot
rynku przez `OfferFetcher` (fałszywy klient) wył./wł.; (3) próbki z
historii, którą SAMPLES tego dnia czytał (id meczów z `03_samples.json`,
składy z cache) przez `build_player_samples`; kontrola: odtworzone tym samym
sposobem próbki `player_fouls_for` dnia = prawdziwe **5 520 / 5 520 wartość
w wartość**; (4) SHEET = `run_sheet.process_fixture` na nowych szczeblach;
(5) ocena z cache jak SETTLE (`run_settle._settle_player`).

| dzień | kursy przeniesione / bez zmian | mecze | szczeble wł. (wył.) | wiersze OVER | krzywa ≥ 0,70 | + x ≥ 0,90 |
|---|---|---|---|---|---|---|
| 10-14 | 16 572 / 373 609 | 21 | 3 308 (0) | 1 089 | 57 | 17 |
| 10-15 | 26 379 / 777 252 | 30 | 3 290 (0) | 980 | 62 | 15 |
| 10-16 | 13 274 / 792 336 | 11 | 1 865 (0) | 528 | 22 | 3 |
| 10-17 | 70 323 / 2 640 651 | 56 | 7 220 (0) | 2 481 | 113 | 31 |
| 10-18 | 35 076 / 1 628 576 | 36 | 6 370 (0) | 1 920 | 105 | 22 |
| 10-19 | 10 512 / 406 794 | 9 | 1 735 (0) | 467 | 36 | 11 |
| 10-20 | 5 558 / 353 353 | 10 | 1 391 (0) | 460 | 21 | 7 |

- Wyłączony: żaden kurs nie zmienia etykiety, 0 szczebli nowego rynku;
  włączony: przenoszą się wyłącznie kursy „Zawodnik - liczba fauli na
  zawodniku”, wszystkie na `player_fouls_drawn_for` OVER; 0 szczebli
  dwustronnych. Test `test_player_props_v2.py` sprawdza to samo na złotym
  OFFER (Villarreal - Napoli): wyłączony = złoty plik, włączony = te same
  szczeble + faule na zawodniku. SHEET z tą samą próbką bez nowych
  szczebli nie daje żadnego wiersza rynku.
- Pominięte w SHEET (razem): `THIN_SAMPLE`, `OUTSIDE_MODEL_RESOLUTION`,
  `NO_ENTITY_FOUND` (zawodnik bez dopasowania w składach) - jak u innych
  rynków zawodnika.
- Kolumna „krzywa ≥ 0,70 / x ≥ 0,90” to **szacunek przy zainstalowanej
  krzywej**; bez instalacji drukuje się 0 nóg (`NO_LINE_EVIDENCE`).

### Ocena na rozliczonych dniach 10-14..10-19 (cache, jego drużyna)

5 335 wierszy OVER z 159 meczów (zwroty: nie w składzie / z ławki - poza
liczeniem; `PLAYER_NOT_MATCHED` u ~6% to artefakt E2E - nie przekazano
nazw z reguły tokenów, SETTLE je przekazuje):

| | n | model p | zrealizowane | z ceny (1/kurs) |
|---|---|---|---|---|
| wszystko | 5 335 | 0,313 | 0,309 | 0,461 |
| linia 0.5 | 1 762 | 0,523 | 0,577 | 0,749 |
| linia 1.5 | 1 625 | 0,280 | 0,265 | 0,436 |
| linia 2.5 | 1 145 | 0,172 | 0,127 | 0,262 |
| krzywa ≥ 0,70 | 290 (126 meczów) | krzywa 0,761 | 0,731, luka −3,0 pp [−8,6; +2,2] | 0,880 |
| drukowałoby się (krzywa ≥ 0,70, x ≥ 0,90) | 78 (56 meczów) | krzywa 0,772 | 0,718; ROI −8,1% [−22,7; +6,7] przy śr. kursie 1,29 | |

Model jest skalibrowany na liniach Superbetu (6 dni - mało). Cena Superbetu
zawyża „powyżej” o ~17 pp na 0.5 - tyle samo co przy rynkach już
czytanych (rozliczone wiersze od 10-12: popełnione faule 0.5 zrealizowane
0,610 wobec 0,789 z ceny, strzały 0.5 0,537 wobec 0,750). Nie widać więc
różnicy liczenia między Sofascore a dostawcą Superbetu ponad to, co mają
inne rynki zawodnika - **podejrzenie, nie dowód** (brak zrzutu rozliczeń
Superbetu dla tego rynku).

## 4. Kartki zawodnika (`cards`) - stop

Superbet kwotuje tylko „Tak” (selekcja = nazwisko, kursy 1,64-12;
czerwona 8,7-60; „1. kartka” 3,8-60). Walk-forward od 2026-03-01: każdy
start zawodnika z ≥ 5 startami historii, P = jego kartki w ostatnich 10
startach skurczone do częstości pozycji (K = 10 startów; G 0,063, D 0,189,
M 0,168, F 0,121):

| | startów | zrealizowane | max P | P ≥ 0,70 | P ≥ 0,50 | Δ log-loss vs częstość pozycji |
|---|---|---|---|---|---|---|
| otrzyma kartkę | 120 294 | 0,156 | 0,536 | **0** | 5 | +0,0027 |
| czerwona | 120 294 | 0,008 | 0,156 | 0 | 0 | +0,0031 |
| 1. kartka meczu | 120 294 | 0,036 | 0,276 | 0 | 0 | +0,0072 |

Noga „Tak” nigdy nie osiąga progu 0,70, a własna częstość zawodnika nie
pobija nawet częstości pozycji. Rynek nie trafi do kuponu w żadnym
wariancie, więc nie jest budowany (zostaje w `unmapped_prices`).
Reguła Superbetu (czy czerwona liczy się do „otrzyma kartkę”, zwrot dla
rezerwowego) nie została potwierdzona w źródle - nie była potrzebna.

## 5. „Którykolwiek z zawodników … powyżej X” - stop

Superbet kwotuje tylko „powyżej X” (jeden kurs na linię). Model: P = 1 −
Π(1 − p_i) po zawodnikach wyjściowych obu drużyn z wierszem SHEET (replay jak
wyżej, bez ucinania 0,05/0,95), wynik = maksimum po **wszystkich**
grających (także rezerwowi; reguła Superbetu nieznana - wynik tylko po
wyjściowych jest niższy o 1-4 pp). Holdout 09-01.., Δ log-loss model −
stała częstość z okresu fitu:

| rynek | wynik (częstość) | model śr. | Δ log-loss [95%] |
|---|---|---|---|
| strzały > 3.5 | 0,725 | 0,600 | +0,108 [+0,077; +0,139] |
| strzały > 4.5 | 0,413 | 0,383 | +0,066 [+0,037; +0,096] |
| celne > 1.5 | 0,853 | 0,637 | +0,216 [+0,186; +0,249] |
| celne > 2.5 | 0,380 | 0,314 | +0,084 [+0,052; +0,114] |
| faule > 2.5 | 0,878 | 0,790 | +0,103 [+0,075; +0,136] |
| faule > 3.5 | 0,471 | 0,432 | +0,091 [+0,059; +0,124] |
| spalone > 1.5 | 0,378 | 0,293 | +0,258 [+0,204; +0,312] |
| odbiory > 3.5 | 0,738 | 0,666 | +0,028 [−0,001; +0,059] |
| odbiory > 4.5 | 0,447 | 0,397 | +0,046 [+0,017; +0,074] |

Przyczyna: wycenić da się średnio 5-12 z 22 wyjściowych (reszta bez
5 startów w historii cache), a skład nie jest znany, gdy SAMPLES pracuje.
Iloczyn zaniża niskie linie i zawyża wysokie. Bez pełnego składu i bez
znanej reguły (czy liczą się rezerwowi) rynek zostaje niewyceniony.

## Czego nie sprawdzono

- Pełny dzień z mostem (RESOLVE → PDF) z przełącznikiem włączonym - nie
  było mostu w tej sesji; E2E idzie przez funkcje etapów na zapisanych dniach.
- Reguła Superbetu dla fauli na zawodniku = reguła rynków zawodnika
  (zwrot, gdy nie wychodzi w składzie) - przyjęta z reguły operatora
  2026-10-11 dla całej rodziny „Zawodnik - liczba …”, niepotwierdzona osobno.
- CONFIDENCE na żywo z zainstalowaną krzywą (line evidence nowego klucza
  zaczyna od zera rozliczonych linii).
