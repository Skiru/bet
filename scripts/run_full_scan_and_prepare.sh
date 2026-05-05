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

# Error counter for critical steps
ERRORS=0

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
echo "[1/14] Installing Python requirements..."
python3 -m pip install --upgrade pip -q 2>&1 | tail -1
if ! python3 -m pip install -r "${SCRIPT_DIR}/requirements.txt" -q 2>&1 | tail -5; then
    echo "[WARNING] pip install had errors — verifying core packages..."
    python3 -c "import requests, bs4, playwright, understat, nba_api" \
        && echo "[OK] All core packages available" \
        || { echo "[FATAL] Core packages missing — aborting"; exit 1; }
fi

echo ""
echo "[2/14] Installing Playwright browser (Chromium)..."
python3 -m playwright install chromium 2>&1 | tail -3 || echo "[WARNING] Playwright install skipped or failed"

echo ""
echo "[3/14] Running Playwright smoke test..."
if python3 "${SCRIPT_DIR}/smoke_playwright.py"; then
    echo "[OK] Smoke test passed"
else
    echo "[WARNING] Smoke test failed — continuing with requests fallback"
fi

echo ""
echo "[4/14] Cleaning stale HTML files (>7 days old)..."
find "${DATA_DIR}" -name "*.html" -path "*/betting/data/*.*/*" -mtime +7 -delete 2>/dev/null
echo "[orchestrator] Cleaned stale HTML files"

echo ""
echo "[5/14] Running full multi-sport scan (Tier-A + Tier-B)..."
SCAN_START=$(date +%s)

# Build ZawodTyper daily URL using bash (avoids quoting issues with inline Python dicts)
_ZT_DAY=$(date '+%-d')
_ZT_MONTH=$(date '+%-m')
_ZT_DOW=$(date '+%u')  # 1=Mon .. 7=Sun
declare -a _PL_M=("" "stycznia" "lutego" "marca" "kwietnia" "maja" "czerwca" "lipca" "sierpnia" "wrzesnia" "pazdziernika" "listopada" "grudnia")
declare -a _PL_D=("" "poniedzialek" "wtorek" "sroda" "czwartek" "piatek" "sobota" "niedziela")
_ZT_URL="https://www.zawodtyper.pl/typy-dnia-${_ZT_DAY}-${_PL_M[$_ZT_MONTH]}-${_PL_D[$_ZT_DOW]}/"
echo "[orchestrator] ZawodTyper URL: ${_ZT_URL}"

# Single source of truth: config/scan_urls.json
# Dynamic ZawodTyper URL appended via --urls (merged with --urls-file)
python3 "${SCRIPT_DIR}/scan_events.py" --deep --max-deep-links 30 --workers 8 \
  --urls-file "${ROOT_DIR}/config/scan_urls.json" \
  --urls "${_ZT_URL}" \
  || { echo "[ERROR] Scan finished with errors — check scan_errors.json"; ERRORS=$((ERRORS + 1)); }
SCAN_END=$(date +%s)
echo "[orchestrator] Scan took $((SCAN_END - SCAN_START)) seconds"

echo ""
echo "[6-8/14] Steps 6-8: Parallel enrichment (discover + stats + odds)..."

python3 "${SCRIPT_DIR}/discover_fixtures.py" --date "$(date '+%Y-%m-%d')" > /tmp/discover_$$.log 2>&1 &
PID_DISCOVER=$!

python3 "${SCRIPT_DIR}/fetch_api_stats.py" --date "$(date '+%Y-%m-%d')" > /tmp/stats_$$.log 2>&1 &
PID_STATS=$!

python3 "${SCRIPT_DIR}/fetch_odds_multi.py" > /tmp/odds_$$.log 2>&1 &
PID_ODDS=$!

# Wait for all and collect results
ENRICH_ERRORS=0

wait $PID_DISCOVER
if [ $? -ne 0 ]; then
    echo "[WARNING] discover_fixtures failed"
    cat /tmp/discover_$$.log
    ENRICH_ERRORS=$((ENRICH_ERRORS + 1))
else
    echo "[OK] discover_fixtures completed"
fi

wait $PID_STATS
if [ $? -ne 0 ]; then
    echo "[WARNING] fetch_api_stats failed"
    cat /tmp/stats_$$.log
    ENRICH_ERRORS=$((ENRICH_ERRORS + 1))
else
    echo "[OK] fetch_api_stats completed"
fi

wait $PID_ODDS
if [ $? -ne 0 ]; then
    echo "[WARNING] fetch_odds_multi failed"
    cat /tmp/odds_$$.log
    ENRICH_ERRORS=$((ENRICH_ERRORS + 1))
else
    echo "[OK] fetch_odds_multi completed"
fi

echo "Parallel enrichment: ${ENRICH_ERRORS} failures"

# Cleanup temp logs
rm -f /tmp/discover_$$.log /tmp/stats_$$.log /tmp/odds_$$.log

echo ""
echo "[8b/14] Ingesting Playwright scan data into stats_cache..."
python3 "${SCRIPT_DIR}/ingest_scan_stats.py" || echo "[WARNING] Scan data ingestion failed — continuing"

echo ""
echo "[9/14] Generating deep analysis pool..."
python3 "${SCRIPT_DIR}/deep_analysis_pool.py" --date "$(date '+%Y-%m-%d')" || echo "[WARNING] Analysis pool generation failed — continuing"

echo ""
echo "[10/14] Aggregating and selecting candidates..."
python3 "${SCRIPT_DIR}/aggregate_and_select.py" || { echo "[ERROR] Aggregation failed"; ERRORS=$((ERRORS + 1)); }

echo ""
echo "[11/14] Generating comprehensive market matrix (STATS-FIRST mode)..."
if [ -z "${PIPELINE_MANAGED:-}" ]; then
    python3 "${SCRIPT_DIR}/generate_market_matrix.py" --date "$(date '+%Y-%m-%d')" --stats-first || echo "[WARNING] Market matrix generation failed — continuing"
else
    echo "[SKIP] Managed by pipeline orchestrator (S1d)"
fi

echo ""
echo "[12b/14] Building ranked S2 shortlist from market matrix..."
if [ -z "${PIPELINE_MANAGED:-}" ]; then
    python3 "${SCRIPT_DIR}/build_shortlist.py" --date "$(date '+%Y-%m-%d')" --stats-first || echo "[WARNING] Shortlist generation failed — continuing"
else
    echo "[SKIP] Managed by pipeline orchestrator (S1e)"
fi

echo ""
echo "[13/14] Fetching weather data for outdoor fixtures..."
if [ -z "${PIPELINE_MANAGED:-}" ]; then
    python3 "${SCRIPT_DIR}/fetch_weather.py" --date "$(date '+%Y-%m-%d')" || echo "[WARNING] Weather fetch failed — continuing"
else
    echo "[SKIP] Managed by pipeline orchestrator (S1b)"
fi

echo ""
echo "[14/14] Summary..."
echo "============================================="
echo "[orchestrator] Pipeline complete"
echo "[orchestrator] Time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "============================================="
echo ""
echo "Outputs:"
for f in "${DATA_DIR}/scan_summary.json" "${DATA_DIR}/picks_suggested.json" "${DATA_DIR}/scan_errors.json" "${DATA_DIR}/betclic_verified_odds.json" "${DATA_DIR}/odds_api_snapshot.json" "${DATA_DIR}/odds_api_summary.csv" "${DATA_DIR}/odds_multi_sources.json" "${DATA_DIR}/analysis_pool_$(date '+%Y-%m-%d').json" "${DATA_DIR}/analysis_pool_$(date '+%Y-%m-%d').md" "${DATA_DIR}/market_matrix_$(date '+%Y-%m-%d').json" "${DATA_DIR}/market_matrix_$(date '+%Y-%m-%d').md" "${DATA_DIR}/decision_matrix_$(date '+%Y-%m-%d').md" "${DATA_DIR}/weather_$(date '+%Y-%m-%d').json"; do
    if [ -f "$f" ]; then
        echo "  [OK] $(basename "$f") ($(wc -c < "$f") bytes)"
    else
        echo "  [--] $(basename "$f") not created"
    fi
done

if [ $ERRORS -gt 0 ]; then
    echo "[FATAL] $ERRORS critical step(s) failed"
    exit 1
fi
