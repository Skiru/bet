#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
  :
else
  ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi
STAMP="$(date '+%Y%m%d-%H%M%S')"
OUT="$ROOT/reports/prod-check-$STAMP"
RUN_TIMEOUT="$SCRIPT_DIR/run_with_timeout.py"
mkdir -p "$OUT"
cd "$ROOT"

run_gate() {
  local seconds="$1"
  local name="$2"
  shift 2
  echo "== $name =="
  if "$RUN_TIMEOUT" --seconds "$seconds" --output "$OUT/$name.log" -- "$@"; then
    echo "PASS $name"
  else
    echo "FAIL $name (see $OUT/$name.log)"
    tail -40 "$OUT/$name.log"
    exit 1
  fi
}

command -v kilo >/dev/null || {
  echo "kilo CLI missing: npm install -g @kilocode/cli"
  exit 1
}
EXPECTED_KILO_VERSION="${KILO_EXPECTED_VERSION:-7.3.41}"
ACTUAL_KILO_VERSION="$(kilo --version 2>&1 | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
if [[ "$ACTUAL_KILO_VERSION" != "$EXPECTED_KILO_VERSION" && "${KILO_ALLOW_VERSION_DRIFT:-0}" != "1" ]]; then
  echo "Kilo version drift: expected $EXPECTED_KILO_VERSION, got ${ACTUAL_KILO_VERSION:-unknown}"
  exit 1
fi

run_gate 30 01-rapid-health ./scripts/local-llm.sh health
run_gate 300 02-rapid-chat ./scripts/local-llm.sh smoke
run_gate 360 03-rapid-tool ./scripts/local-llm.sh tool-smoke
run_gate 360 04-rapid-multitool ./scripts/local-llm.sh multitool-smoke
run_gate 360 05-rapid-stream ./scripts/local-llm.sh stream-smoke
run_gate 960 06-rapid-context ./scripts/local-llm.sh context-smoke
run_gate 120 07-kilo-config kilo config check
run_gate 120 08-kilo-debug-config kilo debug config
run_gate 120 09-kilo-debug-agent kilo debug agent bet-orchestrator
run_gate 120 10-kilo-debug-skills kilo debug skill
run_gate 120 11-kilo-mcp-list kilo mcp list
run_gate 300 12-kilo-roll-call kilo roll-call '^openai-compatible/qwen36-local-35b$' --parallel 1 --timeout 180000 --output json
run_gate 180 13-kilo-sqlite-tool kilo debug agent bet-db-analyst --tool bet_sqlite_query --params '{"sql":"SELECT 1 AS ok","limit":5}'
run_gate 1800 14-kilo-e2e ./scripts/kilo_e2e_soak.py --turns 8 --report "$OUT/kilo-e2e.json"
run_gate 1800 15-kilo-context-guard ./scripts/kilo_context_guard_test.py --report "$OUT/kilo-context-guard.json"

echo "ALL PRODUCTION GATES PASSED"
echo "Reports: $OUT"
