# RESOLVE: kotwica wyszukana (piłka) — pomiar i przełącznik, 2026-10-21

Przełącznik: `epochs.FOOTBALL_SEARCHED_ANCHOR_FROM_UTC` = **2026-10-21 10:00Z**
(operator: „Włączaj od razu!”; 10-21 mieszany — grupa ledgera „10-21 mieszany”,
ta sama co reguły rezerw i pudeł z 09:20Z). Kod: `resolve.searched_anchor_event`,
`resolve.searched_anchor_agreement`, `SofaResolver._searched_anchor`;
pomiar: `scripts/sofa/measure_searched_anchor.py`; test:
`tests/sofa/test_resolve_searched_anchor.py`.

## Problem (klasa F1)

Luki piłkarskie RESOLVE 10-13..10-20, w których żadna strona nie jest
zweryfikowaną encją: 28 pozycji (26 nierozpoczętych, ~3,25 dziennie), gdzie
wyszukana drużyna JEST wśród 3 kandydatów, jej jedyny mecz stoi dokładnie
o godzinie Superbetu, ale nazwa przeciwnika daje 27–81 przy progu 82
(`NAME_MATCH_THRESHOLD`), więc `match_quality` odrzuca. Przykłady: Bunyodkor –
Sogdiyona Jizzax = FC Bunyodkor – FC Sogdiana Jizzakh (74), Vard Haugesund –
Askoy IL = Vard Haugesund – Askøy FK (77), Gabala – Sabah Baku = Qəbələ FK –
Sabah FK. Kotwica dnia K8 (od 10-14) robi to samo tylko dla strony
zweryfikowanej.

## Reguła (ostateczna)

Gdy zwykłe dopasowanie nic nie dało (i nie było niejednoznaczności):

1. **Kandydat**: jeden z dopasowanych wyników wyszukania strony (te same ≤ 3,
   plus drugie wyszukanie rezerw), którego własna nazwa to nazwa strony —
   `part_score` ≥ **90**, ten sam poziom drużyny (`levels_compatible` ze
   znacznikiem) i to samo nieoznaczone słowo składu („2”, „3”, „C”, „D”, „III”).
2. **Mecz**: jedyny mecz piłkarski wszystkich takich kandydatów w ±60 min od
   startu Superbetu (dwa mecze dwóch kandydatów = odmowa), nie przełożony /
   odwołany, płeć tablicy, nie wirtualny, kandydat po stronie wynikającej
   z kolejności Superbetu (F25), druga strona meczu na poziomie przeciwnika.
3. **Przeciwnik** (jedno dodatkowe wyszukanie, tylko po zakotwiczeniu meczu;
   3 dopasowane wyniki + zweryfikowana encja, jeśli jest):
   - **weto**: któryś z nich mocno nazywa przeciwnika (`part_score` > 82, albo
     encja zweryfikowana) i NIE jest drugą stroną meczu → odmowa;
   - `MUTUAL`: któryś z nich jest drugą stroną meczu;
   - `NAME`: `part_score` ≥ **65**;
   - `SHARED_WORD`: wspólne słowo wyróżniające przy zegarach zgodnych do 15 min
     (`shadow_opponent_agrees`).

Mecz dostaje `identity: FUZZY` i nowe pole `Fixture.match_rule =
"SEARCHED_ANCHOR:<MUTUAL|NAME|SHARED_WORD>"`; nazwa nie jest zapisywana jako
zweryfikowany alias; pudło zapisane przed przełącznikiem nie blokuje nazwy
(`get_entity_miss(recorded_after=)`).

## Pomiar 1 — zmostkowane mecze 10-05..10-20 (precyzja)

6 534 mecze piłkarskie z `02_fixtures.json` z wpisem w `01_board.json`;
każda strona po kolei jako „wyszukana” → 13 068 prób. Wyszukania nie ma
w cache, więc kandydaci to: prawdziwa drużyna strony (z meczu zmostkowanego)
**plus każda inna drużyna z listingów w bazie, której nazwa to nazwa strony**
(`part_score` > 82 i `candidate_fits`) — to zaostrza test, nie łagodzi.
Zdarzenia: `sofa_listed_event` + strony `sofa_entity_events` prawdziwych
drużyn, każde w najnowszej pobranej wersji.

| wariant | trafione | **błędne** | odmowa przeciwnika | brak meczu |
|---|---|---|---|---|
| sama kotwica (nazwa przeciwnika ukryta) | 11 645 | 5 | — | 1 418 |
| **reguła z prawdziwym przeciwnikiem** | 8 674 | **0** | 2 976 | 1 418 |

Pięć błędów samej kotwicy — każdy odrzucony przez sprawdzenie przeciwnika:

| strona / przeciwnik Superbetu | zmostkowany | wskazany przez kotwicę | przeciwnik: wynik |
|---|---|---|---|
| CD Santa Cruz / Deportes Temuco 10-10 | 15416339 | 16969961 | nazwa 23 + weto |
| Hapoel Haifa U19 / Hapoel Petah Tikva U19 10-11 | 16893171 (zniknął z indeksu) | 17329555 Maccabi Petach Tikva U19 – Hapoel Haifa U19 | nazwa 73,9 + słowo, **tylko weto** odrzuca (znany przypadek K8) |
| Plymouth Parkway / Yate Town 10-17 | 16587600 (przełożony) | 17273404 Plymouth Parkway – Chertsey Town | nazwa 63,6 (< 65) + weto |
| Aquila / Recanatese 10-18 | 16791044 | 16790693 | nazwa 10 + weto |
| Leatherhead / Welling United 10-20 | 16596346 | 17353943 | nazwa 32 + weto |

„Odmowa przeciwnika” 2 976 to głównie weto na zastępczych kandydatach
(sobowtóry nazw w indeksie) — na tych meczach nic nie zmienia, bo zmostkowało
je zwykłe dopasowanie nazw; pokazuje tylko, że weto jest ostre.

### Przeciwnik podmieniony (scenariusz Kelantan)

Ta sama próba, ale nazwa przeciwnika zastąpiona maks. 3 innymi zmostkowanymi
stronami tego samego turnieju Superbetu i dnia (inaczej tej samej kategorii),
których drużyny nie ma w meczu: 35 008 prób (31 296 turniej, 3 712 kategoria),
29 109 z zakotwiczonym meczem. Każde przyjęcie = zła tożsamość. „Weto” to
zastępcze wyszukanie przynęty: jej prawdziwa drużyna, gdy jej nazwa jest mocna
(> 82), plus sobowtóry — dla 28 224 z 29 109 przynęt weto było dostępne, więc
liczba „z wetem” jest optymistyczna; dla 885 przynęt bez mocnej nazwy reguła
przyjęła 16 (1,8%).

| reguła przeciwnika | prawdziwy przeciwnik | przynęta | ryzyka (Sutton, Kelantan) | F1 (z 25 zakotwiczonych) |
|---|---|---|---|---|
| ≥ 50 lub słowo + weto | 8 727 | 72 | 0/2 | 20 |
| ≥ 50 lub słowo, bez weta | 11 581 | 3 240 | 1/2 | 21 |
| ≥ 60 lub słowo + weto | 8 694 | 23 | 0/2 | 20 |
| **≥ 65 lub słowo + weto (wybrana)** | **8 674** | **16** | **0/2** | **20** |
| ≥ 65 lub słowo, bez weta | 11 515 | 639 | 1/2 | 21 |
| ≥ 70 lub słowo + weto | 8 651 | 12 | 0/2 | 17 |
| ≥ 75 lub słowo + weto | 8 625 | 9 | 0/2 | 14 |
| ≥ 82 lub słowo + weto | 8 582 | 8 | 0/2 | 13 |

Szkic z zadania (≥ 50) był za luźny: losowe nazwy dają 50–57 (`ratio`),
a dwa prawdziwe złe mecze z pomiaru miały 62 (Hannoverscher SC wobec
Karlsruher SC — senior FC St. Pauli za St. Pauli II) i 63,6 (Chertsey Town
wobec Yate Town). Próg własnej nazwy > 82 też był za luźny: Worcester City
za Gloucester City (82,8), Los Angeles FC za LA Galaxy (88,0), SK Slavia Praha
za Slavia Praga C (92,3 — stąd warunek „2 / C”), FC St. Pauli za St. Pauli II
(100 bez znacznika — stąd poziom drużyny). Weto zostało postawione przed
`MUTUAL`: wcześniej 40 przynęt przechodziło przez sobowtóra-drużynę
w meczu („FC Eindhoven” → PSV, „Inter Turku 2” → Inter Turku).

16 przyjętych przynęt (z wetem) to sobowtóry nazw w tym samym turnieju:
CSR Espanol za Deportivo Espanol, Bodrumspor za Bandirmaspor (×2), Dejan FC
za Deltras Sidoarjo (×2), Serik / Etimesgut Belediyespor za inne
„Belediyespor”, U Cluj za CFR Cluj, Negele Arsi Ketema za Halaba / Sheger
Ketema (×2), Creteil Lusitanos za Lusitanos Saint-Maur, Sky Leader FC za
Leaper FC, Olympique Marsylia za Olympique Marsylia (K) i za Olympique Lyon,
PAC Omonia 29M za Omonia Aradippou, Al Draih za Al Qadsiah.

## Pomiar 2 — 28 pozycji F1 i ryzyka (prawdziwe wyszukania)

Na wynikach żywego wyszukania z 2026-10-21 (powtórka luk RESOLVE,
`replay.jsonl`, wraz z listingami kandydatów):

- **rozpoznane 20 z 28**: IDV (K) – Belgrano (K), Bunyodkor, Newroz – Al Minaa,
  Heroes de Zaci FC II, Dalian Yingbo, Ujpest (K) – ETO Gyor (K) (MUTUAL),
  Silifke – Karakopru, FSV Luckenwalde – CZ Jena, Mighty Wanderers, Vard
  Haugesund, Inker Zapresic, Nejmeh – Istiklol, Dinamo Samarqand, Village
  Superstars, Olympique Beja, US Monastir, Setubal – UD Serra, Oman FC – Bahla,
  Gas Alshimal – Al Zawraa, Belgrano (K) – Palmeiras (K); każdy wskazany mecz
  to ten z klasyfikacji luki;
- **nierozpoznane 8**: Gabala (`normalize_name` składa „Qəbələ” do „qbl”,
  własna nazwa 33), Jonava – BFA Vilnius (27), WKS (K) – DR Konga (K) (0),
  AD Pemba – UD do Songo (własna nazwa 84 < 90), UST FC (weto: FC Uster 86),
  Videoton U19 (weto: osobna encja „Videoton FC Fehérvár U19”), Astra (K) –
  Mol Vidi (K) (36), Levante (K) (mecz przełożony);
- **ryzyka odrzucone 4/4**: Sutton Coldfield Town – WBA U21 (Sutton United –
  WBA U21; weto: Sutton Coldfield Town #139 — bez weta przeszłoby przez wspólne
  „sutton”), Kelantan Red Warrior – Imigresen (mecz z Star City FC; nazwa 42
  i weto), Karvan Yevlakh – Cebrayil (własna nazwa 80; mecz z Gəncəbasar FK),
  Asteras Tripolis (K) – Odysseas Glyfadas (K) (Odysseas Moschatou, własna
  nazwa 64).

Oczekiwany zysk: ~20/28 z ~3,25 dziennie ≈ 2,3 meczu dziennie (FUZZY).

## Czego nie zmierzono

- Ranking żywego wyszukania na zbiorze zmostkowanym (wyszukanie nie jest
  w cache) — zastąpiony prawdziwą drużyną + sobowtórami z indeksu listingów;
  weto na przynętach — zastąpione tak samo (optymistycznie).
- Mecz przełożony poza okno i nigdy nierozegrany nie jest w indeksie, więc
  test nie widzi wyboru, który na żywo odrzuciłby filtr NOT_AS_SCHEDULED.
- Żadnego przebiegu RESOLVE na żywo z włączonym przełącznikiem; koszt jednego
  wyszukania przeciwnika na zakotwiczony mecz nie był liczony.
- Pozycje F1 to 28 z 8 dni; reguła była strojona na zbiorze zmostkowanym
  i przynętach, nie na nich (odrzucony szkic ≥ 50 dawał na F1 tyle samo).

Polecenie pomiaru:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_searched_anchor.py \
    --from 2026-10-05 --to 2026-10-20 [--json-out f] \
    [--gap-diag replay.jsonl --gap-classes final2.json]
```
