#!/usr/bin/env bash
set -euo pipefail

# Orchestrator: install deps, ensure Playwright browsers, run smoke, scan and aggregate
# Usage: bash scripts/run_full_scan_and_prepare.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/.."

echo "[orchestrator] Installing Python requirements..."
python3 -m pip install --user -r "${SCRIPT_DIR}/requirements.txt"

echo "[orchestrator] Installing Playwright browser (Chromium)..."
python3 -m playwright install chromium || true

echo "[orchestrator] Running Playwright smoke test..."
python3 "${SCRIPT_DIR}/smoke_playwright.py"

echo "[orchestrator] Running full scan (Tier-A + Tier-B)..."
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
  https://www.zawodtyper.pl/

echo "[orchestrator] Aggregating and selecting candidates..."
python3 "${SCRIPT_DIR}/aggregate_and_select.py"

echo "[orchestrator] Done. Outputs are in betting/data/"
