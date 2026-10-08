# Zależność w jointach piłkarskich i model goli (ścieżka A3, 2026-10-08)

Pomiar wyłącznie do odczytu. Skrypt: `scripts/sofa/measure_dependence_goals.py`
(testy: `tests/sofa/test_measure_dependence_goals.py`), surowe wyniki:
`docs/sofa/evidence/dependence_goals_2026-10-08.json`. Dane: tylko Sofascore
(spakowana historia `data/cache/football_history.pkl`, 911 704 meczów;
statystyki `/statistics` od 2024-10), bez cen Superbet, baza nietknięta.

Podział czasowy: TRAIN 2025-08-01..2026-05-31, TEST 2026-06-01..2026-10-07
(4 miesiące, >= 2). Przedziały ufności: bootstrap po meczach (1000 powtórzeń,
200 dla podziału miesięcznego). Zysk = log-loss modelu odniesienia minus
log-loss modelu testowanego (dodatni = testowany lepszy).

## (a) Zależność w jointach

Odtworzenie wejścia jointu jak w `calibrate_from_cache.football_joint_rows`:
środki po `K_CENTRE` (football 25) i `marginal_centred_stats`, próbka 10
meczów (gole: ta sama rozgrywka). Implementacja numpy kopuły Gaussa zgodna z
`joint._build` do 4e-9 (test). Zdarzenia: `both_over` (7 szczebli),
`handicap` (obie strony, 7 szczebli), `most` (gospodarz / gość / remis),
oceniane tam, gdzie obecny model daje p w [0.05, 0.95]. Testowe mecze:
próbka losowa 12 000 (goals: z 73 283, corners: z 16 452, SoT: z 14 075,
cards: 8 347 wszystkie).

Modele: `cur` (korelacja z `config/sofa_side_correlations.json`), `indep`,
`g_all` (korelacja reszt standaryzowanych zmierzona na TRAIN), `g_gap`
(po tercylach różnicy sił środków), `g_women`, `t4`, `t8` (kopuła t, ten sam
parametr co `g_all`, więc ta sama tau Kendalla - różni się tylko ogon).

Korelacja reszt (TRAIN) a config: goals -0.126 (config -0.012), corners -0.231
(-0.145), shots_on_target -0.107 (-0.003), **cards_points +0.126 (config: brak,
traktowane jak 0)**.

Zysk log-loss względem `cur` [95% CI]:

| baza | klasa | indep | g_all | g_gap | t4 | t8 |
|---|---|---|---|---|---|---|
| goals | both_over | -0.0002 [-0.0003,-0.0002] | +0.0012 [0.0006,0.0018] | +0.0016 [0.0010,0.0023] | +0.0008 [0.0003,0.0013] | +0.0010 [0.0005,0.0016] |
| goals | handicap | -0.00002 | -0.0003 [-0.0005,0.0001] | -0.0003 [-0.0006,0.0000] | +0.00004 [-0.0001,0.0002] | -0.0001 |
| goals | most | -0.00002 | -0.0003 [-0.0006,0.0001] | -0.0005 [-0.0009,-0.0001] | +0.0002 [0.0001,0.0003] | 0.0000 |
| corners | both_over | -0.0018 [-0.0023,-0.0012] | -0.00001 [-0.0004,0.0003] | +0.00001 | -0.00004 | 0.0000 |
| corners | handicap | -0.0007 [-0.0009,-0.0005] | +0.00001 [-0.0001,0.0001] | -0.00001 | -0.0001 [-0.0002,-0.0001] | +0.00001 |
| corners | most | -0.0002 [-0.0004,0.0000] | -0.00002 | -0.00003 | -0.0001 | 0.0000 |
| SoT | both_over | 0.0000 | -0.0008 [-0.0012,-0.0003] | -0.0006 | -0.0005 [-0.0008,-0.0002] | -0.0006 |
| SoT | handicap | 0.0000 | -0.0003 [-0.0004,-0.0001] | -0.0004 | -0.0001 | -0.0001 |
| SoT | most | 0.0000 | -0.0003 [-0.0004,-0.0001] | -0.0004 | +0.0001 | -0.0001 |
| cards_points | both_over | 0.0000 | +0.0016 [0.0009,0.0022] | +0.0016 | +0.0019 [0.0011,0.0026] | +0.0018 |
| cards_points | handicap | 0.0000 | +0.0028 [0.0024,0.0031] | +0.0028 | +0.0037 [0.0031,0.0043] | +0.0033 |
| cards_points | most | 0.0000 | +0.0011 [0.0007,0.0015] | +0.0011 | +0.0013 [0.0004,0.0022] | +0.0013 |

Wnioski:

* **Kopuła t nie pokonuje Gaussa w sposób istotny** (poza kartami, gdzie
  t4 o ok. +0.0009 lepsza od g_all w handicapie; CI obu zachodzą na siebie
  częściowo). Wszędzie indziej różnica < 0.0003.
* **Korelacja po klasie (przedział siły, kobiety) nic nie dodaje**: g_gap ~ g_all
  (różnice < 0.0005, w obie strony). Zmierzone korelacje na tercylach
  różnią się niewiele (corners -0.23/-0.22/-0.24).
* **Jedyny wyraźny zysk: cards_points** - config nie ma korelacji (`null`,
  za mało par), a zmierzona na 34 027 meczach to +0.126; zysk +0.001..+0.003
  log-loss, CI bez zera. To poprawka pliku konfiguracyjnego, nie struktury.
* Goals: zmierzona korelacja reszt poprawia `both_over` (+0.0012), a lekko
  psuje `handicap` / `most` - jedna liczba na metrykę nie służy wszystkim
  trzem klasom (sugestia: osobny parametr dla both_over). Zysk bezwzględny
  to ok. 0.2% log-loss.
* corners / shots_on_target: obecne wartości (-0.145 / -0.003) są nie
  gorsze niż ponownie zmierzone; niezależność jest istotnie gorsza dla
  corners (-0.0018, -0.0007).
* Wiersz SoT: korelacja reszt z TRAIN (-0.107) pogarsza wynik w TEST (-0.0003..
  -0.0008), choć liczona na 31 941 meczach - korelacja reszt standaryzowanych
  nie jest tym samym co optymalny parametr kopuły (podejrzenie, niezmierzone:
  wpływ nierównych zakresów p i błędu środka).
* Ograniczenie: priory `config/sofa_league_baselines.json` są dzisiejsze
  (lekki przeciek, jednakowy dla wszystkich modeli); środek bez
  `W_FOOTBALL_RATING`, jak w replay.

### Zależność między rynkami (Bet Builder)

`matrix`: 40 316 meczów z gole + rzuty rożne + SoT + strzały + kartki
(2025-08..2026-10), reszty względem oczekiwań ratingu as-of (35 714 meczów;
dla kartek wartości oczekiwana z `book.expected`, mimo że SHEET jej nie
miesza). CI 95% w pliku JSON; poniżej wartości punktowe (CI szerokości
ok. ±0.01).

Sumy meczu, korelacja surowa / reszty: gole-SoT 0.57 / 0.53; gole-strzały
0.30 / 0.24; gole-rożne 0.006 / -0.04; rożne-SoT 0.17 / 0.14; rożne-strzały
0.32 / 0.29; SoT-strzały 0.63 / 0.59; kartki z każdym -0.05..-0.06 / ok. -0.02.

Strony (reszty): gole własne - SoT własne +0.52; rożne własne - rożne rywala
-0.21; rożne własne - SoT własne +0.20; **gole własne - rożne własne -0.09
(CI -0.10..-0.08)**; SoT własne - SoT rywala -0.07; gole własne - gole rywala
-0.004.

Lifty (P(AB)/P(A)P(B), surowe, mieszają tempo ligi): suma goli > 2.5 i SoT >
7.5 1.30 [1.29,1.31]; gospodarz gole > 1.5 i SoT > 4.5 1.48 [1.47,1.50];
rożne gosp. > 5.5 i SoT > 4.5 1.24; rożne razem > 9.5 i SoT > 7.5 1.08;
suma goli > 2.5 i rożne > 9.5 1.00 [0.99,1.01]; rożne gosp. > 4.5 i gość >
3.5 0.87 [0.86,0.88]; BTTS 1.00.
Konsekwencja: gole x SoT tej samej strony są silnie zależne (kupon-builder
liczący je jako niezależne zaniża), gole x rożne praktycznie niezależne.

## (b) Model goli na środku z ratingu

Środek: `FootballForecast.centre("goals_for", ...)` as-of, rating
odtwarzany w czasie. TEST 83 247 meczów (58 410 LINKED), TRAIN 292 554.
Parametry z TRAIN: NB `r` = 6.98, dwuzmienna Poissona kappa = 2.9e-6
(lambda3 = kappa * min środków; czyli **zero** - ML nie widzi dodatniej
kowariancji), Dixon-Coles rho = -0.0129, DC na NB rho = -0.0068.
Zdarzenia: suma goli (0.5..4.5), gole drużyny (0.5..2.5), BTTS (both_over
0.5 i 1.5), 1X2, handicap +-0.5/1.5.

Zysk log-loss względem niezależnego Poissona [95% CI], wszystkie mecze:

| model | wszystkie zdarzenia | suma goli | gole druż. (dom/gość) | BTTS | 1X2 | handicap |
|---|---|---|---|---|---|---|
| bivariate Poisson | 0.0000 | 0 | 0 | 0 | 0 | 0 |
| Dixon-Coles (Poisson) | -0.00002 [-0.00002,-0.00001] | +0.00004 | 0 / 0 | -0.00006 | -0.0001 | -0.00003 |
| NB niezależny | +0.0023 [0.0021,0.0026] | +0.0013 | +0.0033 / +0.0025 | +0.0067 | +0.0009 | +0.0017 |
| DC na NB | +0.0023 [0.0021,0.0026] | +0.0013 | +0.0033 / +0.0025 | +0.0067 | +0.0008 | +0.0017 |

* DC nie daje nic (rho ~ -0.013, wyraźnie poniżej wartości z literatury;
  jedyny zysk to `suma goli > 0.5`: +0.00024 [0.00019,0.00029] - ok. 0.05%
  log-lossu, w dolnym szczeblu 0.5; reszta rungów 0). Na LINKED to samo.
  Stabilne w miesiącach (każdy miesiąc ~ -1e-5).
* Bivariate Poisson: kappa = 0 - brak dodatniej zależności do wychwycenia.
* **Przewaga NB (nadmierna dyspersja wokół środka ratingu) jest jedyna i
  wyraźna**, skoncentrowana na BTTS i górnych szczeblach (suma > 3.5/4.5:
  +0.0031/+0.0036; gole druż. > 0.5: +0.0046/+0.0034), a nie na niskich
  sumach (suma > 0.5/1.5: -0.0007..+0.0001, CI przy zerze). Produkcja już
  używa NB z wariancji próbki, więc to jest uwaga o modelu, nie nowość.
* Wygaszanie w czasie (stała wygładzania ratingu goli x0.5 / x2, Poisson,
  zysk względem produkcyjnej): x0.5 gorsze o -0.0049 [-0.0052,-0.0046];
  x2 -0.0014 [-0.0018,-0.0009] ogółem, ale lepsze na handicapie (+0.0026)
  i 1X2 (+0.0018), gorsze na sumie goli (-0.0067). Mieszane; nie ma
  wyraźnej poprawy. Nie testowano ważenia dniami (dostępny jest tylko
  wykładniczy współczynnik per mecz).

## Werdykt

| pytanie | werdykt |
|---|---|
| kopuła t zamiast Gaussa | NIE (nieistotne poza kartami, +0.0009) |
| korelacja per klasa / luka sił | NIE |
| ponowny pomiar korelacji cards_points (config null -> +0.126) | TAK (plik config; zysk +0.001..0.003) |
| corners / SoT / goals: odświeżenie korelacji | NIEJEDNOZNACZNE (goals: both_over +, handicap/most -; SoT -) |
| DC / bivariate Poisson dla goli | NIE |
| rozstrzygnięcie czasowego wygaszania | NIEJEDNOZNACZNE |

Nie zmierzono: wpływu na ceny Superbet i na kupon (brak cen historycznych),
zysku z centrum z `W_FOOTBALL_RATING` w jointach, remisu `most` osobno.
