#!/usr/bin/env bash
# Canonical Rapid-MLX 0.7.0 launcher for Apple M4 Pro / 48 GB.
# It can be invoked from Fish because the shebang selects Bash.

set -Eeuo pipefail

EXPECTED_VERSION="${RAPID_MLX_EXPECTED_VERSION:-0.7.0}"
MODEL="${RAPID_MLX_MODEL:-qwen3.6-35b-4bit}"
HOST="${RAPID_MLX_HOST:-127.0.0.1}"
PORT="${RAPID_MLX_PORT:-8000}"
PROFILE="${RAPID_MLX_PROFILE:-production}"
ACTION="${1:-start}"
if [[ $# -gt 0 ]]; then shift; fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if PROJECT_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
  :
else
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi
RUNTIME_DIR="$PROJECT_ROOT/.kilo/runtime"
LOG_DIR="$PROJECT_ROOT/.kilo/logs"
PID_FILE="$RUNTIME_DIR/rapid-mlx-${PORT}.pid"
META_FILE="$RUNTIME_DIR/rapid-mlx-${PORT}.manifest.json"
MODELS_FILE="$RUNTIME_DIR/rapid-mlx-${PORT}.models.json"
MODEL_INFO_FILE="$RUNTIME_DIR/rapid-mlx-${PORT}.model-info.txt"
CURRENT_LOG="$LOG_DIR/rapid-mlx-${PORT}-current.log"
BASE_URL="http://${HOST}:${PORT}"

MAX_TOKENS=4096
PREFILL_STEP=2048
GPU_MEMORY=0.70
case "$PROFILE" in
  safe)       PREFILL_STEP=1024; GPU_MEMORY=0.66 ;;
  production) PREFILL_STEP=2048; GPU_MEMORY=0.70 ;;
  benchmark)  PREFILL_STEP=4096; GPU_MEMORY=0.74 ;;
  *) echo "ERROR: profile must be safe, production, or benchmark" >&2; exit 2 ;;
esac

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }
require() { command -v "$1" >/dev/null 2>&1 || die "missing command: $1"; }

find_rapid_mlx() {
  local candidates=()
  [[ -n "${RAPID_MLX_BIN:-}" ]] && candidates+=("$RAPID_MLX_BIN")
  candidates+=(
    "$HOME/.venvs/rapid-mlx-${EXPECTED_VERSION}/bin/rapid-mlx"
    "$PROJECT_ROOT/.venv-rapid/bin/rapid-mlx"
    "$HOME/.rapid-mlx/bin/rapid-mlx"
  )
  command -v rapid-mlx >/dev/null 2>&1 && candidates+=("$(command -v rapid-mlx)")
  local candidate
  for candidate in "${candidates[@]}"; do
    [[ -x "$candidate" ]] && { printf '%s\n' "$candidate"; return 0; }
  done
  return 1
}

RAPID_MLX="$(find_rapid_mlx || true)"
[[ -n "$RAPID_MLX" ]] || die "rapid-mlx not found; set RAPID_MLX_BIN explicitly"

rapid_version() {
  "$RAPID_MLX" --version 2>&1 | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1
}

check_version() {
  local actual
  actual="$(rapid_version)"
  [[ -n "$actual" ]] || die "unable to determine Rapid-MLX version from $RAPID_MLX"
  if [[ "$actual" != "$EXPECTED_VERSION" && "${RAPID_MLX_ALLOW_VERSION_DRIFT:-0}" != "1" ]]; then
    die "Rapid-MLX version drift: expected $EXPECTED_VERSION, got $actual. Set RAPID_MLX_ALLOW_VERSION_DRIFT=1 only for an explicit test."
  fi
}

listener_pid() { lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1 || true; }
pid_from_file() { [[ -r "$PID_FILE" ]] && tr -dc '0-9' < "$PID_FILE" || true; }
is_live() { [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; }
is_rapid() { [[ -n "${1:-}" ]] && ps -p "$1" -o command= 2>/dev/null | grep -q 'rapid-mlx.*serve'; }

health() {
  curl -fsS --max-time 15 "$BASE_URL/health" 2>/dev/null || curl -fsS --max-time 15 "$BASE_URL/v1/models"
}

wait_health() {
  local i
  for i in $(seq 1 180); do
    health >/dev/null 2>&1 && return 0
    is_live "$1" || return 1
    sleep 1
  done
  return 1
}

write_manifest() {
  local pid="$1" log_file="$2" actual_version chip memory_bytes os_version python_version kilo_version
  actual_version="$(rapid_version)"
  chip="$(sysctl -n machdep.cpu.brand_string 2>/dev/null || uname -m)"
  memory_bytes="$(sysctl -n hw.memsize 2>/dev/null || echo 0)"
  os_version="$(sw_vers -productVersion 2>/dev/null || uname -r)"
  python_version="$("$(dirname "$RAPID_MLX")/python" --version 2>&1 || true)"
  kilo_version="$(kilo --version 2>/dev/null || echo unavailable)"

  # Capture what the runtime actually served, not only what the launcher requested.
  curl -fsS --max-time 15 "$BASE_URL/v1/models" > "$MODELS_FILE" 2>/dev/null || printf '{"data":[]}\n' > "$MODELS_FILE"
  "$RAPID_MLX" info "$MODEL" > "$MODEL_INFO_FILE" 2>&1 || printf 'rapid-mlx info unavailable for %s\n' "$MODEL" > "$MODEL_INFO_FILE"

  jq -n \
    --slurpfile served_models "$MODELS_FILE" \
    --arg started_at "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
    --argjson pid "$pid" --arg model "$MODEL" --arg host "$HOST" --argjson port "$PORT" \
    --arg profile "$PROFILE" --arg rapid_mlx_bin "$RAPID_MLX" --arg rapid_mlx_version "$actual_version" \
    --arg chip "$chip" --arg memory_bytes "$memory_bytes" --arg macos "$os_version" \
    --arg python "$python_version" --arg kilo "$kilo_version" --arg log "$log_file" \
    --arg model_info_file "$MODEL_INFO_FILE" --arg served_models_file "$MODELS_FILE" \
    --argjson max_tokens "$MAX_TOKENS" --argjson prefill_step "$PREFILL_STEP" --argjson gpu_memory "$GPU_MEMORY" \
    '{started_at:$started_at,pid:$pid,requested_model:$model,served_models:$served_models[0],endpoint:("http://"+$host+":"+($port|tostring)+"/v1"),profile:$profile,rapid_mlx:{binary:$rapid_mlx_bin,version:$rapid_mlx_version,model_info_file:$model_info_file,served_models_file:$served_models_file},host:{chip:$chip,memory_bytes:$memory_bytes,macos:$macos,python:$python,kilo:$kilo},settings:{max_tokens:$max_tokens,prefill_step_size:$prefill_step,gpu_memory_utilization:$gpu_memory,kv_cache_quantization:true,multimodal:false,telemetry:false},log:$log}' > "$META_FILE"
}

start_server() {
  require curl; require jq; require lsof; require nohup
  check_version
  mkdir -p "$RUNTIME_DIR" "$LOG_DIR"
  local existing
  existing="$(listener_pid)"
  if [[ -n "$existing" ]]; then
    is_rapid "$existing" && die "Rapid-MLX already listens on port $PORT (PID $existing)" || die "port $PORT is occupied by non-Rapid process PID $existing"
  fi

  local stamp log_file pid
  stamp="$(date '+%Y%m%d-%H%M%S')"
  log_file="$LOG_DIR/rapid-mlx-${PORT}-${stamp}.log"
  ln -sfn "$(basename "$log_file")" "$CURRENT_LOG"

  export RAPID_MLX_TELEMETRY=0
  log "starting Rapid-MLX $EXPECTED_VERSION model=$MODEL profile=$PROFILE prefill=$PREFILL_STEP gpu=$GPU_MEMORY"
  nohup "$RAPID_MLX" --no-telemetry serve "$MODEL" \
    --host "$HOST" --port "$PORT" \
    --max-tokens "$MAX_TOKENS" \
    --prefill-step-size "$PREFILL_STEP" \
    --gpu-memory-utilization "$GPU_MEMORY" \
    --kv-cache-quantization \
    --enable-prefix-cache \
    --no-mllm \
    --rate-limit 30 \
    --timeout 1800 \
    >"$log_file" 2>&1 &
  pid=$!
  printf '%s\n' "$pid" > "$PID_FILE"

  if ! wait_health "$pid"; then
    tail -80 "$log_file" || true
    kill "$pid" 2>/dev/null || true
    rm -f "$PID_FILE"
    die "server did not become healthy"
  fi

  write_manifest "$pid" "$log_file"
  log "ready PID=$pid endpoint=$BASE_URL/v1 log=$log_file"
}

stop_server() {
  local pid
  pid="$(pid_from_file)"
  [[ -z "$pid" ]] && pid="$(listener_pid)"
  [[ -z "$pid" ]] && { log "already stopped"; rm -f "$PID_FILE"; return 0; }
  is_rapid "$pid" || die "refusing to stop non-Rapid PID $pid"
  kill "$pid" 2>/dev/null || true
  local i
  for i in $(seq 1 30); do
    is_live "$pid" || { rm -f "$PID_FILE"; log "stopped PID=$pid"; return 0; }
    sleep 1
  done
  kill -KILL "$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
  log "force-stopped PID=$pid"
}

post_json() {
  curl -fsS --max-time "${2:-600}" "$BASE_URL/v1/chat/completions" \
    -H 'Content-Type: application/json' --data-binary "$1"
}

smoke() {
  local body
  body="$(post_json '{"model":"default","messages":[{"role":"user","content":"Reply with exactly RAPID_MLX_OK."}],"temperature":0,"max_tokens":64,"stream":false}' 240)"
  jq -e '.choices[0].message.content | contains("RAPID_MLX_OK")' <<<"$body" >/dev/null || { jq . <<<"$body"; die "chat smoke failed"; }
  log "chat smoke: PASS"
}

tool_smoke() {
  local body
  body="$(post_json '{"model":"default","messages":[{"role":"user","content":"Call probe_status with target rapid-mlx. Do not answer directly."}],"tools":[{"type":"function","function":{"name":"probe_status","description":"Probe status","parameters":{"type":"object","properties":{"target":{"type":"string"}},"required":["target"],"additionalProperties":false}}}],"tool_choice":"required","temperature":0,"max_tokens":512,"stream":false}' 300)"
  jq -e '.choices[0].message.tool_calls[0].function.name == "probe_status"' <<<"$body" >/dev/null || { jq . <<<"$body"; die "tool smoke failed"; }
  log "single-tool smoke: PASS"
}

multitool_smoke() {
  local body
  body="$(post_json '{"model":"default","messages":[{"role":"user","content":"Call probe_alpha with value 11 and probe_beta with value 22. Use both tools and do not answer directly."}],"tools":[{"type":"function","function":{"name":"probe_alpha","description":"First probe","parameters":{"type":"object","properties":{"value":{"type":"integer"}},"required":["value"],"additionalProperties":false}}},{"type":"function","function":{"name":"probe_beta","description":"Second probe","parameters":{"type":"object","properties":{"value":{"type":"integer"}},"required":["value"],"additionalProperties":false}}}],"tool_choice":"required","temperature":0,"max_tokens":768,"stream":false}' 300)"
  jq -e '[.choices[0].message.tool_calls[]?.function.name] | (index("probe_alpha") != null and index("probe_beta") != null)' <<<"$body" >/dev/null || { jq . <<<"$body"; die "multi-tool smoke failed"; }
  log "multi-tool smoke: PASS"
}

stream_smoke() {
  local tmp
  tmp="$(mktemp)"
  curl -fsSN --max-time 300 "$BASE_URL/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d '{"model":"default","messages":[{"role":"user","content":"Reply with exactly STREAM_OK."}],"temperature":0,"max_tokens":64,"stream":true}' > "$tmp"
  grep -q 'STREAM_OK' "$tmp" || { tail -30 "$tmp"; rm -f "$tmp"; die "stream smoke failed"; }
  grep -q '\[DONE\]' "$tmp" || { tail -30 "$tmp"; rm -f "$tmp"; die "stream did not terminate cleanly"; }
  rm -f "$tmp"
  log "stream smoke: PASS"
}

context_smoke() {
  require python3
  local tmp request response
  tmp="$(mktemp -d)"
  request="$tmp/request.json"
  response="$tmp/response.json"
  python3 - "$request" <<'PY_CONTEXT'
import json, sys
block = "Bounded long-context probe. Preserve marker ALPHA-947. " * 5000
with open(sys.argv[1], "w") as f:
    json.dump({
        "model": "default",
        "messages": [
            {"role": "system", "content": "Answer concisely."},
            {"role": "user", "content": block + "\nReturn the marker."},
        ],
        "temperature": 0,
        "max_tokens": 64,
        "stream": False,
    }, f)
PY_CONTEXT
  curl -fsS --max-time 900 "$BASE_URL/v1/chat/completions" \
    -H 'Content-Type: application/json' --data-binary "@$request" > "$response"
  jq -e '.choices[0].message.content | contains("ALPHA-947")' "$response" >/dev/null || { jq . "$response"; rm -rf "$tmp"; die "context smoke failed"; }
  rm -rf "$tmp"
  log "bounded-context smoke: PASS"
}

status_server() {
  local pid
  pid="$(pid_from_file)"
  if is_live "$pid" && is_rapid "$pid"; then
    log "running PID=$pid endpoint=$BASE_URL/v1"
    health | jq .
    return 0
  fi
  log "stopped"
  return 3
}

usage() {
  cat <<EOF
Usage: $0 <start|stop|restart|status|health|smoke|tool-smoke|multitool-smoke|stream-smoke|context-smoke|doctor|manifest|model-info|logs>
Environment: RAPID_MLX_BIN, RAPID_MLX_PROFILE=safe|production|benchmark, RAPID_MLX_MODEL, RAPID_MLX_PORT
EOF
}

require curl
require jq
require lsof
case "$ACTION" in
  start) start_server ;;
  stop) stop_server ;;
  restart) stop_server; start_server ;;
  status) status_server ;;
  health) health | jq . ;;
  smoke) smoke ;;
  tool-smoke) tool_smoke ;;
  multitool-smoke) multitool_smoke ;;
  stream-smoke) stream_smoke ;;
  context-smoke) context_smoke ;;
  doctor) check_version; "$RAPID_MLX" doctor ;;
  manifest) [[ -r "$META_FILE" ]] && jq . "$META_FILE" || die "manifest not found" ;;
  logs) [[ -e "$CURRENT_LOG" ]] && tail -f "$CURRENT_LOG" || die "current log not found" ;;
  help|-h|--help) usage ;;
  *) usage; exit 2 ;;
esac
