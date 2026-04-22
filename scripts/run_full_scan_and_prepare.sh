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
source "${VENV_DIR}/bin/activate"

echo "============================================="
echo "[orchestrator] Starting full scan pipeline"
echo "[orchestrator] Time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "[orchestrator] Python: $(which python3)"
echo "============================================="

echo ""
echo "[1/7] Installing Python requirements..."
python3 -m pip install --upgrade pip -q 2>&1 | tail -1
python3 -m pip install -r "${SCRIPT_DIR}/requirements.txt" -q 2>&1 | tail -5

echo ""
echo "[2/7] Installing Playwright browser (Chromium)..."
python3 -m playwright install chromium 2>&1 | tail -3 || echo "[WARNING] Playwright install skipped or failed"

echo ""
echo "[3/7] Running Playwright smoke test..."
if python3 "${SCRIPT_DIR}/smoke_playwright.py"; then
    echo "[OK] Smoke test passed"
else
    echo "[WARNING] Smoke test failed — continuing with requests fallback"
fi

echo ""
echo "[4/7] Running full multi-sport scan (Tier-A + Tier-B)..."
SCAN_START=$(date +%s)
python3 "${SCRIPT_DIR}/scan_events.py" --urls \
  https://www.flashscore.com/ \
  https://www.flashscore.com/tennis/ \
  https://www.flashscore.com/basketball/ \
  https://www.flashscore.com/hockey/ \
  https://www.flashscore.com/baseball/ \
  https://www.sofascore.com/ \
  https://www.betclic.pl/pilka-nozna-s1 \
  https://www.betclic.pl/tenis-s2 \
  https://www.betclic.pl/koszykowka-s4 \
  https://www.betclic.pl/hokej-na-lodzie-s13 \
  https://www.betclic.pl/baseball-s14 \
  https://www.oddsportal.com/ \
  https://www.oddsportal.com/tennis/ \
  https://www.oddsportal.com/basketball/ \
  https://www.oddsportal.com/hockey/ \
  https://www.oddsportal.com/baseball/ \
  https://www.oddspedia.com/ \
  https://www.betexplorer.com/ \
  https://www.covers.com/ \
  https://www.teamrankings.com/ \
  https://www.tennisabstract.com/reports/wta_elo_ratings.html \
  https://www.tennisabstract.com/reports/atp_elo_ratings.html \
  https://www.sportsgambler.com/predictions/today/ \
  https://www.forebet.com/ \
  https://www.sportytrader.com/en/predictions/ \
  https://www.predictz.com/ \
  https://www.protipster.com/ \
  https://www.bettingexpert.com/ \
  https://www.zawodtyper.pl/ || echo "[WARNING] Scan finished with errors — check scan_errors.json"
SCAN_END=$(date +%s)
echo "[orchestrator] Scan took $((SCAN_END - SCAN_START)) seconds"

echo ""
echo "[5/7] Aggregating and selecting candidates..."
python3 "${SCRIPT_DIR}/aggregate_and_select.py"

echo ""
echo "[6/7] Extracting Betclic sport-specific markets..."
python3 "${SCRIPT_DIR}/quick_betclic_extract.py" 2>/dev/null || echo "[INFO] Betclic detail extraction skipped or failed"

echo ""
echo "[7/7] Verifying Betclic odds for pending picks..."
BETTING_DAY=$(date '+%Y-%m-%d')
python3 "${SCRIPT_DIR}/verify_betclic_odds.py" --betting-day "${BETTING_DAY}" 2>/dev/null || echo "[INFO] Betclic odds verification skipped (no pending picks or script error)"

echo ""
echo "============================================="
echo "[orchestrator] Pipeline complete"
echo "[orchestrator] Time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "============================================="
echo ""
echo "Outputs:"
for f in "${DATA_DIR}/scan_summary.json" "${DATA_DIR}/picks_suggested.json" "${DATA_DIR}/scan_errors.json" "${DATA_DIR}/betclic_verified_odds.json"; do
    if [ -f "$f" ]; then
        echo "  [OK] $(basename "$f") ($(wc -c < "$f") bytes)"
    else
        echo "  [--] $(basename "$f") not created"
    fi
done
