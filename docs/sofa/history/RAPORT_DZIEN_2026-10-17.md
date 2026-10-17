# Dzień 2026-10-17: weryfikacja 10-16, siła rywala (rozciągnięcia), refit, kupon

Dzień mieszany (ledger „10-17 mieszany”): rozciągnięcia supremacji od
13:37Z, refit 2026-10-17 od 19:13Z - oba przeniesione do zbudowanego dnia
przez operatora („włączaj już teraz”, „krzywe też”). Nogi wydrukowane wcześniej
zostają zablokowane.

## 1. Rozliczenie 10-16 (szczegóły: `RAPORT_WERYFIKACJA_ROZLICZEN_2026-10-17.md`)

- Każdy wiersz i każda linia wszystkich sportów przeliczone niezależnym kodem
  z surowych danych; 5 defektów rozliczania poprawionych z testami (d5210b89):
  kartki z ławki, wynik połowy przepisany po meczu, nazwiska koszykarzy,
  brak `winnerCode`, pseudonimy CS2.
- Po poprawkach: piłka + tenis 38 438 / 38 456 zgodnych (18 = artefakt skryptu
  kontrolnego, Stocksund), sporty 20 407 / 20 407, ledger 28 dni bez MISMATCH.
- Kupony operatora ze zrzutów: 16 / 16 nóg rozliczonych tak jak Superbet.
- Wynik 10-16 (official): **-107,32 j.** po ostatniej iteracji (sekcja 6; rano -109,66 j.).
- Ostatnia iteracja po terminach zwrotów ITF / Næstved (20:59Z / 21:59Z): sekcja 6.

## 2. Siła rywala w golach i pozostałych rynkach

Pomiar: w meczach nierównych centrum goli było za mało rozciągnięte (faworyt
strzela więcej, outsider mniej). Poprawka (`bet.sofa.supremacy_stretch`):
centrum x exp(beta s) dla strony, exp(g1|s| + g2 s^2) dla sumy, s = oczekiwana
różnica goli z ratingu. Trzy przełączniki, każdy zmierzony poza próbą
(przedziały poniżej zera):

- gole (goals_for na fazę sezonu, połówki, sumy) -
  `docs/sofa/evidence/goals_stretch_2026-10-17.md`;
- 16 rynków licznikowych - `count_stretch_2026-10-17.md`;
- strzały i celne strzały zawodnika - `player_stretch_2026-10-17.md`.

Zmierzone i NIE wdrożone dziś: rynki wyniku z fazą sezonu (lepsze, osobny
proces krzywych), asy / podwójne błędy w tenisie ze składnikiem rywala
(sesja bet-38: zero na liniach Superbetu), hokej / koszykówka - żadna
poprawka nie przeszła.

Włączone od 13:37Z (przed refitem; połówki goli wstrzymane, bo na starych
krzywych zawyżały OVER faworyta o 3-6 pp). Przy okazji naprawiony błąd strony
nogi (244edaaa: Platense i podobne - 2 zmiany na 5 985 par, obie poprawne).

## 3. Refit 2026-10-17 (zainstalowany 19:13Z, ec3d5954)

- Powtórka `data/refit_2026-10-17/sofa_replay.db`: 1 282 317 meczów, 121,9 mln
  wierszy, flagi 10-16b + `--goals-stretch --count-stretch --player-stretch`
  (współczynniki rozciągnięć identyczne z żywymi).
- Krzywe na rozciągniętym p: kubełki UNDER goli realizują wyżej (np.
  goals_for UNDER 0,70-0,75: 0,712 -> 0,720; goals_1h_for UNDER: 0,692 -> 0,707),
  OVER nieco niżej - zgodnie z kierunkiem poprawki.
- Defekt znaleziony przed instalacją: dopasowanie zastąpiłoby zainstalowane
  krzywe strzałów lewą / prawą nogą kubełkiem 0-0,60 (wiersze powtórki z
  próbki, nie z estymatora shot_detail). Naprawione w `fit_confidence.py`
  z testem, krzywe przeliczone, edycja w `fit_manifest.json` (`post_fit_edits`).
- E2E w kopiach dnia, zegary budowy:
  - **10-16:** +83 / -44 nogi; rozliczone -89,94 -> -90,95 j. (odrzucone 41:
    32 W, -0,51 j.; dodane 81: 63 W, -1,52 j.); wspólne nogi ruszają się
    średnio o 0,2 pp; wygrane +0,05 pp, przegrane -0,02 pp.
  - **10-17:** +71 / -28 nóg (głównie gole i połówki), wspólne |ruch| 0,2 pp,
    maks. 6 pp.
- Instalacja: kopia `config/backup_2026-10-18`, tests/sofa 5 102 OK; połówki
  goli przywrócone, SHEET 10-17 przeliczony ręcznie, line evidence odświeżone
  na nowych krzywych (`--before 2026-10-17`).

### Czy nowe modele zamieniłyby przegrane nogi 10-16 w wygrane?

Nie. Nogi z kuponów operatora po nowych modelach:

| noga | pewność przed | po | wynik |
|---|---|---|---|
| Heerenveen gole (strona) poniżej 3.5 | 0,904 | 0,907 | przegrana |
| Frosinone gole 1. połowa poniżej 2.5 | 0,853 | 0,859 | przegrana |
| Alashkert „lub poniżej 4.5” | 0,889 | 0,889 | przegrana |

Heerenveen był w ratingu słabszą stroną (s -0,19), Frosinone przewaga +0,25 -
rozciągnięcie nie ma czego zmienić; rynki wyniku nie są rozciągane. To były
przegrane z rozrzutu, nie z siły rywala. Poprawka działa we właściwą stronę,
ale na jednym dniu jej skutek jest w szumie (-1 j.).

## 4. Kupon 10-17

- Przebudowy r1-r20; ostatnia na nowych modelach o 20:13Z.
- Odczyty: 15 rund analityków (piłka, hokej, siatkówka, koszykówka) + 5
  przebiegów weryfikatora; `reads.json` 2 097, weta 27 (m.in. Winterthur -
  Luzern, Al Qadsia - Fortis, Penafiel - Leça, Académica - Amarante, UNAN -
  San Marcos: defekt siły ligi w pucharze krajowym / beniaminek). C3 = 0.
- Weryfikator: McLeod (pp points poniżej 0.5) NO_BET - kurs spadł pod x 0,90;
  McKenna WATCH. Pozostałe ceny na żywo zgodne z wydrukiem.

## 5. Otwarte

- Siła ligi w krajowych pucharach w ratingu (źródło większości wet dnia) -
  pomiar i poprawka.
- Line evidence rynków „lub” jest kluczowane per rynek, nie per plaster:
  plaster bez krzywej (odrzucony przez bramkę) czyta pulę rynku przez granicę
  Wilsona - do zmierzenia przed zmianą (zmienia druk, przełącznik).
- Rynki wyniku z fazą sezonu (zmierzone lepsze, osobny proces krzywych).
- Decyzje operatora: krecz w tenisie (dziś zwrot wszystkich nóg), mecz
  przerwany (5.D.5, dziś nigdy zwrot).

## 6. Ostatnia iteracja rozliczenia 10-16 (22:02Z, po terminach ITF / Næstved)

- SETTLE 10-16 ponownie: +94 wiersze (statystyki opublikowane w ciągu dnia),
  361 / 373 meczów rozliczonych. Nierozliczone zostają: krecze (592 wierszy,
  zwrot), mecze przerwane (`NOT_FINISHED` 326 - reguła 5.D.5 otwarta, nigdy
  zwrot), 43 `POSTPONED` przed terminem lokalnym, rożne bez statystyk dostawcy
  (poranny sweep).
- `audit_settle_identity`: 41 znalezisk - te same `NAME_BELOW` co rano
  (hokej / kosz / siatka / CS2, inna pisownia; każda tożsamość sprawdzona w
  iteracji A).
- Ledger 10-16 (`record_results --from 2026-10-09`):

| wariant | pozycje | rozliczone | W | L | j. | ROI |
|---|---|---|---|---|---|---|
| official [10-16 mieszany] | 3 142 | 3 064 | 2 454 | 610 | **-107,32** | -3,5% [-5,8, -1,1] |
| removed:reads | 96 | 95 | 76 | 19 | +1,22 | +1,3% |

Pomiary sportów 10-16 (luka trafień vs uczciwe p): koszykówka -1,4 pp,
hokej -1,9, siatkówka +1,3, CS2 -0,1.
