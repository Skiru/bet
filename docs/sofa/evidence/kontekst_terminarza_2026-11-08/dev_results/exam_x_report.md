# Exam X report (outcome-free) - r3 step 8

Generated 2026-11-09 08:17Z by `desc/exam_x_report.py`. No outcome store opened.

## 1. Football exam rows (2026-01..10, non-national, coverage both sides)

`goals`: full/exam/rows goals_for / goals_1h_for / goals_2h_for at `fb.book_for`; `football_result`: full/exam/forecasts rating book 1, 2 rows a match (goals_for centre of each side). Share = rows with the OWN column = 1.

Dropped rows: {'goals:no coverage': 55930, 'goals:national': 15125, 'goals:no features': 2, 'goals:outside exam': 10133, 'result:no coverage': 9418, 'result:national': 1998, 'result:no features': 1}

### goals

| col | 2026-01 | 2026-02 | 2026-03 | 2026-04 | 2026-05 | 2026-06 | 2026-07 | 2026-08 | 2026-09 | 2026-10 | all |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rows | 100962 | 120995 | 169862 | 181177 | 169805 | 61029 | 67844 | 151829 | 173273 | 121693 | 1318469 |
| R1 | 8.27% | 7.42% | 8.50% | 9.35% | 8.45% | 9.45% | 6.60% | 11.64% | 12.09% | 9.93% | 9.40% |
| R2 | 12.42% | 13.32% | 13.89% | 18.01% | 16.21% | 16.64% | 10.71% | 16.58% | 19.01% | 15.86% | 15.72% |
| R3 | 41.54% | 50.31% | 60.05% | 51.99% | 63.01% | 49.99% | 27.97% | 44.20% | 57.23% | 55.48% | 52.28% |
| R4_intl | 0.00% | 0.00% | 6.32% | 13.55% | 0.17% | 11.19% | 0.00% | 0.00% | 1.71% | 6.92% | 4.08% |
| R4_other | 13.94% | 10.82% | 3.19% | 2.30% | 10.25% | 5.84% | 8.60% | 7.83% | 6.29% | 5.74% | 7.08% |
| R5_season_start | 12.13% | 10.57% | 1.24% | 0.49% | 0.18% | 4.04% | 40.42% | 17.85% | 2.61% | 0.43% | 6.85% |
| R5_winter | 10.55% | 5.29% | 4.15% | 0.02% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 1.83% |
| R5_other | 1.16% | 2.27% | 2.66% | 4.29% | 1.73% | 2.85% | 5.71% | 1.91% | 1.05% | 5.63% | 2.76% |
| cont_prev4 | 0.22% | 0.44% | 0.33% | 0.24% | 0.33% | 0.01% | 0.52% | 0.74% | 0.19% | 0.64% | 0.37% |
| cont_prev4_x_R1 | 0.16% | 0.28% | 0.22% | 0.14% | 0.18% | 0.00% | 0.42% | 0.52% | 0.09% | 0.41% | 0.24% |
| et_prev | 0.58% | 0.51% | 0.49% | 0.50% | 0.62% | 0.57% | 0.66% | 0.87% | 0.66% | 0.67% | 0.61% |
| dense14 | 1.59% | 1.84% | 2.44% | 2.20% | 1.98% | 2.44% | 1.21% | 2.04% | 3.14% | 2.89% | 2.25% |
| cont_next4 | 0.13% | 0.19% | 0.09% | 0.21% | 0.17% | 0.00% | 0.31% | 0.18% | 0.10% | 0.37% | 0.17% |

Exposed rows (own col = 1), goals, all months: R1 123991, R2 207245, R3 689284, R4_intl 53779, R4_other 93335, R5_season_start 90336, R5_winter 24145, R5_other 36354, cont_prev4 4901, cont_prev4_x_R1 3174, et_prev 8064, dense14 29700, cont_next4 2297

### football_result

| col | 2026-01 | 2026-02 | 2026-03 | 2026-04 | 2026-05 | 2026-06 | 2026-07 | 2026-08 | 2026-09 | 2026-10 | all |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rows | 38480 | 46286 | 76716 | 82252 | 80436 | 28152 | 17740 | 59240 | 77868 | 49950 | 557120 |
| R1 | 8.26% | 7.34% | 7.85% | 8.88% | 7.93% | 9.32% | 9.83% | 11.89% | 11.66% | 9.10% | 9.21% |
| R2 | 11.84% | 12.91% | 11.83% | 16.32% | 14.14% | 15.87% | 15.47% | 16.69% | 17.46% | 14.46% | 14.78% |
| R3 | 47.29% | 56.13% | 61.32% | 52.87% | 63.43% | 53.42% | 41.80% | 46.41% | 58.59% | 58.20% | 55.71% |
| R4_intl | 0.00% | 0.00% | 6.34% | 14.17% | 0.18% | 11.42% | 0.00% | 0.00% | 1.86% | 6.55% | 4.41% |
| R4_other | 14.85% | 12.48% | 3.36% | 2.19% | 11.30% | 6.02% | 13.16% | 8.48% | 6.54% | 5.69% | 7.53% |
| R5_season_start | 1.83% | 1.33% | 0.67% | 0.47% | 0.20% | 0.37% | 9.61% | 14.05% | 2.72% | 0.45% | 2.67% |
| R5_winter | 14.45% | 6.43% | 5.32% | 0.04% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 2.27% |
| R5_other | 1.48% | 3.38% | 3.31% | 5.06% | 2.82% | 3.58% | 10.14% | 2.48% | 1.16% | 5.54% | 3.42% |
| cont_prev4 | 0.19% | 0.38% | 0.24% | 0.18% | 0.23% | 0.01% | 0.61% | 0.63% | 0.14% | 0.52% | 0.29% |
| cont_prev4_x_R1 | 0.13% | 0.24% | 0.16% | 0.10% | 0.13% | 0.00% | 0.48% | 0.45% | 0.07% | 0.33% | 0.19% |
| et_prev | 0.53% | 0.48% | 0.41% | 0.41% | 0.50% | 0.47% | 0.85% | 0.83% | 0.64% | 0.65% | 0.55% |
| dense14 | 1.51% | 1.78% | 2.19% | 2.19% | 1.83% | 2.24% | 1.82% | 2.20% | 2.78% | 2.68% | 2.17% |
| cont_next4 | 0.11% | 0.16% | 0.07% | 0.15% | 0.12% | 0.00% | 0.38% | 0.15% | 0.07% | 0.30% | 0.14% |

Exposed rows (own col = 1), football_result, all months: R1 51311, R2 82323, R3 310375, R4_intl 24596, R4_other 41951, R5_season_start 14860, R5_winter 12651, R5_other 19053, cont_prev4 1616, cont_prev4_x_R1 1041, et_prev 3071, dense14 12116, cont_next4 759

Per goals metric (rows / exposed own): 
- goals_for: rows 572215; R1 50690, R2 81305, R3 305996, R4_intl 24407, R4_other 41671, R5_season_start 38775, R5_winter 12003, R5_other 17368, cont_prev4 1639, cont_prev4_x_R1 1062, et_prev 3094, dense14 11912, cont_next4 767
- goals_1h_for: rows 372193; R1 36596, R2 62859, R3 191183, R4_intl 14645, R4_other 25755, R5_season_start 25652, R5_winter 6046, R5_other 9457, cont_prev4 1630, cont_prev4_x_R1 1056, et_prev 2486, dense14 8885, cont_next4 764
- goals_2h_for: rows 374061; R1 36705, R2 63081, R3 192105, R4_intl 14727, R4_other 25909, R5_season_start 25909, R5_winter 6096, R5_other 9529, cont_prev4 1632, cont_prev4_x_R1 1056, et_prev 2484, dense14 8903, cont_next4 766

### Tennis exam X (tw_exam_X.pkl, best of three; max over the two players)

| tier | matches | coverage | games78>=3 | layoff21 | ret14 | among covered: games78>=3 | layoff21 | ret14 |
|---|---|---|---|---|---|---|---|---|
| CH | 12139 | 98.80% | 43.14% | 11.04% | 2.22% | 43.59% | 10.96% | 2.23% |
| ITF | 53841 | 96.04% | 48.23% | 14.65% | 2.02% | 49.82% | 14.16% | 2.04% |
| TOUR | 7130 | 99.14% | 37.69% | 12.58% | 2.17% | 37.94% | 12.58% | 2.18% |
| all | 73110 | 96.80% | 46.36% | 13.85% | 2.07% | 47.58% | 13.46% | 2.09% |

## 2. Live vs replay exposure (2026-10-02..2026-10-31)

Missing days: none. Live football fixtures in 03_samples: 13686 (READY 11241); with features 12883; without 803.

No-feature reasons: {'status postponed in DB copy': 187, 'status inprogress in DB copy': 30, 'status interrupted in DB copy': 4, 'not in sofa_listed_event (DB copy)': 463, 'status notstarted in DB copy': 8, 'friendly competition + not in sofa_listed_event (DB copy)': 8, 'national (02_fixtures) + status inprogress in DB copy': 3, 'national (02_fixtures) + not in sofa_listed_event (DB copy)': 69, 'national (02_fixtures) + friendly competition + not in sofa_listed_event (DB copy)': 13, 'status canceled in DB copy': 11, 'unexplained': 5, 'national (02_fixtures) + friendly competition + status inprogress in DB copy': 1, 'status willcontinue in DB copy': 1}

Of those with features: national 122, friendly 91, non-national without coverage of both sides 59.

Compared (non-national, both covered): live 12702 matches, replay 25127 matches (exam goals_for rows, same UTC days); live matches also in the replay set: 12540. Shares are per side (2 per match).

| bucket | live sides | live | replay sides | replay | diff pp | live SE pp (naive) | > 3 pp |
|---|---|---|---|---|---|---|---|
| R1 | 2428 | 9.56% | 4551 | 9.06% | +0.50 | 0.18 |  |
| R2 | 4267 | 16.80% | 7036 | 14.00% | +2.80 | 0.23 |  |
| R3 | 14430 | 56.80% | 28946 | 57.60% | -0.80 | 0.31 |  |
| R4_intl | 1366 | 5.38% | 3649 | 7.26% | -1.88 | 0.14 |  |
| R4_other | 1439 | 5.66% | 2900 | 5.77% | -0.11 | 0.15 |  |
| R5_season_start | 75 | 0.30% | 247 | 0.49% | -0.20 | 0.03 |  |
| R5_winter | 0 | 0.00% | 0 | 0.00% | +0.00 | 0.00 |  |
| R5_other | 1399 | 5.51% | 2925 | 5.82% | -0.31 | 0.14 |  |
| cont_prev4 | 253 | 1.00% | 261 | 0.52% | +0.48 | 0.06 |  |
| cont_prev4_x_R1 | 162 | 0.64% | 167 | 0.33% | +0.31 | 0.05 |  |
| et_prev | 183 | 0.72% | 323 | 0.64% | +0.08 | 0.05 |  |
| dense14 | 504 | 1.98% | 1296 | 2.58% | -0.59 | 0.09 |  |
| cont_next4 | 148 | 0.58% | 150 | 0.30% | +0.28 | 0.05 |  |

Buckets over the 3 pp tolerance: none. The naive SE ignores clustering of the two sides of one match.
