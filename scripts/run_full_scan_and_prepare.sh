#!/usr/bin/env bash
set -euo pipefail

# Orchestrator: install deps, ensure Playwright browsers, run smoke, scan and aggregate
# Usage: bash scripts/run_full_scan_and_prepare.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/.."
DATA_DIR="${ROOT_DIR}/betting/data"
VENV_DIR="${ROOT_DIR}/.venv"

# Ensure data directory exists
mkdir -p "${DATA_DIR}"

# Create or reuse virtual environment
if [ ! -d "${VENV_DIR}" ]; then
    echo "[orchestrator] Creating virtual environment at ${VENV_DIR}..."
    python3 -m venv "${VENV_DIR}"
fi
# shellcheck disable=SC1091
set +u
source "${VENV_DIR}/bin/activate"
set -u

echo "============================================="
echo "[orchestrator] Starting full scan pipeline"
echo "[orchestrator] Time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "[orchestrator] Python: $(which python3)"
echo "============================================="

echo ""
echo "[1/10] Installing Python requirements..."
python3 -m pip install --upgrade pip -q 2>&1 | tail -1
python3 -m pip install -r "${SCRIPT_DIR}/requirements.txt" -q 2>&1 | tail -5

echo ""
echo "[2/10] Installing Playwright browser (Chromium)..."
python3 -m playwright install chromium 2>&1 | tail -3 || echo "[WARNING] Playwright install skipped or failed"

echo ""
echo "[3/10] Running Playwright smoke test..."
if python3 "${SCRIPT_DIR}/smoke_playwright.py"; then
    echo "[OK] Smoke test passed"
else
    echo "[WARNING] Smoke test failed — continuing with requests fallback"
fi

echo ""
echo "[4/10] Running full multi-sport scan (Tier-A + Tier-B)..."
SCAN_START=$(date +%s)

# Build ZawodTyper daily URL using bash (avoids quoting issues with inline Python dicts)
_ZT_DAY=$(date '+%-d')
_ZT_MONTH=$(date '+%-m')
_ZT_DOW=$(date '+%u')  # 1=Mon .. 7=Sun
declare -a _PL_M=("" "stycznia" "lutego" "marca" "kwietnia" "maja" "czerwca" "lipca" "sierpnia" "wrzesnia" "pazdziernika" "listopada" "grudnia")
declare -a _PL_D=("" "poniedzialek" "wtorek" "sroda" "czwartek" "piatek" "sobota" "niedziela")
_ZT_URL="https://www.zawodtyper.pl/typy-dnia-${_ZT_DAY}-${_PL_M[$_ZT_MONTH]}-${_PL_D[$_ZT_DOW]}/"

# URLs include: Flashscore (all sports + exotic football regions),
# Sofascore, Betclic, OddsPortal, BetExplorer, specialist sources,
# tipster sites, and Soccerway (exotic league coverage).
python3 "${SCRIPT_DIR}/scan_events.py" --urls \
  https://www.flashscore.com/ \
  https://www.flashscore.com/tennis/ \
  https://www.flashscore.com/basketball/ \
  https://www.flashscore.com/hockey/ \
  https://www.flashscore.com/baseball/ \
  https://www.flashscore.com/volleyball/ \
  https://www.flashscore.com/handball/ \
  https://www.flashscore.com/snooker/ \
  https://www.flashscore.com/esports/ \
  https://www.flashscore.com/darts/ \
  https://www.flashscore.com/table-tennis/ \
  https://www.flashscore.com/mma/ \
  https://www.flashscore.com/football/peru/ \
  https://www.flashscore.com/football/egypt/ \
  https://www.flashscore.com/football/uzbekistan/ \
  https://www.flashscore.com/football/saudi-arabia/ \
  https://www.flashscore.com/football/colombia/ \
  https://www.flashscore.com/football/chile/ \
  https://www.flashscore.com/football/algeria/ \
  https://www.flashscore.com/football/morocco/ \
  https://www.flashscore.com/football/india/ \
  https://www.flashscore.com/football/vietnam/ \
  https://www.flashscore.com/football/thailand/ \
  https://www.flashscore.com/football/iran/ \
  https://www.flashscore.com/football/kazakhstan/ \
  https://www.flashscore.com/football/georgia/ \
  https://www.flashscore.com/football/kosovo/ \
  https://www.flashscore.com/football/paraguay/ \
  https://www.flashscore.com/football/ecuador/ \
  https://www.flashscore.com/football/costa-rica/ \
  https://www.flashscore.com/football/jordan/ \
  https://www.flashscore.com/football/uae/ \
  https://www.soccerway.com/ \
  https://www.sofascore.com/ \
  https://www.sofascore.com/padel \
  https://www.betclic.pl/pilka-nozna-s1 \
  https://www.betclic.pl/tenis-s2 \
  https://www.betclic.pl/koszykowka-s4 \
  https://www.betclic.pl/hokej-na-lodzie-s13 \
  https://www.betclic.pl/baseball-s14 \
  https://www.betclic.pl/siatkowka-s18 \
  https://www.betclic.pl/snooker-s19 \
  https://www.betclic.pl/esport-s46 \
  https://www.betclic.pl/rzutki-s11 \
  https://www.betclic.pl/pilka-reczna-s3 \
  https://www.betclic.pl/tenis-stolowy-s10 \
  https://www.betclic.pl/mma-s38 \
  https://www.betclic.pl/padel-s48 \
  https://www.betclic.pl/zuzel-s36 \
  https://www.oddsportal.com/ \
  https://www.oddsportal.com/tennis/ \
  https://www.oddsportal.com/basketball/ \
  https://www.oddsportal.com/hockey/ \
  https://www.oddsportal.com/baseball/ \
  https://www.betexplorer.com/ \
  https://www.betexplorer.com/volleyball/ \
  https://www.betexplorer.com/handball/ \
  https://www.betexplorer.com/snooker/ \
  https://www.betexplorer.com/esports/ \
  https://www.betexplorer.com/darts/ \
  https://www.betexplorer.com/table-tennis/ \
  https://www.betexplorer.com/padel/ \
  https://www.betexplorer.com/speedway/ \
  https://www.premierpadel.com/ \
  https://speedwayekstraliga.pl/ \
  https://sportowefakty.wp.pl/zuzel \
  https://www.covers.com/ \
  https://www.teamrankings.com/ \
  https://www.tennisabstract.com/reports/wta_elo_ratings.html \
  https://www.tennisabstract.com/reports/atp_elo_ratings.html \
  https://www.tennisexplorer.com/ \
  https://www.sportsgambler.com/predictions/today/ \
  https://www.betideas.com/ \
  https://www.pickswise.com/ \
  https://www.zawodtyper.pl/ \
  "${_ZT_URL}" \
  https://typersi.pl/ \
  https://www.feedinco.com/ \
  https://www.bettingclosed.com/ \
  https://tips180.com/ \
  https://www.tipstrr.com/tips \
  https://dartsorakel.com/ \
  https://cuetracker.net/ \
  https://www.gosugamers.net/ \
  https://www.basketball-reference.com/ \
  https://www.hockey-reference.com/ || echo "[WARNING] Scan finished with errors — check scan_errors.json"
SCAN_END=$(date +%s)
echo "[orchestrator] Scan took $((SCAN_END - SCAN_START)) seconds"

echo ""
echo "[5/10] Discovering fixtures via APIs..."
python3 "${SCRIPT_DIR}/discover_fixtures.py" --date "$(date '+%Y-%m-%d')" || echo "[WARNING] API fixture discovery failed — continuing with scan results only"

echo ""
echo "[6/10] Fetching statistics from APIs..."
python3 "${SCRIPT_DIR}/fetch_api_stats.py" --date "$(date '+%Y-%m-%d')" || echo "[WARNING] API stats fetch failed — continuing with existing data"

echo ""
echo "[7/10] Generating deep analysis pool..."
python3 "${SCRIPT_DIR}/deep_analysis_pool.py" --date "$(date '+%Y-%m-%d')" || echo "[WARNING] Analysis pool generation failed — continuing"

echo ""
echo "[8/10] Aggregating and selecting candidates..."
python3 "${SCRIPT_DIR}/aggregate_and_select.py"

echo ""
echo "[9/10] Extracting Betclic sport-specific markets..."
python3 "${SCRIPT_DIR}/quick_betclic_extract.py" 2>/dev/null || echo "[INFO] Betclic detail extraction skipped or failed"

echo ""
echo "[10/10] Summary..."
echo "============================================="
echo "[orchestrator] Pipeline complete"
echo "[orchestrator] Time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "============================================="
echo ""
echo "Outputs:"
for f in "${DATA_DIR}/scan_summary.json" "${DATA_DIR}/picks_suggested.json" "${DATA_DIR}/scan_errors.json" "${DATA_DIR}/betclic_verified_odds.json" "${DATA_DIR}/analysis_pool_$(date '+%Y-%m-%d').json" "${DATA_DIR}/analysis_pool_$(date '+%Y-%m-%d').md"; do
    if [ -f "$f" ]; then
        echo "  [OK] $(basename "$f") ($(wc -c < "$f") bytes)"
    else
        echo "  [--] $(basename "$f") not created"
    fi
done
