# Pipeline Knowledge Base (Kilo Code Migration)

## Critical Bugs — ALL FIXED

| Bug | Root Cause | Fix |
|-----|------------|-----|
| Playwright in ThreadPool | greenlet crash | Sequential main-thread (`--deep-workers 1`) |
| Thread guards skip Playwright | 89% teams empty | Phase 2 main-thread retry |
| FIXTURE_ONLY scored 75 | Same as STATS_ONLY | Score 0 + ×0.5 multiplier |
| `--top 200` picks dateless first | Sort by data_tier before `--top` |
| Exact string match team names | "Montréal" ≠ "Montreal" | `normalize_team_name()` + fuzzy fallback |
| DB persistence wrong columns | JOIN through sports/teams tables |
| COIN_FLIP rejects 50% | Threshold `<= 0.50` → `< 0.50` |
| TBD fixtures pass through | Added explicit TBD/TBA filter |
| Date query used `fetched_at` | Changed to `date(f.kickoff) = ?` |
| Totals odds never persisted | Added totals handling with `hdp` field |
| Quality floor drops 625/741 | `--all-fixtures` flag bypasses caps |
| `_min_stat=5` drops 3-4 entries | Lowered to 3 for ALL sports |
| TeamRepo.resolve wrong ID | `fixture_id` passthrough to actual IDs |

## Critical Lessons — NEVER REPEAT

1. **NEVER manually filter/overwrite shortlist JSON** — build_shortlist.py handles ALL filtering
2. **S3 JSON key is `analyses`** (not `candidates` or `results`)
3. **Check DB state BEFORE rebuilding** — `SELECT COUNT(*) FROM analysis_results WHERE betting_date = ?` FIRST
4. **Playwright enrichment always fails in threads** — use bulk enrichment scripts
5. **Enrichment writes to team_form ONLY** — downstream reads team_form only
6. **Dict Simplification = #1 data loss** — verify ALL downstream `.get()` fields exist in producer
7. **Reserve/Youth Team Contamination** — filter by excluded_competition_ids + team name regex

## Data Funnel (typical numbers)

```
1200 scanned → 500 shortlisted → 300 fed to deep_stats → 150 analyzable → 30 gate-approved → 10-15 core picks
```

## Enrichment Architecture

### Fallback Chains
- Tennis: tennis-abstract → sackmann → espn-tennis → google-sports
- Basketball/Football/Hockey: Flashscore → API-Sport → ESPN → SerpAPI
- DB team_form is PRIMARY stat store

### Key Limitations
- SofaScore: 100% 403 blocked
- d.flashscore.com API: requires dynamic x-fsign auth — NOT usable
- ESPN: no soccer gamelogs, no esports
- Betclic: NEVER scrape (always 403)
- API-Basketball/Football: can't resolve minor league teams

## Betclic Constraints

- Hockey: Penalty Minutes NOT available
- **Corners, Fouls, Team Shots, Cards Total O/U: NOT AVAILABLE** (despite Statystyki tab)
- Available: Goals O/U, BTTS, Handicap, 1X2, DC, Player props, Red Card Y/N
- Basketball lines are LEAGUE-SPECIFIC (NBA ~220, NBB ~160, Women ~150)

## Safety Score Patterns

| Pattern | Rule | Cap |
|---------|------|-----|
| H | One-sided data | hard cap 0.40 |
| I | Small sample (<8 games) | hard cap 0.50 |
| G | safety ≥0.80 needs ≥10 L10 + H2H | evidence gate |

## Data Quality Traps

1. Synthetic data → cap 0.50 safety
2. Cache key mismatches (corners_home vs corners)
3. Basketball line collision (team vs combined)
4. Market-matched EV (ML odds applied to corners = impossible)
5. JSON overwrite between steps → DB fallback
6. DB status case → use `UPPER(status)` always
7. L5 wrong slice → `[:5]` = L5 (most-recent-first)
8. Dedup: `min(home,away)|max(home,away)|date`

## Script Monitoring Pattern

```
1. LAUNCH: run_in_terminal, async for >120s scripts
2. MONITOR: check output periodically
3. SUMMARIZE: current activity, errors, progress
4. ON ERROR: STOP and diagnose immediately
5. COMPLETION: When AGENT_SUMMARY seen or shell prompt returns
6. VALIDATE: verify output files/DB entries exist
```
