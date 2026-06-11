#!/usr/bin/env fish
# Production Local LLM Server - Rapid-MLX Qwen3.6-35B
# Validated: 2026-06-09, All gates passed

set MODEL_ID "mlx-community/Qwen3.6-35B-A3B-4bit"
set HOST "127.0.0.1"
set PORT 8000

set GREEN '\033[0;32m'
set RED '\033[0;31m'
set YELLOW '\033[1;33m'
set NC '\033[0m'

echo -e "$GREEN=== LOCAL LLM SERVER STARTUP ===$NC"

set API_KEY (security find-generic-password -a local-llm-benchmark -s RAPID_MLX_API_KEY -w 2>/dev/null)
if test -z "$API_KEY"
    echo -e "$RED ERROR: API key not found in Keychain$NC"
    echo "Run: security add-generic-password -a local-llm-benchmark -s RAPID_MLX_API_KEY -w (openssl rand -hex 32)"
    exit 1
end
echo -e "$GREEN✓$NC API key found"

if test -f /tmp/rapid-mlx.pid
    set OLD_PID (cat /tmp/rapid-mlx.pid)
    if ps -p $OLD_PID >/dev/null 2>&1
        echo -e "$YELLOW WARNING: Server already running (PID: $OLD_PID)$NC"
        echo "Stop with: scripts/stop-local-model.fish"
        exit 0
    else
        rm /tmp/rapid-mlx.pid
    end
end

if lsof -i :$PORT >/dev/null 2>&1
    echo -e "$RED ERROR: Port $PORT already in use$NC"
    lsof -i :$PORT
    exit 1
end
echo -e "$GREEN✓$NC Port $PORT available"

if not test -f .venv-rapid/bin/rapid-mlx
    echo -e "$RED ERROR: Rapid-MLX not found in .venv-rapid/$NC"
    exit 1
end
echo -e "$GREEN✓$NC Virtualenv ready"

echo -e "$YELLOW Starting server...$NC"
.venv-rapid/bin/rapid-mlx serve $MODEL_ID \
    --host $HOST \
    --port $PORT \
    --api-key "$API_KEY" \
    --max-tokens 8192 \
    --prefill-step-size 4096 \
    --gpu-memory-utilization 0.82 \
    --enable-prefix-cache \
    --continuous-batching \
    --text-only \
    --timeout 1800 \
    > /tmp/rapid-mlx.log 2>&1 &

set SERVER_PID $last_pid
echo $SERVER_PID > /tmp/rapid-mlx.pid

echo -e "$YELLOW Waiting for warmup (30s)...$NC"
sleep 30

set MAX_WAIT 60
set WAITED 0
set HEALTHY false

while test $WAITED -lt $MAX_WAIT
    if curl -s -H "Authorization: Bearer $API_KEY" "http://$HOST:$PORT/v1/models" | grep -q "$MODEL_ID"
        set HEALTHY true
        break
    end
    sleep 2
    set WAITED (math $WAITED + 2)
end

if test "$HEALTHY" = "true"
    echo -e "$GREEN✓$NC Server healthy"
    echo ""
    echo -e "$GREEN Server ready!$NC"
    echo "  PID: $SERVER_PID"
    echo "  Endpoint: http://$HOST:$PORT/v1"
    echo "  Model: $MODEL_ID"
    echo "  Logs: tail -f /tmp/rapid-mlx.log"
    echo ""
    echo -e "$GREEN Performance Expectations:$NC"
    echo "  Throughput: ~72 tok/s"
    echo "  Warm TTFT: ~275ms (Kilo prefix cached)"
    echo "  Cold TTFT: ~10s (first request)"
    exit 0
else
    echo -e "$RED ERROR: Server failed to start$NC"
    tail -50 /tmp/rapid-mlx.log
    exit 1
end
