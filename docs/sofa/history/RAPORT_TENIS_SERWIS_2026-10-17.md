# Raport 2026-10-17: rynki serwisowe tenisa i stan wszystkich rynków tenisa

Zlecenie operatora: zmierzyć i poprawić rynek asów / podwójnych błędów, w
osobnym worktree wdrożyć, przetestować (także E2E), zaktualizować
dokumentację i agentów, na koniec upewnić się, że każdy rynek tenisa ma
prawidłowy model i krzywą. Worktree `bet-wt-tennis-aces`, gałąź
`wt/tennis-aces-opponent`. Dowody: `docs/sofa/evidence/tennis_aces_opponent_2026-10-17.md`.

## Co weszło do kodu (przełączniki wyłączone - kupon bez zmian)

| zmiana | gdzie | stan |
|---|---|---|
| korekta asów o returnującego | `bet.sofa.tennis_aces_opponent`, `run_sheet.tennis_aces_correction`, `epochs.TENNIS_ACES_OPPONENT_FROM_UTC`, znacznik `tennis_aces_rule`, `rebuild_plan` | `None` - zmierzona, bez zysku na liniach Superbetu |
| korekta w replayu historii | `calibrate_from_cache --tennis-aces-opponent` (`tennis_aces_multiplier`, ten sam wzór) | tylko pomiar |
| rynki serwisowe w replayu | `calibrate_from_cache --tennis-serve-markets` (`serve_values`: asy / PB w secie, asy + PB) | tylko pomiar |
| krzywe tych rynków | `scripts/sofa/fit_tennis_serve_curves.py`, staged `data/refit_tennis_serve_2026-10-17/` | niezainstalowane |
| grupa zastępująca w instalatorze | `install_new_market_curves.py`, grupa `tennis_serve` (`replace_markets`) | gotowa |
| straż refitu | `prepare_refit.dropped_replay_rules` - install odmawia refitu bez flag wymaganych przez zainstalowane krzywe | czynna (dziś nic jej nie wymaga) |
| flagi refitu | `prepare_refit.py rebuild-cache-rows --tennis-aces-opponent --tennis-serve-markets` | **nie używać** przed `T-TENNIS-SERVE-MARKET-LINE` |
| pomiary | `measure_tennis_aces_opponent.py`, `measure_tennis_serve_market_line.py` | w repo |
| sprawdziany | `T-TENNIS-SET-GAMES-OVER`, `T-TENNIS-SERVE-MARKET-LINE` (PROPOSED, od 10-18) | rejestr |

Testy: `tests/sofa/test_tennis_aces_opponent.py` (12), `test_tennis_serve_curves.py` (5);
cały `tests/sofa`, ruff, mypy --strict, rejestr - czyste (wyniki w sekcji
"Bramki" niżej).

## Dlaczego nic nie włączono

1. Korekta asów: na prawdziwym SHEET i liniach Superbetu (64 mecze, 1 364
   linie) log-loss +0,0060 [-0,0251; +0,0348]. W historii asy łączne gorzej
   na wszystkich liniach (+0,0124). Pierwszy, obiecujący pomiar (-0,058 na
   liniach Superbetu) był względem uproszczonego modelu, nie SHEET - prior
   tieru i zakres próbki SAMPLES robią już tę część pracy.
2. Krzywe rynków serwisowych przechodzą bramkę na historii, ale na liniach
   Superbetu drukowałyby nogi 20-30 pp poniżej pewności. Mechanizm opisany
   w dowodach (sekcja 4): krzywa z siatki linii syntetycznych vs jedna linia
   rynku przy medianie.

## Stan wszystkich rynków tenisa

Źródło: audyt agenta (tylko odczyt, 2026-10-17), liczby oznaczone (S)
sprawdzone przeze mnie skryptem; reszta to liczby agenta (niesprawdzone
lokalnie - patrz `subagent-numbers-need-verification`).

| rynek | wycena | krzywa | na liniach Superbetu / drukowane | werdykt |
|---|---|---|---|---|
| `games_set1_total`, `games_set2_total` | sąsiedzi ratingu | tak | drukowane 10-09..16 (S): UNDER -2,0 / +2,0 pp, OVER -0,8 / +7,3 pp | produkcyjny |
| `games_won_for` | sąsiedzi ratingu | tak | UNDER (S) -0,4 pp [-5,8; +4,6], 324 nogi | produkcyjny (trzyma go offset dowodów linii) |
| `sets_total` | sąsiedzi ratingu (best-of-three) | UNDER | 3 nogi | produkcyjny, mały wolumen |
| `games_won_set1_for` / `set2_for` | sąsiedzi ratingu | tak | OVER (S) -7,1 / -6,6 pp, przedziały dotykają zera | **podejrzenie**: `T-TENNIS-SET-GAMES-OVER` |
| `games_total` | 50/50 NB + rating | tak | agent: drukuje 0 od 10-09 | nic nie drukuje |
| `match_won_for`, `set1/set2_won_for`, `set_score_not` | rating / sąsiedzi | tak | agent: za mało dni | tymczasowe |
| `handicap_games`, `most_games`, handicapy setów | sąsiedzi / próbki | czytane tylko przez dowody linii | agent: linie p 0,70-0,95 realizują 0,55-0,65 | nic nie drukuje (ochrona działa) |
| `tiebreaks_total` | normalny na próbce | mężczyźni do 0,60; kobiety z puli klasy | agent: dLL +0,053 | luka (podejrzenie: replay rzadko go produkuje) |
| `set_score` | sąsiedzi | tak | agent: 0 nóg | nic nie drukuje |
| asy / PB w meczu | NB na próbce + prior tieru | tak | (S) krzywa >= 0,70: -22,6 pp; drukowane 14: 0,714 vs 0,759 | drukuje tylko krótki kurs; korekta zmierzona, wyłączona |
| asy / PB w secie, asy + PB | NB na próbce | brak (> 0,60) | (S) nowe krzywe -20..-31 pp | nic nie drukuje; krzywe niezainstalowane |
| "Asy 5+" itd. (drabinki N+ od 10-17), "Podwójne błędy" (najwięcej), handicap PB | - | - | agent: niezmapowane | nieczytane |

Tenis jako całość (S): drukowane 10-09..10-16 -1,0 pp [-3,5; +1,5], 1 473
nogi, ROI -5,5% - skalibrowane, bez przewagi nad ceną.

## Czego ta sesja nie domknęła (uczciwie)

- **"Każdy rynek production grade"** - nie. To, co drukuje, jest
  skalibrowane w sumie; rynki z luką albo nic nie drukują (ochrona dowodów
  linii), albo są podejrzeniem z przedziałem dotykającym zera. Prawdziwa
  naprawa wspólna dla asów / PB / setów i prawdopodobnie gemów zawodnika w
  secie OVER to **krzywa na liniach rynkowych** (jak A7 w koszykówce): nie
  mamy historii linii rynkowych tych rynków; kandydat do zmierzenia -
  krzywa dopasowana tylko na liniach rynkowych replayu (proxy z dowodów,
  sekcja 4).
- Niezmapowane drabinki serwisowe N+ i "Podwójne błędy" - mapowanie ma sens
  dopiero, gdy rynki serwisowe dostaną krzywą, która trzyma na liniach rynku.
- Liczby agenta oznaczone wyżej bez (S) nie były sprawdzone lokalnie.

## E2E i bramki

**E2E SHEET 10-17** (kopia artefaktów dnia w scratchu, `SOFA_RUNS_DIR` na
kopię, prawdziwy `run_sheet.main` z kodem worktree, przełącznik wyłączony vs
ustawiony na 2026-10-01): 166 046 wierszy wyłączony, 166 048 włączony; różnią
się wyłącznie wiersze asów - 312 przeliczonych (`aces_for` 94, `aces_total`
46, `aces_set1/2_for` po 60, `aces_set1/2_total` po 26; 308 z notatką korekty,
6 "no correction"), plus 2 szczeble `aces_set2_total` 0,5, które weszły w
zakres modelu. Każdy z pozostałych 165 732 wierszy identyczny poza znacznikiem
`tennis_aces_rule` (na każdym z 10 515 wierszy tenisa, na żadnym piłki).
Ruch p asów: średnio 0,0000, maksymalnie 0,363. Wyjście tylko do scratcha
(`output_path` obu przebiegów); prawdziwe pliki 10-16 nietknięte (md5), 10-17
zmieniła przebudowa drugiej sesji (20:00Z, 20:43Z), nie ten przebieg.
CONFIDENCE / COUPON_ASSEMBLY nie były uruchamiane z włączonym przełącznikiem -
nic nie włączono; ich odczyt krzywych sprawdza `measure_tennis_serve_market_line.py`.

**Bramki:** `tests/sofa` 5120 passed / 8 skipped; ruff (`src/bet/sofa`,
`scripts/sofa`) czysty; `mypy --strict` czysty (282 pliki);
`check_test_registry.py` 15 testów, 0 uwag.
