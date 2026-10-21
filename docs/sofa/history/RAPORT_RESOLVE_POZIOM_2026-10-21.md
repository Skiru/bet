# RESOLVE — jedna drużyna, dwie nazwy poziomu (F2), 2026-10-21

Przełącznik: `epochs.FOOTBALL_SQUAD_LEVEL_ALIAS_FROM_UTC` = **2026-10-21 10:30Z** (operator: „Włączaj od razu!”; 10-21 mieszany, grupa ledgera „10-21 mieszany”).
Zbudowane, zmierzone, przetestowane; włączenie zmienia to, co się drukuje
(dochodzą mecze), więc czeka na zgodę operatora (domyślnie od 00:00Z
następnego dnia, nowa grupa księgi).

## Problem

Z 127 zgubionych pozycji piłki 10-13..10-20, w których żadna strona nie była
znana, 23 to klasa F2: Superbet i Sofascore piszą poziom tej samej drużyny
inaczej, a bramka poziomu (`names.levels_compatible`) odrzucała parę.

| wzór | przykład Superbet | przykład Sofascore | pozycji |
|---|---|---|---|
| rocznik o rok | Cosenza U19 · Frosinone U19 | Cosenza U20 – Frosinone U20 | 14 (Primavera 2) |
| rezerwy = młodzież | CD Fas (R) · CD Platense (R) | CD FAS U20 – C.D. Platense Zacatecoluca U20 | 4 (Salwador, Peru, Indie) |
| rezerwy = U23 | Leuven B · KRC Harelbeke | OH Leuven Banqup Academy U23 – Racing Club Harelbeke | 2 (Belgia) |
| końcowe „2” | Houston Dynamo II · Los Angeles FC II | Houston Dynamo 2 – Los Angeles FC 2 | 2 (MLS Next Pro) |
| rezerwy = pierwsza drużyna | Mechelen B · Zulte Waregem B | Yellow Red K.V. Mechelen – S.V. Zulte-Waregem B | 1 |

Końcowe „2” to u Sofascore zawsze druga drużyna klubu: 211 takich nazw piłkarskich
10-02..10-23 (Norwegia, Szwajcaria, Francja, Białoruś, Dania, MLS) — żadna nie jest
pierwszą drużyną. `normalize_name` go nie oznacza, więc „II” przeciw „2” czytało
się jak rezerwy przeciw seniorom.

## Reguła

Ostatnia próba w `SofaResolver.resolve_entity` (po zwykłym dopasowaniu i po
kotwicy wyszukanej — mecz, który one mostkują, nigdy się nie zmienia), tylko
piłka, tylko RESOLVE (`record_miss`):

1. kandydaci: listingi już przeczytane plus do 3 wyników wyszukania (zwykłego
   i drugiego, rezerwowego), których poziom może nazywać poziom strony
   (`resolve.squad_alias_candidate`: ten sam klub po nazwie bez słów poziomu
   `part_score` > 82, płeć tablicy, nie symulacja) — to „Cosenza U20” dla
   „Cosenza U19”, którego `candidate_fits` nie wpuszcza;
2. **jedyny** mecz w ±60 min od startu Superbetu, w którym:
   - strona wyszukana to kandydat, a jej nazwa bez słów poziomu
     (`resolve.level_free_name`) ma `part_score` ≥ 90 (`SQUAD_ALIAS_OWN_SCORE`;
     82 przepuszczało „CA Independiente” za „Independiente Rivadavia”, 89,7);
   - przeciwnik tak samo, `part_score` > 82;
   - poziomy: jedno przesunięcie wspólne dla pary (`resolve.squad_level_shift`):
     ten sam poziom niesenioralny, roczniki o rok (U19↔U20), rezerwy ↔ U19..U23,
     końcowe „2” = rezerwy (`resolve.football_squad_levels` — tylko tutaj;
     `team_levels`, klucze cache, `MATCH_LOGIC_VERSION` bez zmian). Gdy obie
     strony tablicy są niesenioralne, ta sama para (poziom Superbetu, poziom
     Sofascore) musi pasować po obu stronach; strona senioralna musi być
     senioralna u Sofascore. **Nigdy** seniorzy ↔ rezerwy, seniorzy ↔ młodzież;
   - kolejność Superbetu (F25), płeć tablicy, nie przełożony, nie symulacja;
   - dwa takie mecze = odmowa;
3. **weto**: drużyna, którą nazywa własne wyszukanie przeciwnika (3 pasujące
   wyniki albo jego zweryfikowana encja) i która nie jest w meczu, gra w ±60 min
   INNY mecz (`resolve.squad_alias_veto`). Sobowtór bez meczu w tym czasie
   („Vicenza U19” obok L.R. Vicenza U20) nie wetuje. Koszt: jedno wyszukanie i do
   3 listingów, tylko gdy mecz już znaleziono.

Mecz: `identity: FUZZY`, `match_rule: "SQUAD_LEVEL_ALIAS:<Superbet>-><Sofascore>"`
(np. `U19->U20`), nazwa nie trafia do cache jako zweryfikowana; pudło zapisane
przed przełącznikiem nazwy nie blokuje.

## Pomiar precyzji

`scripts/sofa/measure_squad_level_alias.py` (tylko odczyt; baza w trybie ro), wszystkie
zmostkowane mecze piłki RESOLVE 10-05..10-20 (6 534; 622 z obiema stronami
młodzieżowymi / rezerwowymi, 390 z jedną), każda strona po kolei jako wyszukana.
Kandydaci = prawdziwa drużyna (gdy RESOLVE mógłby ją mieć) plus **każda** drużyna
z listingów bazy, którą alias by wziął — czyli inne roczniki i rezerwy tego
samego klubu (właśnie kolizja, której reguła musi odmówić). Weto: wyszukanie
przeciwnika zastąpione jego prawdziwą drużyną i jej sobowtórami.

| populacja | trafne | BŁĘDNE | odmowa | weto (trafny mecz) | weto (błędny) |
|---|---|---|---|---|---|
| tablica bez zmian | 1 698 | **0** | 11 285 | 85 | 0 |
| poziom tablicy przesunięty po obu stronach (każdy alias) | 3 429 | **0** | 351 | 110 | 0 |
| jedna strona niesenioralna przesunięta, druga senioralna | 2 509 | **0** | 347 | 32 | 0 |
| przesunięta tylko jedna z dwóch stron (musi odmówić) | 0 | **0** | 7 780 | 0 | 0 |
| przeciwnik-wabik (inna strona tego turnieju i dnia) | — | **10** | 9 009 | — | 3 |
| zwykła bramka nazw, te same wabiki, tablica bez zmian | — | 20 | 2 828 | — | — |

„Odmowa” w wierszu „bez zmian” to głównie mecze seniorów (reguła ich nie dotyka).
Z prawdziwym przeciwnikiem: **0 błędnych wyborów**.

Wabiki: 10 przyjęć to 3 mecze (każdy na kilku poziomach): FC Winterthur –
„Zurich” przeciw Grasshopper Club Zürich U19, Cap d'Ail – „Cavigal Nice SF”
przeciw Nice U19, EB/Streymur – „B36 Tórshavn” przeciw HB Tórshavn II. Za każdym
razem nazwa wabika jest podzbiorem słów innego klubu — ta sama słabość, którą ma
zwykła bramka nazw (82 na `name_score`): ona na tych samych wabikach przyjmuje
20 z 2 848 (0,70%), alias 10 z 9 022 (0,11%). Wabik to sytuacja sztuczna
(Superbet musiałby wystawić mecz z innym przeciwnikiem w tej samej godzinie,
a Sofascore nie mieć go wcale).

## Odzysk na 23 pozycjach F2

Wyniki wyszukania z powtórki na żywo 2026-10-21 (`gap/replay.jsonl`), RESOLVE
pyta stronę A, potem B; wybór porównany z meczem wskazanym w klasyfikacji.

| wynik | pozycji | które |
|---|---|---|
| rozpoznane trafnie | **18** | 12 × Primavera 2 (U19->U20), Kenkre – Iron Born (R->U19), Inter Formando – Municipal Limeño, CD Fas – CD Platense, Cacahuatique – Alianza (R->U20), Portland Timbers II – St. Louis City II, Houston Dynamo II – Los Angeles FC II (R->R, „2”) |
| błędne | **0** | — |
| odrzucone | 5 | Pisa U19 – Ascoli U19 (Sofascore: Pisa U19 – Ascoli U20) i Modena U19 – Cremonese U20 (Sofascore: obie U20) — poziom różny po jednej stronie, zgodność pary; Mechelen B (Sofascore nazywa ją jak pierwszą drużynę — nigdy); Union SG B (wyszukanie bez kandydata); Leuven B – KRC Harelbeke (przeciwnik „Racing Club Harelbeke” 81,8) |

Weto nie zadziałało na żadnej z 23 pozycji.

Wariant **luźny** (każda strona aliasem osobno, bez zgodności pary) zmierzony
obok: 20 z 23 (dochodzą Pisa i Modena), z prawdziwym przeciwnikiem także 0
błędnych (połowiczne przesunięcia przyjmowane trafnie: 6 802), wabiki te same 10.
**Nie wdrożony** — zgodnie z poleceniem reguła wymaga zgodności pary; to decyzja
operatora.

## Czego nie sprawdzono

- Ranking wyszukiwania Sofascore na zbiorze zmostkowanym (wyszukanie nie jest
  w cache): kandydaci zastąpieni drużynami z listingów bazy; odzysk na F2 liczony
  na prawdziwych wynikach wyszukania z powtórki 10-21 (bez nowych zapytań przez
  most).
- Listingi w powtórce F2 to tylko mecze blisko startu (`near`); weto widzi tylko je.
- Koszt na pełnym dniu (dodatkowe listingi kandydatów-aliasów i wyszukanie
  przeciwnika) — nie mierzony; płaci się tylko za strony niesenioralne, których
  nic innego nie dopasowało.
- Powtórka RESOLVE na kopii bazy z włączonym przełącznikiem — nie wykonana.

## Testy i bramki

`tests/sofa/test_resolve_squad_level_alias.py` (10 testów: poziomy, aliasy,
zgodność pary, Primavera, MLS „2”, odmowy F25 / okno / przełożony / dwa roczniki,
nazwa własna ≥ 90, weto, filtr kandydata, przełącznik on/off w `resolve_entity`
z `match_rule` i bez zapisu do cache, pudło sprzed przełącznika).
`test_resolve_golden`, `test_resolve_club_affixes`, `test_resolve_squad_search`,
`test_resolve_searched_anchor` bez zmian, zielone.

## Wariant bez zgodności pary — włączony 2026-10-21 11:30Z

Operator: „Włącz!” (po pytaniu o wariant luźny). Przełącznik
`epochs.FOOTBALL_SQUAD_LEVEL_ALIAS_LOOSE_FROM_UTC` = 2026-10-21 11:30Z
(10-21 mieszany, grupa „10-21 mieszany”): `resolve.squad_level_shift(...,
loose=True)` pozwala każdej z dwóch stron niesenioralnych przesunąć poziom
osobno. Pomiar `measure_squad_level_alias.py --loose` (ten sam zbiór): z
prawdziwym przeciwnikiem 0 błędnych wyborów, wabiki te same 10 z 9 022; F2
20 z 23 (dochodzą Pisa U19 – Ascoli U19 i Modena U19 – Cremonese U20). Test:
`test_the_loose_shift_lets_each_side_shift_alone`.
