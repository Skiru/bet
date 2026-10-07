# Reguła LINKED: beniaminek nie jest łączony przez nową ligę (2026-10-07)

## Defekt

`football_rating.RatingBook._linked` uznawał parę za `LINKED`, gdy obie
drużyny zagrały ≥3 mecze (`LINK_MIN_MATCHES`) w rozgrywkach będących ligą
(domeną, najczęstszymi rozgrywkami w oknie 365 dni) **którejkolwiek** z nich.
Beniaminek / spadkowicz ma za domenę starą ligę, dopóki w nowej nie zagra
więcej meczów, więc po trzech kolejkach był `LINKED` z nowymi rywalami, a jego
stosunki ataku/obrony ze starej ligi szły 1:1 - bez siły ligi i bez
`CROSS_RATIO_POWER`. Sprzeczne z opisem w kodzie („a promoted side ... is
priced with strength").

Znalezione 10-07 przez analityka hokeja, potwierdzone przez weryfikatora z
`data/sofa.db`: Visby/Roma (HockeyEttan 714 → HockeyAllsvenskan 416), Leksand
(SHL 261 → 416), AZ Havirov (2. liga 28726 → Maxa Liga). Tego dnia 10 nóg
hokejowych zdjęto czytaniem NO_BET. Ta sama książka ratingów zasila model
wyniku hokeja / koszykówki / siatkówki (`score_model`) i SHEET w piłce.

## Poprawka

Para jest `LINKED` tylko wtedy, gdy domeny **obu** drużyn należą do jednych
rozgrywek i obie zagrały w nich ≥3 mecze. Grupy regionalne jednych rozgrywek
(jednostki z `assign_league_units`) nadal się łączą. Każda inna para idzie
przez siłę ligi (`LINKED_BY_STRENGTH`) albo jest `UNLINKED` (w piłce:
`CROSS_LEAGUE_UNLINKED`, CONFIDENCE odmawia). Reguła działa i w prognozie,
i w aktualizacji ratingów (mecze beniaminka uczą teraz siły lig).

Zmienia to, co się drukuje, więc za przełącznikiem. Pierwotnie od 2026-10-08
00:00Z; **operator przesunął go na dzień 10-07** („nic nie postawiłem",
przebuduj dzisiejszy kupon prawidłowo):
`epochs.LINK_SHARED_LEAGUE_FROM_UTC = 2026-10-07 06:45Z`
(`LINK_SHARED_LEAGUE_DATE = 2026-10-07`) - po ostatniej porannej budowie
(05:05Z), przed przebudową. Poranne druki 10-07 sprzed 06:45Z są starą
regułą. Czytany z zegara ściennego (jak `MODEL_FIXES_FROM_UTC` - odtworzenia
refitu z `SOFA_NOW` mają liczyć regułą dnia na żywo); SHEET i
SPORT_CONFIDENCE podają datę budowanego dnia, więc przebudowa dnia sprzed
10-07 zostaje przy starej regule.

Wiersze `05_sheet.json` zbudowane nową regułą niosą `link_rule:
"shared_league"`; `rebuild_plan` puszcza SHEET, gdy reguła budowy jest nowa,
a arkusza stara (wcześniej przebudowa zostawiłaby stary rating piłkarski).

Pliki: `src/bet/sofa/football_rating.py` (`_linked`, `replay`),
`src/bet/sofa/epochs.py`, `src/bet/sofa/score_model.py` (`build_model`),
`scripts/sofa/run_sheet.py`, `scripts/sofa/run_sport_confidence.py`
(`DbForecaster.date`). Testy: `tests/sofa/test_link_shared_league.py` (16),
`tests/sofa/test_football_regional_groups.py` (test grup sparametryzowany
regułą - stara asercja zapisywała właśnie defekt).

## Pomiar (`scripts/sofa/measure_link_rule.py`)

Dwie książki odtwarzane równolegle na tej samej historii, prognoza jeden krok
naprzód przed nauką meczu; MSE na stronę, przedział 95% bootstrap po meczach.
Ujemna różnica = nowa reguła lepsza.

| sport, metryka | okno | populacja | n | MSE stara | MSE nowa | różnica [95%] |
|---|---|---|---|---|---|---|
| piłka, goals_for | 07-01..10-07 | zmienione | 7 317 | 2.4263 | 2.2823 | −0.1440 [−0.1741, −0.1136] |
| piłka, goals_for | 07-01..10-07 | wszystkie | 70 113 | 2.4720 | 2.4573 | −0.0147 [−0.0186, −0.0109] |
| piłka, corners_for | 07-01..10-07 | zmienione | 1 792 | 7.3389 | 7.1529 | −0.1860 [−0.3040, −0.0656] |
| piłka, corners_for | 07-01..10-07 | wszystkie | 16 292 | 7.3582 | 7.3330 | −0.0252 [−0.0402, −0.0089] |
| hokej, wynik regulaminowy | 2025-10-01..2026-10-07 | zmienione | 197 | 3.3021 | 2.8022 | −0.4999 [−0.7084, −0.3062] |
| hokej, wynik regulaminowy | 2025-10-01..2026-10-07 | wszystkie | 13 639 | 3.1544 | 3.1496 | −0.0047 [−0.0081, −0.0014] |

Zmienione mecze w nowej regule: piłka goals_for 6 697 `LINKED_BY_STRENGTH`,
620 `UNLINKED`; hokej 163 / 34.

Brier modelu hokeja na rozliczonych liniach Superbetu 09-20..10-06 (wiersze,
na których dopasowuje się krzywe; 20 879 wierszy, 556 meczów): 0.21411 →
0.21399, −0.00012 [−0.00136, +0.00112]; na 10 585 wierszach, gdzie p się
ruszyło: −0.00024 [−0.00278, +0.00219]. **Bez mierzalnej różnicy** na liniach -
poprawa centrum jest wyraźna, na kalibrowanej skali nie widać jej w 17 dniach.

## Weryfikacja na dniu 10-07 (kopia w scratchpadzie, prawdziwe pliki nietknięte)

Hokej: 5 z 51 par zmienia status (Horacka Slavia – Havirov, Leksands – Nybro,
Almtuna – Visby-Roma, Lorenskog – Gjovik, Vasterviks – Troja-Ljungby), z
`LINKED` na `LINKED_BY_STRENGTH`. SPORT_CONFIDENCE na tych samych danych i
tym samym zegarze (05:04Z): 73 → 66 nóg. Z 10 nóg zdjętych NO_BET:

- 6 przestaje się drukować (Visby-Roma: H −0.5, H −1.5, TT T2 o1.5, total
  o4.5; Leksands – Nybro: H −1.5, TT T2 o1.5);
- 4 drukują się dalej z niższą pewnością: Visby-Roma H −2.5 0.92 → 0.70,
  Leksands – Nybro H −2.5 0.81 → 0.70, TT T2 o0.5 0.93 → 0.89, Havirov TT T2
  o1.5 0.77 → 0.74.

Uwaga: Havirov w notatce z 10-07 miał być `UNLINKED` (siła 2. ligi n=6); w
nowej regule mecze beniaminków uczą siły lig, więc ma ona n ≥ 10 i para jest
`LINKED_BY_STRENGTH`. Inne nogi przesuwają się o kilka pp, bo książki
rozchodzą się na całej historii (np. Lausanne – Lugano TT T1 o1.5 0.77 →
0.80); jedna noga dochodzi (Boro/Vetlanda – Nykopings total o4.5).

Piłka: 20 ze 153 meczów dnia zmienia status (`LINKED` → `LINKED_BY_STRENGTH`),
10 z nich występuje w `11_coupon.json` 10-07 (także wśród zdjętych czytaniem). Sprawdzone ręcznie: zmienione pary z
grupami regionalnymi należą do **różnych** rozgrywek (np. 16990894: −171853 →
196, −171854 → 402) - to nie regresja reguły grup.

## Czego nie sprawdzono

- Krzywe pewności (`sofa_confidence_calibration.json`,
  `sofa_sport_confidence_calibration.json`) dopasowano na starej regule; nowa
  zmienia `p_central` / `forecast_p` na parach przekrojowych. Na liniach
  hokeja różnicy nie widać; piłkarskich wierszy rozliczonych nie
  przeliczano. Następny refit dopasuje krzywe już na nowej regule.
- Koszykówki i siatkówki nie mierzono osobno (koszykówka `NOT_CALIBRATED`).
- `test_chaos_stages.py::test_offer_refused_from_the_first_request_fails_and_keeps_the_file`
  pada też na czystym HEAD 7ee820f8 - niezwiązane z tą zmianą.

## Przebudowa 10-07 na nowej regule (decyzja operatora)

Operator: „nic nie postawiłem, przebuduj dzisiejszy kupon prawidłowo".
Przełącznik przesunięty na 06:45Z (commit b3c7bdd8), `rebuild_day.py`
06:57Z: SHEET przebudowany przez nowy krok planu (24 426 wierszy,
`link_rule=shared_league`), kupon 07:03Z. Odczyty: analityk hokeja (C3
Tappara – Storhamar P1 o0.5 KEEP; Havířov +1.5 WATCH), weryfikator (bez
defektu; WATCH Pavlodar TT o1.5, Boro/Vetlanda TT o2.5). Końcowa przebudowa
07:33Z: 777 nóg, 17 builderów, 19 zdjętych odczytami, 0 odmów zablokowanych
nóg, `audit_variants` 0 znalezisk.

Zostają NO_BET-y z rana na 4 nogach, które w nowej regule przechodzą (Leksand
TT T2 o0.5 0.89, Leksand H −2.5 0.70, Visby H −2.5 0.70, Havířov TT T2 o1.5
0.74) - ich powód (stara reguła) już nie zachodzi; KEEP nie zdejmuje NO_BET,
więc o ich wycofaniu decyduje operator.

**Podejrzenie (niezmierzone, analityk hokeja):** w `RatingBook.update` mecze
beniaminka w nowej lidze uczą siły jego starej ligi, więc siła przekracza
`MIN_STRENGTH_LINKS` dzięki tej samej drużynie, którą potem przenosi (2. Liga:
n 6 → 16, z czego 10 to mecze Havířova; zmierzona siła stawia 3. ligę
nieco wyżej od Maxa ligi). Do pomiaru przed refitem: `MIN_STRENGTH_LINKS`
liczone bez meczów drużyny z ocenianej pary.
