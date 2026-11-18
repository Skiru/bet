# Pre-rejestracja: stawka meczu (stan tabeli) w modelu - hokej, koszykówka, siatkówka (2026-11-18)

**Status: GOTOWE DO ZAMROŻENIA.** Zamraża commit operatora (SHA tego pliku = spec SHA egzaminu). Zmiana czegokolwiek
po pierwszym spojrzeniu na walidację = nowe spojrzenie (G3); po egzaminie - zakazana (G4). Jedyny dopuszczony dopisek
po zamrożeniu: **Aneks A** (sekcja 13) - liczebności sezonów z backfillu, wyłącznie liczby, dopisane **przed**
policzeniem jakiegokolwiek wyniku.

Wzór: `schedule_context_prereg_2026-11-09.md` (struktura, reguła (c), tabela mocy, wcześniejsze spojrzenia). Zakres:
score model (`bet.sofa.score_model`, przez `sport_confidence`) i model wymian siatkówki
(`bet.sofa.volleyball_point_model` / `vb_point_pricer`). Piłka, tenis, CS2 - poza zakresem.

Stan wiedzy: żadna reszta (wynik - środek modelu) ani żaden wynik meczu badanego wg stanu nie był liczony. Co
policzono (sekcja 9): liczebności stron wg stanu, bramka formatu (tabela końcowa vs uczestnicy fazy pucharowej),
średnia i wariancja wyniku drużyny **łącznie dla wszystkich stanów** (tylko tabela mocy).

**Prototypy (dowód, nie kod pipeline'u):** `docs/sofa/evidence/stakes_sports_2026-11-18/` - `extract.py` (zrzut
kompaktowych wierszy z `sofa_listed_event`, `?mode=ro`), `seasons.py` (inwentarz lig-sezonów), `seasons_rules.py`
(reguły: słowa faz, wykluczenia, mapy konferencji, punkty, grupowanie sezonów), `states.py` (**moduł stanów**),
`formatcheck.py` (bramka formatu), `pooled.py` + `vbpts.py` (średnia / wariancja do tabeli mocy). Uruchamiane z
katalogu roboczego z `games.jsonl.gz`; kolejność: `extract.py` -> `states.py` (bez `keep.json`) -> `formatcheck.py`
-> `states.py` (z `keep.json`). sha256:

| plik | sha256 |
|---|---|
| `states.py` | `826dfdd092ee757cd9d08da11feacf5a32568572e08c9dba8d719f7400bcb4cc` |
| `seasons_rules.py` | `7c88084b0bcf0653378cac52d985ba48e2664e3534399038fd934187f97b50f7` |
| `formatcheck.py` | `0fa5a19e7756da7f194a51c44f05d0da9218ed1672907d57c822fa2fe128a11f` |
| `extract.py` | `a3a2f3c28f3aada09e2c749f39968a8c687b044ff67b04b319fd42351880107c` |

## 1. Cel i jedyna definicja "pomogło"

Dokładniejsza prognoza (log score, kalibracja) wyniku meczów hokeja, koszykówki i siatkówki przez stan tabeli każdej
strony w końcówce sezonu zasadniczego. Kryterium jest **model bez poprawki** (jego własny środek / p), nie cena
Superbetu. "Pomogło" = grupa zalicza regułę (c) z sekcji 8. Zero grup zaliczonych = raport zerowy, nic nie wchodzi.

Dziś żaden model tych sportów nie czyta stawki; piłka ma tylko flagi wyświetlane (`bet.sofa.stakes`: reszta wobec
średniej ligi, nie wobec próbek drużyn - dlatego nie korekta). Tu korekta jest mierzona wobec **środka modelu** i z
efektem stałym drużyna-sezon.

## 2. Okresy (decyzja operatora 1, 2026-11-18)

| warstwa | sezony (rok startu = rok pierwszego meczu sezonu zasadniczego, minus 1 gdy miesiąc < 7) |
|---|---|
| rozgrzewka modelu | cała historia przed meczem (jak dziś `load_history`) |
| rozwój (estymacja + walidacja) | **22/23 + 23/24 + 24/25** (rok startu 2022, 2023, 2024; ligi letnie - np. WNBA - wg tej samej reguły) |
| walidacja (<= 3 spojrzenia) | wewnątrz rozwoju: walidacja krzyżowa "zostaw jeden sezon" (3 fałdy) |
| egzamin (raz) | **25/26** (rok startu 2025; WNBA 2026) |

Sezony 22/23 i 23/24 są dziś w cache niepełne (NHL 23/24 od 2024-02-23, NBA od 2024-03-15, większość lig od stycznia
2024; 22/23 praktycznie brak) - **backfill przed egzaminem** (plan w odpowiedzi koordynatorowi; wykonuje operator /
sesja z mostem, nie ta praca). Po backfillu: `STAKES_YEARS=2022,2023 states.py` + `formatcheck.py`, tabela z
sekcji 7 dla tych sezonów dopisana jako **Aneks A** - liczebności tylko, przed jakimkolwiek wynikiem. Liga-sezon
22/23 / 23/24, który po backfillu nie przechodzi reguł sekcji 3, po prostu nie wchodzi (ta sama reguła, nie nowy
wybór). Jeśli backfill nie zostanie wykonany, rozwój = sam 24/25 (liczby sekcji 7) - to też jest zamrożone.

Efekt istnieje tylko w końcówce sezonu (luty-maj), więc egzamin jest na sezonie minionym; sezon 26/27 ma dziś
<= ~25% meczów i okno stanu w nim nie istnieje.

## 3. Populacja

Mecze sezonu zasadniczego (nazwa turnieju = najczęstsza nazwa w lidze-sezonie bez słów fazy pucharowej /
spadkowej), status `finished`, bez towarzyskich. Faza pucharowa, play-in, spadkowa - **poza** (t = 0).

**Liga-sezon = Sofascore `season.id`** w `uniqueTournament`; sezon-satelita tej samej ligi w całości w przedziale
czasu innego sezonu jest doklejany (NBA Cup: osobne `season.id`, 4 mecze grupowe na drużynę liczone do tabeli NBA -
po doklejeniu NBA 82 mecze na drużynę). (Poprawka 2026-11-18: grupowanie po roku startu sklejało dwa sezony WNBA.)

**Liga-sezon wchodzi tylko gdy (automatycznie):**
1. pojedyncza tabela (lub kodowana mapa konferencji - tylko NHL i NBA), >= 10 drużyn;
2. terminarz zrównoważony: liczba meczów drużyn (po usunięciu duplikatów: ta sama para, ten sam dzień UTC) różni
   się o <= 2; `postponed` / `canceled` nie liczone;
3. >= 95% meczów każdej drużyny ma wynik w cache;
4. 2 <= K <= liczba drużyn w grupie - 2;
5. **bramka formatu**: top-K przebudowanej tabeli końcowej w każdej grupie różni się od zbioru drużyn fazy
   pucharowej o <= 1 drużynę (remis / tie-break). >= 2 = zły system punktów / zła mapa / faza pośrednia - wypada.

**Wykluczone z nazwy:** NCAA (hokej 14285, 14317; koszykówka 33651, 648, 33652, 33653, 33654, 33655, 13434,
18640; siatkówka 23428) - turnieje konferencji i at-large, brak jednej tabeli; konferencje / dywizje bez mapy:
KHL 268, AHL 844, ECHL 17188, MHL 1159, VHL 1141, WHL 9475, OHL 1454, QMJHL 14191, B.League B1 1502, Liga
Argentina 21307, LNBP 1472; 23100 Cyber EuroLeague (symulacja).

**Wynik reguł (sezony 2024 + 2025, policzone 2026-11-18):** wypada przez 1-4: hokej 15, koszykówka 148, siatkówka 80
lig-sezonów (m.in. DEL 24/25, Lega A 25/26 - terminarz niezrównoważony w cache); przez bramkę 5: hokej 2 (Alps
Hockey League 24/25, HockeyEttan 25/26), koszykówka 18 (m.in. Nationale 1/2/3, KLS Serbia), siatkówka 6.
**Wchodzi:** hokej 17 (rozwój 24/25) / 26 (egzamin), koszykówka 72 / 80, siatkówka 43 / 44 - m.in. NHL, SHL, Liiga,
DEL 25/26, National League, Extraliga CZ, Tipsport, ICE, Allsvenskan, DEL 2, Ligue Magnus, Elite League; NBA,
WNBA, Euroleague, ACB, BBL, Lega A 24/25, BSL, GBL, VTB, CBA, KBL, NBL, NBB; SuperLega, Serie A1 K, Tauron Liga K,
Ligue A M / K, 1. Bundesliga, Sultanlar, SV League M / K, Superliga BRA. Lista dokładna = `keep.json` z
`formatcheck.py` (powtarzalne z bazy); w F1 zapisana do `config/sofa_stakes_league_formats.json`.

Warstwy (P5): kobiety, NHL / NBA vs pozostałe, liga główna vs niższa / juniorska (lista w F1), konferencje vs
pojedyncza tabela.

## 4. Stany (zamrożone; implementacja = `states.py`, sha256 wyżej)

### 4.1 Linia

Jedna linia na ligę: **K = ostatnie miejsce przedłużające sezon** (play-off lub play-in / pre-play-off) w grupie.
NHL: K = 8 w konferencji (przybliżenie 3 z dywizji + 2 dzikie karty; różni się tylko, gdy dywizja ma < 3 drużyny w
top-8 konferencji - bramka 5 to sprawdza). NBA: K = 10 w konferencji (play-in). Pozostałe: K = liczba drużyn
widzianych w fazie pucharowej ligi-sezonu (fakt formatu); na żywo K z poprzedniego sezonu, zamrożone w pliku.

### 4.2 Punkty tabeli (as-of: tylko mecze sezonu zasadniczego z `startTimestamp` < start meczu badanego)

- hokej NHL (234), Elite League (1442): W 2, porażka po dogrywce / karnych 1 (`status.description` AET / AP);
  pozostałe ligi hokeja: 3-2-1-0;
- koszykówka: wygrane (system FIBA 2-1 daje ten sam porządek; różnica liczby meczów jest w GR);
- siatkówka: 3-0 / 3-1 -> 3:0, 3-2 -> 2:1.

Tie-breaki pomijane (remis punktowy = "może wyprzedzić").

### 4.3 Stan strony s (i osobno rywala)

N = mecze sezonu zasadniczego s w terminarzu, GP = rozegrane przed meczem, GR = N - GP, m = maks. punktów za mecz
(hokej 2 / 3, koszykówka 1, siatkówka 3), grupa = konferencja (NHL / NBA, mapa po id drużyny; 16/16 i 15/15
sprawdzone 2026-11-18) albo cała liga.

| stan | definicja (kolejność sprawdzania) |
|---|---|
| `EARLY` | GP < 0.75 N - poza oknem, t = 0 |
| `SECURED` | liczba innych drużyn grupy z pkt_u + m GR_u >= pkt_s jest < K |
| `DEAD` | liczba innych drużyn grupy z pkt_u > pkt_s + m GR_s jest >= K |
| `MUST_WIN` | ani SECURED, ani DEAD, i odległość od linii / m <= max(1, GR_s / 4); odległość = pkt_s - pkt(K-tej z pozostałych) gdy s w top-K, inaczej pkt(K-tej) - pkt_s |
| `ALIVE` | reszta okna - **odniesienie w oknie** (t = 0) |

Okno 0.75 i próg max(1, GR/4) - zamrożone; 0.66 / 0.85 tylko eksploracyjnie. "Tanking" = DEAD; odpoczynek gwiazd po
zapewnieniu miejsca = SECURED.

## 5. Droga poprawki, grupy, rynki

Wzór: `bet.sofa.schedule_term`. Dla strony s: t_s = beta_own[stan_s] + beta_opp[stan_rywala], beta(ALIVE) =
beta(EARLY) = 0; 6 współczynników na sport.

- **Hokej, koszykówka (score model):** środek regulaminowy strony (po `level_factor` / tempie, w miejscu dzisiejszego
  `SimParams.b2b_delta`) x exp(t_s) przed symulacją; okresy / kwarty / połowy dziedziczą przez udziały okresów.
- **Siatkówka (model wymian, klucze `VB_POINT_MODEL`):** przesunięcie siły wymian strony w logicie o delta_s = t_s.
  Klucze score modelu (suma setów, set na przewagi, sety drużyny, liczba setów): x1 (decyzja 6).
- Gracze: nieobjęci.

Grupy egzaminu (K <= 6): `hk_goals` (gole drużyn, sumy, tercje), `hk_result` (1X2 w regulaminie, zwycięzca,
handicap), `bb_points` (punkty drużyn, sumy, połowy, kwarty), `bb_result` (zwycięzca, handicap), `vb_points` (suma i
handicap punktów), `vb_result` (zwycięzca, dokładny wynik w setach).

## 6. Estymacja (tylko rozwój; nic z egzaminu)

- Wiersze: strony meczów sezonu zasadniczego lig z sekcji 3 (cały sezon - EARLY też, dla efektu stałego
  drużyna-sezon). Środek bazowy = środek modelu z jednego przebiegu odtworzenia as-of (zainstalowane stałe, ścieżka
  `fit_sport_confidence`; kopia bazy `VACUUM INTO`).
- Hokej: Poisson GLM, gole regulaminowe strony, offset log(środek), FE drużyna-sezon (strona atakująca),
  naprzemiennie (FE zamknięte, beta Newtonem). Koszykówka: quasi-Poisson na punktach, to samo. Siatkówka: logit
  wygranych wymian strony w meczu z offsetem logit(p modelu wymian).
- SE klastrowe (drużyna). Ściągnięcie c_shr = c tau² / (tau² + SE²), tau: hokej 0.05, koszykówka 0.02, siatkówka 0.02
  (logit). Współczynniki zamrożone = ściągnięte z rozwoju, **te same instalowane** po zaliczeniu.
- Krzywe obu ramion tylko na rozwoju (offline, nigdy do `config/`).
- S2 placebo: stan z pierwszego meczu okna przypisany meczom tej strony z GP / N w [0.40, 0.60).
- Kierunki (S3) na marginesie (own - opp): DEAD w dół, SECURED w dół, MUST_WIN w górę. Suma - bez kierunku (tylko
  z S1 i S2).

## 7. Tabela mocy (liczebności 2026-11-18, `states.py` okno 0.75, po bramce formatu)

n_wymagane = 7.85 · V · 1.75 / c², V = var / mu² wyniku drużyny w sezonie zasadniczym lig 24/25, **wszystkie stany
razem** (hokej gole: 12,944 stron, mu 2.969, V 0.371; koszykówka punkty: 35,544, mu 82.74, V 0.0397; siatkówka
punkty na set: 11,564, mu 22.03, V 0.0180; policzone na liście lig sprzed poprawki WNBA). Surowe V zawiera rozrzut
między ligami / drużynami - wobec środka modelu mniejsze, więc tabela **ostrożna**; w F1 przeliczana z pliku X
(środki modelu, bez wyników), wzór i progi zamrożone tutaj.

| sport | c | 0.01 | 0.015 | 0.02 | 0.03 | 0.05 | 0.08 | 0.10 |
|---|---|---|---|---|---|---|---|---|
| hokej | n_wym. | 51,014 | 22,673 | 12,754 | 5,668 | 2,041 | 797 | 510 |
| koszykówka | n_wym. | 5,459 | 2,426 | 1,365 | 607 | 218 | 85 | 55 |
| siatkówka | n_wym. | 2,469 | 1,097 | 617 | 274 | 99 | 39 | 25 |

Strony wg stanu (w nawiasie najmniejszy wykrywalny |c| przy 80% mocy, DEFF 1.75):

| sport | sezon | mecze (w oknie) | MUST_WIN | ALIVE (odn.) | SECURED | DEAD | EARLY |
|---|---|---|---|---|---|---|---|
| hokej | 24/25 (rozwój) | 6,238 (1,584) | 710 (0.085) | 1,186 | 934 (0.074) | 247 (0.144) | 9,399 |
| hokej | 25/26 (egzamin) | 8,553 (2,173) | 927 (0.074) | 1,458 | 1,452 (0.059) | 366 (0.118) | 12,903 |
| koszykówka | 24/25 (rozwój) | 14,831 (3,614) | 1,284 (0.021) | 2,053 | 2,464 (0.015) | 1,226 (0.021) | 22,635 |
| koszykówka | 25/26 (egzamin) | 15,060 (3,692) | 1,096 (0.022) | 2,040 | 2,542 (0.015) | 1,444 (0.019) | 22,998 |
| siatkówka | 24/25 (rozwój) | 5,644 (1,379) | 406 (0.025) | 629 | 1,098 (0.015) | 523 (0.022) | 8,632 |
| siatkówka | 25/26 (egzamin) | 5,848 (1,407) | 436 (0.024) | 616 | 1,116 (0.015) | 557 (0.021) | 8,971 |

Strony narażone (MUST_WIN + SECURED + DEAD) egzaminu: hokej 2,745, koszykówka 5,082, siatkówka 2,109. NHL (24/25 /
25/26): MUST_WIN 173 / 274, ALIVE 299 / 227, SECURED 81 / 73, DEAD 87 / 66. NBA: MUST_WIN 62 / **3**, ALIVE 241 /
214, SECURED 213 / 259, DEAD 84 / 124. WNBA (2025 / 2026): MUST_WIN 19 / 0, ALIVE 62 / 49, SECURED 32 / 58, DEAD
30 / 58. NBA / WNBA osobno nietestowalne dla MUST_WIN (warstwa opisowa).

Wrażliwość okna (eksploracyjna, liczona przed bramką formatu i przed poprawką WNBA; strony rozwój / egzamin):
0.66 - hokej MUST_WIN 1,292 / 1,613, DEAD 248 / 381; koszykówka MUST_WIN 2,197 / 2,052; siatkówka 662 / 700.
0.85 - hokej MUST_WIN 267 / 353; koszykówka 675 / 619; siatkówka 170 / 211.

**Werdykt mocy (przed backfillem):** koszykówka wykonalna (~1.5-2.2% punktów drużyny na stan, ~1.2-1.8 pkt);
siatkówka wykonalna (~1.5-2.5% punktów na set); hokej - niedostateczna moc dla efektów < ~6-14% goli na stan,
zgłaszany przy c = 0.05 z S5 na sumie stanów narażonych (2,745 >= 2,041). Backfill 22/23 + 23/24 zwiększa tylko
rozwój (estymację, S1-S4); moc egzaminu (P1) zostaje taka jak wyżej.

## 8. Reguła zaliczenia (c) - adaptacja z `r3_final_review.md` (c) / egzaminu 11-09

**Jednostka** = grupa g z sekcji 5 (K <= 6). Korekta grupy = wszystkie jej zamrożone współczynniki razem.

**Bramki zgłoszenia (rozwój; wszystkie):**
S1 permutacja stanu w obrębie liga-sezon x tydzień (200 powtórzeń): p < 0.05;
S2 placebo (sekcja 6): |beta_placebo| < 0.5 |beta| dla każdego stanu niosącego materialność;
S3 znak marginesu zgodny z sekcją 6 (suma: n/d, wtedy S1 i S2 obowiązkowe);
S4 Delta walidacji ("zostaw jeden sezon") < 0 (punkt);
S5 moc: strony narażone egzaminu (z pliku X, bez wyników) >= n_wymagane dla c_sport przy 80% mocy, DEFF 1.75;
c_sport: hokej 0.05, koszykówka 0.015, siatkówka 0.015 (logit: |delta| dające |Delta p zwycięzcy| >= 0.01).
`*_result` dzieli S5 z grupą punktów / goli swojego sportu.

**Metryka główna.** Delta_g = średnia po **meczach egzaminu w oknie** (>= 1 strona poza EARLY) z [S_treat - S_base]:
`hk_goals` - log score NB goli regulaminowych obu stron (rozrzut zapisany modelu); `bb_points` - log gęstość normalna
punktów regulaminowych obu stron (sd z symulacji danego ramienia); `vb_points` - log gęstość normalna sumy punktów
meczu (średnia i sd z symulacji); `vb_result` - log loss zwycięzcy + log loss kategorialny wyniku w setach;
`hk_result` - log loss 1X2 w regulaminie; `bb_result` - log loss zwycięzcy. Symulacje 4,000, ziarno = id meczu, to
samo w obu ramionach. Ujemne = lepiej.

**PASS(g) iff wszystkie:**
P1 jednostronna górna 95% Delta_g < 0, bootstrap dwukierunkowy klastrów (gospodarz x gość, 2,000 powtórzeń), **Holm**
po K zgłoszonych grupach (alfa 0.05 rodzinnie);
P2 materialność: zamrożony |beta| >= c_sport w >= 1 stanie z >= 2% stron egzaminu grupy w oknie;
P3 poziom linii (krzywe z rozwoju w każdym ramieniu, linie wg ramienia bazowego): Delta_line punkt <= 0 i górna 95%
< +2e-4 nat na wiersz;
P4 kalibracja >= 0.70 (wybór wg p **bazowego** po krzywej): |zrealizowane - średnie p|_treat <= |...|_base + 0.005;
wybór wg p ramienia - raport bez bramki;
P5 nie-gorzej na każdej innej grupie i warstwie z sekcji 3 (górna 95% < +1e-4 nat na wiersz dla grup, < +5e-4 dla
warstw z n >= 2,000; mniejsze opisowo);
P6 współczynnik przefitowany na egzaminie (opisowo, nigdy instalowany) ma znak z rozwoju.

**"Pomogło"** = >= 1 grupa PASS. Instalowane tylko terminy grup zaliczonych; mechanizm wspólny z grupą niezaliczoną
jest tam x1. Zero grup = raport zerowy; commit tylko skryptów pomiarowych i dowodu.

**Strażnicy:** G1-G5 jak 11-09: log `docs/sofa/evidence/stakes_sports_exam_log.md`, skrypt
`measure_stakes_sports_exam.py --spec-sha <sha>` odmawia, gdy linia badania już istnieje; egzamin raz.

## 9. Wcześniejsze spojrzenia (G5)

| kiedy | co | dane | wpływ |
|---|---|---|---|
| 2026-10-01 | back-to-back w score modelu (`SimParams.b2b_delta`), koszykówka +0.06 pkt, se 0.64, odrzucone (`e39f5dda`) | 2026-03..09 | B2B nie jest stanem stawki (sekcja 10) |
| 2026-10-0x | stawka w piłce (`stakes.py`, `measure_peer_choice.py`), reszta vs średnia ligi | piłka, 476 lig-sezonów | kształt stanów; wymóg FE i środka modelu |
| 2026-11-06 | tabela sezonu w score modelu koszykówki (`SEASON_TABLE_W`), odrzucona | 30 dni przed 2026-10-07 | stan = pozycja wobec linii, nie siła z tabeli |
| 2026-11-09 | egzamin terminarza piłka / tenis | piłka, tenis | brak |
| 2026-11-18 (ta praca) | liczebności wg stanu; bramka formatu; średnia / wariancja wyniku łącznie dla stanów | sezony 24/25, 25/26 | okno, próg MUST_WIN, c_sport, werdykt mocy - wybrane po liczebnościach, **bez** wyniku wg stanu |

## 10. Back-to-back / odpoczynek (decyzja operatora 7)

**Osobne badanie później, nie w tym egzaminie.** `SimParams.b2b_delta` (okno 36 h) istnieje i jest 0.0; zmierzone
tylko dla koszykówki na punktach, nigdy na kalibracji >= 0.70; hokej nieraportowany; model wymian bez odpoczynku.

## 11. Wdrożenie (tylko po zaliczeniu)

- Przełącznik `STAKES_TERM_SPORTS_FROM_UTC` w `bet.sofa.epochs` od następnego dnia 00:00Z po commicie instalacji
  (wcześniej tylko operator); tylko grupy zaliczone.
- `config/sofa_stakes_league_formats.json` (ligi, K, system punktów, mapa konferencji NHL / NBA po id, N
  terminarza), zamrożony w F1; liga spoza pliku: t = 0.
- Krzywe sportu przefitowane na kopii bazy (`VACUUM INTO`, `--db-path`, `--without-db-backup`) z flagą odtwarzającą
  termin (`fit_sport_confidence --stakes-term`; krzywe modelu wymian tak samo); instalacja po `tests/sofa` i za
  zgodą operatora; nowa epoka w `audit_ledger.EPOCH_GROUPS`.
- Wiersze: `stakes_state` (own / opp), `stakes_term`, odwrócony cień `p_central_no_stakes_term`; marker
  `stakes_term_rule` (rebuild_plan); `T-STAKES-TERM-SPORTS-FORWARD` zarejestrowany przed dniem przełącznika.
- **Na żywo przełącznik bezczynny do okna końcówki** (~luty 2027); reguła wycofania jak 11-09.

## 12. Decyzje (operator 2026-11-18)

1. **Backfill 22/23 i 23/24: TAK**, przed egzaminem (sekcja 2, Aneks A).
2. Linia druga (spadek / play-out, rozstawienie): **nie w v1** - każda linia to nowe stany i mniejsza moc na stan.
3. Mapy konferencji KHL / AHL / ECHL / CHL / MHL / VHL: **wykluczone** - zmieniają się co sezon, bez sieci
   nieweryfikowalne, a bramka formatu nie wyłapie złej mapy w pełni.
4. Systemy punktów: **jak w 4.2, bez ręcznej weryfikacji** - bramka formatu (top-K vs faza pucharowa) odrzuca każdy
   błąd, który zmienia skład linii.
5. Ligi z brakami wyników (np. Lega A 25/26): **odświeżane tylko przez backfill / refresh przed zamrożeniem listy w
   F1**; po zamrożeniu lista się nie zmienia - brak = liga wypada.
6. Siatkówka, klucze score modelu: **x1 w v1** - jedna droga (model wymian) na sport, bez drugiego mechanizmu w
   Holmie.
7. Back-to-back: **osobne badanie później** (sekcja 10).

## 13. Aneks A (po backfillu, przed jakimkolwiek wynikiem)

Puste do wykonania backfillu. Treść: wynik `formatcheck.py` i `STAKES_YEARS=2022,2023 states.py` (te same pliki,
sha256 jak wyżej): liczba lig-sezonów wchodzących, tabela stron wg stanu dla 22/23 i 23/24, data i commit bazy
(`VACUUM INTO`), nic więcej.
