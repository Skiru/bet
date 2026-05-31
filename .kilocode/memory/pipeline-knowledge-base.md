# Pipeline Knowledge Base

## Active Lessons (NEVER repeat these)

1. **NEVER manually filter/overwrite shortlist JSON** — build_shortlist.py handles ALL filtering
2. **S3 JSON key is `analyses`** (not `candidates` or `results`)
3. **Check DB state BEFORE rebuilding** — `SELECT COUNT(*) FROM analysis_results WHERE betting_date = ?` FIRST
4. **Enrichment writes to team_form ONLY** — downstream reads team_form only
5. **Dict Simplification = #1 data loss** — verify ALL downstream `.get()` fields exist in producer
6. **Reserve/Youth Team Contamination** — filter by excluded_competition_ids + team name regex
7. **Tipster key is `"tips"`** (NOT `"all_picks"`) — R18 mismatch caused 0-tip pipeline for days

## Data Funnel (typical numbers)

```
1200 scanned → 500 shortlisted → 300 fed to deep_stats → 150 analyzable → 30 gate-approved → 10-15 core picks
```

## Betclic Constraints (market availability)

- Hockey: Penalty Minutes NOT available
- **Corners, Fouls, Team Shots, Cards Total O/U: NOT AVAILABLE** (despite Statystyki tab)
- Available: Goals O/U, BTTS, Handicap, 1X2, DC, Player props, Red Card Y/N
- Basketball lines are LEAGUE-SPECIFIC (NBA ~220, NBB ~160, Women ~150)

## Safety Score Caps

| Pattern | Cap |
|---------|-----|
| One-sided data | 0.40 |
| Small sample (<8 games) | 0.50 |
| Synthetic source | 0.50 |
| safety ≥0.80 needs ≥10 L10 + H2H | evidence gate |

## Data Quality Traps

1. Synthetic data → cap 0.50 safety
2. Basketball line collision (team vs combined)
3. Market-matched EV (ML odds applied to corners = impossible)
4. DB status case → use `UPPER(status)` always
5. L5 wrong slice → `[:5]` = L5 (most-recent-first)
6. Dedup: `min(home,away)|max(home,away)|date`
