# Asy i podwójne błędy: ekspozycja, turniej, returnujący - plan pomiaru (pre-rejestracja, 2026-10-19)

Spisany PRZED uruchomieniem czegokolwiek. Ramiona, metryki, populacja i reguła
decyzji są tu zamrożone; wynik, który ich nie spełni, nie zmienia kuponu.

## Pytanie

Czy środek asów / podwójnych błędów (PB) liczony jak w literaturze - tempo na
gem x oczekiwana liczba gemów dzisiejszego meczu (ekspozycja), z efektem
turnieju (kort, piłki, wysokość) i z returnującym - jest lepszy od tego, co
wycenia SHEET dziś (średnia liczba na mecz z próbki, ściągnięta do priora
tier x płeć x nawierzchnia), **na liniach, na których Superbet faktycznie
wystawia te rynki**.

## Dziury pierwszej wersji planu (poprawione niżej)

1. **Populacja.** Superbet wystawia rynki serwisowe tylko w głównym tourze
   (ATP / WTA, `tennis_rating.tier_group == "TOUR"`; 12-29 meczów dziennie,
   `tennis_aces_opponent_2026-10-17.md`). Pomiar 10-17 liczył historię wszystkich
   tierów (60 tys. meczów, głównie ITF). Populacja główna: TOUR; reszta raportowana
   osobno.
2. **Replay ≠ SHEET.** `calibrate_from_cache.shrunk_centre` ściąga tenis do
   bazy ligi; SHEET (`run_sheet.sample_centre`) do priora tieru
   (`bet.sofa.tennis_prior`). Lekcja 10-17: korekta, która wygrała z
   uproszczoną bazą, z prawdziwym SHEET dała zero. Wszystkie ramiona liczą
   środek z priorem tieru jak SHEET; krok 3 (prawdziwy SHEET na liniach
   Superbetu) i tak jest wiążący.
3. **Siatka linii zależy od ramienia** (`lines_for(centre)`), a "linie rynkowe"
   z 10-17 wybierało stare ramię (p OVER w [0.35, 0.65] starego). Teraz: jedna
   linia na (mecz, rynek, zawodnik) - ta ze wspólnej siatki, na której średnie
   p OVER wszystkich ramion jest najbliżej 0.5. Symetrycznie dla ramion.
4. **Główny mechanizm strat to krzywa, nie środek.** Krzywa dopasowana na
   całej drabince, czytana na linii rynku, zawyża (10-17: 0.761 deklarowane,
   0.668 zrealizowane). Lepszy środek z tą samą krzywą dalej drukowałby nogi
   powyżej prawdy. Każde ramię dostaje dwie krzywe: z całej drabinki (jak dziś)
   i **tylko z linii rynkowych** (jak A7 w koszykówce).
5. **Brakowało PB i setów.** Ekspozycja dotyczy asów i PB, meczu i setów 1 / 2.
6. **`serviceGamesTotal` gubi gem tie-breaka** (pułapka payloadu). Długość meczu
   = suma `gamesWon` (tie-break liczony jako gem), tak samo jak gemy sąsiadów
   ratingu.
7. **Rozrzut.** Dzisiejsza długość meczu jest niepewna, więc rozrzut zostaje z
   surowej próbki; zmienia się tylko środek.
8. **Najpierw sufit.** Ramię wyroczni (prawdziwa liczba gemów meczu) mówi, ile
   ekspozycja może dać w ogóle; jeśli wyrocznia nic nie daje, reszta odpada.
9. **Żadnego strojenia na teście.** K efektu turnieju ustalone z góry (30
   wierszy), test od 2026-01-01.
10. **Moc na liniach Superbetu** (10-06..10-18, ok. 70-150 meczów) wystarcza na
    bezpiecznik (czy nie zawyża), nie na dowód ROI. "+24% ROI" z 15 nóg nie jest
    przesłanką.
11. **Wdrożenie.** Nowy środek = nowe p = krzywe dopasowane od nowa na replayu
    z nim; przełącznik w `bet.sofa.epochs`, od następnego dnia 00:00Z; refit
    nigdy z `--tennis-serve-markets` / `--tennis-aces-opponent`, zanim
    `T-TENNIS-SERVE-MARKET-LINE` przejdzie.
12. **Podgląd w przód.** Priory tieru są dopasowane na całym cache (tak samo we
    wszystkich ramionach, tak samo jak na żywo); rating, efekt turnieju i
    returnujący - wyłącznie as-of.

## Ramiona (krok 1, replay historii)

Wszystkie: mecze best-of-three, zakres próbki jak SAMPLES
(`TENNIS_SAMPLE_SCOPE`), prior tieru jak SHEET, rozkład i rozrzut z funkcji
SHEET (`_settle_centred`).

| ramię | środek |
|---|---|
| BASE | jak SHEET dziś |
| ORACLE | BASE x G_mecz / Ḡ próbki (prawdziwe gemy meczu; tylko sufit, nie do wdrożenia) |
| EXP | BASE x E[G] / Ḡ, E[G] = średnia gemów sąsiadów ratingu (mecz / set 1 / set 2), as-of |
| EXP_T | EXP x f(turniej): suma zrealizowanych / suma środków EXP z wcześniejszych meczów tego `uniqueTournament`, z K = 30 wierszy |
| EXP_T_R | EXP_T x returnujący (`tennis_aces_opponent`, tylko asy) |

Ḡ = średnia długość meczów w próbce (gemy); próbka liczb na mecz jest przed
uśrednieniem normalizowana do Ḡ (a_i = x_i Ḡ / G_i), więc mecz 6:0 6:1 i
trzysetowy z tie-breakami ważą jak równe sobie tempo.

## Metryka i reguła decyzji

- Główna: log-loss kalibrowany (krzywa z linii rynkowych, train < 2026-01-01
  od 2025-01-01), na linii rynkowej, populacja TOUR, ramię minus BASE, 95%
  przedział z losowania meczów; osobno: asy mecz, asy sety, PB mecz, PB sety.
- Bezpiecznik: na liniach rynkowych TOUR przy pewności >= 0.70 zrealizowane
  minus pewność nie gorsze niż -2 pp (punkt), raportowane z przedziałem.
- Ramię przechodzi w rodzinie, gdy górna granica przedziału < 0 i bezpiecznik
  stoi. Z kilku przechodzących bierzemy najprostsze.
- Raportowane też: krzywa z całej drabinki.
- Doprecyzowanie przed pierwszym przebiegiem: wiersze powstają tylko dla meczów
  TOUR (historie próbek z wszystkich tierów), więc i krzywe obu rodzajów są
  dopasowane na wierszach TOUR - to populacja, na której Superbet wystawia
  rynek. Krzywa na żywo jest dziś dopasowana na wszystkich tierach; ta różnica
  wraca w kroku 3 (krzywa wdrażana = krzywa zmierzona).
- Skrypt: `scripts/sofa/measure_tennis_serve_exposure.py`.

## Krok 2-3

Ramię, które przejdzie: implementacja w SHEET za przełącznikiem (domyślnie
`None`), flaga replayu, test w `tests/sofa`; potem prawdziwy SHEET
(`process_fixture`) na rozliczonych liniach Superbetu 10-06..10-18, krzywa z
replayu z nowym p + line evidence, nogi >= 0.70 i x >= 0.90: luka i ROI z
przedziałem. Włączenie tylko przy przejściu kroku 1 i braku zawyżenia w kroku
3; inaczej przełącznik zostaje `None`, wynik idzie do
`T-TENNIS-SERVE-MARKET-LINE`.

## Odstępstwo (zapisane po pierwszym pełnym przebiegu, przed decyzją)

Pierwszy przebieg (`data/measure_serve_exposure_2026-10-19/replay.md`) czytał
kubeł krzywej z < 50 wierszami treningu jako surowe p - harness odziedziczony
po pomiarze 10-17. CONFIDENCE tak nie robi (`Calibration.realised` odrzuca
nogę bez kubła), więc bezpiecznik >= 0.70 mieszał nogi skalibrowane z
surowymi (BASE na krzywej z linii rynkowych -24..-28 pp). Poprawka harnessu,
nie ramion ani metryki: pusty kubeł czyta do log-loss najbliższy wypełniony
kubeł tego klucza, a noga bez własnego wypełnionego kubła nie liczy się przy
>= 0.70. Wyniki pierwszego przebiegu widziałem przed poprawką - mówię to
wprost; reguła decyzji się nie zmienia.
