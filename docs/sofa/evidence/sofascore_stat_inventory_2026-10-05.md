# Inwentarz statystyk Sofascore: co jest w cache, a czego nie czytamy (2026-10-05, plan F1.4)

Plan `docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md`, F1.4. Dla każdego sportu
porównuję klucze obecne w zapisanych payloadach Sofascore z kluczami, które
czyta kod. Każda pozycja ma jeden z trzech statusów:

- **USED** - czyta ją kod: metryka, rozliczenie, rating albo strażnik. Strażnik
  oznacza, że klucz służy tylko do kontroli i jest oznaczony „(strażnik)".
- **MEASURED_NO_GAIN** - była zmierzona albo zbudowana i odrzucona; podane
  jest źródło.
- **TODO** - leży w cache, nikt jej nie czyta i nikt jej nie zmierzył.

Raport. Żadna metryka nie została dodana.

## Jak liczone

- **Baza.** `data/sofa.db`, otwarta tylko do odczytu. Payloady siedzą w
  tabeli `sofa_event_stats`, w kolumnach `statistics_json`, `incidents_json`
  i `lineups_json`; sport bierze się z `sofa_listed_event.sport`.
- **Próbka.** Losowo 500 zakończonych meczów na sport (`ORDER BY random()`).
  Dla `/lineups` piłki dodatkowo 400 ostatnio pobranych meczów, bo w próbce
  losowej `/lineups` miało tylko 8 z 500.
- **Kolumna „obecny".** Liczba meczów z kluczem w próbce, na liczbę meczów
  z danym payloadem. Klucz `/statistics` liczy się raz na mecz, w dowolnym
  okresie.
- **Pokrycie cache** (wiersze `sofa_event_stats`):

| sport | mecze ze statystykami | z `/statistics` | z `/incidents` | z `/lineups` |
|---|---|---|---|---|
| piłka | 202 840 | 114 248 | 168 079 | 4 551 |
| tenis | 184 767 | 148 579 | 0 | 0 |
| hokej | 22 553 | 22 523 | 0 | 9 707 |
| koszykówka | 36 786 | 36 699 | 0 | 34 037 |
| siatkówka | 10 898 | 10 803 | 0 | 3 281 |
| CS2 | (osobne tabele) `cs2_series` 16 826 serii, `cs2_map`, `cs2_player_map` | - | - | - |

- **CS2.** Surowych payloadów CS2 nie ma w bazie: `cs2_store` zapisuje tylko
  sparsowane kolumny. Inwentarz CS2 dotyczy więc kolumn, nie kluczy.
- **Lista „co czyta kod".** Zebrana przeglądem kodu: `metrics.py`,
  `players.py`, `shadow.py`, `score_model.py`, `cs2*.py`, `settle.py`,
  `tennis_*` i skrypty. Pliki i linie są podane niżej. Sprawdziłem wyrywkowo
  (grep), m.in. że `shadow.py` nie czyta drużynowego `/statistics`, a
  `flash_assists` / `adr` / `kast` pojawiają się tylko w schemacie `db.py`.

**Uwaga: `docs/sofa/MODELE_HOKEJ_KOSZ_SIATKA.md` §A.7 jest nieaktualny.**
Sekcja (stan na 10-02) podaje `/statistics` hokeja, koszykówki i siatkówki
jako „0 / 0 / 0 w cache, nigdy nie pytany". Dziś w cache jest 22 523 / 36 699
/ 10 803 meczów z tym payloadem - backfill
(`backfill_event_stats.py --sport hockey|basketball|volleyball`) go pobrał.
Kod nadal go nie czyta.

## Piłka nożna

### `/statistics` (265 z 500 meczów miało payload)

| klucz | obecny | status | gdzie / źródło |
|---|---|---|---|
| cornerKicks | 240 | USED | `corners_*` (metrics.py:76-147), rozliczenie, rating |
| fouls | 201 | USED | `fouls_*`; suma drużyny dowodzi zera `player_fouls_for` (players.py:101-104) |
| offsides | 214 | USED | `offsides_*` |
| totalShotsOnGoal | 155 | USED | `shots_*` (to WSZYSTKIE strzały - pułapka z memory `sofascore-payload-traps`) |
| shotsOnGoal | 190 | USED | `shots_on_target_*` |
| goalkeeperSaves | 155 | USED | `saves_total/_for`, `saves_1h_*` |
| throwIns | 175 | USED | `throw_ins_*` |
| goalKicks | 172 | USED | `goal_kicks_*` |
| totalTackle | 155 | USED | `tackles_*`; suma drużyny dla `player_tackles_for` |
| expectedGoals | 141 | USED | `xg_total/_for` zadeklarowane; Superbet nie wycenia xG (history/FIRST_RUN_FINDINGS.md:93-95), więc żaden wiersz z tego nie powstaje |
| yellowCards, redCards | 254 / 173 | USED (strażnik) | dowód zera kartek, kompletność (cache.py:22) - kartki liczone z incydentów |
| shotsOffGoal, blockedScoringAttempt | 188 / 159 | USED (strażnik) | tożsamość strzałów (metrics.py:932-937) |
| hitWoodwork | 106 | USED (strażnik) | tożsamość strzałów; **rynek „strzały w obramowanie" (42 wystąpienia 10-05) - TODO jako metryka** |
| freeKicks | 219 | USED (strażnik) | towarzysz placeholderu (metrics.py:387-396) |
| passes | 155 | USED (strażnik) | znacznik pełnego feedu (`FULL_FEED_MARKER`); rynek „liczba podań" (inne dni) - TODO |
| interceptionWon | 155 | USED (strażnik) | suma drużyny dla `player_interceptions_for` |
| ballPossession | 221 | TODO (odrzucone argumentem, nie pomiarem) | „suma obu stron = 100, stała w przebraniu" (history/PLAN_SOFA_PIPELINE.md:691); jako cecha modelu nigdy nie mierzone |
| bigChanceCreated / bigChanceMissed / bigChanceScored | 84 / 75 / 65 | TODO | brak rynku; kandydat na cechę (F3.2), niemierzony |
| totalShotsInsideBox / totalShotsOutsideBox | 155 / 155 | TODO | brak rynku drużynowego; cecha niemierzona |
| touchesInOppBox, finalThirdEntries, finalThirdPhaseStatistic, fouledFinalThird | 119 / 89 / 119 / 87 | TODO | cechy niemierzone |
| expectedGoalsOnTarget, goalsPrevented | 46 / 46 | TODO | rzadkie (9%) |
| accuratePasses, accurateLongBalls, accurateCross, accurateThroughBall | 155 / 155 / 155 / 106 | TODO | bez rynku |
| dribblesPercentage, duelWonPercent, groundDuelsPercentage, aerialDuelsPercentage, wonTacklePercent | 155 / 155 / 155 / 155 / 89 | TODO | proporcje, bez rynku |
| totalClearance, dispossessed, ballRecovery | 155 / 155 / 89 | TODO | bez rynku |
| diveSaves, highClaims, punches, penaltySaves | 55 / 78 / 40 / 4 | TODO | bez rynku |
| errorsLeadToShot, errorsLeadToGoal | 70 / 20 | TODO | bez rynku |
| kilometersCovered, numberOfSprints | 80 / 80 | TODO | dane z trackingu, tylko część lig |
| avgRating | 7 | TODO | znikome pokrycie |

**Zmierzone na składzie próbki (nie na nowych kluczach).**
`docs/sofa/history/RAPORT_2026-10-04_POROWNYWALNOSC_HISTORII.md` §K2:
- próbka z tych samych rozgrywek dla rożnych / fauli / kartek / strzałów /
  spalonych - bez zysku albo gorzej;
- próbka tylko z bieżącego sezonu - gorzej wszędzie.

To pomiar wyboru meczów do próbki, a nie nowej statystyki.

### `/incidents` (428 z 500)

| klucz | obecny | status | gdzie / źródło |
|---|---|---|---|
| card (yellow / red / yellowRed), rescinded, isHome, player, manager | 188 / 34 / 18 | USED | `cards_points_*` (metrics.py:747-866); kartka sztabu pomijana |
| substitution | 183 | USED (strażnik) | `CARDS_NOT_RECORDED` / `ZERO_NOT_RECORDED` |
| goal (regular / penalty / ownGoal) | 368 / 75 / 15 | USED (strażnik) | tożsamość goli z wynikiem (metrics.py:925-941); gole liczone z wyniku |
| goal: `time`, `player`, `assist1`, `addedTime` | - | TODO | rynki minuty / kolejności goli, strzelca, gola w doliczonym czasie (F1.1: `fb.goal_timing`, `fb.player_goals`, `fb.goal_sequence`) |
| goal: `footballPassingNetworkAction` (`bodyPart`, `situation`, `goalType`, współrzędne) | ~26 tys. meczów w cache | TODO | „gol głową / lewą nogą / spoza pola / z wolnego", „sposób zdobycia gola" (F1.1: `fb.player_goal_detail`, `fb.goal_method`) |
| inGamePenalty (missed) | 15 | TODO | rynki rzutów karnych (`fb.penalties`) |
| varDecision (*) | 11 / 4 / 4 / 3 / 2 / 1 | TODO | zapisuje decyzję, nie podejście do monitora - rynki VAR i tak NOT_COMPUTABLE |
| period, injuryTime | 422 / 114 | TODO | doliczony czas; brak odczytu |
| penaltyShootout | 2 | TODO | dogrywka / karne są dziś odrzucane z metryk liczących (metrics.py:17-24) |

### `/lineups` (zawodnicy; 29 z 400 ostatnio pobranych, 8 z 500 losowych)

| klucz | status | gdzie / źródło |
|---|---|---|
| minutesPlayed | USED | bramka występu (players.py) |
| totalShots, onTargetScoringAttempt, goalAssist, fouls, totalTackle, interceptionWon, totalOffside | USED | 7 propsów (players.py:59-118) |
| shotOffTarget, blockedScoringAttempt, hitWoodwork | USED (strażnik) | tożsamość dowodząca zera celnych |
| wasFouled | MEASURED_NO_GAIN | suma zawodników vs faule rywala domyka się w 58,1% meczów drużyny - zera nie da się dowieść (players.py:94-98) |
| goals, ownGoals, penaltyWon / penaltyMiss / penaltyConceded | TODO | strzelec gola (incydenty dają to samo z minutą) |
| totalPass, keyPass, accuratePass, touches, totalCross, totalLongBalls | TODO | rynek „liczba podań zawodnika" (inne dni, 54 wystąpienia łącznie) |
| saves, savedShotsFromInsideTheBox, punches, goodHighClaim, goalsPrevented | TODO | obrony bramkarza (rynek drużynowy `saves_*` już jest) |
| expectedGoals, expectedAssists, expectedGoalsOnTarget, rating, ratingVersions, *ValueNormalized | TODO | cechy, rzadkie |
| aerialWon / aerialLost, duelWon / duelLost, wonContest / totalContest, challengeLost, dispossessed, possessionLostCtrl, ballRecovery, totalClearance, outfielderBlock, wonTackle, lastManTackle, clearanceOffLine, errorLeadTo* | TODO | bez rynku |
| kilometersCovered, numberOfSprints, topSpeed, metersCovered* , ballCarries*, totalProgression | TODO | tracking, nieliczne ligi |
| poziom drużyny: `missingPlayers`, `formation`, `confirmed` | TODO | **nieobecności = F3.1** (dostępność przed meczem niezmierzona; sonda 9 h przed - brak składów) |

**Propsy jako całość.** Pomiar: ślepo -45,8% [-50,9; -40,0] na 5 768
wierszach (memory `player-props-never-ev-at-superbet`). Dopuszczone decyzją
operatora wbrew temu pomiarowi.

## Tenis

### `/statistics` (406 z 500)

| klucz | obecny | status | gdzie / źródło |
|---|---|---|---|
| aces, doubleFaults | 406 / 406 | USED | `aces_*`, `double_faults_*`, `serve_points_*`, prior tieru (tennis_prior.py:65-73) |
| gamesWon | 187 | USED (strażnik / fallback) | gemy liczone z wyniku setów; to tylko kontrola (metrics.py:1099-1131) |
| tiebreaks | 187 | USED (fallback) | potrafi przeczyć wynikowi seta (metrics.py:1081-1094) |
| firstServePointsAccuracy, secondServePointsAccuracy, firstReturnPoints, secondReturnPoints | 186 / 186 / 304 / 304 | MEASURED_NO_GAIN | model serwis/return: Brier 0,2364 wobec hits/n 0,2397 i ceny 0,2102 - przegrywa z ceną (scripts/sofa/measure_tennis_serve_model.py, commit `b9f19f88`; czytane po `name`, np. „First serve points" = `firstServePointsAccuracy`, sprawdzone na payloadzie) |
| serviceGamesWon, serviceGamesTotal | 405 / 176 | TODO | częstość utrzymań serwisu; **pułapka: `serviceGamesTotal` występuje dwa razy („Service games played" i „Return games played")** |
| breakPointsScored, breakPointsSaved | 312 / 186 | TODO | bez rynku; cecha niemierzona |
| servicePointsScored, receiverPointsScored, pointsTotal | 371 / 311 / 396 | TODO | rynki „liczba punktów" zawodnika / w secie (F1.1 `tn.points`, 60 wystąpień 10-05) |
| firstServeAccuracy, secondServeAccuracy | 186 / 186 | TODO | mianownik = punkty serwisowe zawodnika; rynek „liczba serwisów" (`tn.service_points`, 30) |
| maxPointsInRow, maxGamesInRow | 405 / 378 | TODO | bez rynku |
| winnersTotal, unforcedErrorsTotal, errorsTotal i 19 rozbić (forehand / backhand / volley / lob / drop shot / return / overhead) | 11 | TODO | 2% meczów (duże turnieje) - pokrycie za małe na próbkę |

### Listing / `/event`

| klucz | status | gdzie / źródło |
|---|---|---|
| homeScore/awayScore `.period1..5`, `.current` | USED | gemy, sety, tie-breaki, rating (tennis_score.py:47-86, metrics.py:1133-1162) |
| `period{k}TieBreak` | TODO (czytane tylko w pomiarze) | punkty tie-breaka - rynki „tiebreak - liczba punktów / dokładny wynik" (F1.1 `tn.tiebreak_points`); price_tennis_serve_model.py:212 |
| `firstToServe` | TODO | kto serwuje gem N; potrzebne dopiero z historią gem po gemie |
| groundType, defaultPeriodCount, homeTeam.type, winnerCode, time.periodN, tournament.category.name | USED | nawierzchnia, best-of, singiel, rating, tier |
| `/point-by-point` | TODO (nie w cache) | endpoint istnieje (`docs/sofa/evidence/event_15345277_point_by_point.json`); bez niego cała klasa rynków gem/punkt jest NOT_COMPUTABLE (F1.1: `tn.game_order` 1 020 + `tn.points_in_game` 736 wystąpień 10-05 + 3 111 kombinacji) |

**Zmierzone dodatkowo.** `scripts/sofa/price_tennis_serve_model.py`
(docstring): czynniki pominięte, bo gorsze poza próbą - odchylenie
nawierzchni gracza, obciążenie z 3 dni, super tie-break.

## Hokej

### `/statistics` (500 z 500; od backfillu, nigdy nieczytane)

| klucz | obecny | status |
|---|---|---|
| SuspensionMinutes, suspensions | 338 / 88 | TODO |
| Shots, saves | 172 / 89 | TODO (strzały drużyny; Superbet ma rynki strzałów w hokeju? - niesprawdzone, SHADOW ich nie mapuje) |
| puckPossession | 126 | TODO |
| PowerPlayPercentage, fiveVsFour / fiveVsThree / fourVsThree ConversionPercentage | 88 / 80 / 13 / 4 | TODO |
| FaceOffWinPercentage (+ even / powerPlay / shortHanded) | 80 | TODO |
| Hits, Blocked, Giveaways, Takeaways | 80 | TODO |
| evenStrength / powerPlay / shortHanded ShotPercentage | 80 / 80 / 54 | TODO |
| emptyNetGoals | 28 | TODO (pusta bramka wpływa na totale - cecha niemierzona) |
| corsiPct, fenwickPct, averageShotDistance, *Goals (tip / snap / slap / wrist / backhand / betweenLegs) | 1 | TODO (znikome pokrycie) |

### `/lineups` (222 z 500)

| klucz | status | gdzie |
|---|---|---|
| points, assists, shots, powerPlayPoints, plusMinus, blocked, faceOffWins, hits, saves, secondsPlayed | USED | rozliczenie linii zawodników i player_model (shadow.py:259-277, 945-970) - pomiar, propsy poza krzywymi |
| goals | USED (strażnik) | box musi się zgadzać z wynikiem (shadow.py:917) |
| penaltyMinutes, giveaways, takeaways, shotsMissed, blockedAttempts, faceOffTaken / faceOffPercentage, evenStrength* / powerPlay* / shortHanded* (gole, asysty, punkty, obrony), shotsAgainst, savePercentage, firstStar / secondStar / thirdStar | TODO | |

**Wynik / listing.** `homeScore.period1..N`, `normaltime`, `overtime`,
`winnerCode`, `status` - USED (rozliczenie, model wyniku).

**Zmierzone (model wyniku, nie te klucze)** -
`docs/sofa/RAPORT_KALIBRACJA_SPORTOW_2026-10-05.md` §1 i
`data/analysis_2026-10-04_shadow/RAPORT.md` §1:
- zwycięzca / 1X2 gorzej niż cena;
- totale b +0,58 [-0,09; +1,21], niepotwierdzone.

## Koszykówka

### `/statistics` (500 z 500; nigdy nieczytane)

| klucz | obecny | status |
|---|---|---|
| fieldGoalsScored, twoPointersScored, threePointersScored, freeThrowsScored | 469-472 | TODO (rynki „trójki drużyny" itd. - SHADOW ich nie mapuje; niesprawdzone, czy Superbet je wystawia) |
| rebounds, offensiveRebounds, defensiveRebounds, assists, steals, blocks, turnovers | 403-444 | TODO |
| totalFouls, timeouts | 432 / 159 | TODO |
| biggestLead, maxPointsInARow, leadChanges, timeSpentInLead | 405-433 | TODO |

### `/lineups` (458 z 500)

| klucz | status | gdzie |
|---|---|---|
| points, assists, rebounds, threePointsMade, blocks, steals (+ sumy P+R+A itd.), secondsPlayed | USED | rozliczenie i player_model (shadow.py:281-330, 945-950) |
| turnovers, personalFouls, offensive / defensiveRebounds, fieldGoal* / twoPoint* / freeThrow* (Made / Attempts / Pct), plusMinus, rating, pir, usage, effectiveFieldGoalPercentage, trueShootingPercentage | TODO | |

**Zmierzone.** `RAPORT_KALIBRACJA_SPORTOW_2026-10-05.md` §1: wszystkie
rodziny NOT_CALIBRATED, zawyżają o 3,3-11,2 pp na liniach Superbetu.
Rezygnacja z back-to-back i z mocniejszej separacji: commit `e39f5dda`.

## Siatkówka

### `/statistics` (494 z 500; nigdy nieczytane)

| klucz | obecny | status |
|---|---|---|
| aces, serviceErrors | 205 / 164 | TODO |

### `/lineups` (144 z 500; 52 z kluczami statystyk)

Klucze: attackPoints, attacksTotal, attackErrors, attacksBlocked,
attacksEfficiency, blockPoints, aces, serves, serveErrors, receptionsTotal,
receptionWin, receptionErrors, receptionPerf, receptionPositivity,
breakPoints, pointsTotal, winLoss. **Status: TODO** - siatkówka nie ma
rynków zawodników (`PLAYER_MARKETS["volleyball"] = {}`).

**Wynik / listing.** Punkty setów i wynik w setach - USED.

**Zmierzone.** Model serwisu (side-out) poprawiał totale setów, ale psuł
zwycięzcę - odrzucony (commit `e39f5dda`, `MODELE_HOKEJ_KOSZ_SIATKA.md` §0
i §A.3). Wobec ceny: b +0,01, brak informacji (night shadow RAPORT §2).

## CS2 (kolumny `cs2_map` / `cs2_player_map`)

| kolumna | status | gdzie / źródło |
|---|---|---|
| kills, deaths, assists, headshots | USED + MEASURED_NO_GAIN | rozliczenie `player_*` / `team_kills` i silnik (cs2.py:76-81, cs2_engine.py:340-350); na historii ~stopa bazowa (memory `cs2-shadow-measurement`); Elo zawodników przegrywa z ceną (commit `e39f5dda`) |
| home_rounds / away_rounds, winner_code, status_type | USED | wynik mapy i silnik (cs2_engine.py:316-329) |
| flash_assists, first_kills_diff, kd_diff, adr, kast | TODO | zapisywane (cs2_store.py:203-207), nikt nie czyta |
| home/away_period1, period2, overtime, home_starting_side, length_s, map_name | TODO | połowy mapy, strona startowa, mapa - niezmierzone (`map_name` jako cecha puli map: niezmierzone) |

## Podsumowanie

| sport | USED | MEASURED_NO_GAIN | TODO |
|---|---|---|---|
| piłka `/statistics` | 18 (w tym 8 strażników) | 0 | 32 (+ ballPossession odrzucone argumentem) |
| piłka `/incidents` | karty, zmiany, gole (strażnik) | 0 | minuta / strzelec / sposób gola, karne, VAR, doliczony czas |
| piłka `/lineups` | 11 | 1 (wasFouled) | ~60 + missingPlayers |
| tenis `/statistics` | 4 | 4 (serve / return) | 11 + 22 rzadkie (winners / errors) |
| hokej `/statistics` | 0 | 0 | wszystkie (~25) |
| hokej `/lineups` | 11 | 0 | ~30 |
| koszykówka `/statistics` | 0 | 0 | wszystkie (17) |
| koszykówka `/lineups` | 7 | 0 | ~15 |
| siatkówka | 0 | 0 | 2 + 17 (lineups) |
| CS2 | 4 + wynik mapy | (4 jako sygnał) | 5 + 6 |

**Najtańsze TODO, które mają rynek Superbetu** (liczby wystąpień z F1.1,
10-05):
- `hitWoodwork` (drużyna 42 i zawodnik 29);
- tenisowe `pointsTotal` (60) i punkty serwisowe (30);
- incydenty goli z minutą i strzelcem (`fb.goal_timing` 282,
  `fb.player_goals` 179, `fb.goal_sequence` 168);
- `period{k}TieBreak` dla punktów tie-breaka (na innych dniach).

Dla wszystkich obowiązuje ta sama reguła: „mierz zanim użyjesz" (plan,
sekcja 2). Rynek wchodzi dopiero z krzywą zmierzoną poza próbą.

Czego tu nie sprawdzono:
- czy Superbet wystawia rynki drużynowe hokeja i koszykówki na klucze
  `/statistics` (SHADOW zapisuje tylko rodziny, które mapuje - nazw
  niezmapowanych nie ma w żadnym artefakcie);
- pokrycie kluczy per liga (próbka jest losowa po wszystkich meczach).
