# Step 25 - centre tables under the schedule term (2026-11-09)

The corrected forecast exists only inside `run_sheet.schedule_term_rows` (`scripts/sofa/run_sheet.py:1970`, built
`:1999`, used only for markets in `SCHEDULE_TERM_MARKETS`, `:1989-1995`); callers: the five path (ii) pricers - double
chance `:2803`, 1X2 / DNB `:2819`, score markets `:2834`, first goal `:2849`, simulator `:2880`. The wrapper changes
only `centre("goals_for", side)` (`src/bet/sofa/schedule_term.py:315-322`); supremacy and cards pass through
uncorrected (`:324-325`). Line numbers are of the uncommitted working tree of 2026-11-09.

| table | touched? (evidence) | measurement | verdict |
|---|---|---|---|
| rating weight | no - `sample_centre` blend on the uncorrected forecast (`run_sheet.py:1172-1185`) | none needed | keep |
| game state | no - uncorrected supremacy (`centre_chain.py:102-103`, `run_sheet.py:2048-2049`), count rows | none needed | keep |
| goals stretch | no - sample goals rows (`centre_chain.py:172-179`) | none needed | keep |
| count / player / closeness stretch | no (`centre_chain.py:114-121`, `:160-161`, `run_sheet.py:3181-3184`) | none needed | keep |
| season phase | no - sample goals rows (`centre_chain.py:194-210`, `run_sheet.py:3195`); path (ii) reads the phase label only | none needed | keep |
| referee | no - cards / fouls rows (`run_sheet.py:2712-2717`, `:2037`) | none needed | keep |
| count dispersion | no - count rows (`run_sheet.py:3257-3260`) | none needed | keep |
| `nb_r` 7.586 (`sofa_football_result.json`) | yes - `result_probs(lh e^t, la e^t, nb_r)` | `measure_nb_r.py` on recorder outputs: dev 453,677 / exam 287,962 matches; argmax r same with / without the term (goals 7 / 6, 1X2 100 / 15); r picked on dev scored on exam vs 7.586: goals +0.00038 [+0.00031, +0.00045] corrected vs +0.00039 uncorrected, 1X2 -0.00014 [-0.00034, +0.00004] vs -0.00008; at 7.586 corrected better: goals +0.00045 [+0.00033, +0.00056], 1X2 +0.00022 [+0.00016, +0.00029] | keep |
| simulator frailty 0.03 | yes (simulator keys) | goals at r 33.3 on the exam window: corrected - uncorrected +0.00056 [+0.00042, +0.00069] | keep; minute-profile / state constants not tested |

Gains: mean log-likelihood per match (positive = better), 95% match bootstrap.
