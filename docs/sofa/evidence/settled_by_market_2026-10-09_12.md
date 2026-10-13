# Settled lines by market and direction, 2026-10-09..2026-10-12

Measured: RAW model p (not the calibrated confidence) >= 0.70, every offered rung, no coupon gates (margin, freshness, ODDS_TOO_LOW, reads). ROI per unit at the offered price; interval = 95% bootstrap over games/matches (800 draws, seed 20261013). Cells under n = 20 lines are left out. Each sport has its own table and is never pooled with another.

**Multiple comparisons: this report holds 125 table rows (6 sports). One row in twenty clears zero by chance alone (CLAUDE.md); the market and family views of one sport overlap and one game gives several lines. A row is a lead for a pre-registered check, never a rule.**

## football

108734 settled WIN/LOSS lines with a price, 1549 games (all p).

At p >= 0.70: n 22978, games 1514, hit 0.802, model 0.816, 1/odds 0.846, ROI -5.2% [-6.2, -4.2].

### football: market x direction

| market | direction | n | games | hit | model p | 1/odds | ROI | 95% ROI (games) |
|---|---|---|---|---|---|---|---|---|
| both_over_cards_points | OVER | 55 | 55 | 0.873 | 0.744 | 0.787 | +10.3% | [-0.6, +20.7] |
| handicap_corners | OVER | 30 | 27 | 0.633 | 0.753 | 0.589 | +7.0% | [-28.9, +38.9] |
| goal_kicks_for | UNDER | 20 | 20 | 0.600 | 0.775 | 0.561 | +5.9% | [-30.1, +41.6] |
| corners_2h_total | OVER | 105 | 58 | 0.905 | 0.826 | 0.866 | +4.7% | [-3.7, +12.2] |
| corners_for | OVER | 732 | 249 | 0.884 | 0.821 | 0.858 | +3.4% | [-0.0, +6.6] |
| corners_total | OVER | 804 | 348 | 0.869 | 0.824 | 0.845 | +3.1% | [-0.6, +6.9] |
| handicap_cards_points | OVER | 29 | 28 | 0.793 | 0.773 | 0.782 | +2.6% | [-18.2, +21.3] |
| both_over_shots_on_target | OVER | 140 | 126 | 0.836 | 0.812 | 0.815 | +2.3% | [-7.5, +10.7] |
| corners_2h_for | OVER | 90 | 52 | 0.900 | 0.843 | 0.885 | +1.7% | [-5.7, +7.7] |
| goals_1h_total | OVER | 371 | 371 | 0.809 | 0.741 | 0.798 | +1.7% | [-3.3, +6.5] |
| both_over_corners | OVER | 386 | 272 | 0.881 | 0.834 | 0.871 | +1.4% | [-3.7, +5.4] |
| saves_1h_total | OVER | 34 | 32 | 0.824 | 0.787 | 0.818 | +1.0% | [-15.9, +17.3] |
| shots_total | OVER | 193 | 90 | 0.762 | 0.766 | 0.761 | +0.7% | [-12.9, +12.9] |
| cards_points_for | OVER | 91 | 65 | 0.835 | 0.820 | 0.836 | -0.2% | [-9.1, +9.1] |
| corners_1h_total | OVER | 321 | 218 | 0.844 | 0.825 | 0.846 | -0.2% | [-6.0, +4.6] |
| cards_points_total | OVER | 130 | 102 | 0.838 | 0.794 | 0.841 | -0.4% | [-9.2, +7.2] |
| saves_for | OVER | 151 | 117 | 0.808 | 0.777 | 0.812 | -0.6% | [-9.2, +7.9] |
| corners_1h_for | OVER | 234 | 175 | 0.842 | 0.837 | 0.856 | -1.1% | [-6.5, +4.2] |
| shots_for | OVER | 183 | 85 | 0.765 | 0.774 | 0.773 | -1.1% | [-11.5, +9.1] |
| corners_1h_total | UNDER | 386 | 228 | 0.803 | 0.812 | 0.823 | -2.6% | [-9.0, +3.3] |
| goals_for | OVER | 894 | 644 | 0.808 | 0.765 | 0.829 | -2.6% | [-5.7, +0.3] |
| shots_on_target_total | OVER | 270 | 111 | 0.848 | 0.828 | 0.878 | -2.7% | [-9.8, +4.2] |
| goals_total | OVER | 1576 | 1225 | 0.850 | 0.824 | 0.879 | -3.4% | [-5.5, -1.3] |
| shots_on_target_for | OVER | 325 | 113 | 0.843 | 0.823 | 0.875 | -3.5% | [-9.0, +1.9] |
| goals_1h_for | UNDER | 701 | 363 | 0.857 | 0.861 | 0.886 | -3.5% | [-6.5, -0.2] |
| goals_2h_total | OVER | 785 | 784 | 0.806 | 0.786 | 0.842 | -4.0% | [-7.0, -0.9] |
| corners_for | UNDER | 975 | 240 | 0.807 | 0.820 | 0.844 | -4.4% | [-8.5, -0.6] |
| corners_total | UNDER | 955 | 357 | 0.781 | 0.822 | 0.820 | -4.8% | [-9.9, +0.7] |
| goals_1h_total | UNDER | 1208 | 857 | 0.825 | 0.844 | 0.870 | -5.3% | [-8.0, -2.7] |
| both_over_goals | UNDER | 507 | 507 | 0.785 | 0.833 | 0.825 | -5.4% | [-10.2, -1.0] |
| saves_for | UNDER | 145 | 98 | 0.724 | 0.781 | 0.758 | -5.4% | [-14.1, +4.3] |
| corners_1h_for | UNDER | 384 | 186 | 0.766 | 0.815 | 0.811 | -6.0% | [-12.4, +0.0] |
| goals_2h_total | UNDER | 1083 | 815 | 0.816 | 0.834 | 0.867 | -6.0% | [-9.0, -3.3] |
| goals_for | UNDER | 2053 | 849 | 0.821 | 0.836 | 0.872 | -6.0% | [-8.2, -3.9] |
| goals_2h_for | UNDER | 851 | 380 | 0.818 | 0.847 | 0.870 | -6.4% | [-10.1, -3.0] |
| shots_for | UNDER | 184 | 81 | 0.685 | 0.757 | 0.738 | -7.2% | [-21.2, +5.5] |
| goals_total | UNDER | 2063 | 1231 | 0.788 | 0.823 | 0.854 | -7.8% | [-10.4, -5.2] |
| both_over_shots | OVER | 125 | 68 | 0.656 | 0.793 | 0.718 | -8.7% | [-27.7, +10.2] |
| player_shots_on_target_for | OVER | 61 | 50 | 0.689 | 0.762 | 0.758 | -9.1% | [-26.6, +6.8] |
| cards_points_total | UNDER | 190 | 114 | 0.742 | 0.810 | 0.819 | -9.2% | [-19.2, +0.2] |
| player_offsides_for | OVER | 24 | 24 | 0.542 | 0.773 | 0.581 | -9.8% | [-44.0, +22.9] |
| shots_on_target_for | UNDER | 386 | 111 | 0.782 | 0.817 | 0.870 | -10.2% | [-16.8, -3.8] |
| saves_total | UNDER | 89 | 73 | 0.708 | 0.762 | 0.800 | -10.9% | [-26.0, +2.7] |
| saves_total | OVER | 90 | 78 | 0.733 | 0.764 | 0.828 | -11.5% | [-23.2, +1.1] |
| cards_points_for | UNDER | 86 | 61 | 0.686 | 0.771 | 0.773 | -11.7% | [-24.8, +0.6] |
| both_over_cards_points | UNDER | 87 | 78 | 0.736 | 0.831 | 0.807 | -11.8% | [-24.0, -0.4] |
| shots_on_target_total | UNDER | 266 | 112 | 0.744 | 0.808 | 0.867 | -13.8% | [-23.7, -4.9] |
| corners_2h_total | UNDER | 157 | 59 | 0.732 | 0.845 | 0.845 | -13.8% | [-25.6, -3.3] |
| corners_2h_for | UNDER | 171 | 57 | 0.719 | 0.814 | 0.825 | -14.0% | [-22.9, -5.1] |
| player_shots_for | OVER | 365 | 117 | 0.764 | 0.789 | 0.896 | -15.1% | [-19.9, -10.3] |
| shots_total | UNDER | 99 | 54 | 0.636 | 0.755 | 0.771 | -18.1% | [-34.7, -0.5] |
| both_over_goals | OVER | 95 | 95 | 0.547 | 0.761 | 0.675 | -18.6% | [-33.7, -3.0] |
| player_tackles_for | OVER | 435 | 43 | 0.720 | 0.800 | 0.884 | -19.4% | [-24.6, -14.5] |
| player_fouls_for | OVER | 533 | 74 | 0.657 | 0.788 | 0.836 | -21.2% | [-25.8, -16.5] |

### football: quantity family x direction

| family | direction | n | games | hit | model p | 1/odds | ROI | 95% ROI (games) |
|---|---|---|---|---|---|---|---|---|
| offsides | UNDER | 23 | 10 | 0.739 | 0.768 | 0.668 | +15.4% | [-21.0, +40.4] |
| cards_points | OVER | 84 | 59 | 0.845 | 0.754 | 0.785 | +7.7% | [-2.3, +17.3] |
| corners | OVER | 2729 | 377 | 0.868 | 0.825 | 0.851 | +2.2% | [-0.7, +4.9] |
| cards | OVER | 223 | 114 | 0.834 | 0.804 | 0.836 | -0.3% | [-8.1, +7.3] |
| shots | OVER | 1586 | 158 | 0.793 | 0.796 | 0.813 | -2.4% | [-8.1, +3.3] |
| goals | OVER | 3727 | 1268 | 0.819 | 0.792 | 0.846 | -3.2% | [-5.3, -1.1] |
| corners | UNDER | 3028 | 377 | 0.784 | 0.820 | 0.829 | -5.5% | [-9.5, -1.4] |
| goals | UNDER | 8466 | 1261 | 0.813 | 0.837 | 0.865 | -6.1% | [-8.0, -4.3] |
| cards | UNDER | 276 | 116 | 0.725 | 0.798 | 0.805 | -10.0% | [-19.4, -0.5] |
| shots | UNDER | 1239 | 143 | 0.727 | 0.790 | 0.811 | -10.2% | [-16.9, -3.6] |
| cards_points | UNDER | 87 | 78 | 0.736 | 0.831 | 0.807 | -11.8% | [-24.0, -0.4] |
| player_props | OVER | 1418 | 129 | 0.703 | 0.791 | 0.858 | -18.3% | [-21.2, -15.1] |
| fouls | UNDER | 40 | 18 | 0.425 | 0.751 | 0.582 | -27.3% | [-61.4, +3.5] |

## tennis

22237 settled WIN/LOSS lines with a price, 303 games (all p).

At p >= 0.70: n 4727, games 295, hit 0.761, model 0.810, 1/odds 0.806, ROI -6.1% [-8.2, -4.2].

### tennis: market x direction

| market | direction | n | games | hit | model p | 1/odds | ROI | 95% ROI (games) |
|---|---|---|---|---|---|---|---|---|
| games_total | OVER | 38 | 33 | 0.789 | 0.749 | 0.727 | +8.8% | [-12.3, +27.9] |
| most_games | OVER | 25 | 25 | 0.800 | 0.779 | 0.803 | +1.3% | [-21.3, +20.2] |
| games_won_set2_for | UNDER | 268 | 212 | 0.899 | 0.865 | 0.915 | -2.1% | [-6.3, +1.9] |
| handicap_games | OVER | 131 | 95 | 0.695 | 0.754 | 0.708 | -2.3% | [-14.2, +10.3] |
| games_set2_total | UNDER | 468 | 258 | 0.825 | 0.835 | 0.850 | -2.7% | [-7.8, +2.1] |
| games_won_for | OVER | 283 | 207 | 0.799 | 0.795 | 0.829 | -4.2% | [-10.2, +2.1] |
| games_won_set1_for | OVER | 595 | 212 | 0.701 | 0.783 | 0.726 | -4.5% | [-11.6, +2.0] |
| games_set1_total | OVER | 383 | 236 | 0.838 | 0.838 | 0.878 | -4.7% | [-9.7, +0.5] |
| games_set2_total | OVER | 409 | 241 | 0.834 | 0.836 | 0.886 | -5.8% | [-10.9, -1.1] |
| games_won_set1_for | UNDER | 250 | 194 | 0.864 | 0.854 | 0.917 | -5.9% | [-10.8, -1.1] |
| games_won_set2_for | OVER | 580 | 224 | 0.671 | 0.787 | 0.723 | -8.3% | [-14.9, -2.0] |
| games_set1_total | UNDER | 460 | 253 | 0.783 | 0.833 | 0.851 | -8.5% | [-14.1, -2.6] |
| tiebreaks_total | UNDER | 43 | 43 | 0.791 | 0.845 | 0.854 | -8.6% | [-23.1, +5.4] |
| games_won_for | UNDER | 447 | 269 | 0.700 | 0.773 | 0.774 | -10.0% | [-17.4, -2.8] |
| sets_total | UNDER | 124 | 124 | 0.661 | 0.772 | 0.736 | -10.2% | [-21.8, +1.9] |

### tennis: quantity family x direction

| family | direction | n | games | hit | model p | 1/odds | ROI | 95% ROI (games) |
|---|---|---|---|---|---|---|---|---|
| double_faults | UNDER | 24 | 10 | 0.792 | 0.773 | 0.743 | +7.7% | [-27.3, +34.1] |
| double_faults | OVER | 34 | 10 | 0.676 | 0.776 | 0.704 | -1.6% | [-36.3, +34.8] |
| games | OVER | 2444 | 281 | 0.751 | 0.801 | 0.787 | -5.2% | [-9.0, -1.8] |
| games | UNDER | 2067 | 294 | 0.791 | 0.823 | 0.843 | -6.6% | [-9.9, -3.3] |
| aces | OVER | 55 | 14 | 0.600 | 0.787 | 0.645 | -9.7% | [-33.7, +18.1] |
| aces | UNDER | 28 | 6 | 0.286 | 0.797 | 0.667 | -56.6% | [-74.6, -46.5] |

## hockey

15092 settled WIN/LOSS lines with a price, 400 games (all p).

At p >= 0.70: n 2496, games 351, hit 0.780, model 0.793, 1/odds 0.817, ROI -4.4% [-7.1, -1.8].

### hockey: market x direction

| market | direction | n | games | hit | model p | 1/odds | ROI | 95% ROI (games) |
|---|---|---|---|---|---|---|---|---|
| period_dnb | TEAM | 30 | 29 | 0.900 | 0.761 | 0.769 | +18.8% | [+3.2, +32.7] |
| result_1x2 | TEAM | 30 | 30 | 0.800 | 0.786 | 0.780 | +5.3% | [-14.9, +25.5] |
| total | UNDER | 135 | 114 | 0.785 | 0.761 | 0.767 | +2.2% | [-7.6, +11.6] |
| team_total | UNDER | 288 | 153 | 0.823 | 0.798 | 0.819 | +0.8% | [-5.2, +6.5] |
| period_total | UNDER | 224 | 202 | 0.804 | 0.771 | 0.818 | -1.7% | [-8.2, +4.4] |
| period_handicap | TEAM | 218 | 78 | 0.817 | 0.800 | 0.835 | -2.0% | [-7.9, +3.6] |
| total | OVER | 206 | 172 | 0.733 | 0.774 | 0.775 | -5.3% | [-14.2, +3.6] |
| team_total | OVER | 359 | 181 | 0.783 | 0.814 | 0.824 | -5.3% | [-11.2, +0.0] |
| period_team_total | UNDER | 400 | 172 | 0.800 | 0.803 | 0.845 | -5.4% | [-10.1, -0.8] |
| winner | TEAM | 86 | 86 | 0.733 | 0.768 | 0.787 | -6.4% | [-18.9, +5.5] |
| period_team_total | OVER | 42 | 30 | 0.667 | 0.737 | 0.746 | -10.5% | [-28.7, +8.7] |
| period_total | OVER | 260 | 228 | 0.765 | 0.819 | 0.857 | -10.7% | [-16.9, -4.6] |
| handicap | TEAM | 215 | 123 | 0.698 | 0.779 | 0.788 | -12.2% | [-21.2, -3.7] |

## basketball

24998 settled WIN/LOSS lines with a price, 469 games (all p).

At p >= 0.70: n 1309, games 290, hit 0.626, model 0.766, 1/odds 0.681, ROI -8.0% [-16.4, +2.1].

### basketball: market x direction

| market | direction | n | games | hit | model p | 1/odds | ROI | 95% ROI (games) |
|---|---|---|---|---|---|---|---|---|
| team_total | UNDER | 66 | 27 | 0.621 | 0.748 | 0.595 | +5.7% | [-21.9, +27.1] |
| total | UNDER | 259 | 73 | 0.680 | 0.776 | 0.669 | +2.9% | [-19.3, +24.0] |
| total | OVER | 240 | 66 | 0.654 | 0.764 | 0.668 | -2.5% | [-24.1, +18.9] |
| winner | TEAM | 149 | 149 | 0.812 | 0.787 | 0.850 | -4.3% | [-13.0, +3.5] |
| team_total | OVER | 74 | 29 | 0.568 | 0.745 | 0.594 | -4.4% | [-34.2, +26.8] |
| h1_dnb | TEAM | 26 | 26 | 0.769 | 0.777 | 0.827 | -6.6% | [-26.8, +12.6] |
| result_1x2 | TEAM | 55 | 55 | 0.745 | 0.790 | 0.832 | -9.9% | [-24.5, +4.8] |
| h1_1x2 | TEAM | 26 | 26 | 0.731 | 0.778 | 0.825 | -12.1% | [-32.0, +7.3] |
| h1_handicap | TEAM | 39 | 33 | 0.513 | 0.750 | 0.575 | -12.2% | [-42.2, +17.4] |
| h1_total | OVER | 50 | 24 | 0.440 | 0.771 | 0.575 | -23.2% | [-61.5, +22.8] |
| handicap | TEAM | 212 | 106 | 0.476 | 0.759 | 0.636 | -24.3% | [-41.9, -6.5] |
| h1_team_total | OVER | 43 | 19 | 0.419 | 0.742 | 0.609 | -32.0% | [-62.4, -2.8] |

## volleyball

4218 settled WIN/LOSS lines with a price, 176 games (all p).

At p >= 0.70: n 501, games 143, hit 0.685, model 0.802, 1/odds 0.739, ROI -8.9% [-18.4, +0.8].

### volleyball: market x direction

| market | direction | n | games | hit | model p | 1/odds | ROI | 95% ROI (games) |
|---|---|---|---|---|---|---|---|---|
| winner | TEAM | 103 | 103 | 0.825 | 0.848 | 0.835 | +0.1% | [-9.0, +10.6] |
| set_winner | TEAM | 148 | 64 | 0.723 | 0.788 | 0.761 | -5.5% | [-15.5, +4.3] |
| sets_total | UNDER | 59 | 59 | 0.729 | 0.766 | 0.782 | -7.5% | [-22.0, +6.3] |
| set_handicap | TEAM | 73 | 49 | 0.671 | 0.831 | 0.744 | -12.1% | [-28.9, +3.6] |
| points_handicap | TEAM | 60 | 33 | 0.467 | 0.789 | 0.560 | -17.3% | [-53.7, +20.0] |

## cs2

5002 settled WIN/LOSS lines with a price, 70 games (all p).

At p >= 0.70: n 426, games 40, hit 0.770, model 0.780, 1/odds 0.780, ROI -1.4% [-6.4, +4.4].

### cs2: market x direction

| market | direction | n | games | hit | model p | 1/odds | ROI | 95% ROI (games) |
|---|---|---|---|---|---|---|---|---|
| map_rounds_handicap | T1 | 73 | 10 | 0.904 | 0.814 | 0.840 | +7.8% | [-2.8, +15.5] |
| player_deaths | UNDER | 49 | 9 | 0.592 | 0.751 | 0.564 | +4.9% | [-12.3, +22.1] |
| map_rounds_total | OVER | 42 | 9 | 0.881 | 0.783 | 0.845 | +4.0% | [-9.5, +15.3] |
| map_rounds_total | UNDER | 38 | 8 | 0.895 | 0.827 | 0.865 | +3.3% | [-7.9, +15.8] |
| team_maps | OVER | 28 | 20 | 0.786 | 0.773 | 0.836 | -6.4% | [-23.5, +10.3] |
| map_rounds_handicap | T2 | 67 | 12 | 0.746 | 0.792 | 0.839 | -10.2% | [-26.2, +5.6] |
| map_team_rounds | OVER | 34 | 9 | 0.588 | 0.724 | 0.702 | -16.1% | [-45.9, +9.5] |
