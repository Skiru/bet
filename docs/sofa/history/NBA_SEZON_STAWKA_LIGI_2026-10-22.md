# Restart stawki ligi po przerwie międzysezonowej (koszykówka) - 2026-10-22

Przełącznik `epochs.LEAGUE_SEASON_RESTART_FROM_UTC` = **2026-10-23 00:00Z**,
tylko koszykówka (`LEAGUE_SEASON_RESTART_SPORTS`). Zgoda operatora 2026-10-22
~10:21Z („Rób”) pod warunkiem: pomiar poza próbą lepszy, przedział wyklucza 0.
Grupa księgi: „od 10-23” (ta sama co `SPORT_LATE_WINDOW`). Bez refitu, bez
instalacji krzywych.

## Problem (pomiar z rana, `data/refit_2026-10-22/nba_measure/nba_measure.md`)

Model wyniku sportów mierzonych trzyma stawkę ligi jako wolną średnią
wykładniczą (`football_rating._League`, `ALPHA_LEAGUE` 0,02, ~ostatnie 50
meczów). NBA (Sofascore 132) pamiętała play-offy (maj 215,3 / czerwiec 206,4
pkt na mecz): 10-21 czytała 218,1 pkt, a 14 październikowych meczów miało
średnio 228,6. Suma modelu leżała średnio 13,2 pkt pod główną linią Superbetu
(13 meczów 10-21/10-22), a replay 10-21/10-22 przepuszczał 42 nogi NBA, z
czego 36 to UNDER-y na połowach / kwartach.

## Reguła

`RatingBook.season_restart` (ustawia tylko `score_model.build_model(...,
season_restart=True)`; piłka nigdy):

- liga, której kolejny mecz przychodzi >= `SEASON_GAP_S` (45 dni) po
  poprzednim, miała przerwę międzysezonową;
- pierwszy mecz po przerwie czyta **zwykłą średnią zakończonego sezonu**
  (play-offy w środku, każdy mecz z wagą 1; `_League.season_mean`, wymaga
  >= 30 meczów sezonu, inaczej zostaje stara średnia);
- od pierwszego meczu nowego sezonu **poziom** (gospodarz + gość) startuje od
  tej średniej z wagą `SEASON_PRIOR_MATCHES` = 10 meczów (krok 1/(w+1), aż
  spadnie do `ALPHA_LEAGUE`), a **udział gospodarza** idzie wolnym krokiem
  0,02 (`SEASON_RESTART_LEVEL_ONLY`);
- licznik meczów `n` (bramka 30 meczów, `NO_LEAGUE_RATE`) nie jest zerowany.

Ogólna reguła estymatora - żadna liga ani drużyna nie jest nazwana.

## Pomiar poza próbą

Kopie bazy (nigdy `data/sofa.db`): koszykówka
`scratchpad/nba_measure/bb.db` (kopia 09:48Z z porannego pomiaru), hokej i
siatkówka `data/refit_2026-10-22/league_season/{hk,vb}.db` (`copy_sport.py`,
tylko listingi). Skrypty i wyniki: `data/refit_2026-10-22/league_season/`
(`measure_restart.py`, `analyse.py`, `analysis_k10.md`, `analysis_lvl.md`,
`out/`).

Metoda: jak `sport_confidence.walk_forward_rows` - model przebudowywany co 30
dni, książka aktualizowana mecz po meczu, mecze o jednej godzinie
prognozowane przed nauką któregokolwiek (bez wycieku); przełączniki dnia
(ścisła stawka ligi, świeżość kosza; dogrywka / tempo / strzały / długość seta
wyłączone); 1 000 symulacji. Obie wersje oceniane na **sumie zbiorów linii
syntetycznych obu wersji** (te same zdarzenia), wszystkie rodziny linii meczu,
które kupon drukuje (sumy, handicap, sumy drużyn, połowy, kwarty / tercje,
zwycięzca / 1X2 / DC). Log loss i Brier na linię, nowe - stare (ujemne =
lepiej), bootstrap po meczach (1 000). Okna: 2024-09..2025-08, 2025-09..
2026-08, 2026-09..10-22; „start sezonu” = pierwsze 30 dni ligi po przerwie.
NBA: każdy mecz; inne ligi kosza: 1 z 20 (2026-09..: 1 z 4) wg crc32 id meczu;
nic nie jest sumowane po cichu - pula nazwana osobno.

### Koszykówka - reguła wdrożona (poziom szybko, udział gospodarza wolno)

| grupa | mecze | log loss nowe - stare [95%] | poziom: faktyczne - model, stare -> nowe |
|---|---|---|---|
| NBA, całe okno 2024-09..10-22 | 2 644 | **-0,0006 [-0,0010; -0,0001]** | +0,12 -> +0,02 |
| NBA, start sezonu (3 sezony) | 448 | **-0,0030 [-0,0050; -0,0012]** | +1,96 -> +0,96 |
| NBA, start 2024 | 213 | -0,0020 [-0,0045; +0,0003] | +2,28 -> +1,38 |
| NBA, start 2025 | 221 | -0,0030 [-0,0059; -0,0003] | +1,13 -> +0,59 |
| NBA, start 2026 (do 10-22) | 14 | -0,0150 [-0,0399; +0,0085] | **+10,34 -> +0,58** |
| inne ligi kosza, całe okno | 4 243 | -0,0001 [-0,0005; +0,0003] | +0,17 -> +0,22 |
| inne ligi kosza, start sezonu | 1 441 | -0,0003 [-0,0012; +0,0007] | -0,10 -> +0,10 |
| pula (NBA + inne przerzedzone), całe okno | 6 887 | -0,0003 [-0,0006; +0,00004] | - |
| pula, start sezonu | 1 889 | -0,0009 [-0,0018; -0,0001] | - |

NBA na starcie sezonu wg rodzin: sumy -0,0125 [-0,0196; -0,0057], sumy drużyn
-0,0079 [-0,0126; -0,0034], połowy -0,0034 [-0,0059; -0,0010], kwarty
-0,0014 [-0,0027; -0,0002], zwycięzca -0,0009 [-0,0052; +0,0036], handicap
-0,0006 [-0,0041; +0,0026]. Błąd kwadratowy sumy NBA (całe okno) -2,84
[-4,60; -1,08] pkt² na mecz. W innych ligach żadna rodzina nie ma przedziału
powyżej zera na całym oknie (zwycięzca +0,0006 [-0,0010; +0,0023], handicap
+0,0007 [-0,0006; +0,0021]).

**Kalibracja wierszy drukowalnych** (krzywa `.next.json` >= 0,70, linie
własne każdej wersji, realizacja - pewność): NBA całe okno -2,0 pp
[-2,2; -1,7] w obu wersjach; NBA start sezonu 2026: UNDER połów / kwart
-6,8 [-13,1; -0,8] -> -1,2 [-7,1; +4,6], OVER +5,2 [+1,8; +8,7] -> -0,8
[-6,0; +4,5]; inne ligi +1,3 -> +1,2. Krzywa nie traci zgodności z nowym p.

**Werdykt:** w grupie, w której problem zdiagnozowano (NBA), lepiej z
przedziałem wykluczającym 0 - na całym oknie i na startach sezonu; inne ligi
bez różnicy; pula całego okna dotyka zera (górna granica +0,00004), pula
startów sezonu wyklucza 0. **Przełączone** (koszykówka, od 2026-10-23 00:00Z).

**Uczciwie o kolejności:** z góry zapisana była wersja „obie strony szybko”
(K 10, ta sama przerwa). Dała NBA -0,0005 [-0,0010; -0,0001], ale w innych
ligach pogorszyła zwycięzcę +0,0018 [+0,0003; +0,0031] i handicap +0,0013
[+0,0001; +0,0025] (przewaga gospodarza z 10 meczów jest szumem). Wersję
„tylko poziom” wymyślono **po** tym wyniku i zmierzono na tych samych oknach,
więc jej przewaga nad wersją K 10 jest w próbie; przewaga nad starą regułą
nadal jest pomiarem poza próbą (model nie jest dopasowywany do wyników).
Stałe 45 dni i 10 meczów wybrane przed pomiarem, nie strojone.

### Hokej i siatkówka - nie przełączone

Wersja K 10 (obie strony szybko), ta sama metoda; hokej 1 z 10 (2026-09..:
1 z 2), siatkówka 1 z 10 (1 z 2):

| sport | mecze | log loss nowe - stare [95%] |
|---|---|---|
| hokej, całe okno | 6 169 | +0,0005 [+0,0002; +0,0009] (gorzej) |
| hokej, start 2026 | 1 661 | +0,0022 [+0,0013; +0,0032] (gorzej) |
| siatkówka, całe okno | 5 373 | +0,0012 [+0,0005; +0,0020] (gorzej) |

Ich poziom ligi nie dryfuje między sezonami jak w koszykówce (poziom
faktyczne - model: hokej +0,02 gola, siatkówka -0,04 pkt na set). Wersja
„tylko poziom” dla nich **nie mierzona** (podejrzenie: neutralna, bez
korzyści). `LEAGUE_SEASON_RESTART_SPORTS` = {basketball}.

## Replay 10-21 / 10-22 (NBA)

`replay_1021.py` = poranny `q1_replay.py` z przełącznikiem: SPORT_CONFIDENCE
(`build_sport`) na kopii bazy, model ucięty 20 min przed każdym meczem, krzywa
dnia, line evidence z 10-22 (dopasowane na starej regule).

| | 10-21 | 10-22 | razem | podział |
|---|---|---|---|---|
| stara reguła | 20 | 22 | **42** | 36 UNDER (połowy / kwarty / sumy drużyn), 3 handicap 2. połowy (T2), 3 zwycięzca / 1X2 (T1) |
| nowa reguła | 6 | 8 | **14** | 6 UNDER, 1 OVER, 3 handicap 2. połowy (T2), 4 zwycięzca / 1X2 (T1) |

Stawka NBA (gospodarz / gość): 10-21 109,6 / 108,6 -> 114,2 / 112,8; 10-22
112,0 / 108,6 -> 116,4 / 112,5. Model minus główna linia sumy Superbetu: 10-21
-14,5 -> -4,7, 10-22 -12,1 -> -3,0 (13 meczów: -13,2 -> -3,8 pkt). Czy te nogi
wygrały - nie sprawdzane (2 dni, wynik nie jest argumentem).

## Krzywe i refit

Zainstalowana krzywa koszykówki (`config/sofa_sport_confidence_calibration.next.json`,
`fitted_from.before` 2026-10-14, A7) była dopasowana na starej regule
(replay bez restartu). W walk-forwardzie kalibracja wierszy >= 0,70 się nie
ruszyła (NBA -2,0 pp w obu wersjach), więc krzywa pozostaje spójna z nowym p
na tyle, na ile to widać - **refit nie jest konieczny do spójności**; byłby
porządkiem (krzywa z replayu tej samej reguły, co live). Refit wymagałby:
`fit_sport_confidence.py --sport basketball --before <d+1> --bb-freshness on
--league-season-restart --dry-run --rows-out <dir>` na kopii bazy (od
`--before` >= 2026-10-23 flaga sama z dnia), sekcja do `.next.json`,
`refresh_line_evidence.py`. Osobna zgoda operatora - nie zrobione.
Line evidence (offsety kosza) też liczone na p starej reguły; odświeży się co
rano na nowych rozliczonych liniach.

## Rozrzut kwart NBA (sprawa poboczna)

Nie mierzony na nowo. Z porannego pomiaru: NBA kwarty -2,5 pp, połowy -1,4 pp
(poza próbą, krzywa >= 0,70), inne ligi +0,9 / +1,2; odchylenie reszt kwart
NBA 5,98 vs 5,20 w puli. Restart tego nie zmienia (NBA -2,0 pp w obu
wersjach). Otwarte pytanie w model-state (e): rozrzut zależny od poziomu /
tempa wymaga osobnego pomiaru i przełącznika.

## Zmiany w kodzie

- `football_rating._League` (`last_ts`, `weight`, sumy sezonu,
  `season_mean`, restart w `update`), `RatingBook.season_restart`
  (`league_rates` czyta średnią zakończonego sezonu po przerwie), stałe
  `SEASON_GAP_S`, `SEASON_PRIOR_MATCHES`, `SEASON_RESTART_LEVEL_ONLY`;
- `score_model.build_model(season_restart=)`; `sport_confidence.walk_forward_rows`
  / `settled_shadow_rows`; `run_sport_confidence.DbForecaster`;
  `fit_sport_confidence.py --league-season-restart`; `fit_sport_derived`
  (`estimator_switches`);
- `epochs.LEAGUE_SEASON_RESTART_FROM_UTC`, `league_season_restart(sport, date, at)`;
- testy `tests/sofa/test_league_season_restart.py`; rejestr
  `T-BB-SEASON-RESTART-superbet`.

Pominięte / nie testowane: live SPORT_CONFIDENCE nie uruchomiony (offline);
krzywe przy nowej regule ocenione tylko na liniach syntetycznych, nie na
rozliczonych liniach Superbetu (za mało meczów NBA); wersja „tylko poziom”
dla hokeja / siatkówki nie mierzona.
