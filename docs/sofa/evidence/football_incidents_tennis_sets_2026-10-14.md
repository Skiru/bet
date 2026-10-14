# Rynki piłki z incydentów i tenisowe rynki setów – pomiar i podpięcie (2026-10-14)

Dwie grupy rynków, które Superbet wystawia, a sofa dotąd zostawiała w
`unmapped_markets`, policzone z danych już zapisanych w bazie – bez mostka,
bez nowego pobierania. Próg podpięcia (zadanie): prognozy **>= 0,70**
skalibrowane, czyli |realizacja − prognoza| <= 2 pp przy n >= 300 w tym
zakresie. Rynek poniżej progu – tylko pomiar.

Oba pomiary są walk-forward, as-of każdego meczu (stan modelu tylko z meczów
wcześniejszych), okno testu **2026-06-09 .. 2026-10-14**, baza
`data/sofa.db` otwarta tylko do odczytu. Log-loss: model minus baza (ujemne =
model lepszy), 95% CI to bootstrap meczów. „Wilson” to dolna granica 95%
realizacji.

## A. Piłka – incydenty (`scripts/sofa/measure_football_incidents.py`)

Źródło: `sofa_event_stats.incidents_json` (147 242 czytelne listy
incydentów meczów historii piłki; czytelna = gole z incydentów kończą się na
wyniku z 90 minut listingu), historia i rating z
`data/cache/football_history.pkl` (towarzyskie wyłączone). Czytnik:
`bet.sofa.football_incidents.read_incidents` – tylko czas regularny
(dogrywka i seria karnych się nie liczą). Kartki i karne tylko z **pełnego
zapisu** (lista z substytucją – reguła potoku `metrics.INCIDENT_FEED_DETAIL`):
10 778 z 19 009 meczów testu.

Modele:

- **1. gol** (dom / wyjazd / nikt): niezależne NB goli na czystych środkach
  ratingu (`FootballForecast.centre("goals_for", side)`, r 7,586 z modelu
  podwójnej szansy): P(nikt) = P(0:0), P(strona) = (1 − P(nikt)) × udział
  strony w oczekiwanych golach. Baza: częstość rozgrywek as-of ściągnięta do
  częstości płci (30 meczów).
- **Przedziały minut 1. gola** (15- i 10-minutowe): ten sam mecz jako proces
  Poissona, P(brak gola do t) = P(nikt)^F(t), F – as-of udział wszystkich goli
  czasu regularnego przed minutą t.
- **Czerwone kartki / karne O/U 0,5 i 1,5** (mecz): `league` – as-of częstość
  rozgrywek ściągnięta do częstości płci (30 meczów); `team` – Poisson ze
  średniej dwóch drużyn (as-of sumy meczowe ściągnięte do ligi, 20 meczów).
  Baza: as-of częstość płci.

### Wyniki (wszystkie mecze)

| rynek | n meczów | model − baza [CI] | n >= 0,70 | p / realizacja >= 0,70 | Wilson | różnica | próg |
|---|---|---|---|---|---|---|---|
| 1. gol | 18 481 | −0,0300 [−0,0341; −0,0267] | 1 376 (2,5% wyborów) | 0,759 / 0,770 | 0,747 | +1,0 pp | **spełniony** |
| 1. gol, przedziały 15 min | 18 481 | −0,0040 [−0,0073; −0,0007] | 0 | – | – | – | nie (nic >= 0,70) |
| 1. gol, przedziały 10 min | 18 481 | −0,0093 [−0,0127; −0,0054] | 0 | – | – | – | nie (nic >= 0,70) |
| czerwone O/U 0,5 (`league`) | 10 778 | −0,0085 [−0,0110; −0,0060] | 10 152 | 0,825 / 0,832 | 0,825 | +0,7 pp | **spełniony** |
| czerwone O/U 0,5 (`team`) | 10 778 | −0,0066 [−0,0097; −0,0034] | 9 721 | 0,826 / 0,837 | 0,830 | +1,1 pp | spełniony |
| czerwone O/U 1,5 (`league`) | 10 778 | −0,0045 [−0,0065; −0,0025] | 10 778 | 0,973 / 0,977 | 0,974 | +0,4 pp | **spełniony** |
| karne O/U 0,5 (`league`) | 10 778 | −0,0177 [−0,0200; −0,0153] | 9 518 | 0,776 / 0,786 | 0,777 | +1,0 pp | **spełniony** |
| karne O/U 0,5 (`team`) | 10 778 | −0,0165 [−0,0192; −0,0140] | 9 033 | 0,782 / 0,789 | 0,780 | +0,7 pp | spełniony |
| karne O/U 1,5 (`league`) | 10 778 | −0,0010 [−0,0029; +0,0006] | 10 778 | 0,966 / 0,968 | 0,965 | +0,2 pp | **spełniony** |

Realizacja w teście: czerwona w meczu 17,7%, dwie+ 2,3%; karny przyznany
22,7%, dwa+ 3,2%. 1. gol: gospodarz 51,2%, gość 42,7%, nikt 6,1%.

Kalibracja 1. gola (każdy wybór): 0,70–0,75 n 740 0,723 → 0,732; 0,75–0,80
n 378 0,771 → 0,791; 0,80–0,85 n 163 0,823 → 0,847; 0,85–0,90 n 68 0,872 →
0,824. Wybory >= 0,70 to w 100% faworyt strzelający pierwszy (dom 963, gość
413). Kobiety osobno: +5,7 pp przy n 265 (poniżej n 300; błąd po ostrożnej
stronie), mężczyźni −0,1 pp n 1 111. Bez par `UNLINKED`: +0,9 pp n 1 357.

Kalibracja czerwonych O/U 0,5 (`league`, OVER i UNDER): 0,70–0,75 +1,4 pp
(n 714), 0,75–0,80 +2,4 pp (n 2 568), 0,80–0,85 +0,1 pp (n 3 818), 0,85–0,90
−0,2 pp (n 2 184). Karne O/U 0,5 (`league`): 0,70–0,75 +2,4 pp (n 4 147),
0,75–0,80 −0,1 pp (n 3 018), 0,80–0,85 −0,4 pp (n 1 496), 0,85–0,90 −3,3 pp
(n 306). Pojedyncze kubełki wychodzą poza 2 pp, zakres >= 0,70 jako całość
– nie. Wybory >= 0,70 to prawie wyłącznie UNDER.

**Podpięte** (`FOOTBALL_INCIDENT_MARKETS_FROM_UTC`, `None`): `first_goal`,
`red_cards_total` i `penalties_total` (linie 0,5 i 1,5, model `league` – lepszy
log-loss od `team` przy O/U 0,5, prostszy). **Tylko pomiar**: przedziały minut
1. gola (żadna prognoza nie dochodzi do 0,70), warianty połów i drużyn
(niezmierzone).

## B. Tenis – sety (`scripts/sofa/measure_tennis_outcome_model.py`)

Skrypt z nocy 2026-10-12 rozszerzony o zwycięzcę 2. seta, dolną granicę
Wilsona i werdykt progu. Historia singli z listingów
(`tennis_rating.load_history`), rating as-of dnia meczu
(`AsOfRating.model_at`, tabela tier × płeć, jak w SHEET), tylko ukończone
best of three; baza = as-of częstość klasy (tier × płeć). Wariant `live` to
współczynniki z `config/tennis_rating.json` (widziały okno testu – znane
spojrzenie w przód replayu), `clean` – dopasowane wyłącznie przed oknem.
33 336 meczów (pominięte: 8 891 bez ratingu, 1 584 nieukończone, 283 best of
five, 118 drużynowe).

| rynek | wariant | model − baza [CI] | n >= 0,70 | p / realizacja | Wilson | różnica | próg |
|---|---|---|---|---|---|---|---|
| zwycięzca meczu (kontrola) | live | −0,1248 [−0,1292; −0,1204] | 15 426 | 0,813 / 0,819 | 0,813 | +0,6 pp | spełniony |
| zwycięzca 1. seta | live | −0,0908 [−0,0951; −0,0867] | 12 174 | 0,788 / 0,799 | 0,791 | +1,0 pp | **spełniony** |
| zwycięzca 1. seta | clean | −0,0902 [−0,0947; −0,0861] | 12 180 | 0,788 / 0,797 | 0,790 | +0,9 pp | spełniony |
| zwycięzca 2. seta | live | −0,0902 [−0,0941; −0,0862] | 12 502 | 0,793 / 0,797 | 0,790 | +0,4 pp | **spełniony** |
| zwycięzca 2. seta | clean | −0,0896 [−0,0934; −0,0854] | 12 573 | 0,792 / 0,795 | 0,787 | +0,3 pp | spełniony |
| dokładny wynik w setach | live | −0,1427 [−0,1474; −0,1378] | 4 107 (3,1% wyborów) | 0,786 / 0,802 | 0,789 | +1,5 pp | **spełniony** |
| dokładny wynik w setach | clean | −0,1413 [−0,1459; −0,1364] | 4 064 | 0,786 / 0,804 | 0,792 | +1,9 pp | spełniony |

Sąsiedzi wygrywają też z odczytem analitycznym (sety i.i.d. z p meczu): set 1
−0,0029, set 2 −0,0028, wynik −0,0449 (CI poniżej zera). Kubełki zwycięzcy
1. seta >= 0,70: +1,4 / +0,4 / +1,3 / +1,0 / +0,1 / +0,6 pp; 2. seta: +0,6 /
+0,1 / +0,2 / +0,2 / +1,3 / +0,1 pp; wynik w setach 0,70–1,00: +1,5 pp
(0,60–0,70 +1,7 pp). Wybory >= 0,70 w dokładnym wyniku to 2:0 wyraźnego
faworyta.

W podziale na klasy próg pada tam, gdzie mało meczów: CH-W zwycięzca 1. seta
−3,9 pp (n 268), TOUR-M 1. set −1,1 pp przy n 198, 2. set −1,4 pp n 206,
TOUR-W 2. set −2,1 pp n 468; ITF-M / ITF-W (76% populacji) spełniają próg w
obu setach i w wyniku. Próg zadania liczony jest na rynku łącznie.

**Podpięte** (`TENNIS_SET_MARKETS_FROM_UTC`, `None`): `set1_won_for`,
`set2_won_for`, `set_score`. **Nie podpięte**: zwycięzca 3. seta (Superbet
ma go w „X. set - zwycięzca”; niezmierzony, nierozegrany = zwrot), warianty
„& liczba gemów”, „Zwycięzcy setów”, „1. set/mecz”.

## Co podpięcie robi, a czego nie

- Oba przełączniki `None`: OFFER i SHEET bajt w bajt jak przed zmianą
  (golden `tests/sofa/golden/offer_mappable_off.json`, testy
  `test_football_incident_markets.py`, `test_tennis_set_markets.py`).
- To rynki „rating-only” (`tennis_winner.RATING_ONLY_MARKETS`): bez próbki,
  bez puli, tylko własna krzywa. **Krzywej nie instalowano** – CONFIDENCE
  czyta wyłącznie własne rozliczone linie Superbetu klucza i odmawia
  `NO_LINE_EVIDENCE` do 50 linii / 15 meczów w kubełku. Po włączeniu nic
  się nie drukuje, dopóki linie się nie rozliczą.
- `first_goal` i `set_score` są jednostronne (Superbet nie ma jednego kursu
  dopełnienia), więc marża drabiny nie istnieje – pojedynczo nie drukują się
  także później, bez krzywej historii z n >= 300 i zmiany reguły
  jednostronnych (dziś tylko zawodnicy). Marża całego rynku: „1. gol” 7,3%
  (złoty payload Villarreal – Napoli) do 12,7% (Persepolis, 10-14),
  „Dokładny wynik” tenisa ~17% (Zverev – Bublik i trzy mecze 10-14; powyżej
  15% progu kuponu).
- UNDER czerwonych 0,5 kosztuje 1,07–1,13 (10-14) – blisko `ODDS_TOO_LOW`;
  UNDER karnych 0,5 1,23–1,40.

## Czego nie sprawdzono (podejrzenia, nie fakty)

- Żaden przełącznik nie był włączony na prawdziwym dniu; OFFER sprawdzony na
  złotym payloadzie Villarreal – Napoli / Zverev – Bublik, SETTLE tylko
  offline. Zgodność nazw drużyn w „1. gol” z `matchName` Superbetu poza tym
  jednym meczem niesprawdzona (niezgodność = brak szczebla, nigdy zły).
- Czy Superbet liczy drugą żółtą (`yellowRed`) jako czerwoną kartkę i czy
  karny powtórzony / odwołany przez VAR to „przyznany” – przyjęte,
  niezweryfikowane z regulaminem.
- Kompletność nietrafionych karnych (`inGamePenalty`) w pełnym zapisie
  niezmierzona – jeśli część brakuje, częstość karnych jest zaniżona (UNDER
  wyglądałby lepiej); kalibracja na danych tego samego źródła tego nie
  wykryje.
- Wiersze SHEET dla kartek / karnych dostają rozgrywki bez pełnego zapisu
  (częstość płci) – SETTLE ich linii nie rozliczy (zapis niepełny = brak
  oceny), więc dowód z linii zbierze się tylko z lig z pełnym zapisem.
- Tenis: zwycięzca seta w meczu przerwanym po 1. secie – zwrot przed oceną
  (`settle.REFUND_REASONS`), nie testowane na żywo.

## Odtworzenie

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_football_incidents.py \
    --db data/sofa.db --test-from 2026-06-09 --test-to 2026-10-14 --boot 300 \
    --json-out <dir>/res.json --md-out <dir>/res.md          # ~2 min
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_outcome_model.py \
    --db data/sofa.db --test-from 2026-06-09 --test-to 2026-10-14 --boot 500 \
    --out-dir <dir>                                           # ~5 min
```
