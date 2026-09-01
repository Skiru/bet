# Plan: dociągnąć rynki, które Superbet realnie wystawia

Stan na 2026-09-01. Wszystkie liczby poniżej są zmierzone na runie
`runs/2026-08-31/` i na żywej ofercie Superbetu (fixture Atletico MG–Cruzeiro,
`eventId=14462663`, 2026-09-02), nie oszacowane.

## Skąd biorą się kursy Superbetu (odpowiedź na pytanie operatora)

Publiczne API oferty prematch — to samo, które czyta przeglądarka na
superbet.pl. **Bez logowania, bez konta, bez sesji.** Kod:
[`src/bet/api_clients/superbet.py`](../src/bet/api_clients/superbet.py).

| | |
|---|---|
| host | `production-superbet-offer-pl.freetls.fastly.net`, rozwiązany z `superbet.pl/static/js/fetchConfig/app`, nadpisywalny przez `SUPERBET_BASE_URL` |
| lista zdarzeń | `GET /v2/pl/events/by-date?startDate=…&endDate=…&offerState=prematch` — 1 995 zdarzeń w oknie 48 h, **bez kursów** |
| kursy | `GET /v2/pl/events/{id}` — pełna lista `odds`; odpowiedź to **lista jednoelementowa**, nie obiekt |
| koszt | **brak endpointu zbiorczego** → jedno wywołanie na mecz. `run_superbet.py --max-events` domyślnie 250 |
| kształt wiersza | `{marketName, name, price, status}` — linia i strona siedzą w `name` („Powyżej 8.5"), nie w polach |

OddsPapi jest w `config/provider_registry.json` właśnie po to, żeby serwować
kursy Superbetu, ale `/v4/fixtures` i `/v4/odds` odpowiadają **403** przy
aktywnej subskrypcji i 0/250 zużytych zapytań. To stan billingowy, nie awaria,
i dlatego ta ścieżka jest martwa, a nie obchodzona.

Cena jest **zdjęta raz**, o konkretnej godzinie, i się rusza. Każdy artefakt to
stempluje i tak ma zostać.

## Diagnoza: gdzie dziś ucieka wartość

Run 2026-08-31, pełna ścieżka:

```
30 054 wierszy arkusza  →  451 dotarło do porównania z Superbetem  →  3 przeszły próg
```

Trzy niezależne przyczyny, w kolejności wielkości:

**1. 20 852 wiersze (69%) to propsy zawodników, których nie da się wycenić.**
`PLAYER_SCOPE_MARKETS` w [`superbet_offer.py`](../src/bet/simple_stats/superbet_offer.py)
zwraca `SCOPE_NOT_SUPPORTED` dla każdego z nich. Uzasadnienie w docstringu —
„joining them to our player ids would be a guess rather than a lookup" — było
słuszne przy dopasowywaniu po całym dniu, ale **wewnątrz dopasowanego meczu to
nie jest zgadywanie**: mamy potwierdzony skład z `/events/{id}/lineups/`, czyli
~30 znanych nazwisk przeciwko ~30 stringom.

**2. Mapujemy 24 z 398 unikalnych nazw rynków prostych.** Na jednym dużym
meczu Superbet wystawia 4 987 kursów: 4 558 rynków prostych i 429 gotowych
kombinacji SUPERBETS. Większość niezmapowanych jest odrzucona słusznie (dokładne
wyniki, handicapy, okna minutowe, połowy). Ale nie wszystkie — patrz Faza 3.

**3. Drabinki linii się rozjeżdżają, a przy części rynków Superbet podaje
jedną linię na mecz.** Zmierzone na tym samym meczu:

| nasz rynek | nasze linie | drabinka Superbetu | pokrycie |
|---|---|---|---|
| `fouls_total` | 20.5, 22.5, 24.5 | **30.5** (jedna) | **zero** |
| `cards_total` | 3.5, 4.5, 5.5 | 5.5 – 9.5 | tylko 5.5 |
| `shots_total` | 19.5, 22.5, 25.5, 28.5 | 23.5 – 27.5 | tylko 25.5 |
| `offsides_total` | 1.5, 2.5, 3.5, 4.5 | **2.5** (jedna) | 2.5 |
| `shots_on_target_total` | 4.5 – 7.5 | 5.5 – 9.5 | 5.5, 6.5, 7.5 |
| `corners_total` | 6.5 – 12.5 | 2.5 – 17.5 | pełne |
| `goals_total` | 0.5 – 4.5 | 0.5 – 6.5 | pełne |
| `cards_for` | 1.5, 2.5, 3.5 | 2.5, 3.5, 4.5 | 2.5, 3.5 |

Stała siatka linii nigdy nie trafi w rynek, który bukmacher wystawia jako
**jedną linię dobraną pod mecz**. Dokładanie kolejnych linii tego nie naprawi —
naprawia to odwrócenie kierunku.

## Faza 1 — linie sterowane ofertą (`LINE_NOT_OFFERED` przestaje istnieć)

Dziś: wybieramy linię → pytamy, czy Superbet ją ma → `LINE_NOT_OFFERED`.
Po zmianie: czytamy drabinkę Superbetu dla tego meczu i rynku → liczymy `p_low`
dokładnie dla tych linii.

**Jest to możliwe bez przestawiania pipeline'u**, bo kolejność kroków już na to
pozwala:

```python
STEPS = ("discover", "enrich", "market_context", "tipsters", "superbet", "analyze")
```

SUPERBET **już biegnie przed ANALYZE**. Oferta jest na dysku, zanim arkusz
powstaje.

Zakres zmiany:
- `analyze.py` konsumuje siatkę w trzech miejscach (`market_def["lines"]`,
  linie 583, 630, 682). Dodać opcjonalny parametr `offered_lines:
  dict[(event_id, market, team_name), list[float]]`; brak wpisu → stara siatka.
- `superbet_offer.py` wystawia builder tej mapy z `SuperbetOfferV1`.
- `STANDARD_MARKET_LINES` zostaje jako fallback dla meczów bez oferty (mecze
  spoza Superbetu, tenis bez pokrycia) — nie usuwamy go.

Efekt uboczny, którego chcę pilnować: liczba wierszy urośnie (Superbet ma 16
linii rożnych zamiast naszych 7). Trzeba przyciąć drabinkę do okna wokół
obserwowanej mediany, inaczej arkusz puchnie o rząd wielkości bez wartości.

**To jest zmiana o największej dźwigni i powinna iść pierwsza**, bo każda
kolejna faza dokłada rynki, które bez niej trafiłyby w ten sam mur.

## Faza 2 — propsy zawodników od końca do końca (te 69%)

Format jest w pełni parsowalny — zweryfikowane na żywej ofercie:

```
marketName = "Zawodnik - liczba celnych strzałów"
name       = "Lodi, Renan - powyżej 0.5"
```

Rozdzielić `name` po **ostatnim** ` - `; lewa strona to zawodnik, prawa idzie do
istniejącego `_OUTCOME_RE`. Format nazwiska bywa `"Nazwisko, Imię"` albo
jednoczłonowy (`"Ze Ivaldo"`, `"Fred"`, `"Bernard"`) — obie postacie występują
na tym samym meczu.

Rynki, dla których **wiersze już istnieją** i brakuje wyłącznie ceny:

| Superbet | nasz rynek | pole bzzoiro | kursów na meczu |
|---|---|---|---|
| Zawodnik - liczba strzałów | `player_total_shots` | `total_shots` | 272 |
| Zawodnik - liczba popełnionych fauli | `player_fouls` | `fouls` | 228 |
| Zawodnik - liczba fauli na zawodniku | `player_was_fouled` | `was_fouled` | 213 |
| Zawodnik - liczba celnych strzałów | `player_shots_on_target` | `shots_on_target` | 132 |
| Zawodnik - otrzyma kartkę | `player_cards` | `yellow_card` + `red_card` | 42 |

Rynki **nowe**, w pełni pokryte danymi (gęstość historii sprawdzona: 30/30
meczów ma wartość dla każdego z tych pól, dla każdego testowanego zawodnika):

| Superbet | nowy rynek | pole bzzoiro | kursów |
|---|---|---|---|
| Zawodnik - liczba odbiorów | `player_tackles` | `total_tackle` | 222 |
| Zawodnik - liczba asyst | `player_assists` | `goal_assist` | 76 |
| Zawodnik - liczba spalonych | `player_offsides` | `total_offside` | 58 |

Drabinki Superbetu są **szersze niż nasze**: strzały 0.5–7.5, celne 0.5–3.5,
faule popełnione 0.5–4.5, faule na zawodniku 0.5–5.5, odbiory 0.5–4.5. Nasze
`PLAYER_PROP_LINES` kończą się na 2.5. Faza 1 to zdejmuje sama.

**Dopasowanie nazwisk — dwuwarstwowa bariera**, ta sama co przy meczach:
1. Kandydaci wyłącznie ze składu tego meczu (`/events/{id}/lineups/`,
   `lineup_status`), nigdy z całego dnia.
2. `rapidfuzz` z progiem, plus twardy warunek: dopasowanie musi być
   **jednoznaczne** w obrębie meczu. Dwóch zawodników powyżej progu →
   `PLAYER_AMBIGUOUS`, brak ceny, wiersz w `data_gaps`. To jest dokładnie
   pułapka z `duplicate-fixtures-reach-the-coupon` przeniesiona na zawodników,
   i musi mieć własny test na parze braci/imienników.

Trzecia bariera, wynikająca z rejestru 2026-08-30/31: prop na zawodnika ma
**dwa** źródła ryzyka, minuty i wolumen drużyny. `lineup_status` pokrywa
pierwsze. Do drugiego dołożyć do wiersza rate drużyny dla tego samego zdarzenia
(Lecce popełniło 9 fauli w całym meczu na 16 zawodników — prop „powyżej 0.5
fauli" nie miał z czego wejść).

## Faza 3 — rynki, które mają i bzzoiro, i Superbet, a my ich nie liczymy

bzzoiro daje **55 pól drużynowych** i **75 pól zawodnika** na mecz. Superbet
wystawia z tego jeszcze:

| Superbet | nowy rynek | pole bzzoiro | drabinka |
|---|---|---|---|
| Liczba obronionych strzałów przez bramkarza | `saves_total` | `goalkeeper_saves` / `total_saves` | 3.5 – 7.5 |
| {Drużyna} - liczba obronionych strzałów… | `saves_for` | to samo, per strona | 1.5 – 3.5 |
| Liczba odbiorów | `tackles_total` | `tackles` / `total_tackles` | 28.5 (jedna) |
| {Drużyna} - Liczba odbiorów | `tackles_for` | per strona | 14.5 (jedna) |
| Liczba strzałów w obramowanie bramki | `woodwork_total` | `hit_woodwork` | 0.5, 1.5 |
| {Drużyna} - Liczba strzałów w obramowanie… | `woodwork_for` | per strona | — |
| Liczba czerwonych kartek {Drużyna} | `red_cards_for` | `red_cards` per strona | — |
| Liczba rzutów z autu (+ per drużyna) | `throw_ins_total/_for` | `throw_ins` | 39.5 (jedna) |
| Liczba wybić od bramki (+ per drużyna) | `goal_kicks_total/_for` | `goal_kicks` | 16.5 (jedna) |

**Uwaga o pułapce z obramowaniem.** `"obramowanie bramki"` jest dziś w
`BANNED_SUBSTRINGS` i to był poprawny fix — brano je za strzały celne
(`superbet-is-the-only-real-price`). Poprawką **nie jest** zdjęcie zakazu, tylko
zmapowanie tego ciągu na **własny** rynek `woodwork_*`, sprawdzane *przed*
listą zakazów. Zakaz zostaje jako reguła „to nigdy nie jest `shots_on_target`".
Bez testu, który to pilnuje, ta faza nie wchodzi.

Rzuty z autu i wybicia od bramki są ostatnie w kolejce: dane są, ale
`PRIORITY_METRICS` ich nie zbiera, więc wymagają też zmiany w `providers.py`, a
wartość obstawiania ich jest wątpliwa.

## Faza 4 — kombinacje SUPERBETS

429 z 4 987 kursów na jednym meczu to gotowe sloty z boostem, w tym samym
feedzie, z nogami rozdzielonymi średnikiem:

```
"Atletico MG powyżej 3.5 celnych strzałów; Atletico MG strzeli powyżej 0.5 gola;
 Atletico MG wykona powyżej 4.5 rz.rożnych"
```

To jest **jedyne miejsce, w którym w rejestrze 2026-08-30/31 znalazła się realna
przewaga.** Boost jest wart ~+12,6% ceny i to on przestawił Napoli–Como z −5,5%
na +6,1%. Reszta była poniżej fair z boostem i bez.

Zakres:
- rozbić `marketName` po `;`, każdą nogę przepuścić przez istniejący
  `classify_market` + `parse_outcome`;
- odrzucić cały slot, jeśli **którakolwiek** noga jest nierozpoznana — slot
  wyceniony częściowo jest gorszy niż niewyceniony;
- wycenić przez `slip_audit.py` (już jest) i pokazać cenę fair obok oferowanej.

Warunek konieczny: `slip_price_floor()` na najsłabszej nodze, zanim cokolwiek
trafi do raportu.

## Co zostaje na zewnątrz i dlaczego

- **Podpopulacje strzałów** (głową, lewą/prawą nogą, spoza pola karnego) —
  Superbet wystawia 5 wariantów, bzzoiro **nie rozbija strzałów zawodnika po
  części ciała**. Zostają w `BANNED_SUBSTRINGS`.
- **`Zawodnik - liczba odbiorów na zawodniku`** (212 kursów) — nie wiadomo, czy
  to `challenge_lost`, `total_contest`, czy coś trzeciego. Nie mapować, dopóki
  jedno rozliczone zdarzenie tego nie rozstrzygnie.
- **Rynki minutowe, przedziały, dokładne wyniki, handicapy, zakresy połówkowe** —
  nie są over/under na liczniku i nie mają odpowiednika w arkuszu.
- **`Najwięcej…`, `Którykolwiek…`, `Każda z drużyn…`** — kształt trójstronny lub
  agregat, nie linia. Zostają.

## Ryzyka

1. **Puchnięcie arkusza.** 30 054 wiersze już teraz; linie sterowane ofertą plus
   trzy nowe rynki zawodnika mogą to podwoić. Przycięcie drabinki do okna wokół
   mediany jest częścią Fazy 1, nie osobnym zadaniem.
2. **Koszt wywołań.** Jedno zapytanie na mecz, 250 meczów. Bez zmian, ale przy
   pełnym parsowaniu propsów rośnie czas parsowania, nie liczba zapytań.
3. **Dopasowanie zawodników.** Jedyne miejsce w planie, gdzie błąd jest **cichy**
   i trafia na kupon jako prawidłowo wyglądający wiersz. Stąd twardy warunek
   jednoznaczności i osobny test.
4. **Snapshot ceny.** Rośnie liczba wierszy z ceną, więc rośnie ekspozycja na to,
   że cena już się ruszyła. Stempel czasu w każdym artefakcie zostaje i ma być
   widoczny w raporcie, nie tylko w JSON-ie.

## Status wdrożenia

**Faza 1 i Faza 2 są zrobione (2026-09-01).** Faza 3 i 4 czekają.

Co doszło:

| plik | co |
|---|---|
| `src/bet/simple_stats/offered_lines.py` | nowy: indeks drabinek z oferty + join nazwisk (3 przejścia) + przycinanie wokół mediany |
| `src/bet/simple_stats/superbet_offer.py` | `PLAYER_MARKET_NAMES`, `classify_player_market`, `parse_player_outcome`, `player_alias_index`; `lookup_line` rozwiązuje propsy |
| `src/bet/simple_stats/analyze.py` | `_resolve_lines` + `line_limit`; `analyze_dossier(dossier, offered)` |
| `scripts/simple/run_analyze.py` | oferta ładowana **przed** budową arkusza, ten sam obiekt zasila kolumnę |
| `src/bet/api_clients/bzzoiro.py`, `providers.py`, `market_ranking.py`, `contracts.py` | trzy nowe rynki zawodnika + `PLAYER_NOT_MATCHED` |
| `tests/simple_stats/test_offered_lines.py` | 27 testów, w tym pełna pętla na realnym zrzucie oferty |

Zmierzone na żywym meczu (Atletico MG–Cruzeiro, 4 987 kursów):

- czytamy **1 459 linii** zamiast 221 — 1 238 z nich to propsy, których wcześniej nie dało się wycenić w ogóle;
- **358 drabinek** w indeksie (24 drużynowe/meczowe, 334 zawodnika);
- **46 z 49** stringów Superbetu połączonych z nazwiskami z bzzoiro, zero kolizji;
- **3 z 24** drabinek drużynowych nie miały żadnego wspólnego punktu ze starą siatką — wszystkie trzy to faule (`fouls_total` 30.5 vs 20.5/22.5/24.5; `fouls_for` 14.5/15.5 vs 8.5/10.5/12.5).

Regresja na archiwalnym dossier 2026-08-31, bez oferty: 30 054 → **34 866** wierszy.
Cała różnica to poszerzony fallback linii zawodnika (+4 812). Trzy nowe rynki
(`player_tackles`/`_assists`/`_offsides`) dały **zero** wierszy i to jest
poprawne — dossier zebrano, zanim klient nauczył się normalizować te pola.
**Wymagają świeżego ENRICH-u.**

## Kolejność

Faza 1 → Faza 2 → Faza 3 → Faza 4. Faza 1 jest warunkiem sensu każdej kolejnej;
Faza 4 jest jedyną, która sama z siebie znalazła dodatnią wartość, ale bez
Fazy 1 nie ma z czego wyceniać jej nóg.
