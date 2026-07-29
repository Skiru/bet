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

run_gate 120 01-validators python3 scripts/validate_production_surface.py
run_gate 300 02-certifier python3 scripts/certify_pipeline_final_closure.py --output /tmp/pipeline_cert.json
run_gate 600 03-pytest pytest tests/security/ tests/integration/

echo "ALL PRODUCTION GATES PASSED"
echo "Reports: $OUT"
