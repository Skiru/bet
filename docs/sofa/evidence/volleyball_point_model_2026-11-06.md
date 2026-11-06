# Siatkówka: model wymian (rally-point) - pomiar 2026-11-06

Polecenie operatora 2026-11-06: "puść, niech się liczy". **Tylko pomiar:**
nic nie jest podłączone, żaden przełącznik, żadna instalacja, żaden plik
`config/` nie zmieniony, baza tylko do odczytu (`mode=ro`), sieć nie pytana.

## 0. Reguły zapisane PRZED obejrzeniem wyników (pre-rejestracja)

Ta sekcja powstała przed pierwszym przebiegiem na liniach Superbetu i przed
strojeniem.

**Model** (`src/bet/sofa/volleyball_point_model.py`):
- siła drużyny theta na skali logitu wymiany; P(i wygrywa wymianę przy
  własnym zagrywaniu) = sigmoid(logit(1 - so) + d), P(i wygrywa przy
  zagrywce rywala) = sigmoid(logit(so) + d), d = theta_i - theta_j + atut
  gospodarza; so = odsetek wygranych przyjęć (side-out) komórki (płeć),
  dopasowany największą wiarygodnością dokładnych wyników setów w łańcuchu
  Markowa (zagrywa zwycięzca poprzedniej wymiany);
- rating as-of: rozszerzony Kalman na udziale punktów meczu (oczekiwany
  udział = stacjonarny udział łańcucha), prior nowej drużyny = średnia
  drużyn jej rozgrywek (dopasowanie do przeciwnika i skurcz przez wariancję
  prioru, dryf w czasie, wagę obserwacji);
- symulacja wymiana po wymianie: sety do 25, piąty do 15, przewaga 2, best of
  five, zagrywka u zwycięzcy wymiany, pierwsza zagrywka seta 1 i 5 losowana,
  w setach 2-4 naprzemiennie; niepewność ratingu + forma meczu (jeden szok d
  na mecz) + szok seta; N = 4 000 na mecz, ziarno = id meczu.
- z tych samych symulacji: handicap i suma punktów, handicap setów,
  zwycięzca, liczba setów, dokładny wynik w setach, zwycięzca seta i punkty w
  secie (warunkowo na rozegranie), parzystość, przewagi w secie, "wygra
  seta", "dokładnie N setów". Ocena każdej linii semantyką SHADOW_SETTLE
  (`shadow.actual_value` / `grade`, push = poza; test równoważności).

**Strojenie:** stałe (wariancja prioru, dryf, waga obserwacji, wariancja
formy meczu i seta, so per płeć, atut) wyłącznie na historii z datą
< 2026-03-01 (walidacja one-step 2025-11-01 .. 2026-02-28, kryterium:
log-loss wyniku w setach + Brier progów sumy / handicapu punktów na
liniach kwantylowych). Linie Superbetu nie dotykają żadnej stałej.

*Zmiana reguły strojenia, zapisana przed hold-outem i przed jakąkolwiek
liczbą na liniach Superbetu (2026-11-06, ok. 11:00 UTC):*
- Kryterium wykonane w kodzie to log-wiarygodność **dokładnej sekwencji
  wyników setów** (punkty obu stron w każdym secie) meczów walidacji. Mieści
  ona i wynik w setach, i sumy oraz handicapy punktów, więc nie ma osobnego
  Briera na liniach kwantylowych.
- Pierwszy przebieg skończył `prior_var` i `drift_per_day` na dolnej
  krawędzi siatki (0.03 i 0.0001). Siatki rozszerzono za każdą krawędź
  (koordynator 11-06): `prior_var` do 0.002, dryf do 0, a także waga, forma,
  szok seta, atut i side-out. Drugi przebieg startuje od optimum pierwszego
  (`--warm-start`), na tym samym oknie treningowym. Do historii, krzywych i
  Superbetu idą stałe **drugiego** przebiegu
  (`volleyball_tune2.json`). Jeśli stała dalej leży na krawędzi, raport to
  mówi.

**Historia (bez cen):** walk-forward 2026-03-01 .. 2026-09-28 na wierszach
historii obecnego modelu (`data/line_evidence/rows_before_2026-11-06/
volleyball_history_fit.jsonl`: ta sama gra, linia, strona); Brier / log-loss
nowy - obecny per rodzina, przedziały po meczach.

**Superbet:** linie `runs/sofa/shadow/volleyball/<d>/settled.json` (WIN /
LOSS, `fair_p` = cena bez marży SHADOW), obecny p = wiersz
`volleyball_superbet_settled.jsonl` tego samego klucza (model wyniku jak
dziś, as-of). Mecz przypięty do Sofascore (orientacja `home_is_team1`).
Dev = 2026-09-29 .. 10-19 (tylko błędy mapowania), hold-out = 10-20 .. 11-05,
liczony **raz**. Brier na stronie kanonicznej (T1 / OVER / YES / ODD; dokładny
wynik - każdy wynik jako wiersz), nogi = wszystkie strony.

**Krzywe:** w katalogu roboczym, `sport_confidence.fit_curves` (EDGES,
MIN_BUCKET 200, `realised_lo95`) na wierszach walk-forward modelu na liniach
kwantylowych `synthetic_lines` (ta sama reguła co obecny fit), okno
2025-10-01 .. 2026-09-28. Obecny po krzywej: zainstalowana krzywa siatkówki
z `config/sofa_sport_confidence_calibration.next.2026-10-28.json` (dla
wszystkich dni, dla porównywalności). Bez dowodu linii w obu ramionach.

**Miary i werdykt** - jak w tenisie (`tennis_handicap_point_model_2026-11-06.md`
sekcja 0): Brier model - cena (nie-gorszy: górna granica <= +0.002), model -
obecny (lepszy: górna granica < 0), trafione - pewność przy >= 0.70 i
0.60-0.70 po krzywej (bez nad-obietnicy: górna granica >= 0, >= 30 nóg), ROI
przed i po podatku 12% tylko raport. Rodziny w werdykcie: `points_handicap`,
`points_total`, `set_handicap`, `exact_sets`, `set_points_total`; reszta
raportowana.

## 1. Stałe (strojenie, okno < 2026-03-01, walidacja 2025-11-01 .. 2026-02-28)

Historia: 63 449 meczów (Sofascore, cache tylko do odczytu), walidacja
13 567 meczów. Kryterium: log-wiarygodność dokładnej sekwencji setów na mecz.

| wariant | log-L / mecz |
|---|---|
| domyślne stałe, wymiany niezależne (bez side-outu) | -12.3929 |
| stałe wybrane, wymiany niezależne | -12.4354 |
| **stałe wybrane, łańcuch side-out** | **-12.1572** |

Wybrane (`volleyball_tune.json` = `volleyball_tune2.json`, identyczne):
so mężczyźni 0.68, kobiety 0.60, `prior_var` 0.06, dryf 0.0001 / dzień,
waga 1.0, atut 0.04, forma meczu 0.01, szok seta 0.02. Drugi przebieg na
siatce rozszerzonej za każdą krawędź (od optimum pierwszego) nie ruszył żadnej
stałej w dwóch rundach - **żadna stała nie leży na krawędzi**. Side-out jest
realny: łańcuch zagrywki daje +0.24 log-L na mecz wobec wymian niezależnych.

## 2. Historia bez cen (walk-forward 2026-03-01 .. 2026-09-28)

1 116 meczów z wierszami obecnego modelu (każdy też w historii modelu
wymian). Brier nowy - obecny, 95% bootstrap po meczach:

| rodzina | wiersze | Brier nowy | Brier obecny | nowy - obecny |
|---|---|---|---|---|
| points_handicap | 14 508 | 0.1193 | 0.1284 | -0.0091 [-0.0117, -0.0065] |
| points_total | 14 508 | 0.1420 | 0.1451 | -0.0031 [-0.0049, -0.0010] |
| set_handicap | 4 982 | 0.1719 | 0.1811 | -0.0092 [-0.0125, -0.0060] |
| exact_sets | 6 667 | 0.1223 | 0.1246 | -0.0023 [-0.0034, -0.0012] |
| winner | 1 116 | 0.1727 | 0.1847 | -0.0120 [-0.0171, -0.0073] |
| sets_total | 2 226 | 0.2007 | 0.2034 | -0.0027 [-0.0054, -0.0001] |
| points_odd_even | 1 116 | 0.2504 | 0.2511 | -0.0007 [-0.0017, +0.0004] |
| wszystko | 45 123 | 0.1414 | 0.1471 | -0.0057 [-0.0075, -0.0039] |

Na historii model wymian jest lepszy od obecnego w każdej rodzinie poza
parzystością (szum). Handicap punktów na liniach historii przy >= 0.70:
trafione - p = +2.7 pp (nowy) / +3.4 pp (obecny) - linie kwantylowe historii
są daleko od środka, więc ta liczba nie mówi o liniach Superbetu (sekcja 3).

## 3. Linie Superbetu

Krzywe modelu: `data/refit_2026-11-06_point_handicap_models/volleyball_curves.json`
(4 104 010 wierszy walk-forward na liniach kwantylowych, okno
2025-10-01 .. 2026-09-28; w katalogu roboczym, nic nie zainstalowane).
Odrzucone: 1 007 (dev) i 1 571 (całość) zdarzeń bez przypięcia do Sofascore lub
z niejasną orientacją - te same dla modelu, obecnego i ceny. Dev
09-29 .. 10-19 (592 mecze) służył tylko do sprawdzenia orientacji / mapowania
(błędów nie było).

**Hold-out 2026-10-20 .. 11-05, liczony raz.** Brier (strona kanoniczna,
wiersze z obecnym p), 95% bootstrap po meczach:

| rodzina | wiersze / mecze | nowy - cena | obecny - cena | nowy - obecny |
|---|---|---|---|---|
| points_handicap | 1 272 / 562 | +0.0156 [+0.0049, +0.0274] | +0.0204 [+0.0073, +0.0349] | -0.0048 [-0.0135, +0.0038] |
| points_total | 1 455 / 900 | +0.0072 [-0.0003, +0.0149] | +0.0124 [+0.0036, +0.0212] | -0.0052 [-0.0103, -0.0002] |
| set_handicap | 1 475 / 811 | +0.0034 [-0.0036, +0.0103] | +0.0091 [+0.0015, +0.0165] | -0.0057 [-0.0105, -0.0009] |
| exact_sets | 5 856 / 976 | +0.0018 [+0.0002, +0.0035] | +0.0032 [+0.0015, +0.0050] | -0.0014 [-0.0026, -0.0002] |
| set_points_total | 1 007 / 806 | +0.0020 [-0.0020, +0.0063] | +0.0089 [+0.0022, +0.0153] | -0.0069 [-0.0113, -0.0024] |
| winner | 1 061 / 1 061 | +0.0110 [+0.0035, +0.0182] | +0.0169 [+0.0090, +0.0249] | -0.0059 [-0.0104, -0.0014] |
| sets_total | 1 164 / 582 | +0.0026 [-0.0037, +0.0088] | +0.0011 [-0.0036, +0.0060] | +0.0016 [-0.0029, +0.0057] |
| wszystko | 20 365 / 1 062 | +0.0040 [+0.0011, +0.0067] | +0.0070 [+0.0041, +0.0098] | -0.0030 [-0.0049, -0.0011] |

Trafione - deklarowane (pp, bootstrap po meczach), nogi = obie strony, ROI
przy x >= 0.90 przed / po podatku 12% (tylko raport):

| rodzina | wariant | pasmo | n | dekl. | trafione - dekl. | ROI | po podatku |
|---|---|---|---|---|---|---|---|
| points_handicap | model surowy | >= 0.70 | 259 | 0.767 | -17.2 [-25.1, -8.8] | +3.0 | -9.4 |
| points_handicap | **model po krzywej** | >= 0.70 | 259 | 0.792 | **-19.7 [-27.8, -11.4]** | +3.0 | -9.4 |
| points_handicap | model po krzywej | 0.60-0.70 | 442 | 0.663 | -12.5 [-18.7, -6.6] | -7.1 | -18.2 |
| points_handicap | obecny po krzywej | >= 0.70 | 267 | 0.799 | -22.6 [-31.2, -14.3] | -0.5 | -12.4 |
| points_total | model po krzywej | >= 0.70 | 34 | 0.782 | -13.5 [-31.6, +2.9] | +16.7 | +2.7 |
| points_total | model po krzywej | 0.60-0.70 | 429 | 0.646 | -12.0 [-18.3, -5.4] | -5.5 | -16.9 |
| points_total | obecny po krzywej | >= 0.70 | 48 | 0.763 | -28.4 [-44.3, -11.4] | -12.2 | -22.8 |
| set_handicap | model po krzywej | >= 0.70 | 675 | 0.808 | -0.2 [-3.4, +2.8] | -0.7 | -12.6 |
| set_handicap | model po krzywej | 0.60-0.70 | 399 | 0.651 | -3.0 [-7.3, +1.7] | -1.4 | -13.2 |
| set_handicap | obecny po krzywej | >= 0.70 | 708 | 0.808 | -3.0 [-6.2, +0.2] | -3.6 | -15.2 |
| exact_sets | model po krzywej | >= 0.70 | 26 | 0.702 | +2.8 [-12.6, +18.2] | +11.0 | -2.3 |
| set_points_total | model po krzywej | >= 0.70 | 27 | 0.733 | -6.6 [-24.1, +9.6] | +13.4 | -0.2 |
| set_points_total | model po krzywej | 0.60-0.70 | 223 | 0.650 | -4.0 [-10.0, +1.9] | -0.7 | -12.6 |
| wszystko | model po krzywej | >= 0.70 | 3 356 | 0.796 | -1.3 [-3.2, +0.7] | +1.5 | -10.7 |
| wszystko | obecny po krzywej | >= 0.70 | 2 576 | 0.806 | -2.6 [-4.6, -0.5] | -2.3 | -14.0 |

## 4. Werdykt (reguły z sekcji 0)

| rodzina | nie gorszy od ceny (górna <= +0.002) | bez nad-obietnicy >= 0.70 po krzywej | lepszy od obecnego |
|---|---|---|---|
| points_handicap | **nie** (+0.0156) | **nie** (-19.7 pp) | nie (CI przez 0) |
| points_total | nie (+0.0072, górna +0.0149) | tak wg reguły (n 34, -13.5 pp, CI do +2.9) | tak |
| set_handicap | nie (górna +0.0103) | tak (-0.2 pp, n 675) | tak |
| exact_sets | nie (+0.0018, dolna > 0) | za mało nóg (26) | tak |
| set_points_total | nie (górna +0.0063) | za mało nóg (27) | tak |

**Żadna rodzina nie przechodzi wszystkich trzech warunków.** Cena Superbetu
jest lepsza od modelu wymian w każdej rodzinie (punktowo); model jest jednak
bliżej ceny niż obecny model wyniku w każdej rodzinie poza `sets_total`.

**Gdzie model zawodzi - handicap punktów.** To dokładnie dryf, który miał
naprawić (obecny -22.6 pp, audyt -24.8 pp). Model wymian obniża go tylko do
-19.7 pp po krzywej (-17.2 surowy) - różnica w Brierze nie jest istotna.
Krzywa z historii **podnosi** pewność (0.767 -> 0.792), bo na liniach
kwantylowych historii model jest niedoszacowany (+2.7 pp); na liniach
Superbetu (blisko środka rozkładu marginesu) przeszacowuje. Wniosek: problem
nie leży w strukturze seta (łańcuch side-out jest lepszy na historii), tylko
w rozrzucie marginesu punktów meczu - zbyt wąskim przy liniach, które
wystawia bukmacher; przyczyna (siła drużyny vs. liczba setów vs. dobór meczów
w ofercie) nie jest zmierzona - to podejrzenie.

**Gdzie model jest dobry:** `set_handicap` po krzywej skalibrowany przy
>= 0.70 (-0.2 pp na 675 nogach, obecny -3.0) i najbliżej ceny
(+0.0034, CI przez 0, ale górna granica +0.0103 > +0.002).

## 5. Reguła operatora 2026-11-06 i podłączenie (od 2026-11-07 00:00Z)

Po hold-oucie operator (przez koordynatora) ustalił regułę wiążącą wszystko:
instalować to, co lepsze od OBECNEGO estymatora; pobicie ceny nie jest
wymagane, a "gorszy od ceny" to fakt, nie powód odmowy. Rodzina przechodzi,
gdy na zamrożonym hold-oucie (a) Brier lub log-loss jest punktowo lepszy od
obecnego i (b) kalibracja >= 0.70 po krzywej nie jest gorsza od obecnej o
więcej niż 1 pp (gdy obie strony mają nogi).

| rodzina | Brier model - obecny | >= 0.70 po krzywej: model / obecny | krzywa modelu | wynik |
|---|---|---|---|---|
| points_handicap | -0.0048 | -19.7 / -22.6 pp | tak | **podłączona** |
| points_total | -0.0052 | -13.5 (n 34) / -28.4 pp | tak | **podłączona** |
| set_handicap | -0.0057 | -0.2 / -3.0 pp | tak | **podłączona** |
| exact_sets | -0.0014 | +2.8 (n 26) / brak nóg | tak | **podłączona** |
| set_points_total | -0.0069 | -6.6 (n 27) / brak nóg | tak | **podłączona** |
| winner | -0.0059 | +2.8 / +0.5 pp | tak | **podłączona** |
| set_winner | -0.0033 | +1.8 / brak nóg | tak | **podłączona** |
| points_odd_even | -0.0007 | brak nóg po obu stronach | tak | **podłączona** |
| sets_total | +0.0016 | -3.3 / +0.9 pp | tak | zostaje (gorszy) |
| set_extra_points | +0.0008 | - | nie | zostaje (gorszy) |
| team_sets_exact | +0.0010 | - | nie | zostaje (gorszy) |
| team_wins_set | -0.0054 | brak krzywej modelu | nie | zostaje (kalibracji nie da się ocenić) |
| set_points_odd_even, sets_count | -0.0002 / -0.0064 | brak krzywej modelu | nie | zostają (jw.) |

Podłączenie (`epochs.VB_POINT_MODEL`, 2026-11-07 00:00Z, grupa ledgera
"od 11-07"):
- SPORT_CONFIDENCE (`scripts/sofa/run_sport_confidence.py`, `DbForecaster`)
  dla linii `epochs.VB_POINT_MODEL_MARKETS` bierze p z
  `bet.sofa.vb_point_pricer` (model jak w pomiarze, stałe z
  `volleyball_tune2.json`, prognoza na start meczu z historii w cache, 4 000
  symulacji, ziarno = id Sofascore); noga ma `vb_point_model_rule` i
  `forecast_source: vb_point_model`; brak id strony = `NO_MODEL_P`.
- Krzywe: `config/sofa_sport_confidence_calibration.next.2026-11-07.json` =
  `.next.2026-11-06.json` z 16 kluczami siatkówki z krzywych modelu
  (`volleyball_curves.json`); plik i przełącznik idą razem (test).
- Dowody z linii: `data/line_evidence/volleyball_point_model_p.json.gz`
  (41 818 linii 09-29..11-05, z pomiaru + 128 policzonych ścieżką potoku);
  ścieżka potoku (`scripts/sofa/backfill_vb_point_p.py`, bez ziarna z
  pomiaru) daje identyczne p na 41 712 z 41 770 wspólnych linii (średnia
  |różnica| 0.00012; 58 różnych - inna historia meczu w bazie żywej niż w
  odchudzonej kopii pomiaru), 48 linii bez prognozy. Co rano krok 1b
  `refresh_line_evidence.py` dolicza nowe dni.
- E2E na kopii 2026-11-05 (zegar 09:00Z, ten sam kod, przełącznik wł. / wył.,
  dowody z linii przeliczone z zegarem 11-07 06:00Z): nogi siatkówki 23 -> 40
  (+18 / -1: 12 zwycięzca seta, 2 suma punktów, 2 handicap setów, 2
  zwycięzca); `NO_MODEL_P` 55 -> 7; zero zmian nóg spoza zakresu; znaczniki
  zgodne z zakresem; bez błędów.

**Czego to nie zmienia:** handicap punktów nadal przeszacowuje przy >= 0.70
(-19.7 pp po krzywej) - mniej niż obecny, ale linie te drukują się rzadko i
dowód z linii (offset / cap pasma) je obniża. Cena pozostaje lepsza od modelu
w każdej rodzinie.

## 6. Literatura (z pamięci, bez sieci - nie sprawdzone online)

- Ferrante M., Fonseca G. (2014), *On the winning probabilities and mean
  durations of volleyball*, Journal of Quantitative Analysis in Sports 10(2) -
  set i mecz jako łańcuch Markowa z prawdopodobieństwami wygrania wymiany przy
  własnej i cudzej zagrywce.
- Lee K.-T., Chin S.-T. (2004), *Strategies to serve or receive the service in
  volleyball*, Mathematical Methods of Operations Research 59 - model rally-point
  z zagrywką u zwycięzcy wymiany.
- Barnett T., Brown A., Clarke S. (2006 i n.), modele Markowa dla tenisa i
  siatkówki (rachunek szans setu i meczu z prawdopodobieństw wymiany).
- Ogólnie: modele setów jako łańcuchy Markowa z absorpcją (do 25 / 15, przewaga 2).

## 7. Pliki

- Model: `src/bet/sofa/volleyball_point_model.py` (nic go nie importuje poza
  skryptem pomiaru i testem); pomiar `scripts/sofa/measure_volleyball_point_model.py`;
  testy `tests/sofa/test_point_handicap_models.py`.
- Wyniki: `data/refit_2026-11-06_point_handicap_models/` -
  `volleyball_tune.json`, `volleyball_tune2.json`, `volleyball_history.json`,
  `volleyball_curves.json`, `volleyball_dev.json`, `volleyball_holdout.json`,
  `volleyball_sb_holdout.jsonl`.
