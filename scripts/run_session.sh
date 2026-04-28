#!/usr/bin/env bash
set -euo pipefail

# ==================================================================
# PHASE A — DATA HARVEST (Enhanced v2)
# Single command that runs ALL automated data gathering.
# After this completes, invoke the orchestrator prompt for Phase B.
#
# Sources: 14 sports × Tier A stats + Tier A markets + Tier B tipsters
#          + Tier C specialists + US-sport odds (SBR/ESPN/ScoresAndOdds)
#          + H2H/historical data sources
#
# Usage:
#   bash scripts/run_session.sh                    # settle yesterday + scan today
#   bash scripts/run_session.sh --date 2026-04-27  # explicit date
#   bash scripts/run_session.sh --skip-settle       # skip settlement (already done)
#   bash scripts/run_session.sh --session night     # night session (scan still runs all)
#   bash scripts/run_session.sh --verbose           # full output (no tail truncation)
# ==================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/.."
DATA_DIR="${ROOT_DIR}/betting/data"
VENV_DIR="${ROOT_DIR}/.venv"

# Defaults
RUN_DATE=$(date '+%Y-%m-%d')
SESSION="full"
SKIP_SETTLE=false
VERBOSE=true  # default verbose — use --quiet to suppress

# Counters for final summary
FETCH_OK=0
FETCH_FAIL=0
FETCH_TOTAL=0
STEP_TIMES=()

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --date) RUN_DATE="$2"; shift 2 ;;
        --session) SESSION="$2"; shift 2 ;;
        --skip-settle) SKIP_SETTLE=true; shift ;;
        --verbose) VERBOSE=true; shift ;;
        --quiet) VERBOSE=false; shift ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# Validate date format
if ! date -j -f "%Y-%m-%d" "$RUN_DATE" '+%Y-%m-%d' >/dev/null 2>&1 && \
   ! date -d "$RUN_DATE" '+%Y-%m-%d' >/dev/null 2>&1; then
    echo "ERROR: Invalid date format: $RUN_DATE (expected YYYY-MM-DD)"
    exit 1
fi

YESTERDAY=$(date -j -v-1d -f "%Y-%m-%d" "$RUN_DATE" '+%Y-%m-%d' 2>/dev/null || date -d "$RUN_DATE -1 day" '+%Y-%m-%d')

# --- Helper functions ---

# Fetch a URL with Playwright, tracking success/failure
pw_fetch() {
    local label="$1"
    local url="$2"
    FETCH_TOTAL=$((FETCH_TOTAL + 1))
    local start_ts
    start_ts=$(date +%s)
    if [ "$VERBOSE" = true ]; then
        if python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "${url}" 2>&1; then
            FETCH_OK=$((FETCH_OK + 1))
            local elapsed=$(( $(date +%s) - start_ts ))
            echo "  ✅ [${label}] ${url} (${elapsed}s)"
        else
            FETCH_FAIL=$((FETCH_FAIL + 1))
            echo "  ❌ [${label}] ${url} — FAILED"
        fi
    else
        if python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "${url}" 2>&1 | tail -5; then
            FETCH_OK=$((FETCH_OK + 1))
            local elapsed=$(( $(date +%s) - start_ts ))
            echo "  ✅ [${label}] (${elapsed}s)"
        else
            FETCH_FAIL=$((FETCH_FAIL + 1))
            echo "  ❌ [${label}] ${url} — FAILED"
        fi
    fi
}

# Record step timing
step_start() {
    STEP_START_TS=$(date +%s)
    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "$1"
    echo "═══════════════════════════════════════════════════"
}

step_end() {
    local elapsed=$(( $(date +%s) - STEP_START_TS ))
    STEP_TIMES+=("$1: ${elapsed}s")
    echo "  ⏱  Step completed in ${elapsed}s (running: OK=${FETCH_OK} FAIL=${FETCH_FAIL}/${FETCH_TOTAL})"
}

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║       PHASE A — DATA HARVEST (Enhanced v2)                   ║"
echo "║  Date: $RUN_DATE  Session: $SESSION                          ║"
echo "║  Time: $(date '+%Y-%m-%d %H:%M:%S %Z')                      ║"
echo "║  Verbose: $VERBOSE                                           ║"
echo "╚════════════════════════════════════════════════════════════════╝"

# --- 0. Environment setup ---
mkdir -p "${DATA_DIR}"

if [ ! -d "${VENV_DIR}" ]; then
    echo "[setup] Creating virtual environment..."
    python3 -m venv "${VENV_DIR}"
fi
# shellcheck disable=SC1091
set +u
source "${VENV_DIR}/bin/activate"
set -u
echo "[setup] Python: $(python3 --version) at $(which python3)"
python3 -m pip install --upgrade pip -q 2>&1 | tail -1
python3 -m pip install -r "${SCRIPT_DIR}/requirements.txt" -q 2>&1 | tail -3
python3 -m playwright install chromium 2>&1 | tail -2 || echo "[WARN] Playwright install skipped"
echo "[setup] Environment ready."

step_start "STEP A0: Betclic History Analysis (§0.2 MANDATORY)"

if [ -f "${DATA_DIR}/betclic_bets_history.json" ]; then
    echo "[A0.1] Running Betclic learning analysis..."
    python3 "${SCRIPT_DIR}/analyze_betclic_learning.py" 2>&1 | tee "${DATA_DIR}/betclic_learning_output.txt"
    echo "  ✅ Learning analysis complete"
    if [ -f "${DATA_DIR}/betclic_learning_summary.json" ]; then
        echo "  ✅ Summary artifact: betclic_learning_summary.json"
    fi
else
    echo "  ⚠️  betclic_bets_history.json NOT FOUND"
    echo "  ⚠️  Run: python3 scripts/parse_betclic_bets.py (requires HTML from betclic.pl/my-bets)"
    echo "  ⚠️  §0.2 INCOMPLETE — Phase B will flag this as a blocker"
fi

step_end "A0-BetclicLearning"

step_start "STEP A1: Settlement + Score Fetch"

if [ "$SKIP_SETTLE" = false ]; then
    echo "[A1.1] Fetching scores for settlement via The-Odds-API..."
    python3 "${SCRIPT_DIR}/fetch_odds_api.py" --scores football,tennis,basketball,hockey,baseball,mma 2>&1 || echo "[WARN] Score fetch failed — manual settlement needed"

    echo "[A1.2] Running settlement script for ${YESTERDAY}..."
    python3 "${SCRIPT_DIR}/settle_on_finish.py" --betting-day "${YESTERDAY}" 2>&1 || echo "[WARN] Settlement script returned errors — check manually"
else
    echo "[A1] Settlement skipped (--skip-settle flag)"
fi

step_end "A1-Settlement"

step_start "STEP A2: Full 14-Sport Event Scan"

echo "[A2.1] Running full scan pipeline (Flashscore + Sofascore + BetExplorer + Betclic + OddsPortal)..."
bash "${SCRIPT_DIR}/run_full_scan_and_prepare.sh" 2>&1 || echo "[WARN] Full scan returned errors — check scan_errors.json"

echo "[A2.2] Checking scan results..."
if [ -f "${DATA_DIR}/scan_summary.json" ]; then
    echo "  ✅ scan_summary.json exists"
    DATA_DIR_ENV="${DATA_DIR}" python3 -c "
import json, os
data_dir = os.environ['DATA_DIR_ENV']
d = json.load(open(os.path.join(data_dir, 'scan_summary.json')))
total = sum(len(v) if isinstance(v, list) else 0 for v in d.values())
sources = len(d)
print(f'  Sources: {sources}, Total extracted items: {total}')
from collections import Counter
sports = Counter()
for url, items in d.items():
    if isinstance(items, list):
        for item in items:
            sports[item.get('sport', 'unknown')] += 1
for sport, count in sports.most_common():
    print(f'    {sport}: {count} items')
" 2>/dev/null || echo "  (could not parse summary)"
else
    echo "  ❌ scan_summary.json NOT found"
fi

if [ -f "${DATA_DIR}/scan_errors.json" ]; then
    echo "[A2.3] Scan errors:"
    DATA_DIR_ENV="${DATA_DIR}" python3 -c "
import json, os
data_dir = os.environ['DATA_DIR_ENV']
errs = json.load(open(os.path.join(data_dir, 'scan_errors.json')))
print(f'  {len(errs)} errors logged:')
for e in errs:
    print(f'    - {e.get("url", "?")}: {e.get("error", "?")[:80]}')
" 2>/dev/null || echo "  (could not parse errors)"
else
    echo "  ✅ No scan_errors.json (clean scan)"
fi

step_end "A2-EventScan"

step_start "STEP A3: The-Odds-API Cross-Validation"

if [ -f "${ROOT_DIR}/config/odds_api_key.txt" ] || [ -n "${ODDS_API_KEY:-}" ]; then
    echo "[A3.1] Fetching odds from The-Odds-API (≈30 credits)..."
    python3 "${SCRIPT_DIR}/fetch_odds_api.py" 2>&1 || echo "[WARN] Odds API fetch failed"

    # Show quota status
    if [ -f "${DATA_DIR}/odds_api_snapshot.json" ]; then
        echo "  ✅ odds_api_snapshot.json saved"
        DATA_DIR_ENV="${DATA_DIR}" python3 -c "
import json, os
data_dir = os.environ['DATA_DIR_ENV']
data = json.load(open(os.path.join(data_dir, 'odds_api_snapshot.json')))
if isinstance(data, list):
    print(f'  Events with odds: {len(data)}')
elif isinstance(data, dict):
    total = sum(len(v) if isinstance(v, list) else 0 for v in data.values())
    print(f'  Sports: {len(data)}, Events: {total}')
" 2>/dev/null || true
    fi
    if [ -f "${DATA_DIR}/odds_api_summary.csv" ]; then
        lines=$(wc -l < "${DATA_DIR}/odds_api_summary.csv" | tr -d ' ')
        echo "  ✅ odds_api_summary.csv: ${lines} rows"
    fi
else
    echo "[A3] SKIPPED — no API key found in config/odds_api_key.txt or ODDS_API_KEY env var"
fi

step_end "A3-OddsAPI"

step_start "STEP A4: Tipster Pre-Fetch (§1.5 MANDATORY — Tier B Sources)"

# Determine Polish month and weekday names for ZawodTyper URL
DAY_NUM=$(date -j -f "%Y-%m-%d" "$RUN_DATE" '+%-d' 2>/dev/null || date -d "$RUN_DATE" '+%-d')
MONTH_NUM=$(date -j -f "%Y-%m-%d" "$RUN_DATE" '+%-m' 2>/dev/null || date -d "$RUN_DATE" '+%-m')
DOW_NUM=$(date -j -f "%Y-%m-%d" "$RUN_DATE" '+%u' 2>/dev/null || date -d "$RUN_DATE" '+%u')

declare -a PL_MONTHS=("" "stycznia" "lutego" "marca" "kwietnia" "maja" "czerwca" "lipca" "sierpnia" "wrzesnia" "pazdziernika" "listopada" "grudnia")
declare -a PL_DAYS=("" "poniedzialek" "wtorek" "sroda" "czwartek" "piatek" "sobota" "niedziela")

PL_MONTH="${PL_MONTHS[$MONTH_NUM]}"
PL_DOW="${PL_DAYS[$DOW_NUM]}"
ZT_URL="https://zawodtyper.pl/typy-dnia-${DAY_NUM}-${PL_MONTH}-${PL_DOW}/"

echo ""
echo "--- Tier B: Argument-Based Tipster Communities (Deep-dive required) ---"
pw_fetch "A4.1-ZawodTyper" "${ZT_URL}"
pw_fetch "A4.2-Typersi" "https://typersi.pl/"
pw_fetch "A4.3-Meczyki" "https://meczyki.pl/typy-bukmacherskie"
pw_fetch "A4.4-Sportsgambler" "https://www.sportsgambler.com/predictions/today/"
pw_fetch "A4.5-PicksWise" "https://www.pickswise.com/tennis/"
pw_fetch "A4.6-BetIdeas" "https://www.betideas.com/tips/football"
pw_fetch "A4.7-OLBG-football" "https://www.olbg.com/tips/football"
pw_fetch "A4.8-OLBG-tennis" "https://www.olbg.com/tips/tennis"
pw_fetch "A4.9-Tipstrr" "https://www.tipstrr.com/tips"

echo ""
echo "--- Tier B: Sport-Specific Tipster Pages ---"
pw_fetch "A4.10-PW-NHL" "https://www.pickswise.com/nhl/picks/"
pw_fetch "A4.11-PW-NBA" "https://www.pickswise.com/nba/picks/"
pw_fetch "A4.12-PW-MLB" "https://www.pickswise.com/mlb/picks/"
pw_fetch "A4.13-PW-Soccer" "https://www.pickswise.com/soccer/picks/"
pw_fetch "A4.14-BI-Corners" "https://www.betideas.com/corner-betting-tips"
pw_fetch "A4.15-BI-BTTS" "https://www.betideas.com/btts-tips"
pw_fetch "A4.16-BI-OverUnder" "https://www.betideas.com/over-under-tips"
pw_fetch "A4.17-OLBG-basketball" "https://www.olbg.com/tips/basketball"
pw_fetch "A4.18-OLBG-hockey" "https://www.olbg.com/tips/ice-hockey"

step_end "A4-Tipsters"

step_start "STEP A5: Pre-Fetch Stat Sources (Tier A Specialists)"

echo ""
echo "--- Football: Corners, Cards, Fouls, xG ---"
pw_fetch "A5.1-TotalCorner" "https://www.totalcorner.com/match/today"
pw_fetch "A5.2-Betaminic-Corners" "https://www.betaminic.com/statistics/corners-team-stats-tables/"
pw_fetch "A5.3-Betaminic-Cards" "https://www.betaminic.com/statistics/yellow-cards-team-stats-tables/"
pw_fetch "A5.4-SoccerStats" "https://www.soccerstats.com/latest.asp?league=england"
pw_fetch "A5.5-SoccerStats-Spain" "https://www.soccerstats.com/latest.asp?league=spain"
pw_fetch "A5.6-SoccerStats-Germany" "https://www.soccerstats.com/latest.asp?league=germany"
pw_fetch "A5.7-SoccerStats-Italy" "https://www.soccerstats.com/latest.asp?league=italy"
pw_fetch "A5.8-TransferMarkt" "https://www.transfermarkt.com/transfers/neuestetransfers/statistik"

echo ""
echo "--- BetExplorer: All Sports Fixtures + Odds ---"
for SPORT in soccer tennis basketball volleyball hockey baseball handball snooker esports darts table-tennis padel speedway; do
    pw_fetch "A5.9-BE-${SPORT}" "https://www.betexplorer.com/${SPORT}/"
done

echo ""
echo "--- Tennis: Elo, H2H, Surface Stats ---"
pw_fetch "A5.10-TennisAbstract-ATP" "https://www.tennisabstract.com/reports/atp_elo_ratings.html"
pw_fetch "A5.11-TennisAbstract-WTA" "https://www.tennisabstract.com/reports/wta_elo_ratings.html"
pw_fetch "A5.12-TennisExplorer" "https://www.tennisexplorer.com/"
pw_fetch "A5.13-UTS" "https://www.ultimatetennisstatistics.com/"

echo ""
echo "--- Basketball: Pace, Efficiency, Totals ---"
pw_fetch "A5.14-BBRef" "https://www.basketball-reference.com/"
pw_fetch "A5.15-DunksAndThrees" "https://www.dunksandthrees.com/"
pw_fetch "A5.16-Eurobasket" "https://www.eurobasket.com/"

echo ""
echo "--- Hockey: xG, Corsi, Goalies ---"
pw_fetch "A5.17-HockeyRef" "https://www.hockey-reference.com/"
pw_fetch "A5.18-NatStatTrick" "https://www.naturalstattrick.com/"
pw_fetch "A5.19-MoneyPuck" "https://moneypuck.com/"
pw_fetch "A5.20-DailyFaceoff" "https://www.dailyfaceoff.com/starting-goalies/"

echo ""
echo "--- Baseball: Statcast ---"
pw_fetch "A5.21-BBSavant" "https://baseballsavant.mlb.com/"

echo ""
echo "--- US Sport Odds: SBR + ESPN + ScoresAndOdds ---"
pw_fetch "A5.22-SBR-NHL" "https://www.sportsbookreview.com/betting-odds/nhl-hockey/"
pw_fetch "A5.23-SBR-NBA" "https://www.sportsbookreview.com/betting-odds/nba-basketball/"
pw_fetch "A5.24-SBR-MLB" "https://www.sportsbookreview.com/betting-odds/mlb-baseball/"
pw_fetch "A5.25-ESPN-NHL" "https://www.espn.com/nhl/odds"
pw_fetch "A5.26-ESPN-NBA" "https://www.espn.com/nba/odds"
pw_fetch "A5.27-ESPN-MLB" "https://www.espn.com/mlb/odds"
pw_fetch "A5.28-SAO-NHL" "https://www.scoresandodds.com/nhl"
pw_fetch "A5.29-SAO-NBA" "https://www.scoresandodds.com/nba"
pw_fetch "A5.30-SAO-MLB" "https://www.scoresandodds.com/mlb"

echo ""
echo "--- Esports: CS2, Dota, Valorant ---"
pw_fetch "A5.31-HLTV" "https://www.hltv.org/matches"
pw_fetch "A5.32-Liquipedia-CS2" "https://liquipedia.net/counterstrike/Matches/Today"
pw_fetch "A5.33-GosuGamers" "https://www.gosugamers.net/"
pw_fetch "A5.34-BO3gg" "https://bo3.gg/"

echo ""
echo "--- Snooker ---"
pw_fetch "A5.35-CueTracker" "https://cuetracker.net/"
pw_fetch "A5.36-SnookerOrg" "https://www.snooker.org/"

echo ""
echo "--- Darts ---"
pw_fetch "A5.37-DartsOrakel" "https://dartsorakel.com/"

echo ""
echo "--- MMA ---"
pw_fetch "A5.38-UFCstats" "https://www.ufcstats.com/statistics/events/completed"
pw_fetch "A5.39-Tapology" "https://www.tapology.com/fightcenter"
pw_fetch "A5.40-Sherdog" "https://www.sherdog.com/events"

echo ""
echo "--- Handball ---"
pw_fetch "A5.41-EHF" "https://www.eurohandball.com/"

echo ""
echo "--- Volleyball ---"
pw_fetch "A5.42-PlusLiga" "https://plusliga.pl/"
pw_fetch "A5.43-CEV" "https://www.cev.eu/"

echo ""
echo "--- Padel ---"
pw_fetch "A5.44-PremierPadel" "https://www.premierpadel.com/"
pw_fetch "A5.45-PadelFIP" "https://www.padelfip.com/"

echo ""
echo "--- Speedway ---"
pw_fetch "A5.46-SpeedwayEL" "https://speedwayekstraliga.pl/"
pw_fetch "A5.47-SportoweFakty" "https://sportowefakty.wp.pl/zuzel"

echo ""
echo "--- General Stats + Previews ---"
pw_fetch "A5.48-Covers" "https://www.covers.com/"
pw_fetch "A5.49-TeamRankings" "https://www.teamrankings.com/"

step_end "A5-StatSources"

step_start "STEP A6: Pre-Fetch Validation & Data Consistency Check"

echo ""
echo "--- Tipster Coverage ---"
TIPSTER_DIRS=(zawodtyper.pl typersi.pl sportsgambler.com pickswise.com betideas.com olbg.com meczyki.pl tipstrr.com)
TIPSTER_OK=0
TIPSTER_FAIL=0
for DIR in "${TIPSTER_DIRS[@]}"; do
    if [ -d "${DATA_DIR}/${DIR}" ] && [ -n "$(find "${DATA_DIR}/${DIR}" -name '*.html' -maxdepth 1 2>/dev/null | head -1)" ]; then
        FILE_COUNT=$(find "${DATA_DIR}/${DIR}" -name '*.html' -maxdepth 1 2>/dev/null | wc -l | tr -d ' ')
        TOTAL_SIZE=$(du -sh "${DATA_DIR}/${DIR}" 2>/dev/null | cut -f1)
        echo "  ✅ ${DIR}: ${FILE_COUNT} file(s), ${TOTAL_SIZE}"
        TIPSTER_OK=$((TIPSTER_OK + 1))
    else
        echo "  ❌ ${DIR}: NO HTML — tipster coverage will be degraded"
        TIPSTER_FAIL=$((TIPSTER_FAIL + 1))
    fi
done
echo "  Tipster pre-fetch: ${TIPSTER_OK}/${#TIPSTER_DIRS[@]} OK, ${TIPSTER_FAIL}/${#TIPSTER_DIRS[@]} missing"

echo ""
echo "--- Market & Odds Coverage ---"
MARKET_DIRS=(betexplorer.com oddsportal.com sportsbookreview.com espn.com scoresandodds.com)
for DIR in "${MARKET_DIRS[@]}"; do
    if [ -d "${DATA_DIR}/${DIR}" ] && [ -n "$(find "${DATA_DIR}/${DIR}" -name '*.html' -maxdepth 1 2>/dev/null | head -1)" ]; then
        FILE_COUNT=$(find "${DATA_DIR}/${DIR}" -name '*.html' -maxdepth 1 2>/dev/null | wc -l | tr -d ' ')
        echo "  ✅ ${DIR}: ${FILE_COUNT} file(s)"
    else
        echo "  ⚠️  ${DIR}: no data"
    fi
done

echo ""
echo "--- Statistical Sources Coverage ---"
STAT_DIRS=(flashscore.com sofascore.com totalcorner.com betaminic.com soccerstats.com
           basketball-reference.com hockey-reference.com naturalstattrick.com moneypuck.com
           baseballsavant.mlb.com dailyfaceoff.com tennisabstract.com tennisexplorer.com
           ultimatetennisstatistics.com dunksandthrees.com eurobasket.com transfermarkt.com
           hltv.org cuetracker.net dartsorakel.com ufcstats.com tapology.com)
STAT_OK=0
for DIR in "${STAT_DIRS[@]}"; do
    if [ -d "${DATA_DIR}/${DIR}" ] && [ -n "$(find "${DATA_DIR}/${DIR}" -name '*.html' -maxdepth 1 2>/dev/null | head -1)" ]; then
        STAT_OK=$((STAT_OK + 1))
    fi
done
echo "  Statistical sources with data: ${STAT_OK}/${#STAT_DIRS[@]}"

echo ""
echo "--- Data Volume Summary ---"
TOTAL_HTML=$(find "${DATA_DIR}" -name '*.html' 2>/dev/null | wc -l | tr -d ' ')
TOTAL_JSON=$(find "${DATA_DIR}" -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
TOTAL_SIZE=$(du -sh "${DATA_DIR}" 2>/dev/null | cut -f1)
DOMAIN_COUNT=$(find "${DATA_DIR}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
echo "  Total HTML files: ${TOTAL_HTML}"
echo "  Total JSON files: ${TOTAL_JSON}"
echo "  Total data size: ${TOTAL_SIZE}"
echo "  Domain folders: ${DOMAIN_COUNT}"

echo ""
echo "--- Content Quality Check ---"
DATA_DIR_ENV="${DATA_DIR}" python3 -c "
import os, json
from pathlib import Path

data_dir = Path(os.environ['DATA_DIR_ENV'])
issues = []

# Check for empty or too-small HTML files (< 500 bytes = likely error page)
for html_file in data_dir.rglob('*.html'):
    size = html_file.stat().st_size
    if size < 500:
        issues.append(f'  ⚠️  {html_file.relative_to(data_dir)}: only {size} bytes (likely error/empty)')

# Check scan_summary.json for completeness
summary_path = data_dir / 'scan_summary.json'
if summary_path.exists():
    data = json.load(open(summary_path))
    empty_sources = [url for url, items in data.items() if isinstance(items, list) and len(items) == 0]
    if empty_sources:
        issues.append(f'  ⚠️  {len(empty_sources)} sources returned 0 items in scan_summary.json')
        for src in empty_sources[:5]:
            issues.append(f'      - {src}')

# Check odds_api data
odds_path = data_dir / 'odds_api_snapshot.json'
if odds_path.exists():
    odds_data = json.load(open(odds_path))
    if isinstance(odds_data, dict) and len(odds_data) == 0:
        issues.append('  ⚠️  odds_api_snapshot.json is empty')
    elif isinstance(odds_data, list) and len(odds_data) == 0:
        issues.append('  ⚠️  odds_api_snapshot.json has 0 events')

if issues:
    print(f'Found {len(issues)} potential data quality issues:')
    for issue in issues[:20]:
        print(issue)
else:
    print('  ✅ No data quality issues detected')
" 2>/dev/null || echo "  (could not run quality check)"

step_end "A6-Validation"

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  PHASE A COMPLETE — HARVEST SUMMARY                          ║"
echo "╠════════════════════════════════════════════════════════════════╣"
echo "║  Date: $RUN_DATE  Session: $SESSION                          ║"
echo "║  Finished: $(date '+%Y-%m-%d %H:%M:%S %Z')                   ║"
echo "║  Fetch results: ${FETCH_OK} OK / ${FETCH_FAIL} FAILED / ${FETCH_TOTAL} total    ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Step timings:"
if [ ${#STEP_TIMES[@]} -gt 0 ]; then
    for t in "${STEP_TIMES[@]}"; do
        echo "  ⏱  $t"
    done
fi
echo ""
echo "Key output files:"
for f in "${DATA_DIR}/scan_summary.json" "${DATA_DIR}/picks_suggested.json" "${DATA_DIR}/scan_errors.json" "${DATA_DIR}/odds_api_snapshot.json" "${DATA_DIR}/odds_api_summary.csv"; do
    if [ -f "$f" ]; then
        SIZE=$(du -h "$f" | cut -f1)
        echo "  ✅ $(basename "$f") (${SIZE})"
    else
        echo "  -- $(basename "$f") not created"
    fi
done
echo ""
echo "Data files ready in: betting/data/"
echo ""
echo "NEXT: Invoke the AI orchestrator for Phase B:"
echo ""
echo "  In VS Code Copilot Chat, type:"
echo "  @workspace /prompt orchestrate-betting-day run_date=${RUN_DATE} session=${SESSION}"
echo ""
echo "  Or for rerun:"
echo "  @workspace /prompt orchestrate-betting-day run_date=${RUN_DATE} session=${SESSION} rerun=true"
echo ""
echo "Phase B will run S0→S8 with 4-pass error correction."
echo "You will see ONLY the final coupons at the end."
echo "═══════════════════════════════════════════════════"
