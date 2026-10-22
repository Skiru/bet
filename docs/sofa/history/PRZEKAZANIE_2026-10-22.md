# Przekazanie sesji - 2026-10-22 (stan na ~14:00Z)

Plik dla sesji, która wznawia pracę 2026-10-23. Stan opisuje to, co było prawdą w chwili zapisu.
Przed działaniem sprawdź go komendami poniżej.

## 1. Co weszło na main (wypchnięte, origin/main = `4269ecdf`)

| commit | przełącznik | od |
|---|---|---|
| `460a2093` | `BASKETBALL_PLAYER_V2`: 9 dodatkowych linii zawodników NBA w SHADOW | 2026-10-23 00:00Z |
| `bffa542c` | `SPORT_LATE_WINDOW`: dzień sportów mierzonych to [end(D-1), D+1 05:00Z) | 2026-10-23 00:00Z |
| `4269ecdf` | `LEAGUE_SEASON_RESTART`: stawka ligi koszykówki restartuje po przerwie >= 45 dni | 2026-10-23 00:00Z |

`LEAGUE_SEASON_RESTART` (raport: `NBA_SEZON_STAWKA_LIGI_2026-10-22.md`):
- reguła: liga po przerwie >= 45 dni czyta zwykłą średnią zakończonego sezonu, a jej poziom startuje od niej z wagą 10 meczów; udział gospodarzy zmienia się wolno. Tylko koszykówka.
- log loss poza próbą, nowa minus stara:
  - NBA, cały okres: -0.0006 [-0.0010, -0.0001];
  - NBA, starty sezonów: -0.0030 [-0.0050, -0.0012];
  - inne ligi kosza: -0.0001 [-0.0005, +0.0003];
  - kosz razem, cały okres: na granicy zera (-0.0003 [-0.0006, +0.00004]).
- uwaga: ostateczny kształt reguły (szybki poziom, wolny udział gospodarzy) wybrano po pierwszym pomiarze, na tych samych danych. Progi 45 dni i 10 meczów ustalono przed pomiarem.
- replay 10-21/10-22: nogi NBA przez wszystkie bramki 42 -> 14 (UNDER 36 -> 6). Total modelu minus linia Superbetu: -13.2 -> -3.8 pkt.
- **krzywej kosza NIE refitowano** (fit z 10-14 na starej regule). Kalibracja nóg >= 0.70 się nie przesunęła. Refit tylko na zgodę operatora (polecenie w raporcie).
- test w rejestrze: `T-BB-SEASON-RESTART-superbet` (od 10-23). Ledger od 10-23 otwiera nową grupę.
- **pierwszy żywy test: SPORT_CONFIDENCE 10-23** (dotąd wszystko offline). Sprawdź poziom NBA względem linii i proporcję UNDER/OVER wśród nóg NBA.

## 2. Backfill danych (driver działa dalej po zamknięciu sesji)

- proces `backfill_driver.py` (PPID 1, przeżywa sesję); kopia skryptu w `runs/sofa/backfill/backfill_driver.py`.
- log: `runs/sofa/backfill/backfill_2026-10-22.log`, wyjście: `.out`.
- etapy: koszykówka i hokej (statystyki, składy) GOTOWE; listingi piłki GOTOWE (4 drużyny bez stron).
  - w toku: statystyki piłki 365 dni (o 13:34Z zostało 3 781).
  - potem: składy piłki, listingi i statystyki tenisa, statystyki i składy siatkówki.
- driver czeka (`BLOCKERS`), gdy działa `rebuild_day`, `record_results`, `refresh_line_evidence`, `resettle_sweep`, `regrade_settled` albo SETTLE. **Nie czeka na `run_pipeline.py` (poranny build)**: jeśli rano jeszcze działa, dzieli bridge z buildem. Decyzja operatora: zatrzymać na czas BOARD..SHEET czy nie.
- po 3 rc=2 z rzędu: `STOP`. Każdy etap jest wznawialny. Ponowne uruchomienie od miejsca przerwania:
  `nohup .venv/bin/python -I runs/sofa/backfill/backfill_driver.py >> runs/sofa/backfill/backfill_2026-10-22.out 2>&1 &`
  (skrypt ma zaszyte ścieżki logu 2026-10-22 i blokadę `.lock`).
- **luka listingów koszykówki ZAMKNIĘTA:** seed kosza był z 09-30 i 354 aktywne drużyny nigdy nie trafiły do kolejki. Uruchomiono `backfill_listings.py --sport basketball --days 730 --recent-days 30 --seed-before 2026-10-22T10:40:01+00:00` (log `bb_listings_2026-10-22.log`). Charlotte Hornets (3430): 5 -> 210 meczów; zostało 7 drużyn bez stron.
- podejrzenie (niezmierzone): ta sama luka seeda może dotyczyć innych sportów. Sprawdzenie: `--dry-run --recent-days 30 --seed-before <teraz>` dla każdego sportu.

## 3. Otwarte, czeka na decyzję operatora

1. **Refit krzywej koszykówki** z `--league-season-restart`: niekonieczny, porządkowy, wymaga zgody.
2. **Rozrzut kwart NBA** (model za pewny o ~2 pp na kwartach): wariant zarejestrowany zmierzony, wariant post-hoc przerwany.
   - szczegóły: `data/refit_2026-10-22/comp_spread/PARTIAL_RESULTS.md`.
   - kod WIP: gałąź `worktree-agent-a370bc755953d693f`, commit `1bf8a466`, NIE na main; worktree `.claude/worktrees/agent-a370bc755953d693f` trzyma surowe wyniki - nie usuwać przed decyzją.
   - NBA, cały okres: ALL -0.0019 [-0.0024, -0.0014], kwarty -0.0028, kalibracja kwart -2.3 -> -0.1 pp.
   - **handicap gorzej**: NBA +0.0027 [+0.0013, +0.0041], kosz razem +0.0008 [+0.0001, +0.0015]. W tej postaci kryterium "nie gorzej gdzie indziej" nie przechodzi.
   - inne ligi bez zmian (ALL -0.0001 [-0.0004, +0.0001]). Replay 10-21/10-22: 14 -> 8 nóg NBA.
   - niedokończone: wariant `--qonly` (poszerza tylko szum kwartowy, nie powinien ruszać handicapu) przerwany w połowie. Wybrany PO zobaczeniu wyniku handicapu, więc to pomiar post-hoc.
   - przełącznik i tak wymaga zgody operatora (proponowany od 10-24).
3. Propsy zawodników NBA: nic się nie drukuje, dopóki kubełek nie ma 50 rozliczonych linii (najwięcej 32). Czekać, nie poprawiać.
4. Zawodnicy po zmianie klubu (`PLAYER_TEAM_FROM_SIDE`) czekają na 5 meczów w nowej drużynie: reguła modelu, K7 w model-state.

## 4. Do sprawdzenia na danych 10-23

- Charlotte: czy Ball / Miller / Bridges / Diabate mają `p` w `player_model.jsonl` SHADOW 10-23. Wcześniej nie miały, bo w historii było 5 meczów.
- `BASKETBALL_PLAYER_V2`: czy SHADOW 10-23 zapisuje nowe rynki zawodników NBA (`player_v2_rule`).
- Kopie DB pomiarów w `data/refit_2026-10-22/` (`comp_spread/bb.db` 3,5 GB, `league_season/hk.db`, `vb.db`): usunąć po decyzjach z sekcji 3.

## 5. Wieczór 10-23

Z `SPORT_LATE_WINDOW` nocne NBA i NHL dnia D drukują się tylko przez ręczny wieczorny rebuild:
`rebuild_day.py --date 2026-10-23` około 20:00-21:00Z (RUNBOOK).
