# Prompt na sesję 2026-10-04 (rano, przed /sofa-day)

Wklej całość jako pierwszą wiadomość nowej sesji.

---

## STAN PO NOCY 10-03/04 (dopisane 04:25Z) — czytaj najpierw

Pełny raport nocy: `docs/sofa/RAPORT_NOC_2026-10-04.md` (kopia `data/night_2026-10-03/RAPORT_NOC.md`;
dowody i skrypty w `data/night_2026-10-03/<temat>/`). Commity nocy: `git log c6b60426..HEAD`
(lokalny main, NIE wypchnięte). Testy 2765 zielone, mypy czysty, ruff 92 jak przed nocą.

Co z listy poniżej jest już zrobione:
- pkt 2 tenis: zainstalowane TYLKO `sofa_tennis_tier_baselines.json` (backup
  `config/backup_2026-10-04_tennis/`); rating i korelacje NIE (brak zysku / gorzej poza próbą).
- pkt 3 strażnik zer: zrobiony i rozszerzony (ZERO_NOT_RECORDED, CARDS_NOT_RECORDED — czerwone-only
  listy incydentów liczyły mecz z 7 kartkami jako 2; przywrócone prawdziwe 0-0 spalonych/żółtych;
  pojedynczy rożny w niepełnym feedzie odrzucany). HISTORY_PARSER_VERSION 2026-10-04.2 —
  **pierwszy SHEET dziś parsuje historię ~10 min, to normalne.**
- pkt 4: 851 + 6 innych id na liście towarzyskich.
- pkt 5: zmierzone — pula NIE zawyżała goals_1h UNDER; strata z wybierania wierszy nad ceną
  (160 nóg, realnie .744 przy cenie .779, ROI −8.6%). Zbudowane: odtwarzanie połówek (opt-in
  `--with-halves`) i cienkie kubełki (działają od następnego refitu). Decyzja o
  `refused_markets += goals_1h_total|UNDER` — operator czeka na dzisiejsze rozliczenie 10-03.
- pkt 6: zmierzone (antyselekcja realna w 30/32 komórkach); `gap_shrink_k` zbudowany, WYŁĄCZONY.
- pkt 7: propozycja gorsza poza próbą — bez zmian.
- pkt 9: worktree usunięty.
- Sporty mierzone: ponownie rozliczone 09-29..10-02 po poprawce dopasowania (+10 meczów),
  kupony sportowe i rejestr przeliczone. Kryterium przyjęcia do kuponu: `data/night_2026-10-03/shadow/RAPORT.md`.
- Propsy: rekomendacja zdjąć wszystkie 7 z `admitted_player_markets` (−45.8% w ciemno) — decyzja operatora.

Co zostało na dziś:
- **pkt 1 (rozliczenie 10-03) NIE zostało zrobione w nocy** — robi je `/sofa-day` (D-1). Dodatkowo
  policz osobno: krótka lista rożnych UNDER, 6 nóg goals_1h UNDER z PDF, propsy (ręcznie w nocy:
  27 propsów z pewnością ≥0.70 → 14/5, −4.06 j.).
- Backfill: zrobione statystyki 365 dni wszystkich sportów i 730 dni hokej/kosz/siatka; tenis 730
  przerwany, piłka 730 nie zaczęta (sterownik: `data/night_2026-10-03/tools/night_driver.py <zadania>`, log `runs/sofa/backfill_logs/night_2026-10-03.log`; wznawialne).
- Refit na kopii bazy NIE skończył się (brak RAM-u: odtwarzanie trzyma ~26 GB, OrbStack 11 GB).
  Przed refitem wyłączyć OrbStack/Docker. Kopia: `data/refit_rehearsal_2026-10-04/` (42 GB, do usunięcia).
- Push: tylko na prośbę operatora.

---

Kontekst: wczoraj (10-03) zainstalowano refit (commit `9f0a9f21`, K_CENTRE piłka 15 / tenis 5,
nowe krzywe na 55.2 mln wierszy po nocnym backfillu), poprawiono prior „liga drużyny”
(`3be5f8ae`, `37753e84`, `ae922e10` — ostateczna reguła: liga z ratingu wygrywa, gdy ma w próbce
co najmniej połowę meczów większości; 851 i towarzyskie nigdy) i dopisano
`refused_markets` = shots_total|UNDER, fouls_total|UNDER, shots_for|UNDER. Dowody z wczorajszego
review (skrypty i wyniki zapytań): `data/review_2026-10-03/` (evidence/, curves/, review3/).
Raport refitu: `data/refit_2026-10-03/compare_report.md`. Pamięć: `refit-2026-10-03-installed`,
`goals-1h-under-reads-pool-across-gap`.

Pracuj w tej kolejności. Każda poprawka kodu ma test w `tests/sofa`; refity tylko między dniami
(teraz, przed dzisiejszym /sofa-day); po każdej zmianie pytest + ruff + mypy --strict; commit na main.

## 1. Rozlicz 10-03 w całości (zanim cokolwiek dopasujesz)
- `run_settle.py --date 2026-10-03 --include-unpriced`, D-5 (09-29) `--refetch-stat-gaps` +
  `regrade_settled.py --apply`, kupony sportowe, WSZYSTKIE, `record_results.py --from 2026-09-26 --to 2026-10-03`,
  `audit_ledger.py`, `audit_clv.py --from 2026-10-02 --to 2026-10-03`.
- Osobno policz (każde osobno, nigdy sumowane):
  a) krótka lista operatora z 10-03 — rożne UNDER: Chesterfield–Tranmere 11.5, Harrogate–Hornchurch 12.5,
     Almería–Burgos 11.5, Inter Toronto–Cavalry 11.5, Cuiabá–Ponte Preta 12.5 (drugi rząd: Cádiz–Leganés 11.5,
     Den Bosch–Dordrecht 13.5, Deportes Santa Cruz–San Marcos 12.5);
  b) nogi goals_1h_total UNDER z PDF (6 szt.) — czy pula 0.815 się potwierdziła;
  c) rynki zawodników (dopuszczone wszystkie 7) — ile weszło, jak wypadły.
- Wynik dnia to fakt, nie argument za decyzją.

## 2. Refity, które nie zobaczyły nocnego backfillu (63 tys. meczów tenisa ze statystykami)
- `scripts/sofa/fit_tennis_rating.py` → `config/tennis_rating.json` (dopasowany 09-30).
- `scripts/sofa/fit_tennis_tier_baselines.py` → `config/sofa_tennis_tier_baselines.json` (09-26).
- `scripts/sofa/measure_side_correlations.py` → `config/sofa_side_correlations.json` (≤10-01).
- Rób to jak refit: backup plików, wynik do katalogu roboczego, porównanie stare/nowe
  (Brier/log-loss poza próbą, jeśli skrypt to daje), dopiero potem podmiana; tests/sofa musi przejść.
  Zapisz w CLAUDE.md (sekcja „Refit epoch”), co i kiedy zmieniono.

## 3. Strażnik „zero, które znaczy brak danych” w SAMPLES
- 10-03 weryfikator: event 16494320 (Wealdstone–Halifax) zapisany jako rzuty rożne 0–0 przy
  rzutach wolnych 1/2 wobec 23 fauli i wślizgach 0/1 — zepsuty feed. 28 takich zer w próbkach 20 meczów
  dnia; 8 meczów zawetowano ręcznie (`runs/sofa/2026-10-03/vetoes.json`).
- Odrzucaj obserwację (z notatką/gap), gdy statystyka liczona jest 0 dla obu stron, a towarzyszące
  liczby są niemożliwe (np. rzuty wolne << faule przeciwnika). Zmierz, ile obserwacji odpada w całej
  historii, i sprawdź, czy prawdziwe 0–0 nie znikają. Test na kształcie 16494320.

## 4. Rozgrywki 851 (International Friendly Games) na listę towarzyskich
- Nie ma ich w liście towarzyskich (`config/sofa_friendly_competitions.json` / `FRIENDLY_COMPETITION_IDS`);
  mecze towarzyskie reprezentacji wchodzą do próbek i ratingu. Dodaj, zmierz wpływ (rating reprezentacji,
  pickle historii przebuduje się sam po zmianie klucza), test.

## 5. Krzywa goals_1h_total UNDER czyta ogólną pulę
- Rynek nie ma wierszy z odtworzenia cache (per-połowa tylko z live), kubełki < `MIN_MARKET_BUCKET=400`
  (`fit_confidence.py:59/254`) wypadają, a w dziurze 0.70–0.875 CONFIDENCE bierze `pooled:football`
  (0.8149/0.8408). Własne wiersze live: p .80–.825 n=230 realnie .813, ROI −8.1%; linia 1.5 przy kursie
  1.25–1.35 n=386 realnie .712, ROI −7.5%.
- Najpierw sprawdź, czy odtworzenie da się rozszerzyć na połowy (statystyki per okres są w cache).
  Jeśli nie — próg kubełka dla rynków bez odtworzenia (Wilson lower bound) zamiast puli. Zmierz na live.

## 6. Antyselekcja w krzywych (do zmierzenia, nie od razu do wdrożenia)
- Rożne UNDER drukowane przy p > market_p realizują ~4–5 pp poniżej krzywej (p .80–.85: 142/181=.785
  wobec 0.83–0.84). Krzywa jest średnią z wierszy bez ceny (replay), a kupon drukuje tylko te nad ceną.
- Zaproponuj wymiar „różnica do ceny” w krzywych albo korektę; zmierz poza próbą (leave-one-day-out).

## 7. Mecze pucharowe jako baza ratingu piłki
- `football_rating.league_rates` bierze średnią rozgrywek meczu; FA Cup / EFL Trophy (z akademiami U21)
  podnoszą gole słabszej strony (centre − drabina: liga +0.13, FA Cup +0.23, EFL Trophy +0.37).
- Propozycja z review: gdy rozgrywki nie są ligą żadnej ze stron — średnia lig obu stron z istniejącą
  różnicą siły, w `update()` i `centre()` razem, pomiar jeden krok naprzód; do tego czasu flaga jak
  CROSS_LEAGUE_UNLINKED.

## 8. Decyzje dla operatora (przedstaw dane, nie decyduj sam)
- WARIANT: tydzień 09-26..10-02 −94.06 j., ROI −4.4% [−7.7; −1.1] — strata poza szumem.
- Kupon HOKEJ: −18.2% [−38.5; −1.8]; reguła hokej −7.4%.
- Czy `refused_markets` rozszerzyć na połówki (shots_1h_for|UNDER itd.) — najpierw zmierz.

## 9. Porządki
- Usuń worktree `.claude/worktrees/agent-ac408ef72d9fdb491` (jego commit jest na main jako `3be5f8ae`).
- Nigdy `git checkout <rev> --` (10-03 na chwilę odłączyło HEAD na konfigurację sprzed refitu).

Potem normalny `/sofa-day dzisiaj`.
