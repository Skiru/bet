# Stan pracy: kontekst terminarza piłka / tenis (plik stanu, aktualizowany po każdej fazie)

Plan: `docs/sofa/history/PLAN_KONTEKST_TERMINARZA_PILKA_TENIS_2026-11-08.md`; instrukcja:
`docs/sofa/evidence/kontekst_terminarza_2026-11-08/PROMPT_SESJI_WDROZENIOWEJ.md`;
pre-rejestracja: `docs/sofa/evidence/schedule_context_prereg_2026-11-09.md`.

## Faza bieżąca: F0 + F1 zrobione -> następny krok (d) 5 (rejestrator, próba 5 dni)

| faza | stan | SHA / hash / ścieżka |
|---|---|---|
| F0 pre-rejestracja + plan + materiały r1-r3 + tabela rodzin z kodu | commit | SHA w commicie "F0" (patrz `git log --grep "schedule context F0"`) |
| F1 `src/bet/sofa/schedule_features.py` + `tests/sofa/test_schedule_features.py` (11 testów) | w tym samym commicie (G1: moduł przed przebiegiem) | sha256 modułu - sekcja "Hashe" niżej |
| kopia bazy | gotowa / w toku | `data/refit_2026-11-08_schedule/sofa_copy.db` (VACUUM INTO z `file:data/sofa.db?mode=ro`, start 2026-11-09 ~00:00Z), log `vacuum.log` |
| F2 rejestrator (D4), próba 5 dni 2025-10-01..05, pełny przebieg | nie zaczęte | `data/refit_2026-11-08_schedule/` |
| F3-F8 | nie zaczęte | |

## Hashe
- (uzupełniane po commicie)

## Uwagi
- Bramki przy F0: `tests/sofa/test_player_sample_gates.py::test_off_the_gates_refuse_as_before` pada w drzewie
  roboczym, przechodzi na czystym HEAD e4fb587d (sprawdzone w osobnym worktree) - przyczyna w cudzych
  niezacommitowanych zmianach (`config/sofa_superbet_line_evidence.json`, slip builder), nie w ścieżkach tej pracy.
- Cudze niezacommitowane ścieżki przy starcie: `config/sofa_superbet_line_evidence.json`, `scripts/sofa/build_slip.py`,
  `src/bet/sofa/slip_builder.py`, `tests/sofa/test_slip_builder.py`, `config/sofa_settleability.2026-11-08.json`,
  `docs/sofa/evidence/ucl_kolejka_2026-11-03_04_kartki.md` - nigdy nie dodawane.

## Następny krok (dla kolejnej sesji)
1. Sprawdzić `vacuum.log` ("done"); jeśli brak - kopia niedokończona, powtórzyć VACUUM INTO.
2. Krok (d) 5: rejestrator wg D4 (`data/refit_2026-11-08_schedule/record.py`, wzór
   `data/refit_2026-11-05_replay/verify/run_window.py`), flagi z `data/refit_2026-11-05_replay/ftA/replay_rules.json`
   z `--form-table-per-family`; próba 2025-10-01..05, kontrola p do 1e-9.
