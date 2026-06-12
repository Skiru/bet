#!/bin/bash
# Phase 1 — Rapid-MLX Raw Baseline Launcher
# Production-safe server management for qwen3.6-35b-4bit
# Version: 1.0.0

set -euo pipefail

# =============================================================================
# CONFIGURATION
# =============================================================================

RAPID_MLX_BIN="/Users/mkoziol/.venvs/rapid-mlx-0.7.1/bin/rapid-mlx"
MODEL_ALIAS="qwen3.6-35b-4bit"
HOST="127.0.0.1"
PORT="8000"
BASE_URL="http://${HOST}:${PORT}"

# Runtime directories (relative to script location)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${PROJECT_ROOT}/reports/rapidmlx-baseline/runtime"
LOGS_DIR="${PROJECT_ROOT}/reports/rapidmlx-baseline/logs"
FAILURES_DIR="${PROJECT_ROOT}/reports/rapidmlx-baseline/failures"

# PID and manifest files
PID_FILE="${RUNTIME_DIR}/rapid-mlx.pid"
MANIFEST_FILE="${RUNTIME_DIR}/manifest.json"
STARTUP_LOG="${LOGS_DIR}/startup.log"

# Server parameters
MAX_TOKENS="4096"
GPU_MEMORY_UTILIZATION="0.70"
REQUEST_TIMEOUT="30"
HEALTH_TIMEOUT="60"

# =============================================================================
# INITIALIZATION
# =============================================================================

init_directories() {
    mkdir -p "${RUNTIME_DIR}" "${LOGS_DIR}" "${FAILURES_DIR}"
}

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

log() {
    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "[${timestamp}] $1"
}

get_timestamp() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

write_pid_atomic() {
    local pid="$1"
    local tmp_file="${PID_FILE}.tmp.$$"
    echo "${pid}" > "${tmp_file}"
    mv "${tmp_file}" "${PID_FILE}"
}

read_pid() {
    if [[ -f "${PID_FILE}" ]]; then
        cat "${PID_FILE}"
    else
        echo ""
    fi
}

is_pid_alive() {
    local pid="$1"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

get_pid_command() {
    local pid="$1"
    if [[ -n "${pid}" ]]; then
        ps -p "${pid}" -o command= 2>/dev/null || echo ""
    else
        echo ""
    fi
}

get_pid_start_time() {
    local pid="$1"
    if [[ -n "${pid}" ]]; then
        ps -p "${pid}" -o lstart= 2>/dev/null || echo ""
    else
        echo ""
    fi
}

check_port_status() {
    local port_status
    port_status=$(lsof -nP -iTCP:${PORT} -sTCP:LISTEN 2>/dev/null || echo "")

    if [[ -z "${port_status}" ]]; then
        echo "FREE"
    else
        echo "${port_status}"
    fi
}

get_port_owner_pid() {
    local port_info
    port_info=$(lsof -nP -iTCP:${PORT} -sTCP:LISTEN -t 2>/dev/null || echo "")
    echo "${port_info}"
}

# =============================================================================
# VERIFICATION FUNCTIONS
# =============================================================================

verify_rapid_mlx_binary() {
    if [[ ! -x "${RAPID_MLX_BIN}" ]]; then
        log "ERROR: Rapid-MLX binary not found: ${RAPID_MLX_BIN}"
        return 1
    fi

    local version
    version=$("${RAPID_MLX_BIN}" --version 2>&1 | head -1)
    log "Rapid-MLX binary verified: ${version}"
}

verify_model_available() {
    local models_output
    models_output=$(RAPID_MLX_TELEMETRY=0 "${RAPID_MLX_BIN}" models 2>&1)

    if echo "${models_output}" | grep -q "${MODEL_ALIAS}"; then
        log "Model alias verified: ${MODEL_ALIAS}"
        return 0
    else
        log "ERROR: Model alias not found: ${MODEL_ALIAS}"
        return 1
    fi
}

verify_port_free() {
    local port_status
    port_status=$(check_port_status)

    if [[ "${port_status}" == "FREE" ]]; then
        log "Port ${PORT} is free"
        return 0
    fi

    local owner_pid
    owner_pid=$(get_port_owner_pid)

    if [[ -n "${owner_pid}" ]]; then
        local owner_cmd
        owner_cmd=$(get_pid_command "${owner_pid}")

        if echo "${owner_cmd}" | grep -q "rapid-mlx"; then
            log "Port ${PORT} owned by Rapid-MLX process (PID: ${owner_pid})"
            return 2  # Owned by Rapid-MLX
        else
            log "ERROR: Port ${PORT} occupied by unrelated process (PID: ${owner_pid})"
            log "Owner command: ${owner_cmd}"
            return 1
        fi
    fi

    log "ERROR: Port ${PORT} status unknown"
    return 1
}

# =============================================================================
# SERVER MANAGEMENT
# =============================================================================

get_effective_command() {
    echo "RAPID_MLX_TELEMETRY=0 ${RAPID_MLX_BIN} serve ${MODEL_ALIAS} \\
  --host ${HOST} \\
  --port ${PORT} \\
  --max-tokens ${MAX_TOKENS} \\
  --gpu-memory-utilization ${GPU_MEMORY_UTILIZATION} \\
  --no-mllm"
}

start_server() {
    log "Starting Rapid-MLX server..."

    init_directories
    verify_rapid_mlx_binary
    verify_model_available

    local port_check
    port_check=$(verify_port_free 2>&1)
    local port_result=$?

    if [[ ${port_result} -eq 1 ]]; then
        log "BLOCKED: Port ${PORT} occupied by unrelated process"
        echo "RAPID_BASELINE_BLOCKED — PORT_8000_OCCUPIED"
        return 1
    fi

    if [[ ${port_result} -eq 2 ]]; then
        log "WARNING: Port ${PORT} already has a Rapid-MLX process"
        local existing_pid
        existing_pid=$(get_port_owner_pid)
        log "Existing PID: ${existing_pid}"
        echo "Server already running (PID: ${existing_pid})"
        return 0
    fi

    # Rotate startup log
    if [[ -f "${STARTUP_LOG}" ]]; then
        local timestamp
        timestamp=$(date -u +"%Y%m%dT%H%M%SZ")
        mv "${STARTUP_LOG}" "${LOGS_DIR}/startup-${timestamp}.log"
    fi

    # Start server in background
    log "Launching server with command:"
    log "$(get_effective_command)"

    RAPID_MLX_TELEMETRY=0 "${RAPID_MLX_BIN}" serve "${MODEL_ALIAS}" \
        --host "${HOST}" \
        --port "${PORT}" \
        --max-tokens "${MAX_TOKENS}" \
        --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
        --no-mllm \
        > "${STARTUP_LOG}" 2>&1 &

    local server_pid=$!
    write_pid_atomic "${server_pid}"

    log "Server launched with PID: ${server_pid}"
    log "Waiting for server to become healthy..."

    # Health polling with timeout
    local start_time
    start_time=$(date +%s)
    local healthy=false

    while true; do
        local current_time
        current_time=$(date +%s)
        local elapsed=$((current_time - start_time))

        if [[ ${elapsed} -ge ${HEALTH_TIMEOUT} ]]; then
            log "ERROR: Health check timeout after ${HEALTH_TIMEOUT}s"
            break
        fi

        if health_check_quiet; then
            healthy=true
            break
        fi

        # Check if process is still alive
        if ! is_pid_alive "${server_pid}"; then
            log "ERROR: Server process died during startup"
            break
        fi

        sleep 2
    done

    if [[ "${healthy}" == "true" ]]; then
        log "Server is healthy and ready"
        write_manifest
        echo "Server started successfully (PID: ${server_pid})"
        return 0
    else
        log "ERROR: Server failed to start"
        echo "Server startup failed. Check ${STARTUP_LOG} for details."
        return 1
    fi
}

stop_server() {
    log "Stopping Rapid-MLX server..."

    local pid
    pid=$(read_pid)

    if [[ -z "${pid}" ]]; then
        # Check if port is occupied anyway
        local port_owner
        port_owner=$(get_port_owner_pid)

        if [[ -n "${port_owner}" ]]; then
            log "No PID file, but port ${PORT} is occupied by PID ${port_owner}"
            pid="${port_owner}"
        else
            log "No server running"
            echo "No server running"
            return 0
        fi
    fi

    if ! is_pid_alive "${pid}"; then
        log "PID ${pid} is not alive, cleaning up"
        rm -f "${PID_FILE}"
        echo "Server was not running (stale PID cleaned)"
        return 0
    fi

    # Verify it's actually a Rapid-MLX process
    local pid_cmd
    pid_cmd=$(get_pid_command "${pid}")

    if ! echo "${pid_cmd}" | grep -q "rapid-mlx"; then
        log "ERROR: PID ${pid} is not a Rapid-MLX process"
        log "Command: ${pid_cmd}"
        echo "ERROR: Refusing to stop unrelated process"
        return 1
    fi

    log "Sending SIGTERM to PID ${pid}"
    kill -TERM "${pid}" 2>/dev/null || true

    # Wait for graceful shutdown
    local wait_time=0
    local max_wait=30

    while [[ ${wait_time} -lt ${max_wait} ]]; do
        if ! is_pid_alive "${pid}"; then
            log "Server stopped gracefully"
            rm -f "${PID_FILE}"
            echo "Server stopped (PID: ${pid})"
            return 0
        fi
        sleep 1
        wait_time=$((wait_time + 1))
    done

    # Force kill if still alive
    if is_pid_alive "${pid}"; then
        log "WARNING: Graceful shutdown timeout, sending SIGKILL"
        log "Recording forced termination event"
        echo "$(get_timestamp) SIGKILL ${pid}" >> "${FAILURES_DIR}/forced-stops.log"
        kill -KILL "${pid}" 2>/dev/null || true
        sleep 1
    fi

    rm -f "${PID_FILE}"
    echo "Server stopped (forced)"
    return 0
}

restart_server() {
    log "Restarting Rapid-MLX server..."
    stop_server || true
    sleep 2
    start_server
}

# =============================================================================
# STATUS AND HEALTH
# =============================================================================

status_server() {
    local pid
    pid=$(read_pid)

    echo "=== Rapid-MLX Server Status ==="
    echo ""

    if [[ -n "${pid}" ]]; then
        echo "PID File: ${PID_FILE}"
        echo "PID: ${pid}"

        if is_pid_alive "${pid}"; then
            echo "Process: ALIVE"
            local start_time
            start_time=$(get_pid_start_time "${pid}")
            echo "Start Time: ${start_time}"
            local rss
            rss=$(ps -p "${pid}" -o rss= 2>/dev/null | awk '{print $1}')
            if [[ -n "${rss}" ]]; then
                echo "RSS: ${rss} KB"
            fi
        else
            echo "Process: DEAD (stale PID file)"
        fi
    else
        echo "PID File: (none)"
    fi

    echo ""
    echo "Port ${PORT} Status:"
    local port_status
    port_status=$(check_port_status)

    if [[ "${port_status}" == "FREE" ]]; then
        echo "  FREE"
    else
        local port_owner
        port_owner=$(get_port_owner_pid)
        echo "  Owner PID: ${port_owner}"
        local owner_cmd
        owner_cmd=$(get_pid_command "${port_owner}")
        echo "  Command: ${owner_cmd}"
    fi

    echo ""
    echo "Configuration:"
    echo "  Model: ${MODEL_ALIAS}"
    echo "  Host: ${HOST}"
    echo "  Port: ${PORT}"
    echo "  Binary: ${RAPID_MLX_BIN}"
}

health_check_quiet() {
    local health_endpoint="${BASE_URL}/health"
    local response

    response=$(curl -s -o /dev/null -w "%{http_code}" \
        --connect-timeout 5 \
        --max-time 10 \
        "${health_endpoint}" 2>/dev/null || echo "000")

    if [[ "${response}" == "200" ]]; then
        return 0
    fi

    # Try alternative endpoints
    local models_endpoint="${BASE_URL}/v1/models"
    response=$(curl -s -o /dev/null -w "%{http_code}" \
        --connect-timeout 5 \
        --max-time 10 \
        "${models_endpoint}" 2>/dev/null || echo "000")

    if [[ "${response}" == "200" ]]; then
        return 0
    fi

    return 1
}

health_check() {
    echo "=== Rapid-MLX Health Check ==="
    echo ""

    local health_endpoint="${BASE_URL}/health"
    local models_endpoint="${BASE_URL}/v1/models"

    echo "Testing health endpoint: ${health_endpoint}"
    local health_response
    health_response=$(curl -s -w "\n%{http_code}" \
        --connect-timeout 5 \
        --max-time 10 \
        "${health_endpoint}" 2>/dev/null || echo -e "\n000")

    local health_body
    health_body=$(echo "${health_response}" | head -n -1)
    local health_code
    health_code=$(echo "${health_response}" | tail -n 1)

    echo "  HTTP Status: ${health_code}"
    if [[ -n "${health_body}" ]]; then
        echo "  Response: ${health_body}"
    fi

    echo ""
    echo "Testing models endpoint: ${models_endpoint}"
    local models_response
    models_response=$(curl -s -w "\n%{http_code}" \
        --connect-timeout 5 \
        --max-time 10 \
        "${models_endpoint}" 2>/dev/null || echo -e "\n000")

    local models_body
    models_body=$(echo "${models_response}" | head -n -1)
    local models_code
    models_code=$(echo "${models_response}" | tail -n 1)

    echo "  HTTP Status: ${models_code}"
    if [[ -n "${models_body}" ]]; then
        echo "  Response: ${models_body}" | head -c 500
        echo ""
    fi

    echo ""
    if [[ "${health_code}" == "200" || "${models_code}" == "200" ]]; then
        echo "Status: HEALTHY"
        return 0
    else
        echo "Status: UNHEALTHY"
        return 1
    fi
}

# =============================================================================
# INFORMATION COMMANDS
# =============================================================================

show_models() {
    echo "=== Available Models ==="
    RAPID_MLX_TELEMETRY=0 "${RAPID_MLX_BIN}" models 2>&1 | grep -E "(qwen3.6-35b|Alias|─)" | head -20
    echo ""
    echo "Target model: ${MODEL_ALIAS}"

    echo ""
    echo "=== Server Models Endpoint ==="
    local models_endpoint="${BASE_URL}/v1/models"
    curl -s --connect-timeout 5 --max-time 10 "${models_endpoint}" 2>/dev/null || echo "Server not responding"
}

show_logs() {
    echo "=== Recent Startup Logs ==="
    if [[ -f "${STARTUP_LOG}" ]]; then
        tail -50 "${STARTUP_LOG}"
    else
        echo "No startup log found"
    fi
}

show_command() {
    echo "=== Effective Server Command ==="
    echo ""
    get_effective_command
    echo ""
    echo "Environment:"
    echo "  RAPID_MLX_TELEMETRY=0"
    echo ""
    echo "Working directory: ${PROJECT_ROOT}"
    echo "Log file: ${STARTUP_LOG}"
}

write_manifest() {
    local pid
    pid=$(read_pid)

    local timestamp
    timestamp=$(get_timestamp)

    cat > "${MANIFEST_FILE}" << EOF
{
  "timestamp": "${timestamp}",
  "pid": ${pid:-0},
  "model_alias": "${MODEL_ALIAS}",
  "host": "${HOST}",
  "port": ${PORT},
  "binary": "${RAPID_MLX_BIN}",
  "command": "$(get_effective_command | tr '\n' ' ')",
  "max_tokens": ${MAX_TOKENS},
  "gpu_memory_utilization": ${GPU_MEMORY_UTILIZATION}
}
EOF
    log "Manifest written to ${MANIFEST_FILE}"
}

# =============================================================================
# MAIN
# =============================================================================

main() {
    local command="${1:-help}"

    case "${command}" in
        start)
            start_server
            ;;
        stop)
            stop_server
            ;;
        restart)
            restart_server
            ;;
        status)
            status_server
            ;;
        health)
            health_check
            ;;
        models)
            show_models
            ;;
        logs)
            show_logs
            ;;
        command)
            show_command
            ;;
        help|--help|-h)
            echo "Usage: $0 {start|stop|restart|status|health|models|logs|command}"
            echo ""
            echo "Commands:"
            echo "  start    - Start the Rapid-MLX server"
            echo "  stop     - Stop the server gracefully"
            echo "  restart  - Restart the server"
            echo "  status   - Show server status"
            echo "  health   - Check server health"
            echo "  models   - Show available models"
            echo "  logs     - Show recent logs"
            echo "  command  - Show effective command"
            ;;
        *)
            echo "Unknown command: ${command}"
            echo "Use '$0 help' for usage"
            exit 1
            ;;
    esac
}

main "$@"
