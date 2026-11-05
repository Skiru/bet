# Sygnał ze składów Sofascore a cena Superbetu - pomiar 2026-11-05

Operator 2026-11-05: "Sprawdzić!". Pytanie: czy informacja o składzie z
Sofascore niesie coś, czego cena Superbetu nie ma? Dwa pomiary, tylko do
odczytu (`scripts/sofa/measure_lineup_price_signal.py`, test
`tests/sofa/test_measure_lineup_price_signal.py`). Nic nie drukuje się
inaczej, żadna krzywa, konfiguracja ani przełącznik nie zostały zmienione.

Wcześniej (nie powtarzane): `measure_lineup_absence.py` (10-23) - rzeczywisty
XI nie poprawia prognozy liczników drużyny poza próbą; gdy nie gra główny
strzelec, pozostali strzelają x1.049 swojego udziału (`player_share` tego
nie widzi, nigdy nie zestawione z ceną). bet365 jako druga cena i "Superbet
nieświeży ~30 min" - `slip_flow_backtest_2026-10-31.md`, nic.

## Reguły zamrożone PRZED obejrzeniem wyników

Zapisane w tym pliku przed pierwszym uruchomieniem analizy; nic poniżej tej
sekcji nie zmieniło reguł.

### Wspólne

- Podział dat: **dev** = dni (run_date) < 2026-10-21, **hold-out** = dni od
  2026-10-21 do 2026-11-04. Hold-out oglądany raz.
- Bootstrap po meczu (2000 losowań, przedział 95% percentylowy).
- Podatek 12%: ROI po podatku = średnia(wygrana x 0.88 x kurs - 1); próg
  opłacalności p x kurs >= 1.136.
- Werdykt "przewaga" tylko gdy dolna granica hold-outu ROI po podatku > 0.
  Inaczej "podejrzenie" (dolna granica różnicy > 0, ale nie ROI po podatku)
  albo "nic".
- BH (q = 0.10) w obrębie każdego pomiaru po komórkach hold-outu.
- Skład: rzeczywisty XI z cache po meczu (`sofa_event_stats.lineups_json`) -
  to **górna granica** (przed meczem znany najwyżej przewidywany / potwierdzony
  skład). `lineups_prematch.json` (od 10-23, tylko mecze czytane) liczony
  osobno jako pokrycie: ile nóg ma potwierdzony skład przed meczem.
- Historia strony: mecze drużyny z `sofa_listing_event` (dowolny `kind`)
  przed startem, <= 365 dni, ukończone, nie towarzyskie
  (`comparability.is_friendly_event`), z 11 zawodnikami podstawowymi tej
  drużyny w cache; najnowsze 10; wymagane >= 5, najnowszy <= 45 dni przed
  meczem.
- Główny strzelec T strony: zawodnik z >= 5 startami w oknie o największym
  udziale (jego strzały w jego startach / strzały drużyny w tych meczach,
  strzały drużyny = suma zawodników); udział >= 0.15, inaczej strona bez T.
- Regularny "core": start w >= 70% meczów okna; `core_missing` = liczba
  takich nieobecnych w XI.

### M1 - linie kolegów, gdy główny strzelec nie startuje

- Nogi: piłka nożna, `player_shots_for`, `player_shots_on_target_for`,
  `player_fouls_for` (faule = kontrola negatywna), kierunek OVER, wynik
  WIN / LOSS, `offered_odds` > 1, z `07_settled.json` dni 09-24..11-04
  (unikalny klucz zdarzenie|rynek|zawodnik|linia|kierunek).
- Zawodnik -> strona i id: XI po meczu, `players.match_player`, potem
  `match_player_by_tokens`, `match_player_by_surname` po startujących obu
  drużyn; brak lub dwuznaczność = odrzucony.
- Grupy: ABSENT = T strony nie w XI; PRESENT = T w XI. Nogi samego T
  wyłączone.
- Komórki: rodzina (strzały / celne / faule) x grupa x dev / hold-out.
- Miary: trafienia - 1/kurs (rynek jednostronny, bez partnera - bez
  de-vigu; marża w 1/kurs), **DiD** = (trafienia - 1/kurs)_ABSENT -
  (trafienia - 1/kurs)_PRESENT (test "Superbet nie koryguje"), ROI przed i po
  podatku, trafienia - nasza pewność (`08_refusals.json`, od 10-21).
- Czas ceny: start - `fetched_at_utc` szczebla z `04_offer.json` dnia.
  PRE >= 75 min (przed publikacją składu), POST <= 50 min (po). Tylko POST
  testuje, czy Superbet koryguje po opublikowanym składzie; PRE to górna
  granica (wymagałaby znajomości składu przed jego publikacją).
- Testy główne: DiD strzały i celne w hold-oucie; BH po 3 rodzinach.

### M2 - czy cena rusza się po potwierdzonym składzie (CLV)

- Nogi: drukowane single piłkarskie z `11_coupon.json` dni 10-05..11-04 z
  zapisem w `closing.jsonl` (ostatni zapis 3-30 min przed startem, kurs i
  partner > 1).
- Czas ceny wziętej t0: `printed_at_utc`, inaczej `fetched_at_utc` szczebla
  z `04_offer.json`, jeśli jego kurs = `odds_taken`; inaczej odrzucona.
  Analizowane tylko PRE (start - t0 >= 75 min); POST tylko liczone.
- CLV = kurs_wzięty x p_zamknięcia_fair - 1, p_fair = (1/kurs) / (1/kurs +
  1/partner) zamknięcia.
- Rodziny: PLAYER (`player_*`), SHOTS (rynek zawiera "shots"), GOALS (zawiera
  "goals"), OTHER.
- Kierunek wiadomości (rzeczywisty XI, górna granica):
  - rynek `_for` z drużyną w `subject`: OVER korzystny gdy przeciwnik
    core_missing >= 1 i własna 0; UNDER korzystny gdy własna >= 1 i
    przeciwnik 0; odwrotnie = niekorzystny; obie 0 = NEUTRAL; obie >= 1 =
    MIXED (poza testem);
  - `player_*` OVER: korzystny, gdy T jego strony nie startuje (i to nie on);
  - totale (bez strony): ANY_MISSING (którakolwiek strona core_missing >= 1)
    vs NONE - opisowo, bez kierunku.
- Test: CLV(korzystne) - CLV(NEUTRAL) w rodzinie i CLV(korzystne) samo; ROI
  przed / po podatku z wyniku (`07_settled.json`), trafienia - p_fair ceny
  wziętej (de-vig ze szczebla 04_offer, gdy kurs się zgadza), trafienia -
  pewność nogi.

<!-- wyniki dopisane po uruchomieniu; reguły powyżej bez zmian -->

## Wyniki

Uruchomienie: `measure_lineup_price_signal.py --only m1` i `--only m2`
(2000 losowań, bez sieci, DB tylko do odczytu). Liczby w punktach
procentowych (pp) lub % ROI; [przedział 95%, bootstrap po meczu].

### M1 - populacja

70 915 nóg OVER (strzały 33 463, celne 16 541, faule 20 911), dev 25 dni
(09-24..10-20), hold-out 15 dni (10-21..11-04), ok. 1 040 meczów (największa
rodzina, celne: 528 dev + 513 hold). Odpadło: 12 118 nóg samego T, 9 746 nóg
stron bez T (historia < 5 meczów albo udział < 0.15), 6 789 zawodników
nieodnalezionych w XI, 144 duplikaty.

Czas ceny (`04_offer` fetched_at -> start): PRE 43 094, POST 5 661, MID 1 163,
UNKNOWN 20 997 (kurs szczebla w ostatnim `04_offer` inny niż rozliczony albo
brak szczebla). **Cena w ogromnej większości sprzed publikacji składu** - więc
wynik PRE to górna granica: wymagałby znajomości XI zanim jest opublikowany.

| komórka | nogi / mecze | trafienia | 1/kurs | trafienia - 1/kurs | ROI po podatku | trafienia - pewność (n) |
|---|---|---|---|---|---|---|
| dev strzały ABSENT | 4 347 / 222 | 0.330 | 0.504 | -17.4 [-19.4, -15.4] | -46.8 [-51.6, -41.7] | - |
| dev strzały PRESENT | 9 613 / 396 | 0.294 | 0.482 | -18.8 [-19.9, -17.6] | -54.6 [-57.0, -52.2] | - |
| hold strzały ABSENT | 6 095 / 223 | 0.303 | 0.474 | -17.1 [-18.5, -15.7] | -52.2 [-55.6, -48.4] | +6.7 [+4.8, +8.8] (2 819) |
| hold strzały PRESENT | 13 408 / 416 | 0.273 | 0.469 | -19.7 [-20.7, -18.7] | -57.2 [-59.3, -54.9] | +3.2 [+1.8, +4.6] (6 779) |
| dev celne ABSENT | 2 169 / 245 | 0.242 | 0.357 | -11.5 [-13.5, -9.5] | -45.0 [-51.4, -38.5] | - |
| dev celne PRESENT | 4 891 / 452 | 0.219 | 0.332 | -11.4 [-12.6, -10.0] | -49.9 [-53.5, -45.6] | - |
| hold celne ABSENT | 2 893 / 227 | 0.207 | 0.328 | -12.1 [-13.6, -10.5] | -52.2 [-57.4, -46.5] | +6.6 [+4.3, +9.0] (1 441) |
| hold celne PRESENT | 6 588 / 440 | 0.191 | 0.325 | -13.4 [-14.4, -12.5] | -56.3 [-59.2, -53.3] | +5.1 [+3.8, +6.4] (3 634) |
| hold faule ABSENT | 3 682 / 148 | 0.324 | 0.494 | -17.0 [-18.7, -15.2] | -48.9 [-52.7, -44.9] | +2.2 [-0.1, +4.7] (2 019) |
| hold faule PRESENT | 8 474 / 280 | 0.327 | 0.499 | -17.2 [-18.4, -16.0] | -49.0 [-51.6, -46.4] | +2.4 [+0.9, +3.8] (5 071) |

ROI przed podatkiem: hold strzały ABSENT -45.6 [-49.6, -41.4], celne ABSENT
-45.7 [-51.6, -39.2]. Rynki jednostronne - bez partnera nie ma de-vigu;
"trafienia - 1/kurs" zawiera marżę (~17-20 pp na strzałach), dlatego testem
"Superbet nie koryguje" jest różnica ABSENT - PRESENT (DiD):

| DiD (ABSENT - PRESENT) | dev | hold-out | BH (hold, 3 rodziny) |
|---|---|---|---|
| strzały | +1.4 [-1.0, +3.8] | **+2.6 [+0.7, +4.5]**, p = 0.003 | odrzuca |
| celne | -0.1 [-2.6, +2.2] | +1.3 [-0.5, +3.2], p = 0.08 | nie |
| faule (kontrola) | -1.4 [-4.0, +1.1] | +0.2 [-2.0, +2.3] | nie |
| strzały, tylko cena POST | -6.0 [-12.9, -0.1] (52 mecze) | +6.8 [-1.6, +18.2] (51 meczów) | - |
| celne, tylko cena POST | -3.1 [-9.4, +3.0] | +0.7 [-6.1, +8.8] | - |

Pokrycie `lineups_prematch` (potwierdzony skład przed meczem): 2 757 nóg M1
(293 w ABSENT) - za mało meczów na osobną komórkę; nie analizowane.

**Werdykt M1: przewagi nie ma.** Hold-out ROI po podatku w najlepszej
komórce -52.2% [-55.6, -48.4] - o rząd wielkości od zera; marża propsów
(~17-20 pp) przykrywa każdy sygnał składu. **Podejrzenie** (słabe): przy
cenie sprzed składu linie strzałów kolegów realizują się o ~2.6 pp lepiej,
gdy główny strzelec nie startuje (zgodne z x1.049 z 10-23), w dev
niepotwierdzone (+1.4, przedział przez zero), celne i faule nic. Czy Superbet
koryguje PO opublikowanym składzie - nie da się powiedzieć: cen POST jest ok.
50 meczów na połowę, a znaki dev / hold są przeciwne. Nasza pewność: w
hold-oucie nogi strzałów kolegów przy nieobecnym T realizują się +6.7 pp nad
pewnością wobec +3.2 pp przy obecnym T (różnica ~3.5 pp, przedziały ledwo
rozłączne, różnica nie testowana osobno) - `player_share` nie widzi
nieobecności, jak w pomiarze 10-23; to poprawka kalibracji, nie przewaga nad
ceną.

### M2 - populacja

Drukowane single piłkarskie z zamknięciem 3-30 min przed startem: cena
wzięta PRE (>= 75 min przed startem) 59 034 nóg, POST 2 353, MID 1 438, bez
czasu 14. Z PRE: 24 277 (41%) bez składu w cache (niższe ligi), 3 554 rynków
`_for` bez dopasowanej drużyny -> **31 203 nóg**, ok. 710 meczów / 16 dni dev
i ok. 900 meczów / 15 dni hold-out. Rodzina PLAYER: **0 nóg** (propsy prawie
nigdy się nie drukują) - pytanie o propsy w M2 nie ma danych.

CLV = kurs wzięty x p_fair zamknięcia - 1. Przy niezmienionej cenie to
minus marża (ok. -7..-10%), więc miarą jest różnica grup, nie poziom.

| CLV hold-out | nogi / mecze | CLV | trafienia - p_fair wziętej | ROI po podatku |
|---|---|---|---|---|
| GOALS FAVOURED | 115 / 68 | -7.49 [-7.78, -7.20] | -1.1 [-9.6, +6.7] | -20.9 [-30.3, -12.2] |
| GOALS DISFAVOURED | 89 / 54 | -7.97 [-8.35, -7.62] | +2.5 [-6.7, +10.4] | -15.9 [-25.4, -7.6] |
| GOALS NEUTRAL | 27 / 10 | -8.28 [-9.13, -7.05] | +1.6 [-16.5, +17.9] | -18.1 [-38.3, +0.2] |
| GOALS totale ANY_MISSING | 3 099 / 613 | -7.19 [-7.28, -7.09] | +2.5 [+0.8, +4.3] | -15.7 [-17.6, -13.8] |
| GOALS totale NONE | 138 / 28 | -7.76 [-8.16, -7.36] | +3.9 [-5.7, +12.2] | -14.5 [-25.1, -5.6] |
| SHOTS FAVOURED | 24 / 19 | -9.75 [-10.43, -9.17] | +1.8 [-21.2, +18.5] | -15.6 [-37.5, -0.0] |
| SHOTS totale ANY_MISSING | 834 / 307 | -9.17 [-9.42, -8.90] | +3.7 [-0.5, +7.5] | -15.3 [-19.8, -11.0] |
| OTHER totale ANY_MISSING | 10 697 / 636 | -8.08 [-8.13, -8.03] | +3.1 [+2.1, +4.1] | -15.9 [-17.0, -14.9] |

| różnica CLV | dev | hold-out | BH (hold, 6 testów) |
|---|---|---|---|
| GOALS FAV - NEU | +0.02 [-1.74, +3.10] | +0.80 [-0.64, +1.74] | nie |
| GOALS ANY - NONE (totale) | +0.07 [-0.51, +0.63] | +0.58 [+0.14, +1.00] | odrzuca |
| SHOTS FAV - NEU | +0.84 [-1.23, +2.19] | -4.25 [-4.95, -3.64] (NEU = 1 noga) | nie |
| SHOTS ANY - NONE | +1.33 [-0.38, +3.86] | +0.38 [-1.00, +1.55] | nie |
| OTHER FAV - NEU | +0.15 [-1.24, +2.58] | +0.48 [-0.34, +1.75] | nie |
| OTHER ANY - NONE | -0.02 [-0.41, +0.43] | +0.12 [-0.08, +0.33] | nie |

Uwaga do reguły (zamrożonej, nie zmienianej): brak >= 1 regularnego
zawodnika (start >= 70% okna) jest normą, więc NEUTRAL (obie strony w
komplecie) ma 1-30 nóg, a MIXED dominuje - test FAV - NEU jest przez to
prawie ślepy. Opisowo, poza regułą: FAV - DISFAV (CLV) hold GOALS +0.48,
OTHER -0.11, SHOTS +0.34; dev GOALS +1.68, OTHER +0.80, SHOTS +0.20 - bez
przedziałów, nie jest werdyktem.

"Trafienia - p_fair wziętej" jest dodatnie w prawie każdej komórce (~+2..+4
pp) - to selekcja kuponu (krótkie ceny, pewność >= 0.70), znana i niezależna
od składu; ROI po podatku wszędzie ok. -15%.

**Werdykt M2: nic.** Jedyna różnica odrzucona przez BH (totale goli: CLV
+0.58 pp, gdy komuś brakuje regularnego) jest bez kierunku (nie wiadomo,
którą stronę zagrać), w dev zerowa (+0.07 [-0.51, +0.63]) i o rząd mniejsza od
marży; ROI po podatku -15.7% [-17.6, -13.8]. Ruchu ceny w stronę wiadomości o
składzie, którego nie dałoby się wytłumaczyć szumem, nie widać.

## Luki w danych (dokładnie)

- **Skład przed meczem:** `lineups_prematch.json` od 10-23, tylko mecze
  czytane przez analityków; we wszystkich sportach 59 potwierdzonych
  odpowiedzi w 13 dni, w piłce 31 potwierdzonych przed startem (najwcześniej
  66 min przed startem; niepotwierdzone widziane jeszcze 30-58 min przed).
  Plik trzyma tylko OSTATNIĄ odpowiedź na mecz (bez historii czasu). W M2 29
  meczów (748 nóg) ma potwierdzony skład - nie do analizy. Wszystkie wyniki
  powyżej opierają się na rzeczywistym XI po meczu = **górna granica**.
- **Ceny z czasem:** dla nóg niedrukowanych mamy jedną cenę (ostatni
  `04_offer` dnia, nadpisywany przy przebudowie); `closing.jsonl` zapisuje
  tylko drukowane nogi (propsów praktycznie brak). Nie ma pary "przed
  składem / po składzie" dla propsów zawodników ani dla niedrukowanych
  liczników drużyny.
- 41% drukowanych nóg PRE nie ma składu po meczu w cache (niższe ligi).

Co by to naprawiło (zbieranie, nie pomiar): (1) pętla podobna do
`capture_closing.py`, ale dla WSZYSTKICH szczebli piłkarskich meczów z
propsami (także `unmapped_prices`), dwa zrzuty: ok. 90 min i ok. 15 min przed
startem; (2) `lineups_prematch` pytany dla każdego takiego meczu co 10 min
od 75 do 30 min przed startem, append-only z `asked_at_utc` i momentem
pierwszego `confirmed: true`. Przy ~100 meczach z propsami dziennie dwa
tygodnie dają ~1 400 meczów z parą cen wokół potwierdzonego składu - wtedy
POST-DiD z M1 i CLV propsów z M2 dałoby się zmierzyć na danych, które były
znane przed startem. Bez tego pytanie "czy Superbet koryguje po składzie"
zostaje otwarte. Dwa koszty: ~2 x 100 zapytań Superbetu i ~500 zapytań
mostu dziennie.

## Weryfikacja

- `ruff` i `mypy --strict` na nowym skrypcie, `pytest
  tests/sofa/test_measure_lineup_price_signal.py` (9 testów) - czyste.
- Nie sprawdzono ręcznie: dopasowania nazw zawodników poza regułami
  `players.match_player*` (6 789 nóg odrzuconych), dopasowania nazw drużyn
  Superbetu do Sofascore poza dokładną równością (3 554 nóg M2 odrzuconych).
