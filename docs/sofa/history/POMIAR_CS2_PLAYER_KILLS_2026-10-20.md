# Pomiar: model linii graczy CS2 (player_kills; deaths / assists / headshots) - 2026-10-20

Pomiar tylko do odczytu. **Nic nie zostało zmienione ani zainstalowane** (config, `src/`, krzywe,
epoki bez zmian). Ciężkie przebiegi na kopii bazy `data/refit_2026-10-20_cs2pk/sofa_copy.db`
(`VACUUM INTO` 2026-10-20 12:56 lokalnie), żywa baza otwierana wyłącznie `mode=ro`.

**Werdykt w jednym zdaniu:** kilka poprawek wyraźnie poprawia model na historii (przedziały daleko
od zera), ale **żadna nie sprawia, że model dodaje cokolwiek ponad cenę Superbetu** na jego
prawdziwych liniach - więc nie ma przewagi do zainstalowania; jest co najwyżej poprawka kalibracji,
która dziś nic nie zmienia w druku. Proponuję nic nie włączać bez Twojej decyzji (pytania na końcu).

Skrypty (tylko odczyt, ruff + mypy --strict czyste, niezacommitowane):
`scripts/sofa/measure_cs2_player_lines.py` (replay historii), `scripts/sofa/measure_cs2_player_price.py`
(audyt vs cena), `scripts/sofa/measure_cs2_player_candidates.py` (kandydaci).

## Dane

| zbiór | zakres | wielkość |
|---|---|---|
| historia (replay walk-forward, bez lookahead) | 2025-11-15..2026-10-19, 336 dni (rozgrzewka od 2025-10-01) | 187 548 gracz-map na rodzinę, 8 538 meczów |
| ewaluacja kandydatów | 2026-04..2026-09-27, 6 mies. | ~100 500 gracz-map, 4 477 meczów na rodzinę |
| linie Superbetu rozliczone (tylko audyt) | 2026-09-28..2026-10-19, 20 dni | 9 414 linii (OVER), 127 serii; kills 2 369 |

Wierność replayu: na 989 rozliczonych liniach ekspozycji średnia |Δp| = 0.0022 vs zapisany
`model_p` (korelacja 0.996). Przedziały: bootstrap po meczu (serii), 95%, 1000 powtórzeń.

## P1. Czy krzywa CS2 sprzed 10-13 była liczona na modelu ekspozycji B12?

**Nie - i nie mogła być: rodziny graczy w ogóle nie wchodzą do fitu.**

- `cs2_walk_forward_rows` (`src/bet/sofa/sport_confidence.py:1139-1215`, `_cs2_series_rows` od
  `:1368`) produkuje wiersze tylko dla zwycięzcy mapy / meczu, serii, `map_team_rounds` i rund serii;
  nie ma gałęzi graczy ani team_kills.
- `fit_sport_confidence.py:155-171` fituje CS2 tylko na `history_fit`; klucze graczy pojawiają się
  wyłącznie w wierszach kontrolnych (`superbet_settled`), a `:229-231` oznacza każdy klucz bez krzywej
  `NO_FIT_BUCKET_WITH_N>=200`. Etykieta jest myląca: tych rodzin było **zero wierszy fitu**, a nie
  za mało w kubełku.
- Kolejność w czasie: fit `before` 2026-10-13, switch `CS2_COUNT_EXPOSURE_FROM_UTC` 10-13 18:10
  (`src/bet/sofa/epochs.py:1544`); `docs/sofa/evidence/cs2_kills_exposure_2026-10-13.md` podaje
  jeszcze "2026-10-14 00:00Z" - nieaktualne. B12 mierzył na liniach syntetycznych i żadnej krzywej
  nie zmienił.
- Dziś pewność tych nóg pochodzi wyłącznie z line evidence (`NO_LINE_EVIDENCE` poniżej 50 linii
  w kubełku).

Sam replay obecnego estymatora: patrz P2.

## P2. Rozkład p i kalibracja przy liniach takich jak Superbetu

**Jakie linie wystawia Superbet** (20 dni): jedna linia na gracza na mapę (mapa 1 lub 2, mapa 3
tylko 60 razy), dogrywka się liczy; kills 11.5-16.5 (dominanta 14.5); devig OVER w decylach
0.45-0.54; marża ~8% (kills 7.98%); mediana kursu 1.85.

**Emulacja linii Superbetu na historii.** Reguła dopasowana na 20 dniach wyłącznie do *ustawienia
linii* (żaden parametr prawdopodobieństwa nie pochodzi z naszych dni): `m20` = średnia gracza
z ostatnich 20 map, `pt` = p wygrania mapy z Elo drużyny minus 0.5.

| rodzina | reguła | holdout trafienie dokładne / w ±1 |
|---|---|---|
| kills | floor(5.70 + 0.588·m20 + 1.82·pt) + 0.5 | 40.0% / 90.1% |
| deaths | floor(7.99 + 0.460·m20) + 0.5 | 43.6% / 93.1% |
| assists | floor(1.69 + 0.649·m20 + 0.60·pt) + 0.5 | 69.9% / 99.8% |
| headshots | floor(1.01 + 0.855·m20 + 0.59·pt) + 0.5 | 59.0% / 96.5% |

Superbet ściąga średnią gracza do średniej pola i przesuwa ją o siłę drużyny.

**Obecny estymator na historii (IV-IX 2026, ~100 500 gracz-map, 4 477 meczów):**

| linia | rodzina | log-loss | AUC | nachylenie kalibracji | p ≥ 0.70: n / zrealizowane (średnie p) |
|---|---|---|---|---|---|
| własna średnia modelu (floor(exp_mean)+.5) | kills | - | - | 0.95 [0.85, 1.04] | 0 |
| emulowana Superbetu | kills | 0.68873 | 0.555 | **0.71** | 435 / 0.676 (0.722) |
| emulowana | deaths | 0.67995 | 0.588 | 0.99 | 1 735 / 0.749 (0.729) |
| emulowana | assists | 0.68747 | 0.549 | **0.65** | 299 / 0.649 (0.715) |
| emulowana | headshots (count_p) | 0.69303 | 0.520 | **0.33** | 115 / 0.591 (0.736) |

Przy własnej linii kills jest skalibrowany (kubełki 0.40-0.60 realizują 0.443 / 0.475 / 0.525 /
0.557 - sprawdzone lokalnie). Przy linii odsuniętej tak, jak odsuwa ją Superbet, jest
**przesadnie pewny** (kills, assists, headshots).

**Na prawdziwych liniach Superbetu** (kills 2 347 linii, 125 meczów): nachylenie 0.007
[-0.29, 0.27] - brak dyskryminacji; kubełek 0.60-0.70 zrealizował 0.508 przy obiecanym 0.632
(n = 455 stron, Wilson 0.46-0.55); tylko 23 z 4 694 stron ≥ 0.70. Liczby z line evidence
(player_kills|OVER: 1026/2181, 69/159, 10/16, 6/11, 1/2) odtworzone co do sztuki; uwagi: obejmują
**09-28..10-19 (20 dni)**, nie 10-05..10-19 (to `sheet_days` piłki / tenisa); kubełki są na
surowym p modelu; linie gracz × mapa nie są niezależne (deff ~1.6).

**Dlaczego brak kubełka z N ≥ 200:** mechanicznie - bo w `history_fit` nie ma ani jednego wiersza
gracza (próg i kubełki nie są winne; historia przy liniach z próbki wypełniłaby kubełek 0.70-0.75
w każdej rodzinie). Ekonomicznie - model nie jest "za płaski": przy uczciwej linii p ~ 0.5 to
oczekiwany wynik, a linia Superbetu leży w ±1 od naszej średniej w 92% (kills). Tam, gdzie się
z linią nie zgadzamy, jesteśmy zbyt pewni. Krzywa z historii na liniach syntetycznych powstałaby
głównie dla linii, których Superbet nie wystawia.

## P3. Gdzie model traci (kills, historia; zrealizowane minus p)

| przekrój | gracz-map / mecze | wynik |
|---|---|---|
| liczba rund (diagnoza, używa wyniku) | dogrywka 22 289 / 2 110; ≤ 19 rund 62 893 / 5 101 | +43 pp / -21 pp - główne źródło błędu, nieprzewidywalne przed meczem |
| udział w killach (proxy roli) | górny tercyl 62 799 / 8 488 | -3.3 pp [-3.8, -2.8]; dolny +2.9 pp [+2.5, +3.4] - gwiazdy przeszacowane |
| ADR (proxy) | tercyle | górny -2.4 pp [-2.8, -2.0]; dolny +2.2 pp [+1.7, +2.6] |
| first_kills_diff (proxy entry) | dolny tercyl | +1.5 pp [+1.0, +1.9]; HS% bez efektu |
| mapa | Inferno 22 844 / 2 393 | Inferno -3.2 pp [-4.0, -2.2], Dust2 -1.7; Ancient / Anubis / Nuke +1.6..+1.8 |
| doświadczenie gracza | < 20 map w karierze 10 487 / 2 055 | -4.3 pp [-5.6, -3.0], nachylenie 0.60 |
| stand-in (< 8 map w drużynie) | 6 810 / 1 896 | -0.9 pp, przedział obejmuje 0 |
| mapa 3 vs 1 | mapa 3 32 435 / 3 304 | +1.1 pp [+0.1, +2.0], nachylenie 0.83; mapa 1 -0.6 pp |
| Bo1 vs Bo3 | Bo1 6 421 / 682 | -2.0 pp [-3.6, 0.0]; Bo5 za cienkie (90 meczów) |
| pick / veto (proxy z puli map) | - | własna pula większa +0.6 pp [+0.1, +1.1]; danych o veto w bazie nie ma |
| różnica siły, poziom turnieju (proxy Elo), odpoczynek | - | brak istotnego biasu (±0.5..0.8 pp) |

Role, pick i poziom turnieju to proxy - zaznaczam, nie są to dane o roli.

**Defekt danych:** 239 wierszy `cs2_player_map` ma headshots > kills (24 mapy, wszystkie
2025-10-27, max 2030 - sprawdzone lokalnie). Rozdmuchują one dyspersję headshotów w modelu
ekspozycji (42-396). Werdykt B12 "headshots gorsze o +0.188" wygląda na artefakt tych wierszy:
po ich usunięciu ekspozycja bije count_p o -0.0070 [-0.0080, -0.0061]. Wiersze wypadną z okna
365 dni po 2026-10-27.

## P4. Dyskryminacja względem ceny (audyt na naszych rozliczonych dniach)

Cena: ostatni snapshot przed startem (`cs2.latest_pre_kickoff`, mediana 27 min przed), devig
proporcjonalny (potęgowy różni się o ≤ 0.002). p modelu: `settle_cs2.attach_model`
(`scripts/sofa/settle_cs2.py:507-567`) przeliczone przy rozliczeniu z historią do startu - 60 s
(**podejrzenie:** nie sprawdzono, że równa się liczbie przedmeczowej; replay zgadza się z nią do 0.002).

| rodzina | linie / serie / dni | AUC cena / model | log-loss cena / model | blend OOS (dzień po dniu) Δ vs cena [CI] |
|---|---|---|---|---|
| kills | 2 369 / 127 / 20 | 0.516 / **0.484** | 0.6927 / 0.7098 | +0.00020 [-0.00077, +0.00125] |
| deaths | 2 357 / 127 / 20 | 0.554 / 0.538 | 0.6882 / 0.7006 | +0.00101 [-0.00100, +0.00304] |
| assists | 2 325 / 125 / 19 | 0.547 / 0.529 | 0.6866 / 0.6964 | **+0.00088 [+0.00049, +0.00128]** (gorzej) |
| headshots | 2 363 / 127 / 20 | 0.543 / 0.513 | 0.6871 / 0.7003 | **+0.00059 [+0.00034, +0.00086]** (gorzej) |

(AUC i log-loss przeliczone przeze mnie lokalnie - zgodne.) Różnica model - cena jako ranking:
kills OVER w najwyższym kwintylu luki -5.2 pp [-10.7, +0.4]; ROI kills OVER przy luce > 0:
-16.8% [-24.5, -9.3] vs wszystkie OVER -11.6% [-16.3, -6.6]. **Obecny model nie odróżnia dobrej
linii od złej przy tej samej cenie; jest od niej gorszy.**

## Kandydaci (walk-forward na historii, linia emulowana)

Δ = kandydat minus obecny (ujemne = lepiej), przedział bootstrap po meczu, ~100 500 gracz-map,
4 477 meczów, 6 miesięcy; parametry wybierane wyłącznie na miesiącach przed ocenianym.

| kandydat | kills ΔLL [CI] · nachylenie · ≥0.70 n/zreal. | deaths ΔLL | assists ΔLL | headshots ΔLL |
|---|---|---|---|---|
| C1 czyszczenie wierszy (+ ekspozycja dla HS) | +0.00006 [-0.00002, +0.00014] | +0.00004 n.s. | +0.00002 n.s. | **-0.00704 [-0.00797, -0.00607]** |
| C2 K_SHARE (wybrane 8 / 8 / 16 / 4) | **-0.00145 [-0.00171, -0.00119]** · 0.87 · 178/0.697 | -0.00018 [-0.00037, -0.00001] | **-0.00236 [-0.00291, -0.00187]** | -0.00721 |
| C2b K wg doświadczenia | -0.00142 [-0.00166, -0.00118] | -0.00024 | -0.00236 | -0.00721 |
| C3 mnożnik mapy | -0.00040 [-0.00070, -0.00006] | -0.00098 [-0.00151, -0.00039] | **-0.00679 [-0.00780, -0.00576]** | -0.00752 |
| C4 skala dyspersji | -0.00027 [-0.00052, -0.00004] (znak zmienia się przy innej linii) | +0.00005 n.s. | -0.00032 | -0.00698 |
| C5 format / numer mapy | -0.00007 n.s. | n.s. | n.s. | -0.00700 |
| C6 okno udziału 10 map | +0.00091 (gorzej) | gorzej | n.s. | - |
| **C6 okno udziału 40 map + K** | **-0.00305 [-0.00357, -0.00253]** · 0.87 · 419/0.723 | **-0.00111 [-0.00135, -0.00085]** | **-0.00402 [-0.00464, -0.00341]** | **-0.01018 [-0.01120, -0.00899]** |
| COMBO (C1 + C2b + C3 + C4 + C5) | -0.00190 [-0.00234, -0.00147] · 0.92 | -0.00129 | **-0.00934 [-0.01044, -0.00821]** | -0.00768 |

W headshots większość efektu każdego kandydata to przejście count_p → ekspozycja po czyszczeniu.
Porównań: 11 kandydatów × 4 rodziny = 44 (plus 3 linie wrażliwości). Po Bonferronim zostają:
C2 / C2b, C6-40, COMBO, C3 na assists, C1 na headshots. Efekty są małe (~0.4% log-loss,
AUC +0.01..+0.05).

**Audyt najlepszych kandydatów na prawdziwych liniach Superbetu** (parametry z historii przed 09-28):

| rodzina | kandydat | AUC model / cena | blend OOS Δ vs cena [CI] |
|---|---|---|---|
| kills | C6-40 | 0.520 / 0.516 (obecny 0.497) | +0.00037 [-0.0020, +0.0030] |
| deaths | COMBO | 0.549 / 0.557 | +0.00047 [-0.0045, +0.0057] |
| assists | COMBO | 0.574 / 0.548 | -0.0052 [-0.0102, +0.0003] |
| headshots | C6-40 | 0.538 / 0.540 | +0.00013 [-0.0013, +0.0017] |

**Żaden kandydat nie daje modelowi niczego ponad cenę** - każdy przedział obejmuje zero.
Kandydaci zamykają za to większość istotnej straty obecnego modelu do ceny (kills: log-loss
model - cena z +0.0087 [+0.0033, +0.0141] do +0.0018 [-0.0034, +0.0069]). Assists COMBO / C3
skłania się we właściwą stronę, ale przy 44+ porównaniach to tylko podejrzenie.

## Co zadziałało, co odrzucono

- **Zadziałało na historii, odpada w audycie vs cena:** C6-40 (najlepszy we wszystkich
  rodzinach), C2 / C2b, COMBO, C3 (assists, deaths), C1 (tylko headshots).
- **Odrzucone:** C0 (kontrola), C1 dla kills / deaths / assists, C3 kills (nie przetrwa korekty),
  C4 (niestabilny znak), C5, C6-10 (gorzej).
- **Wpływ na druk:** żaden (podejrzenie - CONFIDENCE nie uruchamiano). Line evidence ma < 50 linii
  w każdym kubełku ≥ 0.70 poza deaths|UNDER 0.70-0.75 (60 linii, zrealizowane 0.58), więc nogi
  graczy CS2 i tak czytają `NO_LINE_EVIDENCE` albo spadają poniżej 0.70. Kandydaci raczej zwężają
  ogon ≥ 0.70 (kills 435 → 139-419), lepiej skalibrowany.

## Inne ustalenia

- **salazar** (id 1139762 i 2334643, obaj w drużynie 1090822 XI-XII 2025, mecz przeciw sobie
  2026-08-31): żadna ścieżka wyceny ani rozliczenia nie skleja graczy po nazwie.
  `cs2_engine.player_id` (`src/bet/sofa/cs2_engine.py:1042`) zwraca None przy imienniku w ostatnich
  20 mapach drużyny; `MapResult.player` (`src/bet/sofa/cs2.py:797-812`) zwraca None, gdy nazwa jest
  w obu składach (linia nierozliczana, nigdy źle rozliczona). Ryzyka resztkowe: `model_probability`
  szuka najpierw w team1 (`cs2_engine.py:~1466`) - imiennik w team1 dałby cenę innemu graczowi
  (rozliczenie by ją odrzuciło); `MapResult.players` kluczuje (strona, nazwa) (`cs2.py:794`) - jedna
  taka mapa w bazie (game 561991, "HS", id 1080307 i 1151715); `dossier.py:443-456` kluczuje po
  nazwie w drużynie (tylko wyświetlanie). W bazie 66 nicków ma > 1 id.
- Odchylenie samej ceny (wewnątrz próby, tylko jako sygnał): UNDER realizował powyżej devigu
  w każdej rodzinie (kills +2.4 pp, headshots +5.4 pp; HS UNDER ROI +2.6% [-1.3, +6.5]) - 20 dni,
  jedna rodzina na cztery, w granicach przypadku. **Podejrzenie**, niemierzone OOS.

## Propozycja

1. **Brak switcha ani refitu jako "przewagi"** - nic nie bije ceny.
2. Do decyzji (zmienia p modelu, nie druk): poprawka kalibracji C6-40 + C1 jako switch w
   `bet.sofa.epochs` od następnego dnia 00:00Z, z testem w `tests/sofa/`:
   okno udziału gracza 40 map jako nowa stała (dziś `deque(maxlen=MAX_SAMPLE)`,
   `cs2_engine.py:1226`, `MAX_SAMPLE` `:68` steruje też liczbami i rundami), `K_SHARE` (`:1100`)
   per statystyka 8 / 8 / 16 / 4, headshots do `EXPOSURE_FAMILIES` (`:1106`) oraz strażnik
   headshots > kills w `load_history` (~`:585`). Zysk: kills nachylenie 0.71 → 0.87, line evidence
   liczona na lepiej skalibrowanym p, model przestaje być istotnie gorszy od ceny. Ryzyko: nowa
   epoka line evidence CS2 graczy (kubełki zaczynają się od zera).
3. Strażnik headshots > kills to poprawka poprawności danych - może wejść osobno, z testem.

## Pytania do operatora

1. Czy włączyć poprawkę kalibracji z punktu 2 (switch od jutra 00:00Z), wiedząc, że nie daje
   przewagi nad ceną i dziś nic nie zmienia w druku?
2. Czy strażnik wierszy headshots > kills wpuścić od razu jako poprawkę poprawności (dotyka tylko
   modelu headshotów do 2026-10-27), czy razem ze switchem?
3. Czy etykietę `NO_FIT_BUCKET_WITH_N>=200` dla rodzin graczy CS2 zmienić na prawdziwy powód
   (np. `NO_HISTORY_ROWS`) - kosmetyka w `fit_sport_confidence.py:229-231`?
4. Czy poprawić datę switcha B12 w `docs/sofa/evidence/cs2_kills_exposure_2026-10-13.md`
   (10-14 00:00Z → 10-13 18:10Z)?
5. Czy commitować trzy skrypty `measure_cs2_player_*.py` i ten raport (ruff, mypy --strict,
   `check_test_registry.py` czyste)?

Nie sprawdzono: zgodności `model_p` z rozliczenia z liczbą przedmeczową; kursów zamknięcia;
niczego poza 20 dniami Superbetu; uruchomienia CONFIDENCE z kandydatem.

## Decyzja operatora i wdrożenie (2026-10-20)

Operator: "TAK" na pytania 1-4.

- `epochs.CS2_PLAYER_SHARE_FROM_UTC` = 2026-10-21 00:00Z: `cs2_engine.SHARE_WINDOW` 40,
  `K_SHARE_BY_STAT` 8 / 8 / 16 / 4, headshoty w ekspozycji (`ExposureBook.families`);
  SPORT_CONFIDENCE (`run_sport_confidence._cs2_counts`) i CS2_SETTLE (`settle_cs2.attach_model`).
  Grupa ledgera "od 10-21".
- Strażnik headshots > kills w `cs2_engine.load_history` - od razu (poprawka poprawności).
- `fit_sport_confidence.no_curve_reason`: `NO_HISTORY_ROWS` dla klucza bez wierszy fitu (od
  następnego fitu; zainstalowane pliki bez zmian).
- Data B12 w `docs/sofa/evidence/cs2_kills_exposure_2026-10-13.md` poprawiona (10-13 18:10Z).
- Test: `tests/sofa/test_cs2_player_share.py`.

**Weryfikacja wdrożenia** (prawdziwy silnik na kopii bazy, 1 000 losowych serii 2026-04..09,
22 499 gracz-map na rodzinę, linia emulowana, bootstrap po meczu), log-loss włączony - wyłączony:
kills -0.00265 [-0.00371, -0.00148], deaths -0.00075 [-0.00133, -0.00019], assists -0.00364
[-0.00486, -0.00237], headshots -0.01097 [-0.01324, -0.00874]; silnik minus kandydat C6-40 na
tych samych wierszach ≤ 0.0002 w każdej rodzinie. Bez switcha silnik odtwarza dotychczasowe p
(|Δp| > 0.01 na 2-9 z 22 499 wierszy na rodzinę). Różnice semantyczne bez znaczenia: kandydat
czyścił dla headshotów jeszcze 55 map (rundy niespójne / strona ≠ 5 graczy) - silnik nie, efekt
-0.00016 [-0.00039, +0.00005].
