# Analysts' reads: value and cost, 2026-10-13 .. 2026-10-25 (13 days, all exist)

Read-only measurement. Scripts: `scratchpad/measure/grade_reads.py` (grades), `value.py`, `cost.py`, `rounds.py`.

## What was pooled, and the grade source

- Grades: `scripts/sofa/record_results.py` `graded_confidence()` (record_results.py:174-258) per day - the ledger's own grader (audit_settlement 7c); variant `official` = printed singles (football/tennis via `settle_audit`, measured sports via `coupon_sports.grade`), variant `removed:reads` = `11_coupon.json` `removed_by_reads` graded the same way. `13_results.json` holds only printed positions (`coupon_results.compute` skips `removed:reads`, coupon_results.py:158), so it cannot grade removed legs.
- Groups (singles only, builders excluded): **WATCH / NO_BET** = `removed:reads` with reason analyst / verifier (verdict from the leg's inline `reads`); **AUTO** = `removed:reads` reason `auto` (MODEL_ABOVE_OWN_SAMPLE, not a read; shown, not pooled with reads); **KEEP** = printed leg carrying a covering read (all KEEP); **UNREAD** = printed leg with no read.
- Pooled across all 13 days, all six sports, all epochs (10-13..10-25 spans several epoch groups - mixed days 10-16/10-17/10-18 and the 10-21 / 10-24 switches), locked and unlocked legs alike. Refunds/VOID = 0 u and excluded from hit rate. Stake 1u flat at the printed price.
- UNREAD is a different population (outside the 30 best-value matches) - compare it on hit-1/odds, not raw hit.
- Context tag: from `reads.json` entries with `context`, joined on (event, market, subject, line, direction).

## A. Value of the reads

### All sports pooled, 2026-10-13..10-25 (settled singles; refunds counted as 0 u, excluded from hit)

| group | n legs | matches | hit | mean 1/odds | hit-1/odds pp | mean conf | units | ROI |
|---|---|---|---|---|---|---|---|---|
| NO_BET | 32 | 13 | 0.581 | 0.810 | -23.0 | 0.794 | -9.3 | -29.0% |
| WATCH | 1072 | 325 | 0.745 | 0.768 | -2.4 | 0.781 | -33.5 | -3.1% |
| REMOVED? | 0 | | | | | | | |
| AUTO | 433 | 249 | 0.767 | 0.815 | -4.8 | 0.804 | -25.2 | -5.8% |
| KEEP | 9198 | 848 | 0.792 | 0.817 | -2.5 | 0.800 | -273.2 | -3.0% |
| UNREAD | 53912 | 6532 | 0.781 | 0.827 | -4.6 | 0.794 | -2991.7 | -5.5% |
| WATCH+NO_BET (read-removed) | 1104 | 331 | 0.740 | 0.770 | -3.0 | 0.781 | -42.8 | -3.9% |

### By sport: read-removed (WATCH+NO_BET) vs KEEP vs UNREAD

| group | n legs | matches | hit | mean 1/odds | hit-1/odds pp | mean conf | units | ROI |
|---|---|---|---|---|---|---|---|---|
| basketball REM | 22 | 11 | 0.455 | 0.629 | -17.5 | 0.723 | -5.9 | -26.7% |
| basketball KEEP | 60 | 35 | 0.667 | 0.644 | +2.3 | 0.721 | +2.3 | +3.8% |
| basketball UNREAD | 114 | 83 | 0.719 | 0.719 | +0.1 | 0.731 | +1.9 | +1.6% |
| cs2 REM | 0 | | | | | | | |
| cs2 KEEP | 62 | 15 | 0.877 | 0.739 | +13.8 | 0.763 | +10.8 | +17.5% |
| cs2 UNREAD | 393 | 80 | 0.781 | 0.806 | -2.5 | 0.767 | -11.6 | -2.9% |
| football REM | 932 | 238 | 0.757 | 0.776 | -1.9 | 0.784 | -21.0 | -2.2% |
| football KEEP | 7944 | 560 | 0.793 | 0.821 | -2.8 | 0.802 | -264.8 | -3.3% |
| football UNREAD | 46333 | 4594 | 0.778 | 0.827 | -4.9 | 0.795 | -2721.2 | -5.9% |
| hockey REM | 57 | 34 | 0.667 | 0.723 | -5.6 | 0.769 | -5.0 | -8.7% |
| hockey KEEP | 737 | 129 | 0.800 | 0.810 | -1.0 | 0.792 | -9.2 | -1.2% |
| hockey UNREAD | 3070 | 667 | 0.793 | 0.827 | -3.4 | 0.784 | -127.2 | -4.1% |
| tennis REM | 84 | 40 | 0.667 | 0.774 | -10.7 | 0.769 | -12.2 | -14.5% |
| tennis KEEP | 317 | 76 | 0.759 | 0.805 | -4.6 | 0.792 | -19.2 | -6.1% |
| tennis UNREAD | 3720 | 936 | 0.799 | 0.830 | -3.1 | 0.792 | -130.7 | -3.5% |
| volleyball REM | 9 | 8 | 0.778 | 0.682 | +9.5 | 0.762 | +1.2 | +13.3% |
| volleyball KEEP | 78 | 33 | 0.821 | 0.762 | +5.9 | 0.798 | +6.9 | +8.8% |
| volleyball UNREAD | 282 | 172 | 0.786 | 0.795 | -1.0 | 0.771 | -3.0 | -1.1% |

### By author of the removal

| group | n legs | matches | hit | mean 1/odds | hit-1/odds pp | mean conf | units | ROI |
|---|---|---|---|---|---|---|---|---|
| removed by analyst | 978 | 273 | 0.745 | 0.769 | -2.4 | 0.779 | -31.1 | -3.2% |
| removed by verifier | 126 | 70 | 0.698 | 0.773 | -7.5 | 0.792 | -11.7 | -9.2% |

### Read-removed by context tag (a leg with several tags counts in each)

| group | n legs | matches | hit | mean 1/odds | hit-1/odds pp | mean conf | units | ROI |
|---|---|---|---|---|---|---|---|---|
| (none) | 933 | 293 | 0.738 | 0.771 | -3.3 | 0.783 | -39.3 | -4.2% |
| SCHEDULE | 58 | 13 | 0.807 | 0.790 | +1.7 | 0.777 | +0.8 | +1.3% |
| ABSENCES | 48 | 21 | 0.617 | 0.713 | -9.6 | 0.752 | -7.0 | -14.6% |
| MOTIVATION | 28 | 10 | 0.714 | 0.776 | -6.2 | 0.796 | -1.9 | -6.7% |
| CONDITIONS | 13 | 7 | 0.636 | 0.706 | -6.9 | 0.743 | -0.8 | -5.8% |
| DERBY | 11 | 2 | 1.000 | 0.807 | +19.3 | 0.787 | +2.7 | +24.9% |
| ROTATION | 7 | 4 | 0.857 | 0.744 | +11.3 | 0.740 | +1.1 | +15.6% |
| MORALE | 6 | 4 | 1.000 | 0.796 | +20.4 | 0.794 | +1.6 | +26.0% |

### By day: read-removed vs KEEP

| group | n legs | matches | hit | mean 1/odds | hit-1/odds pp | mean conf | units | ROI |
|---|---|---|---|---|---|---|---|---|
| 2026-10-13 REM | 12 | 8 | 0.833 | 0.772 | +6.1 | 0.756 | +1.5 | +12.3% |
| 2026-10-13 KEEP | 319 | 44 | 0.824 | 0.832 | -0.8 | 0.800 | -3.8 | -1.2% |
| 2026-10-14 REM | 25 | 13 | 0.640 | 0.743 | -10.3 | 0.786 | -2.7 | -10.6% |
| 2026-10-14 KEEP | 366 | 45 | 0.769 | 0.808 | -3.9 | 0.798 | -17.5 | -4.8% |
| 2026-10-15 REM | 36 | 18 | 0.778 | 0.770 | +0.7 | 0.782 | +0.3 | +0.8% |
| 2026-10-15 KEEP | 516 | 42 | 0.817 | 0.819 | -0.2 | 0.803 | +0.4 | +0.1% |
| 2026-10-16 REM | 65 | 29 | 0.769 | 0.772 | -0.3 | 0.778 | -0.3 | -0.5% |
| 2026-10-16 KEEP | 412 | 54 | 0.830 | 0.813 | +1.7 | 0.799 | +9.0 | +2.2% |
| 2026-10-17 REM | 51 | 9 | 0.922 | 0.819 | +10.2 | 0.791 | +6.4 | +12.6% |
| 2026-10-17 KEEP | 1084 | 96 | 0.755 | 0.817 | -6.3 | 0.795 | -81.7 | -7.5% |
| 2026-10-18 REM | 5 | 5 | 0.800 | 0.767 | +3.3 | 0.754 | +0.2 | +4.6% |
| 2026-10-18 KEEP | 649 | 65 | 0.759 | 0.809 | -5.0 | 0.800 | -37.2 | -5.7% |
| 2026-10-19 REM | 38 | 20 | 0.892 | 0.773 | +11.9 | 0.771 | +5.8 | +15.2% |
| 2026-10-19 KEEP | 1057 | 95 | 0.817 | 0.817 | +0.1 | 0.798 | +2.0 | +0.2% |
| 2026-10-20 REM | 103 | 32 | 0.631 | 0.762 | -13.0 | 0.788 | -18.9 | -18.4% |
| 2026-10-20 KEEP | 595 | 53 | 0.815 | 0.814 | +0.1 | 0.801 | +3.1 | +0.5% |
| 2026-10-21 REM | 182 | 47 | 0.690 | 0.771 | -8.1 | 0.793 | -20.0 | -11.0% |
| 2026-10-21 KEEP | 690 | 61 | 0.799 | 0.823 | -2.4 | 0.803 | -21.7 | -3.1% |
| 2026-10-22 REM | 183 | 42 | 0.758 | 0.779 | -2.0 | 0.779 | -4.3 | -2.4% |
| 2026-10-22 KEEP | 921 | 60 | 0.776 | 0.825 | -4.9 | 0.804 | -53.7 | -5.8% |
| 2026-10-23 REM | 169 | 46 | 0.667 | 0.760 | -9.3 | 0.785 | -19.4 | -11.5% |
| 2026-10-23 KEEP | 829 | 77 | 0.815 | 0.809 | +0.7 | 0.795 | +11.2 | +1.4% |
| 2026-10-24 REM | 130 | 36 | 0.795 | 0.755 | +4.0 | 0.768 | +6.9 | +5.3% |
| 2026-10-24 KEEP | 677 | 75 | 0.772 | 0.818 | -4.6 | 0.805 | -40.3 | -6.0% |
| 2026-10-25 REM | 105 | 26 | 0.781 | 0.772 | +0.9 | 0.769 | +1.7 | +1.6% |
| 2026-10-25 KEEP | 1083 | 81 | 0.788 | 0.821 | -3.2 | 0.802 | -43.0 | -4.0% |

### Price bands: read-removed vs KEEP

| group | n legs | matches | hit | mean 1/odds | hit-1/odds pp | mean conf | units | ROI |
|---|---|---|---|---|---|---|---|---|
| 0-1.3 REM | 606 | 222 | 0.797 | 0.833 | -3.6 | 0.812 | -26.1 | -4.3% |
| 0-1.3 KEEP | 7102 | 726 | 0.819 | 0.848 | -2.9 | 0.817 | -235.9 | -3.3% |
| 1.3-1.6 REM | 459 | 233 | 0.682 | 0.704 | -2.2 | 0.744 | -14.5 | -3.2% |
| 1.3-1.6 KEEP | 2005 | 688 | 0.702 | 0.719 | -1.7 | 0.742 | -45.0 | -2.2% |
| 1.6-2.2 REM | 37 | 33 | 0.559 | 0.566 | -0.7 | 0.729 | -0.2 | -0.5% |
| 1.6-2.2 KEEP | 91 | 85 | 0.629 | 0.579 | +5.0 | 0.726 | +7.8 | +8.5% |
| 2.2-99 REM | 2 | 2 | 0.000 | 0.392 | -39.2 | 0.730 | -2.0 | -100.0% |
| 2.2-99 KEEP | 0 | | | | | | | |

### Match bootstrap (2000 resamples of (day, match)), removed minus KEEP

| scope | n removed / KEEP | ROI diff pp [95%] | (hit-1/odds) diff pp [95%] |
|---|---|---|---|
| all sports | 1104 / 9198 | -0.9 [-5.9, +4.2] | -0.4 [-4.2, +3.4] |
| football | 932 / 7944 | +1.1 [-4.0, +6.1] | +0.9 [-3.1, +4.9] |
| tennis | 84 / 317 | -8.4 [-28.4, +8.2] | -6.1 [-22.1, +6.4] |
| measured sports | 88 / 937 | -12.1 [-33.2, +11.5] | -7.7 [-21.8, +7.7] |

### Removals citing the web, and before / after the obligatory web pass (operator 2026-10-20)

| group | n | matches | hit | 1/odds | hit-1/odds pp | units | ROI |
|---|---|---|---|---|---|---|---|
| removal reason cites [WEB: | 218 | 90 | 0.706 | 0.759 | -5.3 | -14.8 | -6.8% |
| removal reason without web | 886 | 287 | 0.748 | 0.772 | -2.4 | -28.0 | -3.2% |
| removed 10-20..10-25 | 872 | 229 | 0.720 | 0.767 | -4.7 | -54.0 | -6.2% |
| removed 10-13..10-19 | 232 | 102 | 0.814 | 0.779 | +3.5 | +11.2 | +4.8% |
| KEEP 10-20..10-25 | 4795 | 407 | 0.793 | 0.818 | -2.6 | -144.4 | -3.0% |
| KEEP 10-13..10-19 | 4403 | 441 | 0.791 | 0.816 | -2.5 | -128.8 | -2.9% |

Match bootstrap removed minus KEEP: 10-20..10-25 ROI -3.2 pp [-9.2, +2.6], edge -2.2 [-6.6, +2.2]; 10-13..10-19 ROI +7.7 [-1.0, +15.8] (removed legs did *better* than kept); web-cited removals vs KEEP ROI -3.8 [-15.3, +7.5].

**Reading A.** Removed legs realise exactly as kept legs relative to their price: (hit-1/odds) -3.0 pp vs -2.5 pp; ROI diff -0.9 pp [-5.9, +4.2] over 1,104 vs 9,198 legs, 331 vs 848 matches. Raw hit is lower on removed legs (0.740 vs 0.792) only because analysts remove longer prices (1/odds 0.770 vs 0.817); within price bands the gap is <=1 pp in the two populated bands. No sport, author, period or context tag shows an interval excluding zero; NO_BET (n=32, 13 matches) and verifier (126) look better but are tiny. Removal saved units only by betting less (-42.8 u not staked), not by selecting (the removed legs lose at the coupon's own rate). Read legs (KEEP) do beat UNREAD on hit-1/odds (-2.5 vs -4.6 pp) but that is selection by read_value (top 30 by confidence x odds), not by the read.

## B. Redundancy / cost

### Per day (reads.json entries; exact key = event, market, subject, line, direction, period)

| day | reports | KB | rounds | per sport | read entries | distinct leg keys | re-read entries | re-reads repeating KEEP->KEEP | verdict changed | distinct matches | match-reads in >1 report |
| 2026-10-13 | 7 | 138 | 1 | {'cs2': 1, 'football': 2, 'hockey': 2, 'tennis': 2} | 625 | 598 | 27 (analyst-only 12) | 11 | 16 | 58 | 0 matches, 34 match-reports (0 extra) |
| 2026-10-14 | 5 | 108 | 1 | {'basketball': 1, 'football': 1, 'hockey': 1, 'tennis': 1, 'volleyball': 1} | 501 | 496 | 5 (analyst-only 0) | 0 | 5 | 65 | 0 matches, 22 match-reports (0 extra) |
| 2026-10-15 | 3 | 39 | 1 | {'football': 1, 'hockey': 1, 'volleyball': 1} | 653 | 645 | 8 (analyst-only 0) | 0 | 8 | 52 | 0 matches, 10 match-reports (0 extra) |
| 2026-10-16 | 5 | 195 | 1 | {'cs2': 1, 'football': 1, 'hockey': 1, 'tennis': 1, 'volleyball': 1} | 531 | 518 | 13 (analyst-only 0) | 0 | 13 | 61 | 0 matches, 56 match-reports (0 extra) |
| 2026-10-17 | 4 | 534 | 1 | {'basketball': 1, 'football': 1, 'hockey': 1, 'volleyball': 1} | 2105 | 2090 | 15 (analyst-only 0) | 0 | 15 | 163 | 0 matches, 158 match-reports (0 extra) |
| 2026-10-18 | 6 | 233 | 1 | {'basketball': 1, 'cs2': 1, 'football': 1, 'hockey': 1, 'tennis': 1, 'volleyball': 1} | 866 | 857 | 9 (analyst-only 5) | 5 | 4 | 84 | 5 matches, 70 match-reports (5 extra) |
| 2026-10-19 | 6 | 276 | 1 | {'basketball': 1, 'cs2': 1, 'football': 1, 'hockey': 1, 'tennis': 1, 'volleyball': 1} | 1162 | 1153 | 9 (analyst-only 2) | 2 | 7 | 100 | 0 matches, 51 match-reports (0 extra) |
| 2026-10-20 | 24 | 498 | 2 | {'basketball': 1, 'cs2': 5, 'football': 8, 'hockey': 3, 'tennis': 6, 'volleyball': 1} | 591 | 587 | 4 (analyst-only 0) | 0 | 4 | 71 | 9 matches, 84 match-reports (11 extra) |
| 2026-10-21 | 36 | 929 | 2 | {'basketball': 1, 'cs2': 3, 'football': 14, 'hockey': 11, 'tennis': 6, 'volleyball': 1} | 883 | 877 | 6 (analyst-only 0) | 0 | 6 | 86 | 22 matches, 112 match-reports (32 extra) |
| 2026-10-22 | 22 | 674 | 5 | {'basketball': 1, 'football': 11, 'hockey': 3, 'tennis': 7} | 557 | 553 | 4 (analyst-only 0) | 0 | 4 | 75 | 20 matches, 100 match-reports (27 extra) |
| 2026-10-23 | 13 | 677 | 2 | {'basketball': 2, 'football': 5, 'hockey': 4, 'tennis': 1, 'volleyball': 1} | 691 | 687 | 4 (analyst-only 0) | 0 | 4 | 80 | 3 matches, 88 match-reports (3 extra) |
| 2026-10-24 | 28 | 882 | 8 | {'basketball': 4, 'football': 12, 'hockey': 5, 'tennis': 1, 'volleyball': 6} | 992 | 980 | 12 (analyst-only 1) | 1 | 10 | 110 | 10 matches, 122 match-reports (12 extra) |
| 2026-10-25 | 45 | 1379 | 13 | {'basketball': 3, 'football': 28, 'hockey': 10, 'tennis': 2, 'volleyball': 2} | 1501 | 1484 | 17 (analyst-only 0) | 0 | 17 | 149 | 21 matches, 164 match-reports (27 extra) |
{'reports': 204, 'kb': 6562, 'entries': 11658, 'keys': 11525, 'rere': 133, 'rereA': 20, 'kk': 19, 'ch': 113, 'matches': 1154, 'mr': 1071, 'extra': 117, 'multi': 90}

Rounds = 1 + number of distinct `_rN` suffixes in report names. reads.json carries no timestamps; order = append order.

### Re-reads by report (reads blocks parsed with merge_reads.parse_report, reports ordered by mtime)

"Repeat match-appearance" = a match already present in an earlier report of the day. 7 early reports (10-13..10-15) failed to parse (older format) - single-round days, no effect on repeats.

| day | reports (by mtime) | match-appearances | repeat match-appearances | legs in repeat appearances | of which same family as an earlier-report KEEP (other line) | of which exact key already KEEP | of which new family | repeat-appearance verdicts WATCH/NO_BET |
| 2026-10-13 | 7 | 34 | 0 | 0 | 0 | 0 | 0 | 0 | parse_fail 4
| 2026-10-14 | 5 | 22 | 0 | 0 | 0 | 0 | 0 | 0 | parse_fail 2
| 2026-10-15 | 3 | 10 | 0 | 0 | 0 | 0 | 0 | 0 | parse_fail 1
| 2026-10-16 | 5 | 56 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-17 | 4 | 158 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-18 | 6 | 70 | 5 | 19 | 0 | 19 | 0 | 0 |
| 2026-10-19 | 6 | 51 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-20 | 24 | 84 | 11 | 11 | 1 | 7 | 3 | 1 |
| 2026-10-21 | 36 | 111 | 32 | 55 | 9 | 8 | 38 | 16 |
| 2026-10-22 | 22 | 100 | 27 | 40 | 1 | 11 | 28 | 10 |
| 2026-10-23 | 13 | 86 | 3 | 3 | 0 | 1 | 2 | 0 |
| 2026-10-24 | 28 | 122 | 12 | 16 | 4 | 1 | 11 | 4 |
| 2026-10-25 | 45 | 164 | 27 | 125 | 9 | 0 | 116 | 27 |
{'appear': 1068, 'parse_fail': 7, 'repeat': 117, 'rep_legs': 269, 'rep_exact': 47, 'rep_family': 24, 'rep_new': 198, 'rep_refuse': 58}

**Reading B.** 13 days: 204 reports, 6.4 MB, 11,658 read entries on 11,525 distinct leg keys and 1,154 distinct matches. Exact-key re-reads are rare: 133 entries (1.1%), only 20 by analysts; the rest are verifier reads over analyst reads (113 changed the verdict). Match level: 117 of 1,068 match-appearances (11%) were a match already read that day, carrying 269 legs: 47 exact keys already KEEP, 24 a new line of a family already KEEP, 198 a new family; 58 of the 269 came back WATCH/NO_BET. So skipping already-KEEP legs unless something changed would save at most ~71 leg reads (0.6% of entries) and, if whole repeat matches were skipped, ~11% of match-reads (dossier + web pass redone). The cost is volume, not repetition: 500-2,100 entries a day, rising rounds (10-24: 8, 10-25: 13 rounds / 45 reports / 1.35 MB) because each rebuild brings new matches into the top 30, not because old legs are re-read.

## C. Web pass yield

| day | KEEP reasons | KEEP with "nic istotnego" | KEEP citing [WEB: | WATCH/NO_BET citing [WEB: |
|---|---|---|---|---|
| 10-13..10-19 | 5,888 | 0 | 317 (5%) | 18 / 555 |
| 10-20 | 429 | 0 | 11 (3%) | 12/162 |
| 10-21 | 641 | 13 (2%) | 576 (90%) | 50/242 |
| 10-22 | 349 | 54 (15%) | 244 (70%) | 65/208 |
| 10-23 | 514 | 79 (15%) | 368 (72%) | 36/177 |
| 10-24 | 761 | 155 (20%) | 314 (41%) | 84/231 |
| 10-25 | 1,123 | 153 (14%) | 290 (26%) | 100/378 |
| total | 9,705 | 454 (4.7%; 14% of 10-21..10-25 KEEPs, 454/3,388) | 2,120 | 365/1,953 (19%) |

Per match section (`### ` sections of reports 10-20..10-25, 623 sections): "nic istotnego" in 195 (31%), "bez wpływu" 94 (15%), "nie do zweryfikowania" 105 (17%), no [WEB: tag at all 85 (14%), weather (open-meteo) as the only domain 38 (6%). [WEB: tags per match section: mean 2.5, median 2; distinct domains per match mean 2.0, median 2 (0: 85, 1: 148, 2: 196, 3: 118, 4+: 76). Counting the tags inside the JSON reasons too, 10-21..10-25 reports carry 5.4-12.3 tags per match (repeated per leg). Web-cited removals graded: 218 legs, hit-1/odds -5.3 pp vs KEEP -2.5, ROI diff -3.8 pp [-15.3, +7.5] - no measurable value.

## D. `read_set.py --unread`

- scripts/sofa/read_set.py:146-152: with `--unread` a leg is skipped when `analyst_read(leg, reads)` is true.
- scripts/sofa/read_set.py:117-131: `analyst_read` = any covering read in reads.json **by author "analyst"** (or carried inline on the leg) under `veto.matching_reads` - exact (event, market, subject, line, direction, period) (src/bet/sofa/veto.py:59-70; a None field covers all).
- So a leg already read (KEEP or not) is NOT re-included when positions change, whatever its price, confidence or lineup did; nothing re-reads on a price/line move. A leg is re-included only when its key is new - typically a new line (ladder rung) or market of a match already read - or when its only read is the verifier's (verifier reads do not count, :130). Its match then goes back to an analyst, who redoes dossier + web for that match (the 11% repeat match-appearances above).
- merge_reads.py:33-35: reads are appended, never edited; WATCH/NO_BET win over KEEP.
