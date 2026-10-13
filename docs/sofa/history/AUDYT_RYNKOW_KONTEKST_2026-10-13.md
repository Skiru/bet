# Audyt rynków: kontekst, matchup i braki modeli — wszystkie sporty (2026-10-13)

Stan: **po dwóch rundach weryfikacji** (runda 1: 55 uwag - 1 bloker, 13 poważnych, 41 drobnych; runda 2: 39 uwag - 8 poważnych, 31 drobnych; wszystkie naniesione, wyjątki w dzienniku). Dokument jest wejściem do naprawy
modeli. Niczego nie zmienia w tym, co drukuje kupon. Każda pozycja przed wdrożeniem
przechodzi ścieżkę z CLAUDE.md "Changing the pipeline": pomiar poza próbą na historii,
przełącznik w `bet.sofa.epochs` od następnego dnia 00:00Z, zgoda operatora. Refity
wykonujemy na kopii bazy.

## Decyzje operatora (2026-10-13, po audycie)

Ta sekcja ma pierwszeństwo przed „Do operatora” w dzienniku. Wpisano ją także do
CLAUDE.md („Changing the pipeline” 4, wyjątek od twardej reguły o refitach).

| # | temat | decyzja |
|---|---|---|
| O1 | A2: rozgrywki bez własnej stawki (NBA Preseason itd.) | **Odmowa tą samą regułą co `FRIENDLY_FIXTURE` w piłce**; rozgrywki bez stawki dostają `NO_LEAGUE_RATE`. Bez fallbacku do ligi macierzystej |
| O2 | A7: pozycja linii w krzywych koszykówki i hokeja | **Tak.** Historyczne kursy (Sofascore) wyznaczają tylko **pozycję** linii historii; p dalej wyłącznie ze statystyk. To nie jest „blend the price” |
| O3 | Siatkówka: rynki setowe (decyzja z 10-07) | **Wracają po B9** (model długości seta) i pomiarze poza próbą, przez przełącznik |
| O4 | Pozycje nakładające się na „Measured and declined” (B2 K=40, B3, B4, B6, B7, C17) | **Ponowny pomiar dozwolony, jeśli oś jest nowa.** Każdy test zarejestrowany z góry: metryka, próg i okno zapisane przed uruchomieniem |
| O5 | Przełączniki w `epochs` | **Sesja implementująca włącza je sama**, gdy pomiar poza próbą jest lepszy z przedziałem nieobejmującym zera, `tests/sofa` przechodzą i raport jest napisany. Inaczej przełącznik zostaje `None` |
| O6 | Refity (piłka + tenis z replayem ratingu, koszykówka) | **Instalacja automatyczna**, gdy compare pokazuje poprawę i testy przechodzą, **także w dzień już zbudowany**: przełącznik z dokładnym czasem UTC, dzień mieszany i tak opisany, wydrukowane nogi zablokowane, nowa epoka w ledgerze |
| O7 | Zakres | **Całość, etapami według „Kolejność proponowana”**; commit po każdym etapie, raport w `docs/sofa/history/` |
| O8 | Bridge | **Wolno bez ograniczeń** (backfill kursów pod A7, `/event` pod sędziów C15, h2h z dłuższego okna). Twarde reguły bridge'a bez zmian: `MIN_INTERVAL_MS` nietykalne, `SOFA_MAX_CONCURRENCY` = liczba okien, przerwa przy 403 |
| O9 | CLAUDE.md: zdanie o replayu | Poprawione 2026-10-13: replay nie odtwarza ratingu piłki ani priorów tenisa (A6) |

**Skąd ten audyt.** Operator zapytał, gdzie model uwzględnia, jak dwie drużyny
oddziałują na siebie: styl (defensywny / ofensywny), h2h i dawne potyczki. Pytanie
padło na przykładzie `corners_total` z ACL Elite 2026-10-13. Odpowiedź z kodu:
- `corners_total` nie ma ratingu atak × obrona (`football_rating.UNRATED_MARKETS`);
- h2h trafia do próbki tylko przypadkiem i bez wagi (`samples.py:970`);
- styl i odwrócenie ról widzi wyłącznie analityk, a ten może nogę tylko zdjąć.

Operator poprosił o przegląd rynek po rynku we wszystkich sportach.

**Metoda.** Sześciu audytorów pracowało tylko na odczycie. Mieli ten sam brief:
miejsce obliczeń (plik:linia), wejścia, braki z dowodem, rozwiązanie z literatury,
sposób pomiaru i kolizję z listą "Measured and declined". Obszary:

| obszar | raport |
|---|---|
| piłka: rynki liczbowe (gole, rożne, kartki, faule, strzały, celne, spalone, obrony, połowy) | część 1 |
| piłka: rynki łączne (`both_over_*`, `most_*`, `handicap_*`), propsy zawodników, rynki wyniku | część 2 |
| tenis: wszystkie rynki | część 3 |
| hokej i koszykówka | część 4 |
| siatkówka i CS2 | część 5 |
| warstwy wspólne (SAMPLES, środek SHEET, siła ligi, krzywe, line evidence, flagi, analityk) + macierz sport × kontekst | część 6 |

**Jak czytać liczby.**
- **[zmierzone]**: policzone przez audytora na artefaktach, bazie lub historii.
- **[podejrzenie]**: wniosek bez pomiaru.
- Liczby z 4–6 ostatnich dni mają charakter diagnostyczny. Żadna nie jest dowodem do
  zmiany druku, bo każda zmiana wymaga pomiaru poza próbą na historii.
- Wszystkie zaproponowane rozwiązania są **niezmierzone**.

## Lista napraw (skonsolidowana)

Kolumna „wpływ na druk”:
- **tak** — zmiana idzie przez przełącznik w `epochs`, pomiar i zgodę operatora;
- **poprawka** — korekta poprawności; wchodzi od razu z testem, chyba że zmienia druk
  (wtedy też potrzebny jest przełącznik);
- **tak (przez przełącznik)** — w tabelach B, C, D: pozycja zmienia p, bramki albo dodaje rynki, więc zmienia druk dopiero po pomiarze, przełączniku i zgodzie operatora;
- **nie** — sam pomiar albo zmiana struktury danych bez wpływu na p.

Priorytet P1/P2/P3, nakład S/M/L.

### A. Defekty (błędy poprawności lub reguły, która działa wbrew intencji)

| id | sport / rynek | defekt | miejsce w kodzie | rozwiązanie | wpływ na druk | prio |
|---|---|---|---|---|---|---|
| A1 | piłka, wszystko z ratingiem | Podział sezonu na grupy regionalne tworzy nowe jednostki ligi ze startową siłą 0. J1 2026 → -171852 / -171853: siła 0,168 / 0,108 wobec 0,419 całej J1; V-League ma 0,243. Skutek: Công An 2,10 – Kashima 0,97 goli (z siłą 196: 1,63 – 1,24) oraz Kyoto 1,32 – Ratchaburi 1,39 (z siłą 196: 1,80 – 1,02), oba 2026-10-13 | `football_rating.py:452` `assign_league_units`; `:755-768` `_link` | Jednostka regionalna startuje z siłą rodzica (`unit_competition`), nie z 0, albo siła zawsze per rozgrywka (jednostki tylko do reguły LINKED). Reguła „n < MIN_STRENGTH_LINKS” nie wystarczy: jednostki J1 mają n=34/35 przy progu 10 | tak (siła ligi zmienia centra) | P1/S |
| A2 | koszykówka, hokej, siatkówka (score model); piłka w ratingu (ACL 10-13: 17 meczów, stawka globalna); też puchary / nowe rozgrywki; w cache 7 przedsezonów kosza (NBA, CBA, ABA, WNBA, …) | Rozgrywki z < `MIN_LEAGUE_MATCHES` (30) meczami dostają średnią **wszystkich lig**. NBA Preseason (wyłączone z historii jako sparing): 82,8 pkt na stronę zamiast 118/112. Noga 10-10 Raptors–Clippers UNDER 222.5 miała `forecast_p` 0,9998 | `football_rating.py:770-779` `league_rates`; `score_model.py:96-100` `_is_friendly`; brak bramki w `run_sport_confidence.py` | Sparing / przedsezon: odmowa w SPORT_CONFIDENCE tą samą regułą `comparability.is_friendly_event`, co `FRIENDLY_FIXTURE` w piłce (`run_confidence.py:651-654`). Inne rozgrywki z n < 30: `NO_LEAGUE_RATE` albo fallback tylko do ligi tej samej klasy (Część 4 (a)). Test na NBA Preseason | poprawka + przełącznik | P1/S |
| A3 | koszykówka NBA, dogrywka | Dogrywka skalowana jako 5/10 kwarty zamiast 5/12 | `score_model.py:468` | Długość dogrywki z formatu ligi (`defaultPeriodLength` z `/event` albo stała per liga); razem z C8 (ta sama ścieżka `_basketball`, jeden pomiar holdout DRAW) | poprawka + przełącznik (+ refit krzywej koszykówki) | P2/S |
| A4 | piłka, rynki pochodne (`both_over_*`, `most_*`, `handicap_*`) | Wilson z własnych linii klucza jest dzielony przez efekt projektu **całego sportu** (2,437), choć w kubełkach klucza od p 0,60 każdy mecz daje jedną linię. `both_over_corners` OVER p 0,75-0,80: zrealizowane 66/78 = 0,846, odczyt 0,6825. Na 10-07..10-13 zero nóg pochodnych na kuponie | `line_evidence.py:300-312`, `:437-440`; `run_confidence.py:697-698` | Efekt projektu liczony per kubełek tą samą funkcją `design_effect` na liniach kubełka (gdzie games == n wychodzi 1) | tak; dotyczy każdego klucza bez krzywej we wszystkich sportach (kosz, CS2, siatkówka), pomiar walk-forward na wszystkich | P1/S |
| A5 | piłka (MODEL_ABOVE_OWN_SAMPLE, bez propsów); piłka i tenis (bramki kształtu) | `MODEL_ABOVE_OWN_SAMPLE` i bramki kształtu (`MODE_LOSES`, `LINE_BEYOND_SAMPLE`) czytają surową próbkę. Każda przyszła korekta za przeciwnika, która odsunie p od surowej próbki w górę, zostanie automatycznie zdjęta | `confidence.py:623-655`; `run_confidence.py:785-830` | Mierzyć każdy model matchupu razem z tymi bramkami; rozważyć próbkę skorygowaną o przeciwnika jako wejście bramek | tak | P2/S (po B13/B15; Część 6 W7) |
| A6 | piłka, krzywe pewności | Krzywe są dopasowane w replayu **bez ratingu** w centrum, a SHEET na żywo miesza rating po połowie | `calibrate_from_cache.py:1017-1018`, `:1064-1072`; `run_sheet.py:1197-1215` (CLAUDE.md „prices the same estimator as SHEET” jest dla piłki nieprawdziwe) | Replay ratingu as-of każdego meczu, potem refit (na kopii bazy, za zgodą operatora) | tak (refit) | P1/L |
| A7 | koszykówka, hokej: krzywe historii | `synthetic_lines` stawia linie w kwantylach **własnej** symulacji. Linie Superbetu stoją tam, gdzie widzi je rynek. Koszykówka (3 625 linii / 665 meczów z odczytem ≥ 0,70, krzywe `.next`): krzywa 0,760, realizacja 0,633, cena bez marży 0,628; luka rośnie z rozjazdem model − cena, do −26,0 pp | `sport_confidence.py:594-636`, `:221` | Dopasować krzywe na liniach postawionych tam, gdzie stał rynek (historyczne kursy Sofascore służą **tylko** do pozycji linii, nie wchodzą do p). Blisko odrzuconego "blend the price", więc wymaga wyraźnej zgody operatora. Wymaga backfillu kursów przez most; dostępności kursów kosza w Sofascore nie sprawdzono | tak | P1/M |
| A8 | koszykówka: szum symulacji | Reszty kwart liczone wobec ratingu po całym oknie (docstring `score_model.py:574` mówi „one step ahead”, kod robi `book.update` na `:594` przed resztami); symulacja na historii za szeroka (`total` +6,4..+6,9 pp w holdoucie) | `score_model.py:570-647` | Kandydat, nie stwierdzona przyczyna (Część 4: przyczyna i kierunek niezmierzone; kod `:614-615` nazywa to przybliżeniem). Zmierzyć trzy warianty osobno (reszty krok przed, bez `bb_fresh_mult`, `bb_sd_level_power`) na kalibracji kubełków ≥ 0,70 i na liniach Superbetu; wdrażać tylko zwycięski | tak | P2/S (nadany na liście, źródło bez priorytetu) |

### B. Brak kontekstu matchupu i stylu (główne pytanie operatora)

| id | sport / rynek | brak | miejsce w kodzie | rozwiązanie (literatura) | dane | wpływ na druk | prio |
|---|---|---|---|---|---|---|---|
| B1 | piłka `corners_for`, `shots_for`, `cards_points_for`, `fouls_for` | Błąd roli faworyt / outsider. Próbka strony ze słabszej ligi przeszacowuje rożne o +0,80, blend o +0,54 (714 stron z 34 918). `corners_for` OVER faworyta: zrealizowane 0,920 przy p 0,764 (n=100, 39 meczów, 10-09..10-12), wobec 0,837 przy 0,772 w meczach wyrównanych | `run_sheet.py:1197-1215` (blend 50/50); `football_rating.py` (Maher bez terminu "różnica sił → styl") | Oczekiwana różnica goli z ratingu jako współzmienna centrum rynków liczbowych (game state; Buraimo, Forrest, Simmons 2010; Wheatcroft 2020) | rating już jest | tak (przez przełącznik) | P1/M |
| B2 | piłka `corners_total` (+ połowy rożnych, `offsides_total`, `cards_points_for`) | Bez ratingu, bez korekty siły ligi i rywali, bez gospodarza. Wyłączenie z ratingu oparto na 5 dniach, a wykluczenia wybrano na tych samych dniach | `football_rating.py:126-136` `UNRATED_MARKETS`; `run_sheet.py:1066` | Ponowny pomiar ratingu i siły ligi na pełnej historii (log-loss poza próbą). Uwaga: Część 1 zmierzyła MSE sumy rożnych, rating 11,76 jest gorszy od puli 11,56, i proponuje zamiast tego per-market K=40 (P2/S), ale K=40 dla corners_total zmierzono już 10-08 bez rozstrzygnięcia (lc −4,2 [−10,1; +1,9], `k_under_dispersion_2026-10-08.md:33`; `pooling_2026-10-08.md` §4), więc bez nowego dowodu nie proponować; gospodarz jako mnożnik home/away ligi na środku, nie podział próby (memory „venue is a prior, not a split”; Część 1: P3/S; `venue` jest zapisywane w `samples.py:927`, SHEET go nie czyta) | historia w cache'u | tak (przez przełącznik) | P1/S |
| B3 | piłka: rynki łączne `both_over_*`, `handicap_corners`, `most_*` | Gdy Superbet nie kwotuje drabinki jednej strony, brzeg tej strony bierze się z surowej próbki (bez rywala). Kyoto −2,5 rożnego: p 0,060 przy rynku 0,504; Kyoto najwięcej rożnych: p 0,141 przy rynku 0,721. Zależność stron to jedna stała na metrykę | `run_sheet.py:1648-1656`; `derived.py:494-528`, `:618`; `config/sofa_side_correlations.json` | Brzegi zawsze liczone formułą SHEET (shrink + 0,5 × rating atak × obrona), także bez kwotowanej drabinki; przy UNLINKED odmowa jak dla wiersza marginalnego (P1/M). Zależność zależna od różnicy sił (van der Wurp i in. 2019) **nakłada się** z odrzuconą korelacją per klasa ligi; potrzebna nowa oś dowodu (P3/M) | rating już jest | tak (przez przełącznik) | P1/M |
| B4 | piłka, propsy zawodników | Centrum = surowa średnia startów (6 312 z 6 312 wierszy 10-13). Brak priora, rywala, pozycji, minut, udziału w strzałach drużyny i potwierdzenia składu | `run_sheet.py:608`, `:1163-1202` | stawka zawodnika = strzały drużyny (rating vs rywal) × skurczony udział zawodnika × oczekiwane minuty. Kurczenie do pozycji przypomina odrzucony pooling EB (tam: liczniki drużyn), więc trzeba o tym powiedzieć operatorowi | `sofa_event_stats.lineups_json` (53 685 meczów, pozycja i `substitute`) | tak (przez przełącznik) | P1/L |
| B5 | tenis: gemy w setach (`games_set1/2_total`, `games_won_set1/2_for`), `sets_total` | Bez rywala. Własna próbka 8–10 meczów skurczona do globalnej średniej tenisa (`PRIOR_GLOBAL`: 99% wierszy gemów w secie, 78% `games_won_set*_for`, reszta bez priora; `sets_total` ma prior tier × płeć × powierzchnia). To 324 z 432 rozliczonych nóg tenisa 10-09..10-12 | `engine.py:42` `EMPIRICAL_FREQUENCY_METRICS`; `tennis_rating.py:130` `_READABLE_MARKETS`, `:140` `RATING_PRICED_MARKETS` | Odczyt z sąsiadów ratingu, jak dla `games_won_for` (tam −0,0716 log-loss); zmierzyć per rynek | tabela już jest | tak (przez przełącznik) | P1/S |
| B6 | tenis: cały rozkład wyniku | Brak matchupu serwis × return na poziomie punktu. Sąsiedzi są wybierani tylko po p wygranej; powierzchnia nie wpływa na wybór sąsiadów | `tennis_rating.py:621` `_window`, `:688`, `:716` | Siła serwisu jako druga współrzędna wyboru sąsiadów. **Nakłada się** z odrzuconym modelem serwis/return z 10-08 (tamten był zamiennikiem), więc potrzebny zarejestrowany test | `servicePointsScored`, `receiverPointsScored`, `serviceGamesWon` w `sofa_event_stats` | tak (przez przełącznik) | P1/M (źródło), wymaga zarejestrowanego testu |
| B7 | koszykówka: totale, handicapy, team totals | Brak tempa (posiadania Olivera), czterech czynników, odpoczynku i B2B (`b2b_delta = 0`; B2B zmierzone na punktach bez efektu, +0,06 pkt, se 0,64; niezmierzone na kalibracji ≥ 0,70), składów i fazy sezonu. Brier na liniach głównych 0,259–0,264, gorzej niż moneta | `score_model.py` (czyta tylko listingi); `:218` | Efektywność ataku × obrony na posiadanie × oczekiwane tempo (Oliver 2004; KenPom) | ~34 tys. meczów z box score w `statistics_json` | tak (przez przełącznik) | P1/L |
| B8 | hokej | Brak bramkarza (save%), strzałów, przewag i pustej bramki w modelu wyniku | `score_model.py` | Częstość strzałów × save% bramkarza startowego; empty net w handicapach i totalach | ~3–7 tys. meczów ze strzałami (`Hits`/`FaceOff` ~3 tys.), ~3,3 tys. z przewagami, ~1 tys. z pustą bramką, ~3 tys. z save% | tak (przez przełącznik) | P2/M |
| B9 | siatkówka: `points_total`, `points_handicap` | Model wymian i.i.d. bez przewagi serwisu (`vb_sideout = 0`) i bez szoku seta (`vb_set_sd = 0`). Nawet z idealnym udziałem (diagnostyka w próbie) mecze wychodzą o 4–6 pkt za krótkie; side-out 0,62 i set_sd 0,02 zmierzono 2026-10-01 i nie włączono (side-out psuje zwycięzcę i P(5 setów)). Na liniach (krzywa przed offsetem): −13,4 pp ogółem, `points_handicap` −29,5 pp; offset line evidence już to odejmuje, więc skutkiem jest brak druku (0 nóg `points_handicap` na kuponach 10-05..10-13), nie przeszacowany kupon | `score_model.py:504`, `:238`, `:244` | Bezpośredni model długości seta (Egidi & Ntzoufras 2020: logit zwycięzcy seta + ucięty NB punktów przegranego) albo minimalnie kalibrator długości seta per płeć × liga (Część 5 (b); side-out 0,6–0,7 luki nie zamyka: M 158,4–160,4) | historia | tak (przez przełącznik) | P1/M |
| B10 | CS2 `map_team_rounds` | Ignoruje rywala: częstość własna skurczona do bazy. OVER −21,6 pp (66 linii / 24 serie; poniżej MIN_OFFSET_GAMES 30, więc w druku działa tylko offset puli CS2 −3,5 pp; 0 nóg na kuponach 10-07..10-13) | `cs2_engine.py:838-841` | Wyścig rund `map_distribution_for` (`:565`) już istnieje | — | tak (przez przełącznik) | P1/S |
| B11 | CS2: wszystkie rynki map | Brak mapy, strony startowej i połów. Każda mapa serii ma to samo p | `cs2_engine.py:375` `load_history` | Rating per mapa i strona (Elo/Glicko per mapa) | `cs2_map.map_name`, `home_starting_side`, `home_period1/2` | tak (przez przełącznik) | P2/M |
| B12 | CS2: kille, zgony, asysty zawodnika i drużyny | Nie zależą od oczekiwanej liczby rund ani rywala (korelacja killi z rundami 0,592) | `cs2_engine.py:611`, `:710` | kille = rundy z wyścigu × stawka na rundę × siła rywala | `cs2_player_map` (`adr`, `kast`) | tak (przez przełącznik) | P2/M |
| B13 | wszystkie: struktura próbki | `Observation` nie zna rywala (tylko nazwa): brak id, siły i wartości "przeciw" | `contracts.py:129-146` | Dodać `opponent_id`, siłę rywala as-of i wartość `against`; fundament pod korektę próbki o rywala i siłę ligi (Część 6 W1, W4; B15) oraz bramki na skorygowanej próbce (A5 / W7); B1 i B3 go nie potrzebują | cache ma id rywala | nie (struktura danych; skutek przez B15 / A5) | P1/M |
| B14 | piłka `goals_for`, `shots_for` | Jedno W=0,5 dla wszystkich rynków; rating sam lepszy w MSE (goals_for 2,412 vs blend 2,485) | `football_rating.py:125` | W per rynek dopasowane na log-lossie linii z replayem ratingu (A6) | historia | tak (przez przełącznik) | P1/M |
| B15 | piłka: rynki liczbowe (połowa środka z próbki, cały środek UNRATED) | Próbka nieskorygowana o siłę rywali i siłę ligi, w której ją zarobiono (wzorzec Aktobe w próbce): `corners_for` strony silniejszej domeny +1,65 [+0,37; +3,29], n = 13, 6 dni | `run_sheet.process_fixture` przed `deduplicate_observations`; `football_rating.py:748-768` | Obserwacja przeskalowana do neutralnego rywala (`x/def_opp`, Maher 1982) i do domeny dzisiejszego meczu (`exp(±k·lf)`); pomiar `measure_sample_composition.py`, próg górne CI < 0 (Część 6 W1, W4) | wymaga B13 | tak (przez przełącznik) | P1/M |

Źródło B14: Część 1 (`W_FOOTBALL_RATING` per rynek: P1/M w sekcji `goals_for`, P2/M w „Braki wspólne” 4; lista bierze P1/M), dopisane w rundzie 1 (V1-21). B15: Część 6 W1 i W4 (runda 2).

### C. Pozostały kontekst

| id | sport / rynek | brak | miejsce | rozwiązanie | wpływ na druk | prio |
|---|---|---|---|---|---|---|
| C1 | piłka, rynki goli i wyniku | Faza sezonu zmierzona (goals_total −0,00173 log-loss, względem surowej średniej), ale niewdrożona: kodu nie ma (cecha F3.2; `MODEL_FIXES_FROM_UTC` bramkuje tylko poprawki F2.2: dyspersję tenisa i notatkę OTHER_DIVISION_SAMPLE) | brak kodu (tylko `measure_model_defects.py:688`); docelowo za nowym przełącznikiem albo rozszerzonym `MODEL_FIXES_FROM_UTC` (`epochs.py:171`) | Zaimplementować mnożnik fazy w `run_sheet` i `calibrate_from_cache.shrunk_centre`, odtworzyć w replayu, ponownie zmierzyć względem pełnego p_central (−0,00173 było względem surowej średniej), potem wejść z następnym refitem | tak (przez przełącznik) | P1/M |
| C2 | tenis `games_won_for` UNDER, `sets_total` | Trzysetówki ponad model, skupione na mączce (+12,4 pp [+4,3; +21,7], 130 meczów, 4 dni) [zmierzone, 4 dni — może być wariancja] | `tennis_rating.py:688` (komórka tier × płeć) | Kalibracja P(3 setów \| p) per tier × płeć × powierzchnia na historii (tabela sąsiadów tier × powierzchnia zmierzona 10-08 bez zysku: −29,2e-4 vs −31,5e-4) | tak (przez przełącznik) | P2/M |
| C3 | tenis, format | Best-of-5 bez modelu; ITF wpuszcza super-tiebreak liczony jako 1 gem | `run_sheet.py:812`; `tennis_rating.py:688` | Format z metadanych turnieju; zweryfikować, jak Superbet liczy super-tiebreak | tak (przez przełącznik) | P2/M |
| C4 | tenis: asy, podwójne błędy, punkty serwisowe | Brak returnu rywala i oczekiwanej liczby gemów serwisowych | `tennis_prior.py:65` | stawka na gem serwisowy × oczekiwane gemy serwisowe; poprawka dyspersji (−0,0139 na `aces_for`) czeka na `MODEL_FIXES_FROM_UTC` | tak (przez przełącznik) | P2/M |
| C5 | piłka: połowy | Centra połów liczone osobno, nie jako udział pełnego meczu; 2. połowa bez stanu meczu | `football_rating.py:63-80` | Udział połowy z ligi lub drużyny × centrum pełnego meczu | tak (przez przełącznik) | P2/M |
| C6 | piłka `saves_*` | Obrony bramkarza bez celnych strzałów rywala | `run_sheet.py` (brak ratingu) | saves = celne rywala (rating) × skuteczność bramkarza | tak (przez przełącznik) | P2/M |
| C7 | piłka: styl | Posiadanie i dośrodkowania w cache'u, nieużywane (`ballPossession` w 92,7% wierszy piłki z `/statistics`: 99 541 z 107 435) | grep: brak w `src/bet/sofa` | Posiadanie / styl jako współzmienna rożnych i strzałów | tak (przez przełącznik) | P3/M |
| C8 | koszykówka: remis po regulaminie | Niedoszacowany ~1,8× (0,022 wobec 0,040) | `score_model.py` | Efekt "overtime spike" (Ely (Cheap Talk 2009)) | tak (przez przełącznik) | P2/S |
| C9 | siatkówka: rynki setowe (744, 782, 781, 100077) | Rynki setowe są poza `HISTORY_MARKETS` i bez `PERIODS` dla siatkówki (decyzja plan F4 / operator 10-07: tylko rozliczone linie), więc nie ma krzywej historii i rynek praktycznie nigdy się nie drukuje | `sport_confidence.py:205-209` | Dodać okresy siatkówki | tak (przez przełącznik) | P2/S |
| C10 | siatkówka: "set na przewagi" | Niedoszacowany (9,7% wobec 12,3% M) | `score_model.py:504` | Zależy od B9 (side-out 0,65 daje 11,2% u M; niezmierzone OOS) | tak (przez przełącznik) | P2 |
| C11 | CS2 `match_winner` vs rynki serii | Dwa niespójne modele serii | `cs2_engine.py:769`, `:784` | Jeden model (Beta-mixed) | tak (przez przełącznik) | P2/S |
| C12 | CS2 `map_rounds_total` | Globalna stopa bazowa, bez meczu i mapy | `cs2_engine.py:822-830` | Z wyścigu rund i mapy | tak (przez przełącznik) | P3/S |
| C13 | wszystkie: h2h | Bez wagi; niepusty w ~15% meczów piłki 10-12 (22/143 wg Części 6; 23/156 przy filtrze po `02_fixtures`). Literatura daje mało ponad rating | `samples.py:970`, `:1449-1483`; `run_sheet.py:101-119` | Tani test: h2h z listingów w `sofa.db` (3 lata, bez mostu) jako cecha reszty; spodziewany zysk ~0 | tak (przez przełącznik) | P3/S |
| C14 | wszystkie: flagi kontekstu | `CONGESTED`, `LONG_LAYOFF`, stawka meczu tylko wyświetlane; odpoczynek: zysk minimalny (goals_total −0,00015), stawka bez testu log-loss | `schedule.py`, `stakes.py` | Bez zmian; ponowić pomiar z B13 | nie (pomiar) | P3 |
| C15 | piłka: sędzia | Pokrycie 0,19%, więc pomiar nierozstrzygnięty | `count_families_2026-10-08.md` §5 | Najpierw backfill `/event` | tak (przez przełącznik) | P2/L |
| C16 | piłka `both_over_shots/fouls/offsides` | Brzegi zawsze z surowej próbki | `epochs.py:215-216` | Rozszerzyć `DERIVED_MARGINAL_CENTRES_METRICS` po walk-forwardzie | tak (przez przełącznik) | P2/S |
| C17 | hokej: remis regulaminowy | Niedoszacowany o 1,6 pp (0,1693 vs 0,1855, 2 140 meczów) | `score_model.py:220` `hk_common` | Test `hk_common` > 0 tylko dla hokeja (w piłce bivariate odrzucone; w hokeju wspólny szok i `hk_disp` zmierzone bez zysku, nowym dowodem jest tylko holdout DRAW +1,6 pp) | tak (przez przełącznik) | P2/M |
| C18 | tenis `games_total`, `handicap_games` | Waga 0,5 nie re-mierzona na tabeli tier × płeć; ścieżka handicapu bez ratingu bez informacji (korelacja 0,137) | `tennis_rating.py:143`; `derived.py:93-104` | Re-pomiar wagi {0,5; 0,75; 1,0}; odmowa ścieżki bez ratingu | tak (przez przełącznik) | P2/S |
| C19 | siatkówka: `points_total` | Brak tempa ligi: poziom eh+ea odrzucany, liczy się tylko iloraz | `score_model.py:389-396` | Poziom punktów na set z `league_rates` | tak (przez przełącznik) | P2/S |
| C20 | CS2 `map_rounds_handicap` | Brak krzywej historii (NO_FIT_BUCKET), choć 25 669 map ma rundy | `sport_confidence._cs2_series_rows` | Dodać rodzinę do wierszy historii | tak (przez przełącznik) | P2/S |
| C21 | siatkówka 744/782/781/100077 | Niesprawdzone, czy Superbet unieważnia rynek nierozegranego seta (`actual_value` zwraca None) | `shadow.py:913+` | Sprawdzić w Regulaminie Zakładów Online (2026-02-10, już zlokalizowany 10-13); rozbieżność z kodem to poprawka rozliczenia od razu, z testem | poprawka (rozliczenie, jeśli regulamin różni się od kodu) | P2/S |

Źródła wierszy dopisanych w rundzie 1: C16 — Część 2 (V1-21); C17, C18 — Część 4 i Część 3 (V3-13); C19, C20, C21 — Część 5 (V5-10). Weryfikatorzy proponowali numery C16–C18 niezależnie; numerację uciąglono.

### D. Rynki, których nie wyceniamy, choć da się je policzyć z tego, co mamy

| id | sport | rynki | skąd | wpływ na druk | prio |
|---|---|---|---|---|---|
| D1 | piłka | 1X2, DC, DNB (pomiar C2 z `RAPORT_NOC_2026-10-12.md`: skill z czystego ratingu; krzywa potrzebuje fazy sezonu), BTTS (bez skill względem bazy), HT/FT, dokładny wynik, parzystość, kombinacje Superbetu (13 063 wystąpień 10-13) | `measure_football_result_model.py`; `market_coverage` | tak (przez przełącznik; nowe rynki) | P1/L (DNB/DC) |
| D2 | tenis | zwycięzca meczu i seta, wynik w setach, handicap setowy, parzystość, tiebreak w secie (~3 000 wystąpień 10-12) | `MatchForecast.p_home`, `Outcome.set1/set2/sets` | tak (przez przełącznik; nowe rynki) | P2/M (zwycięzca meczu: zgoda operatora na refit 10-13) |
| D3 | hokej / kosz | NHL totale i handicapy z dogrywką i karnymi (`hk.ot_so_scope`), podwójna szansa, statystyki drużyny w koszu, kamienie milowe, double-double | `market_coverage` | tak (przez przełącznik; nowe rynki) | P2/M |
| D4 | CS2 | rundy serii, parzystość rund, dogrywki, dokładny wynik mapy | `market_coverage.py:521-535`; wyścig rund | tak (przez przełącznik; nowe rynki) | P3/S |

### Kolejność proponowana

1. **Poprawki poprawności z testami:** A2 (odmowa sparingu / przedsezonu tą samą regułą co `FRIENDLY_FIXTURE` w piłce, `NO_LEAGUE_RATE` dla rozgrywek bez stawki); zmienia druk, więc za przełącznikiem od następnego dnia 00:00Z. C21: jeśli regulamin rozlicza nierozegrany set inaczej niż kod, to poprawka rozliczenia od razu, z testem.
2. **Tanie pomiary na historii poza próbą** (tylko odczyt, skrypty `measure_*`): A1, A4, B1, B2, B3, B5, B10; B6 jako zarejestrowany test.
3. **Fundament:** B13 (rywal w `Observation`), potem B15 (korekta próbki o rywala i siłę ligi); pomiar razem z A5.
4. **Refit piłki i tenisa** (na kopii bazy, za zgodą operatora): A6 + B14 + C1 + wyniki pkt 2–3. C1 najpierw trzeba napisać (kodu fazy sezonu nie ma, `MODEL_FIXES_FROM_UTC` jej nie obejmuje) i odtworzyć w replayu. Po C1: D1 (DNB/DC; operator 10-13 odmówił ich bez fazy sezonu). Refit zwycięzcy tenisa (D2) ma zgodę operatora z 10-13 i może iść osobno.
5. **Koszykówka, jeden refit:** zatwierdzony 10-13 refit krzywej koszykówki zrobić po A2, A3 + C8 (ta sama ścieżka dogrywki w `_basketball`) i po pomiarze A8. Operatorowi powiedzieć, że bez A7 / B7 refit nie zamknie luki −12,7 pp na liniach Superbetu.
6. **Modele sportów:** B7 (pace w koszu), A7, B9, potem C9 / C10 (siatkówka), B11–B12 (CS2), B8 (hokej), B4 (propsy).

---

Poniżej sześć raportów źródłowych bez skrótów. Lista wyżej odsyła do nich po
szczegóły, dowody i literaturę.

# Część 1

## Piłka nożna: rynki liczbowe jednej wielkości (gole, rożne, kartki, faule, strzały, celne, spalone, obrony, auty, wybicia, odbiory)

Audyt tylko do odczytu, 2026-10-13. Kodu ani danych nie zmieniałem. Pipeline'u nie uruchamiałem.
Bazę czytałem wyłącznie przez SELECT w trybie `mode=ro`. Pomiary własne to skrypty w
`scratchpad/audit/fc/` (`mse.py`, `side.py`, `role.py`, `book.py`, `exp.py`).
Czytają `data/cache/football_history.pkl` (pickle; niczego nie zapisują) albo
`sofa_settled_row`. Każda liczba niżej ma jedną z trzech etykiet:
**ZMIERZONE** (mój skrypt i jego założenia), **Z ARTEFAKTU** (plik dnia) albo **PODEJRZENIE**.

### Podsumowanie

1. **Suma (`*_total`) to pula obu prób, nie matchup. Ale addytywny matchup jest tą samą liczbą.**
   Średnia z puli (X_tot + Y_tot)/2 = ((X_for + Y_against) + (Y_for + X_against))/2, czyli
   addytywne "A_for + B_against" w średniej. Przy równych próbach różnica wynosi zero
   (`run_sheet.py:1066` `deduplicate_observations`). Brakuje nie samej interakcji,
   tylko **korekty za przeciwnika i klasę ligi** w próbach. Dla `corners_total` rating
   tę korektę ma, ale jest wyłączony (`football_rating.py:126-136`, `UNRATED_MARKETS`).
   ZMIERZONE: na sumie rożnych błędy prawie się znoszą. MSE jeden krok naprzód
   (06-01..10-12, 17 459 meczów) wynosi: pula skurczona 11.56, rating 11.76,
   blend 11.58, sama liga 11.63. Mnożnikowe A_for x B_against z surowych prób jest
   wyraźnie gorsze: 13.39.
2. **Rynki jednej strony (`*_for`) mają duży, systematyczny błąd roli (faworyt / outsider, liga silniejsza / słabsza).**
   Próba go nie widzi, a rating usuwa tylko jego część. SHEET bierze 50/50 próby
   i ratingu (`run_sheet.py:1207`), więc zostaje mniej więcej połowa błędu.
   ZMIERZONE, `corners_for`, strona z ligi słabszej o >= 0.3 log siły:
   własna próba przeszacowuje o +0.80, rating o +0.29, blend o +0.54.
   Faworyt (rating goli >= +0.8): próba -0.89, blend -0.60.
   Na rozliczonych wierszach 10-09..10-12 (Z ARTEFAKTU/DB) `corners_for` OVER
   faworyta zrealizował 0.920 przy p_central 0.764 (n=100, 39 meczów).
3. **Defekt (P1): podział sezonu na grupy regionalne zeruje siłę ligi.**
   J1 2026 został podzielony na jednostki -171852 / -171853 (`assign_league_units`,
   `football_rating.py:452`). Siła ligi jest kluczowana jednostką (`_link`,
   `football_rating.py:755-768`), więc J1 startuje od zera.
   ZMIERZONE: siła goli J1 (196) = 0.419 (n=359, miejsce 48 z 3 112 jednostek z n ≥ 10),
   a jednostek 0.168 (n=34) i 0.108 (n=35). To mniej niż V-League 626 (0.243)
   i niewiele ponad Thai League 1032 (0.137).
   Stąd dzisiejsze Công An 2.10 - Kashima 0.97 goli i Kyoto 1.32 - Ratchaburi 1.39 (z siłą 196: 1.80 - 1.02; weryfikacja r1). To ten sam wzorzec "Aktobe",
   który analityk musiał zawetować.
4. **Krzywe są dopasowane do innego estymatora niż ten, który drukuje.**
   Replay nie wkłada ratingu do środka (`calibrate_from_cache.py:1066-1072`, `:1017-1018`).
   SHEET wkłada go dla goli, strzałów, fauli, celnych, spalonych, `cards_points_total`
   i `corners_for` (`run_sheet.py:1197-1215`). Krzywa `market:X|DIR` mapuje więc p
   z innego modelu. Kod sam to nazywa (komentarz `:1066`), ale nie jest to opisane
   jako ryzyko kalibracji.
5. **Stan meczu (game state) nie wchodzi nigdzie.**
   grep: `supremacy`, `game_state` w `run_sheet.py` / `engine.py` = brak (`favourite` tylko w komentarzach o favourite-longshot bias).
   ZMIERZONE: kartki i faule faworyta są przeszacowane (+0.25 / +0.23 pkt próbą,
   +0.22 / +0.18 ratingiem). Rating też tego nie łapie, bo Maher nie ma terminu
   "różnica sił -> styl". Buraimo, Forrest, Simmons (2010) pokazują, że przegrywający faulują.
6. **Styl i posiadanie piłki nie wchodzą.**
   Sofascore `/statistics` ma `ballPossession` (92,7% wierszy piłki w `sofa_event_stats`: 99 541 z 107 435),
   dośrodkowania i wejścia w ostatnią tercję. grep: `ballPossession` w `src/bet/sofa` = brak.
7. **Mecze bezpośrednie (h2h) nie mają żadnej wagi.**
   Kubełek h2h (`samples.py:970`, `:1449-1483`) to mecze, które już są w side_a i side_b.
   Deduplikacja zostawia je raz (`run_sheet.py:101-119`), więc h2h liczy się jak każdy
   inny mecz. W `day_league_observations` (`run_sheet.py:389-401`) też nie ma wagi: klucz (mecz, "") nadpisuje duplikat.
   To nie jest błąd, ale też nie sygnał. Literatura nie daje powodu, by h2h ważyć ponad
   atak x obronę. Zaliczam to do P3.
8. **Gospodarz / wyjazd nie wchodzi do próby.**
   `venue` jest zapisywane (`samples.py:927`), ale SHEET go nie czyta
   (grep: `.venue` w `run_sheet.py` = brak). Rating ma osobne stawki home/away
   (`football_rating.py:781-794`). Dla `corners_total` (bez ratingu) przewagi
   gospodarza nie ma więc wcale.
9. **Sędzia: zmierzone jako INCONCLUSIVE, z powodu pokrycia.**
   Sędzia jest w 0.19% meczów (`docs/sofa/evidence/count_families_2026-10-08.md` §5).
   Dziś 1 458 z 18 996 wierszy `sofa_event_detail`. Bez backfillu `/event` nie da się
   tego ruszyć.
10. **Połowy (`_1h`/`_2h`) liczone są z osobnych prób połówkowych.**
    Brakuje udziału połowy (league/team half share) przy środku pełnego meczu.
    Rating ma tylko 1h dla części metryk (`BASE_METRICS`, `football_rating.py:63-80`).
    `fouls_2h`, `shots_2h`, `sot_2h`, spalone połówkowe, `saves`, `throw_ins`,
    `goal_kicks` i `tackles` są całkiem bez ratingu.

### Mapa obliczeń

```
SAMPLES (samples.py)
  side_a / side_b: ostatnie sample_n=10 meczów każdej strony (config.py:121)
     gole: REGULAR mecze tej samej rozgrywki, gdy >=5 (comparability.py:205, samples.py:1409-1440)
     reszta: najnowsze 10 dowolnych (bez towarzyskich)
  h2h = przecięcie (samples.py:970), już zawarte w side_a/side_b
        │
SHEET (scripts/sofa/run_sheet.py:process_fixture)
  _total: obs = dedup(side_a ∪ side_b ∪ h2h)   (1066)  -> do ~20 sum meczu, każda raz
  _for:   obs = próba jednej strony                    -> do 10
  mean → centre = w·mean + (1-w)·prior, w=n/(n+K)       (1190)
        prior: resolve_prior (491): baseline ligi → dzień → ligi stron → globalny
        K: K_CENTRE 15 albo by_market (per_market_k.py; epoka PER_MARKET_K)
  if rynek ∉ UNRATED_MARKETS i obie strony ≥5 meczów w ratingu:
        centre = 0.5·rating + 0.5·centre               (1207)
        rating = Maher: rate_ligi·home·att_i·def_j·exp(±σ_dom) (football_rating.py:781)
  sd: count_dispersion alpha(market, competition)       (1223-1229; engine.py:288)
  p_raw: NB albo zakotwiczony normalny (shots_total)    (1336; engine.py:354)
        │
CONFIDENCE (confidence.py)
  krzywa market:<m>|<DIR> (kubełki p, Wilson; K13/K13b) z replayu historii
        (calibrate_from_cache.py:_settle_sample, BEZ ratingu)
  → min(offset linii, cap pasma ceny) (line_evidence.py)
  → bramki: MODEL_ABOVE_OWN_SAMPLE (confidence.py:623), CROSS_LEAGUE_UNLINKED, ...
```

Co **nie** wchodzi nigdzie (grep w `run_sheet.py`, `engine.py`, `football_rating.py`
i `confidence.py`): venue próby, sędzia, posiadanie / xG / dośrodkowania, stan meczu
albo różnica sił jako kowariata stylu, odpoczynek (schedule to tylko flaga,
`run_confidence.py:122`), stawka (stakes to flaga, CLAUDE.md), składy (poza propsami),
pogoda.

### Przypadek dnia: 2026-10-13, AFC Champions League Elite East (463)

**Kyoto Sanga - Ratchaburi (16864335), `corners_total`** (Z ARTEFAKTU `03_samples.json`, `05_sheet.json`)

| | rożne za | rożne przeciw | suma meczu | n |
|---|---|---|---|---|
| Kyoto (J1 / Puchar) | 4.50 | 5.88 | 10.38 | 8 |
| Ratchaburi (Thai L1) | 8.30 | 4.50 | 12.80 | 10 |

- Średnia puli = 11.72 (n=18). Prior to `PRIOR_FROM_TEAMS_LEAGUES` 9.548
  (J1 9.53, Thai 9.565), bo rozgrywka 463 nie ma własnego baseline'u.
  K=15 daje środek 10.73. Środek drabinki Superbetu: 9.92.
- Addytywny matchup daje Kyoto (4.5+4.5)/2 = 4.5 i Ratchaburi (8.3+5.88)/2 = 7.09,
  razem 11.59. To praktycznie pula: pula **jest** addytywnym matchupem.
- Rating (ZMIERZONE, `exp.py`, tej rynek nie używa) daje Kyoto 4.98 + Ratchaburi 6.22 = 11.21.
  Liczy z globalnej stawki, bo liga 463 ma 17 meczów z rożnymi, mniej niż wymagane 30.
  Różnica siły rożnych wynosi -0.07 na korzyść Tajlandii.
- Ani pula, ani rating nie widzą, że 8.3 rożnego Ratchaburi zdobyło jako dominator
  słabszej ligi, a w Kioto rola się odwraca. Analityk dał WATCH na OVER 8.5
  i "~9 spodziewane" (`reads.json`).

**Công An Hà Nội - Kashima (16864340)**

- `corners_total`: pula 7.84 (n=19), prior 9.075 (V-League 8.62, J1 9.53), środek 8.39,
  drabinka 8.08. Rating (nieużywany): Công An 5.24 + Kashima 3.56. Rating odwraca rolę,
  zgodnie z goalami: Công An 2.10 - Kashima 0.97 (nota `FOOTBALL_RATING` w `05_sheet.json`).
  Analityk zawetował trzy nogi goli Kashimy jako "wzorzec Aktobe".
- Przyczyna (ZMIERZONE, `book.py`): domena Kashimy to jednostka regionalna -171852
  z siłą goli 0.168 (n=34). V-League ma 0.243, a J1 jako całość 0.419.
  Gdyby wziąć siłę rozgrywki-rodzica (196), wychodzi Công An 1.63 - Kashima 1.24.
  Odwrócenie słabnie, ale nie znika: zostaje przewaga gospodarza i współczynniki
  att/def zdobyte w słabej lidze, potęgowane `CROSS_RATIO_POWER` 0.6.

### Rynek po rynku

#### corners_total (piłka; "liczba rzutów rożnych")

- **Gdzie liczone:** `run_sheet.py:1066` (pula), `:1190` (skurcz do priora),
  `:1197-1215` (rating pominięty przez `UNRATED_MARKETS`, `football_rating.py:127`),
  `:1227` sd, `:1336` p (NB; `engine.py:152`, `NEGATIVE_BINOMIAL_METRICS`).
  Pewność: krzywa `market:corners_total|<DIR>` (np. `calibrated_on` w `08_confidence.json`,
  n=19 421), potem offset linii (dziś -0.0265 na UNDER).
- **Model teraz:** średnia z ~20 sum meczów obu stron, skurczona K=15 do priora ligi.
  Rozrzut NB z alfą historii per (rynek, rozgrywka).
- **Wejścia:** własne próby (sumy meczów), prior ligi, dyspersja. Bez ratingu,
  bez venue, bez korekty za przeciwnika.
- **Braki:**
  1. Brak korekty za siłę przeciwników w próbie i klasę ligi. Wykluczenie ratingu
     zmierzono na 5 dniach Brierem 0.1915 -> 0.1922 (`football_rating.py:127`),
     zanim weszły dyspersja i per-market K.
  2. Brak przewagi gospodarza: próby mieszają home i away, `venue` nieczytane
     (grep: brak w `run_sheet.py`).
  3. Prior meczu międzyligowego to średnia dwóch lig krajowych
     (`resolve_prior`, `run_sheet.py:536-541`), a nie stawka rozgrywki.
  4. Stan meczu: ZMIERZONE, dla sum mały. Meczów jednostronnych (|supremacja| >= 0.8)
     jest na rozliczonych wierszach 10-09..10-12 dla OVER +0.034 vs +0.065 w wyrównanych.
     To bez bootstrapu, więc nie twierdzę, że to istotne.
  5. Styl (posiadanie, dośrodkowania): grep `ballPossession` = brak.
- **Rozwiązanie:** dla sumy nie dokładać ratingu na ślepo, bo ZMIERZONE MSE pokazuje
  rating gorszy od puli (11.76 vs 11.56). Lepiej przyjąć, że suma rożnych jest w dużej
  mierze ligowa. `pooling_2026-10-08.md` mierzy K* dla sum rożnych ~40, a dziś jest 15.
  Pomiar: per-market K=40 dla `corners_total` przez `measure_k_under_dispersion.py`
  (log-loss linii, bootstrap meczów; już zmierzone 10-08 bez rozstrzygnięcia, zob. niżej); dopiero potem epoka. Interakcja ma sens dopiero
  przy rynkach stron i joinach (niżej).
- **Nakładanie się z "zmierzone i odrzucone":** hierarchiczne pooling (odrzucone)
  to inna rzecz niż wybór K per rynek (już przyjęte jako `PER_MARKET_K`).
  K=40 dla `corners_total` zmierzono już 10-08 (lc −4,2 [−10,1; +1,9], nie włączone, `k_under_dispersion_2026-10-08.md:33`); bez nowego dowodu to nie jest nowa propozycja.
- **Priorytet / nakład:** P2 / S.

#### corners_for (piłka; "<drużyna> liczba rzutów rożnych")

- **Gdzie liczone:** jak wyżej, ale `obs` to próba jednej strony (`run_sheet.py:1077-1093`).
  Rating wchodzi w 50% (`:1207`). Pewność: `market:corners_for|DIR`.
- **Model teraz:** 0.5 x Maher (stawka ligi x att x def x exp(σ)) + 0.5 x skurczona próba.
- **Braki:**
  1. **Błąd roli.** ZMIERZONE (`side.py`, 34 918 stron), bias pred - wynik:
     outsider +0.77 (próba) / +0.29 (rating) / +0.53 (blend);
     faworyt -0.89 / -0.30 / -0.60;
     strona ligi słabszej +0.80 / +0.29 / +0.54;
     strona ligi silniejszej -0.95 / -0.35 / -0.65.
     Z ARTEFAKTU/DB (`role.py`, wiersze p_central >= 0.6, 10-09..10-12):
     OVER faworyta 0.764 -> 0.920 (n=100 / 39 meczów);
     UNDER outsidera 0.774 -> 0.833 (n=138 / 49 meczów).
     Brak przedziałów ufności, więc to kierunek, nie dowód.
  2. W=0.5 wybrano na 5 dniach Brierem (`football_rating.py:113-124`).
     ZMIERZONE MSE strony: rating sam 7.367, blend 7.348, próba 7.586.
     Blend jest najlepszy w MSE, ale zostawia połowę biasu roli.
  3. Siła ligi zerowana w jednostkach regionalnych (defekt z podsumowania, pkt 3).
  4. Rating liczy z globalnej stawki, gdy rozgrywka ma < 30 meczów
     (`league_rates`, `football_rating.py:770-779`). Tak jest dziś w ACL (17 meczów).
- **Rozwiązanie:**
  - (a) Termin stanu meczu: środek_for = Maher x exp(β_m x supremacja_goli),
    gdzie supremacja to różnica oczekiwanych goli z ratingu tej samej książki.
    Regresja Poissona/NB z kowariatą (struktura atak × obrona jak u Dixon & Coles 1997; JRSS C 46(2) 265-280; sama kowariata stanu meczu to nasze rozszerzenie,
    https://academic.oup.com/jrsssc/article/46/2/265/6990546). Yip i in.
    (arXiv:2112.13001, https://arxiv.org/abs/2112.13001) dodają do rożnych informację
    z innych rynków. Nam wolno tylko statystyki, więc zamiast kursów supremacja z ratingu goli.
  - Miejsce: `FootballForecast.centre` (`football_rating.py:931`); β per metryka
    dopasowane na historii.
  - Dane: już są (pickle historii, `goals_for` w tej samej książce).
  - Pomiar: one-step-ahead log-loss NB linii 06-01..10-12, bootstrap po meczach,
    oba przecięcia; dla rzutów rożnych osobno OVER i UNDER; próg CI < 0.
    Potem replay z ratingiem (pkt b) i dopiero epoka.
  - (b) W per rynek fitowane na replayu z ratingiem.
- **Nakładanie się:** "re-ranking peers by recent form" i "league selection" to inne
  propozycje. Kowariata supremacji nie była mierzona (`docs/sofa/evidence`:
  "stan meczu" tylko jako niezmierzony kandydat dla kartek w `LITERATURA_2026-10-08.md` #13). Zgłaszam ją jako nową.
- **Priorytet / nakład:** P1 / M.

#### corners_1h_total, corners_1h_for, corners_2h_total, corners_2h_for (piłka; "1./2. połowa - liczba rzutów rożnych")

- **Gdzie liczone:** jak `corners_*`. Metryki połówkowe to `metrics.py:166-189`
  (okres 1ST/2ND z `/statistics`). Wszystkie cztery są w `UNRATED_MARKETS`
  (`football_rating.py:128-132`), więc bez ratingu. NB dla 1h (`engine.py:168-169`).
  Dla 2h normalny, bo nie ma go w `NEGATIVE_BINOMIAL_METRICS`, chyba że pokrywa go
  tabela dyspersji (nie sprawdzałem, które rynki połówkowe ma
  `config/sofa_count_dispersion.json`).
- **Model teraz:** pula sum połówkowych, skurcz do priora (`day_league_observations`
  pomija połowy, `run_sheet.py:385-386`, więc prior połowy pochodzi tylko z baseline'u
  albo z globalnej puli).
- **Braki:**
  1. Brak struktury okresów: środek połowy nie korzysta ze środka całego meczu x udziału połowy.
  2. Brak stanu meczu dla 2h. Faworyt prowadzący po 1h "siedzi", co jest PODEJRZENIEM
     zgodnym z Lago-Peñas i in. (2010, Apunts 102, https://revista-apunts.com/en/the-influence-of-match-location-the-quality-of-opposition-and-match-status-on-possessionin-professional-football/):
     posiadanie zależy od statusu meczu. Kierunku z samego streszczenia nie znam.
  3. Siła ligi dla `corners_1h_for` jest dziś UNLINKED w ACL (ZMIERZONE, `exp.py`).
- **Rozwiązanie:** centre_1h = centre_FT x share_1h(liga, ewentualnie drużyna skurczona),
  gdzie share liczony z `/statistics` 1ST/ALL w historii. Miejsce: `run_sheet.py`
  przed `:1190` (nowa ścieżka dla `_is_half_metric`). Pomiar: log-loss linii 1h/2h
  vs dziś, bootstrap, osobno OVER i UNDER.
- **Nakładanie się:** brak.
- **Priorytet / nakład:** P2 / M.

#### goals_total (piłka; "liczba goli")

- **Gdzie liczone:** próba to REGULAR mecze tej samej rozgrywki, gdy >= 5
  (`samples.py:1409-1440`, `comparability.py:205`). Pula `run_sheet.py:1066`, skurcz `:1190`,
  rating 50% (`:1207`; `goals_for` w `BASE_METRICS`), NB. Pewność: `market:goals_total|DIR`
  z replayu **bez** ratingu (`calibrate_from_cache.py:1066-1072`).
- **Wejścia:** próba, prior, rating Maher z siłą ligi, dyspersja.
- **Braki:**
  1. Niezgodność estymatora: live ma rating, krzywa go nie ma. ZMIERZONE dla sum:
     blend 4.257 MSE vs pula skurczona 4.317. Live liczy więc inny (lepszy w MSE) środek
     niż ten, z którego zrobiono krzywą. Skutek dla kalibracji nie jest zmierzony
     (PODEJRZENIE: krzywa była ustawiana na mniej rozrzucone p).
  2. Siła ligi zerowana w jednostkach regionalnych (pkt 3 podsumowania).
     Dla sumy wpływ mniejszy (Công An – Kashima 3.07 -> 2.87, Kyoto – Ratchaburi 2.71 -> 2.82 w składowej ratingu), dla `goals_for` krytyczny.
  3. xG jest w `/statistics` (`metrics.py:140`, `xg_total`, `NON_COUNT_METRICS`),
     ale nie zasila środka goli. Wheatcroft (2020, IJF 36(3) 916-932,
     https://researchonline.lse.ac.uk/id/eprint/103712) pokazuje, że ratingi GAP ze strzałów
     i rożnych dają przewagę na O/U 2.5. Kolejka CLAUDE.md ("football joints with the
     football rating in their centre") jest pokrewna.
- **Rozwiązanie:**
  - (a) Rating w replayu (`calibrate_from_cache.py:_settle_sample` z `RatingBook`
    replayowanym as-of, jak tenis `AsOfRating`), refit krzywych na kopii DB.
  - (b) Siła ligi jednostki dziedziczona z rodzica, opisana niżej w "Braki wspólne".
  - (c) GAP/xG jako druga składowa środka. Pomiar: `measure_*` one-step log-loss,
    bootstrap meczów.
- **Nakładanie się:** Dixon-Coles i bivariate Poisson są odrzucone. To nie dotyczy (a)-(c).
- **Priorytet / nakład:** (a) P1 / L (refit, zgoda operatora); (b) P1 / S; (c) P2 / M.

#### goals_for (piłka; "<drużyna> liczba goli")

- **Gdzie liczone:** jak wyżej, próba jednej strony. Rating 50%.
- **Braki:**
  1. ZMIERZONE (`side.py`, 164 522 stron): rating sam ma MSE 2.412,
     blend 50/50 2.485, próba 2.704. Bias blendu dla strony ligi słabszej +0.31,
     silniejszej -0.37; faworyt -0.41, outsider +0.27. Rating bez blendu ma tu bias ~0.
     W=0.5 kosztuje więc połowę korekty roli.
  2. Defekt jednostek regionalnych: dziś Kashima 0.97 (analityk zawetował 3 nogi).
  3. Przy UNLINKED rating i tak daje środek (`football_rating.py:943-948`),
     a CONFIDENCE odrzuca wiersz. To jest OK.
- **Rozwiązanie:** W per rynek. Dla `goals_for` prawdopodobnie W -> 1 (rating sam),
  co trzeba zweryfikować log-lossem linii, nie MSE. Do tego dziedziczenie siły.
  Miejsce: `W_FOOTBALL_RATING` jako słownik per rynek (`football_rating.py:125`),
  plus replay. Pomiar jak wyżej.
- **Nakładanie się:** "blending the price" to inna rzecz. Tu waga rating vs próba,
  obie bez ceny.
- **Priorytet / nakład:** P1 / M.

#### goals_1h_total, goals_1h_for, goals_2h_total, goals_2h_for (piłka; "1./2. połowa - liczba goli", "<drużyna>")

- **Gdzie liczone:** wynik połowy z listingu (`metrics.py:105-110`). Próba tej samej
  rozgrywki (`comparability.py:205`). Rating ma `goals_1h_for` / `goals_2h_for`
  (`BASE_METRICS`), NB.
- **Braki:**
  1. Brak spójności połów z całym meczem: 1h i 2h mają osobne środki,
     bez ograniczenia 1h + 2h = FT. PODEJRZENIE: niespójne drabinki.
  2. Brak stanu meczu w 2h. Dixon & Robinson (1998, The Statistician 47(3) 523-538)
     modelują intensywność goli zależną od wyniku. Metadane potwierdzone (Crossref 10.1111/1467-9884.00152); treści nie czytałem.
  3. `day_league_observations` pomija połowy (`run_sheet.py:385-386`), co jest
     świadome (błędy podziału okresów Sofascore).
- **Rozwiązanie:** centre_h = centre_FT x udział połowy (liga, z listingu, as-of).
  Pomiar log-loss linii 1h/2h.
- **Priorytet / nakład:** P2 / M.

#### cards_points_total, cards_points_for (piłka; "liczba kartek" w punktach karnych, "<drużyna> liczba kartek")

- **Gdzie liczone:** `metrics.py:112-135` (punkty z `/incidents`), NB. Rating działa dla
  `_total` (baza `cards_points_for`). `cards_points_for` jest w `UNRATED_MARKETS`
  (`football_rating.py:133`). Per-market K `cards_points_for` = 25 (CLAUDE.md, epoka PER_MARKET_K).
- **Braki:**
  1. **Stan meczu / rola.** ZMIERZONE (`side.py`, 18 486 stron): faworyt przeszacowany
     o +0.25 (próba) / +0.22 (rating); strona ligi silniejszej +0.30 / +0.25.
     Przegrywający faulują i kartkują więcej, co zgadza się z Buraimo, Forrest, Simmons
     (2010, JRSS A 173(2) 431-449, https://knowledge.lancashire.ac.uk/4669).
     Z ARTEFAKTU/DB: `cards_points_total` UNDER p_central 0.733 -> 0.660 (n=241 / 143 mecze),
     OVER 0.722 -> 0.792. To kierunkowe przeszacowanie UNDER, niezależne od roli,
     więc rzecz dla krzywej / offsetu (już działa offset linii).
  2. **Sędzia.** INCONCLUSIVE z powodu pokrycia (`count_families_2026-10-08.md` §5:
     +0.43 pkt na 1 SD żółtych sędziego w próbie, ale nie as-of i nie poza próbą).
     Philipson (2026, JRSS A, "Yellow fever", https://eprints.ncl.ac.uk/312598):
     heterogeniczność sędziów jest porównywalna z heterogenicznością drużyn,
     co uzasadnia nakład na dane.
  3. Derby i stawka: `stakes.py` daje tylko flagę (CLAUDE.md "never gated").
     Efekt +0.2 kartki jest zmierzony, ale nie wchodzi do środka.
  4. Kartki w połowie / dokładna liczba / czerwone są niezmapowane
     (`fb.cards_half_or_exact` 123, `fb.red_cards` 84 wystąpienia dziś, `market_coverage.md`).
     Połowy celowo pominięte (`metrics.py:153-158`).
- **Rozwiązanie:** środek = Maher x exp(β x supremacja) + β_stakes x flaga (as-of tabela z `stakes.py`).
  Sędzia: backfill `/event/{id}` dla historii (bridge, krótkie porcje), potem
  random-effect sędziego skurczony (CMP / NB) jak u Philipsona.
  Pomiar: log-loss NB linii, bootstrap meczów, OOS. Pokrycie musi być najpierw
  >= ~50% meczów z kartkami.
- **Nakładanie się:** stakes "shown, never a correction" to decyzja operatora.
  Przeniesienie efektu do środka wymaga nowego pomiaru OOS i zgody.
- **Priorytet / nakład:** stan meczu P2 / M; sędzia P2 / L (dane); stakes P3 / S.

#### fouls_total, fouls_for, fouls_1h_total/for, fouls_2h_total/for (piłka; "liczba fauli")

- **Gdzie liczone:** `fouls_for` / `fouls_1h_for` w ratingu (`BASE_METRICS`).
  `fouls_2h_*` bez ratingu (nie ma ich w `BASE_METRICS`). Rozkład: normalny ze
  zmierzoną dyspersją, jeśli tabela go zawiera (`fouls_1h/2h` cienkie, poza tabelą,
  `count_dispersion.py:20-21`). K `fouls_total` = 2.
- **Braki:**
  1. ZMIERZONE: dla fauli najlepszy jest blend. MSE strony: blend 15.28, rating 15.53,
     mnożnik skurczony 15.46, próba 15.99. Bias faworyta +0.21 (blend).
     Mnożnikowe for x against wypada lepiej niż addytywne (15.46 vs 15.80):
     faule to faktycznie interakcja.
  2. Sędzia i stan meczu: jak przy kartkach.
  3. CLAUDE.md: `fouls_total UNDER` historycznie przeszacowane (0.729 / 0.389, n=36).
- **Rozwiązanie:** jak kartki, ze stanem meczu. Pomiar log-loss.
- **Priorytet / nakład:** P3 (drukuje 0 dziś) / M.

#### shots_total, shots_for, shots_1h_*, shots_2h_* (piłka; "liczba strzałów")

- **Gdzie liczone:** `shots_for` i `shots_1h_for` w ratingu. `shots_total` ma normalny
  zakotwiczony (`count_dispersion.py:47` `NORMAL_MARKETS`). K: `shots_for` 8,
  `shots_total` 5. `shots_2h` bez ratingu.
- **Braki:**
  1. ZMIERZONE: rating sam wygrywa (MSE strony 23.31 vs blend 23.66 vs próba 26.68).
     Bias blendu dla faworyta -1.55, outsidera +0.95, strony ligi silniejszej -1.79.
     To największy bias roli w obszarze.
  2. Z ARTEFAKTU/DB: `shots_total` w meczach jednostronnych OVER p_central 0.707 -> 0.641
     (n=117 / 36 meczów), w wyrównanych 0.712 -> 0.753. Suma strzałów w meczu
     jednostronnym jest niższa od puli (PODEJRZENIE, mała próba).
  3. `totalShotsOnGoal` to wszystkie strzały, co jest znaną pułapką (memory). Sprawdzone w metrics.
- **Rozwiązanie:** W -> rating dla `shots_for` plus termin supremacji. Pomiar jak `corners_for`.
- **Priorytet / nakład:** P1 / M (te same zmiany co `corners_for`, jeden pomiar).

#### shots_on_target_total, shots_on_target_for, sot_1h_*, sot_2h_* (piłka; "liczba celnych strzałów")

- **Gdzie liczone:** `shots_on_target_for` i `_1h_for` w ratingu. `_2h` bez ratingu.
- **Braki:** ZMIERZONE (sumy) blend 11.32 < pula 11.39 < rating 11.50.
  Z ARTEFAKTU/DB `shots_on_target_for` OVER faworyta 0.758 -> 0.870 (n=46 / 22 mecze).
  Ten sam wzorzec roli co rożne, na małej próbie.
- **Rozwiązanie / priorytet:** w pakiecie supremacji. P2 / S po zrobieniu `corners_for`.

#### offsides_total, offsides_for, offsides_1h/2h_* (piłka; "liczba spalonych")

- **Gdzie liczone:** `offsides_for` w ratingu. `offsides_total` w `UNRATED_MARKETS`
  (n=188 przy decyzji, `football_rating.py:134`). Połowy bez ratingu.
- **Braki:** ZMIERZONE: blend najlepszy (MSE strony 4.48). Styl (wysoka linia obrony
  rywala) to czysta interakcja "rywal_against", ujęta tylko przez `defence` w ratingu.
  `offsides_total` jej nie ma.
- **Rozwiązanie:** zdjąć `offsides_total` z `UNRATED_MARKETS` po pomiarze log-loss
  linii (n=188 to za mało na decyzję z 09-18..22).
- **Priorytet / nakład:** P3 / S (dziś 0 drukowanych).

#### saves_total, saves_for, saves_1h_* (piłka; "liczba obronionych strzałów przez bramkarza")

- **Gdzie liczone:** `metrics.py:291-305` (`goalkeeperSaves`). Nie ma ich w
  `BASE_METRICS`, więc tylko pula plus prior. Nie ma ich w `NEGATIVE_BINOMIAL_METRICS`,
  więc normalny, chyba że pokrywa je tabela dyspersji (nie sprawdzałem).
  Dziś drukowane: 9 + 4.
- **Braki:**
  1. Obrony bramkarza A to funkcja celnych strzałów **rywala** B i skuteczności.
     Model bierze próbę obron A (rywale A), a nie celne B (grep: `saves` w
     `football_rating.py` = brak). To najbardziej "matchupowy" rynek w obszarze
     i jest liczony bez matchupu.
  2. `both_over_saves` niezmapowane (MAPPABLE, 16 wystąpień).
- **Rozwiązanie:** saves_for(A) ≈ sot_for(B) x (1 - konwersja) z centrów ratingu
  `shots_on_target_for` strony B, plus kalibracja. Ewentualnie dodać `saves_for`
  do `BASE_METRICS`. Miejsce: `football_rating.FootballForecast.centre`
  (mapowanie bazy na strony przeciwne). Pomiar: one-step log-loss, bootstrap.
- **Priorytet / nakład:** P2 / M.

#### throw_ins_*, goal_kicks_*, tackles_* (piłka; "rzuty z autu", "wybicia od bramki", "odbiory")

- **Gdzie liczone:** `metrics.py:305-360`. Bez ratingu, pula plus prior. Dziś 0 drukowanych.
- **Braki:** wybicia od bramki A są w dużej mierze funkcją strzałów niecelnych B
  (interakcja, grep: brak). Auty to styl obu stron.
- **Rozwiązanie:** dodać do `BASE_METRICS` (Maher), `goal_kicks_for(A)` sprzęgnąć
  ze strzałami niecelnymi B. Pomiar jak wyżej.
- **Priorytet / nakład:** P3 / M.

#### xg_total, xg_for (zmapowane w metrics, niewyceniane)

- `NON_COUNT_METRICS` (`engine.py:30-31`), bez rynku Superbetu. Jako **wejście**
  do goli (Wheatcroft 2020), opisane przy `goals_total`.

#### Niezmapowane rodziny liczbowe (Superbet oferuje, my nie)

Z ARTEFAKTU (`runs/sofa/2026-10-13/market_coverage.md`):
- `fb.corners_distribution` (142, parzystość / przedziały rożnych);
- `fb.cards_half_or_exact` (123);
- `fb.red_cards` (84);
- `fb.penalties` (66);
- `fb.woodwork` (48);
- `fb.goals_distribution` (531) i `fb.goals_for_distribution` (256);
- MAPPABLE: `fb.team_scores(_half)`, `fb.handicap_corners_half`, `fb.both_over_saves`
  (switch `MAPPABLE_FAMILIES_FROM_UTC` = None).

Przedziały i parzystość wymagają **pełnego rozkładu**, nie tylko środka. NB z tabeli
dyspersji już go daje, więc to kwestia mapowania i krzywej (P3 / M). Czerwone kartki
i karne to rzadkie zdarzenia, a krzywa z linii potrzebuje 50 rozliczonych w kubełku (P3).

### Braki wspólne dla obszaru

1. **Siła ligi w jednostkach regionalnych (defekt, P1 / S).**
   `RatingBook.strength` jest kluczowane `(domain, metric)`, gdzie domain to jednostka
   (`football_rating.py:755-768`, update `:862-873`). Nowa jednostka startuje z σ=0
   i n=0. Dla J1 2026 ZMIERZONE: 0.168 / 0.108 vs 0.419 rodzica.
   - Rozwiązanie: start jednostki z siłą rodzica `strength[(unit_competition(dh), m)]` zamiast σ=0
     (próg n < `MIN_STRENGTH_LINKS` nie odpala: jednostki J1 mają n=34/35, a przy `ALPHA_STRENGTH` 0.02
     start 0 waży jeszcze ~50%). Albo stała siła per rozgrywka (jednostki nadal tylko
     do reguły LINKED). Miejsce: `_link` oraz update residuum.
   - Pomiar: one-step MSE / log-loss goli na parach cross z udziałem jednostek
     regionalnych, 06-01..10-12, bootstrap.
   - Zmienia to, co drukuje (`LINK_*`), więc potrzebny switch w `epochs`.
2. **Niezgodność replayu i SHEET-u (rating w środku tylko live, P1 / L).**
   Dotyczy każdego rynku spoza `UNRATED_MARKETS`. Krzywa `market:X|DIR` jest z innego estymatora.
   - Rozwiązanie: rating replayowany as-of w `calibrate_from_cache.py`
     (książka aktualizowana chronologicznie, odczyt przed meczem).
     Refit na kopii DB, zgoda operatora.
3. **Termin roli / stanu meczu (P1 / M).** Supremacja z ratingu goli jako kowariata
   centrów rożnych, strzałów, celnych, kartek i fauli (per strona, z przeciwnym znakiem
   dla rywala).
   - ZMIERZONE biasy wyżej. To jedyny brak w obszarze, który ma i duży zmierzony efekt,
     i dane już na dysku.
   - Literatura: Buraimo i in. 2010 (stan meczu -> kartki, OTWARTE), Lago-Peñas i in. 2010
     (status meczu -> posiadanie, OTWARTE streszczenie, kierunek nieznany),
     Dixon & Coles 1997 (Poisson atak × obrona; kowariata stanu meczu to nasze rozszerzenie; OTWARTE streszczenie).
4. **W_FOOTBALL_RATING = 0.5 dla wszystkich rynków (P2 / M).**
   ZMIERZONE na MSE: rating sam lepszy dla `goals_for` i `shots_for`, blend lepszy dla
   fauli, rożnych i spalonych. Trzeba dopasować W per rynek na log-lossie linii
   z replayem (pkt 2), nie na 5 dniach Briera.
5. **Venue próby (P3 / S).** Próba strony to mieszanka home i away. Rating ma home ratio,
   ale rynki bez ratingu (`corners_total`, połowy rożnych, saves, auty) nie mają przewagi
   gospodarza wcale. CLAUDE.md "venue is a prior, not a split" (memory) wyklucza podział
   próby. Proponuję mnożnik home/away ligi na środku, nie podział próby.
6. **Styl (posiadanie, dośrodkowania, ostatnia tercja) (P3 / L).** Dane w `statistics_json`
   (próbka 20 000 wierszy, wszystkie sporty: `ballPossession` 9 294, `accurateCross`/`totalCross`
   8 188, `finalThirdEntries` 3 764; w samej piłce `ballPossession` ma 92,7% wierszy: 99 541 z 107 435). Jako kowariata rożnych strony: dośrodkowania_for(A)
   x posiadanie rywala. Wymaga pomiaru. Literatura nie daje gotowego modelu (nie znalazłem).
7. **h2h (P3).** Dziś zero wagi ponad zwykły mecz. Nie proponuję ważenia: brak dowodu
   w literaturze, którą otworzyłem, a h2h to 0-2 mecze na parę (dziś 0 dla obu
   przykładowych meczów).

### Czego nie sprawdziłem

- Moje pomiary MSE / bias (`mse.py`, `side.py`) **nie** odtwarzają SAMPLES:
  - próba to ostatnie 10 meczów z daną metryką w pickle historii, bez filtra
    towarzyskich i rezerw w samej próbie (filtr tylko na meczu docelowym);
  - K=15 dla wszystkich rynków, prior to stawka ligi z książki, nie baseline;
  - gole bez reguły tej samej rozgrywki;
  - MSE środka, nie log-loss linii; bez przedziałów ufności i bez dzielenia po event-id.

  To kierunek, nie dowód na zmianę druku.
- `role.py` używa p_central (nie confidence) z 4 dni, bez bootstrapu. Rolę strony
  ustala dopasowanie nazwy subject do `02_fixtures` (część wierszy odpadła).
- Nie sprawdziłem, które rynki połówkowe, `saves`, `throw_ins`, `goal_kicks` i `tackles`
  pokrywa `config/sofa_count_dispersion.json`.
- Nie czytałem `derived.py` ani `joint.py` (both_over_, most_, handicap_). Korelacja stron
  i matchup w joinach należą do innego obszaru, choć błąd roli z `corners_for`
  przenosi się do nich wprost.
- Nie weryfikowałem wyniku dzisiejszych meczów (start 12:15Z, audyt 10:03Z).
- Literatura: Dixon & Robinson 1998: metadane potwierdzone (Crossref 10.1111/1467-9884.00152); treści nie czytałem.
  Pozostałe pozycje to strony, które otworzyłem (streszczenia, nie pełne teksty).

# Część 2

## Piłka: rynki pochodne (joint), propsy zawodników, rynki wyniku

Audyt tylko do odczytu, 2026-10-13. Nic w repozytorium nie zmieniono, pipeline nie był uruchamiany, mostek / Superbet nie były wołane. Liczby oznaczone **[zmierzone]** policzyłem sam z artefaktów (`runs/sofa/2026-10-13/*.json`, `config/sofa_superbet_line_evidence.json`) lub z bazy (`sqlite3 -readonly`); **[podejrzenie]** to wniosek bez pomiaru.

### Podsumowanie

1. **Dlaczego operator nigdy nie widzi „obie drużyny powyżej 2.5 rożnego”: nie przez model, tylko przez bramkę dowodu z linii.** Od 10-07 klucz pochodny nie ma krzywej (`DERIVED_CURVES_FROM_UTC = None`, `src/bet/sofa/epochs.py:567`). CONFIDENCE ustawia mu wtedy `hit = None` (`scripts/sofa/run_confidence.py:697-698`), więc pewność to tylko dolna granica Wilsona z jego własnych linii Superbetu, podzielona przez efekt projektu sportu (`src/bet/sofa/line_evidence.py:300-312`). Dla piłki ten efekt wynosi **2.437**. Efekt liczy się na liniach wszystkich kluczy naraz (`line_evidence.py:437-440`), ale stosuje się go do kubełka jednego klucza. A w kubełku `both_over_corners|OVER` każdy mecz daje dokładnie jedną linię (games == n w każdym kubełku p ≥ 0.60). **[zmierzone]** Przykład: kubełek p 0.75-0.80 zrealizował 66/78 = **0.846**, a mimo to czyta się jako **0.6825**, poniżej progu 0.70. Bez dzielenia przez efekt projektu Wilson daje 0.750. Na dniu 10-13 dało to 0 z 1 426 wycenionych wierszy pochodnych piłki z kursem. Z efektem 1.0 przeszłoby 8, a wśród nich **Kyoto - Ratchaburi both_over_corners 2.5 OVER @1.51**.
2. **Na kuponach 10-07..10-13 nie było ani jednej pochodnej nogi piłkarskiej [zmierzone]** (`11_coupon.json` każdego dnia; propsy tylko `player_shots_for` / `player_tackles_for`: 0+0+2+3+0+0+1 (10-07..10-13)). `DERIVED_NOT_CALIBRATABLE` (`run_confidence.py:662-664`) od 10-07 nie odpala nigdy. Odmowy niosą `BELOW_CONFIDENCE_FLOOR` albo `NO_LINE_EVIDENCE`, więc w raporcie odmów rodzina pochodna jest niewidoczna jako całość.
3. **Joint nie zna interakcji stron.** Brzegowe rozkłady obu stron to próbki „własne” (`corners_for` z ostatnich ~10 meczów strony, `derived.py:494-496`). Centra z ratingu (atak x obrona, `football_rating.FootballForecast.centre`) trafiają do jointu tylko wtedy, gdy Superbet kwotuje drabinę `corners_for` OBU stron. `marginal_centres` budowane są z wierszy SHEET (`scripts/sofa/run_sheet.py:1648-1656`), a brak wiersza oznacza powrót do surowej próbki (`derived.py:519-528`). **[zmierzone]** Kyoto - Ratchaburi (16864335): Superbet nie kwotuje drabiny Ratchaburi, więc joint bierze surowe 4.5 vs **8.3** (8 z 10 meczów Ratchaburi to Thai League 1032, gdzie dominuje). Wychodzi `handicap_corners` Kyoto -2.5: p **0.060** vs rynek 0.504, `most_corners` Kyoto: p **0.141** vs 0.721. To wzorzec „Aktobe”, tyle że w rożnych.
4. **Zależność stron to jedna stała na metrykę** (`config/sofa_side_correlations.json`: rożne -0.145, gole -0.012, kartki null, a rho 0.126 czeka za `CARDS_CORRELATION_FROM_UTC`). Nie zależy od różnicy sił, stanu meczu ani ligi. Literatura ma kopułę z parametrem zależnym od zmiennych (van der Wurp i in. 2019). Kopuła t i korelacja per klasa ligi są jednak na liście odrzuconych (patrz niżej).
5. **Propsy zawodników: centrum = surowa średnia jego ostatnich startów.** Brak prioru (`NO_PRIOR`, `run_sheet.py:608`, 1175, 1193), brak ratingu (`run_sheet.py:1202` wyklucza `is_player_metric`), brak przeciwnika, pozycji, udziału w strzałach drużyny i potwierdzonego składu. **[zmierzone]** 6 312 z 6 312 wierszy zawodników 10-13 ma `centre == sample_mean`. Pozycje i `substitute` leżą w bazie (`sofa_event_stats.lineups_json`, 53 685 meczów), ale estymator ich nie czyta.
6. **Rynki wyniku (1X2 / DC / DNB / BTTS / HT-FT / dokładny wynik / parzystość / kombinacje Superbetu) nie są mapowane.** Na 10-13 to 25 000 wystąpień COMPUTABLE w piłce, z czego 13 063 to `superbet_combo` (`runs/sofa/2026-10-13/market_coverage.md`). Pomiar C2 (`scripts/sofa/measure_football_result_model.py`) pokazuje umiejętność dla DNB / DC / 1X2 z czystego ratingu. BTTS nie ma umiejętności względem stopy bazowej, a dziś drukowany kształt BTTS (`both_over_goals` 0.5 z jointu) też był gorszy od bazy: +0.0051 Brier (`epochs.py:200-205`).
7. **Ograniczenie, które sam kod przyznaje:** `both_over_*` i `most_*` liczą się z jointu nieprzesuniętego, a `K_DERIVED_CENTRE` w epoce stats_only jest wyłączone (`derived.py:618`). Handicap nie ma więc żadnej kotwicy. Na 10-13 31 meczów `most_corners` i 22+2 meczów `handicap_corners` liczono bez kotwicy, a te bez drabin obu stron (5 z 40 z handicapem) także bez przeciwnika.

### Mapa obliczeń

```
OFFER: market_mapper.classify_derived_market (market_mapper.py:692)
   "Każda z drużyn powyżej X rz.rożnych" -> both_over_corners (line, tak=OVER)
   "Najwięcej ..." / "Liczba ... - H2H"  -> most_<m> (subject: side | __draw__)
   "Rzuty rożne handicap" / "Liczba X - handicap" -> handicap_<m> (subject, signed line)
   (MAPPABLE, OFF: classify_mappable_family market_mapper.py:850; epochs.MAPPABLE_FAMILIES_FROM_UTC=None)
        |
SAMPLES: per-side <m>_for observations (own matches, own opponent ignored)
        |
SHEET  run_sheet.py: marginal rows (corners_for per side: K_CENTRE shrink + 0.5 x rating)
        |-- marginal_centres {(corners_for, side)} ONLY if Superbet quotes that side's ladder (run_sheet.py:1648-1656)
        v
derived.price_derived_rungs (derived.py:445)
   stats_a/b = _side_stats(raw sample) ; if both marginal centres -> marginal_centred_stats (derived.py:249)
   joint = joint.build_joint(mean_a,var_a,mean_b,var_b, rho[base])  Gaussian copula, Poisson/NB margins
   p = derived.probability (derived.py:324): both_over = P(A>=k,B>=k); most = P(A>B)/P(A=B); handicap = P(A-B > -L)
   p_central -> 05_sheet.json (verdict LEAN/BELOW_BAR; VALUE path irrelevant for the coupon)
        |
CONFIDENCE run_confidence.py
   hit = None for derived (run_confidence.py:697, DERIVED_CURVES off)
   evidence.read(key=f"{market}|{dir}", base=None) (line_evidence.py:284)
       -> bucket(p) n>=50 & games>=15  else NO_LINE_EVIDENCE
       -> wilson_lo(k/deff_sport, n/deff_sport), deff football 2.437
       -> band cap (only lowers)
   >= 0.70 and x >= 0.90  -> leg
Player props: SAMPLES build_player_samples (samples.py:1070, starts only) -> SHEET centre = raw mean (no prior, no rating)
   -> NB tail (engine.NEGATIVE_BINOMIAL_METRICS) -> curve market:<m>|OVER (PLAYER_PROP_MARKETS, confidence.py:208)
   -> line offset/band cap -> one_sided_single n>=300 (confidence.py:413)
```

### Rynek po rynku

#### both_over_corners (piłka; „Każda z drużyn powyżej X rzutów rożnych”)
- **Gdzie liczone:** mapowanie `market_mapper.py:710-722`. p z `derived.probability` (`derived.py:332-336`) na `joint.build_joint` (`joint.py:395`). Pewność z `line_evidence.LineEvidence.read` (`line_evidence.py:284-319`), klucz `both_over_corners|OVER`, bez krzywej (`run_confidence.py:697-698`).
- **Model teraz:** P(A>=k i B>=k) z kopuły Gaussa, rho = -0.145 (`config/sofa_side_correlations.json`, 909 par resztowych). Brzegi to Poisson lub NB z momentów. Gdy obie drabiny `corners_for` są kwotowane, brzegi biorą centra wierszy SHEET (`marginal_centred_stats`, `derived.py:249-266`); w przeciwnym razie surową średnią i wariancję próbki.
- **Wejścia:** własne `corners_for` obu stron (n do 10), opcjonalnie centrum SHEET (shrink do prioru ligi + 0.5 x rating atak x obrona), stała rho, dyspersja z `count_dispersion` tylko przy centrach.
- **Liczby dla operatora [zmierzone, `05_sheet.json` 2026-10-13]:**

  | mecz | brzegi | 2.5 OVER p | kurs | 1/kurs | weryfikacja rynkiem |
  |---|---|---|---|---|---|
  | 16864335 Kyoto Sanga - Ratchaburi (ACL) | surowe 4.5 (n 8) / 8.3 (n 10) - brak drabiny Ratchaburi | 0.7745 | 1.51 | 0.662 | `NO_MARKET_MARGINAL` (brak drabin per strona) |
  | 16864334 Shanghai Port - Daejeon | centra SHEET 5.22 / 4.58 | 0.6252 | 1.47 | 0.680 | rynek+rho: 0.650 |

  Odczyt pewności, który policzyłem (replay `LineEvidence.read` na pliku dowodu z 10-13 07:40Z): Kyoto 2.5 → **0.6825** (kubełek 0.75-0.80: 66/78, Wilson z k/2.437, n/2.437), czyli poniżej progu 0.70, noga się nie drukuje. Shanghai 2.5 → p 0.625, kubełek 0.60-0.70: 128/169 → 0.656, też poniżej progu. Cały klucz w kubełkach p ≥ 0.70 (dni arkuszy 10-05..10-12): 0.70-0.75 57/73 (0.78), 0.75-0.80 66/78 (0.85), 0.80-0.825 59/67 (0.88), 0.825-0.85 43/47, 0.85-0.875 44/47, 0.925-0.95 72/74. **Linie realizują powyżej deklarowanego p, a bramka i tak je tnie.** W pasmach kursu przy p ≥ 0.70: 1.00-1.30 352/390 = 0.903, 1.30-1.60 38/51 = 0.745, czyli w paśmie, w którym leży „2.5”, nadwyżka jest mniejsza.
- **Braki:**
  1. **Efekt projektu sportu zastosowany do kubełka jednego klucza.** `design_effect` liczony na liniach wszystkich kluczy (`line_evidence.py:437-440`), dzielenie w `read` (`line_evidence.py:305-310`). W kubełkach tego klucza od p 0.60 w górę games == n, czyli zero klastrowania. Kara jest więc podwójna: Wilson i tak już uwzględnia n. **[zmierzone]** Na 10-13 przy deff = 1 przeszłoby 4 `both_over_corners` + 4 `both_over_goals` UNDER 1.5. Zysku nie mierzyłem.
  2. **Brak przeciwnika i siły ligi w brzegu, gdy Superbet nie kwotuje drabiny strony.** `run_sheet.py:1649-1656` zbiera centra tylko z istniejących wierszy, a `derived.py:521` wraca do surowej próbki. Kyoto - Ratchaburi to dokładnie ten przypadek.
  3. **Surowa próbka niesie ligę, w której strona dominuje (odwrócenie ról).** Ratchaburi 8.3 rożnego z Thai League vs J-League Kyoto. Rating ma `LINKED_BY_STRENGTH` (`football_rating.py:948, :969-973`), ale joint bez centrów go nie widzi.
  4. **Stała rho niezależna od meczu.** `derived.py:517` czyta `correlations.get(base)`. Nierówny mecz (faworyt oblega) powinien mieć silniej ujemną zależność **[podejrzenie]**.
  5. **Stan meczu (score effects).** Przegrywający bije więcej rożnych. Grep `score|game_state` w `derived.py` / `joint.py` nic nie zwraca. Nierówność sił (rating gole) nie wchodzi do jointu rożnych.
  6. **Sędzia, pogoda i składy** nie dotyczą tu wprost. Pominięte celowo.
  7. **Brak weryfikacji rynkiem w ~połowie meczów:** `NO_MARKET_MARGINAL` przy braku drabin per strona (`derived.py:846-850`). Dla kuponu to bez znaczenia (verdict nie jest bramką CONFIDENCE), ale dla analityka to jedyny sprawdzian jointu.
- **Rozwiązanie:**
  - (a) **Efekt projektu per klucz-kubełek:** `fit_line_evidence` zapisuje deff dla kubełka (ta sama funkcja `design_effect` na liniach kubełka), a `LineEvidence.read` czyta go zamiast sportowego. Gdzie games == n, deff wynosi 1. Pomiar: walk-forward jak `measure_sport_guard.py`, czyli dowód dopasowany na dniach < D, nogi dnia D (10-08..10-12, piłka, wszystkie klucze bez krzywej). Metryki: realizacja minus pewność drukowanych (bootstrap po meczach) i ROI dodanych nóg. Próg: dodane nogi nie gorzej skalibrowane niż −2 pp, górna granica CI luki ≥ 0. Zmienia druk, więc potrzebny przełącznik w `epochs` i zgoda operatora.
  - (b) **Brzegi jointu zawsze z `FootballForecast.centre`** (w `price_derived_rungs` przekazać `football` i liczyć centrum strony bez wiersza marginalnego tą samą formułą co SHEET: shrink + 0.5 x rating). Gdzie rating ma `UNLINKED`, odmowa jak dla marginalnego wiersza (`CROSS_LEAGUE_UNLINKED`). Dane są: `football_rating.RatingBook` (pickle `data/cache/football_history.pkl`). Pomiar: rozszerzyć walk-forward z `DERIVED_MARGINAL_CENTRES` (375 714 meczów, `epochs.py:200-205`) o mecze bez drabiny strony. Log-loss i Brier `both_over/most/handicap` vs surowa próbka, bootstrap po meczach.
  - (c) **rho jako funkcja |różnicy ratingu goli|** (dwa do trzech przedziałów): van der Wurp, Groll, Kneib, Marra, Radice 2019, „Generalised Joint Regression for Count Data with a Focus on Modelling Football Matches”, https://arxiv.org/abs/1908.00823 (parametr kopuły jako funkcja zmiennych). Miejsce: `derived.load_side_correlations` plus `scripts/sofa/measure_side_correlations.py` dzielone po przedziałach. Pomiar jak w `dependence_goals_2026-10-08.md`: train/test w czasie, log-loss `both_over_corners`.
  - (d) **Stan meczu:** Skripnikov, Cemek, Gillman 2025, „Leveraging Minute-by-Minute Soccer Match Event Data to Adjust Team's Offensive Production for Game Context”, https://arxiv.org/abs/2508.04008 (GAM z różnicą wyniku, rożne i strzały standaryzowane do remisu). Do pipeline'u: próbka rożnych „skorygowana o stan” wymaga minut goli (`sofa_event_stats.incidents_json`) i rożnych w czasie (Sofascore `/statistics` ma tylko połowy, więc w praktyce 1H/2H). To P3.
- **Nakładanie się z „zmierzone i odrzucone”:** (c) styka się z „t copula or per-league-class correlation for joints”. Nowe jest to, że zmienną jest nierówność meczu (różnica ratingu), nie klasa ligi. Trzeba to powiedzieć operatorowi wprost. (a) nie jest „stricter/looser band cap”, tylko poprawka arytmetyki bramki. Pozostaje jednak zmianą druku.
- **Priorytet / nakład:** (a) **P1 / S**; (b) **P1 / M**; (c) P3 / M; (d) P3 / L.

#### both_over_goals (piłka; „Obie drużyny strzelą”, „Obie drużyny strzelą powyżej X gola”)
- **Gdzie liczone:** `market_mapper.py:724-735` → `derived.probability`. Centra wierszy `goals_for` od 10-07 14:05Z (`epochs.DERIVED_MARGINAL_CENTRES_FROM_UTC`, `epochs.py:207`), rho -0.0118.
- **Model teraz:** joint dwóch NB (dyspersja z `sofa_count_dispersion.json` od 10-09), prawie niezależne.
- **Wejścia:** centra goli (próbka + liga + rating), dyspersja ligowa.
- **Braki:**
  1. **Brak umiejętności względem stopy bazowej:** BTTS Brier +0.0051 gorzej niż baza ligi (`epochs.py:200-205`), C2: +0.0064 (`RAPORT_NOC_2026-10-12.md`, sekcja C2).
  2. **[zmierzone]** Klucz `both_over_goals|UNDER` przy p ≥ 0.70 w paśmie 1.60-2.20 zrealizował 40/85 = 0.47 (dowód linii). Model mocno przecenia tanie „nie strzelą” u outsidera kursowego. Cap pasma to łapie.
  3. **W ratingu gole są ograniczone do LINKED,** a łańcuch gol-strzał (Wheatcroft) siedzi w centrum tylko częściowo (CLAUDE.md „football joints with the football rating in their centre” w kolejce).
- **Rozwiązanie:** nie drukować na samej bazie. Kolejka refitu już ma centrum goli ze strzałów i celnych (Wheatcroft 2020, w `LITERATURA_2026-10-08.md` #8). Pomiar `measure_football_result_model.py` dla BTTS po tej zmianie: log-loss vs baza, próg CI < 0.
- **Nakładanie:** Dixon-Coles / bivariate Poisson odrzucone (rho ~0). Nie proponuję.
- **Priorytet / nakład:** P2 / M (razem z modelem wyniku).

#### both_over_cards_points (piłka; „Każda z drużyn powyżej X kartek”)
- **Gdzie liczone:** jak wyżej. rho = 0 (null w pliku); 0.126 za `CARDS_CORRELATION_FROM_UTC=None` (`epochs.py:309-312`). Brzegi z centrów `cards_points_for` (rating wyłączony dla `cards_points_for`, `football_rating.py:133`).
- **Braki:**
  1. **Sędzia:** `referee` jest w `contracts.py:94`, a grep `referee` w `run_sheet.py` / `derived.py` daje zero. Buraimo, Forrest, Simmons 2010 (#13 w przeglądzie literatury) pokazują efekt sędziego i stanu meczu.
  2. **Stawka** (`STAKES_SIX_POINTER` +0.2 kartki) tylko jako flaga.
  3. **Dodatnia zależność stron** (0.126) zmierzona i czeka na operatora.
- **Rozwiązanie:** włączenie `CARDS_CORRELATION` wymaga `DERIVED_CURVES` (CLAUDE.md), ale klucz i tak czyta tylko dowód linii. **[podejrzenie]** Przy obecnej bramce (kubełek 0.70-0.75: 36/43, n < 50, więc NO_LINE_EVIDENCE niezależnie od deff) nawet poprawne p nie wydrukuje nogi. Sędzia: per-sędzia mnożnik kartek z historii as-of (`sofa_event_detail` jeśli trzyma `referee` - nie sprawdziłem pokrycia). Pomiar log-loss `cards_points_total` / `both_over` na teście w czasie.
- **Priorytet / nakład:** P2 / M (sędzia), P3 / S (rho, decyzja operatora).

#### both_over_shots, both_over_shots_on_target, both_over_fouls, both_over_offsides
- **Gdzie liczone:** jak wyżej. Centra tylko dla `shots_on_target_for` (`epochs.DERIVED_MARGINAL_CENTRES_METRICS`, `epochs.py:215-216`). Strzały, faule i spalone biorą **zawsze surową próbkę**, choć rating dla nich istnieje (`football_rating.BASE_METRICS`).
- **Braki:**
  1. Brak przeciwnika (strzały: rho surowe -0.304, resztowe -0.093 - posiadanie piłki to gra o sumie zerowej).
  2. Faule zależą od stylu przeciwnika (drybling, posiadanie) i sędziego. Nie są w modelu.
- **[zmierzone]** 10-13: `both_over_shots` 35 NO_LINE_EVIDENCE / 44 poniżej progu, `both_over_shots_on_target` 20 / 54, `both_over_fouls` 9 / 30, `both_over_offsides` 3 / 7.
- **Rozwiązanie:** rozszerzyć `DERIVED_MARGINAL_CENTRES_METRICS` o `shots_for` / `fouls_for` / `offsides_for` po pomiarze tym samym walk-forwardem (to zmienia druk, więc przełącznik i zgoda operatora).
- **Priorytet / nakład:** P2 / S.

#### most_corners, most_corners_1h, most_corners_2h (piłka; „Najwięcej rzutów rożnych”, „Liczba rzutów rożnych - H2H”, „1. połowa - najwięcej rzutów rożnych”)
- **Gdzie liczone:** `market_mapper.py:736-764` (`_MOST_SCOPED`, `_MOST`, `_MOST_H2H`); p = `joint.p_a_greater` / `p_equal` (`derived.py:338-345`). Devig trzech wyborów `devig_many` (`derived.py:397-413`) służy tylko do `market_p`.
- **Model teraz:** różnica dwóch niezależnych (rho -0.145) brzegów. Brak jakiejkolwiek kotwicy (`K_DERIVED_CENTRE` tylko dla handicapu, i to wyłączony w stats_only).
- **Braki:**
  1. To rynek **czystej interakcji** (kto przeważa), a liczony jest z dwóch próbek na różnych przeciwnikach. **[zmierzone]** Kyoto p 0.141 vs rynek 0.721.
  2. Brak różnicy sił (rating gole/strzały) i stanu meczu (faworyt prowadzi i oddaje rożne).
  3. Połowy (1h/2h) dodatkowo bez ratingu: `corners_1h_for` i `corners_2h_for` w `UNRATED_MARKETS` (`football_rating.py:129`, `:131`) tylko dla marginali; derived i tak biorą próbki.
- **[zmierzone]** Dowód linii `most_corners|OVER` przy p ≥ 0.70: 13 linii łącznie, czyli zawsze NO_LINE_EVIDENCE lub poniżej progu. Na 10-13: 87 poniżej progu, 1 NLE.
- **Rozwiązanie:** różnica A-B jako Skellam/NB-różnica z centrami z ratingu przeciwnika (attack_A x defence_B i odwrotnie, już w `RatingBook.expected`), plus term nierówności (różnica ratingu goli) w centrum udziału rożnych. Literatura bazowa: Maher 1982 (atak x obrona, `LITERATURA_2026-10-08.md` #1). Pomiar: walk-forward na historii `/statistics` (rożne ~9 tys. meczów wg `football_rating.py` docstring), log-loss 3-drogowy vs obecny joint i vs baza (udział częstości).
- **Priorytet / nakład:** P2 / M (mało linii przy p ≥ 0.70, więc mało druku nawet po naprawie).

#### most_cards_points, most_shots, most_shots_1h/_2h, most_shots_on_target
- Jak `most_corners`. Kartki: brak sędziego i stanu meczu (przegrywający fauluje). Strzały mają najsilniejszą ujemną zależność surową (-0.30), ale resztową tylko -0.09. **[zmierzone]** 10-13: most_shots_1h/2h 24 + 23 NO_LINE_EVIDENCE (15 meczów w dowodzie).
- **Priorytet / nakład:** P3 / M.

#### handicap_corners, handicap_cards_points, handicap_shots_on_target (piłka; „Rzuty rożne handicap”, „Liczba X - handicap”)
- **Gdzie liczone:** `market_mapper.py:766-785`; p = `joint.p_diff_greater` (`derived.py:347-355`). Kotwica do drabiny `K_DERIVED_CENTRE=30` (`derived.py:121`) wyłączona w stats_only (`derived.py:618`).
- **Model teraz:** jak `most_`. **[zmierzone]** 10-13: na 40 meczach z handicapem 5 bez centrów (surowe próbki). Kyoto -2.5: p 0.060 vs rynek 0.504.
- **Braki:** jak `most_`. Komentarz `derived.py:84-121` pokazuje, że samo „różnica dwóch własnych średnich” ma korelację z realizowanym marginesem +0.137 vs drabina +0.516 (tenis, ale ten sam mechanizm).
- **Rozwiązanie:** jak `most_` (centra z ratingu przeciwnika); nie wracać do kotwicy w cenie (stats_only).
- **[zmierzone]** Dowód `handicap_corners|OVER` p 0.70-0.75: 12/20 (0.60), czyli przecenia.
- **Priorytet / nakład:** P2 / M.

#### Pochodne niemapowane (MAPPABLE, wyłączone): both_over_goals_1h/_2h, both_over_saves(_1h), handicap_corners_1h/_2h, handicap_shots, handicap_shots_1h, both_over_throw_ins, both_over_goal_kicks, both_over_tackles
- **Gdzie:** `market_mapper.classify_mappable_family` (`market_mapper.py:850-940`) za `MAPPABLE_FAMILIES_FROM_UTC=None` (`epochs.py:756`). `market_coverage.md` 10-13: `fb.btts_half` 260, `fb.handicap_corners_half` 16, `fb.both_over_saves` 16, throw_ins / goal_kicks / tackles po 8. `fb.handicap_shots` 8 nie jest w `classify_mappable_family` (grep: `handicap_shots` brak w `market_mapper.py` poza raportem).
- **Braki:** te same co rodziny pełnego meczu. Dodatkowo `AWAITING_OWN_CURVE` (`confidence.py:220`) dla saves / throw_ins / goal_kicks / tackles, a pochodne i tak czytają tylko dowód linii, więc NO_LINE_EVIDENCE na długo.
- **Priorytet / nakład:** P3 / S (włączenie to decyzja operatora po replayu E2E).

#### Propsy zawodników: player_shots_for, player_shots_on_target_for, player_assists_for, player_fouls_for, player_tackles_for, player_offsides_for (player_interceptions_for zmapowane, brak w arkuszu 10-13) („Zawodnik - liczba strzałów / celnych strzałów / asyst / fauli / odbiorów / spalonych”)
- **Gdzie liczone:** próbka `samples.build_player_samples` (`samples.py:1070-1176`, starty od 10-12, `epochs.py:704`). Centrum w `run_sheet.py`: gałąź gracza (`run_sheet.py:988-1029`) nie wypełnia `own_sides`, więc `resolve_prior` jest pomijany (`run_sheet.py:1163`), `get_prior` zwraca None (brak kluczy `player_*` w `config/sofa_league_baselines.json`), a `centre = mean` (`run_sheet.py:1193`). Rating wyłączony (`run_sheet.py:1202`). Rozkład NB dla shots / sot / assists (`engine.py:191-207`), dla pozostałych normalny. Pewność: krzywa `market:<m>|OVER` (`confidence.py:208`, `PLAYER_PROP_MARKETS` czytane tylko z własnego kierunku), staged `.next.json` od 10-12, offset linii, druk tylko przy `one_sided_single` n ≥ 300 (`confidence.py:413-431`).
- **Model teraz:** średnia jego ostatnich startów (w meczach próbki drużyny, do 10) z wariancją próbki.
- **Wejścia:** tylko jego liczby i minuty (minuty tylko jako notka `PLAYER_MINUTES`, `run_sheet.py:1004-1018`).
- **[zmierzone]** 10-13: 6 312 wierszy, centrum = średnia w 100%. Notka: „NO_PRIOR: no baseline for player_assists_for ... centre is the sample's own”. Wydrukowane nogi 10-09..10-13: 6. Dowód linii przy p ≥ 0.70 realizuje poniżej p (np. `player_shots_on_target_for|OVER` 0.70-0.75: 23/37 = 0.62; `player_fouls_for` 0.75-0.80: 116/194 = 0.60).
- **Braki:**
  1. **Brak kurczenia** do roli/pozycji: 10 startów obrońcy z 1 strzałem albo napastnika z 0.3 asysty to surowa średnia. Grep `position` w `players.py` / `samples.py` nic nie zwraca w estymatorze, choć `lineups_json` ma `position` i `substitute` (sprawdzone na rekordzie z bazy).
  2. **Brak przeciwnika:** strzały zawodnika = jego udział x strzały drużyny, a strzały drużyny zależą od obrony rywala (`RatingBook` `shots_for` atak x obrona istnieje). Przykład 10-13: Inter - Club Brugge `player_shots_for` Hugo Vetlesen 0.5 OVER pewność 0.840 (`11_coupon.md:256`) bez korekty za obronę Interu **[podejrzenie co do kierunku]**.
  3. **Brak oczekiwanych minut:** próbka to starty, ale start 60' i 90' liczą się jednakowo. Brak normalizacji per 90 i projekcji minut (zmiana trenera, rotacja w pucharach, `CONGESTED` tylko jako flaga).
  4. **Brak potwierdzenia składu:** zakład obowiązuje tylko przy starcie, ale cena i pewność powstają przed składem. Ryzyko jest asymetryczne: void przy ławce, ale zawodnik wchodzący z ławki z rolą rezerwowego... void, więc OK. Problemem jest **zmiana roli/pozycji** w dniu meczu. `probe_lineup_availability.py` jest „not yet run” (CLAUDE.md), a w kodzie estymatora nie ma `confirmed` (grep: tylko w skrypcie probe).
  5. **Rzuty karne i stałe fragmenty** (wykonawca rożnych / wolnych → strzały, asysty) nie są rozróżniane. Sofascore `/lineups` nie podaje roli przy SFG **[podejrzenie]**. Incydenty mają `situation`/`bodyPart` dla goli (`market_coverage` SRC_INC).
  6. **Krzywe dopasowane na replayu historii** przy tym samym estymatorze, więc każdy z powyższych braków jest „skalibrowany w średniej”, ale nie rozróżnia dobrego od złego 1.20 (AUC 0.787 wg `docs/sofa/evidence/player_starts_2026-10-11.md`). ROI drukowalnych 49 nóg: -10.3% [-27.2; +4.4].
- **Rozwiązanie:** model udziału. λ_gracza = (strzały drużyny z `FootballForecast.centre('shots_for', side)`, czyli z przeciwnikiem) x udział gracza w strzałach drużyny w jego startach (shrink do udziału typowego dla jego pozycji z `lineups_json.position`, hierarchicznie) x (oczekiwane minuty / 90). Literatura: Jensen, McShane, Wyner 2009, „Hierarchical Bayesian Modeling of Hitting Performance in Baseball”, *Bayesian Analysis* 4(4), https://arxiv.org/abs/0902.1360 (kurczenie do kowariantów pozycji i wieku; analogia metodologiczna, nie piłka). Scholtes, Karakuş 2023, „Bayes-xG”, https://arxiv.org/abs/2311.13707 (efekty zawodnika zostają po korekcie pozycji; dotyczy xG, nie liczby strzałów). Miejsce: nowa funkcja w `run_sheet.py` (gałąź `is_player_metric`, 988-1029) i `players.py` (udział z `team_totals`, `players.py:206`, już istnieje). Dane: `sofa_event_stats.lineups_json` (53 685 meczów z składem) + `statistics_json`. Pomiar: replay jak w `player_starts_2026-10-11.md` (492 384 wiersze startowych, kalibracja kubełkowa parzyste/nieparzyste id, log-loss i AUC po kalibracji). Próg: Δlog-loss CI < 0 na ≥ 4 z 6 rynków, wtedy przełącznik w `epochs` i refit krzywych graczy.
- **Nakładanie:** „hierarchical / empirical-Bayes pooling of team and league effects” odrzucone dla **liczników drużyn** (+3.1e-4). Tu kurczy się **zawodnik do pozycji** i dochodzi przeciwnik przez udział. Nowy wymiar, ale operator musi wiedzieć o podobieństwie.
- **Priorytet / nakład:** **P1 / L** (to jedyna rodzina, która dziś drukuje się jako jedno-stronna, z ROI poniżej drużyn).

#### Rynki wyniku (piłka; 1X2, podwójna szansa, DNB, BTTS, „X strzeli gola”, połowy, HT/FT, dokładny wynik, parzystość, przedziały, kombinacje)
- **Gdzie liczone:** nigdzie w pipeline. OFFER zostawia w `unmapped_markets`. Klasyfikacja `bet.sofa.market_coverage` (`fb.result`, `fb.result_half`, `fb.ht_ft`, `fb.side_result`, `fb.result_or`, `fb.btts_combo`, `fb.goals_distribution`, `superbet_combo`). „X strzeli gola” to MAPPABLE (`goals_for` 0.5) za przełącznikiem. Pomiar: `scripts/sofa/measure_football_result_model.py` (walk-forward, NB na centrach ratingu, r ≈ 7, siatka wyników `score_grid` linia 130, `market_probs` linia 143).
- **Model w pomiarze:** niezależne NB goli obu stron na centrach ratingu (`FootballForecast.centre`), baza = częstość ligi.
- **Wyniki C2 (z raportu, nie liczyłem):** DNB -0.0792 log-loss vs baza (~19% wyborów ≥ 0.70), DC -0.0376, 1X2 -0.0658, BTTS +0.0064 (gorzej), parzystość i dokładny wynik nie osiągają 0.70, HT/FT 0.3%. Krzywa z historii przeszacowuje start sezonu o 2.4-4 pp. UNLINKED -6..-8 pp.
- **Braki:**
  1. **Faza sezonu** (krzywa nie wie o sierpniu-wrześniu).
  2. **Siła ligi dla UNLINKED** (puchary międzynarodowe, Kyoto - Ratchaburi).
  3. **Dynamika sił:** stałe ALPHA (`football_rating.py` `ALPHA_BY_METRIC`).
  4. **Składy / absencje** (nic przed meczem).
  5. **Motywacja / stawka:** `bet.sofa.stakes` tylko flaga.
  6. **Kontekst dwumeczu** (`fb.advance`: wynik pierwszego meczu).
  7. **Kombinacje Superbetu** (`superbet_combo` 13 063) wymagają jednego łącznego rozkładu (gole x rożne x kartki) z zależnościami, których nie mamy.
- **Rozwiązanie:**
  - Moduł `football_result.py` obok `joint.py`: siatka wyników z NB na **czystym ratingu** (nie mieszance 0.5, która jest niedopewna, C2). Krzywa per rynek z replayu historii z termem fazy sezonu (kubełek tygodnia sezonu jako klasa krzywej, jak `by_class`). Każda noga dalej przez własne linie Superbetu.
  - Siły dynamiczne: Koopman, Lit, „A Dynamic Bivariate Poisson Model for Analysing and Forecasting Match Results in the English Premier League”, *JRSS A* 178(1), online 2013 (https://api.crossref.org/works/10.1111/rssa.12042). Tu tylko dynamika sił (stan-przestrzeń), bez dwuwymiarowości, która jest odrzucona. Karlis, Ntzoufras 2003, *JRSS D* 52(3) 381-393 (https://api.crossref.org/works/10.1111/1467-9884.00366; otworzyłem tylko metadane) jest odrzucony co do korelacji, ale dotyczy inflacji przekątnej dla remisu, której nie zmierzono.
  - Pomiar: rozszerzyć `measure_football_result_model.py` o (i) term fazy sezonu, (ii) mecze `LINKED_BY_STRENGTH`, (iii) walidację na liniach Superbetu z `unmapped_markets` dni 10-05.. (cena znana, wynik z listingu). Próg: kalibracja |luka| ≤ 2 pp przy n ≥ 300 (PASS `measure_calibration`), potem zgoda operatora na refit.
- **Nakładanie:** Dixon-Coles i bivariate Poisson odrzucone. Proponuję tylko inflację przekątnej jako osobny, niezmierzony test, plus dynamiczne siły, które są nowe (nie są na liście).
- **Priorytet / nakład:** **P1 / L** dla DNB / DC (największa pula linii z umiejętnością), P3 dla BTTS, parzystości, dokładnego wyniku i combo.

### Braki wspólne dla obszaru

1. **Pochodne są „zamrożone” bramką, nie modelem:** brak krzywej (`DERIVED_CURVES_FROM_UTC=None`) plus sportowy efekt projektu 2.437 na kubełku bez klastrów. Nawet linie realizujące 0.85-0.94 nie przejdą 0.70 (`line_evidence.py:300-312`, `437-440`). To naprawa arytmetyki z pomiarem walk-forward (P1/S).
2. **Interakcja stron tylko przez rating i tylko w marginalach, gdy Superbet kwotuje drabinę strony.** Joint jej nie dostaje w ~12% meczów handicapu i we wszystkich `both_over_shots/fouls/offsides` (`epochs.py:215-216`).
3. **Brak stanu meczu i nierówności sił w zależności stron** (jedna stała rho na metrykę).
4. **Brak sędziego** (kartki, faule) mimo `RefereeRecord` w kontrakcie (`contracts.py:94`).
5. **Zawodnik bez przeciwnika, pozycji i minut;** dane do tego leżą w `lineups_json`.
6. **H2H:** `samples.py:970` liczy `is_h2h`, ale w derived i u zawodnika nie ma wagi (grep `h2h` w `derived.py`: brak).
7. **Raport odmów nie rozróżnia rodzin pochodnych** (`refused` liczy tylko powód), więc operator widzi „NO_LINE_EVIDENCE 1078” i nie wie, że w tym jest jego „obie powyżej 2.5 rożnego”.

### Czego nie sprawdziłem

- Nie zmierzyłem ROI ani kalibracji nóg, które dodałby deff = 1 (tylko symulacja `LineEvidence.read` na jednym dniu 10-13 bez innych bramek: kickoff, świeżość ceny, SAMPLE_CROSSES_SEASON). 8 nóg to górna granica.
- Nie sprawdziłem, z jakich estymatorów pochodzą p w kubełkach dowodu (dni 10-05..10-12 mieszają epokę przed i po refitcie 10-09).
- Nie liczyłem rozkładu stron w kubełkach (czy p ≥ 0.75 to głównie linia 0.5/1.5, tanie kursy). Pasma kursu sugerują, że tak (390 z 447 linii p ≥ 0.70 w 1.00-1.30).
- Pokrycie `referee` w bazie, `confirmed` w składach przed meczem (probe nieuruchamiany), rola przy stałych fragmentach w `lineups_json` - nie sprawdzone.
- Wyniki C2 cytuję z `RAPORT_NOC_2026-10-12.md`, nie odtwarzałem ich.
- `leg_relations.py` przejrzałem tylko pod kątem mapowania pochodnych na mechanizm (`leg_relations.py:302-341`). Bez wpływu na p.
- Literatura: dla propsów piłkarskich nie znalazłem recenzowanej pracy o udziale x minutach x przeciwniku. Cytowane źródła to analogie (baseball, xG). Karlis-Ntzoufras 2003: tylko metadane.

# Część 3

## Tenis — audyt rynek po rynku (2026-10-13)

Tylko do odczytu. Liczby oznaczone **[zmierzone]** policzyłem sam z artefaktów
`runs/sofa/2026-10-09..12/{11_coupon,07_settled,05_sheet,02_fixtures}.json` albo
`SELECT` na kopii `data/refit_2026-10-08/sofa_replay.db` (mode=ro); skrypty w
`scratchpad/audit/t3/`. Bootstrap zawsze po meczach (1500–2000 prób, 95%).
**[podejrzenie]** = niezmierzone.

### Podsumowanie

1. **Mecz nie jest modelowany na poziomie punktu/gema tego przeciwnika.** Cały
   rozkład wyniku (gemy, sety, sety per set, tiebreaki) jest czytany z 600
   historycznych meczów o najbliższym *p wygranej meczu*
   (`tennis_rating.py:621` `_window`, `:716` `forecast`). Dwa mecze z tym samym
   p — dwóch serwujących „bombardierów” na hali i dwie returnerki na mączce —
   dostają ten sam rozkład gemów. Siła serwisu/returnu (`servicePointsScored`,
   `receiverPointsScored`, `serviceGamesWon` w `sofa_event_stats`) nie wchodzi
   do żadnej ścieżki wyceny (grep po `src/`: brak; jedynie komentarz
   `market_coverage.py:130`). Powierzchnia wchodzi tylko do p (Elo pół na pół z
   powierzchnią, `:363`), nie do wyboru sąsiadów (komórka = tier × płeć, `:688`).
2. **Rynki per set (największy wolumen drukowany) nie mają przeciwnika w ogóle.**
   `games_set1/2_total`, `games_won_set1/2_for` — 324 z 432 rozliczonych nóg
   tenisowych 10-09..10-12 — są wyceniane z częstości własnej próbki 8–10 meczów
   (`engine.py:42` `EMPIRICAL_FREQUENCY_METRICS`) skurczonej do **globalnej**
   średniej całego tenisa (99% wierszy `games_set*_total` i 78% `games_won_set*_for` ma notę `PRIOR_GLOBAL`, reszta bez priora **[zmierzone]**,
   np. „global games_won_set1_for mean 4.74”). Ten sam estymator na
   `games_won_for` przegrał z odczytem z sąsiadów ratingu o −0,0716 log-loss
   (`docs/sofa/evidence/tennis_rating_prices_2026-10-07.md`), a sąsiedzi umieją
   już czytać rynki per set (`tennis_rating.py:130` `_READABLE_MARKETS`) — po
   prostu nikt tego nie zmierzył i nie przełączył (`RATING_PRICED_MARKETS`, `:140`).
3. **`games_won_for` UNDER −13,4 pp — to jest rynek „czy będzie długi trzeci set”.**
   99 drukowanych nóg (83 mecze), 76 na linii 13,5: zrealizowane 0,657, pewność
   0,741, model 0,803, cena po devigu 0,758, implied 0,791 → zrealizowane − implied
   **−13,4 pp [−24,6; −2,5]**, zrealizowane − pewność −8,4 pp [−19,4; +2,2]
   **[zmierzone]**. 33 z 34 przegranych to mecze trzysetowe (jedna bez danych);
   te mecze poszły w 3 sety w 47,5% (38/80) przy P(3 sety) ratingu 0,311 **[zmierzone]**.
   Na historii ta sama krzywa jest skalibrowana (replay: linia 13,5, p 0,74–0,86,
   n = 41 793: deklarowane 0,791, zrealizowane 0,783 **[zmierzone]**). Przyczyny w
   sekcji `games_won_for`.
4. **Trzysetówki ponad model i cenę w tym oknie, skupione na mączce:** wszystkie
   279 meczów z wierszem `sets_total 2,5` (10-09..12): P(3) ratingu 0,319, rynku
   0,315, zrealizowane 0,373 (+5,4 pp [0,0; +10,9]); mączka (n = 130) **+12,4 pp
   [+4,3; +21,7]**, reszta −0,8 pp **[zmierzone, 4 dni — może być wariancja; rynek
   pomylił się tak samo]**. Tabela sąsiadów nie zna powierzchni.
5. **Format jest zgadywany, nie czytany.** Best-of-5 nie ma modelu w ogóle
   (`run_sheet.py:812` zwraca `None`; wtedy próbka), a dla ITF sąsiedzi zawierają
   mecze rozstrzygnięte super-tiebreakiem liczonym jako 1 gem (`tennis_rating.py:688`
   wpuszcza je do komórki ITF) niezależnie od tego, czy *ten* turniej go gra.
   Jak Superbet liczy super-tiebreak w gemach — nadal niezweryfikowane
   (`tennis_score.py`, docstring; CLAUDE.md „Open questions”).
6. **Asy / podwójne błędy / „serwisy”:** własna próbka gracza skurczona do
   priora tier × płeć × powierzchnia (`tennis_prior.py:65`), NB. Brak returnu
   przeciwnika (ile asów *oddaje*), brak oczekiwanej liczby gemów serwisowych
   (faworyt 6-2 6-1 serwuje ~8 gemów, w trzysetówce ~15), brak hali. Rynki per set
   i `serve_points_*` kurczą się do globalnej puli.
7. **`games_total`:** 50/50 NB z puli obu próbek (unimodalny) + sąsiedzi
   (`run_sheet.py:1343`); audyt 10-07 zmierzył, że mieszanka nie usuwa +3–4 pp
   OVER na liniach centralnych (rozkład dwumodalny 2 sety / 3 sety). Waga 0,5 była
   mierzona na tabeli łącznej, nie na obecnej tier × płeć.
8. **Rynki wyniku (zwycięzca, zwycięzca seta, wynik w setach, handicap setowy,
   parzystość gemów, tiebreak w secie) są COMPUTABLE z tego, co już jest**
   (`MatchForecast.p_home`, `Outcome.set1/set2/sets`), ale niewycenione —
   ~3 000 wystąpień w rodzinach `tn.*` (jeden dzień, 10-12, `market_coverage.json`)
   **[zmierzone]**; C3 (2026-10-12) pokazał umiejętność p wygranej.
9. **Brak w ogóle (grep: brak):** h2h (w tenisie — `samples.py:970` liczy `is_h2h`,
   ale `deduplicate_observations` w `run_sheet.py:1066` tylko wrzuca go do puli),
   leworęczność, wysokość n.p.m., hala jako osobna klasa (zmierzone ns), runda /
   kwalifikacje, zmęczenie w *rozkładzie gemów* (zmęczenie jest tylko w p:
   `dmin78`, `drest`, `dn7` w `tennis_rating.py:342–388`).

### Mapa obliczeń

```
Sofascore listing (sofa_entity_events kind=last) ──► load_history (tennis_rating.py:~250)
   │                                              (singiel, Ended/Retired, bez egzybicji)
   ▼
RatingBook (Elo 538: K=250/(n+5)^0.4; overall + per powierzchnia; :300-430)
   │  features (:363): lp, lps, dmin78, drest, dn7, dform, dhigh, dtour (+ lp_t od 10-09)
   ▼
calibrated_p per tier ITF/CH/TOUR (config/tennis_rating.json) = p_home   ──► forecast_p
   │                                                                          (match winner — NIE wyceniany)
   ▼
_window: 600 sąsiadów o najbliższym p (komórka tier×płeć ≥1200, inaczej tier, inaczej pula;
         CH/TOUR bez super-tiebreaków)  → Outcome(games_for/against, sets, tiebreaks, set1, set2)
   │
   ├─ games_won_for, handicap_games, most_games (A/B)   = odczyt z sąsiadów   [RATING_PRICED_MARKETS]
   ├─ games_total = 0,5·sąsiedzi + 0,5·NB(próbka puli obu graczy → prior tier×płeć×pow.)
   └─ sets_total, tiebreaks_total, games_set*_total, games_won_set*_for: sąsiedzi tylko jako
      forecast_p (sets_total) albo wcale; p z próbki:
         próbka = ostatnie 10 meczów gracza, ta sama rodzina powierzchni, ten sam best-of (samples.py:341-386)
         _total = pula obu graczy (+h2h zdeduplikowany, bez wagi) ; _for = tylko gracz
         centrum = n/(n+K)·średnia + K/(n+K)·prior   prior: tier×płeć×pow. (6 metryk) albo GLOBAL
         p = częstość empiryczna (sets, gemy per set, games_won_for bez ratingu) | NB (asy, DF, games_total)
             | normal (tiebreaks_total) | joint niezależny ρ=0 (most_/handicap bez ratingu, most_aces...)
   ▼
CONFIDENCE (confidence.py): krzywa historii market|kierunek (by_market_direction; klasy
   tennis_women / tennis_team_cup / women) ← replay calibrate_from_cache tym samym estymatorem
   → min( krzywa + offset line evidence (≤0), cap pasma ceny )      [line_evidence.py]
   → druk: ≥0,70, ×kurs ≥0,90, marża ≤15%, ... ; price_gap tylko adnotacja
```

### Rynek po rynku

#### games_won_for (tenis; „<zawodnik> liczba gemów”)
- **Gdzie liczone:** `tennis_rating.py:540` `MatchForecast.read` (pula
  `neighbours_home/away`, wartość `o.games_for`); włączone w
  `run_sheet.py:1282` (`rating_prices`, `RATING_PRICED_MARKETS` `tennis_rating.py:140`).
  Bez ratingu (gracz < `MIN_RATED`=10, `:87`) — częstość empiryczna własnej próbki
  (`engine.py:42`). Pewność: krzywa `games_won_for|<kierunek>` (+klasa
  `tennis_women`), offset line evidence (na legach: `line_offset` −0,056).
- **Model teraz:** P(gemy gracza > linia) = udział sąsiadów o zbliżonym p
  zwycięstwa, którzy przekroczyli linię.
- **Wejścia:** p meczu (Elo + 7 cech kontekstu), tier × płeć komórki. Nic o
  serwisie/returnie tych dwóch graczy, nic o powierzchni w sąsiadach.
- **Braki:**
  1. Rozkład warunkowany wyłącznie p (`_window`, `tennis_rating.py:621`). Dla
     UNDER 13,5 rynek jest prawie w całości P(trzeci set) × P(gracz ≥14 | 3 sety);
     P(3 sety | p) jest w modelu niezależnych setów funkcją samego p (q z
     p = q²(3−2q), P(3) = 2q(1−q)), więc to nie jest główna luka; luka jest w
     *drugim czynniku*: ile gemów w secie przy danych poziomach utrzymania
     serwisu (tiebreaki 7-6 vs 6-4). To widać w ewaluacji 10-08: korelacja siły
     serwisu (suma s−r) z resztą gemów ponad p Elo 0,11 (n = 10 830) — sygnał jest.
  2. Super-tiebreak ITF: komórka ITF trzyma mecze 1-0 w trzecim secie
     (`tennis_rating.py:688–699`, wykluczone tylko dla CH/TOUR); dla turnieju z
     pełnym trzecim setem zaniża gemy → zawyża UNDER **[podejrzenie, rząd ≤ 2 pp
     w ITF; zmierzone: ITF i CH/TOUR przegrywają UNDER tak samo, 0,656 vs 0,658,
     więc nie to jest główną przyczyną]**.
  3. Brak powierzchni w sąsiadach (komórka tier × płeć; wariant tier × powierzchnia
     zmierzony 10-08: −29,2e-4 vs −31,5e-4 sam tier, czyli bez zysku na historii).
- **Diagnoza −13,4 pp (UNDER, 10-09..10-12):**
  - **[zmierzone]** 33/34 przegranych w meczach trzysetowych; udział trzysetówek
    47,5% przy P(3) modelu 0,311; po podłożu: mączka 48 nóg, zrealizowane 0,563;
    twarda 47 nóg, 0,745 (n małe — **podejrzenie**).
  - **[zmierzone]** Na historii krzywa jest skalibrowana na tej linii (replay
    13,5: 0,791 → 0,783; 14,5: 0,805 → 0,797). Czyli to nie jest stały błąd
    estymatora, tylko (a) okres z nadwyżką trzysetówek, którą cena też przeoczyła
    (P(3) rynku 0,315), (b) selekcja: drukujemy tam, gdzie model jest 4,5 pp nad
    ceną po devigu (0,803 vs 0,758) — w całym arkuszu rozliczone wiersze
    `games_won_for UNDER` z p ≥ 0,70 i p − cena ≥ 0,05 realizują 0,607 przy p
    0,777 i cenie 0,687 (n = 135) **[zmierzone]** — znany antysygnał niezgody z
    ceną, (c) offset line evidence dopasowany na wierszach starego estymatora
    (CLAUDE.md: „first mornings' offsets are noisy for the repriced families”).
  - Kandydaci strukturalni (do zmierzenia, nie stwierdzeni): brak serwisu/returnu
    w rozkładzie gemów (pkt 1), brak powierzchni w sąsiadach (mączka), ITF
    super-tiebreak (pkt 2). Uwaga: przedział dla „zrealizowane − pewność” obejmuje
    zero; „zrealizowane − cena” nie.
- **Rozwiązanie:** (i) dwuwymiarowy klucz sąsiadów: p meczu **i** indeks dominacji
  serwisu meczu D = (s_A − r_B) + (s_B − r_A), z ocen punktowych serwis/return
  dopasowanych online (SGD z `measure_tennis_calibration.py` `tune_serve`,
  `:1781`; wzór P(punkt | i serwuje do j) = σ(μ + s_i − r_j) jak Barnett & Clarke
  2005 / Klaassen & Magnus 2003). Sąsiedzi = 600 najbliższych w metryce
  (Δp/σ_p)² + (ΔD/σ_D)²; rozkład dalej empiryczny (bez założenia iid, które w
  10-08 przegrało jako zastępstwo). Miejsce: `TennisRatingModel.forecast` /
  `_window` (`tennis_rating.py:621,716`), `Outcome` dostaje pole D, `AsOfRating._add`
  liczy D sprzed meczu. Dane: `sofa_event_stats.statistics_json`
  (`servicePointsScored`, `receiverPointsScored`; 71 652 meczów z pełną statystyką
  wg ewaluacji 10-08). (ii) Kalibracja P(3 sety) per tier × płeć × powierzchnia
  na historii (czy mączka ma systematycznie więcej trzysetówek przy tym samym p).
  - **Pomiar:** walk-forward jak `tennis_rating_prices_2026-10-07.md` (cięcia 03-01
    i 06-15), log-loss per rodzina (`games_won_for`, `games_total`, `tiebreaks_total`,
    `games_set*_total`), bootstrap po meczach, **przedrejestrowane**: jedna metryka
    odległości, jedna waga; próg: CI < 0 w obu oknach i po rekalibracji koszykowej
    (jak 10-08 dla tabeli per tier). Do tego linia 12,5–14,5 osobno (tam drukujemy).
    Potem przełącznik `epochs.TENNIS_MATCHUP_TABLE_FROM_UTC`, refit krzywych na
    kopii, zgoda operatora.
- **Nakładanie się z „zmierzone i odrzucone”:** TAK częściowo — „a serve/return
  tennis model” (2026-10-08). Odrzucono model punktowy KM jako *zastępstwo*
  rozkładu (gorszy o 0,01–0,07 nat) i jego domieszkę 50/50 (zysk = kasowanie
  obciążenia tabeli); domieszka 0,25 na tabeli tier × płeć: −15,6e-4 INCONCLUSIVE
  (waga po fakcie). **Nowe:** ta propozycja nie zastępuje rozkładu modelem iid
  ani go nie miesza — używa siły serwisu tylko jako *drugiej współrzędnej doboru
  sąsiadów* w empirycznej tabeli (rozkład zostaje empiryczny i skalibrowany) i
  celuje w zmierzoną resztę (korelacja 0,11). Wymaga nowego, zarejestrowanego testu;
  bez niego nie proponować wdrożenia.
- **Priorytet / nakład:** P1 / M.

#### handicap_games (tenis; „Handicap gemy: X (−4.5)”)
- **Gdzie liczone:** `tennis_rating.py:540` (`value = games_for − games_against`,
  wygrana gdy > −linia); przez `derived.py:667` (`rating_p`). Bez ratingu —
  joint dwóch próbek, ρ = 0 („DERIVED: joint of both sides, rho=+0.000
  (UNMEASURED, independent)” w arkuszu 10-12 **[zmierzone]**), `K_DERIVED_CENTRE`
  `derived.py:121`.
- **Model teraz / wejścia:** jak `games_won_for` (marża z sąsiadów o tym samym p).
- **Braki:** 1) marża przy danym p zależy od tego, czy sety są 6-2 czy 7-6 —
  poziom utrzymań (grep `serviceGamesWon` w ścieżce: brak); 2) ścieżka bez ratingu:
  różnica dwóch średnich z różnych przeciwników, korelacja z wynikiem 0,137
  (komentarz `derived.py:93–104`) — praktycznie bez informacji; w oknie 10-09..12
  żadna taka noga nie wydrukowała się **[zmierzone]**, ale nic tego nie blokuje.
- **Rozwiązanie:** klucz 2D jak wyżej; ścieżka bez ratingu → `NO_LINE_EVIDENCE`-
  podobna odmowa albo odczyt z tabeli tier × płeć przy p = 0,5 ± (brak informacji)
  — zmierzyć log-loss ścieżki joint vs „nie wyceniać” na replayu wierszy z
  `rated < 10`.
- **Nakładanie się:** jak wyżej (serve/return). Ścieżka bez ratingu — nowe.
- **Priorytet / nakład:** P2 / S (odmowa ścieżki bez ratingu), P1 razem z kluczem 2D.

#### most_games i jego remis (tenis; „Najwięcej gemów”)
- **Gdzie liczone:** A/B `tennis_rating.py:540` (marża > 0); remis `:550`
  (udział sąsiadów z równą liczbą gemów) — ale remis nie jest w
  `RATING_PRICED_MARKETS`, więc w stats-only idzie z jointu próbek
  (`derived.py:667`, komentarz „draw of most_games was not measured and stays on
  the sample”, `tennis_rating.py:138–139`).
- **Braki:** remis z niezależnego jointu dwóch próbek (ρ = 0) przy rynku, na którym
  równość gemów powstaje tylko przy określonych układach setów (np. 6-4 4-6 bez
  trzeciego seta nie istnieje w bo3; równość wymaga trzysetówki z konkretną
  różnicą) — gładki joint dwóch niezależnych średnich to model złej postaci;
  A/B jak handicap.
- **Rozwiązanie:** remis z sąsiadów (`read` już to liczy) — pomiar jak
  `tennis_rating_prices_2026-10-07.md` (tam remis wprost pominięto).
- **Nakładanie się:** brak.
- **Priorytet / nakład:** P3 / S.

#### games_total (tenis; „Liczba gemów”)
- **Gdzie liczone:** `run_sheet.py:1282–1284` (rating → `p_rating_gt`),
  `:1343` mieszanka 0,5 (`W_GAMES_TOTAL_RATING`, `tennis_rating.py:143`) z NB
  (`engine.py:162` w `NEGATIVE_BINOMIAL_METRICS`, `sheet_count_p_raw`).
  Próbka: pula obu graczy + h2h (`run_sheet.py:1066`), centrum skurczone do
  `tier_prior` (`run_sheet.py:1150`, `tennis_prior.py:65`).
- **Model teraz:** pół empirycznego rozkładu sąsiadów, pół NB wokół (X̄+Ȳ)/2.
- **Wejścia:** p meczu, tier × płeć (sąsiedzi), tier × płeć × powierzchnia (prior),
  własne mecze obu graczy na tej powierzchni (bez przeciwników tych meczów).
- **Braki:**
  1. NB jest unimodalny, games_total w bo3 dwumodalny; audyt 10-07: OVER zawyżony
     o 4–5 pp, mieszanka zostawia +3–4 pp na liniach centralnych
     (`tennis_rating_prices_2026-10-07.md`).
  2. Pula obu próbek nie wie, z kim grali (pół próbki gracza A to mecze z
     przeciwnikami innymi niż B) — „pooled estimator targets wrong quantity”.
  3. Waga 0,5 zmierzona na tabeli łącznej; od 10-09 tabela tier × płeć, która
     sama zdejmuje obciążenie (−81e-4 log-loss) — waga nie była re-mierzona
     (grep w evidence: brak pomiaru mieszanki NB na tabeli scoped).
  4. Brak serwisu/returnu w sąsiadach (jak wyżej).
- **Rozwiązanie:** (a) re-pomiar `W_GAMES_TOTAL_RATING` ∈ {0,5; 0,75; 1,0} na
  tabeli tier × płeć (skrypt `tennis_rating_prices` walk-forward), (b) klucz 2D.
  W tenisie p(punkt na serwisie) obu graczy wyznacza rozkład gemów
  (Newton & Keller 2005; Newton & Aslam 2009 — model łańcucha Markowa
  punkt→gem→set→mecz z p serwisu i returnu każdego gracza, JQAS 5(3),
  https://sites.usc.edu/newtonlab/files/2020/04/JQA2009.pdf; O'Malley 2008,
  formuły gemu/tiebreaka/seta przy iid, https://hcp.hms.harvard.edu/publication/probability-formulas-and-statistical-analysis-tennis).
- **Nakładanie się:** serve/return jako zastępstwo — odrzucone; re-pomiar wagi — nowe.
- **Priorytet / nakład:** P2 / S (waga), P1 / M (klucz 2D).

#### sets_total (tenis; „Liczba setów”; + „Zostanie rozegrany 3. set” — MAPPABLE, wyłączone)
- **Gdzie liczone:** p z częstości próbki puli obu graczy (`engine.py:42`),
  centrum do priora tier (`tennis_prior.py:65`). Rating tylko jako `forecast_p`
  (`RATED_MARKETS`, `tennis_rating.py:127`; w stats-only `p_rating = None`,
  `run_sheet.py:1285–1289`). „Zostanie rozegrany 3. set” = `sets_total 2,5`,
  `market_coverage.py:389`, za `MAPPABLE_FAMILIES_FROM_UTC` (None).
- **Braki:**
  1. Próbka 10+10 meczów różnych przeciwników mówi „jak często gracz gra trzy
     sety”, nie „jak często ta para”: P(3 sety) zależy od różnicy sił (q).
     Rating to wie; na 5 dniach 2026-09 rating + cena biły próbkę + cenę
     (Brier 0,2268 vs 0,2309, komentarz `tennis_rating.py:120–126`), ale nigdy nie
     zmierzono „rating vs próbka” w stats-only i nie przełączono.
  2. Powierzchnia: **[zmierzone]** w 10-09..12 mączka +12,4 pp trzysetówek ponad
     model (i ponad cenę).
- **Rozwiązanie:** dodać `sets_total` (i pochodną „3. set rozegrany”) do pomiaru
  „rating vs próbka” (walk-forward, jak 10-07), a P(3 | p) skalibrować per
  tier × płeć × powierzchnia (sprawdzić, czy mączka przesuwa P(3) przy stałym p).
- **Nakładanie się:** „surface-hierarchy” odrzucono dla p *wygranej*; kalibracja
  P(3 setów) per powierzchnia przy danym p — nie była mierzona.
- **Priorytet / nakład:** P1 / S.

#### games_set1_total, games_set2_total (tenis; „1. set - liczba gemów”)
- **Gdzie liczone:** częstość empiryczna (`engine.py:42`, uzasadnienie
  „6,7,8,9,10,12,13, nigdy 11”), pula obu graczy, prior GLOBAL (99% wierszy
  10-09..12 **[zmierzone]**: 6 146 / 6 212 wierszy). Krzywe własne
  (`TENNIS_SET_GAMES`, `confidence.py:276`).
- **Model teraz / wejścia:** własne sety obu graczy z różnymi przeciwnikami;
  prior to średnia całego tenisa (kobiety + mężczyźni, ITF + TOUR).
- **Braki:** 1) brak przeciwnika i ratingu (grep: rating nie jest wołany dla
  tych rynków — `RATING_PRICED_MARKETS` `tennis_rating.py:140`); 2) globalny prior
  (to samo, co `tennis_prior.py` naprawił dla 6 metryk; per-set wprost „not
  measured”, `tennis_prior.py:60–64`); 3) poziom utrzymań serwisu (tiebreak 7-6 =
  13 gemów) — klucz 2D. **[zmierzone]** drukowane 207 nóg / 94 mecze:
  zrealizowane − pewność −2,1 pp [−7,8; +3,8], − implied −5,1 pp [−10,8; +0,7];
  `games_set1_total UNDER` 64 nogi 0,703 vs 0,781.
- **Rozwiązanie:** odczyt z sąsiadów (`Outcome.set1/set2`, `read` już to robi
  `tennis_rating.py:574–577`). Pomiar: walk-forward identyczny z 10-07 (rating vs
  próbka, log-loss, bootstrap po meczach, oba okna); przełącznik = rozszerzenie
  `RATING_PRICED_MARKETS` za nowym epochem, refit krzywych tych rynków w replayu
  (`calibrate_from_cache.py`), odświeżenie line evidence.
- **Nakładanie się:** brak (to ten sam ruch, który 10-07 wdrożono dla `games_won_for`).
- **Priorytet / nakład:** **P1 / S–M** (największy wolumen drukowany).

#### games_won_set1_for, games_won_set2_for, games_won_set3_for (tenis; „1. set - <zawodnik> liczba gemów”)
- **Gdzie liczone:** jak wyżej, ale tylko próbka gracza (`metrics.py` F54,
  `"games_from_listing"`), prior GLOBAL (6 198 / 7 902 wierszy, 78%) albo bez priora
  (~1 700 wierszy) **[zmierzone]**.
- **Braki:** to rynek „czy gracz wygra seta / jak blisko” — w całości funkcja
  różnicy sił, której próbka nie ma. **[zmierzone]** drukowane 117 nóg / 67 meczów:
  zrealizowane − pewność −6,1 pp [−15,5; +1,9]; `games_won_set1_for OVER` 35 nóg
  0,629 vs 0,729.
- **Rozwiązanie:** odczyt z sąsiadów (`o.set1[0]`, `o.set2[0]` — już w `read`);
  set 3 wymaga warunkowania na 3 sety (void, gdy nierozegrany) — `Outcome` trzeba
  rozszerzyć o set 3. Pomiar jak wyżej.
- **Nakładanie się:** brak.
- **Priorytet / nakład:** **P1 / S–M**.

#### handicap_games_set1/2 (tenis; „1. set - handicap gemy”) — MAPPABLE, wyłączone
- **Gdzie:** `market_mapper.py:830–924` (`_HANDICAP_SCOPED`), za
  `MAPPABLE_FAMILIES_FROM_UTC`; mapowane na `games_won_set*_for` (odczyt marży
  seta wymaga obu stron — z próbki niewyliczalne bez jointu).
- **Rozwiązanie:** z sąsiadów: `o.set1[0] − o.set1[1]`. Bez sąsiadów — nie wyceniać.
- **Priorytet / nakład:** P2 / S (po P1 dla per-set).

#### tiebreaks_total (tenis; „Liczba tiebreaków”)
- **Gdzie liczone:** normal bez podłogi (`engine.py:400` `NORMAL_NON_COUNT_METRICS`),
  pula obu próbek, prior GLOBAL (218 wierszy **[zmierzone]**).
- **Braki:** tiebreak = oba utrzymania wysokie — wprost funkcja s_A − r_B i s_B − r_A
  (O'Malley 2008; Newton & Aslam 2009), a próbka to „ile tiebreaków grał każdy z
  nich”. Rating przegrał na 52 wierszach (Brier 0,2310 vs 0,2238,
  `tennis_rating.py:120–126`) — za mało, by cokolwiek rozstrzygnąć.
- **Rozwiązanie:** klucz 2D (sąsiedzi o podobnym D mają podobny odsetek 6-6);
  pomiar walk-forward jak wyżej.
- **Nakładanie się:** serve/return (patrz `games_won_for`).
- **Priorytet / nakład:** P2 / M.

#### aces_for, aces_total, aces_set1/2_for, aces_set1/2_total (tenis; „<zawodnik> liczba asów”)
- **Gdzie liczone:** NB (`engine.py:148`), próbka własna (_for) / pula (_total),
  prior tier × płeć × powierzchnia dla meczowych (`tennis_prior.py:65`), GLOBAL dla
  per set; `TENNIS_DISPERSION_SCALED_METRICS` (`engine.py:349`) czeka na
  `MODEL_FIXES_FROM_UTC` (`epochs.py:171`, None) — zmierzone −0,0139 log-loss
  dla `aces_for` i nadal wyłączone.
- **Braki:**
  1. Return przeciwnika: asy zależą silnie od odbierającego (grep po ścieżce:
     brak „aces conceded”). Barnett & Clarke 2005 łączą statystyki serwującego i
     odbierającego względem średniej (IMA J. Management Math. 16(2) 113–120,
     https://vuir.vu.edu.au/8502/ — **opis z repozytorium/streszczenia, pełnego
     tekstu nie otwarłem**).
  2. Ekspozycja: liczba gemów serwisowych gracza (zależna od p i długości meczu)
     — próbka gracza miesza mecze 6-1 6-1 z trzysetówkami.
  3. Hala (Sofascore „Hardcourt indoor”) — `surface_family` łączy z twardą
     (`tennis_rating.py:168`), a asy na hali są wyższe **[podejrzenie]**.
  4. Dyspersja tenisowa wyłączona (`MODEL_FIXES_FROM_UTC`).
- **Rozwiązanie:** asy = (asy na gem serwisowy gracza × współczynnik oddawania
  asów przeciwnika / średnia tier × płeć × pow.) × E[gemy serwisowe | sąsiedzi]
  (E z tej samej tabeli sąsiadów: `games_for + games_against` / 2 ± kto serwuje).
  Miejsce: nowa funkcja w `tennis_prior.py` + `run_sheet.py` (gałąź centrum,
  `:1140–1191`). Dane: `sofa_event_stats` (asy per strona, mecze z listingu).
  Pomiar: MAE i log-loss NB na liniach 2,5–9,5 vs obecne, walk-forward, bootstrap
  po meczach, próg CI < 0 w obu oknach. Osobno włączenie `MODEL_FIXES` (już zmierzone).
- **Nakładanie się:** brak (odrzucony serve/return dotyczył gemów/wyniku, nie asów).
- **Priorytet / nakład:** P2 / M (mało drukuje: 2 nogi w 4 dni).

#### double_faults_* (tenis; „liczba podwójnych błędów”)
- **Gdzie / model:** jak asy (NB, prior tier dla meczowych, GLOBAL per set).
- **Braki:** ekspozycja (gemy serwisowe), presja returnu przeciwnika (słabsza niż
  przy asach **[podejrzenie]**), dyspersja wyłączona.
- **Rozwiązanie:** jak asy, bez członu przeciwnika jako pierwszy krok (najpierw
  ekspozycja). **Priorytet / nakład:** P3 / S.

#### serve_points_* (tenis; „liczba asów + podwójnych błędów”)
- **Gdzie:** `metrics.py` (`aces_plus_double_faults`), normal/NB
  (`serve_points_set2_for` w NB, reszta normal), prior GLOBAL („global
  serve_points_for mean 7.775 (n=302)” w arkuszu 10-12 **[zmierzone]**); brak
  własnej krzywej → `TENNIS_SERVE_POINTS` (`confidence.py:262`) czyta… tylko
  własną krzywą/evidence.
- **Braki / rozwiązanie:** jak asy; prior tier zamiast GLOBAL (rozszerzyć
  `TIER_PRIOR_METRICS` po pomiarze MAE jak w `tennis_prior.py:46–57`).
- **Priorytet / nakład:** P3 / S.

#### most_aces, most_double_faults, most_serve_points (+ set1/set2) (tenis; „Najwięcej asów”)
- **Gdzie:** `derived.py` joint dwóch próbek, ρ = 0 („UNMEASURED, independent”).
- **Braki:** asy obu graczy w jednym meczu są skorelowane (długość meczu,
  powierzchnia, hala) — ρ = 0 wprost nieprawdziwe; brak przeciwnika.
- **Rozwiązanie:** po modelu asów z ekspozycją: wspólna długość meczu z sąsiadów
  daje korelację z konstrukcji. **Priorytet / nakład:** P3 / M.

#### Rynki wyniku, COMPUTABLE niewycenione (Superbet: „Zwycięzca”, „1. set - zwycięzca”, „Dokładny wynik”, „Handicap setowy”, „Dokładna liczba setów”, „Liczba gemów nieparzysta/parzysta”, „Tiebreak w X. secie”, „1. set/mecz”, „Którykolwiek set do zera”)
- **Gdzie:** `market_coverage.py:394–410` (`tn.winner`, `tn.set_winner`,
  `tn.set_score`, `tn.sets`, `tn.games_distribution`, `tn.tiebreak_set`);
  10-12: ~3 000 wystąpień w tych rodzinach (3 001) + 7 670 kombinacji Superbetu
  **[zmierzone, `runs/sofa/2026-10-12/market_coverage.json`]**.
- **Model teraz:** brak. `p_home` istnieje (`tennis_rating.py:716`), sąsiedzi mają
  `set1`, `set2`, `sets`, `tiebreaks` — każdy z tych rynków to zliczenie w `read`
  (zwycięzca seta 1 = `o.set1[0] > o.set1[1]`; wynik 2:0 / 2:1; parzystość
  `games_for+games_against`; tiebreak w secie 1 = `set1 ∈ {(7,6),(6,7)}`).
- **Dowód umiejętności:** C3 (`measure_tennis_outcome_model.py`, RAPORT_NOC_2026-10-12):
  zwycięzca z ratingu −0,1232 log-loss vs baza, kalibracja ±1,3 pp, 45,7% meczów ≥ 0,70.
- **Rozwiązanie:** `read` rozszerzony o te zdarzenia; krzywe z replayu; line evidence
  od zera (`NO_LINE_EVIDENCE` do 50 linii). Pomiar: jak C3, per rynek, osobne krzywe.
- **Nakładanie się:** „blending the price” — nie dotyczy (bez ceny).
- **Priorytet / nakład:** P2 / M (operator już kolejkuje zwycięzcę na refit; set 1 i
  wynik w setach to ten sam mechanizm).

#### NOT_COMPUTABLE (kolejność gemów, punkty w gemie, „kto przełamie N. gem”)
- `market_coverage.py:433–452`; wymaga modelu punktowego iid + kto serwuje
  pierwszy, a cache nie ma point-by-point. To jedyne miejsce, gdzie model
  Klaassena-Magnusa / O'Malleya byłby *jedynym* możliwym estymatorem; odrzucenie
  z 10-08 dotyczy rynków gemów, nie tych. **Priorytet:** P3 / L (bez historii do
  rozliczenia linii nie ma krzywej).

### Braki wspólne dla obszaru

1. **Brak warstwy meczu (matchup) poza p.** Sąsiedzi ratingowi to dobra
   konstrukcja (spójne rynki, dwumodalność z danych), ale jedyną współrzędną jest
   p. Proponowany klucz 2D (p, D) to najmniejsza zmiana, która wnosi serwis/return
   bez modelu iid. Przypomnienie: trzy wcześniejsze modele serwis/return
   (`measure_tennis_serve_model.py` 09-22: Brier 0,2364 vs 0,2397 próbki, przegrywa
   z ceną; `price_tennis_serve_model.py`; KM 10-08) — żaden nie był testowany jako
   warunek doboru sąsiadów.
2. **Rynki per set i trzysetowe na próbce bez przeciwnika** (P1) — najtańszy
   ruch o największym wolumenie; estymator, który już wygrał na `games_won_for`.
3. **Powierzchnia tylko w p, nie w rozkładzie gemów/setów** — mierzona dla
   tabeli (bez zysku na 6 mies.), ale nie dla P(3 setów) per powierzchnia;
   4 dni pokazały +12,4 pp na mączce (do potwierdzenia na historii).
4. **Format:** best-of-5 bez ratingu (`run_sheet.py:812`); ITF super-tiebreak
   w tabeli bez wiedzy o formacie turnieju — wykrywalne z historii turnieju
   (`tennis_score.match_tiebreak_sets` na poprzednich meczach tego
   `uniqueTournament`), bez nowych danych; konwencja Superbetu dla
   super-tiebreaka nieznana (otwarte pytanie operatora).
   Bo5: P(set) q z p meczu bo3 (p = q²(3−2q)), sety z tabeli setów — zmierzyć na
   cache'owanych meczach bo5 (Wielkie Szlemy).
5. **Priory GLOBAL** dla wszystkich metryk spoza 6 z `TIER_PRIOR_METRICS`
   (`tennis_prior.py:65`) — znany defekt naprawiony dla 6 metryk, reszta czeka.
6. **Rzeczy, których nie ma (grep: brak):** h2h (w tenisie zbyt rzadkie i bez
   dowodu w literaturze — P3, nie proponuję), leworęczność (pole `plays` z
   Sofascore nie jest w cache — `sofa_entity` nie ma takiej kolumny; P3,
   wymaga backfillu), wysokość (Bogotá, Quito — P3), runda/kwalifikacje (Elo
   + `dhigh/dtour` częściowo), zmęczenie w rozkładzie gemów (P3; w
   `price_tennis_serve_model.py:30–34` obciążenie 3 dni nie ruszało reszty
   punktów |z| > 2,2). Retirement jest zwrotem (CLAUDE.md, SETTLE) — nie ryzyko p.
7. **`MODEL_FIXES_FROM_UTC` (dyspersja NB tenisa)** zmierzona i wyłączona —
   decyzja operatora przy następnym reficie.

### Czego nie sprawdziłem

- Nie uruchomiłem żadnego wariantu modelu (klucz 2D, sąsiedzi dla per-set, P(3)
  per powierzchnia) — wszystkie zyski tych propozycji są **niezmierzone**.
- Filtr `settled_at >= 2026-04-01` w zapytaniu na replayu może oznaczać czas
  zapisu replayu, nie meczu — traktuję wynik replayu jako „cała historia replayu”.
- Nie zweryfikowałem, czy wiersze `market_p` w `07_settled.json` są po devigu
  (zakładam tak; `implied` liczyłem osobno jako 1/kurs).
- Pełnych tekstów Barnett & Clarke 2005, Klaassen & Magnus 2003 (EJOR 148(2)
  257–267, tylko metadane z wyszukiwarki, repozytorium Tilburga dało 403),
  Knottenbelt i in. 2012 (model wspólnego przeciwnika — tylko opisy z wyników
  wyszukiwania) ani Ingram 2019 (hierarchiczny bayesowski serwis/return z
  powierzchnią — tylko opis podcastu Tennis Abstract) nie przeczytałem; otwarty i
  przeczytany: Newton & Aslam 2009 (PDF), O'Malley 2008 (streszczenie). Kovalchik
  2016 — według `LITERATURA_2026-10-08.md` (#20, otwarte tam).
- Nie mierzyłem efektu hali, wysokości, leworęczności, h2h na żadnych danych.
- Nie sprawdziłem rozliczeń super-tiebreaka u Superbetu ani tego, czy któryś
  drukowany mecz ITF w oknie grał super-tiebreak.
- Okno 10-09..10-12 to 4 dni (432 nogi, 166 meczów) — wszystkie liczby live mają
  szerokie przedziały; jedynie „zrealizowane − implied” dla `games_won_for UNDER`
  i całego tenisu wykluczają zero.

# Część 4

## Hokej i koszykówka — audyt rynek po rynku (2026-10-13)

Tryb: tylko odczyt. Nie zmieniono żadnego pliku repozytorium, nie uruchomiono potoku, mostka ani Superbetu.
Pomiary własne (skrypty w scratchpadzie `audit/hb/*.py`) czytają wyłącznie:
`data/line_evidence/rows_before_2026-10-13/{basketball,hockey}_{history_holdout,superbet_settled}.jsonl`
(wiersze, które poranne `refresh_line_evidence.py` już wyliczyło), `runs/sofa/shadow/<sport>/<d>/settled.json`,
`runs/sofa/<d>/08_confidence_sports.json`, oraz jeden zbudowany w pamięci model
(`score_model.build_model` na `data/sofa.db` w trybie `mode=ro`, cięcie 2026-10-10 12:00Z).
"ZMIERZONE" = liczba z tych plików, z liczbą linii / meczów i dniami. "PODEJRZENIE" = nie zmierzone.

Okna: `superbet_settled` = rozliczone linie Superbetu 2026-09-29..2026-10-12 (koszykówka 81 011 linii /
1 253 mecze, hokej 42 954 linie); `history_holdout` = mecze historii 2026-09-13..2026-10-13 (koszykówka
2 080 meczów, hokej ~2 140), synthetic lines w kwantylach własnej symulacji modelu.

### Podsumowanie (największe braki)

1. **BŁĄD POPRAWNOŚCI (P1, S): mecz w rozgrywkach bez własnej stawki ligi liczony od globalnej średniej
   wszystkich lig.** `football_rating.RatingBook.league_rates` (`src/bet/sofa/football_rating.py:770-779`)
   przy < `MIN_LEAGUE_MATCHES`=30 meczach rozgrywek bierze `global_league` (EWMA wszystkich lig męskich).
   NBA Preseason jest wyłączone z historii jako sparing (`score_model._is_friendly`, `score_model.py:96-100`),
   więc nie ma własnej stawki; ZMIERZONE (model as-of 2026-10-10): global `bb_reg_for` = 82,8 / 81,8 pkt na
   stronę, NBA (id 132) = 118,1 / 112,0. Mecz NBA przedsezonowy jest centrowany na ~165 pkt dla pary o przeciętnej sile (Raptors–Clippers as-of 10-10: 154,7 pkt) zamiast ~230.
   Na 18 głównych liniach OVER totalu NBA Preseason (fair 0,40-0,60) model różni się od ceny średnio o
   **−0,50**, Brier 0,333 vs 0,25 monety (weryfikacja r1; audytor: 34 linie, −0,323, 0,312). Wydrukowana noga 2026-10-10 Toronto–Clippers
   `total UNDER 222.5` miała `forecast_p` **0,9998** (pewność 0,857 po offsecie) — wygrała przypadkiem
   (220 pkt). Żaden etap nie odrzuca meczu sparingowego/przedsezonowego na żywo (grep: brak `friendly` /
   `preseason` w `scripts/sofa/run_sport_confidence.py`). Ten sam mechanizm dotyczy pucharów i nowych
   rozgrywek z < 30 meczami w cache (PODEJRZENIE co do skali).
2. **Główna przyczyna zawyżenia koszykówki: krzywa historii jest dopasowana na innej populacji linii
   niż ta, którą drukujemy.** `sport_confidence.synthetic_lines` (`sport_confidence.py:594-636`) stawia
   linie w kwantylach *własnej* symulacji modelu (`LINE_QUANTILES`, `:221`), niezależnie od prawdy;
   linia Superbetu stoi tam, gdzie rynek widzi medianę. Noga z p ≈ 0,75 na linii Superbetu to linia, przy
   której model *nie zgadza się* z rynkiem. ZMIERZONE (koszykówka, linie z odczytem krzywej ≥ 0,70: 3 625
   linii / 665 meczów): krzywa 0,760, realizacja **0,633**, cena bez marży **0,628** — realizacja = cena.
   Luka rośnie monotonicznie z rozjazdem `p − fair` (weryfikacja r1, 3 625 linii / 665 meczów): < −0,05 → **+13,6 pp**; 0..0,05 → −9,1; 0,10..0,15 →
   −14,1; 0,15..0,25 → −17,2; ≥ 0,25 → **−26,0 pp** (audytor na innej, nieodtworzonej populacji 6 602 / 801: +8,5 / −12,1 / −19,4 / −23,5 / −28,7 [−34,8; −21,1], bootstrap po meczach). Hokej ma ten
   sam kierunek gradientu (audytor, 6 893 / 962: +6,9 → −18,9 pp; nieodtworzone), ale model rzadziej odjeżdża od ceny, więc łącznie −1,3 pp (`sport_printable.hockey`: 6 105 linii / 886 meczów).
3. **Model kosza nie ma informacji ponad cenę na liniach głównych.** ZMIERZONE: linie z fair 0,45-0,55,
   Brier modelu — total 753: **0,2593**, handicap 768: 0,2636, team totals 0,2578-0,2597 — gorzej niż
   moneta (0,25); średni |p − fair| 0,087-0,104. Hokej: total 623 0,2495, team totals / handicap
   0,2546-0,2607. To nie jest argument za mieszaniem z ceną (odrzucone), tylko dowód, że centrum totalu /
   handicapu kosza nie widzi tego, co widzi rynek: tempa (posiadań), składów/odpoczynku gwiazd, B2B, fazy
   sezonu.
4. **Na historii symulacja kosza jest za szeroka, więc krzywa podnosi p — czy to podbicie dokłada się do
   zawyżenia na liniach rynku, jest niepotwierdzone (zob. niżej).** ZMIERZONE (`history_holdout`): `total|OVER` p 0,79 → realizacja 0,854
   (+6,4 pp), `total|UNDER` +6,5..+6,9 pp, `team_total|UNDER` +4..+5 pp, handicap +1..+1,4 pp. Na liniach
   Superbetu audytor podał średnie surowe p 0,701 → odczyt krzywej 0,755 (+5,4 pp); weryfikacja r1 (krzywe `.next`, 3 625 linii z odczytem ≥ 0,70) tego nie odtwarza: surowe 0,763 → krzywa 0,760, więc na liniach rynku podbicia nie widać. Hokej: brak takiego przesunięcia.
5. **Remis po regulaminie w koszu niedoszacowany ~1,8×** (ZMIERZONE, holdout 2 080 meczów: p 0,0220,
   realizacja 0,0399). Zgodne z Ely (Cheap Talk 2009) (6,26% vs 2,29% w NBA). Dotyka `result_1x2|DRAW`, zwycięzcy
   z dogrywką, handicapów ±0,5..±3,5 i totali w meczach z dogrywką. Plus drobny błąd: dogrywka NBA
   skalowana 5/10 kwarty zamiast 5/12 (`score_model.py:468`, `len(mu1)` jest zawsze 4).
6. **Brak tempa / posiadań i czterech czynników mimo danych w cache.** `sofa_event_stats.statistics_json`
   ma dla ~34 tys. meczów kosza `freeThrowsScored` (trafione/oddane), `fieldGoalsScored`,
   `offensiveRebounds`, `turnovers` — wystarcza do posiadań Olivera; `score_model.py` czyta tylko listingi
   (grep `statistics_json`/`sofa_event_stats` w `score_model.py`, `sport_confidence.py`,
   `run_sport_confidence.py`: 0 trafień). Hokej: ~3–7 tys. meczów z `Shots`, `emptyNetGoals`,
   `PowerPlayPercentage`, ~3 tys. z `savePercentage` bramkarzy — nieużywane w modelu wyniku.
7. **Brak kontekstu meczu w centrum:** odpoczynek / B2B (`b2b_delta`=0, `score_model.py:218`, zmierzone
   i wyłączone), podróż, bramkarz startowy, składy, faza sezonu (początek sezonu poza `bb_fresh_mult`),
   h2h (grep `h2h`: brak), garbage time / minuty gwiazd w propsach i handicapach.
8. **Propsy zawodników** (`player_model.py`): minuty × stawka/s, bez rywala, tempa, spodziewanego
   marginesu (garbage time), roli/startera, B2B; prawie wszystkie klucze kosza są `NO_LINE_EVIDENCE`
   (≤ 50 meczów linii), drukuje się tylko hokejowe `player_pp_points` UNDER (18 nóg 10-05..10-13).
9. **Niezmapowane:** totale / handicapy NHL "z dogrywką i rzutami karnymi" (`hk.ot_so_scope`),
   podwójna szansa (hokej, kosz), statystyki drużyny kosza (`bb.team_box`, 196 wystąpień na 23 meczach
   10-13), kamienie milowe zawodnika (`bb.player_milestone`, 64), double-double, kolejność punktów/goli.

### Mapa obliczeń

```
Listingi Sofascore (sofa_entity_events kind=last + listing_index)          [jedyne wejście modelu wyniku]
  └─ score_model.parse_event (score_model.py:103)  regulamin: hk_reg_for / bb_reg_for = suma okresów
       (sparingi / preseason / OT poza ratingiem)
  └─ RatingBook (football_rating.py)  atak × obrona na PUNKTY/GOLE regulaminu, EWMA alpha 0.02 hk / 0.06 bb
       league_rates(comp) ── <30 meczów ──> global_league  (BŁĄD 1)
  └─ ScoreModel.expected (score_model.py:330)  E = stawka_ligi(dom/wyjazd) × att × def  (× f siły ligi)
       × udziały okresów (JEDNE dla wszystkich lig, :587-598)
  └─ simulate (score_model.py:363), 4000 gier
       hokej: Poisson/okres, +empty-net 0.2 / 6v5 0.05 przy prowadzeniu 1-2 (:428-434), OT: moneta/2 (:442-447)
       kosz:  normalna/kwarta, szok gry g=1.26, drużyny u=0, kwarty e=5.22 (fit momentów, :614-647)
              × bb_fresh_mult 1.085 / 1.026 (≤2 / 3..9 gier w 120 dni), OT gauss (:467-473)
  └─ line_probability (score_model.py:543) = shadow.actual_value/grade  (zakres regulamin/OT jak rozliczenie)
                    │ forecast_p
                    ▼
Pewność (run_sport_confidence.py → 08_confidence_sports.json)
  krzywa: config/sofa_sport_confidence_calibration(.next).json  klucz family|side, kubełki p
     dopasowana na walk_forward_rows (sport_confidence.py:681): linie SYNTETYCZNE w kwantylach modelu (BRAK 2)
  line_evidence (line_evidence.py:284 read): offset klucza / sportu (≤0) + cap pasma ceny (1.30/1.60/2.20)
     z rozliczonych linii Superbetu; design_effect kosz 5.72, hokej 1.84
  propsy: p = player_model (player_model.jsonl SHADOW) → tylko line evidence (brak krzywej historii)
```

### Rynek po rynku

#### Wspólny rdzeń hokeja: `total` 623, `team_total` 658/652, `handicap` 604, `winner` 630, `result_1x2` 640 (hokej; "Liczba goli", "… - liczba goli", "Handicap", "Zwycięzca meczu (z dogrywką i karnymi)", "Mecz 1X2")

- Gdzie liczone: `score_model._hockey` (`src/bet/sofa/score_model.py:410-447`), centrum
  `ScoreModel.expected` (`:330-361`) z `RatingBook.expected` (`football_rating.py:781-794`); p:
  `line_probability` (`score_model.py:543-567`). Pewność: krzywa `hockey:<family>|<side>` z
  `config/sofa_sport_confidence_calibration*.json` + `line_evidence.read` (`line_evidence.py:284`).
- Model teraz: gole regulaminu na drużynę = stawka ligi (dom/wyjazd) × atak_A × obrona_B (multiplikatywny
  Maher, EWMA α 0,02, `SCORE_ALPHA`, `score_model.py:92`), podział na tercje udziałami z całej historii
  (`:587-598`), Poisson na tercję, efekt pustej bramki przy prowadzeniu 1-2 (`:428-434`), dogrywka/karne:
  zwycięzca z proporcji stawek ściągniętej w połowie do monety (`hk_ot_strength` 0,5, `:233`, `:442-447`).
- Wejścia: tylko wynik po tercjach z listingów; liga (stawka dom/wyjazd), siła ligi przy parach
  nielinkowanych (`CROSS_RATIO_POWER` 0,6). Nic więcej.
- Braki:
  1. Bramkarz — który startuje i jego save% (MoneyPuck: bramkarz 29% wagi modelu przedmeczowego).
     grep `goalie|goaltend` w `score_model.py`/`sport_confidence.py`: brak. Dane: `lineups_json` z
     `savePercentage` dla ~2 963 meczów hokeja (SELECT na `sofa_event_stats`), ale bramkarz startowy jest
     znany dopiero przed meczem — Sofascore w cache tego nie ma (`MODELE_HOKEJ_KOSZ_SIATKA.md` §A.7).
  2. Jakość/ilość strzałów (xG nie mamy; strzały są): `statistics_json` hokeja ma `Shots`, `Blocked`,
     `PowerPlayPercentage`, `emptyNetGoals` dla ~3–7 tys. meczów — model czyta tylko gole (grep
     `statistics_json` w `score_model.py`: 0).
  3. Odpoczynek / B2B: `b2b_delta` 0,0 (`score_model.py:218`); zmierzone dla kosza (+0,06 pkt, se 0,64,
     `MODELE…md` §0), dla hokeja nie zmierzone osobno w historii (MoneyPuck: ~−4 pp szansy wygranej).
  4. Remis w regulaminie (1X2 640): ZMIERZONE holdout `result_1x2|DRAW` p 0,1693 vs realizacja 0,1855
     (2 140 meczów) — model niedoszacowuje remisów ~1,6 pp; `hk_common` 0,0 (`:220`). `winner|TEAM` w
     kubełku 0,60-0,70: p 0,646 vs 0,594 (668 wierszy) — faworyt przeszacowany.
  5. Udziały tercji jedne dla wszystkich lig i drużyn (`:587-598`) — drużyna "trzeciej tercji" lub liga o
     innym profilu nie istnieje dla modelu.
  6. Brak totali i handicapów z dogrywką i karnymi (NHL wystawia tylko ten zakres, `market_coverage.py`
     reguła `hk.ot_so_scope`) — patrz niżej.
- Rozwiązanie:
  - (a) **centrum ze strzałów** (Macdonald, Lennon, Sturdivant 2012, "Evaluating NHL Goalies, Skaters,
    and Teams Using Weighted Shots", https://arxiv.org/abs/1205.1746 — ważone strzały "dobre, ale nie
    lepsze od tradycyjnych statystyk", czyli uzupełnienie, nie zamiennik): drugi `RatingBook` na metrykach
    `shots_for` i `save_rate` (gole = strzały × (1 − sv%)), sv% mocno kurczony do ligi. Miejsce:
    `score_model.parse_event` + nowa metryka w `_metrics`, łączenie w `ScoreModel.expected`. Dane:
    `sofa_event_stats.statistics_json` ("Shots"), już w DB.
  - (b) **bramkarz** — tylko jako *flaga kontekstu*, dopóki nie ma źródła bramkarza startowego przed
    meczem (Sofascore `/event/{id}/lineups` przed startem — `probe_lineup_availability.py`, "not yet run").
  - (c) remis regulaminowy: przetestować `hk_common` > 0 (dwuwymiarowy Poisson) **wyłącznie** dla hokeja —
    w piłce DC/bivariate odrzucone, w hokeju `hk_common` zmierzono dla wspólnego szoku (cov −0,04,
    `MODELE…md` §0) — więc nowym dowodem byłoby tylko holdout DRAW +1,6 pp.
  - Pomiar: `scripts/sofa/measure_score_history.py --sport hockey --params '{...}'` (już istnieje,
    walk-forward), metryka: log-loss / Brier progów + kalibracja `result_1x2|DRAW` i `winner|TEAM` w
    kubełkach ≥ 0,6; próg: lepiej w ≥ 3 z 4 okien używanych dla `SCORE_ALPHA`; potem na liniach Superbetu
    (`superbet_settled.jsonl`) `y − fair` nie gorsze. Przełącznik w `bet.sofa.epochs`, refit krzywych hokeja.
- Nakładanie się z "zmierzone i odrzucone": bivariate Poisson / DC odrzucone dla **piłki**; `hk_disp`
  (NB goli) i wspólny szok zmierzone w hokeju bez zysku (`score_model.py:288-296`). Strzały/bramkarz — nowe.
- Priorytet / nakład: P2 / M (hokej jest skalibrowany na liniach Superbetu: −1,3 pp (`sport_printable.hockey`: 6 105 linii / 886 meczów; audytor: −2,5 pp [−3,6; −1,3] na
  6 893 liniach / 962 meczach, 09-29..10-12)).

#### `period_total` 649, `period_team_total` 674/638, `period_handicap` 678, `period_dnb` 662, `period_1x2` 660 (hokej; "N. tercja - …")

- Gdzie liczone: jak wyżej; tercja = `mu × shares[i]` (`score_model.py:360-361`), ocena `_pair` scope
  "period" (`shadow.py:875-912`). Rynki historii: `HISTORY_MARKETS["hockey"]` (`sport_confidence.py:201-205`),
  tercje 1-3 (`PERIODS`, `:207`).
- Model teraz: tercja to Poisson z ułamkiem stawki meczu; efekt pustej bramki tylko w 3. tercji
  (`:432-434`).
- Wejścia: jak rdzeń + globalne udziały tercji.
- Braki: 1. udziały tercji jedne dla wszystkich lig (`:587-598`) — NHL vs ligi juniorskie mają inny profil
  (PODEJRZENIE: nie zmierzone); 2. stan wyniku (score effects: prowadzący oddaje strzały, MODELE §A.1 H22)
  — tercje nie są warunkowane wynikiem poprzednich (niezależne Poissony, `:423-426`) poza empty-net;
  3. kary/przewagi (brak w modelu; `PowerPlayPercentage` w cache).
- Rozwiązanie: udziały per liga z kurczeniem do globalnych (min. N meczów ligi), w `build_model`;
  pomiar `measure_score_history.py` z wariantem `shares_by_league`, Brier tercji 649/678 w holdoucie.
  ZMIERZONE na liniach Superbetu: `period_total|OVER` −2,8 pp, `period_team_total|UNDER` −2,3 pp,
  `period_handicap|TEAM` −1,9 pp (673 / 1 237 / 651 linii) — mało do zyskania.
- Nakładanie się: brak.
- Priorytet / nakład: P3 / S. To najczęściej drukowana grupa hokeja (737 nóg 10-05..10-13 z 1 109).

#### `hk.ot_so_scope` — totale / handicapy / team totals "z dogrywką i rzutami karnymi" (hokej, niezmapowane)

- Gdzie liczone: nigdzie. `shadow.MARKETS["hockey"]` ma tylko scope "reg" dla totali (`shadow.py:169-185`);
  reguła `hk.ot_so_scope` w `src/bet/sofa/market_coverage.py:476-479` (COMPUTABLE). Na próbie 10-13 tylko 4
  wystąpienia (15 meczów, w tym NHL), ale dla NHL to **główne** linie (komentarz reguły).
- Model teraz: brak.
- Braki: symulacja już generuje wynik pełny z bramką decydującą (`GameResult.t1_full`, `score_model.py:446`),
  więc wystarczy MarketSpec scope "full". Brak: rozkład goli w dogrywce 3v3 (dziś: dokładnie 1 gol
  zwycięzcy, nawet przy karnych — zgodne z rozliczeniem Superbetu "karne = 1 gol"? NIE SPRAWDZONE).
- Rozwiązanie: dodać ids do `shadow.MARKETS` (scope "full") po sprawdzeniu regulaminu Superbetu dla karnych;
  pomiar: na historii `walk_forward_rows` z `actual_value` "full" (`status.description` AET/AP w listingach).
  Za przełącznikiem `MAPPABLE_FAMILIES_FROM_UTC`-podobnym w `epochs`.
- Nakładanie się: brak. Priorytet / nakład: P2 / S (NHL sezon ruszył; to linie, które NHL faktycznie ma).

#### `hk.double_chance`, `hk.score_distribution`, `hk.goal_order` (hokej, niezmapowane)

- Gdzie: `market_coverage.py:472-482`. Podwójna szansa i dokładny wynik / parzystość to funkcje tej samej
  symulacji (COMPUTABLE); kolejność goli — NOT_COMPUTABLE (brak incydentów w cache).
- Braki: dokładny wynik zależy od struktury dyspersji (Poisson + empty-net) — remisy niedoszacowane
  (patrz rdzeń). Rozwiązanie: mapowanie + krzywa z historii, jak `result_1x2`. P3 / S.

#### Rdzeń kosza: `total` 753, `team_total` 758/776, `handicap` 768, `winner` 759, `result_1x2` 777 (kosz; "Liczba punktów (z dogrywką)", "Handicap (z dogrywką)", "Zwycięzca (z dogrywką)", "Mecz 1X2")

- Gdzie liczone: `score_model._basketball` (`score_model.py:450-474`), centrum `ScoreModel.expected`
  (`:330-361`), szum z `build_model` (`:610-647`), mnożnik świeżości `noise_mult` (`:317-328`, epoka
  `epochs.BB_FRESHNESS_FROM_UTC`, `epochs.py:364`). Pewność: krzywe `basketball:<family>|<side>` +
  `line_evidence` (offset sportu −12,7 pp [−16,3; −9,0], `config/sofa_superbet_line_evidence.json`
  `sport_printable.basketball`, 3 625 linii / 665 meczów).
- Model teraz: punkty regulaminu na drużynę = stawka ligi × atak × obrona (α 0,06), podział na kwarty
  globalnymi udziałami, szum normalny: wspólny szok gry (tempo) 1,26 pkt/kwartę, drużynowy 0,0, kwartowy
  5,22 (ZMIERZONE z modelu as-of 10-10), ×1,085 / ×1,026 dla "świeżych" drużyn; dogrywka: gauss z
  `mu[-1] × 5/10`.
- Wejścia: tylko punkty po kwartach z listingów; liga; siła ligi.
- Braki:
  1. **Populacja krzywej ≠ populacja druku** (podsumowanie p. 2): `synthetic_lines` (`sport_confidence.py:594-636`)
     stawia linie w kwantylach modelu; linia rynku jest skorelowana z prawdą, kwantyl modelu nie. Krzywa
     jest kalibracją P(y | p) dla linii niezależnych od błędu modelu, a drukujemy linie wybrane tam, gdzie
     model się z rynkiem rozjeżdża (selekcja `conf × odds ≥ 0,90`) — przekleństwo optymalizatora
     (Smith & Winkler 2006). ZMIERZONE: tabela gradientu w podsumowaniu; per klucz (linie z odczytem ≥ 0,70):
     `handicap|TEAM` 0,786 → 0,643 (945 linii / 325 meczów), `total|UNDER` 0,741 → 0,597 (2 151 / 516),
     `total|OVER` 0,834 → 0,643 (672 / 185), `team_total|OVER` 0,805 → 0,545 (246 / 91), `team_total|UNDER`
     0,716 → 0,550 (1 060 / 370), `winner|TEAM` 0,701 → 0,742 (132; jedyny bez zawyżenia). Weryfikacja r1 (krzywe `.next`): n i realizacje
     zgodne dla `handicap|TEAM`, `team_total|OVER`, `h1_*`, ale odczyt krzywej inny (0,781 zamiast 0,786; 0,753 zamiast 0,805);
     `total|UNDER` 384 / 119, `team_total|UNDER` 151 / 59 — liczb audytora dla tych dwóch nie odtworzono.
  2. **Brak tempa (posiadań) i efektywności osobno.** Rating na punktach łączy tempo i skuteczność;
     multiplikatywnie wartość oczekiwana jest formalnie ta sama co KenPom (tempo_A × tempo_B / średnia), ale
     tempo mierzone z posiadań jest dużo mniej zaszumione niż punkty, więc rating z punktów uczy się go
     wolniej (α 0,06 ≈ 16-meczowa pamięć). Dane są: `statistics_json` kosza (~34 484 mecze z
     `freeThrowsScored` "9/14", `fieldGoalsScored`, `offensiveRebounds`, `turnovers`) — grep w kodzie
     modelu: 0 użyć.
  3. **Kontekst meczu:** B2B (`b2b_delta` 0, `:218`; zmierzone +0,06 pkt — na punktach, nie na
     prawdopodobieństwie wygranej/totalu), odpoczynek 3+ dni, podróż, faza sezonu (start sezonu tylko jako
     szum `bb_fresh_mult`, nie jako przesunięcie centrum: undery w 1. tygodniu sezonu 58,2% — Girdner i in.
     2013, cytowane w `MODELE…md` §A.2 B28, źródła nie otwierałem), absencje gwiazd (brak źródła
     przedmeczowego).
  4. **Przedsezon / puchary bez stawki ligi** — p. 1 podsumowania (BŁĄD).
  5. **Za szeroki rozkład na historii** (podsumowanie p. 4) — przyczyna niezmierzona; kandydaci:
     jeden `period_sd` dla lig 140- i 230-punktowych (`bb_sd_level_power` 0, `:259`, zmierzone 10-03 bez
     zysku na Brierze — ale nie na kalibracji kubełków ≥ 0,7), `bb_fresh_mult` doliczany do już szerokiego
     szumu, reszty liczone wobec ratingu "po" meczach okna (docstring `:573-576` mówi "one step ahead,
     before each game updates the book", a kod najpierw robi `book.update` dla całej historii `:594`, potem
     liczy reszty `:614-637` — niezgodność dokumentacji z kodem; kierunek efektu niezmierzony).
  6. **Remis po regulaminie** 2,20% vs 3,99% (podsumowanie p. 5) — gauss niezależny od stanu meczu.
  7. **Dogrywka NBA** 5/10 kwarty zamiast 5/12 (`score_model.py:468`: `q_len = 10.0 if len(mu1) == 4 else 12.0`,
     a `mu1` ma zawsze 4 elementy dla kosza) — ~20% za dużo punktów w dogrywce NBA (BŁĄD, mały: dotyczy
     ~4-6% meczów).
  8. Brak h2h (grep `h2h`: brak; `sample_hit_rate` `sport_confidence.py:1082-1118` liczy ostatnie 10
     meczów każdej drużyny, nie wspólne — pokazywane, nie bramka).
- Rozwiązanie:
  - (a) **BŁĄD 1 (poprawność, z testem, za przełącznikiem od następnego dnia 00:00Z):** w `ScoreModel.expected` zwracać `None`
    (`NOT_CALIBRATED`/nowa notatka `NO_LEAGUE_RATE`), gdy `book.leagues[(comp, metric)].n < MIN_LEAGUE_MATCHES`
    i rozgrywki są sparingiem/przedsezonem (`comparability.is_friendly_event` na `sport_fixtures.json`
    zdarzeniu). (Wariant „dla przedsezonu mapować na ligę macierzystą drużyn” (`RatingBook.domain`) odrzucony
    w weryfikacji r2: wyceniałby przedsezon stawkami sezonu zasadniczego i odbiega od reguły `FRIENDLY_FIXTURE` w piłce; zob. A2.)
    Global fallback zostawić tylko dla lig tej samej klasy. To korekta poprawności (CLAUDE.md "Changing the
    pipeline" 2) — ale zmienia to, co się drukuje, więc przełącznik w `epochs` od następnego dnia 00:00Z (wcześniej tylko decyzją operatora).
    Pomiar: lista nóg 10-05..10-13 z ligą < 30 meczów w `book.leagues` (odtworzenie modelu as-of dnia).
  - (b) **Krzywa na właściwej populacji linii (P1, M):** dopasować krzywą historii także na liniach
    postawionych tam, gdzie stał rynek. Źródło rynku w historii: Sofascore `/event/{id}/odds/1/all`
    (przykład `docs/sofa/evidence/event_16363633_odds.json` ma rynki z `winning`), backfill przez most —
    *cena tylko do postawienia linii, nie jako wejście p* (to nie jest mieszanie ceny). Bez backfillu:
    kalibracja dwuwymiarowa P(y | p, |kwantyl linii w rozkładzie modelu|) nic nie da, bo kwantyl = p;
    więc jedyną niezależną od rynku poprawką jest lepsze centrum (c)-(d). Pomiar: na
    `basketball_superbet_settled.jsonl` (81 011 linii) i na backfillowanej historii: realizacja − pewność w
    kubełkach ≥ 0,70 per klucz; próg F6 (`MAX_OVERSTATEMENT` 0,03).
  - (c) **Tempo + efektywność (P1, L):** model Olivera / KenPom: posiadania
    `Poss = 0,5·[(FGA + 0,4·FTA − 1,07·ORB/(ORB+OppDRB)·(FGA−FG) + TOV) + (to samo dla rywala)]`
    (basketball-reference glossary), tempo meczu = tempo_A × tempo_B / tempo_ligi, punkty =
    posiadania × ORtg_A × DRtg_B / ORtg_ligi (KenPom, schemat wg wyszukiwarki — strona KenPom zwróciła 403).
    Miejsce: nowe metryki `bb_poss`, `bb_ppp_for` w `score_model.parse_event` (z `statistics_json`, gdy jest;
    inaczej punkty), `ScoreModel.expected` zwraca `poss × ppp`; szum tempa (`bb_game_sd`) z wariancji
    posiadań. Dane: `sofa_event_stats.statistics_json` (34 tys. meczów). Pomiar:
    `measure_score_history.py --sport basketball` z nowym wariantem, okna jak `SCORE_ALPHA` (`:83-91`);
    metryka: log-loss progów totalu/handicapu + **Brier na liniach głównych Superbetu** (fair 0,45-0,55,
    dziś 0,2593) — próg: < 0,25 z przedziałem po meczach.
  - (d) **Remis/dogrywka:** zamiast gaussa — empiryczny rozkład marginesu regulaminu z historii per liga
    (ogon "skoku remisu": Ely (Cheap Talk 2009), https://cheaptalk.org/2009/06/10/the-overtime-spike-in-nba-basketball/ —
    6,26% vs 2,29% przewidywane rozkładem normalnym) albo mieszanina: P(remis) kalibrowane empirycznie.
    Miejsce: `_basketball` (`:450-474`). Poprawka `q_len` = 12 dla lig 48-minutowych (`defaultPeriodLength`
    z `/event` lub stała per liga). Pomiar: holdout `result_1x2|DRAW` (dziś 0,022 vs 0,040) i `handicap`
    przy |linii| ≤ 3,5.
  - (e) **Faza sezonu / B2B jako przesunięcie centrum**, nie tylko szum: B2B zmierzone na punktach bez
    efektu; zmierzyć na *totalu* i *wygranej* osobno (MoneyPuck dla NHL: −4% szansy wygranej,
    https://moneypuck.com/about.htm). `measure_schedule_context.py` istnieje (piłka) — rozszerzyć na
    `--sport basketball`.
- Nakładanie się z "zmierzone i odrzucone": per-key p-bucket cap dla sportów odrzucony 2026-10-12
  (`measure_sport_guard.py`) — (b) nie jest capem, tylko inną populacją dopasowania krzywej. Mieszanie z
  ceną / bramka na rozjeździe — odrzucone; (b) używa linii rynku wyłącznie jako miejsca linii w historii;
  operator musi to zaakceptować świadomie. `bb_sd_level_power` i B2B — zmierzone 10-01/10-03 na Brierze
  progów; nowy jest pomiar na kalibracji kubełków ≥ 0,70 i na liniach Superbetu.
- Priorytet / nakład: (a) P1 / S; (b) P1 / M; (c) P1 / L; (d) P2 / S; (e) P2 / M.

#### Połowy: `h1_total` 748, `h1_handicap` 773, `h1_team_total` 200804/200797, `h1_dnb` 765, `h1_1x2` 763; `h2_total` 233404, `h2_handicap` 233405, `h2_team_total` 233806/233807, `h2_dnb` 233499, `h2_1x2` 233400 (kosz)

- Gdzie liczone: suma kwart symulacji, `_pair` scope h1/h2 (`shadow.py:899-904`), h2 bez dogrywki
  (operator 10-07, `sport_confidence.py:130-132`). Krzywe: `HISTORY_MARKETS` (`:201-205`).
- Model teraz: globalne udziały kwart × centrum meczu; szum kwart niezależny poza szokiem gry.
- Braki: 1. ZMIERZONE (linie Superbetu, odczyt ≥ 0,70): `h1_total|OVER` 0,811 → 0,418 (122 linie / 63
  mecze), `h1_team_total|OVER` 0,785 → 0,452 (115 / 57), `h1_handicap|TEAM` 0,772 → 0,497 (187 / 116) —
  najgorsze klucze kosza; fit 10-13 odrzuca je (`OVERSTATES`, `log_basketball.txt`). 2. Druga połowa
  zależy od stanu meczu (garbage time: zespół z +20 zdejmuje starterów — Cleaning the Glass definiuje
  garbage time progami 25/20/10 pkt w 4. kwarcie, https://cleaningtheglass.com/stats/guide/garbage_time),
  model nie warunkuje h2 na h1 (szok kwart niezależny, `:463-464`). 3. Udziały kwart jedne dla wszystkich lig.
- Rozwiązanie: po (c) rdzenia — proces kwart z ujemną zależnością marginesu h2 od |marginesu h1| (tempo
  spada w rozstrzygniętym meczu); mierzalne na historii: regresja `h2_total − E` na `|h1_margin|`. Miejsce
  `_basketball`. Pomiar: `measure_score_history.py`, Brier progów h2. P2 / M.
- Nakładanie się: brak.

#### Kwarty: `quarter_total` 788, `quarter_handicap` 774, `quarter_team_total` 200802/200795, `quarter_dnb` 772, `quarter_1x2` 779 (kosz)

- Gdzie: jak połowy, scope "period" `quarternr`; `EXTENDED_MARKETS` (`sport_confidence.py:133-145`).
- Model teraz: kwarta = udział × centrum + szum gry + szum kwarty 5,22.
- Braki: Q4 w meczu rozstrzygniętym (garbage time) i w meczu wyrównanym (faule taktyczne, rzuty wolne —
  więcej punktów); ZMIERZONE: `quarter_team_total|OVER` 0,726 → 0,474 (19 linii, za mało), krzywe
  `quarter_*` dopuszczone na historii (`log_basketball.txt` admitted). Pozostałe — PODEJRZENIE.
- Rozwiązanie: udział Q4 warunkowy od marginesu po Q3 w symulacji; pomiar jak wyżej. P3 / M.

#### `odd_even` 775, `team_odd_even` 230634/230640 (kosz; "Parzysta/nieparzysta")

- Gdzie: `actual_value` odd_even (`shadow.py:943-946`); symulacja zaokrągla gaussa (`score_model.py:455-464`).
- Model teraz: parzystość z zaokrąglonej normalnej → ~0,5; krzywe `NO_OOS_PRINTABLE_BUCKET`
  (`log_basketball.txt`) — nic się nie drukuje i drukować nie powinno (marża 8,6-8,7%, `MODELE…md` §0).
- Braki: brak; rynek bez informacji. P3 / —.

#### `bb.double_chance`, `bb.team_box`, `bb.double_double`, `bb.score_order` (kosz, niezmapowane)

- Gdzie: `market_coverage.py:485-500`; próba 10-13: `bb.team_box` 196 wystąpień (np. "Fenerbahce - liczba
  asyst (z dogrywką)"), `bb.double_chance` 37, `bb.double_double` 8, `bb.score_order` 16 (NOT_COMPUTABLE).
- Braki: team box (zbiórki, asysty, trójki, straty, faule drużyny) — metryk nie ma w ratingu, ale dane są w
  `statistics_json` (34 tys. meczów). To dokładnie rynki, gdzie styl/matchup (ORB% vs DRB% rywala, tempo)
  jest naturalnym modelem: zbiórki_A ≈ (pudła_A × ORB%_A vs DRB%_B) + (pudła_B × DRB%_A).
- Rozwiązanie: nowe metryki RatingBook (atak × obrona na zbiórki, asysty, trójki, straty) + NB per mecz;
  krzywa z historii i własne linie Superbetu, jak każdy klucz. Pomiar: walk-forward log-loss vs stopa
  bazowa ligi (wzór `measure_football_result_model.py`). P2 / M (marża nieznana — zmierzyć overround grup
  przed pracą).

#### Propsy kosza: `player_points` (233565/239934), `player_assists` (233566/239935), `player_rebounds` (233567/239936), `player_threes` (233568/233857), `player_pts_reb_ast` (233569/239940), `player_reb_ast` (233570/239939), `player_pts_ast` (233571/239937), `player_pts_reb` (233572/239938), `player_blocks` 235217, `player_steals` 235218; + `bb.player_milestone` (niezmapowane, 64 wystąpienia)

- Gdzie liczone: `player_model.count_distribution` (`src/bet/sofa/player_model.py:635-680`), p strony
  `side_probability` (`:720`), kalibracja `calibrate_side` (`:710`); p zapisuje SHADOW do
  `player_model.jsonl`, czyta `run_sport_confidence.pregame_player_p` (`run_sport_confidence.py:219-245`).
  Pewność: tylko `line_evidence` (brak krzywej historii, `sport_confidence.py:150-154`).
- Model teraz: stawka na sekundę zawodnika kurczona do puli (wszyscy zawodnicy obu drużyn, `pool` "all"
  dopasowane), oczekiwane minuty = średnia ważona półokresem 5 meczów, log-normalny szum minut, NB dla
  liczby; kombinacje (P+R+A itd.) modelowane bezpośrednio jako suma w meczu (dobrze — jeden szok minut).
- Wejścia: własne `/lineups` zawodnika (`sofa_event_stats.lineups_json`), pula drużyn.
- Braki: 1. Rywal (obrona / zbiórki dopuszczane / tempo rywala) — grep `opponent|pace|possess` w
  `player_model.py`: brak użycia w modelu. 2. Spodziewany margines → minuty gwiazd (garbage time, CTG
  wyżej) — model nie czyta `score_model`. 3. Rola/starter, nieobecny kolega (usage) — brak źródła
  przedmeczowego. 4. B2B / odpoczynek gwiazd (grep `rest|back`: brak). 5. Dowód z linii cienki: klucze
  kosza 40-50 meczów (`config/sofa_superbet_line_evidence.json` keys basketball/player_*, np.
  `player_points|OVER` n 336 / 50 meczów) — `NO_LINE_EVIDENCE` w praktyce; 0 nóg kosza z propsów
  w `08_confidence_sports.json` 10-05..10-13.
- Rozwiązanie: minuty × (stawka_zawodnika × tempo_meczu/tempo_ligi × korekta_rywala), gdzie tempo i
  spodziewany margines z modelu wyniku (po (c) rdzenia); minuty warunkowe na |marginesie| (garbage time).
  Miejsce: `player_model.count_distribution` dostaje `pace_mult`, `opp_mult`, `minutes_mult` z
  `forecast_records`. Dane: `lineups_json` + `statistics_json` (już są). Pomiar:
  `scripts/sofa/measure_player_props.py --sport basketball` (istnieje) — log-loss liczby i kalibracja OVER na
  liniach Superbetu; próg: lepsza log-loss niż v3 na teście + brak zawyżenia OVER (MODELE §0: OVER −6 pp
  vs cena, podejrzenie z 3 dni).
- Nakładanie się: brak (re-ranking peerów / próbki to inne). Priorytet / nakład: P2 / L (najpierw rdzeń).

#### Propsy hokeja: `player_points` 236265, `player_assists` 236264, `player_shots_on_goal` 230023, `player_pp_points` 232584, `player_plus_minus` 232585, `player_blocked_shots` 232586, `player_faceoff_wins` 236939, `player_hits` 236940, `player_goalie_saves` 230026

- Gdzie liczone: jak kosz (`player_model.py`), pula = grupa pozycji (`position_group`, `:272`);
  plus-minus normalny (`signed_distribution`, `:683`).
- Model teraz: stawka na sekundę lodu × TOI; brak związku z modelem wyniku drużyny.
- Wejścia: `/lineups` hokeja (`shots`, `points`, `powerPlay*`, `saves`, `secondsPlayed`).
- Braki: 1. Punkty/asysty/PP-punkty nie są związane z oczekiwanymi golami drużyny ani przewagami rywala
  (karność rywala) — `MODELE…md` §B.3 proponował `udział × E[gole drużyny]`, nie wdrożone (grep
  `score_model` w `player_model.py`: brak importu). 2. Obrony bramkarza: strzały rywala z modelu nie
  istnieją; bramkarz startowy nieznany (VOID chroni tylko przed DNP). 3. Score effects w strzałach
  (prowadzący strzela mniej). 4. Drukuje się wyłącznie `player_pp_points` UNDER (18 nóg; dowód z linii:
  kubełki 0,75-0,95 w paśmie 1,00-1,30 realizują 0,82-0,91, np. 0,800-0,825: 65/73) — to rynek, gdzie
  UNDER prawie zawsze wygrywa, a cena < 1,30.
- Rozwiązanie: PP-punkty = udział zawodnika w golach PP drużyny × E[gole PP] = E[liczba przewag]
  (kary rywala: `statistics_json` "SuspensionMinutes"/"suspensions") × skuteczność PP drużyny
  (`PowerPlayPercentage`) — dane w cache (~3 tys. meczów). Strzały: TOI × stawka × (strzały dopuszczane
  rywala / liga) z `Shots`. Pomiar: `measure_player_props.py --sport hockey`. P3 / M.
- Nakładanie się: brak.

### Braki wspólne dla obszaru

1. **Brak twardej bramki "rozgrywki bez stawki ligi"** — BŁĄD 1; dotyczy obu sportów (`football_rating.py:770-779`,
   `score_model.py:330-342`). Test offline: mecz w rozgrywkach z n < 30 i sparing → `expected` = None.
2. **Krzywe historii kalibrują inną populację linii niż drukowana** (`sport_confidence.synthetic_lines`) —
   wspólne dla hokeja i kosza; w hokeju małe, bo model blisko rynku. Do raportu dla operatora: gradient
   luki względem `p − fair` jest *pomiarem* (nie propozycją bramki). Smith & Winkler 2006, "The optimizer's
   curse", Management Science 52(3):311-322, https://scholars.duke.edu/publication/798952 — selekcja
   najwyższych szumnych estymat daje systematyczne rozczarowanie; remedium: kurczenie estymat
   (bayesowskie), tu: kurczenie p modelu w stronę… czego? Bez ceny — w stronę bazowej stopy linii
   głównej (0,5) proporcjonalnie do zmierzonego braku informacji (Brier ≥ 0,25 na liniach głównych), co jest
   równoważne zwężeniu odchylenia centrum modelu. Do zmierzenia jako wariant krzywej, nie gate.
3. **`statistics_json` i `lineups_json` w DB, a model wyniku czyta tylko listingi** — posiadania (kosz),
   strzały / przewagi / puste bramki (hokej).
4. **Rozkład i kontekst:** jeden zestaw udziałów okresów i jeden szum dla wszystkich lig; brak
   odpoczynku/podróży/fazy sezonu w centrum; h2h nieobecne (dla tych sportów literatura nie daje
   argumentu za h2h ponad rating — PODEJRZENIE, nie szukałem).
5. **Zakres dogrywki:** kosz pełny mecz OK (z dogrywką), NBA dogrywka 5/10 zamiast 5/12; hokej bez rynków
   z dogrywką i karnymi.
6. Kotwica pomiaru: każdy wariant najpierw `measure_score_history.py` (historia, walk-forward), potem
   `superbet_settled.jsonl` (Brier na liniach głównych, `y − pewność` po rozjeździe), potem przełącznik
   w `bet.sofa.epochs` + refit krzywych sportów na kopii DB, zgoda operatora.

### Czego nie sprawdziłem

- Skali BŁĘDU 1 poza NBA Preseason (puchary, CBA Preseason, nowe rozgrywki): nie odtwarzałem modelu as-of
  każdego dnia; NBA Preseason zmierzone na 34 liniach głównych (weryfikacja r1: 18 linii OVER) i 1 nodze.
- Przyczyny zbyt szerokiego rozkładu kosza na historii (in-sample reszt vs `bb_fresh_mult` vs mieszanka lig) —
  nie rozdzielone.
- Czy kurczenie (wsp. 2) lub posiadania (rdzeń c) faktycznie zamykają lukę −14..−16 pp — to hipotezy.
- Dostępności kursów historycznych Sofascore dla kosza w skali backfillu (jeden plik dowodu, piłka).
- Regulaminu Superbetu dla karnych w totalach NHL "z dogrywką i rzutami karnymi".
- Literatury: strona KenPom zwróciła 403 (wzór tempa tylko z wyników wyszukiwarki i bloga, nie z KenPom);
  Kubatko i in. 2007 — tylko rekord bibliograficzny (wyszukiwarka); efekt B2B bramkarzy NHL (Tulsky 2013)
  — tylko wyniki wyszukiwania, rozbieżne liczby, nieużyte jako dowód; Asness & Brown (SSRN 3132563) —
  PDF niedostępny (404), nieużyte. Otwarte: basketball-reference glossary, cheaptalk (Ely, Cheap Talk 2009),
  moneypuck.com/about, Cleaning the Glass garbage time, Smith & Winkler (Duke), arXiv 1205.1746, arXiv
  1503.03509 (Clauset, Kogan, Redner 2015 — strona nie wymienia koszykówki w streszczeniu).
- Wierszy linii Superbetu dla propsów (brak ich w `*_superbet_settled.jsonl`; liczby propsów tylko z
  `config/sofa_superbet_line_evidence.json`).
- Siatkówki i CS2 (poza zakresem).

# Część 5

## Siatkówka i CS2 - audyt rynek po rynku (2026-10-13)

Tryb: tylko odczyt. Repo nietknięte; baza `data/sofa.db` czytana `mode=ro`; bez bridge'a i Superbetu.
Dwa skrypty diagnostyczne w scratchpadzie (`audit/vb/vb_iid.py`, `vb_so.py`) plus kilka SELECT-ów na `cs2_*`.
"Zmierzone" = liczba policzona tu albo przeczytana z pliku konfiguracyjnego (z podaną ścieżką). "Podejrzenie" = bez pomiaru.

### Podsumowanie

1. **Siatkówka: punktowe rynki stoją na modelu akcji i.i.d., który rozkład długości seta ma zły nawet przy idealnym udziale.**
   `_volleyball` (`src/bet/sofa/score_model.py:504`) gra każdą akcję z tym samym p, gdzie p to stosunek oczekiwanych punktów obu stron na set; produkcja ma `vb_sideout = 0` (`score_model.py:244`) i `vb_set_sd = 0` (`:238`).
   Zmierzone tutaj na 23 421 meczach z historii (diagnostyka w próbie: każdy mecz symulowany z własnym, zrealizowanym udziałem akcji, czyli najlepszy możliwy przypadek). Wynik:
   - suma punktów: mężczyźni 159,99 vs realnie 165,82 (−5,8 pkt na mecz); kobiety 155,25 vs 159,60;
   - set na przewagi: mężczyźni 9,7% vs 12,3% setów; kobiety 8,6% vs 9,9%;
   - rozrzut udziału punktów między setami jednego meczu: mężczyźni sd 0,059 vs 0,044.
   Prawdziwe sety są ciaśniejsze i dłuższe, niż daje i.i.d.
2. **Krzywa historii siatkówki na liniach Superbetu jest przeszacowana (zmierzone; przed offsetem line evidence, który już to obniża w druku).** Dane z `config/sofa_superbet_line_evidence.json`, `sport_printable.volleyball`: realizacja minus pewność −13,4 pp [−18,8; −7,8] na 591 drukowalnych liniach z 274 meczów. Per klucz:
   - `points_handicap|TEAM`: −29,5 pp [−43,4; −15,5], 128 linii / 74 mecze;
   - `set_handicap|TEAM`: −13,6 pp [−20,8; −6,1], 181 / 125;
   - `points_total|OVER`: −56 pp, tylko 24 / 16.

   Krzywe historyczne pokazują, że model przeszacowuje ogony (krzywa to koryguje; holdout tych kubłów: pewność o 1,7-2,9 pp poniżej realizacji). W `config/sofa_sport_confidence_calibration.next.json`, `points_total|UNDER`, kubeł 0,95+ zrealizował 0,933, a kubeł 0,90-0,925 zrealizował 0,881.
3. **Siatkówka nie zna płci na poziomie akcji, przewagi serwującego ani "tempa" ligi.** Liga wchodzi tylko przez `RatingBook.league_rates` (średnie punkty gospodarza i gościa na set, `football_rating.py`, `league_rates`). Płeć jest wyłącznie kluczem rezerwowej średniej globalnej (`_global_key`). Symulacja nie ma parametru zależnego od płci ani ligi (grep `women|gender` w `score_model.py`: tylko `parse_event:152`).
4. **Rynki setowe siatkówki (744, 782, 781, 100077) nie są liczone z historii,** choć symulacja gra każdy set. Powód: nie ma ich w `HISTORY_MARKETS["volleyball"]` (`sport_confidence.py:205`) ani w `PERIODS` (`:207`; decyzja plan F4 / operatora 10-07, komentarz `:208`), a `SETTLED_ONLY_FAMILIES` (`:209`) czyta je wyłącznie z rozliczonych linii Superbetu. W pliku line evidence to n=10 dla `set_extra_points` i n=172 dla `set_points_total`, czyli pozostają `NO_LINE_EVIDENCE`. To naprawa prawie bez modelowania, ale odwraca decyzję operatora i zależy od B9 (długość seta).
5. **CS2 `map_team_rounds` ignoruje przeciwnika.** Liczy częstość rund drużyny z jej ostatnich 20 map, ściągniętą do bazy (`cs2_engine.py:838-841`, `shrunk_frequency`), a rating mapy `p_map` nie wchodzi wcale. Linia 12,5 to praktycznie "wygra mapę albo przegra po dogrywce". Line evidence: `map_team_rounds|OVER` −21,6 pp [−32,9; −10,9], 66 linii / 24 serie. Gotowy wyścig rund `map_distribution_for` (`cs2_engine.py:565`) już istnieje i wycenia z niego `map_rounds_handicap`. Pozycja jest już w kolejce CLAUDE.md ("queued: CS2 map_team_rounds from the round race").
6. **CS2 nie używa mapy, strony ani pierwszej połowy, choć baza je ma.** `cs2_map` ma `map_name` (33 641 z 33 895 map), `home_starting_side`, `home_period1/2` (25 669 map), `home_overtime` (2 935 map z dogrywką); `cs2_player_map` ma `adr` i `kast` (256 293 wierszy). `load_history` (`cs2_engine.py:375`) czyta tylko rundy, zwycięzcę i K/D/A/HS.
   Zmierzone surowo: udział rund pierwszej połowy strony o kodzie 5 waha się per mapa: Nuke 0,552 vs 0,489 dla strony 4, Train 0,582 vs 0,449, Anubis odwrotnie (0,501 vs 0,539).
7. **CS2 zabójstwa zawodnika i drużyny nie zależą od oczekiwanej liczby rund ani od siły rywala.** Używane jest surowe NB z ostatnich 20 map (`cs2_engine.py:611`, `count_p`; `:710`, `player_values`). Zmierzone: korelacja zabójstw z liczbą rund mapy 0,592; średnio 15,94 zabójstwa w wygranej i 12,71 w przegranej (n=256 290 wierszy gracz-mapa).
8. **CS2 `match_winner` liczony jest bez mieszania Beta, a rynki serii z mieszaniem.** `series_distribution` (`cs2_engine.py:784`) vs `series_distribution_mixed` (`:769`). To ten sam p mapy, ale dwa niespójne modele serii; krzywa łata różnicę osobno.
9. **CS2 `map_rounds_total` to globalna stopa bazowa,** bez meczu, mapy i siły (`cs2_engine.py:822-830`). Zmierzone: P(suma > 21,5) waha się od 0,43 (Inferno) do 0,478 (Anubis/Cache).
10. **Niewycenione rynki CS2 dają się wyprowadzić z rozkładów, które już mamy** (wyścig rund + rozkład serii): rundy serii, parzystość rund, liczba dogrywek, dokładny wynik mapy, zwycięzca i liczba rund. Są tylko sklasyfikowane w `market_coverage.py:521-535`.

### Mapa obliczeń

```
SIATKÓWKA
listingi Sofascore (sofa_entity_events) ── score_model.parse_event:103
   wartość = (pkt gospodarza / sety, pkt gościa / sety)  [setpts_for, :148]
        │
RatingBook (football_rating) atak×obrona per drużyna, liga = średnie dom/wyjazd,
   siła ligi tylko przez mecze międzyligowe, alpha 0.14 (score_model.py:92)
        │ expected(): eh, ea  (score_model.py:330)
        ▼
share = eh/(eh+ea) ── (+ N(0, 0.03) na mecz, vb_match_sd :287)
        ▼
_volleyball :504  akcje i.i.d. z p=share (sideout 0), sety do 25 / tie-break 15, 4000 symulacji
        ▼
line_probability :543 → p (forecast)
        ▼
SPORT_CONFIDENCE: krzywa historyczna (fit_sport_confidence, HISTORY_MARKETS
   745,230058,100082,230060,1069,785,200896 - sport_confidence.py:205)
   rynki setowe 744/782/781/100077: tylko rozliczone linie Superbetu (SETTLED_ONLY :209)
        ▼
line_evidence: offset klucza / sportu + cap pasma ceny → pewność

CS2
cs2_series / cs2_map / cs2_player_map (data/sofa.db) ── cs2_engine.load_history:375
        │  (bez map_name, stron, połówek, adr, kast, turnieju)
        ├─ EloBook (mapowe Elo drużyny, K=24) + PlayerEloBook (Elo graczy z ostatniego składu)
        │     → RatingModel.p_map: sigmoid(a + b·gap), a = "gospodarz" (:321)
        │        ├─ map_winner: p_map (to samo dla mapy 1, 2, 3)
        │        ├─ match_winner: series_distribution (stałe p, :784)
        │        ├─ maps_total / maps_handicap / team_maps / exact_maps: series_distribution_mixed κ=6 (:763)
        │        └─ map_rounds_handicap: wyścig rund MR12+OT z szokiem sd 0.12 (:565, :808)
        ├─ map_rounds_total: globalna stopa bazowa (:822)
        ├─ map_team_rounds: częstość własnych rund (20 map) ściągnięta K=20 do bazy (:838)
        └─ team_kills / player_*: NB lub normal z ostatnich 20 map (:611)
        ▼
SPORT_CONFIDENCE: krzywe historyczne (map_winner, match_winner, map_team_rounds,
   rodziny serii); reszta (rundy mapy, kills) tylko z rozliczonych linii (settle_cs2.attach_model)
        ▼ line_evidence → pewność; brak best_of → None (run_sport_confidence.py:169)
```

### Rynek po rynku

#### Siatkówka

##### winner (siatkówka; 745 "Zwycięzca meczu")
- **Gdzie liczone:** `score_model.py:504` (`_volleyball`) przez `line_probability:543`. Pewność daje krzywa `winner|TEAM` (historia) z `calibration.next.json`.
- **Model teraz:** udział punktów z ratingu atak×obrona na "punkty na set", jeden szok meczu sd 0,03, akcje i.i.d.
- **Wejścia:** własne wyniki obu drużyn (oponent-adjusted przez `RatingBook.update`), średnie ligi dom/wyjazd, siła ligi dla par międzyligowych, `LINKED`/`UNLINKED`.
- **Braki:**
  1. Brak przewagi serwującego (side-out). `vb_sideout = 0` (`score_model.py:244`). W kodzie zmierzono 0,62 globalnie: sety lepsze, zwycięzca gorszy (komentarz `:236-237`). Nigdy nie mierzono osobno per płeć ani ligę.
  2. Rating na "punktach na set" miesza sety wygrane i przegrane (`:148`). Wynik meczu (sety) nie jest osobnym sygnałem ratingu.
  3. Brak rest/travel/back-to-back dla siatkówki (`b2b_delta = 0`, `:218`, i siatkówka go nie ustawia), brak h2h (grep `h2h` w `score_model.py`: brak), brak składu (`PLAYER_MARKETS["volleyball"] = {}`, `shadow.py:337`; `/lineups` siatki niesprawdzone, `MODELE_HOKEJ_KOSZ_SIATKA.md:342`).
  4. Krzywa ma dziurę: kubły 0,80-0,95 nie istnieją (n<200). Rozkład p jest dwubiegunowy, bo set i.i.d. ostro wyostrza mały udział (podejrzenie co do przyczyny; dziura zmierzona w pliku).
- **Rozwiązanie:** dwuparametrowy model Ferrante i Fonseca (2014), czyli osobne p(wygrania akcji przy własnym serwisie) i przy odbiorze; https://ideas.repec.Org/a/bpj/jqsprt/v10y2014i2p8n9.html (otwarte, abstrakt).
  - Side-out ligowy fitować per płeć, a różnicę drużyn wnieść jako przesunięcie logitu (już jest w `serve_probabilities:485`).
  - Alternatywa: hierarchiczny model Egidi i Ntzoufras (2020), w którym zwycięzca seta jest logitem, punkty przegranego mają ucięty NB, a set na przewagi ma osobny składnik Poissona; https://arxiv.org/abs/1911.01815 (otwarte).
  - Miejsce w kodzie: `SimParams` plus `ScoreModel.simulate` (`score_model.py:389-396`), parametr per płeć z `FootballResult.women`.
  - Dane: mamy wyniki setów (listingi); punktów przy serwisie nie mamy (`/statistics` siatki w cache 1 064 z 10 381 meczów, `MODELE...md:347`).
  - Pomiar: `measure_score_history.py --sport volleyball --params '{"vb_sideout":...}'` osobno dla kobiet i mężczyzn. Metryka: log-loss na `winner`, `sets_total`, `points_total` w czterech oknach jak przy `vb_match_sd`; próg: lepiej we wszystkich oknach. Potem przełącznik w `epochs`.
- **Nakładanie się z "zmierzone i odrzucone":** `vb_sideout` 0,62 i `vb_set_sd` 0,02 mierzone 2026-10-01 i niewłączone (komentarz w kodzie, nie lista CLAUDE.md). Nowe jest to, że parametr byłby per płeć i oceniany per rynek, a nie jednym średnim Brierem; diagnostyka niżej pokazuje, że kobiety i mężczyźni różnią się w tym miejscu.
- **Priorytet / nakład:** P2 / M.

##### sets_total (230058 "Liczba setów"), set_handicap (100082), exact_sets (785 "Dokładny wynik")
- **Gdzie liczone:** ta sama symulacja; `actual_value` w `shadow.py:913`. Krzywe: `sets_total|OVER/UNDER`, `set_handicap|TEAM`, `exact_sets|a:b` (historia, `next.json`).
- **Model teraz:** sety niezależne przy stałym udziale plus szok meczu 0,03.
- **Braki:**
  1. Brak zależności set do setu poza jednym szokiem meczu: brak momentum, brak "martwego" 3. seta przy 2:0.
     - Diagnostyka (zmierzone, w próbie, idealny udział): P(5 setów) zgadza się przy i.i.d. (M 0,216 vs 0,213, K 0,192 vs 0,188).
     - Side-out 0,65 psuje go (M 0,185, K 0,143). To dlatego serwis "przegrał zwycięzcę".
     - Wniosek: realne mecze mają ciasne sety, ale zmienność między setami większą, niż daje side-out bez szoku na set.
  2. `set_handicap|TEAM` jest przeszacowany: holdout 0,825-0,850 o +0,0427 (`not_calibrated`), Superbet −13,6 pp (pkt 2 podsumowania).
- **Rozwiązanie:** łączyć side-out (ciaśniejsze sety) z szokiem na set (`vb_set_sd` > 0) i fitować oba naraz na wielu rynkach; dziś każdy był mierzony osobno.
  - Ntzoufras, Palaskas i Drikos (2021) modelują różnicę setów porządkowo albo uciętym Skellamem; https://arxiv.org/abs/1911.04541 (otwarte, abstrakt bez liczb). Model pomocniczy dla `set_handicap` i `exact_sets`.
  - Pomiar: siatka (`vb_sideout`, `vb_set_sd`, `vb_match_sd`) per płeć, walk-forward w `measure_score_history.py`. Metryka: log-loss `exact_sets` (6 klas) i `set_handicap`.
- **Nakładanie się:** jak wyżej; hierarchiczne pooling (odrzucone dla piłki) nie jest proponowane.
- **Priorytet / nakład:** P2 / M.

##### points_total (230060 "Suma punktów"), points_handicap (1069 "Handicap punktowy")
- **Gdzie liczone:** `_volleyball:504` (suma i różnica punktów z symulowanych setów). Krzywe: `points_total|OVER/UNDER`, `points_handicap|TEAM`.
- **Braki:**
  1. **Systematycznie za krótkie mecze.** Nawet z prawdziwym udziałem akcji meczu symulacja daje o 5,8 pkt (M) i 4,3 pkt (K) mniej. Zmierzone, `audit/vb/vb_iid.py`, 7 009 meczów M i 16 412 K. Side-out 0,6-0,7 tego nie zamyka (M 158,4-160,4).
     - Przyczyna nieustalona (podejrzenie: zacieśnianie końcówek seta lub błędny warunek końca w danych).
     - Krzywa przesuwa p, ale linia jest postawiona w środku rozkładu, więc błąd średniej przenosi się na każdy szczebel.
  2. **Handicap punktowy: krzywa historii przeszacowana na liniach Superbetu o −29,5 pp** (najgorszy klucz siatkówki; przed offsetem — offset klucza −0,2953 jest już stosowany, więc skutkiem jest brak druku: 0 nóg `points_handicap` na kuponach 10-05..10-13). Różnica punktów zależy od liczby setów i od tego, jak ciasne są sety; model ma sety za luźne (sd udziału 0,059 vs 0,044 u M).
  3. Brak tempa ligi: suma punktów zależy w modelu tylko od udziału, nie od ligi. Grep: `league_rates` wchodzi tylko przez iloraz eh/(eh+ea) w `simulate:389`; poziom eh+ea jest odrzucany.
- **Rozwiązanie:**
  - (a) Model Egidi i Ntzoufras: punkty przegranego seta jako ucięty NB z parametrami drużyn plus składnik przewag. Rozkład długości seta byłby fitowany wprost na wynikach setów, które mamy (period1..5 w listingach) (https://arxiv.org/abs/1911.01815).
  - (b) Minimalnie: kalibrator długości seta per płeć × liga (średnia punktów przegranego przy danej różnicy udziałów).
  - Miejsce: nowa funkcja seta w `score_model._volleyball`.
  - Pomiar: walk-forward 2025-09..2026-09 (jak w `fitted_from`). Metryki: log-loss `points_total` i `points_handicap` na liniach syntetycznych oraz luka realizacja−p na liniach Superbetu z `data/line_evidence/rows_before_<d>`. Próg: luka drukowalna `points_handicap` w CI obejmuje 0.
- **Nakładanie się:** "ZINB, empiryczne i mieszane rodziny" odrzucono dla liczników piłki; to inny problem (długość seta w procesie z regułą stopu), nowy dowód to diagnostyka powyżej.
- **Priorytet / nakład:** **P1 / M** (największy zmierzony błąd krzywej w obszarze; w druku zdjęty offsetem, kosztem jest utracone pokrycie).

##### set_winner (744), set_points_total (782), set_points_odd_even (781), set_extra_points (100077 "Czy set na przewagi")
- **Gdzie liczone:** p z tej samej symulacji (`line_probability`); `actual_value` z regułą 15 dla 5. seta (`shadow.py:913+`, linia `target = 15 if ...`). Pewność **tylko z linii Superbetu** (`SETTLED_ONLY_FAMILIES`, `sport_confidence.py:209`).
- **Braki:**
  1. Historia ich nie ocenia, bo nie ma ich w `HISTORY_MARKETS["volleyball"]` (`sport_confidence.py:205`), a `PERIODS` nie ma `volleyball` (`:207`) i `market_periods` (`:580`) zwraca `()`. Krzywe: `set_extra_points` NO_FIT_BUCKET (n=10 linii w evidence), `set_points_total` n=172. Bez krzywej i z małym n te rynki praktycznie się nie drukują.
  2. `set_extra_points`: model i.i.d. zaniża częstość przewag (M 9,7% vs 12,3%, K 8,6% vs 9,9%; zmierzone, idealny udział). Side-out 0,65 daje 11,2% u M.
  3. Set N jest symulowany bez informacji, że set 4 istnieje tylko przy 2:1 / 1:2. Rynek rozlicza Superbet, a `actual_value` zwraca None dla nierozegranego seta; zgodność z regulaminem (void czy przegrana) niesprawdzona.
- **Rozwiązanie:** dodać `"volleyball": (1, 2, 3, 4, 5)` do `PERIODS` i 744/782/781/100077 do `HISTORY_MARKETS["volleyball"]`, po poprawie modelu długości seta (wyżej). Dane już są (wyniki setów w listingach). Pomiar: `fit_sport_confidence.py --sport volleyball --dry-run`, holdout jak w `fitted_from`; F6 `MAX_OVERSTATEMENT`. Zmiana tego, co drukuje, więc przełącznik w `epochs`.
- **Nakładanie się:** odwraca decyzję plan F4 / operatora z 2026-10-07 (rynki setowe tylko z rozliczonych linii; komentarz `sport_confidence.py:208`), więc wymaga zgody operatora.
- **Priorytet / nakład:** P2 / S (krzywe), zależne od P1.

##### points_odd_even (200896)
- **Gdzie liczone:** symulacja. Krzywa `points_odd_even|*` ma jeden kubeł 0,49/0,51 (`next.json`).
- **Braki:** rynek z definicji bliski 0,5; model nie ma tu przewagi. Nic do dodania poza poprawną długością seta.
- **Priorytet / nakład:** P3 / -.

##### Niezmapowane siatkówki (`market_coverage.py:502-511`)
- **Lista:**
  - `vb.sets_count` ("dokładna liczba setów") i `vb.exact_sets_derived` ("X wygra seta", "czy będzie 4./5. set", "wygra dokładnie N setów") to funkcje `exact_sets`. Do wyceny wystarczy mapper (`market_coverage` oznacza je `_m`, czyli MAPPABLE).
  - `vb.set_and_match` ("N. set/mecz") i `vb.set_points_handicap` wymagają łącznego rozkładu z symulacji (jest).
- **Rozwiązanie:** wejść przez `MAPPABLE_FAMILIES_FROM_UTC` (czeka na operatora) dla dwóch pierwszych; dwa ostatnie dopisać jako `MarketSpec` w `shadow.MARKETS["volleyball"]` po poprawie długości seta.
- **Priorytet / nakład:** P3 / S-M.

#### CS2

##### map_winner ("X wygra N. mapę")
- **Gdzie liczone:** `cs2_engine.py:781` (`model_probability`) przez `RatingModel.p_map:343`. Krzywa `map_winner|TEAM` z historii (`sport_confidence._cs2_series_rows:979-985`).
- **Model teraz:** Elo mapowe drużyny K=24 albo Elo graczy z ostatniego składu (gdy oba składy mają ≥3 mapy i fit ≥200). Kalibracja `sigmoid(a + b·gap)`, `a` to "gospodarz Sofascore" (wygrywa 54% map, `:326`).
- **Braki:**
  1. **Ta sama liczba dla mapy 1, 2 i 3.** `line.map_nr` nie jest czytany w `model_probability` (grep `map_nr` w `cs2_engine.py`: brak). W historii ta sama p idzie na każdą mapę (`sport_confidence.py:981-985`).
  2. **Brak puli map:** `map_name` jest w `cs2_map`, ale nie w `load_history` (`:388-398`). Siła drużyny per mapa i wybór mapy (pick: mapa wybrana przez drużynę A to jej mocna mapa) nie istnieją.
  3. **Brak strony startowej.** Zmierzone surowo: udział rund 1. połowy strony 5 na Nuke 0,552 vs strona 4 0,489, Train 0,582 vs 0,449, Mirage 0,555 vs 0,481, Anubis odwrotnie 0,501 vs 0,539. Która strona to CT: podejrzenie, że 5 = CT (zgodne ze znaną CT-stronnością Nuke).
  4. Brak LAN/online i rangi turnieju (`unique_tournament_id` jest w `cs2_series`, nieczytany).
  5. Brak niepewności ratingu (Glicko RD) i resetu po przerwie.
  6. Stand-in i zmiana składu: Elo graczy bierze **ostatni** skład (`PlayerEloBook.lineup`, `:289`), a ogłoszonego składu nie zna.
- **Rozwiązanie:**
  - (a) Elo mapowe per (drużyna, mapa) jako odchylenie od Elo drużyny, ściągnięte K pseudo-mapami. Wygładzanie Laplace'a (wygrane+5)/(mapy+10) jak u Petri i in. (2021), którzy używają per-mapowego win rate drużyny jako kontekstu wyboru mapy; https://ar5iv.labs.arxiv.org/html/2106.08888 (otwarte).
  - (b) Przed meczem mapa 1/2 nie jest znana (veto kilka minut przed startem; Sofascore podaje `map_name` po fakcie). Dlatego p mapy N = mieszanina po mapach ważona historycznymi pickami i banami obu drużyn (te same dane).
  - (c) Glicko-2 zamiast Elo: Bober-Irizar, Dua i McGuinness (2024) porównali Elo, Glicko2 i TrueSkill na CS:GO; https://arxiv.org/abs/2410.02831 (otwarte, abstrakt bez liczb).
  - Miejsce: `cs2_engine.EloBook` / `RatingModel.p_map(team1, team2, home, map_nr)`.
  - Dane: `cs2_map.map_name`, `map_order`, `home_starting_side`, `home_period1/2`.
  - Pomiar: walk-forward jak `elo_backtest` (`:858`) i `cs2_walk_forward_rows`. Metryka: Brier/log-loss mapy na ostatnich 40%, bootstrap po seriach, jak przy `SERIES_KAPPA`. Próg: CI różnicy < 0.
- **Nakładanie się:** "exponential decay" odrzucono dla piłki; Glicko to nie decay, tylko niepewność. Pooling drużyna-mapa to ściąganie stałym K (jak `K_ROUNDS`), nie hierarchiczny Bayes.
- **Priorytet / nakład:** P2 / M (mapa per drużyna), P3 / S (Glicko).

##### match_winner ("X wygra mecz")
- **Gdzie liczone:** `cs2_engine.py:784` (`series_distribution`, **stałe p**). Historia: `sport_confidence.py:989` tak samo.
- **Braki:**
  1. Niespójność: rynki serii używają `series_distribution_mixed` κ=6 (`:763-775`), bo stałe p "overpredicted three-map series" (komentarz `:86-91`; pomiar κ `:93-102`). Zwycięzca serii ma model, którego wada jest zmierzona w tym samym pliku.
  2. Brak `best_of` po stronie fixtures: od v2 brak liczby (`run_sport_confidence.py:169`). Poprawne, ale pokrycie zależy od SPORT_IDENTITY.
  3. Sekwencja veto: w bo3 mapa 1 to pick drużyny A, mapa 2 pick B, decider to mapa resztkowa; model traktuje mapy jako wymienne.
- **Rozwiązanie:** `match_winner` z `series_distribution_mixed` (jedna funkcja dla wszystkich rodzin serii), następnie per-mapowe p (wyżej) w łańcuchu A-pick/B-pick/decider. Pomiar: log-loss `match_winner` walk-forward, stałe vs mieszane; przełącznik `epochs`, bo zmienia p, a krzywą trzeba przefitować.
- **Priorytet / nakład:** P2 / S.

##### maps_total, maps_handicap, team_maps, exact_maps (serie)
- **Gdzie liczone:** `cs2_engine.py:763-775` (`series_distribution_mixed`, `series_side_p:184`). Krzywe historyczne (`_cs2_series_family_rows:891`).
- **Braki:**
  1. κ=6 globalne, a nie per format czy poziom; bo5 ma 117 serii w bazie, więc i tak cienko.
  2. Mapy w serii nie są wymienne (pick/decider, wyżej).
  3. `maps_handicap|TEAM` przeszacowany w holdoucie 0,6-0,7 o +0,0547 (`next.json` `not_calibrated`); na Superbecie +5,5 pp [−5,0; +15,0], n=44.
- **Rozwiązanie:** p mapy N z modelu mapa×drużyna, potem rozkład serii jako iloczyn różnych p (pick A, pick B, decider) zamiast potęgi jednego p. Mieszanie Beta zostaje dla dnia/formy. Pomiar: log-loss `exact_maps` (to zmierzono przy κ: 1,3154).
- **Priorytet / nakład:** P2 / M.

##### map_rounds_handicap ("handicap rund N. mapy")
- **Gdzie liczone:** `cs2_engine.py:808-819`, wyścig rund MR12 z dogrywkami 6-rundowymi (`map_score_distribution:510`) i szokiem sd 0,12 (`:547`). Krzywa: brak (NO_FIT_BUCKET), więc tylko line evidence (3 708 linii / 190 serii; brak drukowalnego podsumowania).
- **Braki:**
  1. Rundy niezależne poza jednym szokiem mapy. Brak pistoletówek, ekonomii, zmiany stron i autokorelacji rund. Pandascore (2022) modeluje zależność od poprzedniej rundy (Markov binomial, δ≈0,35) i podaje, że prosty model przeszacowuje bliskie mecze i nie docenia rozjazdów; https://www.pandascore.co/blog/cs-go-round-modeling (otwarte; MR15, sprzed CS2).
  2. Brak strony i mapy (wyżej).
  3. Brak historycznej krzywej, choć rozkład dałoby się ocenić na 25 669 mapach z rundami.
- **Rozwiązanie:**
  - Dwie połowy po 12 rund z p_round zależnym od strony per mapa (`home_period1/2`, `home_starting_side`).
  - Autokorelacja rund jako parametr Markowa (δ fitowane na kolejności... **brak danych runda po rundzie** w bazie, są tylko połowy). Wykonalne: p(CT) i p(T) per mapa; δ zastępuje obecny szok.
  - Dodać `map_rounds_handicap` do wierszy historii (`_cs2_series_rows`), żeby powstała krzywa.
  - Pomiar: Brier progowy marginesów, jak przy `ROUND_SHOCK_SD` (0,17348 na 3 047 mapach).
- **Priorytet / nakład:** P2 / M.

##### map_rounds_total ("suma rund N. mapy")
- **Gdzie liczone:** `cs2_engine.py:822-830`, czyli **stopa bazowa całej historii**.
- **Braki:**
  1. Nie zależy od meczu. Uzasadnienie w kodzie: próbki drużyn nie niosły nic i wyścig rund był równy bazie (0,1924 vs 0,1918, `:544-546`).
  2. Mapa niesprawdzona jako wejście. Zmierzone surowo: P(suma > 21,5) od 0,430 (Inferno, n=3 210) do 0,478 (Anubis, n=1 730); średnia 21,33 vs 21,70. Mały efekt, bez testu istotności.
  3. Bliskość meczu (|p_map − 0,5|) powinna skracać lub wydłużać mapę. Wyścig rund to robi, ale "nie pomógł", co sugeruje, że rozkład ma złą wariancję (podejrzenie).
- **Rozwiązanie:** baza per mapa (mieszanina po mapach jak wyżej) plus człon bliskości z wyścigu rund z poprawioną zależnością rund. Pomiar: Brier progowy linii 19,5-23,5 vs obecna baza, walk-forward.
- **Priorytet / nakład:** P3 / S.

##### map_team_rounds ("X - liczba rund na N. mapie"; LINE_OUTSIDE_FIT poza 9,5-12,5)
- **Gdzie liczone:** `cs2_engine.py:838-841` (`shrunk_frequency:651`). Historia: `sport_confidence.py:1003-1019` na liniach `CS2_TEAM_ROUND_LINES` (`:230`). Linie poza nimi to `LINE_OUTSIDE_FIT` (`:238-249`).
- **Braki:**
  1. **Przeciwnik nie istnieje:** częstość własnych rund drużyny niezależnie od rywala. Rundy drużyny są ≥13 wtedy i tylko wtedy, gdy wygra mapę albo przegra w dogrywce (udział dogrywek 11,4% map, zmierzone), więc OVER 12,5 to w praktyce `map_winner` plus mała poprawka.
  2. Line evidence: OVER −21,6 pp [−32,9; −10,9] (66 linii / 24 serie; poniżej `MIN_OFFSET_GAMES` 30, więc w druku działa tylko offset puli CS2 −3,5 pp; druk blokuje sama krzywa i cap pasma, 0 nóg na kuponach 10-07..10-13).
  3. Krzywa nie zna linii, stąd łata `FITTED_LINES`.
- **Rozwiązanie:** p z `map_distribution_for(p_map)` (`cs2_engine.py:565`), czyli z tego samego wyścigu rund co handicap. Wtedy linia 6,5 jest wyceniona tak samo poprawnie jak 12,5 i `LINE_OUTSIDE_FIT` przestaje być potrzebne. Pomiar: walk-forward, log-loss na `CS2_TEAM_ROUND_LINES` plus luka na rozliczonych liniach Superbetu; przełącznik `epochs`.
- **Nakładanie się:** to dokładnie pozycja "queued: CS2 map_team_rounds from the round race" w CLAUDE.md. Nowe jest tylko zmierzone −21,6 pp z pliku evidence z 2026-10-13.
- **Priorytet / nakład:** **P1 / S**.

##### team_kills ("X - liczba zabójstw na N. mapie")
- **Gdzie liczone:** `cs2_engine.py:736` (`team_kills`) i `count_p:611` (NB albo normal). Tylko line evidence (268 linii / 66 serii, bez drukowalnego podsumowania).
- **Braki:**
  1. Brak liczby rund: zabójstwa drużyny ≈ (rundy mapy) × (zabójstwa na rundę). Korelacja zabójstw gracza z rundami 0,592 (zmierzone).
  2. Brak siły rywala i wyniku mapy: 15,94 vs 12,71 zabójstwa gracza w wygranej i przegranej (zmierzone).
  3. Próbka to 20 ostatnich map niezależnie od rywala i mapy.
- **Rozwiązanie:** E[kills] = Σ_rozkład_rund (rundy) × KPR drużyny skorygowane o KPR-przeciw rywala (atak×obrona na zabójstwach na rundę). Rozkład rund z wyścigu rund, wariancja NB warunkowo na rundy. Dane: `cs2_player_map.kills`, `cs2_map.home_rounds/away_rounds`. Pomiar: log-loss linii syntetycznych (mediana ±k) walk-forward vs obecne `count_p`; bootstrap po seriach.
- **Nakładanie się:** "per-team dispersion" i "ZINB" odrzucone dla piłki. To nie dyspersja, tylko średnia warunkowa (ekspozycja w rundach).
- **Priorytet / nakład:** P2 / M.

##### player_kills / player_deaths / player_assists / player_headshots ("zawodnik - zabójstwa na N. mapie")
- **Gdzie liczone:** `cs2_engine.py:843-848` (`player_values:710`, `count_p:611`). Tylko line evidence (ok. 1 300 linii / 64-66 serii każda).
- **Braki:**
  1. Jak `team_kills`: brak ekspozycji w rundach i brak rywala (zmierzone wyżej).
  2. Brak udziału gracza w zabójstwach drużyny (rola: AWPer, entry). Dzielenie team KPR przez udział gracza stabilizuje próbkę 20 map.
  3. `adr`, `kast` i `first_kills_diff` są w bazie, a nieczytane (`load_history:407-419` czyta tylko K/D/A/HS).
  4. Deaths ograniczone przez rundy (komentarz `:614-616`), co nie jest modelowane wprost.
  5. Headshots = kills × HS%; HS% gracza jest stabilniejszy niż surowa liczba (podejrzenie).
- **Rozwiązanie:** kills_gracza ~ NB(średnia = rundy × KPR_drużyny × udział_gracza × korekta rywala). Headshots jako dwumian(kills, HS%). Deaths ≈ rundy − przeżycia, z KAST. Ta sama infrastruktura co `team_kills`. Pomiar: jak wyżej, per rodzina.
- **Priorytet / nakład:** P2 / M.

##### Niewycenione: rounds_total, rounds_handicap, team_rounds (serie), map_rounds_odd_even
- **Gdzie:** `cs2.parse_line` je czyta (`cs2.py:290-317`, `:278`); `MODELLED` ich nie ma (`cs2_engine.py:113`), więc `model_probability` zwraca None.
- **Rozwiązanie:** splot rozkładów wyniku mapy (`map_distribution_for` per mapa) po rozkładzie serii (ile map i kto wygrał każdą). Parzystość z tego samego rozkładu. Wszystko jest w kodzie; brakuje funkcji składającej. Pomiar: krzywe historyczne jak rodziny serii.
- **Priorytet / nakład:** P3 / S-M.

##### Niezmapowane CS2 (`market_coverage.py:521-535`)
- **Lista:** `cs2.overtimes` (liczba dogrywek), `cs2.map_kills_total`, `cs2.map_winner_rounds`, `cs2.map_exact`, `cs2.map_winner_3way`. Wszystkie to funkcje rozkładu wyniku mapy (wyścig rund) albo sumy zabójstw (model ekspozycji wyżej).
- **Priorytet / nakład:** P3 / S po poprawie wyścigu rund.

### Braki wspólne dla obszaru

1. **Brak modelu długości jednostki gry.** W siatkówce długość seta jest za krótka i sety za luźne; w CS2 zabójstwa nie znają rund. Oba sporty mają mechanizm wyścigu do celu, który daje rozkład długości; użyć go spójnie dla wszystkich rynków "ile".
2. **Kontekst meczu nieobecny:** h2h (grep `h2h` w `score_model.py` i `cs2_engine.py`: brak), rest/travel (`b2b_delta` 0, nie dla siatkówki), LAN/online i ranga turnieju (CS2), płeć na poziomie akcji (siatkówka).
3. **Rynki zależne od sesji (set, mapa) nie są indeksowane sesją:** siatkówka nie liczy setów z historii (`HISTORY_MARKETS` i `PERIODS`, decyzja operatora 10-07), CS2 daje tę samą p dla mapy 1, 2 i 3.
4. **Pewność rynków bez krzywej historycznej** (rundy mapy, zabójstwa, rynki setowe) opiera się na 60-200 seriach Superbetu; dopisanie ich do wierszy historii (`walk_forward_rows`, `_cs2_series_rows`) daje dziesiątki tysięcy wierszy.
5. **Krzywa historii siatkówki jest przeszacowana o −13,4 pp na drukowalnych liniach (przed offsetem; offset sportu −0,134 jest już stosowany).** CLAUDE.md mówi o tym jako o "kwestii krzywej" tylko dla koszykówki; siatkówka ma ten sam znak i większą skalę.

### Czego nie sprawdziłem

- Diagnostyka siatkówki (`vb_iid.py`) jest **w próbie**: symulacja z udziałem zrealizowanym w tym samym meczu. To wyrocznia, nie test OOS; mówi, że model i.i.d. nie odtwarza długości setów nawet w najlepszym przypadku, ale nie mierzy zysku z poprawy. Płeć wzięta z `sofascore_gender`; nieznana płeć liczy się jako "M".
- Nie sprawdziłem, czy w danych siatkówki są "złote sety" albo formaty inne niż bo5 do 25/15 (odfiltrowałem mecze z setem 1-4 poniżej 25 pkt).
- Znaczenie kodów `home_starting_side` 4/5 (CT/T) nie zostało zweryfikowane; liczby per mapa są surowe, bez testu istotności i bez kontroli siły drużyn (kto wybiera stronę, zależy od picku).
- Nie mierzyłem OOS żadnej z proponowanych zmian CS2 (mapa×drużyna, Glicko, ekspozycja rund).
- Nie czytałem `settle_cs2.attach_model` ani pełnego `fit_sport_confidence.py`; nie sprawdzałem, jak Superbet rozlicza set 4/5 nierozegrany (void czy przegrana) dla 744/782.
- Literatura nieotwarta: Xenopoulos i in. (2020) "Valuing Player Actions in CS:GO" (arXiv 2011.01324, tylko wynik wyszukiwarki); pełny tekst Egidi i Ntzoufras (post-print zwrócił 403, otwarty był tylko abstrakt arXiv).
- `data/line_evidence/rows_before_*` nie był czytany; liczby line evidence wzięte z `config/sofa_superbet_line_evidence.json` (fitted 2026-10-13T07:40Z, plik zmodyfikowany w drzewie roboczym), bez weryfikacji zakresu dni dla sportów.

Źródła otwarte: https://ideas.repec.Org/a/bpj/jqsprt/v10y2014i2p8n9.html · https://arxiv.org/abs/1911.04541 · https://arxiv.org/abs/1911.01815 · https://ar5iv.arxiv.org/html/1911.08791 · https://ar5iv.labs.arxiv.org/html/2106.08888 · https://arxiv.org/abs/2410.02831 · https://www.pandascore.co/blog/cs-go-round-modeling

# Część 6

## Warstwy wspólne (SAMPLES, środek SHEET, prior i siła ligi, krzywe, line evidence, bramki kształtu, flagi kontekstu, analitycy) - audyt kontekstu meczu, 2026-10-13

Zakres: maszyneria, przez którą przechodzi **każdy** rynek każdego sportu, oceniana pod kątem tego, czego brakuje o **interakcji dwóch stron** (przeciwnik, styl, h2h, liga, faza sezonu, odpoczynek, składy). Tylko odczyt: żaden plik repo nie został zmieniony, pipeline nie był uruchamiany, bez mostu i bez Superbetu. Liczby oznaczone **[zmierzone]** policzyłem sam z artefaktów `runs/sofa/<d>/` (skrypty w scratchpadzie `m/cross.py`, `m/gap.py`) albo przytaczam z plików dowodów w repo (z nazwą pliku); reszta to **[podejrzenie]**.

### Podsumowanie

1. **Próbka nie zna przeciwników swoich meczów.** `Observation` (`src/bet/sofa/contracts.py:129-146`) ma `opponent` tylko jako nazwę, bez id, bez siły i bez wartości „przeciw”. Dla rynków `*_for` nie ma obserwacji `*_against` (skill `football-analysis/SKILL.md:176-179`: „We hold no `*_against` observation”). Dostosowanie do przeciwnika istnieje tylko w ratingu (`football_rating.py`), który w piłce daje **połowę** środka (`W_FOOTBALL_RATING = 0.5`, `football_rating.py:125`, `run_sheet.py:1205-1215`). Rynków `UNRATED_MARKETS` (`football_rating.py:126-136`: `corners_total`, połowy rożnych, `cards_points_for`, `offsides_total`) to nie dotyczy wcale, podobnie propsów zawodników.
2. **Operator źle opisał wzór sumy - ale wniosek jest trafny.** Pula sumy (`run_sheet.py:1066-1069`, `deduplicate_observations`) ma średnią ≈ ½[(A_for + A_against) + (B_for + B_against)] = ½[(A_for + B_against) + (B_for + A_against)]. W modelu addytywnym to **jest** estymator „X_for + Y_against”, uśredniony po dwóch kierunkach. Wada leży gdzie indziej. A_for i A_against zarobiono przeciw **dawnym** przeciwnikom A, a nie przeciw B (siła terminarza, poziom ligi). Do tego interakcja jest multiplikatywna (Maher), więc dominator słabej ligi wnosi zawyżone „for” i zaniżone „against” bez żadnej korekty. To jest wzorzec Aktobe.
3. **Wzorzec Aktobe w połowie środka i w całych UNRATED.** Siła ligi (`LINKED_BY_STRENGTH`, sigma per domena i metryka, `football_rating.py:140-170`, `:748-768`) działa tylko w ratingu. Połowa środka z próbki i prior ligi (`resolve_prior`, `run_sheet.py:491-541`) jej nie mają. **[zmierzone, mało danych]** Na 6 dniach (10-07..10-12) `corners_for` strony z **silniejszej** domeny skończył o +1.65 [+0.37; +3.29] rożnych powyżej średniej próbki (n=13 stron), a strony ze słabszej o -0.44 [-1.82; +0.89] (n=14). Kierunek jest zgodny z hipotezą, ale n jest za małe. W `goals_for`, gdzie rating działa, wzoru nie ma.
4. **h2h nie ma żadnej wagi i w praktyce prawie nie istnieje.** Kubełek h2h to mecze, które przypadkiem wpadły do ostatnich 10 (`samples.py:968-970`, `:1477-1480`). W puli sumy jest deduplikowany, więc mecz h2h liczy się **raz**, jak każdy inny (`run_sheet.py:101-118`), a nawet zajmuje miejsce w obu dziesiątkach. **[zmierzone]** 10-12: h2h niepusty w 22 z 143 meczów piłki i 5 ze 105 tenisa, średnio 0.17 / 0.05 obserwacji na mecz. Literatura daje h2h mało ponad rating (Goddard i Asimakopoulos 2004: wynik zeszłorocznego meczu tych drużyn ma współczynnik -0.037, istotny tylko na 10%, efekt „odwrócenia”). To niski priorytet, ale tani do zmierzenia.
5. **Krzywe pewności opisują inny estymator niż ten, który drukuje.** Replay, z którego fitowane są krzywe piłki, **nie** odtwarza ratingu w środku (`calibrate_from_cache.py:1064-1072`: „What is NOT replayed... the football rating's centre (W_FOOTBALL_RATING)”). Żywy SHEET miesza go w połowie. Każda poprawka kontekstu w środku musi więc wejść do replayu, bo inaczej krzywa jej nie widzi. Tak samo jest z dzisiejszym ratingiem.
6. **Krzywe nie warunkują na kontekście.** Klucz to `rynek|kierunek` x kubełek p (`fit_confidence.py:56` EDGES) plus klasa: kobiety, kobiety w tenisie, puchar drużynowy (`confidence.py:504-537`, `:1334-1350`). Line evidence ma ten sam klucz (`line_evidence.py:148-150`). Żadna krzywa nie zna fazy sezonu, statusu linku ligi (UNLINKED jest po prostu odrzucany), wielkości próbki, luki siły ani różnicy klas.
7. **Faza sezonu jest zmierzona i niewdrożona.** To najsilniejsza ze zmierzonych cech kontekstu (`docs/sofa/evidence/model_defects_2026-10-05.md` §5): goals_total -0.00173 [-0.00200; -0.00147] log-loss, ostatnie 2 kolejki +11% goli. Nie jest zaimplementowana (to kandydat F3.2 na refit; `MODEL_FIXES_FROM_UTC`, `epochs.py:171`, bramkuje tylko poprawki F2.2: dyspersję tenisa i notatkę OTHER_DIVISION_SAMPLE), a grep `season_phase|round_share` w `src/bet/sofa` i `run_sheet.py` nic nie zwraca. CLAUDE.md mówi to samo o 1X2/DNB („a history curve over-states the season start by 2.4-4 pp”).
8. **Bramka MODEL_ABOVE_OWN_SAMPLE karze właśnie dostosowanie do przeciwnika.** Usuwa nogę, gdy p_central przekracza surowy hit rate próbki o > 0.15 (`confidence.py:623`, `run_confidence.py:819-830`). Każda poprawka kontekstu, która odsunie p od surowej próbki w górę (np. słaby rywal), zostanie automatycznie zdjęta. Przyszły model matchupu trzeba mierzyć **razem** z tą bramką.
9. **Flagi kontekstu tylko się wyświetlają.** Dotyczy to `MAKEUP_FIXTURE`, `LONG_LAYOFF`, `CONGESTED` (`schedule.py:1-22`, `run_confidence.py:260-263`, `:881-884`) i stawki meczu (`stakes.py`). Zmierzono przerwę i natłok (stawka bez testu log-loss): przerwa ≥ 21 dni daje gole -0.122 [-0.155; -0.092] względem średniej próbki, ale zysk w log-loss jest znikomy (-0.00015). Rola tylko informacyjna jest zgodna z pomiarem (zysk rzędu 1e-4).
10. **Kontekst żyje u analityka, który może tylko usuwać.** Werdykty to KEEP / WATCH / NO_BET (`sofa-analysis-core/SKILL.md:273-283`). Nic nie może podnieść pewności ani dodać nogi. **[zmierzone z ledgera, bez CI]** Nogi zdjęte odczytem w 10-09..10-12: 156 nóg, -17.19 j. (-11.0%), wobec kuponu 6 344 nóg, -292.3 j. (-4.6%). Kierunek „usuwa gorsze” jest słaby i nieistotnie zbadany.

### Mapa obliczeń

```
SAMPLES (samples.py)
  get_historical_events :264  -> ostatnie sample_n=10 (config.py:121) ukończonych, bez towarzyskich,
                                 bez rezerw (reserve_squads), tenis: ta sama nawierzchnia
  gole ligowe: pick_same_competition (comparability.py:205-228, samples.py:1409-1446), >=5 meczów
  Observation(value, opponent=NAZWA, venue, competition_id)  contracts.py:129   <- brak opp_id/against
  h2h = mecze już obecne w side_a/side_b (samples.py:968-970, 1477-1480)
          │
SHEET (scripts/sofa/run_sheet.py)
  suma:   pool = dedup(side_a ∪ side_b ∪ h2h)  :1066-1069   (jeden mecz raz)
  strona: obs = side_a | side_b                :1071-1090
  prior:  fitted liga | dzień (bez własnej próbki) | ligi stron (PRIOR_FROM_TEAMS_LEAGUES) | globalny
          resolve_prior :491-541 ; tenis: tier x płeć x nawierzchnia (tennis_prior.py)
  centre = n/(n+K)*mean + K/(n+K)*prior        :1180-1189 (K per rynek od 10-09)
  piłka, rynek oceniany: centre = 0.5*rating + 0.5*centre   :1195-1215
         rating = league_rate x home x att_i x def_j x siła ligi (football_rating.py:931-982)
  tenis: games_won_for/handicap/most_games z ratingu Elo+kontekst (tennis_rating.py:15-40)
  spread: sheet_predictive_sd (NB/normal; alfa dyspersji od 10-09)
          │  p_central  (cena wyłączona)
CONFIDENCE (run_confidence.py, confidence.py)
  krzywa(rynek|kierunek|klasa, kubełek p)  -> realised_lo95   confidence.py:1334-1420
  line evidence (rynek|kierunek): min(krzywa+offset<=0, cap pasma ceny)  line_evidence.py
  bramki kształtu na surowej puli: LINE_BEYOND_SAMPLE, MODE_LOSES (run_confidence.py:789-794)
  MODEL_ABOVE_OWN_SAMPLE (p - hit rate próbki > 0.15 -> removed)          :819-830
  context_flags (schedule), stakes, peer, price_gap  -> tylko wyświetlane
          │
ANALITYCY (.claude/agents/sofa-analyst-*.md): KEEP/WATCH/NO_BET - tylko usuwa
SPORTY (score_model.py): RatingBook (att x def x dom x siła ligi) -> symulacja -> krzywa family|side
CS2 (cs2_engine.py): Elo mapy (+ Elo graczy z ostatniego składu) / próbki graczy
```

### Warstwa po warstwie

#### W1. Skład próbki - okno (SAMPLES; wszystkie sporty z próbką: piłka, tenis)
- **Gdzie liczone:** `src/bet/sofa/samples.py:264-300` (`get_historical_events`). Okno to `sample_n=10`, `min_sample=5` (`src/bet/sofa/config.py:121-122`). Przy golach ligowych działa `pick_same_competition` (`comparability.py:205-228`, `samples.py:1409-1446`).
- **Model teraz:** ostatnich 10 ukończonych meczów strony, z wagą równą. Wykluczenia: towarzyskie, walkowery, krecz (`is_completed_event`), mecze rezerw (`second_squad_matches`, `samples.py:637-654`), w tenisie inna nawierzchnia. Gole w lidze biorą tylko mecze REGULAR tej samej rozgrywki, jeśli jest ich co najmniej 5.
- **Wejścia:** wartość metryki, data, nazwa rywala, venue, competition_id, season_id (`contracts.py:129-146`).
- **Braki:**
  1. Brak id rywala i jego siły w obserwacji (`contracts.py:131-146`: pole `opponent: str`). Nie da się więc skorygować próbki o siłę terminarza bez ponownego odczytu cache. Grep `opponent` w `run_sheet.py`/`engine.py` daje brak użycia (wyświetla to tylko analityk).
  2. Brak wartości przeciw dla `*_for`. Z tej samej `/statistics` można by wziąć liczbę rywala, ale SAMPLES zapisuje tylko stronę (`samples.py:917-937`: `extract_metric(..., is_home)` dla jednej strony). Skill to potwierdza (`football-analysis/SKILL.md:176-179`).
  3. Reguła „ta sama rozgrywka” obejmuje tylko gole. Dla rożnych, strzałów i fauli zmierzono ją jako gorszą (`comparability.py:186-204`). W meczu pucharowym między ligami próbka rożnych to więc 10 meczów ligi krajowej, bez korekty poziomu ligi.
  4. Wszystkie obserwacje ważą tyle samo. Zanik wykładniczy został odrzucony (CLAUDE.md „declined”, `pooling_2026-10-08.md` `todayD` +2.2e-4), więc to nie jest brak, tylko decyzja.
- **Rozwiązanie:** korekta siły terminarza na poziomie obserwacji. Każdą obserwację `x_k` strony A przeskalować do „neutralnego” rywala: `x_k' = x_k / def_{opp_k}` (dla `*_for`) przy defensywie rywala as-of z `RatingBook`. Tak robi Maher 1982 i Wheatcroft 2020 (ratingi GAP ze strzałów i rożnych, `researchonline.lse.ac.uk/id/eprint/103712`, OTWARTE w `LITERATURA_2026-10-08.md` #8). Średnia jest wtedy „siłą własną”, mnożoną przez def(B) dzisiejszego rywala. Miejsce: `samples.process_historical_event` zapisuje `opponent_id` (nowe pole `Observation`, domyślnie None, żeby stare artefakty działały), a `run_sheet.process_fixture` liczy skorygowaną średnią. Dane: `sofa_listing_event` / indeks listingów ma `homeTeam.id`/`awayTeam.id`, a `RatingBook.teams` ma `defence` as-of. **Pomiar:** `scripts/sofa/measure_sample_composition.py` (ten sam odczyt co SAMPLES), wariant „próbka skorygowana o def rywala” kontra dzisiejsza. Metryki: log-loss po kalibracji (`lc_all` jak w `measure_pooling.py`) per rynek, bootstrap po meczach, cięcie 2026-06-09. Próg: górne CI < 0 na `corners_*`, `shots_*`, `fouls_*`. Potem replay w `calibrate_from_cache.py` i refit (zgoda operatora), switch w `epochs`.
- **Nakładanie się z „zmierzone i odrzucone”:** to nie jest pooling hierarchiczny (odrzucony) ani zanik wykładniczy. Rating już robi to dla rynków ocenianych, więc nowe jest przeniesienie korekty do **samej próbki** i do UNRATED, gdzie rating przegrał. Patrz W3.
- **Priorytet / nakład:** P1 / M.

#### W2. h2h (SAMPLES -> SHEET; piłka, tenis)
- **Gdzie liczone:** `samples.py:968-970` (`is_h2h = {home_id, away_id} == {fixture...}`), `:1449-1483` (kubełek bez duplikatów), `run_sheet.py:389` (prior dnia), `:1036-1039` (own_events), `:1066-1069` (pula sumy), `calibrate_from_cache.py:620-640` (replay odtwarza to samo).
- **Model teraz:** h2h to tylko mecze, które już są w ostatnich 10 którejś strony. W sumie jest deduplikowany: mecz h2h wchodzi raz, jak każdy inny (`run_sheet.py:101-118`). W rynku strony h2h nie występuje osobno (`calibrate_from_cache.py:908`: „h2h never reaches a per-side market”). Brak osobnego pobrania h2h i brak wagi.
- **Wejścia:** jak wyżej.
- **Braki:**
  1. Brak osobnego pobrania historii spotkań tych dwóch drużyn: grep `h2h` w `samples.py` pokazuje tylko flagę `is_h2h`, a w `client.py` nie ma endpointu h2h. **[zmierzone]** 10-12: piłka 22/143 meczów z h2h, średnio 0.17 obserwacji; tenis 5/105, średnio 0.05.
  2. Mecz h2h ma w sumie wagę mniejszą niż mecz zwykły. Zajmuje miejsce w obu dziesiątkach, a liczy się raz, więc pula ma 19 zamiast 20 meczów (`run_sheet.py:107-112`).
- **Rozwiązanie:** h2h jako **cecha reszty**, a nie jako waga w puli. Na historii (cache, mecze tych samych dwóch drużyn w ostatnich 3 latach, bez towarzyskich) liczyć `r_h2h = średnia(y_h2h - centre_as_of)` i testować `log(lam) = log(centre) + b * r_h2h * n_h2h/(n_h2h + k)`. Metoda jak w F3.2 (`measure_model_defects.py context --feature`, połowy parzystości id). Literatura: Goddard i Asimakopoulos 2004, *Journal of Forecasting* 23(1) (wersja robocza: `https://www.stat.berkeley.edu/~aldous/157/Papers/goddard.pdf`, OTWARTE, tabela 1). Ordered probit na 29 594 meczach angielskich, `LAST1` (wynik zeszłorocznego meczu tej pary) = -0.037 (SE 0.021), istotne tylko na 10%. Autorzy piszą „the effect appears to be relatively weak” i widzą raczej „revenge”, czyli odwrócenie. W tenisie Clegg i Cartlidge 2025 (arXiv:2510.20454, `https://arxiv.org/abs/2510.20454`, OTWARTE: streszczenie) pokazują, że informacja o nieprzechodnich zależnościach par (GNN na grafie meczów) nie bije Weighted Elo sama, ale w kombinacji „significantly outperforms Weighted Elo”. To słaby, ale niezerowy argument za h2h w tenisie. Miejsce: `tennis_rating.py` (cecha w warstwie kalibracji obok `dhigh`/`dtour`) i `football_rating`/SHEET (korekta środka). Dane: listingi w `sofa.db` (już są, bez mostu). **Pomiar:** log-loss poza próbą, próg górne CI < 0 w obu połowach id. Spodziewam się wyniku bliskiego zera **[podejrzenie z literatury]**.
- **Nakładanie się:** brak (h2h nie jest na liście odrzuconych). Nie myl z „re-ranking peers by ...”, który dotyczy kolejności nóg.
- **Priorytet / nakład:** P3 / S.

#### W3. Środek SHEET dla sum i rynków strony; UNRATED_MARKETS (piłka)
- **Gdzie liczone:** `run_sheet.py:1066-1069` (pula), `:1180-1189` (shrink K), `:1195-1215` (rating 0.5), `football_rating.py:931-982` (`FootballForecast.centre`; suma = home_exp + away_exp, `:974-975`), `football_rating.py:104-136` (`W_FOOTBALL_RATING`, `UNRATED_MARKETS`).
- **Model teraz:** dla rynków ocenianych `centre = 0.5 * (rate * home * att_i * def_j [* siła ligi]) + 0.5 * shrink(próbka, prior)`. Dla UNRATED tylko `shrink(próbka, prior)`.
- **Wejścia:** próbka, prior ligi, rating (Maher plus wygładzanie, przewaga gospodarza, siła ligi), K per rynek (od 10-09).
- **Braki:**
  1. `corners_total` i połowy rożnych są poza ratingem. Decyzja zapadła na **5 dniach** rozliczonych wierszy (09-18..22) po Brier, przy wyłączeniach dobranych na tych samych dniach (`football_rating.py:113-124`: „The exclusions were chosen on those same days”). Nie było pomiaru na historii (722k meczów w `pooling_2026-10-08.md`).
  2. Rating rożnych w sumie ma tylko `corners_for` x defensywa rywala. Brak członu „styl”, np. drużyna grająca niskim blokiem oddaje rożne (Gollan, Bellenger, Norton 2020, *JSSM* 19:78-83, `https://www.jssm.org/jssm-19-78.xml-abst`, OTWARTE: streszczenie: „opposition quality having a larger influence on game style than playing location”). Grep `possession|style` w `football_rating.py`: tylko komentarz o wygładzaniu (`:84`), bez kowariaty stylu.
  3. W ocenianych rynkach połowa środka to surowa próbka bez korekty terminarza (W1). Rating koryguje tylko swoją połowę.
  4. **[zmierzone, 6 dni 10-07..10-12, mecze wg noty ratingu goli]** Reszta `actual - centre` dla `corners_total` wynosi +0.55 [+0.27; +0.86] (518 meczów z linkiem LINKED) i +0.27 [-0.20; +0.81] (126 cross-league). Środek zaniżał rożne w tych dniach. `ladder_centre` (środek z ceny) zaniżał bardziej (+0.76), więc to wspólny dryf (pora sezonu?), nie kontekst meczu. Krótki odcinek, tylko do obserwacji.
- **Rozwiązanie:** (a) ponownie zmierzyć `UNRATED_MARKETS` na historii. Wariant „rating rożnych w środku sumy przy W ∈ {0.25, 0.5}” kontra dzisiejszy: `measure_pooling.py` ma już infrastrukturę centrum, wystarczy dodać centrum z `RatingBook` as-of. Metryka `lc_all` per rynek, cięcie 2026-06-09, bootstrap po meczach. (b) rating z cechą stylu: `log E[corners_i] = log rate + a_i + d_j + γ·(posiadanie_i - posiadanie_j)` albo wyraz interakcji `att_i x d_j x (shots_ratio)`. Tak robi model GJRM z parametrami zależnymi od zmiennych: van der Wurp i in. 2019, arXiv:1908.00823, OTWARTE w `LITERATURA` #15. Dane: `/statistics` w `sofa_event_stats` ma `ballPossession`, `totalShotsOnGoal` (od 2024-10). Miejsce: `football_rating.RatingBook` (dodatkowa metryka-kowariata) i replay w `calibrate_from_cache.py`. **Pomiar** jak w W1. Najpierw (a), bo jest tani.
- **Nakładanie się:** pooling EB, ZINB, kopuła t i DC zostały odrzucone. To nie są one. Odrzucenie rożnych z ratingu to decyzja z 5 dni, a nie z listy „declined”, więc ponowny pomiar jest uprawniony.
- **Priorytet / nakład:** (a) P1 / S; (b) P2 / L.

#### W4. Prior ligi i siła ligi; wzorzec Aktobe (piłka; RatingBook dzielony z hokejem, koszykówką, siatkówką)
- **Gdzie liczone:** `run_sheet.py:491-541` (`resolve_prior`), `:434-465` (`home_competition`), `:405-425` (prior dnia); `football_rating.py:140-170` (link i siła), `:748-768` (`link` → `LINKED_BY_STRENGTH`, `sigma_h - sigma_a`), `:931-960` (UNLINKED i tak dostaje rating; CONFIDENCE odrzuca), `run_sheet.py:965-974` (nota `CROSS_LEAGUE_UNLINKED`).
- **Model teraz:** prior to średnia ligi rozgrywek meczu (dopasowana albo z dnia). Jeśli rozgrywka (puchar) nie ma bazy, to średnia lig obu stron. Siła ligi sigma jest uczona tylko na meczach bez linku i działa tylko w ratingu (`expected(..., lf, cross=...)`). Ratio stron poza ligą są ściągane potęgą `CROSS_RATIO_POWER = 0.6`.
- **Braki:**
  1. Puchar z własną bazą (np. `goals_total` ma wpis dla 463: mean 2.8245, n=188; `config/sofa_league_baselines.json`) ściąga próbki obu stron do średniej pucharu. Każda próbka pochodzi jednak z innej ligi o innym poziomie. **[zmierzone: wpis istnieje]**. Dla `corners_total` 463 nie ma bazy, więc prior to średnia lig stron albo dzień.
  2. Połowa z próbki i cały środek UNRATED nie mają korekty siły ligi (grep `strength|sigma` w `run_sheet.py`: użycie tylko w nocie ratingu). **[zmierzone, mało danych]** `corners_for`, strona silniejszej domeny (|gap| > 0.1): reszta względem średniej próbki +1.65 [+0.37; +3.29], n=13; słabszej -0.44 [-1.82; +0.89], n=14; mecze LINKED +0.21 [-0.14; +0.58], n=213 (6 dni, `m/gap.py`). Kierunek zgadza się z Aktobe, n jest za małe na wniosek. Dla `goals_for` brak wzoru (+0.14 / +0.05), czyli rating działa.
  3. Przy UNLINKED noga jest odrzucana (`confidence.has_cross_league_unlinked_note`). To bezpieczne, ale traci mecze, które cena wyceniła. To decyzja, nie błąd.
- **Rozwiązanie:** przenieść `lf` (log luki siły) na próbkę. `x_k' = x_k * exp(±k·lf_metric)`, czyli każdy mecz próbki skalowany siłą domeny, w której go zarobiono, względem domeny dzisiejszego meczu. Dla sum: osobno `for` i `against` każdej strony, co wymaga W1.2. Literatura: Maher 1982 (`api.crossref.org/works/10.1111/j.1467-9574.1982.tb00782.x`, OTWARTE w `LITERATURA` #1) i Baio i Blangiardo 2010 (METADANE, #18) dla przenoszalności sił. Miejsce: `run_sheet.process_fixture` przed `deduplicate_observations`, `lf` z `FootballForecast.link_status` (już liczone). Dane: jest wszystko, `RatingBook.strength`. **Pomiar:** `measure_sample_composition.py` ograniczony do par cross-league (KNOCKOUT i europejskie puchary, ~kilkanaście tys. meczów w cache **[podejrzenie co do liczby]**). Wariant „próbka skalowana sigmą” kontra dzisiejszy, log-loss per `corners_for`/`corners_total`/`shots_*`, bootstrap po meczach. Próg: górne CI < 0. Uwaga na pomiar z 10-04 (`comparability.py:186-204`): ta sama rozgrywka dla pucharów pogarszała gole, więc trzeba testować skalę, a nie filtr.
- **Nakładanie się:** „league selection / gate tuning” to inna rzecz (wybór lig). Pooling EB został odrzucony, ale tu nie ma hierarchii, tylko istniejąca sigma.
- **Priorytet / nakład:** P1 / M.

#### W5. Krzywe pewności (CONFIDENCE; piłka i tenis `confidence.py`, sporty `sport_confidence.py`)
- **Gdzie liczone:** `confidence.py:1084-1116` (sekcje `Calibration`), `:1334-1420` (`realised`), `:504-537` (`match_class`), `scripts/sofa/fit_confidence.py:56` (EDGES), `sport_confidence.py:297-298` (`curve_key = family|side_class`).
- **Model teraz:** pewność to `realised_lo95` kubełka p dla klucza `rynek|kierunek` (albo rynku, albo puli sportu z capami K13/K13b), osobno dla klas kobiety / kobiety w tenisie / puchar drużynowy.
- **Braki:**
  1. Brak warunkowania na fazie sezonu (grep `round|season_phase` w `fit_confidence.py` daje brak). Zmierzone przesunięcie środka na końcu sezonu to +11% goli (`model_defects_2026-10-05.md` §5).
  2. Brak warunkowania na statusie linku ligi i luce siły. LINKED_BY_STRENGTH czyta tę samą krzywą co LINKED.
  3. Brak warunkowania na `n` próbki (ta sama krzywa dla n=5 i n=20, z puli sumy do 20). Pomiar pooling §6 pokazuje, że cienkie próbki zachowują się inaczej (nachylenie priora 0.54 przy n 3-7, wobec 0.44 dla goli ogółem).
  4. Krzywa piłki dopasowana bez ratingu w środku (`calibrate_from_cache.py:1064-1072`), a żywy środek go ma (`run_sheet.py:1205-1209`). Krzywa mapuje więc inny p_central niż drukowany. Rozbieżności nie zmierzyłem.
- **Rozwiązanie:** nie dzielić krzywych (każdy podział rozrzedza kubełki), tylko przenieść kontekst do środka (W1, W4, W6) i odtworzyć go w replayu. Krzywa zostaje jedna, ale opisuje estymator z kontekstem. Sprawdzian: `measure_calibration.py --from 10-09 --to 10-12` z podziałem po `link_rule`/fazie sezonu. Jeśli przerwa (realised - confidence) w podgrupie ma CI wykluczające 0, kontekst brakuje w środku. Osobno rzecz pilna: odtworzyć rating w replayu (`calibrate_from_cache.py`, kolejka CLAUDE.md „football joints with the football rating in their centre” obejmuje tylko łączne; marginalne też go nie mają).
- **Nakładanie się:** „beta / isotonic / spline calibration” odrzucone, tu tego nie proponuję.
- **Priorytet / nakład:** rating w replayu P1 / M; podziały diagnostyczne P2 / S.

#### W6. Kontekst terminarza, faza sezonu, stawka (schedule.py, stakes.py; piłka)
- **Gdzie liczone:** `schedule.py:1-60` (`SideSchedule`, `LONG_LAYOFF_DAYS=21`, `CONGESTED_7D=3`), `run_confidence.py:260-263`, `:881-884` (tylko `context_flags`), `stakes.py` (flagi `STAKES_*`, wyświetlane; CLAUDE.md „shown, never gated, never a correction”).
- **Model teraz:** nic z tego nie wchodzi do p.
- **Braki i pomiary w repo:** z `model_defects_2026-10-05.md` §5 (log-loss poza próbą, połowy id):
  1. runda (początek / koniec sezonu): goals_total **-0.00173** [-0.00200; -0.00147], goals_for -0.00111, corners_total -0.00034, żółte -0.00063. Przechodzi kryterium i nie jest wdrożona (grep: brak).
  2. odpoczynek / natłok: goals_total -0.00015 [-0.00023; -0.00008]. Pozostałe są w zerze.
  3. strona z innej ligi (awans / spadek): goals -0.00009..-0.00011.
  4. puchar / play-off: minimalne.
  5. stawka (six-pointer, top 4): efekt zmierzony w jednostkach rynku (`peer_choice_2026-10-08.md`: +0.9 fauli, +0.2 kartek), bez testu log-loss jako korekty.
- **Rozwiązanie:** wdrożyć **rundę** jako mnożnik środka `log(lam) = log(centre) + a + b·faza` (GLM Poissona z offsetem, współczynniki już dopasowane w `measure_model_defects.py`). Miejsce: `run_sheet.process_fixture` po shrinku, ten sam kod w `calibrate_from_cache.shrunk_centre`. Faza z `round_number` (jest w `02_fixtures.json`) i długości poprzedniego sezonu rozgrywek. Przełącznik: nowy w `epochs` albo rozszerzony `MODEL_FIXES_FROM_UTC` (dziś obejmuje tylko F2.2), razem z refitem. **Pomiar przed instalacją:** powtórzyć względem pełnego `p_central` replayu, a nie surowej średniej, bo tak zastrzega sam dokument („Wszystkie te pomiary są względem surowej średniej z próbki”).
- **Nakładanie się:** brak; zmierzone, ale niezaimplementowane (nie leży za żadnym przełącznikiem).
- **Priorytet / nakład:** runda P1 / M (refit); reszta P3.

#### W7. Bramki kształtu i MODEL_ABOVE_OWN_SAMPLE (piłka; kształt też tenis)
- **Gdzie liczone:** `confidence.py:950-982` (`line_is_beyond_sample`, `mode_loses`), `:620-660` (`MAX_OWN_SAMPLE_GAP=0.15`, tylko piłka, bez propsów), `run_confidence.py:785-831`.
- **Model teraz:** bramki czytają **surową pulę** (`side_observations(row)`). Brak przeskalowania o rywala czy ligę.
- **Braki:**
  1. LINE_BEYOND_SAMPLE i MODE_LOSES na puli z obu historii oceniają linię względem meczów **innych** par. Przy wzorcu Aktobe mod próbki słabej ligi nie mówi nic o dzisiejszym meczu.
  2. MODEL_ABOVE_OWN_SAMPLE z definicji usuwa nogi, w których środek (rating, prior, kontekst) różni się od surowego hit rate. Każde przyszłe dostosowanie do przeciwnika podniesie liczbę takich usunięć.
- **Rozwiązanie:** po W1/W4 liczyć bramki na **skorygowanych** obserwacjach (ta sama transformacja co środek). MODEL_ABOVE_OWN_SAMPLE porównywać ze skorygowanym hit rate. **Pomiar:** `scripts/sofa/measure_own_sample_gap.py` (już istnieje) w dwóch wariantach (surowa i skorygowana próbka), ROI i realised - confidence nóg usuniętych kontra pozostałych, bootstrap po meczach, dni 10-09.. .
- **Nakładanie się:** „gate tuning” jest odrzucony. To nie strojenie progu, tylko zmiana wejścia bramki, ale trzeba to powiedzieć operatorowi wprost.
- **Priorytet / nakład:** P2 / S (po W1).

#### W8. Line evidence (wszystkie sporty)
- **Gdzie liczone:** `line_evidence.py:1-45` (opis), `:66-75` (`PRICE_BANDS`), `:148-150` (`evidence_key = klasa:klucz`), `:284-310` (`read`).
- **Model teraz:** offset ≤ 0 i cap pasma ceny per `rynek|kierunek`. Cena jest tu jedynym nośnikiem kontekstu meczu: pasmo kursu niesie pośrednio to, co bukmacher wie o matchupie.
- **Braki:** offset i cap nie znają ligi ani linku. Klucz `corners_total|OVER` łączy Premier League i puchar azjatycki (grep `competition` w `line_evidence.py`: tylko `klass`).
- **Rozwiązanie:** brak nowej warstwy. Przy pomiarze W4 sprawdzić offset osobno dla cross-league (diagnostycznie: `fit_line_evidence.py --dry-run` z podziałem po `link_rule`). Strażnik obniża tylko, więc ryzyko jest jednostronne.
- **Nakładanie się:** „stricter price-band cap” i „offset per confidence-minus-price bin” odrzucone 10-12. Podział po lidze to inna oś, ale rozrzedzi komórki (MIN_CAP_CELL 20).
- **Priorytet / nakład:** P3 / S.

#### W9. Sporty mierzone: score_model (hokej, koszykówka, siatkówka)
- **Gdzie liczone:** `score_model.py:1-22` (opis: RatingBook, symulacja), `:218` (`b2b_delta: float = 0.0`), `:350-357` (użycie b2b), `:317-326` (`noise_mult`, BB_FRESHNESS), `sport_confidence.py:297-298` (klucz krzywej).
- **Model teraz:** att x def per okres, przewaga gospodarza, siła ligi (ta sama `RatingBook`), symulacja 4000 gier. Koszykówka ma wspólny szok tempa (wariancja), hokej pusty bramkarz.
- **Braki:**
  1. Back-to-back jest zaimplementowany, ale wyłączony: `b2b_delta = 0.0`, a grep `b2b_delta` w `config/` i `scripts/sofa/` nic nie zwraca. Brak pomiaru w repo.
  2. Hokej: brak bramkarza (grep `goalie` w `score_model.py` daje brak). Bramkarz to w literaturze NHL największa pojedyncza zmienna meczu **[podejrzenie, bez źródła otwartego]**.
  3. Koszykówka: tempo jest tylko w szumie, nie w środku (grep `pace` w `score_model.py`: komentarz w `:249`). Matchup tempa (szybki x wolny) nie jest modelowany.
  4. h2h, odpoczynek (poza bb_freshness), składy: brak.
- **Rozwiązanie:** (a) zmierzyć `b2b_delta` na historii skryptem `scripts/sofa/measure_score_history.py --params '{"b2b_delta": ...}'` (parametr już istnieje). Metryka: średni Brier progów, okna tune/test jak w `score_model.py:249`. (b) tempo jako druga metryka ratingu (posiadania z `/statistics` koszykówki, jeśli są w cache; **nie sprawdziłem**). Miejsce: `ScoreModel.expected`.
- **Priorytet / nakład:** (a) P2 / S; (b) P3 / M.

#### W10. CS2 (cs2_engine.py)
- **Gdzie liczone:** `cs2_engine.py:17-40` (rodziny), `:273-282` (Elo graczy z ostatniego składu, zmierzone -0.00148 Brier), `:342-351` (`p_map`: Elo graczy, gdy dopasowane, inaczej Elo drużyny, plus człon gospodarza).
- **Braki:** brak puli map i weta (grep nazw map w `cs2_engine.py` daje brak). `map_rounds_total` to bazowa częstość („the teams' samples carried nothing about the next map's length”). Statystyki graczy (kills) są bez siły rywala. Brak LAN / online i brak odpoczynku.
- **Rozwiązanie:** Elo per mapa (ogólny + mapa, jak blend nawierzchni w tenisie `tennis_rating.py:15`) i kills skorygowane o Elo rywala. Literatura: Bober-Irizar i in. 2024, arXiv:2410.02831, OTWARTE w `LITERATURA` #24 (porównanie Elo / Glicko2 / TrueSkill na CS:GO). **Pomiar:** walk-forward na `cs2_store`, Brier `map_winner`, bootstrap po seriach.
- **Priorytet / nakład:** P2 / M (osobny audytor CS2 prawdopodobnie to pokrywa).

#### W11. Tenis - wspólna część
- **Gdzie liczone:** `tennis_rating.py:15-40` (Elo nawierzchniowe; kalibracja z godzinami na korcie 78 h, powrotem > 21 dni, meczami w 7 dniach, formą, `dhigh`/`dtour`); `tennis_prior.py:1-30` (prior tier x płeć x nawierzchnia).
- **Braki:** asy, podwójne błędy i punkty serwisowe idą z próbki bez rywala. Asy zależą od returnu rywala (Klaassen i Magnus 2001, METADANE, #21, punkty na serwisie). grep `opponent` w `tennis_prior.py`: brak. h2h: przypadkowe (5/105 meczów 10-12).
- **Rozwiązanie:** asy_i ~ rate(tier, nawierzchnia) x serve_i x return_j (Maher na asach), w `tennis_prior`/`run_sheet`. Dane: `sofa_event_stats` tenisa. **Pomiar:** log-loss `aces_for` poza próbą.
- **Priorytet / nakład:** P2 / M (osobny audytor tenisa).

#### W12. Warstwa analityka (.claude/agents/sofa-analyst-*.md, skille)
- **Gdzie:** `sofa-analysis-core/SKILL.md:273-283` (werdykty usuwają), `football-analysis/SKILL.md:143-186` (h2h, rywal, venue, styl, sędzia: wszystko jako czytanie, nie liczba).
- **Model teraz:** kontekst (styl, h2h, stawka, absencje, sędzia) jest tylko u analityka, a ten może tylko zdjąć nogę.
- **Braki:** asymetria. Mecz, w którym kontekst **podnosi** pewność, nigdy nie zostanie wydrukowany, jeśli statystyka go nie przepuściła. **[zmierzone, ledger 10-09..10-12, bez CI]** removed:reads 156 nóg, ROI -11.0%, wobec oficjalnego -4.6% (6 344 nogi). Odczyty możliwie usuwają gorsze nogi, ale n jest za małe.
- **Rozwiązanie:** każdy kontekst, który analityk czyta regularnie (rywal, liga, faza), przenieść do kodu (W1, W4, W6), żeby działał w obie strony i był kalibrowany. Analityk zostaje do rzeczy jednorazowych (zawieszenia, pogoda). **Pomiar:** `record_results.py` z CI bootstrap po meczach dla `removed:reads` kontra kupon, w tym samym paśmie ceny (memory: „vetoes are graded, price-band matched”).
- **Priorytet / nakład:** P3 / S.

### Macierz SPORT x WARSTWA KONTEKSTU

Legenda: **P** = w p (środek albo rozkład); **½P** = w połowie środka; **F** = tylko flaga lub wyświetlenie; **A** = tylko analityk; **–** = brak; **n/d** = nie dotyczy.

| kontekst | piłka - oceniane (gole, strzały, faule, rożne_for) | piłka - UNRATED (corners_total, połowy rożnych, cards_points_for, offsides_total) | piłka - propsy | tenis - gemy (games_won_for, handicap, most, ½ games_total) | tenis - asy, DF, punkty serwisowe | hokej / kosz / siatkówka | CS2 |
|---|---|---|---|---|---|---|---|
| dostosowanie do rywala | ½P (rating att x def, `football_rating.py:931`) | – | – | P (Elo) | – (A) | P (RatingBook) | P zwycięzca, serie, handicap rund (Elo); – kills, suma rund, rundy drużyny |
| venue / dom | ½P (współczynnik domu w ratingu); próbka – | – (venue zapisane, nieużyte) | – | n/d | n/d | P (home w RatingBook) | P (człon gospodarza w kalibracji Elo) |
| odpoczynek / natłok | F (`schedule.py`) | F | F | P (78 h, > 21 dni, 7 dni) | – | – (`b2b_delta=0`); kosz: szum `BB_FRESHNESS` | – |
| h2h | przypadkowe w puli sumy, bez wagi; A | jw. | – | – (rating bez h2h) | przypadkowe | – | – |
| styl / matchup | – (tylko att x def); A | – ; A | – | – (tier gap `dhigh`/`dtour` to klasa, nie styl) | – | kosz: wspólny szok tempa (wariancja) | – (mapy) |
| składy | – (sondy przedmeczowej nie uruchomiono); A | – | P (próbka z meczów w pierwszym składzie, historyczna) | n/d | n/d | propsy: P (drużyny przypięte); bramkarz – | P (Elo graczy z ostatniego składu) |
| siła ligi / klasa | ½P (sigma, LINKED_BY_STRENGTH); UNLINKED odrzucone; prior ligi P | prior ligi P; siła – | – | P (tier, `dhigh`/`dtour`, krzywe klas) | prior tier P | P (sigma w RatingBook) | – (jedna pula Elo) |
| świeżość / recency | ostatnie 10 równo; gole: ta sama rozgrywka; rating EWMA | ostatnie 10 równo | starty, ostatnie | Elo K | ostatnie 10, nawierzchnia | EWMA ratingu; kosz: szum świeżości | Elo K |
| faza sezonu | – (zmierzona, niezaimplementowana) | – | – | – | – | – | – |
| stawka | F (`stakes.py`) | F | – | – | – | – | – |
| sędzia | A | A (kartki) | – | n/d | n/d | – | n/d |

### Braki wspólne dla obszaru

1. **Obserwacja bez rywala** (`contracts.py:129-146`). To korzeń W1, W4 i W7: dopóki obserwacja nie ma `opponent_id` (i `against` dla `*_for`), żadna korekta próbki nie jest możliwa bez nowego odczytu cache.
2. **Replay krzywych bez ratingu** (`calibrate_from_cache.py:1064-1072`). Każda poprawka środka, również istniejący rating, jest przez krzywą widziana tylko pośrednio.
3. **Kontekst zmierzony, ale niewdrożony:** faza sezonu (największa cecha); odpoczynek dla goals_total i strona z innej ligi przechodzą kryterium minimalnie (rząd 1e-4). Żadna nie jest zaimplementowana; trzeba je napisać, odtworzyć w replayu i wejść z refitem (nowy przełącznik albo rozszerzony `MODEL_FIXES_FROM_UTC`).
4. **Decyzje na krótkich oknach:** `UNRATED_MARKETS` (5 dni, wyłączenia dobrane na tych samych dniach). Historia 722k meczów pozwala to sprawdzić poza próbą.
5. **Asymetria analityka:** kontekst może tylko usuwać.
6. **Bramki na surowej puli** będą działać przeciw każdej korekcie kontekstu (MODEL_ABOVE_OWN_SAMPLE).

### Czego nie sprawdziłem

- Nie mierzyłem na historii żadnej proponowanej zmiany. Liczby „[zmierzone]” z 6 dni (10-07..10-12) to rozliczone wiersze sheetu, deduplikowane po pierwszym wierszu (mecz, rynek, strona), bez kontroli epok (10-07/10-08 to inny estymator niż od 10-09). Mają charakter diagnostyczny.
- Nie sprawdziłem, czy `sofa_event_stats` ma posiadanie piłki dla koszykówki ani ile meczów cross-league jest w cache.
- Nie otworzyłem pełnych tekstów Gollan 2020 i Clegg-Cartlidge 2025 (tylko streszczenia). Goddard-Asimakopoulos 2004 czytałem w wersji roboczej PDF (tabela 1), nie w wersji z czasopisma. Nie znalazłem badania, które mierzy h2h ponad rating w piłce na danych po 2010 roku. Wyszukiwanie zwracało głównie poradniki bukmacherskie, których nie traktuję jako źródła.
- Nie znalazłem otwartego źródła o wpływie bramkarza na gole w hokeju; teza w W9.2 to podejrzenie.
- `stakes.py` i `peer_choice` przeczytałem tylko przez CLAUDE.md i grep, bez linii kodu efektu.
- Nie rozpisałem rynków `sport_confidence.EXTENDED_MARKETS` ani rodzin CS2 po kolei. To obszar innych audytorów, tu są tylko warstwy wspólne.
- Ledger removed:reads: brak CI i brak dopasowania pasm ceny.

# Dziennik weryfikacji

## Runda 1

Trzech weryfikatorów (tylko odczyt): V1 (Część 1, Część 2, wiersze piłki), V3 (Część 3, Część 4, wiersze tenisa / hokeja / kosza), V5/V6 (Część 5, Część 6, wiersze siatkówki / CS2 / warstw wspólnych, „Kolejność”). Razem 55 uwag: 1 BLOCKER, 13 MAJOR, 41 MINOR. Naniesione wszystkie; „ręcznie” = stary tekst nie pasował dosłownie albo uwaga nie podawała zamiennika dla danego miejsca.

| id | waga | co zmieniono |
|---|---|---|
| V1-1 | BLOCKER | A1 „rozwiązanie”: start jednostki z siłą rodzica / siła per rozgrywka; próg n < MIN_STRENGTH_LINKS nie odpala (n=34/35). To samo w Części 1 „Braki wspólne” pkt 1 |
| V1-2 | MAJOR | A1 „skutek”: dopisane Kyoto 1,32 – Ratchaburi 1,39 (z siłą 196: 1,80 – 1,02) i Công An z siłą 196 (1,63 – 1,24) |
| V1-3 | MINOR | Część 1: miejsce J1 47 → 48 z 3 112 jednostek z n ≥ 10 |
| V1-4 | MINOR | Część 1: „3.06 = 3.07” zastąpione sumami 3.07 → 2.87 i 2.71 → 2.82 |
| V1-5 | MINOR | A4 „rozwiązanie”: deff per kubełek tą samą funkcją `design_effect`, nie n/games |
| V1-6 | MINOR | Część 2 (dwa miejsca): games == n tylko w kubełkach p ≥ 0.60 |
| V1-7 | MINOR | Część 2: kubełek kartek 36/43 to NO_LINE_EVIDENCE (n < 50) niezależnie od deff |
| V1-8 | MINOR | Część 2: propsy piłki 0+0+2+3+0+0+1; wydrukowane nogi 10-09..10-13: 8 → 6 |
| V1-9 | MINOR | Część 2: 9 → 8 z 10 meczów Ratchaburi w Thai League |
| V1-10 | MAJOR | C1: kodu fazy sezonu nie ma; wdrożyć, odtworzyć w replayu, ponownie zmierzyć względem pełnego p_central, potem refit (scalone z V6-1, zgodne) |
| V1-11 | MAJOR | A5 sport: piłka (MODEL_ABOVE_OWN_SAMPLE), piłka i tenis (bramki kształtu) (scalone z V6-2, które dodaje „bez propsów” i `confidence.py:623-655`) |
| V1-12 | MAJOR | B2: dopisany pomiar MSE Części 1 (rating 11,76 gorszy od puli 11,56) i alternatywa K=40 (P2/S) |
| V1-13 | MINOR | B1: 714 stron z 34 918; porównanie z meczami wyrównanymi (0,837 przy 0,772) |
| V1-14 | MINOR | C7 i Część 1 pkt 6: `ballPossession` 92,7% wierszy piłki (99 541 / 107 435). Ręcznie: l. ~590 (Część 1 „Braki wspólne” 6) — dopisany odsetek piłki obok próbki mieszanej, bo uwaga nie dawała zamiennika |
| V1-15 | MINOR | Część 1: h2h nie ma wagi także w `day_league_observations` (`run_sheet.py:389-401`) |
| V1-16 | MINOR | Część 1 (dwa miejsca): `favourite` tylko w komentarzach; „stan meczu” w LITERATURA #13 jako niezmierzony kandydat |
| V1-17 | MINOR | `run_sheet.py:376-380` → `:385-386` (dwa miejsca) |
| V1-18 | MINOR | `engine.py:168-169`; `football_rating.py:948, :969-973`; `football_rating.py:129`, `:131` |
| V1-19 | MINOR | Część 2 pkt 7: handicap/most „bez kotwicy”, bez przeciwnika tylko mecze bez drabin obu stron |
| V1-20 | MINOR | A6: odwołania `calibrate_from_cache.py:1017-1018`, `:1064-1072` i uwaga o CLAUDE.md (patrz „Do operatora” niżej) |
| V1-21 | MINOR | Dopisane B14 (W per rynek) i C16 (`DERIVED_MARGINAL_CENTRES_METRICS`). Nie dopisano osobnych wierszy dla xG/GAP i raportu odmów: uwaga wymienia je w dowodzie, ale zamiennik daje tylko B14 i C16 |
| V1-22 | MINOR | C13: ~15% meczów (22/143 wg Części 6; 23/156 przy filtrze po `02_fixtures`) |
| V1-23 | MINOR | Część 1 (dwa miejsca): Dixon & Robinson 1998 — metadane potwierdzone (Crossref); drugie miejsce (l. ~615) przepisane ręcznie, bo uwaga dawała zamiennik tylko dla pierwszego |
| V1-24 | MINOR | Część 1: Dixon & Coles jako struktura atak × obrona, kowariata stanu meczu to nasze rozszerzenie |
| V3-1 | MAJOR | B5 i Część 3 (trzy miejsca): PRIOR_GLOBAL 99% / 78%, nie 100%; `sets_total` ma prior tier; liczniki 6 146 / 6 212 i 6 198 / 7 902 |
| V3-2 | MAJOR | A7 i Część 4: kosz 3 625 linii / 665 meczów, 0,760 / 0,633 / 0,628, maks. luka −26,0 pp; hokej −1,3 pp (6 105 / 886) w dwóch miejscach. Ręcznie: dopisany gradient weryfikatora przy −26,0 pp oraz notka przy tabeli per klucz (l. ~1460: odczyt krzywej inny, `total\|UNDER` / `team_total\|UNDER` nieodtworzone) — uwaga nie dawała tam zamiennika |
| V3-3 | MAJOR | B8 i Część 4 (trzy miejsca): ~3–7 tys. meczów hokeja ze strzałami zamiast ~15 tys. |
| V3-4 | MAJOR | C2: rozwiązanie = kalibracja P(3 setów \| p) per tier × płeć × powierzchnia (tabela sąsiadów z powierzchnią zmierzona 10-08 bez zysku); status [zmierzone, 4 dni] z przedziałem |
| V3-5 | MINOR | D2: ~3 000 wystąpień 10-12; P1/M → P2/M |
| V3-6 | MINOR | B6 → P1/M (źródło), wymaga zarejestrowanego testu; B8 P2/L → P2/M |
| V3-7 | MINOR | A2 sport: także siatkówka; 7 przedsezonów kosza w cache |
| V3-8 | MINOR | Część 4: 18 linii OVER, −0,50, Brier 0,333 (z adnotacją liczb audytora). Uwagi o 154,7 pkt dla konkretnej nogi nie wpisano do tekstu (brak zamiennika), zostaje tu: centrum Raptors–Clippers = 154,7 pkt, „~165” to para o przeciętnej sile |
| V3-9 | MINOR | `run_sheet.py:1290–1291` → `:1285–1289` |
| V3-10 | MINOR | Część 3: ~3 000 wystąpień w jednym dniu (10-12) |
| V3-11 | MINOR | „Ely/Hinnosaar” → „Ely (Cheap Talk 2009)” w C8 i Części 4 (trzy miejsca; trzecie, w liście źródeł, ręcznie) |
| V3-12 | MAJOR | Dopisane A8 (szum symulacji kosza, docstring vs kod `score_model.py:574` / `:594`). Zastrzeżenie weryfikatora: na liniach Superbetu z odczytem ≥ 0,70 krzywa `.next` daje 0,760 przy surowym 0,763 — podbicia „0,701 → 0,755” (Część 4 pkt 4) nie widać; tekstu Części 4 nie zmieniano |
| V3-13 | MINOR | Dopisane C17 (hokej, remis regulaminowy) i C18 (tenis, waga `games_total` / ścieżka handicapu). Weryfikator nazwał je C16/C17; przenumerowane, bo C16 zajął V1-21 |
| V5-1 | MAJOR | B9, Część 5 pkt 2, „Braki wspólne” 5: −13,4 / −29,5 pp to błąd krzywej przed offsetem; offset już działa, skutkiem jest brak druku. Ręcznie: Część 5, `points_handicap` „Braki” 2 (l. ~1781) — ta sama poprawka sensu |
| V5-2 | MAJOR | B10: 66 linii / 24 serie, poniżej MIN_OFFSET_GAMES, w druku tylko offset puli −3,5 pp; 0 nóg. Ręcznie: to samo w Części 5 (`map_team_rounds`, „Braki” 2) |
| V5-3 | MINOR | Część 5: ogony przeszacowuje model, krzywa to koryguje |
| V5-4 | MINOR | C9: przyczyną jest brak w `HISTORY_MARKETS` i `PERIODS` (decyzja F4 / operator 10-07); Część 5 „Nakładanie się” → wymaga zgody operatora |
| V5-5 | MINOR | `cs2_engine.py` komentarz `:86-91`, pomiar κ `:93-102` |
| V5-6 | MINOR | `load_history:401-404` → `:407-419` |
| V5-7 | MINOR | Część 5: `home_overtime` 2 935 map z dogrywką; 25 669 to mapy z połówkami i stroną |
| V5-8 | MINOR | B9: diagnostyka w próbie; side-out 0,62 / set_sd 0,02 zmierzone 10-01 i niewłączone |
| V5-9 | MINOR | C10: „Zależy od B9 (… niezmierzone OOS)” |
| V5-10 | MINOR | Dopisane C19 (siatkówka, poziom punktów), C20 (CS2 `map_rounds_handicap`), C21 (rozliczenie nierozegranego seta). Weryfikator nazwał je C16–C18; przenumerowane |
| V5-11 | MINOR | Macierz, CS2 „dostosowanie do rywala”: handicap rund i serie znają rywala; bez rywala kills, suma rund, rundy drużyny |
| V6-1 | MAJOR | Część 6 pkt 7, W6 „Rozwiązanie”, „Braki wspólne” 3, C1, „Kolejność” pkt 4: faza sezonu nie leży za `MODEL_FIXES_FROM_UTC` (ten bramkuje tylko F2.2); kodu nie ma. Zgodne z V1-10 (scalone w jeden wiersz C1) |
| V6-2 | MINOR | A5: zob. V1-11 (scalone; wzięto bardziej szczegółowe sformułowanie V6-2 i zakres `confidence.py:623-655`) |
| V6-3 | MINOR | Część 6: grep `possession\|style` trafia tylko w komentarz `:84` |
| V6-4 | MINOR | C14: „pomiar uzasadnia” → odpoczynek: zysk minimalny, stawka bez testu log-loss |
| V6-5 | MAJOR | „Kolejność” pkt 1: A2 i A3 za przełącznikiem; A3 z refitem krzywej kosza. A3 „wpływ na druk”: poprawka + przełącznik (+ refit krzywej koszykówki) |
| V6-6 | MINOR | „Kolejność” pkt 5: B9 przed wdrożeniem C9 |
| V6-7 | MINOR | „Braki wspólne” 3: odpoczynek i strona z innej ligi przechodzą kryterium minimalnie. Ten sam wiersz zmieniał V6-1 — oba zamienniki złożone ręcznie w jedno zdanie |

Konflikty: V1-10 i V6-1 (C1) oraz V1-11 i V6-2 (A5) poprawiały te same wiersze zgodnie co do treści, więc scalono je; przy A5 wzięto wersję V6-2, bo jest pełniejsza. V1-21, V3-13 i V5-10 niezależnie proponowały nowe wiersze C16..C18, więc numerację uciąglono (C16..C21). Sprzecznych liczb nie było.

Nie przeliczone przez weryfikatorów (zostają jako liczby audytorów): „liga 463 ma 17 meczów z rożnymi”, „40 meczów z handicapem, 5 bez centrów”, `corners_for` +1,65 / −0,44 i reszta `corners_total` +0,55 / +0,27 z Części 6 (brak skryptów `m/gap.py`, `m/cross.py`), liczby wystąpień D3 z 10-13 (196 / 64 / 37 / 4, z sondy na żywo).

Wszystkie liczby line evidence pochodzą z niezacommitowanego `config/sofa_superbet_line_evidence.json` (fit 2026-10-13T07:40:57Z, dni 10-05..10-12); w HEAD (fit 10-12) są inne.

## Runda 2

Dwóch weryfikatorów (tylko odczyt): lista napraw i „Kolejność” (V2L-1..V2L-22: 7 MAJOR, 15 MINOR) oraz naniesienie rundy 1, zdania w Częściach sprzeczne z poprawkami, odwołania plik:linia i render (R2-1..R2-17: 1 MAJOR, 16 MINOR). Razem 39 uwag: 8 MAJOR, 31 MINOR. Naniesione wszystkie; odstępstwa od dosłownego zamiennika opisane w wierszu.

| id | waga | co zmieniono |
|---|---|---|
| V2L-1 | MAJOR | B2 i Część 1 (`corners_total`, „Nakładanie się”): K=40 dla `corners_total` zmierzono już 10-08 bez rozstrzygnięcia (lc −4,2 [−10,1; +1,9]); bez nowego dowodu nie proponować. Ręcznie: w „Rozwiązaniu” Części 1 dopisane „już zmierzone 10-08”, bo uwaga dawała zamiennik tylko dla „Nakładania” |
| V2L-2 | MAJOR | A2: piłka w kolumnie sportu (ACL 17 meczów); rozwiązanie = odmowa sparingu / przedsezonu regułą `FRIENDLY_FIXTURE`, `NO_LEAGUE_RATE` albo fallback tylko do ligi tej samej klasy. Ręcznie: Część 4 (a) — wariant „liga macierzysta dla przedsezonu” oznaczony jako odrzucony w r2 |
| V2L-3 | MAJOR | A8: kandydat, nie stwierdzona przyczyna; trzy warianty mierzone osobno; prio „P2/S (nadany na liście, źródło bez priorytetu)” |
| V2L-4 | MAJOR | B9: „serwis per płeć” → kalibrator długości seta per płeć × liga (side-out luki nie zamyka) |
| V2L-5 | MAJOR | B13: fundament pod korektę próbki (W1, W4; B15) i A5 / W7, nie pod B1–B3 |
| V2L-6 | MAJOR | Dopisany wiersz B15 (korekta próbki o rywala i siłę ligi, wymaga B13); notka źródeł pod B scalona z R2-11 |
| V2L-7 | MAJOR | „Kolejność proponowana” zastąpiona tekstem weryfikatora (6 punktów: B1, B3, B6 w pomiarach; B15 w fundamencie; B14 i D1 w reficie piłki; jeden refit koszykówki z A3 + C8 i A8; C9 / C10 po B9; B8) |
| V2L-8 | MINOR | A5: P1/M → P2/S (po B13/B15; Część 6 W7) |
| V2L-9 | MINOR | A4 „wpływ na druk”: każdy klucz bez krzywej we wszystkich sportach, walk-forward na wszystkich |
| V2L-10 | MINOR | A7: backfill kursów przez most; dostępność kursów kosza w Sofascore niesprawdzona |
| V2L-11 | MINOR | B3: brzegi formułą SHEET (shrink + 0,5 × rating), odmowa przy UNLINKED (P1/M); rho zależne od różnicy sił P3/M |
| V2L-12 | MINOR | B4: podobieństwo do odrzuconego poolingu EB nazwane w wierszu |
| V2L-13 | MINOR | B7: B2B zmierzone na punktach bez efektu (+0,06 pkt, se 0,64) |
| V2L-14 | MINOR | Priorytety jak w źródle: C6 P2/M, C12 P3/S, C15 P2/L |
| V2L-15 | MINOR | C13: h2h z listingów w `sofa.db` (3 lata, bez mostu) |
| V2L-16 | MINOR | C17: wspólny szok i `hk_disp` w hokeju zmierzone bez zysku; nowy dowód to tylko holdout DRAW |
| V2L-17 | MINOR | C21: Regulamin Zakładów Online już zlokalizowany; rozbieżność = poprawka rozliczenia z testem |
| V2L-18 | MINOR | D1: „C2” to pomiar z `RAPORT_NOC_2026-10-12.md`, nie wiersz C2 |
| V2L-19 | MINOR | D2: zgoda operatora na refit zwycięzcy meczu tenisa (10-13) |
| V2L-20 | MINOR | Zamiast zdania w legendzie (zamiennik weryfikatora) dodana kolumna „wpływ na druk” w tabelach B, C, D (polecenie redakcji): „tak (przez przełącznik)” tam, gdzie wiersz zmienia p, bramki albo dodaje rynki; B13 „nie” (struktura danych), C14 „nie (pomiar)”, C21 „poprawka (rozliczenie…)”; legenda rozszerzona |
| V2L-21 | MINOR | B2: gospodarz jako mnożnik home/away ligi, nie podział próby (Część 1: P3/S) |
| V2L-22 | MINOR | A3: `defaultPeriodLength` albo stała per liga; razem z C8 (jedna ścieżka `_basketball`, jeden pomiar) |
| R2-1 | MINOR | Część 4 pkt 2: gradient z weryfikacji r1 (+13,6 … −26,0 pp, 3 625 / 665) jako główny; liczby audytora (6 602 / 801, −28,7 [−34,8; −21,1]) i hokeja (6 893 / 962) oznaczone jako nieodtworzone |
| R2-2 | MAJOR | Część 4 pkt 4: podbicie 0,701 → 0,755 oznaczone jako nieodtworzone (r1: 0,763 → 0,760); tytuł punktu: „niepotwierdzone” |
| R2-3 | MINOR | Część 3: ~2 900 → ~3 000 (3 001) |
| R2-4 | MINOR | Część 4: 18 linii OVER (r1) obok 34; ~165 pkt to para przeciętna, Raptors–Clippers 154,7 pkt |
| R2-5 | MINOR | Część 4 (a): „natychmiast” → przełącznik od następnego dnia 00:00Z (dwa miejsca) |
| R2-6 | MINOR | Część 5 (trzy miejsca) i C9: przyczyna = brak w `HISTORY_MARKETS` i `PERIODS` (decyzja operatora 10-07); pkt 4: zmiana odwraca decyzję operatora i zależy od B9; C9 `:205-209` |
| R2-7 | MINOR | Część 5 `points_*` priorytet: błąd krzywej, w druku zdjęty offsetem |
| R2-8 | MINOR | Macierz i W6: faza sezonu „zmierzona, niezaimplementowana” |
| R2-9 | MINOR | Część 6 pkt 9: zmierzono przerwę i natłok, stawka bez testu; „zgodna z pomiarem (zysk rzędu 1e-4)” |
| R2-10 | MINOR | Część 1 „Braki wspólne” 3: Dixon & Coles jako atak × obrona |
| R2-11 | MINOR | Notka źródła B14: P1/M (`goals_for`) wobec P2/M („Braki wspólne” 4) nazwane; scalone z V2L-6 |
| R2-12 | MINOR | A4: „w kubełkach klucza od p 0,60” |
| R2-13 | MINOR | Część 1 pkt 3: dopisane Kyoto 1,32 – Ratchaburi 1,39 (z siłą 196: 1,80 – 1,02) |
| R2-14 | MINOR | `calibrate_from_cache.py:1062-1068` → `:1064-1072` (trzy miejsca); „Do operatora” rozszerzone o priory tenisa |
| R2-15 | MINOR | `confidence.py:1336-…` → `:1334-…` (trzy miejsca) |
| R2-16 | MINOR | Escape `\|` w wierszach V3-2 i V6-3 tego dziennika |
| R2-17 | MINOR | „Dziennik weryfikacji” jako nagłówek `#` (poziom Części), rundy jako `##` |

Przegląd końcowy redakcji (punkt 8 zlecenia): poza miejscami wskazanymi przez weryfikatorów zmieniono dwa zdania sprzeczne z listą — Część 4 (a) (fallback do ligi macierzystej, zob. V2L-2) i Część 1 `corners_total` „Rozwiązanie” (zob. V2L-1). Nie przeliczono: „18 nóg `player_pp_points` UNDER 10-05..10-13” (R2: w `11_coupon.json` 21, dzień 10-13 przebudowany po audycie; bez poprawki, zgodnie z weryfikatorem).

## Do operatora

Poza tym dokumentem, bez zmiany w repo:
- CLAUDE.md pisze, że replay historii (`calibrate_from_cache.py`) „prices the same estimator as SHEET”. Dla piłki to nieprawda: rating piłki nie jest replayowany dla żadnego rynku marginalnego (`calibrate_from_cache.py:1017-1018`, `:1064-1072`), a SHEET miesza go po połowie (A6, V1-20); ten sam komentarz przyznaje, że nie są replayowane także priory tier / drabiny tenisa (R2-14). Do poprawienia w CLAUDE.md przy najbliższej zmianie tej sekcji.
- Decyzje, od których zależy lista:
  - A7: krzywe na liniach postawionych tam, gdzie stał rynek — blisko odrzuconego „blend the price” (cena tylko do pozycji linii); wymaga wyraźnej zgody, plus backfill kursów przez most.
  - C9 (i pkt 4 Części 5): rynki setowe siatkówki z historii odwracają decyzję plan F4 / operatora z 10-07 (tylko rozliczone linie).
  - Nakładanie się z wcześniejszymi pomiarami: B2 (K=40 dla `corners_total` zmierzone 10-08 bez rozstrzygnięcia; venue jako prior, nie podział), B4 (kurczenie udziału zawodnika przypomina odrzucony pooling EB), B7 (B2B zmierzone na punktach bez efektu), C17 (wspólny szok i `hk_disp` w hokeju bez zysku; nowy jest tylko holdout DRAW).
  - Refit krzywej koszykówki (zgoda 10-13): „Kolejność” pkt 5 proponuje jeden refit po A2, A3 + C8 i pomiarze A8; refit tą samą metodą (`synthetic_lines`) nie zamknie luki −12,7 pp na liniach Superbetu bez A7 / B7.
  - D1 (DNB / DC) po C1 (faza sezonu), zgodnie z odmową z 10-13; refit zwycięzcy meczu tenisa (D2) ma zgodę z 10-13.
