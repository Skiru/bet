# F54 — rynki zawodnicze, piłka i tenis

2026-09-22. Co zmierzono, co zbudowano, i czego **nie** sprawdzono.

## 1. Pomiar tablicy, zanim cokolwiek powstało

Wyliczone z `runs/sofa/2026-09-22/04_offer.json` i z żywych payloadów Superbetu
(`/v2/pl-PL/events/{id}`), nie z pamięci.

### Tenis — `N. set - <zawodnik> liczba gemów`

| | |
|---|---|
| wycenione rynki, 2026-09-22 | **827** |
| mecze tenisowe, które je niosły | **166** |
| ile z nich trafiało do `unmapped_markets` | **wszystkie** |
| obie strony kwotowane? | **tak** — `Poniżej 4.5` / `Powyżej 4.5` na każdym szczeblu |

Odrzucał je `_SUBJECT_IS_SCOPE` i odrzucał **słusznie**: bezmyślny wzorzec
„<gracz> liczba gemów" czytał podmiot jako `"1. set - Kenta Kawada"`, a jedyną
metryką, jaka wtedy istniała, był `games_won_for` z całego meczu. Brakowało
metryki, nie mapowania.

### Piłka — `Zawodnik - liczba ...`

Payload zdarzenia 13718742 (Criciúma) i 2026-09-24 Seattle Sounders:

| market | selekcji (Seattle) | źródło w Sofascore |
|---|---|---|
| `Zawodnik - liczba strzałów` | 283 | `totalShots` |
| `Zawodnik - liczba celnych strzałów` | 149 | `onTargetScoringAttempt` |
| `Zawodnik - liczba asyst` | 82 | `goalAssist` |
| `Zawodnik - liczba spalonych` | 19 | `totalOffside` — **nie wzięte**, patrz §3 |
| 8 wariantów „lewą nogą / głową / spoza pola" | 485 | **brak** w Sofascore |
| `strzeli gola` / `otrzyma kartkę` i pochodne | ~300 | bez linii, to nie szczebel |

**Kwotowane jednostronnie.** Na całej tablicy 2026-09-22: **437 selekcji
„powyżej", 0 „poniżej"**. To jest fakt, który decyduje o wartości całej
rodziny (§4).

Pokrycie jest nierówne i pojawia się **blisko meczu**: 2026-09-23 na 126
meczach piłkarskich **zero** rynków `Zawodnik - liczba`; 2026-09-24 niosły je
m.in. Seattle–Real Salt Lake, Japonia–Urugwaj, Korea–Ekwador. 2026-09-22 — 4 z
182 meczów.

## 2. Rozkład, który zdecydował o estymatorze

80 149 zdarzeń tenisowych z cache'u, obaj gracze liczeni,
`docs/sofa/evidence/games_won_per_set_distribution.md`:

| gemy | set 1 | set 2 |
|---|---|---|
| 4 | 10,8% | 10,5% |
| **5** | **4,4%** | **4,1%** |
| **6** | **45,6%** | **45,8%** |
| 7 | 10,3% | 9,4% |

Dolina na pięciu, ściana na sześciu — bo zwycięzca seta bierze co najmniej
sześć gemów, przegrany najwyżej pięć, a 5:5 rozstrzyga się na 7:5 albo 6:6.
**Superbet stawia szczebel na 5,5, dokładnie na urwisku.**

To jest F49 o jeden set niżej, więc `games_won_set{1,2,3}_for` wchodzą do
`EMPIRICAL_FREQUENCY_METRICS` **od pierwszego dnia**, na pomiarze samej
wielkości, a nie po pierwszym rozliczonym dniu.

## 3. Trzy pułapki payloadu `/lineups`, i co z każdą zrobiono

Nagrany payload: `docs/sofa/evidence/event_16363633_lineups.json`, 40
zawodników, 31 z nich zagrało.

1. **Zawodnik z ławki ma `totalShots: 0` i nie ma `minutesPlayed`.** To nie
   zero. Superbet taki zakład **zwraca**, nie rozlicza na przegraną. Bramką
   wejścia jest obecność `minutesPlayed` — i tylko ona.
2. **`onTargetScoringAttempt` bywa pominięte przy zerze** (obecne u 6 z 31
   grających). Tu zero jest **dowodliwe**: payload niesie rozkład
   `totalShots == celne + niecelne + zablokowane + słupek`, który zamknął się
   **31/31**. Zero bierzemy tylko wtedy, gdy ta tożsamość się zamyka; gdy nie
   — `INTERNAL_INCONSISTENT`, bo reszty nie wolno nam zmyślić.
3. **`totalOffside` też bywa pominięte** (obecne u 4 z 31) i **nie ma**
   tożsamości, która zamknęłaby zero. Dlatego `player_offsides_for` **nie
   istnieje**, mimo że Superbet ten rynek wycenia. Odblokowałby go pomiar:
   suma spalonych zawodników musi równać się drużynowemu `offsides` z
   `/statistics`. Nie zrobiono go.

`goalAssist` jest obecne u 31 z 31 grających, więc jego brak to brak danych i
nic nie jest domyślane.

## 4. Czego rodzina piłkarska **nie** potrafi, i dlaczego to zostaje

Jednostronna kwota ⇒ brak drugiej strony ⇒ nie ma czego odvigować ⇒
`market_p is None` ⇒ `NO_PRICE_ANCHOR` ⇒ werdykt **`LEAN`**, nigdy `VALUE`.
**Żaden piłkarski zakład zawodniczy nie może dziś trafić do kuponu.**

To nie jest bramka do rozkręcenia. Z drabiny jednostronnej marży wyciągnąć
się **nie da**: różnice `1/o_k − 1/o_{k+1}` sumują się do jedynki tożsamościowo,
niezależnie od marży, bo `P(X=0)` nie jest osobno kwotowane. Trzeba by ją
**zmierzyć** na rozliczonych dniach, a rozliczać tę rodzinę zaczynamy dopiero
teraz.

Kierunek jest zgodny z tym, co już wiemy: 2026-09-19 wiersze bez kotwicy
cenowej miały medianę nadwyżki **4,95** wobec **0,24** dla ukotwionych, przy
medianie kursu 12,0 wobec 3,10. To nie była przewaga, to był brak kontroli.
Test `test_a_one_sided_player_rung_can_never_be_value` pilnuje, żeby zmiana
tej reguły nie wpuściła tej rodziny do kuponu po cichu.

## 5. Weryfikacja na żywych danych

**Tenis, pełny łańcuch** (Superbet na żywo + historia z cache'u, bez mostu —
nowa metryka czyta listing, więc nie potrzebuje `/statistics`):

```
tenis na Superbecie 2026-09-23:            378 meczów
obaj gracze w cache:                        50
wiersze SHEET z games_won_set*_for:        760
z tego VALUE:                               88   (11,6%)
```

Każdy wiersz z prawdziwym `market_p` z odvigowanej drabiny, prawdziwą próbką i
prawdziwym kursem. Skrypt: `scratchpad/verify_tennis.py`.

**11,6% VALUE to wyraźnie więcej niż ~8,4% dla całej tablicy.** Nowa rodzina,
która flaguje VALUE częściej niż reszta boardu, to dokładnie kształt
„selektora niezgody" — traktować jako podejrzenie do zmierzenia po pierwszym
rozliczonym dniu, nie jako dobrą wiadomość.

**Piłka, OFFER:** 190 szczebli zawodniczych wyciągniętych z prawdziwego
payloadu 13718742 (129 × celne strzały, 61 × asysty), reszta ekranu
zawodniczego została w `unmapped_markets` z podaną przyczyną.

**Regresja:** SHEET przepuszczony ponownie po całym 2026-09-22 —
10 692 wiersze przed i po, **zero** różnic poza `sample_newest_days`
przesuniętym o dobę (liczy się względem `now()`). Artefakt dnia przywrócony.

## 6. Czego NIE sprawdzono — wymienione, nie przemilczane

- **Pętla `client.event_lineups` przez most nie została uruchomiona ani raz.**
  Most był martwy przez całą sesję (`last browser poll 20593 s ago`).
  Sprawdzone jest: parsowanie prawdziwego payloadu `/lineups` (plik dowodowy,
  40 zawodników), cache (round-trip, w tym pusta odpowiedź jako fakt) i
  budowa próbki. **Nie** sprawdzone: że route odpowiada 200 przez most i że
  koszt wychodzi taki, jak policzono. Pierwszy piłkarski mecz z rynkiem
  zawodniczym to zweryfikuje.
- **Żaden wiersz tej rodziny nie został jeszcze rozliczony.** SETTLE ma
  ścieżkę (`_settle_player`) i testy, ale zerowy przebieg na żywo.
- **Próg dopasowania nazwiska (85) i margines (5,0) nie są dopasowane.**
  Margines jest po prostu ten sam, którego używa `_subject_is_home`, a tam
  wybiera się między **dwoma** kandydatami; skład daje dwudziestu, więc
  maksimum szumu jest większe i 5,0 jest raczej hojne. To pierwsza rzecz do
  zmierzenia na rozliczonych wierszach.
- **Minuty nie filtrują niczego.** Wejście na 12 minut wchodzi do próbki na
  równi ze startem, bo Superbet wypłaca zakład po wejściu z ławki. Wiersz
  niesie profil (`PLAYER_MINUTES`), decyzję zostawiamy analitykowi. Czy próg
  minutowy poprawiłby prognozę — **nie zmierzono**.
- **Próbka zawodnika to ostatnie mecze jego klubu, nie jego.** Zawodnik
  pozyskany w oknie transferowym ma krótką próbkę; widać to jako różnicę
  `sample_size` wobec `squad_matches`, ale nic tego nie zgłasza osobno.
- **`_MOST_SCOPED` zna tylko set 1 i 2**, więc `3. set - najwięcej gemów`
  zostaje nieczytane, mimo że `games_won_set3_for` już istnieje. Nie ruszane.
- **`1. set - liczba gemów` (suma setowa, 132 mecze) nadal nieczytana.** To
  sąsiednia rodzina, nie zawodnicza — świadomie poza zakresem.
