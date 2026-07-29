#!/usr/bin/zsh
set -euo pipefail

# 1. Verify preflight baseline
echo "=== PREFLIGHT VERIFICATION ==="
export BET_PIPELINE_LIVE_ACK=I_UNDERSTAND_LIVE_PROVIDER_CALLS

env PYTHONPATH=src:scripts .venv/bin/python3 -c "
from bet.pipeline.launch_bridge import verify_canonical_db_and_preflight
from pathlib import Path
pre = verify_canonical_db_and_preflight(Path('.'), enforce_baseline=False)
print(f'HEAD={pre.head_sha}')
print(f'TREE={pre.tree_sha}')
print(f'MANIFEST={pre.source_manifest_sha256}')
print(f'WORKTREE_CLEAN={pre.worktree_clean}')
print(f'QUICK_CHECK={pre.quick_check_passed}')
assert pre.quick_check_passed, 'Canonical DB quick_check failed'
"

# 2. Allocate collision-free run ID and date
BETTING_DATE=$(date -u +%Y-%m-%d)
RUN_ID="RUN_$(date -u +%Y%m%dT%H%M%SZ)"
BASE_RUN_DIR="reports/pipeline_runs"
RUN_ROOT="${BASE_RUN_DIR}/${BETTING_DATE}/${RUN_ID}"

echo "Allocated RUN_ID=${RUN_ID} for date ${BETTING_DATE}"

# 3. Step 1: Run Live Plan Pass
echo "=== STEP 1: RUNNING LIVE PLAN PASS ==="
env PYTHONPATH=src:scripts .venv/bin/python3 scripts/pipeline_steps/run_daily_pipeline.py \
  --date "${BETTING_DATE}" \
  --run-id "${RUN_ID}" \
  --runtime-mode LIVE_ANALYSIS_SHADOW \
  --plan-only \
  --allow-live-network \
  --allow-write \
  --base-run-dir "${BASE_RUN_DIR}" > /tmp/plan_output.txt 2>&1 || true

cat /tmp/plan_output.txt

# Parse plan outputs
PLAN_CP_FILE="${RUN_ROOT}/artifacts/plan_checkpoint.json"
if [ ! -f "${PLAN_CP_FILE}" ]; then
  echo "FATAL: plan_checkpoint.json not found at ${PLAN_CP_FILE}"
  exit 1
fi

PLAN_STATUS=$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "import json; print(json.load(open('${PLAN_CP_FILE}'))['PLAN_STATUS'])")
READY_FOR_SESSION=$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "import json; print(json.load(open('${PLAN_CP_FILE}'))['READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION'])")
ANALYZE_FROM_S2=$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "import json; print(json.load(open('${PLAN_CP_FILE}'))['ANALYZE_FROM_S2'])")
PROVIDER_REVALIDATED=$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "import json; print(json.load(open('${PLAN_CP_FILE}'))['PROVIDER_REVALIDATED'])")
SEL_LEDGER_SHA=$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "import json; print(json.load(open('${PLAN_CP_FILE}'))['SELECTION_LEDGER_SHA256'])")

echo "PLAN_STATUS=${PLAN_STATUS}"
echo "READY_FOR_SESSION=${READY_FOR_SESSION}"
echo "ANALYZE_FROM_S2=${ANALYZE_FROM_S2}"
echo "PROVIDER_REVALIDATED=${PROVIDER_REVALIDATED}"
echo "SELECTION_LEDGER_SHA256=${SEL_LEDGER_SHA}"

if [ "${PLAN_STATUS}" != "PASS" ]; then
  echo "FATAL: Plan status is not PASS"
  exit 1
fi

if [ "${READY_FOR_SESSION}" != "YES" ]; then
  echo "FATAL: READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION is not YES"
  exit 1
fi

if [ "${ANALYZE_FROM_S2}" -le 0 ]; then
  echo "FATAL: ANALYZE_FROM_S2 <= 0"
  exit 1
fi

# 4. Step 2: Run S2-S8 Continuation Pass
echo "=== STEP 2: RUNNING S2-S8 CONTINUATION PASS ==="
env PYTHONPATH=src:scripts .venv/bin/python3 scripts/pipeline_steps/run_daily_pipeline.py \
  --date "${BETTING_DATE}" \
  --run-id "${RUN_ID}" \
  --runtime-mode LIVE_ANALYSIS_SHADOW \
  --execute-existing-plan \
  --plan-checkpoint "${PLAN_CP_FILE}" \
  --selection-ledger-sha256 "${SEL_LEDGER_SHA}" \
  --start-step S2 \
  --stop-after-step S8 \
  --allow-live-network \
  --allow-write \
  --base-run-dir "${BASE_RUN_DIR}"

echo "=== S2-S8 EXECUTION COMPLETED SUCCESSFULLY ==="
echo "S9 mode remains HUMAN_ONLY. No automated bet placement or bookmaker login performed."
