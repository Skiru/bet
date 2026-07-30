#!/usr/bin/zsh
set -euo pipefail

# 1. Verify preflight baseline
echo "=== PREFLIGHT BASELINE VERIFICATION ==="
ACTUAL_HEAD="$(git rev-parse HEAD)"
ACTUAL_TREE="$(git rev-parse HEAD^{tree})"
ACTUAL_MANIFEST="$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "from bet.pipeline.receipts import compute_source_manifest_sha256; from pathlib import Path; print(compute_source_manifest_sha256(Path('.')))")"

EXPECTED_HEAD="${EXPECTED_HEAD:-20ee2145a82e9b88cf1e4a64a38d2f1d248b9487}"
EXPECTED_TREE="${EXPECTED_TREE:-8ba53fe9520cb95dfd0c15ebc22d1cc3efdcae1c}"
EXPECTED_SOURCE_MANIFEST_SHA256="${EXPECTED_SOURCE_MANIFEST_SHA256:-b2a2f65109ecf5f6bd54a5c531d0ebbbbd3fa96df990e668c2dd04fead45d7b5}"

[[ "$ACTUAL_HEAD" == "$EXPECTED_HEAD" ]] || { echo "FATAL: HEAD mismatch"; exit 1; }
[[ "$ACTUAL_TREE" == "$EXPECTED_TREE" ]] || { echo "FATAL: TREE mismatch"; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "FATAL: Worktree not clean"; exit 1; }
[[ "$ACTUAL_MANIFEST" == "$EXPECTED_SOURCE_MANIFEST_SHA256" ]] || { echo "FATAL: Source manifest mismatch"; exit 1; }

echo "Baseline verification passed: HEAD=${ACTUAL_HEAD[:10]}, TREE=${ACTUAL_TREE[:10]}, MANIFEST=${ACTUAL_MANIFEST[:10]}"

export BET_PIPELINE_LIVE_ACK=I_UNDERSTAND_LIVE_PROVIDER_CALLS

# 2. Allocate Europe/Warsaw date and run ID
BETTING_DATE="$(TZ=Europe/Warsaw date +%F)"
RUN_ID="RUN_$(TZ=Europe/Warsaw date +%Y%m%dT%H%M%SZ)"
BASE_RUN_DIR="reports/pipeline_runs"
RUN_ROOT="${BASE_RUN_DIR}/${BETTING_DATE}/${RUN_ID}"

echo "Allocated RUN_ID=${RUN_ID} for Europe/Warsaw date ${BETTING_DATE}"

# 3. Step 1: Run Live Plan Pass
echo "=== STEP 1: RUNNING LIVE PLAN PASS ==="
env PYTHONPATH=src:scripts .venv/bin/python3 scripts/pipeline_steps/run_daily_pipeline.py \
  --date "${BETTING_DATE}" \
  --run-id "${RUN_ID}" \
  --runtime-mode LIVE_ANALYSIS_SHADOW \
  --plan-only \
  --allow-live-network \
  --allow-write \
  --base-run-dir "${BASE_RUN_DIR}"

PLAN_CP_FILE="${RUN_ROOT}/artifacts/plan_checkpoint.json"
if [ ! -f "${PLAN_CP_FILE}" ]; then
  echo "FATAL: plan_checkpoint.json not found at ${PLAN_CP_FILE}"
  exit 1
fi

PLAN_STATUS=$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "import json; print(json.load(open('${PLAN_CP_FILE}'))['PLAN_STATUS'])")
READY_FOR_SESSION=$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "import json; print(json.load(open('${PLAN_CP_FILE}'))['READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION'])")
ANALYZE_FROM_S2=$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "import json; print(json.load(open('${PLAN_CP_FILE}'))['ANALYZE_FROM_S2'])")
PROVIDER_REVALIDATED=$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "import json; print(json.load(open('${PLAN_CP_FILE}'))['PROVIDER_REVALIDATED'])")
UNVERIFIED_SELECTED=$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "import json; print(json.load(open('${PLAN_CP_FILE}'))['SELECTED_EVENTS_WITHOUT_PROVIDER_SUCCESS'])")
EVENT_ACCOUNTING_EXACT=$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "import json; print(json.load(open('${PLAN_CP_FILE}'))['EVENT_ACCOUNTING_EXACT'])")
RUNTIME_S1E_MATCH=$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "import json; print(json.load(open('${PLAN_CP_FILE}'))['RUNTIME_S1E_SELECTION_MATCH'])")
SEL_LEDGER_SHA=$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "import json; print(json.load(open('${PLAN_CP_FILE}'))['SELECTION_LEDGER_SHA256'])")

SHADOW_DB_PATH="${RUN_ROOT}/data/runtime_analysis_shadow.db"
PLAN_CP_SHA=$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "import hashlib; print(hashlib.sha256(open('${PLAN_CP_FILE}', 'rb').read()).hexdigest())")
PROV_OBS_SHA=$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "import hashlib, os; p='${RUN_ROOT}/artifacts/provider_revalidation_ledger.json'; print(hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else '')")
S1E_SHA=$(env PYTHONPATH=src:scripts .venv/bin/python3 -c "import hashlib, os; p='${RUN_ROOT}/artifacts/S1e.json'; print(hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else '')")

echo "PLAN_STATUS=${PLAN_STATUS}"
echo "READY_FOR_SESSION=${READY_FOR_SESSION}"
echo "ANALYZE_FROM_S2=${ANALYZE_FROM_S2}"
echo "PROVIDER_REVALIDATED=${PROVIDER_REVALIDATED}"
echo "UNVERIFIED_SELECTED=${UNVERIFIED_SELECTED}"
echo "EVENT_ACCOUNTING_EXACT=${EVENT_ACCOUNTING_EXACT}"
echo "RUNTIME_S1E_MATCH=${RUNTIME_S1E_MATCH}"
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

if [ "${PROVIDER_REVALIDATED}" -le 0 ]; then
  echo "FATAL: PROVIDER_REVALIDATED <= 0"
  exit 1
fi

if [ "${UNVERIFIED_SELECTED}" -ne 0 ]; then
  echo "FATAL: SELECTED_EVENTS_WITHOUT_PROVIDER_SUCCESS is not 0"
  exit 1
fi

if [ "${EVENT_ACCOUNTING_EXACT}" != "YES" ]; then
  echo "FATAL: EVENT_ACCOUNTING_EXACT is not YES"
  exit 1
fi

if [ "${RUNTIME_S1E_MATCH}" != "YES" ]; then
  echo "FATAL: RUNTIME_S1E_SELECTION_MATCH is not YES"
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
