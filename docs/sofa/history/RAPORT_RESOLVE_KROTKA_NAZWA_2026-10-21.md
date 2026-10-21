# RESOLVE: wyszukanie krótką nazwą (piłka) — pomiar i przełącznik, 2026-10-21

Przełącznik: `epochs.FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC` = **2026-10-21 11:00Z**
(operator: „Włączaj od razu!”; 10-21 mieszany, grupa ledgera „10-21 mieszany”). Kod:
`src/bet/sofa/short_name_search.py` (`short_name_queries`,
`short_candidate_fits`, `name_contradicts`, `short_name_pair_event`,
`named_elsewhere`, `resolve_short_name_pair`), wywołanie w
`scripts/sofa/run_resolve.py::_resolve_one` (więc także w późnym przejściu
RESOLVE), pamięć kandydatów zwykłego wyszukania w
`SofaResolver.searched_listings`. Pomiar:
`scripts/sofa/measure_short_name_search.py`; test:
`tests/sofa/test_resolve_short_name.py`. `MATCH_LOGIC_VERSION` bez zmian.

## Problem (klasa F3)

Luki piłkarskie RESOLVE 10-13..10-20, w których żadna strona nie jest znana:
22 pozycje, w których wyszukiwarka Sofascore nie zwraca nic pasującego dla
pełnej nazwy Superbetu, a jedno słowo nazwy znajduje drużynę (klasyfikacja
2026-10-21, `T:FOUND_BY_TOKEN_SEARCH`: 11 „mutual” — obie strony znajdują ten
sam mecz — i 11 „one side”). Przykłady: „Calcio Avola 1949” → „avola” (Avola),
„Menemenspor” → „menemen” (Menemen FK), „Muang Loei Utd” → „loei” (Muang Loei
United), „SV Wallern” → „wallern” (SPG Wallern/ASV St Marienkirchen).

## Reguła (ostateczna)

Tylko piłka i tylko gdy obie strony przepadły: zwykłe wyszukanie, ponowienie
rezerw i kotwica wyszukana nic nie dały (i nie było niejednoznaczności).

1. **Zapytania**: dla każdej strony jej dwa najdłuższe słowa (≥ 4 litery, bez
   cyfr, bez słów z `resolve.name_stopwords()` i słów klubowych —
   `calcio`, `polisportiva`, `sportunion`, `football`, `kulubu`…); słowo
   „…spor” dłuższe niż 8 liter także bez „spor”; nigdy zapytanie zwykłe.
2. **Kandydat z krótkiego zapytania** (do 5 pasujących wyników): drużyna
   piłkarska płci i poziomu strony (`candidate_fits`), z zapytaniem jako
   **całym słowem** nazwy, z tymi samymi nieoznaczonymi słowami składu („2”,
   „3”, „C”… także „Polissya-2”, nigdy inicjał „A.S.D.”), a zapytanie nie jest
   słowem drugiej strony tablicy („Linz” nie wskazuje żadnego z dwóch klubów z
   Linzu).
3. **Kandydaci strony**: zweryfikowana encja (wtedy tylko ona), inaczej
   kandydaci zwykłego wyszukania (zapamiętani przez `resolve_entity`) plus
   krótkie.
4. **Mecz**: gospodarz w kandydatach strony A, gość w kandydatach strony B
   (kolejność Superbetu, F25), ±60 min od startu Superbetu, płeć tablicy, nie
   przełożony / odwołany / przerwany, nie symulacja, poziomy obu stron, te same
   słowa składu, żadna nazwa nie jest **sprzeczna** (`name_contradicts`: KAŻDA z
   dwóch nazw ma słowo ≥ 4 liter, którego druga nie ma — Cheltenham Town /
   Swindon Town, Real Madryt B / Atletico Madrid B, Nomme Kalju / Nomme United;
   słowo dodane tylko po jednej stronie, jak „Calcio Avola 1949” / „Avola”, nie
   jest sprzecznością); **jedyny** taki mecz; co najmniej jedna strona przyszła
   z krótkiego zapytania.
5. **Weto** (`named_elsewhere`): kandydat strony o jej własnej nazwie
   (`part_score` > 82, ten sam poziom i słowa składu), którego nie ma w meczu,
   gra w tym oknie INNY mecz — Sofascore zna drużynę z tablicy i jest ona
   gdzie indziej (Dundee FC obok Dundee United).

Nigdy z jednej strony. Mecz: `identity: FUZZY` (wymuszone, nawet gdy nazwa
przeciwnika dałaby ≥ 95), `match_rule: "SHORT_NAME:<BOTH|A|B>"` (która strona
przyszła z krótkiego zapytania). Nic nie trafia do cache jako zweryfikowane.
Para bez wyniku zapisuje pudło `(short) <a> v <b>` na swój dzień (późne
przejście pyta ponownie po swojej świeżości, jak przy pudle encji).

## Pomiar 1 — zmostkowane mecze 10-05..10-20 (precyzja)

6 534 mecze piłki zmostkowane przez RESOLVE (02_fixtures.json z wpisem
01_board.json). Wyszukanie nie jest w cache, więc wyniki krótkiego zapytania
zastępuje **każda** drużyna z listingów w bazie, którą reguła przyjmuje
(nadzbiór 5 wyników wyszukiwarki — więcej podszywających się, nigdy mniej),
zwykłe wyszukanie — prawdziwa drużyna.

| wariant | dobrze | źle | brak |
|---|---|---|---|
| prawdziwa para (prawdziwe drużyny + krótkie) | 5 193 | **0** | 531 (+810 bez strony krótkiej) |
| tylko krótkie zapytania | 3 339 | **0** | 3 195 |
| ukryta prawdziwa drużyna strony A | — | **0** | 6 534 |
| ukryta prawdziwa drużyna strony B | — | **0** | 6 534 |
| ukryte obie | — | **0** | 6 534 |
| przeciwnik podmieniony (do 3 innych zmostkowanych stron tego samego turnieju i dnia) | — | 17 z 17 504 | 17 487 |

Przyjęte podmiany (każda to błędna tożsamość): CSR Espanol / Deportivo
Español, Kuwait SC / Al Arabi SC Kuwait, Zurich U19 / Grasshopper Club Zürich
U19, Cercle Brugge / Club Brugge KV, HB Torshavn / B36 Tórshavn, U Cluj / CFR
1907 Cluj, USM Alger / MC Alger, LSK Kvinner / SK Brann Kvinner, Dundee FC /
Dundee United, VfB Lubeck / Phönix Lübeck, Hong Kong Rangers / Hong Kong FC,
Inter i Atletic Escaldes / SC Escaldes, Agia Paraskevi (inny mecz NPS Volos w
oknie), AEK Ateny (inny mecz AE Kifisia w oknie), Cavigal Nice U19 / Nice U19,
Inter Mediolan (K) / Milan. Wzór: nazwa z tablicy to miasto + skrót krótszy niż
4 litery („HB”, „MC”, „U”) albo słowo ogólne — nazwa Sofascore niczego jej nie
przeczy. To scenariusz celowo ostrzejszy niż produkcja: prawdziwa drużyna
strony A jest zawsze kandydatem, a przeciwnik z tablicy jest kimś innym niż
drużyna w meczu (kotwica wyszukana: 16 z 29 109 w tym samym teście).

Bez sprawdzenia sprzeczności i weta ta sama reguła przyjmowała 266 podmian,
21 meczów z ukrytą prawdziwą drużyną (Real Bedford → Bedford Town – Biggleswade
Town, Plymouth Argyle ↔ Plymouth Parkway, Unia Solec ↔ Unia Swarzędz, Austria
Salzburg → FV Austria XIII – FC 1980 Wien) i 1 błąd z prawdziwą parą (Hapoel
Petah Tikva U19 → Maccabi Petach Tikva U19). Samo sprawdzenie sprzeczności:
0 / 0 i 34 podmiany; weto: 17.

## Pomiar 2 — 22 pozycje F3 (prawdziwe wyszukania)

`_resolve_one` z przełącznikiem włączonym (oraz ponowieniem rezerw, kotwicą
wyszukaną i pudłami na dzień), pudła encji skasowane, na **kopii** bazy
(nigdy `data/sofa.db`), przez most, pozycja po pozycji.

| wynik | pozycje |
|---|---|
| **dobrze** (`SHORT_NAME:BOTH`, FUZZY) | 8: Nakhon Ratchasima – Muang Loei, SV Wallern – Vortuna Bad Leonfelden, Muang Loei – SGB Kanchanaburi, LASK (K) – Kleinmünchen (K), Menemenspor – Güzide Gebze, Probiy – Polissya-2, Avola – Sambiase, Londerzeel – Diksmuide |
| **źle** | **0** |
| odrzucone tylko przez status z perspektywy czasu | 1: Modica – Athletic Club Palermo (mecz dziś „interrupted”; ze statusem „notstarted” reguła go wybiera — sprawdzone na listingach kopii) |
| jednostronne (z założenia) | 10 z 11 „one side”: Khankendi, Shamakhi, Edelweiss Linz, RWDM U21, Bolivar (K), Sportunion Mauer, Biblioteca Atenas, Sirina Grevenon (K), Pattaya, Standard Liege U23 — druga strona nie znajduje drużyny żadnym słowem (Xankəndi, Şamaxı, Khon Kaen, LAC IC = Landstraßer AC Inter); Londerzeel przeszło mimo klasy „one side” |
| poza zakresem | Avellino U19 – Catanzaro U19 (Sofascore: U20 — poziom, zadanie F2); MEG & Centre – Real Bengaluru (dwa zdarzenia tego meczu w Sofascore = dwa mecze, odmowa); Taipei Xiongzan (K) – Hang Yuan (K) (Sofascore „Taipei Bravo!”: sprzeczność nazw) |

## Koszt

Krótkie wyszukania: średnio **2,5 na zgubioną parę** (F3; na zmostkowanych
parach 2,2). Zgubionych wpisów piłki dziennie 10-05..10-20: średnio ~30
(2–123; 10-13..10-20 ~21) — górna granica, bo obejmuje mecze rozpoczęte i
niejednoznaczne. Razem **~75 wyszukań dziennie** (10-10: ~300) plus do 5
listingów na zapytanie (w większości z cache encji; na kopii F3 1,8 żądania
listingu na parę, ale kopia miała listingi z wcześniejszych prób — nie jest to
pomiar zimnego cache). Każde późne przejście może zapytać ponownie po 30 min.

## Czego nie zmierzono

- Ranking wyszukiwarki na zmostkowanych meczach (wyszukanie nie jest w cache):
  precyzję mierzono na nadzbiorze z listingów, nie na prawdziwych 5 wynikach.
- Świat podszywających się to drużyny z listingów w bazie (dni i strony
  zmostkowanych drużyn); drużyna, której listingu nie ma w bazie, nie mogła się
  podszyć.
- Koszt listingów przy zimnym cache; liczba późnych przejść dziennie.
- Brak pomiaru na meczach przyszłych (F3 to mecze 10-13..10-18 odtworzone po
  fakcie; statusy z perspektywy czasu).
