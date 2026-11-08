# Pre-rejestracja: kontekst terminarza / zmęczenia w prognozie - piłka i tenis (F0, 2026-11-09)

Dokument zamrożony **przed** jakąkolwiek analizą wyników (krok (d) 2, strażnik G1). Plan nadrzędny:
`docs/sofa/history/PLAN_KONTEKST_TERMINARZA_PILKA_TENIS_2026-11-08.md`; reguły wiążące: `r3_final_review.md`
(teksty zastępcze D1-D25, reguła (c), lista (d)) w `docs/sofa/evidence/kontekst_terminarza_2026-11-08/`.
Tam, gdzie ten dokument coś rozstrzyga, a `r3` zostawiał wybór - rozstrzygnięcie jest tutaj i jest zamrożone.
Zmiana czegokolwiek poniżej po pierwszym spojrzeniu na walidację = nowe spojrzenie (G3); po egzaminie - zakazana (G4).

Stan wiedzy w chwili zamrożenia: żadna reszta (y - środek) nie była liczona w tej pracy; kopia bazy
`data/refit_2026-11-08_schedule/sofa_copy.db` (VACUUM INTO z `file:data/sofa.db?mode=ro`, 2026-11-09 ~00:00Z).

## 1. Cel i jedyna definicja "pomogło"

Dokładniejsza prognoza (log score, kalibracja) rynków piłki i tenisa przez kontekst terminarza. Cena Superbetu nie
jest kryterium. "Pomogło" = grupa zalicza regułę (c) (sekcja 8 - przepisana dosłownie z `r3`). Przesadna pewność
przy kursach >= 1.40 jest poza zakresem i nie jest mieszana z wariantami (D21).

## 2. Okresy (D1, dosłownie)

| warstwa | piłka gole / wynik; tenis zwycięzca / gemy / sety | piłka liczniki (rożne, strzały, kartki, faule, spalone, połowy liczników) | tenis serwis (model punktowy) |
|---|---|---|---|
| rozgrzewka (rating, próbki, kalendarz) | cała historia | cała historia | cała historia |
| eksploracja (wiersze liczone) | 2024-07-01 .. 2025-08-31 | 2025-01-01 .. 2025-08-31 | 2025-05-01 .. 2025-08-31 |
| walidacja (<= 3 spojrzenia) | 2025-09-01 .. 2025-12-31 | jw. | jw. |
| egzamin (raz) | 2026-01-01 .. 2026-10-31 | jw. | jw. (cache tenisa kończy się 2026-10-19 - raport to podaje) |

Granica = start meczu (UTC). Przed analizą: raport liczebności wierszy (bez wyników) grupa x kwartał x kubeł
ekspozycji z pliku X; grupa, której eksploracja ma < 50% wierszy narażonych wymaganych tabelą mocy (sekcja 7),
idzie na egzamin tylko łącznie z pokrewną grupą zapisaną tu z góry albo wcale:
pooling z góry: `offsets` -> `shots_sot` (oba to akcje ofensywne); `cards_fouls` bez partnera; `tennis_serve` bez partnera.

## 3. Populacja

- Piłka: mecze z historii `calibrate_from_cache` (bez towarzyskich - reguła `bet.sofa.comparability`, bez
  przyznanych przy stole - `--awarded-excluded`). **Reprezentacje wyłączone** z dopasowania i egzaminu (D11;
  `homeTeam.national` lub `awayTeam.national`), raportowane opisowo. Kobiety = osobna warstwa
  (`FootballResult.women` / `WOMEN_COMPETITION_IDS`), instalowana tylko gdy jej warstwa zalicza, inaczej x1.
- Tenis: single z historii `tennis_rating.load_history`; walkower wykluczony (jak dziś), krecz (`completed=False`)
  oceniany tak, jak ocenia go SETTLE (zwrot = wiersz poza punktacją), a odsetek kreczów wg kubła ekspozycji
  raportowany jako osobny wynik (C31). Kobiety / mężczyźni / turnieje drużynowe = warstwy (D11).
- Klasyfikacja wiersza do grupy **wyłącznie po kluczu rynku wg dyspozycji w kodzie** (C3 / D19), tabela
  `family_table.md` (generowana przez `family_table.py` z symboli kodu; sekcja 10).

## 4. Cechy (zamrożone; moduł `bet.sofa.schedule_features`, jedna funkcja dla odtworzenia i SHEET - D7)

Kalendarz: suma `sofa_listed_event` (wszystkie wiersze danego sportu; strony z `homeTeam.id` / `awayTeam.id`),
wyłącznie mecze o statusie `finished` (przełożone / odwołane / przerwane nie są obciążeniem - M7), ściśle
`startTimestamp < kickoff` badanego meczu (as-of; dzień ani mecze tego samego dnia późniejsze nie wchodzą).
**Towarzyskie wyłączone** z obciążenia - ta sama reguła co `schedule.side_schedule` (`comparability.is_friendly_event`),
żeby wyświetlanie i model liczyły to samo (C23). Flaga `coverage`: strona bez żadnego meczu w kalendarzu w
120 dniach przed meczem = `coverage=False` -> wiersz wypada z dopasowania, na żywo x1 (M6).

### 4.1 Piłka - na stronę s (i to samo dla rywala, osobne współczynniki "own" / "opp")

| cecha | definicja | forma |
|---|---|---|
| `rest_d` | (kickoff - start ostatniego meczu) / 86400 (godziny / 24, D22) | kubły: R1 < 3.5; R2 3.5-5.5; **R3 5.5-8.5 (odniesienie)**; R4 8.5-20.5; R5 >= 20.5 |
| `intl_return` | R4 i w luce leży dzień z >= 30 zakończonymi meczami reprezentacji A (`national`) w kalendarzu sumy | wskaźnik; R4 dzielony na R4_intl / R4_other |
| `layoff_kind` (R5) | `season_start`: pierwszy mecz strony w bieżącym (rozgrywki, sezon); `winter`: luka obejmuje 25.12; `other`: reszta (przerwa reprezentacyjna >= 21 d nie występuje osobno - wpada do `other`) | R5 dzielony na 3 wskaźniki (M7) |
| `cont_prev4` | mecz w rozgrywkach kontynentalnych (`config/sofa_cup_strength.json` `competitions`) w 96 h przed meczem | wskaźnik + interakcja `cont_prev4 x R1` (M18) |
| `et_prev` | poprzedni mecz (w 7 d) z dogrywką / karnymi (`metrics.played_extra_time`) | wskaźnik |
| `dense14` | >= 4 zakończone mecze w 14 d przed meczem | wskaźnik |
| `cont_next4` | następny zakończony mecz strony w rozgrywkach kontynentalnych startuje <= 96 h po meczu (as-of: start znany w chwili meczu; mecze przełożone po starcie badanego meczu - nieodróżnialne w historii, akceptowane) | wskaźnik (rotacja, C19 / M5) |

Kontrole (już w środku modelu, nie dopasowywane): faza sezonu, rozgrywki, siła faworyta (warstwy |s|).
Eksploracyjne, **nigdy nie idą na egzamin**: strefa czasowa z kraju drużyny (kraje jednostrefowe), interakcje inne niż wyżej.
**Nie wchodzą** (pokrycie / przeciek): minuty podstawowych i czerwona kartka w poprzednim meczu - wymagają składów /
statystyk poprzedniego meczu; pomiar 10-23 "realny skład bez zysku na licznikach drużyn" (C18); w v1 niezaliczone
do cech, nazwane w raporcie. Bieżący skład nigdy (przeciek).

### 4.2 Tenis - na gracza (z historii singla `tennis_rating.load_history` + surowy JSON zdarzenia)

| cecha | definicja |
|---|---|
| `games78` | gemy rozegrane w meczach zakończonych w 78 h przed meczem (pełne pokrycie: `homeScore.periodN`) / 10 |
| `games7d_prev` | gemy w 7 d w poprzednich turniejach (inny `tournament.id`) / 10 |
| `rounds_cur` | liczba meczów wygranych w bieżącym turnieju (ten sam `tournament.id`) |
| `layoff21` | ostatni mecz > 21 d temu (zastępuje `drest`) |
| `ret14` | przegrany krecz / walkower w 14 d, bez ukończonego meczu potem |
| `surface_switch` | rodzina nawierzchni poprzedniego meczu inna niż bieżąca |
| `dom_prev` | udział gemów wygranych w poprzednim meczu (kontrola, M16) |
| `qual` | mecz w kwalifikacjach (nazwa turnieju / rundy zawiera "Qualif") |

Punkty rozegrane - tylko z flagą pokrycia, w eksploracji jako wrażliwość; minuty tylko wrażliwość (nigdy w wariancie).
Pięciosetówka nie jest cechą (M17) - poprzedni best-of-five wchodzi tylko przez `games78`. Debel tego samego dnia:
**nieobliczalny na żywo w v1** (dziennik ratingu tylko singiel, C21) - nazwany, poza wariantem.
Wariant tenisa: w ratingu nowe cechy jako różnice graczy **zastępują** `dmin78`, `dn7`, `drest` (nie obok, M16/D14);
`dform`, `dhigh`, `dtour`, `lp(s)` bez zmian.

**Nie do policzenia (D24 / C22):** odległość podróży, wysokość (miejsce tylko na ~4.5% wierszy piłki), pogoda (dostawca
spoza Sofascore), trener (backfill sieciowy), konflikty / morale.

## 5. Grupy i droga poprawki (D3, dosłownie, rozstrzygnięcia)

Grupy egzaminu G = {`goals` (pełny, 1H, 2H; strony i sumy), `corners`, `shots_sot`, `cards_fouls`, `offsides`,
`football_result` (1X2 / DC / DNB / wynik dokładny przez rating + klucze symulatora), `tennis_winner`,
`tennis_games_sets` (rating + sąsiedzi), `tennis_serve` (model punktowy)}; K <= 9.

Piłka:
- (i) wiersze brzegowe liczników / goli (team `_for` / `_total`, połowy, wiersze łączone na środkach brzegowych
  `DERIVED_MARGINAL_CENTRES_METRICS`, propsy przez udział): mnożnik exp(t) na **końcowym** środku
  `live_centre` / `centre_chain.apply_centre_chain`, po fazie sezonu, z połową ratingową i `supremacy` dla stretchy
  czytanymi bez poprawki. t = suma(beta_own · x_own) + suma(beta_opp · x_opp), współczynniki **per (metryka bazowa,
  połowa)**; `_total` = suma środków stron, każda ze swoim t. Współczynnik dopasowany względem zapisanego końcowego środka.
- (ii) czysty rating (1X2, DC, DNB, wynik dokładny, plastry, symulator): poprawione środki goli w
  `FootballForecast.centre` (obie książki, także tabela sezonu 35 rodzin), t z grupy `goals` dopasowane względem
  zapisanych środków ratingu; nigdy (i) i (ii) na tym samym wierszu. Ocena grupy `football_result`: log loss 1X2
  (3 wyniki) z `football_1x2_dnb.probabilities(lh, la, r)` na zapisanych środkach ratingu (bazowy) vs poprawionych.
- (iii) aktualizacja ratingu bez terminu (wariant (a)). Wariant (b) (termin w oczekiwaniu aktualizacji)
  przyjęty tylko gdy na rozwoju lepszy o > 1 SE (M3); jego ocena wymaga drugiego przebiegu - **w v1 nie mierzony**,
  przyjęty (a); raportowany kubeł "pierwszy mecz po zagęszczeniu".
- Joints z surowej próbki (`both_over_*` w połowach, `most_corners_1h/2h`, `handicap_shots*`, `both_over_saves*`):
  **nieobjęte** (C9) - wymienione z nazwy w tabeli rodzin.
- Liczniki drużyn bez grupy w regule (c) - obrony, wrzuty z autu, wybicia od bramki, odbiory (i ich połowy, 20 kluczy
  drogi (i) w `family_table.md`): **nieobjęte** w v1 (x1), choć droga (i) by je osiągnęła.
- Klucze modelu punktowego tenisa (także `games_set1/2_total`, `handicap_games_won_set1/2`) należą do grupy
  `tennis_serve` (dyspozycja w kodzie, `family_table.md`); `set1/2_won_for` do `tennis_games_sets`.
- Czerwone / karne (średnia ligowa): nieobjęte - moc (M14: czerwone nierozstrzygalne przy tych n), C10.
- Propsy: przez udział (strzały / celne / faule) dziedziczą termin drużyny automatycznie; propsy spoza udziału
  nieobjęte; propsy oceniane tylko na podstawowych (C11, M18).
- `season_early` (rundy 1-3): bez terminu `layoff` (R5 season_start = x1) chyba że przefitowanie krzywej klasy na
  rozwoju pokaże brak podwójnego liczenia (D11) - w v1 x1.
- Rozrzut (C7): test zarejestrowany - Pearson chi2/df reszty NB wg kubła ekspozycji na eksploracji; dźwignia
  (mnożnik alpha na kubeł) dozwolona tylko gdy chi2/df w kubełku > 1.10 przy n >= 2000; inaczej brak dźwigni.
- Połowy (C8): termin dopasowany per (metryka, połowa) z H0 1H = 2H; kartki w połowach i profil 2H symulatora -
  nieobjęte w v1 (osiągalne tylko przez sumę 90').

Tenis:
- `tennis_winner`: rating przefitowany na rozwoju (cięcie 2026-01-01) w **obu** wariantach (`fit_tennis_rating.py
  --cut 2026-01-01 --tier-start --score-winner`), wariant = cechy z 4.2 zamiast `dmin78/dn7/drest`; prognozy
  dzienne (stan na 00:00Z dnia, D5). Wiersz dodatkowy: bazowy przefitowany vs zainstalowany na rozwoju.
- `tennis_games_sets`: osiągane **tylko przez zmianę p zwycięzcy** (sąsiedzi wybierani po p, `_window`); klucza
  wspólnego obciążenia nie dodajemy (C12 - rozstrzygnięcie). `games_total` część próbkowa (`W_GAMES_TOTAL_RATING`)
  bez terminu (C14) - `games_total` objęty częściowo, i tak jest kluczem progu 0.60 (D13).
- `tennis_serve`: przesunięcie p wygrania punktu serwisowego gracza w `PointModel` o delta = suma(beta·x) (forma
  shift(prior load), C13); alternatywa "shift + slope x rozegrane punkty" tylko eksploracyjnie, nie na egzamin;
  model punktowy przechodzony dzień po dniu w obu wariantach, hiperparametry jak zainstalowane (M10).

Progi 0.60 (`games_total`, `sets_total`, 4 klucze symulatora): poza przełącznikiem, dopóki próg nie zostanie
zmierzony ponownie tą samą procedurą na poprawionym p (D13).

## 6. Estymacja (eksploracja + walidacja; nic z egzaminu)

- Piłka, grupa g, metryka m: Poisson GLM z offsetem log(środek końcowy) i **efektami stałymi drużyna-sezon**
  (strony atakującej; dla `_total` strona gospodarzy), estymacja naprzemienna (FE w postaci zamkniętej, beta Newtonem).
  Kontrast w meczu (różnica own vs opp) i warstwy - raportowane obok, nie decydują.
- Ściągnięcie: c_shr = c · tau² / (tau² + SE²), tau = 0.05 (rząd efektów z literatury); SE klastrowe (drużyna).
- Współczynniki zamrożone = ściągnięte z eksploracji+walidacji łącznie (krok (d) 10), **te same instaluje się
  po zaliczeniu** (plan pkt 3.3; nie dopasowuje się ponownie na pełnej historii) - rozstrzyga krok (d) 16.
- Tenis: współczynniki ratingu = `fit_tennis_rating` z cięciem 2026-01-01 (rozwój); serwis: delta per cecha z
  logitu punktów serwisowych z offsetem logit(p modelu) na eksploracji.
- Bramki zgłoszenia S1-S5 (sekcja 8), liczone na rozwoju. Negatywne kontrole (M5): permutacja cechy w obrębie
  drużyna-sezon / gracz-sezon (200 powtórzeń); opóźniona ekspozycja `rest_{t-1}` (odpoczynek przed poprzednim meczem);
  wynik bez mechanizmu: spalone rywala (piłka), podwójne błędy rywala... tenis: brak - S2 część "wynik bez mechanizmu"
  dla tenisa = n/d, raportowane.
- Kierunki zarejestrowane (S3): own R1/R2, `cont_prev4`, `et_prev`, `dense14` -> akcje ofensywne own (gole, rożne,
  strzały) w dół, opp te same metryki w górę lub 0; own R5 (wszystkie rodzaje) -> gole / rożne own w dół; `intl_return`
  -> bez kierunku (dwustronny, wymaga |c| >= 0.03 i obu bramek); kartki / faule / spalone - bez kierunku (literatura:
  brak dowodu) -> mechanizm bez kierunku idzie na egzamin tylko gdy S1 i S2 zdane, S3 = n/d. Tenis: `games78`,
  `games7d_prev`, `layoff21`, `ret14` -> p zwycięzcy w dół i p punktu serwisowego w dół; `rounds_cur` -> bez kierunku
  (selekcja, M16).
- Odtworzenie przyjęte: jeden przebieg rejestrujący `calibrate_from_cache` (D4) z flagami z
  `data/refit_2026-11-05_replay/ftA/replay_rules.json` + `--form-table-per-family` zamiast `--form-table`, `--no-write`,
  `--from 2024-07-01`; próba 5 dni (2025-10-01..05) z kontrolą p do 1e-9 przed pełnym przebiegiem.
- Krzywe tylko na rozwoju (D6): offline z zapisanych wierszy tą samą logiką kubłów (`bucket_of`, `wilson_lo`, K13,
  klasy, krzywe liniowe 33 kluczy, plastry) - skrypt pomiarowy, nigdy do `config/`.
- Stałe współliniowe (D10): faza sezonu przefitowana na rozwoju (`fit_season_phase.py` ograniczony do rozwoju,
  zastosowany offline na zapisanym środku przed fazą) w obu wariantach; tabela formy - jak zainstalowana (wybrana na
  10-18..11-04, poza egzaminem); stan gry, stretche, wagi ratingu, sędzia, rozrzut, siła pucharów - dopasowane na
  historii z okresem egzaminu, identyczne w obu wariantach = zaakceptowane symetryczne zanieczyszczenie; współczynnik
  gole x faza raportowany z rozbiciem stretchu goli na fazy włączonym i wyłączonym.

## 7. Tabela mocy (M14; S5)

n_wymagane (wiersze narażone w kubełku) = 7.85 · (1/mu + alpha) · 1.75 / c², c = 0.03, gdzie mu = średni **bazowy
środek** grupy na egzaminie, liczony z pliku X (bez wyników), alpha = zapisany rozrzut NB. Tenis zwycięzca:
n = 4.9k · 1.75 meczów w kubełku dla 1 pp. Tabela liczb wypełniana z X przed walidacją i dopisywana do pliku stanu;
wzór i progi są zamrożone tutaj. Orientacyjnie (r2 M14): rożne ~3.8k, gole ~11k.

## 8. Reguła zaliczenia (c) - dosłownie z `r3_final_review.md` (c)

**Units.** Exam unit = metric group g in G = {goals (full, 1H, 2H; sides and totals), corners, shots+SOT,
cards+fouls, offsides, football result (1X2/DC/DNB/score via rating, sim keys), tennis winner, tennis games/sets
(rating + neighbours), tennis serve (point model)}. Each group's correction = all its frozen mechanism coefficients
together (shrunk, fitted on explore + validate). Mechanism-level tests are dev-only gates. K = number of groups
submitted to the exam (<= 9).

**Submission gates (dev, before the exam; all must hold for g to be submitted):**
S1 permutation null (fatigue feature permuted within team-season / player-season, 200 reps): p < 0.05;
S2 lagged negative control: |beta(rest_{t-1})| < 0.5 |beta(rest_t)|; mechanism-free outcome coefficient CI covers 0;
S3 sign matches the pre-registered direction (own short rest lowers own attack counts, etc.);
S4 validate-tier Delta (definition below) < 0 point estimate;
S5 power: exam exposed rows (counted from the outcome-free X file) >= n required for |c| = 0.03 at 80% power with
DEFF 1.75 (plan 3.7 table), else g is submitted only pooled with a sibling or not at all.

**Primary metric.** Delta_g = mean over exam **matches** of [S_treat - S_base], S = the match's summed per-row
proper score over g's rows: NB log score of the observed count with each arm's centre and the recorded dispersion
(counts, goals); Bernoulli log loss (tennis winner, result markets at their own outcomes); the point model's line log
loss at baseline-fixed lines (tennis serve). Negative = better.

**PASS(g) iff all of:**
P1 one-sided upper 95% bound of Delta_g < 0, from a two-way cluster bootstrap (football: home team x away team;
tennis: player x tournament-week; 2,000 reps), **Holm-adjusted across the K submitted groups** (alpha 0.05 family-wise);
P2 materiality: frozen |c| >= 0.03 (3% of the centre) in at least one pre-registered exposure bucket holding >= 2% of
g's exam rows (tennis winner: mean |Delta p| >= 0.01 in that bucket); a significant but immaterial g = NOT_PASSED;
P3 calibrated line level (dev-refit curves in each arm, baseline-fixed lines): Delta_line point estimate <= 0 and its
upper 95% bound < +2e-4 nats per row;
P4 calibration at >= 0.70, rows selected by the **baseline** calibrated p: |realised - mean p|_treat <=
|realised - mean p|_base + 0.005; the same on rows selected by treatment p reported (no gate);
P5 non-inferiority on every other group and on every pre-registered stratum (women, favourite |s| terciles,
continental vs domestic, round <= 3, tennis tiers): upper 95% bound of Delta < +1e-4 nats per row (groups) and
< +5e-4 (strata, each n >= 2,000 rows; smaller strata descriptive);
P6 exam-refit coefficient (descriptive, never installed) has the dev sign.

**"Helped"** = at least one group PASSes. Only PASSing groups' terms are installed; a mechanism shared with a failing
group is x1 there. Zero passing groups = the deliverable is the null report; nothing is committed except the
measurement scripts / evidence (no switch, no config).

**Guards:** G1-G5 dosłownie z `r3` (c). Log egzaminu: `docs/sofa/evidence/schedule_context_exam_log.md`; skrypt
`measure_schedule_exam.py --spec-sha <sha>` odmawia, gdy linia tego badania już istnieje.

Rozstrzygnięcia wykonawcze reguły (zamrożone): bootstrap dwukierunkowy = niezależne losowanie z powtórzeniami
klastrów gospodarzy i gości (pigeonhole), waga meczu = iloczyn krotności; p-wartość jednostronna = udział replik
Delta >= 0 (min 1/2000), Holm na tych p. "Kubeł ekspozycji" dla P2 = kubły z 4.1 / wartości wskaźników 4.2 (tenis:
`games78` >= 3.0 tj. >= 30 gemów, `layoff21`, `ret14`).

## 9. Wcześniejsze spojrzenia (G5, M8)

| kiedy | co | okres danych | wpływ na wybory tutaj |
|---|---|---|---|
| 2026-10-04 | `measure_schedule_context.py` vs surowa średnia próbki (`RAPORT_2026-10-04_POROWNYWALNOSC_HISTORII.md` K3) | 293k meczów ligowych do 10-04 (w tym 2025-08..2026-10) | kubeł >= 21 d (`LONG_LAYOFF_DAYS`), próg 3 meczów / 7 d, kubły odpoczynku |
| 2026-10-05 | `model_defects_2026-10-05.md` (faza sezonu, przerwa) | historia do 10-05 | faza sezonu jako kontrola; rozdział R5 na season_start |
| 2026-10-08 | fit ratingu tenisa (`dmin78`, `drest`, `dn7`), cięcie 10-01 | in-sample przez okres egzaminu | 21 d przerwy tenisa, okno 78 h, 7 d |
| 2026-11-05 | bateria cech vs cena (`bateria_statystyk_2026-11-05.md`) | rozliczone linie 09-28..11-04 | brak (podróż / back-to-back 0 - nie dodane jako cechy) |

## 10. Tabela rodzin z kodu (C1 / C2)

`docs/sofa/evidence/kontekst_terminarza_2026-11-08/family_table.md`, generowana przez `family_table.py` (ten sam commit).
Każdy klucz: grupa, droga (i) / (ii) / rating / point_model / brak, uwaga zasięgu, symbol kodu.

## 11. Wdrożenie (tylko po zaliczeniu)

Odwrócony cień (r3 sekcja 6): przełącznik od następnego dnia 00:00Z po commicie instalacji, każdy objęty wiersz niesie
`p_central` bez poprawki; `T-SCHEDULE-TERM-FORWARD` zarejestrowany przed dniem przełącznika; reguła wycofania: po
6 tygodniach lub po liczbie wierszy narażonych z tabeli mocy (co później) - jeśli Delta na nowych danych ma znak
przeciwny i górna granica 95% < 0 dla "bez poprawki lepsze", przełącznik wyłączony od następnego dnia 00:00Z.
Rejestr testów: egzamin historyczny to zamrożony dokument (SHA), nie wpis rejestru (D8).

## 12. Status uwag C1-C32, M1-M18, D1-D25

Status: **W** = wdrożone w tym dokumencie (sekcja) lub w kroku (d); **O** = odrzucone z powodem.

| id | status | gdzie / powód |
|---|---|---|
| C1 | W | 10 (tabela "klucz -> środek"); klucze bez bazy = środek próbki (`calibrate_from_cache.py:1311-1313`) |
| C2 | W | 10, generowane z kodu |
| C3 | W | 3, 10 |
| C4 | W | 5 (D3) |
| C5 | W | kubły R5 raportowane dla rundy <= 3 vs > 3; `season_early` 5 |
| C6 | W | warstwy |s| (P5) |
| C7 | W | 5 (test chi2/df, dźwignia) |
| C8 | W | 5 (per metryka, połowa) |
| C9 | W | 5 (joints surowe nieobjęte, z nazwy w 10) |
| C10 | W | 5 (moc M14) |
| C11 | W | 5 |
| C12 | W | 5 (tylko przez p zwycięzcy) |
| C13 | W | 5 (shift; slope eksploracyjnie) |
| C14 | W | 5 (część próbkowa bez terminu) |
| C15 | W | 5 (obie książki) |
| C16 | W | 4.1 own / opp |
| C17 | W | `et_prev` |
| C18 | W | 4.1 (minuty/skład nie w v1; tylko poprzednie mecze) |
| C19 | W | `cont_next4` as-of |
| C20 | W | kontrola (godzina / dzień tygodnia) - raport opisowy |
| C21 | W | 4.2 (debel nieobliczalny na żywo; godzina zakończenia poprzedniego meczu - nieobliczalna bez czasu trwania, nazwana) |
| C22 | W | 4.2 lista "nie do policzenia" |
| C23 | W | F1 testy: zgodność z SAMPLES, flagi bajt w bajt, rozkład ekspozycji live vs replay |
| C24 | W | krok (d) 22-27 |
| C25 | W | krok (d) 28 |
| C26 | W | D13 |
| C27 | W | D12, krok (d) 13 |
| C28 | W | krok (d) 19 |
| C29 | W | krok (d) 19 |
| C30 | W | krok (d) 16-20 |
| C31 | W | 3 |
| C32 | W | 6 (GLM z offsetem) |
| M1 | W | 6 (D4) |
| M2 | W | F1 test mieszania w dniu; D5 |
| M3 | W | 5 (a); (b) niemierzony w v1 - O dla (b): wymaga drugiego 6 h przebiegu, (a) domyślne zgodnie z regułą |
| M4 | W | 6 (FE drużyna-sezon, kontrast w meczu, kierunki S3, warstwy kontynentalne) |
| M5 | W | 6 (permutacja, opóźniona ekspozycja, wynik bez mechanizmu) |
| M6 | W | 4 (`coverage`), krok (d) 8 |
| M7 | W | 4.1 rodzaje przerwy |
| M8 | W | 9 |
| M9 | W | 2, 3 (reprezentacje wyłączone); cień odwrócony 11 |
| M10 | W | 5 |
| M11 | W | 6 (krzywe na rozwoju), P4 na p bazowym |
| M12 | W | reguła (c): jednostka = grupa, Holm |
| M13 | W | 8 |
| M14 | W | 7 |
| M15 | W | 8 G1-G5 |
| M16 | W | 4.2 (zastępują; dominacja; spójność model punktowy vs rating raportowana) |
| M17 | W | 4.2 (pięciosetówka nie cechą) |
| M18 | W | 4.1 (godziny/24, interakcja, strefa eksploracyjnie, null to wynik) |
| D1 | W | 2 |
| D2 | W | 8 |
| D3 | W | 5 |
| D4 | W | 6, krok (d) 5 |
| D5 | W | 5, F1 |
| D6 | W | 6 |
| D7 | W | 4 |
| D8 | W | 11 |
| D9 | W | krok (d) 15 / 26 |
| D10 | W | 6 |
| D11 | W | 3, 5 |
| D12 | W | krok (d) 13 |
| D13 | W | 5 |
| D14 | W | 4.2 |
| D15 | W | sposób pracy (commit własnych ścieżek) |
| D16 | W | 11 |
| D17 | W | 11 |
| D18 | W | krok (d) 5-6 |
| D19 | W | 3 |
| D20 | W | 3 |
| D21 | W | 1 |
| D22 | W | 4.1 |
| D23 | W | ten commit |
| D24 | W | 4.2 |
| D25 | W | `T-SCHEDULE-TERM-FORWARD` - objętość z tablicy na żywo przy rejestracji |
