#!/usr/bin/env bash
set -euo pipefail

# Orchestrator: install deps, ensure Playwright browsers, run smoke, scan and aggregate
# Usage: bash scripts/run_full_scan_and_prepare.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/.."
DATA_DIR="${ROOT_DIR}/betting/data"

# Ensure data directory exists
mkdir -p "${DATA_DIR}"

echo "============================================="
echo "[orchestrator] Starting full scan pipeline"
echo "[orchestrator] Time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "============================================="

echo ""
echo "[1/5] Installing Python requirements..."
python3 -m pip install --user -r "${SCRIPT_DIR}/requirements.txt" 2>&1 | tail -5

echo ""
echo "[2/5] Installing Playwright browser (Chromium)..."
python3 -m playwright install chromium 2>&1 | tail -3 || echo "[WARNING] Playwright install skipped or failed"

echo ""
echo "[3/5] Running Playwright smoke test..."
if python3 "${SCRIPT_DIR}/smoke_playwright.py"; then
    echo "[OK] Smoke test passed"
else
    echo "[WARNING] Smoke test failed — continuing with requests fallback"
fi

echo ""
echo "[4/5] Running full scan (Tier-A + Tier-B)..."
SCAN_START=$(date +%s)
python3 "${SCRIPT_DIR}/scan_events.py" --urls \
  https://www.flashscore.com/ \
  https://www.sofascore.com/ \
  https://www.betclic.pl/ \
  https://www.oddsportal.com/ \
  https://www.oddspedia.com/ \
  https://www.betexplorer.com/ \
  https://www.forebet.com/ \
  https://www.predictz.com/ \
  https://www.protipster.com/ \
  https://www.bettingexpert.com/ \
  https://www.zawodtyper.pl/ || echo "[WARNING] Scan finished with errors — check scan_errors.json"
SCAN_END=$(date +%s)
echo "[orchestrator] Scan took $((SCAN_END - SCAN_START)) seconds"

echo ""
echo "[5/5] Aggregating and selecting candidates..."
python3 "${SCRIPT_DIR}/aggregate_and_select.py"

echo ""
echo "============================================="
echo "[orchestrator] Pipeline complete"
echo "[orchestrator] Time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "============================================="
echo ""
echo "Outputs:"
for f in "${DATA_DIR}/scan_summary.json" "${DATA_DIR}/picks_suggested.json" "${DATA_DIR}/scan_errors.json"; do
    if [ -f "$f" ]; then
        echo "  [OK] $(basename "$f") ($(wc -c < "$f") bytes)"
    else
        echo "  [--] $(basename "$f") not created"
    fi
done
