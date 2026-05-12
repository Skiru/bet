---
name: bet-scanning-hockey
description: "Hockey-specific scanning — source URLs, adapter mappings, data quality requirements, timeouts, fallback chains, and validation rules."
user-invokable: false
---

# Scanning Hockey

## Source URLs

| URL | Domain | Role | Notes |
|-----|--------|------|-------|
| https://www.flashscore.com/hockey/ | flashscore.com | Fixtures | All hockey leagues |
| https://www.flashscore.com/hockey/usa/nhl/ | flashscore.com | Fixtures | NHL |
| https://www.flashscore.com/hockey/sweden/shl/ | flashscore.com | Fixtures | Swedish SHL |
| https://www.flashscore.com/hockey/finland/liiga/ | flashscore.com | Fixtures | Finnish Liiga |
| https://www.flashscore.com/hockey/czech-republic/extraliga/ | flashscore.com | Fixtures | Czech Extraliga |
| https://www.hockey-reference.com/ | hockey-reference.com | Stats | NHL schedule/stats |
| https://www.naturalstattrick.com/teamtable.php | naturalstattrick.com | Advanced Stats | **BLOCKED** — Cloudflare 403. Use MoneyPuck instead. |
| https://moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/teams.csv | moneypuck.com | Advanced Stats | **PRIMARY** xG%, Corsi%, Fenwick%, HDC — free CSV, no auth |
| https://www.dailyfaceoff.com/starting-goalies/ | dailyfaceoff.com | Goalie Confirmations | Starting goalie status (NHL) |
| https://www.betexplorer.com/hockey/ | betexplorer.com | Odds + Standings | Hockey odds, standings |
| https://www.covers.com/nhl/matchups | covers.com | Matchup Data | NHL matchup previews + consensus |
| https://www.betclic.pl/hokej-na-lodzie-s13 | betclic.pl | Execution | ⚠ Always 403 |
| https://www.oddsportal.com/hockey/ | oddsportal.com | Odds | Hockey odds |
| https://www.forebet.com/en/hockey/predictions-today | forebet.com | Predictions | Probabilities |
| https://scores24.live/en/ice-hockey | scores24.live | Deep | H2H + form |

## Adapter Mapping

| Domain | Adapter | Expected Output Fields |
|--------|---------|----------------------|
| flashscore.com | `flashscore_adapter` | home, away, time, league |
| hockey-reference.com | `hockey_reference_adapter` | schedule + box scores (shots, PIM, PP, hits, blocks, faceoffs, period scores) |
| naturalstattrick.com | `naturalstattrick_adapter` | stats (corsi_pct, fenwick_pct, xgf, xga, hdcf, hdca) — **BLOCKED by Cloudflare** |
| moneypuck.com | `moneypuck_adapter` | stats (xg_pct, corsi_pct, fenwick_pct, high_danger_shots_for, pdo, shooting_pct, save_pct + 30 more) — **PRIMARY** |
| dailyfaceoff.com | `dailyfaceoff_adapter` | goalie_home, goalie_away (name + status) |
| betexplorer.com | `betexplorer_adapter` | odds[] |
| oddsportal.com | `oddsportal_adapter` | odds_structured |
| scores24.live | `scores24_adapter` | H2H, form, trends |
| forebet.com | `forebet_adapter` | prediction probabilities |

## Data Quality Standards

- **Minimum events per day:** 10
- **Required stat keys:** shots, hits, blocks, pim, powerplay_goals, faceoff_pct
- **Should-have keys:** saves, save_pct, time_on_ice, giveaways, takeaways
- **Multi-source threshold:** ≥2 sources per event
- **Data freshness:** Same-day data only
- **Stats cache target:** ≥16 team files with ≥8 keys each

## Timeout Configuration

| Domain | Per-page Timeout | Delay Between Pages | Max Concurrent |
|--------|-----------------|--------------------:|---------------:|
| naturalstattrick.com | 30s | 2s | 1 |
| dailyfaceoff.com | 20s | 1s | 1 |
| flashscore.com | 30s | 1s | 3 |
| hockey-reference.com | 20s | 2s | 1 |
| oddsportal.com | 20s | 1s | 2 |
| scores24.live | 20s | 1s | 2 |
| forebet.com | 20s | 1s | 2 |

**Total scanner timeout:** 3 minutes

## Fallback Chains

**Market odds:**
1. SBR → 2. ESPN Odds → 3. ScoresAndOdds

**Statistical data:**
1. **MoneyPuck** (xG%, Corsi%, Fenwick%, HDC, PDO — free CSV, 37 stats/team) → 2. Hockey-Reference (box scores, PP%, PK%) → 3. DailyFaceoff (goalies)
   - NaturalStatTrick is **BLOCKED** by Cloudflare (403 on all methods). Do NOT attempt to scrape.

**Tipsters:**
1. PicksWise → 2. Sportsgambler → 3. OLBG

## Seasonal Considerations

- **NHL:** Oct-Jun (regular season Oct-Apr, playoffs Apr-Jun)
- **SHL/Liiga/Extraliga:** Sep-Apr
- **Off-season:** Jun-Sep (no major leagues active)
- **World Championship:** May (affects NHL players)
- **Olympics:** Feb (every 4 years, affects NHL schedule)

## Known Issues

- **Hockey-Reference:** Full box score support — schedule, per-period scores, shots, PIM, PP, hits, blocks, faceoffs.
- **NaturalStatTrick:** **BLOCKED** — Cloudflare "Under Attack" mode returns 403 on ALL methods. Adapter code exists but source is unreachable. Replaced by MoneyPuck.
- **MoneyPuck:** **PRIMARY** NHL advanced stats source. Free CSV API (no auth, no Cloudflare). Client: `api_clients/moneypuck_client.py`. Adapter: `adapters/moneypuck_adapter.py`. Integrated in `deep_stats_report.py` enrichment.
- **DailyFaceoff:** Goalie confirmations (critical for hockey betting). Manual check.
- **Covers:** NHL pages sometimes empty.
- **EU leagues:** Less data coverage than NHL. BetExplorer standings as fallback.

## API Enrichment

| Client | Free? | Keys Returned | Notes |
|--------|-------|---------------|-------|
| MoneyPuck | ✅ FREE | 37 per team | **PRIMARY** — xG%, Corsi%, Fenwick%, HDC, PDO, shooting%, save%. CSV API, 12h cache. |
| ESPN | ✅ FREE | 15+ per game | NHL game-level enrichment |
| API-Hockey | ❌ 100/day shared | goals, shots, hits, blocks, pim | Shared quota |

## Deep Data Requirements (v4 Pipeline)

For every scanned fixture, the scanner MUST attempt to collect:
1. H2H history (last 5 meetings minimum) with per-stat breakdowns
2. Recent form (last 10 matches) with opponents, results, scores  
3. League standings position and zone status
4. Key injuries/suspensions
5. Per-match statistical data (not just averages)

## Data Quality Validation

After scan completes, validate per fixture:
- Has ≥2 independent source confirmations?
- Has team form data for BOTH teams?
- Has at least 1 statistical data source (API or deep parse)?
- THINK IN THE MIDDLE: use sequentialthinking to evaluate scan quality
