# F3 descriptives (explore only, ts < 2025-09-01 00:00Z)

Generated 2026-11-09 08:18Z by `desc/f3_desc.py`. Descriptive, not gates. Coefficients: estimate (SE); FE fits = `fb.fit_metric` (cluster SE by team).

## 1. Within-match contrast vs FE GLM

Contrast: OLS of dz = [log(y+.5) - log(centre)]_home - [..]_away on own-indicator differences (home - away), intercept, HC1 SE (one obs per match). Its slope estimates own - opp on a log(y+.5) scale; FE GLM columns are on the Poisson log scale.

| metric | col | contrast | matches | FE own | FE opp | FE own-opp |
|---|---|---|---|---|---|---|
| goals_for | R1 | -0.0007 (0.0082) | 281941 | -0.0060 (0.0047) | -0.0083 (0.0049) | +0.0024 |
| goals_for | R2 | +0.0071 (0.0060) | 281941 | -0.0043 (0.0035) | -0.0161 (0.0037) | +0.0118 |
| goals_for | cont_prev4 | -0.0274 (0.0239) | 281941 | -0.0777 (0.0283) | +0.0515 (0.0354) | -0.1293 |
| corners_for | R1 | +0.0188 (0.0335) | 10959 | +0.0057 (0.0135) | +0.0061 (0.0135) | -0.0004 |
| corners_for | R2 | -0.0323 (0.0215) | 10959 | -0.0154 (0.0084) | +0.0147 (0.0086) | -0.0301 |
| corners_for | cont_prev4 | +0.0100 (0.0628) | 10959 | -0.0782 (0.0449) | -0.0006 (0.0528) | -0.0776 |
| shots_for | R1 | +0.0288 (0.0243) | 9178 | +0.0234 (0.0099) | +0.0043 (0.0102) | +0.0191 |
| shots_for | R2 | -0.0252 (0.0158) | 9178 | -0.0044 (0.0064) | +0.0127 (0.0065) | -0.0171 |
| shots_for | cont_prev4 | +0.0103 (0.0493) | 9178 | -0.0878 (0.0286) | +0.0055 (0.0358) | -0.0932 |

|supremacy| tercile edges (explore goals_for matches): [0.3272698152861322, 0.7669698101709657]; coverage {'goals_for_matches': 335765, 'with_sup': 297840}

## 2. Strata (FE refit per stratum)

### goals_for

| stratum | rows | own_R1 | own_R2 | own_cont_prev4 | own_R5_other |
|---|---|---|---|---|---|
| all | 617707 | -0.0060 (0.0047) | -0.0043 (0.0035) | -0.0777 (0.0283) | -0.0523 (0.0066) |
| women | 34308 | +0.0083 (0.0203) | -0.0136 (0.0141) | -0.8568 (0.0188) | -0.1251 (0.0280) |
| men | 583399 | -0.0073 (0.0048) | -0.0036 (0.0036) | -0.0780 (0.0283) | -0.0466 (0.0068) |
| continental | 3569 | -0.0039 (0.0437) | -0.0164 (0.0280) | +0.5593 (0.0078) | -0.0097 (0.1729) |
| domestic | 614138 | -0.0061 (0.0047) | -0.0043 (0.0036) | -0.0750 (0.0284) | -0.0524 (0.0066) |
| sup_T1_low | 187207 | -0.0076 (0.0081) | +0.0009 (0.0061) | -0.0087 (0.0488) | -0.0384 (0.0115) |
| sup_T2_mid | 187647 | +0.0131 (0.0080) | +0.0091 (0.0059) | -0.1041 (0.0450) | -0.0174 (0.0111) |
| sup_T3_high | 188723 | -0.0193 (0.0069) | -0.0132 (0.0055) | -0.1110 (0.0400) | -0.0761 (0.0105) |
| sup_missing | 54130 | not fitted | not fitted | not fitted | not fitted |
| round_le3 | 118484 | +0.0040 (0.0078) | +0.0188 (0.0063) | -0.0659 (0.0523) | -0.0771 (0.0122) |
| round_gt3 | 499223 | -0.0088 (0.0054) | -0.0065 (0.0040) | -0.0728 (0.0307) | -0.0473 (0.0074) |

### corners_for

| stratum | rows | own_R1 | own_R2 | own_cont_prev4 | own_R5_other |
|---|---|---|---|---|---|
| all | 27174 | +0.0057 (0.0135) | -0.0154 (0.0084) | -0.0782 (0.0449) | -0.1877 (0.0561) |
| women | 640 | < 1000 | < 1000 | < 1000 | < 1000 |
| men | 26534 | +0.0058 (0.0137) | -0.0141 (0.0085) | -0.0777 (0.0449) | -0.1557 (0.0607) |
| continental | 1172 (<2000) | +0.0120 (0.0450) | +0.0399 (0.0302) | -0.0278 (0.0670) | -1.3775 (0.0000) |
| domestic | 26002 | +0.0087 (0.0141) | -0.0186 (0.0088) | -0.0623 (0.0452) | -0.1740 (0.0565) |
| sup_T1_low | 10031 | -0.0023 (0.0205) | -0.0254 (0.0133) | +0.1488 (0.0640) | -0.2875 (0.0759) |
| sup_T2_mid | 9639 | -0.0058 (0.0214) | -0.0052 (0.0124) | -0.2456 (0.0762) | -0.1380 (0.1015) |
| sup_T3_high | 6076 | +0.0616 (0.0209) | +0.0180 (0.0137) | -0.0544 (0.0657) | -0.2676 (0.0856) |
| sup_missing | 1428 | not fitted | not fitted | not fitted | not fitted |
| round_le3 | 3919 | -0.1234 (0.0238) | -0.0717 (0.0186) | -0.1993 (0.0804) | -0.0247 (0.1370) |
| round_gt3 | 23255 | +0.0152 (0.0153) | -0.0092 (0.0091) | -0.0649 (0.0483) | -0.1930 (0.0593) |

### shots_for

| stratum | rows | own_R1 | own_R2 | own_cont_prev4 | own_R5_other |
|---|---|---|---|---|---|
| all | 21626 | +0.0234 (0.0099) | -0.0044 (0.0064) | -0.0878 (0.0286) | -0.1060 (0.0406) |
| women | 572 | < 1000 | < 1000 | < 1000 | < 1000 |
| men | 21054 | +0.0259 (0.0100) | -0.0028 (0.0065) | -0.0880 (0.0286) | -0.0954 (0.0440) |
| continental | 1166 (<2000) | -0.0235 (0.0324) | -0.0323 (0.0223) | +0.0285 (0.0617) | -1.4733 (0.0000) |
| domestic | 20460 | +0.0269 (0.0103) | -0.0048 (0.0069) | -0.0806 (0.0290) | -0.1006 (0.0408) |
| sup_T1_low | 8591 | +0.0232 (0.0148) | -0.0179 (0.0097) | +0.0524 (0.0440) | -0.1321 (0.0528) |
| sup_T2_mid | 8138 | +0.0404 (0.0154) | -0.0052 (0.0096) | -0.1425 (0.0513) | -0.0592 (0.0519) |
| sup_T3_high | 4856 | +0.0217 (0.0151) | +0.0120 (0.0105) | -0.1519 (0.0344) | -0.1451 (0.0750) |
| sup_missing | 41 | not fitted | not fitted | not fitted | not fitted |
| round_le3 | 2428 | -0.0282 (0.0236) | -0.0015 (0.0173) | -0.1199 (0.0588) | -0.4752 (0.0450) |
| round_gt3 | 19198 | +0.0265 (0.0106) | -0.0048 (0.0068) | -0.0821 (0.0300) | -0.1046 (0.0431) |

## 3. Dispersion (FE fit)

| metric | n | df | Pearson chi2/df (Poisson) | mean recorded alpha | chi2/df with NB alpha |
|---|---|---|---|---|---|
| goals_for | 617707 | 549965 | 1.2123 | 0.1927 | 0.9292 |
| corners_for | 27174 | 22975 | 1.4584 | 0.1135 | 0.9613 |
| shots_for | 21626 | 19146 | 1.6538 | 0.0770 | 0.8822 |

Per own rest bucket, mean squared Pearson residual (no df correction; Poisson / NB):

- goals_for: R1 n 50729 1.050 / 0.814; R2 n 86511 1.051 / 0.839; R3 n 340302 1.114 / 0.856; R4 n 74454 1.088 / 0.839; R5 n 65711 0.952 / 0.658
- corners_for: R1 n 3158 1.260 / 0.814; R2 n 5964 1.242 / 0.813; R3 n 13327 1.253 / 0.830; R4 n 2399 1.297 / 0.854; R5 n 2326 0.996 / 0.671
- shots_for: R1 n 2780 1.468 / 0.752; R2 n 5102 1.478 / 0.771; R3 n 11016 1.444 / 0.789; R4 n 1958 1.519 / 0.811; R5 n 770 1.512 / 0.761

## 4. Halves (goals)

| col | goals_1h_for | goals_2h_for | naive z (1H-2H) |
|---|---|---|---|
| own_R1 | -0.0046 (0.0082) | +0.0052 (0.0073) | -0.89 |
| own_R2 | -0.0103 (0.0058) | -0.0015 (0.0053) | -1.10 |
| own_cont_prev4 | -0.0836 (0.0423) | -0.0668 (0.0348) | -0.31 |

Rows: goals_1h_for 399225, goals_2h_for 398442. The z treats the halves as independent (they share matches) - indicative only.

## Caveats (written by hand after the run; no new numbers)

- Strata cells with SE 0.0000 (continental own_R5_other in corners / shots) or extreme values (women goals
  own_cont_prev4, continental goals own_cont_prev4) are degenerate fits - very few exposed rows inside a
  stratum with team-season FE; not interpretable. Continental strata are < 2000 rows for corners / shots.
- sup_missing = rows whose event has no book-1 rating forecast with supremacy in full/dev/forecasts; not fitted.

## 5. Prediction-only vs +update (D3 iii)

Not computable from the recorded data. The recorded rows hold, per match, the prediction-time centres
(`final`, sample stats, phase multiplier, NB alpha) and the forecasts hold the rating's goal centres and
supremacy - no rating state (team attack / defence ratios, league rates, domain strengths). In "+update"
the term enters the expectation the rating learns from: `RatingBook.update` (src/bet/sofa/football_rating.py:1075)
computes each side's surprise against `base_h * ta.defence` / `base_a * th.defence` (lines ~1127-1140) and the
cross-domain residual against `exp` (~1152); multiplying those expectations by exp(t_home) / exp(t_away) changes
every later rating, hence every later centre. It would need: a second recording replay of
`calibrate_from_cache` (same flags as the recorded run, from 2024-07-01, both rating books incl. the form-table
book) with the frozen schedule term applied inside the update's expectation (features as of each match from
football_features), recording the rating centres again; then the same scoring on the new centres. Sample-based
centres (path i) are unaffected by the rating update except where the chain reads the rating (rating half /
supremacy). Not done; v1 adopts variant (a) per pre-registration 5.
