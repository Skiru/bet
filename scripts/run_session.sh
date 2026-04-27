#!/usr/bin/env bash
set -euo pipefail

# ==================================================================
# PHASE A — DATA HARVEST
# Single command that runs ALL automated data gathering.
# After this completes, invoke the orchestrator prompt for Phase B.
#
# Usage:
#   bash scripts/run_session.sh                    # settle yesterday + scan today
#   bash scripts/run_session.sh --date 2026-04-27  # explicit date
#   bash scripts/run_session.sh --skip-settle       # skip settlement (already done)
#   bash scripts/run_session.sh --session night     # night session (scan still runs all)
# ==================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/.."
DATA_DIR="${ROOT_DIR}/betting/data"
VENV_DIR="${ROOT_DIR}/.venv"
CONFIG="${ROOT_DIR}/config/betting_config.json"

# Defaults
RUN_DATE=$(date '+%Y-%m-%d')
SESSION="full"
SKIP_SETTLE=false
DATE_COMPACT=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --date) RUN_DATE="$2"; shift 2 ;;
        --session) SESSION="$2"; shift 2 ;;
        --skip-settle) SKIP_SETTLE=true; shift ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

DATE_COMPACT="${RUN_DATE//-/}"
YESTERDAY=$(date -j -v-1d -f "%Y-%m-%d" "$RUN_DATE" '+%Y-%m-%d' 2>/dev/null || date -d "$RUN_DATE -1 day" '+%Y-%m-%d')

echo "╔════════════════════════════════════════════════════╗"
echo "║       PHASE A — DATA HARVEST                      ║"
echo "║  Date: $RUN_DATE  Session: $SESSION               ║"
echo "║  Time: $(date '+%Y-%m-%d %H:%M:%S %Z')            ║"
echo "╚════════════════════════════════════════════════════╝"

# --- 0. Environment setup ---
mkdir -p "${DATA_DIR}"

if [ ! -d "${VENV_DIR}" ]; then
    echo "[setup] Creating virtual environment..."
    python3 -m venv "${VENV_DIR}"
fi
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
python3 -m pip install --upgrade pip -q 2>&1 | tail -1
python3 -m pip install -r "${SCRIPT_DIR}/requirements.txt" -q 2>&1 | tail -3
python3 -m playwright install chromium 2>&1 | tail -2 || echo "[WARN] Playwright install skipped"

echo ""
echo "═══════════════════════════════════════════════════"
echo "STEP A1: Settlement + Score Fetch"
echo "═══════════════════════════════════════════════════"

if [ "$SKIP_SETTLE" = false ]; then
    echo "[A1.1] Fetching scores for settlement via The-Odds-API..."
    python3 "${SCRIPT_DIR}/fetch_odds_api.py" --scores baseball,hockey 2>&1 | tail -5 || echo "[WARN] Score fetch failed — manual settlement needed"

    echo "[A1.2] Running settlement script for ${YESTERDAY}..."
    python3 "${SCRIPT_DIR}/settle_on_finish.py" --betting-day "${YESTERDAY}" 2>&1 | tail -10 || echo "[WARN] Settlement script returned errors — check manually"
else
    echo "[A1] Settlement skipped (--skip-settle flag)"
fi

echo ""
echo "═══════════════════════════════════════════════════"
echo "STEP A2: Full 14-Sport Event Scan"
echo "═══════════════════════════════════════════════════"

echo "[A2.1] Running full scan pipeline (Flashscore + Sofascore + BetExplorer + Betclic)..."
bash "${SCRIPT_DIR}/run_full_scan_and_prepare.sh" 2>&1 | tail -20

echo "[A2.2] Checking scan results..."
if [ -f "${DATA_DIR}/scan_summary.json" ]; then
    echo "[OK] scan_summary.json exists"
    python3 -c "import json; d=json.load(open('${DATA_DIR}/scan_summary.json')); print(f'  Events: {d.get(\"total_events\", \"?\")}, Sports: {d.get(\"sports_count\", \"?\")}')" 2>/dev/null || echo "  (could not parse summary)"
else
    echo "[WARN] scan_summary.json NOT found"
fi

if [ -f "${DATA_DIR}/scan_errors.json" ]; then
    echo "[A2.3] Scan errors:"
    python3 -c "import json; errs=json.load(open('${DATA_DIR}/scan_errors.json')); print(f'  {len(errs)} errors logged')" 2>/dev/null || echo "  (could not parse errors)"
else
    echo "[OK] No scan_errors.json (clean scan)"
fi

echo ""
echo "═══════════════════════════════════════════════════"
echo "STEP A3: The-Odds-API Cross-Validation"
echo "═══════════════════════════════════════════════════"

if [ -f "${ROOT_DIR}/config/odds_api_key.txt" ] || [ -n "${ODDS_API_KEY:-}" ]; then
    echo "[A3] Fetching odds from The-Odds-API (≈30 credits)..."
    python3 "${SCRIPT_DIR}/fetch_odds_api.py" 2>&1 | tail -10 || echo "[WARN] Odds API fetch failed"
else
    echo "[A3] SKIPPED — no API key found in config/odds_api_key.txt or ODDS_API_KEY env var"
fi

echo ""
echo "═══════════════════════════════════════════════════"
echo "STEP A4: Tipster Pre-Fetch (§1.5 MANDATORY)"
echo "═══════════════════════════════════════════════════"

# Determine Polish month and weekday names for ZawodTyper URL
DAY_NUM=$(date -j -f "%Y-%m-%d" "$RUN_DATE" '+%-d' 2>/dev/null || date -d "$RUN_DATE" '+%-d')
MONTH_NUM=$(date -j -f "%Y-%m-%d" "$RUN_DATE" '+%-m' 2>/dev/null || date -d "$RUN_DATE" '+%-m')
DOW_NUM=$(date -j -f "%Y-%m-%d" "$RUN_DATE" '+%u' 2>/dev/null || date -d "$RUN_DATE" '+%u')

declare -a PL_MONTHS=("" "stycznia" "lutego" "marca" "kwietnia" "maja" "czerwca" "lipca" "sierpnia" "wrzesnia" "pazdziernika" "listopada" "grudnia")
declare -a PL_DAYS=("" "poniedzialek" "wtorek" "sroda" "czwartek" "piatek" "sobota" "niedziela")

PL_MONTH="${PL_MONTHS[$MONTH_NUM]}"
PL_DOW="${PL_DAYS[$DOW_NUM]}"
ZT_URL="https://zawodtyper.pl/typy-dnia-${DAY_NUM}-${PL_MONTH}-${PL_DOW}/"

echo "[A4.1] Fetching ZawodTyper: ${ZT_URL}"
python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "${ZT_URL}" 2>&1 | tail -3 || echo "[WARN] ZawodTyper fetch failed"

echo "[A4.2] Fetching Typersi..."
python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "https://typersi.pl/" 2>&1 | tail -3 || echo "[WARN] Typersi fetch failed"

echo "[A4.3] Fetching Sportsgambler..."
python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "https://www.sportsgambler.com/predictions/today/" 2>&1 | tail -3 || echo "[WARN] Sportsgambler fetch failed"

echo "[A4.4] Fetching PicksWise..."
python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "https://www.pickswise.com/tennis/" 2>&1 | tail -3 || echo "[WARN] PicksWise fetch failed"

echo "[A4.5] Fetching BetIdeas..."
python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "https://www.betideas.com/tips/football" 2>&1 | tail -3 || echo "[WARN] BetIdeas fetch failed"

# Sport-specific tipster pages
echo "[A4.6] Fetching sport-specific tipster pages..."
python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "https://www.pickswise.com/nhl/picks/" 2>&1 | tail -2 || true
python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "https://www.pickswise.com/nba/picks/" 2>&1 | tail -2 || true
python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "https://www.pickswise.com/mlb/picks/" 2>&1 | tail -2 || true
python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "https://www.betideas.com/corner-betting-tips" 2>&1 | tail -2 || true
python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "https://www.betideas.com/btts-tips" 2>&1 | tail -2 || true
python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "https://www.betideas.com/over-under-tips" 2>&1 | tail -2 || true
python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "https://www.olbg.com/tips/football" 2>&1 | tail -2 || true
python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "https://www.olbg.com/tips/tennis" 2>&1 | tail -2 || true

echo ""
echo "═══════════════════════════════════════════════════"
echo "STEP A5: Pre-Fetch Stat Sources"
echo "═══════════════════════════════════════════════════"

echo "[A5.1] Fetching TotalCorner today..."
python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "https://www.totalcorner.com/match/today" 2>&1 | tail -2 || true

echo "[A5.2] Fetching BetExplorer fixtures..."
for SPORT in soccer tennis basketball volleyball hockey baseball handball snooker esports darts table-tennis; do
    python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "https://www.betexplorer.com/${SPORT}/" 2>&1 | tail -1 || true
done

echo "[A5.3] Fetching DailyFaceoff (NHL goalies)..."
python3 "${SCRIPT_DIR}/fetch_with_playwright.py" "https://www.dailyfaceoff.com/starting-goalies/" 2>&1 | tail -2 || true

echo ""
echo "═══════════════════════════════════════════════════"
echo "PHASE A COMPLETE"
echo "═══════════════════════════════════════════════════"
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
