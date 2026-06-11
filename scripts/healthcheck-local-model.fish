#!/usr/bin/env fish
# Health check for local LLM server

set API_KEY (security find-generic-password -a local-llm-benchmark -s RAPID_MLX_API_KEY -w 2>/dev/null)
set MODEL_ID "mlx-community/Qwen3.6-35B-A3B-4bit"

set HTTP_CODE (curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $API_KEY" "http://127.0.0.1:8000/v1/models" 2>/dev/null)

if test "$HTTP_CODE" = "200"
    echo "✓ Server healthy"
    echo "✓ Model: $MODEL_ID"
    
    if test -f /tmp/rapid-mlx.pid
        set PID (cat /tmp/rapid-mlx.pid)
        echo "✓ PID: $PID"
    end
    
    set START (date +%s%N)
    curl -s -X POST "http://127.0.0.1:8000/v1/chat/completions" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"model":"mlx-community/Qwen3.6-35B-A3B-4bit","messages":[{"role":"user","content":"test"}],"max_tokens":5}' \
        >/dev/null 2>&1
    set END (date +%s%N)
    set LATENCY (math "($END - $START) / 1000000")
    echo "✓ Latency: {$LATENCY}ms"
    
    exit 0
else
    echo "✗ Server not responding (HTTP $HTTP_CODE)"
    exit 1
end
