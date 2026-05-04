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

# URLs include: Flashscore (all sports + exotic football regions),
# Sofascore, Betclic, OddsPortal, BetExplorer, specialist sources,
# tipster sites, and Soccerway (exotic league coverage).
#
# URLs are also loadable from config/scan_urls.json via:
#   python3 scripts/scan_events.py --urls-file config/scan_urls.json --deep --workers 6
#
# Section breakdown:
# - Flashscore main sport hubs (13 sports)
# - Flashscore Football — European 2nd tier (30)
# - Flashscore Football — Americas, Asia, Africa (40)
# - Flashscore Women's football (5)
# - Flashscore Tennis/Basketball/Volleyball/Handball/Esports deep pages
# - Soccerway, Sofascore
# - Betclic (14 sport categories)
# - OddsPortal (5 sport hubs)
# - BetExplorer (8 sport categories + speedway)
# - Specialist sources (sport-specific)
# - Statistical / corners / advanced stats
# - Tipster / prediction sites
python3 "${SCRIPT_DIR}/scan_events.py" --deep --max-deep-links 50 --urls \
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
  https://www.flashscore.com/football/poland/ \
  https://www.flashscore.com/football/poland/2-liga/ \
  https://www.flashscore.com/football/romania/ \
  https://www.flashscore.com/football/serbia/ \
  https://www.flashscore.com/football/croatia/ \
  https://www.flashscore.com/football/hungary/ \
  https://www.flashscore.com/football/czech-republic/ \
  https://www.flashscore.com/football/slovakia/ \
  https://www.flashscore.com/football/ukraine/ \
  https://www.flashscore.com/football/bulgaria/ \
  https://www.flashscore.com/football/cyprus/ \
  https://www.flashscore.com/football/iceland/ \
  https://www.flashscore.com/football/finland/ \
  https://www.flashscore.com/football/norway/ \
  https://www.flashscore.com/football/sweden/ \
  https://www.flashscore.com/football/denmark/ \
  https://www.flashscore.com/football/switzerland/ \
  https://www.flashscore.com/football/austria/ \
  https://www.flashscore.com/football/greece/ \
  https://www.flashscore.com/football/scotland/ \
  https://www.flashscore.com/football/belgium/ \
  https://www.flashscore.com/football/netherlands/ \
  https://www.flashscore.com/football/turkey/ \
  https://www.flashscore.com/football/england/championship/ \
  https://www.flashscore.com/football/england/league-one/ \
  https://www.flashscore.com/football/germany/2-bundesliga/ \
  https://www.flashscore.com/football/italy/serie-b/ \
  https://www.flashscore.com/football/france/ligue-2/ \
  https://www.flashscore.com/football/spain/laliga2/ \
  https://www.flashscore.com/football/portugal/ \
  https://www.flashscore.com/football/brazil/ \
  https://www.flashscore.com/football/argentina/ \
  https://www.flashscore.com/football/uruguay/ \
  https://www.flashscore.com/football/mexico/ \
  https://www.flashscore.com/football/usa/ \
  https://www.flashscore.com/football/japan/ \
  https://www.flashscore.com/football/south-korea/ \
  https://www.flashscore.com/football/china/ \
  https://www.flashscore.com/football/indonesia/ \
  https://www.flashscore.com/football/australia/ \
  https://www.flashscore.com/football/south-africa/ \
  https://www.flashscore.com/football/nigeria/ \
  https://www.flashscore.com/football/ghana/ \
  https://www.flashscore.com/football/kenya/ \
  https://www.flashscore.com/football/tunisia/ \
  https://www.flashscore.com/football/cameroon/ \
  https://www.flashscore.com/football/senegal/ \
  https://www.flashscore.com/football/bolivia/ \
  https://www.flashscore.com/football/venezuela/ \
  https://www.flashscore.com/football/honduras/ \
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
  https://www.flashscore.com/football/europe/champions-league-women/ \
  https://www.flashscore.com/football/england/wsl-women/ \
  https://www.flashscore.com/football/spain/liga-f-women/ \
  https://www.flashscore.com/football/usa/nwsl-women/ \
  https://www.flashscore.com/football/france/division-1-women/ \
  https://www.flashscore.com/tennis/atp-singles/ \
  https://www.flashscore.com/tennis/wta-singles/ \
  https://www.flashscore.com/tennis/atp-doubles/ \
  https://www.flashscore.com/basketball/europe/euroleague/ \
  https://www.flashscore.com/basketball/europe/eurocup/ \
  https://www.flashscore.com/basketball/spain/acb/ \
  https://www.flashscore.com/basketball/poland/plk/ \
  https://www.flashscore.com/basketball/turkey/bsl/ \
  https://www.flashscore.com/volleyball/poland/plusliga/ \
  https://www.flashscore.com/volleyball/italy/superlega/ \
  https://www.flashscore.com/volleyball/france/ligue-a/ \
  https://www.flashscore.com/volleyball/europe/champions-league/ \
  https://www.flashscore.com/volleyball/brazil/superliga/ \
  https://www.flashscore.com/handball/europe/champions-league/ \
  https://www.flashscore.com/handball/germany/bundesliga/ \
  https://www.flashscore.com/handball/france/starligue/ \
  https://www.flashscore.com/esports/counter-strike/ \
  https://www.flashscore.com/darts/pdc/ \
  https://www.flashscore.com/mma/ufc/ \
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
  https://www.tennisexplorer.com/ \
  https://www.tennisexplorer.com/matches/ \
  https://www.tennisabstract.com/reports/wta_elo_ratings.html \
  https://www.tennisabstract.com/reports/atp_elo_ratings.html \
  https://www.atptour.com/en/scores/current \
  https://dartsorakel.com/ \
  https://cuetracker.net/ \
  https://www.hltv.org/matches \
  https://www.gosugamers.net/ \
  https://www.basketball-reference.com/ \
  https://www.hockey-reference.com/ \
  https://www.soccerstats.com/ \
  https://totalcorner.com/ \
  https://totalcorner.com/match/today \
  https://www.forebet.com/en/football-tips-and-predictions-for-today \
  https://www.forebet.com/en/tennis/predictions-today \
  https://www.forebet.com/en/basketball/predictions-today \
  https://www.forebet.com/en/hockey/predictions-today \
  https://www.forebet.com/en/handball/predictions-today \
  https://www.forebet.com/en/volleyball/predictions-today \
  https://scores24.live/en/soccer \
  https://scores24.live/en/tennis \
  https://scores24.live/en/basketball \
  https://scores24.live/en/ice-hockey \
  https://scores24.live/en/handball \
  https://scores24.live/en/volleyball \
  https://scores24.live/en/baseball \
  https://scores24.live/en/snooker \
  https://scores24.live/en/darts \
  https://scores24.live/en/table-tennis \
  https://scores24.live/en/mma \
  https://scores24.live/en/csgo \
  https://scores24.live/en/american-football \
  https://scores24.live/en/cricket \
  https://scores24.live/en/rugby \
  https://scores24.live/en/badminton \
  https://scores24.live/en/boxing \
  https://scores24.live/en/futsal \
  https://www.covers.com/ \
  https://www.teamrankings.com/ \
  https://www.sportsgambler.com/predictions/today/ \
  https://www.betideas.com/ \
  https://www.pickswise.com/ \
  https://www.betaminic.com/ \
  https://www.zawodtyper.pl/ \
  "${_ZT_URL}" \
  https://typersi.pl/ \
  https://www.feedinco.com/ \
  https://www.bettingclosed.com/ \
  https://tips180.com/ \
  https://www.tipstrr.com/tips \
  https://www.whoscored.com/Previews \
  || echo "[WARNING] Scan finished with errors — check scan_errors.json"
SCAN_END=$(date +%s)
echo "[orchestrator] Scan took $((SCAN_END - SCAN_START)) seconds"

echo ""
echo "[6/14] Discovering fixtures via APIs..."
python3 "${SCRIPT_DIR}/discover_fixtures.py" --date "$(date '+%Y-%m-%d')" || echo "[WARNING] API fixture discovery failed — continuing with scan results only"

echo ""
echo "[7/14] Fetching statistics from APIs..."
python3 "${SCRIPT_DIR}/fetch_api_stats.py" --date "$(date '+%Y-%m-%d')" || echo "[WARNING] API stats fetch failed — continuing with existing data"

echo ""
echo "[8/14] Fetching multi-source odds..."
python3 "${SCRIPT_DIR}/fetch_odds_multi.py" || echo "[WARNING] Multi-source odds fetch failed — run fetch_odds_api.py manually"

echo ""
echo "[9/14] Generating deep analysis pool..."
python3 "${SCRIPT_DIR}/deep_analysis_pool.py" --date "$(date '+%Y-%m-%d')" || echo "[WARNING] Analysis pool generation failed — continuing"

echo ""
echo "[10/14] Aggregating and selecting candidates..."
python3 "${SCRIPT_DIR}/aggregate_and_select.py"

echo ""
echo "[11/14] Generating comprehensive market matrix (STATS-FIRST mode)..."
python3 "${SCRIPT_DIR}/generate_market_matrix.py" --date "$(date '+%Y-%m-%d')" --stats-first || echo "[WARNING] Market matrix generation failed — continuing"

echo ""
echo "[12b/14] Building ranked S2 shortlist from market matrix..."
python3 "${SCRIPT_DIR}/build_shortlist.py" --date "$(date '+%Y-%m-%d')" --top 100 --stats-first || echo "[WARNING] Shortlist generation failed — continuing"

echo ""
echo "[13/14] Fetching weather data for outdoor fixtures..."
python3 "${SCRIPT_DIR}/fetch_weather.py" --date "$(date '+%Y-%m-%d')" || echo "[WARNING] Weather fetch failed — continuing"

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
