# Piłka nożna: symulator minuta po minucie wpięty w pipeline - 2026-11-06

Polecenie operatora 2026-11-06 („TEN SYMULATOR MUSI BYĆ JUŻ DZISIAJ"),
przekazane przez sesję główną. Wzorzec: wpięcie modelu punktowego tenisa
(commit 2e867d87, `tennis_point_model_2026-11-05.md`). Pomiar samego
symulatora: `football_sim_2026-11-06.md` (commit d16ca339).

**Przełącznik:** `epochs.FOOTBALL_SIM_FROM_UTC` = **2026-11-07 00:00Z**
(`epochs.football_sim(date, build_at)`). Dzień 11-06 jest bez zmian. Wcześniejsze
włączenie (11-06 jako dzień mieszany) może zarządzić wyłącznie operator.
Grupa ledgera: **„od 11-07"**, wspólna ze staged refitem 11-07
(`audit_ledger.STAGED_REFIT_1107_EPOCH_FROM_DATE`). Gdy przyjdzie audyt, rozdzieli
je po rodzinie rynku.

## 1. Rynki (`epochs.FOOTBALL_SIM_MARKETS`, `bet.sofa.football_sim_markets`)

Wpięte są tylko rynki „ścieżki", których SHEET dotąd nie wyceniał. Rodziny,
które SHEET już wycenia, zostają przy dzisiejszym estymatorze.

| klucz | Superbet | wybory | strony |
|---|---|---|---|
| `htft` | Do przerwy / koniec meczu | 1/1 .. 2/2 (9) | OVER |
| `result_1h`, `result_2h` | 1. / 2. połowa - wynik | 1, X, 2 | OVER |
| `higher_scoring_half` | Połowa z większą liczbą goli | 1. poł., remis, 2. poł. | OVER |
| `team_scores_both_halves` | <drużyna> strzeli gola w obu połowach | 1, 2 | OVER / UNDER (Tak / Nie) |
| `btts_halves` | Obie drużyny strzelą: 1. poł. / 2. poł. | Tak/Tak .. Nie/Nie | OVER |
| `btts_any_half` | Obie drużyny strzelą w którejkolwiek połowie | - | OVER / UNDER |
| `first_goal_1h` | 1. połowa - pierwszy gol | 1, 2, nikt | OVER |
| `half_goals_combo` | Gole w 1. i 2. połowie (np. „U0.5/O1.5") | linie 0.5-3.5 | OVER |

Odrzucone, z powodem:

- **przedziały minutowe** (gol w 1-15 min itp.): minuta w doliczonym czasie i
  kolejność zdarzeń z cache nie dają pewnego rozliczenia;
- **dokładny wynik połowy**: lista Superbetu jest niepełna, więc nie ma rynku
  dwustronnego.

Mapowanie OFFER (`classify_odd(..., football_sim=True)`) używa dokładnych nazw
rynków i wyborów z prawdziwego zrzutu (Superbet 15202205, Churchill Brothers -
Northeast United, 2026-11-05). Nazwy drużyn porównuje dokładnie z nazwami
listingu. Czego nie zna, zostaje w `unmapped_markets` jak dotąd.

## 2. Rozliczenie (SETTLE / regrade)

Rozliczenie: `football_sim_markets.sim_value`, w `run_settle._settle_sim_market` i
`regrade_settled`.

- Wynik z 90 minut z doliczonym czasem (`metrics.regulation_score`). Dogrywka
  się nie liczy.
- Połowa: `period1`.
- Pierwszy gol 1. połowy:
  - z wyniku, gdy w 1. połowie strzeliła jedna strona albo nikt;
  - z incydentów (`football_incidents`, bieżący wynik, więc gol samobójczy idzie
    na konto strony, której go zapisano), gdy strzeliły obie.
- Zwroty: `settle.REFUND_REASONS`, jak wszędzie.
- Dane sprzeczne albo niepełne dają odmowę, nigdy domysł:
  - `INTERNAL_INCONSISTENT`;
  - `NO_REGULATION_SCORE`, `NO_HALF_TIME_SCORE`;
  - `HALF_ABOVE_MATCH`, `HALF_TIME_DISAGREES`;
  - `FIRST_GOAL_UNREADABLE` (incydenty z inną liczbą goli w 1. połowie niż
    `period1`).

Testy w `tests/sofa/test_football_sim_wiring.py`: 0-0, gol samobójczy, karny i
gol w 45+2, 90+4 i dogrywka, sprzeczności. Rozliczenie zgadza się z
`football_sim.path_actual`.

## 3. SHEET

- `bet.sofa.football_sim_sheet.SimPricer`: `p_central` z
  `football_sim.simulate`:
  - 4 000 symulacji, ziarno = id meczu;
  - parametry `config/sofa_football_sim_params.json` (kopia stałych pomiaru);
  - na centrach goli czystego ratingu SHEET-u (`goals_for` obu stron) i
    centrach kartek.
- Wiersz jest „tylko z ratingu" (`tennis_winner.RATING_ONLY_MARKETS`): bez
  próbki, nigdy w builderze, tylko własna krzywa.
- Każdy wiersz niesie:
  - znacznik `football_sim_rule` (`rebuild_plan` sam powtórzy SHEET, gdy go
    brak);
  - notkę `FOOTBALL_SIM`;
  - `UNFITTED_CONSTANTS: RATING_UNFITTED`.
- Brak centrów daje `NOT_RATED`.
- Rynki dwustronne mają OVER i UNDER, pozostałe tylko OVER.
- `epochs.leg_floor` się nie zmienia (0,70; test).

## 4. Krzywe i dowody z linii

**Krzywe** (`config/sofa_football_sim_curves.json`, `bet.sofa.football_sim_curves`):

- nakładane po krzywych tenisa, klucze w `no_pool_keys`, czyli bez puli;
- dopasowane przez `scripts/sofa/fit_football_sim_curves.py` na krokowym
  przejściu symulatora po historii Sofascore 2026-06-01..10-20: 40 025 meczów,
  2 681 246 wierszy, format `fit_confidence` z `realised_lo95` Wilsona, klasa
  `women` osobno.

Symulator na górze skali obiecuje za dużo. Na przykład kombinacje goli w
połowach przy p 0,85-0,875 trafiają 0,813. Krzywa to koryguje. **Poziom 0,70
osiągają tylko dwa klucze:**

- `team_scores_both_halves|UNDER` („nie strzeli w obu połowach"), od p 0,70:
  lo95 0,725 .. 0,915;
- `half_goals_combo|OVER`, od p 0,75: lo95 0,716 .. 0,791.

Pozostałe 7 rynków jest wpiętych i rozliczanych, ale żaden ich koszyk nie
sięga 0,70, więc się nie drukują. Najwyżej sięgają: `result_2h` 0,670,
`btts_any_half` UNDER 0,671, `htft` 0,606.

**Dowody z linii:**

- backfill `data/line_evidence/football_sim_lines.jsonl.gz`: 236 954
  rozliczonych linii Superbetu z `unmapped_prices` 10-14..11-05, 8 523 meczów,
  ostatni zrzut przed startem, druga strona szczebla przy rynkach dwustronnych;
- odmowy rozliczenia przy budowie backfillu:
  - `HALF_TIME_DISAGREES` 688;
  - `NO_HALF_TIME_SCORE` 759;
  - `INTERNAL_INCONSISTENT` 27;
  - `FIRST_GOAL_UNREADABLE` 12;
- `fit_line_evidence.py` liczy własne wpisy tych kluczy z backfillu (dni przed
  przełącznikiem) i z własnych rozliczonych wierszy od 11-07
  (`football_sim_curves.merge_evidence`), a pule sportu zostają bez zmian;
- pierwszy poranny `refresh_line_evidence.py --before 2026-11-07` je wpisze.

Bramki druku bez zmian:

- 0,70;
- x >= 0,90;
- marża szczebla <= 15% przy dwustronnych;
- jednostronne tylko z własną krzywą n >= 300.

## 5. Odłożona próba (reguła zamrożona przed liczeniem)

Reguła i skrypt: `scripts/sofa/measure_football_sim_wiring.py` (reguła w
docstringu). Dane:

- linie backfillu 2026-10-20..11-05 (po oknie krzywych): 168 194 linie;
- p jak w SHEET;
- wariant A: sama krzywa;
- **wariant B (werdykt):** krzywa i dowody z linii zainstalowane dziś (klucze
  nie mają jeszcze własnych, więc obniża je pulowany offset piłki);
- bramki CONFIDENCE;
- bootstrap po meczach 2 000, ziarno 7;
- ROI płaskiej stawki przed i po podatku 12%.

| wariant | nogi / mecze | pewność | trafione | trafione - pewność | ROI | ROI po podatku |
|---|---|---|---|---|---|---|
| **B (werdykt), razem** | 2 183 / 1 791 | 0,790 | 0,810 | **+2,0 pp [+0,3; +3,6]** | -4,2% [-6,3; -2,3] | -15,7% |
| B: `team_scores_both_halves` | 2 083 / 1 773 | 0,793 | 0,814 | +2,1 pp [+0,3; +3,7] | -4,1% | -15,6% |
| B: `half_goals_combo` | 100 / 100 | 0,740 | 0,740 | +0,0 pp [-8,5; +8,1] | -7,7% [-18,4; +2,5] | -18,8% |
| A (sama krzywa), razem | 3 186 / 2 309 | 0,784 | 0,764 | -2,0 pp [-3,5; -0,5] | -5,1% [-7,0; -3,1] | -16,5% |

Wszystkie nogi z pewnością >= 0,70, bez bramek ceny (kalibracja):

- B: 3 479 nóg, +4,0 pp [+2,7; +5,4];
- A: 4 481 nóg, +0,7 pp [-0,5; +1,9].

**Reguła stopu: PASS.** Górna granica B nie jest < 0. Nogi tracą marżę, jak
cały kupon: ROI ok. -4%. Przewagi nad ceną nie ma. Sama gorsza od ceny
skuteczność nie zatrzymuje wpięcia (decyzja operatora przy 1X2, 11-06).

Uzupełnienie, poza zamrożoną regułą: własne dowody z linii tych kluczy, tak jak
dopasuje je `refresh_line_evidence`, dołożone do dzisiejszego pliku.

- **C:** tylko linie sprzed 10-20, więc poza próbą: 2 702 nogi / 2 076 meczów,
  +1,0 pp [-0,6; +2,5], ROI -4,6% [-6,6; -2,8].
- **D:** linie sprzed 11-07 (to przeczyta 11-07; w próbie, optymistyczne):
  2 280 nóg, +1,9 pp [+0,2; +3,6], ROI -4,0%.

**Poprawka po fakcie (pominięta bramka).** Pierwsze uruchomienie nie stosowało
`ODDS_TOO_LOW` (kurs < 1/0,9202 = 1,087, `run_confidence` `MIN_ODDS`).
Skrypt dostał tę bramkę i został uruchomiony ponownie, reszta reguły bez
zmian:

- B: 1 971 nóg / 1 628 meczów, +1,9 pp [+0,2; +3,6], ROI -4,2% [-6,3; -2,1],
  reguła stopu PASS;
- A: 2 974 nóg, -2,4 pp [-4,0; -0,7];
- odmowy `ODDS_TOO_LOW`: 578.

Liczby w tabeli powyżej są z pierwszego uruchomienia, bez tej bramki.

Wniosek: sama krzywa lekko przeszacowuje (A). Dowody z linii doprowadzają
łańcuch do kalibracji: B i C pokrywają zero albo są powyżej.

## 6. E2E (kopia dnia 2026-11-05, zegar 17:10Z)

Kopia `runs/sofa/2026-11-05` w katalogu roboczym (`SOFA_RUNS_DIR`), zegar
`SOFA_NOW` = 17:10Z, iCloud wyłączony. Prawdziwe `runs/` i iCloud nietknięte,
sieci nie pytano.

- Wariant **„wył."**: przełącznik `None`.
- Wariant **„wł."**:
  - w skopiowanym `04_offer.json` dopisano 3 637 szczebli rynków ścieżki dla
    113 meczów, z własnych `unmapped_prices` tego dnia (ostatni zrzut <=
    17:10Z), przez `classify_odd(football_sim=True)` z OFFER;
  - przełącznik włączony.
- W obu wariantach ten sam kod i te same etapy: SHEET -> COUPON -> CONFIDENCE ->
  COUPON_ASSEMBLY, potem `audit_variants` i `audit_coupon`. Żaden etap się nie
  wywrócił; wszystkie zwróciły 0, `audit_variants` 1 (PARTIAL) w obu.

Wyniki:

- SHEET: 76 547 wierszy wobec 73 301, czyli +3 246 wierszy symulatora
  (`football_sim_rows`).
- Single: 2 949 wobec 2 927, czyli **+22, 0 ubyło**. Nowe są wyłącznie z
  kluczy symulatora:
  - 21 x `team_scores_both_halves` UNDER (np. „Celje zdobędzie gola w obu
    połowach: nie", pewność 0,815, kurs 1,12, marża 8,3%);
  - 1 x `half_goals_combo` („1.połowa liczba goli & 2.połowa liczba goli:
    powyżej 0.5 & powyżej 0.5", Crvena zvezda - Inter d'Escaldes, pewność
    0,716, kurs 1,26, jednostronna z własnej krzywej n 7 697).
- Wszystkie pozostałe nogi identyczne: 0 zmian pewności, kursu i blokady.
  `removed_by_reads` 42 / 42.
- Buildery: 54 / 54, identyczne; 0 nóg symulatora w builderach.
- Pozycje: 2 097 wobec 2 075, bloki 101 / 101.
- Audyty:
  - `audit_variants` ma te same uwagi poza notą C3 („read-set legs printed
    unread" 263 wobec 261: dwie nowe nogi weszły do zbioru do czytania; to
    nota, nie defekt);
  - `audit_coupon` różni się tylko licznikiem wierszy arkusza (VALUE 344 / 344).

## 7. Pliki

- Nowe:
  - `src/bet/sofa/football_sim_markets.py`, `football_sim_sheet.py`,
    `football_sim_curves.py`;
  - `scripts/sofa/fit_football_sim_curves.py`, `measure_football_sim_wiring.py`;
  - `config/sofa_football_sim_params.json`, `config/sofa_football_sim_curves.json`;
  - `data/line_evidence/football_sim_lines.jsonl.gz`;
  - `tests/sofa/test_football_sim_wiring.py`.
- Zmienione:
  - `epochs.py`, `offer.py`, `contracts.py`, `tennis_winner.py`,
    `superbet_names.py`, `rebuild_plan.py`;
  - `run_sheet.py`, `run_confidence.py`, `run_settle.py`, `regrade_settled.py`,
    `fit_line_evidence.py`, `audit_ledger.py` (komentarz);
  - testy `test_football_sim.py`, `off_scenarios.py`.

## Przeniesienie do dnia 2026-11-06 (decyzja operatora)

Operator: „WŁĄCZ JAK NAJWIĘCEJ RZECZY OD DZISIAJ”. `FOOTBALL_SIM_FROM_UTC` i
`FOOTBALL_SIM_FLOOR_FROM_UTC` = **2026-11-06 17:30:00Z**.

- Oba przełączniki działają według dnia i zegara budowy
  (`epochs._audit_1023_on`).
- Dzień 11-06 jest mieszany (grupa ledgera „11-06 mieszany”, potem „od
  11-07”). Nogi wydrukowane wcześniej zostają zablokowane.
- Przebudowa po 17:30Z sama czyta OFFER ponownie: poranny `04_offer.json` nie
  ma szczebli tych rynków (`rebuild_plan` `offer_has_sim`). Potem powtarza
  SHEET, bo wiersze nie mają znacznika.
- Dowody z linii 11-06 policzono rano bez tych kluczy, a
  `config/sofa_superbet_line_evidence.json` nie jest przeliczany w ciągu dnia.
  Do porannego odświeżenia 11-07 noga symulatora czyta więc:
  - pulowany offset piłki według kubełka d (np. `team_scores_both_halves`
    UNDER: -1,4 pp);
  - ogólny limit pasma ceny sportu (`cap:*`), bez własnych linii.

  Tak samo liczył wariant B odłożonej próby.


## Audyt 2026-11-07 — uwagi

Pełny raport: `docs/sofa/history/AUDYT_ZMIAN_2026-11-06.md`.

- Sekcja „Przeniesienie” mówi, że plik dowodu linii nie jest przeliczany w
  ciągu dnia. 11-06 został przeliczony o 17:34:29Z (przed rebuildem
  17:34:52Z); nogi symulatora czytały własne przesunięcia kluczy.
- Rynki wielowynikowe symulatora (HT/FT, kombinacje goli w połowach,
  `btts_halves`) są mapowane jako jednostronne i omijają regułę marży 15%,
  choć Superbet kwotuje cały zestaw: 39 z 52 nóg `half_goals_combo` 11-06
  miało marżę 15,2–16,9%. Zgodne z CLAUDE.md, ale to luka projektowa —
  zmiana wymaga pomiaru i decyzji operatora.
