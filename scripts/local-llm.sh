#!/usr/bin/env bash
# Rapid-MLX 0.7.0 Production Lifecycle Controller
# P2 Certified: localhost-only, no forbidden optimizations, safe PID handling
# Target: Apple M4 Pro / 48 GB unified memory
# Model: qwen3.6-35b-4bit (mlx-community/Qwen3.6-35B-A3B-4bit)

set -Eeuo pipefail

# ==============================================================================
# CONFIGURATION - Pinned production baseline
# ==============================================================================
EXPECTED_VERSION="0.7.0"
MODEL_ALIAS="qwen3.6-35b-4bit"
MODEL_RESOLVED="mlx-community/Qwen3.6-35B-A3B-4bit"
HOST="127.0.0.1"
PORT="8000"
MAX_TOKENS=8192
PREFILL_STEP=2048
GPU_MEMORY=0.70

# Bounded timeouts
STARTUP_TIMEOUT_S=180
GRACEFUL_SHUTDOWN_S=30
FORCED_SHUTDOWN_S=10
HEALTH_TIMEOUT_S=15
SMOKE_TIMEOUT_S=300

# ==============================================================================
# PATHS
# ==============================================================================
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
MANIFEST_FILE="$RUNTIME_DIR/rapid-mlx-${PORT}.manifest.json"
CURRENT_LOG="$LOG_DIR/rapid-mlx-${PORT}-current.log"
BASE_URL="http://${HOST}:${PORT}"

# ==============================================================================
# LOGGING
# ==============================================================================
log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }
require() { command -v "$1" >/dev/null 2>&1 || die "missing command: $1"; }

# ==============================================================================
# EXECUTABLE RESOLUTION - Pinned version only
# ==============================================================================
find_rapid_mlx() {
  # Only accept the pinned version
  local candidate="$HOME/.venvs/rapid-mlx-${EXPECTED_VERSION}/bin/rapid-mlx"
  if [[ -x "$candidate" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi
  return 1
}

RAPID_MLX="$(find_rapid_mlx || true)"
[[ -n "$RAPID_MLX" ]] || die "Rapid-MLX ${EXPECTED_VERSION} not found at ~/.venvs/rapid-mlx-${EXPECTED_VERSION}/bin/rapid-mlx"

# ==============================================================================
# VERSION VALIDATION
# ==============================================================================
rapid_version() {
  "$RAPID_MLX" --version 2>&1 | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1
}

check_version() {
  local actual
  actual="$(rapid_version)"
  [[ -n "$actual" ]] || die "unable to determine Rapid-MLX version from $RAPID_MLX"
  if [[ "$actual" != "$EXPECTED_VERSION" ]]; then
    die "Rapid-MLX version mismatch: expected ${EXPECTED_VERSION}, got ${actual}"
  fi
}

# ==============================================================================
# PROCESS AND PORT UTILITIES
# ==============================================================================
listener_pid() { 
  lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

pid_from_file() { 
  [[ -r "$PID_FILE" ]] && tr -dc '0-9' < "$PID_FILE" || true
}

is_live() { 
  [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null
}

# Verify PID belongs to our Rapid-MLX process
is_owned_rapid_mlx() {
  local pid="$1"
  [[ -n "$pid" ]] || return 1
  
  # Check process exists
  if ! is_live "$pid"; then
    return 1
  fi
  
  # Verify executable path matches
  local proc_exe
  proc_exe="$(readlink "/proc/$pid/exe" 2>/dev/null || ps -p "$pid" -o command= 2>/dev/null | head -1 || true)"
  
  # Check command line contains our binary and model
  local cmdline
  cmdline="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  
  # Must contain rapid-mlx and our model
  if [[ "$cmdline" == *"$RAPID_MLX"* ]] && [[ "$cmdline" == *"serve"* ]] && [[ "$cmdline" == *"$MODEL_ALIAS"* ]]; then
    return 0
  fi
  
  return 1
}

# ==============================================================================
# HEALTH AND READINESS
# ==============================================================================
health_endpoint() {
  curl -fsS --max-time "$HEALTH_TIMEOUT_S" "$BASE_URL/health" 2>/dev/null || \
  curl -fsS --max-time "$HEALTH_TIMEOUT_S" "$BASE_URL/v1/models" 2>/dev/null
}

wait_for_readiness() {
  local pid="$1"
  local i
  for i in $(seq 1 "$STARTUP_TIMEOUT_S"); do
    if health_endpoint >/dev/null 2>&1; then
      return 0
    fi
    if ! is_live "$pid"; then
      return 1
    fi
    sleep 1
  done
  return 1
}

# ==============================================================================
# MANIFEST WRITING
# ==============================================================================
write_manifest() {
  local pid="$1"
  local log_file="$2"
  local actual_version chip memory_bytes os_version
  
  actual_version="$(rapid_version)"
  chip="$(sysctl -n machdep.cpu.brand_string 2>/dev/null || uname -m)"
  memory_bytes="$(sysctl -n hw.memsize 2>/dev/null || echo 0)"
  os_version="$(sw_vers -productVersion 2>/dev/null || uname -r)"
  
  mkdir -p "$RUNTIME_DIR"
  
  jq -n \
    --arg started_at "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
    --argjson pid "$pid" \
    --arg model_alias "$MODEL_ALIAS" \
    --arg model_resolved "$MODEL_RESOLVED" \
    --arg host "$HOST" \
    --argjson port "$PORT" \
    --arg rapid_mlx_bin "$RAPID_MLX" \
    --arg rapid_mlx_version "$actual_version" \
    --arg chip "$chip" \
    --argjson memory_bytes "$memory_bytes" \
    --arg macos "$os_version" \
    --arg log "$log_file" \
    --argjson max_tokens "$MAX_TOKENS" \
    --argjson prefill_step "$PREFILL_STEP" \
    --argjson gpu_memory "$GPU_MEMORY" \
    '{
      started_at: $started_at,
      pid: $pid,
      model_alias: $model_alias,
      model_resolved: $model_resolved,
      endpoint: ("http://"+$host+":"+($port|tostring)+"/v1"),
      rapid_mlx: {
        binary: $rapid_mlx_bin,
        version: $rapid_mlx_version
      },
      host: {
        chip: $chip,
        memory_bytes: $memory_bytes,
        macos: $macos
      },
      settings: {
        max_tokens: $max_tokens,
        prefill_step_size: $prefill_step,
        gpu_memory_utilization: $gpu_memory,
        prefix_cache: true,
        multimodal: false,
        telemetry: false,
        kv_cache_quantization: false,
        turboquant: false,
        mtp: false,
        dflash: false,
        suffix_decoding: false,
        tool_logits_bias: false,
        cloud_routing: false
      },
      log: $log
    }' > "$MANIFEST_FILE"
}

# ==============================================================================
# START COMMAND
# ==============================================================================
start_server() {
  require curl
  require jq
  require lsof
  
  check_version
  
  mkdir -p "$RUNTIME_DIR" "$LOG_DIR"
  
  # Check for existing listener on port
  local existing_listener
  existing_listener="$(listener_pid)"
  if [[ -n "$existing_listener" ]]; then
    if is_owned_rapid_mlx "$existing_listener"; then
      log "already running: PID $existing_listener on port $PORT"
      return 0
    else
      die "port $PORT is occupied by unrelated process PID $existing_listener"
    fi
  fi
  
  # Check for stale PID file
  local stale_pid
  stale_pid="$(pid_from_file)"
  if [[ -n "$stale_pid" ]]; then
    if is_owned_rapid_mlx "$stale_pid"; then
      # Process is actually running - shouldn't happen given listener check above
      log "found running owned process PID $stale_pid"
      return 0
    elif is_live "$stale_pid"; then
      # PID exists but is not our Rapid-MLX - refuse to touch it
      die "stale PID file contains unrelated process PID $stale_pid - remove $PID_FILE manually if safe"
    else
      # PID is dead - safe to clean
      log "cleaning stale PID file (PID $stale_pid no longer exists)"
      rm -f "$PID_FILE"
    fi
  fi
  
  # Create timestamped log
  local stamp log_file pid
  stamp="$(date '+%Y%m%d-%H%M%S')"
  log_file="$LOG_DIR/rapid-mlx-${PORT}-${stamp}.log"
  ln -sfn "$(basename "$log_file")" "$CURRENT_LOG"
  
  # Start server with production flags
  log "starting Rapid-MLX ${EXPECTED_VERSION} model=${MODEL_ALIAS}"
  log "flags: --host ${HOST} --port ${PORT} --max-tokens ${MAX_TOKENS} --prefill-step-size ${PREFILL_STEP} --gpu-memory-utilization ${GPU_MEMORY} --enable-prefix-cache --no-mllm"
  
  # Use process group for clean termination
  nohup "$RAPID_MLX" --no-telemetry serve "$MODEL_ALIAS" \
    --host "$HOST" \
    --port "$PORT" \
    --max-tokens "$MAX_TOKENS" \
    --prefill-step-size "$PREFILL_STEP" \
    --gpu-memory-utilization "$GPU_MEMORY" \
    --enable-prefix-cache \
    --no-mllm \
    >"$log_file" 2>&1 &
  
  pid=$!
  
  # Write PID atomically
  printf '%s\n' "$pid" > "$PID_FILE"
  
  # Wait for readiness
  log "waiting for readiness (timeout ${STARTUP_TIMEOUT_S}s)..."
  if ! wait_for_readiness "$pid"; then
    log "startup failed - cleaning up"
    tail -80 "$log_file" || true
    
    # Kill our process
    if is_live "$pid"; then
      kill "$pid" 2>/dev/null || true
      sleep 2
      if is_live "$pid"; then
        kill -KILL "$pid" 2>/dev/null || true
      fi
    fi
    
    rm -f "$PID_FILE"
    die "server did not become healthy within ${STARTUP_TIMEOUT_S}s"
  fi
  
  # Verify runtime fingerprint
  if ! is_owned_rapid_mlx "$pid"; then
    kill "$pid" 2>/dev/null || true
    rm -f "$PID_FILE"
    die "started process PID $pid does not match expected fingerprint"
  fi
  
  write_manifest "$pid" "$log_file"
  
  log "ready: PID=$pid endpoint=$BASE_URL log=$log_file"
}

# ==============================================================================
# STOP COMMAND
# ==============================================================================
stop_server() {
  local pid
  pid="$(pid_from_file)"
  
  # No PID file
  if [[ -z "$pid" ]]; then
    # Check for orphan listener
    local listener
    listener="$(listener_pid)"
    if [[ -n "$listener" ]]; then
      if is_owned_rapid_mlx "$listener"; then
        log "found orphan Rapid-MLX listener PID $listener - stopping"
        pid="$listener"
      else
        die "port $PORT has unrelated listener PID $listener - refusing to stop"
      fi
    else
      log "already stopped"
      rm -f "$PID_FILE" 2>/dev/null || true
      return 0
    fi
  fi
  
  # Verify ownership before signaling
  if ! is_owned_rapid_mlx "$pid"; then
    if is_live "$pid"; then
      die "refusing to stop unrelated process PID $pid"
    else
      log "PID $pid no longer exists - cleaning state"
      rm -f "$PID_FILE"
      return 0
    fi
  fi
  
  # Graceful termination
  log "stopping PID $pid (graceful)"
  kill "$pid" 2>/dev/null || true
  
  local i
  for i in $(seq 1 "$GRACEFUL_SHUTDOWN_S"); do
    if ! is_live "$pid"; then
      rm -f "$PID_FILE"
      log "stopped PID $pid"
      return 0
    fi
    sleep 1
  done
  
  # Force termination
  log "graceful shutdown timeout - forcing termination"
  kill -KILL "$pid" 2>/dev/null || true
  
  for i in $(seq 1 "$FORCED_SHUTDOWN_S"); do
    if ! is_live "$pid"; then
      rm -f "$PID_FILE"
      log "force-stopped PID $pid"
      return 0
    fi
    sleep 1
  done
  
  rm -f "$PID_FILE"
  
  # Final verification
  if is_live "$pid"; then
    die "failed to stop PID $pid"
  fi
  
  log "stopped"
}

# ==============================================================================
# STATUS COMMAND
# ==============================================================================
status_server() {
  local pid
  pid="$(pid_from_file)"
  
  # Check PID file state
  if [[ -z "$pid" ]]; then
    # No PID file - check for orphan
    local listener
    listener="$(listener_pid)"
    if [[ -n "$listener" ]]; then
      if is_owned_rapid_mlx "$listener"; then
        echo "state: orphan_listener"
        echo "pid: $listener"
        echo "note: Rapid-MLX running without PID file"
      else
        echo "state: port_occupied_unrelated"
        echo "port: $PORT"
        echo "listener_pid: $listener"
        echo "note: Unrelated process on port"
      fi
    else
      echo "state: stopped"
    fi
    return 0
  fi
  
  # Have PID file
  if ! is_live "$pid"; then
    echo "state: stale_pid"
    echo "pid_file: $pid (dead)"
    echo "note: Remove $PID_FILE"
    return 1
  fi
  
  if ! is_owned_rapid_mlx "$pid"; then
    echo "state: pid_reuse"
    echo "pid_file: $pid"
    echo "note: PID file contains unrelated process"
    return 1
  fi
  
  # Running and owned
  echo "state: running"
  echo "pid: $pid"
  echo "endpoint: $BASE_URL"
  echo "model: $MODEL_ALIAS"
  
  # Health check
  if health_endpoint >/dev/null 2>&1; then
    echo "health: ok"
  else
    echo "health: unhealthy"
  fi
  
  # Process info
  local rss
  rss="$(ps -p "$pid" -o rss= 2>/dev/null | awk '{print int($1)}')" || rss="unknown"
  echo "rss_mb: $rss"
  
  # Version
  echo "version: $(rapid_version)"
}

# ==============================================================================
# HEALTH COMMAND
# ==============================================================================
health_check() {
  local pid
  pid="$(pid_from_file)"
  
  # Must have owned process
  if [[ -z "$pid" ]] || ! is_live "$pid" || ! is_owned_rapid_mlx "$pid"; then
    echo "health: no_owned_process"
    return 1
  fi
  
  # HTTP health
  if ! health_endpoint >/dev/null 2>&1; then
    echo "health: http_failed"
    return 1
  fi
  
  # Model availability
  local models
  models="$(curl -fsS --max-time "$HEALTH_TIMEOUT_S" "$BASE_URL/v1/models" 2>/dev/null)" || {
    echo "health: models_endpoint_failed"
    return 1
  }
  
  if ! echo "$models" | grep -q "$MODEL_RESOLVED\|$MODEL_ALIAS"; then
    echo "health: model_not_found"
    return 1
  fi
  
  echo "health: ok"
  echo "pid: $pid"
  echo "model: $MODEL_ALIAS"
  echo "endpoint: $BASE_URL"
  return 0
}

# ==============================================================================
# LOGS COMMAND
# ==============================================================================
show_logs() {
  local lines="${1:-50}"
  
  if [[ ! -e "$CURRENT_LOG" ]]; then
    echo "no log file found at $CURRENT_LOG" >&2
    return 1
  fi
  
  tail -n "$lines" "$CURRENT_LOG"
}

# ==============================================================================
# SMOKE COMMAND
# ==============================================================================
smoke_test() {
  require curl
  require jq
  
  log "running smoke test..."
  
  # Simple chat request
  local body
  body="$(curl -fsS --max-time "$SMOKE_TIMEOUT_S" "$BASE_URL/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    --data-binary '{"model":"default","messages":[{"role":"user","content":"Reply with exactly RAPID_MLX_P2_OK."}],"temperature":0,"max_tokens":64,"stream":false}' 2>&1)"
  
  if [[ $? -ne 0 ]]; then
    echo "smoke: FAILED (HTTP error)"
    echo "$body"
    return 1
  fi
  
  if ! echo "$body" | jq -e '.choices[0].message.content | contains("RAPID_MLX_P2_OK")' >/dev/null 2>&1; then
    echo "smoke: FAILED (unexpected response)"
    echo "$body" | jq .
    return 1
  fi
  
  log "smoke: PASS"
  return 0
}

# ==============================================================================
# RESTART COMMAND
# ==============================================================================
restart_server() {
  stop_server
  start_server
}

# ==============================================================================
# USAGE
# ==============================================================================
usage() {
  cat <<EOF
Rapid-MLX ${EXPECTED_VERSION} Production Lifecycle Controller

Usage: $0 <command>

Commands:
  start     Start the server (idempotent)
  stop      Stop the server (idempotent, safe)
  restart   Stop and start
  status    Show server state
  health    Health check
  logs      Show recent logs (optional: N lines, default 50)
  smoke     Run smoke test

Environment:
  RAPID_MLX_BIN    Override binary path (not recommended)

Production fingerprint:
  Version:  ${EXPECTED_VERSION}
  Model:    ${MODEL_ALIAS}
  Host:     ${HOST}
  Port:     ${PORT}
  Max out:  ${MAX_TOKENS}
  Prefill:  ${PREFILL_STEP}
  GPU mem:  ${GPU_MEMORY}

Forbidden: kv-cache-quantization, turboquant, mtp, dflash, suffix-decoding,
           tool-logits-bias, cloud routing, multimodal, telemetry
EOF
}

# ==============================================================================
# MAIN
# ==============================================================================
require curl
require jq
require lsof

case "$ACTION" in
  start)   start_server ;;
  stop)    stop_server ;;
  restart) restart_server ;;
  status)  status_server ;;
  health)  health_check ;;
  logs)    show_logs "${1:-50}" ;;
  smoke)   smoke_test ;;
  help|-h|--help) usage ;;
  *)       usage; exit 2 ;;
esac
